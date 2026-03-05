#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GH_BIN="${GH_BIN:-gh}"
PY_BIN="${PY_BIN:-python3}"
BODY_FILE="${BODY_FILE:-/tmp/sia-pr-body.md}"
PARSE_LOG="${PARSE_LOG:-/tmp/sia-pr-parse.log}"
CHECK_LOG="${CHECK_LOG:-/tmp/sia-pr-check.log}"
APPLY_TEMPLATE=false
RUN_CHECK_PR=true
DRY_ONLY=false
PR_NUMBER=""
BASE_REF=""
BODY_OVERRIDE=""
FILE_LIST=""
ALLOW_LEGACY_TEMPLATE=false

usage() {
  cat <<'EOF'
Usage:
  ./scope-guard-pr-preflight.sh --pr <PR번호> [--body-file <path>] [--base <ref>] [--check-pr|--no-check-pr] [--apply-template] [--dry-run]

Options:
  --pr              대상 PR 번호. 미지정 시 --body-file 필요
  --body-file       PR 본문 텍스트를 직접 지정
  --base            check-pr 대상 계산용 기준 브랜치(기본: PR base 또는 origin/main)
  --check-pr        변경 파일 체크 실행 (기본 실행)
  --no-check-pr     check-pr 비활성화
  --apply-template  실패 시 scope fix 템플릿을 PR 본문에 자동 적용
  --dry-run         적용만 확인(gh edit 미수행)
  --allow-legacy-template 과거 PR 템플릿 형식은 경고만 반영
  --legacy          --allow-legacy-template 별칭
  --help            사용법 표시
EOF
}

need_arg() {
  local name="$1"
  local next="${2:-}"
  if [[ -z "$next" || "$next" == --* ]]; then
    echo "error: $name requires a value." >&2
    usage
    exit 1
  fi
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
      BODY_OVERRIDE="$2"
      shift 2
      ;;
    --base)
      need_arg "$1" "${2:-}"
      BASE_REF="$2"
      shift 2
      ;;
    --check-pr)
      RUN_CHECK_PR=true
      shift
      ;;
    --no-check-pr)
      RUN_CHECK_PR=false
      shift
      ;;
    --apply-template)
      APPLY_TEMPLATE=true
      shift
      ;;
    --dry-run)
      DRY_ONLY=true
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
      echo "error: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -n "$PR_NUMBER" && -n "$BODY_OVERRIDE" ]]; then
  echo "error: --pr와 --body-file은 동시에 사용할 수 없습니다. 하나만 지정하세요." >&2
  usage
  exit 1
fi

if ! command -v "$PY_BIN" >/dev/null 2>&1; then
  echo "error: python3 가 필요합니다." >&2
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

cd "$REPO_ROOT"

if [[ ! -f "$REPO_ROOT/src/sia/cli.py" ]]; then
  echo "error: SIA 프로젝트 루트에서 실행해 주세요." >&2
  exit 1
fi

if [[ -z "$BODY_OVERRIDE" && -z "$PR_NUMBER" ]]; then
  echo "error: --pr 또는 --body-file 중 하나는 필요합니다." >&2
  usage
  exit 1
fi

if [[ -n "$BODY_OVERRIDE" && ! -f "$BODY_OVERRIDE" ]]; then
  echo "error: --body-file 경로가 없습니다: $BODY_OVERRIDE" >&2
  exit 1
fi

if [[ -n "$BODY_OVERRIDE" ]]; then
  BODY_FILE="$BODY_OVERRIDE"
else
  if ! command -v "$GH_BIN" >/dev/null 2>&1; then
    echo "error: gh CLI가 필요합니다." >&2
    exit 1
  fi
  if [[ -z "$PR_NUMBER" ]]; then
    PR_NUMBER="$("$GH_BIN" pr view --json number -q .number 2>/dev/null || true)"
    if [[ -z "$PR_NUMBER" ]]; then
      echo "error: 현재 브랜치 PR이 없어 --pr 또는 --body-file가 필요합니다." >&2
      exit 1
    fi
  fi

  PR_TITLE="$("$GH_BIN" pr view "$PR_NUMBER" --json title -q .title 2>/dev/null || true)"
  PR_BODY="$("$GH_BIN" pr view "$PR_NUMBER" --json body -q .body 2>/dev/null || true)"
  printf '# %s\n\n%s\n' "$PR_TITLE" "$PR_BODY" > "$BODY_FILE"
fi

echo "== parse-issue (strict) =="
PARSE_RC=0
set +e
PY_PARSE_ARGS=(--file "$BODY_FILE" --strict)
if [[ "$ALLOW_LEGACY_TEMPLATE" == true ]]; then
  PY_PARSE_ARGS+=(--allow-legacy-template)
fi
"$PY_BIN" -m src.sia.cli parse-issue "${PY_PARSE_ARGS[@]}" > "$PARSE_LOG" 2>&1
PARSE_RC=$?
set -e
cat "$PARSE_LOG"

get_codes() {
  local py_bin="$PY_BIN"
  "$py_bin" - "$1" <<'PY'
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

codes = []
if report:
  for key in ("blocked", "critical", "warning"):
    for code in report.get(key, []) or []:
      if code:
        codes.append(code)
for ev in events or []:
  code = ev.get("code")
  if code:
    codes.append(code)
print(",".join(sorted(set(codes))) )
PY
}

SCOPE_CODES="$(get_codes "$PARSE_LOG")"
if [[ -n "$SCOPE_CODES" ]]; then
  echo "scope codes: $SCOPE_CODES"
fi

if [[ "$PARSE_RC" -ne 0 ]]; then
  echo "parse-issue --strict: FAILED (exit=$PARSE_RC)"
else
  echo "parse-issue --strict: OK"
fi

CHECK_RC=0
if [[ "$RUN_CHECK_PR" == true && -n "$PR_NUMBER" ]]; then
  if [[ -z "$BASE_REF" ]]; then
    BASE_REF="$("$GH_BIN" pr view "$PR_NUMBER" --json baseRefName -q .baseRefName 2>/dev/null || true)"
  fi
  if [[ -z "$BASE_REF" ]]; then
    BASE_REF="origin/main"
  fi

  if ! git rev-parse --verify "$BASE_REF" >/dev/null 2>&1; then
    echo "warn: base ref '$BASE_REF' 미확인. diff 계산 생략"
  else
    FILE_LIST="$(git diff --name-only "${BASE_REF}...HEAD" | tr '\n' ',' | sed 's/,$//')"
  fi

  if [[ -n "$FILE_LIST" ]]; then
    echo "== check-pr (files: ${FILE_LIST}) =="
    if ! "$PY_BIN" -m src.sia.cli check-pr --files "$FILE_LIST" > "$CHECK_LOG" 2>&1; then
      CHECK_RC=$?
      cat "$CHECK_LOG"
    else
      cat "$CHECK_LOG"
    fi
  else
    echo "warn: 변경 파일 목록이 비어 있어 check-pr 생략."
  fi
fi

if [[ "$RUN_CHECK_PR" == false ]]; then
  echo "info: check-pr disabled by --no-check-pr."
fi

if [[ "$PARSE_RC" -ne 0 && "$APPLY_TEMPLATE" == true && -n "$PR_NUMBER" ]]; then
  if [[ "$DRY_ONLY" == true ]]; then
    echo "dry-run: --apply-template 건너뜀(실제 갱신 없음)"
  else
    echo "== apply scope-guard template =="
    if [[ -n "$SCOPE_CODES" ]]; then
      "$SCRIPT_DIR/gh-apply-scope-fix-template.sh" --pr "$PR_NUMBER" --codes "$SCOPE_CODES"
    else
      "$SCRIPT_DIR/gh-apply-scope-fix-template.sh" --pr "$PR_NUMBER"
    fi
  fi
elif [[ "$PARSE_RC" -ne 0 && "$APPLY_TEMPLATE" == true ]]; then
  echo "info: --apply-template은 --pr 모드에서만 동작합니다. body-file 모드면 템플릿은 수동 적용하세요."
fi

if [[ "$PARSE_RC" -ne 0 || "$CHECK_RC" -ne 0 ]]; then
  echo "result: preflight failed"
  exit 2
fi

echo "result: preflight passed"
