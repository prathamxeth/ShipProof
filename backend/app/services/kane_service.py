import asyncio
import os
import shutil
import inspect
from pathlib import Path
from typing import Optional, AsyncGenerator, Tuple, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime, timezone
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.services.kane_parser import KaneParser, NormalizedEvent

logger = get_logger("kane_service")

@dataclass
class KaneExecutionResult:
    run_id: str
    exit_code: Optional[int]
    status: str  # passed, failed, incomplete, cancelled, error
    raw_stdout_path: str
    raw_stderr_path: str
    events: List[NormalizedEvent] = field(default_factory=list)
    run_end_event: Optional[NormalizedEvent] = None
    stderr_hint: Optional[str] = None
    error_message: Optional[str] = None


class KaneService:
    """
    Subprocess adapter for Kane CLI.
    Directly invokes the Kane binary with documented flags:
    kane-cli run "<objective>" --url <url> --agent [--headless] [--name <slug>] [--timeout <sec>]
    
    Adheres strictly to production constraints:
    - Never uses shell=True
    - Captures stdout/stderr separately
    - Parses NDJSON line-by-line
    - Safely logs raw outputs
    - Handles timeouts and cancellations cleanly
    """

    @staticmethod
    def resolve_executable() -> str:
        """
        Resolves the kane-cli executable from configured path or PATH.
        Raises FileNotFoundError if missing or not executable.
        """
        configured_path = settings.KANE_CLI_PATH
        if configured_path and os.path.exists(configured_path) and os.access(configured_path, os.X_OK):
            return str(Path(configured_path).resolve())

        which_path = shutil.which("kane-cli")
        if which_path and os.access(which_path, os.X_OK):
            return str(Path(which_path).resolve())

        raise FileNotFoundError(
            f"kane-cli executable not found at '{configured_path}' or system PATH."
        )

    @classmethod
    async def run_kane(
        cls,
        run_id: str,
        objective: str,
        target_url: str,
        headless: bool = True,
        session_name: Optional[str] = None,
        timeout: int = 120,
        event_callback = None
    ) -> KaneExecutionResult:
        """
        Executes Kane CLI asynchronously, streaming NDJSON output and parsing events.
        """
        executable = cls.resolve_executable()
        
        # Prepare run log directory
        run_dir = settings.DATA_DIR / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        raw_stdout_path = run_dir / "raw_stdout.log"
        raw_stderr_path = run_dir / "raw_stderr.log"

        # Build clean command arguments (NO shell=True)
        cmd = [
            executable,
            "run",
            objective,
            "--url",
            target_url,
            "--agent",
            "--timeout",
            str(timeout)
        ]

        if headless:
            cmd.append("--headless")

        if session_name:
            cmd.extend(["--name", session_name])

        # Prepare safe environment without exposing or leaking credentials
        env = dict(os.environ)
        env["KANE_CLI_USER_AGENT"] = settings.KANE_CLI_USER_AGENT

        logger.info(f"Invoking Kane CLI for run {run_id}: objective='{objective[:60]}...', target={target_url}")

        events: List[NormalizedEvent] = []
        run_end_event: Optional[NormalizedEvent] = None
        stderr_hint: Optional[str] = None
        exit_code: Optional[int] = None
        final_status = "incomplete"
        error_msg: Optional[str] = None

        proc: Optional[asyncio.subprocess.Process] = None

        try:
            # Spawn subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=str(settings.WORKSPACE_DIR)
            )

            stdout_lines: List[str] = []
            stderr_lines: List[str] = []

            async def read_stdout():
                nonlocal run_end_event
                assert proc and proc.stdout
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    stdout_lines.append(decoded)
                    
                    event = KaneParser.parse_line(decoded)
                    if event:
                        events.append(event)
                        if event.event_type == "run_end":
                            run_end_event = event
                        if event_callback:
                            try:
                                if inspect.iscoroutinefunction(event_callback):
                                    await event_callback(event)
                                else:
                                    event_callback(event)
                            except Exception as cb_err:
                                logger.warning(f"Error in event callback: {cb_err}")

            async def read_stderr():
                nonlocal stderr_hint
                assert proc and proc.stderr
                while True:
                    line = await proc.stderr.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    stderr_lines.append(decoded)
                    if "kane-cli evidence serve" in decoded:
                        stderr_hint = decoded.strip()

            # Wait for execution with timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(read_stdout(), read_stderr(), proc.wait()),
                    timeout=float(timeout + 15)  # grace period for shutdown
                )
                exit_code = proc.returncode
            except asyncio.TimeoutError:
                logger.error(f"Kane CLI run {run_id} timed out after {timeout} seconds")
                error_msg = f"Process timed out after {timeout} seconds"
                final_status = "incomplete"
                if proc:
                    try:
                        proc.terminate()
                        await asyncio.sleep(1)
                        if proc.returncode is None:
                            proc.kill()
                    except Exception as kill_err:
                        logger.warning(f"Error terminating timed out process: {kill_err}")
                exit_code = -1

            # Write raw stdout and stderr logs for auditability
            with open(raw_stdout_path, "w", encoding="utf-8") as f_out:
                f_out.writelines(stdout_lines)
            with open(raw_stderr_path, "w", encoding="utf-8") as f_err:
                f_err.writelines(stderr_lines)

            # Determine final status using genuine terminal event
            if error_msg:
                final_status = "incomplete"
            elif KaneParser.is_terminal_success(run_end_event):
                final_status = "passed"
            elif run_end_event and run_end_event.status == "failed":
                final_status = "failed"
            elif exit_code == 0 and not run_end_event:
                # Missing terminal event is NOT a pass!
                final_status = "incomplete"
                error_msg = "Process exited with code 0 but missing terminal run_end event"
            else:
                final_status = "error"
                if not error_msg:
                    error_msg = f"Process terminated abnormally with exit code {exit_code}"

        except asyncio.CancelledError:
            logger.warning(f"Kane CLI run {run_id} was cancelled by caller")
            final_status = "cancelled"
            error_msg = "Run was cancelled"
            if proc:
                try:
                    proc.terminate()
                    await asyncio.sleep(0.5)
                    if proc.returncode is None:
                        proc.kill()
                except Exception:
                    pass
            raise

        except Exception as e:
            logger.exception(f"Unexpected error executing Kane CLI for run {run_id}: {e}")
            final_status = "error"
            error_msg = str(e)
            if proc and proc.returncode is None:
                try:
                    proc.kill()
                except Exception:
                    pass

        return KaneExecutionResult(
            run_id=run_id,
            exit_code=exit_code,
            status=final_status,
            raw_stdout_path=str(raw_stdout_path),
            raw_stderr_path=str(raw_stderr_path),
            events=events,
            run_end_event=run_end_event,
            stderr_hint=stderr_hint,
            error_message=error_msg
        )
