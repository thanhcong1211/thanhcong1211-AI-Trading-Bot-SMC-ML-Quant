"""Generate synthetic OHLCV time series for common price patterns.

Usage:
  & ./.venv/Scripts/Activate.ps1
  python live_trading/generate_price_patterns.py --outdir live_trading/patterns --patterns all

This script creates one CSV per pattern containing columns: time, open, high, low, close, volume
"""
import os
import argparse
import math
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def to_ohlc(price_series, jitter=0.002):
    # price_series: center price for each timestep
    n = len(price_series)
    rng = np.random.RandomState(42)
    o = price_series + rng.randn(n) * (jitter * price_series)
    c = price_series + rng.randn(n) * (jitter * price_series)
    h = np.maximum(o, c) + np.abs(rng.randn(n) * (jitter * price_series))
    l = np.minimum(o, c) - np.abs(rng.randn(n) * (jitter * price_series))
    vol = (np.abs(rng.randn(n)) * 1000 + 100).astype(int)
    return o, h, l, c, vol


def make_index(length, freq='T'):
    # minute frequency by default, ending now
    end = pd.Timestamp.utcnow().floor('T')
    idx = pd.date_range(end=end, periods=length, freq=freq)
    return idx


def head_and_shoulders(length=200, base=1800.0, amplitude=10.0):
    # Create left shoulder, head, right shoulder
    x = np.linspace(0, 1, length)
    left = np.exp(-((x - 0.25) ** 2) * 80) * amplitude * 0.8
    head = np.exp(-((x - 0.5) ** 2) * 200) * amplitude * 1.4
    right = np.exp(-((x - 0.75) ** 2) * 80) * amplitude * 0.85
    base_noise = np.cumsum(np.random.randn(length) * 0.05)
    price = base + base_noise + left + head + right
    return price


def inverse_head_and_shoulders(length=200, base=1800.0, amplitude=10.0):
    return - (head_and_shoulders(length=length, base=0, amplitude=amplitude)) + base


def double_top(length=200, base=1800.0, amplitude=12.0):
    x = np.linspace(0, 1, length)
    p = np.exp(-((x - 0.33) ** 2) * 200) * amplitude + np.exp(-((x - 0.66) ** 2) * 200) * amplitude
    price = base + np.cumsum(np.random.randn(length) * 0.05) + p
    return price


def double_bottom(length=200, base=1800.0, amplitude=12.0):
    return - (double_top(length=length, base=0, amplitude=amplitude)) + base


def triple_top(length=240, base=1800.0, amplitude=10.0):
    x = np.linspace(0, 1, length)
    p = (np.exp(-((x - 0.25) ** 2) * 200) + np.exp(-((x - 0.5) ** 2) * 200) + np.exp(-((x - 0.75) ** 2) * 200)) * amplitude
    price = base + np.cumsum(np.random.randn(length) * 0.04) + p
    return price


def rectangle_range(length=200, base=1800.0, width=8.0):
    # sideways between base - width and base + width
    rng = np.random.RandomState(0)
    levels = base + (rng.rand(length) * 2 - 1) * width
    price = levels + np.cumsum(rng.randn(length) * 0.02)
    return price


def flag_pattern(length=200, base=1800.0, pole=50, flag_len=60, bullish=True):
    # Pole: quick move, then consolidation sloped against trend
    pre = np.linspace(0, 1, pole) * (10 if bullish else -10)
    # flag: small converging channel
    x = np.linspace(0, 1, flag_len)
    slope = -0.3 if bullish else 0.3
    flag = x * slope * (5) + np.sin(x * 10) * 0.5
    rest = np.zeros(length - pole - flag_len)
    seq = np.concatenate([pre, flag, rest])
    price = base + np.cumsum(seq) + np.cumsum(np.random.randn(length) * 0.02)
    return price


def triangle_pattern(length=220, base=1800.0, ascending=True):
    # Create converging highs/lows to an apex
    x = np.linspace(0, 1, length)
    if ascending:
        low = - (1 - x) * 10
        high = x * 5
    else:
        low = - x * 5
        high = (1 - x) * 10
    center = (low + high) / 2
    price = base + center + np.cumsum(np.random.randn(length) * 0.03)
    return price


def pennant(length=180, base=1800.0, bullish=True):
    # short pole then small symmetric triangle
    pole = np.linspace(0, 1, 40) * (8 if bullish else -8)
    tri = triangle_pattern(length=length - 40, base=0, ascending=False)
    seq = np.concatenate([pole, tri - np.mean(tri)])
    price = base + np.cumsum(seq) + np.cumsum(np.random.randn(length) * 0.02)
    return price


def wedge(length=200, base=1800.0, rising=True):
    # Wedge: highs and lows both sloped in same direction, converging
    x = np.linspace(0, 1, length)
    if rising:
        high = x * 6
        low = x * 2
    else:
        high = -x * 2
        low = -x * 6
    center = (high + low) / 2
    price = base + center + np.cumsum(np.random.randn(length) * 0.03)
    return price


PATTERNS = {
    'head_and_shoulders': head_and_shoulders,
    'inverse_head_and_shoulders': inverse_head_and_shoulders,
    'double_top': double_top,
    'double_bottom': double_bottom,
    'triple_top': triple_top,
    'rectangle': rectangle_range,
    'bullish_flag': lambda **kw: flag_pattern(bullish=True, **kw),
    'bearish_flag': lambda **kw: flag_pattern(bullish=False, **kw),
    'ascending_triangle': lambda **kw: triangle_pattern(ascending=True, **kw),
    'descending_triangle': lambda **kw: triangle_pattern(ascending=False, **kw),
    'symmetrical_triangle': lambda **kw: triangle_pattern(ascending=False, **kw),
    'bullish_pennant': lambda **kw: pennant(bullish=True, **kw),
    'bearish_pennant': lambda **kw: pennant(bullish=False, **kw),
    'rising_wedge': lambda **kw: wedge(rising=True, **kw),
    'falling_wedge': lambda **kw: wedge(rising=False, **kw),
}


def build_ohlcv_from_price(price, freq='T'):
    o, h, l, c, v = to_ohlc(price)
    idx = make_index(len(price), freq=freq)
    df = pd.DataFrame({'open': o, 'high': h, 'low': l, 'close': c, 'volume': v}, index=idx)
    df.index.name = 'time'
    df.reset_index(inplace=True)
    return df


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='live_trading/patterns')
    parser.add_argument('--patterns', nargs='+', default=['all'], help="pattern keys or 'all'")
    parser.add_argument('--length', type=int, default=240)
    parser.add_argument('--freq', default='T')
    args = parser.parse_args()

    outdir = os.path.abspath(args.outdir)
    ensure_dir(outdir)

    keys = list(PATTERNS.keys())
    if 'all' in args.patterns:
        chosen = keys
    else:
        chosen = [p for p in args.patterns if p in PATTERNS]

    print(f"Generating patterns: {chosen} -> {outdir}")
    for k in chosen:
        func = PATTERNS[k]
        try:
            price = func(length=args.length, base=1800.0)
        except TypeError:
            price = func(args.length)
        df = build_ohlcv_from_price(price, freq=args.freq)
        outpath = os.path.join(outdir, f"{k}.csv")
        df.to_csv(outpath, index=False)
        print(f"Wrote {outpath} ({len(df)} rows)")


if __name__ == '__main__':
    main()
