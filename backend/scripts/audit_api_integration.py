import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:3000/api"

def test_endpoint(name, method, path, body=None, expected_status=200):
    url = f"{BASE_URL}{path}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content = resp.read().decode("utf-8")
            data = json.loads(content) if content else {}
            assert status == expected_status, f"Expected {expected_status}, got {status}"
            print(f"✓ [{method}] {path:40} -> HTTP {status} (OK)")
            return data
    except urllib.error.HTTPError as e:
        status = e.code
        content = e.read().decode("utf-8")
        if status == expected_status:
            print(f"✓ [{method}] {path:40} -> HTTP {status} (Expected: {e.reason})")
            return json.loads(content) if content else {}
        else:
            print(f"✗ [{method}] {path:40} -> HTTP {status} ERROR: {content}")
            raise e

def main():
    print("=== ShipProof Milestone 4.1: API Integration Audit ===\n")
    
    # 1. GET /api/health
    h = test_endpoint("Health", "GET", "/health")
    assert h["status"] == "ok"
    assert h["app"] == "ShipProof"
    
    # 2. GET /api/overview
    ov = test_endpoint("Overview", "GET", "/overview")
    assert "total_runs" in ov
    assert "repairs_verified" in ov
    
    # 3. GET /api/projects
    projs = test_endpoint("List Projects", "GET", "/projects")
    assert isinstance(projs, list)
    
    # 4. POST /api/projects
    new_proj = test_endpoint("Create Project", "POST", "/projects", {
        "name": "Audit Test Project",
        "target_url": "http://127.0.0.1:3005",
        "description": "Integration audit test project"
    }, expected_status=201)
    proj_id = new_proj["id"]
    
    # 5. GET /api/runs
    runs = test_endpoint("List Runs", "GET", "/runs?limit=5")
    assert "items" in runs
    assert len(runs["items"]) > 0
    test_run_id = runs["items"][0]["id"]
    
    # 6. POST /api/runs (Create run)
    created_run = test_endpoint("Create Run", "POST", "/runs", {
        "title": "API Audit Verification Run",
        "objective": "Verify store homepage loads",
        "target_url": "http://127.0.0.1:3005",
        "project_id": proj_id,
        "mode": "verify_only",
        "headless": True,
        "timeout": 30
    }, expected_status=201)
    audit_run_id = created_run["id"]
    
    # 7. GET /api/runs/{id}
    run_detail = test_endpoint("Get Run Detail", "GET", f"/runs/{audit_run_id}")
    assert run_detail["id"] == audit_run_id
    
    # 8. GET /api/runs/{id}/events (static)
    events = test_endpoint("Get Run Events", "GET", f"/runs/{audit_run_id}/events")
    assert isinstance(events, list)
    
    # 9. GET /api/runs/{id}/evidence (check on verified run with evidence)
    ev = test_endpoint("Get Run Evidence", "GET", f"/runs/157c47e8-b90b-47e1-979d-38bbd01e9118/evidence")
    assert ev["has_evidence"] is True
    assert len(ev["artifacts"]) > 0
    
    # 10. GET /api/repairs
    repairs = test_endpoint("List Repairs", "GET", "/repairs")
    assert isinstance(repairs, list)
    assert len(repairs) > 0
    verified_repair_id = "ac1efe85-8c32-4d42-b76e-e68bfeb20c10"
    
    # 11. GET /api/repairs/{id}
    rep_detail = test_endpoint("Get Repair Detail", "GET", f"/repairs/{verified_repair_id}")
    assert rep_detail["id"] == verified_repair_id
    assert rep_detail["execution_mode"] == "ide_mediated"
    assert rep_detail["prompt_markdown"] is not None
    
    # 12. POST /api/repairs/{id}/check-changes
    changes = test_endpoint("Check Repair Changes", "POST", f"/repairs/{verified_repair_id}/check-changes")
    assert "modified" in changes or "has_changes" in changes
    
    # 13. GET /api/repairs/{id}/events
    rep_events = test_endpoint("Get Repair Events", "GET", f"/repairs/{verified_repair_id}/events")
    assert isinstance(rep_events, list)

    print("\n✓ All API integration contracts verified successfully through Next.js proxy!")

if __name__ == "__main__":
    main()
