#!/usr/bin/env bash
# ==============================================================================
# ShipProof — Hackathon Demo Launcher
# One reliable command to start the entire demonstration environment for judges.
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/runtime"
LOG_DIR="${RUNTIME_DIR}/logs"

mkdir -p "${LOG_DIR}"

STORE_PORT="${STORE_PORT:-3005}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

STORE_LOG="${LOG_DIR}/sample_store.log"
BACKEND_LOG="${LOG_DIR}/backend.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"

STORE_PID=""
BACKEND_PID=""
FRONTEND_PID=""
SHUTTING_DOWN=0

# ------------------------------------------------------------------------------
# Graceful Shutdown Handler
# ------------------------------------------------------------------------------
cleanup() {
  if [ "$SHUTTING_DOWN" -eq 1 ]; then
    return
  fi
  SHUTTING_DOWN=1

  echo ""
  echo "========================================================================"
  echo " Shutting down ShipProof demo services..."
  echo "========================================================================"

  # Stop Frontend and any child processes
  if [ -n "$FRONTEND_PID" ]; then
    echo "  → Stopping Next.js Frontend (PID: $FRONTEND_PID)..."
    local fe_bound=$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -P -t 2>/dev/null || true)
    kill "$FRONTEND_PID" 2>/dev/null || true
    if [ -n "$fe_bound" ] && [ "$fe_bound" != "$FRONTEND_PID" ]; then
      kill "$fe_bound" 2>/dev/null || true
    fi
  fi

  # Stop Backend
  if [ -n "$BACKEND_PID" ]; then
    echo "  → Stopping FastAPI Backend (PID: $BACKEND_PID)..."
    kill "$BACKEND_PID" 2>/dev/null || true
  fi

  # Stop Sample Store
  if [ -n "$STORE_PID" ]; then
    echo "  → Stopping Sample Store (PID: $STORE_PID)..."
    kill "$STORE_PID" 2>/dev/null || true
  fi

  # Wait up to 3 seconds for graceful exit
  for _ in {1..6}; do
    local any_alive=0
    for pid in "$FRONTEND_PID" "$BACKEND_PID" "$STORE_PID"; do
      if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        any_alive=1
      fi
    done
    if [ "$any_alive" -eq 0 ]; then
      break
    fi
    sleep 0.5
  done

  # Force kill if still lingering
  for pid in "$FRONTEND_PID" "$BACKEND_PID" "$STORE_PID"; do
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      echo "  → Force stopping PID $pid..."
      kill -9 "$pid" 2>/dev/null || true
    fi
  done

  # Also clean up child port listeners if they didn't exit
  local linger_store=$(lsof -iTCP:"${STORE_PORT}" -sTCP:LISTEN -P -t 2>/dev/null || true)
  local linger_backend=$(lsof -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -P -t 2>/dev/null || true)
  local linger_frontend=$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -P -t 2>/dev/null || true)
  [ -n "$linger_store" ] && kill -9 "$linger_store" 2>/dev/null || true
  [ -n "$linger_backend" ] && kill -9 "$linger_backend" 2>/dev/null || true
  [ -n "$linger_frontend" ] && kill -9 "$linger_frontend" 2>/dev/null || true

  echo "========================================================================"
  echo " All ShipProof demo services stopped cleanly."
  echo " Persistent databases, Kane evidence, and host processes remain intact."
  echo "========================================================================"
}

trap cleanup INT TERM

fail_startup() {
  local message="$1"
  echo ""
  echo "************************************************************************"
  echo "[STARTUP ERROR] ${message}"
  echo "Aborting demo launch and shutting down any launched services..."
  echo "************************************************************************"
  cleanup
  exit 1
}

# ------------------------------------------------------------------------------
# Banner
# ------------------------------------------------------------------------------
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                  SHIPPROOF — HACKATHON DEMO LAUNCHER                 ║"
echo "║       Your AI writes the code. ShipProof proves it works.           ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# ------------------------------------------------------------------------------
# Step 1: Validate Required Dependencies
# ------------------------------------------------------------------------------
echo "[1/6] Validating dependencies..."

# Node.js
if ! command -v node >/dev/null 2>&1; then
  fail_startup "Node.js is not installed or not in PATH."
fi
NODE_VERSION=$(node -v)
echo "  ✓ Node.js: ${NODE_VERSION}"

# npm
if ! command -v npm >/dev/null 2>&1; then
  fail_startup "npm is not installed or not in PATH."
fi
NPM_VERSION=$(npm -v)
echo "  ✓ npm: v${NPM_VERSION}"

# Python backend virtualenv
PYTHON_BIN="${ROOT_DIR}/backend/.venv/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
  fail_startup "Backend Python virtual environment not found at: ${PYTHON_BIN}\nPlease run: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
fi
PY_VERSION=$("${PYTHON_BIN}" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
echo "  ✓ Python virtualenv: v${PY_VERSION} (${PYTHON_BIN})"

# Kane CLI
if ! command -v kane-cli >/dev/null 2>&1; then
  fail_startup "kane-cli executable not found in PATH.\nPlease install Kane CLI: npm install -g @testmuai/kane-cli"
fi
KANE_VERSION=$(kane-cli --version 2>/dev/null || echo "detected")
echo "  ✓ Kane CLI: ${KANE_VERSION}"

# Docker
if ! command -v docker >/dev/null 2>&1; then
  echo "  ⚠ Docker CLI not found. Note: Docker is required for isolated worker execution."
elif ! docker info >/dev/null 2>&1; then
  echo "  ⚠ Docker daemon is not running or socket is inaccessible. Note: Required for worker jobs."
else
  WORKER_IMAGE="shipproof-worker-production:1.0.0"
  if docker image inspect "${WORKER_IMAGE}" >/dev/null 2>&1; then
    IMAGE_DIGEST=$(docker image inspect "${WORKER_IMAGE}" --format '{{index .RepoDigests 0}}' 2>/dev/null || echo "local")
    echo "  ✓ Docker worker image: ${WORKER_IMAGE} (${IMAGE_DIGEST})"
  else
    echo "  ⚠ Docker worker image '${WORKER_IMAGE}' not found locally. Run: docker build -t ${WORKER_IMAGE} -f docker/Dockerfile.worker ."
  fi
fi

# ------------------------------------------------------------------------------
# Step 2: Validate Kane Authentication
# ------------------------------------------------------------------------------
echo ""
echo "[2/6] Checking Kane CLI authentication status..."
KANE_AUTH_OUTPUT=$(kane-cli whoami 2>&1 || true)
if echo "${KANE_AUTH_OUTPUT}" | grep -qiE "Authenticated:\s*YES|Token:\s*valid"; then
  PROFILE_NAME=$(echo "${KANE_AUTH_OUTPUT}" | grep -i "Profile:" | head -n 1 | awk '{print $2}' || echo "Default")
  echo "  ✓ Kane CLI is authenticated (Profile: ${PROFILE_NAME})."
else
  echo "  ⚠ Kane CLI OAuth token is not verified or expired."
  echo "    Detail from kane-cli whoami:"
  echo "${KANE_AUTH_OUTPUT}" | sed 's/^/      /'
  echo "    To authenticate Kane CLI before running browser verifications, run:"
  echo "      kane-cli login --profile Pratham --oauth"
  echo "    Proceeding with demo UI startup..."
fi

# ------------------------------------------------------------------------------
# Step 3: Check Required Ports
# ------------------------------------------------------------------------------
echo ""
echo "[3/6] Inspecting service ports (${STORE_PORT}, ${BACKEND_PORT}, ${FRONTEND_PORT})..."

PORT_CONFLICT=0
for check_entry in "${STORE_PORT}:Sample Store" "${BACKEND_PORT}:FastAPI Backend" "${FRONTEND_PORT}:Next.js Frontend"; do
  PORT="${check_entry%%:*}"
  NAME="${check_entry##*:}"

  PID=$(lsof -iTCP:"${PORT}" -sTCP:LISTEN -P -t 2>/dev/null | head -n 1 || true)
  if [ -n "$PID" ]; then
    PROC_INFO=$(lsof -iTCP:"${PORT}" -sTCP:LISTEN -P 2>/dev/null | tail -n +2 | head -n 1 || true)
    echo "  ✗ Port ${PORT} (${NAME}) is already occupied by PID ${PID}."
    echo "    Occupying Process: ${PROC_INFO}"
    PORT_CONFLICT=1
  else
    echo "  ✓ Port ${PORT} (${NAME}) is free."
  fi
done

if [ "$PORT_CONFLICT" -eq 1 ]; then
  echo ""
  echo "************************************************************************"
  echo "[PORT CONFLICT] One or more required ports are already in use."
  echo "To prevent starting duplicate services or causing port collisions,"
  echo "please terminate the occupying process(es) before running demo.sh:"
  echo "  e.g.: kill <PID>"
  echo "************************************************************************"
  exit 1
fi

# ------------------------------------------------------------------------------
# Step 4: Start Sample Store (Port 3005)
# ------------------------------------------------------------------------------
echo ""
echo "[4/6] Starting Sample Store on port ${STORE_PORT}..."
echo "  → Target: demo_targets/sample_store/app.py"
echo "  → Log: ${STORE_LOG}"

cd "${ROOT_DIR}"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m uvicorn demo_targets.sample_store.app:app \
  --host 127.0.0.1 \
  --port "${STORE_PORT}" \
  > "${STORE_LOG}" 2>&1 &
STORE_PID=$!
echo "  ✓ Sample Store process launched (PID: ${STORE_PID})"

# ------------------------------------------------------------------------------
# Step 5: Start FastAPI Backend (Port 8000)
# ------------------------------------------------------------------------------
echo ""
echo "[5/6] Starting FastAPI Backend on port ${BACKEND_PORT}..."
echo "  → Target: backend.app.main:app"
echo "  → Log: ${BACKEND_LOG}"

cd "${ROOT_DIR}"
PYTHONPATH="${ROOT_DIR}" "${PYTHON_BIN}" -m uvicorn backend.app.main:app \
  --host 127.0.0.1 \
  --port "${BACKEND_PORT}" \
  > "${BACKEND_LOG}" 2>&1 &
BACKEND_PID=$!
echo "  ✓ FastAPI Backend process launched (PID: ${BACKEND_PID})"

# ------------------------------------------------------------------------------
# Step 6: Start Next.js Frontend (Port 3000)
# ------------------------------------------------------------------------------
echo ""
echo "[6/6] Starting Next.js Frontend on port ${FRONTEND_PORT}..."
echo "  → Target: frontend/ (Next.js 16)"
echo "  → Log: ${FRONTEND_LOG}"

cd "${ROOT_DIR}/frontend"
PORT="${FRONTEND_PORT}" npx next dev -p "${FRONTEND_PORT}" > "${FRONTEND_LOG}" 2>&1 &
FRONTEND_PID=$!
echo "  ✓ Next.js Frontend process launched (PID: ${FRONTEND_PID})"

# ------------------------------------------------------------------------------
# Wait For Health & Readiness
# ------------------------------------------------------------------------------
echo ""
echo "Waiting for services to become healthy..."

wait_for_health() {
  local service_name="$1"
  local port="$2"
  local url="$3"
  local pid="$4"
  local log_path="$5"
  local max_seconds=35
  local elapsed=0

  echo -n "  → Checking ${service_name} at ${url} "
  while [ "$elapsed" -lt "$max_seconds" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo " [DIED]"
      echo "[ERROR] ${service_name} (PID: ${pid}) terminated prematurely."
      echo "--- Last 25 lines of ${log_path} ---"
      tail -n 25 "${log_path}" 2>/dev/null || true
      echo "-----------------------------------"
      fail_startup "${service_name} process died on startup."
    fi

    # 1. Primary check: HTTP response
    local http_status
    http_status=$(curl -s -o /dev/null -w "%{http_code}" --noproxy "*" --connect-timeout 1 "$url" 2>/dev/null || echo "000")
    if [ "$http_status" -ge 200 ] && [ "$http_status" -lt 400 ]; then
      echo " [READY - HTTP ${http_status}]"
      return 0
    fi

    # 2. Port binding check: verify port is actively bound in TCP LISTEN state
    local bound_pid
    bound_pid=$(lsof -iTCP:"${port}" -sTCP:LISTEN -P -t 2>/dev/null | head -n 1 || true)
    if [ -n "$bound_pid" ]; then
      sleep 1
      echo " [READY - Port :${port} active]"
      return 0
    fi

    echo -n "."
    sleep 1
    elapsed=$((elapsed + 1))
  done

  echo " [TIMEOUT]"
  echo "[ERROR] ${service_name} did not become ready within ${max_seconds} seconds."
  echo "--- Last 25 lines of ${log_path} ---"
  tail -n 25 "${log_path}" 2>/dev/null || true
  echo "-----------------------------------"
  fail_startup "${service_name} health check timed out."
}

wait_for_health "Sample Store" "${STORE_PORT}" "http://127.0.0.1:${STORE_PORT}/" "$STORE_PID" "$STORE_LOG"
wait_for_health "FastAPI Backend" "${BACKEND_PORT}" "http://127.0.0.1:${BACKEND_PORT}/api/health" "$BACKEND_PID" "$BACKEND_LOG"
wait_for_health "Next.js Frontend" "${FRONTEND_PORT}" "http://localhost:${FRONTEND_PORT}/projects" "$FRONTEND_PID" "$FRONTEND_LOG"

# ------------------------------------------------------------------------------
# Launch Dashboard in Browser
# ------------------------------------------------------------------------------
DASHBOARD_URL="http://localhost:${FRONTEND_PORT}/projects"
echo ""
echo "Opening ShipProof Dashboard in default browser: ${DASHBOARD_URL}"
if command -v open >/dev/null 2>&1; then
  open "${DASHBOARD_URL}" 2>/dev/null || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "${DASHBOARD_URL}" 2>/dev/null || true
fi

# ------------------------------------------------------------------------------
# Ready Banner
# ------------------------------------------------------------------------------
echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║          SHIPPROOF DEMO ENVIRONMENT IS READY FOR EVALUATION         ║"
echo "╠══════════════════════════════════════════════════════════════════════╣"
echo "║                                                                      ║"
echo "║  🌐 Web Dashboard:    http://localhost:${FRONTEND_PORT}/projects                 ║"
echo "║  ⚡ FastAPI Backend:   http://localhost:${BACKEND_PORT}/api/docs                 ║"
echo "║  🛍️  Sample Store:     http://localhost:${STORE_PORT}/                          ║"
echo "║                                                                      ║"
echo "║  📂 Runtime Logs:     ./runtime/logs/                                ║"
echo "║     • sample_store.log (PID: ${STORE_PID})                                  ║"
echo "║     • backend.log      (PID: ${BACKEND_PID})                                  ║"
echo "║     • frontend.log     (PID: ${FRONTEND_PID})                                  ║"
echo "║                                                                      ║"
echo "║  💡 Tips for Judges:                                                 ║"
echo "║     1. Navigate to Projects → Sample Store Tech Gear                 ║"
echo "║     2. Click 'Launch Verification' to trigger real Kane execution    ║"
echo "║     3. Inspect Failure Analysis, Screenshots & LambdaTest Link       ║"
echo "║     4. Review Proposed Diff in Repair Studio & Approve Retest        ║"
echo "║                                                                      ║"
echo "║  Press [Ctrl+C] at any time to shut down all demo services cleanly.  ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Wait on background processes
wait
