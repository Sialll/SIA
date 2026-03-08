#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
RUN_LOG="${CACHE_DIR}/live-acceptance.log"
REPORT_FILE="${CACHE_DIR}/live-acceptance-report.html"
DB_PATH="/tmp/sia_notifier_live_acceptance.sqlite"
API_LOG="${CACHE_DIR}/live-acceptance-api.log"

TARGET_TICKERS="${SIA_LIVE_TICKERS:-${TICKERS:-AAPL}}"
CLEAN_RUNS="${SIA_LIVE_ACCEPTANCE_REPEATS:-1}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env 파일을 찾을 수 없습니다: $ENV_FILE"
  echo "다음 명령으로 생성하세요: cp scripts/sia-notifier-env.example ~/.config/sia-notifier/env"
  exit 3
fi

source "$ENV_FILE"

is_placeholder() {
  case "${1}" in
    ""|__YOUR_*|dummy|placeholder)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

API_STATUS_LIB="${SCRIPT_DIR}/sia-notifier-api-status-lib.sh"
if [[ ! -f "$API_STATUS_LIB" ]]; then
  echo "API 상태 라이브러리를 찾을 수 없습니다: $API_STATUS_LIB"
  exit 4
fi
source "$API_STATUS_LIB"

if [[ -z "${TARGET_TICKERS}" ]]; then
  echo "SIA_LIVE_TICKERS와 TICKERS가 비어 있습니다."
  exit 3
fi

IFS=',' read -r -a RAW_TICKERS <<< "$TARGET_TICKERS"
declare -a CLEAN_TICKERS=()

for raw in "${RAW_TICKERS[@]}"; do
  t="$(printf '%s' "${raw}" | tr -d '[:space:]' | tr '[:lower:]' '[:upper:]')"
  if is_placeholder "$t"; then
    continue
  fi
  duplicate_ticker=0
  for existing in "${CLEAN_TICKERS[@]+"${CLEAN_TICKERS[@]}"}"; do
    if [[ "$existing" == "$t" ]]; then
      duplicate_ticker=1
      break
    fi
  done
  if (( duplicate_ticker == 1 )); then
    continue
  fi
  CLEAN_TICKERS+=("$t")
done

if (( ${#CLEAN_TICKERS[@]} == 0 )); then
  echo "SIA_LIVE_TICKERS/TICKERS에서 유효한 ticker를 찾지 못했습니다."
  exit 3
fi

TARGET_TICKERS_CSV="${CLEAN_TICKERS[*]}"
TARGET_TICKERS_CSV="${TARGET_TICKERS_CSV// /,}"

if is_placeholder "${TELEGRAM_BOT_TOKEN:-}"; then
  echo "TELEGRAM_BOT_TOKEN이 없거나 플레이스홀더입니다."
  exit 3
fi
if is_placeholder "${TELEGRAM_CHAT_ID:-}"; then
  echo "TELEGRAM_CHAT_ID가 없거나 플레이스홀더입니다."
  exit 3
fi
if is_placeholder "${FINNHUB_API_KEY:-}"; then
  echo "FINNHUB_API_KEY가 없거나 플레이스홀더입니다."
  exit 3
fi

if [[ "${SIA_LIVE_CONFIRM:-0}" != "1" ]]; then
  if [[ -t 0 ]]; then
    echo "⚠️  실전 모드 실행 시 텔레그램으로 실제 알림이 발송됩니다."
    read -r -p "계속 진행할까요? [y/N]: " answer
    if [[ "${answer}" != "y" && "${answer}" != "Y" ]]; then
      echo "실행을 취소했습니다."
      exit 0
    fi
  else
    echo "비대화형 실행입니다. 실전 발송을 하려면 SIA_LIVE_CONFIRM=1로 먼저 설정하세요."
    exit 3
  fi
fi

echo "사전 점검: 텔레그램 + finnhub 점검 실행"
 : > "$API_LOG"
if ! { "${REPO_DIR}/scripts/_internal/sia-notifier-check-telegram.command"; } 2>&1 | tee -a "$API_LOG"; then
  echo "telegram 점검 실패"
  exit 3
fi
if ! { "${REPO_DIR}/scripts/_internal/sia-notifier-check-finnhub.command"; } 2>&1 | tee -a "$API_LOG"; then
  echo "finnhub 점검 실패"
  exit 3
fi

mkdir -p "$CACHE_DIR"
rm -f "$DB_PATH" "$RUN_LOG" "$REPORT_FILE"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUN_EXIT=0

RUNS=0
while (( RUNS < CLEAN_RUNS )); do
  RUNS=$((RUNS + 1))
  cd "$REPO_DIR"
  if ! (PYTHONPATH="${REPO_DIR}/src" \
    TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN" \
    TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID" \
    FINNHUB_API_KEY="${FINNHUB_API_KEY}" \
    MARKETAUX_API_KEY="" \
    SIA_DRY_RUN="0" \
    "$PYTHON_BIN" -m sia.trading_signal_notifier \
      --once \
      --tickers "$TARGET_TICKERS_CSV" \
      --db-path "$DB_PATH" \
      --signal-threshold 0 \
      --max-news-per-ticker 0 \
      --cooldown-minutes 1 \
      --ollama-host "" \
      --ollama-model "" \
      >> "$RUN_LOG" 2>&1); then
    RUN_EXIT=$?
    echo "경고: 실시간 승인 실행 실패 (종료 코드=${RUN_EXIT})"
  fi
  if [[ "$RUNS" -ge "$CLEAN_RUNS" ]]; then
    break
  fi
done

if [[ -f "$RUN_LOG" ]]; then
  echo "===== 실시간 실행 로그(최근 40줄) ====="
  tail -n 40 "$RUN_LOG"
  cat "$RUN_LOG" >> "$API_LOG"
fi

echo "===== API 상태 ====="
API_NOTES="$(collect_api_status "$API_LOG")"
parse_api_status "$API_NOTES"
echo "운영 판정: ${API_GRADE}"
if [[ "$API_NOTES" == "NONE" ]]; then
  echo "실행 중 API 장애는 감지되지 않았습니다. (미사용 API는 제외)."
else
if (( ${#API_STATUS_BLOCKER_LIST[@]} > 0 )); then
    echo "- 심각"
    printf '  - [심각] %s\n' "${API_STATUS_BLOCKER_LIST[@]}"
  fi
  if (( ${#API_STATUS_FALLBACK_LIST[@]} > 0 )); then
    echo "- 대체"
    printf '  - [대체] %s\n' "${API_STATUS_FALLBACK_LIST[@]}"
  fi
  if (( ${#API_STATUS_UNKNOWN_LIST[@]} > 0 )); then
    echo "- 미확인"
    printf '  - [미확인] %s\n' "${API_STATUS_UNKNOWN_LIST[@]}"
  fi
fi

if [[ "$API_NOTES" == "NONE" ]]; then
  API_NOTES_B64=""
else
  API_NOTES_B64="$(printf '%s' "$API_NOTES" | base64 | tr -d '\n')"
fi
RESULTS="$(python3 - "$DB_PATH" "$TARGET_TICKERS_CSV" "$REPORT_FILE" "$API_NOTES_B64" <<'PY'
import sqlite3
import sys
import base64
import html
from datetime import datetime
from pathlib import Path

db_path = Path(sys.argv[1])
ticker_csv = sys.argv[2]
report_path = Path(sys.argv[3])
api_status_b64 = sys.argv[4] if len(sys.argv) > 4 else ""

tickers = [item.strip().upper() for item in ticker_csv.split(",") if item.strip()]
raw_api_status = ""
if api_status_b64 and api_status_b64.strip() and api_status_b64 != "NONE":
    try:
        raw_api_status = base64.b64decode(api_status_b64.encode("utf-8")).decode("utf-8", errors="replace")
    except Exception:
        raw_api_status = ""
api_status_lines = [line.strip() for line in raw_api_status.splitlines() if line.strip()]
api_status_buckets = {"BLOCKER": [], "FALLBACK": [], "UNKNOWN": []}
for line in api_status_lines:
    if "|" in line:
        severity, msg = line.split("|", 1)
        severity = severity.strip()
        msg = msg.strip()
        if severity in api_status_buckets:
            api_status_buckets[severity].append(msg)
        else:
            api_status_buckets["UNKNOWN"].append(line)
    else:
        api_status_buckets["UNKNOWN"].append(line)

api_grade = "OK"
if api_status_buckets["BLOCKER"]:
    api_grade = "BLOCKER"
elif api_status_buckets["FALLBACK"]:
    api_grade = "FALLBACK"

if not db_path.exists():
    print("DB_MISSING")
    raise SystemExit(0)

rows = []
sent_count = 0
trade_count = 0
error_count = 0

with sqlite3.connect(str(db_path)) as conn:
    for ticker in tickers:
        row = conn.execute(
            """
            SELECT ts, signal, sent, reason, COALESCE(error_message, '')
            FROM alerts
            WHERE ticker = ? AND signal IN ('BUY','SELL')
            ORDER BY ts DESC
            LIMIT 1
            """,
            (ticker,),
        ).fetchone()

        if row is None:
            error_count += 1
            rows.append(
                {
                    "ticker": ticker,
                    "signal": "",
                    "sent": 0,
                    "ts": 0,
                    "reason": "",
                    "error": "NO_TRADE_SIGNAL",
                }
            )
            continue

        trade_count += 1
        sent = int(row[2])
        if sent == 1:
            sent_count += 1
        rows.append(
            {
                "ticker": ticker,
                "signal": row[1],
                "sent": sent,
                "ts": int(row[0]),
                "reason": (row[3] or "").replace("|", "／"),
                "error": row[4] or "",
            }
        )

rows.sort(key=lambda item: item["ticker"])


def fmt_time(ts: int) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts)


status = "PASS" if sent_count > 0 and trade_count > 0 else "FAIL"
if trade_count == 0:
    status = "FAIL"

with report_path.open("w", encoding="utf-8") as fp:
    fp.write("<!doctype html><html><head><meta charset='utf-8'>")
    fp.write("<title>SIA 실시간 승인 테스트</title>")
    fp.write("<style>body{font-family:Arial,sans-serif;padding:16px} "
             "table{border-collapse:collapse} th,td{border:1px solid #999;padding:6px 8px} "
             ".pass{color:#0a0} .fail{color:#d00} .warn{color:#b88} .ok{color:#0a0} "
             ".fallback{color:#c60} .blocker{color:#d00} .unknown{color:#777} "
             ".legend{color:#333;display:flex;gap:16px;margin:4px 0 12px 0;flex-wrap:wrap}"
             ".legend span{display:inline-flex;align-items:center;gap:6px}"
             ".legend em{display:inline-block;width:8px;height:8px;border-radius:50%}"
             "em.blocker{background:#d00}.unknown{background:#777}.fallback{background:#c60}.ok{background:#0a0}"
             "</style></head><body>")
    fp.write(f"<h2>실시간 수락 테스트 결과: {status}</h2>")
    fp.write(f"<p>티커 목록: {', '.join(tickers)}</p>")
    fp.write(f"<p>신호 수: {trade_count} / {len(tickers)}, 발송 수: {sent_count}</p>")
    fp.write(f"<p>API 등급: <span class='{api_grade.lower()}'>{api_grade}</span></p>")
    fp.write("<div class='legend'><span><em class='blocker'></em>심각</span><span><em class='fallback'></em>대체</span><span><em class='unknown'></em>미확인</span><span><em class='ok'></em>정상</span></div>")
    fp.write("<h3>API 상태</h3><ul>")
    if not any(api_status_buckets.values()):
        fp.write("<li>정상</li>")
    else:
        if api_status_buckets["BLOCKER"]:
            for msg in api_status_buckets["BLOCKER"]:
                fp.write(f"<li class='blocker'>[심각] {html.escape(msg)}</li>")
        if api_status_buckets["FALLBACK"]:
            for msg in api_status_buckets["FALLBACK"]:
                fp.write(f"<li class='fallback'>[대체] {html.escape(msg)}</li>")
        if api_status_buckets["UNKNOWN"]:
            for msg in api_status_buckets["UNKNOWN"]:
                fp.write(f"<li class='unknown'>[미확인] {html.escape(msg)}</li>")
    fp.write("</ul>")
    fp.write("<table><thead><tr><th>ticker</th><th>발송</th><th>신호</th><th>시각</th><th>근거</th></tr></thead><tbody>")
    for row in rows:
        cls = "pass" if row["sent"] == 1 else ("warn" if row["signal"] else "fail")
        fp.write("<tr>")
        fp.write(f"<td>{row['ticker']}</td>")
        fp.write(f"<td class='{cls}'>" + ("Y" if row["sent"] == 1 else "N") + "</td>")
        fp.write(f"<td>{row['signal']}</td>")
        fp.write(f"<td>{fmt_time(row['ts'])}</td>")
        reason = row["reason"] if row["reason"] else row["error"]
        fp.write(f"<td>{reason}</td>")
        fp.write("</tr>")
    fp.write("</tbody></table></body></html>")

if trade_count == 0:
    print("NO_TRADE_SIGNAL")
    raise SystemExit(0)

print(f"SUMMARY|{status}|{sent_count}|{trade_count}|{error_count}")
for row in rows:
    print(
        "ROW|%s|%s|%s|%s|%s|%s"
        % (
            row["ticker"],
            row["sent"],
            row["signal"],
            row["ts"],
            row["reason"],
            row["error"],
        )
    )
PY
)"

if [[ "$RESULTS" == "DB_MISSING" ]]; then
  echo "실패: 거래 DB를 만들지 못했습니다."
  exit 2
fi
if [[ "$RESULTS" == "NO_TRADE_SIGNAL" ]]; then
  echo "실패: 어떤 ticker에서도 BUY/SELL 신호가 생성되지 않았습니다."
  echo "$RUN_LOG에서 데이터 조회/수집 오류를 확인하세요."
  exit 3
fi

SUMMARY_LINE="$(printf '%s\n' "$RESULTS" | awk -F'|' 'NR==1 {print}')"
if [[ "${SUMMARY_LINE%%|*}" != "SUMMARY" ]]; then
  echo "실패: 결과 형식이 예상과 다릅니다."
  echo "$RESULTS"
  exit 5
fi

VERDICT="$(printf '%s\n' "$SUMMARY_LINE" | awk -F'|' '{print $2}')"
SENT_COUNT="$(printf '%s\n' "$SUMMARY_LINE" | awk -F'|' '{print $3}')"
TRADE_COUNT="$(printf '%s\n' "$SUMMARY_LINE" | awk -F'|' '{print $4}')"

echo "===== 실시간 승인 테스트 보고서 ====="
if [[ -f "$REPORT_FILE" ]]; then
  sed -n '1,32p' "$REPORT_FILE"
else
  echo "실패: 보고서 파일이 생성되지 않았습니다."
  echo "확인: 보고서 생성 전에 실행 실패했거나 DB 파일이 없을 수 있습니다."
  if (( RUN_EXIT != 0 )); then
    echo "종료 코드: ${RUN_EXIT}"
  fi
  if [[ -f "$RUN_LOG" ]]; then
    echo "run.log 마지막 줄:"
    tail -n 40 "$RUN_LOG"
  else
    echo "run.log를 찾을 수 없습니다: $RUN_LOG"
  fi
fi
echo "보고서 파일: $REPORT_FILE"
if [[ -f "$REPORT_FILE" && -n "${SIA_DONT_OPEN_REPORT:-}" && "${SIA_DONT_OPEN_REPORT}" != "1" ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$REPORT_FILE" >/dev/null 2>&1 || true
  fi
fi
  echo "요약: 판정=${VERDICT}, 발송=${SENT_COUNT}, 신호=${TRADE_COUNT}"
  echo "상세:"
  printf '%s\n' "$RESULTS" | awk -F'|' 'NR>1 {printf "%s 신호=%s 발송=%s\n", $2, $4, $3}'

if [[ "$VERDICT" == "PASS" ]]; then
  echo "통과: 실시간 수락 테스트 성공"
  exit 0
fi

echo "실패: 실시간 수락 테스트에서 최소 한 번의 BUY/SELL 발송이 확인되지 않았습니다."
echo "결과: $RESULTS"
echo "최근 실행 로그:"
tail -n 50 "$RUN_LOG"
exit 4
