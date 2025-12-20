"""
Integration wrapper for CandlePatternAI.
Provides `enrich_with_candle_patterns(df, scoring=True)` that safely adds pattern columns
(and a `candle_pattern_score` if scoring=True).
"""
from typing import List
import numpy as np

try:
    from ai_modules.CandlePatternAI import CandlePatternAI
except Exception:
    # try lowercase import (file may be named differently on case-insensitive FS)
    try:
        from .CandlePatternAI import CandlePatternAI
    except Exception:
        CandlePatternAI = None


def _row_to_candle(row):
    """Normalize a dataframe row or mapping to a candle dict with keys o,h,l,c.
    This is defensive: it accepts rows with different column name styles ('open','Open','o')
    and also supports positional rows (lists/ndarrays) as a fallback.
    """
    # helper to try multiple possible field names
    def _try_names(r, candidates):
        for name in candidates:
            try:
                # Series or dict access
                val = r[name]
                return val
            except Exception:
                try:
                    # positional access for numpy arrays / lists
                    if hasattr(r, '__getitem__'):
                        # try integer index if name is int
                        if isinstance(name, int):
                            return r[name]
                except Exception:
                    pass
        raise KeyError("No matching field found among candidates")

    # candidate name lists for each field
    open_names = ['open', 'Open', 'o', 'O', 0]
    high_names = ['high', 'High', 'h', 'H', 1]
    low_names = ['low', 'Low', 'l', 'L', 2]
    close_names = ['close', 'Close', 'c', 'C', 3]

    try:
        o = _try_names(row, open_names)
        h = _try_names(row, high_names)
        l = _try_names(row, low_names)
        c = _try_names(row, close_names)
    except Exception:
        # final fallback: try positional access via .iloc if available
        try:
            o = row.iloc[0]
            h = row.iloc[1]
            l = row.iloc[2]
            c = row.iloc[3]
        except Exception:
            # give up with explicit informative error
            raise RuntimeError(f"Cannot extract OHLC from row: columns={getattr(row, 'index', None)}")

def _safe_row_to_candle(row):
    """Safe version of _row_to_candle that returns default dict on error."""
    try:
        return _row_to_candle(row)
    except Exception:
        return {'o': 0.0, 'h': 0.0, 'l': 0.0, 'c': 0.0}


def enrich_with_candle_patterns(df, scoring=True, verbose=True):
    """
    Add candle pattern boolean columns to the dataframe and an optional score.
    Đầy đủ logic, kiểm tra index an toàn cho multi-candle patterns, thông báo tiến trình và lỗi.
    Set verbose=False để tắt log.
    """
    # --- Price direction ---
    if 'close' in df.columns:
        df['price_change_direction'] = np.where(df['close'] > df['close'].shift(1), 1, np.where(df['close'] < df['close'].shift(1), -1, 0))
    # --- RSI feature for momentum analysis ---
    if 'close' in df.columns:
        delta = df['close'].diff()
        up = delta.clip(lower=0)
        down = -1 * delta.clip(upper=0)
        roll_up = up.rolling(14).mean()
        roll_down = down.rolling(14).mean()
        rs = roll_up / roll_down
        df['rsi_14'] = 100 - (100 / (1 + rs))
    # --- EMA features for trend analysis ---
    if 'close' in df.columns:
        df['ema_short'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_long'] = df['close'].ewm(span=50, adjust=False).mean()
    # --- Ensure int dtype for all single-candle pattern columns ---
    for col in ['doji', 'bullish_candle', 'bearish_candle', 'hammer', 'shooting_star', 'inverted_hammer', 'dragonfly_doji', 'gravestone_doji']:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)
    # --- Candle pattern columns ---
    for col in ['bullish_candle', 'bearish_candle', 'body_size', 'upper_shadow', 'lower_shadow']:
        if col not in df.columns:
            df[col] = 0.0
    df['bullish_candle'] = (df['close'] > df['open']).astype(int)
    df['bearish_candle'] = (df['open'] > df['close']).astype(int)
    df['body_size'] = (df['close'] - df['open']).abs()
    df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
    df['doji'] = (df['body_size'] < 0.001).astype(int)
    df['hammer'] = ((df['lower_shadow'] > df['body_size'] * 2) & (df['upper_shadow'] < df['body_size'] * 0.5) & (df['body_size'] > 0.002)).astype(int)
    df['shooting_star'] = ((df['upper_shadow'] > df['body_size'] * 2) & (df['lower_shadow'] < df['body_size'] * 0.5) & (df['body_size'] > 0.002)).astype(int)
    df['inverted_hammer'] = ((df['upper_shadow'] > df['body_size'] * 2) & (df['body_size'] > 0.002)).astype(int)
    df['dragonfly_doji'] = ((df['doji'] == 1) & (df['lower_shadow'] > df['body_size'] * 2)).astype(int)
    df['gravestone_doji'] = ((df['doji'] == 1) & (df['upper_shadow'] > df['body_size'] * 2)).astype(int)
    # --- Single-candle patterns ---
    if CandlePatternAI is None:
        return df
    detector = CandlePatternAI()
    single_methods = {
        'doji': detector.doji,
        'spinning_top': detector.spinning_top,
        'marubozu_bull': detector.marubozu_bull,
        'marubozu_bear': detector.marubozu_bear,
        'hammer': detector.hammer,
        'inverted_hammer': detector.inverted_hammer,
        'hanging_man': detector.hanging_man,
        'shooting_star': detector.shooting_star,
        'dragonfly': detector.dragonfly,
        'gravestone': detector.gravestone,
    }
    # ...existing code...
    for name, fn in single_methods.items():
        df[name] = [int(fn(o,h,l,c)) for o,h,l,c in zip(df['open'],df['high'],df['low'],df['close'])]
    # ...existing code...
    # --- Multi-candle patterns ---
    n = len(df)
    def safe_idx(idx):
        return idx >= 0 and idx < n
    def safe_range(start, end):
        return start >= 0 and end <= n
    def valid_candle(row):
        c = _safe_row_to_candle(row)
        return c is not None and all(k in c and c[k] is not None for k in ['o','h','l','c'])
    # ...existing code...
    multi_methods = {
        'bullish_engulfing': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.bullish_engulfing(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'bearish_engulfing': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.bearish_engulfing(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'piercing': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.piercing(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'dark_cloud': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.dark_cloud(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'morning_star': lambda i: (i >= 2 and safe_idx(i-2) and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-2]) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.morning_star(_safe_row_to_candle(df.iloc[i-2]), _safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'evening_star': lambda i: (i >= 2 and safe_idx(i-2) and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-2]) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.evening_star(_safe_row_to_candle(df.iloc[i-2]), _safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'harami_bull': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.harami_bull(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'harami_bear': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.harami_bear(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'tweezer_top': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.tweezer_top(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'tweezer_bottom': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.tweezer_bottom(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'rising_three': lambda i: (i >= 4 and safe_range(i-4, i+1) and all(valid_candle(df.iloc[j]) for j in range(i-4,i+1)) and detector.rising_three(*[_safe_row_to_candle(df.iloc[j]) for j in range(i-4,i+1)])) or 0,
        'falling_three': lambda i: (i >= 4 and safe_range(i-4, i+1) and all(valid_candle(df.iloc[j]) for j in range(i-4,i+1)) and detector.falling_three(*[_safe_row_to_candle(df.iloc[j]) for j in range(i-4,i+1)])) or 0,
        'inside_bar': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.inside_bar(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'outside_bar': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.outside_bar(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'three_inside_up': lambda i: (i >= 2 and safe_idx(i-2) and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-2]) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.three_inside_up(_safe_row_to_candle(df.iloc[i-2]), _safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'three_inside_down': lambda i: (i >= 2 and safe_idx(i-2) and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-2]) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.three_inside_down(_safe_row_to_candle(df.iloc[i-2]), _safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'gap_up': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.gap_up(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
        'gap_down': lambda i: (i >= 1 and safe_idx(i-1) and safe_idx(i) and valid_candle(df.iloc[i-1]) and valid_candle(df.iloc[i]) and detector.gap_down(_safe_row_to_candle(df.iloc[i-1]), _safe_row_to_candle(df.iloc[i]))) or 0,
    }
    for name, fn in multi_methods.items():
        for i in range(len(df)):
            # ...existing code...
            val = fn(i)
            df.at[df.index[i], name] = int(val) if val else 0
    # ...existing code...
    # --- Scoring ---
    if scoring:
        df['candle_pattern_score'] = df[list(single_methods.keys()) + list(multi_methods.keys())].sum(axis=1)
    return df
