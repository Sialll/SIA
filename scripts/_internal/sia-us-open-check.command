#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${HOME}/.config/sia-notifier/env"
CACHE_DIR="${XDG_CACHE_HOME:-$HOME/Library/Caches}/sia-notifier"
REPORT_FILE="${CACHE_DIR}/us-open-check-report.html"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRATCH_DB="${CACHE_DIR}/us-open-check.sqlite"

mkdir -p "$CACHE_DIR"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$ENV_FILE"
fi

export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"

rm -f "$SCRATCH_DB"
SIA_NO_OPEN_DASHBOARD=1 \
SIA_NO_OPEN_LAST_RUN=1 \
SIGNAL_DB_PATH="$SCRATCH_DB" \
bash "${PROJECT_ROOT}/scripts/_internal/sia-notifier-launch.command" balanced --dry-run >/dev/null 2>&1 || true

SIA_NO_OPEN_DASHBOARD=1 \
bash "${PROJECT_ROOT}/scripts/_internal/sia-dashboard.command" >/dev/null 2>&1 || true

"$PYTHON_BIN" - "$REPORT_FILE" <<'PY'
from __future__ import annotations

import collections
import datetime as dt
import html
import os
import sqlite3
import sys
from pathlib import Path

from sia.default_universe import merge_market_tickers, use_default_universe
from sia.market_runtime import load_enabled_markets, open_markets, selection_file_path


report_path = Path(sys.argv[1]).expanduser()
db_path = Path.home() / "sia-notifier" / "trading_signal_notifier.sqlite"


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def tickers(raw: object) -> list[str]:
    return [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]


enabled_markets = load_enabled_markets(selection_file_path())
include_default_universe = use_default_universe(os.getenv("SIA_INCLUDE_DEFAULT_UNIVERSE", "1"))
market_tickers = {
    "US": list(merge_market_tickers("US", tickers(os.getenv("TICKERS_US", os.getenv("TICKERS", ""))), include_default_universe=include_default_universe)),
    "KR": list(merge_market_tickers("KR", tickers(os.getenv("TICKERS_KR", "")), include_default_universe=include_default_universe)),
    "EU": list(merge_market_tickers("EU", tickers(os.getenv("TICKERS_EU", "")), include_default_universe=include_default_universe)),
    "JP": list(merge_market_tickers("JP", tickers(os.getenv("TICKERS_JP", "")), include_default_universe=include_default_universe)),
}
watchlist = [(market, ticker) for market in enabled_markets for ticker in market_tickers.get(market, [])]
latest_ts = None
fresh_seconds = int(str(os.getenv("SIA_US_OPEN_CHECK_FRESH_SECONDS", "5400")).strip() or "5400")
now_dt = dt.datetime.now()
now_ts = int(now_dt.timestamp())
fresh_cutoff = now_ts - fresh_seconds
latest_snapshot_by_ticker: dict[str, tuple[int | None, str]] = {}
latest_price_tick_by_ticker: dict[str, tuple[int | None, str]] = {}
if db_path.exists():
    with sqlite3.connect(str(db_path)) as conn:
        last_row = conn.execute("SELECT MAX(ts) FROM dashboard_snapshots").fetchone()
        latest_ts = last_row[0] if last_row else None
        for _market, ticker in watchlist:
            snapshot_row = conn.execute(
                "SELECT ts, COALESCE(signal_source, '') FROM dashboard_snapshots WHERE ticker=? ORDER BY ts DESC, id DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if snapshot_row:
                latest_snapshot_by_ticker[ticker] = (int(snapshot_row[0]) if snapshot_row[0] is not None else None, str(snapshot_row[1] or ""))
            price_tick_row = conn.execute(
                "SELECT ts, COALESCE(source, '') FROM price_ticks WHERE ticker=? ORDER BY ts DESC, rowid DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if price_tick_row:
                latest_price_tick_by_ticker[ticker] = (int(price_tick_row[0]) if price_tick_row[0] is not None else None, str(price_tick_row[1] or ""))

open_markets_now = set(open_markets(enabled_markets))
visible_tickers: set[str] = set()
for market, ticker in watchlist:
    snapshot_meta = latest_snapshot_by_ticker.get(ticker)
    if not snapshot_meta:
        continue
    snapshot_ts, _snapshot_source = snapshot_meta
    if snapshot_ts is None:
        continue
    if market in open_markets_now:
        if snapshot_ts >= fresh_cutoff:
            visible_tickers.add(ticker)
    else:
        visible_tickers.add(ticker)

missing = []
for market, ticker in watchlist:
    if ticker in visible_tickers:
        continue
    snapshot_ts, snapshot_source = latest_snapshot_by_ticker.get(ticker, (None, ""))
    price_tick_ts, price_tick_source = latest_price_tick_by_ticker.get(ticker, (None, ""))
    if market not in open_markets_now:
        reason = "시장 휴장"
        action = "장 시작 후 자동 갱신 대기"
    elif price_tick_ts is None:
        reason = "가격 데이터 없음"
        action = "가격 수집 경로 점검"
    elif snapshot_ts is None:
        reason = "신호 스냅샷 미생성"
        action = "엔진 1회 실행 결과 확인"
    elif snapshot_ts < fresh_cutoff and price_tick_ts >= fresh_cutoff and snapshot_source and price_tick_source and snapshot_source != price_tick_source:
        reason = "source 불일치"
        action = "엄격 기준 source 정합성 점검"
    elif snapshot_ts < fresh_cutoff and price_tick_ts >= fresh_cutoff:
        reason = "메인 반영 지연"
        action = "대시보드/엔진 갱신 경로 점검"
    elif snapshot_ts < fresh_cutoff:
        reason = "최신 스냅샷 대기"
        action = "다음 수집 주기 대기"
    else:
        reason = "표시 조건 재확인 필요"
        action = "메인 필터/표시 경로 점검"
    missing.append((market, ticker, reason, action, snapshot_ts, snapshot_source, price_tick_ts, price_tick_source))

visible_count = len([1 for _, ticker in watchlist if ticker in visible_tickers])
total_count = len(watchlist)
coverage = (visible_count / total_count * 100.0) if total_count else 0.0
if not enabled_markets:
    status = "시장 없음"
    status_tone = "info"
elif not open_markets_now:
    status = "시장 휴장"
    status_tone = "info"
elif total_count and visible_count == total_count:
    status = "정상"
    status_tone = "ok"
else:
    status = "확인 필요"
    status_tone = "warn"

reason_counts = collections.Counter(reason for _, _, reason, *_ in missing)
reason_rows = "".join(
    f"<tr><td>{esc(reason)}</td><td>{count}</td></tr>"
    for reason, count in reason_counts.items()
) or "<tr><td colspan='2'>누락 없음</td></tr>"

missing_rows = "".join(
    (
        "<tr>"
        f"<td>{esc(market)}</td>"
        f"<td>{esc(ticker)}</td>"
        f"<td>{esc(reason)}</td>"
        f"<td>{esc(action)}</td>"
        f"<td>{esc(dt.datetime.fromtimestamp(snapshot_ts).strftime('%Y-%m-%d %H:%M:%S') if snapshot_ts else '없음')}</td>"
        f"<td>{esc(snapshot_source or '없음')}</td>"
        f"<td>{esc(dt.datetime.fromtimestamp(price_tick_ts).strftime('%Y-%m-%d %H:%M:%S') if price_tick_ts else '없음')}</td>"
        f"<td>{esc(price_tick_source or '없음')}</td>"
        "</tr>"
    )
    for market, ticker, reason, action, snapshot_ts, snapshot_source, price_tick_ts, price_tick_source in missing
) or "<tr><td colspan='8'>누락 없음</td></tr>"

html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>미국장 시작 점검</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255, 252, 246, 0.88);
      --ink: #171411;
      --muted: #6c6257;
      --line: rgba(23, 20, 17, 0.12);
      --ok: #155e63;
      --warn: #9a3412;
      --shadow: 0 18px 50px rgba(33, 24, 14, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
      background: linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
      padding: 24px;
    }}
    .shell {{ width: min(1080px, 100%); margin: 0 auto; }}
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
      font-size: clamp(32px, 6vw, 60px);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }}
    .meta {{ display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 13px; margin-top: 12px; }}
    .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .stat {{ border: 1px solid var(--line); border-radius: 18px; padding: 16px; background: rgba(255,255,255,0.65); }}
    .stat .label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
    .stat .value {{ margin-top: 8px; font-size: 28px; font-weight: 700; }}
    .tone {{
      display: inline-flex; align-items: center; min-height: 28px; padding: 0 10px; border-radius: 999px;
      border: 1px solid var(--line); font-size: 12px; font-weight: 700;
    }}
    .tone.ok {{ color: var(--ok); background: rgba(21,94,99,0.10); border-color: rgba(21,94,99,0.18); }}
    .tone.warn {{ color: var(--warn); background: rgba(154,52,18,0.10); border-color: rgba(154,52,18,0.18); }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 12px 10px; border-bottom: 1px solid var(--line); }}
    th {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="panel">
      <h1>미국장 시작 점검</h1>
      <p>미국장 시작 직후 드라이런 1회로 현재 관심 종목이 메인에 얼마나 반영됐는지 확인하는 자동 점검 결과입니다.</p>
      <div class="meta">
        <span>생성 시각: {esc(now_dt.strftime("%Y-%m-%d %H:%M:%S"))}</span>
        <span>마지막 스냅샷: {esc(dt.datetime.fromtimestamp(int(latest_ts)).strftime("%Y-%m-%d %H:%M:%S") if latest_ts else '없음')}</span>
        <span>활성 시장: {esc(', '.join(enabled_markets) if enabled_markets else '없음')}</span>
        <span>신선도 기준: 최근 {fresh_seconds // 60}분</span>
      </div>
    </section>
    <section class="panel">
      <div class="stats">
        <div class="stat"><div class="label">판정</div><div class="value"><span class="tone {status_tone}">{status}</span></div></div>
        <div class="stat"><div class="label">관심 종목 수</div><div class="value">{total_count}</div></div>
        <div class="stat"><div class="label">메인 반영 수</div><div class="value">{visible_count}</div></div>
        <div class="stat"><div class="label">반영률</div><div class="value">{coverage:.1f}%</div></div>
      </div>
    </section>
    <section class="panel">
      <h2>누락 사유 요약</h2>
      <table>
        <thead>
          <tr><th>사유</th><th>건수</th></tr>
        </thead>
        <tbody>
          {reason_rows}
        </tbody>
      </table>
    </section>
    <section class="panel">
      <h2>누락 종목</h2>
      <table>
        <thead>
          <tr><th>시장</th><th>티커</th><th>사유</th><th>다음 점검</th><th>최근 스냅샷</th><th>스냅샷 소스</th><th>최근 가격 틱</th><th>가격 소스</th></tr>
        </thead>
        <tbody>
          {missing_rows}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>"""

report_path.write_text(html_doc, encoding="utf-8")
print(report_path)
PY

if [[ "${SIA_NO_OPEN_US_OPEN_CHECK:-0}" != "1" ]] && command -v open >/dev/null 2>&1; then
  open "$REPORT_FILE" >/dev/null 2>&1 || true
fi

echo "미국장 시작 점검: $REPORT_FILE"
