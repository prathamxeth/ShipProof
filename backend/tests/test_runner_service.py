import pytest
import asyncio
import json
from unittest.mock import patch
from httpx import AsyncClient
from backend.app.services.kane_service import KaneService, KaneExecutionResult
from backend.app.services.kane_parser import NormalizedEvent

@pytest.mark.asyncio
async def test_successful_run_lifecycle_and_persistence(client: AsyncClient):
    # Mock KaneService.run_kane to simulate a successful real execution
    mock_events = [
        NormalizedEvent(event_type="stream_start", session_id="/mock/session-101", description="Kane started"),
        NormalizedEvent(event_type="step", step_number=1, status="running", description="Navigate to URL"),
        NormalizedEvent(event_type="step", step_number=1, status="done", description="Navigated to URL"),
        NormalizedEvent(event_type="step", step_number=2, status="done", description="Clicked button"),
        NormalizedEvent(event_type="run_end", session_id="/mock/session-101", status="passed", description="Objective completed", raw_event={"status": "passed"})
    ]

    async def mock_run_kane(*args, **kwargs):
        callback = kwargs.get("event_callback")
        if callback:
            for ev in mock_events:
                await callback(ev)
        return KaneExecutionResult(
            run_id=kwargs.get("run_id", "test-run"),
            exit_code=0,
            status="passed",
            raw_stdout_path="/tmp/stdout.log",
            raw_stderr_path="/tmp/stderr.log",
            events=mock_events,
            run_end_event=mock_events[-1]
        )

    with patch.object(KaneService, "run_kane", side_effect=mock_run_kane):
        # 1. Create run via API
        create_res = await client.post("/api/runs", json={
            "title": "Mocked Kane Pass Test",
            "objective": "Verify page elements",
            "target_url": "http://localhost:3000"
        })
        assert create_res.status_code == 201
        run_data = create_res.json()
        run_id = run_data["id"]

        # Wait briefly for background execution to complete
        await asyncio.sleep(0.4)

        # 2. Historical retrieval via GET /api/runs/{id}
        get_res = await client.get(f"/api/runs/{run_id}")
        assert get_res.status_code == 200
        detail = get_res.json()
        assert detail["status"] == "passed"
        assert detail["exit_code"] == 0
        assert detail["kane_session_id"] in ("/mock/session-101", "session-101")
        assert detail["total_steps"] == 2
        assert detail["passed_steps"] == 2
        assert detail["failed_steps"] == 0
        assert len(detail["steps"]) == 2

        # 3. Retrieve events via GET /api/runs/{id}/events
        ev_res = await client.get(f"/api/runs/{run_id}/events")
        assert ev_res.status_code == 200
        events_list = ev_res.json()
        assert len(events_list) == len(mock_events)
        types = [e["event_type"] for e in events_list]
        assert "stream_start" in types
        assert "step" in types
        assert "run_end" in types

@pytest.mark.asyncio
async def test_failed_run_lifecycle(client: AsyncClient):
    mock_events = [
        NormalizedEvent(event_type="stream_start", session_id="/mock/session-102"),
        NormalizedEvent(event_type="step", step_number=1, status="done", description="Navigated to home"),
        NormalizedEvent(event_type="step", step_number=2, status="failed", description="Add to Cart button missing"),
        NormalizedEvent(event_type="run_end", session_id="/mock/session-102", status="failed", description="Element not found", raw_event={"status": "failed"})
    ]

    async def mock_run_kane(*args, **kwargs):
        callback = kwargs.get("event_callback")
        if callback:
            for ev in mock_events:
                await callback(ev)
        return KaneExecutionResult(
            run_id=kwargs.get("run_id", "test-run-fail"),
            exit_code=1,
            status="failed",
            raw_stdout_path="/tmp/stdout.log",
            raw_stderr_path="/tmp/stderr.log",
            events=mock_events,
            run_end_event=mock_events[-1]
        )

    with patch.object(KaneService, "run_kane", side_effect=mock_run_kane):
        create_res = await client.post("/api/runs", json={
            "title": "Mocked Kane Fail Test",
            "objective": "Verify add to cart",
            "target_url": "http://localhost:3000"
        })
        run_id = create_res.json()["id"]

        await asyncio.sleep(0.4)

        get_res = await client.get(f"/api/runs/{run_id}")
        assert get_res.status_code == 200
        detail = get_res.json()
        assert detail["status"] == "failed"
        assert detail["failed_steps"] == 1
        assert "Element not found" in detail["failure_reason"]

@pytest.mark.asyncio
async def test_missing_terminal_event_produces_incomplete(client: AsyncClient):
    mock_events = [
        NormalizedEvent(event_type="stream_start", session_id="/mock/session-103"),
        NormalizedEvent(event_type="step", step_number=1, status="done", description="Navigated")
    ]

    async def mock_run_kane(*args, **kwargs):
        callback = kwargs.get("event_callback")
        if callback:
            for ev in mock_events:
                await callback(ev)
        return KaneExecutionResult(
            run_id=kwargs.get("run_id", "test-run-incomplete"),
            exit_code=0,
            status="incomplete",
            raw_stdout_path="/tmp/stdout.log",
            raw_stderr_path="/tmp/stderr.log",
            events=mock_events,
            run_end_event=None,
            error_message="Missing terminal run_end event"
        )

    with patch.object(KaneService, "run_kane", side_effect=mock_run_kane):
        create_res = await client.post("/api/runs", json={
            "title": "Incomplete Test",
            "objective": "Check incomplete handling",
            "target_url": "http://localhost:3000"
        })
        run_id = create_res.json()["id"]

        await asyncio.sleep(0.4)

        get_res = await client.get(f"/api/runs/{run_id}")
        detail = get_res.json()
        # Must NEVER be passed without a terminal success event!
        assert detail["status"] == "incomplete"

@pytest.mark.asyncio
async def test_run_cancellation(client: AsyncClient):
    async def slow_kane(*args, **kwargs):
        await asyncio.sleep(10)
        return KaneExecutionResult(
            run_id="slow",
            exit_code=-15,
            status="cancelled",
            raw_stdout_path="/tmp/out",
            raw_stderr_path="/tmp/err"
        )

    with patch.object(KaneService, "run_kane", side_effect=slow_kane):
        create_res = await client.post("/api/runs", json={
            "title": "Slow Run to Cancel",
            "objective": "Long running test",
            "target_url": "http://localhost:3000"
        })
        run_id = create_res.json()["id"]

        await asyncio.sleep(0.1)

        # Cancel the run via API
        cancel_res = await client.post(f"/api/runs/{run_id}/cancel")
        assert cancel_res.status_code == 200
        cancel_data = cancel_res.json()
        assert cancel_data["status"] == "cancelled"

        # Check DB status
        get_res = await client.get(f"/api/runs/{run_id}")
        assert get_res.json()["status"] == "cancelled"

@pytest.mark.asyncio
async def test_sse_event_streaming(client: AsyncClient):
    create_res = await client.post("/api/runs", json={
        "title": "SSE Stream Test",
        "objective": "Stream events test",
        "target_url": "http://localhost:3000"
    })
    run_id = create_res.json()["id"]

    # Stream SSE using client.stream
    async with client.stream("GET", f"/api/runs/{run_id}/events?stream=true") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        # Read at least one event, id, or comment
        async for line in response.aiter_lines():
            if line.strip():
                assert line.startswith("data:") or line.startswith(":") or line.startswith("id:")
                break
