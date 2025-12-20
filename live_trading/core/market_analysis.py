"""
Market Analysis Module
Smart Money Concepts (SMC) Detection Functions
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Import cache from core module
try:
    from core.cache import indicator_cache
except ImportError:
    # Fallback if running standalone
    class DummyCache:
        def get(self, key, length): return None
        def set(self, key, length, value): pass
    indicator_cache = DummyCache()


def detect_structure(data):
    """
    Detect market structure: Higher High (HH), Higher Low (HL), Lower High (LH), Lower Low (LL)

    Args:
        data: dict with timeframe keys containing DataFrames

    Returns:
        tuple: (HH, HL, LH, LL) - Latest values or None
    """
    try:
        df = data.get('H1')  # Use H1 timeframe for structure analysis
        if df is None or len(df) < 20:
            return None, None, None, None

        # Get recent highs and lows (last 20 candles)
        recent_highs = df['high'].tail(20)
        recent_lows = df['low'].tail(20)

        # Higher High: Current high > previous high
        hh = recent_highs.iloc[-1] > recent_highs.iloc[-2] if len(recent_highs) >= 2 else None

        # Higher Low: Current low > previous low
        hl = recent_lows.iloc[-1] > recent_lows.iloc[-2] if len(recent_lows) >= 2 else None

        # Lower High: Current high < previous high
        lh = recent_highs.iloc[-1] < recent_highs.iloc[-2] if len(recent_highs) >= 2 else None

        # Lower Low: Current low < previous low
        ll = recent_lows.iloc[-1] < recent_lows.iloc[-2] if len(recent_lows) >= 2 else None

        return hh, hl, lh, ll

    except Exception as e:
        logger.warning(f"⚠️ detect_structure failed: {e}")
        return None, None, None, None


def detect_BOS_CHOCH(data):
    """
    Detect Break of Structure (BOS) and Change of Character (ChoCH)

    Args:
        data: dict with timeframe keys containing DataFrames

    Returns:
        tuple: (bos, choch) - Boolean flags
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 10:
            return None, None

        # BOS: Break of recent swing high/low
        recent_high = df['high'].tail(10).max()
        recent_low = df['low'].tail(10).min()
        current_high = df['high'].iloc[-1]
        current_low = df['low'].iloc[-1]

        bos = current_high > recent_high or current_low < recent_low

        # ChoCH: Significant change in market character (volatility spike + price rejection)
        volatility = df['close'].pct_change().std()
        avg_volatility = df['close'].pct_change().rolling(20).std().iloc[-1]

        # Volume spike
        volume_spike = df['volume'].iloc[-1] > df['volume'].rolling(20).mean().iloc[-1] * 1.5

        # Price rejection (long wick)
        body_size = abs(df['close'].iloc[-1] - df['open'].iloc[-1])
        total_range = df['high'].iloc[-1] - df['low'].iloc[-1]
        wick_ratio = 1 - (body_size / total_range) if total_range > 0 else 0

        choch = (volatility > avg_volatility * 1.2) and volume_spike and (wick_ratio > 0.6)

        return bos, choch

    except Exception as e:
        logger.warning(f"⚠️ detect_BOS_CHOCH failed: {e}")
        return None, None


def volume_profile(data):
    """
    Compute Volume Profile with POC, VAH, VAL

    Args:
        data: dict with timeframe keys containing DataFrames

    Returns:
        dict: {'poc': price, 'vah': price, 'val': price}
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 50:
            return {'poc': None, 'vah': None, 'val': None}

        # Simple volume profile calculation
        # Group prices into bins and find volume concentration
        price_min = df['low'].min()
        price_max = df['high'].max()
        bins = np.linspace(price_min, price_max, 20)

        # Calculate volume at each price level
        volume_profile_dict = {}
        for i in range(len(bins)-1):
            mask = (df['low'] <= bins[i+1]) & (df['high'] >= bins[i])
            volume_profile_dict[(bins[i] + bins[i+1])/2] = df.loc[mask, 'volume'].sum()

        # Find POC (Point of Control) - highest volume
        poc = max(volume_profile_dict, key=volume_profile_dict.get)

        # VAH/VAL (Value Area High/Low) - 70% of volume around POC
        total_volume = sum(volume_profile_dict.values())
        sorted_prices = sorted(volume_profile_dict.items(), key=lambda x: x[1], reverse=True)

        cumulative_volume = 0
        value_area_prices = []
        for price, vol in sorted_prices:
            cumulative_volume += vol
            value_area_prices.append(price)
            if cumulative_volume >= total_volume * 0.7:
                break

        vah = max(value_area_prices)
        val = min(value_area_prices)

        return {'poc': poc, 'vah': vah, 'val': val}

    except Exception as e:
        logger.warning(f"⚠️ volume_profile failed: {e}")
        return {'poc': None, 'vah': None, 'val': None}


def detect_fvg(data):
    """
    Detect Fair Value Gaps (FVG)

    Args:
        data: dict with timeframe keys containing DataFrames

    Returns:
        tuple: (fvg_up, fvg_down) - Gap sizes or None
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 3:
            return None, None

        # Try cache: key by function name + length of DF
        cached = indicator_cache.get(('detect_fvg', 'H1'), len(df))
        if cached is not None:
            return cached

        # FVG occurs when there's a gap between candles
        prev_high = df['high'].iloc[-3]
        prev_low = df['low'].iloc[-3]
        curr_high = df['high'].iloc[-2]
        curr_low = df['low'].iloc[-2]
        next_high = df['high'].iloc[-1]
        next_low = df['low'].iloc[-1]

        # Bullish FVG: Gap up between candles
        fvg_up = None
        if curr_low > prev_high:
            fvg_up = curr_low - prev_high

        # Bearish FVG: Gap down between candles
        fvg_down = None
        if curr_high < prev_low:
            fvg_down = prev_low - curr_high

        # store to cache
        indicator_cache.set(('detect_fvg', 'H1'), len(df), (fvg_up, fvg_down))
        return fvg_up, fvg_down

    except Exception as e:
        logger.warning(f"⚠️ detect_fvg failed: {e}")
        return None, None


def detect_ob(data):
    """
    Detect Order Blocks

    Args:
        data: dict with timeframe keys containing DataFrames

    Returns:
        tuple: (bullish_ob, bearish_ob) - Order block levels or None
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 10:
            return None, None

        cached = indicator_cache.get(('detect_ob', 'H1'), len(df))
        if cached is not None:
            return cached

        # Simple order block detection based on volume and price rejection
        recent_volume = df['volume'].tail(10)
        avg_volume = recent_volume.mean()

        # Bullish OB: High volume candle with rejection from lows
        bullish_candles = df[(df['close'] > df['open']) & (df['volume'] > avg_volume)].tail(5)
        bullish_ob = bullish_candles['low'].min() if len(bullish_candles) > 0 else None

        # Bearish OB: High volume candle with rejection from highs
        bearish_candles = df[(df['close'] < df['open']) & (df['volume'] > avg_volume)].tail(5)
        bearish_ob = bearish_candles['high'].max() if len(bearish_candles) > 0 else None

        indicator_cache.set(('detect_ob', 'H1'), len(df), (bullish_ob, bearish_ob))
        return bullish_ob, bearish_ob

    except Exception as e:
        logger.warning(f"⚠️ detect_ob failed: {e}")
        return None, None


def liquidity_map(data):
    """
    Compute Liquidity Map (areas with high volume/orders)

    Args:
        data: dict with timeframe keys containing DataFrames

    Returns:
        dict: Liquidity levels or None
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 20:
            return None

        cached = indicator_cache.get(('liquidity_map', 'H1'), len(df))
        if cached is not None:
            return cached

        # Find areas with high volume concentration
        volume_threshold = df['volume'].quantile(0.8)  # Top 20% volume
        high_volume_areas = df[df['volume'] > volume_threshold]

        liquidity_levels = {
            'buy_liquidity': high_volume_areas['high'].max(),
            'sell_liquidity': high_volume_areas['low'].min(),
            'concentration_price': high_volume_areas['close'].mean()
        }

        indicator_cache.set(('liquidity_map', 'H1'), len(df), liquidity_levels)
        return liquidity_levels

    except Exception as e:
        logger.warning(f"⚠️ liquidity_map failed: {e}")
        return None


def detect_stop_hunt(data):
    """
    🔥 LIQUIDITY AI - Phát hiện săn thanh khoản (Stop Hunt)

    Logic:
    - Giá vừa quét SL đỉnh/đáy?
    - Có wick lớn không?
    - Có volume spike khi quét SL?

    Returns:
        dict: {
            'bullish_hunt': bool,  # Săn SL bán → khả năng đảo lên
            'bearish_hunt': bool,  # Săn SL mua → khả năng đảo xuống
            'wick_ratio': float,   # Tỷ lệ wick/body
            'volume_spike': bool   # Volume đột biến khi hunt
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 5:
            return {'bullish_hunt': False, 'bearish_hunt': False, 'wick_ratio': 0.0, 'volume_spike': False}

        cached = indicator_cache.get(('detect_stop_hunt', 'H1'), len(df))
        if cached is not None:
            return cached

        current = df.iloc[-1]
        prev = df.iloc[-2]

        # Tính wick ratio (đo lường stop hunt)
        body_size = abs(current['close'] - current['open'])
        total_range = current['high'] - current['low']

        if total_range == 0:
            wick_ratio = 0.0
        else:
            wick_ratio = (total_range - body_size) / total_range

        # Volume spike khi hunt
        avg_volume = df['volume'].rolling(10).mean().iloc[-1]
        volume_spike = current['volume'] > avg_volume * 1.8

        # Bullish hunt: Giá quét low rồi bật lên (wick dưới lớn)
        lower_wick = current['open'] - current['low'] if current['close'] > current['open'] else current['close'] - current['low']
        upper_wick = current['high'] - current['open'] if current['close'] > current['open'] else current['high'] - current['close']

        bullish_hunt = (
            wick_ratio > 0.7 and  # Wick > 70% range
            lower_wick > upper_wick * 2 and  # Wick dưới > 2x wick trên
            current['close'] > current['open'] and  # Nến tăng
            volume_spike  # Volume spike
        )

        # Bearish hunt: Giá quét high rồi rớt xuống
        bearish_hunt = (
            wick_ratio > 0.7 and
            upper_wick > lower_wick * 2 and  # Wick trên > 2x wick dưới
            current['close'] < current['open'] and  # Nến giảm
            volume_spike
        )

        result = {
            'bullish_hunt': bullish_hunt,
            'bearish_hunt': bearish_hunt,
            'wick_ratio': wick_ratio,
            'volume_spike': volume_spike
        }
        indicator_cache.set(('detect_stop_hunt', 'H1'), len(df), result)
        return result

    except Exception as e:
        logger.warning(f"⚠️ detect_stop_hunt failed: {e}")
        return {'bullish_hunt': False, 'bearish_hunt': False, 'wick_ratio': 0.0, 'volume_spike': False}


def detect_false_breakout(data):
    """
    🔥 LIQUIDITY AI - Phát hiện False Breakout

    Logic:
    - Giá phá đỉnh rồi quay xuống → khả năng đảo chiều cao
    - Giá phá đáy rồi bật mạnh → đảo chiều lên
    - Volume giảm khi breakout → fake breakout

    Returns:
        dict: {
            'bullish_false_breakout': bool,  # Fake breakout lên → đảo xuống
            'bearish_false_breakout': bool,  # Fake breakout xuống → đảo lên
            'breakout_strength': float       # Độ mạnh của breakout (0-1)
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 10:
            return {'bullish_false_breakout': False, 'bearish_false_breakout': False, 'breakout_strength': 0.0}

        # Tìm recent high/low
        recent_high = df['high'].rolling(10).max().iloc[-1]
        recent_low = df['low'].rolling(10).min().iloc[-1]
        current = df.iloc[-1]

        # Bullish false breakout: Phá high rồi đóng dưới high
        bullish_false_breakout = (
            current['high'] > recent_high and  # Phá đỉnh
            current['close'] < recent_high and  # Đóng dưới đỉnh
            current['close'] < current['open']  # Nến giảm
        )

        # Bearish false breakout: Phá low rồi đóng trên low
        bearish_false_breakout = (
            current['low'] < recent_low and  # Phá đáy
            current['close'] > recent_low and  # Đóng trên đáy
            current['close'] > current['open']  # Nến tăng
        )

        # Breakout strength dựa trên volume và range
        avg_volume = df['volume'].rolling(10).mean().iloc[-1]
        avg_range = (df['high'] - df['low']).rolling(10).mean().iloc[-1]
        current_range = current['high'] - current['low']

        volume_ratio = current['volume'] / avg_volume if avg_volume > 0 else 1.0
        range_ratio = current_range / avg_range if avg_range > 0 else 1.0

        breakout_strength = min(1.0, (volume_ratio + range_ratio) / 2.0)

        return {
            'bullish_false_breakout': bullish_false_breakout,
            'bearish_false_breakout': bearish_false_breakout,
            'breakout_strength': breakout_strength
        }

    except Exception as e:
        logger.warning(f"⚠️ detect_false_breakout failed: {e}")
        return {'bullish_false_breakout': False, 'bearish_false_breakout': False, 'breakout_strength': 0.0}


def detect_order_blocks(data):
    """
    🔥 ORDER BLOCK REVERSAL DETECTION

    Logic:
    - Bullish OB: High volume candle với rejection from lows
    - Bearish OB: High volume candle với rejection from highs
    - OB = nơi big player mở lệnh → đảo chiều mạnh

    Returns:
        tuple: (bullish_ob_level, bearish_ob_level) - OB levels or None
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 10:
            return None, None

        cached = indicator_cache.get(('detect_order_blocks', 'H1'), len(df))
        if cached is not None:
            return cached

        # Tìm high volume candles (top 20% volume)
        volume_threshold = df['volume'].quantile(0.8)
        high_volume_candles = df[df['volume'] > volume_threshold].tail(10)  # Recent 10 high vol candles

        bullish_ob = None
        bearish_ob = None

        # Bullish OB: High volume bullish candle (big players buying)
        bullish_candidates = high_volume_candles[high_volume_candles['close'] > high_volume_candles['open']]
        if len(bullish_candidates) > 0:
            # OB level = low của nến bullish mạnh nhất
            strongest_bullish = bullish_candidates.loc[bullish_candidates['volume'].idxmax()]
            bullish_ob = strongest_bullish['low']

        # Bearish OB: High volume bearish candle (big players selling)
        bearish_candidates = high_volume_candles[high_volume_candles['close'] < high_volume_candles['open']]
        if len(bearish_candidates) > 0:
            # OB level = high của nến bearish mạnh nhất
            strongest_bearish = bearish_candidates.loc[bearish_candidates['volume'].idxmax()]
            bearish_ob = strongest_bearish['high']

        indicator_cache.set(('detect_order_blocks', 'H1'), len(df), (bullish_ob, bearish_ob))
        return bullish_ob, bearish_ob

    except Exception as e:
        logger.warning(f"⚠️ detect_order_blocks failed: {e}")
        return None, None


def detect_volume_climax(data):
    """
    🔥 VOLUME CLIMAX + DELTA VOLUME

    Logic:
    - Climax Volume: Volume đột biến → hết lực
    - Giá tăng + volume giảm → đảo chiều xuống
    - Giá giảm + volume tăng mạnh → trap → đảo chiều lên

    Returns:
        dict: {
            'climax_up': bool,     # Climax khi tăng giá
            'climax_down': bool,   # Climax khi giảm giá
            'volume_trend': str,   # 'increasing', 'decreasing', 'neutral'
            'delta_ratio': float   # Volume delta ratio
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 20:
            return {'climax_up': False, 'climax_down': False, 'volume_trend': 'neutral', 'delta_ratio': 0.0}

        # Volume trend (5-period vs 20-period average)
        vol_5 = df['volume'].rolling(5).mean().iloc[-1]
        vol_20 = df['volume'].rolling(20).mean().iloc[-1]

        if vol_5 > vol_20 * 1.5:
            volume_trend = 'increasing'
        elif vol_5 < vol_20 * 0.7:
            volume_trend = 'decreasing'
        else:
            volume_trend = 'neutral'

        # Delta ratio (recent volume vs average)
        current_vol = df['volume'].iloc[-1]
        avg_vol = df['volume'].rolling(20).mean().iloc[-1]
        delta_ratio = current_vol / avg_vol if avg_vol > 0 else 1.0

        # Climax detection
        current = df.iloc[-1]
        climax_up = (
            current['close'] > current['open'] and  # Nến tăng
            delta_ratio > 2.0 and  # Volume > 2x average
            volume_trend == 'increasing'  # Volume đang tăng
        )

        climax_down = (
            current['close'] < current['open'] and  # Nến giảm
            delta_ratio > 2.0 and  # Volume > 2x average
            volume_trend == 'increasing'  # Volume đang tăng
        )

        return {
            'climax_up': climax_up,
            'climax_down': climax_down,
            'volume_trend': volume_trend,
            'delta_ratio': delta_ratio
        }

    except Exception as e:
        logger.warning(f"⚠️ detect_volume_climax failed: {e}")
        return {'climax_up': False, 'climax_down': False, 'volume_trend': 'neutral', 'delta_ratio': 0.0}


def detect_exhaustion(data):
    """
    🔥 EXHAUSTION VOLUME - Cạn lực

    Logic:
    - Volume tăng đột biến rồi giảm mạnh
    - Giá không đổi nhưng volume kiệt
    - Signe hết lực đẩy

    Returns:
        dict: {
            'bullish_exhaustion': bool,  # Hết lực tăng
            'bearish_exhaustion': bool,  # Hết lực giảm
            'exhaustion_level': float    # Mức độ exhaustion (0-1)
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 30:
            return {'bullish_exhaustion': False, 'bearish_exhaustion': False, 'exhaustion_level': 0.0}

        # Volume pattern: High volume spike followed by declining volume
        vol_3 = df['volume'].rolling(3).mean()
        vol_10 = df['volume'].rolling(10).mean()

        # Recent volume spike (last 3 candles)
        recent_spike = vol_3.iloc[-1] > vol_10.iloc[-1] * 1.5

        # Volume declining after spike
        vol_trend = vol_3.iloc[-1] < vol_3.iloc[-3]  # Volume giảm trong 3 kỳ gần nhất

        current = df.iloc[-1]
        exhaustion_level = 0.0

        # Calculate exhaustion level
        if recent_spike:
            vol_drop = (vol_3.iloc[-3] - vol_3.iloc[-1]) / vol_3.iloc[-3] if vol_3.iloc[-3] > 0 else 0
            exhaustion_level = min(1.0, vol_drop)

        bullish_exhaustion = (
            recent_spike and
            vol_trend and
            current['close'] > current['open'] and  # Nến tăng nhưng volume giảm
            exhaustion_level > 0.6
        )

        bearish_exhaustion = (
            recent_spike and
            vol_trend and
            current['close'] < current['open'] and  # Nến giảm nhưng volume giảm
            exhaustion_level > 0.6
        )

        return {
            'bullish_exhaustion': bullish_exhaustion,
            'bearish_exhaustion': bearish_exhaustion,
            'exhaustion_level': exhaustion_level
        }

    except Exception as e:
        logger.warning(f"⚠️ detect_exhaustion failed: {e}")
        return {'bullish_exhaustion': False, 'bearish_exhaustion': False, 'exhaustion_level': 0.0}


def calculate_delta(data):
    """
    🔥 DELTA VOLUME - Volume mua/bán thật

    Logic:
    - Delta = Volume mua - Volume bán
    - Positive delta: Mua mạnh
    - Negative delta: Bán mạnh

    Returns:
        dict: {
            'delta': float,           # Net delta
            'delta_trend': str,       # 'bullish', 'bearish', 'neutral'
            'cumulative_delta': float # Tích lũy delta
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 20:
            return {'delta': 0.0, 'delta_trend': 'neutral', 'cumulative_delta': 0.0}

        # Simplified delta calculation based on price direction and volume
        # Bullish candle = buying volume, Bearish candle = selling volume
        df_copy = df.copy()
        df_copy['buy_volume'] = df_copy.apply(lambda x: x['volume'] if x['close'] > x['open'] else 0, axis=1)
        df_copy['sell_volume'] = df_copy.apply(lambda x: x['volume'] if x['close'] < x['open'] else 0, axis=1)

        # Current delta
        current_buy = df_copy['buy_volume'].iloc[-1]
        current_sell = df_copy['sell_volume'].iloc[-1]
        delta = current_buy - current_sell

        # Cumulative delta (recent 10 candles)
        cum_buy = df_copy['buy_volume'].tail(10).sum()
        cum_sell = df_copy['sell_volume'].tail(10).sum()
        cumulative_delta = cum_buy - cum_sell

        # Delta trend
        if cumulative_delta > 0:
            delta_trend = 'bullish'
        elif cumulative_delta < 0:
            delta_trend = 'bearish'
        else:
            delta_trend = 'neutral'

        return {
            'delta': delta,
            'delta_trend': delta_trend,
            'cumulative_delta': cumulative_delta
        }

    except Exception as e:
        logger.warning(f"⚠️ calculate_delta failed: {e}")
        return {'delta': 0.0, 'delta_trend': 'neutral', 'cumulative_delta': 0.0}


def detect_momentum_shift(data):
    """
    🔥 MOMENTUM SHIFT AI - Mắt thần của bot

    Logic:
    - Tốc độ thay đổi giá
    - Gia tốc của giá
    - Độ dốc EMA
    - Volume change

    Returns:
        dict: {
            'momentum_shift': bool,     # Có shift momentum không
            'shift_direction': str,     # 'bull_to_bear', 'bear_to_bull', 'none'
            'momentum_strength': float, # Độ mạnh của momentum (0-1)
            'acceleration': float       # Gia tốc giá
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 20:
            return {'momentum_shift': False, 'shift_direction': 'none', 'momentum_strength': 0.0, 'acceleration': 0.0}

        # Calculate momentum indicators
        df_copy = df.copy()

        # Price momentum (rate of change)
        df_copy['price_momentum'] = df_copy['close'].pct_change(5)

        # Volume momentum
        df_copy['volume_momentum'] = df_copy['volume'].pct_change(5)

        # EMA slope (trend acceleration)
        df_copy['ema20'] = df_copy['close'].ewm(span=20).mean()
        df_copy['ema_slope'] = df_copy['ema20'].diff(3)  # Slope over 3 periods

        # Acceleration (second derivative of price)
        df_copy['price_velocity'] = df_copy['close'].diff(1)
        df_copy['price_acceleration'] = df_copy['price_velocity'].diff(1)

        current = df_copy.iloc[-1]
        prev = df_copy.iloc[-2]

        # Momentum shift detection
        momentum_shift = False
        shift_direction = 'none'

        # Bull to bear shift: Price increasing but momentum decreasing
        bull_to_bear = (
            current['price_momentum'] < prev['price_momentum'] and  # Momentum giảm
            current['ema_slope'] < 0 and  # EMA slope negative
            current['volume_momentum'] > 0 and  # Volume tăng (distribution)
            current['close'] < current['open']  # Nến giảm
        )

        # Bear to bull shift: Price decreasing but momentum increasing
        bear_to_bull = (
            current['price_momentum'] > prev['price_momentum'] and  # Momentum tăng
            current['ema_slope'] > 0 and  # EMA slope positive
            current['volume_momentum'] > 0 and  # Volume tăng (accumulation)
            current['close'] > current['open']  # Nến tăng
        )

        if bull_to_bear:
            momentum_shift = True
            shift_direction = 'bull_to_bear'
        elif bear_to_bull:
            momentum_shift = True
            shift_direction = 'bear_to_bull'

        # Momentum strength (0-1)
        momentum_strength = abs(current['price_momentum']) / 0.05  # Normalize to 5% change
        momentum_strength = min(1.0, momentum_strength)

        return {
            'momentum_shift': momentum_shift,
            'shift_direction': shift_direction,
            'momentum_strength': momentum_strength,
            'acceleration': current['price_acceleration']
        }

    except Exception as e:
        logger.warning(f"⚠️ detect_momentum_shift failed: {e}")
        return {'momentum_shift': False, 'shift_direction': 'none', 'momentum_strength': 0.0, 'acceleration': 0.0}


def detect_choch(data):
    """
    🔥 STRUCTURE BREAK REVERSAL (CHoCH) - Điểm quan trọng nhất trong SMC

    Logic:
    - HH → HL liên tục → đang tăng
    - Đột ngột tạo Lower Low → CHoCH → đảo chiều
    - Đây là tín hiệu đảo chiều mạnh nhất

    Returns:
        dict: {
            'choch_detected': bool,      # Có CHoCH không
            'choch_direction': str,      # 'bullish', 'bearish', 'none'
            'structure_break': bool,     # Có break structure không
            'break_strength': float      # Độ mạnh của break (0-1)
        }
    """
    try:
        df = data.get('H1')
        if df is None or len(df) < 20:
            return {'choch_detected': False, 'choch_direction': 'none', 'structure_break': False, 'break_strength': 0.0}

        # Detect HH/HL pattern
        highs = df['high']
        lows = df['low']

        # Higher Highs and Higher Lows (bullish structure)
        hh = highs.iloc[-1] > highs.iloc[-2] and highs.iloc[-2] > highs.iloc[-3]
        hl = lows.iloc[-1] > lows.iloc[-2] and lows.iloc[-2] > lows.iloc[-3]

        # Lower Highs and Lower Lows (bearish structure)
        lh = highs.iloc[-1] < highs.iloc[-2] and highs.iloc[-2] < highs.iloc[-3]
        ll = lows.iloc[-1] < lows.iloc[-2] and lows.iloc[-2] < lows.iloc[-3]

        current = df.iloc[-1]

        choch_detected = False
        choch_direction = 'none'
        structure_break = False
        break_strength = 0.0

        # Bullish CHoCH: In bearish structure (LH+LL), suddenly create Higher Low
        if lh and ll:
            # Check if current low breaks the downtrend
            recent_lows = lows.tail(5)
            if current['low'] > recent_lows.min():
                choch_detected = True
                choch_direction = 'bullish'
                structure_break = True
                break_strength = (current['low'] - recent_lows.min()) / recent_lows.min()

        # Bearish CHoCH: In bullish structure (HH+HL), suddenly create Lower High
        elif hh and hl:
            # Check if current high breaks the uptrend
            recent_highs = highs.tail(5)
            if current['high'] < recent_highs.max():
                choch_detected = True
                choch_direction = 'bearish'
                structure_break = True
                break_strength = (recent_highs.max() - current['high']) / recent_highs.max()

        return {
            'choch_detected': choch_detected,
            'choch_direction': choch_direction,
            'structure_break': structure_break,
            'break_strength': break_strength
        }

    except Exception as e:
        logger.warning(f"⚠️ detect_choch failed: {e}")
        return {'choch_detected': False, 'choch_direction': 'none', 'structure_break': False, 'break_strength': 0.0}
