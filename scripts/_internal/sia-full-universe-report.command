#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
SNAPSHOT_FILE="${SIA_FULL_UNIVERSE_SNAPSHOT_PATH:-${CACHE_DIR}/full-universe-snapshot.json}"
OUT_FILE="${SIA_FULL_UNIVERSE_REPORT_PATH:-${CACHE_DIR}/full-universe-report.html}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

mkdir -p "$CACHE_DIR"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
"$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/full_universe_report.py" --snapshot "$SNAPSHOT_FILE" --out "$OUT_FILE" "$@"
if [[ "${SIA_NO_OPEN_FULL_UNIVERSE_REPORT:-0}" != "1" ]]; then
  open "$OUT_FILE"
fi
echo "full universe 리포트: $OUT_FILE"
