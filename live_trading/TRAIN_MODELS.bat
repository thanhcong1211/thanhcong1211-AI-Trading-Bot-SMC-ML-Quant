@echo off
echo ================================================================
echo    TRAIN AI MODELS - Complete AI Trading Bot
echo ================================================================
echo.
echo This will train 3 ML models:
echo   1. TrendAI (XGBoost) - UP/DOWN/SIDEWAY
echo   2. ReversalAI (XGBoost) - Reversal probability
echo   3. SentimentAI (RandomForest) - Market sentiment
echo.
echo Training time: 5-10 minutes
echo Output: models_large\ directory
echo.
pause

python tools\train_models.py --symbol XAUUSD --timeframe H1 --days 365 --output models_large

echo.
echo ================================================================
echo    TRAINING COMPLETED!
echo ================================================================
echo.
echo Models saved to: models_large\
echo.
echo Next step: Run bot with trained models
echo   cd ..
echo   .\START_BOT.bat
echo.
pause
