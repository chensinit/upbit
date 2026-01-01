"""
거래 실행 헬퍼 함수
공통 거래 실행 로직을 제공합니다.
"""
from typing import Dict, List, Optional
from trading_executor import TradingExecutor
from gemini_client import GeminiClient
from config_manager import ConfigManager
from trade_execution_history import TradeExecutionHistory


def execute_function_calls(function_calls: List[Dict],
                          executor: TradingExecutor,
                          gemini_client: GeminiClient,
                          config_manager: ConfigManager = None,
                          execution_history: Optional[TradeExecutionHistory] = None) -> None:
    """
    함수 호출 리스트를 실행합니다.
    
    Args:
        function_calls: 함수 호출 리스트
        executor: TradingExecutor 인스턴스
        gemini_client: GeminiClient 인스턴스
        config_manager: ConfigManager 인스턴스 (update_subscribed_coins 사용 시 필요)
    """
    for fc in function_calls:
        name = fc.get("name", "")
        arguments = fc.get("arguments", {})
        
        # 검증
        is_valid, error_msg, parsed_args = gemini_client.validate_and_parse_function_call(fc)
        
        if not is_valid:
            print(f"❌ 함수 호출 검증 실패 ({name}): {error_msg}")
            continue
        
        print(f"\n🔧 함수 실행: {name}")
        print(f"   인자: {parsed_args}")
        
        try:
            if name == "buy_coin":
                ticker = parsed_args["ticker"]
                amount = float(parsed_args["amount"])
                success, result, error = executor.execute_buy(ticker, amount)
                
                if success:
                    print(f"✅ 매수 성공: {ticker}, {amount:,.0f}원")
                else:
                    print(f"❌ 매수 실패: {error}")
                
                # 거래 내역 저장
                if execution_history:
                    execution_history.save_execution(
                        function_name=name,
                        ticker=ticker,
                        arguments=parsed_args,
                        success=success,
                        result=result if success else None,
                        error=error if not success else None
                    )
            
            elif name == "sell_coin":
                ticker = parsed_args["ticker"]
                volume = str(parsed_args["volume"])
                success, result, error = executor.execute_sell(ticker, volume)
                
                if success:
                    print(f"✅ 매도 성공: {ticker}, {volume}")
                else:
                    print(f"❌ 매도 실패: {error}")
                
                # 거래 내역 저장
                if execution_history:
                    execution_history.save_execution(
                        function_name=name,
                        ticker=ticker,
                        arguments=parsed_args,
                        success=success,
                        result=result if success else None,
                        error=error if not success else None
                    )
            
            elif name == "update_subscribed_coins":
                if config_manager is None:
                    print("❌ ConfigManager가 필요합니다.")
                    continue
                
                new_tickers = parsed_args["tickers"]
                config_manager.save_tickers(new_tickers)
                print(f"✅ 구독 코인 업데이트: {', '.join(new_tickers)}")
            
            else:
                print(f"⚠️  알 수 없는 함수: {name}")
        
        except Exception as e:
            print(f"❌ 함수 실행 오류 ({name}): {e}")
            import traceback
            traceback.print_exc()

