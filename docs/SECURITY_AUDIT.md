# ShipProof — Adversarial Security Audit (Milestone 4.3)

**Audit Date:** November 16, 2026  
**Auditor:** Antigravity IDE Autonomous Engineering Agent  
**Target Codebase:** ShipProof v0.1.0 (`/Users/pratham/Projects/ShipProof`)  
**Scope:** URL & SSRF Security, Repair State Authorization, Evidence Sandbox Containment, and Credential Sanitization  

---

## 1. Executive Summary & Security Boundary Reality

ShipProof is an autonomous AI software verification and repair system designed for **local developer workstations and trusted CI/CD environments**. 

### **Critical Trust Boundary Definition:**
- **Current Authentication State:** The API endpoints (`/api/runs`, `/api/repairs`, `/api/repairs/{id}/approve`, etc.) **do not implement user authentication, RBAC, or session-based identity verification**. Any client that can establish a TCP connection to the FastAPI port (default `127.0.0.1:8000`) can submit verification runs and approve repairs.
- **Approval Gate Reality:** The repair approval mechanism functions as a **state-machine integrity gate** (ensuring changes are staged, workspace is modified, and the repair is in `AWAITING_APPROVAL`), but **not** as a cryptographic or authenticated signature of a human identity.
- **Production Public Egress Boundary:** To prevent abuse in hosted environments, ShipProof implements strict URL scheme whitelisting, cloud metadata blacklisting, and production-mode private IP blocking.

---

## 2. Findings Matrix

| Identifier | Category | Target / Component | Adversarial Condition | Classification | Evidence & Test Location |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **SEC-01** | SSRF | URL Validator & API | Cloud metadata IP `169.254.169.254` | **PASS** | `test_ssrf_blocks_cloud_metadata_endpoints` in `test_adversarial_security.py`. Returns HTTP 422. |
| **SEC-02** | SSRF | URL Validator & API | Cloud metadata hostname `metadata.google.internal` | **PASS** | `test_ssrf_blocks_cloud_metadata_endpoints`. Returns HTTP 422. |
| **SEC-03** | Protocol Smuggling | URL Validator & API | Non-HTTP schemes (`file://`, `gopher://`, `javascript:`, `ftp://`) | **PASS** | `test_ssrf_blocks_dangerous_schemes`. Returns HTTP 422. |
| **SEC-04** | Input Validation | URL Validator & API | Out-of-bounds ports (`:99999`, `:-5`) and malformed URL syntax | **PASS** | `test_ssrf_blocks_malformed_urls_and_ports`. Returns HTTP 422. |
| **SEC-05** | SSRF | URL Validator | Production mode private IPv4/IPv6 blocking (`10.0.0.0/8`, `192.168.0.0/16`, `127.0.0.0/8`) | **PASS** | `test_ssrf_production_mode_restrictions`. Evaluates `ALLOW_LOCAL_TARGETS=False`. |
| **SEC-06** | Dev Compatibility | URL Validator | Local development targets (`http://127.0.0.1:3005`, `http://localhost:3000`) | **PASS** | `test_ssrf_development_mode_permits_sample_store`. Sample Store demo remains 100% operational. |
| **SEC-07** | SSRF | Browser Navigation | Redirects from public URLs to private/internal endpoints | **PARTIAL** | Kane CLI launches Chromium; Chromium enforces browser-level network sandbox, but backend does not intercept intermediate HTTP 302 redirects. |
| **SEC-08** | SSRF | DNS Resolution | DNS Rebinding (Time-of-Check to Time-of-Use) | **PARTIAL** | IP is checked during API validation; Kane CLI resolves DNS independently during Playwright execution. Mitigation requires DNS pinning proxy. |
| **SEC-09** | Concurrency | Repair Approval | Simultaneous race-condition approval requests for single repair | **PASS** | `test_concurrent_approvals_prevent_duplicate_retests` in `test_operational_reliability.py`. Atomic DB update rejects duplicate with HTTP 400/409. |
| **SEC-10** | Integrity | Repair Approval | Approval attempt when workspace is clean (no detected modifications) | **PASS** | `test_approval_without_modifications_rejected`. Returns HTTP 400. |
| **SEC-11** | Integrity | Repair Approval | Repeated approval attempt after repair is already `VERIFIED` | **PASS** | `test_approval_after_verified_rejected`. Returns HTTP 400. |
| **SEC-12** | Concurrency | Repair Creation | Concurrent duplicate repair jobs against single parent run | **PASS** | `test_concurrent_repairs_for_same_run_rejected`. Returns HTTP 400. |
| **SEC-13** | Path Traversal | Artifact Serving | Directory traversal via `..` in `/api/runs/{id}/evidence/files/` | **PASS** | `test_evidence_file_path_traversal_defense`. Returns HTTP 403. |
| **SEC-14** | Path Traversal | Artifact Serving | Prefix collision traversal (`run1-evil` vs `run1`) | **PASS** | `test_evidence_file_path_traversal_defense`. Enforces `evidence_dir in target_file.parents`. Returns HTTP 403. |
| **SEC-15** | Archive Safety | Evidence Extraction | Malicious ZIP entries containing absolute paths or `..` | **PASS** | `test_zip_path_traversal_prevention` in `test_evidence_service.py`. Raises `PathTraversalError`. |
| **SEC-16** | Denial of Service | Evidence Extraction | ZIP bomb attack (uncompressed size > 100MB or > 1000 files) | **PASS** | `test_archive_size_limit_enforcement` in `test_evidence_service.py`. Raises `ArchiveSizeLimitExceededError`. |
| **SEC-17** | Data Leakage | HAR Log Sanitizer | Sensitive credentials in HTTP headers (`Authorization`, `Cookie`, `Set-Cookie`) | **PASS** | `test_har_credential_redaction_preserves_debug_context`. Redacted to `[REDACTED]` on disk. |
| **SEC-18** | Debug Context | HAR Log Sanitizer | Non-sensitive header retention (`Content-Type`, `User-Agent`, status codes) | **PASS** | `test_har_credential_redaction_preserves_debug_context`. Retained intact for developer triage. |
| **SEC-19** | Access Control | API Endpoints | Multi-user authentication & role-based access control (RBAC) | **NOT TESTED** | Not implemented by design. ShipProof is currently a single-tenant local engineering tool. |

---

## 3. Deep-Dive Security Analysis

### A. SSRF & URL Validation Architecture
ShipProof introduces a multi-tier URL validation pipeline in `backend/app/core/url_validator.py`:
1. **Scheme Whitelist:** Strictly enforces `http://` and `https://`. Protocol smuggling vectors (`file://`, `gopher://`, `javascript:`, `ftp://`, `data:`) are rejected with HTTP 422 before subprocess creation.
2. **Universal Cloud Metadata Blacklist:** Any target hostname or IP matching `169.254.169.254`, `metadata.google.internal`, `metadata.goog`, `100.100.100.200`, or link-local IPv4/IPv6 ranges (`169.254.0.0/16`, `fe80::/10`) is blocked unconditionally across all environments.
3. **Environment Segregation:**
   - **Development (`ALLOW_LOCAL_TARGETS=True`):** Allows loopback (`127.0.0.1`, `localhost`) and local RFC-1918 subnets (`192.168.x.x`) to permit end-to-end verification of local development applications like the Sample Store (`http://127.0.0.1:3005`).
   - **Production (`ALLOW_LOCAL_TARGETS=False`):** Resolves target hostnames via DNS and blocks any target resolving to loopback (`127.0.0.0/8`, `::1`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), or internal hostnames.

### B. Repair Authorization & Atomicity
In Milestone 4.3, state-transition protections were hardened to eliminate race conditions:
1. **Atomic Status Check-and-Set:** `POST /api/repairs/{id}/approve` executes a single atomic SQL statement:
   ```sql
   UPDATE repair_records
   SET status = 'APPLYING', updated_at = :now
   WHERE id = :repair_id AND status IN ('AWAITING_APPROVAL', 'AGENT_RESPONSE_RECEIVED', 'PROPOSED', 'AWAITING_AGENT');
   ```
   If two requests arrive concurrently, exactly one updates the row (`rowcount == 1`). The duplicate receives `rowcount == 0` and is rejected with HTTP 400.
2. **Workspace Modification Prerequisite:** Approval requires that either a non-empty patch diff was recorded or uncommitted changes exist in the workspace. An unmodified clean workspace cannot trigger a retest.
3. **Parent Run Collision Guard:** `create_repair_session` inspects all non-terminal states. A second repair cannot be spawned for a run whose repair is in progress.

### C. Evidence Sandbox Containment
Artifact serving via `GET /api/runs/{id}/evidence/files/{file_path:path}` strictly enforces directory containment using Python's `pathlib.Path`:
```python
target_file = (evidence_dir / file_path).resolve()
if target_file != evidence_dir and evidence_dir not in target_file.parents:
    raise HTTPException(status_code=403, detail="Access denied: path traversal attempt detected")
```
This eliminates both relative traversal (`../../etc/passwd`) and prefix collision vulnerabilities (`/evidence/run1-fake` matching `/evidence/run1`).

### D. Credential Sanitization
During evidence extraction, network HAR files (`*-network.har`) are automatically inspected. Request and response headers containing `Authorization`, `Cookie`, `Set-Cookie`, `x-api-key`, `proxy-authorization`, or `token` are overwritten with `[REDACTED]` on disk before the evidence manifest is returned to the user or agent. Non-sensitive headers (`Content-Type`, `User-Agent`, `status`) are preserved for root-cause diagnosis.

---

## 4. Security Recommendations for Future Multi-Tenant Deployments

1. **Implement Reverse-Proxy DNS Pinning:** To completely eliminate DNS rebinding between time-of-check and Chromium execution in hosted cloud deployments, run an intermediate HTTP forward proxy that resolves and pins egress IP addresses.
2. **Add JWT / OAuth2 Authentication:** When exposing ShipProof over public networks or shared team servers, integrate authentication middleware (e.g., Auth0, OAuth2 bearer tokens) to identify and authorize repair approvals.
3. **Egress Network Policies:** In containerized deployments (Docker/K8s), enforce egress network policies blocking access to `169.254.169.254` at the container network interface (CNI) layer.
