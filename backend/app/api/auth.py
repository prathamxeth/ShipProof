import re
import time
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from pydantic import BaseModel, Field, field_validator
from backend.app.core.auth import (
    verify_auth,
    create_scoped_ticket,
    create_session_token,
    SESSION_COOKIE_NAME,
    DEFAULT_SESSION_TTL_SECONDS
)
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication & Tokens"])
logger = get_logger("api.auth")

SAFE_RUN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_\-]+$")

class TicketRequest(BaseModel):
    scope: str = Field(default="stream", description="'stream', 'evidence', or 'all'")
    run_id: Optional[str] = Field(default=None, description="Run ID containment (mandatory for stream/evidence)")
    ttl_seconds: int = Field(default=300, ge=30, le=3600, description="Ticket TTL in seconds (default 300)")

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("stream", "evidence", "all"):
            raise ValueError("Invalid scope: must be 'stream', 'evidence', or 'all'.")
        return clean

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not SAFE_RUN_ID_PATTERN.match(clean):
                raise ValueError("Invalid run_id format: only alphanumeric characters, underscores, and hyphens permitted.")
            return clean
        return None

class TicketResponse(BaseModel):
    ticket: str
    scope: str
    run_id: Optional[str]
    expires_at: int

@router.post(
    "/ticket",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a short-lived scoped ticket for URL-based access (SSE & Images)",
    dependencies=[Depends(verify_auth)]
)
async def issue_scoped_ticket(payload: TicketRequest):
    """
    Issues a cryptographically signed ticket valid for a short window (default 5 minutes).
    Enables native EventSource SSE connections and <img> evidence rendering
    without exposing permanent master API keys in query parameters or access logs.
    Wildcard tickets (run_id=None) are prohibited for stream and evidence scopes.
    """
    if payload.scope in ("stream", "evidence") and not payload.run_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Field 'run_id' is strictly required for '{payload.scope}' scoped tickets. Wildcard access is prohibited."
        )

    ticket_str = create_scoped_ticket(
        scope=payload.scope,
        run_id=payload.run_id,
        ttl_seconds=payload.ttl_seconds
    )
    return TicketResponse(
        ticket=ticket_str,
        scope=payload.scope,
        run_id=payload.run_id,
        expires_at=int(time.time()) + payload.ttl_seconds
    )


class SessionLoginRequest(BaseModel):
    username: Optional[str] = Field(default="beta-operator", description="Authenticated username")
    key: Optional[str] = Field(default=None, description="Master API key or password")
    password: Optional[str] = Field(default=None, description="Alias for master key")


class SessionResponse(BaseModel):
    ok: bool = True
    token: str
    username: str
    expires_at: int
    message: str = "Authenticated session established"


@router.post(
    "/login",
    response_model=SessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Create an authenticated human operator session"
)
async def login_session(payload: SessionLoginRequest, response: Response):
    """
    Issues an HMAC-SHA256 signed session token and sets an HttpOnly cookie.
    Validates master API key if configured or if in single_tenant / production mode.
    """
    expected_key = settings.SHIPPROOF_API_KEY
    mode = settings.DEPLOYMENT_MODE
    candidate_key = payload.key or payload.password

    if (mode in ("trusted_single_tenant", "production") or expected_key):
        if not candidate_key or not secrets.compare_digest(candidate_key, expected_key or ""):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials: authentication key required."
            )

    username = payload.username.strip() if payload.username and payload.username.strip() else "beta-operator"
    token = create_session_token(username=username)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=(mode == "production"),
        max_age=DEFAULT_SESSION_TTL_SECONDS
    )

    return SessionResponse(
        ok=True,
        token=token,
        username=username,
        expires_at=int(time.time()) + DEFAULT_SESSION_TTL_SECONDS
    )

