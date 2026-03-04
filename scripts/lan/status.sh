#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_DIR="$ROOT_DIR/.runtime/lan/pids"

BACKEND_PORT="${LEON_BACKEND_PORT:-18001}"
FRONTEND_PORT="${LEON_FRONTEND_PORT:-15173}"

report_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  if [ ! -f "$pid_file" ]; then
    echo "${name}: down (no pid file)"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [ -z "$pid" ]; then
    echo "${name}: down (empty pid file)"
    return
  fi

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "${name}: up (pid=$pid)"
  else
    echo "${name}: down (stale pid=$pid)"
  fi

  ss -ltn "( sport = :${port} )" | tail -n +2 | sed "s/^/${name} port ${port}: /" || true
}

report_service "backend" "$PID_DIR/backend.pid" "$BACKEND_PORT"
report_service "frontend" "$PID_DIR/frontend.pid" "$FRONTEND_PORT"
