from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PricePoint:
    ts: int
    close: float


@dataclass(frozen=True)
class NewsItem:
    title: str
    published: int
    url: str
    summary: str
    impact: str
    score: float
    keywords: list[str]


@dataclass(frozen=True)
class Signal:
    ticker: str
    signal: str
    confidence: float
    reason: str
    price: float
    sma_fast: float | None
    sma_slow: float | None
    rsi: float | None
    chart_score: float = 0.0
    macro_score: float = 0.0
    event_score: float = 0.0
    news_score: float = 0.0
    composite_score: float = 0.0
    risk_level: str = "LOW"
    momentum: str = "FLAT"
    macro_environment: str = "UNMODELED"
