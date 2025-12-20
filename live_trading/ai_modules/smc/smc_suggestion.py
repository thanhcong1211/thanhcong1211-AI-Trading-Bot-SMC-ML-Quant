# smc_suggestion.py
"""
Scoring & Suggestion:
- score candidates, check session/volatility filters, and produce final suggestion
"""
from typing import List, Dict
from .smc_filters import is_in_killzone, atr as calc_atr
import pandas as pd

def score_candidate(candidate: dict, dfs: dict) -> float:
    """
    Simple scoring:
    - base 0.4
    - +0.3 if HTF trend aligns (H1 slope same direction)
    - +0.2 if ATR small (stable) relative to SL distance
    - +0.1 if M5 momentum aligns (close > ema_short for buy)
    """
    score = 0.4
    m5 = dfs.get('M5')
    h1 = dfs.get('H1')
    if h1 is not None and len(h1) > 0:
        # slope
        ema_long = h1['close'].ewm(span=50).mean().iloc[-1]
        ema_short = h1['close'].ewm(span=20).mean().iloc[-1]
        if candidate['side'] == 'buy' and ema_short > ema_long:
            score += 0.3
        if candidate['side'] == 'sell' and ema_short < ema_long:
            score += 0.3
    if m5 is not None and len(m5) > 0:
        a = calc_atr(m5,14).iloc[-1]
        sl_dist = abs(candidate['entry'] - candidate['sl'])
        if a * 1.5 < sl_dist:  # SL large relative to ATR -> less ideal
            score -= 0.1
        else:
            score += 0.1
        # momentum check
        ema20 = m5['close'].ewm(span=20).mean().iloc[-1]
        if candidate['side']=='buy' and m5['close'].iloc[-1] > ema20:
            score += 0.1
        if candidate['side']=='sell' and m5['close'].iloc[-1] < ema20:
            score += 0.1
    return max(0.0, min(1.0, score))

def finalize_candidates(candidates: List[Dict], dfs: dict, disabled_hours=[(0,6)]) -> List[Dict]:
    final = []
    # check killzone
    m5 = dfs.get('M5')
    ts = None
    if m5 is not None and len(m5) > 0:
        ts = m5.index[-1] if len(m5.index)>0 else None
    if is_in_killzone(ts, disabled_hours=disabled_hours):
        return []  # block trades during killzone
    for c in candidates:
        c['score'] = score_candidate(c, dfs)
        # require min score 0.6
        if c['score'] >= 0.6:
            final.append(c)
    # sort by score desc
    final.sort(key=lambda x: x['score'], reverse=True)
    return final
