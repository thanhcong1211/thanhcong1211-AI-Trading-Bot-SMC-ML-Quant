#!/usr/bin/env python3
"""
🚀 FAST AI TRADING SYSTEM - IMMEDIATE LIVE SIGNALS
Bỏ qua backtest, chỉ tạo live signals ngay lập tức
"""
import os
import time
import logging
import pandas as pd
import numpy as np
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import pickle
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class TechnicalIndicators:
    @staticmethod
    def calculate_rsi(df, period=14):
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-8)
        df['rsi'] = 100 - (100 / (1 + rs))
        return df
    
    @staticmethod
    def calculate_macd(df, fast=12, slow=26, signal=9):
        exp1 = df['close'].ewm(span=fast).mean()
        exp2 = df['close'].ewm(span=slow).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=signal).mean()
        df['macd_histogram'] = df['macd'] - df['macd_signal']
        return df

class SimpleModel:
    """Mô hình đơn giản dùng MACD + RSI để tạo signals nhanh"""
    
    def __init__(self):
        self.name = "SimpleModel"
    
    def predict_signal(self, df):
        """Tạo signals dựa trên MACD và RSI"""
        if len(df) < 50:
            return "HOLD", 30.0
            
        # Tính indicators
        df = TechnicalIndicators.calculate_rsi(df)
        df = TechnicalIndicators.calculate_macd(df)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # Signal logic
        rsi = latest['rsi']
        macd = latest['macd']
        macd_signal = latest['macd_signal']
        macd_hist = latest['macd_histogram']
        prev_macd_hist = prev['macd_histogram']
        
        # BUY conditions
        if (macd > macd_signal and 
            macd_hist > prev_macd_hist and 
            rsi > 30 and rsi < 70):
            confidence = min(80.0, 60 + abs(macd_hist) * 100)
            return "BUY", confidence
            
        # SELL conditions  
        elif (macd < macd_signal and 
              macd_hist < prev_macd_hist and 
              rsi > 30 and rsi < 70):
            confidence = min(80.0, 60 + abs(macd_hist) * 100)
            return "SELL", confidence
            
        return "HOLD", 40.0

class FastAISystem:
    def __init__(self):
        self.model = SimpleModel()
        self.logger = logging.getLogger(__name__)
        self.data = self.generate_demo_data()
        self.server_running = False
        
    def generate_demo_data(self):
        """Tạo demo data nhanh"""
        self.logger.info("📊 Generating demo data...")
        
        # Tạo 1000 candles gần đây thôi
        dates = pd.date_range(end=datetime.now(), periods=1000, freq='5T')
        np.random.seed(42)
        
        # Random walk with trend
        price = 2000.0
        prices = []
        for i in range(1000):
            change = np.random.normal(0, 2) + 0.02  # Small upward bias
            price += change
            prices.append(price)
        
        df = pd.DataFrame({
            'timestamp': dates,
            'open': prices,
            'high': [p + abs(np.random.normal(0, 1)) for p in prices],
            'low': [p - abs(np.random.normal(0, 1)) for p in prices],
            'close': prices,
            'volume': np.random.randint(100, 1000, 1000)
        })
        
        self.logger.info(f"✅ Generated {len(df)} demo candles")
        return df
    
    def get_latest_data(self):
        """Lấy 50 candles gần nhất cho prediction"""
        return self.data.tail(50).copy()
    
    def start_http_server(self):
        """Khởi động HTTP server ngay lập tức"""
        self.logger.info("🚀 Starting HTTP server on port 6555...")
        
        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/ai_signal':
                    try:
                        # Lấy data và tạo signal
                        current_data = ai_system.get_latest_data()
                        action, confidence = ai_system.model.predict_signal(current_data)
                        
                        # Chỉ trade khi confidence >= 60%
                        if confidence < 60.0:
                            action = "HOLD"
                        
                        response = {
                            "action": action,
                            "confidence": round(confidence, 1),
                            "timestamp": datetime.now().isoformat(),
                            "price": float(current_data.iloc[-1]['close']),
                            "rsi": float(current_data.iloc[-1]['rsi']) if 'rsi' in current_data.columns else 50.0,
                            "system": "FastAI"
                        }
                        
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps(response).encode())
                        
                        # Log signal
                        ai_system.logger.info(f"📡 Signal: {action} | Confidence: {confidence:.1f}% | Price: {response['price']:.2f}")
                        
                    except Exception as e:
                        self.send_response(500)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        error_response = {"error": str(e)}
                        self.wfile.write(json.dumps(error_response).encode())
                        ai_system.logger.error(f"❌ Error: {e}")
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                pass  # Suppress HTTP server logs
        
        server = HTTPServer(('localhost', 6555), RequestHandler)
        self.server_running = True
        
        def run_server():
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                server.shutdown()
                
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        self.logger.info("✅ HTTP server started successfully!")
        return server
    
    def run_live(self):
        """Chạy live signals ngay lập tức"""
        self.logger.info("🚀 Starting FAST AI Live Trading System...")
        
        # Start HTTP server
        server = self.start_http_server()
        
        self.logger.info("=" * 60)
        self.logger.info("🟢 FAST AI SYSTEM READY!")
        self.logger.info("📡 HTTP Server: http://localhost:6555/ai_signal")
        self.logger.info("⚙️  MT5 EA ready to receive signals")
        self.logger.info("🎯 Confidence threshold: ≥60%")
        self.logger.info("=" * 60)
        
        # Keep running and show live signals
        try:
            self.logger.info("🔄 Starting live signal generation loop...")
            counter = 0
            while True:
                counter += 1
                # Generate a signal every 25 seconds
                current_data = self.get_latest_data()
                action, confidence = self.model.predict_signal(current_data)
                
                # Update data with small random changes to simulate market movement
                latest_price = current_data.iloc[-1]['close']
                price_change = np.random.normal(0, 1)
                new_price = latest_price + price_change
                
                # Add new candle to data
                new_row = {
                    'timestamp': datetime.now(),
                    'open': latest_price,
                    'high': max(latest_price, new_price) + abs(np.random.normal(0, 0.5)),
                    'low': min(latest_price, new_price) - abs(np.random.normal(0, 0.5)),
                    'close': new_price,
                    'volume': np.random.randint(100, 1000)
                }
                
                self.data = pd.concat([self.data, pd.DataFrame([new_row])], ignore_index=True)
                self.data = self.data.tail(1000)  # Keep only last 1000 candles
                
                # Log live update with counter
                status = "🟢 ACTIVE" if confidence >= 60 else "🟡 STANDBY"
                self.logger.info(f"#{counter} {status} | {action} | {confidence:.1f}% | ${new_price:.2f} | Change: {price_change:+.2f}")
                
                # Show system status every 10 iterations
                if counter % 10 == 0:
                    self.logger.info(f"📊 System Status: {counter} signals generated, HTTP server running on port 6555")
                
                time.sleep(25)  # Wait 25 seconds
                
        except KeyboardInterrupt:
            self.logger.info("🛑 Keyboard interrupt - shutting down Fast AI System...")
        except Exception as e:
            self.logger.error(f"❌ Unexpected error: {e}")
        finally:
            if hasattr(server, 'shutdown'):
                server.shutdown()
            self.logger.info("✅ Fast AI System shutdown complete")

if __name__ == "__main__":
    print("🚀 FAST AI TRADING SYSTEM - IMMEDIATE LIVE SIGNALS")
    print("=" * 60)
    
    ai_system = FastAISystem()
    ai_system.run_live()