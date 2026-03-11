from __future__ import annotations

import hashlib
import json
import logging
import math
import random
import sqlite3
import time
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

try:
    from .http_client import http_get_json, http_get_text, http_post_json, json_request, parse_http_error_payload
    from . import notifier_pipeline
    from .notifier_models import NewsItem, PricePoint
except ImportError:
    from http_client import http_get_json, http_get_text, http_post_json, json_request, parse_http_error_payload  # type: ignore
    import notifier_pipeline  # type: ignore
    from notifier_models import NewsItem, PricePoint  # type: ignore


logger = logging.getLogger("trading_signal_notifier")


def has_finnhub_access_denied_error(payload: dict[str, Any]) -> bool:
    raw = str(payload.get("error", ""))
    lowered = raw.lower()
    return "access to this resource" in lowered or "you don't have access" in lowered


def ollama_is_available(host: str, model: str, timeout: int = 2) -> tuple[bool, str]:
    if not host or not model:
        return False, "OLLAMA 미설정"

    try:
        payload = json_request(
            f"{host}/api/tags",
            method="GET",
            timeout=timeout,
            max_retries=0,
        )
    except Exception as exc:
        return False, str(exc)

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list) or not models:
        return True, ""

    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if name == model or name.startswith(f"{model}:"):
            return True, ""

    return False, f"요청 모델이 설치되어 있지 않습니다: {model}"


def fetch_yahoo_closes(ticker: str, count: int = 40) -> list[PricePoint]:
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(ticker)
    payload = {
        "interval": "1d",
        "range": "6mo",
        "includePrePost": "false",
        "events": "div,splits",
    }
    data = http_get_json(
        url,
        payload,
        timeout=25,
        headers={"User-Agent": "SIA Notifier/1.0"},
    )
    result_list = data.get("chart", {}).get("result") if isinstance(data, dict) else None
    if not isinstance(result_list, list) or not result_list:
        raise RuntimeError(f"Yahoo 차트 응답 형식 오류 ({ticker}): {data}")

    result = result_list[0]
    if not isinstance(result, dict):
        raise RuntimeError(f"Yahoo 차트 결과 형식 오류 ({ticker})")

    timestamps = result.get("timestamp") or []
    indicators = result.get("indicators", {})
    quote_series = indicators.get("quote") if isinstance(indicators, dict) else None
    if not quote_series or not isinstance(quote_series, list):
        raise RuntimeError(f"Yahoo 차트 quote 데이터 누락 ({ticker})")

    closes = quote_series[0].get("close") if isinstance(quote_series[0], dict) else None
    if not isinstance(timestamps, list) or not isinstance(closes, list):
        raise RuntimeError(f"Yahoo 차트 close/timestamp 형식 오류 ({ticker})")

    points: list[PricePoint] = []
    for raw_ts, close in zip(timestamps, closes):
        if close is None:
            continue
        try:
            value = float(close)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value) or value <= 0:
            continue
        points.append(PricePoint(int(raw_ts), value))

    return points[-count:] if points else []


def fetch_finnhub_closes(ticker: str, api_key: str, *, count: int = 40) -> list[PricePoint]:
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

    data = http_get_json(url, payload)
    if data.get("s") != "ok":
        if has_finnhub_access_denied_error(data):
            raise RuntimeError("FINNHUB_CANDLE_ACCESS_DENIED: 권한/요금제 제약으로 stock/candle 접근이 제한됨")
        if "error" in data and str(data.get("error")).strip():
            raise RuntimeError(f"Finnhub candle 실패: {data.get('error')}")
        raise RuntimeError(f"Finnhub candle 실패: {data}")

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


def fetch_yahoo_rss_news(ticker: str, limit: int = 5, *, lookback_hours: int = 24) -> list[dict[str, Any]]:
    if limit <= 0 or lookback_hours <= 0:
        return []

    xml_text = http_get_text(
        "https://feeds.finance.yahoo.com/rss/2.0/headline",
        params={"s": ticker, "region": "US", "lang": "en-US"},
        timeout=20,
        headers={"User-Agent": "SIA Notifier/1.0"},
    )

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    cutoff = int(time.time() - max(1, lookback_hours) * 3600)
    articles: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        if not isinstance(item, ET.Element):
            continue
        title = (item.findtext("title") or "").strip()
        if not title:
            continue

        published_text = item.findtext("pubDate") or item.findtext("published") or item.findtext("date")
        published = parse_news_published(published_text or "")
        if published is None or published < cutoff:
            continue

        link = (item.findtext("link") or "").strip()
        if not link:
            continue

        articles.append(
            {
                "title": title,
                "url": link,
                "published_at": published,
                "published": published,
                "description": (item.findtext("description") or "").strip(),
            }
        )
        if len(articles) >= limit:
            break

    return articles


def fetch_marketaux_news(
    ticker: str,
    api_key: str,
    limit: int = 5,
    *,
    lookback_hours: int = 24,
) -> list[dict[str, Any]]:
    if not api_key or limit <= 0 or lookback_hours <= 0:
        return []

    data = http_get_json(
        "https://api.marketaux.com/v1/news/all",
        {
            "symbols": ticker,
            "limit": str(limit * 2),
            "language": "en",
            "api_token": api_key,
        },
    )
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
        published = parse_news_published(article.get("published_at") or article.get("published"))
        if published is None or published < cutoff:
            continue
        article["published_at"] = published
        articles.append(article)

    return articles[:limit]


def llm_infer_news_summary(
    ollama_host: str,
    model: str,
    ticker: str,
    title: str,
    url: str,
    body: str,
) -> tuple[NewsItem, bool]:
    if not ollama_host or not model:
        return news_fallback_summary(ticker, title, url, body, raw_summary=""), False

    prompt = (
        "다음 뉴스를 한국어로 간결히 정리해서 JSON 한 개만 반환하세요.\n"
        '형식은 {"summary": "...", "impact": "up/down/neutral", '
        '"score": -1.0~1.0, "keywords": ["..."]} 이어야 합니다.\n'
        f"ticker: {ticker}\n"
        f"제목: {title}\n"
        f"링크: {url}\n"
        f"본문: {(body or title)[:1200]}\n"
    )
    try:
        response = http_post_json(
            f"{ollama_host}/api/generate",
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2},
            },
        )
        parsed = safe_json_from_text(str(response.get("response", "")))
    except Exception:
        return news_fallback_summary(ticker, title, url, body, raw_summary=""), False

    if not parsed:
        return news_fallback_summary(ticker, title, url, body, raw_summary=""), False

    score = max(-1.0, min(1.0, float(parsed.get("score", 0.0) or 0.0)))
    impact = str(parsed.get("impact", "neutral")).lower()
    if impact not in {"up", "down", "neutral"}:
        impact = "neutral"

    return (
        NewsItem(
            title=title,
            published=int(time.time()),
            url=url,
            summary=str(parsed.get("summary", ""))[:300],
            impact=impact,
            score=score if impact == "up" else (-score if impact == "down" else score * 0.25),
            keywords=extract_keywords(parsed.get("keywords", "")),
        ),
        True,
    )


def parse_news_published(value: Any) -> int | None:
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
                parsed = (
                    datetime.fromisoformat(normalized)
                    if fmt.startswith("%Y-%m-%dT%H:%M")
                    else datetime.strptime(normalized, fmt)
                )
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return int(parsed.timestamp())
            except Exception:
                continue
        try:
            parsed_rfc = parsedate_to_datetime(text)
        except Exception:
            parsed_rfc = None
        if parsed_rfc:
            if parsed_rfc.tzinfo is None:
                parsed_rfc = parsed_rfc.replace(tzinfo=timezone.utc)
            return int(parsed_rfc.timestamp())
    return None


def news_fallback_summary(
    ticker: str,
    title: str,
    url: str,
    body: str,
    raw_summary: str | None = None,
) -> NewsItem:
    text = f"{title} {body}".lower()
    positive_hits = sum(
        1
        for token in [
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
        ]
        if token in text
    )
    negative_hits = sum(
        1
        for token in [
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
        ]
        if token in text
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


def safe_json_from_text(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def extract_keywords(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value][:5]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()][:5]
    return []


def build_deterministic_rng(seed_text: str) -> random.Random:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def mock_prices(ticker: str, count: int = 40) -> list[PricePoint]:
    if count <= 0:
        return []

    rng = build_deterministic_rng(f"{ticker}:mock-prices")
    now = int(time.time())
    start = now - (count * 24 * 3600)
    close = 100.0 + (rng.random() * 40.0)
    points: list[PricePoint] = []

    for index in range(count):
        start_ts = start + (index + 1) * 24 * 3600
        close = max(10.0, close + (rng.random() - 0.5) * 4.0)
        points.append(PricePoint(start_ts, round(close, 2)))

    return points


def mock_news(ticker: str, limit: int) -> list[NewsItem]:
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
    for index in range(min(limit, len(templates))):
        item = templates[index]
        output.append(
            NewsItem(
                title=item["title"],
                published=item["published"],
                url=f"{item['url']}?ticker={ticker}&n={index}",
                summary=item["summary"],
                impact=item["impact"],
                score=float(item["score"]),
                keywords=list(item["keywords"]),
            )
        )
    return output


def collect_news_items(
    conn: sqlite3.Connection,
    ticker: str,
    raw_news: list[dict[str, Any]],
    *,
    ollama_host: str,
    ollama_model: str,
) -> list[NewsItem]:
    seen_news = set()
    output: list[NewsItem] = []
    use_ollama = bool(ollama_host and ollama_model)
    if use_ollama:
        use_ollama, reason = ollama_is_available(ollama_host, ollama_model)
        if not use_ollama:
            logger.warning(
                "뉴스 요약 LLM 비활성: %s (요청 모델=%s). 규칙 기반 요약으로 전환합니다.",
                reason or "알 수 없는 원인",
                ollama_model,
            )

    for news in raw_news:
        if not isinstance(news, dict):
            continue
        title = (news.get("title") or "").strip()
        url = (news.get("url") or "").strip()
        if not title or not url:
            continue
        normalized_key = f"{ticker}:{url}:{title}"
        if normalized_key in seen_news:
            continue
        seen_news.add(normalized_key)

        body = str(news.get("description") or news.get("snippet") or "")[:1200]
        if use_ollama:
            item, is_llm = llm_infer_news_summary(
                ollama_host,
                ollama_model,
                ticker,
                title,
                url,
                body,
            )
            if not is_llm:
                use_ollama = False
                logger.warning(
                    "Ollama 요약 실패(%s). 이 티커는 규칙 기반 요약으로 폴백합니다.",
                    ticker,
                )
        else:
            item = news_fallback_summary(ticker, title, url, body, raw_summary="")

        notifier_pipeline.remember_news(
            conn,
            ticker,
            item,
            source_url=url,
        )
        output.append(item)

    return output
