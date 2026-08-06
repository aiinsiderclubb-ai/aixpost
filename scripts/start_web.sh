#!/usr/bin/env bash
set -euo pipefail
PORT="${PORT:-8080}"
# gthread avoids eventlet monkey-patch conflicts on Render.
exec gunicorn -k gthread -w 1 --threads 8 "run_test_v2:create_app()" --bind "0.0.0.0:${PORT}"
