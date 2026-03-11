#!/usr/bin/env bash
set -euo pipefail

ACTION="${1:-install}"
RUN_MODE="${2:-balanced}"
LABEL="com.sia.trading-signal-notifier"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"
PLIST_PATH="${LAUNCH_DIR}/${LABEL}.plist"
LAUNCHD_RUNNER="${REPO_DIR}/scripts/_internal/sia-notifier-launch.command"
API_STATUS_LIB="${REPO_DIR}/scripts/_internal/sia-notifier-api-status-lib.sh"

LOG_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
LAUNCHD_RUNTIME_DIR="${LOG_DIR}/runtime"
LAUNCHD_RUNTIME_RUNNER="${LAUNCHD_RUNTIME_DIR}/scripts/sia-notifier-launch.command"
LAUNCHD_RUNTIME_API_STATUS_LIB="${LAUNCHD_RUNTIME_DIR}/scripts/sia-notifier-api-status-lib.sh"
OUT_LOG="${LOG_DIR}/launchd.out.log"
ERR_LOG="${LOG_DIR}/launchd.err.log"
ENV_DIR="${HOME}/.config/sia-notifier"
ENV_FILE="${ENV_DIR}/env"

if [[ "$ACTION" == "uninstall" ]]; then
  launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
  rm -f "$PLIST_PATH"
  echo "런치 에이전트 삭제 완료: ${PLIST_PATH}"
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

if [[ "$ACTION" != "install" && "$ACTION" != "install-market-hours" ]]; then
  echo "사용법: $0 [install|install-market-hours|uninstall|status] [balanced|conservative|aggressive]"
  exit 2
fi

if [[ ! -x "$LAUNCHD_RUNNER" ]]; then
  echo "실행 불가: $LAUNCHD_RUNNER"
    exit 2
fi
if [[ ! -f "$API_STATUS_LIB" ]]; then
  echo "필수 파일 누락: $API_STATUS_LIB"
  exit 2
fi

USER_TICKERS="${TICKERS-}"
USER_POLL_MINUTES="${SIA_POLL_MINUTES-}"
AUTO_INTERVAL_FLAG="${SIA_AUTO_INTERVAL:-0}"
AUTO_PER_TICKER_SECONDS="${SIA_AUTO_INTERVAL_PER_TICKER_SECONDS:-120}"
AUTO_MIN_SECONDS="${SIA_AUTO_INTERVAL_MIN_SECONDS:-900}"
AUTO_MAX_SECONDS="${SIA_AUTO_INTERVAL_MAX_SECONDS:-7200}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "경고: env 파일을 찾지 못했습니다: $ENV_FILE"
  echo "필요 시 생성: cat ${ENV_DIR}/env"
else
  # shell style env should define exports
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

if [[ -n "${USER_TICKERS}" ]]; then
  export TICKERS="$USER_TICKERS"
fi
if [[ -n "${USER_POLL_MINUTES}" ]]; then
  export SIA_POLL_MINUTES="$USER_POLL_MINUTES"
fi

parse_bool() {
  local value="${1:-}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

count_tickers() {
  local raw="${1:-}"
  if [[ -z "$raw" ]]; then
    echo 1
    return 0
  fi
  printf '%s\n' "$raw" \
    | tr ',' '\n' \
    | awk '{
        gsub(/^[[:space:]]+/, "", $0);
        gsub(/[[:space:]]+$/, "", $0);
        if ($0 != "" ) cnt++;
      }
      END {print (cnt > 0 ? cnt : 1)}'
}

mkdir -p "$LAUNCH_DIR"
mkdir -p "$LOG_DIR"
rm -rf "$LAUNCHD_RUNTIME_DIR"
mkdir -p "${LAUNCHD_RUNTIME_DIR}/scripts"
cp -R "$REPO_DIR/src" "$LAUNCHD_RUNTIME_DIR"/
cp "$LAUNCHD_RUNNER" "$LAUNCHD_RUNTIME_RUNNER"
cp "$API_STATUS_LIB" "$LAUNCHD_RUNTIME_API_STATUS_LIB"
chmod +x "$LAUNCHD_RUNTIME_RUNNER"

if [[ -n "${SIA_POLL_MINUTES:-}" ]]; then
  if [[ "$SIA_POLL_MINUTES" =~ ^[0-9]+$ ]] && ((SIA_POLL_MINUTES >= 1 )); then
    INTERVAL=$((SIA_POLL_MINUTES * 60))
  else
    echo "잘못된 SIA_POLL_MINUTES: ${SIA_POLL_MINUTES}. 기본값 900초로 대체합니다."
    INTERVAL=900
  fi
else
  if parse_bool "$AUTO_INTERVAL_FLAG"; then
    tickers_count="$(count_tickers "${TICKERS:-}")"
    if [[ "$AUTO_PER_TICKER_SECONDS" =~ ^[0-9]+$ ]] && ((AUTO_PER_TICKER_SECONDS >= 1)); then
      INTERVAL=$((tickers_count * AUTO_PER_TICKER_SECONDS))
    else
      INTERVAL=900
    fi
    if (( INTERVAL < AUTO_MIN_SECONDS )); then
      INTERVAL=$AUTO_MIN_SECONDS
    fi
    if (( INTERVAL > AUTO_MAX_SECONDS )); then
      INTERVAL=$AUTO_MAX_SECONDS
    fi
    echo "자동 실행 주기 적용: 티커수=${tickers_count}, 간격=${INTERVAL}s (원본=${tickers_count} * ${AUTO_PER_TICKER_SECONDS}, 구간=${AUTO_MIN_SECONDS}~${AUTO_MAX_SECONDS})"
  else
    INTERVAL=900
  fi
fi

if (( INTERVAL < 60 )); then
  INTERVAL=60
fi

SIA_MARKET_HOURS_TIMES="${SIA_MARKET_HOURS_TIMES:-22:30,22:45,23:00,23:15,23:30,23:45,00:00,00:15,00:30,00:45,01:00,01:15,01:30,01:45,02:00,02:15,02:30,02:45,03:00,03:15,03:30,03:45,04:00,04:15,04:30,04:45,05:00}"
SCHEDULE_XML=""
SCHEDULE_SUMMARY=""
if [[ "$ACTION" == "install-market-hours" ]]; then
  IFS=',' read -r -a MARKET_TIMES <<<"${SIA_MARKET_HOURS_TIMES}"
  CALENDAR_ITEMS=""
  VALID_TIMES=()
  for raw_time in "${MARKET_TIMES[@]}"; do
    time_value="$(printf '%s' "$raw_time" | tr -d '[:space:]')"
    if [[ -z "$time_value" ]]; then
      continue
    fi
    if [[ ! "$time_value" =~ ^([0-9]{1,2}):([0-9]{2})$ ]]; then
      echo "잘못된 SIA_MARKET_HOURS_TIMES 항목: ${time_value}" >&2
      exit 2
    fi
    hour="${BASH_REMATCH[1]}"
    minute="${BASH_REMATCH[2]}"
    if ((10#$hour < 0 || 10#$hour > 23 || 10#$minute < 0 || 10#$minute > 59)); then
      echo "잘못된 시장 시간 값: ${time_value}" >&2
      exit 2
    fi
    VALID_TIMES+=("$(printf '%02d:%02d' "$hour" "$minute")")
    CALENDAR_ITEMS="${CALENDAR_ITEMS}
    <dict>
      <key>Hour</key>
      <integer>$((10#$hour))</integer>
      <key>Minute</key>
      <integer>$((10#$minute))</integer>
    </dict>"
  done
  if [[ "${#VALID_TIMES[@]}" -eq 0 ]]; then
    echo "유효한 시장 시간대 실행 시각이 없습니다." >&2
    exit 2
  fi
  SCHEDULE_XML="<key>StartCalendarInterval</key>
  <array>${CALENDAR_ITEMS}
  </array>"
  SCHEDULE_SUMMARY="시장 시간대(KST): ${VALID_TIMES[*]}"
else
  SCHEDULE_XML="<key>StartInterval</key>
  <integer>${INTERVAL}</integer>"
  SCHEDULE_SUMMARY="실행 간격: ${INTERVAL}초"
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
    <string>${LAUNCHD_RUNTIME_RUNNER}</string>
    <string>${RUN_MODE}</string>
    <string>--live</string>
  </array>
  ${SCHEDULE_XML}
  <key>WorkingDirectory</key>
  <string>/tmp</string>
  <key>RunAtLoad</key>
  <true/>
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
    <key>SIA_REPO_DIR</key>
    <string>${LAUNCHD_RUNTIME_DIR}</string>
    <key>SIA_NO_OPEN_REPORT</key>
    <string>1</string>
  </dict>
</dict>
</plist>
EOF

launchctl unload -w "$PLIST_PATH" 2>/dev/null || true
launchctl load -w "$PLIST_PATH"

echo "런치 에이전트 설치 완료: $PLIST_PATH"
echo "모드: ${RUN_MODE}, ${SCHEDULE_SUMMARY}"
echo "로그: ${OUT_LOG}, ${ERR_LOG}"
