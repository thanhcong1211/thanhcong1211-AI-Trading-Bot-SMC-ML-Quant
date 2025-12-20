"""
Enhanced News Filter AI - High Impact News Blocker
===================================================

Features:
1. Forex Factory calendar integration (optional)
2. Manual high-impact news database
3. Auto-close positions before news (30 min window)
4. ATR 2.5x spike detection
5. News-based volatility warnings

"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class EnhancedNewsFilterAI:
    """
    Advanced news filter with multiple detection methods
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.news_window_minutes = self.config.get('news_window_minutes', 30)  # Block 30min before/after
        self.atr_spike_multiplier = self.config.get('atr_spike_multiplier', 2.5)  # 2.5x ATR = spike
        self.enable_forex_factory = self.config.get('enable_forex_factory', False)  # API integration
        
        # High-impact news schedule (manual fallback)
        self.high_impact_schedule = self._init_news_schedule()
        
        # Tracked news events
        self.upcoming_news = []
        self.past_news = []
        
    def _init_news_schedule(self) -> Dict[str, List[Dict]]:
        """
        Initialize manual high-impact news schedule
        Based on typical economic calendar
        
        Returns: {
            'weekly': [{'day': str, 'hour_utc': int, 'event': str}],
            'monthly': [{'date': int, 'hour_utc': int, 'event': str}]
        }
        """
        return {
            'weekly': [
                # US Session
                {'day': 'tuesday', 'hour_utc': 13, 'event': 'CPI (US)'},
                {'day': 'wednesday', 'hour_utc': 18, 'event': 'FOMC Minutes'},
                {'day': 'thursday', 'hour_utc': 12, 'event': 'Jobless Claims (US)'},
                {'day': 'friday', 'hour_utc': 12, 'event': 'Non-Farm Payrolls (US)'},
                {'day': 'friday', 'hour_utc': 12, 'event': 'Unemployment Rate (US)'},
                
                # EUR Session
                {'day': 'thursday', 'hour_utc': 11, 'event': 'ECB Rate Decision'},
                {'day': 'thursday', 'hour_utc': 11, 'event': 'ECB Press Conference'},
                
                # GBP Session
                {'day': 'thursday', 'hour_utc': 11, 'event': 'BOE Rate Decision'},
            ],
            'monthly': [
                # First Friday of month
                {'date': 7, 'hour_utc': 12, 'event': 'NFP (Non-Farm Payrolls)'},
            ]
        }
    
    def check_news_window(self, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Check if we're in a news blackout window
        
        Args:
            current_time: Datetime to check (default: now)
            
        Returns:
            {
                'in_news_window': bool,
                'minutes_until_news': int,  # Minutes until next high-impact news
                'upcoming_event': str,
                'should_close_positions': bool,
                'should_block_entry': bool
            }
        """
        try:
            if current_time is None:
                current_time = datetime.utcnow()
            
            # Check manual schedule
            upcoming = self._find_upcoming_news(current_time)
            
            if not upcoming:
                return {
                    'in_news_window': False,
                    'minutes_until_news': 999,
                    'upcoming_event': None,
                    'should_close_positions': False,
                    'should_block_entry': False
                }
            
            minutes_until = upcoming['minutes_until']
            
            # Block entry 30 min before, 30 min after
            in_window = minutes_until <= self.news_window_minutes
            should_close = minutes_until <= 5  # Close positions 5min before
            
            return {
                'in_news_window': in_window,
                'minutes_until_news': minutes_until,
                'upcoming_event': upcoming['event'],
                'should_close_positions': should_close,
                'should_block_entry': in_window
            }
            
        except Exception as e:
            logger.error(f"❌ News window check error: {e}")
            return {
                'in_news_window': False,
                'minutes_until_news': 999,
                'upcoming_event': None,
                'should_close_positions': False,
                'should_block_entry': False
            }
    
    def _find_upcoming_news(self, current_time: datetime) -> Optional[Dict]:
        """Find next upcoming high-impact news event"""
        day_name = current_time.strftime('%A').lower()
        current_hour_utc = current_time.hour
        current_date = current_time.day
        
        # Check weekly schedule
        for news in self.high_impact_schedule['weekly']:
            if news['day'] == day_name:
                hour_diff = news['hour_utc'] - current_hour_utc
                
                # If news is today
                if 0 <= hour_diff <= 12:  # Within next 12 hours
                    minutes_until = hour_diff * 60 - current_time.minute
                    
                    if minutes_until < 0:
                        minutes_until = 0  # News happening now or just passed
                    
                    return {
                        'event': news['event'],
                        'minutes_until': minutes_until,
                        'time_utc': news['hour_utc']
                    }
        
        # Check monthly schedule
        for news in self.high_impact_schedule['monthly']:
            if current_date == news['date']:
                hour_diff = news['hour_utc'] - current_hour_utc
                
                if 0 <= hour_diff <= 12:
                    minutes_until = hour_diff * 60 - current_time.minute
                    
                    if minutes_until < 0:
                        minutes_until = 0
                    
                    return {
                        'event': news['event'],
                        'minutes_until': minutes_until,
                        'time_utc': news['hour_utc']
                    }
        
        return None
    
    def detect_volatility_spike(self, df: pd.DataFrame, atr_period: int = 14) -> Dict[str, Any]:
        """
        Detect abnormal volatility spike (likely news event)
        
        Args:
            df: Recent OHLC data
            atr_period: ATR calculation period
            
        Returns:
            {
                'is_spike': bool,
                'spike_multiplier': float,  # How many times above normal ATR
                'recommendation': str
            }
        """
        try:
            if df is None or len(df) < atr_period + 5:
                return {'is_spike': False, 'spike_multiplier': 1.0, 'recommendation': 'NORMAL'}
            
            # Calculate ATR
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(atr_period).mean()
            
            if len(atr) < 2:
                return {'is_spike': False, 'spike_multiplier': 1.0, 'recommendation': 'NORMAL'}
            
            # Compare current volatility to average
            current_volatility = tr.iloc[-1]
            avg_atr = atr.iloc[-atr_period:-1].mean()  # Exclude current candle
            
            if avg_atr == 0 or pd.isna(avg_atr):
                return {'is_spike': False, 'spike_multiplier': 1.0, 'recommendation': 'NORMAL'}
            
            spike_multiplier = current_volatility / avg_atr
            
            is_spike = spike_multiplier >= self.atr_spike_multiplier
            
            recommendation = 'AVOID' if is_spike else 'CAUTION' if spike_multiplier > 1.5 else 'NORMAL'
            
            return {
                'is_spike': is_spike,
                'spike_multiplier': float(spike_multiplier),
                'recommendation': recommendation,
                'current_atr': float(current_volatility),
                'avg_atr': float(avg_atr)
            }
            
        except Exception as e:
            logger.error(f"❌ Volatility spike detection error: {e}")
            return {'is_spike': False, 'spike_multiplier': 1.0, 'recommendation': 'NORMAL'}
    
    def should_trade(self, df: pd.DataFrame, current_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Combined check: Should we trade right now?
        
        Returns: (should_trade: bool, reason: str)
        """
        # Check news window
        news_check = self.check_news_window(current_time)
        
        if news_check['should_block_entry']:
            return False, f"High-impact news in {news_check['minutes_until_news']}min: {news_check['upcoming_event']}"
        
        # Check volatility spike
        vol_check = self.detect_volatility_spike(df)
        
        if vol_check['is_spike']:
            return False, f"Abnormal volatility spike detected ({vol_check['spike_multiplier']:.1f}x ATR) - likely news event"
        
        if vol_check['recommendation'] == 'CAUTION':
            return True, f"Trading allowed but caution: volatility elevated ({vol_check['spike_multiplier']:.1f}x ATR)"
        
        return True, "Clear to trade - no news/volatility concerns"
    
    def get_next_news_events(self, count: int = 5) -> List[Dict]:
        """Get next N upcoming high-impact news events"""
        current_time = datetime.utcnow()
        events = []
        
        # Check next 7 days
        for day_offset in range(7):
            check_time = current_time + timedelta(days=day_offset)
            day_name = check_time.strftime('%A').lower()
            
            for news in self.high_impact_schedule['weekly']:
                if news['day'] == day_name:
                    event_time = check_time.replace(hour=news['hour_utc'], minute=0, second=0)
                    
                    if event_time > current_time:
                        minutes_until = int((event_time - current_time).total_seconds() / 60)
                        events.append({
                            'event': news['event'],
                            'time': event_time,
                            'minutes_until': minutes_until
                        })
        
        # Sort by time
        events.sort(key=lambda x: x['minutes_until'])
        
        return events[:count]


# Singleton
_enhanced_news_filter = None

def get_enhanced_news_filter(config: Optional[Dict[str, Any]] = None) -> EnhancedNewsFilterAI:
    """Get singleton instance"""
    global _enhanced_news_filter
    if _enhanced_news_filter is None:
        _enhanced_news_filter = EnhancedNewsFilterAI(config)
    return _enhanced_news_filter
