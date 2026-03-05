#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-balanced}"
case "$MODE" in
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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
REPORT_FILE="$CACHE_DIR/last-run.html"
RUN_LOG="$CACHE_DIR/run.log"
ENV_FILE="$HOME/.config/sia-notifier/env"
DEFAULT_DB="$HOME/sia-notifier/trading_signal_notifier.sqlite"
PYTHON_BIN="${PYTHON_BIN:-python3}"
LOCK_DIR="${CACHE_DIR}/.run-lock"

mkdir -p "$CACHE_DIR"

is_placeholder() {
  case "${1}" in
    __YOUR_*|DUMMY|dummy|placeholder|your_*|YOUR_*) return 0 ;;
    *) return 1 ;;
  esac
}

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python interpreter not found: ${PYTHON_BIN}" >&2
  exit 3
fi

if [[ -f "$ENV_FILE" ]]; then
  # shell style env should define exports
  source "$ENV_FILE"
fi

DB_PATH="${SIGNAL_DB_PATH:-$DEFAULT_DB}"
SIA_DRY_RUN="${SIA_DRY_RUN:-0}"

if [[ -z "${TICKERS:-}" ]]; then
  echo "missing or invalid TICKERS in ${ENV_FILE}" >&2
  exit 3
fi
if is_placeholder "${TICKERS:-}"; then
  echo "missing or invalid TICKERS in ${ENV_FILE}" >&2
  exit 3
fi
if [[ "$SIA_DRY_RUN" != "1" ]]; then
  if [[ -z "${FINNHUB_API_KEY:-}" ]]; then
    echo "FINNHUB_API_KEY is required for live run" >&2
    exit 3
  fi
  if is_placeholder "${FINNHUB_API_KEY:-}"; then
    echo "FINNHUB_API_KEY is required for live run" >&2
    exit 3
  fi
  if [[ -z "${TELEGRAM_BOT_TOKEN:-}" ]]; then
    echo "TELEGRAM_BOT_TOKEN is missing; 메시지가 전송되지 않습니다." >&2
  fi
  if is_placeholder "${TELEGRAM_BOT_TOKEN:-}"; then
    echo "TELEGRAM_BOT_TOKEN is missing; 메시지가 전송되지 않습니다." >&2
  fi
  if [[ -z "${TELEGRAM_CHAT_ID:-}" ]]; then
    echo "TELEGRAM_CHAT_ID is missing; 메시지가 전송되지 않습니다." >&2
  fi
  if is_placeholder "${TELEGRAM_CHAT_ID:-}"; then
    echo "TELEGRAM_CHAT_ID is missing; 메시지가 전송되지 않습니다." >&2
  fi
else
  export SIA_DRY_RUN="1"
fi

if is_placeholder "${MARKETAUX_API_KEY:-}"; then
  echo "MARKETAUX_API_KEY placeholder detected; news fetch disabled for this run." >&2
  export MARKETAUX_API_KEY=""
fi
if is_placeholder "${OLLAMA_HOST:-}"; then
  export OLLAMA_HOST=""
fi
if is_placeholder "${OLLAMA_MODEL:-}"; then
  export OLLAMA_MODEL=""
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "already running (lock exists: $LOCK_DIR)" >&2
  exit 4
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

cd "$REPO_DIR"
export PYTHONPATH="${REPO_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"

RUN_STATUS=0
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

if ! "$PYTHON_BIN" -m sia.trading_signal_notifier \
  "${RUN_ARGS[@]}" \
  > "$RUN_LOG" 2>&1; then
  RUN_STATUS=$?
fi

"$PYTHON_BIN" - "$REPORT_FILE" "$DB_PATH" "$RUN_STATUS" <<'PY'
import sys
import sqlite3
from datetime import datetime
from html import escape

html_path, db_path = sys.argv[1], sys.argv[2]
run_status = int(sys.argv[3]) if len(sys.argv) > 3 else 0
rows = []
error = ""

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
    error = f"DB read error: {exc}"

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
    f.write("<!doctype html><html><head><meta charset='utf-8'><title>SIA Notifier Run</title>")
    f.write("<style>body{font-family:Arial,Helvetica,sans-serif;padding:16px;} table{border-collapse:collapse;} th,td{border:1px solid #999;padding:6px 8px;}</style>")
    f.write("</head><body>")
    f.write(f"<h2>SIA Notifier Run</h2><p>time: {escape(now)}</p>")
    if run_status == 0:
        f.write(f"<p>exit_code: {run_status}</p>")
    else:
        f.write(f"<p style='color:#cc0000'>exit_code: {run_status} (failed)</p>")
        f.write("<p>실행 중 오류가 발생했을 수 있습니다. run.log 를 먼저 확인하세요.</p>")
    if error:
        f.write(f"<p style='color:#cc0000'>{escape(error)}</p>")
    f.write("<table><tr><th>time</th><th>ticker</th><th>signal</th><th>confidence</th><th>sent</th><th>error</th></tr>")
    for r in rows:
        f.write(row_td(*r))
    f.write("</table><p><a href='run.log'>run.log</a></p></body></html>")
PY

if command -v open >/dev/null 2>&1; then
  open "$REPORT_FILE"
fi
