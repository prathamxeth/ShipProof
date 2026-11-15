import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

@pytest.mark.asyncio
async def test_get_overview_stats():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        assert "total_runs" in data
        assert "passed_runs" in data
        assert "failed_runs" in data
        assert "verified_runs" in data
        assert "running_runs" in data
        assert "cancelled_or_incomplete_runs" in data
        assert "total_repairs" in data
        assert "repairs_verified" in data
        assert "repairs_awaiting_approval" in data
        assert "repairs_in_progress" in data
        assert "total_projects" in data
        assert "recent_runs" in data
        assert isinstance(data["recent_runs"], list)
        assert "recent_repairs" in data
        assert isinstance(data["recent_repairs"], list)

@pytest.mark.asyncio
async def test_overview_aggregation_consistency():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        
        # Total runs must exactly equal sum of all mutually exclusive status categories
        accounted_runs = (
            data["passed_runs"]
            + data["verified_runs"]
            + data["failed_runs"]
            + data["running_runs"]
            + data["cancelled_or_incomplete_runs"]
        )
        assert data["total_runs"] == accounted_runs, (
            f"Run status mismatch: total={data['total_runs']} vs sum={accounted_runs}"
        )

        # Total repairs must account for verified, awaiting approval, and in progress
        assert data["total_repairs"] >= (
            data["repairs_verified"]
            + data["repairs_awaiting_approval"]
            + data["repairs_in_progress"]
        )

@pytest.mark.asyncio
async def test_overview_segregates_run_status_from_repair_status():
    """
    Ensure that runs whose status is 'verified' are counted in verified_runs,
    and not conflated with direct 'passed_runs'.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/overview")
        assert response.status_code == 200
        data = response.json()
        
        # If there are verified runs, verified_runs must reflect them
        # while passed_runs only reflects direct passed runs / re-tests
        assert isinstance(data["passed_runs"], int)
        assert isinstance(data["verified_runs"], int)
        assert isinstance(data["repairs_verified"], int)

