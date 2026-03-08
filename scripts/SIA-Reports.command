#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIA_NO_OPEN_UNIVERSE_REPORT=1 "${SCRIPT_DIR}/_internal/sia-universe-report.command" >/dev/null
SIA_NO_OPEN_FULL_UNIVERSE_REPORT=1 "${SCRIPT_DIR}/_internal/sia-full-universe-report.command" >/dev/null
exec "${SCRIPT_DIR}/_internal/sia-report-hub.command"
