from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone

class WorkerJobConfig(BaseModel):
    """
    Job specification passed from trusted host to worker container.
    Contains only the minimal necessary parameters for execution.
    Zero host secrets or unnecessary environment configuration.
    """
    run_id: str
    objective: str
    target_url: str
    allowed_target_ips: List[str] = Field(default_factory=list)
    allow_cdp_port: int = Field(default=9222)
    dns_server_ip: Optional[str] = None
    headless: bool = Field(default=True)
    timeout_sec: int = Field(default=120)
    worker_token: str
    session_slug: Optional[str] = None


class WorkerIPCMessage(BaseModel):
    """
    Structured IPC frame for communication over the UNIX domain socket.
    Strictly validated with bounded frame ceiling.
    """
    msg_type: Literal["handshake", "event", "log", "complete", "error", "heartbeat", "evidence_ready"]
    run_id: str
    worker_token: str
    seq: int = Field(ge=0)
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkerContainerSpec(BaseModel):
    """
    Container creation specification enforced by the trusted host.
    """
    container_name: str
    image: str
    memory_limit: str = "2048m"
    cpu_limit: str = "2.0"
    pids_limit: int = 200
    read_only: bool = True
    no_new_privs: bool = True
    drop_caps: bool = True
    labels: Dict[str, str] = Field(default_factory=dict)
    env: Dict[str, str] = Field(default_factory=dict)
    mounts: List[str] = Field(default_factory=list)
    tmpfs_mounts: Dict[str, str] = Field(default_factory=dict)
