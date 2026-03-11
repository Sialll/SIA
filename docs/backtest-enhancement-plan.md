# SIA 백테스트 보완 설계안

기준일: 2026-03-11

이 문서는 현재 SIA 백테스트를 `운영 리포트 수준`에서 `판매용 설명이 가능한 수준`으로 올리기 위한 보완 계획을 정리한다.

## 1. 현재 판단

현재 상태는 다음까지는 확보됐다.

- `data-quality-report.html` 판정 `양호`
- `backtest-readiness-report.html` 판정 `준비 완료`
- `mock 제외 + source 정합성` 기준 유지
- 운영용 가격/포지션/factor 리포트는 이미 동작

하지만 아직 판매용 설명력은 부족하다.

핵심 부족점:

1. `tick 기반 보유기간`만으로는 일반 사용자 설명이 약함
2. `프리장 / 정규장 / KR 본장` 성과가 분리되지 않음
3. 수수료/슬리피지가 반영되지 않음
4. 일부 종목 편향 여부를 리포트에서 바로 보기가 어려움
5. walk-forward 검증이 없음

## 2. 목표

판매용 기준에서 아래 질문에 답할 수 있어야 한다.

- 이 점수는 `언제까지` 유효한가
- 프리장과 본장에서 결과가 같은가
- 비용을 넣어도 여전히 의미가 있는가
- 특정 몇 종목 덕분에 좋아 보이는 것은 아닌가
- 과거 전체가 아니라 `구간별`로도 일관성이 있는가

## 3. 구현 원칙

- notifier core는 건드리지 않는다.
- `strict = mock 제외 + source 정합성` 기준 유지
- 기존 리포트는 유지하고, 보완 리포트를 추가하거나 옵션을 확장하는 방식으로 간다.
- 파일 변경은 단계별로 작게 쪼갠다.

## 4. 단계별 보완 계획

### 단계 1. 시간 기반 보유기간 추가

목적:

- `+1/+3/+5 tick` 외에 사람이 이해하기 쉬운 기준을 추가한다.

추가할 기준:

- `30분`
- `1시간`
- `당일 종가`
- `익일 시가`

권장 파일 단위:

- 새 파일:
  - `src/sia/backtest_horizons.py`
- 수정 파일:
  - `src/sia/price_backtest_report.py`
  - `src/sia/position_backtest_report.py`
  - `src/sia/report_metrics.py`

구현 방향:

- 현재 tick 순번 기반 horizon 계산을 공통 함수로 분리
- `ts` 기준으로 목표 시점을 계산하고, 해당 시점 이후 첫 price tick을 찾는 방식 추가
- tick 기반 결과와 시간 기반 결과를 동시에 보여준다.

완료 기준:

- 가격 백테스트와 포지션 백테스트에 `tick 기반 / 시간 기반`이 같이 표시됨
- `당일 종가`, `익일 시가` 결과가 리포트에 별도 행으로 나옴

### 단계 2. 세션 분리

목적:

- `US 프리장`, `US 정규장`, `KR 본장`을 분리해서 읽을 수 있게 한다.

권장 파일 단위:

- 새 파일:
  - `src/sia/backtest_sessions.py`
- 수정 파일:
  - `src/sia/market_runtime.py`
  - `src/sia/price_backtest_report.py`
  - `src/sia/position_backtest_report.py`
  - `src/sia/factor_breakdown_report.py`

구현 방향:

- 각 snapshot / price tick에 대해 세션 라벨 계산
  - `US_PREMARKET`
  - `US_REGULAR`
  - `US_AFTERHOURS`
  - `KR_REGULAR`
- 리포트에서 세션별 성과 표를 별도 출력

완료 기준:

- 프리장 성과와 정규장 성과를 구분해 볼 수 있음
- KR/US 혼합 운영에서도 세션별 차이를 설명 가능

### 단계 3. 슬리피지 / 수수료 모델

목적:

- 지나치게 깨끗한 수익률을 줄이고 판매용 현실성을 높인다.

권장 파일 단위:

- 수정 파일:
  - `src/sia/report_metrics.py`
  - `src/sia/price_backtest_report.py`
  - `src/sia/position_backtest_report.py`

권장 설정값:

- `SIA_BACKTEST_SLIPPAGE_BPS`
- `SIA_BACKTEST_FEE_BPS`

구현 방향:

- 진입/청산 양쪽에 비용 적용
- 가격 백테스트와 포지션 백테스트에서 `gross / net` 둘 다 표시

완료 기준:

- 리포트에 `비용 반영 전/후` 수익률이 같이 보임
- 판매용 문서에서 `비용 반영 기준`을 명확히 설명 가능

### 단계 4. 종목 편향 진단

목적:

- 몇 개 종목이 전체 성과를 과도하게 끌고 가는지 바로 볼 수 있게 한다.

권장 파일 단위:

- 새 파일:
  - `src/sia/backtest_concentration_report.py`
- 수정 파일:
  - `src/sia/factor_breakdown_report.py`
  - `src/sia/research_report.py`

구현 방향:

- `종목별 trade 수`
- `종목별 누적 기여`
- `상위 3종목 제외 성과`
- `종목별 평균 edge`

완료 기준:

- 특정 종목 편향 여부를 리포트에서 바로 읽을 수 있음
- 판매 설명에서 “소수 종목 착시” 여부를 방어 가능

### 단계 5. walk-forward 검증

목적:

- 과거 전체 평균이 아니라 구간별 일관성을 본다.

권장 파일 단위:

- 새 파일:
  - `src/sia/walkforward_report.py`
  - `scripts/_internal/sia-walkforward-report.command`
- 수정 파일:
  - `src/sia/report_metrics.py`
  - `scripts/_internal/sia-report-hub.command`

구현 방향:

- 기간을 월/분기 단위로 나눔
- 각 구간별:
  - coverage
  - edge
  - hit rate
  - net return
  - drawdown
  를 출력

완료 기준:

- `좋은 달만 좋은 전략`인지 아닌지 구분 가능
- 판매용에서 “구간별 안정성”을 보여줄 수 있음

## 5. 권장 구현 순서

1. `시간 기반 보유기간`
2. `세션 분리`
3. `슬리피지 / 수수료`
4. `종목 편향 진단`
5. `walk-forward`

이 순서가 맞는 이유:

- 1~3단계가 결과 숫자의 의미를 먼저 바꾼다.
- 4~5단계는 그 뒤에 해석 신뢰도를 올린다.

## 6. 단계별 검증 기준

### 1단계 통과 기준

- 시간 기반 horizon이 실제로 리포트에 표시
- tick 기반 결과와 동시에 존재
- 기존 리포트는 깨지지 않음

### 2단계 통과 기준

- 프리장/정규장/KR 본장 성과가 분리 표기
- `market_runtime` 세션 정책과 일관됨

### 3단계 통과 기준

- gross / net 둘 다 표시
- 기본 비용값이 env로 조정 가능

### 4단계 통과 기준

- 상위 종목 편향 여부를 한눈에 판단 가능

### 5단계 통과 기준

- 월/분기별 성과 분포를 보고 전략 일관성 판단 가능

## 7. 판매용으로 의미가 커지는 시점

아래가 갖춰지면 백테스트는 판매용 설명에 쓸 수 있는 수준에 가까워진다.

- 시간 기반 보유기간 존재
- 세션 분리 존재
- 비용 반영 결과 존재
- 종목 편향 진단 가능
- walk-forward 구간별 일관성 확인 가능

## 8. 당장 다음 구현 추천

다음 실제 구현은 `단계 1 + 단계 2`를 묶어서 하는 것이 가장 효율적이다.

이유:

- 사용자 설명력이 바로 좋아진다.
- 프리장 유지 전략과도 직접 연결된다.
- 이후 비용 모델을 얹어도 구조가 덜 흔들린다.
