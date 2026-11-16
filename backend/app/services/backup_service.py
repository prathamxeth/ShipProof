import sqlite3
import os
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from backend.app.core.config import settings
from backend.app.core.logging import get_logger

logger = get_logger("backup_service")

class SQLiteBackupService:
    """
    High-integrity online backup and recovery service for ShipProof.
    Uses official sqlite3.backup API to perform hot, consistent snapshots
    without blocking concurrent read or write transactions.
    """

    @classmethod
    def get_live_db_path(cls) -> Path:
        """
        Resolves the actual SQLite database file on disk.
        """
        # Parse from DATABASE_URL e.g. sqlite+aiosqlite:///path/to/db
        db_url = settings.DATABASE_URL
        if "sqlite" in db_url:
            path_str = db_url.split("///")[-1]
            return Path(path_str).resolve()
        return (settings.DATA_DIR / "shipproof.db").resolve()

    @classmethod
    def perform_online_backup(
        cls,
        src_path: Optional[Path] = None,
        dest_path: Optional[Path] = None
    ) -> Path:
        """
        Executes a hot online SQLite backup using sqlite3.Connection.backup().
        Safe under concurrent writes in WAL mode.
        """
        src = (src_path or cls.get_live_db_path()).resolve()
        if not src.exists():
            raise FileNotFoundError(f"Source database not found at {src}")

        if not dest_path:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            dest = (settings.BACKUP_DIR / f"shipproof_backup_{timestamp}.db").resolve()
        else:
            dest = dest_path.resolve()

        dest.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Starting online SQLite backup from {src} to {dest}...")
        start_time = time.time()

        # Connect with read-only URI mode to prevent any locking interference
        src_uri = f"file:{src}?mode=ro"
        src_conn = sqlite3.connect(src_uri, uri=True)
        dest_conn = sqlite3.connect(str(dest))

        try:
            with dest_conn:
                src_conn.backup(dest_conn, pages=100)
        finally:
            src_conn.close()
            dest_conn.close()

        elapsed = time.time() - start_time
        file_size = dest.stat().st_size
        logger.info(f"Online backup completed in {elapsed:.2f}s ({file_size} bytes): {dest}")

        # Immediately verify integrity of the generated backup
        is_valid, msg = cls.verify_backup_integrity(dest)
        if not is_valid:
            raise RuntimeError(f"Backup integrity check failed: {msg}")

        return dest

    @classmethod
    def verify_backup_integrity(cls, backup_path: Path) -> Tuple[bool, str]:
        """
        Runs PRAGMA integrity_check on the SQLite backup file.
        """
        resolved = backup_path.resolve()
        if not resolved.exists():
            return False, f"File not found: {resolved}"

        conn = sqlite3.connect(str(resolved))
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            rows = cursor.fetchall()
            if rows and rows[0][0] == "ok":
                return True, "ok"
            else:
                errors = "; ".join([r[0] for r in rows])
                return False, errors
        except Exception as e:
            return False, str(e)
        finally:
            conn.close()

    @classmethod
    def restore_backup(cls, backup_path: Path, target_path: Path) -> Path:
        """
        Safely restores a backup into a target database path using online backup API.
        """
        src = backup_path.resolve()
        target = target_path.resolve()
        target.parent.mkdir(parents=True, exist_ok=True)

        is_valid, msg = cls.verify_backup_integrity(src)
        if not is_valid:
            raise ValueError(f"Cannot restore corrupted backup: {msg}")

        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dest_conn = sqlite3.connect(str(target))
        try:
            with dest_conn:
                src_conn.backup(dest_conn, pages=100)
        finally:
            src_conn.close()
            dest_conn.close()

        is_target_valid, target_msg = cls.verify_backup_integrity(target)
        if not is_target_valid:
            raise RuntimeError(f"Restored database integrity check failed: {target_msg}")

        return target

    @classmethod
    def verify_restored_database(
        cls,
        restored_path: Path,
        source_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Compares restored database records against live database
        and verifies that disk evidence packs referenced by runs exist.
        """
        src = (source_path or cls.get_live_db_path()).resolve()
        restored = restored_path.resolve()

        tables = [
            "projects",
            "verification_runs",
            "verification_steps",
            "verification_events",
            "repair_records",
            "repair_events"
        ]

        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        restored_conn = sqlite3.connect(f"file:{restored}?mode=ro", uri=True)

        counts_match = True
        table_counts: Dict[str, Dict[str, int]] = {}

        try:
            src_cur = src_conn.cursor()
            rest_cur = restored_conn.cursor()

            for table in tables:
                src_count = 0
                rest_count = 0
                try:
                    src_cur.execute(f"SELECT COUNT(*) FROM {table};")
                    src_count = src_cur.fetchone()[0]
                except Exception:
                    pass

                try:
                    rest_cur.execute(f"SELECT COUNT(*) FROM {table};")
                    rest_count = rest_cur.fetchone()[0]
                except Exception:
                    pass

                match = (src_count == rest_count)
                if not match:
                    counts_match = False

                table_counts[table] = {
                    "source": src_count,
                    "restored": rest_count,
                    "match": match
                }

            # Evidence pack disk existence check
            rest_cur.execute("SELECT id, evidence_pack_path FROM verification_runs WHERE evidence_pack_path IS NOT NULL;")
            runs_with_evidence = rest_cur.fetchall()
            
            missing_evidence_packs = []
            verified_evidence_packs = 0

            for run_id, pack_path in runs_with_evidence:
                if pack_path:
                    p = Path(pack_path)
                    # Check either zip pack or extracted folder
                    extracted_dir = settings.EVIDENCE_DIR / run_id
                    if p.exists() or extracted_dir.exists():
                        verified_evidence_packs += 1
                    else:
                        missing_evidence_packs.append({"run_id": run_id, "expected_path": pack_path})

            return {
                "status": "PASS" if (counts_match and len(missing_evidence_packs) == 0) else "PARTIAL",
                "counts_match": counts_match,
                "table_counts": table_counts,
                "evidence_check": {
                    "total_referenced_packs": len(runs_with_evidence),
                    "verified_existing": verified_evidence_packs,
                    "missing": missing_evidence_packs
                }
            }
        finally:
            src_conn.close()
            restored_conn.close()

backup_service = SQLiteBackupService()
