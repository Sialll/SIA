### Scope Guard Fix Summary
- [ ] 적용 코드: `SCOPE-XXXX`
- [ ] 목표 방향 준수: 텔레그램 알림형(자동매매 없음)

#### 수정된 핵심 섹션
## Goal
- 텔레그램 알림형으로 신호 계산 근거(종가/뉴스) 기반 알림만 처리한다.

## Requirements
- Requirements 1: 텔레그램 알림 포맷 및 전송 경로 보강
- Requirements 2: 수집 주기(예: 15분)와 가격/뉴스 소스(Finnhub/Marketaux/Polygon) 명시
- Requirements 3: 운영 항목(로그/오류 재시도/중복 방지) 명시

## Constraints (must obey)
- 자동 주문/자동매매 API 호출은 포함하지 않는다.
- 변경 범위는 템플릿 4개 핵심 섹션으로 유지한다.

## Acceptance criteria
- [ ] 템플릿 섹션 누락/비표준 섹션 없이 Goal/Requirements/Constraints (must obey)/Acceptance criteria 구성 완료
- [ ] 텔레그램 알림 키워드, 수집 주기, 가격/뉴스 소스, 운영 규칙 항목이 텍스트에 존재
- [ ] `SCOPE-*` 코드 반영 후 PR 본문에 요약 블록이 반영됨
