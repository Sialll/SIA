#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env 파일이 없습니다: $ENV_FILE"
  echo "템플릿을 복사하세요: cp scripts/sia-notifier-env.example ~/.config/sia-notifier/env"
  exit 2
fi

# Preserve direct env vars so caller can override env file intentionally.
HAS_TICKERS=0
HAS_FINNHUB=0
HAS_TELEGRAM_BOT_TOKEN=0
HAS_TELEGRAM_CHAT_ID=0

if [[ "${TICKERS+x}" == "x" ]]; then
  HAS_TICKERS=1
  OVERRIDE_TICKERS="$TICKERS"
fi
if [[ "${FINNHUB_API_KEY+x}" == "x" ]]; then
  HAS_FINNHUB=1
  OVERRIDE_FINNHUB_API_KEY="$FINNHUB_API_KEY"
fi
if [[ "${TELEGRAM_BOT_TOKEN+x}" == "x" ]]; then
  HAS_TELEGRAM_BOT_TOKEN=1
  OVERRIDE_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
fi
if [[ "${TELEGRAM_CHAT_ID+x}" == "x" ]]; then
  HAS_TELEGRAM_CHAT_ID=1
  OVERRIDE_TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID"
fi

# shell style env should define exports
source "$ENV_FILE"

if (( HAS_TICKERS )); then
  TICKERS="$OVERRIDE_TICKERS"
fi
if (( HAS_FINNHUB )); then
  FINNHUB_API_KEY="$OVERRIDE_FINNHUB_API_KEY"
fi
if (( HAS_TELEGRAM_BOT_TOKEN )); then
  TELEGRAM_BOT_TOKEN="$OVERRIDE_TELEGRAM_BOT_TOKEN"
fi
if (( HAS_TELEGRAM_CHAT_ID )); then
  TELEGRAM_CHAT_ID="$OVERRIDE_TELEGRAM_CHAT_ID"
fi

if [[ -z "${TICKERS:-}" || "${TICKERS}" == "__YOUR_"* || "${TICKERS}" == "dummy" || "${TICKERS}" == "placeholder" ]]; then
  echo "TICKERS가 없거나 유효하지 않습니다."
  exit 2
fi

cd "$REPO_DIR"

echo "== 사전 점검: finnhub 점검 =="
if [[ "${FINNHUB_API_KEY:-}" == "__YOUR_FINNHUB_API_KEY__" || "${FINNHUB_API_KEY:-}" == "dummy" || "${FINNHUB_API_KEY:-}" == "placeholder" ]]; then
  echo "finnhub 점검 건너뜀: key가 플레이스홀더입니다."
else
  if ! ./scripts/_internal/sia-notifier-check-finnhub.command; then
    echo "finnhub 점검 실패"
    exit 3
  fi
fi

echo "== 사전 점검: telegram 점검 =="
if [[ "${TELEGRAM_BOT_TOKEN:-}" == "__YOUR_BOT_TOKEN__" || "${TELEGRAM_CHAT_ID:-}" == "__YOUR_CHAT_ID__" || "${TELEGRAM_BOT_TOKEN:-}" == "dummy" || "${TELEGRAM_CHAT_ID:-}" == "dummy" || "${TELEGRAM_BOT_TOKEN:-}" == "placeholder" || "${TELEGRAM_CHAT_ID:-}" == "placeholder" ]]; then
  echo "telegram 점검 건너뜀: 인증값이 플레이스홀더 또는 누락"
else
  if ! ./scripts/_internal/sia-notifier-check-telegram.command; then
    echo "telegram 점검 실패"
    exit 3
  fi
fi

echo "== 사전 점검: dry-run notifier 점검 =="
export PYTHONPATH="${REPO_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
python3 -m sia.trading_signal_notifier \
  --once \
  --dry-run
echo "사전 점검 완료"
