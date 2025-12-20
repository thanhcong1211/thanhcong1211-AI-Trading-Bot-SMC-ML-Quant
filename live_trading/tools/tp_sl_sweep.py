import csv
import json
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]


def load_backtest(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_mt5_csv(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            r['timestamp'] = datetime.strptime(r['timestamp'], '%Y-%m-%d %H:%M:%S')
            for k in ('open', 'high', 'low', 'close'):
                r[k] = float(r[k])
            rows.append(r)
    return rows


def find_candle_index(candles, ts):
    # find first candle with timestamp >= ts
    for i, c in enumerate(candles):
        if c['timestamp'] >= ts:
            return i
    return None


def simulate_trade_on_candles(trade, candles, start_idx, tp_mult, sl_mult, max_steps=72):
    action = trade['action']
    entry = float(trade['entry_price'])
    orig_tp = float(trade['tp_price'])
    orig_sl = float(trade['sl_price'])
    lot = float(trade.get('lot_size', 1.0))

    base_tp_dist = abs(orig_tp - entry)
    base_sl_dist = abs(orig_sl - entry)

    # new targets
    if action == 'BUY':
        new_tp = entry + base_tp_dist * tp_mult
        new_sl = entry - base_sl_dist * sl_mult
    else:
        new_tp = entry - base_tp_dist * tp_mult
        new_sl = entry + base_sl_dist * sl_mult

    # iterate candles after entry
    n = len(candles)
    for j in range(start_idx, min(n, start_idx + max_steps)):
        c = candles[j]
        high = c['high']
        low = c['low']
        # detect hits
        if action == 'BUY':
            tp_hit = high >= new_tp
            sl_hit = low <= new_sl
            if tp_hit and sl_hit:
                # heuristic: which is closer to open
                open_p = c['open']
                if (new_tp - open_p) <= (open_p - new_sl):
                    exit_price = new_tp
                    reason = 'tp'
                else:
                    exit_price = new_sl
                    reason = 'sl'
                return exit_price, reason, j
            if tp_hit:
                return new_tp, 'tp', j
            if sl_hit:
                return new_sl, 'sl', j
        else:
            tp_hit = low <= new_tp
            sl_hit = high >= new_sl
            if tp_hit and sl_hit:
                open_p = c['open']
                if (open_p - new_tp) <= (new_sl - open_p):
                    exit_price = new_tp
                    reason = 'tp'
                else:
                    exit_price = new_sl
                    reason = 'sl'
                return exit_price, reason, j
            if tp_hit:
                return new_tp, 'tp', j
            if sl_hit:
                return new_sl, 'sl', j

    # if none hit, use last candle close as exit
    last = candles[min(n - 1, start_idx + max_steps - 1)]
    return last['close'], 'last', min(n - 1, start_idx + max_steps - 1)


def pnl_from_exit(trade, exit_price):
    entry = float(trade['entry_price'])
    lot = float(trade.get('lot_size', 1.0))
    if trade['action'] == 'BUY':
        return (exit_price - entry) * lot
    else:
        return (entry - exit_price) * lot


def run_grid(backtest_json, candles, out_csv):
    trades = backtest_json['trades']
    # grid of multipliers
    tp_mults = [0.5, 0.75, 1.0, 1.5, 2.0]
    sl_mults = [0.5, 0.75, 1.0, 1.5, 2.0]

    results = []
    # prepare candle timestamps index
    for tp_m in tp_mults:
        for sl_m in sl_mults:
            equity = 0.0
            equity_series = []
            wins = 0
            total = 0
            for tr in trades:
                ts = datetime.strptime(tr['timestamp'], '%Y-%m-%d %H:%M:%S')
                idx = find_candle_index(candles, ts)
                if idx is None:
                    continue
                exit_price, reason, exit_idx = simulate_trade_on_candles(tr, candles, idx + 1, tp_m, sl_m)
                trade_pnl = pnl_from_exit(tr, exit_price)
                equity += trade_pnl
                equity_series.append(equity)
                total += 1
                if trade_pnl > 0:
                    wins += 1

            win_rate = (wins / total) * 100 if total else 0.0
            total_pnl = equity
            # simple max drawdown calc
            peak = -1e18
            mdd = 0.0
            for v in equity_series:
                if v > peak:
                    peak = v
                dd = peak - v
                if dd > mdd:
                    mdd = dd

            results.append({
                'tp_mult': tp_m,
                'sl_mult': sl_m,
                'trades_sim': total,
                'win_rate_pct': round(win_rate, 2),
                'total_pnl': round(total_pnl, 2),
                'max_drawdown': round(mdd, 2)
            })

    # write CSV sorted by win_rate then pnl
    results = sorted(results, key=lambda r: (-r['win_rate_pct'], -r['total_pnl']))
    with open(out_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    return results


if __name__ == '__main__':
    base = BASE
    bt = load_backtest(base / 'backtest_results.json')
    candles = load_mt5_csv(base / 'mt5_h1.csv')
    out = base / 'tp_sl_sweep_results.csv'
    print('Running TP/SL sweep, this may take a few seconds...')
    res = run_grid(bt, candles, out)
    print('Done. Top results:')
    for r in res[:5]:
        print(r)
    print('CSV saved to', out)
