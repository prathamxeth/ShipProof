from typing import Optional, List
from pathlib import Path
import json
import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, Request, status, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.errors import ResourceNotFoundException, ShipProofException
from backend.app.models.entities import RepairRecordEntity, RepairEventEntity, VerificationRunEntity
from backend.app.models.schemas import (
    RepairCreate,
    RepairSummaryResponse,
    RepairDetailResponse,
    RepairApproveRequest,
    RepairApproveResponse,
    RepairEventResponse,
    RepairPacketModel
)
from backend.app.core.logging import get_logger
from backend.app.services.repair_orchestrator import repair_orchestrator
from backend.app.services.git_service import GitService
from backend.app.core.auth import verify_auth, verify_protected_action

router = APIRouter(prefix="/repairs", tags=["Autonomous Repairs"])
logger = get_logger("api.repairs")

@router.post("", response_model=RepairSummaryResponse, status_code=status.HTTP_201_CREATED, summary="Create an autonomous repair job", dependencies=[Depends(verify_protected_action)])
async def create_repair(payload: RepairCreate, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == payload.run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", payload.run_id)

    if run.status == "passed":
        raise ShipProofException("Cannot create a repair for a passed verification run", status_code=400)

    try:
        repair = await repair_orchestrator.create_repair_session(
            run_id=payload.run_id,
            auto_approve=payload.auto_approve or False
        )
        return repair
    except ValueError as e:
        raise ShipProofException(str(e), status_code=400)

@router.get("", response_model=List[RepairSummaryResponse], summary="List all repair jobs")
async def list_repairs(
    run_id: Optional[str] = Query(None, description="Filter by run ID"),
    status: Optional[str] = Query(None, description="Filter by repair status"),
    db: AsyncSession = Depends(get_db)
):
    query = select(RepairRecordEntity)
    if run_id:
        query = query.where(RepairRecordEntity.run_id == run_id)
    if status:
        query = query.where(RepairRecordEntity.status == status)

    query = query.order_by(RepairRecordEntity.created_at.desc())
    res = await db.execute(query)
    return res.scalars().all()

@router.get("/{repair_id}", response_model=RepairDetailResponse, summary="Get repair job details")
async def get_repair(repair_id: str, db: AsyncSession = Depends(get_db)):
    query = (
        select(RepairRecordEntity)
        .where(RepairRecordEntity.id == repair_id)
        .options(selectinload(RepairRecordEntity.events))
    )
    res = await db.execute(query)
    repair = res.scalar_one_or_none()
    if not repair:
        raise ResourceNotFoundException("RepairRecord", repair_id)

    packet_obj = None
    if repair.repair_packet_json:
        try:
            packet_obj = RepairPacketModel.model_validate_json(repair.repair_packet_json)
        except Exception:
            pass

    files_mod = None
    if repair.files_modified:
        try:
            files_mod = json.loads(repair.files_modified)
        except Exception:
            pass

    # Resolve published prompt and job directory
    ws_repair_dir = settings.WORKSPACE_DIR / ".shipproof" / "repairs" / repair_id
    prompt_md = None
    if (ws_repair_dir / "prompt.md").exists():
        try:
            prompt_md = (ws_repair_dir / "prompt.md").read_text(encoding="utf-8")
        except Exception:
            pass
    elif (settings.DATA_DIR / "repairs" / repair_id / "repair_prompt.md").exists():
        try:
            prompt_md = (settings.DATA_DIR / "repairs" / repair_id / "repair_prompt.md").read_text(encoding="utf-8")
        except Exception:
            pass
    elif packet_obj:
        try:
            prompt_md = repair_orchestrator.packet_service.format_repair_prompt(packet_obj)
        except Exception:
            pass

    events_resp = [
        RepairEventResponse(
            id=e.id,
            repair_id=e.repair_id,
            from_state=e.from_state,
            to_state=e.to_state,
            description=e.description,
            raw_payload=json.loads(e.raw_payload) if e.raw_payload else None,
            created_at=e.created_at
        )
        for e in repair.events
    ]

    return RepairDetailResponse(
        id=repair.id,
        run_id=repair.run_id,
        attempt_number=repair.attempt_number,
        failing_step_index=repair.failing_step_index,
        status=repair.status,
        diagnosis=repair.diagnosis,
        files_modified=files_mod,
        patch_diff=repair.patch_diff,
        git_commit_before=repair.git_commit_before,
        git_commit_after=repair.git_commit_after,
        repair_packet=packet_obj,
        prompt_markdown=prompt_md,
        job_directory=str(ws_repair_dir),
        retest_run_id=repair.retest_run_id,
        retest_passed=repair.retest_passed,
        failure_notes=repair.failure_notes,
        created_at=repair.created_at,
        updated_at=repair.updated_at,
        completed_at=repair.completed_at,
        events=events_resp
    )

@router.post("/{repair_id}/check-changes", summary="Detect workspace changes applied by Antigravity IDE agent", dependencies=[Depends(verify_auth)])
async def check_repair_changes(repair_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id))
    repair = res.scalar_one_or_none()
    if not repair:
        raise ResourceNotFoundException("RepairRecord", repair_id)

    result = await repair_orchestrator.detect_workspace_changes(repair_id)
    return result

@router.post("/{repair_id}/approve", response_model=RepairApproveResponse, summary="Approve and apply proposed repair", dependencies=[Depends(verify_protected_action)])
async def approve_repair(repair_id: str, payload: RepairApproveRequest = None, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id))
    repair = res.scalar_one_or_none()
    if not repair:
        raise ResourceNotFoundException("RepairRecord", repair_id)

    if repair.status not in ("AWAITING_APPROVAL", "AGENT_RESPONSE_RECEIVED", "PROPOSED", "AWAITING_AGENT"):
        raise ShipProofException(f"Repair in status '{repair.status}' cannot be approved", status_code=400)

    # 1. Concurrency guard: reject if repair is already being applied or actively running
    if repair_id in repair_orchestrator._active_repairs and not repair_orchestrator._active_repairs[repair_id].done():
        raise ShipProofException("Repair session is currently already being processed", status_code=409)

    # 2. Workspace modifications check: require that modifications actually exist
    has_patch = bool(repair.patch_diff and repair.patch_diff.strip())
    ws_status = GitService.inspect_status(settings.WORKSPACE_DIR)
    if not has_patch and ws_status.is_clean:
        raise ShipProofException("Cannot approve repair: no workspace modifications have been detected to test", status_code=400)

    # 3. Atomic database transition to APPLYING
    update_stmt = (
        update(RepairRecordEntity)
        .where(
            RepairRecordEntity.id == repair_id,
            RepairRecordEntity.status.in_(("AWAITING_APPROVAL", "AGENT_RESPONSE_RECEIVED", "PROPOSED", "AWAITING_AGENT"))
        )
        .values(status="APPLYING", updated_at=datetime.now(timezone.utc))
    )
    update_res = await db.execute(update_stmt)
    await db.commit()
    if update_res.rowcount == 0:
        raise ShipProofException(f"Repair cannot be approved (current status: '{repair.status}')", status_code=400)

    rationale = payload.rationale if payload and payload.rationale else "Approved by user"
    try:
        await repair_orchestrator.apply_and_retest(repair_id, rationale=rationale)
    except Exception as e:
        logger.error(f"Failed to launch apply_and_retest for repair {repair_id}: {e}")
        # Revert status on launch failure
        await db.execute(
            update(RepairRecordEntity)
            .where(RepairRecordEntity.id == repair_id)
            .values(status=repair.status, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
        raise ShipProofException(f"Failed to initiate repair execution: {str(e)}", status_code=500)

    return RepairApproveResponse(
        repair_id=repair_id,
        status="APPLYING",
        message="Repair approved. Changes staged, build validating, and Kane re-verification launched."
    )

@router.post("/{repair_id}/cancel", summary="Cancel repair session", dependencies=[Depends(verify_protected_action)])
async def cancel_repair(repair_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id))
    repair = res.scalar_one_or_none()
    if not repair:
        raise ResourceNotFoundException("RepairRecord", repair_id)

    cancelled = await repair_orchestrator.cancel_repair(repair_id)
    return {
        "repair_id": repair_id,
        "status": "CANCELLED" if cancelled else repair.status,
        "message": "Repair session cancelled" if cancelled else "Repair was not active"
    }

@router.get("/{repair_id}/events", summary="Get repair audit events or live SSE stream", dependencies=[Depends(verify_auth)])
async def get_repair_events(
    repair_id: str,
    request: Request,
    stream: bool = Query(False, description="Stream live events via SSE"),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id))
    repair = res.scalar_one_or_none()
    if not repair:
        raise ResourceNotFoundException("RepairRecord", repair_id)

    accept_header = request.headers.get("accept", "")
    wants_sse = stream or "text/event-stream" in accept_header

    if wants_sse:
        async def event_generator():
            # 1. Historical events replay
            hist_res = await db.execute(
                select(RepairEventEntity)
                .where(RepairEventEntity.repair_id == repair_id)
                .order_by(RepairEventEntity.created_at.asc())
            )
            for ev in hist_res.scalars().all():
                payload = {
                    "repair_id": ev.repair_id,
                    "from_state": ev.from_state,
                    "to_state": ev.to_state,
                    "description": ev.description,
                    "timestamp": ev.created_at.isoformat(),
                    "payload": json.loads(ev.raw_payload) if ev.raw_payload else {}
                }
                yield f"data: {json.dumps(payload)}\n\n"

            if repair.status in ("VERIFIED", "FAILED", "UNRESOLVED", "CANCELLED"):
                yield f"data: {json.dumps({'repair_id': repair_id, 'to_state': repair.status, 'description': 'Lifecycle complete'})}\n\n"
                return

            # 2. Live subscriber queue
            queue = repair_orchestrator.subscribe(repair_id)
            try:
                while True:
                    try:
                        event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(event_data)}\n\n"
                        if event_data.get("to_state") in ("VERIFIED", "FAILED", "UNRESOLVED", "CANCELLED"):
                            break
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
            finally:
                repair_orchestrator.unsubscribe(repair_id, queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    else:
        events_res = await db.execute(
            select(RepairEventEntity)
            .where(RepairEventEntity.repair_id == repair_id)
            .order_by(RepairEventEntity.created_at.asc())
        )
        return [
            RepairEventResponse(
                id=e.id,
                repair_id=e.repair_id,
                from_state=e.from_state,
                to_state=e.to_state,
                description=e.description,
                raw_payload=json.loads(e.raw_payload) if e.raw_payload else None,
                created_at=e.created_at
            )
            for e in events_res.scalars().all()
        ]
