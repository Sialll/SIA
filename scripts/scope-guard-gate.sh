#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RUN_ID="$(date +%s)-$$"

PY_BIN="${PY_BIN:-python3}"
GH_BIN="${GH_BIN:-gh}"
PRE_FLIGHT_SCRIPT="$SCRIPT_DIR/scope-guard-pr-preflight.sh"
APPLY_TEMPLATE_SCRIPT="$SCRIPT_DIR/gh-apply-scope-fix-template.sh"

PR_NUMBER=""
BODY_FILE=""
BASE_REF=""
RUN_CHECK_PR=true
AUTO_TEMPLATE=false
DRY_TEMPLATE=false
ALLOW_LEGACY_TEMPLATE=false
MAX_ATTEMPTS=2

usage() {
  cat <<'EOF'
Usage:
  ./scope-guard-gate.sh --pr <PR번호> [옵션]
  ./scope-guard-gate.sh --body-file <path> --no-check-pr [옵션]

Options:
  --pr              PR 번호
  --body-file       PR 본문이 저장된 파일(로컬 검증용)
  --base            check-pr 기준 브랜치(기본: PR base 또는 origin/main)
  --no-check-pr     PR 파일 점검 생략
  --apply-template  parse strict 실패 시 Scope Fix 템플릿 자동 적용(가능한 경우)
  --dry-run-template 템플릿 적용 미리보기(실제 PR 수정 없음)
  --allow-legacy-template 과거 PR 템플릿 형식은 경고만 반영
  --legacy          --allow-legacy-template 별칭
  --help            사용법
EOF
}

need_arg() {
  if [[ -z "${2:-}" || "${2}" == --* ]]; then
    echo "error: $1 requires a value." >&2
    usage
    exit 1
  fi
}

extract_scope_codes() {
  local path="$1"
  local py_bin="$PY_BIN"
  "$py_bin" - "$path" <<'PY'
import json
import sys

path = sys.argv[1]
codes = []
report = None
events = []

for line in open(path, encoding="utf-8", errors="ignore").read().splitlines():
    if line.startswith("STRICT_GUARD_REPORT="):
        try:
            report = json.loads(line[len("STRICT_GUARD_REPORT="):])
        except Exception:
            report = {}
    elif line.startswith("STRICT_GUARD_EVENTS="):
        try:
            events = json.loads(line[len("STRICT_GUARD_EVENTS="):])
        except Exception:
            events = []

if report:
    for key in ("blocked", "critical", "warning"):
        for code in report.get(key, []) or []:
            if code:
                codes.append(code)

for ev in events or []:
    code = ev.get("code")
    if code:
        codes.append(code)

print(",".join(sorted(set(codes))))
PY
}

run_preflight() {
  local attempt="$1"
  local out_file="$2"
  shift 2

  local parse_log="/tmp/sia-gate-parse-${RUN_ID}-${attempt}.log"
  local check_log="/tmp/sia-gate-check-${RUN_ID}-${attempt}.log"
  local rc=0

  set +e
  PARSE_LOG="$parse_log" CHECK_LOG="$check_log" "$PRE_FLIGHT_SCRIPT" "$@" > "$out_file" 2>&1
  rc=$?
  set -e

  PREV_PARSE_LOG="$parse_log"
  PREV_OUT="$out_file"
  PREV_RC=$rc
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)
      need_arg "$1" "${2:-}"
      PR_NUMBER="$2"
      shift 2
      ;;
    --body-file)
      need_arg "$1" "${2:-}"
      BODY_FILE="$2"
      shift 2
      ;;
    --base)
      need_arg "$1" "${2:-}"
      BASE_REF="$2"
      shift 2
      ;;
    --no-check-pr)
      RUN_CHECK_PR=false
      shift
      ;;
    --apply-template)
      AUTO_TEMPLATE=true
      shift
      ;;
    --dry-run-template)
      DRY_TEMPLATE=true
      shift
      ;;
    --allow-legacy-template)
      ALLOW_LEGACY_TEMPLATE=true
      shift
      ;;
    --legacy)
      ALLOW_LEGACY_TEMPLATE=true
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown arg: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$PR_NUMBER" && -n "$BODY_FILE" ]]; then
  echo "error: --pr와 --body-file은 동시에 사용할 수 없습니다. 하나만 지정하세요." >&2
  usage
  exit 1
fi

if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "error: python3 이 필요합니다." >&2
  exit 1
fi

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

if [[ ! -x "$PRE_FLIGHT_SCRIPT" ]]; then
  echo "error: 사전 점검 스크립트가 없거나 실행 불가입니다: $PRE_FLIGHT_SCRIPT" >&2
  exit 1
fi

if [[ ! -x "$APPLY_TEMPLATE_SCRIPT" ]]; then
  echo "error: 템플릿 적용 스크립트가 없거나 실행 불가입니다: $APPLY_TEMPLATE_SCRIPT" >&2
  exit 1
fi

cd "$REPO_ROOT"
if [[ ! -f src/sia/cli.py ]]; then
  echo "error: SIA 프로젝트 루트에서 실행해 주세요." >&2
  exit 1
fi

if [[ -n "$PR_NUMBER" ]] && ! command -v "$GH_BIN" >/dev/null 2>&1; then
  echo "error: gh CLI가 필요합니다. (PR mode)" >&2
  exit 1
fi

if [[ -n "$BODY_FILE" && ! -f "$BODY_FILE" ]]; then
  echo "error: body-file이 존재하지 않습니다: $BODY_FILE" >&2
  exit 1
fi

if [[ -z "$PR_NUMBER" && -z "$BODY_FILE" ]]; then
  if ! command -v "$GH_BIN" >/dev/null 2>&1; then
    echo "error: --pr 또는 --body-file가 없고, 현재 브랜치 PR 탐지를 위해 gh CLI가 필요합니다." >&2
    usage
    exit 1
  fi
  PR_NUMBER="$("$GH_BIN" pr view --json number -q .number 2>/dev/null || true)"
  if [[ -z "$PR_NUMBER" ]]; then
    echo "error: --pr 또는 --body-file 중 하나를 지정해 주세요." >&2
    usage
    exit 1
  fi
fi

if [[ -n "$PR_NUMBER" && "$RUN_CHECK_PR" == true && -z "$BASE_REF" ]]; then
  BASE_REF="origin/main"
fi

if [[ "$RUN_CHECK_PR" == true && -z "$PR_NUMBER" ]]; then
  RUN_CHECK_PR=false
fi

if [[ "$AUTO_TEMPLATE" == true && -z "$PR_NUMBER" ]]; then
  echo "info: --body-file 모드에서는 템플릿 자동 적용이 불가합니다. body-text 재검토 후 PR 모드로 수동 재시작하세요."
fi

PRE_FLIGHT_ARGS=()
if [[ -n "$PR_NUMBER" ]]; then
  PRE_FLIGHT_ARGS+=(--pr "$PR_NUMBER")
else
  PRE_FLIGHT_ARGS+=(--body-file "$BODY_FILE")
fi

if [[ -n "$BASE_REF" ]]; then
  PRE_FLIGHT_ARGS+=(--base "$BASE_REF")
fi
if [[ "$RUN_CHECK_PR" == false ]]; then
  PRE_FLIGHT_ARGS+=(--no-check-pr)
fi
if [[ "$ALLOW_LEGACY_TEMPLATE" == true ]]; then
  PRE_FLIGHT_ARGS+=(--allow-legacy-template)
fi

attempt=1
while true; do
  PRE_OUT="/tmp/sia-gate-preflight-${RUN_ID}-${attempt}.log"
  run_preflight "$attempt" "$PRE_OUT" "${PRE_FLIGHT_ARGS[@]}"

  echo "== Scope Gate attempt ${attempt} =="
  cat "$PRE_OUT"

  if [[ "$PREV_RC" -eq 0 ]]; then
    echo "result: gate passed"
    exit 0
  fi

  if [[ "$AUTO_TEMPLATE" != true || "$attempt" -gt 1 || -z "$PR_NUMBER" ]]; then
    break
  fi

  if ! grep -q "parse-issue --strict: FAILED" "$PREV_OUT"; then
    break
  fi

  SCOPE_CODES="$(extract_scope_codes "$PREV_PARSE_LOG")"
  if [[ -z "$SCOPE_CODES" ]]; then
    SCOPE_CODES="SCOPE-XXXX"
  fi

  if [[ "$DRY_TEMPLATE" == true ]]; then
    echo "== scope fix template (dry-run) =="
    "$APPLY_TEMPLATE_SCRIPT" --pr "$PR_NUMBER" --codes "$SCOPE_CODES" --dry-run
    echo "dry-run complete: remove --dry-run-template to apply."
    break
  fi

  echo "== scope fix template apply =="
  "$APPLY_TEMPLATE_SCRIPT" --pr "$PR_NUMBER" --codes "$SCOPE_CODES"
  echo "applied scope template. retrying..."
  attempt=$((attempt + 1))
  if [[ "$attempt" -gt "$MAX_ATTEMPTS" ]]; then
    break
  fi
  continue
done

echo "result: gate failed"
exit 2
