---
translated: true
source: misc/prompt_caching.ipynb
---

# 透過 Claude API 使用 prompt caching

> 原文：[misc/prompt_caching.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/prompt_caching.ipynb)

快取並重用 prompt context，節省成本並加快回應，附上詳細說明。

## 這篇在做什麼

用一本約 187k token 的長書當 context，示範 prompt caching 的兩種做法：自動 caching 和明確的 cache breakpoint，並比較快取前後的延遲和 token 用量。

## 學完你會

- 在請求最上層加一個 `cache_control`，啟用自動 caching。
- 在多輪對話中使用自動 caching，看 breakpoint 自動往前移。
- 用明確的 cache breakpoint 精細控制哪些內容被快取，並知道什麼時候該選哪種做法。

## 開跑前

需要 Anthropic API key。範例會傳送約 187k token 的內容，會產生實際的 API 費用。

Prompt caching 讓你儲存並重用 prompt 裡的 context，對重複性的任務能把延遲降低超過 2 倍，成本最多降低 90%。

啟用 prompt caching 有兩種方式：

- **自動 caching**（建議）：在請求的最上層加一個 `cache_control` 欄位，系統會自動幫你管理 cache breakpoint。
- **明確的 cache breakpoint**：把 `cache_control` 放在個別的 content block 上，精細控制要快取哪些內容。

這份 cookbook 兩種做法都會示範，先從比較簡單的自動方式開始。

## 設定

```python
%pip install --upgrade 'anthropic>=0.83.0' bs4 requests python-dotenv --quiet
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    ```

```python
import time

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
client = anthropic.Anthropic()
MODEL_NAME = "claude-sonnet-5-5"

# Unique prefix to ensure we don't hit a stale cache from a previous run
TIMESTAMP = int(time.time())
```

我們抓《Pride and Prejudice》的全文（約 187k token）當作大型 context。

```python
def fetch_article_content(url):
    response = requests.get(url, timeout=30)
    soup = BeautifulSoup(response.content, "html.parser")

    for script in soup(["script", "style"]):
        script.decompose()

    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = "\n".join(chunk for chunk in chunks if chunk)

    return text


book_url = "https://www.gutenberg.org/cache/epub/1342/pg1342.txt"
book_content = fetch_article_content(book_url)

print(f"Fetched {len(book_content)} characters from the book.")
print("First 500 characters:")
print(book_content[:500])
```

??? note "輸出"

    ```text
    Fetched 737526 characters from the book.
    First 500 characters:
    The Project Gutenberg eBook of Pride and Prejudice
    This ebook is for the use of anyone anywhere in the United States and
    most other parts of the world at no cost and with almost no restrictions
    whatsoever. You may copy it, give it away or re-use it under the terms
    of the Project Gutenberg License included with this ebook or online
    at www.gutenberg.org. If you are not located in the United States,
    you will have to check the laws of the country where you are located
    before using this eBook.
    Title:
    ```

我們也定義幾個小的 helper，用來取出回應文字並印出用量統計：

```python
def response_text(response):
    """Return the text of a response. Responses can start with a thinking block, so this reads
    the text blocks rather than content[0]."""
    return "".join(block.text for block in response.content if block.type == "text")


def print_usage(response, elapsed):
    """Print token usage and timing for an API response."""
    usage = response.usage
    cache_create = getattr(usage, "cache_creation_input_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)

    print(f"  Time:                {elapsed:.2f}s")
    print(f"  Input tokens:        {usage.input_tokens}")
    print(f"  Output tokens:       {usage.output_tokens}")
    if cache_create:
        print(f"  Cache write tokens:  {cache_create}")
    if cache_read:
        print(f"  Cache read tokens:   {cache_read}")
```

---
## 範例 1：自動 caching（單輪）

自動 caching 是最容易上手的方式。在 `messages.create()` 呼叫的**最上層**加上 `cache_control={"type": "ephemeral"}`，其餘交給系統處理，它會自動把 cache breakpoint 放在最後一個可快取的 block 上。

我們比較三種情境：
1. **不用 caching**：基準
2. **第一次 cached 呼叫**：建立 cache entry（耗時跟基準差不多）
3. **第二次 cached 呼叫**：從 cache 讀取（大幅加速）

### 基準：不用 caching

```python
start = time.time()
baseline_response = client.messages.create(
    model=MODEL_NAME,
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": str(TIMESTAMP)
            + "<book>"
            + book_content
            + "</book>"
            + "\n\nWhat is the title of this book? Only output the title.",
        }
    ],
)
baseline_time = time.time() - start

print(f"Response: {response_text(baseline_response)}")
print_usage(baseline_response, baseline_time)
```

??? note "輸出"

    ```text
    Response: Pride and Prejudice
      Time:                4.89s
      Input tokens:        187364
      Output tokens:       8
    ```

### 第一次自動 caching 呼叫（寫入 cache）

唯一的改變是最上層的 `cache_control` 參數。第一次呼叫會寫入 cache，所以耗時跟基準差不多。

```python
start = time.time()
write_response = client.messages.create(
    model=MODEL_NAME,
    max_tokens=1024,
    cache_control={"type": "ephemeral"},  # <-- one-line change
    messages=[
        {
            "role": "user",
            "content": str(TIMESTAMP)
            + "<book>"
            + book_content
            + "</book>"
            + "\n\nWhat is the title of this book? Only output the title.",
        }
    ],
)
write_time = time.time() - start

print(f"Response: {response_text(write_response)}")
print_usage(write_response, write_time)
```

??? note "輸出"

    ```text
    Response: Pride and Prejudice
      Time:                4.28s
      Input tokens:        3
      Output tokens:       8
      Cache write tokens:  187361
    ```

### 第二次自動 caching 呼叫（cache hit）

同樣的請求再送一次。這次會重用快取的前綴，你應該會看到明顯加速。

```python
start = time.time()
hit_response = client.messages.create(
    model=MODEL_NAME,
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    messages=[
        {
            "role": "user",
            "content": str(TIMESTAMP)
            + "<book>"
            + book_content
            + "</book>"
            + "\n\nWhat is the title of this book? Only output the title.",
        }
    ],
)
hit_time = time.time() - start

print(f"Response: {response_text(hit_response)}")
print_usage(hit_response, hit_time)

print("\n" + "=" * 50)
print("COMPARISON")
print("=" * 50)
print(f"No caching:     {baseline_time:.2f}s")
print(f"Cache write:    {write_time:.2f}s")
print(f"Cache hit:      {hit_time:.2f}s")
print(f"Speedup:        {baseline_time / hit_time:.1f}x")
```

??? note "輸出"

    ```text
    Response: Pride and Prejudice
      Time:                1.48s
      Input tokens:        3
      Output tokens:       8
      Cache read tokens:   187361

    ==================================================
    COMPARISON
    ==================================================
    No caching:     4.89s
    Cache write:    4.28s
    Cache hit:      1.48s
    Speedup:        3.3x
    ```

---
## 範例 2：多輪對話中的自動 caching

自動 caching 在多輪對話中最能發揮。Cache breakpoint 會隨著對話增長**自動往前移**，你不用自己管理任何標記。

| 請求 | Cache 行為 |
|---------|----------------|
| Request 1 | System + User:A 被快取（寫入） |
| Request 2 | System + User:A 從 cache 讀取；Asst:B + User:C 寫入 cache |
| Request 3 | System 到 User:C 從 cache 讀取；Asst:D + User:E 寫入 cache |

```python
system_message = f"{TIMESTAMP} <file_contents> {book_content} </file_contents>"

questions = [
    "What is the title of this novel?",
    "Who are Mr. and Mrs. Bennet?",
    "What is Netherfield Park?",
    "What is the main theme of this novel?",
]

conversation = []

for i, question in enumerate(questions, 1):
    print(f"\n{'=' * 50}")
    print(f"Turn {i}: {question}")
    print("=" * 50)

    conversation.append({"role": "user", "content": question})

    start = time.time()
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        cache_control={"type": "ephemeral"},  # automatic caching
        system=system_message,
        messages=conversation,
    )
    elapsed = time.time() - start

    assistant_reply = response_text(response)
    conversation.append({"role": "assistant", "content": assistant_reply})

    print(f"\nAssistant: {assistant_reply[:200]}{'...' if len(assistant_reply) > 200 else ''}")
    print()
    print_usage(response, elapsed)
```

??? note "輸出"

    ```text

    ==================================================
    Turn 1: What is the title of this novel?
    ==================================================

    Assistant: The title of this novel is **Pride and Prejudice**, written by **Jane Austen**.

      Time:                5.19s
      Input tokens:        3
      Output tokens:       24
      Cache write tokens:  187361

    ==================================================
    Turn 2: Who are Mr. and Mrs. Bennet?
    ==================================================

    Assistant: Mr. and Mrs. Bennet are a married couple who are central characters in the novel. They live at **Longbourn** and are the parents of **five daughters**: Jane, Elizabeth, Mary, Catherine (Kitty), and Ly...

      Time:                8.27s
      Input tokens:        3
      Output tokens:       272
      Cache write tokens:  38
      Cache read tokens:   187361

    ==================================================
    Turn 3: What is Netherfield Park?
    ==================================================

    Assistant: **Netherfield Park** is a large estate located near the village of **Longbourn** in Hertfordshire, where the Bennet family lives. It plays an important role in the novel as it is the home that is let ...

      Time:                8.74s
      Input tokens:        3
      Output tokens:       300
      Cache write tokens:  283
      Cache read tokens:   187399

    ==================================================
    Turn 4: What is the main theme of this novel?
    ==================================================

    ... (省略 10 行)
    ```

第一輪之後，之後每一輪幾乎 100% 的 input token 都是從 cache 讀取。對話的程式碼只是一個普通的訊息 list，個別 block 上不需要任何特殊的 `cache_control` 標記。

---
## 範例 3：明確的 cache breakpoint

想要更多控制，你可以直接把 `cache_control` 放在個別的 content block 上。適合以下情況：

- 想讓不同區段用不同的 TTL 快取
- 需要把 system prompt 跟訊息內容分開快取
- 想精細控制哪些內容被快取

你也可以兩種方式合用：system prompt 用明確 breakpoint，對話則交給自動 caching。

下面我們把 `cache_control` 直接放在書的內容 block 上，並在每一輪手動把 breakpoint 往前移。

```python
class ConversationWithExplicitCaching:
    """Multi-turn conversation that manually places cache_control on the last user message."""

    def __init__(self):
        self.turns = []

    def add_user(self, content):
        self.turns.append({"role": "user", "content": [{"type": "text", "text": content}]})

    def add_assistant(self, content):
        self.turns.append({"role": "assistant", "content": [{"type": "text", "text": content}]})

    def get_messages(self):
        """Return messages with cache_control on the last user message."""
        result = []
        last_user_idx = max(i for i, t in enumerate(self.turns) if t["role"] == "user")

        for i, turn in enumerate(self.turns):
            if i == last_user_idx:
                result.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": turn["content"][0]["text"],
                                "cache_control": {"type": "ephemeral"},
                            }
                        ],
                    }
                )
            else:
                result.append(turn)

        return result


conv = ConversationWithExplicitCaching()

for i, question in enumerate(questions, 1):
    print(f"\n{'=' * 50}")
    print(f"Turn {i}: {question}")
    print("=" * 50)

    conv.add_user(question)

    start = time.time()
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": system_message,
                "cache_control": {"type": "ephemeral"},  # explicit breakpoint on system
            },
        ],
        messages=conv.get_messages(),
    )
    elapsed = time.time() - start

    assistant_reply = response_text(response)
    conv.add_assistant(assistant_reply)

    print(f"\nAssistant: {assistant_reply[:200]}{'...' if len(assistant_reply) > 200 else ''}")
    print()
    print_usage(response, elapsed)
```

??? note "輸出"

    ```text

    ==================================================
    Turn 1: What is the title of this novel?
    ==================================================

    Assistant: The title of this novel is **Pride and Prejudice**, written by **Jane Austen**.

      Time:                4.53s
      Input tokens:        3
      Output tokens:       24
      Cache read tokens:   187361

    ==================================================
    Turn 2: Who are Mr. and Mrs. Bennet?
    ==================================================

    Assistant: Mr. and Mrs. Bennet are a married couple who are central characters in the novel. They live at **Longbourn** and are the parents of **five daughters**: Jane, Elizabeth (Lizzy), Mary, Catherine (Kitty)...

      Time:                7.57s
      Input tokens:        3
      Output tokens:       283
      Cache read tokens:   187399

    ==================================================
    Turn 3: What is Netherfield Park?
    ==================================================

    Assistant: **Netherfield Park** is a large estate located near the village of **Longbourn** in Hertfordshire, where the Bennet family lives. It plays an important role in the novel as it is the residence that se...

      Time:                6.85s
      Input tokens:        3
      Output tokens:       300
      Cache write tokens:  294
      Cache read tokens:   187399

    ==================================================
    Turn 4: What is the main theme of this novel?
    ==================================================

    Assistant: **Pride and Prejudice** explores several interconnected themes throughout the novel. Here are the main ones:
    ... (省略 9 行)
    ```

---
## 選擇哪種做法

| | 自動 caching | 明確 breakpoint |
|---|---|---|
| **易用性** | 改一行就好 | 要自己放置和移動 `cache_control` 標記 |
| **多輪對話** | Breakpoint 自動往前移 | 你自己管理 breakpoint 位置 |
| **精細控制** | 沒有 | 最多 4 個獨立 breakpoint |
| **混合 TTL** | 自動 breakpoint 只有單一 TTL | 每個 breakpoint 可用不同 TTL |
| **可合用** | 可以：自動加明確一起用 | 可以 |

**先從自動 caching 開始。** 它用最少的力氣涵蓋大多數情境。需要精細控制時再改用明確 breakpoint。

### 重要細節

- **最短可快取長度：** 依模型而異（例如 Claude Opus 5.5 是 512 token），見下面連結的 prompt caching 文件。比這短的前綴會正常處理，但不會被快取。
- **Cache TTL：** 預設 5 分鐘（每次 hit 都會刷新）。也有 1 小時 TTL 可用，價格是基本 input 價格的 2 倍。
- **定價：** Cache 寫入是基本 input 價格的 1.25 倍。Cache 讀取是基本 input 價格的 0.1 倍或更低，依模型而定。
- **Breakpoint 上限：** 每個請求最多 4 個明確 breakpoint。自動 caching 會用掉其中一個名額。

完整細節見 [prompt caching 文件](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)。

## 重點整理
- Prompt caching 把重複使用的長 context 存起來，延遲降低超過 2 倍，成本最多降 90%。
- 自動 caching 只要在最上層加一個 `cache_control`，多輪對話時 breakpoint 會自己前移。
- 第一次呼叫是寫入 cache（比基本價貴 1.25 倍），之後的呼叫才是便宜的讀取。
- 需要不同 TTL 或獨立快取 system prompt 時，才用明確 breakpoint（最多 4 個）。
- 前綴太短不會被快取，快取預設 5 分鐘過期，每次 hit 會刷新。

## 練習
1. 把範例 1 的問題換成別的，確認第二次呼叫仍然 cache hit。
2. 在範例 2 多加兩輪對話，觀察 cache 讀取比例的變化。
3. 在範例 3 把 system prompt 另外加一個 `cache_control` breakpoint，比較用量統計。
