#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-install}"
RUN_MODE="${2:-balanced}"
LABEL="com.sia.trading-signal-notifier"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_DIR}/${LABEL}.plist"
LAUNCHD_RUNNER="${REPO_DIR}/scripts/sia-notifier-launch.command"

LOG_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
OUT_LOG="${LOG_DIR}/launchd.out.log"
ERR_LOG="${LOG_DIR}/launchd.err.log"
ENV_DIR="${HOME}/.config/sia-notifier"
ENV_FILE="${ENV_DIR}/env"

if [[ "$ACTION" == "uninstall" ]]; then
  launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  echo "uninstalled launch agent: ${PLIST_PATH}"
  exit 0
fi

if [[ "$ACTION" != "install" ]]; then
  echo "usage: $0 [install|uninstall] [balanced|conservative|aggressive]"
  exit 2
fi

if [[ ! -x "$LAUNCHD_RUNNER" ]]; then
  echo "not executable: $LAUNCHD_RUNNER"
  exit 2
fi

mkdir -p "$LAUNCH_DIR"
mkdir -p "$LOG_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "warning: env file not found: $ENV_FILE"
  echo "create it if needed: cat ${ENV_DIR}/env"
fi

if [[ -n "${SIA_POLL_MINUTES:-}" ]]; then
  if [[ "$SIA_POLL_MINUTES" =~ ^[0-9]+$ ]] && ((SIA_POLL_MINUTES >= 1 )); then
    INTERVAL=$((SIA_POLL_MINUTES * 60))
  else
    echo "invalid SIA_POLL_MINUTES: ${SIA_POLL_MINUTES}; fallback 900"
    INTERVAL=900
  fi
else
  INTERVAL=900
fi

if (( INTERVAL < 60 )); then
  INTERVAL=60
fi

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
    <string>${LAUNCHD_RUNNER}</string>
    <string>${RUN_MODE}</string>
  </array>
  <key>StartInterval</key>
  <integer>${INTERVAL}</integer>
  <key>WorkingDirectory</key>
  <string>${REPO_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>PathState</key>
    <dict>
      <key>${REPO_DIR}</key>
      <true/>
    </dict>
  </dict>
  <key>StandardOutPath</key>
  <string>${OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${ERR_LOG}</string>
</dict>
</plist>
EOF

launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"

echo "installed launch agent: $PLIST_PATH"
echo "mode: ${RUN_MODE}, interval: ${INTERVAL}s"
echo "logs: ${OUT_LOG}, ${ERR_LOG}"
