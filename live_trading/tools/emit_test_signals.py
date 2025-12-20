import sys, os, time
proj_root = r'C:/Users/ROG/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5'
sys.path.insert(0, proj_root)
sys.path.insert(0, os.path.join(proj_root, 'live_trading'))

from core.complete_ai_trading_system import CompleteAITradingSystem

if __name__ == '__main__':
    ai = CompleteAITradingSystem(live_lot_cap=0.05)
    # ensure we write logs
    try:
        os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'logs'), exist_ok=True)
    except Exception:
        pass

    # Force a high balance so lot calculations show capping behaviour
    try:
        ai.money_manager.current_balance = 1000000.0
    except Exception:
        pass

    # Emit test signals (this writes directly via _write_signal_to_file and also persists to logs/latest_signals.jsonl)
    ai.emit_test_signals(mode='all')
    print('Emit_test_signals completed')
