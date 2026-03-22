# telegram_trigger.py
import asyncio
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timezone
import platform
import time

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import NetworkError, TimedOut
from telegram.request import HTTPXRequest

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Project directory (macOS vs Linux)
if platform.system() == "Darwin":
    PROJECT_DIR = Path.home() / "develop/portfolio-builder"
else:
    PROJECT_DIR = Path.home() / "Apps/portfolio-builder"

# Hardcoded module name
MODULE = "app.run_daily_portfolio"


async def run_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Run the portfolio builder via subprocess with status updates."""
    chat_id = update.effective_chat.id
    user = update.effective_user

    print(f"Received /run_portfolio from user {user.id}")

    if chat_id != int(TELEGRAM_CHAT_ID):
        await update.message.reply_text("🚫 無權限，只有主人能用")
        return

    start_time = datetime.now(timezone.utc)
    await update.message.reply_text(
        f"🟡 開始執行 portfolio builder...\n"
        f"📦 模組: {MODULE}\n"
        f"⏱️ 超時: 5 分鐘\n\n"
        f"🔄 執行中，請稍候..."
    )

    cmd = [str(PROJECT_DIR / ".venv/bin/python"), "-m", MODULE]

    # Status update machinery
    loop = asyncio.get_event_loop()
    stop_status = threading.Event()
    status_count = 0

    def send_status():
        nonlocal status_count
        if stop_status.is_set():
            return
        status_count += 1

        async def send():
            try:
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                remaining = 300 - elapsed
                if remaining > 0:
                    msg = (f"🔄 執行中... ({status_count})\n"
                           f"⏱️ 已過: {elapsed:.0f} 秒\n"
                           f"⏰ 剩餘: {remaining:.0f} 秒\n"
                           f"💡 請繼續等待...")
                else:
                    msg = "🔄 仍在執行中，請繼續等待..."
                await update.message.reply_text(msg)
                print(f"Sent status update #{status_count} at {elapsed:.0f}s")
            except Exception as e:
                print(f"Failed to send status: {e}")

        asyncio.run_coroutine_threadsafe(send(), loop)

    def status_scheduler():
        while not stop_status.is_set():
            time.sleep(30)
            if not stop_status.is_set():
                send_status()

    scheduler = threading.Thread(target=status_scheduler, daemon=True)
    scheduler.start()

    try:
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes
            )
        )
        stop_status.set()
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Print all output to console ONLY (not to Telegram)
        print("\n" + "=" * 60)
        print("PORTFOLIO BUILDER OUTPUT:")
        print("=" * 60)
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("ERROR OUTPUT:")
            print(result.stderr)
        print("=" * 60 + "\n")

        if result.returncode == 0:
            # Only send simple completion message to Telegram
            await update.message.reply_text(
                f"✅ Portfolio builder 完成！\n"
                f"⏱️ 耗時: {elapsed:.1f} 秒\n"
                f"📁 請檢查 VPS 上的 OpenClaw input。"
            )
            print(f"Portfolio builder completed in {elapsed:.1f}s")
        else:
            error_msg = result.stderr or result.stdout or "unknown error"
            if len(error_msg) > 800:
                error_msg = error_msg[:800] + "..."
            await update.message.reply_text(
                f"❌ 失敗（返回碼 {result.returncode}）：\n{error_msg}"
            )
            print(f"Portfolio builder failed with code {result.returncode}")

    except subprocess.TimeoutExpired:
        stop_status.set()
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        await update.message.reply_text(
            f"⏰ 超時（5 分鐘）\n"
            f"⏱️ 實際執行: {elapsed:.1f} 秒\n"
            f"可能卡在 yfinance 或其他操作"
        )
        print(f"Portfolio builder timed out after {elapsed:.1f}s")

    except Exception as e:
        stop_status.set()
        await update.message.reply_text(
            f"❌ 錯誤：{str(e)[:500]}\n\n"
            f"💡 提示：檢查日誌獲取更多資訊"
        )
        print(f"Portfolio builder error: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message."""
    await update.message.reply_text(
        f"👋 嗨，我是 portfolio trigger bot\n\n"
        f"📊 **可用命令**:\n"
        f"• `/run_portfolio` - 執行每日投組建構器\n"
        f"• `/status` - 查看系統狀態\n\n"
        f"⚙️ **當前配置**:\n"
        f"• 專案: {PROJECT_DIR}\n"
        f"• 模組: {MODULE}\n"
        f"• 系統: {platform.system()}\n\n"
        f"💡 輸入 `/run_portfolio` 開始執行\n"
        f"⏱️ 超時設定: 5 分鐘\n"
        f"📊 狀態更新: 每 30 秒",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show system status (paths, network)."""
    if update.effective_chat.id != int(TELEGRAM_CHAT_ID):
        await update.message.reply_text("🚫 無權限")
        return

    python_path = PROJECT_DIR / ".venv/bin/python"
    module_file = PROJECT_DIR / "app/run_daily_portfolio.py"

    # Simple network check
    network_ok = False
    try:
        import socket
        socket.create_connection(("api.telegram.org", 443), timeout=5)
        network_ok = True
    except:
        pass
    network_status = "✅ 正常" if network_ok else "❌ 無法連線到 Telegram API"

    status_msg = (
        f"📊 **系統狀態**\n\n"
        f"📁 專案目錄: {'✅' if PROJECT_DIR.exists() else '❌'}\n"
        f"   `{PROJECT_DIR}`\n\n"
        f"🐍 Python: {'✅' if python_path.exists() else '❌'}\n"
        f"   `{python_path}`\n\n"
        f"📦 主要模組: {'✅' if module_file.exists() else '❌'}\n"
        f"   `{MODULE}`\n\n"
        f"🌐 網路: {network_status}\n"
        f"🖥️ 系統: {platform.system()} {platform.machine()}\n"
        f"⏱️ 超時: 5 分鐘\n"
        f"🤖 Bot 狀態: ✅ 線上"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands and common typos."""
    text = update.message.text
    if not text.startswith('/'):
        await update.message.reply_text(
            f"👋 您好！我是 portfolio trigger bot\n\n"
            f"請使用以下命令:\n"
            f"• `/start` - 顯示歡迎訊息\n"
            f"• `/run_portfolio` - 執行投組建構器\n"
            f"• `/status` - 查看系統狀態\n\n"
            f"💡 提示: 所有命令都以斜線 `/` 開頭",
            parse_mode="Markdown"
        )
        return

    # Typos for run_portfolio
    if text in ('/run-protfolio', '/runprotfolio', '/run-portfolio'):
        await update.message.reply_text(
            f"🤔 您輸入的是 `{text}`\n\n"
            f"正確的命令是 `/run_portfolio` (底線)\n\n"
            f"💡 使用 `/start` 查看所有可用命令",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"❓ 未知命令: `{text}`\n\n"
            f"📋 **可用命令**:\n"
            f"• `/start` - 歡迎訊息\n"
            f"• `/run_portfolio` - 執行投組建構器\n"
            f"• `/status` - 系統狀態\n\n"
            f"💡 使用 `/start` 查看完整說明",
            parse_mode="Markdown"
        )


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Telegram API errors gracefully."""
    error = context.error
    if isinstance(error, NetworkError):
        print(f"Network error: {error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⚠️ **網路連線問題**\n\n"
                "無法連線到 Telegram API。\n\n"
                "可能原因：\n"
                "• 網路連線不穩定\n"
                "• 防火牆阻擋\n"
                "• DNS 解析問題\n\n"
                "Bot 會自動重試連線，請稍後再試。",
                parse_mode="Markdown"
            )
    elif isinstance(error, TimedOut):
        print(f"Timeout error: {error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "⏰ **請求超時**\n\n"
                "Telegram API 回應超時。\n\n"
                "請檢查網路連線後重試。",
                parse_mode="Markdown"
            )
    else:
        print(f"Unhandled error: {error}")
        if update and update.effective_message:
            await update.effective_message.reply_text(
                f"❌ **錯誤**: {str(error)[:200]}",
                parse_mode="Markdown"
            )


def main():
    """Start the Telegram bot."""
    print("=" * 60)
    print(f"🚀 Starting Portfolio Bot at {datetime.now()}")
    print(f"🖥️  System: {platform.system()}")
    print(f"📁 PROJECT_DIR: {PROJECT_DIR}")
    print(f"📦 MODULE: {MODULE}")
    print("=" * 60)

    # Quick startup checks
    python_path = PROJECT_DIR / ".venv/bin/python"
    module_file = PROJECT_DIR / "app/run_daily_portfolio.py"

    if not python_path.exists():
        print(f"❌ Python not found: {python_path}")
    else:
        print(f"✅ Python: {python_path}")

    if not module_file.exists():
        print(f"❌ Module not found: {module_file}")
        if (PROJECT_DIR / "app").exists():
            print("Available modules:")
            for f in (PROJECT_DIR / "app").glob("*.py"):
                print(f"   • {f.name}")
    else:
        print(f"✅ Module: {module_file}")

    # Network check
    try:
        import socket
        socket.create_connection(("api.telegram.org", 443), timeout=5)
        print("✅ Connected to Telegram API")
    except Exception as e:
        print(f"⚠️ Cannot connect to Telegram API: {e}")

    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return

    # Bot setup
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0
    )
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("run_portfolio", run_portfolio))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown))
    application.add_error_handler(error_handler)

    print("🚀 Bot started!")
    print("💡 Commands: /start, /status, /run_portfolio")
    print("=" * 60)

    # Run with auto‑reconnect on network errors
    while True:
        try:
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=1.0
            )
            break
        except NetworkError as e:
            print(f"Network error: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
        except Exception as e:
            print(f"Unexpected error: {e}")
            print("Restarting in 10 seconds...")
            time.sleep(10)


if __name__ == "__main__":
    main()