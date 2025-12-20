"""
SMC Entry Models Module
========================

Phân tích và quyết định entry dựa trên:
- Model 1: BOS + Retest
- Model 2: Liquidity Sweep + OB
- Model 3: FVG Entry
- Model 4: Multi-confluence SMC
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig

logger = logging.getLogger(__name__)


class EntryModelAI(SMCBase):
    """SMC Entry Decision Engine"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.default_rr = config.get('DEFAULT_RR', SMCConfig.DEFAULT_RR) if config else SMCConfig.DEFAULT_RR
        self.sl_buffer = config.get('SL_BUFFER', SMCConfig.SL_BUFFER) if config else SMCConfig.SL_BUFFER
        self.min_confluence = config.get('MIN_CONFLUENCE_SCORE', SMCConfig.MIN_CONFLUENCE_SCORE) if config else SMCConfig.MIN_CONFLUENCE_SCORE
        self.min_confidence = config.get('MIN_CONFIDENCE', SMCConfig.MIN_CONFIDENCE) if config else SMCConfig.MIN_CONFIDENCE
    
    def analyze(self, smc_data: Dict[str, Any], 
               df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích tất cả entry models
        
        Args:
            smc_data: Combined SMC analysis from all modules
            df: Current timeframe DataFrame
            
        Returns:
            dict: {
                'model_1_bos_retest': {
                    'valid': bool,
                    'signal': 'buy'/'sell'/None,
                    'entry': float,
                    'sl': float,
                    'tp': float,
                    'confidence': float
                },
                'model_2_sweep_ob': {...},
                'model_3_fvg': {...},
                'best_model': {
                    'name': str,
                    'signal': 'buy'/'sell'/None,
                    'entry': float,
                    'sl': float,
                    'tp': float,
                    'confidence': float,
                    'confluence_score': int
                }
            }
        """
        try:
            if not self.validate_dataframe(df):
                return self._empty_result()
            
            # Model 1: BOS + Retest
            model_1 = self._model_bos_retest(smc_data, df)
            
            # Model 2: Liquidity Sweep + OB
            model_2 = self._model_sweep_ob(smc_data, df)
            
            # Model 3: FVG Entry
            model_3 = self._model_fvg(smc_data, df)
            
            # Select best model
            best = self._select_best_model([model_1, model_2, model_3], smc_data)
            
            result = {
                'model_1_bos_retest': model_1,
                'model_2_sweep_ob': model_2,
                'model_3_fvg': model_3,
                'best_model': best,
                'timestamp': df.index[-1] if len(df) > 0 else datetime.now()
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ EntryModelAI error: {e}")
            return self._empty_result()
    
    def _model_bos_retest(self, smc_data: Dict, 
                         df: pd.DataFrame) -> Dict[str, Any]:
        """
        Model 1: BOS + Retest + OB
        
        Entry after BOS when price retests OB
        """
        try:
            structure = smc_data.get('market_structure', {})
            order_block = smc_data.get('order_block', {})
            pd_zone = smc_data.get('premium_discount', {})
            
            # Check BOS
            bos = structure.get('bos', False)
            bos_type = structure.get('bos_type')
            
            if not bos:
                return {'valid': False, 'signal': None}
            
            current_price = df['close'].iloc[-1]
            
            # Bullish BOS + retest
            if bos_type == 'bullish':
                bullish_ob = order_block.get('bullish_ob', {})
                
                if not bullish_ob.get('exists'):
                    return {'valid': False, 'signal': None}
                
                # Check if price near OB
                ob_high = bullish_ob['entry_high']
                ob_low = bullish_ob['entry_low']
                
                in_retest_zone = (current_price <= ob_high and 
                                 current_price >= ob_low)
                
                # Additional: check if in discount zone
                in_discount = pd_zone.get('zone') == 'discount'
                
                if in_retest_zone or (in_discount and current_price < ob_high * 1.02):
                    entry = (ob_low + ob_high) / 2
                    sl = ob_low * (1 - self.sl_buffer)
                    tp = entry + (entry - sl) * self.default_rr
                    
                    # Confidence
                    conf = 0.65
                    if in_discount:
                        conf += 0.1
                    if bullish_ob.get('strength', 0) > 0.7:
                        conf += 0.1
                    
                    logger.info(f"✅ Model 1 BUY: BOS + Retest @ {entry:.5f}")
                    return {
                        'valid': True,
                        'signal': 'buy',
                        'entry': entry,
                        'sl': sl,
                        'tp': tp,
                        'confidence': min(conf, 0.95)
                    }
            
            # Bearish BOS + retest
            elif bos_type == 'bearish':
                bearish_ob = order_block.get('bearish_ob', {})
                
                if not bearish_ob.get('exists'):
                    return {'valid': False, 'signal': None}
                
                ob_high = bearish_ob['entry_high']
                ob_low = bearish_ob['entry_low']
                
                in_retest_zone = (current_price >= ob_low and
                                 current_price <= ob_high)
                
                in_premium = pd_zone.get('zone') == 'premium'
                
                if in_retest_zone or (in_premium and current_price > ob_low * 0.98):
                    entry = (ob_low + ob_high) / 2
                    sl = ob_high * (1 + self.sl_buffer)
                    tp = entry - (sl - entry) * self.default_rr
                    
                    conf = 0.65
                    if in_premium:
                        conf += 0.1
                    if bearish_ob.get('strength', 0) > 0.7:
                        conf += 0.1
                    
                    logger.info(f"✅ Model 1 SELL: BOS + Retest @ {entry:.5f}")
                    return {
                        'valid': True,
                        'signal': 'sell',
                        'entry': entry,
                        'sl': sl,
                        'tp': tp,
                        'confidence': min(conf, 0.95)
                    }
            
            return {'valid': False, 'signal': None}
            
        except Exception as e:
            logger.error(f"❌ Model 1 error: {e}")
            return {'valid': False, 'signal': None}
    
    def _model_sweep_ob(self, smc_data: Dict,
                       df: pd.DataFrame) -> Dict[str, Any]:
        """
        Model 2: Liquidity Sweep + OB Rejection
        
        Entry after sweep when price rejects from OB
        """
        try:
            liquidity = smc_data.get('liquidity', {})
            order_block = smc_data.get('order_block', {})
            
            # Check sweep
            sweep = liquidity.get('sweep_detected', False)
            sweep_type = liquidity.get('sweep_type')
            
            if not sweep:
                return {'valid': False, 'signal': None}
            
            current_price = df['close'].iloc[-1]
            
            # Bullish sweep + OB
            if sweep_type == 'bullish':
                bullish_ob = order_block.get('bullish_ob', {})
                rejection = order_block.get('rejection_detected', False)
                rej_type = order_block.get('rejection_type')
                
                if bullish_ob.get('exists') and rejection and rej_type == 'bullish':
                    entry = bullish_ob['entry_high']
                    sl = bullish_ob['entry_low'] * (1 - self.sl_buffer)
                    tp = entry + (entry - sl) * self.default_rr
                    
                    conf = 0.70  # Higher confidence with sweep
                    if bullish_ob.get('strength', 0) > 0.7:
                        conf += 0.15
                    
                    logger.info(f"✅ Model 2 BUY: Sweep + OB @ {entry:.5f}")
                    return {
                        'valid': True,
                        'signal': 'buy',
                        'entry': entry,
                        'sl': sl,
                        'tp': tp,
                        'confidence': min(conf, 0.95)
                    }
            
            # Bearish sweep + OB
            elif sweep_type == 'bearish':
                bearish_ob = order_block.get('bearish_ob', {})
                rejection = order_block.get('rejection_detected', False)
                rej_type = order_block.get('rejection_type')
                
                if bearish_ob.get('exists') and rejection and rej_type == 'bearish':
                    entry = bearish_ob['entry_low']
                    sl = bearish_ob['entry_high'] * (1 + self.sl_buffer)
                    tp = entry - (sl - entry) * self.default_rr
                    
                    conf = 0.70
                    if bearish_ob.get('strength', 0) > 0.7:
                        conf += 0.15
                    
                    logger.info(f"✅ Model 2 SELL: Sweep + OB @ {entry:.5f}")
                    return {
                        'valid': True,
                        'signal': 'sell',
                        'entry': entry,
                        'sl': sl,
                        'tp': tp,
                        'confidence': min(conf, 0.95)
                    }
            
            return {'valid': False, 'signal': None}
            
        except Exception as e:
            logger.error(f"❌ Model 2 error: {e}")
            return {'valid': False, 'signal': None}
    
    def _model_fvg(self, smc_data: Dict,
                  df: pd.DataFrame) -> Dict[str, Any]:
        """
        Model 3: FVG Entry
        
        Entry when price enters FVG zone
        """
        try:
            fvg = smc_data.get('fvg', {})
            structure = smc_data.get('market_structure', {})
            
            entry_zone = fvg.get('entry_zone', {})
            zone_type = entry_zone.get('type')
            
            if not zone_type:
                return {'valid': False, 'signal': None}
            
            current_price = df['close'].iloc[-1]
            zone_low = entry_zone.get('low')
            zone_high = entry_zone.get('high')
            
            # Check if price in entry zone
            in_zone = (current_price >= zone_low and current_price <= zone_high)
            
            if not in_zone:
                return {'valid': False, 'signal': None}
            
            # Bullish FVG
            if zone_type == 'bullish':
                # Check structure alignment
                current_struct = structure.get('current_structure')
                aligned = current_struct == 'bullish'
                
                entry = (zone_low + zone_high) / 2
                
                # Get FVG details for SL
                bullish_fvg = fvg.get('bullish_fvg', {})
                gap_low = bullish_fvg.get('gap_low', zone_low)
                
                sl = gap_low * (1 - self.sl_buffer)
                tp = entry + (entry - sl) * self.default_rr
                
                conf = 0.60
                if aligned:
                    conf += 0.15
                
                logger.info(f"✅ Model 3 BUY: FVG Entry @ {entry:.5f}")
                return {
                    'valid': True,
                    'signal': 'buy',
                    'entry': entry,
                    'sl': sl,
                    'tp': tp,
                    'confidence': min(conf, 0.90)
                }
            
            # Bearish FVG
            elif zone_type == 'bearish':
                current_struct = structure.get('current_structure')
                aligned = current_struct == 'bearish'
                
                entry = (zone_low + zone_high) / 2
                
                bearish_fvg = fvg.get('bearish_fvg', {})
                gap_high = bearish_fvg.get('gap_high', zone_high)
                
                sl = gap_high * (1 + self.sl_buffer)
                tp = entry - (sl - entry) * self.default_rr
                
                conf = 0.60
                if aligned:
                    conf += 0.15
                
                logger.info(f"✅ Model 3 SELL: FVG Entry @ {entry:.5f}")
                return {
                    'valid': True,
                    'signal': 'sell',
                    'entry': entry,
                    'sl': sl,
                    'tp': tp,
                    'confidence': min(conf, 0.90)
                }
            
            return {'valid': False, 'signal': None}
            
        except Exception as e:
            logger.error(f"❌ Model 3 error: {e}")
            return {'valid': False, 'signal': None}
    
    def _select_best_model(self, models: List[Dict], 
                          smc_data: Dict) -> Dict[str, Any]:
        """
        Chọn model tốt nhất dựa trên:
        - Confluence score
        - Confidence
        - Risk/Reward
        """
        try:
            model_names = ['BOS_Retest', 'Sweep_OB', 'FVG']
            valid_models = []
            
            for i, model in enumerate(models):
                if model.get('valid') and model.get('signal'):
                    # Calculate confluence
                    confluence = self._calculate_confluence(model, smc_data)
                    
                    valid_models.append({
                        'name': model_names[i],
                        'signal': model['signal'],
                        'entry': model['entry'],
                        'sl': model['sl'],
                        'tp': model['tp'],
                        'confidence': model['confidence'],
                        'confluence_score': confluence
                    })
            
            if not valid_models:
                return {
                    'name': None,
                    'signal': None,
                    'entry': None,
                    'sl': None,
                    'tp': None,
                    'confidence': 0.0,
                    'confluence_score': 0
                }
            
            # Select model with highest confluence + confidence
            best = max(valid_models, 
                      key=lambda x: (x['confluence_score'], x['confidence']))
            
            # Validate minimum thresholds
            if best['confluence_score'] < self.min_confluence:
                logger.warning(f"⚠️ Confluence too low: {best['confluence_score']}")
                return {'name': None, 'signal': None}
            
            if best['confidence'] < self.min_confidence:
                logger.warning(f"⚠️ Confidence too low: {best['confidence']:.2f}")
                return {'name': None, 'signal': None}
            
            logger.info(f"🎯 Best Model: {best['name']} {best['signal'].upper()} "
                       f"@ {best['entry']:.5f} (Conf: {best['confidence']:.2f}, "
                       f"Confluence: {best['confluence_score']})")
            
            return best
            
        except Exception as e:
            logger.error(f"❌ Model selection error: {e}")
            return {'name': None, 'signal': None}
    
    def _calculate_confluence(self, model: Dict, smc_data: Dict) -> int:
        """
        Tính confluence score (số lượng factors hỗ trợ)
        
        Factors:
        - Market structure aligned
        - Premium/Discount zone correct
        - Liquidity support
        - Order block present
        - FVG support
        - Supply/Demand zone
        """
        score = 0
        signal = model.get('signal')
        
        try:
            structure = smc_data.get('market_structure', {})
            pd_zone = smc_data.get('premium_discount', {})
            liquidity = smc_data.get('liquidity', {})
            order_block = smc_data.get('order_block', {})
            fvg = smc_data.get('fvg', {})
            sd = smc_data.get('supply_demand', {})
            
            if signal == 'buy':
                # Factor 1: Bullish structure
                if structure.get('current_structure') == 'bullish':
                    score += 1
                
                # Factor 2: Discount zone
                if pd_zone.get('zone') == 'discount':
                    score += 1
                
                # Factor 3: Liquidity sweep bullish
                if liquidity.get('sweep_type') == 'bullish':
                    score += 1
                
                # Factor 4: Bullish OB
                if order_block.get('bullish_ob', {}).get('exists'):
                    score += 1
                
                # Factor 5: Bullish FVG
                if fvg.get('bullish_fvg', {}).get('exists'):
                    score += 1
                
                # Factor 6: Demand zone
                if sd.get('demand_zone', {}).get('exists'):
                    score += 1
            
            elif signal == 'sell':
                # Similar for sell
                if structure.get('current_structure') == 'bearish':
                    score += 1
                if pd_zone.get('zone') == 'premium':
                    score += 1
                if liquidity.get('sweep_type') == 'bearish':
                    score += 1
                if order_block.get('bearish_ob', {}).get('exists'):
                    score += 1
                if fvg.get('bearish_fvg', {}).get('exists'):
                    score += 1
                if sd.get('supply_zone', {}).get('exists'):
                    score += 1
            
            return score
            
        except Exception as e:
            return 0
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result"""
        return {
            'model_1_bos_retest': {'valid': False, 'signal': None},
            'model_2_sweep_ob': {'valid': False, 'signal': None},
            'model_3_fvg': {'valid': False, 'signal': None},
            'best_model': {
                'name': None,
                'signal': None,
                'entry': None,
                'sl': None,
                'tp': None,
                'confidence': 0.0,
                'confluence_score': 0
            },
            'timestamp': datetime.now()
        }
