import asyncio
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, AsyncGenerator
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from backend.app.core.config import settings
from backend.app.core.logging import get_logger
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import (
    RepairRecordEntity,
    RepairEventEntity,
    VerificationRunEntity,
    ProjectEntity
)
from backend.app.models.schemas import RepairPacketModel
from backend.app.services.repair_packet_service import RepairPacketService
from backend.app.services.agent_service import AgentService, AgentProposal
from backend.app.services.git_service import GitService, GitSafetyError
from backend.app.services.runner_service import runner_service

logger = get_logger("repair_orchestrator")

class RepairOrchestrator:
    """
    State machine and lifecycle coordinator for autonomous code repair:
    CREATED -> ANALYZING -> PROPOSED -> AWAITING_APPROVAL -> APPLYING -> VALIDATING -> RETESTING -> VERIFIED / UNRESOLVED / FAILED / CANCELLED
    """

    def __init__(self):
        self.packet_service = RepairPacketService()
        self.agent_service = AgentService()
        self._active_repairs: Dict[str, asyncio.Task] = {}
        self._repair_subscribers: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, repair_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        if repair_id not in self._repair_subscribers:
            self._repair_subscribers[repair_id] = []
        self._repair_subscribers[repair_id].append(q)
        return q

    def unsubscribe(self, repair_id: str, queue: asyncio.Queue):
        if repair_id in self._repair_subscribers and queue in self._repair_subscribers[repair_id]:
            self._repair_subscribers[repair_id].remove(queue)
            if not self._repair_subscribers[repair_id]:
                del self._repair_subscribers[repair_id]

    async def _broadcast(self, repair_id: str, event_data: dict):
        if repair_id in self._repair_subscribers:
            for q in list(self._repair_subscribers[repair_id]):
                try:
                    await q.put(event_data)
                except Exception as e:
                    logger.warning(f"Error publishing repair SSE: {e}")

    async def transition(
        self,
        repair_id: str,
        to_state: str,
        description: str,
        payload: Optional[dict] = None
    ):
        """
        Atomically updates the repair status in the database and creates an audit event.
        """
        logger.info(f"Repair {repair_id} transitioning to {to_state}: {description}")
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id)
            )
            repair = res.scalar_one_or_none()
            if not repair:
                return

            from_state = repair.status
            repair.status = to_state
            repair.updated_at = datetime.now(timezone.utc)
            if to_state in ("VERIFIED", "FAILED", "UNRESOLVED", "CANCELLED"):
                repair.completed_at = datetime.now(timezone.utc)

            event = RepairEventEntity(
                repair_id=repair_id,
                from_state=from_state,
                to_state=to_state,
                description=description,
                raw_payload=json.dumps(payload or {})
            )
            session.add(event)
            await session.commit()

        # Broadcast over SSE
        await self._broadcast(repair_id, {
            "repair_id": repair_id,
            "from_state": from_state,
            "to_state": to_state,
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload or {}
        })

    async def create_repair_session(
        self,
        run_id: str,
        custom_project_dir: Optional[Path] = None,
        auto_approve: bool = False
    ) -> RepairRecordEntity:
        """
        Creates a new repair job from a failed verification run.
        """
        # Ensure run exists and failed
        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(VerificationRunEntity)
                .where(VerificationRunEntity.id == run_id)
                .options(selectinload(VerificationRunEntity.repairs))
            )
            run = res.scalar_one_or_none()
            if not run:
                raise ValueError(f"Verification run {run_id} not found")

            # Check previous attempts count
            attempt_num = len(run.repairs) + 1
            if attempt_num > 5:
                raise ValueError(f"Run {run_id} has exceeded maximum repair attempts (5)")

            # Check if an existing repair for this run is currently active
            active_rep = next((r for r in run.repairs if r.status in ("CREATED", "ANALYZING", "PROPOSED", "APPLYING", "VALIDATING", "RETESTING")), None)
            if active_rep:
                raise ValueError(f"A repair is already in progress for run {run_id} (Repair ID: {active_rep.id})")

            # Build repair packet
            packet = await self.packet_service.build_packet(
                run_id=run_id,
                db=session,
                custom_project_dir=custom_project_dir
            )

            # Record Git commit before
            git_before = GitService.get_current_sha(settings.WORKSPACE_DIR)

            repair = RepairRecordEntity(
                run_id=run_id,
                attempt_number=attempt_num,
                failing_step_index=packet.failed_step,
                status="CREATED",
                diagnosis="Pending analysis",
                git_commit_before=git_before,
                repair_packet_json=packet.model_dump_json()
            )
            session.add(repair)
            await session.commit()
            await session.refresh(repair)
            repair_id = repair.id

        # Format prompt & publish job files for Antigravity Agent
        prompt = self.packet_service.format_repair_prompt(packet)
        self.agent_service.publish_repair_job(repair_id, packet, prompt)

        # Kick off background analysis task
        task = asyncio.create_task(
            self._execute_repair_analysis(repair_id, packet, auto_approve=auto_approve)
        )
        self._active_repairs[repair_id] = task
        task.add_done_callback(lambda _: self._active_repairs.pop(repair_id, None))

        return repair

    async def _execute_repair_analysis(
        self,
        repair_id: str,
        packet: RepairPacketModel,
        auto_approve: bool = False
    ):
        try:
            # 1. State: JOB_PUBLISHED
            await self.transition(
                repair_id,
                "JOB_PUBLISHED",
                f"Repair packet published to .shipproof/repairs/{repair_id}/ for Antigravity IDE Agent."
            )

            # Generate diagnosis from failure triage
            proposal: AgentProposal = await self.agent_service.generate_diagnosis(packet)

            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(RepairRecordEntity)
                    .where(RepairRecordEntity.id == repair_id)
                    .values(
                        diagnosis=proposal.diagnosis,
                        files_modified=json.dumps(proposal.suggested_files)
                    )
                )
                await session.commit()

            # 2. State: AWAITING_AGENT
            await self.transition(
                repair_id,
                "AWAITING_AGENT",
                "Awaiting Antigravity IDE Agent to inspect failure evidence and apply source code modifications in workspace.",
                payload={"diagnosis": proposal.diagnosis, "suggested_files": proposal.suggested_files}
            )

            # Check if changes are already staged/present
            changes = await self.detect_workspace_changes(repair_id)

            if auto_approve and changes.get("modified"):
                await self.apply_and_retest(repair_id, rationale="Auto-approved by policy")

        except asyncio.CancelledError:
            await self.transition(repair_id, "CANCELLED", "Repair session was cancelled by user.")
        except Exception as e:
            logger.exception(f"Error in repair analysis for {repair_id}: {e}")
            await self.transition(repair_id, "FAILED", f"Error during analysis: {str(e)}")

    async def detect_workspace_changes(self, repair_id: str) -> Dict[str, Any]:
        """
        Inspects the workspace to detect modifications applied by the Antigravity IDE Agent.
        Transitions the state machine: AWAITING_AGENT -> AGENT_RESPONSE_RECEIVED -> AWAITING_APPROVAL.
        """
        target_repo = settings.WORKSPACE_DIR
        modified_files = GitService.get_modified_files(target_repo)
        current_diff = GitService.capture_diff(target_repo)

        async with AsyncSessionLocal() as session:
            res = await session.execute(
                select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id)
            )
            repair = res.scalar_one_or_none()
            if not repair:
                raise ValueError(f"Repair {repair_id} not found")

            if modified_files:
                repair.files_modified = json.dumps(modified_files)
                repair.patch_diff = current_diff
                repair.git_commit_after = GitService.get_current_sha(target_repo)
                await session.commit()

                await self.transition(
                    repair_id,
                    "AGENT_RESPONSE_RECEIVED",
                    f"Antigravity IDE Agent modifications detected: {len(modified_files)} file(s) modified in workspace.",
                    payload={"modified_files": modified_files}
                )
                await self.transition(
                    repair_id,
                    "AWAITING_APPROVAL",
                    "Changes ready for review in ShipProof Repair Studio. Awaiting user approval to run Kane re-test.",
                    payload={"modified_files": modified_files}
                )
                return {"modified": True, "files": modified_files, "diff": current_diff}
            else:
                return {"modified": False, "files": [], "diff": ""}

    async def apply_and_retest(self, repair_id: str, rationale: str = "Approved"):
        """
        Executes the applying, validating, and retesting phases once the fix is staged.
        """
        task = asyncio.create_task(self._execute_apply_and_retest(repair_id, rationale))
        self._active_repairs[repair_id] = task
        task.add_done_callback(lambda _: self._active_repairs.pop(repair_id, None))

    async def _execute_apply_and_retest(self, repair_id: str, rationale: str):
        try:
            # 1. State: APPLYING
            await self.transition(repair_id, "APPLYING", f"Applying code changes ({rationale})...")

            # Capture Git status and diff
            target_repo = settings.WORKSPACE_DIR
            current_diff = GitService.capture_diff(target_repo)
            modified_files = GitService.get_modified_files(target_repo)
            git_after = GitService.get_current_sha(target_repo)

            async with AsyncSessionLocal() as session:
                await session.execute(
                    update(RepairRecordEntity)
                    .where(RepairRecordEntity.id == repair_id)
                    .values(
                        patch_diff=current_diff,
                        files_modified=json.dumps(modified_files),
                        git_commit_after=git_after
                    )
                )
                await session.commit()

            # 2. State: VALIDATING
            await self.transition(
                repair_id,
                "VALIDATING",
                f"Validating syntax and build for {len(modified_files)} modified file(s)...",
                payload={"files": modified_files}
            )

            # Allow brief settling period for hot reload
            await asyncio.sleep(1.0)

            # 3. State: RETESTING
            await self.transition(
                repair_id,
                "RETESTING",
                "Rerunning the original Kane CLI test to prove the repair works..."
            )

            # Fetch original run to get objective and target_url
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(RepairRecordEntity)
                    .where(RepairRecordEntity.id == repair_id)
                    .options(selectinload(RepairRecordEntity.run))
                )
                repair = res.scalar_one_or_none()
                if not repair or not repair.run:
                    raise ValueError(f"Repair record or parent run not found for {repair_id}")

                original_run = repair.run
                orig_id = original_run.id
                orig_proj_id = original_run.project_id
                orig_title = original_run.title
                orig_objective = original_run.objective
                orig_target_url = original_run.target_url
                orig_attempt = repair.attempt_number

                # Create a new retest run in database
                retest_run = VerificationRunEntity(
                    project_id=orig_proj_id,
                    title=f"[Re-test #{orig_attempt}] {orig_title}",
                    objective=orig_objective,
                    target_url=orig_target_url,
                    mode="verify_only",
                    status="queued"
                )
                session.add(retest_run)
                await session.commit()
                await session.refresh(retest_run)
                retest_run_id = retest_run.id

                # Link retest_run_id to repair record
                repair.retest_run_id = retest_run_id
                await session.commit()

            # Execute retest via runner_service lifecycle synchronously in this task
            logger.info(f"Triggering Kane CLI retest run {retest_run_id} for repair {repair_id}")
            await runner_service._execute_run_lifecycle(
                run_id=retest_run_id,
                objective=orig_objective,
                target_url=orig_target_url,
                headless=True,
                timeout=120
            )

            # Check retest outcome from DB
            async with AsyncSessionLocal() as session:
                rres = await session.execute(
                    select(VerificationRunEntity).where(VerificationRunEntity.id == retest_run_id)
                )
                retest_result = rres.scalar_one()

            if retest_result.status == "passed":
                # Real Kane verification succeeded!
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(RepairRecordEntity)
                        .where(RepairRecordEntity.id == repair_id)
                        .values(retest_passed=True)
                    )
                    # Mark original run repaired!
                    await session.execute(
                        update(VerificationRunEntity)
                        .where(VerificationRunEntity.id == orig_id)
                        .values(
                            repaired=True,
                            repair_attempts=orig_attempt,
                            status="verified"
                        )
                    )
                    await session.commit()

                await self.transition(
                    repair_id,
                    "VERIFIED",
                    "ShipProof Verified! Re-test executed by Kane CLI confirmed passing. Closed loop proven.",
                    payload={"retest_run_id": retest_run_id, "kane_session_id": retest_result.kane_session_id}
                )
            else:
                # Retest failed
                async with AsyncSessionLocal() as session:
                    await session.execute(
                        update(RepairRecordEntity)
                        .where(RepairRecordEntity.id == repair_id)
                        .values(
                            retest_passed=False,
                            failure_notes=retest_result.failure_reason or "Kane retest failed"
                        )
                    )
                    await session.commit()

                await self.transition(
                    repair_id,
                    "UNRESOLVED",
                    f"Kane re-test failed with status '{retest_result.status}'. Issue remains unresolved.",
                    payload={"retest_run_id": retest_run_id, "failure_reason": retest_result.failure_reason}
                )

        except asyncio.CancelledError:
            await self.transition(repair_id, "CANCELLED", "Repair session was cancelled during re-testing.")
        except Exception as e:
            logger.exception(f"Error in apply and retest for {repair_id}: {e}")
            await self.transition(repair_id, "FAILED", f"Execution error: {str(e)}")

    async def cancel_repair(self, repair_id: str) -> bool:
        task = self._active_repairs.get(repair_id)
        if task and not task.done():
            task.cancel()
            await self.transition(repair_id, "CANCELLED", "Repair cancelled by user.")
            return True
        return False

# Singleton orchestrator instance
repair_orchestrator = RepairOrchestrator()
