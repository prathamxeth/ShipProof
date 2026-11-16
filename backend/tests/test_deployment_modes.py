import pytest
from pydantic import ValidationError
from backend.app.core.config import Settings
from backend.app.core.auth import check_rate_limit, extract_api_token
from fastapi import Request, HTTPException
from unittest.mock import MagicMock
import time

def test_development_mode_defaults():
    s = Settings(
        DEPLOYMENT_MODE="development",
        ALLOW_LOCAL_TARGETS=True
    )
    assert s.DEPLOYMENT_MODE == "development"
    assert s.ALLOW_LOCAL_TARGETS is True

def test_production_mode_fails_closed_missing_key():
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEPLOYMENT_MODE="production",
            SHIPPROOF_API_KEY=None,
            ALLOW_LOCAL_TARGETS=False,
            CORS_ORIGINS=["http://localhost:3000"]
        )
    assert "Production deployment mode requires SHIPPROOF_API_KEY with at least 16 characters" in str(exc.value)

def test_production_mode_fails_closed_short_key():
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEPLOYMENT_MODE="production",
            SHIPPROOF_API_KEY="short_key",
            ALLOW_LOCAL_TARGETS=False,
            CORS_ORIGINS=["http://localhost:3000"]
        )
    assert "Production deployment mode requires SHIPPROOF_API_KEY with at least 16 characters" in str(exc.value)

def test_production_mode_fails_closed_local_targets_allowed():
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEPLOYMENT_MODE="production",
            SHIPPROOF_API_KEY="long_secure_secret_key_12345",
            ALLOW_LOCAL_TARGETS=True,
            CORS_ORIGINS=["http://localhost:3000"]
        )
    assert "Production deployment mode requires ALLOW_LOCAL_TARGETS=False" in str(exc.value)

def test_production_mode_fails_closed_wildcard_cors():
    with pytest.raises(ValidationError) as exc:
        Settings(
            DEPLOYMENT_MODE="production",
            SHIPPROOF_API_KEY="long_secure_secret_key_12345",
            ALLOW_LOCAL_TARGETS=False,
            CORS_ORIGINS=["*"]
        )
    assert "Production deployment mode requires explicit CORS_ORIGINS whitelist without wildcards" in str(exc.value)

def test_production_mode_success_with_valid_config():
    s = Settings(
        DEPLOYMENT_MODE="production",
        SHIPPROOF_API_KEY="super_secret_production_key_abcdef123456",
        ALLOW_LOCAL_TARGETS=False,
        CORS_ORIGINS=["https://app.shipproof.internal"]
    )
    assert s.DEPLOYMENT_MODE == "production"
    assert s.SHIPPROOF_API_KEY == "super_secret_production_key_abcdef123456"
    assert s.ALLOW_LOCAL_TARGETS is False

def test_trusted_single_tenant_auto_generates_key_if_omitted():
    s = Settings(
        DEPLOYMENT_MODE="trusted_single_tenant",
        SHIPPROOF_API_KEY=None,
        ALLOW_LOCAL_TARGETS=True
    )
    assert s.DEPLOYMENT_MODE == "trusted_single_tenant"
    assert s.SHIPPROOF_API_KEY is not None
    assert s.SHIPPROOF_API_KEY.startswith("sp_beta_")

def test_token_extraction_mechanisms():
    # 1. Bearer header
    req1 = MagicMock(spec=Request)
    req1.headers = {"Authorization": "Bearer token_from_bearer"}
    req1.query_params = {}
    assert extract_api_token(req1) == "token_from_bearer"

    # 2. X-ShipProof-Key
    req2 = MagicMock(spec=Request)
    req2.headers = {"X-ShipProof-Key": "token_from_header"}
    req2.query_params = {}
    assert extract_api_token(req2) == "token_from_header"

    # 3. Query parameter ?token=
    req3 = MagicMock(spec=Request)
    req3.headers = {}
    req3.query_params = {"token": "token_from_query"}
    assert extract_api_token(req3) == "token_from_query"

    # 4. None provided
    req4 = MagicMock(spec=Request)
    req4.headers = {}
    req4.query_params = {}
    assert extract_api_token(req4) is None

def test_rate_limiting_enforcement():
    from backend.app.core.auth import _rate_limit_records
    from backend.app.core.config import settings
    _rate_limit_records.clear()

    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = "192.168.1.50"

    orig_limit = settings.RATE_LIMIT_PER_MINUTE
    try:
        settings.RATE_LIMIT_PER_MINUTE = 5
        # 5 calls should succeed
        for _ in range(5):
            check_rate_limit(req)

        # 6th call within the minute must raise 429
        with pytest.raises(HTTPException) as exc:
            check_rate_limit(req)
        assert exc.value.status_code == 429
        assert "Rate limit exceeded" in exc.value.detail
    finally:
        settings.RATE_LIMIT_PER_MINUTE = orig_limit
        _rate_limit_records.clear()
