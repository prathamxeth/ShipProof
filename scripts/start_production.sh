#!/usr/bin/env bash
set -e

echo "Starting ShipProof Unified Production Environment..."

# 1. Start Sample Store on internal port 3005
echo "Launching Acme Voyager Storefront on port 3005..."
python3 -m uvicorn demo_targets.sample_store.app:app --host 0.0.0.0 --port 3005 &
STORE_PID=$!

# 2. Start FastAPI Backend on $PORT (or 8000)
PORT="${PORT:-8000}"
echo "Launching ShipProof FastAPI Backend on port $PORT..."
python3 -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$PORT" &
BACKEND_PID=$!

# Handle shutdown signals
trap "kill -TERM $STORE_PID $BACKEND_PID 2>/dev/null || true; wait" SIGINT SIGTERM

wait -n $STORE_PID $BACKEND_PID
