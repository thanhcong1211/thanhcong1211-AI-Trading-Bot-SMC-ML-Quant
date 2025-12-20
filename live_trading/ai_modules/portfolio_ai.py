# logic/portfolio_ai.py
"""
PortfolioAI - upgrade of ExposureAI to full portfolio exposure controls.

API:
  p = PortfolioAI(config)
  ok, reason = p.allowed_open(symbol, side, notional)
  p.register_open(...)
  p.register_close(...)
  stats = p.get_stats()
"""

from collections import defaultdict
import math
import os
import json

class PortfolioAI:
    def __init__(self, max_total_notional=200000.0, max_directional_notional=100000.0, max_open_positions=10, correlation_map=None, persist_path=None):
        self.max_total_notional = float(max_total_notional)
        self.max_directional_notional = float(max_directional_notional)
        self.max_open_positions = int(max_open_positions)
        self.correlation_map = correlation_map or {}  # dict[(a,b)] = corr
        self.persist_path = persist_path
        self.open_notional = defaultdict(float)  # symbol -> signed notional
        self.open_positions = {}  # ticket -> {symbol,side,notional}
        self.total_notional = 0.0

    def _corr(self, a, b):
        return float(self.correlation_map.get((a,b)) or self.correlation_map.get((b,a)) or 0.0)

    def allowed_open(self, symbol, side, notional):
        """
        Check whether opening a position is allowed.
        notional = price * lot or precomputed wallet currency exposure
        Returns (bool, reason)
        """
        sign = 1 if str(side).lower() in ("buy","long") else -1
        new_total = self.total_notional + abs(notional)
        if new_total > self.max_total_notional:
            return False, "max_total_notional_exceeded"
        # directional check
        # compute directional totals if opened
        temp_open = dict(self.open_notional)
        temp_open[symbol] = temp_open.get(symbol,0.0) + sign * float(notional)
        buy = sum(v for v in temp_open.values() if v>0)
        sell = -sum(v for v in temp_open.values() if v<0)
        if buy > self.max_directional_notional or sell > self.max_directional_notional:
            return False, "max_directional_exceeded"
        # correlated exposure
        for s_existing, net in self.open_notional.items():
            corr = self._corr(symbol, s_existing)
            if corr > 0.85:
                combined = abs(temp_open.get(symbol,0.0)) + abs(net)
                if combined > self.max_directional_notional * 0.8:
                    return False, f"correlated_exposure_{symbol}_{s_existing}"
        # max positions
        if len(self.open_positions) >= self.max_open_positions:
            return False, "max_open_positions_exceeded"
        return True, "ok"

    def register_open(self, ticket, symbol, side, notional):
        sign = 1 if str(side).lower() in ("buy","long") else -1
        self.open_notional[symbol] += sign * float(notional)
        self.open_positions[ticket] = {"symbol":symbol,"side":side,"notional":float(notional)}
        self.total_notional += abs(notional)
        self._persist_state()

    def register_close(self, ticket):
        pos = self.open_positions.pop(ticket, None)
        if not pos:
            return
        sym = pos["symbol"]; notional = pos["notional"]; side = pos["side"]
        sign = 1 if str(side).lower() in ("buy","long") else -1
        self.open_notional[sym] -= sign * float(notional)
        self.total_notional = max(0.0, self.total_notional - abs(notional))
        self._persist_state()

    def get_stats(self):
        return {
            "open_count": len(self.open_positions),
            "total_notional": float(self.total_notional),
            "directional": {
                "buy": sum(v for v in self.open_notional.values() if v>0),
                "sell": -sum(v for v in self.open_notional.values() if v<0)
            }
        }

    def _persist_state(self):
        if not self.persist_path:
            return
        try:
            os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
            with open(self.persist_path, "w", encoding="utf8") as f:
                json.dump({"open_notional":self.open_notional, "open_positions":self.open_positions, "total_notional":self.total_notional}, f, default=str)
        except Exception:
            pass