#!/usr/bin/env bash
set -e

echo "=== Starting ShipProof Unified Production Environment on Render ==="

export PYTHONPATH="${PYTHONPATH:-/app}"

# Setup Kane CLI credentials if available
if [ -d "/app/docker/kaneai" ]; then
  mkdir -p /root/.testmuai/kaneai "$HOME/.testmuai/kaneai" 2>/dev/null || true
  cp -rf /app/docker/kaneai/* /root/.testmuai/kaneai/ 2>/dev/null || true
  cp -rf /app/docker/kaneai/* "$HOME/.testmuai/kaneai/" 2>/dev/null || true
  chmod -R 700 /root/.testmuai "$HOME/.testmuai" 2>/dev/null || true
fi

# 1. Start Acme Voyager Storefront on internal port 3005
echo "Launching Acme Voyager Storefront on port 3005..."
python3 -m uvicorn demo_targets.sample_store.app:app --host 0.0.0.0 --port 3005 2>&1 | tee -a /tmp/store.log &
STORE_PID=$!

# 2. Start ShipProof FastAPI Backend on internal port 8000
echo "Launching ShipProof FastAPI Backend on port 8000..."
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /tmp/backend.log &
BACKEND_PID=$!

# 3. Wait and verify backend and store are fully healthy before starting Next.js
echo "Waiting for backend services to initialize..."
MAX_WAIT=20
WAIT_COUNT=0
BACKEND_READY=0

while [ $WAIT_COUNT -lt $MAX_WAIT ]; do
  if python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)" >/dev/null 2>&1; then
    BACKEND_READY=1
    break
  fi
  sleep 1
  WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ $BACKEND_READY -eq 1 ]; then
  echo "✅ FastAPI Backend is UP and healthy on port 8000!"
else
  echo "⚠️ FastAPI Backend on port 8000 did not report ready within ${MAX_WAIT}s. Recent log output:"
  cat /tmp/backend.log 2>/dev/null || true
fi

# 4. Start Next.js Frontend on Render's assigned $PORT (defaults to 10000 or 3000)
PUBLIC_PORT="${PORT:-10000}"
echo "Launching Next.js Frontend on public port $PUBLIC_PORT..."
cd /app/frontend

# Graceful termination handler
trap "kill -TERM $STORE_PID $BACKEND_PID 2>/dev/null || true; wait" SIGINT SIGTERM

exec npm run start -- -p "$PUBLIC_PORT"
