# smc_mtf_orchestrator.py
"""
MTF Orchestrator:
- Input: dict of dataframes {'H4': df_h4, 'H1': df_h1, 'M15': df_m15, 'M5': df_m5}
- Detect candidate order blocks/FVG from MTF, persist using SMCStateManager,
- Propose LTF entry candidates (price, sl, reason)
"""
import pandas as pd
import uuid
from typing import Dict, List
from .smc_state_manager import SMCStateManager
from .smc_filters import atr, price_in_zone

def detect_simple_order_blocks(df: pd.DataFrame, lookback: int = 100, side_hint: str = None) -> List[dict]:
    """
    A simple heuristic:
    - For bullish OB: find a strong down candle followed by large up impulse (imbalance)
    - We'll record proximal/distal from high/low of the small build-up
    NOTE: This is heuristic starter; you can swap with your MarketStructureAI detection later.
    """
    obs = []
    
    # Validate dataframe
    if df is None or len(df) < 3:
        return obs
    
    required_cols = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in required_cols):
        return obs
    
    try:
        for i in range(2, min(len(df), lookback)):
            try:
                prev = df.iloc[i-2:i]  # two-candle window
                cur = df.iloc[i]
                
                # Validate data
                if len(prev) < 2:
                    continue
                    
                # detect a 'push' candle then reversal: simple rule
                if prev['close'].iloc[-1] < prev['open'].iloc[-1] and cur['close'] > cur['open'] and abs(cur['close']-cur['open']) > 1.5 * (prev['open'].iloc[-1]-prev['close'].iloc[-1]):
                    # bullish OB
                    ob = {
                        "id": str(uuid.uuid4()),
                        "symbol": df.attrs.get("symbol", "unknown"),
                        "timeframe": df.attrs.get("timeframe","unknown"),
                        "side": "buy",
                        "proximal": float(min(prev['low'].iloc[-1], cur['low'])),
                        "distal": float(max(prev['low'].iloc[-1], cur['low'])),
                        "created_index": int(df.index[i]) if hasattr(df.index[i], '__int__') else i,
                        "notes": "heuristic_two_candle_imbalance"
                    }
                    obs.append(ob)
                # symmetrical for bearish
                if prev['close'].iloc[-1] > prev['open'].iloc[-1] and cur['close'] < cur['open'] and abs(cur['open']-cur['close']) > 1.5 * (prev['close'].iloc[-1]-prev['open'].iloc[-1]):
                    ob = {
                        "id": str(uuid.uuid4()),
                        "symbol": df.attrs.get("symbol", "unknown"),
                        "timeframe": df.attrs.get("timeframe","unknown"),
                        "side": "sell",
                        "proximal": float(max(prev['high'].iloc[-1], cur['high'])),
                        "distal": float(min(prev['high'].iloc[-1], cur['high'])),
                        "created_index": int(df.index[i]) if hasattr(df.index[i], '__int__') else i,
                        "notes": "heuristic_two_candle_imbalance"
                    }
                    obs.append(ob)
            except Exception:
                # Skip this candle if any error
                continue
    except Exception:
        # Return whatever we found so far
        pass
    
    return obs

class SMCMTFOrchestrator:
    def __init__(self, state_path: str = "smc_state.json"):
        self.state = SMCStateManager(path=state_path)

    def ingest_mtfs(self, dfs: Dict[str, pd.DataFrame], persist_new: bool = True):
        """
        dfs: {'H4': df_h4, 'H1': df_h1, 'M15': df_m15, 'M5': df_m5}
        Each df should have attrs: symbol, timeframe
        """
        # detect OB on MTF (H1/M15) to persist
        for tf in ['H4','H1','M15']:
            df = dfs.get(tf)
            if df is None:
                continue
            candidates = detect_simple_order_blocks(df, lookback=200)
            for ob in candidates:
                # basic de-dup: check if similar prox/dist exists
                exists = False
                for o in self.state.list_order_blocks(symbol=ob['symbol'], status="active"):
                    if abs(o['proximal'] - ob['proximal']) < 1e-6 and o['side']==ob['side']:
                        exists = True
                        break
                if not exists and persist_new:
                    self.state.add_order_block(ob)

    def find_ltf_entries(self, dfs: Dict[str, pd.DataFrame], max_distance_pips: float = 0.0005) -> List[dict]:
        """
        Using stored OB/FVG find precise LTF entries:
        - For each active OB matching symbol, check LTF (M5) price proximity
        - Return list of candidate dicts: {ob_id, side, entry, sl, tp, score, reason}
        """
        candidates = []
        # LTF current price (use last close of M5 if present)
        m5 = dfs.get('M5')
        if m5 is None or len(m5) == 0:
            return candidates
        cur_price = float(m5['close'].iloc[-1])
        symbol = m5.attrs.get("symbol", "unknown")
        
        # iterate active OBs
        for ob in self.state.list_order_blocks(status="active"):
            if ob.get("symbol") != symbol and symbol != "unknown":
                continue
            # check proximity: entry near proximal edge (sniper)
            proximal = ob['proximal']
            dist = abs(cur_price - proximal)
            # Simple pip scale: assume forex 1 pip ~ 0.0001 for 5-digit pairs; adjust outside
            if dist <= max_distance_pips:
                # compute sl/tp via ATR from M5
                try:
                    atr_series = atr(m5, period=14)
                    if atr_series is not None and len(atr_series) > 0:
                        a = float(atr_series.iloc[-1])
                    else:
                        # Fallback: use price-based estimate
                        a = cur_price * 0.001  # 0.1% of price
                except Exception:
                    # Fallback: use price-based estimate
                    a = cur_price * 0.001
                
                sl_dist = max(a * 1.0, 1.5 * 1e-4)  # at least small buffer
                if ob['side'] == 'buy':
                    entry = proximal
                    sl = entry - sl_dist
                    tp = entry + sl_dist * 3  # default RR 1:3
                else:
                    entry = proximal
                    sl = entry + sl_dist
                    tp = entry - sl_dist * 3
                cand = {
                    "ob_id": ob['id'],
                    "side": ob['side'],
                    "entry": float(entry),
                    "sl": float(sl),
                    "tp": float(tp),
                    "score": 0.5,  # placeholder, scoring later
                    "reason": "proximal_touch_m5"
                }
                candidates.append(cand)
        return candidates
