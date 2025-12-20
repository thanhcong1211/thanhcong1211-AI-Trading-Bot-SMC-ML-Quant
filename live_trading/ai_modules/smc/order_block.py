"""
Order Block AI Module
=====================

Phát hiện và phân tích:
- Bullish Order Blocks (demand zones)
- Bearish Order Blocks (supply zones)
- Order Block Mitigation
- Rejection Blocks
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class OrderBlockAI(SMCBase):
    """Order Block Detection using ICT methodology"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.lookback = config.get('OB_LOOKBACK', SMCConfig.OB_LOOKBACK) if config else SMCConfig.OB_LOOKBACK
        self.min_move = config.get('MIN_MOVE_PTS', SMCConfig.MIN_MOVE_PTS) if config else SMCConfig.MIN_MOVE_PTS
        self.rejection_threshold = config.get('OB_REJECTION_THRESHOLD', SMCConfig.OB_REJECTION_THRESHOLD) if config else SMCConfig.OB_REJECTION_THRESHOLD
        self.mitigation_threshold = config.get('MITIGATION_THRESHOLD', SMCConfig.MITIGATION_THRESHOLD) if config else SMCConfig.MITIGATION_THRESHOLD
        
        self.bullish_obs = []  # [(time, low, high, strength)]
        self.bearish_obs = []
        
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích Order Blocks
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            dict: {
                'bullish_ob': {
                    'exists': bool,
                    'entry_low': float,
                    'entry_high': float,
                    'strength': float,  # 0-1
                    'mitigated': bool
                },
                'bearish_ob': {
                    'exists': bool,
                    'entry_low': float,
                    'entry_high': float,
                    'strength': float,
                    'mitigated': bool
                },
                'rejection_detected': bool,
                'rejection_type': 'bullish'/'bearish'/None,
                'nearest_ob': {
                    'type': 'bullish'/'bearish'/None,
                    'distance': float,  # % from current price
                    'entry_zone': (low, high)
                }
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Detect new order blocks
            self._detect_order_blocks(df)
            
            # Get active OBs
            bullish_ob = self._get_nearest_bullish_ob(df)
            bearish_ob = self._get_nearest_bearish_ob(df)
            
            # Check mitigation
            if bullish_ob['exists']:
                bullish_ob['mitigated'] = self._check_mitigation(
                    df, bullish_ob['entry_low'], bullish_ob['entry_high'], 'bullish'
                )
            
            if bearish_ob['exists']:
                bearish_ob['mitigated'] = self._check_mitigation(
                    df, bearish_ob['entry_low'], bearish_ob['entry_high'], 'bearish'
                )
            
            # Detect rejection from OB
            rejection, rej_type = self._detect_rejection(df, bullish_ob, bearish_ob)
            
            # Find nearest OB
            nearest = self._find_nearest_ob(df, bullish_ob, bearish_ob)
            
            result = {
                'bullish_ob': bullish_ob,
                'bearish_ob': bearish_ob,
                'rejection_detected': rejection,
                'rejection_type': rej_type,
                'nearest_ob': nearest,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ OrderBlockAI error: {e}")
            return self._empty_result()
    
    def _detect_order_blocks(self, df: pd.DataFrame):
        """
        Phát hiện Order Blocks mới
        
        OB criteria:
        - High volume candle
        - Followed by strong directional move
        - Rejection from zone
        """
        try:
            if len(df) < 50:
                return
            
            # Look for high volume candles
            avg_volume = df['volume'].rolling(20).mean()
            
            for i in range(-50, -1):
                try:
                    candle = df.iloc[i]
                    
                    # Skip if volume too low
                    if candle['volume'] < avg_volume.iloc[i] * 1.2:
                        continue
                    
                    # Check for bullish OB
                    if self._is_bullish_ob(df, i):
                        ob_low = candle['low']
                        ob_high = candle['high']
                        strength = self._calculate_ob_strength(df, i, 'bullish')
                        
                        self.bullish_obs.append((
                            candle.name,  # timestamp
                            ob_low,
                            ob_high,
                            strength
                        ))
                        logger.debug(f"📦 Bullish OB @ {ob_low:.5f}-{ob_high:.5f}")
                    
                    # Check for bearish OB
                    elif self._is_bearish_ob(df, i):
                        ob_low = candle['low']
                        ob_high = candle['high']
                        strength = self._calculate_ob_strength(df, i, 'bearish')
                        
                        self.bearish_obs.append((
                            candle.name,
                            ob_low,
                            ob_high,
                            strength
                        ))
                        logger.debug(f"📦 Bearish OB @ {ob_low:.5f}-{ob_high:.5f}")
                
                except Exception as e:
                    continue
            
            # Keep only recent OBs (last 20)
            self.bullish_obs = self.bullish_obs[-20:]
            self.bearish_obs = self.bearish_obs[-20:]
            
        except Exception as e:
            logger.error(f"❌ OB detection error: {e}")
    
    def _is_bullish_ob(self, df: pd.DataFrame, index: int) -> bool:
        """
        Check if candle is bullish OB
        
        Criteria:
        - Bullish candle or strong bullish rejection
        - Followed by upward move
        """
        try:
            if index >= -3:  # Need future bars
                return False
            
            candle = df.iloc[index]
            next_3 = df.iloc[index+1:index+4]
            
            # Must have upward movement after
            move_up = next_3['high'].max() - candle['high']
            move_pct = move_up / candle['close'] if candle['close'] > 0 else 0
            
            if move_pct < self.min_move:
                return False
            
            # Check for bullish characteristics
            wick_info = self.calculate_wick_ratio(candle)
            bullish_wick = wick_info['lower_wick'] > wick_info['upper_wick']
            bullish_close = candle['close'] >= candle['open']
            
            return bullish_wick or bullish_close
            
        except Exception as e:
            return False
    
    def _is_bearish_ob(self, df: pd.DataFrame, index: int) -> bool:
        """
        Check if candle is bearish OB
        
        Criteria:
        - Bearish candle or strong bearish rejection
        - Followed by downward move
        """
        try:
            if index >= -3:
                return False
            
            candle = df.iloc[index]
            next_3 = df.iloc[index+1:index+4]
            
            # Must have downward movement after
            move_down = candle['low'] - next_3['low'].min()
            move_pct = move_down / candle['close'] if candle['close'] > 0 else 0
            
            if move_pct < self.min_move:
                return False
            
            # Check for bearish characteristics
            wick_info = self.calculate_wick_ratio(candle)
            bearish_wick = wick_info['upper_wick'] > wick_info['lower_wick']
            bearish_close = candle['close'] <= candle['open']
            
            return bearish_wick or bearish_close
            
        except Exception as e:
            return False
    
    def _calculate_ob_strength(self, df: pd.DataFrame, 
                              index: int, ob_type: str) -> float:
        """
        Tính strength của OB (0-1)
        
        Factors:
        - Volume
        - Move size after OB
        - Wick rejection
        """
        try:
            candle = df.iloc[index]
            score = 0.0
            
            # Factor 1: Volume (0-0.4)
            avg_vol = df['volume'].rolling(20).mean().iloc[index]
            if avg_vol > 0:
                vol_ratio = candle['volume'] / avg_vol
                score += min(0.4, 0.4 * (vol_ratio / 2.0))
            
            # Factor 2: Move size (0-0.4)
            if index < -3:
                next_3 = df.iloc[index+1:index+4]
                if ob_type == 'bullish':
                    move = next_3['high'].max() - candle['high']
                else:
                    move = candle['low'] - next_3['low'].min()
                
                move_pct = move / candle['close'] if candle['close'] > 0 else 0
                score += min(0.4, 0.4 * (move_pct / self.min_move))
            
            # Factor 3: Wick (0-0.2)
            wick_info = self.calculate_wick_ratio(candle)
            if ob_type == 'bullish':
                if wick_info['lower_wick'] > wick_info['upper_wick']:
                    score += 0.2
            else:
                if wick_info['upper_wick'] > wick_info['lower_wick']:
                    score += 0.2
            
            return min(score, 1.0)
            
        except Exception as e:
            return 0.5
    
    def _get_nearest_bullish_ob(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Lấy bullish OB gần nhất chưa bị mitigated"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Filter unmitigated OBs below current price
            valid_obs = [
                (t, low, high, strength) 
                for t, low, high, strength in self.bullish_obs
                if high < current_price
            ]
            
            if not valid_obs:
                return {'exists': False}
            
            # Get nearest
            nearest = max(valid_obs, key=lambda x: x[2])  # Highest high
            
            return {
                'exists': True,
                'entry_low': nearest[1],
                'entry_high': nearest[2],
                'strength': nearest[3],
                'mitigated': False
            }
            
        except Exception as e:
            return {'exists': False}
    
    def _get_nearest_bearish_ob(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Lấy bearish OB gần nhất chưa bị mitigated"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Filter unmitigated OBs above current price
            valid_obs = [
                (t, low, high, strength)
                for t, low, high, strength in self.bearish_obs
                if low > current_price
            ]
            
            if not valid_obs:
                return {'exists': False}
            
            # Get nearest
            nearest = min(valid_obs, key=lambda x: x[1])  # Lowest low
            
            return {
                'exists': True,
                'entry_low': nearest[1],
                'entry_high': nearest[2],
                'strength': nearest[3],
                'mitigated': False
            }
            
        except Exception as e:
            return {'exists': False}
    
    def _check_mitigation(self, df: pd.DataFrame,
                         ob_low: float, ob_high: float,
                         ob_type: str) -> bool:
        """
        Check if OB is mitigated
        
        Mitigated = Price filled 50%+ of OB
        """
        try:
            current = df.iloc[-1]
            ob_mid = (ob_low + ob_high) / 2
            
            if ob_type == 'bullish':
                # Bullish OB mitigated if price closes below midpoint
                return current['close'] < ob_mid
            else:
                # Bearish OB mitigated if price closes above midpoint
                return current['close'] > ob_mid
                
        except Exception as e:
            return False
    
    def _detect_rejection(self, df: pd.DataFrame,
                         bullish_ob: Dict, bearish_ob: Dict) -> Tuple[bool, Optional[str]]:
        """Phát hiện rejection from OB"""
        try:
            if len(df) < 2:
                return False, None
            
            current = df.iloc[-1]
            wick_info = self.calculate_wick_ratio(current)
            
            # Bullish rejection (from bullish OB)
            if bullish_ob['exists'] and not bullish_ob['mitigated']:
                in_zone = (current['low'] <= bullish_ob['entry_high'] and
                          current['low'] >= bullish_ob['entry_low'])
                
                if in_zone and wick_info['lower_wick'] > wick_info['upper_wick'] * 1.5:
                    if current['close'] > current['open']:
                        return True, 'bullish'
            
            # Bearish rejection (from bearish OB)
            if bearish_ob['exists'] and not bearish_ob['mitigated']:
                in_zone = (current['high'] >= bearish_ob['entry_low'] and
                          current['high'] <= bearish_ob['entry_high'])
                
                if in_zone and wick_info['upper_wick'] > wick_info['lower_wick'] * 1.5:
                    if current['close'] < current['open']:
                        return True, 'bearish'
            
            return False, None
            
        except Exception as e:
            return False, None
    
    def _find_nearest_ob(self, df: pd.DataFrame,
                        bullish_ob: Dict, bearish_ob: Dict) -> Dict[str, Any]:
        """Tìm OB gần nhất với giá hiện tại"""
        try:
            current_price = df['close'].iloc[-1]
            
            nearest = {'type': None, 'distance': float('inf'), 'entry_zone': None}
            
            # Check bullish OB
            if bullish_ob['exists']:
                dist = abs(current_price - bullish_ob['entry_high']) / current_price
                if dist < nearest['distance']:
                    nearest = {
                        'type': 'bullish',
                        'distance': dist,
                        'entry_zone': (bullish_ob['entry_low'], bullish_ob['entry_high'])
                    }
            
            # Check bearish OB
            if bearish_ob['exists']:
                dist = abs(bearish_ob['entry_low'] - current_price) / current_price
                if dist < nearest['distance']:
                    nearest = {
                        'type': 'bearish',
                        'distance': dist,
                        'entry_zone': (bearish_ob['entry_low'], bearish_ob['entry_high'])
                    }
            
            return nearest
            
        except Exception as e:
            return {'type': None, 'distance': float('inf'), 'entry_zone': None}
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'bullish_ob': {'exists': False},
            'bearish_ob': {'exists': False},
            'rejection_detected': False,
            'rejection_type': None,
            'nearest_ob': {'type': None, 'distance': float('inf'), 'entry_zone': None},
            'timestamp': datetime.now()
        }
