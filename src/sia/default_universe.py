from __future__ import annotations

import os


DEFAULT_MARKET_CAP_FLOOR_USD = 1_000_000_000

DEFAULT_UNIVERSE_BY_MARKET: dict[str, tuple[str, ...]] = {
    "US": (
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "GOOGL",
        "META",
        "AVGO",
        "TSLA",
        "JPM",
        "V",
        "MA",
        "COST",
        "NFLX",
        "AMD",
        "XOM",
        "CVX",
        "KO",
        "PEP",
    ),
    "KR": (
        "005930.KS",
        "000660.KS",
        "035420.KS",
        "005380.KS",
        "207940.KS",
        "068270.KS",
        "105560.KS",
        "055550.KS",
    ),
    "EU": (
        "ASML.AS",
        "SAP.DE",
        "SHEL.L",
        "NOVO-B.CO",
        "MC.PA",
        "OR.PA",
        "SAN.MC",
        "AZN.L",
    ),
    "JP": (
        "7203.T",
        "6758.T",
        "9984.T",
        "8306.T",
        "8035.T",
        "9432.T",
        "8058.T",
        "6861.T",
    ),
}


def use_default_universe(raw: str | None = None) -> bool:
    value = raw if raw is not None else os.getenv("SIA_INCLUDE_DEFAULT_UNIVERSE", "1")
    normalized = str(value or "").strip().lower()
    if normalized in {"", "1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return True


def default_market_tickers(market: str) -> tuple[str, ...]:
    return DEFAULT_UNIVERSE_BY_MARKET.get(str(market or "").strip().upper(), ())


def merge_market_tickers(
    market: str,
    extra_tickers: list[str] | tuple[str, ...],
    *,
    include_default_universe: bool = True,
) -> tuple[str, ...]:
    merged: list[str] = []
    if include_default_universe:
        merged.extend(default_market_tickers(market))
    merged.extend(str(item).strip().upper() for item in extra_tickers if str(item).strip())
    return tuple(dict.fromkeys(merged))
