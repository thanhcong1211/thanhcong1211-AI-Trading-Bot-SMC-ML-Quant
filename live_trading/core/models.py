"""
AI Models Module
XGBoost-based machine learning models for trend and reversal prediction
"""

import logging
import pickle
import os
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score
from sklearn.calibration import CalibratedClassifierCV
from xgboost import XGBClassifier
import xgboost as xgb

try:
    import joblib
    JOBLIB_AVAILABLE = True
except ImportError:
    JOBLIB_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠️ joblib not available, using pickle instead")

from core.indicators import TechnicalIndicators
from utils.helpers import add_session_features, save_feature_importances

logger = logging.getLogger(__name__)

# SMC Helper Functions - Placeholder implementations
def detect_structure(data):
    """Detect HH, HL, LH, LL structure points"""
    try:
        if data is None or len(data) < 3:
            return 0, 0, 0, 0
        highs = data['high'].values
        lows = data['low'].values
        hh = sum(1 for i in range(1, len(highs)-1) if highs[i] > highs[i-1] and highs[i] > highs[i+1])
        ll = sum(1 for i in range(1, len(lows)-1) if lows[i] < lows[i-1] and lows[i] < lows[i+1])
        hl = sum(1 for i in range(1, len(lows)-1) if lows[i] > lows[i-1] and highs[i] > highs[i-1])
        lh = sum(1 for i in range(1, len(highs)-1) if highs[i] < highs[i-1] and lows[i] < lows[i-1])
        return hh, hl, lh, ll
    except Exception:
        return 0, 0, 0, 0

def detect_BOS_CHOCH(data):
    """Detect Break of Structure and Change of Character"""
    try:
        if data is None or len(data) < 5:
            return 0, 0
        bos = 0
        choch = 0
        return bos, choch
    except Exception:
        return 0, 0

def volume_profile(data):
    """Calculate volume profile"""
    try:
        if data is None or 'volume' not in data.columns:
            return None
        return data['volume'].mean()
    except Exception:
        return None

def detect_fvg(data):
    """Detect Fair Value Gaps"""
    try:
        if data is None or len(data) < 3:
            return None, None
        return None, None
    except Exception:
        return None, None

def detect_ob(data):
    """Detect Order Blocks"""
    try:
        if data is None:
            return None
        return None
    except Exception:
        return None

def detect_order_blocks(data):
    """Detect Order Blocks (bullish/bearish)"""
    try:
        if data is None or len(data) < 3:
            return None, None
        return None, None
    except Exception:
        return None, None

def liquidity_map(data):
    """Calculate liquidity mapping"""
    try:
        if data is None:
            return None
        return None
    except Exception:
        return None

def detect_stop_hunt(data):
    """Detect stop hunt/liquidity wicks"""
    try:
        if data is None or len(data) < 2:
            return None
        return None
    except Exception:
        return None

def detect_false_breakout(data):
    """Detect false breakouts"""
    try:
        if data is None:
            return None
        return None
    except Exception:
        return None

def detect_volume_climax(data):
    """Detect volume climax"""
    try:
        if data is None or 'volume' not in data.columns:
            return None
        return None
    except Exception:
        return None

def detect_exhaustion(data):
    """Detect exhaustion volume"""
    try:
        if data is None:
            return None
        return None
    except Exception:
        return None

def calculate_delta(data):
    """Calculate delta volume"""
    try:
        if data is None or 'volume' not in data.columns:
            return None
        return None
    except Exception:
        return None

def detect_momentum_shift(data):
    """Detect momentum shifts"""
    try:
        if data is None:
            return None
        return None
    except Exception:
        return None

def detect_choch(data):
    """Detect Change of Character"""
    try:
        if data is None:
            return None
        return None
    except Exception:
        return None


class XGBoostTrendModel:
    """XGBoost AI Model cho trend prediction"""
    
    def __init__(self, model_path='ai_trend_model.pkl', scaler_path='ai_scaler.pkl', required=False):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.is_trained = False
        self.required = required  # Nếu False, có thể chạy mà không có model
        
    def prepare_features(self, df):
        """🧠 Advanced Feature engineering với phân tích chuyên sâu"""
        df = df.copy()
        # Thêm thông tin session (Asia/EU/US) để model tận dụng pattern theo giờ giao dịch
        try:
            df = add_session_features(df)
        except Exception:
            pass
        
        # ========== TECHNICAL INDICATORS CƠ BẢN ==========
        df = TechnicalIndicators.calculate_sma(df, [5, 10, 20])
        df = TechnicalIndicators.calculate_rsi(df)
        df = TechnicalIndicators.calculate_macd(df)
        df = TechnicalIndicators.calculate_bollinger(df)
        df = TechnicalIndicators.calculate_atr(df)
        
        # ========== 🎯 XU HƯỚNG THỊ TRƯỜNG ==========
        df = TechnicalIndicators.analyze_trend(df, short_period=20, long_period=50)
        
        # ========== 🏗️ VÙNG HỖ TRỢ & KHÁNG CỰ ==========
        df = TechnicalIndicators.detect_support_resistance(df, window=20)
        
        # ========== 📊 PHÂN TÍCH VOLUME ==========
        df = TechnicalIndicators.analyze_volume(df)
        
        # ========== 🕯️ MÔ HÌNH NẾN ==========
        df = TechnicalIndicators.detect_candlestick_patterns(df)
        
        # ========== PRICE FEATURES CƠ BẢN ==========
        df['price_change'] = df['close'].pct_change()
        df['high_low_ratio'] = df['high'] / df['low']
        df['close_open_ratio'] = df['close'] / df['open']
        
        # ========== MOMENTUM FEATURES ==========
        df['momentum_1'] = df['close'] / df['close'].shift(1) - 1
        df['momentum_5'] = df['close'] / df['close'].shift(5) - 1
        df['momentum_10'] = df['close'] / df['close'].shift(10) - 1
        
        # ========== VOLATILITY & ADVANCED FEATURES ==========
        df['volatility'] = df['close'].rolling(10).std()
        df['volatility_ratio'] = df['volatility'] / df['volatility'].rolling(20).mean()
        
        # 🎯 ENHANCED MARKET REGIME DETECTION
        df['market_regime'] = np.where(
            df['is_sideways'] == 1, 0,  # Sideways = regime 0 (avoid trading)
            np.where(df['trend_quality'] > 1.2, 2,  # Strong trend = regime 2
                    1)  # Weak trend = regime 1
        )
        
        # Trend favorability score cho AI
        df['trend_favorability'] = df['trend_quality'] * (1 - df['is_sideways'])
        
        # Multi-timeframe features
        df['close_vs_sma20'] = (df['close'] - df['sma_20']) / df['sma_20']
        df['rsi_momentum'] = df['rsi'].diff()
        df['macd_momentum'] = df['macd'].diff()
        
        # Target: Next period trend (1 = UP, 0 = DOWN)
        df['future_return'] = df['close'].shift(-1) / df['close'] - 1
        df['target'] = (df['future_return'] > 0).astype(int)
        
        # ========== SMC / Candle Pattern Features Integration ==========
        try:
            smc_score_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_score')]
            smc_recent_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_recent')]
            if smc_score_cols or smc_recent_cols:
                # Ensure numeric and fill missing
                for c in smc_score_cols + smc_recent_cols:
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

                # Aggregated features to feed into models
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
            logger.debug(f"⚠️ SMC integration skipped in XGBoostTrendModel.prepare_features: {e}")

        return df

    def save_model(self):
        """Save model và scaler"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            logger.info(f"✅ XGBoostTrendModel saved to {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Error saving XGBoostTrendModel: {e}")

    def load_model(self):
        """Load pre-trained model"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                if JOBLIB_AVAILABLE:
                    self.model = joblib.load(self.model_path)
                    self.scaler = joblib.load(self.scaler_path)
                else:
                    with open(self.model_path, 'rb') as f:
                        self.model = pickle.load(f)
                    with open(self.scaler_path, 'rb') as f:
                        self.scaler = pickle.load(f)
                self.is_trained = True
                logger.info(f"✅ XGBoostTrendModel loaded from {self.model_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Error loading XGBoostTrendModel: {e}")
        return False

    def train_model(self, df, test_size=0.3):
        """Train XGBoostTrendModel from provided DataFrame.

        This method mirrors training patterns used by other AI classes in the
        repository and is intentionally conservative: it prepares features,
        selects feature columns, trains a small XGBoost classifier, and saves
        model + scaler. It does not change external APIs or variable names.
        """
        try:
            logger.info("🧠 Đang huấn luyện mô hình XGBoostTrendModel...")
            logger.info("   - Dữ liệu sử dụng: features, target")
            logger.info("   - Thuật toán: XGBoostClassifier, n_estimators=100, max_depth=6, learning_rate=0.1")
            logger.info("   - Đang thực hiện fitting mô hình...")


            # Prepare features
            df = self.prepare_features(df)

            # Choose feature columns (exclude typical non-features)
            exclude_cols = ['target', 'future_return', 'future_high', 'future_low', 'is_reversal', 'close', 'high', 'low', 'open', 'volume']
            feature_cols = [c for c in df.columns if c not in exclude_cols]

            # Ensure target exists or create a simple target if missing
            if 'target' not in df.columns:
                df['future_return'] = df['close'].shift(-1) / df['close'] - 1
                df['target'] = (df['future_return'] > 0).astype(int)

            df_clean = df[feature_cols + ['target']].dropna()

            if len(df_clean) < 100:
                logger.error("❌ Không đủ dữ liệu để huấn luyện XGBoostTrendModel")
                return False

            X = df_clean[feature_cols]
            y = df_clean['target']

            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42, stratify=y)

            # Scale
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train a conservative XGBoost model
            self.model = xgb.XGBClassifier(
                n_estimators=100,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                eval_metric='logloss'
            )

            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            try:
                y_pred = self.model.predict(X_test_scaled)
                acc = accuracy_score(y_test, y_pred)
                logger.info(f"✅ Đã huấn luyện xong XGBoostTrendModel - Độ chính xác: {acc:.3f}")
                try:
                    save_feature_importances(self.model, feature_cols, 'XGBoostTrendModel', X=X_test_scaled, y=y_test, compute_permutation=True)
                except Exception:
                    pass
            except Exception:
                logger.info("✅ Đã huấn luyện xong XGBoostTrendModel (bỏ qua đánh giá)")

            # Save state
            self.feature_columns = feature_cols
            self.is_trained = True
            self.save_model()
            return True

        except Exception as e:
            logger.error(f"❌ Huấn luyện XGBoostTrendModel thất bại: {e}")
            return False

    def predict_signal(self, df):
        """Compatibility wrapper so external callers can always call predict_signal(df).

        Returns (action:str, confidence:float) where confidence is 0.0-1.0.
        Falls back to simple price-action heuristic when model is not trained or prediction fails.
        """
        try:
            # Ensure we have a DataFrame with indicators
            df_prepared = self.prepare_features(df)

            # Default simple fallback - Tính confidence dựa trên chuỗi nến
            def fallback():
                try:
                    if len(df_prepared) < 2:
                        return "NONE", 0.0
                    
                    # Tính confidence dựa trên strength của chuỗi nến
                    last_close = df_prepared['close'].iloc[-1]
                    prev_close = df_prepared['close'].iloc[-2]
                    
                    # Đếm số nến liên tiếp cùng hướng (tối đa 5)
                    consecutive = 1
                    direction = 1 if last_close > prev_close else -1
                    
                    for i in range(2, min(6, len(df_prepared))):
                        curr = df_prepared['close'].iloc[-i]
                        prev = df_prepared['close'].iloc[-i-1]
                        if (curr > prev and direction > 0) or (curr < prev and direction < 0):
                            consecutive += 1
                        else:
                            break
                    
                    # Confidence = 35% + 5% mỗi nến liên tiếp (tối đa 60%)
                    confidence = min(0.60, 0.35 + (consecutive * 0.05))
                    
                    if last_close > prev_close:
                        return "BUY", confidence
                    else:
                        return "SELL", confidence
                except Exception:
                    return "NONE", 0.0
            
            # ⚠️ Nếu model chưa train hoặc không khả dụng -> dùng fallback
            if not self.is_trained or self.model is None:
                logger.warning("⚠️ TrendAI using FALLBACK heuristic - Model not trained!")
                return fallback()

            # If trained and model available, use it
            if self.is_trained and self.model is not None and self.feature_columns is not None:
                try:
                    latest = df_prepared.iloc[[-1]]
                    X = latest[self.feature_columns].fillna(0)
                    X_scaled = self.scaler.transform(X)
                    probs = self.model.predict_proba(X_scaled)[0]
                    prob_down = float(probs[0])
                    logger.debug(f"⚡ Using TrendAI ML Model (not fallback)")
                    prob_up = float(probs[1])

                    if prob_up >= prob_down:
                        return "BUY", prob_up
                    else:
                        return "SELL", prob_down
                except Exception as e:
                    logger.warning(f"⚠️ XGBoostTrendModel.predict_signal fallback due to: {e}")
                    return fallback()

            # Not trained → fallback
            return fallback()

        except Exception as e:
            logger.error(f"❌ XGBoostTrendModel.predict_signal unexpected error: {e}")
            return "NONE", 0.0


class TrendAI:
    """🧠 TREND AI PRO - Advanced Trend Prediction với SMC Concepts
    
    Học từ Higher High (HH), Lower High (LH), Higher Low (HL), Lower Low (LL),
    Break of Structure (BOS), Change of Character (ChoCH), Volume Profile,
    Fair Value Gaps (FVG), Order Blocks, Liquidity mapping.
    
    Dự đoán BUY/SELL với độ tin cậy cao dựa trên:
    - Market Structure Analysis
    - Volume Profile (POC/VAH/VAL)
    - Price Action Patterns
    - Multi-timeframe Confirmation
    """
    
    def __init__(self, model_path='trend_ai_model.pkl', scaler_path='trend_ai_scaler.pkl'):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.is_trained = False
        
        # SMC Concept Weights
        self.smc_weights = {
            'HH': 0.15, 'HL': 0.15, 'LH': 0.15, 'LL': 0.15,  # Market Structure
            'BOS': 0.20, 'CHOCH': 0.20,  # Structure Breaks
            'POC': 0.10, 'VAH': 0.08, 'VAL': 0.08,  # Volume Profile
            'FVG': 0.12, 'OrderBlock': 0.12, 'Liquidity': 0.10  # Price Action
        }
        
        logger.info("🧠 TrendAI PRO initialized - Advanced SMC-based Trend Prediction")
        logger.info(f"   SMC Concepts: HH/HL/LH/LL, BOS/ChoCH, Volume Profile, FVG, Order Blocks")
    
    def predict(self, features: dict):
        """
        Dự đoán xu hướng BUY/SELL từ features dict
        
        Args:
            features: Dictionary chứa tất cả trend features từ build_trend_features()
            
        Returns:
            tuple: (action: str, confidence: float) - "BUY"/"SELL", 0.0-1.0
        """
        try:
            if not self.is_trained or self.model is None:
                logger.debug("✓ TrendAI using SMC heuristic mode (model not trained)")
                return self._predict_with_smc_heuristic(features)
            
            # 🛡️ DEFENSIVE CHECK: Ensure features is a valid dict
            if features is None or not isinstance(features, dict):
                logger.debug(f"✓ TrendAI fallback to SMC heuristic (invalid features: {type(features)})")
                return self._predict_with_smc_heuristic(features)
            
            # 🛡️ DEFENSIVE CHECK: Ensure feature_columns is available
            if self.feature_columns is None:
                logger.debug("✓ TrendAI using SMC heuristic (feature_columns not initialized)")
                return self._predict_with_smc_heuristic(features)
            
            # Build feature vector
            row = {}
            for col in self.feature_columns:
                val = features.get(col, 0.0)
                try:
                    row[col] = float(val) if val is not None else 0.0
                except Exception:
                    row[col] = 0.0
            
            X = pd.DataFrame([row], columns=self.feature_columns)
            X_scaled = self.scaler.transform(X)
            
            # Get prediction probabilities
            probs = self.model.predict_proba(X_scaled)[0]
            prob_down = float(probs[0])  # Probability of DOWN trend
            prob_up = float(probs[1])    # Probability of UP trend
            
            # Choose action based on higher probability
            if prob_up >= prob_down:
                action = "BUY"
                confidence = prob_up
            else:
                action = "SELL"
                confidence = prob_down
            
            # Boost confidence with SMC confirmation
            smc_boost = self._calculate_smc_boost(features, action)
            confidence = min(0.99, confidence * (1 + smc_boost))
            
            logger.info(f"🧠 TrendAI Prediction: {action} ({confidence:.1%}) | SMC Boost: +{smc_boost:.1%}")
            
            return action, confidence
            
        except Exception as e:
            logger.debug(f"✓ TrendAI using SMC heuristic (prediction error: {e})")
            return self._predict_with_smc_heuristic(features)
    
    def _predict_with_smc_heuristic(self, features: dict):
        """
        Dự đoán dựa trên SMC concepts khi model chưa train
        
        Logic:
        - HH/HL: Bullish structure
        - LH/LL: Bearish structure  
        - BOS: Break of trend
        - ChoCH: Volatility change
        - Volume Profile: Liquidity areas
        """
        # Defensive check for None or invalid features
        if features is None or not isinstance(features, dict):
            logger.warning("⚠️ _predict_with_smc_heuristic: Invalid features input, using fallback")
            return "NONE", 0.0
        
        score_buy = 0.0
        score_sell = 0.0
        
        # Market Structure (40% weight)
        hh = features.get('HH')
        hl = features.get('HL') 
        lh = features.get('LH')
        ll = features.get('LL')
        
        if hh and hl:
            score_buy += 0.4  # Strong bullish structure
            logger.debug("📈 HH+HL detected - Bullish structure")
        elif lh and ll:
            score_sell += 0.4  # Strong bearish structure
            logger.debug("📉 LH+LL detected - Bearish structure")
        
        # Structure Breaks (30% weight)
        bos = features.get('BOS')
        choch = features.get('CHOCH')
        
        if bos:
            # BOS can be bullish or bearish depending on context
            if hh or hl:  # In bullish structure, BOS might signal continuation
                score_buy += 0.15
            else:
                score_sell += 0.15
            logger.debug(f"💥 BOS detected - {bos}")
            
        if choch:
            # ChoCH often signals trend change
            if score_buy > score_sell:
                score_sell += 0.15  # Potential reversal
            else:
                score_buy += 0.15
            logger.debug(f"🔄 ChoCH detected - {choch}")
        
        # Volume Profile (20% weight)
        poc = features.get('POC')
        vah = features.get('VAH')
        val = features.get('VAL')
        
        if poc:
            # Price near POC suggests liquidity
            logger.debug(f"📊 Volume POC: {poc}")
        
        # Price Action (10% weight)
        fvg = features.get('FVG')
        ob = features.get('OrderBlock')
        liquidity = features.get('Liquidity')
        
        if fvg:
            logger.debug(f"🎯 FVG detected: {fvg}")
        if ob:
            logger.debug(f"📦 Order Block: {ob}")
        if liquidity:
            logger.debug(f"💧 Liquidity area: {liquidity}")
        
        # Decision
        total_score = score_buy + score_sell
        
        if total_score < 0.1:  # No clear signal
            return "NONE", 0.0
        
        if score_buy > score_sell:
            confidence = min(0.7, score_buy / total_score)  # Cap at 70% for heuristic
            return "BUY", confidence
        else:
            confidence = min(0.7, score_sell / total_score)
            return "SELL", confidence
    
    def _calculate_smc_boost(self, features: dict, predicted_action: str):
        """
        Tính boost confidence từ SMC confirmation
        
        Returns:
            float: Boost multiplier (0.0 - 0.3)
        """
        # Defensive check for None or invalid features
        if features is None or not isinstance(features, dict):
            logger.warning("⚠️ _calculate_smc_boost: Invalid features input, returning 0.0")
            return 0.0
        
        boost = 0.0
        
        try:
            # Market Structure confirmation
            if predicted_action == "BUY":
                if features.get('HH') and features.get('HL'):
                    boost += 0.1  # Bullish structure confirms BUY
                if features.get('BOS') and (features.get('HH') or features.get('HL')):
                    boost += 0.05  # BOS in bullish structure
            else:  # SELL
                if features.get('LH') and features.get('LL'):
                    boost += 0.1  # Bearish structure confirms SELL
                if features.get('BOS') and (features.get('LH') or features.get('LL')):
                    boost += 0.05  # BOS in bearish structure
            
            # Volume Profile confirmation
            poc = features.get('POC')
            if poc:
                boost += 0.02  # POC presence adds confidence
            
            # Price Action confirmation
            if features.get('FVG') or features.get('OrderBlock'):
                boost += 0.03  # Strong price action signals
            
            return min(0.3, boost)  # Cap boost at 30%
            
        except Exception:
            return 0.0
    
    def train_model(self, df, test_size=0.3):
        """Train TrendAI model với SMC-enhanced features"""
        logger.info("🧠 Đang huấn luyện mô hình TrendAI PRO...")
        
        # Prepare features using build_trend_features logic
        df = self._prepare_training_features(df)
        
        # Feature columns
        exclude_cols = ['target', 'future_return', 'close', 'high', 'low', 'open', 'volume']
        feature_cols = [col for col in df.columns if col not in exclude_cols]
        
        # Clean data
        df_clean = df[feature_cols + ['target']].dropna()
        
        if len(df_clean) < 200:  # Need more data for trend prediction
            logger.error(f"❌ Không đủ dữ liệu để huấn luyện TrendAI: {len(df_clean)} < 200")
            return False
        
        X = df_clean[feature_cols]
        y = df_clean['target']
        
        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train XGBoost with trend-specific parameters
        self.model = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=8,
            learning_rate=0.05,
            random_state=42,
            scale_pos_weight=1.0,  # Balanced for trend prediction
            eval_metric='logloss',
            early_stopping_rounds=20
        )
        
        self.model.fit(
            X_train_scaled, y_train,
            eval_set=[(X_test_scaled, y_test)],
            verbose=False
        )
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
        recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
        logger.info(f"✅ Đã huấn luyện xong TrendAI PRO - Độ chính xác: {accuracy:.3f}, Độ chính xác từng lớp: {precision:.3f}, Khả năng hồi tưởng: {recall:.3f}")
        try:
            save_feature_importances(self.model, feature_cols, 'TrendAI_PRO', X=X_test_scaled, y=y_test, compute_permutation=True)
        except Exception:
            pass
        # Calibrate predicted probabilities for more reliable confidence scores
        try:
            calib = CalibratedClassifierCV(self.model, method='isotonic', cv='prefit')
            calib.fit(X_test_scaled, y_test)
            self.model = calib
            logger.info("🔧 TrendAI PRO probabilities calibrated with isotonic CalibratedClassifierCV")
        except Exception as e:
            logger.debug(f"⚠️ TrendAI calibration skipped: {e}")
        self.feature_columns = feature_cols
        self.is_trained = True
        self.save_model()        
        return True
    
    def _prepare_training_features(self, df):
        """Prepare training features với SMC concepts"""
        df = df.copy()
        # Thêm thông tin session để model học các pattern theo phiên
        try:
            df = add_session_features(df)
        except Exception:
            pass
        
        # Basic technical indicators
        df = TechnicalIndicators.calculate_sma(df, [20, 50, 200])
        df = TechnicalIndicators.calculate_rsi(df)
        df = TechnicalIndicators.calculate_macd(df)
        df = TechnicalIndicators.calculate_atr(df)
        
        # Trend analysis
        df = TechnicalIndicators.analyze_trend(df, short_period=20, long_period=50)
        
        # Add SMC features (simplified for training)
        df['HH'] = self._detect_hh_simple(df)
        df['HL'] = self._detect_hl_simple(df)
        df['LH'] = self._detect_lh_simple(df)
        df['LL'] = self._detect_ll_simple(df)
        
        # Volume profile approximation
        df['POC'] = df['volume'].rolling(20).mean()
        df['VAH'] = df['high'].rolling(20).max()
        df['VAL'] = df['low'].rolling(20).min()
        
        # Target: Future trend direction
        df['future_return'] = df['close'].shift(-5) / df['close'] - 1
        df['target'] = (df['future_return'] > 0.001).astype(int)  # 1 = UP, 0 = DOWN
        
        # ========== SMC / Candle Pattern Features Integration ==========
        try:
            smc_score_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_score')]
            smc_recent_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_recent')]
            if smc_score_cols or smc_recent_cols:
                for c in smc_score_cols + smc_recent_cols:
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

                # Aggregates for TrendAI training
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
            logger.debug(f"⚠️ SMC integration skipped in TrendAI._prepare_training_features: {e}")

        return df
    
    def _detect_hh_simple(self, df, window=10):
        """Simple HH detection for training"""
        try:
            recent_highs = df['high'].rolling(window).max()
            return (df['high'] == recent_highs).astype(int)
        except:
            return 0
    
    def _detect_hl_simple(self, df, window=10):
        """Simple HL detection for training"""
        try:
            recent_lows = df['low'].rolling(window).min()
            return (df['low'] == recent_lows).astype(int)
        except:
            return 0
    
    def _detect_lh_simple(self, df, window=10):
        """Simple LH detection for training"""
        try:
            return ((df['high'] < df['high'].shift(1)) & 
                   (df['high'] < df['high'].rolling(window).max())).astype(int)
        except:
            return 0
    
    def _detect_ll_simple(self, df, window=10):
        """Simple LL detection for training"""
        try:
            return ((df['low'] > df['low'].shift(1)) & 
                   (df['low'] > df['low'].rolling(window).min())).astype(int)
        except:
            return 0
    
    def save_model(self):
        """Save model và scaler"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            joblib.dump(self.feature_columns, 'trend_ai_feature_columns.pkl')
            logger.info(f"✅ TrendAI PRO model saved to {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Error saving TrendAI model: {e}")
    
    def load_model(self):
        """Load pre-trained model"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                
                if os.path.exists('trend_ai_feature_columns.pkl'):
                    self.feature_columns = joblib.load('trend_ai_feature_columns.pkl')
                
                self.is_trained = True
                logger.info(f"✅ TrendAI PRO model loaded from {self.model_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Error loading TrendAI model: {e}")
        return False


def build_trend_features(data):
    """
    Build consolidated trend/structure/volume/price-action features across multiple timeframes.

    This function is an additive helper (non-invasive). It attempts to use the existing
    `TechnicalIndicators` helpers when available, but falls back to safe, minimal
    computations so it does not change any other logic in the file.

    Args:
        data (dict): mapping timeframe string (e.g. 'M5','M15','H1','H4') to a
                     pandas.DataFrame (with columns ['open','high','low','close','volume'])
                     or to a Series of close prices. Missing timeframes are tolerated.

    Returns:
        dict: features keyed by descriptive names (e.g. 'ema20_H1', 'macd_M15',
              'POC', 'FVG', 'HH', 'BOS', ...). Values are scalars where possible.

    Notes:
        - This helper returns scalar (latest) values for each feature to be compatible
          with real-time inference in the rest of the system.
        - If a specialized helper (e.g. detect_structure, volume_profile) is not present
          in the runtime, the corresponding feature will be set to None.
    """
    try:
        if data is None:
            logger.warning("⚠️ build_trend_features received None data")
            return {}
        
        features = {}

        # Lightweight SMC cache helper
        SMC_CACHE = {}

        def get_smc_cached(data, timestamp):
            """Return cached SMC (Order Blocks, FVG, Liquidity, CHoCH, BOS).

            This is a safe wrapper that attempts to call available SMC-related
            helper functions when present, caches results by timestamp string,
            and always returns either a dict with keys or None on failure.
            """
            try:
                if timestamp is None:
                    return None

                key = str(timestamp)
                # Use module-level cache
                cache = globals().get('SMC_CACHE')
                if cache is None:
                    cache = {}
                    globals()['SMC_CACHE'] = cache

                if key in cache:
                    return cache[key]

                smc = {}

                # Fair Value Gaps
                try:
                    if 'detect_fvg' in globals():
                        fvg = detect_fvg(data)
                        smc['fvg'] = fvg
                    else:
                        smc['fvg'] = None
                except Exception:
                    smc['fvg'] = None

                # Order Blocks (OB)
                try:
                    if 'detect_order_blocks' in globals():
                        ob = detect_order_blocks(data)
                        smc['ob'] = ob
                    elif 'detect_ob' in globals():
                        ob = detect_ob(data)
                        smc['ob'] = ob
                    else:
                        smc['ob'] = None
                except Exception:
                    smc['ob'] = None

                # Liquidity map
                try:
                    if 'liquidity_map' in globals():
                        liq = liquidity_map(data)
                        smc['liq'] = liq
                    else:
                        smc['liq'] = None
                except Exception:
                    smc['liq'] = None

                # CHoCH / BOS
                try:
                    if 'detect_BOS_CHOCH' in globals():
                        bos, choch = detect_BOS_CHOCH(data)
                        smc['bos'] = bos
                        smc['choch'] = choch
                    else:
                        # fallback to detect_structure if available
                        if 'detect_structure' in globals():
                            hh, hl, lh, ll = detect_structure(data)
                            smc['bos'] = None
                            smc['choch'] = None
                        else:
                            smc['bos'] = None
                            smc['choch'] = None
                except Exception:
                    smc['bos'] = None
                    smc['choch'] = None

                # Store and return
                cache[key] = smc
                return smc
            except Exception:
                return None

        tfs = ["M5", "M15", "H1", "H4"]

        for tf in tfs:
            df = data.get(tf) if isinstance(data, dict) else None
            if df is None:
                features[f"missing_tf_{tf}"] = True
                continue

            try:
                # If a DataFrame with 'close' exists, compute EMAs, MACD, RSI latest values
                if isinstance(df, pd.DataFrame) and 'close' in df.columns:
                    close = df['close']
                    features[f"ema20_{tf}"] = float(close.ewm(span=20).mean().iloc[-1])
                    features[f"ema200_{tf}"] = float(close.ewm(span=200).mean().iloc[-1])

                    # Try to use TechnicalIndicators helpers if available (they return series)
                    try:
                        tmp = df.copy()
                        tmp = TechnicalIndicators.calculate_macd(tmp)
                        features[f"macd_{tf}"] = float(tmp['macd'].iloc[-1])
                    except Exception:
                        features[f"macd_{tf}"] = None

                    try:
                        tmp2 = df.copy()
                        tmp2 = TechnicalIndicators.calculate_rsi(tmp2)
                        features[f"rsi_{tf}"] = float(tmp2['rsi'].iloc[-1])
                    except Exception:
                        features[f"rsi_{tf}"] = None
                else:
                    # If df is a Series or other iterable, attempt a minimal computation
                    try:
                        s = pd.Series(df)
                        features[f"ema20_{tf}"] = float(s.ewm(span=20).mean().iloc[-1])
                        features[f"ema200_{tf}"] = float(s.ewm(span=200).mean().iloc[-1])
                    except Exception:
                        features[f"ema20_{tf}"] = None
                        features[f"ema200_{tf}"] = None
                    features[f"macd_{tf}"] = None
                    features[f"rsi_{tf}"] = None
            except Exception:
                features[f"ema20_{tf}"] = None
                features[f"ema200_{tf}"] = None
                features[f"macd_{tf}"] = None
                features[f"rsi_{tf}"] = None
        smc_used = False
        try:
            if isinstance(data, dict) and data.get('H1') is not None and hasattr(data.get('H1'), 'index') and len(data.get('H1')) > 0:
                try:
                    timestamp = data.get('H1').index[-1]
                except Exception:
                    timestamp = None

                if timestamp is not None:
                    try:
                        # Respect AUTO_FULL_SMC global (set by AutoModeController). If False,
                        # run SMC detection sparingly (every 30 candles) to save CPU.
                        if globals().get('AUTO_FULL_SMC', True):
                            smc = get_smc_cached(data, timestamp)
                        else:
                            # Lightweight: only compute SMC occasionally to avoid heavy ops
                            h1_df = data.get('H1')
                            smc = None
                            try:
                                if h1_df is not None and len(h1_df) > 0 and (len(h1_df) % 30) == 0:
                                    smc = get_smc_cached(data, timestamp)
                            except Exception:
                                smc = None

                        if smc:
                            # Map cached SMC values into features to avoid recomputation
                            features['FVG'] = smc.get('fvg')
                            features['OrderBlock'] = smc.get('ob')
                            features['Liquidity'] = smc.get('liq')
                            features['CHOCH'] = smc.get('choch')
                            features['BOS'] = smc.get('bos')
                            smc_used = True
                    except Exception:
                        smc_used = False
        except Exception:
            smc_used = False

        # MARKET STRUCTURE: try to call detect_structure and detect_BOS_CHOCH if present
        try:
            if 'detect_structure' in globals():
                hh, hl, lh, ll = detect_structure(data)
                features['HH'] = hh
                features['HL'] = hl
                features['LH'] = lh
                features['LL'] = ll
            else:
                features['HH'] = features['HL'] = features['LH'] = features['LL'] = None
        except Exception:
            features['HH'] = features['HL'] = features['LH'] = features['LL'] = None

        try:
            if 'detect_BOS_CHOCH' in globals():
                bos, choch = detect_BOS_CHOCH(data)
                features['BOS'] = bos
                features['CHOCH'] = choch
            else:
                features['BOS'] = None
                features['CHOCH'] = None
        except Exception:
            features['BOS'] = None
            features['CHOCH'] = None

        # VOLUME PROFILE
        try:
            if 'volume_profile' in globals():
                vp = volume_profile(data)
                if isinstance(vp, dict):
                    features['POC'] = vp.get('poc')
                    features['VAH'] = vp.get('vah')
                    features['VAL'] = vp.get('val')
                else:
                    features['POC'] = getattr(vp, 'poc', None)
                    features['VAH'] = getattr(vp, 'vah', None)
                    features['VAL'] = getattr(vp, 'val', None)
            else:
                features['POC'] = features['VAH'] = features['VAL'] = None
        except Exception:
            features['POC'] = features['VAH'] = features['VAL'] = None

        # ADVANCED PRICE ACTION
        try:
            features['FVG'] = detect_fvg(data) if 'detect_fvg' in globals() else None
        except Exception:
            features['FVG'] = None

        try:
            features['OrderBlock'] = detect_ob(data) if 'detect_ob' in globals() else None
        except Exception:
            features['OrderBlock'] = None

        try:
            features['Liquidity'] = liquidity_map(data) if 'liquidity_map' in globals() else None
        except Exception:
            features['Liquidity'] = None

        # Meta
        try:
            features['_meta'] = {
                'computed_at': datetime.utcnow().isoformat(),
                'source': 'build_trend_features'
            }
        except Exception:
            features['_meta'] = None

        # Ensure features dict is never empty - provide defaults for TrendAI
        if not features or len(features) <= 1:  # Allow _meta
            logger.warning("⚠️ build_trend_features returning minimal defaults")
            features.update({
                'HH': False,
                'HL': False,
                'LH': False,
                'LL': False,
                'BOS': None,
                'CHOCH': None,
                'POC': None,
                'VAH': None,
                'VAL': None,
                'FVG': None,
                'OrderBlock': None,
                'Liquidity': None,
                'ema20_H1': None,
                'ema200_H1': None,
                'macd_H1': None,
                'rsi_H1': None,
                'ema20_M5': None,
                'ema20_M15': None,
                'ema20_H4': None,
                'macd_M5': None,
                'macd_M15': None,
                'macd_H4': None,
                'rsi_M5': None,
                'rsi_M15': None,
                'rsi_H4': None,
            })

        return features
    except Exception as e:
        logger.error(f"❌ Error in build_trend_features: {e}")
        return {}


def build_reversal_features(data):
    """
    Build consolidated reversal features across multiple timeframes.

    This function computes reversal-related features using various detection helpers.
    It attempts to use specialized helpers when available, but falls back to safe defaults.

    Args:
        data (dict): mapping timeframe string (e.g. 'M5','M15','H1','H4') to a
                     pandas.DataFrame or Series. Missing timeframes are tolerated.

    Returns:
        dict: features keyed by descriptive names (e.g. 'liquidity_wick', 'FVG_up',
              'bullish_OB', 'climax_volume', ...). Values are scalars where possible.
    """
    features = {}

    # 1. Liquidity signals
    try:
        features["liquidity_wick"] = detect_stop_hunt(data) if 'detect_stop_hunt' in globals() else None
    except Exception:
        features["liquidity_wick"] = None

    try:
        features["false_break"] = detect_false_breakout(data) if 'detect_false_breakout' in globals() else None
    except Exception:
        features["false_break"] = None

    # 2. Order Block
    try:
        bullish_ob, bearish_ob = detect_order_blocks(data) if 'detect_order_blocks' in globals() else (None, None)
        features["bullish_OB"] = bullish_ob
        features["bearish_OB"] = bearish_ob
    except Exception:
        features["bullish_OB"] = None
        features["bearish_OB"] = None

    # 3. Fair Value Gap
    try:
        fvg_up, fvg_down = detect_fvg(data) if 'detect_fvg' in globals() else (None, None)
        features["FVG_up"] = fvg_up
        features["FVG_down"] = fvg_down
    except Exception:
        features["FVG_up"] = None
        features["FVG_down"] = None

    # 4. Volume signals
    try:
        features["climax_volume"] = detect_volume_climax(data) if 'detect_volume_climax' in globals() else None
    except Exception:
        features["climax_volume"] = None

    try:
        features["exhaustion_volume"] = detect_exhaustion(data) if 'detect_exhaustion' in globals() else None
    except Exception:
        features["exhaustion_volume"] = None

    try:
        features["delta_volume"] = calculate_delta(data) if 'calculate_delta' in globals() else None
    except Exception:
        features["delta_volume"] = None

    # 5. Momentum shift
    try:
        features["momentum_shift"] = detect_momentum_shift(data) if 'detect_momentum_shift' in globals() else None
    except Exception:
        features["momentum_shift"] = None

    # 6. Structure break (CHoCH)
    try:
        features["choch"] = detect_choch(data) if 'detect_choch' in globals() else None
    except Exception:
        features["choch"] = None

    # Meta
    try:
        features['_meta'] = {
            'computed_at': datetime.utcnow().isoformat(),
            'source': 'build_reversal_features'
        }
    except Exception:
        features['_meta'] = None

    return features


def build_volatility_features(data, news):
    """
    🔥 VOLATILITY AI PRO - Build consolidated volatility features

    6 Tính năng PRO:
    🔥 1. GARCH Volatility Prediction
    🔥 2. Transformer Volatility Forecast
    🔥 3. Volatility Regime Detection
    🔥 4. Volume + Volatility Spike Detector
    🔥 5. ATR + Standard Deviation Dynamic SL/TP
    🔥 6. News-based Volatility AI

    Args:
        data (dict): mapping timeframe string (e.g. 'M5','M15','H1','H4') to
                     pandas.DataFrame or Series. Missing timeframes are tolerated.
        news (dict): news data for news filter classification

    Returns:
        dict: features keyed by descriptive names
    """
    features = {}

    # Khởi tạo VolatilityAI instance (local scope để tránh lỗi)
    try:
        from core.complete_ai_trading_system import VolatilityAI
        volatility_ai = VolatilityAI()
    except Exception as e:
        logger.debug(f"✓ VolatilityAI not available, using default values: {e}")
        volatility_ai = None

    # 🔥 1. GARCH VOLATILITY PREDICTION
    if volatility_ai is not None:
        try:
            garch_result = volatility_ai.garch_predict(data)
            features["garch_volatility"] = garch_result['volatility_forecast']
            features["garch_confidence"] = garch_result['confidence']
            features["garch_risk_level"] = garch_result['risk_level']
        except Exception as e:
            logger.debug(f"✓ GARCH using defaults: {e}")
            features["garch_volatility"] = 0.02
            features["garch_confidence"] = 0.5
            features["garch_risk_level"] = 'MEDIUM'
    else:
        features["garch_volatility"] = 0.02
        features["garch_confidence"] = 0.5
        features["garch_risk_level"] = 'MEDIUM'

    # 🔥 2. TRANSFORMER VOLATILITY FORECAST
    if volatility_ai is not None:
        try:
            transformer_result = volatility_ai.transformer_predict(data)
            features["transformer_big_candle_prob"] = transformer_result['big_candle_prob']
            features["transformer_breakout_prob"] = transformer_result['breakout_prob']
            features["transformer_burst_prob"] = transformer_result['volatility_burst_prob']
            features["transformer_forecast_confidence"] = transformer_result['forecast_confidence']
        except Exception as e:
            logger.debug(f"✓ Transformer using defaults: {e}")
            features["transformer_big_candle_prob"] = 0.1
            features["transformer_breakout_prob"] = 0.1
            features["transformer_burst_prob"] = 0.05
            features["transformer_forecast_confidence"] = 0.5
    else:
        features["transformer_big_candle_prob"] = 0.1
        features["transformer_breakout_prob"] = 0.1
        features["transformer_burst_prob"] = 0.05
        features["transformer_forecast_confidence"] = 0.5

    # 🔥 3. VOLATILITY REGIME DETECTION
    if volatility_ai is not None:
        try:
            regime_result = volatility_ai.detect_volatility_regime(data)
            features["vol_regime"] = regime_result['regime']
            features["vol_regime_score"] = regime_result['regime_score']
            features["vol_regime_stability"] = regime_result['stability']
            features["vol_time_to_change"] = regime_result['time_to_change']
        except Exception as e:
            logger.debug(f"✓ Volatility regime using defaults: {e}")
            features["vol_regime"] = 'MEDIUM'
            features["vol_regime_score"] = 0.5
            features["vol_regime_stability"] = 0.5
            features["vol_time_to_change"] = 10
    else:
        features["vol_regime"] = 'MEDIUM'
        features["vol_regime_score"] = 0.5
        features["vol_regime_stability"] = 0.5
        features["vol_time_to_change"] = 10

    # 🔥 4. VOLUME + VOLATILITY SPIKE DETECTOR
    if volatility_ai is not None:
        try:
            spike_result = volatility_ai.detect_volatility_spike(data)
            features["vol_spike_volume"] = spike_result['volume_spike']
            features["vol_spike_volatility"] = spike_result['volatility_spike']
            features["vol_spike_price"] = spike_result['price_spike']
            features["vol_spike_spread"] = spike_result['spread_spike']
            features["vol_spike_intensity"] = spike_result['spike_intensity']
            features["vol_spike_type"] = spike_result['spike_type']
        except Exception as e:
            logger.debug(f"✓ Spike detection using defaults: {e}")
            features["vol_spike_volume"] = False
            features["vol_spike_volatility"] = False
            features["vol_spike_price"] = False
            features["vol_spike_spread"] = False
            features["vol_spike_intensity"] = 0.0
            features["vol_spike_type"] = 'NONE'
    else:
        features["vol_spike_volume"] = False
        features["vol_spike_volatility"] = False
        features["vol_spike_price"] = False
        features["vol_spike_spread"] = False
        features["vol_spike_intensity"] = 0.0
        features["vol_spike_type"] = 'NONE'

    # 🔥 5. ATR + STANDARD DEVIATION DYNAMIC SL/TP
    try:
        # Tính ATR và Standard Deviation cho toàn bộ data
        df_h1 = data.get('H1')
        if df_h1 is not None and len(df_h1) > 20:
            # ATR calculation
            high_low = df_h1['high'] - df_h1['low']
            features["atr"] = float(high_low.rolling(14).mean().iloc[-1])

            # Standard Deviation
            returns = df_h1['close'].pct_change()
            features["std_dev"] = float(returns.rolling(20).std().iloc[-1])
        else:
            features["atr"] = 2.0  # Default
            features["std_dev"] = 0.02  # Default
    except Exception as e:
        logger.debug(f"✓ ATR/STD using defaults: {e}")
        features["atr"] = 2.0
        features["std_dev"] = 0.02

    # 🔥 6. NEWS-BASED VOLATILITY AI
    if volatility_ai is not None:
        try:
            news_level = volatility_ai.classify_news(news)
            features["news_level"] = news_level

            # Convert news level to descriptive
            news_descriptions = {
                0: 'LIGHT',
                1: 'MEDIUM',
                2: 'STRONG',
                3: 'CRITICAL'
            }
            features["news_impact"] = news_descriptions.get(news_level, 'UNKNOWN')

        except Exception as e:
            logger.debug(f"✓ News classification using defaults: {e}")
            features["news_level"] = 0
            features["news_impact"] = 'LIGHT'
    else:
        features["news_level"] = 0
        features["news_impact"] = 'LIGHT'

    # Meta information
    try:
        features['_meta'] = {
            'computed_at': datetime.utcnow().isoformat(),
            'source': 'build_volatility_features',
            'version': 'VOLATILITY_AI_PRO_v1.0'
        }
    except Exception:
        features['_meta'] = None

    return features


class ReversalAI:
    """AI Model cho reversal prediction - Dự đoán xác suất đảo chiều"""

    def __init__(self, model_path='ai_reversal_model.pkl', scaler_path='ai_reversal_scaler.pkl'):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = None
        self.is_trained = False

    def prepare_features(self, df):
        """Chuẩn bị features cho reversal detection"""
        df = df.copy()

        # Thêm thông tin session (Asia/EU/US) — hữu ích cho reversal patterns theo giờ
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

        # ========== TREND ANALYSIS ==========
        df = TechnicalIndicators.analyze_trend(df, short_period=20, long_period=50)

        # ========== VOLUME ANALYSIS ==========
        df = TechnicalIndicators.analyze_volume(df)

        # ========== PRICE ACTION ==========
        df['price_change'] = df['close'].pct_change()
        df['high_low_ratio'] = df['high'] / df['low']
        df['body_size'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])

        # ========== MOMENTUM & VOLATILITY ==========
        df['momentum_5'] = df['close'] / df['close'].shift(5) - 1
        df['momentum_10'] = df['close'] / df['close'].shift(10) - 1
        df['volatility'] = df['close'].rolling(10).std()

        # ========== REVERSAL SIGNALS ==========
        # RSI divergence (simplified)
        df['rsi_divergence'] = np.where(
            (df['close'] > df['close'].shift(5)) & (df['rsi'] < df['rsi'].shift(5)), 1,
            np.where((df['close'] < df['close'].shift(5)) & (df['rsi'] > df['rsi'].shift(5)), -1, 0)
        )

        # MACD divergence
        df['macd_divergence'] = np.where(
            (df['close'] > df['close'].shift(5)) & (df['macd'] < df['macd'].shift(5)), 1,
            np.where((df['close'] < df['close'].shift(5)) & (df['macd'] > df['macd'].shift(5)), -1, 0)
        )

        # Volume spike
        df['volume_spike'] = df['volume'] / df['volume'].rolling(20).mean()

        # Support/Resistance proximity
        df['near_support'] = (df['close'] - df['support_level']) / df['atr'] if 'support_level' in df else 0
        df['near_resistance'] = (df['resistance_level'] - df['close']) / df['atr'] if 'resistance_level' in df else 0

        # ========== TARGET: REVERSAL PROBABILITY ==========
        # Simplified: Look ahead 5 candles for significant reversal
        df['future_high'] = df['high'].rolling(5).max().shift(-5)
        df['future_low'] = df['low'].rolling(5).min().shift(-5)
        df['future_return'] = df['close'].shift(-5) / df['close'] - 1

        # Reversal if price moves against current trend significantly
        current_trend = np.where(df['close'] > df['sma_20'], 1, -1)  # 1 = uptrend, -1 = downtrend
        future_trend = np.where(df['future_return'] > 0.005, 1,
                               np.where(df['future_return'] < -0.005, -1, 0))

        df['is_reversal'] = ((current_trend == 1) & (future_trend == -1)) | \
                           ((current_trend == -1) & (future_trend == 1))
        df['target'] = df['is_reversal'].astype(int)

        # ========== SMC / Candle Pattern Features Integration ==========
        try:
            smc_score_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_score')]
            smc_recent_cols = [c for c in df.columns if c.startswith('SMC_') and c.endswith('_recent')]
            if smc_score_cols or smc_recent_cols:
                for c in smc_score_cols + smc_recent_cols:
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)

                # Aggregates usable by ReversalAI
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
            logger.debug(f"⚠️ SMC integration skipped in ReversalAI.prepare_features: {e}")

        return df

    def train_model(self, df, test_size=0.3):
        """Train XGBoost model cho reversal prediction"""
        logger.info("🧠 Đang huấn luyện mô hình ReversalAI...")
        logger.info("   - Dữ liệu sử dụng: features, target")
        logger.info("   - Thuật toán: XGBoostClassifier, n_estimators=100, max_depth=6, learning_rate=0.1, scale_pos_weight cho class mất cân bằng")
        logger.info("   - Đang thực hiện fitting mô hình...")

        df = self.prepare_features(df)

        feature_cols = [col for col in df.columns if col not in
                       ['target', 'future_return', 'future_high', 'future_low', 'is_reversal']]

        df_clean = df[feature_cols + ['target']].dropna()

        if len(df_clean) < 100:
            logger.error("❌ Không đủ dữ liệu để huấn luyện ReversalAI")
            return False

        X = df_clean[feature_cols]
        y = df_clean['target']

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )

        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)

        # Use scale_pos_weight for imbalanced classes (reversals are rare)
        pos_weight = len(y_train[y_train == 0]) / len(y_train[y_train == 1])

        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            scale_pos_weight=pos_weight,
            eval_metric='logloss'
        )

        self.model.fit(X_train_scaled, y_train)

        y_pred = self.model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)

        logger.info(f"✅ Đã huấn luyện xong ReversalAI - Độ chính xác: {accuracy:.3f}, Độ chính xác từng lớp: {precision:.3f}, Khả năng hồi tưởng: {recall:.3f}")
        try:
            save_feature_importances(self.model, feature_cols, 'ReversalAI', X=X_test_scaled, y=y_test, compute_permutation=True)
        except Exception:
            pass

        self.feature_columns = feature_cols
        self.is_trained = True
        self.save_model()

        return True

    def predict(self, features: dict):
        """
        Dự đoán xác suất reversal từ features dict

        Returns:
            float: Xác suất reversal (0.0 - 1.0)
        """
        try:
            if not self.is_trained or self.model is None or self.feature_columns is None:
                logger.debug("⚠️ ReversalAI not trained, returning 0.0")
                return 0.0

            # Build feature vector
            row = {}
            for col in self.feature_columns:
                val = features.get(col, 0.0)
                try:
                    row[col] = float(val) if val is not None else 0.0
                except Exception:
                    row[col] = 0.0

            X = pd.DataFrame([row], columns=self.feature_columns)
            X_scaled = self.scaler.transform(X)

            # Get reversal probability
            probs = self.model.predict_proba(X_scaled)[0]
            reversal_prob = float(probs[1])  # Probability of class 1 (reversal)

            return reversal_prob

        except Exception as e:
            logger.warning(f"⚠️ ReversalAI prediction failed: {e}")
            return 0.0

    def save_model(self):
        """Save model và scaler"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            joblib.dump(self.feature_columns, 'ai_reversal_feature_columns.pkl')
            logger.info(f"✅ ReversalAI model saved to {self.model_path}")
        except Exception as e:
            logger.error(f"❌ Error saving ReversalAI model: {e}")

    def load_model(self):
        """Load pre-trained model"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)

                if os.path.exists('ai_reversal_feature_columns.pkl'):
                    self.feature_columns = joblib.load('ai_reversal_feature_columns.pkl')

                self.is_trained = True
                logger.info(f"✅ ReversalAI model loaded from {self.model_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Error loading ReversalAI model: {e}")
        return False
    
    def train_model(self, df, test_size=0.3):
        """Train XGBoost model"""
        logger.info("🧠 Starting AI model training...")
        
        # Prepare features
        df = self.prepare_features(df)
        
        # Feature columns (exclude target và non-feature cols)
        feature_cols = [col for col in df.columns if col not in 
                       ['target', 'future_return', 'tr1', 'tr2', 'tr3', 'tr', 'timestamp']]
        
        # Remove rows with NaN
        df_clean = df[feature_cols + ['target']].dropna()
        
        if len(df_clean) < 100:
            logger.error("❌ Not enough data for training")
            return False
            
        X = df_clean[feature_cols]
        y = df_clean['target']
        
        # Train/test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train XGBoost
        self.model = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            random_state=42,
            eval_metric='logloss'
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        accuracy = accuracy_score(y_test, y_pred)
        
        logger.info(f"✅ Model trained - Accuracy: {accuracy:.3f}")
        try:
            save_feature_importances(self.model, feature_cols, getattr(self, '__class__', type(self)).__name__, X=X_test_scaled, y=y_test, compute_permutation=True)
        except Exception:
            pass

        # Save feature columns và model
        self.feature_columns = feature_cols
        self.is_trained = True
        
        # Save to disk
        self.save_model()
        
        return True
    
    def predict_signal(self, df):
        """Predict trading signal - KẾT HỢP INDICATORS + XGBOOST MODEL"""
        # 🆕 KẾT HỢP 2 PHƯƠNG PHÁP: INDICATORS + AI MODEL
        
        # Prepare features để có các indicators
        df = self.prepare_features(df)
        
        # Lấy nến cuối cùng
        latest = df.iloc[-1]
        
        # ========== BƯỚC 1: PHÂN TÍCH CÁC CHỈ BÁO (60% TRỌNG SỐ) ==========
        score_buy = 0   # Điểm xu hướng MUA
        score_sell = 0  # Điểm xu hướng BÁN
        
        # 1. RSI - Relative Strength Index (30 điểm)
        try:
            rsi = latest['rsi']
            if rsi < 30:        # Quá bán → Khả năng tăng
                score_buy += 30
                logger.info(f"  📊 RSI={rsi:.1f} < 30 → Quá bán → +30 BUY")
            elif rsi > 70:      # Quá mua → Khả năng giảm
                score_sell += 30
                logger.info(f"  📊 RSI={rsi:.1f} > 70 → Quá mua → +30 SELL")
            elif rsi > 50:      # Trên 50 → Bullish
                score_buy += 10
                logger.info(f"  📊 RSI={rsi:.1f} > 50 → Bullish → +10 BUY")
            else:               # Dưới 50 → Bearish
                score_sell += 10
                logger.info(f"  📊 RSI={rsi:.1f} < 50 → Bearish → +10 SELL")
        except:
            logger.warning("  ⚠️ Không có RSI")
        
        # 2. MACD (25 điểm)
        try:
            macd = latest['macd']
            macd_signal = latest['macd_signal']
            macd_hist = macd - macd_signal  # MACD Histogram
            
            if macd > macd_signal:  # MACD trên Signal → Tăng
                score_buy += 25
                logger.info(f"  📊 MACD({macd:.2f}) > Signal({macd_signal:.2f}) → +25 BUY")
                # Bonus nếu histogram đang tăng (momentum mạnh)
                if len(df) > 1:
                    prev_macd = df.iloc[-2]['macd']
                    prev_signal = df.iloc[-2]['macd_signal']
                    prev_hist = prev_macd - prev_signal
                    if macd_hist > prev_hist:
                        score_buy += 5
                        logger.info(f"  📊 MACD Histogram tăng ({macd_hist:.2f} > {prev_hist:.2f}) → +5 BUY")
            else:                    # MACD dưới Signal → Giảm
                score_sell += 25
                logger.info(f"  📊 MACD({macd:.2f}) < Signal({macd_signal:.2f}) → +25 SELL")
                # Bonus nếu histogram đang giảm (momentum mạnh)
                if len(df) > 1:
                    prev_macd = df.iloc[-2]['macd']
                    prev_signal = df.iloc[-2]['macd_signal']
                    prev_hist = prev_macd - prev_signal
                    if macd_hist < prev_hist:
                        score_sell += 5
                        logger.info(f"  📊 MACD Histogram giảm ({macd_hist:.2f} < {prev_hist:.2f}) → +5 SELL")
        except:
            logger.warning("  ⚠️ Không có MACD")
        
        # 3. Moving Averages (20 điểm)
        try:
            close = latest['close']
            sma20 = latest['sma_20']
            sma50 = latest['sma_50']
            
            if close > sma20 > sma50:   # Xu hướng tăng mạnh
                score_buy += 20
                logger.info(f"  📊 Close > SMA20 > SMA50 → Xu hướng tăng → +20 BUY")
            elif close < sma20 < sma50: # Xu hướng giảm mạnh
                score_sell += 20
                logger.info(f"  📊 Close < SMA20 < SMA50 → Xu hướng giảm → +20 SELL")
            elif close > sma20:         # Trên SMA20
                score_buy += 10
                logger.info(f"  📊 Close > SMA20 → +10 BUY")
            else:                        # Dưới SMA20
                score_sell += 10
                logger.info(f"  📊 Close < SMA20 → +10 SELL")
        except:
            logger.warning("  ⚠️ Không có SMA")
        
        # 4. Bollinger Bands (15 điểm)
        try:
            close = latest['close']
            bb_upper = latest['bb_upper']
            bb_lower = latest['bb_lower']
            bb_middle = latest['bb_middle']
            
            if close < bb_lower:        # Dưới band dưới → Quá bán
                score_buy += 15
                logger.info(f"  📊 Close < BB_Lower → Quá bán → +15 BUY")
            elif close > bb_upper:      # Trên band trên → Quá mua
                score_sell += 15
                logger.info(f"  📊 Close > BB_Upper → Quá mua → +15 SELL")
            elif close > bb_middle:     # Trên middle
                score_buy += 5
                logger.info(f"  📊 Close > BB_Middle → +5 BUY")
            else:                        # Dưới middle
                score_sell += 5
                logger.info(f"  📊 Close < BB_Middle → +5 SELL")
        except:
            logger.warning("  ⚠️ Không có Bollinger")
        
        # 5. Stochastic (10 điểm)
        try:
            stoch_k = latest['stoch_k']
            if stoch_k < 20:            # Quá bán
                score_buy += 10
                logger.info(f"  📊 Stoch_K={stoch_k:.1f} < 20 → Quá bán → +10 BUY")
            elif stoch_k > 80:          # Quá mua
                score_sell += 10
                logger.info(f"  📊 Stoch_K={stoch_k:.1f} > 80 → Quá mua → +10 SELL")
        except:
            logger.warning("  ⚠️ Không có Stochastic")
        
        # ========== TÍNH TOÁN KẾT QUẢ ==========
        total_score = score_buy + score_sell
        
        if total_score == 0:
            # Không có indicators → Fallback dựa vào price action
            logger.warning("⚠️ Không có indicators - Dùng price action")
            close = latest['close']
            prev_close = df.iloc[-2]['close'] if len(df) > 1 else close
            
            if close > prev_close:
                action = "BUY"
                confidence = 0.51
            else:
                action = "SELL"
                confidence = 0.51
        else:
            # Tính confidence từ indicators (60% trọng số)
            if score_buy > score_sell:
                action = "BUY"
                indicator_confidence = score_buy / total_score
            else:
                action = "SELL"
                indicator_confidence = score_sell / total_score
        
        # ========== BƯỚC 2: XGBOOST MODEL DỰ ĐOÁN (40% TRỌNG SỐ) ==========
        model_confidence = 0.5  # Default nếu model không có
        
        if self.is_trained and self.model is not None:
            try:
                # Prepare data for model
                latest_data = df.iloc[[-1]]  # Get last row
                
                # Select feature columns
                X = latest_data[self.feature_columns].fillna(0)
                X_scaled = self.scaler.transform(X)
                
                # Predict probability [prob_DOWN, prob_UP]
                probabilities = self.model.predict_proba(X_scaled)[0]
                prob_down = probabilities[0]
                prob_up = probabilities[1]
                
                logger.info(f"🤖 XGBOOST MODEL DỰ ĐOÁN:")
                logger.info(f"   📉 Xác suất DOWN: {prob_down*100:.1f}%")
                logger.info(f"   📈 Xác suất UP: {prob_up*100:.1f}%")
                
                # Lấy confidence từ model theo hướng đã chọn
                if action == "BUY":
                    model_confidence = prob_up
                else:  # SELL
                    model_confidence = prob_down
                    
                logger.info(f"   🎯 Model confidence cho {action}: {model_confidence*100:.1f}%")
                
            except Exception as e:
                logger.warning(f"⚠️ Model prediction failed: {e}, using indicators only")
                model_confidence = indicator_confidence  # Fallback
        else:
            logger.info("ℹ️ Model chưa train - Chỉ dùng Indicators")
            model_confidence = indicator_confidence
        
        # ========== BƯỚC 3: KẾT HỢP CONFIDENCE ==========
        # Indicators (60%) + Model (40%)
        final_confidence = (indicator_confidence * 0.6) + (model_confidence * 0.4)
        
        # Đảm bảo confidence trong khoảng 0.4-0.99
        final_confidence = max(0.40, min(0.99, final_confidence))
        
        logger.info(f"🎯 KẾT QUẢ CUỐI CÙNG:")
        logger.info(f"   💚 Điểm BUY: {score_buy}")
        logger.info(f"   ❤️ Điểm SELL: {score_sell}")
        logger.info(f"   📊 Độ tin cậy Indicators: {indicator_confidence*100:.1f}% (60% trọng số)")
        logger.info(f"   🤖 Độ tin cậy Model: {model_confidence*100:.1f}% (40% trọng số)")
        logger.info(f"   ⚡ KẾT QUẢ CUỐI CÙNG: {action} với độ tin cậy {final_confidence*100:.1f}%")
        
        return action, final_confidence

    def detect_reversal(self, df):
        """Detect potential reversals and compute a reversal confidence (0-1).

        Uses combination of simple heuristics:
         - RSI/MACD divergence
         - Momentum shift (trend_momentum drop)
         - Volume spike supporting reversal
         - Break of recent support/resistance
         - Sudden drop in trend_quality

        Returns:
            tuple: (reversal_flag: bool, reversal_confidence: float)
        """
        try:
            df = df.copy()
            # Ensure features exist
            if 'rsi' not in df or 'macd' not in df:
                df = self.prepare_features(df)

            latest = df.iloc[-1]
            prev = df.iloc[-3] if len(df) > 3 else df.iloc[0]

            # 1) Divergence: price higher high but RSI lower high (bearish), or vice versa
            div_score = 0.0
            try:
                price_now = latest['close']
                price_prev = prev['close']
                rsi_now = latest['rsi']
                rsi_prev = prev['rsi']
                # Bearish divergence
                if price_now > price_prev and rsi_now < rsi_prev:
                    div_score = 1.0
                # Bullish divergence
                elif price_now < price_prev and rsi_now > rsi_prev:
                    div_score = 1.0
            except Exception:
                div_score = 0.0

            # 2) Momentum shift: trend_momentum fell sharply
            mom_score = 0.0
            try:
                mom_now = latest.get('trend_momentum', 0.0)
                mom_prev = prev.get('trend_momentum', 0.0)
                if abs(mom_prev) > 1e-6:
                    drop = (mom_prev - mom_now) / (abs(mom_prev) + 1e-8)
                else:
                    drop = 0.0
                mom_score = max(0.0, min(1.0, drop))
            except Exception:
                mom_score = 0.0

            # 3) Volume spike supporting reversal
            vol_score = 0.0
            try:
                vol_now = latest.get('volume', 0.0)
                vol_sma = latest.get('volume_sma', 0.0)
                if vol_sma and vol_now > vol_sma * 1.5:
                    vol_score = 1.0
            except Exception:
                vol_score = 0.0

            # 4) Support/Resistance break
            sr_score = 0.0
            try:
                close = latest['close']
                res = latest.get('resistance_level', None)
                sup = latest.get('support_level', None)
                if res and close > res * 0.995:
                    sr_score = 0.8 if close > res else 0.0
                if sup and close < sup * 1.005:
                    sr_score = max(sr_score, 0.8 if close < sup else 0.0)
            except Exception:
                sr_score = 0.0

            # 5) Trend quality sudden drop
            tq_score = 0.0
            try:
                tq_now = latest.get('trend_quality', 1.0)
                tq_prev = prev.get('trend_quality', 1.0)
                if tq_prev > 1e-6:
                    drop_tq = (tq_prev - tq_now) / (tq_prev + 1e-8)
                    tq_score = max(0.0, min(1.0, drop_tq))
            except Exception:
                tq_score = 0.0

            # Weighted aggregation
            # Give more weight to divergence and momentum
            weight_div = 0.30
            weight_mom = 0.30
            weight_vol = 0.15
            weight_sr = 0.15
            weight_tq = 0.10

            score = (div_score * weight_div + mom_score * weight_mom +
                     vol_score * weight_vol + sr_score * weight_sr +
                     tq_score * weight_tq)

            # Normalize to 0-1
            reversal_confidence = max(0.0, min(1.0, score))
            reversal_flag = reversal_confidence >= 0.6  # default threshold

            return bool(reversal_flag), float(reversal_confidence)
        except Exception as e:
            logger.debug(f"⚠️ detect_reversal failed: {e}")
            return False, 0.0
    
    def calculate_limit_entry(self, df, action, current_price):
        """Tính giá LIMIT entry dựa trên support/resistance
        - BUY LIMIT: Đặt ở support (giá thấp hơn current, chờ giá giảm)
        - SELL LIMIT: Đặt ở resistance (giá cao hơn current, chờ giá tăng)
        """
        try:
            # Lấy support và resistance từ 20 candles gần nhất
            window = 20
            recent_data = df.tail(window)
            
            support = recent_data['low'].min()
            resistance = recent_data['high'].max()
            
            # Tính khoảng cách từ giá hiện tại đến support/resistance
            distance_to_support = current_price - support
            distance_to_resistance = resistance - current_price
            
            if action == "BUY":
                # BUY LIMIT: Đặt ở 50% khoảng cách từ current xuống support
                # Ví dụ: Current=4200, Support=4190 → Limit=4195
                limit_price = current_price - (distance_to_support * 0.5)
                entry_type = "BUY_LIMIT"
                logger.info(f"📊 BUY LIMIT - Current: {current_price:.2f}, Support: {support:.2f}, Limit Entry: {limit_price:.2f}")
            else:  # SELL
                # SELL LIMIT: Đặt ở 50% khoảng cách từ current lên resistance
                # Ví dụ: Current=4200, Resistance=4210 → Limit=4205
                limit_price = current_price + (distance_to_resistance * 0.5)
                entry_type = "SELL_LIMIT"
                logger.info(f"📊 SELL LIMIT - Current: {current_price:.2f}, Resistance: {resistance:.2f}, Limit Entry: {limit_price:.2f}")
            
            return limit_price, entry_type
            
        except Exception as e:
            logger.warning(f"⚠️ Không thể tính limit entry: {e}, dùng market order")
            # Fallback: Return current price with market order type
            return current_price, "BUY" if action == "BUY" else "SELL"
    
    def save_model(self):
        """Save model and scaler"""
        try:
            joblib.dump(self.model, self.model_path)
            joblib.dump(self.scaler, self.scaler_path)
            # Save feature columns
            joblib.dump(self.feature_columns, 'ai_feature_columns.pkl')
            logger.info(f"✅ Model saved to {self.model_path}")
            logger.info(f"✅ Feature columns saved: {len(self.feature_columns)} features")
        except Exception as e:
            logger.error(f"❌ Error saving model: {e}")
    
    def load_model(self):
        """Load pre-trained model"""
        try:
            if os.path.exists(self.model_path) and os.path.exists(self.scaler_path):
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                
                # Load feature columns if exists
                if os.path.exists('ai_feature_columns.pkl'):
                    self.feature_columns = joblib.load('ai_feature_columns.pkl')
                    logger.info(f"✅ Feature columns loaded: {len(self.feature_columns)} features")
                else:
                    logger.warning("⚠️ Feature columns file not found - Model may not work properly")
                
                self.is_trained = True
                logger.info(f"✅ Model loaded from {self.model_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Error loading model: {e}")
        return False

    def predict_from_feature_dict(self, features: dict):
        """
        Predict action and confidence from a features dictionary (single sample).

        Returns a tuple (action:str, confidence:float) where confidence is in [0.0, 1.0].
        If model is not available or prediction fails, returns ("NONE", 0.0)
        """
        try:
            if not self.is_trained or self.model is None or self.feature_columns is None:
                logger.debug("⚠️ predict_from_feature_dict: model not trained or missing feature columns")
                return "NONE", 0.0

            # Build a single-row DataFrame aligned with feature_columns
            row = {}
            for col in self.feature_columns:
                # Use provided feature or 0 fallback
                val = features.get(col, 0.0)
                # Ensure numeric
                try:
                    row[col] = float(val) if val is not None else 0.0
                except Exception:
                    row[col] = 0.0

            X = pd.DataFrame([row], columns=self.feature_columns)

            # Scale
            X_scaled = self.scaler.transform(X)

            # Predict probabilities
            probs = self.model.predict_proba(X_scaled)[0]
            prob_down = float(probs[0])
            prob_up = float(probs[1])

            # Choose action
            if prob_up >= prob_down:
                action = "BUY"
                confidence = prob_up
            else:
                action = "SELL"
                confidence = prob_down

            # Ensure 0-1
            confidence = max(0.0, min(1.0, float(confidence)))
            return action, confidence

        except Exception as e:
            logger.warning(f"⚠️ predict_from_feature_dict failed: {e}")
            return "NONE", 0.0


# ============================================
# AUTO SYSTEM MODE CONTROLLER (WINDOWS VPS)
# ============================================

