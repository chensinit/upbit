"""
코인 선택 테스트 스크립트
규칙 기반 코인 선택을 수동으로 1회 호출하여 테스트할 수 있습니다.
"""
from coin_selector import CoinSelector
from upbit_trader import UpbitTrader
from config_manager import ConfigManager


def test_coin_selection():
    """코인 선택 테스트"""
    # 모드 설정
    apply_changes = True  # True: 선택된 코인으로 실제 업데이트, False: 미리보기만
    
    print("="*60)
    print("🪙 코인 선택 테스트")
    print("="*60)
    
    if apply_changes:
        print("⚙️  모드: 실제 업데이트 (구독 코인 변경)")
    else:
        print("👀 모드: 미리보기 (구독 코인 변경 안 함)")
    print("="*60)
    
    try:
        # 설정 매니저 초기화
        config_manager = ConfigManager()
        
        # 현재 구독 코인 목록 로드
        print("\n📂 현재 구독 코인 목록 로드 중...")
        current_tickers = config_manager.load_tickers()
        print(f"📌 현재 구독 코인 ({len(current_tickers)}개): {', '.join(current_tickers)}")
        
        # 트레이더 초기화 (보유 코인 조회용)
        print("\n📊 계정 정보 조회 중...")
        trader = UpbitTrader()
        
        # 코인 선택기 초기화
        print("\n🪙 코인 선택기 초기화 중...")
        coin_selector = CoinSelector(trader=trader)
        
        # 코인 선택 실행
        print("\n" + "="*60)
        print("🚀 코인 선택 실행")
        print("="*60)
        
        result = coin_selector.update_coin_universe()
        
        if isinstance(result, tuple):
            selected_coins, detail_info = result
        else:
            # 하위 호환성
            selected_coins = result
            detail_info = {}
        
        print("\n" + "="*60)
        print("📊 선택 결과")
        print("="*60)
        
        print(f"\n✅ 선택된 코인 ({len(selected_coins)}개):")
        for ticker in sorted(selected_coins):
            print(f"   - {ticker}")
        
        # 현재 구독과 비교
        current_set = set(current_tickers)
        selected_set = set(selected_coins)
        
        added = selected_set - current_set
        removed = current_set - selected_set
        
        if added:
            print(f"\n➕ 추가될 코인 ({len(added)}개):")
            for ticker in sorted(added):
                print(f"   - {ticker}")
        
        if removed:
            print(f"\n➖ 제거될 코인 ({len(removed)}개):")
            for ticker in sorted(removed):
                print(f"   - {ticker}")
        
        if not added and not removed:
            print("\n⚪️  변경 없음 (현재 구독과 동일)")
        
        # 상세 정보 출력
        if detail_info:
            print("\n" + "="*60)
            print("📈 상세 정보")
            print("="*60)
            
            print(f"\n전체 KRW 코인: {detail_info.get('total_tickers', 0)}개")
            print(f"필터링 통과: {detail_info.get('filtered_count', 0)}개")
            
            momentum_all = detail_info.get('momentum_all', [])
            momentum_selected = detail_info.get('momentum', [])
            if momentum_all:
                print(f"\nMomentum 후보: {len(momentum_all)}개")
                print(f"  선택됨 ({len(momentum_selected)}개): {', '.join(momentum_selected) if momentum_selected else '없음'}")
            
            dip_all = detail_info.get('dip_all', [])
            dip_selected = detail_info.get('dip', [])
            if dip_all:
                print(f"\nDip 후보: {len(dip_all)}개")
                print(f"  선택됨 ({len(dip_selected)}개): {', '.join(dip_selected) if dip_selected else '없음'}")
        
        # 실제 업데이트 여부 확인 및 실행
        print("\n" + "="*60)
        print("❓ 구독 코인 업데이트")
        print("="*60)
        
        if current_set != selected_set:
            print(f"\n⚠️  현재 구독 코인과 선택된 코인이 다릅니다.")
            print(f"   현재: {len(current_set)}개")
            print(f"   선택: {len(selected_set)}개")
            
            if apply_changes:
                print(f"\n⚙️  구독 코인 업데이트 중...")
                config_manager.save_tickers(sorted(list(selected_set)))
                print(f"✅ 구독 코인 업데이트 완료!")
                print(f"   새로운 구독 코인: {', '.join(sorted(selected_set))}")
            else:
                print(f"\n💡 실제 업데이트를 원하시면:")
                print(f"   1. test_coin_selection.py에서 apply_changes = True로 설정")
                print(f"   2. 또는 ai_trader.py를 실행 (새벽 시간에 자동 실행)")
        else:
            print(f"\n✅ 현재 구독 코인과 동일합니다. 업데이트 불필요.")
        
        print("\n" + "="*60)
        print("✅ 테스트 완료")
        print("="*60)
        print(f"\n💾 코인 선택 히스토리는 data/coin_selection_history/ 디렉토리에 저장됩니다.")
        print(f"   (ai_trader.py 실행 시 자동 저장)")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_coin_selection()

