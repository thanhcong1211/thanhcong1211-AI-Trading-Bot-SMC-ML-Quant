# HƯỚNG DẪN ĐƯA BOT AI LÊN VPS WINDOWS

## 1. Cài đặt môi trường trên VPS

- **Cài Python 3.8+**: https://www.python.org/downloads/windows/ (chọn Add Python to PATH khi cài)
- **Cài Git (nếu cần)**: https://git-scm.com/download/win

## 2. Copy mã nguồn bot lên VPS
- Dùng WinSCP, FileZilla, hoặc copy qua Remote Desktop.
- Đặt toàn bộ thư mục bot vào, ví dụ: `C:\AI_BOT\MQL5\live_trading`

## 3. Mở CMD hoặc PowerShell, chuyển vào thư mục bot
```powershell
cd C:\AI_BOT\MQL5\live_trading
```

## 4. Tạo và kích hoạt môi trường ảo Python
```powershell
python -m venv .venv
.venv\Scripts\activate
```

## 5. Cài đặt thư viện cần thiết
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```
Nếu chưa có requirements.txt, dùng:
```powershell
pip install pandas numpy scikit-learn xgboost joblib requests psutil
```

## 6. Kiểm tra lại cấu hình
- Đảm bảo các file `.py` chính, model `.pkl`, thư mục `logic/` đều có trên VPS.
- Nếu dùng MetaTrader5, cài đặt MT5 và cấu hình EA như trên máy local.

## 7. Chạy thử bot
**Training (nếu cần):**
```powershell
python complete_ai_trading_system.py --train
```
**Chạy bot live:**
```powershell
python complete_ai_trading_system.py
```
Hoặc:
```powershell
.\start_ai_trading.bat
```

## 8. (Tùy chọn) Tự động chạy khi VPS khởi động
- Tạo shortcut tới batch file hoặc script Python trong thư mục Startup của Windows.

---

### Tóm tắt lệnh cài đặt nhanh
```powershell
cd C:\AI_BOT\MQL5\live_trading
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install pandas numpy scikit-learn xgboost joblib requests psutil MetaTrader5   
pip install MetaTrader5   
python complete_ai_trading_system.py
```

> Nếu gặp lỗi thiếu thư viện, chỉ cần cài thêm bằng pip install <tên_thư_viện>.
> Nếu dùng môi trường ảo, luôn kích hoạt .venv trước khi chạy bot.
