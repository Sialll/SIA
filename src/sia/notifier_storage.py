from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from . import factor_engine
except ImportError:
    import factor_engine  # type: ignore


logger = logging.getLogger("trading_signal_notifier")

SIGNAL_SOURCE_MATCH_WINDOW_SECONDS = 60 * 30
SIGNAL_SOURCE_FALLBACK_WINDOW_SECONDS = 60 * 60 * 24
SIGNAL_SOURCE_MATCH_TOLERANCE = 0.08


def init_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_ticks (
                ticker TEXT NOT NULL,
                ts INTEGER NOT NULL,
                source TEXT NOT NULL,
                close REAL NOT NULL,
                PRIMARY KEY (ticker, ts, source)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                news_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                published INTEGER NOT NULL,
                source_url TEXT,
                title TEXT NOT NULL,
                summary TEXT,
                impact TEXT,
                score REAL,
                keywords TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                sent INTEGER NOT NULL,
                error_message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS macro_snapshots (
                ts INTEGER NOT NULL,
                source TEXT NOT NULL,
                vix REAL,
                treasury_10y REAL,
                cpi_yoy REAL,
                dollar_index REAL,
                crude_oil REAL,
                raw_json TEXT,
                PRIMARY KEY (ts, source)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_factors (
                ticker TEXT NOT NULL,
                ts INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                sentiment REAL NOT NULL,
                impact TEXT NOT NULL,
                confidence REAL NOT NULL,
                source_title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                raw_json TEXT,
                PRIMARY KEY (ticker, event_type, ts, source_url)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                price REAL NOT NULL,
                sma_fast REAL,
                sma_slow REAL,
                rsi REAL,
                chart_score REAL NOT NULL,
                macro_score REAL NOT NULL,
                event_score REAL NOT NULL,
                news_score REAL NOT NULL,
                composite_score REAL NOT NULL,
                risk_level TEXT NOT NULL,
                momentum TEXT NOT NULL,
                macro_environment TEXT NOT NULL,
                signal_source TEXT,
                reason TEXT NOT NULL,
                news_json TEXT,
                event_factors_json TEXT
            )
            """
        )
        dashboard_columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(dashboard_snapshots)").fetchall()
        }
        if "signal_source" not in dashboard_columns:
            conn.execute("ALTER TABLE dashboard_snapshots ADD COLUMN signal_source TEXT")


def infer_signal_source(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    snapshot_ts: int,
    snapshot_price: float,
) -> str | None:
    if snapshot_price <= 0:
        return None
    def pick_best(rows: list[tuple[Any, Any, Any]]) -> tuple[float, int, int, str] | None:
        best_match: tuple[float, int, int, str] | None = None
        for source, point_ts, close in rows:
            try:
                close_value = float(close)
            except (TypeError, ValueError):
                continue
            if close_value <= 0:
                continue
            gap = abs((close_value / snapshot_price) - 1.0)
            if gap > SIGNAL_SOURCE_MATCH_TOLERANCE:
                continue
            source_name = str(source)
            source_penalty = 1 if source_name == "mock" else 0
            candidate = (gap, source_penalty, abs(int(point_ts) - snapshot_ts), source_name)
            if best_match is None or candidate < best_match:
                best_match = candidate
        return best_match

    primary_rows = conn.execute(
        """
        SELECT source, ts, close
        FROM price_ticks
        WHERE ticker = ?
          AND ts BETWEEN ? AND ?
        ORDER BY ts ASC
        """,
        (
            ticker,
            snapshot_ts - SIGNAL_SOURCE_MATCH_WINDOW_SECONDS,
            snapshot_ts + SIGNAL_SOURCE_MATCH_WINDOW_SECONDS,
        ),
    ).fetchall()
    best_match = pick_best(primary_rows)
    if best_match is None:
        fallback_rows = conn.execute(
            """
            SELECT source, ts, close
            FROM price_ticks
            WHERE ticker = ?
              AND ts BETWEEN ? AND ?
            ORDER BY ts DESC
            """,
            (
                ticker,
                snapshot_ts - SIGNAL_SOURCE_FALLBACK_WINDOW_SECONDS,
                snapshot_ts,
            ),
        ).fetchall()
        best_match = pick_best(fallback_rows)
    return None if best_match is None else best_match[3]


def build_news_id(ticker: str, source_url: str, published: int, title: str) -> str:
    return hashlib.sha1(f"{ticker}:{source_url}:{published}:{title}".encode("utf-8")).hexdigest()


def log_source_event(
    conn: sqlite3.Connection,
    event: str,
    ticker: str,
    *,
    source: str,
    ok: bool,
    level: str | None = None,
    message: str = "",
    sent: int | None = None,
) -> None:
    normalized_level = (level or ("INFO" if ok else "ERROR")).upper()
    if normalized_level not in {"INFO", "WARN", "WARNING", "ERROR", "OK"}:
        normalized_level = "INFO"
    signal_level = "ERROR" if not ok or normalized_level == "ERROR" else "INFO"
    reason = f"source={source}|event={event}|ok={ok}|level={normalized_level}|msg={message}"
    conn.execute(
        "INSERT INTO alerts (ts, ticker, signal, confidence, reason, sent, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            int(time.time()),
            ticker,
            signal_level,
            0.0,
            reason,
            0 if sent is None else sent,
            None if ok else message,
        ),
    )


def remember_prices(
    conn: sqlite3.Connection,
    ticker: str,
    points: list[Any],
    *,
    source: str = "finnhub",
) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO price_ticks (ticker, ts, source, close) VALUES (?, ?, ?, ?)",
        [(ticker, p.ts, source, p.close) for p in points],
    )


def remember_news(
    conn: sqlite3.Connection,
    ticker: str,
    item: Any,
    *,
    source_url: str,
) -> bool:
    news_id = build_news_id(
        ticker,
        source_url,
        int(getattr(item, "published")),
        str(getattr(item, "title")),
    )
    with contextlib.suppress(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO news_items (news_id, ticker, published, source_url, title, summary, impact, score, keywords, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news_id,
                ticker,
                int(getattr(item, "published")),
                source_url,
                str(getattr(item, "title")),
                str(getattr(item, "summary")),
                str(getattr(item, "impact")),
                float(getattr(item, "score")),
                ",".join(list(getattr(item, "keywords"))),
                json.dumps(getattr(item, "__dict__", {}), ensure_ascii=False),
            ),
        )
        return True
    return False


def remember_macro_snapshot(
    conn: sqlite3.Connection,
    snapshot: dict[str, float | None],
    *,
    source: str,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO macro_snapshots (
            ts, source, vix, treasury_10y, cpi_yoy, dollar_index, crude_oil, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            int(time.time()),
            source,
            snapshot.get("vix"),
            snapshot.get("treasury_10y"),
            snapshot.get("cpi_yoy"),
            snapshot.get("dollar_index"),
            snapshot.get("crude_oil"),
            json.dumps(snapshot, ensure_ascii=False),
        ),
    )


def remember_event_factor(
    conn: sqlite3.Connection,
    ticker: str,
    event_factor: factor_engine.EventFactor,
    *,
    published: int,
    source_title: str,
    source_url: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO event_factors (
            ticker, ts, event_type, sentiment, impact, confidence, source_title, source_url, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker,
            published,
            event_factor.event_type,
            event_factor.sentiment,
            event_factor.impact,
            event_factor.confidence,
            source_title,
            source_url,
            json.dumps(
                {
                    "ticker": ticker,
                    "ts": published,
                    "event_type": event_factor.event_type,
                    "sentiment": event_factor.sentiment,
                    "impact": event_factor.impact,
                    "confidence": event_factor.confidence,
                    "source_title": source_title,
                    "source_url": source_url,
                },
                ensure_ascii=False,
            ),
        ),
    )


def remember_dashboard_snapshot(
    conn: sqlite3.Connection,
    signal: Any,
    *,
    latest_news: list[Any],
    event_factors: list[factor_engine.EventFactor],
) -> None:
    ts = int(time.time())
    ticker = str(getattr(signal, "ticker"))
    price = float(getattr(signal, "price"))
    news_json = json.dumps(
        [
            {
                "title": str(getattr(item, "title", "")),
                "published": int(getattr(item, "published", ts)),
                "url": str(getattr(item, "url", "")),
                "impact": str(getattr(item, "impact", "neutral")),
                "score": float(getattr(item, "score", 0.0)),
                "summary": str(getattr(item, "summary", "")),
            }
            for item in latest_news[:5]
        ],
        ensure_ascii=False,
    )
    event_json = json.dumps(
        [
            {
                "event_type": item.event_type,
                "sentiment": item.sentiment,
                "impact": item.impact,
                "confidence": item.confidence,
            }
            for item in event_factors
        ],
        ensure_ascii=False,
    )
    signal_source = getattr(signal, "signal_source", None) or infer_signal_source(
        conn,
        ticker=ticker,
        snapshot_ts=ts,
        snapshot_price=price,
    )
    conn.execute(
        """
        INSERT INTO dashboard_snapshots (
            ts, ticker, signal, confidence, price, sma_fast, sma_slow, rsi,
            chart_score, macro_score, event_score, news_score, composite_score,
            risk_level, momentum, macro_environment, signal_source, reason, news_json, event_factors_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ts,
            ticker,
            str(getattr(signal, "signal")),
            float(getattr(signal, "confidence")),
            price,
            getattr(signal, "sma_fast"),
            getattr(signal, "sma_slow"),
            getattr(signal, "rsi"),
            float(getattr(signal, "chart_score", 0.0)),
            float(getattr(signal, "macro_score", 0.0)),
            float(getattr(signal, "event_score", 0.0)),
            float(getattr(signal, "news_score", 0.0)),
            float(getattr(signal, "composite_score", 0.0)),
            str(getattr(signal, "risk_level", "LOW")),
            str(getattr(signal, "momentum", "FLAT")),
            str(getattr(signal, "macro_environment", "UNMODELED")),
            signal_source,
            str(getattr(signal, "reason", "")),
            news_json,
            event_json,
        ),
    )


def count_recent_source_failures(
    conn: sqlite3.Connection,
    ticker: str,
    source: str,
    event: str,
    *,
    window_minutes: int,
) -> int:
    if window_minutes <= 0:
        return 0

    cutoff = int((datetime.now(timezone.utc) - timedelta(minutes=window_minutes)).timestamp())
    row = conn.execute(
        """
        SELECT COUNT(*) FROM alerts
        WHERE ticker = ?
          AND signal = 'ERROR'
          AND ts >= ?
          AND reason LIKE ?
          AND reason LIKE ?
          AND reason LIKE ?
        """,
        (
            ticker,
            cutoff,
            f"%source={source}%",
            f"%event={event}%",
            "%ok=False%",
        ),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def should_fallback_to_yahoo(
    conn: sqlite3.Connection,
    ticker: str,
    *,
    fail_threshold: int,
    fail_window_minutes: int,
    source: str = "finnhub",
    event: str = "price-fetch",
) -> bool:
    if fail_threshold <= 0:
        return False
    failures = count_recent_source_failures(
        conn,
        ticker,
        source=source,
        event=event,
        window_minutes=fail_window_minutes,
    )
    return failures >= fail_threshold


def is_cooldown_active(
    conn: sqlite3.Connection,
    ticker: str,
    signal: str,
    cooldown_minutes: int,
) -> int | None:
    window = int((datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).timestamp())
    row = conn.execute(
        """
        SELECT ts FROM alerts
        WHERE ticker = ? AND signal = ? AND ts >= ?
        ORDER BY ts DESC LIMIT 1
        """,
        (ticker, signal, window),
    ).fetchone()
    if row is None:
        return None
    return int(row[0])


def remaining_cooldown_seconds(last_signal_ts: int, cooldown_minutes: int) -> int:
    release_at = last_signal_ts + max(1, cooldown_minutes) * 60
    return max(0, release_at - int(time.time()))
