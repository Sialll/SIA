#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-install}"
LABEL="com.sia.backtest-refresh-nightly"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_DIR}/${LABEL}.plist"
RUNNER="${REPO_DIR}/scripts/_internal/sia-backtest-refresh.command"
LOG_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
OUT_LOG="${LOG_DIR}/backtest-refresh-nightly.out.log"
ERR_LOG="${LOG_DIR}/backtest-refresh-nightly.err.log"
ENV_FILE="${HOME}/.config/sia-notifier/env"
NIGHT_HOURS_RAW="${SIA_BACKTEST_NIGHT_HOURS:-23,0,1,2,3,4,5}"
NIGHT_MINUTE="${SIA_BACKTEST_NIGHT_MINUTE:-10}"

if [[ "$ACTION" == "uninstall" ]]; then
  launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  echo "야간 backtest-refresh 에이전트 삭제 완료: ${PLIST_PATH}"
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

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

if ! [[ "$NIGHT_MINUTE" =~ ^[0-9]+$ ]] || (( NIGHT_MINUTE < 0 || NIGHT_MINUTE > 59 )); then
  echo "잘못된 SIA_BACKTEST_NIGHT_MINUTE: ${NIGHT_MINUTE}"
  exit 2
fi

mkdir -p "$LAUNCH_DIR" "$LOG_DIR"

IFS=',' read -r -a NIGHT_HOURS <<<"$NIGHT_HOURS_RAW"
CALENDAR_ITEMS=""
VALID_HOURS=()
for raw_hour in "${NIGHT_HOURS[@]}"; do
  hour="$(printf '%s' "$raw_hour" | tr -d '[:space:]')"
  if [[ -z "$hour" ]]; then
    continue
  fi
  if ! [[ "$hour" =~ ^[0-9]+$ ]] || (( hour < 0 || hour > 23 )); then
    echo "잘못된 야간 실행 시간: ${hour}"
    exit 2
  fi
  VALID_HOURS+=("$hour")
  CALENDAR_ITEMS="${CALENDAR_ITEMS}
    <dict>
      <key>Hour</key>
      <integer>${hour}</integer>
      <key>Minute</key>
      <integer>${NIGHT_MINUTE}</integer>
    </dict>"
done

if [[ "${#VALID_HOURS[@]}" -eq 0 ]]; then
  echo "유효한 야간 실행 시간이 없습니다."
  exit 2
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
    <string>/bin/bash</string>
    <string>${RUNNER}</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>${CALENDAR_ITEMS}
  </array>
  <key>WorkingDirectory</key>
  <string>/tmp</string>
  <key>RunAtLoad</key>
  <false/>
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
    <key>SIA_NO_OPEN_BACKTEST_REFRESH</key>
    <string>1</string>
  </dict>
</dict>
</plist>
EOF

launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"

echo "야간 backtest-refresh 에이전트 설치 완료: $PLIST_PATH"
echo "실행 시각: ${VALID_HOURS[*]}시 ${NIGHT_MINUTE}분"
echo "로그: ${OUT_LOG}, ${ERR_LOG}"
