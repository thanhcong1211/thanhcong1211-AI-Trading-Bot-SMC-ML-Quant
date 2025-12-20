"""
TradingView Clipboard Reader - AUTO FREE SOLUTION
Đọc alerts từ TradingView (copy to clipboard) → Validate 19 AI → Execute MT5
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

import time
import json
import logging
import pyperclip
import re
from datetime import datetime
from logic.tradingview.tradingview_ai_bridge import TradingViewAIBridge

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingViewClipboardReader:
    def __init__(self):
        """Initialize clipboard reader"""
        self.bridge = TradingViewAIBridge()
        self.last_signal = ""
        self.last_process_time = 0
        self.cooldown = 5  # 5 seconds cooldown
        
        logger.info("=" * 70)
        logger.info("🎯 TRADINGVIEW CLIPBOARD READER - AUTO FREE MODE")
        logger.info("=" * 70)
        logger.info("✅ Watching clipboard for TradingView alerts...")
        logger.info("💡 How to use:")
        logger.info("   1. Open TradingView chart with AI_SMC_Advanced indicator")
        logger.info("   2. Create alert → Click 'Copy alert message'")
        logger.info("   3. This script will auto detect & process!")
        logger.info("=" * 70)
    
    def is_valid_tradingview_signal(self, text):
        """Check if clipboard contains valid TradingView JSON signal"""
        try:
            # Check if it's JSON
            if not text.strip().startswith('{'):
                return False
            
            data = json.loads(text)
            
            # Must have required fields
            required = ['action', 'price', 'symbol', 'timeframe', 'smc_score']
            if not all(key in data for key in required):
                return False
            
            # Action must be BUY or SELL
            if data['action'] not in ['BUY', 'SELL']:
                return False
            
            return True
        except:
            return False
    
    def process_signal(self, signal_json):
        """Process TradingView signal with 19 AI validation"""
        try:
            signal = json.loads(signal_json)
            
            logger.info("")
            logger.info("📨" + "=" * 68)
            logger.info(f"🎯 NEW TRADINGVIEW SIGNAL: {signal['action']}")
            logger.info("=" * 70)
            logger.info(f"💰 Price: {signal['price']}")
            logger.info(f"📊 Symbol: {signal['symbol']}")
            logger.info(f"⏰ Timeframe: {signal['timeframe']}")
            logger.info(f"🎲 SMC Score: {signal['smc_score']}/6 ({signal.get('smc_confidence', 0):.1f}%)")
            logger.info(f"📈 Structure: {signal.get('structure', 'N/A')}")
            logger.info("=" * 70)
            
            # Validate with 19 AI Modules
            logger.info("🤖 Validating with 19 AI Modules (70% weight)...")
            result = self.bridge.validate_with_ai_modules(
                action=signal['action'],
                symbol=signal['symbol'],
                timeframe=signal['timeframe'],
                tv_confidence=signal.get('smc_confidence', 50.0)
            )
            
            if result['status'] == 'success':
                logger.info("")
                logger.info("✅ " + "=" * 68)
                logger.info(f"✅ VALIDATION PASSED - Final Confidence: {result['final_confidence']:.1f}%")
                logger.info("=" * 70)
                logger.info(f"🎯 TV Weight (30%): {result['tv_score']:.1f}%")
                logger.info(f"🤖 AI Weight (70%): {result['ai_score']:.1f}%")
                logger.info(f"📊 Market Phase: {result['details']['market_phase']}")
                logger.info(f"💪 SMC Score: {result['details']['smc_score']:.1f}%")
                
                if result['details'].get('breaker_detected'):
                    logger.info("💥 Breaker Block Detected!")
                
                logger.info(f"📉 Stop Loss: {result['details']['sl']:.2f}")
                logger.info(f"📈 Take Profit: {result['details']['tp']:.2f}")
                logger.info("=" * 70)
                logger.info("🚀 Ready to execute on MT5!")
                logger.info("")
                
            else:
                logger.warning("")
                logger.warning("⚠️ " + "=" * 67)
                logger.warning(f"⚠️ VALIDATION FAILED: {result['message']}")
                logger.warning("=" * 70)
                logger.warning(f"📊 Final Confidence: {result.get('final_confidence', 0):.1f}% (Need ≥75%)")
                logger.warning(f"🎯 TV Score: {result.get('tv_score', 0):.1f}%")
                logger.warning(f"🤖 AI Score: {result.get('ai_score', 0):.1f}%")
                logger.warning("=" * 70)
                logger.warning("")
                
        except Exception as e:
            logger.error(f"❌ Error processing signal: {e}")
    
    def run(self):
        """Main loop - monitor clipboard"""
        logger.info("👀 Monitoring clipboard... (Press Ctrl+C to stop)")
        logger.info("")
        
        try:
            while True:
                try:
                    # Get clipboard content
                    clipboard_text = pyperclip.paste()
                    
                    # Check if it's new and valid
                    if clipboard_text and clipboard_text != self.last_signal:
                        if self.is_valid_tradingview_signal(clipboard_text):
                            # Cooldown check
                            current_time = time.time()
                            if current_time - self.last_process_time >= self.cooldown:
                                self.last_signal = clipboard_text
                                self.last_process_time = current_time
                                
                                # Process signal
                                self.process_signal(clipboard_text)
                            else:
                                wait_time = self.cooldown - (current_time - self.last_process_time)
                                logger.info(f"⏳ Cooldown active... wait {wait_time:.1f}s")
                    
                    # Check every 0.5 seconds
                    time.sleep(0.5)
                    
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    logger.error(f"❌ Error in main loop: {e}")
                    time.sleep(1)
                    
        except KeyboardInterrupt:
            logger.info("")
            logger.info("=" * 70)
            logger.info("👋 Clipboard reader stopped by user")
            logger.info("=" * 70)

def main():
    """Start clipboard reader"""
    reader = TradingViewClipboardReader()
    reader.run()

if __name__ == "__main__":
    main()
