"""
Trade Quality Scoring Module
=============================

Chấm điểm chất lượng tín hiệu từ 0-100 dựa trên:
- SMC Structure (25 điểm)
- Liquidity Sweep (20 điểm)  
- Regime Match (20 điểm)
- Quant Probability (20 điểm)
- Volatility OK (15 điểm)

Ngưỡng: >= 65 điểm mới cho vào lệnh
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class TradeQualityScorer:
    """
    Đánh giá chất lượng tín hiệu trading từ 0-100 điểm
    
    Scoring breakdown:
    - SMC Structure: 25 pts (OB + FVG + Structure break)
    - Liquidity Sweep: 20 pts (Equal H/L swept, stop hunt)
    - Regime Match: 20 pts (Signal align với market regime)
    - Quant Probability: 20 pts (TrendAI + FusionAI confidence)
    - Volatility Condition: 15 pts (Volatility thích hợp, không extreme)
    """
    
    def __init__(self, min_quality_score: float = 65.0):
        """
        Args:
            min_quality_score: Ngưỡng tối thiểu để accept trade (0-100)
        """
        self.min_quality_score = min_quality_score
        logger.info(f"✅ TradeQualityScorer initialized (min_score={min_quality_score})")
    
    def score_signal(self, signal: Dict[str, Any]) -> Dict[str, Any]:
        """
        Chấm điểm tổng thể cho tín hiệu
        
        Args:
            signal: Dictionary chứa tất cả thông tin signal
            
        Returns:
            {
                'total_score': float (0-100),
                'breakdown': {
                    'smc': float,
                    'liquidity': float,
                    'regime': float,
                    'probability': float,
                    'volatility': float
                },
                'should_trade': bool,
                'rating': str  # 'EXCELLENT', 'GOOD', 'FAIR', 'POOR'
            }
        """
        try:
            # 1. SMC Structure Score (0-25)
            smc_score = self._score_smc(signal)
            
            # 2. Liquidity Score (0-20)
            liquidity_score = self._score_liquidity(signal)
            
            # 3. Regime Match Score (0-20)
            regime_score = self._score_regime(signal)
            
            # 4. Quant Probability Score (0-20)
            probability_score = self._score_probability(signal)
            
            # 5. Volatility Condition Score (0-15)
            volatility_score = self._score_volatility(signal)
            
            # Total
            total_score = smc_score + liquidity_score + regime_score + probability_score + volatility_score
            
            # Rating
            rating = self._get_rating(total_score)
            
            # Should trade?
            should_trade = total_score >= self.min_quality_score
            
            result = {
                'total_score': round(total_score, 2),
                'breakdown': {
                    'smc': round(smc_score, 2),
                    'liquidity': round(liquidity_score, 2),
                    'regime': round(regime_score, 2),
                    'probability': round(probability_score, 2),
                    'volatility': round(volatility_score, 2)
                },
                'should_trade': should_trade,
                'rating': rating
            }
            
            # Log kết quả
            logger.info(f"📊 Trade Quality Score: {total_score:.1f}/100 - {rating}")
            logger.info(f"   SMC: {smc_score:.1f}/25 | Liquidity: {liquidity_score:.1f}/20 | "
                       f"Regime: {regime_score:.1f}/20 | Prob: {probability_score:.1f}/20 | "
                       f"Vol: {volatility_score:.1f}/15")
            logger.info(f"   ➜ {'✅ ACCEPT' if should_trade else '❌ REJECT'} (threshold: {self.min_quality_score})")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Trade quality scoring failed: {e}")
            # Fallback: return neutral score
            return {
                'total_score': 50.0,
                'breakdown': {'smc': 12.5, 'liquidity': 10, 'regime': 10, 'probability': 10, 'volatility': 7.5},
                'should_trade': False,
                'rating': 'FAIR',
                'error': str(e)
            }
    
    def _score_smc(self, signal: Dict[str, Any]) -> float:
        """
        Score SMC structure quality (0-25 điểm)
        
        Criteria:
        - Order Block detected: +10
        - FVG detected: +8
        - Structure break confirmed: +7
        """
        score = 0.0
        
        try:
            # Check OB
            smc_data = signal.get('smc_data', {})
            ob_detected = smc_data.get('order_block', {}).get('detected', False)
            if ob_detected:
                score += 10.0
                logger.debug("   ✅ Order Block detected (+10)")
            
            # Check FVG
            fvg_detected = smc_data.get('fvg', {}).get('detected', False)
            if fvg_detected:
                score += 8.0
                logger.debug("   ✅ FVG detected (+8)")
            
            # Check Structure break
            structure = smc_data.get('structure', {})
            structure_type = structure.get('type', 'unknown')
            if structure_type in ['uptrend', 'downtrend', 'break_high', 'break_low']:
                score += 7.0
                logger.debug(f"   ✅ Structure: {structure_type} (+7)")
            
        except Exception as e:
            logger.debug(f"   ⚠️ SMC scoring error: {e}")
        
        return min(score, 25.0)
    
    def _score_liquidity(self, signal: Dict[str, Any]) -> float:
        """
        Score liquidity sweep quality (0-20 điểm)
        
        Criteria:
        - Liquidity sweep detected: +12
        - Stop hunt detected: +8
        - Equal H/L nearby: +5
        """
        score = 0.0
        
        try:
            liquidity_data = signal.get('liquidity_sweep_ai', {})
            
            # Liquidity sweep
            sweep_detected = liquidity_data.get('sweep_detected', False)
            if sweep_detected:
                score += 12.0
                logger.debug("   ✅ Liquidity sweep (+12)")
            
            # Stop hunt
            stop_hunt = liquidity_data.get('stop_hunt', False)
            if stop_hunt:
                score += 8.0
                logger.debug("   ✅ Stop hunt detected (+8)")
            
            # Equal highs/lows
            equal_highs = liquidity_data.get('equal_highs', [])
            equal_lows = liquidity_data.get('equal_lows', [])
            if equal_highs or equal_lows:
                score += 5.0
                logger.debug("   ✅ Equal H/L detected (+5)")
                
        except Exception as e:
            logger.debug(f"   ⚠️ Liquidity scoring error: {e}")
        
        return min(score, 20.0)
    
    def _score_regime(self, signal: Dict[str, Any]) -> float:
        """
        Score regime alignment (0-20 điểm)
        
        Criteria:
        - Signal direction matches regime: +15
        - Regime strength high: +5
        """
        score = 0.0
        
        try:
            action = signal.get('action', 'NONE')
            regime_data = signal.get('regime', {})
            
            # Get regime type
            regime_type = regime_data.get('type', 'unknown')
            regime_direction = regime_data.get('direction', 'neutral')
            
            # Check alignment
            if action == 'BUY' and regime_direction in ['bullish', 'uptrend']:
                score += 15.0
                logger.debug(f"   ✅ BUY aligns with {regime_type} regime (+15)")
            elif action == 'SELL' and regime_direction in ['bearish', 'downtrend']:
                score += 15.0
                logger.debug(f"   ✅ SELL aligns with {regime_type} regime (+15)")
            elif regime_type in ['breakout', 'volatility']:
                score += 10.0  # Partial score for breakout
                logger.debug(f"   ⚠️ Breakout regime (partial +10)")
            
            # Regime strength
            regime_strength = regime_data.get('strength', 0.0)
            if regime_strength >= 0.7:
                score += 5.0
                logger.debug(f"   ✅ High regime strength {regime_strength:.2f} (+5)")
            elif regime_strength >= 0.5:
                score += 2.5
                
        except Exception as e:
            logger.debug(f"   ⚠️ Regime scoring error: {e}")
        
        return min(score, 20.0)
    
    def _score_probability(self, signal: Dict[str, Any]) -> float:
        """
        Score quant AI probability (0-20 điểm)
        
        Criteria:
        - Based on TrendAI + FusionAI confidence
        - >= 80%: 20 pts
        - >= 70%: 15 pts
        - >= 60%: 10 pts
        - < 60%: 5 pts
        """
        score = 0.0
        
        try:
            # Get confidence (as percentage 0-100)
            confidence = signal.get('confidence', 0.0)
            
            if confidence >= 80.0:
                score = 20.0
                logger.debug(f"   ✅ Excellent confidence {confidence:.1f}% (+20)")
            elif confidence >= 70.0:
                score = 15.0
                logger.debug(f"   ✅ Good confidence {confidence:.1f}% (+15)")
            elif confidence >= 60.0:
                score = 10.0
                logger.debug(f"   ⚠️ Fair confidence {confidence:.1f}% (+10)")
            else:
                score = 5.0
                logger.debug(f"   ❌ Low confidence {confidence:.1f}% (+5)")
                
        except Exception as e:
            logger.debug(f"   ⚠️ Probability scoring error: {e}")
        
        return score
    
    def _score_volatility(self, signal: Dict[str, Any]) -> float:
        """
        Score volatility condition (0-15 điểm)
        
        Criteria:
        - Normal volatility (optimal): +15
        - Low volatility: +10
        - High volatility: +8
        - Extreme volatility: +3 (dangerous)
        """
        score = 0.0
        
        try:
            volatility_data = signal.get('volatility', {})
            
            # Get volatility level
            vol_level = volatility_data.get('level', 'unknown')
            vol_forecast = volatility_data.get('forecast', {})
            risk_level = vol_forecast.get('risk_level', 'MEDIUM')
            
            if risk_level == 'LOW' or vol_level == 'normal':
                score = 15.0
                logger.debug("   ✅ Normal volatility (+15)")
            elif risk_level == 'MEDIUM' or vol_level == 'low':
                score = 10.0
                logger.debug("   ✅ Low volatility (+10)")
            elif risk_level == 'HIGH' or vol_level == 'high':
                score = 8.0
                logger.debug("   ⚠️ High volatility (+8)")
            else:  # EXTREME
                score = 3.0
                logger.debug("   ❌ Extreme volatility (+3)")
                
        except Exception as e:
            logger.debug(f"   ⚠️ Volatility scoring error: {e}")
        
        return score
    
    def _get_rating(self, score: float) -> str:
        """Convert score to rating"""
        if score >= 80:
            return 'EXCELLENT'
        elif score >= 70:
            return 'GOOD'
        elif score >= 60:
            return 'FAIR'
        else:
            return 'POOR'
    
    def adjust_min_score(self, new_min_score: float):
        """Điều chỉnh ngưỡng chấp nhận"""
        old_score = self.min_quality_score
        self.min_quality_score = new_min_score
        logger.info(f"🔄 Trade quality threshold adjusted: {old_score} → {new_min_score}")
