import asyncio
import json
import os
import re
import stat
import shutil
from pathlib import Path
from typing import Optional, AsyncGenerator, Dict, Any, List
from backend.app.schemas.worker import WorkerIPCMessage
from backend.app.core.logging import get_logger

logger = get_logger("worker_ipc")

MAX_FRAME_SIZE = 65536  # 64 KB
MAX_QUEUE_CAPACITY = 1000

class WorkerIPCReceiver:
    """
    Host-side UNIX domain socket server for a single worker execution run.
    Enforces authenticated worker-to-host IPC, 64 KB message framing, schema validation,
    monotonic sequence ordering, and backpressure queue bounds.
    """

    def __init__(self, run_id: str, expected_token: str, socket_dir: Path):
        if not run_id or not re.match(r"^[a-zA-Z0-9_\-]+$", run_id):
            raise ValueError(f"Invalid run_id for worker IPC: '{run_id}'")
        self.run_id = run_id
        self.expected_token = expected_token
        self.raw_socket_dir = Path(socket_dir)
        if self.raw_socket_dir.is_symlink():
            raise ValueError(f"Socket directory cannot be a symbolic link: {self.raw_socket_dir}")
        self.socket_dir = self.raw_socket_dir.resolve()
        self.socket_path = self.socket_dir / "worker.sock"
        self.queue: asyncio.Queue[WorkerIPCMessage] = asyncio.Queue(maxsize=MAX_QUEUE_CAPACITY)
        self.server: Optional[asyncio.Server] = None
        self.is_authenticated = False
        self.last_seq = -1
        self.is_closed = False
        self.raw_logs: List[str] = []
        self._complete_event = asyncio.Event()
        self.exit_code: Optional[int] = None
        self.error_message: Optional[str] = None

    async def start(self):
        """
        Starts listening on the UNIX domain socket with restrictive host permissions.
        """
        # 1. Prevent symlink traversal on socket_dir
        if self.raw_socket_dir.is_symlink() or (self.socket_dir.exists(follow_symlinks=False) and os.path.islink(self.socket_dir)):
            raise ValueError(f"Socket directory cannot be a symbolic link: {self.socket_dir}")

        # 2. Ensure parent and socket directory are owner-restricted (0700)
        parent_dir = self.socket_dir.parent
        parent_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(parent_dir, 0o700)
        except OSError:
            pass

        self.socket_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.socket_dir, 0o700)
        except OSError:
            pass

        # 3. Check existing socket_path: reject symlinks and non-sockets
        if self.socket_path.exists(follow_symlinks=False):
            if os.path.islink(self.socket_path):
                raise ValueError(f"Symlink substitution detected at socket path: {self.socket_path}")
            st = os.lstat(self.socket_path)
            if not stat.S_ISSOCK(st.st_mode):
                raise ValueError(f"Path exists and is not a socket file: {self.socket_path}")
            self.socket_path.unlink()

        # 4. Start UNIX domain socket server
        self.server = await asyncio.start_unix_server(
            self._handle_client,
            path=str(self.socket_path)
        )

        # 5. Restrict socket permissions to owner-only (0600)
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError:
            pass

        logger.info(f"Worker IPC server listening on {self.socket_path} for run {self.run_id} (mode 0600, dir 0700)")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """
        Processes worker messages line-by-line over the authenticated stream.
        """
        buffer = bytearray()
        try:
            while not reader.at_eof() and not self.is_closed:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buffer.extend(chunk)

                # Check frame size before newline
                if b"\n" not in buffer and len(buffer) > MAX_FRAME_SIZE:
                    logger.warning(f"Worker IPC frame exceeded {MAX_FRAME_SIZE} bytes. Rejecting connection.")
                    self.error_message = "FRAME_SIZE_EXCEEDED"
                    break

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if len(line) > MAX_FRAME_SIZE:
                        logger.warning(f"Worker IPC message line exceeded {MAX_FRAME_SIZE} bytes.")
                        self.error_message = "FRAME_SIZE_EXCEEDED"
                        break

                    line_str = line.decode("utf-8", errors="replace").strip()
                    if not line_str:
                        continue
                    if not line_str.startswith("{"):
                        continue

                    # Validate schema
                    try:
                        msg_dict = json.loads(line_str)
                        msg = WorkerIPCMessage.model_validate(msg_dict)
                    except Exception as parse_err:
                        logger.warning(f"Malformed Worker IPC frame received: {parse_err}")
                        continue

                    # Validate Run ID
                    if msg.run_id != self.run_id:
                        logger.warning(f"Worker IPC Run ID mismatch: expected {self.run_id}, got {msg.run_id}")
                        continue

                    # Validate Worker Token (Authenticated Worker-to-Host IPC)
                    if msg.worker_token != self.expected_token:
                        logger.warning("Worker IPC token authentication failed!")
                        self.error_message = "AUTHENTICATION_FAILED"
                        break

                    # Handle Handshake
                    if msg.msg_type == "handshake":
                        self.is_authenticated = True
                        self.last_seq = msg.seq
                        logger.info(f"Worker {self.run_id} authenticated successfully.")
                        continue

                    if not self.is_authenticated:
                        logger.warning("Message received before handshake authentication. Dropping.")
                        continue

                    # Enforce Monotonic Sequence Ordering (Reject duplicate / stale messages)
                    if msg.seq <= self.last_seq:
                        logger.warning(f"Duplicate or stale IPC sequence {msg.seq} <= {self.last_seq}. Dropping.")
                        continue
                    self.last_seq = msg.seq

                    # Handle Completion or Error
                    if msg.msg_type == "complete":
                        self.exit_code = msg.payload.get("exit_code")
                        self.error_message = msg.payload.get("error_message")
                        self._complete_event.set()
                    elif msg.msg_type == "error":
                        self.error_message = msg.payload.get("error")

                    # Enqueue for host consumer
                    try:
                        self.queue.put_nowait(msg)
                    except asyncio.QueueFull:
                        logger.warning("Worker IPC queue capacity saturated; dropping message.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in Worker IPC stream: {e}")
        finally:
            self._complete_event.set()
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def stream_messages(self, timeout_sec: float = 120.0) -> AsyncGenerator[WorkerIPCMessage, None]:
        """
        Yields validated IPC messages from the queue until complete or timeout.
        """
        start_time = asyncio.get_running_loop().time()
        while not self.is_closed:
            elapsed = asyncio.get_running_loop().time() - start_time
            remaining = timeout_sec - elapsed
            if remaining <= 0:
                raise asyncio.TimeoutError(f"Worker IPC execution timed out after {timeout_sec}s")

            try:
                msg = await asyncio.wait_for(self.queue.get(), timeout=min(remaining, 1.0))
                yield msg
                if msg.msg_type == "complete":
                    break
            except asyncio.TimeoutError:
                if self._complete_event.is_set() and self.queue.empty():
                    break

    async def close(self):
        """
        Shuts down server and safely cleans up only this specific socket file and directory.
        """
        self.is_closed = True
        self._complete_event.set()
        if self.server:
            self.server.close()
            try:
                await self.server.wait_closed()
            except Exception:
                pass

        # Safe socket removal: verify path identity, never follow symlinks
        if self.socket_path.exists(follow_symlinks=False):
            if not os.path.islink(self.socket_path):
                try:
                    st = os.lstat(self.socket_path)
                    if stat.S_ISSOCK(st.st_mode):
                        self.socket_path.unlink()
                except Exception as e:
                    logger.warning(f"Could not unlink socket {self.socket_path}: {e}")
            else:
                logger.warning(f"Refusing to unlink symlink at socket path {self.socket_path}")

        # Remove socket_dir only if it is strictly within its parent and not a symlink
        if self.socket_dir.exists(follow_symlinks=False) and not os.path.islink(self.socket_dir):
            try:
                # Only remove if directory belongs to this run
                if self.socket_dir.name == self.run_id:
                    shutil.rmtree(self.socket_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not remove socket directory {self.socket_dir}: {e}")
