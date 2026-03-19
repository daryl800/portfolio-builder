import feedparser
from datetime import datetime
from app.models import NewsItem

def fetch_yahoo_news(symbol: str, limit: int = 3):
    urls = [f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={symbol}&region=US&lang=en-US"]
    if symbol.endswith(".HK"):
        hk_code = symbol.replace(".HK", "")
        urls.append(f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={hk_code}&region=HK&lang=zh-Hant-HK")

    entries = []
    for url in urls:
        feed = feedparser.parse(url)
        if getattr(feed, "entries", None):
            entries = feed.entries
            break

    news = []
    for entry in entries[:limit]:
        published = ""
        try:
            if entry.get("published_parsed"):
                dt = datetime(*entry.published_parsed[:6])
                published = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

        news.append(NewsItem(
            title=entry.get("title", "").strip(),
            summary=entry.get("summary", "").strip(),
            published=published
        ))

    return news
