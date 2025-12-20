"""
Premium & Discount AI Module
=============================

Phân tích:
- Premium zones (above 50% Fib, overbought)
- Discount zones (below 50% Fib, oversold)
- Equilibrium (balanced zone)
- Fair value assessment
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class PremiumDiscountAI(SMCBase):
    """Premium/Discount Zone Analysis using Fibonacci 50%"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.ma_period = config.get('PD_MA_PERIOD', SMCConfig.PD_MA_PERIOD) if config else SMCConfig.PD_MA_PERIOD
        self.premium_threshold = config.get('PREMIUM_THRESHOLD', SMCConfig.PREMIUM_THRESHOLD) if config else SMCConfig.PREMIUM_THRESHOLD
        self.discount_threshold = config.get('DISCOUNT_THRESHOLD', SMCConfig.DISCOUNT_THRESHOLD) if config else SMCConfig.DISCOUNT_THRESHOLD
        self.eq_range = config.get('EQUILIBRIUM_RANGE', SMCConfig.EQUILIBRIUM_RANGE) if config else SMCConfig.EQUILIBRIUM_RANGE
    
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích Premium/Discount
        
        Args:
            df: DataFrame with OHLC data
            
        Returns:
            dict: {
                'zone': 'premium'/'discount'/'equilibrium',
                'fib_50': float,  # Equilibrium price
                'current_deviation': float,  # % from equilibrium
                'premium_zone': {
                    'high': float,
                    'low': float
                },
                'discount_zone': {
                    'high': float,
                    'low': float
                },
                'recommendation': 'sell'/'buy'/'wait',
                'confidence': float  # 0-1
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Calculate equilibrium (50% Fib)
            fib_50 = self._calculate_equilibrium(df)
            
            # Determine current zone
            current_price = df['close'].iloc[-1]
            deviation = (current_price - fib_50) / fib_50 if fib_50 > 0 else 0
            
            zone = self._determine_zone(deviation)
            
            # Define premium/discount zones
            premium_zone = self._get_premium_zone(fib_50, df)
            discount_zone = self._get_discount_zone(fib_50, df)
            
            # Trading recommendation
            recommendation, confidence = self._get_recommendation(zone, deviation, df)
            
            result = {
                'zone': zone,
                'fib_50': fib_50,
                'current_deviation': deviation,
                'premium_zone': premium_zone,
                'discount_zone': discount_zone,
                'recommendation': recommendation,
                'confidence': confidence,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ PremiumDiscountAI error: {e}")
            return self._empty_result()
    
    def _calculate_equilibrium(self, df: pd.DataFrame) -> float:
        """
        Tính equilibrium (fair value)
        
        Method 1: 50% Fibonacci of recent range
        Method 2: MA-based equilibrium
        """
        try:
            # Method 1: Fibonacci 50% of swing range
            if len(df) >= self.ma_period:
                recent = df.tail(self.ma_period)
                swing_high = recent['high'].max()
                swing_low = recent['low'].min()
                fib_50_swing = (swing_high + swing_low) / 2
                
                # Method 2: Moving average equilibrium
                ma_eq = df['close'].rolling(self.ma_period).mean().iloc[-1]
                
                # Average both methods
                equilibrium = (fib_50_swing + ma_eq) / 2
                
                logger.debug(f"📊 Equilibrium: {equilibrium:.5f}")
                return equilibrium
            else:
                # Fallback: simple midpoint
                return (df['high'].max() + df['low'].min()) / 2
                
        except Exception as e:
            logger.error(f"❌ Equilibrium calculation error: {e}")
            return df['close'].iloc[-1] if len(df) > 0 else 0.0
    
    def _determine_zone(self, deviation: float) -> str:
        """
        Xác định zone hiện tại
        
        Args:
            deviation: % deviation from equilibrium
            
        Returns:
            'premium', 'discount', or 'equilibrium'
        """
        if deviation > self.premium_threshold:
            return 'premium'
        elif deviation < self.discount_threshold:
            return 'discount'
        elif abs(deviation) <= self.eq_range:
            return 'equilibrium'
        else:
            # Between equilibrium and premium/discount
            return 'premium' if deviation > 0 else 'discount'
    
    def _get_premium_zone(self, equilibrium: float, 
                         df: pd.DataFrame) -> Dict[str, float]:
        """
        Xác định premium zone
        
        Premium = Above equilibrium + threshold
        """
        try:
            premium_low = equilibrium * (1 + self.premium_threshold)
            
            # Premium high = recent swing high
            recent_high = df['high'].tail(self.ma_period).max()
            premium_high = max(premium_low, recent_high)
            
            return {
                'low': premium_low,
                'high': premium_high
            }
            
        except Exception as e:
            return {'low': equilibrium, 'high': equilibrium}
    
    def _get_discount_zone(self, equilibrium: float,
                          df: pd.DataFrame) -> Dict[str, float]:
        """
        Xác định discount zone
        
        Discount = Below equilibrium - threshold
        """
        try:
            discount_high = equilibrium * (1 + self.discount_threshold)
            
            # Discount low = recent swing low
            recent_low = df['low'].tail(self.ma_period).min()
            discount_low = min(discount_high, recent_low)
            
            return {
                'low': discount_low,
                'high': discount_high
            }
            
        except Exception as e:
            return {'low': equilibrium, 'high': equilibrium}
    
    def _get_recommendation(self, zone: str, deviation: float,
                           df: pd.DataFrame) -> tuple:
        """
        Đưa ra recommendation dựa trên zone
        
        Returns:
            (recommendation, confidence)
        """
        try:
            # Premium zone → Look to SELL
            if zone == 'premium':
                # Strength of premium
                premium_strength = min(abs(deviation) / abs(self.premium_threshold), 1.0)
                confidence = 0.5 + (premium_strength * 0.4)  # 0.5-0.9
                
                # Check for reversal signs
                if self._check_reversal_signs(df, 'bearish'):
                    confidence += 0.1
                
                return 'sell', min(confidence, 1.0)
            
            # Discount zone → Look to BUY
            elif zone == 'discount':
                discount_strength = min(abs(deviation) / abs(self.discount_threshold), 1.0)
                confidence = 0.5 + (discount_strength * 0.4)
                
                if self._check_reversal_signs(df, 'bullish'):
                    confidence += 0.1
                
                return 'buy', min(confidence, 1.0)
            
            # Equilibrium → WAIT
            else:
                return 'wait', 0.3
                
        except Exception as e:
            return 'wait', 0.0
    
    def _check_reversal_signs(self, df: pd.DataFrame, 
                             direction: str) -> bool:
        """
        Check for reversal signs
        
        Args:
            direction: 'bullish' or 'bearish'
        """
        try:
            if len(df) < 5:
                return False
            
            current = df.iloc[-1]
            wick_info = self.calculate_wick_ratio(current)
            
            if direction == 'bullish':
                # Bullish reversal: long lower wick + bullish close
                return (wick_info['lower_wick'] > wick_info['upper_wick'] * 1.5 and
                       current['close'] > current['open'])
            else:
                # Bearish reversal: long upper wick + bearish close
                return (wick_info['upper_wick'] > wick_info['lower_wick'] * 1.5 and
                       current['close'] < current['open'])
                       
        except Exception as e:
            return False
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'zone': 'equilibrium',
            'fib_50': 0.0,
            'current_deviation': 0.0,
            'premium_zone': {'low': 0.0, 'high': 0.0},
            'discount_zone': {'low': 0.0, 'high': 0.0},
            'recommendation': 'wait',
            'confidence': 0.0,
            'timestamp': datetime.now()
        }
