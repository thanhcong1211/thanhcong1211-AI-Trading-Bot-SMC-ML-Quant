# example_smc_integration.py
"""
Example: Tích hợp SMC MTF Orchestrator với CompleteAITradingSystem
===================================================================

Flow:
1. Load multi-timeframe data (H4/H1/M15/M5)
2. Detect & persist Order Blocks using SMCMTFOrchestrator
3. Find LTF entry candidates
4. Score & filter candidates
5. Pass to MoneyManager/FusionAI for execution
"""

import pandas as pd
from ai_modules.smc import SMCMTFOrchestrator, finalize_candidates

def example_smc_workflow(symbol: str = "EURUSD"):
    """
    Ví dụ workflow SMC hoàn chỉnh
    """
    # 1. Load data từ MT5 hoặc CSV (giả sử đã có)
    # df_h4 = load_mt5_data(symbol, 'H4', bars=500)
    # df_h1 = load_mt5_data(symbol, 'H1', bars=1000)
    # df_m15 = load_mt5_data(symbol, 'M15', bars=2000)
    # df_m5 = load_mt5_data(symbol, 'M5', bars=5000)
    
    # Set attrs để orchestrator nhận dạng
    # df_h4.attrs['symbol'] = symbol
    # df_h4.attrs['timeframe'] = 'H4'
    # df_h1.attrs['symbol'] = symbol
    # df_h1.attrs['timeframe'] = 'H1'
    # df_m15.attrs['symbol'] = symbol
    # df_m15.attrs['timeframe'] = 'M15'
    # df_m5.attrs['symbol'] = symbol
    # df_m5.attrs['timeframe'] = 'M5'
    
    # dfs = {
    #     'H4': df_h4,
    #     'H1': df_h1,
    #     'M15': df_m15,
    #     'M5': df_m5
    # }
    
    # 2. Khởi tạo SMC Orchestrator (persistence enabled)
    orch = SMCMTFOrchestrator(state_path="smc_state.json")
    
    # 3. Ingest MTF data - detect & persist Order Blocks
    # orch.ingest_mtfs(dfs, persist_new=True)
    print("✅ Order Blocks detected & persisted")
    
    # 4. Find LTF entry candidates (M5 sniper entries)
    # candidates = orch.find_ltf_entries(dfs, max_distance_pips=0.0006)
    # print(f"🎯 Found {len(candidates)} LTF candidates")
    
    # 5. Score & filter candidates
    # final = finalize_candidates(
    #     candidates, 
    #     dfs, 
    #     disabled_hours=[(0,6), (22,24)]  # Killzone: 0-6h và 22-24h
    # )
    
    # print(f"✅ {len(final)} candidates passed filters")
    # for idx, cand in enumerate(final, 1):
    #     print(f"\n--- Candidate #{idx} ---")
    #     print(f"  Side: {cand['side'].upper()}")
    #     print(f"  Entry: {cand['entry']:.5f}")
    #     print(f"  SL: {cand['sl']:.5f}")
    #     print(f"  TP: {cand['tp']:.5f}")
    #     print(f"  Score: {cand['score']:.2%}")
    #     print(f"  Reason: {cand['reason']}")
    #     print(f"  OB ID: {cand['ob_id'][:8]}...")
    
    # 6. Pass to MoneyManager/ExecutionAI
    # if final:
    #     best = final[0]  # Highest score
    #     # money_manager.propose_trade(
    #     #     symbol=symbol,
    #     #     side=best['side'],
    #     #     entry=best['entry'],
    #     #     sl=best['sl'],
    #     #     tp=best['tp'],
    #     #     confidence=best['score']
    #     # )
    
    return None  # final


def integrate_with_complete_system():
    """
    Tích hợp vào CompleteAITradingSystem
    """
    from core.complete_ai_trading_system import CompleteAITradingSystem
    
    # Khởi tạo system
    ai_system = CompleteAITradingSystem(
        symbol="EURUSD",
        timeframe="M5",
        mode="live"
    )
    
    # Thêm SMC Orchestrator vào system
    ai_system.smc_orch = SMCMTFOrchestrator(state_path="smc_state_eurusd.json")
    
    # Hook vào process_signal để inject SMC suggestions
    original_process = ai_system.process_signal
    
    def enhanced_process(signal):
        # 1. Get MTF data
        dfs = {
            'H4': ai_system.get_timeframe_data('H4'),
            'H1': ai_system.get_timeframe_data('H1'),
            'M15': ai_system.get_timeframe_data('M15'),
            'M5': ai_system.data
        }
        
        # Set attrs
        for tf, df in dfs.items():
            if df is not None:
                df.attrs['symbol'] = ai_system.symbol
                df.attrs['timeframe'] = tf
        
        # 2. Ingest & find SMC entries
        ai_system.smc_orch.ingest_mtfs(dfs, persist_new=True)
        smc_candidates = ai_system.smc_orch.find_ltf_entries(dfs, max_distance_pips=0.0006)
        smc_final = finalize_candidates(smc_candidates, dfs, disabled_hours=[(0,6)])
        
        # 3. Merge với AI signal
        if smc_final:
            best_smc = smc_final[0]
            signal['smc_suggestion'] = best_smc
            signal['confidence'] = (signal['confidence'] + best_smc['score']) / 2  # Blend
            
            # Override entry/sl/tp nếu SMC score cao hơn
            if best_smc['score'] > signal['confidence']:
                signal['entry_price'] = best_smc['entry']
                signal['stop_loss'] = best_smc['sl']
                signal['take_profit'] = best_smc['tp']
        
        # 4. Gọi original process
        return original_process(signal)
    
    ai_system.process_signal = enhanced_process
    
    print("✅ SMC Orchestrator integrated into CompleteAITradingSystem")
    return ai_system


if __name__ == "__main__":
    print("=== SMC Integration Example ===\n")
    
    # Example 1: Standalone workflow
    print("1. Standalone SMC Workflow:")
    example_smc_workflow("EURUSD")
    
    print("\n" + "="*50 + "\n")
    
    # Example 2: Integration với CompleteAITradingSystem
    print("2. Integration with CompleteAITradingSystem:")
    # system = integrate_with_complete_system()
    # system.run()
