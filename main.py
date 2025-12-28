"""
업비트 자동 트레이딩 메인 스크립트
"""
import time
from upbit_trader import UpbitTrader
from trading_strategies import SimpleStrategy


def main():
    """메인 함수"""
    print("="*60)
    print("🚀 업비트 자동 트레이딩 시스템")
    print("="*60)
    
    try:
        # 트레이더 초기화
        trader = UpbitTrader()
        
        # 계정 정보 출력
        trader.print_account_info()
        
        # 전략 초기화
        strategy = SimpleStrategy(trader)
        
        # 거래할 티커 설정 (예: 비트코인)
        TICKER = "KRW-BTC"
        
        print(f"\n📌 거래 티커: {TICKER}")
        print("전략을 선택하세요:")
        print("1. 이동평균선 전략 (골든크로스/데드크로스)")
        print("2. RSI 전략")
        print("3. 매수 후 보유 전략")
        print("4. 수동 거래 모드")
        print("5. 종료")
        
        choice = input("\n선택 (1-5): ").strip()
        
        if choice == "1":
            # 이동평균선 전략
            short_period = int(input("단기 이동평균 기간 (기본 5): ") or "5")
            long_period = int(input("장기 이동평균 기간 (기본 20): ") or "20")
            buy_amount = float(input("매수 금액 (원, 기본 10000): ") or "10000")
            
            print("\n전략 실행 중... (Ctrl+C로 중지)")
            while True:
                try:
                    strategy.moving_average_strategy(TICKER, short_period, long_period, buy_amount)
                    time.sleep(60)  # 1분마다 체크
                except KeyboardInterrupt:
                    print("\n\n⏹️  전략 중지")
                    break
        
        elif choice == "2":
            # RSI 전략
            period = int(input("RSI 기간 (기본 14): ") or "14")
            buy_amount = float(input("매수 금액 (원, 기본 10000): ") or "10000")
            
            print("\n전략 실행 중... (Ctrl+C로 중지)")
            while True:
                try:
                    strategy.rsi_strategy(TICKER, period, buy_amount)
                    time.sleep(60)  # 1분마다 체크
                except KeyboardInterrupt:
                    print("\n\n⏹️  전략 중지")
                    break
        
        elif choice == "3":
            # 매수 후 보유 전략
            buy_amount = float(input("매수 금액 (원, 기본 10000): ") or "10000")
            strategy.simple_buy_hold(TICKER, buy_amount)
        
        elif choice == "4":
            # 수동 거래 모드
            manual_trading(trader)
        
        elif choice == "5":
            print("👋 프로그램 종료")
        
        else:
            print("❌ 잘못된 선택입니다.")
    
    except ValueError as e:
        print(f"❌ 오류: {e}")
        print("\n💡 해결 방법:")
        print("1. .env 파일을 생성하고 다음 내용을 추가하세요:")
        print("   UPBIT_ACCESS_KEY=your_access_key")
        print("   UPBIT_SECRET_KEY=your_secret_key")
        print("\n2. 또는 config.py에서 직접 설정하세요.")
    
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")


def manual_trading(trader: UpbitTrader):
    """수동 거래 모드"""
    print("\n" + "="*60)
    print("📝 수동 거래 모드")
    print("="*60)
    
    while True:
        print("\n명령어:")
        print("1. 잔고 조회")
        print("2. 현재가 조회")
        print("3. 시장가 매수")
        print("4. 시장가 매도")
        print("5. 지정가 매수")
        print("6. 지정가 매도")
        print("7. 계정 정보")
        print("8. 종료")
        
        cmd = input("\n명령어 선택 (1-8): ").strip()
        
        if cmd == "1":
            ticker = input("티커 입력 (예: KRW-BTC, 또는 KRW): ").strip()
            balance = trader.get_balance(ticker)
            print(f"💰 잔고: {balance}")
        
        elif cmd == "2":
            ticker = input("티커 입력 (예: KRW-BTC): ").strip()
            price = trader.get_current_price(ticker)
            print(f"💵 현재가: {price:,.0f}원")
        
        elif cmd == "3":
            ticker = input("티커 입력 (예: KRW-BTC): ").strip()
            amount = float(input("매수 금액 (원): "))
            trader.buy_market_order(ticker, amount)
        
        elif cmd == "4":
            ticker = input("티커 입력 (예: KRW-BTC): ").strip()
            volume = float(input("매도 수량: "))
            trader.sell_market_order(ticker, volume)
        
        elif cmd == "5":
            ticker = input("티커 입력 (예: KRW-BTC): ").strip()
            amount = float(input("매수 금액 (원): "))
            price = float(input("지정가 (원): "))
            trader.buy_limit_order(ticker, amount, price)
        
        elif cmd == "6":
            ticker = input("티커 입력 (예: KRW-BTC): ").strip()
            volume = float(input("매도 수량: "))
            price = float(input("지정가 (원): "))
            trader.sell_limit_order(ticker, volume, price)
        
        elif cmd == "7":
            trader.print_account_info()
        
        elif cmd == "8":
            print("👋 수동 거래 모드 종료")
            break
        
        else:
            print("❌ 잘못된 명령어입니다.")


if __name__ == "__main__":
    main()

