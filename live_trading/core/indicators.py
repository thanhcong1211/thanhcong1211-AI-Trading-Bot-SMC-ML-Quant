"""
Technical Indicators Module
Technical analysis indicators and filters
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

class TechnicalIndicators:
    """Technical indicators calculation"""
    
    @staticmethod
    def calculate_sma(df, periods=[5, 10, 20]):
        """Simple Moving Averages"""
        for period in periods:
            df[f'sma_{period}'] = df['close'].rolling(period).mean()
        return df

    @staticmethod
    def calculate_rsi(df, period=14):
        """Relative Strength Index"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-8)
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    @staticmethod
    def calculate_macd(df, fast=12, slow=26, signal=9):
        """MACD Oscillator"""
        exp1 = df['close'].ewm(span=fast).mean()
        exp2 = df['close'].ewm(span=slow).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=signal).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        return df
    
    @staticmethod
    def calculate_bollinger(df, period=20, std=2):
        """Bollinger Bands"""
        df['bb_middle'] = df['close'].rolling(period).mean()
        bb_std = df['close'].rolling(period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * std)
        df['bb_lower'] = df['bb_middle'] - (bb_std * std)
        return df
    
    @staticmethod
    def calculate_atr(df, period=14):
        """Average True Range"""
        df['tr1'] = abs(df['high'] - df['low'])
        df['tr2'] = abs(df['high'] - df['close'].shift())
        df['tr3'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(period).mean()
        return df
    
    @staticmethod
    def analyze_trend(df, short_period=20, long_period=50):
        """Trend analysis with sideways detection"""
        df['ema_short'] = df['close'].ewm(span=short_period).mean()
        df['ema_long'] = df['close'].ewm(span=long_period).mean()
        
        df['trend_direction'] = np.where(df['ema_short'] > df['ema_long'], 1, -1)
        df['trend_strength'] = abs(df['ema_short'] - df['ema_long']) / (df['close'] + 1e-8)
        
        # Sideways detection
        df['ema_short_slope'] = df['ema_short'].pct_change(5)
        df['ema_long_slope'] = df['ema_long'].pct_change(10)
        
        sideways_threshold = 0.001
        df['is_sideways'] = (
            (abs(df['ema_short_slope']) < sideways_threshold) &
            (abs(df['ema_long_slope']) < sideways_threshold) &
            (df['trend_strength'] < df['trend_strength'].rolling(20).mean())
        ).astype(int)
        
        df['trend_quality'] = np.where(
            df['is_sideways'] == 1, 
            0.0,
            df['trend_strength'] / (df['trend_strength'].rolling(20).mean() + 1e-8)
        )
        
        df['price_vs_ema_short'] = (df['close'] - df['ema_short']) / (df['ema_short'] + 1e-8)
        df['price_vs_ema_long'] = (df['close'] - df['ema_long']) / (df['ema_long'] + 1e-8)
        df['trend_momentum'] = df['ema_short'].pct_change(5)
        
        df['trend_consistency'] = (
            (df['trend_direction'] == df['trend_direction'].shift(1)) &
            (df['trend_direction'] == df['trend_direction'].shift(2))
        ).astype(int)
        
        return df
    
    @staticmethod
    def detect_support_resistance(df, window=20, min_touches=2):
        """Support/Resistance detection"""
        df['resistance_level'] = df['high'].rolling(window, center=True).max()
        df['support_level'] = df['low'].rolling(window, center=True).min()
        
        df['distance_to_resistance'] = (df['resistance_level'] - df['close']) / df['close']
        df['distance_to_support'] = (df['close'] - df['support_level']) / df['close']
        
        df['near_resistance'] = (abs(df['distance_to_resistance']) < 0.002).astype(int)
        df['near_support'] = (abs(df['distance_to_support']) < 0.002).astype(int)
        
        df['resistance_breakout'] = ((df['close'] > df['resistance_level']) & 
                                   (df['close'].shift(1) <= df['resistance_level'].shift(1))).astype(int)
        df['support_breakdown'] = ((df['close'] < df['support_level']) & 
                                 (df['close'].shift(1) >= df['support_level'].shift(1))).astype(int)
        
        return df
    
    @staticmethod
    def analyze_volume(df):
        """Volume analysis"""
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        df['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()
        df['price_volume_trend'] = df['close'].pct_change() * df['volume_ratio']
        df['volume_spike'] = (df['volume'] > df['volume_sma'] * 2).astype(int)
        
        df['price_change_direction'] = np.where(df['close'] > df['close'].shift(1), 1, 
                                               np.where(df['close'] < df['close'].shift(1), -1, 0))
        df['obv'] = (df['volume'] * df['price_change_direction']).cumsum()
        df['obv_trend'] = df['obv'].rolling(10).mean()
        
        return df
    
    @staticmethod
    def detect_candlestick_patterns(df):
        """Candlestick pattern detection"""
        df['body_size'] = abs(df['close'] - df['open']) / df['open']
        df['upper_shadow'] = (df['high'] - np.maximum(df['close'], df['open'])) / df['open']
        df['lower_shadow'] = (np.minimum(df['close'], df['open']) - df['low']) / df['open']
        df['total_range'] = (df['high'] - df['low']) / df['open']
        
        df['bullish_candle'] = (df['close'] > df['open']).astype(int)
        df['bearish_candle'] = (df['close'] < df['open']).astype(int)
        df['doji'] = (abs(df['close'] - df['open']) / df['open'] < 0.001).astype(int)
        
        df['hammer'] = ((df['lower_shadow'] > df['body_size'] * 2).astype(bool) & 
                       (df['upper_shadow'] < df['body_size'] * 0.5).astype(bool) &
                       (df['body_size'] > 0.002).astype(bool)).astype(int)
        
        df['shooting_star'] = ((df['upper_shadow'] > df['body_size'] * 2).astype(bool) & 
                              (df['lower_shadow'] < df['body_size'] * 0.5).astype(bool) &
                              (df['body_size'] > 0.002).astype(bool)).astype(int)
        
        df['bullish_engulfing'] = ((df['bullish_candle'] == 1).astype(bool) & 
                                  (df['bearish_candle'].shift(1) == 1).astype(bool) &
                                  (df['close'] > df['open'].shift(1)).astype(bool) &
                                  (df['open'] < df['close'].shift(1)).astype(bool)).astype(int)
        
        df['bearish_engulfing'] = ((df['bearish_candle'] == 1).astype(bool) & 
                                  (df['bullish_candle'].shift(1) == 1).astype(bool) &
                                  (df['close'] < df['open'].shift(1)).astype(bool) &
                                  (df['open'] > df['close'].shift(1)).astype(bool)).astype(int)
        
        df['morning_star'] = ((df['bearish_candle'].shift(2) == 1).astype(bool) &
                             (df['doji'].shift(1) == 1).astype(bool) &
                             (df['bullish_candle'] == 1).astype(bool) &
                             (df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2).astype(bool)).astype(int)
        
        df['evening_star'] = ((df['bullish_candle'].shift(2) == 1).astype(bool) &
                             (df['doji'].shift(1) == 1).astype(bool) &
                             (df['bearish_candle'] == 1).astype(bool) &
                             (df['close'] < (df['open'].shift(2) + df['close'].shift(2)) / 2).astype(bool)).astype(int)
        
        # Enhanced patterns
        try:
            from utils.candle_pattern_integration import enrich_with_candle_patterns
            df = enrich_with_candle_patterns(df, scoring=True)
        except Exception:
            pass

        return df


# Helper functions for sideways detection
def ema_distance(data, timeframe='H1'):
    """Calculate EMA distance"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 50:
            return 0.0
        ema20 = df['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        return abs(ema20 - ema50) / ema50
    except:
        return 0.0


def ATR(data, timeframe='H1', period=14):
    """Calculate ATR"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return 0.0
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        tr = pd.concat([high - low, abs(high - close), abs(low - close)], axis=1).max(axis=1)
        return tr.rolling(period).mean().iloc[-1]
    except:
        return 0.0


def bollinger_width(data, timeframe='H1', period=20):
    """Calculate Bollinger Bands width"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return 0.0
        close = df['close']
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()
        width = (sma + (std * 2) - (sma - (std * 2))) / sma
        return width.iloc[-1]
    except:
        return 0.0


def volume(data, timeframe='H1'):
    """Get average volume"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return 0.0
        return df['volume'].rolling(20).mean().iloc[-1]
    except:
        return 0.0


def price_range(data, timeframe='H1'):
    """Calculate price range"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return 0.0
        ranges = (df['high'] - df['low']) / df['close']
        return ranges.rolling(20).mean().iloc[-1]
    except:
        return 0.0


def ADX(data, timeframe='H1', period=14):
    """Calculate ADX"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period + 1:
            return 0.0
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        dm_plus = np.where((high - high.shift(1)) > (low.shift(1) - low),
                          np.maximum(high - high.shift(1), 0), 0)
        dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)),
                           np.maximum(low.shift(1) - low, 0), 0)
        
        atr = tr.ewm(span=period).mean()
        di_plus = pd.Series(dm_plus).ewm(span=period).mean() / atr * 100
        di_minus = pd.Series(dm_minus).ewm(span=period).mean() / atr * 100
        
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100
        adx = dx.ewm(span=period).mean()
        
        return adx.iloc[-1]
    except:
        return 0.0


def detect_sideway(data):
    """Detect sideways market (score 0-7)"""
    sideway_score = 0
    
    if ema_distance(data) < 0.005:
        sideway_score += 1
    
    atr_val = ATR(data)
    current_price = data.get('H1', pd.DataFrame()).get('close', pd.Series()).iloc[-1] if data.get('H1') is not None else 1000
    if atr_val / current_price < 0.003 if current_price > 0 else False:
        sideway_score += 1
    
    if bollinger_width(data) < 0.01:
        sideway_score += 1
    
    if volume(data) < 1000:
        sideway_score += 1
    
    if price_range(data) < 0.005:
        sideway_score += 1
    
    if ADX(data) < 20:
        sideway_score += 1
    
    try:
        df = data.get('H1')
        if df is not None and len(df) >= 20:
            recent_high = df['high'].tail(20).max()
            recent_low = df['low'].tail(20).min()
            current = df['close'].iloc[-1]
            range_size = (recent_high - recent_low) / recent_low
            position_in_range = (current - recent_low) / (recent_high - recent_low)
            if 0.3 < position_in_range < 0.7 and range_size < 0.02:
                sideway_score += 1
    except:
        pass
    
    return sideway_score


def supertrend(data, timeframe='H1', period=10, multiplier=3.0):
    """Calculate Supertrend indicator"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return None
        
        high = df['high']
        low = df['low']
        close = df['close']
        
        tr = pd.concat([high - low, abs(high - close.shift(1)), abs(low - close.shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        hl2 = (high + low) / 2
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)
        
        supertrend_val = pd.Series(index=df.index)
        trend = pd.Series(index=df.index)
        
        for i in range(len(df)):
            if i == 0:
                supertrend_val.iloc[i] = upper_band.iloc[i]
                trend.iloc[i] = 1
            else:
                if close.iloc[i-1] <= supertrend_val.iloc[i-1]:
                    supertrend_val.iloc[i] = max(upper_band.iloc[i], supertrend_val.iloc[i-1])
                else:
                    supertrend_val.iloc[i] = upper_band.iloc[i]
                
                if close.iloc[i-1] >= supertrend_val.iloc[i-1]:
                    temp_trend = min(lower_band.iloc[i], supertrend_val.iloc[i-1])
                else:
                    temp_trend = lower_band.iloc[i]
                
                if close.iloc[i] > supertrend_val.iloc[i-1]:
                    trend.iloc[i] = 1
                    supertrend_val.iloc[i] = temp_trend if temp_trend > supertrend_val.iloc[i] else supertrend_val.iloc[i]
                elif close.iloc[i] < supertrend_val.iloc[i-1]:
                    trend.iloc[i] = -1
                    supertrend_val.iloc[i] = temp_trend if temp_trend < supertrend_val.iloc[i] else supertrend_val.iloc[i]
                else:
                    trend.iloc[i] = trend.iloc[i-1]
                    supertrend_val.iloc[i] = supertrend_val.iloc[i-1]
        
        return supertrend_val.iloc[-1]
    except Exception as e:
        logger.warning(f"⚠️ Supertrend failed: {e}")
        return None


def price(data, timeframe='H1'):
    """Get current price"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) == 0:
            return None
        return df['close'].iloc[-1]
    except:
        return None


def check_ema_alignment(signal, data, timeframe='H1'):
    """Check EMA alignment"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 200:
            return False
        
        close = df['close'].iloc[-1]
        ema20 = df['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200).mean().iloc[-1]
        
        if signal == "BUY":
            return close > ema20 > ema50 > ema200
        elif signal == "SELL":
            return close < ema20 < ema50 < ema200
        
        return False
    except Exception as e:
        logger.warning(f"⚠️ EMA alignment check failed: {e}")
        return False


def check_vwap(signal, data, timeframe='H1'):
    """Check VWAP alignment"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return False
        
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        current_price = df['close'].iloc[-1]
        
        if signal == "BUY":
            return current_price > current_vwap
        elif signal == "SELL":
            return current_price < current_vwap
        
        return False
    except Exception as e:
        logger.warning(f"⚠️ VWAP check failed: {e}")
        return False


def check_keltner(signal, data, timeframe='H1', period=20, multiplier=2.0):
    """Check Keltner Channel"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return False
        
        ema = df['close'].ewm(span=period).mean()
        tr = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        
        upper = ema + (multiplier * atr)
        lower = ema - (multiplier * atr)
        
        current_price = df['close'].iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        
        if signal == "BUY":
            return current_lower < current_price < current_upper
        elif signal == "SELL":
            return current_lower < current_price < current_upper
        
        return False
    except Exception as e:
        logger.warning(f"⚠️ Keltner check failed: {e}")
        return False


def check_volume_confirmation(signal, data, timeframe='H1'):
    """Check volume confirmation"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return False
        
        avg_volume = df['volume'].rolling(20).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        
        return volume_ratio > 1.5
    except Exception as e:
        logger.warning(f"⚠️ Volume confirmation check failed: {e}")
        return False


def check_adx_momentum(signal, data, timeframe='H1', period=14):
    """Check ADX momentum"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period + 1:
            return False
        
        tr = pd.concat([df['high'] - df['low'], abs(df['high'] - df['close'].shift(1)), abs(df['low'] - df['close'].shift(1))], axis=1).max(axis=1)
        dm_plus = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                          np.maximum(df['high'] - df['high'].shift(1), 0), 0)
        dm_minus = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                           np.maximum(df['low'].shift(1) - df['low'], 0), 0)
        
        atr = tr.ewm(span=period).mean()
        di_plus = pd.Series(dm_plus).ewm(span=period).mean() / atr * 100
        di_minus = pd.Series(dm_minus).ewm(span=period).mean() / atr * 100
        
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100
        adx = dx.ewm(span=period).mean()
        
        current_adx = adx.iloc[-1]
        current_di_plus = di_plus.iloc[-1]
        current_di_minus = di_minus.iloc[-1]
        
        if current_adx < 25:
            return False
        
        if signal == "BUY":
            return current_di_plus > current_di_minus and current_di_plus > 20
        elif signal == "SELL":
            return current_di_minus > current_di_plus and current_di_minus > 20
        
        return False
    except Exception as e:
        logger.warning(f"⚠️ ADX momentum check failed: {e}")
        return False


def check_ichimoku(signal, data, timeframe='H1'):
    """Check Ichimoku Cloud"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 52:
            return False
        
        high_9 = df['high'].rolling(9).max()
        low_9 = df['low'].rolling(9).min()
        high_26 = df['high'].rolling(26).max()
        low_26 = df['low'].rolling(26).min()
        high_52 = df['high'].rolling(52).max()
        low_52 = df['low'].rolling(52).min()
        
        tenkan = (high_9 + low_9) / 2
        kijun = (high_26 + low_26) / 2
        senkou_a = ((tenkan + kijun) / 2).shift(26)
        senkou_b = ((high_52 + low_52) / 2).shift(26)
        
        current_price = df['close'].iloc[-1]
        current_tenkan = tenkan.iloc[-1]
        current_kijun = kijun.iloc[-1]
        current_senkou_a = senkou_a.iloc[-1]
        current_senkou_b = senkou_b.iloc[-1]
        
        if signal == "BUY":
            cloud_bullish = current_senkou_a > current_senkou_b
            price_above_cloud = current_price > max(current_senkou_a, current_senkou_b)
            tenkan_above_kijun = current_tenkan > current_kijun
            price_above_kijun = current_price > current_kijun
            return cloud_bullish and price_above_cloud and tenkan_above_kijun and price_above_kijun
        elif signal == "SELL":
            cloud_bearish = current_senkou_b > current_senkou_a
            price_below_cloud = current_price < min(current_senkou_a, current_senkou_b)
            tenkan_below_kijun = current_tenkan < current_kijun
            price_below_kijun = current_price < current_kijun
            return cloud_bearish and price_below_cloud and tenkan_below_kijun and price_below_kijun
        
        return False
    except Exception as e:
        logger.warning(f"⚠️ Ichimoku check failed: {e}")
        return False


def strong_candle(data, timeframe='H1'):
    """Check for strong candle"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 2:
            return False
        
        current = df.iloc[-1]
        body_size = abs(current['close'] - current['open'])
        total_range = current['high'] - current['low']
        
        if total_range == 0:
            return False
        
        body_ratio = body_size / total_range
        
        if len(df) >= 5:
            recent_volume = df['volume'].tail(5).mean()
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_spike = recent_volume > avg_volume * 1.2
        else:
            volume_spike = True
        
        return body_ratio > 0.65 and volume_spike
    except Exception as e:
        logger.warning(f"⚠️ Strong candle check failed: {e}")
        return False


def technical_filter(signal, data):
    """Technical filter with 8 checks"""
    
    st_value = supertrend(data)
    current_price = price(data)
    
    if st_value is None or current_price is None:
        logger.warning("⚠️ Supertrend/Price data unavailable")
        return "NO TRADE"
    
    if signal == "BUY" and st_value >= current_price:
        logger.info(f"📊 Supertrend filter: BUY blocked")
        return "NO TRADE"
    elif signal == "SELL" and st_value <= current_price:
        logger.info(f"📊 Supertrend filter: SELL blocked")
        return "NO TRADE"
    
    logger.info(f"✅ Supertrend filter passed: {signal}")
    
    if not check_ema_alignment(signal, data):
        logger.info(f"📊 EMA alignment filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ EMA alignment filter passed for {signal}")
    
    if not check_vwap(signal, data):
        logger.info(f"📊 VWAP filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ VWAP filter passed for {signal}")
    
    if not check_keltner(signal, data):
        logger.info(f"📊 Keltner channel filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ Keltner channel filter passed for {signal}")
    
    if not check_ichimoku(signal, data):
        logger.info(f"📊 Ichimoku Cloud filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ Ichimoku Cloud filter passed for {signal}")
    
    if not check_volume_confirmation(signal, data):
        logger.info(f"📊 Volume Confirmation filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ Volume Confirmation filter passed for {signal}")
    
    if not check_adx_momentum(signal, data):
        logger.info(f"📊 ADX Momentum filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ ADX Momentum filter passed: Strong trend detected")
    
    if not strong_candle(data):
        logger.info(f"📊 Strong Candle filter failed for {signal}")
        return "NO TRADE"
    
    logger.info(f"✅ Strong Candle filter passed for {signal}")
    
    logger.info(f"🎯 TECHNICAL FILTER PRO: {signal} PASSED ALL 8 FILTERS ✅")
    return "TRADE_OK"
