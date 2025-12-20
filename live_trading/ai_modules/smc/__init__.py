"""
SMC (Smart Money Concepts) Module
==================================

Full implementation of ICT/SMC methodology for institutional trading.

Modules:
--------
1. market_structure.py - BOS, CHoCH, Market Structure
2. liquidity.py - Liquidity Sweeps, Equal Highs/Lows, Stop Hunts
3. order_block.py - Order Blocks, Mitigation Blocks
4. fvg.py - Fair Value Gaps, Imbalances
5. supply_demand.py - Supply/Demand Zones
6. premium_discount.py - Premium/Discount Analysis
7. internal_structure.py - LTF Structure, Multi-timeframe
8. entry_models.py - SMC Entry Models & Strategies

Usage:
------
from smc import SMCOrchestrator

smc = SMCOrchestrator()
result = smc.analyze(df_h1, df_m5, df_m1)
entry = smc.get_entry_signal(result)
"""

from .config import SMCConfig
from .base import SMCBase
from .market_structure import MarketStructureAI
from .liquidity import LiquidityAI
from .order_block import OrderBlockAI
from .fvg import FVGDetector
from .supply_demand import SupplyDemandAI
from .premium_discount import PremiumDiscountAI
from .internal_structure import InternalStructureAI
from .entry_models import EntryModelAI
from .orchestrator import SMCOrchestrator

# New Enhanced SMC Modules (Dec 7, 2025)
from .smc_state_manager import SMCStateManager
from .smc_filters import atr, is_in_killzone, ob_is_valid, price_in_zone
from .smc_mtf_orchestrator import SMCMTFOrchestrator, detect_simple_order_blocks
from .smc_suggestion import score_candidate, finalize_candidates

__version__ = '1.1.0'
__author__ = 'AI Trading System'

__all__ = [
    'SMCConfig',
    'SMCBase',
    'MarketStructureAI',
    'LiquidityAI',
    'OrderBlockAI',
    'FVGDetector',
    'SupplyDemandAI',
    'PremiumDiscountAI',
    # New modules
    'SMCStateManager',
    'SMCMTFOrchestrator',
    'atr',
    'is_in_killzone',
    'ob_is_valid',
    'price_in_zone',
    'score_candidate',
    'finalize_candidates',
    'detect_simple_order_blocks',
    'InternalStructureAI',
    'EntryModelAI',
    'SMCOrchestrator',
]
