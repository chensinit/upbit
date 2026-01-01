"""
가격 히스토리 관리 모듈
구독 중인 코인의 가격을 주기적으로 저장하고, 변화 추이를 제공합니다.

하이브리드 저장 방식:
- 최근 24시간: 10분 간격 상세 데이터
- 24시간~7일: 1시간 간격 데이터 (OHLC)
- 7일 이상: 1일 간격 데이터 (OHLC)
"""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pyupbit


class PriceHistoryManager:
    """가격 히스토리 관리 클래스"""
    
    def __init__(self, data_dir: str = "data/price_history"):
        """
        초기화
        
        Args:
            data_dir: 가격 히스토리 저장 디렉토리
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 메모리 캐시 (최근 24시간 상세 데이터)
        self.price_cache: Dict[str, List[Dict]] = {}
        self.max_cache_size = 144  # 최근 24시간 (10분 간격 = 144개)
    
    def _calculate_rsi_from_prices(self, prices: List[float], period: int) -> Optional[float]:
        """
        가격 리스트로부터 RSI 계산 (내부 헬퍼 함수)
        
        Args:
            prices: 가격 리스트 (오래된 순서)
            period: RSI 계산 기간
            
        Returns:
            RSI 값 (0-100), 데이터 부족 시 None
        """
        if len(prices) < period + 1:
            return None
        
        # 가격 변화 계산
        gains = []  # 상승폭
        losses = []  # 하락폭
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(change))
        
        # 최근 period일의 평균 상승폭/하락폭 계산
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        # RS와 RSI 계산
        if avg_loss == 0:
            return 100.0  # 하락이 없으면 RSI = 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi, 2)
    
    def calculate_daily_rsi(self, ticker: str, period: int = 14, min_days: int = 6) -> Optional[float]:
        """
        일자별 RSI 계산 (14일 기준, 최소 6일 이상 필요)
        
        Args:
            ticker: 코인 티커
            period: RSI 계산 기간 (기본값: 14일)
            min_days: 최소 필요 일수 (기본값: 6일)
            
        Returns:
            RSI 값 (0-100), 데이터 부족 시 None
        """
        try:
            data = self._load_all_data(ticker)
            daily = data.get("daily", [])
            
            # 최소 min_days 이상 데이터 필요
            if len(daily) < min_days:
                return None
            
            # 사용 가능한 데이터로 실제 계산 기간 결정
            actual_period = min(len(daily) - 1, period)  # 변화율 계산을 위해 -1
            
            if actual_period < min_days - 1:
                return None
            
            # 최근 actual_period+1일 가격 추출 (오래된 순서)
            prices = []
            for item in daily[-actual_period-1:]:
                close_price = item.get("close")
                if close_price and close_price > 0:
                    prices.append(close_price)
            
            if len(prices) < actual_period + 1:
                return None
            
            return self._calculate_rsi_from_prices(prices, actual_period)
        
        except Exception as e:
            print(f"⚠️  일자별 RSI 계산 실패 ({ticker}): {e}")
            return None
    
    def calculate_10min_rsi(self, ticker: str, period: int = 14) -> Optional[float]:
        """
        10분 간격 RSI 계산 (14개 기준)
        
        Args:
            ticker: 코인 티커
            period: RSI 계산 기간 (기본값: 14개 = 140분)
            
        Returns:
            RSI 값 (0-100), 데이터 부족 시 None
        """
        try:
            data = self._load_all_data(ticker)
            detailed = data.get("detailed", [])
            
            # 최소 period+1개 데이터 필요
            if len(detailed) < period + 1:
                return None
            
            # 최근 period+1개 가격 추출 (오래된 순서)
            prices = []
            for item in detailed[-period-1:]:
                price = item.get("price")
                if price and price > 0:
                    prices.append(price)
            
            if len(prices) < period + 1:
                return None
            
            return self._calculate_rsi_from_prices(prices, period)
        
        except Exception as e:
            print(f"⚠️  10분 간격 RSI 계산 실패 ({ticker}): {e}")
            return None
    
    def calculate_hourly_rsi(self, ticker: str, period: int = 14) -> Optional[float]:
        """
        시간 단위 RSI 계산 (14시간 기준)
        
        Args:
            ticker: 코인 티커
            period: RSI 계산 기간 (기본값: 14시간)
            
        Returns:
            RSI 값 (0-100), 데이터 부족 시 None
        """
        try:
            data = self._load_all_data(ticker)
            hourly = data.get("hourly", [])
            
            # 최소 period+1개 데이터 필요
            if len(hourly) < period + 1:
                return None
            
            # 최근 period+1개 가격 추출 (오래된 순서, close 사용)
            prices = []
            for item in hourly[-period-1:]:
                close_price = item.get("close")
                if close_price and close_price > 0:
                    prices.append(close_price)
            
            if len(prices) < period + 1:
                return None
            
            return self._calculate_rsi_from_prices(prices, period)
        
        except Exception as e:
            print(f"⚠️  시간 단위 RSI 계산 실패 ({ticker}): {e}")
            return None
    
    def save_price(self, ticker: str, price: float, volume: float = None, timestamp: datetime = None) -> bool:
        """
        가격 저장 (10분 간격)
        
        Args:
            ticker: 코인 티커
            price: 가격
            volume: 24시간 거래량 (선택사항)
            timestamp: 타임스탬프 (None이면 현재 시간)
            
        Returns:
            저장 성공 여부
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            # 파일 경로
            filepath = self.data_dir / f"{ticker.replace('KRW-', '')}.json"
            
            # 기존 데이터 로드
            data = self._load_all_data(ticker)
            
            # 상세 데이터에 추가 (최근 7일, RSI 계산을 위해)
            detailed = data.get("detailed", [])
            price_data = {
                "timestamp": timestamp.isoformat(),
                "price": price
            }
            if volume is not None:
                price_data["volume"] = volume
            # RSI는 저장하지 않음 (항상 현재 시점 기준으로 계산해야 하므로)
            detailed.append(price_data)
            
            # 7일 이전 데이터는 압축 (RSI 계산을 위해 7일 동안 10분 데이터 유지)
            cutoff_7d_detailed = timestamp - timedelta(days=7)
            detailed_7d = []
            to_compress = []
            
            for item in detailed:
                item_time = datetime.fromisoformat(item["timestamp"])
                if item_time > cutoff_7d_detailed:
                    detailed_7d.append(item)
                else:
                    to_compress.append(item)
            
            # 압축할 데이터가 있으면 1시간 단위로 압축
            if to_compress:
                self._compress_to_hourly(ticker, to_compress, data)
            
            # 7일 이전 시간별 데이터는 일별로 압축
            cutoff_7d = timestamp - timedelta(days=7)
            hourly = data.get("hourly", [])
            hourly_recent = []
            to_compress_daily = []
            
            for item in hourly:
                item_time = datetime.fromisoformat(item["timestamp"])
                if item_time > cutoff_7d:
                    hourly_recent.append(item)
                else:
                    to_compress_daily.append(item)
            
            # 일별로 압축
            if to_compress_daily:
                self._compress_to_daily(ticker, to_compress_daily, data)
            
            # 데이터 저장
            data["detailed"] = detailed_7d
            data["hourly"] = hourly_recent
            data["ticker"] = ticker
            data["last_updated"] = timestamp.isoformat()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 메모리 캐시 업데이트
            self._update_cache(ticker, price_data)
            
            return True
        
        except Exception as e:
            print(f"⚠️  가격 저장 실패 ({ticker}): {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _compress_to_hourly(self, ticker: str, data_list: List[Dict], file_data: Dict):
        """
        10분 간격 데이터를 1시간 단위로 압축
        
        Args:
            ticker: 코인 티커
            data_list: 압축할 데이터 리스트
            file_data: 파일 데이터 딕셔너리
        """
        if not data_list:
            return
        
        # 시간별로 그룹화
        hourly_groups: Dict[str, List[Dict]] = {}
        for item in data_list:
            dt = datetime.fromisoformat(item["timestamp"])
            hour_key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
            if hour_key not in hourly_groups:
                hourly_groups[hour_key] = []
            hourly_groups[hour_key].append(item)
        
        # 각 시간별로 OHLC 계산
        hourly = file_data.get("hourly", [])
        for hour_key, items in sorted(hourly_groups.items()):
            prices = [item["price"] for item in items]
            volumes = [item.get("volume", 0) for item in items if item.get("volume") is not None]
            
            hourly_item = {
                "timestamp": hour_key,
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "count": len(prices)
            }
            
            # 거래량이 있으면 평균 거래량 저장
            if volumes:
                hourly_item["volume"] = sum(volumes) / len(volumes)  # 시간당 평균 거래량
            
            hourly.append(hourly_item)
        
        file_data["hourly"] = hourly
    
    def _compress_to_daily(self, ticker: str, data_list: List[Dict], file_data: Dict):
        """
        1시간 간격 데이터를 1일 단위로 압축
        
        Args:
            ticker: 코인 티커
            data_list: 압축할 데이터 리스트
            file_data: 파일 데이터 딕셔너리
        """
        if not data_list:
            return
        
        # 일별로 그룹화
        daily_groups: Dict[str, List[Dict]] = {}
        for item in data_list:
            dt = datetime.fromisoformat(item["timestamp"])
            date_key = dt.date().isoformat()
            if date_key not in daily_groups:
                daily_groups[date_key] = []
            daily_groups[date_key].append(item)
        
        # 각 일별로 OHLC 계산
        daily = file_data.get("daily", [])
        for date_key, items in sorted(daily_groups.items()):
            opens = [item["open"] for item in items]
            highs = [item["high"] for item in items]
            lows = [item["low"] for item in items]
            closes = [item["close"] for item in items]
            
            daily.append({
                "date": date_key,
                "open": opens[0],
                "high": max(highs),
                "low": min(lows),
                "close": closes[-1],
                "count": len(items)
            })
        
        file_data["daily"] = daily
    
    def _load_all_data(self, ticker: str) -> Dict:
        """
        모든 데이터 로드 (상세/시간/일별)
        
        Args:
            ticker: 코인 티커
            
        Returns:
            데이터 딕셔너리
        """
        filepath = self.data_dir / f"{ticker.replace('KRW-', '')}.json"
        
        if not filepath.exists():
            return {
                "ticker": ticker,
                "detailed": [],
                "hourly": [],
                "daily": []
            }
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 기존 형식 호환성 (history 키가 있으면 변환)
                if "history" in data and "detailed" not in data:
                    history = data["history"]
                    data = {
                        "ticker": ticker,
                        "detailed": history,
                        "hourly": [],
                        "daily": []
                    }
                return data
        except Exception as e:
            print(f"⚠️  데이터 로드 실패 ({ticker}): {e}")
            return {
                "ticker": ticker,
                "detailed": [],
                "hourly": [],
                "daily": []
            }
    
    def fetch_historical_data(self, ticker: str) -> bool:
        """
        REST API로 과거 가격 데이터 수집 (새로 구독한 코인용)
        보수적 호출: 일별 + 시간별 데이터 수집 (호출 사이 0.5초 대기)
        
        Args:
            ticker: 코인 티커
            
        Returns:
            성공 여부
        """
        try:
            print(f"📥 {ticker} 과거 데이터 수집 중...")
            
            # 기존 데이터 로드
            data = self._load_all_data(ticker)
            
            # 1. 일별 데이터 수집 (최근 20일, RSI 계산을 위해)
            print(f"   - 일별 데이터 수집 중... (최근 20일)")
            daily_df = pyupbit.get_ohlcv(ticker, interval="day", count=20)
            
            if daily_df is not None and len(daily_df) > 0:
                # 일별 데이터 변환 및 저장
                daily = data.get("daily", [])
                for idx, row in daily_df.iterrows():
                    date_key = idx.strftime("%Y-%m-%d")
                    # 중복 체크 (이미 있으면 스킵)
                    if not any(item["date"] == date_key for item in daily):
                        daily.append({
                            "date": date_key,
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "count": 1
                        })
                data["daily"] = sorted(daily, key=lambda x: x["date"])
                print(f"   ✅ 일별 데이터 {len(daily_df)}개 수집 완료")
            else:
                print(f"   ⚠️  일별 데이터 수집 실패")
            
            # 0.3초 대기 (서버 부하 방지)
            time.sleep(0.3)
            
            # 2. 시간별 데이터 수집 (최근 3일 = 72시간)
            print(f"   - 시간별 데이터 수집 중... (최근 3일)")
            hourly_df = pyupbit.get_ohlcv(ticker, interval="minute60", count=72)
            
            if hourly_df is not None and len(hourly_df) > 0:
                # 시간별 데이터 변환 및 저장
                hourly = data.get("hourly", [])
                for idx, row in hourly_df.iterrows():
                    hour_key = idx.strftime("%Y-%m-%dT%H:00:00")
                    # 중복 체크 (이미 있으면 스킵)
                    if not any(item["timestamp"] == hour_key for item in hourly):
                        hourly_item = {
                            "timestamp": hour_key,
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "count": 1
                        }
                        # 거래량이 있으면 추가
                        if "volume" in row.index:
                            try:
                                volume_val = row["volume"]
                                # NaN이 아니고 유효한 값이면 저장
                                if volume_val is not None:
                                    volume_float = float(volume_val)
                                    # NaN 체크: float('nan') != float('nan')는 True
                                    if volume_float == volume_float:  # NaN이 아니면 True
                                        hourly_item["volume"] = volume_float
                            except (ValueError, TypeError, KeyError):
                                pass
                        hourly.append(hourly_item)
                data["hourly"] = sorted(hourly, key=lambda x: x["timestamp"])
                print(f"   ✅ 시간별 데이터 {len(hourly_df)}개 수집 완료")
            else:
                print(f"   ⚠️  시간별 데이터 수집 실패")
            
            # 데이터 저장
            data["ticker"] = ticker
            data["last_updated"] = datetime.now().isoformat()
            
            filepath = self.data_dir / f"{ticker.replace('KRW-', '')}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ {ticker} 과거 데이터 수집 완료")
            return True
        
        except Exception as e:
            print(f"⚠️  {ticker} 과거 데이터 수집 실패: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _update_cache(self, ticker: str, price_data: Dict):
        """메모리 캐시 업데이트"""
        if ticker not in self.price_cache:
            self.price_cache[ticker] = []
        
        self.price_cache[ticker].append(price_data)
        
        # 캐시 크기 제한
        if len(self.price_cache[ticker]) > self.max_cache_size:
            self.price_cache[ticker] = self.price_cache[ticker][-self.max_cache_size:]
    
    def _get_combined_history(self, ticker: str, hours: int) -> List[Dict]:
        """
        여러 데이터 소스를 결합하여 히스토리 조회
        
        Args:
            ticker: 코인 티커
            hours: 조회할 시간 범위
            
        Returns:
            가격 히스토리 리스트 (통일된 형식)
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        result = []
        
        # 메모리 캐시에서 먼저 확인
        if ticker in self.price_cache:
            cache = self.price_cache[ticker]
            for item in cache:
                item_time = datetime.fromisoformat(item["timestamp"])
                if item_time > cutoff_time:
                    result.append(item)
        
        # 파일에서 로드
        data = self._load_all_data(ticker)
        
        # 상세 데이터 (24시간 이내)
        for item in data.get("detailed", []):
            item_time = datetime.fromisoformat(item["timestamp"])
            if item_time > cutoff_time:
                result.append(item)
        
        # 시간별 데이터 (24시간 이내도 포함 - 상세 데이터가 없을 때 사용)
        # hours가 24 이하여도 시간별 데이터가 있으면 사용
        for item in data.get("hourly", []):
            item_time = datetime.fromisoformat(item["timestamp"])
            if item_time > cutoff_time:
                # OHLC를 가격으로 변환 (close 사용)
                result.append({
                    "timestamp": item["timestamp"],
                    "price": item["close"]
                })
        
        # 일별 데이터 (7일 이상)
        if hours > 24 * 7:
            for item in data.get("daily", []):
                item_date = datetime.fromisoformat(item["date"] + "T00:00:00")
                if item_date > cutoff_time:
                    result.append({
                        "timestamp": item["date"] + "T00:00:00",
                        "price": item["close"]
                    })
        
        # 타임스탬프로 정렬
        result.sort(key=lambda x: x["timestamp"])
        
        return result
    
    def get_price_trend(self, ticker: str, hours: int = 24) -> Dict:
        """
        가격 변화 추이 조회
        
        Args:
            ticker: 코인 티커
            hours: 조회할 시간 범위 (시간)
            
        Returns:
            가격 추이 정보 딕셔너리
        """
        history = self._get_combined_history(ticker, hours)
        
        if not history:
            return {
                "ticker": ticker,
                "has_data": False,
                "message": f"최근 {hours}시간 데이터가 없습니다."
            }
        
        return self._calculate_trend(history, ticker)
    
    def get_multi_period_trends(self, ticker: str) -> Dict:
        """
        다중 기간 추이 조회 (단기/중기/장기)
        
        Args:
            ticker: 코인 티커
            
        Returns:
            다중 기간 추이 정보 딕셔너리
        """
        return {
            "short_term": self.get_price_trend(ticker, hours=24),   # 단기: 24시간
            "medium_term": self.get_price_trend(ticker, hours=72), # 중기: 3일
            "long_term": self.get_price_trend(ticker, hours=168)    # 장기: 7일
        }
    
    def _calculate_trend(self, history: List[Dict], ticker: str) -> Dict:
        """
        가격 추이 계산
        
        Args:
            history: 가격 히스토리 리스트
            ticker: 코인 티커
            
        Returns:
            추이 정보 딕셔너리
        """
        if not history:
            return {
                "ticker": ticker,
                "has_data": False
            }
        
        # 가격 리스트
        prices = [item["price"] for item in history]
        timestamps = [item["timestamp"] for item in history]
        
        # 현재 가격
        current_price = prices[-1]
        
        # 시작 가격
        start_price = prices[0]
        
        # 변화율 계산
        if start_price > 0:
            change_rate = ((current_price - start_price) / start_price) * 100
        else:
            change_rate = 0.0
        
        # 최고가/최저가
        max_price = max(prices)
        min_price = min(prices)
        
        # 추세 방향 판단
        if len(prices) >= 3:
            recent_trend = prices[-3:]
            if recent_trend[-1] > recent_trend[0]:
                trend_direction = "upward"
            elif recent_trend[-1] < recent_trend[0]:
                trend_direction = "downward"
            else:
                trend_direction = "sideways"
        else:
            trend_direction = "unknown"
        
        # 변동성 계산 (표준편차 기반)
        if len(prices) > 1:
            avg_price = sum(prices) / len(prices)
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            volatility = (variance ** 0.5) / avg_price * 100 if avg_price > 0 else 0
        else:
            volatility = 0.0
        
        return {
            "ticker": ticker,
            "has_data": True,
            "current_price": current_price,
            "start_price": start_price,
            "change_rate": round(change_rate, 2),
            "max_price": max_price,
            "min_price": min_price,
            "trend_direction": trend_direction,
            "volatility": round(volatility, 2),
            "data_points": len(history),
            "time_range": {
                "start": timestamps[0],
                "end": timestamps[-1]
            },
            "price_history": history[-20:] if len(history) > 20 else history  # 최근 20개만
        }
    
    def format_trend_for_llm(self, ticker: str, hours: int = 24) -> str:
        """
        LLM에 제공할 가격 추이 텍스트 포맷팅 (단일 기간)
        
        Args:
            ticker: 코인 티커
            hours: 조회할 시간 범위
            
        Returns:
            포맷팅된 텍스트
        """
        trend = self.get_price_trend(ticker, hours)
        
        if not trend.get("has_data", False):
            return f"{ticker}: {trend.get('message', '데이터 없음')}"
        
        # 기간 레이블
        if hours <= 24:
            period_label = "24시간"
        elif hours <= 72:
            period_label = "3일"
        else:
            period_label = "7일"
        
        # 텍스트 포맷팅
        lines = [
            f"**{period_label}**",
            f"- 현재가: {trend['current_price']:,.0f}원",
            f"- 시작가: {trend['start_price']:,.0f}원",
            f"- 변화율: {trend['change_rate']:+.2f}%",
            f"- 최고가: {trend['max_price']:,.0f}원",
            f"- 최저가: {trend['min_price']:,.0f}원",
            f"- 추세: {trend['trend_direction']}",
            f"- 변동성: {trend['volatility']:.2f}%",
        ]
        
        return "\n".join(lines)
    
    def format_multi_trend_for_llm(self, ticker: str) -> str:
        """
        LLM에 제공할 다중 기간 가격 추이 텍스트 포맷팅 (간결한 형식)
        
        Args:
            ticker: 코인 티커
            
        Returns:
            포맷팅된 텍스트
        """
        lines = [f"### {ticker}"]
        
        # RSI 계산 및 표시 (계산 불가면 표시하지 않음)
        rsi_10min = self.calculate_10min_rsi(ticker, period=14)
        rsi_hourly = self.calculate_hourly_rsi(ticker, period=14)
        daily_rsi = self.calculate_daily_rsi(ticker, period=14, min_days=6)
        
        rsi_lines = []
        if rsi_10min is not None:
            rsi_lines.append(f"RSI(10분): {rsi_10min}")
        if rsi_hourly is not None:
            rsi_lines.append(f"RSI(시간): {rsi_hourly}")
        if daily_rsi is not None:
            rsi_lines.append(f"RSI(일): {daily_rsi}")
        
        if rsi_lines:
            lines.extend(rsi_lines)
        
        # 현재 거래량 표시 (최신 데이터에서)
        data = self._load_all_data(ticker)
        current_volume = None
        
        # detailed에서 최신 거래량 확인
        detailed = data.get("detailed", [])
        if detailed:
            latest_detailed = detailed[-1]
            if latest_detailed.get("volume") is not None:
                current_volume = latest_detailed["volume"]
        
        # detailed에 없으면 hourly에서 최신 거래량 확인
        if current_volume is None:
            hourly = data.get("hourly", [])
            if hourly:
                latest_hourly = hourly[-1]
                if latest_hourly.get("volume") is not None:
                    current_volume = latest_hourly["volume"]
        
        if current_volume is not None:
            # 거래량 포맷팅 (M=백만, K=천)
            if current_volume >= 1000000:
                volume_str = f"{current_volume/1000000:.2f}M"
            elif current_volume >= 1000:
                volume_str = f"{current_volume/1000:.2f}K"
            else:
                volume_str = f"{current_volume:.2f}"
            lines.append(f"거래량(24h): {volume_str}")
        
        # 24시간 내: 1시간 간격으로 가격 표시
        now = datetime.now()
        cutoff_24h = now - timedelta(hours=24)
        
        data = self._load_all_data(ticker)
        
        # 시간별 데이터 우선 사용 (OHLC의 close 사용)
        hourly_data = data.get("hourly", [])
        hourly_24h = []
        for item in hourly_data:
            item_time = datetime.fromisoformat(item["timestamp"])
            if item_time > cutoff_24h:
                hourly_24h.append((item_time, item.get("close", 0)))
        
        # 상세 데이터에서 보완 (시간별 데이터가 부족한 경우)
        if len(hourly_24h) < 24:
            detailed = data.get("detailed", [])
            detailed_24h = [item for item in detailed 
                           if datetime.fromisoformat(item["timestamp"]) > cutoff_24h]
            
            # 시간별로 그룹화 (1시간 간격)
            hourly_groups = {}
            for item in detailed_24h:
                item_time = datetime.fromisoformat(item["timestamp"])
                hour_key = item_time.replace(minute=0, second=0, microsecond=0)
                if hour_key not in hourly_groups:
                    hourly_groups[hour_key] = []
                hourly_groups[hour_key].append(item["price"])
            
            # 시간별 데이터에 없는 시간대만 추가
            existing_hours = {h[0].replace(minute=0, second=0, microsecond=0) for h in hourly_24h}
            for hour_key in sorted(hourly_groups.keys(), reverse=True):
                hour_key_normalized = hour_key.replace(minute=0, second=0, microsecond=0)
                if hour_key_normalized not in existing_hours:
                    prices = hourly_groups[hour_key]
                    avg_price = sum(prices) / len(prices) if prices else 0
                    if avg_price > 0:
                        hourly_24h.append((hour_key, avg_price))
        
        # 시간순 정렬 (오래된 순서)
        hourly_24h.sort(key=lambda x: x[0])
        # 최근 24시간만 선택
        hourly_prices = hourly_24h[-24:] if len(hourly_24h) > 24 else hourly_24h
        
        # 24시간 내 모든 시간대를 1시간 간격으로 채우기 (데이터가 없는 시간대는 이전 값 사용)
        if hourly_prices:
            # 시간대별 가격 딕셔너리 생성 (24시간 내만)
            price_dict = {}
            for hour_key, price in hourly_prices:
                if price > 0:  # 가격이 0이면 스킵
                    hour_key_normalized = hour_key.replace(minute=0, second=0, microsecond=0)
                    if hour_key_normalized > cutoff_24h:
                        price_dict[hour_key_normalized] = price
            
            # 최근 24시간의 모든 시간대 생성 (1시간 간격, 오래된 순서부터)
            filled_prices = []
            current_hour = now.replace(minute=0, second=0, microsecond=0)
            start_hour = cutoff_24h.replace(minute=0, second=0, microsecond=0)
            last_price = None
            
            # 오래된 시간부터 최신 시간까지 순회
            check_hour = start_hour
            while check_hour <= current_hour:
                if check_hour in price_dict:
                    last_price = price_dict[check_hour]
                    filled_prices.append((check_hour, last_price))
                elif last_price is not None:
                    # 데이터가 없으면 이전 시간대의 가격 사용
                    filled_prices.append((check_hour, last_price))
                # last_price가 None이면 (가장 오래된 시간대에 데이터가 없으면) 스킵
                check_hour += timedelta(hours=1)
            
            # 시간별 가격 포맷팅 (간결하게, 최신순)
            hour_strs = []
            # 최신순으로 정렬
            for hour_key, price in reversed(filled_prices):
                # 가격이 0이면 스킵 (오류 데이터)
                if price <= 0:
                    continue
                    
                hour_str = hour_key.strftime("%H:%M")
                # 가격을 간단하게 표시 (M=백만, K=천, 더 정확하게)
                if price >= 1000000:
                    price_str = f"{price/1000000:.2f}M"
                elif price >= 1000:
                    # 3K가 아닌 3.45K처럼 소수점 표시
                    price_str = f"{price/1000:.2f}K"
                else:
                    price_str = f"{price:.0f}"
                hour_strs.append(f"{hour_str} {price_str}")
            
            if hour_strs:
                lines.append("24h: " + " | ".join(hour_strs))
            else:
                lines.append("24h: 데이터 없음")
        else:
            lines.append("24h: 데이터 없음")
        
        # 15일 일별 데이터: 가격+변화율+추세+변동성
        daily_data = data.get("daily", [])
        if daily_data:
            # 최근 15일만 (최신순)
            daily_recent = sorted(daily_data, key=lambda x: x["date"], reverse=True)[:15]
            
            daily_strs = []
            # 최신순으로 처리 (변화율은 전일 대비)
            for i, day_item in enumerate(daily_recent):
                close = day_item["close"]
                
                # 가격이 0이면 스킵 (오류 데이터)
                if close <= 0:
                    continue
                
                date_str = day_item["date"][5:]  # MM-DD 형식
                
                # 변화율 계산 (전일 대비)
                if i < len(daily_recent) - 1:
                    prev_close = daily_recent[i + 1]["close"]
                    if prev_close > 0:
                        change_rate = ((close - prev_close) / prev_close) * 100
                        change_str = f"{change_rate:+.1f}%"
                    else:
                        change_str = "0.0%"
                else:
                    change_str = "0.0%"
                
                # 추세 (고가/저가 대비 종가 위치)
                high = day_item["high"]
                low = day_item["low"]
                if high > 0 and low > 0:
                    mid = (high + low) / 2
                    if close > mid * 1.02:
                        trend = "↑"
                    elif close < mid * 0.98:
                        trend = "↓"
                    else:
                        trend = "→"
                    
                    # 변동성 (고저 차이 비율)
                    volatility = ((high - low) / close) * 100
                else:
                    trend = "→"
                    volatility = 0
                
                # 가격 포맷팅 (더 정확하게)
                if close >= 1000000:
                    price_str = f"{close/1000000:.2f}M"
                elif close >= 1000:
                    price_str = f"{close/1000:.2f}K"
                else:
                    price_str = f"{close:.0f}"
                
                # 형식: 날짜 가격 변화율 추세 변동성
                daily_strs.append(f"{date_str} {price_str} {change_str} {trend} vol{volatility:.1f}%")
            
            if daily_strs:
                lines.append("15d: " + " | ".join(daily_strs))
        else:
            lines.append("15d: 데이터 없음")
        
        return "\n".join(lines)
    
    def get_all_trends(self, tickers: List[str], hours: int = 24, auto_fetch: bool = True) -> str:
        """
        여러 코인의 가격 추이를 한 번에 조회
        
        Args:
            tickers: 코인 티커 리스트
            hours: 조회할 시간 범위 (단일 기간용, 기본값은 호환성)
            auto_fetch: 데이터가 없으면 자동으로 REST API 호출 (기본값: True)
            
        Returns:
            포맷팅된 텍스트
        """
        # 설명 추가
        description = "## 가격 정보\n24h: 1시간 간격 가격 | 15d: 날짜 가격 변화율 추세 변동성 (↑상승 ↓하락 →횡보, vol=변동성)\n"
        
        trends = []
        for ticker in tickers:
            # 데이터 확인
            trend = self.get_price_trend(ticker, hours=24)
            
            # 데이터가 없고 auto_fetch가 True이면 REST API로 수집
            if not trend.get("has_data", False) and auto_fetch:
                print(f"⚠️  {ticker} 가격 데이터가 없어 REST API로 수집합니다...")
                self.fetch_historical_data(ticker)
                # 수집 후 다시 조회
                trend = self.get_price_trend(ticker, hours=24)
            
            # 다중 기간 추이 사용
            trend_text = self.format_multi_trend_for_llm(ticker)
            trends.append(trend_text)
        
        return description + "\n\n".join(trends)
