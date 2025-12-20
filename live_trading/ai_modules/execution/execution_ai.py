# logic/execution_ai.py
import time

class ExecutionAI:
    """
    ExecutionAI monitors spreads, session and slippage expectations.
    Usage:
        ex = ExecutionAI(spread_threshold=0.0004, slippage_pct=0.0006)
        ok, reason = ex.allowed_to_execute(current_spread, avg_slippage, session)
    """

    def __init__(self, spread_threshold=0.0004, slippage_threshold_pct=0.0006, disable_hours=None):
        # spread_threshold: absolute price units (symbol-specific; for FX ~0.0004 for 4 pips)
        self.spread_threshold = spread_threshold
        self.slippage_threshold_pct = slippage_threshold_pct
        # disable_hours: list of hour ranges to avoid e.g. [(23,1)] means 23:00-01:00
        self.disable_hours = disable_hours or []
        self.last_warning = 0

    def _in_disabled_hours(self, now_ts):
        if not self.disable_hours:
            return False
        t = time.gmtime(now_ts)
        hour = t.tm_hour
        for rng in self.disable_hours:
            a, b = rng
            if a <= b:
                if a <= hour < b:
                    return True
            else:
                # wrap midnight
                if hour >= a or hour < b:
                    return True
        return False

    def allowed_to_execute(self, current_spread, avg_slippage_pct, now_ts=None):
        """
        current_spread: absolute price units (ask-bid)
        avg_slippage_pct: recent average slippage in price percent of price
        returns (bool, reason, mode) where mode in ('market','limit','no_trade')
        """
        now_ts = now_ts or time.time()
        if self._in_disabled_hours(now_ts):
            return False, "disabled_hours", "no_trade"

        # spread check
        if current_spread is not None and current_spread > self.spread_threshold:
            return False, f"spread_too_high:{current_spread}", "no_trade"

        # slippage check
        if avg_slippage_pct is not None and avg_slippage_pct > self.slippage_threshold_pct:
            # recommend limit order if minor slippage
            if avg_slippage_pct < self.slippage_threshold_pct * 2.0:
                return True, "use_limit_recommended", "limit"
            else:
                return False, f"slippage_too_high:{avg_slippage_pct}", "no_trade"

        return True, "ok", "market"