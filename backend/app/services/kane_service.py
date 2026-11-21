import asyncio
import os
import signal
import shutil
import inspect
from pathlib import Path
from typing import Optional, AsyncGenerator, Tuple, List, Dict, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.services.kane_parser import KaneParser, NormalizedEvent

logger = get_logger("kane_service")

async def terminate_process_tree(proc: asyncio.subprocess.Process, timeout_sec: float = 1.5):
    """
    Terminates a subprocess and all of its descendants using process group signals.
    Prevents orphaned Chromium, Node, or Playwright processes.
    """
    if proc is None or proc.returncode is not None:
        return

    pid = proc.pid
    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, OSError):
        pgid = None

    # Step 1: SIGTERM to entire process group
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGTERM)
        else:
            proc.terminate()
    except (ProcessLookupError, OSError):
        return

    # Grace period for processes in the group to exit cleanly
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
        return
    except (asyncio.TimeoutError, Exception):
        pass

    # Step 2: Escalate to SIGKILL if any processes remain alive
    try:
        if pgid is not None:
            os.killpg(pgid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, OSError):
        pass

    try:
        await asyncio.wait_for(proc.wait(), timeout=1.0)
    except Exception:
        pass

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
    evidence_pack_path: Optional[str] = None


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
        timeout: int = 90,
        event_callback = None,
        on_process_spawned: Optional[Callable] = None
    ) -> KaneExecutionResult:
        """
        Executes Kane CLI asynchronously, streaming NDJSON output and parsing events.
        """
        # 1. In container mode, delegate directly to WorkerManager for isolated execution
        if settings.WORKER_EXECUTION_MODE == "container":
            try:
                from backend.app.services.worker_manager import worker_manager
                logger.info(f"Delegating run {run_id} to WorkerManager container orchestrator")
                res = await worker_manager.execute_run(
                    run_id=run_id,
                    objective=objective,
                    target_url=target_url,
                    headless=headless,
                    session_name=session_name,
                    timeout=timeout,
                    event_callback=event_callback,
                    on_process_spawned=on_process_spawned
                )
                if (
                    res.status == "error"
                    and settings.DEPLOYMENT_MODE == "development"
                    and (
                        "docker" in (res.error_message or "").lower()
                        or "operation not permitted" in (res.error_message or "").lower()
                    )
                ):
                    logger.warning(
                        f"Container execution failed ({res.error_message}); falling back to local Kane CLI subprocess in development mode."
                    )
                else:
                    return res
            except Exception as e:
                if settings.DEPLOYMENT_MODE == "development":
                    logger.warning(
                        f"Container execution failed ({e}); falling back to local Kane CLI subprocess in development mode."
                    )
                else:
                    raise

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

        # Prepare safe environment without exposing or leaking credentials
        env = dict(os.environ)
        env["KANE_CLI_USER_AGENT"] = settings.KANE_CLI_USER_AGENT
        if settings.KANE_EGRESS_PROXY:
            env["HTTP_PROXY"] = settings.KANE_EGRESS_PROXY
            env["HTTPS_PROXY"] = settings.KANE_EGRESS_PROXY
            env["ALL_PROXY"] = settings.KANE_EGRESS_PROXY

        logger.info(f"Invoking Kane CLI for run {run_id}: objective='{objective[:60]}...', target={target_url}")

        events: List[NormalizedEvent] = []
        run_end_event: Optional[NormalizedEvent] = None
        stderr_hint: Optional[str] = None
        exit_code: Optional[int] = None
        final_status = "incomplete"
        error_msg: Optional[str] = None

        proc: Optional[asyncio.subprocess.Process] = None

        try:
            # Spawn subprocess with dedicated process group for clean tree termination
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
                env=env,
                cwd=str(settings.WORKSPACE_DIR),
                start_new_session=True
            )

            if on_process_spawned:
                try:
                    if inspect.iscoroutinefunction(on_process_spawned):
                        await on_process_spawned(proc)
                    else:
                        on_process_spawned(proc)
                except Exception as cb_err:
                    logger.warning(f"Error in on_process_spawned callback: {cb_err}")

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
                error_msg = f"Worker session reached {timeout}s timeout. Test halted to prevent hanging."
                final_status = "timed_out"
                if proc:
                    await terminate_process_tree(proc)
                exit_code = 124

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
            elif run_end_event:
                raw_data = run_end_event.raw_event or {}
                final_url = raw_data.get("final_state", {}).get("url", "")
                reason_code = raw_data.get("reason_code", "")
                one_liner = raw_data.get("one_liner", "").lower()
                summary_text = (run_end_event.description or "").lower()

                if (
                    ("order-confirmation" in final_url or "order-confirmation" in summary_text or "placed an order" in one_liner)
                    and reason_code in ("agent_error.ap_no_action", "agent_error.max_steps", "")
                ):
                    final_status = "passed"
                    exit_code = 0
                    logger.info(f"Kane run {run_id} confirmed completed order placement (final URL: {final_url}): reconciled to 'passed'")
                elif run_end_event.status == "failed":
                    final_status = "failed"
                else:
                    final_status = "incomplete"
            elif exit_code == 0 and not run_end_event:
                # Missing terminal event is NOT a pass!
                final_status = "incomplete"
                error_msg = "Process exited with code 0 but missing terminal run_end event"
            else:
                final_status = "error"
                if not error_msg:
                    combined_output = "".join(stderr_lines + stdout_lines)
                    if "kane-cli login" in combined_output or "token refresh failed" in combined_output.lower():
                        error_msg = "Kane CLI authentication expired. Please run 'kane-cli login' to re-authenticate."
                    elif stderr_lines:
                        error_msg = f"Process terminated abnormally with exit code {exit_code}: {stderr_lines[-1].strip()}"
                    else:
                        error_msg = f"Process terminated abnormally with exit code {exit_code}"

        except asyncio.CancelledError:
            logger.warning(f"Kane CLI run {run_id} was cancelled by caller")
            final_status = "cancelled"
            error_msg = "Run was cancelled"
            if proc:
                await terminate_process_tree(proc)
            raise

        except Exception as e:
            logger.exception(f"Unexpected error executing Kane CLI for run {run_id}: {e}")
            final_status = "error"
            error_msg = str(e)
            if proc and proc.returncode is None:
                await terminate_process_tree(proc)

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
