"""
Fair Value Gap (FVG) Detector Module
=====================================

Phát hiện và theo dõi:
- Bullish FVG (Imbalance lên)
- Bearish FVG (Imbalance xuống)
- FVG Mitigation (Fill)
- FVG Entry Zones
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class FVGDetector(SMCBase):
    """Fair Value Gap Detection - ICT 3-candle imbalance"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.lookback = config.get('FVG_LOOKBACK', SMCConfig.FVG_LOOKBACK) if config else SMCConfig.FVG_LOOKBACK
        self.min_size = config.get('MIN_FVG_SIZE', SMCConfig.MIN_FVG_SIZE) if config else SMCConfig.MIN_FVG_SIZE
        self.fill_threshold = config.get('FVG_FILL_THRESHOLD', SMCConfig.FVG_FILL_THRESHOLD) if config else SMCConfig.FVG_FILL_THRESHOLD
        
        self.bullish_fvgs = []  # [(time, gap_low, gap_high, filled)]
        self.bearish_fvgs = []
    
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích Fair Value Gaps
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            dict: {
                'bullish_fvg': {
                    'exists': bool,
                    'gap_low': float,
                    'gap_high': float,
                    'size': float,
                    'filled': bool,
                    'fill_percent': float
                },
                'bearish_fvg': {
                    'exists': bool,
                    'gap_low': float,
                    'gap_high': float,
                    'size': float,
                    'filled': bool,
                    'fill_percent': float
                },
                'entry_zone': {
                    'type': 'bullish'/'bearish'/None,
                    'low': float,
                    'high': float
                },
                'total_unfilled_fvgs': int
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Detect new FVGs
            self._detect_fvgs(df)
            
            # Update fill status
            self._update_fill_status(df)
            
            # Get active FVGs
            bullish_fvg = self._get_nearest_bullish_fvg(df)
            bearish_fvg = self._get_nearest_bearish_fvg(df)
            
            # Determine entry zone
            entry_zone = self._get_entry_zone(df, bullish_fvg, bearish_fvg)
            
            # Count unfilled FVGs
            unfilled_count = self._count_unfilled()
            
            result = {
                'bullish_fvg': bullish_fvg,
                'bearish_fvg': bearish_fvg,
                'entry_zone': entry_zone,
                'total_unfilled_fvgs': unfilled_count,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ FVGDetector error: {e}")
            return self._empty_result()
    
    def _detect_fvgs(self, df: pd.DataFrame):
        """
        Phát hiện FVG mới
        
        FVG = 3-candle pattern với gap:
        - Bullish: candle3.low > candle1.high (gap up)
        - Bearish: candle3.high < candle1.low (gap down)
        """
        try:
            if len(df) < 50:
                return
            
            # Scan recent candles for FVG patterns
            for i in range(-50, -2):  # Need 3 candles
                try:
                    c1 = df.iloc[i]
                    c2 = df.iloc[i+1]
                    c3 = df.iloc[i+2]
                    
                    # Bullish FVG: gap up
                    if c3['low'] > c1['high']:
                        gap_low = c1['high']
                        gap_high = c3['low']
                        gap_size = gap_high - gap_low
                        
                        if gap_size >= self.min_size:
                            # Check if already tracked
                            if not self._is_tracked(c2.name, 'bullish'):
                                self.bullish_fvgs.append((
                                    c2.name,  # Middle candle time
                                    gap_low,
                                    gap_high,
                                    False  # Not filled yet
                                ))
                                logger.debug(f"⬆️ Bullish FVG @ {gap_low:.5f}-{gap_high:.5f}")
                    
                    # Bearish FVG: gap down
                    elif c3['high'] < c1['low']:
                        gap_low = c3['high']
                        gap_high = c1['low']
                        gap_size = gap_high - gap_low
                        
                        if gap_size >= self.min_size:
                            if not self._is_tracked(c2.name, 'bearish'):
                                self.bearish_fvgs.append((
                                    c2.name,
                                    gap_low,
                                    gap_high,
                                    False
                                ))
                                logger.debug(f"⬇️ Bearish FVG @ {gap_low:.5f}-{gap_high:.5f}")
                
                except Exception as e:
                    continue
            
            # Keep only recent FVGs
            self.bullish_fvgs = self.bullish_fvgs[-30:]
            self.bearish_fvgs = self.bearish_fvgs[-30:]
            
        except Exception as e:
            logger.error(f"❌ FVG detection error: {e}")
    
    def _is_tracked(self, time, fvg_type: str) -> bool:
        """Check if FVG at this time already tracked"""
        if fvg_type == 'bullish':
            return any(t == time for t, _, _, _ in self.bullish_fvgs)
        else:
            return any(t == time for t, _, _, _ in self.bearish_fvgs)
    
    def _update_fill_status(self, df: pd.DataFrame):
        """
        Cập nhật trạng thái fill của FVGs
        
        Filled = Price has moved through X% of gap
        """
        try:
            current_price = df['close'].iloc[-1]
            
            # Update bullish FVGs
            for i, (time, gap_low, gap_high, filled) in enumerate(self.bullish_fvgs):
                if not filled:
                    # Check if price filled the gap
                    fill_level = gap_low + (gap_high - gap_low) * self.fill_threshold
                    if current_price <= fill_level:
                        self.bullish_fvgs[i] = (time, gap_low, gap_high, True)
                        logger.info(f"✅ Bullish FVG filled @ {gap_low:.5f}-{gap_high:.5f}")
            
            # Update bearish FVGs
            for i, (time, gap_low, gap_high, filled) in enumerate(self.bearish_fvgs):
                if not filled:
                    fill_level = gap_high - (gap_high - gap_low) * self.fill_threshold
                    if current_price >= fill_level:
                        self.bearish_fvgs[i] = (time, gap_low, gap_high, True)
                        logger.info(f"✅ Bearish FVG filled @ {gap_low:.5f}-{gap_high:.5f}")
                        
        except Exception as e:
            logger.error(f"❌ Fill status update error: {e}")
    
    def _get_nearest_bullish_fvg(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Lấy bullish FVG gần nhất chưa fill"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Filter unfilled FVGs below price
            unfilled = [
                (t, low, high)
                for t, low, high, filled in self.bullish_fvgs
                if not filled and high < current_price
            ]
            
            if not unfilled:
                return {'exists': False}
            
            # Get nearest (highest)
            nearest = max(unfilled, key=lambda x: x[2])
            gap_size = nearest[2] - nearest[1]
            
            # Calculate fill percent
            fill_pct = self._calculate_fill_percent(
                df, nearest[1], nearest[2], 'bullish'
            )
            
            return {
                'exists': True,
                'gap_low': nearest[1],
                'gap_high': nearest[2],
                'size': gap_size,
                'filled': False,
                'fill_percent': fill_pct
            }
            
        except Exception as e:
            return {'exists': False}
    
    def _get_nearest_bearish_fvg(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Lấy bearish FVG gần nhất chưa fill"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Filter unfilled FVGs above price
            unfilled = [
                (t, low, high)
                for t, low, high, filled in self.bearish_fvgs
                if not filled and low > current_price
            ]
            
            if not unfilled:
                return {'exists': False}
            
            # Get nearest (lowest)
            nearest = min(unfilled, key=lambda x: x[1])
            gap_size = nearest[2] - nearest[1]
            
            fill_pct = self._calculate_fill_percent(
                df, nearest[1], nearest[2], 'bearish'
            )
            
            return {
                'exists': True,
                'gap_low': nearest[1],
                'gap_high': nearest[2],
                'size': gap_size,
                'filled': False,
                'fill_percent': fill_pct
            }
            
        except Exception as e:
            return {'exists': False}
    
    def _calculate_fill_percent(self, df: pd.DataFrame,
                                gap_low: float, gap_high: float,
                                fvg_type: str) -> float:
        """Tính % FVG đã được fill"""
        try:
            current_price = df['close'].iloc[-1]
            gap_size = gap_high - gap_low
            
            if gap_size == 0:
                return 0.0
            
            if fvg_type == 'bullish':
                # How much price moved down into gap
                if current_price >= gap_high:
                    return 0.0
                elif current_price <= gap_low:
                    return 1.0
                else:
                    return (gap_high - current_price) / gap_size
            else:
                # How much price moved up into gap
                if current_price <= gap_low:
                    return 0.0
                elif current_price >= gap_high:
                    return 1.0
                else:
                    return (current_price - gap_low) / gap_size
                    
        except Exception as e:
            return 0.0
    
    def _get_entry_zone(self, df: pd.DataFrame,
                       bullish_fvg: Dict, bearish_fvg: Dict) -> Dict[str, Any]:
        """
        Xác định entry zone từ FVG
        
        Entry = 50%-75% of FVG
        """
        try:
            current_price = df['close'].iloc[-1]
            
            # Bullish FVG entry (price retraces into gap)
            if bullish_fvg['exists']:
                gap_low = bullish_fvg['gap_low']
                gap_high = bullish_fvg['gap_high']
                gap_size = gap_high - gap_low
                
                # Entry zone: 50%-75% of gap
                entry_low = gap_low + gap_size * 0.50
                entry_high = gap_low + gap_size * 0.75
                
                return {
                    'type': 'bullish',
                    'low': entry_low,
                    'high': entry_high
                }
            
            # Bearish FVG entry (price retraces into gap)
            if bearish_fvg['exists']:
                gap_low = bearish_fvg['gap_low']
                gap_high = bearish_fvg['gap_high']
                gap_size = gap_high - gap_low
                
                # Entry zone: 50%-75% of gap
                entry_low = gap_high - gap_size * 0.75
                entry_high = gap_high - gap_size * 0.50
                
                return {
                    'type': 'bearish',
                    'low': entry_low,
                    'high': entry_high
                }
            
            return {'type': None, 'low': None, 'high': None}
            
        except Exception as e:
            return {'type': None, 'low': None, 'high': None}
    
    def _count_unfilled(self) -> int:
        """Đếm số lượng FVG chưa fill"""
        bullish_unfilled = sum(1 for _, _, _, filled in self.bullish_fvgs if not filled)
        bearish_unfilled = sum(1 for _, _, _, filled in self.bearish_fvgs if not filled)
        return bullish_unfilled + bearish_unfilled
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'bullish_fvg': {'exists': False},
            'bearish_fvg': {'exists': False},
            'entry_zone': {'type': None, 'low': None, 'high': None},
            'total_unfilled_fvgs': 0,
            'timestamp': datetime.now()
        }
