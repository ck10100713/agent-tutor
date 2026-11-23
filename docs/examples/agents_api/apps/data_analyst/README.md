---
translated: true
source: examples/agents_api/apps/data_analyst/README.md
---

# 用 Agents API 做資料分析 agent

> 原文：[examples/agents_api/apps/data_analyst/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/README.md)

用唯讀 SQL、商業 context 和存下來的分析師修正，調查資料倉儲裡的問題。

## 這篇在做什麼
這個範例做了一個資料分析 agent，用 Agents API 的 session 串起多次查詢。它會找出相關的資料表、查指標定義和過去的分析、執行唯讀 SQL，並把你明確要求記住的修正存起來，下次調查時使用。

## 學完你會
- 設計四個職責明確的 tool（`search_tables`、`search_context`、`query_warehouse`、`save_memory`），讓 agent 先查 schema 再寫 SQL
- 用不帶 sandbox 的 Agents API session 開始調查，處理 `agent.session.requires_action` 並派發 function call
- 用 `conversation_id` 接續同一場調查，並把修正存成應用程式自己擁有的跨 session 記憶

## 開跑前
- Python 3.14+ 和 `uv`
- OpenAI API key
- 一個相容 PostgreSQL 的資料倉儲的唯讀存取權限（`WAREHOUSE_URL`）

不需要執行 sandbox。

問你自己的業務資料問題。Agent 會找出相關的資料倉儲資料表，檢查指標定義和過去的分析，執行唯讀 SQL，並記住有用的修正，供之後的調查使用。

## 為什麼用 Agents API？

一次有用的調查通常需要好幾個查詢和追問。
Agents API 把這些工作放在同一個 session 裡，並讓模型呼叫你應用程式的
tool。資料庫存取由你的應用程式負責，你決定分析師可以看到哪些
context 和存下來的修正。

這個範例參考了 [OpenAI 內部的資料 agent](https://openai.com/index/inside-our-in-house-data-agent/)：
分析要建立在真實的 schema 上，提供商業 context，公開 SQL，
並重用團隊明確存下來的修正。

![Data analyst workflow: inspect warehouse schemas, verify read-only SQL, explain findings, and save analyst corrections for future questions.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_api/apps/data_analyst/assets/workflow.svg)

## 你需要什麼

- Python 3.14+ 和 `uv`。
- 一把 OpenAI API key。
- 對相容 PostgreSQL 的資料倉儲有唯讀存取權限。

不需要執行 sandbox。Agent 用的是沒有 environment 的 Agents API session，每一個倉儲查詢都由你的應用程式控制。

## 連接你的資料倉儲

在 repository 根目錄：

```bash
cp examples/agents_api/apps/data_analyst/.env.example examples/agents_api/apps/data_analyst/.env
```

把你的 OpenAI API key 和唯讀的 `WAREHOUSE_URL` 加到 `examples/agents_api/apps/data_analyst/.env`。應用程式會自動載入這個檔案。

也可以選擇取消 `.env` 裡 `DATA_AGENT_CONTEXT` 的註解，並把範例 context 檔改成你團隊的資料表說明、指標定義、過去的查詢和公司文件。存下來的分析師修正放在 `examples/agents_api/apps/data_analyst/memories.json`。

## 執行資料 agent

```bash
uv run examples/agents_api/apps/data_analyst/main.py
```

打開 [http://127.0.0.1:8000](http://127.0.0.1:8000) 然後提問：

```text
Why did paid conversions drop last week?
```

接著繼續同一場調查：

```text
Only include enterprise customers.
```

或是從終端機問單一問題：

```bash
uv run examples/agents_api/apps/data_analyst/main.py --prompt \
  "Why did paid conversions drop last week?"
```

## 運作方式

Agent 有四個專職的 tool：

- `search_tables` 找出相關的資料表，並讀取它們實際的欄位。
- `search_context` 取得指標定義、過去的查詢、文件和存下來的修正。
- `query_warehouse` 執行一個唯讀查詢，最多回傳 100 筆資料。
- `save_memory` 把明確要求保存的修正存起來，供之後使用。

`save_memory` tool 是用 `tool_search` 按需探索的。Programmatic tool calling 讓 agent 在回應前，可以結合 metadata、商業 context、存下來的修正，以及多個驗證過的查詢。

請使用唯讀的資料倉儲角色。應用程式也會用唯讀模式啟動 PostgreSQL 連線、套用查詢 timeout，並顯示每一個執行過的查詢。附的瀏覽器介面代表單一本機分析師。在多使用者的應用程式裡，分析師身分要從你的驗證層取得，不要用 request body 或 query parameter。

## 跟著看實作

下面的片段說明 [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/agent.py) 和 [warehouse.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/warehouse.py)。
上面的應用程式包含 tool 派發迴圈、錯誤處理和清理。

### 1. 寫 SQL 之前先探索資料表

先載入範例的環境，再建立 warehouse adapter。探索會
回傳實際的資料表欄位，加上你在 context 檔案裡提供的
負責人和資料新鮮度備註。

```python
from dotenv import load_dotenv
from examples.agents_api.apps.data_analyst.warehouse import Warehouse

load_dotenv("examples/agents_api/apps/data_analyst/.env")
warehouse = Warehouse()
tables = warehouse.search_tables({"query": "paid conversion"})
for table in tables["tables"]:
    print(table["columns"])
```

### 2. 加入定義和可信任的查詢

用 `DATA_AGENT_CONTEXT` 指向一個 JSON 檔，裡面有 `tables`、`metrics`、
`documents` 和 `query_history`。例如，一筆 metric 記錄可以同時定義
計算方式和你團隊預期的過濾條件：

```json
{
  "metrics": [{
    "name": "paid_conversion_rate",
    "definition": "Paid subscriptions divided by eligible signups.",
    "filters": [
      "Exclude employees and test accounts.",
      "Exclude the current incomplete day."
    ]
  }],
  "documents": [{
    "title": "Checkout tracking migration",
    "text": "Mobile checkout tracking changed on August 18."
  }]
}
```

請把這些示意用的定義換成你團隊審核過的定義。
`query_history` 的記錄是把 `description` 和一個審核過的 `sql` 查詢配成一對，讓
agent 可以重用既有的 join。過去的全時段查詢，還是需要明確的日期範圍，才能回答每週的問題。

### 3. 註冊四個 tool

[agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/agent.py) 為每個 tool 定義 schema，然後啟用 tool search 和
programmatic tool calling。寫入記憶的 tool 延後到 agent 需要時才載入：

```python
from examples.agents_api.apps.data_analyst.agent import define_tool

tools = [
    define_tool("search_tables", "Find tables and inspect schemas.",
                {"query": {"type": "string"}}),
    define_tool("search_context", "Find definitions, previous queries, and memories.",
                {"query": {"type": "string"}}),
    define_tool("query_warehouse", "Run read-only SQL.",
                {"sql": {"type": "string"}}),
    define_tool("save_memory", "Save a correction only when explicitly requested.",
                {"note": {"type": "string"},
                 "scope": {"type": "string", "enum": ["personal", "team"]}},
                defer_loading=True),
    {"type": "tool_search"},
    {"type": "programmatic_tool_calling", "enabled": True},
]

handlers = {
    "search_tables": warehouse.search_tables,
    "search_context": warehouse.search_context,
    "query_warehouse": warehouse.query,
    "save_memory": warehouse.memory.save,
}
```

模型可以在回答前結合探索、context 和多個查詢。
它永遠拿不到 `WAREHOUSE_URL`。查詢執行留在你的應用程式裡，
在唯讀資料庫角色之下。

### 4. 不用 sandbox 開始調查

只有對話的 session，用建立請求裡的 input 開始：

```python
from openai import AsyncOpenAI

client = AsyncOpenAI()
instructions = """\
Find relevant tables and metric definitions.
Check previous analyses and saved corrections.
Run read-only queries and explain your findings, assumptions, and SQL.
Save memory only when the user explicitly asks.
"""

events = await client.beta.agents.sessions.create(
    agent={
        "model": "gpt-5.6-luna",
        "instructions": instructions,
        "reasoning": {"effort": "high"},
        "tools": tools,
    },
    environment={"type": "none"},
    input="Why did paid conversions drop last week?",
    stream=True,
)
```

讀取 `agent.session.created` 來儲存 `event.session.id`。當建立 stream 發出 `agent.session.requires_action` 時，把每個待處理的 function
call 派發給對應的 handler，並回傳結果：

```python
import json

arguments = action.arguments
if isinstance(arguments, str):
    arguments = json.loads(arguments)
output = handlers[action.name](arguments)
await client.beta.agents.sessions.events.create(
    session_id,
    events=[{
        "type": "agent.session.input.tool_result",
        "turn_id": action.turn_id,
        "call_id": action.call_id,
        "success": True,
        "output": json.dumps(output),
    }],
)
```

持續消耗 stream，直到 coordinator 的這一輪完成。
應用程式會依 turn 和 call ID 去除重複的呼叫，tool 失敗時回傳通用的錯誤，
並把每個執行過的 SQL 查詢跟答案一起記錄下來。

想直接用完整的迴圈、不用自己重建：

```python
from examples.agents_api.apps.data_analyst.agent import DataAnalyst

analyst = DataAnalyst(client, warehouse)
result = await analyst.answer("Why did paid conversions drop last week?")
print(result["answer"])
print(result["queries"])
```

同一個請求要嘛用底層流程，要嘛用 `DataAnalyst`，不要兩個一起用。

### 5. 接續同一場調查

應用程式把 `conversation_id` 對應到存下來的 API session。追問時把它傳回去：

```python
follow_up = await analyst.answer(
    "Only include enterprise customers.",
    conversation_id=result["conversation_id"],
)
print(follow_up["answer"])
```

內部的追問用 `client.beta.agents.sessions.stream(session_id,
input=question, tool_handlers=handlers)`。跟建立 stream 不同，這個 SDK
helper 會幫你派發 function handler。

### 6. 儲存明確的修正

請 agent 記住一條規則，例如：「Remember that enterprise
conversion excludes manually provisioned accounts.」`save_memory` tool
會用個人或團隊範圍寫入這則筆記：

```python
warehouse.memory.save({
    "note": "Enterprise conversion excludes manually provisioned accounts.",
    "scope": "team",
})
remembered = warehouse.search_context({"query": "enterprise conversion"})
print(remembered["memories"])
```

Session 歷史保留目前的對話。跨 session 的記憶由應用程式擁有：[memory.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/memory.py) 把修正存在 `memories.json`。
服務多個使用者時，要把這個儲存搬到你應用程式的資料庫。

### 7. 檢查證據並清理

一個有用的答案包含結果、查詢過的資料表、SQL 和任何假設。
把敘述當成要對照這些記錄驗證的結論，
不是取代它們。結果取決於你的資料倉儲，這個範例
沒有附固定的業務資料集。

分析師用完後，刪除 session 並關閉資料倉儲：

```python
try:
    await analyst.close()
finally:
    await client.close()
```

瀏覽器應用程式在關閉時會做這個清理。它把目前活躍的
對話對應存在記憶體，而存下來的修正在重啟後仍然存在。

## 檔案

- [main.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/main.py)：Web 路由、UI 和命令列入口。
- [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/agent.py)：Agent 設定、tool 和對話流程。
- [warehouse.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/warehouse.py)：唯讀查詢、schema 和商業 context。
- [memory.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/data_analyst/memory.py)：存下來的個人和團隊修正。

## 重點整理
- 資料庫存取和 context 可見範圍由你的應用程式掌控，模型拿不到 `WAREHOUSE_URL`
- 先探索真實 schema 再寫 SQL，加上審核過的 metric 定義和 query_history，分析才有根據
- Agents API session 讓多次查詢和追問留在同一場調查裡，用 `conversation_id` 接續
- 跨 session 的記憶是應用程式自己的責任，多使用者時要搬到資料庫並從驗證層取得身分
- 答案要附上結果、SQL 和假設，敘述只是待驗證的結論

## 練習
1. 在 `.env` 打開 `DATA_AGENT_CONTEXT`，在 context 檔的 `metrics` 裡新增一個你自己的指標定義，然後問 agent 跟它有關的問題。
2. 在 `query_history` 加一筆帶描述的 SQL，問一個需要它的問題，確認 agent 有沒有重用這個 join，並注意它有沒有補上日期範圍。
3. 修改 `query_warehouse` 的回傳筆數上限，從 100 改成 20，觀察 agent 在結果被截斷時怎麼調整查詢。
