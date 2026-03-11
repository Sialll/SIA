from __future__ import annotations

import argparse
import json
import os
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


DEFAULT_FULL_UNIVERSE_SNAPSHOT_PATH = os.path.expanduser(
    os.getenv("SIA_FULL_UNIVERSE_SNAPSHOT_PATH", "~/Library/Caches/sia-notifier/full-universe-snapshot.json")
)
DEFAULT_FULL_UNIVERSE_REPORT_PATH = os.path.expanduser(
    os.getenv("SIA_FULL_UNIVERSE_REPORT_PATH", "~/Library/Caches/sia-notifier/full-universe-report.html")
)


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


def floor_text(raw: object) -> str:
    try:
        value = int(raw)
    except Exception:
        return "-"
    if value >= 1_000_000_000:
        return f"USD {value:,} (약 {value / 1_000_000_000:.1f}B)"
    return f"USD {value:,}"


def market_cap_text(raw: object) -> str:
    try:
        value = int(raw)
    except Exception:
        return "-"
    if value >= 1_000_000_000_000:
        return f"USD {value / 1_000_000_000_000:.2f}T"
    if value >= 1_000_000_000:
        return f"USD {value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"USD {value / 1_000_000:.2f}M"
    return f"USD {value:,}"


def load_snapshot(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def render_report(snapshot: dict[str, object]) -> str:
    counts = dict(snapshot.get("counts") or {})
    by_market = dict(counts.get("by_market") or {})
    candidate_by_market = dict(counts.get("candidate_by_market") or {})
    entries = list(snapshot.get("entries") or [])
    enabled_markets = list(snapshot.get("enabled_markets") or [])
    provider = str(snapshot.get("provider", "-"))
    provider_status = str(snapshot.get("provider_status", "-"))
    input_path = str(snapshot.get("provider_input_path", "-"))
    floor = snapshot.get("market_cap_floor_usd")

    hero = render_hero_section(
        "시총 상위 종목 보고서",
        "전종목 후보 입력 중에서 현재 시장과 시가총액 기준을 통과한 종목을 정리한 읽기 전용 보고서입니다.",
        render_meta_row(
            [
                f"생성 시각 {fmt_ts(snapshot.get('generated_at'))}",
                f"provider {provider}",
                f"상태 {provider_status}",
            ]
        ),
        render_stats_panel(
            [
                ("후보 수", str(counts.get("candidate_total", 0))),
                ("적격 수", str(counts.get("eligible_total", 0))),
                ("활성 시장", ", ".join(market_name(m) for m in enabled_markets) if enabled_markets else "없음"),
                ("시가총액 기준", floor_text(floor)),
            ]
        ),
    )

    setup_panel = render_summary_panel(
        "수집 설정",
        (
            f"<p>provider: <code>{provider}</code></p>"
            f"<p>provider status: <code>{provider_status}</code></p>"
            f"<p>입력 경로: <code>{input_path}</code></p>"
            f"<p>다음 단계: {snapshot.get('next_step', '')}</p>"
        ),
    )
    filter_panel = render_summary_panel(
        "시장 필터",
        (
            '<div class="control-row">'
            '<button type="button" class="filter-chip active" data-market-filter="ALL">전체</button>'
            + "".join(
                f'<button type="button" class="filter-chip" data-market-filter="{market}">{market_name(market)}</button>'
                for market in enabled_markets
            )
            + "</div>"
        ),
    )
    search_panel = render_summary_panel(
        "티커 검색",
        (
            '<div class="control-row">'
            '<input id="fullUniverseSearch" class="control-input" type="search" placeholder="예: AAPL, 005930.KS, ASML.AS" autocomplete="off">'
            "</div>"
        ),
    )
    sort_panel = render_summary_panel(
        "정렬",
        (
            '<div class="control-row">'
            '<select id="fullUniverseSort" class="control-input">'
            '<option value="ticker">티커순</option>'
            '<option value="market">시장순</option>'
            '<option value="market_cap">시총순</option>'
            "</select>"
            '<button type="button" id="resetFullUniverseControls" class="filter-chip">초기화</button>'
            "</div>"
        ),
    )
    filter_summary_panel = render_summary_panel(
        "현재 필터",
        '<div id="fullUniverseFilterSummary" class="filter-summary-bar"><span class="summary-chip">기본 보기</span></div>',
    )

    market_rows = []
    for market in enabled_markets:
        market_rows.append(
            f"""
            <tr class="market-row" data-market="{market}">
              <td>{market_name(str(market))}</td>
              <td>{candidate_by_market.get(str(market), 0)}</td>
              <td>{by_market.get(str(market), 0)}</td>
            </tr>
            """
        )
    market_table = render_table_section(
        "시장별 후보 현황",
        "입력 후보 수와 시가총액 기준 통과 후 적격 수를 비교합니다.",
        ["시장", "후보 수", "적격 수"],
        "".join(market_rows) or "<tr><td colspan='3'>데이터 없음</td></tr>",
    )

    entry_rows = []
    for entry in entries:
        entry_rows.append(
            f"""
            <tr class="entry-row" data-market="{entry.get('market', '')}" data-ticker="{entry.get('ticker', '')}" data-market-cap="{entry.get('market_cap_usd', 0)}">
              <td>{market_name(str(entry.get('market', '')))}</td>
              <td><code>{entry.get('ticker', '')}</code></td>
              <td>{entry.get('company_name', '') or '-'}</td>
              <td>{market_cap_text(entry.get('market_cap_usd'))}</td>
              <td>{entry.get('source', '')}</td>
            </tr>
            """
        )
    entries_table = render_table_section(
        "시가총액 기준 통과 종목",
        "현재 provider 입력 기준으로 시장/시총 필터를 통과한 항목입니다.",
        ["시장", "티커", "회사명", "시가총액", "출처"],
        "".join(entry_rows) or "<tr><td colspan='5'>적격 데이터 없음</td></tr>",
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
    .control-row {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
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
    .control-input {
      min-height: 42px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.82);
      color: var(--ink);
      padding: 0 14px;
      font-size: 14px;
      outline: none;
      flex: 1 1 220px;
    }
    .control-input:focus {
      border-color: rgba(21,94,99,0.28);
      box-shadow: 0 0 0 3px rgba(21,94,99,0.10);
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
    """
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SIA 전종목 유니버스 리포트</title>
  <style>
    {render_report_theme(extra_css)}
  </style>
</head>
<body>
  <main class="shell">
    {hero}
    <section class="summary-grid">
      {setup_panel}
      {filter_panel}
      {search_panel}
      {sort_panel}
      {filter_summary_panel}
    </section>
    {market_table}
    {entries_table}
  </main>
  <script>
    const MARKET_FILTER_KEY = "sia.fullUniverseReport.marketFilter";
    const SEARCH_KEY = "sia.fullUniverseReport.search";
    const SORT_KEY = "sia.fullUniverseReport.sort";

    const marketFilterButtons = Array.from(document.querySelectorAll("[data-market-filter]"));
    const marketRows = Array.from(document.querySelectorAll(".market-row"));
    const entryRows = Array.from(document.querySelectorAll(".entry-row"));
    const searchInput = document.getElementById("fullUniverseSearch");
    const sortSelect = document.getElementById("fullUniverseSort");
    const resetButton = document.getElementById("resetFullUniverseControls");
    const filterSummaryBar = document.getElementById("fullUniverseFilterSummary");

    let currentMarket = "ALL";
    let currentSearch = "";
    let currentSort = "ticker";

    function loadStored(key, fallback) {{
      try {{
        return window.localStorage.getItem(key) || fallback;
      }} catch (_error) {{
        return fallback;
      }}
    }}

    function saveStored(key, value) {{
      try {{
        window.localStorage.setItem(key, value);
      }} catch (_error) {{
      }}
    }}

    function clearStored() {{
      try {{
        window.localStorage.removeItem(MARKET_FILTER_KEY);
        window.localStorage.removeItem(SEARCH_KEY);
        window.localStorage.removeItem(SORT_KEY);
      }} catch (_error) {{
      }}
    }}

    function sortEntryRows() {{
      if (!entryRows.length) {{
        return;
      }}
      const tbody = entryRows[0].parentElement;
      if (!tbody) {{
        return;
      }}
      const marketRank = {{ US: 0, KR: 1, EU: 2, JP: 3 }};
      entryRows.sort((left, right) => {{
        const leftTicker = String(left.dataset.ticker || "");
        const rightTicker = String(right.dataset.ticker || "");
        const leftMarket = String(left.dataset.market || "");
        const rightMarket = String(right.dataset.market || "");
        const leftCap = Number(left.dataset.marketCap || "0");
        const rightCap = Number(right.dataset.marketCap || "0");

        if (currentSort === "market_cap") {{
          if (rightCap !== leftCap) {{
            return rightCap - leftCap;
          }}
          return leftTicker.localeCompare(rightTicker);
        }}
        if (currentSort === "market") {{
          const marketDiff = (marketRank[leftMarket] ?? 99) - (marketRank[rightMarket] ?? 99);
          if (marketDiff !== 0) {{
            return marketDiff;
          }}
          return leftTicker.localeCompare(rightTicker);
        }}
        return leftTicker.localeCompare(rightTicker);
      }});
      entryRows.forEach((row) => tbody.appendChild(row));
    }}

    function applyControls() {{
      marketFilterButtons.forEach((button) => {{
        const active = button.dataset.marketFilter === currentMarket;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", active ? "true" : "false");
      }});

      marketRows.forEach((row) => {{
        const market = row.dataset.market || "";
        row.style.display = currentMarket === "ALL" || market === currentMarket ? "" : "none";
      }});

      entryRows.forEach((row) => {{
        const market = row.dataset.market || "";
        const ticker = String(row.dataset.ticker || "").toUpperCase();
        const marketMatch = currentMarket === "ALL" || market === currentMarket;
        const searchMatch = !currentSearch || ticker.includes(currentSearch);
        row.style.display = marketMatch && searchMatch ? "" : "none";
      }});

      sortEntryRows();
      renderFilterSummary();
    }}

    function renderFilterSummary() {{
      if (!filterSummaryBar) {{
        return;
      }}
      const chips = [];
      if (currentMarket !== "ALL") {{
        const activeMarketButton = marketFilterButtons.find((button) => button.dataset.marketFilter === currentMarket);
        chips.push("시장 " + (activeMarketButton ? activeMarketButton.textContent : currentMarket));
      }}
      if (currentSearch) {{
        chips.push("검색 " + currentSearch);
      }}
      if (currentSort !== "ticker") {{
        const label = currentSort === "market" ? "시장순" : "시총순";
        chips.push("정렬 " + label);
      }}
      if (!chips.length) {{
        chips.push("기본 보기");
      }}
      filterSummaryBar.innerHTML = chips.map((text) => '<span class="summary-chip">' + text + "</span>").join("");
    }}

    marketFilterButtons.forEach((button) => {{
      button.addEventListener("click", () => {{
        currentMarket = button.dataset.marketFilter || "ALL";
        saveStored(MARKET_FILTER_KEY, currentMarket);
        applyControls();
      }});
    }});

    if (searchInput) {{
      searchInput.addEventListener("input", () => {{
        currentSearch = String(searchInput.value || "").trim().toUpperCase();
        saveStored(SEARCH_KEY, String(searchInput.value || "").trim());
        applyControls();
      }});
    }}

    if (sortSelect) {{
      sortSelect.addEventListener("change", () => {{
        currentSort = String(sortSelect.value || "ticker");
        saveStored(SORT_KEY, currentSort);
        applyControls();
      }});
    }}

    if (resetButton) {{
      resetButton.addEventListener("click", () => {{
        currentMarket = "ALL";
        currentSearch = "";
        currentSort = "ticker";
        clearStored();
        if (searchInput) {{
          searchInput.value = "";
        }}
        if (sortSelect) {{
          sortSelect.value = "ticker";
        }}
        applyControls();
      }});
    }}

    const allowedMarkets = new Set(["ALL", {", ".join(repr(m) for m in enabled_markets)}]);
    const storedMarket = loadStored(MARKET_FILTER_KEY, "ALL");
    currentMarket = allowedMarkets.has(storedMarket) ? storedMarket : "ALL";
    currentSearch = loadStored(SEARCH_KEY, "").trim().toUpperCase();
    currentSort = ["ticker", "market", "market_cap"].includes(loadStored(SORT_KEY, "ticker"))
      ? loadStored(SORT_KEY, "ticker")
      : "ticker";

    if (searchInput) {{
      searchInput.value = loadStored(SEARCH_KEY, "");
    }}
    if (sortSelect) {{
      sortSelect.value = currentSort;
    }}
    applyControls();
  </script>
</body>
</html>"""


def write_report(path: Path, html_text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sia_full_universe_report")
    parser.add_argument("--snapshot", default=DEFAULT_FULL_UNIVERSE_SNAPSHOT_PATH)
    parser.add_argument("--out", default=DEFAULT_FULL_UNIVERSE_REPORT_PATH)
    args = parser.parse_args(argv)

    snapshot_path = Path(args.snapshot).expanduser()
    report_path = Path(args.out).expanduser()

    if not snapshot_path.exists():
        write_report(
            report_path,
            render_empty_report_html(
                "전종목 유니버스 리포트",
                "full universe 스냅샷이 아직 없습니다. 먼저 full universe refresh를 실행하세요.",
            ),
        )
        print(report_path)
        return 0

    snapshot = load_snapshot(snapshot_path)
    write_report(report_path, render_report(snapshot))
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
