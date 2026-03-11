#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.config/sia-notifier/env"
HISTORY_FILE="${HOME}/.config/sia-notifier/ticker-add-history.jsonl"
mkdir -p "$(dirname "$ENV_FILE")"
touch "$ENV_FILE"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

NONINTERACTIVE_MODE=""
NONINTERACTIVE_QUICK_INPUT=""
NONINTERACTIVE_MARKET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quick-add)
      NONINTERACTIVE_MODE="quick_add"
      NONINTERACTIVE_QUICK_INPUT="${2:-}"
      shift 2
      ;;
    --quick-remove)
      NONINTERACTIVE_MODE="quick_remove"
      NONINTERACTIVE_QUICK_INPUT="${2:-}"
      shift 2
      ;;
    --bulk-set)
      NONINTERACTIVE_MODE="bulk_set_market"
      NONINTERACTIVE_MARKET="${2:-}"
      NONINTERACTIVE_QUICK_INPUT="${3:-}"
      shift 3
      ;;
    *)
      echo "알 수 없는 옵션입니다: $1" >&2
      exit 2
      ;;
  esac
done

prompt_mode() {
  osascript <<'OSA'
set launcherChoices to {"빠른 추가", "전체 수정"}
set picked to choose from list launcherChoices with title "SIA 관심 종목 설정" with prompt "원하는 입력 방식을 선택하세요." default items {"빠른 추가"}
if picked is false then
  return "__CANCEL__"
end if
return item 1 of picked
OSA
}

prompt_quick_add() {
  osascript <<'OSA'
set promptText to "예시처럼 입력하면 바로 추가됩니다." & return & return & "티커 추가 : [ ASTS ]" & return & "티커 추가 : [ ASTS, NVDA, 005930.KS ]"
set dialogTitle to "SIA 티커 빠른 추가"
try
  set userInput to text returned of (display dialog promptText with title dialogTitle default answer "티커 추가 : [ ]" buttons {"취소", "추가"} default button "추가")
  return userInput
on error number -128
  return "__CANCEL__"
end try
OSA
}

prompt_default_universe() {
  local current_value="$1"
  osascript <<OSA
set currentValue to "${current_value}"
set promptText to "시가총액 10억달러(약 1.4조원) 이상 기본 universe를 함께 포함할지 선택하세요."
set dialogTitle to "SIA 기본 유니버스 설정"
set defaultButtonName to "기본 포함"
if currentValue is "0" then
  set defaultButtonName to "기본 제외"
end if
try
  set selectedButton to button returned of (display dialog promptText with title dialogTitle buttons {"취소", "기본 제외", "기본 포함"} default button defaultButtonName)
  if selectedButton is "기본 포함" then
    return "1"
  else if selectedButton is "기본 제외" then
    return "0"
  end if
  return "__CANCEL__"
on error number -128
  return "__CANCEL__"
end try
OSA
}

prompt_tickers() {
  local market_label="$1"
  local default_value="$2"
  osascript <<OSA
set promptText to "${market_label} 시장 기본 1B+ universe에 추가할 티커를 쉼표로 구분해서 입력하세요. 비워두면 기본 universe만 사용합니다."
set dialogTitle to "SIA 시장별 티커 설정"
set defaultAnswer to "${default_value}"
try
  set userInput to text returned of (display dialog promptText with title dialogTitle default answer defaultAnswer buttons {"취소", "확인"} default button "확인")
  return userInput
on error number -128
  return "__CANCEL__"
end try
OSA
}

MODE="${NONINTERACTIVE_MODE:-}"
if [[ -z "$MODE" ]]; then
  MODE="$(prompt_mode)"
  [[ "$MODE" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0
fi

if [[ "$MODE" == "빠른 추가" || "$MODE" == "quick_add" || "$MODE" == "quick_remove" || "$MODE" == "bulk_set_market" ]]; then
  QUICK_INPUT="${NONINTERACTIVE_QUICK_INPUT:-}"
  if [[ -z "$QUICK_INPUT" ]]; then
    QUICK_INPUT="$(prompt_quick_add)"
    [[ "$QUICK_INPUT" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0
  fi

  python3 - "$ENV_FILE" "$HISTORY_FILE" "$MODE" "$NONINTERACTIVE_MARKET" "$QUICK_INPUT" "${TICKERS_US:-${TICKERS:-}}" "${TICKERS_KR:-}" "${TICKERS_EU:-}" "${TICKERS_JP:-}" "${SIA_INCLUDE_DEFAULT_UNIVERSE:-1}" <<'PY'
import json
import re
import sys
import time
from pathlib import Path


env_path = Path(sys.argv[1]).expanduser()
history_path = Path(sys.argv[2]).expanduser()
mode = sys.argv[3].strip() or "quick_add"
target_market = sys.argv[4].strip().upper()
raw_input = sys.argv[5].strip()
existing = {
    "TICKERS_US": sys.argv[6].strip(),
    "TICKERS_KR": sys.argv[7].strip(),
    "TICKERS_EU": sys.argv[8].strip(),
    "TICKERS_JP": sys.argv[9].strip(),
    "SIA_INCLUDE_DEFAULT_UNIVERSE": sys.argv[10].strip() or "1",
}


def infer_market(ticker: str) -> str:
    upper = ticker.upper()
    if upper.endswith((".KS", ".KQ")):
        return "KR"
    if upper.endswith((".T", ".JP")):
        return "JP"
    if upper.endswith((".AS", ".BR", ".CO", ".DE", ".HE", ".L", ".MC", ".MI", ".OL", ".PA", ".ST", ".SW", ".VI")):
        return "EU"
    return "US"


def parse_quick_add(text: str) -> list[str]:
    bracket_match = re.search(r"\[(.*?)\]", text)
    if bracket_match:
        payload = bracket_match.group(1)
    elif ":" in text:
        payload = text.split(":", 1)[1]
    else:
        payload = text
    parts = [piece.strip().upper() for piece in re.split(r"[\s,]+", payload) if piece.strip()]
    return [piece for piece in parts if piece not in {"티커", "추가"}]


def parse_bulk_tickers(text: str) -> list[str]:
    parts = [piece.strip().upper() for piece in re.split(r"[\s,\n\r\t]+", text) if piece.strip()]
    return list(dict.fromkeys(parts))


def unique_append(current_csv: str, additions: list[str]) -> str:
    values = [item.strip().upper() for item in current_csv.split(",") if item.strip()]
    seen = set(values)
    for item in additions:
        if item not in seen:
            values.append(item)
            seen.add(item)
    return ",".join(values)


def remove_items(current_csv: str, removals: list[str]) -> str:
    removal_set = {item.strip().upper() for item in removals if item.strip()}
    values = [item.strip().upper() for item in current_csv.split(",") if item.strip()]
    kept = [item for item in values if item not in removal_set]
    return ",".join(kept)


tickers = parse_quick_add(raw_input)
if mode == "bulk_set_market":
    tickers = parse_bulk_tickers(raw_input)
if not tickers and mode != "bulk_set_market":
    print("추가할 티커를 찾지 못했습니다.", file=sys.stderr)
    raise SystemExit(1)
if mode == "bulk_set_market" and target_market not in {"US", "KR", "EU", "JP"}:
    print("시장 코드는 US/KR/EU/JP 중 하나여야 합니다.", file=sys.stderr)
    raise SystemExit(1)

grouped: dict[str, list[str]] = {"US": [], "KR": [], "EU": [], "JP": []}
if mode == "bulk_set_market":
    grouped[target_market] = tickers
else:
    for ticker in tickers:
        grouped[infer_market(ticker)].append(ticker)

values = dict(existing)
for market_key in ("US", "KR", "EU", "JP"):
    env_key = f"TICKERS_{market_key}"
    if mode == "bulk_set_market":
        if market_key == target_market:
            values[env_key] = ",".join(grouped[market_key])
    elif mode == "quick_remove":
        values[env_key] = remove_items(values.get(env_key, ""), grouped[market_key])
    else:
        values[env_key] = unique_append(values.get(env_key, ""), grouped[market_key])
values["TICKERS"] = values["TICKERS_US"]

text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
for key, value in values.items():
    line = f'export {key}="{value}"'
    pattern = re.compile(rf"(?m)^export {re.escape(key)}=.*$")
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"

env_path.write_text(text, encoding="utf-8")
history_path.parent.mkdir(parents=True, exist_ok=True)
history_payload = {
    "ts": int(time.time()),
    "mode": mode,
    "input": raw_input,
    "target_market": target_market,
    "items": [{"market": market_key, "ticker": ticker} for market_key in ("US", "KR", "EU", "JP") for ticker in grouped[market_key]],
}
with history_path.open("a", encoding="utf-8") as fp:
    fp.write(json.dumps(history_payload, ensure_ascii=False) + "\n")
print(env_path)
for market_key in ("US", "KR", "EU", "JP"):
    additions = grouped[market_key]
    if additions:
        if mode == "quick_remove":
            action = "삭제"
        elif mode == "bulk_set_market":
            action = "일괄 설정"
        else:
            action = "추가"
        print(f"{market_key} {action}: {', '.join(additions)}")
print(f"SIA_INCLUDE_DEFAULT_UNIVERSE={values['SIA_INCLUDE_DEFAULT_UNIVERSE']}")
PY

  if [[ "$MODE" == "quick_remove" ]]; then
    echo "빠른 티커 삭제가 저장되었습니다: ${ENV_FILE}"
    echo "참고: 예시 형식은 '티커 삭제 : [ ASTS ]' 입니다."
  elif [[ "$MODE" == "bulk_set_market" ]]; then
    echo "시장별 티커 일괄 설정이 저장되었습니다: ${ENV_FILE}"
    echo "참고: 여러 줄 또는 쉼표로 붙여넣으면 해당 시장 티커 목록을 그대로 덮어씁니다."
  else
    echo "빠른 티커 추가가 저장되었습니다: ${ENV_FILE}"
    echo "참고: 예시 형식은 '티커 추가 : [ ASTS ]' 입니다."
  fi
  exit 0
fi

DEFAULT_UNIVERSE_VALUE="$(prompt_default_universe "${SIA_INCLUDE_DEFAULT_UNIVERSE:-1}")"
[[ "$DEFAULT_UNIVERSE_VALUE" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0

US_VALUE="$(prompt_tickers "미국" "${TICKERS_US:-${TICKERS:-}}")"
[[ "$US_VALUE" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0
KR_VALUE="$(prompt_tickers "한국" "${TICKERS_KR:-}")"
[[ "$KR_VALUE" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0
EU_VALUE="$(prompt_tickers "유럽" "${TICKERS_EU:-}")"
[[ "$EU_VALUE" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0
JP_VALUE="$(prompt_tickers "일본" "${TICKERS_JP:-}")"
[[ "$JP_VALUE" == "__CANCEL__" ]] && echo "티커 설정이 취소되었습니다." && exit 0

python3 - "$ENV_FILE" "$HISTORY_FILE" "$DEFAULT_UNIVERSE_VALUE" "$US_VALUE" "$KR_VALUE" "$EU_VALUE" "$JP_VALUE" <<'PY'
import json
import re
import sys
import time
from pathlib import Path

env_path = Path(sys.argv[1]).expanduser()
history_path = Path(sys.argv[2]).expanduser()
values = {
    "SIA_INCLUDE_DEFAULT_UNIVERSE": sys.argv[3].strip() or "1",
    "TICKERS_US": sys.argv[4].strip(),
    "TICKERS_KR": sys.argv[5].strip(),
    "TICKERS_EU": sys.argv[6].strip(),
    "TICKERS_JP": sys.argv[7].strip(),
}
values["TICKERS"] = values["TICKERS_US"]

text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
for key, value in values.items():
    line = f'export {key}="{value}"'
    pattern = re.compile(rf'(?m)^export {re.escape(key)}=.*$')
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"

env_path.write_text(text, encoding="utf-8")
history_path.parent.mkdir(parents=True, exist_ok=True)
history_payload = {
    "ts": int(time.time()),
    "mode": "bulk_edit",
    "include_default_universe": values["SIA_INCLUDE_DEFAULT_UNIVERSE"],
    "by_market": {
        "US": [item.strip().upper() for item in values["TICKERS_US"].split(",") if item.strip()],
        "KR": [item.strip().upper() for item in values["TICKERS_KR"].split(",") if item.strip()],
        "EU": [item.strip().upper() for item in values["TICKERS_EU"].split(",") if item.strip()],
        "JP": [item.strip().upper() for item in values["TICKERS_JP"].split(",") if item.strip()],
    },
}
with history_path.open("a", encoding="utf-8") as fp:
    fp.write(json.dumps(history_payload, ensure_ascii=False) + "\n")
print(env_path)
print(f"SIA_INCLUDE_DEFAULT_UNIVERSE={values['SIA_INCLUDE_DEFAULT_UNIVERSE']}")
for key in ("TICKERS_US", "TICKERS_KR", "TICKERS_EU", "TICKERS_JP"):
    print(f"{key}={values[key]}")
PY

echo "시장별 티커 설정이 저장되었습니다: ${ENV_FILE}"
if [[ "$DEFAULT_UNIVERSE_VALUE" == "1" ]]; then
  echo "참고: 입력한 값은 기본 1B+ universe에 추가됩니다."
else
  echo "참고: 현재는 기본 1B+ universe를 제외하고 입력 티커만 사용합니다."
fi
echo "참고: 활성 시장은 별도로 /Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Settings.command 에서 체크해야 적용됩니다."
