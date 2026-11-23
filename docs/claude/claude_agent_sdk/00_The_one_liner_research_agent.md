---
translated: true
source: claude_agent_sdk/00_The_one_liner_research_agent.ipynb
---
# 一行搞定的 research agent

> 原文：[claude_agent_sdk/00_The_one_liner_research_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/00_The_one_liner_research_agent.ipynb)

用 Claude Code SDK 搭配 WebSearch，做一個能自己上網查資料的 research agent。

## 這篇在做什麼

用 Claude Agent SDK 內建的 WebSearch tool，幾行程式就搭出一個會自己搜尋、整理資料的 research agent。接著示範怎麼加上對話記憶、system prompt 和圖片分析，最後包成可重用的模組。

## 學完你會

- 用 `query()` 寫出一個無狀態的 research agent，讓 Claude 自己決定要搜什麼
- 用 `ClaudeSDKClient` 做多輪研究，並用 system prompt 要求附上引用來源
- 啟用 `Read` tool 分析圖片，並設定 `max_buffer_size` 避免 buffer 爆掉

## 開跑前

- Python 3.11 以上
- Anthropic API key，放在 `.env` 裡

研究工作很吃專家時間：分析師手動收集競品情報、法務團隊追蹤法規變動、工程師翻文件查 bug。難的地方不是找資料，而是看了剛找到的東西後，知道下一步該搜什麼。

Claude Agent SDK 讓你能建出自己去探索外部系統的 agent，不用事先寫死流程。傳統的工作流程自動化只會照固定步驟走，research agent 則會看找到什麼就調整策略：追著有希望的線索、整合互相矛盾的來源、判斷資料夠不夠回答問題。

## 這份 cookbook 做完，你可以：

- 用幾行程式碼建出一個能自主搜尋、整合資訊的 research agent

這個基礎可以用在任何「需要的資訊一開始拿不到」的工作：競品分析、技術問題排查、投資研究、文獻回顧。

# 為什麼要做 research agent？

Research 很適合用 agent 來做，原因有兩個：

1. **資訊不在問題裡**。光看輸入的問題找不到答案，agent 得跟外部系統（搜尋引擎、資料庫、API）互動才能拿到需要的東西。
2. **路徑是邊探索邊長出來的**。你沒辦法事先決定流程。要先搜公司財報還是監管文件，要看 agent 對這家公司的商業模式發現了什麼。最好的策略是在調查過程中浮現的。

最簡單的 research agent 就是上網搜尋，然後整合結果。下面我們用 Claude Agent SDK 內建的網路搜尋 tool，幾行程式就做出來。

注意：你也可以看 [Claude Code 內建 tool 的完整清單](https://docs.claude.com/en/docs/claude-code/settings#tools-available-to-claude)

# 前置條件

開始之前，請先確認：

**需要具備的知識**

* Python 基礎：熟悉 async/await、函式和基本資料結構
* 對 agent 模式有基本認識：如果你剛接觸 agent，建議先讀 [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

**需要的工具**

* Python 3.11 以上
* Anthropic API key（[在這裡申請](https://console.anthropic.com)）

**建議具備：**
* 熟悉 Claude Agent SDK 的概念
* 了解 LLM 的 tool use 模式


## 環境設定

先安裝需要的套件：

```python
%%capture
%pip install -U claude-agent-sdk python-dotenv
```

注意：確認你的 .env 檔裡有：

```bash
ANTHROPIC_API_KEY=your_key_here
```

載入環境變數並設定 client：

```python
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-5-5"
```

## 建立你的第一個 research agent

先從最簡單的版本開始：一個能上網搜尋並整合結果的 research agent。用 Claude Agent SDK，只要幾行程式。

關鍵是 query() 函式，它會建立一次無狀態的 agent 互動。我們只給 Claude 一個 tool，WebSearch，讓它根據研究問題自己決定什麼時候用、怎麼用。

```python
from utils.agent_visualizer import (
    display_agent_response,
    print_activity,
)

from claude_agent_sdk import ClaudeAgentOptions, query

messages = []
async for msg in query(
    prompt="Research the latest trends in AI agents and give me a brief summary and relevant citiations links.",
    options=ClaudeAgentOptions(model=MODEL, allowed_tools=["WebSearch"], setting_sources=[]),
):
    print_activity(msg)
    messages.append(msg)
```

??? note "輸出"

    ```text
    🤖 Using: WebSearch()
    🤖 Using: WebSearch()
    🤖 Using: WebSearch()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    ```

```python
display_agent_response(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 這裡發生了什麼：

- `query()` 建立單輪的 agent 互動（沒有對話記憶）
- `allowed_tools=["WebSearch"]` 讓 Claude 可以直接上網搜尋，不用每次問你同不同意
- `setting_sources=[]` 讓這次執行自成一格：從 claude-agent-sdk 0.2 開始，SDK 預設會像互動式 CLI 一樣載入你的使用者和專案 Claude Code 設定（CLAUDE.md、MCP servers、hooks）
- agent 自己決定什麼時候搜、搜什麼、怎麼整合結果

**`utils.agent_visualizer` 提供的視覺化工具：**
- `print_activity()`：即時顯示 agent 的動作（tool call、thinking）
- `display_agent_response()`：把最終回應畫成有樣式的 HTML 卡片
- `visualize_conversation()`：產生整段對話的時間軸

就這樣！幾行程式就有一個能用的 research agent。它會搜尋相關資料、追著有用的線索往下查，最後給你一份附引用的整合摘要。

query() 函式建立的是無狀態的 agent 互動。每次呼叫都是獨立的，沒有對話記憶，也看不到前面查詢的 context。所以很適合只要快速拿到答案、不需要保留狀態的一次性研究。

**tool 權限怎麼運作：**

`allowed_tools=["WebSearch"]` 這個參數讓 Claude 不用問你就能搜尋，這是自主運作的關鍵：

- `Allowed tools`：Claude 可以自由使用（這裡是 WebSearch）
- `Other tools`：可以用，但使用前需要你核准
- `Read-only tools`：像 Read 這類 tool 預設永遠允許
- `Disallowed tools`：把 tool 加進 disallowed_tools，就會從 Claude 的 context 裡完全移除

**什麼時候適合用無狀態 query：**

- 不需要 context 的一次性研究問題
- 平行處理彼此獨立的研究任務
- 每次查詢都想從乾淨 context 開始

**什麼時候不適合：**

- 要在前面發現的基礎上繼續追問的多輪調查
- 根據初步結果反覆修正的研究
- 需要長時間保留 context 的複雜分析

用 visualize_conversation 這個 helper 來看看 agent 實際做了什麼：

```python
from utils.agent_visualizer import visualize_conversation

visualize_conversation(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 從原型到 production：三個關鍵改進

這個一行版的 research agent 能跑，但有限制。沒有記憶的單次查詢處理不了需要反覆迭代的研究（「先找 X，再根據找到的結果分析 Y」）。下面三個方向可以讓它更完整。

**1. 用 ClaudeSDKClient 加上對話記憶**：無狀態的查詢沒辦法接續之前的發現。如果你先問「最頂尖的 AI 新創有哪些？」再問「它們怎麼募資的？」，第二個查詢根本不知道「它們」是誰。用 `ClaudeSDKClient` 可以在多次查詢之間保留對話歷史。


**2. 用 system prompt 做專門化的行為**：不同研究領域有不同要求，財務分析和科技新聞摘要的嚴謹度不一樣。你可以用 system prompt 寫進研究標準、偏好的來源、引用格式或輸出結構。research 相關範例可以看我們的 [agent prompting guide](https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents/prompts)。

**3. 用 Read tool 做多模態研究**：真正的研究不只有文字。市場報告有圖表、技術文件有架構圖、競品分析需要比對截圖。啟用 `Read` tool，Claude 就能分析圖片、PDF 和其他視覺內容。

接下來把這三個改動實作到 research agent 上。

```python
from claude_agent_sdk import ClaudeSDKClient

# System prompt with citation requirements for research quality
RESEARCH_SYSTEM_PROMPT = """You are a research agent specialized in AI.

When providing research findings:
- Always include source URLs as citations
- Format citations as markdown links: [Source Title](URL)
- Group sources in a "Sources:" section at the end of your response"""

messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        cwd="research_agent",
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        allowed_tools=["WebSearch", "Read"],
        max_buffer_size=10 * 1024 * 1024,  # Increase to 10MB for image handling
        setting_sources=[],
    )
) as research_agent:
    # First query: Analyze the chart image
    await research_agent.query("Analyze the chart in research_agent/projects_claude.png")
    async for msg in research_agent.receive_response():
        print_activity(msg)
        messages.append(msg)

    # Second query: Use web search to validate/contextualize the chart findings
    await research_agent.query(
        "Based on the chart analysis, search for recent news or data that validates or provides context for these findings. Include source URLs."
    )
    async for msg in research_agent.receive_response():
        print_activity(msg)
        messages.append(msg)
```

??? note "輸出"

    ```text
    🤖 Using: Read()
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Glob()
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Read()
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: WebSearch()
    🤖 Using: WebSearch()
    🤖 Using: WebSearch()
    🤖 Using: WebSearch()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    ```

### 🔧 處理大型回應和 buffer 上限

處理圖片或大量資料時，你可能會碰到 buffer overflow 錯誤：

```
Fatal error in message reader: Failed to decode JSON: JSON message exceeded maximum buffer size of 1048576 bytes
```

**為什麼會這樣：**
- 預設的 `max_buffer_size` 是 1MB（1,048,576 bytes）
- 圖片在 message 裡是 base64 編碼，大小會明顯增加
- 圖表圖片在磁碟上約 200KB，base64 編碼後變成 270KB 以上，再加上 message 本身的開銷

**解法：**
處理圖片或大型 tool 輸出時，在 `ClaudeAgentOptions` 把 `max_buffer_size` 設大一點（例如 10MB）。

**實務建議：**
- 依用途設定 buffer 大小：一般多模態工作 10MB，處理大型文件就再調高
- 想想是不是真的需要傳整張圖，有時候文字描述或縮圖就夠了
- 留意 buffer 錯誤，看到就調整
- 在 system prompt 裡要求附上引用，讓研究結果可以驗證

## 這裡發生了什麼：

這個範例把三個改進合在一起：對話記憶、要求引用的 system prompt、多模態分析。

**關鍵元件：**

| 元件 | 用途 |
|-----------|---------|
| `ClaudeSDKClient` | 在多次查詢之間保留對話狀態 |
| `RESEARCH_SYSTEM_PROMPT` | 強制引用格式和來源 URL |
| `allowed_tools=["WebSearch", "Read"]` | 啟用網路搜尋和圖片、文件分析 |
| `max_buffer_size=10MB` | 處理 base64 編碼的圖片不會溢位 |

**執行流程：**

1. **第一次查詢**：用 `Read` tool 分析圖表圖片
2. **第一次回應 loop**：收集所有 message，直到 agent 完成
3. **第二次查詢**：上網搜尋，驗證並補充圖表的發現
4. **context 繼承**：第二次查詢記得第一次的圖表分析

**為什麼用 `ClaudeSDKClient` 而不是 `query()`：**

`async with ClaudeSDKClient()` 這個 context manager 會維持對話狀態，每次 `receive_response()` 都建立在前面的 context 上。`query()` 則是每次建立獨立、無狀態的 session。

```python
visualize_conversation(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 做成 production 用的模組

Jupyter notebook 很適合學習，但 production 系統需要可重用的模組。我們把 research agent 打包成 `research_agent/agent.py`，介面很簡單：

### 核心函式：

- `print_activity()`：即時顯示 agent 在做什麼（從共用工具匯入）
- `get_activity_text()`：取出 activity 文字，給自訂 handler 用，例如 logging 或 monitoring
- `send_query()`：research 查詢的主要入口，內建 activity 顯示

### 內建的最佳實務：

模組裡有 `RESEARCH_SYSTEM_PROMPT`，確保：
- 一定附上來源 URL 當引用
- 引用用 markdown 連結格式，渲染起來乾淨
- 最後有「Sources:」區塊整理所有參考來源

### 顯示控制：

`send_query()` 有個 `display_result` 參數（預設 `True`）：
- `display_result=True`：在 Jupyter notebook 裡畫出有樣式的 HTML 卡片
- `display_result=False`：只回傳文字結果，方便程式處理

這個 agent 現在可以用在任何 Python script 裡！

適合不需要對話 context 的獨立問題。

模組會自動處理：
- 執行過程中的 activity 顯示
- 新對話的 context 重置
- 最終回應的 HTML 樣式渲染

```python
from research_agent.agent import send_query

# The module handles activity display, context reset, and result visualization internally
result = await send_query("What is the Claude Code SDK? Only do one websearch and be concise")
```

??? note "輸出"

    ```text
    🤖 Using: WebSearch()
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

接下來測試多輪對話，沿用同一段對話。

多輪對話用起來很順，只要傳 `continue_conversation=True`：

```python
result1 = await send_query("What is Anthropic? Only do one websearch and be concise")
```

??? note "輸出"

    ```text
    🤖 Using: WebSearch()
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# Continue the conversation to dig deeper by setting continue_conversation=True
result2 = await send_query(
    "What are some of their products?",
    continue_conversation=True,
)
```

??? note "輸出"

    ```text
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 結論

### 你做了什麼

這份 cookbook 裡，你一步步做出三個越來越完整的 research agent：

- 無狀態 research agent：一行查詢，處理獨立的研究任務
- 有記憶的 stateful agent：多輪調查，在前面的發現上繼續往下查
- production 模組：可重用的 research 函式，能整合進應用程式

### 重點

**什麼時候用無狀態 query（query()）：**

- 獨立的研究問題
- 平行處理互不相關的任務
- 每次都需要乾淨 context

**什麼時候用 stateful agent（ClaudeSDKClient）：**

- 在前面發現的基礎上繼續的多輪調查
- 反覆修正的研究
- 需要長時間保留 context 的複雜分析

當資訊不在問題裡、最佳流程要邊探索邊找時，research agent 最能發揮：競品分析、技術問題排查、文獻回顧、調查報導都是這種模式。

### 下一步

這個基礎讓你準備好進入企業級的 multi-agent 系統。下一份 notebook 你會學到：

用一個協調用的 agent 來調度各種專門的 subagent
用 hooks 和自訂 command 做 governance
依不同對象（主管 vs. 技術團隊）調整輸出風格

下一篇：[01_The_chief_of_staff_agent.ipynb](01_The_chief_of_staff_agent.md)，從單一 agent 走向 multi-agent 協調。

## 重點整理

- research 適合 agent 的原因是資訊不在問題裡，而且路徑要邊查邊決定
- `query()` 每次都是無狀態的獨立互動，適合一次性或平行的研究任務
- `ClaudeSDKClient` 保留對話狀態，多輪追問才接得上前面的發現
- system prompt 用來固定研究標準，例如強制附上來源 URL 的引用格式
- 處理圖片這類大型內容時，要把 `max_buffer_size` 從預設 1MB 調高

## 練習

1. 把 `allowed_tools` 裡的 WebSearch 拿掉再跑一次，看看 agent 的回答有什麼不同。
2. 改 `RESEARCH_SYSTEM_PROMPT`，要求每個結論後面標註信心程度，再比較輸出。
3. 用 `ClaudeSDKClient` 連續問「最頂尖的 AI 新創有哪些？」和「它們怎麼募資的？」，再改用兩次獨立的 `query()`，比較第二個答案。
