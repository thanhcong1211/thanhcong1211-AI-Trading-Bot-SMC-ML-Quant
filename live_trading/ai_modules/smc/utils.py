"""
SMC Utilities
Helper functions for SMC modules
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def validate_ohlcv(df: pd.DataFrame) -> bool:
    """
    Validate DataFrame has proper OHLCV structure
    
    Args:
        df: DataFrame to validate
        
    Returns:
        bool: True if valid
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return False
    
    if df.empty:
        return False
    
    required = ['open', 'high', 'low', 'close']
    for col in required:
        if col not in df.columns:
            logger.error(f"Missing column: {col}")
            return False
    
    return True


def calculate_rr_ratio(entry: float, sl: float, tp: float) -> float:
    """
    Calculate Risk/Reward ratio
    
    Args:
        entry: Entry price
        sl: Stop loss
        tp: Take profit
        
    Returns:
        float: R:R ratio
    """
    try:
        risk = abs(entry - sl)
        reward = abs(tp - entry)
        
        if risk == 0:
            return 0.0
        
        return reward / risk
        
    except Exception as e:
        return 0.0


def format_signal(signal: Dict[str, Any]) -> str:
    """
    Format trading signal for display
    
    Args:
        signal: Signal dictionary
        
    Returns:
        str: Formatted string
    """
    if not signal.get('signal'):
        return "NO SIGNAL"
    
    s = signal['signal'].upper()
    entry = signal.get('entry', 'N/A')
    sl = signal.get('sl', 'N/A')
    tp = signal.get('tp', 'N/A')
    conf = signal.get('confidence', 0)
    
    return f"{s} @ {entry} | SL: {sl} | TP: {tp} | Conf: {conf:.1%}"


def merge_timeframe_data(df_htf: pd.DataFrame,
                         df_mtf: pd.DataFrame,
                         df_ltf: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Merge and align multiple timeframe data
    
    Args:
        df_htf: Higher timeframe
        df_mtf: Medium timeframe
        df_ltf: Lower timeframe
        
    Returns:
        dict: Aligned dataframes
    """
    try:
        # Ensure all have datetime index
        for df in [df_htf, df_mtf, df_ltf]:
            if not isinstance(df.index, pd.DatetimeIndex):
                logger.warning("Converting to DatetimeIndex")
                df.index = pd.to_datetime(df.index)
        
        return {
            'htf': df_htf,
            'mtf': df_mtf,
            'ltf': df_ltf
        }
        
    except Exception as e:
        logger.error(f"Timeframe merge error: {e}")
        return {}


def calculate_position_size(account_balance: float,
                            risk_percent: float,
                            entry: float,
                            sl: float,
                            point_value: float = 0.01) -> float:
    """
    Calculate position size based on risk
    
    Args:
        account_balance: Account size
        risk_percent: Risk per trade (0.02 = 2%)
        entry: Entry price
        sl: Stop loss
        point_value: Value per point
        
    Returns:
        float: Lot size
    """
    try:
        risk_amount = account_balance * risk_percent
        sl_distance = abs(entry - sl)
        
        if sl_distance == 0:
            return 0.0
        
        lots = risk_amount / (sl_distance / point_value)
        
        # Round to 2 decimals (standard lot precision)
        return round(lots, 2)
        
    except Exception as e:
        logger.error(f"Position size calculation error: {e}")
        return 0.0


def is_market_open(current_time: pd.Timestamp,
                  market_hours: Tuple[int, int] = (0, 24)) -> bool:
    """
    Check if market is open
    
    Args:
        current_time: Current timestamp
        market_hours: (open_hour, close_hour)
        
    Returns:
        bool: True if market open
    """
    try:
        hour = current_time.hour
        return market_hours[0] <= hour < market_hours[1]
        
    except Exception as e:
        return True  # Default to open


def fibonacci_levels(high: float, low: float) -> Dict[str, float]:
    """
    Calculate Fibonacci retracement levels
    
    Args:
        high: Swing high
        low: Swing low
        
    Returns:
        dict: Fib levels
    """
    diff = high - low
    
    return {
        '0%': low,
        '23.6%': low + diff * 0.236,
        '38.2%': low + diff * 0.382,
        '50%': low + diff * 0.5,
        '61.8%': low + diff * 0.618,
        '78.6%': low + diff * 0.786,
        '100%': high
    }


def detect_candle_pattern(row: pd.Series) -> str:
    """
    Detect basic candle patterns
    
    Args:
        row: OHLC row
        
    Returns:
        str: Pattern name
    """
    try:
        o = row['open']
        h = row['high']
        l = row['low']
        c = row['close']
        
        body = abs(c - o)
        total_range = h - l
        
        if total_range == 0:
            return 'doji'
        
        body_ratio = body / total_range
        
        # Doji
        if body_ratio < 0.1:
            return 'doji'
        
        # Hammer/Shooting star
        upper_wick = h - max(o, c)
        lower_wick = min(o, c) - l
        
        if lower_wick > body * 2 and upper_wick < body * 0.3:
            return 'hammer' if c > o else 'hanging_man'
        
        if upper_wick > body * 2 and lower_wick < body * 0.3:
            return 'shooting_star' if c < o else 'inverted_hammer'
        
        # Strong directional
        if body_ratio > 0.7:
            return 'strong_bullish' if c > o else 'strong_bearish'
        
        return 'normal'
        
    except Exception as e:
        return 'unknown'


def log_smc_state(smc_data: Dict[str, Any]):
    """
    Log SMC state for debugging
    
    Args:
        smc_data: SMC analysis result
    """
    try:
        logger.debug("=" * 40)
        logger.debug("SMC STATE SNAPSHOT")
        
        for key, value in smc_data.items():
            if isinstance(value, dict):
                logger.debug(f"{key}:")
                for k, v in value.items():
                    logger.debug(f"  {k}: {v}")
            else:
                logger.debug(f"{key}: {value}")
        
        logger.debug("=" * 40)
        
    except Exception as e:
        logger.error(f"State logging error: {e}")
