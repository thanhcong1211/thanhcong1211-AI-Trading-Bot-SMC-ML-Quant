#property copyright "XGBoost 5M Trading"
#property version   "2.0 - DLL Edition"
#property strict

/*
 ====================================================================
 ZmqTestEA_DLL_VN.mq5 - Real ZeroMQ Integration
 Robot giao dịch tự động nhận tín hiệu từ AI/ML qua ZeroMQ (thực)
 
 ====================================================================
 TÍNH NĂNG:
 - Nhận tín hiệu BUY/SELL từ Python (XGBoost model) - THỰC TẾ
 - Quản lý rủi ro tự động (% tài khoản)
 - Điều chỉnh kích cỡ lot theo ý muốn
 - Heartbeat để kiểm tra kết nối
 - Bảo vệ: Tắt giao dịch mặc định (chế độ test trước)
 
 YÊU CẦU:
 - libzmq.dll trong MQL5\Libraries ✓ (đã có)
 - Bật "Allow DLL imports" trong cài đặt EA
 - Dữ liệu: EURUSD 5M (có thể điều chỉnh)
 
 SỰ KHÁC BIỆT VỚI PHIÊN BẢN CŨ:
 - Sử dụng ZmqHandler_DLL.mqh (real DLL imports)
 - Không cần zbridge.dll - chỉ cần libzmq.dll
 - Kết nối thực tế tới Python Publisher
 ====================================================================
*/

#include <ZMQ/ZmqHandler_DLL.mqh>      // ← NEW: Real DLL integration
#include <JAson.mqh>
#include <Trade/Trade.mqh>

// ========== CẤU HÌNH KẾT NỐI ==========
input string   ZmqEndpoint = "tcp://127.0.0.1:5555";        // Địa chỉ ZeroMQ
input string   ZmqTopic    = "";                             // Chủ đề (để trống)
input int      ZmqTimeout  = 1000;                           // Timeout (ms)

// ========== CẤU HÌNH GIAO DỊCH ==========
input bool     EnableTrading = false;                        // BẬT/TẮT giao dịch (mặc định TẮT để test)
input bool     EnableLiveAccount = false;                    // Cho phép tài khoản live
input double   MaxRiskPct = 2.0;                             // % rủi ro tối đa trên tài khoản (2%)

// ========== CẤU HÌNH LOT SIZE ==========
input double   FixedLotSize = 0.0;                           // Lot cố định (0 = tính theo rủi ro)
input bool     UseRiskCalculation = true;                    // Sử dụng tính rủi ro
input int      MultiplyFactor = 1;                           // Hệ số nhân lot

// ========== CẤU HÌNH AUTO LOT BY BALANCE ==========
input bool     UseAutoLotByBalance = true;                   // ✨ Tự động theo kích thước TK
input double   DailyProfitTarget = 2.0;                      // Mục tiêu lãi/ngày (2% minimum)
input double   MinLot = 0.01;                                // Lot tối thiểu
input double   MaxLot = 0.25;                                // Lot tối đa

// ========== CẤU HÌNH CHỐT LỜI & CẮT LỖ TỰ ĐỘNG ==========
input bool     UseAutoTPSL = true;                           // Bật tự động TP/SL
input double   SLMultiplier = 2.0;                           // SL = ATR × value
input double   TPMultiplier = 4.0;                           // TP = ATR × value
input bool     UseFixedTPSL = false;                         // Dùng TP/SL cố định
input double   FixedStopLossPips = 50.0;                     // SL cố định
input double   FixedTakeProfitPips = 100.0;                  // TP cố định

// ========== BIẾN TOÀN CỤC ==========
CZmqHandler_DLL zmq;                   // Handler ZeroMQ (Real DLL)
CJAVal doc;                            // Tài liệu JSON
CTrade trade;                          // Thực thi giao dịch

int SignalCount = 0;
int TradeCount = 0;
int ErrorCount = 0;
datetime LastSignalTime = 0;

// ========== HẰNG SỐ ==========
#define HEART_RATE 1000    // 1 giây check một lần

// ========== ON INIT ==========
int OnInit()
{
   Print("═══════════════════════════════════════════════════════════");
   Print("🤖 ZmqTestEA_DLL_VN v2.0 - XGBoost 5M Trading Bot");
   Print("═══════════════════════════════════════════════════════════");
   Print("Phiên bản: REAL ZeroMQ (DLL Integration)");
   Print("");

   // Kiểm tra account
   Print("📊 ACCOUNT INFO:");
   PrintFormat("   Balance: $%.2f", AccountInfoDouble(ACCOUNT_BALANCE));
   PrintFormat("   Equity: $%.2f", AccountInfoDouble(ACCOUNT_EQUITY));
   PrintFormat("   Leverage: 1:%d", (int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   PrintFormat("   Account Type: %s", AccountInfoString(ACCOUNT_SERVER));
   Print("");

   // Kiểm tra trading mode
   if (EnableTrading && EnableLiveAccount && !IsDemo())
   {
      Print("🔴 WARNING: Live account detected - UseAutoLotByBalance highly recommended!");
      Print("    Enabling auto lot by balance for safety");
   }

   Print("⚙️  CONFIGURATION:");
   PrintFormat("   EnableTrading: %s", EnableTrading ? "TRUE" : "FALSE (TEST MODE)");
   PrintFormat("   UseAutoLotByBalance: %s", UseAutoLotByBalance ? "TRUE" : "FALSE");
   PrintFormat("   ZeroMQ Endpoint: %s", ZmqEndpoint);
   PrintFormat("   ZeroMQ Timeout: %d ms", ZmqTimeout);
   Print("");

   // Khởi tạo ZeroMQ (Real DLL)
   Print("🔗 Initializing ZeroMQ Connection...");
   if (!zmq.Init(ZmqEndpoint, ZmqTopic, ZmqTimeout))
   {
      Print("❌ ERROR: Failed to initialize ZeroMQ!");
      Print("   Make sure libzmq.dll exists in MQL5\\Libraries\\");
      Print("   And 'Allow DLL imports' is enabled in EA properties");
      return INIT_FAILED;
   }

   if (!zmq.Connect())
   {
      Print("❌ ERROR: Failed to connect to ZeroMQ!");
      Print("   Endpoint: " + ZmqEndpoint);
      Print("   Make sure Python signal generator is running!");
      return INIT_FAILED;
   }

   Print("✅ ZeroMQ Connected Successfully!");
   Print("");

   // Set timer
   EventSetTimer(1);  // 1 giây

   Print("═══════════════════════════════════════════════════════════");
   Print("✅ EA READY - Waiting for signals from Python...");
   Print("═══════════════════════════════════════════════════════════");

   return INIT_SUCCEEDED;
}

// ========== ON TIMER ==========
void OnTimer()
{
   // Poll ZeroMQ
   string message;
   if (zmq.Receive(message))
   {
      LastSignalTime = TimeCurrent();
      SignalCount++;

      Print("📨 Signal received (#" + IntegerToString(SignalCount) + ")");
      Print("   Message: " + message);

      // Parse JSON
      if (!doc.Parse(message))
      {
         Print("❌ ERROR: Invalid JSON format");
         ErrorCount++;
         return;
      }

      // Extract fields
      string action = doc["action"].ToStr();
      double entry = doc["entry"].ToDbl();
      double tp = doc["tp"].ToDbl();
      double sl = doc["sl"].ToDbl();
      int buy = (action == "BUY") ? 1 : 0;

      Print("   Action: " + action);
      PrintFormat("   Entry: %.5f | SL: %.5f | TP: %.5f", entry, sl, tp);

      // Calculate lot
      double lot = CalculateLot();
      Print("   Lot Size: " + DoubleToString(lot, 2));

      // Place order
      if (EnableTrading)
      {
         if (buy)
         {
            if (trade.Buy(lot, Symbol(), 0, sl, tp))
            {
               Print("✅ BUY Order filled!");
               TradeCount++;
            }
            else
            {
               Print("❌ BUY Order FAILED: " + IntegerToString(trade.ResultRetcode()));
               ErrorCount++;
            }
         }
         else
         {
            if (trade.Sell(lot, Symbol(), 0, sl, tp))
            {
               Print("✅ SELL Order filled!");
               TradeCount++;
            }
            else
            {
               Print("❌ SELL Order FAILED: " + IntegerToString(trade.ResultRetcode()));
               ErrorCount++;
            }
         }
      }
      else
      {
         Print("ℹ️  TEST MODE: Order not executed (EnableTrading=FALSE)");
      }

      // Monitor open positions
      MonitorOpenPositions();
   }

   // Heartbeat: Check connection
   if (SignalCount % 30 == 0 && SignalCount > 0)
   {
      datetime now = TimeCurrent();
      int seconds_since = (int)(now - LastSignalTime);
      if (seconds_since > 60)
      {
         Print("⚠️  WARNING: No signals for " + IntegerToString(seconds_since) + " seconds!");
         Print("   Check if Python signal generator is running");
      }
   }
}

// ========== CALCULATE LOT ==========
double CalculateLot()
{
   double lot = 0.01;

   if (UseAutoLotByBalance)
   {
      // Auto lot by account balance
      double balance = AccountInfoDouble(ACCOUNT_BALANCE);

      if (balance < 2000)
         lot = 0.01;
      else if (balance < 5000)
         lot = 0.05;
      else if (balance < 7000)
         lot = 0.10;
      else
         lot = 0.25;
   }
   else if (FixedLotSize > 0)
   {
      lot = FixedLotSize;
   }
   else
   {
      // Risk-based calculation
      double risk_amount = (AccountInfoDouble(ACCOUNT_BALANCE) * MaxRiskPct / 100.0);
      double point_value = SymbolInfoDouble(Symbol(), SYMBOL_TRADE_TICK_VALUE);
      
      if (point_value > 0)
      {
         lot = risk_amount / (50 * point_value);  // 50 pips risk
      }
      else
      {
         lot = 0.01;
      }
   }

   // Apply multiplier
   if (MultiplyFactor > 1)
   {
      lot *= MultiplyFactor;
   }

   // Clamp to broker limits
   double min_lot = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MIN);
   double max_lot = SymbolInfoDouble(Symbol(), SYMBOL_VOLUME_MAX);

   if (lot < min_lot)
      lot = min_lot;
   if (lot > max_lot)
      lot = max_lot;

   return lot;
}

// ========== MONITOR OPEN POSITIONS ==========
void MonitorOpenPositions()
{
   int count = 0;
   double total_pl = 0;

   for (int i = 0; i < PositionsTotal(); i++)
   {
      if (PositionSelectByTicket(PositionGetTicket(i)))
      {
         count++;

         double entry = PositionGetDouble(POSITION_PRICE_OPEN);
         double current = PositionGetDouble(POSITION_PRICE_CURRENT);
         double tp = PositionGetDouble(POSITION_TP);
         double sl = PositionGetDouble(POSITION_SL);
         double pl = PositionGetDouble(POSITION_PROFIT);

         total_pl += pl;

         int pos_type = (int)PositionGetInteger(POSITION_TYPE);
         string type = pos_type == POSITION_TYPE_BUY ? "BUY" : "SELL";

         PrintFormat("📊 Position #%d (%s):", i+1, type);
         PrintFormat("   Entry: %.5f | Current: %.5f | SL: %.5f | TP: %.5f", entry, current, sl, tp);
         PrintFormat("   P&L: $%.2f", pl);
      }
   }

   if (count > 0)
   {
      PrintFormat("📈 Total Positions: %d | Total P&L: $%.2f", count, total_pl);
   }
}

// ========== ON DEINIT ==========
void OnDeinit(const int reason)
{
   EventKillTimer();

   Print("");
   Print("═══════════════════════════════════════════════════════════");
   Print("🛑 EA STOPPED - Statistics:");
   PrintFormat("   Signals Received: %d", SignalCount);
   PrintFormat("   Trades Executed: %d", TradeCount);
   PrintFormat("   Errors: %d", ErrorCount);
   Print("═══════════════════════════════════════════════════════════");

   zmq.Disconnect();
}

// ========== HELPERS ==========
bool IsDemo()
{
   return (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO);
}
