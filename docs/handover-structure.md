# SIA 인수인계 구조 문서

## 1. 현재 제품 정의

- 현재 제품은 `자동매매`가 아니라 `Telegram 알림 + 리서치/백테스트 도구`입니다.
- 주문 API는 제거됐고, 운영 경로는 `무료 시세/뉴스 + 로컬 저장 + 분석 + 알림`입니다.
- 현재 목표는 `AI 투자 리서치 엔진`의 안정적인 로컬 운영입니다.

## 2. 현재 실행 흐름

```text
price/news 수집
-> sqlite 저장
-> factor 계산
-> signal 생성
-> telegram 알림
-> dashboard_snapshots 저장
-> dashboard / backtest / readiness / factor / research 리포트 생성
```

## 3. 핵심 코드 구조

### 3.1 notifier 계층

- 메인 실행:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/trading_signal_notifier.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/trading_signal_notifier.py)
- 설정:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_config.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_config.py)
- 기본 유니버스:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/default_universe.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/default_universe.py)
- 유니버스 수집 스켈레톤:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/universe_collector.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/universe_collector.py)
- full universe collector 골격:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/full_universe_collector.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/full_universe_collector.py)
- full universe 리포트:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/full_universe_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/full_universe_report.py)
- 시장 런타임:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/market_runtime.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/market_runtime.py)
- 모델:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_models.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_models.py)
- 수집:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_collector.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_collector.py)
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/http_client.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/http_client.py)
- 저장:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_storage.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_storage.py)
- 매크로:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_macro.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_macro.py)
- 이벤트:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_events.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_events.py)
- 점수 계산:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_scoring.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_scoring.py)
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/factor_engine.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/factor_engine.py)
  - 사용자 노출 점수는 `0~100점`, 내부 계산은 정규화 점수 유지
- 전송:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_sender.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/notifier_sender.py)
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/telegram_message.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/telegram_message.py)

### 3.2 표현 계층

- 공통 용어/색상/클래스:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/presentation.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/presentation.py)
- 리포트 공통 후처리/empty 화면:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/report_common.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/report_common.py)
- 리포트 공통 CSS:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/report_theme.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/report_theme.py)
- 리포트 공통 위젯:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/report_widgets.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/report_widgets.py)
- 대시보드 렌더링:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/dashboard_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/dashboard_report.py)

### 3.3 리포트 계층

- 가격 백테스트:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/price_backtest_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/price_backtest_report.py)
- 포지션 백테스트:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/position_backtest_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/position_backtest_report.py)
- readiness:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/backtest_readiness_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/backtest_readiness_report.py)
- factor 분해:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/factor_breakdown_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/factor_breakdown_report.py)
- research:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/research_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/research_report.py)
- 데이터 품질:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/data_quality_report.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/data_quality_report.py)
- 리포트 공통 계산/파서:
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/report_metrics.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/report_metrics.py)
  - [/Users/dohyeon/Documents/Playground/SIA/src/sia/report_parser.py](/Users/dohyeon/Documents/Playground/SIA/src/sia/report_parser.py)

## 4. 주요 DB 테이블

- `dashboard_snapshots`
  - 대시보드/리포트의 핵심 입력
- `price_ticks`
  - strict 백테스트와 source 정합성 판단의 핵심
- `news_items`
  - 뉴스 원문/요약/센티먼트 저장
- `alerts`
  - telegram 전송 이력
- `event_factors`
  - 뉴스 기반 이벤트 추출 결과
- `macro_snapshots`
  - 매크로 스냅샷 저장

## 5. 운영 리포트 기준

### 5.1 운영 화면

- 대시보드:
  - `~/Library/Caches/sia-notifier/dashboard.html`
- 허브:
  - `~/Library/Caches/sia-notifier/report-hub.html`
- 마지막 실행:
  - `~/Library/Caches/sia-notifier/last-run.html`
- 유니버스 스냅샷:
  - `~/Library/Caches/sia-notifier/universe-snapshot.json`
- full universe 스냅샷:
  - `~/Library/Caches/sia-notifier/full-universe-snapshot.json`
- full universe 리포트:
  - `~/Library/Caches/sia-notifier/full-universe-report.html`

### 5.2 백테스트/품질

- readiness:
  - `~/Library/Caches/sia-notifier/backtest-readiness-report.html`
- readiness guard:
  - `~/Library/Caches/sia-notifier/readiness-guard-report.html`
- 가격 백테스트:
  - `~/Library/Caches/sia-notifier/price-backtest-report.html`
- 포지션 백테스트:
  - `~/Library/Caches/sia-notifier/position-backtest-report.html`
- factor 분해:
  - `~/Library/Caches/sia-notifier/factor-breakdown-report.html`
- research:
  - `~/Library/Caches/sia-notifier/research-report.html`
- 데이터 품질:
  - `~/Library/Caches/sia-notifier/data-quality-report.html`
- 튜닝 비교:
  - `~/Library/Caches/sia-notifier/tuning-compare.html`

## 6. 실행 스크립트

- 사용자용 더블클릭 진입점:
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Run.command](/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Run.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Dashboard.command](/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Dashboard.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Reports.command](/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Reports.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Settings.command](/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Settings.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Tickers.command](/Users/dohyeon/Documents/Playground/SIA/scripts/SIA-Market-Tickers.command)
- 내부 운영 스크립트:
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-notifier-launch.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-notifier-launch.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-dashboard.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-dashboard.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-report-hub.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-report-hub.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-universe-refresh.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-universe-refresh.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-market-settings.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-market-settings.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-market-tickers.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-market-tickers.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-backtest-readiness.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-backtest-readiness.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-price-backtest.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-price-backtest.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-position-backtest.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-position-backtest.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-factor-breakdown.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-factor-breakdown.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-research-report.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-research-report.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-data-quality.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-data-quality.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-backtest-refresh.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-backtest-refresh.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-notifier-launchd.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-notifier-launchd.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-backtest-refresh-launchd.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-backtest-refresh-launchd.command)
  - [/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-ready-buckets-launchd.command](/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-ready-buckets-launchd.command)

## 7. launchd 자동화

- 알림 엔진:
  - `com.sia.trading-signal-notifier`
- 야간 백테스트 누적:
  - `com.sia.backtest-refresh-nightly`
- readiness guard:
  - `com.sia.ready-buckets-guard`

설치/상태 확인 스크립트:

- 알림 엔진:
  - `./scripts/_internal/sia-notifier-launchd.command install balanced`
  - `./scripts/_internal/sia-notifier-launchd.command status`
- 야간 백테스트 누적:
  - `./scripts/_internal/sia-backtest-refresh-launchd.command install`
  - `./scripts/_internal/sia-backtest-refresh-launchd.command status`
- readiness guard:
  - `./scripts/_internal/sia-ready-buckets-launchd.command install`
  - `./scripts/_internal/sia-ready-buckets-launchd.command status`

대시보드 `시스템 상태` 패널에서도 현재 상태를 직접 볼 수 있습니다.

## 8. 현재 운영 철학

- 실전 주문은 하지 않는다.
- Telegram 알림과 리서치 판단을 분리한다.
- 뉴스는 연중무휴로 수집한다.
- 가격/신호는 활성 시장 + 장중일 때만 수집한다.
- 기본 활성 시장은 `US`이며 `KR/EU/JP`는 사용자가 명시적으로 켜야 한다.
- 기본 universe는 `시가총액 10억달러(약 1.4조원) 이상 대표 종목 seed set`이고, 사용자 티커는 여기에 추가된다.
- `SIA_INCLUDE_DEFAULT_UNIVERSE=0`이면 기본 universe를 끌 수 있다.
- full universe 확장은 아직 스켈레톤 단계이며 `full_universe_collector.py`가 provider 확장 지점이다.
- `VIX / 10Y / DXY / WTI / CPI`는 매크로 위험 점수에 반영된다.
- strict 백테스트는 `mock 제외 + source 정합성`을 강제한다.
- readiness가 낮으면 수익률보다 표본 수를 먼저 본다.
- 데이터 품질 리포트를 먼저 보고, 그 다음 readiness/backtest/factor를 본다.

## 9. 지금 수정할 때 안전한 순서

1. 표현 수정:
   - `presentation.py`
   - `report_theme.py`
   - `report_widgets.py`
2. 리포트 수정:
   - 각 `*_report.py`
3. 데이터/전략 수정:
   - `notifier_*`
   - `factor_engine.py`
4. 운영 스크립트 수정:
   - `scripts/SIA-*.command`
   - `scripts/_internal/*.command`

## 10. 현재 가장 중요한 리스크

- mock 비중이 다시 높아지면 strict 리포트 해석이 무너집니다.
- `signal_source`가 비면 source 정합성 추적이 무너집니다.
- 무료 소스 특성상 시장 외 시간에는 표본 누적이 느립니다.
- readiness가 충분히 올라오기 전에는 Sharpe/MDD 숫자를 과신하면 안 됩니다.

## 11. 다음 우선순위

1. `data_quality_report`를 기준으로 mock/non-mock 비율 관리
2. `readiness`를 `READY` 이상까지 올릴 표본 누적
3. 그 다음에만 factor/strategy 튜닝
