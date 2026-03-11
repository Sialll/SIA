#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
DEFAULT_DB="${HOME}/sia-notifier/trading_signal_notifier.sqlite"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

DB_PATH="${SIGNAL_DB_PATH:-$DEFAULT_DB}"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "파이썬 인터프리터를 찾을 수 없습니다: ${PYTHON_BIN}" >&2
  exit 3
fi

"$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/backfill_signal_source.py" --db-path "$DB_PATH" "$@"
