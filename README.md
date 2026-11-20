# ShipProof
> **Your AI writes the code. ShipProof proves it works.**

ShipProof is an autonomous website verification, failure root-cause analysis, and closed-loop repair platform powered by **Kane CLI** and **LambdaTest**. It executes real browser-based verification objectives inside isolated Docker workers, captures forensic test evidence (screenshots, action traces, and failure triage), structures repair packets for IDE agents, and enforces authenticated human approval before retesting the fix on LambdaTest.

Built for the **Kane CLI Online Hackathon 2026** (`kaneclihack.sh`).

---

## 🚀 Quickstart for Hackathon Judges

Get the entire ShipProof evaluation environment up and running with a single command.

### 1. Prerequisites

Ensure the following tools are installed on your machine:

- **Node.js**: v18+ and `npm`
- **Python**: v3.11+ (with virtual environment in `backend/.venv`)
- **Kane CLI**: `@testmuai/kane-cli` (`npm install -g @testmuai/kane-cli`)
- **Docker**: Docker Desktop running (for isolated worker execution)
- **Production Worker Image**: `shipproof-worker-production:1.0.0`
  *(If building from source: `docker build -t shipproof-worker-production:1.0.0 -f docker/Dockerfile.worker .`)*

### 2. Kane Authentication

Kane CLI requires valid authentication to orchestrate cloud browser sessions on LambdaTest:

```bash
# Check current authentication status
kane-cli whoami

# Authenticate via OAuth if not logged in or token is expired
kane-cli login --profile Pratham --oauth
```

*(ShipProof automatically selects the `ShipProof` project and `ASUR` folder upon login).*

### 3. One-Command Startup

Start the Sample Store, FastAPI backend, and Next.js frontend with readiness verification:

```bash
./scripts/demo.sh
```

The launcher will:
1. Validate Node.js, Python virtual environment, Kane CLI, and Docker image.
2. Confirm Kane CLI authentication status.
3. Verify ports `3005`, `8000`, and `3000` are free to avoid duplicate services.
4. Launch Sample Store (:3005), FastAPI Backend (:8000), and Next.js Frontend (:3000).
5. Poll and wait for all three services to return healthy HTTP 200 responses.
6. Automatically open the ShipProof Dashboard in your default browser.

### 4. Local Service URLs

| Service | Port | Local URL | Purpose |
| :--- | :---: | :--- | :--- |
| **ShipProof Web Dashboard** | `3000` | [`http://localhost:3000/projects`](http://localhost:3000/projects) | Next.js interface for runs, evidence, and Repair Studio |
| **ShipProof FastAPI API** | `8000` | [`http://localhost:8000/api/docs`](http://localhost:8000/api/docs) | OpenAPI interactive documentation and health endpoints |
| **Sample Store Target** | `3005` | [`http://localhost:3005`](http://localhost:3005) | E-commerce application tested by Kane CLI |

### 5. Clean Shutdown

To stop all demo services, simply press **`Ctrl+C`** in the terminal running `./scripts/demo.sh`.

The launcher traps the interrupt signal and performs an orderly shutdown:
- Gracefully terminates only the processes launched by the script.
- Leaves any pre-existing processes and system services untouched.
- Preserves the SQLite database (`backend/data/shipproof.db`) and Kane evidence packs.

### 6. Troubleshooting

- **Port Conflict (`EADDRINUSE`):**
  If port `3005`, `8000`, or `3000` is occupied, `demo.sh` halts safely without killing unrelated processes. To free a port:
  ```bash
  lsof -iTCP:8000 -sTCP:LISTEN -P
  kill <PID>
  ```
- **Kane CLI OAuth Expired:**
  Run `kane-cli whoami`. If token validation fails, re-authenticate with:
  ```bash
  kane-cli login --profile Pratham --oauth
  ```
- **Docker Worker Image Missing:**
  Build the production image locally before running verifications:
  ```bash
  docker build -t shipproof-worker-production:1.0.0 -f docker/Dockerfile.worker .
  ```
- **Runtime Logs:**
  All process output is streamed to `./runtime/logs/`:
  - `runtime/logs/sample_store.log`
  - `runtime/logs/backend.log`
  - `runtime/logs/frontend.log`

---

## 🏆 Judge Evaluation Walkthrough

1. **Open Projects**: Navigate to [`http://localhost:3000/projects`](http://localhost:3000/projects).
2. **Review Defect Run**: Inspect run `e5c9662e-7982-4365-9c4a-13e18a76f653` to observe genuine Kane browser steps (`navigate`, `analyze`, `assert`), inline screenshots, failure triage, and the live LambdaTest session link.
3. **Inspect Repair Studio**: Open repair `d34847ec-89ca-4d85-9b5b-7e06ff118812` to see the Antigravity agent handoff packet, proposed Git diff, and authenticated human approval record (`approved_by: pratham-principal-auditor`).
4. **Verify Retest Run**: Click **"View Retest in LambdaTest"** on retest run `50d7bee9-9403-46b3-8fa4-4e44afa6976a` to confirm the closed-loop repair passed independently with exit code 0.
