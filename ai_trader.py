"""
AI 트레이더 메인 모듈
30분 간격으로 Gemini API를 호출하여 자동 트레이딩을 수행합니다.
"""
import time
import threading
from datetime import datetime
from typing import List, Dict
from upbit_trader import UpbitTrader
from price_subscriber import PriceSubscriber, get_current_prices
from gemini_client import GeminiClient
from trading_executor import TradingExecutor
from history_manager import HistoryManager
from config_manager import ConfigManager
from trade_executor_helper import execute_function_calls
from price_history_manager import PriceHistoryManager
import pyupbit


# nohup python ai_trader.py &
# pkill -f ai_trader.py


class AITrader:
    """AI 자동 트레이더 클래스"""
    
    def __init__(self, initial_tickers: List[str] = None):
        """
        초기화
        
        Args:
            initial_tickers: 초기 구독할 코인 티커 리스트 (None이면 파일에서 로드)
        """
        # 설정 파일 관리자 초기화
        self.config_manager = ConfigManager()
        
        # 구독 코인 목록 로드 (파일에서 또는 초기값)
        if initial_tickers is None:
            self.tickers = self.config_manager.load_tickers()
        else:
            # 초기값이 제공되면 파일에 저장
            self.tickers = initial_tickers
            self.config_manager.save_tickers(initial_tickers)
        
        # 설정 정보 로드
        settings = self.config_manager.load_settings()
        self.check_interval = settings.get("check_interval", 30 * 60)  # 거래 사이클 간격 (30분)
        self.coin_selection_interval = settings.get("coin_selection_interval", 6 * 60 * 60)  # 코인 선택 사이클 간격 (6시간)
        
        # 컴포넌트 초기화
        print("🚀 AI 트레이더 초기화 중...")
        self.trader = UpbitTrader()
        self.executor = TradingExecutor(self.trader, max_trade_ratio=None)  # 거래 비율 제한 없음
        self.history_manager = HistoryManager(self.trader)
        self.gemini_client = GeminiClient()
        self.price_history_manager = PriceHistoryManager()
        
        # WebSocket 가격 구독 (폴백: REST API)
        self.price_subscriber = PriceSubscriber(
            tickers=self.tickers,
            callback=self._price_update_callback
        )
        
        # 실행 상태
        self.running = False
        self.thread = None
        self.last_coin_selection_time = None  # 마지막 코인 선택 시간
        self.last_price_save_time = None  # 마지막 가격 저장 시간
        
        print("✅ AI 트레이더 초기화 완료")
    
    def _price_update_callback(self, ticker: str, price: float):
        """가격 업데이트 콜백 (WebSocket 사용 시)"""
        # 가격 히스토리에 저장 (10분마다)
        current_time = datetime.now()
        if self.last_price_save_time is None:
            # 첫 저장
            self.price_history_manager.save_price(ticker, price, current_time)
            self.last_price_save_time = current_time
        else:
            # 10분마다 저장
            elapsed = (current_time - self.last_price_save_time).total_seconds()
            if elapsed >= 600:  # 10분 = 600초
                self.price_history_manager.save_price(ticker, price, current_time)
                self.last_price_save_time = current_time
    
    def _get_current_market_data(self) -> Dict[str, float]:
        """
        현재 시장 데이터 조회 (WebSocket 우선, 실패 시 REST API 폴백)
        
        Returns:
            {ticker: price} 딕셔너리
        """
        # WebSocket이 정상이면 WebSocket 사용
        if self.price_subscriber and self.price_subscriber.is_healthy():
            prices = self.price_subscriber.get_all_prices()
            if prices and len(prices) > 0:
                return prices
        
        # WebSocket이 없거나 비정상이면 REST API 사용
        print("⚠️  WebSocket 사용 불가, REST API로 폴백")
        prices = get_current_prices(self.tickers)
        
        # REST API로 가져온 가격도 저장 (10분마다)
        current_time = datetime.now()
        if self.last_price_save_time is None:
            for ticker, price in prices.items():
                self.price_history_manager.save_price(ticker, price, current_time)
            self.last_price_save_time = current_time
        else:
            elapsed = (current_time - self.last_price_save_time).total_seconds()
            if elapsed >= 600:  # 10분 = 600초
                for ticker, price in prices.items():
                    self.price_history_manager.save_price(ticker, price, current_time)
                self.last_price_save_time = current_time
        
        # WebSocket 재연결 시도
        if self.price_subscriber and not self.price_subscriber.is_healthy():
            if self.price_subscriber.running:
                print("🔄 WebSocket 재연결 시도...")
                self.price_subscriber.reconnect()
        
        return prices
    
    def _get_available_coins(self, limit: int = 50) -> List[str]:
        """
        선택 가능한 코인 목록 조회 (시가총액 상위)
        
        Args:
            limit: 가져올 코인 수 (기본 50개)
            
        Returns:
            코인 티커 리스트
        """
        try:
            # KRW 마켓의 모든 코인 가져오기
            tickers = pyupbit.get_tickers(fiat="KRW")
            
            # 시가총액 정보가 없으므로, 일단 상위 N개 반환
            # 나중에 뉴스 수집 기능이 추가되면 더 정교하게 필터링 가능
            return tickers[:limit] if len(tickers) > limit else tickers
        except Exception as e:
            print(f"⚠️  코인 목록 조회 실패: {e}")
            # 기본 메이저 코인 반환
            return ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA", "KRW-SOL", 
                   "KRW-DOT", "KRW-AVAX", "KRW-LINK", "KRW-MATIC", "KRW-UNI"]
    
    def _execute_trading_cycle(self):
        """한 번의 트레이딩 사이클 실행"""
        try:
            print("\n" + "="*60)
            print(f"⏰ 트레이딩 사이클 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)
            
            # 1. 현재 가격 조회
            print("📊 현재 가격 조회 중...")
            current_prices = self._get_current_market_data()
            
            if not current_prices:
                print("⚠️  가격 조회 실패, 사이클 건너뜀")
                return
            
            print(f"✅ {len(current_prices)}개 코인 가격 조회 완료")
            for ticker, price in current_prices.items():
                print(f"   {ticker}: {price:,.0f}원")
            
            # 2. 가격 변화 추이 조회
            print("\n📈 가격 변화 추이 조회 중...")
            price_trends_text = self.price_history_manager.get_all_trends(
                tickers=list(current_prices.keys()),
                hours=24
            )
            
            # 3. 포트폴리오 정보 조회
            print("\n💰 포트폴리오 정보 조회 중...")
            portfolio = self.history_manager.get_portfolio_status(current_prices=current_prices)
            portfolio_text = f"""원화 잔고: {portfolio['krw_balance']:,.0f}원
총 자산: {portfolio['total_value']:,.0f}원
보유 코인 수: {len(portfolio['holdings'])}개"""
            
            if portfolio['holdings']:
                portfolio_text += "\n\n보유 코인:"
                for holding in portfolio['holdings']:
                    portfolio_text += f"\n- {holding['ticker']}: {holding['amount']:.8f}개 "
                    portfolio_text += f"(현재가: {holding['current_price']:,.0f}원, "
                    portfolio_text += f"평가금액: {holding['total_value']:,.0f}원)"
            
            # 4. 거래 히스토리 조회
            print("\n📜 거래 히스토리 조회 중...")
            trade_history_text = self.history_manager.format_for_gemini(current_prices=current_prices)
            
            # 5. Gemini API로 트레이딩 결정 요청 (가격 추이 포함)
            print("\n🤖 AI 트레이딩 결정 요청 중...")
            success, function_calls, error = self.gemini_client.get_trading_decision(
                current_prices,
                portfolio_text,
                trade_history_text,
                price_trends_text  # 가격 추이 추가
            )
            
            if not success:
                print(f"❌ AI 결정 요청 실패: {error}")
                return
            
            # 5. 함수 호출 실행
            if function_calls:
                print(f"\n⚙️  {len(function_calls)}개 함수 호출 실행 중...")
                
                for func_call in function_calls:
                    self._execute_function_call(func_call)
            else:
                print("\n⚪️  거래 결정 없음 (현재 상태 유지)")
            
            print("\n✅ 트레이딩 사이클 완료")
            print("="*60)
        
        except Exception as e:
            print(f"\n❌ 트레이딩 사이클 오류: {e}")
            import traceback
            traceback.print_exc()
    
    def _execute_coin_selection_cycle(self):
        """코인 선택 사이클 실행 (코인 구독 변경 전용)"""
        try:
            print("\n" + "="*60)
            print(f"🪙 코인 선택 사이클 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)
            
            # 1. 선택 가능한 코인 목록 조회
            print("📋 선택 가능한 코인 목록 조회 중...")
            available_coins = self._get_available_coins(limit=50)
            print(f"✅ {len(available_coins)}개 코인 조회 완료")
            
            # 2. 현재 구독 중인 코인
            current_subscribed = self.tickers.copy()
            print(f"📌 현재 구독 중인 코인: {', '.join(current_subscribed)}")
            
            # 3. 코인 정보 (뉴스 등, 나중에 추가)
            coin_info = ""  # TODO: 뉴스 수집 기능 추가 시 여기에 정보 제공
            
            # 4. Gemini API로 코인 선택 결정 요청
            print("\n🤖 AI 코인 선택 결정 요청 중...")
            success, function_calls, error = self.gemini_client.get_coin_selection_decision(
                available_coins=available_coins,
                current_subscribed=current_subscribed,
                coin_info=coin_info
            )
            
            if not success:
                print(f"❌ AI 결정 요청 실패: {error}")
                return
            
            # 5. 함수 호출 실행 (update_subscribed_coins만)
            if function_calls:
                print(f"\n⚙️  {len(function_calls)}개 함수 호출 실행 중...")
                
                for func_call in function_calls:
                    self._execute_function_call(func_call)
            else:
                print("\n⚪️  코인 선택 결정 없음 (현재 구독 유지)")
            
            # 마지막 코인 선택 시간 업데이트
            self.last_coin_selection_time = datetime.now()
            
            print("\n✅ 코인 선택 사이클 완료")
            print("="*60)
        
        except Exception as e:
            print(f"\n❌ 코인 선택 사이클 오류: {e}")
            import traceback
            traceback.print_exc()
    
    def _execute_function_call(self, function_call: Dict):
        """
        Function call 실행
        
        Args:
            function_call: 함수 호출 딕셔너리
        """
        # 공통 헬퍼 함수 사용
        execute_function_calls(
            function_calls=[function_call],
            executor=self.executor,
            gemini_client=self.gemini_client,
            config_manager=self.config_manager
        )
        
        # update_subscribed_coins의 경우 추가 처리
        name = function_call.get("name", "")
        if name == "update_subscribed_coins":
            arguments = function_call.get("arguments", {})
            new_tickers = arguments.get("tickers", [])
            if new_tickers:
                # 새로 추가된 코인 확인
                old_tickers = set(self.tickers)
                new_tickers_set = set(new_tickers)
                added_tickers = new_tickers_set - old_tickers
                
                # 새로 추가된 코인에 대해 과거 데이터 수집
                if added_tickers:
                    print(f"\n📥 새로 구독한 코인 {len(added_tickers)}개에 대한 과거 데이터 수집 중...")
                    for ticker in added_tickers:
                        # 각 코인 사이에 1초 대기 (서버 부하 방지)
                        if ticker != list(added_tickers)[0]:  # 첫 번째 코인은 대기 없음
                            time.sleep(1.0)
                        self.price_history_manager.fetch_historical_data(ticker)
                
                self.tickers = new_tickers
                # 가격 구독 업데이트 (WebSocket 사용 시)
                if self.price_subscriber:
                    self.price_subscriber.update_tickers(new_tickers)
    
    def _run_loop(self):
        """메인 실행 루프 (거래 사이클만 실행)"""
        while self.running:
            try:
                # 거래 사이클 실행 (30분마다)
                self._execute_trading_cycle()
                
                # 다음 사이클까지 대기
                print(f"\n⏳ 다음 거래 사이클까지 {self.check_interval // 60}분 대기 중...")
                print("   (Ctrl+C로 중지 가능)")
                
                # 대기 중에도 종료 신호 확인
                for _ in range(self.check_interval):
                    if not self.running:
                        break
                    time.sleep(1)
            
            except KeyboardInterrupt:
                print("\n\n⏹️  사용자에 의해 중지됨")
                self.stop()
                break
            except Exception as e:
                print(f"\n❌ 루프 오류: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)  # 오류 발생 시 1분 대기 후 재시도
    
    def start(self):
        """AI 트레이더 시작"""
        if self.running:
            print("⚠️  이미 실행 중입니다.")
            return
        
        self.running = True
        print("\n" + "="*60)
        print("🚀 AI 트레이더 시작")
        print(f"📌 구독 코인: {', '.join(self.tickers)}")
        print(f"⏰ 거래 사이클 간격: {self.check_interval // 60}분")
        print("="*60)
        
        # WebSocket 가격 구독 시작
        if self.price_subscriber:
            print("\n🔌 WebSocket 가격 구독 시작...")
            self.price_subscriber.start()
        
        # 첫 거래 사이클 즉시 실행
        self._execute_trading_cycle()
        
        # 백그라운드 스레드로 주기적 실행
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        """AI 트레이더 중지"""
        if not self.running:
            return
        
        self.running = False
        
        if self.price_subscriber:
            self.price_subscriber.stop()
        
        if self.thread:
            self.thread.join(timeout=5)
        
        print("\n⏹️  AI 트레이더 중지됨")
    
    def run_once(self):
        """한 번만 실행 (테스트용)"""
        print("\n🧪 테스트 모드: 한 번만 실행")
        self._execute_trading_cycle()


def main():
    """메인 함수"""
    import sys
    
    print("="*60)
    print("🤖 AI 자동 트레이딩 시스템")
    print("="*60)
    
    # 명령줄 인자 파싱
    initial_tickers = None
    mode = "auto"  # 기본값: 자동 실행
    
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg in ["test", "once"]:
                mode = arg
            elif arg.startswith("KRW-") or "," in arg:
                # 코인 티커로 인식
                initial_tickers = arg.split(",") if "," in arg else [arg]
    
    if initial_tickers:
        print(f"📌 초기 구독 코인: {', '.join(initial_tickers)}")
    
    try:
        # AI 트레이더 생성
        ai_trader = AITrader(initial_tickers=initial_tickers)
        
        # 계정 정보 출력
        ai_trader.trader.print_account_info()
        
        # 실행 모드에 따라 자동 실행
        if mode == "test" or mode == "once":
            print("\n🧪 테스트 모드: 한 번만 실행")
            ai_trader.run_once()
        else:
            # 자동 실행 모드 (기본값)
            print("\n🚀 자동 실행 모드 시작")
            ai_trader.start()
            
            # 메인 스레드에서 대기
            try:
                while ai_trader.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\n\n⏹️  종료 신호 수신")
                ai_trader.stop()
    
    except ValueError as e:
        print(f"❌ 오류: {e}")
        print("\n💡 해결 방법:")
        print("1. config.py에 Gemini API 키를 설정하세요.")
        print("2. 또는 .env 파일에 GEMINI_API_KEY를 추가하세요.")
    
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

