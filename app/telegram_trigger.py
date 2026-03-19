#!/usr/bin/env python3
import subprocess
import os
from pathlib import Path
from telegram.ext import Application, CommandHandler
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.report import send_telegram_message  # 可選

PROJECT_DIR = Path.home() / "Apps/portfolio-builder"

def run_portfolio(update, context):
    chat_id = update.effective_chat.id
    if chat_id != int(TELEGRAM_CHAT_ID):
        update.message.reply_text("🚫 無權限，只有主人能用")
        return
    
    update.message.reply_text("🟡 開始執行 <b>portfolio builder</b>...")
    
    cmd = [
        str(PROJECT_DIR / ".venv/bin/python"),
        "-m", "app.run_daily_portfolio"
    ]
    
    try:
        result = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, 
                               text=True, timeout=600)
        
        if result.returncode == 0:
            msg = "✅ <b>Portfolio builder 完成！</b>\n\n檢查 VPS OpenClaw input。"
            update.message.reply_text(msg, parse_mode="HTML")
        else:
            error_msg = result.stderr or result.stdout
            update.message.reply_text(f"❌ 失敗：\n<pre>{error_msg[:1000]}</pre>", parse_mode="HTML")
            
    except subprocess.TimeoutExpired:
        update.message.reply_text("⏰ 超時（10 分鐘）")

def main():
    print(f"DEBUG: TELEGRAM_BOT_TOKEN exists: {bool(TELEGRAM_BOT_TOKEN)}")
    print(f"DEBUG: TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN 沒設")
        return
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("run_portfolio", run_portfolio))
    app.add_handler(CommandHandler("status", lambda u,c: u.message.reply_text("Pi OK")))
    
    print("🚀 Bot 啟動！打 /run_portfolio 試試")
    app.run_polling(drop_pending_updates=True)  # 同步，超穩

if __name__ == "__main__":
    main()