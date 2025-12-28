"""
LLM 응답 테스트 스크립트
수동으로 1회 호출하여 테스트할 수 있습니다.
"""
from gemini_client import GeminiClient
from upbit_trader import UpbitTrader
from history_manager import HistoryManager
from config_manager import ConfigManager
from price_subscriber import get_current_prices
from trading_executor import TradingExecutor
from trade_executor_helper import execute_function_calls
from price_history_manager import PriceHistoryManager


def test_llm_call():
    """LLM 호출 테스트"""
    # 모드 설정 (bool 변수 2개로 3가지 모드 선택)
    show_prompt_only = True  # True: prompt만 출력하고 종료
    skip_trade = False        # True: LLM 호출까지만 하고 거래는 실행 안 함
    
    print("="*60)
    print("🧪 LLM 응답 테스트")
    print("="*60)
    
    if show_prompt_only:
        print("📝 모드: Prompt 출력만")
    elif skip_trade:
        print("🤖 모드: LLM 호출 및 응답 출력 (거래 제외)")
    else:
        print("⚙️  모드: 전체 실행 (거래 포함)")
    print("="*60)
    
    try:
        # 설정 매니저 초기화
        config_manager = ConfigManager()
        
        # 구독 코인 목록 로드 (파일이 없으면 메이저 코인으로 자동 생성)
        print("\n📂 구독 코인 목록 로드 중...")
        tickers = config_manager.load_tickers()
        
        print(f"📌 구독 코인: {', '.join(tickers)}")
        
        # 트레이더 및 히스토리 매니저 초기화
        print("\n📊 계정 정보 조회 중...")
        trader = UpbitTrader()
        executor = TradingExecutor(trader, max_trade_ratio=None)
        history_manager = HistoryManager(trader)
        price_history_manager = PriceHistoryManager()
        
        # Gemini 클라이언트 초기화
        print("\n🤖 Gemini 클라이언트 초기화 중...")
        gemini_client = GeminiClient()
        
        # 실제 가격 조회 (WebSocket 사용)
        print("\n📝 현재 가격 조회 중 (WebSocket 구독)...")
        current_prices = get_current_prices(tickers, use_websocket=True, timeout=10)
        
        if not current_prices:
            print("⚠️  가격 조회 실패. 테스트를 종료합니다.")
            return
        
        print(f"✅ {len(current_prices)}개 코인 가격 조회 완료")
        for ticker, price in current_prices.items():
            print(f"   {ticker}: {price:,.0f}원")
        
        # 가격 변화 추이 조회
        print("\n📈 가격 변화 추이 조회 중...")
        price_trends_text = price_history_manager.get_all_trends(
            tickers=list(current_prices.keys()),
            hours=24
        )
        
        # 포트폴리오 정보
        print("\n💰 포트폴리오 정보 조회 중...")
        portfolio = history_manager.get_portfolio_status(current_prices=current_prices)
        portfolio_text = f"""원화 잔고: {portfolio['krw_balance']:,.0f}원
총 자산: {portfolio['total_value']:,.0f}원
보유 코인 수: {len(portfolio['holdings'])}개"""
        
        if portfolio['holdings']:
            portfolio_text += "\n\n보유 코인:"
            for holding in portfolio['holdings']:
                portfolio_text += f"\n- {holding['ticker']}: {holding['amount']:.8f}개 "
                portfolio_text += f"(현재가: {holding['current_price']:,.0f}원, "
                portfolio_text += f"평가금액: {holding['total_value']:,.0f}원)"
        
        # 거래 히스토리
        print("\n📜 거래 히스토리 조회 중...")
        trade_history_text = history_manager.format_for_gemini(current_prices=current_prices)
        
        # Prompt 생성
        prompt = gemini_client.build_trading_prompt(
            current_prices=current_prices,
            portfolio_info=portfolio_text,
            trade_history=trade_history_text,
            price_trends=price_trends_text
        )
        
        print("\n" + "="*60)
        print("📝 생성된 Prompt")
        print("="*60)
        print(prompt)
        print("="*60)
        
        # Prompt만 출력하고 종료
        if show_prompt_only:
            print("\n✅ Prompt 출력 완료 (종료)")
            return
        
        print("\n" + "="*60)
        print("📤 LLM 호출 시작")
        print("="*60)
        
        # LLM 호출 (가격 추이 포함)
        success, function_calls, error = gemini_client.get_trading_decision(
            current_prices=current_prices,
            portfolio_info=portfolio_text,
            trade_history=trade_history_text,
            price_trends=price_trends_text  # 가격 추이 추가
        )
        
        print("\n" + "="*60)
        print("📥 LLM 응답 결과")
        print("="*60)
        
        if success:
            print(f"✅ 호출 성공")
            print(f"📞 함수 호출 개수: {len(function_calls)}")
            
            if function_calls:
                print("\n🔧 함수 호출 상세:")
                for i, fc in enumerate(function_calls, 1):
                    print(f"\n{i}. 함수명: {fc['name']}")
                    print(f"   인자: {fc['arguments']}")
                
                # 거래 실행 여부 확인
                if skip_trade:
                    print("\n⚠️  거래 실행은 건너뜁니다 (skip_trade=True)")
                    print("✅ LLM 응답 출력 완료 (종료)")
                else:
                    # 거래 실행 (y/n 확인 없이 바로 실행)
                    print("\n" + "="*60)
                    print("⚙️  거래 실행")
                    print("="*60)
                    print("\n🚀 거래 실행 시작...")
                    
                    # 공통 헬퍼 함수 사용
                    execute_function_calls(
                        function_calls=function_calls,
                        executor=executor,
                        gemini_client=gemini_client,
                        config_manager=config_manager
                    )
                    
                    print("\n✅ 모든 거래 실행 완료")
            else:
                print("\n⚪️  거래 결정 없음")
        else:
            print(f"❌ 호출 실패: {error}")
        
        print("\n" + "="*60)
        print("✅ 테스트 완료")
        print("="*60)
        print(f"\n💾 응답 히스토리는 data/llm_history/ 디렉토리에 저장되었습니다.")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_llm_call()

