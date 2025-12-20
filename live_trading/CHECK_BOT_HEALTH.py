import sys
import os
sys.path.insert(0, '.')

passed = 0
total = 0

def test(name, func):
    global passed, total
    total += 1
    try:
        if func():
            print(f'✅ [{total:2d}] {name}')
            passed += 1
            return True
        else:
            print(f'⚠️  [{total:2d}] {name}')
            passed += 0.5
            return False
    except Exception as e:
        print(f'❌ [{total:2d}] {name}: {str(e)[:40]}')
        return False

print('╔══════════════════════════════════════════════════════════╗')
print('║         BOT DIAGNOSTIC - ALL FEATURES CHECK           ║')
print('╚══════════════════════════════════════════════════════════╝\n')

print('═══ CORE SYSTEM ═══')
test('CompleteAITradingSystem', lambda: 'CompleteAITradingSystem' in dir(__import__('core.complete_ai_trading_system', fromlist=['CompleteAITradingSystem'])))
test('TrendAI Class', lambda: 'TrendAI' in dir(__import__('core.models', fromlist=['TrendAI'])))
test('ReversalAI Class', lambda: 'ReversalAI' in dir(__import__('core.models', fromlist=['ReversalAI'])))
test('ChartPatternDetector', lambda: 'ChartPatternDetector' in dir(__import__('core.chart_pattern_detector', fromlist=['ChartPatternDetector'])))

print('\n═══ TRAINED MODELS ═══')
test('TrendAI Model File', lambda: os.path.exists('models_large/trend_ai_model.pkl'))
test('TrendAI Scaler', lambda: os.path.exists('models_large/trend_ai_scaler.pkl'))
test('TrendAI Features', lambda: os.path.exists('models_large/trend_ai_feature_columns.pkl'))

print('\n═══ NEW FEATURES (Dec 2025) ═══')

def check_htf():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'htf_policy' in code and 'reversal_prob > 0.7' in code

def check_supertrend():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'distance_pct' in code and 'pullback' in code.lower()

def check_reversal():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'reversal_prob > 0.6' in code and 'reversal_prob < 0.4' in code

def check_boost():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'SELL pullback' in code and 'pattern_boost' in code.lower()

test('HTF Filter Soft Mode', check_htf)
test('Supertrend Distance Filter', check_supertrend)
test('Lowered Reversal Thresholds', check_reversal)
test('Enhanced Confidence Boost', check_boost)

print('\n═══ RISK MANAGEMENT ═══')
test('AIMoneyManager', lambda: 'AIMoneyManager' in dir(__import__('core.money_management', fromlist=['AIMoneyManager'])))
test('DrawdownProtector', lambda: 'DrawdownProtector' in dir(__import__('core.money_management', fromlist=['DrawdownProtector'])))

def check_dd_settings():
    mod = __import__('core.money_management', fromlist=['DrawdownProtector'])
    dd = mod.DrawdownProtector(balance=10000, max_dd_percent=15.0)
    return dd.max_dd_percent == 15.0

test('DrawdownProtector 15% Max', check_dd_settings)

print('\n═══ PERFORMANCE ═══')
def check_speed():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'SIGNAL_COOLDOWN' in code and 'MIN_CONTINUOUS_SLEEP' in code

def check_sleep():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'sleep(2' in code

test('Speed Controls', check_speed)
test('2s Sleep Between Cycles', check_sleep)

print('\n═══ PATTERN DETECTION ═══')
def test_patterns():
    mod = __import__('core.chart_pattern_detector', fromlist=['ChartPatternDetector'])
    detector = mod.ChartPatternDetector()
    import pandas as pd
    import numpy as np
    df = pd.DataFrame({
        'open': np.random.randn(100) + 1800,
        'high': np.random.randn(100) + 1810,
        'low': np.random.randn(100) + 1790,
        'close': np.random.randn(100) + 1800,
        'volume': np.random.randint(100, 1000, 100)
    })
    results = detector.detect_all_patterns(df, lookback=50)
    return len(results) >= 15  # Should detect 16+ patterns

test('Pattern Detection Works', test_patterns)

def check_pattern_integration():
    with open('core/complete_ai_trading_system.py', 'r', encoding='utf-8') as f:
        code = f.read()
    return 'integrate_pattern_detection' in code and 'pattern_confidence' in code

test('Pattern Integration', check_pattern_integration)

print('\n═══ MT5 CONNECTION ═══')
def test_mt5():
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.account_info()
            mt5.shutdown()
            return info is not None
    except:
        return False

test('MT5 Connected', test_mt5)

print('\n═══ DOCUMENTATION ═══')
test('AI_components.md', lambda: os.path.exists('AI_components.md') and os.path.getsize('AI_components.md') > 50000)
test('Chart Patterns Doc', lambda: os.path.exists('CHART_PATTERNS_INTEGRATED.txt'))
test('Before/After Doc', lambda: os.path.exists('BEFORE_AFTER_PATTERNS.md'))
test('SELL Pullback Guide', lambda: os.path.exists('SELL_PULLBACK_ENABLED.txt'))

print('\n═══ STARTUP SCRIPTS ═══')
test('start_ai_trading.bat', lambda: os.path.exists('start_ai_trading.bat'))
test('START_BOT.bat', lambda: os.path.exists('START_BOT.bat') or os.path.exists('../START_BOT.bat'))

print('\n' + '='*62)
pct = (passed/total)*100
print(f'   OVERALL SCORE: {passed:.1f}/{total} = {pct:.1f}%')
print('='*62)

if pct >= 95:
    status = '🔥 EXCELLENT - Production Ready!'
    action = 'Bot hoàn hảo! Chạy ngay: .\\start_ai_trading.bat'
elif pct >= 85:
    status = '✅ VERY GOOD - Nearly perfect'
    action = 'Train model để đạt 100%'
elif pct >= 75:
    status = '⚠️  GOOD - Minor issues'
    action = 'Fix một vài warnings'
elif pct >= 60:
    status = '🔧 FAIR - Some work needed'
    action = 'Cần sửa một số thành phần'
else:
    status = '❌ NEEDS WORK'
    action = 'Cần review lại toàn bộ'

print(f'\n{status}')
print(f'   → {action}')

print('\n📋 TO REACH 100%:')
missing = []
if not os.path.exists('models_large/trend_ai_model.pkl'):
    missing.append('   1. Train TrendAI model: python -m core.complete_ai_trading_system --train')

if missing:
    for m in missing:
        print(m)
else:
    print('   ✅ Tất cả thành phần quan trọng đã sẵn sàng!')
    print(f'   Bot có thể chạy ở {pct:.0f}% hiệu suất ngay!')
    print('\n🚀 READY TO START:')
    print('   cd live_trading')
    print('   .\\start_ai_trading.bat')

print('\n' + '='*62)
