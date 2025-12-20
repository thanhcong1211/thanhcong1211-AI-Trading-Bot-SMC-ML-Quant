"""
Supply & Demand Zones AI Module
================================

Phát hiện và phân tích:
- Supply Zones (resistance, selling pressure)
- Demand Zones (support, buying pressure)
- Flip Zones (S→D, D→S)
- Zone Strength và Touch Count
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class SupplyDemandAI(SMCBase):
    """Supply & Demand Zone Detection"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.lookback = config.get('SD_LOOKBACK', SMCConfig.SD_LOOKBACK) if config else SMCConfig.SD_LOOKBACK
        self.strength_bars = config.get('SD_STRENGTH_BARS', SMCConfig.SD_STRENGTH_BARS) if config else SMCConfig.SD_STRENGTH_BARS
        self.vol_mult = config.get('SD_VOLUME_MULTIPLIER', SMCConfig.SD_VOLUME_MULTIPLIER) if config else SMCConfig.SD_VOLUME_MULTIPLIER
        self.flip_conf = config.get('FLIP_ZONE_CONFIRMATION', SMCConfig.FLIP_ZONE_CONFIRMATION) if config else SMCConfig.FLIP_ZONE_CONFIRMATION
        
        self.supply_zones = []  # [(time, low, high, strength, touches)]
        self.demand_zones = []
        self.flip_zones = []  # Zones that flipped
    
    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích Supply & Demand zones
        
        Args:
            df: DataFrame with OHLCV data
            
        Returns:
            dict: {
                'supply_zone': {
                    'exists': bool,
                    'low': float,
                    'high': float,
                    'strength': float,  # 0-1
                    'touches': int
                },
                'demand_zone': {
                    'exists': bool,
                    'low': float,
                    'high': float,
                    'strength': float,
                    'touches': int
                },
                'flip_zone': {
                    'detected': bool,
                    'type': 'supply_to_demand'/'demand_to_supply'/None,
                    'low': float,
                    'high': float
                },
                'nearest_zone': {
                    'type': 'supply'/'demand'/None,
                    'distance': float  # % from price
                }
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Detect new zones
            self._detect_zones(df)
            
            # Update touch counts
            self._update_touches(df)
            
            # Detect flip zones
            flip = self._detect_flip_zones(df)
            
            # Get active zones
            supply = self._get_nearest_supply(df)
            demand = self._get_nearest_demand(df)
            
            # Find nearest zone
            nearest = self._find_nearest_zone(df, supply, demand)
            
            result = {
                'supply_zone': supply,
                'demand_zone': demand,
                'flip_zone': flip,
                'nearest_zone': nearest,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"❌ SupplyDemandAI error: {e}")
            return self._empty_result()
    
    def _detect_zones(self, df: pd.DataFrame):
        """
        Phát hiện Supply/Demand zones mới
        
        Zone criteria:
        - Strong move away from zone (supply: drop, demand: rally)
        - High volume base
        - Clean break with minimal retrace
        """
        try:
            if len(df) < 50:
                return
            
            avg_volume = df['volume'].rolling(20).mean()
            
            # Scan for zones
            for i in range(-50, -5):
                try:
                    # Check for supply zone (resistance)
                    if self._is_supply_zone(df, i, avg_volume):
                        zone_low = df.iloc[i]['low']
                        zone_high = df.iloc[i]['high']
                        strength = self._calculate_zone_strength(df, i, 'supply')
                        
                        if not self._zone_exists(zone_low, zone_high, 'supply'):
                            self.supply_zones.append((
                                df.iloc[i].name,
                                zone_low,
                                zone_high,
                                strength,
                                0  # Initial touches
                            ))
                            logger.debug(f"🔴 Supply zone @ {zone_low:.5f}-{zone_high:.5f}")
                    
                    # Check for demand zone (support)
                    if self._is_demand_zone(df, i, avg_volume):
                        zone_low = df.iloc[i]['low']
                        zone_high = df.iloc[i]['high']
                        strength = self._calculate_zone_strength(df, i, 'demand')
                        
                        if not self._zone_exists(zone_low, zone_high, 'demand'):
                            self.demand_zones.append((
                                df.iloc[i].name,
                                zone_low,
                                zone_high,
                                strength,
                                0
                            ))
                            logger.debug(f"🟢 Demand zone @ {zone_low:.5f}-{zone_high:.5f}")
                
                except Exception as e:
                    continue
            
            # Keep only recent zones
            self.supply_zones = self.supply_zones[-20:]
            self.demand_zones = self.demand_zones[-20:]
            
        except Exception as e:
            logger.error(f"❌ Zone detection error: {e}")
    
    def _is_supply_zone(self, df: pd.DataFrame, 
                       index: int, avg_volume: pd.Series) -> bool:
        """
        Check if area is supply zone
        
        Criteria:
        - Price consolidated then dropped sharply
        - High volume during consolidation
        """
        try:
            if index >= -self.strength_bars:
                return False
            
            candle = df.iloc[index]
            next_bars = df.iloc[index+1:index+1+self.strength_bars]
            
            # Volume check
            high_volume = candle['volume'] > avg_volume.iloc[index] * self.vol_mult
            
            # Strong drop after
            drop = candle['low'] - next_bars['low'].min()
            drop_pct = drop / candle['close'] if candle['close'] > 0 else 0
            
            strong_drop = drop_pct > 0.005  # 0.5% drop
            
            return high_volume and strong_drop
            
        except Exception as e:
            return False
    
    def _is_demand_zone(self, df: pd.DataFrame,
                       index: int, avg_volume: pd.Series) -> bool:
        """
        Check if area is demand zone
        
        Criteria:
        - Price consolidated then rallied sharply
        - High volume during consolidation
        """
        try:
            if index >= -self.strength_bars:
                return False
            
            candle = df.iloc[index]
            next_bars = df.iloc[index+1:index+1+self.strength_bars]
            
            # Volume check
            high_volume = candle['volume'] > avg_volume.iloc[index] * self.vol_mult
            
            # Strong rally after
            rally = next_bars['high'].max() - candle['high']
            rally_pct = rally / candle['close'] if candle['close'] > 0 else 0
            
            strong_rally = rally_pct > 0.005  # 0.5% rally
            
            return high_volume and strong_rally
            
        except Exception as e:
            return False
    
    def _zone_exists(self, zone_low: float, zone_high: float, 
                    zone_type: str) -> bool:
        """Check if zone already exists"""
        zones = self.supply_zones if zone_type == 'supply' else self.demand_zones
        
        for _, low, high, _, _ in zones:
            # Check overlap
            if (zone_low <= high and zone_high >= low):
                return True
        return False
    
    def _calculate_zone_strength(self, df: pd.DataFrame,
                                 index: int, zone_type: str) -> float:
        """
        Tính strength của zone (0-1)
        
        Factors:
        - Volume
        - Move size away from zone
        - Clean break (minimal retrace)
        """
        try:
            score = 0.0
            candle = df.iloc[index]
            
            # Factor 1: Volume (0-0.4)
            avg_vol = df['volume'].rolling(20).mean().iloc[index]
            if avg_vol > 0:
                vol_ratio = candle['volume'] / avg_vol
                score += min(0.4, 0.4 * (vol_ratio / 2.0))
            
            # Factor 2: Move size (0-0.4)
            if index < -self.strength_bars:
                next_bars = df.iloc[index+1:index+1+self.strength_bars]
                
                if zone_type == 'supply':
                    move = candle['low'] - next_bars['low'].min()
                else:
                    move = next_bars['high'].max() - candle['high']
                
                move_pct = move / candle['close'] if candle['close'] > 0 else 0
                score += min(0.4, 0.4 * (move_pct / 0.01))  # Normalize to 1%
            
            # Factor 3: Clean break (0-0.2)
            # Check if price didn't retrace much
            if index < -self.strength_bars:
                if zone_type == 'supply':
                    retrace = next_bars['high'].max() - candle['high']
                else:
                    retrace = candle['low'] - next_bars['low'].min()
                
                retrace_pct = retrace / candle['close'] if candle['close'] > 0 else 0
                if retrace_pct < 0.002:  # Less than 0.2% retrace
                    score += 0.2
            
            return min(score, 1.0)
            
        except Exception as e:
            return 0.5
    
    def _update_touches(self, df: pd.DataFrame):
        """Update touch counts when price revisits zones"""
        try:
            current = df.iloc[-1]
            current_high = current['high']
            current_low = current['low']
            
            # Update supply zones
            for i, (time, low, high, strength, touches) in enumerate(self.supply_zones):
                # Check if price touched zone
                if current_high >= low and current_low <= high:
                    self.supply_zones[i] = (time, low, high, strength, touches + 1)
            
            # Update demand zones
            for i, (time, low, high, strength, touches) in enumerate(self.demand_zones):
                if current_high >= low and current_low <= high:
                    self.demand_zones[i] = (time, low, high, strength, touches + 1)
                    
        except Exception as e:
            logger.error(f"❌ Touch update error: {e}")
    
    def _detect_flip_zones(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phát hiện flip zones
        
        Flip = Supply zone becomes demand (or vice versa)
        """
        try:
            current_price = df['close'].iloc[-1]
            
            # Check supply → demand flip
            for time, low, high, strength, touches in self.supply_zones:
                if touches >= self.flip_conf:
                    # If price breaks above and holds
                    if current_price > high:
                        logger.info(f"🔄 Supply→Demand flip @ {low:.5f}-{high:.5f}")
                        return {
                            'detected': True,
                            'type': 'supply_to_demand',
                            'low': low,
                            'high': high
                        }
            
            # Check demand → supply flip
            for time, low, high, strength, touches in self.demand_zones:
                if touches >= self.flip_conf:
                    # If price breaks below and holds
                    if current_price < low:
                        logger.info(f"🔄 Demand→Supply flip @ {low:.5f}-{high:.5f}")
                        return {
                            'detected': True,
                            'type': 'demand_to_supply',
                            'low': low,
                            'high': high
                        }
            
            return {'detected': False, 'type': None, 'low': None, 'high': None}
            
        except Exception as e:
            return {'detected': False, 'type': None, 'low': None, 'high': None}
    
    def _get_nearest_supply(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Lấy supply zone gần nhất"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Filter zones above price
            valid = [
                (time, low, high, strength, touches)
                for time, low, high, strength, touches in self.supply_zones
                if low > current_price and touches < 3  # Max 3 touches
            ]
            
            if not valid:
                return {'exists': False}
            
            # Get nearest
            nearest = min(valid, key=lambda x: x[1])
            
            return {
                'exists': True,
                'low': nearest[1],
                'high': nearest[2],
                'strength': nearest[3],
                'touches': nearest[4]
            }
            
        except Exception as e:
            return {'exists': False}
    
    def _get_nearest_demand(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Lấy demand zone gần nhất"""
        try:
            current_price = df['close'].iloc[-1]
            
            # Filter zones below price
            valid = [
                (time, low, high, strength, touches)
                for time, low, high, strength, touches in self.demand_zones
                if high < current_price and touches < 3
            ]
            
            if not valid:
                return {'exists': False}
            
            # Get nearest
            nearest = max(valid, key=lambda x: x[2])
            
            return {
                'exists': True,
                'low': nearest[1],
                'high': nearest[2],
                'strength': nearest[3],
                'touches': nearest[4]
            }
            
        except Exception as e:
            return {'exists': False}
    
    def _find_nearest_zone(self, df: pd.DataFrame,
                          supply: Dict, demand: Dict) -> Dict[str, Any]:
        """Tìm zone gần nhất"""
        try:
            current_price = df['close'].iloc[-1]
            
            nearest = {'type': None, 'distance': float('inf')}
            
            if supply['exists']:
                dist = (supply['low'] - current_price) / current_price
                if dist < nearest['distance']:
                    nearest = {'type': 'supply', 'distance': dist}
            
            if demand['exists']:
                dist = (current_price - demand['high']) / current_price
                if dist < nearest['distance']:
                    nearest = {'type': 'demand', 'distance': dist}
            
            return nearest
            
        except Exception as e:
            return {'type': None, 'distance': float('inf')}
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result on error"""
        return {
            'supply_zone': {'exists': False},
            'demand_zone': {'exists': False},
            'flip_zone': {'detected': False, 'type': None, 'low': None, 'high': None},
            'nearest_zone': {'type': None, 'distance': float('inf')},
            'timestamp': datetime.now()
        }
