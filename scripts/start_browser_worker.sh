#!/usr/bin/env bash
set -euo pipefail

# Chrome + noVNC browser worker for AIPostX (Render web service).
# Serves noVNC on $PORT and runs RQ for Prepare/posting on the same DISPLAY.

export DISPLAY="${DISPLAY:-:99}"
export USE_RQ_WORKERS="${USE_RQ_WORKERS:-true}"
# Prepare goes to "browser"; keep default too so one Docker host can run all Chrome jobs.
export RQ_QUEUES="${RQ_QUEUES:-browser,default}"
NOVNC_PORT="${PORT:-6080}"
VNC_PORT="${VNC_PORT:-5900}"

mkdir -p /tmp /app/data /app/user_data/profiles /app/screenshots /app/logs

if ! pgrep -x Xvfb >/dev/null 2>&1; then
  echo "Starting Xvfb on $DISPLAY"
  Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
  sleep 1
fi

if command -v fluxbox >/dev/null 2>&1 && ! pgrep -x fluxbox >/dev/null 2>&1; then
  echo "Starting fluxbox"
  fluxbox >/tmp/fluxbox.log 2>&1 &
  sleep 1
fi

if ! pgrep -x x11vnc >/dev/null 2>&1; then
  echo "Starting x11vnc on :$VNC_PORT"
  # -nopw: auth is via HTTPS URL secrecy + optional NOVNC_PASSWORD later
  x11vnc \
    -display "$DISPLAY" \
    -rfbport "$VNC_PORT" \
    -localhost \
    -forever \
    -shared \
    -noxdamage \
    -repeat \
    -xkb \
    -nopw \
    >/tmp/x11vnc.log 2>&1 &
  sleep 1
fi

NOVNC_WEB="${NOVNC_WEB_ROOT:-/usr/share/novnc}"
if [[ ! -d "$NOVNC_WEB" ]]; then
  NOVNC_WEB="/usr/share/novnc"
fi

echo "Starting noVNC/websockify on :$NOVNC_PORT (web=$NOVNC_WEB)"
# Prefer websockify from PATH (python package or debian)
if command -v websockify >/dev/null 2>&1; then
  websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "127.0.0.1:$VNC_PORT" >/tmp/websockify.log 2>&1 &
elif python3 -m websockify --help >/dev/null 2>&1; then
  python3 -m websockify --web="$NOVNC_WEB" "$NOVNC_PORT" "127.0.0.1:$VNC_PORT" >/tmp/websockify.log 2>&1 &
else
  echo "ERROR: websockify not found" >&2
  exit 1
fi
WS_PID=$!
sleep 2

if ! kill -0 "$WS_PID" 2>/dev/null; then
  echo "ERROR: websockify died — see /tmp/websockify.log" >&2
  cat /tmp/websockify.log >&2 || true
  exit 1
fi

# Health marker for the dashboard
echo "ok" > /tmp/novnc_ready
echo "noVNC ready at http://0.0.0.0:${NOVNC_PORT}/vnc.html"

if [[ -z "${REDIS_URL:-}" ]]; then
  echo "WARNING: REDIS_URL unset — serving noVNC only (RQ disabled)" >&2
  # Keep container alive for health checks / CAPTCHA viewing
  wait "$WS_PID"
  exit $?
fi

echo "Starting RQ worker (queues=${RQ_QUEUES})"
# Restart RQ if it crashes — do not take down noVNC
while true; do
  python -u rq_worker.py || true
  echo "RQ worker exited — restarting in 5s" >&2
  sleep 5
done
