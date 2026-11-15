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
        assert "repairs_verified" in data
        assert "repairs_awaiting_approval" in data
        assert "recent_runs" in data
        assert isinstance(data["recent_runs"], list)
        assert "recent_repairs" in data
        assert isinstance(data["recent_repairs"], list)
