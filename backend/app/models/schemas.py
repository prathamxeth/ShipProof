from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

# --- Health Schemas ---
class HealthResponse(BaseModel):
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
    app: str = Field(default="ShipProof")
    version: str = Field(default="0.1.0")
    database: str = Field(default="connected")
    kane_cli_installed: bool = Field(default=True)
    agy_cli_installed: bool = Field(default=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- Event Schemas ---
class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    event_seq: Optional[int] = 1
    event_type: str
    step_number: Optional[int] = None
    status: Optional[str] = None
    description: Optional[str] = None
    raw_event: Optional[Dict[str, Any]] = None
    created_at: datetime


# --- Step & Evidence Schemas ---
class StepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    step_index: int
    status: str  # running, done, failed
    remark: str
    screenshot_path: Optional[str] = None
    annotated_screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    created_at: datetime


class EvidenceArtifact(BaseModel):
    step_index: Optional[int] = None
    artifact_type: str  # screenshot, annotated_screenshot, failure_yaml, console_log, network_har
    filename: str
    relative_path: str
    file_size_bytes: int


class EvidenceResponse(BaseModel):
    run_id: str
    pack_path: Optional[str] = None
    execution_id: Optional[str] = None
    extracted_dir: Optional[str] = None
    has_evidence: bool = False
    has_failure_yaml: bool = False
    failure_details: Optional[Dict[str, Any]] = None
    artifacts: List[EvidenceArtifact] = []
    console_errors_count: int = 0
    network_failures_count: int = 0


# --- Repair Schemas ---
class RepairPacketModel(BaseModel):
    run_id: str
    kane_session_id: Optional[str] = None
    target_url: str
    objective: str
    failed_step: Optional[int] = None
    failure_message: Optional[str] = None
    failure_yaml: Optional[Dict[str, Any]] = None
    screenshot_paths: List[str] = []
    console_errors: List[Dict[str, Any]] = []
    network_errors: List[Dict[str, Any]] = []
    project_dir: str
    relevant_files: List[str] = []
    git_commit_before: Optional[str] = None
    execution_mode: str = "ide_mediated"
    created_at: str


class RepairCreate(BaseModel):
    run_id: str = Field(..., description="Failed verification run ID to repair")
    max_retries: Optional[int] = Field(default=3, ge=1, le=5)
    auto_approve: Optional[bool] = Field(default=False, description="Automatically approve proposed repairs")


class RepairEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repair_id: str
    from_state: Optional[str] = None
    to_state: str
    description: Optional[str] = None
    raw_payload: Optional[Dict[str, Any]] = None
    created_at: datetime


class RepairSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    attempt_number: int
    status: str
    execution_mode: str = "ide_mediated"
    diagnosis: Optional[str] = None
    git_commit_before: Optional[str] = None
    git_commit_after: Optional[str] = None
    retest_run_id: Optional[str] = None
    retest_passed: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class RepairDetailResponse(RepairSummaryResponse):
    failing_step_index: Optional[int] = None
    files_modified: Optional[List[str]] = None
    patch_diff: Optional[str] = None
    repair_packet: Optional[RepairPacketModel] = None
    prompt_markdown: Optional[str] = None
    job_directory: Optional[str] = None
    failure_notes: Optional[str] = None
    events: List[RepairEventResponse] = []


class RepairApproveRequest(BaseModel):
    rationale: Optional[str] = Field(default="Approved by user in ShipProof Repair Studio")


class RepairApproveResponse(BaseModel):
    repair_id: str
    status: str
    message: str


# --- Project Schemas ---
class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, json_schema_extra={"example": "E-Commerce Store"})
    target_url: str = Field(..., json_schema_extra={"example": "http://localhost:3000"})
    repo_path: Optional[str] = Field(default=None, json_schema_extra={"example": "/Users/pratham/Projects/ShipProof/demo_targets/store"})
    framework: Optional[str] = Field(default="Next.js", json_schema_extra={"example": "Next.js"})
    description: Optional[str] = Field(default=None, json_schema_extra={"example": "Online storefront with cart and checkout"})


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    target_url: str
    repo_path: Optional[str] = None
    framework: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# --- Verification Run Schemas ---
class RunCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, json_schema_extra={"example": "Cart Checkout Flow Verification"})
    objective: str = Field(
        ...,
        min_length=3,
        json_schema_extra={
            "example": "Open homepage, add 'Wireless Headphones' to cart, go to checkout, assert confirmation page displays order ID"
        }
    )
    target_url: Optional[str] = Field(default=None, json_schema_extra={"example": "http://localhost:3000"})
    project_id: Optional[str] = Field(default=None, json_schema_extra={"example": "project-uuid"})
    mode: Optional[str] = Field(
        default="closed_loop",
        description="Execution mode: 'closed_loop' (auto-repair on fail), 'verify_only', or 'dry_run'",
        json_schema_extra={"example": "closed_loop"}
    )
    headless: Optional[bool] = Field(default=True, description="Run browser headlessly")
    timeout: Optional[int] = Field(default=120, ge=10, le=600, description="Process timeout in seconds")


class RunSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: Optional[str] = None
    title: str
    objective: str
    target_url: str
    status: str
    mode: str
    kane_session_id: Optional[str] = None
    total_steps: int
    passed_steps: int
    failed_steps: int
    exit_code: Optional[int] = None
    repaired: bool
    repair_attempts: int
    created_at: datetime
    completed_at: Optional[datetime] = None


class RunDetailResponse(RunSummaryResponse):
    execution_id: Optional[str] = None
    evidence_pack_path: Optional[str] = None
    failure_reason: Optional[str] = None
    verification_proof: Optional[str] = None
    steps: List[StepResponse] = []
    repairs: List[RepairSummaryResponse] = []
    events_count: int = 0


class PaginatedRunsResponse(BaseModel):
    items: List[RunSummaryResponse]
    total: int
    limit: int
    offset: int


class CancelResponse(BaseModel):
    run_id: str
    status: str
    message: str


# --- Overview & Stats Schemas ---
class OverviewStatsResponse(BaseModel):
    total_runs: int = 0
    passed_runs: int = 0
    failed_runs: int = 0
    verified_runs: int = 0
    running_runs: int = 0
    cancelled_or_incomplete_runs: int = 0
    total_repairs: int = 0
    repairs_verified: int = 0
    repairs_awaiting_approval: int = 0
    repairs_in_progress: int = 0
    total_projects: int = 0
    recent_runs: List[RunSummaryResponse] = []
    recent_repairs: List[RepairSummaryResponse] = []
