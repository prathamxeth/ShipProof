# ShipProof Disaster Recovery Procedure & Operational Runbook

**Document Version:** 1.0  
**Milestone:** 4.5 — Adversarial Beta Acceptance & Disaster Recovery Validation  
**Target Environment:** Controlled Single-Tenant Deployment & Local Appliance  
**Database Engine:** SQLite 3.x (WAL Mode enabled, Foreign Keys enforced)

---

## 1. Overview & Objectives

ShipProof stores orchestration metadata, verification runs, Kane execution step events, agent repair packets, diffs, and verification metrics in a dedicated SQLite database located at `data/shipproof.db`. Associated binary artifacts (Kane screenshots, session logs, video traces, and evidence packages) reside in `data/evidence/<run_id>/`.

This document defines the disaster recovery (DR) procedures, operational runbooks, integrity checks, and recovery verification protocols required to handle database corruption, unexpected host crashes, disk exhaustion, and recovery drills.

### Recovery Objectives
- **Recovery Time Objective (RTO):** < 2 minutes (cold restore of local database file and evidence cross-check).
- **Recovery Point Objective (RPO):** Bound to the latest scheduled backup snapshot interval (recommended: pre-batch execution and hourly automated backup).

---

## 2. Backup Architecture & Safeguards

ShipProof implements online hot backups via `backend/app/services/backup_service.py` using SQLite's native online backup API (`sqlite3.Connection.backup()`).

### Operational Safeguards
1. **Pre-flight Disk Space Check:** The backup engine verifies that the target filesystem has at least **50 MB** of free disk space and exceeds twice the current database size before initiating a backup.
2. **Atomic Write Replacement:** Backups are written to a temporary file (`shipproof_backup_<timestamp>.db.tmp`) and atomically renamed upon successful completion and verification.
3. **Database Integrity Verification:**
   - `PRAGMA integrity_check` must return `"ok"`.
   - `PRAGMA foreign_key_check` must return zero violations.
4. **Cryptographic Checksumming:** A companion `.sha256` hash is generated alongside every `.db` backup file.
5. **Automated Retention Management:** The backup directory (`data/backups/`) retains the 10 most recent verified backups by default (`keep_count=10`). Older backup files and their companion `.sha256` files are automatically pruned.
6. **Filesystem Permission Lockdown:** All backup and database directories are automatically enforced with POSIX permissions `0700` (`rwx------`).

---

## 3. Disaster Triggers & Severity Classification

| Severity | Trigger Scenario | Immediate Impact | DR Action |
|:---|:---|:---|:---|
| **SEV-1** | Malformed / Corrupted `shipproof.db` (`PRAGMA integrity_check` fails or SQLite raises `DatabaseError`) | API returns 503 / 500; all runs blocked | **Full Restore Runbook (Section 4)** |
| **SEV-1** | Host crash / power loss mid-transaction with unrecoverable WAL corruption | Startup failure on SQLite lock or recovery loop | **Full Restore Runbook (Section 4)** |
| **SEV-2** | Foreign key corruption or cascade failure | Inconsistent run or repair lifecycle queries | **Foreign Key Reconciliation (Section 5)** |
| **SEV-2** | Filesystem out-of-space during active Kane run execution | Run halted; backup engine refuses backup to prevent truncation | **Disk Cleanup & Re-run (Section 6)** |
| **SEV-3** | Orphaned disk evidence directory (run record missing in DB) | Storage bloat; dashboard metric mismatch | **Evidence Reconciliation (Section 7)** |

---

## 4. Step-by-Step Operator Recovery Runbook (SEV-1)

Follow this exact sequence when recovering from a corrupted or damaged database:

### Step 1: Terminate the ShipProof Application Service
Stop the running FastAPI backend and any active Kane CLI processes to release file descriptors:

```bash
# Stop backend service (systemd or process supervisor)
pkill -f "uvicorn.*backend.app.main:app" || true

# Verify no orphaned processes hold file locks on data/
lsof data/shipproof.db || true
```

### Step 2: Identify the Latest Verified Backup
List available backups sorted by timestamp in `data/backups/`:

```bash
ls -lat data/backups/shipproof_backup_*.db
```

Select the latest backup file (e.g., `data/backups/shipproof_backup_20261116_120000.db`).

### Step 3: Validate Backup Integrity and Checksum
Verify the cryptographic SHA256 checksum and SQLite internal structure before proceeding:

```bash
BACKUP_FILE="data/backups/shipproof_backup_20261116_120000.db"

# 1. Verify SHA-256
shasum -a 256 -c "${BACKUP_FILE}.sha256"

# 2. Verify SQLite integrity
sqlite3 "$BACKUP_FILE" "PRAGMA integrity_check;"
# Output must be: ok

# 3. Verify Foreign Keys
sqlite3 "$BACKUP_FILE" "PRAGMA foreign_key_check;"
# Output must be empty
```

### Step 4: Quarantine Damaged Database
Preserve the corrupted database and WAL journal files for post-mortem forensics:

```bash
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mv data/shipproof.db "data/shipproof.db.corrupt.${TIMESTAMP}"
[ -f data/shipproof.db-wal ] && mv data/shipproof.db-wal "data/shipproof.db-wal.corrupt.${TIMESTAMP}"
[ -f data/shipproof.db-shm ] && mv data/shipproof.db-shm "data/shipproof.db-shm.corrupt.${TIMESTAMP}"
```

### Step 5: Restore Verified Backup
Execute the atomic restore using the verified backup:

```bash
cp "$BACKUP_FILE" data/shipproof.db
chmod 600 data/shipproof.db
```

### Step 6: Execute Post-Restore Integrity Verification
Run programmatic validation against the restored database:

```bash
# Ensure WAL mode and foreign keys are active
sqlite3 data/shipproof.db "PRAGMA foreign_keys = ON; PRAGMA foreign_key_check; PRAGMA integrity_check;"
```

### Step 7: Restart ShipProof Application
Start the FastAPI backend service:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

### Step 8: Execute Health & Status Verification
Verify the live health check API responds with healthy status and zero database errors:

```bash
curl -s http://127.0.0.1:8000/api/health | jq .
```
Expected output:
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "0.1.0",
  "deployment_mode": "controlled_single_tenant"
}
```

---

## 5. Foreign Key Integrity Reconciliation (SEV-2)

If `PRAGMA foreign_key_check` reports orphaned child rows (e.g., verification step events or repair attempts referencing deleted parent run IDs):

```bash
# Query specific violations
sqlite3 data/shipproof.db "PRAGMA foreign_key_check;"
```

If orphaned records exist, run the cleanup script inside SQLite:
```sql
BEGIN TRANSACTION;

-- Clean orphaned step events
DELETE FROM verification_steps 
WHERE run_id NOT IN (SELECT id FROM verification_runs);

-- Clean orphaned repair attempts
DELETE FROM repair_attempts 
WHERE run_id NOT IN (SELECT id FROM verification_runs);

-- Verify clean state
PRAGMA foreign_key_check;

COMMIT;
```

---

## 6. Disk Exhaustion Recovery (SEV-2)

When disk space falls below 50 MB, backup creation fails defensively to avoid truncating backups:

1. Inspect disk usage:
   ```bash
   df -h data/
   du -sh data/evidence/* | sort -hr | head -n 20
   ```
2. Prune old Kane video traces and raw screenshots for completed runs older than 30 days (preserving JSON metadata and summary evidence packs):
   ```bash
   find data/evidence/ -type f -name "*.png" -mtime +30 -delete
   ```
3. Trigger manual backup pruning via CLI/Python:
   ```python
   from backend.app.services.backup_service import BackupService
   BackupService.prune_old_backups(keep_count=5)
   ```

---

## 7. Evidence Cross-Check & Disk Reconciliation (SEV-3)

To ensure that disk evidence bundles match database verification run records:

```python
import os
import sqlite3

conn = sqlite3.connect("data/shipproof.db")
c = conn.cursor()
db_runs = set(row[0] for row in c.execute("SELECT id FROM verification_runs").fetchall())

evidence_dirs = set(os.listdir("data/evidence")) if os.path.exists("data/evidence") else set()

orphans_on_disk = evidence_dirs - db_runs
missing_on_disk = db_runs - evidence_dirs

print(f"Orphaned disk evidence directories: {len(orphans_on_disk)}")
print(f"Database runs missing disk evidence: {len(missing_on_disk)}")
```

---

## 8. Automated Drill Verification

The disaster recovery runbook is verified in the automated CI test suite via:
`backend/tests/test_disaster_recovery_drill.py`

This test programmatically simulates:
1. Online hot backup creation of an active database.
2. Simulated database corruption (overwriting header bytes with zeroed garbage).
3. Database restoration from hot backup.
4. Post-recovery foreign key and table record integrity verification.
5. In-flight state recovery (cancelling stale 'running' records upon recovery).

**Drill Execution Command:**
```bash
PYTHONPATH=. ./backend/.venv/bin/pytest backend/tests/test_disaster_recovery_drill.py -v
```
Output: **PASSED (4 / 4 drills passed)**.
