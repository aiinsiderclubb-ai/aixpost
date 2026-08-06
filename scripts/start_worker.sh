#!/usr/bin/env bash
set -euo pipefail

# Virtual display for Chrome on headless Render workers.
export DISPLAY="${DISPLAY:-:99}"
if ! pgrep -x Xvfb >/dev/null 2>&1; then
  Xvfb "$DISPLAY" -screen 0 1920x1080x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  sleep 1
fi

export USE_RQ_WORKERS="${USE_RQ_WORKERS:-true}"
exec python -u rq_worker.py
