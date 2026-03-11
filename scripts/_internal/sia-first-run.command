#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="${HOME}/.config/sia-notifier"
ENV_TEMPLATE="${SCRIPT_DIR}/sia-notifier-env.example"
ENV_FILE="${CONFIG_DIR}/env"
MARKET_FILE="${CONFIG_DIR}/market-selection.json"
MARKER_FILE="${CONFIG_DIR}/setup-complete"

mkdir -p "$CONFIG_DIR"
if [[ ! -f "$ENV_FILE" && -f "$ENV_TEMPLATE" ]]; then
  cp "$ENV_TEMPLATE" "$ENV_FILE"
fi
touch "$ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

CURRENT_MARKETS="$(
  python3 - "$MARKET_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
codes = ["US"]
if path.exists():
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        enabled = payload.get("enabled_markets", [])
        filtered = [code for code in enabled if code in {"US", "KR", "EU", "JP"}]
        if filtered:
            codes = filtered
    except Exception:
        pass
print(",".join(codes))
PY
)"

escape_applescript() {
  python3 - "$1" <<'PY'
import sys
print(sys.argv[1].replace("\\", "\\\\").replace('"', '\\"'))
PY
}

write_env_value() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import re
import sys
from pathlib import Path

env_path = Path(sys.argv[1]).expanduser()
key = sys.argv[2]
value = sys.argv[3]
line = f'export {key}="{value}"'
text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
pattern = re.compile(rf"(?m)^export {re.escape(key)}=.*$")
if pattern.search(text):
    text = pattern.sub(line, text)
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text += line + "\n"
env_path.write_text(text, encoding="utf-8")
PY
}

prompt_text() {
  local title="$1"
  local message="$2"
  local default_value="$3"
  local escaped_default
  escaped_default="$(escape_applescript "$default_value")"
  osascript <<OSA
try
  set userInput to text returned of (display dialog "${message}" with title "${title}" default answer "${escaped_default}" buttons {"취소", "다음"} default button "다음")
  return userInput
on error number -128
  return "__CANCEL__"
end try
OSA
}

normalize_csv() {
  python3 - "$1" <<'PY'
import re
import sys

parts = [p.strip().upper() for p in re.split(r"[\s,\n\r\t]+", sys.argv[1]) if p.strip()]
seen = []
for part in parts:
    if part not in seen:
        seen.append(part)
print(",".join(seen))
PY
}

if [[ "${SIA_FIRST_RUN_HEADLESS:-0}" == "1" ]]; then
  TOKEN_VALUE="${SIA_SETUP_TELEGRAM_BOT_TOKEN:-${TELEGRAM_BOT_TOKEN:-}}"
  CHAT_VALUE="${SIA_SETUP_TELEGRAM_CHAT_ID:-${TELEGRAM_CHAT_ID:-}}"
  DEFAULT_UNIVERSE_SELECTED="${SIA_SETUP_INCLUDE_DEFAULT_UNIVERSE:-${SIA_INCLUDE_DEFAULT_UNIVERSE:-1}}"
  ENABLED_CODES="${SIA_SETUP_ENABLED_MARKETS:-$CURRENT_MARKETS}"
  US_VALUE="$(normalize_csv "${SIA_SETUP_TICKERS_US:-${TICKERS_US:-${TICKERS:-AAPL,MSFT}}}")"
  KR_VALUE="$(normalize_csv "${SIA_SETUP_TICKERS_KR:-${TICKERS_KR:-}}")"
  EU_VALUE="$(normalize_csv "${SIA_SETUP_TICKERS_EU:-${TICKERS_EU:-}}")"
  JP_VALUE="$(normalize_csv "${SIA_SETUP_TICKERS_JP:-${TICKERS_JP:-}}")"

  write_env_value "TELEGRAM_BOT_TOKEN" "$TOKEN_VALUE"
  write_env_value "TELEGRAM_CHAT_ID" "$CHAT_VALUE"
  write_env_value "SIA_INCLUDE_DEFAULT_UNIVERSE" "$DEFAULT_UNIVERSE_SELECTED"
  write_env_value "TICKERS_US" "$US_VALUE"
  write_env_value "TICKERS_KR" "$KR_VALUE"
  write_env_value "TICKERS_EU" "$EU_VALUE"
  write_env_value "TICKERS_JP" "$JP_VALUE"
  write_env_value "TICKERS" "$US_VALUE"

  python3 - "$MARKET_FILE" "$ENABLED_CODES" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
codes = [code for code in sys.argv[2].split(",") if code]
payload = {
    "enabled_markets": codes or ["US"],
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER_FILE"
  echo "env: $ENV_FILE"
  echo "markets: $MARKET_FILE"
  echo "marker: $MARKER_FILE"
  exit 0
fi

TOKEN_VALUE="$(prompt_text "SIA 첫 실행 설정" "텔레그램 봇 토큰을 입력하세요. 아직 없으면 비워둘 수 있습니다." "${TELEGRAM_BOT_TOKEN:-}")"
[[ "$TOKEN_VALUE" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0

CHAT_VALUE="$(prompt_text "SIA 첫 실행 설정" "텔레그램 채팅 ID를 입력하세요. 아직 없으면 비워둘 수 있습니다." "${TELEGRAM_CHAT_ID:-}")"
[[ "$CHAT_VALUE" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0

DEFAULT_UNIVERSE_SELECTED="$(
  osascript <<OSA
set defaultButtonName to "기본 포함"
if "${SIA_INCLUDE_DEFAULT_UNIVERSE:-1}" is "0" then
  set defaultButtonName to "기본 제외"
end if
try
  set selectedButton to button returned of (display dialog "시가총액 10억달러 이상 기본 유니버스를 함께 포함할지 선택하세요." with title "SIA 첫 실행 설정" buttons {"취소", "기본 제외", "기본 포함"} default button defaultButtonName)
  if selectedButton is "기본 포함" then
    return "1"
  else
    return "0"
  end if
on error number -128
  return "__CANCEL__"
end try
OSA
)"
[[ "$DEFAULT_UNIVERSE_SELECTED" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0

default_items=()
IFS=',' read -r -a current_codes <<<"$CURRENT_MARKETS"
for code in "${current_codes[@]}"; do
  case "$code" in
    US) default_items+=("\"미국 (US)\"") ;;
    KR) default_items+=("\"한국 (KR)\"") ;;
    EU) default_items+=("\"유럽 (EU)\"") ;;
    JP) default_items+=("\"일본 (JP)\"") ;;
  esac
done
default_items_text="$(IFS=,; echo "${default_items[*]}")"

MARKET_SELECTION="$(
  osascript <<OSA
set marketChoices to {"미국 (US)", "한국 (KR)", "유럽 (EU)", "일본 (JP)"}
set defaultChoices to {${default_items_text}}
set picked to choose from list marketChoices with title "SIA 첫 실행 설정" with prompt "활성 시장을 선택하세요. 기본값은 미국입니다." default items defaultChoices with multiple selections allowed
if picked is false then
  return "__CANCEL__"
end if
return picked as string
OSA
)"
[[ "$MARKET_SELECTION" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0

ENABLED_CODES="$(
  python3 - "$MARKET_SELECTION" <<'PY'
import re
import sys

raw = sys.argv[1]
codes = re.findall(r"\(([A-Z]{2})\)", raw)
filtered = [code for code in codes if code in {"US", "KR", "EU", "JP"}]
print(",".join(filtered or ["US"]))
PY
)"

US_VALUE=""
KR_VALUE=""
EU_VALUE=""
JP_VALUE=""

if [[ ",$ENABLED_CODES," == *",US,"* ]]; then
  US_VALUE="$(prompt_text "SIA 첫 실행 설정" "미국 시장 관심 종목을 쉼표로 입력하세요. 비워두면 기본 유니버스만 사용합니다." "${TICKERS_US:-${TICKERS:-AAPL,MSFT}}")"
  [[ "$US_VALUE" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0
fi
if [[ ",$ENABLED_CODES," == *",KR,"* ]]; then
  KR_VALUE="$(prompt_text "SIA 첫 실행 설정" "한국 시장 관심 종목을 쉼표로 입력하세요. 비워두면 기본 유니버스만 사용합니다." "${TICKERS_KR:-}")"
  [[ "$KR_VALUE" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0
fi
if [[ ",$ENABLED_CODES," == *",EU,"* ]]; then
  EU_VALUE="$(prompt_text "SIA 첫 실행 설정" "유럽 시장 관심 종목을 쉼표로 입력하세요. 비워두면 기본 유니버스만 사용합니다." "${TICKERS_EU:-}")"
  [[ "$EU_VALUE" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0
fi
if [[ ",$ENABLED_CODES," == *",JP,"* ]]; then
  JP_VALUE="$(prompt_text "SIA 첫 실행 설정" "일본 시장 관심 종목을 쉼표로 입력하세요. 비워두면 기본 유니버스만 사용합니다." "${TICKERS_JP:-}")"
  [[ "$JP_VALUE" == "__CANCEL__" ]] && echo "첫 실행 설정이 취소되었습니다." && exit 0
fi

US_VALUE="$(normalize_csv "$US_VALUE")"
KR_VALUE="$(normalize_csv "$KR_VALUE")"
EU_VALUE="$(normalize_csv "$EU_VALUE")"
JP_VALUE="$(normalize_csv "$JP_VALUE")"

write_env_value "TELEGRAM_BOT_TOKEN" "$TOKEN_VALUE"
write_env_value "TELEGRAM_CHAT_ID" "$CHAT_VALUE"
write_env_value "SIA_INCLUDE_DEFAULT_UNIVERSE" "$DEFAULT_UNIVERSE_SELECTED"
write_env_value "TICKERS_US" "$US_VALUE"
write_env_value "TICKERS_KR" "$KR_VALUE"
write_env_value "TICKERS_EU" "$EU_VALUE"
write_env_value "TICKERS_JP" "$JP_VALUE"
write_env_value "TICKERS" "$US_VALUE"

python3 - "$MARKET_FILE" "$ENABLED_CODES" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
codes = [code for code in sys.argv[2].split(",") if code]
payload = {
    "enabled_markets": codes or ["US"],
    "updated_at": datetime.now(timezone.utc).isoformat(),
}
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARKER_FILE"

osascript <<OSA
display dialog "첫 실행 설정이 저장되었습니다. 이제 메인 화면을 엽니다." with title "SIA 첫 실행 설정" buttons {"확인"} default button "확인"
OSA

echo "env: $ENV_FILE"
echo "markets: $MARKET_FILE"
echo "marker: $MARKER_FILE"
