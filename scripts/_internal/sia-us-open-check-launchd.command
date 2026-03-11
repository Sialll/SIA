#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
LAUNCH_DIR="${HOME}/Library/LaunchAgents"

OPEN_LABEL="com.sia.us-open-check"
OPEN_PLIST_PATH="${LAUNCH_DIR}/${OPEN_LABEL}.plist"
OPEN_OUT_LOG="${CACHE_DIR}/us-open-check.out.log"
OPEN_ERR_LOG="${CACHE_DIR}/us-open-check.err.log"

QUALITY_LABEL="com.sia.signal-quality-review"
QUALITY_PLIST_PATH="${LAUNCH_DIR}/${QUALITY_LABEL}.plist"
QUALITY_OUT_LOG="${CACHE_DIR}/signal-quality-review.out.log"
QUALITY_ERR_LOG="${CACHE_DIR}/signal-quality-review.err.log"

AWAKE_LABEL="com.sia.market-awake"
AWAKE_PLIST_PATH="${LAUNCH_DIR}/${AWAKE_LABEL}.plist"

OPEN_RUNTIME_DIR="${CACHE_DIR}/runtime-market-open-check"
QUALITY_RUNTIME_DIR="${CACHE_DIR}/runtime-signal-quality-review"
OPEN_RUNTIME_RUNNER="${OPEN_RUNTIME_DIR}/scripts/run-market-open-check.command"
QUALITY_RUNTIME_RUNNER="${QUALITY_RUNTIME_DIR}/scripts/run-signal-quality-review.command"

copy_runtime() {
  local runtime_dir="$1"
  rm -rf "$runtime_dir"
  mkdir -p "${runtime_dir}/scripts"
  cp -R "${PROJECT_ROOT}/src" "${runtime_dir}/"
  cp -R "${PROJECT_ROOT}/scripts/_internal" "${runtime_dir}/scripts/"
}

write_open_runtime_runner() {
  cat >"$OPEN_RUNTIME_RUNNER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
RUNTIME_DIR="${OPEN_RUNTIME_DIR}"
export PYTHONPATH="\${RUNTIME_DIR}/src\${PYTHONPATH:+:\${PYTHONPATH}}"
bash "\${RUNTIME_DIR}/scripts/_internal/sia-us-open-check.command"
EOF
  chmod +x "$OPEN_RUNTIME_RUNNER"
}

write_quality_runtime_runner() {
  cat >"$QUALITY_RUNTIME_RUNNER" <<EOF
#!/usr/bin/env bash
set -euo pipefail
RUNTIME_DIR="${QUALITY_RUNTIME_DIR}"
export PYTHONPATH="\${RUNTIME_DIR}/src\${PYTHONPATH:+:\${PYTHONPATH}}"
export SIA_NO_OPEN_DATA_QUALITY=1
export SIA_NO_OPEN_BACKTEST_READINESS=1
export SIA_NO_OPEN_PRICE_BACKTEST=1
export SIA_NO_OPEN_POSITION_BACKTEST=1
export SIA_NO_OPEN_FACTOR_BREAKDOWN=1
export SIA_NO_OPEN_DASHBOARD=1
export SIA_NO_OPEN_REPORT_HUB=1
"\${RUNTIME_DIR}/scripts/_internal/sia-data-quality.command"
"\${RUNTIME_DIR}/scripts/_internal/sia-backtest-readiness.command"
"\${RUNTIME_DIR}/scripts/_internal/sia-price-backtest.command"
"\${RUNTIME_DIR}/scripts/_internal/sia-position-backtest.command"
"\${RUNTIME_DIR}/scripts/_internal/sia-factor-breakdown.command"
"\${RUNTIME_DIR}/scripts/_internal/sia-dashboard.command"
"\${RUNTIME_DIR}/scripts/_internal/sia-report-hub.command"
EOF
  chmod +x "$QUALITY_RUNTIME_RUNNER"
}

write_open_plist() {
  cat >"$OPEN_PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${OPEN_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${OPEN_RUNTIME_RUNNER}</string>
  </array>
  <key>StandardOutPath</key>
  <string>${OPEN_OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${OPEN_ERR_LOG}</string>
  <key>WorkingDirectory</key>
  <string>/tmp</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHON_BIN</key>
    <string>${PYTHON_BIN:-python3}</string>
  </dict>
  <key>StartInterval</key>
  <integer>600</integer>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF
}

write_quality_plist() {
  cat >"$QUALITY_PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${QUALITY_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${QUALITY_RUNTIME_RUNNER}</string>
  </array>
  <key>StandardOutPath</key>
  <string>${QUALITY_OUT_LOG}</string>
  <key>StandardErrorPath</key>
  <string>${QUALITY_ERR_LOG}</string>
  <key>WorkingDirectory</key>
  <string>/tmp</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>HOME</key>
    <string>${HOME}</string>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>PYTHON_BIN</key>
    <string>${PYTHON_BIN:-python3}</string>
  </dict>
  <key>StartInterval</key>
  <integer>1800</integer>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF
}

write_awake_plist() {
  cat >"$AWAKE_PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${AWAKE_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/caffeinate</string>
    <string>-i</string>
    <string>-m</string>
    <string>-s</string>
  </array>
  <key>KeepAlive</key>
  <true/>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF
}

install_job() {
  mkdir -p "$LAUNCH_DIR" "$CACHE_DIR"
  copy_runtime "$OPEN_RUNTIME_DIR"
  copy_runtime "$QUALITY_RUNTIME_DIR"
  write_open_runtime_runner
  write_quality_runtime_runner
  write_open_plist
  write_quality_plist
  write_awake_plist
  launchctl bootout "gui/$(id -u)/${OPEN_LABEL}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${QUALITY_LABEL}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${AWAKE_LABEL}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$(id -u)" "$OPEN_PLIST_PATH"
  launchctl bootstrap "gui/$(id -u)" "$QUALITY_PLIST_PATH"
  launchctl bootstrap "gui/$(id -u)" "$AWAKE_PLIST_PATH"
  echo "설치 완료: $OPEN_PLIST_PATH"
  echo "설치 완료: $QUALITY_PLIST_PATH"
  echo "설치 완료: $AWAKE_PLIST_PATH"
}

uninstall_job() {
  launchctl bootout "gui/$(id -u)/${OPEN_LABEL}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${QUALITY_LABEL}" >/dev/null 2>&1 || true
  launchctl bootout "gui/$(id -u)/${AWAKE_LABEL}" >/dev/null 2>&1 || true
  rm -f "$OPEN_PLIST_PATH" "$QUALITY_PLIST_PATH" "$AWAKE_PLIST_PATH"
  rm -rf "$OPEN_RUNTIME_DIR" "$QUALITY_RUNTIME_DIR"
  echo "제거 완료: $OPEN_PLIST_PATH"
  echo "제거 완료: $QUALITY_PLIST_PATH"
  echo "제거 완료: $AWAKE_PLIST_PATH"
}

status_job() {
  launchctl print "gui/$(id -u)/${OPEN_LABEL}" | sed -n '1,120p'
  echo "---"
  launchctl print "gui/$(id -u)/${QUALITY_LABEL}" | sed -n '1,120p'
  echo "---"
  launchctl print "gui/$(id -u)/${AWAKE_LABEL}" | sed -n '1,120p'
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
