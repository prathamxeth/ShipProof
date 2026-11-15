from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.app.core.config import settings
from backend.app.core.logging import setup_logging, get_logger
from backend.app.core.database import init_db
from backend.app.core.errors import (
    ShipProofException,
    shipproof_exception_handler,
    generic_exception_handler
)
from backend.app.api import api_router

# Set up logging early
setup_logging()
logger = get_logger("main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}...")

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
