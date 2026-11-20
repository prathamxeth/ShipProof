import pytest
from httpx import AsyncClient
from backend.app.services.revenue_guard_service import revenue_guard

@pytest.mark.asyncio
async def test_guard_status_endpoint(auth_client: AsyncClient):
    res = await auth_client.get("/api/guard/status")
    assert res.status_code == 200
    data = res.json()
    assert "enabled" in data
    assert "interval_seconds" in data
    assert data["interval_seconds"] == 120
    assert "target_url" in data
    assert "revenue_protected" in data
    assert "state" in data

@pytest.mark.asyncio
async def test_guard_interval_endpoint(auth_client: AsyncClient):
    res = await auth_client.post("/api/guard/interval", json={"interval_seconds": 60})
    assert res.status_code == 200
    data = res.json()
    assert data["interval_seconds"] == 60
    assert data["interval_label"] == "1m"

    # Reset back to 120s
    res2 = await auth_client.post("/api/guard/interval", json={"interval_seconds": 120})
    assert res2.status_code == 200
    assert res2.json()["interval_seconds"] == 120

@pytest.mark.asyncio
async def test_guard_toggle_endpoint(auth_client: AsyncClient):
    res = await auth_client.post("/api/guard/toggle", json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is False

    res2 = await auth_client.post("/api/guard/toggle", json={"enabled": True})
    assert res2.status_code == 200
    assert res2.json()["enabled"] is True
