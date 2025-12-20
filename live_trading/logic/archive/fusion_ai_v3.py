class FusionAIv3:
    """
    FusionAI v3.0
    Inputs (signals dict) expected keys:
      - trend: (side, score)
      - sweep: (side, strength)  # strength 0..1
      - structure: (side, score)
      - reversal: (side, score)
      - candle: (side, score)
      - volatility: dict with 'regime' and 'recommendation'
      - risk_block: (bool, reason) optional
    Returns dict: {'side','score','reasons','meta'}
    """

    def __init__(self, weights=None, threshold=0.7):
        self.weights = weights or {
            "trend": 0.30,
            "sweep": 0.25,
            "structure": 0.20,
            "reversal": 0.10,
            "candle": 0.05,
        }
        self.threshold = threshold

    def fuse(self, signals):
        risk_block = signals.get("risk_block")
        if isinstance(risk_block, tuple):
            blocked, reason = risk_block
            if blocked:
                return {"side": "none", "score": 0.0, "reasons": ["risk_block:"+str(reason)], "meta": signals}

        vol = signals.get("volatility", {})
        if isinstance(vol, dict):
            if vol.get("recommendation") == "avoid":
                return {"side": "none", "score": 0.0, "reasons": ["volatility:avoid"], "meta": signals}

        buy_score = 0.0
        sell_score = 0.0
        reasons = []

        def read(sig):
            if sig is None:
                return ("none", 0.0)
            if isinstance(sig, (tuple, list)):
                return (sig[0], float(sig[1] or 0.0))
            if isinstance(sig, dict):
                return (sig.get("side","none"), float(sig.get("score",0.0)))
            return ("none",0.0)

        for key in ["trend","sweep","structure","reversal","candle"]:
            weight = self.weights.get(key, 0.0)
            side, score = read(signals.get(key))
            if side == "buy":
                buy_score += score * weight
                reasons.append(f"{key}=buy({score:.2f})")
            elif side == "sell":
                sell_score += score * weight
                reasons.append(f"{key}=sell({score:.2f})")
            else:
                reasons.append(f"{key}=none")

        max_possible = sum(self.weights.values()) or 1.0
        buy_score_norm = buy_score / max_possible
        sell_score_norm = sell_score / max_possible

        if buy_score_norm >= self.threshold and buy_score_norm > sell_score_norm:
            return {"side":"buy","score":float(round(buy_score_norm,3)),"reasons":reasons,"meta":signals}
        if sell_score_norm >= self.threshold and sell_score_norm > buy_score_norm:
            return {"side":"sell","score":float(round(sell_score_norm,3)),"reasons":reasons,"meta":signals}

        return {"side":"none","score":float(round(max(buy_score_norm, sell_score_norm),3)),"reasons":reasons,"meta":signals}
