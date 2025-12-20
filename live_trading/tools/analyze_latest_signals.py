import json, os
p = os.path.join(os.path.dirname(__file__), '..', 'logs', 'latest_signals.jsonl')
try:
    with open(p, 'r', encoding='utf-8') as f:
        lines = f.read().strip().splitlines()
except Exception as e:
    print('Error reading file:', e)
    raise SystemExit(1)

sells = []
for i, L in enumerate(lines):
    try:
        obj = json.loads(L)
    except Exception:
        # try to repair simple single-quote dicts by replacing single quotes
        try:
            fixed = L.replace("'", '"')
            obj = json.loads(fixed)
        except Exception:
            continue
    if obj.get('action') == 'SELL':
        sells.append(obj)

if not sells:
    print('No SELL signals found in', p)
else:
    print(f'Found {len(sells)} SELL signals:\n')
    for s in sells:
        sid = s.get('signal_id')
        ts = s.get('timestamp')
        price = s.get('price')
        trend = s.get('trend_ai')
        rev = s.get('reversal_confidence') if 'reversal_confidence' in s else s.get('reversal_confidence', None)
        fusion = s.get('fusion_reasons')
        print('---')
        print('signal_id:', sid)
        print('timestamp :', ts)
        print('price     :', price)
        print('trend_ai  :', trend)
        print('reversal_confidence:', rev)
        print('fusion_reasons:', fusion)
        # print full record truncated
        print('raw keys:', ', '.join(list(s.keys())[:20]))
    print('\nDone.')
