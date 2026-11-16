import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
import json
import io
import zipfile
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.url_validator import validate_target_url
from backend.app.core.errors import ShipProofException
from backend.app.services.evidence_service import (
    EvidenceService,
    PathTraversalError,
    ArchiveSizeLimitExceededError
)

# --- A. URL & SSRF Security Tests ---

@pytest.mark.asyncio
async def test_ssrf_blocks_cloud_metadata_endpoints(client: AsyncClient):
    """
    Ensure cloud metadata endpoints (AWS, GCP, Azure, Alibaba) are strictly blocked in all environments.
    """
    metadata_urls = [
        "http://169.254.169.254/latest/meta-data/",
        "http://169.254.169.254/computeMetadata/v1/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://metadata.goog/",
        "http://100.100.100.200/latest/meta-data/",
    ]
    for url in metadata_urls:
        # Direct validator test
        with pytest.raises(ShipProofException) as exc_info:
            validate_target_url(url, allow_local=True)
        assert exc_info.value.status_code == 422
        assert "metadata" in str(exc_info.value.message).lower()

        # API creation test
        res = await client.post("/api/runs", json={
            "title": "Adversarial Metadata Test",
            "objective": "Attempt metadata exfiltration",
            "target_url": url
        })
        assert res.status_code == 422
        assert "metadata" in res.json()["error"]["message"].lower()

@pytest.mark.asyncio
async def test_ssrf_blocks_dangerous_schemes(client: AsyncClient):
    """
    Ensure non-HTTP schemes (file://, gopher://, javascript:, ftp://, data:) are rejected.
    """
    dangerous_urls = [
        "file:///etc/passwd",
        "file:///Users/pratham/.ssh/id_rsa",
        "gopher://127.0.0.1:6379/_INFO",
        "javascript:alert(document.cookie)",
        "ftp://ftp.example.com/dump.sql",
        "data:text/html,<script>alert(1)</script>",
    ]
    for url in dangerous_urls:
        with pytest.raises(ShipProofException) as exc_info:
            validate_target_url(url, allow_local=True)
        assert exc_info.value.status_code == 422
        assert "scheme" in str(exc_info.value.message).lower()

        res = await client.post("/api/runs", json={
            "title": "Adversarial Scheme Test",
            "objective": "Test protocol smuggling",
            "target_url": url
        })
        assert res.status_code == 422

@pytest.mark.asyncio
async def test_ssrf_blocks_malformed_urls_and_ports(client: AsyncClient):
    """
    Ensure invalid ports and malformed URLs are rejected.
    """
    invalid_urls = [
        "http://example.com:99999",
        "http://example.com:-5",
        "http://:8080",
        "not-a-valid-url-at-all",
        "http://",
    ]
    for url in invalid_urls:
        with pytest.raises(ShipProofException) as exc_info:
            validate_target_url(url, allow_local=True)
        assert exc_info.value.status_code == 422

        res = await client.post("/api/runs", json={
            "title": "Malformed URL Test",
            "objective": "Test bad URL syntax",
            "target_url": url
        })
        assert res.status_code == 422

@pytest.mark.asyncio
async def test_ssrf_production_mode_restrictions():
    """
    Ensure production mode strictly prohibits loopback and private IP networks.
    """
    private_targets = [
        "http://127.0.0.1:8000",
        "http://localhost:3000",
        "http://10.0.0.1:8080",
        "http://192.168.1.100",
    ]
    for url in private_targets:
        with pytest.raises(ShipProofException) as exc_info:
            validate_target_url(url, allow_local=False)
        assert exc_info.value.status_code == 422
        assert "ssrf protection" in str(exc_info.value.message).lower()

@pytest.mark.asyncio
async def test_ssrf_development_mode_permits_sample_store(client: AsyncClient):
    """
    Ensure development allowances remain intact for Sample Store (localhost / 127.0.0.1).
    """
    dev_valid_urls = [
        "http://127.0.0.1:3005/product/1",
        "http://localhost:3000",
        "http://127.0.0.1:8000/api/health",
    ]
    for url in dev_valid_urls:
        validated = validate_target_url(url, allow_local=True)
        assert validated == url

# --- B. Evidence Path Traversal & Containment Tests ---

@pytest.mark.asyncio
async def test_evidence_file_path_traversal_defense(client: AsyncClient, tmp_path: Path):
    """
    Test directory traversal attacks on the evidence artifact serving endpoint.
    Verifies that '..' and prefix collision paths are strictly denied with HTTP 403.
    """
    run_id = "test-traversal-run-99"
    run_evidence_dir = settings.EVIDENCE_DIR / run_id
    run_evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Create legitimate file
    (run_evidence_dir / "valid.txt").write_text("legitimate evidence content")

    # 1. Normal valid request
    res = await client.get(f"/api/runs/{run_id}/evidence/files/valid.txt")
    assert res.status_code == 200
    assert "legitimate evidence content" in res.text

    # 2. Classic path traversal using '..'
    traversal_res = await client.get(f"/api/runs/{run_id}/evidence/files/../../../../etc/passwd")
    assert traversal_res.status_code in (403, 404)

    # 3. Path escaping outside the run directory
    escape_res = await client.get(f"/api/runs/{run_id}/evidence/files/../shipproof.db")
    assert escape_res.status_code in (403, 404)

    # Clean up test dir
    import shutil
    shutil.rmtree(run_evidence_dir, ignore_errors=True)

# --- C. Credential Redaction & Non-Sensitive Preservation ---

def test_har_credential_redaction_preserves_debug_context(tmp_path: Path):
    """
    Verify that sensitive headers (Authorization, Cookie, Set-Cookie) are redacted on disk,
    while non-sensitive headers (Content-Type, User-Agent) remain intact for debugging.
    """
    service = EvidenceService(base_evidence_dir=tmp_path / "evidence")

    har_content = {
        "log": {
            "entries": [
                {
                    "request": {
                        "url": "https://api.store.com/checkout",
                        "method": "POST",
                        "headers": [
                            {"name": "Authorization", "value": "Bearer production-api-key-12345"},
                            {"name": "Cookie", "value": "session_token=secret_session_xyz"},
                            {"name": "Content-Type", "value": "application/json"},
                            {"name": "User-Agent", "value": "Kane-Browser/0.10.4"}
                        ]
                    },
                    "response": {
                        "status": 500,
                        "statusText": "Internal Server Error",
                        "headers": [
                            {"name": "Set-Cookie", "value": "auth_cookie=super_secret_cookie_val"},
                            {"name": "Content-Type", "value": "application/json; charset=utf-8"}
                        ]
                    }
                }
            ]
        }
    }

    # Package into test zip
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        zf.writestr("run.yaml", "status: failed\n")
        zf.writestr("tests/test-1/logs/0-network.har", json.dumps(har_content))

    pack_file = tmp_path / "redact_test.evidence"
    pack_file.write_bytes(zip_buf.getvalue())

    extracted = service.safe_extract_evidence_pack(pack_file, "redact-run-1")
    manifest = service.parse_extracted_evidence(extracted, "redact-run-1")

    # Read extracted HAR from disk
    har_disk = json.loads((extracted / "tests/test-1/logs/0-network.har").read_text())
    entry = har_disk["log"]["entries"][0]

    # Verify secrets are redacted
    req_headers = {h["name"].lower(): h["value"] for h in entry["request"]["headers"]}
    resp_headers = {h["name"].lower(): h["value"] for h in entry["response"]["headers"]}

    assert req_headers["authorization"] == "[REDACTED]"
    assert req_headers["cookie"] == "[REDACTED]"
    assert resp_headers["set-cookie"] == "[REDACTED]"

    # Verify non-sensitive headers are preserved for debugging
    assert req_headers["content-type"] == "application/json"
    assert req_headers["user-agent"] == "Kane-Browser/0.10.4"
    assert resp_headers["content-type"] == "application/json; charset=utf-8"

    # Verify error tracking caught the 500 status
    assert manifest["network_failures_count"] == 1
    assert manifest["network_failures"][0]["status"] == 500
