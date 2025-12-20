# logic/regime_ai.py
import numpy as np
import pandas as pd

class RegimeAI:
    """Simple Regime classifier.
    Usage:
        r = RegimeAI()
        out = r.analyze(df)  # df has 'open','high','low','close','volume'
        out -> {"regime": "trend"/"range"/"high_vol"/"unknown", "score":0.0-1.0, "meta": {...}}
    """

    def __init__(self, atr_period=14, ma_short=20, ma_long=50, vol_window=50, adx_like_period=14):
        self.atr_period = atr_period
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.vol_window = vol_window
        self.adx_like_period = adx_like_period

    def _atr(self, df, n):
        h = df['high']; l = df['low']; c = df['close']
        tr1 = h - l
        tr2 = (h - c.shift(1)).abs()
        tr3 = (l - c.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(n).mean().iloc[-1] if len(tr) >= n else np.nan

    def _ma(self, series, n):
        return series.rolling(n).mean().iloc[-1] if len(series) >= n else np.nan

    def _vol_index(self, df):
        returns = df['close'].pct_change().fillna(0).abs()
        return float(returns.rolling(self.vol_window).std().iloc[-1]) if len(returns) >= self.vol_window else 0.0

    def analyze(self, df):
        try:
            if df is None or len(df) < max(self.ma_long, self.atr_period, self.vol_window):
                return {"regime":"unknown","score":0.0,"meta":{}}

            price = df['close'].astype(float)
            atr = float(self._atr(df, self.atr_period) or 0.0)
            vol_idx = float(self._vol_index(df) or 0.0)

            ma_s = float(self._ma(price, self.ma_short) or 0.0)
            ma_l = float(self._ma(price, self.ma_long) or 0.0)
            ma_gap = 0.0
            if ma_l > 0:
                ma_gap = (ma_s - ma_l) / (ma_l + 1e-9)

            # ADX-like proxy: absolute % moves over period
            returns = price.pct_change().abs().rolling(self.adx_like_period).mean().iloc[-1]
            returns = float(returns or 0.0)

            # Heuristics:
            # high volatility if vol_idx >> atr/price or returns high
            price_now = float(price.iloc[-1])
            atr_norm = (atr / (price_now + 1e-9)) if price_now else 0.0

            high_vol = vol_idx > max(atr_norm * 2.0, 0.002) or returns > 0.01

            # trend if MA gap significant and momentum present
            trend_strength = abs(ma_gap) * 5.0 + (returns * 50.0)
            is_trend = abs(trend_strength) > 0.6 and abs(ma_gap) > 0.002

            # range if both MA close and vol low
            is_range = (not is_trend) and (vol_idx < atr_norm * 0.8)

            if high_vol:
                regime = "high_vol"
                score = min(1.0, max(0.5, (vol_idx / (atr_norm + 1e-9)) if atr_norm>0 else 0.7))
            elif is_trend:
                regime = "trend"
                score = min(1.0, float(abs(trend_strength)))
            elif is_range:
                regime = "range"
                score = 0.6
            else:
                regime = "unknown"
                score = 0.0

            meta = {"atr":atr, "atr_norm":atr_norm, "vol_index":vol_idx, "ma_gap":ma_gap, "returns":returns}
            return {"regime":regime, "score":float(round(score,3)), "meta":meta}
        except Exception:
            return {"regime":"unknown","score":0.0,"meta":{}}