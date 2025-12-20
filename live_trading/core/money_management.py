"""
Money Management Module
Automatic mode control and AI-based money management
"""

import logging
import psutil
import time
import math
import traceback
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Psutil availability check
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

# MT5 availability check
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("⚠️ MetaTrader5 not available - running in demo mode")

# Default minimum lot size
try:
    from config import config as lc
    DEFAULT_MIN_LOT = float(getattr(lc, 'MIN_LOT', 0.01))
except Exception:
    DEFAULT_MIN_LOT = 0.01

# Runtime mode helper
def get_runtime_mode():
    """Get current runtime mode from controller if available"""
    try:
        # Try to get from global controller if exists
        import sys
        for obj in sys.modules.values():
            if hasattr(obj, 'auto_controller'):
                return getattr(obj.auto_controller, 'current_mode', 'NORMAL')
        return 'NORMAL'
    except Exception:
        return 'NORMAL'


# ============================================
# AUTO SYSTEM MODE CONTROLLER (WINDOWS VPS)
# ============================================

class AutoModeController:
    def __init__(self):
        self.current_mode = "ULTRA"  # mặc định chạy mạnh nhất
        self.cpu_history = []

    def get_cpu(self):
        """Đo CPU theo Windows VPS mỗi 1 giây."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            self.cpu_history.append(cpu_percent)
            if len(self.cpu_history) > 10:
                self.cpu_history.pop(0)
            return cpu_percent
        except Exception:
            return 50  # fallback nếu psutil lỗi

    def decide_mode(self):
        cpu = self.get_cpu()

        # Use fixed thresholds (matching complete_ai_trading_system.py)
        high = 85.0
        medium = 75.0  # Đã tăng từ 45% lên 75% để bot vẫn giao dịch

        # SAFE MODE – CPU rất cao
        if cpu >= high:
            self.current_mode = "SAFE"
        # SUPERLIGHT MODE – CPU tầm trung
        elif medium <= cpu < high:
            self.current_mode = "SUPERLIGHT"
        # ULTRA MODE – CPU thấp
        else:
            self.current_mode = "ULTRA"

        return self.current_mode


# NOTE: RiskAIPro merged into RiskAI below as `evaluate(...)` for a single unified risk
# decisioning class. The separate RiskAIPro class was removed to avoid duplication.

#==============================================================================
# 3. 💰 AI MONEY MANAGER - QUẢN LÝ VỐN THÔNG MINH
#==============================================================================

class AIMoneyManager:
    """AI-powered Money Management System
    
    Chức năng:
    - Tính lot size động dựa trên risk % và balance
    - Quản lý nhiều lệnh đồng thời (max open positions)
    - Cắt lỗ thông minh: Giữ lệnh lời, cắt lệnh lỗ
    - Tính toán risk/reward ratio
    - Điều chỉnh position size theo win rate
    """
    
    def __init__(self, 
                 initial_balance=10000.0,
                 risk_per_trade=0.02,      # 2% risk mỗi lệnh
                 max_risk_total=0.10,       # 10% max risk toàn bộ
                 max_open_positions=999,    # UNLIMITED - AI quyết định
                 min_risk_reward=1.5,       # Minimum R:R ratio
                 adaptive_sizing=True,      # Điều chỉnh lot theo win rate
                 min_profit_percent=0.20,   # 🎯 Tối thiểu 20% tài khoản PHẢI lời
                 min_profit_amount=10.0,    # 🎯 Tối thiểu $10 PHẢI lời
                 small_account_threshold=200.0,   # 🛡️ Ngưỡng tài khoản nhỏ
                 small_account_max_positions=3):  # 🛡️ Max 3 lệnh cho TK nhỏ
        
        # 🔄 LẤY BALANCE THẬT TỪ MT5 NẾU CÓ
        if MT5_AVAILABLE:
            try:
                account_info = mt5.account_info()
                if account_info:
                    real_balance = account_info.balance
                    logger.info(f"💰 Đã lấy balance thật từ MT5: ${real_balance:,.2f}")
                    initial_balance = real_balance
                else:
                    logger.warning(f"⚠️ MT5 account_info() trả về None")
            except Exception as e:
                logger.warning(f"⚠️ Không lấy được balance từ MT5, dùng mặc định: {e}")
        
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.peak_balance = initial_balance  # Peak bằng balance thật lúc khởi động
        self.risk_per_trade = risk_per_trade
        self.max_risk_total = max_risk_total
        self.max_open_positions = max_open_positions
        self.min_risk_reward = min_risk_reward
        self.adaptive_sizing = adaptive_sizing
        
        # 🛡️ SMALL ACCOUNT PROTECTION
        self.small_account_threshold = small_account_threshold
        self.small_account_max_positions = small_account_max_positions
        self.last_balance_check = None
        self.balance_scan_interval = 30  # Quét balance mỗi 30 giây
        
        # 🎯 PROFIT TARGET PROTECTION
        self.min_profit_percent = min_profit_percent
        self.min_profit_amount = min_profit_amount
        self.profit_target = max(initial_balance * min_profit_percent, min_profit_amount)
        self.profit_locked = False  # Đã đạt target chưa
        self.peak_balance = initial_balance  # Balance cao nhất đạt được
        
        # 💰 PARTIAL TAKE PROFIT - Chốt lời một phần
        self.partial_take_profit_levels = [
            {'profit': 5.0, 'close_percent': 0.25},   # Chốt 25% khi lời $5
            {'profit': 10.0, 'close_percent': 0.30},  # Chốt thêm 30% khi lời $10
            {'profit': 20.0, 'close_percent': 0.45},  # Chốt thêm 45% khi lời $20
        ]  # Có thể customize qua parameter
        
        # Trading history
        self.trade_history = []
        self.open_positions = []
        
        # Callback invoked when a position is closed: callable(pos_dict)
        self.on_position_closed = None

        # MT5 Integration
        self.mt5_enabled = False
        self.last_sync_time = None
        self.win_count = 0
        self.loss_count = 0
        
        # ✅ YÊU CẦU 1: BỎ CHỨC NĂNG CẮT LỖ CỨNG - CHỈ CẮT KHI CÓ TÍN HIỆU ĐẢO CHIỀU
        self.enable_hard_stop_loss = False  # Tắt SL cứng
        self.enable_reversal_stop_only = True  # Chỉ cắt lỗ khi có reversal signal mạnh
        self.min_reversal_confidence = 75.0  # Confidence tối thiểu để cắt lỗ
        logger.info("🛡️ STOP LOSS MODE: CHỈ CẮT LỖ KHI CÓ TÍN HIỆU ĐẢO CHIỀU")
        
        # ✅ YÊU CẦU 2: AI TỰ ĐỘNG TÍNH SL/TP THÔNG MINH
        self.auto_set_tp_sl_on_mt5 = True  # Tự động đặt TP/SL trên MT5
        self.use_ai_smart_sl_tp = True  # Dùng AI để tính SL/TP (ATR + Support/Resistance)
        logger.info("🤖 AI SMART SL/TP: Dựa trên ATR + Support/Resistance + Volatility")
        
        logger.info("💰 AI Money Manager initialized")
        logger.info(f"   Balance: ${initial_balance:,.2f}")
        logger.info(f"   Risk per trade: {risk_per_trade*100:.1f}%")
        logger.info(f"   Max total risk: {max_risk_total*100:.1f}%")
        logger.info(f"   Max open positions: UNLIMITED (AI quyết định)")
        logger.info(f"   Min R:R ratio: {min_risk_reward:.1f}:1")
        logger.info(f"   Adaptive sizing: {'ON' if adaptive_sizing else 'OFF'}")
        logger.info(f"   🎯 Profit Target: ${self.profit_target:.2f} ({min_profit_percent*100:.0f}% hoặc ${min_profit_amount})")
        logger.info(f"   🛡️ SMALL ACCOUNT PROTECTION: Balance < ${small_account_threshold:.0f} → Max {small_account_max_positions} lệnh")
    
    def scan_balance_from_mt5(self):
        """🔍 QUÉT BALANCE TỪ MT5 LIÊN TỤC
        
        Cập nhật balance real-time từ MT5 và điều chỉnh strategy cho tài khoản nhỏ
        """
        if not MT5_AVAILABLE:
            return False
        
        # Kiểm tra interval (không quét quá thường xuyên)
        current_time = time.time()
        if self.last_balance_check and (current_time - self.last_balance_check) < self.balance_scan_interval:
            return False
        
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.warning("⚠️ Không thể lấy thông tin tài khoản từ MT5")
                return False
            
            new_balance = account_info.balance
            old_balance = self.current_balance
            
            # Cập nhật balance
            self.current_balance = new_balance
            self.last_balance_check = current_time
            
            # Kiểm tra balance thay đổi đáng kể
            balance_change = new_balance - old_balance
            if abs(balance_change) > 0.01:  # Thay đổi > $0.01
                logger.info(f"💰 Balance updated: ${old_balance:.2f} → ${new_balance:.2f} ({balance_change:+.2f})")
            
            # 🛡️ KIỂM TRA TÀI KHOẢN NHỎ
            if new_balance < self.small_account_threshold:
                current_positions = len(self.open_positions)
                logger.warning("="*80)
                logger.warning(f"🛡️ TÀI KHOẢN NHỎ PHÁT HIỆN!")
                logger.warning(f"   Balance: ${new_balance:.2f} < ${self.small_account_threshold:.0f}")
                logger.warning(f"   Lệnh đang mở: {current_positions}/{self.small_account_max_positions}")
                logger.warning(f"   CHẾ ĐỘ BẢO VỆ: Giới hạn tối đa {self.small_account_max_positions} lệnh")
                logger.warning(f"   ⚠️ Chống cháy tài khoản - Giảm risk!")
                logger.warning("="*80)
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi quét balance từ MT5: {e}")
            return False
    
    def sync_positions_from_mt5(self):
        """🔄 Đồng bộ positions từ MT5 vào bot
        
        Đọc tất cả positions đang mở trên MT5 và đồng bộ vào self.open_positions
        để bot biết và quản lý được
        """
        if not MT5_AVAILABLE:
            return False
        
        try:
            # Khởi tạo MT5 nếu chưa
            if not mt5.initialize():
                return False
            
            # Lấy tất cả positions đang mở
            positions = mt5.positions_get()
            if positions is None:
                return False
            
            # Clear positions cũ
            self.open_positions = []
            
            # Đồng bộ positions
            for pos in positions:
                # Chỉ lấy positions của symbol GOLD/XAUUSD (bao gồm nhiều biến thể broker)
                if pos.symbol not in [
                    "XAUUSD", "GOLD", "XAUUSDm", "XAUUSD-VIPc", "XAUUSDVIPc",
                    "XAUUSC", "XAUUSC-VIPc", "XAUUSC.VIPC", "XAUUSC.VIPc", "XAUUSDC"
                ]:
                    continue
                
                # Tạo position object
                position = {
                    'signal_id': pos.ticket,  # Dùng ticket làm ID
                    'action': 'BUY' if pos.type == 0 else 'SELL',
                    'entry_price': pos.price_open,
                    'sl_price': pos.sl if pos.sl > 0 else None,
                    'tp_price': pos.tp if pos.tp > 0 else None,
                    'lot_size': pos.volume,
                    'entry_time': datetime.fromtimestamp(pos.time),
                    'risk_amount': 0.0,  # Tính sau
                    'current_price': pos.price_current,
                    'profit': pos.profit,
                    'mt5_ticket': pos.ticket,
                    'mt5_synced': True
                }
                
                self.open_positions.append(position)
            
            self.last_sync_time = datetime.now()
            self.mt5_enabled = True
            
            # 💰 CẬP NHẬT BALANCE THẬT TỪ MT5
            account_info = mt5.account_info()
            if account_info:
                self.current_balance = account_info.balance
                # Cập nhật peak nếu cao hơn
                if self.current_balance > self.peak_balance:
                    self.peak_balance = self.current_balance
            
            if len(self.open_positions) > 0:
                logger.info(f"🔄 Đã đồng bộ {len(self.open_positions)} positions từ MT5")
                logger.info(f"💰 Balance thật: ${self.current_balance:,.2f} (Peak: ${self.peak_balance:,.2f})")
                for pos in self.open_positions:
                    # Skip invalid position data
                    if not isinstance(pos, dict):
                        logger.warning(f"⚠️ Skipping invalid position data in sync_positions_from_mt5: {pos} (type: {type(pos)})")
                        continue
                    logger.info(f"   #{pos['signal_id']}: {pos['action']} @ {pos['entry_price']:.2f} | P/L: ${pos['profit']:.2f}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi đồng bộ MT5: {e}")
            return False
    
    def close_position_on_mt5(self, ticket, reason='AI_CLOSE'):
        """Đóng position trực tiếp trên MT5
        
        Args:
            ticket: MT5 ticket number
            reason: Lý do đóng lệnh
        """
        if not MT5_AVAILABLE or not self.mt5_enabled:
            return False
        
        try:
            # Lấy thông tin position
            position = mt5.positions_get(ticket=ticket)
            if position is None or len(position) == 0:
                logger.warning(f"⚠️ Không tìm thấy position #{ticket} trên MT5")
                return False
            
            pos = position[0]
            
            # Đóng lệnh
            # 🔧 FIX: MT5 comment max 31 chars
            safe_reason = reason[:22] if len(reason) > 22 else reason
            comment = f"AI_Close_{safe_reason}"[:31]
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "price": mt5.symbol_info_tick(pos.symbol).ask if pos.type == 1 else mt5.symbol_info_tick(pos.symbol).bid,
                "deviation": 20,
                "magic": 234000,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Use safe wrapper to avoid None dereference and centralize retries/logging
            result = self._safe_order_send(request)

            if result is None:
                logger.error(f"❌ MT5 order_send returned None when closing position #{ticket}")
                return False

            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Đã đóng position #{ticket} trên MT5 | Lý do: {reason} | P/L: ${pos.profit:.2f}")
                return True
            else:
                logger.error(f"❌ Lỗi đóng position #{ticket}: {getattr(result, 'comment', 'no comment')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception khi đóng MT5 position: {e}")
            return False
    
    def close_partial_position_on_mt5(self, ticket, close_volume, reason='PARTIAL_TAKE_PROFIT'):
        """Đóng một phần position trên MT5
        
        Args:
            ticket: MT5 ticket number
            close_volume: Khối lượng cần đóng (ví dụ: 0.5 để đóng 0.5 lot)
            reason: Lý do đóng lệnh
        
        Returns:
            bool: Thành công hay không
        """
        if not MT5_AVAILABLE or not self.mt5_enabled:
            return False
        
        try:
            # Lấy thông tin position
            position = mt5.positions_get(ticket=ticket)
            if position is None or len(position) == 0:
                logger.warning(f"⚠️ Không tìm thấy position #{ticket} trên MT5")
                return False

            pos = position[0]

            # Debug: Log position info
            logger.debug(f"📊 Position #{ticket}: Symbol={pos.symbol}, Type={pos.type}, Volume={pos.volume}, Price={pos.price_open}")

            # Kiểm tra volume hợp lệ
            if close_volume >= pos.volume:
                logger.warning(f"⚠️ Close volume {close_volume} >= position volume {pos.volume}, dùng close_position_on_mt5 thay thế")
                return self.close_position_on_mt5(ticket, reason)

            if close_volume <= 0:
                logger.warning(f"⚠️ Close volume {close_volume} không hợp lệ")
                return False

            # Kiểm tra symbol info
            symbol_info = mt5.symbol_info(pos.symbol)
            if symbol_info is None:
                logger.error(f"❌ Không tìm thấy symbol info cho {pos.symbol}")
                return False

            # Debug: Log symbol info
            logger.debug(f"📊 Symbol {pos.symbol}: Bid={symbol_info.bid}, Ask={symbol_info.ask}, Spread={symbol_info.spread}")

            # 🔧 LÀM TRÒN VOLUME THEO VOLUME_STEP ĐỂ TRÁNH LỖI "Invalid volume"
            if symbol_info.volume_step > 0:
                # Tính số bội số gần nhất của volume_step
                import math
                valid_close_volume = math.floor(close_volume / symbol_info.volume_step) * symbol_info.volume_step
                
                # Đảm bảo không vượt quá volume hiện tại và volume min
                valid_close_volume = max(symbol_info.volume_min, min(valid_close_volume, pos.volume))
                
                if valid_close_volume != close_volume:
                    logger.info(f"🔧 Adjusted close volume: {close_volume:.4f} → {valid_close_volume:.4f} (step: {symbol_info.volume_step})")
                    close_volume = valid_close_volume
            
            # Kiểm tra lại sau khi làm tròn
            if close_volume < symbol_info.volume_min:
                logger.warning(f"⚠️ Close volume {close_volume} < min {symbol_info.volume_min}, bỏ qua")
                return False
            
            # 🛡️ KIỂM TRA VOLUME MIN CHO PARTIAL CLOSE - MT5 có thể từ chối volume quá nhỏ
            min_partial_volume = max(symbol_info.volume_min, 0.1)  # Tối thiểu 0.1 lots cho partial close
            if close_volume < min_partial_volume:
                logger.warning(f"⚠️ Close volume {close_volume} < min partial {min_partial_volume}, tăng lên {min_partial_volume}")
                close_volume = min_partial_volume
                # Đảm bảo không vượt quá volume hiện tại
                close_volume = min(close_volume, pos.volume)
            
            # Debug: Log symbol info
            logger.debug(f"📊 Symbol {pos.symbol}: Bid={symbol_info.bid}, Ask={symbol_info.ask}, Spread={symbol_info.spread}")

            # Đóng một phần lệnh
            # 🔧 FIX: MT5 comment max 31 chars, truncate reason
            safe_reason = reason[:20] if len(reason) > 20 else reason
            comment = f"AI_{safe_reason}"[:31]  # Max 31 chars for MT5
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": pos.symbol,
                "volume": close_volume,
                "type": mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                "position": ticket,
                "price": mt5.symbol_info_tick(pos.symbol).ask if pos.type == 1 else mt5.symbol_info_tick(pos.symbol).bid,
                "deviation": 20,
                "magic": 234000,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            # Use safe wrapper to handle retries and detailed logging
            max_retries = 3
            result = self._safe_order_send(request, max_retries=max_retries, retry_delay=0.5)

            if result is None:
                logger.error(f"❌ MT5 order_send returned None for partial close #{ticket} after {max_retries} attempts")
                return False
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                # Tính P/L cho phần đóng
                partial_pnl = (result.price - pos.price_open) * close_volume * 100
                if pos.type == 1:  # SELL position
                    partial_pnl = (pos.price_open - result.price) * close_volume * 100
                
                logger.info(f"✅ PARTIAL CLOSE #{ticket} - Đóng {close_volume:.2f} lots | P/L: ${partial_pnl:.2f} ({reason})")
                return True
            else:
                logger.error(f"❌ Lỗi partial close position #{ticket}: {result.comment}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Exception khi partial close MT5 position: {e}")
            return False
    
    def get_effective_max_positions(self):
        """🛡️ TÍNH MAX POSITIONS ĐỘNG THEO BALANCE
        
        - Balance < $200 → Max 3 lệnh (CHỐNG CHÁY TK NHỎ)
        - $200 - $3,999 → Max 10 lệnh
        - $4,000 - $7,999 → Max 20 lệnh
        - $8,000 - $14,999 → Max 30 lệnh
        - $15,000 - $29,999 → Max 35 lệnh
        - $30,000+ → Max 40 lệnh
        
        Returns:
            int: Số lệnh tối đa cho phép
        """
        balance = self.current_balance
        if balance < self.small_account_threshold:
            return self.small_account_max_positions
        elif balance < 4000:
            return 10
        elif balance < 8000:
            return 20
        elif balance < 15000:
            return 30
        elif balance < 30000:
            return 35
        else:
            return 40
    
    def calculate_lot_size(self, entry_price, sl_price, confidence=0.5):
        """Tính lot size thông minh dựa trên risk và confidence
        
        Args:
            entry_price: Giá vào lệnh
            sl_price: Giá stop loss
            confidence: Độ tin cậy AI (0.0 - 1.0)
        
        Returns:
            float: Lot size tối ưu
        """
        # 🛡️ SMALL ACCOUNT PROTECTION: Giảm risk cho tài khoản nhỏ
        effective_risk = self.risk_per_trade
        if self.current_balance < self.small_account_threshold:
            effective_risk = self.risk_per_trade * 0.5  # Giảm 50% risk cho TK nhỏ
            logger.info(f"🛡️ Small Account: Risk giảm từ {self.risk_per_trade*100:.1f}% → {effective_risk*100:.1f}%")
        
        # 1. Tính risk amount cơ bản
        base_risk_amount = self.current_balance * effective_risk
        
        # 2. Điều chỉnh theo confidence (cao hơn → size lớn hơn)
        if confidence >= 0.8:
            risk_multiplier = 1.5  # Tin cậy cao → tăng 50%
        elif confidence >= 0.7:
            risk_multiplier = 1.2  # Tin cậy trung bình cao → tăng 20%
        elif confidence >= 0.6:
            risk_multiplier = 1.0  # Tin cậy trung bình → giữ nguyên
        else:
            risk_multiplier = 0.7  # Tin cậy thấp → giảm 30%
        
        adjusted_risk = base_risk_amount * risk_multiplier
        
        # 3. Điều chỉnh theo win rate (nếu bật adaptive sizing)
        if self.adaptive_sizing and len(self.trade_history) >= 10:
            win_rate = self.get_win_rate()
            
            if win_rate >= 0.6:
                win_multiplier = 1.3  # Win rate cao → tăng size
            elif win_rate >= 0.5:
                win_multiplier = 1.0  # Win rate ổn định
            elif win_rate >= 0.4:
                win_multiplier = 0.8  # Win rate thấp → giảm size
            else:
                win_multiplier = 0.5  # Win rate rất thấp → giảm mạnh
            
            adjusted_risk *= win_multiplier
            logger.debug(f"   Win rate: {win_rate*100:.1f}% → Multiplier: {win_multiplier:.1f}x")
        
        # 4. Tính lot size từ risk và khoảng cách SL
        price_diff = abs(entry_price - sl_price)
        
        if price_diff == 0:
            logger.warning("⚠️ SL = Entry price, using minimum lot")
            return float(getattr(self, 'min_lot', DEFAULT_MIN_LOT))
        
        # Lot size = Risk Amount / (Price Distance × Contract Size)
        # Với XAUUSD: 1 lot = 100 oz, pip value ≈ $10/pip
        lot_size = adjusted_risk / (price_diff * 100)
        
        # 5. Giới hạn lot size (respect instance min_lot and live_lot_cap safety)
        try:
            cap = float(getattr(self, 'live_lot_cap', 10.0) or 10.0)
        except Exception:
            cap = 10.0
        min_lot = float(getattr(self, 'min_lot', DEFAULT_MIN_LOT))
        lot_size = max(min_lot, min(lot_size, cap))
        
        # 6. Làm tròn đến 0.01
        lot_size = round(lot_size, 2)
        
        logger.info(f"💰 TÍNH TOÁN KHỐI LƯỢNG LỆNH:")
        logger.info(f"   Balance: ${self.current_balance:,.2f}")
        logger.info(f"   Base risk: ${base_risk_amount:.2f} ({self.risk_per_trade*100:.1f}%)")
        logger.info(f"   Confidence: {confidence*100:.1f}% → Multiplier: {risk_multiplier:.1f}x")
        logger.info(f"   Adjusted risk: ${adjusted_risk:.2f}")
        logger.info(f"   Price distance: {price_diff:.2f}")
        logger.info(f"   → LOT SIZE: {lot_size:.2f}")
        
        return lot_size
    
    def check_profit_target(self):
        """🎯 KIỂM TRA MỤC TIÊU LỢI NHUẬN
        
        Trả về:
        - achieved: Đã đạt target chưa
        - current_profit: Lợi nhuận hiện tại
        - protection_mode: Chế độ bảo vệ (NONE, CONSERVATIVE, SOFT, HARD)
        """
        current_profit = self.current_balance - self.initial_balance
        
        # Cập nhật peak balance
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
        
        # Kiểm tra đạt target
        if current_profit >= self.profit_target and not self.profit_locked:
            self.profit_locked = True
            logger.info(f"🎯 PROFIT TARGET ACHIEVED! ${current_profit:.2f} >= ${self.profit_target:.2f}")
            logger.info(f"   🛡️ Entering PROTECTION MODE - Bảo vệ lợi nhuận")
        
        # Xác định chế độ bảo vệ
        if self.profit_locked:
            # Đã đạt target → Bảo vệ
            drawdown_from_peak = (self.peak_balance - self.current_balance)
            
            if drawdown_from_peak >= self.profit_target * 0.5:
                # Mất > 50% profit → HARD protection (stop trading)
                return True, current_profit, "HARD"
            elif drawdown_from_peak >= self.profit_target * 0.3:
                # Mất > 30% profit → SOFT protection (reduce risk)
                return True, current_profit, "SOFT"
            else:
                # Còn giữ được lợi nhuận → Tiếp tục nhưng thận trọng
                return True, current_profit, "CONSERVATIVE"
        
        return False, current_profit, "NONE"
    
    def apply_partial_take_profit(self, current_prices, market_data=None):
        """💰 ÁP DỤNG PARTIAL TAKE PROFIT THÔNG MINH - Chốt lời một phần dựa trên AI phân tích
        
        ⚠️ CHỨC NĂNG ĐÃ TẮT - Theo yêu cầu user (Dec 16, 2025)
        
        Lý do tắt:
        - User muốn KHÔNG tự động chốt lời một phần
        - Giữ lệnh đến khi hit TP/SL gốc
        - Tránh bot đóng lệnh quá sớm, để lời chạy tối đa
        
        Logic AI cũ:
        - Phân tích điều kiện thị trường (trend, volatility, volume)
        - Khi có dấu hiệu GIẢM NHẸ: Giữ lệnh để lời cao nhất
        - Khi có dấu hiệu GIẢM MẠNH/QUÉT THANH KHOẢN: Chốt lời một phần
        - Đảm bảo tài khoản luôn lời nhiều hơn lỗ
        
        Args:
            current_prices: dict với keys 'BUY' và 'SELL' là giá hiện tại
            market_data: dict chứa dữ liệu thị trường (trend, volume, volatility, etc.)
        
        Returns:
            list: Empty (disabled)
        """
        # 🔴 DISABLED - Return immediately without partial closing
        logger.debug("🔴 PARTIAL_TP: DISABLED by user request - No auto partial take profit")
        return []
        
        # ===== CODE BELOW IS DISABLED =====
        if not self.open_positions:
            logger.debug("💰 PARTIAL TP: No open positions")
            return []
        
        logger.debug(f"💰 PARTIAL TP: Checking {len(self.open_positions)} positions")
        partial_closed = []
        
        # 🧠 AI PHÂN TÍCH ĐIỀU KIỆN THỊ TRƯỜNG
        market_analysis = self._analyze_market_conditions(current_prices, market_data)
        
        logger.debug(f"💰 PARTIAL TP: Market data received: {market_data is not None}")
        logger.debug(f"💰 PARTIAL TP: Market analysis result: {market_analysis}")
        
        for i, pos in enumerate(self.open_positions):
            # Skip invalid position data
            if not isinstance(pos, dict):
                logger.warning(f"⚠️ Skipping invalid position data in apply_partial_take_profit: {pos} (type: {type(pos)})")
                continue
                
            # Tính P/L hiện tại
            if 'BUY' in pos['action']:
                current_price = current_prices.get('BUY', pos['entry_price'])
                current_pnl = (current_price - pos['entry_price']) * pos['lot_size'] * 100
            else:  # SELL
                current_price = current_prices.get('SELL', pos['entry_price'])
                current_pnl = (pos['entry_price'] - current_price) * pos['lot_size'] * 100
            
            logger.debug(f"💰 PARTIAL TP: Position #{pos['signal_id']} {pos['action']} - PNL: ${current_pnl:.2f}")
            
            # 🧠 AI QUYẾT ĐỊNH CHỐT LỜI
            should_partial_close, close_reason, close_percentage = self._ai_decide_partial_take_profit(
                pos, current_pnl, market_analysis
            )
            
            logger.debug(f"💰 PARTIAL TP: Decision for #{pos['signal_id']}: {should_partial_close} ({close_reason}, {close_percentage*100:.0f}%)")
            
            if not should_partial_close:
                continue
            
            # Tính volume cần đóng
            close_volume = pos['lot_size'] * close_percentage
            
            # Đảm bảo không đóng quá volume hiện tại
            close_volume = min(close_volume, pos['lot_size'])
            
            # 🛡️ TRÁNH ĐÓNG VOLUME QUÁ NHỎ - MT5 có thể từ chối
            if close_volume < 0.05:
                logger.debug(f"⚠️ Close volume {close_volume:.4f} < 0.05, bỏ qua partial close để tránh lỗi MT5")
                continue
            
            if close_volume <= 0:
                continue
            
            # Đóng partial trên MT5
            mt5_ticket = pos.get('mt5_ticket')
            if mt5_ticket:
                success = self.close_partial_position_on_mt5(
                    mt5_ticket, 
                    close_volume, 
                    reason=f'AI_PARTIAL_TP_{close_reason}'
                )
                
                if success:
                    # Cập nhật position trong list
                    pos['lot_size'] -= close_volume
                    profit_threshold = current_pnl  # Sử dụng P/L hiện tại làm threshold
                    pos[f'partial_closed_{profit_threshold}'] = True
                    
                    # Tính P/L cho phần đóng
                    partial_pnl = current_pnl * close_percentage
                    self.current_balance += partial_pnl
                    
                    logger.info(f"🧠 AI PARTIAL TAKE PROFIT #{pos['signal_id']} - {close_reason}")
                    logger.info(f"   Đóng {close_percentage*100:.0f}% ({close_volume:.2f} lots) | P/L: ${partial_pnl:.2f}")
                    logger.info(f"   Còn {pos['lot_size']:.2f} lots | Balance: ${self.current_balance:,.2f}")
                    
                    partial_closed.append({
                        'signal_id': pos['signal_id'],
                        'close_reason': close_reason,
                        'close_percentage': close_percentage,
                        'close_volume': close_volume,
                        'partial_pnl': partial_pnl
                    })
                    
                    # Nếu đóng hết, xóa khỏi list
                    try:
                        min_lot = float(getattr(self, 'min_lot', DEFAULT_MIN_LOT))
                    except Exception:
                        min_lot = DEFAULT_MIN_LOT
                    if pos['lot_size'] <= min_lot:
                        self.open_positions.pop(i)
                        logger.info(f"   → Đã đóng hết lệnh #{pos['signal_id']}")
                        break
                else:
                    logger.warning(f"⚠️ Partial close thất bại cho #{pos['signal_id']}")
        
        if partial_closed:
            logger.info(f"✅ AI đã áp dụng partial take profit cho {len(partial_closed)} lệnh")
        
        return partial_closed

    def ai_close_losing_positions(self, ms_signal, current_prices, market_analysis=None,
                                  protect_capital_pct=0.65, target_win_rate=0.65):
        """AI-driven closing of losing positions based on MarketStructureAI and market analysis.
        
        ⚠️ CHỨC NĂNG ĐÃ TẮT - Theo yêu cầu user (Dec 12, 2025)
        
        Lý do tắt:
        - User muốn bot KHÔNG tự động cắt lỗ
        - Chỉ để AI OPEN lệnh, user tự quản lý CLOSE
        - Tránh bot đóng lệnh quá sớm khi chưa có đảo chiều thực sự

        Args:
            ms_signal: -1 (bearish), 0 (neutral), 1 (bullish)
            current_prices: dict with 'BUY'/'SELL'
            market_analysis: optional dict from _analyze_market_conditions
            protect_capital_pct: fraction of profit to keep (not used rigidly, heuristic)
            target_win_rate: desired win rate (used to be more/less aggressive)

        Returns:
            list: Empty (disabled)
        """
        # 🔴 DISABLED - Return immediately without closing positions
        logger.debug("🔴 AI_CLOSE_LOSING: DISABLED by user request - No auto stop loss")
        return []
        
        # ===== CODE BELOW IS DISABLED =====
        if not self.open_positions:
            return []

        closed = []

        # Basic market signal: only aggressively cut losses when market is bearish
        bearish_market = (ms_signal == -1)

        # Fallback market analysis
        if market_analysis is None:
            market_analysis = {'momentum_shift': 'NEUTRAL', 'risk_level': 'MEDIUM'}

        # Aggressive mode if current win rate is below target
        current_wr = self.get_win_rate()
        aggressive = current_wr < target_win_rate

        logger.info(f"🧠 AI_CLOSE: MarketSignal={ms_signal}, WinRate={current_wr:.2%}, Aggressive={aggressive}")

        # Build list of losing positions sorted by loss severity (largest loss first)
        losers = []
        for pos in self.open_positions:
            # Skip invalid position data
            if not isinstance(pos, dict):
                logger.warning(f"⚠️ Skipping invalid position data in ai_close_losing_positions: {pos} (type: {type(pos)})")
                continue
                
            if 'BUY' in pos['action']:
                cur_price = current_prices.get('BUY', pos['entry_price'])
                pnl = (cur_price - pos['entry_price']) * pos['lot_size'] * 100
            else:
                cur_price = current_prices.get('SELL', pos['entry_price'])
                pnl = (pos['entry_price'] - cur_price) * pos['lot_size'] * 100
            
            if pnl < 0:
                # compute loss percent relative to entry for sorting
                loss_pct = abs(pnl) / max(1.0, (pos['entry_price'] * pos['lot_size'] * 100))
                losers.append((pos, pnl, loss_pct))
        if not losers:
            logger.debug("🧠 AI_CLOSE: No losing positions to consider")
            return []

        # Sort by absolute loss descending
        losers.sort(key=lambda x: x[1])  # most negative first

        # Decision thresholds (heuristic)
        abs_loss_threshold = max(5.0, 0.001 * self.current_balance)  # at least $5 or relative
        loss_pct_threshold = 0.5 if not aggressive else 0.35  # % of SL or relative measure

        # If market bearish, close more; if neutral, be conservative
        for pos, pnl, loss_pct in losers:
            ticket = pos.get('signal_id')

            # If market bearish, consider closing even moderate losses
            should_close = False
            reason = None

            # Close if large absolute loss
            if abs(pnl) >= abs_loss_threshold:
                should_close = True
                reason = f"AI_CLOSE_ABS_LOSS_{abs_loss_threshold:.2f}"

            # Close if loss_pct large (relative)
            if loss_pct >= loss_pct_threshold:
                should_close = True
                reason = f"AI_CLOSE_PCT_LOSS_{loss_pct_threshold:.2f}"

            # If market is bearish and momentum indicates bearish, be more aggressive
            ms_momentum = market_analysis.get('momentum_shift', 'NEUTRAL')
            if bearish_market and (ms_momentum == 'BEARISH' or market_analysis.get('volume_surge', False)):
                # lower thresholds when bearish
                if abs(pnl) >= max(3.0, 0.0005 * self.current_balance):
                    should_close = True
                    if reason is None:
                        reason = "AI_CLOSE_BEARISH_MARKET"

            # Respect minimum profit protection: if closing would reduce profit protection too much, skip
            # (heuristic: keep at least protect_capital_pct of current available profit)
            # Compute total pnl across positions
            total_pnl = sum(((current_prices.get('BUY', p['entry_price']) - p['entry_price']) * p['lot_size'] * 100) if 'BUY' in p['action'] else ((p['entry_price'] - current_prices.get('SELL', p['entry_price'])) * p['lot_size'] * 100) for p in self.open_positions)

            if should_close:
                # Extra guard: don't trim into deeper drawdown (only close when overall pnl positive or market bearish)
                if total_pnl <= 0 and not bearish_market:
                    logger.debug(f"🧠 AI_CLOSE: Skipping close of #{ticket} because total PnL={total_pnl:.2f} and market not bearish")
                    continue

                # Attempt close
                logger.info(f"🧠 AI_CLOSE: Closing losing pos #{ticket} | PnL=${pnl:.2f} | Reason={reason}")
                closed_pnl = self.close_position(ticket, current_prices.get('BUY' if 'BUY' in pos['action'] else 'SELL', pos['entry_price']), reason=f"AI_MARKET_DECLINE_{reason}")
                if closed_pnl is not None:
                    closed.append(ticket)

                    # Recompute total_pnl and stop if we've preserved enough profit
                    total_pnl = sum(((current_prices.get('BUY', p['entry_price']) - p['entry_price']) * p['lot_size'] * 100) if 'BUY' in p['action'] else ((p['entry_price'] - current_prices.get('SELL', p['entry_price'])) * p['lot_size'] * 100) for p in self.open_positions)
                    if total_pnl >= 0 and (not aggressive):
                        # conservative: stop after covering negatives
                        break

        if closed:
            logger.info(f"🧠 AI_CLOSE: Closed {len(closed)} losing positions: {closed}")

        return closed
    
    def _analyze_market_conditions(self, current_prices, market_data=None):
        """🧠 PHÂN TÍCH ĐIỀU KIỆN THỊ TRƯỜNG CHO AI DECISION
        
        Phân tích:
        - Trend strength: Sức mạnh xu hướng
        - Volatility: Mức độ biến động
        - Volume: Khối lượng giao dịch
        - Momentum: Động lượng giá
        
        Returns:
            dict: Phân tích điều kiện thị trường
        """
        analysis = {
            'trend_strength': 0.5,      # 0-1: Sức mạnh xu hướng
            'volatility_level': 'MEDIUM', # LOW/MEDIUM/HIGH/EXTREME
            'volume_surge': False,       # Có quét thanh khoản không
            'momentum_shift': 'NEUTRAL', # BULLISH/BEARISH/NEUTRAL
            'risk_level': 'MEDIUM'       # LOW/MEDIUM/HIGH
        }
        
        try:
            if market_data:
                # Trend analysis
                trend_indicators = market_data.get('trend', {})
                analysis['trend_strength'] = min(1.0, max(0.0, trend_indicators.get('strength', 0.5)))
                
                # Volatility analysis
                volatility = market_data.get('volatility', {})
                vol_level = volatility.get('level', 0.5)
                if vol_level < 0.3:
                    analysis['volatility_level'] = 'LOW'
                elif vol_level < 0.7:
                    analysis['volatility_level'] = 'MEDIUM'
                elif vol_level < 0.9:
                    analysis['volatility_level'] = 'HIGH'
                else:
                    analysis['volatility_level'] = 'EXTREME'
                
                # Volume surge detection (quét thanh khoản)
                volume_data = market_data.get('volume', {})
                current_volume = volume_data.get('current', 0)
                avg_volume = volume_data.get('average', 1)
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                analysis['volume_surge'] = volume_ratio > 2.5  # Quét thanh khoản khi volume > 2.5x trung bình
                
                # Momentum shift
                momentum = market_data.get('momentum', {})
                rsi = momentum.get('rsi', 50)
                macd_signal = momentum.get('macd_signal', 0)
                
                if rsi > 70 and macd_signal < 0:
                    analysis['momentum_shift'] = 'BEARISH'  # Dấu hiệu giảm
                elif rsi < 30 and macd_signal > 0:
                    analysis['momentum_shift'] = 'BULLISH'  # Dấu hiệu tăng
                else:
                    analysis['momentum_shift'] = 'NEUTRAL'
                
                # Overall risk level
                risk_score = 0
                if analysis['volatility_level'] == 'HIGH':
                    risk_score += 30
                elif analysis['volatility_level'] == 'EXTREME':
                    risk_score += 50
                    
                if analysis['volume_surge']:
                    risk_score += 40
                    
                if analysis['momentum_shift'] != 'NEUTRAL':
                    risk_score += 20
                    
                if analysis['trend_strength'] < 0.3:
                    risk_score += 25
                    
                if risk_score < 40:
                    analysis['risk_level'] = 'LOW'
                elif risk_score < 80:
                    analysis['risk_level'] = 'MEDIUM'
                else:
                    analysis['risk_level'] = 'HIGH'
                    
            logger.debug(f"🧠 Market Analysis: Trend={analysis['trend_strength']:.2f}, "
                        f"Vol={analysis['volatility_level']}, VolumeSurge={analysis['volume_surge']}, "
                        f"Momentum={analysis['momentum_shift']}, Risk={analysis['risk_level']}")
                        
        except Exception as e:
            logger.warning(f"⚠️ Market analysis error: {e}")
        
        return analysis
    
    def _ai_decide_partial_take_profit(self, position, current_pnl, market_analysis):
        """🧠 AI QUYẾT ĐỊNH CHỐT LỜI MỘT PHẦN
        
        Logic AI:
        1. Nếu đang lỗ → KHÔNG chốt lời một phần
        2. Nếu lời nhỏ (< $3) → Giữ để chạy tiếp
        3. Nếu lời vừa ($3-$10) + điều kiện bình thường → Chốt 25%
        4. Nếu lời lớn (>$10) + dấu hiệu GIẢM NHẸ → Giữ để lời cao nhất
        5. Nếu lời lớn (>$10) + dấu hiệu GIẢM MẠNH/QUÉT THANH KHOẢN → Chốt 40-50%
        
        Args:
            position: dict thông tin lệnh
            current_pnl: P/L hiện tại ($)
            market_analysis: dict phân tích thị trường
            
        Returns:
            tuple: (should_close, reason, close_percentage)
        """
        # 1. Nếu đang lỗ → Không chốt lời
        if current_pnl <= 0:
            logger.debug(f"💰 PARTIAL TP: LOSS_POSITION - PNL: ${current_pnl:.2f}")
            return False, "LOSS_POSITION", 0.0
        
        # 2. Nếu lời nhỏ (< $3) → Giữ để chạy tiếp
        if current_pnl < 3.0:
            logger.debug(f"💰 PARTIAL TP: SMALL_PROFIT_HOLD - PNL: ${current_pnl:.2f}")
            return False, "SMALL_PROFIT_HOLD", 0.0
        
        # 3. Phân tích điều kiện thị trường
        trend_strength = market_analysis.get('trend_strength', 0.5)
        volatility_level = market_analysis.get('volatility_level', 'MEDIUM')
        volume_surge = market_analysis.get('volume_surge', False)
        momentum_shift = market_analysis.get('momentum_shift', 'NEUTRAL')
        risk_level = market_analysis.get('risk_level', 'MEDIUM')
        
        logger.debug(f"💰 PARTIAL TP: Market analysis - Trend: {trend_strength:.2f}, Vol: {volatility_level}, Volume surge: {volume_surge}, Momentum: {momentum_shift}, Risk: {risk_level}")
        
        # 4. Logic quyết định dựa trên P/L và điều kiện thị trường
        
        # KIỂM TRA WIN RATE HIỆN TẠI - Ưu tiên bảo vệ lợi nhuận nếu win rate thấp
        current_win_rate = self.get_win_rate()
        conservative_mode = current_win_rate < 0.55  # Conservative nếu win rate < 55%
        
        logger.debug(f"💰 PARTIAL TP: Win rate: {current_win_rate:.1%}, Conservative mode: {conservative_mode}")
        
        # LỜI VỪA ($3-$10)
        if current_pnl < 10.0:
            logger.debug(f"💰 PARTIAL TP: MODERATE_PROFIT range (${current_pnl:.2f})")
            # Trong điều kiện bình thường → Chốt 25%
            if risk_level == 'LOW' and not volume_surge:
                close_pct = 0.20 if conservative_mode else 0.25  # Chốt ít hơn nếu conservative
                reason = f"MODERATE_PROFIT_NORMAL_CONDITIONS_{'CONSERVATIVE' if conservative_mode else 'NORMAL'}"
                logger.debug(f"💰 PARTIAL TP: {reason} - Close {close_pct*100:.0f}%")
                return True, reason, close_pct
            # Trong điều kiện rủi ro → Chốt 30%
            elif risk_level == 'MEDIUM':
                close_pct = 0.25 if conservative_mode else 0.30
                reason = f"MODERATE_PROFIT_MEDIUM_RISK_{'CONSERVATIVE' if conservative_mode else 'NORMAL'}"
                logger.debug(f"💰 PARTIAL TP: {reason} - Close {close_pct*100:.0f}%")
                return True, reason, close_pct
            # Trong điều kiện rủi ro cao → Chốt 35%
            else:
                close_pct = 0.30 if conservative_mode else 0.35
                reason = f"MODERATE_PROFIT_HIGH_RISK_{'CONSERVATIVE' if conservative_mode else 'NORMAL'}"
                logger.debug(f"💰 PARTIAL TP: {reason} - Close {close_pct*100:.0f}%")
                return True, reason, close_pct
        
        # LỜI LỚN (>$10)
        else:
            logger.debug(f"💰 PARTIAL TP: LARGE_PROFIT range (${current_pnl:.2f})")
            # DẤU HIỆU GIẢM MẠNH hoặc QUÉT THANH KHOẢN
            strong_bearish_signals = [
                volume_surge,  # Quét thanh khoản
                volatility_level in ['HIGH', 'EXTREME'],  # Biến động mạnh
                momentum_shift == 'BEARISH',  # Momentum giảm
                trend_strength < 0.3  # Xu hướng yếu
            ]
            
            bearish_signal_count = sum(strong_bearish_signals)
            logger.debug(f"💰 PARTIAL TP: Strong bearish signals: {bearish_signal_count}/4 - {strong_bearish_signals}")
            
            if bearish_signal_count >= 2:  # Có ít nhất 2 dấu hiệu giảm mạnh
                # Chốt 45-50% để bảo vệ lợi nhuận
                close_pct = 0.40 if conservative_mode else (0.45 if bearish_signal_count >= 3 else 0.50)
                reason = f"STRONG_BEARISH_SIGNALS_{bearish_signal_count}_{'CONSERVATIVE' if conservative_mode else 'NORMAL'}"
                logger.debug(f"💰 PARTIAL TP: {reason} - Close {close_pct*100:.0f}%")
                return True, reason, close_pct
            
            # DẤU HIỆU GIẢM NHẸ
            mild_bearish_signals = [
                momentum_shift == 'BEARISH' and not volume_surge,  # Chỉ momentum giảm, không quét volume
                trend_strength < 0.5 and volatility_level == 'MEDIUM',  # Xu hướng trung bình + biến động trung bình
                risk_level == 'MEDIUM' and not volume_surge  # Risk trung bình, không quét volume
            ]
            
            logger.debug(f"💰 PARTIAL TP: Mild bearish signals: {sum(mild_bearish_signals)}/3 - {mild_bearish_signals}")
            
            if any(mild_bearish_signals):
                # Nếu conservative mode và lời rất lớn (> $20) → Chốt một phần nhỏ để bảo vệ
                if conservative_mode and current_pnl > 20.0:
                    logger.debug(f"💰 PARTIAL TP: MILD_BEARISH_CONSERVATIVE_PARTIAL - Close 15%")
                    return True, "MILD_BEARISH_CONSERVATIVE_PARTIAL", 0.15
                # GIỮ LỆNH để lời cao nhất có thể
                logger.debug(f"💰 PARTIAL TP: MILD_BEARISH_HOLD_FOR_MAX_PROFIT - Hold")
                return False, "MILD_BEARISH_HOLD_FOR_MAX_PROFIT", 0.0
            
            # ĐIỀU KIỆN TỐT - Chốt một phần nhỏ để bảo vệ
            if risk_level == 'LOW' and trend_strength > 0.7:
                close_pct = 0.15 if conservative_mode else 0.20
                reason = f"STRONG_TREND_PARTIAL_PROTECT_{'CONSERVATIVE' if conservative_mode else 'NORMAL'}"
                logger.debug(f"💰 PARTIAL TP: {reason} - Close {close_pct*100:.0f}%")
                return True, reason, close_pct
            
            # Điều kiện trung lập - Chốt 25-30%
            close_pct = 0.25 if conservative_mode else 0.30
            reason = f"LARGE_PROFIT_NEUTRAL_CONDITIONS_{'CONSERVATIVE' if conservative_mode else 'NORMAL'}"
            logger.debug(f"💰 PARTIAL TP: {reason} - Close {close_pct*100:.0f}%")
            return True, reason, close_pct
    
    def can_open_position(self, confidence=0.5, market_condition="UNKNOWN"):
        """🧠 AI QUYẾT ĐỊNH - Có nên mở lệnh mới không?
        
        Thay vì giới hạn cứng, AI phân tích:
        - Tổng risk hiện tại
        - Confidence của tín hiệu
        - Market condition
        - Win rate gần đây
        - Drawdown level
        - 🎯 Profit target protection
        
        Returns:
            tuple: (can_open: bool, reason: str, risk_score: float)
        """
        reasons = []
        risk_score = 0.0
        
        # 0. EXECUTIONAI CHECK - Pre-trade execution conditions
        try:
            if hasattr(self, 'execution_ai') and self.execution_ai is not None:
                allowed, reason, mode = self.execution_ai.allowed_to_execute()
                if not allowed:
                    logger.warning(f"🚫 ExecutionAI blocked trade: {reason} (mode: {mode})")
                    return False, f"ExecutionAI: {reason}", 0.0
                else:
                    logger.info(f"✅ ExecutionAI approved trade (mode: {mode})")
        except Exception as e:
            logger.warning(f"⚠️ ExecutionAI check failed: {e} - proceeding")
        
        # 0. 🛡️ HARD LIMIT: Max lệnh mở cùng lúc theo balance (BẢO VỆ CHỐNG CHÁY TÀI KHOẢN)
        max_allowed = self.get_effective_max_positions()
        current_positions = len(self.open_positions)
        if current_positions >= max_allowed:
            return False, f"❌ STOP - Đã có {current_positions}/{max_allowed} lệnh (Max limit để bảo vệ tài khoản)", 0.0
        
        # 1. 🎯 PROFIT TARGET PROTECTION - Ưu tiên cao nhất
        profit_achieved, current_profit, protection_mode = self.check_profit_target()
        
        if protection_mode == "HARD":
            return False, f"🛡️ HARD PROTECTION - Đã mất >50% profit từ peak (${current_profit:.2f})", 0.0
        elif protection_mode == "SOFT":
            risk_score -= 30  # Giảm 30 điểm
            reasons.append(f"🛡️ SOFT protection (Profit: ${current_profit:.2f})")
        elif protection_mode == "CONSERVATIVE":
            risk_score += 10  # Bonus vì đang lời
            reasons.append(f"✅ Đang lời ${current_profit:.2f}")
        
        # 2. ⚠️ HARD LIMIT: Tổng risk không được vượt quá 50% (GIẢM ĐỂ BẢO VỆ)
        total_risk = sum(pos['risk_amount'] for pos in self.open_positions if isinstance(pos, dict))
        max_total_risk = self.current_balance * self.max_risk_total
        current_risk = total_risk / self.current_balance if self.current_balance > 0 else 0
        
        if current_risk >= 0.5:
            return False, f"❌ STOP - Tổng risk {current_risk:.1%} >= 50% (Quá nguy hiểm)", 0.0
        
        # 3. ✅ SOFT ANALYSIS: Đánh giá điều kiện
        
        # 3.1: Risk level hiện tại
        if current_risk < 0.3:
            risk_score += 30  # Risk thấp → Tốt
            reasons.append(f"✅ Risk thấp ({current_risk:.1%})")
        elif current_risk < 0.5:
            risk_score += 20  # Risk trung bình
            reasons.append(f"⚠️ Risk TB ({current_risk:.1%})")
        else:
            risk_score += 5  # Risk cao → Cẩn trọng
            reasons.append(f"⚠️ Risk cao ({current_risk:.1%})")
        
        # 3.2: Confidence của tín hiệu
        if confidence >= 0.8:
            risk_score += 30  # Confidence cao
            reasons.append(f"✅ Conf cao ({confidence:.1%})")
        elif confidence >= 0.6:
            risk_score += 15
            reasons.append(f"⚠️ Conf TB ({confidence:.1%})")
        else:
            risk_score += 5
            reasons.append(f"⚠️ Conf thấp ({confidence:.1%})")
        
        # 3.3: Market condition
        if market_condition == "TRENDING":
            risk_score += 25  # Trending tốt
            reasons.append("✅ Market trending")
        elif market_condition == "SIDEWAYS/WEAK":
            risk_score += 10  # Sideways cẩn trọng
            reasons.append("⚠️ Market sideways")
        else:
            risk_score += 15  # Unknown
            reasons.append("❓ Market unknown")
        
        # 3.4: Win rate (nếu có đủ dữ liệu)
        if len(self.trade_history) >= 5:
            win_rate = self.get_win_rate()
            # 🆕 DEBUG LOG - Hiển thị chi tiết WR
            logger.info(f"📊 Win Rate Stats: {win_rate:.1%} (Wins: {self.win_count}, Losses: {self.loss_count}, History: {len(self.trade_history)} trades)")
            
            if win_rate >= 0.6:
                risk_score += 15
                reasons.append(f"✅ WR cao ({win_rate:.1%})")
            elif win_rate >= 0.4:
                risk_score += 5
                reasons.append(f"⚠️ WR TB ({win_rate:.1%})")
            else:
                risk_score -= 10
                reasons.append(f"❌ WR thấp ({win_rate:.1%})")
        else:
            logger.info(f"📊 Win Rate: Chưa đủ dữ liệu (History: {len(self.trade_history)}/5 trades)")

        
        # 4. 🎯 QUYẾT ĐỊNH: Score >= 55 → Mở lệnh (dễ vào hơn, chấp nhận sideways)
        can_open = risk_score >= 55
        
        summary = " | ".join(reasons)
        decision = "✅ MỞ LỆNH" if can_open else "❌ KHÔNG MỞ"
        
        logger.info(f"🧠 QUYẾT ĐỊNH AI: {decision} (Điểm số: {risk_score:.0f}/100)")
        logger.info(f"   Phân tích: {summary}")
        
        return can_open, summary, risk_score
    
    def validate_risk_reward(self, entry_price, sl_price, tp_price):
        """Kiểm tra risk/reward ratio có hợp lý không"""
        risk = abs(entry_price - sl_price)
        reward = abs(tp_price - entry_price)
        
        if risk == 0:
            return False, 0
        
        rr_ratio = reward / risk
        
        if rr_ratio < self.min_risk_reward:
            logger.warning(f"⚠️ R:R ratio {rr_ratio:.2f} < {self.min_risk_reward} (không khuyến nghị)")
            return False, rr_ratio
        
        logger.info(f"✅ R:R ratio: {rr_ratio:.2f}:1 (tốt)")
        return True, rr_ratio
    
    def add_position(self, signal_data, lot_size, mt5_ticket=None):
        """Thêm lệnh mới vào danh sách quản lý"""
        # Validate signal_data is a dict
        if not isinstance(signal_data, dict):
            logger.error(f"❌ Invalid signal_data type in add_position: {type(signal_data)}, expected dict. Data: {signal_data}")
            return None
        
        # accept explicit SL/TP from arguments or from signal_data
        sl_price = signal_data.get('sl') if isinstance(signal_data, dict) else None
        tp_price = signal_data.get('tp') if isinstance(signal_data, dict) else None

        position = {
            'signal_id': signal_data['signal_id'],
            'action': signal_data['action'],
            'entry_price': signal_data.get('entry_price', signal_data.get('price')),
            'sl': sl_price,
            'tp': tp_price,
            'lot_size': lot_size,
            'confidence': signal_data.get('confidence', 50.0) / 100.0,
            'risk_amount': self.current_balance * self.risk_per_trade,
            'open_time': datetime.now(),
            'status': 'OPEN',
            'mt5_ticket': mt5_ticket  # Thêm MT5 ticket để partial take profit
        }
        
        self.open_positions.append(position)
        logger.info(f"📊 Thêm lệnh #{signal_data['signal_id']} vào quản lý ({len(self.open_positions)}/{self.get_effective_max_positions()})")
        try:
            # Ghi log trạng thái chi tiết bao gồm BUY/SELL, lot và giá vào
            self.log_position_status(position)
        except Exception:
            pass

        return position

    def log_position_status(self, pos):
        """Ghi log trạng thái ngắn gọn cho một position.

        Format: #{id}: ACTION STATUS | Lot: x.xx | Entry: xxxx.xx | P/L: $xx.xx (nếu có)
        """
        try:
            sid = pos.get('signal_id', 'N/A')
            action = pos.get('action', 'N/A')
            status = pos.get('status', 'N/A')
            lot = pos.get('lot_size', 0)
            entry = pos.get('entry_price', 0)
            profit = pos.get('profit', None)
            mode = get_runtime_mode()
            # Include CPU/MEM snapshot when available to aid debugging on VPS
            try:
                if PSUTIL_AVAILABLE:
                    cpu = psutil.cpu_percent(interval=0.1)
                    mem = psutil.virtual_memory().percent
                    if profit is not None:
                        logger.info(f"🔔 #{sid}: {action} {status} | Lot: {lot:.2f} | Entry: {entry:.4f} | P/L: ${profit:.2f} | Mode: {mode} | CPU={cpu:.1f}% MEM={mem:.1f}%")
                    else:
                        logger.info(f"🔔 #{sid}: {action} {status} | Lot: {lot:.2f} | Entry: {entry:.4f} | Mode: {mode} | CPU={cpu:.1f}% MEM={mem:.1f}%")
                else:
                    if profit is not None:
                        logger.info(f"🔔 #{sid}: {action} {status} | Lot: {lot:.2f} | Entry: {entry:.4f} | P/L: ${profit:.2f} | Mode: {mode}")
                    else:
                        logger.info(f"🔔 #{sid}: {action} {status} | Lot: {lot:.2f} | Entry: {entry:.4f} | Mode: {mode}")
            except Exception:
                # Fallback to basic log if sampling fails
                if profit is not None:
                    logger.info(f"🔔 #{sid}: {action} {status} | Lot: {lot:.2f} | Entry: {entry:.4f} | P/L: ${profit:.2f} | Mode: {mode}")
                else:
                    logger.info(f"🔔 #{sid}: {action} {status} | Lot: {lot:.2f} | Entry: {entry:.4f} | Mode: {mode}")
        except Exception:
            logger.debug("⚠️ log_position_status failed")
    
    def close_position(self, signal_id, exit_price, reason='MANUAL'):
        """Đóng lệnh và tính P/L"""
        for i, pos in enumerate(self.open_positions):
            # Skip invalid position data
            if not isinstance(pos, dict):
                logger.warning(f"⚠️ Skipping invalid position data in close_position: {pos} (type: {type(pos)})")
                continue
                
            if pos['signal_id'] == signal_id:
                # 🎯 ĐÓNG LỆNH THẬT TRÊN MT5 TRƯỚC
                mt5_ticket = pos.get('mt5_ticket', None)
                if mt5_ticket:
                    mt5_success = self.close_position_on_mt5(mt5_ticket, reason)
                    if not mt5_success:
                        logger.error(f"❌ Không thể đóng lệnh #{mt5_ticket} trên MT5!")
                        return None
                    logger.info(f"✅ Đã đóng lệnh #{mt5_ticket} trên MT5 | Lý do: {reason}")
                
                # Tính profit/loss
                if 'BUY' in pos['action']:
                    pnl = (exit_price - pos['entry_price']) * pos['lot_size'] * 100
                else:  # SELL
                    pnl = (pos['entry_price'] - exit_price) * pos['lot_size'] * 100
                
                # Cập nhật balance
                self.current_balance += pnl
                
                # Cập nhật win/loss count
                if pnl > 0:
                    self.win_count += 1
                    logger.info(f"✅ CLOSE WIN #{signal_id} - Profit: ${pnl:.2f} ({reason})")
                else:
                    self.loss_count += 1
                    logger.info(f"❌ CLOSE LOSS #{signal_id} - Loss: ${pnl:.2f} ({reason})")
                
                # Lưu vào history
                pos['exit_price'] = exit_price
                pos['pnl'] = pnl
                pos['close_time'] = datetime.now()
                pos['close_reason'] = reason
                pos['status'] = 'CLOSED'
                self.trade_history.append(pos)
                try:
                    self.log_position_status(pos)
                except Exception:
                    pass

                # Call post-close callback if provided (e.g., for re-entry hooks)
                try:
                    if callable(getattr(self, 'on_position_closed', None)):
                        # Provide a shallow copy to avoid mutation issues
                        try:
                            cb_pos = pos.copy()
                        except Exception:
                            cb_pos = pos
                        try:
                            self.on_position_closed(cb_pos)
                        except Exception:
                            pass
                except Exception:
                    pass

                # Xóa khỏi open positions
                self.open_positions.pop(i)
                
                logger.info(f"💰 Balance: ${self.current_balance:,.2f} (Start: ${self.initial_balance:,.2f})")
                return pnl
        
        return None
    
    def should_cut_loss(self, signal_id, current_price):
        """AI quyết định có nên cắt lỗ không
        
        Logic:
        - Nếu lệnh đang lỗ > 50% khoảng SL → Cắt ngay
        - Nếu có lệnh khác đang lời → Giữ lệnh lời, cắt lệnh lỗ
        """
        for pos in self.open_positions:
            # Skip invalid position data
            if not isinstance(pos, dict):
                logger.warning(f"⚠️ Skipping invalid position data in should_cut_loss: {pos} (type: {type(pos)})")
                continue
                
            if pos['signal_id'] == signal_id:
                # Tính P/L hiện tại
                if 'BUY' in pos['action']:
                    current_pnl = (current_price - pos['entry_price']) * pos['lot_size'] * 100
                else:
                    current_pnl = (pos['entry_price'] - current_price) * pos['lot_size'] * 100
                
                # Nếu đang lãi → KHÔNG cắt
                if current_pnl > 0:
                    return False, "Đang lãi"
                
                # Tính % lỗ so với SL (nếu có)
                sl_price = pos.get('sl', None)
                if sl_price and sl_price > 0:
                    sl_distance = abs(pos['entry_price'] - sl_price)
                    current_loss_distance = abs(current_price - pos['entry_price'])
                    loss_pct = (current_loss_distance / sl_distance) if sl_distance > 0 else 0
                    
                    # Cắt lỗ nếu > 50% khoảng SL
                    if loss_pct > 0.5:
                        logger.warning(f"⚠️ Lệnh #{signal_id} lỗ {loss_pct*100:.1f}% khoảng SL → NÊN CẮT")
                        return True, f"Loss {loss_pct*100:.1f}%"
                
                # Nếu không có SL, kiểm tra loss tuyệt đối (> $5)
                if abs(current_pnl) > 5.0:
                    logger.warning(f"⚠️ Lệnh #{signal_id} lỗ ${abs(current_pnl):.2f} → NÊN CẮT")
                    return True, f"Loss ${abs(current_pnl):.2f}"
                
                # Kiểm tra có lệnh khác đang lời không
                other_positions_profit = [p for p in self.open_positions 
                                         if p['signal_id'] != signal_id]
                
                if other_positions_profit:
                    return True, "Có lệnh khác lời hơn"
                
                return False, "Giữ lệnh"
        
        return False, "Không tìm thấy"
    
    def update_trailing_stops(self, current_prices, market_analysis=None, ms_signal=None, ls_signal=None, trailing_sl_signal=None, **kwargs):
        """🎯 BREAK EVEN PROTECTION (Di chuyển SL lên entry khi có lãi)
        
        ✅ CHỨC NĂNG ĐANG BẬT:
        - Khi lệnh có lãi → Di chuyển SL lên entry (break even)
        - Bảo vệ lợi nhuận, tránh quay đầu thành lỗ
        
        ❌ CHỨC NĂNG ĐÃ TẮT:
        - KHÔNG kéo TP lên (giữ TP gốc)
        - KHÔNG tự động chốt lời sớm
        - KHÔNG đóng lệnh khi đảo chiều
        
        Args:
            current_prices: dict với 'BUY'/'SELL' giá hiện tại
            market_analysis: dict phân tích thị trường (không dùng)
            ms_signal: Market Structure signal (không dùng)
            ls_signal: Liquidity Sweep signal (không dùng)
        
        Returns:
            dict: {'updated_positions': [...], 'closed_positions': []}
        """
        try:
            if not self.open_positions:
                return {'updated_positions': [], 'closed_positions': []}
            
            updated_positions = []
            closed_positions = []
            
            logger.debug("🎯 BREAK EVEN: Checking positions for SL → Entry...")
        
            for pos in self.open_positions[:]:
                # Skip nếu pos không phải dict
                if not isinstance(pos, dict):
                    logger.warning(f"⚠️ Skipping invalid position data: {pos} (type: {type(pos)})")
                    continue
                
                signal_id = pos['signal_id']
                action = pos['action']
                
                # Xử lý action có thể là dict hoặc string
                if isinstance(action, dict):
                    action_str = action.get('type', 'BUY')
                else:
                    action_str = str(action)
                
                entry_price = pos['entry_price']
                
                # Lấy giá hiện tại
                current_price = current_prices.get('BUY' if 'BUY' in action_str else 'SELL', entry_price)
                
                # Tính P/L hiện tại (pips)
                if 'BUY' in action_str:
                    profit_pips = (current_price - entry_price) * 100  # Convert to pips
                    current_pnl = profit_pips * pos['lot_size']
                else:
                    profit_pips = (entry_price - current_price) * 100  # Convert to pips
                    current_pnl = profit_pips * pos['lot_size']
                
                # ✅ ĐIỀU KIỆN: Chỉ move SL khi lãi >= 40-50 pips
                MIN_PROFIT_PIPS = 40.0  # Tối thiểu 40 pips lãi
                
                if profit_pips < MIN_PROFIT_PIPS:
                    logger.debug(f"🎯 BREAK EVEN: #{signal_id} profit {profit_pips:.1f} pips < {MIN_PROFIT_PIPS} pips - Chưa đủ để move SL")
                    continue
                
                # ✅ BREAK EVEN: Di chuyển SL lên entry
                new_sl = entry_price
                
                # Kiểm tra SL hiện tại
                old_sl = pos.get('current_sl', pos.get('sl'))
                
                # Chỉ update nếu chưa move lên entry
                should_update = False
                if 'BUY' in action_str:
                    # BUY: new_sl phải > old_sl
                    if old_sl is None or new_sl > old_sl:
                        should_update = True
                else:
                    # SELL: new_sl phải < old_sl
                    if old_sl is None or new_sl < old_sl:
                        should_update = True
                
                if should_update:
                    pos['current_sl'] = new_sl
                    updated_positions.append(signal_id)
                    logger.info(f"✅ BREAK EVEN: #{signal_id} SL moved to entry ${new_sl:.5f} | Profit: ${current_pnl:.2f}")
                    
                    # Update trên MT5 nếu có
                    mt5_ticket = pos.get('mt5_ticket')
                    if mt5_ticket and self.mt5_enabled:
                        self._update_sl_on_mt5(mt5_ticket, new_sl, pos.get('current_tp'))
            
            if updated_positions:
                logger.info(f"🎯 BREAK EVEN: Updated {len(updated_positions)} positions to entry SL")
            
            return {'updated_positions': updated_positions, 'closed_positions': closed_positions}
            
        except Exception as e:
            logger.error("❌ Exception in update_trailing_stops:\n" + traceback.format_exc())
            return {'updated_positions': [], 'closed_positions': []}
        
            # If caller provided a pre-computed trailing_sl analysis, prefer it
            passed_trailing_signal = trailing_sl_signal

            for pos in self.open_positions[:]:  # Copy để tránh lỗi khi modify list
                # Skip nếu pos không phải dict (bảo vệ chống lỗi data corrupt)
                if not isinstance(pos, dict):
                    logger.warning(f"⚠️ Skipping invalid position data: {pos} (type: {type(pos)})")
                    continue
                
                signal_id = pos['signal_id']
                action = pos['action']
                
                # Xử lý action có thể là dict hoặc string
                if isinstance(action, dict):
                    action_str = action.get('type', 'BUY')  # Giả sử action có key 'type'
                else:
                    action_str = str(action)
                
                entry_price = pos['entry_price']
                
                # Lấy giá hiện tại
                current_price = current_prices.get('BUY' if 'BUY' in action_str else 'SELL', entry_price)
                
                # Tính P/L hiện tại
                if 'BUY' in action:
                    current_pnl = (current_price - entry_price) * pos['lot_size'] * 100
                else:
                    current_pnl = (entry_price - current_price) * pos['lot_size'] * 100
                
                # Chỉ xử lý lệnh đang lãi
                if current_pnl <= 0:
                    continue
                
                logger.debug(f"🎯 TRAILING: #{signal_id} {action} - PNL: ${current_pnl:.2f}")
                
                # 1. 🎯 TRAILING STOP LOSS - SL lên entry (hòa vốn)
                new_sl = entry_price  # SL tại entry = hòa vốn
                
                # Nếu đã có SL cũ, chỉ update nếu mới tốt hơn
                old_sl = pos.get('current_sl', pos.get('sl'))
                if old_sl:
                    if 'BUY' in action_str and new_sl > old_sl:
                        pos['current_sl'] = new_sl
                        logger.info(f"🎯 TRAILING SL: #{signal_id} SL updated to entry ${new_sl:.4f} (Break-even)")
                        updated_positions.append(signal_id)
                    elif 'SELL' in action_str and new_sl < old_sl:
                        pos['current_sl'] = new_sl
                        logger.info(f"🎯 TRAILING SL: #{signal_id} SL updated to entry ${new_sl:.4f} (Break-even)")
                        updated_positions.append(signal_id)
                
                # 2. 🎯 DYNAMIC TAKE PROFIT - TP gấp đôi lợi nhuận hiện tại
                profit_distance = abs(current_price - entry_price)
                new_tp_distance = profit_distance * 2  # Gấp đôi
                
                if 'BUY' in action_str:
                    new_tp = entry_price + new_tp_distance
                else:
                    new_tp = entry_price - new_tp_distance
                
                # Update TP
                old_tp = pos.get('current_tp', pos.get('tp'))
                if old_tp:
                    pos['current_tp'] = new_tp
                    logger.info(f"🎯 DYNAMIC TP: #{signal_id} TP updated to ${new_tp:.4f} (2x profit distance)")
                    updated_positions.append(signal_id)
                
                # 3. 🚨 AUTO TAKE PROFIT - Chốt lời khi có dấu hiệu đảo chiều mạnh
                should_close = self._should_auto_take_profit(pos, current_pnl, market_analysis, ms_signal, ls_signal)
                
                if should_close:
                    reason = "AUTO_TAKE_PROFIT_TRAILING"
                    pnl = self.close_position(signal_id, current_price, reason)
                    if pnl is not None:
                        closed_positions.append({'signal_id': signal_id, 'pnl': pnl, 'reason': reason})
                        logger.info(f"🚨 AUTO TAKE PROFIT: #{signal_id} closed with ${pnl:.2f} profit")
            
            # 4. 🎯 TRAILINGSL AI - Dynamic trailing stop analysis
            if hasattr(self, 'trailing_sl_ai') and self.trailing_sl_ai is not None:
                # Get market data for TrailingSL analysis
                market_df = None
                try:
                    # Try to get from CompleteAITradingSystem if available
                    if hasattr(self, '_get_market_data_for_ai'):
                        market_df = self._get_market_data_for_ai()
                    # Fallback: try to get from current system context
                    elif hasattr(self, 'data_fetcher') and hasattr(self.data_fetcher, 'get_recent_data'):
                        market_df = self.data_fetcher.get_recent_data(bars=100)
                except Exception:
                    market_df = None
                
                if market_df is not None and len(market_df) >= 20:
                    # Use passed trailing_sl_signal when available (avoids double analysis)
                    if passed_trailing_signal is not None:
                        trailing_result = passed_trailing_signal
                    else:
                        # Call TrailingSL AI analyze
                        trailing_result = self.trailing_sl_ai.analyze(market_df, {'bid': current_price, 'ask': current_price})

                    if isinstance(trailing_result, dict) and trailing_result.get('confidence', 0.0) >= 0.6:
                        ai_trailing_stop = trailing_result.get('trailing_stop')
                        ai_action = trailing_result.get('recommended_action', 'hold')
                        
                        if ai_trailing_stop is not None:
                            # Only update if AI suggests a better stop
                            current_sl = pos.get('current_sl', pos.get('sl'))
                            if current_sl:
                                # For BUY: AI stop should be higher (better)
                                # For SELL: AI stop should be lower (better)
                                should_update = False
                                if 'BUY' in action_str and ai_trailing_stop > current_sl:
                                    should_update = True
                                elif 'SELL' in action_str and ai_trailing_stop < current_sl:
                                    should_update = True
                                
                                if should_update:
                                    pos['current_sl'] = ai_trailing_stop
                                    updated_positions.append(signal_id)
                                    logger.info(f"🎯 TRAILINGSL AI: #{signal_id} SL updated to ${ai_trailing_stop:.4f} (Action: {ai_action}, Conf: {trailing_result.get('confidence', 0.0):.2f})")
                                
                                # Check if AI recommends tightening or adjusting
                                if ai_action in ['tighten_stop', 'adjust_stop'] and trailing_result.get('confidence', 0.0) >= 0.7:
                                    # AI suggests more aggressive trailing
                                    tighter_stop = ai_trailing_stop
                                    if 'BUY' in action_str:
                                        tighter_stop = min(ai_trailing_stop, current_price - 0.5)  # Max tighten 50 cents
                                    else:
                                        tighter_stop = max(ai_trailing_stop, current_price + 0.5)
                                    
                                    if tighter_stop != current_sl:
                                        pos['current_sl'] = tighter_stop
                                        updated_positions.append(signal_id)
                                        logger.info(f"🎯 TRAILINGSL AI TIGHTEN: #{signal_id} SL tightened to ${tighter_stop:.4f}")
                    else:
                        conf = trailing_result.get('confidence', 0.0) if isinstance(trailing_result, dict) else 0.0
                        logger.debug(f"🎯 TRAILINGSL AI: Low confidence ({conf:.2f}) - keeping current stops")
                else:
                    logger.debug("🎯 TRAILINGSL AI: Insufficient market data for analysis")

            return {
                'updated_positions': updated_positions,
                'closed_positions': closed_positions
            }
        except Exception as e:
            import traceback
            logger.error("❌ Exception in update_trailing_stops:\n" + traceback.format_exc())
            # Return safe empty structure
            return {'updated_positions': [], 'closed_positions': []}

    def _safe_order_send(self, request, max_retries=3, retry_delay=0.5):
        """Helper to send MT5 orders with retries and defensive logging.

        Returns the `result` from `mt5.order_send` or `None` on failure.
        This centralizes retry and diagnostic logging so callers don't dereference None.
        """
        try:
            import MetaTrader5 as mt5
        except Exception:
            logger.error("❌ MetaTrader5 import failed in _safe_order_send")
            return None

        try:
            max_retries = int(max_retries)
        except Exception:
            max_retries = 3
        # Diagnostic: call order_check() once before attempting order_send so we
        # capture the broker/terminal validation result (non-blocking)
        try:
            # Sanitize comment field to avoid broker/MT5 rejecting requests.
            # MT5 comment must be ASCII printable and typically <= 31 characters.
            try:
                if isinstance(request, dict) and request.get('comment') is not None:
                    import re
                    raw_comment = request.get('comment')
                    try:
                        raw_s = str(raw_comment)
                    except Exception:
                        raw_s = ''
                    # replace whitespace with underscore, remove non-printable/non-ascii
                    raw_s = re.sub(r"\s+", "_", raw_s)
                    raw_s = ''.join(ch for ch in raw_s if 32 <= ord(ch) <= 126)
                    # truncate to 31 chars (MT5 comment limit)
                    if len(raw_s) > 31:
                        raw_s = raw_s[:31]
                    request['comment'] = raw_s
            except Exception:
                # Don't let comment sanitization break order flow
                pass

            try:
                order_check_res = mt5.order_check(request)
            except Exception as _ex:
                order_check_res = f"order_check raised: {_ex}"
            logger.debug(f"🔍 MT5 order_check result: {order_check_res}")
        except Exception:
            # Never allow diagnostics to raise
            pass

        result = None
        # Short-circuit: if operator requested to disable live trading, return a simulated success
        try:
            if globals().get('FORCE_DISABLE_TRADING', False):
                logger.info("ℹ️ FORCE_DISABLE_TRADING=True — skipping real MT5 order_send (simulated success).")
                class _SimResult:
                    pass
                sim = _SimResult()
                try:
                    sim.retcode = getattr(mt5, 'TRADE_RETCODE_DONE', 10009)
                except Exception:
                    sim.retcode = 10009
                sim.comment = 'simulated-order-send'
                return sim
        except Exception:
            pass
        for attempt in range(max_retries):
            try:
                result = mt5.order_send(request)
            except Exception as e:
                logger.warning(f"⚠️ MT5 order_send exception attempt {attempt+1}/{max_retries}: {e}")
                result = None

            if result is not None:
                return result

            logger.warning(f"⚠️ MT5 order_send attempt {attempt+1}/{max_retries} returned None, retrying...")
            time.sleep(retry_delay)

        # After retries: collect last_error() and other diagnostic info
        logger.error(f"❌ MT5 order_send returned None after {max_retries} attempts")
        try:
            try:
                last_err = mt5.last_error()
            except Exception as _le:
                last_err = f"mt5.last_error() raised: {_le}"
            logger.error(f"MT5 last_error: {last_err}")
        except Exception:
            pass

        try:
            terminal_info = mt5.terminal_info()
            if terminal_info is None:
                logger.error("❌ MT5 terminal_info() returned None - MT5 not connected!")
            else:
                # terminal_info sometimes lacks 'trade_allowed' attribute; guard access
                trade_allowed = getattr(terminal_info, 'trade_allowed', None)
                connected = getattr(terminal_info, 'connected', None)
                logger.error(f"📊 MT5 Terminal: Connected={connected}, TradeAllowed={trade_allowed}")
        except Exception:
            logger.error("❌ Failed to read MT5 terminal_info()")

        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("❌ MT5 account_info() returned None - Account not available!")
            else:
                logger.error(f"📊 MT5 Account: Balance={getattr(account_info, 'balance', None)}, Margin={getattr(account_info, 'margin', None)}, FreeMargin={getattr(account_info, 'margin_free', None)}")
        except Exception:
            logger.error("❌ Failed to read MT5 account_info()")

        # Log request payload for debugging
        try:
            logger.error(f"📊 Request details: action={request.get('action')}, symbol={request.get('symbol')}, volume={request.get('volume')}, type={request.get('type')}, position={request.get('position')}")
            logger.error(f"📊 Price details: price={request.get('price')}, deviation={request.get('deviation')}")
        except Exception:
            logger.error("❌ Failed to serialize MT5 request for logging")

        return None
    
    def _should_auto_take_profit(self, position, current_pnl, market_analysis=None, ms_signal=None, ls_signal=None):
        """🧠 QUYẾT ĐỊNH CÓ NÊN TỰ ĐỘNG CHỐT LỜI KHÔNG
        
        Logic:
        - Dấu hiệu giảm mạnh: volume_surge + momentum BEARISH + trend_strength < 0.3
        - Dấu hiệu đảo chiều: MS signal ngược lại + LS signal mạnh
        - Chỉ áp dụng khi lời > $5 (tránh chốt lời quá sớm)
        
        Args:
            position: dict thông tin lệnh
            current_pnl: P/L hiện tại ($)
            market_analysis: dict phân tích thị trường
            ms_signal: Market Structure signal
            ls_signal: Liquidity Sweep signal
        
        Returns:
            bool: Có nên chốt lời không
        """
        # Chỉ áp dụng cho lệnh lời > $5
        if current_pnl < 5.0:
            return False
        
        action = position['action']
        # Xử lý action có thể là dict hoặc string
        if isinstance(action, dict):
            action_str = action.get('type', 'BUY')
        else:
            action_str = str(action)
        
        # 1. 🎯 DẤU HIỆU GIẢM MẠNH - Từ market analysis
        strong_bearish_signals = 0
        
        if market_analysis:
            volume_surge = market_analysis.get('volume_surge', False)
            momentum_shift = market_analysis.get('momentum_shift', 'NEUTRAL')
            trend_strength = market_analysis.get('trend_strength', 0.5)
            
            if volume_surge:
                strong_bearish_signals += 1
            if momentum_shift == 'BEARISH':
                strong_bearish_signals += 1
            if trend_strength < 0.3:
                strong_bearish_signals += 1
        
        # 2. 🎯 DẤU HIỆU ĐẢO CHIỀU - Từ MS và LS AI
        reversal_signals = 0
        
        # Market Structure signal ngược lại
        if ms_signal is not None:
            if ('BUY' in action_str and ms_signal == -1) or ('SELL' in action_str and ms_signal == 1):
                reversal_signals += 1
        
        # Liquidity Sweep signal mạnh
        if ls_signal and hasattr(ls_signal, 'get'):
            ls_strength = ls_signal.get('strength', 0)
            if ls_strength >= 0.7:  # LS mạnh
                reversal_signals += 1
        
        # 3. 🎯 QUYẾT ĐỊNH CHỐT LỜI
        total_signals = strong_bearish_signals + reversal_signals
        
        logger.debug(f"🚨 AUTO TP CHECK: #{position['signal_id']} - Bearish: {strong_bearish_signals}, Reversal: {reversal_signals}, Total: {total_signals}")
        
        # Chốt lời nếu có >= 2 dấu hiệu (bearish + reversal) HOẶC >= 3 bearish signals
        if total_signals >= 2 or strong_bearish_signals >= 3:
            logger.info(f"🚨 AUTO TP TRIGGER: #{position['signal_id']} - Strong reversal signals detected")
            return True
        
        return False
    
    def auto_trim_positions(self, current_prices):
        """🔧 TỈA LỆNH TỰ ĐỘNG - Dùng lợi nhuận lệnh dương đóng lệnh âm
        
        Logic:
        1. Tính tổng P/L của tất cả lệnh đang mở
        2. Nếu có lệnh dương + lệnh âm cùng tồn tại:
           - Đóng lệnh âm lớn nhất nếu tổng profit > 0
           - Giữ lại lệnh dương để chạy tiếp
        3. Ưu tiên đóng lệnh âm có loss% cao nhất
        
        Args:
            current_prices: dict với keys 'BUY' và 'SELL' là giá hiện tại
            
        Returns:
            list of closed position IDs
        """
        if len(self.open_positions) < 2:
            return []  # Cần ít nhất 2 lệnh
        
        # Tính P/L cho từng lệnh
        positions_with_pnl = []
        total_pnl = 0
        
        for pos in self.open_positions:
            # Skip invalid position data
            if not isinstance(pos, dict):
                logger.warning(f"⚠️ Skipping invalid position data in auto_trim_positions: {pos} (type: {type(pos)})")
                continue
                
            # Lấy giá hiện tại
            if 'BUY' in pos['action']:
                current_price = current_prices.get('BUY', pos['entry_price'])
                pnl = (current_price - pos['entry_price']) * pos['lot_size'] * 100
            else:  # SELL
                current_price = current_prices.get('SELL', pos['entry_price'])
                pnl = (pos['entry_price'] - current_price) * pos['lot_size'] * 100
            
            positions_with_pnl.append({
                'position': pos,
                'current_price': current_price,
                'pnl': pnl,
                'pnl_percent': (pnl / (pos['entry_price'] * pos['lot_size'] * 100)) * 100
            })
            total_pnl += pnl
        
        # Phân loại lệnh dương và âm
        positive_positions = [p for p in positions_with_pnl if p['pnl'] > 0]
        negative_positions = [p for p in positions_with_pnl if p['pnl'] < 0]
        
        # Điều kiện trim: Có cả lệnh dương và âm, và tổng P/L > 0
        if not positive_positions or not negative_positions:
            return []
        
        if total_pnl <= 0:
            logger.info("💡 Tổng P/L âm - Không trim (đợi lệnh dương tăng thêm)")
            return []
        
        closed_ids = []
        
        # Sort lệnh âm theo loss% (cao nhất trước)
        negative_positions.sort(key=lambda x: x['pnl'])
        
        # Tính profit có thể dùng để trim (giữ lại 30% profit cho an toàn)
        available_profit = total_pnl * 0.7
        
        logger.info(f"🔧 AUTO TRIM - Tổng P/L: ${total_pnl:.2f}, Available: ${available_profit:.2f}")
        logger.info(f"   Lệnh dương: {len(positive_positions)}, Lệnh âm: {len(negative_positions)}")
        
        # Đóng lệnh âm từng cái một
        for neg_pos in negative_positions:
            loss_amount = abs(neg_pos['pnl'])
            
            # Chỉ đóng nếu profit đủ cover loss
            if available_profit >= loss_amount:
                pos = neg_pos['position']
                current_price = neg_pos['current_price']
                
                # Đóng lệnh
                pnl = self.close_position(
                    pos['signal_id'], 
                    current_price, 
                    reason='AUTO_TRIM'
                )
                
                if pnl is not None:
                    closed_ids.append(pos['signal_id'])
                    available_profit -= loss_amount
                    
                    logger.info(f"✂️ TRIM #{pos['signal_id']} - Loss: ${pnl:.2f} (Covered by profit)")
                    
                    # Chỉ đóng 1 lệnh mỗi lần để không quá aggressive
                    break
        
        if closed_ids:
            logger.info(f"✅ Trimmed {len(closed_ids)} positions - Balance: ${self.current_balance:,.2f}")
        
        return closed_ids
    
    def close_all_by_type(self, action_type, current_price, reason='REVERSE_SIGNAL'):
        """🔄 ĐÓNG TẤT CẢ LỆNH CÙNG LOẠI (BUY hoặc SELL)
        
        Khi có tín hiệu đảo chiều:
        - Tín hiệu BUY mới → Đóng TẤT CẢ lệnh SELL cũ
        - Tín hiệu SELL mới → Đóng TẤT CẢ lệnh BUY cũ
        
        Args:
            action_type: 'BUY' hoặc 'SELL' - loại lệnh cần đóng
            current_price: giá đóng lệnh
            reason: lý do đóng lệnh
        
        Returns:
            list of (signal_id, pnl) tuples
        """
        closed_positions = []
        positions_to_close = [pos for pos in self.open_positions if isinstance(pos, dict) and action_type in pos['action']]
        
        if not positions_to_close:
            return closed_positions
        
        logger.info(f"🔄 BATCH CLOSE - Đóng {len(positions_to_close)} lệnh {action_type} ({reason})")
        
        for pos in positions_to_close:
            signal_id = pos['signal_id']
            pnl = self.close_position(signal_id, current_price, reason)
            
            if pnl is not None:
                closed_positions.append((signal_id, pnl))
        
        total_pnl = sum(pnl for _, pnl in closed_positions)
        logger.info(f"✅ Batch close hoàn tất - Total P/L: ${total_pnl:.2f}")
        
        return closed_positions
    
    def close_all_positions(self, current_price, reason='EXIT_ALL'):
        """🛑 ĐÓNG TẤT CẢ LỆNH (BUY + SELL)
        
        Sử dụng khi:
        - Có tín hiệu EXIT từ AI
        - Drawdown quá lớn
        - Emergency stop
        
        Returns:
            dict với keys 'BUY' và 'SELL' chứa list (signal_id, pnl)
        """
        if not self.open_positions:
            return {'BUY': [], 'SELL': []}
        
        logger.info(f"🛑 EXIT ALL - Đóng {len(self.open_positions)} lệnh ({reason})")
        
        result = {
            'BUY': self.close_all_by_type('BUY', current_price, reason),
            'SELL': self.close_all_by_type('SELL', current_price, reason)
        }
        
        total_pnl = sum(pnl for positions in result.values() for _, pnl in positions)
        logger.info(f"✅ Exit all hoàn tất - Total P/L: ${total_pnl:.2f}")
        
        return result
    
    def get_statistics(self):
        """Lấy thống kê trading"""
        total_trades = len(self.trade_history)
        win_rate = self.get_win_rate()
        
        total_profit = sum(t['pnl'] for t in self.trade_history if t['pnl'] > 0)
        total_loss = sum(t['pnl'] for t in self.trade_history if t['pnl'] < 0)
        net_profit = self.current_balance - self.initial_balance
        
        # Đếm số lệnh theo lý do đóng
        trim_count = sum(1 for t in self.trade_history if t.get('close_reason') == 'AUTO_TRIM')
        cut_loss_count = sum(1 for t in self.trade_history if t.get('close_reason') == 'CUT_LOSS')
        reverse_count = sum(1 for t in self.trade_history if t.get('close_reason') == 'REVERSE_SIGNAL')
        exit_count = sum(1 for t in self.trade_history if t.get('close_reason') == 'EXIT_ALL')
        
        # 🎯 Profit target progress
        profit_achieved, current_profit, protection_mode = self.check_profit_target()
        profit_progress = (current_profit / self.profit_target) * 100 if self.profit_target > 0 else 0
        
        return {
            'total_trades': total_trades,
            'wins': self.win_count,
            'losses': self.loss_count,
            'win_rate': win_rate,
            'current_balance': self.current_balance,
            'net_profit': net_profit,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'open_positions': len(self.open_positions),
            'trim_count': trim_count,
            'cut_loss_count': cut_loss_count,
            'reverse_count': reverse_count,
            'exit_count': exit_count,
            'profit_target': self.profit_target,
            'profit_progress': profit_progress,
            'profit_achieved': profit_achieved,
            'protection_mode': protection_mode,
            'peak_balance': self.peak_balance
        }
    
    def get_win_rate(self):
        """Tính tỷ lệ thắng từ win_count và loss_count"""
        total_trades = self.win_count + self.loss_count
        if total_trades == 0:
            return 0.0
        return self.win_count / total_trades

    def update_position_sl_tp_on_mt5(self, ticket, new_sl, new_tp):
        """Update SL/TP for a position on MT5"""
        try:
            import MetaTrader5 as mt5

            if not mt5.initialize():
                logger.error("❌ MT5 initialization failed")
                return False

            # Get position info
            position = mt5.positions_get(ticket=ticket)
            if not position or len(position) == 0:
                logger.error(f"❌ Position {ticket} not found")
                return False

            position = position[0]

            # Prepare SL/TP update request
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "position": ticket,
                "sl": new_sl,
                "tp": new_tp,
                "symbol": position.symbol,
                "magic": position.magic,
                "comment": "AI Trailing Stop"
            }

            # Send order using safe wrapper to avoid None dereference
            result = self._safe_order_send(request)

            if result is None:
                logger.error("❌ MT5 order_send returned None")
                return False

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"❌ MT5 SL/TP update failed: {result.retcode} - {result.comment}")
                return False

            logger.info(f"✅ Updated SL/TP for position {ticket}: SL={new_sl}, TP={new_tp}")
            return True

        except Exception as e:
            logger.error(f"❌ Error updating SL/TP on MT5: {e}")
            return False

    def calculate_smart_sl_tp(self, signal_data, market_data=None):
        """🤖 AI TỰ ĐỘNG TÍNH SL/TP THÔNG MINH
        
        Dựa trên:
        - ATR (Average True Range) - Biến động thị trường
        - Support/Resistance levels - Vùng hỗ trợ/kháng cự
        - Swing High/Low - Đỉnh/đáy gần nhất
        - Market structure - Cấu trúc thị trường
        
        Args:
            signal_data: Dict chứa thông tin signal (action, price, symbol...)
            market_data: Dict chứa dữ liệu thị trường (df, atr, support, resistance...)
        
        Returns:
            dict: {'sl': sl_price, 'tp': tp_price, 'method': 'AI_SMART'}
        """
        try:
            action = signal_data.get('action', 'BUY')
            entry_price = signal_data.get('entry_price') or signal_data.get('price', 0)
            symbol = signal_data.get('symbol', 'GOLD')
            
            if entry_price == 0:
                logger.warning("⚠️ Entry price = 0, không thể tính SL/TP")
                return {'sl': None, 'tp': None, 'method': 'FAILED'}
            
            # === 1. LẤY THÔNG TIN THỊ TRƯỜNG ===
            atr = None
            support = None
            resistance = None
            swing_high = None
            swing_low = None
            
            if market_data:
                atr = market_data.get('atr')
                support = market_data.get('support_level')
                resistance = market_data.get('resistance_level')
                swing_high = market_data.get('last_swing_high')
                swing_low = market_data.get('last_swing_low')
            
            # === 2. TÍNH ATR NẾU KHÔNG CÓ ===
            if atr is None or atr == 0:
                # Default ATR cho GOLD: ~$15-20
                atr = entry_price * 0.005  # 0.5% của giá (khoảng $20 cho GOLD $4000)
                logger.debug(f"📊 Dùng ATR mặc định: {atr:.2f}")
            
            # === 3. TÍNH SL THÔNG MINH ===
            sl_price = None
            sl_method = ""
            
            if action == 'BUY':
                # BUY: SL phía dưới
                candidates = []
                
                # Option 1: Support level (ưu tiên cao nhất)
                if support and support < entry_price:
                    buffer = atr * 0.3  # Buffer 30% ATR dưới support
                    sl_support = support - buffer
                    candidates.append(('SUPPORT', sl_support))
                
                # Option 2: Swing Low gần nhất
                if swing_low and swing_low < entry_price:
                    buffer = atr * 0.2
                    sl_swing = swing_low - buffer
                    candidates.append(('SWING_LOW', sl_swing))
                
                # Option 3: ATR-based (1.5x ATR)
                sl_atr = entry_price - (atr * 1.5)
                candidates.append(('ATR_1.5X', sl_atr))
                
                # Chọn SL gần entry nhất (nhưng không quá xa)
                max_sl_distance = atr * 2.5  # Tối đa 2.5 ATR
                valid_candidates = [(m, p) for m, p in candidates if (entry_price - p) <= max_sl_distance and p > 0]
                
                if valid_candidates:
                    # Chọn SL cao nhất trong các candidates hợp lệ (gần entry nhất)
                    sl_method, sl_price = max(valid_candidates, key=lambda x: x[1])
                else:
                    # Fallback: 1.5 ATR
                    sl_method = 'ATR_FALLBACK'
                    sl_price = entry_price - (atr * 1.5)
            
            else:  # SELL
                # SELL: SL phía trên
                candidates = []
                
                # Option 1: Resistance level
                if resistance and resistance > entry_price:
                    buffer = atr * 0.3
                    sl_resistance = resistance + buffer
                    candidates.append(('RESISTANCE', sl_resistance))
                
                # Option 2: Swing High
                if swing_high and swing_high > entry_price:
                    buffer = atr * 0.2
                    sl_swing = swing_high + buffer
                    candidates.append(('SWING_HIGH', sl_swing))
                
                # Option 3: ATR-based
                sl_atr = entry_price + (atr * 1.5)
                candidates.append(('ATR_1.5X', sl_atr))
                
                # Chọn SL gần entry nhất
                max_sl_distance = atr * 2.5
                valid_candidates = [(m, p) for m, p in candidates if (p - entry_price) <= max_sl_distance and p > 0]
                
                if valid_candidates:
                    # Chọn SL thấp nhất trong candidates (gần entry nhất)
                    sl_method, sl_price = min(valid_candidates, key=lambda x: x[1])
                else:
                    sl_method = 'ATR_FALLBACK'
                    sl_price = entry_price + (atr * 1.5)
            
            # === 4. TÍNH TP THÔNG MINH (R:R 1:2 hoặc theo resistance/support) ===
            tp_price = None
            tp_method = ""
            
            if action == 'BUY':
                # BUY: TP phía trên
                sl_distance = entry_price - sl_price
                
                # Option 1: Resistance level (nếu có)
                if resistance and resistance > entry_price:
                    potential_tp = resistance - (atr * 0.2)  # Buffer trước resistance
                    if potential_tp > entry_price + (sl_distance * 1.5):  # R:R >= 1:1.5
                        tp_price = potential_tp
                        tp_method = 'RESISTANCE'
                
                # Option 2: R:R 1:2
                if not tp_price:
                    tp_price = entry_price + (sl_distance * 2)
                    tp_method = 'RR_2.0'
            
            else:  # SELL
                sl_distance = sl_price - entry_price
                
                # Option 1: Support level
                if support and support < entry_price:
                    potential_tp = support + (atr * 0.2)
                    if potential_tp < entry_price - (sl_distance * 1.5):
                        tp_price = potential_tp
                        tp_method = 'SUPPORT'
                
                # Option 2: R:R 1:2
                if not tp_price:
                    tp_price = entry_price - (sl_distance * 2)
                    tp_method = 'RR_2.0'
            
            # === 5. VALIDATE & LOG ===
            if sl_price and tp_price:
                sl_distance = abs(entry_price - sl_price)
                tp_distance = abs(tp_price - entry_price)
                rr_ratio = tp_distance / sl_distance if sl_distance > 0 else 0
                
                logger.info("="*70)
                logger.info(f"🤖 AI SMART SL/TP CALCULATED")
                logger.info(f"   Action: {action} @ ${entry_price:.2f}")
                logger.info(f"   ATR: ${atr:.2f}")
                logger.info(f"   SL: ${sl_price:.2f} (Method: {sl_method}, Distance: ${sl_distance:.2f})")
                logger.info(f"   TP: ${tp_price:.2f} (Method: {tp_method}, Distance: ${tp_distance:.2f})")
                logger.info(f"   R:R Ratio: 1:{rr_ratio:.2f}")
                logger.info("="*70)
                
                return {
                    'sl': sl_price,
                    'tp': tp_price,
                    'method': f'AI_SMART_{sl_method}_{tp_method}',
                    'rr_ratio': rr_ratio,
                    'atr': atr
                }
            else:
                logger.warning("⚠️ Không thể tính SL/TP thông minh")
                return {'sl': None, 'tp': None, 'method': 'FAILED'}
        
        except Exception as e:
            logger.error(f"❌ Error in calculate_smart_sl_tp: {e}")
            return {'sl': None, 'tp': None, 'method': 'ERROR'}
    
    def _update_sl_on_mt5(self, ticket, new_sl, current_tp=None):
        """Update SL on MT5 position"""
        if not MT5_AVAILABLE or not self.mt5_enabled:
            return False
        
        try:
            if not mt5.initialize():
                logger.error("❌ MT5 not initialized")
                return False
            
            # Get position info
            positions = mt5.positions_get(ticket=ticket)
            if not positions or len(positions) == 0:
                logger.warning(f"⚠️ Position #{ticket} not found on MT5")
                return False
            
            pos = positions[0]
            symbol = pos.symbol
            
            # Normalize SL/TP
            digits = mt5.symbol_info(symbol).digits
            normalized_sl = round(new_sl, digits)
            normalized_tp = round(current_tp, digits) if current_tp else pos.tp
            
            # Modify position
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": symbol,
                "position": ticket,
                "sl": normalized_sl,
                "tp": normalized_tp
            }
            
            result = mt5.order_send(request)
            
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ MT5 SL updated: #{ticket} SL → {normalized_sl}")
                return True
            else:
                logger.error(f"❌ MT5 SL update failed: #{ticket} - {result.comment}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Exception updating SL on MT5: {e}\n{traceback.format_exc()}")
            return False

#==============================================================================
# 4. 🛡️ DRAWDOWN PROTECTOR - BẢO VỆ VỐN
#==============================================================================

class DrawdownProtector:
    """Hệ thống bảo vệ vốn thông minh
    
    Chức năng:
    - Monitor drawdown realtime
    - Pause trading khi DD quá lớn
    - Giảm lot size khi DD cảnh báo
    - Gửi alerts qua multiple channels
    - Auto resume khi recovery
    """
    
    def __init__(self,
                 initial_balance=10000.0,
                 max_dd_percent=20.0,          # Stop trading @ 20% DD
                 warning_dd_percent=10.0,       # Reduce size @ 10% DD
                 critical_dd_percent=15.0,      # Alert @ 15% DD
                 lot_reduction_factor=0.5,      # Giảm 50% lot
                 auto_resume_recovery=5.0):     # Resume khi recovery 5% từ bottom
        
        self.initial_balance = initial_balance
        self.peak_balance = initial_balance
        self.current_balance = initial_balance
        self.max_dd_percent = max_dd_percent
        self.warning_dd_percent = warning_dd_percent
        self.critical_dd_percent = critical_dd_percent
        self.lot_reduction_factor = lot_reduction_factor
        self.auto_resume_recovery = auto_resume_recovery
        
        self.is_trading_paused = False
        self.is_lot_reduced = False
        self.max_dd_reached = 0.0
        self.bottom_balance = initial_balance
        
        # History
        self.dd_history = []
        self.alert_sent = {
            'warning': False,
            'critical': False,
            'max': False
        }
        
        logger.info("🛡️ Drawdown Protector initialized")
        logger.info(f"   Initial balance: ${initial_balance:,.2f}")
        logger.info(f"   Warning DD: {warning_dd_percent}% (reduce lot size)")
        logger.info(f"   Critical DD: {critical_dd_percent}% (alert)")
        logger.info(f"   Max DD: {max_dd_percent}% (pause trading)")
        logger.info(f"   Auto resume: Recovery {auto_resume_recovery}% from bottom")
    
    def update_balance(self, new_balance):
        """Cập nhật balance và check drawdown"""
        self.current_balance = new_balance
        
        # Update peak
        if new_balance > self.peak_balance:
            self.peak_balance = new_balance
            logger.debug(f"📈 New peak balance: ${self.peak_balance:,.2f}")
            
            # Reset alerts when new peak
            self.alert_sent = {
                'warning': False,
                'critical': False,
                'max': False
            }
        
        # Update bottom (for recovery calculation)
        if new_balance < self.bottom_balance:
            self.bottom_balance = new_balance
        
        # Calculate drawdown
        dd_percent = self.calculate_drawdown()
        
        # Update max DD
        if dd_percent > self.max_dd_reached:
            self.max_dd_reached = dd_percent
        
        # Check và trigger actions
        status = self.check_drawdown_level(dd_percent)
        
        # Save history
        self.dd_history.append({
            'timestamp': datetime.now(),
            'balance': new_balance,
            'peak': self.peak_balance,
            'dd_percent': dd_percent,
            'status': status
        })
        
        return status
    
    def calculate_drawdown(self):
        """Tính drawdown % từ peak"""
        if self.peak_balance == 0:
            return 0.0
        
        dd = (self.peak_balance - self.current_balance) / self.peak_balance * 100
        return max(0.0, dd)
    
    def calculate_recovery(self):
        """Tính % recovery từ bottom"""
        if self.bottom_balance == 0:
            return 0.0
        
        recovery = (self.current_balance - self.bottom_balance) / self.bottom_balance * 100
        return max(0.0, recovery)
    
    def check_drawdown_level(self, dd_percent):
        """Kiểm tra mức độ DD và trigger actions"""
        
        # 1. MAX DD - PAUSE TRADING
        if dd_percent >= self.max_dd_percent:
            if not self.is_trading_paused:
                self.pause_trading()
                self._send_alert('max', dd_percent)
            return 'PAUSED'
        
        # 2. CRITICAL DD - ALERT ONLY
        elif dd_percent >= self.critical_dd_percent:
            if not self.alert_sent['critical']:
                self._send_alert('critical', dd_percent)
            
            if not self.is_lot_reduced:
                self.reduce_lot_size()
            return 'CRITICAL'
        
        # 3. WARNING DD - REDUCE LOT SIZE
        elif dd_percent >= self.warning_dd_percent:
            if not self.alert_sent['warning']:
                self._send_alert('warning', dd_percent)
            
            if not self.is_lot_reduced:
                self.reduce_lot_size()
            return 'WARNING'
        
        # 4. OK - Check auto resume
        else:
            # Auto resume if recovered enough
            if self.is_trading_paused:
                recovery = self.calculate_recovery()
                if recovery >= self.auto_resume_recovery:
                    self.resume_trading()
                    logger.info(f"✅ Auto resumed - Recovery {recovery:.1f}% from bottom")
            
            # Reset lot reduction if DD back to normal
            if self.is_lot_reduced and dd_percent < self.warning_dd_percent / 2:
                self.restore_lot_size()
            
            return 'OK'
    
    def pause_trading(self):
        """Tạm dừng trading"""
        self.is_trading_paused = True
        dd = self.calculate_drawdown()
        
        logger.warning("="*80)
        logger.warning("🚨 DRAWDOWN PROTECTION ACTIVATED!")
        logger.warning(f"   Current DD: {dd:.2f}% (Max: {self.max_dd_percent}%)")
        logger.warning(f"   Balance: ${self.current_balance:,.2f} (Peak: ${self.peak_balance:,.2f})")
        logger.warning(f"   Loss: ${self.peak_balance - self.current_balance:,.2f}")
        logger.warning("   ⏸️ TRADING PAUSED - Protecting your capital")
        logger.warning("="*80)
    
    def resume_trading(self):
        """Tiếp tục trading"""
        self.is_trading_paused = False
        self.bottom_balance = self.current_balance  # Reset bottom
        
        logger.info("="*80)
        logger.info("✅ TRADING RESUMED")
        logger.info(f"   Recovery successful")
        logger.info(f"   Current balance: ${self.current_balance:,.2f}")
        logger.info("="*80)
    
    def reduce_lot_size(self):
        """Giảm lot size"""
        self.is_lot_reduced = True
        dd = self.calculate_drawdown()
        
        logger.warning("⚠️ DRAWDOWN WARNING - LOT SIZE REDUCED")
        logger.warning(f"   DD: {dd:.2f}% → Reducing lot size to {self.lot_reduction_factor*100:.0f}%")
    
    def restore_lot_size(self):
        """Khôi phục lot size bình thường"""
        self.is_lot_reduced = False
        logger.info("✅ Drawdown normalized - Lot size restored to 100%")
    
    def get_lot_multiplier(self):
        """Lấy multiplier cho lot size"""
        if self.is_lot_reduced:
            return self.lot_reduction_factor
        return 1.0
    
    def can_open_trade(self):
        """Kiểm tra có thể mở lệnh mới không"""
        if self.is_trading_paused:
            logger.warning("⚠️ Trading paused due to drawdown - Cannot open new trades")
            return False
        return True
    
    def _send_alert(self, level, dd_percent):
        """Gửi alert (placeholder for Telegram/Email integration)"""
        self.alert_sent[level] = True
        
        messages = {
            'warning': f"⚠️ WARNING: Drawdown {dd_percent:.1f}% - Lot size reduced",
            'critical': f"🚨 CRITICAL: Drawdown {dd_percent:.1f}% - Review positions!",
            'max': f"🛑 MAX DD: Drawdown {dd_percent:.1f}% - Trading PAUSED!"
        }
        
        message = messages.get(level, '')
        logger.warning(message)
        
        # TODO: Integrate Telegram/Email/SMS here
        # self.telegram_bot.send_message(message)
        # self.email_sender.send_alert(message)
    
    def get_status(self):
        """Lấy status hiện tại"""
        dd = self.calculate_drawdown()
        recovery = self.calculate_recovery()
        
        return {
            'current_balance': self.current_balance,
            'peak_balance': self.peak_balance,
            'drawdown_percent': dd,
            'drawdown_amount': self.peak_balance - self.current_balance,
            'max_dd_reached': self.max_dd_reached,
            'recovery_percent': recovery,
            'is_paused': self.is_trading_paused,
            'is_lot_reduced': self.is_lot_reduced,
            'lot_multiplier': self.get_lot_multiplier(),
            'can_trade': self.can_open_trade()
        }
    
    def print_status(self):
        """In status đẹp"""
        status = self.get_status()
        dd = status['drawdown_percent']
        
        print("\n" + "="*80)
        print("🛡️ DRAWDOWN PROTECTION STATUS")
        print("="*80)


class RiskAI:
    """Risk AI PRO - centralized risk decisioning module

    Implements the 10 mechanisms described by the user:
      1) Dynamic lot sizing
      2) Daily max loss
      3) Max consecutive losses
      4) Volatility-aware SL/TP guidance (helper)
      5) Spread protection
      6) News protection
      7) Trend quality check
      8) Confidence threshold
      9) Smart recovery (gentle increase after loss)
     10) Account protection mode (SUPER_SAFE_MODE)
    """

    def __init__(self, money_manager: 'AIMoneyManager' = None, drawdown_protector: 'DrawdownProtector' = None,
                 normal_spread=0.5):
        self.money_manager = money_manager
        self.drawdown_protector = drawdown_protector
        self.normal_spread = float(normal_spread)

        # Track consecutive losses locally for quick access
        self._consecutive_losses = 0

        # Daily loss tracking (reset at midnight)
        self.daily_loss_date = datetime.utcnow().date()
        self.daily_loss_amount = 0.0

        # Pause state for long stops (e.g. 24h stop)
        self.pause_until = None

        # Account lock flag (for >10% lock)
        self.account_locked = False

        # Lightweight evaluate() parameters (merged from RiskAIPro)
        self.max_daily_loss = 0.05      # 5%
        self.max_consecutive_loss = 6
        self.max_volatility_risk = 0.75

        logger.info("🛡️ RiskAI initialized (PRO)")

    def _reset_daily_if_needed(self):
        today = datetime.utcnow().date()
        if today != self.daily_loss_date:
            self.daily_loss_date = today
            self.daily_loss_amount = 0.0

    def observe_trade_result(self, pnl: float):
        """Feed trade PnL to RiskAI so it can update daily loss and consecutive losses."""
        self._reset_daily_if_needed()
        if pnl < 0:
            self._consecutive_losses += 1
            self.daily_loss_amount += abs(pnl)
        else:
            self._consecutive_losses = 0

        # Enforce absolute account lock if drawdown too big (money_manager keeps balance)
        try:
            if self.money_manager and self.money_manager.current_balance is not None:
                start_balance = self.money_manager.initial_balance
                curr = self.money_manager.current_balance
                if start_balance > 0 and ((start_balance - curr) / start_balance) >= 0.10:
                    self.account_locked = True
                    logger.warning("🛑 RiskAI: Account locked due to >=10% loss")
        except Exception:
            pass

    def get_consecutive_losses(self):
        # Prefer local counter, but fallback to money_manager trade history
        if self._consecutive_losses > 0:
            return self._consecutive_losses
        try:
            if self.money_manager and len(self.money_manager.trade_history) > 0:
                # Count last consecutive negative trades
                count = 0
                for t in reversed(self.money_manager.trade_history[-20:]):
                    if t.get('pnl', 0) < 0:
                        count += 1
                    else:
                        break
                return count
        except Exception:
            pass
        return 0

    def calculate_dynamic_lot(self, volatility, confidence, dd, trend_quality=None, win_rate=0.5):
        """Compute dynamic lot based on several inputs.

        Returns a lot size between 0.01 and 0.05 per user rules.
        """
        # Base lot depends on account size: keep small absolute sizes for safety
        base = 0.02

        # Volatility: higher vol -> smaller lot
        vol_factor = 1.0
        try:
            vol_val = float(volatility.get('std_dev', volatility.get('volatility', 0.02))) if isinstance(volatility, dict) else float(volatility or 0.02)
            if vol_val > 0.05:
                vol_factor *= 0.6
            elif vol_val > 0.03:
                vol_factor *= 0.8
            else:
                vol_factor *= 1.0
        except Exception:
            vol_factor *= 1.0

        # Confidence and trend quality: higher -> increase lot
        conf_factor = 1.0 + max(0.0, (confidence - 0.7))  # small bump above 0.7
        tq_factor = 1.0
        try:
            if trend_quality is not None:
                if trend_quality > 1.5:
                    tq_factor = 1.3
                elif trend_quality > 1.2:
                    tq_factor = 1.15
                else:
                    tq_factor = 1.0
        except Exception:
            tq_factor = 1.0

        # Win rate: reward good win rate with slightly larger lot
        wr_factor = 1.0
        try:
            if win_rate >= 0.6:
                wr_factor = 1.15
            elif win_rate >= 0.5:
                wr_factor = 1.05
            else:
                wr_factor = 0.95
        except Exception:
            wr_factor = 1.0

        # Drawdown: penalize lot when drawdown grows
        dd_factor = 1.0
        try:
            if dd >= 0.10:
                dd_factor = 0.5
            elif dd >= 0.06:
                dd_factor = 0.7
            elif dd >= 0.03:
                dd_factor = 0.85
        except Exception:
            dd_factor = 1.0

        lot = base * vol_factor * conf_factor * tq_factor * wr_factor * dd_factor

        # Boundaries per spec
        lot = max(DEFAULT_MIN_LOT, min(0.05, lot))
        # Round to 0.002 increments for nicer sizing
        lot = round(lot, 3)
        return lot

    def smart_recovery_lot(self, last_lot):
        """Slightly increase lot after a loss (non-martingale)."""
        # Example rule: increase by 40% but cap at 1.4x and at 0.05
        new_lot = min(0.05, round(last_lot * 1.4, 3))
        return max(DEFAULT_MIN_LOT, new_lot)

    def assess(self, signal_confidence, vol=None, spread=None, consecutive_losses=None,
               dd=0.0, news_level=0, trend_quality=None, win_rate=0.5, normal_spread=None):
        """Main decision function.

        Returns a dict with keys: status (TRADE_OK/NO_TRADE/STOP_24H/LOCKED), lot, mode, reason
        """
        now = datetime.utcnow()
        # Respect global pause
        if self.pause_until and now < self.pause_until:
            return {'status': 'STOP_24H', 'lot': 0.0, 'mode': 'PAUSED', 'reason': 'pause_until'}

        # 1) Account locked guard
        if self.account_locked:
            return {'status': 'LOCKED', 'lot': 0.0, 'mode': 'LOCKED', 'reason': 'account_locked'}

        # 2) News protection
        try:
            if news_level is not None and int(news_level) >= 2:
                logger.info("🚫 RiskAI: Blocking trade due to strong news")
                return {'status': 'NO_TRADE', 'lot': 0.0, 'mode': 'NEWS_BLOCK', 'reason': 'news'}
        except Exception:
            pass

        # 3) Spread protection
        try:
            s = spread if spread is not None else 0.0
            ns = normal_spread if normal_spread is not None else self.normal_spread
            if s and ns and s > 2.0 * ns:
                logger.info(f"🚫 RiskAI: Blocking trade due to wide spread ({s} > {2.0*ns})")
                return {'status': 'NO_TRADE', 'lot': 0.0, 'mode': 'SPREAD', 'reason': 'spread'}
        except Exception:
            pass

        # 4) Consecutive loss protection
        try:
            cl = consecutive_losses if consecutive_losses is not None else self.get_consecutive_losses()
            if cl >= 5:
                # Pause 24 hours
                self.pause_until = now + timedelta(hours=24)
                logger.warning("🚫 RiskAI: 5 consecutive losses - pausing 24h")
                return {'status': 'STOP_24H', 'lot': 0.0, 'mode': 'STOP_24H', 'reason': 'consecutive_losses'}
            if cl >= 3:
                # Reduce lot aggressively
                lot = DEFAULT_MIN_LOT
                return {'status': 'TRADE_OK', 'lot': lot, 'mode': 'LOSS_PROTECTION', 'reason': '3+ losses'}
        except Exception:
            pass

        # 5) Drawdown & daily max loss protections
        try:
            # daily_loss is tracked internally by observe_trade_result
            self._reset_daily_if_needed()
            if self.daily_loss_amount >= (0.03 * (self.money_manager.initial_balance if self.money_manager else 1)):
                # Reduce lot
                logger.warning("⚠️ RiskAI: Daily loss >= 3% - reducing lot")
                return {'status': 'TRADE_OK', 'lot': DEFAULT_MIN_LOT, 'mode': 'DAILY_LOSS_REDUCE', 'reason': 'daily_loss_3pct'}

            # Stop trading at 6% daily loss
            if self.daily_loss_amount >= (0.06 * (self.money_manager.initial_balance if self.money_manager else 1)):
                logger.warning("🛑 RiskAI: Daily loss >= 6% - stopping trading for today")
                return {'status': 'NO_TRADE', 'lot': 0.0, 'mode': 'DAILY_STOP', 'reason': 'daily_loss_6pct'}

            # Full account lock handled elsewhere (>=10%)
        except Exception:
            pass

        # 6) Confidence threshold
        try:
            if signal_confidence is None or signal_confidence < 0.70:
                return {'status': 'NO_TRADE', 'lot': 0.0, 'mode': 'LOW_CONFIDENCE', 'reason': 'confidence'}
        except Exception:
            return {'status': 'NO_TRADE', 'lot': 0.0, 'mode': 'LOW_CONFIDENCE', 'reason': 'confidence_error'}

        # 7) Trend quality check (if provided)
        try:
            if trend_quality is not None and trend_quality < 0.8:
                # reduce or avoid trading when trend weak
                logger.info("⚠️ RiskAI: Weak trend quality - reducing lot or skipping")
                # small lot but still trade if confidence strong
                if signal_confidence >= 0.85:
                    lot = DEFAULT_MIN_LOT
                    return {'status': 'TRADE_OK', 'lot': lot, 'mode': 'WEAK_TREND_ALLOW_SMALL', 'reason': 'trend_quality'}
                else:
                    return {'status': 'NO_TRADE', 'lot': 0.0, 'mode': 'WEAK_TREND_BLOCK', 'reason': 'trend_quality'}
        except Exception:
            pass

        # 8) Smart dynamic lot sizing
        try:
            lot = self.calculate_dynamic_lot(vol or {}, float(signal_confidence), float(dd or 0.0), trend_quality, win_rate)
        except Exception:
            lot = 0.02

        # 9) Smart recovery: if most recent trade lost, slightly increase lot (non-martingale)
        try:
            if self.get_consecutive_losses() >= 1:
                # gentle bump
                lot = min(0.05, round(lot * 1.2, 3))
        except Exception:
            pass

        # 10) Account protection mode
        try:
            if dd and dd >= 0.15:
                # SUPER SAFE MODE
                return {'status': 'TRADE_OK', 'lot': DEFAULT_MIN_LOT, 'mode': 'SUPER_SAFE', 'reason': 'drawdown_15pct'}
        except Exception:
            pass

        return {'status': 'TRADE_OK', 'lot': lot, 'mode': 'NORMAL', 'reason': 'ok'}

    def evaluate(self,
                 volatility_level,
                 trend_strength,
                 sideway_score,
                 liquidity_risk,
                 structure_score,
                 confidence):
        """Lightweight risk check (backwards-compatible with previous RiskAIPro).

        Returns: (allowed: bool, risk_level: float 0..1)
        """
        risk = 0.0

        # Volatility
        try:
            if volatility_level == "HIGH":
                risk += 0.25
            elif volatility_level == "EXTREME":
                risk += 0.45
        except Exception:
            pass

        # Weak trend -> higher risk
        try:
            if trend_strength is None or float(trend_strength) < 0.3:
                risk += 0.20
        except Exception:
            pass

        # Sideways increases risk
        try:
            risk += float(sideway_score or 0.0) * 0.40
        except Exception:
            pass

        # Liquidity risk
        try:
            risk += float(liquidity_risk or 0.0) * 0.25
        except Exception:
            pass

        # Structure instability
        try:
            bs = float(structure_score.get('bullish', 0.0))
            be = float(structure_score.get('bearish', 0.0))
            risk += abs(bs - be) * 0.15
        except Exception:
            pass

        # Low AI confidence increases risk
        try:
            if confidence is None or float(confidence) < 0.35:
                risk += 0.25
        except Exception:
            pass

        risk_level = min(1.0, float(risk))
        allowed = risk_level < float(self.max_volatility_risk)

        return bool(allowed), float(risk_level)

