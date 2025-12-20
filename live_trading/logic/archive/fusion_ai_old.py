"""FusionAI - weight-based signal fusion

Lightweight fusion module to combine multiple sub-signals into a final
decision (buy/sell/none) using configurable weights.
"""


class FusionAI:
    def __init__(self):
        self.weights = {
            "trend": 0.35,
            "sweep": 0.30,
            "structure": 0.20,
            "reversal": 0.10,
            "candle": 0.05,
        }

    def fuse(self, signals):
        """
        signals = {
            "trend": ("buy", score),
            "sweep": ("buy", score),
            "structure": ("sell", score),
            "reversal": ("buy", score),
            "candle": ("buy", score),
        }
        """

        buy_score = 0
        sell_score = 0

        for k, (side, score) in (signals or {}).items():
            weight = self.weights.get(k, 0)

            if side == "buy":
                try:
                    buy_score += float(score) * float(weight)
                except Exception:
                    pass
            elif side == "sell":
                try:
                    sell_score += float(score) * float(weight)
                except Exception:
                    pass

        # Decision thresholds
        if buy_score >= 0.7:
            return "buy", buy_score

        if sell_score >= 0.7:
            return "sell", sell_score

        return "none", max(buy_score, sell_score)
