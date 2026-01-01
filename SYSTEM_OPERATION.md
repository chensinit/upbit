# 시스템 동작 방식 설명서

이 문서는 시스템의 동작 방식을 상세히 설명합니다. AI 어시스턴트가 시스템을 이해하고 수정할 때 참고할 용도입니다.

## 전체 구조

### 메인 스케줄러

**통합 스케줄러 (`_unified_scheduler`)**
- **실행 주기**: 10분마다
- **동작**:
  1. 가격 및 거래량 저장 (항상 실행)
  2. 거래 사이클 실행 (3번째마다 = 30분 간격)

**코인 선택 스케줄러 (`_coin_selection_scheduler`)**
- **실행 주기**: 매일 지정된 시간 (기본: 새벽 2시)
- **동작**: 규칙 기반 코인 선택 및 구독 코인 업데이트

## 데이터 수집 및 저장

### 가격 데이터 저장 구조

**3단계 하이브리드 저장 방식**:

1. **`detailed` (10분 간격)**
   - 최근 7일 유지 (RSI 계산을 위해)
   - 저장 항목: `timestamp`, `price`, `volume` (24시간 거래량)
   - 7일 지나면 → `hourly`로 압축

2. **`hourly` (1시간 간격)**
   - 7일~30일 유지
   - 저장 항목: `timestamp`, `open`, `high`, `low`, `close`, `count`, `volume` (평균)
   - 7일 지나면 → `daily`로 압축

3. **`daily` (1일 간격)**
   - 30일 이상 유지
   - 저장 항목: `date`, `open`, `high`, `low`, `close`, `count`

### 데이터 수집 프로세스

**실시간 수집 (10분 간격)**
- `get_current_prices_and_volumes()`: REST API로 가격 + 거래량 조회
- `save_price()`: `detailed`에 저장
- 7일 지난 데이터는 자동으로 `hourly`로 압축

**과거 데이터 수집**
- `fetch_historical_data()`: 새로 구독한 코인에 대해 과거 데이터 수집
  - 일별 데이터: 최근 20일 (RSI 계산용)
  - 시간별 데이터: 최근 3일 (72시간)

## RSI 계산

### 3가지 RSI 제공

1. **RSI(10분)**: `detailed` 데이터 사용, 최근 14개 (140분)
2. **RSI(시간)**: `hourly` 데이터 사용, 최근 14시간
3. **RSI(일)**: `daily` 데이터 사용, 최근 14일 (최소 6일 필요)

### 계산 방식
- 공통 로직: `_calculate_rsi_from_prices()`
- 계산 불가 시: None 반환 (표시하지 않음)
- RSI는 저장하지 않음 (항상 현재 시점 기준으로 계산)

## 거래 사이클

### 실행 주기
- 30분마다 실행 (통합 스케줄러의 3번째 호출)

### 실행 순서

1. **현재 시장 데이터 조회**
   - `get_current_prices_and_volumes()`: 현재가 + 거래량
   - 포트폴리오 정보 조회

2. **가격 추이 정보 생성**
   - `format_multi_trend_for_llm()`: 24시간/15일 가격 추이
   - RSI 정보 포함 (10분/시간/일)
   - 거래량 정보 포함

3. **거래 히스토리 조회**
   - `HistoryManager`: 보유 코인의 최근 거래 내역
   - 최근 15개만 제공

4. **Gemini API 호출**
   - `get_trading_decision()`: 거래 결정 요청
   - Function Calling: `buy_coin`, `sell_coin`

5. **Function Call 실행**
   - `execute_function_calls()`: 거래 실행
   - 거래 실행 내역 저장 (`TradeExecutionHistory`)

## 코인 선택

### 실행 주기
- 매일 지정된 시간 (기본: 새벽 2시)
- `_coin_selection_scheduler`에서 관리

### 선택 로직 (`CoinSelector`)

1. **기본 코인 포함**
   - Pinned 코인 (메이저 코인, `data/pinned_tickers.json`)
   - 현재 보유 코인

2. **필터링**
   - 거래대금 >= 10억원
   - 변동성: 0.01 ~ 0.25

3. **분류**
   - **Momentum**: 변화율 >= +3%
   - **Dip**: -6% <= 변화율 <= 0% AND 변동성 >= 1.5%

4. **최종 선택**
   - Pinned + 보유 + Momentum(5-6개) + Dip(5-6개)
   - 최대 10개

5. **히스토리 저장**
   - `data/coin_selection_history/`에 저장
   - 파일명: `🪙_COIN_SELECTION_YYYYMMDD_HHMMSS.txt`

## 거래 실행 내역 저장

### 저장 위치
- `data/trade_execution_history/execution_history.json`

### 저장 항목
- `timestamp`: 실행 시간
- `function_name`: `buy_coin` 또는 `sell_coin`
- `ticker`: 코인 티커
- `arguments`: 함수 인자
- `success`: 성공 여부
- `result`: 성공 시 결과 (주문 정보)
- `error`: 실패 시 에러 메시지

### 관리
- 최근 1000개만 유지 (메모리 절약)
- Prompt에는 포함하지 않음 (저장만)

## API 호출 및 Rate Limiting

### Rate Limiting 방지
- 모든 REST API 호출 사이에 0.3초 대기
- 적용 위치:
  - `get_current_prices_and_volumes()`: 코인 사이
  - `coin_selector.py`: 배치 API 호출 후
  - `history_manager.py`: 거래 내역 조회 시
  - `price_history_manager.py`: 과거 데이터 수집 시

### 주요 API 호출
- `pyupbit.get_ticker()`: 가격 + 거래량
- `pyupbit.get_ohlcv()`: 과거 OHLC 데이터
- `pyupbit.get_current_price()`: 현재가 (사용 안 함, `get_ticker` 사용)

## 파일 구조

### 데이터 파일
- `data/tickers.json`: 현재 구독 코인 목록
- `data/price_history/{TICKER}.json`: 가격 히스토리
- `data/trade_history.json`: 거래 내역 (업비트 API에서 조회)
- `data/trade_execution_history/execution_history.json`: Function call 실행 내역
- `data/coin_selection_history/`: 코인 선택 히스토리
- `data/llm_history/`: LLM 응답 히스토리
- `data/pinned_tickers.json`: 고정 코인 목록

### 설정 파일
- `.env`: API 키
- `config.json`: 설정 (거래 간격, 코인 선택 시간 등)

## 주요 모듈

### `ai_trader.py`
- 메인 실행 스크립트
- 통합 스케줄러 관리
- 거래 사이클 실행

### `price_history_manager.py`
- 가격 데이터 저장/조회
- RSI 계산
- 데이터 압축 (10분 → 시간 → 일)

### `gemini_client.py`
- Gemini API 호출
- Prompt 생성
- Function Calling 파싱

### `coin_selector.py`
- 규칙 기반 코인 선택
- 시장 데이터 분석

### `trade_execution_history.py`
- 거래 실행 내역 저장/조회

### `history_manager.py`
- 업비트 거래 내역 조회
- Prompt용 포맷팅

## 주의사항

1. **데이터 압축 타이밍**
   - 10분 데이터는 7일 후 압축
   - 시간 데이터는 7일 후 압축
   - 압축은 저장 시점에 자동 실행

2. **RSI 계산**
   - 항상 현재 시점 기준으로 계산
   - 저장하지 않음 (과거 RSI는 의미 없음)

3. **거래 실행**
   - Function call이 없으면 거래하지 않음
   - 검증 실패 시 거래하지 않음

4. **코인 선택**
   - 실행 중에는 가격 저장 스케줄러 일시 중지
   - `is_coin_selection_running` 플래그로 관리

