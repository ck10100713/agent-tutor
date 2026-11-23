---
translated: true
source: misc/speculative_prompt_caching.ipynb
---

# Speculative prompt caching

> 原文：[misc/speculative_prompt_caching.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/speculative_prompt_caching.ipynb)

趁使用者還在組織問題時，先預熱 cache，降低 time-to-first-token。

## 這篇在做什麼

這份 cookbook 示範「Speculative Prompt Caching」：在使用者還在打字時就先預熱 cache，藉此降低 time-to-first-token（TTFT）。你會跑標準 prompt caching 和 speculative 版本，比較延遲差異。

## 學完你會

- 用 1-token 的請求，在使用者打字時先把大型 context 寫進 cache。
- 比較有無 speculative caching 的 TTFT。
- 用 `cache_read_input_tokens` 驗證 cache 是否命中，並掌握實務上的最佳做法。

## 開跑前

需要 Anthropic API key，並會下載一份大型文件當 context。

這份 cookbook 示範「Speculative Prompt Caching」，這是一種在使用者還在組織問題時就預熱 cache，來降低 time-to-first-token（TTFT）的模式。

**沒有 Speculative Caching：**
1. 使用者輸入問題（3 秒）
2. 使用者送出問題
3. API 把 context 載入 cache，同時產生回應

**有 Speculative Caching：**
1. 使用者開始打字（立刻開始預熱 cache）
2. 使用者繼續打字（cache 預熱在背景完成）
3. 使用者送出問題
4. API 用已預熱的 cache 產生回應

## Setup

首先安裝需要的套件：

```python
%pip install anthropic httpx --quiet
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

```python
import asyncio
import copy
import datetime
import time

import httpx
from anthropic import AsyncAnthropic

# Configuration constants
MODEL = "claude-sonnet-5-5"
SQLITE_SOURCES = {
    "btree.h": "https://sqlite.org/src/raw/18e5e7b2124c23426a283523e5f31a4bff029131b795bb82391f9d2f3136fc50?at=btree.h",
    "btree.c": "https://sqlite.org/src/raw/63ca6b647342e8cef643863cd0962a542f133e1069460725ba4461dcda92b03c?at=btree.c",
}
DEFAULT_CLIENT_ARGS = {
    "system": "You are an expert systems programmer helping analyze database internals.",
    "max_tokens": 4096,
}
```

## Helper Functions

設定下載大型 context 和準備訊息的 function：

````python
async def get_sqlite_sources() -> dict[str, str]:
    print("Downloading SQLite source files...")

    source_files = {}
    start_time = time.time()

    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = []

        async def download_file(filename: str, url: str) -> tuple[str, str]:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            print(f"Successfully downloaded {filename}")
            return filename, response.text

        for filename, url in SQLITE_SOURCES.items():
            tasks.append(download_file(filename, url))

        results = await asyncio.gather(*tasks)
        source_files = dict(results)

    duration = time.time() - start_time
    print(f"Downloaded {len(source_files)} files in {duration:.2f} seconds")
    return source_files


async def create_initial_message():
    sources = await get_sqlite_sources()
    # Prepare the initial message with the source code as context.
    # A Timestamp is included to prevent cache sharing across different runs.
    initial_message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": f"""
Current time: {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Source to Analyze:

btree.h:
```c
{sources["btree.h"]}
```

btree.c:
```c
{sources["btree.c"]}
```""",
                "cache_control": {"type": "ephemeral"},
            }
        ],
    }
    return initial_message


async def sample_one_token(client: AsyncAnthropic, messages: list):
    """Send a single-token request to warm up the cache"""
    args = copy.deepcopy(DEFAULT_CLIENT_ARGS)
    args["max_tokens"] = 1
    await client.messages.create(
        messages=messages,
        model=MODEL,
        **args,
    )


def print_query_statistics(response, query_type: str) -> None:
    print(f"\n{query_type} query statistics:")
    print(f"\tInput tokens: {response.usage.input_tokens}")
    print(f"\tOutput tokens: {response.usage.output_tokens}")
    print(f"\tCache read input tokens: {getattr(response.usage, 'cache_read_input_tokens', '---')}")
    print(
        f"\tCache creation input tokens: {getattr(response.usage, 'cache_creation_input_tokens', '---')}"
    )
````

## 範例 1：標準 Prompt Caching（沒有 Speculative Caching）

先看標準 prompt caching 怎麼運作。使用者輸入問題，然後我們把整份 context 加問題一起送給 API：

```python
async def standard_prompt_caching_demo():
    client = AsyncAnthropic()

    # Prepare the large context
    initial_message = await create_initial_message()

    # Simulate user typing time (in real app, this would be actual user input)
    print("User is typing their question...")
    await asyncio.sleep(3)  # Simulate 3 seconds of typing
    user_question = "What is the purpose of the BtShared structure?"
    print(f"User submitted: {user_question}")

    # Now send the full request (context + question)
    full_message = copy.deepcopy(initial_message)
    full_message["content"].append(
        {"type": "text", "text": f"Answer the user's question: {user_question}"}
    )

    print("\nSending request to API...")
    start_time = time.time()

    # Measure time to first token
    first_token_time = None
    async with client.messages.stream(
        messages=[full_message],
        model=MODEL,
        **DEFAULT_CLIENT_ARGS,
    ) as stream:
        async for text in stream.text_stream:
            if first_token_time is None and text.strip():
                first_token_time = time.time() - start_time
                print(f"\n🕐 Time to first token: {first_token_time:.2f} seconds")
                break

        # Get the full response
        response = await stream.get_final_message()

    total_time = time.time() - start_time
    print(f"Total response time: {total_time:.2f} seconds")
    print_query_statistics(response, "Standard Caching")

    return first_token_time, total_time
```

```python
# Run the standard demo
standard_ttft, standard_total = await standard_prompt_caching_demo()
```

??? note "輸出"

    ```text
    Downloading SQLite source files...
    Successfully downloaded btree.h
    Successfully downloaded btree.c
    Downloaded 2 files in 0.30 seconds
    User is typing their question...
    User submitted: What is the purpose of the BtShared structure?

    Sending request to API...

    🕐 Time to first token: 20.87 seconds
    Total response time: 28.32 seconds

    Standard Caching query statistics:
    	Input tokens: 22
    	Output tokens: 362
    	Cache read input tokens: 0
    	Cache creation input tokens: 151629
    ```

## 範例 2：Speculative Prompt Caching

現在看 speculative prompt caching 怎麼在使用者打字時預熱 cache，改善 TTFT：

```python
async def speculative_prompt_caching_demo():
    client = AsyncAnthropic()

    # The user has a large amount of context they want to interact with,
    # in this case it's the sqlite b-tree implementation (~150k tokens).
    initial_message = await create_initial_message()

    # Start speculative caching while user is typing
    print("User is typing their question...")
    print("🔥 Starting cache warming in background...")

    # While the user is typing out their question, we sample a single token
    # from the context the user is going to be interacting with with explicit
    # prompt caching turned on to warm up the cache.
    cache_task = asyncio.create_task(sample_one_token(client, [initial_message]))

    # Simulate user typing time
    await asyncio.sleep(3)  # Simulate 3 seconds of typing
    user_question = "What is the purpose of the BtShared structure?"
    print(f"User submitted: {user_question}")

    # Ensure cache warming is complete
    await cache_task
    print("✅ Cache warming completed!")

    # Prepare messages for cached query. We make sure we
    # reuse the same initial message as was cached to ensure we have a cache hit.
    cached_message = copy.deepcopy(initial_message)
    cached_message["content"].append(
        {"type": "text", "text": f"Answer the user's question: {user_question}"}
    )

    print("\nSending request to API (with warm cache)...")
    start_time = time.time()

    # Measure time to first token
    first_token_time = None
    async with client.messages.stream(
        messages=[cached_message],
        model=MODEL,
        **DEFAULT_CLIENT_ARGS,
    ) as stream:
        async for text in stream.text_stream:
            if first_token_time is None and text.strip():
                first_token_time = time.time() - start_time
                print(f"\n🚀 Time to first token: {first_token_time:.2f} seconds")
                break

        # Get the full response
        response = await stream.get_final_message()

    total_time = time.time() - start_time
    print(f"Total response time: {total_time:.2f} seconds")
    print_query_statistics(response, "Speculative Caching")

    return first_token_time, total_time
```

```python
# Run the speculative caching demo
speculative_ttft, speculative_total = await speculative_prompt_caching_demo()
```

??? note "輸出"

    ```text
    Downloading SQLite source files...
    Successfully downloaded btree.h
    Successfully downloaded btree.c
    Downloaded 2 files in 0.36 seconds
    User is typing their question...
    🔥 Starting cache warming in background...
    User submitted: What is the purpose of the BtShared structure?
    ✅ Cache warming completed!

    Sending request to API (with warm cache)...

    🚀 Time to first token: 1.94 seconds
    Total response time: 8.40 seconds

    Speculative Caching query statistics:
    	Input tokens: 22
    	Output tokens: 330
    	Cache read input tokens: 151629
    	Cache creation input tokens: 0
    ```

## 效能比較

比較結果，看 speculative caching 的好處：

```python
print("=" * 60)
print("PERFORMANCE COMPARISON")
print("=" * 60)

print("\nStandard Prompt Caching:")
print(f"  Time to First Token: {standard_ttft:.2f} seconds")
print(f"  Total Response Time: {standard_total:.2f} seconds")

print("\nSpeculative Prompt Caching:")
print(f"  Time to First Token: {speculative_ttft:.2f} seconds")
print(f"  Total Response Time: {speculative_total:.2f} seconds")

ttft_improvement = (standard_ttft - speculative_ttft) / standard_ttft * 100
total_improvement = (standard_total - speculative_total) / standard_total * 100

print("\n🎯 IMPROVEMENTS:")
print(
    f"  TTFT Improvement: {ttft_improvement:.1f}% ({standard_ttft - speculative_ttft:.2f}s faster)"
)
print(
    f"  Total Time Improvement: {total_improvement:.1f}% ({standard_total - speculative_total:.2f}s faster)"
)
```

??? note "輸出"

    ```text
    ============================================================
    PERFORMANCE COMPARISON
    ============================================================

    Standard Prompt Caching:
      Time to First Token: 20.87 seconds
      Total Response Time: 28.32 seconds

    Speculative Prompt Caching:
      Time to First Token: 1.94 seconds
      Total Response Time: 8.40 seconds

    🎯 IMPROVEMENTS:
      TTFT Improvement: 90.7% (18.93s faster)
      Total Time Improvement: 70.4% (19.92s faster)
    ```

## 重點

1. **Speculative caching 能大幅降低 TTFT**，做法是在使用者打字時預熱 cache
2. **這個模式在 context 很大時最有效**（超過 1000 個 token），而且會在多次查詢間重複使用
3. **實作很簡單**，只要在使用者打字時送一個 1-token 的請求
4. **Cache 預熱與使用者輸入平行進行**，等於把建立 cache 的時間「藏」起來

## 最佳做法

- 盡早開始預熱 cache（例如使用者 focus 到輸入框時）
- 預熱和實際請求要用完全相同的 context，確保 cache 命中
- 監控 `cache_read_input_tokens` 來驗證 cache 命中
- 加上 timestamp，避免不同 session 間意外共用 cache

## 重點整理

- TTFT 的瓶頸之一是第一次載入大型 context 到 cache，這段時間可以藏在使用者打字的空檔。
- 預熱只要送 1-token 的請求，成本很低。
- 預熱和正式請求的 context 必須完全一致，cache 才會命中。
- 這個做法在大 context 且會重複使用時最划算。
- 用 `cache_read_input_tokens` 確認真的命中，並用 timestamp 避免 session 間誤共用。

## 練習

1. 把範例 2 的模擬打字時間從 3 秒改成 1 秒，觀察 TTFT 的改善幅度怎麼變。
2. 故意在預熱和正式請求的 context 之間加一個字元差異，用 `cache_read_input_tokens` 確認 cache 沒命中。
3. 把預熱邏輯包成函式，在使用者每次輸入框 focus 時才觸發一次，並避免重複送出預熱請求。
