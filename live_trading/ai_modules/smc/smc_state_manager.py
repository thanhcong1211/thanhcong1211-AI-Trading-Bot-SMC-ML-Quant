# smc_state_manager.py
"""
SMC State Manager
- Lưu/Load Order Blocks (OB) và FVG (Fair Value Gaps) ra file JSON
- API nhẹ để thêm, đánh dấu mitigated/expired, list current zones
"""
import json
import time
from typing import List, Dict, Optional
from pathlib import Path

DEFAULT_PATH = "smc_state.json"

class SMCStateManager:
    def __init__(self, path: str = DEFAULT_PATH):
        self.path = path
        self.state = {"order_blocks": [], "fvg": [], "meta": {"updated": time.time()}}
        self._load()

    def _load(self):
        try:
            with open(self.path, "r") as f:
                self.state = json.load(f)
        except Exception:
            # nothing saved yet or corrupted -> keep default
            self._save()

    def _save(self):
        self.state["meta"]["updated"] = time.time()
        with open(self.path, "w") as f:
            json.dump(self.state, f, indent=2)

    # ---------- Order Block API ----------
    def add_order_block(self, ob: Dict):
        """
        ob: {
            'id': str,
            'symbol': 'EURUSD',
            'timeframe': 'H1',
            'side': 'buy'|'sell',
            'proximal': float,
            'distal': float,
            'created_at': ts,
            'notes': '',
            'status': 'active'|'mitigated'|'expired'
        }
        """
        ob = dict(ob)
        ob.setdefault("created_at", time.time())
        ob.setdefault("status", "active")
        self.state["order_blocks"].append(ob)
        self._save()
        return ob

    def list_order_blocks(self, symbol: Optional[str] = None, status: Optional[str] = "active") -> List[Dict]:
        res = [ob for ob in self.state["order_blocks"] if (symbol is None or ob.get("symbol")==symbol)]
        if status is not None:
            res = [ob for ob in res if ob.get("status")==status]
        return res

    def mark_order_block(self, ob_id: str, status: str, reason: str = ""):
        for ob in self.state["order_blocks"]:
            if ob.get("id")==ob_id:
                ob["status"] = status
                ob.setdefault("history", []).append({"t": time.time(), "status": status, "reason": reason})
                self._save()
                return ob
        return None

    # ---------- FVG API ----------
    def add_fvg(self, fvg: Dict):
        fvg = dict(fvg)
        fvg.setdefault("created_at", time.time())
        fvg.setdefault("status", "active")
        self.state["fvg"].append(fvg)
        self._save()
        return fvg

    def list_fvg(self, symbol: Optional[str] = None, status: Optional[str] = "active") -> List[Dict]:
        res = [f for f in self.state["fvg"] if (symbol is None or f.get("symbol")==symbol)]
        if status is not None:
            res = [f for f in res if f.get("status")==status]
        return res

    def mark_fvg(self, fvg_id: str, status: str, reason: str = ""):
        for f in self.state["fvg"]:
            if f.get("id")==fvg_id:
                f["status"] = status
                f.setdefault("history", []).append({"t": time.time(), "status": status, "reason": reason})
                self._save()
                return f
        return None

    # ---------- Utility ----------
    def purge_expired(self, older_than_seconds: int = 86400):
        cutoff = time.time() - older_than_seconds
        changed = False
        for ob in self.state["order_blocks"]:
            if ob.get("status")=="active" and ob.get("created_at",0) < cutoff:
                ob["status"] = "expired"
                changed = True
        for f in self.state["fvg"]:
            if f.get("status")=="active" and f.get("created_at",0) < cutoff:
                f["status"] = "expired"
                changed = True
        if changed:
            self._save()
