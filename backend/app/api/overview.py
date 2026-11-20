from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from backend.app.core.database import get_db
from backend.app.models.entities import VerificationRunEntity, RepairRecordEntity, ProjectEntity
from backend.app.models.schemas import OverviewStatsResponse, RunSummaryResponse, RepairSummaryResponse
from backend.app.core.logging import get_logger
from backend.app.core.auth import verify_auth
from backend.app.core.sanitizer import (
    sanitize_filesystem_path,
    sanitize_kane_session_id,
    sanitize_user_identifier
)

router = APIRouter(prefix="/overview", tags=["Overview"])
logger = get_logger("api.overview")

@router.get("", response_model=OverviewStatsResponse, summary="Get aggregate system overview statistics", dependencies=[Depends(verify_auth)])
async def get_overview_stats(db: AsyncSession = Depends(get_db)):
    # 1. Total runs count
    total_runs_q = await db.execute(select(func.count()).select_from(VerificationRunEntity))
    total_runs = total_runs_q.scalar() or 0

    # 2. Runs by status
    passed_runs_q = await db.execute(
        select(func.count()).select_from(VerificationRunEntity).where(VerificationRunEntity.status == "passed")
    )
    passed_runs = passed_runs_q.scalar() or 0

    verified_runs_q = await db.execute(
        select(func.count()).select_from(VerificationRunEntity).where(VerificationRunEntity.status == "verified")
    )
    verified_runs = verified_runs_q.scalar() or 0

    failed_runs_q = await db.execute(
        select(func.count()).select_from(VerificationRunEntity).where(VerificationRunEntity.status == "failed")
    )
    failed_runs = failed_runs_q.scalar() or 0

    running_runs_q = await db.execute(
        select(func.count()).select_from(VerificationRunEntity).where(VerificationRunEntity.status.in_(["running", "queued"]))
    )
    running_runs = running_runs_q.scalar() or 0

    cancelled_runs_q = await db.execute(
        select(func.count()).select_from(VerificationRunEntity).where(
            VerificationRunEntity.status.in_(["cancelled", "incomplete", "error"])
        )
    )
    cancelled_runs = cancelled_runs_q.scalar() or 0

    # 3. Repairs count
    total_repairs_q = await db.execute(select(func.count()).select_from(RepairRecordEntity))
    total_repairs = total_repairs_q.scalar() or 0

    verified_repairs_q = await db.execute(
        select(func.count()).select_from(RepairRecordEntity).where(RepairRecordEntity.status == "VERIFIED")
    )
    repairs_verified = verified_repairs_q.scalar() or 0

    awaiting_approval_q = await db.execute(
        select(func.count()).select_from(RepairRecordEntity).where(
            RepairRecordEntity.status.in_(["AWAITING_APPROVAL", "AGENT_RESPONSE_RECEIVED"])
        )
    )
    repairs_awaiting_approval = awaiting_approval_q.scalar() or 0

    in_progress_repairs_q = await db.execute(
        select(func.count()).select_from(RepairRecordEntity).where(
            RepairRecordEntity.status.in_([
                "CREATED", "JOB_PUBLISHED", "AWAITING_AGENT", "APPLYING", "VALIDATING", "RETESTING"
            ])
        )
    )
    repairs_in_progress = in_progress_repairs_q.scalar() or 0

    # 4. Total projects
    total_projects_q = await db.execute(select(func.count()).select_from(ProjectEntity))
    total_projects = total_projects_q.scalar() or 0

    # 5. Recent runs
    recent_runs_q = await db.execute(
        select(VerificationRunEntity)
        .order_by(VerificationRunEntity.created_at.desc())
        .limit(5)
    )
    recent_runs = recent_runs_q.scalars().all()

    # 6. Recent repairs
    recent_repairs_q = await db.execute(
        select(RepairRecordEntity)
        .order_by(RepairRecordEntity.created_at.desc())
        .limit(5)
    )
    recent_repairs = recent_repairs_q.scalars().all()

    # Map project names
    proj_res = await db.execute(select(ProjectEntity.id, ProjectEntity.name))
    proj_map = {row[0]: row[1] for row in proj_res.all()}

    # Map run to project name for repairs
    run_proj_q = await db.execute(
        select(VerificationRunEntity.id, VerificationRunEntity.project_id)
    )
    run_to_proj_id = {row[0]: row[1] for row in run_proj_q.all()}

    safe_recent_runs = [
        RunSummaryResponse(
            id=r.id,
            project_id=r.project_id,
            project_name=proj_map.get(r.project_id, "Standalone / Ad-Hoc"),
            title=r.title,
            objective=r.objective,
            target_url=r.target_url,
            status=r.status,
            mode=r.mode,
            kane_session_id=sanitize_kane_session_id(r.kane_session_id),
            total_steps=r.total_steps,
            passed_steps=r.passed_steps,
            failed_steps=r.failed_steps,
            exit_code=r.exit_code,
            repaired=r.repaired,
            repair_attempts=r.repair_attempts,
            created_at=r.created_at,
            completed_at=r.completed_at
        )
        for r in recent_runs
    ]

    safe_recent_repairs = [
        RepairSummaryResponse(
            id=rep.id,
            run_id=rep.run_id,
            project_name=proj_map.get(run_to_proj_id.get(rep.run_id), "Standalone / Ad-Hoc"),
            attempt_number=rep.attempt_number,
            status=rep.status,
            execution_mode=rep.execution_mode or "ide_mediated",
            diagnosis=rep.diagnosis,
            git_commit_before=rep.git_commit_before,
            git_commit_after=rep.git_commit_after,
            retest_run_id=rep.retest_run_id,
            retest_passed=rep.retest_passed,
            approved_by_user_id=sanitize_user_identifier(rep.approved_by_user_id),
            approved_at=rep.approved_at,
            approved_diff_hash=rep.approved_diff_hash,
            approval_decision=rep.approval_decision,
            created_at=rep.created_at,
            updated_at=rep.updated_at,
            completed_at=rep.completed_at
        )
        for rep in recent_repairs
    ]

    return OverviewStatsResponse(
        total_runs=total_runs,
        passed_runs=passed_runs,
        failed_runs=failed_runs,
        verified_runs=verified_runs,
        running_runs=running_runs,
        cancelled_or_incomplete_runs=cancelled_runs,
        total_repairs=total_repairs,
        repairs_verified=repairs_verified,
        repairs_awaiting_approval=repairs_awaiting_approval,
        repairs_in_progress=repairs_in_progress,
        total_projects=total_projects,
        recent_runs=safe_recent_runs,
        recent_repairs=safe_recent_repairs
    )
