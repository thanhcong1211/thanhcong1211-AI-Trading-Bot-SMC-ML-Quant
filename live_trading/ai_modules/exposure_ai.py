# logic/exposure_ai.py
from collections import defaultdict
import math

class ExposureAI:
    """
    Track open positions and enforce exposure constraints.
    Methods:
      - register_open(symbol, side, lot, notional)
      - register_close(symbol, side, lot, notional)
      - allowed_open(symbol, side, lot, notional) -> (bool, reason)
    Config:
      - max_total_notional
      - max_directional_notional (per direction)
      - correlation_map: dict of tuple(symbolA,symbolB)->correlation (0..1)
    """

    def __init__(self, max_total_notional=100000.0, max_directional_notional=50000.0, correlation_map=None):
        self.max_total_notional = float(max_total_notional)
        self.max_directional_notional = float(max_directional_notional)
        self.correlation_map = correlation_map or {}
        self.open_notional = defaultdict(float)  # symbol -> net notional (buy positive, sell negative)
        self.total_notional = 0.0

    def register_open(self, symbol, side, notional):
        sign = 1 if side.lower() in ("buy","long") else -1
        self.open_notional[symbol] += sign * float(notional)
        self.total_notional += abs(notional)

    def register_close(self, symbol, side, notional):
        sign = 1 if side.lower() in ("buy","long") else -1
        self.open_notional[symbol] -= sign * float(notional)
        self.total_notional = max(0.0, self.total_notional - abs(notional))

    def _directional_net(self):
        buy = sum(v for v in self.open_notional.values() if v>0)
        sell = -sum(v for v in self.open_notional.values() if v<0)
        return buy, sell

    def allowed_open(self, symbol, side, notional):
        # estimate new totals
        sign = 1 if side.lower() in ("buy","long") else -1
        new_open = dict(self.open_notional)
        new_open[symbol] = new_open.get(symbol,0.0) + sign * float(notional)
        # total notional
        new_total = self.total_notional + abs(notional)
        if new_total > self.max_total_notional:
            return False, "max_total_notional_exceeded"
        # directional
        buy = sum(v for v in new_open.values() if v>0)
        sell = -sum(v for v in new_open.values() if v<0)
        if buy > self.max_directional_notional or sell > self.max_directional_notional:
            return False, "max_directional_exceeded"
        # correlation check: if opening symbol highly correlated with existing, limit combined
        for s_existing, net in self.open_notional.items():
            pair = (symbol, s_existing)
            corr = self.correlation_map.get(pair) or self.correlation_map.get((s_existing, symbol)) or 0.0
            if corr > 0.85:
                # simple rule: cap combined notional for strongly correlated pairs
                combined = abs(new_open.get(symbol,0.0)) + abs(net)
                if combined > (self.max_directional_notional * 0.8):
                    return False, f"correlated_exposure_{symbol}_{s_existing}"
        return True, "ok"