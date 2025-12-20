"""
Internal Structure AI Module
=============================

Phân tích:
- Lower Timeframe (LTF) structure refinement
- M1/M5 entry precision
- EMA-based trend confirmation
- Pullback depth analysis
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class InternalStructureAI(SMCBase):
    """Internal Structure Analysis - LTF Refinement"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.ema_short = config.get('LTF_EMA_SHORT', SMCConfig.LTF_EMA_SHORT) if config else SMCConfig.LTF_EMA_SHORT
        self.ema_long = config.get('LTF_EMA_LONG', SMCConfig.LTF_EMA_LONG) if config else SMCConfig.LTF_EMA_LONG
        self.pullback_window = config.get('PULLBACK_WINDOW', SMCConfig.PULLBACK_WINDOW) if config else SMCConfig.PULLBACK_WINDOW
    
    def analyze(self, df: pd.DataFrame, 
               htf_bias: Optional[str] = None) -> Dict[str, Any]:
        """
        Phân tích internal structure
        
        Args:
            df: Lower timeframe DataFrame (M1/M5)
            htf_bias: Higher timeframe bias ('bullish'/'bearish'/None)
            
        Returns:
            dict: {
                'ltf_trend': 'bullish'/'bearish'/'sideways',
                'ema_alignment': bool,  # EMAs aligned with trend
                'ema_cross': {
                    'detected': bool,
                    'type': 'bullish'/'bearish'/None
                },
                'pullback': {
                    'active': bool,
                    'depth': float,  # % of recent move
                    'quality': float  # 0-1
                },
                'entry_valid': bool,  # LTF confirms HTF bias
                'precision_entry': {
                    'price': float,
                    'confidence': float
                }
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Calculate EMAs
            ema_short = df['close'].ewm(span=self.ema_short, adjust=False).mean()
            ema_long = df['close'].ewm(span=self.ema_long, adjust=False).mean()
            
            # LTF trend
            ltf_trend = self._determine_ltf_trend(df, ema_short, ema_long)
            
            # EMA alignment
            alignment = self._check_ema_alignment(ema_short, ema_long, ltf_trend)
            
            # EMA crossover
            cross = self._detect_ema_cross(ema_short, ema_long)
            
            # Pullback analysis
            pullback = self._analyze_pullback(df, ltf_trend)
            
            # Validate entry
            entry_valid = self._validate_entry(ltf_trend, htf_bias, pullback)
            
            # Precision entry
            precision = self._calculate_precision_entry(df, ltf_trend, pullback)
            
            result = {
                'ltf_trend': ltf_trend,
                'ema_alignment': alignment,
                'ema_cross': cross,
                'pullback': pullback,
                'entry_valid': entry_valid,
                'precision_entry': precision,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ InternalStructureAI error: {e}")
            return self._empty_result()
    
    def _determine_ltf_trend(self, df: pd.DataFrame,
                            ema_short: pd.Series,
                            ema_long: pd.Series) -> str:
        """
        Xác định LTF trend
        
        Uses EMA positions and price action
        """
        try:
            current_price = df['close'].iloc[-1]
            ema_s = ema_short.iloc[-1]
            ema_l = ema_long.iloc[-1]
            
            # Bullish: price > EMA_short > EMA_long
            if current_price > ema_s > ema_l:
                return 'bullish'
            
            # Bearish: price < EMA_short < EMA_long
            elif current_price < ema_s < ema_l:
                return 'bearish'
            
            # Sideways
            else:
                return 'sideways'
                
        except Exception as e:
            return 'sideways'
    
    def _check_ema_alignment(self, ema_short: pd.Series,
                            ema_long: pd.Series,
                            trend: str) -> bool:
        """
        Check if EMAs aligned with trend
        
        Aligned = EMA order matches trend direction
        """
        try:
            ema_s = ema_short.iloc[-1]
            ema_l = ema_long.iloc[-1]
            
            if trend == 'bullish':
                return ema_s > ema_l
            elif trend == 'bearish':
                return ema_s < ema_l
            else:
                return False
                
        except Exception as e:
            return False
    
    def _detect_ema_cross(self, ema_short: pd.Series,
                         ema_long: pd.Series) -> Dict[str, Any]:
        """
        Detect EMA crossover
        
        Returns recent cross if detected
        """
        try:
            if len(ema_short) < 3:
                return {'detected': False, 'type': None}
            
            # Current positions
            s_curr = ema_short.iloc[-1]
            l_curr = ema_long.iloc[-1]
            
            # Previous positions
            s_prev = ema_short.iloc[-2]
            l_prev = ema_long.iloc[-2]
            
            # Bullish cross: short crosses above long
            if s_prev <= l_prev and s_curr > l_curr:
                logger.info("📈 Bullish EMA cross detected")
                return {'detected': True, 'type': 'bullish'}
            
            # Bearish cross: short crosses below long
            elif s_prev >= l_prev and s_curr < l_curr:
                logger.info("📉 Bearish EMA cross detected")
                return {'detected': True, 'type': 'bearish'}
            
            return {'detected': False, 'type': None}
            
        except Exception as e:
            return {'detected': False, 'type': None}
    
    def _analyze_pullback(self, df: pd.DataFrame,
                         trend: str) -> Dict[str, Any]:
        """
        Phân tích pullback depth và quality
        
        Returns pullback info if active
        """
        try:
            if len(df) < self.pullback_window:
                return {'active': False, 'depth': 0.0, 'quality': 0.0}
            
            recent = df.tail(self.pullback_window)
            current_price = df['close'].iloc[-1]
            
            if trend == 'bullish':
                # Bullish trend: check pullback from high
                recent_high = recent['high'].max()
                pullback_depth = (recent_high - current_price) / recent_high
                
                # Check if pullback is active
                active = current_price < recent_high * 0.99  # 1% below high
                
                # Quality: shallow pullback better (23.6%-50% Fib)
                if 0.236 <= pullback_depth <= 0.5:
                    quality = 0.8
                elif 0.5 < pullback_depth <= 0.618:
                    quality = 0.6
                elif pullback_depth < 0.236:
                    quality = 0.5  # Too shallow
                else:
                    quality = 0.3  # Too deep
                
                return {
                    'active': active,
                    'depth': pullback_depth,
                    'quality': quality if active else 0.0
                }
            
            elif trend == 'bearish':
                # Bearish trend: check pullback from low
                recent_low = recent['low'].min()
                pullback_depth = (current_price - recent_low) / recent_low
                
                active = current_price > recent_low * 1.01
                
                if 0.236 <= pullback_depth <= 0.5:
                    quality = 0.8
                elif 0.5 < pullback_depth <= 0.618:
                    quality = 0.6
                elif pullback_depth < 0.236:
                    quality = 0.5
                else:
                    quality = 0.3
                
                return {
                    'active': active,
                    'depth': pullback_depth,
                    'quality': quality if active else 0.0
                }
            
            else:
                return {'active': False, 'depth': 0.0, 'quality': 0.0}
                
        except Exception as e:
            return {'active': False, 'depth': 0.0, 'quality': 0.0}
    
    def _validate_entry(self, ltf_trend: str,
                       htf_bias: Optional[str],
                       pullback: Dict) -> bool:
        """
        Validate if LTF confirms HTF entry
        
        Conditions:
        - LTF trend aligns with HTF bias
        - Quality pullback present
        """
        try:
            if htf_bias is None:
                return False
            
            # LTF must match HTF
            if ltf_trend != htf_bias:
                return False
            
            # Need quality pullback
            if not pullback['active']:
                return False
            
            if pullback['quality'] < 0.5:
                return False
            
            return True
            
        except Exception as e:
            return False
    
    def _calculate_precision_entry(self, df: pd.DataFrame,
                                   trend: str,
                                   pullback: Dict) -> Dict[str, Any]:
        """
        Tính precision entry price
        
        Entry = EMA + pullback zone
        """
        try:
            if not pullback['active']:
                return {'price': None, 'confidence': 0.0}
            
            # Calculate EMA entry zone
            ema_short = df['close'].ewm(span=self.ema_short, adjust=False).mean().iloc[-1]
            ema_long = df['close'].ewm(span=self.ema_long, adjust=False).mean().iloc[-1]
            
            if trend == 'bullish':
                # Entry near EMA zone
                entry_price = (ema_short + ema_long) / 2
                
                # Confidence based on pullback quality
                confidence = pullback['quality']
                
                return {
                    'price': entry_price,
                    'confidence': confidence
                }
            
            elif trend == 'bearish':
                entry_price = (ema_short + ema_long) / 2
                confidence = pullback['quality']
                
                return {
                    'price': entry_price,
                    'confidence': confidence
                }
            
            return {'price': None, 'confidence': 0.0}
            
        except Exception as e:
            return {'price': None, 'confidence': 0.0}
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'ltf_trend': 'sideways',
            'ema_alignment': False,
            'ema_cross': {'detected': False, 'type': None},
            'pullback': {'active': False, 'depth': 0.0, 'quality': 0.0},
            'entry_valid': False,
            'precision_entry': {'price': None, 'confidence': 0.0},
            'timestamp': datetime.now()
        }
