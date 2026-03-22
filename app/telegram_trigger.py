#!/usr/bin/env python3
import asyncio
import subprocess
from pathlib import Path

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

PROJECT_DIR = Path.home() / "Apps/portfolio-builder"

async def run_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id != int(TELEGRAM_CHAT_ID):
        await update.message.reply_text("🚫 無權限，只有主人能用")
        return

    await update.message.reply_text("🟡 開始執行 portfolio builder...")

    cmd = [
        str(PROJECT_DIR / ".venv/bin/python"),
        "-m", "app.run_daily_portfolio",
    ]

    try:
        # Run the subprocess in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=600,
            )
        )

        if result.returncode == 0:
            await update.message.reply_text(
                "✅ Portfolio builder 完成！\n請檢查 VPS 上的 OpenClaw input。"
            )
        else:
            error_msg = result.stderr or result.stdout or "unknown error"
            await update.message.reply_text(f"❌ 失敗：\n{error_msg[:1000]}")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏰ 超時（10 分鐘），可能卡在 yfinance")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 嗨，我是 Pi 上的 portfolio trigger。\n用 /run_portfolio 來跑每日投組。")

def main():
    print(f"DEBUG: TELEGRAM_BOT_TOKEN exists: {bool(TELEGRAM_BOT_TOKEN)}")
    print(f"DEBUG: TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN 沒設")
        return

    # Create the Application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("run_portfolio", run_portfolio))

    print("🚀 Bot 啟動！到 Telegram 打 /run_portfolio")
    
    # Run the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
