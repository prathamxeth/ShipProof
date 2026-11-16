import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, AsyncGenerator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import (
    VerificationRunEntity,
    VerificationStepEntity,
    VerificationEventEntity
)
from backend.app.services.kane_parser import NormalizedEvent, KaneParser
from backend.app.services.kane_service import KaneService, KaneExecutionResult, terminate_process_tree
from backend.app.services.evidence_service import EvidenceService

logger = get_logger("runner_service")

class RunnerService:
    """
    Orchestrates verification runs:
    - Background task management
    - State transitions: QUEUED -> RUNNING -> PASSED / FAILED / ERROR / CANCELLED / INCOMPLETE
    - Incremental database event persistence
    - Live SSE broadcasting to connected clients
    - Evidence extraction & manifest generation
    - Process tree management and clean termination
    """

    def __init__(self):
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self._event_subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._concurrency_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_RUNS)
        self.evidence_service = EvidenceService()

    def subscribe(self, run_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        if run_id not in self._event_subscribers:
            self._event_subscribers[run_id] = []
        self._event_subscribers[run_id].append(queue)
        logger.debug(f"Client subscribed to SSE events for run {run_id}")
        return queue

    def unsubscribe(self, run_id: str, queue: asyncio.Queue):
        if run_id in self._event_subscribers and queue in self._event_subscribers[run_id]:
            self._event_subscribers[run_id].remove(queue)
            if not self._event_subscribers[run_id]:
                del self._event_subscribers[run_id]

    async def _broadcast_event(self, run_id: str, event_data: dict):
        if run_id in self._event_subscribers:
            for q in list(self._event_subscribers[run_id]):
                try:
                    if q.full():
                        try:
                            q.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    q.put_nowait(event_data)
                except Exception as e:
                    logger.warning(f"Error publishing to SSE queue: {e}")

    async def cancel_run(self, run_id: str) -> bool:
        """
        Cancels an active running task and cleanly terminates its entire process tree.
        Idempotent: safely cancels active tasks and marks running/queued runs as cancelled.
        """
        # 1. Kill subprocess tree immediately if running
        proc = self._active_processes.get(run_id)
        if proc:
            logger.info(f"Terminating subprocess tree for run {run_id}")
            await terminate_process_tree(proc)

        cancelled = False
        task = self._active_tasks.get(run_id)
        if task and not task.done():
            logger.info(f"Cancelling active execution task for run {run_id}")
            task.cancel()
            cancelled = True

        # Update database status atomically if in active state
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                update(VerificationRunEntity)
                .where(
                    VerificationRunEntity.id == run_id,
                    VerificationRunEntity.status.in_(["running", "queued"])
                )
                .values(
                    status="cancelled",
                    failure_reason="Run cancelled by user",
                    completed_at=datetime.now(timezone.utc)
                )
            )
            await session.commit()
            if res.rowcount > 0:
                cancelled = True

        if cancelled:
            # Broadcast terminal cancellation event
            await self._broadcast_event(run_id, {
                "event_type": "cancelled",
                "status": "cancelled",
                "description": "Verification run was cancelled by user",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            return True
        return False

    async def terminate_all_processes(self):
        """
        Terminates all active subprocess trees on backend shutdown.
        """
        for run_id, proc in list(self._active_processes.items()):
            logger.info(f"Terminating active process tree for run {run_id}")
            try:
                await terminate_process_tree(proc)
            except Exception as e:
                logger.warning(f"Error terminating process tree for run {run_id}: {e}")
        self._active_processes.clear()

    def enqueue_run(
        self,
        run_id: str,
        objective: str,
        target_url: str,
        headless: bool = True,
        timeout: int = 120
    ):
        """
        Spawns background execution task for a run.
        """
        task = asyncio.create_task(
            self._execute_run_lifecycle(run_id, objective, target_url, headless, timeout)
        )
        self._active_tasks[run_id] = task

        def _cleanup(_):
            self._active_tasks.pop(run_id, None)

        task.add_done_callback(_cleanup)

    async def _execute_run_lifecycle(
        self,
        run_id: str,
        objective: str,
        target_url: str,
        headless: bool,
        timeout: int
    ):
        logger.info(f"Starting execution lifecycle for run {run_id}")
        
        async with self._concurrency_semaphore:
            # 1. Transition state to RUNNING if not cancelled
            async with AsyncSessionLocal() as session:
                curr_res = await session.execute(
                    select(VerificationRunEntity.status).where(VerificationRunEntity.id == run_id)
                )
                curr_status = curr_res.scalar_one_or_none()
                if curr_status == "cancelled":
                    logger.info(f"Run {run_id} was cancelled before execution started; skipping")
                    return

                await session.execute(
                    update(VerificationRunEntity)
                    .where(VerificationRunEntity.id == run_id, VerificationRunEntity.status == "queued")
                    .values(status="running", updated_at=datetime.now(timezone.utc))
                )
                await session.commit()

            # Incremental event callback to persist and broadcast events with monotonic sequences
            seq_counter = 0

            async def on_event(event: NormalizedEvent):
                nonlocal seq_counter
                seq_counter += 1
                event_dict = event.to_dict()
                event_dict["event_seq"] = seq_counter

                # Broadcast to SSE subscribers immediately
                await self._broadcast_event(run_id, event_dict)

                # Persist to database
                async with AsyncSessionLocal() as session:
                    # Save event entity
                    event_entity = VerificationEventEntity(
                        run_id=run_id,
                        event_seq=seq_counter,
                        event_type=event.event_type,
                        step_number=event.step_number,
                        status=event.status,
                        description=event.description,
                        raw_event=json.dumps(event.raw_event)
                    )
                    session.add(event_entity)

                    # If step event, update or insert step entity
                    if event.event_type == "step" and event.step_number is not None:
                        # Check if step exists
                        res = await session.execute(
                            select(VerificationStepEntity).where(
                                VerificationStepEntity.run_id == run_id,
                                VerificationStepEntity.step_index == event.step_number
                            )
                        )
                        existing_step = res.scalar_one_or_none()
                        if existing_step:
                            existing_step.status = event.status or existing_step.status
                            if event.description:
                                existing_step.remark = event.description
                        else:
                            new_step = VerificationStepEntity(
                                run_id=run_id,
                                step_index=event.step_number,
                                status=event.status or "running",
                                remark=event.description or f"Step {event.step_number}"
                            )
                            session.add(new_step)

                    # Capture session_id if present
                    if event.session_id:
                        await session.execute(
                            update(VerificationRunEntity)
                            .where(VerificationRunEntity.id == run_id)
                            .values(kane_session_id=event.session_id)
                        )

                    await session.commit()

            # 2. Run Kane process via adapter
            session_slug = f"run-{run_id[:8]}"
            exec_result: Optional[KaneExecutionResult] = None
            try:
                exec_result = await KaneService.run_kane(
                    run_id=run_id,
                    objective=objective,
                    target_url=target_url,
                    headless=headless,
                    session_name=session_slug,
                    timeout=timeout,
                    event_callback=on_event,
                    on_process_spawned=lambda proc: self._active_processes.update({run_id: proc})
                )
            except asyncio.CancelledError:
                logger.warning(f"Run {run_id} cancelled during subprocess execution")
                return
            except Exception as err:
                logger.error(f"Execution error running Kane for run {run_id}: {err}")
                async with AsyncSessionLocal() as session:
                    # Check if already cancelled
                    chk_res = await session.execute(
                        select(VerificationRunEntity.status).where(VerificationRunEntity.id == run_id)
                    )
                    if chk_res.scalar_one_or_none() == "cancelled":
                        return

                    await session.execute(
                        update(VerificationRunEntity)
                        .where(VerificationRunEntity.id == run_id, VerificationRunEntity.status == "running")
                        .values(
                            status="error",
                            exit_code=-1,
                            failure_reason=f"Execution error: {str(err)}",
                            completed_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                    )
                    await session.commit()
                await self._broadcast_event(run_id, {
                    "event_type": "completed",
                    "status": "error",
                    "exit_code": -1,
                    "description": f"Verification failed with execution error: {str(err)}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                return
            finally:
                self._active_processes.pop(run_id, None)

            # 3. Post-execution evidence discovery & packaging
            evidence_pack_path = None
            session_dir = None
            if exec_result.run_end_event:
                session_dir = exec_result.run_end_event.session_id

            found_pack = self.evidence_service.locate_evidence_pack(
                run_id=run_id,
                session_dir=session_dir,
                stderr_hint=exec_result.stderr_hint
            )

            if found_pack:
                try:
                    extracted_dir = self.evidence_service.safe_extract_evidence_pack(found_pack, run_id)
                    evidence_manifest = self.evidence_service.parse_extracted_evidence(extracted_dir, run_id)
                    evidence_pack_path = str(found_pack)

                    # Associate screenshots with steps in DB
                    async with AsyncSessionLocal() as session:
                        for art in evidence_manifest.get("artifacts", []):
                            step_idx = art.get("step_index")
                            if step_idx is not None:
                                res = await session.execute(
                                    select(VerificationStepEntity).where(
                                        VerificationStepEntity.run_id == run_id,
                                        VerificationStepEntity.step_index == step_idx
                                    )
                                )
                                step = res.scalar_one_or_none()
                                if step:
                                    if art.get("artifact_type") == "annotated_screenshot":
                                        step.annotated_screenshot_path = art.get("relative_path")
                                    elif art.get("artifact_type") == "screenshot":
                                        step.screenshot_path = art.get("relative_path")
                        await session.commit()
                except Exception as ev_err:
                    logger.error(f"Error extracting evidence pack for run {run_id}: {ev_err}")

            # 4. Compute step counts and finalize database record
            async with AsyncSessionLocal() as session:
                # Check if run was cancelled during execution
                chk_res = await session.execute(
                    select(VerificationRunEntity.status).where(VerificationRunEntity.id == run_id)
                )
                if chk_res.scalar_one_or_none() == "cancelled":
                    logger.info(f"Run {run_id} is in cancelled terminal state; ignoring late subprocess result ({exec_result.status})")
                    return

                # Count steps
                steps_res = await session.execute(
                    select(VerificationStepEntity).where(VerificationStepEntity.run_id == run_id)
                )
                all_steps = steps_res.scalars().all()
                total_steps = len(all_steps)
                passed_steps = sum(1 for s in all_steps if s.status == "done")
                failed_steps = sum(1 for s in all_steps if s.status == "failed")

                # Extract failure reason if failed
                failure_reason = exec_result.error_message
                if exec_result.run_end_event and exec_result.run_end_event.status == "failed":
                    failure_reason = exec_result.run_end_event.description or "Test objective failed"

                update_res = await session.execute(
                    update(VerificationRunEntity)
                    .where(VerificationRunEntity.id == run_id, VerificationRunEntity.status.in_(["running", "queued"]))
                    .values(
                        status=exec_result.status,
                        exit_code=exec_result.exit_code,
                        total_steps=total_steps,
                        passed_steps=passed_steps,
                        failed_steps=failed_steps,
                        failure_reason=failure_reason,
                        raw_stdout_path=exec_result.raw_stdout_path,
                        raw_stderr_path=exec_result.raw_stderr_path,
                        evidence_pack_path=evidence_pack_path,
                        completed_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc)
                    )
                )
                await session.commit()
                if update_res.rowcount == 0:
                    logger.warning(f"Run {run_id} was modified concurrently; skipping completion broadcast")
                    return

            # 5. Broadcast completion event to SSE
            await self._broadcast_event(run_id, {
                "event_type": "completed",
                "status": exec_result.status,
                "exit_code": exec_result.exit_code,
                "description": f"Verification run finalized with status: {exec_result.status}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })

            logger.info(f"Run {run_id} completed with status: {exec_result.status} (exit code: {exec_result.exit_code})")

# Singleton instance
runner_service = RunnerService()
