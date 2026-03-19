import asyncio
import os
import subprocess
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from app.config import TELEGRAM_BOT_TOKEN  # 重用你的 token

async def run_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """收到 /run_portfolio 就執行 daily portfolio"""
    await update.message.reply_text("🟡 開始執行 daily portfolio builder...")
    
    # 切到專案目錄 + venv + 跑腳本
    cmd = [
        "/home/daryl/Apps/portfolio-builder/.venv/bin/python",  # venv python [cite:22]
        "-m", "app.run_daily_portfolio"
    ]
    
    try:
        result = subprocess.run(cmd, cwd="/home/daryl/Apps/portfolio-builder", 
                               capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            await update.message.reply_text("✅ Portfolio builder 完成！\n檢查 log 或 VPS 上的 OpenClaw input 檔。")
        else:
            await update.message.reply_text(f"❌ 執行失敗：\n{result.stderr[:1000]}")
    except subprocess.TimeoutExpired:
        await update.message.reply_text("⏰ 執行超時（5 分鐘）")

async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("run_portfolio", run_portfolio))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())