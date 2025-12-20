class RiskGuardianAI:
    """
    Daily loss protection + lot scaling + spread filter.
    """

    def __init__(self, max_daily_loss=0.04, max_consec_loss=3, max_spread=25):
        self.max_daily_loss = max_daily_loss
        self.max_consec_loss = max_consec_loss
        self.max_spread = max_spread
        self.daily_start_balance = None
        self.consec_losses = 0

    def update_day_balance(self, balance):
        if self.daily_start_balance is None:
            self.daily_start_balance = balance

    def check_daily_loss(self, balance):
        drop = (self.daily_start_balance - balance) / self.daily_start_balance
        return drop < self.max_daily_loss

    def update_consecutive(self, last_result):
        if last_result < 0:
            self.consec_losses += 1
        else:
            self.consec_losses = 0

    def can_trade(self, spread, balance):
        if spread > self.max_spread:
            return False
        if not self.check_daily_loss(balance):
            return False
        if self.consec_losses >= self.max_consec_loss:
            return False
        return True
