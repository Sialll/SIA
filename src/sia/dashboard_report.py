from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from sia.default_universe import merge_market_tickers, use_default_universe
from sia.market_runtime import load_enabled_markets, market_selection_summary, open_markets, selection_file_path
from sia.presentation import (
    css_root_block as presentation_css_root_block,
    event_type_class_name as presentation_event_type_class_name,
    event_type_display as presentation_event_type_display,
    macro_env_class_name as presentation_macro_env_class_name,
    macro_env_display as presentation_macro_env_display,
    reason_display as presentation_reason_display,
    risk_class_name as presentation_risk_class_name,
    risk_display as presentation_risk_display,
    score_delta_display as presentation_score_delta_display,
    score_display as presentation_score_display,
    score_value as presentation_score_value,
    signal_class_name as presentation_signal_class_name,
    signal_display as presentation_signal_display,
)
from sia.report_common import render_empty_report_html


report_path = Path(sys.argv[1])
db_path = Path(sys.argv[2]).expanduser()
report_path.parent.mkdir(parents=True, exist_ok=True)
cache_dir = report_path.parent
min_price_samples = os.getenv("SIA_MIN_PRICE_SAMPLES", "20").strip() or "20"
min_position_trades = os.getenv("SIA_MIN_POSITION_TRADES", "10").strip() or "10"
min_strict_aligned = os.getenv("SIA_MIN_STRICT_ALIGNED_SIGNALS", "8").strip() or "8"


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value))


def fmt_num(value: object, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def fmt_delta(value: object, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):+.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def fmt_score(value: object, digits: int = 1, suffix: str = "점") -> str:
    return presentation_score_display(value, digits=digits, suffix=suffix)


def fmt_score_raw(value: object, digits: int = 4) -> str:
    numeric = presentation_score_value(value)
    if numeric is None:
        return "-"
    return f"{numeric:.{digits}f}"


def fmt_score_delta(value: object, digits: int = 1, suffix: str = "점") -> str:
    return presentation_score_delta_display(value, digits=digits, suffix=suffix)


def fmt_ts(value: object) -> str:
    if value is None:
        return "-"
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return "-"
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def ticker_list_summary(raw: object, limit: int = 6) -> str:
    values = [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]
    if not values:
        return "없음"
    if len(values) <= limit:
        return ", ".join(values)
    return ", ".join(values[:limit]) + f" 외 {len(values) - limit}개"


def ticker_list_values(raw: object) -> list[str]:
    return [item.strip().upper() for item in str(raw or "").split(",") if item.strip()]


def signal_source_display(value: object) -> str:
    text = str(value or "").strip()
    return text if text else "-"


def strict_state(signal_source: object, future_ticks: object) -> tuple[str, str, bool]:
    source = signal_source_display(signal_source)
    try:
        count = int(future_ticks or 0)
    except (TypeError, ValueError):
        count = 0
    if source in {"-", "mock"}:
        return "엄격 기준 불가", "strict-wait", False
    if count > 0:
        return f"엄격 기준 가능 ({count}틱)", "strict-ready", True
    return "엄격 기준 대기 (0틱)", "strict-wait", False


def signal_class(signal: str) -> str:
    return presentation_signal_class_name(signal)


def signal_display(signal: object) -> str:
    return presentation_signal_display(signal)


def risk_class(risk: str) -> str:
    return presentation_risk_class_name(risk)


def risk_display(risk: object) -> str:
    return presentation_risk_display(risk)


def delta_class(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "delta-flat"
    if numeric > 0.005:
        return "delta-up"
    if numeric < -0.005:
        return "delta-down"
    return "delta-flat"


def macro_env_class(value: object) -> str:
    return presentation_macro_env_class_name(value)


def macro_env_display(value: object) -> str:
    return presentation_macro_env_display(value)


def event_type_class(value: object) -> str:
    return presentation_event_type_class_name(value)


def event_type_display(value: object) -> str:
    return presentation_event_type_display(value)


def reason_display(value: object) -> str:
    return presentation_reason_display(value)


def sparkline_svg(values: list[float], width: int = 240, height: int = 64, color: str = "#1f6f78") -> str:
    points = [float(value) for value in values if value is not None]
    if len(points) < 2:
        return (
            f"<svg viewBox='0 0 {width} {height}' class='sparkline' aria-hidden='true'>"
            f"<line x1='0' y1='{height - 10}' x2='{width}' y2='{height - 10}' stroke='rgba(23,20,17,0.14)' stroke-width='2' />"
            "</svg>"
        )
    low = min(points)
    high = max(points)
    span = high - low or 1.0
    step = width / max(len(points) - 1, 1)
    coords = []
    for index, value in enumerate(points):
        x = round(index * step, 2)
        y = round(height - 8 - (((value - low) / span) * (height - 16)), 2)
        coords.append(f"{x},{y}")
    area_coords = " ".join(["0," + str(height), *coords, f"{width},{height}"])
    line_coords = " ".join(coords)
    return (
        f"<svg viewBox='0 0 {width} {height}' class='sparkline' aria-hidden='true'>"
        f"<polyline points='{area_coords}' fill='rgba(31,111,120,0.10)' stroke='none' />"
        f"<polyline points='{line_coords}' fill='none' stroke='{color}' stroke-width='3' stroke-linecap='round' stroke-linejoin='round' />"
        f"<circle cx='{coords[-1].split(',')[0]}' cy='{coords[-1].split(',')[1]}' r='3.5' fill='{color}' />"
        "</svg>"
    )


def build_empty_html(message: str) -> str:
    return render_empty_report_html("SIA 메인", message)


def load_ticker_history(path: Path, limit: int = 8) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw = raw_line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return list(reversed(rows[-limit:]))


if not db_path.exists():
    report_path.write_text(build_empty_html(f"DB 파일이 없습니다: {db_path}"), encoding="utf-8")
    raise SystemExit(0)

with sqlite3.connect(str(db_path)) as conn:
    table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='dashboard_snapshots'"
    ).fetchone()
    if table_exists is None:
        report_path.write_text(build_empty_html("dashboard_snapshots 테이블이 없습니다. 먼저 notifier를 1회 실행하세요."), encoding="utf-8")
        raise SystemExit(0)

    snapshot_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(dashboard_snapshots)").fetchall()
    }
    price_ticks_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='price_ticks'"
    ).fetchone() is not None
    signal_source_expr = "COALESCE(signal_source, '') AS signal_source" if "signal_source" in snapshot_columns else "'' AS signal_source"
    strict_future_ticks_expr = (
        "CASE "
        "WHEN COALESCE(signal_source, '') <> '' AND signal_source <> 'mock' THEN ("
        "SELECT COUNT(1) FROM price_ticks pt "
        "WHERE pt.ticker = dashboard_snapshots.ticker "
        "AND pt.source = dashboard_snapshots.signal_source "
        "AND pt.ts > dashboard_snapshots.ts"
        ") ELSE 0 END AS strict_future_ticks"
        if "signal_source" in snapshot_columns and price_ticks_exists
        else "0 AS strict_future_ticks"
    )

    rows = conn.execute(
        f"""
        SELECT
            ts, ticker, signal, confidence, price, sma_fast, sma_slow, rsi,
            chart_score, macro_score, event_score, news_score, composite_score,
            risk_level, momentum, macro_environment, reason, news_json, event_factors_json,
            {signal_source_expr}, {strict_future_ticks_expr}
        FROM dashboard_snapshots
        ORDER BY id DESC
        LIMIT 200
        """
    ).fetchall()
    alerts_table_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='alerts'"
    ).fetchone()
    alert_rows = []
    if alerts_table_exists is not None:
        alert_rows = conn.execute(
            """
            SELECT ts, ticker, signal, confidence, reason, sent
            FROM alerts
            ORDER BY id DESC
            LIMIT 300
            """
        ).fetchall()

if not rows:
    report_path.write_text(build_empty_html("저장된 스냅샷이 없습니다. notifier를 먼저 실행하세요."), encoding="utf-8")
    raise SystemExit(0)

columns = [
    "ts", "ticker", "signal", "confidence", "price", "sma_fast", "sma_slow", "rsi",
    "chart_score", "macro_score", "event_score", "news_score", "composite_score",
    "risk_level", "momentum", "macro_environment", "reason", "news_json", "event_factors_json",
    "signal_source", "strict_future_ticks",
]
items = [dict(zip(columns, row)) for row in rows]
alerts_by_ticker: dict[str, list[dict]] = {}
for ts, ticker, signal, confidence, reason, sent in alert_rows:
    alerts_by_ticker.setdefault(ticker, []).append(
        {
            "ts": fmt_ts(ts),
            "signal": signal or "-",
            "confidence": fmt_score(confidence),
            "reason": reason or "-",
            "sent": "전송" if sent else "미전송",
        }
    )

latest_by_ticker: dict[str, dict] = {}
recent_snapshots_by_ticker: dict[str, list[dict]] = {}
price_history_by_ticker: dict[str, list[float]] = {}
for item in items:
    latest_by_ticker.setdefault(item["ticker"], item)
    snapshots = recent_snapshots_by_ticker.setdefault(item["ticker"], [])
    if len(snapshots) < 2:
        snapshots.append(item)
    try:
        price_history_by_ticker.setdefault(item["ticker"], []).append(float(item["price"]))
    except (TypeError, ValueError):
        continue

for ticker, series in price_history_by_ticker.items():
    price_history_by_ticker[ticker] = list(reversed(series[-24:]))

score_delta_by_ticker: dict[str, dict[str, float | None]] = {}
for ticker, snapshots in recent_snapshots_by_ticker.items():
    if len(snapshots) >= 2:
        latest_item, previous_item = snapshots[0], snapshots[1]
        try:
            composite_delta = float(latest_item["composite_score"]) - float(previous_item["composite_score"])
        except (TypeError, ValueError):
            composite_delta = None
        try:
            confidence_delta = float(latest_item["confidence"]) - float(previous_item["confidence"])
        except (TypeError, ValueError):
            confidence_delta = None
    else:
        composite_delta = None
        confidence_delta = None
    score_delta_by_ticker[ticker] = {
        "composite": composite_delta,
        "confidence": confidence_delta,
    }

all_cards = list(latest_by_ticker.values())
all_cards.sort(key=lambda item: (item["signal"] != "BUY", -float(item["confidence"])))

cards: list[dict] = []
visible_snapshot_items: list[dict] = []
initial_source = "-"
initial_strict_label = "strict 불가"
initial_strict_class = "strict-wait"
buy_count = 0
sell_count = 0
hold_count = 0
avg_confidence = 0.0
last_updated = "없음"
def launchd_service_status(label: str) -> tuple[str, str]:
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return "확인 불가", "warn"
    if result.returncode != 0:
        return "미설치", "warn"
    text = result.stdout or ""
    exit_match = re.search(r"last exit code = (\d+)", text)
    exit_code = exit_match.group(1) if exit_match else None
    suffix = f" (exit {exit_code})" if exit_code is not None else ""
    if "state = running" in text:
        return f"실행 중{suffix}", "ok"
    if "state = not running" in text:
        tone = "ok" if exit_code in {None, '0'} else "warn"
        return f"대기 중{suffix}", tone
    return "설치됨", "info"


telegram_ready = bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip() and os.getenv("TELEGRAM_CHAT_ID", "").strip())
ollama_disabled = os.getenv("SIA_NO_OLLAMA", "0").strip() == "1"
ollama_model = os.getenv("OLLAMA_MODEL", "").strip()
marketaux_ready = bool(os.getenv("MARKETAUX_API_KEY", "").strip())
finnhub_ready = bool(os.getenv("FINNHUB_API_KEY", "").strip())
live_mode = os.getenv("SIA_DRY_RUN", "1").strip() in {"0", "false", "False"}
enabled_markets = load_enabled_markets(selection_file_path())
currently_open_markets = open_markets(enabled_markets)
include_default_universe = use_default_universe(os.getenv("SIA_INCLUDE_DEFAULT_UNIVERSE", "1"))
market_ticker_values = {
    "US": list(
        merge_market_tickers(
            "US",
            ticker_list_values(os.getenv("TICKERS_US", os.getenv("TICKERS", ""))),
            include_default_universe=include_default_universe,
        )
    ),
    "KR": list(
        merge_market_tickers(
            "KR",
            ticker_list_values(os.getenv("TICKERS_KR", "")),
            include_default_universe=include_default_universe,
        )
    ),
    "EU": list(
        merge_market_tickers(
            "EU",
            ticker_list_values(os.getenv("TICKERS_EU", "")),
            include_default_universe=include_default_universe,
        )
    ),
    "JP": list(
        merge_market_tickers(
            "JP",
            ticker_list_values(os.getenv("TICKERS_JP", "")),
            include_default_universe=include_default_universe,
        )
    ),
}
tickers_us = ticker_list_summary(",".join(market_ticker_values["US"]))
tickers_kr = ticker_list_summary(",".join(market_ticker_values["KR"]))
tickers_eu = ticker_list_summary(",".join(market_ticker_values["EU"]))
tickers_jp = ticker_list_summary(",".join(market_ticker_values["JP"]))
active_watchlist_entries = [
    (market_code, ticker)
    for market_code in enabled_markets
    for ticker in market_ticker_values.get(market_code, [])
]
active_ticker_set = {ticker for _, ticker in active_watchlist_entries}
visible_snapshot_items = [item for item in items if item["ticker"] in active_ticker_set]
cards = [item for item in all_cards if item["ticker"] in active_ticker_set]
cards.sort(key=lambda item: (item["signal"] != "BUY", -float(item["confidence"])))
initial_card = (
    cards[0]
    if cards
    else {
        "ticker": "표시 없음",
        "signal": "HOLD",
        "ts": None,
        "confidence": None,
        "price": None,
        "sma_fast": None,
        "sma_slow": None,
        "rsi": None,
        "chart_score": None,
        "macro_score": None,
        "event_score": None,
        "news_score": None,
        "composite_score": None,
        "risk_level": "LOW",
        "momentum": "-",
        "macro_environment": "MIXED",
        "reason": "현재 관심 종목 중 메인에 표시할 최신 스냅샷이 없습니다.",
        "signal_source": "",
        "strict_future_ticks": 0,
    }
)
initial_source = signal_source_display(initial_card.get("signal_source"))
initial_strict_label, initial_strict_class, _ = strict_state(
    initial_card.get("signal_source"), initial_card.get("strict_future_ticks")
)
buy_count = sum(1 for item in cards if item["signal"] == "BUY")
sell_count = sum(1 for item in cards if item["signal"] == "SELL")
hold_count = sum(1 for item in cards if item["signal"] == "HOLD")
avg_confidence = sum(float(item["confidence"]) for item in cards) / max(len(cards), 1)
last_updated = fmt_ts(cards[0]["ts"]) if cards else "없음"
notifier_launchd, notifier_launchd_tone = launchd_service_status("com.sia.trading-signal-notifier")
refresh_launchd, refresh_launchd_tone = launchd_service_status("com.sia.backtest-refresh-nightly")
guard_launchd, guard_launchd_tone = launchd_service_status("com.sia.ready-buckets-guard")
backtest_report_paths = [
    cache_dir / "backtest-readiness-report.html",
    cache_dir / "price-backtest-report.html",
    cache_dir / "position-backtest-report.html",
    cache_dir / "factor-breakdown-report.html",
    cache_dir / "research-report.html",
]
dashboard_actions_url = os.getenv("SIA_DASHBOARD_ACTIONS_URL", "http://127.0.0.1:8765").strip() or "http://127.0.0.1:8765"
universe_snapshot_path = cache_dir / "universe-snapshot.json"
universe_report_path = cache_dir / "universe-report.html"
full_universe_snapshot_path = cache_dir / "full-universe-snapshot.json"
full_universe_report_path = cache_dir / "full-universe-report.html"
ticker_history_path = Path(os.path.expanduser(os.getenv("SIA_TICKER_HISTORY_PATH", "~/.config/sia-notifier/ticker-add-history.jsonl")))
us_open_check_report_path = cache_dir / "us-open-check-report.html"
existing_backtest_reports = [path for path in backtest_report_paths if path.exists()]
last_backtest_refresh = (
    fmt_ts(int(max(path.stat().st_mtime for path in existing_backtest_reports)))
    if existing_backtest_reports
    else "없음"
)
system_status_items = [
    ("DB 경로", str(db_path), "info"),
    ("캐시 경로", str(cache_dir), "info"),
    ("관심 종목 수", str(len(active_watchlist_entries)), "info"),
    ("메인 표시 종목", str(len(cards)), "info"),
    ("마지막 반영", last_updated, "info"),
    ("최근 엔진 실행", fmt_ts(items[0]["ts"]), "info"),
    ("최근 백테스트 갱신", last_backtest_refresh, "info"),
    (
        "유니버스 스냅샷",
        fmt_ts(int(universe_snapshot_path.stat().st_mtime)) if universe_snapshot_path.exists() else "없음",
        "ok" if universe_snapshot_path.exists() else "warn",
    ),
    (
        "관심 종목 구성표",
        fmt_ts(int(universe_report_path.stat().st_mtime)) if universe_report_path.exists() else "없음",
        "ok" if universe_report_path.exists() else "warn",
    ),
    (
        "전종목 유니버스 스냅샷",
        fmt_ts(int(full_universe_snapshot_path.stat().st_mtime)) if full_universe_snapshot_path.exists() else "없음",
        "ok" if full_universe_snapshot_path.exists() else "warn",
    ),
    (
        "시총 상위 종목 보고서",
        fmt_ts(int(full_universe_report_path.stat().st_mtime)) if full_universe_report_path.exists() else "없음",
        "ok" if full_universe_report_path.exists() else "warn",
    ),
    (
        "미국장 시작 점검",
        fmt_ts(int(us_open_check_report_path.stat().st_mtime)) if us_open_check_report_path.exists() else "없음",
        "ok" if us_open_check_report_path.exists() else "info",
    ),
    ("실행 모드", "실전" if live_mode else "드라이런", "ok" if live_mode else "warn"),
    ("기본 유니버스", "사용" if include_default_universe else "해제", "ok" if include_default_universe else "warn"),
    ("활성 시장", market_selection_summary(enabled_markets), "ok" if enabled_markets else "warn"),
    ("현재 열린 시장", market_selection_summary(currently_open_markets), "ok" if currently_open_markets else "info"),
    ("시장 설정 파일", selection_file_path(), "info"),
    ("미국 티커", tickers_us, "ok" if "US" in enabled_markets and tickers_us != "없음" else "warn" if "US" in enabled_markets else "info"),
    ("한국 티커", tickers_kr, "ok" if "KR" in enabled_markets and tickers_kr != "없음" else "warn" if "KR" in enabled_markets else "info"),
    ("유럽 티커", tickers_eu, "ok" if "EU" in enabled_markets and tickers_eu != "없음" else "warn" if "EU" in enabled_markets else "info"),
    ("일본 티커", tickers_jp, "ok" if "JP" in enabled_markets and tickers_jp != "없음" else "warn" if "JP" in enabled_markets else "info"),
    ("텔레그램", "설정됨" if telegram_ready else "미설정", "ok" if telegram_ready else "warn"),
    ("뉴스 소스", "Marketaux + Yahoo" if marketaux_ready else "Yahoo RSS 무료", "ok" if marketaux_ready else "info"),
    ("가격 소스", "Finnhub + Yahoo" if finnhub_ready else "Yahoo 무료", "ok" if finnhub_ready else "info"),
    ("로컬 LLM", "비활성" if ollama_disabled or not ollama_model else ollama_model, "warn" if ollama_disabled or not ollama_model else "ok"),
    ("알림 엔진 launchd", notifier_launchd, notifier_launchd_tone),
    ("야간 백테스트 launchd", refresh_launchd, refresh_launchd_tone),
    ("준비도 가드 launchd", guard_launchd, guard_launchd_tone),
]
status_tone_meta = {
    "ok": ("정상", "현재 사용 가능한 상태입니다."),
    "warn": ("주의", "설정 누락 또는 비활성 상태입니다."),
    "info": ("정보", "참고용 상태 정보입니다."),
}
system_status_html = "".join(
    f"""
    <div class="status-item status-{tone}">
      <div class="label">{esc(label)} <span class="tone-badge tone-{tone}" title="{esc(status_tone_meta[tone][1])}">{esc(status_tone_meta[tone][0])}</span></div>
      <div class="value">{esc(value)}</div>
    </div>
    """
    for label, value, tone in system_status_items
)

market_cards_html = []
market_warnings: list[str] = []
for market_code, market_name in (("US", "미국"), ("KR", "한국"), ("EU", "유럽"), ("JP", "일본")):
    ticker_values = market_ticker_values.get(market_code, [])
    ticker_count = len(ticker_values)
    enabled = market_code in enabled_markets
    opened = market_code in currently_open_markets
    if enabled and ticker_count == 0:
        tone = "warn"
        status_text = "활성인데 티커 없음"
        market_warnings.append(f"{market_name} 시장이 활성 상태지만 티커가 비어 있습니다.")
    elif enabled and opened:
        tone = "ok"
        status_text = "활성 / 장중"
    elif enabled:
        tone = "info"
        status_text = "활성 / 휴장"
    else:
        tone = "muted"
        status_text = "비활성"
    sample_text = ticker_list_summary(",".join(ticker_values), limit=4)
    market_cards_html.append(
        f"""
        <article class="market-card market-{tone}">
          <div class="market-head">
            <h3>{esc(market_name)}</h3>
            <span class="market-state state-{tone}">{esc(status_text)}</span>
          </div>
          <div class="market-count">{ticker_count}개</div>
          <p class="market-sample">{esc(sample_text)}</p>
        </article>
        """
    )
market_warning_html = ""
if market_warnings:
    warning_text = " / ".join(market_warnings)
    market_warning_html = f"<div class='market-warning'>{esc(warning_text)}</div>"

coverage_total = len(active_watchlist_entries)
coverage_visible = len(cards)
coverage_missing = max(coverage_total - coverage_visible, 0)
coverage_ratio = (coverage_visible / coverage_total * 100.0) if coverage_total else 0.0
coverage_tone = "ok" if coverage_total and coverage_visible == coverage_total else "warn" if coverage_total else "info"
coverage_status_html = "".join(
    [
        f"""
        <div class="status-item status-{coverage_tone}">
          <div class="label">메인 반영률 <span class="tone-badge tone-{coverage_tone}">{fmt_num(coverage_ratio, 1)}%</span></div>
          <div class="value">{coverage_visible} / {coverage_total}</div>
        </div>
        """,
        f"""
        <div class="status-item status-{'warn' if coverage_missing else 'ok'}">
          <div class="label">아직 안 보이는 종목 <span class="tone-badge tone-{'warn' if coverage_missing else 'ok'}">{coverage_missing}개</span></div>
          <div class="value">{'아래 점검 영역에서 바로 확인' if coverage_missing else '현재 관심 종목이 모두 메인에 반영됨'}</div>
        </div>
        """,
        f"""
        <div class="status-item status-{'ok' if currently_open_markets else 'info'}">
          <div class="label">현재 열린 시장 <span class="tone-badge tone-{'ok' if currently_open_markets else 'info'}">{market_selection_summary(currently_open_markets) or '없음'}</span></div>
          <div class="value">{'장중에는 15분 주기로 자동 반영' if currently_open_markets else '장 시작 후 메인이 자동 갱신됩니다.'}</div>
        </div>
        """,
        f"""
        <div class="status-item status-info">
          <div class="label">현재 관심 종목</div>
          <div class="value">{esc(', '.join(ticker for _, ticker in active_watchlist_entries[:10]) + (f' 외 {coverage_total - 10}개' if coverage_total > 10 else '') if coverage_total else '없음')}</div>
        </div>
        """,
    ]
)

missing_watchlist_items: list[tuple[str, str, str]] = []
for market_code, ticker in active_watchlist_entries:
    if ticker in latest_by_ticker:
        continue
    if market_code not in currently_open_markets:
        reason = "시장 휴장"
    else:
        reason = "최신 스냅샷 대기"
    missing_watchlist_items.append((market_code, ticker, reason))

missing_watchlist_html = ""
if missing_watchlist_items:
    missing_watchlist_html = "".join(
        f"""
        <div class="status-item status-warn">
          <div class="label">{esc(ticker)} <span class="tone-badge tone-warn">{esc(market_code)}</span></div>
          <div class="value">{esc(reason)}</div>
        </div>
        """
        for market_code, ticker, reason in missing_watchlist_items[:24]
    )
else:
    missing_watchlist_html = """
    <div class="status-item status-ok">
      <div class="label">누락 종목 없음 <span class="tone-badge tone-ok">정상</span></div>
      <div class="value">현재 활성 관심 종목은 모두 메인에 반영되어 있습니다.</div>
    </div>
    """

recent_ticker_history = load_ticker_history(ticker_history_path)
market_name_labels = {"US": "미국", "KR": "한국", "EU": "유럽", "JP": "일본"}
last_bulk_set_entry = next((entry for entry in recent_ticker_history if entry.get("mode") == "bulk_set_market"), None)
if last_bulk_set_entry:
    last_bulk_market = str(last_bulk_set_entry.get("target_market") or "-").upper()
    last_bulk_market_label = market_name_labels.get(last_bulk_market, last_bulk_market)
    last_bulk_items = [
        str(item.get("ticker", "")).upper()
        for item in (last_bulk_set_entry.get("items") or [])
        if isinstance(item, dict) and str(item.get("ticker", "")).strip()
    ]
    last_bulk_preview = ", ".join(last_bulk_items[:8]) + (f" 외 {len(last_bulk_items) - 8}개" if len(last_bulk_items) > 8 else "")
    last_bulk_set_html = (
        f"최근 마지막 일괄 붙여넣기: {esc(last_bulk_market_label)} / {esc(fmt_ts(last_bulk_set_entry.get('ts')))}"
        + (f" / {esc(last_bulk_preview)}" if last_bulk_preview else "")
    )
else:
    last_bulk_set_html = "최근 마지막 일괄 붙여넣기 기록이 없습니다."
last_quick_add_entry = next((entry for entry in recent_ticker_history if entry.get("mode") == "quick_add"), None)
if last_quick_add_entry:
    quick_add_items = [
        f"{market_name_labels.get(str(item.get('market', '-')).upper(), str(item.get('market', '-')).upper())}:{str(item.get('ticker', '-')).upper()}"
        for item in (last_quick_add_entry.get("items") or [])
        if isinstance(item, dict)
    ]
    quick_add_value = ", ".join(quick_add_items) if quick_add_items else str(last_quick_add_entry.get("input") or "-")
    last_quick_add_html = f"최근 마지막 빠른 추가: {esc(fmt_ts(last_quick_add_entry.get('ts')))} / {esc(quick_add_value)}"
else:
    last_quick_add_html = "최근 마지막 빠른 추가 기록이 없습니다."
last_quick_remove_entry = next((entry for entry in recent_ticker_history if entry.get("mode") == "quick_remove"), None)
if last_quick_remove_entry:
    quick_remove_items = [
        f"{market_name_labels.get(str(item.get('market', '-')).upper(), str(item.get('market', '-')).upper())}:{str(item.get('ticker', '-')).upper()}"
        for item in (last_quick_remove_entry.get("items") or [])
        if isinstance(item, dict)
    ]
    quick_remove_value = ", ".join(quick_remove_items) if quick_remove_items else str(last_quick_remove_entry.get("input") or "-")
    last_quick_remove_html = f"최근 마지막 빠른 삭제: {esc(fmt_ts(last_quick_remove_entry.get('ts')))} / {esc(quick_remove_value)}"
else:
    last_quick_remove_html = "최근 마지막 빠른 삭제 기록이 없습니다."
recent_ticker_history_html_parts: list[str] = []
for entry in recent_ticker_history:
    if entry.get("mode") == "quick_add":
        items = [
            f"{market_name_map}:{ticker_name}"
            for market_name_map, ticker_name in [
                (str(item.get("market", "-")), str(item.get("ticker", "-")))
                for item in (entry.get("items") or [])
                if isinstance(item, dict)
            ]
        ]
        title = "빠른 추가"
        value = ", ".join(items) if items else str(entry.get("input") or "-")
    elif entry.get("mode") == "quick_remove":
        items = [
            f"{market_name_map}:{ticker_name}"
            for market_name_map, ticker_name in [
                (str(item.get("market", "-")), str(item.get("ticker", "-")))
                for item in (entry.get("items") or [])
                if isinstance(item, dict)
            ]
        ]
        title = "빠른 삭제"
        value = ", ".join(items) if items else str(entry.get("input") or "-")
    elif entry.get("mode") == "bulk_set_market":
        target_market = str(entry.get("target_market") or "-").upper()
        title = f"{market_name_labels.get(target_market, target_market)} 일괄 설정"
        items = [
            str(item.get("ticker", "")).upper()
            for item in (entry.get("items") or [])
            if isinstance(item, dict) and str(item.get("ticker", "")).strip()
        ]
        value = ", ".join(items[:8]) + (f" 외 {len(items) - 8}개" if len(items) > 8 else "") if items else "입력 없음"
    else:
        by_market = entry.get("by_market") or {}
        items = []
        for market_code in ("US", "KR", "EU", "JP"):
            tickers = by_market.get(market_code) or []
            if tickers:
                items.append(f"{market_code}:{', '.join(str(t).upper() for t in tickers[:4])}{' 외 ' + str(len(tickers) - 4) + '개' if len(tickers) > 4 else ''}")
        title = "전체 수정"
        value = " / ".join(items) if items else "입력 없음"
    recent_ticker_history_html_parts.append(
        f"""
        <div class="status-item status-info">
          <div class="label">{esc(title)} <span class="tone-badge tone-info">{esc(fmt_ts(entry.get('ts')))}</span></div>
          <div class="value">{esc(value)}</div>
        </div>
        """
    )
recent_ticker_history_html = "".join(recent_ticker_history_html_parts) or """
<div class="status-item status-info">
  <div class="label">최근 추가 기록 없음 <span class="tone-badge tone-info">정보</span></div>
  <div class="value">지금부터 빠른 추가 또는 전체 수정으로 바꾼 기록이 여기에 누적됩니다.</div>
</div>
"""

offline_cards_html_parts: list[str] = []
offline_snapshot_ts_values: list[int] = []
offline_scored_count = 0
for market_code, ticker in active_watchlist_entries:
    market_label = market_name_labels.get(market_code, market_code)
    item = latest_by_ticker.get(ticker)
    if item:
        offline_scored_count += 1
        try:
            if item.get("ts") is not None:
                offline_snapshot_ts_values.append(int(item["ts"]))
        except (TypeError, ValueError):
            pass
        signal_source = signal_source_display(item.get("signal_source"))
        strict_label, strict_class_name, _strict_eligible = strict_state(
            item.get("signal_source"), item.get("strict_future_ticks")
        )
        reason_text = reason_display(item.get("reason"))
        reason_preview = reason_text if len(reason_text) <= 120 else reason_text[:117] + "..."
        offline_cards_html_parts.append(
            f"""
            <article class="card offline-card">
              <div class="card-head">
                <div>
                  <div class="ticker">{esc(ticker)}</div>
                  <div class="sub">{esc(market_label)} · 마지막 저장 {esc(fmt_ts(item.get("ts")))}</div>
                </div>
                <span class="badge {signal_class(item['signal'])}">{esc(signal_display(item["signal"]))}</span>
              </div>
              <div class="score-line">
                <strong>{fmt_score(item["composite_score"])}</strong>
                <span>신뢰도 {fmt_score(item["confidence"])}</span>
              </div>
              <div class="status-line">
                <span class="macro-pill {macro_env_class(item['macro_environment'])}">{esc(macro_env_display(item["macro_environment"]))}</span>
                <span class="delta {risk_class(item['risk_level'])}">{esc(risk_display(item["risk_level"]))}</span>
                <span class="strict-chip {esc(strict_class_name)}">{esc(strict_label)}</span>
              </div>
              <p class="offline-reason">{esc(reason_preview)}</p>
              <div class="offline-meta">
                <span>소스 {esc(signal_source)}</span>
                <span>가격 {esc(fmt_num(item.get("price")))}</span>
                <span>모멘텀 {esc(item.get("momentum") or "-")}</span>
              </div>
            </article>
            """
        )
        continue
    pending_reason = "장이 열리면 첫 저장 점수가 생성됩니다." if market_code in currently_open_markets else "시장 휴장 중이라 마지막 저장 점수가 없습니다."
    offline_cards_html_parts.append(
        f"""
        <article class="card offline-card offline-card-empty">
          <div class="card-head">
            <div>
              <div class="ticker">{esc(ticker)}</div>
              <div class="sub">{esc(market_label)} · 저장 점수 없음</div>
            </div>
            <span class="badge hold">대기</span>
          </div>
          <div class="score-line">
            <strong>-</strong>
            <span>마지막 저장 없음</span>
          </div>
          <p class="offline-reason">{esc(pending_reason)}</p>
          <div class="offline-meta">
            <span>상태 {esc('장중 대기' if market_code in currently_open_markets else '시장 휴장')}</span>
          </div>
        </article>
        """
    )

offline_last_updated = fmt_ts(max(offline_snapshot_ts_values)) if offline_snapshot_ts_values else "없음"
offline_missing_count = max(len(active_watchlist_entries) - offline_scored_count, 0)
offline_status_html = "".join(
    [
        f"""
        <div class="status-item status-info">
          <div class="label">관심 종목 수 <span class="tone-badge tone-info">정보</span></div>
          <div class="value">{len(active_watchlist_entries)}개</div>
        </div>
        """,
        f"""
        <div class="status-item status-{'ok' if offline_scored_count else 'warn'}">
          <div class="label">저장된 점수 <span class="tone-badge tone-{'ok' if offline_scored_count else 'warn'}">{offline_scored_count}개</span></div>
          <div class="value">마지막 저장 스냅샷 기준으로 보여줍니다.</div>
        </div>
        """,
        f"""
        <div class="status-item status-{'warn' if offline_missing_count else 'ok'}">
          <div class="label">저장 대기 <span class="tone-badge tone-{'warn' if offline_missing_count else 'ok'}">{offline_missing_count}개</span></div>
          <div class="value">{'아직 저장 점수가 없는 종목이 있습니다.' if offline_missing_count else '현재 관심 종목 모두 저장 점수가 있습니다.'}</div>
        </div>
        """,
        f"""
        <div class="status-item status-info">
          <div class="label">최근 저장 시각 <span class="tone-badge tone-info">정보</span></div>
          <div class="value">{esc(offline_last_updated)}</div>
        </div>
        """,
    ]
)
offline_cards_html = "".join(offline_cards_html_parts) or """
<div class="empty-card">
  <strong>오프라인 점수 없음</strong>
  <p>현재 관심 종목 기준 마지막 저장 스냅샷이 없습니다.</p>
</div>
"""

card_html = []
for item in cards:
    news = json.loads(item["news_json"] or "[]")
    events = json.loads(item["event_factors_json"] or "[]")
    signal_source = signal_source_display(item.get("signal_source"))
    strict_label, strict_class_name, strict_eligible = strict_state(
        item.get("signal_source"), item.get("strict_future_ticks")
    )
    top_news = news[0]["title"] if news else "최근 뉴스 없음"
    top_news_url = str(news[0].get("link") or news[0].get("url") or "").strip() if news else ""
    price_history = price_history_by_ticker.get(item["ticker"], [])
    score_delta = score_delta_by_ticker.get(item["ticker"], {})
    composite_delta = score_delta.get("composite")
    confidence_delta = score_delta.get("confidence")
    event_types = ",".join(
        sorted(
            {
                str(event.get("event_type") or "").strip().lower()
                for event in events
                if str(event.get("event_type") or "").strip()
            }
        )
    )
    sparkline = sparkline_svg(price_history)
    search_blob = " ".join(
        [
            str(item["ticker"]),
            str(item["signal"]),
            str(item["risk_level"]),
            str(item["momentum"]),
            str(item["macro_environment"]),
            signal_source,
            strict_label,
            str(top_news),
            str(item["reason"]),
        ]
    ).lower()
    macro_badge = (
        f"<span class='macro-pill {macro_env_class(item['macro_environment'])}'>"
        f"{esc(macro_env_display(item['macro_environment'] or 'MIXED'))}"
        "</span>"
    )
    source_badge = f"<span class='micro-chip source-chip'>소스 {esc(signal_source)}</span>"
    strict_badge = f"<span class='micro-chip {strict_class_name}'>{esc(strict_label)}</span>"
    event_badges = "".join(
        f"<span class='event {event_type_class(event.get('event_type'))}'>{esc(event_type_display(event.get('event_type', '-')))} {fmt_num(event.get('sentiment'), 2)}</span>"
        for event in events[:3]
    ) or "<span class='event empty'>이벤트 없음</span>"
    detail_payload = json.dumps(
        {
            "ticker": item["ticker"],
            "signal": item["signal"],
            "ts": fmt_ts(item["ts"]),
            "confidence": fmt_score(item["confidence"]),
            "price": fmt_num(item["price"]),
            "sma_fast": fmt_num(item["sma_fast"]),
            "sma_slow": fmt_num(item["sma_slow"]),
            "rsi": fmt_num(item["rsi"]),
            "chart_score": fmt_score(item["chart_score"]),
            "macro_score": fmt_score(item["macro_score"]),
            "event_score": fmt_score(item["event_score"]),
            "news_score": fmt_score(item["news_score"]),
            "composite_score": fmt_score(item["composite_score"]),
            "risk_level": item["risk_level"] or "-",
            "momentum": item["momentum"] or "-",
            "macro_environment": item["macro_environment"] or "-",
            "signal_source": signal_source,
            "strict_label": strict_label,
            "strict_eligible": strict_eligible,
            "strict_future_ticks": int(item.get("strict_future_ticks") or 0),
            "reason": reason_display(item["reason"] or "-"),
            "headline": top_news,
            "price_history": price_history,
            "composite_delta": fmt_score_delta(composite_delta),
            "confidence_delta": fmt_score_delta(confidence_delta),
            "news": news[:5],
            "events": events[:5],
            "alerts": alerts_by_ticker.get(item["ticker"], [])[:5],
        },
        ensure_ascii=False,
    )
    card_html.append(
        f"""
        <article
          class="card"
          data-ticker="{esc(item['ticker'])}"
          data-signal="{esc(item['signal'])}"
          data-risk="{esc(item['risk_level'])}"
          data-macro-env="{esc(item['macro_environment'])}"
          data-has-events="{'1' if events else '0'}"
          data-event-types="{esc(event_types)}"
          data-confidence="{fmt_score_raw(item['confidence'])}"
          data-composite="{fmt_score_raw(item['composite_score'])}"
          data-composite-delta="{fmt_score_raw(composite_delta)}"
          data-confidence-delta="{fmt_score_raw(confidence_delta)}"
          data-ts="{esc(item['ts'])}"
          data-source="{esc(signal_source)}"
          data-strict-eligible="{'1' if strict_eligible else '0'}"
          data-strict-future-ticks="{int(item.get('strict_future_ticks') or 0)}"
          data-search="{esc(search_blob)}"
          data-detail="{esc(detail_payload)}"
        >
          <div class="card-head">
            <div>
              <div class="ticker">{esc(item['ticker'])}</div>
              <div class="sub">{fmt_ts(item['ts'])}</div>
            </div>
            <div class="badge {signal_class(item['signal'])}">{esc(signal_display(item['signal']))}</div>
          </div>
          <div class="score-line">
            <strong>{fmt_score(item['composite_score'])}</strong>
            <span>종합 점수</span>
            <span class="risk {risk_class(item['risk_level'])}">{esc(risk_display(item['risk_level']))}</span>
          </div>
          <div class="delta-line">
            <span class="delta {delta_class(composite_delta)}">최근 점수 {fmt_score_delta(composite_delta)}</span>
            <span class="delta {delta_class(confidence_delta)}">신뢰도 {fmt_score_delta(confidence_delta)}</span>
          </div>
          <div class="status-line">
            {macro_badge}
            <span class="status-label">이벤트</span>
          </div>
          <dl class="metrics">
            <div><dt>가격</dt><dd>{fmt_num(item['price'])}</dd></div>
            <div><dt>신뢰도</dt><dd>{fmt_score(item['confidence'])}</dd></div>
            <div><dt>모멘텀</dt><dd>{esc(item['momentum'])}</dd></div>
            <div><dt>매크로</dt><dd>{esc(macro_env_display(item['macro_environment']))}</dd></div>
          </dl>
          <div class="sparkline-wrap">
            <div class="sparkline-meta">
              <span>최근 가격 흐름</span>
              <span>{fmt_num(price_history[0]) if price_history else '-'} → {fmt_num(price_history[-1]) if price_history else '-'}</span>
            </div>
            {sparkline}
          </div>
          <div class="mini-bars">
            <span>차트 {fmt_score(item['chart_score'])}</span>
            <span>매크로 {fmt_score(item['macro_score'])}</span>
            <span>이벤트 {fmt_score(item['event_score'])}</span>
            <span>뉴스 {fmt_score(item['news_score'])}</span>
          </div>
          <div class="micro-meta">{source_badge}{strict_badge}</div>
          {"<a class='headline headline-link' href='" + esc(top_news_url) + "' target='_blank' rel='noreferrer'>" + esc(top_news) + "</a>" if top_news_url else "<p class='headline'>" + esc(top_news) + "</p>"}
          <div class="events">{event_badges}</div>
          <p class="reason">{esc(reason_display(item['reason']))}</p>
        </article>
        """
    )

table_rows = []
for item in visible_snapshot_items[:30]:
    news = json.loads(item["news_json"] or "[]")
    events = json.loads(item["event_factors_json"] or "[]")
    signal_source = signal_source_display(item.get("signal_source"))
    strict_label, _, strict_eligible = strict_state(
        item.get("signal_source"), item.get("strict_future_ticks")
    )
    top_news = news[0]["title"] if news else "최근 뉴스 없음"
    event_types = ",".join(
        sorted(
            {
                str(event.get("event_type") or "").strip().lower()
                for event in events
                if str(event.get("event_type") or "").strip()
            }
        )
    )
    row_search_blob = " ".join(
        [
            str(item["ticker"]),
            str(item["signal"]),
            str(item["risk_level"]),
            str(item["momentum"]),
            str(item["macro_environment"]),
            signal_source,
            strict_label,
            str(top_news),
            str(item["reason"]),
        ]
    ).lower()
    detail_payload = json.dumps(
        {
            "ticker": item["ticker"],
            "signal": item["signal"],
            "ts": fmt_ts(item["ts"]),
            "confidence": fmt_score(item["confidence"]),
            "price": fmt_num(item["price"]),
            "sma_fast": fmt_num(item["sma_fast"]),
            "sma_slow": fmt_num(item["sma_slow"]),
            "rsi": fmt_num(item["rsi"]),
            "chart_score": fmt_score(item["chart_score"]),
            "macro_score": fmt_score(item["macro_score"]),
            "event_score": fmt_score(item["event_score"]),
            "news_score": fmt_score(item["news_score"]),
            "composite_score": fmt_score(item["composite_score"]),
            "risk_level": item["risk_level"] or "-",
            "momentum": item["momentum"] or "-",
            "macro_environment": item["macro_environment"] or "-",
            "signal_source": signal_source,
            "strict_label": strict_label,
            "strict_eligible": strict_eligible,
            "strict_future_ticks": int(item.get("strict_future_ticks") or 0),
            "reason": reason_display(item["reason"] or "-"),
            "headline": top_news,
            "composite_delta": fmt_score_delta(score_delta_by_ticker.get(item["ticker"], {}).get("composite")),
            "confidence_delta": fmt_score_delta(score_delta_by_ticker.get(item["ticker"], {}).get("confidence")),
            "news": news[:5],
            "events": events[:5],
            "alerts": alerts_by_ticker.get(item["ticker"], [])[:5],
        },
        ensure_ascii=False,
    )
    table_rows.append(
        f"""
        <tr
          data-ticker="{esc(item['ticker'])}"
          data-signal="{esc(item['signal'])}"
          data-risk="{esc(item['risk_level'])}"
          data-macro-env="{esc(item['macro_environment'])}"
          data-has-events="{'1' if events else '0'}"
          data-event-types="{esc(event_types)}"
          data-confidence="{fmt_score_raw(item['confidence'])}"
          data-composite="{fmt_score_raw(item['composite_score'])}"
          data-composite-delta="{fmt_score_raw(score_delta_by_ticker.get(item['ticker'], {}).get('composite'))}"
          data-confidence-delta="{fmt_score_raw(score_delta_by_ticker.get(item['ticker'], {}).get('confidence'))}"
          data-ts="{esc(item['ts'])}"
          data-source="{esc(signal_source)}"
          data-strict-eligible="{'1' if strict_eligible else '0'}"
          data-strict-future-ticks="{int(item.get('strict_future_ticks') or 0)}"
          data-search="{esc(row_search_blob)}"
          data-detail="{esc(detail_payload)}"
        >
          <td>{fmt_ts(item['ts'])}</td>
          <td>{esc(item['ticker'])}</td>
          <td><span class="badge {signal_class(item['signal'])}">{esc(signal_display(item['signal']))}</span></td>
          <td>{fmt_score(item['confidence'])}</td>
          <td>{fmt_score(item['composite_score'])}</td>
          <td>{esc(risk_display(item['risk_level']))}</td>
          <td>{esc(item['momentum'])}</td>
          <td>{esc(macro_env_display(item['macro_environment']))}</td>
          <td>{esc(signal_source)}</td>
          <td><span class="strict-chip {'strict-ready' if strict_eligible else 'strict-wait'}">{esc(strict_label)}</span></td>
        </tr>
        """
    )

card_grid_html = "".join(card_html) or """
<article class="empty-card">
  <strong>현재 메인에 표시할 관심 종목이 없습니다.</strong>
  <p>시장 휴장 중이거나 최신 스냅샷이 아직 만들어지지 않았습니다. 아래 '관심 종목 표시 점검'에서 누락 이유를 바로 확인하세요.</p>
</article>
"""
table_rows_html = "".join(table_rows) or "<tr><td colspan='10'>현재 관심 종목 기준 최근 스냅샷이 없습니다.</td></tr>"

html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 메인</title>
  <style>
    {presentation_css_root_block()}
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
      grid-template-columns: 1.5fr 1fr;
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
      overflow: hidden;
      position: relative;
    }}
    .intro::after {{
      content: "";
      position: absolute;
      inset: auto -10% -35% auto;
      width: 260px;
      height: 260px;
      background: radial-gradient(circle, rgba(198,157,90,0.22), transparent 65%);
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
      max-width: 46rem;
      line-height: 1.7;
    }}
    .meta {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 16px;
      color: var(--muted);
      font-size: 14px;
    }}
    .quick-links {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
    }}
    .quick-link {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .quick-link:hover {{
      border-color: rgba(21,94,99,0.28);
    }}
    .quick-link.admin-link {{
      background: rgba(23,20,17,0.05);
      color: var(--muted);
    }}
    .action-workbench {{
      margin-top: 16px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: rgba(255,255,255,0.58);
      position: relative;
      z-index: 1;
    }}
    .action-workbench h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .action-workbench p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .action-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
      align-items: center;
    }}
    .action-inline-row {{
      align-items: stretch;
    }}
    .action-input {{
      min-height: 44px;
      flex: 1 1 320px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.84);
      padding: 0 14px;
      font-size: 14px;
      color: var(--ink);
      outline: none;
    }}
    textarea.action-input {{
      min-height: 98px;
      padding: 12px 14px;
      resize: vertical;
      line-height: 1.6;
    }}
    .action-input:focus {{
      border-color: rgba(21,94,99,0.28);
      box-shadow: 0 0 0 3px rgba(21,94,99,0.10);
    }}
    .action-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      cursor: pointer;
    }}
    .action-button.primary {{
      color: #155e63;
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .action-button:disabled {{
      opacity: 0.55;
      cursor: wait;
    }}
    .action-status {{
      margin-top: 12px;
      min-height: 42px;
      padding: 10px 12px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      white-space: pre-wrap;
    }}
    .action-format-guide {{
      margin-top: 12px;
      padding: 14px;
      border-radius: 16px;
      border: 1px dashed rgba(21,94,99,0.20);
      background: rgba(21,94,99,0.06);
    }}
    .action-format-guide strong {{
      display: block;
      margin-bottom: 10px;
      color: #155e63;
    }}
    .action-format-guide p {{
      margin-top: 10px;
      font-size: 13px;
    }}
    .action-format-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .action-format-card {{
      border-radius: 14px;
      border: 1px solid rgba(21,94,99,0.12);
      background: rgba(255,255,255,0.76);
      padding: 12px;
    }}
    .format-label {{
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      margin-bottom: 8px;
      letter-spacing: 0.02em;
    }}
    .action-format-card pre {{
      margin: 0;
      font-size: 13px;
      line-height: 1.7;
      color: var(--ink);
      white-space: pre-wrap;
      word-break: break-word;
      font-family: "SFMono-Regular", "Menlo", monospace;
    }}
    .quick-mode-toggle {{
      display: inline-flex;
      gap: 8px;
      flex: 0 0 auto;
    }}
    .action-toggle {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 44px;
      padding: 0 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      cursor: pointer;
    }}
    .action-toggle.active {{
      color: #155e63;
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .bulk-example-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .bulk-example-toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      margin-top: 10px;
    }}
    .bulk-example-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }}
    .bulk-example-tab.active {{
      color: #155e63;
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .bulk-example-panel {{
      display: none;
      margin-top: 10px;
    }}
    .bulk-example-panel.active {{
      display: block;
    }}
    .bulk-copy-button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }}
    .bulk-copy-button:hover {{
      color: #155e63;
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .action-preview {{
      margin-top: 12px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
      white-space: pre-wrap;
    }}
    .workspace-toolbar {{
      padding: 14px 18px;
      margin-bottom: 18px;
    }}
    .workspace-tabs {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .workspace-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 16px;
      border-radius: 16px 16px 0 0;
      border: 1px solid var(--line);
      border-bottom: 0;
      background: rgba(255,255,255,0.60);
      color: var(--muted);
      font-size: 13px;
      font-weight: 800;
      letter-spacing: 0.02em;
      cursor: pointer;
    }}
    .workspace-tab.active {{
      color: var(--ink);
      background: rgba(255,255,255,0.96);
      box-shadow: inset 0 2px 0 rgba(31,111,120,0.25);
    }}
    .workspace-note {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}
    .workspace-panel.is-hidden {{
      display: none;
    }}
    .gate-strip {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 12px;
    }}
    .gate-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.64);
      color: var(--ink);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
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
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .stat .value {{
      margin-top: 6px;
      font-size: 28px;
      font-weight: 700;
    }}
    .status-panel {{
      padding: 18px 20px;
      margin-bottom: 18px;
    }}
    .status-panel h2 {{
      margin: 0 0 10px;
      font-size: 20px;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .status-panel p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.7;
    }}
    .status-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .status-item {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px;
      background: rgba(255,255,255,0.58);
    }}
    .status-item.status-ok {{
      background: #ecfdf5;
      border-color: rgba(22, 163, 74, 0.18);
    }}
    .status-item.status-warn {{
      background: #fff7ed;
      border-color: rgba(234, 88, 12, 0.18);
    }}
    .status-item.status-info {{
      background: #eff6ff;
      border-color: rgba(37, 99, 235, 0.14);
    }}
    .status-item .label {{
      color: var(--muted);
      font-size: 11px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .tone-badge {{
      display: inline-flex;
      align-items: center;
      min-height: 20px;
      padding: 0 8px;
      margin-left: 6px;
      border-radius: 999px;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      cursor: help;
    }}
    .tone-badge.tone-ok {{
      background: rgba(22, 163, 74, 0.12);
      color: #166534;
    }}
    .tone-badge.tone-warn {{
      background: rgba(234, 88, 12, 0.12);
      color: #9a3412;
    }}
    .tone-badge.tone-info {{
      background: rgba(37, 99, 235, 0.12);
      color: #1d4ed8;
    }}
    .status-item .value {{
      margin-top: 6px;
      font-size: 14px;
      line-height: 1.5;
      word-break: break-word;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }}
    .content-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.7fr) minmax(320px, 0.9fr);
      gap: 18px;
      align-items: start;
      margin-bottom: 18px;
    }}
    .controls {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 14px;
      padding: 18px;
      margin-bottom: 18px;
      align-items: end;
    }}
    .control-stack {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .tabs {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .event-type-tabs .tab {{
      text-transform: lowercase;
    }}
    .tab {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.56);
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.06em;
      cursor: pointer;
    }}
    .tab.active {{
      background: var(--ink);
      color: white;
      border-color: var(--ink);
    }}
    .field {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .field label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .field input,
    .field select {{
      height: 42px;
      min-width: 180px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      font-size: 14px;
    }}
    .control-meta {{
      color: var(--muted);
      font-size: 13px;
      text-align: right;
    }}
    .control-meta-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .reset-button {{
      height: 38px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255,255,255,0.74);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      cursor: pointer;
    }}
    .reset-button:hover {{
      border-color: rgba(21,94,99,0.28);
    }}
    .filter-summary {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid var(--line);
    }}
    .filter-summary-label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .filter-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .filter-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.70);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }}
    .card {{
      padding: 18px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      cursor: pointer;
      transition: transform 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease;
    }}
    .card:hover {{
      transform: translateY(-2px);
      border-color: rgba(21,94,99,0.30);
    }}
    .card.is-active {{
      border-color: rgba(21,94,99,0.46);
      box-shadow: 0 20px 42px rgba(21,94,99,0.14);
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      margin-bottom: 16px;
    }}
    .ticker {{
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }}
    .sub {{
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 68px;
      height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      color: white;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .buy {{ background: var(--buy); }}
    .sell {{ background: var(--sell); }}
    .hold {{ background: var(--hold); }}
    .score-line {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 14px;
    }}
    .score-line strong {{
      font-size: 34px;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .score-line span {{
      color: var(--muted);
      font-size: 14px;
    }}
    .delta-line {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin: -2px 0 14px;
    }}
    .delta {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.52);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
    }}
    .delta-up {{
      color: var(--buy);
      background: rgba(21,94,99,0.10);
    }}
    .delta-down {{
      color: var(--sell);
      background: rgba(154,52,18,0.10);
    }}
    .delta-flat {{
      color: var(--muted);
      background: rgba(107,114,128,0.10);
    }}
    .status-line {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin: -2px 0 14px;
    }}
    .status-label {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .macro-pill {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.08em;
      background: rgba(255,255,255,0.52);
    }}
    .macro-risk-on {{
      color: var(--buy);
      background: rgba(21,94,99,0.12);
    }}
    .macro-risk-off {{
      color: var(--sell);
      background: rgba(154,52,18,0.12);
    }}
    .macro-mixed {{
      color: #7a560d;
      background: rgba(198,157,90,0.18);
    }}
    .macro-partial {{
      color: var(--hold);
      background: rgba(107,114,128,0.12);
    }}
    .risk {{
      margin-left: auto;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.08em;
    }}
    .risk-high {{ background: rgba(154,52,18,0.12); color: var(--sell); }}
    .risk-medium {{ background: rgba(198,157,90,0.18); color: #7a560d; }}
    .risk-low {{ background: rgba(21,94,99,0.12); color: var(--buy); }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px 14px;
      margin: 0 0 14px;
    }}
    .metrics div {{
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .metrics dt {{
      color: var(--muted);
      font-size: 12px;
    }}
    .metrics dd {{
      margin: 4px 0 0;
      font-size: 16px;
      font-weight: 700;
    }}
    .sparkline-wrap {{
      margin: 0 0 14px;
      padding: 10px 12px 8px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(255,255,255,0.52);
    }}
    .sparkline-meta {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .sparkline {{
      display: block;
      width: 100%;
      height: 64px;
      overflow: visible;
    }}
    .mini-bars {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
      color: var(--muted);
      font-size: 12px;
    }}
    .mini-bars span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      background: rgba(255,255,255,0.5);
    }}
    .headline {{
      margin: 0 0 10px;
      font-size: 14px;
      line-height: 1.6;
    }}
    .headline-link {{
      display: block;
      color: inherit;
      text-decoration: none;
    }}
    .headline-link:hover {{
      text-decoration: underline;
    }}
    .events {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 10px;
    }}
    .event {{
      border-radius: 999px;
      padding: 4px 10px;
      background: rgba(21,94,99,0.10);
      color: var(--buy);
      font-size: 11px;
      font-weight: 700;
      border: 1px solid transparent;
    }}
    .event.empty {{
      background: rgba(107,114,128,0.10);
      color: var(--hold);
    }}
    .event-earnings {{
      background: rgba(21,94,99,0.10);
      color: var(--buy);
      border-color: rgba(21,94,99,0.16);
    }}
    .event-regulation {{
      background: rgba(154,52,18,0.10);
      color: var(--sell);
      border-color: rgba(154,52,18,0.16);
    }}
    .event-insider {{
      background: rgba(198,157,90,0.18);
      color: #7a560d;
      border-color: rgba(198,157,90,0.24);
    }}
    .event-capital {{
      background: rgba(79,70,229,0.10);
      color: #4338ca;
      border-color: rgba(79,70,229,0.16);
    }}
    .event-generic {{
      background: rgba(107,114,128,0.10);
      color: var(--hold);
      border-color: rgba(107,114,128,0.16);
    }}
    .reason {{
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }}
    .micro-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .micro-chip,
    .strict-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      background: rgba(255,255,255,0.60);
    }}
    .source-chip {{
      color: var(--ink);
    }}
    .strict-ready {{
      color: #155e63;
      background: rgba(21,94,99,0.10);
      border-color: rgba(21,94,99,0.18);
    }}
    .strict-wait {{
      color: #9a3412;
      background: rgba(154,52,18,0.10);
      border-color: rgba(154,52,18,0.18);
    }}
    .detail-panel {{
      position: sticky;
      top: 24px;
      padding: 20px;
    }}
    .detail-panel h2 {{
      margin: 0;
      font-size: 16px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .detail-title {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin: 12px 0 10px;
    }}
    .detail-title strong {{
      font-size: 36px;
      line-height: 1;
      letter-spacing: -0.03em;
    }}
    .detail-sub {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 16px;
    }}
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }}
    .detail-item {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255,255,255,0.54);
    }}
    .detail-item .label {{
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .detail-item .value {{
      margin-top: 6px;
      font-size: 16px;
      font-weight: 700;
    }}
    .detail-item .value .macro-pill {{
      min-height: 30px;
      font-size: 12px;
    }}
    .detail-sparkline {{
      margin: 0;
      padding: 14px 14px 8px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255,255,255,0.54);
    }}
    .detail-sparkline .sparkline {{
      height: 86px;
    }}
    .detail-block {{
      border-top: 1px solid var(--line);
      padding-top: 14px;
      margin-top: 14px;
    }}
    .detail-block h3 {{
      margin: 0 0 10px;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .detail-reason {{
      margin: 0;
      font-size: 13px;
      line-height: 1.7;
      color: var(--ink);
    }}
    .detail-list {{
      display: grid;
      gap: 10px;
    }}
    .detail-news-item,
    .detail-event-item,
    .detail-alert-item {{
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255,255,255,0.48);
    }}
    .detail-news-link {{
      display: block;
      color: inherit;
      text-decoration: none;
    }}
    .detail-news-link:hover strong {{
      text-decoration: underline;
    }}
    .detail-news-item strong,
    .detail-event-item strong,
    .detail-alert-item strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 13px;
    }}
    .detail-event-head {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}
    .detail-event-meta {{
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .detail-news-item p,
    .detail-event-item p,
    .detail-alert-item p {{
      margin: 0;
      font-size: 12px;
      line-height: 1.6;
      color: var(--muted);
    }}
    .detail-empty {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .table-panel {{
      padding: 18px;
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
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
    }}
    tbody tr {{
      cursor: pointer;
      transition: background 0.18s ease;
    }}
    tbody tr:hover {{
      background: rgba(21,94,99,0.06);
    }}
    tbody tr.is-active {{
      background: rgba(21,94,99,0.10);
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .is-hidden {{
      display: none !important;
    }}
    .market-overview {{
      margin-top: 18px;
      display: grid;
      gap: 14px;
    }}
    .market-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }}
    .market-card {{
      padding: 14px;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.7);
    }}
    .market-head {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 10px;
      margin-bottom: 8px;
    }}
    .market-head h3 {{
      margin: 0;
      font-size: 16px;
      letter-spacing: -0.02em;
    }}
    .market-state {{
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 0 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.82);
    }}
    .market-count {{
      font-size: 28px;
      font-weight: 700;
      letter-spacing: -0.04em;
    }}
    .market-sample {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .market-warning {{
      padding: 12px 14px;
      border-radius: 16px;
      border: 1px solid rgba(180,83,9,0.18);
      background: rgba(180,83,9,0.10);
      color: var(--sell);
      font-size: 13px;
      line-height: 1.6;
      font-weight: 600;
    }}
    .market-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 10px;
    }}
    .market-action-link {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.84);
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .market-action-note {{
      margin: 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.6;
    }}
    .state-ok {{
      color: var(--buy);
      border-color: rgba(21,94,99,0.18);
      background: rgba(21,94,99,0.10);
    }}
    .state-info {{
      color: #345d7a;
      border-color: rgba(52,93,122,0.18);
      background: rgba(52,93,122,0.10);
    }}
    .state-warn {{
      color: var(--sell);
      border-color: rgba(180,83,9,0.18);
      background: rgba(180,83,9,0.10);
    }}
    .state-muted {{
      color: var(--muted);
      border-color: rgba(23,20,17,0.12);
      background: rgba(23,20,17,0.04);
    }}
    .empty-card {{
      border: 1px dashed var(--line);
      border-radius: 22px;
      padding: 24px;
      background: rgba(255,255,255,0.55);
      color: var(--muted);
    }}
    .empty-card strong {{
      display: block;
      margin-bottom: 8px;
      color: var(--ink);
      font-size: 18px;
    }}
    .empty-card p {{
      margin: 0;
      line-height: 1.7;
    }}
    .offline-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }}
    .offline-card {{
      cursor: default;
    }}
    .offline-card:hover {{
      transform: none;
      border-color: var(--line);
    }}
    .offline-card-empty {{
      background: rgba(255,255,255,0.58);
      border-style: dashed;
    }}
    .offline-reason {{
      margin: 0 0 12px;
      color: var(--ink);
      font-size: 13px;
      line-height: 1.7;
    }}
    .offline-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }}
    .admin-links-panel {{
      padding: 18px 20px;
      margin-bottom: 18px;
    }}
    .admin-links-panel h2 {{
      margin: 0 0 10px;
      font-size: 20px;
      font-family: Georgia, "Times New Roman", serif;
    }}
    .admin-links-panel p {{
      margin: 0 0 12px;
      color: var(--muted);
      line-height: 1.7;
    }}
    @media (max-width: 860px) {{
      body {{ padding: 14px; }}
      .hero {{ grid-template-columns: 1fr; }}
      .content-grid {{ grid-template-columns: 1fr; }}
      .stats {{ grid-template-columns: repeat(2, 1fr); }}
      .controls {{ grid-template-columns: 1fr; }}
      .control-meta {{ text-align: left; }}
      .detail-panel {{ position: static; }}
      .table-panel {{ overflow-x: auto; }}
      table {{ min-width: 760px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <article class="panel intro">
        <h1>SIA<br>메인</h1>
        <p>관심 종목 추가, 시장 설정, 점수 확인을 한 화면에서 처리하는 사용자용 메인입니다. 장중 상태는 <strong>실시간</strong>, 마지막 저장 점수는 <strong>오프라인 점수</strong>, 운영 진단은 <strong>관리자 체크</strong>에서 봅니다.</p>
        <div class="meta">
          <span>최근 갱신: {esc(last_updated)}</span>
          <span>관심 종목 수: {len(active_watchlist_entries)}</span>
          <span>실시간 반영 종목: <strong id="metaTickerCount">{len(cards)}</strong></span>
        </div>
        <div class="action-workbench">
          <h2>메인 작업</h2>
          <p>여기서 관심 종목 추가/삭제, 시장별 티커 일괄 붙여넣기, 엔진 1회 실행, 백테스트 갱신을 바로 시작합니다.</p>
          <div class="action-row action-inline-row">
            <div class="quick-mode-toggle">
              <button id="quickModeAddButton" class="action-toggle active" type="button">추가 모드</button>
              <button id="quickModeRemoveButton" class="action-toggle" type="button">삭제 모드</button>
            </div>
            <input id="quickAddInput" class="action-input" type="text" placeholder="티커 추가 : [ ASTS ]" autocomplete="off">
          </div>
          <div class="action-row">
            <button id="quickAddButton" class="action-button primary" type="button">관심 종목 추가</button>
            <button id="quickRemoveButton" class="action-button" type="button">관심 종목 삭제</button>
          </div>
          <div class="action-format-guide">
            <strong>빠른 추가 / 삭제 예시</strong>
            <div class="action-format-grid">
              <div class="action-format-card">
                <div class="format-label">빠른 추가</div>
                <pre>티커 추가 : [ ASTS ]</pre>
              </div>
              <div class="action-format-card">
                <div class="format-label">빠른 삭제</div>
                <pre>티커 삭제 : [ ASTS ]</pre>
              </div>
            </div>
          </div>
          <div class="action-row">
            <select id="bulkMarketSelect" class="action-input">
              <option value="US">미국</option>
              <option value="KR">한국</option>
              <option value="EU">유럽</option>
              <option value="JP">일본</option>
            </select>
            <textarea id="bulkTickerInput" class="action-input" rows="3" placeholder="AAPL, MSFT, NVDA&#10;또는&#10;AAPL&#10;MSFT&#10;NVDA"></textarea>
            <button id="bulkSetButton" class="action-button" type="button">시장별 티커 일괄 붙여넣기</button>
          </div>
          <div class="action-format-guide">
            <strong>붙여넣기 예시</strong>
            <div class="action-format-grid">
              <div class="action-format-card">
                <div class="format-label">쉼표로 한 줄 입력</div>
                <pre>AAPL, MSFT, NVDA, AMZN</pre>
              </div>
              <div class="action-format-card">
                <div class="format-label">줄바꿈으로 여러 줄 입력</div>
                <pre>AAPL
MSFT
NVDA
AMZN</pre>
              </div>
              <div class="action-format-card">
                <div class="format-label">한국 예시</div>
                <pre>005930.KS
000660.KS</pre>
              </div>
              <div class="action-format-card">
                <div class="format-label">유럽 / 일본 예시</div>
                <pre>ASML
7203.T</pre>
              </div>
            </div>
            <p>여기에 넣는 값은 선택한 시장의 관심 종목 목록을 그대로 덮어씁니다.</p>
            <p>입력값 자체는 브라우저에 저장하지 않고, 마지막으로 고른 시장만 기억합니다.</p>
            <div class="bulk-example-toolbar">
              <div class="bulk-example-tabs">
                <button class="bulk-example-tab active" type="button" data-bulk-example-market="US">미국</button>
                <button class="bulk-example-tab" type="button" data-bulk-example-market="KR">한국</button>
                <button class="bulk-example-tab" type="button" data-bulk-example-market="EU">유럽</button>
                <button class="bulk-example-tab" type="button" data-bulk-example-market="JP">일본</button>
              </div>
              <button id="bulkExampleCopyButton" class="bulk-copy-button" type="button">현재 예시 복사 + 입력</button>
            </div>
            <div class="bulk-example-panel active" data-bulk-example-panel="US">
              <pre>AAPL, MSFT, NVDA, AMZN
GOOGL, META, TSLA, ASTS</pre>
            </div>
            <div class="bulk-example-panel" data-bulk-example-panel="KR">
              <pre>005930.KS
000660.KS
035420.KS
051910.KS</pre>
            </div>
            <div class="bulk-example-panel" data-bulk-example-panel="EU">
              <pre>ASML.AS
SAP.DE
MC.PA
NESN.SW</pre>
            </div>
            <div class="bulk-example-panel" data-bulk-example-panel="JP">
              <pre>7203.T
9984.T
6758.T
8035.T</pre>
            </div>
          </div>
          <div id="bulkPreviewBox" class="action-preview">선택한 시장의 현재 관심 종목 목록을 불러오는 중입니다.</div>
          <div class="action-preview">{last_bulk_set_html}</div>
          <div class="action-preview">{last_quick_add_html}</div>
          <div class="action-preview">{last_quick_remove_html}</div>
          <div class="action-row">
            <button id="runLiveOnceButton" class="action-button" type="button">엔진 1회 실행</button>
            <button id="backtestRefreshButton" class="action-button" type="button">백테스트 갱신</button>
            <button id="refreshMainButton" class="action-button" type="button">메인 다시 만들기</button>
          </div>
          <div id="actionStatus" class="action-status">로컬 액션 서비스 연결 후 여기에서 실행 결과를 보여줍니다.</div>
        </div>
        <div class="quick-links">
          <a class="quick-link" href="file:///Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Tickers.command">관심 종목 설정</a>
          <a class="quick-link" href="file:///Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Settings.command">시장 설정</a>
          <a class="quick-link" href="universe-report.html" target="_blank" rel="noreferrer">관심 종목 목록</a>
          <a class="quick-link" href="full-universe-report.html" target="_blank" rel="noreferrer">시총 상위 종목 보고서</a>
          <a class="quick-link" href="backtest-readiness-report.html" target="_blank" rel="noreferrer">백테스트 준비도</a>
          <a class="quick-link" href="price-backtest-report.html" target="_blank" rel="noreferrer">가격 백테스트</a>
          <a class="quick-link" href="position-backtest-report.html" target="_blank" rel="noreferrer">포지션 백테스트</a>
        </div>
        <div class="gate-strip">
          <span class="gate-pill">가격 gate {esc(min_price_samples)}</span>
          <span class="gate-pill">포지션 gate {esc(min_position_trades)}</span>
          <span class="gate-pill">strict gate {esc(min_strict_aligned)}</span>
        </div>
        <div class="market-overview">
          {market_warning_html}
          <div class="market-actions">
            <a class="market-action-link" href="file:///Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Settings.command">시장 체크 변경</a>
            <a class="market-action-link" href="file:///Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Tickers.command">관심 종목 추가/수정</a>
          </div>
          <p class="market-action-note">빠른 추가 예시: <code>티커 추가 : [ ASTS ]</code> / <code>티커 추가 : [ ASTS, NVDA, 005930.KS ]</code></p>
          <div class="market-grid">
            {''.join(market_cards_html)}
          </div>
        </div>
      </article>
      <aside class="panel stats">
        <div class="stat"><div class="label">매수</div><div class="value" id="summaryBuyCount">{buy_count}</div></div>
        <div class="stat"><div class="label">매도</div><div class="value" id="summarySellCount">{sell_count}</div></div>
        <div class="stat"><div class="label">관망</div><div class="value" id="summaryHoldCount">{hold_count}</div></div>
        <div class="stat"><div class="label">평균 신뢰도</div><div class="value" id="summaryAvgConfidence">{fmt_score(avg_confidence)}</div></div>
      </aside>
    </section>
    <section class="panel workspace-toolbar">
      <div class="workspace-tabs">
        <button class="workspace-tab active" type="button" data-main-view="realtime">실시간</button>
        <button class="workspace-tab" type="button" data-main-view="offline">오프라인 점수</button>
        <button class="workspace-tab" type="button" data-main-view="admin">관리자 체크</button>
      </div>
      <p class="workspace-note">실시간은 장중 반영 상태를, 오프라인 점수는 마지막 저장 스냅샷을, 관리자 체크는 데이터 품질과 운영 상태를 보여줍니다.</p>
    </section>
    <section class="workspace-panel" data-main-view-panel="realtime">
    <section class="panel status-panel">
      <h2>장중 반영 현황</h2>
      <p>미국장 등 활성 시장이 열리면 알림 엔진이 15분 주기로 메인을 다시 채웁니다. ASTS 포함 현재 관심 종목이 몇 개 반영됐는지 여기서 바로 확인할 수 있습니다.</p>
      <div class="status-grid">
        {coverage_status_html}
      </div>
    </section>
    <section class="panel controls">
      <div class="control-stack">
        <div class="field">
          <label>신호 탭</label>
          <div class="tabs">
            <button class="tab active" type="button" data-filter-signal="ALL">전체</button>
            <button class="tab" type="button" data-filter-signal="BUY">매수</button>
            <button class="tab" type="button" data-filter-signal="SELL">매도</button>
            <button class="tab" type="button" data-filter-signal="HOLD">관망</button>
            <button class="tab" type="button" id="riskHighToggle">리스크 높음만</button>
            <button class="tab" type="button" id="eventOnlyToggle">이벤트 있는 종목만</button>
            <button class="tab" type="button" id="strictEligibleToggle">엄격 기준 가능만</button>
          </div>
        </div>
        <div class="field">
          <label>매크로 환경</label>
          <div class="tabs macro-tabs">
            <button class="tab active" type="button" data-filter-macro="ALL">전체</button>
            <button class="tab" type="button" data-filter-macro="RISK_ON">위험선호</button>
            <button class="tab" type="button" data-filter-macro="MIXED">혼합</button>
            <button class="tab" type="button" data-filter-macro="RISK_OFF">위험회피</button>
            <button class="tab" type="button" data-filter-macro="PARTIAL">부분</button>
          </div>
        </div>
        <div class="field">
          <label>이벤트 타입</label>
          <div class="tabs event-type-tabs">
            <button class="tab active" type="button" data-filter-event-type="ALL">전체</button>
            <button class="tab" type="button" data-filter-event-type="earnings">실적</button>
            <button class="tab" type="button" data-filter-event-type="regulation">규제</button>
            <button class="tab" type="button" data-filter-event-type="insider">내부자</button>
            <button class="tab" type="button" data-filter-event-type="capital">자본</button>
          </div>
        </div>
        <div class="field">
          <label for="searchBox">검색</label>
          <input id="searchBox" type="search" placeholder="티커, 이유, 뉴스 검색">
        </div>
        <div class="field">
          <label for="sortSelect">정렬</label>
          <select id="sortSelect">
            <option value="composite">종합 점수</option>
            <option value="confidence">신뢰도</option>
            <option value="strict_status">엄격 기준 상태</option>
            <option value="composite_delta">점수 변화량</option>
            <option value="confidence_delta">신뢰도 변화량</option>
            <option value="latest">최신순</option>
            <option value="ticker">티커순</option>
          </select>
        </div>
      </div>
      <div class="control-meta">
        <div class="control-meta-row">
          <div>보이는 카드: <strong id="visibleCardCount">{len(cards)}</strong> / {len(cards)}</div>
          <div>보이는 행: <strong id="visibleRowCount">{min(len(items), 30)}</strong> / {min(len(items), 30)}</div>
          <button class="reset-button" type="button" id="resetDashboardState">필터 초기화</button>
        </div>
      </div>
      <div class="filter-summary" id="filterSummaryBar">
        <span class="filter-summary-label">현재 필터</span>
        <div class="filter-chips"><span class="filter-chip">기본 보기</span></div>
      </div>
    </section>
    <section class="content-grid">
      <section class="cards" id="cardGrid">
        {card_grid_html}
      </section>
      <aside class="panel detail-panel" id="detailPanel">
        <h2>상세 보기</h2>
        <div class="detail-title">
          <strong id="detailTicker">{esc(initial_card["ticker"])}</strong>
          <span class="badge {signal_class(initial_card['signal'])}" id="detailSignal">{esc(signal_display(initial_card["signal"]))}</span>
        </div>
        <div class="detail-sub" id="detailTimestamp">{fmt_ts(initial_card["ts"])}</div>
        <div class="detail-grid">
          <div class="detail-item"><div class="label">종합 점수</div><div class="value" id="detailComposite">{fmt_score(initial_card["composite_score"])}</div></div>
          <div class="detail-item"><div class="label">신뢰도</div><div class="value" id="detailConfidence">{fmt_score(initial_card["confidence"])}</div></div>
          <div class="detail-item"><div class="label">리스크</div><div class="value" id="detailRisk">{esc(risk_display(initial_card["risk_level"]))}</div></div>
          <div class="detail-item"><div class="label">모멘텀</div><div class="value" id="detailMomentum">{esc(initial_card["momentum"])}</div></div>
          <div class="detail-item"><div class="label">매크로</div><div class="value"><span class="macro-pill {macro_env_class(initial_card['macro_environment'])}" id="detailMacroEnvironment">{esc(macro_env_display(initial_card["macro_environment"]))}</span></div></div>
          <div class="detail-item"><div class="label">신호 소스</div><div class="value" id="detailSignalSource">{esc(initial_source)}</div></div>
          <div class="detail-item"><div class="label">엄격 기준 상태</div><div class="value strict-chip {initial_strict_class}" id="detailStrictEligible">{esc(initial_strict_label)}</div></div>
          <div class="detail-item"><div class="label">가격</div><div class="value" id="detailPrice">{fmt_num(initial_card["price"])}</div></div>
          <div class="detail-item"><div class="label">RSI</div><div class="value" id="detailRsi">{fmt_num(initial_card["rsi"])}</div></div>
          <div class="detail-item"><div class="label">SMA Fast</div><div class="value" id="detailSmaFast">{fmt_num(initial_card["sma_fast"])}</div></div>
          <div class="detail-item"><div class="label">SMA Slow</div><div class="value" id="detailSmaSlow">{fmt_num(initial_card["sma_slow"])}</div></div>
        </div>
        <div class="detail-sparkline" id="detailSparklineWrap">
          {sparkline_svg(price_history_by_ticker.get(initial_card["ticker"], []), width=320, height=86)}
        </div>
        <div class="detail-block">
          <h3>최근 변화</h3>
          <div class="detail-grid">
            <div class="detail-item"><div class="label">점수 변화</div><div class="value delta {delta_class(score_delta_by_ticker.get(initial_card['ticker'], {}).get('composite'))}" id="detailCompositeDelta">{fmt_score_delta(score_delta_by_ticker.get(initial_card["ticker"], {}).get("composite"))}</div></div>
            <div class="detail-item"><div class="label">신뢰도 변화</div><div class="value delta {delta_class(score_delta_by_ticker.get(initial_card['ticker'], {}).get('confidence'))}" id="detailConfidenceDelta">{fmt_score_delta(score_delta_by_ticker.get(initial_card["ticker"], {}).get("confidence"))}</div></div>
          </div>
        </div>
        <div class="detail-block">
          <h3>팩터 점수</h3>
          <div class="detail-grid">
            <div class="detail-item"><div class="label">차트</div><div class="value" id="detailChartScore">{fmt_score(initial_card["chart_score"])}</div></div>
            <div class="detail-item"><div class="label">매크로</div><div class="value" id="detailMacroScore">{fmt_score(initial_card["macro_score"])}</div></div>
            <div class="detail-item"><div class="label">이벤트</div><div class="value" id="detailEventScore">{fmt_score(initial_card["event_score"])}</div></div>
            <div class="detail-item"><div class="label">뉴스</div><div class="value" id="detailNewsScore">{fmt_score(initial_card["news_score"])}</div></div>
          </div>
        </div>
        <div class="detail-block">
          <h3>근거</h3>
          <p class="detail-reason" id="detailReason">{esc(reason_display(initial_card["reason"]))}</p>
        </div>
        <div class="detail-block">
          <h3>주요 뉴스</h3>
          <div class="detail-list" id="detailNewsList"></div>
        </div>
        <div class="detail-block">
          <h3>이벤트</h3>
          <div class="detail-list" id="detailEventList"></div>
        </div>
        <div class="detail-block">
          <h3>최근 알림</h3>
          <div class="detail-list" id="detailAlertList"></div>
        </div>
      </aside>
    </section>
    <section class="panel table-panel">
      <div class="table-head">
        <h2>최근 반영 스냅샷</h2>
        <p>현재 관심 종목 기준 최근 30건만 보여줍니다.</p>
      </div>
      <table>
        <thead>
          <tr>
            <th>시간</th>
            <th>티커</th>
            <th>신호</th>
            <th>신뢰도</th>
            <th>종합점수</th>
            <th>리스크</th>
            <th>모멘텀</th>
            <th>매크로</th>
            <th>소스</th>
            <th>엄격 기준 상태</th>
          </tr>
        </thead>
        <tbody id="historyTableBody">
          {table_rows_html}
        </tbody>
      </table>
    </section>
    </section>
    <section class="workspace-panel is-hidden" data-main-view-panel="offline">
      <section class="panel status-panel">
        <h2>오프라인 점수</h2>
        <p>장이 닫혀 있어도 마지막으로 저장된 스냅샷 점수를 읽을 수 있습니다. 실시간 탭보다 시간이 뒤쳐질 수 있으므로 최근 저장 시각을 같이 보세요.</p>
        <div class="status-grid">
          {offline_status_html}
        </div>
      </section>
      <section class="panel status-panel">
        <h2>최근 관심 종목 변경</h2>
        <p>빠른 추가, 빠른 삭제, 시장별 일괄 붙여넣기 기록입니다. 입력이 제대로 들어갔는지 여기서 확인합니다.</p>
        <div class="status-grid">
          {recent_ticker_history_html}
        </div>
      </section>
      <section class="panel status-panel">
        <h2>관심 종목 표시 점검</h2>
        <p>실시간 탭에 아직 안 보이는 종목과 현재 이유를 보여줍니다. 휴장인지, 스냅샷 대기인지 바로 구분할 수 있게 둔 영역입니다.</p>
        <div class="status-grid">
          {missing_watchlist_html}
        </div>
      </section>
      <section class="panel table-panel">
        <div class="table-head">
          <h2>마지막 저장 점수</h2>
          <p>현재 관심 종목 기준 마지막 저장 스냅샷을 카드로 보여줍니다. 실시간 반영이 없어도 여기서는 점수를 확인할 수 있습니다.</p>
        </div>
        <div class="offline-grid">
          {offline_cards_html}
        </div>
      </section>
    </section>
    <section class="workspace-panel is-hidden" data-main-view-panel="admin">
      <section class="panel admin-links-panel">
        <h2>관리자 체크</h2>
        <p>운영 진단용 리포트와 데이터 상태 링크입니다. 일반 사용자는 평소에 이 탭까지 볼 필요는 없습니다.</p>
        <div class="quick-links">
          <a class="quick-link admin-link" href="report-hub.html" target="_blank" rel="noreferrer">관리자 체크 포인트</a>
          <a class="quick-link admin-link" href="data-quality-report.html" target="_blank" rel="noreferrer">데이터 품질</a>
          <a class="quick-link admin-link" href="factor-breakdown-report.html" target="_blank" rel="noreferrer">점수 분해</a>
          <a class="quick-link admin-link" href="tuning-compare.html" target="_blank" rel="noreferrer">튜닝 비교</a>
        </div>
      </section>
      <section class="panel status-panel">
        <h2>시스템 상태</h2>
        <p>운영자가 보는 연결 상태, 캐시 파일, launchd 상태를 읽기 전용으로 보여줍니다.</p>
        <div class="status-grid">
          {system_status_html}
        </div>
      </section>
    </section>
  </main>
  <script>
    (() => {{
      const workspaceTabs = [...document.querySelectorAll('[data-main-view]')];
      const workspacePanels = [...document.querySelectorAll('[data-main-view-panel]')];
      const signalTabs = [...document.querySelectorAll('[data-filter-signal]')];
      const macroTabs = [...document.querySelectorAll('[data-filter-macro]')];
      const searchBox = document.getElementById('searchBox');
      const sortSelect = document.getElementById('sortSelect');
      const riskHighToggle = document.getElementById('riskHighToggle');
      const eventOnlyToggle = document.getElementById('eventOnlyToggle');
      const strictEligibleToggle = document.getElementById('strictEligibleToggle');
      const eventTypeTabs = [...document.querySelectorAll('[data-filter-event-type]')];
      const cardGrid = document.getElementById('cardGrid');
      const tableBody = document.getElementById('historyTableBody');
      const quickAddInput = document.getElementById('quickAddInput');
      const quickModeAddButton = document.getElementById('quickModeAddButton');
      const quickModeRemoveButton = document.getElementById('quickModeRemoveButton');
      const quickAddButton = document.getElementById('quickAddButton');
      const quickRemoveButton = document.getElementById('quickRemoveButton');
      const bulkMarketSelect = document.getElementById('bulkMarketSelect');
      const bulkTickerInput = document.getElementById('bulkTickerInput');
      const bulkSetButton = document.getElementById('bulkSetButton');
      const bulkPreviewBox = document.getElementById('bulkPreviewBox');
      const bulkExampleTabs = [...document.querySelectorAll('[data-bulk-example-market]')];
      const bulkExamplePanels = [...document.querySelectorAll('[data-bulk-example-panel]')];
      const bulkExampleCopyButton = document.getElementById('bulkExampleCopyButton');
      const runLiveOnceButton = document.getElementById('runLiveOnceButton');
      const backtestRefreshButton = document.getElementById('backtestRefreshButton');
      const refreshMainButton = document.getElementById('refreshMainButton');
      const actionStatus = document.getElementById('actionStatus');
      const visibleCardCount = document.getElementById('visibleCardCount');
      const visibleRowCount = document.getElementById('visibleRowCount');
      const metaTickerCount = document.getElementById('metaTickerCount');
      const filterSummaryBar = document.getElementById('filterSummaryBar');
      const resetDashboardState = document.getElementById('resetDashboardState');
      const summaryBuyCount = document.getElementById('summaryBuyCount');
      const summarySellCount = document.getElementById('summarySellCount');
      const summaryHoldCount = document.getElementById('summaryHoldCount');
      const summaryAvgConfidence = document.getElementById('summaryAvgConfidence');
      const detailTicker = document.getElementById('detailTicker');
      const detailSignal = document.getElementById('detailSignal');
      const detailTimestamp = document.getElementById('detailTimestamp');
      const detailComposite = document.getElementById('detailComposite');
      const detailConfidence = document.getElementById('detailConfidence');
      const detailRisk = document.getElementById('detailRisk');
      const detailMomentum = document.getElementById('detailMomentum');
      const detailMacroEnvironment = document.getElementById('detailMacroEnvironment');
      const detailSignalSource = document.getElementById('detailSignalSource');
      const detailStrictEligible = document.getElementById('detailStrictEligible');
      const detailPrice = document.getElementById('detailPrice');
      const detailRsi = document.getElementById('detailRsi');
      const detailSmaFast = document.getElementById('detailSmaFast');
      const detailSmaSlow = document.getElementById('detailSmaSlow');
      const detailCompositeDelta = document.getElementById('detailCompositeDelta');
      const detailConfidenceDelta = document.getElementById('detailConfidenceDelta');
      const detailChartScore = document.getElementById('detailChartScore');
      const detailMacroScore = document.getElementById('detailMacroScore');
      const detailEventScore = document.getElementById('detailEventScore');
      const detailNewsScore = document.getElementById('detailNewsScore');
      const detailReason = document.getElementById('detailReason');
      const detailNewsList = document.getElementById('detailNewsList');
      const detailEventList = document.getElementById('detailEventList');
      const detailAlertList = document.getElementById('detailAlertList');
      const detailSparklineWrap = document.getElementById('detailSparklineWrap');
      const cards = [...cardGrid.querySelectorAll('.card')];
      const rows = [...tableBody.querySelectorAll('tr')];
      const STRICT_ELIGIBLE_STORAGE_KEY = 'sia.dashboard.strictEligibleOnly';
      const RISK_HIGH_STORAGE_KEY = 'sia.dashboard.riskHighOnly';
      const EVENT_ONLY_STORAGE_KEY = 'sia.dashboard.eventOnly';
      const SORT_STORAGE_KEY = 'sia.dashboard.sort';
      const SIGNAL_FILTER_STORAGE_KEY = 'sia.dashboard.signal';
      const MACRO_FILTER_STORAGE_KEY = 'sia.dashboard.macro';
      const EVENT_TYPE_STORAGE_KEY = 'sia.dashboard.eventType';
      const SEARCH_STORAGE_KEY = 'sia.dashboard.search';
      const BULK_MARKET_STORAGE_KEY = 'sia.dashboard.bulkMarket';
      const MAIN_VIEW_STORAGE_KEY = 'sia.dashboard.mainView';
      const DASHBOARD_ACTIONS_URL = {json.dumps(dashboard_actions_url)};
      const MARKET_TICKER_PREVIEW = {json.dumps(market_ticker_values, ensure_ascii=False)};
      const MARKET_LABELS = {{ US: '미국', KR: '한국', EU: '유럽', JP: '일본' }};
      const QUICK_INPUT_PLACEHOLDERS = {{
        add: '티커 추가 : [ ASTS ]',
        remove: '티커 삭제 : [ ASTS ]',
      }};

      let activeSignal = 'ALL';
      let activeMacroEnv = 'ALL';
      let riskHighOnly = false;
      let eventOnly = false;
      let strictEligibleOnly = false;
      let activeEventType = 'ALL';
      let quickInputMode = 'add';

      function loadMainViewPreference() {{
        try {{
          const stored = window.localStorage.getItem(MAIN_VIEW_STORAGE_KEY) || 'realtime';
          return ['realtime', 'offline', 'admin'].includes(stored) ? stored : 'realtime';
        }} catch (_error) {{
          return 'realtime';
        }}
      }}

      function saveMainViewPreference(value) {{
        try {{
          window.localStorage.setItem(MAIN_VIEW_STORAGE_KEY, String(value || 'realtime'));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function setMainView(view) {{
        const activeView = ['realtime', 'offline', 'admin'].includes(view) ? view : 'realtime';
        workspaceTabs.forEach((tab) => {{
          tab.classList.toggle('active', (tab.dataset.mainView || 'realtime') === activeView);
        }});
        workspacePanels.forEach((panel) => {{
          panel.classList.toggle('is-hidden', (panel.dataset.mainViewPanel || 'realtime') !== activeView);
        }});
        saveMainViewPreference(activeView);
      }}

      const parseNum = (value) => {{
        const parsed = Number.parseFloat(value || '0');
        return Number.isFinite(parsed) ? parsed : 0;
      }};

      function loadStrictEligiblePreference() {{
        try {{
          return window.localStorage.getItem(STRICT_ELIGIBLE_STORAGE_KEY) === '1';
        }} catch (_error) {{
          return false;
        }}
      }}

      function saveStrictEligiblePreference(value) {{
        try {{
          window.localStorage.setItem(STRICT_ELIGIBLE_STORAGE_KEY, value ? '1' : '0');
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadRiskHighPreference() {{
        try {{
          return window.localStorage.getItem(RISK_HIGH_STORAGE_KEY) === '1';
        }} catch (_error) {{
          return false;
        }}
      }}

      function saveRiskHighPreference(value) {{
        try {{
          window.localStorage.setItem(RISK_HIGH_STORAGE_KEY, value ? '1' : '0');
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadEventOnlyPreference() {{
        try {{
          return window.localStorage.getItem(EVENT_ONLY_STORAGE_KEY) === '1';
        }} catch (_error) {{
          return false;
        }}
      }}

      function saveEventOnlyPreference(value) {{
        try {{
          window.localStorage.setItem(EVENT_ONLY_STORAGE_KEY, value ? '1' : '0');
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadSortPreference() {{
        try {{
          return window.localStorage.getItem(SORT_STORAGE_KEY) || '';
        }} catch (_error) {{
          return '';
        }}
      }}

      function saveSortPreference(value) {{
        try {{
          window.localStorage.setItem(SORT_STORAGE_KEY, String(value || ''));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadSignalPreference() {{
        try {{
          return window.localStorage.getItem(SIGNAL_FILTER_STORAGE_KEY) || 'ALL';
        }} catch (_error) {{
          return 'ALL';
        }}
      }}

      function saveSignalPreference(value) {{
        try {{
          window.localStorage.setItem(SIGNAL_FILTER_STORAGE_KEY, String(value || 'ALL'));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadMacroPreference() {{
        try {{
          return window.localStorage.getItem(MACRO_FILTER_STORAGE_KEY) || 'ALL';
        }} catch (_error) {{
          return 'ALL';
        }}
      }}

      function saveMacroPreference(value) {{
        try {{
          window.localStorage.setItem(MACRO_FILTER_STORAGE_KEY, String(value || 'ALL'));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadEventTypePreference() {{
        try {{
          return window.localStorage.getItem(EVENT_TYPE_STORAGE_KEY) || 'ALL';
        }} catch (_error) {{
          return 'ALL';
        }}
      }}

      function saveEventTypePreference(value) {{
        try {{
          window.localStorage.setItem(EVENT_TYPE_STORAGE_KEY, String(value || 'ALL'));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadSearchPreference() {{
        try {{
          return window.localStorage.getItem(SEARCH_STORAGE_KEY) || '';
        }} catch (_error) {{
          return '';
        }}
      }}

      function saveSearchPreference(value) {{
        try {{
          window.localStorage.setItem(SEARCH_STORAGE_KEY, String(value || ''));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function loadBulkMarketPreference() {{
        try {{
          const stored = window.localStorage.getItem(BULK_MARKET_STORAGE_KEY) || 'US';
          return ['US', 'KR', 'EU', 'JP'].includes(stored) ? stored : 'US';
        }} catch (_error) {{
          return 'US';
        }}
      }}

      function saveBulkMarketPreference(value) {{
        try {{
          window.localStorage.setItem(BULK_MARKET_STORAGE_KEY, String(value || 'US'));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function clearDashboardPreferences() {{
        try {{
          [
            STRICT_ELIGIBLE_STORAGE_KEY,
            RISK_HIGH_STORAGE_KEY,
            EVENT_ONLY_STORAGE_KEY,
            SORT_STORAGE_KEY,
            SIGNAL_FILTER_STORAGE_KEY,
            MACRO_FILTER_STORAGE_KEY,
            EVENT_TYPE_STORAGE_KEY,
            SEARCH_STORAGE_KEY,
            BULK_MARKET_STORAGE_KEY,
            MAIN_VIEW_STORAGE_KEY,
          ].forEach((key) => window.localStorage.removeItem(key));
        }} catch (_error) {{
          // ignore storage errors
        }}
      }}

      function setActionBusy(isBusy, message) {{
        [quickAddButton, quickRemoveButton, bulkSetButton, runLiveOnceButton, backtestRefreshButton, refreshMainButton].forEach((button) => {{
          if (button) button.disabled = isBusy;
        }});
        if (bulkMarketSelect) bulkMarketSelect.disabled = isBusy;
        if (bulkTickerInput) bulkTickerInput.disabled = isBusy;
        if (actionStatus && message) actionStatus.textContent = message;
      }}

      function renderBulkPreview() {{
        if (!bulkPreviewBox || !bulkMarketSelect) return;
        const market = (bulkMarketSelect.value || 'US').trim();
        const label = MARKET_LABELS[market] || market;
        const tickers = Array.isArray(MARKET_TICKER_PREVIEW[market]) ? MARKET_TICKER_PREVIEW[market] : [];
        if (!tickers.length) {{
          bulkPreviewBox.textContent = `${{label}} 시장 현재 관심 종목 목록이 비어 있습니다.`;
          return;
        }}
        const preview = tickers.slice(0, 12).join(', ');
        const suffix = tickers.length > 12 ? ` 외 ${{tickers.length - 12}}개` : '';
        bulkPreviewBox.textContent = `${{label}} 시장 현재 관심 종목 ${{tickers.length}}개: ${{preview}}${{suffix}}`;
      }}

      function setQuickInputMode(mode) {{
        if (!quickAddInput) return;
        quickInputMode = mode === 'remove' ? 'remove' : 'add';
        if (mode === 'remove') {{
          quickAddInput.placeholder = QUICK_INPUT_PLACEHOLDERS.remove;
          quickModeRemoveButton?.classList.add('active');
          quickModeAddButton?.classList.remove('active');
          if (quickRemoveButton) quickRemoveButton.textContent = '삭제 실행';
          if (quickAddButton) quickAddButton.textContent = '관심 종목 추가';
          quickRemoveButton?.classList.add('primary');
          quickAddButton?.classList.remove('primary');
          return;
        }}
        quickAddInput.placeholder = QUICK_INPUT_PLACEHOLDERS.add;
        quickModeAddButton?.classList.add('active');
        quickModeRemoveButton?.classList.remove('active');
        if (quickAddButton) quickAddButton.textContent = '추가 실행';
        if (quickRemoveButton) quickRemoveButton.textContent = '관심 종목 삭제';
        quickAddButton?.classList.add('primary');
        quickRemoveButton?.classList.remove('primary');
      }}

      function setBulkExampleMarket(market) {{
        bulkExampleTabs.forEach((tab) => {{
          tab.classList.toggle('active', (tab.dataset.bulkExampleMarket || 'US') === market);
        }});
        bulkExamplePanels.forEach((panel) => {{
          panel.classList.toggle('active', (panel.dataset.bulkExamplePanel || 'US') === market);
        }});
      }}

      async function copyBulkExample() {{
        const activePanel = bulkExamplePanels.find((panel) => panel.classList.contains('active'));
        const text = activePanel?.innerText?.trim() || '';
        if (!text) {{
          actionStatus.textContent = '복사할 예시가 없습니다.';
          return;
        }}
        try {{
          if (navigator.clipboard && navigator.clipboard.writeText) {{
            await navigator.clipboard.writeText(text);
          }} else {{
            const helper = document.createElement('textarea');
            helper.value = text;
            document.body.appendChild(helper);
            helper.select();
            document.execCommand('copy');
            document.body.removeChild(helper);
          }}
          if (bulkTickerInput) {{
            bulkTickerInput.value = text;
            bulkTickerInput.focus();
          }}
          actionStatus.textContent = '현재 시장 예시를 복사했고 입력칸에도 넣었습니다.';
        }} catch (error) {{
          actionStatus.textContent = `예시 복사 실패: ${{error.message || error}}`;
        }}
      }}

      async function callAction(path, body = '') {{
        const response = await fetch(`${{DASHBOARD_ACTIONS_URL}}${{path}}`, {{
          method: 'POST',
          body,
        }});
        const payload = await response.json().catch(() => ({{ ok: false, error: 'invalid_json' }}));
        if (!response.ok || payload.ok === false) {{
          const stderr = payload.stderr ? `\\n${{payload.stderr}}` : '';
          throw new Error((payload.message || payload.error || '요청 실패') + stderr);
        }}
        return payload;
      }}

      function deltaToneClass(value) {{
        const parsed = Number.parseFloat(value || '');
        if (!Number.isFinite(parsed)) return 'delta-flat';
        if (parsed > 0.005) return 'delta-up';
        if (parsed < -0.005) return 'delta-down';
        return 'delta-flat';
      }}

      function macroToneClass(value) {{
        const macro = String(value || '').toUpperCase();
        if (macro === 'RISK_ON') return 'macro-risk-on';
        if (macro === 'RISK_OFF') return 'macro-risk-off';
        if (macro === 'PARTIAL') return 'macro-partial';
        return 'macro-mixed';
      }}

      function signalDisplay(value) {{
        const signal = String(value || '').toUpperCase();
        if (signal === 'BUY') return '매수';
        if (signal === 'SELL') return '매도';
        if (signal === 'HOLD') return '관망';
        return String(value || '-');
      }}

      function riskDisplay(value) {{
        const risk = String(value || '').toUpperCase();
        if (risk === 'HIGH') return '높음';
        if (risk === 'MEDIUM') return '보통';
        if (risk === 'LOW') return '낮음';
        return String(value || '-');
      }}

      function macroDisplay(value) {{
        const macro = String(value || '').toUpperCase();
        if (macro === 'RISK_ON') return '위험선호';
        if (macro === 'RISK_OFF') return '위험회피';
        if (macro === 'MIXED') return '혼합';
        if (macro === 'PARTIAL') return '부분';
        return String(value || '-');
      }}

      function eventTypeDisplay(value) {{
        const eventType = String(value || '').trim().toLowerCase();
        if (eventType === 'earnings') return '실적';
        if (eventType === 'regulation') return '규제';
        if (eventType === 'insider') return '내부자';
        if (eventType === 'capital') return '자본';
        return String(value || '-');
      }}

      function reasonDisplay(value) {{
        const text = String(value || '').trim();
        if (!text) return '-';
        const keyMap = {{
          confirm: '확인 지표',
          gate: '판단 게이트',
          conflict: '신호 충돌',
          regime: '시장 국면',
          events: '이벤트',
          event: '이벤트',
          macro: '매크로',
        }};
        const replacements = [
          ['RISK_OFF', '위험회피'],
          ['RISK_ON', '위험선호'],
          ['PARTIAL', '부분'],
          ['MIXED', '혼합'],
          ['BUY', '매수'],
          ['SELL', '매도'],
          ['HOLD', '관망'],
          ['HIGH', '높음'],
          ['MEDIUM', '보통'],
          ['LOW', '낮음'],
          ['UP', '상승'],
          ['DOWN', '하락'],
          ['FLAT', '횡보'],
          ['buy_blocked', '매수 차단'],
          ['sell_blocked', '매도 차단'],
          ['pass', '통과'],
          ['blocked', '차단'],
          ['earnings', '실적'],
          ['regulation', '규제'],
          ['insider', '내부자'],
          ['capital', '자본'],
          ['strong', '강함'],
          ['weak', '약함'],
        ];
        const translateFragment = (fragment) => {{
          let output = String(fragment || '');
          replacements.forEach(([source, target]) => {{
            output = output.split(source).join(target);
          }});
          return output;
        }};
        const parts = text.split(',').map((item) => item.trim()).filter(Boolean).map((item) => {{
          if (!item.includes('=')) return translateFragment(item);
          const [key, ...rest] = item.split('=');
          const valueText = translateFragment(rest.join('=').trim());
          return `${{keyMap[key.trim()] || key.trim()}}: ${{valueText}}`;
        }});
        return parts.length ? parts.join(' / ') : translateFragment(text);
      }}

      function eventToneClass(value) {{
        const eventType = String(value || '').trim().toLowerCase();
        if (eventType === 'earnings') return 'event-earnings';
        if (eventType === 'regulation') return 'event-regulation';
        if (eventType === 'insider') return 'event-insider';
        if (eventType === 'capital') return 'event-capital';
        return 'event-generic';
      }}

      const sorters = {{
        composite: (a, b) => parseNum(b.dataset.composite) - parseNum(a.dataset.composite),
        confidence: (a, b) => parseNum(b.dataset.confidence) - parseNum(a.dataset.confidence),
        strict_status: (a, b) =>
          (parseNum(b.dataset.strictEligible) - parseNum(a.dataset.strictEligible)) ||
          (parseNum(b.dataset.strictFutureTicks) - parseNum(a.dataset.strictFutureTicks)) ||
          (parseNum(b.dataset.ts) - parseNum(a.dataset.ts)),
        composite_delta: (a, b) => parseNum(b.dataset.compositeDelta) - parseNum(a.dataset.compositeDelta),
        confidence_delta: (a, b) => parseNum(b.dataset.confidenceDelta) - parseNum(a.dataset.confidenceDelta),
        latest: (a, b) => parseNum(b.dataset.ts) - parseNum(a.dataset.ts),
        ticker: (a, b) => (a.dataset.ticker || '').localeCompare(b.dataset.ticker || ''),
      }};

      function matches(element, query) {{
        const signalOk = activeSignal === 'ALL' || (element.dataset.signal || '') === activeSignal;
        const macroOk = activeMacroEnv === 'ALL' || (element.dataset.macroEnv || '').toUpperCase() === activeMacroEnv;
        const riskOk = !riskHighOnly || (element.dataset.risk || '').toUpperCase() === 'HIGH';
        const eventOk = !eventOnly || (element.dataset.hasEvents || '') === '1';
        const strictOk = !strictEligibleOnly || (element.dataset.strictEligible || '') === '1';
        const eventTypes = (element.dataset.eventTypes || '').split(',').filter(Boolean);
        const eventTypeOk = activeEventType === 'ALL' || eventTypes.includes(activeEventType);
        const searchOk = !query || (element.dataset.search || '').includes(query);
        return signalOk && macroOk && riskOk && eventOk && strictOk && eventTypeOk && searchOk;
      }}

      function escapeHtml(value) {{
        return String(value ?? '')
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#39;');
      }}

      function renderFilterSummary(query) {{
        const sortLabels = {{
          composite: '정렬 종합 점수',
          confidence: '정렬 신뢰도',
          strict_status: '정렬 엄격 기준 상태',
          composite_delta: '정렬 점수 변화량',
          confidence_delta: '정렬 신뢰도 변화량',
          latest: '정렬 최신순',
          ticker: '정렬 티커순',
        }};
        const chips = [];
        if (activeSignal !== 'ALL') chips.push(`신호 ${{signalDisplay(activeSignal)}}`);
        if (activeMacroEnv !== 'ALL') chips.push(`매크로 ${{macroDisplay(activeMacroEnv)}}`);
        if (activeEventType !== 'ALL') chips.push(`이벤트 타입 ${{eventTypeDisplay(activeEventType)}}`);
        if (riskHighOnly) chips.push('리스크 높음만');
        if (eventOnly) chips.push('이벤트 있는 종목만');
        if (strictEligibleOnly) chips.push('엄격 기준 가능만');
        if (query) chips.push(`검색 ${{query}}`);
        if ((sortSelect.value || 'composite') !== 'composite') {{
          chips.push(sortLabels[sortSelect.value] || `정렬 ${{sortSelect.value}}`);
        }}
        if (!chips.length) {{
          chips.push('기본 보기');
        }}
        filterSummaryBar.innerHTML = `
          <span class="filter-summary-label">현재 필터</span>
          <div class="filter-chips">
            ${{chips.map((item) => `<span class="filter-chip">${{escapeHtml(item)}}</span>`).join('')}}
          </div>
        `;
      }}

      function renderNewsList(news) {{
        if (!news.length) {{
          detailNewsList.innerHTML = '<p class="detail-empty">최근 뉴스가 없습니다.</p>';
          return;
        }}
        detailNewsList.innerHTML = news.map((item) => {{
          const title = escapeHtml(item.title || '제목 없음');
          const summary = escapeHtml(item.summary || item.publisher || '요약 없음');
          const url = String(item.link || item.url || '').trim();
          if (url) {{
            const safeUrl = escapeHtml(url);
            return `<article class="detail-news-item"><a class="detail-news-link" href="${{safeUrl}}" target="_blank" rel="noreferrer"><strong>${{title}}</strong><p>${{summary}}</p></a></article>`;
          }}
          return `<article class="detail-news-item"><strong>${{title}}</strong><p>${{summary}}</p></article>`;
        }}).join('');
      }}

      function renderEventList(events) {{
        if (!events.length) {{
          detailEventList.innerHTML = '<p class="detail-empty">이벤트가 없습니다.</p>';
          return;
        }}
        detailEventList.innerHTML = events.map((item) => {{
          const rawType = String(item.event_type || 'unknown').trim().toLowerCase();
          const eventType = escapeHtml(eventTypeDisplay(rawType || 'unknown'));
          const sentiment = escapeHtml(item.sentiment ?? '-');
          const importance = escapeHtml(item.importance || '-');
          const note = escapeHtml(item.note || item.source_title || '메모 없음');
          return `<article class="detail-event-item"><div class="detail-event-head"><span class="event ${{eventToneClass(rawType)}}">${{eventType}}</span><span class="detail-event-meta">감성 ${{sentiment}}</span><span class="detail-event-meta">중요도 ${{importance}}</span></div><p>${{note}}</p></article>`;
        }}).join('');
      }}

      function renderAlertList(alerts) {{
        if (!alerts.length) {{
          detailAlertList.innerHTML = '<p class="detail-empty">최근 알림 이력이 없습니다.</p>';
          return;
        }}
        detailAlertList.innerHTML = alerts.map((item) => {{
          const signal = escapeHtml(signalDisplay(item.signal || 'HOLD'));
          const confidence = escapeHtml(item.confidence ?? '-');
          const ts = escapeHtml(item.ts || '-');
          const reason = escapeHtml(reasonDisplay(item.reason || '-'));
          const sent = escapeHtml(item.sent || '-');
          return `<article class="detail-alert-item"><strong>${{ts}} / ${{signal}} / 신뢰도 ${{confidence}}</strong><p>${{sent}} | ${{reason}}</p></article>`;
        }}).join('');
      }}

      function renderSparkline(values) {{
        const points = (Array.isArray(values) ? values : []).map((value) => Number.parseFloat(value)).filter((value) => Number.isFinite(value));
        const width = 320;
        const height = 86;
        if (points.length < 2) {{
          detailSparklineWrap.innerHTML = "<svg viewBox='0 0 320 86' class='sparkline' aria-hidden='true'><line x1='0' y1='76' x2='320' y2='76' stroke='rgba(23,20,17,0.14)' stroke-width='2' /></svg>";
          return;
        }}
        const low = Math.min(...points);
        const high = Math.max(...points);
        const span = (high - low) || 1;
        const step = width / Math.max(points.length - 1, 1);
        const coords = points.map((value, index) => {{
          const x = (index * step).toFixed(2);
          const y = (height - 8 - (((value - low) / span) * (height - 16))).toFixed(2);
          return `${{x}},${{y}}`;
        }});
        const area = [`0,${{height}}`, ...coords, `${{width}},${{height}}`].join(' ');
        const line = coords.join(' ');
        const last = coords[coords.length - 1].split(',');
        detailSparklineWrap.innerHTML = `<svg viewBox="0 0 ${{width}} ${{height}}" class="sparkline" aria-hidden="true"><polyline points="${{area}}" fill="rgba(31,111,120,0.10)" stroke="none" /><polyline points="${{line}}" fill="none" stroke="#1f6f78" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" /><circle cx="${{last[0]}}" cy="${{last[1]}}" r="3.5" fill="#1f6f78" /></svg>`;
      }}

      function setDetail(card) {{
        if (!card) return;
        cards.forEach((item) => item.classList.toggle('is-active', item === card));
        rows.forEach((item) => item.classList.toggle('is-active', item === card));
        let payload = {{}};
        try {{
          payload = JSON.parse(card.dataset.detail || '{{}}');
        }} catch (_error) {{
          payload = {{}};
        }}
        const signal = payload.signal || card.dataset.signal || 'HOLD';
        detailTicker.textContent = payload.ticker || card.dataset.ticker || '-';
        detailTimestamp.textContent = payload.ts || '-';
        detailComposite.textContent = payload.composite_score || '-';
        detailConfidence.textContent = payload.confidence || '-';
        detailRisk.textContent = riskDisplay(payload.risk_level || '-');
        detailMomentum.textContent = payload.momentum || '-';
        detailMacroEnvironment.textContent = macroDisplay(payload.macro_environment || '-');
        detailMacroEnvironment.className = `macro-pill ${{macroToneClass(payload.macro_environment)}}`;
        detailSignalSource.textContent = payload.signal_source || '-';
        detailStrictEligible.textContent = payload.strict_label || '엄격 기준 불가';
        detailStrictEligible.className = `value strict-chip ${{payload.strict_eligible ? 'strict-ready' : 'strict-wait'}}`;
        detailPrice.textContent = payload.price || '-';
        detailRsi.textContent = payload.rsi || '-';
        detailSmaFast.textContent = payload.sma_fast || '-';
        detailSmaSlow.textContent = payload.sma_slow || '-';
        detailCompositeDelta.textContent = payload.composite_delta || '-';
        detailConfidenceDelta.textContent = payload.confidence_delta || '-';
        detailCompositeDelta.className = `value delta ${{deltaToneClass(payload.composite_delta)}}`;
        detailConfidenceDelta.className = `value delta ${{deltaToneClass(payload.confidence_delta)}}`;
        detailChartScore.textContent = payload.chart_score || '-';
        detailMacroScore.textContent = payload.macro_score || '-';
        detailEventScore.textContent = payload.event_score || '-';
        detailNewsScore.textContent = payload.news_score || '-';
        detailReason.textContent = payload.reason || '-';
        detailSignal.textContent = signalDisplay(signal);
        detailSignal.className = `badge ${{(signal || 'HOLD').toLowerCase()}}`;
        renderSparkline(Array.isArray(payload.price_history) ? payload.price_history : []);
        renderNewsList(Array.isArray(payload.news) ? payload.news : []);
        renderEventList(Array.isArray(payload.events) ? payload.events : []);
        renderAlertList(Array.isArray(payload.alerts) ? payload.alerts : []);
      }}

      function applyFilters() {{
        const query = (searchBox.value || '').trim().toLowerCase();
        const sorter = sorters[sortSelect.value] || sorters.composite;

        cards.sort(sorter).forEach((card) => {{
          card.classList.toggle('is-hidden', !matches(card, query));
          cardGrid.appendChild(card);
        }});

        rows.sort(sorter).forEach((row) => {{
          row.classList.toggle('is-hidden', !matches(row, query));
          tableBody.appendChild(row);
        }});

        const visibleCards = cards.filter((card) => !card.classList.contains('is-hidden'));
        const visibleRows = rows.filter((row) => !row.classList.contains('is-hidden'));
        const buyVisible = visibleCards.filter((card) => (card.dataset.signal || '') === 'BUY').length;
        const sellVisible = visibleCards.filter((card) => (card.dataset.signal || '') === 'SELL').length;
        const holdVisible = visibleCards.filter((card) => (card.dataset.signal || '') === 'HOLD').length;
        const avgVisibleConfidence = visibleCards.length
          ? visibleCards.reduce((sum, card) => sum + parseNum(card.dataset.confidence), 0) / visibleCards.length
          : 0;

        visibleCardCount.textContent = String(visibleCards.length);
        visibleRowCount.textContent = String(visibleRows.length);
        metaTickerCount.textContent = String(visibleCards.length);
        summaryBuyCount.textContent = String(buyVisible);
        summarySellCount.textContent = String(sellVisible);
        summaryHoldCount.textContent = String(holdVisible);
        summaryAvgConfidence.textContent = avgVisibleConfidence.toFixed(1) + '점';
        renderFilterSummary(query);
      }}

      workspaceTabs.forEach((tab) => {{
        tab.addEventListener('click', () => {{
          setMainView(tab.dataset.mainView || 'realtime');
        }});
      }});

      signalTabs.forEach((tab) => {{
        tab.addEventListener('click', () => {{
          activeSignal = tab.dataset.filterSignal || 'ALL';
          saveSignalPreference(activeSignal);
          signalTabs.forEach((item) => item.classList.toggle('active', item === tab));
          applyFilters();
        }});
      }});

      macroTabs.forEach((tab) => {{
        tab.addEventListener('click', () => {{
          activeMacroEnv = tab.dataset.filterMacro || 'ALL';
          saveMacroPreference(activeMacroEnv);
          macroTabs.forEach((item) => item.classList.toggle('active', item === tab));
          applyFilters();
        }});
      }});

      riskHighToggle.addEventListener('click', () => {{
        riskHighOnly = !riskHighOnly;
        riskHighToggle.classList.toggle('active', riskHighOnly);
        saveRiskHighPreference(riskHighOnly);
        applyFilters();
      }});

      eventOnlyToggle.addEventListener('click', () => {{
        eventOnly = !eventOnly;
        eventOnlyToggle.classList.toggle('active', eventOnly);
        saveEventOnlyPreference(eventOnly);
        applyFilters();
      }});

      strictEligibleToggle.addEventListener('click', () => {{
        strictEligibleOnly = !strictEligibleOnly;
        strictEligibleToggle.classList.toggle('active', strictEligibleOnly);
        saveStrictEligiblePreference(strictEligibleOnly);
        applyFilters();
      }});

      eventTypeTabs.forEach((tab) => {{
        tab.addEventListener('click', () => {{
          activeEventType = tab.dataset.filterEventType || 'ALL';
          saveEventTypePreference(activeEventType);
          eventTypeTabs.forEach((item) => item.classList.toggle('active', item === tab));
          applyFilters();
        }});
      }});

      cards.forEach((card) => {{
        card.addEventListener('click', () => setDetail(card));
      }});

      rows.forEach((row) => {{
        row.addEventListener('click', () => setDetail(row));
      }});

      strictEligibleOnly = loadStrictEligiblePreference();
      riskHighOnly = loadRiskHighPreference();
      eventOnly = loadEventOnlyPreference();
      activeSignal = loadSignalPreference();
      activeMacroEnv = loadMacroPreference();
      activeEventType = loadEventTypePreference();
      sortSelect.value = loadSortPreference() || sortSelect.value;
      searchBox.value = loadSearchPreference();
      if (!signalTabs.some((item) => (item.dataset.filterSignal || 'ALL') === activeSignal)) activeSignal = 'ALL';
      if (!macroTabs.some((item) => (item.dataset.filterMacro || 'ALL') === activeMacroEnv)) activeMacroEnv = 'ALL';
      if (!eventTypeTabs.some((item) => (item.dataset.filterEventType || 'ALL') === activeEventType)) activeEventType = 'ALL';
      signalTabs.forEach((item) => item.classList.toggle('active', (item.dataset.filterSignal || 'ALL') === activeSignal));
      macroTabs.forEach((item) => item.classList.toggle('active', (item.dataset.filterMacro || 'ALL') === activeMacroEnv));
      eventTypeTabs.forEach((item) => item.classList.toggle('active', (item.dataset.filterEventType || 'ALL') === activeEventType));
      riskHighToggle.classList.toggle('active', riskHighOnly);
      eventOnlyToggle.classList.toggle('active', eventOnly);
      strictEligibleToggle.classList.toggle('active', strictEligibleOnly);

      resetDashboardState.addEventListener('click', () => {{
        clearDashboardPreferences();
        activeSignal = 'ALL';
        activeMacroEnv = 'ALL';
        activeEventType = 'ALL';
        riskHighOnly = false;
        eventOnly = false;
        strictEligibleOnly = false;
        searchBox.value = '';
        sortSelect.value = 'composite';
        signalTabs.forEach((item) => item.classList.toggle('active', (item.dataset.filterSignal || 'ALL') === 'ALL'));
        macroTabs.forEach((item) => item.classList.toggle('active', (item.dataset.filterMacro || 'ALL') === 'ALL'));
        eventTypeTabs.forEach((item) => item.classList.toggle('active', (item.dataset.filterEventType || 'ALL') === 'ALL'));
        riskHighToggle.classList.remove('active');
        eventOnlyToggle.classList.remove('active');
        strictEligibleToggle.classList.remove('active');
        applyFilters();
      }});

      quickAddButton?.addEventListener('click', async () => {{
        setQuickInputMode('add');
        const inputValue = (quickAddInput?.value || '').trim();
        if (!inputValue) {{
          actionStatus.textContent = '입력값이 비어 있습니다. 예: 티커 추가 : [ ASTS ]';
          return;
        }}
        setActionBusy(true, '관심 종목을 추가하고 메인을 다시 만드는 중입니다...');
        try {{
          const payload = await callAction('/api/tickers/quick-add', inputValue);
          actionStatus.textContent = payload.message || '관심 종목 추가가 끝났습니다.';
          if (quickAddInput) quickAddInput.value = '';
          window.setTimeout(() => window.location.reload(), 900);
        }} catch (error) {{
          actionStatus.textContent = `관심 종목 추가 실패: ${{error.message || error}}`;
        }} finally {{
          setActionBusy(false);
        }}
      }});

      quickRemoveButton?.addEventListener('click', async () => {{
        setQuickInputMode('remove');
        const inputValue = (quickAddInput?.value || '').trim();
        if (!inputValue) {{
          actionStatus.textContent = '입력값이 비어 있습니다. 예: 티커 삭제 : [ ASTS ]';
          return;
        }}
        setActionBusy(true, '관심 종목을 삭제하고 메인을 다시 만드는 중입니다...');
        try {{
          const payload = await callAction('/api/tickers/quick-remove', inputValue);
          actionStatus.textContent = payload.message || '관심 종목 삭제가 끝났습니다.';
          if (quickAddInput) quickAddInput.value = '';
          window.setTimeout(() => window.location.reload(), 900);
        }} catch (error) {{
          actionStatus.textContent = `관심 종목 삭제 실패: ${{error.message || error}}`;
        }} finally {{
          setActionBusy(false);
        }}
      }});

      bulkSetButton?.addEventListener('click', async () => {{
        const market = (bulkMarketSelect?.value || 'US').trim();
        const tickers = (bulkTickerInput?.value || '').trim();
        if (!tickers) {{
          actionStatus.textContent = '일괄 반영할 티커를 입력하세요. 예: AAPL, MSFT, NVDA';
          return;
        }}
        setActionBusy(true, '시장별 티커 목록을 일괄 반영하고 메인을 다시 만드는 중입니다...');
        try {{
          const payload = await callAction('/api/tickers/bulk-set', JSON.stringify({{ market, tickers }}));
          actionStatus.textContent = payload.message || '시장별 티커 일괄 반영이 끝났습니다.';
          if (bulkTickerInput) bulkTickerInput.value = '';
          window.setTimeout(() => window.location.reload(), 900);
        }} catch (error) {{
          actionStatus.textContent = `시장별 티커 일괄 반영 실패: ${{error.message || error}}`;
        }} finally {{
          setActionBusy(false);
        }}
      }});

      bulkMarketSelect?.addEventListener('change', () => {{
        saveBulkMarketPreference((bulkMarketSelect?.value || 'US').trim());
        setBulkExampleMarket((bulkMarketSelect?.value || 'US').trim());
        renderBulkPreview();
      }});

      quickAddInput?.addEventListener('keydown', (event) => {{
        if (event.key === 'Enter') {{
          event.preventDefault();
          if (quickInputMode === 'remove') {{
            quickRemoveButton?.click();
            return;
          }}
          quickAddButton?.click();
        }}
      }});
      quickAddInput?.addEventListener('focus', () => {{
        const current = (quickAddInput.value || '').trim();
        if (current.startsWith('티커 삭제')) {{
          setQuickInputMode('remove');
          return;
        }}
        setQuickInputMode('add');
      }});
      quickAddInput?.addEventListener('input', () => {{
        const current = (quickAddInput.value || '').trim();
        if (!current) {{
          return;
        }}
        if (current.startsWith('티커 삭제') || current.includes('삭제')) {{
          setQuickInputMode('remove');
          return;
        }}
        if (current.startsWith('티커 추가') || current.includes('추가')) {{
          setQuickInputMode('add');
          return;
        }}
      }});
      quickModeAddButton?.addEventListener('click', () => {{
        setQuickInputMode('add');
        quickAddInput?.focus();
      }});
      quickModeRemoveButton?.addEventListener('click', () => {{
        setQuickInputMode('remove');
        quickAddInput?.focus();
      }});
      bulkExampleTabs.forEach((tab) => {{
        tab.addEventListener('click', () => {{
          const market = (tab.dataset.bulkExampleMarket || 'US').trim();
          if (bulkMarketSelect) bulkMarketSelect.value = market;
          saveBulkMarketPreference(market);
          setBulkExampleMarket(market);
          renderBulkPreview();
        }});
      }});
      bulkExampleCopyButton?.addEventListener('click', () => {{
        copyBulkExample();
      }});

      runLiveOnceButton?.addEventListener('click', async () => {{
        setActionBusy(true, '엔진 1회 실행 중입니다...');
        try {{
          const payload = await callAction('/api/run-live-once');
          actionStatus.textContent = payload.message || '엔진 1회 실행이 끝났습니다.';
          window.setTimeout(() => window.location.reload(), 900);
        }} catch (error) {{
          actionStatus.textContent = `엔진 1회 실행 실패: ${{error.message || error}}`;
        }} finally {{
          setActionBusy(false);
        }}
      }});

      backtestRefreshButton?.addEventListener('click', async () => {{
        setActionBusy(true, '백테스트 갱신을 시작합니다...');
        try {{
          const payload = await callAction('/api/backtest-refresh');
          actionStatus.textContent = payload.message || '백테스트 갱신을 시작했습니다.';
        }} catch (error) {{
          actionStatus.textContent = `백테스트 갱신 실패: ${{error.message || error}}`;
        }} finally {{
          setActionBusy(false);
        }}
      }});

      refreshMainButton?.addEventListener('click', async () => {{
        setActionBusy(true, '메인을 다시 만드는 중입니다...');
        try {{
          const payload = await callAction('/api/dashboard-refresh');
          actionStatus.textContent = payload.message || '메인을 다시 만들었습니다.';
          window.setTimeout(() => window.location.reload(), 700);
        }} catch (error) {{
          actionStatus.textContent = `메인 갱신 실패: ${{error.message || error}}`;
        }} finally {{
          setActionBusy(false);
        }}
      }});

      searchBox.addEventListener('input', () => {{
        saveSearchPreference(searchBox.value || '');
        applyFilters();
      }});
      sortSelect.addEventListener('change', () => {{
        saveSortPreference(sortSelect.value);
        applyFilters();
      }});
      if (bulkMarketSelect) {{
        bulkMarketSelect.value = loadBulkMarketPreference();
      }}
      setMainView(loadMainViewPreference());
      setQuickInputMode('add');
      setBulkExampleMarket((bulkMarketSelect?.value || 'US').trim());
      renderBulkPreview();
      applyFilters();
      if (cards.length > 0) {{
        setDetail(cards[0]);
      }}
    }})();
  </script>
</body>
</html>
"""

report_path.write_text(html_doc, encoding="utf-8")
print(report_path)
