#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
RUN_LOG="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/run.log"
RUN_MODE="${1:-balanced}"
RUN_SCRIPT="${REPO_DIR}/scripts/sia-notifier-launch.command"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE"
  echo "copy from template: cp scripts/sia-notifier-env.example ~/.config/sia-notifier/env"
  exit 2
fi

# shell style env should define exports
source "$ENV_FILE"
export SIA_DRY_RUN="${SIA_DRY_RUN:-0}"

if [[ "${SIA_DRY_RUN}" == "1" ]]; then
  required_vars=(TICKERS)
else
  required_vars=(TICKERS TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID FINNHUB_API_KEY)
fi
for var in "${required_vars[@]}"; do
  value="${!var:-}"
  if [[ -z "$value" || "$value" == "__YOUR_"* || "$value" == "dummy" || "$value" == "placeholder" ]]; then
    echo "invalid or missing: $var"
    exit 3
  fi
done

if [[ "${SIA_DRY_RUN}" != "0" ]]; then
  echo "SIA_DRY_RUN=${SIA_DRY_RUN} (switch to 0 for live run)"
fi

cd "$REPO_DIR"
if [[ -f "$RUN_SCRIPT" ]]; then
  "$RUN_SCRIPT" "$RUN_MODE"
else
  echo "missing runner: $RUN_SCRIPT" >&2
  exit 3
fi
if [[ -f "$RUN_LOG" ]]; then
  tail -n 60 "$RUN_LOG"
else
  echo "run log not found: $RUN_LOG"
fi
