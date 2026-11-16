import pytest
import json
import asyncio
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.entities import VerificationRunEntity, VerificationEventEntity
from backend.app.services.runner_service import runner_service

@pytest.mark.asyncio
async def test_durable_sse_replay_and_sequence():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a run and add 4 events with sequence numbers
        run_id = "test-durable-sse-run"
        async with AsyncSessionLocal() as session:
            run = VerificationRunEntity(
                id=run_id,
                title="SSE Reconnect Test",
                objective="Test durable SSE recovery",
                target_url="http://127.0.0.1:3005",
                status="passed"
            )
            session.add(run)

            for seq in range(1, 5):
                ev = VerificationEventEntity(
                    run_id=run_id,
                    event_seq=seq,
                    event_type="step" if seq < 4 else "completed",
                    step_number=seq if seq < 4 else None,
                    status="passed",
                    description=f"Step {seq} description",
                    raw_event=json.dumps({"event": "step", "step": seq})
                )
                session.add(ev)
            await session.commit()

        # 2. Query static events list
        static_resp = await client.get(f"/api/runs/{run_id}/events")
        assert static_resp.status_code == 200
        events_list = static_resp.json()
        assert len(events_list) == 4
        assert [e["event_seq"] for e in events_list] == [1, 2, 3, 4]

        # 3. Stream all events (no Last-Event-ID)
        sse_all = await client.get(f"/api/runs/{run_id}/events?stream=true")
        assert sse_all.status_code == 200
        lines = sse_all.text.split("\n")
        ids = [l.replace("id: ", "").strip() for l in lines if l.startswith("id: ")]
        assert ids == ["1", "2", "3", "4"]

        # 4. Stream reconnect with Last-Event-ID header = 2
        # Should only replay sequence > 2 (i.e. 3 and 4)
        sse_reconnect = await client.get(
            f"/api/runs/{run_id}/events?stream=true",
            headers={"Last-Event-ID": "2"}
        )
        assert sse_reconnect.status_code == 200
        lines_reconnect = sse_reconnect.text.split("\n")
        ids_reconnect = [l.replace("id: ", "").strip() for l in lines_reconnect if l.startswith("id: ")]
        assert ids_reconnect == ["3", "4"]

        # 5. Stream reconnect via query parameter ?last_event_id=3
        # Should only replay sequence 4
        sse_query_param = await client.get(f"/api/runs/{run_id}/events?stream=true&last_event_id=3")
        assert sse_query_param.status_code == 200
        lines_param = sse_query_param.text.split("\n")
        ids_param = [l.replace("id: ", "").strip() for l in lines_param if l.startswith("id: ")]
        assert ids_param == ["4"]
