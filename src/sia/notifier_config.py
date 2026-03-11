from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass

try:
    from .default_universe import merge_market_tickers, use_default_universe
    from .market_runtime import (
        MARKET_ORDER,
        MARKET_TICKER_ENV,
        load_enabled_markets,
        market_session_window,
        open_markets,
        selection_file_path,
    )
except ImportError:
    from default_universe import merge_market_tickers, use_default_universe  # type: ignore
    from market_runtime import (  # type: ignore
        MARKET_ORDER,
        MARKET_TICKER_ENV,
        load_enabled_markets,
        market_session_window,
        open_markets,
        selection_file_path,
    )


@dataclass(frozen=True)
class Settings:
    db_path: str
    tickers: tuple[str, ...]
    default_universe_enabled: bool
    enabled_markets: tuple[str, ...]
    open_markets: tuple[str, ...]
    ticker_markets: tuple[tuple[str, str], ...]
    market_selection_file: str
    market_sessions: tuple[tuple[str, str], ...]
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    finnhub_api_key: str | None
    marketaux_api_key: str | None
    ollama_host: str
    ollama_model: str
    poll_interval_minutes: int
    cooldown_minutes: int
    max_news_per_ticker: int
    news_lookback_hours: int
    telegram_parse_mode: str
    trend_weight: float
    rsi_weight: float
    news_weight: float
    signal_threshold: float
    dry_run: bool
    run_once: bool
    finnhub_fail_threshold: int
    finnhub_fail_window_minutes: int


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    return value.strip()


def _is_placeholder_secret(value: str | None) -> bool:
    if value is None:
        return True
    normalized = str(value).strip().lower()
    if normalized == "":
        return True
    if normalized in {"dummy", "placeholder"}:
        return True
    if normalized.startswith("__your_"):
        return True
    return False


def _parse_int(value: str, name: str, min_value: int = 1, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 정수 파싱 실패: {value}") from exc
    if parsed < min_value:
        raise ValueError(f"{name}은(는) {min_value} 이상이어야 합니다.")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{name}은(는) {max_value} 이하여야 합니다.")
    return parsed


def _parse_float(value: str, name: str, min_value: float = 0.0, max_value: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} 실수 파싱 실패: {value}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{name}은(는) 유한한 숫자여야 합니다.")
    if parsed < min_value:
        raise ValueError(f"{name}은(는) {min_value} 이상이어야 합니다.")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{name}은(는) {max_value} 이하여야 합니다.")
    return parsed


def _parse_bool(value: str | None, default: bool) -> bool:
    normalized = str(value or "").strip().lower()
    if normalized == "":
        return default
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _dedupe_preserve_order(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v for v in values if v))


def load_settings(argv: list[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser(prog="trading_signal_notifier")
    parser.add_argument("--tickers", default=_env("TICKERS", ""))
    parser.add_argument("--include-default-universe", default=_env("SIA_INCLUDE_DEFAULT_UNIVERSE", "1"))
    parser.add_argument("--enabled-markets", default=_env("SIA_ENABLED_MARKETS", ""))
    parser.add_argument("--market-selection-file", default=_env("SIA_MARKET_SELECTION_FILE", selection_file_path()))
    parser.add_argument("--db-path", default=_env("SIGNAL_DB_PATH", "data/trading_signal_notifier.sqlite"))
    parser.add_argument("--telegram-bot-token", default=_env("TELEGRAM_BOT_TOKEN"))
    parser.add_argument("--telegram-chat-id", default=_env("TELEGRAM_CHAT_ID"))
    parser.add_argument("--finnhub-api-key", default=_env("FINNHUB_API_KEY"))
    parser.add_argument("--marketaux-api-key", default=_env("MARKETAUX_API_KEY"))
    parser.add_argument("--ollama-host", default=_env("OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--ollama-model", default=_env("OLLAMA_MODEL", "mistral:7b-instruct"))
    parser.add_argument("--poll-interval-minutes", type=int, default=int(_env("POLL_INTERVAL_MINUTES", "15")))
    parser.add_argument("--cooldown-minutes", type=int, default=int(_env("SIGNAL_COOLDOWN_MINUTES", "30")))
    parser.add_argument("--max-news-per-ticker", type=int, default=int(_env("MAX_NEWS_PER_TICKER", "3")))
    parser.add_argument("--news-lookback-hours", type=int, default=int(_env("NEWS_LOOKBACK_HOURS", "24")))
    parser.add_argument("--telegram-parse-mode", default=_env("TELEGRAM_PARSE_MODE", "HTML"))
    parser.add_argument("--trend-weight", type=float, default=float(_env("SIGNAL_TREND_WEIGHT", "0.55")))
    parser.add_argument("--rsi-weight", type=float, default=float(_env("SIGNAL_RSI_WEIGHT", "0.25")))
    parser.add_argument("--news-weight", type=float, default=float(_env("SIGNAL_NEWS_WEIGHT", "0.20")))
    parser.add_argument("--signal-threshold", type=float, default=float(_env("SIGNAL_THRESHOLD", "0.35")))
    parser.add_argument("--finnhub-fail-threshold", type=int, default=int(_env("FINNHUB_FAIL_THRESHOLD", "3")))
    parser.add_argument(
        "--finnhub-fail-window-minutes",
        type=int,
        default=int(_env("FINNHUB_FAIL_WINDOW_MINUTES", "120")),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")

    args = parser.parse_args(argv)
    if args.enabled_markets:
        requested_markets = _dedupe_preserve_order(
            [market.strip().upper() for market in str(args.enabled_markets).split(",") if market.strip()]
        )
        enabled_markets = tuple(code for code in requested_markets if code in MARKET_ORDER)
        if not enabled_markets:
            raise ValueError("enabled-markets에 유효한 시장이 없습니다.")
    else:
        enabled_markets = load_enabled_markets(str(args.market_selection_file))

    include_default_universe = _parse_bool(args.include_default_universe, use_default_universe())
    market_ticker_pairs: list[tuple[str, str]] = []
    for market in MARKET_ORDER:
        env_name = MARKET_TICKER_ENV[market]
        raw_value = _env(env_name)
        if market == "US" and raw_value is None:
            raw_value = args.tickers
        raw_tickers = [ticker.strip().upper() for ticker in str(raw_value or "").split(",") if ticker.strip()]
        if len(raw_tickers) > 40:
            raise ValueError(f"{env_name}는 추가 티커 기준 최대 40개까지 지원합니다.")
        market_tickers = merge_market_tickers(
            market,
            raw_tickers,
            include_default_universe=include_default_universe,
        )
        if market not in enabled_markets:
            continue
        market_ticker_pairs.extend((ticker, market) for ticker in market_tickers)

    if not market_ticker_pairs:
        raise ValueError(
            "활성 시장에 유효한 티커가 없습니다. 기본 universe 사용 여부와 "
            "TICKERS_US/TICKERS_KR/TICKERS_EU/TICKERS_JP 추가 티커를 확인하세요."
        )

    normalized = tuple(ticker for ticker, _ in market_ticker_pairs)
    if len(normalized) > 140:
        raise ValueError("한 번 실행에 설정할 수 있는 활성 티커는 최대 140개입니다.")

    poll_interval_minutes = _parse_int(str(args.poll_interval_minutes), "poll-interval-minutes", 1, 24 * 60)
    cooldown_minutes = _parse_int(str(args.cooldown_minutes), "cooldown-minutes", 1, 24 * 60)
    max_news_per_ticker = _parse_int(str(args.max_news_per_ticker), "max-news-per-ticker", 0, 20)
    news_lookback_hours = _parse_int(str(args.news_lookback_hours), "news-lookback-hours", 1, 24 * 14)
    finnhub_fail_threshold = _parse_int(str(args.finnhub_fail_threshold), "finnhub-fail-threshold", 1, 20)
    finnhub_fail_window_minutes = _parse_int(
        str(args.finnhub_fail_window_minutes),
        "finnhub-fail-window-minutes",
        1,
        24 * 60 * 30,
    )
    trend_weight = _parse_float(str(args.trend_weight), "trend-weight", 0.0)
    rsi_weight = _parse_float(str(args.rsi_weight), "rsi-weight", 0.0)
    news_weight = _parse_float(str(args.news_weight), "news-weight", 0.0)
    signal_threshold_input = _parse_float(str(args.signal_threshold), "signal-threshold", 0.0, 100.0)
    signal_threshold = signal_threshold_input / 100.0 if signal_threshold_input > 1.0 else signal_threshold_input
    telegram_parse_mode = (args.telegram_parse_mode or "HTML").strip().upper()
    if telegram_parse_mode not in {"HTML", "MARKDOWN", "MARKDOWNV2", "NONE"}:
        raise ValueError("telegram-parse-mode는 HTML, MARKDOWN, MARKDOWNV2, NONE 중 하나여야 합니다.")

    total_weight = trend_weight + rsi_weight + news_weight
    if total_weight <= 0.0:
        raise ValueError("trend-weight, rsi-weight, news-weight의 합은 0보다 커야 합니다.")

    trend_weight = trend_weight / total_weight
    rsi_weight = rsi_weight / total_weight
    news_weight = news_weight / total_weight
    telegram_bot_token = None if _is_placeholder_secret(args.telegram_bot_token) else str(args.telegram_bot_token).strip()
    telegram_chat_id = None if _is_placeholder_secret(args.telegram_chat_id) else str(args.telegram_chat_id).strip()
    finnhub_api_key = None if _is_placeholder_secret(args.finnhub_api_key) else str(args.finnhub_api_key).strip()
    marketaux_api_key = None if _is_placeholder_secret(args.marketaux_api_key) else str(args.marketaux_api_key).strip()
    ollama_host = (args.ollama_host or "").strip().rstrip("/")
    if _is_placeholder_secret(ollama_host):
        ollama_host = ""
    ollama_model = (args.ollama_model or "").strip()
    if _is_placeholder_secret(ollama_model):
        ollama_model = ""

    current_open_markets = open_markets(enabled_markets)

    return Settings(
        db_path=os.path.expanduser(os.path.expandvars(args.db_path)),
        tickers=normalized,
        default_universe_enabled=include_default_universe,
        enabled_markets=enabled_markets,
        open_markets=current_open_markets,
        ticker_markets=tuple(market_ticker_pairs),
        market_selection_file=os.path.expanduser(os.path.expandvars(str(args.market_selection_file))),
        market_sessions=tuple((market, market_session_window(market)) for market in enabled_markets),
        telegram_bot_token=telegram_bot_token,
        telegram_chat_id=telegram_chat_id,
        finnhub_api_key=finnhub_api_key,
        marketaux_api_key=marketaux_api_key,
        ollama_host=ollama_host,
        ollama_model=ollama_model,
        poll_interval_minutes=poll_interval_minutes,
        cooldown_minutes=cooldown_minutes,
        max_news_per_ticker=max_news_per_ticker,
        news_lookback_hours=news_lookback_hours,
        telegram_parse_mode=telegram_parse_mode,
        trend_weight=trend_weight,
        rsi_weight=rsi_weight,
        news_weight=news_weight,
        signal_threshold=min(1.0, max(0.0, signal_threshold)),
        dry_run=args.dry_run,
        run_once=args.once,
        finnhub_fail_threshold=finnhub_fail_threshold,
        finnhub_fail_window_minutes=finnhub_fail_window_minutes,
    )
