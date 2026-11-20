# ShipProof — Controlled Single-Tenant Beta Deployment Guide

**Document Version:** 2.0  
**Milestone:** 4.6.6 — Final Artifact Integrity Reconciliation  
**Target Environment:** Controlled Single-Tenant Beta (Dedicated Workstation / Private Appliance)  

---

## 1. System Prerequisites & Runtime Specifications

Before installing ShipProof, verify that the host machine satisfies the following hardware and software specifications.

### Hardware Specifications
- **Architecture:** Apple Silicon (ARM64) or x86_64 Linux.
- **Memory (RAM):** 8 GB minimum (16 GB recommended for concurrent browser verification runs).
- **Storage:** 10 GB available SSD space on a local POSIX filesystem (APFS or ext4).

### Software Dependencies & Tested Versions
- **Python Runtime:** Actively validated on Python 3.14.5. (Python 3.11, 3.12, and 3.13 are specification targets based on package constraints, but were not actively benchmarked in this validation session).
- **Node.js Runtime:** Actively validated on Node.js v20.20.2 LTS with `npm` 10.8.2.
- **Frontend Framework:** Next.js 16.4.6 (Turbopack).
- **Kane CLI Tooling:** Binary v0.10.4 located at `/opt/homebrew/bin/kane-cli` (or in system `$PATH`).
- **Browser Automation:** Chromium / Playwright binaries managed by Kane CLI.
- **IDE Agent Tooling:** Google Antigravity CLI (`agy`) located at `~/.gemini/bin/agy` (or in system `$PATH`).

---

## 2. Installation Procedure

### Step 2.1 — Backend Virtual Environment & Dependencies
From the repository root:

```bash
# 1. Create a dedicated Python virtual environment
python3 -m venv backend/.venv

# 2. Activate the virtual environment
source backend/.venv/bin/activate

# 3. Upgrade core packaging tools
pip install --upgrade pip setuptools wheel

# 4. Install backend dependencies
pip install -r backend/requirements.txt
```

### Step 2.2 — Frontend Dependencies & Production Compilation
From the `frontend/` directory:

```bash
cd frontend

# 1. Install production and build dependencies
npm ci

# 2. Build the Next.js production bundle
npm run build
```

---

## 3. Configuration & Credential Architecture

### 3.1 The Three Independent Secret Values
ShipProof defines exactly **three independent secret values**. A fourth environment variable name exists, but it shares an identical value with the backend master key:

| Secret / Config Name | Environment & Process Scope | Secret Independence | Purpose |
|:---|:---|:---:|:---|
| **`SHIPPROOF_API_KEY`** | FastAPI Backend (`.env`) | **Independent Secret 1** | Master bearer token securing backend REST API endpoints (`Authorization: Bearer <token>`). |
| **`SHIPPROOF_BACKEND_API_KEY`** | Next.js BFF (`frontend/.env.local`) | *Matches Secret 1* | The environment-variable name used by the Next.js BFF proxy. **Its value must match `SHIPPROOF_API_KEY`**. It is not an independent secret. |
| **`SHIPPROOF_BETA_KEY`** | Next.js Frontend (`frontend/.env.local`) | **Independent Secret 2** | Operator access credential entered into the browser login form (`/login`). **Must remain completely independent from the backend master key**. |
| **`SESSION_SECRET`** | Next.js BFF (`frontend/.env.local`) | **Independent Secret 3** | Cryptographic HMAC-SHA256 key used by Next.js to sign `shipproof_session` browser cookies. **Must remain completely independent**. |

### 3.2 Generating Cryptographic Secrets
Generate independent 256-bit (32 bytes = 64 hexadecimal characters) and 128-bit (16 bytes = 32 hexadecimal characters) secrets using Python's standard `secrets` module:

```bash
# 1. Generate Master Backend API Key (32 bytes = 256 bits = 64 hex characters):
python3 -c "import secrets; print('sp_master_' + secrets.token_hex(32))"

# 2. Generate Operator Beta Access Key (16 bytes = 128 bits = 32 hex characters):
python3 -c "import secrets; print('sp_beta_' + secrets.token_hex(16))"

# 3. Generate Next.js Session Cookie Secret (32 bytes = 256 bits = 64 hex characters):
python3 -c "import secrets; print('sp_sess_' + secrets.token_hex(32))"
```

> **Credential Separation Rule:**  
> Never reuse `SHIPPROOF_BETA_KEY` or `SESSION_SECRET` as the backend `SHIPPROOF_API_KEY`. If an operator login passphrase is compromised, having separate keys ensures the master backend API remains protected.

### 3.3 Environment File Separation & Loading Behavior
FastAPI and Next.js execute in separate processes and load configuration independently:
- **FastAPI Backend:** When started from the workspace root, `backend/app/core/config.py` explicitly loads `.env` from the repository root (`/Users/pratham/Projects/ShipProof/.env`).
- **Next.js Frontend:** When started from `frontend/`, Next.js automatically loads `frontend/.env.local` using its built-in environment-variable cascade. Next.js does **not** traverse parent directories to read the root `.env`.

> **No Symlink Rule:**  
> Do not create a symbolic link between the two environment files (e.g. do not run `ln -s ../.env frontend/.env.local`). Symlinking merges the namespaces, needlessly exposes backend-only internal variables to the frontend runtime, and obscures which variables belong to each process.

#### 1. Backend Environment File (`.env` in workspace root)
Create `/Users/pratham/Projects/ShipProof/.env`:
```bash
# Deployment & Security Mode
# Supported options: "development", "trusted_single_tenant", "production"
DEPLOYMENT_MODE=trusted_single_tenant

# Master API Secret Key (Independent Secret 1 — 32 bytes hex)
SHIPPROOF_API_KEY=<REPLACE_WITH_GENERATED_MASTER_KEY_32_BYTES_HEX>

# Network Binding & Target Allowances
HOST=127.0.0.1
PORT=8000
ALLOW_LOCAL_TARGETS=true

# Tooling Executable Paths
KANE_CLI_PATH=/opt/homebrew/bin/kane-cli
KANE_DEFAULT_TIMEOUT=120
AGY_CLI_PATH=/Users/pratham/.gemini/bin/agy

# Optional Forward Egress Proxy (Recommended when verifying external targets)
# KANE_EGRESS_PROXY=http://127.0.0.1:3128
```

#### 2. Frontend Environment File (`frontend/.env.local`)
Create `/Users/pratham/Projects/ShipProof/frontend/.env.local`:
```bash
# Upstream Master API Key (MUST match SHIPPROOF_API_KEY from backend .env)
SHIPPROOF_BACKEND_API_KEY=<REPLACE_WITH_EXACT_SAME_VALUE_AS_SHIPPROOF_API_KEY>

# Operator Beta Access Key (Independent Secret 2 — entered at /login)
SHIPPROOF_BETA_KEY=<REPLACE_WITH_GENERATED_BETA_KEY_16_BYTES_HEX>

# Session Cookie Signing Secret (Independent Secret 3 — 32 bytes hex)
SESSION_SECRET=<REPLACE_WITH_GENERATED_SESSION_KEY_32_BYTES_HEX>

# Backend URL for server-side proxy rewrites
INTERNAL_BACKEND_URL=http://127.0.0.1:8000
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
```

> **Client Bundle Safety Rule:**  
> Never prefix secrets with `NEXT_PUBLIC_`. Variables prefixed with `NEXT_PUBLIC_` are bundled into client-side JavaScript by Next.js and exposed directly to browser inspection.

---

## 4. Kane CLI Tooling & Authentication Reality

Kane CLI requires an active, authenticated user session to orchestrate real browser verification runs. Operators must clearly distinguish between four distinct operational states:

1. **CLI Binary Installed:** `/opt/homebrew/bin/kane-cli --version` confirms that the executable exists on disk (verified v0.10.4).
2. **Login Command Supported:** `/opt/homebrew/bin/kane-cli login --help` confirms that the interactive login command is supported by the binary.
3. **OAuth Authentication Status:** Active authentication is currently **unverified / expired** on this workstation. Running `/opt/homebrew/bin/kane-cli whoami` exits with code 1 (`OAuth token refresh failed — run 'kane-cli login'`). Successful authentication cannot be claimed until an operator performs the interactive login.
4. **Browser Execution Readiness:** Verification runs against real web targets will exit with code 2 and transition to `status="error"` until the operator completes interactive browser login.

### Performing Interactive OAuth Authentication
To authenticate on a workstation with desktop browser access:
```bash
/opt/homebrew/bin/kane-cli login
```
This opens the system browser to complete the interactive OAuth exchange. Once completed, verify the session:
```bash
/opt/homebrew/bin/kane-cli whoami
```
Expected output once authenticated:
```
✔ Authenticated as <operator_identity>
Profile: default
Environment: prod
```

---

## 5. Starting Application Services with Explicit Loopback Binding

ShipProof consists of two independent services that must be bound strictly to the local loopback interface (`127.0.0.1`).

### Step 5.1 — Start FastAPI Backend (Loopback Bound)
```bash
# Terminal 1 (Repository root):
source backend/.venv/bin/activate
PYTHONPATH=. uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

On startup, the backend automatically:
1. Enforces POSIX `0700` (`rwx------`) permissions on `backend/data`, `backend/data/evidence`, and `backend/data/backups`.
2. Initializes SQLite database tables and foreign keys.
3. Recovers any active runs interrupted by a prior restart to truthful terminal states (`incomplete`).

### Step 5.2 — Start Next.js Frontend (Explicit Loopback Binding)
> **Crucial Loopback Security Notice:**  
> By default, `next start` binds to `0.0.0.0:3000`, exposing the frontend to all local network interfaces. In the controlled single-tenant beta, you **must explicitly bind to loopback (`127.0.0.1`)** using the `-H` flag:

```bash
# Terminal 2 (From frontend/ directory):
cd frontend
PORT=3000 npx next start -H 127.0.0.1 -p 3000
```

Or equivalently via `npm start`:
```bash
cd frontend
PORT=3000 npm start -- -H 127.0.0.1 -p 3000
```

### Step 5.3 — Verifying Actually Observed Bound Listeners
Do not assume services are bound strictly to loopback merely because flags were passed. Verify the active socket bindings:
```bash
# Verify backend is bound strictly to 127.0.0.1:8000 (not *:8000):
lsof -n -iTCP:8000 -sTCP:LISTEN

# Verify frontend is bound strictly to 127.0.0.1:3000 (not *:3000):
lsof -n -iTCP:3000 -sTCP:LISTEN
```

---

## 6. Health & Readiness Verification

### 6.1 Process Liveness & Dependency Health Check
Verify backend process uptime, database connectivity, and local tooling discovery:
```bash
curl -s http://127.0.0.1:8000/api/health | jq .
```
Expected output:
```json
{
  "status": "ok",
  "app": "ShipProof",
  "version": "0.1.0",
  "database": "connected",
  "kane_cli_installed": true,
  "agy_cli_installed": true,
  "timestamp": "2026-11-16T12:00:00.000000Z"
}
```

> **Liveness vs Readiness Distinction:**  
> The `/api/health` endpoint verifies only that the FastAPI process is alive, SQLite is responsive, and local CLI binaries exist on disk. It does **not** verify whether Kane's OAuth token is valid or expired. True execution readiness requires verifying `kane-cli whoami` and executing an initial verification run.

### 6.2 Frontend BFF Session Check
Verify that the Next.js BFF proxy is operational and enforcing authentication:
```bash
curl -s http://127.0.0.1:3000/api/auth/session | jq .
```
Expected output (pre-login):
```json
{
  "authenticated": false,
  "mode": "trusted_single_tenant",
  "user": null,
  "requiresAuth": true
}
```

### 6.3 Operator Access & Login Workflow
1. Open your web browser and navigate to `http://127.0.0.1:3000`.
2. Next.js Edge Middleware intercepts the unauthenticated session and redirects to `/login?from=/`.
3. Enter the configured `SHIPPROOF_BETA_KEY` into the access key field.
4. On successful authentication, the BFF establishes an HTTP-only cookie (`shipproof_session`) and redirects to the ShipProof Verification Dashboard.

---

## 7. Targeted Process Management

Never use broad `pkill -f` commands or routine `kill -9`. Follow targeted process management:

### Step 7.1 — Identify Exact Service PIDs by Port
```bash
# Identify Backend PID:
lsof -n -iTCP:8000 -sTCP:LISTEN -t

# Identify Frontend PID:
lsof -n -iTCP:3000 -sTCP:LISTEN -t
```

### Step 7.2 — Verify Process Ownership and Command Line
```bash
ps -o pid,user,command -p <PID>
```
Verify that the PID belongs to your user account and matches the expected ShipProof command before proceeding.

### Step 7.3 — Request Graceful Termination (`SIGTERM`)
```bash
kill -TERM <PID>
```

### Step 7.4 — Wait Loop & Conditional Escalation
Wait up to 15 seconds for clean termination:
```bash
for i in {1..15}; do kill -0 <PID> 2>/dev/null || break; sleep 1; done
```
Escalate to `kill -KILL <PID>` (`kill -9`) **only** if the process remains alive and unresponsive after the 15-second graceful shutdown window.

---

## 8. Troubleshooting Common Operational Errors

| Symptom / Error | Root Cause | Safe Resolution |
|:---|:---|:---|
| `[Errno 48] Address already in use` | A stale process is holding port 8000 or 3000 | Run `lsof -n -iTCP:<PORT> -sTCP:LISTEN -t` to find the exact PID, verify identity, and terminate via `kill -TERM <PID>`. |
| `Token refresh failed. Run: kane-cli login` | Kane CLI OAuth session has expired | Execute `/opt/homebrew/bin/kane-cli login` in a desktop terminal and complete browser OAuth. |
| `HTTP 401 Unauthorized: missing ShipProof API token` | Next.js cannot read `SHIPPROOF_BACKEND_API_KEY` | Ensure `frontend/.env.local` exists and contains `SHIPPROOF_BACKEND_API_KEY` matching the backend `.env`. |
| `HTTP 403 Forbidden: Cross-site request forgery protection` | Request contains mismatched `Origin` or `Sec-Fetch-Site: cross-site` | Access the application directly via `http://127.0.0.1:3000` using standard same-origin browser navigation. |
| `RuntimeError: Startup security violation: Failed to enforce secure 0700 permissions` | Storage path resides on a non-POSIX filesystem | Ensure `backend/data` is located on a local POSIX filesystem (APFS or ext4) owned by the executing user. |
| `FileNotFoundError: kane-cli executable not found` | Kane CLI is not installed or path is misconfigured | Verify installation via `which kane-cli` or set `KANE_CLI_PATH=/path/to/kane-cli` in `.env`. |
