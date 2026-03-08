from __future__ import annotations

import sqlite3
from typing import Any, Callable

try:
    from .notifier_storage import log_source_event, remember_macro_snapshot
except ImportError:
    from notifier_storage import log_source_event, remember_macro_snapshot  # type: ignore


def _safe_last_close(
    fetch_yahoo_closes_fn: Callable[..., list[Any]],
    ticker: str,
) -> float | None:
    try:
        points = fetch_yahoo_closes_fn(ticker, 5)
    except Exception:
        return None
    if not points:
        return None
    value = getattr(points[-1], "close", None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_treasury_10y(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 10.0 if value >= 20.0 else value


def collect_macro_snapshot(
    conn: sqlite3.Connection,
    *,
    dry_run: bool,
    fetch_yahoo_closes_fn: Callable[..., list[Any]],
) -> dict[str, float | None]:
    if dry_run:
        snapshot = {
            "vix": 18.5,
            "treasury_10y": 4.1,
            "cpi_yoy": 2.8,
            "dollar_index": 103.2,
            "crude_oil": 78.4,
        }
        remember_macro_snapshot(conn, snapshot, source="mock")
        return snapshot

    snapshot = {
        "vix": _safe_last_close(fetch_yahoo_closes_fn, "^VIX"),
        "treasury_10y": _normalize_treasury_10y(_safe_last_close(fetch_yahoo_closes_fn, "^TNX")),
        "cpi_yoy": _safe_last_close(fetch_yahoo_closes_fn, "CPIAUCSL"),
        "dollar_index": _safe_last_close(fetch_yahoo_closes_fn, "DX-Y.NYB"),
        "crude_oil": _safe_last_close(fetch_yahoo_closes_fn, "CL=F"),
    }
    remember_macro_snapshot(conn, snapshot, source="yahoo")
    log_source_event(
        conn,
        "macro-fetch",
        "MACRO",
        source="yahoo",
        ok=any(value is not None for value in snapshot.values()),
        level="INFO",
        message=("vix={vix},10y={treasury_10y},cpi={cpi_yoy},dxy={dollar_index},oil={crude_oil}").format(**snapshot),
        sent=0,
    )
    return snapshot
