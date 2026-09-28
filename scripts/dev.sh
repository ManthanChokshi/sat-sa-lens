#!/usr/bin/env bash
# Start the backend and the frontend together for local development.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT_BACKEND="${SATSA_BACKEND_PORT:-8000}"
PORT_FRONTEND="${SATSA_FRONTEND_PORT:-5173}"

if [ ! -d backend/.venv ]; then
  echo "Creating the Python virtual environment..."
  python3 -m venv backend/.venv
  backend/.venv/bin/python -m pip install --upgrade pip
  backend/.venv/bin/python -m pip install -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "Installing frontend dependencies..."
  (cd frontend && npm install)
fi

if [ ! -f data/raw/alerts.csv ]; then
  echo "Generating the sample corpus (seed 42)..."
  backend/.venv/bin/python -m generator.generate --seed 42 --entities 12 --days 90
fi

if [ ! -f data/satsa.duckdb ]; then
  echo "Loading the sample corpus..."
  (cd backend && .venv/bin/python -m app.ingest.load_sample)
  echo "Running the first analysis..."
  (cd backend && .venv/bin/python -m app.runner)
fi

cleanup() {
  echo ""
  echo "Stopping servers..."
  kill 0
}
trap cleanup EXIT INT TERM

echo "Backend  -> http://127.0.0.1:${PORT_BACKEND}  (docs at /docs)"
echo "Frontend -> http://localhost:${PORT_FRONTEND}"
echo ""

(cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port "${PORT_BACKEND}") &
(cd frontend && SATSA_API="http://127.0.0.1:${PORT_BACKEND}" npm run dev -- --port "${PORT_FRONTEND}") &
wait
