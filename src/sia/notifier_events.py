from __future__ import annotations

import sqlite3
import time
from typing import Any, Callable

try:
    from . import factor_engine
    from .notifier_storage import log_source_event, remember_event_factor, remember_news
except ImportError:
    import factor_engine  # type: ignore
    from notifier_storage import log_source_event, remember_event_factor, remember_news  # type: ignore


def collect_ticker_news(
    conn: sqlite3.Connection,
    ticker: str,
    *,
    dry_run: bool,
    max_news_per_ticker: int,
    news_lookback_hours: int,
    marketaux_api_key: str | None,
    ollama_host: str,
    ollama_model: str,
    mock_news_fn: Callable[[str, int], list[Any]],
    fetch_marketaux_news_fn: Callable[..., list[dict[str, Any]]],
    fetch_yahoo_rss_news_fn: Callable[..., list[dict[str, Any]]],
    collect_news_items_fn: Callable[..., list[Any]],
) -> list[Any]:
    latest_news: list[Any] = []

    if dry_run:
        raw_news = mock_news_fn(ticker, max_news_per_ticker)
        for item in raw_news:
            remember_news(
                conn,
                ticker,
                item,
                source_url=str(getattr(item, "url", "")),
            )
            latest_news.append(item)
        return latest_news

    if max_news_per_ticker <= 0:
        log_source_event(
            conn,
            "news-fetch",
            ticker,
            source="disabled",
            ok=False,
            message="뉴스 비활성화(max_news_per_ticker=0)",
            sent=0,
        )
        return latest_news

    if marketaux_api_key:
        source_used = "marketaux"
        try:
            raw_news = fetch_marketaux_news_fn(
                ticker,
                marketaux_api_key,
                limit=max_news_per_ticker,
                lookback_hours=news_lookback_hours,
            )
            if not raw_news:
                source_used = "marketaux-empty"
                raw_news = fetch_yahoo_rss_news_fn(
                    ticker,
                    limit=max_news_per_ticker,
                    lookback_hours=news_lookback_hours,
                )
        except Exception:
            source_used = "marketaux-failed->yahoo"
            raw_news = fetch_yahoo_rss_news_fn(
                ticker,
                limit=max_news_per_ticker,
                lookback_hours=news_lookback_hours,
            )
        log_source_event(
            conn,
            "news-fetch",
            ticker,
            source=source_used,
            ok=bool(raw_news),
            message=f"marketaux_key={'on' if marketaux_api_key else 'off'}",
            sent=0,
        )
        return collect_news_items_fn(
            conn,
            ticker,
            raw_news,
            ollama_host=ollama_host,
            ollama_model=ollama_model,
        )

    source_used = "yahoo-rss"
    try:
        raw_news = fetch_yahoo_rss_news_fn(
            ticker,
            limit=max_news_per_ticker,
            lookback_hours=news_lookback_hours,
        )
    except Exception:
        source_used = "yahoo-rss-failed"
        raw_news = []
    latest_news = collect_news_items_fn(
        conn,
        ticker,
        raw_news,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
    )
    log_source_event(
        conn,
        "news-fetch",
        ticker,
        source=source_used,
        ok=bool(raw_news),
        message="marketaux key 없음",
        sent=0,
    )
    return latest_news


def derive_and_store_event_factors(
    conn: sqlite3.Connection,
    ticker: str,
    latest_news: list[Any],
) -> list[factor_engine.EventFactor]:
    event_rules = [
        ("earnings", ("earnings", "guidance", "eps", "revenue", "beat", "miss")),
        ("regulation", ("regulation", "antitrust", "lawsuit", "probe", "investigation", "sec")),
        ("insider", ("insider", "director", "ceo", "cfo", "officer", "buys shares", "sells shares")),
        ("capital", ("dividend", "buyback", "repurchase", "offering", "secondary", "dilution")),
    ]

    output: list[factor_engine.EventFactor] = []
    seen_types: set[str] = set()
    for item in latest_news[:5]:
        title = str(getattr(item, "title", ""))
        summary = str(getattr(item, "summary", ""))
        text = f"{title} {summary}".lower()
        event_type = None
        for candidate, keywords in event_rules:
            if any(keyword in text for keyword in keywords):
                event_type = candidate
                break
        if event_type is None or event_type in seen_types:
            continue

        seen_types.add(event_type)
        sentiment = float(getattr(item, "score", 0.0))
        if sentiment == 0.0:
            impact_hint = str(getattr(item, "impact", "neutral")).lower()
            if impact_hint == "up":
                sentiment = 0.2
            elif impact_hint == "down":
                sentiment = -0.2

        magnitude = abs(sentiment)
        if magnitude >= 0.35:
            impact = "high"
        elif magnitude >= 0.15:
            impact = "medium"
        else:
            impact = "low"
        confidence = min(0.9, 0.55 + magnitude)

        event_factor = factor_engine.EventFactor(
            event_type=event_type,
            sentiment=sentiment,
            impact=impact,
            confidence=confidence,
        )
        remember_event_factor(
            conn,
            ticker,
            event_factor,
            published=int(getattr(item, "published", int(time.time()))),
            source_title=title,
            source_url=str(getattr(item, "url", "")),
        )
        output.append(event_factor)

    return output
