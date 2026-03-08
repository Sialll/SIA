from __future__ import annotations

import argparse
import html
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

try:
    from .report_common import render_empty_report_html
    from .report_metrics import fmt_pct, fmt_ts
    from .report_theme import render_report_theme
    from .report_widgets import (
        render_action_section,
        render_hero_section,
        render_meta_row,
        render_notes_section,
        render_stats_panel,
        render_summary_panel,
        render_table_section,
    )
except ImportError:
    from report_common import render_empty_report_html  # type: ignore
    from report_metrics import fmt_pct, fmt_ts  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import (  # type: ignore
        render_action_section,
        render_hero_section,
        render_meta_row,
        render_notes_section,
        render_stats_panel,
        render_summary_panel,
        render_table_section,
    )


@dataclass(frozen=True)
class SourceStat:
    source: str
    rows: int
    tickers: int
    last_ts: int | None


@dataclass(frozen=True)
class QualityInputs:
    tables: set[str]
    snapshot_sources: list[SourceStat]
    price_sources: list[SourceStat]
    total_snapshots: int
    total_price_ticks: int
    total_events: int
    total_macro: int
    total_alerts: int
    sent_alerts: int
    last_snapshot_ts: int | None
    last_price_ts: int | None
    last_macro_ts: int | None
    strict_non_mock: int
    strict_ready: int
    missing_signal_source: int


@dataclass(frozen=True)
class QualitySummary:
    verdict: str
    verdict_class: str
    findings: list[str]
    recommendations: list[str]


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


MAX_MOCK_RATIO = env_float("SIA_DATA_QUALITY_MAX_MOCK_RATIO", 0.50)
MIN_STRICT_READY_RATIO = env_float("SIA_DATA_QUALITY_MIN_STRICT_READY_RATIO", 0.35)


def table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def load_source_stats(
    conn: sqlite3.Connection,
    table: str,
    source_expr: str,
) -> list[SourceStat]:
    rows = conn.execute(
        f"""
        SELECT
            {source_expr} AS source,
            COUNT(*) AS rows,
            COUNT(DISTINCT ticker) AS tickers,
            MAX(ts) AS last_ts
        FROM {table}
        GROUP BY 1
        ORDER BY rows DESC, source ASC
        """
    ).fetchall()
    return [
        SourceStat(
            source=str(row[0]),
            rows=int(row[1]),
            tickers=int(row[2]),
            last_ts=int(row[3]) if row[3] is not None else None,
        )
        for row in rows
    ]


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 데이터 품질", message)


def load_inputs(db_path: Path) -> QualityInputs:
    with sqlite3.connect(str(db_path)) as conn:
        tables = {
            str(row[0])
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }

        snapshot_sources: list[SourceStat] = []
        total_snapshots = 0
        last_snapshot_ts: int | None = None
        strict_non_mock = 0
        strict_ready = 0
        missing_signal_source = 0

        if "dashboard_snapshots" in tables:
            snapshot_columns = table_columns(conn, "dashboard_snapshots")
            source_expr = (
                "COALESCE(NULLIF(signal_source, ''), 'unknown')"
                if "signal_source" in snapshot_columns
                else "'unknown'"
            )
            snapshot_sources = load_source_stats(conn, "dashboard_snapshots", source_expr)
            total_snapshots = sum(item.rows for item in snapshot_sources)
            last_snapshot_ts = max((item.last_ts or 0) for item in snapshot_sources) or None
            if "signal_source" in snapshot_columns:
                missing_signal_source = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM dashboard_snapshots WHERE COALESCE(signal_source, '') = ''"
                    ).fetchone()[0]
                )
                strict_non_mock = int(
                    conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM dashboard_snapshots
                        WHERE COALESCE(signal_source, '') NOT IN ('', 'mock')
                        """
                    ).fetchone()[0]
                )
                if "price_ticks" in tables:
                    strict_ready = int(
                        conn.execute(
                            """
                            SELECT COUNT(*)
                            FROM dashboard_snapshots ds
                            WHERE COALESCE(ds.signal_source, '') NOT IN ('', 'mock')
                              AND EXISTS (
                                SELECT 1
                                FROM price_ticks pt
                                WHERE pt.ticker = ds.ticker
                                  AND pt.source = ds.signal_source
                                  AND pt.ts > ds.ts
                                LIMIT 1
                              )
                            """
                        ).fetchone()[0]
                    )

        price_sources: list[SourceStat] = []
        total_price_ticks = 0
        last_price_ts: int | None = None
        if "price_ticks" in tables:
            price_sources = load_source_stats(
                conn,
                "price_ticks",
                "COALESCE(NULLIF(source, ''), 'unknown')",
            )
            total_price_ticks = sum(item.rows for item in price_sources)
            last_price_ts = max((item.last_ts or 0) for item in price_sources) or None

        total_events = int(
            conn.execute("SELECT COUNT(*) FROM event_factors").fetchone()[0]
            if "event_factors" in tables
            else 0
        )
        total_macro = int(
            conn.execute("SELECT COUNT(*) FROM macro_snapshots").fetchone()[0]
            if "macro_snapshots" in tables
            else 0
        )
        last_macro_ts = (
            int(conn.execute("SELECT MAX(ts) FROM macro_snapshots").fetchone()[0])
            if "macro_snapshots" in tables and conn.execute("SELECT MAX(ts) FROM macro_snapshots").fetchone()[0] is not None
            else None
        )
        total_alerts = int(
            conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] if "alerts" in tables else 0
        )
        sent_alerts = int(
            conn.execute("SELECT COUNT(*) FROM alerts WHERE sent = 1").fetchone()[0]
            if "alerts" in tables
            else 0
        )

    return QualityInputs(
        tables=tables,
        snapshot_sources=snapshot_sources,
        price_sources=price_sources,
        total_snapshots=total_snapshots,
        total_price_ticks=total_price_ticks,
        total_events=total_events,
        total_macro=total_macro,
        total_alerts=total_alerts,
        sent_alerts=sent_alerts,
        last_snapshot_ts=last_snapshot_ts,
        last_price_ts=last_price_ts,
        last_macro_ts=last_macro_ts,
        strict_non_mock=strict_non_mock,
        strict_ready=strict_ready,
        missing_signal_source=missing_signal_source,
    )


def summarize(inputs: QualityInputs) -> QualitySummary:
    findings: list[str] = []
    recommendations: list[str] = []
    blocked = False
    warned = False

    if inputs.total_snapshots == 0:
        blocked = True
        findings.append("dashboard_snapshots가 비어 있습니다.")
        recommendations.append("알림 엔진을 live 기준으로 먼저 실행해 snapshot을 쌓으세요.")

    if inputs.total_price_ticks == 0:
        blocked = True
        findings.append("price_ticks가 비어 있습니다.")
        recommendations.append("가격 수집 경로가 살아 있는지 먼저 확인하세요.")

    if inputs.total_snapshots > 0:
        mock_rows = sum(item.rows for item in inputs.snapshot_sources if item.source == "mock")
        mock_ratio = mock_rows / inputs.total_snapshots
        if mock_ratio > MAX_MOCK_RATIO:
            warned = True
            findings.append(
                f"snapshot의 {fmt_pct(mock_ratio)}가 mock source입니다. 기준 {fmt_pct(MAX_MOCK_RATIO)}를 넘었습니다."
            )
            recommendations.append(
                "strict 백테스트는 non-mock 구간만 기준으로 해석하고 live source 비중을 더 올리세요."
            )

    if inputs.strict_non_mock == 0:
        blocked = True
        findings.append("non-mock snapshot이 아직 없습니다.")
        recommendations.append("dry-run 대신 live source로 누적을 시작하세요.")
    elif inputs.strict_ready / max(inputs.strict_non_mock, 1) < MIN_STRICT_READY_RATIO:
        warned = True
        findings.append(
            f"non-mock snapshot 대비 strict 가능률이 {fmt_pct(inputs.strict_ready / max(inputs.strict_non_mock, 1))}로 기준 {fmt_pct(MIN_STRICT_READY_RATIO)} 미만입니다."
        )
        recommendations.append("후속 price tick이 더 쌓일 때까지 readiness를 우선 보고 live 누적을 더 진행하세요.")

    if inputs.missing_signal_source > 0:
        warned = True
        findings.append(f"signal_source 미기록 snapshot이 {inputs.missing_signal_source}건 있습니다.")
        recommendations.append("backfill과 최신 notifier 실행으로 source 기록을 유지하세요.")

    if inputs.total_alerts > 0 and inputs.sent_alerts < inputs.total_alerts:
        warned = True
        findings.append("alerts 테이블 기준 미전송 알림이 일부 있습니다.")
        recommendations.append("텔레그램 토큰/채팅 ID와 쿨다운 정책을 같이 확인하세요.")

    if not findings:
        findings.append("치명적인 데이터 품질 문제는 현재 보이지 않습니다.")
        recommendations.append("readiness와 data quality를 같이 보면서 non-mock 표본을 계속 누적하세요.")

    verdict = "차단" if blocked else "주의" if warned else "양호"
    verdict_class = "blocked" if blocked else "warn" if warned else "good"
    return QualitySummary(
        verdict=verdict,
        verdict_class=verdict_class,
        findings=findings,
        recommendations=recommendations,
    )


def render_html(db_path: Path, inputs: QualityInputs, summary: QualitySummary) -> str:
    snapshot_rows_html = "".join(
        f"""
        <tr>
          <td>{esc(item.source)}</td>
          <td>{item.rows}</td>
          <td>{item.tickers}</td>
          <td>{fmt_ts(item.last_ts)}</td>
        </tr>
        """
        for item in inputs.snapshot_sources
    ) or "<tr><td colspan='4'>데이터 없음</td></tr>"

    price_rows_html = "".join(
        f"""
        <tr>
          <td>{esc(item.source)}</td>
          <td>{item.rows}</td>
          <td>{item.tickers}</td>
          <td>{fmt_ts(item.last_ts)}</td>
        </tr>
        """
        for item in inputs.price_sources
    ) or "<tr><td colspan='4'>데이터 없음</td></tr>"

    pipeline_rows_html = "".join(
        [
            f"<tr><td>snapshot</td><td>{inputs.total_snapshots}</td><td>{fmt_ts(inputs.last_snapshot_ts)}</td><td>signal_source 누락 {inputs.missing_signal_source}건</td></tr>",
            f"<tr><td>price_ticks</td><td>{inputs.total_price_ticks}</td><td>{fmt_ts(inputs.last_price_ts)}</td><td>non-mock strict 가능 {inputs.strict_ready}/{inputs.strict_non_mock}</td></tr>",
            f"<tr><td>event_factors</td><td>{inputs.total_events}</td><td>-</td><td>뉴스 이벤트 추출 결과</td></tr>",
            f"<tr><td>macro_snapshots</td><td>{inputs.total_macro}</td><td>{fmt_ts(inputs.last_macro_ts)}</td><td>매크로 스냅샷 저장</td></tr>",
            f"<tr><td>alerts</td><td>{inputs.total_alerts}</td><td>-</td><td>전송 성공 {inputs.sent_alerts}건</td></tr>",
        ]
    )

    findings_html = "".join(f"<li>{esc(item)}</li>" for item in summary.findings)
    recommendations_html = "".join(f"<li>{esc(item)}</li>" for item in summary.recommendations)
    strict_ratio = (
        inputs.strict_ready / inputs.strict_non_mock if inputs.strict_non_mock else 0.0
    )
    mock_rows = sum(item.rows for item in inputs.snapshot_sources if item.source == "mock")
    mock_ratio = (mock_rows / inputs.total_snapshots) if inputs.total_snapshots else 0.0
    extra_css = """
    .badge {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    .badge.good {
      color: var(--buy);
      background: rgba(21,94,99,0.10);
      border-color: rgba(21,94,99,0.18);
    }
    .badge.warn {
      color: var(--sell);
      background: rgba(180,83,9,0.10);
      border-color: rgba(180,83,9,0.18);
    }
    .badge.blocked {
      color: #8b1e3f;
      background: rgba(139,30,63,0.10);
      border-color: rgba(139,30,63,0.18);
    }
    """
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 데이터 품질</title>
  <style>
    {render_report_theme(extra_css)}
  </style>
</head>
<body>
  <main class="shell">
    {render_hero_section(
        "SIA Data<br>Quality",
        "이 리포트는 전략 수익률 이전에, 현재 DB가 믿고 읽을 수 있는 상태인지 점검합니다. 핵심은 mock 비중, non-mock strict 가능률, source 기록 상태입니다.",
        render_meta_row([
            f"DB: {esc(db_path)}",
            f"마지막 snapshot: {fmt_ts(inputs.last_snapshot_ts)}",
            f"마지막 price tick: {fmt_ts(inputs.last_price_ts)}",
        ]),
        render_stats_panel([
            ("판정", f"<span class='badge {summary.verdict_class}'>{summary.verdict}</span>"),
            ("snapshot", str(inputs.total_snapshots)),
            ("price_ticks", str(inputs.total_price_ticks)),
            ("strict 가능률", fmt_pct(strict_ratio)),
        ]),
    )}

    <section class="summary-grid">
      {render_summary_panel("핵심 진단", f"<p>{esc(summary.findings[0])}</p>")}
      {render_summary_panel("즉시 권장", f"<p>{esc(summary.recommendations[0])}</p>")}
      {render_summary_panel(
        "기준값",
        f"<p>mock 비중 경고 기준: {esc(fmt_pct(MAX_MOCK_RATIO))}<br>strict 가능률 최소 기준: {esc(fmt_pct(MIN_STRICT_READY_RATIO))}<br>현재 mock 비중: {esc(fmt_pct(mock_ratio))}</p>",
      )}
    </section>

    {render_table_section(
        "Snapshot source 분포",
        "dashboard_snapshots 기준 source별 분포입니다.",
        ["source", "행 수", "티커 수", "최근 시각"],
        snapshot_rows_html,
    )}

    {render_table_section(
        "Price tick source 분포",
        "price_ticks 기준 source별 분포입니다.",
        ["source", "행 수", "티커 수", "최근 시각"],
        price_rows_html,
    )}

    {render_table_section(
        "파이프라인 체크포인트",
        "운영 리포트 해석 전에 먼저 확인할 항목입니다.",
        ["체크포인트", "건수", "최근 시각", "메모"],
        pipeline_rows_html,
    )}

    {render_notes_section("발견 사항", findings_html)}
    {render_action_section("권장 액션", recommendations_html)}
  </main>
</body>
</html>"""


def write_report(db_path: Path, output_path: Path) -> Path:
    inputs = load_inputs(db_path)
    if not inputs.tables:
        output_path.write_text(build_empty_html("DB에 아직 테이블이 없습니다."), encoding="utf-8")
        return output_path
    summary = summarize(inputs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(db_path, inputs, summary), encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SIA data quality report from local sqlite data.")
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
