from datetime import datetime, timezone
import os
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.logging import get_logger
from backend.app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])
logger = get_logger("api.health")

@router.get("/health", response_model=HealthResponse, summary="System Health & Tooling Status")
async def get_health(db: AsyncSession = Depends(get_db)):
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"unhealthy: {str(e)}"

    kane_exists = os.path.exists(settings.KANE_CLI_PATH) and os.access(settings.KANE_CLI_PATH, os.X_OK)
    agy_exists = os.path.exists(settings.AGY_CLI_PATH) and os.access(settings.AGY_CLI_PATH, os.X_OK)

    return HealthResponse(
        status="ok" if db_status == "connected" else "degraded",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        database=db_status,
        kane_cli_installed=kane_exists,
        agy_cli_installed=agy_exists,
        timestamp=datetime.now(timezone.utc)
    )
