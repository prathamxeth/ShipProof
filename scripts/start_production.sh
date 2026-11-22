#!/usr/bin/env bash
set -e

echo "=== Starting ShipProof Unified Production Environment on Render ==="

# 1. Start Acme Voyager Storefront on internal port 3005
echo "Launching Acme Voyager Storefront on port 3005..."
python3 -m uvicorn demo_targets.sample_store.app:app --host 127.0.0.1 --port 3005 &
STORE_PID=$!

# 2. Start ShipProof FastAPI Backend on internal port 8000
echo "Launching ShipProof FastAPI Backend on port 8000..."
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# 3. Wait for backend services to initialize
sleep 3

# 4. Start Next.js Frontend on Render's assigned $PORT (defaults to 10000 or 3000)
PUBLIC_PORT="${PORT:-10000}"
echo "Launching Next.js Frontend on public port $PUBLIC_PORT..."
cd /app/frontend

# Graceful termination handler
trap "kill -TERM $STORE_PID $BACKEND_PID 2>/dev/null || true; wait" SIGINT SIGTERM

exec npm run start -- -p "$PUBLIC_PORT"
