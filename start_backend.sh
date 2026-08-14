#!/usr/bin/env bash
set -euo pipefail

# Run from the backend directory.
cd "$(dirname "$0")"

# Load environment variables from .env if present.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

# Prefer the local virtual environment's Python if available.
if [ -x .venv/bin/python ]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python"
fi

exec "$PYTHON" -m uvicorn app.main:app --reload --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
