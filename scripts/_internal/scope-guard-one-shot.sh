#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_SCRIPT="$SCRIPT_DIR/scope-guard-gate.sh"

MODE="range"
START_PR="1"
END_PR="8"
APPLY_TEMPLATE_RAW="${SCOPE_GUARD_APPLY_TEMPLATE:-true}"
APPLY_TEMPLATE="true"
SKIP=0
declare -a PR_NUMBERS=()
GH_DEFAULT_CANDIDATES=(
  "/Users/dohyeon/bin/gh"
  "/usr/local/bin/gh"
  "/opt/homebrew/bin/gh"
  "$HOME/bin/gh"
  "gh"
)

resolve_gh() {
  if [[ -n "${GH_BIN:-}" ]] && [[ -x "${GH_BIN}" ]]; then
    echo "${GH_BIN}"
    return 0
  fi
  if [[ -n "${GH:-}" ]] && [[ -x "${GH}" ]]; then
    echo "${GH}"
    return 0
  fi
  for candidate in "${GH_DEFAULT_CANDIDATES[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 || [[ -x "$candidate" ]]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

parse_bool() {
  local value="${1:-}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    1|true|yes|on)
      echo true
      ;;
    0|false|no|off)
      echo false
      ;;
    *)
      echo true
      echo "warn: unknown SCOPE_GUARD_APPLY_TEMPLATE='$1', fallback=true" >&2
      ;;
  esac
}

collect_open_pr_numbers_with_gh() {
  "$GH_BIN" pr list --state open --json number -q ".[].number" 2>/dev/null || return 1
}

collect_open_pr_numbers_from_api() {
  local repo="${1:-}"
  local token="${2:-}"
  GITHUB_TOKEN="$token" python3 - "$repo" <<'PY'
import json
import os
import urllib.request
import sys

repo = sys.argv[1]
token = os.environ.get("GITHUB_TOKEN", "").strip()
url = f"https://api.github.com/repos/{repo}/pulls?state=open&per_page=100"
headers = {"User-Agent": "scope-guard-one-shot", "Accept": "application/vnd.github+json"}
if token:
    headers["Authorization"] = f"Bearer {token}"

with urllib.request.urlopen(
    urllib.request.Request(url, headers=headers),
    timeout=30,
) as response:
    raw = response.read().decode("utf-8")

items = json.loads(raw)
for item in items:
    number = item.get("number")
    if isinstance(number, int):
        print(number)
PY
}

usage() {
  cat <<'EOF'
Usage:
  ./scope-guard-one-shot.sh [start_pr] [end_pr]
  ./scope-guard-one-shot.sh open

Examples:
  ./scope-guard-one-shot.sh                # 기본 1~8
  ./scope-guard-one-shot.sh 1 12          # 1~12
  ./scope-guard-one-shot.sh open           # 현재 열린 PR 전체
  SCOPE_GUARD_APPLY_TEMPLATE=false ./scripts/_internal/scope-guard-one-shot.sh open
EOF
}

resolve_open_repo() {
  local repo="${GITHUB_REPOSITORY:-}"
  if [[ -n "$repo" ]]; then
    echo "$repo"
    return 0
  fi

  local remote
  remote="$(git config --get remote.origin.url 2>/dev/null || true)"
  if [[ -z "$remote" ]]; then
    return 1
  fi

  if [[ "$remote" == https://github.com/* ]]; then
    remote="${remote#https://github.com/}"
  elif [[ "$remote" == git@github.com:* ]]; then
    remote="${remote#git@github.com:}"
  else
    return 1
  fi

  remote="${remote%.git}"
  echo "$remote"
}

collect_open_pr_numbers() {
  if command -v "$GH_BIN" >/dev/null 2>&1; then
    collect_open_pr_numbers_with_gh
    return $?
  fi

  local repo
  repo="$(resolve_open_repo || true)"
  if [[ -z "$repo" ]]; then
    return 1
  fi

  collect_open_pr_numbers_from_api "$repo" "${GITHUB_TOKEN:-${GH_TOKEN:-}}" 
}

resolve_args() {
  local arg_count=$#
  if (( arg_count == 0 )); then
    return 0
  fi

  case "${1}" in
    -h|--help)
      usage
      exit 0
      ;;
    open|--open|--open-prs)
      MODE="open"
      shift
      if (( $# != 0 )); then
        echo "error: 'open' mode does not accept start/end arguments." >&2
        usage
        exit 1
      fi
      ;;
    *)
      if (( arg_count != 2 )); then
        echo "error: range mode requires two arguments: start_pr end_pr." >&2
        usage
        exit 1
      fi
      START_PR="$1"
      END_PR="$2"
      ;;
  esac
}

if [[ "${START_PR}" == "-h" || "${START_PR}" == "--help" ]]; then
  usage
  exit 0
fi

resolve_args "$@"
APPLY_TEMPLATE="$(parse_bool "$APPLY_TEMPLATE_RAW")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required." >&2
  exit 1
fi

GH_BIN="$(resolve_gh || true)"
if [[ -z "${GH_BIN}" ]] || ! command -v "${GH_BIN}" >/dev/null 2>&1; then
  echo "error: gh CLI is required." >&2
  exit 1
fi

if [[ "$MODE" == "open" ]]; then
  OPEN_PR_RAW="$(collect_open_pr_numbers || true)"
  if [[ -z "${OPEN_PR_RAW}" ]]; then
    echo "result: no open PRs found"
    echo "summary: mode=open, pass=0, fail=0, skip=0"
    exit 0
  fi
  while IFS= read -r pr; do
    pr="${pr#$'\r'}"
    if [[ -n "$pr" ]]; then
      PR_NUMBERS+=("$pr")
    fi
  done <<<"$(printf '%s\n' "$OPEN_PR_RAW" | sed '/^[[:space:]]*$/d' | sort -nu)"
else
  if [[ ! "$START_PR" =~ ^[0-9]+$ || ! "$END_PR" =~ ^[0-9]+$ ]]; then
    echo "error: start/end must be numeric." >&2
    usage
    exit 1
  fi

  if (( START_PR > END_PR )); then
    echo "error: start_pr cannot be greater than end_pr." >&2
    usage
    exit 1
  fi

  for ((n=START_PR; n<=END_PR; n++)); do
    PR_NUMBERS+=("$n")
  done
fi

if [[ "${#PR_NUMBERS[@]}" -eq 0 ]]; then
  echo "error: no PR numbers to check." >&2
  exit 1
fi

if [[ ! -x "$GATE_SCRIPT" ]]; then
  echo "error: gate script missing: $GATE_SCRIPT" >&2
  exit 1
fi

export PY_BIN="${PY_BIN:-python3}"
export GH_BIN="${GH_BIN:-gh}"

show_gate_fail_snippet() {
  local pr="$1"
  local log_file="$2"
  local lines="${3:-120}"
  echo "===== PR #${pr} gate failure (last ${lines} lines) ====="
  if [[ -f "$log_file" && -s "$log_file" ]]; then
    tail -n "$lines" "$log_file"
  else
    echo "(empty or missing log)"
  fi
}

run_gate_for_pr() {
  local pr="$1"
  local log_file="$2"
  if [[ "$APPLY_TEMPLATE" == true ]]; then
    "$GATE_SCRIPT" --pr "$pr" --legacy --no-check-pr --apply-template > "$log_file" 2>&1
  else
    "$GATE_SCRIPT" --pr "$pr" --legacy --no-check-pr > "$log_file" 2>&1
  fi
}

PASS=0
FAIL=0

for pr in "${PR_NUMBERS[@]}"; do
  if [[ ! "$pr" =~ ^[0-9]+$ ]]; then
    SKIP=$((SKIP + 1))
    echo "===== PR ${pr} (skip: invalid number) ====="
    continue
  fi

  GATE_LOG="/tmp/sia-one-shot-gate-${pr}-$$.log"
  set +e
  run_gate_for_pr "$pr" "$GATE_LOG"
  GATE_RC=$?
  set -e

  echo "===== PR #${pr} ====="
  if [[ "$GATE_RC" -eq 0 ]]; then
    PASS=$((PASS + 1))
  else
    echo "PR #${pr}: auto-fix attempted but failed after template retry. exit=$GATE_RC"
    show_gate_fail_snippet "$pr" "$GATE_LOG"
    FAIL=$((FAIL + 1))
  fi
done

echo
echo "=== one-shot summary ==="
if [[ "$MODE" == "open" ]]; then
  echo "scope=open"
else
  echo "scope=${START_PR}-${END_PR}"
fi
echo "pass=${PASS}, fail=${FAIL}, skip=${SKIP}"

if (( FAIL > 0 )); then
  exit 2
fi
exit 0
