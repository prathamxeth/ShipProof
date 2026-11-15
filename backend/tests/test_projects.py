import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_and_get_project(client: AsyncClient):
    payload = {
        "name": "ShipProof Demo Store",
        "target_url": "http://localhost:3000",
        "repo_path": "/Users/pratham/Projects/ShipProof/frontend",
        "framework": "Next.js",
        "description": "E-Commerce checkout demo application"
    }
    create_res = await client.post("/api/projects", json=payload)
    assert create_res.status_code == 201
    created_data = create_res.json()
    assert created_data["name"] == payload["name"]
    assert created_data["target_url"] == payload["target_url"]
    assert "id" in created_data
    
    project_id = created_data["id"]

    # Get project by ID
    get_res = await client.get(f"/api/projects/{project_id}")
    assert get_res.status_code == 200
    fetched_data = get_res.json()
    assert fetched_data["id"] == project_id
    assert fetched_data["name"] == payload["name"]

    # List projects
    list_res = await client.get("/api/projects")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) >= 1
    assert any(p["id"] == project_id for p in items)

@pytest.mark.asyncio
async def test_get_nonexistent_project(client: AsyncClient):
    response = await client.get("/api/projects/non-existent-id")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["type"] == "ResourceNotFoundException"
