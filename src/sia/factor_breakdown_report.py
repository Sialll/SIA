from __future__ import annotations

import argparse
import html
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import price_backtest_report as price_report

try:
    from .report_common import localize_report_html, render_empty_report_html
    from .report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts, pearson, read_float_env, read_positive_int_env
    from .report_theme import render_report_theme
    from .report_widgets import render_gate_strip, render_hero_section, render_meta_row, render_notes_section, render_stats_panel, render_summary_panel, render_table_section
except ImportError:
    from report_common import localize_report_html, render_empty_report_html  # type: ignore
    from report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts, pearson, read_float_env, read_positive_int_env  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import render_gate_strip, render_hero_section, render_meta_row, render_notes_section, render_stats_panel, render_summary_panel, render_table_section  # type: ignore


HORIZONS = [1, 3, 5]
FACTOR_FIELDS = [
    ("chart_score", "차트"),
    ("macro_score", "매크로"),
    ("event_score", "이벤트"),
    ("news_score", "뉴스"),
    ("composite_score", "종합"),
]
BUCKET_ORDER = [
    "strong_negative",
    "negative",
    "neutral",
    "positive",
    "strong_positive",
]
BUCKET_LABELS = {
    "strong_negative": "강한 음수 (<= -0.50)",
    "negative": "음수 (-0.49 ~ -0.15)",
    "neutral": "중립 (-0.14 ~ 0.14)",
    "positive": "양수 (0.15 ~ 0.49)",
    "strong_positive": "강한 양수 (>= 0.50)",
}
DEFAULT_CONFIRM_LONG_RISK_OFF = 3
DEFAULT_CONFIRM_LONG_MIXED = 2
DEFAULT_CONFIRM_LONG_RISK_ON = 1
DEFAULT_CONFIRM_SHORT_RISK_OFF = 1
DEFAULT_CONFIRM_SHORT_MIXED = 2
DEFAULT_CONFIRM_SHORT_RISK_ON = 3
DEFAULT_REGIME_BUY_PENALTY_RISK_OFF = 0.18
DEFAULT_REGIME_SELL_PENALTY_RISK_ON = 0.15
DEFAULT_REGIME_EXTRA_PENALTY_OPPOSED = 0.08
DEFAULT_REGIME_BUY_BONUS_RISK_ON = 0.05
DEFAULT_REGIME_SELL_BONUS_RISK_OFF = 0.06
DEFAULT_REGIME_MULTIPLIER_MIN = 0.55
DEFAULT_REGIME_MULTIPLIER_MAX = 1.15


@dataclass(frozen=True)
class FactorSnapshot:
    ts: int
    ticker: str
    signal: str
    confidence: float
    entry_price: float
    risk_level: str
    macro_environment: str
    signal_source: str | None
    chart_score: float
    macro_score: float
    event_score: float
    news_score: float
    composite_score: float


@dataclass(frozen=True)
class FactorSample:
    ticker: str
    ts: int
    horizon: int
    forward_return: float
    chart_score: float
    macro_score: float
    event_score: float
    news_score: float
    composite_score: float


@dataclass(frozen=True)
class FactorReportInputs:
    snapshots: list[FactorSnapshot]
    price_series: dict[str, dict[str, list[price_report.PricePoint]]]


@dataclass(frozen=True)
class FactorReportSummary:
    samples: list[FactorSample]
    diagnostics: dict[str, object]
    summary_rows: list[dict[str, object]]
    bucket_rows: list[dict[str, object]]


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def load_regime_display() -> list[str]:
    return [
        (
            "롱 확인 "
            f"{read_positive_int_env('SIA_CONFIRM_LONG_RISK_OFF', DEFAULT_CONFIRM_LONG_RISK_OFF)}"
            f" / {read_positive_int_env('SIA_CONFIRM_LONG_MIXED', DEFAULT_CONFIRM_LONG_MIXED)}"
            f" / {read_positive_int_env('SIA_CONFIRM_LONG_RISK_ON', DEFAULT_CONFIRM_LONG_RISK_ON)}"
        ),
        (
            "숏 확인 "
            f"{read_positive_int_env('SIA_CONFIRM_SHORT_RISK_OFF', DEFAULT_CONFIRM_SHORT_RISK_OFF)}"
            f" / {read_positive_int_env('SIA_CONFIRM_SHORT_MIXED', DEFAULT_CONFIRM_SHORT_MIXED)}"
            f" / {read_positive_int_env('SIA_CONFIRM_SHORT_RISK_ON', DEFAULT_CONFIRM_SHORT_RISK_ON)}"
        ),
        (
            "OFF 매수 패널티 "
            f"{read_float_env('SIA_REGIME_BUY_PENALTY_RISK_OFF', DEFAULT_REGIME_BUY_PENALTY_RISK_OFF):.2f}"
        ),
        (
            "ON 매도 패널티 "
            f"{read_float_env('SIA_REGIME_SELL_PENALTY_RISK_ON', DEFAULT_REGIME_SELL_PENALTY_RISK_ON):.2f}"
        ),
        (
            "반대추세 추가 "
            f"{read_float_env('SIA_REGIME_EXTRA_PENALTY_OPPOSED', DEFAULT_REGIME_EXTRA_PENALTY_OPPOSED):.2f}"
        ),
        (
            "ON 매수 보너스 "
            f"{read_float_env('SIA_REGIME_BUY_BONUS_RISK_ON', DEFAULT_REGIME_BUY_BONUS_RISK_ON):.2f}"
        ),
        (
            "OFF 매도 보너스 "
            f"{read_float_env('SIA_REGIME_SELL_BONUS_RISK_OFF', DEFAULT_REGIME_SELL_BONUS_RISK_OFF):.2f}"
        ),
        (
            "배수 clamp "
            f"{read_float_env('SIA_REGIME_MULTIPLIER_MIN', DEFAULT_REGIME_MULTIPLIER_MIN):.2f}"
            f" ~ {read_float_env('SIA_REGIME_MULTIPLIER_MAX', DEFAULT_REGIME_MULTIPLIER_MAX):.2f}"
        ),
    ]


def score_bucket(value: float) -> str:
    if value <= -0.50:
        return "strong_negative"
    if value <= -0.15:
        return "negative"
    if value >= 0.50:
        return "strong_positive"
    if value >= 0.15:
        return "positive"
    return "neutral"


def directional_edge(score: float, forward_return: float) -> float:
    if score > 0:
        return forward_return
    if score < 0:
        return -forward_return
    return 0.0


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 팩터 분해", message)


def localize_output_html(text: str) -> str:
    return localize_report_html(
        text,
        [
            ("SIA Factor Breakdown", "SIA 팩터 분해"),
            ("Factor 요약", "팩터 요약"),
            ("factor별 horizon 성능 요약", "팩터별 기간 성능 요약"),
        ],
    )


def load_factor_snapshots(db_path: Path) -> list[FactorSnapshot]:
    with sqlite3.connect(str(db_path)) as conn:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dashboard_snapshots'"
        ).fetchone()
        if table_exists is None:
            return []
        snapshot_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(dashboard_snapshots)").fetchall()
        }
        has_signal_source = "signal_source" in snapshot_columns
        rows = conn.execute(
            (
                """
                SELECT
                    ts, ticker, signal, confidence, price, risk_level, macro_environment,
                    signal_source, chart_score, macro_score, event_score, news_score, composite_score
                FROM dashboard_snapshots
                ORDER BY ts ASC, ticker ASC, id ASC
                """
                if has_signal_source
                else
                """
                SELECT
                    ts, ticker, signal, confidence, price, risk_level, macro_environment,
                    NULL AS signal_source, chart_score, macro_score, event_score, news_score, composite_score
                FROM dashboard_snapshots
                ORDER BY ts ASC, ticker ASC, id ASC
                """
            )
        ).fetchall()

    snapshots: list[FactorSnapshot] = []
    for row in rows:
        if row[4] in (None, 0):
            continue
        snapshots.append(
            FactorSnapshot(
                ts=int(row[0]),
                ticker=str(row[1]),
                signal=str(row[2] or "HOLD"),
                confidence=float(row[3] or 0.0),
                entry_price=float(row[4]),
                risk_level=str(row[5] or "-"),
                macro_environment=str(row[6] or "-"),
                signal_source=str(row[7]) if row[7] not in (None, "") else None,
                chart_score=float(row[8] or 0.0),
                macro_score=float(row[9] or 0.0),
                event_score=float(row[10] or 0.0),
                news_score=float(row[11] or 0.0),
                composite_score=float(row[12] or 0.0),
            )
        )
    return snapshots


def align_samples(
    snapshots: list[FactorSnapshot],
    price_series: dict[str, dict[str, list[price_report.PricePoint]]],
) -> tuple[list[FactorSample], dict[str, object]]:
    diagnostics: dict[str, object] = {
        "total_snapshots": len(snapshots),
        "aligned_snapshots": 0,
        "filtered_mock_only": 0,
        "filtered_source_mismatch": 0,
        "aligned_sources": {},
    }
    aligned_items: list[tuple[FactorSnapshot, int, list[price_report.PricePoint]]] = []

    for snapshot in snapshots:
        signal_proxy = price_report.SignalSnapshot(
            ts=snapshot.ts,
            ticker=snapshot.ticker,
            signal=snapshot.signal,
            confidence=snapshot.confidence,
            entry_price=snapshot.entry_price,
            composite_score=snapshot.composite_score,
            risk_level=snapshot.risk_level,
            macro_environment=snapshot.macro_environment,
            signal_source=snapshot.signal_source,
        )
        alignment = price_report.align_signal_to_series(signal_proxy, price_series.get(snapshot.ticker, {}))
        if alignment.status == "mock_only":
            diagnostics["filtered_mock_only"] = int(diagnostics["filtered_mock_only"]) + 1
            continue
        if alignment.status != "aligned" or alignment.source is None or alignment.entry_index is None:
            diagnostics["filtered_source_mismatch"] = int(diagnostics["filtered_source_mismatch"]) + 1
            continue
        diagnostics["aligned_snapshots"] = int(diagnostics["aligned_snapshots"]) + 1
        aligned_sources = dict(diagnostics["aligned_sources"])
        aligned_sources[alignment.source] = aligned_sources.get(alignment.source, 0) + 1
        diagnostics["aligned_sources"] = aligned_sources
        series = price_series.get(snapshot.ticker, {}).get(alignment.source, [])
        aligned_items.append((snapshot, alignment.entry_index, series))

    samples: list[FactorSample] = []
    for snapshot, entry_index, series in aligned_items:
        for horizon in HORIZONS:
            exit_index = entry_index + horizon
            if exit_index >= len(series):
                continue
            exit_point = series[exit_index]
            forward_return = (exit_point.close / snapshot.entry_price) - 1.0
            samples.append(
                FactorSample(
                    ticker=snapshot.ticker,
                    ts=snapshot.ts,
                    horizon=horizon,
                    forward_return=forward_return,
                    chart_score=snapshot.chart_score,
                    macro_score=snapshot.macro_score,
                    event_score=snapshot.event_score,
                    news_score=snapshot.news_score,
                    composite_score=snapshot.composite_score,
                )
            )
    return samples, diagnostics


def build_factor_summaries(samples: list[FactorSample]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    summary_rows: list[dict[str, object]] = []
    bucket_rows: list[dict[str, object]] = []

    for factor_key, factor_label in FACTOR_FIELDS:
        for horizon in HORIZONS:
            factor_samples = [sample for sample in samples if sample.horizon == horizon]
            xs = [float(getattr(sample, factor_key)) for sample in factor_samples]
            ys = [sample.forward_return for sample in factor_samples]
            non_neutral = [sample for sample in factor_samples if abs(float(getattr(sample, factor_key))) >= 0.15]
            directional_hits = [
                directional_edge(float(getattr(sample, factor_key)), sample.forward_return) > 0
                for sample in non_neutral
            ]
            summary_rows.append(
                {
                    "factor_key": factor_key,
                    "factor_label": factor_label,
                    "horizon": horizon,
                    "samples": len(factor_samples),
                    "correlation": pearson(xs, ys),
                    "avg_score": avg(xs),
                    "avg_return": avg(ys),
                    "avg_edge": avg(
                        [
                            directional_edge(float(getattr(sample, factor_key)), sample.forward_return)
                            for sample in factor_samples
                        ]
                    ),
                    "directional_hit_rate": (
                        sum(1 for hit in directional_hits if hit) / len(directional_hits)
                        if directional_hits
                        else None
                    ),
                }
            )

            for bucket in BUCKET_ORDER:
                bucket_samples = [
                    sample
                    for sample in factor_samples
                    if score_bucket(float(getattr(sample, factor_key))) == bucket
                ]
                if not bucket_samples:
                    continue
                scores = [float(getattr(sample, factor_key)) for sample in bucket_samples]
                returns = [sample.forward_return for sample in bucket_samples]
                edges = [directional_edge(score, sample.forward_return) for score, sample in zip(scores, bucket_samples)]
                bucket_rows.append(
                    {
                        "factor_key": factor_key,
                        "factor_label": factor_label,
                        "horizon": horizon,
                        "bucket": bucket,
                        "bucket_label": BUCKET_LABELS[bucket],
                        "samples": len(bucket_samples),
                        "avg_score": avg(scores),
                        "avg_return": avg(returns),
                        "avg_edge": avg(edges),
                        "hit_rate": (
                            sum(1 for edge in edges if edge > 0) / len(edges)
                            if edges
                            else None
                        ),
                    }
                )

    return summary_rows, bucket_rows


def render_html(
    db_path: Path,
    snapshots: list[FactorSnapshot],
    samples: list[FactorSample],
    diagnostics: dict[str, object],
    summary_rows: list[dict[str, object]],
    bucket_rows: list[dict[str, object]],
) -> str:
    first_ts = min((item.ts for item in snapshots), default=None)
    last_ts = max((item.ts for item in snapshots), default=None)
    aligned_sources = ", ".join(
        f"{source}:{count}" for source, count in sorted(dict(diagnostics["aligned_sources"]).items())
    ) or "-"
    best_summary = max(
        summary_rows,
        key=lambda row: (
            -999.0 if row["avg_edge"] is None else float(row["avg_edge"]),
            int(row["samples"]),
        ),
        default=None,
    )
    best_text = (
        f"{best_summary['factor_label']} / +{best_summary['horizon']} tick / "
        f"avg edge {fmt_pct(best_summary['avg_edge'])} / corr {fmt_num(best_summary['correlation'], 3)}"
        if best_summary
        else "충분한 샘플이 아직 없습니다."
    )
    regime_chip_html = "".join(
        f'<span class="gate-chip">{esc(chip)}</span>'
        for chip in load_regime_display()
    )

    summary_html = "".join(
        f"""
        <tr>
          <td>{esc(row['factor_label'])}</td>
          <td>+{row['horizon']} tick</td>
          <td>{row['samples']}</td>
          <td>{fmt_score(row['avg_score'])}</td>
          <td>{fmt_pct(row['avg_return'])}</td>
          <td>{fmt_pct(row['avg_edge'])}</td>
          <td>{fmt_pct(row['directional_hit_rate'])}</td>
          <td>{fmt_num(row['correlation'], 3)}</td>
        </tr>
        """
        for row in summary_rows
    )
    bucket_html = "".join(
        f"""
        <tr>
          <td>{esc(row['factor_label'])}</td>
          <td>+{row['horizon']} tick</td>
          <td>{esc(row['bucket_label'])}</td>
          <td>{row['samples']}</td>
          <td>{fmt_score(row['avg_score'])}</td>
          <td>{fmt_pct(row['avg_return'])}</td>
          <td>{fmt_pct(row['avg_edge'])}</td>
          <td>{fmt_pct(row['hit_rate'])}</td>
        </tr>
        """
        for row in bucket_rows
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA Factor Breakdown</title>
  <style>
    {render_report_theme()}
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
    .intro p,
    .table-head p,
    .notes li {{
      color: var(--muted);
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      margin-top: 16px;
      color: var(--muted);
      font-size: 13px;
    }}
    .gate-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .gate-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.68);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.03em;
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
    .summary-box,
    .table-panel,
    .notes {{
      padding: 20px;
    }}
    .summary-box h2,
    .table-head h2,
    .notes h2 {{
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    .summary-box p,
    .notes p {{
      margin: 0;
      line-height: 1.7;
      color: var(--muted);
    }}
    .table-panel {{
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
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 880px;
      font-size: 14px;
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
    .notes ul {{
      margin: 0;
      padding-left: 18px;
      line-height: 1.7;
    }}
    @media (max-width: 900px) {{
      body {{ padding: 14px; }}
      .hero,
      .summary-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    {render_hero_section(
        "SIA Factor<br>Breakdown",
        "이 리포트는 strict non-mock 기준으로 정렬된 스냅샷만 사용해 factor score와 미래 수익률의 관계를 분해합니다. 즉, 현재 factor가 실제로 방향성을 만드는지 먼저 보려는 리서치 뷰입니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"스냅샷 구간: {fmt_ts(first_ts)} ~ {fmt_ts(last_ts)}",
            f"Aligned sources: {esc(aligned_sources)}",
        ]),
        render_stats_panel([
            ("Snapshots", str(int(diagnostics['total_snapshots']))),
            ("Strict Aligned", str(int(diagnostics['aligned_snapshots']))),
            ("Samples", str(len(samples))),
            ("Mock Filtered", str(int(diagnostics['filtered_mock_only']))),
        ]),
        extra_html=render_gate_strip(regime_chip_html),
    )}

    <section class="summary-grid">
      {render_summary_panel("현재 가장 강한 조합", f"<p>{esc(best_text)}</p>")}
      {render_summary_panel("해석 기준", "<p><code>avg edge</code>는 factor score 방향과 미래 수익률 방향이 얼마나 맞았는지 봅니다. 양수 score면 상승, 음수 score면 하락이 맞을수록 edge가 좋아집니다.</p><p class='label'>현재 factor 해석은 위 <code>SIA_CONFIRM_*</code>, <code>SIA_REGIME_*</code> 파라미터로 생성된 신호 기준입니다.</p>")}
    </section>

    {render_table_section(
        "Factor 요약",
        "factor별 horizon 성능 요약",
        ["Factor", "Horizon", "Samples", "Avg Score", "Avg Return", "Avg Edge", "Directional Hit", "Corr"],
        summary_html,
    )}

    {render_table_section(
        "Bucket 분해",
        "factor score 구간별 미래 수익률과 방향 적중도",
        ["Factor", "Horizon", "Bucket", "Samples", "Avg Score", "Avg Return", "Avg Edge", "Hit Rate"],
        bucket_html,
    )}

    {render_notes_section(
        "메모",
        "<li>strict 정렬 기준은 가격/포지션 백테스트와 동일합니다. source가 맞고, <code>mock</code>은 제외됩니다.</li><li>표본이 적으면 corr와 hit rate는 쉽게 흔들립니다. readiness 리포트를 같이 보는 게 맞습니다.</li><li>이 리포트는 factor 품질 진단용입니다. 전략 수익률 리포트와 역할이 다릅니다.</li>",
    )}
  </main>
</body>
</html>"""


def load_report_inputs(db_path: Path) -> FactorReportInputs:
    return FactorReportInputs(
        snapshots=load_factor_snapshots(db_path),
        price_series=price_report.load_price_series(db_path),
    )


def summarize_report(inputs: FactorReportInputs) -> FactorReportSummary:
    samples, diagnostics = align_samples(inputs.snapshots, inputs.price_series)
    summary_rows, bucket_rows = build_factor_summaries(samples) if samples else ([], [])
    return FactorReportSummary(
        samples=samples,
        diagnostics=diagnostics,
        summary_rows=summary_rows,
        bucket_rows=bucket_rows,
    )


def render_report(db_path: Path, inputs: FactorReportInputs, summary: FactorReportSummary) -> str:
    return localize_output_html(
        render_html(
            db_path,
            inputs.snapshots,
            summary.samples,
            summary.diagnostics,
            summary.summary_rows,
            summary.bucket_rows,
        )
    )


def write_report(db_path: Path, output_path: Path) -> Path:
    inputs = load_report_inputs(db_path)
    if not inputs.snapshots:
        output_path.write_text(build_empty_html("dashboard_snapshots가 없습니다. notifier를 먼저 실행하세요."), encoding="utf-8")
        return output_path

    summary = summarize_report(inputs)
    if not summary.samples:
        output_path.write_text(
            build_empty_html(
                "strict non-mock factor sample이 아직 없습니다. live/non-mock snapshot과 후속 price tick을 더 쌓아야 합니다."
            ),
            encoding="utf-8",
        )
        return output_path

    output_path.write_text(render_report(db_path, inputs, summary), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate factor breakdown report from local sqlite data.")
    parser.add_argument("--db-path", required=True, help="Path to trading_signal_notifier sqlite db")
    parser.add_argument("--output", required=True, help="HTML output path")
    args = parser.parse_args()

    db_path = Path(args.db_path).expanduser()
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_report(db_path, output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
