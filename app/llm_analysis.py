# llm_analysis.py - With MetaSota Support and Provider Logging
import json
import re
from typing import Iterable, Dict, List, Optional, Union
import dashscope
from openai import OpenAI
from app.config import (
    OPENAI_API_KEY, 
    OPENAI_MODEL,
    QWEN_API_KEY,
    QWEN_MODEL,
    LLM_PROVIDER,  # "openai" or "qwen" or "metasota"
    QWEN_USE_DASHSCOPE_SDK,  # Set to True to use dashscope SDK, False to use OpenAI-compatible endpoint
    METASOTA_API_KEY,
    METASOTA_MODEL,
    METASOTA_BASE_URL,
)
from app.models import LLMAnalysis, NewsItem

# Initialize clients (without timeout/max_retries in constructor)
openai_client = None
metasota_client = None

# Initialize OpenAI client
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY)
        print(f"[OpenAI] Client initialized", flush=True)
    except Exception as e:
        print(f"[OpenAI] Failed to initialize: {e}", flush=True)

# Initialize dashscope for QWEN
if QWEN_API_KEY:
    try:
        dashscope.api_key = QWEN_API_KEY
        print(f"[Qwen] Dashscope initialized", flush=True)
    except Exception as e:
        print(f"[Qwen] Failed to initialize: {e}", flush=True)

# Initialize MetaSota client
if METASOTA_API_KEY:
    try:
        metasota_base_url = METASOTA_BASE_URL if METASOTA_BASE_URL else "https://metaso.cn/api/v1"
        metasota_client = OpenAI(
            api_key=METASOTA_API_KEY,
            base_url=metasota_base_url
        )
        print(f"[MetaSota] Client initialized with base URL: {metasota_base_url}", flush=True)
    except Exception as e:
        print(f"[MetaSota] Failed to initialize: {e}", flush=True)
        metasota_client = None

LLM_CALL_COUNT = 0

class QwenDashscopeWrapper:
    """Wrapper for dashscope SDK to match OpenAI's interface pattern."""
    
    def __init__(self, api_key: str, model: str):
        dashscope.api_key = api_key
        self.model = model
        print(f"[Qwen] Dashscope wrapper initialized with model: {model}", flush=True)
    
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
            result_format='message'
        )
        
        return response

def get_client_and_model():
    print(f"📦 LLM_PROVIDER: {LLM_PROVIDER}")
    """Get the appropriate client and model based on LLM_PROVIDER setting."""
    if LLM_PROVIDER == "qwen":
        if not QWEN_API_KEY:
            raise ValueError("QWEN_API_KEY not set but LLM_PROVIDER is 'qwen'")
        
        if QWEN_USE_DASHSCOPE_SDK:
            print(f"[LLM Provider] Using Qwen with Dashscope SDK (model: {QWEN_MODEL})", flush=True)
            return QwenDashscopeWrapper(QWEN_API_KEY, QWEN_MODEL), QWEN_MODEL
        else:
            print(f"[LLM Provider] Using Qwen with OpenAI-compatible endpoint (model: {QWEN_MODEL})", flush=True)
            # Use OpenAI client with QWEN's OpenAI-compatible endpoint
            qwen_client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            return qwen_client, QWEN_MODEL
    
    elif LLM_PROVIDER == "metasota":
        if not METASOTA_API_KEY:
            raise ValueError("METASOTA_API_KEY not set but LLM_PROVIDER is 'metasota'")
        
        if not metasota_client:
            raise Exception("MetaSota client not initialized")
        
        model = METASOTA_MODEL if METASOTA_MODEL else "fast"
        print(f"[LLM Provider] Using MetaSota (model: {model}, base_url: {METASOTA_BASE_URL})", flush=True)
        return metasota_client, model
    
    else:  # default to openai
        if not openai_client:
            raise ValueError("OPENAI_API_KEY not set but LLM_PROVIDER is 'openai'")
        print(f"[LLM Provider] Using OpenAI (model: {OPENAI_MODEL})", flush=True)
        return openai_client, OPENAI_MODEL

def clean_metasota_response(content: str) -> str:
    """Clean MetaSota response by removing [[number]] patterns."""
    # Remove [[number]] patterns
    cleaned = re.sub(r'\[\[\d+\]\]', '', content)
    # Remove extra whitespace
    cleaned = ' '.join(cleaned.split())
    return cleaned

def call_llm(client, model, messages, temperature=0.2, max_tokens=1500):
    """Unified LLM call function that works with OpenAI, dashscope, and MetaSota."""
    
    print(f"📦 LLM_PROVIDER: {LLM_PROVIDER}")

    if isinstance(client, QwenDashscopeWrapper):
        # Using dashscope SDK
        print(f"[LLM Call] Using Qwen Dashscope SDK with model: {model}", flush=True)
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
        # Using OpenAI client (works for OpenAI and MetaSota)
        provider_type = "MetaSota" if LLM_PROVIDER == "metasota" else "OpenAI" if LLM_PROVIDER == "openai" else "Qwen (OpenAI-compatible)"
        print(f"[LLM Call] Using {provider_type} with model: {model}", flush=True)
        
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=messages,
            max_tokens=max_tokens
        )
        content = response.choices[0].message.content.strip()
        
        # Clean MetaSota responses
        if LLM_PROVIDER == "metasota":
            content = clean_metasota_response(content)
        
        return content

def analyze_stock_news(symbol: str, news_list: list[NewsItem]) -> LLMAnalysis:
    # Check if any API key is available
    has_api_key = False

    print(f"📦 LLM_PROVIDER: {LLM_PROVIDER}")

    if LLM_PROVIDER == "qwen":
        has_api_key = bool(QWEN_API_KEY)
    elif LLM_PROVIDER == "metasota":
        has_api_key = bool(METASOTA_API_KEY)
    else:
        has_api_key = bool(OPENAI_API_KEY)
    
    if not has_api_key:
        provider = LLM_PROVIDER if LLM_PROVIDER else "openai"
        print(f"[LLM] No API key found for provider: {provider}", flush=True)
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
你是一位謹慎的股票研究助理。請盡可能搜尋網上最新的資訊或最新新聞對 {symbol} 的影響，包含正面和負面。
請只輸出 JSON，不要輸出 markdown，不要加註解。

JSON schema:
{{
  "sentiment": "積極|中性|消極",
  "short_term_view": "幾句重點",
  "long_term_view": "幾句重點",
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
        
        print(f"[LLM] Successfully analyzed {symbol} with {LLM_PROVIDER}", flush=True)
        
        return LLMAnalysis(
            sentiment=data.get("sentiment", "中性"),
            short_term_view=data.get("short_term_view", ""),
            long_term_view=data.get("long_term_view", ""),
            risks=data.get("risks", []),
            action_label=data.get("action_label", "watch"),
            confidence=int(data.get("confidence", 50)),
        )
    except Exception as e:
        print(f"[LLM] Error analyzing {symbol} with {LLM_PROVIDER}: {e}", flush=True)
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
    has_api_key = False
    if LLM_PROVIDER == "qwen":
        has_api_key = bool(QWEN_API_KEY)
    elif LLM_PROVIDER == "metasota":
        has_api_key = bool(METASOTA_API_KEY)
    else:
        has_api_key = bool(OPENAI_API_KEY)
    
    if not has_api_key:
        provider = LLM_PROVIDER if LLM_PROVIDER else "openai"
        print(f"[LLM] No API key found for provider: {provider}", flush=True)
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
    "short_term_view": "幾句重點",
    "long_term_view": "幾句重點",
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

        print(f"[LLM] Batch analysis completed with {LLM_PROVIDER}, processed {len(result)} symbols", flush=True)
        return result

    except Exception as e:
        print(f"[LLM] Batch analysis failed with {LLM_PROVIDER}: {e}", flush=True)
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


# Optional: Test function for MetaSota
def test_metasota():
    """Test MetaSota connection"""
    if LLM_PROVIDER != "metasota":
        print(f"Current provider is {LLM_PROVIDER}, not MetaSota")
        return False
    
    if not METASOTA_API_KEY:
        print("METASOTA_API_KEY not set")
        return False
    
    try:
        client, model = get_client_and_model()
        print(f"Testing MetaSota with model: {model}")
        
        messages = [
            {"role": "user", "content": "What is 2+2? Answer with just the number."}
        ]
        
        response = call_llm(client, model, messages, temperature=0.1, max_tokens=10)
        print(f"Response: {response}")
        
        if "4" in response:
            print("✅ MetaSota test passed!")
            return True
        else:
            print("⚠️ MetaSota test: Unexpected response")
            return False
            
    except Exception as e:
        print(f"❌ MetaSota test failed: {e}")
        return False


# Allow running tests from the command line
if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print(f"LLM Configuration:")

    print(f"Current LLM_PROVIDER: {LLM_PROVIDER}")
    if LLM_PROVIDER == "metasota":
        if METASOTA_API_KEY:
            print(f"MetaSota API Key found: {METASOTA_API_KEY[:8]}...")
            print(f"MetaSota Model: {METASOTA_MODEL if 'METASOTA_MODEL' in dir() else 'not set'}")
        else:
            print("⚠️ WARNING: METASOTA_API_KEY is not set in environment!")
    elif LLM_PROVIDER == "qwen":
        print(f"Qwen API Key found: {bool(QWEN_API_KEY)}")
    elif LLM_PROVIDER == "openai":
        print(f"OpenAI API Key found: {bool(OPENAI_API_KEY)}")
    print("=" * 60)
    print(f"Python version: {sys.version}")
    
    if LLM_PROVIDER == "metasota":
        print("\nTesting MetaSota...")
        test_metasota()
    else:
        print(f"\nCurrently using {LLM_PROVIDER.upper()}. To test MetaSota, set LLM_PROVIDER=metasota in your .env file")