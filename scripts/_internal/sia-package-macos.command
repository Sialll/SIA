#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST_DIR="$PROJECT_ROOT/dist/macos/SIA-macOS"
DOCS_DIR="$DIST_DIR/Docs"
UTILS_DIR="$DIST_DIR/Utilities"
APP_DIR="$DIST_DIR/SIA.app"
SUPPORT_DIR="$DIST_DIR/.sia-support"
INTERNAL_DIR="$SUPPORT_DIR/scripts/_internal"
SRC_DIR="$SUPPORT_DIR/src"
ICON_PATH="${SIA_MACOS_ICON_ICNS:-}"
CODESIGN_IDENTITY="${SIA_MACOS_CODESIGN_IDENTITY:-}"
NOTARY_PROFILE="${SIA_MACOS_NOTARY_PROFILE:-}"
ZIP_PATH="$PROJECT_ROOT/dist/macos/SIA-macOS.zip"

rm -rf "$DIST_DIR"
mkdir -p "$DOCS_DIR" "$UTILS_DIR" "$INTERNAL_DIR" "$SRC_DIR"

copy_if_exists() {
  local src="$1"
  local dst="$2"
  if [[ -e "$src" ]]; then
    cp -R "$src" "$dst"
  fi
}

cp -R "$PROJECT_ROOT/src/." "$SRC_DIR/"
cp -R "$PROJECT_ROOT/scripts/_internal/." "$INTERNAL_DIR/"

copy_if_exists "$PROJECT_ROOT/docs/sales-readiness-checklist.md" "$DOCS_DIR/"
copy_if_exists "$PROJECT_ROOT/docs/sales-ui-ia-plan.md" "$DOCS_DIR/"
copy_if_exists "$PROJECT_ROOT/docs/sales-packaging-flow.md" "$DOCS_DIR/"
copy_if_exists "$PROJECT_ROOT/docs/default-universe.md" "$DOCS_DIR/"

cat > "$UTILS_DIR/SIA.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/../.sia-support/scripts/_internal/sia-first-run.command" "$@"
EOF

cat > "$UTILS_DIR/SIA-Run.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/../.sia-support/scripts/_internal/sia-notifier-launch.command" balanced --live
EOF

cat > "$UTILS_DIR/SIA-Dashboard.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/../.sia-support/scripts/_internal/sia-dashboard.command"
EOF

cat > "$UTILS_DIR/SIA-Reports.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/../.sia-support/scripts/_internal/sia-report-hub.command"
EOF

cat > "$UTILS_DIR/SIA-Market-Settings.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/../.sia-support/scripts/_internal/sia-market-settings.command"
EOF

cat > "$UTILS_DIR/SIA-Market-Tickers.command" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/../.sia-support/scripts/_internal/sia-market-tickers.command" "$@"
EOF

chmod +x "$UTILS_DIR"/*.command

/usr/bin/osacompile -o "$APP_DIR" <<'EOF'
on run
  set appPath to POSIX path of (path to me)
  set launcherPath to quoted form of (appPath & "Contents/Resources/run-sia.sh")
  do shell script launcherPath & " >/tmp/sia-app-launch.log 2>&1 &"
end run
EOF

cat > "$APP_DIR/Contents/Resources/run-sia.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
exec "$DIST_DIR/Utilities/SIA.command" "$@"
EOF

chmod +x "$APP_DIR/Contents/Resources/run-sia.sh"

if [[ -n "$ICON_PATH" && -f "$ICON_PATH" ]]; then
  cp "$ICON_PATH" "$APP_DIR/Contents/Resources/applet.icns"
fi

if [[ -n "$CODESIGN_IDENTITY" ]]; then
  /usr/bin/codesign --force --deep --options runtime --sign "$CODESIGN_IDENTITY" "$APP_DIR"
fi

if [[ -n "$NOTARY_PROFILE" ]]; then
  if [[ -z "$CODESIGN_IDENTITY" ]]; then
    echo "notarization requires SIA_MACOS_CODESIGN_IDENTITY" >&2
    exit 1
  fi
  rm -f "$ZIP_PATH"
  /usr/bin/ditto -c -k --keepParent "$APP_DIR" "$ZIP_PATH"
  /usr/bin/xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$NOTARY_PROFILE" --wait
  /usr/bin/xcrun stapler staple "$APP_DIR"
fi

cat > "$DIST_DIR/README.txt" <<'EOF'
SIA macOS release staging

권장 실행:
1. SIA.app 실행

보조 실행기:
- SIA.app
- Utilities/SIA.command
- Utilities/SIA-Run.command
- Utilities/SIA-Dashboard.command
- Utilities/SIA-Reports.command

문서:
- Docs/ 폴더 참고

주의:
- 이 폴더는 release staging 산출물이다.
- 현재 macOS staging은 standalone 폴더 기준으로 동작한다.
- 배포 진입점은 SIA.app 이고, Utilities/는 보조 실행기다.
- 내부 실행 파일은 숨김 폴더(.sia-support)에 포함되어 있으며 사용자가 직접 열 필요가 없다.
- 선택 옵션:
  - SIA_MACOS_ICON_ICNS=/path/to/SIA.icns
  - SIA_MACOS_CODESIGN_IDENTITY="Developer ID Application: ..."
  - SIA_MACOS_NOTARY_PROFILE="notary-profile-name"
EOF

echo "$DIST_DIR"
