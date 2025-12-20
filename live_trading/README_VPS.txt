# AI TRADING BOT - VPS DEPLOYMENT PACKAGE

##  Nội dung đã được tối ưu cho VPS

###  Files quan trọng được giữ lại:
- **Core system**: core/, ai_modules/, logic/
- **Models**: *.pkl (TrendAI, Scaler, Feature columns)
- **Config**: config/, requirements.txt
- **Scripts**: train.bat, TRAIN_TRENDAI.bat, start_ai_trading*.bat

###  Đã xóa (không cần trên VPS):
- logs/ - Log files cũ
- __pycache__/ - Python cache
- archive/, backtests/ - Backup data
- tests/, models_test/ - Test files
- *.csv, *.json - Temporary data
- Docs không cần thiết

###  CÁCH CHẠY TRÊN VPS:

1. **Upload lên VPS**:
   - Copy toàn bộ thư mục live_trading
   - Đảm bảo có Python 3.13+ và MT5

2. **Cài đặt dependencies**:
   `
   pip install -r requirements.txt
   `

3. **Chạy bot**:
   `
   start_ai_trading_vps.bat
   `
   Hoặc:
   `
   python -m core.complete_ai_trading_system --continuous --min-confidence 60
   `

###  Bảo vệ đã bật:
- DrawdownProtector: 15% max loss
- RiskAI: Kiểm soát từng lệnh
- Signal cooldown: 5s
- AI timeout: 30s
- Sleep: 2s (không spam)

###  Kích thước: ~179 MB
###  Số files: 118

---
Đã clean và ready để deploy! 
