# SIA Double-Click Launcher

Mac
- 더블클릭 실행 파일: `scripts/sia-notifier-launch.command`
- 동작: `trading_signal_notifier`를 1회 실행 후, 결과를 `last-run.html`로 생성해서 브라우저로 열어줍니다.
- 기본 저장소: `~/Library/Caches/sia-notifier/last-run.html`
- 동시 실행 방지 락: 스크립트는 실행 중 중복 실행을 차단합니다.

Windows
- 더블클릭 실행 파일: `scripts/sia-notifier-launch.ps1`
- 동작: `trading_signal_notifier --once` 실행 후, HTML 리포트 자동 생성/오픈
- 기본 저장소: `$env:LOCALAPPDATA\sia-notifier\last-run.html`

Mac launchd 자동실행

목적: 15분(기본) 간격으로 백그라운드 실행.

설치
```bash
./scripts/sia-notifier-launchd.command install balanced
```

제거
```bash
./scripts/sia-notifier-launchd.command uninstall
```

실행 간격 변경
```bash
SIA_POLL_MINUTES=30 ./scripts/sia-notifier-launchd.command install conservative
```

생성 위치
`~/Library/LaunchAgents/com.sia.trading-signal-notifier.plist`

로그 저장
`~/Library/Caches/sia-notifier/launchd.out.log`
`~/Library/Caches/sia-notifier/launchd.err.log`

원클릭 실행 체크리스트(권장)

- 환경 파일 생성
  - `mkdir -p ~/.config/sia-notifier`
  - `cat scripts/sia-notifier-env.example > ~/.config/sia-notifier/env`
  - `chmod 600 ~/.config/sia-notifier/env`
- 값 입력 확인
  - `TICKERS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `FINNHUB_API_KEY` 설정 확인
  - `__YOUR_*`, `dummy`, `placeholder` 형태의 가짜값은 실행이 차단됩니다.
- 더블클릭 모드 체크
  - `SIA_DRY_RUN=1 TICKERS=AAPL,MSFT SIGNAL_DB_PATH=/tmp/sia_notifier.sqlite ./scripts/sia-notifier-launch.command balanced`
- 검증 전용 실행(권장): `./scripts/sia-notifier-live-quickcheck.command balanced`
- launchd 등록(선택)
  - `./scripts/sia-notifier-launchd.command install balanced`
- 동작 확인
  - `cat ~/Library/Caches/sia-notifier/last-run.html`
  - `tail -n 40 ~/Library/Caches/sia-notifier/run.log`
- 주기 변경(원하면)
  - `SIA_POLL_MINUTES=30 ./scripts/sia-notifier-launchd.command install conservative`

주의
- 텔레그램은 기본 포함입니다. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 환경변수에 설정해야 전송합니다.
- 실행 시 `TICKERS`와 API 키가 미설정이면 기존 동작 정책에 따라 확인/오류가 기록됩니다.

### PR 사전 점검 스크립트(권장)

PR 본문 + 변경 파일을 한 번에 점검해 실패 원인을 즉시 확인합니다.

```bash
./scripts/scope-guard-pr-preflight.sh --pr <PR번호>
./scripts/scope-guard-pr-preflight.sh --pr <PR번호> --apply-template
./scripts/scope-guard-pr-preflight.sh --pr <PR번호> --no-check-pr --apply-template
./scripts/scope-guard-pr-preflight.sh --body-file /tmp/pr-body.md --no-check-pr
```

실패 시:
- `--apply-template`을 함께 쓰면 `gh-apply-scope-fix-template.sh`를 이어서 호출해 PR 본문에 Fix 템플릿을 붙입니다.

### PR 게이트 스크립트(한 번에 실행)

`parse-issue`, `check-pr`, 실패 시 `Scope Fix` 자동 보강까지 한 번에 수행하는 통합 래퍼입니다.

```bash
./scripts/scope-guard-gate.sh --pr <PR번호>
./scripts/scope-guard-gate.sh --pr <PR번호> --apply-template
./scripts/scope-guard-gate.sh --pr <PR번호> --no-check-pr --apply-template --dry-run-template
./scripts/scope-guard-gate.sh --body-file /tmp/pr-body.md --no-check-pr
```

주의:
- `--body-file` 입력은 임시 PR 텍스트 점검용이라 템플릿 자동 적용(`--apply-template`)은 동작하지 않습니다.
- `--pr`와 `--body-file`은 동시에 사용할 수 없습니다.
- 실패 재시도는 `--dry-run-template`으로 본문 미리보기를 확인한 뒤 실제 적용하세요.

실패 시:
- `--apply-template`이 활성화되어 있으면 PR 본문 텍스트가 실패한 `parse-issue --strict` 항목 기준으로 템플릿 자동 보강 후 1회 재검증합니다.
- `--dry-run-template`을 쓰면 실제 PR 수정 없이 미리보기만 보여줍니다.
- `--pr`를 생략하면 현재 브랜치와 연결된 열린 PR을 자동 탐지합니다(`body-file` 미지정 시).
- 기본 `check-pr` 기준 브랜치는 `origin/main`입니다(필요 시 `--base`로 오버라이드).

### PR 가드 템플릿 자동 반영 (오류 방지 스킬)

- 용도: `parse-issue --strict`에서 실패했을 때 PR 본문에 재요청용 템플릿을 자동으로 붙입니다.
- 파일: `scripts/gh-apply-scope-fix-template.sh`
- 템플릿: `scripts/scope-guard-fix-template.md`

```bash
# 실행(기본: 본문 상단에 템플릿 추가)
./scripts/gh-apply-scope-fix-template.sh --pr <PR번호>

# 코드 자동 채우기 실패 시 수동 코드 지정
./scripts/gh-apply-scope-fix-template.sh --pr <PR번호> --codes "SCOPE-MISSING-TITLE,SCOPE-OPS-SOFT"

# 실제 적용 전 내용 미리보기
./scripts/gh-apply-scope-fix-template.sh --pr <PR번호> --dry-run
```
