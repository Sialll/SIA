#!/usr/bin/env bash
set -euo pipefail

MODE="balanced"
DRY_RUN_OVERRIDE=""
DRY_RUN_EXPLICIT="0"

parse_mode() {
  local mode_value="$1"
  case "$mode_value" in
    conservative|conservative-mode|safe|보수)
      TREND_WEIGHT=0.6
      RSI_WEIGHT=0.2
      NEWS_WEIGHT=0.2
      SIGNAL_THRESHOLD=0.45
      ;;
    aggressive|aggressive-mode|fast|공격)
      TREND_WEIGHT=0.45
      RSI_WEIGHT=0.25
      NEWS_WEIGHT=0.30
      SIGNAL_THRESHOLD=0.25
      ;;
    balanced|default|normal|균형|*)
      TREND_WEIGHT=0.55
      RSI_WEIGHT=0.25
      NEWS_WEIGHT=0.20
      SIGNAL_THRESHOLD=0.35
      ;;
  esac
}

parse_args() {
  local arg

  while [[ $# -gt 0 ]]; do
    arg="$1"
    case "$arg" in
      balanced|conservative|conservative-mode|safe|보수|aggressive|aggressive-mode|fast|공격|default|normal)
        MODE="$arg"
        shift
        ;;
      --dry-run)
        DRY_RUN_OVERRIDE="1"
        DRY_RUN_EXPLICIT="1"
        shift
        ;;
      --live)
        DRY_RUN_OVERRIDE="0"
        DRY_RUN_EXPLICIT="1"
        shift
        ;;
      --help|-h)
        cat <<'EOF_USAGE'
사용법:
  ./sia-notifier-launch.command [balanced|conservative|aggressive] [--live|--dry-run]

옵션:
  --live      실전 모드 강제 실행(텔레그램 전송)
  --dry-run   드라이런 강제 실행(텔레그램 미전송)

--live/--dry-run를 지정하지 않으면 env 파일의 SIA_DRY_RUN 값을 사용합니다.
EOF_USAGE
        exit 0
        ;;
      *)
        echo "알 수 없는 옵션/모드입니다: ${arg}" >&2
        echo "도움말 보기: ./sia-notifier-launch.command --help" >&2
        exit 2
        ;;
    esac
  done
}

parse_args "$@"
parse_mode "$MODE"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -n "${SIA_REPO_DIR:-}" && -d "${SIA_REPO_DIR}" ]]; then
  REPO_DIR="$(cd "${SIA_REPO_DIR}" && pwd)"
else
  REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
REPORT_FILE="$CACHE_DIR/last-run.html"
DASHBOARD_FILE="$CACHE_DIR/dashboard.html"
RUN_LOG="$CACHE_DIR/run.log"
API_LOG="$CACHE_DIR/last-run-api.log"
ENV_FILE="$HOME/.config/sia-notifier/env"
DEFAULT_DB="$HOME/sia-notifier/trading_signal_notifier.sqlite"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOCK_DIR="${CACHE_DIR}/.run-lock"
API_STATUS_LIB="${SCRIPT_DIR}/sia-notifier-api-status-lib.sh"
DASHBOARD_SCRIPT="${SCRIPT_DIR}/sia-dashboard.command"

mkdir -p "$CACHE_DIR"

is_placeholder() {
  case "${1}" in
    __YOUR_*|DUMMY|dummy|placeholder|your_*|YOUR_*) return 0 ;;
    *) return 1 ;;
  esac
}

parse_bool() {
  case "${1:-}" in
    1|true|TRUE|True|yes|YES|Yes|on|ON|On)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "파이썬 인터프리터를 찾을 수 없습니다: ${PYTHON_BIN}" >&2
  exit 3
fi
if [[ ! -f "$API_STATUS_LIB" ]]; then
  echo "API 상태 라이브러리를 찾을 수 없습니다: $API_STATUS_LIB"
  exit 4
fi
source "$API_STATUS_LIB"

if [[ -f "$ENV_FILE" ]]; then
  # shell style env should define exports
  source "$ENV_FILE"
fi

DB_PATH="${SIGNAL_DB_PATH:-$DEFAULT_DB}"
if [[ -n "$DRY_RUN_OVERRIDE" ]]; then
  SIA_DRY_RUN="$DRY_RUN_OVERRIDE"
else
  SIA_DRY_RUN="${SIA_DRY_RUN:-0}"
fi

if [[ "${SIA_DRY_RUN}" == "1" && "${DRY_RUN_EXPLICIT}" == "0" ]]; then
  echo "안내: SIA_DRY_RUN=1이 적용되어 텔레그램 전송되지 않습니다."
  echo "      현재는 드라이런입니다. 실전 실행은 --live를 사용하세요."
fi

if [[ -z "${TICKERS:-}" ]]; then
  echo "${ENV_FILE}에서 TICKERS가 없거나 유효하지 않습니다." >&2
  exit 3
fi
if is_placeholder "${TICKERS:-}"; then
  echo "${ENV_FILE}에서 TICKERS가 없거나 유효하지 않습니다." >&2
  exit 3
fi
if [[ "$SIA_DRY_RUN" != "1" ]]; then
  if [[ -z "${FINNHUB_API_KEY:-}" ]]; then
    echo "FINNHUB_API_KEY가 없습니다. 가격 조회는 Yahoo Finance 대체 경로를 사용합니다." >&2
  elif is_placeholder "${FINNHUB_API_KEY:-}"; then
    echo "FINNHUB_API_KEY가 플레이스홀더입니다. 가격 조회는 Yahoo Finance 대체 경로를 사용합니다." >&2
    export FINNHUB_API_KEY=""
  fi
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "TELEGRAM_BOT_TOKEN이 없습니다. 메시지가 전송되지 않습니다." >&2
  fi
  if is_placeholder "${TELEGRAM_BOT_TOKEN:-}"; then
    echo "TELEGRAM_BOT_TOKEN이 플레이스홀더입니다. 메시지가 전송되지 않습니다." >&2
  fi
  if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    echo "TELEGRAM_CHAT_ID가 없습니다. 메시지가 전송되지 않습니다." >&2
  fi
  if is_placeholder "${TELEGRAM_CHAT_ID:-}"; then
    echo "TELEGRAM_CHAT_ID가 플레이스홀더입니다. 메시지가 전송되지 않습니다." >&2
  fi
else
  SIA_DRY_RUN="1"
fi

if is_placeholder "${MARKETAUX_API_KEY:-}"; then
  echo "MARKETAUX_API_KEY가 플레이스홀더입니다. Marketaux는 건너뛰고 Yahoo RSS 무료 뉴스 경로를 사용합니다." >&2
  export MARKETAUX_API_KEY=""
fi

if parse_bool "${SIA_NO_OLLAMA:-0}"; then
  echo "SIA_NO_OLLAMA=1: 이번 실행은 ollama 요약을 사용하지 않습니다."
  export OLLAMA_HOST=""
  export OLLAMA_MODEL=""
fi

if is_placeholder "${OLLAMA_HOST:-}"; then
  export OLLAMA_HOST=""
fi
if is_placeholder "${OLLAMA_MODEL:-}"; then
  export OLLAMA_MODEL=""
fi
if [[ -z "${OLLAMA_HOST:-}" ]]; then
  OLLAMA_HOST=""
fi
if [[ -z "${OLLAMA_MODEL:-}" ]]; then
  OLLAMA_MODEL=""
fi

OLLAMA_TIMEOUT_SECONDS="${SIA_OLLAMA_TIMEOUT_SECONDS:-1}"
if [[ ! "$OLLAMA_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || (( OLLAMA_TIMEOUT_SECONDS < 1 )); then
  OLLAMA_TIMEOUT_SECONDS=1
fi

if [[ -n "${OLLAMA_HOST:-}" ]]; then
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl이 없어 ollama를 사용하지 못합니다. 이번 실행은 뉴스 요약을 비활성화합니다."
    export OLLAMA_HOST=""
    export OLLAMA_MODEL=""
  elif ! curl -fsS --max-time "${OLLAMA_TIMEOUT_SECONDS}" "${OLLAMA_HOST%/}/api/tags" >/dev/null 2>&1; then
    echo "ollama 연결 실패로 이번 실행은 뉴스 요약을 비활성화합니다."
    export OLLAMA_HOST=""
    export OLLAMA_MODEL=""
  fi
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "이미 실행 중입니다. (lock 존재: $LOCK_DIR)" >&2
  exit 4
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$REPO_DIR"
export PYTHONPATH="${REPO_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

RUN_STATUS=0
 : > "$API_LOG"
RUN_ARGS=(
  --once
  --db-path "$DB_PATH"
  --trend-weight "$TREND_WEIGHT"
  --rsi-weight "$RSI_WEIGHT"
  --news-weight "$NEWS_WEIGHT"
  --signal-threshold "$SIGNAL_THRESHOLD"
)
if [[ "${SIA_DRY_RUN}" == "1" ]]; then
  RUN_ARGS+=(--dry-run)
fi
if [[ "${SIA_DRY_RUN}" != "1" && -n "${MARKETAUX_API_KEY:-}" ]]; then
  RUN_ARGS+=(--max-news-per-ticker "${MAX_NEWS_PER_TICKER:-3}")
fi
RUN_ARGS+=(--ollama-host "${OLLAMA_HOST:-}" --ollama-model "${OLLAMA_MODEL:-}")

if ! "$PYTHON_BIN" -m sia.trading_signal_notifier \
  "${RUN_ARGS[@]}" \
  > "$RUN_LOG" 2>&1; then
  RUN_STATUS=$?
fi

if [[ -f "$RUN_LOG" ]]; then
  cp "$RUN_LOG" "$API_LOG"
else
  echo "run.log를 찾을 수 없습니다: $RUN_LOG" > "$API_LOG"
fi

API_NOTES="$(collect_api_status "$API_LOG")"
parse_api_status "$API_NOTES"
echo "===== API 상태 ====="
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

"$PYTHON_BIN" - "$REPORT_FILE" "$DB_PATH" "$RUN_STATUS" "$API_NOTES_B64" <<'PY'
import sys
import sqlite3
import base64
import html
from datetime import datetime
from html import escape

html_path, db_path = sys.argv[1], sys.argv[2]
run_status = int(sys.argv[3]) if len(sys.argv) > 3 else 0
api_status_b64 = sys.argv[4] if len(sys.argv) > 4 else ""
rows = []
error = ""

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

try:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT ts, ticker, signal, confidence, sent, COALESCE(error_message, '')
            FROM alerts
            ORDER BY ts DESC
            LIMIT 20
            """
        ).fetchall()
except Exception as exc:
    error = f"DB 조회 실패: {exc}"

now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def row_td(ts, ticker, signal, confidence, sent, err):
    try:
        t = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        t = str(ts)
    return (
        f"<tr>"
        f"<td>{escape(str(t))}</td>"
        f"<td>{escape(str(ticker))}</td>"
        f"<td>{escape(str(signal))}</td>"
        f"<td>{float(confidence):.2f}</td>"
        f"<td>{'Y' if sent else 'N'}</td>"
        f"<td>{escape(str(err))}</td>"
        f"</tr>\n"
    )

with open(html_path, 'w', encoding='utf-8') as f:
    f.write("<!doctype html><html><head><meta charset='utf-8'><title>SIA 알림 실행</title>")
    f.write(
        "<style>body{font-family:Arial,Helvetica,sans-serif;padding:16px;} "
        "table{border-collapse:collapse;} th,td{border:1px solid #999;padding:6px 8px;}"
        ".pass{color:#0a0}.fail{color:#d00}.warn{color:#c80}"
        ".ok{color:#0a0}.fallback{color:#c60}.blocker{color:#d00}.unknown{color:#777}"
        ".legend{color:#333;display:flex;gap:16px;margin:4px 0 12px 0;flex-wrap:wrap}"
        ".legend span{display:inline-flex;align-items:center;gap:6px}"
        ".legend em{display:inline-block;width:8px;height:8px;border-radius:50%}"
        "em.blocker{background:#d00}.unknown{background:#777}.fallback{background:#c60}.ok{background:#0a0}"
        "</style>"
    )
    f.write("</head><body>")
    f.write(f"<h2>SIA 알림 실행</h2><p>시간: {escape(now)}</p>")
    if run_status == 0:
        f.write(f"<p>종료 코드: {run_status}</p>")
    else:
        f.write(f"<p style='color:#cc0000'>종료 코드: {run_status} (실패)</p>")
        f.write("<p>실행 중 오류가 발생했을 수 있습니다. run.log를 먼저 확인하세요.</p>")
    if error:
        f.write(f"<p style='color:#cc0000'>{escape(error)}</p>")
    f.write(f"<p>API 등급: <strong class='{escape(api_grade.lower())}'>{escape(api_grade)}</strong></p>")
    f.write("<div class='legend'><span><em class='blocker'></em>심각</span><span><em class='fallback'></em>대체</span><span><em class='unknown'></em>미확인</span><span><em class='ok'></em>정상</span></div>")
    f.write("<h3>API 상태</h3><ul>")
    if not any(api_status_buckets.values()):
        f.write("<li>정상</li>")
    else:
        for msg in api_status_buckets["BLOCKER"]:
            f.write(f"<li class='blocker'>[심각] {html.escape(msg)}</li>")
        for msg in api_status_buckets["FALLBACK"]:
            f.write(f"<li class='fallback'>[대체] {html.escape(msg)}</li>")
        for msg in api_status_buckets["UNKNOWN"]:
            f.write(f"<li class='unknown'>[미확인] {html.escape(msg)}</li>")
    f.write("</ul>")
    f.write("<table><tr><th>시각</th><th>ticker</th><th>신호</th><th>신뢰도</th><th>발송</th><th>오류</th></tr>")
    for r in rows:
        f.write(row_td(*r))
    f.write("</table><p><a href='run.log'>run.log</a> | <a href='last-run-api.log'>last-run-api.log</a> | <a href='dashboard.html'>dashboard.html</a></p></body></html>")
PY

if [[ -x "$DASHBOARD_SCRIPT" ]]; then
  SIA_NO_OPEN_DASHBOARD=1 "$DASHBOARD_SCRIPT" >/dev/null 2>&1 || true
fi

if [[ "${SIA_NO_OPEN_REPORT:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  if ! open "$REPORT_FILE" >/dev/null 2>&1; then
    echo "경고: 브라우저에서 보고서를 열지 못했습니다. 경로: $REPORT_FILE"
  fi
fi

if [[ ! -f "$REPORT_FILE" ]]; then
  echo "실패: 보고서 파일이 생성되지 않았습니다."
  echo "확인: 보고서 생성 전에 실행이 실패했을 수 있습니다."
  if [[ -f "$RUN_LOG" ]]; then
    echo "run.log 마지막 줄:"
    tail -n 40 "$RUN_LOG"
  else
    echo "run.log를 찾을 수 없습니다: $RUN_LOG"
  fi
  exit 4
fi
if [[ ! -f "$DASHBOARD_FILE" ]]; then
  echo "경고: dashboard.html 생성에 실패했습니다. 경로: $DASHBOARD_FILE"
fi
if (( RUN_STATUS != 0 )); then
  echo "경고: 실행이 종료 코드 ${RUN_STATUS}로 끝났습니다."
fi
