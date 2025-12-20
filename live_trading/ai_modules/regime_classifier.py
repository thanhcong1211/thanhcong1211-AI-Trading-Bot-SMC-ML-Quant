import numpy as np

class RegimeClassifierAI:
    """
    Market regime classifier.
    """

    def __init__(self):
        pass

    def classify(self, df):
        closes = df['close']
        ret = np.diff(closes)
        vol = np.std(ret)
        atr = (df['high'] - df['low']).rolling(14).mean().iloc[-1]

        # Trend = price directional + low noise
        if vol < atr * 0.7:
            if closes.iloc[-1] > closes.iloc[-10]:
                return "UPTREND"
            if closes.iloc[-1] < closes.iloc[-10]:
                return "DOWNTREND"

        # Range = volatility small + no direction
        if vol < atr * 0.5:
            return "RANGE"

        # Momentum = volatility high + direction strong
        if vol > atr * 1.2:
            return "MOMENTUM"

        return "CHAOS"
