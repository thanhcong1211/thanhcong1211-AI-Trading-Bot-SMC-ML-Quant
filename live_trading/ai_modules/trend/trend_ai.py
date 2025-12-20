import numpy as np
import pandas as pd

class TrendAI:
    """
    TrendAI: multi-timeframe trend detector and scoring.
    Usage:
        ta = TrendAI()
        out = ta.analyze({"H4": df_h4, "H1": df_h1, "M15": df_m15})
        side, score = out["side"], out["score"]
    """

    def __init__(self,
                 ma_short=20,
                 ma_long=50,
                 slope_window=10,
                 min_strength=0.2):
        self.ma_short = ma_short
        self.ma_long = ma_long
        self.slope_window = slope_window
        self.min_strength = min_strength

    def _slope(self, series):
        x = np.arange(len(series))
        if len(series) < 2:
            return 0.0
        coef = np.polyfit(x, series, 1)
        return coef[0]

    def _single_tf_trend(self, df):
        out = {'side': 'none', 'strength': 0.0}
        if df is None or len(df) < max(self.ma_long, self.slope_window) + 2:
            return out
        close = df['close'].astype(float)
        ma_s = close.rolling(self.ma_short).mean().iloc[-1]
        ma_l = close.rolling(self.ma_long).mean().iloc[-1]
        ma_short_series = close.rolling(self.ma_short).mean().dropna()
        slope = self._slope(ma_short_series[-self.slope_window:]) if len(ma_short_series) >= self.slope_window else 0.0
        slope_norm = slope / (close.iloc[-1] + 1e-9)
        ma_gap = (ma_s - ma_l) / (ma_l + 1e-9)
        strength = min(1.0, max(0.0, abs(ma_gap) * 2.0 + abs(slope_norm) * 100.0))
        if ma_s > ma_l and slope_norm > 0:
            out['side'] = 'buy'
            out['strength'] = strength
        elif ma_s < ma_l and slope_norm < 0:
            out['side'] = 'sell'
            out['strength'] = strength
        return out

    def analyze(self, df_multi):
        if not isinstance(df_multi, dict):
            df_multi = {"H1": df_multi}

        tf_weights = {"H4": 0.5, "H1": 0.3, "M15": 0.2}
        total_buy = 0.0
        total_sell = 0.0
        sum_weights = 0.0
        reasons = []
        for tf, df in df_multi.items():
            weight = tf_weights.get(tf, 0.1)
            r = self._single_tf_trend(df)
            sum_weights += weight
            reasons.append(f"{tf}:{r['side']}({r['strength']:.2f})")
            if r['side'] == 'buy':
                total_buy += r['strength'] * weight
            elif r['side'] == 'sell':
                total_sell += r['strength'] * weight

        if sum_weights == 0:
            score = 0.0
            side = 'none'
        else:
            buy_score = total_buy / sum_weights
            sell_score = total_sell / sum_weights
            if buy_score > sell_score and buy_score >= self.min_strength:
                side = 'buy'
                score = buy_score
            elif sell_score > buy_score and sell_score >= self.min_strength:
                side = 'sell'
                score = sell_score
            else:
                side = 'none'
                score = max(buy_score, sell_score)

        return {"side": side, "score": float(round(score, 3)), "reason": ";".join(reasons)}
