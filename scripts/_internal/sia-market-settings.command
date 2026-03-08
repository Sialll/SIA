#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${HOME}/.config/sia-notifier/env"
if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

CONFIG_PATH="${SIA_MARKET_SELECTION_FILE:-$HOME/.config/sia-notifier/market-selection.json}"
mkdir -p "$(dirname "$CONFIG_PATH")"

CURRENT_CODES="$(
  python3 - "$CONFIG_PATH" <<'PY'
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

default_items=()
IFS=',' read -r -a current_codes <<<"$CURRENT_CODES"
for code in "${current_codes[@]}"; do
  case "$code" in
    US) default_items+=("\"미국 (US)\"") ;;
    KR) default_items+=("\"한국 (KR)\"") ;;
    EU) default_items+=("\"유럽 (EU)\"") ;;
    JP) default_items+=("\"일본 (JP)\"") ;;
  esac
done
default_items_text="$(IFS=,; echo "${default_items[*]}")"

selection="$(
osascript <<OSA
set marketChoices to {"미국 (US)", "한국 (KR)", "유럽 (EU)", "일본 (JP)"}
set defaultChoices to {${default_items_text}}
set picked to choose from list marketChoices with title "SIA 시장 설정" with prompt "활성 시장을 선택하세요. 뉴스는 연중무휴로 돌고, 가격/신호는 선택된 시장의 장 시간에만 수집됩니다." default items defaultChoices with multiple selections allowed
if picked is false then
  return "__CANCEL__"
end if
return picked as string
OSA
)"

if [[ "$selection" == "__CANCEL__" ]]; then
  echo "시장 설정이 취소되었습니다."
  exit 0
fi

ENABLED_CODES="$(
  python3 - "$selection" <<'PY'
import re
import sys

raw = sys.argv[1]
codes = re.findall(r"\(([A-Z]{2})\)", raw)
filtered = [code for code in codes if code in {"US", "KR", "EU", "JP"}]
print(",".join(filtered or ["US"]))
PY
)"

python3 - "$CONFIG_PATH" "$ENABLED_CODES" <<'PY'
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
print(path)
PY

echo "활성 시장: ${ENABLED_CODES}"
echo "설정 파일: ${CONFIG_PATH}"
echo "참고: TICKERS_KR / TICKERS_EU / TICKERS_JP가 비어 있으면 해당 시장을 켜도 수집 대상은 없습니다."
