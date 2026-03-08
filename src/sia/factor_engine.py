from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


@dataclass(frozen=True)
class CompositeAnalysis:
    signal: str
    confidence: float
    price: float
    sma_fast: float | None
    sma_slow: float | None
    rsi: float | None
    chart_score: float
    macro_score: float
    event_score: float
    news_score: float
    composite_score: float
    risk_level: str
    momentum: str
    macro_environment: str
    reason: str


@dataclass(frozen=True)
class MacroSnapshot:
    vix: float | None = None
    treasury_10y: float | None = None
    cpi_yoy: float | None = None
    dollar_index: float | None = None
    crude_oil: float | None = None


@dataclass(frozen=True)
class EventFactor:
    event_type: str
    sentiment: float
    impact: str = "medium"
    confidence: float = 0.5


@dataclass(frozen=True)
class FactorInputs:
    closes: list[float]
    latest_news: list[Any]
    macro_snapshot: MacroSnapshot | None = None
    event_factors: list[EventFactor] | None = None


def _env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= minimum else default


def _env_float(name: str, default: float, *, minimum: float = 0.0, maximum: float | None = None) -> float:
    raw = str(os.getenv(name, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if value < minimum:
        return default
    if maximum is not None and value > maximum:
        return default
    return value


CONFIRM_LONG_RISK_OFF = _env_int("SIA_CONFIRM_LONG_RISK_OFF", 3, minimum=1)
CONFIRM_LONG_MIXED = _env_int("SIA_CONFIRM_LONG_MIXED", 2, minimum=1)
CONFIRM_LONG_RISK_ON = _env_int("SIA_CONFIRM_LONG_RISK_ON", 1, minimum=1)
CONFIRM_SHORT_RISK_OFF = _env_int("SIA_CONFIRM_SHORT_RISK_OFF", 1, minimum=1)
CONFIRM_SHORT_MIXED = _env_int("SIA_CONFIRM_SHORT_MIXED", 2, minimum=1)
CONFIRM_SHORT_RISK_ON = _env_int("SIA_CONFIRM_SHORT_RISK_ON", 3, minimum=1)

REGIME_BUY_PENALTY_RISK_OFF = _env_float("SIA_REGIME_BUY_PENALTY_RISK_OFF", 0.18, minimum=0.0, maximum=0.5)
REGIME_SELL_PENALTY_RISK_ON = _env_float("SIA_REGIME_SELL_PENALTY_RISK_ON", 0.15, minimum=0.0, maximum=0.5)
REGIME_EXTRA_PENALTY_OPPOSED = _env_float("SIA_REGIME_EXTRA_PENALTY_OPPOSED", 0.08, minimum=0.0, maximum=0.3)
REGIME_BUY_BONUS_RISK_ON = _env_float("SIA_REGIME_BUY_BONUS_RISK_ON", 0.05, minimum=0.0, maximum=0.2)
REGIME_SELL_BONUS_RISK_OFF = _env_float("SIA_REGIME_SELL_BONUS_RISK_OFF", 0.06, minimum=0.0, maximum=0.2)
REGIME_MULTIPLIER_MIN = _env_float("SIA_REGIME_MULTIPLIER_MIN", 0.55, minimum=0.1, maximum=1.0)
REGIME_MULTIPLIER_MAX = _env_float("SIA_REGIME_MULTIPLIER_MAX", 1.15, minimum=1.0, maximum=2.0)


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None

    changes = [cur - prev for prev, cur in zip(values[:-1], values[1:])]
    gains = [max(v, 0.0) for v in changes[-period:]]
    losses = [abs(min(v, 0.0)) for v in changes[-period:]]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1 + rs))


def _clamp_score(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _factor_direction(value: float, *, threshold: float = 0.15) -> int:
    if value >= threshold:
        return 1
    if value <= -threshold:
        return -1
    return 0


def _count_confirmations(factors: dict[str, float], direction: int) -> int:
    return sum(1 for value in factors.values() if _factor_direction(value) == direction)


def _has_strong_factor(factors: dict[str, float], direction: int, *, threshold: float = 0.45) -> bool:
    if direction > 0:
        return any(value >= threshold for value in factors.values())
    return any(value <= -threshold for value in factors.values())


def _conflict_penalty(factors: dict[str, float]) -> float:
    directions = [_factor_direction(value) for value in factors.values()]
    bullish = sum(1 for direction in directions if direction > 0)
    bearish = sum(1 for direction in directions if direction < 0)
    directional_total = bullish + bearish
    if bullish == 0 or bearish == 0 or directional_total < 2:
        return 0.0
    ratio = min(bullish, bearish) / directional_total
    return min(0.35, 0.10 + (0.30 * ratio))


def _regime_multiplier(
    composite_score: float,
    *,
    macro_environment: str,
    bullish_confirmations: int,
    bearish_confirmations: int,
) -> float:
    multiplier = 1.0
    if macro_environment == "RISK_OFF":
        if composite_score > 0:
            multiplier -= REGIME_BUY_PENALTY_RISK_OFF
            if bearish_confirmations > bullish_confirmations:
                multiplier -= REGIME_EXTRA_PENALTY_OPPOSED
        elif composite_score < 0 and bearish_confirmations >= 2:
            multiplier += REGIME_SELL_BONUS_RISK_OFF
    elif macro_environment == "RISK_ON":
        if composite_score < 0:
            multiplier -= REGIME_SELL_PENALTY_RISK_ON
            if bullish_confirmations > bearish_confirmations:
                multiplier -= REGIME_EXTRA_PENALTY_OPPOSED
        elif composite_score > 0 and bullish_confirmations >= 2:
            multiplier += REGIME_BUY_BONUS_RISK_ON
    return max(REGIME_MULTIPLIER_MIN, min(REGIME_MULTIPLIER_MAX, multiplier))


def _required_confirmations(macro_environment: str) -> tuple[int, int]:
    if macro_environment == "RISK_OFF":
        return CONFIRM_LONG_RISK_OFF, CONFIRM_SHORT_RISK_OFF
    if macro_environment == "RISK_ON":
        return CONFIRM_LONG_RISK_ON, CONFIRM_SHORT_RISK_ON
    return CONFIRM_LONG_MIXED, CONFIRM_SHORT_MIXED


def _build_reason(
    price: float,
    sma_fast: float | None,
    sma_slow: float | None,
    rsi: float | None,
    latest_news: list[Any],
    macro_snapshot: MacroSnapshot | None,
    macro_environment: str,
    macro_score: float,
    strategy_notes: list[str] | None = None,
) -> str:
    def _fmt_points(value: float | None) -> str:
        return "n/a" if value is None else f"{value * 100.0:.1f}점"

    top_news = [
        f"{getattr(item, 'impact', 'neutral')}:{str(getattr(item, 'title', ''))[:40]} ({float(getattr(item, 'score', 0.0)) * 100.0:+.1f}점)"
        for item in latest_news[:2]
    ]
    if not top_news:
        top_news = ["no_news_signal"]

    def _fmt(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    macro_parts: list[str] = []
    if macro_snapshot is not None:
        if macro_snapshot.vix is not None:
            macro_parts.append(f"VIX {_fmt(macro_snapshot.vix)}")
        if macro_snapshot.treasury_10y is not None:
            macro_parts.append(f"10Y {_fmt(macro_snapshot.treasury_10y)}")
        if macro_snapshot.dollar_index is not None:
            macro_parts.append(f"DXY {_fmt(macro_snapshot.dollar_index)}")
        if macro_snapshot.crude_oil is not None:
            macro_parts.append(f"WTI {_fmt(macro_snapshot.crude_oil)}")
        if macro_snapshot.cpi_yoy is not None:
            macro_parts.append(f"CPI {_fmt(macro_snapshot.cpi_yoy)}")

    macro_text = f"{macro_environment} ({_fmt_points(macro_score)}"
    if macro_parts:
        macro_text = f"{macro_text}; {' / '.join(macro_parts)})"
    else:
        macro_text = f"{macro_text})"

    reason = (
        f"price={price:.2f}, SMA5={_fmt(sma_fast)}, SMA20={_fmt(sma_slow)}, RSI14={_fmt(rsi)}, "
        f"news={', '.join(top_news)}, macro={macro_text}"
    )
    if strategy_notes:
        reason = f"{reason}, strategy={'; '.join(note for note in strategy_notes if note)}"
    return reason


def _normalize_macro_snapshot(snapshot: MacroSnapshot | None) -> tuple[dict[str, float | None], int]:
    if snapshot is None:
        return {}, 0

    normalized = {
        "vix": snapshot.vix,
        "treasury_10y": snapshot.treasury_10y,
        "cpi_yoy": snapshot.cpi_yoy if snapshot.cpi_yoy is not None and 0.0 <= snapshot.cpi_yoy <= 20.0 else None,
        "dollar_index": snapshot.dollar_index,
        "crude_oil": snapshot.crude_oil,
    }
    usable_count = sum(1 for value in normalized.values() if value is not None)
    return normalized, usable_count


def _score_macro(snapshot: MacroSnapshot | None) -> tuple[float, str]:
    if snapshot is None:
        return 0.0, "UNMODELED"

    normalized, usable_count = _normalize_macro_snapshot(snapshot)
    if usable_count < 2:
        return 0.0, "PARTIAL"

    score = 0.0
    if normalized["vix"] is not None:
        if normalized["vix"] >= 25.0:
            score -= 0.35
        elif normalized["vix"] <= 16.0:
            score += 0.20
    if normalized["treasury_10y"] is not None:
        if normalized["treasury_10y"] >= 4.5:
            score -= 0.20
        elif normalized["treasury_10y"] <= 3.5:
            score += 0.10
    if normalized["cpi_yoy"] is not None:
        if normalized["cpi_yoy"] >= 3.5:
            score -= 0.15
        elif normalized["cpi_yoy"] <= 2.5:
            score += 0.10
    if normalized["dollar_index"] is not None:
        if normalized["dollar_index"] >= 105.0:
            score -= 0.10
        elif normalized["dollar_index"] <= 100.0:
            score += 0.05
    if normalized["crude_oil"] is not None:
        if normalized["crude_oil"] >= 90.0:
            score -= 0.10
        elif normalized["crude_oil"] <= 70.0:
            score += 0.05

    score = _clamp_score(score)
    if score <= -0.20:
        environment = "RISK_OFF"
    elif score >= 0.20:
        environment = "RISK_ON"
    else:
        environment = "MIXED"
    return score, environment


def _score_events(event_factors: list[EventFactor] | None) -> float:
    if not event_factors:
        return 0.0

    impact_weights = {
        "low": 0.15,
        "medium": 0.30,
        "high": 0.50,
    }
    weighted_scores: list[float] = []
    for item in event_factors:
        impact_weight = impact_weights.get(item.impact.lower(), 0.30)
        confidence = max(0.0, min(1.0, item.confidence))
        sentiment = _clamp_score(item.sentiment)
        weighted_scores.append(sentiment * impact_weight * confidence)

    if not weighted_scores:
        return 0.0
    return _clamp_score(sum(weighted_scores) / len(weighted_scores))


def analyze_signal(
    inputs: FactorInputs,
    *,
    trend_weight: float,
    rsi_weight: float,
    news_weight: float,
    signal_threshold: float,
    macro_weight: float = 0.0,
    event_weight: float = 0.0,
) -> CompositeAnalysis | None:
    closes = inputs.closes
    latest_news = inputs.latest_news
    if len(closes) < 2:
        return None

    sma_fast = _sma(closes, 5)
    sma_slow = _sma(closes, 20)
    rsi = _rsi(closes, 14)
    price = closes[-1]

    trend_score = 0.0
    if sma_fast is not None and sma_slow is not None:
        trend_score = 1.0 if sma_fast > sma_slow else -1.0
    elif sma_fast is not None and closes[-1] > sma_fast:
        trend_score = 0.3
    elif sma_fast is not None:
        trend_score = -0.3

    if rsi is None:
        rsi_score = 0.0
    elif rsi >= 70:
        rsi_score = -0.6
    elif rsi <= 30:
        rsi_score = 0.6
    else:
        rsi_score = (50.0 - abs(rsi - 50.0)) / 50.0 - 1.0

    news_scores = [float(getattr(item, "score", 0.0)) for item in latest_news]
    news_score_raw = _clamp_score(sum(news_scores) / len(news_scores)) if news_scores else 0.0
    macro_score_raw, macro_environment = _score_macro(inputs.macro_snapshot)
    event_score_raw = _score_events(inputs.event_factors)

    active_macro_weight = macro_weight if macro_environment not in {"UNMODELED", "PARTIAL"} else 0.0
    active_event_weight = event_weight if inputs.event_factors else 0.0
    total_weight = trend_weight + rsi_weight + news_weight + active_macro_weight + active_event_weight
    if total_weight <= 0.0:
        total_weight = 1.0

    weighted_trend_score = trend_score * (trend_weight / total_weight)
    weighted_rsi_score = rsi_score * (rsi_weight / total_weight)
    chart_score = _clamp_score(weighted_trend_score + weighted_rsi_score)
    macro_score = _clamp_score(macro_score_raw * (active_macro_weight / total_weight))
    event_score = _clamp_score(event_score_raw * (active_event_weight / total_weight))
    weighted_news_score = _clamp_score(news_score_raw * (news_weight / total_weight))
    composite_score = _clamp_score(chart_score + macro_score + event_score + weighted_news_score)

    factor_stack: dict[str, float] = {
        "trend": trend_score,
        "rsi": rsi_score,
        "news": news_score_raw,
    }
    if active_macro_weight > 0.0:
        factor_stack["macro"] = macro_score_raw
    if active_event_weight > 0.0:
        factor_stack["event"] = event_score_raw

    bullish_confirmations = _count_confirmations(factor_stack, 1)
    bearish_confirmations = _count_confirmations(factor_stack, -1)
    long_required, short_required = _required_confirmations(macro_environment)
    conflict_penalty = _conflict_penalty(factor_stack)
    regime_multiplier = _regime_multiplier(
        composite_score,
        macro_environment=macro_environment,
        bullish_confirmations=bullish_confirmations,
        bearish_confirmations=bearish_confirmations,
    )
    composite_score = _clamp_score(composite_score * regime_multiplier)
    if conflict_penalty > 0.0:
        composite_score = _clamp_score(composite_score * (1.0 - conflict_penalty))

    confidence = min(1.0, max(0.0, abs(composite_score)))
    strong_bullish = _has_strong_factor(factor_stack, 1)
    strong_bearish = _has_strong_factor(factor_stack, -1)
    signal = "HOLD"
    signal_gate = ""
    if composite_score >= signal_threshold:
        long_gate = bullish_confirmations >= long_required or (
            strong_bullish and bullish_confirmations >= max(1, long_required - 1)
        )
        if long_gate:
            signal = "BUY"
        else:
            signal_gate = f"buy_blocked({bullish_confirmations}/{long_required})"
    elif composite_score <= -signal_threshold:
        short_gate = bearish_confirmations >= short_required or (
            strong_bearish and bearish_confirmations >= max(1, short_required - 1)
        )
        if short_gate:
            signal = "SELL"
        else:
            signal_gate = f"sell_blocked({bearish_confirmations}/{short_required})"

    if (
        abs(news_score_raw) >= 0.5
        or (rsi is not None and (rsi >= 70 or rsi <= 30))
        or conflict_penalty >= 0.18
    ):
        risk_level = "HIGH"
    elif confidence >= 0.45 or signal_gate:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    if trend_score > 0:
        momentum = "UP"
    elif trend_score < 0:
        momentum = "DOWN"
    else:
        momentum = "FLAT"

    strategy_notes = [
        f"confirm=+{bullish_confirmations}/-{bearish_confirmations}",
        f"gate=+{long_required}/-{short_required}",
        f"conflict={conflict_penalty:.2f}",
        f"regime={regime_multiplier:.2f}x",
    ]
    if signal_gate:
        strategy_notes.append(signal_gate)

    return CompositeAnalysis(
        signal=signal,
        confidence=confidence,
        price=price,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        rsi=rsi,
        chart_score=chart_score,
        macro_score=macro_score,
        event_score=event_score,
        news_score=weighted_news_score,
        composite_score=composite_score,
        risk_level=risk_level,
        momentum=momentum,
        macro_environment=macro_environment,
        reason=_build_reason(
            price,
            sma_fast,
            sma_slow,
            rsi,
            latest_news,
            inputs.macro_snapshot,
            macro_environment,
            macro_score,
            strategy_notes,
        ),
    )
