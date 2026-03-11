# macOS 서명/노타리 체크리스트

기준일: 2026-03-11

이 문서는 `SIA` macOS 배포물을 실제 판매/전달 가능한 수준으로 서명하고 노타리하는 절차를 정리한다.

## 1. 목표

- 대상 산출물:
  - `dist/macos/SIA-macOS/SIA.app`
- 목표 상태:
  - `Developer ID Application` 서명 완료
  - `notarytool` 제출 및 승인 완료
  - stapler 적용 완료

## 2. 사전 조건

- Apple Developer Program 계정
- macOS 키체인에 `Developer ID Application` 인증서 설치
- `xcrun notarytool` 사용 가능
- 필요 시 앱 아이콘 파일:
  - `.icns`

## 3. 현재 확인 포인트

현재 환경에서 먼저 확인:

```bash
security find-identity -v -p codesigning
xcrun notarytool history --keychain-profile <PROFILE_NAME>
```

정상 기준:

- 첫 명령에서 유효한 `Developer ID Application` 항목이 1개 이상 보여야 함
- 두 번째 명령이 실패하지 않아야 함

## 4. 환경 변수

패키징 스크립트가 읽는 값:

```bash
export SIA_MACOS_CODESIGN_IDENTITY="Developer ID Application: <YOUR NAME> (<TEAMID>)"
export SIA_MACOS_NOTARY_PROFILE="<NOTARY_PROFILE_NAME>"
export SIA_MACOS_ICON_ICNS="/absolute/path/to/SIA.icns"
```

설명:

- `SIA_MACOS_CODESIGN_IDENTITY`
  - `codesign`에 사용할 인증서 이름
- `SIA_MACOS_NOTARY_PROFILE`
  - `xcrun notarytool store-credentials`로 저장한 프로필 이름
- `SIA_MACOS_ICON_ICNS`
  - 선택 사항
  - 주지 않으면 기본 `applet.icns` 유지

## 5. 실행 절차

```bash
/Users/dohyeon/Documents/Playground/SIA/scripts/_internal/sia-package-macos.command
```

현재 스크립트 동작:

1. staging 폴더 생성
2. `SIA.app` 생성
3. 아이콘 덮어쓰기
4. `codesign --deep --options runtime`
5. `notarytool submit --wait`
6. `stapler staple`

## 6. 결과 확인

### 6.1 앱 구조

```bash
ls -la /Users/dohyeon/Documents/Playground/SIA/dist/macos/SIA-macOS
```

기대 항목:

- `SIA.app`
- `Utilities/`
- `Docs/`
- `.sia-support/`

### 6.2 서명 확인

```bash
codesign -dv --verbose=4 /Users/dohyeon/Documents/Playground/SIA/dist/macos/SIA-macOS/SIA.app
```

확인할 값:

- `Authority=Developer ID Application`
- 식별자/서명 정보가 정상 출력

### 6.3 Gatekeeper 확인

```bash
spctl -a -vv /Users/dohyeon/Documents/Playground/SIA/dist/macos/SIA-macOS/SIA.app
```

기대 상태:

- `accepted`

## 7. 실패 시 점검 순서

1. `0 valid identities found`
   - 인증서가 키체인에 없음
2. `notarytool` profile 오류
   - keychain profile이 저장되지 않았거나 이름이 다름
3. `stapler` 실패
   - 노타리 승인 전이거나 제출 실패
4. icon 파일 오류
   - `.icns` 경로 오타 또는 파일 손상

## 8. 판매 직전 최종 체크

- [ ] `SIA.app` 더블클릭 시 메인 진입
- [ ] 첫 실행 설정 마법사 동작
- [ ] Telegram 토큰/채팅 ID 저장
- [ ] 대시보드 표시
- [ ] 서명 확인 통과
- [ ] Gatekeeper 확인 통과
- [ ] 노타리 스테이플 완료

