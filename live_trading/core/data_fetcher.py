"""
Market Data Fetcher Module
Fetch and preprocess market data from MT5
"""

import os
import logging
import pandas as pd

logger = logging.getLogger(__name__)

# Check MT5 availability
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logger.warning("⚠️ MetaTrader5 library not available")


class MarketDataFetcher:
    """Data fetching và preprocessing cho 5M XAUUSD"""
    
    def __init__(self, symbol='GOLD', use_mt5=True):  # Đổi thành GOLD cho XM broker
        # Allow overriding default symbol via environment variable (no logic change)
        env_sym = os.environ.get('AI_SYMBOL') or os.environ.get('SYMBOL')
        if env_sym:
            self.symbol = env_sym
            logger.info(f"🔧 Symbol override from env: {self.symbol}")
        else:
            self.symbol = symbol
        self.data_cache = {}
        self.use_mt5 = use_mt5 and MT5_AVAILABLE
        self.mt5_initialized = False
        
        # Khởi tạo kết nối MT5
        if self.use_mt5:
            self._initialize_mt5()
        
    # ❌ KHÔNG CÓ DEMO DATA - CHỈ DÙNG DỮ LIỆU THẬT TỪ MT5
    # generate_demo_data() đã bị xóa - Bot chỉ học từ thị trường thật
    
    def _initialize_mt5(self):
        """Khởi tạo kết nối MT5"""
        try:
            if not mt5.initialize():
                logger.warning(f"⚠️ MT5 initialization failed: {mt5.last_error()}")
                self.use_mt5 = False
                return False
            
            # Kiểm tra kết nối
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("❌ MT5 không kết nối - Không thể lấy dữ liệu thật!")
                self.use_mt5 = False
                return False
                
            self.mt5_initialized = True
            logger.info(f"✅ MT5 connected - Account: {account_info.login}, Server: {account_info.server}")
            
            # --- Auto-detect broker-specific symbol name for XAU/GOLD ---
            try:
                import re

                found = None
                # First try a short explicit list (prefer VT variants)
                explicit = [
                    self.symbol,
                    # XAU/GOLD variants
                    'XAUUSC-VIPc','XAUUSC','XAUUSC-VIPC','XAUUSD-VIPc','XAUUSD','GOLD','XAU',
                    # BTC aliases commonly used by brokers
                    'BTCUSD','BTCUSDm','XBTUSD','XBTUSD.m','BTCUSDM'
                ]
                for cand in explicit:
                    if not cand:
                        continue
                    try:
                        info = mt5.symbol_info(cand)
                    except Exception:
                        info = None
                    if info is not None:
                        try:
                            mt5.symbol_select(cand, True)
                        except Exception:
                            pass
                        found = cand
                        break

                # If not found yet, scan all symbols for XAU/GOLD-like names
                if not found:
                    avail = []
                    try:
                        all_syms = mt5.symbols_get()
                        if all_syms:
                            for s in all_syms:
                                # mt5.SymbolInfo has 'name' attribute sometimes, fall back to 'symbol'
                                name = getattr(s, 'name', None) or getattr(s, 'symbol', None)
                                if not name:
                                    continue
                                up = name.upper()
                                if re.search(r'XAU|GOLD', up):
                                    avail.append(name)
                    except Exception:
                        avail = []

                    if avail:
                        # prefer VT-like variants first
                        pref = None
                        for a in avail:
                            ua = a.upper()
                            if 'XAUUSC' in ua or 'VIP' in ua or 'XAUUSD' in ua:
                                pref = a
                                break
                        if not pref:
                            pref = avail[0]

                        try:
                            mt5.symbol_select(pref, True)
                        except Exception:
                            pass
                        found = pref
                        logger.info(f"🔎 Symbols on broker matching XAU/GOLD: {avail}")
                        logger.info(f"🔎 Chosen symbol: {found}")
                    else:
                        logger.error("⚠️ Không tìm thấy symbol liên quan đến XAU/GOLD trên broker. Vui lòng thêm symbol vào Market Watch hoặc kiểm tra tên symbol chính xác.")

                if found:
                    if found != self.symbol:
                        logger.info(f"🔎 Auto-detected symbol for XAU/GOLD: {found} (using instead of '{self.symbol}')")
                    self.symbol = found

            except Exception as e:
                logger.warning(f"⚠️ Auto-detect symbol for XAU failed: {e}")
            return True
            
        except Exception as e:
            logger.error(f"❌ MT5 connection error: {e} - Không thể lấy dữ liệu thật!")
            self.use_mt5 = False
            return False
    
    def fetch_mt5_data(self, symbol=None, timeframe=None, bars=1000):
        """Lấy dữ liệu thật từ MT5"""
        try:
            if not MT5_AVAILABLE:
                return None
            
            if not self.mt5_initialized:
                logger.error("❌ MT5 chưa khởi tạo - Không thể lấy dữ liệu thật!")
                return None
            
            # Sử dụng timeframe mặc định nếu không có
            if timeframe is None:
                timeframe = mt5.TIMEFRAME_H1  # 🎯 Phân tích trên 1H cho chính xác
            
            # Use instance symbol if not provided
            if symbol is None:
                symbol = self.symbol
            # Lấy dữ liệu từ MT5
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
            
            if rates is None or len(rates) == 0:
                logger.warning(f"⚠️ No data from MT5 for {symbol}")
                return None
            
            # Chuyển đổi sang DataFrame
            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'tick_volume']]
            df.rename(columns={'tick_volume': 'volume'}, inplace=True)
            df.set_index('timestamp', inplace=True)
            
            logger.info(f"✅ Fetched {len(df)} bars from MT5 for {symbol}")
            try:
                # visual separator after fetching data
                if hasattr(logger, 'sep'):
                    logger.sep(f"NEW COMMAND: FETCHED {len(df)} BARS FROM MT5 for {symbol}")
            except Exception:
                pass
            return df
            
        except Exception as e:
            logger.error(f"❌ Error fetching MT5 data: {e}")
            return None
    
    def fetch_live_data(self, symbol=None, periods=100):
        """Fetch REAL market data from MT5 ONLY - NO DEMO FALLBACK"""
        if not MT5_AVAILABLE:
            logger.error("❌ MT5 library không khả dụng - Không thể lấy dữ liệu thật!")
            raise RuntimeError("MT5 library required for real data")
        
        if not self.use_mt5 or not self.mt5_initialized:
            logger.error("❌ MT5 chưa được khởi tạo - Không thể lấy dữ liệu thật!")
            raise RuntimeError("MT5 must be initialized to fetch real data")
        
        # Use instance symbol if not provided
        if symbol is None:
            symbol = self.symbol

        # CHỈ LẤY DỮ LIỆU THẬT TỪ MT5
        df = self.fetch_mt5_data(symbol, mt5.TIMEFRAME_H1, periods)  # 🎯 Live data trên 1H
        
        if df is None or len(df) == 0:
            logger.error(f"❌ Không thể lấy dữ liệu từ MT5 cho {symbol}!")
            logger.error("💡 Kiểm tra:")
            logger.error("   1. MT5 có đang chạy?")
            logger.error("   2. Symbol GOLD có tồn tại?")
            logger.error("   3. Dữ liệu lịch sử đã tải xong?")
            raise RuntimeError(f"Failed to fetch real data from MT5 for {symbol}")
        
        logger.debug(f"✅ Lấy được {len(df)} bars dữ liệu THẬT từ MT5")
        return df
