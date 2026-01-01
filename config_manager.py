"""
설정 파일 관리 모듈
구독 코인 목록, 체크 간격 등 중요 정보를 파일로 저장하고 관리합니다.
"""
import json
import os
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime


class ConfigManager:
    """설정 파일 관리 클래스"""
    
    def __init__(self, config_dir: str = "data"):
        """
        초기화
        
        Args:
            config_dir: 설정 파일을 저장할 디렉토리
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        
        self.tickers_file = self.config_dir / "tickers.json"
        self.settings_file = self.config_dir / "settings.json"
    
    def load_tickers(self, default_tickers: List[str] = None) -> List[str]:
        """
        구독 코인 목록 로드
        
        Args:
            default_tickers: 파일이 없을 때 사용할 기본값 (None이면 메이저 코인 사용)
            
        Returns:
            구독 코인 티커 리스트
        """
        # 기본값: 메이저 코인 6개
        if default_tickers is None:
            default_tickers = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA", "KRW-SOL", "KRW-DOT"]
        
        if self.tickers_file.exists():
            try:
                with open(self.tickers_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    tickers = data.get("tickers", default_tickers)
                    
                    # 빈 리스트이거나 None인 경우 기본값 사용
                    if not tickers or len(tickers) == 0:
                        print("⚠️  구독 코인 목록이 비어있습니다. 메이저 코인으로 초기화합니다.")
                        tickers = default_tickers
                        self.save_tickers(tickers)
                    
                    print(f"📂 구독 코인 목록 로드: {', '.join(tickers)}")
                    return tickers
            except Exception as e:
                print(f"⚠️  구독 코인 목록 로드 실패: {e}, 메이저 코인으로 초기화")
                self.save_tickers(default_tickers)
                return default_tickers
        else:
            # 파일이 없으면 메이저 코인으로 기본 파일 생성
            print("📝 구독 코인 목록 파일이 없습니다. 메이저 코인으로 초기화합니다.")
            self.save_tickers(default_tickers)
            return default_tickers
    
    def save_tickers(self, tickers: List[str]) -> bool:
        """
        구독 코인 목록 저장
        
        Args:
            tickers: 구독 코인 티커 리스트
            
        Returns:
            저장 성공 여부
        """
        try:
            data = {
                "tickers": tickers,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            with open(self.tickers_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"💾 구독 코인 목록 저장: {', '.join(tickers)}")
            return True
        except Exception as e:
            print(f"❌ 구독 코인 목록 저장 실패: {e}")
            return False
    
    def load_settings(self) -> Dict:
        """
        설정 정보 로드
        
        Returns:
            설정 딕셔너리
        """
        default_settings = {
            "check_interval": 30 * 60,  # 거래 사이클 간격: 30분 (초)
            "coin_selection_interval": 6 * 60 * 60,  # 코인 선택 사이클 간격: 6시간 (초, 사용 안 함)
            "coin_selection_hour": 2,  # 코인 선택 실행 시간 (새벽 2시)
            "coin_selection_minute": 0,  # 코인 선택 실행 분 (0분)
            "max_trade_ratio": None,  # 거래 비율 제한 (None이면 제한 없음)
        }
        
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    # 기본값과 병합
                    merged = {**default_settings, **settings}
                    print(f"📂 설정 정보 로드: 체크 간격 {merged['check_interval'] // 60}분")
                    return merged
            except Exception as e:
                print(f"⚠️  설정 정보 로드 실패: {e}, 기본값 사용")
                return default_settings
        else:
            # 파일이 없으면 기본값으로 생성
            self.save_settings(default_settings)
            return default_settings
    
    def save_settings(self, settings: Dict) -> bool:
        """
        설정 정보 저장
        
        Args:
            settings: 설정 딕셔너리
            
        Returns:
            저장 성공 여부
        """
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            
            print(f"💾 설정 정보 저장 완료")
            return True
        except Exception as e:
            print(f"❌ 설정 정보 저장 실패: {e}")
            return False
    
    def update_check_interval(self, interval_minutes: int) -> bool:
        """
        체크 간격 업데이트
        
        Args:
            interval_minutes: 체크 간격 (분)
            
        Returns:
            업데이트 성공 여부
        """
        settings = self.load_settings()
        settings["check_interval"] = interval_minutes * 60
        return self.save_settings(settings)
    
    def get_check_interval(self) -> int:
        """
        체크 간격 조회 (초)
        
        Returns:
            체크 간격 (초)
        """
        settings = self.load_settings()
        return settings.get("check_interval", 30 * 60)

