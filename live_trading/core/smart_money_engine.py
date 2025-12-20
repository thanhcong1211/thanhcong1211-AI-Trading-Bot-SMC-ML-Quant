"""
Smart Money Concepts + Price Action Engine - NÂNG CẤP
========================================================
Tính năng chính:
- Phát hiện Order Blocks (OB), Fair Value Gaps (FVG), Liquidity Sweeps
- Break Of Structure (BOS) / Change of Character (CHoCH)
- Phát hiện NHỊP XẢ NGƯỢC XU HƯỚNG (liquidity grab) -> Entry point tốt
- Xác nhận Price Action (Pinbar, Engulfing, Inside Bar, Rejection)
- Tính SL/TP thông minh dựa ATR + structure levels
- Tích hợp với RiskAI, ExecutionAI, MoneyManager

Tác giả: AI Trading System
Ngày: 2025-12-04
"""

from typing import Dict, Any, Optional, Tuple, List
import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# Optional imports
try:
    from core.money_management import AIMoneyManager
except ImportError:
    AIMoneyManager = None

# ========================
# INDICATORS & HELPERS
# ========================

def atr(series_high: pd.Series, series_low: pd.Series, series_close: pd.Series, period: int = 14) -> pd.Series:
    """Tính ATR (Average True Range)"""
    h_l = series_high - series_low
    h_c = (series_high - series_close.shift(1)).abs()
    l_c = (series_low - series_close.shift(1)).abs()
    tr = pd.concat([h_l, h_c, l_c], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()

def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple Moving Average"""
    return series.rolling(period, min_periods=1).mean()

def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential Moving Average"""
    return series.ewm(span=period, adjust=False).mean()

def swing_highs_lows(df: pd.DataFrame, window: int = 5) -> Tuple[pd.Series, pd.Series]:
    """
    Tìm swing highs và swing lows
    Return: (swing_highs, swing_lows) - Series with NaN where not swing
    """
    highs = df['high'].rolling(window=2*window+1, center=True).apply(
        lambda x: x[window] if x[window] == x.max() else np.nan, raw=True
    )
    lows = df['low'].rolling(window=2*window+1, center=True).apply(
        lambda x: x[window] if x[window] == x.min() else np.nan, raw=True
    )
    return highs, lows

# ========================
# SMC DETECTION
# ========================

def detect_order_blocks(df: pd.DataFrame, lookback: int = 50) -> List[Dict[str, Any]]:
    """
    Phát hiện Order Blocks (OB):
    - Tìm candle có body nhỏ (base) + candle tiếp theo move mạnh
    - OB = vùng mà smart money đã đặt lệnh trước khi đẩy giá
    """
    obs = []
    n = len(df)
    if n < 3:
        return obs
    
    close = df['close'].values
    open_ = df['open'].values
    high = df['high'].values
    low = df['low'].values
    
    atr_series = atr(df['high'], df['low'], df['close'], period=14).fillna(0.0001).values
    
    for i in range(2, min(n, lookback)):
        # Body sizes
        body_prev = abs(close[i-1] - open_[i-1])
        body_curr = abs(close[i] - open_[i])
        
        # Detect strong move
        move_size = abs(close[i] - open_[i])
        
        # OB conditions: small body followed by large directional move
        if body_prev < 0.4 * body_curr and move_size > 0.5 * atr_series[i]:
            
            # Bullish OB: bearish base candle + strong bullish move
            if close[i-1] < open_[i-1] and close[i] > open_[i]:
                obs.append({
                    'type': 'bull',
                    'start_idx': i-1,
                    'end_idx': i,
                    'level_low': min(low[i-1:i+1]),
                    'level_high': max(high[i-1:i+1]),
                    'strength': move_size / atr_series[i]
                })
            
            # Bearish OB: bullish base candle + strong bearish move
            elif close[i-1] > open_[i-1] and close[i] < open_[i]:
                obs.append({
                    'type': 'bear',
                    'start_idx': i-1,
                    'end_idx': i,
                    'level_low': min(low[i-1:i+1]),
                    'level_high': max(high[i-1:i+1]),
                    'strength': move_size / atr_series[i]
                })
    
    return obs[-10:]  # Chỉ giữ 10 OB gần nhất

def detect_fvg(df: pd.DataFrame, lookback: int = 100) -> List[Dict[str, Any]]:
    """
    Phát hiện Fair Value Gaps (FVG):
    - Gap giữa 3 candle liên tiếp A-B-C
    - FVG = vùng chưa được fill, thường được test lại
    """
    fvg_list = []
    n = len(df)
    
    if n < 3:
        return fvg_list
    
    high = df['high'].values
    low = df['low'].values
    
    for i in range(2, min(n, lookback)):
        # Bullish FVG: gap between A.high and C.low
        if low[i] > high[i-2]:
            gap_low = high[i-2]
            gap_high = low[i]
            gap_size = gap_high - gap_low
            
            fvg_list.append({
                'type': 'bull',
                'start_idx': i-2,
                'end_idx': i,
                'gap_low': gap_low,
                'gap_high': gap_high,
                'gap_size': gap_size
            })
        
        # Bearish FVG: gap between A.low and C.high
        if high[i] < low[i-2]:
            gap_low = high[i]
            gap_high = low[i-2]
            gap_size = gap_high - gap_low
            
            fvg_list.append({
                'type': 'bear',
                'start_idx': i-2,
                'end_idx': i,
                'gap_low': gap_low,
                'gap_high': gap_high,
                'gap_size': gap_size
            })
    
    return fvg_list[-10:]  # Chỉ giữ 10 FVG gần nhất

def detect_liquidity_sweep_advanced(df: pd.DataFrame, lookback: int = 20) -> Optional[Dict[str, Any]]:
    """
    NÂNG CẤP: Phát hiện NHỊP XẢ/SWEEP NGƯỢC XU HƯỚNG
    
    Dấu hiệu liquidity grab (sweep):
    1. Giá xuyên qua swing high/low gần đây
    2. Volume spike tại candle sweep
    3. Wick dài (rejection) - giá quay lại nhanh
    4. Candle tiếp theo đóng ngược lại (confirmation)
    
    -> ĐÂY LÀ ENTRY POINT TỐT: Smart money đã sweep liquidity và bắt đầu move theo hướng thật
    """
    n = len(df)
    if n < lookback + 3:
        return None
    
    recent = df.iloc[-lookback:]
    
    # Tính swing highs/lows trong recent period
    swing_high = recent['high'].rolling(5, center=True).max()
    swing_low = recent['low'].rolling(5, center=True).min()
    
    last_swing_high = swing_high.dropna().iloc[-1] if len(swing_high.dropna()) > 0 else recent['high'].max()
    last_swing_low = swing_low.dropna().iloc[-1] if len(swing_low.dropna()) > 0 else recent['low'].min()
    
    # Check 2 candles cuối
    if n < 2:
        return None
    
    prev = df.iloc[-2]
    last = df.iloc[-1]
    
    # Volume analysis
    vol = df['volume'] if 'volume' in df.columns else pd.Series(np.ones(len(df)))
    vol_avg = vol.iloc[-20:].mean() if len(vol) > 20 else vol.mean()
    vol_spike = (prev['volume'] if 'volume' in prev.index else 1) > vol_avg * 1.5
    
    # ATR for wick measurement
    atr_val = atr(df['high'], df['low'], df['close'], period=14).iloc[-1]
    
    # Measure wicks
    prev_body_top = max(prev['open'], prev['close'])
    prev_body_bottom = min(prev['open'], prev['close'])
    prev_upper_wick = prev['high'] - prev_body_top
    prev_lower_wick = prev_body_bottom - prev['low']
    
    last_body_top = max(last['open'], last['close'])
    last_body_bottom = min(last['open'], last['close'])
    
    sweep_result = None
    
    # ===== BULLISH SWEEP (Lower wick xuyên swing low rồi close lên) =====
    if prev['low'] < last_swing_low * 0.9995:  # Xuyên qua swing low
        if prev_lower_wick > 1.2 * atr_val:  # Wick dài
            if vol_spike:  # Volume spike
                if last['close'] > prev['close']:  # Candle tiếp theo close cao hơn (confirmation)
                    sweep_result = {
                        'sweep': True,
                        'direction': 'buy',
                        'type': 'liquidity_grab_bullish',
                        'idx': n-2,
                        'sweep_low': prev['low'],
                        'swing_low': last_swing_low,
                        'wick_size': prev_lower_wick / atr_val,
                        'volume_ratio': (prev['volume'] if 'volume' in prev.index else 1) / vol_avg,
                        'confirmation': 'next_candle_bullish',
                        'strength': min(3.0, (prev_lower_wick / atr_val) * 0.5 + 
                                     ((prev['volume'] if 'volume' in prev.index else 1) / vol_avg) * 0.3),
                        'entry_zone': (prev['low'], prev_body_bottom)
                    }
    
    # ===== BEARISH SWEEP (Upper wick xuyên swing high rồi close xuống) =====
    if prev['high'] > last_swing_high * 1.0005:  # Xuyên qua swing high
        if prev_upper_wick > 1.2 * atr_val:  # Wick dài
            if vol_spike:  # Volume spike
                if last['close'] < prev['close']:  # Candle tiếp theo close thấp hơn (confirmation)
                    sweep_result = {
                        'sweep': True,
                        'direction': 'sell',
                        'type': 'liquidity_grab_bearish',
                        'idx': n-2,
                        'sweep_high': prev['high'],
                        'swing_high': last_swing_high,
                        'wick_size': prev_upper_wick / atr_val,
                        'volume_ratio': (prev['volume'] if 'volume' in prev.index else 1) / vol_avg,
                        'confirmation': 'next_candle_bearish',
                        'strength': min(3.0, (prev_upper_wick / atr_val) * 0.5 + 
                                     ((prev['volume'] if 'volume' in prev.index else 1) / vol_avg) * 0.3),
                        'entry_zone': (prev_body_top, prev['high'])
                    }
    
    # Log if sweep detected
    if sweep_result:
        logger.info(f"🎯 LIQUIDITY SWEEP DETECTED: {sweep_result['type']} - "
                   f"Strength: {sweep_result['strength']:.2f} - "
                   f"Entry zone: {sweep_result['entry_zone']}")
    
    return sweep_result

def detect_false_breakout(df: pd.DataFrame, lookback: int = 20) -> Optional[Dict[str, Any]]:
    """
    Phát hiện FALSE BREAKOUT (dấu hiệu nhận biết):
    - Giá break qua resistance/support
    - Nhưng không sustain được (close lại trong range)
    - Volume thấp hoặc không có follow-through
    
    -> Signal ngược lại với breakout direction
    """
    n = len(df)
    if n < lookback + 2:
        return None
    
    recent = df.iloc[-lookback:]
    resistance = recent['high'].iloc[:-2].max()
    support = recent['low'].iloc[:-2].min()
    
    prev = df.iloc[-2]
    last = df.iloc[-1]
    
    vol = df['volume'] if 'volume' in df.columns else pd.Series(np.ones(len(df)))
    vol_avg = vol.iloc[-20:].mean()
    
    # False breakout UP (bullish fake -> actually bearish)
    if prev['high'] > resistance * 1.001:  # Break resistance
        if prev['close'] < resistance:  # But close back inside
            if last['close'] < prev['close']:  # Next candle continues down
                if (prev['volume'] if 'volume' in prev.index else 1) < vol_avg * 1.2:  # Low volume
                    return {
                        'false_breakout': True,
                        'direction': 'sell',
                        'type': 'false_breakout_up',
                        'resistance': resistance,
                        'fake_high': prev['high'],
                        'strength': 0.7,
                        'reason': 'break_up_but_close_inside_low_volume'
                    }
    
    # False breakout DOWN (bearish fake -> actually bullish)
    if prev['low'] < support * 0.999:  # Break support
        if prev['close'] > support:  # But close back inside
            if last['close'] > prev['close']:  # Next candle continues up
                if (prev['volume'] if 'volume' in prev.index else 1) < vol_avg * 1.2:  # Low volume
                    return {
                        'false_breakout': True,
                        'direction': 'buy',
                        'type': 'false_breakout_down',
                        'support': support,
                        'fake_low': prev['low'],
                        'strength': 0.7,
                        'reason': 'break_down_but_close_inside_low_volume'
                    }
    
    return None

# ========================
# MARKET STRUCTURE (BOS/CHoCH)
# ========================

def detect_market_structure(df: pd.DataFrame, pivot_window: int = 5) -> Dict[str, Any]:
    """
    Phát hiện cấu trúc thị trường:
    - Higher Highs + Higher Lows = Uptrend
    - Lower Highs + Lower Lows = Downtrend
    - BOS (Break of Structure) = phá vỡ cấu trúc hiện tại
    - CHoCH (Change of Character) = thay đổi xu hướng
    """
    n = len(df)
    if n < pivot_window * 3:
        return {'structure': 'neutral', 'bos': False, 'choch': False, 'confidence': 0.0}
    
    swing_highs, swing_lows = swing_highs_lows(df, window=pivot_window)
    
    # Get last few swings
    highs = swing_highs.dropna()
    lows = swing_lows.dropna()
    
    if len(highs) < 2 or len(lows) < 2:
        return {'structure': 'neutral', 'bos': False, 'choch': False, 'confidence': 0.0}
    
    # Analyze trend
    last_2_highs = highs.iloc[-2:]
    last_2_lows = lows.iloc[-2:]
    
    hh = last_2_highs.iloc[-1] > last_2_highs.iloc[-2]  # Higher High
    hl = last_2_lows.iloc[-1] > last_2_lows.iloc[-2]     # Higher Low
    lh = last_2_highs.iloc[-1] < last_2_highs.iloc[-2]  # Lower High
    ll = last_2_lows.iloc[-1] < last_2_lows.iloc[-2]     # Lower Low
    
    structure = 'neutral'
    bos = False
    choch = False
    confidence = 0.5
    
    # Uptrend
    if hh and hl:
        structure = 'bull'
        confidence = 0.8
        bos = True  # Broke above previous high
    
    # Downtrend
    elif lh and ll:
        structure = 'bear'
        confidence = 0.8
        bos = True  # Broke below previous low
    
    # Change of Character
    elif (hh and ll) or (lh and hl):
        choch = True
        confidence = 0.6
        if hh and ll:
            structure = 'bear_choch'  # Was bull, now turning bear
        else:
            structure = 'bull_choch'  # Was bear, now turning bull
    
    return {
        'structure': structure,
        'bos': bos,
        'choch': choch,
        'confidence': confidence,
        'last_swing_high': float(highs.iloc[-1]),
        'last_swing_low': float(lows.iloc[-1])
    }

# ========================
# PRICE ACTION PATTERNS
# ========================

def is_pinbar(row: pd.Series, body_ratio: float = 0.3, wick_ratio: float = 2.5) -> Dict[str, Any]:
    """
    Pinbar detection với chi tiết
    Return: {'is_pinbar': bool, 'direction': 'bull'|'bear'|None, 'strength': float}
    """
    o, c, h, l = row['open'], row['close'], row['high'], row['low']
    body = abs(c - o)
    total_range = h - l
    
    if total_range == 0:
        return {'is_pinbar': False, 'direction': None, 'strength': 0.0}
    
    body_pct = body / total_range
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    
    # Bullish pinbar: long lower wick, small body
    if lower_wick > body * wick_ratio and upper_wick < body and body_pct < body_ratio:
        return {
            'is_pinbar': True,
            'direction': 'bull',
            'strength': min(1.0, lower_wick / (body + 0.0001) / 5.0),
            'rejection_level': l
        }
    
    # Bearish pinbar: long upper wick, small body
    if upper_wick > body * wick_ratio and lower_wick < body and body_pct < body_ratio:
        return {
            'is_pinbar': True,
            'direction': 'bear',
            'strength': min(1.0, upper_wick / (body + 0.0001) / 5.0),
            'rejection_level': h
        }
    
    return {'is_pinbar': False, 'direction': None, 'strength': 0.0}

def is_engulfing(prev: pd.Series, curr: pd.Series) -> Dict[str, Any]:
    """Engulfing pattern detection"""
    prev_bull = prev['close'] > prev['open']
    curr_bull = curr['close'] > curr['open']
    
    # Bullish engulfing
    if not prev_bull and curr_bull:
        if curr['close'] > prev['open'] and curr['open'] < prev['close']:
            return {'is_engulfing': True, 'direction': 'bull', 'strength': 0.8}
    
    # Bearish engulfing
    if prev_bull and not curr_bull:
        if curr['open'] > prev['close'] and curr['close'] < prev['open']:
            return {'is_engulfing': True, 'direction': 'bear', 'strength': 0.8}
    
    return {'is_engulfing': False, 'direction': None, 'strength': 0.0}

def price_action_confirm(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Tổng hợp xác nhận Price Action
    Return: các patterns detected và confidence tổng hợp
    """
    n = len(df)
    if n < 2:
        return {'confirmed': False, 'patterns': [], 'confidence': 0.0, 'direction': None}
    
    last = df.iloc[-1]
    prev = df.iloc[-2]
    
    patterns = []
    total_conf = 0.0
    directions = []
    
    # Check pinbar
    pinbar = is_pinbar(last)
    if pinbar['is_pinbar']:
        patterns.append({'type': 'pinbar', **pinbar})
        total_conf += pinbar['strength'] * 0.4
        directions.append(pinbar['direction'])
    
    # Check engulfing
    engulfing = is_engulfing(prev, last)
    if engulfing['is_engulfing']:
        patterns.append({'type': 'engulfing', **engulfing})
        total_conf += engulfing['strength'] * 0.5
        directions.append(engulfing['direction'])
    
    # Check inside bar
    if last['high'] <= prev['high'] and last['low'] >= prev['low']:
        patterns.append({'type': 'inside_bar', 'strength': 0.3})
        total_conf += 0.15
    
    # Determine consensus direction
    direction = None
    if directions:
        bull_count = directions.count('bull')
        bear_count = directions.count('bear')
        if bull_count > bear_count:
            direction = 'bull'
        elif bear_count > bull_count:
            direction = 'bear'
    
    confirmed = len(patterns) > 0
    confidence = min(1.0, total_conf)
    
    return {
        'confirmed': confirmed,
        'patterns': patterns,
        'confidence': confidence,
        'direction': direction
    }

# ========================
# SL/TP CALCULATION
# ========================

def compute_sl_tp_smart(entry: float, side: str, df: pd.DataFrame, 
                        structure: Dict[str, Any], 
                        obs: List[Dict], 
                        fvgs: List[Dict],
                        atr_multiplier: float = 1.5,
                        rr_ratio: float = 2.0) -> Tuple[float, float]:
    """
    Tính SL/TP thông minh dựa trên:
    1. Structure levels (swing high/low)
    2. Order Block levels
    3. ATR
    4. Risk:Reward ratio
    """
    atr_val = atr(df['high'], df['low'], df['close'], period=14).iloc[-1]
    
    if side == 'buy':
        # SL: dưới structure low hoặc OB level
        sl_candidates = []
        
        # ATR-based
        sl_candidates.append(entry - atr_val * atr_multiplier)
        
        # Structure-based
        if 'last_swing_low' in structure:
            sl_candidates.append(structure['last_swing_low'] - atr_val * 0.2)
        
        # OB-based
        for ob in obs:
            if ob['type'] == 'bull' and ob['level_low'] < entry:
                sl_candidates.append(ob['level_low'] - atr_val * 0.1)
        
        # Choose tightest reasonable SL
        sl = max(sl_candidates) if sl_candidates else entry - atr_val * atr_multiplier
        
        # TP: trên structure high hoặc FVG
        tp_candidates = []
        tp_candidates.append(entry + (entry - sl) * rr_ratio)
        
        if 'last_swing_high' in structure and structure['last_swing_high'] > entry:
            tp_candidates.append(structure['last_swing_high'])
        
        for fvg in fvgs:
            if fvg['type'] == 'bear' and fvg['gap_low'] > entry:
                tp_candidates.append(fvg['gap_low'])
        
        tp = min([t for t in tp_candidates if t > entry], default=entry + (entry - sl) * rr_ratio)
    
    else:  # sell
        # SL: trên structure high hoặc OB level
        sl_candidates = []
        
        # ATR-based
        sl_candidates.append(entry + atr_val * atr_multiplier)
        
        # Structure-based
        if 'last_swing_high' in structure:
            sl_candidates.append(structure['last_swing_high'] + atr_val * 0.2)
        
        # OB-based
        for ob in obs:
            if ob['type'] == 'bear' and ob['level_high'] > entry:
                sl_candidates.append(ob['level_high'] + atr_val * 0.1)
        
        # Choose tightest reasonable SL
        sl = min(sl_candidates) if sl_candidates else entry + atr_val * atr_multiplier
        
        # TP: dưới structure low hoặc FVG
        tp_candidates = []
        tp_candidates.append(entry - (sl - entry) * rr_ratio)
        
        if 'last_swing_low' in structure and structure['last_swing_low'] < entry:
            tp_candidates.append(structure['last_swing_low'])
        
        for fvg in fvgs:
            if fvg['type'] == 'bull' and fvg['gap_high'] < entry:
                tp_candidates.append(fvg['gap_high'])
        
        tp = max([t for t in tp_candidates if t < entry], default=entry - (sl - entry) * rr_ratio)
    
    return float(sl), float(tp)

# ========================
# MAIN DECISION GENERATOR
# ========================

def generate_trade_decision(df: pd.DataFrame,
                           symbol: str,
                           context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    MAIN ENTRY POINT - Tạo quyết định trading
    
    Context có thể chứa:
    - risk_check: callable để check risk
    - execution_check: callable để check execution
    - portfolio_check: callable để check portfolio
    - money_manager: AIMoneyManager instance
    - enter_threshold: ngưỡng confidence để vào lệnh (default 0.6)
    - atr_multiplier: multiplier cho ATR SL (default 1.5)
    - rr_ratio: Risk:Reward ratio (default 2.0)
    """
    if context is None:
        context = {}
    
    # Defensive checks
    if not {'open', 'high', 'low', 'close'}.issubset(df.columns):
        return {
            'side': 'none',
            'type': 'none',
            'entry': None,
            'sl': None,
            'tp': None,
            'confidence': 0.0,
            'reasons': ['missing_ohlc'],
            'meta': {},
            'blocked': True,
            'blocked_reason': 'missing_ohlc_columns'
        }
    
    if len(df) < 50:
        return {
            'side': 'none',
            'type': 'none',
            'entry': None,
            'sl': None,
            'tp': None,
            'confidence': 0.0,
            'reasons': ['insufficient_data'],
            'meta': {},
            'blocked': True,
            'blocked_reason': 'need_at_least_50_bars'
        }
    
    reasons = []
    
    # ========== 1. DETECT SMC COMPONENTS ==========
    logger.info("🔍 Analyzing SMC components...")
    
    structure = detect_market_structure(df)
    reasons.append(f"structure:{structure['structure']}")
    
    obs = detect_order_blocks(df)
    if obs:
        reasons.append(f"order_blocks:{len(obs)}")
    
    fvgs = detect_fvg(df)
    if fvgs:
        reasons.append(f"fvgs:{len(fvgs)}")
    
    # ========== 2. DETECT LIQUIDITY SWEEP (KEY SIGNAL) ==========
    sweep = detect_liquidity_sweep_advanced(df)
    if sweep and sweep.get('sweep'):
        reasons.append(f"LIQUIDITY_SWEEP:{sweep['type']}")
        logger.info(f"🎯 LIQUIDITY SWEEP: {sweep['type']} - Strength: {sweep.get('strength', 0):.2f}")
    
    # ========== 3. DETECT FALSE BREAKOUT ==========
    false_bo = detect_false_breakout(df)
    if false_bo and false_bo.get('false_breakout'):
        reasons.append(f"FALSE_BREAKOUT:{false_bo['type']}")
        logger.info(f"⚠️ FALSE BREAKOUT: {false_bo['type']}")
    
    # ========== 4. PRICE ACTION CONFIRMATION ==========
    pa = price_action_confirm(df)
    if pa['confirmed']:
        patterns_str = ','.join([p['type'] for p in pa['patterns']])
        reasons.append(f"PA:{patterns_str}")
    
    # ========== 5. SCORING SYSTEM ==========
    bull_score = 0.0
    bear_score = 0.0
    
    # Structure scoring
    if structure['structure'] == 'bull':
        bull_score += 0.25
    elif structure['structure'] == 'bear':
        bear_score += 0.25
    elif structure['structure'] == 'bull_choch':
        bull_score += 0.35  # CHoCH có điểm cao hơn
    elif structure['structure'] == 'bear_choch':
        bear_score += 0.35
    
    # LIQUIDITY SWEEP scoring (HIGHEST PRIORITY)
    if sweep and sweep.get('sweep'):
        sweep_strength = sweep.get('strength', 0.5)
        if sweep['direction'] == 'buy':
            bull_score += min(0.6, sweep_strength * 0.4)  # Có thể lên đến 0.6 điểm
            reasons.append(f"sweep_bull_strength:{sweep_strength:.2f}")
        elif sweep['direction'] == 'sell':
            bear_score += min(0.6, sweep_strength * 0.4)
            reasons.append(f"sweep_bear_strength:{sweep_strength:.2f}")
    
    # FALSE BREAKOUT scoring
    if false_bo and false_bo.get('false_breakout'):
        fb_strength = false_bo.get('strength', 0.5)
        if false_bo['direction'] == 'buy':
            bull_score += fb_strength * 0.3
        elif false_bo['direction'] == 'sell':
            bear_score += fb_strength * 0.3
    
    # Order Block proximity scoring
    last_price = df['close'].iloc[-1]
    for ob in obs[-5:]:  # Check 5 OBs gần nhất
        ob_mid = (ob['level_low'] + ob['level_high']) / 2
        distance_pct = abs(last_price - ob_mid) / last_price
        
        if distance_pct < 0.002:  # Trong vùng OB (0.2%)
            if ob['type'] == 'bull':
                bull_score += min(0.3, ob.get('strength', 1.0) * 0.15)
            else:
                bear_score += min(0.3, ob.get('strength', 1.0) * 0.15)
    
    # FVG proximity scoring
    for fvg in fvgs[-5:]:
        fvg_mid = (fvg['gap_low'] + fvg['gap_high']) / 2
        distance_pct = abs(last_price - fvg_mid) / last_price
        
        if distance_pct < 0.003:  # Trong vùng FVG (0.3%)
            if fvg['type'] == 'bull':
                bull_score += 0.2
            else:
                bear_score += 0.2
    
    # Price Action scoring
    if pa['confirmed']:
        pa_conf = pa['confidence']
        if pa['direction'] == 'bull':
            bull_score += pa_conf * 0.35
        elif pa['direction'] == 'bear':
            bear_score += pa_conf * 0.35
    
    # ========== 6. MAKE DECISION ==========
    total_score = bull_score + bear_score + 1e-9
    bull_conf = bull_score / total_score
    bear_conf = bear_score / total_score
    
    enter_threshold = context.get('enter_threshold', 0.6)  # Cần >60% confidence
    
    chosen_side = 'none'
    chosen_conf = 0.0
    
    if bull_conf > enter_threshold:
        chosen_side = 'buy'
        chosen_conf = bull_conf
    elif bear_conf > enter_threshold:
        chosen_side = 'sell'
        chosen_conf = bear_conf
    
    if chosen_side == 'none':
        return {
            'side': 'none',
            'type': 'none',
            'entry': None,
            'sl': None,
            'tp': None,
            'confidence': max(bull_conf, bear_conf),
            'reasons': reasons + [f"bull:{bull_score:.2f}", f"bear:{bear_score:.2f}", "below_threshold"],
            'meta': {
                'structure': structure,
                'obs': obs,
                'fvgs': fvgs,
                'sweep': sweep,
                'false_breakout': false_bo,
                'pa': pa
            },
            'blocked': False,
            'blocked_reason': None
        }
    
    # ========== 7. DETERMINE ENTRY PRICE & TYPE ==========
    entry_price = last_price
    entry_type = 'market'
    prefer_limit = context.get('prefer_limit', True)
    
    # Nếu có liquidity sweep, entry tại vùng sweep đã confirmed
    if sweep and sweep.get('sweep') and sweep['direction'] == chosen_side:
        entry_zone = sweep.get('entry_zone')
        if entry_zone:
            entry_price = (entry_zone[0] + entry_zone[1]) / 2
            entry_type = 'limit' if prefer_limit else 'market'
            reasons.append(f"entry:sweep_zone")
    
    # Nếu không có sweep, dùng OB hoặc FVG gần nhất
    elif obs:
        for ob in reversed(obs[-5:]):
            if (chosen_side == 'buy' and ob['type'] == 'bull') or \
               (chosen_side == 'sell' and ob['type'] == 'bear'):
                if chosen_side == 'buy':
                    entry_price = ob['level_low'] + (ob['level_high'] - ob['level_low']) * 0.2
                else:
                    entry_price = ob['level_high'] - (ob['level_high'] - ob['level_low']) * 0.2
                entry_type = 'limit' if prefer_limit else 'market'
                reasons.append(f"entry:ob_zone")
                break
    
    # ========== 8. CALCULATE SL/TP ==========
    sl, tp = compute_sl_tp_smart(
        entry_price, chosen_side, df, structure, obs, fvgs,
        atr_multiplier=context.get('atr_multiplier', 1.5),
        rr_ratio=context.get('rr_ratio', 2.0)
    )
    
    # ========== 9. BUILD DECISION ==========
    decision = {
        'side': chosen_side,
        'type': entry_type,
        'entry': float(entry_price),
        'sl': float(sl),
        'tp': float(tp),
        'confidence': float(chosen_conf),
        'reasons': reasons + [
            f"bull_score:{bull_score:.2f}",
            f"bear_score:{bear_score:.2f}",
            f"pa_conf:{pa['confidence']:.2f}"
        ],
        'meta': {
            'structure': structure,
            'obs': obs,
            'fvgs': fvgs,
            'sweep': sweep,
            'false_breakout': false_bo,
            'pa': pa,
            'scores': {'bull': bull_score, 'bear': bear_score}
        },
        'blocked': False,
        'blocked_reason': None
    }
    
    # ========== 10. RUN CHECKS (Risk, Execution, Portfolio) ==========
    
    # Risk check
    risk_check = context.get('risk_check')
    if risk_check:
        try:
            allowed, reason = risk_check({
                'symbol': symbol,
                'side': chosen_side,
                'entry': entry_price,
                'sl': sl,
                'tp': tp,
                'confidence': chosen_conf
            })
            if not allowed:
                decision['blocked'] = True
                decision['blocked_reason'] = f"risk_check:{reason}"
                decision['reasons'].append(decision['blocked_reason'])
                logger.warning(f"❌ Risk check blocked: {reason}")
                return decision
        except Exception as e:
            decision['blocked'] = True
            decision['blocked_reason'] = f"risk_check_error:{e}"
            decision['reasons'].append(decision['blocked_reason'])
            logger.error(f"❌ Risk check error: {e}")
            return decision
    
    # Execution check
    exec_check = context.get('execution_check')
    if exec_check:
        try:
            allowed, reason = exec_check({
                'symbol': symbol,
                'entry': entry_price,
                'side': chosen_side,
                'type': entry_type
            })
            if not allowed:
                decision['blocked'] = True
                decision['blocked_reason'] = f"execution_check:{reason}"
                decision['reasons'].append(decision['blocked_reason'])
                logger.warning(f"❌ Execution check blocked: {reason}")
                return decision
        except Exception as e:
            decision['blocked'] = True
            decision['blocked_reason'] = f"execution_check_error:{e}"
            decision['reasons'].append(decision['blocked_reason'])
            logger.error(f"❌ Execution check error: {e}")
            return decision
    
    # Portfolio check
    portfolio_check = context.get('portfolio_check')
    if portfolio_check:
        try:
            allowed, reason = portfolio_check({
                'symbol': symbol,
                'side': chosen_side,
                'notional': None
            })
            if not allowed:
                decision['blocked'] = True
                decision['blocked_reason'] = f"portfolio_check:{reason}"
                decision['reasons'].append(decision['blocked_reason'])
                logger.warning(f"❌ Portfolio check blocked: {reason}")
                return decision
        except Exception as e:
            decision['blocked'] = True
            decision['blocked_reason'] = f"portfolio_check_error:{e}"
            decision['reasons'].append(decision['blocked_reason'])
            logger.error(f"❌ Portfolio check error: {e}")
            return decision
    
    # ========== 11. SUCCESS - RETURN DECISION ==========
    logger.info(f"✅ TRADE DECISION: {chosen_side.upper()} {symbol} @ {entry_price:.5f} "
               f"| SL: {sl:.5f} | TP: {tp:.5f} | Conf: {chosen_conf:.1%}")
    
    return decision


# ========================
# INTEGRATION HELPER
# ========================

def integrate_with_fusion_ai(decision: Dict[str, Any], fusion_ai_result: Optional[Dict] = None) -> Dict[str, Any]:
    """
    Helper để merge kết quả từ FusionAI với SMC decision
    Return final decision with combined confidence
    """
    if fusion_ai_result is None:
        return decision
    
    # Combine confidence
    smc_conf = decision.get('confidence', 0.0)
    fusion_conf = fusion_ai_result.get('confidence', 0.0)
    
    # Weighted average (SMC 60%, Fusion 40% vì SMC detail hơn)
    combined_conf = smc_conf * 0.6 + fusion_conf * 0.4
    
    # Check agreement
    smc_side = decision.get('side')
    fusion_side = fusion_ai_result.get('action', 'none').lower()
    
    if smc_side != fusion_side and smc_side != 'none' and fusion_side != 'none':
        # Disagreement - lower confidence
        combined_conf *= 0.7
        decision['reasons'].append(f"fusion_disagree:smc_{smc_side}_vs_fusion_{fusion_side}")
    else:
        decision['reasons'].append(f"fusion_agree:both_{smc_side}")
    
    decision['confidence'] = combined_conf
    decision['meta']['fusion_result'] = fusion_ai_result
    
    return decision
