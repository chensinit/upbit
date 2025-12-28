"""
업비트 자동 트레이딩 시스템
"""
import pyupbit
import time
from config import ACCESS_KEY, SECRET_KEY
from typing import Dict, List, Optional


class UpbitTrader:
    """업비트 API를 사용한 자동 트레이딩 클래스"""
    
    def __init__(self, access_key: str = None, secret_key: str = None):
        """
        초기화
        
        Args:
            access_key: 업비트 Access Key
            secret_key: 업비트 Secret Key
        """
        self.access_key = access_key or ACCESS_KEY
        self.secret_key = secret_key or SECRET_KEY
        
        if not self.access_key or not self.secret_key:
            raise ValueError("API 키가 설정되지 않았습니다. config.py 또는 .env 파일을 확인하세요.")
        
        # 업비트 객체 생성
        self.upbit = pyupbit.Upbit(self.access_key, self.secret_key)
        print("✅ 업비트 API 연결 성공!")
    
    def get_balance(self, ticker: str = "KRW") -> float:
        """
        잔고 조회
        
        Args:
            ticker: 조회할 티커 (기본값: "KRW" - 원화 잔고)
            
        Returns:
            잔고 금액
        """
        try:
            if ticker == "KRW":
                balance = self.upbit.get_balance("KRW")
            else:
                balance = self.upbit.get_balance(ticker)
            return balance
        except Exception as e:
            print(f"❌ 잔고 조회 실패: {e}")
            return 0.0
    
    def get_all_balances(self) -> List[Dict]:
        """
        전체 잔고 조회
        
        Returns:
            보유 자산 리스트
        """
        try:
            balances = self.upbit.get_balances()
            return balances
        except Exception as e:
            print(f"❌ 전체 잔고 조회 실패: {e}")
            return []
    
    def get_current_price(self, ticker: str, retry: int = 2) -> Optional[float]:
        """
        현재가 조회 (재시도 로직 포함)
        
        Args:
            ticker: 조회할 티커 (예: "KRW-BTC")
            retry: 재시도 횟수 (기본값: 2)
            
        Returns:
            현재가 (실패 시 None 반환)
        """
        for attempt in range(retry + 1):
            try:
                price = pyupbit.get_current_price(ticker)
                if price is None:
                    if attempt < retry:
                        time.sleep(0.5)  # 재시도 전 대기
                        continue
                    print(f"⚠️  {ticker} 가격 조회 실패: 가격 정보 없음")
                    return None
                return price
            except Exception as e:
                if attempt < retry:
                    time.sleep(0.5)  # 재시도 전 대기
                    continue
                error_msg = str(e)
                # "Code not found" 같은 에러는 코인이 존재하지 않는 경우
                if "Code not found" in error_msg or "not found" in error_msg.lower():
                    print(f"⚠️  {ticker} 가격 조회 실패: 코인을 찾을 수 없음 (업비트에 존재하지 않을 수 있음)")
                else:
                    print(f"❌ {ticker} 현재가 조회 실패: {e}")
                return None
        return None
    
    def buy_market_order(self, ticker: str, price: float) -> Optional[Dict]:
        """
        시장가 매수 주문
        
        Args:
            ticker: 매수할 티커 (예: "KRW-BTC")
            price: 매수할 금액 (원화)
            
        Returns:
            주문 결과 딕셔너리
        """
        try:
            print(f"🟢 매수 주문: {ticker}, 금액: {price:,.0f}원")
            result = self.upbit.buy_market_order(ticker, price)
            print(f"✅ 매수 주문 성공: {result}")
            return result
        except Exception as e:
            print(f"❌ 매수 주문 실패: {e}")
            return None
    
    def sell_market_order(self, ticker: str, volume: float) -> Optional[Dict]:
        """
        시장가 매도 주문
        
        Args:
            ticker: 매도할 티커 (예: "KRW-BTC")
            volume: 매도할 수량
            
        Returns:
            주문 결과 딕셔너리
        """
        try:
            print(f"🔴 매도 주문: {ticker}, 수량: {volume}")
            result = self.upbit.sell_market_order(ticker, volume)
            print(f"✅ 매도 주문 성공: {result}")
            return result
        except Exception as e:
            print(f"❌ 매도 주문 실패: {e}")
            return None
    
    def buy_limit_order(self, ticker: str, price: float, order_price: float) -> Optional[Dict]:
        """
        지정가 매수 주문
        
        Args:
            ticker: 매수할 티커
            price: 매수할 금액 (원화)
            order_price: 지정가 (원)
            
        Returns:
            주문 결과 딕셔너리
        """
        try:
            volume = price / order_price
            print(f"🟢 지정가 매수 주문: {ticker}, 가격: {order_price:,.0f}원, 수량: {volume}")
            result = self.upbit.buy_limit_order(ticker, order_price, volume)
            print(f"✅ 지정가 매수 주문 성공: {result}")
            return result
        except Exception as e:
            print(f"❌ 지정가 매수 주문 실패: {e}")
            return None
    
    def sell_limit_order(self, ticker: str, volume: float, order_price: float) -> Optional[Dict]:
        """
        지정가 매도 주문
        
        Args:
            ticker: 매도할 티커
            volume: 매도할 수량
            order_price: 지정가 (원)
            
        Returns:
            주문 결과 딕셔너리
        """
        try:
            print(f"🔴 지정가 매도 주문: {ticker}, 가격: {order_price:,.0f}원, 수량: {volume}")
            result = self.upbit.sell_limit_order(ticker, order_price, volume)
            print(f"✅ 지정가 매도 주문 성공: {result}")
            return result
        except Exception as e:
            print(f"❌ 지정가 매도 주문 실패: {e}")
            return None
    
    def get_order_status(self, uuid: str) -> Optional[Dict]:
        """
        주문 상태 조회
        
        Args:
            uuid: 주문 UUID
            
        Returns:
            주문 상태 딕셔너리
        """
        try:
            result = self.upbit.get_order(uuid)
            return result
        except Exception as e:
            print(f"❌ 주문 상태 조회 실패: {e}")
            return None
    
    def cancel_order(self, uuid: str) -> bool:
        """
        주문 취소
        
        Args:
            uuid: 주문 UUID
            
        Returns:
            취소 성공 여부
        """
        try:
            result = self.upbit.cancel_order(uuid)
            print(f"✅ 주문 취소 성공: {uuid}")
            return True
        except Exception as e:
            print(f"❌ 주문 취소 실패: {e}")
            return False
    
    def get_ticker_info(self, ticker: str) -> Optional[Dict]:
        """
        티커 정보 조회
        
        Args:
            ticker: 조회할 티커
            
        Returns:
            티커 정보 딕셔너리
        """
        try:
            info = pyupbit.get_ticker(ticker)
            return info
        except Exception as e:
            print(f"❌ 티커 정보 조회 실패: {e}")
            return None
    
    def print_account_info(self):
        """계정 정보 출력"""
        print("\n" + "="*50)
        print("📊 계정 정보")
        print("="*50)
        
        # 원화 잔고
        krw_balance = self.get_balance("KRW")
        print(f"💰 원화 잔고: {krw_balance:,.0f}원")
        
        # 보유 코인
        balances = self.get_all_balances()
        if balances:
            print("\n📈 보유 자산:")
            for balance in balances:
                currency = balance.get('currency', '')
                balance_amount = float(balance.get('balance', 0))
                locked = float(balance.get('locked', 0))
                if balance_amount > 0 or locked > 0:
                    ticker = f"KRW-{currency}"
                    if currency != "KRW":
                        current_price = self.get_current_price(ticker)
                        total_value = balance_amount * current_price
                        print(f"  - {currency}: {balance_amount:.8f} (잠김: {locked:.8f})")
                        print(f"    현재가: {current_price:,.0f}원, 평가금액: {total_value:,.0f}원")
                    else:
                        print(f"  - {currency}: {balance_amount:,.0f}원 (잠김: {locked:,.0f}원)")
        print("="*50 + "\n")

