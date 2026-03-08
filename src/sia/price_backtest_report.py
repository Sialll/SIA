from __future__ import annotations

import argparse
import html
import math
import sqlite3
from bisect import bisect_right
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    from .presentation import signal_set_display as presentation_signal_set_display
    from .report_common import localize_report_html, render_empty_report_html
    from .report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts, stddev
    from .report_theme import render_report_theme
    from .report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section
except ImportError:
    from presentation import signal_set_display as presentation_signal_set_display  # type: ignore
    from report_common import localize_report_html, render_empty_report_html  # type: ignore
    from report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts, stddev  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section  # type: ignore


@dataclass(frozen=True)
class SignalSnapshot:
    ts: int
    ticker: str
    signal: str
    confidence: float
    entry_price: float
    composite_score: float
    risk_level: str
    macro_environment: str
    signal_source: str | None = None


@dataclass(frozen=True)
class PricePoint:
    ts: int
    close: float


@dataclass(frozen=True)
class BacktestSample:
    ticker: str
    signal: str
    entry_ts: int
    exit_ts: int
    horizon: int
    entry_price: float
    exit_price: float
    forward_return: float
    signal_edge: float
    hit: bool
    max_favorable_move: float
    max_adverse_move: float
    composite_score: float
    confidence: float
    risk_level: str
    macro_environment: str


@dataclass(frozen=True)
class AlignmentResult:
    status: str
    source: str | None = None
    entry_index: int | None = None
    matched_ts: int | None = None
    matched_price: float | None = None
    price_gap: float | None = None


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

ENTRY_MATCH_TOLERANCE = 0.08
ENTRY_MATCH_WINDOW_SECONDS = 60 * 30
ENTRY_MATCH_FALLBACK_WINDOW_SECONDS = 60 * 60 * 24
STRICT_EXCLUDED_SOURCES = {"mock"}


@dataclass(frozen=True)
class PriceBacktestInputs:
    signals: list[SignalSnapshot]
    price_series: dict[str, dict[str, list[PricePoint]]]
    horizons: list[int]


@dataclass(frozen=True)
class PriceBacktestSummary:
    samples: list[BacktestSample]
    coverage: list[dict[str, object]]
    diagnostics: dict[str, object]


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
    return render_empty_report_html("SIA 가격 백테스트", message)


def localize_output_html(text: str) -> str:
    return localize_report_html(
        text,
        [
            ("SIA Price<br>Backtest", "SIA 가격<br>백테스트"),
            ("Max Favorable", "최대 유리 움직임"),
            ("Max Adverse", "최대 불리 움직임"),
        ],
    )


def load_signals(db_path: Path) -> list[SignalSnapshot]:
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
                    ts, ticker, signal, confidence, price,
                    composite_score, risk_level, macro_environment, signal_source
                FROM dashboard_snapshots
                WHERE signal IN ('BUY', 'SELL')
                ORDER BY ticker ASC, ts ASC, id ASC
                """
                if has_signal_source
                else
                """
                SELECT
                    ts, ticker, signal, confidence, price,
                    composite_score, risk_level, macro_environment, NULL AS signal_source
                FROM dashboard_snapshots
                WHERE signal IN ('BUY', 'SELL')
                ORDER BY ticker ASC, ts ASC, id ASC
                """
            )
        ).fetchall()

    return [
        SignalSnapshot(
            ts=int(row[0]),
            ticker=str(row[1]),
            signal=str(row[2]),
            confidence=float(row[3]),
            entry_price=float(row[4]),
            composite_score=float(row[5]),
            risk_level=str(row[6]),
            macro_environment=str(row[7]),
            signal_source=str(row[8]) if row[8] not in (None, "") else None,
        )
        for row in rows
        if row[4] not in (None, 0)
    ]


def load_price_series(db_path: Path) -> dict[str, dict[str, list[PricePoint]]]:
    with sqlite3.connect(str(db_path)) as conn:
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='price_ticks'"
        ).fetchone()
        if table_exists is None:
            return {}
        rows = conn.execute(
            """
            SELECT ticker, source, ts, AVG(close) AS close
            FROM price_ticks
            GROUP BY ticker, source, ts
            ORDER BY ticker ASC, source ASC, ts ASC
            """
        ).fetchall()

    by_ticker: dict[str, dict[str, list[PricePoint]]] = defaultdict(lambda: defaultdict(list))
    for ticker, source, ts, close in rows:
        if close in (None, 0):
            continue
        by_ticker[str(ticker)][str(source)].append(PricePoint(ts=int(ts), close=float(close)))
    return {ticker: dict(source_map) for ticker, source_map in by_ticker.items()}


def _find_entry_match(signal: SignalSnapshot, series: list[PricePoint]) -> tuple[int, int, float, float] | None:
    if not series:
        return None
    ts_values = [point.ts for point in series]
    insert_at = bisect_right(ts_values, signal.ts)
    candidate_indices = [index for index in {insert_at - 1} if 0 <= index < len(series)]
    best_match: tuple[int, int, float, float] | None = None
    for index in candidate_indices:
        point = series[index]
        if abs(point.ts - signal.ts) > ENTRY_MATCH_WINDOW_SECONDS:
            continue
        if signal.entry_price <= 0:
            continue
        gap = abs(point.close / signal.entry_price - 1.0)
        if gap > ENTRY_MATCH_TOLERANCE:
            continue
        candidate = (index, point.ts, point.close, gap)
        if best_match is None or candidate[3] < best_match[3]:
            best_match = candidate
    if best_match is not None:
        return best_match
    fallback_best: tuple[float, int, int, int, float] | None = None
    for index in range(insert_at - 1, -1, -1):
        point = series[index]
        age = signal.ts - point.ts
        if age < 0:
            continue
        if age > ENTRY_MATCH_FALLBACK_WINDOW_SECONDS:
            break
        if signal.entry_price <= 0:
            continue
        gap = abs(point.close / signal.entry_price - 1.0)
        if gap > ENTRY_MATCH_TOLERANCE:
            continue
        candidate = (gap, age, index, point.ts, point.close)
        if fallback_best is None or candidate < fallback_best:
            fallback_best = candidate
    if fallback_best is not None:
        _, _, index, point_ts, point_close = fallback_best
        return (index, point_ts, point_close, fallback_best[0])
    return best_match


def align_signal_to_series(
    signal: SignalSnapshot,
    ticker_sources: dict[str, list[PricePoint]],
) -> AlignmentResult:
    if not ticker_sources:
        return AlignmentResult(status="no_price_series")
    if signal.signal_source:
        source_name = signal.signal_source
        if source_name in STRICT_EXCLUDED_SOURCES:
            return AlignmentResult(status="mock_only", source=source_name)
        series = ticker_sources.get(source_name, [])
        match = _find_entry_match(signal, series)
        if match is None:
            return AlignmentResult(status="source_mismatch", source=source_name)
        entry_index, matched_ts, matched_price, gap = match
        return AlignmentResult(
            status="aligned",
            source=source_name,
            entry_index=entry_index,
            matched_ts=matched_ts,
            matched_price=matched_price,
            price_gap=gap,
        )

    strict_candidates: list[tuple[str, int, int, float, float]] = []
    mock_candidates: list[tuple[str, int, int, float, float]] = []

    for source, series in ticker_sources.items():
        match = _find_entry_match(signal, series)
        if match is None:
            continue
        entry_index, matched_ts, matched_price, gap = match
        item = (source, entry_index, matched_ts, matched_price, gap)
        if source in STRICT_EXCLUDED_SOURCES:
            mock_candidates.append(item)
        else:
            strict_candidates.append(item)

    if strict_candidates:
        source, entry_index, matched_ts, matched_price, gap = min(strict_candidates, key=lambda item: item[4])
        return AlignmentResult(
            status="aligned",
            source=source,
            entry_index=entry_index,
            matched_ts=matched_ts,
            matched_price=matched_price,
            price_gap=gap,
        )
    if mock_candidates:
        source, entry_index, matched_ts, matched_price, gap = min(mock_candidates, key=lambda item: item[4])
        return AlignmentResult(
            status="mock_only",
            source=source,
            entry_index=entry_index,
            matched_ts=matched_ts,
            matched_price=matched_price,
            price_gap=gap,
        )
    return AlignmentResult(status="source_mismatch")


def build_samples(
    signals: list[SignalSnapshot],
    price_series: dict[str, dict[str, list[PricePoint]]],
    horizons: list[int],
) -> tuple[list[BacktestSample], list[dict[str, int]], dict[str, object]]:
    samples: list[BacktestSample] = []
    coverage: list[dict[str, int]] = []
    diagnostics: dict[str, object] = {
        "total_signals": len(signals),
        "aligned_signals": 0,
        "filtered_mock_only": 0,
        "filtered_source_mismatch": 0,
        "aligned_sources": {},
    }
    aligned_signals: list[tuple[SignalSnapshot, AlignmentResult]] = []

    for signal in signals:
        alignment = align_signal_to_series(signal, price_series.get(signal.ticker, {}))
        if alignment.status == "aligned":
            aligned_signals.append((signal, alignment))
            diagnostics["aligned_signals"] = int(diagnostics["aligned_signals"]) + 1
            aligned_sources = dict(diagnostics["aligned_sources"])
            aligned_sources[alignment.source or "unknown"] = aligned_sources.get(alignment.source or "unknown", 0) + 1
            diagnostics["aligned_sources"] = aligned_sources
        elif alignment.status == "mock_only":
            diagnostics["filtered_mock_only"] = int(diagnostics["filtered_mock_only"]) + 1
        else:
            diagnostics["filtered_source_mismatch"] = int(diagnostics["filtered_source_mismatch"]) + 1

    for horizon in horizons:
        eligible = len(aligned_signals)
        produced = 0
        for signal, alignment in aligned_signals:
            if alignment.source is None or alignment.entry_index is None:
                continue
            series = price_series.get(signal.ticker, {}).get(alignment.source, [])
            start_index = alignment.entry_index + 1
            exit_index = start_index + horizon - 1
            if start_index >= len(series) or exit_index >= len(series):
                continue

            path = series[start_index : exit_index + 1]
            if not path:
                continue
            exit_point = path[-1]
            forward_return = (exit_point.close / signal.entry_price) - 1.0

            if signal.signal == "BUY":
                signal_edge = forward_return
                hit = forward_return > 0
                max_favorable_move = max(0.0, (max(point.close for point in path) / signal.entry_price) - 1.0)
                max_adverse_move = max(0.0, 1.0 - (min(point.close for point in path) / signal.entry_price))
            else:
                signal_edge = -forward_return
                hit = forward_return < 0
                max_favorable_move = max(0.0, 1.0 - (min(point.close for point in path) / signal.entry_price))
                max_adverse_move = max(0.0, (max(point.close for point in path) / signal.entry_price) - 1.0)

            samples.append(
                BacktestSample(
                    ticker=signal.ticker,
                    signal=signal.signal,
                    entry_ts=signal.ts,
                    exit_ts=exit_point.ts,
                    horizon=horizon,
                    entry_price=signal.entry_price,
                    exit_price=exit_point.close,
                    forward_return=forward_return,
                    signal_edge=signal_edge,
                    hit=hit,
                    max_favorable_move=max_favorable_move,
                    max_adverse_move=max_adverse_move,
                    composite_score=signal.composite_score,
                    confidence=signal.confidence,
                    risk_level=signal.risk_level,
                    macro_environment=signal.macro_environment,
                )
            )
            produced += 1

        coverage.append({"horizon": horizon, "eligible": eligible, "produced": produced})

    return samples, coverage, diagnostics


def summarize_by_signal(samples: list[BacktestSample], horizons: list[int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        horizon_samples = [item for item in samples if item.horizon == horizon]
        for signal in ("BUY", "SELL"):
            filtered = [item for item in horizon_samples if item.signal == signal]
            if not filtered:
                continue
            rows.append(
                {
                    "horizon": horizon,
                    "signal": signal,
                    "samples": len(filtered),
                    "avg_signal_edge": avg([item.signal_edge for item in filtered]),
                    "hit_rate": avg([1.0 if item.hit else 0.0 for item in filtered]),
                    "avg_adverse": avg([item.max_adverse_move for item in filtered]),
                    "avg_favorable": avg([item.max_favorable_move for item in filtered]),
                }
            )
    return rows


def summarize_portfolio_metrics(samples: list[BacktestSample], horizons: list[int]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon in horizons:
        horizon_samples = [item for item in samples if item.horizon == horizon]
        for label, filtered in (
            ("ALL", horizon_samples),
            ("BUY", [item for item in horizon_samples if item.signal == "BUY"]),
            ("SELL", [item for item in horizon_samples if item.signal == "SELL"]),
        ):
            if not filtered:
                continue
            ordered = sorted(filtered, key=lambda item: (item.entry_ts, item.exit_ts, item.ticker, item.signal))
            returns = [item.signal_edge for item in ordered]
            equity = 1.0
            peak = 1.0
            max_drawdown = 0.0
            for trade_return in returns:
                equity *= 1.0 + trade_return
                peak = max(peak, equity)
                if peak > 0:
                    max_drawdown = max(max_drawdown, 1.0 - (equity / peak))
            sample_std = stddev(returns)
            mean_return = avg(returns)
            sharpe = None
            if sample_std is not None and sample_std > 0 and mean_return is not None:
                sharpe = (mean_return / sample_std) * math.sqrt(len(returns))
            rows.append(
                {
                    "horizon": horizon,
                    "signal": label,
                    "samples": len(filtered),
                    "avg_trade_return": mean_return,
                    "cumulative_return": equity - 1.0,
                    "max_drawdown": max_drawdown,
                    "sharpe": sharpe,
                }
            )
    return rows


def summarize_by_bucket(samples: list[BacktestSample], horizons: list[int]) -> list[dict[str, object]]:
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
                    "avg_signal_edge": avg([item.signal_edge for item in filtered]),
                    "avg_confidence": avg([item.confidence for item in filtered]),
                    "avg_adverse": avg([item.max_adverse_move for item in filtered]),
                }
            )
    return rows


def summarize_leaderboard(samples: list[BacktestSample], horizon: int) -> list[dict[str, object]]:
    filtered = [item for item in samples if item.horizon == horizon]
    by_ticker: dict[str, list[BacktestSample]] = defaultdict(list)
    for item in filtered:
        by_ticker[item.ticker].append(item)

    rows: list[dict[str, object]] = []
    for ticker, series in by_ticker.items():
        rows.append(
            {
                "ticker": ticker,
                "samples": len(series),
                "avg_signal_edge": avg([item.signal_edge for item in series]),
                "hit_rate": avg([1.0 if item.hit else 0.0 for item in series]),
                "avg_adverse": avg([item.max_adverse_move for item in series]),
            }
        )
    rows.sort(key=lambda item: (item["avg_signal_edge"] is not None, item["avg_signal_edge"]), reverse=True)
    return rows


def render_html(
    db_path: Path,
    signals: list[SignalSnapshot],
    price_series: dict[str, dict[str, list[PricePoint]]],
    samples: list[BacktestSample],
    coverage: list[dict[str, int]],
    diagnostics: dict[str, object],
    horizons: list[int],
) -> str:
    if not signals:
        return build_empty_html("BUY/SELL 신호가 없습니다. notifier가 더 실행되어야 합니다.")
    if not price_series:
        return build_empty_html("price_ticks 데이터가 없습니다. 가격 수집이 먼저 필요합니다.")
    if not samples:
        return build_empty_html(
            "strict source filter 이후 usable sample이 없습니다. "
            f"전체 신호 {diagnostics['total_signals']}개, "
            f"aligned {diagnostics['aligned_signals']}개, "
            f"mock-only 제외 {diagnostics['filtered_mock_only']}개, "
            f"source mismatch {diagnostics['filtered_source_mismatch']}개."
        )

    signal_summary = summarize_by_signal(samples, horizons)
    portfolio_summary = summarize_portfolio_metrics(samples, horizons)
    bucket_summary = summarize_by_bucket(samples, horizons)
    leaderboard = summarize_leaderboard(samples, 3 if 3 in horizons else horizons[0])

    unique_tickers = len({item.ticker for item in signals})
    total_price_ticks = sum(len(points) for source_map in price_series.values() for points in source_map.values())
    total_samples = len(samples)
    first_signal_ts = fmt_ts(min(item.ts for item in signals))
    last_signal_ts = fmt_ts(max(item.ts for item in signals))
    aligned_sources = ", ".join(
        f"{source}:{count}" for source, count in sorted(dict(diagnostics["aligned_sources"]).items())
    ) or "없음"

    signal_rows_html = []
    for row in signal_summary:
        signal_rows_html.append(
            f"""
            <tr>
              <td>+{row['horizon']} price tick</td>
              <td>{esc(row['signal'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_signal_edge'])}</td>
              <td>{fmt_pct(row['hit_rate'])}</td>
              <td>{fmt_pct(row['avg_favorable'])}</td>
              <td>{fmt_pct(row['avg_adverse'])}</td>
            </tr>
            """
        )

    portfolio_rows_html = []
    for row in portfolio_summary:
        portfolio_rows_html.append(
            f"""
            <tr>
              <td>+{row['horizon']} price tick</td>
              <td>{esc(row['signal'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_trade_return'])}</td>
              <td>{fmt_pct(row['cumulative_return'])}</td>
              <td>{fmt_pct(row['max_drawdown'])}</td>
              <td>{fmt_num(row['sharpe'])}</td>
            </tr>
            """
        )

    coverage_rows_html = []
    for row in coverage:
        coverage_rate = (row["produced"] / row["eligible"]) if row["eligible"] else None
        coverage_rows_html.append(
            f"""
            <tr>
              <td>+{row['horizon']} price tick</td>
              <td>{row['eligible']}</td>
              <td>{row['produced']}</td>
              <td>{fmt_pct(coverage_rate)}</td>
            </tr>
            """
        )

    bucket_rows_html = []
    for row in bucket_summary:
        bucket_rows_html.append(
            f"""
            <tr>
              <td>+{row['horizon']} price tick</td>
              <td>{esc(row['bucket'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_signal_edge'])}</td>
              <td>{fmt_score(row['avg_confidence'])}</td>
              <td>{fmt_pct(row['avg_adverse'])}</td>
            </tr>
            """
        )

    leaderboard_rows_html = []
    for row in leaderboard[:12]:
        leaderboard_rows_html.append(
            f"""
            <tr>
              <td>{esc(row['ticker'])}</td>
              <td>{row['samples']}</td>
              <td>{fmt_pct(row['avg_signal_edge'])}</td>
              <td>{fmt_pct(row['hit_rate'])}</td>
              <td>{fmt_pct(row['avg_adverse'])}</td>
            </tr>
            """
        )

    best_signal_row = max(
        signal_summary,
        key=lambda row: (row["avg_signal_edge"] is not None, row["avg_signal_edge"]),
    )
    best_portfolio_row = max(
        portfolio_summary,
        key=lambda row: (
            row["sharpe"] is not None,
            row["sharpe"] if row["sharpe"] is not None else float("-inf"),
            row["cumulative_return"] if row["cumulative_return"] is not None else float("-inf"),
        ),
    )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 가격 백테스트</title>
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
        "SIA Price<br>Backtest",
        "이 리포트는 <code>dashboard_snapshots</code>의 BUY/SELL 신호를 기준으로, 이후 <code>price_ticks</code>에서 실제로 저장된 다음 가격 흐름을 사용해 신호 성능을 계산합니다. 즉, snapshot 간격이 아니라 독립 가격 tick 기준입니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"신호 구간: {esc(first_signal_ts)} ~ {esc(last_signal_ts)}",
            f"Horizon: {esc(', '.join(str(item) for item in horizons))}",
            f"Aligned sources: {esc(aligned_sources)}",
        ]),
        render_stats_panel([
            ("Signals", str(len(signals))),
            ("Aligned", str(diagnostics['aligned_signals'])),
            ("Mock Filtered", str(diagnostics['filtered_mock_only'])),
            ("Samples", str(total_samples)),
        ]),
    )}

    <section class="summary-grid">
      {render_summary_panel("핵심 해석", "<p><span class='accent-buy'>Signal Edge</span>는 BUY면 미래 상승률, SELL이면 미래 하락률을 기준으로 계산합니다. 이 리포트는 `signal entry price`와 같은 source의 entry tick이 허용오차 8% 안에서 맞는 경우만 사용하고, <code>mock</code> source는 strict 백테스트에서 제외합니다.</p>")}
      {render_summary_panel("현재 가장 나은 조합", f"<p>{esc(presentation_signal_set_display(best_portfolio_row['signal']))} / +{best_portfolio_row['horizon']} price tick / 누적수익률 {fmt_pct(best_portfolio_row['cumulative_return'])} / Sharpe {fmt_num(best_portfolio_row['sharpe'])}</p>")}
    </section>

    <section class="panel table-panel">
      <div class="table-head">
        <h2>포트폴리오 메트릭</h2>
        <p>trade sequence를 시간순으로 연결한 누적수익률 / MDD / sample Sharpe</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>Horizon</th>
            <th>Signal Set</th>
            <th>Samples</th>
            <th>평균 Trade Return</th>
            <th>누적수익률</th>
            <th>MDD</th>
            <th>Sharpe</th>
          </tr>
        </thead>
        <tbody>
          {''.join(portfolio_rows_html)}
        </tbody>
      </table>
    </section>

    <section class="panel table-panel">
      <div class="table-head">
        <h2>신호별 가격 기반 성과</h2>
        <p>미래 방향 적중, 유리한 최대 움직임, 불리한 최대 움직임</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>Horizon</th>
            <th>Signal</th>
            <th>Samples</th>
            <th>평균 시그널 엣지</th>
            <th>적중률</th>
            <th>평균 Max Favorable</th>
            <th>평균 Max Adverse</th>
          </tr>
        </thead>
        <tbody>
          {''.join(signal_rows_html)}
        </tbody>
      </table>
    </section>

    <section class="panel table-panel">
      <div class="table-head">
        <h2>Horizon 커버리지</h2>
        <p>신호는 있었지만 미래 price tick이 부족해 평가하지 못한 비율 확인</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>Horizon</th>
            <th>Eligible Signals</th>
            <th>Backtested Samples</th>
            <th>Coverage</th>
          </tr>
        </thead>
        <tbody>
          {''.join(coverage_rows_html)}
        </tbody>
      </table>
    </section>

    {render_table_section(
        "점수 구간별 가격 기반 성과",
        "Composite Score 구간이 실제 가격 흐름에서 얼마나 유효했는지 점검",
        ["Horizon", "Bucket", "Samples", "평균 시그널 엣지", "평균 신뢰도", "평균 Max Adverse"],
        ''.join(bucket_rows_html),
    )}

    {render_table_section(
        "티커 리더보드",
        esc(f"+{3 if 3 in horizons else horizons[0]} price tick 기준"),
        ["Ticker", "Samples", "평균 시그널 엣지", "적중률", "평균 Max Adverse"],
        ''.join(leaderboard_rows_html),
    )}

    {render_footnote_section(
        "방법론 메모",
        f"1. 이 리포트는 외부 API 재조회 없이 현재 DB만 사용합니다.<br>2. strict 기준: entry price와 같은 source의 price tick이 허용오차 8% 안에서 맞아야 하며, <code>mock</code> source는 제외합니다.<br>3. Horizon `+3 price tick`은 진입 tick 이후 같은 티커의 세 번째 가격 기록입니다.<br>4. 누적수익률 / MDD / Sharpe는 `sample trade sequence`를 시간순으로 단순 연결한 값이며, 실제 포트폴리오 체결/중복 포지션 모델은 아닙니다.<br>5. 총 ticker 수는 {unique_tickers}, 총 stored price tick 수는 {total_price_ticks}, source mismatch 필터 수는 {diagnostics['filtered_source_mismatch']} 입니다.<br>6. 데이터가 적을 때는 결과보다 표본 수와 coverage부터 보는 편이 맞습니다.<br>7. 현재 가장 나은 단일 신호 기준은 {esc(best_signal_row['signal'])} / +{best_signal_row['horizon']} price tick / 평균 시그널 엣지 {fmt_pct(best_signal_row['avg_signal_edge'])} 입니다.",
    )}
  </main>
</body>
</html>"""


def load_report_inputs(db_path: Path, horizons: list[int]) -> PriceBacktestInputs:
    return PriceBacktestInputs(
        signals=load_signals(db_path),
        price_series=load_price_series(db_path),
        horizons=horizons,
    )


def summarize_report(inputs: PriceBacktestInputs) -> PriceBacktestSummary:
    samples, coverage, diagnostics = build_samples(inputs.signals, inputs.price_series, inputs.horizons)
    return PriceBacktestSummary(samples=samples, coverage=coverage, diagnostics=diagnostics)


def render_report(db_path: Path, inputs: PriceBacktestInputs, summary: PriceBacktestSummary) -> str:
    return localize_output_html(
        render_html(
            db_path,
            inputs.signals,
            inputs.price_series,
            summary.samples,
            summary.coverage,
            summary.diagnostics,
            inputs.horizons,
        )
    )


def write_report(db_path: Path, output_path: Path, horizons: list[int]) -> Path:
    inputs = load_report_inputs(db_path, horizons)
    summary = summarize_report(inputs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(db_path, inputs, summary), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate stricter price-based backtest report from local sqlite data.")
    parser.add_argument("--db-path", required=True, help="Path to trading_signal_notifier sqlite db")
    parser.add_argument("--output", required=True, help="HTML output path")
    parser.add_argument("--horizons", default="1,3,5,10", help="Comma-separated future price tick horizons")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser()
    output_path = Path(args.output).expanduser()
    horizons = [int(item.strip()) for item in args.horizons.split(",") if item.strip()]
    if not horizons:
        horizons = [1, 3, 5, 10]
    write_report(db_path, output_path, horizons)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
