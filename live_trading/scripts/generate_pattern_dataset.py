"""Generate a labeled dataset (CSV) of synthetic price-pattern examples.

Each sample is an OHLCV time series with metadata columns repeated per row:
  sample_id, pattern, base, amplitude, jitter, length, tick_size, spread, volume_scale

Also writes a `metadata.csv` summarizing each sample (one row per sample).

Usage (PowerShell):
  & ./.venv/Scripts/Activate.ps1
  python live_trading/generate_pattern_dataset.py --outdir live_trading/dataset --samples 5

"""
import os
import argparse
import uuid
import numpy as np
import pandas as pd
import sys

# Ensure project root is on sys.path so we can import the sibling module
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from generate_price_patterns import PATTERNS, build_ohlcv_from_price


def apply_tick_spread(df, tick_size=0.01, spread=0.05, volume_scale=1.0):
    # Snap prices to tick and add spread (mid->bid/ask). We'll keep OHLC as mid-based but add spread metadata
    df = df.copy()
    # snap
    for col in ['open', 'high', 'low', 'close']:
        df[col] = (df[col] / tick_size).round() * tick_size
    # Add spread columns (for realism) as two extra columns
    df['bid'] = df['close'] - spread / 2.0
    df['ask'] = df['close'] + spread / 2.0
    df['volume'] = (df['volume'] * volume_scale).astype(int)
    return df


def generate_dataset(outdir, samples_per_pattern=10, lengths=(200, 260), jitter_range=(0.001, 0.01),
                     amplitude_range=(6.0, 14.0), base_range=(1700, 1900), tick_size=0.01, spread=0.05,
                     volume_scale=1.0):
    ensure_dir(outdir)
    rows = []
    meta = []
    sample_id = 0

    patterns = list(PATTERNS.keys())
    rng = np.random.RandomState(123)

    for p in patterns:
        func = PATTERNS[p]
        for i in range(samples_per_pattern):
            sample_id += 1
            length = int(rng.randint(lengths[0], lengths[1]+1))
            amplitude = float(rng.uniform(amplitude_range[0], amplitude_range[1]))
            base = float(rng.uniform(base_range[0], base_range[1]))
            jitter = float(rng.uniform(jitter_range[0], jitter_range[1]))

            # call pattern function with common kw args where accepted
            # Call pattern generator robustly: prefer (length, base) kwargs, then fallbacks
            try:
                price = func(length=length, base=base)
            except TypeError:
                try:
                    price = func(length=length)
                except TypeError:
                    try:
                        price = func(length)
                    except Exception:
                        # Last resort: call without args
                        price = func()

            # Add small multiplicative noise per-sample
            price = price * (1.0 + rng.randn(len(price)) * (jitter * 0.1))

            df = build_ohlcv_from_price(price, freq='T')
            df = apply_tick_spread(df, tick_size=tick_size, spread=spread, volume_scale=volume_scale)

            # attach metadata columns per row
            df['sample_id'] = sample_id
            df['pattern'] = p
            df['base'] = base
            df['amplitude'] = amplitude
            df['jitter'] = jitter
            df['length'] = length
            df['tick_size'] = tick_size
            df['spread'] = spread
            df['volume_scale'] = volume_scale

            rows.append(df)

            meta.append({'sample_id': sample_id, 'pattern': p, 'base': base, 'amplitude': amplitude,
                         'jitter': jitter, 'length': length, 'tick_size': tick_size, 'spread': spread,
                         'volume_scale': volume_scale})

    # concat and write
    out_df = pd.concat(rows, ignore_index=True)
    csv_path = os.path.join(outdir, 'pattern_dataset.csv')
    meta_path = os.path.join(outdir, 'metadata.csv')
    out_df.to_csv(csv_path, index=False)
    pd.DataFrame(meta).to_csv(meta_path, index=False)
    return csv_path, meta_path


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--outdir', default='live_trading/dataset')
    parser.add_argument('--samples', type=int, default=10, help='samples per pattern')
    parser.add_argument('--tick', type=float, default=0.01)
    parser.add_argument('--spread', type=float, default=0.05)
    parser.add_argument('--volume-scale', type=float, default=1.0)
    args = parser.parse_args()

    outdir = os.path.abspath(args.outdir)
    print(f"Generating dataset -> {outdir} ({args.samples} samples per pattern)")
    csv_path, meta_path = generate_dataset(outdir, samples_per_pattern=args.samples,
                                          tick_size=args.tick, spread=args.spread,
                                          volume_scale=args.volume_scale)
    print("Wrote dataset:", csv_path)
    print("Wrote metadata:", meta_path)


if __name__ == '__main__':
    main()
