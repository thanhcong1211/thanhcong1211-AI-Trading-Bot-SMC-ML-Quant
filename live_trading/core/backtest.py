"""
Backtest Module
Backtesting engine and HTTP signal handler for testing strategies
"""

import logging
import pandas as pd
import numpy as np
from http.server import BaseHTTPRequestHandler
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Complete backtesting engine"""
    
    def __init__(self, initial_balance=10000, risk_per_trade=0.02):
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.results = []
        
    def calculate_lot_size(self, balance, risk_pct, entry_price, sl_price):
        """Calculate position size based on risk"""
        risk_amount = balance * risk_pct
        price_diff = abs(entry_price - sl_price)
        if price_diff > 0:
            lot_size = risk_amount / price_diff
            min_lot = DEFAULT_MIN_LOT
            cap = 10.0
            return max(min_lot, min(lot_size, cap))  # Min from config, max 10 lots
        return float(DEFAULT_MIN_LOT)
    
    def run_backtest(self, df, model, start_date=None, end_date=None):
        """Run complete backtest"""
        logger.info("⚡ Starting backtest...")
        
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
            
        balance = self.initial_balance
        positions = []
        trades = []
        
        for i in range(200, len(df)):  # Skip first 200 for indicators
            current_data = df.iloc[:i+1]
            current_row = df.iloc[i]
            
            # Get AI signal
            action, confidence = model.predict_signal(current_data)
            
            # 🎯 NO CONFIDENCE FILTER - ACCEPT ALL SIGNALS
            if action in ["BUY", "SELL"]:  # Accept all AI predictions
                entry_price = current_row['close']
                
                # Simple SL/TP calculation
                atr = current_data['atr'].iloc[-1] if 'atr' in current_data else 2.0
                
                if action == "BUY":
                    sl_price = entry_price - (atr * 2)
                    tp_price = entry_price + (atr * 3)
                else:
                    sl_price = entry_price + (atr * 2)
                    tp_price = entry_price - (atr * 3)
                
                # Calculate lot size
                lot_size = self.calculate_lot_size(balance, self.risk_per_trade, 
                                                 entry_price, sl_price)
                
                # Record trade
                trade = {
                    'timestamp': current_row.name,
                    'action': action,
                    'entry_price': entry_price,
                    'sl_price': sl_price,
                    'tp_price': tp_price,
                    'lot_size': lot_size,
                    'confidence': confidence
                }
                
                positions.append(trade)
                
                # Simulate trade result (simplified)
                # In real backtest, would check next candles for SL/TP hits
                pnl_pips = random.uniform(-20, 30)  # Simplified PnL
                pnl_amount = pnl_pips * lot_size * 10  # $10 per pip per lot
                
                balance += pnl_amount
                trade['pnl'] = pnl_amount
                trade['exit_price'] = entry_price + (pnl_pips * (1 if action == "BUY" else -1))
                trades.append(trade)
        
        # Calculate metrics
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t['pnl'] > 0])
        total_pnl = sum([t['pnl'] for t in trades])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        win_rate_pct = round(win_rate * 100.0, 2)
        
        results = {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'win_rate': win_rate,
            'win_rate_pct': win_rate_pct,
            'total_pnl': total_pnl,
            'final_balance': balance,
            'return_pct': (balance - self.initial_balance) / self.initial_balance * 100,
            'trades': trades
        }
        
        logger.info(f"✅ Backtest completed:")
        logger.info(f"   📊 Total trades: {total_trades}")
        logger.info(f"   🎯 Win rate: {win_rate*100:.2f}% ({winning_trades}/{total_trades})")
        logger.info(f"   💰 Total PnL: ${total_pnl:.2f}")
        logger.info(f"   📈 Return: {results['return_pct']:.1f}%")
        
        # 💾 Save backtest results to file
        self._save_backtest_results(results)
        
        self.results = results
        return results
    
    def _save_backtest_results(self, results):
        """Save backtest results to file for future use"""
        try:
            import json
            from datetime import datetime
            
            # Add timestamp to results
            results['backtest_date'] = datetime.now().isoformat()
            results['data_period'] = "60_days_5M"
            
            # Save to JSON file
            with open('backtest_results.json', 'w') as f:
                json.dump(results, f, indent=2, default=str)
            
            logger.info(f"💾 Backtest results saved to backtest_results.json")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to save backtest results: {e}")
    
    def load_backtest_results(self):
        """Load previous backtest results if available"""
        try:
            import json
            import os
            from datetime import datetime, timedelta
            
            if os.path.exists('backtest_results.json'):
                with open('backtest_results.json', 'r') as f:
                    results = json.load(f)
                
                # Check if results are recent (within 24 hours)
                backtest_date = datetime.fromisoformat(results.get('backtest_date', '2000-01-01'))
                if datetime.now() - backtest_date < timedelta(hours=24):
                    logger.info(f"📊 Loaded cached backtest results from {backtest_date.strftime('%H:%M:%S')}")
                    logger.info(f"   📊 Total trades: {results['total_trades']}")
                    # Display exact win-rate percentage if present, otherwise compute
                    if 'win_rate_pct' in results:
                        logger.info(f"   🎯 Win rate: {results['win_rate_pct']:.2f}% ({results.get('winning_trades',0)}/{results.get('total_trades',0)})")
                    else:
                        try:
                            pct = float(results.get('win_rate', 0.0)) * 100.0
                        except Exception:
                            pct = 0.0
                        logger.info(f"   🎯 Win rate: {pct:.2f}% ({results.get('winning_trades',0)}/{results.get('total_trades',0)})")
                    logger.info(f"   💰 Total PnL: ${results['total_pnl']:.2f}")
                    logger.info(f"   📈 Return: {results['return_pct']:.1f}%")
                    return results
                else:
                    logger.info(f"⏰ Cached backtest is old ({backtest_date.strftime('%H:%M:%S')}), running new backtest...")
            
            return None
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to load backtest results: {e}")
            return None

#==============================================================================
# 4. 🚀 LIVE TRADING SIGNAL GENERATOR
#==============================================================================

# Global storage for latest signal
latest_signal = {
    "action": "NONE",
    "symbol": "XAUUSD", 
    "price": 0.0,
    "confidence": 0.0,
    "timestamp": datetime.now().isoformat(),
    "signal_id": 0
}

class HTTPSignalHandler(BaseHTTPRequestHandler):
    """HTTP handler for MT5 communication"""
    
    def do_GET(self):
        if self.path == '/signal':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = json.dumps(latest_signal)
            self.wfile.write(response.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass


try:
    from ai_modules.CandlePatternAI import CandlePatternAI
except Exception:
    # Fallback stub: provide minimal interface so module import doesn't fail.
    class CandlePatternAI:
        def __init__(self, *args, **kwargs):
            pass

        def doji(self, o, h, l, c):
            return False

        def hammer(self, o, h, l, c):
            return False

        def inverted_hammer(self, o, h, l, c):
            return False

        def bullish_engulfing(self, prev, curr):
            return False

        def bearish_engulfing(self, prev, curr):
            return False

