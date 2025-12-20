"""
Configuration file for AI Trading Bot
Modify these settings before deploying to VPS
"""

# ============================================================================
# MT5 CONNECTION SETTINGS
# ============================================================================
MT5_PATH = "C:/Program Files/MetaTrader 5/terminal64.exe"  # Change for VPS
MT5_LOGIN = None  # Your MT5 account number (optional)
MT5_PASSWORD = None  # Your MT5 password (optional)
MT5_SERVER = None  # Your broker server (optional)

# ============================================================================
# TRADING SETTINGS
# ============================================================================
SYMBOL = "XAUUSD"
TIMEFRAME = "M5"  # 5-minute chart
SIGNAL_INTERVAL = 300  # Generate signal every 5 minutes (300 seconds)
MIN_CONFIDENCE = 30.0  # Minimum confidence to trade (0-100) - Giảm để dễ trade hơn
ENABLE_SIDEWAYS_FILTER = False  # Filter sideways market

# ============================================================================
# MONEY MANAGER SETTINGS
# ============================================================================
USE_MONEY_MANAGER = True
INITIAL_BALANCE = 10000.0  # USD
RISK_PER_TRADE = 2.0  # % per trade
MAX_POSITIONS = 3  # Maximum concurrent positions
MAX_TOTAL_RISK = 10.0  # % maximum total risk
MIN_RISK_REWARD = 1.5  # Minimum R:R ratio

# ============================================================================
# DRAWDOWN PROTECTOR SETTINGS
# ============================================================================
USE_DRAWDOWN_PROTECTOR = True
MAX_DD_PERCENT = 20.0  # Pause trading at 20% drawdown
WARNING_DD_PERCENT = 10.0  # Warning alert at 10% drawdown
CRITICAL_DD_PERCENT = 15.0  # Critical alert at 15% drawdown
LOT_REDUCTION_FACTOR = 0.5  # Reduce lot to 50% at warning level
AUTO_RESUME_RECOVERY = 5.0  # Resume after 5% recovery from bottom

# ============================================================================
# HTTP SERVER SETTINGS
# ============================================================================
HTTP_PORT = 6555
HTTP_HOST = "127.0.0.1"  # Localhost only (secure)

# ============================================================================
# DATA SETTINGS
# ============================================================================
TRAINING_BARS = 17280  # 60 days of 5M data for training
MIN_BARS_REQUIRED = 1000  # Minimum bars needed to start

# ============================================================================
# AI MODEL SETTINGS
# ============================================================================
TRAIN_NEW_MODEL = False  # True = train new, False = use existing
SKIP_BACKTEST = True  # Skip backtest on startup for faster start
MODEL_PATH = "models/xgboost_trend_model.pkl"  # Relative path

# ============================================================================
# LOGGING SETTINGS
# ============================================================================
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR
LOG_TO_FILE = True
LOG_FILE_PATH = "logs/trading_bot.log"

# ============================================================================
# TELEGRAM BOT SETTINGS (TODO)
# ============================================================================
TELEGRAM_ENABLED = False
TELEGRAM_BOT_TOKEN = ""  # Your bot token
TELEGRAM_CHAT_ID = ""  # Your chat ID

# ============================================================================
# BALANCE -> LOT CAP MAPPING (user-configurable)
# Each tuple: (min_inclusive, max_exclusive, lot_cap)
# The system will use the first matching range to determine the per-order lot cap.
BALANCE_LOT_CAPS = [
	(0.0, 1000.0, 0.2),
	(5000.0, 10000.0, 0.5),
	(20000.0, 40000.0, 0.25),
	(40000.0, 100000.0, 0.68),
	(100000.0, float('inf'), 1.68),
]

# Toggle whether to enforce user-configured BALANCE_LOT_CAPS mapping.
# If False, the AI's computed lot size is used (only `live_lot_cap` acts as a safety cap).
RESPECT_BALANCE_LOT_CAPS = False

# Minimum lot size used across the system (can be increased for brokers with higher min lot)
# Default remains 0.01 (one centilot / typical MT5 minimum for many brokers).
MIN_LOT = 0.01

def get_balance_lot_cap_for_balance(balance: float) -> float:
	"""Return lot cap for a given balance using BALANCE_LOT_CAPS mapping."""
	try:
		b = float(balance or 0.0)
		for lo, hi, cap in BALANCE_LOT_CAPS:
			if b >= lo and b < hi:
				return float(cap)
	except Exception:
		pass
	# safe fallback
	return 0.05
