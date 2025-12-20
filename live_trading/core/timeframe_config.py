"""
=============================================================================
TIMEFRAME CONFIGURATION - QUY TRÌNH PHÂN TÍCH MỚI
=============================================================================
Cấu hình khung thời gian theo phương pháp SMC chuẩn

| Vai trò                       | Khung thời gian | Ý nghĩa                                          |
| ----------------------------- | --------------- | ------------------------------------------------ |
| HTF (xu hướng)                | H1 hoặc M30     | Xác định thị trường đang tăng/giảm/tích lũy      |
| MMF (mô hình thị trường)      | M15             | Tìm BOS, CHoCH, Liquidity sweep                  |
| LTF (vùng vào lệnh chính xác) | M5              | Tìm OB/FVG để vào lệnh                           |
| Entry Sniper                  | M1–M3           | Xác nhận nến, wick, volume để đặt limit          |
=============================================================================
"""

# =============================================================================
# KHUNG THỜI GIAN THEO QUY TRÌNH SMC CHUẨN
# =============================================================================

# HTF - HIGHER TIMEFRAME (Xu hướng tổng thể)
# Xác định thị trường đang: Tăng / Giảm / Tích lũy / Phân phối
HTF_TIMEFRAME = 'H1'          # H1 hoặc M30 (có thể chuyển sang M30 nếu muốn)
HTF_ROLE = 'TREND_DIRECTION'  # Vai trò: Xác định bias (bullish/bearish)

# MMF - MID TIMEFRAME (Mô hình thị trường)
# Tìm: BOS (Break of Structure), CHoCH (Change of Character), Liquidity Sweep
MMF_TIMEFRAME = 'M15'
MMF_ROLE = 'MARKET_STRUCTURE'  # Vai trò: Phát hiện cấu trúc thị trường

# LTF - LOW TIMEFRAME (Vùng vào lệnh)
# Tìm: Order Block (OB), Fair Value Gap (FVG) để vào lệnh
LTF_TIMEFRAME = 'M5'
LTF_ROLE = 'ENTRY_ZONES'       # Vai trò: Xác định vùng OB/FVG

# SNIPER - ENTRY CONFIRMATION (Xác nhận cuối cùng)
# Xác nhận: Nến, wick, volume để đặt limit order chính xác
SNIPER_TIMEFRAME = 'M1'        # M1 hoặc M3 (có thể điều chỉnh)
SNIPER_ROLE = 'ENTRY_CONFIRMATION'  # Vai trò: Timing chính xác

# =============================================================================
# TIMEFRAME FETCHING ORDER
# =============================================================================

# Thứ tự fetch data (từ lớn đến nhỏ)
ALL_TIMEFRAMES = [
    HTF_TIMEFRAME,      # H1 - Xu hướng
    MMF_TIMEFRAME,      # M15 - Market structure
    LTF_TIMEFRAME,      # M5 - Entry zones
    SNIPER_TIMEFRAME    # M1 - Final confirmation
]

# Primary timeframe cho AI analysis (sử dụng M15 làm khung chính)
PRIMARY_TIMEFRAME = MMF_TIMEFRAME  # M15

# =============================================================================
# CANDLE COUNTS (Số nến cần fetch)
# =============================================================================

TIMEFRAME_CANDLE_COUNTS = {
    'H1': 500,    # ~21 ngày (500 giờ)
    'M30': 1000,  # ~21 ngày (500 giờ)
    'M15': 2000,  # ~21 ngày (500 giờ)
    'M5': 3000,   # ~10 ngày (2400 phút)
    'M3': 5000,   # ~10 ngày
    'M1': 5000    # ~3.5 ngày (5000 phút)
}

# =============================================================================
# QUY TRÌNH PHÂN TÍCH
# =============================================================================

ANALYSIS_WORKFLOW = {
    'STEP_1_HTF': {
        'timeframe': HTF_TIMEFRAME,
        'purpose': 'Xác định xu hướng tổng thể',
        'indicators': ['EMA200', 'Market Phase (Wyckoff)', 'Trend Strength'],
        'output': 'BULLISH/BEARISH/ACCUMULATION/DISTRIBUTION'
    },
    
    'STEP_2_MMF': {
        'timeframe': MMF_TIMEFRAME,
        'purpose': 'Phát hiện cấu trúc thị trường',
        'patterns': ['BOS', 'CHoCH', 'Liquidity Sweep', 'Internal Liquidity'],
        'output': 'Market structure + Entry bias'
    },
    
    'STEP_3_LTF': {
        'timeframe': LTF_TIMEFRAME,
        'purpose': 'Tìm vùng vào lệnh chính xác',
        'zones': ['Order Block (OB)', 'Fair Value Gap (FVG)', 'Breaker Block'],
        'output': 'Entry zone price levels'
    },
    
    'STEP_4_SNIPER': {
        'timeframe': SNIPER_TIMEFRAME,
        'purpose': 'Xác nhận entry timing',
        'confirmations': ['Nến đảo chiều', 'Rejection wick', 'Volume spike'],
        'output': 'Exact entry price + limit order'
    }
}

# =============================================================================
# HTF FILTER POLICY
# =============================================================================

# HTF Filter: Lọc tín hiệu theo xu hướng H1
HTF_FILTER_ENABLED = True
HTF_FILTER_POLICY = 'soft'  # 'soft', 'block', 'off'
HTF_SOFT_MULTIPLIER = 0.7   # Giảm 30% confidence nếu ngược HTF

# =============================================================================
# CONFIDENCE THRESHOLDS
# =============================================================================

# Ngưỡng confidence tối thiểu cho từng timeframe
CONFIDENCE_THRESHOLDS = {
    'HTF': 60,    # H1 trend phải rõ ràng (≥60%)
    'MMF': 70,    # M15 structure phải mạnh (≥70%)
    'LTF': 65,    # M5 entry zone hợp lý (≥65%)
    'SNIPER': 75  # M1 confirmation phải chắc chắn (≥75%)
}

# Overall minimum confidence để execute
MIN_OVERALL_CONFIDENCE = 65.0  # 65% tổng thể

# =============================================================================
# ENTRY TYPES
# =============================================================================

# Market order: Vào ngay khi có tín hiệu mạnh
# Limit order: Đặt lệnh chờ tại OB/FVG
ENTRY_TYPE_RULES = {
    'MARKET_ORDER': {
        'condition': 'confidence >= 75 AND strong_momentum',
        'use_when': 'Breakout mạnh, không có OB/FVG gần'
    },
    'LIMIT_ORDER': {
        'condition': 'confidence >= 65 AND has_entry_zone',
        'use_when': 'Có OB/FVG gần, chờ price test lại'
    }
}

# =============================================================================
# SL/TP CALCULATION
# =============================================================================

# SL/TP dựa trên timeframe nào?
SL_TP_BASED_ON = {
    'ATR_TIMEFRAME': LTF_TIMEFRAME,    # Dùng ATR M5
    'STRUCTURE_TIMEFRAME': MMF_TIMEFRAME,  # Dùng swing M15
    'SUPPORT_RESISTANCE_TIMEFRAME': HTF_TIMEFRAME  # Dùng S/R H1
}

# =============================================================================
# EXPORTS
# =============================================================================

# Export các biến quan trọng để dùng trong code chính
__all__ = [
    'HTF_TIMEFRAME',
    'MMF_TIMEFRAME', 
    'LTF_TIMEFRAME',
    'SNIPER_TIMEFRAME',
    'PRIMARY_TIMEFRAME',
    'ALL_TIMEFRAMES',
    'TIMEFRAME_CANDLE_COUNTS',
    'ANALYSIS_WORKFLOW',
    'HTF_FILTER_ENABLED',
    'HTF_FILTER_POLICY',
    'HTF_SOFT_MULTIPLIER',
    'CONFIDENCE_THRESHOLDS',
    'MIN_OVERALL_CONFIDENCE',
    'ENTRY_TYPE_RULES',
    'SL_TP_BASED_ON'
]

# =============================================================================
# LOGGING
# =============================================================================

def print_timeframe_config():
    """In ra cấu hình khung thời gian"""
    print("="*70)
    print("📊 TIMEFRAME CONFIGURATION")
    print("="*70)
    print(f"🔵 HTF (Xu hướng):          {HTF_TIMEFRAME} - {HTF_ROLE}")
    print(f"🟢 MMF (Market Structure):  {MMF_TIMEFRAME} - {MMF_ROLE}")
    print(f"🟡 LTF (Entry Zones):       {LTF_TIMEFRAME} - {LTF_ROLE}")
    print(f"🔴 SNIPER (Confirmation):   {SNIPER_TIMEFRAME} - {SNIPER_ROLE}")
    print("="*70)
    print(f"⭐ Primary Analysis: {PRIMARY_TIMEFRAME}")
    print(f"🎯 Min Confidence: {MIN_OVERALL_CONFIDENCE}%")
    print(f"🛡️ HTF Filter: {HTF_FILTER_POLICY}")
    print("="*70)

if __name__ == '__main__':
    print_timeframe_config()
