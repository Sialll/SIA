# SIA Trading Signal Notifier (Telegram-only)

> 이 프로젝트의 목적: 
> **자동 주문은 하지 않고, 로컬 LLM 보조로 시그널 근거를 계산해 텔레그램으로 매수/매도/관망 알림만 발송**한다.

## Product Direction

- 현재 구현은 `Telegram-only notifier`다.
- 목표 제품은 `AI + Macro + Quant + Event`를 결합한 `local-first investment research engine`이다.
- 상용 방향은 `자동매매`가 아니라 `분석 도구 판매`이며, 유료 버전은 직접적인 `BUY/SELL 추천`보다 `Composite Score`, `Risk Level`, `Macro Environment`, `Momentum` 중심으로 표현한다.
- 장기 구조와 사업/법적 가정은 [product-architecture.md](/Users/dohyeon/Documents/Playground/SIA/docs/product-architecture.md)에 정리했다.

## Current Phase

- 현재 리포지토리는 `1단계 운영 코어`에 해당한다.
- 구현 범위는 `가격/뉴스 수집 -> 점수 계산 -> Telegram 알림 -> DB 기록 -> HTML 리포트`다.
- 기본 universe는 `시가총액 10억달러(약 1.4조원) 이상 대표 종목 seed set + 사용자 추가 티커` 구조다.
- 주문 실행, 포트폴리오 체결, 투자자문형 추천 엔진은 포함하지 않는다.
- 즉, 지금 코드는 `최종 제품의 collector + notifier slice`이며, 이후 대시보드/백테스트/리서치 기능이 위에 붙는 구조다.

## 한 줄 요약

- 주기적으로 주가(종가 기반)와 뉴스 헤드라인을 수집한다.
- 뉴스는 연중무휴 수집하고, 가격/신호는 활성 시장 장중에만 수집한다.
- 간단한 기술적 지표(SMA/RSI)와 뉴스 임팩트를 합성해 신호를 만든다.
- `VIX / 10Y / DXY / WTI / CPI` 같은 위험지표를 매크로 점수에 반영한다.
- `BUY`/`SELL`/`HOLD` 신호가 생성되면 텔레그램으로 메시지를 전송한다.
- 화면과 알림의 점수 표시는 `0~100점` 체계다. 내부 계산은 정규화 점수를 유지한다.
- 주문 실행(자동매매)은 포함하지 않는다.

## 현재 코드 구조

- `src/sia/trading_signal_notifier.py`
  - 메인 운영 엔진
- `src/sia/notifier_config.py`
  - 환경변수/시장 선택/시장별 티커 설정 로드
- `src/sia/default_universe.py`
  - 시장별 기본 1B+ seed universe
- `src/sia/universe_collector.py`
  - daily full-universe 확장용 스켈레톤과 universe snapshot 생성기
- `src/sia/full_universe_collector.py`
  - 전종목 1B+ universe provider 확장용 collector 골격
- `src/sia/full_universe_report.py`
  - full universe 후보 snapshot을 읽기용 HTML로 보여주는 리포트
- `src/sia/market_runtime.py`
  - 시장 활성 상태와 장 시간 판정
- `src/sia/notifier_collector.py`
  - 가격/뉴스/LLM 수집
- `src/sia/notifier_storage.py`
  - sqlite 저장, source 추론, snapshot 기록
- `src/sia/notifier_scoring.py`, `src/sia/factor_engine.py`
  - signal/composite score 계산
- `src/sia/dashboard_report.py` 및 각 `*_report.py`
  - dashboard / readiness / backtest / factor / research / data quality 리포트 렌더링
- `scripts/SIA-*.command`
  - 사용자용 더블클릭 진입점
- `scripts/_internal/`
  - 운영/검증/launchd/리포트 생성 내부 스크립트

## 실행 목적/인수인계 포인트

1. **수신용 알림 시스템**으로 이해하고 코드/설정/환경변수를 확인하면 된다.
2. **자동 주문 경로가 없으므로** 법적/운영 리스크를 줄이고 모니터링 중심으로 운영한다.
3. 신호 정확성은 모델/임계치 변경으로 개선 가능하며, 핵심 포인트는 아래 설정값이다.
   - `SIA_INCLUDE_DEFAULT_UNIVERSE`: 기본 1B+ universe 포함 여부
   - `SIA_UNIVERSE_SNAPSHOT_PATH`: 유니버스 스냅샷 저장 경로
   - `SIA_FULL_UNIVERSE_PROVIDER`: full universe 후보 수집 provider 이름
   - `SIA_FULL_UNIVERSE_INPUT_PATH`: full universe 후보 입력 JSON 경로
   - `SIA_FULL_UNIVERSE_SNAPSHOT_PATH`: full universe 스냅샷 저장 경로
   - `SIGNAL_COOLDOWN_MINUTES`: 동일 티커 반복 알림 억제 시간
   - `POLL_INTERVAL_MINUTES`: 수집 주기
   - `MAX_NEWS_PER_TICKER`: 뉴스 반영 건수
   - `SIGNAL_TREND_WEIGHT`, `SIGNAL_RSI_WEIGHT`, `SIGNAL_NEWS_WEIGHT`: 지표 가중치
   - `SIGNAL_THRESHOLD`: BUY/SELL 임계치 (`0.35` 또는 `35` 입력 가능)
   - `OLLAMA_MODEL`: 로컬 LLM 모델

## 실행 방법

### 필수 요구사항

- Python 3.11+ 권장
- 로컬 Ollama 실행 중이어야 함(또는 dry-run)
- Telegram Bot Token + Chat ID (운영 시)
- API 키
  - 주가: `FINNHUB_API_KEY` (현재 구현 기본값)
  - 뉴스: `MARKETAUX_API_KEY` (선택. 없으면 뉴스 분석/첨부 생략)

### 환경 변수

- `SIA_INCLUDE_DEFAULT_UNIVERSE`: 기본 1B+ seed universe 포함 여부(기본 `1`)
- `TICKERS_US`, `TICKERS_KR`, `TICKERS_EU`, `TICKERS_JP`: 시장별 추가 티커
- `TICKERS`: 미국 추가 티커 alias
- `SIGNAL_DB_PATH`: DB 저장 경로(기본값 `data/trading_signal_notifier.sqlite`)
- `SIA_UNIVERSE_SNAPSHOT_PATH`: 유니버스 스냅샷 경로(기본 `~/Library/Caches/sia-notifier/universe-snapshot.json`)
- `SIA_FULL_UNIVERSE_PROVIDER`: full universe 후보 공급자 이름(기본 `manual_json`)
- `SIA_FULL_UNIVERSE_INPUT_PATH`: full universe 후보 입력 경로(기본 `~/.config/sia-notifier/full-universe-candidates.json`)
- `SIA_FULL_UNIVERSE_SNAPSHOT_PATH`: full universe 스냅샷 경로(기본 `~/Library/Caches/sia-notifier/full-universe-snapshot.json`)
- `SIA_FULL_UNIVERSE_REPORT_PATH`: full universe 리포트 경로(기본 `~/Library/Caches/sia-notifier/full-universe-report.html`)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `FINNHUB_API_KEY`, `MARKETAUX_API_KEY`
- `OLLAMA_HOST`(기본 `http://localhost:11434`)
- `OLLAMA_MODEL`(가볍게 시작: `phi3:mini`, 사용 시 성능 여유 있으면 `mistral:7b-instruct`로 변경 가능)
- `POLL_INTERVAL_MINUTES`(기본 `15`)
- `SIGNAL_COOLDOWN_MINUTES`(기본 `30`)
- `MAX_NEWS_PER_TICKER`(기본 `3`)
- `NEWS_LOOKBACK_HOURS`(기본 `24`)
- `FINNHUB_FAIL_THRESHOLD`(기본 `3`, 기본값 초과 실패 시 Yahoo 폴백 강제)
- `FINNHUB_FAIL_WINDOW_MINUTES`(기본 `120`, 실패 이력 윈도우)
- `TELEGRAM_PARSE_MODE`(`HTML`, `MARKDOWN`, `MARKDOWNV2`, `NONE`, 기본 `HTML`)
- `SIGNAL_TREND_WEIGHT`(기본 `0.55`), `SIGNAL_RSI_WEIGHT`(기본 `0.25`), `SIGNAL_NEWS_WEIGHT`(기본 `0.20`)
- `SIGNAL_THRESHOLD`(기본 `35`, `0.35`도 허용)

### 실행 예시

```bash
python -m sia.trading_signal_notifier \
  --tickers AAPL,TSLA,MSFT \
  --finnhub-api-key "$FINNHUB_API_KEY" \
  --marketaux-api-key "$MARKETAUX_API_KEY" \
  --telegram-bot-token "$TELEGRAM_BOT_TOKEN" \
  --telegram-chat-id "$TELEGRAM_CHAT_ID" \
  --ollama-host http://localhost:11434 \
  --ollama-model phi3:mini \
  --news-lookback-hours 24 \
  --telegram-parse-mode HTML \
  --trend-weight 0.55 \
  --rsi-weight 0.25 \
  --news-weight 0.2 \
  --signal-threshold 0.35 \
  --poll-interval-minutes 15
```

원하면 한 번만 실행:

```bash
python -m sia.trading_signal_notifier --once
```

API/네트워크 없이 동작 확인:

```bash
python -m sia.trading_signal_notifier --dry-run --once
```

원클릭 사전 점검(권장):

```bash
./scripts/_internal/sia-notifier-preflight.command
```

동작 순서: Finnhub 키(있는 경우) 점검 → Telegram 점검(설정된 경우) → dry-run 1회 실행.

텔레그램 연동 점검:

```bash
./scripts/_internal/sia-notifier-check-telegram.command
```

위 스크립트는 `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` 값으로 `getMe`, `getChat` API 응답을 먼저 확인해
텔레그램 연결 상태를 빠르게 점검합니다.

### 신호 튜닝 프리셋(실행 예시)

기본값은 `trend=0.55 / rsi=0.25 / news=0.20 / threshold=35점`입니다.

- 보수형(신호 빈도 낮춤)

```bash
python -m sia.trading_signal_notifier --once --tickers AAPL,MSFT \
  --trend-weight 0.6 --rsi-weight 0.2 --news-weight 0.2 --signal-threshold 45
```

- 균형형(기본값)

```bash
python -m sia.trading_signal_notifier --once --tickers AAPL,MSFT \
  --trend-weight 0.55 --rsi-weight 0.25 --news-weight 0.20 --signal-threshold 35
```

- 공격형(신호 빈도 증가)

```bash
python -m sia.trading_signal_notifier --once --tickers AAPL,MSFT \
  --trend-weight 0.45 --rsi-weight 0.25 --news-weight 0.30 --signal-threshold 25
```

Mac에서는 더블클릭 실행용으로 `scripts/SIA-Run.command`를 두 번 클릭할 수 있습니다.  
실행 후 마지막 로그를 바탕으로 `last-run.html` 리포트가 자동 열림 상태로 남습니다.

### 리서치 리포트

기존 `dashboard_snapshots` 데이터를 재활용해 가벼운 백테스트/리서치 리포트를 만들 수 있습니다.

```bash
./scripts/_internal/sia-research-report.command
```

생성 파일:

- `~/Library/Caches/sia-notifier/research-report.html`

기준:

- 외부 API를 다시 호출하지 않음
- 같은 티커의 다음 `N snapshot` 가격을 기준으로 미래 성과 계산
- 기본 horizon: `1,3,5`

### 기본 유니버스 문서

현재 기본 1B+ seed universe 목록은 아래 문서에 정리했습니다.

- [default-universe.md](/Users/dohyeon/Documents/Playground/SIA/docs/default-universe.md)

중요:

- 현재는 `전종목 전체`가 아니라 운영 가능한 `seed universe`
- 장기적으로는 `daily universe collector`를 붙여 full universe로 확장

### 유니버스 스냅샷 생성 스켈레톤

현재 full universe 확장용 골격이 들어가 있습니다.

```bash
./scripts/_internal/sia-universe-refresh.command
```

생성 파일:

- `~/Library/Caches/sia-notifier/universe-snapshot.json`

현재 역할:

- 활성 시장 기준 기본 seed universe + 사용자 추가 티커를 JSON snapshot으로 저장
- 아직 `전 시장 1B+ 전종목 수집`은 하지 않음
- 나중에 market-cap provider를 붙일 자리만 먼저 만들어 둔 상태

### full universe collector 골격

실제 `전종목 1B+ universe` 확장은 별도 collector 축으로 분리해 두었습니다.

```bash
./scripts/_internal/sia-full-universe-refresh.command
```

생성 파일:

- `~/Library/Caches/sia-notifier/full-universe-snapshot.json`

현재 역할:

- `manual_json` provider로 후보 리스트를 읽어 활성 시장 + 시가총액 기준으로 필터링
- 아직 외부 market-cap provider를 직접 호출하지 않음
- runtime watchlist와 분리된 `전종목 후보 universe` 스냅샷만 생성

샘플 입력 파일:

- `~/.config/sia-notifier/full-universe-candidates.json`

읽기용 HTML 리포트:

- `~/Library/Caches/sia-notifier/full-universe-report.html`

### 실행기 프리셋 사용법

- 균형형(기본): `open scripts/_internal/sia-notifier-launch.command balanced`
- 보수형: `open scripts/_internal/sia-notifier-launch.command conservative`
- 공격형: `open scripts/_internal/sia-notifier-launch.command aggressive`

각 모드가 실행 시 내부적으로 `--trend-weight`, `--rsi-weight`, `--news-weight`, `--signal-threshold`를 자동 적용합니다.

## 데이터/판단 흐름

1. 수집: Finnhub 일봉 클로즈 + Marketaux 뉴스 2~3건
2. 처리:
   - 종가 시퀀스로 SMA(5/20), RSI(14) 계산
   - `VIX / 10Y / DXY / WTI / CPI`로 매크로 위험 점수 계산
   - 뉴스는 Ollama에서 요약/감성 점수 추출
3. 신호 결합:
   - 추세/RSI/뉴스 + 매크로/이벤트 보정으로 BUY/SELL/HOLD 판단
   - 사용자에게 보이는 점수는 `0~100점`
4. 알림:
   - `HOLD`는 DB에 기록만 하고 전송 생략 가능
   - 동일 티커 30분(기본) 이내 중복 알림 차단
5. 내구성:
   - 실패 시 예외 로그 + 알림 이력 저장, 재실행 시 DB 기반 중복 방지

## DB 테이블 요약

- `price_ticks`: 티커/시간/close 저장(중복방지 PK)
- `news_items`: 뉴스 ID 기준 저장(요약, 임팩트, 점수, 키워드)
- `alerts`: 실제 알림/실패 이력 저장

## 운영 주의사항

- 이 코드는 **시그널 보조용**이며 투자 조언이 아님.
- 무료 API는 호출량/지연 이슈가 있어 티커 수를 늘릴 때 쿼터 조정 필요.
- 텔레그램은 텍스트 제한 및 전송 실패를 대비해 주기적 오류 모니터링 필요.
- 시장별(국내/해외) 데이터 커버리지가 API마다 다르므로 종목군별 동작 검증이 필요.

## 인수인계 체크리스트 (핸드오버용)

1. `trading_signal_notifier.py`는 Telegram-only 파이프라인 동작의 메인 파일이다.
2. 환경변수 세팅 후 `--dry-run --once`로 먼저 점검한다.
3. API 키/봇 토큰 유효성 확인 후 상시 실행한다.
4. 알림 품질 조정은 임계치, 가중치, 뉴스 수량으로 수행한다.
5. PR 규칙 변경 시 `pr_rules.py`의 one-file 정책을 먼저 확인한다.
6. 작업 전후 방향성 점검은 루트의 [`SKILL.md`](SKILL.md)에서 확인한다.  
7. PR 본문은 `Goal / Requirements / Constraints (must obey) / Acceptance criteria` 형식을 지키고, `parse-issue --strict` 결과를 실패 없이 통과해야 병합 가능.

## 관련 워크플로우

- Issue 기반으로 작업 계획 수립 후 브랜치/PR 처리 (`WORKFLOW.md`, `AGENTS.md` 참조).

## 상시 실행 가이드 (운영용)

### 공통: 환경 변수 파일 준비

macOS 기준 `$HOME/.config/sia-notifier/env` 예시:

```bash
export TICKERS="AAPL,MSFT,TSLA"
export SIA_INCLUDE_DEFAULT_UNIVERSE="1"
export TICKERS_US="AAPL,MSFT"
export TICKERS_KR=""
export TICKERS_EU=""
export TICKERS_JP=""
export SIGNAL_DB_PATH="/Users/dohyeon/sia-notifier/trading_signal_notifier.sqlite"
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export FINNHUB_API_KEY="..."
export MARKETAUX_API_KEY="..."
export OLLAMA_HOST="http://localhost:11434"
export OLLAMA_MODEL="phi3:mini"
export POLL_INTERVAL_MINUTES="15"
export SIGNAL_COOLDOWN_MINUTES="30"
export MAX_NEWS_PER_TICKER="3"
export NEWS_LOOKBACK_HOURS="24"
export FINNHUB_FAIL_THRESHOLD="3"
export FINNHUB_FAIL_WINDOW_MINUTES="120"
export TELEGRAM_PARSE_MODE="HTML"
export SIGNAL_TREND_WEIGHT="0.55"
export SIGNAL_RSI_WEIGHT="0.25"
export SIGNAL_NEWS_WEIGHT="0.20"
export SIGNAL_THRESHOLD="35"
export PYTHONPATH="/Users/dohyeon/Documents/Playground/SIA/src"
```

파일 권한은 `chmod 600`으로 보호하세요.

### macOS (launchd)

현재는 plist를 수동 작성하지 않고 내부 스크립트로 설치하는 방식을 권장합니다.

적용 명령:

```bash
./scripts/_internal/sia-notifier-launchd.command install balanced
./scripts/_internal/sia-notifier-launchd.command status
```

로그 확인:

```bash
tail -f ~/Library/Caches/sia-notifier/launchd.out.log
tail -f ~/Library/Caches/sia-notifier/launchd.err.log
```

관련 launchd:

- 알림 엔진: `./scripts/_internal/sia-notifier-launchd.command`
- 야간 백테스트 리프레시: `./scripts/_internal/sia-backtest-refresh-launchd.command`
- 준비도 가드: `./scripts/_internal/sia-ready-buckets-launchd.command`

### Linux (systemd)

`/etc/systemd/system/sia-notifier.service` 예시:

```ini
[Unit]
Description=SIA Trading Signal Notifier
After=network.target

[Service]
Type=simple
User=dohyeon
WorkingDirectory=/home/dohyeon/Documents/Playground/SIA
EnvironmentFile=/etc/sia-notifier/env
Environment="PYTHONPATH=/home/dohyeon/Documents/Playground/SIA/src"
ExecStart=/usr/bin/python3 -m sia.trading_signal_notifier
Restart=always
RestartSec=5
StandardOutput=append:/var/log/sia-notifier/sia-notifier.log
StandardError=append:/var/log/sia-notifier/sia-notifier.err.log

[Install]
WantedBy=multi-user.target
```

실행:

```bash
sudo mkdir -p /var/log/sia-notifier
sudo systemctl daemon-reload
sudo systemctl enable --now sia-notifier
sudo systemctl status sia-notifier
```

### 실행 전 점검

- `./scripts/_internal/sia-notifier-preflight.command`로 환경/권한/API 기본 점검
- `./scripts/_internal/sia-notifier-live-quickcheck.command balanced`로 드라이런 검증
- 데이터 저장 경로 권한(`SIGNAL_DB_PATH`)과 로그 디렉터리 권한을 먼저 확인
- Telegram으로 샘플 알림 1회가 오면 상시 실행으로 전환

### 통합 설치 스크립트(가볍게)

현재 macOS 운영은 임시 bootstrap 스크립트보다 아래 조합을 권장합니다.

```bash
cat scripts/_internal/sia-notifier-env.example > ~/.config/sia-notifier/env
./scripts/_internal/sia-notifier-preflight.command
./scripts/_internal/sia-notifier-launchd.command install balanced
```

시장 설정이 필요하면 아래를 추가로 사용합니다.

```bash
./scripts/_internal/sia-market-settings.command
./scripts/_internal/sia-market-tickers.command
```

시장 설정 정책:

- 기본 활성 시장: `US`
- 기본 universe: 시장별 `시가총액 10억달러 이상 대표 종목 seed set`
- 사용자 입력 티커: 기본 universe에 추가
- 필요하면 `SIA_INCLUDE_DEFAULT_UNIVERSE=0`으로 기본 universe를 끌 수 있음

### 초기 셋업 상태 확인 (가볍게)

```bash
ollama list | grep -q "phi3:mini" && echo "phi3:mini: ok" || echo "phi3:mini: missing"
/Users/dohyeon/bin/gh auth status || echo "gh: not logged in"
./scripts/_internal/sia-notifier-live-quickcheck.command balanced
```

GitHub 인증은 아래 1회로 마무리:

```bash
/Users/dohyeon/bin/gh auth login --hostname github.com --git-protocol https --web
```

### 더블클릭 실행 + HTML 보기 (macOS)

이미 저장소에 더블클릭 실행기가 포함되어 있습니다.

- 엔진 실행: `scripts/SIA-Run.command`
- 대시보드: `scripts/SIA-Dashboard.command`
- 리포트 허브: `scripts/SIA-Reports.command`
- 시장 선택: `scripts/SIA-Market-Settings.command`
- 시장별 티커 편집: `scripts/SIA-Market-Tickers.command`

생성되는 주요 HTML:

- `~/Library/Caches/sia-notifier/last-run.html`
- `~/Library/Caches/sia-notifier/dashboard.html`
- `~/Library/Caches/sia-notifier/report-hub.html`

텔레그램 알림 기본 동작

- 텔레그램 알림은 기본 기능으로 항상 포함되어 있음
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`가 없으면 알림은 건너뛰고 `run.log`에 기록만 남김

#### Windows에서도 같은 방식으로 실행(선택)

Windows는 내부 PowerShell 실행기를 직접 사용합니다.

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force
.\scripts\_internal\sia-notifier-launch.ps1
```

현재 Windows 쪽은 macOS의 `SIA-*` 래퍼처럼 상단 사용자용 파일 분리가 적용되어 있지 않고, 내부 실행기 기준으로 유지됩니다.
