# logic/adaptive_learner.py
import json
import os
from collections import defaultdict
from typing import Dict

class AdaptiveLearner:
    """
    Tracks wins/losses by tag (pattern name / strategy id) and suggests weight adjustments.
    API:
      - register_result(tag:str, profit:float)
      - get_stats(tag) -> dict
      - recommend_weight(tag, base_weight) -> adjusted_weight
    """

    def __init__(self, persist_path="live_trading/state/adaptive_state.json", min_samples=20):
        self.persist_path = persist_path
        self.min_samples = min_samples
        self.stats = defaultdict(lambda: {"trades":0,"wins":0,"losses":0,"pnl":0.0})
        self._load()

    def _load(self):
        try:
            if os.path.exists(self.persist_path):
                with open(self.persist_path,"r") as f:
                    j = json.load(f)
                for k,v in j.items():
                    self.stats[k] = v
        except Exception:
            pass

    def _save(self):
        try:
            d = {k:v for k,v in self.stats.items()}
            os.makedirs(os.path.dirname(self.persist_path) or ".", exist_ok=True)
            with open(self.persist_path,"w") as f:
                json.dump(d,f)
        except Exception:
            pass

    def register_result(self, tag: str, profit: float):
        s = self.stats[tag]
        s["trades"] += 1
        s["pnl"] = s.get("pnl",0.0) + profit
        if profit > 0:
            s["wins"] += 1
        else:
            s["losses"] += 1
        self.stats[tag] = s
        self._save()

    def get_stats(self, tag: str):
        s = self.stats.get(tag, {"trades":0,"wins":0,"losses":0,"pnl":0.0})
        s["winrate"] = (s["wins"] / s["trades"]) if s["trades"]>0 else None
        return s

    def recommend_weight(self, tag: str, base_weight: float):
        s = self.stats.get(tag)
        if not s or s.get("trades",0) < self.min_samples:
            return base_weight
        winrate = s["wins"]/s["trades"] if s["trades"] else 0.0
        # simple rule: scale weight linearly 0.5x..1.5x based on winrate vs 0.5 baseline
        factor = 1.0
        if winrate < 0.4:
            factor = max(0.2, 0.8 * (winrate/0.4))
        elif winrate > 0.6:
            factor = 1.0 + min(0.5, (winrate - 0.6) * 1.5)
        return float(base_weight * factor)