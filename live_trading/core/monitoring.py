"""
Monitoring Module - System Resource and Crash Detection
=======================================================
Provides CPU/memory monitoring and momentum crash detection
"""

import time
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Try to import psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except Exception:
    PSUTIL_AVAILABLE = False

# Runtime mode flags (can be adjusted by cpu_monitor)
CPU_MONITOR_ENABLED = True
ultra_mode = True
superlight_mode = False
safe_mode = False

# Thresholds (percentage)
CPU_HIGH_THRESHOLD = 85.0
CPU_MEDIUM_THRESHOLD = 45.0
MEMORY_HIGH_PERCENT = 92.0


def cpu_monitor(poll_interval=5, cpu_high=CPU_HIGH_THRESHOLD, cpu_medium=CPU_MEDIUM_THRESHOLD):
    """Daemon thread monitoring CPU and memory, automatically switches global modes.

    Notes:
    - Runs in "best-effort" mode: if psutil is unavailable or errors occur,
      function will exit silently without breaking the main program.
    - Global variables `ultra_mode`, `superlight_mode`, `safe_mode` are updated
      based on resource status so other parts of the system can adjust frequency
      or disable trading when needed.
    """
    global ultra_mode, superlight_mode, safe_mode
    if not PSUTIL_AVAILABLE or not CPU_MONITOR_ENABLED:
        return
    try:
        prev_state = (ultra_mode, superlight_mode, safe_mode)
        while True:
            # psutil.cpu_percent with interval=1 returns sample over 1s
            cpu = psutil.cpu_percent(interval=1)
            try:
                mem = psutil.virtual_memory().percent
            except Exception:
                mem = 0.0

            if cpu >= cpu_high or mem >= MEMORY_HIGH_PERCENT:
                # High load: enter safe_mode (pause trading) and enable superlight
                safe_mode = True
                superlight_mode = True
                ultra_mode = False
            elif cpu >= cpu_medium:
                # Medium load: limit heavy computations, allow limited trading
                safe_mode = False
                superlight_mode = True
                ultra_mode = False
            else:
                # Normal: prefer ultra - if CPU drops, SWITCH TO ULTRA
                safe_mode = False
                ultra_mode = True
                superlight_mode = False

            # Log when runtime mode changes for easier observation
            try:
                current_state = (ultra_mode, superlight_mode, safe_mode)
                if current_state != prev_state:
                    logger.debug(f"🔁 Runtime mode changed: ultra={ultra_mode}, superlight={superlight_mode}, safe={safe_mode} (CPU={cpu:.1f}%, MEM={mem:.1f}%)")
                    prev_state = current_state
            except Exception:
                pass

            time.sleep(poll_interval)
    except Exception:
        # Catch any exception gently - monitoring is best-effort
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


class CrashDetector:
    """Momentum Crash Detector - MACD VETO System
    
    Detects momentum crashes to block unsafe BUY/SELL orders.
    Analyzes MACD histogram, volume spike, ATR spike, wick rejection.
    
    Bidirectional logic:
    - Block BUY when momentum is bearish (crash down)
    - Block SELL when momentum is bullish (pump up)
    """
    
    def __init__(self):
        self.veto_threshold = 0.5  # Veto threshold (0.5 = 50%)
        logger.info("💥 CrashDetector initialized - MACD VETO bidirectional")
    
    def macd_veto(self, df):
        """MACD VETO - Analyze momentum to block orders
        
        Args:
            df: DataFrame with columns MACD, signal, histogram, volume, atr, high, low, open, close
            
        Returns:
            dict: {
                'veto_buy': bool,      # True = block BUY
                'veto_sell': bool,     # True = block SELL  
                'score': float,        # Veto strength (0-1)
                'reason': str         # Veto reason
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
            
            # Get latest candle
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            # Calculate MACD histogram slope
            hist_current = latest.get('macd_histogram', 0.0)
            hist_prev = prev.get('macd_histogram', 0.0)
            hist_slope = hist_current - hist_prev
            
            # Recent histogram average
            avg_prev_hist = df['macd_histogram'].tail(3).mean() if len(df) >= 3 else hist_prev
            
            # MACD cross bearish (MACD cuts down signal)
            macd_cross_bear = False
            if len(df) >= 3:
                a = df['macd'].iloc[-3] - df['macd_signal'].iloc[-3]
                b = df['macd'].iloc[-2] - df['macd_signal'].iloc[-2]
                c = df['macd'].iloc[-1] - df['macd_signal'].iloc[-1]
                macd_cross_bear = (a > 0) and (b > 0) and (c < 0)
            
            # Volume spike (volume surge)
            vol_current = latest.get('volume', 0.0)
            vol_avg = df['volume'].tail(10).mean() if len(df) >= 10 else vol_current
            vol_spike = vol_current > vol_avg * 1.5 if vol_avg > 0 else False
            
            # ATR spike (volatility increase)
            atr_current = latest.get('atr', 0.0)
            atr_avg = df['atr'].tail(10).mean() if len(df) >= 10 else atr_current
            atr_spike = atr_current > atr_avg * 1.3 if atr_avg > 0 else False
            
            # Wick rejection (long wick candle - rejection)
            body_high = max(latest['open'], latest['close'])
            body_low = min(latest['open'], latest['close'])
            upper_wick = latest['high'] - body_high
            lower_wick = body_low - latest['low']
            body_size = abs(latest['close'] - latest['open'])
            
            wick_flag_bearish = upper_wick > body_size * 2  # Long upper wick = rejection downward
            wick_flag_bullish = lower_wick > body_size * 2   # Long lower wick = rejection upward
            
            # --- BUY VETO (bearish trend) ---
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
            
            
            # --- SELL VETO (bullish trend) ---
            bull_score = 0.0
            bull_reasons = []
            
            # MACD histogram rising strongly
            if hist_slope > 0:
                bull_score += min(0.6, (hist_slope / (abs(avg_prev_hist)+1e-6)) * 0.2)
                bull_reasons.append('hist_rise')
            
            # MACD cuts up signal
            macd_cross_bull = False
            if len(df) >= 3:
                a2 = df['macd'].iloc[-3] - df['macd_signal'].iloc[-3]
                b2 = df['macd'].iloc[-2] - df['macd_signal'].iloc[-2]
                c2 = df['macd'].iloc[-1] - df['macd_signal'].iloc[-1]
                macd_cross_bull = (a2 < 0) and (b2 < 0) and (c2 > 0)
            
            if macd_cross_bull:
                bull_score += 0.4
                bull_reasons.append('macd_cross_bull')
            
            # volume spike upward
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
            
            
            # --- Final decision ---
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
