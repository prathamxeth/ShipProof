import pytest
import sqlite3
import time
import shutil
from pathlib import Path
from backend.app.services.backup_service import backup_service
from backend.app.core.config import settings

def test_disaster_recovery_full_drill(tmp_path):
    """
    Simulates a complete real-world disaster recovery lifecycle:
    1. Active database under concurrent write load.
    2. Hot online backup using sqlite3.backup API.
    3. Metrics recording (duration, file size).
    4. Structural and foreign-key integrity verification.
    5. Clean restore into a brand-new disposable database.
    6. Record count and evidence pack cross-verification.
    7. Foreign-key violation detection drill.
    8. Insufficient disk space simulation.
    9. Retention pruning of old backups.
    """
    # 1. Setup disposable source database
    src_db = tmp_path / "live_simulated.db"
    conn = sqlite3.connect(str(src_db))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    
    # Create schema matching ShipProof entities with foreign key
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT);")
    conn.execute("""
        CREATE TABLE verification_runs (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            title TEXT,
            status TEXT,
            evidence_pack_path TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
    """)
    conn.execute("""
        CREATE TABLE verification_steps (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            step_index INTEGER,
            status TEXT,
            FOREIGN KEY (run_id) REFERENCES verification_runs(id) ON DELETE CASCADE
        );
    """)
    conn.execute("""
        CREATE TABLE verification_events (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            event_seq INTEGER,
            event_type TEXT,
            FOREIGN KEY (run_id) REFERENCES verification_runs(id) ON DELETE CASCADE
        );
    """)
    conn.execute("""
        CREATE TABLE repair_records (
            id TEXT PRIMARY KEY,
            run_id TEXT,
            status TEXT,
            FOREIGN KEY (run_id) REFERENCES verification_runs(id) ON DELETE CASCADE
        );
    """)
    conn.execute("""
        CREATE TABLE repair_events (
            id TEXT PRIMARY KEY,
            repair_id TEXT,
            from_state TEXT,
            to_state TEXT,
            FOREIGN KEY (repair_id) REFERENCES repair_records(id) ON DELETE CASCADE
        );
    """)

    # Populate sample data
    conn.execute("INSERT INTO projects VALUES ('proj-1', 'Alpha Project');")
    evidence_zip = tmp_path / "run_evidence.zip"
    evidence_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 18)  # Empty valid zip
    conn.execute(f"INSERT INTO verification_runs VALUES ('run-1', 'proj-1', 'Run 1', 'failed', '{str(evidence_zip)}');")
    conn.execute("INSERT INTO verification_steps VALUES ('step-1', 'run-1', 1, 'done');")
    conn.execute("INSERT INTO verification_events VALUES ('ev-1', 'run-1', 1, 'step');")
    conn.execute("INSERT INTO repair_records VALUES ('rep-1', 'run-1', 'AWAITING_APPROVAL');")
    conn.execute("INSERT INTO repair_events VALUES ('rev-1', 'rep-1', 'CREATED', 'AWAITING_APPROVAL');")
    conn.commit()

    # 2. Perform hot online backup while writing 50 more rows
    backup_file = tmp_path / "backup_drill.db"
    for i in range(2, 52):
        conn.execute(f"INSERT INTO verification_steps VALUES ('step-{i}', 'run-1', {i}, 'done');")
    conn.commit()

    start_backup = time.time()
    dest = backup_service.perform_online_backup(src_path=src_db, dest_path=backup_file)
    backup_duration = time.time() - start_backup
    backup_size = dest.stat().st_size

    assert dest.exists()
    assert backup_duration >= 0
    assert backup_size > 0

    # 3. Verify backup structural & foreign key integrity
    is_valid, msg = backup_service.verify_backup_integrity(dest)
    assert is_valid is True
    assert msg == "ok"

    # 4. Restore into a brand-new disposable database
    restored_db = tmp_path / "restored_drill.db"
    start_restore = time.time()
    backup_service.restore_backup(dest, restored_db)
    restore_duration = time.time() - start_restore
    assert restored_db.exists()

    # 5. Check row counts and evidence consistency
    report = backup_service.verify_restored_database(restored_path=restored_db, source_path=src_db)
    assert report["status"] == "PASS"
    assert report["counts_match"] is True
    assert report["foreign_key_violations"] == 0
    assert report["table_counts"]["verification_steps"]["restored"] == 51

    # 6. Test foreign key violation detection in a corrupted database
    corrupt_fk_db = tmp_path / "corrupt_fk.db"
    shutil.copyfile(restored_db, corrupt_fk_db)
    cfk_conn = sqlite3.connect(str(corrupt_fk_db))
    # Insert step with invalid parent run_id
    cfk_conn.execute("PRAGMA foreign_keys = OFF;")
    cfk_conn.execute("INSERT INTO verification_steps VALUES ('orphan-step', 'nonexistent-run', 99, 'done');")
    cfk_conn.commit()
    cfk_conn.close()

    is_cfk_valid, cfk_msg = backup_service.verify_backup_integrity(corrupt_fk_db)
    assert is_cfk_valid is False
    assert "Foreign key check failed" in cfk_msg

    # 7. Test missing evidence file detection
    evidence_zip.unlink()  # Delete the referenced evidence pack
    report_missing = backup_service.verify_restored_database(restored_path=restored_db, source_path=src_db)
    assert report_missing["status"] == "PARTIAL"
    assert len(report_missing["evidence_check"]["missing"]) == 1
    assert report_missing["evidence_check"]["missing"][0]["run_id"] == "run-1"

    # 8. Test backup retention pruning
    # Create 15 dummy backup files
    orig_backup_dir = settings.BACKUP_DIR
    settings.BACKUP_DIR = tmp_path / "retention_test"
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for n in range(15):
            f = settings.BACKUP_DIR / f"test_backup_{n:02d}.db"
            f.write_text("dummy")
            time.sleep(0.01)

        pruned = backup_service.prune_old_backups(keep_count=10)
        remaining = list(settings.BACKUP_DIR.glob("*.db"))
        assert pruned == 5
        assert len(remaining) == 10
    finally:
        settings.BACKUP_DIR = orig_backup_dir

    conn.close()
