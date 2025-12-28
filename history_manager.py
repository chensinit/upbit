"""
거래 히스토리 관리 모듈
거래 내역을 수집하고 분석하여 Gemini API에 전달할 수 있는 형태로 정리합니다.
"""
import pyupbit
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from upbit_trader import UpbitTrader


class HistoryManager:
    """거래 히스토리 관리 클래스"""
    
    def __init__(self, trader: UpbitTrader):
        """
        초기화
        
        Args:
            trader: UpbitTrader 인스턴스
        """
        self.trader = trader
        self.trade_history: List[Dict] = []
    
    def get_recent_trades(self, days: int = 7, tickers: List[str] = None) -> List[Dict]:
        """
        최근 거래 내역 조회 (모든 코인)
        
        Args:
            days: 조회할 일수 (기본 7일, 참고용 - 실제로는 API 제한에 따름)
            tickers: 조회할 티커 리스트 (None이면 보유 코인에서 자동 조회)
            
        Returns:
            거래 내역 리스트
        """
        try:
            # 업비트 API로 최근 주문 내역 조회
            # pyupbit의 get_order는 ticker_or_uuid가 필수이므로, 보유 중인 코인만 조회
            all_orders = []
            
            # 조회할 티커 목록 결정
            if tickers is None:
                # 보유 코인에서 자동 조회 (가격 조회 없이 잔고만 확인)
                balances = self.trader.get_all_balances()
                tickers_to_check = set()
                for balance in balances:
                    currency = balance.get('currency', '')
                    balance_amount = float(balance.get('balance', 0))
                    if currency != "KRW" and balance_amount > 0:
                        tickers_to_check.add(f"KRW-{currency}")
            else:
                tickers_to_check = set(tickers)
            
            # 보유 코인이 없으면 빈 리스트 반환
            if not tickers_to_check:
                return []
            
            print(f"🔍 거래 내역 조회 대상 코인: {len(tickers_to_check)}개")
            
            # 각 코인별로 최근 주문만 조회 (효율성을 위해 각 코인당 최대 30개만)
            found_orders_count = 0
            for ticker in tickers_to_check:
                try:
                    # 최근 30개 주문만 조회 (1페이지, limit=30)
                    orders = self.trader.upbit.get_order(ticker, state="done", page=1, limit=30)
                    if orders:
                        if not isinstance(orders, list):
                            orders = [orders]
                        all_orders.extend(orders)
                        found_orders_count += len(orders)
                except Exception as e:
                    # 특정 코인 조회 실패 시 스킵 (로그는 출력하지 않음 - 너무 많을 수 있음)
                    continue
            
            print(f"📋 총 {found_orders_count}개 주문 조회됨 (각 코인당 최대 30개)")
            orders = all_orders
            
            # 날짜 필터링 (지정된 일수 이내의 거래만)
            cutoff_date = datetime.now() - timedelta(days=days)
            
            trades = []
            skipped_count = 0
            for order in orders:
                # 주문이 딕셔너리인지 확인
                if isinstance(order, dict):
                    created_at_str = order.get("created_at", "")
                    
                    # 날짜 파싱 및 필터링
                    try:
                        if created_at_str:
                            # ISO 형식: "2024-01-01T00:00:00+09:00" 또는 "2024-01-01T00:00:00"
                            # 타임존 정보를 유지한 채로 파싱
                            try:
                                # 타임존 정보가 있으면 그대로 파싱
                                if "+" in created_at_str or created_at_str.endswith("Z"):
                                    created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                                    # 타임존을 제거하고 naive datetime으로 변환 (비교를 위해)
                                    if created_at.tzinfo:
                                        created_at = created_at.replace(tzinfo=None)
                                else:
                                    created_at = datetime.fromisoformat(created_at_str)
                            except ValueError:
                                # ISO 형식이 아닌 경우 다른 형식 시도
                                try:
                                    from dateutil import parser
                                    created_at = parser.parse(created_at_str)
                                    if created_at.tzinfo:
                                        created_at = created_at.replace(tzinfo=None)
                                except:
                                    # 파싱 실패 시 스킵
                                    skipped_count += 1
                                    continue
                            
                            # 지정된 일수 이내의 거래만 포함
                            if created_at < cutoff_date:
                                skipped_count += 1
                                continue
                        else:
                            # created_at이 없으면 제외 (날짜 정보가 없으면 필터링 불가)
                            skipped_count += 1
                            continue
                    except Exception as e:
                        # 날짜 파싱 실패 시 해당 주문은 스킵
                        skipped_count += 1
                        continue
                    
                    # 주문 가격 정보 확인 (시장가 주문의 경우 price가 0일 수 있음)
                    order_price = order.get("price", 0)
                    if not order_price or order_price == 0:
                        # 시장가 주문의 경우 평균 체결가 사용
                        order_price = order.get("avg_price", 0)
                    if not order_price or order_price == 0:
                        # 그래도 없으면 체결 금액 / 체결 수량으로 계산
                        executed_funds = float(order.get("executed_funds", 0))
                        executed_volume = float(order.get("executed_volume", 0))
                        if executed_volume > 0:
                            order_price = executed_funds / executed_volume
                    
                    executed_volume = float(order.get("executed_volume", 0))
                    
                    trade = {
                        "ticker": order.get("market", ""),
                        "side": order.get("side", ""),  # "bid" (매수) or "ask" (매도)
                        "price": float(order_price) if order_price else 0.0,
                        "volume": executed_volume,
                        "created_at": created_at_str,
                        "uuid": order.get("uuid", "")
                    }
                    # 유효한 거래만 추가 (티커가 있고, 수량이 0보다 크고, 가격이 0보다 큰 경우)
                    if trade["ticker"] and trade["volume"] > 0 and trade["price"] > 0:
                        trades.append(trade)
                    else:
                        # 디버깅: 왜 거래가 제외되었는지 로그 (첫 번째 거래만)
                        if len(trades) == 0 and len(all_orders) <= 5:  # 거래가 적을 때만 로그
                            if not trade["ticker"]:
                                print(f"⚠️  거래 제외: 티커 없음 - order keys: {order.keys()}")
                            elif trade["volume"] <= 0:
                                print(f"⚠️  거래 제외: 수량 0 (executed_volume={executed_volume}) - order: {order.get('market', 'N/A')}")
                            elif trade["price"] <= 0:
                                print(f"⚠️  거래 제외: 가격 0 (price={order.get('price')}, avg_price={order.get('avg_price')}, executed_funds={order.get('executed_funds')}) - order: {order.get('market', 'N/A')}")
            
            print(f"✅ {len(trades)}개 거래 내역 필터링 완료 (날짜 필터로 {skipped_count}개 제외)")
            
            # 날짜순 정렬 (최신순)
            trades.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            
            # 최대 15개만 반환 (너무 많으면 제한, 최신순으로)
            if len(trades) > 15:
                trades = trades[:15]
                print(f"📌 최신 15개 거래만 반환 (총 {len(trades) + skipped_count}개 중)")
            
            return trades
        
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
    
    def format_for_gemini(self, current_prices: Dict[str, float] = None) -> str:
        """
        Gemini API에 전달할 형태로 거래 히스토리 포맷팅
        
        Args:
            current_prices: 이미 조회한 현재가 딕셔너리 (선택사항, 있으면 재사용)
        
        Returns:
            포맷팅된 문자열
        """
        # 거래 내역은 보유 코인만 조회해야 함 (구독 코인이 아닌 보유 코인)
        # tickers를 None으로 설정하면 get_recent_trades가 보유 코인을 자동으로 조회함
        summary = self.get_trade_summary(tickers=None)
        recent_trades = self.get_recent_trades(days=7, tickers=None)
        
        # 손익 정보 포맷팅
        if summary['profit_loss'] is not None:
            profit_text = f"- 손익: {summary['profit_loss']:,.0f}원 ({summary['profit_loss_rate']:.2f}%)"
        else:
            profit_text = "- 손익: 계산 불가 (매도 거래 없음)"
        
        text = f"""## 거래 히스토리 요약

### 최근 거래 통계
- 총 거래 횟수: {summary['total_trades']}회
- 매수 횟수: {summary['buy_count']}회
- 매도 횟수: {summary['sell_count']}회
- 총 매수 금액: {summary['total_buy_amount']:,.0f}원
- 총 매도 금액: {summary['total_sell_amount']:,.0f}원
{profit_text}
"""
        
        # 거래 내역 표시
        text += f"\n### 최근 거래 내역\n"
        if recent_trades:
            for trade in recent_trades[:10]:  # 최근 10건만 표시
                side = "매수" if trade['side'] == 'bid' else "매도"
                # 거래 금액 계산
                trade_amount = trade['price'] * trade['volume']
                text += f"- {side}: {trade['ticker']} {trade['volume']:.8f}개 "
                text += f"@ {trade['price']:,.0f}원 (총 {trade_amount:,.0f}원) - {trade['created_at']}\n"
        else:
            text += "- 거래 내역 없음\n"
        
        return text

