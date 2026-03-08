from __future__ import annotations

import html
import re

try:
    from .presentation import report_label_display, signal_set_display
    from .report_theme import render_report_theme
except ImportError:
    from presentation import report_label_display, signal_set_display  # type: ignore
    from report_theme import render_report_theme  # type: ignore


COMMON_LITERAL_REPLACEMENTS = [
    ("Aligned sources:", "정합 소스:"),
    ("Horizon:", "기간:"),
    ("Signal Edge", "시그널 엣지"),
    ("Signal Set", "신호 집합"),
    ("BUY/SELL", "매수/매도"),
    ("BUY-only", "매수만"),
    ("SELL-only", "매도만"),
    (" price tick", " 가격 틱"),
    (" snapshot", " 스냅샷"),
    ("signal entry price", "신호 진입 가격"),
    ("sample Sharpe", "표본 Sharpe"),
    ("skipped overlap", "중복 제외"),
    ("stored price tick", "저장된 가격 틱"),
    ("avg edge", "평균 엣지"),
    ("corr", "상관계수"),
]


def render_empty_report_html(title: str, message: str) -> str:
    extra_css = """
    body {
      min-height: 100vh;
      display: grid;
      place-items: center;
    }
    .panel {
      width: min(760px, 100%);
      padding: 28px;
    }
    h1 {
      margin: 0 0 12px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(34px, 6vw, 56px);
    }
    p {
      margin: 0;
      line-height: 1.7;
      color: var(--muted);
    }
    """
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    {render_report_theme(extra_css)}
  </style>
</head>
<body>
  <section class="panel">
    <h1>{html.escape(title)}</h1>
    <p>{html.escape(message)}</p>
  </section>
</body>
</html>"""


def localize_report_html(text: str, replacements: list[tuple[str, str]]) -> str:
    localized = text
    for source, target in COMMON_LITERAL_REPLACEMENTS:
        localized = localized.replace(source, target)
    for source, target in replacements:
        localized = localized.replace(source, target)
    localized = re.sub(
        r'(<div class="label">)([^<]+)(</div>)',
        lambda match: f"{match.group(1)}{report_label_display(match.group(2))}{match.group(3)}",
        localized,
    )
    localized = re.sub(
        r"(<th>)([^<]+)(</th>)",
        lambda match: f"{match.group(1)}{report_label_display(match.group(2))}{match.group(3)}",
        localized,
    )
    localized = localized.replace(">ALL<", f">{signal_set_display('ALL')}<")
    localized = localized.replace(">BUY<", f">{signal_set_display('BUY')}<")
    localized = localized.replace(">SELL<", f">{signal_set_display('SELL')}<")
    localized = localized.replace(">HOLD<", f">{signal_set_display('HOLD')}<")
    return localized
