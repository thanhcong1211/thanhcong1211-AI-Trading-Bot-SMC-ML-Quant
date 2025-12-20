#!/usr/bin/env python3
"""
🧠 TRAIN TRENDAI MODEL - Kết hợp SMC + ML
===========================================
Script này train TrendAI model với dữ liệu lịch sử GOLD
để system có thể dùng cả SMC heuristic + ML predictions
"""

import sys
import os
import pandas as pd
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.models import TrendAI
from core.data_fetcher import DataFetcher
import MetaTrader5 as mt5

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def fetch_training_data(symbol='GOLD', timeframe='H1', days=90):
    """Lấy dữ liệu từ MT5 để training"""
    logger.info(f"🔄 Đang lấy dữ liệu training từ MT5...")
    logger.info(f"   Symbol: {symbol}")
    logger.info(f"   Timeframe: {timeframe}")
    logger.info(f"   Days: {days}")
    
    try:
        # Khởi tạo MT5
        if not mt5.initialize():
            logger.error("❌ Không thể khởi tạo MT5")
            return None
        
        # Fetch data
        fetcher = DataFetcher(symbol=symbol)
        
        if timeframe == 'H1':
            bars = days * 24
            df = fetcher.fetch_h1_data(count=bars)
        elif timeframe == 'H4':
            bars = days * 6
            df = fetcher.fetch_h4_data(count=bars)
        else:
            bars = days * 24
            df = fetcher.fetch_h1_data(count=bars)
        
        if df is None or len(df) == 0:
            logger.error("❌ Không lấy được dữ liệu từ MT5")
            return None
        
        logger.info(f"✅ Đã lấy {len(df)} bars từ MT5")
        return df
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi lấy dữ liệu: {e}")
        return None
    finally:
        try:
            mt5.shutdown()
        except:
            pass


def load_csv_data(csv_path='mt5_h1.csv'):
    """Load dữ liệu từ CSV nếu có"""
    try:
        if os.path.exists(csv_path):
            logger.info(f"📂 Đang load dữ liệu từ {csv_path}...")
            df = pd.read_csv(csv_path)
            
            # Convert time column to datetime if needed
            if 'time' in df.columns:
                df['time'] = pd.to_datetime(df['time'])
                df = df.set_index('time')
            
            logger.info(f"✅ Đã load {len(df)} rows từ CSV")
            return df
        else:
            logger.warning(f"⚠️ File {csv_path} không tồn tại")
            return None
    except Exception as e:
        logger.error(f"❌ Lỗi khi load CSV: {e}")
        return None


def main():
    """Main training function"""
    logger.info("=" * 80)
    logger.info("🧠 BẮT ĐẦU TRAINING TRENDAI MODEL")
    logger.info("=" * 80)
    
    # Step 1: Load data
    logger.info("\n📊 BƯỚC 1: LOAD DỮ LIỆU TRAINING")
    logger.info("-" * 80)
    
    # Try CSV first
    df = load_csv_data('mt5_h1.csv')
    
    # If no CSV, fetch from MT5
    if df is None or len(df) < 1000:
        logger.info("⚠️ CSV không có hoặc không đủ dữ liệu, fetch từ MT5...")
        df = fetch_training_data(symbol='GOLD', timeframe='H1', days=90)
    
    if df is None or len(df) < 100:
        logger.error("❌ Không có dữ liệu để training!")
        logger.error("   Hãy đảm bảo:")
        logger.error("   1. MT5 đang chạy và login")
        logger.error("   2. Symbol GOLD có sẵn dữ liệu")
        logger.error("   3. Hoặc có file mt5_h1.csv trong thư mục")
        return False
    
    logger.info(f"✅ Sẵn sàng training với {len(df)} bars")
    
    # Step 2: Initialize TrendAI
    logger.info("\n🤖 BƯỚC 2: KHỞI TẠO TRENDAI MODEL")
    logger.info("-" * 80)
    
    trend_ai = TrendAI(
        model_path='trend_ai_model.pkl',
        scaler_path='trend_ai_scaler.pkl'
    )
    
    # Step 3: Train model
    logger.info("\n🧠 BƯỚC 3: TRAINING MODEL")
    logger.info("-" * 80)
    logger.info("⏳ Quá trình training có thể mất vài phút...")
    logger.info("   - Chuẩn bị features (SMC indicators, technical analysis)")
    logger.info("   - Training XGBoost classifier")
    logger.info("   - Đánh giá accuracy trên test set")
    logger.info("   - Lưu model và scaler")
    
    success = trend_ai.train_model(df, test_size=0.3)
    
    if success:
        logger.info("\n" + "=" * 80)
        logger.info("✅ TRAINING THÀNH CÔNG!")
        logger.info("=" * 80)
        logger.info(f"📁 Model đã lưu tại: {trend_ai.model_path}")
        logger.info(f"📁 Scaler đã lưu tại: {trend_ai.scaler_path}")
        logger.info(f"📁 Feature columns đã lưu tại: trend_ai_feature_columns.pkl")
        logger.info("\n🚀 Bây giờ TrendAI sẽ sử dụng SMC + ML predictions!")
        logger.info("   Chạy bot với lệnh:")
        logger.info("   cd live_trading")
        logger.info("   python -m core.complete_ai_trading_system --continuous --min-confidence 60")
        return True
    else:
        logger.error("\n" + "=" * 80)
        logger.error("❌ TRAINING THẤT BẠI!")
        logger.error("=" * 80)
        logger.error("   Kiểm tra logs phía trên để xem chi tiết lỗi")
        return False


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Training bị dừng bởi người dùng")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Lỗi không mong đợi: {e}", exc_info=True)
        sys.exit(1)
