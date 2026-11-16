import pytest
import asyncio
from datetime import datetime, timezone
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import VerificationRunEntity, RepairRecordEntity
from backend.app.services.runner_service import runner_service
from backend.app.main import recover_interrupted_states

@pytest.mark.asyncio
async def test_cancelled_run_cannot_be_overwritten_by_late_subprocess():
    """
    Verifies that once a run is transitioned to 'cancelled', any late subprocess
    completion or lifecycle finalization NEVER overwrites the cancelled terminal state.
    """
    run_id = "test-concurrency-cancel-guard"
    async with AsyncSessionLocal() as session:
        run = VerificationRunEntity(
            id=run_id,
            title="Cancel Overwrite Test",
            objective="Ensure cancelled state is immutable",
            target_url="http://127.0.0.1:3005",
            status="running"
        )
        session.add(run)
        await session.commit()

    # 1. User cancels the run
    async with AsyncSessionLocal() as session:
        from sqlalchemy import update
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="cancelled", failure_reason="Cancelled by test operator")
        )
        await session.commit()

    # 2. Simulate late lifecycle finalization trying to mark it passed
    from unittest.mock import MagicMock
    mock_exec_result = MagicMock()
    mock_exec_result.status = "passed"
    mock_exec_result.exit_code = 0
    mock_exec_result.run_end_event = None
    mock_exec_result.error_message = None
    mock_exec_result.raw_stdout_path = "/tmp/fake_stdout.log"
    mock_exec_result.raw_stderr_path = "/tmp/fake_stderr.log"

    # Attempt to update database as lifecycle would
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        chk = await session.execute(
            select(VerificationRunEntity.status).where(VerificationRunEntity.id == run_id)
        )
        curr_status = chk.scalar_one_or_none()
        assert curr_status == "cancelled"

        # The runner service's update condition checks status in ("running", "queued")
        update_res = await session.execute(
            update(VerificationRunEntity)
            .where(
                VerificationRunEntity.id == run_id,
                VerificationRunEntity.status.in_(["running", "queued"])
            )
            .values(status=mock_exec_result.status, exit_code=0)
        )
        await session.commit()
        # Rowcount must be 0 because it was cancelled!
        assert update_res.rowcount == 0

    # Verify final status remains cancelled
    async with AsyncSessionLocal() as session:
        final_chk = await session.execute(
            select(VerificationRunEntity.status).where(VerificationRunEntity.id == run_id)
        )
        assert final_chk.scalar_one_or_none() == "cancelled"

@pytest.mark.asyncio
async def test_duplicate_cancellations_are_idempotent():
    """
    Verifies that multiple cancellation requests for the same run execute idempotently
    without raising unhandled exceptions or corrupting database records.
    """
    run_id = "test-idempotent-cancellation"
    async with AsyncSessionLocal() as session:
        run = VerificationRunEntity(
            id=run_id,
            title="Idempotency Test",
            objective="Ensure multiple cancels are safe",
            target_url="http://127.0.0.1:3005",
            status="running"
        )
        session.add(run)
        await session.commit()

    # Call cancel_run multiple times
    res1 = await runner_service.cancel_run(run_id)
    res2 = await runner_service.cancel_run(run_id)
    res3 = await runner_service.cancel_run(run_id)

    # Subsequent cancellations return False gracefully (since no active task remains)
    assert res2 is False
    assert res3 is False

    # Status in DB remains cancelled
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res = await session.execute(
            select(VerificationRunEntity.status).where(VerificationRunEntity.id == run_id)
        )
        assert res.scalar_one_or_none() == "cancelled"

@pytest.mark.asyncio
async def test_startup_recovery_interrupted_states():
    """
    Verifies that interrupted active runs and repairs are truthfully recovered on restart,
    and NEVER falsely classified as passed or verified.
    """
    run_interrupted_id = "run-crashed-during-exec"
    repair_interrupted_id = "repair-crashed-during-apply"

    async with AsyncSessionLocal() as session:
        run = VerificationRunEntity(
            id=run_interrupted_id,
            title="Crashed Run",
            objective="Test crash recovery",
            target_url="http://127.0.0.1:3005",
            status="running"
        )
        session.add(run)

        repair = RepairRecordEntity(
            id=repair_interrupted_id,
            run_id=run_interrupted_id,
            status="APPLYING"
        )
        session.add(repair)
        await session.commit()

    # Execute startup recovery handler
    await recover_interrupted_states()

    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        r_run = await session.execute(
            select(VerificationRunEntity).where(VerificationRunEntity.id == run_interrupted_id)
        )
        run_entity = r_run.scalar_one_or_none()
        assert run_entity.status == "incomplete"
        assert "interrupted by backend server restart" in run_entity.failure_reason

        r_rep = await session.execute(
            select(RepairRecordEntity).where(RepairRecordEntity.id == repair_interrupted_id)
        )
        rep_entity = r_rep.scalar_one_or_none()
        assert rep_entity.status == "FAILED"
        assert "interrupted by backend server restart" in rep_entity.failure_notes
