#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
REPORT_FILE="${CACHE_DIR}/position-backtest-report.html"
DEFAULT_DB="${HOME}/sia-notifier/trading_signal_notifier.sqlite"
PYTHON_BIN="${PYTHON_BIN:-python3}"

mkdir -p "$CACHE_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

DB_PATH="${SIGNAL_DB_PATH:-$DEFAULT_DB}"
HOLD_TICKS="${POSITION_BACKTEST_HOLD_TICKS:-3}"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "파이썬 인터프리터를 찾을 수 없습니다: ${PYTHON_BIN}" >&2
  exit 3
fi

EXTRA_ARGS=()
if [[ "$#" -gt 0 ]]; then
  EXTRA_ARGS=("$@")
fi
HAS_HOLD_TICKS=0
if [[ "${#EXTRA_ARGS[@]}" -gt 0 ]]; then
  for arg in "${EXTRA_ARGS[@]}"; do
    if [[ "$arg" == "--hold-ticks" ]]; then
      HAS_HOLD_TICKS=1
      break
    fi
  done
fi

CMD=(
  "$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/position_backtest_report.py"
  --db-path "$DB_PATH"
  --output "$REPORT_FILE"
)

if [[ "$HAS_HOLD_TICKS" -eq 0 ]]; then
  CMD+=(--hold-ticks "$HOLD_TICKS")
fi

if [[ "${#EXTRA_ARGS[@]}" -gt 0 ]]; then
  CMD+=("${EXTRA_ARGS[@]}")
fi
"${CMD[@]}"

if [[ "${SIA_NO_OPEN_POSITION_BACKTEST:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  open "$REPORT_FILE" >/dev/null 2>&1 || true
fi

echo "포지션 백테스트 리포트: $REPORT_FILE"
