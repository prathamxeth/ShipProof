from fastapi import Request, HTTPException, status, Depends
from typing import Optional, Dict, Any, List
import secrets
import time
import json
import base64
import hmac
import hashlib
import asyncio
from collections import defaultdict
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger("auth")

# Concurrency lock for rate-limiting updates
_rate_limit_lock = asyncio.Lock()
# In-memory sliding window rate limiter: ip -> list of timestamps
_rate_limit_records: Dict[str, List[float]] = defaultdict(list)
_MAX_TRACKED_IPS = 5000

def get_client_ip(request: Request) -> str:
    """
    Safely resolves client IP address.
    Only trusts X-Forwarded-For if direct peer IP is in settings.TRUSTED_PROXIES.
    Prevents IP spoofing in rate limiting and audit logging.
    """
    direct_peer = request.client.host if request.client else "unknown"
    trusted_proxies = settings.TRUSTED_PROXIES or ["127.0.0.1", "::1"]

    if direct_peer in trusted_proxies:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            # Rightmost hop closest to the trusted proxy is the most reliable untrusted client IP
            hops = [h.strip() for h in xff.split(",") if h.strip()]
            if hops:
                return hops[-1]

    return direct_peer

def check_rate_limit(request: Request):
    """
    Sliding window rate limiter with bounded memory cleanup.
    Runs synchronously and atomically on the event loop.
    """
    limit = settings.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return

    client_ip = get_client_ip(request)
    now = time.time()
    window_start = now - 60.0

    # Prune memory if table grows excessively
    if len(_rate_limit_records) > _MAX_TRACKED_IPS:
        stale_keys = [k for k, v in _rate_limit_records.items() if not v or v[-1] <= window_start]
        for k in stale_keys:
            _rate_limit_records.pop(k, None)

    # Prune old timestamps for this IP
    timestamps = [t for t in _rate_limit_records.get(client_ip, []) if t > window_start]
    if len(timestamps) >= limit:
        logger.warning(f"Rate limit exceeded for client IP {client_ip} ({len(timestamps)} requests in 60s)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: maximum {limit} requests per minute."
        )

    timestamps.append(now)
    _rate_limit_records[client_ip] = timestamps

def _get_signing_key() -> str:
    return settings.SHIPPROOF_API_KEY or "dev_fallback_signing_secret_do_not_use_in_prod"

def create_scoped_ticket(scope: str, run_id: Optional[str] = None, ttl_seconds: int = 300) -> str:
    """
    Generates a short-lived, cryptographically signed, resource-scoped ticket.
    Permits URL-based access (e.g. SSE EventSource and <img> tags) without leaking master API key.
    """
    payload = {
        "exp": int(time.time()) + ttl_seconds,
        "scope": scope,
        "run_id": run_id,
        "nonce": secrets.token_hex(8)
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
    
    key = _get_signing_key().encode()
    sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"spt.{payload_b64}.{sig}"

def verify_scoped_ticket(ticket_str: str, required_scope: str, target_run_id: Optional[str] = None) -> bool:
    """
    Validates a short-lived scoped ticket.
    """
    try:
        parts = ticket_str.split(".")
        if len(parts) != 3 or parts[0] != "spt":
            return False

        payload_b64, sig = parts[1], parts[2]
        key = _get_signing_key().encode()
        expected_sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()
        
        if not secrets.compare_digest(sig, expected_sig):
            return False

        # Add base64 padding
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode())

        # Expiration check
        if payload.get("exp", 0) < time.time():
            return False

        # Scope check
        ticket_scope = payload.get("scope")
        if ticket_scope != "all" and ticket_scope != required_scope:
            return False

        # Resource containment check
        ticket_run_id = payload.get("run_id")
        if ticket_run_id and target_run_id and ticket_run_id != target_run_id:
            return False

        return True
    except Exception as e:
        logger.debug(f"Ticket verification failed: {e}")
        return False

def extract_api_token(request: Request) -> Optional[str]:
    """
    Extracts the authentication token from headers or query parameters.
    """
    # 1. Bearer Header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 2. X-ShipProof-Key
    custom_header = request.headers.get("X-ShipProof-Key")
    if custom_header:
        return custom_header.strip()

    # 3. Query param ?token= (deprecated fallback for backward compatibility)
    query_token = request.query_params.get("token")
    if query_token:
        return query_token.strip()

    return None

async def verify_auth(request: Request) -> str:
    """
    Enforces authentication boundaries:
    - development: Optional if no API key is set; enforces if set.
    - trusted_single_tenant & production: Strictly enforces valid API key.
    """
    mode = settings.DEPLOYMENT_MODE
    expected_key = settings.SHIPPROOF_API_KEY

    # Development mode without configured key permits local development
    if mode == "development" and not expected_key:
        return "dev-local-user"

    # Check for short-lived ticket in query parameters
    ticket = request.query_params.get("ticket")
    if ticket:
        # Determine scope from path
        path = request.url.path
        scope = "stream" if "events" in path else ("evidence" if "evidence" in path else "all")
        # Extract run_id if in path
        run_id = None
        if "/runs/" in path:
            parts = path.split("/runs/")[1].split("/")
            run_id = parts[0]

        if verify_scoped_ticket(ticket, required_scope=scope, target_run_id=run_id):
            return "scoped-ticket-user"

    provided_token = extract_api_token(request)
    if not provided_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing ShipProof API token (Authorization: Bearer <token> or X-ShipProof-Key).",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not expected_key or not secrets.compare_digest(provided_token, expected_key):
        logger.warning(f"Unauthorized access attempt to {request.url.path} from {get_client_ip(request)}")
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
    Combines authentication verification with sliding-window rate limiting.
    Scoped tickets are disallowed from executing mutating actions.
    """
    if user == "scoped-ticket-user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: scoped ticket cannot perform mutating actions."
        )

    check_rate_limit(request)
    return user
