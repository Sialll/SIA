from __future__ import annotations

try:
    from . import factor_engine
    from .notifier_models import NewsItem, Signal
except ImportError:
    import factor_engine  # type: ignore
    from notifier_models import NewsItem, Signal  # type: ignore


def build_signal(
    ticker: str,
    closes: list[float],
    latest_news: list[NewsItem],
    *,
    macro_snapshot: factor_engine.MacroSnapshot | None = None,
    event_factors: list[factor_engine.EventFactor] | None = None,
    trend_weight: float,
    rsi_weight: float,
    news_weight: float,
    signal_threshold: float,
) -> Signal | None:
    active_event_weight = 0.08 if event_factors else 0.0
    factor_inputs = factor_engine.FactorInputs(
        closes=closes,
        latest_news=latest_news,
        macro_snapshot=macro_snapshot,
        event_factors=event_factors or [],
    )
    analysis = factor_engine.analyze_signal(
        factor_inputs,
        trend_weight=trend_weight,
        rsi_weight=rsi_weight,
        news_weight=news_weight,
        signal_threshold=signal_threshold,
        macro_weight=0.12,
        event_weight=active_event_weight,
    )
    if analysis is None:
        return None

    reason = analysis.reason
    if event_factors:
        event_tags = ", ".join(
            f"{item.event_type}:{item.sentiment:+.2f}/{item.impact}"
            for item in event_factors[:2]
        )
        reason = f"{reason}, events={event_tags}"

    return Signal(
        ticker=ticker,
        signal=analysis.signal,
        confidence=analysis.confidence,
        reason=reason,
        price=analysis.price,
        sma_fast=analysis.sma_fast,
        sma_slow=analysis.sma_slow,
        rsi=analysis.rsi,
        chart_score=analysis.chart_score,
        macro_score=analysis.macro_score,
        event_score=analysis.event_score,
        news_score=analysis.news_score,
        composite_score=analysis.composite_score,
        risk_level=analysis.risk_level,
        momentum=analysis.momentum,
        macro_environment=analysis.macro_environment,
    )
