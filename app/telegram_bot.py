# telegram_bot.py
import requests
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False, "telegram not configured"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:4000],
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, json=payload, timeout=20)
        return r.ok, r.text
    except Exception as e:
        return False, str(e)
