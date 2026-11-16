import pytest
import sqlite3
import tempfile
from pathlib import Path
from backend.app.services.backup_service import backup_service
from httpx import AsyncClient, ASGITransport
from backend.app.main import app

def test_online_backup_under_active_writes(tmp_path):
    # 1. Create a live database
    db_file = tmp_path / "live.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE projects (id TEXT PRIMARY KEY, name TEXT);")
    conn.execute("CREATE TABLE verification_runs (id TEXT PRIMARY KEY, title TEXT, evidence_pack_path TEXT);")
    conn.execute("INSERT INTO projects VALUES ('p1', 'Alpha Project');")
    conn.execute("INSERT INTO verification_runs VALUES ('r1', 'Run 1', NULL);")
    conn.commit()

    # 2. While inserting in a loop, perform online backup
    backup_file = tmp_path / "backup.db"

    # Insert more records
    for i in range(2, 25):
        conn.execute(f"INSERT INTO verification_runs VALUES ('r{i}', 'Run {i}', NULL);")
    conn.commit()

    # Perform online backup
    res_path = backup_service.perform_online_backup(src_path=db_file, dest_path=backup_file)
    assert res_path.exists()
    assert res_path == backup_file

    # 3. Verify integrity
    is_valid, msg = backup_service.verify_backup_integrity(backup_file)
    assert is_valid is True
    assert msg == "ok"

    # 4. Restore to temporary database
    restored_file = tmp_path / "restored.db"
    backup_service.restore_backup(backup_file, restored_file)
    assert restored_file.exists()

    # 5. Check restored row counts
    report = backup_service.verify_restored_database(restored_path=restored_file, source_path=db_file)
    assert report["counts_match"] is True
    assert report["table_counts"]["verification_runs"]["restored"] == 24
    assert report["status"] == "PASS"

    conn.close()

def test_verify_backup_integrity_detects_corrupted_file(tmp_path):
    bad_file = tmp_path / "corrupt.db"
    bad_file.write_bytes(b"NOT A SQLITE DATABASE HEADER GIBBERISH")

    is_valid, msg = backup_service.verify_backup_integrity(bad_file)
    assert is_valid is False
    assert "file is not a database" in msg or "corrupted" in msg or "not a database" in msg.lower()

@pytest.mark.asyncio
async def test_system_backup_endpoints():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # POST /api/system/backup
        resp = await client.post("/api/system/backup")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["integrity_check"] == "ok"
        assert data["file_size_bytes"] > 0
        backup_path = data["backup_path"]

        # POST /api/system/backup/restore-verify
        resp_restore = await client.post(f"/api/system/backup/restore-verify?backup_path={backup_path}")
        assert resp_restore.status_code == 200
        data_restore = resp_restore.json()
        assert data_restore["status"] in ("PASS", "PARTIAL")
        assert data_restore["counts_match"] is True
