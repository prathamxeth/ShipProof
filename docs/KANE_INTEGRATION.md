# ShipProof — Kane CLI Integration & Evidence Engine

## 1. Overview & Architecture

ShipProof uses **Kane CLI** as the ground-truth browser verification layer for autonomous AI software development.
This document describes the design, execution protocol, NDJSON stream parsing contract, evidence extraction pipeline, and REST/SSE API interfaces implemented in Milestone 2.

```
+--------------------------------------------------------------------------------+
|                             ShipProof Application                              |
+--------------------------------------------------------------------------------+
      |                                              ^
      | 1. Enqueue Verification Run                  | 4. SSE Stream / Evidence
      v                                              |
+-------------------+                          +--------------------+
|   RunnerService   |                          |  EvidenceService   |
+-------------------+                          +--------------------+
      |                                              ^
      | 2. Async Subprocess                          | 3. Locate & Unpack
      v                                              |    .evidence ZIP
+-------------------+     NDJSON Events (stdout)     |
|    KaneService    | -------------------------> KaneParser
+-------------------+                          +--------------------+
      |                                              |
      | Executes                                     | Normalizes & Persists
      v                                              v
+-------------------------------------------------------------------+
| /opt/homebrew/bin/kane-cli run "<objective>" --url <url> --agent   |
| (Real Google Chrome Browser / Headless Automation / Evidence Pack)|
+-------------------------------------------------------------------+
```

---

## 2. CLI Invocation Protocol

### Command Shape
```bash
KANE_CLI_USER_AGENT=shipproof-antigravity /opt/homebrew/bin/kane-cli run "<objective>" \
  --url <target_url> \
  --agent \
  --headless \
  --name <run_slug> \
  --timeout <seconds>
```

### Safety & Isolation Guarantees
- **No `shell=True`:** Subprocess execution is invoked directly via `asyncio.create_subprocess_exec` passing validated argument arrays.
- **Process Isolation:** Stdout (NDJSON event stream) and stderr (TUI progress & evidence hints) are captured separately and written to audit logs at `backend/data/runs/<run_id>/raw_stdout.log` and `raw_stderr.log`.
- **Runtime Tagging:** Every invocation sets `KANE_CLI_USER_AGENT=shipproof-antigravity`.
- **Credential Protection:** Authentication relies strictly on local OAuth tokens managed by the system profile (`Pratham`), with zero credentials logged or transmitted over REST.

---

## 3. NDJSON Event Contract

With `--agent`, Kane CLI outputs one JSON object per line to **stdout**. The parser handles typeless progress lines, envelope events, and terminal events:

### Event Families

| Event Type | Structure / Fields | Description |
| :--- | :--- | :--- |
| `stream_start` | `{"type":"stream_start","cli_version":"0.10.4","surface":"run","pid":...}` | Initial envelope establishing session parameters |
| `step` (typeless) | `{"step": 1, "status": "running"\|"done"\|"failed", "remark": "..."}` | Live step progress; typeless by design (no `type` key) |
| `bifurcation` | `{"type":"bifurcation","flows":[...],"count":1}` | Splitting of high-level objective into sub-flows |
| `coverage` | `{"type":"coverage","status":"written"\|"skipped","pct":...}` | Test coverage accounting |
| `error` | `{"type":"error","message":"...","code":...}` | Non-terminal or fatal execution error |
| `run_end` (terminal) | `{"type":"run_end","status":"passed"\|"failed","summary":"...","session_dir":"..."}` | Authoritative terminal execution verdict |

### Terminal Verdict Rules
1. A run can **ONLY** be transitioned to `PASSED` when a genuine terminal `run_end` event has been received with `status: "passed"`.
2. Process exit code `0` without a `run_end` event produces `INCOMPLETE`, **never a false pass**.
3. Malformed JSON lines are preserved as `malformed` events without interrupting execution.
4. Unknown event types are retained and stored in SQLite.

---

## 4. Evidence Archive Structure

Every Kane CLI execution seals an `.evidence` archive (standard ZIP) located at:
`~/.testmuai/kaneai/sessions/<session_id>/evidence/<execution_id>.evidence`

### Internal ZIP Hierarchy
```
<execution_id>.evidence
├── run.yaml                                    # Run manifest: status, duration, totals
├── failure.yaml                                # Top-level failure summary
└── tests/<test-id>/
    ├── test.md                                 # Executed test scenario definition
    ├── result.yaml                             # Step-level verdict breakdown
    ├── logs/
    │   ├── 0-actions.ndjson                    # Chronological actions taken by browser agent
    │   ├── 0-console.ndjson                    # Browser console log (errors, warnings)
    │   ├── 0-network.har                       # Full network HAR trace
    │   └── 0-run.log                           # Raw runner execution trace
    └── steps/<ordinal>-<child>-<step-id>/
        ├── screenshot.jpg                      # Browser screenshot at step execution
        ├── annotated.jpg                       # Highlighted element acted upon (if generated)
        ├── step.json                           # Step DOM extraction metadata
        └── failure.yaml                        # Deep RCA failure triage (on failed steps)
```

### Security & Sanitization
- **Path Traversal Defense:** Every ZIP entry is validated against `..` segments and verified that `os.path.commonpath([dest, target]) == dest`. Any violation raises `PathTraversalError`.
- **Extraction Bounds:** Max total uncompressed bytes: 100 MB; max single file: 50 MB; max entry count: 1000.
- **HAR Credential Redaction:** Network HAR files have `Authorization`, `Cookie`, `Set-Cookie`, `x-api-key`, and other tokens redacted to `[REDACTED]` prior to disk persistence and REST delivery.

---

## 5. API Contracts

### 1. Create Run
- **Endpoint:** `POST /api/runs`
- **Payload:**
  ```json
  {
    "title": "Smoke Verification",
    "objective": "Verify heading contains 'Example Domain'",
    "target_url": "https://example.com",
    "mode": "verify_only",
    "headless": true,
    "timeout": 120
  }
  ```
- **Response (201 Created):** `RunSummaryResponse`

### 2. Get Run Details
- **Endpoint:** `GET /api/runs/{run_id}`
- **Response (200 OK):** `RunDetailResponse` including step list, execution duration, and evidence pack path.

### 3. Cancel Run
- **Endpoint:** `POST /api/runs/{run_id}/cancel`
- **Response (200 OK):** `CancelResponse` with status `cancelled`.

### 4. Live Event Stream (Server-Sent Events)
- **Endpoint:** `GET /api/runs/{run_id}/events?stream=true`
- **Header:** `Accept: text/event-stream`
- **Stream Format:**
  ```text
  data: {"event_type": "step", "step_number": 1, "status": "done", "description": "Navigated to https://example.com", "timestamp": "2026-11-16T01:50:00Z"}

  data: {"event_type": "run_end", "status": "failed", "description": "Stale content", "timestamp": "2026-11-16T01:50:14Z"}
  ```

### 5. Get Evidence Metadata
- **Endpoint:** `GET /api/runs/{run_id}/evidence`
- **Response (200 OK):** `EvidenceResponse` containing discovered screenshots, failure YAML triage, console error count, and network failure count.

### 6. Serve Evidence File
- **Endpoint:** `GET /api/runs/{run_id}/evidence/files/{file_path}`
- **Response (200 OK):** Image or log file with appropriate MIME type (e.g., `image/jpeg`, `image/png`). Strictly contained within the run's evidence directory.

---

## 6. How to Reproduce the Real Smoke Test

To execute a controlled real Kane CLI smoke test using the authenticated environment:

```bash
cd /Users/pratham/Projects/ShipProof
PYTHONPATH=. ./backend/.venv/bin/python -c "
import asyncio
from backend.app.core.database import init_db
from backend.app.services.runner_service import runner_service

async def run_test():
    await init_db()
    runner_service.enqueue_run(
        run_id='smoke-test-01',
        objective=\"Verify that page title is 'Example Domain'\",
        target_url='https://example.com',
        headless=True,
        timeout=120
    )

asyncio.run(run_test())
"
```

To run all automated unit tests:
```bash
./backend/.venv/bin/pytest backend/tests -v
```
