#!/bin/zsh
set -euo pipefail

ROOT_DIR="/Users/dohyeon/Documents/Playground/SIA"
CACHE_DIR="${HOME}/Library/Caches/sia-notifier"
ENV_FILE="${HOME}/.config/sia-notifier/env"
BASELINE_PATH="${CACHE_DIR}/tuning-baseline.json"
READINESS_REPORT="${CACHE_DIR}/backtest-readiness-report.html"
FACTOR_REPORT="${CACHE_DIR}/factor-breakdown-report.html"

mkdir -p "${CACHE_DIR}"

if [[ -f "${ENV_FILE}" ]]; then
  source "${ENV_FILE}"
fi

python3 - "${BASELINE_PATH}" "${READINESS_REPORT}" "${FACTOR_REPORT}" "${ROOT_DIR}/src" <<'PY'
import json
import os
import sys
from datetime import datetime
from pathlib import Path

baseline_path = Path(sys.argv[1])
readiness_path = Path(sys.argv[2])
factor_path = Path(sys.argv[3])
sys.path.insert(0, sys.argv[4])
from sia.report_parser import extract_chip_value, extract_first_label_value, extract_heading_paragraph, read_html


readiness_html = read_html(readiness_path)
factor_html = read_html(factor_path)

tuning_keys = [
    "SIGNAL_THRESHOLD",
    "SIA_CONFIRM_LONG_RISK_OFF",
    "SIA_CONFIRM_LONG_MIXED",
    "SIA_CONFIRM_LONG_RISK_ON",
    "SIA_CONFIRM_SHORT_RISK_OFF",
    "SIA_CONFIRM_SHORT_MIXED",
    "SIA_CONFIRM_SHORT_RISK_ON",
    "SIA_REGIME_BUY_PENALTY_RISK_OFF",
    "SIA_REGIME_SELL_PENALTY_RISK_ON",
    "SIA_REGIME_EXTRA_PENALTY_OPPOSED",
    "SIA_REGIME_BUY_BONUS_RISK_ON",
    "SIA_REGIME_SELL_BONUS_RISK_OFF",
    "SIA_REGIME_MULTIPLIER_MIN",
    "SIA_REGIME_MULTIPLIER_MAX",
]

payload = {
    "captured_at": datetime.now().isoformat(timespec="seconds"),
    "readiness_report": str(readiness_path),
    "factor_report": str(factor_path),
    "tuning": {key: os.getenv(key, "") for key in tuning_keys},
    "readiness": {
        "verdict": extract_first_label_value(readiness_html, ("판정", "Verdict")),
        "signals": extract_first_label_value(readiness_html, ("신호 수", "Signals")),
        "strict_aligned": extract_first_label_value(readiness_html, ("정합 신호 수", "Strict Aligned")),
        "ready_buckets": extract_first_label_value(readiness_html, ("준비 구간 수", "Ready Buckets")),
        "long_confirm": extract_chip_value(readiness_html, "롱 확인"),
        "short_confirm": extract_chip_value(readiness_html, "숏 확인"),
        "buy_penalty_risk_off": extract_chip_value(readiness_html, "OFF 매수 패널티"),
        "sell_bonus_risk_off": extract_chip_value(readiness_html, "OFF 매도 보너스"),
        "multiplier_clamp": extract_chip_value(readiness_html, "배수 clamp"),
    },
    "factor": {
        "snapshots": extract_first_label_value(factor_html, ("스냅샷 수", "Snapshots")),
        "strict_aligned": extract_first_label_value(factor_html, ("정합 스냅샷", "Strict Aligned")),
        "samples": extract_first_label_value(factor_html, ("표본 수", "Samples")),
        "mock_filtered": extract_first_label_value(factor_html, ("모의 제외", "Mock Filtered")),
        "best_combo": extract_heading_paragraph(factor_html, "현재 가장 강한 조합"),
        "long_confirm": extract_chip_value(factor_html, "롱 확인"),
        "short_confirm": extract_chip_value(factor_html, "숏 확인"),
        "buy_penalty_risk_off": extract_chip_value(factor_html, "OFF 매수 패널티"),
        "sell_bonus_risk_off": extract_chip_value(factor_html, "OFF 매도 보너스"),
        "multiplier_clamp": extract_chip_value(factor_html, "배수 clamp"),
    },
}

baseline_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2))
print(str(baseline_path))
PY
