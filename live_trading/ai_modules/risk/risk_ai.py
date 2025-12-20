"""RiskAI v2

Enhanced RiskAI with additional gates and persistence. Keeps public API
compatible with previous version: register_trade_result, allowed_to_trade,
reset_daily_if_needed.
"""
import time
from datetime import datetime
import json
import os


class RiskAI:
    """RiskAI v2

    - API compatibility preserved
    - Adds: max_daily_trades, max_total_drawdown_pct, max_daily_drawdown_pct,
      trades_today tracking, persistence (save/load state)
    """

    def __init__(
        self,
        max_consecutive_loss: int = 3,
        daily_max_loss_pct: float = 2.0,
        cooldown_after_sl: int = 180,
        volatility_block_threshold: float = 2.0,
        max_daily_trades: int = 10,
        max_total_drawdown_pct: float = 25.0,
        max_daily_drawdown_pct: float = 5.0,
        starting_balance: float = None,
        persist_path: str = None,
    ):
        # core limits
        self.max_consecutive_loss = int(max_consecutive_loss)
        self.daily_max_loss_pct = float(daily_max_loss_pct)
        self.cooldown_after_sl = int(cooldown_after_sl)
        self.volatility_block_threshold = float(volatility_block_threshold)

        # new limits
        self.max_daily_trades = int(max_daily_trades)
        self.max_total_drawdown_pct = float(max_total_drawdown_pct)
        self.max_daily_drawdown_pct = float(max_daily_drawdown_pct)

        # runtime account info
        self.starting_balance = float(starting_balance) if starting_balance is not None else None
        self.persist_path = persist_path

        # state
        self.consecutive_loss = 0
        self.daily_loss = 0.0
        self.trades_today = 0
        self.last_sl_time = None
        self.last_reset_date = datetime.utcnow().date()
        self.peak_equity = None
        self.current_equity = None

        # load persisted if possible
        if self.persist_path and os.path.exists(self.persist_path):
            try:
                self.load_state(self.persist_path)
            except Exception:
                pass

    # -----------------------------
    # helper: reset daily counters
    # -----------------------------
    def reset_daily_if_needed(self):
        today = datetime.utcnow().date()
        if today != self.last_reset_date:
            self.daily_loss = 0.0
            self.trades_today = 0
            self.consecutive_loss = 0
            self.last_reset_date = today

    # -----------------------------
    # update equity tracking (call periodically from orchestrator)
    # -----------------------------
    def update_equity(self, equity):
        try:
            equity = float(equity)
        except Exception:
            return
        self.current_equity = equity
        if self.peak_equity is None or equity > self.peak_equity:
            self.peak_equity = equity

    # -----------------------------
    # register trade result (profit can be negative)
    # Called when a position is closed
    # -----------------------------
    def register_trade_result(self, profit, is_live=True):
        self.reset_daily_if_needed()

        # update trades counter when a trade closed (count only live trades)
        if is_live:
            self.trades_today += 1

        # update daily loss tracking (only count negative amounts)
        if profit < 0:
            self.daily_loss += -float(profit)
            self.consecutive_loss += 1
            self.last_sl_time = time.time()
        else:
            self.consecutive_loss = 0

        # optionally persist
        if self.persist_path:
            try:
                self.save_state(self.persist_path)
            except Exception:
                pass

    # -----------------------------
    # compute drawdown percent from starting balance or peak equity
    # -----------------------------
    def current_total_drawdown_pct(self):
        if self.starting_balance:
            if self.current_equity is None:
                return None
            dd = max(0.0, (self.starting_balance - self.current_equity) / (self.starting_balance + 1e-9) * 100.0)
            return dd
        else:
            if self.peak_equity is None or self.current_equity is None:
                return None
            dd = max(0.0, (self.peak_equity - self.current_equity) / (self.peak_equity + 1e-9) * 100.0)
            return dd

    # -----------------------------
    # compute daily drawdown percent (approx via daily_loss / starting_balance or peak_equity)
    # -----------------------------
    def current_daily_drawdown_pct(self):
        if self.starting_balance:
            dd = (self.daily_loss / (self.starting_balance + 1e-9)) * 100.0
            return dd
        else:
            if self.peak_equity:
                dd = (self.daily_loss / (self.peak_equity + 1e-9)) * 100.0
                return dd
        return None

    # -----------------------------
    # core check: allowed to trade?
    # returns (bool, reason)
    # -----------------------------
    def allowed_to_trade(self, volatility_score=1.0, equity=None):
        self.reset_daily_if_needed()

        if equity is not None:
            self.update_equity(equity)

        # 1) max consecutive loss
        if self.consecutive_loss >= self.max_consecutive_loss:
            return False, "blocked: max_consecutive_loss_reached"

        # 2) daily loss percent (absolute losses today)
        daily_loss_pct = self.current_daily_drawdown_pct()
        if daily_loss_pct is not None and daily_loss_pct >= self.daily_max_loss_pct:
            return False, f"blocked: daily_loss_pct_exceeded ({daily_loss_pct:.2f}%)"

        # 3) daily drawdown percent (alternative check)
        if self.max_daily_drawdown_pct is not None:
            if daily_loss_pct is not None and daily_loss_pct >= self.max_daily_drawdown_pct:
                return False, f"blocked: daily_drawdown_pct_exceeded ({daily_loss_pct:.2f}%)"

        # 4) daily trades cap
        if self.trades_today >= self.max_daily_trades:
            return False, "blocked: max_daily_trades_reached"

        # 5) total drawdown percent (from starting or peak)
        total_dd = self.current_total_drawdown_pct()
        if total_dd is not None and total_dd >= self.max_total_drawdown_pct:
            return False, f"blocked: total_drawdown_exceeded ({total_dd:.2f}%)"

        # 6) cooldown after last SL
        if self.last_sl_time:
            if time.time() - self.last_sl_time < self.cooldown_after_sl:
                remaining = int(self.cooldown_after_sl - (time.time() - self.last_sl_time))
                return False, f"blocked: cooldown_after_sl ({remaining}s left)"

        # 7) volatility block
        if volatility_score >= self.volatility_block_threshold:
            return False, "blocked: high_volatility"

        return True, "ok"

    # -----------------------------
    # Persistence helpers
    # -----------------------------
    def save_state(self, path):
        state = {
            "consecutive_loss": int(self.consecutive_loss),
            "daily_loss": float(self.daily_loss),
            "trades_today": int(self.trades_today),
            "last_sl_time": float(self.last_sl_time) if self.last_sl_time else None,
            "last_reset_date": self.last_reset_date.isoformat(),
            "peak_equity": float(self.peak_equity) if self.peak_equity is not None else None,
            "current_equity": float(self.current_equity) if self.current_equity is not None else None,
            "starting_balance": float(self.starting_balance) if self.starting_balance is not None else None,
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f)

    def load_state(self, path):
        with open(path, "r") as f:
            state = json.load(f)
        self.consecutive_loss = int(state.get("consecutive_loss", 0))
        self.daily_loss = float(state.get("daily_loss", 0.0))
        self.trades_today = int(state.get("trades_today", 0))
        self.last_sl_time = float(state.get("last_sl_time")) if state.get("last_sl_time") else None
        self.last_reset_date = datetime.fromisoformat(state.get("last_reset_date")).date() if state.get("last_reset_date") else datetime.utcnow().date()
        self.peak_equity = float(state.get("peak_equity")) if state.get("peak_equity") else None
        self.current_equity = float(state.get("current_equity")) if state.get("current_equity") else None
        self.starting_balance = float(state.get("starting_balance")) if state.get("starting_balance") else None

    # -----------------------------
    # utility: manually increment trades (if you open trades externally)
    # -----------------------------
    def increment_trade_count(self):
        self.reset_daily_if_needed()
        self.trades_today += 1
        if self.persist_path:
            try:
                self.save_state(self.persist_path)
            except Exception:
                pass
"""RiskAI - simple safety module

This module implements the RiskAI class provided by the user. It is
designed to be imported into the orchestrator and used as a gate before
opening positions.
"""
import time
from datetime import datetime


class RiskAI:
    def __init__(
        self,
        max_consecutive_loss=3,
        daily_max_loss_pct=2.0,
        cooldown_after_sl=180,
        volatility_block_threshold=2.0,
    ):
        # --- Các biến cốt lõi ---
        self.max_consecutive_loss = max_consecutive_loss
        self.daily_max_loss_pct = daily_max_loss_pct
        self.cooldown_after_sl = cooldown_after_sl
        self.volatility_block_threshold = volatility_block_threshold

        # --- Trạng thái ---
        self.consecutive_loss = 0
        self.daily_loss = 0.0
        self.last_sl_time = None
        self.last_reset_date = datetime.utcnow().date()

    # -------------------------------------------------------------
    # Reset daily loss mỗi ngày
    # -------------------------------------------------------------
    def reset_daily_if_needed(self):
        today = datetime.utcnow().date()
        if today != self.last_reset_date:
            self.daily_loss = 0.0
            self.consecutive_loss = 0
            self.last_reset_date = today

    # -------------------------------------------------------------
    # Ghi nhận kết quả lệnh vừa đóng
    # -------------------------------------------------------------
    def register_trade_result(self, profit):
        """Register the profit (positive) or loss (negative) of a closed trade.

        Note: `daily_max_loss_pct` is treated as a numeric threshold that
        the calling orchestrator interprets appropriately (kept as provided).
        """
        self.reset_daily_if_needed()

        # daily_loss accumulates the absolute loss amounts (not converted to %)
        self.daily_loss += -profit if profit < 0 else 0

        if profit < 0:
            self.consecutive_loss += 1
            self.last_sl_time = time.time()
        else:
            self.consecutive_loss = 0

    # -------------------------------------------------------------
    # Kiểm tra có được phép mở lệnh hay không
    # -------------------------------------------------------------
    def allowed_to_trade(self, volatility_score=1.0):
        """Return (bool, reason)."""

        self.reset_daily_if_needed()

        # 1) Chặn chuỗi thua
        if self.consecutive_loss >= self.max_consecutive_loss:
            return False, "blocked: max consecutive loss reached"

        # 2) Chặn daily loss
        if self.daily_loss >= self.daily_max_loss_pct:
            return False, "blocked: daily loss max reached"

        # 3) Cooldown sau SL
        if self.last_sl_time:
            if time.time() - self.last_sl_time < self.cooldown_after_sl:
                return False, "blocked: cooldown after SL"

        # 4) Chặn khi biến động mạnh (được truyền từ VolatilityAI)
        if volatility_score >= self.volatility_block_threshold:
            return False, "blocked: high volatility"

        return True, "ok"
