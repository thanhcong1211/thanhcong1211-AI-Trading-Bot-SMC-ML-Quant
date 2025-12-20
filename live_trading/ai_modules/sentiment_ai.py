"""
SentimentAI - Price Action Sentiment Analysis Module
Analyzes market sentiment through price action patterns and momentum indicators
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional
import logging

logger = logging.getLogger(__name__)

class SentimentAI:
    """
    Advanced sentiment analysis using price action and momentum indicators
    """

    def __init__(self):
        """Initialize SentimentAI with default parameters"""
        self.momentum_period = 14
        self.sentiment_threshold = 0.1  # Threshold for sentiment classification
        self.lookback_periods = 20
        self.volume_weight = 0.3  # Weight given to volume in sentiment calculation

    def analyze(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze market sentiment from OHLCV data

        Args:
            df: DataFrame with OHLCV data

        Returns:
            dict: Sentiment analysis results
        """
        try:
            if df is None or len(df) < self.lookback_periods:
                return {
                    "sentiment": "neutral",
                    "score": 0.0,
                    "meta": {}
                }

            # Calculate momentum indicators
            momentum_score = self._calculate_momentum_score(df)

            # Calculate price action sentiment
            price_action_score = self._calculate_price_action_sentiment(df)

            # Calculate volume sentiment
            volume_score = self._calculate_volume_sentiment(df)

            # Combine scores with weights
            combined_score = (
                momentum_score * 0.4 +
                price_action_score * 0.4 +
                volume_score * self.volume_weight
            )

            # Classify sentiment
            sentiment, confidence = self._classify_sentiment(combined_score)

            return {
                "sentiment": sentiment,
                "score": combined_score,
                "meta": {
                    "momentum_score": momentum_score,
                    "price_action_score": price_action_score,
                    "volume_score": volume_score,
                    "confidence": confidence,
                    "components": {
                        "rsi": self._calculate_rsi(df),
                        "macd": self._calculate_macd_signal(df),
                        "trend_strength": self._calculate_trend_strength(df),
                        "candle_pattern": self._analyze_candle_patterns(df)
                    }
                }
            }

        except Exception as e:
            logger.warning(f"SentimentAI analysis failed: {e}")
            return {
                "sentiment": "neutral",
                "score": 0.0,
                "meta": {"error": str(e)}
            }

    def _calculate_momentum_score(self, df: pd.DataFrame) -> float:
        """Calculate momentum-based sentiment score"""
        try:
            # RSI calculation
            rsi = self._calculate_rsi(df)
            rsi_score = (rsi - 50) / 50  # Normalize to -1 to 1

            # MACD signal
            macd_score = self._calculate_macd_signal(df)

            # Stochastic oscillator
            stoch_score = self._calculate_stochastic_score(df)

            # Combine momentum indicators
            momentum_score = (rsi_score * 0.4 + macd_score * 0.4 + stoch_score * 0.2)

            return momentum_score

        except Exception:
            return 0.0

    def _calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate RSI indicator"""
        try:
            close = df['close'].astype(float)
            delta = close.diff()

            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            return rsi.iloc[-1]

        except Exception:
            return 50.0

    def _calculate_macd_signal(self, df: pd.DataFrame) -> float:
        """Calculate MACD signal strength"""
        try:
            close = df['close'].astype(float)

            # MACD components
            ema12 = close.ewm(span=12).mean()
            ema26 = close.ewm(span=26).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9).mean()

            # MACD histogram
            histogram = macd - signal

            # Normalize histogram to score
            hist_std = histogram.tail(20).std()
            if hist_std > 0:
                normalized_hist = histogram.iloc[-1] / hist_std
                return np.tanh(normalized_hist)  # Bound between -1 and 1
            else:
                return 0.0

        except Exception:
            return 0.0

    def _calculate_stochastic_score(self, df: pd.DataFrame) -> float:
        """Calculate Stochastic oscillator score"""
        try:
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            close = df['close'].astype(float)

            # Stochastic %K
            lowest_low = low.rolling(window=14).min()
            highest_high = high.rolling(window=14).max()

            k_percent = 100 * ((close - lowest_low) / (highest_high - lowest_low))

            # Stochastic %D (SMA of %K)
            d_percent = k_percent.rolling(window=3).mean()

            # Convert to sentiment score (-1 to 1)
            k_score = (k_percent.iloc[-1] - 50) / 50
            d_score = (d_percent.iloc[-1] - 50) / 50

            return (k_score + d_score) / 2

        except Exception:
            return 0.0

    def _calculate_price_action_sentiment(self, df: pd.DataFrame) -> float:
        """Calculate sentiment from price action patterns"""
        try:
            close = df['close'].astype(float)
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            open_price = df['open'].astype(float)

            # Recent price trend
            trend_score = self._calculate_trend_strength(df)

            # Candle pattern analysis
            pattern_score = self._analyze_candle_patterns(df)

            # Support/resistance interaction
            sr_score = self._calculate_support_resistance_score(df)

            # Combine price action components
            price_action_score = (trend_score * 0.5 + pattern_score * 0.3 + sr_score * 0.2)

            return price_action_score

        except Exception:
            return 0.0

    def _calculate_trend_strength(self, df: pd.DataFrame) -> float:
        """Calculate trend strength indicator"""
        try:
            close = df['close'].astype(float)

            # Linear regression slope
            x = np.arange(len(close))
            slope, _ = np.polyfit(x, close.values, 1)

            # Normalize slope by average price
            avg_price = close.mean()
            normalized_slope = slope / avg_price

            # Bound between -1 and 1
            return np.tanh(normalized_slope * 100)

        except Exception:
            return 0.0

    def _analyze_candle_patterns(self, df: pd.DataFrame) -> float:
        """Analyze recent candle patterns for sentiment"""
        try:
            recent_candles = df.tail(5)

            bullish_patterns = 0
            bearish_patterns = 0

            for idx, row in recent_candles.iterrows():
                open_price = row['open']
                close = row['close']
                high = row['high']
                low = row['low']

                # Bullish engulfing
                if close > open_price and (close - open_price) > abs(open_price - close):
                    bullish_patterns += 1

                # Bearish engulfing
                elif close < open_price and (open_price - close) > abs(open_price - close):
                    bearish_patterns += 1

                # Doji (indecision)
                body_size = abs(close - open_price)
                total_range = high - low
                if total_range > 0 and body_size / total_range < 0.1:
                    continue  # Neutral

            # Calculate pattern score
            total_patterns = bullish_patterns + bearish_patterns
            if total_patterns > 0:
                pattern_score = (bullish_patterns - bearish_patterns) / total_patterns
                return pattern_score
            else:
                return 0.0

        except Exception:
            return 0.0

    def _calculate_support_resistance_score(self, df: pd.DataFrame) -> float:
        """Calculate sentiment based on S/R levels"""
        try:
            close = df['close'].astype(float)
            current_price = close.iloc[-1]

            # Find recent swing points
            highs = df['high'].tail(20).nlargest(3)
            lows = df['low'].tail(20).nsmallest(3)

            resistance_levels = highs.mean()
            support_levels = lows.mean()

            # Calculate distance to S/R levels
            dist_to_resistance = (resistance_levels - current_price) / current_price
            dist_to_support = (current_price - support_levels) / current_price

            # Sentiment based on proximity to S/R
            if dist_to_support < 0.01:  # Near support
                return 0.3  # Slightly bullish
            elif dist_to_resistance < 0.01:  # Near resistance
                return -0.3  # Slightly bearish
            else:
                return 0.0  # Neutral

        except Exception:
            return 0.0

    def _calculate_volume_sentiment(self, df: pd.DataFrame) -> float:
        """Calculate sentiment from volume analysis"""
        try:
            volume = df['volume'].astype(float)
            close = df['close'].astype(float)

            # Volume trend
            volume_ma = volume.rolling(20).mean()
            volume_trend = (volume / volume_ma).tail(5).mean() - 1

            # Volume-price correlation
            price_change = close.pct_change()
            volume_price_corr = price_change.corr(volume)

            # Combine volume indicators
            volume_score = (volume_trend * 0.6 + volume_price_corr * 0.4)

            return np.tanh(volume_score)  # Bound between -1 and 1

        except Exception:
            return 0.0

    def _classify_sentiment(self, score: float) -> tuple:
        """Classify sentiment based on combined score"""
        try:
            abs_score = abs(score)

            if abs_score < self.sentiment_threshold:
                sentiment = "neutral"
                confidence = 1 - abs_score / self.sentiment_threshold
            elif score > self.sentiment_threshold:
                sentiment = "bullish"
                confidence = score
            else:
                sentiment = "bearish"
                confidence = abs(score)

            # Ensure confidence is between 0 and 1
            confidence = max(0.0, min(1.0, confidence))

            return sentiment, confidence

        except Exception:
            return "neutral", 0.0