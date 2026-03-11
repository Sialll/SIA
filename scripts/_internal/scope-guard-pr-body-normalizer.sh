#!/usr/bin/env bash
set -euo pipefail

OUTPUT_FILE="/tmp/sia-pr-body-normalized.md"
DRY_RUN=false
MODE=""
START_PR=""
END_PR=""
PR_NUMBER=""

GH_CANDIDATES=(
  "${GH_BIN:-}"
  "${GH:-}"
  "/Users/dohyeon/bin/gh"
  "/usr/local/bin/gh"
  "/opt/homebrew/bin/gh"
  "$HOME/bin/gh"
  "gh"
)

usage() {
  cat <<'EOF_USAGE'
Usage:
  ./scope-guard-pr-body-normalizer.sh open
  ./scope-guard-pr-body-normalizer.sh --pr <PR_NUMBER>
  ./scope-guard-pr-body-normalizer.sh <start_pr> <end_pr>

Options:
  --dry-run   print diff only, no PR update
  --help      usage
EOF_USAGE
}

pick_gh_cmd() {
  local candidate
  for candidate in "${GH_CANDIDATES[@]}"; do
    if [[ -n "$candidate" ]] && command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

collect_open_pr_numbers_with_gh() {
  "$GH_CMD" pr list --state open --json number -q ".[].number" 2>/dev/null
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
headers = {
    "User-Agent": "scope-guard-body-normalizer",
    "Accept": "application/vnd.github+json",
}
if token:
    headers["Authorization"] = f"Bearer {token}"

with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
    raw = response.read().decode("utf-8")

for item in json.loads(raw):
    number = item.get("number")
    if isinstance(number, int):
        print(number)
PY
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
  local open_pr_raw
  if open_pr_raw="$(collect_open_pr_numbers_with_gh)" && [[ -n "$open_pr_raw" ]]; then
    printf '%s\n' "$open_pr_raw"
    return 0
  fi

  local repo
  repo="$(resolve_open_repo || true)"
  if [[ -z "$repo" ]]; then
    return 1
  fi

  collect_open_pr_numbers_from_api "$repo" "${GITHUB_TOKEN:-${GH_TOKEN:-}}"
}

collect_targets() {
  if [[ -n "$PR_NUMBER" ]]; then
    echo "$PR_NUMBER"
    return
  fi

  if [[ "$MODE" == "open" ]]; then
    collect_open_pr_numbers
    return
  fi

  local n
  for ((n=START_PR; n<=END_PR; n++)); do
    echo "$n"
  done
}

normalize_body() {
  local input_body="$1"
  if [[ -z "$input_body" ]]; then
    echo ""
    return 0
  fi

  python3 - "$input_body" <<'PY'
import re
import sys

text = sys.argv[1]
patterns = [
    r"(?im)^\s*#{2,6}\s*Changes\s*$\n?",
    r"(?im)^\s*###\s*Scope Guard Fix Summary\s*$\n?",
    r"(?im)^\s*####\s*수정된 핵심 섹션\s*$\n?",
    r"(?im)^\s*<!--\s*Scope Guard Fix Summary\s*-->\n?",
    r"(?im)^\s*<!--\s*수정된 핵심 섹션\s*-->\n?",
    r"(?im)^PR Title:\s*.*$\n?",
]

for pattern in patterns:
    text = re.sub(pattern, "", text)

text = re.sub(r"\n{3,}", "\n\n", text)
print(text.strip("\n") + "\n")
PY
}

apply_or_print() {
  local pr="$1"
  local body
  local normalized

  body="$($GH_CMD pr view "$pr" --json body -q .body 2>/dev/null || true)"
  if [[ -z "$body" ]]; then
    echo "skip: PR #$pr body empty"
    return
  fi

  normalized="$(normalize_body "$body")"
  if [[ -z "${normalized//[[:space:]]/}" ]]; then
    echo "skip: PR #$pr normalization resulted in empty text"
    return
  fi

  if [[ "$normalized" == "$body" ]]; then
    echo "skip: PR #$pr no-op"
    return
  fi

  printf '%s\n' "$normalized" > "$OUTPUT_FILE"

  if [[ "$DRY_RUN" == true ]]; then
    echo "===== PR #$pr (dry-run) ====="
    diff -u <(printf '%s' "$body") <(printf '%s' "$normalized") | sed -n '1,120p' || true
    return
  fi

  "$GH_CMD" pr edit "$pr" --body-file "$OUTPUT_FILE"
  echo "normalized: PR #$pr"
}

parse_args() {
  local -a normalized_args=()
  if (( $# == 0 )); then
    usage
    exit 1
  fi

  while (( $# > 0 )); do
    case "$1" in
      --help)
        usage
        exit 0
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --pr)
        if (( $# < 2 )); then
          echo "error: --pr requires a PR number." >&2
          usage
          exit 1
        fi
        normalized_args+=("--pr")
        normalized_args+=("$2")
        shift 2
        ;;
      *)
        if [[ "${1}" == --* ]]; then
          echo "Unknown argument: $1" >&2
          usage
          exit 1
        fi
        normalized_args+=("$1")
        shift
        ;;
    esac
  done
  set -- "${normalized_args[@]:-}"

  if (( $# == 0 )); then
    echo "error: no valid target found." >&2
    usage
    exit 1
  fi

  if [[ "$1" == "open" ]]; then
    if (( $# != 1 )); then
      echo "error: open mode accepts no extra arguments." >&2
      usage
      exit 1
    fi
    MODE="open"
    return
  fi

  if [[ "$1" == "--pr" ]]; then
    if (( $# != 2 )); then
      echo "error: --pr requires a PR number." >&2
      usage
      exit 1
    fi
    PR_NUMBER="$2"
    MODE="single"
    return
  fi

  if (( $# != 2 )); then
    echo "error: range mode requires two numbers." >&2
    usage
    exit 1
  fi
  if ! [[ "$1" =~ ^[0-9]+$ && "$2" =~ ^[0-9]+$ ]]; then
    echo "error: range mode requires numeric values." >&2
    usage
    exit 1
  fi
  START_PR="$1"
  END_PR="$2"
  MODE="range"

  if (( START_PR > END_PR )); then
    echo "error: start_pr cannot be greater than end_pr." >&2
    exit 1
  fi
}

parse_args "$@"

GH_CMD="$(pick_gh_cmd || true)"
if [[ -z "${GH_CMD}" ]]; then
  echo "error: gh CLI가 필요합니다. (PATH 또는 GH_BIN 환경변수 확인)" >&2
  exit 1
fi
if ! command -v "$GH_CMD" >/dev/null 2>&1; then
  echo "error: gh CLI가 필요합니다. (PATH 또는 GH_BIN 환경변수 확인)" >&2
  exit 1
fi

if [[ "$MODE" == "" ]]; then
  echo "error: no target mode" >&2
  usage
  exit 1
fi

if [[ "$MODE" == "single" ]]; then
  targets="$PR_NUMBER"
else
  targets="$(collect_targets || true)"
fi

if [[ -z "${targets:-}" ]]; then
  echo "result: no targets"
  exit 0
fi

while IFS= read -r pr; do
  [[ -z "$pr" ]] && continue
  apply_or_print "$pr"
done <<<"$(printf '%s\n' "$targets" | sed '/^[[:space:]]*$/d' | sort -nu)"
