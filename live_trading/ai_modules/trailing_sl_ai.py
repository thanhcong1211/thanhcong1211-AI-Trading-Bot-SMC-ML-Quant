"""
TrailingSL - Smart Trailing Stop-Loss Management Module
Implements adaptive trailing stops based on ATR, risk-reward ratios, and market conditions
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class TrailingSL:
    """
    Advanced trailing stop-loss management with ATR-based calculations
    """

    def __init__(self):
        """Initialize TrailingSL with default parameters"""
        self.atr_period = 14
        self.atr_multiplier = 1.5
        self.min_stop_distance = 0.001  # 0.1% minimum stop distance
        self.max_stop_distance = 0.05   # 5% maximum stop distance
        self.trailing_speed = 0.8       # How quickly to trail (0.5 = 50% of ATR)
        self.profit_lock_threshold = 2.0  # Lock in profits after 2:1 RR
        self.volatility_adjustment = True

    def analyze(self, df: pd.DataFrame, current_prices: Dict[str, float]) -> Dict[str, Any]:
        """
        Analyze trailing stop levels for current position

        Args:
            df: DataFrame with OHLCV data
            current_prices: Dict with current bid/ask prices

        Returns:
            dict: Trailing stop analysis results
        """
        try:
            if df is None or len(df) < self.atr_period:
                return {
                    "trailing_stop": None,
                    "stop_distance": 0.0,
                    "atr_value": 0.0,
                    "recommended_action": "hold",
                    "confidence": 0.0
                }

            # Calculate ATR
            atr_value = self._calculate_atr(df)

            # Get current market prices
            current_price = current_prices.get('bid', current_prices.get('ask', df['close'].iloc[-1]))

            # Calculate base trailing distance
            base_distance = atr_value * self.atr_multiplier

            # Adjust for volatility if enabled
            if self.volatility_adjustment:
                volatility_factor = self._calculate_volatility_factor(df)
                base_distance *= volatility_factor

            # Ensure reasonable bounds
            base_distance = max(self.min_stop_distance * current_price,
                              min(self.max_stop_distance * current_price, base_distance))

            # Calculate trailing stop levels
            trailing_levels = self._calculate_trailing_levels(current_price, base_distance, df)

            # Determine recommended action
            action, confidence = self._determine_action(trailing_levels, current_price, df)

            return {
                "trailing_stop": trailing_levels.get("current_stop"),
                "stop_distance": base_distance,
                "atr_value": atr_value,
                "recommended_action": action,
                "confidence": confidence,
                "levels": trailing_levels,
                "meta": {
                    "volatility_factor": volatility_factor if self.volatility_adjustment else 1.0,
                    "base_distance_pct": base_distance / current_price,
                    "current_price": current_price
                }
            }

        except Exception as e:
            logger.warning(f"TrailingSL analysis failed: {e}")
            return {
                "trailing_stop": None,
                "stop_distance": 0.0,
                "atr_value": 0.0,
                "recommended_action": "hold",
                "confidence": 0.0
            }

    def _calculate_atr(self, df: pd.DataFrame) -> float:
        """Calculate Average True Range"""
        try:
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            close = df['close'].astype(float)

            # True Range
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # ATR
            atr = tr.ewm(span=self.atr_period).mean()
            return atr.iloc[-1]

        except Exception:
            return 0.0

    def _calculate_volatility_factor(self, df: pd.DataFrame) -> float:
        """Calculate volatility adjustment factor"""
        try:
            # Use recent price movement as volatility proxy
            close = df['close'].astype(float)
            recent_returns = close.pct_change().tail(20)

            # Calculate volatility (standard deviation of returns)
            vol = recent_returns.std()

            # Normalize volatility factor (higher vol = wider stops)
            # Base factor of 1.0, scale up for high vol, down for low vol
            if vol > 0.02:  # High volatility
                factor = 1.5
            elif vol > 0.01:  # Medium volatility
                factor = 1.2
            elif vol < 0.005:  # Low volatility
                factor = 0.8
            else:
                factor = 1.0

            return factor

        except Exception:
            return 1.0

    def _calculate_trailing_levels(self, current_price: float, base_distance: float, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate trailing stop levels"""
        try:
            # Get recent swing points for reference
            recent_high = df['high'].tail(20).max()
            recent_low = df['low'].tail(20).min()

            # Calculate different trailing stop levels
            levels = {}

            # ATR-based trailing stop
            levels["atr_stop"] = current_price - base_distance

            # Percentage-based trailing stop
            levels["percentage_stop"] = current_price * (1 - self.min_stop_distance)

            # Swing-based trailing stop (use recent low as reference)
            swing_buffer = base_distance * 0.5
            levels["swing_stop"] = recent_low - swing_buffer

            # Dynamic trailing based on profit
            profit_factor = self._calculate_profit_factor(current_price, df)
            levels["dynamic_stop"] = current_price - (base_distance * profit_factor)

            # Choose the most conservative (highest) stop level
            current_stop = max(levels["atr_stop"], levels["percentage_stop"],
                             levels["swing_stop"], levels["dynamic_stop"])

            levels["current_stop"] = current_stop
            levels["recommended_stop"] = current_stop

            return levels

        except Exception:
            return {"current_stop": current_price - base_distance}

    def _calculate_profit_factor(self, current_price: float, df: pd.DataFrame) -> float:
        """Calculate profit-based adjustment factor"""
        try:
            # Estimate entry price (could be improved with actual position data)
            entry_price = df['close'].iloc[-20]  # Rough estimate

            profit_pct = (current_price - entry_price) / entry_price

            # Adjust stop distance based on profit level
            if profit_pct > 0.02:  # 2% profit
                return 0.7  # Tighter stops as profit increases
            elif profit_pct > 0.01:  # 1% profit
                return 0.8
            elif profit_pct < -0.005:  # Loss
                return 1.2  # Wider stops in losses
            else:
                return 1.0  # Standard stops

        except Exception:
            return 1.0

    def _determine_action(self, trailing_levels: Dict, current_price: float, df: pd.DataFrame) -> Tuple[str, float]:
        """Determine recommended action based on trailing levels"""
        try:
            current_stop = trailing_levels.get("current_stop", current_price)

            # Calculate risk-reward metrics
            stop_distance = abs(current_price - current_stop)
            potential_reward = self._estimate_potential_reward(current_price, df)

            rr_ratio = potential_reward / stop_distance if stop_distance > 0 else 0

            # Action logic
            if rr_ratio >= self.profit_lock_threshold:
                # Lock in profits - recommend tightening stop
                return "tighten_stop", min(0.9, rr_ratio / 10)

            elif rr_ratio >= 1.5:
                # Good RR ratio - hold current stop
                return "hold_stop", 0.7

            elif rr_ratio >= 1.0:
                # Acceptable RR - monitor
                return "monitor", 0.5

            else:
                # Poor RR - consider adjusting
                return "adjust_stop", 0.3

        except Exception:
            return "hold", 0.5

    def _estimate_potential_reward(self, current_price: float, df: pd.DataFrame) -> float:
        """Estimate potential reward based on market structure"""
        try:
            # Use recent resistance levels as reward targets
            recent_highs = df['high'].tail(20)
            resistance = recent_highs.max()

            # Use recent ATR as reward estimate
            atr = self._calculate_atr(df)

            # Take the more conservative estimate
            potential_reward = min(resistance - current_price, atr * 3)

            return max(potential_reward, atr)  # Minimum 1 ATR reward

        except Exception:
            return self._calculate_atr(df) * 2  # Default to 2 ATR

    def update_trailing_stop(self, current_price: float, current_stop: float, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Update trailing stop for an existing position

        Args:
            current_price: Current market price
            current_stop: Current stop loss price
            df: Recent market data

        Returns:
            dict: Updated stop information
        """
        try:
            # Get new trailing analysis
            analysis = self.analyze(df, {'bid': current_price, 'ask': current_price})

            new_stop = analysis.get("trailing_stop")

            if new_stop is None:
                return {
                    "updated_stop": current_stop,
                    "action": "hold",
                    "reason": "no_update_available"
                }

            # Only move stop in favorable direction (up for longs)
            if new_stop > current_stop:
                return {
                    "updated_stop": new_stop,
                    "action": "updated",
                    "reason": "favorable_move",
                    "improvement": new_stop - current_stop
                }
            else:
                return {
                    "updated_stop": current_stop,
                    "action": "hold",
                    "reason": "no_improvement"
                }

        except Exception as e:
            logger.warning(f"TrailingSL update failed: {e}")
            return {
                "updated_stop": current_stop,
                "action": "hold",
                "reason": "error"
            }