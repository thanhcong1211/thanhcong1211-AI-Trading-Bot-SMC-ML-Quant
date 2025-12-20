"""
Tool tự động train 3 mô hình ML chính:
1. TrendAI Model (XGBoost)
2. ReversalAI Model (XGBoost) 
3. SentimentAI Model (RandomForest)

Usage:
    python tools/train_models.py --symbol GOLD --timeframe H1 --days 365
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pickle
import json
import argparse
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
import MetaTrader5 as mt5

def connect_mt5():
    """Kết nối MT5"""
    if not mt5.initialize():
        print("MT5 initialize failed")
        return False
    print(f"✅ MT5 Connected: {mt5.terminal_info()}")
    return True

def get_historical_data(symbol='XAUUSD', timeframe='H1', days=365):
    """Lấy dữ liệu lịch sử từ MT5"""
    tf_map = {'M5': mt5.TIMEFRAME_M5, 'H1': mt5.TIMEFRAME_H1, 'H4': mt5.TIMEFRAME_H4}
    
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)
    
    rates = mt5.copy_rates_range(symbol, tf_map[timeframe], start_time, end_time)
    
    if rates is None or len(rates) == 0:
        print(f"❌ No data for {symbol} {timeframe}")
        return None
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    print(f"✅ Loaded {len(df)} bars from {start_time.date()} to {end_time.date()}")
    return df

def calculate_features(df):
    """Tính các features cho ML"""
    df = df.copy()
    
    # Technical indicators
    df['sma_20'] = df['close'].rolling(20).mean()
    df['sma_50'] = df['close'].rolling(50).mean()
    df['sma_200'] = df['close'].rolling(200).mean()
    df['ema_12'] = df['close'].ewm(span=12).mean()
    df['ema_26'] = df['close'].ewm(span=26).mean()
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = ranges.max(axis=1).rolling(14).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    
    # Momentum
    df['momentum'] = df['close'] / df['close'].shift(10) - 1
    df['roc'] = (df['close'] - df['close'].shift(10)) / df['close'].shift(10)
    
    # Volatility
    df['volatility'] = df['close'].pct_change().rolling(20).std()
    
    # Price action
    df['body_size'] = np.abs(df['close'] - df['open'])
    df['upper_wick'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['lower_wick'] = df[['close', 'open']].min(axis=1) - df['low']
    
    return df

def create_trend_labels(df, lookahead=5):
    """Tạo labels cho TrendAI: 2=UP, 1=SIDEWAY, 0=DOWN"""
    future_return = (df['close'].shift(-lookahead) - df['close']) / df['close']
    
    labels = np.ones(len(df))  # Default = 1 (SIDEWAY)
    labels[future_return > 0.002] = 2   # UP
    labels[future_return < -0.002] = 0  # DOWN
    
    return labels

def create_reversal_labels(df, lookahead=3):
    """Tạo labels cho ReversalAI: 1=BULLISH_REVERSAL, 0=BEARISH_REVERSAL"""
    # Detect trend reversal points
    sma_20 = df['close'].rolling(20).mean()
    sma_50 = df['close'].rolling(50).mean()
    
    trend_now = (sma_20 > sma_50).astype(int)
    trend_future = (sma_20.shift(-lookahead) > sma_50.shift(-lookahead)).astype(int)
    
    # Reversal = trend change
    reversal = (trend_now != trend_future).astype(int)
    reversal_type = trend_future  # 1 if reversal to bullish, 0 if to bearish
    
    return reversal_type

def create_sentiment_labels(df, window=10):
    """Tạo labels cho SentimentAI: 1=BULLISH, 0=BEARISH, -1=NEUTRAL"""
    # Simple sentiment based on price action
    future_move = df['close'].shift(-window) / df['close'] - 1
    
    labels = np.zeros(len(df))
    labels[future_move > 0.001] = 1    # BULLISH
    labels[future_move < -0.001] = 0   # BEARISH
    labels[(future_move >= -0.001) & (future_move <= 0.001)] = -1  # NEUTRAL
    
    return labels

def train_trend_ai(df, output_dir='models_large'):
    """Train TrendAI model"""
    print("\n📊 Training TrendAI Model...")
    
    # Calculate features
    df = calculate_features(df)
    df['label'] = create_trend_labels(df, lookahead=5)
    df = df.dropna()
    
    # Features
    feature_cols = ['sma_20', 'sma_50', 'sma_200', 'ema_12', 'ema_26', 
                    'atr', 'rsi', 'macd', 'macd_signal', 'momentum', 'roc', 
                    'volatility', 'body_size', 'upper_wick', 'lower_wick']
    
    X = df[feature_cols].values
    y = df['label'].values
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Scale
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Train XGBoost
    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.1,
        random_state=42
    )
    model.fit(X_train_scaled, y_train)
    
    # Evaluate
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"✅ TrendAI Accuracy: {accuracy*100:.2f}%")
    print(classification_report(y_test, y_pred, target_names=['DOWN', 'SIDEWAY', 'UP']))
    
    # Save
    os.makedirs(output_dir, exist_ok=True)
    with open(f'{output_dir}/trend_ai_model.pkl', 'wb') as f:
        pickle.dump(model, f)
    with open(f'{output_dir}/trend_ai_scaler.pkl', 'wb') as f:
        pickle.dump(scaler, f)
    with open(f'{output_dir}/trend_ai_feature_columns.pkl', 'wb') as f:
        pickle.dump(feature_cols, f)
    
    print(f"💾 Saved: {output_dir}/trend_ai_*.pkl")
    return model, scaler, feature_cols, accuracy

def train_reversal_ai(df, output_dir='models_large'):
    """Train ReversalAI model"""
    print("\n🔄 Training ReversalAI Model...")
    
    df = calculate_features(df)
    df['label'] = create_reversal_labels(df, lookahead=3)
    df = df.dropna()
    
    feature_cols = ['sma_20', 'sma_50', 'rsi', 'macd', 'momentum', 
                    'volatility', 'body_size', 'upper_wick', 'lower_wick']
    
    X = df[feature_cols].values
    y = df['label'].values
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    model = XGBClassifier(n_estimators=150, max_depth=5, learning_rate=0.1, random_state=42)
    model.fit(X_train_scaled, y_train)
    
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"✅ ReversalAI Accuracy: {accuracy*100:.2f}%")
    print(classification_report(y_test, y_pred, target_names=['BEARISH_REV', 'BULLISH_REV']))
    
    os.makedirs(output_dir, exist_ok=True)
    with open(f'{output_dir}/reversal_ai_model.pkl', 'wb') as f:
        pickle.dump(model, f)
    with open(f'{output_dir}/reversal_ai_scaler.pkl', 'wb') as f:
        pickle.dump(scaler, f)
    with open(f'{output_dir}/reversal_ai_feature_columns.pkl', 'wb') as f:
        pickle.dump(feature_cols, f)
    
    print(f"💾 Saved: {output_dir}/reversal_ai_*.pkl")
    return model, scaler, feature_cols, accuracy

def train_sentiment_ai(df, output_dir='models_large'):
    """Train SentimentAI model"""
    print("\n💭 Training SentimentAI Model...")
    
    df = calculate_features(df)
    df['label'] = create_sentiment_labels(df, window=10)
    df = df.dropna()
    
    feature_cols = ['sma_20', 'sma_50', 'rsi', 'momentum', 'volatility']
    
    X = df[feature_cols].values
    y = df['label'].values
    
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
    model.fit(X_train_scaled, y_train)
    
    y_pred = model.predict(X_test_scaled)
    accuracy = accuracy_score(y_test, y_pred)
    print(f"✅ SentimentAI Accuracy: {accuracy*100:.2f}%")
    print(classification_report(y_test, y_pred, target_names=['BEARISH', 'NEUTRAL', 'BULLISH']))
    
    os.makedirs(output_dir, exist_ok=True)
    with open(f'{output_dir}/sentiment_ai_model.pkl', 'wb') as f:
        pickle.dump(model, f)
    with open(f'{output_dir}/sentiment_ai_scaler.pkl', 'wb') as f:
        pickle.dump(scaler, f)
    with open(f'{output_dir}/sentiment_ai_feature_columns.pkl', 'wb') as f:
        pickle.dump(feature_cols, f)
    
    print(f"💾 Saved: {output_dir}/sentiment_ai_*.pkl")
    return model, scaler, feature_cols, accuracy

def main():
    parser = argparse.ArgumentParser(description='Train AI models')
    parser.add_argument('--symbol', default='XAUUSD', help='Symbol to train on')
    parser.add_argument('--timeframe', default='H1', choices=['M5', 'H1', 'H4'], help='Timeframe')
    parser.add_argument('--days', type=int, default=365, help='Days of historical data')
    parser.add_argument('--output', default='models_large', help='Output directory')
    args = parser.parse_args()
    
    print(f"🚀 Starting model training...")
    print(f"   Symbol: {args.symbol}")
    print(f"   Timeframe: {args.timeframe}")
    print(f"   Days: {args.days}")
    
    # Connect MT5
    if not connect_mt5():
        return
    
    # Get data
    df = get_historical_data(args.symbol, args.timeframe, args.days)
    if df is None:
        return
    
    # Train models
    results = {}
    
    trend_model, trend_scaler, trend_features, trend_acc = train_trend_ai(df, args.output)
    results['TrendAI'] = {'accuracy': trend_acc, 'features': len(trend_features)}
    
    rev_model, rev_scaler, rev_features, rev_acc = train_reversal_ai(df, args.output)
    results['ReversalAI'] = {'accuracy': rev_acc, 'features': len(rev_features)}
    
    sent_model, sent_scaler, sent_features, sent_acc = train_sentiment_ai(df, args.output)
    results['SentimentAI'] = {'accuracy': sent_acc, 'features': len(sent_features)}
    
    # Save metadata
    metadata = {
        'trained_at': datetime.now().isoformat(),
        'symbol': args.symbol,
        'timeframe': args.timeframe,
        'training_days': args.days,
        'training_samples': len(df),
        'results': results
    }
    
    with open(f'{args.output}/training_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print("\n" + "="*60)
    print("🎉 TRAINING COMPLETED!")
    print("="*60)
    print(f"📁 Models saved to: {args.output}/")
    print(f"📊 TrendAI:     {trend_acc*100:.1f}% accuracy")
    print(f"🔄 ReversalAI:  {rev_acc*100:.1f}% accuracy")
    print(f"💭 SentimentAI: {sent_acc*100:.1f}% accuracy")
    print("="*60)
    
    mt5.shutdown()

if __name__ == '__main__':
    main()
