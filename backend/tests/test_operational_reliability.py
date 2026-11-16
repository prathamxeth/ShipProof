import pytest
import asyncio
from httpx import AsyncClient
from datetime import datetime, timezone
from sqlalchemy import update, select
from unittest.mock import patch

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import VerificationRunEntity, RepairRecordEntity
from backend.app.services.repair_orchestrator import repair_orchestrator
from backend.app.services.runner_service import runner_service
from backend.app.services.kane_service import KaneService, KaneExecutionResult
from backend.app.main import recover_interrupted_states

# --- A. Repair Concurrency & State Machine Atomicity ---

@pytest.mark.asyncio
async def test_concurrent_approvals_prevent_duplicate_retests(client: AsyncClient):
    """
    Test two simultaneous approval requests for the same repair.
    Atomicity in database & memory ensures only one approval proceeds,
    preventing duplicate execution and race conditions.
    """
    # 1. Create a failed run and a repair session
    run_res = await client.post("/api/runs", json={
        "title": "Race Condition Run",
        "objective": "Verify race conditions",
        "target_url": "http://localhost:3005"
    })
    run_id = run_res.json()["id"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed", failure_reason="Test checkout failure")
        )
        await session.commit()

    rep_res = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": False})
    repair_id = rep_res.json()["id"]

    # Wait for initial repair analysis task to reach AWAITING_APPROVAL
    for _ in range(15):
        await asyncio.sleep(0.1)
        res = await client.get(f"/api/repairs/{repair_id}")
        if res.json()["status"] in ("AWAITING_APPROVAL", "AWAITING_AGENT"):
            break

    # Stage a simulated patch diff
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RepairRecordEntity)
            .where(RepairRecordEntity.id == repair_id)
            .values(
                status="AWAITING_APPROVAL",
                patch_diff="diff --git a/test b/test\n+fix",
                files_modified='["test.py"]'
            )
        )
        await session.commit()

    # Clear active analysis task if still lingering
    repair_orchestrator._active_repairs.pop(repair_id, None)

    # 2. Fire two concurrent approval requests
    async def call_approve():
        return await client.post(f"/api/repairs/{repair_id}/approve", json={"rationale": "Concurrent test"})

    resp1, resp2 = await asyncio.gather(call_approve(), call_approve())

    # Exactly one must succeed (200 OK) and the other must be rejected (400 Bad Request or 409 Conflict)
    status_codes = sorted([resp1.status_code, resp2.status_code])
    assert status_codes[0] == 200
    assert status_codes[1] in (400, 409)

@pytest.mark.asyncio
async def test_approval_without_modifications_rejected(client: AsyncClient):
    """
    Verify that an approval attempt on a repair with no detected workspace modifications
    is rejected with HTTP 400.
    """
    run_res = await client.post("/api/runs", json={
        "title": "No Modifications Run",
        "objective": "Verify clean workspace approval rejection",
        "target_url": "http://localhost:3005"
    })
    run_id = run_res.json()["id"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed", failure_reason="Initial failure")
        )
        await session.commit()

    rep_res = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": False})
    repair_id = rep_res.json()["id"]

    for _ in range(15):
        await asyncio.sleep(0.1)
        res = await client.get(f"/api/repairs/{repair_id}")
        if res.json()["status"] in ("AWAITING_APPROVAL", "AWAITING_AGENT"):
            break

    repair_orchestrator._active_repairs.pop(repair_id, None)

    # Explicitly set status to AWAITING_APPROVAL but with NO patch diff
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RepairRecordEntity)
            .where(RepairRecordEntity.id == repair_id)
            .values(status="AWAITING_APPROVAL", patch_diff="", files_modified="[]")
        )
        await session.commit()

    # Attempt approve when workspace is clean
    with patch("backend.app.services.git_service.GitService.inspect_status") as mock_git:
        mock_git.return_value.is_clean = True
        approve_res = await client.post(f"/api/repairs/{repair_id}/approve")
        assert approve_res.status_code == 400
        assert "no workspace modifications" in approve_res.json()["error"]["message"]

@pytest.mark.asyncio
async def test_approval_after_verified_rejected(client: AsyncClient):
    """
    Verify that approval cannot be called on a repair that is already VERIFIED.
    """
    run_res = await client.post("/api/runs", json={
        "title": "Already Verified Run",
        "objective": "Verify approval rejection on finalized repair",
        "target_url": "http://localhost:3005"
    })
    run_id = run_res.json()["id"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed")
        )
        await session.commit()

    rep_res = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": False})
    repair_id = rep_res.json()["id"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(RepairRecordEntity)
            .where(RepairRecordEntity.id == repair_id)
            .values(status="VERIFIED", retest_passed=True)
        )
        await session.commit()

    approve_res = await client.post(f"/api/repairs/{repair_id}/approve")
    assert approve_res.status_code == 400
    assert "cannot be approved" in approve_res.json()["error"]["message"]

@pytest.mark.asyncio
async def test_concurrent_repairs_for_same_run_rejected(client: AsyncClient):
    """
    Ensure only one active/pending repair can exist for a run at any time.
    """
    run_res = await client.post("/api/runs", json={
        "title": "Concurrent Repairs Parent Run",
        "objective": "Verify duplicate repair prevention",
        "target_url": "http://localhost:3005"
    })
    run_id = run_res.json()["id"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed")
        )
        await session.commit()

    # First repair session
    rep1 = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": False})
    assert rep1.status_code == 201

    # Second repair session against the same run while first is active
    rep2 = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": False})
    assert rep2.status_code == 400
    assert "already in progress" in rep2.json()["error"]["message"]

@pytest.mark.asyncio
async def test_repair_with_nonexistent_parent_run_rejected(client: AsyncClient):
    """
    Verify that repair request for nonexistent parent run returns 404.
    """
    res = await client.post("/api/repairs", json={"run_id": "00000000-0000-0000-0000-000000000000"})
    assert res.status_code == 404

# --- B. Process Reliability & Terminal States ---

@pytest.mark.asyncio
async def test_kane_executable_missing_reaches_truthful_error_state():
    """
    Verify that if the Kane executable is missing or raises FileNotFoundError,
    runner_service catches the exception and transitions the run to 'error' (never hung in 'running').
    """
    async with AsyncSessionLocal() as session:
        run = VerificationRunEntity(
            title="Missing Executable Run",
            objective="Test missing CLI error handling",
            target_url="http://localhost:3005",
            status="queued"
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    with patch.object(KaneService, "run_kane", side_effect=FileNotFoundError("kane-cli binary not found")):
        await runner_service._execute_run_lifecycle(
            run_id=run_id,
            objective="Test",
            target_url="http://localhost:3005",
            headless=True,
            timeout=120
        )

    # Verify run record in DB reached truthful terminal 'error' state
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))
        updated_run = res.scalar_one()
        assert updated_run.status == "error"
        assert updated_run.exit_code == -1
        assert "not found" in str(updated_run.failure_reason)

# --- C. Persistence, Server Restart & Recovery ---

@pytest.mark.asyncio
async def test_startup_recovery_interrupted_runs_and_repairs():
    """
    Test recovery of transient states on server restart.
    Interrupted runs become 'incomplete' and repairs become 'FAILED'.
    Neither is silently marked as passed or verified.
    """
    async with AsyncSessionLocal() as session:
        # Create an orphaned active run
        orphan_run = VerificationRunEntity(
            title="Orphaned Running Test",
            objective="Simulate server crash mid-run",
            target_url="http://localhost:3005",
            status="running"
        )
        session.add(orphan_run)

        # Create an orphaned queued run
        orphan_queued = VerificationRunEntity(
            title="Orphaned Queued Test",
            objective="Simulate server crash while queued",
            target_url="http://localhost:3005",
            status="queued"
        )
        session.add(orphan_queued)

        # Create an active retesting repair
        orphan_repair = RepairRecordEntity(
            run_id="dummy-parent-id",
            attempt_number=1,
            status="RETESTING"
        )
        session.add(orphan_repair)
        await session.commit()

        run_id = orphan_run.id
        queued_id = orphan_queued.id
        repair_id = orphan_repair.id

    # Execute startup recovery routine
    await recover_interrupted_states()

    # Verify states were cleanly and truthfully finalized
    async with AsyncSessionLocal() as session:
        r1 = (await session.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == run_id))).scalar_one()
        r2 = (await session.execute(select(VerificationRunEntity).where(VerificationRunEntity.id == queued_id))).scalar_one()
        rep = (await session.execute(select(RepairRecordEntity).where(RepairRecordEntity.id == repair_id))).scalar_one()

        assert r1.status == "incomplete"
        assert "interrupted" in str(r1.failure_reason).lower()
        assert r2.status == "incomplete"
        assert rep.status == "FAILED"
        assert "interrupted" in str(rep.failure_notes).lower()

# --- D. SSE Subscriber Cleanliness ---

@pytest.mark.asyncio
async def test_sse_subscriber_lifecycle_and_cleanup():
    """
    Verify subscriber queues are created on subscribe and cleaned up on unsubscribe.
    """
    test_run_id = "sse-clean-test-123"
    q = runner_service.subscribe(test_run_id)
    assert test_run_id in runner_service._event_subscribers
    assert q in runner_service._event_subscribers[test_run_id]

    runner_service.unsubscribe(test_run_id, q)
    assert test_run_id not in runner_service._event_subscribers
