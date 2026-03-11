#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
RUN_LOG="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/run.log"
RUN_MODE="balanced"
OVERRIDE_DRY_RUN="__UNSET__"
RUN_SCRIPT="${REPO_DIR}/scripts/_internal/sia-notifier-launch.command"
REPORT_FILE="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/quickcheck-report.html"
API_LOG="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/quickcheck-api.log"
SCRATCH_DB="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier/quickcheck.sqlite"

if [[ "${SIA_DRY_RUN+x}" == "x" ]]; then
  OVERRIDE_DRY_RUN="$SIA_DRY_RUN"
fi

if [[ $# -gt 0 ]]; then
  case "$1" in
    balanced|conservative|aggressive)
      RUN_MODE="$1"
      shift
      ;;
    --help|-h)
      cat <<'EOF_USAGE'
사용법:
  ./sia-notifier-live-quickcheck.command [balanced|conservative|aggressive] [--live|--dry-run]

옵션:
  --live      실전 모드 강제 실행(텔레그램 포함)
  --dry-run   드라이런 강제 실행(텔레그램 미전송)
EOF_USAGE
      exit 0
      ;;
  esac
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --live)
      OVERRIDE_DRY_RUN="0"
      shift
      ;;
    --dry-run)
      OVERRIDE_DRY_RUN="1"
      shift
      ;;
    --help|-h)
      cat <<'EOF_USAGE'
사용법:
  ./sia-notifier-live-quickcheck.command [balanced|conservative|aggressive] [--live|--dry-run]

옵션:
  --live      실전 모드 강제 실행(텔레그램 포함)
  --dry-run   드라이런 강제 실행(텔레그램 미전송)
EOF_USAGE
      exit 0
      ;;
    *)
      echo "알 수 없는 인자: $1"
      echo "도움말: ./sia-notifier-live-quickcheck.command --help"
      exit 2
      ;;
  esac
done

API_STATUS_LIB="${SCRIPT_DIR}/sia-notifier-api-status-lib.sh"
if [[ ! -f "$API_STATUS_LIB" ]]; then
  echo "API 상태 라이브러리를 찾을 수 없습니다: $API_STATUS_LIB"
  exit 4
fi
source "$API_STATUS_LIB"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "env 파일을 찾을 수 없습니다: $ENV_FILE"
  echo "템플릿을 복사하세요: cp scripts/sia-notifier-env.example ~/.config/sia-notifier/env"
  exit 2
fi

# shell style env should define exports
source "$ENV_FILE"
if [[ "$OVERRIDE_DRY_RUN" != "__UNSET__" ]]; then
  SIA_DRY_RUN="$OVERRIDE_DRY_RUN"
fi
export SIA_DRY_RUN="${SIA_DRY_RUN:-0}"

if [[ "${SIA_DRY_RUN}" == "1" ]]; then
  required_vars=(TICKERS)
else
  required_vars=(TICKERS TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID FINNHUB_API_KEY)
fi
for var in "${required_vars[@]}"; do
  value="${!var:-}"
  if [[ -z "$value" || "$value" == "__YOUR_"* || "$value" == "dummy" || "$value" == "placeholder" ]]; then
    echo "필수 값이 없거나 유효하지 않습니다: $var"
    exit 3
  fi
done

if [[ "${SIA_DRY_RUN}" != "0" ]]; then
  echo "현재 드라이런 모드입니다. 실시간 실행하려면 SIA_DRY_RUN=0 설정."
fi

: > "$API_LOG"

cd "$REPO_DIR"
RUN_EXIT=0
if [[ -f "$RUN_SCRIPT" ]]; then
  if [[ "${SIA_DRY_RUN}" == "1" ]]; then
    rm -f "$SCRATCH_DB"
    if { SIGNAL_DB_PATH="$SCRATCH_DB" "$RUN_SCRIPT" "$RUN_MODE" --dry-run; } 2>&1 | tee -a "$API_LOG"; then
      RUN_EXIT=0
    else
      RUN_EXIT="${PIPESTATUS[0]:-1}"
      echo "실행이 중단되었습니다. 종료코드=$RUN_EXIT"
    fi
  else
    if { "$RUN_SCRIPT" "$RUN_MODE" --live; } 2>&1 | tee -a "$API_LOG"; then
      RUN_EXIT=0
    else
      RUN_EXIT="${PIPESTATUS[0]:-1}"
      echo "실행이 중단되었습니다. 종료코드=$RUN_EXIT"
    fi
  fi
else
  echo "런처 파일이 없습니다: $RUN_SCRIPT" >&2
  echo "런처를 찾을 수 없습니다: $RUN_SCRIPT" >&2
  exit 3
fi

if (( RUN_EXIT != 0 )); then
  echo "경고: 실행 스크립트 종료 코드 = ${RUN_EXIT}"
fi
if [[ -f "$RUN_LOG" ]]; then
  tail -n 60 "$RUN_LOG"
  cat "$RUN_LOG" >> "$API_LOG"
else
  echo "run.log를 찾을 수 없습니다: $RUN_LOG"
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

python3 - "$REPORT_FILE" "$RUN_EXIT" "$RUN_MODE" "$API_GRADE" "$API_NOTES" <<'PY'
import os
import sys
import html
from datetime import datetime
from pathlib import Path

report_path, run_exit, mode, api_grade, api_notes = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
run_exit = int(run_exit or 0)
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

blockers = []
fallbacks = []
unknowns = []
for line in [x.strip() for x in api_notes.splitlines() if x.strip()]:
    if "|" in line:
        severity, msg = line.split("|", 1)
        severity = severity.strip().upper()
        msg = msg.strip()
        if severity == "BLOCKER":
            blockers.append(msg)
        elif severity == "FALLBACK":
            fallbacks.append(msg)
        else:
            unknowns.append(line)
    else:
        unknowns.append(line)

status_line = "OK"
if blockers:
    status_line = "BLOCKER"
elif fallbacks:
    status_line = "FALLBACK"

def li(tag, items, css=""):
    if not items:
        return ""
    head = [f"<li class='{css}'>[{tag}] {html.escape(item)}</li>" for item in items]
    return "\n".join(head)

Path(report_path).parent.mkdir(parents=True, exist_ok=True)
with open(report_path, "w", encoding="utf-8") as fp:
    fp.write("<!doctype html><html><head><meta charset='utf-8'>")
    fp.write("<title>SIA 빠른 점검 보고서</title>")
    fp.write(
        "<style>"
    "body{font-family:Arial,Helvetica,sans-serif;padding:16px}"
    "ul{padding-left:20px}"
    "li{margin:4px 0}"
    ".pass{color:#0a0}.fail{color:#d00}.warn{color:#c80}"
    ".ok{color:#0a0}.fallback{color:#c60}.blocker{color:#d00}.unknown{color:#777}"
    ".meta{color:#555;font-size:14px;margin-bottom:8px}"
    ".legend{color:#333;display:flex;gap:16px;margin:4px 0 12px 0;flex-wrap:wrap}"
    ".legend span{display:inline-flex;align-items:center;gap:6px}"
    ".legend em{display:inline-block;width:8px;height:8px;border-radius:50%}"
    "em.blocker{background:#d00}.unknown{background:#777}.fallback{background:#c60}.ok{background:#0a0}"
    "</style></head><body>"
)
    fp.write(f"<h2>SIA 빠른 점검 보고서</h2>")
    fp.write(f"<div class='meta'>시간={html.escape(now)} 모드={html.escape(mode)} 종료코드={run_exit}</div>")
    fp.write(f"<p>API 등급: <strong class='{html.escape(status_line.lower())}'>{html.escape(status_line)}</strong></p>")
    fp.write("<div class='legend'><span><em class='blocker'></em>심각</span><span><em class='fallback'></em>대체</span><span><em class='unknown'></em>미확인</span><span><em class='ok'></em>정상</span></div>")
    fp.write("<h3>API 상태</h3><ul>")
    if blockers:
        fp.write(li("심각", blockers, "blocker"))
    if fallbacks:
        fp.write(li("대체", fallbacks, "fallback"))
    if unknowns:
        for item in unknowns:
            fp.write(f"<li class='unknown'>[미확인] {html.escape(item)}</li>")
    if not (blockers or fallbacks or unknowns):
        fp.write("<li>정상</li>")
    fp.write("</ul>")
    if run_exit != 0:
        fp.write("<p class='fail'>실행 중 오류가 감지되었습니다. run.log / quickcheck-api.log를 확인하세요.</p>")
    fp.write("<p><a href='run.log'>run.log</a> | <a href='quickcheck-api.log'>quickcheck-api.log</a></p>")
    fp.write("</body></html>")

print(report_path)
PY

  if [[ "$RUN_EXIT" != "0" ]]; then
  echo "퀵체크 보고서: $REPORT_FILE (종료코드=$RUN_EXIT)"
else
  echo "퀵체크 보고서: $REPORT_FILE"
fi
if command -v open >/dev/null 2>&1; then
  open "$REPORT_FILE" >/dev/null 2>&1 || true
fi
