#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/.runtime/lan"
LOG_DIR="$RUNTIME_DIR/logs"
PID_DIR="$RUNTIME_DIR/pids"

BACKEND_HOST="0.0.0.0"
BACKEND_PORT="${LEON_BACKEND_PORT:-18001}"
FRONTEND_HOST="0.0.0.0"
FRONTEND_PORT="${LEON_FRONTEND_PORT:-15173}"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

BACKEND_OUT_LOG="$LOG_DIR/backend.out.log"
BACKEND_ERR_LOG="$LOG_DIR/backend.err.log"
FRONTEND_OUT_LOG="$LOG_DIR/frontend.out.log"
FRONTEND_ERR_LOG="$LOG_DIR/frontend.err.log"

mkdir -p "$LOG_DIR" "$PID_DIR"

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command not found: $cmd" >&2
    exit 1
  fi
}

check_pid_file_not_running() {
  local pid_file="$1"
  local service_name="$2"
  if [ ! -f "$pid_file" ]; then
    return
  fi
  local pid
  pid="$(cat "$pid_file")"
  if [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1; then
    echo "ERROR: ${service_name} already running (pid=$pid)." >&2
    echo "Run: scripts/lan/stop.sh" >&2
    exit 1
  fi
  rm -f "$pid_file"
}

wait_http_ok() {
  local url="$1"
  local label="$2"
  local attempts="${3:-30}"
  local delay_s="${4:-0.5}"
  local i
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep "$delay_s"
  done
  echo "ERROR: ${label} health check failed: $url" >&2
  return 1
}

check_cors_preflight() {
  local url="$1"
  local origin="$2"
  local headers
  headers="$(curl -sS -i -X OPTIONS "$url" \
    -H "Origin: $origin" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: content-type" || true)"
  # @@@cors-fail-loud - Treat missing CORS headers as deployment misconfiguration so LAN/manual QA fails fast.
  if ! printf '%s\n' "$headers" | grep -qi '^access-control-allow-origin:'; then
    echo "ERROR: CORS preflight check failed for $url" >&2
    printf '%s\n' "$headers" >&2
    exit 1
  fi
}

ensure_port_free() {
  local port="$1"
  local label="$2"
  if ss -ltn "( sport = :${port} )" | tail -n +2 | grep -q .; then
    echo "ERROR: ${label} port already in use: ${port}" >&2
    exit 1
  fi
}

require_cmd uv
require_cmd npm
require_cmd curl
require_cmd ss

check_pid_file_not_running "$BACKEND_PID_FILE" "backend"
check_pid_file_not_running "$FRONTEND_PID_FILE" "frontend"
ensure_port_free "$BACKEND_PORT" "backend"
ensure_port_free "$FRONTEND_PORT" "frontend"

cd "$ROOT_DIR"
setsid nohup uv run python -m uvicorn backend.web.main:app \
  --host "$BACKEND_HOST" \
  --port "$BACKEND_PORT" \
  >"$BACKEND_OUT_LOG" 2>"$BACKEND_ERR_LOG" < /dev/null &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$BACKEND_PID_FILE"

if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
  echo "ERROR: backend failed to stay alive (pid=$BACKEND_PID)." >&2
  echo "See: $BACKEND_ERR_LOG" >&2
  exit 1
fi

wait_http_ok "http://127.0.0.1:${BACKEND_PORT}/api/health" "backend"
check_cors_preflight "http://127.0.0.1:${BACKEND_PORT}/api/health" "http://192.168.31.117:${FRONTEND_PORT}"
ss -ltn "( sport = :${BACKEND_PORT} )" | grep -q "${BACKEND_HOST}:${BACKEND_PORT}"

cd "$ROOT_DIR/frontend/app"
# @@@strict-port-contract - Fail immediately if port is occupied, so operator sees explicit conflict instead of silent auto-port shift.
LEON_BACKEND_PORT="$BACKEND_PORT" setsid nohup npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" --strictPort \
  >"$FRONTEND_OUT_LOG" 2>"$FRONTEND_ERR_LOG" < /dev/null &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$FRONTEND_PID_FILE"

if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
  echo "ERROR: frontend failed to stay alive (pid=$FRONTEND_PID)." >&2
  echo "See: $FRONTEND_ERR_LOG" >&2
  exit 1
fi

wait_http_ok "http://127.0.0.1:${FRONTEND_PORT}/api/health" "frontend-proxy"
ss -ltn "( sport = :${FRONTEND_PORT} )" | grep -q "0.0.0.0:${FRONTEND_PORT}"

LAN_IP="$(hostname -I | tr ' ' '\n' | grep -E '^[0-9]+(\.[0-9]+){3}$' | grep -v '^127\.' | head -n1 || true)"

echo "backend_pid=$BACKEND_PID"
echo "frontend_pid=$FRONTEND_PID"
echo "backend_url=http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "frontend_local_url=http://127.0.0.1:${FRONTEND_PORT}/resources"
if [ -n "$LAN_IP" ]; then
  echo "frontend_lan_url=http://${LAN_IP}:${FRONTEND_PORT}/resources"
else
  echo "frontend_lan_url=<unable to detect LAN IP>"
fi
echo "backend_logs=$BACKEND_OUT_LOG,$BACKEND_ERR_LOG"
echo "frontend_logs=$FRONTEND_OUT_LOG,$FRONTEND_ERR_LOG"
