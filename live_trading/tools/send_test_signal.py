"""send_test_signal.py
Ghi một tín hiệu thử nghiệm (action=BUY) vào Files/ai_signals.txt
Sử dụng atomic write (temp -> rename).
"""
from pathlib import Path
import json
from datetime import datetime

# Resolve project root (MQL5 folder is two levels above this file)
repo_root = Path(__file__).resolve().parents[2]
out_dir = repo_root / 'Files'
out_dir.mkdir(parents=True, exist_ok=True)
out_file = out_dir / 'ai_signals.txt'

def build_signal():
    now = datetime.now().isoformat()
    signal = {
        'action': 'BUY',
        'symbol': 'XAUUSD',
        'price': 1850.50,
        'entry_price': 1850.50,
        'sl_price': 1847.50,
        'tp_price': 1856.50,
        'lot_size': 0.01,
        'confidence': 85.0,
        'timestamp': now,
        'signal_id': 9999,
        'mt5_log': 'TEST SIGNAL: BUY XAUUSD 0.01 lot',
        'reason': 'TEST_FORCE_SIGNAL'
    }
    return signal


def atomic_write(path: Path, data: str):
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(data)
        f.flush()
    # replace
    tmp.replace(path)


if __name__ == '__main__':
    sig = build_signal()
    payload = json.dumps(sig, ensure_ascii=False)
    atomic_write(out_file, payload)
    print(f"WROTE: {out_file}")
    print(payload)
