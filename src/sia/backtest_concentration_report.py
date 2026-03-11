from __future__ import annotations

import argparse
import html
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

try:
    from .backtest_horizons import DEFAULT_POSITION_HORIZONS, BacktestHorizon, parse_horizon_specs
    from .position_backtest_report import (
        DEFAULT_FEE_BPS_PER_SIDE,
        DEFAULT_SLIPPAGE_BPS_PER_SIDE,
        Trade,
        compute_path_metrics,
        load_price_series,
        load_signals,
        round_trip_cost_rate,
        simulate_trades,
    )
    from .report_common import localize_report_html, render_empty_report_html
    from .report_metrics import fmt_num, fmt_pct, fmt_ts
    from .report_theme import render_report_theme
    from .report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section
except ImportError:
    from backtest_horizons import DEFAULT_POSITION_HORIZONS, BacktestHorizon, parse_horizon_specs  # type: ignore
    from position_backtest_report import (  # type: ignore
        DEFAULT_FEE_BPS_PER_SIDE,
        DEFAULT_SLIPPAGE_BPS_PER_SIDE,
        Trade,
        compute_path_metrics,
        load_price_series,
        load_signals,
        round_trip_cost_rate,
        simulate_trades,
    )
    from report_common import localize_report_html, render_empty_report_html  # type: ignore
    from report_metrics import fmt_num, fmt_pct, fmt_ts  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import render_footnote_section, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section  # type: ignore


@dataclass(frozen=True)
class ConcentrationInputs:
    holds: list[BacktestHorizon]
    slippage_bps_per_side: float
    fee_bps_per_side: float
    round_trip_cost_rate: float
    trades_by_hold: dict[str, list[Trade]]


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 종목 편향 진단", message)


def localize_output_html(text: str) -> str:
    return localize_report_html(
        text,
        [
            ("SIA Concentration<br>Report", "SIA 종목 편향<br>진단"),
            ("Top 1", "상위 1종목"),
            ("Top 3", "상위 3종목"),
            ("Top 5", "상위 5종목"),
            ("Net Contribution", "순기여"),
            ("Abs Share", "절대 기여 비중"),
        ],
    )


def load_inputs(
    db_path: Path,
    holds: list[BacktestHorizon],
    slippage_bps_per_side: float,
    fee_bps_per_side: float,
) -> ConcentrationInputs:
    signals = load_signals(db_path)
    price_series = load_price_series(db_path)
    cost_rate = round_trip_cost_rate(slippage_bps_per_side, fee_bps_per_side)
    trades_by_hold: dict[str, list[Trade]] = {}
    for hold in holds:
        trades, _ = simulate_trades(signals, price_series, hold, cost_rate)
        trades_by_hold[hold.key] = trades
    return ConcentrationInputs(
        holds=holds,
        slippage_bps_per_side=slippage_bps_per_side,
        fee_bps_per_side=fee_bps_per_side,
        round_trip_cost_rate=cost_rate,
        trades_by_hold=trades_by_hold,
    )


def summarize_ticker_rows(trades: list[Trade]) -> list[dict[str, object]]:
    grouped: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        grouped[trade.ticker].append(trade)
    total_abs = sum(abs(trade.strategy_return) for trade in trades)
    rows: list[dict[str, object]] = []
    for ticker, series in grouped.items():
        metrics = compute_path_metrics(series)
        abs_share = None
        if total_abs > 0:
            abs_share = sum(abs(item.strategy_return) for item in series) / total_abs
        rows.append(
            {
                "ticker": ticker,
                "trades": len(series),
                "avg_trade_return": metrics["avg_trade_return"],
                "cumulative_return": metrics["cumulative_return"],
                "win_rate": metrics["win_rate"],
                "net_contribution": sum(item.strategy_return for item in series),
                "abs_share": abs_share,
            }
        )
    rows.sort(
        key=lambda row: (
            row["abs_share"] is not None,
            row["abs_share"] if row["abs_share"] is not None else float("-inf"),
            row["net_contribution"],
        ),
        reverse=True,
    )
    return rows


def summarize_exclusions(rows: list[dict[str, object]], trades: list[Trade]) -> list[dict[str, object]]:
    exclusions: list[dict[str, object]] = []
    ordered_tickers = [str(row["ticker"]) for row in rows]
    for count in (1, 3, 5):
        excluded = set(ordered_tickers[:count])
        remaining = [trade for trade in trades if trade.ticker not in excluded]
        metrics = compute_path_metrics(remaining)
        exclusions.append(
            {
                "excluded_label": f"상위 {count}종목 제외",
                "remaining_trades": len(remaining),
                "cumulative_return": metrics["cumulative_return"],
                "avg_trade_return": metrics["avg_trade_return"],
                "win_rate": metrics["win_rate"],
            }
        )
    return exclusions


def summarize_hold_row(hold: BacktestHorizon, rows: list[dict[str, object]], trades: list[Trade]) -> dict[str, object]:
    top1 = rows[0]["abs_share"] if len(rows) >= 1 else None
    top3 = sum((row["abs_share"] or 0.0) for row in rows[:3]) if rows else None
    top5 = sum((row["abs_share"] or 0.0) for row in rows[:5]) if rows else None
    verdict = "양호"
    if (top1 is not None and top1 >= 0.35) or (top3 is not None and top3 >= 0.70):
        verdict = "주의"
    metrics = compute_path_metrics(trades)
    return {
        "hold_label": hold.label,
        "trades": len(trades),
        "top1_share": top1,
        "top3_share": top3,
        "top5_share": top5,
        "cumulative_return": metrics["cumulative_return"],
        "verdict": verdict,
    }


def render_html(db_path: Path, inputs: ConcentrationInputs) -> str:
    total_trades = sum(len(trades) for trades in inputs.trades_by_hold.values())
    if total_trades == 0:
        return build_empty_html("종목 편향을 계산할 strict trade 표본이 없습니다.")

    hold_rows: list[dict[str, object]] = []
    detail_sections: list[str] = []
    best_hold_label = "-"
    best_hold_score = float("-inf")

    for hold in inputs.holds:
        trades = inputs.trades_by_hold.get(hold.key, [])
        if not trades:
            continue
        ticker_rows = summarize_ticker_rows(trades)
        exclusion_rows = summarize_exclusions(ticker_rows, trades)
        hold_row = summarize_hold_row(hold, ticker_rows, trades)
        hold_rows.append(hold_row)

        score = hold_row["top3_share"] or 0.0
        if score > best_hold_score:
            best_hold_score = score
            best_hold_label = hold.label

        ticker_rows_html = "".join(
            f"""
            <tr>
              <td>{esc(row['ticker'])}</td>
              <td>{row['trades']}</td>
              <td>{fmt_pct(row['avg_trade_return'])}</td>
              <td>{fmt_pct(row['cumulative_return'])}</td>
              <td>{fmt_pct(row['win_rate'])}</td>
              <td>{fmt_pct(row['net_contribution'])}</td>
              <td>{fmt_pct(row['abs_share'])}</td>
            </tr>
            """
            for row in ticker_rows[:15]
        )

        exclusion_rows_html = "".join(
            f"""
            <tr>
              <td>{esc(row['excluded_label'])}</td>
              <td>{row['remaining_trades']}</td>
              <td>{fmt_pct(row['avg_trade_return'])}</td>
              <td>{fmt_pct(row['cumulative_return'])}</td>
              <td>{fmt_pct(row['win_rate'])}</td>
            </tr>
            """
            for row in exclusion_rows
        )

        detail_sections.append(
            render_table_section(
                f"{hold.label} 종목별 기여도",
                "절대 기여 비중 기준 상위 종목과 제외 시 성과 변화",
                ["Ticker", "Trades", "평균 Trade Return", "누적수익률", "적중률", "순기여", "절대 기여 비중"],
                ticker_rows_html,
            )
            + render_table_section(
                f"{hold.label} 상위 종목 제외 성과",
                "소수 종목을 제거했을 때 성과가 얼마나 유지되는지 확인",
                ["제외 범위", "남은 Trades", "평균 Trade Return", "누적수익률", "적중률"],
                exclusion_rows_html,
            )
        )

    hold_rows_html = "".join(
        f"""
        <tr>
          <td>{esc(row['hold_label'])}</td>
          <td>{row['trades']}</td>
          <td>{fmt_pct(row['top1_share'])}</td>
          <td>{fmt_pct(row['top3_share'])}</td>
          <td>{fmt_pct(row['top5_share'])}</td>
          <td>{fmt_pct(row['cumulative_return'])}</td>
          <td>{esc(row['verdict'])}</td>
        </tr>
        """
        for row in hold_rows
    )

    first_trade_ts = fmt_ts(
        min(trade.entry_ts for trades in inputs.trades_by_hold.values() for trade in trades)  # type: ignore[arg-type]
    )
    last_trade_ts = fmt_ts(
        max(trade.exit_ts for trades in inputs.trades_by_hold.values() for trade in trades)  # type: ignore[arg-type]
    )

    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 종목 편향 진단</title>
  <style>{render_report_theme()}</style>
</head>
<body>
  <main class="shell">
    {render_hero_section(
        "SIA Concentration<br>Report",
        "백테스트 결과가 특정 소수 종목에 과도하게 의존하는지 보는 리포트입니다. 기본 포지션 백테스트와 같은 strict 기준, 같은 비용 가정을 사용합니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"Trade 구간: {esc(first_trade_ts)} ~ {esc(last_trade_ts)}",
            f"보유 기준: {esc(', '.join(hold.label for hold in inputs.holds))}",
            f"비용 가정: 왕복 {fmt_pct(inputs.round_trip_cost_rate)}",
        ]),
        render_stats_panel([
            ("Trades", str(total_trades)),
            ("보유 기준 수", str(len(hold_rows))),
            ("최대 집중 기준", best_hold_label),
            ("Top 3 집중도", fmt_pct(best_hold_score if best_hold_score != float('-inf') else None)),
        ]),
    )}

    <section class="summary-grid">
      {render_summary_panel("핵심 해석", "<p>`상위 1종목`, `상위 3종목`, `상위 5종목`이 전체 절대 기여에서 차지하는 비중을 봅니다. 상위 종목을 제거했을 때도 성과가 유지되면 전략 설명력이 올라갑니다.</p>")}
      {render_summary_panel("집중도 판정 기준", "<p>기본적으로 `상위 1종목 35% 이상` 또는 `상위 3종목 70% 이상`이면 `주의`로 봅니다. 이 기준은 판매용 방어선으로 둔 보수적 기준입니다.</p>")}
    </section>

    {render_table_section(
        "보유 기준별 집중도",
        "각 보유 기준에서 소수 종목 의존도가 얼마나 큰지 요약",
        ["보유 기준", "Trades", "상위 1종목", "상위 3종목", "상위 5종목", "누적수익률", "판정"],
        hold_rows_html,
    )}

    {''.join(detail_sections)}

    {render_footnote_section(
        "방법론 메모",
        f"1. 이 리포트는 포지션 백테스트와 같은 strict 기준을 사용합니다.<br>2. 비용 가정은 왕복 슬리피지 {inputs.slippage_bps_per_side * 2:.1f}bp + 수수료 {inputs.fee_bps_per_side * 2:.1f}bp, 총 {fmt_pct(inputs.round_trip_cost_rate)}입니다.<br>3. 절대 기여 비중은 각 종목 trade의 절대 전략 수익률 합을 전체 절대 전략 수익률 합으로 나눈 값입니다.<br>4. `상위 3종목 제외 성과`가 크게 무너지면 종목 편향이 강하다고 보는 편이 맞습니다.",
    )}
  </main>
</body>
</html>"""
    return localize_output_html(html_doc)


def write_report(
    db_path: Path,
    output_path: Path,
    holds: list[BacktestHorizon],
    slippage_bps_per_side: float,
    fee_bps_per_side: float,
) -> Path:
    inputs = load_inputs(db_path, holds, slippage_bps_per_side, fee_bps_per_side)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(db_path, inputs), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ticker concentration diagnostics from strict position backtest trades.")
    parser.add_argument("--db-path", required=True, help="Path to trading_signal_notifier sqlite db")
    parser.add_argument("--output", required=True, help="HTML output path")
    parser.add_argument("--hold-horizons", default="3,30m,1h,day_close,next_open", help="Comma-separated tick/time holding horizons")
    parser.add_argument("--slippage-bps-per-side", type=float, default=DEFAULT_SLIPPAGE_BPS_PER_SIDE, help="Per-side slippage assumption in basis points")
    parser.add_argument("--fee-bps-per-side", type=float, default=DEFAULT_FEE_BPS_PER_SIDE, help="Per-side fee assumption in basis points")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = Path(args.db_path).expanduser()
    output_path = Path(args.output).expanduser()
    holds = parse_horizon_specs(args.hold_horizons)
    if not holds:
        holds = parse_horizon_specs(DEFAULT_POSITION_HORIZONS)
    write_report(
        db_path,
        output_path,
        holds,
        float(args.slippage_bps_per_side),
        float(args.fee_bps_per_side),
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
