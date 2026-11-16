# ShipProof — Deployment Security Model

**Milestone:** 4.4 Controlled Beta Security Closure  
**Product:** ShipProof — Autonomous AI Software Verification & Repair  
**Target Environment:** Controlled Single-Tenant Beta  
**Status:** Approved for Controlled Deployment  

---

## 1. Overview & Architectural Philosophy

ShipProof orchestrates real browser test execution via the **Kane CLI** and coordinates autonomous code repairs mediated by the **Antigravity IDE Agent**. Because browser execution involves spawning Chromium instances and interacting with target web applications, ShipProof establishes rigorous deployment boundaries separating development, trusted beta, and multi-tenant environments.

ShipProof explicitly rejects "security through obscurity" or unverifiable security claims. This document articulates the concrete security mechanisms, threat model boundaries, and operational assumptions enforced across ShipProof.

---

## 2. Deployment Security Modes

ShipProof introduces three mutually exclusive, explicitly configured deployment modes defined in `backend/app/core/config.py`:

```
+------------------------------------------------------------------------------------+
|                               DEPLOYMENT MODES                                     |
+--------------------------+------------------------------+--------------------------+
|       development        |    trusted_single_tenant     |        production        |
+--------------------------+------------------------------+--------------------------+
| - Local debugging        | - Dedicated customer VM/VPC  | - Multi-tenant cloud     |
| - ALLOW_LOCAL_TARGETS=1  | - ALLOW_LOCAL_TARGETS=0/1    | - ALLOW_LOCAL_TARGETS=0  |
| - Sample Store permitted | - Enforced API Token         | - Enforced API Key (>=16)|
| - Optional API token     | - Strict CORS Whitelist      | - Fail-Closed Startup    |
| - Localhost CORS allowed | - Rate Limiting Active       | - Network Egress Filter  |
+--------------------------+------------------------------+--------------------------+
```

### Mode 1: `development`
* **Purpose:** Local developer workstation debugging and developer evaluation.
* **Network & Target Policy:** `ALLOW_LOCAL_TARGETS=True` by default, permitting verification runs against local development targets like the embedded Sample Store (`http://127.0.0.1:3005`).
* **Authentication:** Optional if `SHIPPROOF_API_KEY` is unset (defaults to `"dev-local-user"` identity). If an API key is provided, authentication is enforced.
* **CORS:** Binds to `http://localhost:3000` and `http://127.0.0.1:3000`.

### Mode 2: `trusted_single_tenant` (Current Milestone Target)
* **Purpose:** Single-organization, private-cloud or on-premises deployment where the platform is dedicated to a trusted engineering team.
* **Authentication:** Mandatory API Key. If `SHIPPROOF_API_KEY` is not explicitly set in the environment, the server auto-generates a cryptographically strong 40-character ephemeral token (`sp_beta_<token_hex>`) and logs it at startup.
* **Rate Limiting:** Active sliding-window rate limiting on all resource-intensive operations (verification run creation, repair generation, approval, cancellation).
* **CORS:** Whitelisted to explicit single-tenant host origins.

### Mode 3: `production`
* **Purpose:** Hardened, isolated deployment.
* **Fail-Closed Guarantees:** The application refuses to start (`model_validator` raises fatal validation error) if:
  1. `SHIPPROOF_API_KEY` is missing or shorter than 16 characters.
  2. `ALLOW_LOCAL_TARGETS=True` is enabled (strictly forbidden in production to prevent private network SSRF).
  3. Wildcard `"*"` is present in `CORS_ORIGINS` or `CORS_ORIGINS` is empty.

---

## 3. Threat Model & Security Boundaries

### 3.1 Trust Boundary Matrix

| Actor / Component | Trust Level | Capabilities / Access |
| :--- | :--- | :--- |
| **ShipProof Operator / User** | Authenticated / Trusted | Can submit test objectives, view evidence, trigger repairs, approve patches. |
| **FastAPI Backend Core** | Trusted Orchestrator | Validates URLs, manages SQLite DB, enforces auth, controls Kane CLI process groups. |
| **Antigravity IDE Agent** | Privileged Local Agent | Inspects workspace code, reviews repair packets, drafts unified diff patches. |
| **Kane CLI Subprocess** | Sandboxed Execution | Runs headless browser to verify web application behavior. |
| **Target Web Application** | Untrusted Remote Server | External code, potentially issuing HTTP redirects, executing untrusted JavaScript. |

---

### 3.2 Browser Egress & SSRF Protection: Honest Technical Reality

#### Target URL Pre-Execution Validation
Every user-supplied `target_url` is evaluated by `backend/app/core/url_validator.py` before any browser process is spawned:
- **Dangerous Schemes Blocked:** Schemes other than `http` or `https` (e.g. `file://`, `gopher://`, `javascript:`, `ftp://`) are rejected with HTTP 422.
- **Cloud Metadata Blocked:** IPv4 link-local (`169.254.169.254`, `169.254.0.0/16`) and internal metadata hostnames (`metadata.google.internal`, `instance-data`) are unconditionally blocked.
- **Private & Loopback IP Defense:** In `production` mode, RFC 1918 private ranges (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`) and loopback (`127.0.0.0/8`, `::1`) are strictly rejected.
- **Port Containment:** Ports outside 0–65535 or restricted system ports are rejected.

#### Browser Redirects & Network Egress Boundary
An honest assessment of the Kane CLI browser environment shows:
1. `kane-cli run` **does not provide CLI flags for upstream proxy configuration** (`--proxy` or `--proxy-server` are not CLI arguments supported by `kane-cli`).
2. Chromium launched by Kane CLI follows HTTP 301/302 redirects in-page.
3. Therefore, if a target web server responds to an initial navigation with a redirect to `http://169.254.169.254/latest/meta-data/` or an internal IP, Chromium will follow that redirect unless egress filtering is enforced at the network or host OS level.
4. **Boundary Conclusion:** Application-level validation is necessary but insufficient for untrusted public clouds. For multi-tenant SaaS environments, host firewall rules (e.g. `iptables`, `nftables`), Kubernetes CNI egress policies (e.g. Cilium / Calico), or transparent egress proxies are **strictly required**. For the **Controlled Single-Tenant Beta**, ShipProof operates within the customer's trusted perimeter.

---

### 3.3 Subprocess Tree Cleanup & Process Group Containment

To prevent "zombie" or orphaned Chromium and Playwright instances from accumulating during timeouts or cancellations:
- **Process Group Isolation:** Kane CLI subprocesses are spawned via `asyncio.create_subprocess_exec` with `start_new_session=True`. This creates a dedicated POSIX process group where `pgid == proc.pid`.
- **Hierarchical Tree Termination:** When a run completes, times out, or is cancelled:
  1. `terminate_process_tree` issues `os.killpg(pgid, signal.SIGTERM)` to the entire process group.
  2. A 1.5-second grace period allows Node, Playwright, and Chromium to exit cleanly.
  3. If any process remains alive after the grace period, `os.killpg(pgid, signal.SIGKILL)` is dispatched.
- **Server Shutdown Hook:** FastAPI's `lifespan` context registers `await runner_service.terminate_all_processes()` upon shutdown, guaranteeing zero orphan processes upon server restarts.

---

### 3.4 Authentication & Sliding-Window Rate Limiting

- **Multi-Vector Token Extraction:** The auth module (`backend/app/core/auth.py`) extracts tokens from:
  1. `Authorization: Bearer <token>`
  2. `X-ShipProof-Key: <token>`
  3. Query parameter `?token=<token>` (required for browser Server-Sent Events `EventSource` and direct `<img>` evidence rendering).
- **Constant-Time Verification:** Uses `secrets.compare_digest` to prevent timing attacks.
- **Sliding-Window Rate Limiting:** Enforces `RATE_LIMIT_PER_MINUTE` (default: 60 rpm per client IP) on mutating operations:
  - `POST /api/runs` (launch verification)
  - `POST /api/runs/{id}/cancel` (cancel verification)
  - `POST /api/repairs` (create repair job)
  - `POST /api/repairs/{id}/approve` (apply patch and launch retest)
  - `POST /api/repairs/{id}/cancel` (cancel repair)
  - `POST /api/system/backup` (hot online backup)

---

### 3.5 Storage & Disaster Recovery: SQLite Hot Online Backup

- **Hot Online Backups:** `backend/app/services/backup_service.py` utilizes the official SQLite `sqlite3.backup` API. Because the database operates with `PRAGMA journal_mode=WAL;`, hot backups can be created during active read and write transactions without locking or corruption.
- **Integrity Checks:** Every backup and restored database is immediately verified using `PRAGMA integrity_check;`.
- **Evidence Cross-Referencing:** Restored databases are cross-verified against disk storage to ensure all evidence pack files (`.evidence` archives, `.png` screenshots, `.har` traces) referenced in `verification_runs` exist.

---

### 3.6 Durable SSE Stream Recovery

- **Monotonic Event Sequences:** Each event for a verification run is assigned an integer `event_seq` (1, 2, 3...) that is persisted in `VerificationEventEntity`.
- **`Last-Event-ID` Support:** When a client reconnects, it transmits `Last-Event-ID: <id>` (or `?last_event_id=<id>`). ShipProof queries the database and replays only events where `event_seq > last_id`.
- **Deduplication:** Live events arriving from the subscriber queue with `event_seq <= last_id` are suppressed to prevent duplicate event rendering.
- **Heartbeat Comments:** Every 15 seconds of inactivity, `: heartbeat\n\n` comments keep HTTP connections alive across NATs and load balancers.
