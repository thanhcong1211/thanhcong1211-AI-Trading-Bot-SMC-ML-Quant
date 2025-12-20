# logic/pattern_sltp.py
import math

class PatternSLTPAdvisor:
    """
    Suggest SL and TP based on pattern type and volatility multiplier.
    API:
      advise(pattern:str, side:str, recent_levels:dict, atr:float, price:float, base_rr=1.5)
      returns {"sl":..., "tp":..., "rr":...}
    recent_levels: may include {'last_swing_high':..., 'last_swing_low':...}
    """

    def __init__(self, atr_multiplier_map=None, rr_map=None, min_sl_pts=0.0001):
        # default multipliers for pattern types
        self.atr_multiplier_map = atr_multiplier_map or {
            "double_top": 1.2, "double_bottom":1.2,
            "head_and_shoulders":1.5, "inverse_head_and_shoulders":1.5,
            "flag":1.0, "pennant":1.0, "triangle":1.1,
            "engulfing": 0.9, "pinbar": 0.8, "hammer": 0.8
        }
        self.rr_map = rr_map or {
            "default": 1.5
        }
        self.min_sl_pts = min_sl_pts

    def advise(self, pattern, side, recent_levels, atr, price, base_rr=None):
        base_rr = base_rr or self.rr_map.get("default",1.5)
        mult = self.atr_multiplier_map.get(pattern, 1.2)
        sl_distance = max(self.min_sl_pts, atr * mult)
        if side.lower() in ("buy","long"):
            sl = price - sl_distance
            # TP: base_rr * sl_distance (dynamic)
            tp = price + base_rr * sl_distance
            # if recent_levels has target high, prefer that if it's closer/further sensibly
            target_high = recent_levels.get("target_high")
            if target_high and target_high > price and (target_high - price) < (base_rr * sl_distance * 2):
                tp = target_high
        else:
            sl = price + sl_distance
            tp = price - base_rr * sl_distance
            target_low = recent_levels.get("target_low")
            if target_low and target_low < price and (price - target_low) < (base_rr * sl_distance * 2):
                tp = target_low
        rr = abs((tp - price) / (price - sl)) if sl != price else base_rr
        return {"sl":float(sl), "tp":float(tp), "rr":float(rr)}