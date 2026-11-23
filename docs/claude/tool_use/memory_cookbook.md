---
translated: true
source: tool_use/memory_cookbook.ipynb
---

# Claude 的 Memory 與 context 管理

> 原文：[tool_use/memory_cookbook.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/memory_cookbook.ipynb)

用 Claude 的 memory tool 和 context editing，打造有持久記憶的 AI agent。

## 這篇在做什麼

跨多個 session 或長時間執行的 agent 會遇到兩個問題：對話之間學到的東西會消失，以及 context window 在長對話中被塞滿。這篇用 Claude 的 memory tool 和 context editing 解決這兩件事，並做一個 Code Review Assistant 當 demo：第一次 review 學到的 bug 模式，下一次對話直接拿來用。

## 學完你會

- 啟用 memory tool，讓 Claude 把學到的模式寫進 `/memories`，並在全新對話中讀回來用
- 設定 context editing（清除舊的 tool 結果和 thinking block），讓長 session 不爆 context 又不丟長期記憶
- 套用 memory 安全做法，包含 path traversal 防護和 memory poisoning 的緩解策略

## 開跑前

- 需要 Anthropic API key，放進 `.env`
- Python 3.10 以上

AI agent 如果跨多個 session 執行，或要處理長時間任務，會遇到兩個關鍵挑戰：在對話之間會忘掉已學到的模式，以及長時間互動中 context window 會被填滿。

這份 cookbook 示範怎麼用 Claude 的 memory tool 和 context editing 功能來解決這些挑戰。

## 目錄

1. [Introduction: Why Memory Matters](#introduction)
2. [Use Cases](#use-cases)
3. [Quick Start Examples](#quick-start)
4. [How It Works](#how-it-works)
5. [Code Review Assistant Demo](#demo)
6. [Real-World Applications](#real-world)
7. [Best Practices](#best-practices)

## 先備條件

**需要的知識：**
- Python 基礎（function、class、async/await 基本概念）
- 對 REST API 和 JSON 有基本了解

**需要的工具：**
- Python 3.10 以上
- Anthropic API key（[在這裡申請](https://console.anthropic.com/)）

**建議具備：**
- 熟悉並行程式設計的概念（thread、async）
- 對 LLM 的 context window 有基本了解

## Setup

### VSCode 使用者

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate it
source .venv/bin/activate  # macOS/Linux
# or: .venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. In VSCode: Select .venv as kernel (top right)
```

### API Key

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

API key 在這裡取得：https://console.anthropic.com/

## 1. 簡介：為什麼 Memory 很重要 {#introduction}

這份 cookbook 示範 [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 裡提到的 context engineering 模式的實際做法。那篇文章講了為什麼 context 是有限資源、attention budget 怎麼運作，以及打造有效 agent 的策略，你在這裡會看到這些技巧的實際應用。

### 問題

大型語言模型的 context window 有限（目前所有 Claude model 都是 1M token）。看起來很大，但還是會遇到幾個挑戰：

- **Context 上限**：長對話或複雜任務可能超過可用的 context
- **運算成本**：處理大量 context 很貴，attention 機制的成本隨長度呈平方成長
- **重複的模式**：類似的任務在不同對話中，每次都要重新解釋一遍背景
- **資訊遺失**：context 滿了之後，前面重要的資訊就會消失

### 解法

目前的 Claude model 支援強大的 context 管理功能：

1. **Memory Tool**（`memory_20250818`）：讓 Claude 能跨對話學習
   - Claude 可以把學到的東西寫下來，供之後參考
   - 以檔案為基礎，放在 `/memories` 目錄下
   - 在 client 端實作，你完全掌控

2. **Context Editing**：用兩種策略自動管理 context：
   - **清除 tool use**（`clear_tool_uses_20250919`）：context 變大時，清掉舊的 tool 結果
   - **管理 thinking**（`clear_thinking_20251015`）：管理 extended thinking block（需要啟用 thinking）
   - 觸發條件和保留策略可以設定

### 好處

打造會**在你的特定任務上越做越好**的 AI agent：

- **Session 1**：Claude 解決問題，把模式寫下來
- **Session 2**：Claude 直接套用學到的模式（更快！）
- **長 session**：Context editing 讓對話保持可控

可以想成是給 Claude 一本筆記本，讓它做筆記再回頭查，跟人類的做法一樣。

### 你會學到什麼

讀完這份 cookbook，你將能夠：
- **實作** memory tool，做到跨對話學習
- **設定** context editing 來管理長時間執行的 session
- **套用** memory 安全與組織方式的最佳實務

## 1. 簡介：為什麼 Memory 很重要 {#introduction}

這份 cookbook 示範 [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 裡提到的 context engineering 模式的實際做法。那篇文章講了為什麼 context 是有限資源、attention budget 怎麼運作，以及打造有效 agent 的策略，你在這裡會看到這些技巧的實際應用。

### 問題

大型語言模型的 context window 有限（目前所有 Claude model 都是 1M token）。看起來很大，但還是會遇到幾個挑戰：

- **Context 上限**：長對話或複雜任務可能超過可用的 context
- **運算成本**：處理大量 context 很貴，attention 機制的成本隨長度呈平方成長
- **重複的模式**：類似的任務在不同對話中，每次都要重新解釋一遍背景
- **資訊遺失**：context 滿了之後，前面重要的資訊就會消失

### 解法

目前的 Claude model 支援強大的 context 管理功能：

1. **Memory Tool**（`memory_20250818`）：讓 Claude 能跨對話學習
   - Claude 可以把學到的東西寫下來，供之後參考
   - 以檔案為基礎，放在 `/memories` 目錄下
   - 在 client 端實作，你完全掌控

**支援的 model**：Claude Opus 5.5（`claude-opus-5-5`）、Claude Sonnet 5.5（`claude-sonnet-5-5`）、Claude Haiku 5.5（`claude-haiku-5-5`）

### 好處

打造會**在你的特定任務上越做越好**的 AI agent：

- **Session 1**：Claude 解決問題，把模式寫下來
- **Session 2**：Claude 直接套用學到的模式（更快！）
- **長 session**：Context editing 讓對話保持可控

可以想成是給 Claude 一本筆記本，讓它做筆記再回頭查，跟人類的做法一樣。

## 2. 使用情境 {#use-cases}

Memory 和 context 管理可以支援很多新的工作流程：

### 🔍 Code Review Assistant
- 從過去的 review 學習 debug 模式
- 之後遇到類似的 bug 馬上認得
- 累積團隊專屬的程式碼品質知識
- **可上 production**：整合 [claude-code-action](https://github.com/anthropics/claude-code-action) 做 GitHub PR review

### 📚 Research Assistant
- 跨多個 session 累積某個主題的知識
- 把不同研究線索的洞見串起來
- 維護參考書目並追蹤來源

### 💬 客服機器人
- 學習使用者偏好和溝通風格
- 記住常見問題和解法
- 從互動中建立產品知識庫

### 📊 資料分析助手
- 記住資料集的模式和異常
- 儲存有效的分析技巧
- 隨時間累積特定領域的洞見

**支援的 model**：Claude Opus 5.5（`claude-opus-5-5`）、Claude Sonnet 5.5（`claude-sonnet-5-5`）、Claude Haiku 5.5（`claude-haiku-5-5`）

**這份 cookbook 聚焦在 Code Review Assistant**，因為它能清楚展示 memory（學習模式）和 context editing（處理很長的 review）。

## 3. 快速上手範例 {#quick-start}

用幾個簡單的例子看 memory 和 context 管理怎麼運作。

### Setup

首先安裝相依套件並設定環境：

```python
%%capture
# Install required packages
# Option 1: From requirements.txt
# %pip install -q -r requirements.txt

# Option 2: Direct install
%pip install -q anthropic python-dotenv ipykernel
```

**⚠️ 重要**：在這個目錄建立 `.env` 檔：

```bash
# Copy .env.example to .env and add your API key
cp .env.example .env
```

然後編輯 `.env`，填入你從 https://console.anthropic.com/ 取得的 Anthropic API key。

```python
import os
from typing import cast

from anthropic import Anthropic
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Model configuration - use alias for automatic updates
MODEL = "claude-sonnet-5-5"  # Can override via ANTHROPIC_MODEL env var
if os.getenv("ANTHROPIC_MODEL"):
    MODEL = os.getenv("ANTHROPIC_MODEL")

API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found. Copy .env.example to .env and add your API key.")

if not MODEL:
    raise ValueError("ANTHROPIC_MODEL not found. Copy .env.example to .env and set the model.")

MODEL = cast(str, MODEL)

client = Anthropic(api_key=API_KEY)

print("✓ API key loaded")
print(f"✓ Using model: {MODEL}")
```

??? note "輸出"

    ```text
    ✓ API key loaded
    ✓ Using model: claude-sonnet-5-5
    ```

### 範例 1：基本 Memory 用法

看 Claude 怎麼用 memory 儲存資訊，供之後參考。

**Helper function**

這些範例用了 `demo_helpers.py` 裡的 helper function：

- **`run_conversation_loop()`**：處理 API 對話迴圈
  - 在啟用 memory tool 的情況下呼叫 Claude API
  - 執行 tool use（memory 操作）
  - 持續到 Claude 不再使用 tool
  - 回傳最終回應

- **`run_conversation_turn()`**：單一回合（範例 3 會用）
  - 跟上面一樣，但只做一次 API 呼叫就回傳
  - 需要細緻控制時很有用

- **`print_context_management_info()`**：顯示 context 清除的統計
  - 顯示省下多少 token、清掉幾個 tool use
  - 幫助你看出 context editing 什麼時候被觸發

**⚠️ 關於清除 Memory**

下面這個 cell 會清掉所有 memory 檔案，讓 demo 從乾淨狀態開始。這樣重複跑 notebook 時結果才會一致。

**在 production 應用裡**，清掉全部 memory 要想清楚，因為這會永久移除學到的模式。可以考慮改用選擇性刪除，或把 memory 依專案分目錄管理。

````python
# Import helper functions
from memory_demo.demo_helpers import (
    print_context_management_info,
    run_conversation_loop,
    run_conversation_turn,
)
from memory_tool import MemoryToolHandler

# Initialize
client = Anthropic()
memory = MemoryToolHandler(base_path="./demo_memory")

# Clear any existing memories to start fresh
print("🧹 Clearing previous memories...")
memory.clear_all_memory()
print("✓ Memory cleared\n")

# Load example code with a race condition bug
with open("memory_demo/sample_code/web_scraper_v1.py") as f:
    code_to_review = f.read()

messages = [
    {
        "role": "user",
        "content": f"I'm reviewing a multi-threaded web scraper that sometimes returns fewer results than expected. The count is inconsistent across runs. Can you find the issue?\n\n```python\n{code_to_review}\n```",
    }
]

print("=" * 60)
print("📝 SESSION 1: Learning from a bug")
print("=" * 60)

# Run conversation loop
response = run_conversation_loop(
    client=client,
    model=MODEL,
    messages=messages,
    memory_handler=memory,
    system="You are a code reviewer.",
    max_tokens=2048,
    max_turns=5,
    verbose=True,
)

print("\n" + "=" * 60)
print("✅ Session 1 complete!")
print("=" * 60)
````

??? note "輸出"

    ````text
    🧹 Clearing previous memories...
    ✓ Memory cleared

    ============================================================
    📝 SESSION 1: Learning from a bug
    ============================================================

    🔄 Turn 1:
    💬 Claude: I'll review this code for the race condition issue. Let me first check my memory, then analyze the problem.

      🔧 Memory tool: view /memories
      ✓ Result: Directory: /memories
    (empty)

    🔄 Turn 2:
      🔧 Memory tool: create /memories/review.md
      ✓ Result: File created successfully at /memories/review.md

    🔄 Turn 3:
    💬 Claude: ## Code Review: Multi-threaded Web Scraper Race Condition

    ### 🔴 **Critical Issue Found: Race Condition in Shared State**

    You've correctly identified the problem! The code has **race conditions** caused by multiple threads modifying shared lists without synchronization.

    ---

    ### **The Problem**

    **Lines with race conditions:**
    ```python
    self.results.append(result)  # RACE CONDITION
    ```

    **Problem:** 
    - Python's `list.append()` is **NOT thread-safe** for concurrent modifications
    - Multiple threads simultaneously appending can cause:
      - **Lost updates:** One thread's append overwrites another's
      - **Inconsistent state:** Internal list structure can be corrupted
      - **Unpredictable counts:** Results randomly dropped
    ... (省略 225 行)
    ````

**發生了什麼事？**

1. Claude 先查了自己的 memory（第一次跑是空的）
2. 找出 bug：**race condition**，多個 thread 在沒有同步的情況下修改共享狀態（`self.results` 和 `self.failed_urls`）
3. 把這個並行處理的模式存進 memory，供未來參考

接下來看神奇的部分：Claude 在**新對話**裡套用學到的模式：

### 範例 2：跨對話學習

開一個全新的對話，memory 會保留！

````python
# NEW conversation (empty messages)
# Load API client code with similar concurrency issue
with open("memory_demo/sample_code/api_client_v1.py") as f:
    code_to_review = f.read()

messages = [
    {"role": "user", "content": f"Review this API client code:\n\n```python\n{code_to_review}\n```"}
]

print("=" * 60)
print("🚀 SESSION 2: Applying learned pattern")
print("=" * 60)

# Run conversation loop
response = run_conversation_loop(
    client=client,
    model=MODEL,
    messages=messages,
    memory_handler=memory,
    system="You are a code reviewer.",
    max_tokens=2048,
    max_turns=5,
    verbose=True,
)

print("\n" + "=" * 60)
print("✅ Session 2 complete!")
print("=" * 60)
````

??? note "輸出"

    ````text
    ============================================================
    🚀 SESSION 2: Applying learned pattern
    ============================================================

    🔄 Turn 1:
      🔧 Memory tool: view /memories
      ✓ Result: Directory: /memories
    - review.md

    🔄 Turn 2:
      🔧 Memory tool: view /memories/review.md
      ✓ Result:    1: # Code Review: Multi-threaded Web Scraper
       2: 
       3: ## Issue
       4: Revi...

    🔄 Turn 3:
      🔧 Memory tool: str_replace /memories/review.md
      ✓ Result: File /memories/review.md has been edited successfully

    🔄 Turn 4:
    💬 Claude: ## Code Review: Async API Client

    ### Summary
    This code has **concurrency issues** related to shared mutable state being accessed from multiple coroutines without proper synchronization. While the author correctly identifies these as bugs in comments, let me provide a comprehensive review.

    However, the actual race condition risk here is **somewhat overstated** because:
    - List `.append()` is atomic in CPython
    - The `+=` operation on integers is also atomic
    - Coroutines only switch at `await` points, and there are none between the operations

    **BUT** this is still problematic because:
    - It relies on CPython implementation details
    - It's not guaranteed by the language specification
    - The code is not portable to other Python implementations
    - Future refactoring could introduce `await` points that cause real races

    #### 1. **Race Condition on `self.error_count` (Line 51)**
    ```python
    self.error_count += 1  # Not atomic!
    ... (省略 249 行)
    ````

**注意差異：**

- Claude **馬上查了 memory**，找到 thread-safety/並行處理的模式
- **立刻**在 async 程式碼裡認出類似的問題，不用重新學
- 回應**更快**，因為它套用了關於共享可變狀態的已存知識

這就是**跨對話學習**。

### 範例 3：清除 Context 但保留 Memory

**很長的 review session** 要看很多程式檔時會發生什麼事？

- Context 被先前 review 的 tool 結果塞滿
- 但 memory（學到的模式）必須保留

我們來觸發 **context editing**，看 Claude 怎麼自動處理。

**設定說明：** 我們用 `clear_at_least: 50` token，因為 memory tool 操作的結果很小（每個約 50 到 150 token）。在 production 中，tool 結果比較大（例如 web search 或 code execution），要用更高的值，像 3000 到 5000 token。

````python
# Configure context management with BOTH clearing strategies
# Low thresholds for demo - in production use 30-40k tokens
CONTEXT_MANAGEMENT = {
    "edits": [
        # Thinking management MUST come first when combining strategies
        {
            "type": "clear_thinking_20251015",
            "keep": {"type": "thinking_turns", "value": 1},  # Keep only last turn's thinking
        },
        {
            "type": "clear_tool_uses_20250919",
            "trigger": {"type": "input_tokens", "value": 5000},  # Low threshold for demo
            "keep": {"type": "tool_uses", "value": 2},  # Keep last 2 tool uses
            "clear_at_least": {"type": "input_tokens", "value": 2000},
        },
    ]
}

# Adaptive thinking config (required for clear_thinking strategy).
# Thinking text is omitted from responses by default; add "display": "summarized" to see it.
THINKING = {"type": "adaptive"}

# Continue from previous session - memory persists!
print("=" * 60)
print("📚 SESSION 3: Long review session with context clearing")
print("=" * 60)
print()

# Clean up messages - remove any empty content from previous session
# This ensures we have a valid message state to continue from
cleaned_messages = []
for msg in messages:
    if isinstance(msg.get("content"), list):
        # Filter out empty content blocks
        content = [c for c in msg["content"] if c]
        if content:
            cleaned_messages.append({"role": msg["role"], "content": content})
    elif msg.get("content"):
        cleaned_messages.append(msg)

messages = cleaned_messages

# Review 1: Data processor (larger file)
with open("memory_demo/sample_code/data_processor_v1.py") as f:
    data_processor_code = f.read()

messages.append(
    {
        "role": "user",
        "content": f"Review this data processor:\n\n```python\n{data_processor_code}\n```",
    }
)

print("📝 Review 1: Data processor")
response = run_conversation_turn(
    client=client,
    model=MODEL,
    messages=messages,
    memory_handler=memory,
    system="You are a code reviewer.",
    context_management=CONTEXT_MANAGEMENT,
    thinking=THINKING,
    max_tokens=4096,
    verbose=True,
)

# Add response to messages
messages.append({"role": "assistant", "content": response[1]})
if response[2]:
    messages.append({"role": "user", "content": response[2]})

print(f"  📊 Input tokens: {response[0].usage.input_tokens:,}")
context_cleared, saved = print_context_management_info(response[0])
print()

# Review 2: SQL code
with open("memory_demo/sample_code/sql_query_builder.py") as f:
    sql_code = f.read()

messages.append(
    {"role": "user", "content": f"Review this SQL query builder:\n\n```python\n{sql_code}\n```"}
)

print("📝 Review 2: SQL query builder")
response = run_conversation_turn(
    client=client,
    model=MODEL,
    messages=messages,
    memory_handler=memory,
    system="You are a code reviewer.",
    context_management=CONTEXT_MANAGEMENT,
    thinking=THINKING,
    max_tokens=4096,
    verbose=True,
)

messages.append({"role": "assistant", "content": response[1]})
if response[2]:
    messages.append({"role": "user", "content": response[2]})

print(f"  📊 Input tokens: {response[0].usage.input_tokens:,}")
context_cleared, saved = print_context_management_info(response[0])
print()

# Review 3: Add one more review to ensure we trigger clearing
with open("memory_demo/sample_code/web_scraper_v1.py") as f:
    scraper_code = f.read()

messages.append(
    {"role": "user", "content": f"Quick check - any issues here?\n\n```python\n{scraper_code}\n```"}
)

print("📝 Review 3: Web scraper (should trigger clearing)")
response = run_conversation_turn(
    client=client,
    model=MODEL,
    messages=messages,
    memory_handler=memory,
    system="You are a code reviewer.",
    context_management=CONTEXT_MANAGEMENT,
    thinking=THINKING,
    max_tokens=4096,
    verbose=True,
)

messages.append({"role": "assistant", "content": response[1]})
if response[2]:
    messages.append({"role": "user", "content": response[2]})

print(f"  📊 Input tokens: {response[0].usage.input_tokens:,}")
context_cleared, saved = print_context_management_info(response[0])

print()
print("=" * 60)
print("✅ Session 3 complete!")
print("=" * 60)
````

??? note "輸出"

    ```text
    ============================================================
    📚 SESSION 3: Long review session with context clearing
    ============================================================

    📝 Review 1: Data processor
    🧠 Thinking: The user wants me to review a data processor with multiple concurrency and thread-safety issues. Let...
      🔧 Memory tool: str_replace /memories/review.md
      ✓ Result: File /memories/review.md has been edited successfully
      📊 Input tokens: 6,611
      ℹ️  Context below threshold - no clearing triggered

    📝 Review 2: SQL query builder
    🧠 Thinking: The user is now asking me to review a SQL query builder with SQL injection vulnerabilities. This is ...
      🔧 Memory tool: str_replace /memories/review.md
      ✓ Result: File /memories/review.md has been edited successfully
      📊 Input tokens: 7,923
      ✂️  Context editing triggered!
          • Cleared 1 thinking turn(s), saved 166 tokens
          • After clearing: 7,923 tokens

    📝 Review 3: Web scraper (should trigger clearing)
    🧠 Thinking: This is a quick check request for a web scraper with threading issues. Let me quickly identify the p...
      🔧 Memory tool: str_replace /memories/review.md
      ✓ Result: File /memories/review.md has been edited successfully
      📊 Input tokens: 9,052
      ✂️  Context editing triggered!
          • Cleared 2 thinking turn(s), saved 265 tokens
          • After clearing: 9,052 tokens

    ============================================================
    ✅ Session 3 complete!
    ============================================================
    ```

**剛剛發生了什麼？**

隨著 context 在啟用 extended thinking 的多次 review 中變大，context editing 開始生效：
1. **Thinking block 被清除**：先移除前幾輪的舊 thinking
2. **Tool 結果被清除**：超過門檻後，移除舊的 memory tool 結果
3. **Memory 檔案完好**：Claude 仍然可以查詢學到的模式
4. **Token 使用量受控**：thinking 和 tool 結果都省下了 token

這展示了關鍵好處：
- **短期記憶**（對話 context 加 thinking）：清除以節省空間
- **長期記憶**（儲存的模式）：跨 session 保留

來驗證 memory 在清除後是否還在：

```python
# Verify memory persists after context clearing
import os

print("📂 Memory files in demo_memory/:")
print()

for root, _dirs, files in os.walk("./demo_memory"):
    # Calculate relative path for display
    level = root.replace("./demo_memory", "").count(os.sep)
    indent = "  " * level
    folder_name = os.path.basename(root) or "demo_memory"
    print(f"{indent}{folder_name}/")

    sub_indent = "  " * (level + 1)
    for file in files:
        file_path = os.path.join(root, file)
        size = os.path.getsize(file_path)
        print(f"{sub_indent}├── {file} ({size} bytes)")

print()
print("✅ All learned patterns preserved despite context clearing!")
```

??? note "輸出"

    ```text
    📂 Memory files in demo_memory/:

    demo_memory/
      memories/
        ├── review.md (318 bytes)

    ✅ All learned patterns preserved despite context clearing!
    ```

## 4. 運作方式 {#how-it-works}

### Memory Tool 架構

Memory tool 是**client 端**的，儲存由你控制。Claude 發出 tool call，由你的應用程式執行。

#### Memory Tool 指令

| Command | Description | Example |
|---------|-------------|---------|
| `view` | Show directory or file contents | `{"command": "view", "path": "/memories"}` |
| `create` | Create or overwrite a file | `{"command": "create", "path": "/memories/notes.md", "file_text": "..."}` |
| `str_replace` | Replace text in a file | `{"command": "str_replace", "path": "...", "old_str": "...", "new_str": "..."}` |
| `insert` | Insert text at line number | `{"command": "insert", "path": "...", "insert_line": 2, "insert_text": "..."}` |
| `delete` | Delete a file or directory | `{"command": "delete", "path": "/memories/old.txt"}` |
| `rename` | Rename or move a file | `{"command": "rename", "old_path": "...", "new_path": "..."}` |

完整實作（含 path 驗證和安全措施）請看 `memory_tool.py`。

### Thinking 管理（`clear_thinking_20251015`）

使用 extended thinking 時，thinking block 會累積並消耗 token。`clear_thinking` 策略會自動管理它們。

**重要**：這個策略需要在 API 呼叫中啟用 `thinking`。

**API 呼叫模式**（啟用 extended thinking）：

```python
response = client.beta.messages.create(
    betas=["context-management-2025-06-27"],  # Required beta flag
    model="claude-sonnet-5-5",
    messages=messages,
    tools=[{"type": "memory_20250818", "name": "memory"}],
    thinking={"type": "adaptive"},  # Enable thinking
    context_management={  # Context editing config
        "edits": [
            {
                "type": "clear_thinking_20251015",
                "keep": {"type": "thinking_turns", "value": 1}  # Keep last turn only
            },
            {
                "type": "clear_tool_uses_20250919",
                "trigger": {"type": "input_tokens", "value": 35000},
                "keep": {"type": "tool_uses", "value": 5}
            }
        ]
    },
    max_tokens=2048
)
```
**重點：**
- 組合多個策略時，`clear_thinking` 必須放在**最前面**
- 需要啟用 thinking（現行 model 用 `thinking={"type": "adaptive"}`，不再使用 token budget）
- 用 `"keep": "all"` 保留所有 thinking block，可以讓 cache 命中率最高
- Thinking 的 trigger 是選填的（依 `keep` 的值決定清除）

### 了解 Demo 程式碼

`code_review_demo.py` 的關鍵實作細節：

```python
class CodeReviewAssistant:
    def __init__(self, memory_storage_path="./memory_storage"):
        self.client = Anthropic()
        self.memory_handler = MemoryToolHandler(base_path=memory_storage_path)
        self.messages = []
    
    def review_code(self, code, filename, description=""):
        # 1. Add user message
        self.messages.append({...})
        
        # 2. Conversation loop with tool execution
        while True:
            response = self.client.beta.messages.create(
                model=MODEL,
                system=self._create_system_prompt(),
                messages=self.messages,
                tools=[{"type": "memory_20250818", "name": "memory"}],
                betas=["context-management-2025-06-27"],
                context_management=CONTEXT_MANAGEMENT
            )
            
            # 3. Execute tool uses
            tool_results = []
            for content in response.content:
                if content.type == "tool_use":
                    result = self._execute_tool_use(content)
                    tool_results.append({...})
            
            # 4. Continue if there are tool uses, otherwise done
            if tool_results:
                self.messages.append({"role": "user", "content": tool_results})
            else:
                break
```

**關鍵模式**：只要還有 tool use 就持續呼叫 API，執行它們並把結果回傳給 Claude。

### Claude 實際學到什麼

Memory 的強大之處在於**語意層面的模式辨識**，而不只是語法：

**Session 1：Thread 版網頁爬蟲**

```python
# Bug: Race condition
class WebScraper:
    def __init__(self):
        self.results = []  # Shared state!
    
    def scrape_urls(self, urls):
        with ThreadPoolExecutor() as executor:
            for future in as_completed(futures):
                self.results.append(future.result())  # RACE!
```

**Claude 存進 Memory 的內容**（範例檔案：`/memories/concurrency_patterns/thread_safety.md`）：

遇到這個模式時，Claude 會把以下洞見存進它的 memory 檔案：
- **症狀**：並行操作的結果不一致
- **原因**：共享的可變狀態（list/dict）被多個 thread 修改
- **解法**：用 lock、thread-safe 資料結構，或改成回傳結果
- **警訊**：thread callback 裡用 instance 變數、沒用到的 lock、計數器遞增

---

**Session 2：Async API Client**（新對話！）

Claude **先**查 memory，找到 thread-safety 模式，接著：
1. **認出**async 程式碼裡的類似模式（coroutine 也可能交錯執行）
2. **立刻套用**解法（不用重新學）
3. **參照**已存的知識來解釋

```python
# Claude spots this immediately:
async def fetch_all(self, endpoints):
    for coro in asyncio.as_completed(tasks):
        self.responses.append(await coro)  # Same pattern!
```

---

**為什麼重要：**

- ❌ **語法檢查工具**完全抓不到 race condition
- ✅ **Claude 學到**架構層級的模式，並能跨情境套用
- ✅ **跨語言**：這個模式也適用於 Go、Java、Rust 的並行處理
- ✅ **越用越好**：每次 review 都會增加知識庫

### 範例程式檔

Demo 用了這幾個範例檔（全部都有並行/thread-safety 的 bug）：

- `memory_demo/sample_code/web_scraper_v1.py`：Race condition，thread 修改共享狀態
- `memory_demo/sample_code/api_client_v1.py`：async 情境下類似的並行 bug
- `memory_demo/sample_code/data_processor_v1.py`：多個並行問題，用於長 session demo

來看其中一個：

**`memory_demo/sample_code/web_scraper_v1.py`**

```python
"""
Concurrent web scraper with a race condition bug.
Multiple threads modify shared state without synchronization.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

import requests


class WebScraper:
    """Web scraper that fetches multiple URLs concurrently."""

    def __init__(self, max_workers: int = 10):
        self.max_workers = max_workers
        self.results = []  # BUG: Shared mutable state accessed by multiple threads!
        self.failed_urls = []  # BUG: Another race condition!

    def fetch_url(self, url: str) -> Dict[str, any]:
        """Fetch a single URL and return the result."""
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return {
                "url": url,
                "status": response.status_code,
                "content_length": len(response.content),
            }
        except requests.exceptions.RequestException as e:
            return {"url": url, "error": str(e)}

    def scrape_urls(self, urls: List[str]) -> List[Dict[str, any]]:
        """
        Scrape multiple URLs concurrently.

        BUG: self.results is accessed from multiple threads without locking!
        This causes race conditions where results can be lost or corrupted.
        """
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.fetch_url, url) for url in urls]

            for future in as_completed(futures):
                result = future.result()

                # RACE CONDITION: Multiple threads append to self.results simultaneously
                if "error" in result:
                    self.failed_urls.append(result["url"])  # RACE CONDITION
                else:
                    self.results.append(result)  # RACE CONDITION

        return self.results
```

**Bug**：多個 thread 在沒有 lock 的情況下修改 `self.results` 和 `self.failed_urls`！

Claude 會：
1. 找出 race condition
2. 把模式存進 `/memories/concurrency_patterns/thread_safety.md`
3. 在 Session 2 把這個並行處理模式套用到 async 程式碼

### Demo 總覽

我們做了一個完整的 Code Review Assistant，實作在 `memory_demo/code_review_demo.py`。

**執行互動式 demo：**
```bash
python memory_demo/code_review_demo.py
```

Demo 展示了：
1. **Session 1**：review 有 bug 的 Python 程式碼，Claude 學到這個模式
2. **Session 2**：review 類似的程式碼（新對話），Claude 套用學到的模式
3. **Session 3**：很長的 review session，context editing 讓它保持可控

## 7. 最佳實務與安全 {#best-practices}

### Memory 管理

**該做：**
- ✅ 儲存跟任務相關的模式，不是對話歷史
- ✅ 用清楚的目錄結構整理
- ✅ 用有描述性的檔名
- ✅ 定期檢查並清理 memory

**不該做：**
- ❌ 儲存敏感資訊（密碼、API key、PII）
- ❌ 讓 memory 無限成長
- ❌ 什麼都不加選擇地存

### 安全：Path Traversal 防護

**關鍵**：一定要驗證 path，防止 directory traversal 攻擊。實作請看 `memory_tool.py`。

### 安全：Memory Poisoning

**⚠️ 關鍵風險**：Memory 檔案會被讀回 Claude 的 context，所以可能成為 prompt injection 的管道。

**緩解策略：**
1. **內容消毒**：儲存前過濾危險的模式
2. **Memory 範圍隔離**：依使用者或專案隔離
3. **Memory 稽核**：記錄並掃描所有 memory 操作
4. **Prompt 設計**：指示 Claude 忽略 memory 裡的指令

完整的安全實作請看 `memory_tool.py`，測試在 `tests/`。

## 結論

### 你完成了什麼

在這份 cookbook 裡，你學會了：
- ✅ **實作 memory tool** 做跨對話學習（Session 1 和 2 展示了模式辨識的持久性）
- ✅ **設定 context editing**，包含 token 觸發條件和保留策略（Session 3 展示了自動清除）
- ✅ **套用安全最佳實務**，包含 path 驗證和防止 memory poisoning

### 套用這些模式

**用在你的專案：**
1. 從單一 memory 檔案存模式開始（例如 `/memories/patterns.md`）
2. Production 的 context editing 觸發點設在 30 到 40k token
3. 實作每個專案獨立的 memory 隔離，避免互相污染

**其他應用：**
- **客服**：儲存使用者偏好和常見問題的解法
- **Research assistant**：跨 session 累積領域知識
- **資料分析**：記住資料集特性和有效的技巧

### 下一步

- **Production 部署**：用 [claude-code-action](https://github.com/anthropics/claude-code-action) 做 GitHub PR review
- **安全強化**：看 `memory_tool.py` 裡的 memory poisoning 緩解措施
- **Extended thinking**：研究 thinking 管理，用在運算量大的任務

### 資源

- [Memory tool 文件](https://docs.claude.com/en/docs/agents-and-tools/tool-use/memory-tool)
- [Claude API 參考](https://docs.claude.com/en/api/messages)
- [Support](https://support.claude.com)

Memory 和 context 管理目前是 **beta**，歡迎回報意見幫我們改進！

## 重點整理

- Context window 再大也是有限資源，長任務需要把「該記住的」和「可以丟的」分開處理。
- Memory tool 是 client 端實作：Claude 發出檔案操作的 tool call，你的程式決定怎麼存、存在哪，所以安全由你負責。
- Context editing 清的是短期的 tool 結果和 thinking，memory 檔案是長期記憶，兩者互不影響。
- Memory 學到的是語意層級的模式（例如 race condition 的成因和解法），所以能跨語言、跨情境套用。
- Memory 內容會被讀回 context，必須防 path traversal 和 memory poisoning。

## 練習

1. 把 demo 裡 `clear_at_least` 從 50 改成 500，看 context editing 的觸發時機和省下的 token 有什麼變化。
2. 在 memory 目錄加一個你自己的 Python 範例檔（例如有 SQL injection 的程式），跑兩個 session，確認 Claude 在第二個 session 會先查 memory。
3. 在 `memory_tool.py` 的 path 驗證裡，試著傳入 `/memories/../secret.txt`，確認它被擋下，再寫一個測試案例放進 `tests/`。

