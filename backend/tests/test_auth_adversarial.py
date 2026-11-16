import pytest
import time
import json
from unittest.mock import MagicMock
from fastapi import Request, HTTPException
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.auth import (
    verify_auth,
    verify_protected_action,
    create_scoped_ticket,
    verify_scoped_ticket,
    get_client_ip,
    check_rate_limit,
    _rate_limit_records
)

@pytest.mark.asyncio
async def test_auth_enforcement_in_single_tenant_and_production_mode():
    """
    Verifies that all sensitive read and write endpoints reject missing,
    empty, or invalid credentials when an API key is configured.
    """
    orig_mode = settings.DEPLOYMENT_MODE
    orig_key = settings.SHIPPROOF_API_KEY
    settings.DEPLOYMENT_MODE = "trusted_single_tenant"
    settings.SHIPPROOF_API_KEY = "test_beta_secret_key_12345678"

    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            endpoints = [
                ("GET", "/api/overview"),
                ("GET", "/api/runs"),
                ("GET", "/api/repairs"),
                ("GET", "/api/projects"),
                ("POST", "/api/runs", {"title": "T", "objective": "O", "target_url": "http://example.com"}),
                ("POST", "/api/system/backup", None),
            ]

            for method, path, *data in endpoints:
                payload = data[0] if data else None
                # 1. Missing Authorization header
                if method == "GET":
                    resp_missing = await client.get(path)
                else:
                    resp_missing = await client.post(path, json=payload)
                assert resp_missing.status_code == 401, f"Expected 401 on {path} with missing auth, got {resp_missing.status_code}"

                # 2. Invalid Bearer Token
                headers_bad = {"Authorization": "Bearer invalid_token_xyz"}
                if method == "GET":
                    resp_bad = await client.get(path, headers=headers_bad)
                else:
                    resp_bad = await client.post(path, headers=headers_bad, json=payload)
                assert resp_bad.status_code == 401, f"Expected 401 on {path} with bad bearer, got {resp_bad.status_code}"

                # 3. Malformed Header
                headers_malformed = {"Authorization": "Token not_a_bearer"}
                if method == "GET":
                    resp_malformed = await client.get(path, headers=headers_malformed)
                else:
                    resp_malformed = await client.post(path, headers=headers_malformed, json=payload)
                assert resp_malformed.status_code == 401

                # 4. Correct Bearer Token succeeds
                headers_good = {"Authorization": f"Bearer {settings.SHIPPROOF_API_KEY}"}
                if method == "GET":
                    resp_good = await client.get(path, headers=headers_good)
                    assert resp_good.status_code == 200, f"Expected 200 on {path} with valid bearer, got {resp_good.status_code}"
                elif path == "/api/system/backup":
                    resp_good = await client.post(path, headers=headers_good)
                    assert resp_good.status_code == 200
    finally:
        settings.DEPLOYMENT_MODE = orig_mode
        settings.SHIPPROOF_API_KEY = orig_key

@pytest.mark.asyncio
async def test_scoped_ticket_lifecycle_and_scope_confinement():
    """
    Tests creation, validation, expiration, and scope confinement of short-lived scoped tickets.
    """
    orig_key = settings.SHIPPROOF_API_KEY
    settings.SHIPPROOF_API_KEY = "master_signing_key_for_tickets_12345"
    try:
        # 1. Generate stream ticket for run-abc
        ticket_stream = create_scoped_ticket(scope="stream", run_id="run-abc", ttl_seconds=300)
        assert ticket_stream.startswith("spt.")

        # Valid scope and matching run_id
        assert verify_scoped_ticket(ticket_stream, required_scope="stream", target_run_id="run-abc") is True
        
        # Mismatched scope rejected
        assert verify_scoped_ticket(ticket_stream, required_scope="evidence", target_run_id="run-abc") is False

        # Mismatched run_id rejected
        assert verify_scoped_ticket(ticket_stream, required_scope="stream", target_run_id="run-xyz") is False

        # 2. Tampered signature rejected
        tampered_ticket = ticket_stream[:-5] + "aaaaa"
        assert verify_scoped_ticket(tampered_ticket, required_scope="stream", target_run_id="run-abc") is False

        # 3. Expired ticket rejected
        ticket_expired = create_scoped_ticket(scope="stream", run_id="run-abc", ttl_seconds=-10)
        assert verify_scoped_ticket(ticket_expired, required_scope="stream", target_run_id="run-abc") is False

        # 4. Scoped ticket cannot perform mutating actions
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Stream ticket fails authorization on /api/runs (401)
            resp_stream = await client.post(
                f"/api/runs?ticket={ticket_stream}",
                json={"title": "T", "objective": "O", "target_url": "http://example.com"}
            )
            assert resp_stream.status_code == 401

            # Even a ticket with 'all' scope is strictly forbidden from mutating actions (403)
            ticket_all = create_scoped_ticket(scope="all", ttl_seconds=300)
            resp_mutating = await client.post(
                f"/api/runs?ticket={ticket_all}",
                json={"title": "T", "objective": "O", "target_url": "http://example.com"}
            )
            assert resp_mutating.status_code == 403
            assert "cannot perform mutating actions" in resp_mutating.json()["detail"]
    finally:
        settings.SHIPPROOF_API_KEY = orig_key

def test_ip_spoofing_defense():
    """
    Verifies that unverified X-Forwarded-For headers from untrusted clients are NOT trusted,
    preventing IP-spoofing rate limit evasion.
    """
    settings.TRUSTED_PROXIES = ["127.0.0.1", "10.0.0.1"]

    # 1. Direct connection from untrusted public IP with forged X-Forwarded-For
    req_untrusted = MagicMock(spec=Request)
    req_untrusted.client = MagicMock()
    req_untrusted.client.host = "203.0.113.50"
    req_untrusted.headers = {"X-Forwarded-For": "1.1.1.1, 8.8.8.8"}
    resolved_ip = get_client_ip(req_untrusted)
    assert resolved_ip == "203.0.113.50", "Must NOT trust X-Forwarded-For from untrusted peer"

    # 2. Connection from trusted reverse proxy
    req_trusted = MagicMock(spec=Request)
    req_trusted.client = MagicMock()
    req_trusted.client.host = "127.0.0.1"
    req_trusted.headers = {"X-Forwarded-For": "203.0.113.50, 198.51.100.22"}
    resolved_ip_trusted = get_client_ip(req_trusted)
    assert resolved_ip_trusted == "198.51.100.22", "Must resolve rightmost client hop from trusted proxy"

@pytest.mark.asyncio
async def test_request_payload_size_limit():
    """
    Verifies that requests exceeding 10MB Content-Length are rejected with 413 Payload Too Large.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        huge_headers = {"Content-Length": str(15 * 1024 * 1024)}  # 15 MB header
        resp = await client.post("/api/runs", headers=huge_headers)
        assert resp.status_code == 413
        assert "exceeds 10MB limit" in resp.json()["detail"]
