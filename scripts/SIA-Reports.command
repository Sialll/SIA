#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SIA_NO_OPEN_DATA_QUALITY=1 "${SCRIPT_DIR}/_internal/sia-data-quality.command" >/dev/null
SIA_NO_OPEN_BACKTEST_READINESS=1 "${SCRIPT_DIR}/_internal/sia-backtest-readiness.command" >/dev/null
PRICE_BACKTEST_HORIZONS="1,3,5,10,30m,1h,day_close,next_open" \
SIA_NO_OPEN_PRICE_BACKTEST=1 \
  "${SCRIPT_DIR}/_internal/sia-price-backtest.command" >/dev/null
SIA_NO_OPEN_POSITION_BACKTEST=1 \
  "${SCRIPT_DIR}/_internal/sia-position-backtest.command" --hold-horizons "3,30m,1h,day_close,next_open" >/dev/null
SIA_NO_OPEN_BACKTEST_CONCENTRATION=1 "${SCRIPT_DIR}/_internal/sia-backtest-concentration.command" >/dev/null
SIA_NO_OPEN_FACTOR_BREAKDOWN=1 "${SCRIPT_DIR}/_internal/sia-factor-breakdown.command" >/dev/null
SIA_NO_OPEN_RESEARCH_REPORT=1 "${SCRIPT_DIR}/_internal/sia-research-report.command" >/dev/null
SIA_NO_OPEN_UNIVERSE_REPORT=1 "${SCRIPT_DIR}/_internal/sia-universe-report.command" >/dev/null
SIA_NO_OPEN_FULL_UNIVERSE_REPORT=1 "${SCRIPT_DIR}/_internal/sia-full-universe-report.command" >/dev/null
exec "${SCRIPT_DIR}/_internal/sia-report-hub.command"
