//+------------------------------------------------------------------+
//|                                          Account_Analyzer_EA.mq5 |
//|                                    Matrix AI - Pro SMC Analyzer  |
//|                        Full Logic: SMC + OB + FVG + Liquidity    |
//+------------------------------------------------------------------+
#property copyright "Matrix AI"
#property link      ""
#property version   "3.0"
#property description "Full Matrix AI Logic - SMC Pro Level"
#property strict

#include <Trade\Trade.mqh>

//+------------------------------------------------------------------+
//| MATRIX AI CONFIG                                                 |
//+------------------------------------------------------------------+
#define ACCOUNT_TARGET      20000.0   // Vốn mục tiêu
#define RISK_PER_TRADE      0.01      // 1% risk/trade
#define MAX_DAILY_LOSS      0.02      // 2% max loss/day
#define DAILY_TARGET        500.0     // $500/ngày
#define MAX_TRADES_PER_DAY  5         // Tối đa 5 lệnh/ngày
#define RR_MIN              2.0       // 1:2 minimum
#define RR_OPTIMAL          3.0       // 1:3 optimal
#define TARGET_WINRATE      90.0      // 90% win rate

// SMC Settings
#define MIN_BOS_PIPS        15.0      // Min pips for BOS
#define MIN_CHOCH_PIPS      10.0      // Min pips for CHoCH
#define OB_LOOKBACK         20        // OB search bars
#define FVG_MIN_PIPS        5.0       // Min FVG size
#define LIQUIDITY_THRESHOLD 1.5       // Liquidity strength

//+------------------------------------------------------------------+
//| Input Parameters                                                 |
//+------------------------------------------------------------------+
input int UpdateIntervalSeconds = 10;  // Cập nhật mỗi X giây
input bool ShowDetailedAnalysis = true; // Hiển thị phân tích chi tiết

// AUTO TRADING SETTINGS
input bool EnableAutoTrading = true;    // BẬT tự động vào lệnh
input ENUM_TIMEFRAMES AnalysisTimeframe = PERIOD_M15;  // Khung phân tích (M5/M15/H1)
input ENUM_TIMEFRAMES HTFTrend = PERIOD_H1;            // Trend khung lớn (H1/H4/D1)
input double LotSize = 0.01;            // Lot size
input int MagicNumber = 888888;         // Magic number
input string TradeComment = "MatrixAI"; // Comment

//+------------------------------------------------------------------+
//| Global Variables                                                 |
//+------------------------------------------------------------------+
datetime lastUpdateTime = 0;
datetime todayStart = 0;
datetime lastTradeTime = 0;  // Prevent multiple trades

CTrade trade;  // Trade object

// Daily tracking
double dailyProfitToday = 0;
double dailyLossToday = 0;
int tradesCountToday = 0;
int winsToday = 0;
int lossesToday = 0;

// SMC tracking
string currentMarketStructure = "UNKNOWN";
string lastDetectedPattern = "NONE";
double lastLiquiditySweep = 0;
datetime lastStructureBreak = 0;

//+------------------------------------------------------------------+
//| Structures                                                       |
//+------------------------------------------------------------------+
struct OrderBlock
{
   datetime time;
   double highPrice;
   double lowPrice;
   double openPrice;
   double closePrice;
   string type;        // "BULLISH" / "BEARISH"
   double strength;    // 0-100
   bool hasSweep;
   bool valid;
};

struct FairValueGap
{
   datetime time;
   double gapHigh;
   double gapLow;
   double gapMid;
   string type;        // "BULLISH" / "BEARISH"
   bool filled;
   bool valid;
};

struct LiquiditySweep
{
   datetime time;
   double sweptPrice;
   string type;        // "HIGH" / "LOW"
   double strength;
   bool confirmed;
};

struct MarketStructure
{
   string trend;           // "BULLISH" / "BEARISH" / "RANGING"
   string lastBreak;       // "BOS" / "CHoCH" / "NONE"
   datetime breakTime;
   double breakPrice;
   double swingHigh;
   double swingLow;
   bool valid;
};

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   Print("========================================");
   Print("   MATRIX AI - ACCOUNT ANALYZER v3.0");
   Print("   Full SMC Pro: OB + FVG + Liquidity");
   Print("========================================");
   
   // Setup trade object
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(50);
   trade.SetTypeFilling(ORDER_FILLING_FOK);
   
   ResetDailyTracking();
   PrintMatrixConfig();
   PrintAccountInfo();
   
   // Phân tích SMC
   AnalyzeSMCStructure();
   
   // Phân tích positions
   AnalyzeCurrentPositions();
   
   // Phân tích history
   AnalyzeHistoryMatrixAI();
   
   // Đánh giá performance
   EvaluateBotPerformance();
   
   if(EnableAutoTrading)
      Print("\n🚀 AUTO TRADING: ENABLED");
   else
      Print("\n⏸️ AUTO TRADING: DISABLED (Analysis only)");
   
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("Matrix AI Analyzer stopped. Reason: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   ResetDailyTracking();
   
   if(TimeCurrent() - lastUpdateTime >= UpdateIntervalSeconds)
   {
      Comment(GetMatrixAISummary());
      lastUpdateTime = TimeCurrent();
      CheckRiskLimits();
      
      // AUTO TRADING LOGIC
      if(EnableAutoTrading)
      {
         CheckAndExecuteTrade();
      }
   }
}

//+------------------------------------------------------------------+
//| Reset Daily Tracking                                             |
//+------------------------------------------------------------------+
void ResetDailyTracking()
{
   datetime currentDay = iTime(_Symbol, PERIOD_D1, 0);
   
   if(todayStart != currentDay)
   {
      Print("\n========== NEW TRADING DAY RESET ==========");
      todayStart = currentDay;
      dailyProfitToday = 0;
      dailyLossToday = 0;
      tradesCountToday = 0;
      winsToday = 0;
      lossesToday = 0;
      Print("Daily counters reset: ", TimeToString(currentDay, TIME_DATE));
   }
}

//+------------------------------------------------------------------+
//| Print Matrix AI Configuration                                    |
//+------------------------------------------------------------------+
void PrintMatrixConfig()
{
   Print("\n========== MATRIX AI CONFIG ==========");
   Print("Account Target: $", ACCOUNT_TARGET);
   Print("Risk Per Trade: ", RISK_PER_TRADE * 100, "%");
   Print("Max Daily Loss: ", MAX_DAILY_LOSS * 100, "%");
   Print("Daily Target: $", DAILY_TARGET);
   Print("Max Trades/Day: ", MAX_TRADES_PER_DAY);
   Print("Min RR: 1:", RR_MIN);
   Print("Optimal RR: 1:", RR_OPTIMAL);
   Print("Target Win Rate: ", TARGET_WINRATE, "%");
   Print("\n--- SMC Settings ---");
   Print("Analysis Timeframe: ", EnumToString(AnalysisTimeframe));
   Print("HTF Trend: ", EnumToString(HTFTrend));
   Print("Min BOS: ", MIN_BOS_PIPS, " pips");
   Print("Min CHoCH: ", MIN_CHOCH_PIPS, " pips");
   Print("OB Lookback: ", OB_LOOKBACK, " bars");
   Print("Min FVG: ", FVG_MIN_PIPS, " pips");
   Print("Liquidity Threshold: ", LIQUIDITY_THRESHOLD);
}

//+------------------------------------------------------------------+
//| Print Account Information                                        |
//+------------------------------------------------------------------+
void PrintAccountInfo()
{
   Print("\n========== THÔNG TIN TÀI KHOẢN ==========");
   Print("Login: ", AccountInfoInteger(ACCOUNT_LOGIN));
   Print("Server: ", AccountInfoString(ACCOUNT_SERVER));
   Print("Name: ", AccountInfoString(ACCOUNT_NAME));
   Print("Type: ", (AccountInfoInteger(ACCOUNT_TRADE_MODE) == ACCOUNT_TRADE_MODE_DEMO ? "DEMO" : "REAL"));
   Print("Leverage: 1:", AccountInfoInteger(ACCOUNT_LEVERAGE));
   
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   
   Print("\n--- Vốn & Lợi nhuận ---");
   Print("Balance: $", DoubleToString(balance, 2));
   Print("Equity: $", DoubleToString(equity, 2));
   Print("Margin: $", DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN), 2));
   Print("Free Margin: $", DoubleToString(AccountInfoDouble(ACCOUNT_MARGIN_FREE), 2));
   Print("Profit: $", DoubleToString(AccountInfoDouble(ACCOUNT_PROFIT), 2));
   
   if(balance >= ACCOUNT_TARGET)
      Print("✅ Balance >= Target ($", ACCOUNT_TARGET, ")");
   else
      Print("⏳ Thiếu: $", DoubleToString(ACCOUNT_TARGET - balance, 2));
}

//+------------------------------------------------------------------+
//| Analyze SMC Structure (FULL LOGIC)                              |
//+------------------------------------------------------------------+
void AnalyzeSMCStructure()
{
   Print("\n========== SMC STRUCTURE ANALYSIS ==========");
   Print("Analysis TF: ", EnumToString(AnalysisTimeframe), " | HTF: ", EnumToString(HTFTrend));
   
   // 1. HTF Trend first
   MarketStructure htfStructure = DetectMarketStructure(HTFTrend);
   Print("\n🏗️ HTF TREND (", EnumToString(HTFTrend), "):");
   Print("Trend: ", htfStructure.trend);
   Print("Last Break: ", htfStructure.lastBreak);
   
   // 2. Market Structure (Analysis TF)
   MarketStructure structure = DetectMarketStructure(AnalysisTimeframe);
   Print("\n🏗️ MARKET STRUCTURE (", EnumToString(AnalysisTimeframe), "):");
   Print("Trend: ", structure.trend);
   Print("Last Break: ", structure.lastBreak);
   if(structure.breakTime > 0)
      Print("Break Time: ", TimeToString(structure.breakTime, TIME_DATE|TIME_MINUTES));
   Print("Swing High: ", DoubleToString(structure.swingHigh, _Digits));
   Print("Swing Low: ", DoubleToString(structure.swingLow, _Digits));
   
   // Check HTF alignment
   if(htfStructure.trend == structure.trend)
      Print("✅ HTF and LTF aligned (", structure.trend, ")");
   else
      Print("⚠️ HTF (", htfStructure.trend, ") vs LTF (", structure.trend, ") - Conflict");
   
   // 3. Liquidity Sweep
   LiquiditySweep sweep = DetectLiquiditySweep(AnalysisTimeframe, 50);
   Print("\n💧 LIQUIDITY SWEEP:");
   if(sweep.confirmed)
   {
      Print("✅ Detected: ", sweep.type, " sweep");
      Print("Price: ", DoubleToString(sweep.sweptPrice, _Digits));
      Print("Strength: ", DoubleToString(sweep.strength, 2));
      Print("Time: ", TimeToString(sweep.time, TIME_DATE|TIME_MINUTES));
   }
   else
   {
      Print("❌ No recent sweep");
   }
   
   // 4. Order Block
   OrderBlock ob = FindOrderBlock(AnalysisTimeframe, structure.trend);
   Print("\n📦 ORDER BLOCK:");
   if(ob.valid)
   {
      Print("✅ ", ob.type, " OB detected");
      Print("High: ", DoubleToString(ob.highPrice, _Digits));
      Print("Low: ", DoubleToString(ob.lowPrice, _Digits));
      Print("Strength: ", DoubleToString(ob.strength, 1), "%");
      Print("Has Sweep: ", (ob.hasSweep ? "YES ✅" : "NO"));
      Print("Time: ", TimeToString(ob.time, TIME_DATE|TIME_MINUTES));
   }
   else
   {
      Print("❌ No valid OB");
   }
   
   // 5. Fair Value Gap
   FairValueGap fvg = FindFVG(AnalysisTimeframe, structure.trend);
   Print("\n📊 FAIR VALUE GAP:");
   if(fvg.valid)
   {
      Print("✅ ", fvg.type, " FVG detected");
      Print("Gap High: ", DoubleToString(fvg.gapHigh, _Digits));
      Print("Gap Mid: ", DoubleToString(fvg.gapMid, _Digits));
      Print("Gap Low: ", DoubleToString(fvg.gapLow, _Digits));
      Print("Size: ", DoubleToString((fvg.gapHigh - fvg.gapLow) / SymbolInfoDouble(_Symbol, SYMBOL_POINT) / 10, 1), " pips");
      Print("Filled: ", (fvg.filled ? "YES" : "NO"));
   }
   else
   {
      Print("❌ No valid FVG");
   }
   
   // 6. Entry Conditions Check
   Print("\n🎯 ENTRY CONDITIONS (Matrix AI):");
   bool conditionMet = true;
   
   Print("\n✓ Checklist:");
   
   // HTF alignment
   if(htfStructure.trend == structure.trend || htfStructure.trend == "RANGING")
      Print("  ✅ HTF alignment OK");
   else
   {
      Print("  ⚠️ HTF conflict (", htfStructure.trend, " vs ", structure.trend, ")");
      conditionMet = false;
   }
   
   if(structure.valid && structure.lastBreak != "NONE")
      Print("  ✅ Structure break confirmed (", structure.lastBreak, ")");
   else
   {
      Print("  ❌ No structure break");
      conditionMet = false;
   }
   
   if(sweep.confirmed)
      Print("  ✅ Liquidity sweep present");
   else
      Print("  ⚠️ No sweep (optional)");
   
   if(ob.valid || fvg.valid)
      Print("  ✅ Entry zone identified (OB/FVG)");
   else
   {
      Print("  ❌ No entry zone");
      conditionMet = false;
   }
   
   if(conditionMet)
      Print("\n🚀 SETUP QUALITY: HIGH - Ready for entry");
   else
      Print("\n⏳ SETUP QUALITY: LOW - Wait for better conditions");
   
   Print("\n📌 Matrix AI: \"Chỉ trade khi ALL điều kiện = GREEN\"");
}

//+------------------------------------------------------------------+
//| Detect Market Structure                                          |
//+------------------------------------------------------------------+
MarketStructure DetectMarketStructure(ENUM_TIMEFRAMES tf)
{
   MarketStructure structure;
   structure.trend = "RANGING";
   structure.lastBreak = "NONE";
   structure.breakTime = 0;
   structure.breakPrice = 0;
   structure.valid = false;
   
   // Find swing highs and lows
   double swingHighs[];
   double swingLows[];
   ArrayResize(swingHighs, 0);
   ArrayResize(swingLows, 0);
   
   for(int i = 5; i < 100; i += 5)
   {
      double high = iHigh(_Symbol, tf, i);
      double low = iLow(_Symbol, tf, i);
      
      bool isSwingHigh = true;
      bool isSwingLow = true;
      
      for(int j = 1; j <= 3; j++)
      {
         if(iHigh(_Symbol, tf, i-j) >= high || iHigh(_Symbol, tf, i+j) >= high)
            isSwingHigh = false;
         if(iLow(_Symbol, tf, i-j) <= low || iLow(_Symbol, tf, i+j) <= low)
            isSwingLow = false;
      }
      
      if(isSwingHigh)
      {
         int size = ArraySize(swingHighs);
         ArrayResize(swingHighs, size + 1);
         swingHighs[size] = high;
      }
      
      if(isSwingLow)
      {
         int size = ArraySize(swingLows);
         ArrayResize(swingLows, size + 1);
         swingLows[size] = low;
      }
   }
   
   if(ArraySize(swingHighs) >= 2 && ArraySize(swingLows) >= 2)
   {
      structure.swingHigh = swingHighs[0];
      structure.swingLow = swingLows[0];
      
      // Check for BOS (Break of Structure)
      double currentPrice = iClose(_Symbol, tf, 0);
      double pipSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10;
      
      if(currentPrice > swingHighs[0] + MIN_BOS_PIPS * pipSize)
      {
         structure.trend = "BULLISH";
         structure.lastBreak = "BOS";
         structure.breakPrice = swingHighs[0];
         structure.valid = true;
      }
      else if(currentPrice < swingLows[0] - MIN_BOS_PIPS * pipSize)
      {
         structure.trend = "BEARISH";
         structure.lastBreak = "BOS";
         structure.breakPrice = swingLows[0];
         structure.valid = true;
      }
      // Check for CHoCH (Change of Character)
      else if(ArraySize(swingHighs) >= 2 && currentPrice < swingHighs[1] && currentPrice > swingLows[0])
      {
         if((swingHighs[0] - currentPrice) / pipSize >= MIN_CHOCH_PIPS)
         {
            structure.trend = "BEARISH";
            structure.lastBreak = "CHoCH";
            structure.breakPrice = swingHighs[0];
            structure.valid = true;
         }
      }
      else if(ArraySize(swingLows) >= 2 && currentPrice > swingLows[1] && currentPrice < swingHighs[0])
      {
         if((currentPrice - swingLows[0]) / pipSize >= MIN_CHOCH_PIPS)
         {
            structure.trend = "BULLISH";
            structure.lastBreak = "CHoCH";
            structure.breakPrice = swingLows[0];
            structure.valid = true;
         }
      }
   }
   
   return structure;
}

//+------------------------------------------------------------------+
//| Detect Liquidity Sweep                                           |
//+------------------------------------------------------------------+
LiquiditySweep DetectLiquiditySweep(ENUM_TIMEFRAMES tf, int lookback)
{
   LiquiditySweep sweep;
   sweep.confirmed = false;
   sweep.strength = 0;
   
   double highestHigh = 0;
   double lowestLow = DBL_MAX;
   int highBar = 0;
   int lowBar = 0;
   
   // Find recent highs/lows
   for(int i = 1; i < lookback; i++)
   {
      double high = iHigh(_Symbol, tf, i);
      double low = iLow(_Symbol, tf, i);
      
      if(high > highestHigh)
      {
         highestHigh = high;
         highBar = i;
      }
      
      if(low < lowestLow)
      {
         lowestLow = low;
         lowBar = i;
      }
   }
   
   double currentHigh = iHigh(_Symbol, tf, 0);
   double currentLow = iLow(_Symbol, tf, 0);
   double currentClose = iClose(_Symbol, tf, 0);
   double pipSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10;
   
   // Check for HIGH sweep (liquidity grab above)
   if(currentHigh > highestHigh && currentClose < highestHigh)
   {
      double sweepSize = (currentHigh - highestHigh) / pipSize;
      if(sweepSize >= 3 && sweepSize <= 20) // Realistic sweep
      {
         sweep.confirmed = true;
         sweep.type = "HIGH";
         sweep.sweptPrice = highestHigh;
         sweep.strength = MathMin(sweepSize / 10, 2.0);
         sweep.time = iTime(_Symbol, tf, 0);
      }
   }
   // Check for LOW sweep (liquidity grab below)
   else if(currentLow < lowestLow && currentClose > lowestLow)
   {
      double sweepSize = (lowestLow - currentLow) / pipSize;
      if(sweepSize >= 3 && sweepSize <= 20)
      {
         sweep.confirmed = true;
         sweep.type = "LOW";
         sweep.sweptPrice = lowestLow;
         sweep.strength = MathMin(sweepSize / 10, 2.0);
         sweep.time = iTime(_Symbol, tf, 0);
      }
   }
   
   return sweep;
}

//+------------------------------------------------------------------+
//| Find Order Block                                                 |
//+------------------------------------------------------------------+
OrderBlock FindOrderBlock(ENUM_TIMEFRAMES tf, string trend)
{
   OrderBlock ob;
   ob.valid = false;
   ob.strength = 0;
   ob.hasSweep = false;
   
   if(trend != "BULLISH" && trend != "BEARISH")
      return ob;
   
   // Find last impulse move
   for(int i = 1; i < OB_LOOKBACK; i++)
   {
      double open = iOpen(_Symbol, tf, i);
      double close = iClose(_Symbol, tf, i);
      double high = iHigh(_Symbol, tf, i);
      double low = iLow(_Symbol, tf, i);
      double pipSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10;
      
      double candleSize = MathAbs(close - open) / pipSize;
      
      if(trend == "BULLISH")
      {
         // Look for bearish candle before bullish impulse
         if(close < open && candleSize >= 5)
         {
            // Check if next candles are bullish impulse
            bool hasImpulse = false;
            for(int j = i - 1; j >= MathMax(i - 3, 0); j--)
            {
               double closeNext = iClose(_Symbol, tf, j);
               double openNext = iOpen(_Symbol, tf, j);
               if((closeNext - openNext) / pipSize >= 10)
               {
                  hasImpulse = true;
                  break;
               }
            }
            
            if(hasImpulse)
            {
               ob.valid = true;
               ob.type = "BULLISH";
               ob.highPrice = high;
               ob.lowPrice = low;
               ob.openPrice = open;
               ob.closePrice = close;
               ob.time = iTime(_Symbol, tf, i);
               ob.strength = MathMin(candleSize * 5, 100);
               
               // Check if OB has liquidity sweep
               LiquiditySweep sweep = DetectLiquiditySweep(tf, i + 10);
               if(sweep.confirmed && sweep.type == "LOW")
                  ob.hasSweep = true;
               
               break;
            }
         }
      }
      else if(trend == "BEARISH")
      {
         // Look for bullish candle before bearish impulse
         if(close > open && candleSize >= 5)
         {
            bool hasImpulse = false;
            for(int j = i - 1; j >= MathMax(i - 3, 0); j--)
            {
               double closeNext = iClose(_Symbol, tf, j);
               double openNext = iOpen(_Symbol, tf, j);
               if((openNext - closeNext) / pipSize >= 10)
               {
                  hasImpulse = true;
                  break;
               }
            }
            
            if(hasImpulse)
            {
               ob.valid = true;
               ob.type = "BEARISH";
               ob.highPrice = high;
               ob.lowPrice = low;
               ob.openPrice = open;
               ob.closePrice = close;
               ob.time = iTime(_Symbol, tf, i);
               ob.strength = MathMin(candleSize * 5, 100);
               
               LiquiditySweep sweep = DetectLiquiditySweep(tf, i + 10);
               if(sweep.confirmed && sweep.type == "HIGH")
                  ob.hasSweep = true;
               
               break;
            }
         }
      }
   }
   
   return ob;
}

//+------------------------------------------------------------------+
//| Find Fair Value Gap                                              |
//+------------------------------------------------------------------+
FairValueGap FindFVG(ENUM_TIMEFRAMES tf, string trend)
{
   FairValueGap fvg;
   fvg.valid = false;
   fvg.filled = false;
   
   double pipSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10;
   
   // Check last 20 candles for FVG
   for(int i = 1; i < 20; i++)
   {
      double high1 = iHigh(_Symbol, tf, i + 2);  // Candle 1
      double low1 = iLow(_Symbol, tf, i + 2);
      
      double high2 = iHigh(_Symbol, tf, i + 1);  // Candle 2 (middle)
      double low2 = iLow(_Symbol, tf, i + 1);
      
      double high3 = iHigh(_Symbol, tf, i);      // Candle 3
      double low3 = iLow(_Symbol, tf, i);
      
      // Bullish FVG: low3 > high1 (gap between candle 1 and 3)
      if(trend == "BULLISH" || trend == "RANGING")
      {
         if(low3 > high1)
         {
            double gapSize = (low3 - high1) / pipSize;
            if(gapSize >= FVG_MIN_PIPS)
            {
               fvg.valid = true;
               fvg.type = "BULLISH";
               fvg.gapHigh = low3;
               fvg.gapLow = high1;
               fvg.gapMid = (low3 + high1) / 2;
               fvg.time = iTime(_Symbol, tf, i);
               
               // Check if filled
               double currentLow = iLow(_Symbol, tf, 0);
               if(currentLow <= fvg.gapMid)
                  fvg.filled = true;
               
               break;
            }
         }
      }
      
      // Bearish FVG: high3 < low1
      if(trend == "BEARISH" || trend == "RANGING")
      {
         if(high3 < low1)
         {
            double gapSize = (low1 - high3) / pipSize;
            if(gapSize >= FVG_MIN_PIPS)
            {
               fvg.valid = true;
               fvg.type = "BEARISH";
               fvg.gapHigh = low1;
               fvg.gapLow = high3;
               fvg.gapMid = (low1 + high3) / 2;
               fvg.time = iTime(_Symbol, tf, i);
               
               // Check if filled
               double currentHigh = iHigh(_Symbol, tf, 0);
               if(currentHigh >= fvg.gapMid)
                  fvg.filled = true;
               
               break;
            }
         }
      }
   }
   
   return fvg;
}

//+------------------------------------------------------------------+
//| Analyze Current Positions (Matrix AI)                           |
//+------------------------------------------------------------------+
void AnalyzeCurrentPositions()
{
   Print("\n========== POSITIONS (MATRIX AI) ==========");
   
   int totalPositions = PositionsTotal();
   Print("Total: ", totalPositions);
   
   if(totalPositions == 0)
   {
      Print("✅ No open positions");
      Print("📌 Matrix AI: Waiting for perfect setup");
      return;
   }
   
   double totalProfit = 0;
   double totalRisk = 0;
   
   for(int i = 0; i < totalPositions; i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         string symbol = PositionGetString(POSITION_SYMBOL);
         long type = PositionGetInteger(POSITION_TYPE);
         double volume = PositionGetDouble(POSITION_VOLUME);
         double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
         double currentPrice = (type == POSITION_TYPE_BUY) ? SymbolInfoDouble(symbol, SYMBOL_BID) : SymbolInfoDouble(symbol, SYMBOL_ASK);
         double profit = PositionGetDouble(POSITION_PROFIT);
         double sl = PositionGetDouble(POSITION_SL);
         double tp = PositionGetDouble(POSITION_TP);
         
         double pipSize = SymbolInfoDouble(symbol, SYMBOL_POINT) * 10;
         double pips = (type == POSITION_TYPE_BUY) ? (currentPrice - openPrice) / pipSize : (openPrice - currentPrice) / pipSize;
         
         Print("\n--- #", ticket, " ---");
         Print(type == POSITION_TYPE_BUY ? "BUY ⬆️" : "SELL ⬇️");
         Print("Profit: $", DoubleToString(profit, 2), " (", DoubleToString(pips, 1), " pips)");
         
         // RR Analysis
         if(sl > 0 && tp > 0)
         {
            double riskPips = (type == POSITION_TYPE_BUY) ? (openPrice - sl) / pipSize : (sl - openPrice) / pipSize;
            double rewardPips = (type == POSITION_TYPE_BUY) ? (tp - openPrice) / pipSize : (openPrice - tp) / pipSize;
            double rr = rewardPips / riskPips;
            
            Print("RR: 1:", DoubleToString(rr, 1), (rr >= RR_MIN ? " ✅" : " ⚠️"));
            
            if(riskPips > 0)
            {
               double rMultiple = pips / riskPips;
               Print("Current R: ", DoubleToString(rMultiple, 2), "R");
               
               if(rMultiple >= 2.0)
                  Print("✅ +2R: Partial close recommended");
            }
         }
         
         totalProfit += profit;
      }
   }
   
   Print("\nTotal P&L: $", DoubleToString(totalProfit, 2));
}

//+------------------------------------------------------------------+
//| Analyze History Matrix AI                                        |
//+------------------------------------------------------------------+
void AnalyzeHistoryMatrixAI()
{
   Print("\n========== HISTORY TODAY ==========");
   
   datetime from = iTime(_Symbol, PERIOD_D1, 0);
   datetime to = TimeCurrent();
   
   if(!HistorySelect(from, to))
      return;
   
   int totalDeals = HistoryDealsTotal();
   if(totalDeals == 0)
   {
      Print("✅ No trades yet today");
      return;
   }
   
   int wins = 0, losses = 0;
   double profitWin = 0, profitLose = 0;
   
   for(int i = 0; i < totalDeals; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket > 0)
      {
         long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_OUT)
         {
            double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
            profit += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
            profit += HistoryDealGetDouble(ticket, DEAL_SWAP);
            
            if(profit > 0)
            {
               wins++;
               profitWin += profit;
            }
            else if(profit < 0)
            {
               losses++;
               profitLose += profit;
            }
         }
      }
   }
   
   int total = wins + losses;
   if(total > 0)
   {
      double winRate = ((double)wins / total) * 100;
      Print("Trades: ", total, " (", wins, "W / ", losses, "L)");
      Print("Win Rate: ", DoubleToString(winRate, 0), "%", (winRate >= TARGET_WINRATE ? " ✅" : " ⏳"));
      Print("Net: $", DoubleToString(profitWin + profitLose, 2));
   }
}

//+------------------------------------------------------------------+
//| Evaluate Bot Performance                                         |
//+------------------------------------------------------------------+
void EvaluateBotPerformance()
{
   Print("\n========== BOT PERFORMANCE ==========");
   
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   UpdateDailyPnL();
   
   Print("Balance: $", DoubleToString(balance, 2));
   Print("Target: $", DoubleToString(ACCOUNT_TARGET, 2), (balance >= ACCOUNT_TARGET ? " ✅" : " ⏳"));
   
   Print("\nToday Profit: $", DoubleToString(dailyProfitToday, 2));
   Print("Target: $", DoubleToString(DAILY_TARGET, 2), (dailyProfitToday >= DAILY_TARGET ? " 🎯" : ""));
   
   if(tradesCountToday > 0)
   {
      double wr = ((double)winsToday / tradesCountToday) * 100;
      Print("Win Rate: ", DoubleToString(wr, 0), "%", (wr >= TARGET_WINRATE ? " ⭐" : ""));
   }
   
   Print("\n📌 Matrix AI: Trade ít, trade ĐÚNG");
}

//+------------------------------------------------------------------+
//| Check Risk Limits                                                |
//+------------------------------------------------------------------+
void CheckRiskLimits()
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   UpdateDailyPnL();
   
   if(dailyLossToday >= balance * MAX_DAILY_LOSS)
      Print("🔴 STOP: Max loss reached");
   
   if(dailyProfitToday >= DAILY_TARGET)
      Print("🎯 STOP: Target reached");
   
   if(tradesCountToday >= MAX_TRADES_PER_DAY)
      Print("⛔ STOP: Max trades reached");
}

//+------------------------------------------------------------------+
//| Update Daily P&L                                                 |
//+------------------------------------------------------------------+
void UpdateDailyPnL()
{
   datetime from = iTime(_Symbol, PERIOD_D1, 0);
   datetime to = TimeCurrent();
   
   if(!HistorySelect(from, to))
      return;
   
   dailyProfitToday = 0;
   dailyLossToday = 0;
   tradesCountToday = 0;
   winsToday = 0;
   lossesToday = 0;
   
   int totalDeals = HistoryDealsTotal();
   for(int i = 0; i < totalDeals; i++)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket > 0)
      {
         long entry = HistoryDealGetInteger(ticket, DEAL_ENTRY);
         if(entry == DEAL_ENTRY_OUT)
         {
            double profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
            profit += HistoryDealGetDouble(ticket, DEAL_COMMISSION);
            profit += HistoryDealGetDouble(ticket, DEAL_SWAP);
            
            tradesCountToday++;
            if(profit > 0)
            {
               dailyProfitToday += profit;
               winsToday++;
            }
            else if(profit < 0)
            {
               dailyLossToday += MathAbs(profit);
               lossesToday++;
            }
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Get Matrix AI Summary                                            |
//+------------------------------------------------------------------+
string GetMatrixAISummary()
{
   string s = "========== MATRIX AI v3.0 ==========\n";
   s += "SMC Pro: OB + FVG + Liquidity\n\n";
   
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   s += "Balance: $" + DoubleToString(balance, 2) + "\n";
   
   UpdateDailyPnL();
   s += "Today: $" + DoubleToString(dailyProfitToday, 2);
   s += " / $" + DoubleToString(DAILY_TARGET, 2) + "\n";
   
   s += "Trades: " + IntegerToString(tradesCountToday);
   s += " / " + IntegerToString(MAX_TRADES_PER_DAY) + "\n";
   
   if(tradesCountToday > 0)
   {
      double wr = ((double)winsToday / tradesCountToday) * 100;
      s += "Win Rate: " + DoubleToString(wr, 0) + "%\n";
   }
   
   s += "\nPositions: " + IntegerToString(PositionsTotal()) + "\n";
   s += "\n📌 Trade ít, trade ĐÚNG\n";
   
   if(EnableAutoTrading)
      s += "🚀 AUTO TRADE: ON\n";
   else
      s += "⏸️ AUTO TRADE: OFF\n";
   
   s += TimeToString(TimeCurrent(), TIME_MINUTES);
   
   return s;
}

//+------------------------------------------------------------------+
//| Check And Execute Trade (Matrix AI Logic)                       |
//+------------------------------------------------------------------+
void CheckAndExecuteTrade()
{
   // SAFETY CHECKS
   UpdateDailyPnL();
   
   // Check 1: Max trades per day
   if(tradesCountToday >= MAX_TRADES_PER_DAY)
   {
      if(tradesCountToday == MAX_TRADES_PER_DAY)
         Print("⛔ Max trades reached (", MAX_TRADES_PER_DAY, ") - STOP trading");
      return;
   }
   
   // Check 2: Daily loss limit
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(dailyLossToday >= balance * MAX_DAILY_LOSS)
   {
      Print("🔴 Max daily loss reached - STOP trading");
      return;
   }
   
   // Check 3: Daily target reached
   if(dailyProfitToday >= DAILY_TARGET)
   {
      Print("🎯 Daily target reached - STOP trading");
      return;
   }
   
   // Check 4: Already have position
   if(HasOpenPosition())
   {
      return; // Only 1 position at a time
   }
   
   // Check 5: Cooldown (1 minute between trades)
   if(TimeCurrent() - lastTradeTime < 60)
   {
      return;
   }
   
   // MATRIX AI ENTRY LOGIC
   Print("\n🔍 Checking entry conditions...");
   
   // Check HTF trend first
   MarketStructure htfStructure = DetectMarketStructure(HTFTrend);
   Print("HTF (", EnumToString(HTFTrend), ") Trend: ", htfStructure.trend);
   
   MarketStructure structure = DetectMarketStructure(AnalysisTimeframe);
   
   Print("Structure (", EnumToString(AnalysisTimeframe), ") - Trend: ", structure.trend, " | Break: ", structure.lastBreak, " | Valid: ", structure.valid);
   
   // HTF alignment check
   if(htfStructure.trend != "RANGING" && htfStructure.trend != structure.trend)
   {
      Print("❌ HTF conflict: ", htfStructure.trend, " vs ", structure.trend, " - Waiting...");
      return;
   }
   
   if(!structure.valid || structure.lastBreak == "NONE")
   {
      Print("❌ No valid structure break - Waiting...");
      return;
   }
   
   LiquiditySweep sweep = DetectLiquiditySweep(AnalysisTimeframe, 50);
   Print("Liquidity Sweep: ", (sweep.confirmed ? "YES ✅" : "NO"));
   
   OrderBlock ob = FindOrderBlock(AnalysisTimeframe, structure.trend);
   Print("Order Block: ", (ob.valid ? "YES ✅" : "NO"));
   
   FairValueGap fvg = FindFVG(AnalysisTimeframe, structure.trend);
   Print("FVG: ", (fvg.valid ? "YES ✅" : "NO"));
   
   // ENTRY CONDITION: Must have structure + (OB or FVG)
   if(!ob.valid && !fvg.valid)
   {
      Print("❌ No entry zone (OB/FVG) - Waiting...");
      return;
   }
   
   // Check if price is in entry zone
   double currentPrice = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double currentBid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   bool inEntryZone = false;
   
   Print("Current Price: ", DoubleToString(currentPrice, _Digits));
   
   if(structure.trend == "BULLISH")
   {
      // For BUY: Check if price touched OB or FVG
      if(ob.valid)
      {
         Print("OB Zone: ", DoubleToString(ob.lowPrice, _Digits), " - ", DoubleToString(ob.highPrice, _Digits));
         if(currentBid <= ob.highPrice && currentBid >= ob.lowPrice)
         {
            inEntryZone = true;
            Print("✅ Price IN OB zone!");
         }
         else
         {
            Print("⏳ Price NOT in OB zone yet");
         }
      }
      
      if(fvg.valid && !inEntryZone)
      {
         Print("FVG Zone: ", DoubleToString(fvg.gapLow, _Digits), " - ", DoubleToString(fvg.gapHigh, _Digits));
         if(currentBid <= fvg.gapHigh && currentBid >= fvg.gapLow)
         {
            inEntryZone = true;
            Print("✅ Price IN FVG zone!");
         }
         else
         {
            Print("⏳ Price NOT in FVG zone yet");
         }
      }
   }
   else if(structure.trend == "BEARISH")
   {
      // For SELL: Check if price touched OB or FVG
      if(ob.valid)
      {
         Print("OB Zone: ", DoubleToString(ob.lowPrice, _Digits), " - ", DoubleToString(ob.highPrice, _Digits));
         if(currentPrice >= ob.lowPrice && currentPrice <= ob.highPrice)
         {
            inEntryZone = true;
            Print("✅ Price IN OB zone!");
         }
         else
         {
            Print("⏳ Price NOT in OB zone yet");
         }
      }
      
      if(fvg.valid && !inEntryZone)
      {
         Print("FVG Zone: ", DoubleToString(fvg.gapLow, _Digits), " - ", DoubleToString(fvg.gapHigh, _Digits));
         if(currentPrice >= fvg.gapLow && currentPrice <= fvg.gapHigh)
         {
            inEntryZone = true;
            Print("✅ Price IN FVG zone!");
         }
         else
         {
            Print("⏳ Price NOT in FVG zone yet");
         }
      }
   }
   
   if(!inEntryZone)
   {
      Print("❌ Price not in entry zone - Waiting for pullback...");
      return;
   }
   
   Print("🚀 ALL CONDITIONS MET - EXECUTING TRADE...");
   
   // CALCULATE SL & TP
   double sl = 0;
   double tp = 0;
   double pipSize = SymbolInfoDouble(_Symbol, SYMBOL_POINT) * 10;
   
   if(structure.trend == "BULLISH")
   {
      // BUY: SL below OB/FVG
      if(ob.valid)
         sl = ob.lowPrice - 5 * pipSize;
      else if(fvg.valid)
         sl = fvg.gapLow - 5 * pipSize;
      
      double riskPips = (currentPrice - sl) / pipSize;
      tp = currentPrice + (riskPips * RR_OPTIMAL * pipSize);
      
      Print("BUY Setup:");
      Print("  Entry: ", DoubleToString(currentPrice, _Digits));
      Print("  SL: ", DoubleToString(sl, _Digits), " (", DoubleToString(riskPips, 1), " pips risk)");
      Print("  TP: ", DoubleToString(tp, _Digits), " (RR 1:", DoubleToString(RR_OPTIMAL, 1), ")");
      
      // EXECUTE BUY
      if(ExecuteBuyTrade(currentPrice, sl, tp))
      {
         Print("\n✅ BUY EXECUTED (Matrix AI)");
         Print("Structure: ", structure.lastBreak);
         Print("OB: ", (ob.valid ? "YES" : "NO"));
         Print("FVG: ", (fvg.valid ? "YES" : "NO"));
         Print("Sweep: ", (sweep.confirmed ? "YES" : "NO"));
         
         lastTradeTime = TimeCurrent();
      }
   }
   else if(structure.trend == "BEARISH")
   {
      // SELL: SL above OB/FVG
      if(ob.valid)
         sl = ob.highPrice + 5 * pipSize;
      else if(fvg.valid)
         sl = fvg.gapHigh + 5 * pipSize;
      
      double riskPips = (sl - currentBid) / pipSize;
      tp = currentBid - (riskPips * RR_OPTIMAL * pipSize);
      
      Print("SELL Setup:");
      Print("  Entry: ", DoubleToString(currentBid, _Digits));
      Print("  SL: ", DoubleToString(sl, _Digits), " (", DoubleToString(riskPips, 1), " pips risk)");
      Print("  TP: ", DoubleToString(tp, _Digits), " (RR 1:", DoubleToString(RR_OPTIMAL, 1), ")");
      
      // EXECUTE SELL
      if(ExecuteSellTrade(currentBid, sl, tp))
      {
         Print("\n✅ SELL EXECUTED (Matrix AI)");
         Print("Structure: ", structure.lastBreak);
         Print("OB: ", (ob.valid ? "YES" : "NO"));
         Print("FVG: ", (fvg.valid ? "YES" : "NO"));
         Print("Sweep: ", (sweep.confirmed ? "YES" : "NO"));
         
         lastTradeTime = TimeCurrent();
      }
   }
}

//+------------------------------------------------------------------+
//| Execute Buy Trade                                                |
//+------------------------------------------------------------------+
bool ExecuteBuyTrade(double price, double sl, double tp)
{
   double normalizedSL = NormalizeDouble(sl, _Digits);
   double normalizedTP = NormalizeDouble(tp, _Digits);
   
   if(trade.Buy(LotSize, _Symbol, price, normalizedSL, normalizedTP, TradeComment))
   {
      return true;
   }
   else
   {
      Print("❌ BUY failed: ", trade.ResultRetcodeDescription());
      return false;
   }
}

//+------------------------------------------------------------------+
//| Execute Sell Trade                                               |
//+------------------------------------------------------------------+
bool ExecuteSellTrade(double price, double sl, double tp)
{
   double normalizedSL = NormalizeDouble(sl, _Digits);
   double normalizedTP = NormalizeDouble(tp, _Digits);
   
   if(trade.Sell(LotSize, _Symbol, price, normalizedSL, normalizedTP, TradeComment))
   {
      return true;
   }
   else
   {
      Print("❌ SELL failed: ", trade.ResultRetcodeDescription());
      return false;
   }
}

//+------------------------------------------------------------------+
//| Check if has open position                                       |
//+------------------------------------------------------------------+
bool HasOpenPosition()
{
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket > 0)
      {
         if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
            PositionGetInteger(POSITION_MAGIC) == MagicNumber)
         {
            return true;
         }
      }
   }
   return false;
}
//+------------------------------------------------------------------+
