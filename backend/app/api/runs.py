from typing import Optional, List
from pathlib import Path
import json
import asyncio
import re
from fastapi import APIRouter, Depends, Query, Request, status, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.errors import ResourceNotFoundException, ShipProofException
from backend.app.models.entities import (
    VerificationRunEntity,
    ProjectEntity,
    VerificationEventEntity,
    VerificationStepEntity
)
from backend.app.models.schemas import (
    RunCreate,
    RunSummaryResponse,
    RunDetailResponse,
    PaginatedRunsResponse,
    EventResponse,
    EvidenceResponse,
    EvidenceArtifact,
    CancelResponse
)
from backend.app.core.logging import get_logger
from backend.app.services.runner_service import runner_service
from backend.app.services.evidence_service import PathTraversalError
from backend.app.core.url_validator import validate_target_url
from backend.app.core.auth import verify_auth, verify_protected_action
from backend.app.core.sanitizer import (
    sanitize_filesystem_path,
    sanitize_kane_session_id,
    sanitize_user_identifier
)
from backend.app.models.schemas import StepResponse, RepairSummaryResponse

router = APIRouter(prefix="/runs", tags=["Verification Runs"])
logger = get_logger("api.runs")

async def get_project_map(db: AsyncSession) -> dict[str, str]:
    res = await db.execute(select(ProjectEntity.id, ProjectEntity.name))
    return {row[0]: row[1] for row in res.all()}

def to_run_summary(run: VerificationRunEntity, project_map: dict[str, str]) -> RunSummaryResponse:
    p_name = project_map.get(run.project_id) if run.project_id else "Standalone / Ad-Hoc"
    return RunSummaryResponse(
        id=run.id,
        project_id=run.project_id,
        project_name=p_name,
        title=run.title,
        objective=run.objective,
        target_url=run.target_url,
        status=run.status,
        mode=run.mode,
        kane_session_id=sanitize_kane_session_id(run.kane_session_id),
        total_steps=run.total_steps,
        passed_steps=run.passed_steps,
        failed_steps=run.failed_steps,
        exit_code=run.exit_code,
        repaired=run.repaired,
        repair_attempts=run.repair_attempts,
        created_at=run.created_at,
        completed_at=run.completed_at
    )

def to_run_detail(run: VerificationRunEntity, project_map: dict[str, str]) -> RunDetailResponse:
    p_name = project_map.get(run.project_id) if run.project_id else "Standalone / Ad-Hoc"
    summary = to_run_summary(run, project_map)
    repairs_summary = [
        RepairSummaryResponse(
            id=rep.id,
            run_id=rep.run_id,
            project_name=p_name,
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
        for rep in (run.repairs or [])
    ]
    return RunDetailResponse(
        **summary.model_dump(),
        execution_id=run.execution_id,
        evidence_pack_path=sanitize_filesystem_path(run.evidence_pack_path),
        failure_reason=run.failure_reason,
        verification_proof=run.verification_proof,
        steps=[StepResponse.model_validate(s) for s in (run.steps or [])],
        repairs=repairs_summary,
        events_count=len(run.events) if run.events else 0
    )

@router.post("", response_model=RunSummaryResponse, status_code=status.HTTP_201_CREATED, summary="Create and launch a verification run", dependencies=[Depends(verify_protected_action)])
async def create_verification_run(payload: RunCreate, db: AsyncSession = Depends(get_db)):
    target_url = payload.target_url
    project_id = payload.project_id

    # If project_id provided, ensure project exists and default target_url if not explicitly set
    if project_id:
        proj_result = await db.execute(select(ProjectEntity).where(ProjectEntity.id == project_id))
        project = proj_result.scalar_one_or_none()
        if not project:
            raise ResourceNotFoundException("Project", project_id)
        if not target_url:
            target_url = project.target_url
    elif target_url:
        # Auto-link to matching project by target_url if available
        validated_candidate = validate_target_url(target_url)
        match_q = await db.execute(
            select(ProjectEntity).where(ProjectEntity.target_url == str(validated_candidate)).order_by(ProjectEntity.created_at.asc())
        )
        matching_proj = match_q.scalars().first()
        if matching_proj:
            project_id = matching_proj.id

    if not target_url:
        raise ShipProofException("Either 'target_url' or a valid 'project_id' with target_url must be provided", status_code=422)

    # Validate target URL against dangerous schemes, cloud metadata and SSRF risks
    target_url = validate_target_url(target_url)

    # Create run entity in QUEUED state
    run = VerificationRunEntity(
        title=payload.title,
        objective=payload.objective,
        target_url=str(target_url),
        project_id=project_id,
        mode=payload.mode or "closed_loop",
        status="queued",
    )
    db.add(run)
    await db.flush()
    await db.refresh(run)

    logger.info(f"Created verification run '{run.title}' (ID: {run.id})")

    # Enqueue background execution
    runner_service.enqueue_run(
        run_id=run.id,
        objective=run.objective,
        target_url=run.target_url,
        headless=payload.headless if payload.headless is not None else True,
        timeout=payload.timeout or 120
    )

    project_map = await get_project_map(db)
    return to_run_summary(run, project_map)

@router.get("", response_model=PaginatedRunsResponse, summary="List verification runs", dependencies=[Depends(verify_auth)])
async def list_verification_runs(
    project_id: Optional[str] = Query(None, description="Filter runs by project ID"),
    status: Optional[str] = Query(None, description="Filter runs by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(VerificationRunEntity)
    count_query = select(func.count()).select_from(VerificationRunEntity)

    if project_id:
        query = query.where(VerificationRunEntity.project_id == project_id)
        count_query = count_query.where(VerificationRunEntity.project_id == project_id)
    if status:
        query = query.where(VerificationRunEntity.status == status)
        count_query = count_query.where(VerificationRunEntity.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(VerificationRunEntity.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()

    project_map = await get_project_map(db)
    summary_items = [to_run_summary(r, project_map) for r in items]

    return PaginatedRunsResponse(
        items=summary_items,
        total=total,
        limit=limit,
        offset=offset
    )

@router.get("/{run_id}", response_model=RunDetailResponse, summary="Get full verification run details and steps", dependencies=[Depends(verify_auth)])
async def get_verification_run(run_id: str, db: AsyncSession = Depends(get_db)):
    query = (
        select(VerificationRunEntity)
        .where(VerificationRunEntity.id == run_id)
        .options(
            selectinload(VerificationRunEntity.steps),
            selectinload(VerificationRunEntity.repairs),
            selectinload(VerificationRunEntity.events)
        )
    )
    result = await db.execute(query)
    run = result.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", run_id)
    
    project_map = await get_project_map(db)
    return to_run_detail(run, project_map)

@router.post("/{run_id}/cancel", response_model=CancelResponse, summary="Cancel an active verification run", dependencies=[Depends(verify_protected_action)])
async def cancel_verification_run(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", run_id)

    if run.status in ("passed", "failed", "error", "cancelled", "incomplete"):
        return CancelResponse(
            run_id=run_id,
            status=run.status,
            message=f"Run cannot be cancelled because it is already finalized with status: {run.status}"
        )

    cancelled = await runner_service.cancel_run(run_id)
    return CancelResponse(
        run_id=run_id,
        status="cancelled" if cancelled else run.status,
        message="Verification run cancelled successfully" if cancelled else "No active process was running"
    )

@router.get("/{run_id}/events", summary="Get run events or live SSE event stream", dependencies=[Depends(verify_auth)])
async def get_run_events(
    run_id: str,
    request: Request,
    stream: bool = Query(False, description="Stream live events via Server-Sent Events"),
    last_event_id: Optional[int] = Query(None, description="Monotonic event sequence to replay after"),
    db: AsyncSession = Depends(get_db)
):
    # Verify run exists
    res = await db.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", run_id)

    accept_header = request.headers.get("accept", "")
    wants_sse = stream or "text/event-stream" in accept_header

    # Determine Last-Event-ID from header or query param
    header_last_id = request.headers.get("last-event-id")
    effective_last_id = last_event_id
    if effective_last_id is None and header_last_id:
        try:
            effective_last_id = int(header_last_id.strip())
        except ValueError:
            effective_last_id = None

    if wants_sse:
        async def event_generator():
            last_seq_sent = effective_last_id or 0
            
            # Subscribe to live queue FIRST to prevent any race condition event loss during history query
            queue = runner_service.subscribe(run_id)
            try:
                # 1. First replay existing historical events (filtering by sequence if reconnecting)
                hist_query = (
                    select(VerificationEventEntity)
                    .where(VerificationEventEntity.run_id == run_id)
                )
                if effective_last_id is not None:
                    hist_query = hist_query.where(VerificationEventEntity.event_seq > effective_last_id)
                
                hist_query = hist_query.order_by(VerificationEventEntity.event_seq.asc())
                hist_res = await db.execute(hist_query)
                
                for ev in hist_res.scalars().all():
                    seq = ev.event_seq or (last_seq_sent + 1)
                    last_seq_sent = max(last_seq_sent, seq)
                    payload = {
                        "event_seq": seq,
                        "event_type": ev.event_type,
                        "step_number": ev.step_number,
                        "status": ev.status,
                        "description": ev.description,
                        "timestamp": ev.created_at.isoformat()
                    }
                    yield f"id: {seq}\ndata: {json.dumps(payload)}\n\n"

                # 2. If run already finalized, send stream termination
                if run.status in ("passed", "failed", "error", "cancelled", "incomplete"):
                    yield f"data: {json.dumps({'event_type': 'stream_end', 'status': run.status})}\n\n"
                    return

                # 3. Stream real-time events from subscriber queue with strict deduplication
                while True:
                    try:
                        event_data = await asyncio.wait_for(queue.get(), timeout=15.0)
                        seq = event_data.get("event_seq")
                        
                        # Deduplicate events that were already streamed during history replay
                        if seq is not None and seq <= last_seq_sent:
                            continue
                        
                        if seq is not None:
                            last_seq_sent = seq
                            yield f"id: {seq}\ndata: {json.dumps(event_data)}\n\n"
                        else:
                            yield f"data: {json.dumps(event_data)}\n\n"

                        if event_data.get("event_type") in ("completed", "cancelled") or event_data.get("status") in ("passed", "failed", "error", "cancelled", "incomplete"):
                            break
                    except asyncio.TimeoutError:
                        # Send heartbeat comment to keep connection alive
                        yield ": heartbeat\n\n"
            finally:
                runner_service.unsubscribe(run_id, queue)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Return static list of events
        events_res = await db.execute(
            select(VerificationEventEntity)
            .where(VerificationEventEntity.run_id == run_id)
            .order_by(VerificationEventEntity.event_seq.asc(), VerificationEventEntity.created_at.asc())
        )
        entities = events_res.scalars().all()
        result = []
        for e in entities:
            raw_obj = None
            if e.raw_event:
                try:
                    raw_obj = json.loads(e.raw_event)
                except Exception:
                    pass
            result.append(EventResponse(
                id=e.id,
                run_id=e.run_id,
                event_seq=e.event_seq,
                event_type=e.event_type,
                step_number=e.step_number,
                status=e.status,
                description=e.description,
                raw_event=raw_obj,
                created_at=e.created_at
            ))
        return result

def validate_safe_run_id(run_id: str) -> Path:
    """
    Validates run_id against illegal path characters and ensures containment within EVIDENCE_DIR.
    """
    if not run_id or not re.match(r"^[a-zA-Z0-9_\-]+$", run_id):
        raise HTTPException(status_code=400, detail="Invalid run_id format: contains disallowed characters")
    evidence_dir = (settings.EVIDENCE_DIR / run_id).resolve()
    base_dir = settings.EVIDENCE_DIR.resolve()
    if base_dir not in evidence_dir.parents or evidence_dir == base_dir:
        raise HTTPException(status_code=403, detail="Access denied: path traversal attempt in run_id")
    return evidence_dir

@router.get("/{run_id}/evidence", response_model=EvidenceResponse, summary="Get evidence pack metadata and artifacts", dependencies=[Depends(verify_auth)])
async def get_run_evidence(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", run_id)

    evidence_dir = validate_safe_run_id(run_id)
    if not evidence_dir.exists() or not evidence_dir.is_dir():
        return EvidenceResponse(
            run_id=run_id,
            pack_path=run.evidence_pack_path,
            has_evidence=False,
            artifacts=[]
        )

    manifest = runner_service.evidence_service.parse_extracted_evidence(evidence_dir, run_id)
    artifacts = [
        EvidenceArtifact(
            step_index=a.get("step_index"),
            artifact_type=a.get("artifact_type"),
            filename=a.get("filename"),
            relative_path=a.get("relative_path"),
            file_size_bytes=a.get("file_size_bytes", 0)
        )
        for a in manifest.get("artifacts", [])
    ]

    return EvidenceResponse(
        run_id=run_id,
        pack_path=sanitize_filesystem_path(run.evidence_pack_path),
        extracted_dir=f"evidence/{run_id}",
        has_evidence=True,
        has_failure_yaml=manifest.get("has_failure_yaml", False),
        failure_details=manifest.get("failure_details"),
        artifacts=artifacts,
        console_errors_count=manifest.get("console_errors_count", 0),
        network_failures_count=manifest.get("network_failures_count", 0)
    )

@router.get("/{run_id}/evidence/files/{file_path:path}", summary="Securely serve evidence screenshots, HARs and logs", dependencies=[Depends(verify_auth)])
async def get_evidence_file(run_id: str, file_path: str):
    """
    Safely serves an extracted evidence artifact while strictly enforcing path containment.
    """
    evidence_dir = validate_safe_run_id(run_id)
    if not evidence_dir.exists():
        raise HTTPException(status_code=404, detail="Evidence directory not found for this run")

    # Path traversal defense: target must strictly reside within evidence_dir hierarchy
    target_file = (evidence_dir / file_path).resolve()
    if target_file != evidence_dir and evidence_dir not in target_file.parents:
        raise HTTPException(status_code=403, detail="Access denied: path traversal attempt detected")

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail=f"Evidence file '{file_path}' not found")

    # Content type determination
    suffix = target_file.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".json": "application/json",
        ".ndjson": "application/x-ndjson",
        ".har": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".log": "text/plain",
        ".txt": "text/plain",
    }
    media_type = media_types.get(suffix, "application/octet-stream")

    return FileResponse(
        path=str(target_file),
        media_type=media_type,
        filename=target_file.name
    )
