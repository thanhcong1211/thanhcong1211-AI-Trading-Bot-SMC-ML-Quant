"""SMC SL/TP helpers

Simple helper to compute SL/TP anchored to sweep wick and nearby liquidity.
"""


class SMC_SLTP:
    def __init__(self, buffer=0.0003):
        self.buffer = buffer

    # -----------------------------------------------------
    # SL cho BUY theo SMC: đặt dưới đáy vừa bị quét
    # -----------------------------------------------------
    def sl_for_buy(self, sweep_low):
        return sweep_low - self.buffer

    # -----------------------------------------------------
    # SL cho SELL theo SMC: đặt trên đỉnh vừa bị quét
    # -----------------------------------------------------
    def sl_for_sell(self, sweep_high):
        return sweep_high + self.buffer

    # -----------------------------------------------------
    # TP cho BUY: tới liquidity trên
    # -----------------------------------------------------
    def tp_for_buy(self, recent_high):
        return recent_high

    # -----------------------------------------------------
    # TP cho SELL: tới liquidity dưới
    # -----------------------------------------------------
    def tp_for_sell(self, recent_low):
        return recent_low
