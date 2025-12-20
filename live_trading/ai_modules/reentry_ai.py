import numpy as np
import pandas as pd


class ReEntrySmartAI:
    """
    Re-entry logic (configurable):
    - Detect bullish engulfing or strong rejection candle after a sweep
    - Detect BOS (Break of Structure)
    - Confirm with volume absorption
    - Returns a dict {reentry_buy, confidence, reason}
    """

    def __init__(self, min_confidence: float = 0.5, weights: dict = None):
        """
        Args:
            min_confidence: threshold (0..1) to consider re-entry valid
            weights: dict of weights for signals: keys 'engulfing','rejection','volume_confirm','bos'
        """
        self.min_confidence = float(min_confidence)
        # default equal weights
        self.weights = weights or {'engulfing': 1.0, 'rejection': 1.0, 'volume_confirm': 1.0, 'bos': 1.0}

    def detect(self, df, lookback=25):
        if df is None:
            return {"reentry_buy": False, "confidence": 0.0, "reason": "no_data"}

        # accept both DataFrame and dict-of-dfs
        if isinstance(df, dict) and 'H1' in df:
            df = df['H1']

        if not hasattr(df, 'iloc'):
            return {"reentry_buy": False, "confidence": 0.0, "reason": "bad_df"}

        if len(df) < lookback + 5:
            return {"reentry_buy": False, "confidence": 0.0, "reason": "too_short"}

        recent = df.iloc[-lookback:].copy()

        open_ = recent['open'].values
        high = recent['high'].values
        low = recent['low'].values
        close = recent['close'].values
        # support both 'tick_volume' and 'volume'
        if 'tick_volume' in recent.columns:
            volume = recent['tick_volume'].values
        else:
            volume = recent['volume'].values if 'volume' in recent.columns else np.zeros(len(recent))

        # -----------------------------------------
        # 1. Detect prior sweep (false-breakdown)
        # -----------------------------------------
        prev_low = np.min(low[:-3]) if len(low) > 3 else np.min(low)
        sweep = (low[-3] < prev_low) and (close[-3] > prev_low)

        # If no sweep → no reentry needed
        if not sweep:
            return {"reentry_buy": False, "confidence": 0.0, "reason": "no_sweep"}

        # -----------------------------------------
        # 2. Detect bullish engulfing after sweep
        # -----------------------------------------
        engulf = (
            close[-1] > open_[-1] and  # bullish candle
            close[-1] > open_[-2] and  # closes above prior open
            close[-2] < open_[-2]      # previous candle was bearish
        )

        # -----------------------------------------
        # 3. Detect strong bullish rejection candle
        # -----------------------------------------
        full_range = high[-1] - low[-1]
        body = close[-1] - open_[-1]
        lower_wick = open_[-1] - low[-1] if close[-1] >= open_[-1] else close[-1] - low[-1]

        rejection = (
            full_range > 0 and
            lower_wick > full_range * 0.4 and
            body > full_range * 0.2
        )

        # -----------------------------------------
        # 4. Volume absorption confirmation
        # -----------------------------------------
        vol_mean = np.mean(volume[:-1]) if len(volume) > 1 else 0
        vol_confirm = (volume[-1] > vol_mean * 1.3) if vol_mean > 0 else False

        # -----------------------------------------
        # 5. Break of Structure (BOS)
        # -----------------------------------------
        last_highs = high[-5:]
        bos = close[-1] > np.max(last_highs[:-1]) if len(last_highs) > 1 else False

        # -----------------------------------------
        # Combine signals with configurable weights
        # -----------------------------------------
        sig_flags = {
            'engulfing': bool(engulf),
            'rejection': bool(rejection),
            'volume_confirm': bool(vol_confirm),
            'bos': bool(bos)
        }

        total_weight = sum(self.weights.get(k, 0.0) for k in sig_flags.keys())
        if total_weight <= 0:
            # avoid division by zero
            total_weight = 1.0

        weighted_score = 0.0
        reasons = []
        for k, flag in sig_flags.items():
            if flag:
                w = float(self.weights.get(k, 1.0))
                weighted_score += w
                reasons.append(k)

        confidence = float(weighted_score) / float(total_weight)

        if confidence >= self.min_confidence:
            return {
                "reentry_buy": True,
                "confidence": float(confidence),
                "reason": ", ".join(reasons)
            }

        return {"reentry_buy": False, "confidence": float(confidence), "reason": "low_conf"}
