---
translated: true
source: tool_use/tool_search_with_embeddings.ipynb
---

# 用 embedding 做 tool search

> 原文：[tool_use/tool_search_with_embeddings.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/tool_search_with_embeddings.ipynb)

用語意 embedding 動態探索 tool，讓 Claude 應用擴展到上千個 tool。

## 這篇在做什麼

tool 一多，把所有定義一次塞進 prompt 會吃掉 context、拖慢速度又增加成本。這篇做一個 client 端的 `tool_search`：先把每個 tool 的描述轉成 embedding，Claude 需要某種能力時用自然語言搜尋，拿回最相關的 tool 定義再直接使用。

## 學完你會

- 實作 client 端的 tool search，把 Claude 應用從幾十個 tool 擴展到上千個
- 用 embedding 加 cosine similarity，依任務內容動態找出相關的 tool
- 寫出 `tool_search` 這個 meta-tool 和對話迴圈，讓 Claude 搜到 tool 後立刻使用

## 開跑前

- Anthropic API key，放進 `.env`
- Python 3.11 以上，要安裝 sentence-transformers（embedding 在本機跑，不用額外 API）

在 Claude 應用裡放幾十個專用 tool 很快就會碰壁：一次提供所有 tool 定義會吃掉 context window、增加延遲和成本，也讓 Claude 更難找到對的 tool。超過大約 100 個 tool，這種做法就不實際了。

語意 tool search 把 tool 當成可被探索的資源來解決這個問題。你不用預先塞進幾百個定義，而是只給 Claude 一個 `tool_search` tool，需要時回傳相關的能力，在能擴展到上千個 tool 的同時，把 context 用量降低 90% 以上。

**這本 cookbook 結束時，你會學會：**
- 實作 client 端的 tool search，把 Claude 應用從幾十個 tool 擴展到上千個
- 用語意 embedding，根據任務 context 動態找出相關的 tool
- 把這個模式套用到特定領域的 tool 庫（API、資料庫、內部系統）

這個模式已在 production 中被管理大型 tool 生態的團隊使用，這些團隊很在意 context 效率。我們為了清楚而用一小組 tool 示範，但同樣的做法可以無縫擴展到幾百或幾千個 tool 的函式庫。

## 事前準備

開始之前，請確認你具備：

**需要的知識**
- Python 基礎：熟悉函式、dictionary 和基本資料結構
- 對 Claude tool use 有基本了解：建議先讀 [Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)

**需要的工具**
- Python 3.11 以上
- Anthropic API key（[在這裡申請](https://docs.anthropic.com/claude/reference/getting-started-with-the-api)）

## 設定

首先，安裝需要的套件：

```python
# Note: we use -q to avoid printing too much to stdout
# Use --only-binary to avoid build issues with pythran
%pip install --only-binary :all: -q anthropic sentence-transformers numpy python-dotenv
```

??? note "輸出"

    ```text
    huggingface/tokenizers: The current process just got forked, after parallelism has already been used. Disabling parallelism to avoid deadlocks...
    To disable this warning, you can either:
    	- Avoid using `tokenizers` before the fork if possible
    	- Explicitly set the environment variable TOKENIZERS_PARALLELISM=(true | false)
    ```

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

確認你的 `.env` 檔包含：
```
ANTHROPIC_API_KEY=your_key_here
```

載入環境變數並設定 client：

```python
import json
import random
from datetime import datetime, timedelta
from typing import Any

import anthropic
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# Load environment variables from .env file
load_dotenv()

# Define model constant for easy updates
MODEL = "claude-sonnet-5-5"

# Initialize Claude client (API key loaded from environment)
claude_client = anthropic.Anthropic()

# Load the SentenceTransformer model
# all-MiniLM-L6-v2 is a lightweight model with 384 dimensional embeddings
# It will be downloaded from HuggingFace on first use
print("Loading SentenceTransformer model...")
embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

print("✓ Clients initialized successfully")
```

??? note "輸出"

    ```text
    Loading SentenceTransformer model...
    ✓ Clients initialized successfully
    ```

## 定義 Tool 庫

在實作語意搜尋之前，我們需要有 tool 可以搜。我們會建一個包含 8 個 tool 的函式庫，分成兩類：Weather 和 Finance。

在 production 應用裡，你可能管理橫跨內部 API、資料庫操作或第三方整合的幾百或幾千個 tool。語意搜尋的做法不用修改就能擴展到這麼大的函式庫，這裡用小組 tool 純粹是為了示範清楚。

```python
# Define our tool library with 2 domains
TOOL_LIBRARY = [
    # Weather Tools
    {
        "name": "get_weather",
        "description": "Get the current weather in a given location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "The unit of temperature",
                },
            },
            "required": ["location"],
        },
    },
    {
        "name": "get_forecast",
        "description": "Get the weather forecast for multiple days ahead",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state",
                },
                "days": {
                    "type": "number",
                    "description": "Number of days to forecast (1-10)",
                },
            },
            "required": ["location", "days"],
        },
    },
    {
        "name": "get_timezone",
        "description": "Get the current timezone and time for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or timezone identifier",
                }
            },
            "required": ["location"],
        },
    },
    {
        "name": "get_air_quality",
        "description": "Get current air quality index and pollutant levels for a location",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name or coordinates",
                }
            },
            "required": ["location"],
        },
    },
    # Finance Tools
    {
        "name": "get_stock_price",
        "description": "Get the current stock price and market data for a given ticker symbol",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., AAPL, GOOGL)",
                },
                "include_history": {
                    "type": "boolean",
                    "description": "Include historical data",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "convert_currency",
        "description": "Convert an amount from one currency to another using current exchange rates",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Amount to convert",
                },
                "from_currency": {
                    "type": "string",
                    "description": "Source currency code (e.g., USD)",
                },
                "to_currency": {
                    "type": "string",
                    "description": "Target currency code (e.g., EUR)",
                },
            },
            "required": ["amount", "from_currency", "to_currency"],
        },
    },
    {
        "name": "calculate_compound_interest",
        "description": "Calculate compound interest for investments over time",
        "input_schema": {
            "type": "object",
            "properties": {
                "principal": {
                    "type": "number",
                    "description": "Initial investment amount",
                },
                "rate": {
                    "type": "number",
                    "description": "Annual interest rate (as percentage)",
                },
                "years": {"type": "number", "description": "Number of years"},
                "frequency": {
                    "type": "string",
                    "enum": ["daily", "monthly", "quarterly", "annually"],
                    "description": "Compounding frequency",
                },
            },
            "required": ["principal", "rate", "years"],
        },
    },
    {
        "name": "get_market_news",
        "description": "Get recent financial news and market updates for a specific company or sector",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Company name, ticker symbol, or sector",
                },
                "limit": {
                    "type": "number",
                    "description": "Maximum number of news articles to return",
                },
            },
            "required": ["query"],
        },
    },
]

print(f"✓ Defined {len(TOOL_LIBRARY)} tools in the library")
```

??? note "輸出"

    ```text
    ✓ Defined 8 tools in the library
    ```

## 建立 Tool Embedding

語意搜尋的原理是比較文字的*意義*，而不只是搜尋關鍵字。要做到這點，我們需要把每個 tool 定義轉成能捕捉其語意的 **embedding 向量**。

由於我們的 tool 定義是帶有名稱、描述和參數的結構化 JSON 物件，我們先把每個 tool 轉成人類可讀的文字表示，再用 SentenceTransformer 的 `all-MiniLM-L6-v2` 模型產生 embedding 向量。

我們選這個模型是因為它：
- **輕量又快**（只有 384 維，大型模型是 768 維以上）
- **在本機執行**，不需要 API 呼叫
- **對 tool search 夠用**（你可以試更大的模型，看準確度會不會更好）

先來建一個把 tool 定義轉成可搜尋文字的函式：

```python
def tool_to_text(tool: dict[str, Any]) -> str:
    """
    Convert a tool definition into a text representation for embedding.
    Combines the tool name, description, and parameter information.
    """
    text_parts = [
        f"Tool: {tool['name']}",
        f"Description: {tool['description']}",
    ]

    # Add parameter information
    if "input_schema" in tool and "properties" in tool["input_schema"]:
        params = tool["input_schema"]["properties"]
        param_descriptions = []
        for param_name, param_info in params.items():
            param_desc = param_info.get("description", "")
            param_type = param_info.get("type", "")
            param_descriptions.append(f"{param_name} ({param_type}): {param_desc}")

        if param_descriptions:
            text_parts.append("Parameters: " + ", ".join(param_descriptions))

    return "\n".join(text_parts)


# Test with one tool
sample_text = tool_to_text(TOOL_LIBRARY[0])
print("Sample tool text representation:")
print(sample_text)
```

??? note "輸出"

    ```text
    Sample tool text representation:
    Tool: get_weather
    Description: Get the current weather in a given location
    Parameters: location (string): The city and state, e.g. San Francisco, CA, unit (string): The unit of temperature
    ```

現在幫所有 tool 建立 embedding：

```python
# Create embeddings for all tools
print("Creating embeddings for all tools...")

tool_texts = [tool_to_text(tool) for tool in TOOL_LIBRARY]

# Embed all tools at once using SentenceTransformer
# The model returns normalized embeddings by default
tool_embeddings = embedding_model.encode(tool_texts, convert_to_numpy=True)

print(f"✓ Created embeddings with shape: {tool_embeddings.shape}")
print(f"  - {tool_embeddings.shape[0]} tools")
print(f"  - {tool_embeddings.shape[1]} dimensions per embedding")
```

??? note "輸出"

    ```text
    Creating embeddings for all tools...
    ✓ Created embeddings with shape: (8, 384)
      - 8 tools
      - 384 dimensions per embedding
    ```

## 實作 Tool Search

Tool 都嵌入成向量之後，就能實作語意搜尋。如果兩段文字意義相近，它們的 embedding 向量在向量空間裡就會靠得很近。我們用 **cosine similarity** 來衡量這種「接近程度」。

搜尋流程：
1. **嵌入查詢**：把 Claude 的自然語言搜尋請求，轉到跟 tool 相同的向量空間
2. **計算相似度**：算出查詢向量跟每個 tool 向量之間的 cosine similarity
3. **排序並回傳**：依相似度分數排序 tool，回傳前 N 個符合的

有了語意搜尋，Claude 可以用「I need to check the weather」或「calculate investment returns」這種自然語言搜尋，不需要精確的 tool 名稱。

來實作搜尋函式，並用一個範例查詢測試：

```python
def search_tools(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    Search for tools using semantic similarity.

    Args:
        query: Natural language description of what tool is needed
        top_k: Number of top tools to return

    Returns:
        List of tool definitions most relevant to the query
    """
    # Embed the query using SentenceTransformer
    query_embedding = embedding_model.encode(query, convert_to_numpy=True)

    # Calculate cosine similarity using dot product
    # SentenceTransformer returns normalized embeddings, so dot product = cosine similarity
    similarities = np.dot(tool_embeddings, query_embedding)

    # Get top k indices
    top_indices = np.argsort(similarities)[-top_k:][::-1]

    # Return the corresponding tools with their scores
    results = []
    for idx in top_indices:
        results.append({"tool": TOOL_LIBRARY[idx], "similarity_score": float(similarities[idx])})

    return results


# Test the search function
test_query = "I need to check the weather"
test_results = search_tools(test_query, top_k=3)

print(f"Search query: '{test_query}'\n")
print("Top 3 matching tools:")
for i, result in enumerate(test_results, 1):
    tool_name = result["tool"]["name"]
    score = result["similarity_score"]
    print(f"{i}. {tool_name} (similarity: {score:.3f})")
```

??? note "輸出"

    ```text
    Search query: 'I need to check the weather'

    Top 3 matching tools:
    1. get_weather (similarity: 0.560)
    2. get_forecast (similarity: 0.508)
    3. get_air_quality (similarity: 0.401)
    ```

## 定義 tool_search Tool

現在我們來實作 **meta-tool**，讓 Claude 能按需探索其他 tool。當 Claude 需要它沒有的能力時，就用這個 `tool_search` tool 搜尋，在結果中收到 tool 定義，然後可以立刻使用這些新發現的 tool。

這是我們一開始提供給 Claude 的唯一 tool：

```python
# The tool_search tool definition
TOOL_SEARCH_DEFINITION = {
    "name": "tool_search",
    "description": "Search for available tools that can help with a task. Returns tool definitions for matching tools. Use this when you need a tool but don't have it available yet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural language description of what kind of tool you need (e.g., 'weather information', 'currency conversion', 'stock prices')",
            },
            "top_k": {
                "type": "number",
                "description": "Number of tools to return (default: 5)",
            },
        },
        "required": ["query"],
    },
}

print("✓ Tool search definition created")
```

??? note "輸出"

    ```text
    ✓ Tool search definition created
    ```

接著實作 handler，處理 Claude 的 `tool_search` 呼叫並回傳找到的 tool：

```python
def handle_tool_search(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    Handle a tool_search invocation and return tool references.

    Returns a list of tool_reference content blocks for discovered tools.
    """
    # Search for relevant tools
    results = search_tools(query, top_k=top_k)

    # Create tool_reference objects instead of full definitions
    tool_references = [
        {"type": "tool_reference", "tool_name": result["tool"]["name"]} for result in results
    ]

    print(f"\n🔍 Tool search: '{query}'")
    print(f"   Found {len(tool_references)} tools:")
    for i, result in enumerate(results, 1):
        print(f"   {i}. {result['tool']['name']} (similarity: {result['similarity_score']:.3f})")

    return tool_references


# Test the handler
test_result = handle_tool_search("stock market data", top_k=3)
print(f"\nReturned {len(test_result)} tool references:")
for ref in test_result:
    print(f"  {ref}")
```

??? note "輸出"

    ```text

    🔍 Tool search: 'stock market data'
       Found 3 tools:
       1. get_stock_price (similarity: 0.524)
       2. get_market_news (similarity: 0.469)
       3. calculate_compound_interest (similarity: 0.244)

    Returned 3 tool references:
      {'type': 'tool_reference', 'tool_name': 'get_stock_price'}
      {'type': 'tool_reference', 'tool_name': 'get_market_news'}
      {'type': 'tool_reference', 'tool_name': 'calculate_compound_interest'}
    ```

## 模擬 Tool 執行

這個示範中，我們會建立 tool 執行的模擬回應。在真實應用裡，這些會去呼叫實際的 API 或服務：

```python
def mock_tool_execution(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Generate realistic mock responses for tool executions.

    Args:
        tool_name: Name of the tool being executed
        tool_input: Input parameters for the tool

    Returns:
        Mock response string appropriate for the tool
    """
    # Weather tools
    if tool_name == "get_weather":
        location = tool_input.get("location", "Unknown")
        unit = tool_input.get("unit", "fahrenheit")
        temp = random.randint(15, 30) if unit == "celsius" else random.randint(60, 85)
        conditions = random.choice(["sunny", "partly cloudy", "cloudy", "rainy"])
        return json.dumps(
            {
                "location": location,
                "temperature": temp,
                "unit": unit,
                "conditions": conditions,
                "humidity": random.randint(40, 80),
                "wind_speed": random.randint(5, 20),
            }
        )

    elif tool_name == "get_forecast":
        location = tool_input.get("location", "Unknown")
        days = int(tool_input.get("days", 5))
        forecast = []
        for i in range(days):
            date = (datetime.now() + timedelta(days=i)).strftime("%Y-%m-%d")
            forecast.append(
                {
                    "date": date,
                    "high": random.randint(20, 30),
                    "low": random.randint(10, 20),
                    "conditions": random.choice(["sunny", "cloudy", "rainy", "partly cloudy"]),
                }
            )
        return json.dumps({"location": location, "forecast": forecast})

    elif tool_name == "get_timezone":
        location = tool_input.get("location", "Unknown")
        return json.dumps(
            {
                "location": location,
                "timezone": "UTC+9",
                "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "utc_offset": "+09:00",
            }
        )

    elif tool_name == "get_air_quality":
        location = tool_input.get("location", "Unknown")
        aqi = random.randint(20, 150)
        categories = {
            (0, 50): "Good",
            (51, 100): "Moderate",
            (101, 150): "Unhealthy for Sensitive Groups",
        }
        category = next(cat for (low, high), cat in categories.items() if low <= aqi <= high)
        return json.dumps(
            {
                "location": location,
                "aqi": aqi,
                "category": category,
                "pollutants": {
                    "pm25": random.randint(5, 50),
                    "pm10": random.randint(10, 100),
                    "o3": random.randint(20, 80),
                },
            }
        )

    # Finance tools
    elif tool_name == "get_stock_price":
        ticker = tool_input.get("ticker", "UNKNOWN")
        return json.dumps(
            {
                "ticker": ticker,
                "price": round(random.uniform(100, 500), 2),
                "change": round(random.uniform(-5, 5), 2),
                "change_percent": round(random.uniform(-2, 2), 2),
                "volume": random.randint(1000000, 10000000),
                "market_cap": f"${random.randint(100, 1000)}B",
            }
        )

    elif tool_name == "convert_currency":
        amount = tool_input.get("amount", 0)
        from_currency = tool_input.get("from_currency", "USD")
        to_currency = tool_input.get("to_currency", "EUR")
        # Mock exchange rate
        rate = random.uniform(0.8, 1.2)
        converted = round(amount * rate, 2)
        return json.dumps(
            {
                "original_amount": amount,
                "from_currency": from_currency,
                "to_currency": to_currency,
                "exchange_rate": round(rate, 4),
                "converted_amount": converted,
            }
        )

    elif tool_name == "calculate_compound_interest":
        principal = tool_input.get("principal", 0)
        rate = tool_input.get("rate", 0)
        years = tool_input.get("years", 0)
        frequency = tool_input.get("frequency", "monthly")

        # Calculate compound interest
        n_map = {"daily": 365, "monthly": 12, "quarterly": 4, "annually": 1}
        n = n_map.get(frequency, 12)
        final_amount = principal * (1 + rate / 100 / n) ** (n * years)
        interest_earned = final_amount - principal

        return json.dumps(
            {
                "principal": principal,
                "rate": rate,
                "years": years,
                "compounding_frequency": frequency,
                "final_amount": round(final_amount, 2),
                "interest_earned": round(interest_earned, 2),
            }
        )

    elif tool_name == "get_market_news":
        query = tool_input.get("query", "")
        limit = tool_input.get("limit", 5)
        news = []
        for i in range(min(limit, 5)):
            news.append(
                {
                    "title": f"{query} - News Article {i + 1}",
                    "source": random.choice(
                        [
                            "Bloomberg",
                            "Reuters",
                            "Financial Times",
                            "Wall Street Journal",
                        ]
                    ),
                    "published": (datetime.now() - timedelta(hours=random.randint(1, 24))).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "summary": f"Latest developments regarding {query}...",
                }
            )
        return json.dumps({"query": query, "articles": news, "count": len(news)})

    # Default fallback
    else:
        return json.dumps(
            {
                "status": "executed",
                "tool": tool_name,
                "message": f"Tool {tool_name} executed successfully with input: {json.dumps(tool_input)}",
            }
        )


print("✓ Mock tool execution function created")
```

??? note "輸出"

    ```text
    ✓ Mock tool execution function created
    ```

## 實作對話迴圈

現在把所有東西串起來！我們會建一個處理完整 tool search 流程的對話迴圈。

**對話流程：**
1. Claude 一開始只有 `tool_search` 這個 tool 可用
2. 當 Claude 呼叫 `tool_search`，我們執行語意搜尋並回傳符合的 tool 定義
3. Claude 接著可以立刻使用找到的 tool
4. 當 Claude 呼叫找到的 tool，我們執行它（這個示範用模擬回應）
5. 迴圈持續到 Claude 給出最終答案

```python
def run_tool_search_conversation(user_message: str, max_turns: int = 5) -> None:
    """
    Run a conversation with Claude using the tool search pattern.

    Args:
        user_message: The initial user message
        max_turns: Maximum number of conversation turns
    """
    print(f"\n{'=' * 80}")
    print(f"USER: {user_message}")
    print(f"{'=' * 80}\n")

    # Initialize conversation with only tool_search available
    messages = [{"role": "user", "content": user_message}]

    for turn in range(max_turns):
        print(f"\n--- Turn {turn + 1} ---")

        # Call Claude with current message history
        response = claude_client.messages.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOL_LIBRARY + [TOOL_SEARCH_DEFINITION],
            messages=messages,
            # IMPORTANT: This beta header enables tool definitions in tool results
            extra_headers={"anthropic-beta": "advanced-tool-use-2025-11-20"},
        )

        # Add assistant's response to messages
        messages.append({"role": "assistant", "content": response.content})

        # Check if we're done
        if response.stop_reason == "end_turn":
            print("\n✓ Conversation complete\n")
            # Print final response
            for block in response.content:
                if block.type == "text":
                    print(f"ASSISTANT: {block.text}")
            break

        # Handle tool uses
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "text":
                    print(f"\nASSISTANT: {block.text}")

                elif block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    print(f"\n🔧 Tool invocation: {tool_name}")
                    print(f"   Input: {json.dumps(tool_input, indent=2)}")

                    if tool_name == "tool_search":
                        # Handle tool search
                        query = tool_input["query"]
                        top_k = tool_input.get("top_k", 5)

                        # Get tool references
                        tool_references = handle_tool_search(query, top_k)

                        # Create tool result with tool_reference content blocks
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": tool_references,
                            }
                        )
                    else:
                        # Execute the discovered tool with mock data
                        mock_result = mock_tool_execution(tool_name, tool_input)

                        # Print a preview of the result
                        if len(mock_result) > 150:
                            print(f"   ✅ Mock result: {mock_result[:150]}...")
                        else:
                            print(f"   ✅ Mock result: {mock_result}")

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": mock_result,
                            }
                        )

            # Add tool results to messages
            if tool_results:
                messages.append({"role": "user", "content": tool_results})
        else:
            print(f"\nUnexpected stop reason: {response.stop_reason}")
            break

    print(f"\n{'=' * 80}\n")


print("✓ Conversation loop implemented")
```

??? note "輸出"

    ```text
    ✓ Conversation loop implemented
    ```

## 範例 1：天氣查詢

我們用一個簡單的天氣問題測試。Claude 應該：
1. 呼叫 `tool_search` 找天氣 tool
2. 在結果中收到天氣 tool 的定義
3. 使用找到的其中一個 tool

```python
run_tool_search_conversation("What's the weather like in Tokyo?")
```

??? note "輸出"

    ```text

    ================================================================================
    USER: What's the weather like in Tokyo?
    ================================================================================


    --- Turn 1 ---

    🔧 Tool invocation: get_weather
       Input: {
      "location": "Tokyo"
    }
       ✅ Mock result: {"location": "Tokyo", "temperature": 75, "unit": "fahrenheit", "conditions": "partly cloudy", "humidity": 61, "wind_speed": 9}

    --- Turn 2 ---

    ✓ Conversation complete

    ASSISTANT: The weather in Tokyo is currently:
    - **Temperature:** 75°F (about 24°C)
    - **Conditions:** Partly cloudy
    - **Humidity:** 61%
    - **Wind Speed:** 9 mph

    It's a pleasant day with comfortable temperatures and some cloud cover!

    ================================================================================
    ```

## 範例 2：財務查詢

再試一個需要找到並使用財務 tool 的財務計算查詢：

```python
run_tool_search_conversation(
    "If I invest $10,000 at 5% annual interest for 10 years with monthly compounding, how much will I have?"
)
```

??? note "輸出"

    ```text

    ================================================================================
    USER: If I invest $10,000 at 5% annual interest for 10 years with monthly compounding, how much will I have?
    ================================================================================


    --- Turn 1 ---

    🔧 Tool invocation: calculate_compound_interest
       Input: {
      "principal": 10000,
      "rate": 5,
      "years": 10,
      "frequency": "monthly"
    }
       ✅ Mock result: {"principal": 10000, "rate": 5, "years": 10, "compounding_frequency": "monthly", "final_amount": 16470.09, "interest_earned": 6470.09}

    --- Turn 2 ---

    ✓ Conversation complete

    ASSISTANT: If you invest $10,000 at 5% annual interest for 10 years with monthly compounding, you will have:

    **Final Amount: $16,470.09**

    This means you'll earn **$6,470.09** in interest over the 10-year period.

    The monthly compounding means that interest is calculated and added to your principal every month, which allows your investment to grow faster than with annual compounding due to the effect of earning "interest on interest" more frequently.

    ================================================================================
    ```

## 結論

這本 cookbook 實作了 client 端的 tool search 系統，讓 Claude 能有效率地處理大型 tool 庫。我們涵蓋了：

- **語意 tool 探索**：用 embedding 把自然語言查詢對應到相關的 tool，讓 Claude 不用預先看到所有可用 tool，也能找到對的能力
- **動態載入 tool**：用 Claude 的 tool search 功能在 tool result 中回傳 tool 定義，讓 Claude 在對話中途就能探索並立刻使用新 tool
- **Context 最佳化**：把初始 context 從幾千個 token（19 個以上的 tool 定義）降到只剩單一的 `tool_search` 定義，context 用量降低 90% 以上

### 套用到你的專案

以下情況可以考慮 tool search：
- 你有 **超過 20 個專用 tool**，而 context 用量成為考量
- 你的 tool 庫**隨時間成長**，手動整理變得不實際
- 你需要支援有幾百個 endpoint 的**特定領域 API**（資料庫操作、內部 microservice、第三方整合）
- **成本與延遲最佳化**是你應用的優先事項

### 下一步

要進一步延伸這個實作：

1. **持久化 embedding**：把 embedding 快取到磁碟，避免每個 session 重新計算，縮短啟動時間
2. **改善搜尋品質**：試不同的 embedding 模型（例如較大的 `all-mpnet-base-v2`），或實作結合語意與關鍵字比對（BM25）的 hybrid search
3. **擴展到更大的 tool 庫**：用幾百或幾千個 tool 測試，看這個模式在 production 規模表現如何
4. **加入 tool metadata**：把使用統計、成本資訊或可靠度分數加進搜尋排名
5. **實作快取**：快取常用的 tool 定義，減少重複搜尋

### 延伸閱讀

- [Claude Tool Use Guide](https://docs.anthropic.com/en/docs/build-with-claude/tool-use) - 用 tool 建構應用的完整指南
- [SentenceTransformers Documentation](https://www.sbert.net/) - 進一步了解 embedding 模型和語意搜尋
- [Tool Search Tool Documentation](https://docs.anthropic.com/en/docs/build-with-claude/tool-use#tool-search) - tool search 模式的官方文件

## 重點整理

- Tool 數量一多，全部預載會吃 context、增加成本，也讓模型更難選對 tool。
- 做法是只給 Claude 一個 `tool_search` meta-tool，需要時再用語意搜尋回傳相關的 tool 定義。
- 搜尋原理是把 tool 描述和查詢都轉成 embedding，用 cosine similarity 排序取前 N 個。
- Tool 定義放在 tool result 裡回傳，Claude 可以在同一段對話中直接使用剛找到的 tool。
- 這個模式的效益在 tool 多（大約 20 個以上）而且會持續成長時最明顯。

## 練習

1. 把搜尋函式回傳的前 N 個結果數量從目前的值改成 1 和 5，觀察 Claude 找 tool 的行為有什麼不同。
2. 在 tool 庫新增兩個不同類別的 tool（例如 Email 或 Calendar），再問一個需要用到新 tool 的問題，確認 `tool_search` 能搜到。
3. 把 embedding 模型從 `all-MiniLM-L6-v2` 換成 `all-mpnet-base-v2`，並把 embedding 存到磁碟快取，比較啟動時間和搜尋結果。
