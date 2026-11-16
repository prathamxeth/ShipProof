from typing import Optional, List
from pathlib import Path
import json
import asyncio
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

router = APIRouter(prefix="/runs", tags=["Verification Runs"])
logger = get_logger("api.runs")

@router.post("", response_model=RunSummaryResponse, status_code=status.HTTP_201_CREATED, summary="Create and launch a verification run")
async def create_verification_run(payload: RunCreate, db: AsyncSession = Depends(get_db)):
    target_url = payload.target_url

    # If project_id provided, ensure project exists and default target_url if not explicitly set
    if payload.project_id:
        proj_result = await db.execute(select(ProjectEntity).where(ProjectEntity.id == payload.project_id))
        project = proj_result.scalar_one_or_none()
        if not project:
            raise ResourceNotFoundException("Project", payload.project_id)
        if not target_url:
            target_url = project.target_url

    if not target_url:
        raise ShipProofException("Either 'target_url' or a valid 'project_id' with target_url must be provided", status_code=422)

    # Validate target URL against dangerous schemes, cloud metadata and SSRF risks
    target_url = validate_target_url(target_url)

    # Create run entity in QUEUED state
    run = VerificationRunEntity(
        title=payload.title,
        objective=payload.objective,
        target_url=str(target_url),
        project_id=payload.project_id,
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

    return run

@router.get("", response_model=PaginatedRunsResponse, summary="List verification runs")
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

    return PaginatedRunsResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset
    )

@router.get("/{run_id}", response_model=RunDetailResponse, summary="Get full verification run details and steps")
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
    
    # Construct response with events_count
    resp = RunDetailResponse.model_validate(run)
    resp.events_count = len(run.events)
    return resp

@router.post("/{run_id}/cancel", response_model=CancelResponse, summary="Cancel an active verification run")
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

@router.get("/{run_id}/events", summary="Get run events or live SSE event stream")
async def get_run_events(
    run_id: str,
    request: Request,
    stream: bool = Query(False, description="Stream live events via Server-Sent Events"),
    db: AsyncSession = Depends(get_db)
):
    # Verify run exists
    res = await db.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", run_id)

    accept_header = request.headers.get("accept", "")
    wants_sse = stream or "text/event-stream" in accept_header

    if wants_sse:
        async def event_generator():
            # 1. First replay existing historical events
            hist_res = await db.execute(
                select(VerificationEventEntity)
                .where(VerificationEventEntity.run_id == run_id)
                .order_by(VerificationEventEntity.created_at.asc())
            )
            for ev in hist_res.scalars().all():
                payload = {
                    "event_type": ev.event_type,
                    "step_number": ev.step_number,
                    "status": ev.status,
                    "description": ev.description,
                    "timestamp": ev.created_at.isoformat()
                }
                yield f"data: {json.dumps(payload)}\n\n"

            # 2. If run already finished, exit
            if run.status in ("passed", "failed", "error", "cancelled", "incomplete"):
                yield f"data: {json.dumps({'event_type': 'stream_end', 'status': run.status})}\n\n"
                return

            # 3. Stream real-time events from subscriber queue
            queue = runner_service.subscribe(run_id)
            try:
                while True:
                    try:
                        event_data = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(event_data)}\n\n"
                        if event_data.get("event_type") in ("completed", "cancelled"):
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
            .order_by(VerificationEventEntity.created_at.asc())
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
                event_type=e.event_type,
                step_number=e.step_number,
                status=e.status,
                description=e.description,
                raw_event=raw_obj,
                created_at=e.created_at
            ))
        return result

@router.get("/{run_id}/evidence", response_model=EvidenceResponse, summary="Get evidence pack metadata and artifacts")
async def get_run_evidence(run_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))
    run = res.scalar_one_or_none()
    if not run:
        raise ResourceNotFoundException("VerificationRun", run_id)

    evidence_dir = (settings.EVIDENCE_DIR / run_id).resolve()
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
        pack_path=run.evidence_pack_path,
        extracted_dir=str(evidence_dir),
        has_evidence=True,
        has_failure_yaml=manifest.get("has_failure_yaml", False),
        failure_details=manifest.get("failure_details"),
        artifacts=artifacts,
        console_errors_count=manifest.get("console_errors_count", 0),
        network_failures_count=manifest.get("network_failures_count", 0)
    )

@router.get("/{run_id}/evidence/files/{file_path:path}", summary="Securely serve evidence screenshots, HARs and logs")
async def get_evidence_file(run_id: str, file_path: str):
    """
    Safely serves an extracted evidence artifact while strictly enforcing path containment.
    """
    evidence_dir = (settings.EVIDENCE_DIR / run_id).resolve()
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
