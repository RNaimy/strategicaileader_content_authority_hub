

#!/usr/bin/env bash
set -euo pipefail

# Phase 9 demo script
# Rule #1: Always inform Richard of the desired file before attempting to code or patch anything

echo "=== Phase 9 Demo Start ==="

# Kill any existing uvicorn processes on port 8000
echo "[Step 1] Stopping old uvicorn processes on :8000 (if any)"
pkill -f "uvicorn.*8000" || true

# Export required environment variables
echo "[Step 2] Setting environment variables"
export ENABLE_RETRIEVAL=1
export DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/appdb"

# Start the API in background
echo "[Step 3] Starting Uvicorn server"
uvicorn src.main:app --reload --port 8000 &
UVICORN_PID=$!
sleep 3

# Seed demo content
echo "[Step 4] Seeding demo content for example.com"
PYTHONPATH=".:src" python scripts/seed_demo.py --domain example.com --flush

# Call retrieval health endpoint
echo "[Step 5] Checking retrieval health"
curl -sS http://127.0.0.1:8000/retrieval/health | python -m json.tool

# Trigger reindex
echo "[Step 6] Triggering reindex for example.com"
curl -sS -X POST http://127.0.0.1:8000/retrieval/reindex \
  -H 'Content-Type: application/json' \
  -d '{"domain":"example.com","refresh_embeddings":false}' | python -m json.tool

# Run sample search queries
echo "[Step 7] Running sample search queries"
curl -sS "http://127.0.0.1:8000/retrieval/search?q=pillar&domain=example.com&top_k=5" | python -m json.tool
curl -sS "http://127.0.0.1:8000/retrieval/search?q=deep%20dive&domain=example.com&top_k=5" | python -m json.tool

echo "=== Phase 9 Demo Complete ==="
echo "Use 'kill \$UVICORN_PID' to stop the Uvicorn server when done."