from __future__ import annotations

SIGNAL_LABELS = {
    "BUY": "매수",
    "SELL": "매도",
    "HOLD": "관망",
}

SIGNAL_SET_LABELS = {
    "ALL": "전체",
    "BUY": "매수",
    "SELL": "매도",
    "HOLD": "관망",
}

REPORT_LABELS = {
    "Signals": "신호 수",
    "Aligned": "정합 수",
    "Samples": "표본 수",
    "Mock Filtered": "모의 제외",
    "Trades": "거래 수",
    "Snapshots": "스냅샷 수",
    "Tickers": "티커 수",
    "BUY/SELL": "매수/매도",
    "Verdict": "판정",
    "Strict Aligned": "정합 수",
    "Ready Buckets": "준비 구간 수",
    "Horizon": "Horizon",
    "Signal": "신호",
    "Signal Set": "신호 집합",
    "Ticker": "티커",
    "Bucket": "구간",
    "Factor": "팩터",
    "Status": "상태",
    "Min Gate": "최소 기준",
    "Coverage": "커버리지",
    "Future Gap": "미래 부족",
    "Usable Tickers": "활용 티커 수",
    "Hold": "보유",
    "Overlap Skip": "중복 건너뜀",
    "Avg Score": "평균 점수",
    "Avg Return": "평균 수익률",
    "Avg Edge": "평균 엣지",
    "Directional Hit": "방향 적중률",
    "Corr": "상관",
    "Hit Rate": "적중률",
    "Entry": "진입",
    "Exit": "청산",
    "Strategy Return": "전략 수익률",
    "Trade Return": "거래 수익률",
    "Max Favorable": "최대 유리",
    "Max Adverse": "최대 불리",
    "Confidence": "신뢰도",
    "Aligned sources:": "정합 소스:",
    "Backtested Samples": "백테스트 표본",
    "Eligible Signals": "평가 가능 신호",
    "BUY-only": "매수만",
    "SELL-only": "매도만",
}

RISK_LABELS = {
    "HIGH": "높음",
    "MEDIUM": "보통",
    "LOW": "낮음",
}

MACRO_LABELS = {
    "RISK_ON": "위험선호",
    "RISK_OFF": "위험회피",
    "MIXED": "혼합",
    "PARTIAL": "부분",
}

EVENT_LABELS = {
    "earnings": "실적",
    "regulation": "규제",
    "insider": "내부자",
    "capital": "자본",
}

IMPACT_LABELS = {
    "positive": "긍정",
    "negative": "부정",
    "neutral": "중립",
    "mixed": "혼합",
    "high": "높음",
    "medium": "보통",
    "low": "낮음",
}

REASON_KEY_LABELS = {
    "confirm": "확인 지표",
    "gate": "판단 게이트",
    "conflict": "신호 충돌",
    "regime": "시장 국면",
    "events": "이벤트",
    "event": "이벤트",
    "macro": "매크로",
}

REASON_FRAGMENT_REPLACEMENTS = [
    ("RISK_OFF", "위험회피"),
    ("RISK_ON", "위험선호"),
    ("PARTIAL", "부분"),
    ("MIXED", "혼합"),
    ("BUY", "매수"),
    ("SELL", "매도"),
    ("HOLD", "관망"),
    ("HIGH", "높음"),
    ("MEDIUM", "보통"),
    ("LOW", "낮음"),
    ("UP", "상승"),
    ("DOWN", "하락"),
    ("FLAT", "횡보"),
    ("buy_blocked", "매수 차단"),
    ("sell_blocked", "매도 차단"),
    ("pass", "통과"),
    ("blocked", "차단"),
    ("earnings", "실적"),
    ("regulation", "규제"),
    ("insider", "내부자"),
    ("capital", "자본"),
    ("strong", "강함"),
    ("weak", "약함"),
]

THEME_COLOR_TOKENS = {
    "bg": "#f4efe6",
    "panel": "rgba(255, 252, 246, 0.88)",
    "ink": "#171411",
    "muted": "#6c6257",
    "line": "rgba(23, 20, 17, 0.12)",
    "accent": "#1f6f78",
    "buy": "#155e63",
    "sell": "#9a3412",
    "hold": "#6b7280",
    "gold": "#c69d5a",
    "shadow": "0 18px 50px rgba(33, 24, 14, 0.10)",
}


def signal_display(value: object) -> str:
    normalized = str(value or "").upper()
    return SIGNAL_LABELS.get(normalized, str(value or "-"))


def signal_set_display(value: object) -> str:
    normalized = str(value or "").upper()
    return SIGNAL_SET_LABELS.get(normalized, str(value or "-"))


def report_label_display(value: object) -> str:
    text = str(value or "")
    return REPORT_LABELS.get(text, text)


def score_value(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value) * 100.0
    except (TypeError, ValueError):
        return None


def score_display(value: object, digits: int = 1, suffix: str = "점") -> str:
    numeric = score_value(value)
    if numeric is None:
        return "-"
    text = f"{numeric:.{digits}f}"
    return f"{text}{suffix}" if suffix else text


def score_delta_display(value: object, digits: int = 1, suffix: str = "점") -> str:
    numeric = score_value(value)
    if numeric is None:
        return "-"
    text = f"{numeric:+.{digits}f}"
    return f"{text}{suffix}" if suffix else text


def risk_display(value: object) -> str:
    normalized = str(value or "").upper()
    return RISK_LABELS.get(normalized, str(value or "-"))


def macro_env_display(value: object) -> str:
    normalized = str(value or "").upper()
    return MACRO_LABELS.get(normalized, str(value or "-"))


def event_type_display(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return EVENT_LABELS.get(normalized, str(value or "-"))


def signal_class_name(value: object) -> str:
    normalized = str(value or "").upper()
    if normalized == "BUY":
        return "buy"
    if normalized == "SELL":
        return "sell"
    return "hold"


def risk_class_name(value: object) -> str:
    normalized = str(value or "").upper()
    if normalized == "HIGH":
        return "risk-high"
    if normalized == "MEDIUM":
        return "risk-medium"
    return "risk-low"


def macro_env_class_name(value: object) -> str:
    normalized = str(value or "").upper()
    if normalized == "RISK_ON":
        return "macro-risk-on"
    if normalized == "RISK_OFF":
        return "macro-risk-off"
    if normalized == "PARTIAL":
        return "macro-partial"
    return "macro-mixed"


def event_type_class_name(value: object) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == "earnings":
        return "event-earnings"
    if normalized == "regulation":
        return "event-regulation"
    if normalized == "insider":
        return "event-insider"
    if normalized == "capital":
        return "event-capital"
    return "event-generic"


def impact_display(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return IMPACT_LABELS.get(normalized, str(value or "기타"))


def translate_reason_fragment(text: object) -> str:
    output = str(text or "")
    for source, target in REASON_FRAGMENT_REPLACEMENTS:
        output = output.replace(source, target)
    return output


def reason_display(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    parts: list[str] = []
    for chunk in [part.strip() for part in text.split(",") if part.strip()]:
        if "=" in chunk:
            key, raw_value = [piece.strip() for piece in chunk.split("=", 1)]
            parts.append(
                f"{REASON_KEY_LABELS.get(key, key)}: {translate_reason_fragment(raw_value)}"
            )
        else:
            parts.append(translate_reason_fragment(chunk))
    return " / ".join(parts) if parts else translate_reason_fragment(text)


def css_root_block() -> str:
    return "\n".join(
        [
            ":root {",
            f"  --bg: {THEME_COLOR_TOKENS['bg']};",
            f"  --panel: {THEME_COLOR_TOKENS['panel']};",
            f"  --ink: {THEME_COLOR_TOKENS['ink']};",
            f"  --muted: {THEME_COLOR_TOKENS['muted']};",
            f"  --line: {THEME_COLOR_TOKENS['line']};",
            f"  --accent: {THEME_COLOR_TOKENS['accent']};",
            f"  --buy: {THEME_COLOR_TOKENS['buy']};",
            f"  --sell: {THEME_COLOR_TOKENS['sell']};",
            f"  --hold: {THEME_COLOR_TOKENS['hold']};",
            f"  --gold: {THEME_COLOR_TOKENS['gold']};",
            f"  --shadow: {THEME_COLOR_TOKENS['shadow']};",
            "}",
        ]
    )
