"""
Live Trading Core - Main Entry Point
====================================
Run with: python -m live_trading.core
"""

import sys
import os

# Add parent directory to path to enable imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import and run main function from complete_ai_trading_system
from live_trading.core.complete_ai_trading_system import main

if __name__ == '__main__':
    main()
