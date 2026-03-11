# Windows 패키징 검증 체크리스트

기준일: 2026-03-11

이 문서는 `SIA` Windows 배포물의 build 및 runtime 검증 절차를 정리한다.

## 1. 목표

- 대상 산출물:
  - `dist/windows/SIA-Windows`
- 목표 상태:
  - standalone 구조 생성 완료
  - 첫 실행 설정 가능
  - 대시보드/리포트 실행 가능
  - dry-run/live 기본 흐름 확인

## 2. 사전 조건

- Windows 환경 또는 `pwsh` 사용 가능한 환경
- Python 또는 `py -3`
- PowerShell 실행 가능

## 3. build 실행

```powershell
pwsh /Users/dohyeon/Documents/Playground/SIA/scripts/windows-launchers/Build-SIA-Windows.ps1
```

생성 위치:

- `dist/windows/SIA-Windows`

## 4. 생성물 구조 확인

기대 항목:

- `SIA.cmd`
- `SIA.ps1`
- `SIA-Run.cmd`
- `SIA-Dashboard.cmd`
- `SIA-Reports.cmd`
- `SIA-Market-Settings.cmd`
- `SIA-Market-Tickers.cmd`
- `.sia-support/`
  - `src/`
  - `scripts/_internal/`
- `Docs/`
- `README.txt`

중요:

- 내부 실행 파일은 `.sia-support` 아래에 있어야 함
- 루트에는 사용자 진입점만 보여야 함

## 5. 첫 실행 검증

### 5.1 기본 진입점

```cmd
SIA.cmd
```

또는

```powershell
.\SIA.ps1
```

기대 동작:

- 설정이 비어 있으면 첫 실행 설정 마법사
- 설정이 있으면 메인 진입

### 5.2 생성 파일

기대 생성:

- `%USERPROFILE%\.config\sia-notifier\env`
- `%USERPROFILE%\.config\sia-notifier\market-selection.json`
- `%USERPROFILE%\.config\sia-notifier\setup-complete`

## 6. 런타임 검증

### 6.1 대시보드

```cmd
SIA-Dashboard.cmd
```

기대 결과:

- `dashboard.html` 생성
- 기본 브라우저에서 오픈

### 6.2 리포트

```cmd
SIA-Reports.cmd
```

기대 결과:

- report hub 생성
- 리포트 링크 접근 가능

### 6.3 엔진 dry-run

```powershell
.\SIA-Run.ps1 -DryRun
```

기대 결과:

- 텔레그램 미전송
- DB/리포트 생성은 정상

### 6.4 엔진 live

```powershell
.\SIA-Run.ps1 -Live
```

기대 결과:

- 현재 장중 시장에서 수집/판단
- 조건 충족 시 텔레그램 발송

## 7. 실패 시 점검 순서

1. `python` 또는 `py` 없음
   - Windows PATH 문제
2. `.sia-support` 누락
   - build script가 incomplete
3. env 파일 저장 실패
   - `%USERPROFILE%\.config` 권한 문제
4. dashboard 미생성
   - Python 실행 경로 또는 `PYTHONPATH` 설정 문제

## 8. 판매 직전 최종 체크

- [ ] build가 에러 없이 완료되는가
- [ ] 루트에 사용자 진입점만 보이는가
- [ ] `.sia-support`가 포함되는가
- [ ] 첫 실행 설정 마법사가 동작하는가
- [ ] 대시보드가 열리는가
- [ ] 리포트 허브가 열리는가
- [ ] dry-run이 실제 텔레그램을 보내지 않는가
- [ ] live 1회가 정상 수행되는가

