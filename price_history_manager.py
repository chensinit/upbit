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
    
    def save_price(self, ticker: str, price: float, timestamp: datetime = None) -> bool:
        """
        가격 저장 (10분 간격)
        
        Args:
            ticker: 코인 티커
            price: 가격
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
            
            # 상세 데이터에 추가 (최근 24시간)
            detailed = data.get("detailed", [])
            price_data = {
                "timestamp": timestamp.isoformat(),
                "price": price
            }
            detailed.append(price_data)
            
            # 24시간 이전 데이터는 압축
            cutoff_24h = timestamp - timedelta(hours=24)
            detailed_24h = []
            to_compress = []
            
            for item in detailed:
                item_time = datetime.fromisoformat(item["timestamp"])
                if item_time > cutoff_24h:
                    detailed_24h.append(item)
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
            data["detailed"] = detailed_24h
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
            hourly.append({
                "timestamp": hour_key,
                "open": prices[0],
                "high": max(prices),
                "low": min(prices),
                "close": prices[-1],
                "count": len(prices)
            })
        
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
            
            # 1. 일별 데이터 수집 (최근 7일)
            print(f"   - 일별 데이터 수집 중... (최근 7일)")
            daily_df = pyupbit.get_ohlcv(ticker, interval="day", count=7)
            
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
            
            # 1초 대기 (서버 부하 방지)
            time.sleep(1.0)
            
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
                        hourly.append({
                            "timestamp": hour_key,
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "count": 1
                        })
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
        LLM에 제공할 다중 기간 가격 추이 텍스트 포맷팅
        
        Args:
            ticker: 코인 티커
            
        Returns:
            포맷팅된 텍스트
        """
        trends = self.get_multi_period_trends(ticker)
        
        lines = [f"### {ticker} 가격 추이"]
        
        # 단기 (24시간)
        short = trends["short_term"]
        if short.get("has_data", False):
            lines.append("\n**단기 (24시간)**")
            lines.append(f"- 현재가: {short['current_price']:,.0f}원")
            lines.append(f"- 시작가: {short['start_price']:,.0f}원")
            lines.append(f"- 변화율: {short['change_rate']:+.2f}%")
            lines.append(f"- 추세: {short['trend_direction']}")
            lines.append(f"- 변동성: {short['volatility']:.2f}%")
        else:
            lines.append("\n**단기 (24시간)**: 데이터 없음")
        
        # 중기 (3일)
        medium = trends["medium_term"]
        if medium.get("has_data", False):
            lines.append("\n**중기 (3일)**")
            lines.append(f"- 시작가: {medium['start_price']:,.0f}원")
            lines.append(f"- 변화율: {medium['change_rate']:+.2f}%")
            lines.append(f"- 추세: {medium['trend_direction']}")
        else:
            lines.append("\n**중기 (3일)**: 데이터 없음")
        
        # 장기 (7일)
        long_term = trends["long_term"]
        if long_term.get("has_data", False):
            lines.append("\n**장기 (7일)**")
            lines.append(f"- 시작가: {long_term['start_price']:,.0f}원")
            lines.append(f"- 변화율: {long_term['change_rate']:+.2f}%")
            lines.append(f"- 추세: {long_term['trend_direction']}")
        else:
            lines.append("\n**장기 (7일)**: 데이터 없음")
        
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
        
        return "\n\n".join(trends)
