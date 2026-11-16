from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from typing import Optional
import time
from backend.app.core.auth import verify_auth, create_scoped_ticket
from backend.app.core.logging import get_logger

router = APIRouter(prefix="/auth", tags=["Authentication & Tokens"])
logger = get_logger("api.auth")

class TicketRequest(BaseModel):
    scope: str = Field(default="all", description="'stream', 'evidence', or 'all'")
    run_id: Optional[str] = Field(default=None, description="Optional run ID containment")
    ttl_seconds: int = Field(default=300, ge=30, le=3600, description="Ticket TTL in seconds (default 300)")

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
    """
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
