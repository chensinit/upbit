"""
Function Calling 스키마 정의
Gemini API에서 사용할 함수 정의
"""
from typing import List, Dict, Tuple


def get_function_definitions() -> List[Dict]:
    """
    Gemini API에 전달할 Function Calling 스키마 (전체)
    
    Returns:
        Function 정의 리스트
    """
    return get_trading_function_definitions() + get_coin_selection_function_definitions()


def get_trading_function_definitions() -> List[Dict]:
    """
    거래용 Function Calling 스키마 (buy_coin, sell_coin만)
    
    Returns:
        거래 함수 정의 리스트
    """
    return [
        {
            "name": "buy_coin",
            "description": "코인을 시장가로 매수합니다. 잔고를 확인하고 거래를 실행합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "매수할 코인 티커 (예: KRW-BTC, KRW-ETH)"
                    },
                    "amount": {
                        "type": "number",
                        "description": "매수할 금액 (원화, 최소 5000원 이상)"
                    }
                },
                "required": ["ticker", "amount"]
            }
        },
        {
            "name": "sell_coin",
            "description": "보유한 코인을 시장가로 매도합니다. 보유 수량을 확인하고 거래를 실행합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {
                        "type": "string",
                        "description": "매도할 코인 티커 (예: KRW-BTC, KRW-ETH)"
                    },
                    "volume": {
                        "type": "string",
                        "description": "매도 수량. 'all' 또는 숫자 (예: 'all', '0.001')"
                    }
                },
                "required": ["ticker", "volume"]
            }
        }
    ]


def get_coin_selection_function_definitions() -> List[Dict]:
    """
    코인 선택용 Function Calling 스키마 (update_subscribed_coins만)
    
    Returns:
        코인 선택 함수 정의 리스트
    """
    return [
        {
            "name": "update_subscribed_coins",
            "description": "실시간 가격을 구독할 코인 목록을 변경합니다. 최대 10개까지 구독 가능합니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "구독할 코인 티커 리스트 (예: ['KRW-BTC', 'KRW-ETH'])"
                    }
                },
                "required": ["tickers"]
            }
        }
    ]


def validate_function_call(function_name: str, arguments: Dict) -> Tuple[bool, str]:
    """
    Function call 파라미터 검증
    
    Args:
        function_name: 함수 이름
        arguments: 함수 인자
        
    Returns:
        (검증 성공 여부, 에러 메시지)
    """
    if function_name == "buy_coin":
        if "ticker" not in arguments or "amount" not in arguments:
            return False, "ticker와 amount가 필요합니다."
        if not arguments["ticker"].startswith("KRW-"):
            return False, "티커는 KRW-로 시작해야 합니다."
        if arguments["amount"] < 5000:
            return False, "최소 매수 금액은 5000원입니다."
        return True, ""
    
    elif function_name == "sell_coin":
        if "ticker" not in arguments or "volume" not in arguments:
            return False, "ticker와 volume이 필요합니다."
        if not arguments["ticker"].startswith("KRW-"):
            return False, "티커는 KRW-로 시작해야 합니다."
        return True, ""
    
    elif function_name == "update_subscribed_coins":
        if "tickers" not in arguments:
            return False, "tickers가 필요합니다."
        if not isinstance(arguments["tickers"], list):
            return False, "tickers는 리스트여야 합니다."
        if len(arguments["tickers"]) > 10:
            return False, "최대 10개까지 구독 가능합니다."
        for ticker in arguments["tickers"]:
            if not ticker.startswith("KRW-"):
                return False, f"티커 {ticker}는 KRW-로 시작해야 합니다."
        return True, ""
    
    return False, f"알 수 없는 함수: {function_name}"

