"""
Liquidity AI Module
===================

Phát hiện:
- Equal Highs/Lows (Liquidity Pools)
- Liquidity Sweeps/Stop Hunts
- Buy-side & Sell-side Liquidity
- Liquidity Voids
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class LiquidityAI(SMCBase):
    """Liquidity Detection using ICT Smart Money methodology"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.lookback = config.get('LIQUIDITY_LOOKBACK', SMCConfig.LIQUIDITY_LOOKBACK) if config else SMCConfig.LIQUIDITY_LOOKBACK
        self.vol_mult = config.get('VOLUME_MULTIPLIER', SMCConfig.VOLUME_MULTIPLIER) if config else SMCConfig.VOLUME_MULTIPLIER
        self.wick_threshold = config.get('WICK_RATIO_THRESHOLD', SMCConfig.WICK_RATIO_THRESHOLD) if config else SMCConfig.WICK_RATIO_THRESHOLD
        self.equal_tolerance = config.get('EQUAL_HL_TOLERANCE', SMCConfig.EQUAL_HL_TOLERANCE) if config else SMCConfig.EQUAL_HL_TOLERANCE
        
        self.liquidity_pools = []
        
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích toàn bộ liquidity
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            dict: {
                'equal_highs': List[(time, price)],
                'equal_lows': List[(time, price)],
                'sweep_detected': bool,
                'sweep_type': 'bullish'/'bearish'/None,
                'stop_hunt': bool,
                'hunt_type': 'buy_stops'/'sell_stops'/None,
                'liquidity_map': {
                    'buy_side': float,  # Price level
                    'sell_side': float,
                    'strength': float  # 0-1
                },
                'void_detected': bool
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Detect equal highs/lows
            eq_highs = self._detect_equal_highs(df)
            eq_lows = self._detect_equal_lows(df)
            
            # Detect sweeps
            sweep, sweep_type = self._detect_sweep(df, eq_highs, eq_lows)
            
            # Detect stop hunts
            hunt, hunt_type = self._detect_stop_hunt(df)
            
            # Build liquidity map
            liq_map = self._build_liquidity_map(df, eq_highs, eq_lows)
            
            # Detect voids
            void_detected = self._detect_liquidity_void(df)
            
            result = {
                'equal_highs': eq_highs,
                'equal_lows': eq_lows,
                'sweep_detected': sweep,
                'sweep_type': sweep_type,
                'stop_hunt': hunt,
                'hunt_type': hunt_type,
                'liquidity_map': liq_map,
                'void_detected': void_detected,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ LiquidityAI error: {e}")
            return self._empty_result()
    
    def _detect_equal_highs(self, df: pd.DataFrame) -> List[Tuple]:
        """
        Phát hiện Equal Highs (sell-side liquidity)
        
        Equal highs = 2+ highs gần bằng nhau trong vùng tolerance
        """
        try:
            equal_highs = []
            highs = df['high'].tail(self.lookback).values
            times = df.index[-self.lookback:]
            
            for i in range(1, len(highs)):
                for j in range(i):
                    # Check if highs are equal within tolerance
                    diff_pct = abs(highs[i] - highs[j]) / highs[j]
                    if diff_pct <= self.equal_tolerance:
                        avg_price = (highs[i] + highs[j]) / 2
                        equal_highs.append((times[i], avg_price))
                        logger.debug(f"💧 Equal high detected @ {avg_price:.5f}")
                        break
            
            return equal_highs[-10:]  # Keep recent 10
            
        except Exception as e:
            logger.error(f"❌ Equal highs detection error: {e}")
            return []
    
    def _detect_equal_lows(self, df: pd.DataFrame) -> List[Tuple]:
        """
        Phát hiện Equal Lows (buy-side liquidity)
        
        Equal lows = 2+ lows gần bằng nhau trong vùng tolerance
        """
        try:
            equal_lows = []
            lows = df['low'].tail(self.lookback).values
            times = df.index[-self.lookback:]
            
            for i in range(1, len(lows)):
                for j in range(i):
                    # Check if lows are equal within tolerance
                    diff_pct = abs(lows[i] - lows[j]) / lows[j]
                    if diff_pct <= self.equal_tolerance:
                        avg_price = (lows[i] + lows[j]) / 2
                        equal_lows.append((times[i], avg_price))
                        logger.debug(f"💧 Equal low detected @ {avg_price:.5f}")
                        break
            
            return equal_lows[-10:]
            
        except Exception as e:
            logger.error(f"❌ Equal lows detection error: {e}")
            return []
    
    def _detect_sweep(self, df: pd.DataFrame, 
                     eq_highs: List[Tuple], 
                     eq_lows: List[Tuple]) -> Tuple[bool, Optional[str]]:
        """
        Phát hiện Liquidity Sweep
        
        Sweep = Price briefly breaks liquidity level then reverses
        """
        try:
            if len(df) < 5:
                return False, None
            
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Check bullish sweep (sweep sell-side liquidity)
            if eq_highs:
                recent_high = eq_highs[-1][1]
                # Price swept above then closed below
                if current['high'] > recent_high and current['close'] < recent_high:
                    wick_info = self.calculate_wick_ratio(current)
                    if wick_info['upper_wick'] > wick_info['lower_wick']:
                        logger.info(f"🔥 Bullish sweep @ {recent_high:.5f}")
                        return True, 'bullish'
            
            # Check bearish sweep (sweep buy-side liquidity)
            if eq_lows:
                recent_low = eq_lows[-1][1]
                # Price swept below then closed above
                if current['low'] < recent_low and current['close'] > recent_low:
                    wick_info = self.calculate_wick_ratio(current)
                    if wick_info['lower_wick'] > wick_info['upper_wick']:
                        logger.info(f"🔥 Bearish sweep @ {recent_low:.5f}")
                        return True, 'bearish'
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ Sweep detection error: {e}")
            return False, None
    
    def _detect_stop_hunt(self, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
        """
        Phát hiện Stop Hunt
        
        Stop hunt = Large wick + volume spike + reversal
        """
        try:
            if len(df) < 20:
                return False, None
            
            current = df.iloc[-1]
            
            # Calculate wick ratios
            wick_info = self.calculate_wick_ratio(current)
            
            # Volume spike
            vol_spike = self.detect_volume_spike(
                df, index=-1, 
                window=20, 
                multiplier=self.vol_mult
            )
            
            # ATR for context
            atr = self.atr(df, period=14)
            current_range = wick_info['total_range']
            avg_range = atr.iloc[-1]
            
            large_range = current_range > avg_range * 1.5 if avg_range > 0 else False
            
            # Bullish stop hunt (hunt sell stops)
            if wick_info['lower_wick'] > wick_info['upper_wick'] * self.wick_threshold:
                if vol_spike and current['close'] > current['open']:
                    logger.info(f"🎯 Bullish stop hunt detected")
                    return True, 'sell_stops'
            
            # Bearish stop hunt (hunt buy stops)
            if wick_info['upper_wick'] > wick_info['lower_wick'] * self.wick_threshold:
                if vol_spike and current['close'] < current['open']:
                    logger.info(f"🎯 Bearish stop hunt detected")
                    return True, 'buy_stops'
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ Stop hunt detection error: {e}")
            return False, None
    
    def _build_liquidity_map(self, df: pd.DataFrame,
                            eq_highs: List[Tuple],
                            eq_lows: List[Tuple]) -> Dict[str, Any]:
        """
        Xây dựng liquidity map
        
        Returns nearest buy-side and sell-side liquidity levels
        """
        try:
            current_price = df['close'].iloc[-1]
            
            # Buy-side liquidity (below price)
            buy_side = None
            if eq_lows:
                lows_below = [p for t, p in eq_lows if p < current_price]
                if lows_below:
                    buy_side = max(lows_below)  # Nearest below
            
            # Sell-side liquidity (above price)
            sell_side = None
            if eq_highs:
                highs_above = [p for t, p in eq_highs if p > current_price]
                if highs_above:
                    sell_side = min(highs_above)  # Nearest above
            
            # Strength calculation
            strength = 0.0
            if buy_side and sell_side:
                # Distance to nearest liquidity
                dist_buy = abs(current_price - buy_side) / current_price
                dist_sell = abs(sell_side - current_price) / current_price
                
                # Closer liquidity = higher strength
                avg_dist = (dist_buy + dist_sell) / 2
                strength = max(0.0, 1.0 - (avg_dist * 100))  # Normalize
            
            return {
                'buy_side': buy_side,
                'sell_side': sell_side,
                'strength': strength
            }
            
        except Exception as e:
            logger.error(f"❌ Liquidity map error: {e}")
            return {'buy_side': None, 'sell_side': None, 'strength': 0.0}
    
    def _detect_liquidity_void(self, df: pd.DataFrame) -> bool:
        """
        Phát hiện liquidity void (khoảng trống không có volume)
        
        Void = Area with abnormally low volume
        """
        try:
            if 'volume' not in df.columns or len(df) < 20:
                return False
            
            recent_vol = df['volume'].tail(10).mean()
            avg_vol = df['volume'].mean()
            
            # Void if recent volume < 30% of average
            return recent_vol < avg_vol * 0.3
            
        except Exception as e:
            logger.error(f"❌ Void detection error: {e}")
            return False
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'equal_highs': [],
            'equal_lows': [],
            'sweep_detected': False,
            'sweep_type': None,
            'stop_hunt': False,
            'hunt_type': None,
            'liquidity_map': {
                'buy_side': None,
                'sell_side': None,
                'strength': 0.0
            },
            'void_detected': False,
            'timestamp': datetime.now()
        }
