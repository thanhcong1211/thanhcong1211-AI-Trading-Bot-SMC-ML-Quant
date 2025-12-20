"""
SMC Base Classes
Common utilities and base classes for all SMC modules
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class SMCBase:
    """Base class for all SMC modules"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize SMC base module
        
        Args:
            config: Configuration dictionary (optional)
        """
        self.config = config or {}
        self.cache = {}
        self.last_update = None
        
    def validate_dataframe(self, df: pd.DataFrame, 
                          required_cols: List[str] = None) -> bool:
        """
        Validate DataFrame has required structure
        
        Args:
            df: DataFrame to validate
            required_cols: List of required column names
            
        Returns:
            bool: True if valid
        """
        if df is None or not isinstance(df, pd.DataFrame):
            logger.warning("❌ Invalid DataFrame: None or wrong type")
            return False
            
        if df.empty:
            logger.warning("❌ Invalid DataFrame: Empty")
            return False
            
        # Default required columns for OHLCV
        req = required_cols or ['open', 'high', 'low', 'close']
        
        missing = [col for col in req if col not in df.columns]
        if missing:
            logger.warning(f"❌ Missing columns: {missing}")
            return False
            
        return True
    
    def atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Calculate Average True Range
        
        Args:
            df: DataFrame with OHLC data
            period: ATR period
            
        Returns:
            pd.Series: ATR values
        """
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(period, min_periods=1).mean()
    
    def pivot_points(self, series: pd.Series, 
                    lookback: int = 5) -> Tuple[List, List]:
        """
        Detect pivot highs and lows
        
        Args:
            series: Price series
            lookback: Window size for pivot detection
            
        Returns:
            Tuple[List, List]: (highs, lows) lists of (time, index, price)
        """
        highs = []
        lows = []
        n = len(series)
        
        for i in range(lookback, n - lookback):
            window = series.iloc[i - lookback:i + lookback + 1]
            val = series.iloc[i]
            
            if val == window.max():
                highs.append((series.index[i], i, float(val)))
            if val == window.min():
                lows.append((series.index[i], i, float(val)))
                
        return highs, lows
    
    def calculate_wick_ratio(self, row: pd.Series) -> Dict[str, float]:
        """
        Calculate wick ratios for a candle
        
        Args:
            row: DataFrame row with OHLC
            
        Returns:
            dict: Wick ratios and sizes
        """
        body_size = abs(row['close'] - row['open'])
        total_range = row['high'] - row['low']
        
        if total_range == 0:
            return {
                'upper_wick': 0.0,
                'lower_wick': 0.0,
                'wick_ratio': 0.0,
                'body_ratio': 0.0
            }
        
        # Upper wick
        upper_wick = row['high'] - max(row['open'], row['close'])
        lower_wick = min(row['open'], row['close']) - row['low']
        
        return {
            'upper_wick': upper_wick,
            'lower_wick': lower_wick,
            'wick_ratio': (upper_wick + lower_wick) / total_range,
            'body_ratio': body_size / total_range,
            'total_range': total_range
        }
    
    def is_bullish_candle(self, row: pd.Series) -> bool:
        """Check if candle is bullish"""
        return row['close'] > row['open']
    
    def is_bearish_candle(self, row: pd.Series) -> bool:
        """Check if candle is bearish"""
        return row['close'] < row['open']
    
    def get_candle_body(self, row: pd.Series) -> Tuple[float, float]:
        """
        Get candle body top and bottom
        
        Returns:
            Tuple[float, float]: (bottom, top)
        """
        return (
            min(row['open'], row['close']),
            max(row['open'], row['close'])
        )
    
    def detect_volume_spike(self, df: pd.DataFrame, 
                           index: int = -1,
                           window: int = 20,
                           multiplier: float = 1.5) -> bool:
        """
        Detect volume spike at given index
        
        Args:
            df: DataFrame with volume
            index: Index to check (default: last)
            window: Rolling window for average
            multiplier: Spike threshold multiplier
            
        Returns:
            bool: True if volume spike detected
        """
        if 'volume' not in df.columns:
            return False
            
        vol = df['volume'].iloc[index]
        avg_vol = df['volume'].rolling(window).mean().iloc[index]
        
        return vol > avg_vol * multiplier if avg_vol > 0 else False
    
    def calculate_momentum(self, series: pd.Series, 
                          period: int = 14) -> pd.Series:
        """Calculate price momentum"""
        return series.pct_change(period)
    
    def clear_cache(self):
        """Clear module cache"""
        self.cache = {}
        logger.debug("🗑️ Cache cleared")
