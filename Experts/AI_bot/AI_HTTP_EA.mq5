//+------------------------------------------------------------------+
//| AI_HTTP_EA.mq5 - Complete AI Trading System with VN Features    |
//+------------------------------------------------------------------+
#property copyright "XGBoost 5M Trading - Complete AI System"
#property version   "2.00"
#property strict

/*
 ====================================================================
 AI_HTTP_EA.mq5 - Robot giao dịch AI hoàn chỉnh (Complete AI System)
 Tích hợp: Complete AI Trading System + Tính năng Việt Nam
 ====================================================================
 TÍNH NĂNG:
 - Nhận tín hiệu từ Complete AI Trading System (HTTP + File backup)
 - Quản lý rủi ro tự động theo kích thước tài khoản
 - Tự động điều chỉnh lot size theo balance
 - Theo dõi lợi nhuận hàng ngày (không dừng giao dịch)
 - ATR-based SL/TP calculation
 - Comprehensive logging và monitoring
 ====================================================================
*/

#include <ZMQ/ZmqHandler_FilePolling.mqh>
#include <JAson.mqh>
#include <Trade/Trade.mqh>

// ========== CẤU HÌNH KẾT NỐI HTTP ==========
input string   HttpEndpoint = "http://127.0.0.1:6555";   // Complete AI System HTTP endpoint

// ========== CẤU HÌNH GIAO DỊCH ==========
input bool     EnableTrading = true;                      // BẬT/TẮT giao dịch
input double   RiskPercent = 2.0;                         // % rủi ro mỗi lệnh
input double   MinConfidence = 0.0;                       // Confidence tối thiểu (%) - TẮT FILTER
input int      MaxPositions = 999;                        // UNLIMITED - AI quyết định

// ========== CẤU HÌNH LOT SIZE VÀ QUẢN LÝ RỦI RO ==========
input bool     UseAutoLotByBalance = true;                // ✨ Tự động lot theo balance
input double   FixedLotSize = 0.01;                       // Lot cố định (nếu không dùng auto)
input bool     UseRiskManagement = true;                  // Dùng risk management
input int      MultiplyFactor = 1;                        // Hệ số nhân lot (1x, 2x, 3x...)
input double   MinLot = 0.01;                             // Lot tối thiểu
input double   MaxLot = 1.68;                             // 🔴 Lot tối đa - CÓ THỂ SỬA TÙY Ý (Python AI sẽ tuân theo)

// ========== 🛡️ SMALL ACCOUNT PROTECTION ==========
input bool     EnableSmallAccountProtection = true;       // 🛡️ BẬT bảo vệ tài khoản nhỏ
input double   SmallAccountThreshold = 200.0;             // 🛡️ Ngưỡng TK nhỏ ($)
input int      SmallAccountMaxPositions = 3;              // 🛡️ Max lệnh cho TK nhỏ
input double   SmallAccountRiskReduction = 0.5;           // 🛡️ Giảm risk (50%)

// ========== 🎯 PROFIT TARGET PROTECTION ==========
input bool     EnableProfitTargetProtection = true;      // 🎯 BẬT bảo vệ profit target
input double   MinProfitPercent = 20.0;                   // 🎯 % profit tối thiểu
input double   MinProfitAmount = 10.0;                    // 🎯 $ profit tối thiểu

// ========== 🔄 AUTO CLOSE FEATURES ==========
input bool     EnableAutoTrim = false;                    // 🔄 BẬT auto trim (đóng lỗ bằng lãi) - default: FALSE (AI Python quyết định)
input bool     EnableReverseClose = false;                // 🔄 BẬT đóng lệnh ngược khi reverse - TẮT (AI Python quyết định)

// ========== CẤU HÌNH THEO DÕI LỢI NHUẬN ==========
input bool     EnableDailyProfitTracking = true;          // Theo dõi lợi nhuận hàng ngày
input double   DailyProfitTarget = 2.0;                   // Mục tiêu lãi tối thiểu/ngày (%)
input double   MaxProfitTarget = 200.0;                   // Lãi tối đa theo dõi (%)

// ========== CẤU HÌNH SL/TP ==========
input double   SLMultiplier = 2.0;                        // Hệ số SL (ATR × value)
input double   TPMultiplier = 4.0;                        // Hệ số TP (ATR × value)

// ========== CẤU HÌNH TRAILING STOP & BREAK EVEN ==========
input bool     EnableTrailingStop = true;                  // ✅ BẬT Trailing Stop (30 pips, chỉ tăng không giảm)
input double   TrailingStopPips = 30.0;                   // Trailing Stop (pips) - Khoảng cách SL từ giá (giữ 30 pips lời)
input double   TrailingStepPips = 5.0;                    // Trailing Step (pips) - Bước di chuyển tối thiểu
input double   MinProfitToStartTrailing = 50.0;           // ✅ Min Profit để bắt đầu trailing (pips) - GIỮ 50 cho lệnh thường
input bool     EnableTrailingTP = true;                    // ✅ BẬT Trailing TP (tăng target)
input double   TrailingTPPips = 20.0;                     // Trailing TP Distance (pips)
input bool     EnableBreakEven = true;                     // ✅ BẬT Break Even (Entry + 15 pips)
input double   BreakEvenPips = 40.0;                      // Break Even khi lời (pips) - NORMAL/TREND @ 40 pips
input double   BreakEvenPlusPips = 15.0;                  // BE + thêm (pips) - Entry + 15 pips
input bool     EnablePartialClose = false;                 // BẬT Partial Close - TẮT (AI Python quyết định)
input double   PartialClosePercent = 50.0;                // % đóng khi đạt TP1
input double   PartialTP1Multiplier = 20.0;                // TP1 = ATR × value

// ========== BIẾN TOÀN CỤC ==========
CZmqHandler    zmqHandler;
CTrade         trade;
datetime       lastSignalTime = 0;
int            signalCount = 0;
int            tradeCount = 0;
int            heartbeatCount = 0;                        // Số heartbeat
datetime       lastProfitLogTime = 0;                    // Lần cuối log lợi nhuận

// 🛡️ Small Account Protection
datetime       lastBalanceCheck = 0;                     // Lần cuối check balance
int            balanceScanInterval = 30;                 // Quét balance mỗi 30 giây
double         currentBalance = 0;                       // Balance hiện tại
bool           isSmallAccount = false;                   // TK nhỏ hay không

// 🎯 Profit Target Protection
double         initialBalance = 0;                       // Balance ban đầu
double         peakBalance = 0;                          // Peak balance đạt được
bool           profitTargetAchieved = false;             // Đã đạt profit target chưa

// 🔄 Auto Features
datetime       lastTrimTime = 0;                         // Lần cuối auto trim
int            trimInterval = 300;                       // Auto trim mỗi 5 phút

// ========== 🎯 TRAILING & BREAKEVEN FROM PYTHON SIGNAL ==========
string         g_LastTrailingType = "";                  // Trailing type từ Python
string         g_LastSidewaysType = "";                  // Sideways type (TIGHT/WIDE/TRENDING)
double         g_LastBEPips = 20.0;                      // Breakeven trigger pips
double         g_LastBEOffsetPips = 10.0;                // Breakeven offset pips
bool           g_WideBEApplied = false;                  // Flag: WIDE BE đã chạy chưa
int            lastProcessedSignalId = -1;              // Signal ID cuối xử lý (chống duplicate)
datetime       lastTrailingCheck = 0;                    // Thời gian check trailing cuối
int            trailingCheckInterval = 1;                // Interval check (giây)

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("===============================================================");
   Print("🤖 Robot AI HTTP EA - Hệ thống AI Trading Hoàn chỉnh");
   Print("===============================================================");
   Print("🧠 Hệ thống AI: Complete AI Trading System (Tất cả trong một)");
   Print("📡 Địa chỉ HTTP: ", HttpEndpoint);
   Print("💰 Lot cố định: ", FixedLotSize);
   Print("📊 Quản lý rủi ro: ", UseRiskManagement ? "BẬT" : "TẮT");
   Print("🎯 Độ tin cậy tối thiểu: ", MinConfidence, "%");
   Print("🔒 Số lệnh tối đa: ", MaxPositions);
   Print("⚡ Giao dịch: ", EnableTrading ? "BẬT" : "TẮT");
   Print("🎲 Symbol: ", _Symbol, " (", PeriodSeconds() / 60, "M)");
   
   // 🛡️ Small Account Protection Info
   if(EnableSmallAccountProtection)
   {
      Print("🛡️ SMALL ACCOUNT PROTECTION: ENABLED");
      Print("   Ngưỡng TK nhỏ: $", SmallAccountThreshold);
      Print("   Max lệnh TK nhỏ: ", SmallAccountMaxPositions);
      Print("   Giảm risk: ", SmallAccountRiskReduction * 100, "%");
   }
   
   // 🎯 Profit Target Protection Info
   initialBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   currentBalance = initialBalance;
   peakBalance = initialBalance;
   
   if(EnableProfitTargetProtection)
   {
      double profitTarget = MathMax(initialBalance * MinProfitPercent / 100.0, MinProfitAmount);
      Print("🎯 PROFIT TARGET PROTECTION: ENABLED");
      Print("   Balance ban đầu: $", initialBalance);
      Print("   Profit target: $", profitTarget, " (", MinProfitPercent, "% hoặc $", MinProfitAmount, ")");
   }
   
   // 🔄 Auto Features Info
   if(EnableAutoTrim)
   {
      Print("🔄 AUTO TRIM: ENABLED (Đóng lỗ bằng lãi mỗi 5 phút)");
   }
   else
   {
      Print("🔄 AUTO TRIM: DISABLED (Python AI sẽ quản lý đóng lệnh) ");
   }
   if(EnableReverseClose)
   {
      Print("🔄 REVERSE CLOSE: ENABLED (Đóng lệnh ngược khi reverse signal)");
   }
   
   Print("===============================================================");
   
   // Khởi tạo Complete AI System Handler
   zmqHandler.Init(HttpEndpoint);
   
   if(!zmqHandler.Connect())
   {
      Print("❌ Không thể kết nối đến Hệ thống AI Trading");
      Print("💡 Vui lòng đảm bảo complete_ai_trading_system.py đang chạy");
      return INIT_FAILED;
   }
   
   Print("✅ EA đã kết nối thành công với Hệ thống AI Trading");
   Print("🚀 Sẵn sàng nhận dự đoán AI và thực hiện giao dịch");
   
   // ⚠️ KIỂM TRA AUTO TRADING
   if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
   {
      Print("═══════════════════════════════════════════════════════════");
      Print("❌ WARNING: AUTO TRADING BỊ TẮT!");
      Print("═══════════════════════════════════════════════════════════");
      Print("🔧 CÁCH SỮA:");
      Print("   1. Nhấp nút AUTO TRADING trên thanh công cụ MT5 (phải màu XANH)");
      Print("   2. Hoặc: Tools → Options → Expert Advisors → Tick 'Allow automated trading'");
      Print("═══════════════════════════════════════════════════════════");
      return INIT_SUCCEEDED;  // Không fail, chỉ cảnh báo
   }
   
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
   {
      Print("═══════════════════════════════════════════════════════════");
      Print("❌ WARNING: TERMINAL KHÔNG CHO PHÉP GIAO DỊCH!");
      Print("═══════════════════════════════════════════════════════════");
      Print("🔧 CÁCH SỮA:");
      Print("   Tools → Options → Expert Advisors → Tick 'Allow automated trading'");
      Print("═══════════════════════════════════════════════════════════");
      return INIT_SUCCEEDED;
   }
   
   Print("✅ AUTO TRADING: ENABLED");
   Print("✅ TERMINAL TRADE: ALLOWED");
   
   // ⏰ Thiết lập timer để poll tín hiệu mỗi 5 giây
   EventSetTimer(5);
   
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   zmqHandler.Deinit();
   Print("🔌 Robot AI HTTP EA đã dừng - Tín hiệu: ", signalCount, ", Giao dịch: ", tradeCount);
}

//+------------------------------------------------------------------+
//| OnTick - Quản lý Trailing Stop & Break Even                     |
//+------------------------------------------------------------------+
void OnTick()
{
   // Quản lý tất cả positions
   ManagePositions();
}

//+------------------------------------------------------------------+
//| 🎯 Kiểm Tra Profit Target                                        |
//+------------------------------------------------------------------+
string CheckProfitTarget()
{
   if(!EnableProfitTargetProtection)
      return "NONE";
   
   double currentProfit = currentBalance - initialBalance;
   double profitTarget = MathMax(initialBalance * MinProfitPercent / 100.0, MinProfitAmount);
   
   // Cập nhật peak balance
   if(currentBalance > peakBalance)
      peakBalance = currentBalance;
   
   // Kiểm tra đạt target
   if(currentProfit >= profitTarget && !profitTargetAchieved)
   {
      profitTargetAchieved = true;
      Print("═══════════════════════════════════════════════════════════════");
      Print("🎯 PROFIT TARGET ACHIEVED!");
      Print("   Current profit: $", currentProfit, " >= Target: $", profitTarget);
      Print("   Chế độ bảo vệ lợi nhuận: BẬT");
      Print("═══════════════════════════════════════════════════════════════");
   }
   
   // Xác định chế độ bảo vệ
   if(profitTargetAchieved)
   {
      double drawdownFromPeak = (peakBalance - currentBalance) / peakBalance * 100;
      
      if(drawdownFromPeak > 10.0)
         return "HARD";  // Giảm xuống > 10% từ peak
      else if(drawdownFromPeak > 5.0)
         return "SOFT";  // Giảm xuống > 5% từ peak
      else
         return "CONSERVATIVE";  // Bảo vệ nhẹ
   }
   
   return "NONE";
}

//+------------------------------------------------------------------+
//| 🔍 Quét Balance và Kiểm Tra Tài Khoản Nhỏ                       |
//+------------------------------------------------------------------+
void ScanBalanceAndCheckSmallAccount()
{
   if(!EnableSmallAccountProtection)
      return;
   
   // Kiểm tra interval (không quét quá thường xuyên)
   if(TimeCurrent() - lastBalanceCheck < balanceScanInterval)
      return;
   
   lastBalanceCheck = TimeCurrent();
   
   // Lấy balance hiện tại
   double newBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   double oldBalance = currentBalance;
   currentBalance = newBalance;
   
   // Kiểm tra thay đổi balance
   if(MathAbs(newBalance - oldBalance) > 0.01)
   {
      Print("💰 Balance updated: $", DoubleToString(oldBalance, 2), " → $", DoubleToString(newBalance, 2), 
            " (", newBalance > oldBalance ? "+" : "", DoubleToString(newBalance - oldBalance, 2), ")");
   }
   
   // 🛡️ KIỂM TRA TÀI KHOẢN NHỎ
   bool wasSmallAccount = isSmallAccount;
   isSmallAccount = (newBalance < SmallAccountThreshold);
   
   if(isSmallAccount)
   {
      int currentPositions = PositionsTotal();
      
      // Chỉ cảnh báo khi chuyển từ TK lớn → TK nhỏ
      if(!wasSmallAccount)
      {
         Print("===============================================================");
         Print("🛡️ TÀI KHOẢN NHỎ PHÁT HIỆN!");
         Print("===============================================================");
         Print("   Balance: $", DoubleToString(newBalance, 2), " < $", SmallAccountThreshold);
         Print("   Lệnh đang mở: ", currentPositions, "/", SmallAccountMaxPositions);
         Print("   CHẾ ĐỘ BẢO VỆ: Giới hạn tối đa ", SmallAccountMaxPositions, " lệnh");
         Print("   ⚠️ Chống cháy tài khoản - Giảm risk!");
         Print("===============================================================");
      }
      
      // Cảnh báo nếu có quá nhiều lệnh
      if(currentPositions >= SmallAccountMaxPositions)
      {
         Print("⚠️ WARNING: ", currentPositions, " lệnh đang mở - ĐẠT GIỚI HẠN ", SmallAccountMaxPositions, " lệnh cho TK nhỏ!");
      }
   }
}

//+------------------------------------------------------------------+
//| 🔧 Auto Trim Positions - Đóng lỗ bằng lãi                      |
//+------------------------------------------------------------------+
void AutoTrimPositions()
{
   if(!EnableAutoTrim)
      return;
   
   // Kiểm tra interval
   if(TimeCurrent() - lastTrimTime < trimInterval)
      return;
   
   lastTrimTime = TimeCurrent();
   
   if(PositionsTotal() < 2)
      return;
   
   // Tính tổng P/L
   double totalPnL = 0;
   int positiveCount = 0;
   int negativeCount = 0;
   
   for(int i = 0; i < PositionsTotal(); i++)
   {
      if(PositionSelectByTicket(PositionGetTicket(i)))
      {
         double profit = PositionGetDouble(POSITION_PROFIT);
         totalPnL += profit;
         
         if(profit > 0)
            positiveCount++;
         else if(profit < 0)
            negativeCount++;
      }
   }
   
   // Điều kiện trim: Có cả lệnh dương và âm, tổng P/L > 0
   if(positiveCount == 0 || negativeCount == 0 || totalPnL <= 0)
      return;
   
   Print("🔧 AUTO TRIM - Tổng P/L: $", totalPnL, " (Lãi: ", positiveCount, ", Lỗ: ", negativeCount, ")");
   
   // Tìm lệnh lỗ lớn nhất
   double worstLoss = 0;
   ulong worstTicket = 0;
   
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         double profit = PositionGetDouble(POSITION_PROFIT);
         if(profit < worstLoss)
         {
            worstLoss = profit;
            worstTicket = ticket;
         }
      }
   }
   
   // Đóng lệnh lỗ lớn nhất nếu profit có thể cover
   double availableProfit = totalPnL * 0.7;  // Giữ lại 30% safety
   
   if(worstTicket > 0 && MathAbs(worstLoss) <= availableProfit)
   {
      if(PositionSelectByTicket(worstTicket))
      {
         string symbol = PositionGetString(POSITION_SYMBOL);
         double volume = PositionGetDouble(POSITION_VOLUME);
         
         if(trade.PositionClose(worstTicket))
         {
            Print("✅ AUTO TRIM: Đóng lệnh #", worstTicket, " với loss $", worstLoss);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| 🔄 Close All By Type - Đóng tất cả lệnh cùng loại              |
//+------------------------------------------------------------------+
int CloseAllByType(string actionType)
{
   if(!EnableReverseClose)
      return 0;
   
   int closedCount = 0;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(PositionSelectByTicket(ticket))
      {
         string symbol = PositionGetString(POSITION_SYMBOL);
         ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
         
         bool shouldClose = false;
         
         if(actionType == "BUY" && posType == POSITION_TYPE_BUY)
            shouldClose = true;
         else if(actionType == "SELL" && posType == POSITION_TYPE_SELL)
            shouldClose = true;
         
         if(shouldClose)
         {
            if(trade.PositionClose(ticket))
            {
               closedCount++;
               Print("🔄 REVERSE CLOSE: Đóng lệnh #", ticket, " (Type: ", actionType, ")");
            }
         }
      }
   }
   
   if(closedCount > 0)
   {
      Print("✅ REVERSE CLOSE: Đã đóng ", closedCount, " lệnh ", actionType);
   }
   
   return closedCount;
}

//+------------------------------------------------------------------+
//| Timer function - Enhanced with VN monitoring                    |
//+------------------------------------------------------------------+
void OnTimer()
{
   static int timerCount = 0;
   timerCount++;
   
   // Debug: In log mỗi lần timer chạy
   if(timerCount % 6 == 1) // Mỗi 30 giây in một lần
   {
      Print("⏰ Timer đang hoạt động - lần thứ ", timerCount);
   }
   
   // 🔍 BALANCE SCANNING - Quét balance liên tục
   ScanBalanceAndCheckSmallAccount();
   
   // 🎯 PROFIT TARGET CHECK
   string protectionMode = CheckProfitTarget();
   
   // 🔧 AUTO TRIM POSITIONS - Đóng lỗ bằng lãi
   AutoTrimPositions();
   
   // VN Feature: Theo dõi lợi nhuận hàng ngày (không dừng EA)
   LogDailyProfitStatus();
   
   // Poll tín hiệu từ Complete AI Trading System
   string rawMessage;
   if(zmqHandler.Poll(rawMessage))
   {
      Print("✅ Đã nhận tín hiệu từ AI system");
      ProcessAISignal(rawMessage);
   }
}

//+------------------------------------------------------------------+
//| Xử lý tín hiệu AI từ HTTP server                                 |
//+------------------------------------------------------------------+
void ProcessAISignal(string rawMessage)
{
   signalCount++;
   
   Print("═══════════════════════════════════════════════════════════════");
   Print("📦 BẮT ĐẦU XỬ LÝ TÍN HIỆU #", signalCount);
   Print("📄 Raw Message: ", rawMessage);
   
   // Parse JSON message directly
   CJAVal localDoc;
   if(!localDoc.Deserialize(rawMessage))
   {
      Print("❌ Không thể phân tích JSON tín hiệu AI: ", rawMessage);
      return;
   }
   
   Print("✅ Parse JSON thành công");
   
   // Lấy thông tin signal từ Complete AI Trading System
   string action = localDoc["action"].ToStr();
   string symbol = localDoc["symbol"].ToStr();
   double price = localDoc["price"].ToDbl();
   double entry_price = localDoc["entry_price"].ToDbl(); // 🆕 Giá đặt lệnh LIMIT
   double confidence = localDoc["confidence"].ToDbl();
   string timestamp = localDoc["timestamp"].ToStr();
   int signal_id = (int)localDoc["signal_id"].ToDbl();
   string mt5_log = localDoc["mt5_log"].ToStr();
   
   Print("🔍 Extracted: action=", action, ", symbol=", symbol, ", price=", price, ", entry=", entry_price, ", conf=", confidence, "%");
   
   // ========== 🚫 DUPLICATE SIGNAL PREVENTION ==========
   if(signal_id == lastProcessedSignalId && signal_id > 0)
   {
      Print("⚠️ DUPLICATE SIGNAL #", signal_id, " - BỎ QUA!");
      return;
   }
   lastProcessedSignalId = signal_id;
   Print("✅ Signal ID check passed: ", signal_id);
   
   // 📡 LUÔN GHI LOG MỌI TÍN HIỆU - ngay cả khi NONE
   Print("🤖 Tín hiệu AI #", signal_id, ": ", action, " ", symbol, " @ ", price, " (Độ tin cậy: ", confidence, "%) [", timestamp, "]");
   if(mt5_log != "")
   {
      Print(mt5_log); // Ghi log chi tiết từ Python system
   }
   
   // ========== 📥 READ TRAILING PARAMS FROM PYTHON SIGNAL ==========
   if(localDoc["trailing_type"].m_type == jtSTR)
      g_LastTrailingType = localDoc["trailing_type"].ToStr();
   if(localDoc["sideways_type"].m_type == jtSTR)
      g_LastSidewaysType = localDoc["sideways_type"].ToStr();
   if(localDoc["trailing_params"].m_type == jtOBJ)
   {
      if(localDoc["trailing_params"]["breakeven_trigger_pips"].m_type == jtDBL)
         g_LastBEPips = localDoc["trailing_params"]["breakeven_trigger_pips"].ToDbl();
      if(localDoc["trailing_params"]["breakeven_offset_pips"].m_type == jtDBL)
         g_LastBEOffsetPips = localDoc["trailing_params"]["breakeven_offset_pips"].ToDbl();
   }
   g_WideBEApplied = false; // Reset flag khi có signal mới
   Print("📊 Trailing: type=", g_LastTrailingType, ", sideways=", g_LastSidewaysType, ", BE trigger=", g_LastBEPips, "p, offset=", g_LastBEOffsetPips, "p");
   
   // ========== 💰 READ LOT SIZE FROM PYTHON AI ==========
   double pythonLotSize = 0.01; // Default fallback
   if(localDoc["lot_size"].m_type == jtDBL)
   {
      pythonLotSize = localDoc["lot_size"].ToDbl();
      Print("💰 Python AI calculated lot: ", pythonLotSize);
   }
   else if(localDoc["lot_size"].m_type == jtINT)
   {
      pythonLotSize = (double)localDoc["lot_size"].ToInt();
      Print("💰 Python AI calculated lot: ", pythonLotSize);
   }
   
   // Kiểm tra confidence threshold
   Print("📊 Checking confidence: ", confidence, "% vs MinConfidence: ", MinConfidence, "%");
   if(confidence < MinConfidence)
   {
      Print("⚠️ Độ tin cậy tín hiệu quá thấp: ", confidence, "% < ", MinConfidence, "%");
      return;
   }
   Print("✅ Confidence OK");
   
   // 🎯 PROFIT TARGET PROTECTION CHECK
   string protectionMode = CheckProfitTarget();
   if(protectionMode == "HARD")
   {
      Print("🎯 PROFIT TARGET PROTECTION: HARD MODE - Không mở lệnh mới (bảo vệ profit)");
      return;
   }
   else if(protectionMode == "SOFT" && confidence < 70.0)
   {
      Print("🎯 PROFIT TARGET PROTECTION: SOFT MODE - Chỉ chấp nhận confidence > 70%");
      return;
   }
   
   // Kiểm tra số lượng positions - ƯU TIÊN SMALL ACCOUNT PROTECTION
   int effectiveMaxPositions = MaxPositions;
   
   if(EnableSmallAccountProtection && isSmallAccount)
   {
      effectiveMaxPositions = SmallAccountMaxPositions;
      Print("🛡️ Small Account Mode: Max positions = ", effectiveMaxPositions);
   }
   
   Print("📋 Checking positions: ", PositionsTotal(), "/", effectiveMaxPositions);
   if(PositionsTotal() >= effectiveMaxPositions)
   {
      if(isSmallAccount)
      {
         Print("🛡️ SMALL ACCOUNT PROTECTION: Đã đạt ", effectiveMaxPositions, " lệnh tối đa (Balance $", currentBalance, " < $", SmallAccountThreshold, ")");
      }
      else
      {
         Print("⚠️ Đã đạt số lệnh tối đa: ", PositionsTotal(), "/", effectiveMaxPositions);
      }
      return;
   }
   Print("✅ Positions OK");
   
   // Kiểm tra symbol (convert XAUUSD/GOLD -> current symbol nếu cần)
   if(symbol == "XAUUSD" || symbol == "GOLD")
   {
      symbol = _Symbol; // Dùng symbol hiện tại của chart
   }

   // Chuẩn hoá các bí danh cho BTC (ví dụ: BTC, XBT, BTCUSD)
   // Nếu tín hiệu chứa 'BTC' hoặc 'XBT' và chart hiện tại cũng là một symbol BTC,
   // thì map về chart symbol để đảm bảo khớp với tên của broker (ví dụ: BTCUSD, BTCUSD.i)
   if((StringFind(symbol, "BTC") >= 0 || StringFind(symbol, "XBT") >= 0) &&
      (StringFind(_Symbol, "BTC") >= 0 || StringFind(_Symbol, "XBT") >= 0))
   {
      symbol = _Symbol;
   }
   
   // 🔄 REVERSE SIGNAL HANDLING - Đóng lệnh ngược chiều
   if(EnableReverseClose && action != "NONE")
   {
      string reverseType = "";
      
      if(action == "BUY" || StringFind(action, "BUY") >= 0)
         reverseType = "SELL";
      else if(action == "SELL" || StringFind(action, "SELL") >= 0)
         reverseType = "BUY";
      
      if(reverseType != "")
      {
         // Đóng lệnh ngược chiều khi có tín hiệu mạnh
         if(confidence >= 65.0)
         {
            Print("🔄 HIGH CONFIDENCE REVERSE (", confidence, "%) - Đóng TẤT CẢ lệnh ", reverseType);
            CloseAllByType(reverseType);
         }
         else
         {
            // Chỉ đóng lệnh lỗ khi confidence thấp hơn
            Print("🔄 MODERATE REVERSE (", confidence, "%) - Đóng lệnh LỖ ", reverseType);
            for(int i = PositionsTotal() - 1; i >= 0; i--)
            {
               ulong ticket = PositionGetTicket(i);
               if(PositionSelectByTicket(ticket))
               {
                  ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
                  double profit = PositionGetDouble(POSITION_PROFIT);
                  
                  bool isTargetType = (reverseType == "BUY" && posType == POSITION_TYPE_BUY) ||
                                    (reverseType == "SELL" && posType == POSITION_TYPE_SELL);
                  
                  if(isTargetType && profit < 0)
                  {
                     trade.PositionClose(ticket);
                     Print("   Đóng lệnh lỗ #", ticket, " P/L: $", profit);
                  }
               }
            }
         }
      }
   }
   
   // Thực hiện giao dịch
   Print("🔍 EnableTrading: ", EnableTrading);
   if(EnableTrading)
   {
      // ⚠️ KIỂM TRA AUTO TRADING TRƯỚC KHI ĐẶT LỆNH
      if(!MQLInfoInteger(MQL_TRADE_ALLOWED))
      {
         Print("═══════════════════════════════════════════════════════════");
         Print("❌ KHÔNG THỂ ĐẶT LỆNH: AUTO TRADING BỊ TẮT!");
         Print("═══════════════════════════════════════════════════════════");
         Print("🔧 CÁCH SỮA NGAY:");
         Print("   1. Nhấn nút AUTO TRADING trên toolbar MT5 (biểu tượng robot)");
         Print("   2. Nút phải chuyển sang màu XANH");
         Print("   3. Hoặc: Tools → Options → Expert Advisors → 'Allow automated trading'");
         Print("═══════════════════════════════════════════════════════════");
         return;
      }
      
      if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED))
      {
         Print("❌ Lỗi: Terminal không cho phép giao dịch!");
         return;
      }
      
      Print("⚡ Chuyển sang ExecuteAITrade...");
      ExecuteAITrade(action, symbol, price, entry_price, confidence, pythonLotSize);
   }
   else
   {
      Print("📊 Giao dịch tạm tắt - Tín hiệu sẽ là: ", action, " ", symbol);
   }
   
   Print("═══════════════════════════════════════════════════════════════");
}

//+------------------------------------------------------------------+
//| Thực hiện giao dịch từ AI signal - Hỗ trợ LIMIT orders          |
//+------------------------------------------------------------------+
void ExecuteAITrade(string action, string symbol, double price, double entry_price, double confidence, double pythonLotSize = 0.01)
{
   Print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
   Print("⚡ BẮT ĐẦU EXECUTE TRADE");
   Print("📊 Action: ", action, " | Symbol: ", symbol);
   Print("💰 Price: ", price, " | Entry: ", entry_price, " | Confidence: ", confidence, "%");
   
   // ✅ DÙNG LOT TỪ PYTHON AI (ưu tiên), hoặc tính lại nếu không có
   double lotSize = pythonLotSize;
   
   // Nếu Python không gửi lot hoặc lot = 0, mới tính lại
   if(lotSize <= 0)
   {
      lotSize = CalculateLotSize(confidence);
      Print("⚠️ Python không gửi lot, EA tự tính: ", lotSize);
   }
   else
   {
      Print("✅ DÙNG LOT TỪ PYTHON AI (trước clamp): ", lotSize);
   }
   
   // 🔴 CLAMP LOT THEO EA INPUT (MinLot, MaxLot)
   double minLotSymbol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLotSymbol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   
   double originalLot = lotSize;
   lotSize = MathMax(MathMax(minLotSymbol, MinLot), MathMin(MathMin(maxLotSymbol, MaxLot), lotSize));
   
   if(originalLot != lotSize)
   {
      Print("🔴 LOT CLAMPED: ", originalLot, " → ", lotSize, " (Min=", MinLot, ", Max=", MaxLot, ")");
   }
   
   double sl = 0, tp = 0;
   
   // Tính SL/TP dựa trên ATR
   int atr_handle = iATR(symbol, PERIOD_H1, 14);
   double atr_buffer[];
   ArraySetAsSeries(atr_buffer, true);
   
   double atr = 0;
   if(atr_handle != INVALID_HANDLE && CopyBuffer(atr_handle, 0, 0, 1, atr_buffer) > 0)
   {
      atr = atr_buffer[0];
      IndicatorRelease(atr_handle);
   }
   
   // 🆕 Tính SL/TP cho từng loại lệnh
   if(atr > 0)
   {
      if(action == "BUY" || action == "BUY_LIMIT")
      {
         double base_price = (action == "BUY") ? SymbolInfoDouble(symbol, SYMBOL_ASK) : entry_price;
         sl = base_price - atr * SLMultiplier;
         tp = base_price + atr * TPMultiplier;
      }
      else if(action == "SELL" || action == "SELL_LIMIT")
      {
         double base_price = (action == "SELL") ? SymbolInfoDouble(symbol, SYMBOL_BID) : entry_price;
         sl = base_price + atr * SLMultiplier;
         tp = base_price - atr * TPMultiplier;
      }
   }
   
   Print("🚀 Đang thực thi lệnh AI: ", action, " ", symbol);
   Print("📊 Lot: ", lotSize, " | SL: ", sl, " | TP: ", tp);
   if(action == "BUY_LIMIT" || action == "SELL_LIMIT")
   {
      Print("📍 Giá hiện tại: ", price, " → Giá đặt lệnh: ", entry_price);
   }
   
   // 🆕 Thực hiện lệnh - Hỗ trợ cả Market và Limit orders
   bool success = false;
   
   if(action == "BUY")
   {
      success = trade.Buy(lotSize, symbol, 0, sl, tp, "AI-Signal-" + IntegerToString(signalCount));
   }
   else if(action == "SELL")
   {
      success = trade.Sell(lotSize, symbol, 0, sl, tp, "AI-Signal-" + IntegerToString(signalCount));
   }
   else if(action == "BUY_LIMIT")
   {
      success = trade.BuyLimit(lotSize, entry_price, symbol, sl, tp, ORDER_TIME_GTC, 0, "AI-LIMIT-" + IntegerToString(signalCount));
   }
   else if(action == "SELL_LIMIT")
   {
      success = trade.SellLimit(lotSize, entry_price, symbol, sl, tp, ORDER_TIME_GTC, 0, "AI-LIMIT-" + IntegerToString(signalCount));
   }
   else
   {
      Print("⚠️ Loại lệnh không hợp lệ: ", action);
      return;
   }
   
   if(success)
   {
      tradeCount++;
      Print("✅ Lệnh AI đã đặt thành công - Tổng số giao dịch: ", tradeCount);
      Print("📈 Ticket #", trade.ResultOrder(), " | Loại: ", action, " | Ghi chú: AI-Signal-", signalCount);
   }
   else
   {
      uint errorCode = GetLastError();
      string errorDesc = "";
      
      // Giải thích lỗi chi tiết
      switch(errorCode)
      {
         case 10027: errorDesc = "AutoTrading disabled by client - Bật AUTO TRADING!"; break;
         case 133: errorDesc = "Trading disabled - Kiểm tra Terminal settings"; break;
         case 134: errorDesc = "Not enough money - Balance không đủ"; break;
         case 138: errorDesc = "Requote - Giá thay đổi, thử lại"; break;
         case 4756: errorDesc = "Trade context busy - Server bận, chờ tí"; break;
         default: errorDesc = "Unknown error"; break;
      }
      
      Print("═══════════════════════════════════════════════════════════");
      Print("❌ Lệnh AI thất bại!");
      Print("═══════════════════════════════════════════════════════════");
      Print("🔍 Chi tiết lỗi:");
      Print("   Error Code: ", errorCode);
      Print("   Error Message: ", trade.ResultComment());
      Print("   Giải thích: ", errorDesc);
      Print("📄 Thông tin lệnh:");
      Print("   Action: ", action);
      Print("   Entry Price: ", entry_price);
      Print("   Current Price: ", price);
      Print("   Lot Size: ", lotSize);
      Print("   SL: ", sl, " | TP: ", tp);
      
      if(errorCode == 10027)
      {
         Print("═══════════════════════════════════════════════════════════");
         Print("🔧 CÁCH SỮA:");
         Print("   1. Nhấn nút AUTO TRADING trên toolbar MT5");
         Print("   2. Nút phải chuyển từ Đỏ (TẮT) sang XANH (BẬT)");
         Print("   3. Sau đó EA sẽ tự động đặt lệnh ở tín hiệu tiếp theo");
         Print("═══════════════════════════════════════════════════════════");
      }
      Print("═══════════════════════════════════════════════════════════");
   }
}

//+------------------------------------------------------------------+
//| Tính lot size - Tích hợp VN features và AI confidence           |
//+------------------------------------------------------------------+
double CalculateLotSize(double confidence)
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double baseLot;
   
   // 🛡️ SMALL ACCOUNT PROTECTION: Giảm risk cho tài khoản nhỏ
   double effectiveRiskPercent = RiskPercent;
   if(EnableSmallAccountProtection && isSmallAccount)
   {
      effectiveRiskPercent = RiskPercent * SmallAccountRiskReduction;
      Print("🛡️ Small Account: Risk giảm từ ", RiskPercent, "% → ", effectiveRiskPercent, "%");
   }
   
   // ✨ MỚI: Tự động lot theo kích thước tài khoản (VN feature)
   if(UseAutoLotByBalance)
   {
      baseLot = CalculateLotByBalance(balance);
      Print("📊 Tự động Lot theo TK: ", baseLot, " (Số dư: $", balance, ")");
   }
   else if(!UseRiskManagement)
   {
      baseLot = FixedLotSize;
   }
   else
   {
      // Risk management theo confidence
      double confidenceMultiplier = confidence / 100.0;
      double riskAmount = balance * effectiveRiskPercent / 100.0;  // Dùng effective risk
      double riskLot = riskAmount / 100.0; // Simplified risk calculation
      baseLot = MathMax(FixedLotSize * confidenceMultiplier, riskLot);
   }
   
   // Áp dụng hệ số nhân (VN feature)
   double finalLot = baseLot * MultiplyFactor;
   
   // Giới hạn lot size
   double minLotSymbol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLotSymbol = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   
   finalLot = MathMax(MathMax(minLotSymbol, MinLot), MathMin(MathMin(maxLotSymbol, MaxLot), finalLot));
   
   Print("📊 Tính Lot nâng cao - Độ tin cậy: ", confidence, "%, Cơ bản: ", baseLot, ", Cuối cùng: ", finalLot, " (Hệ số: ", MultiplyFactor, "x)");
   
   return finalLot;
}

//+------------------------------------------------------------------+
//| Tự động lot theo kích thước tài khoản (VN Feature)            |
//+------------------------------------------------------------------+
double CalculateLotByBalance(double balance)
{
   // Quy tắc tự động VN:
   // < $2,000   → 0.01 lot
   // $2,000 - $5,000 → 0.05 lot  
   // $5,000 - $7,000 → 0.10 lot
   // >= $7,000  → 0.25 lot
   
   if(balance < 2000)
      return MinLot;  // 0.01
   else if(balance < 5000)
      return 0.05;
   else if(balance < 7000)
      return 0.10;
   else
      return MaxLot;  // 0.25
}

//+------------------------------------------------------------------+
//| Theo dõi lợi nhuận hàng ngày (VN Feature - Không dừng EA)      |
//+------------------------------------------------------------------+
void LogDailyProfitStatus()
{
   if(!EnableDailyProfitTracking)
      return;
      
   // Chỉ log mỗi 30 phút để tránh spam
   if(TimeCurrent() - lastProfitLogTime < 1800)
      return;
      
   lastProfitLogTime = TimeCurrent();
   
   double todayPnL = GetTodayPnL();
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double minProfitTargetUSD = balance * DailyProfitTarget / 100.0;
   double maxProfitTargetUSD = balance * MaxProfitTarget / 100.0;
   double profitPercentage = (todayPnL / balance) * 100.0;
   
   Print("═══════════════════════════════════════════════════════");
   Print("📈 THỐNG KÊ LỢI NHUẬN HÔM NAY");
   Print("───────────────────────────────────────────────────────");
   Print("💰 Lãi hôm nay: $", DoubleToString(todayPnL, 2), " (", DoubleToString(profitPercentage, 2), "%)");
   Print("🎯 Mục tiêu tối thiểu: $", DoubleToString(minProfitTargetUSD, 2), " (", DoubleToString(DailyProfitTarget, 1), "%)");
   
   if(todayPnL >= minProfitTargetUSD)
      Print("✅ ĐẠT MỤC TIÊU TỐI THIỂU - Tiếp tục giao dịch!");
   else
      Print("⏳ Còn cần: $", DoubleToString(minProfitTargetUSD - todayPnL, 2), " nữa");
   
   Print("📈 Tối đa theo dõi: $", DoubleToString(maxProfitTargetUSD, 2), " (", DoubleToString(MaxProfitTarget, 1), "%)");
   Print("═══════════════════════════════════════════════════════");
}

//+------------------------------------------------------------------+
//| Tính lãi/lỗ hôm nay (VN Feature)                              |
//+------------------------------------------------------------------+
double GetTodayPnL()
{
   double todayPnL = 0;
   datetime todayStart = iTime(_Symbol, PERIOD_D1, 0);
   
   // Kiểm tra lịch sử giao dịch hôm nay
   if(HistorySelect(todayStart, TimeCurrent()))
   {
      for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = HistoryDealGetTicket(i);
         if(ticket > 0)
         {
            double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
            todayPnL += profit;
         }
      }
   }
   
   return todayPnL;
}

//+------------------------------------------------------------------+
//| Quản lý Trailing Stop, Break Even, Partial Close               |
//+------------------------------------------------------------------+
void ManagePositions()
{
   // ✅ THROTTLING - Chỉ chạy mỗi 1 giây để tránh tính toán liên tục
   datetime currentTime = TimeCurrent();
   if(currentTime - lastTrailingCheck < trailingCheckInterval)
      return;
   lastTrailingCheck = currentTime;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket <= 0) continue;
      
      string symbol = PositionGetString(POSITION_SYMBOL);
      if(symbol != _Symbol) continue;
      
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      double currentProfit = PositionGetDouble(POSITION_PROFIT);
      double volume = PositionGetDouble(POSITION_VOLUME);
      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      
      double currentPrice = (posType == POSITION_TYPE_BUY) ? 
                           SymbolInfoDouble(symbol, SYMBOL_BID) : 
                           SymbolInfoDouble(symbol, SYMBOL_ASK);
      
      double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
      int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
      
      // Tính profit bằng pips
      double profitPips = 0;
      if(posType == POSITION_TYPE_BUY)
         profitPips = (currentPrice - openPrice) / point / 10;
      else
         profitPips = (openPrice - currentPrice) / point / 10;
      
      // ============ PARTIAL CLOSE ============
      if(EnablePartialClose && volume > SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN))
      {
         double tp1Distance = PartialTP1Multiplier * (MathAbs(openPrice - currentSL) / SLMultiplier);
         double tp1Price = (posType == POSITION_TYPE_BUY) ? 
                          openPrice + tp1Distance : 
                          openPrice - tp1Distance;
         
         bool reachedTP1 = (posType == POSITION_TYPE_BUY && currentPrice >= tp1Price) ||
                          (posType == POSITION_TYPE_SELL && currentPrice <= tp1Price);
         
         if(reachedTP1 && currentProfit > 0)
         {
            double closeVolume = NormalizeDouble(volume * PartialClosePercent / 100.0, 2);
            closeVolume = MathMax(closeVolume, SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN));
            
            if(closeVolume < volume)
            {
               if(trade.PositionClosePartial(ticket, closeVolume))
                  Print("✅ Partial Close: ", closeVolume, " lot @ ", currentPrice, " (Profit: $", currentProfit, ")");
            }
         }
      }
      
      // ============ BREAK EVEN ============
      // ============ BREAK EVEN (Entry + 10 pips) - Phân biệt SWING vs NORMAL ============
      // 🎯 SWING (WIDE): Trigger @ 40 pips → SL = Entry + 10 pips
      // 🎯 NORMAL/TREND: Trigger @ 15 pips → SL = Entry + 10 pips
      
      double effectiveBEPips = BreakEvenPips; // Default: 15 pips
      if(g_LastSidewaysType == "WIDE")
      {
         effectiveBEPips = 40.0; // SWING: Đợi lời 40 pips mới chạy BE
      }
      
      if(EnableBreakEven && profitPips >= effectiveBEPips)
      {
         double newSL = 0;
         if(posType == POSITION_TYPE_BUY)
         {
            newSL = openPrice + BreakEvenPlusPips * point * 10;
            // ✅ BUY: CHỈ TĂNG SL (không giảm) - bảo vệ lợi nhuận
            if(currentSL == 0 || newSL > currentSL)
            {
               if(trade.PositionModify(ticket, NormalizeDouble(newSL, digits), currentTP))
               {
                  string orderType = (g_LastSidewaysType == "WIDE") ? "SWING" : "NORMAL";
                  Print("🔒 Break Even BUY #", ticket, " [", orderType, "]: SL ", DoubleToString(currentSL, digits), " → ", DoubleToString(newSL, digits), " (Entry+10 @ ", DoubleToString(profitPips, 1), " pips)");
               }
            }
         }
         else // SELL
         {
            newSL = openPrice - BreakEvenPlusPips * point * 10;
            // ✅ SELL: CHỈ GIẢM SL (không tăng) - bảo vệ lợi nhuận
            if(currentSL == 0 || newSL < currentSL)
            {
               if(trade.PositionModify(ticket, NormalizeDouble(newSL, digits), currentTP))
               {
                  string orderType = (g_LastSidewaysType == "WIDE") ? "SWING" : "NORMAL";
                  Print("🔒 Break Even SELL #", ticket, " [", orderType, "]: SL ", DoubleToString(currentSL, digits), " → ", DoubleToString(newSL, digits), " (Entry-10 @ ", DoubleToString(profitPips, 1), " pips)");
               }
            }
         }
      }
      
      // ============ WIDE SIDEWAYS BREAKEVEN (Lời 20 pips → SL lên Entry+10 pips) ============
      // ❌ TẮT - Để test Trailing Stop thuần túy
      if(false && !g_WideBEApplied && g_LastTrailingType == "sideways_breakeven" && g_LastSidewaysType == "WIDE")
      {
         if(profitPips >= g_LastBEPips) // >= 20 pips
         {
            double newSL = 0;
            bool shouldModify = false;
            
            if(posType == POSITION_TYPE_BUY)
            {
               // BUY: SL = Entry + 10 pips
               newSL = NormalizeDouble(openPrice + g_LastBEOffsetPips * point * 10, digits);
               
               // ✅ CHỈ TĂNG SL, KHÔNG GIẢM
               if(currentSL == 0 || newSL > currentSL)
                  shouldModify = true;
            }
            else // SELL
            {
               // SELL: SL = Entry - 10 pips
               newSL = NormalizeDouble(openPrice - g_LastBEOffsetPips * point * 10, digits);
               
               // ✅ CHỈ GIẢM SL, KHÔNG TĂNG
               if(currentSL == 0 || newSL < currentSL)
                  shouldModify = true;
            }
            
            if(shouldModify)
            {
               if(trade.PositionModify(ticket, newSL, currentTP))
               {
                  g_WideBEApplied = true; // ✅ Đánh dấu đã chạy
                  string typeStr = (posType == POSITION_TYPE_BUY) ? "BUY" : "SELL";
                  Print("🎯 WIDE SIDEWAYS BE ", typeStr, " #", ticket, ": Lời ", DoubleToString(profitPips, 1), " pips → SL Entry+", g_LastBEOffsetPips, " pips (", DoubleToString(newSL, digits), ")");
               }
            }
         }
      }
      
      // ============ TRAILING STOP (v2.2 - Phân biệt SWING vs TREND) ============
      // ✅ Bắt đầu khi lãi >= MinProfitToStartTrailing
      // ✅ WIDE (Swing) → Trigger @ 40 pips, giữ 20 pips
      // ✅ TRENDING → Trigger @ 50 pips, giữ 20 pips
      // ✅ SL chỉ TĂNG (BUY) hoặc GIẢM (SELL), KHÔNG BAO GIỜ đi ngược
      
      // 🔍 PHÂN BIỆT SWING vs TREND
      double effectiveMinProfit = MinProfitToStartTrailing; // Default: 50 pips
      if(g_LastSidewaysType == "WIDE")
      {
         effectiveMinProfit = 40.0; // SWING: Bắt đầu sớm hơn @ 40 pips
      }
      
      if(EnableTrailingStop && profitPips >= effectiveMinProfit)
      {
         // Log loại lệnh khi trailing lần đầu
         static ulong lastLoggedTicket = 0;
         if(ticket != lastLoggedTicket)
         {
            string orderType = (g_LastSidewaysType == "WIDE") ? "SWING" : 
                              (g_LastSidewaysType == "TRENDING") ? "TREND" : "NORMAL";
            Print("🎯 TRAILING START #", ticket, " - Type: ", orderType, " (", g_LastSidewaysType, ") - Trigger: ", effectiveMinProfit, " pips");
            lastLoggedTicket = ticket;
         }
         
         double newSL = 0;
         double newTP = currentTP; // Mặc định giữ TP
         bool shouldModifySL = false;
         bool shouldModifyTP = false;
         
         if(posType == POSITION_TYPE_BUY)
         {
            // BUY: SL = Current Price - TrailingStopPips
            newSL = NormalizeDouble(currentPrice - TrailingStopPips * point * 10, digits);
            
            Print("🔍 DEBUG BUY #", ticket, ": Price=", DoubleToString(currentPrice, digits), ", newSL=", DoubleToString(newSL, digits), ", currentSL=", DoubleToString(currentSL, digits));
            
            // ✅ CHỈ TĂNG SL - KHÔNG BAO GIỞ ĐẶT LẠI SL THẤP HƠN
            // Nếu đã có SL, chỉ tăng lên, KHÔNG giảm xuống
            if(currentSL == 0)
            {
               // Lần đầu tiên trailing
               shouldModifySL = true;
               Print("✅ BUY: Lần đầu tiên đặt SL = ", DoubleToString(newSL, digits));
            }
            else if(newSL > currentSL)
            {
               // Chỉ di chuyển khi newSL cao hơn currentSL
               shouldModifySL = true;
               Print("✅ BUY: TĂNG SL từ ", DoubleToString(currentSL, digits), " lên ", DoubleToString(newSL, digits));
            }
            else
            {
               // Giá giảm → newSL thấp hơn currentSL → GIỮ NGUYÊN SL hiện tại
               shouldModifySL = false;
               Print("🔒 BUY: GIỮ NGUYÊN SL ", DoubleToString(currentSL, digits), " (newSL=", DoubleToString(newSL, digits), " thấp hơn)");
            }
            
            // ✅ TRAILING TP (optional)
            if(EnableTrailingTP && TrailingTPPips > 0)
            {
               newTP = NormalizeDouble(currentPrice + TrailingTPPips * point * 10, digits);
               
               // CHỈ TĂNG TP, KHÔNG BAO GIỜ GIẢM
               if(currentTP == 0 || newTP > currentTP + TrailingStepPips * point * 10)
               {
                  shouldModifyTP = true;
               }
            }
         }
         else // SELL
         {
            // SELL: SL = Current Price + TrailingStopPips
            newSL = NormalizeDouble(currentPrice + TrailingStopPips * point * 10, digits);
            
            Print("🔍 DEBUG SELL #", ticket, ": Price=", DoubleToString(currentPrice, digits), ", newSL=", DoubleToString(newSL, digits), ", currentSL=", DoubleToString(currentSL, digits));
            
            // ✅ CHỈ GIẢM SL - KHÔNG BAO GIỞ ĐẶT LẠI SL CAO HƠN
            // Nếu đã có SL, chỉ giảm xuống, KHÔNG tăng lên
            if(currentSL == 0)
            {
               // Lần đầu tiên trailing
               shouldModifySL = true;
               Print("✅ SELL: Lần đầu tiên đặt SL = ", DoubleToString(newSL, digits));
            }
            else if(newSL < currentSL)
            {
               // Chỉ di chuyển khi newSL thấp hơn currentSL
               shouldModifySL = true;
               Print("✅ SELL: GIẢM SL từ ", DoubleToString(currentSL, digits), " xuống ", DoubleToString(newSL, digits));
            }
            else
            {
               // Giá tăng → newSL cao hơn currentSL → GIỮ NGUYÊN SL hiện tại
               shouldModifySL = false;
               Print("🔒 SELL: GIỮ NGUYÊN SL ", DoubleToString(currentSL, digits), " (newSL=", DoubleToString(newSL, digits), " cao hơn)");
            }
            
            // ✅ TRAILING TP (optional)
            if(EnableTrailingTP && TrailingTPPips > 0)
            {
               newTP = NormalizeDouble(currentPrice - TrailingTPPips * point * 10, digits);
               
               // CHỈ GIẢM TP (target tốt hơn cho SELL), KHÔNG BAO GIỜ TĂNG
               if(currentTP == 0 || newTP < currentTP - TrailingStepPips * point * 10)
               {
                  shouldModifyTP = true;
               }
            }
         }
         
         // MODIFY POSITION
         if(shouldModifySL || shouldModifyTP)
         {
            // ✅ QUAN TRỌNG: Nếu KHÔNG modify SL, GIỮ NGUYÊN currentSL
            if(!shouldModifySL)
            {
               newSL = currentSL; // ✅ GIỮ NGUYÊN SL hiện tại
               Print("🔒 GIỮ NGUYÊN SL: ", DoubleToString(currentSL, digits));
            }
            
            // Nếu không modify TP, giữ nguyên TP hiện tại
            if(!shouldModifyTP)
               newTP = currentTP;
            
            // ✅ VALIDATION CUỐI CÙNG - KHÔNG BAO GIỞ cho phép SL thay đổi sai hướng
            bool finalValidation = false;
            if(posType == POSITION_TYPE_BUY)
            {
               // BUY: Chỉ cho phép nếu newSL >= currentSL (bằng = giữ nguyên, lớn hơn = tăng)
               if(currentSL == 0 || newSL >= currentSL)
                  finalValidation = true;
               else
               {
                  Print("❌ FINAL VALIDATION FAILED BUY #", ticket, ": newSL=", DoubleToString(newSL, digits), " < currentSL=", DoubleToString(currentSL, digits), " - BỐ QUA!");
                  continue; // Bỏ qua position này
               }
            }
            else // SELL
            {
               // SELL: Chỉ cho phép nếu newSL <= currentSL (bằng = giữ nguyên, nhỏ hơn = giảm)
               if(currentSL == 0 || newSL <= currentSL)
                  finalValidation = true;
               else
               {
                  Print("❌ FINAL VALIDATION FAILED SELL #", ticket, ": newSL=", DoubleToString(newSL, digits), " > currentSL=", DoubleToString(currentSL, digits), " - BỐ QUA!");
                  continue; // Bỏ qua position này
               }
            }
            
            if(!finalValidation)
            {
               Print("❌ CRITICAL ERROR: Final validation failed for #", ticket);
               continue;
            }
            
            if(trade.PositionModify(ticket, newSL, newTP))
            {
               string typeStr = (posType == POSITION_TYPE_BUY) ? "BUY" : "SELL";
               Print("✅ TRAILING ", typeStr, " #", ticket, " - Profit: ", DoubleToString(profitPips, 1), " pips");
               
               if(shouldModifySL)
                  Print("   SL: ", DoubleToString(currentSL, digits), " → ", DoubleToString(newSL, digits), " (Giữ ", DoubleToString(TrailingStopPips, 1), " pips lời)");
               
               if(shouldModifyTP)
                  Print("   TP: ", DoubleToString(currentTP, digits), " → ", DoubleToString(newTP, digits));
            }
            else
            {
               Print("⚠️ TRAILING FAILED #", ticket, " - Error: ", trade.ResultRetcode(), " (", trade.ResultRetcodeDescription(), ")");
            }
         }
      }
   }
}