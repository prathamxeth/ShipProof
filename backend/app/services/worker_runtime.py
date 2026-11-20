import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from backend.app.schemas.worker import WorkerJobConfig
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger("worker_runtime")

class WorkerRuntimeError(Exception):
    pass

class WorkerRuntime:
    """
    Manages ephemeral Docker container lifecycles from the trusted host.
    Applies strict security flags, performs host-side security inspection,
    extracts evidence archives, and terminates containers reliably.
    """

    def __init__(self, docker_sock: Optional[str] = None):
        self.docker_sock = docker_sock or settings.WORKER_DOCKER_SOCKET
        self.env = dict(os.environ)
        if self.docker_sock:
            self.env["DOCKER_HOST"] = self.docker_sock

    def _run_docker(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        cmd = ["docker"] + args
        try:
            res = subprocess.run(cmd, env=self.env, capture_output=True, text=True)
            if check and res.returncode != 0:
                raise WorkerRuntimeError(
                    f"Docker command failed ({res.returncode}): {' '.join(cmd)}\nSTDERR: {res.stderr}\nSTDOUT: {res.stdout}"
                )
            return res
        except FileNotFoundError:
            raise WorkerRuntimeError("Docker CLI binary 'docker' not found on system PATH.")

    def check_docker_available(self) -> bool:
        """
        Checks whether Docker daemon is active and responsive.
        """
        res = self._run_docker(["info"], check=False)
        return res.returncode == 0

    def check_image_exists(self, image_name: str) -> bool:
        """
        Verifies the container image is available locally.
        """
        res = self._run_docker(["image", "inspect", image_name], check=False)
        return res.returncode == 0

    def create_and_start_worker(
        self,
        job: WorkerJobConfig,
        ipc_socket_dir: Path,
        entrypoint_path: Path,
        agent_path: Path,
        cmd_args: List[str],
        image_name: Optional[str] = None,
        network_name: Optional[str] = None
    ) -> str:
        """
        Launches worker container with all mandatory security flags.
        """
        image = image_name or settings.WORKER_IMAGE
        container_name = f"shipproof-worker-{job.run_id[:12]}"

        # Pre-clean if container with same name exists
        self.terminate_worker(container_name)

        docker_cmd = [
            "run", "-d",
            "--name", container_name,
            "--label", "shipproof.managed=true",
            "--label", f"shipproof.run_id={job.run_id}",
            "--cap-add=NET_ADMIN",
            "--security-opt=no-new-privileges:true",
            f"--memory={settings.WORKER_MEMORY_LIMIT}",
            f"--cpus={settings.WORKER_CPU_LIMIT}",
            f"--pids-limit={settings.WORKER_PIDS_LIMIT}",
            "--read-only",
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--tmpfs", "/dev/shm:rw,nosuid,size=64m",
            "--tmpfs", "/home/kane:rw,exec,nosuid,size=1024m",
            "-e", f"RUN_ID={job.run_id}",
            "-e", f"WORKER_TOKEN={job.worker_token}",
            "-e", f"ALLOWED_TARGET_IPS={' '.join(job.allowed_target_ips)}",
            "-e", f"ALLOW_CDP_PORT={job.allow_cdp_port}",
            "-e", "HOME=/home/kane",
            "-e", "KANE_CLI_CHROME_PATH=/usr/bin/chromium",
            "-v", f"{ipc_socket_dir}:/ipc:rw",
            "-v", f"{entrypoint_path}:/workspace/entrypoint.sh:ro",
            "-v", f"{agent_path}:/workspace/agent.py:ro"
        ]

        # Securely mount Kane CLI profile/credentials: prefer narrowed staging if present
        staged_auth = ipc_socket_dir / "auth"
        if staged_auth.exists():
            docker_cmd.extend(["-v", f"{staged_auth}:/kane-auth:ro"])
        else:
            kane_auth_dir = Path.home() / ".testmuai" / "kaneai"
            if kane_auth_dir.exists():
                docker_cmd.extend(["-v", f"{kane_auth_dir}:/kane-auth:ro"])

        if network_name:
            docker_cmd.extend(["--network", network_name])

        if job.dns_server_ip:
            docker_cmd.extend(["--dns", job.dns_server_ip])

        # Target command inside worker
        target_payload = ["python3", "/workspace/agent.py"] + cmd_args
        docker_cmd.append(image)
        docker_cmd.extend(["bash", "/workspace/entrypoint.sh"] + target_payload)

        logger.info(f"Launching worker container {container_name} for run {job.run_id}")
        res = self._run_docker(docker_cmd)
        container_id = res.stdout.strip()
        return container_id

    def inspect_worker_security(self, container_name_or_id: str) -> Dict[str, Any]:
        """
        Inspects effective container configuration from the trusted host side.
        Fails closed if security flags are missing.
        """
        res = self._run_docker(["inspect", container_name_or_id])
        data = json.loads(res.stdout)[0]
        host_config = data.get("HostConfig", {})
        mounts = data.get("Mounts", [])

        # Security Checks
        readonly_root = host_config.get("ReadonlyRootfs", False)
        security_opts = host_config.get("SecurityOpt", [])
        no_new_privs = any("no-new-privileges" in opt.lower() for opt in (security_opts or []))
        memory = host_config.get("Memory", 0)
        pids_limit = host_config.get("PidsLimit", 0)

        # Mount Checks (Must NOT mount docker socket or host DB)
        has_docker_sock = any("/var/run/docker.sock" in m.get("Source", "") for m in mounts)
        has_host_db = any("shipproof.db" in m.get("Source", "") for m in mounts)

        is_valid = readonly_root and no_new_privs and (not has_docker_sock) and (not has_host_db)

        return {
            "valid": is_valid,
            "readonly_root": readonly_root,
            "no_new_privs": no_new_privs,
            "memory": memory,
            "pids_limit": pids_limit,
            "has_docker_sock": has_docker_sock,
            "has_host_db": has_host_db,
            "mount_count": len(mounts)
        }

    def extract_evidence(self, container_name_or_id: str, host_dest_dir: Path) -> Optional[Path]:
        """
        Extracts evidence archive or directory from container tmpfs/workspace.
        """
        host_dest_dir.mkdir(parents=True, exist_ok=True)
        # Attempt to copy .kane session directory or tmpfs evidence
        copy_res = self._run_docker(
            ["cp", f"{container_name_or_id}:/tmp/evidence", str(host_dest_dir)],
            check=False
        )
        if copy_res.returncode == 0:
            return host_dest_dir / "evidence"

        # Check for Kane sessions directory
        copy_sessions = self._run_docker(
            ["cp", f"{container_name_or_id}:/home/kane/.testmuai/kaneai/sessions", str(host_dest_dir)],
            check=False
        )
        if copy_sessions.returncode == 0:
            import shutil
            for ev_file in (host_dest_dir / "sessions").glob("*/evidence/*.evidence"):
                shutil.copy2(ev_file, host_dest_dir / ev_file.name)
                return host_dest_dir / ev_file.name
            return host_dest_dir / "sessions"

        # Alternative: check for .kane output
        copy_kane = self._run_docker(
            ["cp", f"{container_name_or_id}:/workspace/.kane", str(host_dest_dir)],
            check=False
        )
        if copy_kane.returncode == 0:
            return host_dest_dir / ".kane"

        return None

    def terminate_worker(self, container_name_or_id: str):
        """
        Forcibly removes worker container.
        """
        self._run_docker(["rm", "-f", container_name_or_id], check=False)
        logger.info(f"Terminated worker container {container_name_or_id}")

    def recover_orphans(self) -> List[str]:
        """
        Discovers and cleans up lingering worker containers with label shipproof.managed=true.
        """
        res = self._run_docker(
            ["ps", "-a", "--filter", "label=shipproof.managed=true", "--format", "{{.Names}}"],
            check=False
        )
        orphans = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        for name in orphans:
            logger.info(f"Cleaning up orphan worker container: {name}")
            self.terminate_worker(name)
        return orphans
