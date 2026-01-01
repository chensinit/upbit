"""
AI 트레이더 메인 모듈
30분 간격으로 Gemini API를 호출하여 자동 트레이딩을 수행합니다.
"""
import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict
from pathlib import Path
from upbit_trader import UpbitTrader
from price_subscriber import get_current_prices, get_current_prices_and_volumes
from gemini_client import GeminiClient
from trading_executor import TradingExecutor
from history_manager import HistoryManager
from config_manager import ConfigManager
from trade_executor_helper import execute_function_calls
from price_history_manager import PriceHistoryManager
from coin_selector import CoinSelector
from trade_execution_history import TradeExecutionHistory
import pyupbit


# nohup python ai_trader.py &
# pkill -f ai_trader.py
# ps aux | grep ai_trader.py


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
        self.coin_selection_interval = settings.get("coin_selection_interval", 6 * 60 * 60)  # 코인 선택 사이클 간격 (6시간, 사용 안 함)
        self.coin_selection_hour = settings.get("coin_selection_hour", 2)  # 코인 선택 실행 시간 (새벽 2시)
        self.coin_selection_minute = settings.get("coin_selection_minute", 0)  # 코인 선택 실행 분 (0분)
        
        # 컴포넌트 초기화
        print("🚀 AI 트레이더 초기화 중...")
        self.trader = UpbitTrader()
        self.executor = TradingExecutor(self.trader, max_trade_ratio=None)  # 거래 비율 제한 없음
        self.history_manager = HistoryManager(self.trader)
        self.gemini_client = GeminiClient()
        self.price_history_manager = PriceHistoryManager()
        self.coin_selector = CoinSelector(trader=self.trader)  # 규칙 기반 코인 선택기
        self.execution_history = TradeExecutionHistory()  # 거래 실행 내역 관리
        
        # 실행 상태
        self.running = False
        self.unified_scheduler_thread = None  # 통합 스케줄러 스레드 (가격 저장 + 거래 사이클)
        self.coin_selection_thread = None  # 코인 선택 스케줄러 스레드
        self.last_coin_selection_time = None  # 마지막 코인 선택 시간
        self.is_coin_selection_running = False  # 코인 선택 실행 중 플래그
        
        print("✅ AI 트레이더 초기화 완료")
    
    def _get_current_market_data(self) -> Dict[str, float]:
        """
        현재 시장 데이터 조회 (REST API)
        
        Returns:
            {ticker: price} 딕셔너리
        """
        # REST API로 현재가 조회
        prices = get_current_prices(self.tickers)
        
        # REST API로 가져온 가격은 저장하지 않음 (가격 저장 스케줄러에서 처리)
        
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
            
            # 4. 거래 히스토리 조회 (보유 코인만 조회, 저장된 거래 내역 우선 사용)
            print("\n📜 거래 히스토리 조회 중...")
            trade_history_text = self.history_manager.format_for_gemini(
                current_prices=current_prices,
                tickers=None  # None이면 보유 코인만 조회
            )
            
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
        """코인 선택 사이클 실행 (규칙 기반)"""
        try:
            print("\n" + "="*60)
            print(f"🪙 코인 선택 사이클 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)
            
            # 코인 선택 실행 중 플래그 설정
            self.is_coin_selection_running = True
            
            # 규칙 기반 코인 선택
            result = self.coin_selector.update_coin_universe()
            if isinstance(result, tuple):
                selected_coins, detail_info = result
            else:
                # 하위 호환성 (tuple이 아닌 경우)
                selected_coins = result
                detail_info = {}
            
            if not selected_coins:
                print("⚠️  코인 선택 실패, 현재 구독 유지")
                self.is_coin_selection_running = False
                return
            
            # 현재 구독 코인과 비교
            old_tickers = set(self.tickers)
            new_tickers = set(selected_coins)
            
            if old_tickers == new_tickers:
                print("\n⚪️  코인 변경 없음 (현재 구독 유지)")
            else:
                # 변경된 코인 확인
                added_tickers = new_tickers - old_tickers
                removed_tickers = old_tickers - new_tickers
                
                if added_tickers:
                    print(f"\n➕ 추가된 코인: {', '.join(sorted(added_tickers))}")
                if removed_tickers:
                    print(f"\n➖ 제거된 코인: {', '.join(sorted(removed_tickers))}")
                
                # 새로 추가된 코인에 대해 과거 데이터 수집
                if added_tickers:
                    print(f"\n📥 새로 구독한 코인 {len(added_tickers)}개에 대한 과거 데이터 수집 중...")
                    for i, ticker in enumerate(sorted(added_tickers)):
                        if i > 0:  # 첫 번째 코인은 대기 없음
                            time.sleep(0.3)  # 서버 부하 방지
                        self.price_history_manager.fetch_historical_data(ticker)
                
                # 구독 코인 업데이트
                self.tickers = sorted(list(new_tickers))
                self.config_manager.save_tickers(self.tickers)
            
            # 마지막 코인 선택 시간 업데이트
            self.last_coin_selection_time = datetime.now()
            
            # 코인 선택 히스토리 저장
            self._save_coin_selection_history(
                old_tickers=old_tickers,
                new_tickers=new_tickers,
                selected_coins=selected_coins,
                detail_info=detail_info
            )
            
            print("\n✅ 코인 선택 사이클 완료")
            print("="*60)
            
            # 코인 선택 실행 중 플래그 해제
            self.is_coin_selection_running = False
        
        except Exception as e:
            print(f"\n❌ 코인 선택 사이클 오류: {e}")
            import traceback
            traceback.print_exc()
            self.is_coin_selection_running = False
    
    def _save_coin_selection_history(self, old_tickers: set, new_tickers: set, 
                                    selected_coins: List[str], detail_info: Dict = None):
        """
        코인 선택 히스토리 저장
        
        Args:
            old_tickers: 이전 구독 코인
            new_tickers: 새로운 구독 코인
            selected_coins: 선택된 코인 리스트
            detail_info: 상세 정보 딕셔너리
        """
        try:
            history_dir = Path("data/coin_selection_history")
            history_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일명: 🪙_COIN_SELECTION_YYYYMMDD_HHMMSS.txt
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"🪙_COIN_SELECTION_{timestamp}.txt"
            filepath = history_dir / filename
            
            # PINNED 코인 정보 가져오기
            pinned = self.coin_selector.load_pinned_tickers()
            held = self.coin_selector.get_held_tickers()
            
            # 히스토리 내용 작성
            content = f"""🪙 코인 선택 히스토리
{'='*60}
실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## PINNED 코인
메이저 코인: {', '.join(pinned) if pinned else '없음'}
보유 코인: {', '.join(held) if held else '없음'}
PINNED 총 {len(pinned) + len(held)}개

## 선택된 코인
총 {len(selected_coins)}개: {', '.join(sorted(selected_coins))}

## 변경 사항
이전 구독: {len(old_tickers)}개
  {', '.join(sorted(old_tickers)) if old_tickers else '없음'}

새 구독: {len(new_tickers)}개
  {', '.join(sorted(new_tickers)) if new_tickers else '없음'}

"""
            
            # 추가/제거된 코인
            added = new_tickers - old_tickers
            removed = old_tickers - new_tickers
            
            if added:
                content += f"➕ 추가된 코인 ({len(added)}개):\n"
                for ticker in sorted(added):
                    content += f"  - {ticker}\n"
                content += "\n"
            
            if removed:
                content += f"➖ 제거된 코인 ({len(removed)}개):\n"
                for ticker in sorted(removed):
                    content += f"  - {ticker}\n"
                content += "\n"
            
            if not added and not removed:
                content += "⚪️  변경 없음 (현재 구독 유지)\n\n"
            
            # 상세 정보 추가
            if detail_info:
                content += f"""## 상세 선택 정보
전체 KRW 코인: {detail_info.get('total_tickers', 0)}개
필터링 통과: {detail_info.get('filtered_count', 0)}개

Momentum 후보: {len(detail_info.get('momentum_all', []))}개
  선택됨: {', '.join(detail_info.get('momentum', [])) if detail_info.get('momentum') else '없음'}

Dip 후보: {len(detail_info.get('dip_all', []))}개
  선택됨: {', '.join(detail_info.get('dip', [])) if detail_info.get('dip') else '없음'}

"""
            
            # 선택 기준
            content += f"""## 선택 기준
- 거래대금 24h >= 10억원
- 변동성 1% ~ 25%
- Momentum: +3% 이상 상승
- Dip: -6% ~ 0%, 변동성 >= 1.5%
- 목표: PINNED + Momentum 6개 + Dip 6개

{'='*60}
"""
            
            # 파일 저장
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"💾 코인 선택 히스토리 저장: {filename}")
        
        except Exception as e:
            print(f"⚠️  코인 선택 히스토리 저장 실패: {e}")
    
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
            config_manager=self.config_manager,
            execution_history=self.execution_history
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
                    for i, ticker in enumerate(added_tickers):
                        # 각 코인 사이에 0.3초 대기 (서버 부하 방지)
                        if i > 0:
                            time.sleep(0.3)
                        self.price_history_manager.fetch_historical_data(ticker)
                
                self.tickers = new_tickers
    
    def _unified_scheduler(self):
        """통합 스케줄러: 10분마다 가격 저장, 30분마다 거래 사이클 실행"""
        # 첫 실행 전 10초 대기 (초기화 완료 대기)
        time.sleep(10)
        
        cycle_count = 0  # 거래 사이클 카운터 (3번째마다 실행 = 30분 간격)
        
        while self.running:
            try:
                # 코인 선택 실행 중이면 스킵
                if self.is_coin_selection_running:
                    time.sleep(60)  # 1분 후 다시 확인
                    continue
                
                # 1. 가격 및 거래량 저장 (항상 실행)
                prices_and_volumes = get_current_prices_and_volumes(self.tickers)
                
                if prices_and_volumes:
                    # 즉시 저장
                    current_time = datetime.now()
                    saved_count = 0
                    for ticker, data in prices_and_volumes.items():
                        price = data.get("price")
                        volume = data.get("volume")
                        if price and price > 0:
                            self.price_history_manager.save_price(
                                ticker, 
                                price, 
                                volume=volume, 
                                timestamp=current_time
                            )
                            saved_count += 1
                    
                    print(f"💾 가격/거래량/RSI 저장 완료: {saved_count}개 코인 ({current_time.strftime('%Y-%m-%d %H:%M:%S')})")
                else:
                    print(f"⚠️  가격 조회 실패 ({datetime.now().strftime('%H:%M:%S')})")
                
                # 2. 거래 사이클 실행 (3번째마다 = 30분 간격)
                cycle_count += 1
                if cycle_count >= 3:  # 10분 * 3 = 30분
                    cycle_count = 0
                    print(f"\n📊 거래 사이클 실행 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                    self._execute_trading_cycle()
                    print(f"✅ 거래 사이클 완료\n")
                
                # 10분 대기
                for _ in range(600):
                    if not self.running:
                        break
                    time.sleep(1)
            
            except Exception as e:
                print(f"⚠️  통합 스케줄러 오류: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)  # 오류 발생 시 1분 후 재시도
    
    def _coin_selection_scheduler(self):
        """새벽 시간에 코인 선택 실행하는 스케줄러"""
        while self.running:
            try:
                now = datetime.now()
                target_time = now.replace(
                    hour=self.coin_selection_hour, 
                    minute=self.coin_selection_minute, 
                    second=0, 
                    microsecond=0
                )
                
                # 오늘 새벽 시간이 지났으면 내일 새벽 시간으로
                if now >= target_time:
                    target_time += timedelta(days=1)
                
                # 다음 새벽 시간까지 대기
                wait_seconds = (target_time - now).total_seconds()
                print(f"⏰ 다음 코인 선택 시간: {target_time.strftime('%Y-%m-%d %H:%M:%S')} (대기: {wait_seconds // 3600:.1f}시간)")
                
                # 대기 중에도 종료 신호 확인
                for _ in range(int(wait_seconds)):
                    if not self.running:
                        break
                    time.sleep(1)
                
                if not self.running:
                    break
                
                # 코인 선택 실행
                print(f"\n🌙 새벽 코인 선택 시작: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                self._execute_coin_selection_cycle()
                print(f"✅ 코인 선택 완료: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
            except Exception as e:
                print(f"❌ 코인 선택 스케줄러 오류: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(3600)  # 1시간 후 재시도
    
    
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
        
        # 첫 거래 사이클 즉시 실행
        self._execute_trading_cycle()
        
        # 통합 스케줄러 스레드 시작 (10분마다 가격 저장, 30분마다 거래 사이클)
        self.unified_scheduler_thread = threading.Thread(
            target=self._unified_scheduler,
            daemon=True
        )
        self.unified_scheduler_thread.start()
        print(f"⏰ 통합 스케줄러 시작 (가격 저장: 10분 간격, 거래 사이클: 30분 간격)")
        
        # 코인 선택 스케줄러 스레드 시작
        self.coin_selection_thread = threading.Thread(
            target=self._coin_selection_scheduler, 
            daemon=True
        )
        self.coin_selection_thread.start()
        print(f"⏰ 코인 선택 스케줄러 시작 (매일 {self.coin_selection_hour:02d}:{self.coin_selection_minute:02d} 실행)")
    
    def stop(self):
        """AI 트레이더 중지"""
        if not self.running:
            return
        
        self.running = False
        
        if self.unified_scheduler_thread:
            self.unified_scheduler_thread.join(timeout=5)
        
        if self.coin_selection_thread:
            self.coin_selection_thread.join(timeout=5)
        
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

