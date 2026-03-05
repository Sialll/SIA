from __future__ import annotations

import argparse
import html
import contextlib
import hashlib
import json
import math
import logging
import os
import random
import sqlite3
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


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
    news_lookback_hours: int
    telegram_parse_mode: str
    trend_weight: float
    rsi_weight: float
    news_weight: float
    signal_threshold: float
    dry_run: bool
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


def _parse_int(value: str, name: str, min_value: int = 1, max_value: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid integer for {name}: {value}") from exc
    if parsed < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return parsed


def _parse_float(value: str, name: str, min_value: float = 0.0, max_value: float | None = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid number for {name}: {value}") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{name} must be finite")
    if parsed < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and parsed > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return parsed


def _dedupe_preserve_order(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(v for v in values if v))


def _json_request(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    method: str = "GET",
    timeout: int = 20,
    max_retries: int = 2,
    backoff_seconds: float = 0.5,
) -> dict[str, Any]:
    method = method.upper()
    if method == "GET":
        headers = {}
        if payload is not None:
            delimiter = "&" if "?" in url else "?"
            url = f"{url}{delimiter}{urllib.parse.urlencode(payload)}"
        data = None
    elif method == "POST":
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload or {}).encode("utf-8")
    else:
        raise ValueError(f"unsupported HTTP method: {method}")

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )

    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="ignore")
            if not body.strip():
                return {}
            return json.loads(body)
        except (urllib.error.HTTPError, urllib.error.URLError, socket.timeout, TimeoutError, json.JSONDecodeError) as exc:
            if attempt >= max_retries:
                raise RuntimeError(f"{method} request failed: {url}") from exc
            logger.warning(
                "http request retry (%d/%d) for %s: %s",
                attempt + 1,
                max_retries,
                url,
                exc,
            )
            time.sleep(backoff_seconds * (2**attempt))
    return {}


def _http_get_json(url: str, params: dict[str, str] | None = None, timeout: int = 20) -> dict[str, Any]:
    if params:
        return _json_request(url, payload=params, method="GET", timeout=timeout)
    return _json_request(url, method="GET", timeout=timeout)


def _http_post_json(url: str, payload: dict[str, Any], timeout: int = 20) -> dict[str, Any]:
    return _json_request(url, payload=payload, method="POST", timeout=timeout)


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
    parser.add_argument("--news-lookback-hours", type=int, default=int(_env("NEWS_LOOKBACK_HOURS", "24")))
    parser.add_argument("--telegram-parse-mode", default=_env("TELEGRAM_PARSE_MODE", "HTML"))
    parser.add_argument("--trend-weight", type=float, default=float(_env("SIGNAL_TREND_WEIGHT", "0.55")))
    parser.add_argument("--rsi-weight", type=float, default=float(_env("SIGNAL_RSI_WEIGHT", "0.25")))
    parser.add_argument("--news-weight", type=float, default=float(_env("SIGNAL_NEWS_WEIGHT", "0.20")))
    parser.add_argument("--signal-threshold", type=float, default=float(_env("SIGNAL_THRESHOLD", "0.35")))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")

    args = parser.parse_args(argv)
    if not args.tickers:
        raise ValueError("TICKERS env or --tickers is required")

    raw_tickers = [ticker.strip().upper() for ticker in args.tickers.split(",") if ticker.strip()]
    if not raw_tickers:
        raise ValueError("TICKERS contains no valid symbol")
    normalized = _dedupe_preserve_order(raw_tickers)
    if len(normalized) > 30:
        raise ValueError("TICKERS has too many entries. maximum is 30 per run")

    poll_interval_minutes = _parse_int(str(args.poll_interval_minutes), "poll-interval-minutes", 1, 24 * 60)
    cooldown_minutes = _parse_int(str(args.cooldown_minutes), "cooldown-minutes", 1, 24 * 60)
    max_news_per_ticker = _parse_int(str(args.max_news_per_ticker), "max-news-per-ticker", 0, 20)
    news_lookback_hours = _parse_int(str(args.news_lookback_hours), "news-lookback-hours", 1, 24 * 14)
    trend_weight = _parse_float(str(args.trend_weight), "trend-weight", 0.0)
    rsi_weight = _parse_float(str(args.rsi_weight), "rsi-weight", 0.0)
    news_weight = _parse_float(str(args.news_weight), "news-weight", 0.0)
    signal_threshold = _parse_float(str(args.signal_threshold), "signal-threshold", 0.0, 1.0)
    telegram_parse_mode = (args.telegram_parse_mode or "HTML").strip().upper()
    if telegram_parse_mode not in {"HTML", "MARKDOWN", "MARKDOWNV2", "NONE"}:
        raise ValueError("telegram-parse-mode must be HTML, MARKDOWN, MARKDOWNV2, or NONE")

    total_weight = trend_weight + rsi_weight + news_weight
    if total_weight <= 0.0:
        raise ValueError("trend-weight + rsi-weight + news-weight must be > 0")
    trend_weight = trend_weight / total_weight
    rsi_weight = rsi_weight / total_weight
    news_weight = news_weight / total_weight
    return Settings(
        db_path=os.path.expanduser(os.path.expandvars(args.db_path)),
        tickers=normalized,
        telegram_bot_token=args.telegram_bot_token,
        telegram_chat_id=args.telegram_chat_id,
        finnhub_api_key=args.finnhub_api_key,
        marketaux_api_key=args.marketaux_api_key,
        ollama_host=args.ollama_host.rstrip("/"),
        ollama_model=args.ollama_model,
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


def build_signal(
    ticker: str,
    closes: list[float],
    latest_news: list[NewsItem],
    *,
    trend_weight: float,
    rsi_weight: float,
    news_weight: float,
    signal_threshold: float,
) -> Signal | None:
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

    score = trend_score * trend_weight + rsi_score * rsi_weight + news_score * news_weight
    score = max(-1.0, min(1.0, score))
    confidence = min(1.0, max(0.0, abs(score)))

    if score >= signal_threshold:
        label = "BUY"
    elif score <= -signal_threshold:
        label = "SELL"
    else:
        label = "HOLD"

    top_news = [
        f"{n.impact}:{n.title[:40]} ({n.score:+.2f})" for n in latest_news[:2]
    ]
    if not top_news:
        top_news = ["no_news_signal"]

    def _fmt_signal_value(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.2f}"

    reason = (
        f"price={price:.2f}, SMA5={_fmt_signal_value(sma_fast)}, SMA20={_fmt_signal_value(sma_slow)}, RSI14={_fmt_signal_value(rsi)}, "
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


def _fetch_marketaux_news(
    ticker: str,
    api_key: str,
    limit: int = 5,
    *,
    lookback_hours: int = 24,
) -> list[dict[str, Any]]:
    if not api_key:
        return []
    if limit <= 0 or lookback_hours <= 0:
        return []

    url = "https://api.marketaux.com/v1/news/all"
    payload = {
        "symbols": ticker,
        "limit": str(limit * 2),
        "language": "en",
        "api_token": api_key,
    }
    data = _http_get_json(url, payload)
    raw_articles = data.get("data", []) or []
    if not isinstance(raw_articles, list):
        return []

    cutoff = int(time.time() - max(1, lookback_hours) * 3600)
    articles: list[dict[str, Any]] = []
    for article in raw_articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        if not title:
            continue
        published = _parse_news_published(article.get("published_at") or article.get("published"))
        if published is None:
            continue
        if published < cutoff:
            continue
        article["published_at"] = published
        articles.append(article)

    return articles[:limit]


def _llm_infer_news_summary(
    ollama_host: str,
    model: str,
    ticker: str,
    title: str,
    url: str,
    body: str,
) -> NewsItem:
    if not body:
        body = title
    prompt = (
        "다음 뉴스를 한국어로 간결히 정리해서 JSON 한 개만 반환하세요.\n"
        '형식은 {"summary": "...", "impact": "up/down/neutral", '
        '"score": -1.0~1.0, "keywords": ["..."]} 이어야 합니다.\n'
        f"티커: {ticker}\n"
        f"제목: {title}\n"
        f"링크: {url}\n"
        f"본문: {body[:1200]}\n"
    )
    try:
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
    except Exception as exc:
        logger.warning("ollama summarize failed: %s", exc)
        parsed = None
        raw = ""
    if not parsed:
        return _news_fallback_summary(ticker, title, url, body, raw_summary=raw)

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


def _parse_news_published(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        normalized = text.replace("Z", "+00:00")
        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.fromisoformat(normalized) if fmt.startswith("%Y-%m-%dT%H:%M") else datetime.strptime(normalized, fmt)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return int(parsed.timestamp())
            except Exception:
                continue
    return None


def _news_fallback_summary(
    ticker: str,
    title: str,
    url: str,
    body: str,
    raw_summary: str | None = None,
) -> NewsItem:
    text = f"{title} {body}".lower()
    positive_hits = sum(
        1 for token in [
            "급등",
            "상향",
            "호재",
            "매수",
            "개선",
            "강세",
            "이익",
            "매출",
            "beat",
            "surge",
            "growth",
            "record",
        ] if token in text
    )
    negative_hits = sum(
        1 for token in [
            "급락",
            "하락",
            "규제",
            "적자",
            "오류",
            "리스크",
            "약세",
            "실적 악화",
            "down",
            "penalty",
            "lawsuit",
            "risk",
            "fraud",
        ] if token in text
    )

    if positive_hits and not negative_hits:
        impact = "up"
        score = min(0.45, 0.22 + min(0.23, positive_hits * 0.05))
    elif negative_hits and not positive_hits:
        impact = "down"
        score = -(min(0.45, 0.22 + min(0.23, negative_hits * 0.05)))
    else:
        impact = "neutral"
        score = 0.0
    summary = (
        (raw_summary or "").strip()[:300]
        if raw_summary and raw_summary.strip()
        else f"{ticker} 관련 뉴스 수집됨. 키워드 기반 폴백 분석 사용."
    )
    if not summary:
        summary = f"{ticker} 관련 뉴스 수집됨. 키워드 기반 폴백 분석 사용."

    return NewsItem(
        title=title,
        published=int(time.time()),
        url=url,
        summary=summary,
        impact=impact,
        score=score,
        keywords=[],
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


def _build_deterministic_rng(seed_text: str) -> random.Random:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    seed = int(digest[:16], 16)
    return random.Random(seed)


def _mock_prices(ticker: str, count: int = 40) -> list[PricePoint]:
    if count <= 0:
        return []

    rng = _build_deterministic_rng(f"{ticker}:mock-prices")
    now = int(time.time())
    start = now - (count * 24 * 3600)
    base = 100.0 + (rng.random() * 40.0)
    points: list[PricePoint] = []
    close = base

    for i in range(count):
        start_ts = start + (i + 1) * 24 * 3600
        drift = (rng.random() - 0.5) * 4.0
        close = max(10.0, close + drift)
        points.append(PricePoint(start_ts, round(close, 2)))

    return points


def _mock_news(ticker: str, limit: int) -> list[NewsItem]:
    templates = [
        {
            "title": f"{ticker} 시장 기대치 상회 실적 예상",
            "published": int(time.time()) - 4200,
            "url": "https://example.local/news/earnings",
            "summary": f"{ticker} 실적 개선과 수급 안정성으로 단기 매수 모멘텀 가능성",
            "impact": "up",
            "score": 0.46,
            "keywords": ["실적", "수요", "확장"],
        },
        {
            "title": f"{ticker} 규제 뉴스로 실적 전망 압박 논란",
            "published": int(time.time()) - 2800,
            "url": "https://example.local/news/regulation",
            "summary": f"{ticker} 규제 이슈로 밸류에이션 부담이 커질 수 있는 구간",
            "impact": "down",
            "score": -0.41,
            "keywords": ["규제", "심사", "영향"],
        },
        {
            "title": f"{ticker} 업종 지표 강세, 거래량 증가 신호 관찰",
            "published": int(time.time()) - 1300,
            "url": "https://example.local/news/sector",
            "summary": f"{ticker} 업종 수요가 증가하며 추세 반등 가능성이 제시됨",
            "impact": "up",
            "score": 0.33,
            "keywords": ["거래량", "업종", "회복"],
        },
    ]

    output: list[NewsItem] = []
    for idx in range(min(limit, len(templates))):
        item = templates[idx]
        output.append(
            NewsItem(
                title=item["title"],
                published=item["published"],
                url=f"{item['url']}?ticker={ticker}&n={idx}",
                summary=item["summary"],
                impact=item["impact"],
                score=float(item["score"]),
                keywords=list(item["keywords"]),
            )
        )
    return output


def _is_cooldown_active(conn: sqlite3.Connection, ticker: str, signal: str, cooldown_minutes: int) -> bool:
    window = int((datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)).timestamp())
    row = conn.execute(
        """
        SELECT ts FROM alerts
        WHERE ticker = ? AND signal = ? AND ts >= ?
        ORDER BY ts DESC LIMIT 1
        """,
        (ticker, signal, window),
    ).fetchone()

    return row is not None


def _build_telegram_message(signal: Signal, latest_news: list[NewsItem]) -> str:
    def _fmt(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.2f}"

    def _shorten(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    lines = [
        f"[{signal.ticker}] {signal.signal} ({signal.confidence:.2f})",
        f"시간: {datetime.now(timezone.utc).isoformat()}",
        f"가격: {signal.price:.2f}, SMA5={_fmt(signal.sma_fast)}, SMA20={_fmt(signal.sma_slow)}, RSI14={_fmt(signal.rsi)}",
        f"근거: {signal.reason}",
        "뉴스:",
    ]
    if latest_news:
        for idx, item in enumerate(latest_news[:3], start=1):
            lines.append(
                f"{idx}. {item.impact.upper()}({item.score:+.2f}) {_shorten(item.title, 90)}"
            )
    else:
        lines.append("1) 최근 반영 뉴스 없음")
    return "\n".join(lines)[:3500]


def _remember_prices(conn: sqlite3.Connection, ticker: str, points: list[PricePoint], source: str = "finnhub") -> None:
    conn.executemany(
        "INSERT OR IGNORE INTO price_ticks (ticker, ts, source, close) VALUES (?, ?, ?, ?)",
        [(ticker, p.ts, source, p.close) for p in points],
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
    parse_mode: str,
    text: str,
) -> bool:
    if not bot_token or not chat_id:
        logger.info("skip telegram (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID): %s", text)
        return False

    payload = {
        "chat_id": chat_id,
        "text": html.escape(text) if parse_mode == "HTML" else text,
    }
    if parse_mode != "NONE":
        payload["parse_mode"] = parse_mode

    try:
        response = _http_post_json(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            payload,
        )
    except Exception as exc:
        logger.warning("telegram send failed for token/chat=%s: %s", chat_id, exc)
        return False

    if not response.get("ok", False):
        logger.warning("telegram API rejected request: %s", response)
    return bool(response.get("ok", False))


def run_once(settings: Settings) -> None:
    init_db(settings.db_path)

    with sqlite3.connect(settings.db_path) as conn:
        for ticker in settings.tickers:
            try:
                if settings.dry_run:
                    closes_points = _mock_prices(ticker, 40)
                elif not settings.finnhub_api_key:
                    raise RuntimeError("FINNHUB_API_KEY is required for price fetch")
                else:
                    closes_points = _fetch_finnhub_closes(ticker, settings.finnhub_api_key)

                _remember_prices(
                    conn,
                    ticker,
                    closes_points,
                    source="mock" if settings.dry_run else "finnhub",
                )
                if not closes_points:
                    logger.warning("no price data for %s", ticker)
                    continue

                closes = [p.close for p in closes_points]
                logger.info("fetched price points for %s: %d", ticker, len(closes_points))

                latest_news: list[NewsItem] = []
                if settings.dry_run:
                    raw_news = _mock_news(ticker, settings.max_news_per_ticker)
                    for item in raw_news:
                        _remember_news(
                            conn,
                            ticker,
                            item,
                            source_url=item.url,
                        )
                        latest_news.append(item)
                elif settings.marketaux_api_key:
                    raw_news = _fetch_marketaux_news(
                        ticker,
                        settings.marketaux_api_key,
                        limit=settings.max_news_per_ticker,
                        lookback_hours=settings.news_lookback_hours,
                    )
                    seen_news = set()
                    for n in raw_news:
                        title = (n.get("title") or "").strip()
                        url = n.get("url") or ""
                        if not title:
                            continue
                        normalized_news_key = f"{ticker}:{url}:{title}"
                        if normalized_news_key in seen_news:
                            continue
                        seen_news.add(normalized_news_key)
                        body = (n.get("description") or n.get("snippet") or "")[:1200]
                        item = _llm_infer_news_summary(
                            settings.ollama_host,
                            settings.ollama_model,
                            ticker,
                            title,
                            url,
                            body,
                        )
                        _remember_news(
                            conn,
                            ticker,
                            item,
                            source_url=url,
                        )
                        latest_news.append(item)
                elif not settings.dry_run:
                    logger.info("marketaux key not set; skip news fetch for %s", ticker)

                signal = build_signal(
                    ticker,
                    closes,
                    latest_news,
                    trend_weight=settings.trend_weight,
                    rsi_weight=settings.rsi_weight,
                    news_weight=settings.news_weight,
                    signal_threshold=settings.signal_threshold,
                )
                if signal is None:
                    continue

                if signal.signal == "HOLD":
                    conn.execute(
                        "INSERT INTO alerts (ts, ticker, signal, confidence, reason, sent, error_message) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (int(time.time()), ticker, signal.signal, signal.confidence, signal.reason, 0, None),
                    )
                    logger.info("signal hold: %s", signal.reason)
                    continue

                if _is_cooldown_active(conn, ticker, signal.signal, settings.cooldown_minutes):
                    logger.info("skip due to cooldown: %s", ticker)
                    continue

                message = _build_telegram_message(signal, latest_news)
                sent = _send_telegram(
                    settings.telegram_bot_token,
                    settings.telegram_chat_id,
                    settings.telegram_parse_mode,
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
