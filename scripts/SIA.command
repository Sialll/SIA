#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${HOME}/.config/sia-notifier"
ENV_FILE="${CONFIG_DIR}/env"
MARKET_FILE="${CONFIG_DIR}/market-selection.json"
MARKER_FILE="${CONFIG_DIR}/setup-complete"
FIRST_RUN_SCRIPT="${SCRIPT_DIR}/_internal/sia-first-run.command"

needs_setup="0"
if [[ ! -f "$MARKER_FILE" ]]; then
  if [[ ! -f "$ENV_FILE" || ! -f "$MARKET_FILE" ]]; then
    needs_setup="1"
  elif ! grep -q '^export TELEGRAM_BOT_TOKEN="[^"]' "$ENV_FILE" 2>/dev/null; then
    needs_setup="1"
  else
    mkdir -p "$CONFIG_DIR"
    date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER_FILE"
  fi
fi

if [[ "${1:-}" == "--setup" ]]; then
  exec "$FIRST_RUN_SCRIPT"
fi

if [[ "$needs_setup" == "1" ]]; then
  "$FIRST_RUN_SCRIPT"
fi

exec "${SCRIPT_DIR}/SIA-Dashboard.command"
