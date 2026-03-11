#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# Preserve direct env vars so caller can override env file intentionally.
HAS_BOT_TOKEN=0
HAS_CHAT_ID=0
if [[ "${TELEGRAM_BOT_TOKEN+x}" == "x" ]]; then
  HAS_BOT_TOKEN=1
  OVERRIDE_TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
fi
if [[ "${TELEGRAM_CHAT_ID+x}" == "x" ]]; then
  HAS_CHAT_ID=1
  OVERRIDE_TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID"
fi

if [[ -f "$ENV_FILE" ]]; then
  # shell style env should define exports
  source "$ENV_FILE"
fi

if (( HAS_BOT_TOKEN )); then
  TELEGRAM_BOT_TOKEN="$OVERRIDE_TELEGRAM_BOT_TOKEN"
fi
if (( HAS_CHAT_ID )); then
  TELEGRAM_CHAT_ID="$OVERRIDE_TELEGRAM_CHAT_ID"
fi

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TELEGRAM_CHAT_ID="${TELEGRAM_CHAT_ID:-}"

is_placeholder() {
  case "$1" in
    __YOUR_*|dummy|placeholder|"")
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if is_placeholder "${TELEGRAM_BOT_TOKEN:-}"; then
  echo "TELEGRAM_BOT_TOKEN이 없거나 유효하지 않습니다."
  exit 2
fi
if is_placeholder "${TELEGRAM_CHAT_ID:-}"; then
  echo "TELEGRAM_CHAT_ID가 없거나 유효하지 않습니다."
  exit 2
fi

check_ok() {
  local payload="$1"
  python3 - "$payload" <<'PY'
import json
import sys

target = sys.argv[1]

try:
    data = json.loads(target)
except Exception:
    print("응답 JSON이 유효하지 않습니다.")
    raise SystemExit(1)

if not data.get("ok", False):
    print(data.get("description", "요청이 거부되었습니다."))
    raise SystemExit(1)

result = data.get("result")
if result is None:
    raise SystemExit(0)

if isinstance(result, dict) and result.get("title"):
    print(result["title"])
else:
    print(result)
PY

  return $?
}

ME_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"
CHAT_URL="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getChat?chat_id=${TELEGRAM_CHAT_ID}"

ME_JSON="$(cd "$PROJECT_ROOT" && curl -fsS "$ME_URL")"
if ! check_ok "$ME_JSON"; then
  echo "TELEGRAM getMe 점검 실패"
  echo "$ME_JSON"
  exit 3
fi

CHAT_JSON="$(cd "$PROJECT_ROOT" && curl -fsS "$CHAT_URL")"
if ! check_ok "$CHAT_JSON"; then
  echo "TELEGRAM getChat 점검 실패"
  echo "$CHAT_JSON"
  exit 3
fi

CHAT_ID_SAFE="$(echo "$TELEGRAM_CHAT_ID" | tr -d '[:space:]')"
echo "텔레그램 점검 통과: bot=${TELEGRAM_BOT_TOKEN:0:8}..., chat=${CHAT_ID_SAFE}"
