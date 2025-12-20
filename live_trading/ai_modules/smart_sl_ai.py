import numpy as np

class SmartSLAI:
    """
    Dynamic stoploss generator (ATR + structure).
    """

    def __init__(self, atr_period=14, atr_mult=1.8):
        self.atr_period = atr_period
        self.atr_mult = atr_mult

    def compute_atr(self, df):
        high = df['high']
        low = df['low']
        close = df['close']

        tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
        atr = tr.rolling(self.atr_period).mean()
        return atr.iloc[-1]

    def get_structure_sl(self, df, direction):
        if direction == "BUY":
            return df['low'].tail(5).min()
        else:
            return df['high'].tail(5).max()

    def generate_sl(self, df, direction):
        atr = self.compute_atr(df)
        structure_sl = self.get_structure_sl(df, direction)
        price = df['close'].iloc[-1]

        if direction == "BUY":
            sl = min(price - atr * self.atr_mult, structure_sl)
        else:
            sl = max(price + atr * self.atr_mult, structure_sl)

        return float(sl)
