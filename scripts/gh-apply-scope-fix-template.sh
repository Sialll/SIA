#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_PATH="${SCRIPT_DIR}/scope-guard-fix-template.md"
DEFAULT_GH_CMD="gh"
GH_CMD="${GH_BIN:-${GH:-$DEFAULT_GH_CMD}}"
OUTPUT_FILE="/tmp/sia-pr-guard-body.md"
SUMMARY_FILE="/tmp/guard-summary.json"
DRY_RUN=false
PR_NUMBER=""
SCOPE_CODES=""
POSITION="prepend"

usage() {
  cat <<'EOF'
Usage:
  ./gh-apply-scope-fix-template.sh --pr <PR_NUMBER> [--codes "SCOPE-XXX,SCOPE-YYY"] [--append] [--dry-run]

Options:
  --pr            대상 PR 번호(미지정 시 현재 브랜치와 연결된 열린 PR 탐색)
  --codes         템플릿 안의 `SCOPE-XXXX`를 치환할 코드 목록(쉼표 구분)
  --append        템플릿을 본문 뒤에 추가(기본은 본문 앞에 추가)
  --dry-run       PR 수정 없이 최종 본문만 출력
  --help          사용법 출력
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pr)
      if [[ $# -lt 2 || "${2:-}" == --* ]]; then
        echo "error: --pr requires a PR number" >&2
        usage
        exit 1
      fi
      PR_NUMBER="${2:-}"
      shift 2
      ;;
    --codes)
      if [[ $# -lt 2 || "${2:-}" == --* ]]; then
        echo "error: --codes requires comma-separated codes" >&2
        usage
        exit 1
      fi
      SCOPE_CODES="${2:-}"
      shift 2
      ;;
    --append)
      POSITION="append"
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v "$GH_CMD" >/dev/null 2>&1; then
  echo "error: gh CLI가 필요합니다. (PATH 또는 GH_BIN 환경변수 확인)" >&2
  exit 1
fi

if [[ ! -f "$TEMPLATE_PATH" ]]; then
  echo "error: 템플릿 파일이 없습니다: $TEMPLATE_PATH" >&2
  exit 1
fi

if [[ -z "$PR_NUMBER" ]]; then
  PR_NUMBER="$("$GH_CMD" pr view --json number -q .number 2>/dev/null || true)"
  if [[ -z "$PR_NUMBER" ]]; then
    echo "error: 현재 브랜치의 PR 번호를 찾지 못했습니다. --pr <번호>를 지정하세요." >&2
    exit 1
  fi
fi

if [[ -z "$SCOPE_CODES" && -f "$SUMMARY_FILE" ]]; then
  SCOPE_CODES="$(python3 - "$SUMMARY_FILE" <<'PY'
import json
import sys

path = sys.argv[1]
try:
    payload = json.loads(open(path, encoding="utf-8").read())
except Exception:
    sys.exit(0)

codes = []
report = payload.get("report") or {}
events = payload.get("events") or []

for key in ("blocked", "critical", "warning"):
    for code in report.get(key, []) or []:
        if code:
            codes.append(code)

for event in events:
    code = event.get("code")
    if code:
        codes.append(code)

if not codes:
    sys.exit(0)

uniq = sorted(dict.fromkeys(codes))
print(",".join(uniq))
PY
  )"
fi

if [[ -z "$SCOPE_CODES" ]]; then
  SCOPE_CODES="SCOPE-XXXX"
fi

TEMPLATE_BODY="$(cat "$TEMPLATE_PATH")"
TEMPLATE_BODY="${TEMPLATE_BODY//SCOPE-XXXX/$SCOPE_CODES}"

CURRENT_BODY="$("$GH_CMD" pr view "$PR_NUMBER" --json body -q .body 2>/dev/null || true)"

if printf '%s\n' "$CURRENT_BODY" | grep -q '^### Scope Guard Fix Summary$'; then
  echo "info: PR 본문에 Scope Guard Fix Summary가 이미 있습니다. 중복 삽입을 방지합니다."
  exit 0
fi

if [[ "$POSITION" == "append" ]]; then
  printf '%s\n\n%s\n' "$CURRENT_BODY" "$TEMPLATE_BODY" > "$OUTPUT_FILE"
else
  printf '%s\n\n%s\n' "$TEMPLATE_BODY" "$CURRENT_BODY" > "$OUTPUT_FILE"
fi

if [[ "$DRY_RUN" == true ]]; then
  cat "$OUTPUT_FILE"
  echo "---"
  echo "dry-run only: PR #$PR_NUMBER 미변경"
  exit 0
fi

"$GH_CMD" pr edit "$PR_NUMBER" --body-file "$OUTPUT_FILE"
POSITION_LABEL="prepended"
if [[ "$POSITION" == "append" ]]; then
  POSITION_LABEL="appended"
fi
echo "updated: PR #$PR_NUMBER body ${POSITION_LABEL} with scope fix summary"
