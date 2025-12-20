"""
TradingView Monitor - Lấy phân tích kỹ thuật từ TradingView
Tích hợp với 19 AI Modules để validate tín hiệu
"""

from tradingview_ta import TA_Handler, Interval
import time
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TradingViewMonitor:
    """Monitor TradingView technical analysis"""
    
    def __init__(self, symbol="XAUUSD", screener="forex", exchange="OANDA"):
        """
        Khởi tạo TradingView Monitor
        
        Args:
            symbol: Cặp tiền (XAUUSD, EURUSD, etc.)
            screener: Loại thị trường (forex, crypto, stocks)
            exchange: Sàn giao dịch (OANDA, FX_IDC, BINANCE, etc.)
        """
        self.symbol = symbol
        self.screener = screener
        self.exchange = exchange
        
        # Handlers cho các timeframe khác nhau
        self.handlers = {
            'M15': TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=Interval.INTERVAL_15_MINUTES
            ),
            'H1': TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=Interval.INTERVAL_1_HOUR
            ),
            'H4': TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=Interval.INTERVAL_4_HOURS
            ),
            'D1': TA_Handler(
                symbol=symbol,
                screener=screener,
                exchange=exchange,
                interval=Interval.INTERVAL_1_DAY
            )
        }
        
        logger.info(f"✅ TradingView Monitor initialized: {symbol} on {exchange}")
    
    def get_technical_analysis(self, timeframe='M15'):
        """
        Lấy phân tích kỹ thuật từ TradingView
        
        Args:
            timeframe: Khung thời gian (M15, H1, H4, D1)
            
        Returns:
            dict: Phân tích kỹ thuật chi tiết
        """
        try:
            handler = self.handlers.get(timeframe)
            if not handler:
                logger.error(f"❌ Invalid timeframe: {timeframe}")
                return None
            
            analysis = handler.get_analysis()
            
            result = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'timeframe': timeframe,
                'symbol': self.symbol,
                
                # Tổng quan recommendation
                'recommendation': analysis.summary['RECOMMENDATION'],  # BUY/SELL/NEUTRAL
                'buy_signals': analysis.summary['BUY'],
                'sell_signals': analysis.summary['SELL'],
                'neutral_signals': analysis.summary['NEUTRAL'],
                
                # Oscillators (MACD, RSI, Stochastic, etc.)
                'oscillators': {
                    'recommendation': analysis.oscillators['RECOMMENDATION'],
                    'buy': analysis.oscillators['BUY'],
                    'sell': analysis.oscillators['SELL'],
                    'neutral': analysis.oscillators['NEUTRAL']
                },
                
                # Moving Averages
                'moving_averages': {
                    'recommendation': analysis.moving_averages['RECOMMENDATION'],
                    'buy': analysis.moving_averages['BUY'],
                    'sell': analysis.moving_averages['SELL'],
                    'neutral': analysis.moving_averages['NEUTRAL']
                },
                
                # Chi tiết indicators
                'indicators': {
                    'price': analysis.indicators.get('close', 0),
                    'open': analysis.indicators.get('open', 0),
                    'high': analysis.indicators.get('high', 0),
                    'low': analysis.indicators.get('low', 0),
                    
                    # MACD
                    'macd': analysis.indicators.get('MACD.macd', 0),
                    'macd_signal': analysis.indicators.get('MACD.signal', 0),
                    'macd_histogram': analysis.indicators.get('MACD.macd', 0) - analysis.indicators.get('MACD.signal', 0),
                    
                    # RSI
                    'rsi': analysis.indicators.get('RSI', 50),
                    'rsi14': analysis.indicators.get('RSI14', 50),
                    
                    # Stochastic
                    'stoch_k': analysis.indicators.get('Stoch.K', 50),
                    'stoch_d': analysis.indicators.get('Stoch.D', 50),
                    
                    # ADX
                    'adx': analysis.indicators.get('ADX', 0),
                    
                    # CCI
                    'cci20': analysis.indicators.get('CCI20', 0),
                    
                    # Moving Averages
                    'ema10': analysis.indicators.get('EMA10', 0),
                    'ema20': analysis.indicators.get('EMA20', 0),
                    'ema50': analysis.indicators.get('EMA50', 0),
                    'ema100': analysis.indicators.get('EMA100', 0),
                    'ema200': analysis.indicators.get('EMA200', 0),
                    'sma10': analysis.indicators.get('SMA10', 0),
                    'sma20': analysis.indicators.get('SMA20', 0),
                    'sma50': analysis.indicators.get('SMA50', 0),
                    'sma100': analysis.indicators.get('SMA100', 0),
                    'sma200': analysis.indicators.get('SMA200', 0),
                }
            }
            
            # Tính confidence score từ TradingView
            result['tv_confidence'] = self._calculate_tv_confidence(result)
            
            logger.info(f"📊 [{timeframe}] {self.symbol}: {result['recommendation']} "
                       f"(Confidence: {result['tv_confidence']:.1f}%)")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error getting TradingView analysis: {e}")
            return None
    
    def _calculate_tv_confidence(self, analysis):
        """
        Tính confidence score từ TradingView signals
        
        Args:
            analysis: Kết quả phân tích từ get_technical_analysis
            
        Returns:
            float: Confidence score (0-100)
        """
        recommendation = analysis['recommendation']
        buy_signals = analysis['buy_signals']
        sell_signals = analysis['sell_signals']
        neutral_signals = analysis['neutral_signals']
        
        total_signals = buy_signals + sell_signals + neutral_signals
        
        if recommendation == 'BUY':
            confidence = (buy_signals / total_signals) * 100 if total_signals > 0 else 0
        elif recommendation == 'SELL':
            confidence = (sell_signals / total_signals) * 100 if total_signals > 0 else 0
        else:  # NEUTRAL
            confidence = 50  # Neutral = 50%
        
        return confidence
    
    def get_multi_timeframe_analysis(self):
        """
        Lấy phân tích từ nhiều timeframe
        
        Returns:
            dict: Phân tích tất cả timeframes
        """
        logger.info("🔍 Getting multi-timeframe analysis...")
        
        mtf_analysis = {}
        for tf in ['M15', 'H1', 'H4', 'D1']:
            analysis = self.get_technical_analysis(tf)
            if analysis:
                mtf_analysis[tf] = analysis
            time.sleep(1)  # Delay để tránh rate limit
        
        # Tính overall recommendation
        overall = self._calculate_mtf_consensus(mtf_analysis)
        mtf_analysis['overall'] = overall
        
        logger.info(f"🎯 Multi-timeframe consensus: {overall['recommendation']} "
                   f"(Confidence: {overall['confidence']:.1f}%)")
        
        return mtf_analysis
    
    def _calculate_mtf_consensus(self, mtf_analysis):
        """
        Tính consensus từ nhiều timeframe
        
        Args:
            mtf_analysis: Dict chứa phân tích của các timeframe
            
        Returns:
            dict: Overall consensus
        """
        # Weight cho mỗi timeframe
        weights = {
            'M15': 0.2,  # 20%
            'H1': 0.3,   # 30%
            'H4': 0.3,   # 30%
            'D1': 0.2    # 20%
        }
        
        buy_score = 0
        sell_score = 0
        total_weight = 0
        
        for tf, weight in weights.items():
            if tf in mtf_analysis:
                rec = mtf_analysis[tf]['recommendation']
                conf = mtf_analysis[tf]['tv_confidence']
                
                if rec == 'BUY':
                    buy_score += conf * weight
                elif rec == 'SELL':
                    sell_score += conf * weight
                
                total_weight += weight
        
        # Normalize
        if total_weight > 0:
            buy_score = buy_score / total_weight
            sell_score = sell_score / total_weight
        
        # Quyết định
        if buy_score > sell_score and buy_score > 50:
            recommendation = 'BUY'
            confidence = buy_score
        elif sell_score > buy_score and sell_score > 50:
            recommendation = 'SELL'
            confidence = sell_score
        else:
            recommendation = 'NEUTRAL'
            confidence = 50
        
        return {
            'recommendation': recommendation,
            'confidence': confidence,
            'buy_score': buy_score,
            'sell_score': sell_score
        }
    
    def monitor_continuous(self, interval=60, callback=None):
        """
        Monitor liên tục TradingView
        
        Args:
            interval: Thời gian check (giây)
            callback: Hàm callback khi có tín hiệu
        """
        logger.info(f"🔄 Starting continuous monitor (interval: {interval}s)")
        
        while True:
            try:
                analysis = self.get_technical_analysis('M15')
                
                if analysis and callback:
                    callback(analysis)
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                logger.info("⏹️ Monitor stopped by user")
                break
            except Exception as e:
                logger.error(f"❌ Error in monitor loop: {e}")
                time.sleep(interval)


def test_tradingview_monitor():
    """Test TradingView Monitor"""
    print("\n" + "="*60)
    print("🧪 TESTING TRADINGVIEW MONITOR")
    print("="*60 + "\n")
    
    # Test 1: Single timeframe
    print("📊 Test 1: Single Timeframe Analysis (M15)")
    print("-" * 60)
    # GOLD trên TradingView thường là TVC:GOLD
    monitor = TradingViewMonitor(symbol="GOLD", screener="cfd", exchange="TVC")
    analysis = monitor.get_technical_analysis('M15')
    
    if analysis:
        print(f"✅ Symbol: {analysis['symbol']}")
        print(f"✅ Timeframe: {analysis['timeframe']}")
        print(f"✅ Price: ${analysis['indicators']['price']}")
        print(f"✅ Recommendation: {analysis['recommendation']}")
        print(f"✅ Confidence: {analysis['tv_confidence']:.1f}%")
        print(f"✅ BUY signals: {analysis['buy_signals']}")
        print(f"✅ SELL signals: {analysis['sell_signals']}")
        print(f"✅ MACD: {analysis['indicators']['macd']:.3f}")
        print(f"✅ RSI: {analysis['indicators']['rsi']:.1f}")
    
    print("\n" + "="*60)
    
    # Test 2: Multi-timeframe
    print("📊 Test 2: Multi-Timeframe Analysis")
    print("-" * 60)
    mtf_analysis = monitor.get_multi_timeframe_analysis()
    
    for tf in ['M15', 'H1', 'H4', 'D1']:
        if tf in mtf_analysis:
            data = mtf_analysis[tf]
            print(f"{tf}: {data['recommendation']} ({data['tv_confidence']:.1f}%)")
    
    if 'overall' in mtf_analysis:
        overall = mtf_analysis['overall']
        print(f"\n🎯 OVERALL: {overall['recommendation']} ({overall['confidence']:.1f}%)")
    
    print("\n" + "="*60)
    print("✅ TRADINGVIEW MONITOR TEST COMPLETED")
    print("="*60 + "\n")


if __name__ == '__main__':
    test_tradingview_monitor()
