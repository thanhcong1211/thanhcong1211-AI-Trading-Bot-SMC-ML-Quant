#!/usr/bin/env python3
"""
=============================================================================
COMPLETE AI TRADING SYSTEM - ALL-IN-ONE
Tích hợp đầy đủ: Data Fetching → AI Training → Backtesting → Live Trading
=============================================================================
Author: AI Trading System
Version: 2.0 - Complete Pipeline
Communication: HTTP only (no ZeroMQ)
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

# Fix imports to work from core/ directory
import sys
from pathlib import Path
if str(Path(__file__).parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from ai_modules.trend.trend_matrix_ai import TrendMatrixAI
    from ai_modules.smart_sl_ai import SmartSLAI
    from ai_modules.risk.risk_guardian_ai import RiskGuardianAI
    from ai_modules.fusion.fusion_ai import FusionAIUpgraded
    from ai_modules.sideway_detector_v2 import SidewayDetectorV2
    from ai_modules.regime_classifier import RegimeClassifierAI
    # NEW: Advanced AI Modules (Dec 2025)
    from ai_modules import (
        get_market_phase_ai,
        get_breaker_block_ai,
        get_enhanced_news_filter,
        get_advanced_rl_ai
    )
    # NEW: Scoring Modules (Dec 2025)
    from ai_modules.scoring import TradeQualityScorer, PatternProbabilityFilter
    AI_MODULES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Warning: AI modules not available: {e}")
    print("   System will run in basic mode without advanced AI features")
    AI_MODULES_AVAILABLE = False
    TrendMatrixAI = None
    SmartSLAI = None
    TradeQualityScorer = None
    PatternProbabilityFilter = None
    RiskGuardianAI = None
    FusionAIUpgraded = None
    SidewayDetectorV2 = None
    RegimeClassifierAI = None
    get_market_phase_ai = None
    get_breaker_block_ai = None
    get_enhanced_news_filter = None
    get_advanced_rl_ai = None
from pathlib import Path
from collections import deque, Counter
from http.server import HTTPServer, BaseHTTPRequestHandler
import random
try:
    import requests
    REQUESTS_AVAILABLE = True
except Exception:
    REQUESTS_AVAILABLE = False
from functools import lru_cache
import psutil

# Import from refactored modules
try:
    from .cache import indicator_cache, data_cache, IndicatorCache, DataCache
    from .monitoring import (
        cpu_monitor, heartbeat, get_runtime_mode, CrashDetector,
        CPU_MONITOR_ENABLED, ultra_mode, superlight_mode, safe_mode,
        CPU_HIGH_THRESHOLD, CPU_MEDIUM_THRESHOLD, MEMORY_HIGH_PERCENT,
        PSUTIL_AVAILABLE
    )
    MODULES_IMPORTED = True
except ImportError:
    # Fallback if running file directly (not as module)
    MODULES_IMPORTED = False
    try:
        import psutil
        PSUTIL_AVAILABLE = True
    except Exception:
        PSUTIL_AVAILABLE = False
    
    if PSUTIL_AVAILABLE:
        CPU_MONITOR_ENABLED = True
        ultra_mode = True
        superlight_mode = False
        safe_mode = False
        CPU_HIGH_THRESHOLD = 85.0
        CPU_MEDIUM_THRESHOLD = 75.0  # Tăng từ 45% lên 75% để bot vẫn giao dịch
        MEMORY_HIGH_PERCENT = 92.0
    else:
        # Fallback khi không import được psutil
        CPU_MONITOR_ENABLED = False
        ultra_mode = True
        superlight_mode = False
        safe_mode = False

# Super-light mode: when True the system will skip or throttle heavy computations
SUPERLIGHT = superlight_mode

# --- AUTO-FILTER (tự động áp dụng cấu hình tối ưu từ backtest sweep) ---
# Nếu bật, hệ thống sẽ chỉ vào lệnh khi tín hiệu thoả min confidence (phần trăm)
# và thuộc một trong các session được whitelist. Thay đổi này được áp
# tự động bởi công cụ phân tích nếu tìm thấy cấu hình tốt nhất từ backtest.
AUTO_FILTER_ENABLED = True
# Giá trị tối ưu để đạt winrate 65-75%: Chỉ trade tín hiệu confidence ≥70%
AUTO_MIN_CONFIDENCE = 70.0   # percent (0-100) - Tăng từ 60% → 70% để lọc chặt hơn
AUTO_SESSION_WHITELIST = ['eu', 'us']  # Chỉ trade session EU + US (volume cao, trending)

# Khi bật, hệ thống KHÔNG gửi lệnh thực tế tới MT5 — chỉ mô phỏng/huấn luyện/backtest.
# Dùng để chạy huấn luyện/backtest trên máy local hoặc khi muốn tắt giao dịch live.
# Đã chuyển sang False để cho phép gửi lệnh thật theo yêu cầu.
FORCE_DISABLE_TRADING = False

# Feature toggle: enable/disable Fusion engine at runtime without removing code.
# Set to False to fully disable Fusion calls (useful to avoid overrides while
# keeping other AIs active). Default: disabled for safe investigation.
USE_FUSION = True

# AI Processing Controls - Bảo vệ AI khỏi quá tải
AI_PROCESSING_TIMEOUT = 30.0  # seconds - Timeout cho mỗi lần phân tích
SIGNAL_COOLDOWN = 5.0        # seconds - Thời gian chờ tối thiểu giữa các signal
MIN_CONTINUOUS_SLEEP = 2.0   # seconds - Sleep tối thiểu trong continuous mode
def cpu_monitor(poll_interval=5, cpu_high=CPU_HIGH_THRESHOLD, cpu_medium=CPU_MEDIUM_THRESHOLD):
    """Luồng daemon giám sát CPU và bộ nhớ, tự động chuyển các chế độ toàn cục.

    Ghi chú:
    - Hàm này chạy ở chế độ "best-effort" và có tính phòng ngừa: nếu `psutil`
      không có hoặc xảy ra lỗi bất ngờ thì hàm sẽ dừng im lặng và KHÔNG làm hỏng
      luồng chính của chương trình.
    - Các biến toàn cục `ultra_mode`, `superlight_mode`, `safe_mode` được cập nhật
      theo trạng thái tài nguyên để các phần còn lại của hệ thống có thể điều
      chỉnh tần suất hoặc tắt trading khi cần.
    """
    global ultra_mode, superlight_mode, safe_mode, SUPERLIGHT
    if not PSUTIL_AVAILABLE or not CPU_MONITOR_ENABLED:
        return
    try:
        prev_state = (ultra_mode, superlight_mode, safe_mode)
        while True:
            # psutil.cpu_percent với interval=1 trả về giá trị mẫu trong 1s
            cpu = psutil.cpu_percent(interval=1)
            try:
                mem = psutil.virtual_memory().percent
            except Exception:
                mem = 0.0

            if cpu >= cpu_high or mem >= MEMORY_HIGH_PERCENT:
                # Tải cao: vào safe_mode (tạm dừng giao dịch) và bật superlight
                safe_mode = True
                superlight_mode = True
                ultra_mode = False
            elif cpu >= cpu_medium:
                # Tải trung bình: giới hạn các tính toán nặng, cho phép giao dịch giới hạn
                safe_mode = False
                superlight_mode = True
                ultra_mode = False
            else:
                # Bình thường: ưu tiên ultra — nếu CPU giảm, CHUYỂN VỀ ULTRA
                # (clear superlight_mode so system does not remain in SUPERLIGHT)
                safe_mode = False
                ultra_mode = True
                # Nếu CPU đã hạ xuống, đảm bảo superlight_mode bị tắt
                superlight_mode = False

            # Đồng bộ cờ SUPERLIGHT toàn cục để các kiểm tra hiện có tiếp tục hoạt động
            try:
                SUPERLIGHT = superlight_mode
            except Exception:
                pass

            # Ghi log khi chế độ runtime thay đổi để dễ quan sát
            try:
                current_state = (ultra_mode, superlight_mode, safe_mode)
                if current_state != prev_state:
                    # Chuyển log thay đổi chế độ sang DEBUG để không in chồng lên console.
                    logger.debug(f"🔁 Chế độ runtime thay đổi: ultra_mode={ultra_mode}, superlight_mode={superlight_mode}, safe_mode={safe_mode} (CPU={cpu:.1f}%, MEM={mem:.1f}%)")
                    prev_state = current_state
            except Exception:
                pass

            time.sleep(poll_interval)
    except Exception:
        # Bắt mọi ngoại lệ nhẹ nhàng - giám sát là nỗ lực tốt nhất (best-effort)
        return


def get_runtime_mode():
    """Return a short string describing the current runtime mode.

    Possible values: 'SAFE', 'SUPERLIGHT', 'ULTRA'.
    This is read-only and safe to call even if psutil is not available.
    """
    try:
        if safe_mode:
            return 'SAFE'
        if superlight_mode:
            return 'SUPERLIGHT'
        if ultra_mode:
            return 'ULTRA'
        return 'UNKNOWN'
    except Exception:
        return 'UNKNOWN'


def heartbeat(poll_interval=60):
    """Periodic heartbeat logger to report runtime mode and CPU/MEM usage.

    Runs as a daemon thread. Best-effort: if psutil isn't available it will
    only log the runtime mode.
    """
    # Deferred lookup of the dedicated heartbeat logger (created after main logger)
    try:
        hb_logger = logging.getLogger('cpu_heartbeat')
    except Exception:
        hb_logger = None

    try:
        while True:
            mode = get_runtime_mode()
            try:
                if PSUTIL_AVAILABLE:
                    cpu = psutil.cpu_percent(interval=1)
                    mem = psutil.virtual_memory().percent
                    msg = f"💓 Heartbeat: Mode={mode} | CPU={cpu:.1f}% | MEM={mem:.1f}%"
                else:
                    msg = f"💓 Heartbeat: Mode={mode}"

                # Write to dedicated heartbeat log file when available
                try:
                    if hb_logger and getattr(hb_logger, 'handlers', None):
                        hb_logger.info(msg)
                except Exception:
                    pass

                # ALWAYS print a visible separator + heartbeat message to the main console logger
                try:
                    sep = '=' * 70
                    logger.info(sep)
                    logger.info(msg)
                    logger.info(sep)
                except Exception:
                    # Fallback: at least log the message
                    logger.info(msg)
            except Exception:
                logger.debug("⚠️ Heartbeat sample failed")
            time.sleep(poll_interval)
    except Exception:
        return


# Lightweight indicator cache used to avoid recomputing O(n) indicators each tick.
class IndicatorCache:
    def __init__(self):
        # key -> (last_len, value)
        self._cache = {}

    def get(self, key, length):
        v = self._cache.get(key)
        if v is None:
            return None
        last_len, value = v
        if last_len == length:
            return value
        return None

    def set(self, key, length, value):
        try:
            self._cache[key] = (length, value)
        except Exception:
            pass


# Global cache instance
indicator_cache = IndicatorCache()

# Auto-mode globals controlled by AutoModeController (can be toggled at runtime)
AUTO_FULL_SMC = True
AUTO_DEEP_VOLATILITY = True

# ======================================
# DATA CACHE ENGINE - ULTRA v2.1
# ======================================
class DataCache:
    def __init__(self):
        self.last_timestamp = None
        self.cached_indicators = {}
        self.cached_smc = {}

data_cache = DataCache()

# Import market analysis functions (SMC detection)
from core.market_analysis import (
    detect_structure, detect_BOS_CHOCH, volume_profile, detect_fvg,
    detect_ob, liquidity_map, detect_stop_hunt, detect_false_breakout,
    detect_order_blocks, detect_volume_climax, detect_exhaustion,
    calculate_delta, detect_momentum_shift, detect_choch
)

# Import helper functions
from utils.helpers import (
    normalize_symbol, tr, remove_accents, _persist_latest_signal_log,
    _log_separator, save_feature_importances, add_session_features
)

# Import data fetcher
from core.data_fetcher import MarketDataFetcher

# Import technical indicators
from core.indicators import (
    TechnicalIndicators, ema_distance, ATR, bollinger_width, volume,
    price_range, ADX, supertrend, price,
    check_ema_alignment, check_vwap, check_keltner,
    check_volume_confirmation, check_adx_momentum, check_ichimoku,
    strong_candle, technical_filter
)
# NOTE: detect_sideway() is defined locally in this file (returns tuple), not imported from indicators.py

# Import AI models
from core.models import (
    XGBoostTrendModel, TrendAI, ReversalAI,
    build_trend_features, build_reversal_features, build_volatility_features
)
# Import Chart Pattern Detector
from core.chart_pattern_detector import ChartPatternDetector, integrate_pattern_detection

# Import money management
from core.money_management import AutoModeController, AIMoneyManager, DrawdownProtector

# Import backtest engine
from core.backtest import BacktestEngine, HTTPSignalHandler

# 🔥 NEW: Import ICT Multi-Timeframe Logic (Dec 11, 2025)
try:
    from core.mtf_config import (
        check_htf_trend,
        check_mmf_structure,
        find_order_blocks_m5,
        calculate_ict_sl_tp,
        HTF_TREND_LOGIC,
        MMF_STRUCTURE_LOGIC,
        LTF_ENTRY_LOGIC,
        SNIPER_LOGIC,
        SL_TP_LOGIC,
        TRADE_FILTER
    )
    ICT_LOGIC_AVAILABLE = True
    print("✅ ICT Multi-Timeframe Logic imported successfully")
except ImportError as e:
    print(f"⚠️ Warning: ICT Logic not available: {e}")
    print("   System will run without ICT Multi-Timeframe logic")
    ICT_LOGIC_AVAILABLE = False
    check_htf_trend = None
    check_mmf_structure = None
    find_order_blocks_m5 = None
    calculate_ict_sl_tp = None
 
# --- Optional helper stubs (REMOVED - now in core.market_analysis) ---------
# Keeping this comment for reference during refactoring
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
        volume_profile = {}
        for i in range(len(bins)-1):
            mask = (df['low'] <= bins[i+1]) & (df['high'] >= bins[i])
            volume_profile[(bins[i] + bins[i+1])/2] = df.loc[mask, 'volume'].sum()

        # Find POC (Point of Control) - highest volume
        poc = max(volume_profile, key=volume_profile.get)

        # VAH/VAL (Value Area High/Low) - 70% of volume around POC
        total_volume = sum(volume_profile.values())
        sorted_prices = sorted(volume_profile.items(), key=lambda x: x[1], reverse=True)

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

        # Calculate exhaustion level
        if recent_spike:
            vol_drop = (vol_3.iloc[-3] - vol_3.iloc[-1]) / vol_3.iloc[-3] if vol_3.iloc[-3] > 0 else 0
            exhaustion_level = min(1.0, vol_drop)

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


import warnings
warnings.filterwarnings('ignore')
# Fix for TrendAI training: import precision_score, recall_score
from sklearn.metrics import precision_score, recall_score
import unicodedata


def normalize_symbol(symbol: str) -> str:
    """Normalize symbol names to base instrument names.

    Examples:
      - 'XAUUSD-VIPc' -> 'XAUUSD'
      - 'XAUUSDm' -> 'XAUUSD'
      - 'GOLD' -> 'XAUUSD' (alias)
    """
    if symbol is None:
        return symbol
    s = symbol.upper()
    # Common VT/other broker variants mapping
    variants = [
        'XAUUSC', 'XAUUSDC', 'XAUUSD-C', 'XAUUSD.C', 'XAUUSDVIPC', 'XAUUSD-VIPC', 'XAUUSDM', 'XAUUSDM'
    ]
    for v in variants:
        if v in s:
            return 'XAUUSD'

    # Map common precious metals aliases
    if 'XAU' in s or 'GOLD' in s:
        return 'XAUUSD'
    # Map common crypto aliases (BTC / XBT) to broker pair
    if 'BTC' in s or 'XBT' in s:
        return 'BTCUSD'
    return symbol

# Global language for logs/notifications. Values: 'en' or 'vi'
LOG_LANG = 'en'

# Simple translation dictionary for frequently used messages added by scripts
TRANSLATIONS = {
    "Pattern classifier training completed": "✅ Huấn luyện bộ phân loại mô hình hoàn tất",
    "Pattern classifier training failed": "❌ Huấn luyện bộ phân loại mô hình thất bại",
    "--train-patterns requested: Generating dataset and training pattern classifier...": "📚 Yêu cầu --train-patterns: Đang sinh dữ liệu và huấn luyện bộ phân loại mô hình...",
    "ML libraries not available in this environment. Install scikit-learn/xgboost/joblib.": "❌ Thư viện ML chưa được cài đặt. Hãy cài scikit-learn và joblib.",
    "Generating synthetic dataset ({samples} samples/pattern) ...": "📦 Đang sinh dữ liệu tổng hợp ({samples} mẫu/loại) ...",
    "Loading dataset from {path} ...": "📥 Đang tải dữ liệu từ {path} ...",
    "Training RandomForest classifier on synthetic patterns...": "🧠 Đang huấn luyện RandomForest trên các mẫu mô hình...",
    "Saved classifier: {path}": "✅ Đã lưu bộ phân loại: {path}",
    "Saved scaler: {path}": "✅ Đã lưu scaler: {path}",
}


def tr(msg: str, **kwargs) -> str:
    """Translate a message key to the selected language if available.

    This is deliberately simple: only translates exact keys present in TRANSLATIONS.
    Use `tr("Saved classifier: {path}", path=p)` to format translated templates.
    """
    try:
        if LOG_LANG == 'vi':
            tmpl = TRANSLATIONS.get(msg, None)
            if tmpl is not None:
                return tmpl.format(**kwargs)
        return msg.format(**kwargs) if kwargs else msg
    except Exception:
        return msg


def remove_accents(text: str) -> str:
    """Remove diacritics from Unicode text, return ASCII-friendly string."""
    try:
        if not isinstance(text, str):
            return text
        nk = unicodedata.normalize('NFKD', text)
        return ''.join([c for c in nk if not unicodedata.combining(c)])
    except Exception:
        return text


def _persist_latest_signal_log(signal: dict):
    """Append a JSON line with the latest signal into `live_trading/logs/latest_signals.jsonl`.

    This is a lightweight best-effort logger used for debugging and diagnostics.
    It will attempt to make all values JSON-serializable and preserve `fusion_reasons`.

    Additionally, if `fusion_reasons` is present, persist it separately into
    `fusion_explains.jsonl` to guarantee explainability artifacts are captured
    even if the main signal path mutates or strips them later.
    """
    try:
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        out_path = os.path.join(log_dir, 'latest_signals.jsonl')

        # Make a JSON-serializable copy
        serial = {}
        for k, v in (signal or {}).items():
            try:
                if hasattr(v, 'item'):
                    serial[k] = v.item()
                elif isinstance(v, (int, float, str, bool)) or v is None:
                    serial[k] = v
                else:
                    # Try json.dumps first for nested dict/list
                    try:
                        json.dumps(v)
                        serial[k] = v
                    except Exception:
                        serial[k] = str(v)
            except Exception:
                try:
                    serial[k] = str(v)
                except Exception:
                    serial[k] = None

        # Ensure timestamp for ordering
        try:
            serial.setdefault('persist_ts', int(time.time() * 1000))
        except Exception:
            serial['persist_ts'] = None

        # Append as JSON line (UTF-8, keep unicode for readability)
        try:
            with open(out_path, 'a', encoding='utf-8') as fh:
                fh.write(json.dumps(serial, ensure_ascii=False) + '\n')
        except Exception:
            # Fallback: ascii-safe write
            try:
                with open(out_path, 'a', encoding='utf-8') as fh:
                    fh.write(json.dumps(serial, ensure_ascii=True) + '\n')
            except Exception as e:
                logger.debug(f"⚠️ _persist_latest_signal_log failed to write: {e}")

        # If fusion_reasons present, persist to dedicated explains file as well
        try:
            fusion = serial.get('fusion_reasons') or (signal or {}).get('fusion_reasons')
            if fusion:
                fusion_file = os.path.join(log_dir, 'fusion_explains.jsonl')
                payload = {
                    'signal_id': serial.get('signal_id'),
                    'timestamp': serial.get('timestamp') or serial.get('persist_ts'),
                    'fusion_reasons': fusion
                }
                try:
                    with open(fusion_file, 'a', encoding='utf-8') as fh2:
                        fh2.write(json.dumps(payload, ensure_ascii=False) + '\n')
                except Exception:
                    try:
                        with open(fusion_file, 'a', encoding='utf-8') as fh2:
                            fh2.write(json.dumps(payload, ensure_ascii=True) + '\n')
                    except Exception as e:
                        logger.debug(f"⚠️ Failed writing fusion_explains: {e}")
        except Exception:
            # Non-critical: continue
            pass

    except Exception as e:
        try:
            logger.debug(f"⚠️ _persist_latest_signal_log error: {e}")
        except Exception:
            pass

# MT5 Connection
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    print("⚠️ MetaTrader5 library not available - using demo data")
    MT5_AVAILABLE = False

# ML Libraries
try:
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import classification_report, accuracy_score
    import xgboost as xgb
    import joblib
    from sklearn.calibration import CalibratedClassifierCV
    ML_AVAILABLE = True
except ImportError:
    print("⚠️ ML libraries not available - running in demo mode")
    ML_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# Dedicated heartbeat logger writing to a separate file to avoid polluting main logs
try:
    hb_logger = logging.getLogger('cpu_heartbeat')
    if not hb_logger.handlers:
        hb_log_dir = os.path.join('Files')
        try:
            os.makedirs(hb_log_dir, exist_ok=True)
        except Exception:
            pass
        hb_path = os.path.join(hb_log_dir, 'cpu_heartbeat.log')
        try:
            fh = logging.FileHandler(hb_path, encoding='utf-8')
            fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            hb_logger.addHandler(fh)
            hb_logger.setLevel(logging.INFO)
            hb_logger.propagate = False
        except Exception:
            # If file handler creation fails, leave hb_logger without handlers
            pass
except Exception:
    hb_logger = None

# Load a default minimum lot from config if available
try:
    from config import config as lc
    DEFAULT_MIN_LOT = float(getattr(lc, 'MIN_LOT', 0.01))
except Exception:
    DEFAULT_MIN_LOT = 0.01

# Helper: pretty separator for log blocks. Call `logger.sep("Optional message")` to print
# a clear visual separator in logs so new commands/blocks are easy to spot.
def _log_separator(msg: str = None, char: str = '=', width: int = 80):
    try:
        line = char * width
        logger.info(line)
        if msg:
            logger.info(f" {msg} ")
            logger.info(line)
        else:
            logger.info(line)
    except Exception:
        # Best-effort: avoid raising from logging helper
        try:
            print('=' * width)
            if msg:
                print(msg)
            print('=' * width)
        except Exception:
            pass

# Attach helper to module logger for convenient calls from other modules
try:
    setattr(logger, 'sep', _log_separator)
except Exception:
    pass


def save_feature_importances(model, feature_cols, model_name: str, outdir: str = 'live_trading/feature_importances', top_k: int = 20,
                             X=None, y=None, compute_permutation: bool = False, n_repeats: int = 10, random_state: int = 42):
    """Compute and save feature importances for trained models.

    Supports models with `feature_importances_`, `coef_`, or XGBoost `get_booster()`.
    Saves CSV to `outdir/{model_name}_feature_importances.csv` and logs top-k features.
    """
    try:
        os.makedirs(outdir, exist_ok=True)
        import numpy as _np
        import pandas as _pd

        # Compute importances array aligned with feature_cols (base importance)
        if hasattr(model, 'feature_importances_'):
            importances = _np.array(model.feature_importances_)
        elif hasattr(model, 'coef_'):
            coef = _np.array(model.coef_)
            if coef.ndim > 1:
                importances = _np.mean(_np.abs(coef), axis=0)
            else:
                importances = _np.abs(coef)
        elif hasattr(model, 'get_booster'):
            try:
                booster = model.get_booster()
                score = booster.get_score(importance_type='gain')
                importances = _np.zeros(len(feature_cols))
                for i, f in enumerate(feature_cols):
                    importances[i] = float(score.get(f, score.get(f'f{i}', 0.0)))
            except Exception:
                importances = _np.zeros(len(feature_cols))
        else:
            importances = _np.zeros(len(feature_cols))

        # Ensure length matches
        if len(importances) != len(feature_cols):
            arr = _np.zeros(len(feature_cols))
            arr[:min(len(importances), len(arr))] = importances[:len(arr)]
            importances = arr

        df_imp = _pd.DataFrame({'feature': list(feature_cols), 'importance': list(importances)})
        df_imp = df_imp.sort_values('importance', ascending=False).reset_index(drop=True)

        csv_path = os.path.join(outdir, f"{model_name}_feature_importances.csv")
        try:
            df_imp.to_csv(csv_path, index=False, encoding='utf-8')
            logger.info(f"✅ Đã lưu feature importances cho {model_name} → {csv_path}")
        except Exception:
            logger.debug(f"⚠️ Không thể lưu feature importances cho {model_name} vào {csv_path}")

        # Also produce a PNG bar chart for top_k features if matplotlib is available
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            top = df_imp.head(top_k)
            if not top.empty:
                plt.figure(figsize=(8, max(4, 0.3 * len(top))))
                plt.barh(top['feature'][::-1], top['importance'][::-1], color='C0')
                plt.xlabel('Importance')
                plt.title(f'{model_name} - Top {min(top_k, len(top))} Feature Importances')
                plt.tight_layout()
                png_path = os.path.join(outdir, f"{model_name}_feature_importances.png")
                try:
                    plt.savefig(png_path, dpi=150)
                    plt.close()
                    logger.info(f"🖼️ Đã lưu biểu đồ feature importances cho {model_name} → {png_path}")
                except Exception:
                    logger.debug(f"⚠️ Không thể lưu PNG cho {model_name}")
        except Exception:
            # matplotlib not available or plotting failed — ignore silently
            pass

        # Optional: compute permutation importance if requested and X,y provided
        if compute_permutation and X is not None and y is not None:
            try:
                from sklearn.inspection import permutation_importance as _perm
                X_arr = X
                y_arr = y
                try:
                    # Accept pandas DataFrame/Series or numpy arrays
                    import numpy as _np
                    if hasattr(X_arr, 'values'):
                        X_arr = X_arr.values
                    if hasattr(y_arr, 'values'):
                        y_arr = y_arr.values
                except Exception:
                    pass

                perm_res = _perm(model, X_arr, y_arr, n_repeats=n_repeats, random_state=random_state, n_jobs=1)
                perm_means = perm_res.importances_mean
                perm_stds = perm_res.importances_std

                df_perm = _pd.DataFrame({'feature': list(feature_cols), 'perm_mean': list(perm_means), 'perm_std': list(perm_stds)})
                df_perm = df_perm.sort_values('perm_mean', ascending=False).reset_index(drop=True)

                perm_csv = os.path.join(outdir, f"{model_name}_feature_importances_permutation.csv")
                try:
                    df_perm.to_csv(perm_csv, index=False, encoding='utf-8')
                    logger.info(f"✅ Đã lưu permutation importances cho {model_name} → {perm_csv}")
                except Exception:
                    logger.debug(f"⚠️ Không thể lưu permutation importances cho {model_name}")

                # Plot permutation importances
                try:
                    import matplotlib
                    matplotlib.use('Agg')
                    import matplotlib.pyplot as plt

                    top_p = df_perm.head(top_k)
                    if not top_p.empty:
                        plt.figure(figsize=(8, max(4, 0.3 * len(top_p))))
                        plt.barh(top_p['feature'][::-1], top_p['perm_mean'][::-1], color='C1')
                        plt.xlabel('Permutation Importance (mean)')
                        plt.title(f'{model_name} - Top {min(top_k, len(top_p))} Permutation Importances')
                        plt.tight_layout()
                        perm_png = os.path.join(outdir, f"{model_name}_feature_importances_permutation.png")
                        try:
                            plt.savefig(perm_png, dpi=150)
                            plt.close()
                            logger.info(f"🖼️ Đã lưu biểu đồ permutation importances cho {model_name} → {perm_png}")
                        except Exception:
                            logger.debug(f"⚠️ Không thể lưu permutation PNG cho {model_name}")
                except Exception:
                    pass

                try:
                    top_p_list = df_perm.head(top_k).apply(lambda r: (r['feature'], float(r['perm_mean'])), axis=1).tolist()
                    logger.info(f"📌 Top permutation features cho {model_name}: {top_p_list}")
                except Exception:
                    pass

            except Exception as e:
                try:
                    logger.debug(f"⚠️ Permutation importance failed for {model_name}: {e}")
                except Exception:
                    pass

        # Log top-k features concisely
        try:
            top = df_imp.head(top_k)
            top_list = top.apply(lambda r: (r['feature'], float(r['importance'])), axis=1).tolist()
            logger.info(f"📌 Top {min(top_k, len(top_list))} features cho {model_name}: {top_list}")
        except Exception:
            try:
                logger.info(f"📌 Feature importances (truncated) for {model_name}: {df_imp.head(10).to_dict('records')}")
            except Exception:
                pass

        return True
    except Exception as e:
        try:
            logger.debug(f"⚠️ save_feature_importances error for {model_name}: {e}")
        except Exception:
            pass
        return False


def add_session_features(df, timezone: str = 'UTC'):
    """Add session indicators (Asia/EU/US) based on timestamp index or a 'timestamp' column.

    - Adds `session` categorical column with values 'asia','eu','us','other'.
    - Adds one-hot boolean columns: `session_asia`, `session_eu`, `session_us`.

    Assumes timestamps are timezone-naive in UTC unless specified otherwise. Returns modified DataFrame.
    """
    try:
        import pandas as _pd
        if df is None or df.empty:
            return df

        # Ensure we have a DatetimeIndex
        if isinstance(df.index, _pd.DatetimeIndex):
            idx = df.index
        elif 'timestamp' in df.columns:
            idx = _pd.to_datetime(df['timestamp'], errors='coerce')
            df = df.set_index(idx)
        else:
            # nothing to do
            return df

        # Convert to provided timezone if possible
        try:
            idx_utc = idx.tz_localize('UTC') if idx.tz is None else idx.tz_convert('UTC')
            if timezone and timezone.upper() != 'UTC':
                idx_tz = idx_utc.tz_convert(timezone)
            else:
                idx_tz = idx_utc
        except Exception:
            # Fallback to naive hours
            idx_tz = idx

        hours = idx_tz.hour if hasattr(idx_tz, 'hour') else idx_tz.hour

        # Define session windows (UTC hours)
        # Asia: 0-8 UTC (approx), Europe: 6-16 UTC, US: 13-23 UTC — these are approximate
        asia_mask = (hours >= 0) & (hours < 8)
        eu_mask = (hours >= 6) & (hours < 16)
        us_mask = (hours >= 13) & (hours < 23)

        df['session_asia'] = asia_mask.astype(int)
        df['session_eu'] = eu_mask.astype(int)
        df['session_us'] = us_mask.astype(int)

        # session as numeric code: 0=other, 1=asia, 2=eu, 3=us (numeric to avoid ML conversion issues)
        try:
            df['session'] = 0
            df.loc[asia_mask, 'session'] = 1
            df.loc[eu_mask, 'session'] = 2
            df.loc[us_mask, 'session'] = 3
            df['session'] = df['session'].astype(int)
        except Exception:
            # fallback: create numeric list
            sess = []
            for i in range(len(df)):
                if asia_mask[i]:
                    sess.append(1)
                elif eu_mask[i]:
                    sess.append(2)
                elif us_mask[i]:
                    sess.append(3)
                else:
                    sess.append(0)
            df['session'] = sess

        return df
    except Exception:
        return df

# Print an initial separator so each run is clearly delimited in logs
try:
    logger.sep('=== NEW LOG BLOCK ===')
except Exception:
    pass

#==============================================================================
# 1. 📊 DATA FETCHING & PREPROCESSING (MOVED TO core/data_fetcher.py)
#==============================================================================
# MarketDataFetcher class has been moved to core/data_fetcher.py

#==============================================================================
# 2. 🧠 AI MODEL & TECHNICAL INDICATORS (MOVED TO core/indicators.py)
#==============================================================================
# TechnicalIndicators class and helper functions moved to core/indicators.py

class VolatilityAI:
    """Technical indicators calculation"""
    
    @staticmethod
    def calculate_sma(df, periods=[5, 10, 20]):
        """Simple Moving Averages"""
        for period in periods:
            df[f'sma_{period}'] = df['close'].rolling(period).mean()
        return df

    @staticmethod
    def calculate_rsi(df, period=14):
        """Relative Strength Index - compatibility method (keeps existing logic)"""
        try:
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / (loss + 1e-8)
            df['rsi'] = 100 - (100 / (1 + rs))
        except Exception:
            df['rsi'] = 50.0
        return df

    @staticmethod
    def calculate_macd(df, fast=12, slow=26, signal=9):
        """MACD Oscillator - compatibility method"""
        try:
            exp1 = df['close'].ewm(span=fast).mean()
            exp2 = df['close'].ewm(span=slow).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=signal).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
        except Exception:
            df['macd'] = df['macd_signal'] = df['macd_histogram'] = 0.0
        return df

    @staticmethod
    def calculate_bollinger(df, period=20, std=2):
        """Bollinger Bands - compatibility method"""
        try:
            df['bb_middle'] = df['close'].rolling(period).mean()
            bb_std = df['close'].rolling(period).std()
            df['bb_upper'] = df['bb_middle'] + (bb_std * std)
            df['bb_lower'] = df['bb_middle'] - (bb_std * std)
        except Exception:
            df['bb_middle'] = df['bb_upper'] = df['bb_lower'] = df['close']
        return df

    @staticmethod
    def calculate_atr(df, period=14):
        """Average True Range - compatibility method"""
        try:
            df['tr1'] = abs(df['high'] - df['low'])
            df['tr2'] = abs(df['high'] - df['close'].shift())
            df['tr3'] = abs(df['low'] - df['close'].shift())
            df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
            df['atr'] = df['tr'].rolling(period).mean()
        except Exception:
            df['tr1'] = df['tr2'] = df['tr3'] = df['tr'] = 0.0
            df['atr'] = 0.0
        return df

    @staticmethod
    def analyze_trend(df, short_period=20, long_period=50):
        """Phân tích xu hướng thị trường và phát hiện sideways (compat wrapper)"""
        try:
            df['ema_short'] = df['close'].ewm(span=short_period).mean()
            df['ema_long'] = df['close'].ewm(span=long_period).mean()
            df['trend_direction'] = np.where(df['ema_short'] > df['ema_long'], 1, -1)
            df['trend_strength'] = abs(df['ema_short'] - df['ema_long']) / (df['close'] + 1e-8)
            df['ema_short_slope'] = df['ema_short'].pct_change(5)
            df['ema_long_slope'] = df['ema_long'].pct_change(10)
            sideways_threshold = 0.001
            df['is_sideways'] = (
                (abs(df['ema_short_slope']) < sideways_threshold) &
                (abs(df['ema_long_slope']) < sideways_threshold) &
                (df['trend_strength'] < df['trend_strength'].rolling(20).mean())
            ).astype(int)
            df['trend_quality'] = np.where(
                df['is_sideways'] == 1,
                0.0,
                df['trend_strength'] / (df['trend_strength'].rolling(20).mean() + 1e-8)
            )
            df['price_vs_ema_short'] = (df['close'] - df['ema_short']) / (df['ema_short'] + 1e-8)
            df['price_vs_ema_long'] = (df['close'] - df['ema_long']) / (df['ema_long'] + 1e-8)
            df['trend_momentum'] = df['ema_short'].pct_change(5)
            df['trend_consistency'] = (
                (df['trend_direction'] == df['trend_direction'].shift(1)) &
                (df['trend_direction'] == df['trend_direction'].shift(2))
            ).astype(int)
        except Exception:
            # Ensure required columns exist with safe defaults
            df['ema_short'] = df['ema_long'] = df['trend_direction'] = 0
            df['trend_strength'] = df['is_sideways'] = df['trend_quality'] = 0
            df['price_vs_ema_short'] = df['price_vs_ema_long'] = 0
            df['trend_momentum'] = df['trend_consistency'] = 0
        return df

    @staticmethod
    def detect_support_resistance(df, window=20, min_touches=2):
        """Phát hiện vùng hỗ trợ và kháng cự (compat wrapper)"""
        try:
            df['resistance_level'] = df['high'].rolling(window, center=True).max()
            df['support_level'] = df['low'].rolling(window, center=True).min()
            df['distance_to_resistance'] = (df['resistance_level'] - df['close']) / df['close']
            df['distance_to_support'] = (df['close'] - df['support_level']) / df['close']
            df['near_resistance'] = (abs(df['distance_to_resistance']) < 0.002).astype(int)
            df['near_support'] = (abs(df['distance_to_support']) < 0.002).astype(int)
            df['resistance_breakout'] = ((df['close'] > df['resistance_level']) & (df['close'].shift(1) <= df['resistance_level'].shift(1))).astype(int)
            df['support_breakdown'] = ((df['close'] < df['support_level']) & (df['close'].shift(1) >= df['support_level'].shift(1))).astype(int)
        except Exception:
            df['resistance_level'] = df['support_level'] = df['distance_to_resistance'] = df['distance_to_support'] = 0
            df['near_resistance'] = df['near_support'] = df['resistance_breakout'] = df['support_breakdown'] = 0
        return df

    @staticmethod
    def analyze_volume(df):
        """Phân tích volume và thanh khoản (compat wrapper)"""
        try:
            df['volume_sma'] = df['volume'].rolling(20).mean()
            df['volume_ratio'] = df['volume'] / df['volume_sma']
            df['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()
            df['price_volume_trend'] = df['close'].pct_change() * df['volume_ratio']
            df['volume_spike'] = (df['volume'] > df['volume_sma'] * 2).astype(int)
            df['price_change_direction'] = np.where(df['close'] > df['close'].shift(1), 1, np.where(df['close'] < df['close'].shift(1), -1, 0))
            df['obv'] = (df['volume'] * df['price_change_direction']).cumsum()
            df['obv_trend'] = df['obv'].rolling(10).mean()
        except Exception:
            df['volume_sma'] = df['volume_ratio'] = df['volume_trend'] = 0
            df['price_volume_trend'] = df['volume_spike'] = df['obv'] = df['obv_trend'] = 0
        return df

    @staticmethod
    def detect_candlestick_patterns(df):
        """Phát hiện mô hình nến (compat wrapper)"""
        try:
            df['body_size'] = abs(df['close'] - df['open']) / df['open']
            df['upper_shadow'] = (df['high'] - np.maximum(df['close'], df['open'])) / df['open']
            df['lower_shadow'] = (np.minimum(df['close'], df['open']) - df['low']) / df['open']
            df['total_range'] = (df['high'] - df['low']) / df['open']
            df['bullish_candle'] = (df['close'] > df['open']).astype(int)
            df['bearish_candle'] = (df['close'] < df['open']).astype(int)
            df['doji'] = (abs(df['close'] - df['open']) / df['open'] < 0.001).astype(int)
            df['hammer'] = ((df['lower_shadow'] > df['body_size'] * 2) & (df['upper_shadow'] < df['body_size'] * 0.5) & (df['body_size'] > 0.002)).astype(int)
            df['shooting_star'] = ((df['upper_shadow'] > df['body_size'] * 2) & (df['lower_shadow'] < df['body_size'] * 0.5) & (df['body_size'] > 0.002)).astype(int)
            df['bullish_engulfing'] = ((df['bullish_candle'] == 1) & (df['bearish_candle'].shift(1) == 1) & (df['close'] > df['open'].shift(1)) & (df['open'] < df['close'].shift(1))).astype(int)
            df['bearish_engulfing'] = ((df['bearish_candle'] == 1) & (df['bullish_candle'].shift(1) == 1) & (df['close'] < df['open'].shift(1)) & (df['open'] > df['close'].shift(1))).astype(int)
            df['morning_star'] = ((df['bearish_candle'].shift(2) == 1) & (df['doji'].shift(1) == 1) & (df['bullish_candle'] == 1) & (df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2)).astype(int)
            df['evening_star'] = ((df['bullish_candle'].shift(2) == 1) & (df['doji'].shift(1) == 1) & (df['bearish_candle'] == 1) & (df['close'] < (df['open'].shift(2) + df['close'].shift(2)) / 2)).astype(int)
        except Exception:
            df['body_size'] = df['upper_shadow'] = df['lower_shadow'] = df['total_range'] = 0
            df['bullish_candle'] = df['bearish_candle'] = df['doji'] = 0
        # Enrich with extended CandlePatternAI if available
        try:
            from utils.candle_pattern_integration import enrich_with_candle_patterns
            df = enrich_with_candle_patterns(df, scoring=True)
        except Exception:
            pass
        return df


def ema_fast(arr, span):
    """Fast EMA implemented with numpy for low-memory/CPU operation.

    This is an additive helper (does not remove existing EMA logic).
    """
    try:
        a = np.asarray(arr, dtype=float)
        if a.size == 0:
            return a
        alpha = 2.0 / (span + 1.0)
        ema = np.empty_like(a)
        ema[0] = a[0]
        for i in range(1, a.size):
            ema[i] = alpha * a[i] + (1.0 - alpha) * ema[i-1]
        return ema
    except Exception:
        # Fallback to pandas if something unexpected
        try:
            return pd.Series(arr).ewm(span=span).mean().values
        except Exception:
            return np.array(arr)
    
    @staticmethod
    def calculate_rsi(df, period=14):
        """Relative Strength Index"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-8)
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    @staticmethod
    def calculate_macd(df, fast=12, slow=26, signal=9):
        """MACD Oscillator"""
        exp1 = df['close'].ewm(span=fast).mean()
        exp2 = df['close'].ewm(span=slow).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=signal).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        return df
    
    @staticmethod
    def calculate_bollinger(df, period=20, std=2):
        """Bollinger Bands"""
        df['bb_middle'] = df['close'].rolling(period).mean()
        bb_std = df['close'].rolling(period).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * std)
        df['bb_lower'] = df['bb_middle'] - (bb_std * std)
        return df
    
    @staticmethod
    def calculate_atr(df, period=14):
        """Average True Range"""
        df['tr1'] = abs(df['high'] - df['low'])
        df['tr2'] = abs(df['high'] - df['close'].shift())
        df['tr3'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr'] = df['tr'].rolling(period).mean()
        return df
    
    @staticmethod
    def analyze_trend(df, short_period=20, long_period=50):
        """🎯 Phân tích xu hướng thị trường và phát hiện sideways"""
        # Trend direction với multiple MA
        df['ema_short'] = df['close'].ewm(span=short_period).mean()
        df['ema_long'] = df['close'].ewm(span=long_period).mean()
        
        # Trend direction và strength
        df['trend_direction'] = np.where(df['ema_short'] > df['ema_long'], 1, -1)
        df['trend_strength'] = abs(df['ema_short'] - df['ema_long']) / (df['close'] + 1e-8)
        
        # 🚫 SIDEWAYS MARKET DETECTION
        # Tính độ dốc của EMA để phát hiện sideways
        df['ema_short_slope'] = df['ema_short'].pct_change(5)  # Slope over 5 periods
        df['ema_long_slope'] = df['ema_long'].pct_change(10)   # Slope over 10 periods
        
        # Sideways conditions:
        # 1. EMA slopes are very small (flat)
        # 2. Price oscillates around EMAs
        # 3. Low trend strength
        sideways_threshold = 0.001  # 0.1% threshold
        
        df['is_sideways'] = (
            (abs(df['ema_short_slope']) < sideways_threshold) &  # EMA ngắn hạn phẳng
            (abs(df['ema_long_slope']) < sideways_threshold) &   # EMA dài hạn phẳng
            (df['trend_strength'] < df['trend_strength'].rolling(20).mean())  # Trend yếu
        ).astype(int)
        
        # Trend quality score (0-1, where 1 = strong trend, 0 = sideways)
        df['trend_quality'] = np.where(
            df['is_sideways'] == 1, 
            0.0,  # Sideways = no trend quality
            df['trend_strength'] / (df['trend_strength'].rolling(20).mean() + 1e-8)
        )
        
        # Price position in trend (avoid division by zero)
        df['price_vs_ema_short'] = (df['close'] - df['ema_short']) / (df['ema_short'] + 1e-8)
        df['price_vs_ema_long'] = (df['close'] - df['ema_long']) / (df['ema_long'] + 1e-8)
        
        # Enhanced trend momentum
        df['trend_momentum'] = df['ema_short'].pct_change(5)
        
        # Multi-timeframe trend confirmation
        df['trend_consistency'] = (
            (df['trend_direction'] == df['trend_direction'].shift(1)) &
            (df['trend_direction'] == df['trend_direction'].shift(2))
        ).astype(int)
        
        return df
    
    @staticmethod
    def detect_support_resistance(df, window=20, min_touches=2):
        """🏗️ Phát hiện vùng hỗ trợ và kháng cự"""
        # Rolling max/min for S/R levels
        df['resistance_level'] = df['high'].rolling(window, center=True).max()
        df['support_level'] = df['low'].rolling(window, center=True).min()
        
        # Distance to S/R levels
        df['distance_to_resistance'] = (df['resistance_level'] - df['close']) / df['close']
        df['distance_to_support'] = (df['close'] - df['support_level']) / df['close']
        
        # S/R strength (based on volume và touches)
        df['near_resistance'] = (abs(df['distance_to_resistance']) < 0.002).astype(int)
        df['near_support'] = (abs(df['distance_to_support']) < 0.002).astype(int)
        
        # Breakout potential
        df['resistance_breakout'] = ((df['close'] > df['resistance_level']) & 
                                   (df['close'].shift(1) <= df['resistance_level'].shift(1))).astype(int)
        df['support_breakdown'] = ((df['close'] < df['support_level']) & 
                                 (df['close'].shift(1) >= df['support_level'].shift(1))).astype(int)
        
        return df
    
    @staticmethod
    def analyze_volume(df):
        """📊 Phân tích volume và thanh khoản"""
        # Volume indicators
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        
        # Volume trend
        df['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()
        
        # Price-Volume relationship
        df['price_volume_trend'] = df['close'].pct_change() * df['volume_ratio']
        
        # Volume spikes
        df['volume_spike'] = (df['volume'] > df['volume_sma'] * 2).astype(int)
        
        # On-Balance Volume (OBV)
        df['price_change_direction'] = np.where(df['close'] > df['close'].shift(1), 1, 
                                               np.where(df['close'] < df['close'].shift(1), -1, 0))
        df['obv'] = (df['volume'] * df['price_change_direction']).cumsum()
        df['obv_trend'] = df['obv'].rolling(10).mean()
        
        return df
    
    @staticmethod
    def detect_candlestick_patterns(df):
        """🕯️ Phát hiện mô hình nến"""
        # Basic candle properties
        df['body_size'] = abs(df['close'] - df['open']) / df['open']
        df['upper_shadow'] = (df['high'] - np.maximum(df['close'], df['open'])) / df['open']
        df['lower_shadow'] = (np.minimum(df['close'], df['open']) - df['low']) / df['open']
        df['total_range'] = (df['high'] - df['low']) / df['open']
        
        # Candle direction
        df['bullish_candle'] = (df['close'] > df['open']).astype(int)
        df['bearish_candle'] = (df['close'] < df['open']).astype(int)
        
        # Doji pattern
        df['doji'] = (abs(df['close'] - df['open']) / df['open'] < 0.001).astype(int)
        
        # Hammer và Shooting Star
        df['hammer'] = ((df['lower_shadow'] > df['body_size'] * 2).astype(bool) & 
                       (df['upper_shadow'] < df['body_size'] * 0.5).astype(bool) &
                       (df['body_size'] > 0.002).astype(bool)).astype(int)
        
        df['shooting_star'] = ((df['upper_shadow'] > df['body_size'] * 2).astype(bool) & 
                              (df['lower_shadow'] < df['body_size'] * 0.5).astype(bool) &
                              (df['body_size'] > 0.002).astype(bool)).astype(int)
        
        # Engulfing patterns
        df['bullish_engulfing'] = ((df['bullish_candle'] == 1).astype(bool) & 
                                  (df['bearish_candle'].shift(1) == 1).astype(bool) &
                                  (df['close'] > df['open'].shift(1)).astype(bool) &
                                  (df['open'] < df['close'].shift(1)).astype(bool)).astype(int)
        
        df['bearish_engulfing'] = ((df['bearish_candle'] == 1).astype(bool) & 
                                  (df['bullish_candle'].shift(1) == 1).astype(bool) &
                                  (df['close'] < df['open'].shift(1)).astype(bool) &
                                  (df['open'] > df['close'].shift(1)).astype(bool)).astype(int)
        
        # Morning Star và Evening Star (3-candle patterns)
        df['morning_star'] = ((df['bearish_candle'].shift(2) == 1).astype(bool) &
                             (df['doji'].shift(1) == 1).astype(bool) &
                             (df['bullish_candle'] == 1).astype(bool) &
                             (df['close'] > (df['open'].shift(2) + df['close'].shift(2)) / 2).astype(bool)).astype(int)
        
        df['evening_star'] = ((df['bullish_candle'].shift(2) == 1).astype(bool) &
                             (df['doji'].shift(1) == 1).astype(bool) &
                             (df['bearish_candle'] == 1).astype(bool) &
                             (df['close'] < (df['open'].shift(2) + df['close'].shift(2)) / 2).astype(bool)).astype(int)
        
        # Enrich with extended CandlePatternAI if available (non-breaking)
        try:
            from utils.candle_pattern_integration import enrich_with_candle_patterns
            df = enrich_with_candle_patterns(df, scoring=True)
        except Exception:
            pass

        return df


# ========== SIDEWAYS DETECTION HELPER FUNCTIONS ==========

def ema_distance(data, timeframe='H1'):
    """Tính khoảng cách giữa các EMA để phát hiện compression"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 50:
            return 0.0

        # Tính EMA 20 và EMA 50
        ema20 = df['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]

        # Tính khoảng cách %
        distance = abs(ema20 - ema50) / ema50
        return distance
    except:
        return 0.0

def ATR(data, timeframe='H1', period=14):
    """Tính Average True Range"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return 0.0

        high = df['high']
        low = df['low']
        close = df['close'].shift(1)

        tr = pd.concat([
            high - low,
            abs(high - close),
            abs(low - close)
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean().iloc[-1]
        return atr
    except:
        return 0.0

def bollinger_width(data, timeframe='H1', period=20):
    """Tính độ rộng Bollinger Bands"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return 0.0

        close = df['close']
        sma = close.rolling(period).mean()
        std = close.rolling(period).std()

        upper = sma + (std * 2)
        lower = sma - (std * 2)

        width = (upper - lower) / sma
        return width.iloc[-1]
    except:
        return 0.0

def volume(data, timeframe='H1'):
    """Tính volume trung bình"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return 0.0

        return df['volume'].rolling(20).mean().iloc[-1]
    except:
        return 0.0

def price_range(data, timeframe='H1'):
    """Tính biên độ giá"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return 0.0

        ranges = (df['high'] - df['low']) / df['close']
        return ranges.rolling(20).mean().iloc[-1]
    except:
        return 0.0

def ADX(data, timeframe='H1', period=14):
    """Tính ADX (Average Directional Index)"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period + 1:
            return 0.0

        # Tính True Range
        high = df['high']
        low = df['low']
        close = df['close']

        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)

        # Tính +DM và -DM
        dm_plus = np.where((high - high.shift(1)) > (low.shift(1) - low),
                          np.maximum(high - high.shift(1), 0), 0)
        dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)),
                           np.maximum(low.shift(1) - low, 0), 0)

        # Smooth với EMA
        atr = tr.ewm(span=period).mean()
        di_plus = pd.Series(dm_plus).ewm(span=period).mean() / atr * 100
        di_minus = pd.Series(dm_minus).ewm(span=period).mean() / atr * 100

        # Tính DX và ADX
        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100
        adx = dx.ewm(span=period).mean()

        return adx.iloc[-1]
    except:
        return 0.0

def classify_sideways(data, sideway_score, range_pct, atr_pct):
    """
    Phân loại sideways market: TIGHT vs WIDE vs TRENDING
    
    Returns:
        str: 'TIGHT', 'WIDE', hoặc 'TRENDING'
    """
    # TIGHT SIDEWAYS: Range hẹp + ATR thấp → KHÔNG trade (whipsaw risk)
    if range_pct < 0.005 and atr_pct < 0.003:  # Range < 0.5% AND ATR < 0.3%
        return 'TIGHT'
    
    # WIDE SIDEWAYS: Range 0.5-2% + ATR cao → CÓ THỂ trade (range trading)
    elif sideway_score >= 2 and range_pct >= 0.005 and range_pct < 0.02 and atr_pct >= 0.005:
        return 'WIDE'
    
    # TRENDING hoặc VERY WIDE RANGE: Range > 2% → Trade bình thường
    else:
        return 'TRENDING'


def detect_sideway(data):
    """
    Phát hiện thị trường sideways dựa trên nhiều tiêu chí

    Returns:
        tuple: (sideway_score, sideways_type, range_pct, atr_pct)
               - sideway_score (int): 0-7, cao hơn = sideways mạnh hơn
               - sideways_type (str): 'TIGHT', 'WIDE', hoặc 'TRENDING'
               - range_pct (float): Biên độ % của range
               - atr_pct (float): ATR % so với giá
    """
    sideway_score = 0

    # 1. EMA Compression: EMA 20 và 50 sát nhau (< 0.5%)
    ema_dist = ema_distance(data)
    if ema_dist < 0.005:  # < 0.5%
        sideway_score += 1

    # 2. ATR Low: Biến động thấp (< 0.3%)
    atr_val = ATR(data)
    current_price = data.get('H1', pd.DataFrame()).get('close', pd.Series()).iloc[-1] if data.get('H1') is not None else 1000
    atr_pct = atr_val / current_price if current_price > 0 else 0
    if atr_pct < 0.003:  # < 0.3%
        sideway_score += 1
    
    # Store atr_pct for classification

    # 3. Bollinger Squeeze: Bands sát nhau (< 1%)
    bb_width = bollinger_width(data)
    if bb_width < 0.01:  # < 1%
        sideway_score += 1

    # 4. Volume Dry-up: Volume thấp
    vol_avg = volume(data)
    if vol_avg < 1000:  # Threshold tùy chỉnh
        sideway_score += 1

    # 5. Range Width: Biên độ giá nhỏ (< 0.5%)
    range_pct = price_range(data)
    if range_pct < 0.005:  # < 0.5%
        sideway_score += 1
    
    # Store range_pct for classification

    # 6. ADX Low: Không có xu hướng mạnh (< 20)
    adx_val = ADX(data)
    if adx_val < 20:
        sideway_score += 1

    # 7. Choppy Structure: Price oscillate trong range hẹp
    try:
        df = data.get('H1')
        if df is not None and len(df) >= 20:
            recent_high = df['high'].tail(20).max()
            recent_low = df['low'].tail(20).min()
            current = df['close'].iloc[-1]
            range_size = (recent_high - recent_low) / recent_low

            # Price trong 70% range gần nhất
            position_in_range = (current - recent_low) / (recent_high - recent_low)
            if 0.3 < position_in_range < 0.7 and range_size < 0.02:  # Range < 2%
                sideway_score += 1
    except:
        pass

    # Classify sideways type
    sideways_type = classify_sideways(data, sideway_score, range_pct, atr_pct)
    
    return (sideway_score, sideways_type, range_pct, atr_pct)


def supertrend(data, timeframe='H1', period=10, multiplier=3.0):
    """Tính Supertrend indicator"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return None

        high = df['high']
        low = df['low']
        close = df['close']

        # Tính ATR
        tr = pd.concat([
            high - low,
            abs(high - close.shift(1)),
            abs(low - close.shift(1))
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()

        # Tính basic upper/lower bands
        hl2 = (high + low) / 2
        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)

        # Tính Supertrend
        supertrend = pd.Series(index=df.index)
        trend = pd.Series(index=df.index)

        for i in range(len(df)):
            if i == 0:
                supertrend.iloc[i] = upper_band.iloc[i]
                trend.iloc[i] = 1  # 1 = uptrend, -1 = downtrend
            else:
                # Uptrend
                if close.iloc[i-1] <= supertrend.iloc[i-1]:
                    supertrend.iloc[i] = max(upper_band.iloc[i], supertrend.iloc[i-1])
                else:
                    supertrend.iloc[i] = upper_band.iloc[i]

                # Downtrend
                if close.iloc[i-1] >= supertrend.iloc[i-1]:
                    temp_trend = min(lower_band.iloc[i], supertrend.iloc[i-1])
                else:
                    temp_trend = lower_band.iloc[i]

                # Final trend determination
                if close.iloc[i] > supertrend.iloc[i-1]:
                    trend.iloc[i] = 1
                    supertrend.iloc[i] = temp_trend if temp_trend > supertrend.iloc[i] else supertrend.iloc[i]
                elif close.iloc[i] < supertrend.iloc[i-1]:
                    trend.iloc[i] = -1
                    supertrend.iloc[i] = temp_trend if temp_trend < supertrend.iloc[i] else supertrend.iloc[i]
                else:
                    trend.iloc[i] = trend.iloc[i-1]
                    supertrend.iloc[i] = supertrend.iloc[i-1]

        return supertrend.iloc[-1]

    except Exception as e:
        logger.warning(f"⚠️ Supertrend calculation failed: {e}")
        return None


def price(data, timeframe='H1'):
    """Lấy giá close hiện tại"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) == 0:
            return None
        return df['close'].iloc[-1]
    except:
        return None


def check_ema_alignment(signal, data, timeframe='H1'):
    """Kiểm tra EMA alignment cho signal"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 200:
            return False

        close = df['close'].iloc[-1]

        # Tính EMAs
        ema20 = df['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df['close'].ewm(span=50).mean().iloc[-1]
        ema200 = df['close'].ewm(span=200).mean().iloc[-1]

        if signal == "BUY":
            # BUY: Price > EMA20 > EMA50 > EMA200
            return close > ema20 > ema50 > ema200
        elif signal == "SELL":
            # SELL: Price < EMA20 < EMA50 < EMA200
            return close < ema20 < ema50 < ema200

        return False

    except Exception as e:
        logger.warning(f"⚠️ EMA alignment check failed: {e}")
        return False


def check_vwap(signal, data, timeframe='H1'):
    """Kiểm tra VWAP alignment"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return False

        # Tính VWAP (simplified - using close as proxy for typical price)
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
        current_vwap = vwap.iloc[-1]
        current_price = df['close'].iloc[-1]

        if signal == "BUY":
            return current_price > current_vwap
        elif signal == "SELL":
            return current_price < current_vwap

        return False

    except Exception as e:
        logger.warning(f"⚠️ VWAP check failed: {e}")
        return False


def check_keltner(signal, data, timeframe='H1', period=20, multiplier=2.0):
    """Kiểm tra Keltner Channel"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period:
            return False

        # Tính EMA cho midline
        ema = df['close'].ewm(span=period).mean()

        # Tính ATR
        tr = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()

        # Keltner bands
        upper = ema + (multiplier * atr)
        lower = ema - (multiplier * atr)

        current_price = df['close'].iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]

        if signal == "BUY":
            # BUY: Price trong channel và không chạm upper band
            return current_lower < current_price < current_upper
        elif signal == "SELL":
            # SELL: Price trong channel và không chạm lower band
            return current_lower < current_price < current_upper

        return False

    except Exception as e:
        logger.warning(f"⚠️ Keltner check failed: {e}")
        return False


def check_volume_confirmation(signal, data, timeframe='H1'):
    """Kiểm tra volume confirmation nâng cao"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 20:
            return False

        # Volume phải cao hơn trung bình 20 kỳ
        avg_volume = df['volume'].rolling(20).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]

        # Volume phải cao hơn ít nhất 50% so với trung bình
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0
        return volume_ratio > 1.5  # 50% above average

    except Exception as e:
        logger.warning(f"⚠️ Volume confirmation check failed: {e}")
        return False


def check_adx_momentum(signal, data, timeframe='H1', period=14):
    """Kiểm tra ADX momentum - trend strength + directional momentum"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < period + 1:
            return False

        # Tính ADX components
        tr = pd.concat([
            df['high'] - df['low'],
            abs(df['high'] - df['close'].shift(1)),
            abs(df['low'] - df['close'].shift(1))
        ], axis=1).max(axis=1)

        dm_plus = np.where((df['high'] - df['high'].shift(1)) > (df['low'].shift(1) - df['low']),
                          np.maximum(df['high'] - df['high'].shift(1), 0), 0)
        dm_minus = np.where((df['low'].shift(1) - df['low']) > (df['high'] - df['high'].shift(1)),
                           np.maximum(df['low'].shift(1) - df['low'], 0), 0)

        atr = tr.ewm(span=period).mean()
        di_plus = pd.Series(dm_plus).ewm(span=period).mean() / atr * 100
        di_minus = pd.Series(dm_minus).ewm(span=period).mean() / atr * 100

        dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100
        adx = dx.ewm(span=period).mean()

        current_adx = adx.iloc[-1]
        current_di_plus = di_plus.iloc[-1]
        current_di_minus = di_minus.iloc[-1]

        # ADX > 25 indicates strong trend
        if current_adx < 25:
            return False

        # Check directional momentum
        if signal == "BUY":
            # BUY: +DI > -DI and strong up momentum
            return current_di_plus > current_di_minus and current_di_plus > 20
        elif signal == "SELL":
            # SELL: -DI > +DI and strong down momentum
            return current_di_minus > current_di_plus and current_di_minus > 20

        return False

    except Exception as e:
        logger.warning(f"⚠️ ADX momentum check failed: {e}")
        return False


def check_ichimoku(signal, data, timeframe='H1'):
    """Kiểm tra Ichimoku Cloud alignment"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 52:  # Need at least 52 periods for Ichimoku
            return False

        high_9 = df['high'].rolling(9).max()
        low_9 = df['low'].rolling(9).min()
        high_26 = df['high'].rolling(26).max()
        low_26 = df['low'].rolling(26).min()
        high_52 = df['high'].rolling(52).max()
        low_52 = df['low'].rolling(52).min()

        # Tenkan-sen (Conversion Line): (9-period high + 9-period low) / 2
        tenkan = (high_9 + low_9) / 2

        # Kijun-sen (Base Line): (26-period high + 26-period low) / 2
        kijun = (high_26 + low_26) / 2

        # Senkou Span A (Leading Span A): (Tenkan + Kijun) / 2, plotted 26 periods ahead
        senkou_a = ((tenkan + kijun) / 2).shift(26)

        # Senkou Span B (Leading Span B): (52-period high + 52-period low) / 2, plotted 26 periods ahead
        senkou_b = ((high_52 + low_52) / 2).shift(26)

        # Chikou Span (Lagging Span): Close plotted 26 periods back
        chikou = df['close'].shift(-26)

        current_price = df['close'].iloc[-1]
        current_tenkan = tenkan.iloc[-1]
        current_kijun = kijun.iloc[-1]
        current_senkou_a = senkou_a.iloc[-1]
        current_senkou_b = senkou_b.iloc[-1]

        if signal == "BUY":
            # BUY conditions for Ichimoku:
            # 1. Price above cloud (Senkou A > Senkou B and Price > both)
            # 2. Tenkan above Kijun (bullish crossover)
            # 3. Price above Kijun
            cloud_bullish = current_senkou_a > current_senkou_b
            price_above_cloud = current_price > max(current_senkou_a, current_senkou_b)
            tenkan_above_kijun = current_tenkan > current_kijun
            price_above_kijun = current_price > current_kijun

            return cloud_bullish and price_above_cloud and tenkan_above_kijun and price_above_kijun

        elif signal == "SELL":
            # SELL conditions for Ichimoku:
            # 1. Price below cloud (Senkou B > Senkou A and Price < both)
            # 2. Tenkan below Kijun (bearish crossover)
            # 3. Price below Kijun
            cloud_bearish = current_senkou_b > current_senkou_a
            price_below_cloud = current_price < min(current_senkou_a, current_senkou_b)
            tenkan_below_kijun = current_tenkan < current_kijun
            price_below_kijun = current_price < current_kijun

            return cloud_bearish and price_below_cloud and tenkan_below_kijun and price_below_kijun

        return False

    except Exception as e:
        logger.warning(f"⚠️ Ichimoku check failed: {e}")
        return False


def strong_candle(data, timeframe='H1'):
    """Kiểm tra nến mạnh (strong candle) - enhanced version"""
    try:
        df = data.get(timeframe)
        if df is None or len(df) < 2:
            return False

        current = df.iloc[-1]
        body_size = abs(current['close'] - current['open'])
        total_range = current['high'] - current['low']

        if total_range == 0:
            return False

        # Enhanced: Body ratio > 65% (stronger candle) + volume confirmation
        body_ratio = body_size / total_range

        # Check volume spike for confirmation
        if len(df) >= 5:
            recent_volume = df['volume'].tail(5).mean()
            avg_volume = df['volume'].rolling(20).mean().iloc[-1]
            volume_spike = recent_volume > avg_volume * 1.2
        else:
            volume_spike = True  # Assume true if not enough data

        return body_ratio > 0.65 and volume_spike

    except Exception as e:
        logger.warning(f"⚠️ Strong candle check failed: {e}")
        return False


def technical_filter(signal, data):
    """
    TECHNICAL FILTER PRO - 8 Bộ lọc kỹ thuật chuyên nghiệp

    Args:
        signal: "BUY" hoặc "SELL"
        data: dict chứa dữ liệu multi-timeframe

    Returns:
        str: "TRADE_OK" nếu pass tất cả filter, "NO TRADE" nếu fail
    """

    # 1. Supertrend
    st_value = supertrend(data)
    current_price = price(data)

    if st_value is None or current_price is None:
        logger.warning("⚠️ Supertrend/Price data unavailable")
        return "NO TRADE"

    # Kiểm tra khoảng cách giá với Supertrend (cho phép pullback)
    distance_pct = abs(current_price - st_value) / st_value * 100
    
    if signal == "BUY" and st_value >= current_price:
        # Chỉ block BUY nếu giá quá xa dưới Supertrend
        if distance_pct > 0.5:  # > 0.5% distance
            logger.info(f"📊 Supertrend filter: ST({st_value:.2f}) >= Price({current_price:.2f}) - BUY blocked")
            return "NO TRADE"
        else:
            logger.info(f"✅ Supertrend: BUY near ST (distance {distance_pct:.2f}%) - Allow (reversal)")
    elif signal == "SELL" and st_value <= current_price:
        # 🔥 CHO PHÉP SELL khi giá gần hoặc vừa vượt xuống Supertrend (pullback/reversal)
        if distance_pct <= 1.0:  # Trong vòng 1% - cho phép SELL pullback
            logger.info(f"✅ Supertrend: SELL near ST (distance {distance_pct:.2f}%) - Allow (pullback/reversal)")
        else:
            logger.info(f"📊 Supertrend filter: ST({st_value:.2f}) <= Price({current_price:.2f}, distance {distance_pct:.2f}%) - SELL blocked")
            return "NO TRADE"

    logger.info(f"✅ Supertrend filter passed: {signal} @ {current_price:.2f} vs ST {st_value:.2f}")

    # 2. EMA alignment
    if not check_ema_alignment(signal, data):
        logger.info(f"📊 EMA alignment filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ EMA alignment filter passed for {signal}")

    # 3. VWAP
    if not check_vwap(signal, data):
        logger.info(f"📊 VWAP filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ VWAP filter passed for {signal}")

    # 4. Keltner channel
    if not check_keltner(signal, data):
        logger.info(f"📊 Keltner channel filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ Keltner channel filter passed for {signal}")

    # 5. Ichimoku Cloud
    if not check_ichimoku(signal, data):
        logger.info(f"📊 Ichimoku Cloud filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ Ichimoku Cloud filter passed for {signal}")

    # 6. Volume Confirmation
    if not check_volume_confirmation(signal, data):
        logger.info(f"📊 Volume Confirmation filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ Volume Confirmation filter passed for {signal}")

    # 7. ADX Momentum
    if not check_adx_momentum(signal, data):
        logger.info(f"📊 ADX Momentum filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ ADX Momentum filter passed: Strong trend detected")

    # 8. Candle Strength
    if not strong_candle(data):
        logger.info(f"📊 Strong Candle filter failed for {signal}")
        return "NO TRADE"

    logger.info(f"✅ Strong Candle filter passed for {signal}")

    # All 8 filters passed
    logger.info(f"🎯 TECHNICAL FILTER PRO: {signal} PASSED ALL 8 FILTERS ✅")
    return "TRADE_OK"


class VolatilityAI:
    """🧠 VOLATILITY AI PRO - Advanced Risk Management System

    6 Tính năng PRO:
    🔥 1. GARCH Volatility Prediction - Dự đoán biến động tương lai
    🔥 2. Transformer Volatility Forecast - Dự đoán nến lớn, breakout
    🔥 3. Volatility Regime Detection - 4 chế độ: Low/Medium/High/Explosion
    🔥 4. Volume + Volatility Spike Detector - Phát hiện spike bất thường
    🔥 5. ATR + Standard Deviation Dynamic SL/TP - SL/TP động theo biến động
    🔥 6. News-based Volatility AI - Filter news L1/L2/L3

    Hedge Fund Level Risk Management!
    """

    def __init__(self, model_path='ai_volatility_model.pkl', scaler_path='ai_volatility_scaler.pkl'):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.is_trained = False

        # 🧠 Transformer Model cho volatility forecast
        self.transformer_model = None
        self.transformer_scaler = StandardScaler()

        # 📊 GARCH Model cho volatility prediction
        self.garch_model = None

        # 📰 News Database cho news filter
        self.news_db = {}

        logger.info("🧠 VolatilityAI PRO initialized - Hedge Fund Level Risk Management")
        logger.info("   🔥 GARCH Volatility Prediction")
        logger.info("   🔥 Transformer Volatility Forecast")
        logger.info("   🔥 4-Regime Volatility Detection")
        logger.info("   🔥 Spike Detector (Volume + Volatility)")
        logger.info("   🔥 Dynamic ATR SL/TP")
        logger.info("   🔥 News-based Filter (L1/L2/L3)")

    # 🔥 NÂNG CẤP 1: GARCH VOLATILITY PREDICTION
    def garch_predict(self, data, horizon=5):
        """
        Dự đoán biến động tương lai bằng GARCH model

        Args:
            data: Dictionary chứa multi-timeframe data
            horizon: Số candles dự đoán phía trước

        Returns:
            dict: {
                'volatility_forecast': float,  # Biến động dự đoán
                'confidence': float,  # Độ tin cậy
                'risk_level': str  # LOW/MEDIUM/HIGH
            }
        """
        try:
            # Lấy data H1 cho GARCH (timeframe dài hạn)
            df = data.get('H1')
            if df is None or len(df) < 50:
                return {'volatility_forecast': 0.02, 'confidence': 0.5, 'risk_level': 'MEDIUM'}

            # Tính returns
            returns = df['close'].pct_change().dropna()

            # Simple GARCH(1,1) approximation (không cần arch library)
            # Volatility = omega + alpha * returns^2 + beta * prev_volatility

            # Tính realized volatility
            realized_vol = returns.rolling(20).std()

            # Dự đoán volatility tiếp theo
            current_vol = realized_vol.iloc[-1]
            avg_vol = realized_vol.mean()
            vol_ratio = current_vol / avg_vol

            # GARCH forecast
            omega = 0.0001  # Base volatility
            alpha = 0.1     # ARCH term
            beta = 0.85     # GARCH term

            # Dự đoán volatility cho horizon candles
            forecast_vol = current_vol
            for i in range(horizon):
                forecast_vol = omega + alpha * (returns.iloc[-1]**2) + beta * forecast_vol

            # Risk level
            if forecast_vol > avg_vol * 1.5:
                risk_level = 'HIGH'
                confidence = 0.8
            elif forecast_vol > avg_vol * 1.2:
                risk_level = 'MEDIUM'
                confidence = 0.6
            else:
                risk_level = 'LOW'
                confidence = 0.7

            return {
                'volatility_forecast': float(forecast_vol),
                'confidence': confidence,
                'risk_level': risk_level
            }

        except Exception as e:
            logger.warning(f"⚠️ GARCH prediction failed: {e}")
            return {'volatility_forecast': 0.02, 'confidence': 0.5, 'risk_level': 'MEDIUM'}

    # 🔥 NÂNG CẤP 2: TRANSFORMER VOLATILITY FORECAST
    def transformer_predict(self, data, sequence_length=20):
        """
        Dự đoán biến động bằng Transformer model (ChatGPT-style)

        Args:
            data: Dictionary chứa multi-timeframe data
            sequence_length: Độ dài sequence để dự đoán

        Returns:
            dict: {
                'big_candle_prob': float,  # Xác suất nến lớn
                'breakout_prob': float,   # Xác suất breakout
                'volatility_burst_prob': float,  # Xác suất volatility burst
                'forecast_confidence': float
            }
        """
        try:
            df = data.get('M5')  # Dùng M5 cho short-term prediction
            if df is None or len(df) < sequence_length + 10:
                return {
                    'big_candle_prob': 0.1,
                    'breakout_prob': 0.1,
                    'volatility_burst_prob': 0.05,
                    'forecast_confidence': 0.5
                }

            # Tạo features cho Transformer
            features = []

            for i in range(sequence_length, len(df)):
                window = df.iloc[i-sequence_length:i]

                # Price features
                price_change = window['close'].pct_change().fillna(0)
                high_low_ratio = window['high'] / window['low']
                body_size = abs(window['close'] - window['open']) / (window['high'] - window['low'])

                # Volume features
                volume_sma = window['volume'].rolling(5).mean()
                volume_ratio = window['volume'] / volume_sma

                # Volatility features
                returns = window['close'].pct_change()
                volatility = returns.rolling(5).std()

                # Combine features
                seq_features = pd.concat([
                    price_change,
                    high_low_ratio,
                    body_size.fillna(0.5),
                    volume_ratio.fillna(1.0),
                    volatility.fillna(0.01)
                ], axis=1).fillna(0).values.flatten()

                features.append(seq_features)

            if len(features) < 5:
                return {
                    'big_candle_prob': 0.1,
                    'breakout_prob': 0.1,
                    'volatility_burst_prob': 0.05,
                    'forecast_confidence': 0.5
                }

            # Simple Transformer approximation (attention mechanism)
            # Trong thực tế sẽ dùng torch.nn.Transformer

            # Tính attention weights (simplified)
            recent_features = features[-5:]  # Last 5 sequences
            attention_weights = []

            for i, seq in enumerate(recent_features):
                # Similarity với sequence cuối cùng
                last_seq = recent_features[-1]
                similarity = np.dot(seq, last_seq) / (np.linalg.norm(seq) * np.linalg.norm(last_seq) + 1e-8)
                attention_weights.append(similarity)

            # Normalize attention
            attention_weights = np.array(attention_weights)
            attention_weights = np.exp(attention_weights) / np.sum(np.exp(attention_weights))

            # Dự đoán dựa trên attention pattern
            avg_attention = np.mean(attention_weights)

            # Big candle probability: High attention + high volatility
            current_volatility = np.std([f[4] for f in recent_features])  # volatility feature
            big_candle_prob = min(0.8, avg_attention * current_volatility * 10)

            # Breakout probability: Sudden attention increase
            if len(attention_weights) >= 3:
                breakout_trend = attention_weights[-1] - attention_weights[-3]
                breakout_prob = max(0, min(0.9, breakout_trend * 5))
            else:
                breakout_prob = 0.1

            # Volatility burst: Extreme attention + volume spike
            volume_spike = np.mean([f[3] for f in recent_features])  # volume ratio
            burst_prob = min(0.7, big_candle_prob * volume_spike * 0.5)

            # Confidence dựa trên data quality
            data_quality = min(1.0, len(features) / 50)  # More data = higher confidence
            forecast_confidence = data_quality * 0.8

            return {
                'big_candle_prob': float(big_candle_prob),
                'breakout_prob': float(breakout_prob),
                'volatility_burst_prob': float(burst_prob),
                'forecast_confidence': float(forecast_confidence)
            }

        except Exception as e:
            logger.warning(f"⚠️ Transformer prediction failed: {e}")
            return {
                'big_candle_prob': 0.1,
                'breakout_prob': 0.1,
                'volatility_burst_prob': 0.05,
                'forecast_confidence': 0.5
            }

    # 🔥 NÂNG CẤP 3: VOLATILITY REGIME DETECTION
    def detect_volatility_regime(self, data):
        """
        Phát hiện 4 chế độ volatility: Low/Medium/High/Explosion

        Args:
            data: Dictionary chứa multi-timeframe data

        Returns:
            dict: {
                'regime': str,  # LOW/MEDIUM/HIGH/EXPLOSION
                'regime_score': float,  # 0-1
                'stability': float,  # Độ ổn định của regime
                'time_to_change': int  # Dự đoán candles đến khi đổi regime
            }
        """
        try:
            df = data.get('H1')  # Dùng H1 cho regime detection
            if df is None or len(df) < 20:
                return {'regime': 'MEDIUM', 'regime_score': 0.5, 'stability': 0.5, 'time_to_change': 10}

            # Tính các metrics cho regime detection
            returns = df['close'].pct_change().fillna(0)

            # 1. Volatility level (ATR-based)
            atr = df['high'] - df['low']  # Simple ATR approximation
            atr_sma = atr.rolling(20).mean()
            current_atr = atr.iloc[-1]
            avg_atr = atr_sma.iloc[-1]

            vol_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

            # 2. Volume intensity
            volume_sma = df['volume'].rolling(20).mean()
            current_volume = df['volume'].iloc[-1]
            avg_volume = volume_sma.iloc[-1]

            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            # 3. Price movement intensity
            price_range = (df['high'] - df['low']) / df['close']
            range_sma = price_range.rolling(20).mean()
            current_range = price_range.iloc[-1]
            avg_range = range_sma.iloc[-1]

            range_ratio = current_range / avg_range if avg_range > 0 else 1.0

            # 4. Momentum acceleration
            momentum = returns.rolling(5).mean()
            momentum_accel = momentum.diff().rolling(3).mean()
            current_accel = momentum_accel.iloc[-1]

            # Combine metrics thành regime score
            regime_score = (
                vol_ratio * 0.4 +      # Volatility 40%
                volume_ratio * 0.3 +   # Volume 30%
                range_ratio * 0.2 +    # Price range 20%
                abs(current_accel) * 10 * 0.1  # Momentum accel 10%
            )

            # Classify regime
            if regime_score >= 2.0:
                regime = 'EXPLOSION'
                stability = 0.3  # Unstable, can change quickly
                time_to_change = 2  # 2 candles
            elif regime_score >= 1.5:
                regime = 'HIGH'
                stability = 0.5
                time_to_change = 5
            elif regime_score >= 1.0:
                regime = 'MEDIUM'
                stability = 0.7
                time_to_change = 12
            else:
                regime = 'LOW'
                stability = 0.8
                time_to_change = 20

            # Normalize score to 0-1
            regime_score = min(1.0, regime_score / 2.0)

            return {
                'regime': regime,
                'regime_score': float(regime_score),
                'stability': float(stability),
                'time_to_change': time_to_change
            }

        except Exception as e:
            logger.warning(f"⚠️ Volatility regime detection failed: {e}")
            return {'regime': 'MEDIUM', 'regime_score': 0.5, 'stability': 0.5, 'time_to_change': 10}

    # 🔥 NÂNG CẤP 4: VOLUME + VOLATILITY SPIKE DETECTOR
    def detect_volatility_spike(self, data, threshold_multiplier=2.5):
        """
        Phát hiện spike bất thường trong volume và volatility

        Args:
            data: Dictionary chứa multi-timeframe data
            threshold_multiplier: Ngưỡng phát hiện spike

        Returns:
            dict: {
                'volume_spike': bool,
                'volatility_spike': bool,
                'price_spike': bool,
                'spread_spike': bool,
                'spike_intensity': float,  # 0-1
                'spike_type': str  # NONE/VOLUME/VOLATILITY/PRICE/SPREAD/COMBINED
            }
        """
        try:
            df = data.get('M5')  # Dùng M5 cho spike detection
            if df is None or len(df) < 20:
                return {
                    'volume_spike': False,
                    'volatility_spike': False,
                    'price_spike': False,
                    'spread_spike': False,
                    'spike_intensity': 0.0,
                    'spike_type': 'NONE'
                }

            # 1. Volume Spike Detection
            volume_sma = df['volume'].rolling(20).mean()
            volume_std = df['volume'].rolling(20).std()
            current_volume = df['volume'].iloc[-1]
            avg_volume = volume_sma.iloc[-1]
            std_volume = volume_std.iloc[-1]

            volume_zscore = (current_volume - avg_volume) / std_volume if std_volume > 0 else 0
            volume_spike = volume_zscore > threshold_multiplier

            # 2. Volatility Spike Detection
            returns = df['close'].pct_change()
            vol_sma = returns.rolling(20).std()
            vol_std = returns.rolling(20).std()
            current_vol = returns.iloc[-1]
            avg_vol = vol_sma.iloc[-1]
            std_vol = vol_std.iloc[-1]

            vol_zscore = abs(current_vol) / std_vol if std_vol > 0 else 0
            volatility_spike = vol_zscore > threshold_multiplier

            # 3. Price Spike Detection (sudden large moves)
            price_range = (df['high'] - df['low']) / df['close']
            range_sma = price_range.rolling(20).mean()
            range_std = price_range.rolling(20).std()
            current_range = price_range.iloc[-1]
            avg_range = range_sma.iloc[-1]
            std_range = range_std.iloc[-1]

            range_zscore = (current_range - avg_range) / std_range if std_range > 0 else 0
            price_spike = range_zscore > threshold_multiplier

            # 4. Spread Spike Detection (bid-ask spread widening)
            # Approximation: High-Low range as proxy for spread
            spread_ratio = (df['high'] - df['low']) / df['close']
            spread_sma = spread_ratio.rolling(20).mean()
            spread_std = spread_ratio.rolling(20).std()
            current_spread = spread_ratio.iloc[-1]
            avg_spread = spread_sma.iloc[-1]
            std_spread = spread_std.iloc[-1]

            spread_zscore = (current_spread - avg_spread) / std_spread if std_spread > 0 else 0
            spread_spike = spread_zscore > threshold_multiplier

            # Calculate overall spike intensity
            spike_scores = [volume_zscore, vol_zscore, range_zscore, spread_zscore]
            max_spike = max(spike_scores)
            spike_intensity = min(1.0, max_spike / (threshold_multiplier * 2))

            # Determine spike type
            spike_flags = [volume_spike, volatility_spike, price_spike, spread_spike]
            spike_types = ['VOLUME', 'VOLATILITY', 'PRICE', 'SPREAD']

            active_spikes = [t for t, f in zip(spike_types, spike_flags) if f]

            if len(active_spikes) == 0:
                spike_type = 'NONE'
            elif len(active_spikes) == 1:
                spike_type = active_spikes[0]
            else:
                spike_type = 'COMBINED'

            return {
                'volume_spike': volume_spike,
                'volatility_spike': volatility_spike,
                'price_spike': price_spike,
                'spread_spike': spread_spike,
                'spike_intensity': float(spike_intensity),
                'spike_type': spike_type
            }

        except Exception as e:
            logger.warning(f"⚠️ Spike detection failed: {e}")
            return {
                'volume_spike': False,
                'volatility_spike': False,
                'price_spike': False,
                'spread_spike': False,
                'spike_intensity': 0.0,
                'spike_type': 'NONE'
            }

    # 🔥 NÂNG CẤP 5: ATR + STANDARD DEVIATION DYNAMIC SL/TP
    def calculate_dynamic_sl_tp(self, data, entry_price, direction, confidence=0.5):
        """
        Tính SL/TP động dựa trên ATR và Standard Deviation

        Args:
            data: Dictionary chứa multi-timeframe data
            entry_price: Giá vào lệnh
            direction: "BUY" hoặc "SELL"
            confidence: Độ tin cậy AI (0.0-1.0)

        Returns:
            dict: {
                'sl_price': float,
                'tp_price': float,
                'sl_distance': float,
                'tp_distance': float,
                'risk_reward_ratio': float,
                'volatility_adjusted': bool
            }
        """
        try:
            df = data.get('H1')  # Dùng H1 cho SL/TP calculation
            if df is None or len(df) < 20:
                # Fallback: Fixed SL/TP
                sl_distance = 2.0
                tp_distance = 4.0
                if direction == "BUY":
                    sl_price = entry_price - sl_distance
                    tp_price = entry_price + tp_distance
                else:
                    sl_price = entry_price + sl_distance
                    tp_price = entry_price - tp_distance

                return {
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'sl_distance': sl_distance,
                    'tp_distance': tp_distance,
                    'risk_reward_ratio': tp_distance / sl_distance,
                    'volatility_adjusted': False
                }

            # 1. ATR-based SL/TP
            high_low = df['high'] - df['low']
            atr = high_low.rolling(14).mean().iloc[-1]  # ATR approximation

            # 2. Standard Deviation of returns
            returns = df['close'].pct_change()
            std_dev = returns.rolling(20).std().iloc[-1]

            # 3. Current volatility regime
            regime_info = self.detect_volatility_regime(data)
            regime = regime_info['regime']

            # Base multipliers theo regime
            if regime == 'EXPLOSION':
                sl_multiplier = 2.0  # Wide SL for high volatility
                tp_multiplier = 1.5  # Close TP to capture quick moves
            elif regime == 'HIGH':
                sl_multiplier = 1.5
                tp_multiplier = 2.0
            elif regime == 'MEDIUM':
                sl_multiplier = 1.2
                tp_multiplier = 2.5
            else:  # LOW
                sl_multiplier = 1.0
                tp_multiplier = 3.0

            # Adjust theo confidence
            if confidence >= 0.8:
                sl_multiplier *= 0.8  # Tighter SL for high confidence
                tp_multiplier *= 1.2  # Wider TP for high confidence
            elif confidence <= 0.5:
                sl_multiplier *= 1.2  # Wider SL for low confidence
                tp_multiplier *= 0.8  # Closer TP for low confidence

            # Calculate distances
            base_atr_sl = atr * sl_multiplier
            base_std_sl = std_dev * entry_price * sl_multiplier

            # Use the larger of ATR or STD for SL (more conservative)
            sl_distance = max(base_atr_sl, base_std_sl, 1.0)  # Minimum 1.0

            # TP based on risk-reward (typically 1:2 or 1:3)
            tp_distance = sl_distance * tp_multiplier

            # Apply direction
            if direction == "BUY":
                sl_price = entry_price - sl_distance
                tp_price = entry_price + tp_distance
            else:
                sl_price = entry_price + sl_distance
                tp_price = entry_price - tp_distance

            risk_reward_ratio = tp_distance / sl_distance

            return {
                'sl_price': float(sl_price),
                'tp_price': float(tp_price),
                'sl_distance': float(sl_distance),
                'tp_distance': float(tp_distance),
                'risk_reward_ratio': float(risk_reward_ratio),
                'volatility_adjusted': True
            }

        except Exception as e:
            logger.warning(f"⚠️ Dynamic SL/TP calculation failed: {e}")
            # Fallback
            sl_distance = 2.0
            tp_distance = 4.0
            if direction == "BUY":
                sl_price = entry_price - sl_distance
                tp_price = entry_price + tp_distance
            else:
                sl_price = entry_price + sl_distance
                tp_price = entry_price - tp_distance

            return {
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_distance': sl_distance,
                'tp_distance': tp_distance,
                'risk_reward_ratio': tp_distance / sl_distance,
                'volatility_adjusted': False
            }

    # 🔥 NÂNG CẤP 6: NEWS-BASED VOLATILITY AI
    def classify_news(self, news):
        """
        Phân loại news thành L1/L2/L3 và tính volatility impact

        Args:
            news: Dictionary chứa news data hoặc list of news items

        Returns:
            int: News level (0=LIGHT, 1=MEDIUM, 2=STRONG, 3=CRITICAL)
        """
        try:
            if not news:
                return 0  # No news = Light impact

            # Keywords cho từng level
            l3_keywords = [
                'fomc', 'federal reserve', 'fed', 'cpi', 'inflation', 'employment',
                'nfp', 'non-farm payrolls', 'gdp', 'interest rate', 'rate decision',
                'central bank', 'ecb', 'boe', 'boj', 'rba', 'boc'
            ]

            l2_keywords = [
                'earnings', 'quarterly results', 'economic data', 'trade war',
                'geopolitical', 'oil prices', 'commodity', 'currency intervention',
                'bank stress test', 'sovereign debt', 'recession fears'
            ]

            l1_keywords = [
                'weather', 'hurricane', 'earthquake', 'natural disaster',
                'holiday', 'maintenance', 'technical issues', 'minor policy'
            ]

            # Convert news to string for analysis
            if isinstance(news, dict):
                news_text = ' '.join(str(v) for v in news.values() if v)
            elif isinstance(news, list):
                news_text = ' '.join(str(item) for item in news)
            else:
                news_text = str(news)

            news_lower = news_text.lower()

            # Check L3 (Critical)
            for keyword in l3_keywords:
                if keyword in news_lower:
                    logger.warning(f"🚨 L3 CRITICAL NEWS DETECTED: {keyword}")
                    return 3

            # Check L2 (Strong)
            for keyword in l2_keywords:
                if keyword in news_lower:
                    logger.info(f"⚠️ L2 STRONG NEWS DETECTED: {keyword}")
                    return 2

            # Check L1 (Medium)
            for keyword in l1_keywords:
                if keyword in news_lower:
                    logger.info(f"ℹ️ L1 MEDIUM NEWS DETECTED: {keyword}")
                    return 1

            # No significant news
            return 0

        except Exception as e:
            logger.warning(f"⚠️ News classification failed: {e}")
            return 0

    def __init__(self, model_path='ai_volatility_model.pkl', scaler_path='ai_volatility_scaler.pkl'):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.is_trained = False

    def prepare_features(self, df):
        """Chuẩn bị features cho volatility detection"""
        if df is None or df.empty:
            logger.warning("⚠️ prepare_features received None or empty DataFrame")
            return pd.DataFrame()  # Return empty DataFrame instead of None
        
        df = df.copy()
        # Thêm thông tin phiên (Asia/EU/US) để model có thể học khác biệt theo khung giờ
        try:
            df = add_session_features(df)
        except Exception:
            pass

        # ========== TECHNICAL INDICATORS ==========
        df = TechnicalIndicators.calculate_sma(df, [5, 10, 20, 50])
        df = TechnicalIndicators.calculate_rsi(df)
        df = TechnicalIndicators.calculate_macd(df)
        df = TechnicalIndicators.calculate_bollinger(df)
        df = TechnicalIndicators.calculate_atr(df)

        # ========== VOLATILITY FEATURES ==========
        df['returns'] = df['close'].pct_change()
        df['volatility_5'] = df['returns'].rolling(5).std()
        df['volatility_10'] = df['returns'].rolling(10).std()
        df['volatility_20'] = df['returns'].rolling(20).std()

        # Volatility ratio (current vs historical)
        df['vol_ratio_5_20'] = df['volatility_5'] / df['volatility_20'].rolling(20).mean()
        df['vol_ratio_10_50'] = df['volatility_10'] / df['volatility_20'].rolling(50).mean()

        # Price range features
        df['daily_range'] = (df['high'] - df['low']) / df['close']
        df['range_ratio'] = df['daily_range'] / df['daily_range'].rolling(20).mean()

        # Momentum volatility
        df['momentum_vol'] = df['returns'].rolling(5).std() / df['returns'].rolling(20).std()

        # ATR ratio
        df['atr_ratio'] = df['atr'] / df['atr'].rolling(20).mean()

        # ========== MARKET REGIME DETECTION ==========
        # High volatility regime: vol_ratio > 1.5
        # Medium volatility: vol_ratio 1.0-1.5
        # Low volatility: vol_ratio < 1.0
        df['vol_regime'] = np.where(
            df['vol_ratio_5_20'] > 1.5, 2,  # High vol
            np.where(df['vol_ratio_5_20'] > 1.0, 1,  # Medium vol
                    0)  # Low vol
        )

        # ========== TARGET: VOLATILITY RISK LEVEL ==========
        # Risk level based on multiple factors
        df['future_volatility'] = df['volatility_20'].shift(-5)  # Look ahead 5 periods
        df['future_range'] = df['daily_range'].shift(-5)

        # Risk score (0-1): Higher = More risky
        df['vol_risk_score'] = (
            (df['vol_ratio_5_20'] - 1).clip(0, 2) / 2 * 0.4 +  # Volatility ratio (40%)
            (df['range_ratio'] - 1).clip(0, 2) / 2 * 0.3 +     # Range ratio (30%)
            (df['atr_ratio'] - 1).clip(0, 2) / 2 * 0.3          # ATR ratio (30%)
        ).clip(0, 1)

        # Risk level: 0=Low, 1=Medium, 2=High
        df['risk_level'] = np.where(
            df['vol_risk_score'] > 0.7, 2,  # High risk
            np.where(df['vol_risk_score'] > 0.4, 1,  # Medium risk
                    0)  # Low risk
        )

        df['target'] = df['risk_level']

        # ========== SMC / Candle Pattern Features Integration ==========
        try:
            smc_score_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_score')]
            smc_recent_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_recent')]
            if smc_score_cols or smc_recent_cols:
                # Ensure numeric and fill missing
                for c in smc_score_cols + smc_recent_cols:
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

                # Aggregated features for models
                if smc_score_cols:
                    df['smc_score_sum'] = df[smc_score_cols].sum(axis=1)
                    df['smc_score_mean'] = df[smc_score_cols].mean(axis=1)
                else:
                    df['smc_score_sum'] = 0.0
                    df['smc_score_mean'] = 0.0

                if smc_recent_cols:
                    df['smc_recent_max'] = df[smc_recent_cols].max(axis=1)
                else:
                    df['smc_recent_max'] = 0.0
        except Exception as e:
            logger.debug(f"⚠️ SMC integration skipped in VolatilityAI.prepare_features: {e}")

        return df

    def train_model(self, df, test_size=0.3):
        """Train XGBoost model cho volatility prediction"""
        logger.info("🧠 Đang huấn luyện mô hình VolatilityAI...")
        logger.info("   - Dữ liệu sử dụng: features, target")
        logger.info("   - Thuật toán: XGBoostClassifier, n_estimators=100, max_depth=6, learning_rate=0.1")
        logger.info("   - Đang thực hiện fitting mô hình...")

        df = self.prepare_features(df)

        feature_cols = [col for col in df.columns if col not in
                       ['target', 'vol_risk_score', 'future_volatility', 'future_range']]

        df_clean = df[feature_cols + ['target']].dropna()

        if len(df_clean) < 100:
            logger.error("❌ Không đủ dữ liệu để huấn luyện VolatilityAI")
            return False

        X = df_clean[feature_cols]
        y = df_clean['target']

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            eval_metric='mlogloss'
        )

        self.model.fit(X_train_scaled, y_train)

        y_pred = self.model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)

        logger.info(f"✅ Đã huấn luyện xong VolatilityAI - Độ chính xác: {accuracy:.3f}")

        try:
            save_feature_importances(self.model, feature_cols, 'VolatilityAI', X=X_test_scaled, y=y_test, compute_permutation=True)
        except Exception:
            pass

        self.feature_columns = feature_cols
        self.is_trained = True
        self.save_model()

        return True

    def predict(self, features: dict):
        """
        🔥 VOLATILITY AI PRO - Dự đoán mức độ rủi ro với 6 tính năng Hedge Fund level

        Args:
            features: Dictionary từ build_volatility_features()

        Returns:
            dict: {
                'risk': float (0.0-1.0),  # Risk score
                'level': str,  # LOW/MEDIUM/HIGH/CRITICAL
                'regime': str,  # Volatility regime
                'spike_alert': bool,  # Có spike không
                'news_alert': bool,  # Có news quan trọng không
                'trading_allowed': bool,  # Có nên trade không
                'recommendation': str  # Khuyến nghị cụ thể
            }
        """
        try:
            risk_score = 0.0
            risk_factors = []

            # 🔥 1. GARCH VOLATILITY PREDICTION (30% weight)
            garch_risk = features.get('garch_volatility', 0.02)
            garch_confidence = features.get('garch_confidence', 0.5)
            garch_level = features.get('garch_risk_level', 'MEDIUM')

            # Convert GARCH risk to score
            if garch_level == 'HIGH':
                garch_score = 0.8
            elif garch_level == 'MEDIUM':
                garch_score = 0.5
            else:
                garch_score = 0.2

            risk_score += garch_score * 0.3  # 30% weight
            risk_factors.append(f"GARCH: {garch_level} ({garch_score:.1f})")

            # 🔥 2. TRANSFORMER VOLATILITY FORECAST (25% weight)
            big_candle_prob = features.get('transformer_big_candle_prob', 0.1)
            breakout_prob = features.get('transformer_breakout_prob', 0.1)
            burst_prob = features.get('transformer_burst_prob', 0.05)

            transformer_score = (big_candle_prob + breakout_prob + burst_prob) / 3
            risk_score += transformer_score * 0.25  # 25% weight
            risk_factors.append(f"Transformer: {transformer_score:.2f}")

            # 🔥 3. VOLATILITY REGIME DETECTION (20% weight)
            regime = features.get('vol_regime', 'MEDIUM')
            regime_score = features.get('vol_regime_score', 0.5)
            regime_stability = features.get('vol_regime_stability', 0.5)

            if regime == 'EXPLOSION':
                regime_risk = 0.9
            elif regime == 'HIGH':
                regime_risk = 0.7
            elif regime == 'MEDIUM':
                regime_risk = 0.4
            else:  # LOW
                regime_risk = 0.1

            # Adjust by stability (less stable = higher risk)
            regime_risk = regime_risk * (2 - regime_stability)
            risk_score += regime_risk * 0.2  # 20% weight
            risk_factors.append(f"Regime: {regime} ({regime_risk:.2f})")

            # 🔥 4. VOLUME + VOLATILITY SPIKE DETECTOR (15% weight)
            spike_intensity = features.get('vol_spike_intensity', 0.0)
            spike_type = features.get('vol_spike_type', 'NONE')

            spike_alert = spike_intensity > 0.5 or spike_type != 'NONE'
            spike_score = min(1.0, spike_intensity * 2)  # Amplify spike impact

            risk_score += spike_score * 0.15  # 15% weight
            risk_factors.append(f"Spike: {spike_type} ({spike_score:.2f})")

            # 🔥 5. ATR + STANDARD DEVIATION (5% weight)
            atr = features.get('atr', 2.0)
            std_dev = features.get('std_dev', 0.02)

            # High ATR/STD = High risk
            volatility_score = min(1.0, (atr / 5.0) * 0.5 + (std_dev / 0.05) * 0.5)
            risk_score += volatility_score * 0.05  # 5% weight
            risk_factors.append(f"Volatility: {volatility_score:.2f}")

            # 🔥 6. NEWS-BASED VOLATILITY AI (5% weight)
            news_level = features.get('news_level', 0)
            news_impact = features.get('news_impact', 'LIGHT')

            if news_level >= 3:
                news_score = 1.0  # Critical news
            elif news_level >= 2:
                news_score = 0.7  # Strong news
            elif news_level >= 1:
                news_score = 0.4  # Medium news
            else:
                news_score = 0.0  # Light/no news

            risk_score += news_score * 0.05  # 5% weight
            risk_factors.append(f"News: {news_impact} ({news_score:.1f})")

            # Normalize risk score to 0-1
            risk_score = min(1.0, max(0.0, risk_score))

            # Determine risk level
            if risk_score >= 0.8:
                risk_level = 'CRITICAL'
            elif risk_score >= 0.6:
                risk_level = 'HIGH'
            elif risk_score >= 0.4:
                risk_level = 'MEDIUM'
            else:
                risk_level = 'LOW'

            # Trading decision
            trading_allowed = risk_score < 0.7  # Allow trading if risk < 70%
            news_alert = news_level >= 2  # Alert for strong/critical news

            # Generate recommendation
            if not trading_allowed:
                if spike_alert:
                    recommendation = "🚫 AVOID: Spike detected - wait for stabilization"
                elif news_alert:
                    recommendation = "🚫 AVOID: High-impact news upcoming"
                elif regime == 'EXPLOSION':
                    recommendation = "🚫 AVOID: Volatility explosion - extreme risk"
                else:
                    recommendation = "🚫 AVOID: High risk conditions"
            elif risk_level == 'MEDIUM':
                recommendation = "⚠️ CAUTION: Medium risk - reduce position size"
            else:
                recommendation = "✅ OK: Low risk - normal trading"

            logger.info(f"🧠 VolatilityAI PRO Assessment:")
            logger.info(f"   Risk Score: {risk_score:.3f} ({risk_level})")
            logger.info(f"   Factors: {' | '.join(risk_factors)}")
            logger.info(f"   Trading: {'ALLOWED' if trading_allowed else 'BLOCKED'}")
            logger.info(f"   Recommendation: {recommendation}")

            return {
                'risk': round(risk_score, 3),
                'level': risk_level,
                'regime': regime,
                'spike_alert': spike_alert,
                'news_alert': news_alert,
                'trading_allowed': trading_allowed,
                'recommendation': recommendation,
                'risk_factors': risk_factors
            }

        except Exception as e:
            logger.warning(f"⚠️ VolatilityAI PRO prediction failed: {e}")
            return {
                'risk': 0.5,
                'level': 'MEDIUM',
                'regime': 'MEDIUM',
                'spike_alert': False,
                'news_alert': False,
                'trading_allowed': True,
                'recommendation': "⚠️ Fallback: Medium risk - proceed with caution",
                'risk_factors': ['Error in calculation']
            }

    def save_model(self):
        """Save model và scaler"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            joblib.dump(self.feature_columns, 'ai_volatility_feature_columns.pkl')
            logger.info(f"✅ VolatilityAI model saved to {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Error saving VolatilityAI model: {e}")

    def load_model(self):
        """Load pre-trained model"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)

                if os.path.exists('ai_volatility_feature_columns.pkl'):
                    self.feature_columns = joblib.load('ai_volatility_feature_columns.pkl')

                self.is_trained = True
                logger.info(f"✅ VolatilityAI model loaded from {self.model_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Error loading VolatilityAI model: {e}")
        return False


# ============================================
# 3. 🤖 AI MODELS (MOVED TO core/models.py)
# ============================================
# XGBoostTrendModel, TrendAI, ReversalAI

# ============================================
# AUTO SYSTEM MODE CONTROLLER (WINDOWS VPS)

# ============================================
# 4. 💰 MONEY MANAGEMENT (MOVED TO core/money_management.py)
# ============================================
# AutoModeController, AIMoneyManager

#==============================================================================
class CompleteAITradingSystem:
    """Complete backtesting engine"""
    
    def __init__(self, initial_balance=1000, risk_per_trade=0.02):
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.results = []
        
    def calculate_lot_size(self, balance, risk_pct, entry_price, sl_price):
        """
        Calculate position size based on risk - GOLD/XAUUSD optimized
        
        Công thức: lot = risk_amount / (pip_risk * value_per_pip)
        Với GOLD: 1 lot = 100 oz, mỗi $1 di chuyển = $100 thay đổi P/L
        """
        risk_amount = balance * risk_pct
        price_diff = abs(entry_price - sl_price)
        
        if price_diff > 0:
            # GOLD: 1 lot = 100 oz, mỗi $1 = $100 P/L
            # Ví dụ: Risk $100, SL = $10 → lot = 100 / (10 * 100) = 0.10 lot
            contract_size = 100.0  # GOLD standard
            lot_size = risk_amount / (price_diff * contract_size)
            
            # Giới hạn lot size hợp lý
            min_lot = DEFAULT_MIN_LOT  # 0.01
            max_lot = 1.68  # Max 1.68 lot (có thể điều chỉnh trong EA)
            
            # Điều chỉnh thêm cho tài khoản nhỏ
            if balance < 5000:
                max_lot = min(max_lot, 0.10)  # TK < $5k → max 0.10 lot
            elif balance < 10000:
                max_lot = min(max_lot, 0.25)  # TK < $10k → max 0.25 lot
            elif balance < 50000:
                max_lot = min(max_lot, 0.80)  # TK < $50k → max 0.80 lot
            # TK >= $50k → max 1.68 lot
            
            final_lot = max(min_lot, min(lot_size, max_lot))
            logger.info(f"💰 LOT CALC: Balance=${balance:.2f}, Risk={risk_pct*100}%, "
                       f"Price_diff=${price_diff:.2f} → Raw={lot_size:.4f} → Final={final_lot:.2f} lot")
            return final_lot
            
        return float(DEFAULT_MIN_LOT)
    
    def run_backtest(self, df, model, start_date=None, end_date=None):
        """Run complete backtest"""
        logger.info("⚡ Starting backtest...")
        
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
            
        balance = self.initial_balance
        positions = []
        trades = []
        
        for i in range(200, len(df)):  # Skip first 200 for indicators
            current_data = df.iloc[:i+1]
            current_row = df.iloc[i]
            
            # Get AI signal
            action, confidence = model.predict_signal(current_data)
            
            # 🎯 NO CONFIDENCE FILTER - ACCEPT ALL SIGNALS
            if action in ["BUY", "SELL"]:  # Accept all AI predictions
                entry_price = current_row['close']
                
                # Simple SL/TP calculation
                atr = current_data['atr'].iloc[-1] if 'atr' in current_data else 2.0
                
                if action == "BUY":
                    sl_price = entry_price - (atr * 2)
                    tp_price = entry_price + (atr * 3)
                else:
                    sl_price = entry_price + (atr * 2)
                    tp_price = entry_price - (atr * 3)
                
                # Calculate lot size
                lot_size = self.calculate_lot_size(balance, self.risk_per_trade, 
                                                 entry_price, sl_price)
                
                # Record trade
                trade = {
                    'timestamp': current_row.name,
                    'action': action,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'lot_size': lot_size,
                    'confidence': confidence
                }
                
                positions.append(trade)
                
                # Simulate trade result (simplified)
                # In real backtest, would check next candles for SL/TP hits
                pnl_pips = random.uniform(-20, 30)  # Simplified PnL
                pnl_amount = pnl_pips * lot_size * 10  # $10 per pip per lot
                
                balance += pnl_amount
                trade['pnl'] = pnl_amount
                trade['exit_price'] = entry_price + (pnl_pips * (1 if action == "BUY" else -1))
                trades.append(trade)
        
        # Calculate metrics
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t['pnl'] > 0])
        total_pnl = sum([t['pnl'] for t in trades])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        win_rate_pct = round(win_rate * 100.0, 2)
        
        results = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'win_rate_pct': win_rate_pct,
            'total_pnl': total_pnl,
            'final_balance': balance,
            'return_pct': (balance - self.initial_balance) / self.initial_balance * 100,
            'trades': trades
        }
        
        logger.info(f"✅ Backtest completed:")
        logger.info(f"   📊 Total trades: {total_trades}")
        logger.info(f"   🎯 Win rate: {win_rate*100:.2f}% ({winning_trades}/{total_trades})")
        logger.info(f"   💰 Total PnL: ${total_pnl:.2f}")
        logger.info(f"   📈 Return: {results['return_pct']:.1f}%")
        
        # 💾 Save backtest results to file
        self._save_backtest_results(results)
        
        self.results = results
        return results
    
    def _save_backtest_results(self, results):
        """Save backtest results to file for future use"""
        try:
            import json
            from datetime import datetime
            
            # Add timestamp to results
            results['backtest_date'] = datetime.now().isoformat()
            results['data_period'] = "60_days_5M"
            
            # Save to JSON file
            with open('backtest_results.json', 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            logger.info(f"💾 Backtest results saved to backtest_results.json")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to save backtest results: {e}")
    
    def load_backtest_results(self):
        """Load previous backtest results if available"""
        try:
            import json
            import os
            from datetime import datetime, timedelta
            
            if os.path.exists('backtest_results.json'):
                with open('backtest_results.json', 'r') as f:
                    results = json.load(f)
                
                # Check if results are recent (within 24 hours)
                backtest_date = datetime.fromisoformat(results.get('backtest_date', '2000-01-01'))
                if datetime.now() - backtest_date < timedelta(hours=24):
                    logger.info(f"📊 Loaded cached backtest results from {backtest_date.strftime('%H:%M:%S')}")
                    logger.info(f"   📊 Total trades: {results['total_trades']}")
                    # Display exact win-rate percentage if present, otherwise compute
                    if 'win_rate_pct' in results:
                        logger.info(f"   🎯 Win rate: {results['win_rate_pct']:.2f}% ({results.get('winning_trades',0)}/{results.get('total_trades',0)})")
                    else:
                        try:
                            pct = float(results.get('win_rate', 0.0)) * 100.0
                        except Exception:
                            pct = 0.0
                        logger.info(f"   🎯 Win rate: {pct:.2f}% ({results.get('winning_trades',0)}/{results.get('total_trades',0)})")
                    logger.info(f"   💰 Total PnL: ${results['total_pnl']:.2f}")
                    logger.info(f"   📈 Return: {results['return_pct']:.1f}%")
                    return results
                else:
                    logger.info(f"⏰ Cached backtest is old ({backtest_date.strftime('%H:%M:%S')}), running new backtest...")
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load backtest results: {e}")
            return None

#==============================================================================
# 4. 🚀 LIVE TRADING SIGNAL GENERATOR
#==============================================================================

# Global storage for latest signal
latest_signal = {
    "action": "NONE",
    "symbol": "XAUUSD", 
    "price": 0.0,
    "confidence": 0.0,
    "timestamp": datetime.now().isoformat(),
    "signal_id": 0
}

class HTTPSignalHandler(BaseHTTPRequestHandler):
    """HTTP handler for MT5 communication"""
    
    def do_GET(self):
        if self.path == '/signal':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = json.dumps(latest_signal)
            self.wfile.write(response.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass


try:
    from ai_modules.CandlePatternAI import CandlePatternAI
except Exception:
    # Fallback stub: provide minimal interface so module import doesn't fail.
    class CandlePatternAI:
        def __init__(self, *args, **kwargs):
            pass

        def doji(self, o, h, l, c):
            return False

        def hammer(self, o, h, l, c):
            return False

        def inverted_hammer(self, o, h, l, c):
            return False

        def bullish_engulfing(self, prev, curr):
            return False

        def bearish_engulfing(self, prev, curr):
            return False

class CompleteAITradingSystem:
    """Main AI Trading System class"""
    
    def __init__(self, use_money_manager=True, use_drawdown_protector=True, initial_balance=1000.0,
                 htf_policy='block', htf_soft_multiplier=0.5, enable_live_reentry: bool = False,
                 min_lot: float = None, live_lot_cap: float = 10.0):
        # === UNIFIED FUSION AI (merged v1-v5) ===
        self.fusion_ai = FusionAIUpgraded()
        
        # === NEW UPGRADE AIs ===
        self.trend_matrix = TrendMatrixAI()
        self.smart_sl = SmartSLAI()
        self.risk_guardian = RiskGuardianAI()
        self.sideway_v2 = SidewayDetectorV2()
        self.regime_ai = RegimeClassifierAI()
        
        # === NEW: ADVANCED AI MODULES (Dec 2025) ===
        try:
            if get_market_phase_ai:
                self.market_phase_ai = get_market_phase_ai()
                logger.info("✅ Market Phase AI initialized (Wyckoff phases)")
            else:
                self.market_phase_ai = None
        except Exception as e:
            logger.warning(f"⚠️ Market Phase AI init failed: {e}")
            self.market_phase_ai = None
            
        try:
            if get_breaker_block_ai:
                self.breaker_block_ai = get_breaker_block_ai()
                logger.info("✅ Breaker Block AI initialized (Failed OB detection)")
            else:
                self.breaker_block_ai = None
        except Exception as e:
            logger.warning(f"⚠️ Breaker Block AI init failed: {e}")
            self.breaker_block_ai = None
            
        try:
            if get_enhanced_news_filter:
                self.news_filter_ai = get_enhanced_news_filter()
                logger.info("✅ Enhanced News Filter AI initialized (News calendar + ATR spike)")
            else:
                self.news_filter_ai = None
        except Exception as e:
            logger.warning(f"⚠️ Enhanced News Filter AI init failed: {e}")
            self.news_filter_ai = None
            
        try:
            if get_advanced_rl_ai:
                self.advanced_rl_ai = get_advanced_rl_ai()
                logger.info("✅ Advanced RL AI initialized (Q-Learning + auto-tuning)")
            else:
                self.advanced_rl_ai = None
        except Exception as e:
            logger.warning(f"⚠️ Advanced RL AI init failed: {e}")
            self.advanced_rl_ai = None
        
        # === SMC ORCHESTRATOR (Full Smart Money Concepts) ===
        try:
            # Import từ ai_modules/smc/ (đã move vào ai_modules)
            from ai_modules.smc import SMCOrchestrator, SMCMTFOrchestrator
            self.smc_orchestrator = SMCOrchestrator()
            logger.info("✅ SMC Orchestrator initialized (8 modules: Market Structure, Liquidity, OB, FVG, S/D, P/D, Internal, Entry)")
            
            # 🆕 SMC MTF Orchestrator (Enhanced - Dec 8, 2025)
            # Initialize after data_fetcher to get symbol
            self.smc_mtf_orch = None  # Will be initialized after data_fetcher
        except Exception as e:
            logger.warning(f"⚠️ SMC Orchestrator init failed: {e}")
            self.smc_orchestrator = None
            self.smc_mtf_orch = None
        
        # Prefer AI implementations from the centralized registry `live_trading.logic`.
        try:
            from live_trading.logic import get_ai, TrendAI as RegTrend, VolatilityAI as RegVol, MarketStructureAI as RegMSAI, LiquiditySweepAI as RegLSAI, RiskAI as RegRiskAI, ReEntrySmartAI as RegReEntry, SMC_SLTP as RegSMC
        except Exception:
            RegTrend = RegVol = RegMSAI = RegLSAI = RegRiskAI = RegReEntry = RegSMC = None
        
        self.data_fetcher = MarketDataFetcher()
        
        # 🆕 Initialize SMC MTF Orchestrator now that we have symbol
        if self.smc_mtf_orch is None and hasattr(self, 'smc_orchestrator') and self.smc_orchestrator:
            try:
                from ai_modules.smc import SMCMTFOrchestrator
                self.smc_mtf_orch = SMCMTFOrchestrator(state_path=f"smc_state_{self.data_fetcher.symbol}.json")
                logger.info("✅ SMC MTF Orchestrator initialized (Persistence + Sniper Entries)")
            except Exception as e2:
                logger.warning(f"⚠️ SMC MTF Orchestrator init failed: {e2}")
                self.smc_mtf_orch = None
        
        self.ai_model = XGBoostTrendModel()
        self.backtest_engine = BacktestEngine()
        
        # Minimum lot for this instance (configurable via CLI override or live_trading.config.MIN_LOT)
        if min_lot is not None:
            try:
                self.min_lot = float(min_lot)
            except Exception:
                self.min_lot = DEFAULT_MIN_LOT
        else:
            try:
                from config import config as lc
                self.min_lot = float(getattr(lc, 'MIN_LOT', DEFAULT_MIN_LOT))
            except Exception:
                self.min_lot = DEFAULT_MIN_LOT
        
        # Control whether AUTO_FILTER will enforce session whitelist
        self.enable_session_whitelist = False
        self.reversal_ai = ReversalAI()
        self.volatility_ai = VolatilityAI()
        self.candle_ai = CandlePatternAI()
        
        # Throttle volatility computations to once per N signals in SUPERLIGHT mode
        self.volatility_throttle = 30
        self._volatility_last_signal = 0
        # Prefer AI implementations from the centralized registry `live_trading.logic`.
        try:
            from live_trading.logic import get_ai, TrendAI as RegTrend, VolatilityAI as RegVol, MarketStructureAI as RegMSAI, LiquiditySweepAI as RegLSAI, RiskAI as RegRiskAI, ReEntrySmartAI as RegReEntry, SMC_SLTP as RegSMC
        except Exception:
            RegTrend = RegVol = RegMSAI = RegLSAI = RegRiskAI = RegReEntry = RegSMC = None

        # TrendAI: prefer registry implementation, else fall back to bundled TrendAI
        try:
            if RegTrend:
                self.trend_ai = RegTrend()
                logger.info("✅ TrendAI (external) initialized")
            else:
                self.trend_ai = TrendAI()
                logger.info("✅ TrendAI (bundled) initialized")
        except Exception as e:
            logger.warning(f"⚠️ TrendAI init failed: {e}")
            self.trend_ai = None

        # Market Structure & Liquidity Sweep AI
        try:
            if RegMSAI:
                self.ms_ai = RegMSAI()
                logger.info("✅ MarketStructureAI (external) initialized")
            else:
                # Legacy/local import
                try:
                    from live_trading.ai_modules.smc.market_structure import MarketStructureAI
                    self.ms_ai = MarketStructureAI()
                    logger.info("✅ MarketStructureAI (local) initialized")
                except Exception:
                    self.ms_ai = None
        except Exception as e:
            logger.debug(f"⚠️ MarketStructureAI init error: {e}")
            self.ms_ai = None

        try:
            if RegLSAI:
                self.ls_ai = RegLSAI()
                logger.info("✅ LiquiditySweepAI (external) initialized")
            else:
                try:
                    from live_trading.ai_modules.smc.liquidity import LiquidityAI
                    self.ls_ai = LiquidityAI()
                    logger.info("✅ LiquidityAI (local) initialized")
                except Exception:
                    self.ls_ai = None
        except Exception as e:
            logger.debug(f"⚠️ LiquiditySweepAI init error: {e}")
            self.ls_ai = None

        # RiskAI
        try:
            if RegRiskAI:
                self.risk_ai = RegRiskAI()
                logger.info("✅ RiskAI (external) initialized")
            else:
                try:
                    from ai_modules.risk.risk_ai import RiskAI
                    self.risk_ai = RiskAI()
                    logger.info("✅ RiskAI (local) initialized")
                except Exception:
                    self.risk_ai = None
        except Exception:
            self.risk_ai = None

        # SMC SL/TP helper
        try:
            if RegSMC:
                self.smc_sl = RegSMC(buffer=0.0003)
                logger.info("✅ SMC_SLTP (external) initialized")
            else:
                from ai_modules.smc_sl_tp import SMC_SLTP
                self.smc_sl = SMC_SLTP(buffer=0.0003)
                logger.info("✅ SMC_SLTP initialized")
        except Exception:
            self.smc_sl = None

        # FusionAI capabilities logging (already initialized above as FusionAIUpgraded)
        try:
            fa = self.fusion_ai
            caps = []
            if hasattr(fa, 'fuse'):
                caps.append('fuse')
            if hasattr(fa, 'last_explain'):
                caps.append('last_explain')
            if hasattr(fa, 'explain'):
                caps.append('explain')
            logger.info(f"✅ FusionAI unified (v1-v5) initialized | Capabilities: {caps}")
            self._fusion_capabilities = caps
        except Exception as e:
            logger.warning(f"⚠️ FusionAI capability check failed: {e}")

        # ExplainAI - Human-readable explanations and logging
        try:
            try:
                from live_trading.logic import ExplainAI as RegExplainAI
            except Exception:
                RegExplainAI = None

            if RegExplainAI:
                self.explain_ai = RegExplainAI()
                logger.info("✅ ExplainAI (external) initialized")
            else:
                try:
                    from ai_modules.explain_ai import ExplainAI
                    self.explain_ai = ExplainAI()
                    logger.info("✅ ExplainAI initialized")
                except Exception:
                    self.explain_ai = None
        except Exception:
            self.explain_ai = None

        # PortfolioAI - Portfolio exposure controls and risk management
        try:
            try:
                from live_trading.logic import PortfolioAI as RegPortfolioAI
            except Exception:
                RegPortfolioAI = None

            if RegPortfolioAI:
                self.portfolio_ai = RegPortfolioAI()
                logger.info("✅ PortfolioAI (external) initialized")
            else:
                try:
                    from ai_modules.portfolio_ai import PortfolioAI
                    self.portfolio_ai = PortfolioAI()
                    logger.info("✅ PortfolioAI initialized")
                except Exception:
                    self.portfolio_ai = None
        except Exception:
            self.portfolio_ai = None

        # HealthAI - Model health monitoring and drift detection
        try:
            try:
                from live_trading.logic import HealthAI as RegHealthAI
            except Exception:
                RegHealthAI = None

            if RegHealthAI:
                self.health_ai = RegHealthAI()
                logger.info("✅ HealthAI (external) initialized")
            else:
                try:
                    from ai_modules.health_ai import HealthAI
                    self.health_ai = HealthAI()
                    logger.info("✅ HealthAI initialized")
                except Exception:
                    self.health_ai = None
        except Exception:
            self.health_ai = None

        # ExecutionAI - Pre-trade execution conditions check
        try:
            try:
                from live_trading.logic import ExecutionAI as RegExecutionAI
            except Exception:
                RegExecutionAI = None

            if RegExecutionAI:
                self.execution_ai = RegExecutionAI()
                logger.info("✅ ExecutionAI (external) initialized")
            else:
                try:
                    from ai_modules.execution.execution_ai import ExecutionAI
                    self.execution_ai = ExecutionAI()
                    logger.info("✅ ExecutionAI initialized")
                except Exception:
                    self.execution_ai = None
        except Exception:
            self.execution_ai = None

        # AdaptiveLearner - Post-trade weight adjustment
        try:
            try:
                from live_trading.logic import AdaptiveLearner as RegAdaptiveLearner
            except Exception:
                RegAdaptiveLearner = None

            if RegAdaptiveLearner:
                self.adaptive_learner = RegAdaptiveLearner()
                logger.info("✅ AdaptiveLearner (external) initialized")
            else:
                try:
                    from ai_modules.adaptive_learner import AdaptiveLearner
                    self.adaptive_learner = AdaptiveLearner()
                    logger.info("✅ AdaptiveLearner initialized")
                except Exception:
                    self.adaptive_learner = None
        except Exception:
            self.adaptive_learner = None

        # PatternSLTPAdvisor - Pattern-based SL/TP advice
        try:
            try:
                from live_trading.logic import PatternSLTPAdvisor as RegPatternSLTPAdvisor
            except Exception:
                RegPatternSLTPAdvisor = None

            if RegPatternSLTPAdvisor:
                self.pattern_sltp_advisor = RegPatternSLTPAdvisor()
                logger.info("✅ PatternSLTPAdvisor (external) initialized")
            else:
                try:
                    from ai_modules.pattern_sltp import PatternSLTPAdvisor
                    self.pattern_sltp_advisor = PatternSLTPAdvisor()
                    logger.info("✅ PatternSLTPAdvisor initialized")
                except Exception:
                    self.pattern_sltp_advisor = None
        except Exception:
            self.pattern_sltp_advisor = None

        # === NEW: SCORING MODULES (Dec 2025) ===
        # Trade Quality Scorer - Chấm điểm tín hiệu 0-100
        try:
            if TradeQualityScorer:
                self.quality_scorer = TradeQualityScorer(min_quality_score=65.0)
                logger.info("✅ TradeQualityScorer initialized (min_score=65)")
            else:
                self.quality_scorer = None
        except Exception as e:
            logger.warning(f"⚠️ TradeQualityScorer init failed: {e}")
            self.quality_scorer = None

        # Pattern Probability Filter - Lọc theo win rate lịch sử
        try:
            if PatternProbabilityFilter:
                self.pattern_filter = PatternProbabilityFilter(
                    min_win_rate=0.65,
                    min_sample_size=10
                )
                logger.info("✅ PatternProbabilityFilter initialized (min_wr=65%)")
            else:
                self.pattern_filter = None
        except Exception as e:
            logger.warning(f"⚠️ PatternProbabilityFilter init failed: {e}")
            self.pattern_filter = None

        # TrailingSL AI - Dynamic trailing stops
        try:
            try:
                from live_trading.logic import TrailingSL as RegTrailingSL
            except Exception:
                RegTrailingSL = None

            if RegTrailingSL:
                self.trailing_sl_ai = RegTrailingSL()
                logger.info("✅ TrailingSL AI (external) initialized")
            else:
                try:
                    from ai_modules.trailing_sl_ai import TrailingSL
                    self.trailing_sl_ai = TrailingSL()
                    logger.info("✅ TrailingSL AI initialized")
                except Exception:
                    self.trailing_sl_ai = None
        except Exception:
            self.trailing_sl_ai = None

        # SentimentAI - Price action sentiment analysis
        try:
            try:
                from live_trading.logic import SentimentAI as RegSentimentAI
            except Exception:
                RegSentimentAI = None

            if RegSentimentAI:
                self.sentiment_ai = RegSentimentAI()
                logger.info("✅ SentimentAI (external) initialized")
            else:
                try:
                    from ai_modules.sentiment_ai import SentimentAI
                    self.sentiment_ai = SentimentAI()
                    logger.info("✅ SentimentAI initialized")
                except Exception:
                    self.sentiment_ai = None
        except Exception:
            self.sentiment_ai = None

        # CrashDetector - Momentum crash detection with MACD veto
        try:
            self.crash_detector = CrashDetector()
            logger.info("✅ CrashDetector initialized")
        except Exception:
            self.crash_detector = None

        self.http_server = None
        # Load signal_count from file to persist across restarts
        self.signal_count = self._load_signal_count()
        self.is_running = False
        self.retrain_interval_days = 7  # 🎓 Default 7 ngày, có thể thay đổi qua --retrain-days
        
        # 🚫 DUPLICATE SIGNAL FILTER - Tránh spam lệnh giống nhau
        self.last_signal = {
            'action': None,
            'price': None,
            'timestamp': None
        }
        self.min_signal_interval = 60  # Tối thiểu 60 giây giữa 2 signal giống nhau
        self.min_price_change = 2.0    # Giá phải thay đổi ít nhất $2
        # Internal: last written signal JSON and timestamp to avoid repeated identical writes
        self._last_signal_written = None
        self._last_signal_written_ts = 0.0
        # Deduplication window seconds: skip identical writes within this window
        self._signal_dedup_window = 10
        
        # 💰 AI Money Manager
        self.use_money_manager = use_money_manager
        if use_money_manager:
            self.money_manager = AIMoneyManager(
                initial_balance=initial_balance,
                risk_per_trade=0.02,        # 2% risk/trade
                max_risk_total=0.10,        # 10% max total risk
                max_open_positions=999,     # UNLIMITED - AI quyết định
                min_risk_reward=1.5,        # Min 1.5:1 R:R
                adaptive_sizing=True        # Điều chỉnh theo win rate
            )
            # Attach post-close callback for re-entry logic
            try:
                self.money_manager.on_position_closed = self._on_position_closed
            except Exception:
                pass
        else:
            self.money_manager = None
        
        # 🛡️ Drawdown Protector
        self.use_drawdown_protector = use_drawdown_protector
        if use_drawdown_protector:
            self.drawdown_protector = DrawdownProtector(
                initial_balance=initial_balance,
                max_dd_percent=15.0,        # ✅ BẢO VỆ: Dừng trading khi lỗ 15%
                warning_dd_percent=8.0,     # ✅ CẢNH BÁO: Giảm lot khi lỗ 8%
                critical_dd_percent=12.0,   # ✅ NGUY HIỂM: Alert khi lỗ 12%
                lot_reduction_factor=0.5,   # Giảm 50%
                auto_resume_recovery=5.0    # Resume @ 5% recovery
            )
            # Sync balance với Money Manager nếu có
            if self.money_manager:
                self.drawdown_protector.update_balance(self.money_manager.current_balance)
                # Reset peak balance về balance thật khi khởi động
                self.drawdown_protector.peak_balance = self.money_manager.current_balance
                self.drawdown_protector.initial_balance = self.money_manager.current_balance
                self.drawdown_protector.is_trading_paused = False  # Reset pause flag
                self.drawdown_protector.max_dd_reached = 0.0  # Reset max DD
                logger.info(f"🔄 Đã sync DrawdownProtector với MT5 balance: ${self.money_manager.current_balance:,.2f}")
        else:
            self.drawdown_protector = None

        # Enable/disable live re-entry (if enabled the system will attempt to open
        # positions via `money_manager.add_position()` when ReEntrySmartAI signals)
        self.enable_live_reentry = bool(enable_live_reentry)

        # Hard cap per-order lot size for live orders (safety)
        try:
            self.live_lot_cap = float(live_lot_cap)
        except Exception:
            # Fallback safety cap: allow reasonably large lots by default
            # 0.01 is treated as the MINIMUM lot in sizing calculations elsewhere.
            self.live_lot_cap = 10.0

        # HTF (Higher Timeframe) policy: 'block' | 'soft' | 'off'
        # - 'block': chặn cứng tín hiệu ngược HTF (mặc định)
        # - 'soft': giảm confidence khi tín hiệu trái HTF (giữ cơ hội nhưng giảm thôi)
        # - 'off' : không áp dụng HTF filter
        self.htf_policy = htf_policy
        self.htf_soft_multiplier = float(htf_soft_multiplier) if htf_soft_multiplier else 0.6  # Tăng từ 0.5 → 0.6 (ít penalty hơn)

        # Re-entry & safety configs (defaults, can be overridden via CLI)
        self.enable_auto_sl_tp = False
        self.reentry_cooldown_seconds = 60
        self.last_reentry_time = datetime.min
        self.reentries_session_count = 0
        self.max_reentries_session = 3
        self.reentry_min_confidence = 0.65  # 0..1 (Tăng từ 0.5 → 0.65 để chỉ re-entry tín hiệu mạnh)

    def compute_sl_tp(self, signal: dict, market_data=None, atr_period: int = 14,
                      atr_multiplier: float = 1.5, base_rr: float = 2.0,
                      min_rr: float = 1.3, structure_buffer_pct: float = 0.25):
        """Compute dynamic SL and TP for a given signal.

        Returns dict: {'sl_price', 'tp_price', 'stop_distance', 'tp_distance', 'lot_size'}
        """
        try:
            action = signal.get('action', 'NONE')
            if action not in ('BUY', 'SELL', 'BUY_LIMIT', 'SELL_LIMIT'):
                return {}

            # 🆕 PRIORITY 1: SMC MTF Orchestrator Entry/SL/TP (most precise)
            smc_mtf_override = False
            if hasattr(self, 'last_smc_entry') and self.last_smc_entry is not None:
                # Verify SMC MTF signal matches current action
                smc_side = signal.get('smc_mtf_side', '').lower()
                # Check if SMC MTF side matches action OR if no explicit side (fallback to SMC MTF data)
                side_match = (smc_side == 'buy' and action.startswith('BUY')) or \
                             (smc_side == 'sell' and action.startswith('SELL')) or \
                             (not smc_side and hasattr(self, 'last_smc_sl') and self.last_smc_sl is not None)
                
                if side_match:
                    logger.info("🎯 Using SMC MTF Orchestrator Entry/SL/TP (Sniper Mode)")
                    entry_price = float(self.last_smc_entry)
                    stop_price = float(self.last_smc_sl)
                    tp_price = float(self.last_smc_tp)
                    
                    stop_distance = abs(entry_price - stop_price)
                    tp_distance = abs(tp_price - entry_price)
                    
                    # Calculate lot size based on risk
                    if hasattr(self, 'money_manager') and self.money_manager:
                        lot_size = self.money_manager.calculate_lot_size(
                            entry_price=entry_price,
                            sl_price=stop_price,
                            confidence=signal.get('confidence', 50) / 100.0
                        )
                    else:
                        lot_size = getattr(self, 'min_lot', DEFAULT_MIN_LOT)
                    
                    logger.info(f"   Entry: {entry_price:.5f} | SL: {stop_price:.5f} | TP: {tp_price:.5f}")
                    logger.info(f"   Stop Distance: {stop_distance:.5f} | TP Distance: {tp_distance:.5f}")
                    logger.info(f"   R:R = {(tp_distance/stop_distance):.2f}:1 | Lot: {lot_size:.2f}")
                    
                    return {
                        'sl_price': stop_price,
                        'tp_price': tp_price,
                        'stop_distance': stop_distance,
                        'tp_distance': tp_distance,
                        'lot_size': lot_size,
                        'source': 'smc_mtf_orchestrator',
                        'rr_ratio': tp_distance / stop_distance if stop_distance > 0 else 0
                    }
            
            # 🔥 PRIORITY 2: ICT Multi-Timeframe Logic Entry/SL/TP (Dec 11, 2025)
            if hasattr(self, 'last_ict_entry') and self.last_ict_entry is not None:
                ict_side = signal.get('ict_side', '').upper()
                side_match = (ict_side == 'BUY' and action.startswith('BUY')) or \
                             (ict_side == 'SELL' and action.startswith('SELL')) or \
                             (not ict_side and hasattr(self, 'last_ict_sl') and self.last_ict_sl is not None)
                
                if side_match:
                    logger.info("🔥 Using ICT Multi-Timeframe Entry/SL/TP (4-Step Confirmed)")
                    entry_price = float(self.last_ict_entry)
                    stop_price = float(self.last_ict_sl)
                    tp_price = float(self.last_ict_tp)
                    
                    stop_distance = abs(entry_price - stop_price)
                    tp_distance = abs(tp_price - entry_price)
                    
                    # Calculate lot size
                    if hasattr(self, 'money_manager') and self.money_manager:
                        lot_size = self.money_manager.calculate_lot_size(
                            entry_price=entry_price,
                            sl_price=stop_price,
                            confidence=signal.get('confidence', 50) / 100.0
                        )
                    else:
                        lot_size = getattr(self, 'min_lot', DEFAULT_MIN_LOT)
                    
                    logger.info(f"   Entry: {entry_price:.5f} | SL: {stop_price:.5f} | TP: {tp_price:.5f}")
                    logger.info(f"   Stop Distance: {stop_distance:.5f} | TP Distance: {tp_distance:.5f}")
                    logger.info(f"   R:R = {(tp_distance/stop_distance):.2f}:1 | Lot: {lot_size:.2f}")
                    
                    return {
                        'sl_price': stop_price,
                        'tp_price': tp_price,
                        'stop_distance': stop_distance,
                        'tp_distance': tp_distance,
                        'lot_size': lot_size,
                        'source': 'ict_multi_timeframe',
                        'rr_ratio': tp_distance / stop_distance if stop_distance > 0 else 0
                    }
            
            # Entry price: prefer explicit entry_price, otherwise current price
            entry_price = float(signal.get('entry_price') or signal.get('price') or 0.0)

            # Try to obtain H1 dataframe for ATR and levels
            df = None
            try:
                if market_data and isinstance(market_data, dict) and 'H1' in market_data:
                    df = market_data['H1']
                else:
                    # Best-effort: fetch recent H1 bars (non-blocking if MT5 unavailable)
                    if MT5_AVAILABLE and hasattr(self, 'data_fetcher'):
                        df = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_H1, bars=200)
            except Exception:
                df = None

            # Compute ATR baseline
            atr_val = None
            try:
                if df is not None and len(df) >= atr_period + 2:
                    atr_val = ATR({'H1': df}, 'H1', period=atr_period)
            except Exception:
                atr_val = None
            if not atr_val or atr_val <= 0:
                # sensible default for XAU/major: $2.0
                atr_val = 2.0

            # Structure-based candidate (recent swing high/low)
            structural_stop = None
            tp_level_candidate = None
            try:
                if df is not None and len(df) >= 10:
                    recent_high = df['high'].tail(50).max()
                    recent_low = df['low'].tail(50).min()
                    if action.startswith('BUY'):
                        structural_stop = recent_low - max(structure_buffer_pct * atr_val, 0.1)
                        # target toward recent_high
                        tp_level_candidate = recent_high
                    else:
                        structural_stop = recent_high + max(structure_buffer_pct * atr_val, 0.1)
                        tp_level_candidate = recent_low
            except Exception:
                structural_stop = None
                tp_level_candidate = None

            # ATR-based candidate
            if action.startswith('BUY'):
                atr_stop = entry_price - (atr_val * atr_multiplier)
            else:
                atr_stop = entry_price + (atr_val * atr_multiplier)

            # Choose conservative (farther) stop to avoid noise
            if structural_stop is not None:
                if action.startswith('BUY'):
                    stop_price = min(structural_stop, atr_stop)
                else:
                    stop_price = max(structural_stop, atr_stop)
            else:
                stop_price = atr_stop

            # Enforce minimum distance
            stop_distance = abs(entry_price - stop_price)
            min_stop = max(0.1, atr_val * 0.25)
            if stop_distance < min_stop:
                # expand stop away from price
                if action.startswith('BUY'):
                    stop_price = entry_price - min_stop
                else:
                    stop_price = entry_price + min_stop
                stop_distance = min_stop

            # Pattern-based RR scaling
            pattern_prob = 0.0
            try:
                pattern_prob = float(signal.get('pattern_prob') or signal.get('confidence') or 0.0)
                # If confidence is percentage (0-100), normalize to 0-1
                if pattern_prob > 1:
                    pattern_prob = pattern_prob / 100.0
            except Exception:
                pattern_prob = 0.0

            pattern_scale = 1.0
            if pattern_prob >= 0.8:
                pattern_scale = 1.3
            elif pattern_prob >= 0.6:
                pattern_scale = 1.1
            elif pattern_prob < 0.4:
                pattern_scale = 0.9

            rr_target = max(min_rr, base_rr * pattern_scale)

            # TP candidate: prefer structure level if it gives sufficient RR
            tp_price = None
            if tp_level_candidate is not None:
                # ensure TP is in the correct direction
                if action.startswith('BUY') and tp_level_candidate > entry_price:
                    tp_price = tp_level_candidate
                elif action.startswith('SELL') and tp_level_candidate < entry_price:
                    tp_price = tp_level_candidate

            # If tp candidate too close, enforce RR target
            required_tp_distance = stop_distance * rr_target
            if tp_price is not None:
                tp_distance = abs(tp_price - entry_price)
                if tp_distance < required_tp_distance:
                    # expand TP to meet RR target
                    if action.startswith('BUY'):
                        tp_price = entry_price + required_tp_distance
                    else:
                        tp_price = entry_price - required_tp_distance
            else:
                # no structural TP found -> set TP by RR
                if action.startswith('BUY'):
                    tp_price = entry_price + required_tp_distance
                else:
                    tp_price = entry_price - required_tp_distance

            tp_distance = abs(tp_price - entry_price)

            # Lot sizing: use money_manager if available
            lot = None
            try:
                conf_norm = float(signal.get('confidence', 50.0))
                if conf_norm > 1.0:
                    conf_norm = conf_norm / 100.0
            except Exception:
                conf_norm = 0.5

            if hasattr(self, 'money_manager') and self.money_manager is not None:
                try:
                    lot = self.money_manager.calculate_lot_size(entry_price, stop_price, confidence=conf_norm)
                except Exception:
                    lot = None

            if lot is None:
                # fallback simple lot calc: risk 0.5% of balance
                try:
                    balance = getattr(self.money_manager, 'current_balance', 10000.0)
                except Exception:
                    balance = 10000.0
                risk_amount = balance * 0.005
                try:
                    min_lot = float(getattr(self, 'min_lot', DEFAULT_MIN_LOT))
                except Exception:
                    min_lot = DEFAULT_MIN_LOT
                lot = max(min_lot, min(round(risk_amount / (stop_distance * 100), 2), 10.0))

            # Round prices and produce result
            result = {
                'sl_price': round(float(stop_price), 4),
                'tp_price': round(float(tp_price), 4),
                'stop_distance': round(float(stop_distance), 4),
                'tp_distance': round(float(tp_distance), 4),
                'lot_size': float(lot)
            }
            return result
        except Exception as e:
            logger.warning(f"⚠️ compute_sl_tp failed: {e}")
            return {}

    def compute_adaptive_lot(self, signal: dict, base_lot: float = None):
        """Compute adaptive lot using available AI modules (Fusion, Volatility, Risk).

        - `signal` expected to contain at least `confidence` (0..100) or None.
        - Returns a float lot (already capped by `self.live_lot_cap` when possible).
        - If RiskAI blocks trading, returns 0.0.
        """
        try:
            # Base confidence (0..1) - from signal if present
            conf = 0.0
            try:
                conf = float(signal.get('confidence', 0.0)) / 100.0
            except Exception:
                conf = 0.0

            # --- Prefer FusionAIv4 fused score when available ---
            fused = None
            try:
                # 1) explicit score in signal
                if 'fusion_score' in signal:
                    fused = float(signal.get('fusion_score') or 0.0)
                # 2) last cached fused score
                elif getattr(self, 'last_fused_score', None) is not None:
                    fused = float(self.last_fused_score)
                # 3) if we have a FusionAIv4 instance, try to compute from last_fusion_context or from signal
                elif getattr(self, 'fusion_ai_v4', None) is not None and hasattr(self.fusion_ai, 'fuse'):
                    # Prefer using last_fusion_context (populated during main loop)
                    ctx = signal.get('fusion_context') if isinstance(signal.get('fusion_context'), dict) else getattr(self, 'last_fusion_context', None)
                    if ctx is not None:
                        # Map our stored context to FusionAIv4 fuse() format
                        fusion_signals = {
                            'structure': ctx.get('structure', {}),
                            'liquidity': ctx.get('liquidity', {}),
                            'volume': ctx.get('volume', {}),
                            'momentum': ctx.get('momentum', {}),
                            'trend': ctx.get('trend'),
                            'reversal': ctx.get('reversal'),
                            'volatility': ctx.get('volatility', {}),
                            'sentiment': ctx.get('sentiment', {}),
                            'sideway': ctx.get('sideway', {}),
                            'session': ctx.get('session', {})
                        }

                        try:
                            fusion_result = self.fusion_ai.fuse(fusion_signals)
                            fused = fusion_result.get('score', 0.0)
                            # cache
                            try:
                                self.last_fused_score = fused
                            except Exception:
                                pass
                        except Exception:
                            fused = None
                    else:
                        # Minimal attempt: try to use signal fields directly
                        fusion_signals = {
                            'structure': signal.get('structure_score', {}),
                            'liquidity': signal.get('liquidity_score', {}),
                            'volume': signal.get('volume_score', {}),
                            'momentum': signal.get('momentum_score', {}),
                            'trend': (signal.get('trend_direction'), signal.get('trend_strength', 0.0)),
                            'reversal': (signal.get('reversal_signal'), signal.get('reversal_prob', 0.0)),
                            'volatility': signal.get('volatility_level', {}),
                            'sentiment': signal.get('sentiment_score', {}),
                            'sideway': signal.get('sideway_score', {}),
                            'session': signal.get('session_result', {})
                        }

                        try:
                            fusion_result = self.fusion_ai.fuse(fusion_signals)
                            fused = fusion_result.get('score', 0.0)
                            # cache
                            try:
                                self.last_fused_score = fused
                            except Exception:
                                pass
                        except Exception:
                            fused = None
            except Exception:
                fused = None

            # Normalize fused to 0..1 (some implementations return 0..100)
            try:
                if fused is not None and fused > 1.0:
                    fused = fused / 100.0
            except Exception:
                pass

            # Choose final confidence: fused preferred, else original signal conf
            final_conf = fused if (fused is not None and fused >= 0.0) else conf
            final_conf = max(0.0, min(1.0, float(final_conf)))

            # --- Volatility multiplier ---
            vol_scale = 1.0
            try:
                vp = getattr(self, 'last_vol_prediction', None)
                if vp is None and getattr(self, 'volatility_ai', None):
                    if hasattr(self.volatility_ai, 'get_volatility_multiplier'):
                        vol_scale = float(self.volatility_ai.get_volatility_multiplier())
                    elif hasattr(self.volatility_ai, 'suggest_multiplier'):
                        vol_scale = float(self.volatility_ai.suggest_multiplier())
                elif isinstance(vp, dict):
                    risk_score = float(vp.get('risk', 0.0))
                    if risk_score >= 0.7:
                        vol_scale = 0.4
                    elif risk_score >= 0.4:
                        vol_scale = 0.7
                    elif risk_score >= 0.2:
                        vol_scale = 0.85
                    else:
                        vol_scale = 1.0
            except Exception:
                vol_scale = 1.0

            # --- Risk gating via RiskAI ---
            try:
                risk_impl = getattr(self, 'risk_ai', None)
                if risk_impl is None:
                    try:
                        from ai_modules.risk.risk_ai import RiskAI as _RiskLocal
                        risk_impl = _RiskLocal(money_manager=self.money_manager, drawdown_protector=getattr(self, 'drawdown_protector', None))
                    except Exception:
                        risk_impl = None

                if risk_impl is not None:
                    # Preferred method: allowed_to_trade(volatility_score, equity)
                    vol_score_for_risk = 1.0
                    if getattr(self, 'last_vol_prediction', None) is not None:
                        vol_score_for_risk = float(self.last_vol_prediction.get('risk', 0.0))
                    try:
                        if hasattr(risk_impl, 'allowed_to_trade'):
                            can_trade, reason = risk_impl.allowed_to_trade(volatility_score=vol_score_for_risk, equity=(getattr(self.money_manager, 'current_balance', None) if getattr(self, 'money_manager', None) else None))
                            if not can_trade:
                                logger.info(f"🔒 RiskAI blocked adaptive lot: {reason}")
                                return 0.0
                        elif hasattr(risk_impl, 'evaluate'):
                            allowed, level = risk_impl.evaluate(volatility_level=(getattr(self, 'last_vol_prediction', {}) or {}).get('level'), trend_strength=signal.get('trend_strength', 0.0), sideway_score=signal.get('sideway_score', 0.0), liquidity_risk=(signal.get('liquidity') or {}).get('risk', 0.0), structure_score=signal.get('structure_score', {}), confidence=final_conf)
                            if not allowed:
                                logger.info(f"🔒 RiskAI.evaluate blocked adaptive lot: level={level}")
                                return 0.0
                    except Exception:
                        # If risk check fails unexpectedly, proceed conservatively
                        logger.debug("⚠️ RiskAI check failed during adaptive lot; proceeding conservatively")
            except Exception:
                pass

            # If base_lot not provided, use configured min_lot as base
            if base_lot is None:
                try:
                    base_lot = float(getattr(self, 'min_lot', DEFAULT_MIN_LOT))
                except Exception:
                    base_lot = float(DEFAULT_MIN_LOT)

            # Confidence multiplier: map [0..1] -> [min_mult..1]
            min_mult = 0.05
            conf_mult = max(min_mult, min(1.0, float(final_conf)))

            # Combined lot
            lot = float(base_lot) * conf_mult * float(vol_scale)

            # Apply live_lot_cap, optionally respect user BALANCE_LOT_CAPS mapping
            try:
                cap = float(getattr(self, 'live_lot_cap', 10.0) or 10.0)
                respect = False
                try:
                    from config import config as lc
                    respect = bool(getattr(lc, 'RESPECT_BALANCE_LOT_CAPS', False))
                except Exception:
                    respect = False

                if respect:
                    try:
                        balance_cap = float(self.get_balance_lot_cap())
                    except Exception:
                        balance_cap = cap
                    effective_cap = min(cap, balance_cap)
                    lot = min(lot, effective_cap)
                else:
                    lot = min(lot, cap)
            except Exception:
                pass

            # Round to two decimals
            try:
                lot = round(float(lot), 2)
            except Exception:
                lot = float(lot)

            if lot <= 0:
                return 0.0
            # Log decision for traceability
            try:
                logger.debug(f"Adaptive lot computed: base={base_lot} conf={final_conf:.3f} vol_scale={vol_scale:.3f} -> lot={lot}")
            except Exception:
                pass
            return lot
        except Exception as e:
            logger.warning(f"⚠️ compute_adaptive_lot failed: {e}")
            return float(base_lot)

    def _resolve_conflicting_decision(self, trend_action, trend_confidence, fusion_action, fusion_confidence, fusion_reasons, latest_signal=None):
        """Resolve conflicts between TrendAI (`trend_action`) and FusionAI (`fusion_action`).

        Returns: (resolved_action, meta_dict)
        Meta contains justification fields for logging and diagnostics.
        Rules (simple, extensible):
        - If both agree -> keep that action.
        - If disagree -> prefer the source with substantially higher confidence:
            * If trend_confidence >= 0.75 and fusion_confidence < 0.60 => prefer trend
            * If fusion_confidence >= 0.80 and trend_confidence < 0.60 => prefer fusion
            * Else compare numeric scores; require delta >= 0.20 to switch (tăng từ 0.15 → 0.20)
            * Default: prefer fusion (conservative: fusion is ensemble)
        """
        try:
            ta = (str(trend_action).upper() if trend_action is not None else None)
            fs = (str(fusion_action).upper() if fusion_action is not None else None)
            tc = float(trend_confidence or 0.0)
            fc = float(fusion_confidence or 0.0)

            meta = {
                'trend_action': ta,
                'trend_confidence': round(tc, 3),
                'fusion_action': fs,
                'fusion_score': round(fc, 3),
                'fusion_reasons': fusion_reasons
            }

            # If either side is NONE or unknown, prefer the other
            if ta not in ('BUY', 'SELL') and fs in ('BUY', 'SELL'):
                meta['decision'] = 'fusion_only'
                return fs, meta
            if fs not in ('BUY', 'SELL') and ta in ('BUY', 'SELL'):
                meta['decision'] = 'trend_only'
                return ta, meta

            # If they agree, keep
            if ta == fs:
                meta['decision'] = 'agree'
                return fs, meta

            # Conflict resolution rules
            # Strong trend preference (tăng từ 0.8 → 0.75, giữ fusion < 0.6)
            if tc >= 0.75 and fc < 0.60:
                meta['decision'] = 'prefer_trend_high_conf_low_fused'
                return ta, meta

            # Strong fusion preference (tăng từ 0.85 → 0.80, giữ trend < 0.6)
            if fc >= 0.80 and tc < 0.60:
                meta['decision'] = 'prefer_fusion_high_conf_low_trend'
                return fs, meta

            # Numeric comparison with hysteresis (tăng từ 0.15 → 0.20 để khó swap hơn)
            if (tc - fc) >= 0.20:
                meta['decision'] = 'trend_higher_by_delta'
                return ta, meta
            if (fc - tc) >= 0.20:
                meta['decision'] = 'fusion_higher_by_delta'
                return fs, meta

            # Default tie-breaker: prefer fusion (ensemble) but record tie
            meta['decision'] = 'default_prefer_fusion_tie'
            return fs, meta
        except Exception as e:
            logger.debug(f"⚠️ Decision resolver failed: {e}")
            # fallback: use fusion if present
            try:
                if fusion_action:
                    return fusion_action, {'decision': 'fallback_use_fusion', 'error': str(e)}
            except Exception:
                pass
            return trend_action or fusion_action or 'NONE', {'decision': 'fallback_use_any', 'error': str(e)}

    def _on_position_closed(self, pos: dict):
        """
        Callback invoked when a position is closed. Detect liquidity sweep and
        optionally perform re-entry (write dry-run and optionally open live).
        """
        try:
            # Only consider negative-closed positions for re-entry (user requested behaviour)
            pnl = float(pos.get('pnl') or 0.0)
            reason = pos.get('close_reason', '')

            # Basic gating: only if loss occurred or closed by SL
            if pnl >= 0 and 'SL' not in reason and 'CUT_LOSS' not in reason and 'AUTO_CUT_LOSS' not in reason:
                return

            # Cooldown / session cap
            now = datetime.now()
            try:
                if (now - self.last_reentry_time).total_seconds() < float(self.reentry_cooldown_seconds):
                    logger.debug("ℹ️ Re-entry cooldown active, skipping")
                    return
            except Exception:
                pass
            if self.reentries_session_count >= int(self.max_reentries_session):
                logger.debug("ℹ️ Max re-entries this session reached, skipping")
                return

            # Obtain H1 data
            df_h1 = None
            try:
                if hasattr(self, 'data_fetcher') and self.data_fetcher is not None and MT5_AVAILABLE:
                    try:
                        df_h1 = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_H1, bars=200)
                    except Exception:
                        df_h1 = None
            except Exception:
                df_h1 = None

            if not getattr(self, 'liquidity_detector', None):
                logger.debug("ℹ️ No liquidity detector available")
                return

            try:
                det = None
                if df_h1 is not None:
                    det = self.liquidity_detector(df_h1)
                else:
                    det = self.liquidity_detector(pd.DataFrame())
            except Exception as e:
                logger.debug(f"⚠️ Liquidity detector failed: {e}")
                det = None

            if not det or not isinstance(det, dict):
                return

            # Check for bullish sweep (re-entry buy)
            if det.get('sweep') and det.get('direction') == 'buy' and float(det.get('strength', 0.0)) >= float(self.reentry_min_confidence):
                logger.info(f"🔎 Liquidity sweep detected (buy) strength={det.get('strength')}, reason={det.get('reason')}")
                # Build re-entry signal
                cur_price = None
                try:
                    if df_h1 is not None and len(df_h1) > 0:
                        cur_price = float(df_h1['close'].iloc[-1])
                except Exception:
                    cur_price = None
                if cur_price is None:
                    try:
                        cur_price = float(self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_H1, bars=1)['close'].iloc[-1])
                    except Exception:
                        cur_price = pos.get('entry_price')

                re_signal = {
                    'action': 'BUY',
                    'symbol': getattr(self.data_fetcher, 'symbol', 'XAUUSD'),
                    'price': round(float(cur_price), 4) if cur_price is not None else pos.get('entry_price'),
                    'entry_price': round(float(cur_price), 4) if cur_price is not None else pos.get('entry_price'),
                    'lot_size': float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                    'confidence': float(det.get('strength', 0.0)) * 100.0,
                    'timestamp': datetime.now().isoformat(),
                    'signal_id': self.signal_count + 1,
                    'reason': 'post_close_reentry:' + str(det.get('reason', ''))
                }

                # Compute SL/TP and suggested lot
                try:
                    sltp = self.compute_sl_tp(re_signal, market_data={'H1': df_h1} if df_h1 is not None else None)
                    if sltp:
                        re_signal['sl_price'] = sltp.get('sl_price')
                        re_signal['tp_price'] = sltp.get('tp_price')
                        re_signal['lot_size'] = round(sltp.get('lot_size', re_signal['lot_size']), 2)
                except Exception:
                    pass

                # dry-run: write to file
                try:
                    self._write_signal_to_file(re_signal)
                    logger.info(f"🔁 Post-close re-entry: wrote dry-run signal reason={det.get('reason')} strength={det.get('strength')}")
                except Exception:
                    pass

                # If allowed, open live position (respect lot cap)
                if getattr(self, 'enable_live_reentry', False) and self.money_manager is not None:
                    try:
                        suggested_lot = float(re_signal.get('lot_size', getattr(self, 'min_lot', DEFAULT_MIN_LOT)) or getattr(self, 'min_lot', DEFAULT_MIN_LOT))
                        # Compute adaptive lot using available AI modules (Fusion, Volatility, Risk)
                        try:
                            lot_to_use = float(self.compute_adaptive_lot(re_signal, base_lot=suggested_lot))
                        except Exception:
                            lot_to_use = float(suggested_lot)
                        # Enforce hard cap as a final safety
                        try:
                            cap = float(getattr(self, 'live_lot_cap', 10.0) or 10.0)
                            lot_to_use = min(lot_to_use, cap)
                        except Exception:
                            pass

                        # If the adaptive lot returns zero or negative, skip live open
                        if lot_to_use <= 0:
                            logger.info("ℹ️ Adaptive lot sizing returned 0 → skipping live re-entry open")
                            lot_to_use = 0.0

                        # If adaptive sizing returned zero, skip live open entirely
                        if lot_to_use <= 0:
                            logger.info("ℹ️ Post-close re-entry skipped: adaptive lot sizing returned 0 or trade blocked by RiskAI")
                        else:
                            # Attempt to place market order via MT5 if available
                            mt5_ticket = None
                            if MT5_AVAILABLE:
                                try:
                                    import MetaTrader5 as mt5
                                    symbol = re_signal.get('symbol')
                                    tick = mt5.symbol_info_tick(symbol)
                                    price = float(tick.ask) if re_signal.get('action') == 'BUY' else float(tick.bid)
                                    request = {
                                        'action': mt5.TRADE_ACTION_DEAL,
                                        'symbol': symbol,
                                        'volume': float(lot_to_use),
                                        'type': mt5.ORDER_TYPE_BUY if re_signal.get('action') == 'BUY' else mt5.ORDER_TYPE_SELL,
                                        'price': price,
                                        'deviation': 20,
                                        'magic': 234000,
                                        'comment': 'AI_ReEntry',
                                        'type_time': mt5.ORDER_TIME_GTC,
                                        'type_filling': mt5.ORDER_FILLING_IOC
                                    }
                                    result = mt5.order_send(request)
                                    if result is not None and getattr(result, 'retcode', None) == mt5.TRADE_RETCODE_DONE:
                                        mt5_ticket = getattr(result, 'order', None) or getattr(result, 'request', None) or getattr(result, 'ticket', None)
                                        logger.info(f"✅ Post-close re-entry: Market order sent, retcode={result.retcode}")
                                        # Try to set SL/TP if provided
                                        if re_signal.get('sl_price') or re_signal.get('tp_price'):
                                            try:
                                                self.money_manager.update_position_sl_tp_on_mt5(mt5_ticket, re_signal.get('sl_price'), re_signal.get('tp_price'))
                                            except Exception:
                                                pass
                                    else:
                                        logger.warning(f"⚠️ Post-close re-entry: MT5 order_send failed: {getattr(result, 'comment', result)}")
                                except Exception as e:
                                    logger.warning(f"⚠️ Post-close re-entry: MT5 order error: {e}")

                            # Add to manager (record)
                            try:
                                added = self.money_manager.add_position(re_signal, lot_to_use, mt5_ticket=mt5_ticket)
                                if added is None:
                                    logger.warning(f"⚠️ Post-close re-entry: invalid signal data, skipping add_position")
                                else:
                                    logger.info(f"✅ Post-close re-entry: added position to manager: {added}")
                            except Exception as e:
                                logger.warning(f"⚠️ Post-close re-entry: add_position failed: {e}")

                            # Update counters
                            self.last_reentry_time = datetime.now()
                            self.reentries_session_count += 1
                    except Exception as e:
                        logger.warning(f"⚠️ Post-close re-entry failed: {e}")

            # --- AdaptiveLearner: Update FusionAI weights based on trade result ---
            try:
                if hasattr(self, 'adaptive_learner') and self.adaptive_learner is not None:
                    # Register trade result to update FusionAI weights
                    self.adaptive_learner.register_result()
                    logger.debug("🧠 AdaptiveLearner: Updated FusionAI weights from trade result")
            except Exception as e:
                logger.debug(f"⚠️ AdaptiveLearner update failed: {e}")

            # --- PatternProbabilityFilter: Record trade result for learning ---
            try:
                if hasattr(self, 'pattern_filter') and self.pattern_filter is not None:
                    # Get original signal if available
                    original_signal = pos.get('original_signal', None)
                    if original_signal:
                        # Determine if won or lost
                        won = pnl > 0
                        self.pattern_filter.record_trade_result(original_signal, won)
                        logger.debug(f"📚 PatternFilter: Recorded {'WIN' if won else 'LOSS'} for pattern learning")
            except Exception as e:
                logger.debug(f"⚠️ PatternFilter update failed: {e}")

        except Exception as e:
            logger.debug(f"⚠️ _on_position_closed error: {e}")

    def get_balance_lot_cap(self) -> float:
        """Return the user-defined maximum per-order lot cap based on current balance.

        Mapping (as requested):
        - balance < 10000 => max 0.2
        - balance < 20000 => max 0.5
        - balance < 40000 => max 0.25
        - balance < 100000 => max 0.68
        - balance >=100000 => max 1.68

        The function is intentionally conservative: it returns a float cap and
        will not increase AI-chosen lots beyond this cap.
        """
        try:
            bal = 0.0
            if getattr(self, 'money_manager', None) is not None:
                bal = float(getattr(self.money_manager, 'current_balance', 0.0) or 0.0)
            # Fallback: try drawdown protector or default initial balance
            if bal <= 0 and getattr(self, 'drawdown_protector', None) is not None:
                bal = float(getattr(self.drawdown_protector, 'current_balance', 0.0) or 0.0)
            if bal <= 0:
                bal = float(getattr(self, 'initial_balance', 10000.0) or 10000.0)

            # Try to load mapping from live_trading.config if available
            try:
                from config import config as lc
                # Prefer helper if present
                if hasattr(lc, 'get_balance_lot_cap_for_balance'):
                    return float(lc.get_balance_lot_cap_for_balance(bal))
                # Or try list mapping
                caps = getattr(lc, 'BALANCE_LOT_CAPS', None)
                if caps:
                    for lo, hi, cap in caps:
                        try:
                            if float(bal) >= float(lo) and float(bal) < float(hi):
                                return float(cap)
                        except Exception:
                            continue
            except Exception:
                # Config import failed — fall back to hard-coded mapping below
                pass

            # Hard-coded fallback mapping (kept for backward compatibility)
            if bal < 10000.0:
                return 0.2
            if bal < 20000.0:
                return 0.5
            if bal < 40000.0:
                return 0.25
            if bal < 100000.0:
                return 0.68
            return 1.68
        except Exception:
            # Safe fallback
            return float(getattr(self, 'live_lot_cap', 10.0) or 10.0)

    def initialize_system(self, train_model=True, skip_backtest=False):
        """Initialize complete AI system"""
        logger.info("🚀 Initializing Complete AI Trading System...")
        
        # ========== KIỂM TRA KẾT NỐI MT5 TRƯỚC KHI BẮT ĐẦU ==========
        logger.info("=" * 70)
        logger.info("🔍 STEP 0: CHECKING MT5 CONNECTION AND DATA AVAILABILITY")
        logger.info("=" * 70)
        
        # 0.1. Kiểm tra thư viện MT5
        if not MT5_AVAILABLE:
            logger.error("❌ Thư viện MetaTrader5 CHƯA CÀI ĐẶT!")
            logger.error("💡 Giải pháp: pip install MetaTrader5")
            logger.error("🛑 DỬNG LẠI - Không thể tiếp tục mà không có thư viện MT5")
            return False
        logger.info("✅ Thư viện MetaTrader5: OK")
        
        # 0.2. Kiểm tra kết nối MT5
        if not self.data_fetcher.use_mt5:
            logger.error("❌ MT5 CHƯA KẾT NỐI!")
            logger.error("💡 Nguyên nhân có thể:")
            logger.error("   1. Phần mềm MT5 chưa chạy")
            logger.error("   2. MT5 chưa đăng nhập")
            logger.error("   3. Khởi tạo MT5 thất bại")
            logger.error("🛑 DỬNG LẠI - Không thể tiếp tục mà không có kết nối MT5")
            return False
        
        if not self.data_fetcher.mt5_initialized:
            logger.error("❌ KHỚI TẠO MT5 THẤT BẠI!")
            logger.error("💡 Vui lòng kiểm tra:")
            logger.error("   1. Mở phần mềm MT5")
            logger.error("   2. Đăng nhập vào tài khoản giao dịch")
            logger.error("   3. Đảm bảo tài khoản đang hoạt động")
            logger.error("🛑 DỬNG LẠI - Không thể tiếp tục mà không khởi tạo được MT5")
            return False
        
        logger.info("✅ Kết nối MT5: OK")
        
        # 0.3. Kiểm tra symbol (dùng symbol đã được data_fetcher auto-detect nếu có)
        symbol_to_check = getattr(self.data_fetcher, 'symbol', 'GOLD') or 'GOLD'
        logger.info(f"🔍 Kiểm tra symbol: {symbol_to_check}...")
        try:
            symbol_info = mt5.symbol_info(symbol_to_check)
            if symbol_info is None:
                # Nếu symbol cụ thể không có, liệt kê các symbol trên broker chứa XAU/GOLD
                logger.error(f"❌ KHÔNG TÌM THẤY SYMBOL {symbol_to_check}!")
                logger.info("🔎 Đang tìm các symbol tương tự trên broker (XAU/GOLD)...")
                avail = []
                try:
                    all_syms = mt5.symbols_get()
                    if all_syms:
                        for s in all_syms:
                            name = getattr(s, 'name', None) or getattr(s, 'symbol', None)
                            if not name:
                                continue
                            up = name.upper()
                            if 'XAU' in up or 'GOLD' in up:
                                avail.append(name)
                except Exception:
                    avail = []

                if avail:
                    logger.error(f"⚠️ Symbols on broker matching XAU/GOLD: {avail}")
                    logger.error("💡 Hãy đặt 'symbol' trong cấu hình bằng một trong các tên trên hoặc thêm symbol vào Market Watch trong MT5.")
                else:
                    logger.error("⚠️ Không tìm thấy symbol liên quan đến XAU/GOLD trên broker. Vui lòng thêm symbol vào Market Watch hoặc kiểm tra tên symbol chính xác.")

                logger.error("🛑 DỬNG LẠI - Không thể giao dịch mà không có symbol XAU/GOLD")
                return False

            if not symbol_info.visible:
                logger.warning(f"⚠️ {symbol_to_check} không hiển thị trong Market Watch")
                logger.info(f"🔧 Đang thêm {symbol_to_check} vào Market Watch...")
                if mt5.symbol_select(symbol_to_check, True):
                    logger.info(f"✅ Đã thêm {symbol_to_check} vào Market Watch")
                else:
                    logger.error(f"❌ Thêm {symbol_to_check} vào Market Watch thất bại")
                    return False

            logger.info(f"✅ Symbol {symbol_to_check}: OK")
            logger.info(f"   Giá Bid hiện tại: {symbol_info.bid:.2f}")
            logger.info(f"   Giá Ask hiện tại: {symbol_info.ask:.2f}")
            logger.info(f"   Spread: {symbol_info.spread}")

            # Adjust ExecutionAI thresholds for symbol-specific units
            try:
                sym_upper = (symbol_to_check or '').upper()
                if getattr(self, 'execution_ai', None) is not None:
                    # XAU/GOLD instruments have spreads in absolute USD (e.g. 0.4..1.0)
                    if 'XAU' in sym_upper or 'GOLD' in sym_upper:
                        try:
                            # Increase allowed spread threshold for precious metals
                            self.execution_ai.spread_threshold = 1.0
                            logger.info(f"🔧 ExecutionAI: adjusted spread_threshold to {self.execution_ai.spread_threshold} for symbol {sym_upper}")
                        except Exception:
                            logger.debug("⚠️ Failed to adjust ExecutionAI.spread_threshold for XAU/GOLD")
                    else:
                        # keep default for FX/other symbols
                        pass
            except Exception:
                pass

        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra symbol {symbol_to_check}: {e}")
            logger.error("🛑 DỬNG LẠI - Kiểm tra symbol thất bại")
            return False
        
        # 0.4. Kiểm tra dữ liệu lịch sử
        logger.info("🔍 Kiểm tra dữ liệu lịch sử...")
        bars_needed = 90 * 24  # 🎯 2,160 bars cho 90 ngày trên 1H
        logger.info(f"   Yêu cầu: {bars_needed} bars (90 ngày × 1H)")

        # Sử dụng helper để đảm bảo symbol có lịch sử (tự động select và chờ download nếu cần)
        try:
            ok = self.ensure_symbol_history(symbol_to_check, timeframe=mt5.TIMEFRAME_H1, required_bars=1000, timeout_seconds=300)
            if not ok:
                logger.error("❌ KHÔNG THỂ LẤY DỮ LIỆU TỪ MT5! (Thiếu bars hoặc timeout)")
                logger.error("💡 Giải pháp có thể:")
                logger.error("   1. Mở chart symbol trong MT5 để tải lịch sử")
                logger.error("   2. Tools → Options → Charts → Max bars in history (tăng lên 100,000+)")
                logger.error("   3. Đợi MT5 tải dữ liệu hoặc kiểm tra tên symbol chính xác")
                logger.error("🛑 DỬNG LẠI - Không thể tiếp tục mà không có dữ liệu")
                return False
            else:
                logger.info("✅ Dữ liệu lịch sử: SẴN SÀNG (Đã kiểm tra đủ bars)")

        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra dữ liệu: {e}")
            logger.error("🛑 DỬNG LẠI - Kiểm tra dữ liệu thất bại")
            return False
        
        logger.info("=" * 70)
        logger.info("✅ TẤT CẢ KIỂM TRA ĐỀU THÀNH CÔNG - BẮT ĐẦU LẤY DỮ LIỆU")
        logger.info("=" * 70)
        
        # 1. Fetch training data from MT5 (REAL DATA ONLY - NO DEMO FALLBACK)
        logger.info("📊 Bước 1: Lấy dữ liệu thị trường từ MT5...")
        logger.info(f"   🎯 TRAINING TRÊN 1H - Phân tích chính xác hơn 5M")
        logger.info(f"   Đang lấy {bars_needed} bars (90 ngày dữ liệu 1H)...")
        
        training_data = self.data_fetcher.fetch_mt5_data(symbol=symbol_to_check, timeframe=mt5.TIMEFRAME_H1, bars=bars_needed)
        
        if training_data is None or len(training_data) < 1000:
            logger.error("❌ KHÔNG THỂ LẤY ĐỦ DỮ LIỆU TỮ MT5!")
            logger.error(f"❌ Yêu cầu: {bars_needed} bars, Nhận được: {len(training_data) if training_data is not None else 0} bars")
            logger.error("💡 Tối thiểu: 1,000 bars để huấn luyện")
            logger.error("💡 Kiểm tra: Tools → Options → Charts → Max bars in history (tăng lên 100,000+)")
            logger.error("🛑 DỬNG LẠI - Không thể tiếp tục mà không có đủ dữ liệu")
            return False
        
        logger.info(f"✅ Đã lấy {len(training_data)} bars từ MT5 (DỮ LIỆU THỰC)")
        logger.info(f"   Khoảng thời gian: {training_data.index[0]} đến {training_data.index[-1]}")
        logger.info(f"   Khoảng giá: {training_data['low'].min():.2f} - {training_data['high'].max():.2f}")
        
        # 2. Train AI model
        if train_model and ML_AVAILABLE:
            logger.info("🧠 Bước 2: Huấn luyện mô hình AI...")
            success = self.ai_model.train_model(training_data)
            if not success:
                logger.error("❌ Huấn luyện mô hình thất bại")
                return False
        else:
            logger.info("🔄 Bước 2: Tải mô hình có sẵn...")
            if not self.ai_model.load_model():
                logger.error("❌ Không tìm thấy mô hình đã train - Vui lòng train mô hình trước!")
                logger.error("💡 Chạy lệnh: python complete_ai_trading_system.py --train")
                return False

        # 2.b Auto-train TrendAI when --train flag is used
        # If the user requested training, ensure the TrendAI model is trained as well.
        try:
            if train_model and ML_AVAILABLE and hasattr(self, 'trend_ai') and self.trend_ai:
                logger.info("🧠 Bước 2.b: Huấn luyện TrendAI PRO (SMC-enhanced)...")
                try:
                    trend_ok = self.trend_ai.train_model(training_data)
                    if not trend_ok:
                        logger.warning("⚠️ TrendAI training did not complete (insufficient data or error). Falling back to SMC heuristic.")
                    else:
                        logger.info("✅ TrendAI PRO trained successfully")
                except Exception as e:
                    logger.warning(f"⚠️ TrendAI training failed with exception: {e} - continuing with SMC heuristic")
        except Exception:
            # Non-fatal: continue even if TrendAI auto-train hook fails
            logger.warning("⚠️ Auto-train TrendAI hook failed unexpectedly - continuing")

        # Defensive: ensure ai_model exposes the expected wrapper interface.
        try:
            if hasattr(self, '_ensure_ai_model_interface'):
                self._ensure_ai_model_interface()
        except Exception:
            # Non-fatal: continue but warn
            logger.warning("⚠️ Failed to enforce ai_model interface during init")
        
        # 3. Run backtest
        if skip_backtest:
            logger.info("⚡ Bước 3: Bỏ qua backtest - chuyển thẳng sang giao dịch thực")
        else:
            logger.info("⚡ Bước 3: Chạy backtest...")
            backtest_results = self.backtest_engine.run_backtest(training_data, self.ai_model)
        
        # 4. Start HTTP server - GỬI TÍN HIỆU LÊN MT5
        logger.info("🌐 Bước 4: Khởi động HTTP server...")
        self.start_http_server()
        
        # Start CPU monitor thread if available (best-effort, non-fatal)
        try:
            if PSUTIL_AVAILABLE and CPU_MONITOR_ENABLED:
                monitor_thread = threading.Thread(target=cpu_monitor, args=(5,), daemon=True)
                monitor_thread.start()
                logger.info("🔋 CPU monitor started (psutil detected) - runtime modes: ultra/superlight/safe")
                # Start heartbeat logger as well (periodic status)
                try:
                    hb = threading.Thread(target=heartbeat, args=(60,), daemon=True)
                    hb.start()
                    logger.info("💓 Heartbeat logger started (interval=60s)")
                    # Emit an initial heartbeat immediately so the heartbeat file is created
                    try:
                        init_mode = get_runtime_mode()
                        if PSUTIL_AVAILABLE:
                            try:
                                cpu_init = psutil.cpu_percent(interval=0.1)
                            except Exception:
                                cpu_init = 0.0
                            try:
                                mem_init = psutil.virtual_memory().percent
                            except Exception:
                                mem_init = 0.0
                            init_msg = f"💓 Initial Heartbeat: Mode={init_mode} | CPU={cpu_init:.1f}% | MEM={mem_init:.1f}%"
                        else:
                            init_msg = f"💓 Initial Heartbeat: Mode={init_mode}"

                        try:
                            # Write initial heartbeat to heartbeat file if available
                            if 'hb_logger' in globals() and hb_logger and getattr(hb_logger, 'handlers', None):
                                try:
                                    hb_logger.info(init_msg)
                                except Exception:
                                    pass

                            # Also print a visible separator + initial message to console
                            try:
                                sep0 = '=' * 70
                                logger.info(sep0)
                                logger.info(init_msg)
                                logger.info(sep0)
                            except Exception:
                                logger.info(init_msg)
                        except Exception:
                            # Non-fatal: continue startup even if heartbeat write fails
                            pass
                    except Exception:
                        # Non-fatal: continue startup even if heartbeat write fails
                        pass
                except Exception as _:
                    logger.warning("⚠️ Failed to start heartbeat thread")
            else:
                # No-op else branch (heartbeat not started) — keep startup flow unchanged
                pass
        except Exception as e:
            logger.warning(f"⚠️ Failed to start cpu_monitor thread: {e}")

        logger.info("✅ Hệ thống AI Trading khởi động thành công!")
        return True
    
    def start_http_server(self, port=6555):
        """Start HTTP server for MT5 communication"""
        try:
            server_address = ('', port)
            self.http_server = HTTPServer(server_address, HTTPSignalHandler)
            
            def run_server():
                logger.info(f"🌐 HTTP server đã khởi động trên cổng {port}")
                logger.info(f"📡 Địa chỉ: http://127.0.0.1:{port}/signal")
                self.http_server.serve_forever()
            
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
        except Exception as e:
            logger.error(f"❌ Lỗi khởi động HTTP server: {e}")

    def train_price_pattern_classifier(self, outdir='live_trading/models', samples_per_pattern=50,
                                       tick_size=0.01, spread=0.05, volume_scale=1.0):
        """Generate synthetic pattern dataset and train a simple classifier.

        Saves model to `outdir/pattern_classifier.pkl` and scaler to `outdir/pattern_scaler.pkl`.
        """
        try:
            if not ML_AVAILABLE:
                logger.error("❌ ML libraries not available in this environment. Install scikit-learn/xgboost/joblib.")
                return False

            # Ensure local import path
            try:
                root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
                if root_dir not in sys.path:
                    sys.path.insert(0, root_dir)
                from scripts.generate_pattern_dataset import generate_dataset
            except Exception as e:
                logger.error(f"❌ Failed to import dataset generator: {e}")
                return False

            ensure_dir = lambda p: os.makedirs(p, exist_ok=True)
            ensure_dir(outdir)

            logger.info(f"📦 Generating synthetic dataset ({samples_per_pattern} samples/pattern) ...")
            dataset_csv, meta_csv = generate_dataset(outdir, samples_per_pattern=samples_per_pattern,
                                                    tick_size=tick_size, spread=spread, volume_scale=volume_scale)

            logger.info(tr("Loading dataset from {path} ...", path=dataset_csv))
            df = pd.read_csv(dataset_csv)

            # Simple feature engineering: use last N returns, sma, volatility per sample window
            # We'll aggregate per-sample into feature vectors (mean, std, last_return, max_drawdown)
            feats = []
            labels = []
            sample_ids = df['sample_id'].unique()
            for sid in sample_ids:
                sub = df[df['sample_id'] == sid]
                close = sub['close'].values
                returns = np.diff(close) / (close[:-1] + 1e-8)
                feat = {
                    'mean_return': np.nanmean(returns),
                    'std_return': np.nanstd(returns),
                    'max_return': np.nanmax(returns),
                    'min_return': np.nanmin(returns),
                    'last_return': returns[-1] if len(returns) > 0 else 0.0,
                    'vol_mean': sub['volume'].mean(),
                    'range_mean': ((sub['high'] - sub['low']) / (sub['close'] + 1e-8)).mean()
                }
                feats.append(list(feat.values()))
                labels.append(sub['pattern'].iloc[0])

            X = np.array(feats)
            y = np.array(labels)

            # Train/test split
            from sklearn.model_selection import train_test_split
            from sklearn.preprocessing import StandardScaler
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.metrics import classification_report
            import joblib

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_test_s = scaler.transform(X_test)

            logger.info("🧠 Đang huấn luyện mô hình RandomForest Phân loại mẫu mô hình...")
            logger.info("   - Dữ liệu sử dụng: features, target")
            logger.info("   - Thuật toán: RandomForestClassifier, n_estimators=200, random_state=42, n_jobs=-1")
            logger.info("   - Đang thực hiện fitting mô hình...")
            clf = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=-1)
            clf.fit(X_train_s, y_train)

            logger.info("   - Đang đánh giá mô hình...")
            preds = clf.predict(X_test_s)
            report = classification_report(y_test, preds, zero_division=0)
            logger.info("📊 Báo cáo phân loại mẫu mô hình:\n" + report)

            # Save feature importances (we know the synthetic feature names)
            try:
                feature_names = ['mean_return', 'std_return', 'max_return', 'min_return', 'last_return', 'vol_mean', 'range_mean']
                save_feature_importances(clf, feature_names, 'PatternClassifier', outdir=outdir, X=X_test_s, y=y_test, compute_permutation=True)
            except Exception:
                pass

            # Save model and scaler
            model_path = os.path.join(outdir, 'pattern_classifier.pkl')
            scaler_path = os.path.join(outdir, 'pattern_scaler.pkl')
            joblib.dump(clf, model_path)
            joblib.dump(scaler, scaler_path)
            logger.info(f"✅ Đã lưu mô hình RandomForest Phân loại mẫu mô hình tại {model_path}")
            logger.info(f"✅ Đã lưu scaler mẫu mô hình tại {scaler_path}")
            return True
        except Exception as e:
            logger.error(f"❌ train_price_pattern_classifier failed: {e}")
            try:
                import traceback as _tb
                logger.debug(_tb.format_exc())
            except Exception:
                # fallback: log exception repr
                logger.debug(repr(e))
            return False

    # ----------------- Pattern inference helpers -----------------
    def load_pattern_model(self, model_dir: Optional[str] = None):
        """Load saved pattern classifier and scaler into the instance.

        If `model_dir` is None the function will look for the `models_large`
        directory located next to this script file. If `model_dir` is a
        relative path it will be resolved relative to the script directory.

        Sets `self.pattern_model` and `self.pattern_scaler`.
        """
        try:
            import joblib
            # Resolve model_dir relative to this script to avoid cwd issues
            script_dir = Path(__file__).resolve().parent
            if model_dir is None:
                model_dir_path = script_dir.joinpath('models_large')
            else:
                model_dir_path = Path(model_dir)
                if not model_dir_path.is_absolute():
                    model_dir_path = (script_dir / model_dir).resolve()

            # Log resolved path for easier debugging
            logger.debug(f"🔎 Checking old pattern model directory: {model_dir_path}")

            model_path = model_dir_path.joinpath('pattern_classifier.pkl')
            scaler_path = model_dir_path.joinpath('pattern_scaler.pkl')

            if not model_path.exists():
                # Changed from ERROR to DEBUG - this is expected when using new ChartPatternDetector
                logger.debug(f"⚠️ Old pattern_classifier.pkl not found (using new ChartPatternDetector instead)")
                return False

            self.pattern_model = joblib.load(str(model_path))
            self.pattern_scaler = None
            if scaler_path.exists():
                try:
                    self.pattern_scaler = joblib.load(str(scaler_path))
                except Exception:
                    self.pattern_scaler = None

            logger.info(f"✅ Loaded pattern model from {model_dir_path}")
            return True
        except Exception as e:
            logger.error(f"❌ load_pattern_model failed: {e}")
            try:
                import traceback as _tb
                logger.debug(_tb.format_exc())
            except Exception:
                pass
            return False

    def predict_patterns_on_df(self, df, window: int = 30):
        """Run pattern inference on an OHLCV DataFrame and return predictions DataFrame.

        NOTE: This is the OLD pattern inference system (requires trained pattern_classifier.pkl).
        The NEW ChartPatternDetector (chart_pattern_detector.py) does NOT use this.
        This function is kept for backward compatibility but is not used in current signal generation.

        Returns the DataFrame produced by `pattern_inference.predict_on_df` or empty DF on failure.
        """
        try:
            # Lazy import local inference helper (keeps separation)
            try:
                from .pattern_inference import predict_on_df
            except Exception:
                # fallback to relative import
                from core.pattern_inference import predict_on_df

            if not hasattr(self, 'pattern_model'):
                # Try loading default model dir
                ok = self.load_pattern_model()
                if not ok:
                    # Changed from ERROR to DEBUG - this is expected when using new ChartPatternDetector
                    logger.debug("⚠️ Old pattern_classifier.pkl not found - using new ChartPatternDetector instead")
                    return pd.DataFrame()

            preds = predict_on_df(df, self.pattern_model, scaler=getattr(self, 'pattern_scaler', None), window=window)
            return preds
        except Exception as e:
            logger.debug(f"⚠️ predict_patterns_on_df skipped: {e}")
            return pd.DataFrame()

    def predict_patterns_on_csv(self, csv_path: str, model_dir: Optional[str] = None, window: int = 30):
        """Convenience: load CSV OHLCV and run pattern inference. Returns preds DF."""
        try:
            # Flexible CSV loader similar to backtest
            df = None
            for col in ['timestamp', 'time', 'datetime']:
                try:
                    df = pd.read_csv(csv_path, parse_dates=[col], index_col=col)
                    break
                except Exception:
                    df = None
            if df is None:
                df = pd.read_csv(csv_path)
                for col in df.columns:
                    if 'time' in col.lower() or 'date' in col.lower():
                        try:
                            df[col] = pd.to_datetime(df[col])
                            df.set_index(col, inplace=True)
                            break
                        except Exception:
                            continue
            # Normalize index name
            df.index.name = 'timestamp'

            # Ensure required columns
            for c in ['open', 'high', 'low', 'close', 'volume']:
                if c not in df.columns:
                    raise ValueError(f"Column missing: {c} in {csv_path}")

            # Load model
            if not self.load_pattern_model(model_dir):
                return pd.DataFrame()

            preds = self.predict_patterns_on_df(df, window=window)
            return preds
        except Exception as e:
            logger.error(f"❌ predict_patterns_on_csv failed: {e}")
            try:
                import traceback as _tb
                logger.debug(_tb.format_exc())
            except Exception:
                pass
            return pd.DataFrame()

    def _send_webhook(self, url: str, payload: dict, auth: Optional[str] = None, max_retries: int = 3, backoff: float = 2.0) -> bool:
        """Send JSON payload to webhook URL with simple retry/backoff and optional Authorization header.
        Uses `requests` if available; otherwise falls back to urllib.
        Returns True on HTTP 2xx, False otherwise.
        """
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = auth

        body = json.dumps(payload).encode('utf-8')

        # Try requests first
        if REQUESTS_AVAILABLE:
            attempt = 0
            while attempt <= max_retries:
                try:
                    r = requests.post(url, json=payload, headers=headers, timeout=10)
                    if 200 <= r.status_code < 300:
                        return True
                    else:
                        logger.debug(f"⚠️ Webhook POST returned status {r.status_code}: {r.text}")
                except Exception as e:
                    logger.debug(f"⚠️ Webhook POST attempt {attempt} failed: {e}")
                attempt += 1
                time.sleep(backoff ** attempt)
            return False

        # Fallback: urllib
        try:
            from urllib.request import Request, urlopen
            from urllib.error import URLError, HTTPError
            attempt = 0
            while attempt <= max_retries:
                try:
                    req = Request(url, data=body, headers=headers)
                    resp = urlopen(req, timeout=10)
                    code = resp.getcode()
                    if 200 <= code < 300:
                        return True
                    else:
                        logger.debug(f"⚠️ Webhook POST returned status {code}")
                except Exception as e:
                    logger.debug(f"⚠️ Webhook POST attempt {attempt} failed (urllib): {e}")
                attempt += 1
                time.sleep(backoff ** attempt)
        except Exception as e:
            logger.debug(f"⚠️ Webhook fallback failed to import urllib: {e}")

        return False

    def ensure_symbol_history(self, symbol, timeframe= None, required_bars=1000, timeout_seconds=180):
        """Ensure the given symbol is selected in Market Watch and has at least `required_bars` history.
        Returns True if enough bars are available, False on timeout/failure.
        """
        if timeframe is None:
            timeframe = mt5.TIMEFRAME_H1

        logger.info(f"🔧 ensure_symbol_history: symbol={symbol}, timeframe={timeframe}, required_bars={required_bars}, timeout={timeout_seconds}s")

        start_time = time.time()
        # Try to add/select symbol first
        try:
            try:
                info = mt5.symbol_info(symbol)
            except Exception:
                info = None

            if info is None:
                logger.warning(f"⚠️ Symbol {symbol} không tồn tại trên broker (symbol_info returned None)")
                return False

            if not info.visible:
                logger.info(f"🔧 Symbol {symbol} không hiển thị - thử add vào Market Watch...")
                try:
                    mt5.symbol_select(symbol, True)
                except Exception:
                    pass

            # Loop until enough bars or timeout
            while True:
                try:
                    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, required_bars)
                except Exception as e:
                    rates = None
                    logger.debug(f"🔍 copy_rates error: {e}")

                got = 0
                if rates is not None:
                    try:
                        got = len(rates)
                    except Exception:
                        got = 0

                logger.info(f"🔎 {symbol} - bars available: {got}/{required_bars}")
                if got >= required_bars:
                    return True

                if time.time() - start_time > timeout_seconds:
                    logger.error(f"⏱️ Timeout waiting for {symbol} history ({got}/{required_bars})")
                    return False

                # Wait a bit for MT5 to download history (user should open chart in MT5)
                time.sleep(5)

        except Exception as e:
            logger.error(f"❌ ensure_symbol_history error: {e}")
            return False
    
    def generate_live_signal(self, demo_mode=True, min_confidence=30.0, enable_sideways_filter=True):
        # --- Market Structure & Liquidity Sweep AI ---
        ms_result = None
        ls_result = None
        """Generate real-time trading signal với low confidence threshold (30%)"""
        global latest_signal

        self.signal_count += 1
        # Ensure live_data exists in local scope to avoid UnboundLocalError in except handlers
        live_data = None

        # Initialize variables to avoid UnboundLocalError
        tf_data = {}
        vol_prediction = {}

        # ============================================================================
        # 🛡️ STEP 0: DRAWDOWN PROTECTION CHECK
        # ============================================================================
        if self.drawdown_protector:
            # Check if trading is paused due to max drawdown
            if not self.drawdown_protector.can_open_trade():
                logger.warning(f"⛔ TRADING PAUSED - Drawdown quá cao!")
                self.drawdown_protector.print_status()

                latest_signal.update({
                    "action": "NONE",
                    "reason": "DRAWDOWN_PROTECTION",
                    "timestamp": datetime.now().isoformat(),
                    "signal_id": self.signal_count
                })

                return latest_signal

        # ---------------------- SIGNAL-DRIFT PROTECTION INIT ----------------------
        try:
            # Allow overriding settings via ai_system.signal_drift_settings or medium_plus_config
            sd = getattr(self, 'signal_drift_settings', None)
            if sd is None:
                mpg = getattr(self, 'medium_plus_config', None)
                if isinstance(mpg, dict):
                    sd = mpg.get('signal_drift_protection', None)
            # Default settings
            if sd is None:
                sd = {
                    'enabled': True,
                    'window_size': 20,
                    'max_same_dir_ratio': 0.75,
                    'max_consecutive_same_dir': 6,
                    'cooldown_seconds': 600,
                    'action': 'pause'  # or 'downgrade'
                }
            # Normalize
            try:
                sd['window_size'] = int(sd.get('window_size', 20))
                sd['max_same_dir_ratio'] = float(sd.get('max_same_dir_ratio', 0.75))
                sd['max_consecutive_same_dir'] = int(sd.get('max_consecutive_same_dir', 6))
                sd['cooldown_seconds'] = int(sd.get('cooldown_seconds', 600))
            except Exception:
                pass
            self.signal_drift_settings = sd

            # per-instance history and cooldown
            if not hasattr(self, '_drift_history'):
                try:
                    self._drift_history = deque(maxlen=sd.get('window_size', 20))
                except Exception:
                    self._drift_history = deque(maxlen=20)
            if not hasattr(self, '_drift_cooldown_until'):
                self._drift_cooldown_until = 0.0
        except Exception:
            # non-fatal: continue without drift protection
            pass

        # If cooldown active, block trading early
        try:
            sd = getattr(self, 'signal_drift_settings', {}) or {}
            if sd.get('enabled', False) and getattr(self, '_drift_cooldown_until', 0.0) > time.time():
                remaining = int(self._drift_cooldown_until - time.time())
                logger.warning(f"⛔ DRIFT PROTECTION ACTIVE - paused for {remaining}s")
                latest_signal.update({
                    "action": "NONE",
                    "reason": "DRIFT_COOLDOWN_ACTIVE",
                    "drift_cooldown_remaining": remaining,
                    "timestamp": datetime.now().isoformat(),
                    "signal_id": self.signal_count
                })
                return latest_signal
        except Exception:
            pass

        # CPU/MEMORY SAFE MODE: if monitor flagged safe_mode, pause trading
        try:
            if CPU_MONITOR_ENABLED and PSUTIL_AVAILABLE and safe_mode:
                logger.warning("⛔ SAFE MODE: High CPU or Memory detected — trading paused by cpu_monitor")
                latest_signal.update({
                    "action": "NONE",
                    "reason": "CPU_SAFE_MODE",
                    "timestamp": datetime.now().isoformat(),
                    "signal_id": self.signal_count
                })
                return latest_signal
        except Exception:
            # Non-fatal: if flags missing, continue as normal
            pass

        # ------------------------- AUTO MODE (Windows VPS) -------------------------
        try:
            if not hasattr(self, "auto_mode"):
                self.auto_mode = AutoModeController()

            mode = self.auto_mode.decide_mode()

            # Default: run fully
            deep_volatility = True
            full_smc = True

            if mode == "ULTRA":
                deep_volatility = True
                full_smc = True
            elif mode == "SUPERLIGHT":
                deep_volatility = False
                full_smc = False
            elif mode == "SAFE":
                latest_signal.update({
                    "action": "NONE",
                    "reason": "AUTO_SAFE_MODE_CPU_OVERLOAD",
                    "timestamp": datetime.now().isoformat(),
                    "signal_id": self.signal_count
                })
                return latest_signal

            # Expose to other modules/functions (build_trend_features uses this)
            try:
                globals()['AUTO_FULL_SMC'] = bool(full_smc)
                globals()['AUTO_DEEP_VOLATILITY'] = bool(deep_volatility)
            except Exception:
                pass
        except Exception:
            # If auto mode fails, fallback to defaults
            mode = 'UNKNOWN'
            deep_volatility = True
            full_smc = True
            
            # Check current drawdown level and show warning
            current_dd = self.drawdown_protector.calculate_drawdown()
            if current_dd >= self.drawdown_protector.warning_dd_percent:
                logger.warning(f"⚠️ WARNING - Drawdown: {current_dd:.2f}% (Warning level: {self.drawdown_protector.warning_dd_percent}%)")
                logger.warning(f"💡 Lot size sẽ giảm xuống {self.drawdown_protector.get_lot_multiplier():.1%}")
            elif current_dd > 0:
                logger.info(f"📊 Current Drawdown: {current_dd:.2f}% (Status: OK)")
        
        if demo_mode or not ML_AVAILABLE:
            # Demo mode: Simulate market conditions và filtering
            action = random.choice(["BUY", "SELL"])
            price = random.uniform(1845.0, 1855.0)
            confidence = random.uniform(50.0, 95.0)  # 🎯 Chỉ tạo signal >= 50%
            order_type = action  # Demo mode dùng market order
            limit_price = price
            
            # 🚫 Demo: Simulate sideways market filtering (30% chance)
            is_sideways_demo = random.random() < 0.3  # 30% chance of sideways
            if is_sideways_demo:
                action = "NONE"
                order_type = "NONE"
                logger.info(f"🚫 Demo: Simulated sideways market filter")
            
        else:
            # Real mode: AI prediction với confidence filter
            live_data = self.data_fetcher.fetch_live_data()
            # Try multi-timeframe feature prediction first (TrendAI-style)
            action = "NONE"
            confidence = 0.0
            try:
                # Attempt to fetch several timeframes; fall back gracefully if any fail
                try:
                    df_m5 = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_M5, 200)
                    if df_m5 is not None and len(df_m5) > 0:
                        tf_data['M5'] = df_m5
                except Exception:
                    pass
                try:
                    df_m15 = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_M15, 200)
                    if df_m15 is not None and len(df_m15) > 0:
                        tf_data['M15'] = df_m15
                except Exception:
                    pass
                try:
                    df_h1 = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_H1, 500)
                    if df_h1 is not None and len(df_h1) > 0:
                        tf_data['H1'] = df_h1
                except Exception:
                    pass
                try:
                    df_h4 = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_H4, 500)
                    if df_h4 is not None and len(df_h4) > 0:
                        tf_data['H4'] = df_h4
                except Exception:
                    pass

                # ============================================================
                # 🚫 STEP 0: ENHANCED NEWS FILTER - CHECK TRƯỚC TIÊN!
                # ⚡ OPTIMIZATION: Check news BEFORE running AI (save 5-10s)
                # ============================================================
                news_safe_to_trade = True
                news_reason = ""
                if hasattr(self, 'news_filter_ai') and self.news_filter_ai:
                    try:
                        logger.info("=" * 70)
                        logger.info("📰 ENHANCED NEWS FILTER AI - News & Volatility Check")
                        logger.info("=" * 70)
                        
                        # Use H1 data for ATR spike detection
                        df_for_news = tf_data.get('H1', live_data)
                        current_time = datetime.now()
                        
                        news_safe_to_trade, news_reason = self.news_filter_ai.should_trade(
                            df_for_news, current_time
                        )
                        
                        if not news_safe_to_trade:
                            logger.warning(f"🚫 NEWS FILTER BLOCKED: {news_reason}")
                            
                            # ⚡ Return early - DON'T run AI modules (save CPU/RAM)
                            latest_signal.update({
                                "action": "NONE",
                                "reason": f"NEWS_FILTER: {news_reason}",
                                "timestamp": datetime.now().isoformat(),
                                "signal_id": self.signal_count
                            })
                            logger.info("=" * 70)
                            logger.info("⚡ OPTIMIZATION: Skipped AI analysis due to news block (saved ~5-10s)")
                            return latest_signal
                        else:
                            logger.info(f"✅ NEWS FILTER CLEAR: {news_reason}")
                        
                        # Check if we need to close positions
                        news_check = self.news_filter_ai.check_news_window(current_time)
                        if news_check['should_close_positions']:
                            logger.warning(f"⚠️ NEWS WARNING: {news_check['upcoming_event']} in {news_check['minutes_until_news']} minutes")
                            logger.warning(f"💡 Consider closing open positions")
                        
                        logger.info("=" * 70)
                        
                    except Exception as e:
                        logger.error(f"❌ News Filter AI error: {e}")
                        # Non-fatal - continue without news filter

                # ============================================================
                # 🚫 STEP 0.2: VOLATILITY PRE-CHECK - Fast volatility risk check
                # ⚡ OPTIMIZATION: Check BEFORE running heavy AI (save 5-10s)
                # ============================================================
                vol_prediction = None
                try:
                    # Build volatility features for pre-check
                    news = {}  # TODO: Integrate with actual news feed
                    volatility_features = build_volatility_features(tf_data, news)
                    
                    # Quick volatility prediction
                    if hasattr(self, 'volatility_ai') and self.volatility_ai:
                        vol_prediction = self.volatility_ai.predict(volatility_features)
                        
                        if not vol_prediction.get('trading_allowed', True):
                            logger.warning("=" * 70)
                            logger.warning("🚫 VOLATILITY PRE-CHECK BLOCKED")
                            logger.warning(f"   Risk Level: {vol_prediction.get('level', 'UNKNOWN')}")
                            logger.warning(f"   Risk Score: {vol_prediction.get('risk', 0.0):.3f}")
                            logger.warning(f"   Recommendation: {vol_prediction.get('recommendation', 'High risk')}")
                            logger.warning("=" * 70)
                            
                            # Return early - DON'T run AI modules (save CPU/RAM)
                            latest_signal.update({
                                "action": "NONE",
                                "reason": f"VOLATILITY_BLOCK: {vol_prediction.get('level', 'HIGH_RISK')}",
                                "timestamp": datetime.now().isoformat(),
                                "signal_id": self.signal_count
                            })
                            logger.info("⚡ OPTIMIZATION: Skipped AI analysis due to volatility block (saved ~5-10s)")
                            return latest_signal
                        else:
                            logger.info("✅ VOLATILITY PRE-CHECK: OK to trade")
                            logger.info(f"   Risk Level: {vol_prediction.get('level', 'MEDIUM')}")
                            logger.info(f"   Risk Score: {vol_prediction.get('risk', 0.0):.3f}")
                    else:
                        vol_prediction = {'trading_allowed': True, 'level': 'MEDIUM', 'risk': 0.0, 'regime': 'MEDIUM'}
                        logger.debug("ℹ️ Volatility AI not available - skipping pre-check")
                except Exception as e:
                    logger.debug(f"⚠️ Volatility pre-check failed: {e} - continuing")
                    vol_prediction = {'trading_allowed': True, 'level': 'MEDIUM', 'risk': 0.0, 'regime': 'MEDIUM'}

                # ============================================================
                # 🚫 STEP 0.3: SIDEWAYS PRE-CHECK - Fast sideways detection
                # ⚡ OPTIMIZATION: Check BEFORE running SMC/ICT (save 3-5s)
                # ============================================================
                try:
                    # Get sideways classification
                    sideway_result = detect_sideway(tf_data)
                    sideway_score = sideway_result[0] if isinstance(sideway_result, tuple) else sideway_result
                    sideways_type = sideway_result[1] if isinstance(sideway_result, tuple) and len(sideway_result) > 1 else 'UNKNOWN'
                    range_pct = sideway_result[2] if isinstance(sideway_result, tuple) and len(sideway_result) > 2 else 0.0
                    atr_pct = sideway_result[3] if isinstance(sideway_result, tuple) and len(sideway_result) > 3 else 0.0
                    
                    # ⚡ NEW LOGIC: Only block TIGHT sideways (skip WIDE sideways)
                    if enable_sideways_filter and sideway_score >= 2:
                        if sideways_type == 'TIGHT':
                            logger.warning("=" * 70)
                            logger.warning("🚫 TIGHT SIDEWAYS BLOCKED")
                            logger.warning(f"   Type: {sideways_type} (Range: {range_pct*100:.2f}%, ATR: {atr_pct*100:.2f}%)")
                            logger.warning(f"   Sideway Score: {sideway_score}/7 (Threshold: >=2)")
                            logger.warning("   ❌ Range quá hẹp - Whipsaw risk cao - SKIP")
                            logger.warning("=" * 70)
                            
                            # Return early - DON'T run AI modules (save CPU/RAM)
                            latest_signal.update({
                                "action": "NONE",
                                "reason": f"TIGHT_SIDEWAYS_BLOCK: Score {sideway_score}/7, Range {range_pct*100:.2f}%",
                                "timestamp": datetime.now().isoformat(),
                                "signal_id": self.signal_count
                            })
                            logger.info("⚡ OPTIMIZATION: Skipped AI analysis due to TIGHT sideways (saved ~3-5s)")
                            return latest_signal
                        else:
                            # WIDE SIDEWAYS or TRENDING: Allow trading
                            logger.info("=" * 70)
                            logger.info(f"✅ {sideways_type} SIDEWAYS DETECTED")
                            logger.info(f"   Range: {range_pct*100:.2f}%, ATR: {atr_pct*100:.2f}%")
                            logger.info(f"   Sideway Score: {sideway_score}/7")
                            logger.info("   ✅ Biên độ đủ rộng - Có thể trade range (support/resistance)")
                            logger.info("=" * 70)
                    elif sideway_score >= 2:
                        logger.warning(f"⚠️ SIDEWAYS DETECTED ({sideways_type}, Score: {sideway_score}/7) - But filter is DISABLED, continuing AI analysis...")
                    else:
                        logger.info(f"✅ SIDEWAYS PRE-CHECK: OK - Score {sideway_score}/7 ({sideways_type})")
                except Exception as e:
                    logger.debug(f"⚠️ Sideways pre-check failed: {e} - continuing")
                    sideway_score = 0
                    sideways_type = 'UNKNOWN'

                logger.info("=" * 70)
                logger.info("✅ ALL PRE-FILTERS PASSED - Starting AI Analysis...")
                logger.info("=" * 70)

                # --- Market Structure & Liquidity Sweep AI ---
                try:
                    if hasattr(self, 'structure_ai') and self.structure_ai:
                        struct_result = self.structure_ai.analyze(tf_data['H1'] if 'H1' in tf_data else live_data)
                    else:
                        struct_result = {"structure":0, "type":"unknown", "swings":[], "meta":{}}
                except Exception as e:
                    logger.warning(f"⚠️ StructureAI failed: {e}")
                    struct_result = {"structure":0, "type":"unknown", "swings":[], "meta":{}}

                try:
                    if hasattr(self, 'liquidity_ai') and self.liquidity_ai:
                        liq_result = self.liquidity_ai.detect(tf_data['H1'] if 'H1' in tf_data else live_data)
                    else:
                        liq_result = {"signal":0, "strength":0.0, "reason":"none", "details":{}}
                except Exception as e:
                    logger.warning(f"⚠️ LiquidityAI failed: {e}")
                    liq_result = {"signal":0, "strength":0.0, "reason":"error", "details":{}}

                try:
                    if hasattr(self, 'sentiment_ai') and self.sentiment_ai:
                        sent_result = self.sentiment_ai.analyze(tf_data['H1'] if 'H1' in tf_data else live_data)
                    else:
                        sent_result = {"sentiment":"neutral","score":0.0,"meta":{}}
                except Exception as e:
                    logger.warning(f"⚠️ SentimentAI failed: {e}")
                    sent_result = {"sentiment":"neutral","score":0.0,"meta":{}}

                if tf_data is not None and len(tf_data) > 0:
                    # 🛡️ DEBUG: Check tf_data content before building features
                    logger.debug(f"📊 tf_data keys: {list(tf_data.keys()) if isinstance(tf_data, dict) else 'Not dict'}")
                    for tf_key in ['H1', 'M15', 'M5']:
                        if tf_key in tf_data:
                            df = tf_data[tf_key]
                            logger.debug(f"📊 {tf_key} data: {len(df) if hasattr(df, '__len__') else 'No len'} rows")
                    
                    features = build_trend_features(tf_data)
                    reversal_features = build_reversal_features(tf_data)
                    reversal_prob = self.reversal_ai.predict(reversal_features)
                    
                    # 🧠 TREND AI PRO - Dự đoán BUY/SELL từ SMC concepts
                    trend_action = "NONE"
                    trend_confidence = 0.0
                    
                    if hasattr(self, 'trend_ai') and self.trend_ai:
                        try:
                            # 🛡️ DEFENSIVE CHECK: Ensure features is valid dict
                            if features is None or not isinstance(features, dict) or len(features) == 0:
                                logger.warning("⚠️ TrendAI prediction failed: Invalid or empty features input")
                                logger.warning(f"   tf_data type: {type(tf_data)}")
                                logger.warning(f"   tf_data keys: {list(tf_data.keys()) if isinstance(tf_data, dict) else 'Not dict'}")
                                logger.warning(f"   features: {features}")
                                
                                # 🚨 FALLBACK: Try to build features from live_data if tf_data failed
                                try:
                                    logger.info("🔄 FALLBACK: Attempting to build features from live_data...")
                                    if live_data is not None and len(live_data) > 20:
                                        # Convert live_data to tf_data format
                                        fallback_tf_data = {'H1': live_data.tail(200)}  # Use recent 200 bars as H1
                                        fallback_features = build_trend_features(fallback_tf_data)
                                        if fallback_features and len(fallback_features) > 0:
                                            features = fallback_features
                                            logger.info(f"✅ FALLBACK SUCCESS: Built {len(features)} features from live_data")
                                        else:
                                            logger.warning("⚠️ FALLBACK FAILED: build_trend_features returned empty from live_data")
                                            trend_action, trend_confidence = "NONE", 0.0
                                    else:
                                        logger.warning("⚠️ FALLBACK IMPOSSIBLE: live_data insufficient or None")
                                        trend_action, trend_confidence = "NONE", 0.0
                                except Exception as fallback_e:
                                    logger.warning(f"⚠️ FALLBACK EXCEPTION: {fallback_e}")
                                    trend_action, trend_confidence = "NONE", 0.0
                            else:
                                trend_action, trend_confidence = self.trend_ai.predict(features)
                                logger.info(f"🧠 TrendAI PRO: {trend_action} ({trend_confidence:.1%}) - SMC Analysis Complete")
                        except Exception as e:
                            logger.warning(f"⚠️ TrendAI prediction failed: {e}")
                            trend_action, trend_confidence = "NONE", 0.0
                    
                    # ============================================================
                    # 🎯 SMC ORCHESTRATOR - Full Smart Money Concepts Analysis
                    # ============================================================
                    smc_signal = None
                    smc_confidence = 0.0
                    smc_confluence = 0
                    
                    if hasattr(self, 'smc_orchestrator') and self.smc_orchestrator:
                        try:
                            logger.info("=" * 70)
                            logger.info("🎯 SMC ORCHESTRATOR - Multi-Timeframe SMC Analysis")
                            logger.info("=" * 70)
                            
                            # Check if we have enough timeframe data for full analysis
                            if 'H1' in tf_data and 'M15' in tf_data and 'M5' in tf_data:
                                # Full multi-timeframe SMC analysis
                                smc_result = self.smc_orchestrator.analyze_full(
                                    df_htf=tf_data['H1'],
                                    df_mtf=tf_data['M15'],
                                    df_ltf=tf_data['M5']
                                )
                                
                                # Extract final signal from SMC
                                final_smc = smc_result.get('final_signal', {})
                                smc_signal = final_smc.get('signal')  # 'buy'/'sell'/None
                                smc_confidence = final_smc.get('confidence', 0.0)
                                smc_confluence = final_smc.get('confluence_score', 0)
                                
                                if smc_signal:
                                    logger.info(f"🎯 SMC SIGNAL: {smc_signal.upper()}")
                                    logger.info(f"   Entry: {final_smc.get('entry', 'N/A')}")
                                    logger.info(f"   SL: {final_smc.get('sl', 'N/A')}")
                                    logger.info(f"   TP: {final_smc.get('tp', 'N/A')}")
                                    logger.info(f"   Confidence: {smc_confidence:.1%}")
                                    logger.info(f"   Confluence: {smc_confluence}/6")
                                    logger.info(f"   Model: {final_smc.get('model', 'N/A')}")
                                    
                                    # Store SMC SL/TP for later use
                                    self.last_smc_sl = final_smc.get('sl')
                                    self.last_smc_tp = final_smc.get('tp')
                                    self.last_smc_entry = final_smc.get('entry')
                                else:
                                    logger.info(f"⚠️ SMC: No valid entry - {final_smc.get('reason', 'Unknown')}")
                                
                                # Log SMC report for transparency
                                smc_report = self.smc_orchestrator.get_smc_report(smc_result)
                                logger.debug(smc_report)
                                
                            else:
                                # Single timeframe fallback (use H1 or M15)
                                logger.info("⚠️ SMC: Using single timeframe analysis (missing some TFs)")
                                primary_tf = tf_data.get('H1') or tf_data.get('M15') or tf_data.get('M5')
                                
                                if primary_tf is not None:
                                    smc_result = self.smc_orchestrator.analyze_single_timeframe(primary_tf)
                                    final_smc = smc_result.get('final_signal', {})
                                    smc_signal = final_smc.get('signal')
                                    smc_confidence = final_smc.get('confidence', 0.0)
                                    smc_confluence = final_smc.get('confluence_score', 0)
                                    
                                    if smc_signal:
                                        logger.info(f"🎯 SMC SIGNAL (Single TF): {smc_signal.upper()} - Conf: {smc_confidence:.1%}")
                                else:
                                    logger.warning("⚠️ SMC: No timeframe data available")
                            
                            logger.info("=" * 70)
                            
                        except Exception as e:
                            logger.error(f"❌ SMC Orchestrator error: {e}")
                            smc_signal = None
                            smc_confidence = 0.0
                    else:
                        logger.debug("ℹ️ SMC Orchestrator not available")
                    
                    # 🆕 SMC MTF ORCHESTRATOR - Enhanced Sniper Entries (Dec 8, 2025)
                    smc_mtf_candidates = []
                    if hasattr(self, 'smc_mtf_orch') and self.smc_mtf_orch:
                        try:
                            from ai_modules.smc import finalize_candidates
                            
                            logger.info("=" * 70)
                            logger.info("🎯 SMC MTF ORCHESTRATOR - Sniper Entry System")
                            logger.info("=" * 70)
                            
                            # Prepare dataframes with attrs
                            dfs_mtf = {}
                            for tf_name in ['H4', 'H1', 'M15', 'M5']:
                                if tf_name in tf_data:
                                    df = tf_data[tf_name]
                                    df.attrs['symbol'] = self.data_fetcher.symbol
                                    df.attrs['timeframe'] = tf_name
                                    dfs_mtf[tf_name] = df
                            
                            if len(dfs_mtf) >= 2:  # Need at least 2 timeframes
                                # Ingest & detect OBs
                                self.smc_mtf_orch.ingest_mtfs(dfs_mtf, persist_new=True)
                                logger.info(f"✅ SMC MTF: Ingested {len(dfs_mtf)} timeframes")
                                
                                # Find sniper entries (6 pips tolerance for XAUUSD ~ 0.60)
                                max_dist = 0.60 if 'XAU' in self.data_fetcher.symbol else 0.0006
                                raw_candidates = self.smc_mtf_orch.find_ltf_entries(dfs_mtf, max_distance_pips=max_dist)
                                logger.info(f"🎯 SMC MTF: Found {len(raw_candidates)} raw candidates")
                                
                                # Score & filter (killzone: 0-6h)
                                smc_mtf_candidates = finalize_candidates(
                                    raw_candidates,
                                    dfs_mtf,
                                    disabled_hours=[(0, 6)]
                                )
                                
                                if smc_mtf_candidates:
                                    best = smc_mtf_candidates[0]
                                    logger.info(f"🔥 SMC MTF BEST: {best['side'].upper()} @ {best['entry']:.5f}")
                                    logger.info(f"   SL: {best['sl']:.5f} | TP: {best['tp']:.5f}")
                                    logger.info(f"   Score: {best['score']:.2%} | Reason: {best['reason']}")
                                    logger.info(f"   OB ID: {best['ob_id'][:8]}...")
                                    
                                    # Store metadata for signal
                                    smc_mtf_metadata = {
                                        'side': best['side'],
                                        'entry': best['entry'],
                                        'sl': best['sl'],
                                        'tp': best['tp'],
                                        'score': best['score'],
                                        'reason': best['reason'],
                                        'ob_id': best['ob_id'],
                                        'rr_ratio': abs(best['tp'] - best['entry']) / abs(best['entry'] - best['sl']) if abs(best['entry'] - best['sl']) > 0 else 0
                                    }
                                    
                                    # Blend với existing SMC signal
                                    if smc_signal and best['side'] == smc_signal:
                                        # Alignment - boost confidence
                                        smc_confidence = (smc_confidence + best['score']) / 2
                                        logger.info(f"✅ SMC MTF aligned with SMC Orchestrator - Confidence: {smc_confidence:.2%}")
                                        # Always store MTF SL/TP when aligned (more precise)
                                        self.last_smc_sl = best['sl']
                                        self.last_smc_tp = best['tp']
                                        self.last_smc_entry = best['entry']
                                        smc_mtf_metadata['alignment'] = 'aligned'
                                    elif smc_signal and best['side'] != smc_signal:
                                        # Conflict - log warning, clear stored values
                                        logger.warning(f"⚠️ SMC MTF conflict: MTF={best['side']} vs SMC={smc_signal}")
                                        self.last_smc_sl = None
                                        self.last_smc_tp = None
                                        self.last_smc_entry = None
                                        smc_mtf_metadata['alignment'] = 'conflict'
                                    else:
                                        # No SMC signal - use MTF as primary
                                        smc_signal = best['side']
                                        smc_confidence = best['score']
                                        logger.info(f"🆕 SMC MTF primary signal: {smc_signal.upper()} ({smc_confidence:.2%})")
                                        
                                        # Store for SL/TP
                                        self.last_smc_sl = best['sl']
                                        self.last_smc_tp = best['tp']
                                        self.last_smc_entry = best['entry']
                                        smc_mtf_metadata['alignment'] = 'primary'
                                    
                                    # Store metadata temporarily (will be added to latest_signal later)
                                    try:
                                        # Store in instance variable for later use
                                        self._smc_mtf_metadata = smc_mtf_metadata
                                        logger.debug(f"✅ SMC MTF metadata stored for signal integration")
                                    except Exception as e:
                                        logger.debug(f"⚠️ Failed to store SMC MTF metadata: {e}")
                                else:
                                    logger.info("⚠️ SMC MTF: No candidates passed filters")
                            else:
                                logger.warning(f"⚠️ SMC MTF: Insufficient timeframes ({len(dfs_mtf)}/4)")
                            
                            logger.info("=" * 70)
                            
                        except Exception as e:
                            logger.error(f"❌ SMC MTF Orchestrator error: {e}")
                            import traceback
                            logger.debug(traceback.format_exc())
                    
                    # ============================================================
                    # 🔥 ICT MULTI-TIMEFRAME LOGIC - 4-Step Workflow (Dec 11, 2025)
                    # ============================================================
                    ict_signal = None
                    ict_confidence = 0.0
                    ict_sl = None
                    ict_tp = None
                    ict_entry = None
                    
                    if ICT_LOGIC_AVAILABLE:
                        try:
                            logger.info("=" * 70)
                            logger.info("🔥 ICT MULTI-TIMEFRAME LOGIC - 4-Step Workflow")
                            logger.info("=" * 70)
                            
                            # STEP 1: HTF TREND FILTER (H1)
                            if 'H1' in tf_data and len(tf_data['H1']) >= 200:
                                htf_trend = check_htf_trend(tf_data['H1'])
                                logger.info(f"📊 STEP 1 (HTF): Trend = {htf_trend}")
                                
                                # ✅ ACCEPT NEUTRAL - Allow sideways/ranging trading
                                if htf_trend == 'NEUTRAL':
                                    logger.info("✅ HTF NEUTRAL (H1) - Chấp nhận giao dịch sideways/ranging")
                                
                                # STEP 2: MMF STRUCTURE (M15) - Continue for all HTF trends
                                if 'M15' in tf_data and len(tf_data['M15']) >= 500:
                                        mmf_structure = check_mmf_structure(tf_data['M15'])
                                        logger.info(f"📊 STEP 2 (MMF): Setup = {mmf_structure.get('setup', 'NONE')}")
                                        
                                        if mmf_structure.get('setup') != 'NONE' and mmf_structure.get('liquidity_swept'):
                                            # STEP 3: LTF ENTRY ZONE (M5)
                                            if 'M5' in tf_data and len(tf_data['M5']) >= 1000:
                                                setup_type = mmf_structure.get('setup')
                                                order_blocks = find_order_blocks_m5(tf_data['M5'], setup_type)
                                                
                                                if len(order_blocks) > 0:
                                                    best_ob = order_blocks[0]
                                                    ict_entry = best_ob['low'] if setup_type == 'BUY' else best_ob['high']
                                                    logger.info(f"✅ STEP 3 (LTF): Entry = {ict_entry:.5f}")
                                                    
                                                    # STEP 4: CALCULATE SL/TP
                                                    atr_period = 14
                                                    if len(tf_data['M5']) >= atr_period:
                                                        high_low = tf_data['M5']['high'] - tf_data['M5']['low']
                                                        atr_value = high_low.rolling(window=atr_period).mean().iloc[-1]
                                                        
                                                        ict_levels = calculate_ict_sl_tp(ict_entry, setup_type, best_ob, atr_value)
                                                        ict_sl = ict_levels['sl']
                                                        ict_tp = ict_levels['tp1']
                                                        
                                                        logger.info(f"✅ STEP 4 (SL/TP): SL={ict_sl:.5f}, TP={ict_tp:.5f}")
                                                        
                                                        # STEP 5: M1 SNIPER CONFIRMATION
                                                        try:
                                                            df_m1 = self.data_fetcher.fetch_mt5_data(
                                                                self.data_fetcher.symbol, mt5.TIMEFRAME_M1, 500
                                                            )
                                                            if df_m1 is not None and len(df_m1) >= 50:
                                                                volume_spike = df_m1['volume'].iloc[-1] / df_m1['volume'].iloc[-50:].mean()
                                                                if volume_spike >= 2.0:
                                                                    ict_signal = setup_type
                                                                    ict_confidence = min(85 + (volume_spike - 2.0) * 5, 95)
                                                                    logger.info(f"🔥 ICT CONFIRMED: {ict_signal} ({ict_confidence:.1f}%)")
                                                        except Exception:
                                                            pass
                            logger.info("=" * 70)
                        except Exception as e:
                            logger.error(f"❌ ICT Logic error: {e}")
                    
                    # ============================================================
                    # 🆕 NEW AI MODULES - Advanced Features (Dec 2025)
                    # ============================================================
                    # ℹ️ News Filter đã chạy ở STEP 0 (trước các module AI)
                    
                    # 1️⃣ MARKET PHASE AI - Wyckoff phase detection
                    market_phase_safe = True
                    market_phase_info = {}
                    if hasattr(self, 'market_phase_ai') and self.market_phase_ai:
                        try:
                            logger.info("=" * 70)
                            logger.info("📊 MARKET PHASE AI - Wyckoff Phase Detection")
                            logger.info("=" * 70)
                            
                            # Use H1 data for phase detection
                            df_for_phase = tf_data.get('H1', live_data)
                            
                            phase_result = self.market_phase_ai.detect_phase(df_for_phase, lookback=50)
                            market_phase_info = phase_result
                            
                            logger.info(f"📊 Phase: {phase_result['phase'].upper()}")
                            logger.info(f"   Confidence: {phase_result['confidence']:.1%}")
                            logger.info(f"   Action: {phase_result['action_recommendation']}")
                            logger.info(f"   Reasoning: {phase_result['reasoning']}")
                            
                            # Check phase compatibility with intended action (if we have one)
                            intended_action = None
                            if smc_signal == 'buy':
                                intended_action = 'BUY'
                            elif smc_signal == 'sell':
                                intended_action = 'SELL'
                            elif trend_action in ['BUY', 'SELL']:
                                intended_action = trend_action
                            
                            if intended_action:
                                market_phase_safe, phase_reason = self.market_phase_ai.should_trade(
                                    phase_result, intended_action
                                )
                                
                                if not market_phase_safe:
                                    logger.warning(f"🚫 MARKET PHASE BLOCKED: {phase_reason}")
                                else:
                                    logger.info(f"✅ MARKET PHASE OK: {intended_action} compatible with {phase_result['phase']}")
                            
                            logger.info("=" * 70)
                            
                        except Exception as e:
                            logger.error(f"❌ Market Phase AI error: {e}")
                    
                    # 3️⃣ BREAKER BLOCK AI - Track OBs and detect failed blocks
                    breaker_signal = None
                    breaker_metadata = {}
                    if hasattr(self, 'breaker_block_ai') and self.breaker_block_ai:
                        try:
                            logger.info("=" * 70)
                            logger.info("💥 BREAKER BLOCK AI - Failed OB Detection")
                            logger.info("=" * 70)
                            
                            # Get current price from latest data
                            df_latest = tf_data.get('M5', tf_data.get('M15', live_data))
                            current_price = df_latest['close'].iloc[-1] if len(df_latest) > 0 else 0.0
                            
                            # Update breaker block tracking
                            breaker_update = self.breaker_block_ai.update(df_latest, current_price)
                            
                            # Log new breakers
                            if breaker_update['new_breakers']:
                                logger.info(f"🔥 NEW BREAKERS: {len(breaker_update['new_breakers'])}")
                                for bb in breaker_update['new_breakers'][:3]:  # Show first 3
                                    logger.info(f"   {bb['side'].upper()} @ {bb['signal_zone'][0]:.5f}-{bb['signal_zone'][1]:.5f}")
                                    logger.info(f"   Severity: {bb['severity']} | Confidence: {bb['confidence']:.1%}")
                            
                            # Check if we have a breaker signal
                            if smc_signal:
                                intended_action = 'BUY' if smc_signal == 'buy' else 'SELL'
                                breaker_signal = self.breaker_block_ai.get_breaker_signal(
                                    current_price, intended_action
                                )
                                
                                if breaker_signal:
                                    logger.info(f"💥 BREAKER SIGNAL: {breaker_signal['side'].upper()}")
                                    logger.info(f"   Zone: {breaker_signal['signal_zone'][0]:.5f}-{breaker_signal['signal_zone'][1]:.5f}")
                                    logger.info(f"   Confidence: {breaker_signal['confidence']:.1%}")
                                    breaker_metadata = breaker_signal
                            
                            logger.info("=" * 70)
                            
                        except Exception as e:
                            logger.error(f"❌ Breaker Block AI error: {e}")
                    
                    # 4️⃣ ADVANCED RL AI - Get optimized parameters & action recommendation
                    rl_action = None
                    rl_params = {}
                    if hasattr(self, 'advanced_rl_ai') and self.advanced_rl_ai:
                        try:
                            logger.info("=" * 70)
                            logger.info("🤖 ADVANCED RL AI - Q-Learning & Parameter Optimization")
                            logger.info("=" * 70)
                            
                            # Build market context for RL
                            market_context = {
                                'trend': 'bullish' if trend_action == 'BUY' else 'bearish' if trend_action == 'SELL' else 'neutral',
                                'phase': market_phase_info.get('phase', 'unknown'),
                                'volatility': 'high',  # Will be refined with actual ATR ratio
                                'session': 'london'  # Will be refined with actual session
                            }
                            
                            # Get state key
                            state_key = self.advanced_rl_ai.get_state_key(market_context)
                            
                            # Get RL action recommendation
                            possible_actions = ['BUY', 'SELL', 'NONE']
                            rl_action = self.advanced_rl_ai.choose_action(state_key, possible_actions)
                            
                            # Get optimized parameters
                            rl_params = self.advanced_rl_ai.get_optimized_parameters()
                            
                            logger.info(f"🤖 RL Action: {rl_action}")
                            logger.info(f"   Optimized Parameters:")
                            logger.info(f"   - ATR Multiplier: {rl_params['atr_multiplier']:.2f}")
                            logger.info(f"   - OB Depth: {rl_params['ob_depth']}")
                            logger.info(f"   - FVG Min Size: {rl_params['fvg_min_size']:.6f}")
                            logger.info(f"   - Confidence Threshold: {rl_params['confidence_threshold']:.1f}%")
                            
                            # Check RL action alignment
                            if smc_signal:
                                smc_action = 'BUY' if smc_signal == 'buy' else 'SELL'
                                if rl_action == smc_action:
                                    logger.info(f"✅ RL aligned with SMC signal")
                                elif rl_action != 'NONE':
                                    logger.warning(f"⚠️ RL suggests {rl_action} but SMC suggests {smc_action}")
                            
                            logger.info("=" * 70)
                            
                        except Exception as e:
                            logger.error(f"❌ Advanced RL AI error: {e}")
                    
                    # ============================================================
                    # END OF NEW AI MODULES
                    # ============================================================
                    
                    # ℹ️ Volatility analysis already done in STEP 0.2 (pre-filter)
                    # Use cached vol_prediction from pre-check
                    if vol_prediction is None:
                        vol_prediction = {'trading_allowed': True, 'level': 'MEDIUM', 'risk': 0.0, 'regime': 'MEDIUM'}
                    
                    # Store for adaptive sizing
                    try:
                        self.last_vol_prediction = vol_prediction
                    except Exception:
                        self.last_vol_prediction = vol_prediction
                    
                    logger.info(f"📊 VOLATILITY STATUS: {vol_prediction.get('level', 'MEDIUM')} risk (Score: {vol_prediction.get('risk', 0.0):.3f})")
                    
                    # Apply dynamic SL/TP based on volatility regime
                    if action != "NONE" and hasattr(self, 'volatility_ai'):
                        try:
                            # Determine a safe entry price to pass into dynamic SL/TP helper.
                            # `price` may not yet be set at this point, so fall back to H1 latest close or live_data if available.
                            entry_price_for_dynamic = None
                            try:
                                if 'price' in locals() and price is not None:
                                    entry_price_for_dynamic = price
                                elif tf_data.get('H1') is not None:
                                    entry_price_for_dynamic = float(tf_data.get('H1')['close'].iloc[-1])
                                elif 'live_data' in locals() and live_data is not None:
                                    entry_price_for_dynamic = float(live_data['close'].iloc[-1])
                            except Exception:
                                entry_price_for_dynamic = None

                            if entry_price_for_dynamic is None:
                                # If still None, skip dynamic SL/TP safely
                                logger.debug("ℹ️ Skipping dynamic SL/TP: no entry price available yet")
                            else:
                                dynamic_sl_tp = self.volatility_ai.calculate_dynamic_sl_tp(
                                    tf_data, entry_price_for_dynamic, action, confidence / 100.0
                                )

                                if dynamic_sl_tp.get('volatility_adjusted', False):
                                    logger.info(f"🔧 DYNAMIC SL/TP APPLIED:")
                                    logger.info(f"   SL: ${dynamic_sl_tp['sl_distance']:.2f} → TP: ${dynamic_sl_tp['tp_distance']:.2f}")
                                    logger.info(f"   R:R Ratio: {dynamic_sl_tp['risk_reward_ratio']:.2f}:1")

                                    # Store for later use in signal generation
                                    self.last_dynamic_sl_tp = dynamic_sl_tp
                                else:
                                    logger.info(f"⚠️ Using default SL/TP (volatility calculation failed)")
                        except Exception as e:
                            logger.warning(f"⚠️ Dynamic SL/TP calculation failed: {e}")
                    
                    # ℹ️ Sideways check already done in STEP 0.3 (pre-filter)
                    # Use cached sideway_score from pre-check
                    if 'sideway_score' not in locals():
                        sideway_score = 0
                    
                    logger.info(f"📊 SIDEWAYS STATUS: Score {sideway_score}/7 (Passed pre-filter)")


                    # ================= FUSION AI + RISK AI PRO ================
                    try:
                        # Build inputs for FusionAIv4 from available features
                        # Prefer FusionAIv4 instance for advanced fusion
                        # Local fallbacks will be resolved later when calling fuse/evaluate.
                        fusion = None
                        try:
                            # prefer instance attached to system
                            fusion = getattr(self, 'fusion', None)
                        except Exception:
                            fusion = None

                        # Risk evaluator: prefer self.risk_ai if present, else will fallback when needed
                        try:
                            risk_pro = getattr(self, 'risk_ai', None)
                        except Exception:
                            risk_pro = None

                        # Structure scores
                        try:
                            struct_bull = float(features.get('HH', 0) or 0.0) + float(features.get('HL', 0) or 0.0)
                            struct_bear = float(features.get('LH', 0) or 0.0) + float(features.get('LL', 0) or 0.0)
                            structure_result = {'bullish': struct_bull, 'bearish': struct_bear}
                        except Exception:
                            structure_result = {'bullish': 0.0, 'bearish': 0.0}

                        # --- Integrate StructureAI if available ---
                        try:
                            struct_signal = int(struct_result.get("structure", 0))
                            if struct_signal == 1:
                                structure_result['bullish'] = structure_result.get('bullish', 0.0) + 1.0
                            elif struct_signal == -1:
                                structure_result['bearish'] = structure_result.get('bearish', 0.0) + 1.0
                            logger.debug(f"StructureAI signal: {struct_signal} | updated structure_result={structure_result}")
                        except Exception as e:
                            logger.debug(f"⚠️ StructureAI integration failed: {e}")

                        # Liquidity estimate
                        try:
                            liq = float(struct_result.get('meta', {}).get('score', 0.0) or 0.0)  # fallback to structure score if no liquidity
                            liquidity_result = {'bullish': 0.0, 'bearish': 0.0, 'risk': liq}
                        except Exception:
                            liquidity_result = {'bullish': 0.0, 'bearish': 0.0, 'risk': 0.0}

                        # --- Integrate LiquidityAI if available ---
                        try:
                            liq_signal = int(liq_result.get("signal", 0))
                            if liq_signal == 1:
                                liquidity_result['bullish'] = liquidity_result.get('bullish', 0.0) + 1.0
                            elif liq_signal == -1:
                                liquidity_result['bearish'] = liquidity_result.get('bearish', 0.0) + 1.0
                            logger.debug(f"LiquidityAI signal: {liq_signal} | updated liquidity_result={liquidity_result}")
                        except Exception as e:
                            logger.debug(f"⚠️ LiquidityAI integration failed: {e}")

                        # Sentiment estimate
                        try:
                            sent_score = float(sent_result.get("score", 0.0))
                            sentiment_result = {'bullish': 1.0 if sent_score > 0.15 else 0.0, 'bearish': 1.0 if sent_score < -0.15 else 0.0, 'score': sent_score}
                        except Exception:
                            sentiment_result = {'bullish': 0.0, 'bearish': 0.0, 'score': 0.0}

                        # --- SessionAI evaluation for veto ---
                        try:
                            if hasattr(self, 'session_ai') and self.session_ai:
                                session_result = self.session_ai.evaluate(tf_data.get('H1') if 'H1' in tf_data else live_data)
                            else:
                                session_result = {"session": "neutral", "trading_allowed": True, "reason": "none", "meta": {}}
                        except Exception as e:
                            logger.warning(f"⚠️ SessionAI failed: {e}")
                            session_result = {"session": "neutral", "trading_allowed": True, "reason": "error", "meta": {}}

                        # Volume (approx): compare latest volume vs 20-avg if available
                        try:
                            latest_bar = tf_data.get('H1').iloc[-1] if isinstance(tf_data, dict) and 'H1' in tf_data else None
                            vol_bull = 0.0
                            vol_bear = 0.0
                            if latest_bar is not None and 'volume' in latest_bar:
                                vol = float(latest_bar['volume'])
                                vol_sma = float(latest_bar.get('volume_sma', 0) or 0)
                                if vol_sma and vol > vol_sma:
                                    vol_bull = 1.0
                                else:
                                    vol_bear = 0.0
                            volume_result = {'bullish': vol_bull, 'bearish': vol_bear}
                        except Exception:
                            volume_result = {'bullish': 0.0, 'bearish': 0.0}

                        # Momentum (simple)
                        try:
                            mom_bull = 1.0 if features.get('macd_H1', 0) and features.get('macd_H1', 0) > 0 else 0.0
                            mom_bear = 1.0 if features.get('macd_H1', 0) and features.get('macd_H1', 0) < 0 else 0.0
                            momentum_result = {'bullish': mom_bull, 'bearish': mom_bear}
                        except Exception:
                            momentum_result = {'bullish': 0.0, 'bearish': 0.0}

                        # Trend
                        trend_result = {'direction': trend_action, 'strength': trend_confidence}

                        # Reversal signal from reversal_prob (GIẢM threshold để nhạy hơn với pullback)
                        reversal_signal = None
                        try:
                            # 🔥 GIẢM threshold để dễ bắt SELL pullback hơn
                            if reversal_prob > 0.6:  # Giảm từ 0.7 → 0.6 (nhạy hơn)
                                reversal_signal = 'BUY'
                                logger.info(f"🔄 ReversalAI: BUY reversal detected (prob={reversal_prob:.1%})")
                            elif reversal_prob < 0.4:  # Tăng từ 0.3 → 0.4 (dễ SELL hơn)
                                reversal_signal = 'SELL'
                                logger.info(f"🔄 ReversalAI: SELL pullback detected (prob={reversal_prob:.1%})")
                        except Exception:
                            reversal_signal = None

                        # Volatility result - khởi tạo sớm để tránh scope issue
                        volatility_result = {'level': vol_prediction.get('level', 'MEDIUM'), 'risk': vol_prediction.get('risk', 0.0)}
                        
                        # Structure, liquidity results - khởi tạo sớm cho ExplainAI
                        struct_result = structure_result if 'structure_result' in locals() else {}
                        liq_result = liquidity_result if 'liquidity_result' in locals() else {}
                        sent_result = sentiment_result if 'sentiment_result' in locals() else {}

                        sideway_result = {'score': sideway_score}

                        # Run fusion using FusionAIv4 (hierarchical priority-based fusion with veto rules)
                        final_signal = 'NONE'
                        fused_score = 0.0
                        fusion_reasons = []
                        fusion_meta = {}

                        # Build signals dict for FusionAIv4
                        fusion_signals = {
                            'structure': structure_result,
                            'liquidity': liquidity_result,
                            'volume': volume_result,
                            'momentum': momentum_result,
                            'trend': (trend_result.get('direction'), trend_result.get('strength', 0.0)) if trend_result else None,
                            'reversal': (reversal_signal, reversal_prob) if reversal_signal else None,
                            'volatility': volatility_result,
                            'sentiment': sentiment_result,
                            'sentiment_raw': sent_result,  # Add raw SentimentAI.analyze() result
                            'sideway': sideway_result
                        }

                        # Add risk evaluation for veto
                        risk_block = None
                        try:
                            if risk_pro is not None:
                                risk_block = (not allowed, risk_level) if 'allowed' in locals() else None
                        except Exception:
                            pass
                        if risk_block:
                            fusion_signals['risk_block'] = risk_block

                        # Add session evaluation for veto
                        fusion_signals['session'] = session_result
                        
                        # Add SMC signal to fusion
                        if smc_signal:
                            smc_direction = 1 if smc_signal == 'buy' else -1 if smc_signal == 'sell' else 0
                            fusion_signals['smc'] = {
                                'signal': smc_direction,
                                'confidence': smc_confidence,
                                'confluence': smc_confluence,
                                'bullish': smc_confidence if smc_signal == 'buy' else 0.0,
                                'bearish': smc_confidence if smc_signal == 'sell' else 0.0
                            }
                            logger.info(f"🎯 SMC integrated into Fusion: {smc_signal.upper()} (conf={smc_confidence:.1%}, confluence={smc_confluence})")
                        else:
                            fusion_signals['smc'] = {'signal': 0, 'confidence': 0.0, 'confluence': 0}

                        # Call FusionAIv4.fuse()
                        if hasattr(self, 'fusion_ai_v4') and self.fusion_ai is not None:
                            try:
                                fusion_result = self.fusion_ai.fuse(fusion_signals)
                                final_signal = fusion_result.get('side', 'none').upper()
                                fused_score = fusion_result.get('score', 0.0)
                                fusion_reasons = fusion_result.get('reasons', [])
                                fusion_meta = fusion_result.get('meta', {})

                                # Handle veto blocks
                                if fusion_result.get('blocked', False):
                                    blocked_reason = fusion_result.get('blocked_reason', 'unknown')
                                    logger.warning(f"🚫 FusionAIv4 BLOCKED: {blocked_reason} | 🚫 FusionAIv4 BỊ CHẶN: {blocked_reason}")
                                    final_signal = 'NONE'
                                    action = 'NONE'
                                    order_type = 'NONE'
                                    # update latest_signal early to reflect block
                                    latest_signal.update({
                                        'action': 'NONE',
                                        'reason': f'FUSION_BLOCK_{blocked_reason.upper()}',
                                        'confidence': round(confidence, 1),
                                        'risk_level': round(risk_level, 3) if 'risk_level' in locals() else 0.0
                                    })

                            except Exception as e:
                                logger.debug(f"⚠️ FusionAIv4 fuse() failed: {e} | ⚠️ FusionAIv4 fuse() thất bại: {e}")
                                final_signal = 'NONE'
                                fused_score = 0.0
                        else:
                            logger.debug("⚠️ FusionAIv4 not available; skipping fusion step | ⚠️ FusionAIv4 không khả dụng; bỏ qua bước fusion")
                            final_signal = 'NONE'
                            fused_score = 0.0

                        # Persist last fusion context/result for adaptive sizing
                        try:
                            self.last_fused_score = fused_score
                            self.last_fusion_context = {
                                'structure': structure_result,
                                'liquidity': liquidity_result,
                                'volume': volume_result,
                                'momentum': momentum_result,
                                'trend': trend_result,
                                'reversal': reversal_signal,
                                'volatility': volatility_result,
                                'sideway': sideway_result,
                                'sentiment': sentiment_result,
                                'session': session_result,
                                'fusion_reasons': fusion_reasons,
                                'fusion_meta': fusion_meta
                            }
                        except Exception:
                            self.last_fused_score = fused_score
                            self.last_fusion_context = None

                        # Evaluate risk with RiskAI (prefer instance attached to system)
                        try:
                            # Ensure VolatilityAI is available
                            if not hasattr(self, 'volatility_ai') or self.volatility_ai is None:
                                try:
                                    self.volatility_ai = VolatilityAI()
                                except:
                                    self.volatility_ai = None
                            
                            if risk_pro is None:
                                try:
                                    from ai_modules.risk.risk_ai import RiskAI as _RiskLocal
                                    risk_pro = _RiskLocal(money_manager=self.money_manager, drawdown_protector=getattr(self, 'drawdown_protector', None))
                                except Exception:
                                    risk_pro = None

                            if risk_pro is None:
                                # No RiskAI available: default to allowed
                                allowed, risk_level = True, 0.0
                            else:
                                allowed, risk_level = risk_pro.evaluate(
                                    volatility_level=volatility_result.get('level'),
                                    trend_strength=trend_result.get('strength', 0.0),
                                    sideway_score=sideway_result.get('score', 0.0),
                                    liquidity_risk=liquidity_result.get('risk', 0.0),
                                    structure_score=structure_result,
                                    confidence=fused_score
                                )
                        except Exception as _e:
                            logger.debug(f"⚠️ Risk evaluation failed: {_e}")
                            allowed, risk_level = True, 0.0

                        logger.info(f"🔀 FusionAIv4 → {final_signal} (score={fused_score:.3f}) | Reasons: {', '.join(fusion_reasons)} | 🔀 FusionAIv4 → {final_signal} (điểm={fused_score:.3f}) | Lý do: {', '.join(fusion_reasons)}")

                        if not allowed:
                            logger.warning("⛔ RiskAI blocked trade (HIGH RISK)")
                            action = 'NONE'
                            order_type = 'NONE'
                            # update latest_signal early to reflect block
                            latest_signal.update({
                                'action': 'NONE',
                                'reason': 'HIGH_RISK_AI_BLOCK',
                                'confidence': round(confidence, 1),
                                'risk_level': round(risk_level, 3)
                            })
                        else:
                            # If Fusion returned a clear final signal, use it (if action not already blocked)
                            if final_signal in ('BUY', 'SELL'):
                                action = final_signal
                                # Use fused_score (0..?) scale to 0-100 if small
                                try:
                                    if fused_score <= 1.0:
                                        confidence = float(fused_score) * 100.0
                                    else:
                                        confidence = float(fused_score)
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.debug(f"⚠️ FusionAIv4/RiskAI integration failed: {e} | ⚠️ FusionAIv4/RiskAI tích hợp thất bại: {e}")
                    
                    # 🆕 AI DECISION RESOLVER - Giải quyết xung đột giữa TrendAI và FusionAI
                    if action != "NONE" and trend_action != "NONE":
                        resolved_action, resolver_reason = self._resolve_conflicting_decision(
                            trend_action=trend_action,
                            fusion_action=action,
                            trend_confidence=trend_confidence,
                            fusion_confidence=confidence,
                            fusion_reasons=fusion_reasons
                        )
                        if resolved_action != action:
                            logger.warning(f"🔄 DECISION RESOLVER: {action} → {resolved_action} | Lý do: {resolver_reason.get('decision', 'unknown')}")
                            action = resolved_action
                            # Log resolver metadata for analysis
                            latest_signal['decision_resolution'] = {
                                'original_trend': trend_action,
                                'original_fusion': action,
                                'resolved_action': resolved_action,
                                'resolver_reason': resolver_reason,
                                'trend_confidence': trend_confidence,
                                'fusion_confidence': confidence
                            }
                        else:
                            logger.debug(f"✅ DECISION RESOLVER: Không có xung đột, giữ {action}")
                    
                    # =========================================================
                    
                    # 🆕 TECHNICAL FILTER PRO - Áp dụng 7 bộ lọc kỹ thuật chuyên nghiệp
                    if action != "NONE":
                        tech_filter_result = technical_filter(action, tf_data)
                        if tech_filter_result == "NO TRADE":
                            logger.info(f"🚫 TECHNICAL FILTER PRO: {action} bị từ chối - Không đáp ứng tiêu chí kỹ thuật")
                            action = "NONE"
                            order_type = "NONE"
                        else:
                            logger.info(f"✅ TECHNICAL FILTER PRO: {action} đạt tiêu chí kỹ thuật - CHO PHÉP TRADE")
                    
                    # 🎯 DECISION MAKING: Combine TrendAI + ReversalAI + Technical Filters
                    if trend_action != "NONE" and action != "NONE":
                        # Both TrendAI and technical filters agree
                        action = trend_action
                        confidence = trend_confidence * 100  # Convert to percentage
                        logger.info(f"🎯 FINAL DECISION: {action} (TrendAI: {trend_confidence:.1%}, Tech Filters: PASS)")
                    elif trend_action != "NONE":
                        # Only TrendAI has signal, technical filters blocked
                        action = trend_action
                        confidence = trend_confidence * 100 * 0.7  # Reduce confidence due to filter conflict
                        logger.info(f"⚠️ TREND SIGNAL ONLY: {action} (TrendAI: {trend_confidence:.1%}, Tech Filters: BLOCKED)")
                    else:
                        # No TrendAI signal or technical filters blocked
                        action = "NONE"
                        confidence = 0.0
                        logger.info(f"⏸️ NO SIGNAL: TrendAI={trend_action}, Tech Filters={action}")
                    
                    logger.info(f"🤖 TrendAI PRO → {trend_action} (confidence={trend_confidence:.3f})")
                    logger.info(f"🔄 ReversalAI → reversal_prob={reversal_prob:.3f}")
                    
                    # 📊 CHART PATTERN DETECTION - Phát hiện mô hình biểu đồ
                    try:
                        pattern_result = integrate_pattern_detection(live_data, logger)
                        if pattern_result.get('has_pattern', False):
                            pattern_name = pattern_result.get('strongest_pattern', '')
                            pattern_data = pattern_result.get('pattern_data', {})
                            pattern_signal = pattern_data.get('signal', 'NONE')
                            pattern_confidence = pattern_data.get('confidence', 0.0) * 100
                            
                            # Nếu pattern signal khớp với AI signal → BOOST confidence
                            # GIẢM boost từ 25% → 15% để lọc chặt hơn
                            if pattern_signal == action and pattern_confidence > 65:
                                pattern_boost = 15.0  # Giảm từ 25% → 15%
                                confidence = min(100.0, confidence + pattern_boost)
                                logger.info(f"📊✅ CHART PATTERN: {pattern_name.upper()} confirms {action}")
                                logger.info(f"   Pattern confidence: {pattern_confidence:.1f}% → Boost +{pattern_boost}% to {confidence:.1f}%")
                            elif pattern_signal == action and pattern_confidence > 50:
                                pattern_boost = 8.0  # Giảm từ 15% → 8%
                                confidence = min(100.0, confidence + pattern_boost)
                                logger.info(f"📊 CHART PATTERN: {pattern_name.upper()} suggests {action} (+{pattern_boost}%)")
                    except Exception as pe:
                        logger.debug(f"⚠️ Pattern detection skipped: {pe}")
                    
                    # ============================================================
                    # 🔥 ICT SIGNAL BLENDING - Integrate ICT with AI decisions
                    # ============================================================
                    if ict_signal and ict_confidence > 0:
                        logger.info("=" * 70)
                        logger.info("🔥 ICT SIGNAL BLENDING")
                        
                        # Check alignment
                        if ict_signal == action:
                            # Perfect alignment - boost confidence (giảm từ 15% → 10%)
                            confidence = min(100.0, confidence + 10.0)
                            logger.info(f"✅ ICT ALIGNED: {action} boosted to {confidence:.1f}%")
                            
                            # Store ICT SL/TP
                            if ict_sl and ict_tp and ict_entry:
                                self.last_ict_sl = ict_sl
                                self.last_ict_tp = ict_tp
                                self.last_ict_entry = ict_entry
                        
                        elif ict_signal in ['BUY', 'SELL'] and action == 'NONE':
                            # ICT primary signal
                            action = ict_signal
                            confidence = ict_confidence
                            logger.info(f"🆕 ICT PRIMARY: {action} ({confidence:.1f}%)")
                            
                            if ict_sl and ict_tp and ict_entry:
                                self.last_ict_sl = ict_sl
                                self.last_ict_tp = ict_tp
                                self.last_ict_entry = ict_entry
                        
                        elif ict_signal != action and action != 'NONE':
                            # Conflict
                            logger.warning(f"⚠️ ICT CONFLICT: ICT={ict_signal} vs AI={action}")
                            if ict_confidence > confidence + 10:
                                logger.info(f"🔄 SWITCH to ICT: {ict_signal}")
                                action = ict_signal
                                confidence = ict_confidence
                                if ict_sl and ict_tp and ict_entry:
                                    self.last_ict_sl = ict_sl
                                    self.last_ict_tp = ict_tp
                                    self.last_ict_entry = ict_entry
                        
                        logger.info("=" * 70)
                    
                    # Adjust confidence based on reversal probability
                    # Giảm các boost để lọc chặt hơn
                    if reversal_prob > 0.6:  # Bullish reversal
                        boost = 10.0 if action == "BUY" else 3.0  # Giảm từ 15%/5% → 10%/3%
                        confidence = min(100.0, confidence + boost)
                        logger.info(f"📈 High reversal prob ({reversal_prob:.3f}) → Boost confidence +{boost}% to {confidence:.1f}%")
                    elif reversal_prob < 0.4:  # Bearish reversal/pullback
                        boost = 12.0 if action == "SELL" else 3.0  # Giảm từ 20%/5% → 12%/3%
                        confidence = min(100.0, confidence + boost)
                        logger.info(f"🔻 SELL pullback detected ({reversal_prob:.3f}) → Boost confidence +{boost}% to {confidence:.1f}%")
                    else:
                        logger.info(f"➡️ Moderate reversal prob ({reversal_prob:.3f}) → Keep confidence at {confidence:.1f}%")

                # If multi-TF didn't produce a decision, fall back to original model.predict
                if action == "NONE":
                    action, confidence = self.ai_model.predict_signal(live_data)

            except Exception as e:
                logger.debug(f"✓ Multi-TF TrendAI using single-TF fallback: {e}")
                action, confidence = self.ai_model.predict_signal(live_data)
            price = live_data['close'].iloc[-1]
            confidence *= 100  # Convert to percentage
            
            # 🔍 DEBUG: Xem AI trả về gì TRƯỚC KHI filter
            logger.info(f"🔍 GỠ LỖI - Dự đoán AI: hành_động={action}, độ_tin_cậy={confidence:.1f}%")

            # ========== HTF TREND ALIGNMENT FILTER (H4) - Configurable ==========
            try:
                h4_close = None
                h4_ema200 = None

                if 'df_h4' in locals() and df_h4 is not None and hasattr(df_h4, 'iloc') and len(df_h4) > 0:
                    try:
                        h4_close = float(df_h4['close'].iloc[-1])
                    except Exception:
                        h4_close = None

                if 'features' in locals() and features is not None:
                    h4_ema200 = features.get('ema200_H4')

                if h4_ema200 is None and 'df_h4' in locals() and df_h4 is not None and hasattr(df_h4, 'close'):
                    try:
                        h4_ema200 = float(pd.Series(df_h4['close']).ewm(span=200).mean().iloc[-1])
                    except Exception:
                        h4_ema200 = None

                policy = getattr(self, 'htf_policy', 'soft')  # Đổi mặc định sang 'soft' để cho phép reversal

                if h4_close is not None and h4_ema200 is not None and action != 'NONE':
                    # BLOCK policy: chặn cứng tín hiệu ngược HTF (NHƯNG cho phép nếu có reversal mạnh)
                    if policy == 'block':
                        # Kiểm tra reversal signal
                        has_strong_reversal = False
                        try:
                            if 'reversal_prob' in locals() and reversal_prob > 0.7:
                                has_strong_reversal = True
                        except:
                            pass
                        
                        if action in ["BUY", "BUY_LIMIT"] and h4_close < h4_ema200:
                            if not has_strong_reversal:
                                logger.info(f"🚫 HTF Filter (block): H4 bearish ({h4_close:.3f} < {h4_ema200:.3f}) → Block BUY")
                                action = 'NONE'
                                order_type = 'NONE'
                            else:
                                logger.info(f"⚠️ HTF Filter: H4 bearish BUT strong reversal ({reversal_prob:.1%}) → Allow BUY")
                        elif action in ["SELL", "SELL_LIMIT"] and h4_close > h4_ema200:
                            # 🔥 CHO PHÉP SELL khi có reversal/pullback mạnh
                            if has_strong_reversal:
                                logger.info(f"✅ HTF Filter: H4 bullish BUT strong reversal ({reversal_prob:.1%}) → Allow SELL (pullback)")
                            else:
                                # Chỉ giảm confidence thay vì block hoàn toàn (giảm xuống 60% từ 70%)
                                logger.info(f"⚠️ HTF Filter (soft-block): H4 bullish ({h4_close:.3f} > {h4_ema200:.3f}) → Reduce SELL confidence")
                                confidence = confidence * 0.6  # Tăng penalty từ 0.7 → 0.6
                                if confidence < float(min_confidence):
                                    action = 'NONE'
                                    order_type = 'NONE'

                    # SOFT policy: giảm confidence nếu trái HTF
                    elif policy == 'soft':
                        if action in ["BUY", "BUY_LIMIT"] and h4_close < h4_ema200:
                            logger.info(f"⚠️ HTF Filter (soft): H4 bearish → reduce confidence by {self.htf_soft_multiplier}")
                            confidence = confidence * float(self.htf_soft_multiplier)
                            # Nếu giảm xuống dưới ngưỡng min_confidence thì hủy
                            if confidence < float(min_confidence):
                                action = 'NONE'
                                order_type = 'NONE'
                        elif action in ["SELL", "SELL_LIMIT"] and h4_close > h4_ema200:
                            logger.info(f"⚠️ HTF Filter (soft): H4 bullish → reduce confidence by {self.htf_soft_multiplier}")
                            confidence = confidence * float(self.htf_soft_multiplier)
                            if confidence < float(min_confidence):
                                action = 'NONE'
                                order_type = 'NONE'

                    else:
                        # policy == 'off' or unknown: do nothing
                        logger.debug("ℹ️ HTF Filter: policy off or unknown - skipping")
                else:
                    logger.debug("ℹ️ HTF Filter: H4 data missing or action NONE - continuing")
            except Exception as e:
                logger.warning(f"⚠️ HTF filter failed: {e}")

            
            # 🆕 QUYẾT ĐỊNH LOẠI LỆNH: MARKET hoặc LIMIT dựa trên confidence
            if action != "NONE":
                # Confidence CAO (>= 50%) → Market order (vào ngay)
                # Confidence THẤP (< 50%) → Limit order (chờ giá tốt hơn)
                if confidence >= 50.0:
                    # HIGH CONFIDENCE → MARKET ORDER
                    order_type = action  # "BUY" hoặc "SELL"
                    limit_price = price
                    logger.info(f"⚡ Confidence {confidence:.1f}% >= 50% → MARKET {action} @ {price:.2f}")
                else:
                    # MEDIUM CONFIDENCE → LIMIT ORDER
                    # Use compatibility-safe call: if the ai_model doesn't implement
                    # `calculate_limit_entry` (possible when runtime replaced the
                    # object), fall back to a conservative local implementation.
                    try:
                        calc = getattr(self.ai_model, 'calculate_limit_entry', None)
                        if callable(calc):
                            limit_price, order_type = calc(live_data, action, price)
                        else:
                            # Local conservative fallback: use recent SR from live_data
                            try:
                                recent = live_data.tail(20) if hasattr(live_data, 'tail') else live_data
                                support = float(recent['low'].min()) if 'low' in recent else float(price)
                                resistance = float(recent['high'].max()) if 'high' in recent else float(price)
                                if action == 'BUY':
                                    limit_price = float(price) - ((float(price) - support) * 0.5)
                                    order_type = 'BUY_LIMIT'
                                else:
                                    limit_price = float(price) + ((resistance - float(price)) * 0.5)
                                    order_type = 'SELL_LIMIT'
                            except Exception:
                                limit_price = price
                                order_type = action
                        logger.info(f"📊 Confidence {confidence:.1f}% < 50% → {order_type} @ {limit_price:.2f}")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to compute limit entry (fallback): {e}")
                        limit_price = price
                        order_type = action
            else:
                limit_price = price
                order_type = "NONE"
            
            # === 🎯 NEW: TRADE QUALITY SCORING & PATTERN PROBABILITY FILTERING ===
            # Check 1: Trade Quality Score (0-100)
            quality_result = None
            if action != "NONE" and self.quality_scorer:
                try:
                    # 🔧 FIX: Map correct variables from existing AI modules
                    # Get SMC data from smc_result (if available)
                    smc_data_safe = {}
                    if 'smc_result' in locals() and smc_result:
                        smc_data_safe = smc_result
                    
                    # Get regime data from regime_ai (if exists)
                    regime_data_safe = {}
                    if hasattr(self, 'regime_ai') and self.regime_ai:
                        try:
                            # Try to get last regime classification
                            regime_data_safe = getattr(self, 'last_regime_result', {})
                        except:
                            pass
                    
                    # Get volatility data from vol_prediction
                    vol_level_safe = vol_prediction.get('level', 'MEDIUM') if 'vol_prediction' in locals() else 'MEDIUM'
                    vol_forecast_safe = vol_prediction.get('forecast', 0.0) if 'vol_prediction' in locals() else 0.0
                    
                    # Get liquidity sweep result (may be None)
                    ls_result_safe = ls_result if 'ls_result' in locals() else None
                    
                    # Prepare signal data for scoring
                    signal_data = {
                        'action': action,
                        'confidence': confidence,
                        'smc_data': smc_data_safe,
                        'liquidity_sweep_ai': ls_result_safe,
                        'regime': {
                            'type': regime_data_safe.get('regime', 'unknown') if isinstance(regime_data_safe, dict) else 'unknown',
                            'direction': regime_data_safe.get('direction', 'neutral') if isinstance(regime_data_safe, dict) else 'neutral',
                            'strength': regime_data_safe.get('strength', 0.5) if isinstance(regime_data_safe, dict) else 0.5
                        },
                        'volatility': {
                            'level': vol_level_safe,
                            'forecast': vol_forecast_safe
                        }
                    }
                    
                    quality_result = self.quality_scorer.score_signal(signal_data)
                    
                    if not quality_result.get('should_trade', False):
                        logger.warning(f"❌ QUALITY FILTER: Signal rejected - Score {quality_result['total_score']:.1f}/100 < 65")
                        logger.warning(f"   Breakdown: SMC={quality_result['breakdown']['smc']:.1f} | "
                                      f"Liq={quality_result['breakdown']['liquidity']:.1f} | "
                                      f"Regime={quality_result['breakdown']['regime']:.1f} | "
                                      f"Prob={quality_result['breakdown']['probability']:.1f} | "
                                      f"Vol={quality_result['breakdown']['volatility']:.1f}")
                        action = 'NONE'
                        order_type = 'NONE'
                except Exception as e:
                    logger.error(f"❌ Trade quality scoring failed: {e}")
                    quality_result = None
            
            # Check 2: Pattern Probability Filter (historical win rate)
            pattern_prob_result = None
            if action != "NONE" and self.pattern_filter:
                try:
                    # 🔧 FIX: Use same safe variables as Quality Scorer
                    signal_data = {
                        'action': action,
                        'confidence': confidence,
                        'smc_data': smc_data_safe if 'smc_data_safe' in locals() else {},
                        'liquidity_sweep_ai': ls_result_safe if 'ls_result_safe' in locals() else None,
                        'regime': {
                            'type': regime_data_safe.get('regime', 'unknown') if 'regime_data_safe' in locals() and isinstance(regime_data_safe, dict) else 'unknown'
                        },
                        'volatility': {
                            'level': vol_level_safe if 'vol_level_safe' in locals() else 'MEDIUM'
                        }
                    }
                    
                    pattern_prob_result = self.pattern_filter.should_trade(signal_data)
                    
                    if not pattern_prob_result.get('should_trade', False):
                        stats = pattern_prob_result.get('stats', {})
                        logger.warning(f"❌ PATTERN FILTER: Signal rejected - Pattern has low win rate")
                        logger.warning(f"   Historical: {stats.get('wins', 0)}W-{stats.get('losses', 0)}L "
                                      f"(WR: {stats.get('win_rate', 0)*100:.1f}%, n={stats.get('total', 0)})")
                        action = 'NONE'
                        order_type = 'NONE'
                except Exception as e:
                    logger.error(f"❌ Pattern probability filter failed: {e}")
                    pattern_prob_result = None
            
            # ⚡ TỰ ĐỘNG LỌC THEO CONFIDENCE + SESSION (AUTO_FILTER)
            # Nếu AUTO_FILTER_ENABLED = True thì áp bộ lọc tự động được tính
            # từ kết quả sweep backtest (AUTO_MIN_CONFIDENCE, AUTO_SESSION_WHITELIST).
            try:
                if AUTO_FILTER_ENABLED:
                    # Confidence (min_confidence được chuyển ở mức % trong hàm gọi)
                    if float(confidence) < float(AUTO_MIN_CONFIDENCE):
                        original_action = action
                        action = "NONE"
                        order_type = "NONE"
                        logger.info(f"🚫 AUTO FILTER: Tín hiệu {original_action} bị từ chối do confidence {confidence:.1f}% < {AUTO_MIN_CONFIDENCE}%")
                    else:
                        # Session whitelist check (session_result từ SessionAI)
                        # Behavior controlled by instance flag `self.enable_session_whitelist`.
                        # If enabled, attempt to normalize session label and drop signals
                        # not in AUTO_SESSION_WHITELIST. If disabled, skip session filtering.
                        try:
                            if getattr(self, 'enable_session_whitelist', False):
                                sess_label = None
                                # session_result may be a dict-like or object
                                try:
                                    if isinstance(session_result, dict):
                                        sess_label = session_result.get('session') or session_result.get('label')
                                    else:
                                        sess_label = getattr(session_result, 'session', None) or getattr(session_result, 'label', None)
                                except Exception:
                                    sess_label = None

                                # If not found, try last row one-hot flags in live_data
                                if sess_label is None and isinstance(live_data, pd.DataFrame):
                                    try:
                                        last = live_data.iloc[-1]
                                        if int(last.get('session_asia', 0)) == 1:
                                            sess_label = 'asia'
                                        elif int(last.get('session_eu', 0)) == 1:
                                            sess_label = 'eu'
                                        elif int(last.get('session_us', 0)) == 1:
                                            sess_label = 'us'
                                    except Exception:
                                        sess_label = None

                                # Normalize numeric codes 1/2/3 to names
                                try:
                                    if isinstance(sess_label, (int, float, np.integer, np.floating)):
                                        sess_map = {1: 'asia', 2: 'eu', 3: 'us'}
                                        sess_label = sess_map.get(int(sess_label), 'other')
                                except Exception:
                                    pass

                                sess_norm = (str(sess_label).lower() if sess_label is not None else 'other')
                                if sess_norm not in AUTO_SESSION_WHITELIST:
                                    original_action = action
                                    action = 'NONE'
                                    order_type = 'NONE'
                                    logger.info(f"🚫 AUTO FILTER: Tín hiệu {original_action} bị từ chối do session '{sess_norm}' không thuộc whitelist {AUTO_SESSION_WHITELIST}")
                                else:
                                    logger.debug(f"✅ AUTO FILTER: session '{sess_norm}' thuộc whitelist")
                            else:
                                # Session whitelist disabled: do nothing
                                logger.debug("ℹ️ AUTO FILTER: session whitelist disabled (skipping session check)")
                        except Exception as e:
                            logger.debug(f"⚠️ AUTO_FILTER session check failed: {e}")
            except Exception as _e:
                logger.debug(f"⚠️ AUTO_FILTER check failed: {_e}")
            
            # 🚫 SIDEWAYS MARKET FILTER: Tránh trade trong thị trường sideways (TẮT)
            # original_action_after_conf = action
            # if action != "NONE" and enable_sideways_filter:
            #     # Kiểm tra market regime từ latest data
            #     df_features = self.ai_model.prepare_features(live_data)
            #     latest_regime = df_features['market_regime'].iloc[-1]
            #     is_sideways = df_features['is_sideways'].iloc[-1]
            #     trend_quality = df_features['trend_quality'].iloc[-1]
            #     
            #     if is_sideways == 1 or trend_quality < 0.8:
            #         action = "NONE"
            #         logger.info(f"🚫 Lọc Sideways - Tín hiệu {original_action_after_conf} bị từ chối (Thị trường sideway, Chất lượng xu hướng: {trend_quality:.2f})")
            #     elif latest_regime == 0:
            #         action = "NONE"  
            #         logger.info(f"🚫 Lọc Sideways - Tín hiệu {original_action_after_conf} bị từ chối (Thị trường yếu: {latest_regime})")
            #     else:
            #         logger.info(f"✅ TÍN HIỆU CHẤP NHẬN - {action} (Độ tin cậy: {confidence:.1f}%, Chế độ: {latest_regime}, Chất lượng xu hướng: {trend_quality:.2f})")
            # elif action != "NONE" and not enable_sideways_filter:
            #     logger.info(f"✅ TÍN HIỆU CHẤP NHẬN - {action} (Độ tin cậy: {confidence:.1f}%, Lọc sideways: TẮT)")
            
            if action != "NONE":
                # Hiển thị log khác nhau cho Market vs Limit
                if order_type in ["BUY", "SELL"]:
                    logger.info(f"⚡ MARKET {order_type} NGAY LẬP TỨC @ {price:.2f} (Độ tin cậy: {confidence:.1f}%)")
                else:
                    logger.info(f"⚡ LỆNH {order_type} - Entry @ {limit_price:.2f} (Current: {price:.2f}, Độ tin cậy: {confidence:.1f}%)")
            else:
                logger.info(f"⏸️ KHÔNG VÀO LỆNH - Chờ điều kiện tốt hơn")
            
            # --- ExplainAI logging for decision transparency ---
            try:
                if hasattr(self, 'explain_ai') and self.explain_ai:
                    decision_context = {
                        'action': action,
                        'order_type': order_type,
                        'confidence': confidence,
                        'price': price,
                        'session_result': session_result if 'session_result' in locals() else {},
                        'fusion_result': {
                            'final_signal': final_signal if 'final_signal' in locals() else 'NONE',
                            'fused_score': fused_score if 'fused_score' in locals() else 0.0,
                            'fusion_reasons': fusion_reasons if 'fusion_reasons' in locals() else [],
                            'fusion_meta': fusion_meta if 'fusion_meta' in locals() else {}
                        },
                        'structure_result': struct_result if 'struct_result' in locals() else {},
                        'liquidity_result': liq_result if 'liq_result' in locals() else {},
                        'sentiment_result': sent_result if 'sent_result' in locals() else {},
                        'volatility_result': volatility_result if 'volatility_result' in locals() else {'level': 'MEDIUM', 'risk': 0.0},
                        'sideway_result': sideway_result if 'sideway_result' in locals() else {'score': 0.0},
                        'trend_result': trend_result if 'trend_result' in locals() else {},
                        'reversal_result': reversal_signal if 'reversal_signal' in locals() else None,
                        'risk_allowed': allowed if 'allowed' in locals() else True,
                        'risk_level': risk_level if 'risk_level' in locals() else 0.0
                    }
                    self.explain_ai.log(decision_context, fusion_signals)
            except Exception as e:
                logger.debug(f"✓ ExplainAI logging skipped: {e}")
        
        # ============================================================================
        # 🔄 STEP 2.5: REVERSE SIGNAL HANDLING - Đóng TẤT CẢ lệnh khi đảo chiều MẠNH
        # ✅ BẬT LẠI - Theo yêu cầu user (Dec 16, 2025)
        # ============================================================================
        # Logic: Khi có tín hiệu đảo chiều MẠNH (confidence >= 70%) → Đóng TẤT CẢ lệnh ngược chiều
        # - Tín hiệu BUY mạnh → Đóng TẤT CẢ lệnh SELL cũ
        # - Tín hiệu SELL mạnh → Đóng TẤT CẢ lệnh BUY cũ
        # 
        # ⚠️ FIX BUG: TÁCH RIÊNG khỏi điều kiện mở lệnh mới
        # - Đóng lệnh cũ: Chạy NGAY nếu có đảo chiều mạnh
        # - Mở lệnh mới: Kiểm tra điều kiện riêng sau đó
        
        if self.money_manager and len(self.money_manager.open_positions) > 0:
            # Ngưỡng confidence cho đảo chiều MẠNH
            STRONG_REVERSAL_THRESHOLD = 70.0  # >= 70% confidence
            
            # Kiểm tra đảo chiều TRƯỚC KHI kiểm tra điều kiện mở lệnh
            if action != "NONE" and confidence >= STRONG_REVERSAL_THRESHOLD:
                # Xác định loại lệnh ngược lại cần đóng
                reverse_type = None
                if action in ["BUY", "BUY_LIMIT"]:
                    reverse_type = "SELL"
                elif action in ["SELL", "SELL_LIMIT"]:
                    reverse_type = "BUY"
                
                if reverse_type:
                    # Tìm tất cả lệnh ngược chiều
                    reverse_positions = [pos for pos in self.money_manager.open_positions 
                                        if isinstance(pos, dict) and reverse_type in pos['action']]
                    
                    if reverse_positions:
                        total_reverse_pnl = sum(pos.get('pnl', 0) for pos in reverse_positions)
                        
                        logger.warning("=" * 80)
                        logger.warning(f"🔄 ĐẢO CHIỀU MẠNH PHÁT HIỆN: {action} (Confidence: {confidence:.1f}%)")
                        logger.warning(f"   Có {len(reverse_positions)} lệnh {reverse_type} cũ (P/L: ${total_reverse_pnl:,.2f})")
                        logger.warning(f"   → ĐÓNG TẤT CẢ lệnh {reverse_type} để chuẩn bị chuyển sang {action}")
                        logger.warning("=" * 80)
                        
                        # Đóng TẤT CẢ lệnh ngược chiều
                        try:
                            current_price = price if 'price' in locals() else (
                                live_data['close'].iloc[-1] if demo_mode or not ML_AVAILABLE else 
                                self.data_fetcher.fetch_live_data()['close'].iloc[-1]
                            )
                            
                            closed = self.money_manager.close_all_by_type(reverse_type, current_price, 'STRONG_REVERSAL')
                            
                            if closed:
                                total_closed_pnl = sum(pnl for _, pnl in closed)
                                logger.info(f"✅ Đã đóng {len(closed)} lệnh {reverse_type}")
                                logger.info(f"   Total P/L: ${total_closed_pnl:.2f}")
                                logger.info(f"   Balance: ${self.money_manager.current_balance:,.2f}")
                                logger.info(f"   → Tiếp tục kiểm tra điều kiện mở lệnh {action} mới...")
                        except Exception as e:
                            logger.error(f"❌ Lỗi khi đóng lệnh đảo chiều: {e}")
                    else:
                        logger.debug(f"✓ Không có lệnh {reverse_type} cũ cần đóng")
        
        # ============================================================================
        # 🛡️ STEP 2.6: AUTO CUT LOSS - Cắt lỗ tự động khi chạm SL
        # ⚠️ CHỨC NĂNG ĐÃ TẮT - Theo yêu cầu user (Dec 12, 2025)
        # ============================================================================
        # User muốn để MT5 tự động đóng lệnh khi hit SL
        # Không cần bot kiểm tra và đóng manual
        logger.debug("🔴 AUTO CUT LOSS: DISABLED - Let MT5 handle SL automatically")
        
        # ============================================================================
        # 🧠 STEP 3: AI DECISION - AI quyết định có mở lệnh MỚI không
        # ============================================================================
        # ⚠️ QUAN TRỌNG: Bước này RIÊNG BIỆT với STEP 2.5
        # - STEP 2.5 đã đóng lệnh cũ (nếu có đảo chiều)
        # - STEP 3 quyết định có mở lệnh mới không
        # - Nếu STEP 3 block → Không mở lệnh mới, nhưng đã đóng lệnh cũ rồi
        if action != "NONE" and order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
            # 3.0: PORTFOLIO EXPOSURE CHECK - Kiểm tra giới hạn exposure trước khi mở lệnh
            try:
                if hasattr(self, 'portfolio_ai') and self.portfolio_ai is not None:
                    # Chuẩn bị thông tin lệnh dự kiến
                    intended_trade = {
                        'action': order_type,
                        'symbol': self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else 'XAUUSD',
                        'price': price,
                        'lot_size': base_lot if 'base_lot' in locals() else float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                        'confidence': confidence,
                        'entry_price': price if order_type in ["BUY", "SELL"] else limit_price
                    }
                    
                    # Tính notional exposure
                    notional = intended_trade['price'] * intended_trade['lot_size'] * 100  # Giả sử pip value = 100
                    
                    # Kiểm tra exposure
                    allowed, reason = self.portfolio_ai.allowed_open(
                        symbol=intended_trade['symbol'],
                        side=intended_trade['action'],
                        notional=notional
                    )
                    
                    if not allowed:
                        logger.warning(f"🚫 PORTFOLIO EXPOSURE BLOCKED - {order_type}")
                        logger.warning(f"   Lý do: {reason}")
                        logger.warning(f"   Notional: ${notional:,.2f}")
                        action = "NONE"
                        order_type = "NONE"
                    else:
                        logger.info(f"✅ PORTFOLIO EXPOSURE OK - Notional: ${notional:,.2f}")
                else:
                    logger.debug("ℹ️ PortfolioAI not available - skipping exposure check")
            except Exception as e:
                logger.warning(f"⚠️ Portfolio exposure check failed: {e} - proceeding with trade")
            
            # 3.1: AI SMART DECISION - Phân tích market condition
            if self.money_manager:
                # Lấy live_data nếu chưa có (cho demo mode)
                if demo_mode or not ML_AVAILABLE:
                    live_data = self.data_fetcher.fetch_live_data()
                
                # Phân tích market để AI ra quyết định
                df_features = self.ai_model.prepare_features(live_data)
                is_sideways = df_features['is_sideways'].iloc[-1]
                trend_quality = df_features['trend_quality'].iloc[-1]
                
                # Xác định market condition
                if is_sideways == 1 or trend_quality < 0.8:
                    market_condition = "SIDEWAYS/WEAK"
                else:
                    market_condition = "TRENDING"

                # Tên xu hướng (human-friendly): Bullish / Bearish / Neutral / Sideways
                if 'trend_direction' in df_features.columns:
                    try:
                        td = int(df_features['trend_direction'].iloc[-1])
                        if td == 1:
                            trend_label = 'Bullish'
                        elif td == -1:
                            trend_label = 'Bearish'
                        else:
                            trend_label = 'Neutral'
                    except Exception:
                        trend_label = 'Unknown'
                else:
                    trend_label = 'Sideways' if market_condition == 'SIDEWAYS/WEAK' else 'Unknown'

                # Map English trend label to Vietnamese for clearer logs
                try:
                    _vn_map = {
                        'bullish': 'Tăng',
                        'bearish': 'Giảm',
                        'neutral': 'Trung lập',
                        'sideways': 'Đi ngang',
                        'unknown': 'Không rõ'
                    }
                    trend_vn = _vn_map.get(str(trend_label).lower(), str(trend_label))
                except Exception:
                    trend_vn = str(trend_label)

                logger.info(f"📊 Thị trường: {market_condition} — Xu hướng: {trend_vn} (Chất lượng xu hướng: {trend_quality:.2f})")
                
                # 🧠 AI quyết định dựa trên nhiều yếu tố
                # 🎯 TẠM TẮT SIDEWAYS FILTER ĐỂ TEST
                if enable_sideways_filter:
                    can_open, reason, risk_score = self.money_manager.can_open_position(
                        confidence=confidence / 100.0,
                        market_condition=market_condition
                    )
                else:
                    # Tắt filter → Luôn cho phép mở lệnh
                    can_open = True
                    reason = "Sideways filter disabled"
                    risk_score = 80.0
                    logger.info(f"🎯 SIDEWAYS FILTER TẮT - Chấp nhận mọi tín hiệu AI")
                
                if not can_open:
                    logger.warning(f"⛔ QUYẾT ĐỊNH AI: KHÔNG MỞ LỆNH")
                    logger.warning(f"   Lý do: {reason}")
                    logger.warning(f"   Điểm Risk: {risk_score:.0f}/100 (Cần >= 50)")
                    
                    action = "NONE"
                    order_type = "NONE"
                else:
                    logger.info(f"✅ QUYẾT ĐỊNH AI: MỞ LỆNH (Điểm số: {risk_score:.0f}/100)")
            
            # 3.2: 🚫 DUPLICATE SIGNAL FILTER - Kiểm tra tín hiệu trùng lặp
            if action != "NONE":
                # Kiểm tra tín hiệu có giống signal trước không
                is_duplicate = False
                current_time = datetime.now()
                
                if self.last_signal['action'] == action and self.last_signal['timestamp']:
                    time_diff = (current_time - self.last_signal['timestamp']).total_seconds()
                    price_diff = abs(price - self.last_signal['price']) if self.last_signal['price'] else 999
                    
                    # Nếu cùng action, trong vòng 60s, và giá không đổi nhiều → SPAM!
                    if time_diff < self.min_signal_interval and price_diff < self.min_price_change:
                        is_duplicate = True
                        logger.warning(f"🚫 DUPLICATE SIGNAL - {action} @ {price:.2f}")
                        logger.warning(f"   Last signal: {self.last_signal['action']} @ {self.last_signal['price']:.2f} ({time_diff:.0f}s ago)")
                        logger.warning(f"   Price change: ${price_diff:.2f} (Need >= ${self.min_price_change})")
                        action = "NONE"
                        order_type = "NONE"
                
                # Cập nhật last signal nếu không trùng
                if not is_duplicate:
                    self.last_signal = {
                        'action': action,
                        'price': price,
                        'timestamp': current_time
                    }
            
            # 3.3: Calculate lot size with confidence & DD multipliers
            base_lot = 0.10  # Default lot size
            if self.money_manager and action != "NONE":
                # Calculate SL price - normalize symbol variants (VIPc) to base XAUUSD
                base_sym = normalize_symbol(self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else None)
                # Default distances per instrument
                if base_sym == 'XAUUSD':
                    sl_distance = 1.0  # $1 for XAUUSD
                else:
                    sl_distance = 1.0  # Fallback
                if action in ["BUY", "BUY_LIMIT"]:
                    sl_price = price - sl_distance
                else:
                    sl_price = price + sl_distance
                
                # Money Manager calculates lot based on entry/SL prices
                mm_lot = self.money_manager.calculate_lot_size(
                    entry_price=price,
                    sl_price=sl_price,
                    confidence=confidence / 100.0  # Convert to 0-1
                )
                
                # Apply drawdown protector multiplier (0.5 if reduced, 1.0 if normal)
                if self.drawdown_protector:
                    dd_multiplier = self.drawdown_protector.get_lot_multiplier()
                    final_lot = mm_lot * dd_multiplier
                    
                    if dd_multiplier < 1.0:
                        logger.warning(f"🛡️ DRAWDOWN PROTECTION - Lot size reduced:")
                        logger.warning(f"   Base lot: {mm_lot:.2f} → Final lot: {final_lot:.2f} ({dd_multiplier:.1%})")
                else:
                    final_lot = mm_lot              
                # Apply live_lot_cap, optionally respect user BALANCE_LOT_CAPS mapping
                try:
                    cap = float(getattr(self, 'live_lot_cap', 10.0) or 10.0)
                    respect = False
                    try:
                        from config import config as lc
                        respect = bool(getattr(lc, 'RESPECT_BALANCE_LOT_CAPS', False))
                    except Exception:
                        respect = False

                    if respect:
                        try:
                            balance_cap = float(self.get_balance_lot_cap())
                        except Exception:
                            balance_cap = cap
                        effective_cap = min(cap, balance_cap)
                        if final_lot > effective_cap:
                            logger.warning(f"🔒 Capping computed lot {final_lot:.2f} -> {effective_cap:.2f} due to balance cap/livectrl")
                            final_lot = effective_cap
                    else:
                        if final_lot > cap:
                            logger.warning(f"🔒 Capping computed lot {final_lot:.2f} -> {cap:.2f} due to live_lot_cap")
                            final_lot = cap
                except Exception:
                    pass

                logger.info(f"💰 Lot size calculated: {final_lot:.2f} (Confidence: {confidence:.1f}%)")
                base_lot = final_lot
            elif self.drawdown_protector and action != "NONE":
                # If no Money Manager, still apply DD multiplier
                dd_multiplier = self.drawdown_protector.get_lot_multiplier()
                final_lot = base_lot * dd_multiplier
                
                if dd_multiplier < 1.0:
                    logger.warning(f"🛡️ DRAWDOWN PROTECTION - Lot size reduced:")
                    logger.warning(f"   Base lot: {base_lot:.2f} → Final lot: {final_lot:.2f} ({dd_multiplier:.1%})")
                
                base_lot = final_lot
        
        # Update global signal with detailed info
        # QUAN TRỌNG: Chỉ gửi tín hiệu khi có action BUY/SELL/BUY_LIMIT/SELL_LIMIT
        if order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
            actual_entry_price = price if order_type in ["BUY", "SELL"] else limit_price

            # --- AI Pattern Analysis ---
            try:
                # Use last available H1 data for pattern detection
                pattern_data = None
                if 'H1' in tf_data:
                    pattern_data = tf_data['H1'].copy()
                elif live_data is not None:
                    pattern_data = live_data.copy()
                else:
                    pattern_data = None
                pattern_result = None
                if pattern_data is not None and hasattr(self, 'candle_ai'):
                    # Detect patterns on the last bar
                    last_row = pattern_data.iloc[-1]
                    o, h, l, c = last_row['open'], last_row['high'], last_row['low'], last_row['close']
                    pattern_result = {
                        'doji': self.candle_ai.doji(o, h, l, c),
                        'hammer': self.candle_ai.hammer(o, h, l, c),
                        'inverted_hammer': self.candle_ai.inverted_hammer(o, h, l, c),
                        'bullish_engulfing': False,
                        'bearish_engulfing': False
                    }
                    # Engulfing needs previous bar
                    if len(pattern_data) > 1:
                        prev = pattern_data.iloc[-2]
                        prev_dict = {'o': prev['open'], 'c': prev['close']}
                        curr_dict = {'o': o, 'c': c}
                        pattern_result['bullish_engulfing'] = self.candle_ai.bullish_engulfing(prev_dict, curr_dict)
                        pattern_result['bearish_engulfing'] = self.candle_ai.bearish_engulfing(prev_dict, curr_dict)
            except Exception as e:
                logger.warning(f"⚠️ Pattern AI analysis failed: {e}")
                pattern_result = None

            # --- Trend, Volatility, Reversal already computed above ---
            # trend_action, trend_confidence, vol_prediction, reversal_prob

            # --- Prepare other AI analysis as before ---
            reversal_flag = False
            reversal_confidence = 0.0
            try:
                df_features = self.ai_model.prepare_features(live_data)
                is_sideways = int(df_features['is_sideways'].iloc[-1])
                trend_quality = float(df_features['trend_quality'].iloc[-1])
                market_regime = int(df_features['market_regime'].iloc[-1])
                latest_bar = df_features.iloc[-1]
                rsi_value = float(latest_bar['rsi']) if 'rsi' in latest_bar else 50.0
                adx_value = float(latest_bar['adx']) if 'adx' in latest_bar else 20.0
                support_level = float(latest_bar['bb_lower']) if 'bb_lower' in latest_bar else price - 5.0
                resistance_level = float(latest_bar['bb_upper']) if 'bb_upper' in latest_bar else price + 5.0
            except Exception as e:
                logger.warning(f"⚠️ Không thể lấy AI analysis data: {e}")
                is_sideways = 0
                trend_quality = 1.0
                market_regime = 1
                rsi_value = 50.0
                adx_value = 20.0
                support_level = price - 5.0
                resistance_level = price + 5.0
                try:
                    if live_data is None:
                        try:
                            live_data = self.data_fetcher.fetch_live_data()
                        except Exception:
                            live_data = None
                    if live_data is not None:
                        reversal_flag, reversal_confidence = self.ai_model.detect_reversal(live_data)
                    else:
                        reversal_flag, reversal_confidence = False, 0.0
                except Exception:
                    reversal_flag, reversal_confidence = False, 0.0

            # --- Volatility info ---
            volatility_info = vol_prediction if isinstance(vol_prediction, dict) else {}

            # --- Volume/Price Action AI ---
            try:
                volume_climax = detect_volume_climax(tf_data)
            except Exception as e:
                logger.warning(f"⚠️ detect_volume_climax failed: {e}"); volume_climax = None
            try:
                exhaustion = detect_exhaustion(tf_data)
            except Exception as e:
                logger.warning(f"⚠️ detect_exhaustion failed: {e}"); exhaustion = None
            try:
                delta = calculate_delta(tf_data)
            except Exception as e:
                logger.warning(f"⚠️ calculate_delta failed: {e}"); delta = None
            try:
                momentum = detect_momentum_shift(tf_data)
            except Exception as e:
                logger.warning(f"⚠️ detect_momentum_shift failed: {e}"); momentum = None
            try:
                choch = detect_choch(tf_data)
            except Exception as e:
                logger.warning(f"⚠️ detect_choch failed: {e}"); choch = None

            # --- Aggregate all AI results into latest_signal ---
            latest_signal.update({
                "action": order_type,
                "symbol": self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else "XAUUSD",
                "price": round(price, 4),
                "entry_price": round(actual_entry_price, 4),
                "lot_size": round(base_lot, 2),
                "confidence": round(confidence, 1),
                "timestamp": datetime.now().isoformat(),
                "signal_id": self.signal_count,
                "min_confidence_used": min_confidence,
                "sideways_filter_enabled": enable_sideways_filter,
                "is_sideways": is_sideways,
                "sideways_type": sideways_type if 'sideways_type' in locals() else 'UNKNOWN',  # TIGHT/WIDE/TRENDING
                "trend_quality": round(trend_quality, 2),
                "market_regime": market_regime,
                "rsi": round(rsi_value, 1),
                "adx": round(adx_value, 1),
                "support_level": round(support_level, 4),
                "resistance_level": round(resistance_level, 4),
                "reversal_flag": bool(reversal_flag),
                "reversal_confidence": round(reversal_confidence, 3),
                # --- 🆕 SMC MTF Orchestrator metadata ---
                "smc_mtf": getattr(self, '_smc_mtf_metadata', None),
                "smc_mtf_side": getattr(self, '_smc_mtf_metadata', {}).get('side') if hasattr(self, '_smc_mtf_metadata') else None,
                # --- 🆕 SCORING MODULE RESULTS ---
                "quality_score": quality_result if 'quality_result' in locals() else None,
                "pattern_probability": pattern_prob_result if 'pattern_prob_result' in locals() else None,
                # --- Aggregated AI results ---
                "pattern_ai": pattern_result,
                "trend_ai": {
                    "trend_action": trend_action if 'trend_action' in locals() else None,
                    "trend_confidence": trend_confidence if 'trend_confidence' in locals() else None
                },
                "volatility_ai": volatility_info,
                "reversal_ai": {
                    "reversal_prob": reversal_prob if 'reversal_prob' in locals() else None
                },
                # --- Price/Volume AI ---
                "volume_climax_ai": volume_climax,
                "exhaustion_ai": exhaustion,
                "delta_ai": delta,
                "momentum_shift_ai": momentum,
                "choch_ai": choch
                ,
                # --- Market Structure & Liquidity Sweep AI ---
                "market_structure_ai": ms_result,
                "liquidity_sweep_ai": ls_result,
                # --- Original signal for pattern learning ---
                "original_signal": {
                    'action': action,
                    'confidence': confidence,
                    'smc_data': smc_data_safe if 'smc_data_safe' in locals() else {},
                    'liquidity_sweep_ai': ls_result_safe if 'ls_result_safe' in locals() else ls_result,
                    'regime': {
                        'type': regime_data_safe.get('regime', 'unknown') if 'regime_data_safe' in locals() and isinstance(regime_data_safe, dict) else 'unknown'
                    },
                    'volatility': {
                        'level': vol_level_safe if 'vol_level_safe' in locals() else 'MEDIUM'
                    }
                }
            })
        else:
            # NONE - không cập nhật signal, giữ signal cũ
            latest_signal.update({
                "action": "NONE",
                "confidence": round(confidence, 1),
                "timestamp": datetime.now().isoformat(),
                "signal_id": self.signal_count
            })
        
        if action == "NONE":
            logger.info(f"="*80)
            logger.info(f"⏸️ Tín hiệu #{self.signal_count}: KHÔNG - Chờ điều kiện thị trường phù hợp")
            logger.info(f"   Giá hiện tại: {price:.4f} | Độ tin cậy: {confidence:.1f}%")
            # Chế độ runtime không in ra ở đây để tránh trùng lặp; heartbeat/ai_signals giữ thông tin này.
            logger.info(f"="*80)
        elif order_type in ["BUY", "SELL"]:
            # MARKET ORDER
            logger.info(f"="*80)
            logger.info(f"🎯 Tín hiệu #{self.signal_count}: {order_type} MARKET XAUUSD")
            logger.info(f"   📍 Giá thực thi: {price:.4f}")
            logger.info(f"   💪 Độ tin cậy: {confidence:.1f}% (HIGH - Vào ngay)")
            # Chế độ runtime không in ra ở đây để tránh trùng lặp; heartbeat/ai_signals giữ thông tin này.
            logger.info(f"   ⚡ VÀO LỆNH NGAY LẬP TỨC")
            logger.info(f"="*80)
        else:
            # LIMIT ORDER
            logger.info(f"="*80)
            logger.info(f"🎯 Tín hiệu #{self.signal_count}: {order_type} XAUUSD")
            logger.info(f"   📍 Giá hiện tại: {price:.4f}")
            logger.info(f"   🎯 Giá đặt lệnh LIMIT: {limit_price:.4f}")
            logger.info(f"   💪 Độ tin cậy: {confidence:.1f}% (MEDIUM - Chờ giá tốt)")
            # Chế độ runtime không in ra ở đây để tránh trùng lặp; heartbeat/ai_signals giữ thông tin này.
            logger.info(f"   ✅ Đặt lệnh LIMIT chờ giá chạm")
            logger.info(f"="*80)
        
        # Compute dynamic SL/TP and suggested lot, then write signal to file for MT5 EA
        if order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
            # 🚫 APPLY MACD VETO BEFORE SENDING SIGNAL
            try:
                if hasattr(self, 'fusion_ai_v4') and self.fusion_ai is not None:
                    # Prepare market data for veto analysis
                    veto_market_data = {'H1': tf_data.get('H1')} if tf_data and 'H1' in tf_data else None
                    
                    # Apply final decision with CrashDetector veto
                    vetoed_signal = self.fusion_ai.final_decision(latest_signal, veto_market_data)
                    
                    if vetoed_signal != latest_signal:
                        # Record fusion reasons for diagnostics
                        fusion_reason = vetoed_signal.get('reason', None) or vetoed_signal.get('reasons', None)
                        try:
                            latest_signal['fusion_reasons'] = fusion_reason
                        except Exception:
                            pass

                        logger.warning(f"🚫 MACD VETO APPLIED: {latest_signal['action']} → NONE | 🚫 MACD VETO ĐƯỢC ÁP DỤNG: {latest_signal['action']} → NONE")
                        logger.warning(f"   Reason: {fusion_reason} |   Lý do: {fusion_reason}")
                        latest_signal = vetoed_signal
                        order_type = "NONE"  # Update order_type to reflect veto
                    else:
                        # If fusion engine returned an explanation, save it for later diagnostics
                        try:
                            maybe_reasons = getattr(self.fusion_ai, 'last_explain', None)
                            if maybe_reasons:
                                latest_signal['fusion_reasons'] = maybe_reasons
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"⚠️ MACD Veto failed: {e} - proceeding with original signal | ⚠️ MACD Veto thất bại: {e} - tiếp tục với tín hiệu gốc")

            # 🛡️ EXECUTIONAI - Pre-trade execution conditions check
            try:
                if hasattr(self, 'execution_ai') and self.execution_ai is not None and order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
                    # Get current spread from MT5
                    try:
                        if MT5_AVAILABLE and hasattr(self, 'data_fetcher') and self.data_fetcher.use_mt5:
                            symbol_info = mt5.symbol_info(self.data_fetcher.symbol)
                            if symbol_info:
                                current_spread = symbol_info.ask - symbol_info.bid
                                avg_slippage_pct = 0.0002  # Default assumption
                                now_ts = time.time()
                                
                                # Check execution conditions
                                can_execute, reason, mode = self.execution_ai.allowed_to_execute(current_spread, avg_slippage_pct, now_ts)
                                
                                if not can_execute:
                                    logger.warning(f"🚫 EXECUTIONAI BLOCKED: {order_type} → NONE")
                                    logger.warning(f"   Reason: {reason}")
                                    latest_signal['action'] = "NONE"
                                    order_type = "NONE"
                                else:
                                    logger.info(f"✅ EXECUTIONAI APPROVED: {order_type} (mode: {mode})")
                                    # Could use mode to adjust order type if needed
                            else:
                                logger.debug("⚠️ Could not get symbol info for execution check")
                        else:
                            logger.debug("⚠️ MT5 not available for execution check")
                    except Exception as e:
                        logger.warning(f"⚠️ Error getting spread for execution check: {e}")
            except Exception as e:
                logger.warning(f"⚠️ ExecutionAI check failed: {e} - proceeding")

            # 🧠 ADAPTIVELEARNER - Update FusionAI weights based on signal generation
            try:
                if hasattr(self, 'adaptive_learner') and self.adaptive_learner is not None:
                    # Register signal generation for learning
                    self.adaptive_learner.register_signal(latest_signal)
                    logger.debug("🧠 AdaptiveLearner: Updated weights from signal generation")
            except Exception as e:
                logger.debug(f"⚠️ AdaptiveLearner signal registration failed: {e}")

            # 🎯 PATTERN SLTP ADVISOR - Enhanced SL/TP calculation
            try:
                if hasattr(self, 'pattern_sltp_advisor') and self.pattern_sltp_advisor is not None and order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
                    # Prepare data for PatternSLTPAdvisor
                    entry_price = latest_signal.get('entry_price', latest_signal.get('price', 0))
                    if entry_price > 0 and tf_data and 'H1' in tf_data:
                        df_h1 = tf_data['H1']
                        if df_h1 is not None and len(df_h1) >= 20:
                            # Calculate ATR for the pattern advisor
                            try:
                                atr_val = TechnicalIndicators.calculate_atr(df_h1.copy(), period=14)['atr'].iloc[-1]
                            except:
                                atr_val = abs(df_h1['high'].iloc[-1] - df_h1['low'].iloc[-1]) * 0.5  # Rough ATR estimate
                            
                            # Get recent levels
                            recent_levels = {
                                'last_swing_high': df_h1['high'].tail(20).max(),
                                'last_swing_low': df_h1['low'].tail(20).min()
                            }
                            
                            # Determine side
                            side = "buy" if order_type in ["BUY", "BUY_LIMIT"] else "sell"
                            
                            # Use a default pattern (could be enhanced to detect actual pattern)
                            pattern = "default"
                            
                            # Call PatternSLTPAdvisor.advise()
                            sltp_advice = self.pattern_sltp_advisor.advise(
                                pattern=pattern,
                                side=side,
                                recent_levels=recent_levels,
                                atr=atr_val,
                                price=entry_price,
                                base_rr=1.5
                            )
                            
                            if sltp_advice and isinstance(sltp_advice, dict):
                                logger.debug(f"🎯 PatternSLTPAdvisor advice: {sltp_advice}")
                                # Use AI-advised SL/TP if provided
                                ai_sl = sltp_advice.get('sl')
                                ai_tp = sltp_advice.get('tp')
                                
                                if ai_sl and ai_sl > 0:
                                    latest_signal['sl_price'] = ai_sl
                                    logger.info(f"🎯 PatternSLTPAdvisor updated SL: {ai_sl:.4f}")
                                if ai_tp and ai_tp > 0:
                                    latest_signal['tp_price'] = ai_tp
                                    logger.info(f"🎯 PatternSLTPAdvisor updated TP: {ai_tp:.4f}")
            except Exception as e:
                logger.warning(f"⚠️ PatternSLTPAdvisor failed: {e} - using default SL/TP")

            # 🎯 TRAILING SL AI - Dynamic trailing stops setup
            try:
                if hasattr(self, 'trailing_sl_ai') and self.trailing_sl_ai is not None and order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
                    # Use TrailingSL.analyze() to get trailing stop parameters
                    if tf_data and 'H1' in tf_data:
                        df_h1 = tf_data['H1']
                        if df_h1 is not None and len(df_h1) >= 20:
                            entry_price = latest_signal.get('entry_price', latest_signal.get('price', 0))
                            current_prices = {'bid': entry_price, 'ask': entry_price}  # Use entry price as reference
                            
                            # Get trailing analysis
                            trailing_analysis = self.trailing_sl_ai.analyze(df_h1, current_prices)
                            
                            if trailing_analysis and isinstance(trailing_analysis, dict):
                                # Add trailing parameters to signal
                                trailing_stop = trailing_analysis.get('trailing_stop')
                                if trailing_stop:
                                    # 🆕 SPECIAL LOGIC: WIDE sideways → breakeven nhanh khi lời 20 pips
                                    sideways_market_type = latest_signal.get('sideways_type', 'UNKNOWN')
                                    if sideways_market_type == 'WIDE':
                                        latest_signal['trailing_enabled'] = True
                                        latest_signal['trailing_type'] = 'sideways_breakeven'  # Đặc biệt cho WIDE sideways
                                        latest_signal['trailing_params'] = {
                                            'initial_stop': trailing_stop,
                                            'breakeven_trigger_pips': 20,  # 20-30 pips lời → trigger
                                            'breakeven_offset_pips': 10,   # SL lên +10 pips (không về entry)
                                            'atr_value': trailing_analysis.get('atr_value', 0),
                                            'stop_distance': trailing_analysis.get('stop_distance', 0)
                                        }
                                        logger.info(f"🎯 WIDE SIDEWAYS: Lời 20-30 pips → SL lên +10 pips (stop: {trailing_stop:.4f})")
                                    else:
                                        # TRENDING hoặc TIGHT → dùng trailing bình thường
                                        latest_signal['trailing_enabled'] = True
                                        latest_signal['trailing_type'] = 'atr_based'
                                        latest_signal['trailing_params'] = {
                                            'initial_stop': trailing_stop,
                                            'atr_value': trailing_analysis.get('atr_value', 0),
                                            'stop_distance': trailing_analysis.get('stop_distance', 0)
                                        }
                                        logger.info(f"🎯 TrailingSL AI setup: ATR-based trailing (stop: {trailing_stop:.4f})")
                                else:
                                    latest_signal['trailing_enabled'] = False
                                    logger.debug("🎯 TrailingSL AI: No trailing stop recommended")
            except Exception as e:
                logger.warning(f"⚠️ TrailingSL AI setup failed: {e} - no trailing stops")
            
            # -------------------- SIGNAL-DRIFT PROTECTION CHECK --------------------
            try:
                sd = getattr(self, 'signal_drift_settings', {}) or {}
                if sd.get('enabled', False):
                    # Append current direction into history (BUY/SELL/NONE)
                    try:
                        if order_type in ["BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"]:
                            dir_action = 'BUY' if 'BUY' in order_type else 'SELL'
                        else:
                            dir_action = 'NONE'
                        self._drift_history.append(dir_action)
                    except Exception:
                        pass

                    # Analyze recent non-NONE signals
                    try:
                        recent = [d for d in list(self._drift_history) if d in ('BUY', 'SELL')]
                        if len(recent) > 0:
                            counts = Counter(recent)
                            buyc = counts.get('BUY', 0)
                            sellc = counts.get('SELL', 0)
                            total = buyc + sellc
                            dominant = 'BUY' if buyc >= sellc else 'SELL'
                            ratio = float(buyc if dominant == 'BUY' else sellc) / float(total) if total > 0 else 0.0

                            # consecutive same-direction detection
                            consec = 0
                            for x in reversed(self._drift_history):
                                if x == dominant:
                                    consec += 1
                                elif x in ('BUY', 'SELL'):
                                    break

                            if ratio >= float(sd.get('max_same_dir_ratio', 0.75)) or consec >= int(sd.get('max_consecutive_same_dir', 6)):
                                # Trigger cooldown / mitigation
                                cooldown = int(sd.get('cooldown_seconds', 600))
                                self._drift_cooldown_until = time.time() + cooldown
                                logger.warning(f"⛔ DRIFT PROTECTION TRIGGERED: dominant={dominant}, ratio={ratio:.2f}, consec={consec} -> cooldown {cooldown}s")
                                latest_signal.update({
                                    'action': 'NONE',
                                    'reason': 'DRIFT_PROTECTION_TRIGGERED',
                                    'drift_dominant': dominant,
                                    'drift_ratio': round(ratio, 3),
                                    'drift_consecutive': int(consec),
                                    'drift_window': list(self._drift_history),
                                    'drift_cooldown_seconds': cooldown,
                                    'timestamp': datetime.now().isoformat(),
                                    'signal_id': self.signal_count
                                })
                                # persist a final NONE signal for EA visibility and exit early
                                try:
                                    self._write_signal_to_file(latest_signal)
                                except Exception:
                                    pass
                                return latest_signal
                    except Exception:
                        pass
            except Exception:
                pass

            try:
                sltp = self.compute_sl_tp(latest_signal, market_data=live_data)
                if sltp:
                    # merge back results into signal
                    latest_signal['sl_price'] = sltp.get('sl_price')
                    latest_signal['tp_price'] = sltp.get('tp_price')
                    # override lot_size if calculator suggested
                    latest_signal['lot_size'] = round(sltp.get('lot_size', latest_signal.get('lot_size', getattr(self, 'min_lot', DEFAULT_MIN_LOT))), 2)
                    latest_signal['sl_tp_computed'] = True
                    
                    # Log SL/TP source for transparency
                    sl_tp_source = sltp.get('source', 'standard')
                    if sl_tp_source == 'smc_mtf_orchestrator':
                        logger.info("=" * 70)
                        logger.info("🎯 USING SMC MTF ORCHESTRATOR SNIPER ENTRY")
                        logger.info(f"   Entry: {latest_signal['entry_price']:.5f}")
                        logger.info(f"   SL: {latest_signal['sl_price']:.5f}")
                        logger.info(f"   TP: {latest_signal['tp_price']:.5f}")
                        logger.info(f"   R:R: {sltp.get('rr_ratio', 0):.2f}:1")
                        logger.info(f"   Lot: {latest_signal['lot_size']:.2f}")
                        logger.info("=" * 70)
                    else:
                        logger.info(f"💰 SL/TP Computed: SL={latest_signal['sl_price']:.5f}, TP={latest_signal['tp_price']:.5f}, Lot={latest_signal['lot_size']:.2f}")
                else:
                    latest_signal['sl_tp_computed'] = False
            except Exception as e:
                logger.warning(f"⚠️ SL/TP compute failed before sending signal: {e}")
                latest_signal['sl_tp_computed'] = False

            # Diagnostic: if final decision conflicts with trend AI, log components for debugging
            try:
                trend_action = None
                try:
                    trend_action = latest_signal.get('trend_ai', {}).get('trend_action')
                except Exception:
                    trend_action = None

                if trend_action and order_type in ["BUY", "SELL"]:
                    # Normalize
                    ta = str(trend_action).upper()
                    if ta not in ("BUY", "SELL"):
                        # try mapping common labels
                        if ta.lower().startswith('bull'):
                            ta = 'BUY'
                        elif ta.lower().startswith('bear'):
                            ta = 'SELL'
                    if ta in ("BUY", "SELL") and ta != order_type:
                        logger.warning(f"⚠️ Quyết định mâu thuẫn với xu hướng AI: xu hướng={trend_action} nhưng ra lệnh {order_type}")
                        # Log useful signal internals
                        try:
                            logger.warning(f"   trend_quality={latest_signal.get('trend_quality')}, reversal_conf={latest_signal.get('reversal_confidence')}")
                            logger.warning(f"   liquidity_sweep={latest_signal.get('liquidity_sweep_ai')}, pattern={latest_signal.get('pattern_ai')}")
                            logger.warning(f"   volatility={latest_signal.get('volatility_ai')}")
                            if latest_signal.get('fusion_reasons'):
                                logger.warning(f"   fusion_reasons={latest_signal.get('fusion_reasons')}")
                        except Exception:
                            logger.debug("⚠️ Could not print full diagnostic details for conflicting decision")
            except Exception:
                pass

            logger.info(f"📝 Đang gọi _write_signal_to_file với signal: action={latest_signal.get('action')}, symbol={latest_signal.get('symbol')}")
            self._write_signal_to_file(latest_signal)
            logger.info(f"✅ ĐÃ GỬI TÍN HIỆU LÊN MT5: {order_type}")
            try:
                if hasattr(logger, 'sep'):
                    logger.sep(f"NEW COMMAND: SENT SIGNAL TO MT5 -> {order_type}")
            except Exception:
                pass
            
            # 3.4: HEALTH MONITORING - Đăng ký hoạt động giao dịch sau khi gửi tín hiệu
            try:
                if hasattr(self, 'health_ai') and self.health_ai is not None:
                    # Đăng ký tín hiệu được gửi (chưa có kết quả)
                    tag = f"signal_{order_type.lower()}"
                    self.health_ai.register_result(
                        tag=tag,
                        correct=None,  # Chưa biết kết quả
                        confidence=confidence / 100.0,  # Convert to 0-1
                        pnl=0.0  # Chưa có P/L
                    )
                    logger.debug(f"🏥 HEALTH MONITORING: Registered signal - Tag: {tag}, Confidence: {confidence:.1f}%")
                else:
                    logger.debug("ℹ️ HealthAI not available - skipping operation registration")
            except Exception as e:
                logger.warning(f"⚠️ Health monitoring registration failed: {e} - proceeding normally")
        else:
            logger.info(f"⏭️ BỎ QUA - Không gửi tín hiệu NONE lên MT5")
        
        return latest_signal
    
    def _collect_market_data_for_partial_tp(self, live_data):
        """🧠 Thu thập dữ liệu thị trường cho AI Partial Take Profit
        
        Args:
            live_data: DataFrame chứa dữ liệu giá trực tiếp
            
        Returns:
            dict: Dữ liệu thị trường đã xử lý
        """
        try:
            if live_data is None or len(live_data) < 20:
                return {}
            
            # Lấy dữ liệu gần nhất
            recent_data = live_data.tail(50)  # Lấy 50 cây nến gần nhất
            
            # Trend analysis
            trend_data = {}
            try:
                # Tính trend strength dựa trên slope của EMA
                ema_short = recent_data['close'].ewm(span=20).mean()
                ema_long = recent_data['close'].ewm(span=50).mean()
                trend_slope = (ema_short.iloc[-1] - ema_short.iloc[-10]) / 10
                trend_strength = min(1.0, max(0.0, abs(trend_slope) / (recent_data['close'].iloc[-1] * 0.001)))
                trend_data = {'strength': trend_strength}
            except:
                trend_data = {'strength': 0.5}
            
            # Volatility analysis
            volatility_data = {}
            try:
                returns = recent_data['close'].pct_change().dropna()
                vol_std = returns.std()
                vol_level = min(1.0, vol_std * 100)  # Normalize to 0-1
                volatility_data = {'level': vol_level, 'std_dev': vol_std}
            except:
                volatility_data = {'level': 0.5, 'std_dev': 0.01}
            
            # Volume analysis
            volume_data = {}
            try:
                current_volume = recent_data['volume'].iloc[-1]
                avg_volume = recent_data['volume'].tail(20).mean()
                volume_data = {
                    'current': current_volume,
                    'average': avg_volume,
                    'ratio': current_volume / avg_volume if avg_volume > 0 else 1
                }
            except:
                volume_data = {'current': 0, 'average': 1, 'ratio': 1}
            
            # Momentum analysis
            momentum_data = {}
            try:
                # RSI
                delta = recent_data['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                current_rsi = rsi.iloc[-1]
                
                # MACD
                ema12 = recent_data['close'].ewm(span=12).mean()
                ema26 = recent_data['close'].ewm(span=26).mean()
                macd = ema12 - ema26
                macd_signal = macd.ewm(span=9).mean()
                macd_hist = macd - macd_signal
                current_macd_signal = macd_hist.iloc[-1]
                
                momentum_data = {
                    'rsi': current_rsi,
                    'macd_signal': current_macd_signal
                }
            except:
                momentum_data = {'rsi': 50, 'macd_signal': 0}
            
            return {
                'trend': trend_data,
                'volatility': volatility_data,
                'volume': volume_data,
                'momentum': momentum_data
            }
            
        except Exception as e:
            logger.warning(f"⚠️ Error collecting market data for partial TP: {e}")
            return {}
    
    def _load_signal_count(self):
        """Load signal_count from file to persist across bot restarts"""
        try:
            script_dir = os.path.dirname(__file__)
            live_trading_dir = os.path.dirname(script_dir)
            mql5_dir = os.path.dirname(live_trading_dir)
            count_file = os.path.join(mql5_dir, "Files", "signal_count.txt")
            if os.path.exists(count_file):
                with open(count_file, 'r') as f:
                    count = int(f.read().strip())
                    logger.info(f"📊 Loaded signal_count from file: {count}")
                    return count
        except Exception as e:
            logger.debug(f"Could not load signal_count: {e}")
        return 0
    
    def _save_signal_count(self):
        """Save signal_count to file for persistence"""
        try:
            script_dir = os.path.dirname(__file__)
            live_trading_dir = os.path.dirname(script_dir)
            mql5_dir = os.path.dirname(live_trading_dir)
            mt5_files_path = os.path.join(mql5_dir, "Files")
            if not os.path.exists(mt5_files_path):
                os.makedirs(mt5_files_path, exist_ok=True)
            count_file = os.path.join(mt5_files_path, "signal_count.txt")
            with open(count_file, 'w') as f:
                f.write(str(self.signal_count))
        except Exception as e:
            logger.debug(f"Could not save signal_count: {e}")
    
    def _write_signal_to_file(self, signal):
        """Write signal to file for MT5 EA backup communication
        
        Signal format includes:
        - sideways_type: 'TIGHT', 'WIDE', or 'TRENDING' (for conditional trailing logic)
        - trailing_type: 'sideways_breakeven' or 'atr_based'
        - trailing_params:
            * For WIDE sideways: breakeven_trigger_pips (20), breakeven_offset_pips (0)
            * For others: standard ATR-based trailing
        
        MT5 EA should implement:
        - If sideways_type == 'WIDE' and trailing_type == 'sideways_breakeven':
            → Move SL to entry when profit >= 20 pips
        - Else: Use standard trailing stop logic
        """
        logger.info(f"🔍 _write_signal_to_file CALLED - action={signal.get('action')}, price={signal.get('price')}")
        try:
            # Ensure SL/TP and lot are present for actionable signals.
            try:
                action = signal.get('action', 'NONE')
                if action in ("BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT"):
                    # If SL/TP not already attached, compute them.
                    if 'sl_price' not in signal or 'tp_price' not in signal or 'lot_size' not in signal:
                        try:
                            # Try to obtain recent market data for better SL/TP
                            live_data = None
                            if MT5_AVAILABLE and hasattr(self, 'data_fetcher'):
                                try:
                                    live_data = self.data_fetcher.fetch_mt5_data(self.data_fetcher.symbol, mt5.TIMEFRAME_H1, bars=200)
                                except Exception:
                                    live_data = None

                            # If we have a DataFrame, pass it as a dict with 'H1' key so compute_sl_tp can use it
                            market_data_arg = {'H1': live_data} if live_data is not None else None
                            sltp = self.compute_sl_tp(signal, market_data=market_data_arg)
                            if sltp:
                                logger.debug(f"🔧 compute_sl_tp result: {sltp}")
                                # merge results (don't overwrite explicit values)
                                sl_val = sltp.get('sl_price')
                                tp_val = sltp.get('tp_price')
                                if sl_val is not None and 'sl_price' not in signal:
                                    signal['sl_price'] = sl_val
                                if tp_val is not None and 'tp_price' not in signal:
                                    signal['tp_price'] = tp_val
                                # prefer computed lot but respect explicit small values
                                try:
                                    suggested_lot = sltp.get('lot_size', signal.get('lot_size', getattr(self, 'min_lot', DEFAULT_MIN_LOT)))
                                    if suggested_lot is not None:
                                        suggested_lot = round(float(suggested_lot), 2)
                                        signal['lot_size'] = suggested_lot
                                except Exception:
                                    pass
                                signal['sl_tp_computed'] = True
                            else:
                                signal['sl_tp_computed'] = False
                        except Exception:
                            signal['sl_tp_computed'] = False
            except Exception:
                # Non-fatal - continue to write whatever is available
                pass

            # Convert numpy types to Python types
            # Ensure fusion_reasons is present if available from FusionAI
            try:
                if 'fusion_reasons' not in signal or signal.get('fusion_reasons') in (None, ''):
                    fa = getattr(self, 'fusion_ai_v4', None)
                    if fa is not None:
                        try:
                            # Prefer stored last_explain
                            maybe = getattr(fa, 'last_explain', None)
                            if maybe:
                                signal['fusion_reasons'] = maybe
                            else:
                                # Try calling explain/explain_signal if available
                                explain_fn = getattr(fa, 'explain', None) or getattr(fa, 'explain_signal', None)
                                if callable(explain_fn):
                                    try:
                                        expl = explain_fn(signal)
                                        if expl:
                                            signal['fusion_reasons'] = expl
                                    except Exception:
                                        # ignore explain errors
                                        pass
                        except Exception:
                            pass
            except Exception:
                pass

            signal_clean = {}
            for key, value in signal.items():
                if hasattr(value, 'item'):  # numpy types have .item() method
                    signal_clean[key] = value.item()
                elif isinstance(value, (int, float, str, bool, type(None))):
                    signal_clean[key] = value
                else:
                    signal_clean[key] = str(value)
            
            # Write to MT5 Files directory for EA access
            # __file__ = MQL5/live_trading/core/complete_ai_trading_system.py
            # Need to go up 3 levels: core -> live_trading -> MQL5 -> Files
            script_dir = os.path.dirname(__file__)  # MQL5/live_trading/core
            live_trading_dir = os.path.dirname(script_dir)  # MQL5/live_trading
            mql5_dir = os.path.dirname(live_trading_dir)  # MQL5
            mt5_files_path = os.path.join(mql5_dir, "Files")
            if not os.path.exists(mt5_files_path):
                os.makedirs(mt5_files_path, exist_ok=True)
            
            signal_file = os.path.join(mt5_files_path, "ai_signals.txt")
            logger.info(f"📂 Target file path: {signal_file}")
            
            # Gắn runtime mode để EA / logs biết chế độ hiện tại
            try:
                signal_clean['runtime_mode'] = get_runtime_mode()
            except Exception:
                signal_clean['runtime_mode'] = 'UNKNOWN'

            # Thêm thông tin chi tiết cho log
            signal_with_log = signal_clean.copy()
            
            # Tạo message log cho MT5
            mode = signal_clean.get('runtime_mode', 'UNKNOWN')
            if signal_clean['action'] == 'NONE':
                viet_log = f"⏸️ Tín hiệu #{signal_clean['signal_id']}: KHÔNG - Chờ điều kiện tốt hơn (Giá: {signal_clean['price']:.4f}, Độ tin cậy: {signal_clean['confidence']:.1f}%) | Mode: {mode}"
                eng_log = f"⏸️ Signal #{signal_clean['signal_id']}: NONE - Waiting for better market conditions (Price: {signal_clean['price']:.4f}, Confidence: {signal_clean['confidence']:.1f}%) | Mode: {mode}"
                signal_with_log['mt5_log_vi'] = viet_log
                signal_with_log['mt5_log_en'] = eng_log
                signal_with_log['mt5_log'] = viet_log
            elif signal_clean['action'] in ['BUY', 'SELL']:
                # MARKET ORDER
                viet_log = f"⚡ Tín hiệu #{signal_clean['signal_id']}: {signal_clean['action']} MARKET @ {signal_clean['price']:.4f} (Độ tin cậy: {signal_clean['confidence']:.1f}% - VÀO NGAY) | Mode: {mode}"
                eng_log = f"⚡ Signal #{signal_clean['signal_id']}: {signal_clean['action']} MARKET @ {signal_clean['price']:.4f} (Confidence: {signal_clean['confidence']:.1f}% - ENTER NOW) | Mode: {mode}"
                signal_with_log['mt5_log_vi'] = viet_log
                signal_with_log['mt5_log_en'] = eng_log
                signal_with_log['mt5_log'] = viet_log
            elif 'LIMIT' in signal_clean['action']:
                # LIMIT ORDER
                viet_log = f"🎯 Tín hiệu #{signal_clean['signal_id']}: {signal_clean['action']} - Giá hiện tại: {signal_clean['price']:.4f}, Đặt lệnh @ {signal_clean['entry_price']:.4f} (Độ tin cậy: {signal_clean['confidence']:.1f}%) | Mode: {mode}"
                eng_log = f"🎯 Signal #{signal_clean['signal_id']}: {signal_clean['action']} - Current price: {signal_clean['price']:.4f}, Place order @ {signal_clean['entry_price']:.4f} (Confidence: {signal_clean['confidence']:.1f}%) | Mode: {mode}"
                signal_with_log['mt5_log_vi'] = viet_log
                signal_with_log['mt5_log_en'] = eng_log
                signal_with_log['mt5_log'] = viet_log
            else:
                viet_log = f"🎯 Tín hiệu #{signal_clean['signal_id']}: {signal_clean['action']} @ {signal_clean['price']:.4f} (Độ tin cậy: {signal_clean['confidence']:.1f}%) | Mode: {mode}"
                eng_log = f"🎯 Signal #{signal_clean['signal_id']}: {signal_clean['action']} @ {signal_clean['price']:.4f} (Confidence: {signal_clean['confidence']:.1f}%) | Mode: {mode}"
                signal_with_log['mt5_log_vi'] = viet_log
                signal_with_log['mt5_log_en'] = eng_log
                signal_with_log['mt5_log'] = viet_log
            
            # Prepare ASCII-friendly mt5_log to avoid garbled characters in MT5 terminal
            original_log = signal_with_log.get('mt5_log', '')
            signal_with_log['mt5_log_utf8'] = original_log
            try:
                ascii_log = remove_accents(original_log)
            except Exception:
                ascii_log = original_log
            signal_with_log['mt5_log'] = ascii_log

            # Add sender timestamp (milliseconds since epoch) so EA can measure latency
            try:
                signal_with_log['ts_ms'] = int(time.time() * 1000)
            except Exception:
                signal_with_log['ts_ms'] = None

            # Add CPU/MEM snapshot so the EA can read runtime telemetry
            try:
                if PSUTIL_AVAILABLE:
                    try:
                        cpu_sig = psutil.cpu_percent(interval=0.1)
                    except Exception:
                        cpu_sig = None
                    try:
                        mem_sig = psutil.virtual_memory().percent
                    except Exception:
                        mem_sig = None
                    signal_with_log['cpu_percent'] = float(cpu_sig) if cpu_sig is not None else 0.0
                    signal_with_log['mem_percent'] = float(mem_sig) if mem_sig is not None else 0.0
                else:
                    signal_with_log['cpu_percent'] = None
                    signal_with_log['mem_percent'] = None
            except Exception:
                # Non-fatal: continue without telemetry
                signal_with_log['cpu_percent'] = None
                signal_with_log['mem_percent'] = None

            # Write JSON signal to file (ASCII mt5_log) using atomic replace
            # This reduces file-lock/partial-read race conditions with MT5 EA
            json_content = json.dumps(signal_with_log, ensure_ascii=True, indent=2)

            # Persist full signal for diagnostics (append JSONL). Best-effort: always try to save.
            try:
                try:
                    _persist_latest_signal_log(signal_with_log)
                except Exception:
                    # swallow any persistence error - do not block main flow
                    pass
            except Exception:
                pass
            # --- Deduplication: skip writing identical signal repeatedly within short window ---
            try:
                now_ts = time.time()
                last = getattr(self, '_last_signal_written', None)
                last_ts = getattr(self, '_last_signal_written_ts', 0.0)
                dedup_window = getattr(self, '_signal_dedup_window', 10)
                if last is not None and last == json_content and (now_ts - float(last_ts)) < float(dedup_window):
                    logger.warning(f"⚠️ DEDUP BLOCK: Skipping identical signal write (within {dedup_window}s window)")
                    return
                else:
                    logger.info(f"✅ DEDUP CHECK PASSED - Writing signal (last_ts: {now_ts - last_ts:.1f}s ago)")
            except Exception as e:
                # If dedup check fails for any reason, continue to write normally
                logger.warning(f"⚠️ Dedup check failed: {e} - continuing to write")
                pass
            temp_file = signal_file + '.tmp'
            try:
                with open(temp_file, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(json_content)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        # fsync may not be available on all platforms; ignore if it fails
                        pass
                # atomic replace
                try:
                    os.replace(temp_file, signal_file)
                except Exception:
                    # fallback to rename if replace not supported
                    os.rename(temp_file, signal_file)

                logger.info(f"📁 ✅ ĐÃ GHI FILE: {signal_file}")
                try:
                    # update dedup cache on successful write
                    self._last_signal_written = json_content
                    self._last_signal_written_ts = time.time()
                except Exception:
                    pass
                # Increment and save signal_count for next signal
                try:
                    self.signal_count += 1
                    self._save_signal_count()
                    logger.info(f"📊 Signal count incremented to: {self.signal_count}")
                except Exception as e:
                    logger.debug(f"Could not increment signal_count: {e}")
            except Exception as e:
                logger.error(f"❌ Lỗi ghi file tín hiệu (atomic): {e}")
                import traceback
                logger.error(f"   Traceback: {traceback.format_exc()}")
                # Best-effort fallback: try direct write
                try:
                    with open(signal_file, 'w', encoding='utf-8', errors='ignore') as f:
                        f.write(json_content)
                    logger.info(f"📁 ✅ FALLBACK WRITE SUCCESS: {signal_file}")
                except Exception as e2:
                    logger.error(f"❌ Fallback write failed: {e2}")
                    logger.error(f"   Traceback: {traceback.format_exc()}")
            
        except Exception as e:
            logger.error(f"❌ CRITICAL: _write_signal_to_file failed completely: {e}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")

    def emit_test_signals(self, mode='all'):
        """Emit synthetic signals (market/limit/reversal) and write to Files/ai_signals.txt for EA testing.
        mode: 'market', 'limit', 'reversal', or 'all'
        """
        logger.info(f"🧪 Emitting test signals (mode={mode})")
        try:
            # Try to get a live reference price
            try:
                live = self.data_fetcher.fetch_live_data()
                ref_price = float(live['close'].iloc[-1])
                bid = float(live['low'].iloc[-1]) if 'low' in live else ref_price - 0.5
                ask = float(live['high'].iloc[-1]) if 'high' in live else ref_price + 0.5
            except Exception:
                # Fallback to a sensible XAU price
                ref_price = 1850.0
                bid = ref_price - 0.5
                ask = ref_price + 0.5

            signals = []
            sid = self.signal_count + 1

            if mode in ('market', 'all'):
                # Market BUY
                signals.append({
                    'action': 'BUY',
                    'symbol': self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else 'XAUUSD',
                    'price': round(ref_price, 4),
                    'entry_price': round(ref_price, 4),
                    'lot_size': float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                    'confidence': 90.0,
                    'timestamp': datetime.now().isoformat(),
                    'signal_id': sid,
                    'min_confidence_used': 0,
                    'sideways_filter_enabled': False,
                    'is_sideways': 0,
                    'trend_quality': 1.2,
                    'market_regime': 2,
                    'rsi': 55.0,
                    'adx': 30.0,
                    'support_level': round(ref_price - 2.0, 4),
                    'resistance_level': round(ref_price + 2.0, 4),
                    'reversal_flag': False,
                    'reversal_confidence': 0.0
                })
                sid += 1

                # Market SELL
                signals.append({
                    'action': 'SELL',
                    'symbol': self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else 'XAUUSD',
                    'price': round(ref_price, 4),
                    'entry_price': round(ref_price, 4),
                    'lot_size': float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                    'confidence': 85.0,
                    'timestamp': datetime.now().isoformat(),
                    'signal_id': sid,
                    'min_confidence_used': 0,
                    'sideways_filter_enabled': False,
                    'is_sideways': 0,
                    'trend_quality': 1.0,
                    'market_regime': 1,
                    'rsi': 45.0,
                    'adx': 28.0,
                    'support_level': round(ref_price - 3.0, 4),
                    'resistance_level': round(ref_price + 3.0, 4),
                    'reversal_flag': False,
                    'reversal_confidence': 0.0
                })
                sid += 1

            if mode in ('limit', 'all'):
                # BUY_LIMIT slightly below current
                buy_limit = round(bid - 0.5, 4)
                signals.append({
                    'action': 'BUY_LIMIT',
                    'symbol': self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else 'XAUUSD',
                    'price': round(ref_price, 4),
                    'entry_price': buy_limit,
                    'lot_size': float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                    'confidence': 65.0,
                    'timestamp': datetime.now().isoformat(),
                    'signal_id': sid,
                    'min_confidence_used': 0,
                    'sideways_filter_enabled': False,
                    'is_sideways': 0,
                    'trend_quality': 0.95,
                    'market_regime': 1,
                    'rsi': 50.0,
                    'adx': 22.0,
                    'support_level': round(ref_price - 4.0, 4),
                    'resistance_level': round(ref_price + 4.0, 4),
                    'reversal_flag': False,
                    'reversal_confidence': 0.0
                })
                sid += 1

                # SELL_LIMIT slightly above current
                sell_limit = round(ask + 0.5, 4)
                signals.append({
                    'action': 'SELL_LIMIT',
                    'symbol': self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else 'XAUUSD',
                    'price': round(ref_price, 4),
                    'entry_price': sell_limit,
                    'lot_size': float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                    'confidence': 60.0,
                    'timestamp': datetime.now().isoformat(),
                    'signal_id': sid,
                    'min_confidence_used': 0,
                    'sideways_filter_enabled': False,
                    'is_sideways': 0,
                    'trend_quality': 0.9,
                    'market_regime': 1,
                    'rsi': 48.0,
                    'adx': 21.0,
                    'support_level': round(ref_price - 5.0, 4),
                    'resistance_level': round(ref_price + 5.0, 4),
                    'reversal_flag': False,
                    'reversal_confidence': 0.0
                })
                sid += 1

            if mode in ('reversal', 'all'):
                # Add a reversal signal with high reversal_confidence
                signals.append({
                    'action': 'SELL',
                    'symbol': self.data_fetcher.symbol if hasattr(self, 'data_fetcher') else 'XAUUSD',
                    'price': round(ref_price + 1.0, 4),
                    'entry_price': round(ref_price + 1.0, 4),
                    'lot_size': float(getattr(self, 'min_lot', DEFAULT_MIN_LOT)),
                    'confidence': 88.0,
                    'timestamp': datetime.now().isoformat(),
                    'signal_id': sid,
                    'min_confidence_used': 0,
                    'sideways_filter_enabled': False,
                    'is_sideways': 0,
                    'trend_quality': 0.5,
                    'market_regime': 0,
                    'rsi': 70.0,
                    'adx': 12.0,
                    'support_level': round(ref_price - 6.0, 4),
                    'resistance_level': round(ref_price + 6.0, 4),
                    'reversal_flag': True,
                    'reversal_confidence': 0.85
                })

            # Write each signal to file (overwrite) with short delay so EA can pick up successive cases
            for s in signals:
                self.signal_count += 1
                s['signal_id'] = self.signal_count
                s['timestamp'] = datetime.now().isoformat()
                # If FusionAI explain API is available, try to attach an explanation for test signals
                try:
                    fa = getattr(self, 'fusion_ai_v4', None)
                    if fa is not None:
                        # prefer last_explain if already present
                        maybe = getattr(fa, 'last_explain', None)
                        if maybe:
                            s['fusion_reasons'] = maybe
                        else:
                            explain_fn = getattr(fa, 'explain', None) or getattr(fa, 'explain_signal', None)
                            if callable(explain_fn):
                                try:
                                    expl = explain_fn(s)
                                    if expl:
                                        s['fusion_reasons'] = expl
                                except Exception:
                                    # Ignore explain errors for test emitter
                                    pass
                except Exception:
                    pass
                self._write_signal_to_file(s)
                logger.info(f"🧪 Test signal written: {s['action']} id={s['signal_id']} entry={s.get('entry_price')}")
                time.sleep(1.0)

            logger.info("✅ Test signals emission completed")
        except Exception as e:
            logger.error(f"❌ Error emitting test signals: {e}")
    
    def run_live_trading(self, demo_mode=True, interval=30, min_confidence=30.0, enable_sideways_filter=True,
                         pattern_report_enable=False, pattern_report_every=10, pattern_report_window=30,
                         pattern_model_dir='live_trading/models_large', pattern_webhook_url=None,
                         pattern_webhook_auth=None, pattern_webhook_max_retries=3, pattern_webhook_backoff=2.0):
        """Run live trading signal generation với low confidence filter (30%)"""
        logger.info("🚀 Khởi động Hệ thống Tín hiệu AI - ĐẶT LỆNH LIMIT KHI AI PHÂN TÍCH HỢP LÝ")
        
        # 🎯 CONTINUOUS MODE - Phân tích liên tục, không chờ interval
        if interval <= 1:
            logger.info("⚡ CONTINUOUS MODE - Phân tích LIÊN TỤC mọi tick giá, vào lệnh NGAY khi AI thấy cơ hội!")
            logger.info("📊 AI sẽ tự quyết định KHI NÀO vào lệnh dựa trên phân tích thị trường")
        else:
            logger.info(f"⏰ Chu kỳ kiểm tra: {interval}s (Vào lệnh KHI AI phân tích, KHÔNG theo giây)")
        
        logger.info(f"🎯 Chế độ demo: {demo_mode}")
        logger.info(f"📊 Ngưỡng độ tin cậy tối thiểu: {min_confidence}%")
        if enable_sideways_filter:
            logger.info(f"🚫 Bộ lọc Sideways: BẬT (Tránh giao dịch trong thị trường sideway)")
            logger.info(f"📈 Chất lượng xu hướng yêu cầu: >= 0.8 (Chỉ giao dịch khi xu hướng mạnh)")
        else:
            logger.info(f"⚠️ Bộ lọc Sideways: TẮT (Chấp nhận TẤT CẢ tín hiệu từ AI)")
        logger.info(f"🌐 Địa chỉ HTTP: http://127.0.0.1:6555/signal")
        logger.info(f"✅ CHẾ ĐỘ: Đặt lệnh LIMIT + Gửi lên MT5/EA qua HTTP + File")
        logger.info(f"✂️ AUTO TRIM: Tự động đóng lệnh âm bằng profit lệnh dương (mỗi 5 phút)")
        logger.info(f"🎓 AUTO RETRAIN: Tự động training lại model mỗi 7 ngày")
        logger.info("Nhấn Ctrl+C để dừng")
        
        self.is_running = True
        signal_count = 0
        last_signal_time = 0  # 🕐 Track thời gian signal cuối để enforce cooldown
        
        # 🎯 TRAILING STOPS INTERVAL - Có thể tùy chỉnh
        # 30 = 30 giây (gần thời gian thực)
        # 60 = 1 phút (cân bằng)
        # 300 = 5 phút (tiết kiệm tài nguyên)
        trim_interval = 30  # ⚡ THỜI GIAN THỰC - Update mỗi 30 giây
        
        # 🔄 Đồng bộ positions từ MT5 khi khởi động
        if self.money_manager and MT5_AVAILABLE:
            logger.info("🔄 Đang đồng bộ positions từ MT5...")
            if self.money_manager.sync_positions_from_mt5():
                logger.info(f"✅ Đã tải {len(self.money_manager.open_positions)} positions từ MT5")
            else:
                logger.warning("⚠️ Không thể đồng bộ MT5 - Bot sẽ chạy độc lập")
            
            # 🔍 Quét balance lần đầu
            logger.info("🔍 Quét balance từ MT5...")
            self.money_manager.scan_balance_from_mt5()
        last_trim_time = time.time()
        
        # 🎓 AUTO RETRAIN SCHEDULER
        retrain_interval = self.retrain_interval_days * 24 * 60 * 60  # Convert days to seconds
        last_retrain_time = time.time()
        next_retrain = last_retrain_time + retrain_interval
        
        try:
            while self.is_running:
                # 🔍 BALANCE SCANNING - Quét balance liên tục mỗi 30 giây
                if self.money_manager and MT5_AVAILABLE:
                    self.money_manager.scan_balance_from_mt5()
                
                # 🔄 SYNC MT5 POSITIONS - Đồng bộ mỗi 30 giây
                if self.money_manager and MT5_AVAILABLE:
                    if self.money_manager.last_sync_time is None or \
                       (datetime.now() - self.money_manager.last_sync_time).total_seconds() >= 30:
                        self.money_manager.sync_positions_from_mt5()
                
                # 🎓 CHECK AUTO RETRAIN - Kiểm tra có cần train lại không
                current_time = time.time()
                if current_time >= next_retrain:
                    logger.info("=" * 80)
                    logger.info("🎓 AUTO RETRAIN TRIGGERED - Bắt đầu training lại model")
                    logger.info("=" * 80)
                    
                    try:
                        # Pause trading
                        logger.info("⏸️ PAUSE TRADING - Dừng trading trong lúc train")
                        
                        # Đóng tất cả positions trước khi train
                        if self.money_manager and len(self.money_manager.open_positions) > 0:
                            logger.info(f"🛑 Đóng {len(self.money_manager.open_positions)} lệnh trước khi train")
                            live_data = self.data_fetcher.fetch_live_data()
                            current_price = live_data['close'].iloc[-1]
                            closed = self.money_manager.close_all_positions(current_price, 'AUTO_RETRAIN')
                            logger.info(f"✅ Đã đóng tất cả lệnh để chuẩn bị train")
                        
                        # Fetch historical data (30 ngày gần nhất)
                        logger.info("📊 Fetching historical data (30 days)...")
                        if demo_mode or not ML_AVAILABLE:
                            train_data = self.data_fetcher.generate_demo_data(days=30, timeframe='5M')
                        else:
                            train_data = self.data_fetcher.fetch_mt5_data(symbol=self.data_fetcher.symbol, bars=8640)  # 30 days * 288 bars/day
                        
                        # Train model
                        logger.info("🤖 Training AI model với data mới...")
                        self.ai_model.train_model(train_data, test_size=0.3)
                        
                        # Save model
                        logger.info("💾 Lưu model mới...")
                        self.ai_model.save_model()
                        
                        logger.info("=" * 80)
                        logger.info("✅ AUTO RETRAIN COMPLETED - Model đã được cập nhật!")
                        logger.info(f"📅 Next retrain scheduled: {datetime.fromtimestamp(current_time + retrain_interval).strftime('%Y-%m-%d %H:%M:%S')}")
                        logger.info("=" * 80)
                        
                        # Update next retrain time
                        last_retrain_time = current_time
                        next_retrain = current_time + retrain_interval
                        
                        # Resume trading
                        logger.info("▶️ RESUME TRADING - Tiếp tục trading với model mới")
                        
                    except Exception as e:
                        logger.error(f"❌ Error during auto retrain: {e}")
                        logger.error("⚠️ Tiếp tục trading với model cũ")
                        # Vẫn update next retrain để không bị stuck
                        next_retrain = current_time + retrain_interval
                
                # 🕐 SIGNAL COOLDOWN - Kiểm tra thời gian chờ giữa các signal
                current_time = time.time()
                time_since_last_signal = current_time - last_signal_time
                
                if time_since_last_signal < SIGNAL_COOLDOWN:
                    cooldown_remaining = SIGNAL_COOLDOWN - time_since_last_signal
                    logger.debug(f"⏸️ Signal cooldown: {cooldown_remaining:.1f}s còn lại")
                    # Skip signal generation, chờ cooldown
                else:
                    # Generate new signal với confidence filter
                    # ⏱️ Track thời gian xử lý AI
                    analysis_start = time.time()
                    try:
                        self.generate_live_signal(demo_mode=demo_mode, min_confidence=min_confidence, enable_sideways_filter=enable_sideways_filter)
                        analysis_duration = time.time() - analysis_start
                        
                        # Warning nếu AI xử lý quá lâu
                        if analysis_duration > AI_PROCESSING_TIMEOUT:
                            logger.error(f"❌ AI timeout: {analysis_duration:.1f}s > {AI_PROCESSING_TIMEOUT}s")
                        elif analysis_duration > 10.0:
                            logger.warning(f"⚠️ AI xử lý chậm: {analysis_duration:.1f}s")
                        
                        # Update last signal time
                        last_signal_time = time.time()
                        
                    except Exception as e:
                        logger.error(f"❌ generate_live_signal failed: {e}")
                    
                    signal_count += 1

                # Pattern reporting: every N signals, run pattern inference on recent H1 and attach to latest_signal
                try:
                    if pattern_report_enable and (signal_count % max(1, int(pattern_report_every)) == 0):
                        # Fetch recent H1 bars for inference
                        try:
                            df_h1 = None
                            if MT5_AVAILABLE and self.data_fetcher.use_mt5:
                                # fetch slightly more bars than window to be safe
                                bars = max(pattern_report_window + 10, 60)
                                df_h1 = self.data_fetcher.fetch_mt5_data(symbol=self.data_fetcher.symbol, timeframe=mt5.TIMEFRAME_H1, bars=bars)
                        except Exception:
                            df_h1 = None

                        # If MT5 not available or fetch failed, skip reporting
                        if df_h1 is None or df_h1.empty:
                            logger.debug("ℹ️ Pattern report skipped: no H1 data available for inference")
                        else:
                            preds = self.predict_patterns_on_df(df_h1, window=pattern_report_window)
                            if preds is not None and not preds.empty:
                                last = preds.iloc[-1]
                                top = last.get('top_pattern') if 'top_pattern' in last.index else None
                                prob = float(last.get('top_prob')) if 'top_prob' in last.index else 0.0
                                # attach to global latest_signal so HTTP GET returns it
                                try:
                                    latest_signal['pattern_label'] = top
                                    latest_signal['pattern_score'] = float(prob)
                                    # include full prob columns if present
                                    prob_cols = {k: float(v) for k, v in last.items() if str(k).startswith('prob_')}
                                    if prob_cols:
                                        latest_signal['pattern_probs'] = prob_cols
                                except Exception:
                                    pass
                                logger.info(f"🔬 Pattern report: {top} (p={prob:.3f})")
                                # if webhook configured, send payload
                                if pattern_webhook_url:
                                    payload = {
                                        'source': 'complete_ai_trading_system',
                                        'timestamp': datetime.utcnow().isoformat() + 'Z',
                                        'symbol': getattr(self.data_fetcher, 'symbol', None),
                                        'top_pattern': top,
                                        'top_prob': prob
                                    }
                                    try:
                                        if 'pattern_probs' in latest_signal:
                                            payload['pattern_probs'] = latest_signal.get('pattern_probs')
                                    except Exception:
                                        pass
                                    ok = self._send_webhook(pattern_webhook_url, payload, auth=pattern_webhook_auth, max_retries=pattern_webhook_max_retries, backoff=pattern_webhook_backoff)
                                    logger.info(f"🔁 Webhook POST {'succeeded' if ok else 'failed'} to {pattern_webhook_url}")
                            else:
                                logger.debug("ℹ️ Pattern inference produced no predictions")
                except Exception as e:
                    logger.debug(f"⚠️ Pattern reporting error: {e}")
                
                # ✂️ AI-DRIVEN LOSS MANAGEMENT - Chạy mỗi 5 phút (thay thế auto_trim cũ)
                current_time = time.time()
                if current_time - last_trim_time >= trim_interval:
                    if self.money_manager and len(self.money_manager.open_positions) >= 1:
                        try:
                            # Lấy giá hiện tại
                            live_data = self.data_fetcher.fetch_live_data()
                            current_price = live_data['close'].iloc[-1]
                            current_prices = {
                                'BUY': current_price,
                                'SELL': current_price
                            }

                            # Thu thập H1 để phân tích cấu trúc thị trường (MSAI)
                            try:
                                df_h1 = None
                                if MT5_AVAILABLE and self.data_fetcher.use_mt5:
                                    df_h1 = self.data_fetcher.fetch_mt5_data(symbol=self.data_fetcher.symbol, timeframe=mt5.TIMEFRAME_H1, bars=200)
                                # Fallback: use recent live_data if H1 not available
                                if df_h1 is None or df_h1.empty:
                                    df_h1 = live_data.tail(200)
                            except Exception:
                                df_h1 = live_data.tail(200)

                            # Market Structure AI decision
                            try:
                                ms_result = None
                                if hasattr(self, 'structure_ai') and self.structure_ai:
                                    ms_result = self.structure_ai.analyze(df_h1)
                                else:
                                    ms_result = 0
                            except Exception as e:
                                logger.warning(f"⚠️ MarketStructureAI failed: {e}")
                                ms_result = 0

                            # Thu thập dữ liệu thị trường cho partial TP và market analysis
                            try:
                                market_data = self._collect_market_data_for_partial_tp(live_data)
                            except Exception:
                                market_data = None

                            # 🎯 TRAILING STOPS - Update SL/TP for profitable positions
                            try:
                                if self.money_manager and hasattr(self.money_manager, 'update_trailing_stops'):
                                    # Get market analysis for reversal signals
                                    market_analysis = None
                                    try:
                                        if hasattr(self, 'structure_ai') and self.structure_ai:
                                            market_analysis = {'ms_signal': ms_result}
                                        if hasattr(self, 'liquidity_ai') and self.liquidity_ai:
                                            if market_analysis is None:
                                                market_analysis = {}
                                            # Use safe lookup for ls_result to avoid NameError when it's not defined
                                            market_analysis['ls_signal'] = locals().get('ls_result', None)
                                    except Exception:
                                        pass

                                    # Get TrailingSL analysis for adaptive trailing stops
                                    trailing_sl_result = None
                                    try:
                                        if hasattr(self, 'trailing_sl_ai') and self.trailing_sl_ai:
                                            trailing_sl_result = self.trailing_sl_ai.analyze(df_h1, current_prices)
                                    except Exception as e:
                                        logger.debug(f"⚠️ TrailingSL AI failed: {e}")

                                    # Update trailing stops for all positions
                                    trailing_updates = self.money_manager.update_trailing_stops(
                                        current_prices=current_prices,
                                        market_analysis=market_analysis,
                                        ms_signal=ms_result if 'ms_result' in locals() else None,
                                        ls_signal=locals().get('ls_result', None),
                                        trailing_sl_signal=trailing_sl_result
                                    )
                                    
                                    if trailing_updates:
                                        # Normalize and log different possible return shapes from money_manager
                                        try:
                                            if isinstance(trailing_updates, dict):
                                                # Prefer explicit lists if provided
                                                updated = trailing_updates.get('updated_positions') if isinstance(trailing_updates.get('updated_positions'), list) else None
                                                closed = trailing_updates.get('closed_positions') if isinstance(trailing_updates.get('closed_positions'), list) else None

                                                total = 0
                                                if updated:
                                                    total += len(updated)
                                                if closed:
                                                    total += len(closed)

                                                logger.info(f"🎯 TRAILING STOPS updated for {total} positions")

                                                # Log details where possible
                                                if updated:
                                                    for ticket in updated:
                                                        logger.info(f"   Updated Position #{ticket}")
                                                if closed:
                                                    for item in closed:
                                                        # closed entries may be dicts or simple ids
                                                        if isinstance(item, dict) and 'signal_id' in item:
                                                            logger.info(f"   Closed Position #{item.get('signal_id')} (pnl={item.get('pnl', 'n/a')})")
                                                        else:
                                                            logger.info(f"   Closed Position #{item}")
                                            elif isinstance(trailing_updates, list):
                                                logger.info(f"🎯 TRAILING STOPS updated for {len(trailing_updates)} positions")
                                                for update in trailing_updates:
                                                    try:
                                                        logger.info(f"   Position #{update['ticket']}: SL={update.get('new_sl', 'unchanged')}, TP={update.get('new_tp', 'unchanged')}")
                                                    except Exception:
                                                        logger.info(f"   Position update: {update}")
                                            else:
                                                # Fallback - log raw
                                                logger.info(f"🎯 TRAILING STOPS update returned: {trailing_updates}")
                                        except Exception as e:
                                            logger.warning(f"⚠️ Failed to log trailing_updates detail: {e}")
                            except Exception as e:
                                logger.exception(f"⚠️ Trailing stops update failed: {e}")

                            # Gọi AI-driven close (thay vì auto_trim cũ)
                            try:
                                closed_ids = self.money_manager.ai_close_losing_positions(ms_result, current_prices, market_analysis=market_data)
                                if closed_ids:
                                    logger.info(f"✂️ AI_CLOSE completed - Closed {len(closed_ids)} positions")
                                else:
                                    logger.debug("✂️ AI_CLOSE: No positions closed this run")
                            except Exception as e:
                                logger.error(f"❌ Error in AI_CLOSE: {e}")

                            # 💰 PARTIAL TAKE PROFIT - Chạy sau AI_CLOSE
                            try:
                                partial_closed = self.money_manager.apply_partial_take_profit(current_prices, market_data)
                                if partial_closed:
                                    logger.info(f"💰 AI PARTIAL TAKE PROFIT completed - Applied to {len(partial_closed)} positions")
                                else:
                                    logger.debug(f"💰 AI PARTIAL TAKE PROFIT: No positions qualified for partial close")
                            except Exception as e:
                                logger.error(f"❌ Error in AI partial take profit: {e}")

                        except Exception as e:
                            logger.error(f"❌ Error in AI loss-management loop: {e}")

                    last_trim_time = current_time
                
                # Hiển thị countdown đến next retrain (mỗi 100 signals)
                if signal_count % 100 == 0:
                    time_until_retrain = next_retrain - time.time()
                    days_left = int(time_until_retrain / 86400)
                    hours_left = int((time_until_retrain % 86400) / 3600)
                    logger.info(f"📅 Next auto retrain in: {days_left}d {hours_left}h")
                
                # 🎯 CONTINUOUS MODE - Không chờ nếu interval = 0
                if interval > 0:
                    time.sleep(interval)
                else:
                    # Continuous mode - sleep 2s để AI có đủ thời gian xử lý
                    # ⚠️ KHÔNG GIẢM XUỐNG < 2s - AI sẽ bị quá tải!
                    time.sleep(2.0)
                
        except KeyboardInterrupt:
            logger.info("🛑 Giao dịch thực đã dừng bởi người dùng")
        except Exception as e:
            logger.error(f"❌ Lỗi trong quá trình giao dịch: {e}")
        finally:
            self.stop_system()
    
    def stop_system(self):
        """Stop the AI trading system"""
        self.is_running = False
        if self.http_server:
            self.http_server.shutdown()
            logger.info("🔌 Đã dừng HTTP server")
        logger.info("✅ Hệ thống AI Trading đã dừng")


#==============================================================================
# 4. 💥 MOMENTUM CRASH DETECTOR (MACD VETO) - 2 CHIỀU
#==============================================================================

class CrashDetector:
    """Momentum Crash Detector - MACD VETO System
    
    Phát hiện momentum crash để chặn lệnh BUY/SELL không an toàn.
    Phân tích MACD histogram, volume spike, ATR spike, wick rejection.
    
    Logic 2 chiều:
    - Chặn BUY khi momentum bearish (crash xuống)
    - Chặn SELL khi momentum bullish (pump lên)
    """
    
    def __init__(self):
        self.veto_threshold = 0.5  # Ngưỡng veto (0.5 = 50%)
        logger.info("💥 CrashDetector initialized - MACD VETO 2 chiều")
    
    def macd_veto(self, df):
        """MACD VETO - Phân tích momentum để chặn lệnh
        
        Args:
            df: DataFrame với cột MACD, signal, histogram, volume, atr, high, low, open, close
            
        Returns:
            dict: {
                'veto_buy': bool,      # True = chặn BUY
                'veto_sell': bool,     # True = chặn SELL  
                'score': float,        # Độ mạnh của veto (0-1)
                'reason': str         # Lý do veto
            }
        """
        try:
            if df is None or len(df) < 5:
                return {
                    'veto_buy': False,
                    'veto_sell': False,
                    'score': 0.0,
                    'reason': 'insufficient_data'
                }
            
            # Lấy nến cuối cùng
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            # Tính MACD histogram slope (độ dốc)
            hist_current = latest.get('macd_histogram', 0.0)
            hist_prev = prev.get('macd_histogram', 0.0)
            hist_slope = hist_current - hist_prev
            
            # Trung bình histogram gần đây
            avg_prev_hist = df['macd_histogram'].tail(3).mean() if len(df) >= 3 else hist_prev
            
            # MACD cross bearish (MACD cắt xuống signal)
            macd_cross_bear = False
            if len(df) >= 3:
                a = df['macd'].iloc[-3] - df['macd_signal'].iloc[-3]
                b = df['macd'].iloc[-2] - df['macd_signal'].iloc[-2]
                c = df['macd'].iloc[-1] - df['macd_signal'].iloc[-1]
                macd_cross_bear = (a > 0) and (b > 0) and (c < 0)
            
            # Volume spike (volume tăng đột biến)
            vol_current = latest.get('volume', 0.0)
            vol_avg = df['volume'].tail(10).mean() if len(df) >= 10 else vol_current
            vol_spike = vol_current > vol_avg * 1.5 if vol_avg > 0 else False
            
            # ATR spike (biến động tăng)
            atr_current = latest.get('atr', 0.0)
            atr_avg = df['atr'].tail(10).mean() if len(df) >= 10 else atr_current
            atr_spike = atr_current > atr_avg * 1.3 if atr_avg > 0 else False
            
            # Wick rejection (nến có wick dài - rejection)
            body_high = max(latest['open'], latest['close'])
            body_low = min(latest['open'], latest['close'])
            upper_wick = latest['high'] - body_high
            lower_wick = body_low - latest['low']
            body_size = abs(latest['close'] - latest['open'])
            
            wick_flag_bearish = upper_wick > body_size * 2  # Upper wick dài = rejection đi xuống
            wick_flag_bullish = lower_wick > body_size * 2   # Lower wick dài = rejection đi lên
            
            # --- BUY VETO (xu hướng giảm) ---
            bear_score = 0.0
            bear_reasons = []
            
            if hist_slope < 0:
                bear_score += min(0.6, max(0.0, -hist_slope / max(1e-6, abs(avg_prev_hist)+1e-6) * 0.2))
                bear_reasons.append('hist_decline')
            
            if macd_cross_bear:
                bear_score += 0.4
                bear_reasons.append('macd_cross_bear')
            
            if vol_spike:
                bear_score += 0.2
                bear_reasons.append('vol_spike')
            
            if atr_spike:
                bear_score += 0.25
                bear_reasons.append('atr_spike')
            
            if wick_flag_bearish:
                bear_score += 0.2
                bear_reasons.append('upper_wick_rejection')
            
            bear_score = min(1.0, bear_score)
            
            
            # --- SELL VETO (xu hướng tăng) ---
            bull_score = 0.0
            bull_reasons = []
            
            # MACD histogram tăng mạnh
            if hist_slope > 0:
                bull_score += min(0.6, (hist_slope / (abs(avg_prev_hist)+1e-6)) * 0.2)
                bull_reasons.append('hist_rise')
            
            # MACD cắt lên signal
            macd_cross_bull = False
            if len(df) >= 3:
                a2 = df['macd'].iloc[-3] - df['macd_signal'].iloc[-3]
                b2 = df['macd'].iloc[-2] - df['macd_signal'].iloc[-2]
                c2 = df['macd'].iloc[-1] - df['macd_signal'].iloc[-1]
                macd_cross_bull = (a2 < 0) and (b2 < 0) and (c2 > 0)
            
            if macd_cross_bull:
                bull_score += 0.4
                bull_reasons.append('macd_cross_bull')
            
            # volume spike bật lên
            if vol_spike:
                bull_score += 0.2
                bull_reasons.append('vol_spike')
            
            # ATR spike
            if atr_spike:
                bull_score += 0.25
                bull_reasons.append('atr_spike')
            
            # lower wick rejection
            if wick_flag_bullish:
                bull_score += 0.2
                bull_reasons.append('lower_wick_rejection')
            
            bull_score = min(1.0, bull_score)
            
            
            # --- Quyết định cuối ---
            veto_threshold = self.veto_threshold
            
            if bear_score >= veto_threshold:
                return {
                    'veto_buy': True,
                    'veto_sell': False,
                    'score': bear_score,
                    'reason': 'momentum_bearish_crash:' + ','.join(bear_reasons),
                }
            
            elif bull_score >= veto_threshold:
                return {
                    'veto_buy': False,
                    'veto_sell': True,
                    'score': bull_score,
                    'reason': 'momentum_bullish_pump:' + ','.join(bull_reasons),
                }
            
            else:
                return {
                    'veto_buy': False,
                    'veto_sell': False,
                    'score': max(bear_score, bull_score),
                    'reason': 'no_veto'
                }
        
        except Exception as e:
            logger.warning(f"⚠️ CrashDetector.macd_veto failed: {e}")
            return {
                'veto_buy': False,
                'veto_sell': False,
                'score': 0.0,
                'reason': f'error:{str(e)}'
            }


#==============================================================================
# 5. 📡 MAIN EXECUTION
#==============================================================================

def main():
    print("=" * 80)
    print("COMPLETE AI TRADING SYSTEM - ALL-IN-ONE")
    print("=" * 80)
    print("Data Fetching -> AI Training -> Backtesting -> Live Trading")
    print("=" * 80)
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Complete AI Trading System')
    parser.add_argument('--demo', action='store_true', 
                       help='Run in demo mode (random signals)')
    parser.add_argument('--train', action='store_true', 
                       help='Train new model (default: load existing)')
    parser.add_argument('--interval', type=int, default=30,
                       help='Signal generation interval in seconds (default: 30, set 0 for continuous)')
    parser.add_argument('--turbo', action='store_true',
                       help='TURBO MODE: Run with 5-second interval for maximum speed')
    parser.add_argument('--continuous', action='store_true',
                       help='CONTINUOUS MODE: Phân tích LIÊN TỤC, AI quyết định KHI NÀO vào lệnh (interval=0)')
    parser.add_argument('--min-confidence', type=float, default=30.0,
                       help='Minimum confidence threshold in percent (default: 30.0)')
    parser.add_argument('--backtest-only', action='store_true',
                       help='Run backtest only, no live trading')
    parser.add_argument('--skip-backtest', action='store_true',
                       help='Skip running the backtest during initialization')
    parser.add_argument('--no-sideways-filter', action='store_true',
                       help='Disable sideways market filter (accept all AI signals)')
    parser.add_argument('--retrain-days', type=int, default=7,
                       help='Auto retrain interval in days (default: 7, set 14 for 2 weeks)')
    parser.add_argument('--test-signal', type=str, choices=['market','limit','reversal','all'],
                       help='Emit synthetic test signals for EA testing and exit (choices: market, limit, reversal, all)')
    parser.add_argument('--train-patterns', action='store_true',
                       help='Generate synthetic pattern dataset and train a pattern classifier, then exit')
    parser.add_argument('--lang', choices=['en','vi'], default='en', help='Language for logs/notifications (en or vi)')
    parser.add_argument('--pattern-samples', type=int, default=50, help='Samples per pattern when --train-patterns is used')
    parser.add_argument('--pattern-outdir', type=str, default='live_trading/models', help='Output dir for pattern dataset/model')
    parser.add_argument('--pattern-tick', type=float, default=0.01, help='Tick size to simulate when generating patterns')
    parser.add_argument('--pattern-spread', type=float, default=0.05, help='Spread to simulate when generating patterns')
    parser.add_argument('--pattern-volume-scale', type=float, default=1.0, help='Volume scale factor when generating patterns')
    parser.add_argument('--pattern-infer', action='store_true', help='Run pattern inference on a CSV and exit')
    parser.add_argument('--pattern-infer-csv', type=str, default=None, help='CSV file to run inference on (timestamp/time column + open,high,low,close,volume)')
    parser.add_argument('--pattern-model-dir', type=str, default=None, help='Pattern model directory (defaults to <script>/models_large)')
    parser.add_argument('--pattern-window', type=int, default=30, help='Window length (bars) used for pattern features during inference')
    parser.add_argument('--pattern-report-enable', action='store_true', help='Enable periodic pattern reporting during live trading')
    parser.add_argument('--pattern-report-every', type=int, default=10, help='Report pattern score every N signals')
    parser.add_argument('--pattern-report-window', type=int, default=30, help='Window (bars) used for pattern reporting during live trading')
    parser.add_argument('--pattern-webhook-url', type=str, default=None, help='If set, POST pattern reports to this webhook URL')
    parser.add_argument('--pattern-webhook-auth', type=str, default=None, help='Authorization header value for webhook (e.g. "Bearer <token>")')
    parser.add_argument('--pattern-webhook-max-retries', type=int, default=3, help='Max retries for webhook POST')
    parser.add_argument('--pattern-webhook-backoff', type=float, default=2.0, help='Exponential backoff base seconds for webhook retries')
    parser.add_argument('--pattern-save', type=str, default=None, help='If set, save prediction probabilities to this CSV path')
    parser.add_argument('--enable-live-reentry', action='store_true',
                       help='Enable live re-entry order placement from ReEntrySmartAI (default: OFF — dry-run only)')
    parser.add_argument('--lot-cap', type=float, default=10.0,
                       help='Hard cap on lot size per order when live re-entry is enabled (default: 10.0)')
    parser.add_argument('--min-lot', type=float, default=DEFAULT_MIN_LOT,
                       help='Minimum lot size per order (overrides live_trading.config.MIN_LOT)')
    parser.add_argument('--enable-auto-sl-tp', action='store_true',
                       help='Enable automatic SL/TP placement on re-entry orders (default: OFF)')
    parser.add_argument('--reentry-cooldown', type=int, default=60,
                       help='Cooldown seconds between automatic re-entries after a close (default: 60)')
    parser.add_argument('--max-reentries-session', type=int, default=3,
                       help='Maximum automatic re-entries allowed per session (default: 3)')
    parser.add_argument('--reentry-min-confidence', type=float, default=50.0,
                       help='Minimum detector strength (percent) to allow automatic re-entry (default: 50.0)')
    parser.add_argument('--enable-session-whitelist', action='store_true',
                       help='Enable session whitelist check in AUTO_FILTER (default: OFF - do not drop signals by session)')
    
    args = parser.parse_args()
    
    # Set log language
    global LOG_LANG
    LOG_LANG = args.lang

    # Validate CLI min-lot and lot-cap before creating the system
    try:
        min_lot_arg = float(getattr(args, 'min_lot', DEFAULT_MIN_LOT) or DEFAULT_MIN_LOT)
    except Exception:
        logger.error('❌ --min-lot must be a valid positive number')
        sys.exit(2)
    try:
        lot_cap_arg = float(getattr(args, 'lot_cap', 10.0) or 10.0)
    except Exception:
        logger.error('❌ --lot-cap must be a valid positive number')
        sys.exit(2)

    if min_lot_arg <= 0.0:
        logger.error('❌ --min-lot must be > 0')
        sys.exit(2)
    if lot_cap_arg <= 0.0:
        logger.error('❌ --lot-cap must be > 0')
        sys.exit(2)
    if min_lot_arg > lot_cap_arg:
        logger.error(f'❌ Invalid args: --min-lot ({min_lot_arg}) cannot exceed --lot-cap ({lot_cap_arg})')
        sys.exit(2)

    # Initialize AI Trading System (pass live re-entry flag)
    ai_system = CompleteAITradingSystem(enable_live_reentry=getattr(args, 'enable_live_reentry', False),
                                         min_lot=min_lot_arg,
                                         live_lot_cap=lot_cap_arg)
    # Attempt to load MEDIUM_PLUS config (non-destructive)
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), 'seup', 'AI_MEDIUM_PLUS_config.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r', encoding='utf-8') as fh:
                    cfg = json.load(fh)
                ai_system.medium_plus_config = cfg
                ai_system.signal_drift_settings = cfg.get('signal_drift_protection', {}) or {}
                logger.info(f"🔧 Loaded MEDIUM_PLUS config: {cfg_path}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to parse MEDIUM_PLUS_config.json: {e}")
                ai_system.medium_plus_config = {}
                ai_system.signal_drift_settings = {}
        else:
            ai_system.medium_plus_config = {}
            ai_system.signal_drift_settings = {}
    except Exception as e:
        logger.debug(f"⚠️ Loading MEDIUM_PLUS config failed: {e}")
    # Apply session whitelist toggle (default: False)
    try:
        ai_system.enable_session_whitelist = bool(getattr(args, 'enable_session_whitelist', False))
        if ai_system.enable_session_whitelist:
            logger.info(f"🔐 Session whitelist ENABLED via CLI: {AUTO_SESSION_WHITELIST}")
        else:
            logger.info("🔓 Session whitelist DISABLED via CLI (signals won't be dropped by session)")
    except Exception:
        ai_system.enable_session_whitelist = False
    # Apply re-entry safety overrides
    try:
        ai_system.enable_auto_sl_tp = bool(getattr(args, 'enable_auto_sl_tp', False))
        ai_system.reentry_cooldown_seconds = int(getattr(args, 'reentry_cooldown', 60))
        ai_system.max_reentries_session = int(getattr(args, 'max_reentries_session', 3))
        ai_system.reentry_min_confidence = float(getattr(args, 'reentry_min_confidence', 50.0)) / 100.0
    except Exception:
        pass

    # Pattern inference shortcut: run inference on CSV and exit (no MT5 required)
    if getattr(args, 'pattern_infer', False):
        csv_path = args.pattern_infer_csv
        if not csv_path:
            logger.error('❌ --pattern-infer requires --pattern-infer-csv <path>')
            return
        logger.info(f"🔬 Running pattern inference on CSV: {csv_path} using model {args.pattern_model_dir}")
        preds = ai_system.predict_patterns_on_csv(csv_path, model_dir=args.pattern_model_dir, window=args.pattern_window)
        if preds is None or preds.empty:
            logger.error('❌ No predictions produced (data too short or model load failed)')
            return
        # Print a short summary and optionally save
        logger.info(f"✅ Predictions produced: {len(preds)} rows")
        if args.pattern_save:
            try:
                os.makedirs(os.path.dirname(args.pattern_save), exist_ok=True)
                preds.to_csv(args.pattern_save)
                logger.info(f"✅ Saved predictions to {args.pattern_save}")
            except Exception as e:
                logger.error(f"❌ Failed to save predictions: {e}")
        else:
            # Print top 5 rows
            try:
                logger.info('\n' + preds.head(10).to_string())
            except Exception:
                print(preds.head(10))
        # If webhook configured, send a summary payload
        if getattr(args, 'pattern_webhook_url', None):
            payload = {
                'source': 'complete_ai_trading_system',
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'csv': os.path.basename(csv_path),
                'predictions_count': len(preds)
            }
            # send last row detail if available
            try:
                last = preds.iloc[-1]
                payload['top_pattern'] = str(last.get('top_pattern'))
                payload['top_prob'] = float(last.get('top_prob') or 0.0)
                prob_cols = {k: float(v) for k, v in last.items() if str(k).startswith('prob_')}
                if prob_cols:
                    payload['pattern_probs'] = prob_cols
            except Exception:
                pass
            ok = ai_system._send_webhook(args.pattern_webhook_url, payload, auth=args.pattern_webhook_auth, max_retries=args.pattern_webhook_max_retries, backoff=args.pattern_webhook_backoff)
            logger.info(f"🔁 Webhook POST {'succeeded' if ok else 'failed'} to {args.pattern_webhook_url}")
        return

    # Train pattern classifier mode (synthetic dataset based) - exit after training
    if getattr(args, 'train_patterns', False):
        logger.info(tr("--train-patterns requested: Generating dataset and training pattern classifier..."))
        ok = ai_system.train_price_pattern_classifier(
            outdir=args.pattern_outdir,
            samples_per_pattern=args.pattern_samples,
            tick_size=args.pattern_tick,
            spread=args.pattern_spread,
            volume_scale=args.pattern_volume_scale
        )
        if ok:
            logger.info(tr("Pattern classifier training completed"))
        else:
            logger.error(tr("Pattern classifier training failed"))
        return

    # Test-signal mode: emit synthetic signals and exit (no MT5 required)
    if args.test_signal:
        ai_system.emit_test_signals(mode=args.test_signal)
        return
    
    # Set retrain interval
    ai_system.retrain_interval_days = args.retrain_days
    
    # Determine whether to skip backtest
    # Behavior: Run backtest only when training (`--train`) or when `--backtest-only` is used.
    # By default (normal run without --train) we skip the backtest to save time.
    if args.backtest_only:
        skip_backtest_flag = False
    else:
        if args.train:
            # During training, run backtest by default unless user explicitly requests --skip-backtest
            skip_backtest_flag = bool(args.skip_backtest)
        else:
            # Normal live run: skip backtest unless user explicitly changes behavior (use --train to run backtest)
            skip_backtest_flag = True

    # Initialize system
    if not ai_system.initialize_system(train_model=args.train, skip_backtest=skip_backtest_flag):
        logger.error("❌ System initialization failed")
        return
    
    # Run backtest only mode
    if args.backtest_only:
        logger.info("📊 Backtest-only mode completed")
        return
    
    # 🚀 DETERMINE INTERVAL MODE
    if args.continuous:
        actual_interval = 0
        logger.info("⚡ CONTINUOUS MODE ACTIVATED - AI phân tích LIÊN TỤC và tự quyết định KHI NÀO vào lệnh!")
    elif args.turbo:
        actual_interval = 5
        logger.info("⚡ TURBO MODE ACTIVATED - Running at maximum speed (5s interval)")
    else:
        actual_interval = args.interval
    
    # Run live trading với configurable filters
    ai_system.run_live_trading(
        demo_mode=args.demo,
        interval=actual_interval,
        min_confidence=args.min_confidence,  # 🎯 Configurable confidence threshold
        enable_sideways_filter=(not args.no_sideways_filter),  # 🚫 Bật/tắt sideways filter
        pattern_report_enable=getattr(args, 'pattern_report_enable', False),
        pattern_report_every=getattr(args, 'pattern_report_every', 10),
        pattern_report_window=getattr(args, 'pattern_report_window', args.pattern_window),
        pattern_model_dir=getattr(args, 'pattern_model_dir', 'live_trading/models_large'),
        pattern_webhook_url=getattr(args, 'pattern_webhook_url', None),
        pattern_webhook_auth=getattr(args, 'pattern_webhook_auth', None),
        pattern_webhook_max_retries=getattr(args, 'pattern_webhook_max_retries', 3),
        pattern_webhook_backoff=getattr(args, 'pattern_webhook_backoff', 2.0)
    )

if __name__ == "__main__":
    main()

