"""
규칙 기반 코인 선택 모듈
하루 한 번 새벽 시간에 실행되어 코인 universe를 업데이트합니다.
"""
import json
import time
import random
from pathlib import Path
from typing import List, Dict, Optional
import pyupbit
import requests


class CoinSelector:
    """규칙 기반 코인 선택 클래스"""
    
    def __init__(self, trader=None):
        """
        초기화
        
        Args:
            trader: UpbitTrader 인스턴스 (보유 코인 조회용, None 가능)
        """
        self.trader = trader
        self.data_dir = Path("data")
        self.pinned_file = self.data_dir / "pinned_tickers.json"
        
        # 필터링 기준
        self.min_trade_volume = 1_000_000_000  # 10억원
        self.min_volatility = 0.01  # 1%
        self.max_volatility = 0.25  # 25%
        
        # 분류 기준
        self.momentum_threshold = 0.03  # +3%
        self.dip_min_rate = -0.06  # -6%
        self.dip_max_rate = 0.0  # 0%
        self.dip_min_volatility = 0.015  # 1.5%
        
        # 목표 개수
        self.target_momentum_count = 6
        self.target_dip_count = 6
        self.candidate_pool_size = 12  # 후보 풀 크기 (상위 12개 중에서 랜덤 선택)
        
        # API Rate Limiting
        self.api_delay = 0.3  # 0.3초 대기 (초당 10회 제한)
    
    def load_pinned_tickers(self) -> List[str]:
        """
        PINNED_TICKERS 로드 (메이저 코인만)
        
        Returns:
            메이저 코인 리스트
        """
        if self.pinned_file.exists():
            try:
                with open(self.pinned_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("major_coins", [])
            except Exception as e:
                print(f"⚠️  PINNED_TICKERS 로드 실패: {e}")
                return self._get_default_major_coins()
        else:
            # 파일이 없으면 기본값으로 생성
            default_coins = self._get_default_major_coins()
            self._save_pinned_tickers(default_coins)
            return default_coins
    
    def _get_default_major_coins(self) -> List[str]:
        """기본 메이저 코인"""
        return ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA", "KRW-SOL"]
    
    def _save_pinned_tickers(self, coins: List[str]):
        """PINNED_TICKERS 저장"""
        try:
            data = {
                "major_coins": coins,
                "note": "보유 코인은 런타임에 동적으로 추가됨"
            }
            with open(self.pinned_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  PINNED_TICKERS 저장 실패: {e}")
    
    def get_held_tickers(self) -> List[str]:
        """
        현재 보유 중인 코인 티커 조회
        
        Returns:
            보유 코인 티커 리스트
        """
        if not self.trader:
            return []
        
        try:
            balances = self.trader.get_all_balances()
            held_tickers = []
            for balance in balances:
                currency = balance.get('currency', '')
                balance_amount = float(balance.get('balance', 0))
                if currency != "KRW" and balance_amount > 0:
                    held_tickers.append(f"KRW-{currency}")
            return held_tickers
        except Exception as e:
            print(f"⚠️  보유 코인 조회 실패: {e}")
            return []
    
    def get_all_krw_tickers(self) -> List[str]:
        """
        모든 KRW 마켓 코인 조회
        
        Returns:
            KRW 마켓 코인 티커 리스트
        """
        try:
            tickers = pyupbit.get_tickers(fiat="KRW")
            print(f"✅ KRW 마켓 코인 {len(tickers)}개 조회 완료")
            return tickers
        except Exception as e:
            print(f"❌ KRW 마켓 코인 조회 실패: {e}")
            return []
    
    def get_ticker_data_batch(self, tickers: List[str]) -> List[Dict]:
        """
        여러 코인의 24h ticker 데이터 조회
        
        Args:
            tickers: 조회할 티커 리스트
            
        Returns:
            ticker 데이터 리스트
        """
        if not tickers:
            return []
        
        # Upbit API 직접 호출 (배치 조회)
        # /v1/ticker?markets=KRW-BTC,KRW-ETH,...
        try:
            markets = ",".join(tickers)
            url = f"https://api.upbit.com/v1/ticker"
            params = {"markets": markets}
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            print(f"✅ {len(data)}개 코인 ticker 데이터 조회 완료")
            
            # Rate limiting 대기
            time.sleep(self.api_delay)
            
            return data
        except Exception as e:
            print(f"❌ Ticker 데이터 조회 실패: {e}")
            return []
    
    def calculate_volatility(self, high: float, low: float, trade_price: float) -> float:
        """
        변동성 계산: (high - low) / trade_price
        
        Args:
            high: 24h 최고가
            low: 24h 최저가
            trade_price: 현재가
            
        Returns:
            변동성 (0.01 = 1%)
        """
        if trade_price <= 0:
            return 0.0
        return (high - low) / trade_price
    
    def filter_coins(self, ticker_data: List[Dict]) -> List[Dict]:
        """
        공통 필터 적용
        
        필터 조건:
        - acc_trade_price_24h >= 10억
        - 0.01 <= 변동성 <= 0.25
        
        Args:
            ticker_data: ticker 데이터 리스트
            
        Returns:
            필터링된 코인 리스트
        """
        filtered = []
        
        for item in ticker_data:
            market = item.get("market", "")
            if not market.startswith("KRW-"):
                continue
            
            # 거래대금 24h
            acc_trade_price_24h = item.get("acc_trade_price_24h", 0)
            if acc_trade_price_24h < self.min_trade_volume:
                continue
            
            # 변동성 계산
            high = item.get("high_price", 0)
            low = item.get("low_price", 0)
            trade_price = item.get("trade_price", 0)
            
            volatility = self.calculate_volatility(high, low, trade_price)
            
            if volatility < self.min_volatility or volatility > self.max_volatility:
                continue
            
            # 필터 통과한 코인
            item["volatility"] = volatility
            filtered.append(item)
        
        print(f"✅ 필터링 완료: {len(filtered)}/{len(ticker_data)}개 코인 통과")
        return filtered
    
    def classify_coins(self, filtered_coins: List[Dict]) -> Dict[str, List[Dict]]:
        """
        코인을 Momentum과 Dip으로 분류
        
        A: Momentum (상승) → signed_change_rate >= +3%
        B: Dip (눌림) → -6% ≤ signed_change_rate ≤ 0 AND 변동성 ≥ 0.015
        
        Args:
            filtered_coins: 필터링된 코인 리스트
            
        Returns:
            {"momentum": [...], "dip": [...]}
        """
        momentum = []
        dip = []
        
        for coin in filtered_coins:
            signed_change_rate = coin.get("signed_change_rate", 0)
            volatility = coin.get("volatility", 0)
            
            # Momentum: +3% 이상
            if signed_change_rate >= self.momentum_threshold:
                momentum.append(coin)
            
            # Dip: -6% ~ 0% AND 변동성 >= 1.5%
            elif (self.dip_min_rate <= signed_change_rate <= self.dip_max_rate and 
                  volatility >= self.dip_min_volatility):
                dip.append(coin)
        
        # 정렬
        momentum.sort(key=lambda x: x.get("signed_change_rate", 0), reverse=True)
        dip.sort(key=lambda x: x.get("volatility", 0), reverse=True)
        
        print(f"✅ 분류 완료: Momentum {len(momentum)}개, Dip {len(dip)}개")
        
        return {
            "momentum": momentum,
            "dip": dip
        }
    
    def select_final_coins(self, pinned: List[str], 
                          momentum: List[Dict], 
                          dip: List[Dict]) -> List[str]:
        """
        최종 코인 선택
        
        목표 개수 = pinned + 보유 코인 + momentum(5-6개) + dip(5-6개)
        
        Args:
            pinned: PINNED 코인 리스트 (보유 + 메이저)
            momentum: Momentum 코인 리스트
            dip: Dip 코인 리스트
            
        Returns:
            최종 선택된 코인 티커 리스트
        """
        selected = set(pinned)  # PINNED는 무조건 포함
        pinned_set = set(pinned)  # 중복 체크용
        
        # Momentum에서 선택 (상위 12개 후보 중 랜덤으로 6개 선택, PINNED 제외)
        momentum_candidates = []
        for coin in momentum:
            market = coin.get("market")
            if market not in pinned_set:
                momentum_candidates.append(market)
                if len(momentum_candidates) >= self.candidate_pool_size:
                    break
        
        if momentum_candidates:
            # 후보가 목표 개수보다 적으면 모두 선택, 많으면 랜덤 선택
            if len(momentum_candidates) <= self.target_momentum_count:
                momentum_tickers = momentum_candidates
            else:
                momentum_tickers = random.sample(momentum_candidates, self.target_momentum_count)
            selected.update(momentum_tickers)
        else:
            momentum_tickers = []
        
        # Dip에서 선택 (상위 12개 후보 중 랜덤으로 6개 선택, PINNED 제외)
        dip_candidates = []
        for coin in dip:
            market = coin.get("market")
            if market not in pinned_set:
                dip_candidates.append(market)
                if len(dip_candidates) >= self.candidate_pool_size:
                    break
        
        if dip_candidates:
            # 후보가 목표 개수보다 적으면 모두 선택, 많으면 랜덤 선택
            if len(dip_candidates) <= self.target_dip_count:
                dip_tickers = dip_candidates
            else:
                dip_tickers = random.sample(dip_candidates, self.target_dip_count)
            selected.update(dip_tickers)
        else:
            dip_tickers = []
        
        final_list = sorted(list(selected))
        
        print(f"✅ 최종 선택: {len(final_list)}개 코인")
        print(f"   - PINNED: {len(pinned)}개")
        print(f"   - Momentum: {len(momentum_tickers)}개")
        print(f"   - Dip: {len(dip_tickers)}개")
        
        return final_list
    
    def update_coin_universe(self) -> tuple[List[str], Dict]:
        """
        전체 프로세스 실행: 코인 universe 업데이트
        
        Returns:
            (선택된 코인 티커 리스트, 상세 정보 딕셔너리)
        """
        print("\n" + "="*60)
        print("🪙 코인 Universe 업데이트 시작")
        print("="*60)
        
        # 1. PINNED_TICKERS 로드 (메이저 코인)
        print("\n1️⃣ PINNED_TICKERS 로드 중...")
        major_coins = self.load_pinned_tickers()
        print(f"   메이저 코인: {', '.join(major_coins)}")
        
        # 2. 보유 코인 조회
        print("\n2️⃣ 보유 코인 조회 중...")
        held_coins = self.get_held_tickers()
        print(f"   보유 코인: {', '.join(held_coins) if held_coins else '없음'}")
        
        # PINNED = 메이저 + 보유
        pinned = list(set(major_coins + held_coins))
        print(f"   PINNED 총 {len(pinned)}개: {', '.join(pinned)}")
        
        # 3. 모든 KRW 코인 조회
        print("\n3️⃣ 모든 KRW 마켓 코인 조회 중...")
        all_tickers = self.get_all_krw_tickers()
        if not all_tickers:
            print("⚠️  코인 조회 실패, PINNED만 반환")
            return pinned
        
        # 4. Ticker 데이터 조회 (24h 데이터)
        print("\n4️⃣ Ticker 데이터 조회 중...")
        ticker_data = self.get_ticker_data_batch(all_tickers)
        if not ticker_data:
            print("⚠️  Ticker 데이터 조회 실패, PINNED만 반환")
            return pinned, {"pinned": pinned, "momentum": [], "dip": [], "momentum_all": [], "dip_all": [], "filtered_count": 0, "total_tickers": len(all_tickers)}
        
        # 5. 필터링
        print("\n5️⃣ 필터링 중...")
        print(f"   기준: 거래대금 >= {self.min_trade_volume/1_000_000_000:.0f}억원")
        print(f"   기준: 변동성 {self.min_volatility*100:.0f}% ~ {self.max_volatility*100:.0f}%")
        filtered = self.filter_coins(ticker_data)
        
        # PINNED 제외 (이미 포함할 것이므로)
        filtered = [coin for coin in filtered if coin.get("market") not in pinned]
        
        # 6. 분류
        print("\n6️⃣ Momentum/Dip 분류 중...")
        print(f"   Momentum: {self.momentum_threshold*100:.0f}% 이상 상승")
        print(f"   Dip: {self.dip_min_rate*100:.0f}% ~ {self.dip_max_rate*100:.0f}%, 변동성 >= {self.dip_min_volatility*100:.1f}%")
        classified = self.classify_coins(filtered)
        
        # 7. 최종 선택
        print("\n7️⃣ 최종 코인 선택 중...")
        final_coins = self.select_final_coins(
            pinned=pinned,
            momentum=classified["momentum"],
            dip=classified["dip"]
        )
        
        print("\n" + "="*60)
        print("✅ 코인 Universe 업데이트 완료")
        print("="*60)
        
        # 상세 정보 딕셔너리 생성
        detail_info = {
            "pinned": pinned,
            "momentum": [coin.get("market") for coin in classified["momentum"][:self.target_momentum_count]],
            "dip": [coin.get("market") for coin in classified["dip"][:self.target_dip_count]],
            "momentum_all": [coin.get("market") for coin in classified["momentum"]],
            "dip_all": [coin.get("market") for coin in classified["dip"]],
            "filtered_count": len(filtered),
            "total_tickers": len(all_tickers)
        }
        
        return final_coins, detail_info

