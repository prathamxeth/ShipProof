from fastapi import Request, HTTPException, status, Depends
from typing import Optional
import secrets
import time
from collections import defaultdict
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger("auth")

# In-memory sliding window rate limiter: ip -> list of timestamps
_rate_limit_records = defaultdict(list)

def check_rate_limit(request: Request):
    """
    Applies per-client IP rate limiting to protect resource-intensive operations
    (browser verification and code repair execution).
    """
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window_start = now - 60.0

    # Prune old timestamps
    timestamps = [t for t in _rate_limit_records[client_ip] if t > window_start]
    if len(timestamps) >= limit:
        logger.warning(f"Rate limit exceeded for client IP {client_ip} ({len(timestamps)} requests in 60s)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {limit} requests per minute."
        )

    timestamps.append(now)
    _rate_limit_records[client_ip] = timestamps

def extract_api_token(request: Request) -> Optional[str]:
    """
    Extracts the authentication token from:
    1. Authorization: Bearer <token>
    2. X-ShipProof-Key: <token>
    3. Query parameter ?token=<token> (needed for browser EventSource and direct img requests)
    """
    # 1. Bearer Header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 2. X-ShipProof-Key
    custom_header = request.headers.get("X-ShipProof-Key")
    if custom_header:
        return custom_header.strip()

    # 3. Query param
    query_token = request.query_params.get("token")
    if query_token:
        return query_token.strip()

    return None

async def verify_auth(request: Request) -> str:
    """
    Enforces authentication boundaries based on DEPLOYMENT_MODE:
    - development: Optional if no API key is set; enforces if set.
    - trusted_single_tenant: Strictly enforces single-tenant API key.
    - production: Strictly enforces production API key.
    """
    mode = settings.DEPLOYMENT_MODE
    expected_key = settings.SHIPPROOF_API_KEY

    # Development mode without configured key permits local development
    if mode == "development" and not expected_key:
        return "dev-local-user"

    provided_token = extract_api_token(request)
    if not provided_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing ShipProof API token (Authorization: Bearer <token>, X-ShipProof-Key, or ?token=).",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not expected_key or not secrets.compare_digest(provided_token, expected_key):
        logger.warning(f"Unauthorized access attempt to {request.url.path} from {request.client.host if request.client else 'unknown'}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid ShipProof API token.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return "authenticated-user"

async def verify_protected_action(
    request: Request,
    user: str = Depends(verify_auth)
) -> str:
    """
    Combines authentication verification with rate limiting for expensive mutating actions.
    """
    check_rate_limit(request)
    return user
