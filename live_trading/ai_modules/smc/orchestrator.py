"""
SMC Orchestrator
================

Central coordinator for all SMC modules.
Manages multi-timeframe analysis and signal fusion.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

from .base import SMCBase
from .config import SMCConfig
from .market_structure import MarketStructureAI
from .liquidity import LiquidityAI
from .order_block import OrderBlockAI
from .fvg import FVGDetector
from .supply_demand import SupplyDemandAI
from .premium_discount import PremiumDiscountAI
from .internal_structure import InternalStructureAI
from .entry_models import EntryModelAI

logger = logging.getLogger(__name__)


class SMCOrchestrator:
    """
    SMC Orchestrator - Điều phối toàn bộ SMC system
    
    Multi-timeframe workflow:
    1. HTF (H1/H4): Xác định bias tổng thể
    2. MTF (M15): Xác nhận structure
    3. LTF (M5/M1): Precision entry
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize SMC Orchestrator
        
        Args:
            config: Configuration dictionary (optional)
        """
        self.config = config or {}
        
        # Initialize all modules
        logger.info("🚀 Initializing SMC Orchestrator...")
        
        self.market_structure = MarketStructureAI(config)
        self.liquidity = LiquidityAI(config)
        self.order_block = OrderBlockAI(config)
        self.fvg = FVGDetector(config)
        self.supply_demand = SupplyDemandAI(config)
        self.premium_discount = PremiumDiscountAI(config)
        self.internal_structure = InternalStructureAI(config)
        self.entry_models = EntryModelAI(config)
        
        logger.info("✅ SMC Orchestrator initialized")
        
    def analyze_full(self, 
                    df_htf: pd.DataFrame,
                    df_mtf: pd.DataFrame,
                    df_ltf: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích FULL multi-timeframe SMC
        
        Args:
            df_htf: Higher timeframe (H1/H4)
            df_mtf: Medium timeframe (M15)
            df_ltf: Lower timeframe (M5/M1)
            
        Returns:
            dict: Complete SMC analysis với entry signal
        """
        try:
            logger.info("=" * 60)
            logger.info("🎯 SMC FULL ANALYSIS STARTING")
            logger.info("=" * 60)
            
            # Step 1: HTF Analysis (Bias)
            logger.info("📊 Step 1: HTF Analysis...")
            htf_analysis = self._analyze_timeframe(df_htf, 'HTF')
            htf_bias = htf_analysis['market_structure']['current_structure']
            
            logger.info(f"HTF Bias: {htf_bias.upper()}")
            
            # Step 2: MTF Analysis (Confirmation)
            logger.info("📊 Step 2: MTF Analysis...")
            mtf_analysis = self._analyze_timeframe(df_mtf, 'MTF')
            mtf_structure = mtf_analysis['market_structure']['current_structure']
            
            logger.info(f"MTF Structure: {mtf_structure.upper()}")
            
            # Step 3: LTF Analysis (Entry)
            logger.info("📊 Step 3: LTF Analysis...")
            ltf_analysis = self._analyze_timeframe(df_ltf, 'LTF')
            
            # Step 4: Internal Structure (Precision)
            logger.info("📊 Step 4: Internal Structure...")
            internal = self.internal_structure.analyze(df_ltf, htf_bias)
            
            # Step 5: Entry Models
            logger.info("📊 Step 5: Entry Models Evaluation...")
            entry_decision = self.entry_models.analyze(ltf_analysis, df_ltf)
            
            # Step 6: Multi-timeframe alignment check
            alignment = self._check_mtf_alignment(
                htf_bias, mtf_structure, internal
            )
            
            # Step 7: Final signal
            final_signal = self._generate_final_signal(
                entry_decision, alignment, htf_analysis, ltf_analysis
            )
            
            logger.info("=" * 60)
            logger.info(f"🎯 FINAL SIGNAL: {final_signal['signal']}")
            logger.info(f"💪 Confidence: {final_signal['confidence']:.2%}")
            logger.info(f"🔗 Confluence: {final_signal['confluence_score']}/6")
            logger.info("=" * 60)
            
            return {
                'htf_analysis': htf_analysis,
                'mtf_analysis': mtf_analysis,
                'ltf_analysis': ltf_analysis,
                'internal_structure': internal,
                'entry_decision': entry_decision,
                'alignment': alignment,
                'final_signal': final_signal,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"❌ SMC Orchestrator error: {e}")
            return self._empty_result()
    
    def analyze_single_timeframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Phân tích SINGLE timeframe (nhanh hơn)
        
        Args:
            df: DataFrame với OHLCV data
            
        Returns:
            dict: SMC analysis cho timeframe này
        """
        try:
            logger.info("🎯 Single Timeframe SMC Analysis")
            
            analysis = self._analyze_timeframe(df, 'SINGLE')
            entry_decision = self.entry_models.analyze(analysis, df)
            
            final_signal = {
                'signal': entry_decision['best_model']['signal'],
                'entry': entry_decision['best_model']['entry'],
                'sl': entry_decision['best_model']['sl'],
                'tp': entry_decision['best_model']['tp'],
                'confidence': entry_decision['best_model']['confidence'],
                'confluence_score': entry_decision['best_model']['confluence_score'],
                'model': entry_decision['best_model']['name']
            }
            
            return {
                'analysis': analysis,
                'entry_decision': entry_decision,
                'final_signal': final_signal,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"❌ Single TF analysis error: {e}")
            return self._empty_result()
    
    def _analyze_timeframe(self, df: pd.DataFrame, 
                          tf_name: str) -> Dict[str, Any]:
        """
        Phân tích một timeframe với tất cả modules
        
        Args:
            df: DataFrame
            tf_name: Timeframe name for logging
            
        Returns:
            dict: Combined analysis từ tất cả modules
        """
        try:
            logger.debug(f"Analyzing {tf_name}...")
            
            # Run all modules
            ms = self.market_structure.analyze(df)
            liq = self.liquidity.analyze(df)
            ob = self.order_block.analyze(df)
            fvg_result = self.fvg.analyze(df)
            sd = self.supply_demand.analyze(df)
            pd_zone = self.premium_discount.analyze(df)
            
            return {
                'market_structure': ms,
                'liquidity': liq,
                'order_block': ob,
                'fvg': fvg_result,
                'supply_demand': sd,
                'premium_discount': pd_zone,
                'timeframe': tf_name
            }
            
        except Exception as e:
            logger.error(f"❌ Timeframe analysis error: {e}")
            return {}
    
    def _check_mtf_alignment(self, htf_bias: str,
                            mtf_structure: str,
                            internal: Dict) -> Dict[str, Any]:
        """
        Kiểm tra multi-timeframe alignment
        
        Returns:
            dict: {
                'aligned': bool,
                'htf_mtf_match': bool,
                'ltf_confirms': bool,
                'score': float  # 0-1
            }
        """
        try:
            score = 0.0
            
            # HTF-MTF alignment (0.4)
            htf_mtf_match = (htf_bias == mtf_structure and 
                            htf_bias != 'sideways')
            if htf_mtf_match:
                score += 0.4
            
            # LTF confirms HTF (0.3)
            ltf_confirms = internal.get('entry_valid', False)
            if ltf_confirms:
                score += 0.3
            
            # LTF trend quality (0.3)
            ltf_trend = internal.get('ltf_trend')
            ema_aligned = internal.get('ema_alignment', False)
            
            if ltf_trend == htf_bias and ema_aligned:
                score += 0.3
            elif ltf_trend == htf_bias:
                score += 0.15
            
            aligned = score >= 0.7  # Threshold 70%
            
            return {
                'aligned': aligned,
                'htf_mtf_match': htf_mtf_match,
                'ltf_confirms': ltf_confirms,
                'score': score
            }
            
        except Exception as e:
            logger.error(f"❌ Alignment check error: {e}")
            return {
                'aligned': False,
                'htf_mtf_match': False,
                'ltf_confirms': False,
                'score': 0.0
            }
    
    def _generate_final_signal(self, entry_decision: Dict,
                              alignment: Dict,
                              htf_analysis: Dict,
                              ltf_analysis: Dict) -> Dict[str, Any]:
        """
        Tạo final trading signal
        
        Combines:
        - Entry model decision
        - Multi-timeframe alignment
        - Risk management
        """
        try:
            best_model = entry_decision.get('best_model', {})
            
            # No valid model
            if not best_model.get('signal'):
                return {
                    'signal': None,
                    'entry': None,
                    'sl': None,
                    'tp': None,
                    'confidence': 0.0,
                    'confluence_score': 0,
                    'model': None,
                    'reason': 'No valid entry model'
                }
            
            # Check alignment
            if not alignment.get('aligned'):
                logger.warning("⚠️ Multi-timeframe NOT aligned")
                # Reduce confidence
                confidence = best_model['confidence'] * 0.7
                
                # Still allow if confluence high
                if best_model['confluence_score'] < 4:
                    return {
                        'signal': None,
                        'reason': 'MTF misalignment, low confluence'
                    }
            else:
                confidence = best_model['confidence']
                # Boost confidence if aligned
                confidence = min(confidence * 1.1, 0.98)
            
            # Check premium/discount alignment
            pd_zone = ltf_analysis.get('premium_discount', {})
            zone = pd_zone.get('zone')
            signal = best_model['signal']
            
            # BUY in premium = risky
            if signal == 'buy' and zone == 'premium':
                logger.warning("⚠️ BUY in premium zone")
                confidence *= 0.85
            
            # SELL in discount = risky
            elif signal == 'sell' and zone == 'discount':
                logger.warning("⚠️ SELL in discount zone")
                confidence *= 0.85
            
            # Final confidence check
            if confidence < SMCConfig.MIN_CONFIDENCE:
                return {
                    'signal': None,
                    'reason': f'Confidence too low: {confidence:.2f}'
                }
            
            return {
                'signal': signal,
                'entry': best_model['entry'],
                'sl': best_model['sl'],
                'tp': best_model['tp'],
                'confidence': confidence,
                'confluence_score': best_model['confluence_score'],
                'model': best_model['name'],
                'alignment_score': alignment['score'],
                'reason': 'Valid SMC setup'
            }
            
        except Exception as e:
            logger.error(f"❌ Final signal generation error: {e}")
            return {'signal': None, 'reason': f'Error: {e}'}
    
    def get_smc_report(self, analysis: Dict) -> str:
        """
        Tạo human-readable SMC report
        
        Args:
            analysis: Result từ analyze_full() hoặc analyze_single_timeframe()
            
        Returns:
            str: Formatted report
        """
        try:
            report = []
            report.append("\n" + "=" * 60)
            report.append("📊 SMC ANALYSIS REPORT")
            report.append("=" * 60)
            
            # Final Signal
            final = analysis.get('final_signal', {})
            signal = final.get('signal', 'NONE')
            
            report.append(f"\n🎯 SIGNAL: {signal}")
            if signal:
                report.append(f"   Entry: {final.get('entry', 'N/A')}")
                report.append(f"   SL: {final.get('sl', 'N/A')}")
                report.append(f"   TP: {final.get('tp', 'N/A')}")
                report.append(f"   Confidence: {final.get('confidence', 0):.1%}")
                report.append(f"   Confluence: {final.get('confluence_score', 0)}/6")
                report.append(f"   Model: {final.get('model', 'N/A')}")
            else:
                report.append(f"   Reason: {final.get('reason', 'Unknown')}")
            
            # Market Structure
            if 'ltf_analysis' in analysis:
                ms = analysis['ltf_analysis'].get('market_structure', {})
                report.append(f"\n📈 MARKET STRUCTURE:")
                report.append(f"   Current: {ms.get('current_structure', 'N/A').upper()}")
                report.append(f"   BOS: {ms.get('bos', False)} ({ms.get('bos_type', 'N/A')})")
                report.append(f"   CHoCH: {ms.get('choch', False)} ({ms.get('choch_type', 'N/A')})")
                report.append(f"   Quality: {ms.get('structure_quality', 0):.1%}")
            
            # Liquidity
            if 'ltf_analysis' in analysis:
                liq = analysis['ltf_analysis'].get('liquidity', {})
                report.append(f"\n💧 LIQUIDITY:")
                report.append(f"   Sweep: {liq.get('sweep_detected', False)} ({liq.get('sweep_type', 'N/A')})")
                report.append(f"   Stop Hunt: {liq.get('stop_hunt', False)} ({liq.get('hunt_type', 'N/A')})")
                liq_map = liq.get('liquidity_map', {})
                report.append(f"   Buy-side: {liq_map.get('buy_side', 'N/A')}")
                report.append(f"   Sell-side: {liq_map.get('sell_side', 'N/A')}")
            
            # Order Blocks
            if 'ltf_analysis' in analysis:
                ob = analysis['ltf_analysis'].get('order_block', {})
                bull_ob = ob.get('bullish_ob', {})
                bear_ob = ob.get('bearish_ob', {})
                report.append(f"\n📦 ORDER BLOCKS:")
                report.append(f"   Bullish: {bull_ob.get('exists', False)}")
                if bull_ob.get('exists'):
                    report.append(f"      Zone: {bull_ob.get('entry_low')} - {bull_ob.get('entry_high')}")
                    report.append(f"      Strength: {bull_ob.get('strength', 0):.1%}")
                report.append(f"   Bearish: {bear_ob.get('exists', False)}")
                if bear_ob.get('exists'):
                    report.append(f"      Zone: {bear_ob.get('entry_low')} - {bear_ob.get('entry_high')}")
                    report.append(f"      Strength: {bear_ob.get('strength', 0):.1%}")
            
            # Premium/Discount
            if 'ltf_analysis' in analysis:
                pd = analysis['ltf_analysis'].get('premium_discount', {})
                report.append(f"\n💰 PREMIUM/DISCOUNT:")
                report.append(f"   Zone: {pd.get('zone', 'N/A').upper()}")
                report.append(f"   Equilibrium: {pd.get('fib_50', 'N/A')}")
                report.append(f"   Deviation: {pd.get('current_deviation', 0):.2%}")
                report.append(f"   Recommendation: {pd.get('recommendation', 'N/A').upper()}")
            
            # Alignment
            if 'alignment' in analysis:
                align = analysis['alignment']
                report.append(f"\n🔗 MULTI-TIMEFRAME ALIGNMENT:")
                report.append(f"   Aligned: {align.get('aligned', False)}")
                report.append(f"   Score: {align.get('score', 0):.1%}")
                report.append(f"   HTF-MTF Match: {align.get('htf_mtf_match', False)}")
                report.append(f"   LTF Confirms: {align.get('ltf_confirms', False)}")
            
            report.append("\n" + "=" * 60)
            
            return "\n".join(report)
            
        except Exception as e:
            return f"❌ Report generation error: {e}"
    
    def _empty_result(self) -> Dict[str, Any]:
        """Return empty result"""
        return {
            'htf_analysis': {},
            'mtf_analysis': {},
            'ltf_analysis': {},
            'internal_structure': {},
            'entry_decision': {},
            'alignment': {'aligned': False, 'score': 0.0},
            'final_signal': {'signal': None, 'reason': 'Error'},
            'timestamp': datetime.now()
        }
