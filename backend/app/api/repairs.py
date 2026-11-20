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
from backend.app.core.auth import verify_auth, verify_protected_action, verify_human_approval_auth
from backend.app.core.sanitizer import (
    sanitize_filesystem_path,
    sanitize_user_identifier,
    sanitize_kane_session_id
)
from backend.app.models.entities import ProjectEntity
import hashlib

router = APIRouter(prefix="/repairs", tags=["Autonomous Repairs"])
logger = get_logger("api.repairs")

async def get_repair_project_map(db: AsyncSession) -> dict[str, str]:
    q = (
        select(VerificationRunEntity.id, ProjectEntity.name)
        .join(ProjectEntity, VerificationRunEntity.project_id == ProjectEntity.id, isouter=True)
    )
    res = await db.execute(q)
    return {row[0]: (row[1] or "Standalone / Ad-Hoc") for row in res.all()}

def to_repair_summary(repair: RepairRecordEntity, run_project_map: dict[str, str]) -> RepairSummaryResponse:
    p_name = run_project_map.get(repair.run_id, "Standalone / Ad-Hoc")
    files_list = []
    if repair.files_modified:
        try:
            files_list = json.loads(repair.files_modified) if isinstance(repair.files_modified, str) else repair.files_modified
        except Exception:
            files_list = []
    return RepairSummaryResponse(
        id=repair.id,
        run_id=repair.run_id,
        project_name=p_name,
        attempt_number=repair.attempt_number,
        status=repair.status,
        execution_mode=repair.execution_mode or "ide_mediated",
        diagnosis=repair.diagnosis,
        patch_diff=repair.patch_diff,
        files_modified=files_list,
        git_commit_before=repair.git_commit_before,
        git_commit_after=repair.git_commit_after,
        retest_run_id=repair.retest_run_id,
        retest_passed=repair.retest_passed,
        approved_by_user_id=sanitize_user_identifier(repair.approved_by_user_id),
        approved_at=repair.approved_at,
        approved_diff_hash=repair.approved_diff_hash,
        approval_decision=repair.approval_decision,
        created_at=repair.created_at,
        updated_at=repair.updated_at,
        completed_at=repair.completed_at
    )

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
        proj_map = await get_repair_project_map(db)
        return to_repair_summary(repair, proj_map)
    except ValueError as e:
        raise ShipProofException(str(e), status_code=400)

@router.get("", response_model=List[RepairSummaryResponse], summary="List all repair jobs", dependencies=[Depends(verify_auth)])
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
    repairs = res.scalars().all()
    proj_map = await get_repair_project_map(db)
    return [to_repair_summary(r, proj_map) for r in repairs]

@router.get("/{repair_id}", response_model=RepairDetailResponse, summary="Get repair job details", dependencies=[Depends(verify_auth)])
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
            # Sanitize paths in packet
            if packet_obj.project_dir:
                packet_obj.project_dir = sanitize_filesystem_path(packet_obj.project_dir) or "demo_targets/sample_store"
            if packet_obj.kane_session_id:
                packet_obj.kane_session_id = sanitize_kane_session_id(packet_obj.kane_session_id)
        except Exception:
            pass

    files_mod = None
    if repair.files_modified:
        try:
            files_mod = json.loads(repair.files_modified)
        except Exception:
            pass

    # Resolve published prompt and job directory (sanitize to relative path)
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

    proj_map = await get_repair_project_map(db)
    summary = to_repair_summary(repair, proj_map)
    summary_data = summary.model_dump()
    if files_mod is not None:
        summary_data["files_modified"] = files_mod
    if repair.patch_diff is not None:
        summary_data["patch_diff"] = repair.patch_diff

    return RepairDetailResponse(
        **summary_data,
        failing_step_index=repair.failing_step_index,
        repair_packet=packet_obj,
        prompt_markdown=prompt_md,
        job_directory=f".shipproof/repairs/{repair_id}",
        failure_notes=repair.failure_notes,
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

@router.post("/{repair_id}/approve", response_model=RepairApproveResponse, summary="Approve and apply proposed repair")
async def approve_repair(
    repair_id: str,
    payload: Optional[RepairApproveRequest] = None,
    user: str = Depends(verify_human_approval_auth),
    db: AsyncSession = Depends(get_db)
):
    res = await db.execute(select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id))
    repair = res.scalar_one_or_none()
    if not repair:
        raise ResourceNotFoundException("RepairRecord", repair_id)

    orig_status = repair.status
    decision = (payload.decision if payload and payload.decision else "APPROVE").strip().upper()
    rationale = (
        payload.rationale.strip()
        if payload and payload.rationale and payload.rationale.strip()
        else f"{decision} by {user}"
    )

    # 1. Handle REJECT decision
    if decision == "REJECT":
        if orig_status not in ("AWAITING_APPROVAL", "AGENT_RESPONSE_RECEIVED", "PROPOSED", "AWAITING_AGENT"):
            raise ShipProofException(f"Repair in status '{orig_status}' cannot be rejected", status_code=400)

        now = datetime.now(timezone.utc)
        repair.status = "REJECTED"
        repair.approved_by_user_id = user
        repair.approved_at = now
        repair.approval_decision = "REJECTED"
        repair.updated_at = now

        event = RepairEventEntity(
            repair_id=repair_id,
            from_state=orig_status,
            to_state="REJECTED",
            description=f"Repair rejected by {user}: {rationale}",
            raw_payload=json.dumps({"approver": user, "decision": "REJECTED", "rationale": rationale})
        )
        db.add(event)
        await db.commit()

        await repair_orchestrator._broadcast(repair_id, {
            "repair_id": repair_id,
            "from_state": orig_status,
            "to_state": "REJECTED",
            "description": f"Repair rejected by {user}",
            "timestamp": now.isoformat(),
            "payload": {"approver": user, "decision": "REJECTED", "rationale": rationale}
        })

        return RepairApproveResponse(
            repair_id=repair_id,
            status="REJECTED",
            message=f"Repair rejected by {user}.",
            approved_by=user,
            approved_at=now,
            decision="REJECTED"
        )

    if decision != "APPROVE":
        raise ShipProofException(f"Invalid decision '{decision}': must be 'APPROVE' or 'REJECT'", status_code=400)

    # 2. Handle APPROVE decision
    if orig_status not in ("AWAITING_APPROVAL", "AGENT_RESPONSE_RECEIVED", "PROPOSED", "AWAITING_AGENT"):
        raise ShipProofException(f"Repair in status '{orig_status}' cannot be approved", status_code=400)

    # Reject replay if already approved/applying
    if orig_status in ("APPLYING", "VERIFIED") or repair.approval_decision == "APPROVED":
        raise ShipProofException(f"Repair in status '{orig_status}' cannot be approved", status_code=400)

    # Concurrency guard: reject if repair is already being applied or actively running
    if repair_id in repair_orchestrator._active_repairs and not repair_orchestrator._active_repairs[repair_id].done():
        raise ShipProofException("Repair session is currently already being processed", status_code=409)

    # Workspace modifications & diff binding check
    ws_status = GitService.inspect_status(settings.WORKSPACE_DIR)
    has_patch = bool(repair.patch_diff and repair.patch_diff.strip())
    if not has_patch and ws_status.is_clean:
        raise ShipProofException("Cannot approve repair: no workspace modifications have been detected to test", status_code=400)

    ws_diff = GitService.capture_diff(settings.WORKSPACE_DIR)
    effective_diff = repair.patch_diff.strip() if has_patch else ws_diff.strip()
    current_diff_hash = hashlib.sha256(effective_diff.encode("utf-8")).hexdigest()

    if payload and payload.diff_hash:
        supplied_hash = payload.diff_hash.strip()
        if supplied_hash.lower() != current_diff_hash.lower():
            logger.warning(f"Diff hash mismatch for repair {repair_id}: supplied {supplied_hash}, computed {current_diff_hash}")
            raise ShipProofException(
                f"Approval diff hash mismatch: the diff presented for review does not match current workspace changes ({supplied_hash[:8]} != {current_diff_hash[:8]}).",
                status_code=409
            )

    # Atomic database transition to APPLYING
    now = datetime.now(timezone.utc)
    update_stmt = (
        update(RepairRecordEntity)
        .where(
            RepairRecordEntity.id == repair_id,
            RepairRecordEntity.status.in_(("AWAITING_APPROVAL", "AGENT_RESPONSE_RECEIVED", "PROPOSED", "AWAITING_AGENT"))
        )
        .values(
            status="APPLYING",
            approved_by_user_id=user,
            approved_at=now,
            approved_diff_hash=current_diff_hash,
            approval_decision="APPROVED",
            updated_at=now
        )
    )
    update_res = await db.execute(update_stmt)
    if update_res.rowcount == 0:
        await db.rollback()
        raise ShipProofException(f"Concurrent approval conflict: repair status is '{orig_status}'", status_code=409)

    # Record immutable audit event in repair_events
    event = RepairEventEntity(
        repair_id=repair_id,
        from_state=orig_status,
        to_state="APPLYING",
        description=f"Repair approved by {user} with diff hash {current_diff_hash[:8]}",
        raw_payload=json.dumps({
            "approver": user,
            "diff_hash": current_diff_hash,
            "decision": "APPROVED",
            "rationale": rationale
        })
    )
    db.add(event)
    await db.commit()

    try:
        await repair_orchestrator.apply_and_retest(
            repair_id=repair_id,
            rationale=rationale,
            approver=user,
            diff_hash=current_diff_hash
        )
    except Exception as e:
        logger.error(f"Failed to launch apply_and_retest for repair {repair_id}: {e}")
        # Revert status on launch failure
        await db.execute(
            update(RepairRecordEntity)
            .where(RepairRecordEntity.id == repair_id)
            .values(status=orig_status, updated_at=datetime.now(timezone.utc))
        )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to initiate repair execution: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate repair execution: {str(e)}")

    return RepairApproveResponse(
        repair_id=repair_id,
        status="APPLYING",
        message="Repair approved. Changes staged, build validating, and Kane re-verification launched.",
        approved_by=user,
        approved_at=now,
        approved_diff_hash=current_diff_hash,
        decision="APPROVED"
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
