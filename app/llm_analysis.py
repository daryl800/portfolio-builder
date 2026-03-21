# llm_analysis.py
import json
import os
import re
import time
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

# Initialize clients with None defaults
openai_client = None
metasota_client = None

# Initialize OpenAI client
if OPENAI_API_KEY:
    try:
        openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0, max_retries=2)
        print(f"[OpenAI] Client initialized successfully", flush=True)
    except Exception as e:
        print(f"[OpenAI] Failed to initialize client: {e}", flush=True)

# Initialize dashscope for QWEN
if QWEN_API_KEY:
    try:
        dashscope.api_key = QWEN_API_KEY
        print(f"[Qwen] Dashscope initialized", flush=True)
    except Exception as e:
        print(f"[Qwen] Failed to initialize: {e}", flush=True)

# Initialize MetaSota client with the working configuration
if METASOTA_API_KEY:
    try:
        # Use the working base URL from your test
        metasota_base_url = METASOTA_BASE_URL if METASOTA_BASE_URL else "https://metaso.cn/api/v1"
        print(f"[MetaSota] Initializing client with base URL: {metasota_base_url}", flush=True)
        metasota_client = OpenAI(
            api_key=METASOTA_API_KEY,
            base_url=metasota_base_url,
            timeout=30.0,
            max_retries=2
        )
        print(f"[MetaSota] Client initialized successfully", flush=True)
    except Exception as e:
        print(f"[MetaSota] Failed to initialize client: {e}", flush=True)
        metasota_client = None

LLM_CALL_COUNT = 0

def clean_metasota_response(content: str) -> str:
    """Remove [[number]] patterns from MetaSota response."""
    return re.sub(r'\[\[\d+\]\]', '', content)

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
            result_format='message'
        )
        
        return response

def get_client_and_model():
    """Get the appropriate client and model based on LLM_PROVIDER setting."""
    if LLM_PROVIDER == "qwen":
        if not QWEN_API_KEY:
            raise ValueError("QWEN_API_KEY not set but LLM_PROVIDER is 'qwen'")
        
        # Check if we should use dashscope SDK or OpenAI-compatible endpoint
        if QWEN_USE_DASHSCOPE_SDK:
            return QwenDashscopeWrapper(QWEN_API_KEY, QWEN_MODEL), QWEN_MODEL
        else:
            qwen_client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                timeout=30.0,
                max_retries=2
            )
            return qwen_client, QWEN_MODEL
    elif LLM_PROVIDER == "metasota":
        if not METASOTA_API_KEY:
            raise ValueError("METASOTA_API_KEY not set but LLM_PROVIDER is 'metasota'")
        
        global metasota_client
        if not metasota_client:
            # Re-initialize if not already done
            try:
                metasota_base_url = METASOTA_BASE_URL if METASOTA_BASE_URL else "https://metaso.cn/api/v1"
                metasota_client = OpenAI(
                    api_key=METASOTA_API_KEY,
                    base_url=metasota_base_url,
                    timeout=30.0,
                    max_retries=2
                )
            except Exception as e:
                raise Exception(f"Failed to initialize MetaSota client: {e}")
        
        # Get model from config, with default "fast" for MetaSota
        model = METASOTA_MODEL if METASOTA_MODEL else "fast"
        return metasota_client, model
    else:  # default to openai
        if not openai_client:
            raise ValueError("OPENAI_API_KEY not set but LLM_PROVIDER is 'openai'")
        return openai_client, OPENAI_MODEL

def call_llm(client, model, messages, temperature=0.2, max_tokens=1500):
    """Unified LLM call function that works with OpenAI, dashscope, and MetaSota."""
    
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
        # Using OpenAI client (works for OpenAI, MetaSota, and Qwen's OpenAI-compatible endpoint)
        try:
            print(f"[call_llm] Attempting to call {LLM_PROVIDER} with model {model}", flush=True)
            response = client.chat.completions.create(
                model=model,
                temperature=temperature,
                messages=messages,
                max_tokens=max_tokens,
                timeout=30.0
            )
            content = response.choices[0].message.content.strip()
            
            # Clean MetaSota responses if needed
            if LLM_PROVIDER == "metasota":
                content = clean_metasota_response(content)
            
            return content
        except Exception as e:
            error_msg = str(e)
            print(f"[call_llm] Error: {error_msg}", flush=True)
            
            if LLM_PROVIDER == "metasota":
                if "Connection error" in error_msg or "connection" in error_msg.lower():
                    raise Exception(f"MetaSota API connection error. Please check:\n"
                                  f"1. Your internet connection\n"
                                  f"2. The base URL is correct: {METASOTA_BASE_URL}\n"
                                  f"3. Your API key is valid\n"
                                  f"Original error: {error_msg}")
                else:
                    raise Exception(f"MetaSota API error: {error_msg}")
            raise

def analyze_stock_news(symbol: str, news_list: list[NewsItem]) -> LLMAnalysis:
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
    has_api_key = False
    if LLM_PROVIDER == "qwen":
        has_api_key = bool(QWEN_API_KEY)
    elif LLM_PROVIDER == "metasota":
        has_api_key = bool(METASOTA_API_KEY)
    else:
        has_api_key = bool(OPENAI_API_KEY)
    
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


def test_llm_connection():
    """
    Simple test function to verify LLM connection and basic functionality.
    Tests with simple questions to ensure the LLM is working properly.
    """
    print("\n" + "="*50)
    print("LLM CONNECTION TEST")
    print("="*50)
    
    # Check if API key is configured
    has_api_key = False
    provider = LLM_PROVIDER if LLM_PROVIDER else "openai"
    
    if provider == "qwen":
        has_api_key = bool(QWEN_API_KEY)
        print(f"Provider: Qwen (QWEN_API_KEY {'✓' if has_api_key else '✗'})")
    elif provider == "metasota":
        has_api_key = bool(METASOTA_API_KEY)
        print(f"Provider: MetaSota (METASOTA_API_KEY {'✓' if has_api_key else '✗'})")
        print(f"Base URL: {METASOTA_BASE_URL if METASOTA_BASE_URL else 'https://metaso.cn/api/v1'}")
    else:
        has_api_key = bool(OPENAI_API_KEY)
        print(f"Provider: OpenAI (OPENAI_API_KEY {'✓' if has_api_key else '✗'})")
    
    if not has_api_key:
        print(f"\n❌ ERROR: {provider.upper()}_API_KEY not configured!")
        print("Please set the appropriate API key in your environment variables.")
        return False
    
    try:
        # Get client and model
        client, model = get_client_and_model()
        print(f"Model: {model}")
        
        # Test questions
        test_questions = [
            "What date is today? Please answer in YYYY-MM-DD format.",
            "Who is the current president of the United States?",
            "What is 2+2? Answer with just the number."
        ]
        
        print("\n" + "-"*50)
        print("Running tests...")
        print("-"*50)
        
        all_passed = True
        
        for i, question in enumerate(test_questions, 1):
            print(f"\nTest {i}: {question}")
            print("-" * 40)
            
            try:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant. Provide concise and accurate answers."},
                    {"role": "user", "content": question},
                ]
                
                global LLM_CALL_COUNT
                LLM_CALL_COUNT += 1
                
                print(f"[LLM] test call #{LLM_CALL_COUNT}", flush=True)
                
                response = call_llm(client, model, messages, temperature=0.1, max_tokens=100)
                
                print(f"Response: {response}")
                
                # Simple validation
                if i == 1 and response:  # Date question
                    if any(char.isdigit() for char in response):
                        print("✓ Date test passed")
                    else:
                        print("⚠ Date test: Response received but format may not be optimal")
                        
                elif i == 2 and response:  # President question
                    if len(response.strip()) > 0:
                        print("✓ President test passed")
                    else:
                        print("⚠ President test: Empty response")
                        
                elif i == 3:  # Math question
                    if "4" in response:
                        print("✓ Math test passed")
                    else:
                        print("⚠ Math test: Expected '4' in response")
                
                print(f"✓ Test {i} completed successfully")
                
            except Exception as e:
                print(f"✗ Test {i} failed: {str(e)}")
                all_passed = False
        
        # Summary
        print("\n" + "="*50)
        print("TEST SUMMARY")
        print("="*50)
        
        if all_passed:
            print("✓ All tests passed!")
            print(f"✓ LLM provider '{provider}' is working correctly")
            return True
        else:
            print("⚠ Some tests had issues")
            print("⚠ LLM is responding but some answers may not be accurate")
            return False
            
    except Exception as e:
        print(f"\n❌ FATAL ERROR: Failed to initialize LLM client: {str(e)}")
        print(f"Please check your {provider.upper()}_API_KEY and configuration.")
        return False


def quick_test():
    """
    A super simple test that just checks if the LLM can respond to a basic question.
    Useful for quick verification.
    """
    print("\n" + "="*50)
    print("QUICK LLM TEST")
    print("="*50)
    
    provider = LLM_PROVIDER if LLM_PROVIDER else "openai"
    
    # Check API key
    if provider == "qwen" and not QWEN_API_KEY:
        print("❌ QWEN_API_KEY not set")
        return False
    elif provider == "metasota" and not METASOTA_API_KEY:
        print("❌ METASOTA_API_KEY not set")
        return False
    elif provider == "openai" and not OPENAI_API_KEY:
        print("❌ OPENAI_API_KEY not set")
        return False
    
    try:
        client, model = get_client_and_model()
        print(f"Provider: {provider}")
        print(f"Model: {model}")
        if provider == "metasota":
            print(f"Base URL: {METASOTA_BASE_URL if METASOTA_BASE_URL else 'https://metaso.cn/api/v1'}")
        
        messages = [
            {"role": "user", "content": "What is 2+2? Answer with just the number."}
        ]
        
        print("Sending test request...")
        response = call_llm(client, model, messages, temperature=0.1, max_tokens=10)
        print(f"Response: {response}")
        
        if "4" in response:
            print("✓ Quick test passed!")
            return True
        else:
            print("⚠ Quick test: Unexpected response")
            return False
            
    except Exception as e:
        print(f"❌ Quick test failed: {str(e)}")
        return False


# Allow running tests from command line
if __name__ == "__main__":
    import sys
    
    print(f"LLM Provider: {LLM_PROVIDER if LLM_PROVIDER else 'openai'}")
    print(f"Python version: {sys.version}")
    
    print("\nChoose test option:")
    print("1. Full test (3 questions)")
    print("2. Quick test (1 question)")
    print("3. Run both tests")
    
    choice = input("\nEnter choice (1/2/3): ").strip()
    
    if choice == "1":
        test_llm_connection()
    elif choice == "2":
        quick_test()
    elif choice == "3":
        quick_test()
        print("\n" + "-"*50)
        test_llm_connection()
    else:
        print("Invalid choice. Running quick test by default...")
        quick_test()