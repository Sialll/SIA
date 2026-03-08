# SIA Current Status - 2026-03-08

## Scope

- Product position: Telegram notifier + local research/backtest tool
- Not auto-trading
- Keep Telegram as a default feature
- Keep strict backtest rule: mock excluded + source alignment required

## What is stable now

### User-facing entry points

- `scripts/SIA.command`
- `scripts/SIA-Run.command`
- `scripts/SIA-Dashboard.command`
- `scripts/SIA-Reports.command`
- `scripts/SIA-Market-Settings.command`
- `scripts/SIA-Market-Tickers.command`

### Main dashboard structure

The main dashboard is now split into three tabs:

1. `실시간`
   - current intraday visibility
   - current signal cards
   - recent reflected snapshots
2. `오프라인 점수`
   - last stored snapshot score for the active watchlist
   - visible even when the market is closed
   - recent ticker change history
   - missing ticker reasons
3. `관리자 체크`
   - report links
   - system status
   - launchd / cache / source status

### Main action panel

The main action panel is intentionally the primary user surface.

It supports:

- quick add
- quick remove
- add/remove mode toggle
- plain ticker input like `INTC`
- bulk set by market
- market example tabs
- copy example + autofill
- run notifier once
- refresh backtest bundle
- rebuild main dashboard

Quick input should be understood as:

- add mode + `INTC` -> add
- remove mode + `INTC` -> remove

Legacy text like `티커 추가 : [ ASTS ]` still works, but the preferred UX is plain ticker input plus the mode button.

## Market policy

- News collection: 24/7
- Price/signal collection: active market + market open only
- Default enabled market: `US`
- `KR`, `EU`, `JP` must be explicitly enabled by the user

Config files:

- `~/.config/sia-notifier/env`
- `~/.config/sia-notifier/market-selection.json`

## Current watchlist state

Current US watchlist:

- `AAPL`
- `MSFT`
- `NVDA`
- `AMZN`
- `GOOGL`
- `META`
- `TSLA`
- `ASTS`
- `INTC`

Current setting:

- `SIA_INCLUDE_DEFAULT_UNIVERSE=0`
- default seed universe is currently disabled for runtime watchlist

## Scoring / reporting

- User-visible scores are shown as `0-100`
- Internal normalized scoring is still preserved for engine math
- Macro inputs already wired:
  - `VIX`
  - `10Y`
  - `DXY`
  - `WTI`
  - `CPI`
- Current factor mix:
  - chart
  - macro
  - event
  - news

## Reports that matter first

Read in this order:

1. `data-quality-report.html`
2. `backtest-readiness-report.html`
3. `price-backtest-report.html`
4. `position-backtest-report.html`
5. `factor-breakdown-report.html`
6. `research-report.html`

Hub:

- `~/Library/Caches/sia-notifier/report-hub.html`

## Current operational reading

As of 2026-03-08 Asia/Seoul:

- `us-open-check-report.html`
  - watchlist count: `9`
  - visible in main: `2`
  - coverage: `22.2%`
  - reason for missing tickers: market closed
- `data-quality-report.html`
  - verdict: `주의`
  - strict ready ratio: `50.00%`
  - mock ratio: `17.65%`
  - `signal_source` missing: `0`
- `backtest-readiness-report.html`
  - verdict: `부분 준비`
  - only `1 tick` position bucket is ready
  - longer horizons still need more live non-mock samples
- `factor-breakdown-report.html`
  - current strongest combination:
    - `이벤트 / +5 tick / 평균 엣지 0.05% / 상관계수 0.614`

Important limitation:

- signal-quality interpretation is still heavily biased toward the symbols with accumulated non-mock intraday data
- do not over-read the factor report until more live samples accumulate across the expanded watchlist

## Automations currently worth keeping

- `us-open-coverage-fix`
- `signal-quality-review`

These were deduplicated and older duplicates were removed.

## Important implementation boundaries

- Do not reintroduce order execution paths
- Do not remove Telegram from the default flow
- Do not relax strict backtest semantics
- Do not silently change the default active market from `US`
- Do not merge user launchers and internal scripts

## Recommended next step for the next operator

1. Wait for the next US open
2. Check `us-open-check-report.html`
3. If coverage is not `9/9` while US market is open, fix only the exact missing path
4. Re-check:
   - `data-quality-report.html`
   - `backtest-readiness-report.html`
   - `factor-breakdown-report.html`
5. Only after enough non-mock live samples accumulate, interpret signal quality across the whole watchlist
