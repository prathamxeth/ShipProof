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
        recent_runs=[RunSummaryResponse.model_validate(r) for r in recent_runs],
        recent_repairs=[RepairSummaryResponse.model_validate(rep) for rep in recent_repairs]
    )
