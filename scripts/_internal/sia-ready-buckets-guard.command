#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
READINESS_REPORT="${CACHE_DIR}/backtest-readiness-report.html"
TUNING_COMPARE_REPORT="${CACHE_DIR}/tuning-compare.html"
OUTPUT_REPORT="${CACHE_DIR}/readiness-guard-report.html"
THRESHOLD="${SIA_READY_BUCKETS_RETUNE_THRESHOLD:-2}"

mkdir -p "$CACHE_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

if ! [[ "$THRESHOLD" =~ ^[0-9]+$ ]]; then
  echo "잘못된 SIA_READY_BUCKETS_RETUNE_THRESHOLD: ${THRESHOLD}" >&2
  exit 2
fi

if [[ ! -f "$READINESS_REPORT" ]]; then
  cat > "$OUTPUT_REPORT" <<EOF
<!doctype html>
<html lang="ko">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SIA 준비도 가드</title></head>
<body><p>readiness 리포트가 없습니다: ${READINESS_REPORT}</p></body>
</html>
EOF
  echo "$OUTPUT_REPORT"
  exit 0
fi

guard_output="$(
python3 - "$READINESS_REPORT" "$THRESHOLD" "${PROJECT_ROOT}/src" <<'PY'
import sys
from pathlib import Path

sys.path.insert(0, sys.argv[3])
from sia.report_parser import extract_first_label_value, read_html

text = read_html(Path(sys.argv[1]))
threshold = int(sys.argv[2])
verdict = extract_first_label_value(text, ("판정", "Verdict")) or ""
signals = extract_first_label_value(text, ("신호 수", "Signals")) or ""
strict_aligned = extract_first_label_value(text, ("정합 신호 수", "Strict Aligned")) or ""
ready_buckets = extract_first_label_value(text, ("준비 구간 수", "Ready Buckets")) or ""
try:
    ready_value = int(ready_buckets)
except ValueError:
    ready_value = 0

action = "run_compare" if ready_value >= threshold else "skip_compare"
message = (
    f"준비 구간 수 {ready_value}가 기준 {threshold} 이상이므로 튜닝 비교를 갱신합니다."
    if action == "run_compare"
    else f"준비 구간 수 {ready_value}가 기준 {threshold} 미만이므로 튜닝 비교는 유지합니다."
)

print(action)
print(verdict)
print(signals)
print(strict_aligned)
print(ready_buckets)
print(message)
PY
)"

ACTION="$(printf '%s\n' "$guard_output" | sed -n '1p')"
VERDICT="$(printf '%s\n' "$guard_output" | sed -n '2p')"
SIGNALS="$(printf '%s\n' "$guard_output" | sed -n '3p')"
STRICT_ALIGNED="$(printf '%s\n' "$guard_output" | sed -n '4p')"
READY_BUCKETS="$(printf '%s\n' "$guard_output" | sed -n '5p')"
MESSAGE="$(printf '%s\n' "$guard_output" | sed -n '6p')"
ACTION_STATUS="SKIPPED"

if [[ "$ACTION" == "run_compare" ]]; then
  SIA_NO_OPEN_TUNING_COMPARE=1 \
    "${PROJECT_ROOT}/scripts/_internal/sia-compare-tuning.command" >/dev/null
  ACTION_STATUS="UPDATED"
fi

python3 - "$OUTPUT_REPORT" "$READINESS_REPORT" "$TUNING_COMPARE_REPORT" "$VERDICT" "$SIGNALS" "$STRICT_ALIGNED" "$READY_BUCKETS" "$THRESHOLD" "$ACTION_STATUS" "$MESSAGE" <<'PY'
import datetime as dt
import html
import sys
from pathlib import Path

output_path = Path(sys.argv[1])
readiness_report = Path(sys.argv[2])
tuning_compare_report = Path(sys.argv[3])
verdict = sys.argv[4]
signals = sys.argv[5]
strict_aligned = sys.argv[6]
ready_buckets = sys.argv[7]
threshold = sys.argv[8]
action_status = sys.argv[9]
message = sys.argv[10]


def esc(value):
    return html.escape("" if value is None else str(value))


html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 준비도 가드</title>
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
      width: min(900px, 100%);
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
      font-size: clamp(34px, 6vw, 58px);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }}
    p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,0.6);
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .value {{
      margin-top: 6px;
      font-size: 24px;
      font-weight: 700;
    }}
    .links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 18px;
    }}
    .link {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel">
      <h1>SIA 준비도<br>가드</h1>
      <p>{esc(message)}</p>
      <div class="meta">
        <div class="metric"><div class="label">판정</div><div class="value">{esc(verdict)}</div></div>
        <div class="metric"><div class="label">신호 수</div><div class="value">{esc(signals)}</div></div>
        <div class="metric"><div class="label">정합 신호 수</div><div class="value">{esc(strict_aligned)}</div></div>
        <div class="metric"><div class="label">준비 구간 수</div><div class="value">{esc(ready_buckets)}</div></div>
        <div class="metric"><div class="label">기준값</div><div class="value">{esc(threshold)}</div></div>
        <div class="metric"><div class="label">조치</div><div class="value">{esc(action_status)}</div></div>
      </div>
      <div class="links">
        <a class="link" href="{esc(readiness_report.name)}" target="_blank" rel="noreferrer">준비도 리포트</a>
        <a class="link" href="{esc(tuning_compare_report.name)}" target="_blank" rel="noreferrer">튜닝 비교</a>
      </div>
      <p style="margin-top:18px;">생성 시각: {esc(dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>
    </section>
  </main>
</body>
</html>
"""

output_path.write_text(html_doc, encoding="utf-8")
print(str(output_path))
PY

echo "$OUTPUT_REPORT"
