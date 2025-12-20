"""
=============================================================================
MULTI-TIMEFRAME CONFIG - QUY TRÌNH PHÂN TÍCH MỚI
=============================================================================
Cấu hình khung thời gian theo yêu cầu:
- HTF (H1/M30): Xu hướng tổng thể
- MMF (M15): Market structure (BOS, CHoCH, Liquidity)
- LTF (M5): Entry zones (OB, FVG)
- Sniper (M1-M3): Entry confirmation
"""

# ===========================================================================
# KHUNG THỜI GIAN MỚI - THEO YÊU CẦU
# ===========================================================================

# HTF - Higher Timeframe (Xu hướng tổng thể)
HTF_TIMEFRAME = 'H1'  # Hoặc 'M30' tùy chọn
HTF_ROLE = 'TREND_DIRECTION'  # Xác định xu hướng chính

# MMF - Mid Timeframe (Market Structure)
MMF_TIMEFRAME = 'M15'
MMF_ROLE = 'MARKET_STRUCTURE'  # BOS, CHoCH, Liquidity Sweep

# LTF - Low Timeframe (Entry Zones)
LTF_TIMEFRAME = 'M5'
LTF_ROLE = 'ENTRY_ZONES'  # Order Blocks, FVG

# Sniper - Entry Confirmation
SNIPER_TIMEFRAME = 'M1'  # Hoặc M3
SNIPER_ROLE = 'ENTRY_CONFIRMATION'  # Nến, wick, volume

# ===========================================================================
# PHÂN CÔNG AI MODULES CHO TỪNG KHUNG
# ===========================================================================

# === HTF (H1) - 5 AI MODULES ===
HTF_AI_MODULES = [
    'TrendAI',           # Xu hướng chính (EMA alignment)
    'RegimeAI',          # Market regime (trending/ranging)
    'SessionAI',         # Trading session bias
    'NewsFilterAI',      # News impact filter
    'SentimentAI'        # Market sentiment
]

# === MMF (M15) - 8 AI MODULES ===
MMF_AI_MODULES = [
    'MarketPhaseAI',         # Wyckoff phases
    'MarketStructure',       # BOS, CHoCH detection
    'LiquiditySweepAI',      # Liquidity sweep detection
    'BreakerBlockAI',        # Breaker blocks
    'VolatilityAI',          # GARCH volatility
    'ReversalAI',            # Reversal detection
    'FusionAI',              # Decision engine
    'RiskAI'                 # Risk guardian
]

# === LTF (M5) - 4 AI MODULES ===
LTF_AI_MODULES = [
    'OrderBlockAI',          # Order block detection
    'FVG_AI',                # Fair Value Gap
    'ChartPatternAI',        # 33 candlestick patterns
    'SmartSL_AI'             # Smart SL/TP calculation
]

# === SNIPER (M1) - 2 AI MODULES ===
SNIPER_AI_MODULES = [
    'VolumeAI',              # Volume spike confirmation
    'MoneyManagerAI'         # Final position sizing
]

# ===========================================================================
# QUY TRÌNH PHÂN TÍCH (Step-by-step)
# ===========================================================================

ANALYSIS_WORKFLOW = {
    'step_1': {
        'name': 'HTF Analysis (H1)',
        'timeframe': HTF_TIMEFRAME,
        'modules': HTF_AI_MODULES,
        'purpose': 'Xác định xu hướng tổng thể',
        'output': ['trend_direction', 'regime', 'session_bias', 'news_level', 'sentiment']
    },
    
    'step_2': {
        'name': 'MMF Analysis (M15)',
        'timeframe': MMF_TIMEFRAME,
        'modules': MMF_AI_MODULES,
        'purpose': 'Phát hiện cấu trúc thị trường & liquidity',
        'output': ['bos_detected', 'choch_detected', 'liquidity_swept', 'breaker_blocks', 
                   'volatility_level', 'reversal_signal', 'fusion_decision']
    },
    
    'step_3': {
        'name': 'LTF Analysis (M5)',
        'timeframe': LTF_TIMEFRAME,
        'modules': LTF_AI_MODULES,
        'purpose': 'Tìm vùng vào lệnh chính xác',
        'output': ['order_blocks', 'fvg_zones', 'patterns', 'sl_tp_levels']
    },
    
    'step_4': {
        'name': 'Sniper Confirmation (M1)',
        'timeframe': SNIPER_TIMEFRAME,
        'modules': SNIPER_AI_MODULES,
        'purpose': 'Xác nhận entry cuối cùng',
        'output': ['volume_confirmed', 'final_lot_size', 'entry_triggered']
    }
}

# ===========================================================================
# CONFIDENCE THRESHOLD
# ===========================================================================

MIN_CONFIDENCE = {
    'HTF': 60.0,      # HTF cần 60% confidence
    'MMF': 70.0,      # MMF cần 70% confidence (quan trọng nhất)
    'LTF': 65.0,      # LTF cần 65% confidence
    'SNIPER': 50.0,   # Sniper chỉ cần 50% (đã có 3 khung trước confirm)
    'OVERALL': 65.0   # Tổng thể cần 65%
}

# ===========================================================================
# DATA FETCH SETTINGS
# ===========================================================================

CANDLES_TO_FETCH = {
    'H1': 1000,    # 1000 nến H1 = ~41 ngày
    'M30': 2000,   # 2000 nến M30 = ~41 ngày
    'M15': 2000,   # 2000 nến M15 = ~20 ngày
    'M5': 2000,    # 2000 nến M5 = ~7 ngày
    'M1': 1000     # 1000 nến M1 = ~16 giờ
}

# ===========================================================================
# ICT/SMC LOGIC - CHUẨN CHO BOT AI
# ===========================================================================

# === HTF TREND FILTER (H1) ===
HTF_TREND_LOGIC = {
    'bullish': {
        'ema': 'ema20 > ema50 > ema200',
        'macd': 'MACD > 0',
        'structure': 'HH > HL',
        'action': 'CHỈ tìm BUY'
    },
    'bearish': {
        'ema': 'ema20 < ema50 < ema200',
        'macd': 'MACD < 0',
        'structure': 'LL < LH',
        'action': 'CHỈ tìm SELL'
    }
}

# === M15 STRUCTURE CONFIRMATION ===
MMF_STRUCTURE_LOGIC = {
    'buy_setup': {
        'choch': 'CHoCH lên (change of character)',
        'liquidity': 'Sweep đáy trước (liquidity grab)',
        'volume': 'Volume spike (> 1.5x average)',
        'required': 'Cả 3 điều kiện phải thỏa'
    },
    'sell_setup': {
        'choch': 'CHoCH xuống',
        'liquidity': 'Sweep đỉnh trước',
        'volume': 'Volume spike (> 1.5x average)',
        'required': 'Cả 3 điều kiện phải thỏa'
    }
}

# === M5 ENTRY ZONES ===
LTF_ENTRY_LOGIC = {
    'demand_ob': 'Nến giảm cuối cùng trước cú tăng mạnh',
    'supply_ob': 'Nến tăng cuối cùng trước cú giảm mạnh',
    'fvg': 'Fair Value Gap (imbalance zones)',
    'breaker_block': 'Failed OB → Reversal zone',
    'mitigation': 'Volume Imbalance (Wyckoff)',
    'note': 'M5 = nơi đặt Limit Order'
}

# === M1 SNIPER CONFIRMATION ===
SNIPER_LOGIC = {
    'buy_entry': {
        'sweep': 'Sweep đáy nhỏ (stop hunt)',
        'rejection': 'Nến rejection (wick dài)',
        'micro_bos': 'Micro-BOS lên',
        'volume': 'Volume tăng đột biến',
        'macd': 'MACD cạn lực giảm → tăng trở lại'
    },
    'sell_entry': {
        'sweep': 'Sweep đỉnh nhỏ',
        'pinbar': 'Nến pinbar (wick trên dài)',
        'micro_bos': 'Micro-BOS xuống',
        'volume': 'Volume tăng đột biến',
        'macd': 'MACD cạn lực tăng → đảo chiều'
    }
}

# === STOP LOSS & TAKE PROFIT (ICT Standard) ===
SL_TP_LOGIC = {
    'stop_loss': {
        'buy': 'Ngay dưới đáy của Order Block',
        'sell': 'Ngay trên đỉnh của Order Block',
        'buffer': 'ATR * 0.3 để tránh bị quét'
    },
    'take_profit': {
        'tp1': {'target': 'FVG gần nhất', 'rr': '1:2', 'close': '30% position'},
        'tp2': {'target': 'Đỉnh/đáy cấu trúc M15', 'rr': '1:4', 'close': '40% position'},
        'tp3': {'target': 'Liquidity tiếp theo H1', 'rr': '1:6+', 'close': '30% position'}
    }
}

# === TRADE FILTER (Critical) ===
TRADE_FILTER = {
    'reject_if': [
        'Không có liquidity sweep',
        'OB bị chạm 2 lần (OB yếu)',
        'Volume thấp (< 0.8x average)',
        'M1 chưa xác nhận entry',
        'Tin tức mạnh (NFP, FOMC, CPI)',
        'Giờ vàng (5 phút trước/sau news L3)'
    ],
    'min_confidence': {
        'HTF': 60,
        'MMF': 70,  # Quan trọng nhất
        'LTF': 65,
        'SNIPER': 50
    }
}

# ===========================================================================
# HELPER FUNCTIONS
# ===========================================================================

def get_all_timeframes():
    """Trả về tất cả khung thời gian cần fetch"""
    return [HTF_TIMEFRAME, MMF_TIMEFRAME, LTF_TIMEFRAME, SNIPER_TIMEFRAME]

def get_modules_for_timeframe(timeframe):
    """Trả về danh sách AI modules cho khung thời gian"""
    if timeframe == HTF_TIMEFRAME:
        return HTF_AI_MODULES
    elif timeframe == MMF_TIMEFRAME:
        return MMF_AI_MODULES
    elif timeframe == LTF_TIMEFRAME:
        return LTF_AI_MODULES
    elif timeframe == SNIPER_TIMEFRAME:
        return SNIPER_AI_MODULES
    return []

def get_analysis_flow():
    """Trả về quy trình phân tích đầy đủ"""
    return ANALYSIS_WORKFLOW

def check_htf_trend(data_h1):
    """
    Kiểm tra xu hướng HTF theo logic ICT
    
    Returns:
        'BULLISH' | 'BEARISH' | 'NEUTRAL'
    """
    if data_h1 is None or len(data_h1) < 200:
        return 'NEUTRAL'
    
    # EMA alignment
    ema20 = data_h1['close'].ewm(span=20).mean().iloc[-1]
    ema50 = data_h1['close'].ewm(span=50).mean().iloc[-1]
    ema200 = data_h1['close'].ewm(span=200).mean().iloc[-1]
    
    # MACD
    ema12 = data_h1['close'].ewm(span=12).mean()
    ema26 = data_h1['close'].ewm(span=26).mean()
    macd = ema12 - ema26
    macd_current = macd.iloc[-1]
    
    # Structure (HH/HL vs LL/LH)
    highs = data_h1['high'].tail(10)
    lows = data_h1['low'].tail(10)
    
    if ema20 > ema50 > ema200 and macd_current > 0:
        return 'BULLISH'
    elif ema20 < ema50 < ema200 and macd_current < 0:
        return 'BEARISH'
    else:
        return 'NEUTRAL'

def check_mmf_structure(data_m15):
    """
    Kiểm tra cấu trúc M15: BOS, CHoCH, Liquidity Sweep
    
    Returns:
        dict with 'bos', 'choch', 'liquidity_swept', 'setup'
    """
    result = {
        'bos': False,
        'choch': False,
        'liquidity_swept': False,
        'volume_spike': False,
        'setup': None  # 'BUY' or 'SELL' or None
    }
    
    if data_m15 is None or len(data_m15) < 50:
        return result
    
    # Volume spike detection
    volumes = data_m15['tick_volume'].tail(20)
    avg_volume = volumes.mean()
    current_volume = volumes.iloc[-1]
    result['volume_spike'] = current_volume > (avg_volume * 1.5)
    
    # Liquidity sweep detection (simplified)
    highs = data_m15['high'].tail(10)
    lows = data_m15['low'].tail(10)
    
    # Sweep lows = giá xuống quét đáy cũ rồi đóng cửa cao hơn
    if data_m15['low'].iloc[-1] < lows.iloc[-3] and data_m15['close'].iloc[-1] > lows.iloc[-3]:
        result['liquidity_swept'] = True
        result['setup'] = 'BUY'
    
    # Sweep highs = giá lên quét đỉnh cũ rồi đóng cửa thấp hơn
    if data_m15['high'].iloc[-1] > highs.iloc[-3] and data_m15['close'].iloc[-1] < highs.iloc[-3]:
        result['liquidity_swept'] = True
        result['setup'] = 'SELL'
    
    return result

def find_order_blocks_m5(data_m5, setup='BUY'):
    """
    Tìm Order Blocks trên M5
    
    Args:
        setup: 'BUY' (demand) or 'SELL' (supply)
    
    Returns:
        list of {'type', 'high', 'low', 'fresh'}
    """
    obs = []
    
    if data_m5 is None or len(data_m5) < 20:
        return obs
    
    if setup == 'BUY':
        # Demand OB: Nến giảm cuối cùng trước cú tăng mạnh
        for i in range(len(data_m5) - 5, len(data_m5) - 1):
            if (data_m5['close'].iloc[i] < data_m5['open'].iloc[i] and  # Bearish candle
                data_m5['close'].iloc[i+1] > data_m5['close'].iloc[i]):  # Next candle bullish
                obs.append({
                    'type': 'DEMAND',
                    'high': data_m5['high'].iloc[i],
                    'low': data_m5['low'].iloc[i],
                    'fresh': True
                })
    
    elif setup == 'SELL':
        # Supply OB: Nến tăng cuối cùng trước cú giảm mạnh
        for i in range(len(data_m5) - 5, len(data_m5) - 1):
            if (data_m5['close'].iloc[i] > data_m5['open'].iloc[i] and  # Bullish candle
                data_m5['close'].iloc[i+1] < data_m5['close'].iloc[i]):  # Next candle bearish
                obs.append({
                    'type': 'SUPPLY',
                    'high': data_m5['high'].iloc[i],
                    'low': data_m5['low'].iloc[i],
                    'fresh': True
                })
    
    return obs

def calculate_ict_sl_tp(entry_price, setup, order_block, atr):
    """
    Tính SL/TP theo chuẩn ICT
    
    Args:
        entry_price: giá vào lệnh
        setup: 'BUY' or 'SELL'
        order_block: dict {'high', 'low'}
        atr: Average True Range
    
    Returns:
        dict {'sl', 'tp1', 'tp2', 'tp3'}
    """
    buffer = atr * 0.3
    
    if setup == 'BUY':
        sl = order_block['low'] - buffer
        tp1 = entry_price + (entry_price - sl) * 2    # RR 1:2
        tp2 = entry_price + (entry_price - sl) * 4    # RR 1:4
        tp3 = entry_price + (entry_price - sl) * 6    # RR 1:6
    else:  # SELL
        sl = order_block['high'] + buffer
        tp1 = entry_price - (sl - entry_price) * 2    # RR 1:2
        tp2 = entry_price - (sl - entry_price) * 4    # RR 1:4
        tp3 = entry_price - (sl - entry_price) * 6    # RR 1:6
    
    return {
        'sl': sl,
        'tp1': tp1,
        'tp2': tp2,
        'tp3': tp3,
        'rr_ratios': [2.0, 4.0, 6.0]
    }

# ===========================================================================
# VALIDATION
# ===========================================================================

# Kiểm tra tổng số AI modules = 19
total_modules = len(HTF_AI_MODULES) + len(MMF_AI_MODULES) + len(LTF_AI_MODULES) + len(SNIPER_AI_MODULES)
assert total_modules == 19, f"❌ Số AI modules phải là 19, hiện tại: {total_modules}"

print("✅ Multi-Timeframe Config loaded successfully!")
print(f"   HTF: {HTF_TIMEFRAME} ({len(HTF_AI_MODULES)} modules)")
print(f"   MMF: {MMF_TIMEFRAME} ({len(MMF_AI_MODULES)} modules)")
print(f"   LTF: {LTF_TIMEFRAME} ({len(LTF_AI_MODULES)} modules)")
print(f"   Sniper: {SNIPER_TIMEFRAME} ({len(SNIPER_AI_MODULES)} modules)")
print(f"   Total: {total_modules} AI Modules ⭐")
