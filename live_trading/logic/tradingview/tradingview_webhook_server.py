"""
TradingView Webhook Server
Nhan webhook alerts tu TradingView va xu ly bang 19 AI Modules
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import logging
import json
from datetime import datetime
import threading
import time

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from logic.tradingview.tradingview_ai_bridge import TradingViewAIBridge
import MetaTrader5 as mt5

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Allow CORS for TradingView webhooks

# Global bridge instance
bridge = None
last_signal_time = {}
SIGNAL_COOLDOWN = 300  # 5 minutes cooldown between same signals


def init_bridge():
    """Initialize TradingView AI Bridge"""
    global bridge
    try:
        bridge = TradingViewAIBridge(
            symbol="GOLD",
            tv_exchange="TVC",
            mt5_symbol="GOLD"
        )
        logger.info("Bridge initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize bridge: {e}")
        return False


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'bridge_status': 'ready' if bridge else 'not_initialized'
    })


@app.route('/webhook', methods=['POST'])
def tradingview_webhook():
    """
    Nhan webhook tu TradingView
    
    Expected JSON format:
    {
        "action": "BUY" | "SELL",
        "price": 4200.50,
        "symbol": "GOLD",
        "timeframe": "15",
        "comment": "Optional comment"
    }
    """
    try:
        # Get data from TradingView
        data = request.get_json()
        
        if not data:
            logger.error("No JSON data received")
            return jsonify({'status': 'error', 'message': 'No data received'}), 400
        
        logger.info("="*70)
        logger.info(f"WEBHOOK RECEIVED at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Data: {json.dumps(data, indent=2)}")
        
        # Validate required fields
        action = data.get('action', '').upper()
        if action not in ['BUY', 'SELL']:
            return jsonify({
                'status': 'error',
                'message': 'Invalid action. Must be BUY or SELL'
            }), 400
        
        symbol = data.get('symbol', 'GOLD')
        price = data.get('price', 0)
        timeframe = data.get('timeframe', '15')
        comment = data.get('comment', f'TV Webhook {action}')
        
        # Check cooldown
        signal_key = f"{symbol}_{action}"
        current_time = time.time()
        
        if signal_key in last_signal_time:
            time_since_last = current_time - last_signal_time[signal_key]
            if time_since_last < SIGNAL_COOLDOWN:
                remaining = SIGNAL_COOLDOWN - time_since_last
                logger.warning(f"Signal cooldown active. Wait {remaining:.0f}s")
                return jsonify({
                    'status': 'cooldown',
                    'message': f'Please wait {remaining:.0f} seconds',
                    'action': action,
                    'symbol': symbol
                }), 429
        
        # Process signal
        result = process_signal(action, symbol, price, timeframe, comment)
        
        # Update last signal time if processed
        if result.get('status') == 'processed':
            last_signal_time[signal_key] = current_time
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


def process_signal(action, symbol, price, timeframe, comment):
    """
    Xu ly tin hieu tu TradingView
    
    Args:
        action: BUY or SELL
        symbol: Trading symbol
        price: Current price
        timeframe: Timeframe (15, 60, 240, etc.)
        comment: Comment for order
        
    Returns:
        dict: Processing result
    """
    if not bridge:
        return {
            'status': 'error',
            'message': 'Bridge not initialized'
        }
    
    try:
        logger.info(f"Processing {action} signal for {symbol} at {price}")
        
        # Step 1: Get TradingView analysis
        tf_map = {
            '1': 'M1', '5': 'M5', '15': 'M15', '30': 'M30',
            '60': 'H1', '240': 'H4', '1D': 'D1'
        }
        tv_timeframe = tf_map.get(str(timeframe), 'M15')
        
        logger.info(f"Step 1: Getting TradingView analysis ({tv_timeframe})...")
        tv_signal = bridge.get_tradingview_signal(tv_timeframe)
        
        if not tv_signal:
            return {
                'status': 'error',
                'message': 'Failed to get TradingView analysis'
            }
        
        tv_recommendation = tv_signal.get('recommendation', 'NEUTRAL')
        tv_confidence = tv_signal.get('tv_confidence', 0)
        
        logger.info(f"TradingView: {tv_recommendation} ({tv_confidence:.1f}%)")
        
        # Step 2: Validate with 19 AI Modules
        logger.info("Step 2: Validating with 19 AI Modules...")
        ai_result = bridge.validate_with_ai_modules(tv_signal)
        
        if not ai_result:
            return {
                'status': 'error',
                'message': 'Failed AI validation'
            }
        
        final_recommendation = ai_result['final']['recommendation']
        final_confidence = ai_result['final']['confidence']
        
        logger.info(f"AI Modules: {ai_result['ai_modules']['direction']} ({ai_result['ai_modules']['score']:.1f}%)")
        logger.info(f"FINAL: {final_recommendation} ({final_confidence:.1f}%)")
        
        # Step 3: Check if signal matches
        signal_match = (
            (action == 'BUY' and 'BUY' in final_recommendation) or
            (action == 'SELL' and 'SELL' in final_recommendation)
        )
        
        # Step 4: Check confidence threshold
        MIN_CONFIDENCE = 75.0
        
        if not signal_match:
            logger.warning(f"Signal mismatch: TV={action}, AI={final_recommendation}")
            return {
                'status': 'rejected',
                'reason': 'signal_mismatch',
                'message': f'TradingView says {action} but AI says {final_recommendation}',
                'tradingview': {
                    'action': action,
                    'recommendation': tv_recommendation,
                    'confidence': tv_confidence
                },
                'ai_modules': {
                    'recommendation': final_recommendation,
                    'confidence': final_confidence
                }
            }
        
        if final_confidence < MIN_CONFIDENCE:
            logger.warning(f"Low confidence: {final_confidence:.1f}% < {MIN_CONFIDENCE}%")
            return {
                'status': 'rejected',
                'reason': 'low_confidence',
                'message': f'Confidence {final_confidence:.1f}% below threshold {MIN_CONFIDENCE}%',
                'final_confidence': final_confidence,
                'min_confidence': MIN_CONFIDENCE
            }
        
        # Step 5: Calculate SL/TP
        risk = ai_result['ai_modules']['risk']
        atr = risk.get('atr', 10)
        
        if action == 'BUY':
            sl = price - (atr * 2)
            tp1 = price + (atr * 2)
            tp2 = price + (atr * 3)
            tp3 = price + (atr * 4)
        else:  # SELL
            sl = price + (atr * 2)
            tp1 = price - (atr * 2)
            tp2 = price - (atr * 3)
            tp3 = price - (atr * 4)
        
        # Step 6: Execute order
        logger.info("Step 3: Executing order on MT5...")
        order_result = execute_order(
            symbol=symbol,
            action=action,
            price=price,
            sl=sl,
            tp=tp1,
            comment=comment,
            ai_result=ai_result
        )
        
        if order_result.get('success'):
            logger.info(f"ORDER EXECUTED: Ticket #{order_result.get('ticket')}")
        else:
            logger.error(f"ORDER FAILED: {order_result.get('message')}")
        
        return {
            'status': 'processed',
            'signal_matched': True,
            'confidence_passed': True,
            'tradingview': {
                'action': action,
                'recommendation': tv_recommendation,
                'confidence': tv_confidence,
                'price': price
            },
            'ai_modules': {
                'recommendation': final_recommendation,
                'confidence': final_confidence,
                'market_phase': ai_result['ai_modules']['market_phase'].get('phase', 'Unknown'),
                'smc_score': ai_result['ai_modules']['smc_score']['score']
            },
            'order': {
                'symbol': symbol,
                'action': action,
                'price': price,
                'sl': round(sl, 2),
                'tp1': round(tp1, 2),
                'tp2': round(tp2, 2),
                'tp3': round(tp3, 2),
                'atr': round(atr, 2)
            },
            'execution': order_result
        }
        
    except Exception as e:
        logger.error(f"Error in process_signal: {e}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'error',
            'message': str(e)
        }


def execute_order(symbol, action, price, sl, tp, comment, ai_result):
    """
    Execute order tren MT5
    
    Args:
        symbol: Trading symbol
        action: BUY or SELL
        price: Entry price
        sl: Stop loss
        tp: Take profit
        comment: Order comment
        ai_result: AI analysis result
        
    Returns:
        dict: Execution result
    """
    try:
        # Get symbol info
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {
                'success': False,
                'message': f'Symbol {symbol} not found'
            }
        
        # Calculate lot size (simple: 0.01 for now)
        # TODO: Use AI Money Manager for dynamic lot sizing
        lot = 0.01
        
        # ✅ YÊU CẦU 2: AI TỰ ĐỘNG TÍNH SL/TP THÔNG MINH
        # Lấy market data để tính SL/TP
        market_data = None
        try:
            if ai_result and 'ai_modules' in ai_result:
                atr_val = ai_result['ai_modules'].get('atr')
                market_data = {
                    'atr': atr_val,
                    'support_level': ai_result['ai_modules'].get('support'),
                    'resistance_level': ai_result['ai_modules'].get('resistance'),
                    'last_swing_high': ai_result['ai_modules'].get('swing_high'),
                    'last_swing_low': ai_result['ai_modules'].get('swing_low')
                }
        except:
            pass
        
        # Tính SL/TP thông minh bằng AI
        from core.money_management import AIMoneyManager
        money_manager = AIMoneyManager()
        
        signal_data = {
            'action': action,
            'entry_price': price,
            'price': price,
            'symbol': symbol
        }
        
        smart_sl_tp = money_manager.calculate_smart_sl_tp(signal_data, market_data)
        
        # Dùng SL/TP từ AI nếu có, nếu không dùng từ signal
        if smart_sl_tp['sl']:
            sl = smart_sl_tp['sl']
            logger.info(f"🤖 AI SL calculated: {sl:.2f} (Method: {smart_sl_tp['method']})")
        elif sl == 0 or sl is None:
            # Fallback: Tính SL default nếu AI fail
            point = symbol_info.point
            sl = price - (50 * 10 * point) if action == 'BUY' else price + (50 * 10 * point)
            logger.info(f"⚙️ Fallback SL calculated: {sl:.2f}")
        
        if smart_sl_tp['tp']:
            tp = smart_sl_tp['tp']
            logger.info(f"🤖 AI TP calculated: {tp:.2f} (R:R = 1:{smart_sl_tp.get('rr_ratio', 0):.2f})")
        elif tp == 0 or tp is None:
            # Fallback: Tính TP default
            point = symbol_info.point
            tp = price + (100 * 10 * point) if action == 'BUY' else price - (100 * 10 * point)
            logger.info(f"⚙️ Fallback TP calculated: {tp:.2f}")
        
        # Prepare request
        order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "sl": sl,  # ✅ SL từ AI
            "tp": tp,  # ✅ TP từ AI
            "deviation": 20,
            "magic": 234000,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        # Send order
        logger.info(f"📤 Sending order: {action} {lot} lot at {price}, SL={sl:.2f}, TP={tp:.2f}")
        }
        
        # Send order
        logger.info(f"Sending order: {action} {lot} lot at {price}, SL={sl}, TP={tp}")
        result = mt5.order_send(request)
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                'success': False,
                'message': f'Order failed: {result.comment}',
                'retcode': result.retcode
            }
        
        return {
            'success': True,
            'ticket': result.order,
            'volume': result.volume,
            'price': result.price,
            'message': 'Order executed successfully'
        }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Exception: {str(e)}'
        }


@app.route('/manual', methods=['POST'])
def manual_analysis():
    """
    Endpoint de phan tich thu cong (khong execute)
    """
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'GOLD')
        timeframe = data.get('timeframe', 'M15')
        
        if not bridge:
            return jsonify({'error': 'Bridge not initialized'}), 500
        
        logger.info(f"Manual analysis requested: {symbol} {timeframe}")
        
        # Get TradingView signal
        tv_signal = bridge.get_tradingview_signal(timeframe)
        if not tv_signal:
            return jsonify({'error': 'Failed to get TradingView data'}), 500
        
        # Validate with AI
        ai_result = bridge.validate_with_ai_modules(tv_signal)
        if not ai_result:
            return jsonify({'error': 'Failed AI validation'}), 500
        
        # Format response
        response = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'timeframe': timeframe,
            'tradingview': {
                'recommendation': tv_signal['recommendation'],
                'confidence': tv_signal['tv_confidence'],
                'price': tv_signal['indicators']['price'],
                'macd': tv_signal['indicators']['macd'],
                'rsi': tv_signal['indicators']['rsi']
            },
            'ai_modules': {
                'recommendation': ai_result['final']['recommendation'],
                'confidence': ai_result['final']['confidence'],
                'market_phase': ai_result['ai_modules']['market_phase'].get('phase'),
                'smc_score': f"{ai_result['ai_modules']['smc_score']['score']}/6",
                'macd_signal': ai_result['ai_modules']['macd']['signal'],
                'breaker_blocks': len(ai_result['ai_modules']['breaker_blocks'])
            },
            'risk': {
                'atr': ai_result['ai_modules']['risk']['atr'],
                'recommended_sl': ai_result['ai_modules']['risk']['recommended_sl'],
                'volatility': ai_result['ai_modules']['risk']['volatility']
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        logger.error(f"Error in manual analysis: {e}")
        return jsonify({'error': str(e)}), 500


def start_server(host='0.0.0.0', port=5000):
    """Start Flask server"""
    logger.info("="*70)
    logger.info("TRADINGVIEW WEBHOOK SERVER")
    logger.info("="*70)
    
    # Initialize bridge
    logger.info("Initializing TradingView AI Bridge...")
    if not init_bridge():
        logger.error("Failed to initialize bridge. Exiting.")
        return
    
    logger.info(f"Server starting on {host}:{port}")
    logger.info("Endpoints:")
    logger.info(f"  - POST /webhook        : Receive TradingView webhooks")
    logger.info(f"  - POST /manual         : Manual analysis (no execution)")
    logger.info(f"  - GET  /health         : Health check")
    logger.info("="*70)
    
    app.run(host=host, port=port, debug=False)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='TradingView Webhook Server')
    parser.add_argument('--host', default='0.0.0.0', help='Server host')
    parser.add_argument('--port', type=int, default=5000, help='Server port')
    
    args = parser.parse_args()
    
    start_server(host=args.host, port=args.port)
