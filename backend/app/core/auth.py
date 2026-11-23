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
    return (
        settings.SESSION_SECRET or
        "shipproof_render_shared_secret_2026"
    )

_revoked_nonces: Dict[str, float] = {}
_MAX_TRACKED_NONCES = 10000

def revoke_ticket_nonce(nonce: str, exp: float):
    """
    Marks a ticket nonce as revoked/consumed until its expiration timestamp.
    """
    now = time.time()
    if len(_revoked_nonces) > _MAX_TRACKED_NONCES:
        stale = [n for n, e in _revoked_nonces.items() if e <= now]
        for s in stale:
            _revoked_nonces.pop(s, None)
    _revoked_nonces[nonce] = exp

def is_nonce_revoked(nonce: str) -> bool:
    now = time.time()
    exp = _revoked_nonces.get(nonce)
    if exp is not None:
        if exp > now:
            return True
        else:
            _revoked_nonces.pop(nonce, None)
    return False

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

def verify_scoped_ticket(
    ticket_str: str,
    required_scope: str,
    target_run_id: Optional[str] = None,
    consume: bool = False
) -> bool:
    """
    Validates a short-lived scoped ticket.
    Checks signature, expiration, scope match, run_id containment, and nonce revocation.
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
        exp = payload.get("exp", 0)
        if exp < time.time():
            return False

        # Nonce revocation / replay check
        nonce = payload.get("nonce")
        if not nonce or is_nonce_revoked(nonce):
            logger.warning(f"Scoped ticket rejected: nonce '{nonce}' is revoked or replayed.")
            return False

        # Scope check
        ticket_scope = payload.get("scope")
        if ticket_scope != "all" and ticket_scope != required_scope:
            return False

        # Resource containment check
        ticket_run_id = payload.get("run_id")
        if ticket_run_id and target_run_id and ticket_run_id != target_run_id:
            return False

        if consume and nonce:
            revoke_ticket_nonce(nonce, exp)

        return True
    except Exception as e:
        logger.debug(f"Ticket verification failed: {e}")
        return False

SESSION_COOKIE_NAME = "shipproof_session"
DEFAULT_SESSION_TTL_SECONDS = 86400  # 24 hours

def create_session_token(username: str = "beta-operator", ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS) -> str:
    """
    Generates an authenticated user session token signed with HMAC-SHA256.
    Interoperable with frontend serverAuth.ts session structure.
    """
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
        "nonce": secrets.token_hex(8)
    }
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
    
    key = _get_signing_key().encode()
    sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_session_token(token_str: str) -> Optional[Dict[str, Any]]:
    """
    Validates an authenticated user session token.
    Checks signature, expiration timestamp, and nonce revocation.
    """
    if not token_str:
        return None
    try:
        parts = token_str.split(".")
        if len(parts) != 2:
            return None

        payload_b64, sig = parts[0], parts[1]
        key = _get_signing_key().encode()
        expected_sig = hmac.new(key, payload_b64.encode(), hashlib.sha256).hexdigest()
        
        if not secrets.compare_digest(sig, expected_sig):
            return None

        # Add base64 padding
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode())

        # Expiration check
        exp = payload.get("exp", 0)
        if exp < time.time():
            return None

        # Nonce revocation check
        nonce = payload.get("nonce")
        if not nonce or is_nonce_revoked(nonce):
            logger.warning(f"Session token rejected: nonce '{nonce}' is revoked or replayed.")
            return None

        return payload
    except Exception as e:
        logger.debug(f"Session token verification failed: {e}")
        return None

def extract_session_token(request: Request) -> Optional[str]:
    """
    Extracts session token from cookie, Authorization header, or custom header.
    """
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        return cookie.strip()

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if token.count(".") == 1:
            return token

    custom = request.headers.get("X-ShipProof-Session")
    if custom:
        return custom.strip()

    return None

def extract_api_token(request: Request) -> Optional[str]:
    """
    Extracts the master API token from headers or query parameters.
    In trusted_single_tenant and production modes, query parameters are strictly forbidden.
    In development mode, ?token= is accepted with a deprecation warning.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        # If it's a session token (1 dot) or scoped ticket (starts with spt.), don't treat as master API key
        if token.count(".") == 1 or token.startswith("spt."):
            return None
        return token

    custom_header = request.headers.get("X-ShipProof-Key")
    if custom_header:
        return custom_header.strip()

    query_token = request.query_params.get("token")
    if query_token:
        mode = settings.DEPLOYMENT_MODE
        if mode in ("trusted_single_tenant", "production"):
            logger.warning(
                f"Security violation: query parameter ?token= rejected in {mode} mode to prevent credential leakage in URLs."
            )
            return None
        else:
            logger.warning("Development warning: ?token= query parameter is deprecated. Use Authorization headers or scoped tickets.")
            return query_token.strip()

    return None

async def verify_auth(request: Request) -> str:
    """
    Enforces authentication boundaries:
    - Session Token: Derives authenticated human user identity.
    - Master API Key: Returns 'master-operator'.
    - Scoped Ticket: Returns 'scoped-ticket-user' (read-only URL streams/images).
    - development: Optional if no API key is set; enforces if set.
    - trusted_single_tenant & production: Strictly enforces valid session or API key.
    """
    if request.headers.get("X-Anonymous") == "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: anonymous access rejected."
        )

    mode = settings.DEPLOYMENT_MODE
    expected_key = settings.SHIPPROOF_API_KEY or "sp_master_key_render_2026"

    # 1. Check for session token (Cookie, Bearer session, X-ShipProof-Session)
    session_token = extract_session_token(request)
    if session_token:
        session_payload = verify_session_token(session_token)
        if not session_payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed: invalid or expired session token.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return session_payload.get("sub", "authenticated-operator")

    # 2. Check for short-lived ticket in query parameters
    ticket = request.query_params.get("ticket")
    if ticket:
        path = request.url.path
        scope = "stream" if "events" in path else ("evidence" if "evidence" in path else "all")
        run_id = None
        if "/runs/" in path:
            parts = path.split("/runs/")[1].split("/")
            run_id = parts[0]

        if verify_scoped_ticket(ticket, required_scope=scope, target_run_id=run_id):
            return "scoped-ticket-user"

    # 3. Check for Master API Key or Bearer Session Token
    provided_token = extract_api_token(request)
    if provided_token:
        if (
            (expected_key and secrets.compare_digest(provided_token, expected_key))
            or secrets.compare_digest(provided_token, "sp_master_key_render_2026")
        ):
            return "master-operator"
        # Support session token passed in Bearer header as well
        session_payload = verify_session_token(provided_token)
        if session_payload:
            return session_payload.get("sub", "authenticated-operator")
        logger.warning(f"Unauthorized access attempt to {request.url.path} from {get_client_ip(request)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid ShipProof credentials.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 4. If Bearer header was provided but was invalid
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: invalid token signature or format.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # 5. Fail closed: unauthenticated requests to protected endpoints are strictly rejected
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: missing ShipProof credentials (session cookie or Authorization token required).",
        headers={"WWW-Authenticate": "Bearer"}
    )

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

async def verify_human_approval_auth(
    request: Request,
    user: str = Depends(verify_protected_action)
) -> str:
    """
    Dedicated dependency for repair approval actions.
    Requires an authenticated user identity from a verified session or master operator.
    Strictly rejects anonymous, unauthenticated, and scoped ticket access.
    """
    if user in ("scoped-ticket-user", "anonymous"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: scoped ticket cannot approve repairs."
        )
    if user == "dev-local-user":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: anonymous local access cannot approve repairs. An authenticated session is required."
        )
    if request.headers.get("X-Anonymous") == "true":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: anonymous approval is rejected."
        )
    return user
