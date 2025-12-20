# logic/explain_ai.py
"""
ExplainAI - produce human-readable explanation for decisions and log them.
API:
  e = ExplainAI(log_path="live_trading/logs/explain.log")
  text = e.explain(decision, signals)
  e.log(decision, signals)
"""

import json
import os
import datetime

class ExplainAI:
    def __init__(self, log_path="live_trading/logs/explain.log"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)

    def explain(self, decision: dict, signals: dict) -> str:
        """
        Build a readable explanation string from decision and signals.
        """
        try:
            lines = []
            ts = datetime.datetime.utcnow().isoformat() + "Z"
            lines.append(f"[{ts}] Decision: {decision.get('side','none').upper()} score={decision.get('score',0.0)} blocked={decision.get('blocked',False)}")
            reasons = decision.get("reasons") or []
            if reasons:
                lines.append("  Reasons: " + ", ".join(map(str,reasons)))
            # Summarize key modules (structure, trend, liquidity, volatility, risk)
            keys_of_interest = ["structure","trend","liquidity","reversal","candle","sentiment","volatility","risk_block","session"]
            for k in keys_of_interest:
                v = signals.get(k)
                if v is None:
                    continue
                if isinstance(v, (list,tuple)) and len(v)>=2:
                    lines.append(f"  {k.upper():12}: {v[0]} (score={v[1]})")
                elif isinstance(v, dict):
                    # friendly formatting
                    s = v.get("signal") or v.get("side") or v.get("sentiment") or str(v)
                    score = v.get("strength", v.get("score","-"))
                    lines.append(f"  {k.upper():12}: {s} (score={score})")
                else:
                    lines.append(f"  {k.upper():12}: {v}")
            # meta short
            meta = decision.get("meta",{})
            if meta:
                lines.append("  Meta keys: " + ", ".join(list(meta.get("component_scores",{}).keys())[:8]))
            return "\n".join(lines)
        except Exception as e:
            return f"ExplainAI error: {e}"

    def log(self, decision: dict, signals: dict):
        try:
            txt = self.explain(decision, signals)
            with open(self.log_path, "a", encoding="utf8") as f:
                f.write(txt + "\n\n")
        except Exception:
            pass