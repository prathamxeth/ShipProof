# ShipProof — Autonomous Code Repair Engine & Closed Loop
## Architecture, Protocols, Git Safety, and Demonstration Proof

---

## 1. Overview & Closed-Loop Architecture

ShipProof's core mission is: **"Your AI writes the code. ShipProof proves it works."**

Milestone 3 transforms ShipProof from a verification-only observation backend into an **autonomous closed-loop repair and verification system**. When browser tests fail under real Kane CLI execution, ShipProof automatically constructs rich diagnostic packets, exposes repair jobs to the Antigravity engineering agent, tracks surgical Git diffs within strict workspace boundaries, and reruns the original test scenario to prove the repair works.

```
+---------------------------------------------------------------------------------------+
|                                SHIPPROOF CLOSED LOOP                                   |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
                        +-------------------------------------+
                        | 1. Kane CLI Browser Verification    |
                        |    (Real Chrome / LambdaTest Engine)|
                        +-------------------------------------+
                                           |
                         Terminal Event: run_end (FAILED)
                                           |
                                           v
                        +-------------------------------------+
                        | 2. Evidence & Failure Extraction    |
                        |    - failure.yaml triage & RCA      |
                        |    - Step screenshots (annotated)   |
                        |    - Console & Network error logs   |
                        +-------------------------------------+
                                           |
                                           v
                        +-------------------------------------+
                        | 3. Repair Packet Engine             |
                        |    (repair_packet_service.py)       |
                        |    - Candidate source file scoping  |
                        |    - Secret & credential redaction  |
                        |    - Publishes job to .shipproof/   |
                        +-------------------------------------+
                                           |
                                           v
                        +-------------------------------------+
                        | 4. Antigravity Agent Bridge         |
                        |    (agent_service.py)               |
                        |    - IDE-mediated repair workflow   |
                        |    - Formulates diagnosis & files   |
                        +-------------------------------------+
                                           |
                                           v
                        +-------------------------------------+
                        | 5. Surgical Code Patch & Git Audit  |
                        |    (git_service.py)                 |
                        |    - Strict boundary enforcement    |
                        |    - Working tree diff capture      |
                        +-------------------------------------+
                                           |
                              Explicit User Review /
                              ShipProof Studio Approval
                                           |
                                           v
                        +-------------------------------------+
                        | 6. Kane CLI Retest Execution        |
                        |    (runner_service.py)              |
                        |    - Exact original test scenario   |
                        |    - Fresh evidence archive         |
                        +-------------------------------------+
                                           |
                         Terminal Event: run_end (PASSED)
                                           |
                                           v
                        +-------------------------------------+
                        | 7. Authoritative Verdict: VERIFIED  |
                        |    - RepairRecord marked VERIFIED   |
                        |    - Parent run marked Repaired     |
                        +-------------------------------------+
```

---

## 2. Repair Packet Specification

The **Repair Packet** (`backend/app/models/schemas.py:RepairPacketModel`) encapsulates everything an AI engineer needs to diagnose and fix a browser-level bug without leaking secrets or polluting agent context.

### Fields and Schema Contract

| Field | Type | Description |
| :--- | :--- | :--- |
| `run_id` | `UUID` | ShipProof verification run identifier |
| `kane_session_id` | `String` | Real Kane CLI session directory path |
| `target_url` | `String` | Application URL tested by Kane |
| `objective` | `String` | Original natural-language test objective |
| `failed_step` | `Integer` | Exact ordinal step index where verification broke |
| `failure_message` | `String` | Kane's terminal failure summary and reasoning |
| `failure_yaml` | `Dict` | Deep Root Cause Analysis (RCA) extracted from evidence archive |
| `relevant_screenshots` | `List[String]` | Static file paths to screenshots taken leading up to the failure |
| `console_errors` | `List[Dict]` | Sanitized browser console error NDJSON entries |
| `network_errors` | `List[Dict]` | Sanitized failing HTTP requests (4xx / 5xx) from network HAR |
| `project_dir` | `String` | Target source code directory |
| `relevant_files` | `List[String]` | Scoped candidate source code files likely containing the bug |
| `git_commit_before` | `String` | Repository commit SHA before any repair code is applied |
| `execution_mode` | `String` | Execution mode: `ide_mediated` (default) vs `programmatic` |
| `created_at` | `DateTime` | Timestamp of packet generation |

### Security & Context Safeguards
- **Strict Credential Redaction:** Passwords, tokens, Bearer headers, and secrets in HAR network logs or console strings are sanitized before packet generation.
- **Project Boundary Scoping:** Candidate files are strictly limited to the target project directory (e.g. `demo_targets/sample_store/`), preventing the agent from modifying parent tooling or unrelated projects.
- **JSON Serialization Safety:** Nested YAML timestamps and datetimes are cleanly normalized to ISO-8601 strings.

---

## 3. Antigravity Agent Integration Bridge & Execution Modes

### CLI and IDE Capability Assessment
The bridge inspected the real environment capabilities of Antigravity:
- **Executable:** `/Users/pratham/.gemini/bin/agy` (v2.0 preview)
- **Supported Models:** `gemini-3.8-flash-high`, `gemini-3.8-flash-low`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`
- **Headless Non-Interactive Flag:** `agy -p "..." --output-format json`

### Execution Integrity Audit Findings
An exhaustive audit of the `agy` CLI binary revealed:
1. **Interactive OAuth Gate:** Invoking `agy` headlessly outside the active IDE session triggers a blocking OAuth URL challenge:
   ```text
   consumerOAuth: starting OAuth flow
   Authentication required. Please visit the URL to log in:
     https://accounts.google.com/o/oauth2/auth?...
   Waiting for authentication (timeout 60s)...
   ```
2. **Permission Boundary Constraints:** Unattended tool execution in `agy` requires `--dangerously-skip-permissions`. Without it, the CLI halts on terminal stdin prompts before writing to disk. Under ShipProof Rule 8, `--dangerously-skip-permissions` is **strictly prohibited**.
3. **Architectural Realism:** As a result, ShipProof does not claim unattended background agent execution. Instead, ShipProof natively implements the **IDE-Mediated Repair Workflow**.

### IDE-Mediated Repair Workflow
1. **ShipProof Publishes Repair Job:** Structured repair packet and prompt are generated into `.shipproof/repairs/<repair_id>/`:
   - `job.json`: Full repair packet payload and current state.
   - `prompt.md`: Markdown prompt tailored for the Antigravity IDE agent.
2. **Antigravity IDE Agent Investigates:** The active Antigravity IDE agent reads `prompt.md`, investigates candidate files, and applies surgical source code modifications.
3. **Workspace Modification Detection:** ShipProof monitors Git status via `detect_workspace_changes()`. When modifications appear in the target project, the state transitions from `AWAITING_AGENT` to `AGENT_RESPONSE_RECEIVED` and `AWAITING_APPROVAL`.
4. **Explicit User Review:** The user reviews the unified Git diff in ShipProof Repair Studio and approves the change via `POST /api/repairs/{id}/approve`.
5. **Kane CLI Retest Execution:** ShipProof validates workspace boundaries, applies the locked diff, and triggers a real Kane CLI retest to prove the repair works.

---

## 4. Orchestrator State Machine

The repair lifecycle is strictly governed by `RepairOrchestrator` (`backend/app/services/repair_orchestrator.py`):

```
CREATED
   ↓
JOB_PUBLISHED
   ↓
AWAITING_AGENT
   ↓ (Agent applies source edits in workspace)
AGENT_RESPONSE_RECEIVED
   ↓
AWAITING_APPROVAL ──→ (User Cancel) ──→ CANCELLED
   ↓ (Explicit Approval in ShipProof Studio)
APPLYING
   ↓
VALIDATING ─────────→ (Boundary/Syntax Violation) ──→ UNRESOLVED
   ↓
RETESTING (Kane CLI Execution)
   ↓
   ├── Retest Passed (run_end: passed) ──→ VERIFIED (Parent run marked Repaired)
   └── Retest Failed (run_end: failed) ──→ UNRESOLVED (Retry attempt permitted, up to 5)
```

Every state transition records a timestamped `RepairEventEntity` in SQLite and broadcasts real-time Server-Sent Events (SSE) to connected clients.

---

## 5. Git Safety & Diff Capture

`GitService` (`backend/app/services/git_service.py`) provides robust protections:
1. **Workspace Boundary Checking:** `validate_modifications(repo_dir, allowed_subpath)` verifies that all modified and untracked files are strictly within the target project directory. If an agent modifies files outside the project boundary, the repair is rejected with `GitSafetyError`.
2. **Unified Diff Tracking:** Full unified diffs (`git diff HEAD`) are captured before retesting and permanently stored in the `repair_records.patch_diff` database column.
3. **Commit Hash Traceability:** Pre-repair and post-repair commit SHAs (`git_commit_before`, `git_commit_after`) are stored for complete provenance.

---

## 6. Live Closed-Loop Demonstration Walkthrough

A fresh end-to-end verification and repair demonstration was executed on macOS using the included `sample_store` demo application with the explicit IDE-mediated state machine.

### Phase 1: Defect Injection
An intentional defect was enabled in `demo_targets/sample_store/templates/cart.html` and `config.json`:
- The cart checkout button was mutated to `checkout-btn-broken` with `disabled` attribute.
- An error banner `<div id="defect-msg">Error: Checkout button disabled by defect</div>` was rendered.

### Phase 2: Initial Kane Verification Run (Failure Detection)
- **ShipProof Run ID:** `157c47e8-b90b-47e1-979d-38bbd01e9118`
- **Target URL:** `http://127.0.0.1:3005/product/1`
- **Objective:** `Click 'Add to Cart', then in the cart click 'Proceed to Checkout', and verify that 'Secure Checkout' is displayed.`
- **Real Kane Session ID:** `/Users/pratham/.testmuai/kaneai/sessions/5017d3ed-d940-4b08-8f21-47e75dbf859e`
- **Evidence Pack:** `e4578b38-79bf-46e9-9c19-5af88df6a163.evidence`
- **Observed Result:** Kane navigated to `/product/1`, clicked "Add to Cart", navigated to `/cart`, identified the disabled checkout button, and failed at Step 3.
- **Kane Failure Reason:**
  > `"The store accepts the add-to-cart action but leaves checkout unavailable, preventing a customer with an item in the cart from continuing. Fix the cart state after a successful add so that Proceed to Checkout is enabled when the cart contains the added item, then verify it opens Secure Checkout."`
- **Terminal Verdict:** `FAILED` (Exit code: 1, Duration: 46.6s).

### Phase 3: Repair Packet Generation & Job Publication
- **Repair Session ID:** `ac1efe85-8c32-4d42-b76e-e68bfeb20c10`
- **Execution Mode:** `ide_mediated`
- **Repair Packet Published:** `.shipproof/repairs/ac1efe85-8c32-4d42-b76e-e68bfeb20c10/` (`job.json` & `prompt.md`)
- **State Transition:** `CREATED -> JOB_PUBLISHED -> AWAITING_AGENT`.

### Phase 4: Antigravity IDE Agent Code Repair & Change Detection
The Antigravity IDE Agent applied the surgical repair to `demo_targets/sample_store/templates/cart.html` and `config.json`.
- ShipProof's `detect_workspace_changes()` detected modifications to `templates/cart.html` and `config.json`.
- **State Transition:** `AWAITING_AGENT -> AGENT_RESPONSE_RECEIVED -> AWAITING_APPROVAL`.
- **Captured Git Patch (`patch_diff`):**
```diff
diff --git a/demo_targets/sample_store/config.json b/demo_targets/sample_store/config.json
index ca45016..77a4c33 100644
--- a/demo_targets/sample_store/config.json
+++ b/demo_targets/sample_store/config.json
@@ -1,5 +1,5 @@
 {
-  "defect_enabled": true,
+  "defect_enabled": false,
   "defect_type": "checkout_button_broken",
   "defect_description": "Checkout button has broken ID and disabled state preventing order completion"
 }
\ No newline at end of file
diff --git a/demo_targets/sample_store/templates/cart.html b/demo_targets/sample_store/templates/cart.html
index cd1b827..8565ea2 100644
--- a/demo_targets/sample_store/templates/cart.html
+++ b/demo_targets/sample_store/templates/cart.html
@@ -44,14 +44,8 @@
       </div>
 
       <div>
-        {% if defect_enabled %}
-          <!-- INTENTIONAL DEFECT: Button has broken ID and disabled state -->
-          <button id="checkout-btn-broken" class="btn btn-disabled" disabled style="padding: 0.8rem 2rem; font-size: 1.1rem;">Proceed to Checkout</button>
-          <div style="color: var(--danger); font-size: 0.8rem; margin-top: 0.4rem; text-align: right;" id="defect-msg">Error: Checkout button disabled by defect</div>
-        {% else %}
-          <!-- NORMAL / REPAIRED STATE -->
-          <a id="checkout-btn" href="/checkout" class="btn btn-primary" style="padding: 0.8rem 2rem; font-size: 1.1rem;">Proceed to Checkout</a>
-        {% endif %}
+        <!-- REPAIRED BY SHIPPROOF ANTIGRAVITY AGENT -->
+        <a id="checkout-btn" href="/checkout" class="btn btn-primary" style="padding: 0.8rem 2rem; font-size: 1.1rem;">Proceed to Checkout</a>
       </div>
     </div>
```

### Phase 5: Approval & Retest Execution
- Orchestrator approved the repair: `AWAITING_APPROVAL -> APPLYING -> VALIDATING -> RETESTING`.
- Kane CLI retest was launched with the identical objective and target URL:
  - **Retest Run ID:** `eab2ddcc-5b43-4467-b5ad-df7e6f3fc30f`
  - **Retest Kane Session ID:** `/Users/pratham/.testmuai/kaneai/sessions/e3604e6d-0d9e-4ed6-9e32-fc2825b653e1`
  - **Retest Evidence Pack:** `2b863177-d855-4b92-b976-3ea8f862dcd8.evidence`
- **Real Retest Execution Steps:**
  - Step 1: Navigated to `http://127.0.0.1:3005/product/1` (`status: done`)
  - Step 2: Clicked "Add to Cart" (`status: done`)
  - Step 3: Clicked "Proceed to Checkout in the cart summary panel" (`status: done`)
  - Step 4: Waited for "Secure Checkout" heading to be visible (`status: done`)
  - Step 5: Analyzed "Secure Checkout" heading (`status: done`)
  - Step 6: Asserted "Secure Checkout" is displayed (`status: done`)
- **Terminal Event:** `run_end` with `status: "passed"`, duration: 41.6s.

### Phase 6: Final Verification Proof
- Repair Record `ac1efe85-8c32-4d42-b76e-e68bfeb20c10` transitioned to **`VERIFIED`** (`retest_passed: true`).
- Parent Verification Run `157c47e8-b90b-47e1-979d-38bbd01e9118` updated to **`repaired: true`**, **`status: "verified"`**, `repair_attempts: 1`.
- **Closed loop is fully verified and documented with genuine Kane CLI evidence.**
