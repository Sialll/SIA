# Workflow (Issue -> PR)

## 기본 흐름

1. Issue 생성
2. 계획 정리
3. 구현
4. 점검
5. PR 생성
6. 리뷰 반영 후 머지

## 현재 저장소 기준

- 사용자 실행 파일: `scripts/SIA-*.command`
- 내부 운영/검증/리포트 스크립트: `scripts/_internal/`
- 문서/launchd/운영 안내를 수정할 때는 위 경로 구조를 기준으로 맞춘다.

## 구현 전 점검

- 요구사항과 제약을 먼저 고정
- 영향 파일을 좁게 잡고 수정
- 운영 경로와 사용자 더블클릭 경로를 혼동하지 않음

## 구현 후 점검

- 운영 엔진 변경 시:
  - `scripts/_internal/sia-notifier-live-quickcheck.command`
- 리포트/대시보드 변경 시:
  - `scripts/SIA-Dashboard.command`
  - `scripts/SIA-Reports.command`

## PR 전 확인

- 변경 범위가 Issue와 맞는지 확인
- 문서 경로가 `SIA-*` / `_internal` 구조와 맞는지 확인
- 사용자용 진입점과 내부용 스크립트를 섞어 설명하지 않았는지 확인
