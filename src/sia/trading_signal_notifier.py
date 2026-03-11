from __future__ import annotations

import logging
import sqlite3
import time

try:
    from . import factor_engine, notifier_pipeline
    from .market_runtime import market_label
    from .notifier_config import Settings, load_settings
    from .notifier_collector import (
        collect_news_items,
        fetch_finnhub_closes,
        fetch_marketaux_news,
        fetch_yahoo_closes,
        fetch_yahoo_rss_news,
        mock_news,
        mock_prices,
    )
    from .notifier_models import NewsItem, PricePoint
    from .notifier_scoring import build_signal
    from .notifier_sender import send_signal_notification
except ImportError:
    import factor_engine  # type: ignore
    import notifier_pipeline  # type: ignore
    from market_runtime import market_label  # type: ignore
    from notifier_config import Settings, load_settings  # type: ignore
    from notifier_collector import (  # type: ignore
        collect_news_items,
        fetch_finnhub_closes,
        fetch_marketaux_news,
        fetch_yahoo_closes,
        fetch_yahoo_rss_news,
        mock_news,
        mock_prices,
    )
    from notifier_models import NewsItem, PricePoint  # type: ignore
    from notifier_scoring import build_signal  # type: ignore
    from notifier_sender import send_signal_notification  # type: ignore


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logger = logging.getLogger("trading_signal_notifier")
def run_once(settings: Settings) -> None:
    notifier_pipeline.init_db(settings.db_path)
    ticker_market_map = dict(settings.ticker_markets)
    open_markets = set(settings.open_markets)

    with sqlite3.connect(settings.db_path) as conn:
        macro_snapshot_payload = notifier_pipeline.collect_macro_snapshot(
            conn,
            dry_run=settings.dry_run,
            fetch_yahoo_closes_fn=fetch_yahoo_closes,
        )
        macro_snapshot = factor_engine.MacroSnapshot(**macro_snapshot_payload)

        for ticker in settings.tickers:
            try:
                market_code = ticker_market_map.get(ticker, "US")
                latest_news = notifier_pipeline.collect_ticker_news(
                    conn,
                    ticker,
                    dry_run=settings.dry_run,
                    max_news_per_ticker=settings.max_news_per_ticker,
                    news_lookback_hours=settings.news_lookback_hours,
                    marketaux_api_key=settings.marketaux_api_key,
                    ollama_host=settings.ollama_host,
                    ollama_model=settings.ollama_model,
                    mock_news_fn=mock_news,
                    fetch_marketaux_news_fn=fetch_marketaux_news,
                    fetch_yahoo_rss_news_fn=fetch_yahoo_rss_news,
                    collect_news_items_fn=collect_news_items,
                )
                event_factors = notifier_pipeline.derive_and_store_event_factors(
                    conn,
                    ticker,
                    latest_news,
                )

                if market_code not in open_markets:
                    logger.info(
                        "시장 휴장으로 가격/신호 스킵: ticker=%s market=%s(%s)",
                        ticker,
                        market_code,
                        market_label(market_code),
                    )
                    continue

                close_source, closes_points = notifier_pipeline.collect_price_points(
                    conn,
                    ticker,
                    dry_run=settings.dry_run,
                    finnhub_api_key=settings.finnhub_api_key,
                    finnhub_fail_threshold=settings.finnhub_fail_threshold,
                    finnhub_fail_window_minutes=settings.finnhub_fail_window_minutes,
                    mock_prices_fn=mock_prices,
                    fetch_finnhub_closes_fn=fetch_finnhub_closes,
                    fetch_yahoo_closes_fn=fetch_yahoo_closes,
                )

                notifier_pipeline.remember_prices(
                    conn,
                    ticker,
                    closes_points,
                    source=close_source,
                )
                if not closes_points:
                    logger.warning("가격 데이터 없음: %s", ticker)
                    continue

                closes = [p.close for p in closes_points]
                logger.info("가격 데이터 수집 완료: %s (%d개)", ticker, len(closes_points))

                signal = build_signal(
                    ticker,
                    closes,
                    latest_news,
                    macro_snapshot=macro_snapshot,
                    event_factors=event_factors,
                    trend_weight=settings.trend_weight,
                    rsi_weight=settings.rsi_weight,
                    news_weight=settings.news_weight,
                    signal_threshold=settings.signal_threshold,
                )
                if signal is None:
                    continue

                notifier_pipeline.remember_dashboard_snapshot(
                    conn,
                    signal,
                    latest_news=latest_news,
                    event_factors=event_factors,
                )

                if signal.signal == "HOLD":
                    conn.execute(
                        "INSERT INTO alerts (ts, ticker, signal, confidence, reason, sent, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (int(time.time()), ticker, signal.signal, signal.confidence, signal.reason, 0, None),
                    )
                    logger.info("신호 보류: %s", signal.reason)
                    continue

                cooldown_ts = notifier_pipeline.is_cooldown_active(
                    conn,
                    ticker,
                    signal.signal,
                    settings.cooldown_minutes,
                )
                if cooldown_ts is not None:
                    remaining = notifier_pipeline.remaining_cooldown_seconds(
                        cooldown_ts,
                        settings.cooldown_minutes,
                    )
                    logger.info(
                        "쿨다운 스킵: ticker=%s signal=%s last_signal_ts=%s remaining=%ss",
                        ticker,
                        signal.signal,
                        cooldown_ts,
                        remaining,
                    )
                    continue

                sent = send_signal_notification(
                    settings.telegram_bot_token,
                    settings.telegram_chat_id,
                    settings.telegram_parse_mode,
                    signal,
                    latest_news,
                )
                conn.execute(
                    "INSERT INTO alerts (ts, ticker, signal, confidence, reason, sent, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        int(time.time()),
                        signal.ticker,
                        signal.signal,
                        signal.confidence,
                        signal.reason,
                        1 if sent else 0,
                        None,
                    ),
                )
                if sent:
                    logger.info("알림 발송 완료: %s", ticker)
                else:
                    logger.info("알림 미발송: %s", ticker)

            except Exception as exc:
                logger.exception("티커 처리 중 오류: %s", ticker)
                conn.execute(
                    "INSERT INTO alerts (ts, ticker, signal, confidence, reason, sent, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (int(time.time()), ticker, "ERROR", 0.0, "", 0, str(exc)),
                )

        conn.commit()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        settings = load_settings()
        if settings.run_once:
            run_once(settings)
            return 0

        while True:
            run_once(settings)
            time.sleep(max(1, settings.poll_interval_minutes) * 60)
    except KeyboardInterrupt:
        logger.info("중지됨")
        return 0
    except Exception as exc:
        logger.exception("치명적 오류: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
