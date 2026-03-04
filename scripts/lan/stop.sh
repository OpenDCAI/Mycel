#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PID_DIR="$ROOT_DIR/.runtime/lan/pids"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

stop_by_pid_file() {
  local pid_file="$1"
  local name="$2"
  if [ ! -f "$pid_file" ]; then
    echo "${name}: not running (pid file missing)"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"
  if [ -z "$pid" ]; then
    echo "${name}: invalid pid file ($pid_file)"
    rm -f "$pid_file"
    return
  fi

  if ! kill -0 "$pid" >/dev/null 2>&1; then
    echo "${name}: stale pid file (pid=$pid)"
    rm -f "$pid_file"
    return
  fi

  kill "$pid"
  sleep 1
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill -9 "$pid"
  fi

  rm -f "$pid_file"
  echo "${name}: stopped (pid=$pid)"
}

stop_by_pid_file "$FRONTEND_PID_FILE" "frontend"
stop_by_pid_file "$BACKEND_PID_FILE" "backend"
