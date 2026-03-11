#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
DEFAULT_DB="${HOME}/sia-notifier/trading_signal_notifier.sqlite"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
REPORT_FILE="${CACHE_DIR}/dashboard.html"
ACTION_SERVER_SCRIPT="${SCRIPT_DIR}/sia-dashboard-actions.command"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

DB_PATH="${SIGNAL_DB_PATH:-$DEFAULT_DB}"
mkdir -p "$CACHE_DIR"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
"$ACTION_SERVER_SCRIPT" || true
"$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/dashboard_report.py" "$REPORT_FILE" "$DB_PATH"

echo "$REPORT_FILE"
echo "대시보드: $REPORT_FILE"

if [[ "${SIA_NO_OPEN_DASHBOARD:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  open "$REPORT_FILE" >/dev/null 2>&1 || true
fi
