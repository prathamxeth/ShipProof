import os
import shutil
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from backend.app.core.config import settings
from backend.app.core.logging import setup_logging, get_logger
from backend.app.core.database import init_db, AsyncSessionLocal
from backend.app.models.entities import VerificationRunEntity, RepairRecordEntity
from backend.app.core.errors import (
    ShipProofException,
    shipproof_exception_handler,
    generic_exception_handler
)
from backend.app.services.runner_service import runner_service
from backend.app.api import api_router

# Set up logging early
setup_logging()
logger = get_logger("main")

class PayloadTooLargeException(Exception):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)

async def payload_too_large_exception_handler(request: Request, exc: PayloadTooLargeException):
    return JSONResponse(status_code=413, content={"detail": exc.detail})

class PayloadSizeLimitMiddleware:
    """
    ASGI middleware enforcing a strict maximum request body size limit (default 10 MB).
    Protects against DoS from oversized Content-Length, missing Content-Length,
    chunked transfer encoding, and streaming bodies without breaking downstream route consumption.
    """
    def __init__(self, app, max_bytes: int = 10 * 1024 * 1024):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length_raw = headers.get(b"content-length")

        if content_length_raw is not None:
            try:
                content_length = int(content_length_raw.decode("latin1").strip())
                if content_length < 0:
                    resp = JSONResponse(
                        status_code=400,
                        content={"detail": "Bad request: Content-Length cannot be negative."}
                    )
                    await resp(scope, receive, send)
                    return
                if content_length > self.max_bytes:
                    resp = JSONResponse(
                        status_code=413,
                        content={"detail": f"Payload too large: request body exceeds {self.max_bytes // (1024 * 1024)}MB limit."}
                    )
                    await resp(scope, receive, send)
                    return
            except ValueError:
                resp = JSONResponse(
                    status_code=400,
                    content={"detail": "Bad request: invalid Content-Length header."}
                )
                await resp(scope, receive, send)
                return

        total_received = 0

        async def limited_receive():
            nonlocal total_received
            message = await receive()
            if message.get("type") == "http.request":
                body_chunk = message.get("body", b"")
                total_received += len(body_chunk)
                if total_received > self.max_bytes:
                    raise PayloadTooLargeException(
                        f"Payload too large: request body exceeds {self.max_bytes // (1024 * 1024)}MB limit."
                    )
            return message

        await self.app(scope, limited_receive, send)

async def recover_interrupted_states():
    """
    On backend startup, transitions any runs or repairs that were left in an active
    transient state (e.g. running, queued, applying, validating, retesting) to truthful terminal states.
    Does not convert interrupted runs to passed or verified.
    """
    async with AsyncSessionLocal() as session:
        runs_res = await session.execute(
            select(VerificationRunEntity).where(VerificationRunEntity.status.in_(["running", "queued"]))
        )
        interrupted_runs = runs_res.scalars().all()
        for r in interrupted_runs:
            r.status = "failed"
            r.failure_reason = "Run interrupted or halted by backend restart"
            r.completed_at = datetime.now(timezone.utc)
            r.updated_at = datetime.now(timezone.utc)
            logger.warning(f"Recovered interrupted run {r.id}: set status='failed'")

        repairs_res = await session.execute(
            select(RepairRecordEntity).where(RepairRecordEntity.status.in_(["APPLYING", "VALIDATING", "RETESTING"]))
        )
        interrupted_repairs = repairs_res.scalars().all()
        for rep in interrupted_repairs:
            rep.status = "FAILED"
            rep.failure_notes = "Repair process interrupted by backend server restart"
            rep.completed_at = datetime.now(timezone.utc)
            rep.updated_at = datetime.now(timezone.utc)
            logger.warning(f"Recovered interrupted repair {rep.id}: set status='FAILED'")

        if interrupted_runs or interrupted_repairs:
            await session.commit()
            logger.info(f"Startup recovery completed: {len(interrupted_runs)} run(s) and {len(interrupted_repairs)} repair(s) finalized.")

def enforce_directory_permissions():
    """
    Ensures runtime storage directories (DATA_DIR, EVIDENCE_DIR, BACKUP_DIR)
    exist with secure POSIX permissions (0700: rwx------).
    Fails closed in trusted_single_tenant and production modes if permissions cannot be enforced.
    """
    dirs = [settings.DATA_DIR, settings.EVIDENCE_DIR, settings.BACKUP_DIR]
    mode = settings.DEPLOYMENT_MODE

    for directory in dirs:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o700)
            current_mode = directory.stat().st_mode & 0o777
            if current_mode != 0o700:
                msg = f"Failed to verify secure permissions on {directory}: expected 0700, got {oct(current_mode)}"
                if mode in ("trusted_single_tenant", "production"):
                    logger.error(msg)
                    raise RuntimeError(f"Startup security violation: {msg}")
                else:
                    logger.warning(f"Development mode permission warning: {msg}")
        except Exception as err:
            if isinstance(err, RuntimeError):
                raise
            msg = f"Failed to enforce secure 0700 permissions on directory '{directory}': {err}"
            if mode in ("trusted_single_tenant", "production"):
                logger.error(msg)
                raise RuntimeError(f"Startup security violation: {msg}") from err
            else:
                logger.warning(f"Development mode permission warning: {msg}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}...")
    
    # Enforce secure directory permissions on sensitive storage paths before services use them
    enforce_directory_permissions()

    await init_db()
    logger.info("Database initialized.")
    await recover_interrupted_states()

    # Recover orphan worker containers and stale IPC resources from previous crash
    try:
        from backend.app.services.worker_manager import worker_manager
        orphans = worker_manager.runtime.recover_orphans()
        if orphans:
            logger.info(f"Startup recovery: cleaned up {len(orphans)} orphan worker container(s): {orphans}")
        if settings.WORKER_IPC_DIR.exists():
            for p in settings.WORKER_IPC_DIR.iterdir():
                if p.is_dir() and not p.is_symlink():
                    shutil.rmtree(p, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Could not recover worker orphans on startup: {e}")

    # Start Revenue Guard Autonomous Secret Shopper sentinel
    try:
        from backend.app.services.revenue_guard_service import revenue_guard
        revenue_guard.start()
    except Exception as e:
        logger.warning(f"Could not start Revenue Guard on startup: {e}")

    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")
    try:
        from backend.app.services.revenue_guard_service import revenue_guard
        revenue_guard.stop()
    except Exception:
        pass
    await runner_service.terminate_all_processes()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="ShipProof Backend — Autonomous AI Software Verification & Repair",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request payload size limiter (10 MB bound, ASGI stream + Content-Length)
app.add_middleware(PayloadSizeLimitMiddleware, max_bytes=10 * 1024 * 1024)

from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler

# Exception handlers
app.add_exception_handler(PayloadTooLargeException, payload_too_large_exception_handler)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    cause = getattr(exc, "__cause__", None)
    if isinstance(cause, PayloadTooLargeException):
        return JSONResponse(status_code=413, content={"detail": cause.detail})
    return await http_exception_handler(request, exc)

app.add_exception_handler(ShipProofException, shipproof_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Mount API routes
app.include_router(api_router)

@app.get("/", tags=["Root"])
async def root():
    return {
        "app": settings.APP_NAME,
        "tagline": "Your AI writes the code. ShipProof proves it works.",
        "version": settings.APP_VERSION,
        "docs": "/api/docs",
        "health": "/api/health"
    }
