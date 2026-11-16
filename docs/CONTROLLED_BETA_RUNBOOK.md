# ShipProof — Controlled Beta Runbook

**Environment:** Controlled Single-Tenant Beta  
**App Version:** 0.1.0  
**Target Audience:** Site Reliability Engineers, DevOps Engineers, and Platform Operators  

---

## 1. System Topology & Architecture

```
                  +-----------------------------------+
                  |      Browser / Client (UI)        |
                  +-----------------+-----------------+
                                    |
                        HTTP / SSE (Port 3000/8000)
                                    v
+-------------------------------------------------------------------------+
|                  ShipProof Single-Tenant Appliance Host                 |
|                                                                         |
|  +-------------------------+         +-------------------------------+  |
|  |   Next.js Frontend      | <-----> |   FastAPI Backend (Port 8000) |  |
|  |   (Node.js Port 3000)   |         |   - Auth & Rate Limiting      |  |
|  +-------------------------+         |   - Runner Service            |  |
|                                      |   - Repair Orchestrator       |  |
|                                      +---------------+---------------+  |
|                                                      |                  |
|                                                      v                  |
|                                      +-------------------------------+  |
|                                      |   SQLite Database (WAL Mode)  |  |
|                                      |   - backend/data/shipproof.db |  |
|                                      +---------------+---------------+  |
|                                                      |                  |
|               +--------------------------------------+                  |
|               |                                                         |
|               v                                      v                  |
|  +-------------------------+         +-------------------------------+  |
|  |   Kane CLI Process Tree |         |   Antigravity IDE Agent       |  |
|  |   - kane-cli (Group Leader)|      |   - .shipproof/repairs/       |  |
|  |   - Playwright Subprocess|         |   - Unified Diff Patching     |  |
|  |   - Chromium Headless   |         +-------------------------------+  |
|  +-------------------------+                                            |
|                                                                         |
|  Evidence Packs Storage: backend/data/evidence/<run_id>/                |
|  Online Backups Storage: backend/data/backups/                          |
+-------------------------------------------------------------------------+
```

---

## 2. Configuration & Environment Variables

Create `/Users/pratham/Projects/ShipProof/.env` (or configure host environment):

```bash
# Deployment Mode: "trusted_single_tenant"
DEPLOYMENT_MODE=trusted_single_tenant

# Secret API Key (min 16 chars). If omitted, an ephemeral key is generated on startup
SHIPPROOF_API_KEY=sp_beta_7f8a9b2c3d4e5f60718293a4b5c6d7e8f9012345

# Target URL Security Policy
# Set to false to reject RFC 1918 private IPs and loopback in beta
ALLOW_LOCAL_TARGETS=false

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60

# Port & Host Bindings
HOST=127.0.0.1
PORT=8000

# Executable Paths
KANE_CLI_PATH=/opt/homebrew/bin/kane-cli
AGY_CLI_PATH=/Users/pratham/.gemini/bin/agy
AGY_DEFAULT_MODEL=gemini-3.8-flash-high

# Kane Timeout (seconds)
KANE_DEFAULT_TIMEOUT=120
```

---

## 3. Deployment & Startup Sequence

### Step 1: Install Dependencies
```bash
# Backend Virtualenv
python3 -m venv backend/.venv
source backend/.venv/bin/activate
pip install -r backend/requirements.txt

# Frontend Build
cd frontend
npm install
npm run build
cd ..
```

### Step 2: Start Backend Server
```bash
PYTHONPATH=. ./backend/.venv/bin/uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1
```

### Step 3: Start Frontend Server
```bash
cd frontend
npm run start -- -p 3000
```

### Step 4: Verify Health
```bash
curl -s http://127.0.0.1:8000/api/health
# Expected JSON output:
# {"status":"ok","app":"ShipProof","version":"0.1.0","database":"connected","kane_cli_installed":true,"agy_cli_installed":true}
```

---

## 4. Routine Operations

### 4.1 Creating a Hot Online Backup
The online backup API executes non-blocking backups using `sqlite3.backup` under active WAL mode:

```bash
curl -X POST http://127.0.0.1:8000/api/system/backup \
  -H "Authorization: Bearer sp_beta_7f8a9b2c3d4e5f60718293a4b5c6d7e8f9012345"
```
*Response Example:*
```json
{
  "status": "success",
  "backup_path": "/Users/pratham/Projects/ShipProof/backend/data/backups/shipproof_backup_20261116_125000.db",
  "file_size_bytes": 147456,
  "integrity_check": "ok"
}
```

### 4.2 Verifying and Testing Restore
To verify that the backup is undamaged and all referenced evidence files exist on disk:

```bash
curl -X POST "http://127.0.0.1:8000/api/system/backup/restore-verify" \
  -H "Authorization: Bearer sp_beta_7f8a9b2c3d4e5f60718293a4b5c6d7e8f9012345"
```
*Response Example:*
```json
{
  "status": "PASS",
  "backup_path": "/Users/pratham/Projects/ShipProof/backend/data/backups/shipproof_backup_20261116_125000.db",
  "counts_match": true,
  "table_counts": {
    "projects": {"source": 2, "restored": 2, "match": true},
    "verification_runs": {"source": 11, "restored": 11, "match": true},
    "repair_records": {"source": 3, "restored": 3, "match": true}
  },
  "evidence_check": {
    "total_referenced_packs": 3,
    "verified_existing": 3,
    "missing": []
  }
}
```

---

## 5. Incident Response & Troubleshooting

### Scenario A: Unresponsive Kane Execution or Timeout
* **Symptom:** A test run remains in `running` status longer than expected.
* **Mechanism:** ShipProof automatically sets a process timeout (`timeout + 15` seconds grace). If the process times out:
  1. `terminate_process_tree` sends `SIGTERM` to the entire process group.
  2. If children remain after 1.5s, `SIGKILL` is sent.
  3. The database transitions the run to `status="incomplete"`.
* **Manual Intervention:** If you need to immediately stop a run:
```bash
curl -X POST "http://127.0.0.1:8000/api/runs/<RUN_ID>/cancel" \
  -H "Authorization: Bearer sp_beta_7f8a9b2c3d4e5f60718293a4b5c6d7e8f9012345"
```

### Scenario B: Unexpected Backend Server Restart
* **Symptom:** Server crashes or host restarts while runs or repairs were actively in progress.
* **Automated Recovery:** Upon restart, FastAPI's lifespan invokes `recover_interrupted_states()`:
  - Any run in `running` or `queued` is marked `incomplete` (with reason `"Run interrupted by backend server restart"`).
  - Any repair in `APPLYING`, `VALIDATING`, or `RETESTING` is marked `FAILED`.
  - **No interrupted run is falsely marked as passed or verified.**

### Scenario C: Rate Limit Tripped (HTTP 429)
* **Symptom:** API returns `HTTP 429 Too Many Requests`.
* **Remedy:** The sliding-window rate limiter permits up to `RATE_LIMIT_PER_MINUTE` requests per IP address. Wait 60 seconds or adjust `RATE_LIMIT_PER_MINUTE` in `.env` if legitimate automated integration pipelines require higher throughput.

### Scenario D: Browser SSE Disconnects & Recovery
* **Symptom:** Network drops between frontend browser and backend during a 2-minute test run.
* **Recovery:** When the browser reconnects, it sends header `Last-Event-ID: <id>`. ShipProof automatically queries `verification_events` and replays all missed events starting from sequence `last_id + 1`. Deduplication ensures no duplicate cards or logs appear in the UI.

---

## 6. Security Boundaries for Beta Operators

1. **Host-Level Egress Filtering:** Because Kane CLI does not feature upstream proxy configuration flags, operate ShipProof Beta inside a VPC or subnet with strict outbound firewall rules (restricting egress to external target domains).
2. **Access Control:** Do not expose port 8000 or 3000 to the public Internet without an upstream reverse proxy (e.g. Nginx, Cloudflare Zero Trust, or AWS ALB) enforcing HTTPS and IP whitelisting.
3. **Evidence Protection:** Evidence packs contain HTTP request/response headers and screenshots. While ShipProof redacts common authorization headers, ensure `backend/data/evidence` permissions are restricted to the `shipproof` system service user (`chmod 700`).
