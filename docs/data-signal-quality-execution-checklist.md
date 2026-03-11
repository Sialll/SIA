# SIA 데이터 / 신호 품질 실행 체크리스트

기준일: 2026-03-08

이 문서는 실제 운영자가 장중 데이터 품질과 신호 품질을 점검할 때 그대로 따라갈 수 있는 실행 체크리스트다.

## 1. 목적

- `메인 반영률`이 정상인지 확인한다.
- `mock 제외 + source 정합성` 상태에서 데이터가 해석 가능한지 확인한다.
- readiness가 낮은데 수익률 숫자만 보고 오판하는 일을 막는다.

## 2. 점검 순서

항상 아래 순서로 본다.

1. `us-open-check-report.html`
2. `data-quality-report.html`
3. `backtest-readiness-report.html`
4. `factor-breakdown-report.html`

## 3. 파일 위치

- 미국장 반영률:
  - `~/Library/Caches/sia-notifier/us-open-check-report.html`
- 데이터 품질:
  - `~/Library/Caches/sia-notifier/data-quality-report.html`
- 준비도:
  - `~/Library/Caches/sia-notifier/backtest-readiness-report.html`
- 점수 품질:
  - `~/Library/Caches/sia-notifier/factor-breakdown-report.html`

## 4. 실행 전 조건

- 미국장 시간인지 확인
- watchlist가 최신인지 확인
- 텔레그램 연결 상태가 살아 있는지 확인
- 메인이 최근에 재생성됐는지 확인

## 5. 1단계: 미국장 반영률

### 보는 값

- 관심 종목 수
- 메인 반영 수
- 반영률
- 누락 종목
- 누락 사유

### 통과 기준

- 장중 기준 `100%`가 목표
- 장 직후에는 짧게 지연될 수 있으나, 이유가 `시장 휴장`이면 정상

### 실패 시 원인 분류

- 시장 휴장
- 가격 데이터 없음
- 신호 스냅샷 미생성
- source 불일치
- 메인 반영 지연

### 대응

- `시장 휴장`: 수정하지 않음
- `가격 데이터 없음`: 데이터 경로 점검
- `신호 스냅샷 미생성`: 엔진 실행 경로 점검
- `source 불일치`: strict/source 정합성 경로 점검
- `메인 반영 지연`: dashboard 재생성 경로 점검

## 6. 2단계: 데이터 품질

### 보는 값

- snapshot 수
- price_ticks 수
- strict 가능률
- mock 비중
- signal_source 누락

### 현재 기본 기준

- mock 비중 경고 기준: `50%`
- strict 가능률 최소 기준: `35%`
- signal_source 누락: `0` 목표

### 통과 기준

- `strict 가능률`이 기준 이상
- `mock 비중`이 기준 이하
- `signal_source 누락`이 없거나 매우 낮음

### 실패 시 해석

- `mock 비중`이 높으면 아직 실전 데이터보다 테스트 데이터 편향
- `strict 가능률`이 낮으면 백테스트 숫자 해석을 보류
- `signal_source 누락`이 있으면 source 추적부터 복구

## 7. 3단계: readiness

### 보는 값

- 판정
- 신호 수
- 정합 수
- 준비 구간 수
- 가격 horizon별 표본 수
- 포지션 hold별 trade 수

### 해석 규칙

- `부분 준비` 이하는 수익률 숫자를 강하게 해석하지 않음
- `준비 구간 수`가 늘기 전까지는 전략 우열 판단을 보수적으로 함

### 우선 확인 포인트

- `1 tick`만 준비 완료인지
- `3 tick`, `5 tick`, `10 tick`이 얼마나 비어 있는지
- 준비 구간 수가 1에 머무는지 늘어나는지

## 8. 4단계: 점수 품질

### 보는 값

- 현재 가장 강한 조합
- 평균 엣지
- 상관계수
- factor별 표본 수

### 해석 규칙

- factor 리포트는 `품질 진단용`
- readiness가 낮으면 factor 상관계수를 마케팅 숫자로 쓰지 않음
- 일부 종목 편향인지 반드시 확인

## 9. 장중 점검 루틴

### 미국장 개장 직후

- `us-open-check-report.html`
- 목적: watchlist 반영률 확인

### 장중 중반

- `data-quality-report.html`
- `backtest-readiness-report.html`
- 목적: non-mock 표본 누적 상태 확인

### 장 후반 또는 마감 전

- `factor-breakdown-report.html`
- 목적: factor 방향성이 특정 종목 편향인지 확인

## 10. 체크 결과 기록 형식

아래 형식으로 남긴다.

### 예시

- 날짜:
- 시장 상태:
- 관심 종목 수:
- 메인 반영 수:
- 반영률:
- 데이터 품질 판정:
- readiness 판정:
- strongest factor:
- 현재 병목:
- 조치 필요 여부:

## 11. 조치 우선순위

1. 시장 휴장 여부 확인
2. source 정합성 확인
3. signal_source 누락 확인
4. non-mock 표본 수 확인
5. readiness 해석
6. factor 해석

## 12. 하지 말아야 할 것

- 시장이 닫혀 있는데 반영률 낮다고 버그로 확정하는 일
- readiness가 낮은데 factor 결과만 보고 전략 판단하는 일
- `mock 포함` 결과를 `strict 결과`처럼 해석하는 일
- 표본 부족 상태에서 수익률 숫자를 판매 문구처럼 쓰는 일

