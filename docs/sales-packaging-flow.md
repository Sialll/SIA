# SIA 판매용 패키징 흐름

기준일: 2026-03-11

이 문서는 현재 SIA를 판매용 배포 형태로 묶기 위한 최소 흐름을 정리한다.

## 1. 현재 판단

- 데이터 검증:
  - 미국장 기준 반영률 `100%`
  - `data-quality-report.html` 판정 `양호`
  - `backtest-readiness-report.html` 판정 `준비 완료`
- 따라서 지금부터는 `설치/실행 경험`을 판매용으로 정리하는 단계다.

## 2. 판매용 패키징 목표

사용자에게 노출되는 것은 아래 1개 진입점이면 충분하다.

- macOS: `SIA.app`
- Windows: `SIA.cmd` 또는 `SIA.ps1`

보조 실행기는 제품 내부 유틸리티로만 포함한다.

## 3. 배포물 구성

### macOS

- `SIA.app`
- `Utilities/`
  - `SIA.command`
  - `SIA-Run.command`
  - `SIA-Dashboard.command`
  - `SIA-Reports.command`
  - `SIA-Market-Settings.command`
  - `SIA-Market-Tickers.command`
- `Docs/`
  - `sales-readiness-checklist.md`
  - `sales-ui-ia-plan.md`
  - `default-universe.md`
- `README.txt`
- 숨김 내부 폴더 `.sia-support/`
  - `src/`
  - `scripts/_internal/`

### Windows

- `SIA.cmd`
- `SIA.ps1`
- `SIA-Run.cmd`
- `SIA-Dashboard.cmd`
- `SIA-Reports.cmd`
- `SIA-Market-Settings.cmd`
- `SIA-Market-Tickers.cmd`
- `Docs/`
  - `sales-readiness-checklist.md`
  - `sales-ui-ia-plan.md`
  - `default-universe.md`
- `README.txt`

## 4. 패키징 원칙

- 사용자에게 `env`, `launchd`, 내부 `_internal` 경로를 직접 설명하지 않는다.
- 배포물에는 단일 진입점과 최소 유틸리티만 둔다.
- 내부 실행 파일은 루트에 드러내지 않고 숨김 support 폴더로 묶는다.
- 관리자용 리포트는 제품 메인에서 숨기고, 지원/운영 시에만 사용한다.
- Telegram 알림과 로컬 DB 기반 오프라인 점수 기능은 기본 포함한다.
- 첫 실행 시에는 설정 마법사가 자동으로 열리게 한다.

## 4.1 첫 실행 설정 마법사

첫 실행 마법사에서 처리할 항목:

- Telegram 봇 토큰
- Telegram 채팅 ID
- 기본 유니버스 포함 여부
- 활성 시장 선택
- 시장별 관심 종목 입력

재실행 방법:

```bash
./scripts/SIA.command --setup
```

## 5. 현재 제공 스크립트

### macOS 스테이징

```bash
./scripts/_internal/sia-package-macos.command
```

생성 위치:

- `dist/macos/SIA-macOS/`

주 진입점:

- `dist/macos/SIA-macOS/SIA.app`

보조 실행기:

- `dist/macos/SIA-macOS/Utilities/`

### Windows 스테이징

```powershell
pwsh ./scripts/windows-launchers/Build-SIA-Windows.ps1
```

생성 위치:

- `dist/windows/SIA-Windows/`

관련 체크리스트:

- `docs/macos-signing-notarization-checklist.md`
- `docs/windows-packaging-validation-checklist.md`

## 6. 다음 단계

### 단계 1

- 현재 staging 폴더 기준으로 사용자 테스트
- 첫 실행 설정 문구 정리
- `README.txt`를 일반 사용자용 문구로 다듬기
- `SIA.app` 더블클릭 흐름 점검

### 단계 2

- macOS:
  - 앱 번들(`SIA.app`) 아이콘/서명/notarization 검토
  - 지원 환경 변수:
    - `SIA_MACOS_ICON_ICNS`
    - `SIA_MACOS_CODESIGN_IDENTITY`
    - `SIA_MACOS_NOTARY_PROFILE`
- Windows:
  - 실행 정책/바로가기/압축 배포 검토
  - standalone support 폴더(`.sia-support`) 유지

### 단계 3

- 자동 업데이트 정책
- 버전 표시
- 라이선스/활성화 흐름

## 7. 출시 전 최종 확인

- [ ] 더블클릭 한 번으로 메인이 열리는가
- [ ] Telegram 연결 안내가 비개발자 기준으로 이해 가능한가
- [ ] 관심 종목 추가/삭제/일괄 입력이 자연스러운가
- [ ] 휴장 중에도 오프라인 점수 읽기가 가능한가
- [ ] 백테스트 탭에서 현재 판매 준비 상태를 쉽게 이해할 수 있는가

## 8. 현재 패키징 상태

기준일: 2026-03-11

- macOS:
  - staging 폴더 생성 가능
  - `SIA.app` 생성 가능
  - hidden support 구조(`.sia-support`) 반영 완료
  - 실제 `Developer ID` 서명/노타리는 아직 미실행
- Windows:
  - standalone build script 준비 완료
  - `.sia-support` 구조 반영 완료
  - 이 환경에 `pwsh`가 없어 실제 runtime 검증은 미완료
