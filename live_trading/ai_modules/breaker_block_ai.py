"""
Breaker Block AI - Failed Order Block Detection
================================================

Breaker Block = Order Block that FAILED and reversed
- Bullish OB failed → Price broke below distal → Now BEARISH signal
- Bearish OB failed → Price broke above distal → Now BULLISH signal

This prevents bot from trading INVALID Order Blocks

Logic:
1. Track all Order Blocks
2. Monitor price interaction
3. If OB gets "broken" (invalidated) → Mark as Breaker
4. Use Breaker Block as NEW signal in opposite direction

"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class BreakerBlockAI:
    """
    Detect failed Order Blocks (Breakers) and use them as reversal signals
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.breaker_confirmation_candles = self.config.get('breaker_confirmation', 2)  # Candles to confirm break
        self.breaker_buffer = self.config.get('breaker_buffer', 0.0005)  # 0.05% buffer
        self.tracked_obs = []  # List of Order Blocks being tracked
        self.breakers = []  # List of confirmed Breaker Blocks
        
    def track_order_block(self, ob: Dict[str, Any]):
        """
        Start tracking an Order Block for potential invalidation
        
        Args:
            ob: {
                'id': str,
                'side': 'buy'|'sell',
                'proximal': float,
                'distal': float,
                'created_at': timestamp,
                'timeframe': str
            }
        """
        if not ob or 'id' in [o['id'] for o in self.tracked_obs]:
            return
        
        ob['status'] = 'active'
        ob['tracked_since'] = datetime.now()
        self.tracked_obs.append(ob)
        logger.debug(f"📍 Tracking OB: {ob['side'].upper()} @ {ob['distal']:.5f}")
    
    def update(self, df: pd.DataFrame, current_price: float) -> Dict[str, Any]:
        """
        Update all tracked OBs and detect Breaker Blocks
        
        Args:
            df: Recent OHLC data (for confirmation)
            current_price: Current market price
            
        Returns:
            {
                'new_breakers': List[dict],  # Newly detected breakers
                'active_breakers': List[dict],  # All active breakers
                'invalidated_obs': List[str]  # IDs of invalidated OBs
            }
        """
        try:
            new_breakers = []
            invalidated_obs = []
            
            # Check each tracked OB
            for ob in self.tracked_obs[:]:  # Copy to allow removal
                if ob['status'] != 'active':
                    continue
                
                # Check if OB got invalidated (broken)
                is_broken, break_severity = self._check_invalidation(ob, df, current_price)
                
                if is_broken:
                    # Convert to Breaker Block
                    breaker = self._create_breaker(ob, break_severity, current_price)
                    new_breakers.append(breaker)
                    self.breakers.append(breaker)
                    
                    # Mark OB as invalid
                    ob['status'] = 'invalidated'
                    invalidated_obs.append(ob['id'])
                    
                    logger.info(f"💥 BREAKER DETECTED: {breaker['side'].upper()} @ {breaker['price']:.5f} "
                              f"(OB {ob['side']} failed)")
            
            # Clean up old OBs (keep last 100)
            if len(self.tracked_obs) > 100:
                self.tracked_obs = [ob for ob in self.tracked_obs if ob['status'] == 'active'][-100:]
            
            # Clean up old breakers (keep last 50)
            if len(self.breakers) > 50:
                self.breakers = self.breakers[-50:]
            
            return {
                'new_breakers': new_breakers,
                'active_breakers': [b for b in self.breakers if b['status'] == 'active'],
                'invalidated_obs': invalidated_obs
            }
            
        except Exception as e:
            logger.error(f"❌ BreakerBlockAI update error: {e}")
            return {'new_breakers': [], 'active_breakers': [], 'invalidated_obs': []}
    
    def _check_invalidation(self, ob: Dict, df: pd.DataFrame, current_price: float) -> tuple[bool, float]:
        """
        Check if Order Block has been invalidated (broken)
        
        Returns: (is_broken: bool, severity: float)
        """
        side = ob['side']
        distal = ob['distal']
        proximal = ob['proximal']
        
        # Add buffer for noise tolerance
        buffer = distal * self.breaker_buffer
        
        if side == 'buy':
            # Bullish OB invalidated if price breaks BELOW distal (support failed)
            break_level = distal - buffer
            is_broken = current_price < break_level
            
            if is_broken:
                # Check confirmation: need X candles closing below
                recent_candles = df.tail(self.breaker_confirmation_candles)
                confirmed = (recent_candles['close'] < break_level).sum() >= self.breaker_confirmation_candles
                
                if confirmed:
                    break_distance = (distal - current_price) / distal
                    return True, float(break_distance)
        
        elif side == 'sell':
            # Bearish OB invalidated if price breaks ABOVE distal (resistance failed)
            break_level = distal + buffer
            is_broken = current_price > break_level
            
            if is_broken:
                # Check confirmation
                recent_candles = df.tail(self.breaker_confirmation_candles)
                confirmed = (recent_candles['close'] > break_level).sum() >= self.breaker_confirmation_candles
                
                if confirmed:
                    break_distance = (current_price - distal) / distal
                    return True, float(break_distance)
        
        return False, 0.0
    
    def _create_breaker(self, failed_ob: Dict, severity: float, current_price: float) -> Dict[str, Any]:
        """
        Create Breaker Block from failed OB
        
        Breaker = Opposite side of failed OB
        - Failed bullish OB → Bearish breaker
        - Failed bearish OB → Bullish breaker
        """
        # Opposite side
        breaker_side = 'sell' if failed_ob['side'] == 'buy' else 'buy'
        
        breaker = {
            'id': f"BREAKER_{failed_ob['id']}",
            'side': breaker_side,
            'price': current_price,
            'failed_ob_id': failed_ob['id'],
            'failed_ob_side': failed_ob['side'],
            'severity': severity,
            'proximal': failed_ob['distal'],  # Old distal becomes new proximal
            'distal': failed_ob['proximal'],  # Old proximal becomes new distal (flip range)
            'created_at': datetime.now(),
            'timeframe': failed_ob.get('timeframe', 'H1'),
            'status': 'active',
            'confidence': min(0.95, 0.7 + severity * 0.5)  # Higher severity = higher confidence
        }
        
        return breaker
    
    def get_breaker_signal(self, current_price: float, action: str) -> Optional[Dict[str, Any]]:
        """
        Check if there's a valid Breaker Block signal for intended action
        
        Args:
            current_price: Current market price
            action: 'BUY' or 'SELL'
            
        Returns:
            Breaker signal dict or None
        """
        for breaker in reversed(self.breakers):  # Most recent first
            if breaker['status'] != 'active':
                continue
            
            # Check if breaker side matches action
            if (breaker['side'] == 'buy' and action == 'BUY') or \
               (breaker['side'] == 'sell' and action == 'SELL'):
                
                # Check if price is near breaker zone
                proximal = breaker['proximal']
                distal = breaker['distal']
                
                in_zone = (min(proximal, distal) <= current_price <= max(proximal, distal))
                
                if in_zone:
                    return {
                        'type': 'breaker_block',
                        'side': breaker['side'],
                        'confidence': breaker['confidence'],
                        'price': breaker['price'],
                        'entry': current_price,
                        'sl': distal,  # Breaker invalid if price breaks distal again
                        'reasoning': f"Breaker Block from failed {breaker['failed_ob_side']} OB (severity: {breaker['severity']:.2%})"
                    }
        
        return None
    
    def should_block_ob_trade(self, ob_id: str) -> tuple[bool, str]:
        """
        Check if an OB has been invalidated (should NOT trade it)
        
        Returns: (should_block: bool, reason: str)
        """
        # Check if this OB is in invalidated list
        for ob in self.tracked_obs:
            if ob['id'] == ob_id and ob['status'] == 'invalidated':
                return True, f"Order Block {ob_id} has been invalidated (breaker formed)"
        
        return False, ""
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        return {
            'tracked_obs': len([ob for ob in self.tracked_obs if ob['status'] == 'active']),
            'invalidated_obs': len([ob for ob in self.tracked_obs if ob['status'] == 'invalidated']),
            'active_breakers': len([b for b in self.breakers if b['status'] == 'active']),
            'total_breakers': len(self.breakers)
        }


# Singleton instance
_breaker_block_ai = None

def get_breaker_block_ai(config: Optional[Dict[str, Any]] = None) -> BreakerBlockAI:
    """Get singleton instance"""
    global _breaker_block_ai
    if _breaker_block_ai is None:
        _breaker_block_ai = BreakerBlockAI(config)
    return _breaker_block_ai
