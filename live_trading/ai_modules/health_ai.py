# logic/health_ai.py
"""
HealthAI - monitor model & system health (drift detection, signal quality).
API:
  h = HealthAI(window=100)
  h.register_result(tag, was_correct_bool, confidence, pnl)
  summary = h.summary()
  flagged = h.check_drift()
"""

import time
from collections import defaultdict, deque
import math

class HealthAI:
    def __init__(self, window=200, drift_threshold=0.15):
        # window: how many most recent trades to consider
        self.window = int(window)
        self.drift_threshold = float(drift_threshold)
        # stores per-tag deque of (timestamp, correct(bool), confidence, pnl)
        self.data = defaultdict(lambda: deque(maxlen=self.window))
        self.last_summary = {}

    def register_result(self, tag: str, correct: bool, confidence: float, pnl: float, timestamp=None):
        ts = timestamp or time.time()
        try:
            self.data[tag].append((ts, bool(correct), float(confidence), float(pnl)))
        except Exception:
            pass

    def _compute_stats(self, seq):
        n = len(seq)
        if n == 0:
            return {"trades":0,"winrate":None,"avg_conf":None,"avg_pnl":None}
        wins = sum(1 for t in seq if t[1])
        avg_conf = sum(t[2] for t in seq) / n
        avg_pnl = sum(t[3] for t in seq) / n
        return {"trades":n,"winrate":wins/n,"avg_conf":avg_conf,"avg_pnl":avg_pnl}

    def summary(self):
        res = {}
        for tag, deq in self.data.items():
            res[tag] = self._compute_stats(list(deq))
        self.last_summary = res
        return res

    def check_drift(self, min_trades=30):
        """
        Check whether any tag has drift (winrate significantly lower than 0.5 by threshold).
        returns dict of flagged tags -> reason
        """
        flagged = {}
        sm = self.summary()
        for tag, stat in sm.items():
            if stat["trades"] is None or stat["trades"] < min_trades:
                continue
            wr = stat["winrate"]
            if wr is None:
                continue
            # if winrate less than 0.5 - drift_threshold, flag
            if wr < 0.5 - self.drift_threshold:
                flagged[tag] = {"winrate":wr, "trades":stat["trades"], "reason":"low_winrate_drift"}
            # if avg confidence >> actual winrate (overconfident), flag
            avg_conf = stat["avg_conf"] or 0.0
            if avg_conf - wr > 0.35 and stat["trades"] >= min_trades:
                flagged[tag] = {"winrate":wr, "avg_conf":avg_conf, "trades":stat["trades"], "reason":"overconfident_model"}
        return flagged