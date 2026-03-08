#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
HUB_REPORT="${CACHE_DIR}/report-hub.html"
DATA_QUALITY_REPORT="${CACHE_DIR}/data-quality-report.html"
READINESS_REPORT="${CACHE_DIR}/backtest-readiness-report.html"
PRICE_REPORT="${CACHE_DIR}/price-backtest-report.html"
POSITION_REPORT="${CACHE_DIR}/position-backtest-report.html"
FACTOR_REPORT="${CACHE_DIR}/factor-breakdown-report.html"
TUNING_COMPARE_REPORT="${CACHE_DIR}/tuning-compare.html"
DASHBOARD_REPORT="${CACHE_DIR}/dashboard.html"
LOOPS="${SIA_BACKTEST_REFRESH_LOOPS:-2}"
SLEEP_SECONDS="${SIA_BACKTEST_REFRESH_SLEEP_SECONDS:-1}"

mkdir -p "$CACHE_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

if ! [[ "$LOOPS" =~ ^[0-9]+$ ]] || [[ "$LOOPS" -lt 1 ]]; then
  echo "SIA_BACKTEST_REFRESH_LOOPS는 1 이상의 정수여야 합니다: ${LOOPS}" >&2
  exit 2
fi

if ! [[ "$SLEEP_SECONDS" =~ ^[0-9]+$ ]]; then
  echo "SIA_BACKTEST_REFRESH_SLEEP_SECONDS는 0 이상의 정수여야 합니다: ${SLEEP_SECONDS}" >&2
  exit 2
fi

for ((i = 1; i <= LOOPS; i++)); do
  echo "[${i}/${LOOPS}] live 표본 수집"
  SIA_NO_OPEN_DASHBOARD=1 \
  SIA_NO_OPEN_LAST_RUN=1 \
  bash "${PROJECT_ROOT}/scripts/_internal/sia-notifier-launch.command" balanced --live
  if [[ "$i" -lt "$LOOPS" ]] && [[ "$SLEEP_SECONDS" -gt 0 ]]; then
    sleep "$SLEEP_SECONDS"
  fi
done

echo "[quality] 데이터 품질 리포트 생성"
SIA_NO_OPEN_DATA_QUALITY=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-data-quality.command"

echo "[readiness] 백테스트 준비도 리포트 생성"
SIA_NO_OPEN_BACKTEST_READINESS=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-backtest-readiness.command"

echo "[price] 가격 백테스트 리포트 생성"
SIA_NO_OPEN_PRICE_BACKTEST=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-price-backtest.command"

echo "[position] 포지션 백테스트 리포트 생성"
SIA_NO_OPEN_POSITION_BACKTEST=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-position-backtest.command"

echo "[factor] factor 분해 리포트 생성"
SIA_NO_OPEN_FACTOR_BREAKDOWN=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-factor-breakdown.command"

if [[ -f "$READINESS_REPORT" ]] && grep -Eq '>(READY|준비 완료)<' "$READINESS_REPORT"; then
  echo "[tuning] 준비 완료 도달: 튜닝 비교 리포트 생성"
  SIA_NO_OPEN_TUNING_COMPARE=1 \
    "${PROJECT_ROOT}/scripts/_internal/sia-compare-tuning.command"
else
  echo "[tuning] readiness가 READY가 아니라서 튜닝 비교 자동 갱신은 건너뜀"
fi

echo "[dashboard] 대시보드 갱신"
SIA_NO_OPEN_DASHBOARD=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-dashboard.command"

echo "[hub] 리포트 허브 생성"
SIA_NO_OPEN_REPORT_HUB=1 \
  "${PROJECT_ROOT}/scripts/_internal/sia-report-hub.command"

if [[ "${SIA_NO_OPEN_BACKTEST_REFRESH:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  open "$HUB_REPORT" >/dev/null 2>&1 || true
fi

echo "완료:"
echo "  hub: $HUB_REPORT"
echo "  data_quality: $DATA_QUALITY_REPORT"
echo "  readiness: $READINESS_REPORT"
echo "  price: $PRICE_REPORT"
echo "  position: $POSITION_REPORT"
echo "  factor: $FACTOR_REPORT"
echo "  tuning_compare: $TUNING_COMPARE_REPORT"
echo "  dashboard: $DASHBOARD_REPORT"
