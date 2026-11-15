import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app"] == "ShipProof"
    assert data["version"] == "0.1.0"
    assert data["database"] == "connected"
    assert "timestamp" in data
    assert "kane_cli_installed" in data
    assert "agy_cli_installed" in data

@pytest.mark.asyncio
async def test_root_endpoint(client: AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "ShipProof"
    assert "Your AI writes the code. ShipProof proves it works." in data["tagline"]
