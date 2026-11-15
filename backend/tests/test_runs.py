import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_and_query_verification_run(client: AsyncClient):
    # 1. Create run with direct target_url
    run_payload = {
        "title": "Header Navigation Verification",
        "objective": "Verify that navbar logo links to root and shows title",
        "target_url": "http://localhost:3000",
        "mode": "closed_loop"
    }
    res = await client.post("/api/runs", json=run_payload)
    assert res.status_code == 201
    run_data = res.json()
    assert run_data["title"] == run_payload["title"]
    assert run_data["status"] in ("queued", "pending")
    assert run_data["mode"] == "closed_loop"
    assert run_data["target_url"] == "http://localhost:3000"
    assert run_data["total_steps"] == 0
    assert "id" in run_data

    run_id = run_data["id"]

    # 2. Get run details by ID
    get_res = await client.get(f"/api/runs/{run_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["id"] == run_id
    assert detail["title"] == run_payload["title"]
    assert "steps" in detail
    assert "repairs" in detail

    # 3. List runs
    list_res = await client.get("/api/runs")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(r["id"] == run_id for r in list_data["items"])

@pytest.mark.asyncio
async def test_create_run_with_project(client: AsyncClient):
    # Create project first
    proj_res = await client.post("/api/projects", json={
        "name": "Project Alpha",
        "target_url": "http://localhost:3000/alpha"
    })
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # Create run using project_id (inheriting target_url)
    run_res = await client.post("/api/runs", json={
        "title": "Alpha Smoke Test",
        "objective": "Verify home page loads",
        "project_id": project_id
    })
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["project_id"] == project_id
    assert run_data["target_url"] == "http://localhost:3000/alpha"

@pytest.mark.asyncio
async def test_create_run_missing_target_url(client: AsyncClient):
    # Missing both target_url and project_id
    run_res = await client.post("/api/runs", json={
        "title": "Invalid Run",
        "objective": "Should fail because no target URL"
    })
    assert run_res.status_code == 422

@pytest.mark.asyncio
async def test_get_nonexistent_run(client: AsyncClient):
    res = await client.get("/api/runs/non-existent-uuid")
    assert res.status_code == 404
    data = res.json()
    assert data["error"]["type"] == "ResourceNotFoundException"
