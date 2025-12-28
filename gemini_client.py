"""
Gemini API 클라이언트
Function Calling을 사용하여 AI 트레이딩 의사결정을 수행합니다.
"""
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from config import GEMINI_API_KEY
from function_tools import (
    get_function_definitions, 
    get_trading_function_definitions,
    get_coin_selection_function_definitions,
    validate_function_call
)
from OpenaiApi import gemini_api


class GeminiClient:
    """Gemini API 클라이언트 클래스"""
    
    def __init__(self, api_key: str = None, system_prompt: str = None, history_dir: str = "data/llm_history"):
        """
        초기화
        
        Args:
            api_key: Gemini API 키 (None이면 config에서 가져오고, 그것도 없으면 OpenaiApi.py의 기본값 사용)
            system_prompt: 시스템 프롬프트 (선택사항)
            history_dir: 응답 히스토리 저장 디렉토리
        """
        # API 키 우선순위: 인자 > config > OpenaiApi.py 기본값
        self.api_key = api_key or GEMINI_API_KEY
        
        # API 키가 없으면 OpenaiApi.py의 기본값 사용 (None으로 전달하면 기본값 사용)
        if not self.api_key:
            print("⚠️  GEMINI_API_KEY가 설정되지 않아 OpenaiApi.py의 기본 키를 사용합니다.")
            self.api_key = None  # None으로 전달하면 OpenaiApi.py가 기본값 사용
        
        # 시스템 프롬프트 설정
        if system_prompt is None:
            system_prompt = "당신은 암호화폐 자동 트레이딩 시스템의 AI 트레이더입니다. 적극적이고 기회를 포착하는 트레이더입니다. 완벽한 확신이 없어도 손익비가 유리한 기회를 놓치지 않습니다."
        
        # 거래용 Gemini 인스턴스 (buy_coin, sell_coin만)
        trading_system_prompt = "당신은 암호화폐 자동 트레이딩 시스템의 AI 트레이더입니다. 적극적으로 기회를 포착하고, 완벽한 확신이 없어도 손익비가 유리한 거래를 실행합니다."
        self.gemini_trading = gemini_api(
            api_key=self.api_key,
            system_prompt=trading_system_prompt,
            tools=get_trading_function_definitions()
        )
        
        # 코인 선택용 Gemini 인스턴스 (update_subscribed_coins만)
        coin_selection_system_prompt = "당신은 암호화폐 자동 트레이딩 시스템의 코인 선택 전문가입니다. 시장 상황과 뉴스를 분석하여 최적의 코인을 선택합니다."
        self.gemini_coin_selection = gemini_api(
            api_key=self.api_key,
            system_prompt=coin_selection_system_prompt,
            tools=get_coin_selection_function_definitions()
        )
        
        # 호환성을 위해 기존 gemini도 유지 (전체 함수)
        self.gemini = gemini_api(
            api_key=self.api_key,
            system_prompt=system_prompt,
            tools=get_function_definitions()
        )
        
        self.max_retries = 3
        self.retry_delay = 2  # 재시도 간격 (초)
        
        # 히스토리 저장 디렉토리 설정
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        print("✅ Gemini API 클라이언트 초기화 완료 (OpenaiApi.py 사용)")
    
    def _retry_with_backoff(self, func, *args, **kwargs) -> Tuple[bool, Optional[any], str]:
        """
        함수를 최대 3회까지 재시도
        
        Args:
            func: 실행할 함수
            *args, **kwargs: 함수 인자
            
        Returns:
            (성공 여부, 결과, 에러 메시지)
        """
        last_error = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                return True, result, ""
            
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    print(f"⚠️  Gemini API 시도 {attempt}/{self.max_retries} 실패, {self.retry_delay}초 후 재시도...")
                    time.sleep(self.retry_delay * attempt)
                else:
                    print(f"❌ Gemini API 모든 재시도 실패: {last_error}")
        
        return False, None, last_error or "알 수 없는 오류"
    
    def _extract_json_from_text(self, text: str) -> Optional[Dict]:
        """
        텍스트에서 JSON 코드 블록 추출
        
        Args:
            text: JSON 코드 블록이 포함된 텍스트
            
        Returns:
            파싱된 JSON 딕셔너리 (없으면 None)
        """
        if not text:
            return None
        
        # 다양한 백틱 문자 패턴 (일반 백틱, 유니코드 백틱 등)
        # ```json ... ``` 또는 ``` ... ``` 형태
        patterns = [
            r'```\s*json\s*\n(.*?)\n```',  # ```json ... ```
            r'```\s*\n(.*?)\n```',  # ``` ... ```
            r'`\s*json\s*\n(.*?)\n`',  # `json ... `
            r'`\s*\n(.*?)\n`',  # ` ... `
            # 유니코드 백틱 변형들
            r'[`'']\s*json\s*\n(.*?)\n[`'']',  # 다양한 백틱 + json
            r'[`'']\s*\n(.*?)\n[`'']',  # 다양한 백틱
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    json_str = match.strip()
                    # JSON 파싱 시도
                    data = json.loads(json_str)
                    return data
                except json.JSONDecodeError:
                    continue
        
        # 코드 블록이 없으면 전체 텍스트를 JSON으로 시도
        try:
            # 중괄호로 시작하고 끝나는 부분 찾기
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                return data
        except json.JSONDecodeError:
            pass
        
        return None
    
    def _normalize_function_args(self, func_name: str, func_args: Dict) -> Dict:
        """
        함수 인자를 정규화 (다양한 키 이름을 표준 형식으로 변환)
        
        Args:
            func_name: 함수 이름
            func_args: 함수 인자 딕셔너리
            
        Returns:
            정규화된 함수 인자 딕셔너리
        """
        normalized = func_args.copy()
        
        if func_name == "buy_coin":
            # ticker 변환: coin_type, coin_symbol, coin -> ticker
            if "coin_type" in normalized and "ticker" not in normalized:
                normalized["ticker"] = normalized.pop("coin_type")
            elif "coin_symbol" in normalized and "ticker" not in normalized:
                normalized["ticker"] = normalized.pop("coin_symbol")
            elif "coin" in normalized and "ticker" not in normalized:
                normalized["ticker"] = normalized.pop("coin")
            
            # amount 변환: volume -> amount (buy_coin의 경우)
            if "volume" in normalized and "amount" not in normalized:
                normalized["amount"] = normalized.pop("volume")
            
            # price는 제거 (필요 없음)
            if "price" in normalized:
                normalized.pop("price")
        
        elif func_name == "sell_coin":
            # ticker 변환: coin_type, coin_symbol, coin -> ticker
            if "coin_type" in normalized and "ticker" not in normalized:
                normalized["ticker"] = normalized.pop("coin_type")
            elif "coin_symbol" in normalized and "ticker" not in normalized:
                normalized["ticker"] = normalized.pop("coin_symbol")
            elif "coin" in normalized and "ticker" not in normalized:
                normalized["ticker"] = normalized.pop("coin")
            
            # price는 제거 (필요 없음)
            if "price" in normalized:
                normalized.pop("price")
        
        return normalized
    
    def _parse_text_response(self, response_text: str) -> List[Dict]:
        """
        텍스트 응답에서 함수 호출 정보 파싱
        
        Args:
            response_text: LLM의 텍스트 응답
            
        Returns:
            함수 호출 리스트
        """
        function_calls = []
        
        # JSON 코드 블록에서 추출
        json_data = self._extract_json_from_text(response_text)
        
        if json_data:
            # 단일 함수 호출
            if isinstance(json_data, dict):
                # "trades" 또는 "actions" 배열 형식 처리 (LLM이 반환하는 형식)
                trades_or_actions = json_data.get("trades") or json_data.get("actions")
                if trades_or_actions and isinstance(trades_or_actions, list):
                    for trade in trades_or_actions:
                        if isinstance(trade, dict):
                            func_name = trade.get("function") or trade.get("name")
                            # "parameters" 또는 "arguments" 또는 "args" 키 확인
                            func_args = (trade.get("parameters") or 
                                       trade.get("arguments") or 
                                       trade.get("args") or {})
                            if func_name:
                                # 인자 정규화 (coin/coin_symbol -> ticker 변환)
                                normalized_args = self._normalize_function_args(func_name, func_args)
                                function_calls.append({
                                    "name": func_name,
                                    "arguments": normalized_args
                                })
                # 단일 함수 호출 (function/name 키가 직접 있는 경우)
                elif "function" in json_data or "name" in json_data:
                    func_name = json_data.get("function") or json_data.get("name")
                    func_args = (json_data.get("parameters") or 
                               json_data.get("arguments") or 
                               json_data.get("args") or {})
                    
                    if func_name:
                        # 인자 정규화 (coin -> ticker 변환)
                        normalized_args = self._normalize_function_args(func_name, func_args)
                        function_calls.append({
                            "name": func_name,
                            "arguments": normalized_args
                        })
                # 여러 함수 호출이 배열로 있는 경우
                elif "calls" in json_data or isinstance(json_data.get("functions"), list):
                    calls = json_data.get("calls") or json_data.get("functions") or []
                    for call in calls:
                        if isinstance(call, dict):
                            func_name = call.get("function") or call.get("name")
                            func_args = (call.get("parameters") or 
                                       call.get("arguments") or 
                                       call.get("args") or {})
                            if func_name:
                                # 인자 정규화 (coin -> ticker 변환)
                                normalized_args = self._normalize_function_args(func_name, func_args)
                                function_calls.append({
                                    "name": func_name,
                                    "arguments": normalized_args
                                })
            
            # 배열로 직접 함수 호출이 있는 경우
            elif isinstance(json_data, list):
                for item in json_data:
                    if isinstance(item, dict):
                        func_name = item.get("function") or item.get("name")
                        func_args = (item.get("parameters") or 
                                   item.get("arguments") or 
                                   item.get("args") or {})
                        if func_name:
                            # 인자 정규화 (coin -> ticker 변환)
                            normalized_args = self._normalize_function_args(func_name, func_args)
                            function_calls.append({
                                "name": func_name,
                                "arguments": normalized_args
                            })
        
        return function_calls
    
    def _save_response_history(self, prompt: str, response_text: str, 
                               function_calls: List[Dict], 
                               current_prices: Dict[str, float]) -> bool:
        """
        LLM 응답 히스토리 저장 (텍스트 형식)
        
        Args:
            prompt: 전송한 프롬프트
            response_text: LLM 응답 텍스트
            function_calls: 파싱된 함수 호출 리스트
            current_prices: 현재 가격 딕셔너리
            
        Returns:
            저장 성공 여부
        """
        try:
            timestamp = datetime.now()
            filename = timestamp.strftime("%Y%m%d_%H%M%S") + ".txt"
            filepath = self.history_dir / filename
            
            # 텍스트 형식으로 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                # Prompt 섹션
                f.write("prompt\n")
                f.write("=" * 80 + "\n")
                f.write(prompt)
                f.write("\n\n")
                
                # LLM Response 섹션
                f.write("llm response\n")
                f.write("=" * 80 + "\n")
                f.write(response_text)
                f.write("\n\n")
                
                # Function Calls 정보 (있는 경우)
                if function_calls:
                    f.write("function calls\n")
                    f.write("=" * 80 + "\n")
                    for i, func_call in enumerate(function_calls, 1):
                        f.write(f"{i}. {func_call.get('name', 'unknown')}\n")
                        f.write(f"   Arguments: {json.dumps(func_call.get('arguments', {}), ensure_ascii=False, indent=2)}\n")
                    f.write("\n")
                
                # 메타 정보
                f.write("metadata\n")
                f.write("=" * 80 + "\n")
                f.write(f"Timestamp: {timestamp.isoformat()}\n")
                f.write(f"Function Calls Count: {len(function_calls)}\n")
                f.write(f"Current Prices Count: {len(current_prices)}\n")
            
            print(f"💾 LLM 응답 히스토리 저장: {filename}")
            return True
        
        except Exception as e:
            print(f"⚠️  히스토리 저장 실패: {e}")
            return False
    
    def build_trading_prompt(self, current_prices: Dict[str, float], 
                             portfolio_info: str, 
                             trade_history: str,
                             price_trends: str = "") -> str:
        """
        거래 결정용 프롬프트 생성 (buy_coin, sell_coin만)
        
        Args:
            current_prices: 현재 가격 딕셔너리 {ticker: price}
            portfolio_info: 포트폴리오 정보 문자열
            trade_history: 거래 히스토리 문자열
            price_trends: 가격 변화 추이 문자열 (선택사항)
            
        Returns:
            프롬프트 문자열
        """
        prices_text = "\n".join([f"- {ticker}: {price:,.0f}원" for ticker, price in current_prices.items()])
        
        # price_trends에 중괄호가 있을 수 있으므로 f-string 대신 format 사용
        price_trends_section = price_trends if price_trends else ""
        
        prompt = """당신은 경험이 풍부한 암호화폐 전문 트레이더이자 리스크 관리자입니다.
데이터 기반의 논리적 분석을 통해 신중하지만 기회를 놓치지 않는 판단을 합니다.

입력으로 주어진 코인 가격 정보와 추이를 기반으로 논리적 Reasoning 과정을 거쳐
매수(BUY) / 매도(SELL) / 보유(HOLD) / 관망(PASS) 중 하나를 결정하세요.

기술적 가격 흐름, 추세, 지표 해석을 스스로 Reasoning하여 판단하세요.
"조건식 평가"가 아니라 "맥락 기반 판단"을 수행하세요.

## 현재 시장 상황

### 구독 중인 코인 현재가
{0}

{1}

## 내 계좌 정보
{2}

## 거래 히스토리
{3}

-----------------------------
📌 필수 안전조건 (반드시 준수)
-----------------------------

1. **과열 구간 매수 금지**
   - RSI > 70인 경우 BUY 금지 (과열 구간은 매수하지 않음)
   - 가격이 급등한 직후는 신중하게 판단

2. **리스크 관리 필수**
   - 모든 매매 결정에는 손익비를 고려하세요
   - 불확실하거나 판단 근거가 부족하면 PASS를 선택할 수 있습니다
   - PASS는 허용되는 선택입니다

3. **과도한 거래 방지**
   - 하루 신규 매수 종목 수를 과도하게 제시하지 마세요
   - 필요하다면 소수의 기회만 선택하세요
   - 한 번에 너무 많은 거래를 하지 마세요

4. **기술적 제약**
   - 최소 매수 금액: 10000원
   - 최소 매도 금액: 5000원
   - 시장가 거래만 가능
   - 코인 구독 변경은 이 프롬프트에서 하지 마세요

-----------------------------
📌 자유 판단 영역 (LLM이 Reasoning 기반으로 스스로 판단)
-----------------------------

다음 요소들을 종합적으로 분석하여 판단하세요:

1. **추세 해석**
   - 상승/하락/횡보 추세를 가격 추이를 통해 판단
   - 단기/중기/장기 추세의 일관성 분석

2. **이동평균 관계 분석**
   - 가격 추이에서 단기/중기 이동평균 관계 파악
   - 골든크로스/데드크로스 패턴 인식

3. **과매도 기회 판단**
   - 가격이 급락한 후 반등 가능성 평가
   - 변동성과 함께 고려한 진입 타이밍

4. **거래량 변화 해석**
   - 가격 변화와 거래량의 관계 분석
   - 거래량 급증/감소의 의미 해석

5. **변동성 기반 리스크 평가**
   - 변동성이 높은 코인은 신중하게 접근
   - 리스크 대비 수익 가능성 평가

6. **추가 전략 제안**
   - 진입/익절/청산 타이밍 제안
   - 포지션 크기 조절 전략

## 지시사항

1. 위 정보를 종합적으로 분석하여 논리적 Reasoning을 수행하세요.
2. **맥락 기반 판단**: 단순 조건식이 아닌 전체적인 맥락을 고려하세요.
3. **판단 근거 명확화**: 왜 그런 결정을 내렸는지 논리적으로 설명할 수 있어야 합니다.
4. 거래가 필요하다고 판단되면 **buy_coin 또는 sell_coin 함수**를 사용하세요.
5. **불확실하면 PASS**: 판단 근거가 부족하거나 불확실하면 거래하지 않아도 됩니다.

## 응답 형식

함수 호출 시 각 거래에 대한 이유를 명확히 하세요.

### Function Calling 사용
거래가 필요할 경우 **buy_coin** 또는 **sell_coin** 함수를 호출하세요.

### 주의사항
- `ticker`는 반드시 "KRW-"로 시작해야 합니다.
- `buy_coin`의 `amount`는 최소 5000원 이상이어야 합니다.
- `sell_coin`의 `volume`은 "all" 또는 숫자 문자열 (예: "0.001")입니다.
- 거래가 필요하지 않으면 함수를 호출하지 않아도 됩니다.
""".format(
            prices_text,
            price_trends_section,
            portfolio_info,
            trade_history
        )
        
        return prompt
    
    def build_coin_selection_prompt(self, available_coins: List[str],
                                     current_subscribed: List[str],
                                     coin_info: str = "") -> str:
        """
        코인 선택용 프롬프트 생성 (update_subscribed_coins만)
        
        Args:
            available_coins: 선택 가능한 코인 리스트 (예: 시가총액 상위 코인들)
            current_subscribed: 현재 구독 중인 코인 리스트
            coin_info: 코인별 정보 (뉴스, 가격 추이 등, 선택사항)
            
        Returns:
            프롬프트 문자열
        """
        available_text = "\n".join([f"- {coin}" for coin in available_coins])
        subscribed_text = ", ".join(current_subscribed) if current_subscribed else "없음"
        
        prompt = f"""당신은 암호화폐 자동 트레이딩 시스템의 코인 선택 전문가입니다.
시장 상황, 뉴스, 트렌드를 분석하여 최적의 코인을 선택합니다.

## 선택 가능한 코인 목록
{available_text}

## 현재 구독 중인 코인
{subscribed_text}

{coin_info if coin_info else ""}

## 코인 선택 전략

1. **시가총액과 거래량 고려**
   - 시가총액이 높고 거래량이 활발한 코인 우선
   - 너무 작은 코인은 변동성이 크므로 주의

2. **최근 뉴스와 트렌드 분석**
   - 긍정적인 뉴스가 있는 코인 우선
   - 기술적 발전이나 파트너십 발표 등 주목

3. **다양성 유지**
   - 한 종류의 코인에 집중하지 말고 분산
   - 최대 10개까지 구독 가능

4. **현재 보유 코인 고려**
   - 이미 보유 중인 코인은 유지 고려
   - 새로운 기회가 있으면 교체 가능

## 지시사항

1. 위 정보를 분석하여 구독할 코인 목록을 결정하세요.
2. **update_subscribed_coins 함수만** 사용하여 코인 목록을 업데이트하세요.
3. 최대 10개까지 선택 가능합니다.
4. 현재 구독 중인 코인을 유지할지, 새로운 코인으로 교체할지 판단하세요.
5. 명확한 이유 없이 자주 변경하지 마세요.

## 주의사항

- 모든 티커는 KRW-로 시작해야 합니다.
- 최대 10개까지 구독 가능합니다.
- 이 프롬프트는 코인 선택만을 위한 것입니다. 거래는 하지 마세요.

JSON 형식으로 응답하되, 함수 호출이 필요한 경우에만 함수를 호출하세요.
"""
        
        return prompt
    
    def build_prompt(self, current_prices: Dict[str, float], 
                     portfolio_info: str, 
                     trade_history: str) -> str:
        """
        기존 호환성을 위한 프롬프트 생성 (deprecated, build_trading_prompt 사용 권장)
        """
        return self.build_trading_prompt(current_prices, portfolio_info, trade_history)
    
    def get_trading_decision(self, current_prices: Dict[str, float],
                           portfolio_info: str,
                           trade_history: str,
                           price_trends: str = "") -> Tuple[bool, List[Dict], str]:
        """
        Gemini API로 트레이딩 결정 요청 (거래 전용: buy_coin, sell_coin만)
        
        Args:
            current_prices: 현재 가격 딕셔너리
            portfolio_info: 포트폴리오 정보
            trade_history: 거래 히스토리
            price_trends: 가격 변화 추이 (선택사항)
            
        Returns:
            (성공 여부, 함수 호출 리스트, 에러 메시지)
        """
        prompt = self.build_trading_prompt(current_prices, portfolio_info, trade_history, price_trends)
        
        print("\n" + "="*60)
        print("🤖 Gemini API에 트레이딩 결정 요청 중... (거래 전용)")
        print("="*60)
        
        # 거래용 Gemini 인스턴스 사용
        success, response, error = self._retry_with_backoff(
            self.gemini_trading.get_response,
            prompt
        )
        
        if not success:
            print(f"❌ API 호출 실패: {error}")
            return False, [], error
        
        # 응답 로그 출력
        print("\n" + "-"*60)
        print("📥 Gemini API 응답 로그")
        print("-"*60)
        
        if response is None:
            print("❌ 응답이 None입니다.")
            return False, [], "응답이 None입니다."
        
        # 텍스트 응답 확인 및 출력 (한번만)
        try:
            response_text = response.text if hasattr(response, 'text') else str(response)
            print(f"\n📝 응답 텍스트:")
            print(response_text)
            print("-"*60)
        except Exception as e:
            print(f"⚠️  텍스트 추출 실패: {e}")
            response_text = ""
        
        # Function calling 결과 파싱
        function_calls = []
        
        try:
            # Function calling 파싱
            if hasattr(response, 'candidates'):
                candidates = response.candidates
                if candidates is not None and len(candidates) > 0:
                    candidate = candidates[0]
                    if hasattr(candidate, 'content'):
                        content = candidate.content
                        if hasattr(content, 'parts'):
                            parts = content.parts
                            if parts is not None:
                                for part in parts:
                                    if hasattr(part, 'function_call'):
                                        func_call = part.function_call
                                        try:
                                            function_calls.append({
                                                "name": func_call.name,
                                                "arguments": dict(func_call.args)
                                            })
                                        except Exception as e:
                                            print(f"⚠️  function_call 파싱 실패: {e}")
            
            # Function calling이 없으면 텍스트에서 JSON 파싱 시도
            if not function_calls and response_text:
                print(f"\n🔍 텍스트에서 JSON 파싱 시도...")
                text_function_calls = self._parse_text_response(response_text)
                if text_function_calls:
                    function_calls.extend(text_function_calls)
                    print(f"📝 텍스트 응답에서 함수 호출 {len(text_function_calls)}개 발견")
                else:
                    print("⚪️  텍스트에서 함수 호출을 찾을 수 없습니다.")
            
            # 거래 함수만 필터링 (buy_coin, sell_coin만)
            trading_functions = ["buy_coin", "sell_coin"]
            filtered_calls = [fc for fc in function_calls if fc.get("name") in trading_functions]
            
            if filtered_calls != function_calls:
                removed = [fc for fc in function_calls if fc.get("name") not in trading_functions]
                if removed:
                    print(f"⚠️  거래 함수가 아닌 호출 제거: {[fc['name'] for fc in removed]}")
            
            if filtered_calls:
                print(f"📞 총 거래 함수 호출 {len(filtered_calls)}개 발견")
                for fc in filtered_calls:
                    print(f"   - {fc['name']}: {fc['arguments']}")
            else:
                print("⚪️  거래 결정 없음 (현재 상태 유지)")
            
            # 응답 히스토리 저장
            self._save_response_history(
                prompt=prompt,
                response_text=response_text,
                function_calls=filtered_calls,
                current_prices=current_prices
            )
        
        except Exception as e:
            print(f"⚠️  응답 파싱 오류: {e}")
            return False, [], str(e)
        
        return True, filtered_calls, ""
    
    def get_coin_selection_decision(self, available_coins: List[str],
                                   current_subscribed: List[str],
                                   coin_info: str = "") -> Tuple[bool, List[Dict], str]:
        """
        Gemini API로 코인 선택 결정 요청 (코인 구독 변경 전용: update_subscribed_coins만)
        
        Args:
            available_coins: 선택 가능한 코인 리스트
            current_subscribed: 현재 구독 중인 코인 리스트
            coin_info: 코인별 정보 (뉴스, 가격 추이 등, 선택사항)
            
        Returns:
            (성공 여부, 함수 호출 리스트, 에러 메시지)
        """
        prompt = self.build_coin_selection_prompt(available_coins, current_subscribed, coin_info)
        
        print("\n" + "="*60)
        print("🤖 Gemini API에 코인 선택 결정 요청 중... (코인 구독 변경 전용)")
        print("="*60)
        
        # 코인 선택용 Gemini 인스턴스 사용
        success, response, error = self._retry_with_backoff(
            self.gemini_coin_selection.get_response,
            prompt
        )
        
        if not success:
            print(f"❌ API 호출 실패: {error}")
            return False, [], error
        
        # 응답 로그 출력
        print("\n" + "-"*60)
        print("📥 Gemini API 응답 로그")
        print("-"*60)
        
        if response is None:
            print("❌ 응답이 None입니다.")
            return False, [], "응답이 None입니다."
        
        # 텍스트 응답 확인 및 출력 (한번만)
        try:
            response_text = response.text if hasattr(response, 'text') else str(response)
            print(f"\n📝 응답 텍스트:")
            print(response_text)
            print("-"*60)
        except Exception as e:
            print(f"⚠️  텍스트 추출 실패: {e}")
            response_text = ""
        
        # Function calling 결과 파싱
        function_calls = []
        
        try:
            # Function calling 파싱
            if hasattr(response, 'candidates'):
                candidates = response.candidates
                if candidates is not None and len(candidates) > 0:
                    candidate = candidates[0]
                    if hasattr(candidate, 'content'):
                        content = candidate.content
                        if hasattr(content, 'parts'):
                            parts = content.parts
                            if parts is not None:
                                for part in parts:
                                    if hasattr(part, 'function_call'):
                                        func_call = part.function_call
                                        try:
                                            function_calls.append({
                                                "name": func_call.name,
                                                "arguments": dict(func_call.args)
                                            })
                                        except Exception as e:
                                            print(f"⚠️  function_call 파싱 실패: {e}")
            
            # Function calling이 없으면 텍스트에서 JSON 파싱 시도
            if not function_calls and response_text:
                print(f"\n🔍 텍스트에서 JSON 파싱 시도...")
                text_function_calls = self._parse_text_response(response_text)
                if text_function_calls:
                    function_calls.extend(text_function_calls)
                    print(f"📝 텍스트 응답에서 함수 호출 {len(text_function_calls)}개 발견")
            
            # 코인 선택 함수만 필터링 (update_subscribed_coins만)
            coin_selection_functions = ["update_subscribed_coins"]
            filtered_calls = [fc for fc in function_calls if fc.get("name") in coin_selection_functions]
            
            if filtered_calls != function_calls:
                removed = [fc for fc in function_calls if fc.get("name") not in coin_selection_functions]
                if removed:
                    print(f"⚠️  코인 선택 함수가 아닌 호출 제거: {[fc['name'] for fc in removed]}")
            
            if filtered_calls:
                print(f"📞 총 코인 선택 함수 호출 {len(filtered_calls)}개 발견")
                for fc in filtered_calls:
                    print(f"   - {fc['name']}: {fc['arguments']}")
            else:
                print("⚪️  코인 선택 결정 없음 (현재 구독 유지)")
            
            # 응답 히스토리 저장 (코인 정보 포함)
            history_data = {
                "available_coins": available_coins,
                "current_subscribed": current_subscribed,
                "coin_info": coin_info
            }
            self._save_response_history(
                prompt=prompt,
                response_text=response_text,
                function_calls=filtered_calls,
                current_prices=history_data  # 가격 대신 코인 정보 저장
            )
        
        except Exception as e:
            print(f"⚠️  응답 파싱 오류: {e}")
            return False, [], str(e)
        
        return True, filtered_calls, ""
    
    def validate_and_parse_function_call(self, function_call: Dict) -> Tuple[bool, str, Dict]:
        """
        Function call 검증 및 파싱
        
        Args:
            function_call: 함수 호출 딕셔너리
            
        Returns:
            (검증 성공 여부, 에러 메시지, 파싱된 인자)
        """
        name = function_call.get("name", "")
        arguments = function_call.get("arguments", {})
        
        # 검증
        is_valid, error_msg = validate_function_call(name, arguments)
        
        if not is_valid:
            return False, error_msg, {}
        
        return True, "", arguments

