# SIA Scope-Guard Skill (운영 가드)

이 스킬은 SIA 프로젝트에서 방향성이 흔들리지 않도록 최소 규칙 집합을 제공합니다.

## 1) 프로젝트 목적 불변성
- 텔레그램 알림형 신호 보조 도구로 유지.
- 자동 주문/자동매매 실행(코드 생성, API 주문 호출) 방향은 금지.
- 시세 기준은 종가 기반 중심, 운영은 텔레그램 알림 중심.

## 2) 입력/출력 경계
- Issue 템플릿 핵심 섹션은 `Goal`, `Requirements`, `Constraints (must obey)`, `Acceptance criteria`만 사용.
- 허용되지 않는 변경 패턴 (`Work type`, `Exceptions (only if needed)`, `Exception reason`)은 가드 예외로만 처리.
- 핵심 섹션 누락 또는 템플릿 바깥 섹션 혼입 시 `parse-issue --strict`가 차단해야 함.

## 3) 변경 제약
- 기본 원칙: PR 1개 파일 원칙 준수(필요 시 예외 라벨/근거 사용).
- 범위 밖 파일 경로 변경/절대경로/상위경로 사용은 금지.
- `core` 또는 핵심 의사결정 로직 경계 변경 시 별도 승인 없으면 금지로 간주.

## 4) 실수 방지 체크리스트 (자동 적용 가드)
- `python -m src.sia.cli parse-issue --file <path> --strict`
  - 자동매매/자동주문 키워드 탐지
  - 템플릿 섹션 누락·비표준 섹션 탐지
  - 텔레그램/알림/수집 주기/데이터 소스/운영 키워드 근거 확인
- `python -m src.sia.cli check-pr --files <paths>`
  - one-file rule + Python 문법 가드 + 범위 가드
- 위반이 있으면 PR/작업 정지 후 메시지 보강 후 재작업

## 5) 실패 코드(Strict)
- BLOCKED: `SCOPE-AUTO-ORDER`, `SCOPE-TEMPLATE-BLANK`, `SCOPE-UNKNOWN-SECTIONS` (즉시 중단)
- CRITICAL: `SCOPE-MISSING-TELEGRAM`, `SCOPE-SCHEDULE-MISSING`, `SCOPE-DATA-MISSING`, `SCOPE-OPS-MISSING`, `SCOPE-TEMPLATE-MISSING-SECTION`, `SCOPE-MISSING-TITLE`
- WARNING: `SCOPE-WEAK-SIGNAL`, `SCOPE-SCHEDULE-SOFT`, `SCOPE-DATA-SOFT`, `SCOPE-OPS-SOFT`, `SCOPE-EMPTY-SECTIONS`
- CI 로그는 `STRICT_GUARD_REPORT=` 및 `STRICT_GUARD_EVENTS=` 라인에서 위 코드를 확인한다.

## 6) 우선순위 대응 가이드
- BLOCKED 우선 처리: 1) 블록 원인 제거/명시, 2) 중복되지 않은 핵심 섹션 복원 후 재실행.
- CRITICAL 후속: 3) 템플릿 필수 항목(Goal/Requirements/Constraints/Acceptance criteria) 채움, 4) 텔레그램/수집 주기/데이터 소스/운영 항목 보강.
- WARNING 보완: 5) 시그널 근거(지표/뉴스 기준)와 완화 항목 문구 정리.
- 반복 이슈 방지 체크: 실패 코드 3개 이상 동시 발생 시 `task.yml` 전체 섹션을 한번에 정비 후 재요청.

## 7) 실패 코드별 수정 템플릿

### BLOCKED
- `SCOPE-AUTO-ORDER`
  - 제거/수정 텍스트 예시:
    - `- 자동 주문 실행은 사용하지 않으며 Telegram 알림 발송만 구현한다.`
  - 입력(Requirements): `- 프로젝트 범위: 텔레그램 알림만, 자동 주문 미포함`

- `SCOPE-TEMPLATE-BLANK`
  - 최소 섹션 템플릿(필수 항목) 예시:
    - `## Goal`
    - `- ...`
    - `## Requirements`
    - `- ...`
    - `- 텔레그램 알림 발송 경로: ...`
    - `## Constraints (must obey)`
    - `- ...`
    - `## Acceptance criteria`
    - `- [ ] ...`

- `SCOPE-UNKNOWN-SECTIONS`
  - 허용 섹션만 남기고 표준화:
    - 제거 대상: `Work type`, `Exceptions (only if needed)` 등
    - 남겨야 할 라벨: `Goal`, `Requirements`, `Constraints (must obey)`, `Acceptance criteria`

### CRITICAL
- `SCOPE-MISSING-TELEGRAM`
  - 보강 예시:
    - `- Telegram 메시지 포맷: 티커, 시그널, 근거, 수집시간을 포함`
    - `- 텔레그램 알림 실패 시 대체 로그 저장`

- `SCOPE-SCHEDULE-MISSING`
  - 보강 예시:
    - `- 수집 주기: 15분`
    - `- 실행 주기: 매 15분 정각 배치`

- `SCOPE-DATA-MISSING`
  - 보강 예시:
    - `- 데이터 소스: Finnhub(가격), Marketaux(뉴스)`
    - `- 데이터 처리: 종가 기준으로 신호 계산`

- `SCOPE-OPS-MISSING`
  - 보강 예시:
    - `- 운영 항목: 오류 로깅, 중복 방지(cooldown), 재시도 정책`
    - `- DB 스키마: price_ticks/news_items/alerts`

- `SCOPE-TEMPLATE-MISSING-SECTION`
  - 누락된 섹션 한 줄씩 보완:
    - `- Goal: 변경 의도 1문장`
    - `- Requirements: 필수 동작 3개 이상 목록`
    - `- Constraints: 금지/제약 2개 이상`
    - `- Acceptance criteria: 검증 항목 체크리스트`

- `SCOPE-MISSING-TITLE`
  - 제목 1줄 규칙:
    - `- PR/티켓 제목: [TASK] 텔레그램 알림 신호 개선 ...`

### WARNING
- `SCOPE-WEAK-SIGNAL`
  - 보강 예시:
    - `- 시그널 산출 규칙: SMA(5/20), RSI(14), 뉴스 임팩트 반영`
    - `- BUY/SELL/ HOLD의 임계치 근거 명시`

- `SCOPE-SCHEDULE-SOFT`
  - 보강 예시:
    - `- 실행 주기 15분 고정, 외부 API 지연 고려 15분 지연 기준 적용`

- `SCOPE-DATA-SOFT`
  - 보강 예시:
    - `- 종가/클로즈, 티커, 일봉 기준을 명시`

- `SCOPE-OPS-SOFT`
  - 보강 예시:
    - `- 장애 처리: 재시도 3회, 롤백/수동 개입 기준`

- `SCOPE-EMPTY-SECTIONS`
  - 보강 예시:
    - `- 각 섹션 최소 1개 항목 이상 채움(빈 항목은 제거)`

## 8) 인수인계 메모
- 핵심 목적은 텔레그램 알림 자동화이며, 시그널은 분석 근거로만 제시.
- 변경할 때마다 템플릿 섹션과 가드 메시지를 먼저 확인해 방향성 역전이 없는지 점검.

## 9) PR 재요청용 복붙 템플릿(자동 생성 조각)

아래 블록을 실패 항목 정리 후 PR 본문 맨 앞에 붙이면 됩니다.

```markdown
### Scope Guard Fix Summary
- [ ] 적용 코드: `SCOPE-XXXX` 
- [ ] 목표 방향 준수: 텔레그램 알림형(자동매매 없음)

#### 수정된 핵심 섹션
## Goal
- 텔레그램 알림형으로 신호 계산 근거(종가/뉴스) 기반 알림만 처리한다.

## Requirements
- Requirements 1: 텔레그램 알림 포맷 및 전송 경로 보강
- Requirements 2: 수집 주기(예: 15분)와 데이터 소스(Finnhub/Marketaux) 명시
- Requirements 3: 운영 항목(로그/오류 재시도/중복 방지) 명시

## Constraints (must obey)
- 자동 주문/자동매매 API 호출은 포함하지 않는다.
- 변경 범위는 템플릿 4개 핵심 섹션으로 유지한다.

## Acceptance criteria
- [ ] 템플릿 섹션 누락/비표준 섹션 없이 Goal/Requirements/Constraints (must obey)/Acceptance criteria 구성 완료
- [ ] `python -m src.sia.cli parse-issue --file /tmp/pr-body.md --strict` 또는 PR 본문 텍스트 기준으로 BLOCKED/CRITICAL 미발생 확인
- [ ] 텔레그램 알림 키워드, 수집 주기, 가격/뉴스 소스, 운영 규칙 항목이 텍스트에 존재
- [ ] 필요 시 PR 코멘트에 적용한 SCOPE 코드 반영 (`SCOPE-*`)

### 이번 수정에서 수정한 가드 코드
- `SCOPE-AUTO-ORDER`: ...
- `SCOPE-TEMPLATE-MISSING-SECTION`: ...
```

```bash
# 빠른 반영용(수동 편집용)
cat <<'EOF' > /tmp/guard-fix-template.md
### Scope Guard Fix Summary
- [ ] 적용 코드: `SCOPE-XXXX`
- [ ] 목표 방향 준수: 텔레그램 알림형(자동매매 없음)

#### 수정된 핵심 섹션
## Goal
- 텔레그램 알림형으로 신호 계산 근거(종가/뉴스) 기반 알림만 처리한다.

## Requirements
- Requirements 1: 텔레그램 알림 포맷 및 전송 경로 보강
- Requirements 2: 수집 주기(예: 15분)와 데이터 소스(Finnhub/Marketaux) 명시
- Requirements 3: 운영 항목(로그/오류 재시도/중복 방지) 명시

## Constraints (must obey)
- 자동 주문/자동매매 API 호출은 포함하지 않는다.
- 변경 범위는 템플릿 4개 핵심 섹션으로 유지한다.

## Acceptance criteria
- [ ] 템플릿 섹션 누락/비표준 섹션 없이 Goal/Requirements/Constraints (must obey)/Acceptance criteria 구성 완료
- [ ] 텔레그램 알림 키워드, 수집 주기, 가격/뉴스 소스, 운영 규칙 항목이 텍스트에 존재
- [ ] PR 코멘트에 적용한 SCOPE 코드 반영 (`SCOPE-*`)
EOF
```

## 10) PR 본문 자동 반영 스킬(권장)

오류 수정 반복 시, 템플릿을 수동으로 붙이는 대신 아래 스크립트를 사용하세요.

```bash
./scripts/gh-apply-scope-fix-template.sh --pr <PR번호>
```

또는 여러 건 일괄 정리를 할 때는 아래를 사용해 붙여넣기용 블록만 추출하세요.

```bash
./scripts/scope-guard-batch.sh --range 1 8 --summary --fix-drafts-only --out-auto
```

이 모드는 PR별 로그를 출력하지 않고, 복붙 가능한 템플릿 초안 블록만 생성합니다.

코멘트용으로 바로 붙이려면 compact 모드를 사용하세요.

```bash
./scripts/scope-guard-batch.sh --range 1 8 --summary --fix-drafts-compact --out-auto
```

한 줄로 요약해서 붙이려면 ultra 모드를 사용하세요.

```bash
./scripts/scope-guard-batch.sh --range 1 8 --summary --fix-drafts-ultra --out-auto
```

한 줄 더 짧게(tiny) 붙이려면 ultra-tight 모드를 사용하세요.

```bash
./scripts/scope-guard-batch.sh --range 1 8 --summary --fix-drafts-ultra-tight --out-auto
```

이 모드는 제목이 24자 이내로 잘리고, `tg`, `sch` 같은 축약 태그로 최소폭을 맞춥니다.

이 모드는 PR당 3~4줄 최소본으로 정리되어 빠르게 붙여넣을 수 있습니다.

동작 방식:

- 현재 PR 본문을 조회하고, 템플릿 파일을 맨 앞에 붙입니다.
- 기존 본문이 있으면 그대로 보존하되, 상단에 `### Scope Guard Fix Summary` 블록이 있으면 중복 삽입을 막습니다.
- `/tmp/guard-summary.json`에서 이벤트를 읽어 `SCOPE-*` 코드를 자동 채웁니다.
- `--dry-run` 옵션으로 변경 결과를 미리 볼 수 있습니다.

실행 예시(요약 코드 자동 채움):

```bash
./scripts/gh-apply-scope-fix-template.sh --pr 123 --codes "SCOPE-MISSING-TITLE,SCOPE-OPS-SOFT"
```

실패 복구용 1줄 루틴:

```bash
python -m src.sia.cli parse-issue --file /tmp/pr-body.md --strict || true
./scripts/gh-apply-scope-fix-template.sh --pr 123 --dry-run
./scripts/gh-apply-scope-fix-template.sh --pr 123
```

권장 스텝:

- [ ] 템플릿 중복 삽입 방지 여부 확인
- [ ] `--dry-run`으로 최종 본문 검증
- [ ] 업데이트 후 `./scripts/README.md`에 남긴 실행 로그 보관

## 11) PR 사전 점검 스킬(권장)

작업 시작 전/후에 아래를 실행하면 오류 전파를 줄일 수 있습니다.

```bash
./scripts/scope-guard-pr-preflight.sh --pr <PR번호>
./scripts/scope-guard-pr-preflight.sh --pr <PR번호> --apply-template
./scripts/scope-guard-pr-preflight.sh --body-file /tmp/pr-body.md --no-check-pr
```

권장 순서:

- `parse-issue --strict` 우선 통과를 맞춘다.
- 실패 시 템플릿 자동 삽입으로 PR 본문을 보강한다.
- `--no-check-pr`은 임시 PR 텍스트 검증용일 때만 사용하고 기본은 켠다.

## 12) PR 통합 게이트(추천 실행 스크립트)

다음 1줄 플로우로 “오류가 반복적으로 쌓이는” 상황을 줄입니다.

```bash
./scripts/scope-guard-gate.sh --pr <PR번호>
./scripts/scope-guard-gate.sh --pr <PR번호> --apply-template
./scripts/scope-guard-gate.sh --body-file /tmp/pr-body.md --no-check-pr
```

권장 규칙:

- 템플릿 자동 보강은 `parse-issue`가 실패한 경우만 실행(체크리스트/구조적 규칙 위반은 직접 수정).
- 기본은 “1회 실패 시 템플릿 적용 + 1회 재검증”으로 고정.
- 템플릿 적용 전엔 `--dry-run-template`으로 최종 본문만 확인 후 실제 수정.
- `--pr` 미지정 시 현재 브랜치 PR을 자동 탐지(단, body-file 모드 제외).
- `check-pr` 기본 비교 기준은 `origin/main`이며, 필요 시 `--base` 지정.

## 13) 오류 방지 실행 스킬(실무 루틴)

실무 작업 시작/종료 시 아래 순서를 기본 루틴으로 고정:

- 시작(1회): `./scripts/scope-guard-pr-preflight.sh --pr <PR번호>`
- 변경 후 검증(권장): `./scripts/scope-guard-gate.sh --pr <PR번호> --apply-template --dry-run-template`
- 최종 반영(필요 시): `./scripts/scope-guard-gate.sh --pr <PR번호> --apply-template`

운영 주의:

- PR 본문/체크 실패를 숨기지 않도록 `--body-file` 모드에서는 템플릿 자동 적용이 동작하지 않음을 가정한다.
- `--pr`와 `--body-file`을 동시에 쓰면 오류로 즉시 중단한다.
- 스크립트는 기본을 최소 변경(최대 1회 템플릿 재적용)으로 둔다.

## 14) 실제 운영 가드(시스템 안정성)

- 방향성: 텔레그램 알림형만 유지, 자동 주문/체결 코드는 추가하지 않는다.
- 데이터 소스 정책: Finnhub 연속 실패가 누적될 때는 다음 실행에서 Yahoo로 폴백을 먼저 시도한다.
- 감시 포인트: 실패 이벤트(`alerts`의 source/event/ok 로그 포맷)를 통해 원인 추적이 가능해야 한다.
- 변경 규칙: 핵심 목적 변경이 생기면 `README.md` 인수인계 항목을 먼저 갱신한다.
