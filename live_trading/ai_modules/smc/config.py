"""
SMC Configuration
Centralized config for all SMC modules
"""

class SMCConfig:
    """Centralized SMC configuration"""
    
    # Market Structure
    PIVOT_LOOKBACK = 50
    MIN_SWING_PTS = 1e-6
    STRUCTURE_CONFIRMATION_BARS = 3
    
    # Liquidity
    LIQUIDITY_LOOKBACK = 50
    VOLUME_MULTIPLIER = 1.6
    WICK_RATIO_THRESHOLD = 2.0
    ATR_PERIOD = 14
    EQUAL_HL_TOLERANCE = 0.0001  # 0.01% tolerance for equal highs/lows
    
    # Order Block
    OB_LOOKBACK = 200
    MIN_MOVE_PTS = 0.002  # 0.2% minimum move to validate OB
    OB_REJECTION_THRESHOLD = 0.6
    MITIGATION_THRESHOLD = 0.5  # 50% retracement into OB
    
    # FVG
    FVG_LOOKBACK = 200
    MIN_FVG_SIZE = 0.0001  # Minimum gap size
    FVG_FILL_THRESHOLD = 0.5  # 50% fill considered mitigated
    
    # Supply/Demand
    SD_LOOKBACK = 300
    SD_STRENGTH_BARS = 5
    SD_VOLUME_MULTIPLIER = 1.5
    FLIP_ZONE_CONFIRMATION = 2  # bars to confirm flip
    
    # Premium/Discount
    PD_MA_PERIOD = 50
    PREMIUM_THRESHOLD = 0.005  # 0.5%
    DISCOUNT_THRESHOLD = -0.005
    EQUILIBRIUM_RANGE = 0.002  # ±0.2%
    
    # Internal Structure (LTF)
    LTF_EMA_SHORT = 8
    LTF_EMA_LONG = 21
    PULLBACK_WINDOW = 50
    
    # Entry Models
    DEFAULT_RR = 2.5
    SL_BUFFER = 0.0006  # 0.06%
    MAX_ENTRIES_PER_SESSION = 3
    MIN_CONFLUENCE_SCORE = 2  # Minimum number of confluences
    
    # Risk Management
    MAX_RISK_PER_TRADE = 0.02  # 2%
    MAX_TOTAL_RISK = 0.10  # 10%
    MIN_CONFIDENCE = 0.65  # 65%
    
    # Multi-Timeframe
    HTF_TIMEFRAME = 'H1'  # Higher timeframe
    MTF_TIMEFRAME = 'M15'  # Medium timeframe
    LTF_TIMEFRAME = 'M5'  # Lower timeframe for entry
    PRECISION_TIMEFRAME = 'M1'  # Precision entry
    
    # Performance
    CACHE_ENABLED = True
    CACHE_TTL = 300  # 5 minutes
    MAX_CACHE_SIZE = 1000
    
    # Logging
    DEBUG_MODE = False
    LOG_LEVEL = 'INFO'
    
    @classmethod
    def to_dict(cls):
        """Export config as dictionary"""
        return {k: v for k, v in cls.__dict__.items() 
                if not k.startswith('_') and k.isupper()}
    
    @classmethod
    def from_dict(cls, config_dict):
        """Import config from dictionary"""
        for k, v in config_dict.items():
            if hasattr(cls, k):
                setattr(cls, k, v)
