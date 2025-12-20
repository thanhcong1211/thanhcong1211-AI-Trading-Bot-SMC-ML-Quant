"""
Market Phase AI - Wyckoff-based Phase Detection
================================================

Phân tích thị trường đang ở phase nào:
1. ACCUMULATION - Smart money đang mua vào
2. MANIPULATION - False breakout để shake out weak hands
3. EXPANSION - Xu hướng chính xác, markup/markdown
4. DISTRIBUTION - Smart money đang bán ra

Logic:
- Accumulation: Range-bound + Volume tăng + Volatility thấp
- Manipulation: False break + Quick reversal
- Expansion: Strong trend + Volume confirmation
- Distribution: Range-bound high + Volume climax + Weakness

"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class MarketPhaseAI:
    """
    Wyckoff Market Phase Detection
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        # Thresholds
        self.range_threshold = self.config.get('range_threshold', 0.015)  # 1.5% range = consolidation
        self.vol_spike_threshold = self.config.get('vol_spike_threshold', 1.5)  # 1.5x avg volume
        self.trend_strength_min = self.config.get('trend_strength_min', 0.6)  # ADX-like
        self.manipulation_retracement = self.config.get('manipulation_retracement', 0.618)  # Fib 61.8%
        
    def detect_phase(self, df: pd.DataFrame, lookback: int = 50) -> Dict[str, Any]:
        """
        Detect current market phase
        
        Args:
            df: OHLC dataframe
            lookback: Candles to analyze
            
        Returns:
            {
                'phase': 'accumulation'|'manipulation'|'expansion'|'distribution',
                'confidence': float (0-1),
                'sub_phase': str,  # Detailed phase info
                'action_recommendation': 'BUY'|'SELL'|'AVOID',
                'reasoning': str
            }
        """
        try:
            if df is None or len(df) < lookback:
                return self._default_response()
            
            recent = df.tail(lookback).copy()
            
            # Calculate key metrics
            price_range = self._calculate_range(recent)
            volume_profile = self._analyze_volume(recent)
            trend_info = self._analyze_trend(recent)
            breakout_info = self._detect_manipulation(recent)
            
            # Decision tree for phase detection
            phase, confidence, sub_phase, action, reasoning = self._classify_phase(
                price_range, volume_profile, trend_info, breakout_info, recent
            )
            
            return {
                'phase': phase,
                'confidence': confidence,
                'sub_phase': sub_phase,
                'action_recommendation': action,
                'reasoning': reasoning,
                'metrics': {
                    'price_range_pct': price_range,
                    'volume_ratio': volume_profile['volume_ratio'],
                    'trend_strength': trend_info['strength'],
                    'is_false_break': breakout_info['is_manipulation']
                }
            }
            
        except Exception as e:
            logger.error(f"❌ MarketPhaseAI error: {e}")
            return self._default_response()
    
    def _calculate_range(self, df: pd.DataFrame) -> float:
        """Calculate price range as % of price"""
        high_max = df['high'].max()
        low_min = df['low'].min()
        mid_price = (high_max + low_min) / 2
        range_pct = (high_max - low_min) / mid_price if mid_price > 0 else 0
        return float(range_pct)
    
    def _analyze_volume(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze volume profile"""
        if 'volume' not in df.columns or df['volume'].sum() == 0:
            return {'volume_ratio': 1.0, 'is_climax': False, 'trend': 'neutral'}
        
        recent_vol = df['volume'].tail(10).mean()
        avg_vol = df['volume'].mean()
        vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
        
        # Volume climax = spike > 2x average
        is_climax = vol_ratio > 2.0
        
        # Volume trend
        early_vol = df['volume'].head(len(df)//2).mean()
        late_vol = df['volume'].tail(len(df)//2).mean()
        vol_trend = 'increasing' if late_vol > early_vol * 1.2 else 'decreasing' if late_vol < early_vol * 0.8 else 'neutral'
        
        return {
            'volume_ratio': vol_ratio,
            'is_climax': is_climax,
            'trend': vol_trend
        }
    
    def _analyze_trend(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Analyze trend strength"""
        close = df['close']
        high = df['high']
        low = df['low']
        
        # Simple trend strength (similar to ADX concept)
        price_change = close.iloc[-1] - close.iloc[0]
        price_range = high.max() - low.min()
        trend_strength = abs(price_change) / price_range if price_range > 0 else 0
        
        # Direction
        direction = 'bullish' if price_change > 0 else 'bearish' if price_change < 0 else 'neutral'
        
        # Higher highs / Lower lows
        recent_10 = df.tail(10)
        hh = recent_10['high'].is_monotonic_increasing
        ll = recent_10['low'].is_monotonic_decreasing
        
        return {
            'strength': float(trend_strength),
            'direction': direction,
            'higher_highs': hh,
            'lower_lows': ll
        }
    
    def _detect_manipulation(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Detect false breakouts (manipulation)"""
        if len(df) < 20:
            return {'is_manipulation': False, 'severity': 0.0}
        
        # Look for:
        # 1. Break above recent high
        # 2. Immediate reversal back into range
        recent_20 = df.tail(20)
        recent_10 = df.tail(10)
        last_5 = df.tail(5)
        
        high_20 = recent_20['high'].iloc[:-5].max()  # High before last 5 candles
        low_20 = recent_20['low'].iloc[:-5].min()
        
        # Check if last 5 candles broke above then reversed
        broke_high = last_5['high'].max() > high_20
        reversed_back = last_5['close'].iloc[-1] < high_20 * 0.995  # Back below break level
        
        # Check if last 5 candles broke below then reversed
        broke_low = last_5['low'].min() < low_20
        reversed_up = last_5['close'].iloc[-1] > low_20 * 1.005
        
        is_manipulation = (broke_high and reversed_back) or (broke_low and reversed_up)
        
        # Severity based on how deep the false break went
        severity = 0.0
        if is_manipulation:
            if broke_high and reversed_back:
                break_size = (last_5['high'].max() - high_20) / high_20
                severity = min(1.0, break_size / 0.01)  # 1% break = severity 1.0
            elif broke_low and reversed_up:
                break_size = (low_20 - last_5['low'].min()) / low_20
                severity = min(1.0, break_size / 0.01)
        
        return {
            'is_manipulation': is_manipulation,
            'severity': float(severity)
        }
    
    def _classify_phase(self, price_range: float, volume_profile: Dict, 
                       trend_info: Dict, breakout_info: Dict, df: pd.DataFrame) -> Tuple[str, float, str, str, str]:
        """
        Classify phase based on all metrics
        
        Returns: (phase, confidence, sub_phase, action, reasoning)
        """
        
        # 1. MANIPULATION - Highest priority (false breaks)
        if breakout_info['is_manipulation'] and breakout_info['severity'] > 0.5:
            return (
                'manipulation',
                0.8,
                'false_breakout',
                'AVOID',
                f"False breakout detected (severity: {breakout_info['severity']:.2f}). Market manipulating weak hands."
            )
        
        # 2. EXPANSION - Strong trend with volume
        if trend_info['strength'] > self.trend_strength_min and volume_profile['volume_ratio'] > 1.0:
            direction = trend_info['direction']
            action = 'BUY' if direction == 'bullish' else 'SELL' if direction == 'bearish' else 'AVOID'
            return (
                'expansion',
                0.85,
                f'markup_{direction}' if direction == 'bullish' else f'markdown_{direction}',
                action,
                f"Strong {direction} trend (strength: {trend_info['strength']:.2f}) with volume confirmation."
            )
        
        # 3. DISTRIBUTION - Range-bound high with volume climax
        if price_range < self.range_threshold and volume_profile['is_climax']:
            # Check if at high levels (distribution) or low levels (accumulation)
            close_position = (df['close'].iloc[-1] - df['low'].min()) / (df['high'].max() - df['low'].min())
            
            if close_position > 0.7:  # Near highs = distribution
                return (
                    'distribution',
                    0.75,
                    'topping_process',
                    'AVOID',
                    f"Range-bound near highs ({close_position:.1%}) with volume climax. Smart money distributing."
                )
        
        # 4. ACCUMULATION - Range-bound low with increasing volume
        if price_range < self.range_threshold and volume_profile['trend'] == 'increasing':
            close_position = (df['close'].iloc[-1] - df['low'].min()) / (df['high'].max() - df['low'].min())
            
            if close_position < 0.3:  # Near lows = accumulation
                return (
                    'accumulation',
                    0.75,
                    'bottoming_process',
                    'BUY',
                    f"Range-bound near lows ({close_position:.1%}) with building volume. Smart money accumulating."
                )
        
        # 5. DEFAULT - Uncertain, avoid
        return (
            'uncertain',
            0.3,
            'transitioning',
            'AVOID',
            "Phase not clearly defined. Wait for clearer structure."
        )
    
    def _default_response(self) -> Dict[str, Any]:
        """Default response when analysis fails"""
        return {
            'phase': 'uncertain',
            'confidence': 0.0,
            'sub_phase': 'unknown',
            'action_recommendation': 'AVOID',
            'reasoning': 'Insufficient data for phase analysis',
            'metrics': {}
        }
    
    def should_trade(self, phase_result: Dict[str, Any], intended_action: str) -> Tuple[bool, str]:
        """
        Check if intended action is safe in current phase
        
        Args:
            phase_result: Result from detect_phase()
            intended_action: 'BUY' or 'SELL'
            
        Returns:
            (should_trade: bool, reason: str)
        """
        phase = phase_result['phase']
        action_rec = phase_result['action_recommendation']
        
        # AVOID phases
        if phase in ['manipulation', 'uncertain']:
            return False, f"Market in {phase} phase - too risky to trade"
        
        # DISTRIBUTION - no BUY
        if phase == 'distribution' and intended_action == 'BUY':
            return False, "Distribution phase - smart money selling, avoid BUY"
        
        # ACCUMULATION - no SELL
        if phase == 'accumulation' and intended_action == 'SELL':
            return False, "Accumulation phase - smart money buying, avoid SELL"
        
        # EXPANSION - trade with trend only
        if phase == 'expansion':
            if action_rec == intended_action:
                return True, f"Expansion phase aligned with {intended_action}"
            else:
                return False, f"Expansion phase counter to {intended_action} - avoid counter-trend"
        
        # Default allow
        return True, f"Phase {phase} allows {intended_action}"


# Singleton instance
_market_phase_ai = None

def get_market_phase_ai(config: Optional[Dict[str, Any]] = None) -> MarketPhaseAI:
    """Get singleton instance"""
    global _market_phase_ai
    if _market_phase_ai is None:
        _market_phase_ai = MarketPhaseAI(config)
    return _market_phase_ai
