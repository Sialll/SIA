#!/bin/zsh
set -euo pipefail

CACHE_DIR="${HOME}/Library/Caches/sia-notifier"
ENV_FILE="${HOME}/.config/sia-notifier/env"
BASELINE_PATH="${CACHE_DIR}/tuning-baseline.json"
READINESS_REPORT="${CACHE_DIR}/backtest-readiness-report.html"
FACTOR_REPORT="${CACHE_DIR}/factor-breakdown-report.html"
OUTPUT_PATH="${CACHE_DIR}/tuning-compare.html"
ROOT_DIR="/Users/dohyeon/Documents/Playground/SIA"

mkdir -p "${CACHE_DIR}"

if [[ -f "${ENV_FILE}" ]]; then
  source "${ENV_FILE}"
fi

python3 - "${BASELINE_PATH}" "${READINESS_REPORT}" "${FACTOR_REPORT}" "${OUTPUT_PATH}" "${ROOT_DIR}/src" <<'PY'
import json
import os
import sys
from datetime import datetime
from pathlib import Path

baseline_path = Path(sys.argv[1])
readiness_path = Path(sys.argv[2])
factor_path = Path(sys.argv[3])
output_path = Path(sys.argv[4])
sys.path.insert(0, sys.argv[5])
from sia.report_parser import extract_chip_value, extract_first_label_value, extract_heading_paragraph, read_html


def esc(text: object) -> str:
    value = "" if text is None else str(text)
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
def load_current() -> dict:
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
    return {
        "captured_at": datetime.now().isoformat(timespec="seconds"),
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
        },
    }


baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
current = load_current()

metric_rows = [
    ("준비도 판정", baseline.get("readiness", {}).get("verdict"), current["readiness"].get("verdict")),
    ("신호 수", baseline.get("readiness", {}).get("signals"), current["readiness"].get("signals")),
    ("정합 신호 수", baseline.get("readiness", {}).get("strict_aligned"), current["readiness"].get("strict_aligned")),
    ("준비 구간 수", baseline.get("readiness", {}).get("ready_buckets"), current["readiness"].get("ready_buckets")),
    ("팩터 스냅샷 수", baseline.get("factor", {}).get("snapshots"), current["factor"].get("snapshots")),
    ("팩터 표본 수", baseline.get("factor", {}).get("samples"), current["factor"].get("samples")),
    ("가장 강한 조합", baseline.get("factor", {}).get("best_combo"), current["factor"].get("best_combo")),
]

tuning_rows = []
baseline_tuning = baseline.get("tuning", {})
for key, current_value in current["tuning"].items():
    tuning_rows.append((key, baseline_tuning.get(key), current_value))

metric_html = "".join(
    f"""
    <tr>
      <td>{esc(label)}</td>
      <td>{esc(base)}</td>
      <td>{esc(now)}</td>
    </tr>
    """
    for label, base, now in metric_rows
)

tuning_html = "".join(
    f"""
    <tr>
      <td><code>{esc(key)}</code></td>
      <td>{esc(base)}</td>
      <td>{esc(now)}</td>
    </tr>
    """
    for key, base, now in tuning_rows
)

baseline_at = baseline.get("captured_at", "-")
current_at = current.get("captured_at", "-")

html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 튜닝 비교</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255, 252, 246, 0.88);
      --ink: #171411;
      --muted: #6c6257;
      --line: rgba(23, 20, 17, 0.12);
      --shadow: 0 18px 50px rgba(33, 24, 14, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      color: var(--ink);
      font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(21,94,99,0.18), transparent 24%),
        radial-gradient(circle at bottom right, rgba(198,157,90,0.16), transparent 20%),
        linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
    }}
    .shell {{
      width: min(1200px, 100%);
      margin: 0 auto;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 22px;
      margin-bottom: 18px;
    }}
    h1 {{
      margin: 0 0 10px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(34px, 6vw, 60px);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      color: var(--muted);
      font-size: 13px;
      margin-top: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel">
      <h1>SIA 튜닝<br>비교</h1>
      <p>현재 리포트와 저장된 기준선의 차이를 보여줍니다. 준비도가 준비 완료에 도달하면 이 페이지로 튜닝 전후 차이를 바로 읽을 수 있습니다.</p>
      <div class="meta">
        <span>기준선 시각: {esc(baseline_at)}</span>
        <span>현재 시각: {esc(current_at)}</span>
        <span>기준선 파일: {esc(baseline_path)}</span>
      </div>
    </section>
    <section class="panel">
      <h2>핵심 지표 비교</h2>
      <table>
        <thead>
          <tr><th>항목</th><th>기준선</th><th>현재</th></tr>
        </thead>
        <tbody>
          {metric_html}
        </tbody>
      </table>
    </section>
    <section class="panel">
      <h2>튜닝 파라미터 비교</h2>
      <table>
        <thead>
          <tr><th>파라미터</th><th>기준선</th><th>현재</th></tr>
        </thead>
        <tbody>
          {tuning_html}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""

output_path.write_text(html_doc)
print(str(output_path))
PY

if [[ "${SIA_NO_OPEN_TUNING_COMPARE:-0}" != "1" ]]; then
  open "${OUTPUT_PATH}"
fi
