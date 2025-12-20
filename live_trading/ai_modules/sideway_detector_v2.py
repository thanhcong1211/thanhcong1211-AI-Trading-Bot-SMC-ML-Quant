import numpy as np

class SidewayDetectorV2:
    """
    Advanced sideways market detector.
    """

    def __init__(self, bb_period=20, bb_width=1.4):
        self.bb_period = bb_period
        self.bb_width = bb_width

    def bb_squeeze(self, df):
        mid = df['close'].rolling(self.bb_period).mean()
        std = df['close'].rolling(self.bb_period).std()

        upper = mid + std * self.bb_width
        lower = mid - std * self.bb_width

        width = upper - lower
        norm = width / df['close']

        return norm.iloc[-1] < 0.012  # <1.2% range

    def low_volume(self, df):
        vol = df['volume'].rolling(20).mean()
        return df['volume'].iloc[-1] < vol.iloc[-1] * 0.8

    def is_sideway(self, df):
        return self.bb_squeeze(df) and self.low_volume(df)
