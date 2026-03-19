# llm_analysis.py
import json
from openai import OpenAI
from app.config import OPENAI_API_KEY, OPENAI_MODEL
from app.models import LLMAnalysis, NewsItem

client = OpenAI(api_key=OPENAI_API_KEY)

LLM_CALL_COUNT = 0


def analyze_stock_news(symbol: str, news_list: list[NewsItem]) -> LLMAnalysis:
    if not OPENAI_API_KEY:
        return LLMAnalysis(
            sentiment="中性",
            short_term_view="未設定 OPENAI_API_KEY，略過分析",
            long_term_view="未設定 OPENAI_API_KEY，略過分析",
            risks=["API key missing"],
            action_label="watch",
            confidence=20,
        )

    news_text = "\n".join(
        f"- {n.published} | {n.title} | {n.summary}"
        for n in news_list if n.title
    ) or "No important news found."

    prompt = f"""
你是一位謹慎的股票研究助理。請根據 {symbol} 的最新新聞做摘要。
請只輸出 JSON，不要輸出 markdown，不要加註解。

JSON schema:
{{
  "sentiment": "積極|中性|消極",
  "short_term_view": "一句話",
  "long_term_view": "一句話",
  "risks": ["風險1", "風險2"],
  "action_label": "watch|review|hold|avoid",
  "confidence": 0
}}

新聞如下：
{news_text}
""".strip()

    try:
        global LLM_CALL_COUNT
        LLM_CALL_COUNT += 1
        print(
            f"[LLM] call #{LLM_CALL_COUNT} - single - symbol={symbol}",
            flush=True,
        )
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a careful financial research assistant. Reply in Traditional Chinese and valid JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content.strip()
        data = json.loads(content)
        return LLMAnalysis(
            sentiment=data.get("sentiment", "中性"),
            short_term_view=data.get("short_term_view", ""),
            long_term_view=data.get("long_term_view", ""),
            risks=data.get("risks", []),
            action_label=data.get("action_label", "watch"),
            confidence=int(data.get("confidence", 50)),
        )
    except Exception as e:
        return LLMAnalysis(
            sentiment="中性",
            short_term_view=f"分析失敗: {e}",
            long_term_view="",
            risks=["LLM parsing failed"],
            action_label="watch",
            confidence=10,
        )
    
##########################################################
    
from collections import defaultdict
from typing import Iterable, Dict, List, Tuple

from app.models import LLMAnalysis, NewsItem

def analyze_stock_news_batch(
    items: Iterable[tuple[str, list[NewsItem]]]
) -> Dict[str, LLMAnalysis]:
    """
    批次分析多檔股票新聞。

    :param items: 例如 [("AAPL", [NewsItem, ...]), ("MSFT", [NewsItem, ...])]
    :return: { "AAPL": LLMAnalysis(...), "MSFT": LLMAnalysis(...) }
    """
    items = list(items)
    if not items:
        return {}

    if not OPENAI_API_KEY:
        # 沒 API key 時，全部回 fallback，和單檔版一致
        return {
            symbol: LLMAnalysis(
                sentiment="中性",
                short_term_view="未設定 OPENAI_API_KEY，略過分析",
                long_term_view="未設定 OPENAI_API_KEY，略過分析",
                risks=["API key missing"],
                action_label="watch",
                confidence=20,
            )
            for symbol, _ in items
        }

    # 準備批次新聞文字
    blocks: List[str] = []
    for symbol, news_list in items:
        news_text = "\n".join(
            f"- {n.published} | {n.title} | {n.summary}"
            for n in news_list if n.title
        ) or "No important news found."

        block = f"""### {symbol}
{news_text}
"""
        blocks.append(block)

    combined_news = "\n\n".join(blocks)

    # prompt：要求回傳一個 JSON array，每個 element 對應一檔股票
    schema = """
[
  {
    "symbol": "AAPL",
    "sentiment": "積極|中性|消極",
    "short_term_view": "一句話",
    "long_term_view": "一句話",
    "risks": ["風險1", "風險2"],
    "action_label": "watch|review|hold|avoid",
    "confidence": 0
  }
]
""".strip()

    prompt = f"""
你是一位謹慎的股票研究助理。以下是多檔股票的最新新聞，請依照每個「### SYMBOL」區塊，分別輸出一個 JSON 物件，最後組成一個 JSON array。

請嚴格遵守：
- 只輸出 JSON，不要輸出 markdown 或註解
- 每檔股票都要有一個物件
- symbol 欄位必須和標題中的 SYMBOL 相同

JSON schema 範例：
{schema}

新聞區塊如下：
{combined_news}
""".strip()

    try:
        global LLM_CALL_COUNT
        LLM_CALL_COUNT += 1
        print(
            f"[LLM] call #{LLM_CALL_COUNT} - batch - symbols={[s for s, _ in items]}",
            flush=True,
        )

        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful financial research assistant. "
                        "Reply in Traditional Chinese and valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = resp.choices[0].message.content.strip()
        data = json.loads(content)

        # 轉成 {symbol: LLMAnalysis}
        result: Dict[str, LLMAnalysis] = {}
        for item in data:
            symbol = item.get("symbol", "").strip().upper()
            if not symbol:
                continue
            result[symbol] = LLMAnalysis(
                sentiment=item.get("sentiment", "中性"),
                short_term_view=item.get("short_term_view", ""),
                long_term_view=item.get("long_term_view", ""),
                risks=item.get("risks", []),
                action_label=item.get("action_label", "watch"),
                confidence=int(item.get("confidence", 50)),
            )

        # 對於沒被回覆到的 symbol，用保守 fallback
        for symbol, _ in items:
            usym = symbol.upper()
            if usym not in result:
                result[usym] = LLMAnalysis(
                    sentiment="中性",
                    short_term_view="LLM 未回傳此標的的結果",
                    long_term_view="",
                    risks=["missing in batch response"],
                    action_label="watch",
                    confidence=10,
                )

        return result

    except Exception as e:
        # 整批失敗：所有 symbol 都回 fallback
        return {
            symbol: LLMAnalysis(
                sentiment="中性",
                short_term_view=f"分析失敗: {e}",
                long_term_view="",
                risks=["LLM batch parsing failed"],
                action_label="watch",
                confidence=10,
            )
            for symbol, _ in items
        }

