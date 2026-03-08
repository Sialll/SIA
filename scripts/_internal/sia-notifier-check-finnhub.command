#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CHECK_TIMEOUT=12

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env 파일이 없습니다: $ENV_FILE"
  echo "실행: cp ${SCRIPT_DIR}/sia-notifier-env.example ~/.config/sia-notifier/env"
  exit 2
fi

# shell style env should define exports
source "$ENV_FILE"

if [[ -z "${FINNHUB_API_KEY:-}" ]]; then
  echo "FINNHUB_API_KEY가 없습니다."
  exit 3
fi

if [[ "$FINNHUB_API_KEY" == "__YOUR_FINNHUB_API_KEY__" || "$FINNHUB_API_KEY" == "__YOUR_*" || "$FINNHUB_API_KEY" == "dummy" || "$FINNHUB_API_KEY" == "placeholder" ]]; then
  echo "FINNHUB_API_KEY 값이 플레이스홀더입니다."
  exit 3
fi

if ! [[ "$FINNHUB_API_KEY" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "FINNHUB_API_KEY에 유효하지 않은 문자가 있습니다."
  exit 3
fi

if command -v python3 >/dev/null 2>&1; then
  :
else
  echo "python3를 찾을 수 없습니다. 이 점검은 응답 본문 검증을 위해 python3가 필요합니다."
  exit 3
fi
if command -v curl >/dev/null 2>&1; then
  :
else
  echo "curl을 찾을 수 없습니다. Finnhub API 호출을 할 수 없습니다."
  exit 3
fi

cd "$REPO_DIR"
TO_TS=$(date +%s)
FROM_TS=$((TO_TS - 86400))
QUOTE_URL="https://finnhub.io/api/v1/quote?symbol=AAPL&token=${FINNHUB_API_KEY}"
CANDLE_URL="https://finnhub.io/api/v1/stock/candle?symbol=AAPL&resolution=D&from=${FROM_TS}&to=${TO_TS}&token=${FINNHUB_API_KEY}"

RESP_FILE="$(mktemp)"
if ! HTTP_CODE=$(curl -sS --max-time "$CHECK_TIMEOUT" -w "%{http_code}" -o "$RESP_FILE" "$QUOTE_URL"); then
  echo "finnhub 엔드포인트 요청 실패"
  rm -f "$RESP_FILE"
  exit 3
fi

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "finnhub 응답 실패: HTTP $HTTP_CODE"
  cat "$RESP_FILE" 2>/dev/null || true
  rm -f "$RESP_FILE"
  exit 3
fi

PY_STATUS=0
python3 - "$RESP_FILE" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    raw = f.read()
try:
    data = json.loads(raw)
except Exception as exc:
    print(f"JSON 응답 파싱 실패: {exc}")
    sys.exit(2)

if data.get("c"):
    print("FINNHUB_API_KEY 유효")
    sys.exit(0)

if 'error' in data and data['error']:
    print(f"FINNHUB API 오류: {data['error']}")
    sys.exit(2)

print(f"예상치 못한 응답: {raw[:300]}")
sys.exit(2)
PY
PY_STATUS=$?
rm -f "$RESP_FILE"
if [[ $PY_STATUS -ne 0 ]]; then
  exit $PY_STATUS
fi

if ! HTTP_CODE=$(curl -sS --max-time "$CHECK_TIMEOUT" -w "%{http_code}" -o "$RESP_FILE" "$CANDLE_URL"); then
  echo "finnhub candle 엔드포인트 요청 실패"
  rm -f "$RESP_FILE"
  exit 3
fi

if [[ "$HTTP_CODE" == "200" ]]; then
  python3 - "$RESP_FILE" <<'PY'
import json
import sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    raw = f.read()
try:
    data = json.loads(raw)
except Exception as exc:
    print(f"candle 응답 파싱 실패: {exc}")
    sys.exit(2)

if data.get("s") == "ok" and data.get("c"):
    print("finnhub candle 엔드포인트 정상")
    sys.exit(0)

if "error" in data and data["error"] and "access to this resource" in str(data["error"]).lower():
    print("candle endpoint 접근이 제한됨: 무료 플랜은 quote는 가능하지만 stock/candle 접근이 제한될 수 있습니다.")
    print("차트 신호를 사용하지 않거나 Finnhub 플랜을 업그레이드하세요.")
    sys.exit(0)

print(f"예상치 못한 캔들 응답: {raw[:300]}")
sys.exit(0)
PY
  PY_STATUS=$?
  rm -f "$RESP_FILE"
  if [[ $PY_STATUS -ne 0 ]]; then
    exit $PY_STATUS
  fi
elif [[ "$HTTP_CODE" == "403" ]]; then
  echo "finnhub 캔들 엔드포인트가 403으로 차단됨. quote 엔드포인트는 유효합니다."
  echo "차트 신호를 사용하지 않거나 Finnhub 플랜을 업그레이드하세요."
else
  echo "finnhub candle 요청 실패: HTTP $HTTP_CODE"
  cat "$RESP_FILE" 2>/dev/null || true
  rm -f "$RESP_FILE"
  exit 3
fi

rm -f "$RESP_FILE"
echo "FINNHUB 선점검 완료."
