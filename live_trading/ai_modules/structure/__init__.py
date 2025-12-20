"""Structure & Liquidity AI Module - DEPRECATED

Old structure files have been consolidated into ai_modules/smc/
Please use: from ai_modules.smc import MarketStructureAI, LiquidityAI
"""

# Backward compatibility: redirect to SMC modules
try:
    from ..smc import MarketStructureAI as StructureAI
    from ..smc import LiquidityAI
    from ..smc import LiquidityAI as LiquiditySweepAI
except ImportError:
    StructureAI = None
    LiquidityAI = None
    LiquiditySweepAI = None

__all__ = ['StructureAI', 'LiquidityAI', 'LiquiditySweepAI']
