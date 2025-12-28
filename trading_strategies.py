"""
트레이딩 전략 예제
"""
import pyupbit
import time
from upbit_trader import UpbitTrader
from typing import Optional


class SimpleStrategy:
    """간단한 트레이딩 전략 예제"""
    
    def __init__(self, trader: UpbitTrader):
        self.trader = trader
    
    def moving_average_strategy(self, ticker: str, short_period: int = 5, long_period: int = 20, 
                               buy_amount: float = 10000):
        """
        이동평균선 전략 (골든크로스/데드크로스)
        
        Args:
            ticker: 거래할 티커
            short_period: 단기 이동평균 기간
            long_period: 장기 이동평균 기간
            buy_amount: 매수 금액 (원화)
        """
        print(f"\n📊 이동평균선 전략 실행: {ticker}")
        print(f"   단기: {short_period}일, 장기: {long_period}일")
        
        # 과거 데이터 가져오기
        df = pyupbit.get_ohlcv(ticker, interval="day", count=long_period + 1)
        
        if df is None or len(df) < long_period:
            print("❌ 데이터를 가져올 수 없습니다.")
            return
        
        # 이동평균 계산
        df['ma_short'] = df['close'].rolling(window=short_period).mean()
        df['ma_long'] = df['close'].rolling(window=long_period).mean()
        
        current_short = df['ma_short'].iloc[-1]
        current_long = df['ma_long'].iloc[-1]
        prev_short = df['ma_short'].iloc[-2]
        prev_long = df['ma_long'].iloc[-2]
        
        current_price = self.trader.get_current_price(ticker)
        balance = self.trader.get_balance(ticker)
        
        print(f"   현재가: {current_price:,.0f}원")
        print(f"   단기 이동평균: {current_short:,.0f}원")
        print(f"   장기 이동평균: {current_long:,.0f}원")
        print(f"   보유 수량: {balance}")
        
        # 골든크로스: 단기선이 장기선을 상향 돌파
        if prev_short <= prev_long and current_short > current_long:
            print("🟢 골든크로스 발생! 매수 신호")
            krw_balance = self.trader.get_balance("KRW")
            if krw_balance >= buy_amount:
                self.trader.buy_market_order(ticker, buy_amount)
            else:
                print(f"❌ 잔고 부족: {krw_balance:,.0f}원 < {buy_amount:,.0f}원")
        
        # 데드크로스: 단기선이 장기선을 하향 돌파
        elif prev_short >= prev_long and current_short < current_long:
            print("🔴 데드크로스 발생! 매도 신호")
            if balance > 0:
                self.trader.sell_market_order(ticker, balance)
            else:
                print("❌ 보유 수량 없음")
        
        else:
            print("⚪️  신호 없음 (보유)")
    
    def rsi_strategy(self, ticker: str, period: int = 14, buy_amount: float = 10000,
                    oversold: float = 30, overbought: float = 70):
        """
        RSI 전략
        
        Args:
            ticker: 거래할 티커
            period: RSI 기간
            buy_amount: 매수 금액
            oversold: 과매도 기준 (기본 30)
            overbought: 과매수 기준 (기본 70)
        """
        print(f"\n📊 RSI 전략 실행: {ticker}")
        print(f"   기간: {period}일, 과매도: {oversold}, 과매수: {overbought}")
        
        # 과거 데이터 가져오기
        df = pyupbit.get_ohlcv(ticker, interval="day", count=period + 1)
        
        if df is None or len(df) < period:
            print("❌ 데이터를 가져올 수 없습니다.")
            return
        
        # RSI 계산
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        current_rsi = rsi.iloc[-1]
        current_price = self.trader.get_current_price(ticker)
        balance = self.trader.get_balance(ticker)
        
        print(f"   현재가: {current_price:,.0f}원")
        print(f"   RSI: {current_rsi:.2f}")
        print(f"   보유 수량: {balance}")
        
        # 과매도 구간: 매수
        if current_rsi < oversold:
            print(f"🟢 RSI {current_rsi:.2f} < {oversold} (과매도) - 매수 신호")
            krw_balance = self.trader.get_balance("KRW")
            if krw_balance >= buy_amount:
                self.trader.buy_market_order(ticker, buy_amount)
            else:
                print(f"❌ 잔고 부족: {krw_balance:,.0f}원 < {buy_amount:,.0f}원")
        
        # 과매수 구간: 매도
        elif current_rsi > overbought:
            print(f"🔴 RSI {current_rsi:.2f} > {overbought} (과매수) - 매도 신호")
            if balance > 0:
                self.trader.sell_market_order(ticker, balance)
            else:
                print("❌ 보유 수량 없음")
        
        else:
            print(f"⚪️  RSI {current_rsi:.2f} (보유)")
    
    def simple_buy_hold(self, ticker: str, buy_amount: float = 10000):
        """
        간단한 매수 후 보유 전략
        
        Args:
            ticker: 거래할 티커
            buy_amount: 매수 금액
        """
        print(f"\n📊 매수 후 보유 전략: {ticker}")
        
        balance = self.trader.get_balance(ticker)
        current_price = self.trader.get_current_price(ticker)
        
        print(f"   현재가: {current_price:,.0f}원")
        print(f"   보유 수량: {balance}")
        
        if balance == 0:
            print("🟢 보유 수량 없음 - 매수 실행")
            krw_balance = self.trader.get_balance("KRW")
            if krw_balance >= buy_amount:
                self.trader.buy_market_order(ticker, buy_amount)
            else:
                print(f"❌ 잔고 부족: {krw_balance:,.0f}원 < {buy_amount:,.0f}원")
        else:
            print("⚪️  이미 보유 중")

