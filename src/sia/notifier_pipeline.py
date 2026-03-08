from __future__ import annotations

import logging
import sqlite3
from typing import Any, Callable

try:
    from . import factor_engine
    from .notifier_events import collect_ticker_news, derive_and_store_event_factors
    from .notifier_macro import collect_macro_snapshot
    from .notifier_storage import (
        count_recent_source_failures,
        infer_signal_source,
        init_db,
        is_cooldown_active,
        log_source_event,
        remaining_cooldown_seconds,
        remember_dashboard_snapshot,
        remember_event_factor,
        remember_macro_snapshot,
        remember_news,
        remember_prices,
        should_fallback_to_yahoo,
    )
except ImportError:
    import factor_engine  # type: ignore
    from notifier_events import collect_ticker_news, derive_and_store_event_factors  # type: ignore
    from notifier_macro import collect_macro_snapshot  # type: ignore
    from notifier_storage import (  # type: ignore
        count_recent_source_failures,
        infer_signal_source,
        init_db,
        is_cooldown_active,
        log_source_event,
        remaining_cooldown_seconds,
        remember_dashboard_snapshot,
        remember_event_factor,
        remember_macro_snapshot,
        remember_news,
        remember_prices,
        should_fallback_to_yahoo,
    )


logger = logging.getLogger("trading_signal_notifier")


def collect_price_points(
    conn: sqlite3.Connection,
    ticker: str,
    *,
    dry_run: bool,
    finnhub_api_key: str | None,
    finnhub_fail_threshold: int,
    finnhub_fail_window_minutes: int,
    mock_prices_fn: Callable[[str, int], list[Any]],
    fetch_finnhub_closes_fn: Callable[[str, str], list[Any]],
    fetch_yahoo_closes_fn: Callable[[str], list[Any]],
) -> tuple[str, list[Any]]:
    close_source = "mock" if dry_run else "finnhub"
    if dry_run:
        return close_source, mock_prices_fn(ticker, 40)

    if finnhub_api_key:
        if should_fallback_to_yahoo(
            conn,
            ticker,
            fail_threshold=finnhub_fail_threshold,
            fail_window_minutes=finnhub_fail_window_minutes,
        ):
            recent_failures = count_recent_source_failures(
                conn,
                ticker,
                source="finnhub",
                event="price-fetch",
                window_minutes=finnhub_fail_window_minutes,
            )
            close_source = "finnhub-emailed-failover-yahoo"
            log_source_event(
                conn,
                "price-fetch",
                ticker,
                source="finnhub",
                ok=True,
                level="WARN",
                message=(
                    "연속 실패로 finnhub 폴백"
                    f" failures={recent_failures}"
                    f"/{finnhub_fail_threshold}"
                    f" window_min={finnhub_fail_window_minutes}"
                ),
                sent=0,
            )
            return close_source, fetch_yahoo_closes_fn(ticker)

        try:
            closes_points = fetch_finnhub_closes_fn(ticker, finnhub_api_key)
            close_source = "finnhub-candle"
            log_source_event(
                conn,
                "price-fetch",
                ticker,
                source="finnhub",
                ok=True,
                message="ok",
                sent=0,
            )
            return close_source, closes_points
        except RuntimeError as exc:
            warning_reason = "차트 조회 실패"
            exc_text = str(exc)
            if "FINNHUB_CANDLE_ACCESS_DENIED" in exc_text:
                warning_reason = "차트 조회 권한/요금제 제한"
            log_source_event(
                conn,
                "price-fetch",
                ticker,
                source="finnhub",
                ok=False,
                level="ERROR",
                message=exc_text,
                sent=0,
            )
            logger.warning(
                "finnhub candle 실패: %s (%s), yahoo로 폴백",
                ticker,
                warning_reason,
            )
            try:
                closes_points = fetch_yahoo_closes_fn(ticker)
                close_source = "finnhub-fallback-yahoo"
                log_source_event(
                    conn,
                    "price-fetch-fallback",
                    ticker,
                    source="yahoo",
                    ok=True,
                    level="INFO",
                    message=f"from_finnhub_fail: {warning_reason} ({exc_text})",
                    sent=0,
                )
                return close_source, closes_points
            except Exception as fallback_exc:
                log_source_event(
                    conn,
                    "price-fetch-fallback",
                    ticker,
                    source="yahoo",
                    ok=False,
                    level="ERROR",
                    message=f"finnhub_fail={exc};yahoo_fail={fallback_exc}",
                    sent=0,
                )
                raise

    try:
        return "yahoo", fetch_yahoo_closes_fn(ticker)
    except Exception as exc:
        log_source_event(
            conn,
            "price-fetch",
            ticker,
            source="yahoo",
            ok=False,
            level="ERROR",
            message=str(exc),
            sent=0,
        )
        raise
