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
    from .backtest_horizons import DEFAULT_POSITION_HORIZONS, BacktestHorizon, parse_horizon_specs, resolve_exit_index
    from .presentation import signal_set_display as presentation_signal_set_display
    from .report_common import localize_report_html, render_empty_report_html
    from .report_metrics import avg, fmt_num, fmt_pct, fmt_score, fmt_ts, stddev
    from .report_theme import render_report_theme
    from .report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section
except ImportError:
    from backtest_horizons import DEFAULT_POSITION_HORIZONS, BacktestHorizon, parse_horizon_specs, resolve_exit_index  # type: ignore
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
class Trade:
    ticker: str
    signal: str
    entry_ts: int
    exit_ts: int
    hold_key: str
    hold_label: str
    hold_ticks: int
    entry_price: float
    exit_price: float
    strategy_return: float
    raw_return: float
    hit: bool
    max_favorable_move: float
    max_adverse_move: float
    confidence: float
    composite_score: float
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


ENTRY_MATCH_TOLERANCE = 0.08
ENTRY_MATCH_WINDOW_SECONDS = 60 * 30
ENTRY_MATCH_FALLBACK_WINDOW_SECONDS = 60 * 60 * 24
STRICT_EXCLUDED_SOURCES = {"mock"}


@dataclass(frozen=True)
class PositionBacktestInputs:
    signals: list[SignalSnapshot]
    price_series: dict[str, dict[str, list[PricePoint]]]
    primary_hold: BacktestHorizon
    holds: list[BacktestHorizon]


@dataclass(frozen=True)
class PositionBacktestSummary:
    primary_trades: list[Trade]
    primary_diagnostics: dict[str, object]
    comparison_rows: list[dict[str, object]]


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 포지션 백테스트", message)


def localize_output_html(text: str) -> str:
    return localize_report_html(
        text,
        [
            ("SIA Position<br>Backtest", "SIA 포지션<br>백테스트"),
            ("Strategy Return", "전략 수익률"),
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
                ORDER BY ts ASC, ticker ASC, id ASC
                """
                if has_signal_source
                else
                """
                SELECT
                    ts, ticker, signal, confidence, price,
                    composite_score, risk_level, macro_environment, NULL AS signal_source
                FROM dashboard_snapshots
                WHERE signal IN ('BUY', 'SELL')
                ORDER BY ts ASC, ticker ASC, id ASC
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


def simulate_trades(
    signals: list[SignalSnapshot],
    price_series: dict[str, dict[str, list[PricePoint]]],
    hold: BacktestHorizon,
) -> tuple[list[Trade], dict[str, object]]:
    trades: list[Trade] = []
    active_until_by_ticker: dict[str, int] = {}
    diagnostics: dict[str, object] = {
        "total_signals": len(signals),
        "aligned_signals": 0,
        "filtered_mock_only": 0,
        "filtered_source_mismatch": 0,
        "skipped_overlap": 0,
        "aligned_sources": {},
    }

    for signal in signals:
        alignment = align_signal_to_series(signal, price_series.get(signal.ticker, {}))
        if alignment.status == "mock_only":
            diagnostics["filtered_mock_only"] = int(diagnostics["filtered_mock_only"]) + 1
            continue
        if alignment.status != "aligned" or alignment.source is None or alignment.entry_index is None:
            diagnostics["filtered_source_mismatch"] = int(diagnostics["filtered_source_mismatch"]) + 1
            continue

        diagnostics["aligned_signals"] = int(diagnostics["aligned_signals"]) + 1
        aligned_sources = dict(diagnostics["aligned_sources"])
        aligned_sources[alignment.source] = aligned_sources.get(alignment.source, 0) + 1
        diagnostics["aligned_sources"] = aligned_sources

        if active_until_by_ticker.get(signal.ticker, -1) > signal.ts:
            diagnostics["skipped_overlap"] = int(diagnostics["skipped_overlap"]) + 1
            continue

        series = price_series.get(signal.ticker, {}).get(alignment.source, [])
        exit_index = resolve_exit_index(
            series,
            alignment.entry_index,
            alignment.matched_ts or signal.ts,
            hold,
        )
        if exit_index is None:
            continue

        start_index = alignment.entry_index + 1
        path = series[start_index : exit_index + 1]
        if not path:
            continue
        exit_point = path[-1]
        raw_return = (exit_point.close / signal.entry_price) - 1.0

        if signal.signal == "BUY":
            strategy_return = raw_return
            hit = raw_return > 0
            max_favorable_move = max(0.0, (max(point.close for point in path) / signal.entry_price) - 1.0)
            max_adverse_move = max(0.0, 1.0 - (min(point.close for point in path) / signal.entry_price))
        else:
            strategy_return = -raw_return
            hit = raw_return < 0
            max_favorable_move = max(0.0, 1.0 - (min(point.close for point in path) / signal.entry_price))
            max_adverse_move = max(0.0, (max(point.close for point in path) / signal.entry_price) - 1.0)

        active_until_by_ticker[signal.ticker] = exit_point.ts
        trades.append(
            Trade(
                ticker=signal.ticker,
                signal=signal.signal,
                entry_ts=signal.ts,
                exit_ts=exit_point.ts,
                hold_key=hold.key,
                hold_label=hold.label,
                hold_ticks=len(path),
                entry_price=signal.entry_price,
                exit_price=exit_point.close,
                strategy_return=strategy_return,
                raw_return=raw_return,
                hit=hit,
                max_favorable_move=max_favorable_move,
                max_adverse_move=max_adverse_move,
                confidence=signal.confidence,
                composite_score=signal.composite_score,
                risk_level=signal.risk_level,
                macro_environment=signal.macro_environment,
            )
        )

    return trades, diagnostics


def compute_path_metrics(trades: list[Trade]) -> dict[str, float | None]:
    if not trades:
        return {
            "avg_trade_return": None,
            "cumulative_return": None,
            "max_drawdown": None,
            "sharpe": None,
            "win_rate": None,
        }
    ordered = sorted(trades, key=lambda item: (item.exit_ts, item.entry_ts, item.ticker))
    returns = [item.strategy_return for item in ordered]
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for trade_return in returns:
        equity *= 1.0 + trade_return
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = max(max_drawdown, 1.0 - (equity / peak))
    mean_return = avg(returns)
    sample_std = stddev(returns)
    sharpe = None
    if sample_std is not None and sample_std > 0 and mean_return is not None:
        sharpe = (mean_return / sample_std) * math.sqrt(len(returns))
    return {
        "avg_trade_return": mean_return,
        "cumulative_return": equity - 1.0,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "win_rate": avg([1.0 if item.hit else 0.0 for item in ordered]),
    }


def summarize_trade_sets(trades: list[Trade], hold: BacktestHorizon) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for label, filtered in (
        ("ALL", trades),
        ("BUY", [item for item in trades if item.signal == "BUY"]),
        ("SELL", [item for item in trades if item.signal == "SELL"]),
    ):
        if not filtered:
            continue
        metrics = compute_path_metrics(filtered)
        rows.append(
            {
                "hold_key": hold.key,
                "hold_label": hold.label,
                "signal_set": label,
                "trades": len(filtered),
                "avg_trade_return": metrics["avg_trade_return"],
                "cumulative_return": metrics["cumulative_return"],
                "max_drawdown": metrics["max_drawdown"],
                "sharpe": metrics["sharpe"],
                "win_rate": metrics["win_rate"],
                "avg_hold_ticks": avg([float(item.hold_ticks) for item in filtered]),
            }
        )
    return rows


def summarize_tickers(trades: list[Trade]) -> list[dict[str, object]]:
    by_ticker: dict[str, list[Trade]] = defaultdict(list)
    for item in trades:
        by_ticker[item.ticker].append(item)

    rows: list[dict[str, object]] = []
    for ticker, series in by_ticker.items():
        metrics = compute_path_metrics(series)
        rows.append(
            {
                "ticker": ticker,
                "trades": len(series),
                "avg_trade_return": metrics["avg_trade_return"],
                "cumulative_return": metrics["cumulative_return"],
                "win_rate": metrics["win_rate"],
                "max_drawdown": metrics["max_drawdown"],
            }
        )
    rows.sort(key=lambda item: (item["cumulative_return"] is not None, item["cumulative_return"]), reverse=True)
    return rows


def render_html(
    db_path: Path,
    primary_hold: BacktestHorizon,
    signals: list[SignalSnapshot],
    price_series: dict[str, dict[str, list[PricePoint]]],
    trades: list[Trade],
    diagnostics: dict[str, object],
    comparison_rows: list[dict[str, object]],
) -> str:
    if not signals:
        return build_empty_html("BUY/SELL 신호가 없습니다. notifier가 더 실행되어야 합니다.")
    if not price_series:
        return build_empty_html("price_ticks 데이터가 없습니다. 가격 수집이 먼저 필요합니다.")
    if not trades:
        return build_empty_html(
            "strict position backtest 대상 trade가 없습니다. "
            f"전체 신호 {diagnostics['total_signals']}개, "
            f"aligned {diagnostics['aligned_signals']}개, "
            f"mock-only 제외 {diagnostics['filtered_mock_only']}개, "
            f"source mismatch {diagnostics['filtered_source_mismatch']}개, "
            f"overlap skip {diagnostics['skipped_overlap']}개."
        )

    ticker_rows = summarize_tickers(trades)
    best_row = max(
        comparison_rows,
        key=lambda row: (
            row["sharpe"] is not None,
            row["sharpe"] if row["sharpe"] is not None else float("-inf"),
            row["cumulative_return"] if row["cumulative_return"] is not None else float("-inf"),
        ),
    )

    unique_tickers = len({item.ticker for item in trades})
    total_price_ticks = sum(len(points) for source_map in price_series.values() for points in source_map.values())
    first_trade_ts = fmt_ts(min(item.entry_ts for item in trades))
    last_trade_ts = fmt_ts(max(item.exit_ts for item in trades))
    aligned_sources = ", ".join(
        f"{source}:{count}" for source, count in sorted(dict(diagnostics["aligned_sources"]).items())
    ) or "없음"

    trade_set_rows_html = []
    for row in comparison_rows:
        trade_set_rows_html.append(
            f"""
            <tr>
              <td>{esc(row['hold_label'])}</td>
              <td>{esc(row['signal_set'])}</td>
              <td>{row['trades']}</td>
              <td>{fmt_pct(row['avg_trade_return'])}</td>
              <td>{fmt_pct(row['cumulative_return'])}</td>
              <td>{fmt_pct(row['max_drawdown'])}</td>
              <td>{fmt_num(row['sharpe'])}</td>
              <td>{fmt_pct(row['win_rate'])}</td>
              <td>{fmt_num(row['avg_hold_ticks'])}</td>
            </tr>
            """
        )

    ticker_rows_html = []
    for row in ticker_rows[:12]:
        ticker_rows_html.append(
            f"""
            <tr>
              <td>{esc(row['ticker'])}</td>
              <td>{row['trades']}</td>
              <td>{fmt_pct(row['avg_trade_return'])}</td>
              <td>{fmt_pct(row['cumulative_return'])}</td>
              <td>{fmt_pct(row['win_rate'])}</td>
              <td>{fmt_pct(row['max_drawdown'])}</td>
            </tr>
            """
        )

    trade_rows_html = []
    for trade in sorted(trades, key=lambda item: (item.entry_ts, item.ticker), reverse=True)[:20]:
        trade_rows_html.append(
            f"""
            <tr>
              <td>{fmt_ts(trade.entry_ts)}</td>
              <td>{fmt_ts(trade.exit_ts)}</td>
              <td>{esc(trade.hold_label)}</td>
              <td>{esc(trade.ticker)}</td>
              <td>{esc(trade.signal)}</td>
              <td>{fmt_pct(trade.strategy_return)}</td>
              <td>{fmt_pct(trade.max_favorable_move)}</td>
              <td>{fmt_pct(trade.max_adverse_move)}</td>
              <td>{fmt_score(trade.confidence)}</td>
            </tr>
            """
        )

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 포지션 백테스트</title>
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
        "SIA Position<br>Backtest",
        "이 리포트는 ticker당 중복 포지션을 허용하지 않고, 각 신호를 고정 보유 기준으로 유지한 뒤 청산하는 방식으로 trade를 시뮬레이션합니다. 같은 ticker에 이미 열린 포지션이 있으면 뒤 신호는 건너뜁니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"기본 보유 기준: {esc(primary_hold.label)}",
            f"Trade 구간: {esc(first_trade_ts)} ~ {esc(last_trade_ts)}",
            f"Aligned sources: {esc(aligned_sources)}",
        ]),
        render_stats_panel([
            ("Signals", str(len(signals))),
            ("Aligned", str(diagnostics['aligned_signals'])),
            ("Mock Filtered", str(diagnostics['filtered_mock_only'])),
            ("Trades", str(len(trades))),
        ]),
    )}

    <section class="summary-grid">
      {render_summary_panel("핵심 해석", "<p>이 엔진은 `ticker별 중복 포지션 금지` 규칙과 함께, entry price와 같은 source의 price tick이 허용오차 8% 안에서 맞는 경우만 사용합니다. <code>mock</code> source는 strict 포지션 백테스트에서 제외합니다. 기본 tick 기준 외에 `30분`, `1시간`, `당일 종가`, `익일 시가` 기준을 같이 비교합니다.</p>")}
      {render_summary_panel("현재 가장 나은 집합", f"<p>{esc(best_row['hold_label'])} / {esc(presentation_signal_set_display(best_row['signal_set']))} / 누적수익률 {fmt_pct(best_row['cumulative_return'])} / Sharpe {fmt_num(best_row['sharpe'])} / MDD {fmt_pct(best_row['max_drawdown'])}</p>")}
    </section>

    <section class="panel table-panel">
      <div class="table-head">
        <h2>포지션 집합별 메트릭</h2>
        <p>ALL, BUY-only, SELL-only을 보유 기준별로 비교</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>보유 기준</th>
            <th>Signal Set</th>
            <th>Trades</th>
            <th>평균 Trade Return</th>
            <th>누적수익률</th>
            <th>MDD</th>
            <th>Sharpe</th>
            <th>적중률</th>
            <th>평균 Hold Tick</th>
          </tr>
        </thead>
        <tbody>
          {''.join(trade_set_rows_html)}
        </tbody>
      </table>
    </section>

    {render_table_section(
        "티커별 성과",
        f"중복 포지션 금지 규칙 반영 후 {primary_hold.label} 기준 ticker별 누적 성과",
        ["Ticker", "Trades", "평균 Trade Return", "누적수익률", "적중률", "MDD"],
        ''.join(ticker_rows_html),
    )}

    {render_table_section(
        "최근 Trade 20건",
        f"entry/exit 기준으로 실제 시뮬레이션된 포지션 ({primary_hold.label} 기준)",
        ["Entry", "Exit", "보유 기준", "Ticker", "Signal", "Strategy Return", "Max Favorable", "Max Adverse", "Confidence"],
        ''.join(trade_rows_html),
    )}

    {render_footnote_section(
        "방법론 메모",
        f"1. 이 리포트는 외부 API 재조회 없이 현재 DB만 사용합니다.<br>2. strict 기준: entry price와 같은 source의 price tick이 허용오차 8% 안에서 맞아야 하며, <code>mock</code> source는 제외합니다.<br>3. 같은 ticker에서 포지션이 살아있는 동안 들어오는 다음 신호는 `skipped overlap`으로 제외합니다.<br>4. 다른 ticker 간 동시 보유는 허용하지만, equity curve는 실현 순서대로 단순 연결합니다.<br>5. Sharpe는 연환산이 아닌 sample Sharpe입니다.<br>6. stored price tick 수는 {total_price_ticks}, source mismatch 필터 수는 {diagnostics['filtered_source_mismatch']}, overlap skip 수는 {diagnostics['skipped_overlap']} 입니다.<br>7. 기본 tick 기준 외에 `30분`, `1시간`, `당일 종가`, `익일 시가` 비교를 같이 보여줍니다.",
    )}
  </main>
</body>
</html>"""


def load_report_inputs(db_path: Path, primary_hold: BacktestHorizon, holds: list[BacktestHorizon]) -> PositionBacktestInputs:
    return PositionBacktestInputs(
        signals=load_signals(db_path),
        price_series=load_price_series(db_path),
        primary_hold=primary_hold,
        holds=holds,
    )


def summarize_report(inputs: PositionBacktestInputs) -> PositionBacktestSummary:
    primary_trades: list[Trade] = []
    primary_diagnostics: dict[str, object] = {}
    comparison_rows: list[dict[str, object]] = []
    for hold in inputs.holds:
        trades, diagnostics = simulate_trades(inputs.signals, inputs.price_series, hold)
        comparison_rows.extend(summarize_trade_sets(trades, hold))
        if hold.key == inputs.primary_hold.key:
            primary_trades = trades
            primary_diagnostics = diagnostics
    return PositionBacktestSummary(
        primary_trades=primary_trades,
        primary_diagnostics=primary_diagnostics,
        comparison_rows=comparison_rows,
    )


def render_report(db_path: Path, inputs: PositionBacktestInputs, summary: PositionBacktestSummary) -> str:
    return localize_output_html(
        render_html(
            db_path,
            inputs.primary_hold,
            inputs.signals,
            inputs.price_series,
            summary.primary_trades,
            summary.primary_diagnostics,
            summary.comparison_rows,
        )
    )


def write_report(db_path: Path, output_path: Path, primary_hold: BacktestHorizon, holds: list[BacktestHorizon]) -> Path:
    inputs = load_report_inputs(db_path, primary_hold, holds)
    summary = summarize_report(inputs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_report(db_path, inputs, summary), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate overlap-aware position backtest report from local sqlite data.")
    parser.add_argument("--db-path", required=True, help="Path to trading_signal_notifier sqlite db")
    parser.add_argument("--output", required=True, help="HTML output path")
    parser.add_argument("--hold-ticks", type=int, default=3, help="Fixed holding period measured in future price ticks")
    parser.add_argument("--hold-horizons", default="", help="Comma-separated tick/time holding horizons")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser()
    output_path = Path(args.output).expanduser()
    if args.hold_horizons.strip():
        holds = parse_horizon_specs(args.hold_horizons)
    else:
        holds = parse_horizon_specs(f"{max(1, int(args.hold_ticks))},30m,1h,day_close,next_open")
    if not holds:
        holds = parse_horizon_specs(DEFAULT_POSITION_HORIZONS)
    primary_hold = holds[0]
    write_report(db_path, output_path, primary_hold, holds)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
