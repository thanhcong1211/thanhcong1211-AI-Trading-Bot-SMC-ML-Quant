═══════════════════════════════════════════════════════════
  🤖 AI TRADING BOT - HƯỚNG DẪN KHỞI ĐỘNG
═══════════════════════════════════════════════════════════

📋 CÁC FILE KHỞI ĐỘNG:

1. ⭐ start_ai_trading.bat
   - Dùng cho: Local machine
   - Tự động kích hoạt virtualenv
   - Chạy với pattern report và webhook

2. 🌐 start_ai_trading_vps.bat  
   - Dùng cho: VPS (Administrator account)
   - Đường dẫn cố định cho VPS

3. 🚀 START_BOT.bat
   - Phiên bản đơn giản
   - Có kiểm tra và hướng dẫn chi tiết

═══════════════════════════════════════════════════════════

🎯 LỆNH CHẠY HIỆN TẠI:

python -u -m core.complete_ai_trading_system \
  --continuous \
  --min-confidence 60 \
  --pattern-report-enable \
  --pattern-report-every 10 \
  --pattern-webhook-url https://httpbin.org/post

═══════════════════════════════════════════════════════════

📊 THAM SỐ:

• --continuous              : Chạy liên tục (không dừng)
• --min-confidence 60       : Chỉ vào lệnh khi confidence ≥ 60%
• --pattern-report-enable   : Bật báo cáo pattern
• --pattern-report-every 10 : Báo cáo mỗi 10 signals
• --pattern-webhook-url     : URL nhận báo cáo (test: httpbin.org)
• -u                        : Unbuffered output (real-time logs)

═══════════════════════════════════════════════════════════

✅ TÍNH NĂNG ĐÃ BẬT:

✓ DrawdownProtector: 15% max loss
✓ RiskAI: Kiểm soát từng lệnh
✓ Signal Cooldown: 5s giữa các signal
✓ AI Processing Timeout: 30s
✓ Sleep: 2s (không spam)
✓ Pattern Recognition: Báo cáo mỗi 10 signals
✓ Webhook: POST kết quả lên httpbin.org

═══════════════════════════════════════════════════════════

🚀 CÁCH CHẠY:

Windows (Local):
  1. Double-click: start_ai_trading.bat
  2. Hoặc: START_BOT.bat (có hướng dẫn)

VPS:
  1. Copy thư mục live_trading lên VPS
  2. Đổi đường dẫn trong start_ai_trading_vps.bat nếu cần
  3. Double-click: start_ai_trading_vps.bat

═══════════════════════════════════════════════════════════

⚠️ LƯU Ý:

1. Bot sẽ TỰ ĐỘNG VÀO LỆNH khi có signal đạt yêu cầu
2. Nhấn Ctrl+C để dừng bot
3. Check log để xem AI dùng Model hay Fallback
4. Nếu thấy "FALLBACK" → Chạy train.bat để train model

═══════════════════════════════════════════════════════════

🔧 TROUBLESHOOTING:

Lỗi: "File not found"
→ File đã bị xóa hoặc đổi tên
→ Kiểm tra: core\complete_ai_trading_system.py tồn tại

Lỗi: "Python not found"  
→ Python chưa cài hoặc không trong PATH
→ Kích hoạt virtualenv trước

Lỗi: "Model not trained" (51% confidence)
→ Chạy: train.bat hoặc TRAIN_TRENDAI.bat

═══════════════════════════════════════════════════════════

📝 LOG FILES:

• Console output: Real-time trong terminal
• Webhook POST: httpbin.org/post (test only)
• Pattern reports: Mỗi 10 signals

═══════════════════════════════════════════════════════════
Updated: 2025-12-04
