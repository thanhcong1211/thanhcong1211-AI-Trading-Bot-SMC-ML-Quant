# logic/fusion_ai_v4.py
"""
FusionAI v4 - Hierarchical / priority-based fusion with veto rules.

API:
  fusion = FusionAIv4(weights=None, thresholds=None, priority=None)
  decision = fusion.fuse(signals, context=None)
  where signals is dict with keys from your modules e.g.
   {
     "trend": ("buy", 0.8),
     "structure": ("buy", 0.7),
     "liquidity": ("buy", 0.6),
     "sentiment": ("bull", 0.2),
     "volatility": {"vol_index": 0.02, "regime":"normal"},
     "risk_block": (False,"")
     ...
   }
Returns:
  {"side":"buy|sell|none","score":0..1,"reasons":[...],"meta":{...},"blocked":bool,"blocked_reason":str}
"""

from typing import Dict, Any
import logging

# Module logger for FusionAI
logger = logging.getLogger(__name__)

class FusionAIv4:
    def __init__(self, weights: Dict[str,float]=None, thresholds: Dict[str,float]=None, priority: list=None):
        # default weights used when combining sibling signals (if needed)
        self.weights = weights or {
            "structure": 0.30,
            "trend": 0.25,
            "liquidity": 0.20,
            "reversal": 0.10,
            "candle": 0.075,
            "sentiment": 0.025
        }
        # minimum score to consider module as strong
        self.thresholds = thresholds or {
            "strong": 0.7,
            "weak": 0.4
        }
        # priority order (higher priority earlier)
        self.priority = priority or ["structure","trend","liquidity","reversal","candle","sentiment"]

        # veto modules (if their output says block) - can be set externally
        self.veto_keys = ["volatility","risk_block","session"]

    def _normalize_side(self, s):
        if not s: return "none"
        s = str(s).lower()
        if s in ("buy","long","bull","1","+1"):
            return "buy"
        if s in ("sell","short","bear","-1"):
            return "sell"
        return "none"

    def fuse(self, signals: Dict[str,Any], context: Dict[str,Any]=None):
        """
        Main fuse method. signals: dict.
        """
        context = context or {}
        reasons = []
        meta = {"component_scores":{}}

        # 1) quick veto checks: volatility / risk / session
        # volatility veto: if vol_index high -> block
        vol = signals.get("volatility") or signals.get("vol_ai") or {}
        if isinstance(vol, dict):
            vol_idx = float(vol.get("vol_index", 0.0))
            regime = vol.get("regime","unknown")
            if regime == "high_vol" or vol_idx > context.get("volatility_block_threshold", 0.05):
                return {"side":"none","score":0.0,"reasons":["veto_volatility"],"meta":{"volatility":vol},"blocked":True,"blocked_reason":"high_volatility"}

        # risk veto
        rb = signals.get("risk_block")
        if rb:
            blocked_flag = False
            if isinstance(rb, (list,tuple)) and len(rb)>=1:
                blocked_flag = bool(rb[0])
                blocked_reason = rb[1] if len(rb)>1 else "risk_block"
            elif isinstance(rb, dict):
                blocked_flag = bool(rb.get("blocked",False))
                blocked_reason = rb.get("reason","risk_block")
            else:
                blocked_flag = False
            if blocked_flag:
                return {"side":"none","score":0.0,"reasons":["veto_risk"],"meta":{"risk_block":rb},"blocked":True,"blocked_reason":str(blocked_reason)}

        # session veto
        sess = signals.get("session")
        if isinstance(sess, dict):
            if sess.get("mode","full") == "no_trade" or sess.get("allowed") is False:
                return {"side":"none","score":0.0,"reasons":["veto_session"],"meta":{"session":sess},"blocked":True,"blocked_reason":"session_block"}

        # 2) accumulate according to priority and weights
        accum = {"buy":0.0, "sell":0.0}
        total_weight = 0.0
        # We'll process priority list first (if present) so that high-priority modules get considered earlier
        for key in self.priority:
            val = signals.get(key)
            if not val:
                continue
            score = 0.0
            side = "none"
            # val may be tuple (side,score) or dict
            if isinstance(val, (list,tuple)) and len(val)>=2:
                side = self._normalize_side(val[0])
                try:
                    score = float(val[1])
                except Exception:
                    score = 0.0
            elif isinstance(val, dict):
                # try common fields
                side = self._normalize_side(val.get("side") or val.get("signal") or val.get("direction") or val.get("sentiment"))
                score = float(val.get("score", val.get("strength",0.0) or 0.0))
            else:
                side = self._normalize_side(val)
                score = 0.0

            w = float(self.weights.get(key, 0.05))
            meta["component_scores"][key] = {"side":side,"raw_score":score,"weight":w}
            if side in ("buy","sell"):
                accum[side] += score * w
                total_weight += w

        # 3) normalize and decide
        if total_weight <= 0:
            return {"side":"none","score":0.0,"reasons":["no_inputs"],"meta":meta,"blocked":False,"blocked_reason":None}

        buy_score = accum["buy"] / total_weight
        sell_score = accum["sell"] / total_weight

        final_side = "none"
        final_score = 0.0
        if buy_score > sell_score and buy_score >= self.thresholds["weak"]:
            final_side = "buy"
            final_score = buy_score
        elif sell_score > buy_score and sell_score >= self.thresholds["weak"]:
            final_side = "sell"
            final_score = sell_score
        else:
            final_side = "none"
            final_score = max(buy_score, sell_score)

        # 4) apply rule-based priority overrides:
        # If structure strongly opposes trend, respect structure (priority rule)
        st = signals.get("structure")
        tr = signals.get("trend")
        if st and tr:
            st_side = self._normalize_side(st[0]) if isinstance(st, (list,tuple)) else (st.get("side") if isinstance(st, dict) else None)
            st_score = float(st[1]) if isinstance(st, (list,tuple)) and len(st)>1 else (st.get("score",0.0) if isinstance(st, dict) else 0.0)
            tr_side = self._normalize_side(tr[0]) if isinstance(tr, (list,tuple)) else (tr.get("side") if isinstance(tr, dict) else None)
            tr_score = float(tr[1]) if isinstance(tr, (list,tuple)) and len(tr)>1 else (tr.get("score",0.0) if isinstance(tr, dict) else 0.0)
            # if structure strong and contradicts final_side, override
            if st_side in ("buy","sell") and st_side != final_side and st_score >= self.thresholds["strong"]:
                final_side = st_side
                final_score = st_score
                reasons.append("override_structure_priority")

        # 5) reason logging
        if final_side == "none":
            reasons.append("no_clear_consensus")
        else:
            reasons.append(f"final_from_aggregate:{final_side}")

        # 6) return
        return {"side": final_side, "score": float(round(final_score,3)), "reasons": reasons, "meta": meta, "blocked": False, "blocked_reason": None}

    def final_decision(self, decision: str, df, crash_detector=None):
        """Final decision with CrashDetector MACD VETO
        
        Args:
            decision: "buy", "sell", or None
            df: DataFrame for MACD veto analysis
            crash_detector: CrashDetector instance (optional)
        
        Returns:
            str: Final decision after veto ("buy", "sell", or None)
        """
        if decision is None or decision not in ("buy", "sell"):
            return decision
        
        if crash_detector is None:
            return decision
        
        try:
            veto = crash_detector.macd_veto(df)
            
            if decision == 'buy' and veto['veto_buy']:
                logger.info(f"🚫 BUY VETO: {veto['reason']} (score: {veto['score']:.2f})")
                return None
            
            if decision == 'sell' and veto['veto_sell']:
                logger.info(f"🚫 SELL VETO: {veto['reason']} (score: {veto['score']:.2f})")
                return None
            
            return decision
        
        except Exception as e:
            logger.warning(f"⚠️ final_decision veto failed: {e}")
            return decision