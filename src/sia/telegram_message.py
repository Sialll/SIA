from __future__ import annotations

from datetime import datetime
from typing import Any

try:
    from .presentation import impact_display, reason_display, score_display, signal_display
except ImportError:
    from presentation import impact_display, reason_display, score_display, signal_display  # type: ignore


def build_telegram_message(signal: Any, latest_news: list[Any]) -> str:
    def _fmt(value: float | None) -> str:
        return "없음" if value is None else f"{value:.2f}"

    def _shorten(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "…"

    local_now = datetime.now().astimezone()
    lines = [
        f"[{signal.ticker}] 텔레그램 신호 알림",
        f"현재 판단은 {signal_display(signal.signal)}이며 신뢰도는 {score_display(signal.confidence)}입니다.",
        f"기준 시각은 {local_now.strftime('%Y-%m-%d %H:%M:%S %Z')}입니다.",
        (
            f"가격은 {signal.price:.2f}, "
            f"SMA5는 {_fmt(signal.sma_fast)}, "
            f"SMA20은 {_fmt(signal.sma_slow)}, "
            f"RSI14는 {_fmt(signal.rsi)}입니다."
        ),
        f"판단 근거: {reason_display(signal.reason) or '근거 정보가 없습니다.'}",
        "뉴스 요약:",
    ]
    if latest_news:
        for index, item in enumerate(latest_news[:3], start=1):
            lines.append(
                f"{index}) {impact_display(getattr(item, 'impact', ''))} | "
                f"{_shorten(str(getattr(item, 'title', '제목 없음')), 90)} "
                f"({score_display(getattr(item, 'score', 0.0))})"
            )
    else:
        lines.append("1) 최근 반영 뉴스 없음")
    return "\n".join(lines)[:3500]
