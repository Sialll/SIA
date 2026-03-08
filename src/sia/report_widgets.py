from __future__ import annotations

try:
    from .presentation import report_label_display
except ImportError:
    from presentation import report_label_display  # type: ignore


def render_meta_row(items: list[str]) -> str:
    spans = "".join(f"<span>{item}</span>" for item in items)
    return f'<div class="meta">{spans}</div>'


def render_stats_panel(items: list[tuple[str, str]]) -> str:
    stats_html = "".join(
        f'<div class="stat"><div class="label">{report_label_display(label)}</div><div class="value">{value}</div></div>'
        for label, value in items
    )
    return f'<aside class="panel stats">{stats_html}</aside>'


def render_hero_section(
    title_html: str,
    description_html: str,
    meta_html: str,
    stats_html: str,
    extra_html: str = "",
) -> str:
    return f"""
    <section class="hero">
      <article class="panel intro">
        <h1>{title_html}</h1>
        <p>{description_html}</p>
        {meta_html}
        {extra_html}
      </article>
      {stats_html}
    </section>"""


def render_table_section(
    title: str,
    subtitle: str,
    headers: list[str],
    rows_html: str,
    panel_class: str = "panel table-panel",
) -> str:
    header_html = "".join(f"<th>{report_label_display(header)}</th>" for header in headers)
    return f"""
    <section class="{panel_class}">
      <div class="table-head">
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      <table>
        <thead>
          <tr>{header_html}</tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>"""


def render_summary_panel(
    title: str,
    body_html: str,
    panel_class: str = "panel summary-box",
) -> str:
    return f"""
    <article class="{panel_class}">
      <h2>{title}</h2>
      {body_html}
    </article>"""


def render_footnote_section(
    title: str,
    body_html: str,
    panel_class: str = "panel footnote",
) -> str:
    return f"""
    <section class="{panel_class}">
      <strong>{title}</strong><br>
      {body_html}
    </section>"""


def render_gate_strip(chips_html: str) -> str:
    return f'<div class="gate-strip">{chips_html}</div>'


def render_notes_section(
    title: str,
    list_items_html: str,
    footnote_html: str = "",
    panel_class: str = "panel notes",
) -> str:
    footnote_block = f'<p class="footnote">{footnote_html}</p>' if footnote_html else ""
    return f"""
    <section class="{panel_class}">
      <h2>{title}</h2>
      <ul>
        {list_items_html}
      </ul>
      {footnote_block}
    </section>"""


def render_action_section(
    title: str,
    list_items_html: str,
    footnote_html: str = "",
    panel_class: str = "panel notes",
) -> str:
    return render_notes_section(title, list_items_html, footnote_html, panel_class)
