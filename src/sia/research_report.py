from __future__ import annotations

import argparse
import html
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    from .report_common import localize_report_html, render_empty_report_html
    from .report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts
    from .report_theme import render_report_theme
    from .report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section
except ImportError:
    from report_common import localize_report_html, render_empty_report_html  # type: ignore
    from report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section  # type: ignore


@dataclass(frozen=True)
class Snapshot:
    ts: int
    ticker: str
    signal: str
    confidence: float
    price: float
    composite_score: float
    risk_level: str
    momentum: str
    macro_environment: str


@dataclass(frozen=True)
class ForwardSample:
    ticker: str
    ts: int
    signal: str
    confidence: float
    composite_score: float
    risk_level: str
    momentum: str
    macro_environment: str
    horizon: int
    forward_return: float
    signal_edge: float | None
    hit: bool


@dataclass(frozen=True)
class ResearchInputs:
    snapshots: list[Snapshot]
    horizons: list[int]


@dataclass(frozen=True)
class ResearchSummary:
    samples: list[ForwardSample]


BUCKET_ORDER = [
    "strong_buy_zone",
    "buy_zone",
    "neutral_zone",
    "sell_zone",
    "strong_sell_zone",
]

BUCKET_LABELS = {
    "strong_buy_zone": "강한 매수 구간 (>= 60점)",
    "buy_zone": "매수 구간 (35점 ~ 59점)",
    "neutral_zone": "중립 구간 (-34점 ~ 34점)",
    "sell_zone": "매도 구간 (-59점 ~ -35점)",
    "strong_sell_zone": "강한 매도 구간 (<= -60점)",
}


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def score_bucket(score: float) -> str:
    if score >= 0.60:
        return "strong_buy_zone"
    if score >= 0.35:
        return "buy_zone"
    if score <= -0.60:
        return "strong_sell_zone"
    if score <= -0.35:
        return "sell_zone"
    return "neutral_zone"


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 리서치 리포트", message)


def localize_output_html(text: str) -> str:
    return localize_report_html(
        text,
        [
            ("HOLD", "관망"),
        ],
    )


def load_snapshots(db_path: Path) -> list[Snapshot]:
    with sqlite3.connect(str(db_path)) as conn:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dashboard_snapshots'"
        ).fetchone()
        if table_exists is None:
            return []
        rows = conn.execute(
            """
            SELECT
                ts, ticker, signal, confidence, price,
                composite_score, risk_level, momentum, macro_environment
            FROM dashboard_snapshots
            ORDER BY ticker ASC, ts ASC, id ASC
            """
        ).fetchall()

    snapshots: list[Snapshot] = []
    for row in rows:
        snapshots.append(
            Snapshot(
                ts=int(row[0]),
                ticker=str(row[1]),
                signal=str(row[2]),
                confidence=float(row[3]),
                price=float(row[4]),
                composite_score=float(row[5]),
                risk_level=str(row[6]),
                momentum=str(row[7]),
                macro_environment=str(row[8]),
            )
        )
    return snapshots


def build_forward_samples(snapshots: list[Snapshot], horizons: list[int]) -> list[ForwardSample]:
    by_ticker: dict[str, list[Snapshot]] = defaultdict(list)
    for item in snapshots:
        by_ticker[item.ticker].append(item)

    samples: list[ForwardSample] = []
    for ticker, series in by_ticker.items():
        for index, item in enumerate(series):
            if item.price <= 0:
                continue
            for horizon in horizons:
                future_index = index + horizon
                if future_index >= len(series):
                    continue
                future = series[future_index]
                if future.price <= 0:
                    continue
                forward_return = (future.price / item.price) - 1.0
                if item.signal == "BUY":
                    signal_edge = forward_return
                    hit = forward_return > 0
                elif item.signal == "SELL":
                    signal_edge = -forward_return
                    hit = forward_return < 0
                else:
                    signal_edge = None
                    hit = abs(forward_return) <= 0.01
                samples.append(
                    ForwardSample(
                        ticker=ticker,
                        ts=item.ts,
                        signal=item.signal,
                        confidence=item.confidence,
                        composite_score=item.composite_score,
                        risk_level=item.risk_level,
                        momentum=item.momentum,
                        macro_environment=item.macro_environment,
                        horizon=horizon,
                        forward_return=forward_return,
                        signal_edge=signal_edge,
                        hit=hit,
                    )
                )
    return samples


def summarize_signals(samples: list[ForwardSample], horizons: list[int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        horizon_samples = [item for item in samples if item.horizon == horizon]
        for signal in ("BUY", "SELL", "HOLD"):
            filtered = [item for item in horizon_samples if item.signal == signal]
            if not filtered:
                continue
            row: dict[str, object] = {
                "horizon": horizon,
                "signal": signal,
                "samples": len(filtered),
                "avg_forward_return": avg([item.forward_return for item in filtered]),
            }
            if signal == "HOLD":
                abs_moves = [abs(item.forward_return) for item in filtered]
                row["signal_edge"] = avg(abs_moves)
                row["rate_label"] = "calm rate"
                row["rate"] = avg([1.0 if item.hit else 0.0 for item in filtered])
            else:
                row["signal_edge"] = avg([item.signal_edge for item in filtered if item.signal_edge is not None])
                row["rate_label"] = "hit rate"
                row["rate"] = avg([1.0 if item.hit else 0.0 for item in filtered])
            rows.append(row)
    return rows


def summarize_score_buckets(samples: list[ForwardSample], horizons: list[int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        horizon_samples = [item for item in samples if item.horizon == horizon]
        for bucket in BUCKET_ORDER:
            filtered = [item for item in horizon_samples if score_bucket(item.composite_score) == bucket]
            if not filtered:
                continue
            rows.append(
                {
                    "horizon": horizon,
                    "bucket": BUCKET_LABELS[bucket],
                    "samples": len(filtered),
                    "avg_forward_return": avg([item.forward_return for item in filtered]),
                    "avg_abs_move": avg([abs(item.forward_return) for item in filtered]),
                    "avg_confidence": avg([item.confidence for item in filtered]),
                }
            )
    return rows


def summarize_tickers(samples: list[ForwardSample], horizon: int) -> list[dict[str, object]]:
    filtered = [item for item in samples if item.horizon == horizon and item.signal in {"BUY", "SELL"}]
    by_ticker: dict[str, list[ForwardSample]] = defaultdict(list)
    for item in filtered:
        by_ticker[item.ticker].append(item)

    rows: list[dict[str, object]] = []
    for ticker, series in by_ticker.items():
        edges = [item.signal_edge for item in series if item.signal_edge is not None]
        if not edges:
            continue
        rows.append(
            {
                "ticker": ticker,
                "samples": len(series),
                "avg_signal_edge": avg(edges),
                "avg_forward_return": avg([item.forward_return for item in series]),
                "hit_rate": avg([1.0 if item.hit else 0.0 for item in series]),
            }
        )
    rows.sort(key=lambda item: (item["avg_signal_edge"] is None, item["avg_signal_edge"]), reverse=True)
    return rows


def render_html(
    db_path: Path,
    snapshots: list[Snapshot],
    samples: list[ForwardSample],
    horizons: list[int],
) -> str:
    if not snapshots:
        return build_empty_html("dashboard_snapshots 데이터가 없습니다. notifier를 먼저 실행하세요.")
    if not samples:
        return build_empty_html("리서치 샘플이 없습니다. 같은 티커에 대해 최소 2개 이상의 snapshot이 필요합니다.")

    signal_rows = summarize_signals(samples, horizons)
    bucket_rows = summarize_score_buckets(samples, horizons)
    leaderboard_rows = summarize_tickers(samples, 3 if 3 in horizons else horizons[0])

    unique_tickers = len({item.ticker for item in snapshots})
    first_ts = fmt_ts(snapshots[0].ts)
    last_ts = fmt_ts(snapshots[-1].ts)
    total_buy_sell = len([item for item in samples if item.signal in {"BUY", "SELL"}])
    strongest_bucket = None
    bucket_h3 = [item for item in bucket_rows if item["horizon"] == (3 if 3 in horizons else horizons[0])]
    if bucket_h3:
        strongest_bucket = max(
            bucket_h3,
            key=lambda item: (item["avg_forward_return"] is not None, item["avg_forward_return"]),
        )

    signal_table_html = []
    for row in signal_rows:
        metric_label = "평균 절대 변동" if row["signal"] == "HOLD" else "평균 시그널 엣지"
        rate_label = "평온 비율" if row["signal"] == "HOLD" else "적중률"
        signal_table_html.append(
            f"""
            <tr>
              <td>+{row['horizon']} snapshot</td>
              <td>{esc(row['signal'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_forward_return'])}</td>
              <td>{fmt_pct(row['signal_edge'])}</td>
              <td>{fmt_pct(row['rate'])}</td>
            </tr>
            """
        )

    bucket_table_html = []
    for row in bucket_rows:
        bucket_table_html.append(
            f"""
            <tr>
              <td>+{row['horizon']} snapshot</td>
              <td>{esc(row['bucket'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_forward_return'])}</td>
              <td>{fmt_pct(row['avg_abs_move'])}</td>
              <td>{fmt_score(row['avg_confidence'])}</td>
            </tr>
            """
        )

    leaderboard_html = []
    for row in leaderboard_rows[:12]:
        leaderboard_html.append(
            f"""
            <tr>
              <td>{esc(row['ticker'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_signal_edge'])}</td>
              <td>{fmt_pct(row['avg_forward_return'])}</td>
              <td>{fmt_pct(row['hit_rate'])}</td>
            </tr>
            """
        )

    strongest_bucket_text = (
        f"{strongest_bucket['bucket']} / 평균 미래 수익률 {fmt_pct(strongest_bucket['avg_forward_return'])}"
        if strongest_bucket
        else "충분한 3-snapshot 데이터 없음"
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 리서치 리포트</title>
  <style>
    {render_report_theme()}
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255, 252, 246, 0.88);
      --ink: #171411;
      --muted: #6c6257;
      --line: rgba(23, 20, 17, 0.12);
      --buy: #155e63;
      --sell: #9a3412;
      --gold: #c69d5a;
      --shadow: 0 18px 50px rgba(33, 24, 14, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font-family: "Avenir Next", "Helvetica Neue", Helvetica, Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(21,94,99,0.18), transparent 24%),
        radial-gradient(circle at top right, rgba(198,157,90,0.16), transparent 20%),
        linear-gradient(180deg, #f7f1e8 0%, #efe7db 100%);
      padding: 24px;
    }}
    .shell {{
      width: min(1280px, 100%);
      margin: 0 auto;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 16px;
      margin-bottom: 18px;
    }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 26px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(14px);
    }}
    .intro {{
      padding: 28px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(34px, 6vw, 68px);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }}
    .intro p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
      max-width: 48rem;
    }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 16px;
      color: var(--muted);
      font-size: 14px;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      padding: 18px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
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
      font-size: 28px;
      font-weight: 700;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-bottom: 18px;
    }}
    .summary-box {{
      padding: 20px;
    }}
    .summary-box h2 {{
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    .summary-box p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .table-panel {{
      padding: 18px;
      margin-bottom: 18px;
      overflow-x: auto;
    }}
    .table-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }}
    .table-head h2 {{
      margin: 0;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    .table-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      min-width: 760px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .footnote {{
      padding: 20px;
      color: var(--muted);
      line-height: 1.7;
    }}
    .accent-buy {{ color: var(--buy); }}
    .accent-sell {{ color: var(--sell); }}
    .accent-gold {{ color: #7a560d; }}
    @media (max-width: 860px) {{
      body {{ padding: 14px; }}
      .hero {{ grid-template-columns: 1fr; }}
      .summary-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    {render_hero_section(
        "SIA<br>Research",
        "저장된 <code>dashboard_snapshots</code>만 사용해 신호 이후 미래 성과를 점검하는 로컬 리서치 리포트입니다. 기준은 시장일이 아니라 같은 티커의 다음 snapshot 개수입니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"데이터 구간: {esc(first_ts)} ~ {esc(last_ts)}",
            f"Horizon: {esc(', '.join(str(item) for item in horizons))}",
        ]),
        render_stats_panel([
            ("Snapshots", str(len(snapshots))),
            ("Tickers", str(unique_tickers)),
            ("Samples", str(len(samples))),
            ("BUY/SELL", str(total_buy_sell)),
        ]),
    )}

    <section class="summary-grid">
      {render_summary_panel("핵심 해석", "<p><span class='accent-buy'>Signal Edge</span>는 BUY면 미래 수익률, SELL이면 역방향 수익률입니다. 값이 플러스면 해당 신호가 방향성 측면에서 유리하게 작동했다는 뜻입니다. HOLD는 방향 적중 대신 미래 절대 변동이 작을수록 좋게 봅니다.</p>")}
      {render_summary_panel("현재 가장 강한 점수 구간", f"<p>{esc(strongest_bucket_text)}</p>")}
    </section>

    {render_table_section(
        "신호별 성과",
        "평균 미래 수익률 / 시그널 엣지 / 적중률(또는 평온 비율)",
        ["Horizon", "Signal", "Samples", "평균 미래 수익률", "평균 시그널 엣지", "적중률"],
        ''.join(signal_table_html),
    )}

    {render_table_section(
        "점수 구간 연구",
        "Composite Score 구간별 미래 수익률과 변동 정도",
        ["Horizon", "Bucket", "Samples", "평균 미래 수익률", "평균 절대 변동", "평균 신뢰도"],
        ''.join(bucket_table_html),
    )}

    {render_table_section(
        "티커 리더보드",
        esc(f"+{3 if 3 in horizons else horizons[0]} snapshot 기준, BUY/SELL만 집계"),
        ["Ticker", "Samples", "평균 시그널 엣지", "평균 미래 수익률", "적중률"],
        ''.join(leaderboard_html),
    )}

    {render_footnote_section(
        "방법론 메모",
        "1. 이 리포트는 외부 데이터 재조회 없이 현재 DB에 저장된 snapshot만 사용합니다.<br>2. Horizon `+3 snapshot`은 같은 티커의 다음 세 번째 snapshot 가격을 뜻합니다.<br>3. 표본 수가 적으면 결과가 쉽게 흔들리므로, 티커 수와 운영 기간을 늘린 뒤 다시 보는 편이 좋습니다.",
    )}
  </main>
</body>
</html>"""


def load_report_inputs(db_path: Path, horizons: list[int]) -> ResearchInputs:
    return ResearchInputs(
        snapshots=load_snapshots(db_path),
        horizons=horizons,
    )


def summarize_report(inputs: ResearchInputs) -> ResearchSummary:
    return ResearchSummary(samples=build_forward_samples(inputs.snapshots, inputs.horizons))


def render_report(db_path: Path, inputs: ResearchInputs, summary: ResearchSummary) -> str:
    return localize_output_html(render_html(db_path, inputs.snapshots, summary.samples, inputs.horizons))


def write_report(db_path: Path, output_path: Path, horizons: list[int]) -> Path:
    inputs = load_report_inputs(db_path, horizons)
    summary = summarize_report(inputs)
    html_doc = render_report(db_path, inputs, summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_doc, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate lightweight research report from dashboard snapshots.")
    parser.add_argument("--db-path", required=True, help="Path to trading_signal_notifier sqlite db")
    parser.add_argument("--output", required=True, help="HTML output path")
    parser.add_argument("--horizons", default="1,3,5", help="Comma-separated future snapshot horizons")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser()
    output_path = Path(args.output).expanduser()
    horizons = [int(item.strip()) for item in args.horizons.split(",") if item.strip()]
    if not horizons:
        horizons = [1, 3, 5]
    write_report(db_path, output_path, horizons)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
