#!/usr/bin/env python3
"""
🧠 QUICK TRAIN TRENDAI - Test nhanh với synthetic data
"""

import sys
import os
import pandas as pd
import numpy as np
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.models import TrendAI

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_synthetic_data(n=5000):
    """Tạo dữ liệu synthetic để test training"""
    logger.info(f"📊 Tạo {n} bars synthetic data để test training...")
    
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=n, freq='1H')
    
    # Tạo price movement có trend
    trend = np.linspace(4000, 4200, n) + np.random.randn(n) * 10
    
    df = pd.DataFrame({
        'time': dates,
        'open': trend + np.random.randn(n) * 5,
        'high': trend + abs(np.random.randn(n) * 10),
        'low': trend - abs(np.random.randn(n) * 10),
        'close': trend + np.random.randn(n) * 5,
        'volume': np.random.randint(1000, 10000, n),
    })
    
    # Ensure high/low logic
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    
    df = df.set_index('time')
    
    logger.info(f"✅ Đã tạo synthetic data: {len(df)} bars")
    return df


def main():
    logger.info("=" * 80)
    logger.info("🧠 QUICK TRAIN TRENDAI - TEST MODE")
    logger.info("=" * 80)
    
    # Create synthetic data
    df = create_synthetic_data(n=5000)
    
    # Initialize TrendAI
    logger.info("\n🤖 Khởi tạo TrendAI...")
    trend_ai = TrendAI(
        model_path='trend_ai_model.pkl',
        scaler_path='trend_ai_scaler.pkl'
    )
    
    # Train
    logger.info("\n🧠 Bắt đầu training...")
    logger.info("⏳ Training có thể mất 2-3 phút...")
    
    success = trend_ai.train_model(df, test_size=0.3)
    
    if success:
        logger.info("\n" + "=" * 80)
        logger.info("✅ TRAINING THÀNH CÔNG!")
        logger.info("=" * 80)
        logger.info(f"📁 Model: {trend_ai.model_path}")
        logger.info(f"📁 Scaler: {trend_ai.scaler_path}")
        logger.info("\n🚀 TrendAI sẵn sàng sử dụng SMC + ML predictions!")
        
        # Test prediction
        logger.info("\n🧪 Test prediction...")
        test_df = df.iloc[-100:]
        action, confidence = trend_ai.predict(test_df)
        logger.info(f"   Prediction: {action} (confidence: {confidence:.1%})")
        
        return True
    else:
        logger.error("\n❌ TRAINING THẤT BẠI!")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"❌ Lỗi: {e}", exc_info=True)
        sys.exit(1)
