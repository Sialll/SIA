#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${SIA_DASHBOARD_ACTIONS_PORT:-8765}"
HOST="${SIA_DASHBOARD_ACTIONS_HOST:-127.0.0.1}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
LOG_FILE="${CACHE_DIR}/dashboard-actions-server.log"
HEALTH_URL="http://${HOST}:${PORT}/health"

mkdir -p "$CACHE_DIR"

if command -v curl >/dev/null 2>&1; then
  if curl -fsS --max-time 1 "$HEALTH_URL" >/dev/null 2>&1; then
    exit 0
  fi
fi

launchctl bootout "gui/$(id -u)/com.sia.dashboard-actions" >/dev/null 2>&1 || true
rm -f "${HOME}/Library/LaunchAgents/com.sia.dashboard-actions.plist"

nohup "$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/dashboard_actions_server.py" --host "$HOST" --port "$PORT" \
  >>"$LOG_FILE" 2>&1 < /dev/null &
disown || true

sleep 0.8
exit 0
