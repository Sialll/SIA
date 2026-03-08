#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
RUN_LOG="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/qa-cooldown.log"
DB_PATH="/tmp/sia_notifier_qa_cooldown.sqlite"

TARGET_TICKERS="${SIA_COOLDOWN_TICKERS:-AAPL}"
TARGET_TICKER="${TARGET_TICKERS%%,*}"
COOLDOWN_MINUTES="${SIA_COOLDOWN_MINUTES:-30}"
MAX_ATTEMPTS="${SIA_COOLDOWN_ATTEMPTS:-8}"

if [[ -f "$ENV_FILE" ]]; then
  # shell style env should define exports
  source "$ENV_FILE"
fi

if [[ -z "$TARGET_TICKER" ]]; then
  echo "실패: TARGET 티커가 비어 있습니다."
  exit 2
fi

mkdir -p "$(dirname "$RUN_LOG")"
rm -f "$RUN_LOG" "$DB_PATH"

run_once() {
  local attempt="$1"
  cd "$REPO_DIR"
  PYTHONPATH="${REPO_DIR}/src" \
  python3 -m sia.trading_signal_notifier \
    --once \
    --dry-run \
    --tickers "$TARGET_TICKER" \
    --db-path "$DB_PATH" \
    --signal-threshold 0 \
    --max-news-per-ticker 0 \
    --cooldown-minutes "$COOLDOWN_MINUTES" \
    > "$RUN_LOG.tmp" 2>&1

  cat "$RUN_LOG.tmp" >> "$RUN_LOG"
  echo "시도 ${attempt}: $(tail -n 1 "$RUN_LOG.tmp" 2>/dev/null || true)"
}

latest_trade_signal() {
  sqlite3 "$DB_PATH" "
    SELECT signal, ts
    FROM alerts
    WHERE ticker = '${TARGET_TICKER}'
      AND signal IN ('BUY', 'SELL')
    ORDER BY ts DESC
    LIMIT 1
  " 2>/dev/null || true
}

run_attempt=0
BASE_SIGNAL=""
BASE_TS=""
while (( run_attempt < MAX_ATTEMPTS )); do
  run_attempt=$((run_attempt + 1))
  run_once "$run_attempt"
  row="$(latest_trade_signal)"
  if [[ -z "${row:-}" ]]; then
    continue
  fi
  BASE_SIGNAL="${row%|*}"
  BASE_TS="${row#*|}"
  echo "기준 신호: ${BASE_SIGNAL} / ${BASE_TS}"
  break
done

if [[ -z "${BASE_SIGNAL}" ]]; then
  echo "실패: ${MAX_ATTEMPTS}회 시도 내에 BUY/SELL 신호가 없습니다."
  echo "최신 로그:"
  tail -n 40 "$RUN_LOG"
  exit 3
fi

run_once "repeat"
if grep -q "skip due to cooldown: ticker=$TARGET_TICKER signal=$BASE_SIGNAL" "$RUN_LOG"; then
  echo "통과: 쿨다운 스킵 감지됨 (${TARGET_TICKER} / ${BASE_SIGNAL})"
  exit 0
fi

if grep -q "쿨다운 스킵" "$RUN_LOG"; then
  echo "통과: 쿨다운 스킵 감지됨 (${TARGET_TICKER} / ${BASE_SIGNAL})"
  exit 0
fi

echo "실패: ${TARGET_TICKER}/${BASE_SIGNAL}에 대한 쿨다운 스킵이 감지되지 않았습니다."
echo "로그 확인:"
tail -n 80 "$RUN_LOG"
exit 2
