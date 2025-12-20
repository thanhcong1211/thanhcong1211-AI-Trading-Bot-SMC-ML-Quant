import numpy as np
import pandas as pd

class VolatilityAI:
    """
    VolatilityAI: compute ATR, vol_index and regime.
    Usage:
        v = VolatilityAI()
        out = v.analyze(df)  # df with 'high','low','close'
    """

    def __init__(self, atr_period=14, vol_window=50):
        self.atr_period = atr_period
        self.vol_window = vol_window

    def _atr(self, df, period):
        high = df['high'].astype(float)
        low = df['low'].astype(float)
        close = df['close'].astype(float)
        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not np.isnan(atr) else 0.0

    def analyze(self, df):
        if df is None or len(df) < max(self.atr_period, self.vol_window) + 2:
            return {"vol_index": 0.0, "regime": "unknown", "recommendation": "skip"}

        atr = self._atr(df, self.atr_period)
        returns = df['close'].pct_change().fillna(0).abs()
        vol_index = float(returns.rolling(self.vol_window).std().iloc[-1])
        price = float(df['close'].iloc[-1])
        atr_norm = atr / (price + 1e-9)
        if vol_index > atr_norm * 2.5:
            regime = "high"
            rec = "avoid"
        elif vol_index > atr_norm * 1.2:
            regime = "elevated"
            rec = "caution"
        else:
            regime = "low"
            rec = "ok"

        return {"vol_index": float(round(vol_index,6)), "regime": regime, "recommendation": rec, "atr": float(round(atr,6)), "risk": float(round(vol_index,6))}
