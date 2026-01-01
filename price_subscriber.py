"""
실시간 가격 구독 모듈
WebSocket을 사용하여 여러 코인의 실시간 가격을 구독합니다.
"""
import pyupbit
import json
import threading
import time
import multiprocessing
from typing import Dict, Callable, Optional, List


class PriceSubscriber:
    """실시간 가격 구독 클래스"""
    
    def __init__(self, tickers: List[str], callback: Optional[Callable] = None):
        """
        초기화
        
        Args:
            tickers: 구독할 코인 티커 리스트 (예: ['KRW-BTC', 'KRW-ETH'])
            callback: 가격 업데이트 시 호출될 콜백 함수 (ticker, price) -> None
        """
        self.tickers = tickers
        self.callback = callback
        self.prices: Dict[str, float] = {}
        self.running = False
        self.ws = None
        self.thread = None
        self.queue_thread = None
        self.queue = None
        self.reconnect_interval = 5  # 재연결 간격 (초)
        self.max_reconnect_attempts = 10  # 최대 재연결 시도 횟수
        
        # 연결 상태 추적
        self.is_connected = False
        self.last_message_time: Optional[float] = None
        self.reconnect_attempts = 0
        self.connection_timeout = 30  # 30초 이상 메시지 없으면 비정상으로 간주
        
    def _process_queue(self):
        """Queue에서 메시지를 읽어서 처리하는 스레드"""
        while self.running:
            try:
                if self.queue is None:
                    time.sleep(0.1)
                    continue
                
                # Queue에서 메시지 읽기 (타임아웃 1초)
                try:
                    data = self.queue.get(timeout=1)
                except:
                    continue
                
                # ConnectionClosedError 체크
                if data == 'ConnectionClosedError':
                    print("⚠️  WebSocket 연결 종료됨")
                    self.is_connected = False
                    if self.running:
                        # 재연결 시도
                        if self.reconnect_attempts < self.max_reconnect_attempts:
                            self.reconnect_attempts += 1
                            print(f"🔄 재연결 시도 {self.reconnect_attempts}/{self.max_reconnect_attempts}...")
                            time.sleep(self.reconnect_interval)
                            self._connect()
                        else:
                            print(f"❌ 최대 재연결 시도 횟수 초과 ({self.max_reconnect_attempts}회)")
                            print("   REST API로 폴백하거나 수동으로 재연결하세요.")
                    continue
                
                # ticker 데이터 처리
                if isinstance(data, dict) and 'type' in data and data['type'] == 'ticker':
                    ticker = data.get('code')
                    price = data.get('trade_price')
                    
                    if ticker and price:
                        price = float(price)
                        
                        # 가격 업데이트
                        self.prices[ticker] = price
                        
                        # 마지막 메시지 시간 업데이트
                        self.last_message_time = time.time()
                        
                        # 연결 상태 확인 (첫 메시지 수신 시 연결됨으로 표시)
                        if not self.is_connected:
                            self.is_connected = True
                            self.reconnect_attempts = 0
                            print(f"✅ WebSocket 연결 확인: {ticker} 가격 수신")
                        
                        # 콜백 호출
                        if self.callback:
                            self.callback(ticker, price)
            
            except Exception as e:
                print(f"⚠️  Queue 처리 오류: {e}")
                time.sleep(0.1)
    
    def _connect_thread(self):
        """WebSocket 연결 (별도 스레드에서 실행)"""
        try:
            # Queue 생성
            if self.queue is None:
                self.queue = multiprocessing.Queue()
            
            # Queue 처리 스레드 시작 (아직 시작하지 않았다면)
            if self.queue_thread is None or not self.queue_thread.is_alive():
                self.queue_thread = threading.Thread(target=self._process_queue, daemon=True)
                self.queue_thread.start()
            
            # pyupbit.WebSocketClient는 type, codes, queue를 받음
            # __init__에서 블로킹되므로 별도 스레드에서 실행
            self.ws = pyupbit.WebSocketClient(
                type="ticker",
                codes=self.tickers,
                queue=self.queue
            )
            
            print(f"✅ WebSocket 연결 시작: {len(self.tickers)}개 코인 구독")
            
        except Exception as e:
            print(f"❌ WebSocket 연결 실패: {e}")
            self.is_connected = False
            if self.running:
                if self.reconnect_attempts < self.max_reconnect_attempts:
                    self.reconnect_attempts += 1
                    print(f"🔄 재연결 시도 {self.reconnect_attempts}/{self.max_reconnect_attempts}...")
                    time.sleep(self.reconnect_interval)
                    # 재연결도 별도 스레드에서
                    reconnect_thread = threading.Thread(target=self._connect_thread, daemon=True)
                    reconnect_thread.start()
                else:
                    print(f"❌ 최대 재연결 시도 횟수 초과")
    
    def _connect(self):
        """WebSocket 연결 (비블로킹)"""
        # WebSocketClient는 블로킹되므로 별도 스레드에서 실행
        connect_thread = threading.Thread(target=self._connect_thread, daemon=True)
        connect_thread.start()
    
    def reconnect(self):
        """수동 재연결"""
        if self.running:
            print("🔄 WebSocket 수동 재연결 시도...")
            self.reconnect_attempts = 0
            self.is_connected = False
            # WebSocketClient는 자동으로 재연결되므로, 새로운 인스턴스 생성
            # _connect()는 이미 별도 스레드에서 실행됨
            self._connect()
    
    def is_healthy(self) -> bool:
        """
        WebSocket 연결 상태 확인
        
        Returns:
            연결이 정상이면 True
        """
        if not self.running or not self.is_connected:
            return False
        
        # 마지막 메시지 수신 시간 확인
        if self.last_message_time:
            elapsed = time.time() - self.last_message_time
            if elapsed > self.connection_timeout:
                print(f"⚠️  WebSocket 비정상: {elapsed:.1f}초 동안 메시지 없음")
                self.is_connected = False
                return False
        
        return True
    
    def start(self):
        """가격 구독 시작"""
        if self.running:
            print("⚠️  이미 구독 중입니다.")
            return
        
        self.running = True
        print(f"🚀 가격 구독 시작: {', '.join(self.tickers)}")
        self._connect()
    
    def stop(self):
        """가격 구독 중지"""
        self.running = False
        self.is_connected = False
        # WebSocketClient는 프로세스에서 실행되므로 명시적으로 종료할 수 없음
        # running 플래그로 제어
        print("⏹️  가격 구독 중지")
    
    def update_tickers(self, new_tickers: List[str]):
        """
        구독할 코인 목록 업데이트
        
        Args:
            new_tickers: 새로운 코인 티커 리스트
        """
        was_running = self.running
        
        if was_running:
            self.stop()
        
        self.tickers = new_tickers
        self.prices = {}
        
        if was_running:
            self.start()
        
        print(f"📝 구독 코인 업데이트: {', '.join(new_tickers)}")
    
    def get_price(self, ticker: str) -> Optional[float]:
        """
        현재 가격 조회
        
        Args:
            ticker: 조회할 티커
            
        Returns:
            현재 가격 (없으면 None)
        """
        return self.prices.get(ticker)
    
    def get_all_prices(self) -> Dict[str, float]:
        """
        모든 구독 중인 코인의 현재 가격 조회
        
        Returns:
            {ticker: price} 딕셔너리
        """
        return self.prices.copy()


# 간단한 테스트용 동기식 가격 조회 함수
def get_current_prices(tickers: List[str], use_websocket: bool = False, timeout: int = 10) -> Dict[str, float]:
    """
    여러 코인의 현재가를 조회
    
    Args:
        tickers: 조회할 티커 리스트
        use_websocket: True면 WebSocket 사용, False면 REST API 사용 (기본값: False)
        timeout: WebSocket 사용 시 타임아웃 (초, 기본값: 10)
        
    Returns:
        {ticker: price} 딕셔너리
    """
    if use_websocket:
        # WebSocket으로 구독하여 한 번 가격 받고 해지
        return get_current_prices_via_websocket(tickers, timeout)
    else:
        # REST API 사용 (기존 방식)
        prices = {}
        for i, ticker in enumerate(tickers):
            try:
                # Rate limiting 방지: 코인 사이에 0.3초 대기
                if i > 0:
                    time.sleep(0.3)
                
                price = pyupbit.get_current_price(ticker)
                if price and price > 0:  # price가 None이거나 0이면 실패
                    prices[ticker] = price
                else:
                    # 가격이 None이거나 0인 경우
                    if price == 0:
                        print(f"⚠️  {ticker} 가격 조회 실패: 가격이 0 (일시적 오류 또는 코인 없음)")
                    else:
                        print(f"⚠️  {ticker} 가격 조회 실패: 가격 정보 없음 (업비트에 존재하지 않을 수 있음)")
            except Exception as e:
                error_msg = str(e)
                # "Code not found"는 업비트에 해당 코인이 없다는 의미
                if "Code not found" in error_msg or "not found" in error_msg.lower():
                    print(f"⚠️  {ticker} 가격 조회 실패: 업비트에 존재하지 않는 코인입니다")
                else:
                    print(f"⚠️  {ticker} 가격 조회 실패: {e}")
        
        return prices


def get_current_prices_and_volumes(tickers: List[str]) -> Dict[str, Dict]:
    """
    여러 코인의 현재가와 24시간 거래량을 함께 조회
    
    Args:
        tickers: 조회할 티커 리스트
        
    Returns:
        {ticker: {"price": price, "volume": volume}} 딕셔너리
    """
    result = {}
    for i, ticker in enumerate(tickers):
        try:
            # Rate limiting 방지: 코인 사이에 0.3초 대기
            if i > 0:
                time.sleep(0.3)
            
            # get_ticker()로 가격과 거래량 함께 조회
            ticker_info = pyupbit.get_ticker(ticker)
            if ticker_info:
                price = ticker_info.get("trade_price")
                volume = ticker_info.get("acc_trade_volume_24h")  # 24시간 거래량
                
                if price and price > 0:
                    result[ticker] = {
                        "price": price,
                        "volume": volume if volume else 0.0
                    }
                else:
                    if price == 0:
                        print(f"⚠️  {ticker} 가격 조회 실패: 가격이 0 (일시적 오류 또는 코인 없음)")
                    else:
                        print(f"⚠️  {ticker} 가격 조회 실패: 가격 정보 없음")
            else:
                print(f"⚠️  {ticker} 티커 정보 조회 실패")
        except Exception as e:
            error_msg = str(e)
            if "Code not found" in error_msg or "not found" in error_msg.lower():
                print(f"⚠️  {ticker} 티커 정보 조회 실패: 업비트에 존재하지 않는 코인입니다")
            else:
                print(f"⚠️  {ticker} 티커 정보 조회 실패: {e}")
    
    return result


def get_current_prices_via_websocket(tickers: List[str], timeout: int = 10) -> Dict[str, float]:
    """
    WebSocket을 사용하여 여러 코인의 현재가를 한 번 조회하고 구독 해지
    
    Args:
        tickers: 조회할 티커 리스트
        timeout: 타임아웃 (초, 기본값: 10)
        
    Returns:
        {ticker: price} 딕셔너리
    """
    if not tickers:
        return {}
    
    prices: Dict[str, float] = {}
    received_tickers = set()
    subscriber = None
    
    def price_callback(ticker: str, price: float):
        """가격 업데이트 콜백"""
        nonlocal prices, received_tickers
        if ticker not in received_tickers:
            prices[ticker] = price
            received_tickers.add(ticker)
    
    try:
        # PriceSubscriber 생성 및 시작
        subscriber = PriceSubscriber(tickers=tickers, callback=price_callback)
        subscriber.start()
        
        # 모든 코인의 가격을 받을 때까지 대기 (또는 타임아웃)
        start_time = time.time()
        while len(received_tickers) < len(tickers):
            elapsed = time.time() - start_time
            if elapsed > timeout:
                print(f"⚠️  WebSocket 타임아웃 ({timeout}초): {len(received_tickers)}/{len(tickers)}개 코인 가격 수신")
                break
            
            # 연결 확인
            if not subscriber.is_healthy() and elapsed > 3:
                # 3초 이상 연결되지 않으면 실패로 간주
                print(f"⚠️  WebSocket 연결 실패, REST API로 폴백")
                subscriber.stop()
                return get_current_prices(tickers, use_websocket=False)
            
            time.sleep(0.1)
        
        # 구독 해지
        subscriber.stop()
        
        # 받지 못한 코인은 REST API로 조회
        missing_tickers = set(tickers) - received_tickers
        if missing_tickers:
            print(f"⚠️  WebSocket으로 받지 못한 코인 {len(missing_tickers)}개를 REST API로 조회...")
            rest_prices = get_current_prices(list(missing_tickers), use_websocket=False)
            prices.update(rest_prices)
        
        print(f"✅ WebSocket으로 {len(received_tickers)}개 코인 가격 수신 완료")
        return prices
        
    except Exception as e:
        print(f"⚠️  WebSocket 가격 조회 실패: {e}, REST API로 폴백")
        if subscriber:
            try:
                subscriber.stop()
            except:
                pass
        # REST API로 폴백
        return get_current_prices(tickers, use_websocket=False)

