# SIA Scripts Guide

현재 구조는 `단일 사용자용 실행기`와 `내부 운영 스크립트`로 분리되어 있습니다.

## 1. 사용자용 더블클릭 실행기

Finder에서 바로 실행할 기본 파일은 아래 1개입니다.

- `scripts/SIA.command`
  - 단일 실행기. 실전/드라이런/대시보드/리포트/시장 설정/티커 설정을 한 번에 선택

보조 실행기는 아래에 남겨둡니다.

- `scripts/SIA-Run.command`
  - 알림 엔진 1회 실행
- `scripts/SIA-Dashboard.command`
  - 대시보드 생성/오픈
- `scripts/SIA-Reports.command`
  - 리포트 허브 생성/오픈
- `scripts/SIA-Market-Settings.command`
  - 활성 시장 선택
- `scripts/SIA-Market-Tickers.command`
  - 시장별 티커 편집

## 2. 내부 운영 스크립트

실제 동작 로직은 모두 `scripts/_internal/` 아래에 있습니다.

- 운영 엔진
  - `scripts/_internal/sia-notifier-launch.command`
  - `scripts/_internal/sia-notifier-launchd.command`
- 점검/검증
  - `scripts/_internal/sia-notifier-preflight.command`
  - `scripts/_internal/sia-notifier-check-finnhub.command`
  - `scripts/_internal/sia-notifier-check-telegram.command`
  - `scripts/_internal/sia-notifier-live-quickcheck.command`
  - `scripts/_internal/sia-notifier-live-acceptance.command`
- 리포트
  - `scripts/_internal/sia-dashboard.command`
  - `scripts/_internal/sia-report-hub.command`
  - `scripts/_internal/sia-universe-refresh.command`
  - `scripts/_internal/sia-full-universe-refresh.command`
  - `scripts/_internal/sia-full-universe-report.command`
  - `scripts/_internal/sia-data-quality.command`
  - `scripts/_internal/sia-backtest-readiness.command`
  - `scripts/_internal/sia-price-backtest.command`
  - `scripts/_internal/sia-position-backtest.command`
  - `scripts/_internal/sia-factor-breakdown.command`
  - `scripts/_internal/sia-research-report.command`
- 운영 보조
  - `scripts/_internal/sia-backtest-refresh.command`
  - `scripts/_internal/sia-backtest-refresh-launchd.command`
  - `scripts/_internal/sia-ready-buckets-guard.command`
  - `scripts/_internal/sia-ready-buckets-launchd.command`

## 2.1 Windows 백업 실행기

Windows용 백업 래퍼는 `scripts/windows-launchers/` 아래에 있습니다.

- `scripts/windows-launchers/SIA.cmd`
- `scripts/windows-launchers/SIA.ps1`
- `scripts/windows-launchers/SIA-Run.cmd`
- `scripts/windows-launchers/SIA-Dashboard.cmd`
- `scripts/windows-launchers/SIA-Reports.cmd`
- `scripts/windows-launchers/SIA-Market-Settings.cmd`
- `scripts/windows-launchers/SIA-Market-Tickers.cmd`
- `scripts/windows-launchers/*.ps1`

## 3. macOS 기본 사용 흐름

### 빠른 실행

- 엔진 실행: `scripts/SIA-Run.command`
- 대시보드 확인: `scripts/SIA-Dashboard.command`
- 리포트 허브 확인: `scripts/SIA-Reports.command`

### 환경 파일 준비

```bash
mkdir -p ~/.config/sia-notifier
cat scripts/_internal/sia-notifier-env.example > ~/.config/sia-notifier/env
chmod 600 ~/.config/sia-notifier/env
```

### 사전 점검

```bash
./scripts/_internal/sia-notifier-preflight.command
./scripts/_internal/sia-notifier-check-telegram.command
./scripts/_internal/sia-notifier-check-finnhub.command
./scripts/_internal/sia-notifier-live-quickcheck.command balanced
```

### 실전/드라이런

```bash
./scripts/_internal/sia-notifier-launch.command balanced --live
./scripts/_internal/sia-notifier-launch.command balanced --dry-run
```

### 리포트 재생성

```bash
./scripts/_internal/sia-dashboard.command
./scripts/_internal/sia-report-hub.command
./scripts/_internal/sia-data-quality.command
./scripts/_internal/sia-backtest-readiness.command
./scripts/_internal/sia-backtest-refresh.command
```

## 4. launchd 자동 실행

설치:

```bash
./scripts/_internal/sia-notifier-launchd.command install balanced
```

제거:

```bash
./scripts/_internal/sia-notifier-launchd.command uninstall
```

상태:

```bash
./scripts/_internal/sia-notifier-launchd.command status
```

야간 백테스트 리프레시:

```bash
./scripts/_internal/sia-backtest-refresh-launchd.command install
./scripts/_internal/sia-backtest-refresh-launchd.command status
```

준비도 가드:

```bash
./scripts/_internal/sia-ready-buckets-launchd.command install
./scripts/_internal/sia-ready-buckets-launchd.command status
```

## 5. 시장 설정

활성 시장 선택:

```bash
./scripts/_internal/sia-market-settings.command
```

시장별 티커 편집:

```bash
./scripts/_internal/sia-market-tickers.command
```

기본 정책:

- 뉴스 수집: 연중무휴
- 가격/신호 수집: 활성 시장 + 장중일 때만
- 기본 활성 시장: `US`
- `KR`, `EU`, `JP`는 사용자가 직접 활성화해야 동작

## 6. Windows 참고

Windows 진입점은 현재 내부 스크립트 경로를 사용합니다.

- `scripts/_internal/sia-notifier-launch.ps1`

## 7. PR/Scope Guard 도구

PR 관련 스크립트도 모두 내부 경로를 사용합니다.

```bash
./scripts/_internal/scope-guard-pr-preflight.sh --pr <PR번호>
./scripts/_internal/scope-guard-gate.sh --pr <PR번호>
./scripts/_internal/scope-guard-one-shot.sh
./scripts/_internal/scope-guard-pr-body-normalizer.sh --pr <PR번호>
./scripts/_internal/gh-apply-scope-fix-template.sh --pr <PR번호>
```

## 8. 원칙

- Finder에서 직접 누르는 파일은 `SIA-*`만 사용
- 자동화/점검/운영 명령은 `scripts/_internal/`만 사용
- 문서/launchd/래퍼 수정 시 경로 기준은 이 분리 구조를 따라야 함
