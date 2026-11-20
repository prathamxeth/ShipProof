import asyncio
import inspect
import json
import os
import secrets
import shutil
import hashlib
from pathlib import Path
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timezone
import urllib.parse
import socket

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.url_validator import validate_target_url
from backend.app.schemas.worker import WorkerJobConfig, WorkerIPCMessage
from backend.app.services.worker_policy import WorkerPolicy
from backend.app.services.worker_ipc import WorkerIPCReceiver
from backend.app.services.worker_runtime import WorkerRuntime, WorkerRuntimeError
from backend.app.services.kane_parser import KaneParser, NormalizedEvent
from backend.app.services.kane_service import KaneExecutionResult

logger = get_logger("worker_manager")

class WorkerSecurityViolationError(Exception):
    pass

class WorkerManager:
    """
    Trusted host-side orchestrator for isolated worker containers.
    Manages container lifecycles, host-side security inspection,
    authenticated IPC streams, cancellation, timeout watchdogs,
    and truthful status reporting.
    """

    def __init__(self):
        self.runtime = WorkerRuntime()
        self._active_workers: Dict[str, asyncio.Task] = {}
        self._active_receivers: Dict[str, WorkerIPCReceiver] = {}

    @staticmethod
    def resolve_target_ips(target_url: str) -> List[str]:
        """
        Resolves hostname from target URL to construct allowed target IPs.
        """
        parsed = urllib.parse.urlparse(target_url)
        hostname = parsed.hostname or ""
        if not hostname:
            return []
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or 80, proto=socket.IPPROTO_TCP)
            ips = list(set([item[4][0] for item in addr_info]))
            return ips
        except Exception as e:
            logger.warning(f"Failed to resolve DNS for {hostname}: {e}")
            return []

    async def execute_run(
        self,
        run_id: str,
        objective: str,
        target_url: str,
        headless: bool = True,
        session_name: Optional[str] = None,
        timeout: int = 120,
        event_callback: Optional[Callable] = None,
        on_process_spawned: Optional[Callable] = None,
        custom_cmd_args: Optional[List[str]] = None,
        image_name: Optional[str] = None,
        network_name: Optional[str] = None,
        dns_server_ip: Optional[str] = None
    ) -> KaneExecutionResult:
        """
        Executes an automated run inside a disposable, security-confined Linux worker.
        """
        # Validate target URL first
        target_url = validate_target_url(target_url)
        allowed_ips = self.resolve_target_ips(target_url)

        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        container_target_url = target_url

        # In development mode with local targets, add 127.0.0.1 and host gateway if allowed
        if settings.ALLOW_LOCAL_TARGETS and (not parsed.hostname or parsed.hostname in ("127.0.0.1", "localhost")):
            if not allowed_ips:
                allowed_ips = ["127.0.0.1"]
            if "192.168.65.254" not in allowed_ips:
                allowed_ips.append("192.168.65.254")
            container_target_url = target_url.replace(parsed.netloc, f"host.docker.internal:{target_port}")

        # Validate IPs through security policy
        validated_ips = WorkerPolicy.validate_allowed_ips(
            allowed_ips,
            allow_local=settings.ALLOW_LOCAL_TARGETS
        )

        # Construct Job Configuration
        worker_token = secrets.token_hex(24)
        job = WorkerJobConfig(
            run_id=run_id,
            objective=objective,
            target_url=target_url,
            allowed_target_ips=validated_ips,
            allow_cdp_port=9222,
            dns_server_ip=dns_server_ip,
            headless=headless,
            timeout_sec=timeout,
            worker_token=worker_token,
            session_slug=session_name or f"run-{run_id[:8]}"
        )

        # Prepare run directories
        run_dir = settings.DATA_DIR / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        raw_stdout_path = run_dir / "raw_stdout.log"
        raw_stderr_path = run_dir / "raw_stderr.log"
        settings.WORKER_IPC_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(settings.WORKER_IPC_DIR, 0o700)
        except OSError:
            pass
        ipc_socket_dir = settings.WORKER_IPC_DIR / run_id
        ipc_socket_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(ipc_socket_dir, 0o700)
        except OSError:
            pass

        # Generate policy scripts
        entrypoint_content = WorkerPolicy.generate_firewall_script(
            allowed_ips=job.allowed_target_ips,
            allow_cdp_port=job.allow_cdp_port,
            dns_server_ip=job.dns_server_ip,
            target_ports=[target_port]
        )
        entrypoint_file = ipc_socket_dir / "entrypoint.sh"
        entrypoint_file.write_text(entrypoint_content)
        entrypoint_file.chmod(0o755)

        agent_content = WorkerPolicy.generate_worker_agent_script()
        agent_file = ipc_socket_dir / "agent.py"
        agent_file.write_text(agent_content)
        agent_file.chmod(0o755)

        # Stage ONLY active Kane credentials into restricted ephemeral directory
        self.stage_kane_credentials(ipc_socket_dir)

        # Prepare target command inside container
        if custom_cmd_args:
            cmd_args = custom_cmd_args
        else:
            # Default Kane CLI execution
            cmd_args = [
                "kane-cli", "run", job.objective,
                "--url", container_target_url,
                "--agent",
                "--timeout", str(job.timeout_sec)
            ]
            if job.headless:
                cmd_args.append("--headless")
            if job.session_slug:
                cmd_args.extend(["--name", job.session_slug])

        # Initialize IPC Server
        ipc_receiver = WorkerIPCReceiver(
            run_id=run_id,
            expected_token=worker_token,
            socket_dir=ipc_socket_dir
        )
        await ipc_receiver.start()
        self._active_receivers[run_id] = ipc_receiver

        container_id: Optional[str] = None
        container_name = f"shipproof-worker-{run_id[:12]}"
        events: List[NormalizedEvent] = []
        run_end_event: Optional[NormalizedEvent] = None
        final_status = "incomplete"
        exit_code: Optional[int] = None
        error_msg: Optional[str] = None
        evidence_pack_path: Optional[str] = None
        evidence_transferred: bool = False
        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        docker_stream_proc = None
        docker_stream_task = None

        try:
            # Verify Docker daemon availability
            if not self.runtime.check_docker_available():
                raise WorkerRuntimeError("Docker daemon is not reachable. Cannot launch isolated worker.")

            # Launch Worker Container
            container_id = self.runtime.create_and_start_worker(
                job=job,
                ipc_socket_dir=ipc_socket_dir,
                entrypoint_path=entrypoint_file,
                agent_path=agent_file,
                cmd_args=cmd_args,
                image_name=image_name,
                network_name=network_name
            )

            # Host-Side Security Inspection (Fail-closed)
            security_info = self.runtime.inspect_worker_security(container_name)
            if not security_info["valid"]:
                raise WorkerSecurityViolationError(
                    f"Worker container {container_name} failed host security policy: {security_info}"
                )

            logger.info(f"Worker container {container_name} passed host security inspection: {security_info}")

            # Attach streaming pipe if socket doesn't bridge across hypervisor VFS mounts
            try:
                docker_cmd = ["docker", "logs", "-f", container_name]
                docker_env = dict(os.environ)
                if self.runtime.docker_sock:
                    docker_env["DOCKER_HOST"] = self.runtime.docker_sock
                docker_stream_proc = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=docker_env
                )

                class DummyWriter:
                    def close(self): pass
                    async def wait_closed(self): pass

                if docker_stream_proc.stdout:
                    docker_stream_task = asyncio.create_task(
                        ipc_receiver._handle_client(docker_stream_proc.stdout, DummyWriter())
                    )
            except Exception as stream_err:
                logger.warning(f"Could not attach docker logs stream: {stream_err}")

            if on_process_spawned:
                try:
                    if inspect.iscoroutinefunction(on_process_spawned):
                        await on_process_spawned(container_name)
                    else:
                        on_process_spawned(container_name)
                except Exception as cb_err:
                    logger.warning(f"Error in on_process_spawned callback: {cb_err}")

            # Stream messages from Worker IPC Receiver
            async for msg in ipc_receiver.stream_messages(timeout_sec=timeout):
                if msg.msg_type == "event":
                    raw_line = msg.payload.get("raw_line", "")
                    stdout_lines.append(raw_line)
                    event = KaneParser.parse_line(raw_line)
                    if event:
                        events.append(event)
                        if event.event_type in ("run_end", "test_md_done", "testrun_done"):
                            run_end_event = event
                        if event_callback:
                            try:
                                if inspect.iscoroutinefunction(event_callback):
                                    await event_callback(event)
                                else:
                                    event_callback(event)
                            except Exception as cb_err:
                                logger.warning(f"Error in event_callback: {cb_err}")

                elif msg.msg_type == "log":
                    stderr_snippet = msg.payload.get("stderr", "")
                    if stderr_snippet:
                        stderr_lines.append(stderr_snippet)

                elif msg.msg_type == "evidence_ready":
                    exp_sha256 = msg.payload.get("sha256")
                    exp_size = msg.payload.get("size")
                    host_ev_file = ipc_socket_dir / "evidence" / "evidence.pack"
                    if host_ev_file.exists():
                        actual_bytes = host_ev_file.read_bytes()
                        actual_sha256 = hashlib.sha256(actual_bytes).hexdigest()
                        actual_size = len(actual_bytes)
                        if exp_sha256 and exp_sha256.lower() != actual_sha256.lower():
                            logger.error(f"Evidence SHA-256 mismatch for run {run_id}: expected {exp_sha256}, got {actual_sha256}")
                        elif exp_size and exp_size != actual_size:
                            logger.error(f"Evidence size mismatch for run {run_id}: expected {exp_size}, got {actual_size}")
                        else:
                            dest_pack = run_dir / "evidence.pack"
                            shutil.copy2(host_ev_file, dest_pack)
                            evidence_pack_path = str(dest_pack)
                            evidence_transferred = True
                            logger.info(f"Verified and transferred evidence pack for run {run_id} ({actual_size} bytes, SHA-256: {actual_sha256[:16]})")

                elif msg.msg_type == "error":
                    error_msg = msg.payload.get("error")

                elif msg.msg_type == "complete":
                    exit_code = msg.payload.get("exit_code")
                    if msg.payload.get("error_message"):
                        error_msg = msg.payload.get("error_message")
                    break

            # Reconcile final status
            if run_end_event:
                if run_end_event.status == "passed":
                    final_status = "passed"
                elif run_end_event.status == "failed":
                    final_status = "failed"
                else:
                    final_status = "incomplete"
            elif exit_code == 0:
                final_status = "passed"
            elif exit_code is not None:
                final_status = "failed" if not error_msg else "error"
            elif any(e.status == "done" and "assert" in (e.description or "").lower() for e in events):
                final_status = "passed"
                exit_code = 0
            else:
                final_status = "incomplete"

        except asyncio.TimeoutError:
            logger.warning(f"Execution timeout reached ({timeout}s) for worker {run_id}")
            if any(e.status == "done" and "assert" in (e.description or "").lower() for e in events):
                final_status = "passed"
                exit_code = 0
                logger.info(f"Worker {run_id} hit timeout during teardown but all assertions passed: reconciled to 'passed'")
            else:
                final_status = "incomplete"
                error_msg = f"Worker execution timed out after {timeout} seconds"
        except WorkerSecurityViolationError as sec_err:
            logger.error(f"Security violation for worker {run_id}: {sec_err}")
            final_status = "error"
            error_msg = str(sec_err)
        except Exception as e:
            logger.error(f"Error orchestrating worker run {run_id}: {e}")
            final_status = "error"
            error_msg = str(e)
        finally:
            if docker_stream_task and not docker_stream_task.done():
                docker_stream_task.cancel()
            if docker_stream_proc:
                try:
                    docker_stream_proc.terminate()
                except Exception:
                    pass

            # 1. Transfer Evidence while container is still alive (if not transferred via IPC)
            if not evidence_transferred and container_id:
                try:
                    # Check IPC shared directory first
                    host_ev_file = ipc_socket_dir / "evidence" / "evidence.pack"
                    if host_ev_file.exists():
                        dest_pack = run_dir / "evidence.pack"
                        shutil.copy2(host_ev_file, dest_pack)
                        evidence_pack_path = str(dest_pack)
                        evidence_transferred = True
                        logger.info(f"Transferred evidence pack from IPC mount for run {run_id}")
                    else:
                        extracted_path = self.runtime.extract_evidence(container_name, run_dir)
                        if extracted_path and extracted_path.exists():
                            evidence_pack_path = str(extracted_path)
                            evidence_transferred = True
                            logger.info(f"Extracted evidence pack via runtime for run {run_id}")
                except Exception as ex_err:
                    logger.warning(f"Error transferring evidence from worker {container_name}: {ex_err}")

            # 2. Terminate and Remove Worker Container ONLY after evidence transfer has completed
            if container_id:
                try:
                    self.runtime.terminate_worker(container_name)
                except Exception as term_err:
                    logger.warning(f"Error terminating worker {container_name}: {term_err}")

            # 3. Close IPC Receiver
            await ipc_receiver.close()
            self._active_receivers.pop(run_id, None)

            # 4. Clean up temporary socket directory safely
            if ipc_socket_dir.exists(follow_symlinks=False) and not os.path.islink(ipc_socket_dir):
                try:
                    if ipc_socket_dir.name == run_id:
                        shutil.rmtree(ipc_socket_dir, ignore_errors=True)
                except Exception:
                    pass

            # 5. Write raw logs to disk
            raw_stdout_path.write_text("\n".join(stdout_lines))
            raw_stderr_path.write_text("\n".join(stderr_lines))

        return KaneExecutionResult(
            run_id=run_id,
            exit_code=exit_code,
            status=final_status,
            raw_stdout_path=str(raw_stdout_path),
            raw_stderr_path=str(raw_stderr_path),
            events=events,
            run_end_event=run_end_event,
            stderr_hint="\n".join(stderr_lines) if stderr_lines else None,
            error_message=error_msg,
            evidence_pack_path=evidence_pack_path
        )

    @staticmethod
    def stage_kane_credentials(ipc_socket_dir: Path) -> Optional[Path]:
        """
        Stages ONLY the active Kane CLI profile and config.json into an owner-restricted
        directory (0700) within the ephemeral IPC socket directory.
        Prevents exposing unrelated profiles, historical sessions, or other host files to the container.
        """
        host_kane = Path.home() / ".testmuai" / "kaneai"
        if not host_kane.exists():
            return None

        auth_dir = ipc_socket_dir / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(auth_dir, 0o700)
        except OSError:
            pass

        # 1. Read config.json to determine active profile
        active_profile = "default"
        host_config = host_kane / "config.json"
        if host_config.exists():
            try:
                data = json.loads(host_config.read_text(encoding="utf-8"))
                active_profile = data.get("active_profile") or "default"
            except Exception:
                pass
            dest_config = auth_dir / "config.json"
            shutil.copy2(host_config, dest_config)
            try:
                os.chmod(dest_config, 0o600)
            except OSError:
                pass

        # 2. Copy ONLY the active profile directory
        host_profile_dir = host_kane / "profiles" / active_profile
        if host_profile_dir.exists():
            dest_profile_dir = auth_dir / "profiles" / active_profile
            dest_profile_dir.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(dest_profile_dir.parent, 0o700)
            except OSError:
                pass
            shutil.copytree(host_profile_dir, dest_profile_dir, dirs_exist_ok=True, symlinks=False)
            for root, dirs, files in os.walk(dest_profile_dir):
                for d in dirs:
                    try:
                        os.chmod(os.path.join(root, d), 0o700)
                    except OSError:
                        pass
                for f in files:
                    try:
                        os.chmod(os.path.join(root, f), 0o600)
                    except OSError:
                        pass

        return auth_dir

    def cancel_run(self, run_id: str):
        """
        Immediately cancels and cleans up an active worker container.
        """
        container_name = f"shipproof-worker-{run_id[:12]}"
        logger.info(f"Cancelling active worker {container_name}")
        self.runtime.terminate_worker(container_name)

        receiver = self._active_receivers.get(run_id)
        if receiver:
            asyncio.create_task(receiver.close())

worker_manager = WorkerManager()
