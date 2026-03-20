# llm_analysis.py
import json
import time
from typing import Iterable, Dict, List, Optional, Union
import dashscope
from openai import OpenAI
from app.config import (
    OPENAI_API_KEY, 
    OPENAI_MODEL,
    QWEN_API_KEY,
    QWEN_MODEL,
    LLM_PROVIDER,  # "openai" or "qwen"
    QWEN_USE_DASHSCOPE_SDK  # Set to True to use dashscope SDK, False to use OpenAI-compatible endpoint
)
from app.models import LLMAnalysis, NewsItem

# Initialize OpenAI client (always, in case we need it)
openai_client = None
if OPENAI_API_KEY:
    openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Initialize dashscope for QWEN
if QWEN_API_KEY:
    dashscope.api_key = QWEN_API_KEY

LLM_CALL_COUNT = 0

class QwenDashscopeWrapper:
    """Wrapper for dashscope SDK to match OpenAI's interface pattern."""
    
    def __init__(self, api_key: str, model: str):
        dashscope.api_key = api_key
        self.model = model
    
    def chat_completions_create(self, **kwargs):
        """Convert OpenAI-style call to dashscope call."""
        messages = kwargs.get("messages", [])
        temperature = kwargs.get("temperature", 0.2)
        max_tokens = kwargs.get("max_tokens", 1500)
        
        # Extract system and user messages
        system_content = ""
        user_content = ""
        
        for msg in messages:
            if msg["role"] == "system":
                system_content = msg["content"]
            elif msg["role"] == "user":
                user_content = msg["content"]
        
        # Combine prompts
        full_prompt = system_content + "\n\n" + user_content if system_content else user_content
        
        # Call dashscope
        response = dashscope.Generation.call(
            model=self.model,
            prompt=full_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            result_format='message'  # Get response in message format
        )
        
        return response

def get_client_and_model():
    """Get the appropriate client and model based on LLM_PROVIDER setting."""
    if LLM_PROVIDER == "qwen":
        if not QWEN_API_KEY:
            raise ValueError("QWEN_API_KEY not set but LLM_PROVIDER is 'qwen'")
        
        # Check if we should use dashscope SDK or OpenAI-compatible endpoint
        if QWEN_USE_DASHSCOPE_SDK:
            # Return a wrapper that mimics OpenAI's interface
            return QwenDashscopeWrapper(QWEN_API_KEY, QWEN_MODEL), QWEN_MODEL
        else:
            # Use OpenAI client with QWEN's OpenAI-compatible endpoint
            qwen_client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            return qwen_client, QWEN_MODEL
    else:  # default to openai
        if not openai_client:
            raise ValueError("OPENAI_API_KEY not set but LLM_PROVIDER is 'openai'")
        return openai_client, OPENAI_MODEL

def call_llm(client, model, messages, temperature=0.2, max_tokens=1500):
    """Unified LLM call function that works with both OpenAI and dashscope."""
    
    if isinstance(client, QwenDashscopeWrapper):
        # Using dashscope SDK
        response = client.chat_completions_create(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract content from dashscope response
        if hasattr(response, 'output') and hasattr(response.output, 'choices'):
            return response.output.choices[0].message.content
        elif hasattr(response, 'output') and hasattr(response.output, 'text'):
            return response.output.text
        else:
            return str(response)
    else:
        # Using OpenAI client
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            max_tokens=max_tokens
        )
        return response.choices[0].message.content.strip()

def analyze_stock_news(symbol: str, news_list: list[NewsItem]) -> LLMAnalysis:
    # Check if any API key is available
    has_api_key = (LLM_PROVIDER == "qwen" and QWEN_API_KEY) or (LLM_PROVIDER != "qwen" and OPENAI_API_KEY)
    
    if not has_api_key:
        provider = LLM_PROVIDER if LLM_PROVIDER else "openai"
        return LLMAnalysis(
            sentiment="中性",
            short_term_view=f"未設定 {provider.upper()}_API_KEY，略過分析",
            long_term_view="未設定 API key，略過分析",
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
        client, model = get_client_and_model()
        
        print(
            f"[LLM] call #{LLM_CALL_COUNT} - single - provider={LLM_PROVIDER} - model={model} - symbol={symbol}",
            flush=True,
        )
        
        messages = [
            {"role": "system", "content": "You are a careful financial research assistant. Reply in Traditional Chinese and valid JSON only."},
            {"role": "user", "content": prompt},
        ]
        
        content = call_llm(client, model, messages, temperature=0.2)
        
        # Handle potential markdown code blocks in response
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()
            
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

    # Check if any API key is available
    has_api_key = (LLM_PROVIDER == "qwen" and QWEN_API_KEY) or (LLM_PROVIDER != "qwen" and OPENAI_API_KEY)
    
    if not has_api_key:
        provider = LLM_PROVIDER if LLM_PROVIDER else "openai"
        return {
            symbol: LLMAnalysis(
                sentiment="中性",
                short_term_view=f"未設定 {provider.upper()}_API_KEY，略過分析",
                long_term_view="未設定 API key，略過分析",
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
        client, model = get_client_and_model()
        
        print(
            f"[LLM] call #{LLM_CALL_COUNT} - batch - provider={LLM_PROVIDER} - model={model} - symbols={[s for s, _ in items]}",
            flush=True,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a careful financial research assistant. "
                    "Reply in Traditional Chinese and valid JSON only."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        
        content = call_llm(client, model, messages, temperature=0.2)
        
        # Handle potential markdown code blocks in response
        if content.startswith("```json"):
            content = content.replace("```json", "").replace("```", "").strip()
        elif content.startswith("```"):
            content = content.replace("```", "").strip()
            
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