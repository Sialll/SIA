from __future__ import annotations

import argparse
import html
import os
from pathlib import Path

import position_backtest_report as position_report
import price_backtest_report as price_report

try:
    from .report_common import localize_report_html, render_empty_report_html
    from .report_metrics import fmt_pct, fmt_ts, read_float_env, read_positive_int_env
    from .report_theme import render_report_theme
    from .report_widgets import render_action_section, render_gate_strip, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section
except ImportError:
    from report_common import localize_report_html, render_empty_report_html  # type: ignore
    from report_metrics import fmt_pct, fmt_ts, read_float_env, read_positive_int_env  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import render_action_section, render_gate_strip, render_hero_section, render_meta_row, render_stats_panel, render_summary_panel, render_table_section  # type: ignore


PRICE_HORIZONS = [1, 3, 5, 10]
POSITION_HOLDS = [1, 3, 5]
DEFAULT_MIN_PRICE_SAMPLES = 20
DEFAULT_MIN_POSITION_TRADES = 10
DEFAULT_MIN_STRICT_ALIGNED_SIGNALS = 8
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


class ReadinessInputs:
    def __init__(
        self,
        price_signals: list[price_report.SignalSnapshot],
        price_series: dict[str, dict[str, list[price_report.PricePoint]]],
        position_signals: list[position_report.SignalSnapshot],
        position_series: dict[str, dict[str, list[position_report.PricePoint]]],
    ) -> None:
        self.price_signals = price_signals
        self.price_series = price_series
        self.position_signals = position_signals
        self.position_series = position_series


class ReadinessSummary:
    def __init__(
        self,
        price_rows: list[dict[str, object]],
        price_diagnostics: dict[str, object],
        position_rows: list[dict[str, object]],
    ) -> None:
        self.price_rows = price_rows
        self.price_diagnostics = price_diagnostics
        self.position_rows = position_rows
MIN_PRICE_SAMPLES = read_positive_int_env("SIA_MIN_PRICE_SAMPLES", DEFAULT_MIN_PRICE_SAMPLES)
MIN_POSITION_TRADES = read_positive_int_env("SIA_MIN_POSITION_TRADES", DEFAULT_MIN_POSITION_TRADES)
MIN_STRICT_ALIGNED_SIGNALS = read_positive_int_env(
    "SIA_MIN_STRICT_ALIGNED_SIGNALS",
    DEFAULT_MIN_STRICT_ALIGNED_SIGNALS,
)


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


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def readiness_badge(count: int, minimum: int) -> tuple[str, str]:
    if count >= minimum:
        return f"READY ({count}/{minimum}+)", "ready"
    if count > 0:
        return f"THIN ({count}/{minimum})", "thin"
    return f"BLOCKED (0/{minimum})", "blocked"


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 백테스트 준비도", message)


def localize_output_html(text: str) -> str:
    return localize_report_html(
        text,
        [
            ("SIA Backtest<br>Readiness", "SIA 백테스트<br>준비도"),
            ("strict gate", "정합 기준"),
            ("minimum gate:", "최소 기준:"),
            ("Gate 기준", "기준값"),
            ("THIN/BLOCKED", "표본 부족/차단"),
            (">READY<", ">준비 완료<"),
            (">PARTIAL<", ">부분 준비<"),
            (">NOT READY<", ">미준비<"),
            ("READY (", "준비 완료 ("),
            ("THIN (", "표본 부족 ("),
            ("BLOCKED (", "차단 ("),
        ],
    )


def summarize_price_readiness(
    signals: list[price_report.SignalSnapshot],
    price_series: dict[str, dict[str, list[price_report.PricePoint]]],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    diagnostics: dict[str, object] = {
        "total_signals": len(signals),
        "aligned_signals": 0,
        "filtered_mock_only": 0,
        "filtered_source_mismatch": 0,
        "aligned_sources": {},
    }
    aligned_records: list[tuple[price_report.SignalSnapshot, int, list[price_report.PricePoint]]] = []

    for signal in signals:
        alignment = price_report.align_signal_to_series(signal, price_series.get(signal.ticker, {}))
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
        series = price_series.get(signal.ticker, {}).get(alignment.source, [])
        aligned_records.append((signal, alignment.entry_index, series))

    rows: list[dict[str, object]] = []
    aligned_total = int(diagnostics["aligned_signals"])
    for horizon in PRICE_HORIZONS:
        samples = 0
        gap_count = 0
        usable_tickers: set[str] = set()
        for signal, entry_index, series in aligned_records:
            if entry_index + horizon < len(series):
                samples += 1
                usable_tickers.add(signal.ticker)
            else:
                gap_count += 1
        badge, badge_class = readiness_badge(samples, MIN_PRICE_SAMPLES)
        coverage = (samples / aligned_total) if aligned_total else None
        rows.append(
            {
                "horizon": horizon,
                "samples": samples,
                "minimum": MIN_PRICE_SAMPLES,
                "coverage": coverage,
                "gap_count": gap_count,
                "usable_tickers": len(usable_tickers),
                "badge": badge,
                "badge_class": badge_class,
            }
        )
    return rows, diagnostics


def summarize_position_readiness(
    signals: list[position_report.SignalSnapshot],
    price_series: dict[str, dict[str, list[position_report.PricePoint]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for hold_ticks in POSITION_HOLDS:
        trades, diagnostics = position_report.simulate_trades(signals, price_series, hold_ticks)
        trade_count = len(trades)
        badge, badge_class = readiness_badge(trade_count, MIN_POSITION_TRADES)
        aligned_total = int(diagnostics["aligned_signals"])
        coverage = (trade_count / aligned_total) if aligned_total else None
        rows.append(
            {
                "hold_ticks": hold_ticks,
                "trades": trade_count,
                "minimum": MIN_POSITION_TRADES,
                "coverage": coverage,
                "aligned": aligned_total,
                "mock_filtered": int(diagnostics["filtered_mock_only"]),
                "source_mismatch": int(diagnostics["filtered_source_mismatch"]),
                "overlap_skip": int(diagnostics["skipped_overlap"]),
                "badge": badge,
                "badge_class": badge_class,
            }
        )
    return rows


def verdict_text(price_rows: list[dict[str, object]], position_rows: list[dict[str, object]], aligned_signals: int) -> tuple[str, str]:
    price_ready = sum(1 for row in price_rows if row["badge_class"] == "ready")
    position_ready = sum(1 for row in position_rows if row["badge_class"] == "ready")
    if aligned_signals < MIN_STRICT_ALIGNED_SIGNALS:
        return "NOT READY", "strict non-mock 신호 수 자체가 아직 얇습니다."
    if price_ready == len(price_rows) and position_ready == len(position_rows):
        return "READY", "가격 horizon과 포지션 hold tick 모두 최소 표본을 넘었습니다."
    if price_ready > 0 or position_ready > 0:
        return "PARTIAL", "일부 horizon만 최소 표본을 넘었습니다. 결과 해석은 제한적으로만 해야 합니다."
    return "NOT READY", "strict 기준 샘플 수가 최소치에 못 미칩니다."


def recommendation_lines(price_rows: list[dict[str, object]], position_rows: list[dict[str, object]], price_diagnostics: dict[str, object]) -> list[str]:
    lines: list[str] = []
    aligned = int(price_diagnostics["aligned_signals"])
    mock_filtered = int(price_diagnostics["filtered_mock_only"])
    mismatch = int(price_diagnostics["filtered_source_mismatch"])
    if aligned < MIN_STRICT_ALIGNED_SIGNALS:
        lines.append(
            f"strict aligned signal은 {aligned}건입니다. 최소 {MIN_STRICT_ALIGNED_SIGNALS}건까지는 live/non-mock 실행을 더 쌓는 편이 맞습니다."
        )
    if mock_filtered > 0:
        lines.append(
            f"mock filtered가 {mock_filtered}건입니다. dry-run row는 strict 백테스트에서 자동 제외되므로 live row 비중을 더 올려야 합니다."
        )
    if mismatch > 0:
        lines.append(
            f"source mismatch가 {mismatch}건입니다. entry source와 가격 tick source 정합성을 먼저 확인해야 합니다."
        )

    weakest_price = min(price_rows, key=lambda row: int(row["samples"]))
    weakest_position = min(position_rows, key=lambda row: int(row["trades"]))
    if int(weakest_price["samples"]) < MIN_PRICE_SAMPLES:
        lines.append(
            f"+{weakest_price['horizon']} tick 가격 평가 샘플은 {weakest_price['samples']}건입니다. 최소 {MIN_PRICE_SAMPLES}건 전까지는 horizon 비교를 과신하면 안 됩니다."
        )
    if int(weakest_position["trades"]) < MIN_POSITION_TRADES:
        lines.append(
            f"hold {weakest_position['hold_ticks']} tick 포지션 trade는 {weakest_position['trades']}건입니다. 최소 {MIN_POSITION_TRADES}건 전까지는 누적수익률/MDD 해석이 흔들립니다."
        )
    if not lines:
        lines.append("현재 기준으로는 표본 gate를 통과했습니다. 그 다음은 factor별 성능 분해와 기간 분리 검증 단계입니다.")
    return lines


def render_html(
    db_path: Path,
    price_signals: list[price_report.SignalSnapshot],
    price_rows: list[dict[str, object]],
    price_diagnostics: dict[str, object],
    position_rows: list[dict[str, object]],
) -> str:
    verdict, verdict_reason = verdict_text(
        price_rows,
        position_rows,
        int(price_diagnostics["aligned_signals"]),
    )
    recommendations = recommendation_lines(price_rows, position_rows, price_diagnostics)
    first_ts = min((signal.ts for signal in price_signals), default=None)
    last_ts = max((signal.ts for signal in price_signals), default=None)
    aligned_sources = ", ".join(
        f"{source}:{count}" for source, count in sorted(dict(price_diagnostics["aligned_sources"]).items())
    ) or "-"
    gate_summary = (
        f"가격 horizon {MIN_PRICE_SAMPLES} sample / "
        f"포지션 hold {MIN_POSITION_TRADES} trade / "
        f"strict aligned {MIN_STRICT_ALIGNED_SIGNALS} signal"
    )
    regime_chip_html = "".join(
        f'<span class="gate-chip">{esc(chip)}</span>'
        for chip in load_regime_display()
    )
    ready_price_count = sum(1 for row in price_rows if row["badge_class"] == "ready")
    ready_position_count = sum(1 for row in position_rows if row["badge_class"] == "ready")
    verdict_class = "ready" if verdict == "READY" else ("partial" if verdict == "PARTIAL" else "blocked")

    price_rows_html = "".join(
        f"""
        <tr>
          <td>+{row['horizon']} tick</td>
          <td><span class="badge {row['badge_class']}">{esc(row['badge'])}</span></td>
          <td>{row['samples']}</td>
          <td>{row['minimum']}</td>
          <td>{fmt_pct(row['coverage'])}</td>
          <td>{row['gap_count']}</td>
          <td>{row['usable_tickers']}</td>
        </tr>
        """
        for row in price_rows
    )
    position_rows_html = "".join(
        f"""
        <tr>
          <td>{row['hold_ticks']} tick</td>
          <td><span class="badge {row['badge_class']}">{esc(row['badge'])}</span></td>
          <td>{row['trades']}</td>
          <td>{row['minimum']}</td>
          <td>{fmt_pct(row['coverage'])}</td>
          <td>{row['aligned']}</td>
          <td>{row['overlap_skip']}</td>
        </tr>
        """
        for row in position_rows
    )
    recommendation_html = "".join(f"<li>{esc(line)}</li>" for line in recommendations)

    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 백테스트 준비도</title>
  <style>
    {render_report_theme()}
    :root {{
      --bg: #f4efe6;
      --panel: rgba(255, 252, 246, 0.88);
      --ink: #171411;
      --muted: #6c6257;
      --line: rgba(23, 20, 17, 0.12);
      --ready: #155e63;
      --thin: #b45309;
      --blocked: #9a3412;
      --partial: #8b5cf6;
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
      width: min(1200px, 100%);
      margin: 0 auto;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.35fr 1fr;
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
    .stat .label,
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
    .stat .label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .stat .value {{
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
    .verdict {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      background: rgba(255,255,255,0.68);
    }}
    .verdict.ready,
    .badge.ready {{
      color: var(--ready);
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .verdict.partial {{
      color: var(--partial);
      border-color: rgba(139,92,246,0.18);
      background: rgba(139,92,246,0.10);
    }}
    .verdict.blocked,
    .badge.blocked {{
      color: var(--blocked);
      border-color: rgba(154,52,18,0.18);
      background: rgba(154,52,18,0.10);
    }}
    .badge.thin {{
      color: var(--thin);
      border-color: rgba(180,83,9,0.18);
      background: rgba(180,83,9,0.10);
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
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
      min-width: 760px;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
    }}
    th {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    .notes ul {{
      margin: 0;
      padding-left: 18px;
      line-height: 1.7;
    }}
    .footnote {{
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
      margin-top: 8px;
    }}
    @media (max-width: 880px) {{
      body {{ padding: 14px; }}
      .hero,
      .summary-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    {render_hero_section(
        "SIA Backtest<br>Readiness",
        "이 리포트는 백테스트 수익률보다 먼저, 현재 DB가 strict 기준 결과를 읽어도 되는 상태인지 판정합니다. 표본이 얇으면 숫자는 보여도 해석은 보류해야 합니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"신호 구간: {fmt_ts(first_ts)} ~ {fmt_ts(last_ts)}",
            f"Aligned sources: {esc(aligned_sources)}",
        ]),
        render_stats_panel([
            ("Verdict", f"<span class='verdict {verdict_class}'>{esc(verdict)}</span>"),
            ("Signals", str(int(price_diagnostics['total_signals']))),
            ("Strict Aligned", str(int(price_diagnostics['aligned_signals']))),
            ("Ready Buckets", str(ready_price_count + ready_position_count)),
        ]),
        extra_html=render_gate_strip(f"<span class='gate-chip'>가격 gate {MIN_PRICE_SAMPLES}</span><span class='gate-chip'>포지션 gate {MIN_POSITION_TRADES}</span><span class='gate-chip'>strict gate {MIN_STRICT_ALIGNED_SIGNALS}</span>") + render_gate_strip(regime_chip_html),
    )}

    <section class="summary-grid">
      {render_summary_panel("현재 판정", f"<p>{esc(verdict_reason)}</p><p class='footnote'>minimum gate: {esc(gate_summary)}</p>")}
      {render_summary_panel("Gate 기준", f"<p>{esc(gate_summary)}</p><p class='footnote'>이 기준은 env에서 조정됩니다: <code>SIA_MIN_PRICE_SAMPLES</code>, <code>SIA_MIN_POSITION_TRADES</code>, <code>SIA_MIN_STRICT_ALIGNED_SIGNALS</code></p><p class='footnote'>전략 국면 파라미터는 <code>SIA_CONFIRM_*</code>, <code>SIA_REGIME_*</code>에서 읽습니다.</p>")}
    </section>

    <section class="summary-grid">
      {render_summary_panel("현재 가장 큰 병목", f"<p>mock 제외 {int(price_diagnostics['filtered_mock_only'])}건, source mismatch {int(price_diagnostics['filtered_source_mismatch'])}건입니다. live/non-mock row와 후속 tick 누적이 핵심입니다.</p>")}
      {render_summary_panel("해석 규칙", "<p>READY 전에는 수익률보다 표본 수를 먼저 봐야 합니다. THIN/BLOCKED 구간의 Sharpe, MDD, 누적수익률은 참고치로만 다뤄야 합니다.</p>")}
    </section>

    {render_table_section(
        "가격 백테스트 준비도",
        "strict source 정합성 + horizon별 future tick 샘플 수",
        ["Horizon", "Status", "Samples", "Min Gate", "Coverage", "Future Gap", "Usable Tickers"],
        price_rows_html,
    )}

    {render_table_section(
        "포지션 백테스트 준비도",
        "ticker 중복 포지션 금지 규칙을 포함한 hold tick별 trade 수",
        ["Hold", "Status", "Trades", "Min Gate", "Coverage", "Aligned", "Overlap Skip"],
        position_rows_html,
    )}

    {render_action_section(
        "다음 액션",
        recommendation_html,
        "strict 기준은 기존 리포트와 동일합니다. entry price와 같은 source의 tick이 허용오차 8% 안에서 맞아야 하며, <code>mock</code> source는 제외합니다.",
    )}
  </main>
</body>
</html>"""


def load_report_inputs(db_path: Path) -> ReadinessInputs:
    return ReadinessInputs(
        price_signals=price_report.load_signals(db_path),
        price_series=price_report.load_price_series(db_path),
        position_signals=position_report.load_signals(db_path),
        position_series=position_report.load_price_series(db_path),
    )


def summarize_report(inputs: ReadinessInputs) -> ReadinessSummary:
    price_rows, price_diagnostics = summarize_price_readiness(inputs.price_signals, inputs.price_series)
    position_rows = summarize_position_readiness(inputs.position_signals, inputs.position_series)
    return ReadinessSummary(
        price_rows=price_rows,
        price_diagnostics=price_diagnostics,
        position_rows=position_rows,
    )


def render_report(db_path: Path, inputs: ReadinessInputs, summary: ReadinessSummary) -> str:
    return localize_output_html(
        render_html(
            db_path,
            inputs.price_signals,
            summary.price_rows,
            summary.price_diagnostics,
            summary.position_rows,
        )
    )


def write_report(db_path: Path, output_path: Path) -> Path:
    inputs = load_report_inputs(db_path)
    if not inputs.price_signals:
        output_path.write_text(build_empty_html("BUY/SELL 신호가 아직 없습니다. notifier를 먼저 live로 실행하세요."), encoding="utf-8")
        return output_path

    summary = summarize_report(inputs)
    output_path.write_text(render_report(db_path, inputs, summary), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate strict backtest readiness report from local sqlite data.")
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
