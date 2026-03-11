from __future__ import annotations

try:
    from .presentation import css_root_block
except ImportError:
    from presentation import css_root_block  # type: ignore


def render_report_theme(extra_css: str = "") -> str:
    return f"""
    {css_root_block()}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.86), transparent 36%),
        linear-gradient(180deg, #f9f5ee 0%, #f2ece2 100%);
      color: var(--ink);
      font-family: "SF Pro Display", "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    }}
    code {{
      font-family: "SF Mono", "SFMono-Regular", ui-monospace, monospace;
      font-size: 0.92em;
    }}
    .shell {{
      max-width: 1240px;
      margin: 0 auto;
    }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 24px;
      background: var(--panel);
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.5fr) minmax(280px, 0.9fr);
      gap: 18px;
      margin-bottom: 18px;
    }}
    .intro {{
      padding: 24px;
    }}
    .intro h1 {{
      margin: 0;
      font-size: clamp(30px, 6vw, 56px);
      line-height: 0.94;
      letter-spacing: -0.05em;
    }}
    .intro p {{
      margin: 18px 0 0;
      color: var(--muted);
      line-height: 1.7;
      font-size: 14px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .meta span {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      padding: 0 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.64);
      color: var(--muted);
      font-size: 12px;
      font-weight: 600;
    }}
    .gate-strip {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .gate-chip {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.68);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.03em;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
      padding: 18px;
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
      background: rgba(255,255,255,0.6);
    }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .value {{
      margin-top: 6px;
      font-size: 28px;
      font-weight: 700;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      margin-bottom: 18px;
    }}
    .summary-box,
    .table-panel,
    .notes,
    .footnote {{
      padding: 20px;
    }}
    .summary-box h2,
    .table-head h2,
    .notes h2 {{
      margin: 0 0 10px;
      font-size: 18px;
      letter-spacing: -0.02em;
    }}
    .summary-box p,
    .notes p,
    .footnote {{
      margin: 0;
      line-height: 1.7;
      color: var(--muted);
    }}
    .notes ul {{
      margin: 0;
      padding-left: 18px;
      line-height: 1.7;
    }}
    .table-panel {{
      margin-bottom: 18px;
      overflow-x: auto;
    }}
    .table-head {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }}
    .table-head p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
      min-width: 760px;
    }}
    th, td {{
      text-align: left;
      padding: 10px 8px;
      border-top: 1px solid var(--line);
    }}
    th {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    @media (max-width: 900px) {{
      body {{ padding: 14px; }}
      .hero,
      .summary-grid {{ grid-template-columns: 1fr; }}
    }}
    {extra_css}
    """
