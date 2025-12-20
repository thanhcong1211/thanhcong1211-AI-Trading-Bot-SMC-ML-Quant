import numpy as np

class TrendMatrixAI:
    """
    Multi-timeframe trend filter.
    Returns BUY, SELL, or NONE based on EMA trend across multiple TFs.
    """

    def __init__(self, ema_fast=20, ema_slow=50):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    def compute_trend(self, df):
        if len(df) < self.ema_slow:
            return "NONE"

        ema_fast = df['close'].ewm(span=self.ema_fast).mean().iloc[-1]
        ema_slow = df['close'].ewm(span=self.ema_slow).mean().iloc[-1]

        if ema_fast > ema_slow:
            return "UP"
        if ema_fast < ema_slow:
            return "DOWN"
        return "FLAT"

    def analyze(self, m5, m15, h1, h4):
        """
        Input: 4 DataFrames
        Output: BUY / SELL / NONE
        """

        t5 = self.compute_trend(m5)
        t15 = self.compute_trend(m15)
        t1 = self.compute_trend(h1)
        t4 = self.compute_trend(h4)

        trends = [t5, t15, t1, t4]

        if trends.count("UP") >= 3:
            return "BUY"
        if trends.count("DOWN") >= 3:
            return "SELL"
        return "NONE"
