#!/usr/bin/env bash
set -euo pipefail
# Render-compatible start: prefer eventlet worker; fall back to gthread.
PORT="${PORT:-8080}"
exec gunicorn -k eventlet -w 1 "run_test_v2:create_app()" --bind "0.0.0.0:${PORT}"
