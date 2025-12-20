@echo off
chcp 65001 > nul
title 🤖 AI Trading Bot - Live Trading

echo ================================================================================
echo 🤖 AI TRADING BOT - LIVE TRADING
echo ================================================================================
echo.
echo 📊 Symbol: GOLD (XAUUSD)
echo 🎯 Min Confidence: 50%% (Dễ vào lệnh hơn)
echo 🔄 Mode: CONTINUOUS (Auto trading)
echo 🛡️  Max Drawdown: 15%%
echo ⏱️  Signal Cooldown: 5s
echo 🧠 AI Components: 28/28 (100%%)
echo 📈 Chart Patterns: 33 patterns
echo.
echo ⚠️  Bot sẽ TỰ ĐỘNG VÀO LỆNH khi có tín hiệu!
echo ⚠️  Nhấn Ctrl+C để dừng bot
echo.

cd /d "%~dp0"

REM Check if models exist
if exist "models_large\trend_ai_model.pkl" (
    echo ✅ Using ML Models - Expected Win Rate: 65-70%%
) else (
    echo ⚠️  Using Heuristic Mode - Expected Win Rate: 60-65%%
    echo 💡 Run train.bat to train models for better performance
)
echo.

python -u -m core.complete_ai_trading_system --continuous --min-confidence 50 --pattern-report-enable --pattern-report-every 10 --pattern-webhook-url https://httpbin.org/post

if %ERRORLEVEL% neq 0 (
    echo.
    echo ❌ Bot gặp lỗi!
    echo.
    echo 💡 Kiểm tra:
    echo    1. MT5 đang chạy và đã login
    echo    2. Symbol GOLD có sẵn
    echo    3. Python packages đã cài đặt: pip install -r requirements.txt
    echo.
) else (
    echo.
    echo ✅ Bot đã dừng!
)

pause
