from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import logging
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logger = logging.getLogger("trading_signal_notifier")


@dataclass(frozen=True)
class Settings:
    db_path: str
    tickers: tuple[str, ...]
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    finnhub_api_key: str | None
    marketaux_api_key: str | None
    ollama_host: str
    ollama_model: str
    poll_interval_minutes: int
    cooldown_minutes: int
    max_news_per_ticker: int
    run_once: bool


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


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or str(value).strip() == "":
        return default
    return value.strip()


def _json_request(url: str, *, payload: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    if payload is not None:
        data = urllib.parse.urlencode(payload).encode("utf-8")
    else:
        data = None
    req = urllib.request.Request(url, data=data, method="GET" if data is None else "POST")

    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def _http_get_json(url: str, params: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    if params:
        delimiter = "&" if "?" in url else "?"
        url = f"{url}{delimiter}{urllib.parse.urlencode(params)}"
    return _json_request(url, payload=None, timeout=timeout)


def _http_post_json(url: str, payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def load_settings(argv: list[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser(prog="trading_signal_notifier")
    parser.add_argument("--tickers", default=_env("TICKERS", ""))
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
    parser.add_argument("--once", action="store_true")

    args = parser.parse_args(argv)
    if not args.tickers:
        raise ValueError("TICKERS env or --tickers is required")

    normalized = tuple(
        [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    )
    return Settings(
        db_path=args.db_path,
        tickers=normalized,
        telegram_bot_token=args.telegram_bot_token,
        telegram_chat_id=args.telegram_chat_id,
        finnhub_api_key=args.finnhub_api_key,
        marketaux_api_key=args.marketaux_api_key,
        ollama_host=args.ollama_host.rstrip("/"),
        ollama_model=args.ollama_model,
        poll_interval_minutes=args.poll_interval_minutes,
        cooldown_minutes=args.cooldown_minutes,
        max_news_per_ticker=args.max_news_per_ticker,
        run_once=args.once,
    )


def init_db(db_path: str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_ticks (
                ticker TEXT NOT NULL,
                ts INTEGER NOT NULL,
                source TEXT NOT NULL,
                close REAL NOT NULL,
                PRIMARY KEY (ticker, ts, source)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                news_id TEXT PRIMARY KEY,
                ticker TEXT NOT NULL,
                published INTEGER NOT NULL,
                source_url TEXT,
                title TEXT NOT NULL,
                summary TEXT,
                impact TEXT,
                score REAL,
                keywords TEXT,
                raw_json TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                signal TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL,
                sent INTEGER NOT NULL,
                error_message TEXT
            )
            """
        )


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


def build_signal(ticker: str, closes: list[float], latest_news: list[NewsItem]) -> Signal | None:
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

    news_scores = [n.score for n in latest_news]
    news_score = sum(news_scores) / len(news_scores) if news_scores else 0.0
    news_score = max(-1.0, min(1.0, news_score))

    score = trend_score * 0.55 + rsi_score * 0.25 + news_score * 0.2
    confidence = min(1.0, max(0.0, abs(score)))

    if score >= 0.35:
        label = "BUY"
    elif score <= -0.35:
        label = "SELL"
    else:
        label = "HOLD"

    top_news = [
        f"{n.impact}:{n.title} ({n.score:+.2f})" for n in latest_news[:2]
    ]
    if not top_news:
        top_news = ["no_news_signal"]

    reason = (
        f"price={price:.2f}, SMA5={sma_fast}, SMA20={sma_slow}, RSI14={rsi}, "
        f"news={', '.join(top_news)}"
    )

    return Signal(
        ticker=ticker,
        signal=label,
        confidence=confidence,
        reason=reason,
        price=price,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        rsi=rsi,
    )


def _make_news_id(ticker: str, item: dict[str, Any]) -> str:
    raw = f"{ticker}:{item.get('url', '')}:{item.get('published_at', '')}:{item.get('title', '')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _fetch_finnhub_closes(ticker: str, api_key: str, *, count: int = 40) -> list[PricePoint]:
    to_ts = int(time.time())
    from_ts = int((datetime.now(timezone.utc) - timedelta(days=180)).timestamp())
    url = "https://finnhub.io/api/v1/stock/candle"
    payload = {
        "symbol": ticker,
        "resolution": "D",
        "from": str(from_ts),
        "to": str(to_ts),
        "token": api_key,
    }

    data = _http_get_json(url, payload)
    if data.get("s") != "ok":
        raise RuntimeError(f"Finnhub candle failed: {data}")

    closes = data.get("c", [])
    timestamps = data.get("t", [])
    if not closes:
        return []

    points: list[PricePoint] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        points.append(PricePoint(int(ts), float(close)))

    return points[-count:]


def _fetch_marketaux_news(ticker: str, api_key: str, limit: int = 5) -> list[dict[str, Any]]:
    url = "https://api.marketaux.com/v1/news/all"
    payload = {
        "symbols": ticker,
        "limit": str(limit),
        "language": "en",
        "api_token": api_key,
    }
    data = _http_get_json(url, payload)
    articles = data.get("data", []) or []
    return articles[:limit]


def _llm_infer_news_summary(
    ollama_host: str,
    model: str,
    ticker: str,
    title: str,
    url: str,
    body: str,
) -> NewsItem:
    prompt = (
        "다음 뉴스를 한국어로 간결히 정리해서 JSON 한 개만 반환하세요."
        "형식은 {\\"summary\\":.., \\"impact\\": \\\"up/down/neutral\\\", "
        "\\"score\\": -1.0~1.0, \\"keywords\\":[...]} 이어야 합니다.\n"
        f"티커: {ticker}\n"
        f"제목: {title}\n"
        f"링크: {url}\n"
        f"본문: {body[:1200]}\n"
    )
    response = _http_post_json(
        f"{ollama_host}/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        },
    )

    raw = response.get("response", "")
    parsed = _safe_json_from_text(raw)
    if not parsed:
        return NewsItem(
            title=title,
            published=int(time.time()),
            url=url,
            summary=raw[:300],
            impact="neutral",
            score=0.0,
            keywords=[],
        )

    score = float(parsed.get("score", 0.0) or 0.0)
    score = max(-1.0, min(1.0, score))
    impact = str(parsed.get("impact", "neutral")).lower()
    if impact not in {"up", "down", "neutral"}:
        impact = "neutral"

    return NewsItem(
        title=title,
        published=int(time.time()),
        url=url,
        summary=str(parsed.get("summary", ""))[:300],
        impact=impact,
        score=score if impact == "up" else (-score if impact == "down" else score * 0.25),
        keywords=_extract_keywords(parsed.get("keywords", "")),
    )


def _safe_json_from_text(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    chunk = text[start : end + 1]
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        return None


def _extract_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value][:5]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()][:5]
    return []


def _is_cooldown_active(conn: sqlite3.Connection, ticker: str, cooldown_minutes: int) -> bool:
    window = int((datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).timestamp())
    row = conn.execute(
        """
        SELECT signal, sent, ts FROM alerts
        WHERE ticker = ? AND ts >= ?
        ORDER BY ts DESC LIMIT 1
        """,
        (ticker, window),
    ).fetchone()

    return row is not None


def _remember_prices(conn: sqlite3.Connection, ticker: str, points: list[PricePoint]) -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO price_ticks (ticker, ts, source, close) VALUES (?, ?, ?, ?)",
        [(ticker, p.ts, "finnhub", p.close) for p in points],
    )


def _remember_news(conn: sqlite3.Connection, ticker: str, item: NewsItem, *, source_url: str) -> bool:
    news_id = _make_news_id(ticker, {
        "url": source_url,
        "published_at": item.published,
        "title": item.title,
    })
    with contextlib.suppress(sqlite3.IntegrityError):
        conn.execute(
            """
            INSERT INTO news_items (news_id, ticker, published, source_url, title, summary, impact, score, keywords, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news_id,
                ticker,
                item.published,
                source_url,
                item.title,
                item.summary,
                item.impact,
                item.score,
                ",".join(item.keywords),
                json.dumps(item.__dict__, ensure_ascii=False),
            ),
        )
        return True
    return False


def _send_telegram(
    bot_token: str | None,
    chat_id: str | None,
    text: str,
) -> bool:
    if not bot_token or not chat_id:
        logger.info("skip telegram (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID): %s", text)
        return False

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    response = _http_post_json(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        payload,
    )
    return bool(response.get("ok", False))


def run_once(settings: Settings) -> None:
    init_db(settings.db_path)

    with sqlite3.connect(settings.db_path) as conn:
        for ticker in settings.tickers:
            try:
                if not settings.finnhub_api_key:
                    raise RuntimeError("FINNHUB_API_KEY is required for price fetch")

                closes_points = _fetch_finnhub_closes(ticker, settings.finnhub_api_key)
                if not closes_points:
                    logger.warning("no price data for %s", ticker)
                    continue
                _remember_prices(conn, ticker, closes_points)

                closes = [p.close for p in closes_points]
                logger.info("fetched price points for %s: %d", ticker, len(closes_points))

                latest_news: list[NewsItem] = []
                if settings.marketaux_api_key:
                    raw_news = _fetch_marketaux_news(
                        ticker,
                        settings.marketaux_api_key,
                        limit=settings.max_news_per_ticker,
                    )
                    for n in raw_news:
                        title = (n.get("title") or "").strip()
                        url = n.get("url") or ""
                        if not title:
                            continue
                        body = (n.get("description") or n.get("snippet") or "")[:1200]
                        item = _llm_infer_news_summary(
                            settings.ollama_host,
                            settings.ollama_model,
                            ticker,
                            title,
                            url,
                            body,
                        )
                        inserted = _remember_news(
                            conn,
                            ticker,
                            item,
                            source_url=url,
                        )
                        if inserted:
                            latest_news.append(item)

                signal = build_signal(ticker, closes, latest_news)
                if signal is None:
                    continue

                if signal.signal == "HOLD":
                    conn.execute(
                        "INSERT INTO alerts (ts, ticker, signal, confidence, reason, sent, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (int(time.time()), ticker, signal.signal, signal.confidence, signal.reason, 0, None),
                    )
                    logger.info("signal hold: %s", signal.reason)
                    continue

                if _is_cooldown_active(conn, ticker, settings.cooldown_minutes):
                    logger.info("skip due to cooldown: %s", ticker)
                    continue

                message = (
                    f"[ {signal.ticker} ] {signal.signal} ({signal.confidence:.2f})\n"
                    f"시간: {datetime.now(timezone.utc).isoformat()}\n"
                    f"근거: {signal.reason}\n"
                )
                sent = _send_telegram(
                    settings.telegram_bot_token,
                    settings.telegram_chat_id,
                    message,
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
                logger.info("signal sent=%s ticker=%s", sent, ticker)

            except Exception as exc:
                logger.exception("run_once failed for %s", ticker)
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
        logger.info("stopped")
        return 0
    except Exception as exc:
        logger.exception("fatal: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
