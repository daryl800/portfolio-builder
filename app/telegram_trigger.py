# telegram_trigger.py
import asyncio
import subprocess
import sys
import logging
from pathlib import Path
from datetime import datetime
import platform
import threading

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
REQUEST_TIMEOUT_SECONDS = 600  # 10 minutes timeout (same as original)
STATUS_UPDATE_INTERVAL = 30  # Send status updates every 30 seconds

# Determine PROJECT_DIR based on OS
if platform.system() == "Darwin":  # macOS
    PROJECT_DIR = Path.home() / "develop/portfolio-builder"
else:  # Linux (including Raspberry Pi)
    PROJECT_DIR = Path.home() / "Apps/portfolio-builder"

# Determine the correct module name based on what exists
def get_module_name():
    """Auto-detect the correct portfolio module name"""
    # List of possible module names to try
    possible_modules = [
        "app.run_daily_portfolio",  # With underscores (used on Pi)
        "app.rundailyportfolio",     # Without underscores (used on Mac)
        "app.daily_portfolio",       # Alternative
        "app.portfolio",             # Another alternative
    ]
    
    # Check which module actually exists
    for module in possible_modules:
        module_parts = module.split('.')
        if len(module_parts) == 2:
            module_file = PROJECT_DIR / module_parts[0] / f"{module_parts[1]}.py"
            if module_file.exists():
                logger.info(f"Found module: {module} at {module_file}")
                return module
    
    # If none found, try to find any file with 'portfolio' in the name
    app_dir = PROJECT_DIR / "app"
    if app_dir.exists():
        portfolio_files = list(app_dir.glob("*portfolio*.py"))
        if portfolio_files:
            module_name = f"app.{portfolio_files[0].stem}"
            logger.info(f"Auto-detected module: {module_name}")
            return module_name
    
    # Default fallback
    logger.warning("No portfolio module found, using default")
    return "app.run_daily_portfolio"

MODULE_NAME = get_module_name()

class PortfolioBuilderTask:
    """Track the portfolio builder task with timeout and status updates"""
    
    def __init__(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.update = update
        self.context = context
        self.start_time = None
        self.timeout_timer = None
        self.status_timer = None
        self.result = None
        self.completed = False
        
    async def start(self):
        """Start the portfolio builder task"""
        self.start_time = datetime.now()
        
        # Send initial status
        await self.update.message.reply_text(
            f"🟡 開始執行 portfolio builder...\n"
            f"📦 模組: {MODULE_NAME}\n"
            f"⏱️ 超時設定: {REQUEST_TIMEOUT_SECONDS // 60} 分鐘\n"
            f"📊 狀態更新: 每 {STATUS_UPDATE_INTERVAL} 秒\n\n"
            f"🔄 執行中，請稍候..."
        )
        
        # Start periodic status updates
        self.status_timer = threading.Timer(
            STATUS_UPDATE_INTERVAL,
            lambda: asyncio.run_coroutine_threadsafe(
                self.send_status_update(),
                self.context.application.loop
            )
        )
        self.status_timer.start()
        
        try:
            result = await self.run_portfolio_builder()
            self.result = result
            self.completed = True
            await self.send_completion_message(result)
        except Exception as e:
            logger.exception(f"Task failed: {e}")
            if not self.completed:
                await self.update.message.reply_text(f"❌ 執行失敗: {str(e)[:500]}")
        finally:
            self.cleanup()
    
    async def run_portfolio_builder(self):
        """Execute the portfolio builder subprocess"""
        cmd = [
            str(PROJECT_DIR / ".venv/bin/python"),
            "-m", MODULE_NAME,
        ]
        
        # Check if Python executable exists
        python_path = Path(cmd[0])
        if not python_path.exists():
            raise FileNotFoundError(f"Python executable not found: {python_path}")
        
        logger.info(f"Running: {' '.join(cmd)} in {PROJECT_DIR}")
        
        # Run subprocess with timeout
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                cwd=PROJECT_DIR,
                capture_output=True,
                text=True,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        )
        
        return result
    
    async def send_status_update(self):
        """Send periodic status update"""
        if self.completed:
            return
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        remaining = REQUEST_TIMEOUT_SECONDS - elapsed
        
        if remaining > 0 and not self.completed:
            try:
                progress = min(100, int((elapsed / REQUEST_TIMEOUT_SECONDS) * 100))
                bar_length = 20
                filled = int(bar_length * progress / 100)
                bar = '█' * filled + '░' * (bar_length - filled)
                
                await self.update.message.reply_text(
                    f"🔄 執行中...\n\n"
                    f"[{bar}] {progress}%\n\n"
                    f"⏱️ 已過: {elapsed:.0f} 秒\n"
                    f"⏰ 剩餘: {remaining:.0f} 秒\n"
                    f"💡 請繼續等待..."
                )
                logger.info(f"Status update: {elapsed:.0f}s, {progress}%")
            except Exception as e:
                logger.error(f"Failed to send status update: {e}")
            
            if not self.completed:
                self.status_timer = threading.Timer(
                    STATUS_UPDATE_INTERVAL,
                    lambda: asyncio.run_coroutine_threadsafe(
                        self.send_status_update(),
                        self.context.application.loop
                    )
                )
                self.status_timer.start()
    
    async def send_completion_message(self, result):
        """Send completion message"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        if result.returncode == 0:
            await self.update.message.reply_text(
                f"✅ Portfolio builder 完成！\n"
                f"⏱️ 耗時: {elapsed:.1f} 秒\n"
                f"📁 請檢查 OpenClaw input。"
            )
            logger.info(f"Completed in {elapsed:.1f}s")
        else:
            error_msg = result.stderr or result.stdout or "unknown error"
            if len(error_msg) > 800:
                error_msg = error_msg[:800] + "..."
            await self.update.message.reply_text(
                f"❌ 失敗（返回碼 {result.returncode}）：\n{error_msg}"
            )
            logger.error(f"Failed with code {result.returncode}")
    
    def cleanup(self):
        """Clean up timers"""
        if self.timeout_timer:
            self.timeout_timer.cancel()
        if self.status_timer:
            self.status_timer.cancel()


async def run_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run_portfolio command"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    logger.info(f"Received /run_portfolio from user {user.id}")
    
    # Check authorization
    if chat_id != int(TELEGRAM_CHAT_ID):
        await update.message.reply_text("🚫 無權限，只有主人能用")
        return
    
    # Send immediate acknowledgment
    await update.message.reply_text(
        f"✅ 收到請求！\n"
        f"📦 模組: {MODULE_NAME}\n"
        f"⏱️ 超時: {REQUEST_TIMEOUT_SECONDS // 60} 分鐘\n\n"
        f"🔄 開始執行..."
    )
    
    # Create and start the task
    task = PortfolioBuilderTask(update, context)
    asyncio.create_task(task.start())


async def handle_unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle unknown commands and typos"""
    text = update.message.text
    user = update.effective_user
    
    if text.startswith('/'):
        logger.info(f"Unknown command: {text} from user {user.id}")
        
        # Check for common typos
        if text in ['/run-protfolio', '/runprotfolio', '/run-portfolio']:
            await update.message.reply_text(
                f"🤔 您輸入的是 `{text}`\n\n"
                f"正確的命令是 `/run_portfolio` (底線)\n\n"
                f"💡 使用 `/start` 查看所有可用命令",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❓ 未知命令: `{text}`\n\n"
                f"📋 可用命令:\n"
                f"• `/start` - 歡迎訊息\n"
                f"• `/run_portfolio` - 執行投組建構器\n"
                f"• `/status` - 系統狀態\n\n"
                f"💡 使用 `/start` 查看完整說明",
                parse_mode="Markdown"
            )
    else:
        # Handle non-command messages
        await update.message.reply_text(
            f"👋 您好！我是 portfolio trigger bot\n\n"
            f"請使用以下命令:\n"
            f"• `/start` - 顯示歡迎訊息\n"
            f"• `/run_portfolio` - 執行投組建構器\n"
            f"• `/status` - 查看系統狀態",
            parse_mode="Markdown"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    
    logger.info(f"User {user.id} started the bot")
    
    await update.message.reply_text(
        f"👋 嗨 {user.first_name}，我是 portfolio trigger bot\n\n"
        f"📊 **可用命令**:\n"
        f"• `/start` - 顯示此訊息\n"
        f"• `/run_portfolio` - 執行每日投組建構器\n"
        f"• `/status` - 查看系統狀態\n\n"
        f"⚙️ **當前配置**:\n"
        f"• 專案: `{PROJECT_DIR}`\n"
        f"• 模組: `{MODULE_NAME}`\n"
        f"• 超時: {REQUEST_TIMEOUT_SECONDS // 60} 分鐘\n\n"
        f"💡 提示: 輸入 `/run_portfolio` 開始執行",
        parse_mode="Markdown"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    chat_id = update.effective_chat.id
    
    if chat_id != int(TELEGRAM_CHAT_ID):
        await update.message.reply_text("🚫 無權限")
        return
    
    # Check paths
    python_path = PROJECT_DIR / ".venv/bin/python"
    module_file = PROJECT_DIR / "app" / f"{MODULE_NAME.split('.')[-1]}.py"
    
    status_lines = [
        "📊 **系統狀態**",
        "",
        f"📁 專案目錄: {'✅' if PROJECT_DIR.exists() else '❌'}",
        f"   `{PROJECT_DIR}`",
        "",
        f"🐍 Python: {'✅' if python_path.exists() else '❌'}",
        f"   `{python_path}`",
        "",
        f"📦 主要模組: {'✅' if module_file.exists() else '❌'}",
        f"   `{MODULE_NAME}`",
        "",
        f"⏱️ 超時設定: {REQUEST_TIMEOUT_SECONDS // 60} 分鐘",
        f"🖥️ 系統: {platform.system()} {platform.machine()}",
    ]
    
    await update.message.reply_text("\n".join(status_lines), parse_mode="Markdown")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(msg="Exception:", exc_info=context.error)
    
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ 處理錯誤，請稍後再試"
            )
        except Exception as e:
            logger.error(f"Failed to send error: {e}")


def main():
    """Main bot function"""
    import threading
    
    print("=" * 60)
    print(f"🚀 Starting Portfolio Bot at {datetime.now()}")
    print(f"🖥️  System: {platform.system()}")
    print("=" * 60)
    
    print(f"📁 PROJECT_DIR: {PROJECT_DIR}")
    print(f"📁 EXISTS: {PROJECT_DIR.exists()}")
    print(f"📦 MODULE: {MODULE_NAME}")
    print(f"⏱️ TIMEOUT: {REQUEST_TIMEOUT_SECONDS // 60} minutes")
    
    # Validate paths
    python_path = PROJECT_DIR / ".venv/bin/python"
    if python_path.exists():
        print(f"✅ Python: {python_path}")
    else:
        print(f"❌ Python not found: {python_path}")
    
    module_file = PROJECT_DIR / "app" / f"{MODULE_NAME.split('.')[-1]}.py"
    if module_file.exists():
        print(f"✅ Module file: {module_file}")
    else:
        print(f"❌ Module file not found: {module_file}")
        
        # Show available modules
        app_dir = PROJECT_DIR / "app"
        if app_dir.exists():
            print(f"\n📁 Available modules in app/:")
            for f in app_dir.glob("*.py"):
                print(f"   • {f.name}")
    
    print("=" * 60)
    
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set")
        return
    
    # Create application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("run_portfolio", run_portfolio))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(MessageHandler(filters.COMMAND, handle_unknown_command))
    application.add_error_handler(error_handler)
    
    print("🚀 Bot started! Available commands:")
    print("   /start - Welcome message")
    print("   /status - System status")
    print("   /run_portfolio - Execute portfolio builder")
    print("=" * 60)
    
    # Run bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()