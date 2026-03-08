#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
OUT_FILE="${SIA_UNIVERSE_SNAPSHOT_PATH:-${CACHE_DIR}/universe-snapshot.json}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

mkdir -p "$CACHE_DIR"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
"$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/universe_collector.py" --out "$OUT_FILE" "$@"
SIA_NO_OPEN_UNIVERSE_REPORT=1 "${SCRIPT_DIR}/sia-universe-report.command" >/dev/null
echo "유니버스 스냅샷: $OUT_FILE"
