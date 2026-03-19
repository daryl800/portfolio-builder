from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT_DIR / "input"
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"

HOLDINGS_CSV = INPUT_DIR / "holdings.csv"
WATCHLIST_CSV = INPUT_DIR / "watchlist.csv"

DAILY_PORTFOLIO_SNAPSHOT = DATA_DIR / "daily_portfolio_snapshot.json"
DAILY_PORTFOLIO_OC_INPUT = DATA_DIR / "daily_portfolio_openclaw_input.json"

# 報表輸出（給 report.py）
REPORT_JSON = OUTPUT_DIR / "daily_portfolio.json"
REPORT_MD = OUTPUT_DIR / "daily_portfolio.md"
REPORT_CSV = OUTPUT_DIR / "opportunities.csv"

# --- LLM / Telegram 設定（從環境變數讀） ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

VPS_USER = "ubuntu"
VPS_HOST = "lighthouse"
VPS_TARGET_PATH = "/home/ubuntu/scp_drive/portfolio-scout/input"
