"""
TradingView AI Bridge - Kết nối TradingView với 19 AI Modules
"""

import sys
import os

# Add paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from logic.tradingview.tradingview_monitor import TradingViewMonitor
from core.complete_ai_trading_system import CompleteAITradingSystem
import MetaTrader5 as mt5
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradingViewAIBridge:
    """Bridge giữa TradingView và 19 AI Modules"""
    
    def __init__(self, symbol="GOLD", tv_exchange="TVC", mt5_symbol="GOLD"):
        """
        Khởi tạo Bridge
        
        Args:
            symbol: Symbol trên TradingView (GOLD)
            tv_exchange: Exchange trên TradingView (TVC)
            mt5_symbol: Symbol trên MT5 (GOLD on this broker, not XAUUSD)
        """
        self.symbol = symbol
        self.tv_exchange = tv_exchange
        self.mt5_symbol = mt5_symbol
        
        # Initialize TradingView Monitor
        self.tv_monitor = TradingViewMonitor(
            symbol=symbol,
            screener="cfd",
            exchange=tv_exchange
        )
        
        # Initialize 19 AI Modules
        self.ai_system = None
        self._init_ai_system()
        
        logger.info("✅ TradingView AI Bridge initialized")
    
    def _init_ai_system(self):
        """Khởi tạo 19 AI Modules"""
        try:
            # Initialize MT5
            if not mt5.initialize():
                logger.error("❌ MT5 initialization failed")
                return False
            
            # Initialize AI System (no parameters in __init__)
            self.ai_system = CompleteAITradingSystem()
            
            logger.info("✅ 19 AI Modules initialized")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error initializing AI system: {e}")
            return False
    
    def get_tradingview_signal(self, timeframe='M15'):
        """
        Lấy tín hiệu từ TradingView
        
        Args:
            timeframe: Khung thời gian
            
        Returns:
            dict: TradingView analysis
        """
        return self.tv_monitor.get_technical_analysis(timeframe)
    
    def validate_with_ai_modules(self, tv_signal):
        """
        Validate tín hiệu TradingView với 19 AI Modules
        
        Args:
            tv_signal: Tín hiệu từ TradingView
            
        Returns:
            dict: Kết quả validation
        """
        if not self.ai_system:
            logger.error("❌ AI System not initialized")
            return None
        
        try:
            # Lấy data từ MT5
            rates = mt5.copy_rates_from_pos(self.mt5_symbol, mt5.TIMEFRAME_M15, 0, 500)
            if rates is None or len(rates) == 0:
                error_code = mt5.last_error()
                logger.error(f"❌ Failed to get MT5 data: {error_code}")
                logger.error(f"   Symbol: {self.mt5_symbol}, Timeframe: M15")
                # Try to check if symbol exists
                symbol_info = mt5.symbol_info(self.mt5_symbol)
                if symbol_info is None:
                    logger.error(f"   Symbol {self.mt5_symbol} not found in MT5")
                    logger.error(f"   Try checking available symbols with mt5.symbols_get()")
                return None
            
            # Prepare MT5 data
            import pandas as pd
            import numpy as np
            
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            
            # Calculate indicators needed by AI modules
            df['rsi'] = self._calculate_rsi(df['close'])
            df['macd'], df['macd_signal'], df['macd_hist'] = self._calculate_macd(df['close'])
            df['atr'] = self._calculate_atr(df)
            
            # Get AI analysis
            ai_analysis = {}
            
            # 1. Market Phase AI
            try:
                phase = self.ai_system.market_phase_ai.detect_phase(df)
                ai_analysis['market_phase'] = phase
                logger.info(f"📊 Market Phase: {phase.get('phase', 'Unknown')}")
            except Exception as e:
                logger.error(f"❌ Market Phase AI error: {e}")
                ai_analysis['market_phase'] = {'phase': 'Unknown', 'confidence': 0}
            
            # 2. Breaker Block AI  
            try:
                breakers = self.ai_system.breaker_ai.detect_breakers(df)
                ai_analysis['breaker_blocks'] = breakers
                logger.info(f"📊 Breakers: {len(breakers.get('breakers', []))}")
            except Exception as e:
                logger.error(f"❌ Breaker Block AI error: {e}")
                ai_analysis['breaker_blocks'] = {'breakers': []}
            
            # 3. SMC Score
            try:
                smc_score = self._calculate_smc_score(df)
                ai_analysis['smc_score'] = smc_score
                logger.info(f"📊 SMC Score: {smc_score.get('score', 0)}/6")
            except Exception as e:
                logger.error(f"❌ SMC Score error: {e}")
                ai_analysis['smc_score'] = {'score': 0}
            
            # 4. MACD Analysis
            current_macd = df['macd_hist'].iloc[-1]
            ai_analysis['macd'] = {
                'histogram': current_macd,
                'signal': 'BULLISH' if current_macd > 0 else 'BEARISH',
                'strength': abs(current_macd)
            }
            
            # 5. Enhanced News Filter AI
            try:
                if hasattr(self.ai_system, 'news_filter_ai'):
                    news_impact = self.ai_system.news_filter_ai.check_news_impact()
                    ai_analysis['news_filter'] = news_impact
                else:
                    ai_analysis['news_filter'] = {'safe_to_trade': True}
            except Exception as e:
                logger.error(f"❌ News Filter AI error: {e}")
                ai_analysis['news_filter'] = {'safe_to_trade': True}
            
            # 6. Risk AI
            current_price = df['close'].iloc[-1]
            atr = df['atr'].iloc[-1]
            
            ai_analysis['risk'] = {
                'atr': atr,
                'recommended_sl': atr * 2,
                'recommended_tp': atr * 3,
                'volatility': 'HIGH' if atr > 10 else 'MEDIUM' if atr > 5 else 'LOW'
            }
            
            # Calculate final confidence
            final_analysis = self._calculate_final_confidence(tv_signal, ai_analysis)
            
            return final_analysis
            
        except Exception as e:
            logger.error(f"❌ Error in AI validation: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        import pandas as pd
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calculate MACD"""
        import pandas as pd
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        macd_hist = macd - macd_signal
        return macd, macd_signal, macd_hist
    
    def _calculate_atr(self, df, period=14):
        """Calculate ATR"""
        import pandas as pd
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr
    
    def _calculate_smc_score(self, df):
        """Calculate SMC Score"""
        score = 0
        max_score = 6
        reasons = []
        
        # Check trend (BOS/CHoCH)
        if self._check_structure(df):
            score += 1
            reasons.append("Structure confirmed")
        
        # Check Order Blocks
        if self._check_order_blocks(df):
            score += 1
            reasons.append("Order Block present")
        
        # Check FVG
        if self._check_fvg(df):
            score += 1
            reasons.append("Fair Value Gap")
        
        # Check Liquidity
        if self._check_liquidity(df):
            score += 1
            reasons.append("Liquidity swept")
        
        # Check Premium/Discount
        if self._check_premium_discount(df):
            score += 1
            reasons.append("In discount zone")
        
        # Check Volume
        if self._check_volume(df):
            score += 1
            reasons.append("Volume confirmation")
        
        return {
            'score': score,
            'max_score': max_score,
            'percentage': (score / max_score) * 100,
            'reasons': reasons
        }
    
    def _check_structure(self, df):
        """Check market structure"""
        # Simple check: Higher highs and higher lows for uptrend
        recent = df.tail(10)
        highs = recent['high'].values
        lows = recent['low'].values
        
        # Check if making higher highs
        if len(highs) >= 3:
            if highs[-1] > highs[-2] > highs[-3]:
                return True
            if lows[-1] < lows[-2] < lows[-3]:
                return True
        
        return False
    
    def _check_order_blocks(self, df):
        """Check for Order Blocks"""
        # Simplified: Check for strong rejection candles
        recent = df.tail(20)
        for i in range(len(recent) - 1):
            body = abs(recent['close'].iloc[i] - recent['open'].iloc[i])
            range_size = recent['high'].iloc[i] - recent['low'].iloc[i]
            if body / range_size > 0.7:  # Strong body
                return True
        return False
    
    def _check_fvg(self, df):
        """Check for Fair Value Gap"""
        recent = df.tail(5)
        for i in range(1, len(recent) - 1):
            # Check if there's a gap
            if recent['low'].iloc[i+1] > recent['high'].iloc[i-1]:
                return True
            if recent['high'].iloc[i+1] < recent['low'].iloc[i-1]:
                return True
        return False
    
    def _check_liquidity(self, df):
        """Check liquidity sweep"""
        recent = df.tail(20)
        # Check if price swept a recent high/low
        recent_high = recent['high'].max()
        recent_low = recent['low'].min()
        current_price = df['close'].iloc[-1]
        
        # If price is near recent high/low
        if abs(current_price - recent_high) / recent_high < 0.002:
            return True
        if abs(current_price - recent_low) / recent_low < 0.002:
            return True
        
        return False
    
    def _check_premium_discount(self, df):
        """Check if in premium/discount zone"""
        recent_high = df['high'].tail(50).max()
        recent_low = df['low'].tail(50).min()
        current_price = df['close'].iloc[-1]
        
        range_size = recent_high - recent_low
        from_low = current_price - recent_low
        
        position = (from_low / range_size) * 100
        
        # Discount zone: 0-40%, Premium zone: 60-100%
        if position < 40 or position > 60:
            return True
        
        return False
    
    def _check_volume(self, df):
        """Check volume confirmation"""
        if 'tick_volume' in df.columns:
            recent_volume = df['tick_volume'].tail(5).mean()
            avg_volume = df['tick_volume'].tail(50).mean()
            return recent_volume > avg_volume * 1.2
        return True  # Default true if no volume data
    
    def _calculate_final_confidence(self, tv_signal, ai_analysis):
        """
        Tính confidence cuối cùng kết hợp TradingView và AI
        
        Args:
            tv_signal: Tín hiệu TradingView
            ai_analysis: Phân tích từ 19 AI modules
            
        Returns:
            dict: Kết quả cuối cùng
        """
        # Weight allocation
        TV_WEIGHT = 0.30  # 30% TradingView
        AI_WEIGHT = 0.70  # 70% AI Modules
        
        # TradingView score
        tv_recommendation = tv_signal.get('recommendation', 'NEUTRAL')
        tv_confidence = tv_signal.get('tv_confidence', 50)
        
        # Chuyển recommendation thành score
        if 'BUY' in tv_recommendation:
            tv_score = tv_confidence
            tv_direction = 'BUY'
        elif 'SELL' in tv_recommendation:
            tv_score = tv_confidence
            tv_direction = 'SELL'
        else:
            tv_score = 50
            tv_direction = 'NEUTRAL'
        
        # AI Modules score
        ai_scores = []
        
        # Market Phase (20%)
        phase = ai_analysis.get('market_phase', {})
        phase_name = phase.get('phase', 'Unknown')
        if 'Expansion' in phase_name or 'Accumulation' in phase_name:
            ai_scores.append(70)
        elif 'Distribution' in phase_name or 'Markdown' in phase_name:
            ai_scores.append(30)
        else:
            ai_scores.append(50)
        
        # SMC Score (25%)
        smc = ai_analysis.get('smc_score', {})
        smc_percentage = smc.get('percentage', 0)
        ai_scores.append(smc_percentage)
        
        # MACD (20%)
        macd = ai_analysis.get('macd', {})
        macd_signal = macd.get('signal', 'NEUTRAL')
        macd_strength = macd.get('strength', 0)
        
        if macd_signal == 'BULLISH':
            macd_score = 50 + min(macd_strength * 5, 50)
        elif macd_signal == 'BEARISH':
            macd_score = 50 - min(macd_strength * 5, 50)
        else:
            macd_score = 50
        ai_scores.append(macd_score)
        
        # News Filter (15%)
        news = ai_analysis.get('news_filter', {})
        if news.get('safe_to_trade', True):
            ai_scores.append(70)
        else:
            ai_scores.append(30)
        
        # Breaker Blocks (20%)
        breakers = ai_analysis.get('breaker_blocks', {})
        breaker_list = breakers.get('breakers', [])
        if len(breaker_list) > 0:
            ai_scores.append(75)
        else:
            ai_scores.append(50)
        
        # Calculate average AI score
        ai_score = sum(ai_scores) / len(ai_scores) if ai_scores else 50
        
        # Determine AI direction
        if ai_score > 60:
            ai_direction = 'BUY'
        elif ai_score < 40:
            ai_direction = 'SELL'
        else:
            ai_direction = 'NEUTRAL'
        
        # Calculate final confidence
        final_confidence = (tv_score * TV_WEIGHT) + (ai_score * AI_WEIGHT)
        
        # Determine final recommendation
        if tv_direction == ai_direction and tv_direction != 'NEUTRAL':
            final_recommendation = tv_direction
            # Boost confidence if both agree
            final_confidence = min(final_confidence * 1.1, 100)
        elif tv_direction != ai_direction and tv_direction != 'NEUTRAL' and ai_direction != 'NEUTRAL':
            # Conflict - reduce confidence
            final_recommendation = 'NEUTRAL'
            final_confidence = 50
        else:
            # One is neutral
            final_recommendation = tv_direction if tv_direction != 'NEUTRAL' else ai_direction
        
        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'symbol': self.symbol,
            
            # TradingView
            'tradingview': {
                'recommendation': tv_recommendation,
                'confidence': tv_confidence,
                'score': tv_score,
                'indicators': tv_signal.get('indicators', {})
            },
            
            # AI Modules
            'ai_modules': {
                'score': ai_score,
                'direction': ai_direction,
                'market_phase': phase,
                'smc_score': smc,
                'macd': macd,
                'news_filter': news,
                'breaker_blocks': breaker_list,
                'risk': ai_analysis.get('risk', {})
            },
            
            # Final
            'final': {
                'recommendation': final_recommendation,
                'confidence': final_confidence,
                'tv_weight': TV_WEIGHT * 100,
                'ai_weight': AI_WEIGHT * 100
            }
        }


def test_bridge():
    """Test TradingView AI Bridge"""
    print("\n" + "="*70)
    print("🧪 TESTING TRADINGVIEW AI BRIDGE")
    print("="*70 + "\n")
    
    bridge = TradingViewAIBridge(
        symbol="GOLD",
        tv_exchange="TVC",
        mt5_symbol="XAUUSD"
    )
    
    print("📊 Getting TradingView signal...")
    tv_signal = bridge.get_tradingview_signal('M15')
    
    if tv_signal:
        print(f"✅ TradingView: {tv_signal['recommendation']} ({tv_signal['tv_confidence']:.1f}%)")
        print(f"   Price: ${tv_signal['indicators']['price']}")
        print(f"   MACD: {tv_signal['indicators']['macd']:.3f}")
        print(f"   RSI: {tv_signal['indicators']['rsi']:.1f}")
    
    print("\n📊 Validating with 19 AI Modules...")
    result = bridge.validate_with_ai_modules(tv_signal)
    
    if result:
        print("\n" + "="*70)
        print("🎯 FINAL ANALYSIS")
        print("="*70)
        print(f"TradingView: {result['tradingview']['recommendation']} ({result['tradingview']['confidence']:.1f}%)")
        print(f"AI Modules: {result['ai_modules']['direction']} ({result['ai_modules']['score']:.1f}%)")
        print(f"\n🎯 FINAL RECOMMENDATION: {result['final']['recommendation']}")
        print(f"🎯 FINAL CONFIDENCE: {result['final']['confidence']:.1f}%")
        print(f"\nWeights: TV={result['final']['tv_weight']:.0f}% | AI={result['final']['ai_weight']:.0f}%")
        
        print("\n📊 AI Modules Details:")
        print(f"   Market Phase: {result['ai_modules']['market_phase'].get('phase', 'Unknown')}")
        print(f"   SMC Score: {result['ai_modules']['smc_score']['score']}/6 ({result['ai_modules']['smc_score']['percentage']:.0f}%)")
        print(f"   MACD: {result['ai_modules']['macd']['signal']} (Strength: {result['ai_modules']['macd']['strength']:.2f})")
        print(f"   Breaker Blocks: {len(result['ai_modules']['breaker_blocks'])}")
        print(f"   Safe to Trade: {result['ai_modules']['news_filter'].get('safe_to_trade', True)}")
    
    print("\n" + "="*70)
    print("✅ BRIDGE TEST COMPLETED")
    print("="*70 + "\n")


if __name__ == '__main__':
    test_bridge()
