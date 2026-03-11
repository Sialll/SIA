#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
OUT_FILE="${SIA_FULL_UNIVERSE_SNAPSHOT_PATH:-${CACHE_DIR}/full-universe-snapshot.json}"
INPUT_FILE="${SIA_FULL_UNIVERSE_INPUT_PATH:-${HOME}/.config/sia-notifier/full-universe-candidates.json}"
PROVIDER_NAME="${SIA_FULL_UNIVERSE_PROVIDER:-manual_json}"
MARKET_CAP_FLOOR="${SIA_FULL_UNIVERSE_MARKET_CAP_FLOOR_USD:-1000000000}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

mkdir -p "$CACHE_DIR"
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
"$PYTHON_BIN" "${PROJECT_ROOT}/src/sia/full_universe_collector.py" \
  --provider "$PROVIDER_NAME" \
  --input "$INPUT_FILE" \
  --out "$OUT_FILE" \
  --market-cap-floor-usd "$MARKET_CAP_FLOOR" \
  "$@"
SIA_NO_OPEN_FULL_UNIVERSE_REPORT=1 "${SCRIPT_DIR}/sia-full-universe-report.command" >/dev/null
echo "full universe 스냅샷: $OUT_FILE"
