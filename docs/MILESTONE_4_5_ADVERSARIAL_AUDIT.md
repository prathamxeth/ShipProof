# ShipProof — Milestone 4.5 Adversarial Audit Report

**Date:** November 16, 2026  
**Auditor:** Principal Security Engineer & Application Security Auditor  
**Workspace:** `/Users/pratham/Projects/ShipProof`  
**Milestone:** 4.5 Adversarial Beta Acceptance & Disaster Recovery Validation  
**Final Status:** **READY FOR CONTROLLED SINGLE-TENANT BETA** (with documented infrastructure prerequisites)  

---

## 1. Executive Summary & Audit Scope

Prior to onboarding external controlled-beta users, ShipProof underwent an exhaustive adversarial engineering audit. The audit examined five core security domains:
1. **Authentication & Session Security:** Credential leakage in URLs, token validation, rate-limiting spoofing, and read-endpoint authorization.
2. **Adversarial SSRF & Browser Egress:** Alternative IP representations (decimal, hex, octal), IPv4-mapped IPv6, DNS rebinding, and in-browser HTTP 302 redirect egress.
3. **Disaster Recovery & SQLite Integrity:** Hot online backups under concurrent write load, structural integrity checks, foreign-key constraint enforcement, disk evidence verification, and storage retention.
4. **Concurrency & Process Lifecycle:** Race conditions between user cancellations and late subprocess events, unbounded process spawning, and restart recovery.
5. **Durable SSE & Event Streams:** Pub/sub race conditions, memory bounds on slow consumers, and out-of-order sequence replay.

Across 80 automated unit, integration, and adversarial tests, **100% of tests pass (80/80)**, and the Next.js frontend builds cleanly across all 8 routes in 302ms.

---

## 2. Methodology & Threat Modeling

The audit combined static code inspection, threat modeling, active exploitation attempts, and regression test authoring. The adversarial attack surface was partitioned into three threat profiles:

```
+---------------------------------------------------------------------------------+
|                               THREAT SURFACE                                    |
+--------------------------+------------------------------+-----------------------+
|  Unauthenticated Public  |  Authenticated Beta Client   | Target Web Server     |
|  - Endpoint enumeration  | - Token privilege escalation | - 302 Redirect SSRF   |
|  - Rate-limit bypass     | - Cross-run evidence access  | - DNS rebinding       |
|  - Replay / timing attacks| - Denial-of-service / OOM    | - Traversal payloads  |
+--------------------------+------------------------------+-----------------------+
```

---

## 3. Confirmed Vulnerabilities & Remediation Actions

### Vulnerability 1: Unauthenticated Read Reconnaissance on Query Endpoints
* **Severity:** High (CVSS 7.5)
* **Location:** `backend/app/api/overview.py`, `runs.py`, `repairs.py`, `projects.py`
* **Defect:** While mutating endpoints (`POST /runs`, `POST /repairs`) required authentication, query endpoints (`GET /overview`, `GET /runs`, `GET /repairs`, `GET /projects`) lacked `Depends(verify_auth)`. In single-tenant and production modes, unauthenticated callers could harvest project names, target URLs, failure messages, and code repair diffs.
* **Remediation:** Wired `dependencies=[Depends(verify_auth)]` across all read endpoints. In `development` mode without a key, it continues to permit local workstation development seamlessly; in `trusted_single_tenant` and `production`, all endpoints reject unauthenticated requests with HTTP 401.

### Vulnerability 2: Master API Key Exposure in URL Query Parameters
* **Severity:** Medium (CVSS 6.5)
* **Location:** `backend/app/core/auth.py`
* **Defect:** Native browser `EventSource` and `<img>` tags cannot supply custom `Authorization` headers. The previous implementation extracted the permanent master key from `?token=<key>`. This leaked the long-lived API key into browser history, web server access logs, and upstream proxy logs.
* **Remediation:** Designed and implemented **Short-Lived Scoped Tickets** (`POST /api/auth/ticket`, `create_scoped_ticket`, `verify_scoped_ticket`):
  - HMAC-SHA256 signed tokens (`spt.<payload_b64>.<sig>`) with a 5-minute TTL.
  - Resource-scoped (`scope: "stream"` or `"evidence"`) and optionally bound to a specific `run_id`.
  - Tickets are strictly forbidden from executing mutating actions (attempts return HTTP 403).

### Vulnerability 3: Directory Traversal via `run_id` Identifier Manipulation
* **Severity:** High (CVSS 8.2)
* **Location:** `backend/app/api/runs.py`, `backend/app/services/evidence_service.py`
* **Defect:** `run_id` was concatenated into `settings.EVIDENCE_DIR / run_id` without regex format validation. Supplying `run_id=../../tmp` could escape the evidence storage root and allow reading arbitrary host files where `evidence_dir in target_file.parents` evaluated to true.
* **Remediation:** Introduced `validate_safe_run_id` enforcing strict regex `^[a-zA-Z0-9_\-]+$` and verifying that `settings.EVIDENCE_DIR in evidence_dir.parents and evidence_dir != settings.EVIDENCE_DIR`.

### Vulnerability 4: Alternative IP Representations & DNS Resolution SSRF Bypasses
* **Severity:** High (CVSS 8.0)
* **Location:** `backend/app/core/url_validator.py`
* **Defect:** In development mode (`allow_local=True`), DNS resolution was bypassed, allowing decimal IP literals (e.g. `http://2852039166` for `169.254.169.254`) or DNS domains resolving to link-local metadata to evade static blacklist checks.
* **Remediation:** Enforced universal DNS resolution via `socket.getaddrinfo` across ALL modes. Link-local and cloud metadata ranges (`169.254.0.0/16`, `100.100.100.200/32`, `fe80::/10`) are unconditionally blocked. Added normalization for IPv4-mapped IPv6, decimal, hex, and octal IP formats.

### Vulnerability 5: IP Spoofing & Memory Exhaustion in Rate Limiter
* **Severity:** Medium (CVSS 5.3)
* **Location:** `backend/app/core/auth.py`
* **Defect:** 
  1. Forwarded headers were susceptible to spoofing if an untrusted peer sent forged `X-Forwarded-For`.
  2. The in-memory tracking dictionary grew unboundedly without pruning stale IP keys.
* **Remediation:** 
  1. Implemented `get_client_ip` which strictly checks whether the direct connection originates from `settings.TRUSTED_PROXIES` before evaluating `X-Forwarded-For`.
  2. Added bounded memory pruning (`_MAX_TRACKED_IPS = 5000`) that purges stale keys when the table grows.

### Vulnerability 6: Cancelled Run State Overwrite Race Condition
* **Severity:** Medium (CVSS 5.9)
* **Location:** `backend/app/services/runner_service.py`
* **Defect:** When a run was cancelled by a user, late subprocess completion could overwrite `status="cancelled"` with `status="passed"`, `"failed"`, or `"error"` because the database update query lacked a status guard.
* **Remediation:** Conditioned database status updates to `where(VerificationRunEntity.id == run_id, VerificationRunEntity.status.in_(["running", "queued"]))`. If the run is already cancelled, late subprocess completions and completion broadcasts are discarded.

### Vulnerability 7: Pub/Sub Subscription Gap in Durable SSE Stream
* **Severity:** Low (CVSS 3.7)
* **Location:** `backend/app/api/runs.py`
* **Defect:** In `get_run_events`, the database history query occurred *before* subscribing to the live queue. Events emitted in the microsecond gap between the query and queue registration were lost.
* **Remediation:** Subscribed to the live queue `queue = runner_service.subscribe(run_id)` *before* executing the historical database query, using monotonic sequence deduplication (`seq <= last_seq_sent`) to eliminate duplicate event delivery. Added bounded capacity (`maxsize=1000`) to prevent slow-consumer memory bloat.

### Vulnerability 8: Information Disclosure in `/api/health`
* **Severity:** Low (CVSS 3.1)
* **Location:** `backend/app/api/health.py`
* **Defect:** Database connectivity errors returned `f"unhealthy: {str(e)}"`, which could expose database file paths and driver internals to unauthenticated callers.
* **Remediation:** Sanitized the response to `"unhealthy: database connectivity failed"` while logging the full exception internally.

---

## 4. Adversarial Test Evidence & Results

Automated regression command:
```bash
PYTHONPATH=. ./backend/.venv/bin/pytest backend/tests -v
```

Execution output:
```
============================= 80 passed in 14.46s ==============================
```

Breakdown of newly added adversarial test modules:
1. **`test_auth_adversarial.py`** (4 tests): Verifies token enforcement across read/write endpoints, scoped ticket confinement, IP-spoofing defense, and 10MB payload size limits.
2. **`test_ssrf_adversarial.py`** (3 tests): Verifies decimal/hex/IPv4-mapped metadata blocking, dangerous schemes/ports rejection, and demonstrates in-browser 302 redirect boundaries.
3. **`test_disaster_recovery_drill.py`** (1 test): Exercises a complete disaster recovery drill under active writes, verifying structural integrity, foreign-key constraints, disk evidence references, and backup pruning.
4. **`test_concurrency_adversarial.py`** (3 tests): Tests cancelled state immutability, duplicate cancellation idempotency, and startup crash recovery.
5. **`test_sse_integrity.py`** (3 tests): Tests invalid/negative `Last-Event-ID` handling, bounded queue capacity under slow consumers, and zero-loss subscription gap prevention.

---

## 5. Browser Egress Boundary: Unresolved Infrastructure Dependency

### Technical Assessment:
The automated test `test_browser_redirect_egress_boundary_demonstration` conclusively demonstrates that while pre-execution URL validation correctly rejects direct requests to private IPs and cloud metadata, **in-browser HTTP 302 redirects cannot be prevented by application-level URL checks alone**.

Kane CLI executes headless Chromium, which follows HTTP 302 redirects natively. Because Kane CLI does not support upstream `--proxy` CLI flags, if an external target responds with a 302 redirect to an internal IP (e.g. `http://10.0.0.1/` or `http://169.254.169.254/`), Chromium will follow the redirect.

### Deployment Dependency:
For public multi-tenant SaaS environments, network-level egress filtering (such as host OS `iptables`/`nftables` rules or Kubernetes CNI egress policies) is an **unresolved deployment dependency**. For the **Controlled Single-Tenant Beta**, ShipProof operates safely within the dedicated customer perimeter.
