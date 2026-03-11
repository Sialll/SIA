# SIA Current Status - 2026-03-11

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

The sales-facing dashboard is now split into four tabs:

1. `메인`
   - current intraday visibility
   - current signal cards
   - latest summary and help
2. `종목`
   - last stored snapshot score for the active watchlist
   - visible even when the market is closed
   - recent ticker change history
   - missing ticker reasons
3. `백테스트`
   - readiness / quality / factor interpretation surface
   - current sales readiness summary
4. `설정`
   - ticker and market configuration
   - run / refresh actions

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

As of 2026-03-11 Asia/Seoul:

- `us-open-check-report.html`
  - watchlist count: `28`
  - visible in main: `28`
  - coverage: `100.0%`
  - verdict: `정상`
- `data-quality-report.html`
  - verdict: `양호`
  - strict ready ratio: `93.64%`
  - mock ratio: `0.00%`
  - `signal_source` missing: `0`
- `backtest-readiness-report.html`
  - verdict: `준비 완료`
- `factor-breakdown-report.html`
  - current strongest combination:
    - `차트 / +1 tick / 평균 엣지 0.32% / 상관계수 0.177`

Important limitation:

- packaging is not fully production-ready yet
- macOS direct distribution packaging is ready:
  - `SIA.app`
  - `SIA-macOS.zip`
  - `SIA-macOS.zip.sha256`
  - `SECURITY.txt`
- Apple Developer signing/notarization is not required for the current plan
- Windows staging is ready, but runtime validation is still pending in a PowerShell-capable environment

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

1. Keep macOS direct distribution package current
2. Run Windows build/runtime verification in a real PowerShell environment
3. Keep packaging docs aligned:
   - `docs/sales-packaging-flow.md`
   - `docs/macos-signing-notarization-checklist.md`
   - `docs/windows-packaging-validation-checklist.md`
