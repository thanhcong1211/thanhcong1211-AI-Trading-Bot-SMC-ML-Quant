# logic/session_ai.py
"""
SessionAI - classify trading session and decide allowed modes.
Usage:
    s = SessionAI()
    out = s.evaluate(now_timestamp=None, symbol="EURUSD", recent_volatility=0.001)
    -> {"session":"London","allowed":True,"mode":"full|reduced|no_trade","reason":"...","meta":{...}}
"""

import time

class SessionAI:
    def __init__(self, tz_offset_hours=0):
        # tz_offset_hours: server tz offset relative to UTC (if needed)
        self.tz_offset = int(tz_offset_hours)
        # default rules (hours in UTC)
        # tuples (start_hour_inclusive, end_hour_exclusive, name, default_mode)
        self.session_map = [
            (0, 2, "Asia_Late", "reduced"),
            (2, 8, "Asia", "reduced"),
            (8, 16, "London", "full"),
            (16, 20, "NY", "full"),
            (20, 24, "NY_Late", "reduced")
        ]
        # news windows to block around high-impact events (minutes)
        self.news_block_minutes = 15

    def _hour_utc(self, now_ts):
        t = time.gmtime(now_ts)
        return t.tm_hour

    def evaluate(self, now_ts=None, symbol=None, recent_volatility=None, news_minutes_until=None):
        """
        now_ts: epoch seconds. If None, use time.time()
        recent_volatility: optional float (e.g. atr_norm or vol index)
        news_minutes_until: if upcoming high-impact news in X minutes (int)
        returns: dict: {"session","allowed","mode","reason","meta"}
        mode = "no_trade" | "reduced" | "full"
        """
        now_ts = now_ts or time.time()
        hour = self._hour_utc(now_ts)
        session = "unknown"
        mode = "full"
        for a,b,name,defmode in self.session_map:
            if a <= hour < b:
                session = name
                mode = defmode
                break
        # simple rules
        allowed = True
        reason = "ok"

        # block around news
        if news_minutes_until is not None and news_minutes_until >= 0 and news_minutes_until <= self.news_block_minutes:
            allowed = False
            mode = "no_trade"
            reason = f"news_block_{news_minutes_until}min"

        # if volatility very low, reduce trading power
        if recent_volatility is not None:
            if recent_volatility < 1e-6 and mode == "full":
                mode = "reduced"
                reason = "very_low_volatility"
            if recent_volatility is not None and recent_volatility > 0.05:
                # extremely volatile -> block
                allowed = False
                mode = "no_trade"
                reason = "extreme_volatility"

        return {"session": session, "allowed": allowed, "mode": mode, "reason": reason, "meta":{"hour_utc":hour}}