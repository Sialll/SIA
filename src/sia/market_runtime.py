from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


MARKET_ORDER = ("US", "KR", "EU", "JP")
MARKET_LABELS = {
    "US": "미국",
    "KR": "한국",
    "EU": "유럽",
    "JP": "일본",
}
MARKET_TICKER_ENV = {
    "US": "TICKERS_US",
    "KR": "TICKERS_KR",
    "EU": "TICKERS_EU",
    "JP": "TICKERS_JP",
}
MARKET_SESSION_ENV = {
    "US": "SIA_MARKET_SESSION_US",
    "KR": "SIA_MARKET_SESSION_KR",
    "EU": "SIA_MARKET_SESSION_EU",
    "JP": "SIA_MARKET_SESSION_JP",
}
DEFAULT_SESSION_WINDOWS = {
    "US": "22:30-05:00",
    "KR": "09:00-15:30",
    "EU": "17:00-01:30",
    "JP": "09:00-15:00",
}
DEFAULT_MARKET_SELECTION_PATH = "~/.config/sia-notifier/market-selection.json"
DEFAULT_ENABLED_MARKETS = ("US",)
KST = ZoneInfo("Asia/Seoul")
EU_TICKER_SUFFIXES = (".AS", ".BR", ".DE", ".L", ".MC", ".MI", ".PA", ".SW")


def selection_file_path() -> str:
    return os.path.expanduser(
        os.path.expandvars(
            os.getenv("SIA_MARKET_SELECTION_FILE", DEFAULT_MARKET_SELECTION_PATH)
        )
    )


def market_label(code: str) -> str:
    return MARKET_LABELS.get(code, code)


def ticker_market_code(ticker: str) -> str:
    normalized = str(ticker or "").strip().upper()
    if normalized.endswith((".KS", ".KQ")):
        return "KR"
    if normalized.endswith(".T"):
        return "JP"
    if normalized.endswith(EU_TICKER_SUFFIXES):
        return "EU"
    return "US"


def market_selection_summary(codes: tuple[str, ...]) -> str:
    if not codes:
        return "없음"
    return ", ".join(market_label(code) for code in codes)


def market_session_window(code: str) -> str:
    env_name = MARKET_SESSION_ENV.get(code)
    if env_name:
        raw = os.getenv(env_name, "").strip()
        if raw:
            return raw
    return DEFAULT_SESSION_WINDOWS.get(code, "")


def _parse_hhmm(value: str) -> int:
    raw = value.strip()
    hour_text, minute_text = raw.split(":", 1)
    hour = int(hour_text)
    minute = int(minute_text)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError(f"잘못된 시각 형식: {value}")
    return hour * 60 + minute


def _dedupe_codes(values: list[str]) -> tuple[str, ...]:
    normalized = []
    seen = set()
    for value in values:
        code = str(value or "").strip().upper()
        if code not in MARKET_ORDER or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return tuple(normalized)


def load_enabled_markets(selection_path: str | None = None) -> tuple[str, ...]:
    path = Path(selection_path or selection_file_path())
    if not path.exists():
        return DEFAULT_ENABLED_MARKETS
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_ENABLED_MARKETS
    if not isinstance(payload, dict):
        return DEFAULT_ENABLED_MARKETS
    enabled = payload.get("enabled_markets")
    if not isinstance(enabled, list):
        return DEFAULT_ENABLED_MARKETS
    normalized = _dedupe_codes([str(item) for item in enabled])
    return normalized or DEFAULT_ENABLED_MARKETS


def is_market_open(code: str, now: datetime | None = None) -> bool:
    window = market_session_window(code)
    if "-" not in window:
        return False
    now_kst = now.astimezone(KST) if now is not None else datetime.now(KST)
    start_text, end_text = [part.strip() for part in window.split("-", 1)]
    start_minutes = _parse_hhmm(start_text)
    end_minutes = _parse_hhmm(end_text)
    current_minutes = now_kst.hour * 60 + now_kst.minute

    if start_minutes <= end_minutes:
        return now_kst.weekday() < 5 and start_minutes <= current_minutes <= end_minutes

    if current_minutes >= start_minutes:
        return now_kst.weekday() < 5
    if current_minutes <= end_minutes:
        previous_weekday = (now_kst.weekday() - 1) % 7
        return previous_weekday < 5
    return False


def open_markets(enabled_markets: tuple[str, ...], now: datetime | None = None) -> tuple[str, ...]:
    return tuple(code for code in enabled_markets if is_market_open(code, now=now))
