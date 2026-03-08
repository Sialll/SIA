#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GATE_SCRIPT="$SCRIPT_DIR/scope-guard-gate.sh"
GH_BIN="${GH_BIN:-gh}"
PY_BIN="${PY_BIN:-python3}"

RUN_CHECK_PR=true
ALLOW_LEGACY=false
PRINT_SUMMARY_ONLY=false
REPORT_FORMAT="text"
PRINT_FIX_DRAFTS=false
PRINT_FIX_DRAFTS_ONLY=false
PRINT_FIX_DRAFTS_COMPACT=false
PRINT_FIX_DRAFTS_ULTRA=false
PRINT_FIX_DRAFTS_ULTRA_TIGHT=false
OUT_FILE=""
AUTO_OUT=false
BASE_REF=""
RANGE_FROM=""
RANGE_TO=""
PRINT_FIX_HINTS=false
declare -a PR_NUMBERS=()

usage() {
  cat <<'EOF'
  Usage:
  ./scope-guard-batch.sh [--pr <번호> ...] [--range <시작> <종료>] [--legacy] [--no-check-pr] [--summary]
    (기본: PASS/WARN/FAIL 텍스트 요약)

Options:
  --pr             검증할 PR 번호(여러 번 사용 가능: --pr 1 --pr 2)
  --range          시작~끝 PR 번호(예: --range 1 8)
  --no-check-pr    check-pr 단계 생략
  --legacy         과거 PR 템플릿 형식 경고 모드 적용
  --summary        PASS/WARN/FAIL 요약만 출력(상세 로그는 실행 결과 뒤에 표시)
  --fix-hints      FAIL/WARN 요약 뒤에 스코프 가드 수정 가이드 출력
  --fix-drafts     FAIL/WARN 상세 뒤에 붙여넣기용 템플릿 초안 출력
  --fix-drafts-only  PR별 상세 로그를 생략하고 붙여넣기용 템플릿 초안만 출력
  --fix-drafts-compact  PR별 제목/코드/핵심 항목 2개만 출력(최소본)
  --fix-drafts-ultra  PR별 1줄 최소본 출력(코드/핵심 태그 2개)
  --fix-drafts-ultra-tight  --fix-drafts-ultra의 더 짧은 한 줄(제목 20자+)
  --format         출력 포맷(text, json, csv), 기본 text
  --out            실행 결과를 파일로 저장(콘솔에도 출력)
  --out-auto       기본 경로에 저장 (/tmp/scope-guard-batch-YYYYMMDD-HHMMSS.{txt,csv,json})
                   text: /tmp/scope-guard-batch-<timestamp>.txt
                   csv:  /tmp/scope-guard-batch-<timestamp>.csv
                   json: /tmp/scope-guard-batch-<timestamp>.json
  --help           사용법
EOF
}

need_arg() {
  if [[ -z "${2:-}" || "${2}" == --* ]]; then
    echo "error: $1 requires a value." >&2
    usage
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)
      need_arg "$1" "${2:-}"
      PR_NUMBERS+=("${2:-}")
      shift 2
      ;;
    --range)
      need_arg "$1" "${2:-}"
      need_arg "$1" "${3:-}"
      RANGE_FROM="$2"
      RANGE_TO="$3"
      shift 3
      ;;
    --no-check-pr)
      RUN_CHECK_PR=false
      shift
      ;;
    --legacy)
      ALLOW_LEGACY=true
      shift
      ;;
    --summary)
      PRINT_SUMMARY_ONLY=true
      shift
      ;;
    --fix-hints)
      PRINT_FIX_HINTS=true
      shift
      ;;
    --fix-drafts)
      PRINT_FIX_DRAFTS=true
      shift
      ;;
    --fix-drafts-compact)
      PRINT_FIX_DRAFTS_COMPACT=true
      shift
      ;;
    --fix-drafts-ultra)
      PRINT_FIX_DRAFTS_ULTRA=true
      shift
      ;;
    --fix-drafts-ultra-tight)
      PRINT_FIX_DRAFTS_ULTRA=true
      PRINT_FIX_DRAFTS_ULTRA_TIGHT=true
      shift
      ;;
    --fix-drafts-only)
      PRINT_FIX_DRAFTS_ONLY=true
      PRINT_FIX_DRAFTS=true
      shift
      ;;
    --format)
      need_arg "$1" "${2:-}"
      if [[ "$2" != "text" && "$2" != "json" && "$2" != "csv" ]]; then
        echo "error: --format accepts only text|json|csv." >&2
        usage
        exit 1
      fi
      REPORT_FORMAT="$2"
      shift 2
      ;;
    --out)
      need_arg "$1" "${2:-}"
      OUT_FILE="$2"
      shift 2
      ;;
    --out-auto)
      AUTO_OUT=true
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v "$GH_BIN" >/dev/null 2>&1; then
  for candidate in \
    "/usr/local/bin/gh" \
    "/opt/homebrew/bin/gh" \
    "$HOME/bin/gh" \
    "/Users/dohyeon/bin/gh"; do
    if [[ -x "$candidate" ]]; then
      GH_BIN="$candidate"
      break
    fi
  done
fi

if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "error: python3가 필요합니다." >&2
  exit 1
fi

if ! command -v "$GH_BIN" >/dev/null 2>&1; then
  echo "error: gh CLI가 필요합니다." >&2
  exit 1
fi

if [[ ! -x "$GATE_SCRIPT" ]]; then
  echo "error: gate 스크립트가 없습니다: $GATE_SCRIPT" >&2
  exit 1
fi

if [[ ${#PR_NUMBERS[@]} -eq 0 ]]; then
  if [[ -n "$RANGE_FROM" && -n "$RANGE_TO" ]]; then
    if ! [[ "$RANGE_FROM" =~ ^[0-9]+$ && "$RANGE_TO" =~ ^[0-9]+$ ]]; then
      echo "error: --range 값은 숫자여야 합니다." >&2
      exit 1
    fi
    if (( RANGE_FROM <= RANGE_TO )); then
      for ((n=RANGE_FROM; n<=RANGE_TO; n++)); do
        PR_NUMBERS+=("$n")
      done
    else
      echo "error: --range 시작값은 종료값보다 클 수 없습니다." >&2
      exit 1
    fi
  else
    echo "error: --pr 또는 --range 중 하나는 필요합니다." >&2
    usage
    exit 1
  fi
fi

if (( ${#PR_NUMBERS[@]} == 0 )); then
  echo "error: 점검할 PR 번호가 없습니다." >&2
  exit 1
fi

if [[ -z "$OUT_FILE" && "$AUTO_OUT" == true ]]; then
  TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
  case "$REPORT_FORMAT" in
    json)
      OUT_FILE="/tmp/scope-guard-batch-${TIMESTAMP}.json"
      ;;
    csv)
      OUT_FILE="/tmp/scope-guard-batch-${TIMESTAMP}.csv"
      ;;
    *)
      OUT_FILE="/tmp/scope-guard-batch-${TIMESTAMP}.txt"
      ;;
  esac
fi

if [[ -n "$OUT_FILE" ]]; then
  OUT_DIR="$(dirname -- "$OUT_FILE")"
  if [[ -n "$OUT_DIR" && "$OUT_DIR" != "." ]]; then
    mkdir -p "$OUT_DIR"
  fi
  : > "$OUT_FILE"
  BATCH_TMP_OUT="$(mktemp "${TMPDIR:-/tmp}/scope-guard-batch-output-XXXXXX")"

  finalize_output() {
    local rc=$?
    # shellcheck disable=SC2064
    trap - EXIT
    exec 1>&3
    exec 2>&4
    if [[ -n "${BATCH_TMP_OUT:-}" && -f "$BATCH_TMP_OUT" ]]; then
      cat "$BATCH_TMP_OUT" > "$OUT_FILE"
      cat "$BATCH_TMP_OUT" >&3
      rm -f "$BATCH_TMP_OUT"
    fi
    exit "$rc"
  }

  trap finalize_output EXIT
  exec 3>&1
  exec 4>&2
  exec >"$BATCH_TMP_OUT" 2>&1
fi

cd "$REPO_ROOT"
if [[ ! -f src/sia/cli.py ]]; then
  echo "error: SIA 프로젝트 루트에서 실행해 주세요." >&2
  exit 1
fi

sanitize_field() {
  local value="${1-}"
  printf '%s' "$value" | tr '\n\r\t' '   '
}

report_tail() {
  local pr="$1"
  local log_file="$2"
  echo "==== PR #${pr} 최근 로그 ===="
  if [[ -f "$log_file" && -s "$log_file" ]]; then
    tail -n 120 "$log_file"
  else
    echo "(empty or missing log)"
  fi
}

parse_gate_report() {
  local log_file="$1"
  "$PY_BIN" - "$log_file" <<'PY'
import json
import sys

path = sys.argv[1]
lines = open(path, encoding="utf-8", errors="ignore").read().splitlines()
report = None
events = []

for line in lines:
    if line.startswith("STRICT_GUARD_REPORT="):
        try:
            report = json.loads(line.split("=", 1)[1])
        except Exception:
            report = {}
    elif line.startswith("STRICT_GUARD_EVENTS="):
        try:
            events = json.loads(line.split("=", 1)[1])
        except Exception:
            events = []

if not report and not events:
    print("NO_REPORT\t\t\t\t")
    raise SystemExit(0)

blocked = list(report.get("blocked", []) or [])
critical = list(report.get("critical", []) or [])
warning = list(report.get("warning", []) or [])

all_codes = []
all_codes.extend(blocked)
all_codes.extend(critical)
all_codes.extend(warning)
if not events:
    events = []
for event in events:
    code = event.get("code")
    if code:
        all_codes.append(code)

if any(blocked) or any(critical):
    level = "CRITICAL"
elif warning:
    level = "WARNING"
else:
    level = "OK"

uniq_codes = ",".join(sorted(set(all_codes)))
print(
    "\t".join(
        [
            level,
            uniq_codes,
            ",".join(sorted(set(blocked))),
            ",".join(sorted(set(critical))),
            ",".join(sorted(set(warning))),
        ]
    )
)
PY
}

format_scope_hints() {
  local codes_csv="${1-}"
  local hints=()
  if [[ -z "$codes_csv" ]]; then
    hints+=("현재 PR에서 감지된 scope 가드 코드가 없어 가이드를 생략합니다.")
  else
    if [[ "$codes_csv" == *"SCOPE-MISSING-TELEGRAM"* ]]; then
      hints+=(" [SCOPE-MISSING-TELEGRAM] Goal/Requirements/Constraints/Acceptance에 텔레그램 알림 목적 및 트리거(매수/매도/보유 알림, 텔레그램 수신 대상, 실패 시 조치)을 명시하세요.")
    fi
    if [[ "$codes_csv" == *"SCOPE-UNKNOWN-SECTIONS"* ]]; then
      hints+=(" [SCOPE-UNKNOWN-SECTIONS] PR 본문 섹션을 표준만 사용하세요: Goal / Requirements / Constraints (must obey) / Acceptance criteria. 불필요한 섹션은 삭제하세요.")
    fi
    if [[ "$codes_csv" == *"SCOPE-EMPTY-SECTIONS"* ]]; then
      hints+=(" [SCOPE-EMPTY-SECTIONS] 각 필수 섹션에 실제 내용(빈칸/placeholder 없음)을 채우고, 목적·요구사항·검증 기준을 구체적으로 작성하세요.")
    fi
    if [[ "$codes_csv" == *"SCOPE-WEAK-SIGNAL"* ]]; then
      hints+=(" [SCOPE-WEAK-SIGNAL] 시그널 근거를 강화하세요: 데이터 소스, 계산식, 임계치(예: SMA/RSI/RSI score), 뉴스 반영 규칙, 쿨다운 조건을 Acceptance criteria에 수치로 넣으세요.")
    fi
  fi

  if (( ${#hints[@]} == 0 )); then
    return 0
  fi
  printf '%s\n' "== scope fix hints =="
  for h in "${hints[@]}"; do
    echo "$h"
  done
}

format_scope_fix_draft() {
  local pr="$1"
  local title="$2"
  local codes_csv="${3-}"

  local has_missing=false
  local has_unknown=false
  local has_empty=false
  local has_weak=false
  local need_codes=false

  if [[ "$codes_csv" == *"SCOPE-MISSING-TELEGRAM"* ]]; then
    has_missing=true
    need_codes=true
  fi
  if [[ "$codes_csv" == *"SCOPE-UNKNOWN-SECTIONS"* ]]; then
    has_unknown=true
    need_codes=true
  fi
  if [[ "$codes_csv" == *"SCOPE-EMPTY-SECTIONS"* ]]; then
    has_empty=true
    need_codes=true
  fi
  if [[ "$codes_csv" == *"SCOPE-WEAK-SIGNAL"* ]]; then
    has_weak=true
    need_codes=true
  fi
  if [[ -z "$codes_csv" || "$need_codes" == false ]]; then
    codes_csv="SCOPE-XXXX"
  fi

  echo "== scope fix draft =="
  echo "### Scope Guard Fix Draft for PR #${pr} (${title})"
  echo ""
  echo "### Scope Guard Fix Summary"
  echo "- [ ] 적용 코드: ${codes_csv}"
  echo "- [ ] 목표 방향 준수: 텔레그램 알림형(자동주문 없음)"
  echo ""
  echo "#### 수정된 핵심 섹션"
  echo "## Goal"
  echo "- 텔레그램 알림형으로 종가 기반 시그널(매수/매도/보류)만 계산하여 알림을 전송한다."
  echo "- 자동 주문/자동 매매 실행은 하지 않는다."
  echo ""
  echo "## Requirements"
  echo "- 텔레그램 알림 키워드(매수/매도/매도보류), 알림 대상 채널, 실패 대응이 본문에 존재해야 한다."
  echo "- 가격/뉴스 획득 주기, 데이터 소스, 쿼터 정책이 구체적으로 정의되어야 한다."
  if [[ "$has_weak" == true ]]; then
    echo "- SMA/RSI 임계치와 뉴스 반영 규칙 등 신호 산출 로직이 숫자 기준으로 명시되어야 한다."
  fi
  echo ""
  echo "## Constraints (must obey)"
  echo "- 텔레그램 알림 외의 자동 실행(자동 주문)은 금지한다."
  echo "- PR 템플릿은 Goal/Requirements/Constraints (must obey)/Acceptance criteria 4개 섹션으로 유지한다."
  echo ""
  echo "## Acceptance criteria"
  echo "- [ ] 텔레그램 알림 트리거, 텍스트 포맷, 실패 처리 규칙이 명시되어 있다."
  echo "- [ ] 수집 주기/중복 방지/쿨다운 규칙이 작성되어 있다."
  if [[ "$has_unknown" == true ]]; then
    echo "- [ ] 템플릿 섹션이 표준 형식 외 불필요 섹션 없이 구성된다."
  fi
  if [[ "$has_empty" == true ]]; then
    echo "- [ ] 각 섹션 내용이 비어 있지 않고 실제 운영 기준/테스트 계획이 들어간다."
  fi
}

format_scope_fix_draft_compact() {
  local pr="$1"
  local title="$2"
  local codes_csv="${3-}"

  if [[ -z "$codes_csv" ]]; then
    codes_csv="SCOPE-XXXX"
  fi

  echo "- PR #${pr}: ${title}"
  echo "  - 코드: ${codes_csv}"
  echo "  - 핵심 확인:"
  echo "    - 텔레그램 알림 트리거, 텍스트 포맷, 실패 처리 규칙이 명시되어 있다."
  echo "    - 수집 주기/중복 방지/쿨다운 규칙이 작성되어 있다."
}

format_scope_fix_draft_ultra() {
  local pr="$1"
  local title="$2"
  local codes_csv="${3-}"

  local title_short="$title"
  local telegram_note="telegram:있음"
  local sched_note="schedule:15m/cooldown/dup-check"

  if [[ -z "$codes_csv" ]]; then
    codes_csv="SCOPE-XXXX"
  fi

  if [[ "$PRINT_FIX_DRAFTS_ULTRA_TIGHT" == true ]]; then
    title_short="${title:0:24}"
    if [[ ${#title} -gt 24 ]]; then
      title_short="${title_short}..."
    fi
    telegram_note="tg"
    sched_note="sch"
  fi

  echo "#${pr}|${title_short}|${codes_csv}|${telegram_note}|${sched_note}"
}

declare -a SUMMARY_LINES=()
declare -a GATE_ARGS=()
SUMMARY_REPORT_FILE="/tmp/sia-batch-gate-summary-${$}.tsv"
: > "$SUMMARY_REPORT_FILE"
PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

if [[ "$RUN_CHECK_PR" == false ]]; then
  GATE_ARGS+=(--no-check-pr)
fi
if [[ "$ALLOW_LEGACY" == true ]]; then
  GATE_ARGS+=(--legacy)
fi

for PR in "${PR_NUMBERS[@]}"; do
  if ! [[ "$PR" =~ ^[0-9]+$ ]]; then
    SUMMARY_LINES+=("[$PR] SKIP: invalid-pr")
    ((FAIL_COUNT += 1))
    continue
  fi

  TITLE="$("$GH_BIN" pr view "$PR" --json title -q .title 2>/dev/null || true)"
  STATE="$("$GH_BIN" pr view "$PR" --json state -q .state 2>/dev/null || true)"
  if [[ -z "$TITLE" ]]; then
    SUMMARY_LINES+=("[$PR] SKIP: pr-not-found")
    ((FAIL_COUNT += 1))
    continue
  fi

  LOG_FILE="/tmp/sia-batch-gate-${PR}-$$.log"
  set +e
  if (( ${#GATE_ARGS[@]} > 0 )); then
    GH_BIN="$GH_BIN" "$GATE_SCRIPT" --pr "$PR" "${GATE_ARGS[@]}" > "$LOG_FILE" 2>&1
  else
    GH_BIN="$GH_BIN" "$GATE_SCRIPT" --pr "$PR" > "$LOG_FILE" 2>&1
  fi
  GATE_RC=$?
  set -e

  REPORT_PARSE_RESULT="$(parse_gate_report "$LOG_FILE")"
  read -r REPORT_LEVEL REPORT_CODES REPORT_BLOCKED REPORT_CRITICAL REPORT_WARNING <<<"${REPORT_PARSE_RESULT}"
  if [[ -z "${REPORT_LEVEL:-}" ]]; then
    REPORT_LEVEL="NO_REPORT"
    REPORT_CODES=""
    REPORT_BLOCKED=""
    REPORT_CRITICAL=""
    REPORT_WARNING=""
  fi

  if (( GATE_RC != 0 )); then
    STATUS="FAIL"
    ((FAIL_COUNT += 1))
  elif [[ "$REPORT_LEVEL" == "CRITICAL" ]]; then
    STATUS="FAIL"
    ((FAIL_COUNT += 1))
  elif [[ "$REPORT_LEVEL" == "WARNING" ]]; then
    STATUS="WARN"
    ((WARN_COUNT += 1))
  else
    STATUS="PASS"
    ((PASS_COUNT += 1))
  fi

  if [[ "$STATUS" == "PASS" ]]; then
    PREFIX="PASS"
  elif [[ "$STATUS" == "WARN" ]]; then
    PREFIX="WARN"
  else
    PREFIX="FAIL"
  fi

  SUMMARY_LINES+=("[$PR] $PREFIX | $STATE | ${TITLE:0:80}")
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$PR" \
    "$(sanitize_field "$STATE")" \
    "$(sanitize_field "${TITLE:0:80}")" \
    "$PREFIX" \
    "$GATE_RC" \
    "$REPORT_LEVEL" \
    "$(sanitize_field "$REPORT_BLOCKED")" \
    "$(sanitize_field "$REPORT_CRITICAL")" \
    "$(sanitize_field "$REPORT_WARNING")" \
    >> "$SUMMARY_REPORT_FILE"
  if [[ "$PRINT_FIX_DRAFTS_ULTRA" == true ]]; then
    echo "===== PR #$PR ====="
    format_scope_fix_draft_ultra "$PR" "${TITLE:0:80}" "${REPORT_CODES}"
  elif [[ "$PRINT_FIX_DRAFTS_COMPACT" == true ]]; then
    echo "===== PR #$PR ====="
    format_scope_fix_draft_compact "$PR" "${TITLE:0:80}" "${REPORT_CODES}"
  elif [[ "$PRINT_FIX_DRAFTS_ONLY" == true ]]; then
    echo "===== PR #$PR ====="
    format_scope_fix_draft "$PR" "${TITLE:0:80}" "${REPORT_CODES}"
  elif [[ "$PRINT_SUMMARY_ONLY" == false ]]; then
    echo "===== PR #$PR ====="
    cat "$LOG_FILE"
    if [[ "$PRINT_FIX_HINTS" == true ]]; then
      format_scope_hints "${REPORT_BLOCKED},${REPORT_CRITICAL},${REPORT_WARNING}"
    fi
    if [[ "$PRINT_FIX_DRAFTS" == true ]]; then
      format_scope_fix_draft "$PR" "${TITLE:0:80}" "${REPORT_CODES}"
    fi
  fi

  if [[ "$STATUS" == "FAIL" ]]; then
    if [[ "$PRINT_SUMMARY_ONLY" == true || "$PRINT_FIX_DRAFTS_ONLY" == true || "$PRINT_FIX_DRAFTS_COMPACT" == true || "$PRINT_FIX_DRAFTS_ULTRA" == true ]]; then
      report_tail "$PR" "$LOG_FILE"
    fi
  fi
done

echo ""
if [[ "$REPORT_FORMAT" != "text" && ("$PRINT_FIX_DRAFTS_ONLY" == true || "$PRINT_FIX_DRAFTS_COMPACT" == true || "$PRINT_FIX_DRAFTS_ULTRA" == true) ]]; then
  echo "error: --fix-drafts-* only support --format text." >&2
  rm -f "$SUMMARY_REPORT_FILE"
  exit 1
fi

if [[ "$PRINT_FIX_DRAFTS_ONLY" == true || "$PRINT_FIX_DRAFTS_COMPACT" == true || "$PRINT_FIX_DRAFTS_ULTRA" == true ]]; then
  echo "=== draft pack summary ==="
  echo "total=${#PR_NUMBERS[@]}, pass=${PASS_COUNT}, warn=${WARN_COUNT}, fail=${FAIL_COUNT}"
  rm -f "$SUMMARY_REPORT_FILE"
  if (( FAIL_COUNT > 0 )); then
    exit 2
  fi
  exit 0
fi

if [[ "$REPORT_FORMAT" == "json" ]]; then
  "$PY_BIN" - "$SUMMARY_REPORT_FILE" "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT" <<'PY'
import csv
import json
import sys

path = sys.argv[1]
pass_count = int(sys.argv[2] or 0)
warn_count = int(sys.argv[3] or 0)
fail_count = int(sys.argv[4] or 0)

rows = []
code_counts = {}
code_priority = {}

severity_priority = {"blocked": 2, "critical": 1, "warning": 0}
severity_label = {2: "BLOCKED", 1: "CRITICAL", 0: "WARNING"}

with open(path, encoding="utf-8", errors="ignore") as f:
    reader = csv.reader(f, delimiter="\t")
    for row in reader:
        if len(row) < 9:
            continue
        pr, state, title, status, exit_code, report_level, blocked, critical, warning = row[:9]
        rows.append({
            "pr": int(pr),
            "state": state,
            "title": title,
            "status": status,
            "exit_code": int(exit_code) if exit_code.isdigit() else exit_code,
            "report_level": report_level,
            "blocked_codes": [x for x in blocked.split(",") if x],
            "critical_codes": [x for x in critical.split(",") if x],
            "warning_codes": [x for x in warning.split(",") if x],
        })
        for code in [x for x in blocked.split(",") if x]:
            entry = code_counts.setdefault(code, {"frequency": 0, "priority": 0})
            entry["frequency"] += 1
            if severity_priority["blocked"] > entry["priority"]:
                entry["priority"] = severity_priority["blocked"]
        for code in [x for x in critical.split(",") if x]:
            entry = code_counts.setdefault(code, {"frequency": 0, "priority": 0})
            entry["frequency"] += 1
            if severity_priority["critical"] > entry["priority"]:
                entry["priority"] = severity_priority["critical"]
        for code in [x for x in warning.split(",") if x]:
            entry = code_counts.setdefault(code, {"frequency": 0, "priority": 0})
            entry["frequency"] += 1
            if severity_priority["warning"] > entry["priority"]:
                entry["priority"] = severity_priority["warning"]

code_summary = []
for code, value in sorted(
    code_counts.items(),
    key=lambda item: (-item[1]["frequency"], -item[1]["priority"], item[0]),
):
    code_summary.append({
        "code": code,
        "frequency": value["frequency"],
        "priority": severity_label[value["priority"]],
    })

print(json.dumps({
    "summary": {
        "total": len(rows),
        "pass": pass_count,
        "warn": warn_count,
        "fail": fail_count,
    },
    "results": rows,
    "code_summary": code_summary,
}, ensure_ascii=False, indent=2))
PY
 elif [[ "$REPORT_FORMAT" == "csv" ]]; then
  "$PY_BIN" - "$SUMMARY_REPORT_FILE" "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT" <<'PY'
import csv
import sys
from collections import Counter

path = sys.argv[1]
pass_count = int(sys.argv[2] or 0)
warn_count = int(sys.argv[3] or 0)
fail_count = int(sys.argv[4] or 0)

severity_order = {"blocked_codes": 2, "critical_codes": 1, "warning_codes": 0}
severity_label = {
    "blocked_codes": "BLOCKED",
    "critical_codes": "CRITICAL",
    "warning_codes": "WARNING",
}

code_counts = Counter()
code_priority = {}

rows = []
with open(path, encoding="utf-8", errors="ignore") as f:
    reader = csv.reader(f, delimiter="\t")
    for row in reader:
        if len(row) < 9:
            continue
        pr, state, title, status, exit_code, report_level, blocked, critical, warning = row[:9]
        rows.append([pr, state, title, status, exit_code, report_level, blocked, critical, warning])

        buckets = {
            "blocked_codes": [x for x in blocked.split(",") if x],
            "critical_codes": [x for x in critical.split(",") if x],
            "warning_codes": [x for x in warning.split(",") if x],
        }
        for bucket, codes in buckets.items():
            for code in codes:
                code_counts[code] += 1
                prev = code_priority.get(code)
                cur = severity_order[bucket]
                if prev is None or cur > prev:
                    code_priority[code] = cur

writer = csv.writer(sys.stdout)
writer.writerow([
    "pr",
    "state",
    "title",
    "status",
    "exit_code",
    "report_level",
    "blocked_codes",
    "critical_codes",
    "warning_codes",
])
for row in rows:
    writer.writerow(row)
writer.writerow([])
writer.writerow(["summary_total", len(rows)])
writer.writerow(["summary_pass", pass_count])
writer.writerow(["summary_warn", warn_count])
writer.writerow(["summary_fail", fail_count])
writer.writerow([])
writer.writerow(["code_summary"])
writer.writerow(["code", "frequency", "priority"])
for code in sorted(code_counts, key=lambda k: (-code_counts[k], -code_priority[k], k)):
    priority_key = code_priority[code]
    priority_label = "WARNING" if priority_key == 0 else ("CRITICAL" if priority_key == 1 else "BLOCKED")
    writer.writerow([code, code_counts[code], priority_label])
PY
else
  "$PY_BIN" - "$SUMMARY_REPORT_FILE" <<'PY'
import csv
import sys

path = sys.argv[1]
counts = {}

def add_code(code, level):
    if not code:
        return
    entry = counts.setdefault(code, {"frequency": 0, "priority": 0})
    entry["frequency"] += 1
    priority = 2 if level == "BLOCKED" else 1 if level == "CRITICAL" else 0
    if priority > entry["priority"]:
        entry["priority"] = priority

with open(path, encoding="utf-8", errors="ignore") as f:
    reader = csv.reader(f, delimiter="\t")
    for row in reader:
        if len(row) < 9:
            continue
        _, _, _, _, _, _, blocked, critical, warning = row[:9]
        for code in [x for x in blocked.split(",") if x]:
            add_code(code, "BLOCKED")
        for code in [x for x in critical.split(",") if x]:
            add_code(code, "CRITICAL")
        for code in [x for x in warning.split(",") if x]:
            add_code(code, "WARNING")

if counts:
    order = {2: "BLOCKED", 1: "CRITICAL", 0: "WARNING"}
    summary_rows = sorted(
        ((code, data["frequency"], order[data["priority"]]) for code, data in counts.items()),
        key=lambda item: (-item[1], -(2 if item[2] == "BLOCKED" else 1 if item[2] == "CRITICAL" else 0), item[0]),
    )
    print("=== code summary ===")
    print("code | count | priority")
    print("---------------------------")
    for code, freq, priority in summary_rows:
        print(f"{code} | {freq} | {priority}")

PY
  echo "=== batch summary ==="
  for L in "${SUMMARY_LINES[@]}"; do
    echo "$L"
  done
  echo "total=${#PR_NUMBERS[@]}, pass=${PASS_COUNT}, warn=${WARN_COUNT}, fail=${FAIL_COUNT}"
fi

rm -f "$SUMMARY_REPORT_FILE"

if [[ "$PRINT_SUMMARY_ONLY" == true ]]; then
  if [[ "$PRINT_FIX_DRAFTS_ONLY" == true ]]; then
    echo "=== draft pack summary ==="
    echo "total=${#PR_NUMBERS[@]}, pass=${PASS_COUNT}, warn=${WARN_COUNT}, fail=${FAIL_COUNT}"
    if (( FAIL_COUNT > 0 )); then
      exit 2
    fi
    exit 0
  fi
  exit 0
fi

if (( FAIL_COUNT > 0 )); then
  exit 2
fi
exit 0
