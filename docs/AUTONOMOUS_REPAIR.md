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
| `created_at` | `DateTime` | Timestamp of packet generation |

### Security & Context Safeguards
- **Strict Credential Redaction:** Passwords, tokens, Bearer headers, and secrets in HAR network logs or console strings are sanitized before packet generation.
- **Project Boundary Scoping:** Candidate files are strictly limited to the target project directory (e.g. `demo_targets/sample_store/`), preventing the agent from modifying parent tooling or unrelated projects.
- **JSON Serialization Safety:** Nested YAML timestamps and datetimes are cleanly normalized to ISO-8601 strings.

---

## 3. Antigravity Agent Integration Bridge

### CLI and IDE Capability Assessment
The bridge inspected the real environment capabilities of Antigravity:
- **Executable:** `/Users/pratham/.gemini/bin/agy` (v2.0 preview)
- **Supported Models:** `gemini-3.8-flash-high`, `gemini-3.8-flash-low`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`
- **Headless Non-Interactive Flag:** `agy -p "..." --output-format json`

### Security Compliance (No `--dangerously-skip-permissions`)
In accordance with Rule 8, `--dangerously-skip-permissions` is **never** used. Running headless file modifications without explicit review triggers interactive terminal prompts that block automation. 

Therefore, ShipProof implements the **IDE-Mediated Repair Workflow**:
1. ShipProof publishes structured repair job metadata to `.shipproof/repairs/<repair_id>/`:
   - `job.json`: Full repair packet payload and current state.
   - `prompt.md`: Markdown prompt tailored for the Antigravity IDE agent.
2. The Antigravity IDE agent accesses the workspace files, inspects the failure triage, and applies surgical source code modifications.
3. The user or orchestrator reviews the resulting unified Git diff and approves the change via `POST /api/repairs/{id}/approve`.
4. Only upon explicit approval does the orchestrator apply, validate, and rerun the Kane verification.

---

## 4. Orchestrator State Machine

The repair lifecycle is strictly governed by `RepairOrchestrator` (`backend/app/services/repair_orchestrator.py`):

```
CREATED
   ↓
ANALYZING ──────→ (Error) ──→ FAILED
   ↓
PROPOSED
   ↓
AWAITING_APPROVAL ──→ (User Cancel) ──→ CANCELLED
   ↓ (Explicit Approval)
APPLYING
   ↓
VALIDATING ─────→ (Syntax/Build Break) ──→ UNRESOLVED
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

A live end-to-end verification and repair demonstration was executed on macOS using the included `sample_store` demo application.

### Phase 1: Defect Injection
An intentional defect was enabled in `demo_targets/sample_store/templates/cart.html` and `config.json`:
- The cart checkout button ID was mutated to `checkout-btn-broken` with `disabled` attribute.
- An error banner `<div id="defect-msg">Error: Checkout button disabled by defect</div>` was injected.

### Phase 2: Initial Kane Verification Run (Failure Detection)
- **ShipProof Run ID:** `0c1d3be8-4e9f-446e-98d9-900d5a14389c`
- **Target URL:** `http://127.0.0.1:3005/product/1`
- **Objective:** `Click 'Add to Cart', then in the cart click 'Proceed to Checkout', and verify that 'Secure Checkout' is displayed.`
- **Real Kane Session ID:** `/Users/pratham/.testmuai/kaneai/sessions/c97f08bf-2114-435b-80e7-cdb8e58d4f55`
- **Evidence Pack:** `614c90a4-40ca-4e2d-b6b0-de4274300f92.evidence`
- **Observed Result:** Kane navigated to `/product/1`, clicked "Add to Cart", navigated to `/cart`, identified the disabled checkout button, and failed at Step 3.
- **Kane Failure Reason:**
  > `"The cart's Proceed to Checkout button is disabled and the page reports a checkout defect. Fix the cart checkout eligibility logic so Proceed to Checkout is enabled."`
- **Terminal Verdict:** `FAILED` (Exit code: 1).

### Phase 3: Repair Packet Generation
- **Repair Session ID:** `3fff0cce-4f54-4b1b-8121-71ab938a9b25`
- Repair packet generated and published to `.shipproof/repairs/3fff0cce-4f54-4b1b-8121-71ab938a9b25/`.
- State transitioned: `CREATED -> ANALYZING -> PROPOSED -> AWAITING_APPROVAL`.

### Phase 4: Antigravity Code Repair
The Antigravity agent repaired `demo_targets/sample_store/templates/cart.html` and `config.json`.
- **Recorded Git Diff:**
```diff
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
- Orchestrator approved the repair: `APPLYING -> VALIDATING -> RETESTING`.
- Kane CLI retest was launched with the identical objective and target URL:
  - **Retest Run ID:** `b81f23b2-cf41-42a8-9f17-25f89c5ed160`
  - **Retest Kane Session ID:** `/Users/pratham/.testmuai/kaneai/sessions/40e33715-e2f4-422b-af8d-e688a317133a`
  - **Retest Evidence Pack:** `41df1783-f614-4323-b8d7-003869a6c097.evidence`
- **Real Retest Execution Steps:**
  - Step 1: Navigated to `http://127.0.0.1:3005/product/1` (`status: done`)
  - Step 2: Clicked "Add to Cart" (`status: done`)
  - Step 3: Clicked "Proceed to Checkout in the cart" (`status: done`)
  - Step 4: Waited for "Secure Checkout" page to load (`status: done`)
  - Step 5: Analyzed "Secure Checkout" heading (`status: done`)
  - Step 6: Asserted "Secure Checkout" is displayed (`status: done`)
- **Terminal Event:** `run_end` with `status: "passed"`, duration: 35.3s.

### Phase 6: Final Verification Proof
- Repair Record `3fff0cce-4f54-4b1b-8121-71ab938a9b25` transitioned to **`VERIFIED`** (`retest_passed: true`).
- Parent Verification Run `0c1d3be8-4e9f-446e-98d9-900d5a14389c` updated to **`repaired: true`**, **`status: "verified"`**, `repair_attempts: 1`.
- **Closed loop is fully verified and documented with genuine Kane CLI evidence.**
