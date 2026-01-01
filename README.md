# 업비트 AI 자동 트레이딩 시스템

업비트 API와 Gemini AI를 활용한 자동 거래 시스템입니다.

**⚠️ 주의**: 테스트 중입니다. 거래의 책임은 사용한 본인에게 있으며, 반드시 소액으로만 하시는 것을 추천드립니다. (10만원 이하. 3만원 추천)   
**⚠️ 주의**: 현재 수익률이 좋지 않습니다. 기능 업데이트를 기다렸다가 사용을 권장합니다.
**⚠️ 주의**: 이 시스템은 24시간 자동으로 실행되므로, 저전력 mini PC 사용을 권장합니다.

## 📋 목차

- [소개](#소개)
- [현재 문제점 (업데이트 예정)](#현재-문제점-업데이트-예정)
- [설치 방법](#설치-방법)
- [실행 방법](#실행-방법)
- [주의사항](#주의사항)

## 소개

업비트 API와 Gemini AI를 활용하여 자동으로 암호화폐 거래를 수행하는 시스템입니다.

- Gemini AI가 시장 상황을 분석하여 매수/매도 결정
- Function Calling을 통한 완전 자동화
- 24시간 자동 실행 (가격 저장: 10분 간격, 거래 사이클: 30분 간격)
- 규칙 기반 코인 선택 (매일 자동 실행)
- 가격/거래량/RSI 데이터 수집 및 분석

**문제가 있거나 개선 사항이 있으면 Issue로 남겨주세요. 당분간 PR은 받지 않습니다.**

## 주요 기능

- **자동 거래**: Gemini AI 기반 매수/매도 결정 (30분 간격)
- **코인 선택**: 규칙 기반 자동 코인 선택 (매일 새벽 실행)
- **데이터 수집**: 가격, 거래량, RSI 데이터 자동 수집 (10분 간격)
- **거래 내역**: Function call 실행 내역 자동 저장

## 현재 문제점 (업데이트 예정)

- 거래 내역이 최근 것만 전달되는 문제
- 뉴스 수집 기능 업데이트 예정
- 백테스트 기능 추가
- llm 분석 단계를 세분화(deepseek의 thinking)

## 설치 방법

### 1. Conda 환경 생성 (선택사항)

```bash
conda create -n upbit python=3.10
conda activate upbit
```

### 2. 패키지 설치

```bash
pip install -r requirements.txt
```

**중요**: `google-generativeai` 버전 0.4.0 이상이 필요합니다:

```bash
pip install --upgrade google-generativeai
```

### 3. API 키 설정

`.env` 파일을 생성하고 다음 내용을 추가하세요:

```
UPBIT_ACCESS_KEY=your_access_key_here
UPBIT_SECRET_KEY=your_secret_key_here
GEMINI_API_KEY=your_gemini_api_key_here
```

#### API 키 발급 방법

**업비트 API 키**
1. [업비트](https://upbit.com) 로그인
2. 마이페이지 > Open API 관리
3. API 키 생성 후 Access Key와 Secret Key 복사

**Gemini API 키**
1. [Google AI Studio](https://makersuite.google.com/app/apikey) 접속
2. API 키 생성 후 복사

⚠️ **보안 주의사항**
- API 키는 절대 공개하지 마세요
- `.env` 파일은 Git에 커밋하지 마세요
- IP 제한 설정을 권장합니다

## 실행 방법

### 1. 테스트 실행 (test_llm.py)

LLM 호출을 수동으로 테스트하고 거래를 실행할 수 있습니다:

```bash
python test_llm.py
```

`test_llm.py` 파일에서 모드를 설정할 수 있습니다:
- `show_prompt_only = True`: Prompt만 출력하고 종료
- `skip_trade = True`: LLM 호출까지만 하고 거래는 실행 안 함
- 둘 다 `False`: 전체 실행 (거래 포함)

### 2. 정식 실행 (ai_trader.py)

#### 기본 실행 (자동 모드, 30분 간격)

```bash
python ai_trader.py
```

#### 테스트 모드 (한 번만 실행)

```bash
python ai_trader.py test
# 또는
python ai_trader.py once
```

#### 백그라운드 실행 (24시간 자동 실행)

```bash
nohup python ai_trader.py > ai_trader.log 2>&1 &
```

백그라운드 실행 중지:
```bash
# 프로세스 확인
ps aux | grep ai_trader.py

# 프로세스 종료 (PID 확인 후)
kill <PID>
```

#### 초기 구독 코인 지정

```bash
python ai_trader.py KRW-BTC,KRW-ETH,KRW-XRP
```

## 주의사항

1. **자동 트레이딩은 위험합니다**
   - 실제 자금으로 거래하기 전에 충분히 테스트하세요
   - 손실 가능성을 항상 염두에 두세요
   - **시스템은 사용자 확인 없이 자동으로 거래를 실행합니다**

2. **API 키 보안**
   - API 키는 절대 공개하지 마세요
   - IP 제한 설정을 권장합니다
   - 출금 권한은 제한하는 것을 권장합니다

3. **거래 수수료**
   - 업비트 거래 수수료를 고려하세요
   - 빈번한 거래는 수수료 부담이 큽니다

4. **시장 변동성**
   - 암호화폐 시장은 변동성이 큽니다
   - 전략이 항상 수익을 보장하지는 않습니다
   - AI의 결정이 항상 정확한 것은 아닙니다

5. **테스트**
   - 실제 거래 전에 소액으로 테스트하세요
   - `test_llm.py`로 LLM 응답을 먼저 확인하세요
   - `ai_trader.py test`로 한 번만 실행해보세요

6. **백그라운드 실행**
   - `nohup`으로 실행 시 로그 파일을 확인하세요
   - 프로세스가 정상 실행 중인지 주기적으로 확인하세요
   - `data/llm_history/`에서 AI의 결정을 확인할 수 있습니다

## 📚 참고 자료

- [업비트 API 문서](https://docs.upbit.com/)
- [pyupbit 라이브러리](https://github.com/sharebook-kr/pyupbit)
- [Google Gemini API](https://ai.google.dev/)

## 📄 라이선스

이 프로젝트는 개인 사용 목적으로 제작되었습니다.
