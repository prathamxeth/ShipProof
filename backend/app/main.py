from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI
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
            r.status = "incomplete"
            r.failure_reason = "Run interrupted by backend server restart"
            r.completed_at = datetime.now(timezone.utc)
            r.updated_at = datetime.now(timezone.utc)
            logger.warning(f"Recovered interrupted run {r.id}: set status='incomplete'")

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}...")
    
    # Enforce secure directory permissions on sensitive storage paths
    try:
        os.chmod(settings.DATA_DIR, 0o700)
        os.chmod(settings.EVIDENCE_DIR, 0o700)
        os.chmod(settings.BACKUP_DIR, 0o700)
    except Exception as perm_err:
        logger.warning(f"Directory permissions setup warning: {perm_err}")

    await init_db()
    logger.info("Database initialized.")
    await recover_interrupted_states()
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")
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

# Request payload size limiter (10 MB bound)
@app.middleware("http")
async def limit_request_size(request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > 10 * 1024 * 1024:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Payload too large: request body exceeds 10MB limit."}
                )
        except ValueError:
            pass
    return await call_next(request)

# Exception handlers
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
