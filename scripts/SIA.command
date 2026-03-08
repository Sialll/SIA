#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

selection="$(
osascript <<'OSA'
set launcherChoices to {"메인", "관심 종목 추가/수정", "시장 설정", "관리자 체크 포인트", "엔진 실행 (실전)", "엔진 실행 (드라이런)"}
set picked to choose from list launcherChoices with title "SIA 실행기" with prompt "실행할 항목을 선택하세요." default items {"메인"}
if picked is false then
  return "__CANCEL__"
end if
return item 1 of picked
OSA
)"

case "$selection" in
  "__CANCEL__")
    echo "실행이 취소되었습니다."
    exit 0
    ;;
  "메인")
    exec "${SCRIPT_DIR}/SIA-Dashboard.command"
    ;;
  "관심 종목 추가/수정")
    exec "${SCRIPT_DIR}/SIA-Market-Tickers.command"
    ;;
  "시장 설정")
    exec "${SCRIPT_DIR}/SIA-Market-Settings.command"
    ;;
  "관리자 체크 포인트")
    exec "${SCRIPT_DIR}/SIA-Reports.command"
    ;;
  "엔진 실행 (실전)")
    exec "${SCRIPT_DIR}/_internal/sia-notifier-launch.command" balanced --live
    ;;
  "엔진 실행 (드라이런)")
    exec "${SCRIPT_DIR}/_internal/sia-notifier-launch.command" balanced --dry-run
    ;;
  *)
    echo "알 수 없는 선택입니다: ${selection}" >&2
    exit 1
    ;;
esac
