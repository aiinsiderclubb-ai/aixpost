#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ -f "$ROOT/.env" ]]; then
  # Parse dotenv assignments as data. Sourcing breaks on unquoted spaces and
  # executes shell syntax from what should only be configuration.
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key#export }"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ "$value" == \"*\" && "$value" == *\" ]]; then
      value="${value:1:${#value}-2}"
    elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
      value="${value:1:${#value}-2}"
    fi
    export "$key=$value"
  done < "$ROOT/.env"
fi

export FERNET_KEY="${FERNET_KEY:-$(cat "$ROOT/encryption.key" 2>/dev/null | tr -d '\n' || true)}"
export REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"
export USE_RQ_WORKERS="${USE_RQ_WORKERS:-false}"
export PYTHONUNBUFFERED=1

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x /tmp/fb_auto_venv/bin/python ]]; then
    PYTHON_BIN=/tmp/fb_auto_venv/bin/python
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN=python3
  fi
fi

start_worker() {
  echo "Starting RQ posting/fetch worker (queue: default)..."
  "$PYTHON_BIN" rq_worker.py
}

start_analytics_worker() {
  echo "Starting RQ analytics worker (queue: analytics)..."
  "$PYTHON_BIN" rq_analytics_worker.py
}

start_web() {
  echo "Starting AIPostX on http://localhost:8080"
  "$PYTHON_BIN" run_test_v2.py
}

case "${1:-web}" in
  worker) start_worker ;;
  analytics-worker) start_analytics_worker ;;
  web) start_web ;;
  all)
    start_worker &
    start_analytics_worker &
    start_web
    ;;
  *) echo "Usage: $0 [web|worker|analytics-worker|all]" >&2; exit 1 ;;
esac
