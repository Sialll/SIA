#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-install}"
LABEL="com.sia.ready-buckets-guard"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_DIR}/${LABEL}.plist"
RUNNER="${REPO_DIR}/scripts/_internal/sia-ready-buckets-guard.command"
LOG_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
OUT_LOG="${LOG_DIR}/ready-buckets-guard.out.log"
ERR_LOG="${LOG_DIR}/ready-buckets-guard.err.log"
GUARD_HOUR="${SIA_READY_BUCKETS_GUARD_HOUR:-8}"
GUARD_MINUTE="${SIA_READY_BUCKETS_GUARD_MINUTE:-20}"

if [[ "$ACTION" == "uninstall" ]]; then
  launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  echo "ready-buckets guard 에이전트 삭제 완료: ${PLIST_PATH}"
  exit 0
fi

if [[ "$ACTION" == "status" ]]; then
  if [[ ! -f "$PLIST_PATH" ]]; then
    echo "설치되지 않았습니다: ${PLIST_PATH}"
    exit 0
  fi
  launchctl print "gui/$(id -u)/${LABEL}" 2>/dev/null | rg "state =|last exit code =|path =" || true
  exit 0
fi

if [[ "$ACTION" != "install" ]]; then
  echo "사용법: $0 [install|uninstall|status]"
  exit 2
fi

if [[ ! -x "$RUNNER" ]]; then
  echo "실행 불가: $RUNNER"
  exit 2
fi

if ! [[ "$GUARD_HOUR" =~ ^[0-9]+$ ]] || (( GUARD_HOUR < 0 || GUARD_HOUR > 23 )); then
  echo "잘못된 SIA_READY_BUCKETS_GUARD_HOUR: ${GUARD_HOUR}"
  exit 2
fi

if ! [[ "$GUARD_MINUTE" =~ ^[0-9]+$ ]] || (( GUARD_MINUTE < 0 || GUARD_MINUTE > 59 )); then
  echo "잘못된 SIA_READY_BUCKETS_GUARD_MINUTE: ${GUARD_MINUTE}"
  exit 2
fi

mkdir -p "$LAUNCH_DIR" "$LOG_DIR"

cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${RUNNER}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>${GUARD_HOUR}</integer>
    <key>Minute</key>
    <integer>${GUARD_MINUTE}</integer>
  </dict>
  <key>RunAtLoad</key>
  <false/>
  <key>WorkingDirectory</key>
  <string>/tmp</string>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHON_BIN</key>
    <string>${PYTHON_BIN:-python3}</string>
  </dict>
</dict>
</plist>
EOF

launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"

echo "ready-buckets guard 에이전트 설치 완료: $PLIST_PATH"
echo "실행 시각: ${GUARD_HOUR}시 ${GUARD_MINUTE}분"
echo "로그: ${OUT_LOG}, ${ERR_LOG}"
