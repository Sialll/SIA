#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LABEL="com.sia.us-open-check"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
COMMAND_PATH="${PROJECT_ROOT}/scripts/_internal/sia-us-open-check.command"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
OUT_LOG="${CACHE_DIR}/us-open-check.out.log"
ERR_LOG="${CACHE_DIR}/us-open-check.err.log"

install_job() {
  mkdir -p "${HOME}/Library/LaunchAgents" "$CACHE_DIR"
  cat >"$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${COMMAND_PATH}</string>
  </array>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>40</integer></dict>
    <dict><key>Weekday</key><integer>6</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>40</integer></dict>
  </array>
</dict>
</plist>
EOF
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
  echo "설치 완료: $PLIST_PATH"
}

uninstall_job() {
  launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
  rm -f "$PLIST_PATH"
  echo "제거 완료: $PLIST_PATH"
}

status_job() {
  launchctl print "gui/$(id -u)/${LABEL}" | sed -n '1,120p'
}

case "${1:-install}" in
  install)
    install_job
    ;;
  uninstall|remove)
    uninstall_job
    ;;
  status)
    status_job
    ;;
  *)
    echo "사용법: $0 [install|status|uninstall]" >&2
    exit 2
    ;;
esac
