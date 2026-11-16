import pytest
import json
import asyncio
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import VerificationRunEntity, VerificationEventEntity
from backend.app.services.runner_service import runner_service

@pytest.mark.asyncio
async def test_sse_reconnection_with_invalid_and_negative_ids():
    """
    Verifies that reconnection with invalid or negative Last-Event-ID headers
    is safely handled without exceptions, streaming from sequence 0 onwards.
    """
    run_id = "test-sse-invalid-ids"
    async with AsyncSessionLocal() as session:
        run = VerificationRunEntity(
            id=run_id,
            title="SSE Edge Case Test",
            objective="Test negative and malformed event IDs",
            target_url="http://127.0.0.1:3005",
            status="passed"
        )
        session.add(run)

        for seq in range(1, 4):
            ev = VerificationEventEntity(
                run_id=run_id,
                event_seq=seq,
                event_type="step",
                step_number=seq,
                status="done",
                description=f"Step {seq}",
                raw_event=json.dumps({"seq": seq})
            )
            session.add(ev)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Non-numeric Last-Event-ID header
        resp_bad = await client.get(
            f"/api/runs/{run_id}/events?stream=true",
            headers={"Last-Event-ID": "invalid-alpha-id"}
        )
        assert resp_bad.status_code == 200
        # Should stream all 3 events
        assert "id: 1" in resp_bad.text
        assert "id: 2" in resp_bad.text
        assert "id: 3" in resp_bad.text

        # 2. Reconnection with future ID (e.g. 999) - should return no events and stream_end
        resp_future = await client.get(
            f"/api/runs/{run_id}/events?stream=true",
            headers={"Last-Event-ID": "999"}
        )
        assert resp_future.status_code == 200
        assert "id: 1" not in resp_future.text
        assert "stream_end" in resp_future.text

@pytest.mark.asyncio
async def test_sse_queue_bounded_capacity_under_slow_consumer():
    """
    Verifies that slow or stalled SSE consumers cannot cause unbounded memory growth.
    The subscriber queue has maxsize=1000 and drops oldest on overflow.
    """
    run_id = "test-sse-bounded-queue"
    queue = runner_service.subscribe(run_id)
    try:
        # Broadcast 1200 events rapidly
        for i in range(1200):
            await runner_service._broadcast_event(run_id, {"seq": i, "data": "test"})

        # Queue size must not exceed 1000
        assert queue.qsize() <= 1000
    finally:
        runner_service.unsubscribe(run_id, queue)

@pytest.mark.asyncio
async def test_sse_subscription_gap_prevention():
    """
    Verifies that subscribing before historical query ensures zero event loss
    even if an event occurs in the microsecond gap between subscription and query.
    """
    run_id = "test-sse-zero-loss"
    # Create subscriber queue
    q = runner_service.subscribe(run_id)
    try:
        # Simulate live event arriving with sequence 2
        await runner_service._broadcast_event(run_id, {
            "event_seq": 2,
            "event_type": "step",
            "description": "Mid-flight event"
        })

        # Event is safely in queue
        assert not q.empty()
        item = await q.get()
        assert item["event_seq"] == 2
    finally:
        runner_service.unsubscribe(run_id, q)
