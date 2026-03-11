from __future__ import annotations

import html
import logging

try:
    from .notifier_collector import http_post_json
    from .notifier_models import NewsItem, Signal
    from .telegram_message import build_telegram_message
except ImportError:
    from notifier_collector import http_post_json  # type: ignore
    from notifier_models import NewsItem, Signal  # type: ignore
    from telegram_message import build_telegram_message  # type: ignore


logger = logging.getLogger("trading_signal_notifier")


def send_telegram(
    bot_token: str | None,
    chat_id: str | None,
    parse_mode: str,
    text: str,
) -> bool:
    if not bot_token or not chat_id:
        logger.info("텔레그램 스킵(토큰/채팅ID 미설정): %s", text)
        return False

    payload = {
        "chat_id": chat_id,
        "text": html.escape(text) if parse_mode == "HTML" else text,
    }
    if parse_mode != "NONE":
        payload["parse_mode"] = parse_mode

    try:
        response = http_post_json(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            payload,
        )
    except Exception as exc:
        logger.warning(
            "텔레그램 발송 실패(token/chat=%s): %s",
            chat_id,
            exc,
        )
        return False

    if not response.get("ok", False):
        logger.warning(
            "텔레그램 API 거절: code=%s desc=%s",
            response.get("error_code"),
            response.get("description"),
        )
    return bool(response.get("ok", False))


def send_signal_notification(
    bot_token: str | None,
    chat_id: str | None,
    parse_mode: str,
    signal: Signal,
    latest_news: list[NewsItem],
) -> bool:
    return send_telegram(
        bot_token,
        chat_id,
        parse_mode,
        build_telegram_message(signal, latest_news),
    )
