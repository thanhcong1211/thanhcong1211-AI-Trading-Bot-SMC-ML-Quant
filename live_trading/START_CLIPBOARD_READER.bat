@echo off
echo ========================================
echo  TRADINGVIEW AUTO CLIPBOARD READER
echo  100%% FREE - No Webhook Needed!
echo ========================================
echo.
echo Starting clipboard monitor...
echo.
echo HOW TO USE:
echo 1. Keep this window open
echo 2. On TradingView: Create Alert
echo 3. Copy alert message (Ctrl+C)
echo 4. Script auto-detects and validates!
echo.
echo ========================================
echo.

cd /d "%~dp0"
call .venv\Scripts\activate
python -m logic.tradingview.tradingview_clipboard_reader

pause
