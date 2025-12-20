# smc_filters.py
"""
Utility filters for SMC:
- ATR calculation
- killzone (session) checking
- OB / FVG validity helpers
"""
import pandas as pd
import numpy as np
from typing import Tuple

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate ATR (Average True Range) with error handling"""
    try:
        if df is None or len(df) < period:
            return None
        
        required_cols = ['high', 'low', 'close']
        if not all(col in df.columns for col in required_cols):
            return None
        
        high = df['high']
        low = df['low']
        close = df['close']
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period).mean()
    except Exception:
        return None

def is_in_killzone(ts, disabled_hours: list = [(0,6)] , timezone_offset_hours: int = 0) -> bool:
    """
    ts: pandas.Timestamp or datetime
    disabled_hours: list of tuples (start_hour, end_hour) in 24h local time where trading is not allowed
    timezone_offset_hours: shift ts to local if needed
    """
    if ts is None:
        return False
    if not hasattr(ts, 'hour'):
        ts = pd.to_datetime(ts)
    h = (ts.hour + timezone_offset_hours) % 24
    for s,e in disabled_hours:
        if s <= h < e:
            return True
    return False

def ob_is_valid(ob: dict, current_price: float) -> bool:
    """
    Basic validity: still active and price hasn't mitigated it.
    For buy OB: mitigated when price <= distal (filled)
    For sell OB: mitigated when price >= distal
    """
    if ob.get("status") != "active":
        return False
    side = ob.get("side")
    distal = ob.get("distal")
    if side == "buy":
        return current_price > distal
    elif side == "sell":
        return current_price < distal
    return True

def price_in_zone(price: float, proximal: float, distal: float) -> bool:
    lo = min(proximal, distal)
    hi = max(proximal, distal)
    return lo <= price <= hi
