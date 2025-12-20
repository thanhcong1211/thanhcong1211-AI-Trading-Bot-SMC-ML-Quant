"""
Market Structure AI Module
==========================

Phát hiện:
- BOS (Break of Structure): Phá vỡ cấu trúc thị trường
- CHoCH (Change of Character): Thay đổi xu hướng
- Market Structure Shifts
- Swing Highs/Lows
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class MarketStructureAI(SMCBase):
    """Market Structure Analysis using ICT methodology"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.pivot_lookback = config.get('PIVOT_LOOKBACK', SMCConfig.PIVOT_LOOKBACK) if config else SMCConfig.PIVOT_LOOKBACK
        self.min_swing_pts = config.get('MIN_SWING_PTS', SMCConfig.MIN_SWING_PTS) if config else SMCConfig.MIN_SWING_PTS
        self.conf_bars = config.get('STRUCTURE_CONFIRMATION_BARS', SMCConfig.STRUCTURE_CONFIRMATION_BARS) if config else SMCConfig.STRUCTURE_CONFIRMATION_BARS
        
        self.swing_highs = []
        self.swing_lows = []
        self.last_structure = None  # 'bullish' or 'bearish'
        
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích toàn bộ market structure
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            dict: {
                'bos': bool,
                'bos_type': 'bullish'/'bearish'/None,
                'choch': bool,
                'choch_type': 'bullish_to_bearish'/'bearish_to_bullish'/None,
                'current_structure': 'bullish'/'bearish'/'sideways',
                'swing_highs': List[(time, price)],
                'swing_lows': List[(time, price)],
                'last_higher_high': float,
                'last_lower_low': float,
                'structure_quality': float  # 0-1
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Detect swing points
            self._update_swings(df)
            
            # Detect BOS
            bos, bos_type = self._detect_bos(df)
            
            # Detect CHoCH
            choch, choch_type = self._detect_choch(df)
            
            # Determine current structure
            current_struct = self._determine_structure(df)
            
            # Calculate structure quality
            quality = self._calculate_structure_quality(df)
            
            result = {
                'bos': bos,
                'bos_type': bos_type,
                'choch': choch,
                'choch_type': choch_type,
                'current_structure': current_struct,
                'swing_highs': self.swing_highs[-10:],  # Last 10
                'swing_lows': self.swing_lows[-10:],
                'last_higher_high': self._get_last_higher_high(),
                'last_lower_low': self._get_last_lower_low(),
                'structure_quality': quality,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ MarketStructureAI error: {e}")
            return self._empty_result()
    
    def _update_swings(self, df: pd.DataFrame):
        """Cập nhật swing highs và lows"""
        try:
            # Detect pivot highs
            highs, lows = self.pivot_points(
                df['high'], 
                lookback=self.pivot_lookback
            )
            
            # Update swing highs
            for time, idx, price in highs:
                if not self.swing_highs or price != self.swing_highs[-1][1]:
                    self.swing_highs.append((time, price))
            
            # Detect pivot lows
            for time, idx, price in lows:
                if not self.swing_lows or price != self.swing_lows[-1][1]:
                    self.swing_lows.append((time, price))
            
            # Keep only recent swings
            self.swing_highs = self.swing_highs[-50:]
            self.swing_lows = self.swing_lows[-50:]
            
        except Exception as e:
            logger.error(f"❌ Error updating swings: {e}")
    
    def _detect_bos(self, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
        """
        Detect Break of Structure
        
        BOS bullish: Price breaks above recent swing high
        BOS bearish: Price breaks below recent swing low
        """
        try:
            if len(self.swing_highs) < 2 or len(self.swing_lows) < 2:
                return False, None
            
            current_high = df['high'].iloc[-1]
            current_low = df['low'].iloc[-1]
            
            # Recent swing high (exclude current bar)
            recent_swing_high = max([p for t, p in self.swing_highs[-5:]])
            recent_swing_low = min([p for t, p in self.swing_lows[-5:]])
            
            # Bullish BOS: break above swing high
            if current_high > recent_swing_high + self.min_swing_pts:
                logger.info(f"🔥 Bullish BOS detected: {current_high:.5f} > {recent_swing_high:.5f}")
                return True, 'bullish'
            
            # Bearish BOS: break below swing low
            if current_low < recent_swing_low - self.min_swing_pts:
                logger.info(f"🔥 Bearish BOS detected: {current_low:.5f} < {recent_swing_low:.5f}")
                return True, 'bearish'
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ BOS detection error: {e}")
            return False, None
    
    def _detect_choch(self, df: pd.DataFrame) -> Tuple[bool, Optional[str]]:
        """
        Detect Change of Character
        
        CHoCH: Thay đổi cấu trúc từ bullish → bearish hoặc ngược lại
        Tiêu chí:
        - Volatility spike
        - Volume spike
        - Large wick rejection
        - Break counter-trend
        """
        try:
            if len(df) < 20:
                return False, None
            
            current = df.iloc[-1]
            prev = df.iloc[-2]
            
            # Volatility spike
            recent_vol = df['close'].pct_change().tail(20).std()
            avg_vol = df['close'].pct_change().std()
            vol_spike = recent_vol > avg_vol * 1.3
            
            # Volume spike
            volume_spike = self.detect_volume_spike(df, index=-1, multiplier=1.8)
            
            # Wick analysis
            wick_info = self.calculate_wick_ratio(current)
            large_wick = wick_info['wick_ratio'] > 0.6
            
            # Determine CHoCH type
            if vol_spike and large_wick:
                # Bullish CHoCH: was bearish, now bullish rejection
                if wick_info['lower_wick'] > wick_info['upper_wick'] * 2:
                    if current['close'] > current['open']:  # Bullish close
                        logger.info(f"🔄 CHoCH detected: Bearish → Bullish")
                        self.last_structure = 'bullish'
                        return True, 'bearish_to_bullish'
                
                # Bearish CHoCH: was bullish, now bearish rejection
                if wick_info['upper_wick'] > wick_info['lower_wick'] * 2:
                    if current['close'] < current['open']:  # Bearish close
                        logger.info(f"🔄 CHoCH detected: Bullish → Bearish")
                        self.last_structure = 'bearish'
                        return True, 'bullish_to_bearish'
            
            return False, None
            
        except Exception as e:
            logger.error(f"❌ CHoCH detection error: {e}")
            return False, None
    
    def _determine_structure(self, df: pd.DataFrame) -> str:
        """
        Xác định cấu trúc thị trường hiện tại
        
        Bullish: Higher Highs + Higher Lows
        Bearish: Lower Highs + Lower Lows
        Sideways: Choppy structure
        """
        try:
            if len(self.swing_highs) < 3 or len(self.swing_lows) < 3:
                return 'sideways'
            
            # Recent 3 swings
            recent_highs = [p for t, p in self.swing_highs[-3:]]
            recent_lows = [p for t, p in self.swing_lows[-3:]]
            
            # Check for higher highs
            higher_highs = all(recent_highs[i] > recent_highs[i-1] 
                             for i in range(1, len(recent_highs)))
            
            # Check for higher lows
            higher_lows = all(recent_lows[i] > recent_lows[i-1] 
                            for i in range(1, len(recent_lows)))
            
            # Check for lower highs
            lower_highs = all(recent_highs[i] < recent_highs[i-1] 
                            for i in range(1, len(recent_highs)))
            
            # Check for lower lows
            lower_lows = all(recent_lows[i] < recent_lows[i-1] 
                           for i in range(1, len(recent_lows)))
            
            if higher_highs and higher_lows:
                return 'bullish'
            elif lower_highs and lower_lows:
                return 'bearish'
            else:
                return 'sideways'
                
        except Exception as e:
            logger.error(f"❌ Structure determination error: {e}")
            return 'sideways'
    
    def _calculate_structure_quality(self, df: pd.DataFrame) -> float:
        """
        Tính chất lượng cấu trúc (0-1)
        
        Factors:
        - Số lượng swing points rõ ràng
        - Độ nhất quán của structure
        - Volume confirmation
        """
        try:
            score = 0.0
            
            # Factor 1: Clear swings (0-0.4)
            num_swings = len(self.swing_highs) + len(self.swing_lows)
            if num_swings >= 10:
                score += 0.4
            else:
                score += 0.4 * (num_swings / 10)
            
            # Factor 2: Structure consistency (0-0.4)
            struct = self._determine_structure(df)
            if struct != 'sideways':
                score += 0.4
            
            # Factor 3: Volume confirmation (0-0.2)
            if 'volume' in df.columns:
                recent_vol = df['volume'].tail(10).mean()
                avg_vol = df['volume'].mean()
                if recent_vol > avg_vol * 0.8:
                    score += 0.2
            
            return min(score, 1.0)
            
        except Exception as e:
            logger.error(f"❌ Quality calculation error: {e}")
            return 0.5
    
    def _get_last_higher_high(self) -> Optional[float]:
        """Lấy higher high gần nhất"""
        if len(self.swing_highs) < 2:
            return None
        return max([p for t, p in self.swing_highs[-5:]])
    
    def _get_last_lower_low(self) -> Optional[float]:
        """Lấy lower low gần nhất"""
        if len(self.swing_lows) < 2:
            return None
        return min([p for t, p in self.swing_lows[-5:]])
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'bos': False,
            'bos_type': None,
            'choch': False,
            'choch_type': None,
            'current_structure': 'sideways',
            'swing_highs': [],
            'swing_lows': [],
            'last_higher_high': None,
            'last_lower_low': None,
            'structure_quality': 0.0,
            'timestamp': datetime.now()
        }
