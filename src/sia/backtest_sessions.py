from __future__ import annotations

import datetime as dt

try:
    from .market_runtime import KST, ticker_market_code
except ImportError:
    from market_runtime import KST, ticker_market_code  # type: ignore


SESSION_LABELS = {
    "US_PREMARKET": "미국 프리장",
    "US_REGULAR": "미국 정규장",
    "US_AFTERHOURS": "미국 시간외",
    "KR_REGULAR": "한국 본장",
    "KR_OFFHOURS": "한국 장외",
    "EU_REGULAR": "유럽 본장",
    "EU_OFFHOURS": "유럽 장외",
    "JP_REGULAR": "일본 본장",
    "JP_OFFHOURS": "일본 장외",
}


def session_label_for_ticker_ts(ticker: str, ts: int) -> str:
    market = ticker_market_code(ticker)
    current = dt.datetime.fromtimestamp(ts, tz=KST)
    minute = current.hour * 60 + current.minute

    if market == "US":
        if 17 * 60 <= minute < 22 * 60 + 30 and current.weekday() < 5:
            return SESSION_LABELS["US_PREMARKET"]
        if minute >= 22 * 60 + 30 and current.weekday() < 5:
            return SESSION_LABELS["US_REGULAR"]
        if minute <= 5 * 60 and ((current.weekday() - 1) % 7) < 5:
            return SESSION_LABELS["US_REGULAR"]
        return SESSION_LABELS["US_AFTERHOURS"]

    if market == "KR":
        if current.weekday() < 5 and 9 * 60 <= minute <= 15 * 60 + 30:
            return SESSION_LABELS["KR_REGULAR"]
        return SESSION_LABELS["KR_OFFHOURS"]

    if market == "EU":
        if current.weekday() < 5 and minute >= 17 * 60:
            return SESSION_LABELS["EU_REGULAR"]
        if minute <= 90 and ((current.weekday() - 1) % 7) < 5:
            return SESSION_LABELS["EU_REGULAR"]
        return SESSION_LABELS["EU_OFFHOURS"]

    if current.weekday() < 5 and 9 * 60 <= minute <= 15 * 60:
        return SESSION_LABELS["JP_REGULAR"]
    return SESSION_LABELS["JP_OFFHOURS"]
