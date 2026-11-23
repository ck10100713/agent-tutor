---
translated: true
source: tool_use/programmatic_tool_calling_ptc.ipynb
---

# Programmatic tool calling (PTC)

> 原文：[tool_use/programmatic_tool_calling_ptc.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/programmatic_tool_calling_ptc.ipynb)

讓 Claude 在 code execution 環境裡寫程式來呼叫 tool，降低 latency 和 token 用量。

## 這篇在做什麼

用一組團隊費用管理的 mock API，先用傳統 tool calling 跑出 baseline，再改用 PTC 讓 Claude 在 code execution 裡寫程式批次呼叫 tool、過濾資料。最後比較兩種做法的 token 和 API 呼叫數。

## 學完你會

- 分辨傳統 tool calling 和 PTC 的差別，以及各自的成本在哪
- 用 `allowed_callers` 讓 tool 可以被 code execution 呼叫，並處理 beta API、`container_id` 和 `caller` 欄位
- 判斷什麼情境適合用 PTC（大型資料、有順序相依、迴圈呼叫）

## 開跑前

- Python 3.11 以上
- Anthropic API key，放在 `.env`
- Anthropic Python SDK 0.72 以上

Programmatic Tool Calling（PTC）讓 Claude 在 Code Execution 環境裡寫程式來呼叫 tool，不用每次 tool 呼叫都繞回模型一趟。這大幅降低多次 tool 呼叫的端到端 latency，也能讓模型寫程式在資料進入 context window 之前就先濾掉無關內容（例如在又大又雜的檔案裡 grep 關鍵資訊），大幅減少 token 用量。

遇到你沒辦法直接修改的第三方 API 和 tool 時，PTC 可以讓 Claude 寫程式在 Code Execution 環境裡呼叫它們，減少 context 的使用。

這份 cookbook 用一個團隊費用管理的 mock API。這個 API 設計成需要多次呼叫，而且回傳很大的結果，正好用來說明 Programmatic Tool Calling 的好處。

## 這份 cookbook 做完，你可以：

- 了解一般 tool calling 和 programmatic tool calling（PTC）的差別
- 寫出利用 PTC 的 agent


## 前置條件

開始之前，請先確認：

**需要具備的知識**

- Python 基礎：熟悉 async/await、函式和基本資料結構
- 對 agent 模式和 tool calling 有基本認識

**需要的工具**

- Python 3.11 以上
- Anthropic API key
- Anthropic Python SDK >= 0.72


## 環境設定

先安裝需要的套件：

```python
# %pip install -r requirements.txt
```

注意：確認你的 .env 檔裡有：

`ANTHROPIC_API_KEY=your_key_here`

載入環境變數並設定 client。我們也載入一個 helper 工具，用來視覺化 Claude 的 message 回應。


```python
from dotenv import load_dotenv
from utils.visualize import visualize

load_dotenv()

MODEL = "claude-sonnet-5-5"

viz = visualize(auto_show=True)
```

## 了解這個第三方 API

[utils/team_expense_api.py](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/utils/team_expense_api.py) 裡定義了三個函式：`get_team_members`、`get_expenses` 和 `get_custom_budget`。`get_team_members` 能取得某部門所有員工的職位、層級和聯絡資訊。`get_expenses` 回傳某員工在特定季度的所有費用明細，每位員工可能有好幾百筆，每筆都帶有大量 metadata，包括收據 URL、核准鏈、商家資料等等。`get_custom_budget` 檢查特定員工是否有自訂的差旅預算例外（否則適用標準的每季 $5,000 上限）。

這個情境裡，我們要分析團隊費用，找出誰超出預算。傳統上，我們可能得手動拉每個人的費用報表、依類別加總、對照預算上限（還要查自訂預算的例外），再整理成報告。現在改請 Claude 來做，讓它用現有的 tool 取得團隊資料、抓回可能數百筆帶豐富 metadata 的費用明細，並判斷誰超出預算。

關鍵難點是：每位員工可能有 100 筆以上的費用明細要抓、解析和彙整，而且 `get_custom_budget` 只能在分析完費用、看出誰超過標準預算之後才能呼叫。這形成一條有順序相依的鏈，剛好適合示範 Programmatic Tool Calling 的好處。

我們把 tool 定義傳給 messages API，請 Claude 做分析。如果你不熟 tool use 在 Claude API 的運作方式，請先讀 [implementing tool use](https://docs.claude.com/en/docs/agents-and-tools/tool-use/implement-tool-use) 文件。

```python
import json

import anthropic
from utils.team_expense_api import get_custom_budget, get_expenses, get_team_members

client = anthropic.Anthropic()

# Tool definitions for the team expense API
tools = [
    {
        "name": "get_team_members",
        "description": 'Returns a list of team members for a given department. Each team member includes their ID, name, role, level (junior, mid, senior, staff, principal), and contact information. Use this to get a list of people whose expenses you want to analyze. Available departments are: engineering, sales, and marketing.\n\nRETURN FORMAT: Returns a JSON string containing an ARRAY of team member objects (not wrapped in an outer object). Parse with json.loads() to get a list. Example: [{"id": "ENG001", "name": "Alice", ...}, {"id": "ENG002", ...}]',
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {
                    "type": "string",
                    "description": "The department name. Case-insensitive.",
                }
            },
            "required": ["department"],
        },
        "input_examples": [
            {"department": "engineering"},
            {"department": "sales"},
            {"department": "marketing"},
        ],
    },
    {
        "name": "get_expenses",
        "description": "Returns all expense line items for a given employee in a specific quarter. Each expense includes extensive metadata: date, category, description, amount (in USD), currency, status (approved, pending, rejected), receipt URL, approval chain, merchant name and location, payment method, and project codes. An employee may have 20-50+ expense line items per quarter, and each line item contains substantial metadata for audit and compliance purposes. Categories include: 'travel' (flights, trains, rental cars, taxis, parking), 'lodging' (hotels, airbnb), 'meals', 'software', 'equipment', 'conference', 'office', and 'internet'. IMPORTANT: Only expenses with status='approved' should be counted toward budget limits.\n\nRETURN FORMAT: Returns a JSON string containing an ARRAY of expense objects (not wrapped in an outer object with an 'expenses' key). Parse with json.loads() to get a list directly. Example: [{\"expense_id\": \"ENG001_Q3_001\", \"amount\": 1250.50, \"category\": \"travel\", ...}, {...}]",
        "input_schema": {
            "type": "object",
            "properties": {
                "employee_id": {
                    "type": "string",
                    "description": "The unique employee identifier",
                },
                "quarter": {
                    "type": "string",
                    "description": "Quarter identifier: 'Q1', 'Q2', 'Q3', or 'Q4'",
                },
            },
            "required": ["employee_id", "quarter"],
        },
        "input_examples": [
            {"employee_id": "ENG001", "quarter": "Q3"},
            {"employee_id": "SAL002", "quarter": "Q1"},
            {"employee_id": "MKT001", "quarter": "Q4"},
        ],
    },
    {
        "name": "get_custom_budget",
        "description": 'Get the custom quarterly travel budget for a specific employee. Most employees have a standard $5,000 quarterly travel budget. However, some employees have custom budget exceptions based on their role requirements. This function checks if a specific employee has a custom budget assigned.\n\nRETURN FORMAT: Returns a JSON string containing a SINGLE OBJECT (not an array). Parse with json.loads() to get a dict. Example: {"user_id": "ENG001", "has_custom_budget": false, "travel_budget": 5000, "reason": "Standard", "currency": "USD"}',
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "string",
                    "description": "The unique employee identifier",
                }
            },
            "required": ["user_id"],
        },
        "input_examples": [
            {"user_id": "ENG001"},
            {"user_id": "SAL002"},
            {"user_id": "MKT001"},
        ],
    },
]

tool_functions = {
    "get_team_members": get_team_members,
    "get_expenses": get_expenses,
    "get_custom_budget": get_custom_budget,
}
```

## 傳統 Tool Calling（Baseline）

第一個範例用傳統 tool calling 建立 baseline。

我們用初始 query 呼叫 `messages.create` API。當模型以 `tool_use` 原因停下時，我們照它的要求執行 tool，把 tool 的輸出加進 messages，再呼叫模型一次。

```python
import time

from anthropic.types import TextBlock, ToolUseBlock
from anthropic.types.beta import (
    BetaMessageParam as MessageParam,
)
from anthropic.types.beta import (
    BetaTextBlock,
    BetaToolUseBlock,
)

messages: list[MessageParam] = []


def run_agent_without_ptc(user_message):
    """Run agent using traditional tool calling"""
    messages.append({"role": "user", "content": user_message})
    total_tokens = 0
    start_time = time.time()
    api_counter = 0

    while True:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            tools=tools,
            messages=messages,
            betas=["advanced-tool-use-2025-11-20"],
        )

        api_counter += 1

        # Track token usage
        total_tokens += response.usage.input_tokens + response.usage.output_tokens
        viz.capture(response)
        if response.stop_reason == "end_turn":
            # Extract the first text block from the response
            final_response = next(
                (
                    block.text
                    for block in response.content
                    if isinstance(block, (BetaTextBlock, TextBlock))
                ),
                None,
            )
            elapsed_time = time.time() - start_time
            return final_response, messages, total_tokens, elapsed_time, api_counter

        # Process tool calls
        if response.stop_reason == "tool_use":
            # First, add the assistant's response to messages
            messages.append({"role": "assistant", "content": response.content})

            # Collect all tool results
            tool_results = []

            for block in response.content:
                if isinstance(block, (BetaToolUseBlock, ToolUseBlock)):
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    result = tool_functions[tool_name](**tool_input)

                    content = str(result)

                    tool_result = {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": content,
                    }
                    tool_results.append(tool_result)

            # Append all tool results at once after collecting them
            messages.append({"role": "user", "content": tool_results})

        else:
            print(f"\nUnexpected stop reason: {response.stop_reason}")
            elapsed_time = time.time() - start_time

            final_response = next(
                (
                    block.text
                    for block in response.content
                    if isinstance(block, (BetaTextBlock, TextBlock))
                ),
                f"Stopped with reason: {response.stop_reason}",
            )
            return final_response, messages, total_tokens, elapsed_time, api_counter
```

我們給模型的初始 query 帶了一些引導的指示。為了簡潔，我們請模型每個 tool 只呼叫一次。更深入的調查中，模型可能會想查多個系統或時間範圍。

```python
query = "Which engineering team members exceeded their Q3 travel budget? Standard quarterly travel budget is $5,000. However, some employees have custom budget limits. For anyone who exceeded the $5,000 standard budget, check if they have a custom budget exception. If they do, use that custom limit instead to determine if they truly exceeded their budget."
```

```python
# Run the agent
result, conversation, total_tokens, elapsed_time, api_count_without_ptc = run_agent_without_ptc(
    query
)

print(f"Result: {result}")
print(f"API calls made: {api_count_without_ptc}")
print(f"Total tokens used: {total_tokens:,}")
print(f"Total time taken: {elapsed_time:.2f}s")
```

??? note "輸出"

    ```text
    ╭────────────────────────────────────────────── Claude API Response ──────────────────────────────────────────────╮
    │ Claude Message (assistant) │ tokens: 1,859 in • 85 out • 1,944 total                                            │
    │ ├── Model: claude-sonnet-4-6                                                                           │
    │ ├── Stop Reason: tool_use                                                                                       │
    │ └── Content (2 blocks)                                                                                          │
    │     ├── Block 1                                                                                                 │
    │     │   └── Text                                                                                                │
    │     │       └── I'll help you identify which engineering team members exceeded their Q3 travel budget. Let me   │
    │     │           start by getting the list of engineering team members.                                          │
    │     └── Block 2                                                                                                 │
    │         └── Tool Use: get_team_members                                                                          │
    │             ├── ID: toolu_01LuouuJYp1sSvBe2Du7EG7v                                                              │
    │             ├── Caller: model (direct)                                                                          │
    │             └── Input:                                                                                          │
    │                 └── {                                                                                           │
    │                       "department": "engineering"                                                               │
    │                     }                                                                                           │
    ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
    ```

    ```text
    ╭────────────────────────────────────────────── Claude API Response ──────────────────────────────────────────────╮
    │ Claude Message (assistant) │ tokens: 51,744 in • 290 out • 52,034 total                                         │
    │ ├── Model: claude-sonnet-4-6                                                                           │
    │ ├── Stop Reason: tool_use                                                                                       │
    │ └── Content (7 blocks)                                                                                          │
    │     ├── Block 1                                                                                                 │
    │     │   └── Text                                                                                                │
    │     │       └── Now let me calculate the approved travel expenses for each engineer and identify who exceeded   │
    │     │           $5,000:                                                                                         │
    │     ├── Block 2                                                                                                 │
    │     │   └── Tool Use: get_custom_budget                                                                         │
    │     │       ├── ID: toolu_013oegKwjvToLwEW1daDD8av                                                              │
    │     │       ├── Caller: model (direct)                                                                          │
    │     │       └── Input:                                                                                          │
    │     │           └── {                                                                                           │
    │     │                 "user_id": "ENG001"                                                                       │
    │     │               }                                                                                           │
    │     ├── Block 3                                                                                                 │
    │     │   └── Tool Use: get_custom_budget                                                                         │
    │     │       ├── ID: toolu_0162W4Ycr9FcVVED65exjAj4                                                              │
    │     │       ├── Caller: model (direct)                                                                          │
    │     │       └── Input:                                                                                          │
    │     │           └── {                                                                                           │
    │     │                 "user_id": "ENG003"                                                                       │
    │     │               }                                                                                           │
    │     ├── Block 4                                                                                                 │
    │     │   └── Tool Use: get_custom_budget                                                                         │
    │     │       ├── ID: toolu_01JcTX5rnwFxA99Am33gXmh6                                                              │
    │     │       ├── Caller: model (direct)                                                                          │
    │     │       └── Input:                                                                                          │
    │     │           └── {                                                                                           │
    │     │                 "user_id": "ENG005"                                                                       │
    │     │               }                                                                                           │
    │     ├── Block 5                                                                                                 │
    │     │   └── Tool Use: get_custom_budget                                                                         │
    │     │       ├── ID: toolu_01QwNJz1wGeV5VeZoCd4ByER                                                              │
    │     │       ├── Caller: model (direct)                                                                          │
    │     │       └── Input:                                                                                          │
    │     │           └── {                                                                                           │
    │     │                 "user_id": "ENG006"                                                                       │
    ... (省略 18 行)
    ```

    ```text
    ╭────────────────────────────────────────────── Claude API Response ──────────────────────────────────────────────╮
    │ Claude Message (assistant) │ tokens: 52,533 in • 992 out • 53,525 total                                         │
    │ ├── Model: claude-sonnet-4-6                                                                           │
    │ ├── Stop Reason: end_turn                                                                                       │
    │ └── Content (1 blocks)                                                                                          │
    │     └── Block 1                                                                                                 │
    │         └── Text                                                                                                │
    │             └── Now let me analyze the data. I'll calculate the approved travel expenses for each engineer:     │
    │                                                                                                                 │
    │                 **Analysis of Q3 Travel Expenses:**                                                             │
    │                                                                                                                 │
    │                 **ENG001 - Alice Chen (Senior Software Engineer)**                                              │
    │                 - Approved travel expenses: $1,161.04 + $18.63 + $13.21 + $36.55 + $1,440.42 + $166.46 + $48.43 │
    │                 + $1,124.56 + $1,245.90 + $1,498.42 = **$6,753.62**                                             │
    │                 - Budget: $5,000 (Standard)                                                                     │
    │                 - **EXCEEDED by $1,753.62** ❌                                                                  │
    │                                                                                                                 │
    │                 **ENG002 - Bob Martinez (Staff Engineer)**                                                      │
    │                 - Approved travel expenses: $180.16 + $10.07 + $20.76 = **$210.99**                             │
    │                 - Budget: $5,000 (Standard)                                                                     │
    │                 - Under budget ✓                                                                                │
    │                                                                                                                 │
    │                 **ENG003 - Carol White (Software Engineer)**                                                    │
    │                 - Approved travel expenses: $24.75 + $424.74 + $1,397.17 + $1,026.12 + $1,288.36 + $1,128.90 +  │
    │                 $1,148.42 + $45.03 = **$6,483.49**                                                              │
    │                 - Budget: $5,000 (Standard)                                                                     │
    │                 - **EXCEEDED by $1,483.49** ❌                                                                  │
    │                                                                                                                 │
    │                 **ENG004 - David Kim (Principal Engineer)**                                                     │
    │                 - Approved travel expenses: $21.68 + $46.12 + $1,008.68 + $46.43 = **$1,122.91**                │
    │                 - Budget: $5,000 (Standard)                                                                     │
    │                 - Under budget ✓                                                                                │
    │                                                                                                                 │
    │                 **ENG005 - Emma Johnson (Junior Software Engineer)                                              │
    │                 ... (truncated)                                                                                 │
    ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
    ```

    ```text
    Result: Now let me analyze the data. I'll calculate the approved travel expenses for each engineer:

    **Analysis of Q3 Travel Expenses:**

    **ENG001 - Alice Chen (Senior Software Engineer)**
    - Approved travel expenses: $1,161.04 + $18.63 + $13.21 + $36.55 + $1,440.42 + $166.46 + $48.43 + $1,124.56 + $1,245.90 + $1,498.42 = **$6,753.62**
    - Budget: $5,000 (Standard)
    - **EXCEEDED by $1,753.62** ❌

    **ENG002 - Bob Martinez (Staff Engineer)**
    - Approved travel expenses: $180.16 + $10.07 + $20.76 = **$210.99**
    - Budget: $5,000 (Standard)
    - Under budget ✓

    **ENG003 - Carol White (Software Engineer)**
    - Approved travel expenses: $24.75 + $424.74 + $1,397.17 + $1,026.12 + $1,288.36 + $1,128.90 + $1,148.42 + $45.03 = **$6,483.49**
    - Budget: $5,000 (Standard)
    - **EXCEEDED by $1,483.49** ❌

    **ENG004 - David Kim (Principal Engineer)**
    - Approved travel expenses: $21.68 + $46.12 + $1,008.68 + $46.43 = **$1,122.91**
    - Budget: $5,000 (Standard)
    - Under budget ✓

    **ENG005 - Emma Johnson (Junior Software Engineer)**
    - Approved travel expenses: $450.00 + $1,376.36 + $1,164.49 + $151.55 + $1,253.88 = **$4,396.28**
    - Budget: $5,000 (Standard)
    - Under budget ✓

    **ENG006 - Frank Liu (Senior Software Engineer)**
    - Approved travel expenses: $596.48 + $1,018.71 + $1,193.82 + $159.08 + $1,112.11 + $24.97 = **$4,105.17**
    - Budget: $5,000 (Standard)
    - Under budget ✓

    **ENG007 - Grace Taylor (Software Engineer)**
    - Approved travel expenses: $1,476.63 + $39.85 + $1,220.19 + $189.16 + $1,032.52 + $1,331.00 = **$5,289.35**
    - Budget: $5,000 (Standard)
    - **EXCEEDED by $289.35** ❌

    **ENG008 - Henry Park (Staff Engineer)**
    ... (省略 29 行)
    ```

很好！Claude 成功用現有的 tool 找出哪些團隊成員超出差旅預算。不過我們也看到完成這件事用了很多 token。Claude 得讓所有費用明細都經過它的 context window（每位員工可能超過 100 筆，每筆都帶有大量 metadata，包括收據 URL、核准鏈、商家資訊等等），才能解析、依類別加總並對照預算上限。

此外，傳統 tool calling 需要多次循序的往返：先抓團隊成員，再抓每個人的費用，再對超過標準上限的人查自訂預算。每次往返都增加 latency，而且費用紀錄裡所有豐富的 metadata 都會流經模型的 context。

看看能不能用 PTC 提升表現，讓 Claude 寫程式在 code execution 環境裡處理這些大型資料集。

要對 tool 啟用 PTC，必須先在任何要讓 code execution 呼叫的 tool 上加 `allowed_callers` 欄位。

**重點**

- 沒有 allowed_callers 的 tool，預設只能由模型呼叫
- tool 可以同時讓模型和 code execution 呼叫，只要列多個 caller：`["direct", "code_execution_20250825"]`
- 只讓可以安全地被程式、重複執行的 tool 加入 PTC


```python
import copy

ptc_tools = copy.deepcopy(tools)
for tool in ptc_tools:
    tool["allowed_callers"] = ["code_execution_20250825"]  # type: ignore


# Add the code execution tool
ptc_tools.append(
    {
        "type": "code_execution_20250825",  # type: ignore
        "name": "code_execution",
    }
)
```

tool 定義更新成允許 programmatic tool calling 後，就能用 PTC 跑我們的 agent。為此我們得對函式做幾個修改。必須使用 `beta` messages API。

1. 我們在 betas 加了 `"advanced-tool-use-2025-11-20"`。
2. 如果有定義 `container_id`，就把它帶進 request。這只有像我們這種 stateful 的 workflow 才需要，單輪的 workflow 不用。
3. 我們可以檢查 `tool_use` block 裡的 `caller` 欄位，判斷這次 tool 呼叫是模型直接呼叫還是程式呼叫的。

注意不管哪種情況，我們都是透過 Claude API 送回 tool 結果，但只有 `direct` 的呼叫會被模型「看到」。`code_execution_20250825` 類型的結果只會被 code execution container 看到。

```python
messages = []


def run_agent_with_ptc(user_message):
    """Run agent using PTC"""
    messages.append({"role": "user", "content": user_message})
    total_tokens = 0
    start_time = time.time()
    container_id = None
    api_counter = 0

    while True:
        # Build request with PTC beta headers
        request_params = {
            "model": MODEL,
            "max_tokens": 4000,
            "tools": ptc_tools,
            "messages": messages,
        }

        response = client.beta.messages.create(
            **request_params,
            betas=[
                "advanced-tool-use-2025-11-20",
            ],
            extra_body={"container": container_id} if container_id else None,
        )
        viz.capture(response)
        api_counter += 1

        # Track container for stateful execution
        if hasattr(response, "container") and response.container:
            container_id = response.container.id
            print(f"\n[Container] ID: {container_id}")
            if hasattr(response.container, "expires_at"):
                # If the container has expired, we would need to restart our workflow. In our case, it completes before expiration.
                print(f"[Container] Expires at: {response.container.expires_at}")

        # Track token usage
        total_tokens += response.usage.input_tokens + response.usage.output_tokens

        if response.stop_reason == "end_turn":
            # Extract the first text block from the response
            final_response = next(
                (block.text for block in response.content if isinstance(block, BetaTextBlock)),
                None,
            )
            elapsed_time = time.time() - start_time
            return final_response, messages, total_tokens, elapsed_time, api_counter

        # As before, we process tool calls
        if response.stop_reason == "tool_use":
            # First, add the assistant's response to messages
            messages.append({"role": "assistant", "content": response.content})

            # Collect all tool results
            tool_results = []

            for block in response.content:
                if isinstance(block, BetaToolUseBlock):
                    tool_name = block.name
                    tool_input = block.input
                    tool_use_id = block.id

                    # We can use caller type to understand how the tool was invoked
                    caller_type = block.caller["type"]  # type: ignore

                    if caller_type == "code_execution_20250825":
                        print(f"[PTC] Tool called from code execution environment: {tool_name}")

                    elif caller_type == "direct":
                        print(f"[Direct] Tool called by model: {tool_name}")

                    result = tool_functions[tool_name](**tool_input)

                    # Format result as proper content for the API
                    if isinstance(result, list) and result and isinstance(result[0], str):
                        content = "\n".join(result)
                    elif isinstance(result, (dict, list)):
                        content = json.dumps(result)
                    else:
                        content = str(result)

                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": content,
                        }
                    )

            messages.append({"role": "user", "content": tool_results})

        else:
            print(f"\nUnexpected stop reason: {response.stop_reason}")
            elapsed_time = time.time() - start_time

            final_response = next(
                (block.text for block in response.content if isinstance(block, BetaTextBlock)),
                f"Stopped with reason: {response.stop_reason}",
            )
            return final_response, messages, total_tokens, elapsed_time, api_counter
```

```python
# Run the PTC agent
result_ptc, conversation_ptc, total_tokens_ptc, elapsed_time_ptc, api_count_with_ptc = (
    run_agent_with_ptc(query)
)
```

??? note "輸出"

    ```text

    [Container] ID: container_011CVSAwq5J4vNPi3A4P2Rwh
    [Container] Expires at: 2025-11-24 05:41:17.467494+00:00
    [PTC] Tool called from code execution environment: get_team_members
    ```

    ```text

    [Container] ID: container_011CVSAwq5J4vNPi3A4P2Rwh
    [Container] Expires at: 2025-11-24 05:41:19.266670+00:00
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    [PTC] Tool called from code execution environment: get_expenses
    ```

    ```text

    [Container] ID: container_011CVSAwq5J4vNPi3A4P2Rwh
    [Container] Expires at: 2025-11-24 05:41:33.430636+00:00
    [PTC] Tool called from code execution environment: get_custom_budget
    [PTC] Tool called from code execution environment: get_custom_budget
    [PTC] Tool called from code execution environment: get_custom_budget
    ```

    ```text
    ╭────────────────────────────────────────────── Claude API Response ──────────────────────────────────────────────╮
    │ Claude Message (assistant) │ tokens: 5,611 in • 205 out • 5,816 total                                           │
    │ ├── Model: claude-sonnet-4-6                                                                           │
    │ ├── Stop Reason: end_turn                                                                                       │
    │ └── Content (2 blocks)                                                                                          │
    │     ├── Block 1                                                                                                 │
    │     │   └── Code Execution Result: Success (exit 0)                                                             │
    │     │       └── stdout:                                                                                         │
    │     │           └── ENGINEERING TEAM MEMBERS WHO EXCEEDED THEIR Q3 TRAVEL BUDGET:                               │
    │     │               ================================================================================            │
    │     │                                                                                                           │
    │     │               Alice Chen (ENG001)                                                                         │
    │     │                 Budget Limit: $5,000.00 (Standard)                                                        │
    │     │                 Travel Spending: $9,177.88                                                                │
    │     │                 Exceeded By: $4,177.88                                                                    │
    │     │                                                                                                           │
    │     │               Carol White (ENG003)                                                                        │
    │     │                 Budget Limit: $5,000.00 (Standard)                                                        │
    │     │                 Travel Spending: $6,483.49                                                                │
    │     │                 Exceeded By: $1,483.49                                                                    │
    │     │                                                                                                           │
    │     │               Grace Taylor (ENG007)                                                                       │
    │     │                 Budget Limit: $5,000.00 (Standard)                                                        │
    │     │                 Travel Spending: $5,289.35                                                                │
    │     │                 Exceeded By: $289.35                                                                      │
    │     │                                                                                                           │
    │     └── Block 2                                                                                                 │
    │         └── Text                                                                                                │
    │             └── ## Summary                                                                                      │
    │                                                                                                                 │
    │                 **Three engineering team members exceeded their Q3 travel budget:**                             │
    │                                                                                                                 │
    │                 1. **Alice Chen (ENG001)**                                                                      │
    │                    - Budget: $5,000 (Standard)                                                                  │
    │                    - Spent: $9,177.88                                                                           │
    │                    - Over budget by: **$4,177.88**                                                              │
    │                                                                                                                 │
    │                 2. **Carol White (ENG003)**                                                                     │
    │                    - Budget: $5,000 (Standard)                                                                  │
    │                    - Spent: $6,483.49                                                                           │
    ... (省略 10 行)
    ```

```python
print(f"\n{'=' * 60}")
print(f"Result: {result_ptc}")
print(f"\n{'=' * 60}")
print("Performance Metrics:")
print(
    f"  Total API calls to Claude: {len([m for m in conversation_ptc if m['role'] == 'assistant'])}"
)
print(f"  Total tokens used: {total_tokens_ptc:,}")
print(f"  Total time taken: {elapsed_time_ptc:.2f}s")
```

??? note "輸出"

    ```text

    ============================================================
    Result: ## Summary

    **Three engineering team members exceeded their Q3 travel budget:**

    1. **Alice Chen (ENG001)**
       - Budget: $5,000 (Standard)
       - Spent: $9,177.88
       - Over budget by: **$4,177.88**

    2. **Carol White (ENG003)**
       - Budget: $5,000 (Standard)
       - Spent: $6,483.49
       - Over budget by: **$1,483.49**

    3. **Grace Taylor (ENG007)**
       - Budget: $5,000 (Standard)
       - Spent: $5,289.35
       - Over budget by: **$289.35**

    All three employees are on the standard $5,000 quarterly travel budget with no custom exceptions, so they all genuinely exceeded their allocated travel budget for Q3.

    ============================================================
    Performance Metrics:
      Total API calls to Claude: 3
      Total tokens used: 15,919
      Total time taken: 34.88s
    ```

## 效能比較

比較傳統 tool calling 和 PTC 的效能：

**關於 API 呼叫次數的說明：** 你可能會注意到這個範例裡 PTC 需要更多次 API 呼叫。這是因為 PTC 寫出的程式更結構化、循序，遵循最佳實務，例如把抓費用的步驟和檢查預算的步驟分開。傳統 tool calling 有時能在單一回合把操作批次處理，代價是所有原始資料都得經過模型的 context。PTC 在 token 效率上的收益遠大於往返次數的少量增加，特別是處理大型、metadata 豐富的資料集時。

```python
import pandas as pd

# Create comparison dataframe
comparison_data = {
    "Metric": [
        "API Calls",
        "Total Tokens",
        "Elapsed Time (s)",
        "Token Reduction",
        "Time Reduction",
    ],
    "Traditional": [
        api_count_without_ptc,
        f"{total_tokens:,}",
        f"{elapsed_time:.2f}",
        "-",
        "-",
    ],
    "PTC": [
        api_count_with_ptc,
        f"{total_tokens_ptc:,}",
        f"{elapsed_time_ptc:.2f}",
        f"{((total_tokens - total_tokens_ptc) / total_tokens * 100):.1f}%",
        f"{((elapsed_time - elapsed_time_ptc) / elapsed_time * 100):.1f}%",
    ],
}

df = pd.DataFrame(comparison_data)
print(df.to_string(index=False))
```

??? note "輸出"

    ```text
              Metric Traditional    PTC
           API Calls           4      4
        Total Tokens     110,473 15,919
    Elapsed Time (s)       35.38  34.88
     Token Reduction           -  85.6%
      Time Reduction           -   1.4%
    ```

## 重點

這個例子裡，PTC 靠三個核心能力顯著改善了效能：

### 1. 解析大量資料時保護 context
這是我們的 workflow 展示的主要好處。Claude 寫程式在 code execution 環境裡抓取並處理數百筆費用明細。透過程式處理這些資料，Claude 解析 JSON、依狀態過濾、依類別加總金額、對照預算上限，全程不用把原始費用資料和 metadata 送進模型的 context window。結果是 **token 用量顯著下降**。

### 2. 最佳化順序相依
這個 API 有順序相依：`get_custom_budget(user_id)` 只能在分析完費用、找出誰超過標準 $5,000 預算之後才能呼叫。傳統 tool calling 需要多次往返：抓團隊成員、抓每個人的費用、找出超預算的人、再一個個查他們的自訂預算。用 PTC，Claude 寫程式在 code execution 環境裡編排整個流程，在迴圈裡做 programmatic tool call，並在多次呼叫間維持狀態。這把原本很多次循序的 API 往返，變成較少次、編排更聰明的呼叫。

### 3. 在 code execution 裡做運算邏輯
不用要求模型在腦中追蹤並加總幾十筆帶複雜 metadata 的費用，Claude 把算術和彙整邏輯交給 Python 程式。這降低模型的負擔、確保計算精確，並讓無關的 metadata（像收據 URL 和商家地點）完全不進模型的 context。

---

## 什麼時候用 PTC

PTC 在這些情況最有幫助：

- **處理大型、metadata 豐富的資料集**，需要過濾、解析或彙整（像我們的費用分析，有收據 URL、核准鏈、商家資料等等）
- **有順序相依**，某個 tool 呼叫取決於前面呼叫的結果（像只對超過標準上限的員工檢查自訂預算）
- **需要多次 tool 呼叫**，循序或在迴圈裡對類似的 entity 重複做（對每個團隊成員檢查費用和預算）
- **運算邏輯**可以減少需要流經模型 context 的量
- **tool 是安全的**，可以在沒有人監督下由程式重複執行

## 結論

團隊費用分析展示了 PTC 的強項：**處理大型、metadata 豐富的資料集時，大幅降低 context 消耗**，以及**最佳化有順序相依的 workflow**。讓 Claude 寫程式來編排 tool 呼叫並以程式處理結果，我們在維持準確度和洞察品質的同時，省下大量 token。

PTC 特別適合這些 workflow：大量處理帶豐富 metadata 的資料、有相依的重複 tool 呼叫，或是原始 tool 輸出會污染模型 context 的情境。

## 下一步

試著把這個模式套到你自己的用例：
- 帶有順序查詢的財務資料分析和報告
- 取決於初步掃描結果的多 entity 健康檢查
- 帶 metadata 的大型檔案處理（CSV、JSON、XML 解析）
- 資料庫查詢結果彙整，加上後續查詢
- 依初步結果加上條件邏輯的批次 API 操作

## 重點整理

- 傳統 tool calling 每次呼叫都繞回模型，原始資料全進 context，成本高
- PTC 讓 Claude 寫程式在 code execution 裡呼叫 tool，只把處理後的結果回給模型
- 要用 `allowed_callers` 明確開放 tool，並使用 beta API；`caller` 欄位區分直接呼叫和程式呼叫
- PTC 的 API 呼叫次數可能比較多，但 token 節省通常更重要
- 最適合大資料、有順序相依、迴圈呼叫的情境，而且 tool 必須能安全地被程式重複執行

## 練習

1. 把某個 tool 的 `allowed_callers` 改回只有 `["direct"]`，觀察該 tool 的呼叫行為怎麼變。
2. 改初始 query，不要限制「每個 tool 只呼叫一次」，比較 PTC 和傳統做法的 token 用量差異。
3. 仿照 `get_custom_budget` 再加一個新 tool（例如查員工所屬部門的核准上限），開放給 code execution，看 Claude 寫的程式怎麼用它。
