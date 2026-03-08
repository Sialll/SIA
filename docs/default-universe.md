# SIA 기본 유니버스 문서

## 목적

현재 기본 유니버스는 `시가총액 10억달러(USD 1B, 약 1.4조원) 이상` 범주의 대표 종목 seed set입니다.

중요:

- 이 목록은 `전종목 전체`가 아닙니다.
- 무료 데이터 경로로 바로 운영 가능한 크기로 줄인 `seed universe`입니다.
- 실제 운영에서는 이 기본 목록 위에 사용자가 티커를 추가하는 구조입니다.

## 현재 기준

- 기본 활성 시장: `US`
- 다른 시장은 사용자가 직접 켜야 기본 유니버스가 붙습니다.
- 기본 유니버스 포함 여부:
  - env: `SIA_INCLUDE_DEFAULT_UNIVERSE=1`
  - 끄려면: `SIA_INCLUDE_DEFAULT_UNIVERSE=0`

## 시장별 기본 유니버스

### US

- `AAPL`
- `MSFT`
- `NVDA`
- `AMZN`
- `GOOGL`
- `META`
- `AVGO`
- `TSLA`
- `JPM`
- `V`
- `MA`
- `COST`
- `NFLX`
- `AMD`
- `XOM`
- `CVX`
- `KO`
- `PEP`

### KR

- `005930.KS`
- `000660.KS`
- `035420.KS`
- `005380.KS`
- `207940.KS`
- `068270.KS`
- `105560.KS`
- `055550.KS`

### EU

- `ASML.AS`
- `SAP.DE`
- `SHEL.L`
- `NOVO-B.CO`
- `MC.PA`
- `OR.PA`
- `SAN.MC`
- `AZN.L`

### JP

- `7203.T`
- `6758.T`
- `9984.T`
- `8306.T`
- `8035.T`
- `9432.T`
- `8058.T`
- `6861.T`

## 사용자 추가 방식

사용자 티커는 시장별 env 값으로 추가합니다.

- `TICKERS_US`
- `TICKERS_KR`
- `TICKERS_EU`
- `TICKERS_JP`

합성 규칙:

- 기본 유니버스 `ON`: `기본 seed universe + 사용자 추가 티커`
- 기본 유니버스 `OFF`: `사용자 추가 티커만`

## 현재 한계

- 아직 `전 시장 1B+ 전종목 자동 수집`은 아닙니다.
- 현재는 `seed universe`만 코드에 고정되어 있습니다.
- 향후 전체 확장은 `daily universe collector`가 담당해야 합니다.

## 다음 단계

다음 단계는 아래 순서가 맞습니다.

1. 시장별 read-only 시총 데이터 공급자 연결
2. 일 단위 universe snapshot 생성
3. `USD 1B floor` 필터 적용
4. 기본 seed universe와 비교/검증
5. 운영용 활성 watchlist와 리서치용 전체 universe 분리
