# SIA Product Architecture

## Purpose

SIA의 목표 제품은 단순한 알림 봇이 아니라 `AI + Macro + Quant + Event`를 결합한 투자 분석 엔진이다.

핵심 방향:

- 포지셔닝: `투자 실행 시스템`이 아니라 `투자 리서치/분석 도구`
- 배포: `Desktop / Local-first software`
- 수익화: `프로그램 판매` 우선, 이후 필요 시 SaaS 확장 검토
- 법적 원칙: 자동주문 미포함, 유료 버전에서는 직접적인 `BUY/SELL 추천`보다 분석 지표 중심 표현

## System Shape

목표 시스템 구조:

```text
Collector -> Storage -> AI Interpreter -> Factor Engine -> Dashboard -> Telegram
```

세부 흐름:

```text
뉴스 / 공시 / 가격 / 매크로 / 자금흐름
-> 로컬 DB 저장
-> AI가 텍스트를 구조화 JSON으로 해석
-> Python rule engine이 정량 점수 계산
-> Composite Score 생성
-> 웹 대시보드 / Telegram 알림
```

## Data Domains

수집 대상:

- 가격 데이터
- 뉴스
- SEC 공시
- 13F
- 내부자 거래
- 매크로 데이터

설계 원칙:

- 데이터는 먼저 로컬 DB에 저장한다.
- API 응답 원문과 정제 결과를 분리 저장한다.
- 동일 데이터를 재사용 가능하게 만들어 백테스트와 비용 통제를 동시에 잡는다.

## AI Role

AI는 `판단 엔진`이 아니라 `해석 엔진`으로 사용한다.

입력:

- 뉴스
- 공시
- 이벤트 텍스트

출력:

```json
{
  "event_type": "earnings|guidance|regulation|insider|macro",
  "sentiment": -1.0,
  "impact": "low|medium|high",
  "time_horizon": "short|medium|long",
  "confidence": 0.72
}
```

원칙:

- AI가 최종 투자판단을 직접 내리지 않는다.
- 최종 점수와 랭킹은 Python factor engine이 계산한다.

## Scoring Model

현재 목표 점수 구조:

```text
Chart Score
+ Macro Score
+ News/Event Score
= Composite Score
```

핵심 출력:

- `Composite Score`
- `Risk Level`
- `Momentum`
- `Macro Environment`

상용 버전 원칙:

- 직접적인 `BUY/SELL 추천` 문구는 최소화한다.
- 제품 설명도 `투자 분석 보조 도구` 기준으로 유지한다.

## Universe

기본 universe:

- 시가총액 `USD 1B` 이상
- 사용자 관심종목 별도 추가

의도:

- 유동성 낮은 종목 제거
- 계산량과 API 비용 제어
- 백테스트와 운영의 일관성 확보

예상 운영 규모:

- 약 `1,000 ~ 1,500` 종목

## Backtest Design

기본 원칙:

- 최근 `10년` 기준 평가
- 최근 `3년 / 5년 / 10년` 구간을 나눠 비교

핵심 지표:

- total return
- max drawdown
- sharpe ratio
- win rate
- holding period

검증 원칙:

- `lookahead bias` 금지
- 뉴스/공시/이벤트는 실제 공개 시점 이후부터만 반영
- factor parameter는 sweep 가능하지만 과최적화 경고를 남긴다

## Delivery Model

배포 전략:

- 1단계: 로컬 실행형 프로그램 판매
- 2단계: 사용자 API 키 기반 프리미엄 기능
- 3단계: 필요 시 SaaS 또는 팀 버전 검토

초기 가격 가정:

- `USD 199 ~ 299`

초기 타깃:

- 개인 투자자
- 자기 데이터를 직접 소유하고 싶은 사용자
- Telegram/대시보드 중심 운영을 원하는 사용자

## Legal Positioning

주의 지점:

- 자동주문/실행 루프는 넣지 않는다.
- 유료 제품에서 직접적인 투자 권유처럼 해석될 표현은 줄인다.
- 제품은 `분석 도구`, `리서치 엔진`, `의사결정 보조 시스템`으로 설명한다.

## Current Implementation Status

현재 저장소에 구현된 것은 최종 제품의 일부다.

현재 동작:

- 종가 기반 가격 수집
- 뉴스 연중무휴 수집
- 시장별 장중 가격/신호 수집
- 간단한 기술지표 계산
- 매크로 스냅샷 저장과 기본 매크로 점수 반영
- 이벤트 팩터 추출과 기본 이벤트 점수 반영
- Telegram 알림
- SQLite 기록
- HTML 대시보드 / readiness / backtest / factor / research / data quality 리포트

아직 없는 것:

- SEC / 13F / insider 본격 파이프라인
- 10년 일봉 기준 백테스트 프레임워크
- 상용 제품용 설치 패키징
- 대규모 universe 운영용 데이터 파이프라인
- 제품 판매용 권한/라이선스 체계

즉, 현재 코드는 `운영 가능한 알림형 MVP + 로컬 리서치 리포트` 수준이고, 장기적으로는 이 위에 `research engine` 레이어를 확장한다.

## Build Order

권장 개발 순서:

1. `Collector` 안정화: 가격/뉴스/매크로/공시 ingest 경로 정리
2. `Storage` 정규화: raw / normalized / features 테이블 분리
3. `Factor Engine`: chart, macro, event 점수 엔진 구축
4. `Backtest`: 시점 일관성 검증과 성능 리포트
5. `Dashboard`: 점수/리스크/매크로 상태 시각화
6. `Commercial Packaging`: 로컬 설치형 제품으로 묶기

## Non-Negotiables

- 자동매매 경로는 추가하지 않는다.
- 분석 근거와 점수 계산은 재현 가능해야 한다.
- 외부 AI는 해석 보조 역할로만 둔다.
- 최종 제품 설명은 `리서치 도구` 기준을 유지한다.
