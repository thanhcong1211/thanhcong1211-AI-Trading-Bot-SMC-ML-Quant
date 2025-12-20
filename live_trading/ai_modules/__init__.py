"""AI Modules Package - Tất cả các AI components"""

# Import các AI modules chính
try:
    from .fusion.fusion_ai import FusionAIUpgraded
except ImportError:
    FusionAIUpgraded = None

# Import from submodules
try:
    from .trend.trend_matrix_ai import TrendMatrixAI
except ImportError:
    TrendMatrixAI = None

# SMC (Smart Money Concepts) - Full 8-module system
try:
    from .smc import (
        SMCOrchestrator,
        MarketStructureAI,
        LiquidityAI,
        OrderBlockAI,
        FVGDetector,
        SupplyDemandAI,
        PremiumDiscountAI,
        InternalStructureAI,
        EntryModelAI
    )
except ImportError:
    SMCOrchestrator = None
    MarketStructureAI = None
    LiquidityAI = None
    OrderBlockAI = None
    FVGDetector = None
    SupplyDemandAI = None
    PremiumDiscountAI = None
    InternalStructureAI = None
    EntryModelAI = None

try:
    from .risk.risk_guardian_ai import RiskGuardianAI
except ImportError:
    RiskGuardianAI = None

try:
    from .risk.risk_ai import RiskAI
except ImportError:
    RiskAI = None

try:
    from .risk.volatility_ai import VolatilityAI
except ImportError:
    VolatilityAI = None

try:
    from .execution.execution_ai import ExecutionAI
except ImportError:
    ExecutionAI = None

try:
    from .explain_ai import ExplainAI
except ImportError:
    ExplainAI = None

try:
    from .sentiment_ai import SentimentAI
except ImportError:
    SentimentAI = None

try:
    from .session_ai import SessionAI
except ImportError:
    SessionAI = None

try:
    from .regime_ai import RegimeClassifierAI
except ImportError:
    RegimeClassifierAI = None

try:
    from .health_ai import HealthAI
except ImportError:
    HealthAI = None

try:
    from .portfolio_ai import PortfolioAI
except ImportError:
    PortfolioAI = None

try:
    from .adaptive_learner import AdaptiveLearner
except ImportError:
    AdaptiveLearner = None

try:
    from .trailing_sl_ai import TrailingSL
except ImportError:
    TrailingSL = None

try:
    from .smc_sl_tp import SMC_SLTP
except ImportError:
    SMC_SLTP = None

try:
    from .pattern_sltp import PatternSLTPAdvisor
except ImportError:
    PatternSLTPAdvisor = None

try:
    from .reentry_ai import ReEntrySmartAI
except ImportError:
    ReEntrySmartAI = None

try:
    from .sideway_detector_v2 import SidewayDetectorV2
except ImportError:
    SidewayDetectorV2 = None

try:
    from .CandlePatternAI import CandlePatternAI
except ImportError:
    CandlePatternAI = None

# NEW: Advanced AI Modules (Dec 2025)
try:
    from .market_phase_ai import MarketPhaseAI, get_market_phase_ai
except ImportError:
    MarketPhaseAI = None
    get_market_phase_ai = None

try:
    from .breaker_block_ai import BreakerBlockAI, get_breaker_block_ai
except ImportError:
    BreakerBlockAI = None
    get_breaker_block_ai = None

try:
    from .enhanced_news_filter_ai import EnhancedNewsFilterAI, get_enhanced_news_filter
except ImportError:
    EnhancedNewsFilterAI = None
    get_enhanced_news_filter = None

try:
    from .advanced_rl_ai import AdvancedReinforcementLearningAI, get_advanced_rl_ai
except ImportError:
    AdvancedReinforcementLearningAI = None
    get_advanced_rl_ai = None

__all__ = [
    'FusionAIUpgraded',
    'TrendMatrixAI',
    # SMC (Smart Money Concepts) - Full 8-module system
    'SMCOrchestrator',
    'MarketStructureAI',
    'LiquidityAI',
    'OrderBlockAI',
    'FVGDetector',
    'SupplyDemandAI',
    'PremiumDiscountAI',
    'InternalStructureAI',
    'EntryModelAI',
    # Other AI modules
    'RiskGuardianAI',
    'RiskAI',
    'VolatilityAI',
    'ExecutionAI',
    'ExplainAI',
    'SentimentAI',
    'SessionAI',
    'RegimeClassifierAI',
    'HealthAI',
    'PortfolioAI',
    'AdaptiveLearner',
    'TrailingSL',
    'SMC_SLTP',
    'PatternSLTPAdvisor',
    'ReEntrySmartAI',
    'SidewayDetectorV2',
    'CandlePatternAI',
    # NEW: Advanced AI Modules (Dec 2025)
    'MarketPhaseAI',
    'get_market_phase_ai',
    'BreakerBlockAI',
    'get_breaker_block_ai',
    'EnhancedNewsFilterAI',
    'get_enhanced_news_filter',
    'AdvancedReinforcementLearningAI',
    'get_advanced_rl_ai',
]
