from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def get_utc_now():
    return datetime.now(timezone.utc)

class ProjectEntity(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    target_url = Column(String(1024), nullable=False)
    repo_path = Column(String(1024), nullable=True)
    framework = Column(String(100), default="Next.js")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    runs = relationship("VerificationRunEntity", back_populates="project", cascade="all, delete-orphan")


class VerificationRunEntity(Base):
    __tablename__ = "verification_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    objective = Column(Text, nullable=False)
    target_url = Column(String(1024), nullable=False)
    
    # Status: queued, running, passed, failed, error, cancelled, incomplete
    status = Column(String(50), default="queued", nullable=False)
    
    # Mode: verify_only, closed_loop, dry_run
    mode = Column(String(50), default="closed_loop", nullable=False)
    
    # Kane execution metadata
    kane_session_id = Column(String(128), nullable=True)
    execution_id = Column(String(128), nullable=True)
    evidence_pack_path = Column(String(1024), nullable=True)
    exit_code = Column(Integer, nullable=True)
    raw_stdout_path = Column(String(1024), nullable=True)
    raw_stderr_path = Column(String(1024), nullable=True)
    total_steps = Column(Integer, default=0)
    passed_steps = Column(Integer, default=0)
    failed_steps = Column(Integer, default=0)
    failure_reason = Column(Text, nullable=True)
    
    # Autonomous repair tracking
    repaired = Column(Boolean, default=False)
    repair_attempts = Column(Integer, default=0)
    verification_proof = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    completed_at = Column(DateTime, nullable=True)

    project = relationship("ProjectEntity", back_populates="runs")
    steps = relationship("VerificationStepEntity", back_populates="run", cascade="all, delete-orphan", order_by="VerificationStepEntity.step_index")
    repairs = relationship("RepairRecordEntity", back_populates="run", cascade="all, delete-orphan", order_by="RepairRecordEntity.attempt_number")
    events = relationship("VerificationEventEntity", back_populates="run", cascade="all, delete-orphan", order_by="VerificationEventEntity.event_seq")


class VerificationEventEntity(Base):
    __tablename__ = "verification_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("verification_runs.id", ondelete="CASCADE"), nullable=False)
    event_seq = Column(Integer, default=1, nullable=False)
    event_type = Column(String(50), nullable=False)
    step_number = Column(Integer, nullable=True)
    status = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    raw_event = Column(Text, nullable=False)
    created_at = Column(DateTime, default=get_utc_now)

    run = relationship("VerificationRunEntity", back_populates="events")


class VerificationStepEntity(Base):
    __tablename__ = "verification_steps"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("verification_runs.id", ondelete="CASCADE"), nullable=False)
    step_index = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False)
    remark = Column(Text, nullable=False)
    screenshot_path = Column(String(1024), nullable=True)
    annotated_screenshot_path = Column(String(1024), nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Float, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    run = relationship("VerificationRunEntity", back_populates="steps")


class RepairRecordEntity(Base):
    __tablename__ = "repair_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id = Column(String(36), ForeignKey("verification_runs.id", ondelete="CASCADE"), nullable=False)
    attempt_number = Column(Integer, default=1, nullable=False)
    failing_step_index = Column(Integer, nullable=True)
    
    # State machine: CREATED -> JOB_PUBLISHED -> AWAITING_AGENT -> AGENT_RESPONSE_RECEIVED -> AWAITING_APPROVAL -> APPLYING -> VALIDATING -> RETESTING -> VERIFIED / UNRESOLVED / FAILED / CANCELLED
    status = Column(String(50), default="CREATED", nullable=False)
    execution_mode = Column(String(50), default="ide_mediated", nullable=False)
    
    diagnosis = Column(Text, nullable=True)
    files_modified = Column(Text, nullable=True)  # JSON list
    patch_diff = Column(Text, nullable=True)
    git_commit_before = Column(String(64), nullable=True)
    git_commit_after = Column(String(64), nullable=True)
    repair_packet_json = Column(Text, nullable=True)  # Full repair packet payload
    
    # Verification retest linkage
    retest_run_id = Column(String(36), nullable=True)
    retest_passed = Column(Boolean, default=False)
    failure_notes = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)
    completed_at = Column(DateTime, nullable=True)

    run = relationship("VerificationRunEntity", back_populates="repairs")
    events = relationship("RepairEventEntity", back_populates="repair", cascade="all, delete-orphan", order_by="RepairEventEntity.created_at")


class RepairEventEntity(Base):
    __tablename__ = "repair_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repair_id = Column(String(36), ForeignKey("repair_records.id", ondelete="CASCADE"), nullable=False)
    from_state = Column(String(50), nullable=True)
    to_state = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    raw_payload = Column(Text, nullable=True)  # Stored JSON
    created_at = Column(DateTime, default=get_utc_now)

    repair = relationship("RepairRecordEntity", back_populates="events")
