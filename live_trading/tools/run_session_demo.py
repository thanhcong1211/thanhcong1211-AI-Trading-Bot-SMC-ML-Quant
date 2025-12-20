import sys, time, os
# Ensure both project root and `live_trading` package dir are on sys.path so
# absolute imports like `logic.*` inside `complete_ai_trading_system` resolve.
proj_root = r'C:/Users/ROG/AppData/Roaming/MetaQuotes/Terminal/D0E8209F77C8CF37AD8BF550E51FF075/MQL5'
sys.path.insert(0, proj_root)
sys.path.insert(0, os.path.join(proj_root, 'live_trading'))
from core.complete_ai_trading_system import CompleteAITradingSystem

ai = CompleteAITradingSystem(live_lot_cap=0.05)
ai.enable_session_whitelist = True
print('Session whitelist set to', ai.enable_session_whitelist)
# Force high balance to see lot calc
try:
    ai.money_manager.current_balance = 1000000.0
    print('Forced balance ->', ai.money_manager.current_balance)
except Exception as e:
    print('Could not set balance', e)
# Run multiple generate_live_signal to observe session logs
for i in range(3):
    print('\n--- Run', i+1, '---')
    ai.generate_live_signal(demo_mode=True, min_confidence=0.0, enable_sideways_filter=False)
    time.sleep(1)
print('Done')
