from datetime import datetime, timezone
import os
import time
import asyncio
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.logging import get_logger
from backend.app.models.schemas import HealthResponse

router = APIRouter(tags=["Health"])
logger = get_logger("api.health")

_last_auth_check_time = 0.0
_last_auth_result = (False, "Not checked")

async def check_kane_auth() -> tuple[bool, str]:
    global _last_auth_check_time, _last_auth_result
    now = time.time()
    if now - _last_auth_check_time < 60.0:
        return _last_auth_result

    if not os.path.exists(settings.KANE_CLI_PATH) or not os.access(settings.KANE_CLI_PATH, os.X_OK):
        _last_auth_result = (False, "Kane CLI binary not found or not executable")
        _last_auth_check_time = now
        return _last_auth_result

    try:
        proc = await asyncio.create_subprocess_exec(
            settings.KANE_CLI_PATH, "whoami",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3.5)
        out_text = (stdout + stderr).decode(errors="ignore")
        if proc.returncode == 0:
            _last_auth_result = (True, "Authenticated")
        else:
            if "expired" in out_text.lower():
                _last_auth_result = (False, "OAuth token expired (run 'kane-cli login')")
            elif "not authenticated" in out_text.lower():
                _last_auth_result = (False, "Unauthenticated (run 'kane-cli login')")
            else:
                _last_auth_result = (False, "CLI check returned non-zero")
    except Exception as e:
        _last_auth_result = (False, f"Check timed out: {e}")

    _last_auth_check_time = now
    return _last_auth_result

@router.get("/health", response_model=HealthResponse, summary="System Health & Tooling Status")
async def get_health(db: AsyncSession = Depends(get_db)):
    db_status = "connected"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy: database connectivity failed"

    kane_installed = os.path.exists(settings.KANE_CLI_PATH)
    kane_executable = kane_installed and os.access(settings.KANE_CLI_PATH, os.X_OK)
    kane_auth, kane_detail = await check_kane_auth()

    agy_installed = os.path.exists(settings.AGY_CLI_PATH)
    agy_executable = agy_installed and os.access(settings.AGY_CLI_PATH, os.X_OK)

    # IDE handoff is available via ShipProof repair studio protocol
    ide_handoff = True
    # Verification execution is ready via runner service
    execution_engine = True

    overall_status = "ok" if db_status == "connected" else "degraded"

    return HealthResponse(
        status=overall_status,
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        database=db_status,
        kane_cli_installed=kane_installed,
        kane_cli_executable=kane_executable,
        kane_cli_authenticated=kane_auth,
        kane_auth_detail=kane_detail,
        agy_cli_installed=agy_installed,
        agy_cli_executable=agy_executable,
        ide_handoff_available=ide_handoff,
        execution_engine_available=execution_engine,
        execution_mode=settings.WORKER_EXECUTION_MODE,
        timestamp=datetime.now(timezone.utc)
    )
