#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
RUN_LOG="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/run.log"
DB_PATH="/tmp/sia_notifier_telegram_reject.sqlite"
TARGET_TICKERS="${SIA_QA_TICKERS:-AAPL}"
TARGET_TICKER="${TARGET_TICKERS%%,*}"
BAD_TOKEN="${SIA_BAD_TELEGRAM_TOKEN:-123456789:ABCDEF-fake-token}"
BAD_CHAT_ID="${SIA_BAD_TELEGRAM_CHAT_ID:-000000}"
MAX_ATTEMPTS="${SIA_QA_ATTEMPTS:-6}"

if [[ -f "$ENV_FILE" ]]; then
  # shell style env should define exports
  source "$ENV_FILE"
fi

if [[ "${SIA_DRY_RUN:-0}" == "1" ]]; then
  echo "이 점검은 무효한 텔레그램 토큰을 사용하므로 SIA_DRY_RUN=1은 무시되고, mock 가격으로 드라이런 모드로 강제 실행됩니다."
fi

mkdir -p "$(dirname "$DB_PATH")"
rm -f "$DB_PATH"

run_once() {
  local attempt="$1"
  rm -f "$DB_PATH"
  cd "$REPO_DIR"
  PYTHONPATH="${REPO_DIR}/src" \
  SIGNAL_DB_PATH="$DB_PATH" \
  SIGNAL_THRESHOLD="0" \
  MAX_NEWS_PER_TICKER="0" \
  SIGNAL_COOLDOWN_MINUTES="1" \
  TELEGRAM_BOT_TOKEN="$BAD_TOKEN" \
  TELEGRAM_CHAT_ID="$BAD_CHAT_ID" \
  SIA_NO_OLLAMA="1" \
    python3 -m sia.trading_signal_notifier \
      --once \
      --dry-run \
      --tickers "$TARGET_TICKER" \
      --signal-threshold 0 \
      --max-news-per-ticker 0 \
      --cooldown-minutes 1 \
      --db-path "$DB_PATH" \
      > "$RUN_LOG" 2>&1

  echo "시도 ${attempt}: $(tail -n 1 "$RUN_LOG" 2>/dev/null || true)"
}

check_reject() {
  if [[ -f "$RUN_LOG" ]] && rg -q "텔레그램 API 거절|telegram API rejected request" "$RUN_LOG"; then
    echo "통과: 텔레그램 거절 경로가 감지되었습니다."
    return 0
  fi
  return 1
}

latest_signal() {
  sqlite3 "$DB_PATH" "
    SELECT signal, ts
    FROM alerts
    WHERE ticker = '$TARGET_TICKER' AND signal IN ('BUY', 'SELL')
    ORDER BY ts DESC
    LIMIT 1
  " 2>/dev/null || true
}

nonhold_count=0
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  run_once "$attempt"
  signal_row="$(latest_signal)"
  if [[ -n "$signal_row" ]]; then
    nonhold_count=1
    if check_reject; then
      echo "검출 라인:"
      rg -n "텔레그램 API 거절|telegram API rejected request" "$RUN_LOG"
      exit 0
    fi
  fi
done

if [[ "$nonhold_count" == "0" ]]; then
  echo "실패: ${MAX_ATTEMPTS}회 시도 내에 BUY/SELL 신호가 생성되지 않았습니다."
  echo "팁: SIGNAL_THRESHOLD를 낮춰 보세요 (--signal-threshold)."
  exit 3
fi

echo "실패: BUY/SELL 신호는 생성되었지만 텔레그램 거절 로그를 찾지 못했습니다."
echo "최근 신호 행: ${signal_row:-<none>}"
echo "최근 로그:"
tail -n 30 "$RUN_LOG"
exit 2
