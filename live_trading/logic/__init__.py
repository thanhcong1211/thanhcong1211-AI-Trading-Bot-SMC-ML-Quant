"""Central registry for AI logic modules.

This file keeps a small registry of available AI implementations so the
orchestrator can import a single canonical name and let this module
prefer newer versions (e.g. `fusion_ai_v3`) while keeping backward
compatibility with older imports.

Usage:
    from live_trading.logic import get_ai, TrendAI, VolatilityAI, StructureAI, LiquidityAI, TrailingSL, SentimentAI
    TrendAIClass = TrendAI
    structure_ai = get_ai('structure_ai')  # returns StructureAI class
    liquidity_ai = get_ai('liquidity_ai')  # returns LiquidityAI class
    trailing_sl = get_ai('trailing_sl')    # returns TrailingSL class
    sentiment_ai = get_ai('sentiment')     # returns SentimentAI class
"""
from importlib import import_module
import logging

logger = logging.getLogger(__name__)

# Try to import known AI implementations and expose them as attributes.
# Prefer versioned modules (fusion_ai_v3) when present.

def _try_import(mod_name, attr_name=None):
    try:
        # Try relative import first (when inside logic package)
        try:
            mod = import_module(f".{mod_name}", package="logic")
        except:
            # Fallback to absolute import
            mod = import_module(f"live_trading.logic.{mod_name}")
        if attr_name:
            return getattr(mod, attr_name)
        return mod
    except Exception as e:
        logger.debug(f"logic._try_import: failed to import {mod_name}: {e}")
        return None

# TrendAI
TrendAI = _try_import('trend_ai', 'TrendAI') or _try_import('trendai', 'TrendAI')
# VolatilityAI
VolatilityAI = _try_import('volatility_ai', 'VolatilityAI')
# Fusion: unified version (merged v1-v5)
FusionAI = _try_import('fusion_ai', 'FusionAIUpgraded')
# Backward compatibility aliases
FusionAIv4 = FusionAI
FusionAIv3 = FusionAI
# SMC (Smart Money Concepts) - Import from ai_modules.smc
try:
    from ai_modules.smc import (
        MarketStructureAI,
        LiquidityAI,
        SMCOrchestrator
    )
    # Backward compatibility aliases
    LiquiditySweepAI = LiquidityAI  # Old name → new SMC module
    StructureAI = MarketStructureAI  # Old name → new SMC module
except Exception as e:
    logger.warning(f"Could not import SMC modules: {e}")
    MarketStructureAI = None
    LiquidityAI = None
    LiquiditySweepAI = None
    StructureAI = None
    SMCOrchestrator = None

# Risk / ReEntry / SL/TP
RiskAI = _try_import('risk_ai', 'RiskAI')
ReEntrySmartAI = _try_import('reentry_ai', 'ReEntrySmartAI')
SMC_SLTP = _try_import('smc_sl_tp', 'SMC_SLTP')
# Other AI modules
TrailingSL = _try_import('trailing_sl_ai', 'TrailingSL')
SentimentAI = _try_import('sentiment_ai', 'SentimentAI')

def get_ai(key: str):
    """Return the preferred AI class or module for a given key.

    Keys: 'trend', 'volatility', 'fusion', 'liquidity', 'structure', 'risk', 'reentry', 'smc', 'structure_ai', 'liquidity_ai', 'trailing_sl', 'sentiment'
    Returns: class or None
    """
    k = (key or '').lower()
    if k in ('trend', 'trendai'):
        return TrendAI
    if k in ('volatility', 'vol'):
        return VolatilityAI
    if k in ('fusion', 'fusionai'):
        return FusionAI
    if k in ('fusionv4', 'fusion_v4'):
        return FusionAIv4
    if k in ('fusionv3', 'fusion_v3'):
        return FusionAIv3
    if k in ('liquidity', 'lsai'):
        return LiquiditySweepAI
    if k in ('structure', 'msai'):
        return MarketStructureAI
    if k in ('risk', 'riskai'):
        return RiskAI
    if k in ('reentry', 'reentryai'):
        return ReEntrySmartAI
    if k in ('smc', 'smc_sltp'):
        return SMC_SLTP
    if k in ('smc_orchestrator', 'smc_orch'):
        return SMCOrchestrator
    if k in ('structure_ai', 'structureai'):
        return StructureAI
    if k in ('liquidity_ai', 'liquidityai'):
        return LiquidityAI
    if k in ('trailing_sl', 'trailingsl', 'trailing'):
        return TrailingSL
    if k in ('sentiment', 'sentimentai'):
        return SentimentAI
    return None

__all__ = [
    'get_ai', 'TrendAI', 'VolatilityAI', 'FusionAI', 'FusionAIv4', 'FusionAIv3', 'LiquiditySweepAI',
    'MarketStructureAI', 'RiskAI', 'ReEntrySmartAI', 'SMC_SLTP',
    'StructureAI', 'LiquidityAI', 'TrailingSL', 'SentimentAI'
]
