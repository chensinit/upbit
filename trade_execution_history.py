"""
거래 실행 내역 저장 모듈
Function call 실행 결과를 저장하고 관리합니다.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class TradeExecutionHistory:
    """거래 실행 내역 관리 클래스"""
    
    def __init__(self, data_dir: str = "data/trade_execution_history"):
        """
        초기화
        
        Args:
            data_dir: 거래 내역 저장 디렉토리
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "execution_history.json"
    
    def save_execution(self, 
                      function_name: str,
                      ticker: str,
                      arguments: Dict,
                      success: bool,
                      result: Optional[Dict] = None,
                      error: Optional[str] = None,
                      timestamp: Optional[datetime] = None) -> bool:
        """
        거래 실행 내역 저장
        
        Args:
            function_name: 함수 이름 (buy_coin, sell_coin 등)
            ticker: 코인 티커
            arguments: 함수 인자
            success: 성공 여부
            result: 성공 시 결과 (주문 정보 등)
            error: 실패 시 에러 메시지
            timestamp: 타임스탬프 (None이면 현재 시간)
            
        Returns:
            저장 성공 여부
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        try:
            # 기존 내역 로드
            history = self._load_history()
            
            # 새 내역 추가
            execution_record = {
                "timestamp": timestamp.isoformat(),
                "function_name": function_name,
                "ticker": ticker,
                "arguments": arguments,
                "success": success,
                "result": result,
                "error": error
            }
            
            history.append(execution_record)
            
            # 최근 1000개만 유지 (메모리 절약)
            if len(history) > 1000:
                history = history[-1000:]
            
            # 저장
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            
            return True
        
        except Exception as e:
            print(f"⚠️  거래 내역 저장 실패: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _load_history(self) -> List[Dict]:
        """거래 내역 로드"""
        if not self.history_file.exists():
            return []
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  거래 내역 로드 실패: {e}")
            return []
    
    def get_recent_executions(self, limit: int = 15) -> List[Dict]:
        """
        최근 거래 실행 내역 조회
        
        Args:
            limit: 조회할 개수 (기본값: 15)
            
        Returns:
            거래 실행 내역 리스트 (최신순)
        """
        history = self._load_history()
        return history[-limit:] if len(history) > limit else history
    
    def get_executions_for_prompt(self, limit: int = 15) -> str:
        """
        Prompt에 포함시킬 거래 내역 텍스트 생성
        
        Args:
            limit: 조회할 개수 (기본값: 15)
            
        Returns:
            거래 내역 텍스트
        """
        executions = self.get_recent_executions(limit)
        
        if not executions:
            return "## 거래 실행 내역\n최근 거래 실행 내역이 없습니다.\n"
        
        lines = ["## 거래 실행 내역"]
        lines.append(f"최근 {len(executions)}개 거래 실행 내역:\n")
        
        for i, exec_record in enumerate(reversed(executions), 1):
            timestamp = datetime.fromisoformat(exec_record["timestamp"])
            func_name = exec_record["function_name"]
            ticker = exec_record["ticker"]
            args = exec_record["arguments"]
            success = exec_record["success"]
            
            status = "✅ 성공" if success else "❌ 실패"
            
            if func_name == "buy_coin":
                amount = args.get("amount", "N/A")
                if isinstance(amount, (int, float)):
                    lines.append(f"{i}. [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {status} 매수: {ticker}, 금액: {amount:,.0f}원")
                else:
                    lines.append(f"{i}. [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {status} 매수: {ticker}, 금액: {amount}")
            elif func_name == "sell_coin":
                volume = args.get("volume", "N/A")
                lines.append(f"{i}. [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {status} 매도: {ticker}, 수량: {volume}")
            else:
                lines.append(f"{i}. [{timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {status} {func_name}: {ticker}")
            
            if not success and exec_record.get("error"):
                lines.append(f"   오류: {exec_record['error']}")
        
        return "\n".join(lines) + "\n"

