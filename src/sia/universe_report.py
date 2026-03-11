from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path

try:
    from .report_common import render_empty_report_html
    from .report_theme import render_report_theme
    from .report_widgets import (
        render_hero_section,
        render_meta_row,
        render_stats_panel,
        render_summary_panel,
        render_table_section,
    )
    from .universe_collector import DEFAULT_UNIVERSE_SNAPSHOT_PATH
except ImportError:
    from report_common import render_empty_report_html  # type: ignore
    from report_theme import render_report_theme  # type: ignore
    from report_widgets import (  # type: ignore
        render_hero_section,
        render_meta_row,
        render_stats_panel,
        render_summary_panel,
        render_table_section,
    )
    from universe_collector import DEFAULT_UNIVERSE_SNAPSHOT_PATH  # type: ignore


DEFAULT_UNIVERSE_REPORT_PATH = os.path.expanduser(
    os.getenv("SIA_UNIVERSE_REPORT_PATH", "~/Library/Caches/sia-notifier/universe-report.html")
)
DEFAULT_UNIVERSE_HISTORY_PATH = os.path.expanduser(
    os.getenv("SIA_UNIVERSE_HISTORY_PATH", "~/Library/Caches/sia-notifier/universe-history.jsonl")
)
MARKET_SETTINGS_COMMAND = "/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Settings.command"
MARKET_TICKERS_COMMAND = "/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Tickers.command"


def fmt_ts(raw: object) -> str:
    try:
        import datetime as dt

        return dt.datetime.fromtimestamp(int(raw)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return "없음"


def market_name(market: str) -> str:
    return {
        "US": "미국",
        "KR": "한국",
        "EU": "유럽",
        "JP": "일본",
    }.get(str(market).upper(), str(market))


def source_name(source: str) -> str:
    return {
        "default_seed": "기본 1B+",
        "user": "사용자 추가",
    }.get(str(source), str(source))


def floor_text(raw: object) -> str:
    try:
        value = int(raw)
    except Exception:
        return "-"
    if value >= 1_000_000_000:
        return f"USD {value:,} (약 {value / 1_000_000_000:.1f}B)"
    return f"USD {value:,}"


def load_snapshot(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_history(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def delta_text(current: int, previous: int | None) -> str:
    if previous is None:
        return "기준 없음"
    diff = current - previous
    if diff > 0:
        return f"+{diff}"
    if diff < 0:
        return str(diff)
    return "0"


def render_report(snapshot: dict[str, object], history_rows: list[dict[str, object]] | None = None) -> str:
    counts = dict(snapshot.get("counts") or {})
    by_market = dict(counts.get("by_market") or {})
    by_source = dict(counts.get("by_source") or {})
    entries = list(snapshot.get("entries") or [])
    enabled_markets = list(snapshot.get("enabled_markets") or [])
    history_rows = history_rows or []
    previous_counts = dict(((history_rows[-2].get("counts") or {}) if len(history_rows) >= 2 else {}) or {})
    previous_by_market = dict(previous_counts.get("by_market") or {})

    per_market_source: dict[str, Counter[str]] = {}
    for entry in entries:
        market = str(entry.get("market", ""))
        source = str(entry.get("source", ""))
        if market not in per_market_source:
            per_market_source[market] = Counter()
        per_market_source[market][source] += 1

    hero = render_hero_section(
        "관심 종목 구성표",
        "기본 시총 seed와 사용자가 추가한 종목이 현재 관심 종목 목록에 어떻게 들어가는지 한눈에 보여주는 읽기 전용 화면입니다.",
        render_meta_row(
            [
                f"생성 시각 {fmt_ts(snapshot.get('generated_at'))}",
                f"활성 시장 {', '.join(market_name(m) for m in enabled_markets) if enabled_markets else '없음'}",
                f"기본 유니버스 {'사용' if snapshot.get('include_default_universe') else '해제'}",
            ]
        ),
        render_stats_panel(
            [
                ("총 티커", str(counts.get("total", 0))),
                ("기본 1B+", str(by_source.get("default_seed", 0))),
                ("사용자 추가", str(by_source.get("user", 0))),
                ("시가총액 기준", floor_text(snapshot.get("market_cap_floor_usd"))),
            ]
        ),
    )

    summary = render_summary_panel(
        "수집 상태",
        (
            f"<p>모드: <code>{snapshot.get('mode', '-')}</code></p>"
            f"<p>상태: <code>{snapshot.get('future_collector_status', '-')}</code></p>"
            f"<p>{snapshot.get('future_collector_next_step', '')}</p>"
        ),
    )
    settings_summary = render_summary_panel(
        "현재 설정",
        (
            f"<p>기본 유니버스: <strong>{'사용' if snapshot.get('include_default_universe') else '해제'}</strong></p>"
            f"<p>활성 시장: <strong>{', '.join(market_name(m) for m in enabled_markets) if enabled_markets else '없음'}</strong></p>"
            f"<p>기본 유니버스 포함 여부는 <code>SIA-Market-Tickers.command</code>에서 함께 바꿉니다.</p>"
        ),
    )
    action_panel = render_summary_panel(
        "수정 바로가기",
        (
            '<div class="action-row">'
            f'<a class="action-link" href="file://{MARKET_SETTINGS_COMMAND}" target="_blank" rel="noreferrer">시장 체크 변경</a>'
            f'<a class="action-link" href="file://{MARKET_TICKERS_COMMAND}" target="_blank" rel="noreferrer">티커 / 기본 유니버스 수정</a>'
            "</div>"
            '<p class="action-note">브라우저 설정에 따라 직접 실행이 막힐 수 있습니다.</p>'
            f'<p class="action-note">시장 체크: <code>{MARKET_SETTINGS_COMMAND}</code></p>'
            f'<p class="action-note">티커 / 기본 유니버스: <code>{MARKET_TICKERS_COMMAND}</code></p>'
        ),
    )
    filter_panel = render_summary_panel(
        "시장 필터",
        (
            '<div class="filter-row">'
            '<button type="button" class="filter-chip active" data-market-filter="ALL">전체</button>'
            + "".join(
                f'<button type="button" class="filter-chip" data-market-filter="{market}">{market_name(market)}</button>'
                for market in enabled_markets
            )
            + "</div>"
            '<p class="action-note">아래 표들은 선택한 시장 기준으로 바로 필터링됩니다.</p>'
        ),
    )
    source_filter_panel = render_summary_panel(
        "출처 필터",
        (
            '<div class="filter-row">'
            '<button type="button" class="filter-chip active" data-source-filter="ALL">전체</button>'
            '<button type="button" class="filter-chip" data-source-filter="default_seed">기본 1B+</button>'
            '<button type="button" class="filter-chip" data-source-filter="user">사용자 추가</button>'
            "</div>"
            '<p class="action-note">선택한 출처가 없는 시장 행은 숨기고, 티커 목록은 출처 기준으로 직접 필터링합니다.</p>'
        ),
    )
    search_panel = render_summary_panel(
        "티커 검색",
        (
            '<div class="search-wrap">'
            '<input id="tickerSearch" class="search-input" type="search" placeholder="예: AAPL, 005930.KS, ASML.AS" autocomplete="off">'
            "</div>"
            '<div class="action-row">'
            '<button type="button" id="resetUniverseFilters" class="filter-chip">필터 초기화</button>'
            "</div>"
            '<p class="action-note">티커 목록 표에서 입력한 티커를 바로 찾습니다.</p>'
        ),
    )
    sort_panel = render_summary_panel(
        "정렬",
        (
            '<div class="search-wrap">'
            '<select id="universeSortSelect" class="search-input">'
            '<option value="ticker">티커순</option>'
            '<option value="market">시장순</option>'
            '<option value="source">출처순</option>'
            "</select>"
            "</div>"
            '<p class="action-note">티커 목록 표를 선택한 기준으로 정렬합니다.</p>'
        ),
    )
    filter_summary_panel = render_summary_panel(
        "현재 필터",
        '<div id="filterSummaryBar" class="filter-summary-bar"><span class="summary-chip">기본 보기</span></div>',
    )
    total_count = int(counts.get("total", 0) or 0)
    default_count = int(by_source.get("default_seed", 0) or 0)
    user_count = int(by_source.get("user", 0) or 0)
    default_ratio = (default_count / total_count * 100.0) if total_count else 0.0
    user_ratio = (user_count / total_count * 100.0) if total_count else 0.0
    ratio_panel = render_summary_panel(
        "출처 비중",
        (
            '<div class="ratio-bar">'
            f'<span class="ratio-segment ratio-default" style="width:{default_ratio:.2f}%"></span>'
            f'<span class="ratio-segment ratio-user" style="width:{user_ratio:.2f}%"></span>'
            "</div>"
            '<div class="ratio-legend">'
            f'<div><span class="legend-dot ratio-default"></span>기본 1B+ {default_count}개 ({default_ratio:.1f}%)</div>'
            f'<div><span class="legend-dot ratio-user"></span>사용자 추가 {user_count}개 ({user_ratio:.1f}%)</div>'
            "</div>"
        ),
    )

    market_rows = []
    for market in enabled_markets:
        market_counter = per_market_source.get(str(market), Counter())
        market_rows.append(
            f"""
            <tr data-market="{market}" data-source="ALL" data-default-count="{market_counter.get('default_seed', 0)}" data-user-count="{market_counter.get('user', 0)}">
              <td>{market_name(str(market))}</td>
              <td>{by_market.get(str(market), 0)}</td>
              <td>{market_counter.get('default_seed', 0)}</td>
              <td>{market_counter.get('user', 0)}</td>
            </tr>
            """
        )
    market_table = render_table_section(
        "시장별 구성",
        "활성 시장별 기본 1B+ seed와 사용자 추가 티커 수입니다.",
        ["시장", "총 티커", "기본 1B+", "사용자 추가"],
        "".join(market_rows) or "<tr><td colspan='4'>데이터 없음</td></tr>",
    )
    market_mix_rows = []
    for market in enabled_markets:
        market_counter = per_market_source.get(str(market), Counter())
        default_count_market = int(market_counter.get("default_seed", 0))
        user_count_market = int(market_counter.get("user", 0))
        total_market = default_count_market + user_count_market
        default_ratio_market = (default_count_market / total_market * 100.0) if total_market else 0.0
        user_ratio_market = (user_count_market / total_market * 100.0) if total_market else 0.0
        market_mix_rows.append(
            f"""
            <tr data-market="{market}" data-source="ALL" data-default-count="{default_count_market}" data-user-count="{user_count_market}">
              <td>{market_name(str(market))}</td>
              <td>
                <div class="market-ratio-bar">
                  <span class="ratio-segment ratio-default" style="width:{default_ratio_market:.2f}%"></span>
                  <span class="ratio-segment ratio-user" style="width:{user_ratio_market:.2f}%"></span>
                </div>
              </td>
              <td>{default_count_market}개 ({default_ratio_market:.1f}%)</td>
              <td>{user_count_market}개 ({user_ratio_market:.1f}%)</td>
            </tr>
            """
        )
    market_mix_table = render_table_section(
        "시장별 출처 비중",
        "시장별로 기본 1B+ seed와 사용자 추가 티커가 어떤 비율로 섞여 있는지 보여줍니다.",
        ["시장", "누적 막대", "기본 1B+", "사용자 추가"],
        "".join(market_mix_rows) or "<tr><td colspan='4'>데이터 없음</td></tr>",
    )
    market_change_rows = []
    for market in enabled_markets:
        current_total = int(by_market.get(str(market), 0) or 0)
        previous_total = previous_by_market.get(str(market))
        market_counter = per_market_source.get(str(market), Counter())
        default_count_market = int(market_counter.get("default_seed", 0))
        user_count_market = int(market_counter.get("user", 0))
        if previous_total is not None:
            previous_total = int(previous_total)
        change_class = "delta-flat"
        if previous_total is not None:
            if current_total > previous_total:
                change_class = "delta-up"
            elif current_total < previous_total:
                change_class = "delta-down"
        market_change_rows.append(
            f"""
            <tr data-market="{market}" data-source="ALL" data-default-count="{default_count_market}" data-user-count="{user_count_market}">
              <td>{market_name(str(market))}</td>
              <td>{current_total}</td>
              <td class="{change_class}">{delta_text(current_total, previous_total)}</td>
              <td>{previous_total if previous_total is not None else '-'}</td>
            </tr>
            """
        )
    market_change_table = render_table_section(
        "시장별 티커 수 변화",
        "직전 스냅샷과 비교한 시장별 티커 수 변화입니다. history가 없으면 기준 없음으로 표시됩니다.",
        ["시장", "현재", "변화", "직전"],
        "".join(market_change_rows) or "<tr><td colspan='4'>데이터 없음</td></tr>",
    )

    entry_rows = []
    for entry in entries:
        entry_rows.append(
            f"""
            <tr class="universe-entry-row" data-market="{entry.get('market', '')}" data-ticker="{entry.get('ticker', '')}" data-source="{entry.get('source', '')}">
              <td>{market_name(str(entry.get('market', '')))}</td>
              <td><code>{entry.get('ticker', '')}</code></td>
              <td>{source_name(str(entry.get('source', '')))}</td>
              <td>{floor_text(entry.get('market_cap_floor_usd'))}</td>
            </tr>
            """
        )
    entries_table = render_table_section(
        "티커 목록",
        "현재 유니버스 스냅샷에 들어간 전체 티커입니다.",
        ["시장", "티커", "출처", "시가총액 기준"],
        "".join(entry_rows) or "<tr><td colspan='4'>데이터 없음</td></tr>",
    )

    extra_css = """
    code {
      font-weight: 700;
    }
    .summary-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 18px;
      margin-bottom: 18px;
    }
    .ratio-bar {
      display: flex;
      width: 100%;
      height: 16px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(12, 18, 28, 0.08);
      border: 1px solid var(--line);
      margin-bottom: 12px;
    }
    .ratio-segment {
      display: block;
      height: 100%;
    }
    .market-ratio-bar {
      display: flex;
      width: min(280px, 100%);
      height: 14px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(12, 18, 28, 0.08);
      border: 1px solid var(--line);
    }
    .ratio-default {
      background: #155e63;
    }
    .ratio-user {
      background: #c17c10;
    }
    .ratio-legend {
      display: grid;
      gap: 8px;
      color: var(--muted);
      font-size: 13px;
    }
    .legend-dot {
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-right: 8px;
      vertical-align: middle;
    }
    .action-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    }
    .filter-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 12px;
    }
    .filter-chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 36px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      cursor: pointer;
    }
    .filter-chip.active {
      border-color: rgba(21,94,99,0.28);
      background: rgba(21,94,99,0.10);
      color: #155e63;
    }
    .search-wrap {
      display: flex;
      align-items: center;
      min-height: 38px;
      padding: 0;
    }
    .search-input {
      width: 100%;
      min-height: 42px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.82);
      color: var(--ink);
      padding: 0 14px;
      font-size: 14px;
      outline: none;
    }
    .search-input:focus {
      border-color: rgba(21,94,99,0.28);
      box-shadow: 0 0 0 3px rgba(21,94,99,0.10);
    }
    .action-link {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 0 14px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.76);
      color: var(--ink);
      text-decoration: none;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    .action-link:hover {
      border-color: rgba(21,94,99,0.28);
    }
    .action-note {
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.6;
      font-size: 13px;
    }
    .filter-summary-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .summary-chip {
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      padding: 0 12px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.03em;
    }
    .delta-up {
      color: #0f766e;
      font-weight: 700;
    }
    .delta-down {
      color: #b91c1c;
      font-weight: 700;
    }
    .delta-flat {
      color: var(--muted);
      font-weight: 700;
    }
    @media (max-width: 900px) {
      .summary-grid {
        grid-template-columns: 1fr;
      }
    }
    """
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 유니버스 리포트</title>
  <style>
    {render_report_theme(extra_css)}
  </style>
</head>
<body>
  <main class="shell">
    {hero}
    <section class="summary-grid">
      {summary}
      {settings_summary}
      {action_panel}
      {ratio_panel}
      {filter_panel}
      {source_filter_panel}
      {search_panel}
      {sort_panel}
      {filter_summary_panel}
    </section>
    {market_table}
    {market_mix_table}
    {market_change_table}
    {entries_table}
  </main>
  <script>
    const MARKET_FILTER_STORAGE_KEY = "sia.universeReport.marketFilter";
    const SOURCE_FILTER_STORAGE_KEY = "sia.universeReport.sourceFilter";
    const SEARCH_QUERY_STORAGE_KEY = "sia.universeReport.searchQuery";
    const SORT_STORAGE_KEY = "sia.universeReport.sort";
    const marketFilterButtons = Array.from(document.querySelectorAll("[data-market-filter]"));
    const sourceFilterButtons = Array.from(document.querySelectorAll("[data-source-filter]"));
    const marketRows = Array.from(document.querySelectorAll("tr[data-market]"));
    const tickerSearchInput = document.getElementById("tickerSearch");
    const resetUniverseFiltersButton = document.getElementById("resetUniverseFilters");
    const universeSortSelect = document.getElementById("universeSortSelect");
    const filterSummaryBar = document.getElementById("filterSummaryBar");
    const universeEntryRows = Array.from(document.querySelectorAll(".universe-entry-row"));
    let currentMarketFilter = "ALL";
    let currentSourceFilter = "ALL";
    let currentTickerQuery = "";
    let currentSort = "ticker";

    function loadSavedMarketFilter() {{
      try {{
        const saved = window.localStorage.getItem(MARKET_FILTER_STORAGE_KEY) || "ALL";
        const allowed = ["ALL", {", ".join(repr(m) for m in enabled_markets)}];
        return allowed.includes(saved) ? saved : "ALL";
      }} catch (_error) {{
        return "ALL";
      }}
    }}

    function saveMarketFilter(value) {{
      try {{
        window.localStorage.setItem(MARKET_FILTER_STORAGE_KEY, value);
      }} catch (_error) {{
      }}
    }}

    function loadSavedSourceFilter() {{
      try {{
        const saved = window.localStorage.getItem(SOURCE_FILTER_STORAGE_KEY) || "ALL";
        return ["ALL", "default_seed", "user"].includes(saved) ? saved : "ALL";
      }} catch (_error) {{
        return "ALL";
      }}
    }}

    function saveSourceFilter(value) {{
      try {{
        window.localStorage.setItem(SOURCE_FILTER_STORAGE_KEY, value);
      }} catch (_error) {{
      }}
    }}

    function loadSavedSearchQuery() {{
      try {{
        return String(window.localStorage.getItem(SEARCH_QUERY_STORAGE_KEY) || "");
      }} catch (_error) {{
        return "";
      }}
    }}

    function saveSearchQuery(value) {{
      try {{
        window.localStorage.setItem(SEARCH_QUERY_STORAGE_KEY, value);
      }} catch (_error) {{
      }}
    }}

    function loadSavedSort() {{
      try {{
        const saved = window.localStorage.getItem(SORT_STORAGE_KEY) || "ticker";
        return ["ticker", "market", "source"].includes(saved) ? saved : "ticker";
      }} catch (_error) {{
        return "ticker";
      }}
    }}

    function saveSort(value) {{
      try {{
        window.localStorage.setItem(SORT_STORAGE_KEY, value);
      }} catch (_error) {{
      }}
    }}

    function clearSavedFilters() {{
      try {{
        window.localStorage.removeItem(MARKET_FILTER_STORAGE_KEY);
        window.localStorage.removeItem(SOURCE_FILTER_STORAGE_KEY);
        window.localStorage.removeItem(SEARCH_QUERY_STORAGE_KEY);
        window.localStorage.removeItem(SORT_STORAGE_KEY);
      }} catch (_error) {{
      }}
    }}

    function applyFilters() {{
      marketFilterButtons.forEach((button) => {{
        const isActive = button.dataset.marketFilter === currentMarketFilter;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      }});
      sourceFilterButtons.forEach((button) => {{
        const isActive = button.dataset.sourceFilter === currentSourceFilter;
        button.classList.toggle("active", isActive);
        button.setAttribute("aria-pressed", isActive ? "true" : "false");
      }});
      marketRows.forEach((row) => {{
        const rowMarket = row.dataset.market || "";
        const marketMatch = currentMarketFilter === "ALL" || rowMarket === currentMarketFilter;
        const isEntryRow = row.classList.contains("universe-entry-row");
        const tickerValue = (row.dataset.ticker || "").toUpperCase();
        const rowSource = row.dataset.source || "";
        const defaultCount = Number(row.dataset.defaultCount || "0");
        const userCount = Number(row.dataset.userCount || "0");
        let sourceMatch = true;
        if (currentSourceFilter !== "ALL") {{
          if (isEntryRow) {{
            sourceMatch = rowSource === currentSourceFilter;
          }} else if (currentSourceFilter === "default_seed") {{
            sourceMatch = defaultCount > 0;
          }} else if (currentSourceFilter === "user") {{
            sourceMatch = userCount > 0;
          }}
        }}
        const searchMatch = !isEntryRow || !currentTickerQuery || tickerValue.includes(currentTickerQuery);
        row.style.display = marketMatch && sourceMatch && searchMatch ? "" : "none";
      }});
      sortUniverseEntries();
      renderFilterSummary();
    }}

    function sortUniverseEntries() {{
      if (!universeEntryRows.length) {{
        return;
      }}
      const tbody = universeEntryRows[0].parentElement;
      if (!tbody) {{
        return;
      }}
      const marketRank = {{ US: 0, KR: 1, EU: 2, JP: 3 }};
      const sourceRank = {{ default_seed: 0, user: 1 }};
      universeEntryRows.sort((left, right) => {{
        const leftTicker = String(left.dataset.ticker || "");
        const rightTicker = String(right.dataset.ticker || "");
        const leftMarket = String(left.dataset.market || "");
        const rightMarket = String(right.dataset.market || "");
        const leftSource = String(left.dataset.source || "");
        const rightSource = String(right.dataset.source || "");

        if (currentSort === "market") {{
          const marketDiff = (marketRank[leftMarket] ?? 99) - (marketRank[rightMarket] ?? 99);
          if (marketDiff !== 0) {{
            return marketDiff;
          }}
          return leftTicker.localeCompare(rightTicker);
        }}
        if (currentSort === "source") {{
          const sourceDiff = (sourceRank[leftSource] ?? 99) - (sourceRank[rightSource] ?? 99);
          if (sourceDiff !== 0) {{
            return sourceDiff;
          }}
          const marketDiff = (marketRank[leftMarket] ?? 99) - (marketRank[rightMarket] ?? 99);
          if (marketDiff !== 0) {{
            return marketDiff;
          }}
          return leftTicker.localeCompare(rightTicker);
        }}
        return leftTicker.localeCompare(rightTicker);
      }});
      universeEntryRows.forEach((row) => tbody.appendChild(row));
    }}

    function renderFilterSummary() {{
      if (!filterSummaryBar) {{
        return;
      }}
      const chips = [];
      if (currentMarketFilter !== "ALL") {{
        const activeMarketButton = marketFilterButtons.find((button) => button.dataset.marketFilter === currentMarketFilter);
        chips.push("시장 " + (activeMarketButton ? activeMarketButton.textContent : currentMarketFilter));
      }}
      if (currentSourceFilter !== "ALL") {{
        const activeSourceButton = sourceFilterButtons.find((button) => button.dataset.sourceFilter === currentSourceFilter);
        chips.push("출처 " + (activeSourceButton ? activeSourceButton.textContent : currentSourceFilter));
      }}
      if (currentTickerQuery) {{
        chips.push("검색 " + currentTickerQuery);
      }}
      if (currentSort !== "ticker") {{
        const label = currentSort === "market" ? "시장순" : "출처순";
        chips.push("정렬 " + label);
      }}
      if (!chips.length) {{
        chips.push("기본 보기");
      }}
      filterSummaryBar.innerHTML = chips.map((text) => '<span class="summary-chip">' + text + "</span>").join("");
    }}

    marketFilterButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        currentMarketFilter = button.dataset.marketFilter || "ALL";
        saveMarketFilter(currentMarketFilter);
        applyFilters();
      }});
    }});

    sourceFilterButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        currentSourceFilter = button.dataset.sourceFilter || "ALL";
        saveSourceFilter(currentSourceFilter);
        applyFilters();
      }});
    }});

    if (tickerSearchInput) {{
      tickerSearchInput.addEventListener("input", () => {{
        currentTickerQuery = String(tickerSearchInput.value || "").trim().toUpperCase();
        saveSearchQuery(String(tickerSearchInput.value || "").trim());
        applyFilters();
      }});
    }}

    if (resetUniverseFiltersButton) {{
      resetUniverseFiltersButton.addEventListener("click", () => {{
        currentMarketFilter = "ALL";
        currentSourceFilter = "ALL";
        currentTickerQuery = "";
        currentSort = "ticker";
        clearSavedFilters();
        if (tickerSearchInput) {{
          tickerSearchInput.value = "";
        }}
        if (universeSortSelect) {{
          universeSortSelect.value = "ticker";
        }}
        applyFilters();
      }});
    }}

    if (universeSortSelect) {{
      universeSortSelect.addEventListener("change", () => {{
        currentSort = String(universeSortSelect.value || "ticker");
        saveSort(currentSort);
        applyFilters();
      }});
    }}

    currentMarketFilter = loadSavedMarketFilter();
    currentSourceFilter = loadSavedSourceFilter();
    currentTickerQuery = loadSavedSearchQuery().trim().toUpperCase();
    currentSort = loadSavedSort();
    if (tickerSearchInput) {{
      tickerSearchInput.value = loadSavedSearchQuery();
    }}
    if (universeSortSelect) {{
      universeSortSelect.value = currentSort;
    }}
    applyFilters();
  </script>
</body>
</html>"""


def write_report(path: Path, html_text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sia_universe_report")
    parser.add_argument("--snapshot", default=DEFAULT_UNIVERSE_SNAPSHOT_PATH)
    parser.add_argument("--history", default=DEFAULT_UNIVERSE_HISTORY_PATH)
    parser.add_argument("--out", default=DEFAULT_UNIVERSE_REPORT_PATH)
    args = parser.parse_args(argv)

    snapshot_path = Path(args.snapshot).expanduser()
    history_path = Path(args.history).expanduser()
    report_path = Path(args.out).expanduser()

    if not snapshot_path.exists():
        write_report(
            report_path,
            render_empty_report_html(
                "유니버스 리포트",
                "유니버스 스냅샷이 아직 없습니다. 먼저 universe refresh를 실행하세요.",
            ),
        )
        print(report_path)
        return 0

    snapshot = load_snapshot(snapshot_path)
    write_report(report_path, render_report(snapshot, load_history(history_path)))
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
