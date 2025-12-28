"""
업비트 API 연결 테스트 및 잔고 조회 스크립트
"""
import pyupbit
from config import ACCESS_KEY, SECRET_KEY


def test_connection():
    """업비트 API 연결 테스트"""
    print("="*60)
    print("🔌 업비트 API 연결 테스트")
    print("="*60)
    
    # API 키 확인
    if not ACCESS_KEY or not SECRET_KEY:
        print("❌ API 키가 설정되지 않았습니다.")
        print("   config.py 파일을 확인하세요.")
        return False
    
    print(f"✅ API 키 확인됨")
    print(f"   Access Key: {ACCESS_KEY[:10]}...")
    print(f"   Secret Key: {SECRET_KEY[:10]}...")
    print()
    
    try:
        # 업비트 객체 생성
        upbit = pyupbit.Upbit(ACCESS_KEY, SECRET_KEY)
        print("✅ 업비트 객체 생성 성공")
        
        # 계정 정보 조회
        print("\n" + "-"*60)
        print("📊 계정 정보 조회")
        print("-"*60)
        
        # 원화 잔고
        krw_balance = upbit.get_balance("KRW")
        print(f"💰 원화 잔고: {krw_balance:,.0f}원")
        
        # 전체 잔고 조회
        balances = upbit.get_balances()
        
        if balances:
            print(f"\n📈 보유 자산 ({len(balances)}개):")
            print("-"*60)
            
            total_krw_value = 0
            
            for balance in balances:
                currency = balance.get('currency', '')
                balance_amount = float(balance.get('balance', 0))
                locked = float(balance.get('locked', 0))
                
                # 잔고가 있는 경우만 표시
                if balance_amount > 0 or locked > 0:
                    if currency == "KRW":
                        print(f"  💵 {currency}")
                        print(f"     보유: {balance_amount:,.0f}원")
                        if locked > 0:
                            print(f"     주문 중: {locked:,.0f}원")
                        total_krw_value += balance_amount
                    else:
                        ticker = f"KRW-{currency}"
                        try:
                            current_price = pyupbit.get_current_price(ticker)
                            total_value = balance_amount * current_price
                            total_krw_value += total_value
                            
                            print(f"  🪙 {currency}")
                            print(f"     보유: {balance_amount:.8f}")
                            if locked > 0:
                                print(f"     주문 중: {locked:.8f}")
                            print(f"     현재가: {current_price:,.0f}원")
                            print(f"     평가금액: {total_value:,.0f}원")
                        except Exception as e:
                            print(f"  🪙 {currency}")
                            print(f"     보유: {balance_amount:.8f}")
                            if locked > 0:
                                print(f"     주문 중: {locked:.8f}")
                            print(f"     ⚠️  가격 조회 실패: {e}")
                        print()
            
            print("-"*60)
            print(f"💎 총 자산: {total_krw_value:,.0f}원")
            print("="*60)
        else:
            print("⚠️  보유 자산이 없습니다.")
        
        # 현재가 조회 테스트 (인기 코인)
        print("\n" + "-"*60)
        print("💹 주요 코인 현재가")
        print("-"*60)
        
        popular_coins = ["KRW-BTC", "KRW-ETH", "KRW-XRP", "KRW-ADA"]
        for ticker in popular_coins:
            try:
                price = pyupbit.get_current_price(ticker)
                coin_name = ticker.replace("KRW-", "")
                print(f"  {coin_name:6s}: {price:>15,.0f}원")
            except Exception as e:
                print(f"  {ticker}: 조회 실패 - {e}")
        
        print("="*60)
        print("✅ 모든 테스트 완료!")
        return True
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        print("\n가능한 원인:")
        print("  1. API 키가 잘못되었습니다")
        print("  2. 네트워크 연결 문제")
        print("  3. 업비트 API 서버 문제")
        return False


if __name__ == "__main__":
    test_connection()

