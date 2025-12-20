"""
Live Trading AI System
======================
Complete AI Trading System for MetaTrader 5

Main Components:
- core.complete_ai_trading_system: Main trading system orchestrator
- ai_modules: All AI components (fusion, trend, structure, risk, execution)
- config: Configuration management
- utils: Utility functions
"""

__version__ = "2.0.0"

# Import main classes from core
try:
    from .core.complete_ai_trading_system import CompleteAITradingSystem
except ImportError:
    CompleteAITradingSystem = None

# Import AI modules
try:
    from .ai_modules.fusion.fusion_ai import FusionAIUpgraded
except ImportError:
    FusionAIUpgraded = None

try:
    from .ai_modules.trend.trend_matrix_ai import TrendMatrixAI
except ImportError:
    TrendMatrixAI = None

try:
    from .ai_modules.risk.risk_guardian_ai import RiskGuardianAI
except ImportError:
    RiskGuardianAI = None

__all__ = [
    'CompleteAITradingSystem',
    'FusionAIUpgraded',
    'TrendMatrixAI',
    'RiskGuardianAI',
]
