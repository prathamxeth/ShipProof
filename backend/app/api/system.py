from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path
import tempfile
from backend.app.core.auth import verify_protected_action
from backend.app.services.backup_service import backup_service
from backend.app.core.logging import get_logger

router = APIRouter(prefix="/system", tags=["System & Maintenance"])
logger = get_logger("api.system")

class BackupResponse(BaseModel):
    status: str
    backup_path: str
    file_size_bytes: int
    integrity_check: str

class RestoreVerifyResponse(BaseModel):
    status: str
    backup_path: str
    counts_match: bool
    table_counts: Dict[str, Dict[str, Any]]
    evidence_check: Dict[str, Any]

@router.post(
    "/backup",
    response_model=BackupResponse,
    summary="Create a hot online SQLite backup",
    dependencies=[Depends(verify_protected_action)]
)
async def create_backup():
    """
    Creates a non-blocking hot online backup using SQLite's online backup API,
    and runs PRAGMA integrity_check to verify consistency.
    """
    try:
        backup_path = backup_service.perform_online_backup()
        is_valid, msg = backup_service.verify_backup_integrity(backup_path)
        return BackupResponse(
            status="success" if is_valid else "error",
            backup_path=str(backup_path),
            file_size_bytes=backup_path.stat().st_size,
            integrity_check=msg
        )
    except Exception as e:
        logger.exception(f"Failed to create online backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backup operation failed: {str(e)}"
        )

@router.post(
    "/backup/restore-verify",
    response_model=RestoreVerifyResponse,
    summary="Restore backup into temporary database and verify record & evidence integrity",
    dependencies=[Depends(verify_protected_action)]
)
async def restore_and_verify(backup_path: Optional[str] = None):
    """
    Restores specified backup (or latest backup) into a temporary test database,
    verifies table row counts, and verifies that disk evidence packs exist.
    """
    try:
        if backup_path:
            p = Path(backup_path)
        else:
            # Pick latest backup from BACKUP_DIR
            backups = sorted(
                list(backup_service.get_live_db_path().parent.parent.joinpath("data", "backups").glob("*.db")),
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if not backups:
                # Perform one fresh
                p = backup_service.perform_online_backup()
            else:
                p = backups[0]

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            backup_service.restore_backup(p, tmp_path)
            report = backup_service.verify_restored_database(tmp_path)
            return RestoreVerifyResponse(
                status=report["status"],
                backup_path=str(p),
                counts_match=report["counts_match"],
                table_counts=report["table_counts"],
                evidence_check=report["evidence_check"]
            )
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    except Exception as e:
        logger.exception(f"Failed to restore and verify backup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Restore verification failed: {str(e)}"
        )
