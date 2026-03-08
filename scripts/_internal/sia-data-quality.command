#!/bin/zsh
set -euo pipefail

ROOT="/Users/dohyeon/Documents/Playground/SIA"
ENV_FILE="${HOME}/.config/sia-notifier/env"

if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
fi

DB_PATH="${SIGNAL_DB_PATH:-$HOME/sia-notifier/trading_signal_notifier.sqlite}"
CACHE_DIR="${HOME}/Library/Caches/sia-notifier"
OUTPUT_PATH="$CACHE_DIR/data-quality-report.html"

mkdir -p "$CACHE_DIR"
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}" \
  python3 -m sia.data_quality_report \
  --db-path "$DB_PATH" \
  --output "$OUTPUT_PATH"

echo "데이터 품질 리포트: $OUTPUT_PATH"

if [[ "${SIA_NO_OPEN_DATA_QUALITY:-0}" != "1" ]]; then
  open "$OUTPUT_PATH"
fi
