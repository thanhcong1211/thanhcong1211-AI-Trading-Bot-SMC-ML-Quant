#property copyright "XGBoost 5M Trading - Backtest Version"
#property version   "1.1"
#property strict

/*
 ====================================================================
 ZmqTestEA_Backtest.mq5 - Phiên bản cho Strategy Tester
 
 Bot giao dịch với logic đơn giản để test trong Strategy Tester
 Không cần ZeroMQ/Python - sử dụng Moving Average crossover
 ====================================================================
*/

#include <Trade/Trade.mqh>

// ========== CẤU HÌNH GIAO DỊCH ==========
input bool     EnableTrading = true;                         // BẬT/TẮT giao dịch
input double   MaxRiskPct = 2.0;                             // % rủi ro tối đa (2%)

// ========== CẤU HÌNH LOT SIZE ==========
input bool     UseAutoLotByBalance = true;                   // Tự động tính Lot theo TK
input double   FixedLotSize = 0.01;                          // Lot cố định nếu không dùng auto
input double   MinLot = 0.01;                                // Lot tối thiểu
input double   MaxLot = 0.25;                                // Lot tối đa

// ========== CẤU HÌNH TP/SL ==========
input double   SLMultiplier = 2.0;                           // Hệ số SL (ATR × 2)
input double   TPMultiplier = 4.0;                           // Hệ số TP (ATR × 4)

// ========== LOGIC GIAO DỊCH (MA Crossover) ==========
input int      FastMA = 10;                                  // MA nhanh
input int      SlowMA = 30;                                  // MA chậm
input int      ATRPeriod = 14;                               // ATR period

// ========== BIẾN TOÀN CỤC ==========
CTrade trade;
int handleFastMA;
int handleSlowMA;
int handleATR;
double fastMABuffer[];
double slowMABuffer[];
double atrBuffer[];

datetime lastBarTime = 0;
int TradeCount = 0;

// ========== KHỞI ĐỘNG ==========
int OnInit()
{
   Print("═══════════════════════════════════════════════════");
   Print("🤖 ZmqTestEA_Backtest v1.1 - Backtest Version");
   Print("═══════════════════════════════════════════════════");
   Print("📊 Logic: MA Crossover (Fast:", FastMA, " / Slow:", SlowMA, ")");
   Print("💰 Rủi ro: ", DoubleToString(MaxRiskPct, 1), "%");
   Print("🎲 Giao dịch: ", EnableTrading ? "✅ BẬT" : "❌ TẮT");
   Print("═══════════════════════════════════════════════════");
   
   // Tạo indicators
   handleFastMA = iMA(_Symbol, PERIOD_CURRENT, FastMA, 0, MODE_EMA, PRICE_CLOSE);
   handleSlowMA = iMA(_Symbol, PERIOD_CURRENT, SlowMA, 0, MODE_EMA, PRICE_CLOSE);
   handleATR = iATR(_Symbol, PERIOD_CURRENT, ATRPeriod);
   
   if(handleFastMA == INVALID_HANDLE || handleSlowMA == INVALID_HANDLE || handleATR == INVALID_HANDLE)
   {
      Print("❌ Lỗi khởi tạo indicators");
      return INIT_FAILED;
   }
   
   ArraySetAsSeries(fastMABuffer, true);
   ArraySetAsSeries(slowMABuffer, true);
   ArraySetAsSeries(atrBuffer, true);
   
   Print("✅ Indicators khởi tạo thành công");
   return INIT_SUCCEEDED;
}

// ========== DỌN DẸP ==========
void OnDeinit(const int reason)
{
   IndicatorRelease(handleFastMA);
   IndicatorRelease(handleSlowMA);
   IndicatorRelease(handleATR);
   
   Print("═══════════════════════════════════════════════════");
   Print("📊 THỐNG KÊ GIAO DỊCH");
   Print("   Tổng lệnh: ", TradeCount);
   Print("═══════════════════════════════════════════════════");
}

// ========== TICK HANDLER ==========
void OnTick()
{
   // Chỉ giao dịch khi có nến mới
   datetime currentBarTime = iTime(_Symbol, PERIOD_CURRENT, 0);
   if(currentBarTime == lastBarTime)
      return;
   lastBarTime = currentBarTime;
   
   // Copy data indicators
   if(CopyBuffer(handleFastMA, 0, 0, 3, fastMABuffer) < 3) return;
   if(CopyBuffer(handleSlowMA, 0, 0, 3, slowMABuffer) < 3) return;
   if(CopyBuffer(handleATR, 0, 0, 1, atrBuffer) < 1) return;
   
   double fastMA_current = fastMABuffer[0];
   double fastMA_prev = fastMABuffer[1];
   double slowMA_current = slowMABuffer[0];
   double slowMA_prev = slowMABuffer[1];
   double atr = atrBuffer[0];
   
   // Kiểm tra có position đang mở không
   if(PositionsTotal() > 0)
      return; // Chỉ giao dịch 1 lệnh tại một thời điểm
   
   // TÍNH LOT SIZE
   double lotSize = CalculateLotSize(atr);
   
   // TÍNH TP/SL
   double sl = atr * SLMultiplier;
   double tp = atr * TPMultiplier;
   
   // SIGNAL: BUY khi FastMA cắt lên SlowMA
   if(fastMA_prev <= slowMA_prev && fastMA_current > slowMA_current)
   {
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double stopLoss = ask - sl;
      double takeProfit = ask + tp;
      
      if(!EnableTrading)
      {
         Print("📊 [SIMULATION] BUY Signal | Lot:", lotSize, " | SL:", stopLoss, " | TP:", takeProfit);
         return;
      }
      
      if(trade.Buy(lotSize, _Symbol, ask, stopLoss, takeProfit, "MA Crossover BUY"))
      {
         Print("✅ BUY thành công | Lot:", lotSize, " | SL:", stopLoss, " | TP:", takeProfit);
         TradeCount++;
      }
      else
      {
         Print("❌ BUY thất bại | Error:", GetLastError());
      }
   }
   
   // SIGNAL: SELL khi FastMA cắt xuống SlowMA
   else if(fastMA_prev >= slowMA_prev && fastMA_current < slowMA_current)
   {
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double stopLoss = bid + sl;
      double takeProfit = bid - tp;
      
      if(!EnableTrading)
      {
         Print("📊 [SIMULATION] SELL Signal | Lot:", lotSize, " | SL:", stopLoss, " | TP:", takeProfit);
         return;
      }
      
      if(trade.Sell(lotSize, _Symbol, bid, stopLoss, takeProfit, "MA Crossover SELL"))
      {
         Print("✅ SELL thành công | Lot:", lotSize, " | SL:", stopLoss, " | TP:", takeProfit);
         TradeCount++;
      }
      else
      {
         Print("❌ SELL thất bại | Error:", GetLastError());
      }
   }
}

// ========== TÍNH LOT SIZE ==========
double CalculateLotSize(double atr)
{
   if(!UseAutoLotByBalance)
      return NormalizeLot(FixedLotSize);
   
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   
   // Ngưỡng tự động theo tài khoản
   double baseLot = 0.01;
   if(balance >= 7000.0)
      baseLot = MaxLot;
   else if(balance >= 5000.0)
      baseLot = 0.10;
   else if(balance >= 2000.0)
      baseLot = 0.05;
   else
      baseLot = MinLot;
   
   // Tính theo rủi ro
   double riskAmount = balance * MaxRiskPct / 100.0;
   double slDistance = atr * SLMultiplier;
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   
   if(slDistance > 0 && tickValue > 0 && tickSize > 0)
   {
      double slPips = slDistance / tickSize;
      double riskLot = riskAmount / (slPips * tickValue);
      baseLot = MathMin(baseLot, riskLot);
   }
   
   return NormalizeLot(baseLot);
}

// ========== CHUẨN HÓA LOT ==========
double NormalizeLot(double lot)
{
   double minLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double stepLot = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   
   lot = MathMax(lot, minLot);
   lot = MathMin(lot, maxLot);
   lot = MathRound(lot / stepLot) * stepLot;
   
   return lot;
}
