"""
거래 히스토리 관리 모듈
거래 내역을 수집하고 분석하여 Gemini API에 전달할 수 있는 형태로 정리합니다.
"""
import json
import os
from pathlib import Path
import pyupbit
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from upbit_trader import UpbitTrader


class HistoryManager:
    """거래 히스토리 관리 클래스"""
    
    def __init__(self, trader: UpbitTrader, history_dir: str = "data"):
        """
        초기화
        
        Args:
            trader: UpbitTrader 인스턴스
            history_dir: 거래 내역 저장 디렉토리
        """
        self.trader = trader
        self.trade_history: List[Dict] = []
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(exist_ok=True)
        self.trade_history_file = self.history_dir / "trade_history.json"
    
    def _load_trade_history(self) -> List[Dict]:
        """
        저장된 거래 내역 로드
        
        Returns:
            거래 내역 리스트
        """
        if not self.trade_history_file.exists():
            return []
        
        try:
            with open(self.trade_history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                trades = data.get("trades", [])
                print(f"📂 저장된 거래 내역 로드: {len(trades)}개")
                return trades
        except Exception as e:
            print(f"⚠️  거래 내역 로드 실패: {e}")
            return []
    
    def _save_trade_history(self, trades: List[Dict]):
        """
        거래 내역 저장
        
        Args:
            trades: 저장할 거래 내역 리스트
        """
        try:
            data = {
                "trades": trades,
                "updated_at": datetime.now().isoformat()
            }
            with open(self.trade_history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"💾 거래 내역 저장: {len(trades)}개")
        except Exception as e:
            print(f"⚠️  거래 내역 저장 실패: {e}")
    
    def _parse_trade_date(self, created_at_str: str) -> Optional[datetime]:
        """
        거래 날짜 파싱
        
        Args:
            created_at_str: 날짜 문자열
            
        Returns:
            파싱된 datetime 객체 (실패 시 None)
        """
        if not created_at_str:
            return None
        
        try:
            # ISO 형식: "2024-01-01T00:00:00+09:00" 또는 "2024-01-01T00:00:00"
            if "+" in created_at_str or created_at_str.endswith("Z"):
                created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at.tzinfo:
                    created_at = created_at.replace(tzinfo=None)
            else:
                created_at = datetime.fromisoformat(created_at_str)
            return created_at
        except ValueError:
            try:
                from dateutil import parser
                created_at = parser.parse(created_at_str)
                if created_at.tzinfo:
                    created_at = created_at.replace(tzinfo=None)
                return created_at
            except:
                return None
    
    def _sync_trade_history(self, tickers: List[str] = None):
        """
        API에서 가져온 거래 내역을 저장된 거래 내역과 동기화
        
        Args:
            tickers: 조회할 티커 리스트 (None이면 보유 코인만 조회)
        """
        try:
            # 저장된 거래 내역 로드
            saved_trades = self._load_trade_history()
            saved_uuids = {trade.get("uuid") for trade in saved_trades if trade.get("uuid")}
            
            # 조회할 티커 목록 결정 (보유 코인만)
            if tickers is None:
                balances = self.trader.get_all_balances()
                tickers = []
                for balance in balances:
                    currency = balance.get('currency', '')
                    balance_amount = float(balance.get('balance', 0))
                    if currency != "KRW" and balance_amount > 0:
                        tickers.append(f"KRW-{currency}")
            
            if not tickers:
                print("✅ 보유 코인이 없어 거래 내역 조회를 스킵합니다.")
                return
            
            print(f"🔍 보유 코인 {len(tickers)}개 거래 내역 조회 중...")
            
            # API에서 최근 거래 조회 (보유 코인만)
            api_trades = self._fetch_trades_from_api(tickers=tickers)
            
            # 새로운 거래만 추가 (uuid 기준으로 중복 체크)
            new_trades = []
            for trade in api_trades:
                uuid = trade.get("uuid")
                if uuid and uuid not in saved_uuids:
                    new_trades.append(trade)
                    saved_uuids.add(uuid)
            
            if new_trades:
                print(f"🆕 새로운 거래 {len(new_trades)}개 발견")
                # 기존 거래와 합치고 날짜순 정렬
                all_trades = saved_trades + new_trades
                all_trades.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                # 저장 (최대 1000개만 유지 - 너무 많아지지 않도록)
                if len(all_trades) > 1000:
                    all_trades = all_trades[:1000]
                    print(f"📌 거래 내역이 1000개를 초과하여 최신 1000개만 유지")
                self._save_trade_history(all_trades)
            else:
                print(f"✅ 새로운 거래 없음 (저장된 거래: {len(saved_trades)}개)")
        
        except Exception as e:
            print(f"⚠️  거래 내역 동기화 실패: {e}")
    
    def _fetch_trades_from_api(self, tickers: List[str] = None) -> List[Dict]:
        """
        API에서 거래 내역 조회 (내부 메서드)
        
        Args:
            tickers: 조회할 티커 리스트 (None이면 보유 코인에서 자동 조회)
            
        Returns:
            거래 내역 리스트
        """
        try:
            all_orders = []
            
            # 조회할 티커 목록 결정
            if tickers is None:
                balances = self.trader.get_all_balances()
                tickers_to_check = set()
                for balance in balances:
                    currency = balance.get('currency', '')
                    balance_amount = float(balance.get('balance', 0))
                    if currency != "KRW" and balance_amount > 0:
                        tickers_to_check.add(f"KRW-{currency}")
            else:
                tickers_to_check = set(tickers)
            
            if not tickers_to_check:
                return []
            
            # 각 코인별로 최근 주문만 조회
            for i, ticker in enumerate(tickers_to_check):
                try:
                    # Rate limiting 방지: 코인 사이에 0.3초 대기
                    if i > 0:
                        time.sleep(0.3)
                    
                    orders = self.trader.upbit.get_order(ticker, state="done", page=1, limit=30)
                    if orders:
                        if not isinstance(orders, list):
                            orders = [orders]
                        all_orders.extend(orders)
                except Exception:
                    continue
            
            # 주문을 거래 형식으로 변환
            trades = []
            for order in all_orders:
                if isinstance(order, dict):
                    created_at_str = order.get("created_at", "")
                    if not created_at_str:
                        continue
                    
                    # 주문 가격 정보 확인
                    order_price = order.get("price", 0)
                    if not order_price or order_price == 0:
                        order_price = order.get("avg_price", 0)
                    if not order_price or order_price == 0:
                        executed_funds = float(order.get("executed_funds", 0))
                        executed_volume = float(order.get("executed_volume", 0))
                        if executed_volume > 0:
                            order_price = executed_funds / executed_volume
                    
                    executed_volume = float(order.get("executed_volume", 0))
                    
                    trade = {
                        "ticker": order.get("market", ""),
                        "side": order.get("side", ""),
                        "price": float(order_price) if order_price else 0.0,
                        "volume": executed_volume,
                        "created_at": created_at_str,
                        "uuid": order.get("uuid", "")
                    }
                    
                    if trade["ticker"] and trade["volume"] > 0 and trade["price"] > 0:
                        trades.append(trade)
            
            return trades
        
        except Exception as e:
            print(f"⚠️  API 거래 내역 조회 실패: {e}")
            return []
    
    def get_recent_trades(self, days: int = 7, tickers: List[str] = None) -> List[Dict]:
        """
        저장된 거래 내역에서 최근 거래 조회 (최근 15개)
        
        Args:
            days: 조회할 일수 (참고용, 실제로는 저장된 거래에서 최근 15개 반환)
            tickers: 조회할 티커 리스트 (None이면 전체)
            
        Returns:
            거래 내역 리스트 (최근 15개)
        """
        try:
            # 먼저 API에서 새로운 거래 동기화
            self._sync_trade_history(tickers=tickers)
            
            # 저장된 거래 내역 로드
            all_trades = self._load_trade_history()
            
            # 티커 필터링
            if tickers:
                tickers_set = set(tickers)
                all_trades = [t for t in all_trades if t.get("ticker") in tickers_set]
            
            # 날짜순 정렬 (최신순)
            all_trades.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            # 최근 15개만 반환
            recent_trades = all_trades[:15]
            
            print(f"✅ 저장된 거래 내역에서 최근 {len(recent_trades)}개 조회 (전체 {len(all_trades)}개 중)")
            
            return recent_trades
        
        except Exception as e:
            print(f"⚠️  거래 내역 조회 실패: {e}")
            return []
    
    def get_trade_summary(self, ticker: Optional[str] = None, tickers: List[str] = None) -> Dict:
        """
        거래 요약 정보 생성
        
        Args:
            ticker: 특정 코인만 조회 (None이면 전체)
            tickers: 조회할 티커 리스트 (None이면 보유 코인에서 자동 조회)
            
        Returns:
            거래 요약 딕셔너리
        """
        trades = self.get_recent_trades(days=7, tickers=tickers)
        
        if ticker:
            trades = [t for t in trades if t["ticker"] == ticker]
        
        if not trades:
            return {
                "total_trades": 0,
                "buy_count": 0,
                "sell_count": 0,
                "total_buy_amount": 0,
                "total_sell_amount": 0,
                "profit_loss": 0,
                "profit_loss_rate": 0
            }
        
        buy_trades = [t for t in trades if t["side"] == "bid"]
        sell_trades = [t for t in trades if t["side"] == "ask"]
        
        total_buy_amount = sum(t["price"] * t["volume"] for t in buy_trades)
        total_sell_amount = sum(t["price"] * t["volume"] for t in sell_trades)
        
        # 손익 계산: 매도한 거래만 기준으로 계산
        # 매수만 하고 매도하지 않은 경우는 손익 계산 불가
        if total_sell_amount > 0:
            # 매도 거래가 있으면 손익 계산
            profit_loss = total_sell_amount - total_buy_amount
            profit_loss_rate = ((total_sell_amount - total_buy_amount) / total_buy_amount * 100) if total_buy_amount > 0 else 0
        else:
            # 매도 거래가 없으면 손익 계산 불가 (매수만 한 상태)
            profit_loss = None
            profit_loss_rate = None
        
        return {
            "total_trades": len(trades),
            "buy_count": len(buy_trades),
            "sell_count": len(sell_trades),
            "total_buy_amount": total_buy_amount,
            "total_sell_amount": total_sell_amount,
            "profit_loss": profit_loss,
            "profit_loss_rate": profit_loss_rate
        }
    
    def get_portfolio_status(self, current_prices: Dict[str, float] = None) -> Dict:
        """
        현재 포트폴리오 상태 조회
        
        Args:
            current_prices: 이미 조회한 현재가 딕셔너리 (선택사항, 있으면 재사용)
        
        Returns:
            포트폴리오 상태 딕셔너리
        """
        balances = self.trader.get_all_balances()
        
        portfolio = {
            "krw_balance": self.trader.get_balance("KRW"),
            "holdings": []
        }
        
        total_value = portfolio["krw_balance"]
        
        for balance in balances:
            currency = balance.get('currency', '')
            balance_amount = float(balance.get('balance', 0))
            
            if currency != "KRW" and balance_amount > 0:
                ticker = f"KRW-{currency}"
                try:
                    # 이미 조회한 가격이 있으면 재사용
                    if current_prices and ticker in current_prices:
                        current_price = current_prices[ticker]
                    else:
                        # 가격이 없으면 조회
                        current_price = self.trader.get_current_price(ticker, retry=2)
                        if current_price is None:
                            # 가격 조회 실패 시 재시도 (다른 방법으로 시도)
                            try:
                                import pyupbit
                                current_price = pyupbit.get_current_price(ticker)
                                if current_price is None:
                                    print(f"⚠️  {ticker} 가격 조회 실패, 0원으로 표시")
                                    current_price = 0.0
                            except Exception:
                                print(f"⚠️  {ticker} 가격 조회 실패, 0원으로 표시")
                                current_price = 0.0
                    
                    total_value_coin = balance_amount * current_price
                    total_value += total_value_coin
                    
                    # 평균 매수가 계산 (간단히 현재가로 대체, 실제로는 거래 내역에서 계산 필요)
                    portfolio["holdings"].append({
                        "ticker": ticker,
                        "currency": currency,
                        "amount": balance_amount,
                        "current_price": current_price,
                        "total_value": total_value_coin,
                        "profit_loss": 0,  # 실제로는 평균 매수가와 비교 필요
                        "profit_loss_rate": 0
                    })
                except Exception as e:
                    print(f"⚠️  {ticker} 정보 조회 실패: {e}")
        
        portfolio["total_value"] = total_value
        
        return portfolio
    
    def format_for_gemini(self, current_prices: Dict[str, float] = None, tickers: List[str] = None) -> str:
        """
        Gemini API에 전달할 형태로 거래 히스토리 포맷팅
        
        Args:
            current_prices: 이미 조회한 현재가 딕셔너리 (선택사항, 있으면 재사용)
            tickers: 조회할 티커 리스트 (None이면 보유 코인만 조회, 저장된 거래 내역 사용)
        
        Returns:
            포맷팅된 문자열
        """
        # 임시: 거래 내역은 저장만 하고 prompt에는 포함하지 않음
        # 거래 내역은 계속 저장하도록 동기화만 수행
        try:
            self._sync_trade_history(tickers=tickers)
        except Exception as e:
            print(f"⚠️  거래 내역 동기화 실패 (무시): {e}")
        
        # 빈 문자열 반환 (거래 내역을 prompt에 포함하지 않음)
        return ""

