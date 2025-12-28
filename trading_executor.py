"""
거래 실행 및 검증 모듈
안전장치와 함께 거래를 실행하고, 3회까지 재시도합니다.
"""
import time
from typing import Dict, Optional, Tuple
from upbit_trader import UpbitTrader


class TradingExecutor:
    """거래 실행 및 검증 클래스"""
    
    def __init__(self, trader: UpbitTrader, max_trade_ratio: float = None):
        """
        초기화
        
        Args:
            trader: UpbitTrader 인스턴스
            max_trade_ratio: 최대 거래 비율 (잔고 대비, None이면 제한 없음)
        """
        self.trader = trader
        self.max_trade_ratio = max_trade_ratio
        self.max_retries = 3
        self.retry_delay = 1  # 재시도 간격 (초)
    
    def _retry_with_backoff(self, func, *args, **kwargs) -> Tuple[bool, Optional[Dict], str]:
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
                if result is not None:
                    return True, result, ""
                else:
                    last_error = "함수가 None을 반환했습니다."
            
            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries:
                    print(f"⚠️  시도 {attempt}/{self.max_retries} 실패, {self.retry_delay}초 후 재시도...")
                    time.sleep(self.retry_delay * attempt)  # 지수 백오프
                else:
                    print(f"❌ 모든 재시도 실패: {last_error}")
        
        return False, None, last_error or "알 수 없는 오류"
    
    def validate_buy_order(self, ticker: str, amount: float) -> Tuple[bool, str]:
        """
        매수 주문 검증
        
        Args:
            ticker: 매수할 티커
            amount: 매수 금액
            
        Returns:
            (검증 성공 여부, 에러 메시지)
        """
        # 최소 금액 확인
        if amount < 5000:
            return False, "최소 매수 금액은 5000원입니다."
        
        # 잔고 확인
        krw_balance = self.trader.get_balance("KRW")
        if krw_balance < amount:
            return False, f"잔고 부족: {krw_balance:,.0f}원 < {amount:,.0f}원"
        
        # 최대 거래 비율 확인 (제한이 설정된 경우에만)
        if self.max_trade_ratio is not None:
            max_amount = krw_balance * self.max_trade_ratio
            if amount > max_amount:
                return False, f"최대 거래 금액 초과: {amount:,.0f}원 > {max_amount:,.0f}원 (잔고의 {self.max_trade_ratio*100}%)"
        
        return True, ""
    
    def validate_sell_order(self, ticker: str, volume: str) -> Tuple[bool, str, float]:
        """
        매도 주문 검증
        
        Args:
            ticker: 매도할 티커
            volume: 매도 수량 ("all" 또는 숫자 문자열)
            
        Returns:
            (검증 성공 여부, 에러 메시지, 실제 매도 수량)
        """
        # 보유 수량 확인
        balance = self.trader.get_balance(ticker)
        
        if balance == 0:
            return False, f"{ticker} 보유 수량이 없습니다.", 0.0
        
        # 수량 파싱
        if volume.lower() == "all":
            sell_volume = balance
        else:
            try:
                sell_volume = float(volume)
            except ValueError:
                return False, f"잘못된 수량 형식: {volume}", 0.0
        
        # 보유 수량 초과 확인
        if sell_volume > balance:
            return False, f"보유 수량 초과: {sell_volume} > {balance}", 0.0
        
        return True, "", sell_volume
    
    def execute_buy(self, ticker: str, amount: float) -> Tuple[bool, Optional[Dict], str]:
        """
        매수 주문 실행 (3회 재시도)
        
        Args:
            ticker: 매수할 티커
            amount: 매수 금액
            
        Returns:
            (성공 여부, 주문 결과, 에러 메시지)
        """
        # 검증
        is_valid, error_msg = self.validate_buy_order(ticker, amount)
        if not is_valid:
            return False, None, error_msg
        
        # 거래 실행 (재시도 포함)
        print(f"🟢 매수 주문 실행: {ticker}, 금액: {amount:,.0f}원")
        success, result, error = self._retry_with_backoff(
            self.trader.buy_market_order,
            ticker,
            amount
        )
        
        if success:
            print(f"✅ 매수 주문 성공: {result}")
        else:
            print(f"❌ 매수 주문 실패: {error}")
        
        return success, result, error
    
    def execute_sell(self, ticker: str, volume: str) -> Tuple[bool, Optional[Dict], str]:
        """
        매도 주문 실행 (3회 재시도)
        
        Args:
            ticker: 매도할 티커
            volume: 매도 수량 ("all" 또는 숫자)
            
        Returns:
            (성공 여부, 주문 결과, 에러 메시지)
        """
        # 검증
        is_valid, error_msg, sell_volume = self.validate_sell_order(ticker, volume)
        if not is_valid:
            return False, None, error_msg
        
        # 거래 실행 (재시도 포함)
        print(f"🔴 매도 주문 실행: {ticker}, 수량: {sell_volume}")
        success, result, error = self._retry_with_backoff(
            self.trader.sell_market_order,
            ticker,
            sell_volume
        )
        
        if success:
            print(f"✅ 매도 주문 성공: {result}")
        else:
            print(f"❌ 매도 주문 실패: {error}")
        
        return success, result, error

