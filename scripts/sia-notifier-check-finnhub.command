#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CHECK_TIMEOUT=12

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing env file: $ENV_FILE"
  echo "run: cp ${SCRIPT_DIR}/sia-notifier-env.example ~/.config/sia-notifier/env"
  exit 2
fi

# shell style env should define exports
source "$ENV_FILE"

if [[ -z "${FINNHUB_API_KEY:-}" ]]; then
  echo "FINNHUB_API_KEY is missing."
  exit 3
fi

if [[ "$FINNHUB_API_KEY" == "__YOUR_FINNHUB_API_KEY__" || "$FINNHUB_API_KEY" == "__YOUR_*" || "$FINNHUB_API_KEY" == "dummy" || "$FINNHUB_API_KEY" == "placeholder" ]]; then
  echo "FINNHUB_API_KEY has placeholder value."
  exit 3
fi

if ! [[ "$FINNHUB_API_KEY" =~ ^[A-Za-z0-9_-]+$ ]]; then
  echo "FINNHUB_API_KEY contains invalid characters."
  exit 3
fi

if command -v python3 >/dev/null 2>&1; then
  :
else
  echo "python3 not found. this check needs python3 to validate response body."
  exit 3
fi
if command -v curl >/dev/null 2>&1; then
  :
else
  echo "curl not found. cannot call Finnhub API."
  exit 3
fi

cd "$REPO_DIR"
TO_TS=$(date +%s)
FROM_TS=$((TO_TS - 86400))
QUOTE_URL="https://finnhub.io/api/v1/quote?symbol=AAPL&token=${FINNHUB_API_KEY}"
CANDLE_URL="https://finnhub.io/api/v1/stock/candle?symbol=AAPL&resolution=D&from=${FROM_TS}&to=${TO_TS}&token=${FINNHUB_API_KEY}"

RESP_FILE="$(mktemp)"
if ! HTTP_CODE=$(curl -sS --max-time "$CHECK_TIMEOUT" -w "%{http_code}" -o "$RESP_FILE" "$QUOTE_URL"); then
  echo "failed to request finnhub endpoint"
  rm -f "$RESP_FILE"
  exit 3
fi

if [[ "$HTTP_CODE" != "200" ]]; then
  echo "finnhub http failed: $HTTP_CODE"
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
    print(f"invalid json response: {exc}")
    sys.exit(2)

if data.get("c"):
    print("FINNHUB_API_KEY valid")
    sys.exit(0)

if 'error' in data and data['error']:
    print(f"FINNHUB API error: {data['error']}")
    sys.exit(2)

print(f"unexpected response: {raw[:300]}")
sys.exit(2)
PY
PY_STATUS=$?
rm -f "$RESP_FILE"
if [[ $PY_STATUS -ne 0 ]]; then
  exit $PY_STATUS
fi

if ! HTTP_CODE=$(curl -sS --max-time "$CHECK_TIMEOUT" -w "%{http_code}" -o "$RESP_FILE" "$CANDLE_URL"); then
  echo "failed to request finnhub candle endpoint"
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
    print(f"candle response parse failed: {exc}")
    sys.exit(2)

if data.get("s") == "ok" and data.get("c"):
    print("finnhub candle endpoint ok")
    sys.exit(0)

if "error" in data and data["error"] and "access to this resource" in str(data["error"]).lower():
    print("candle access blocked: free plan can pass quote auth but cannot access stock/candle")
    print("run without chart signals or upgrade Finnhub plan.")
    sys.exit(0)

print(f"unexpected candle response: {raw[:300]}")
sys.exit(0)
PY
  PY_STATUS=$?
  rm -f "$RESP_FILE"
  if [[ $PY_STATUS -ne 0 ]]; then
    exit $PY_STATUS
  fi
elif [[ "$HTTP_CODE" == "403" ]]; then
  echo "finnhub candle endpoint blocked (403). quote endpoint is valid."
  echo "run without chart signals or upgrade Finnhub plan."
else
  echo "finnhub candle http failed: $HTTP_CODE"
  cat "$RESP_FILE" 2>/dev/null || true
  rm -f "$RESP_FILE"
  exit 3
fi

rm -f "$RESP_FILE"
echo "FINNHUB preflight done."
