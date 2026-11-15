import pytest
import asyncio
import json
from pathlib import Path
from unittest.mock import patch
from httpx import AsyncClient

from backend.app.core.config import settings
from backend.app.services.agent_service import AgentService, AgentCapabilities, AgentProposal
from backend.app.services.git_service import GitService, GitStatus
from backend.app.services.repair_packet_service import RepairPacketService
from backend.app.services.repair_orchestrator import repair_orchestrator
from backend.app.services.kane_service import KaneService, KaneExecutionResult
from backend.app.services.kane_parser import NormalizedEvent

@pytest.mark.asyncio
async def test_agent_capabilities_detection():
    caps = AgentService.detect_capabilities()
    assert isinstance(caps.cli_installed, bool)
    assert caps.preferred_mode == "ide_agent"
    assert "gemini-3.8-flash-high" in caps.supported_models or not caps.cli_installed
    # Ensure headless tools without user prompt is false (Rule 8 compliance: no dangerously skip permissions)
    assert caps.supports_headless_tools is False

@pytest.mark.asyncio
async def test_repair_packet_generation_and_sanitization(client: AsyncClient, tmp_path: Path):
    packet_service = RepairPacketService()
    
    # 1. Create a failed verification run
    create_res = await client.post("/api/runs", json={
        "title": "Failed Checkout Test",
        "objective": "Add headphones and checkout",
        "target_url": "http://localhost:3005"
    })
    run_id = create_res.json()["id"]

    # 2. Add a failed step and evidence
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.entities import VerificationStepEntity, VerificationRunEntity
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        step = VerificationStepEntity(
            run_id=run_id,
            step_index=2,
            status="failed",
            remark="assert: Checkout button disabled by defect"
        )
        session.add(step)
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed", failure_reason="assert: Checkout button disabled by defect")
        )
        await session.commit()

        # Build packet
        packet = await packet_service.build_packet(run_id, session, custom_project_dir=settings.WORKSPACE_DIR / "demo_targets" / "sample_store")

    assert packet.run_id == run_id
    assert packet.failed_step == 2
    assert "Checkout button disabled" in packet.failure_message
    assert packet.target_url == "http://localhost:3005"
    assert len(packet.relevant_files) > 0

    # Format prompt
    prompt = packet_service.format_repair_prompt(packet)
    assert "# ShipProof Autonomous Repair Request" in prompt
    assert "Failed Step Index:" in prompt
    assert "Candidate Source Files:" in prompt

@pytest.mark.asyncio
async def test_git_service_diff_and_safety(tmp_path: Path):
    # Test status check on workspace
    status = GitService.inspect_status(settings.WORKSPACE_DIR)
    assert isinstance(status.is_clean, bool)
    assert status.current_sha is not None

    # Test modification validation boundary
    allowed_dir = settings.WORKSPACE_DIR / "demo_targets" / "sample_store"
    is_valid, violations = GitService.validate_modifications(settings.WORKSPACE_DIR, allowed_dir)
    # Violations should be a list
    assert isinstance(violations, list)

@pytest.mark.asyncio
async def test_repair_lifecycle_and_approval_requirement(client: AsyncClient):
    # 1. Create a failed run
    create_res = await client.post("/api/runs", json={
        "title": "Broken Cart Verification",
        "objective": "Verify checkout completes",
        "target_url": "http://localhost:3005"
    })
    run_id = create_res.json()["id"]

    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.entities import VerificationRunEntity
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed", failure_reason="Proceed to Checkout button not clickable")
        )
        await session.commit()

    # 2. Trigger repair creation
    repair_res = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": False})
    assert repair_res.status_code == 201
    repair_data = repair_res.json()
    repair_id = repair_data["id"]

    # Wait for analysis to transition to AWAITING_APPROVAL
    await asyncio.sleep(0.5)

    detail_res = await client.get(f"/api/repairs/{repair_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["status"] in ("AWAITING_APPROVAL", "AWAITING_AGENT", "JOB_PUBLISHED", "AGENT_RESPONSE_RECEIVED", "PROPOSED", "ANALYZING")
    assert detail["attempt_number"] == 1

@pytest.mark.asyncio
async def test_repair_cannot_exceed_retry_limit(client: AsyncClient):
    # Create run and fake 5 attempts
    create_res = await client.post("/api/runs", json={
        "title": "Exhausted Retries Test",
        "objective": "Check retry limits",
        "target_url": "http://localhost:3005"
    })
    run_id = create_res.json()["id"]

    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.entities import RepairRecordEntity, VerificationRunEntity
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed")
        )
        for i in range(1, 6):
            session.add(RepairRecordEntity(
                run_id=run_id,
                attempt_number=i,
                status="UNRESOLVED"
            ))
        await session.commit()

    # 6th attempt must be rejected
    fail_res = await client.post("/api/repairs", json={"run_id": run_id})
    assert fail_res.status_code == 400
    assert "exceeded maximum repair attempts" in fail_res.json()["error"]["message"]

@pytest.mark.asyncio
async def test_repair_cancellation(client: AsyncClient):
    create_res = await client.post("/api/runs", json={
        "title": "Repair Cancellation Test",
        "objective": "Verify cancellation",
        "target_url": "http://localhost:3005"
    })
    run_id = create_res.json()["id"]

    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.entities import VerificationRunEntity
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed")
        )
        await session.commit()

    repair_res = await client.post("/api/repairs", json={"run_id": run_id})
    repair_id = repair_res.json()["id"]

    cancel_res = await client.post(f"/api/repairs/{repair_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

@pytest.mark.asyncio
async def test_retest_passed_marks_verified(client: AsyncClient):
    # Mock KaneService so retest passes
    mock_events = [
        NormalizedEvent(event_type="stream_start"),
        NormalizedEvent(event_type="step", step_number=1, status="done", description="Navigated to cart"),
        NormalizedEvent(event_type="step", step_number=2, status="done", description="Clicked checkout"),
        NormalizedEvent(event_type="run_end", status="passed", description="Order confirmed", raw_event={"status": "passed"})
    ]

    async def mock_run_kane(*args, **kwargs):
        cb = kwargs.get("event_callback")
        if cb:
            for ev in mock_events:
                await cb(ev)
        return KaneExecutionResult(
            run_id=kwargs.get("run_id", "retest-pass"),
            exit_code=0,
            status="passed",
            raw_stdout_path="/tmp/out",
            raw_stderr_path="/tmp/err",
            events=mock_events,
            run_end_event=mock_events[-1]
        )

    # 1. Create failed run
    create_res = await client.post("/api/runs", json={
        "title": "Closed Loop Pass Test",
        "objective": "Add to cart and checkout",
        "target_url": "http://localhost:3005"
    })
    run_id = create_res.json()["id"]

    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.entities import VerificationRunEntity
    from sqlalchemy import update

    async with AsyncSessionLocal() as session:
        await session.execute(
            update(VerificationRunEntity)
            .where(VerificationRunEntity.id == run_id)
            .values(status="failed", failure_reason="Checkout button disabled")
        )
        await session.commit()

    mock_proposal = AgentProposal(
        repair_id=run_id,
        diagnosis="Fix disabled checkout button in cart.html",
        rationale="Button has disabled attribute",
        suggested_files=["templates/cart.html"]
    )

    with patch.object(KaneService, "run_kane", side_effect=mock_run_kane), \
         patch.object(AgentService, "generate_diagnosis", return_value=mock_proposal):
        # 2. Create repair
        rep_res = await client.post("/api/repairs", json={"run_id": run_id, "auto_approve": True})
        repair_id = rep_res.json()["id"]

        # Poll until status reaches terminal state
        det = None
        for _ in range(20):
            await asyncio.sleep(0.2)
            det_res = await client.get(f"/api/repairs/{repair_id}")
            det = det_res.json()
            if det["status"] in ("VERIFIED", "FAILED", "UNRESOLVED", "CANCELLED"):
                break

        # 3. Verify final status is VERIFIED
        assert det is not None
        assert det["status"] == "VERIFIED"
        assert det["retest_passed"] is True
        assert det["retest_run_id"] is not None

        # 4. Verify parent run status is verified
        run_res = await client.get(f"/api/runs/{run_id}")
        assert run_res.json()["repaired"] is True
        assert run_res.json()["status"] == "verified"
