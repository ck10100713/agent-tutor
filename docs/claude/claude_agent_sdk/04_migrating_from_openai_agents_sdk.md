---
translated: true
source: claude_agent_sdk/04_migrating_from_openai_agents_sdk.ipynb
---

# 從 OpenAI Agents SDK 遷移到 Claude Agent SDK

> 原文：[claude_agent_sdk/04_migrating_from_openai_agents_sdk.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/04_migrating_from_openai_agents_sdk.ipynb)

用一個費用核准 agent 當範例，把 OpenAI Agents SDK 的 app 搬到 Claude Agent SDK，逐一對應 tools、guardrails、sessions、handoffs 這些元件。

## 這篇在做什麼

這篇用同一個費用核准 agent，先用 OpenAI Agents SDK 寫一遍，再一個元件一個元件搬到 Claude Agent SDK。兩邊都真的會跑，最後並排比較結果。業務邏輯不用重寫，主要是換外層的包裝。

## 學完你會

- 把 `@function_tool`、guardrails、`Runner.run` 換成 Claude 的對應寫法，不用重寫業務邏輯
- 搬一個單 agent 的 app：自訂 tool、輸入與輸出 guardrail、多輪 session、可持久化的 resume
- 分得清什麼時候用 `ClaudeSDKClient`，什麼時候用無狀態的 `query()`

## 開跑前

`.env` 裡要有 `OPENAI_API_KEY` 和 `ANTHROPIC_API_KEY`，兩個都會真的呼叫，都會花錢。Colab 的話把兩個 key 放進 Secrets，或在 cell 裡設成環境變數。

如果你的 app 已經用 OpenAI Agents SDK 寫好，想搬到 Claude Agent SDK，這份 notebook 用一個例子（費用核准 agent）把每個元件對應一遍。

**搬完之後你得到什麼。** Claude Agent SDK 跑在跟 Claude Code 同一個 runtime 上，所以你直接繼承內建的 `Read`、`Edit`、`Bash`、`Grep` tool、一套分層的權限系統（控制 agent 能碰什麼）、自動 prompt caching，還能直接拿到 event stream，用來串流進度或在執行中途攔截。tool 的定義是明確的（你自己宣告 schema，不靠 type hint 推導），loop 由你來驅動。多數情況下，每個 tool 的樣板碼會多一點，其他地方的樣板碼會少很多。

## 這份 notebook 結束時，你能做到：

- 把 `@function_tool`、guardrails 和 `Runner.run` 換成 Claude 的對應寫法，不用重寫業務邏輯
- 搬一個單 agent 的 app：自訂 tool、輸入與輸出 guardrail、多輪 session、可持久化的 resume
- 知道什麼時候該用 `ClaudeSDKClient`，什麼時候用無狀態的 `query()` 函式
- 把 SDK 的 OpenTelemetry export 接到你現有的 observability 堆疊

兩個 SDK 都會真的執行。你需要在 `.env` 裡放 `OPENAI_API_KEY` 和 `ANTHROPIC_API_KEY`。

| OpenAI Agents SDK | Claude Agent SDK |
|---|---|
| `Agent(name, instructions, tools)` | `ClaudeAgentOptions` + system prompt |
| `@function_tool` | `@tool` + `create_sdk_mcp_server` |
| `@input_guardrail` | 在 loop 之前呼叫的一般函式（或 `UserPromptSubmit` hook） |
| `@output_guardrail` | 對 `ResultMessage.result` 做檢查的一般函式 |
| `Runner.run(agent, msg)` | `ClaudeSDKClient` context manager |
| `Sessions`（client 管理） | 重複使用同一個 `ClaudeSDKClient` |
| `conversation_id`（server 管理） | `resume=session_id`（存在磁碟） |
| 內建 tracing dashboard | 原生 OTel，可接你現有的 Grafana/Datadog/Honeycomb |
| `handoffs=[...]` | `AgentDefinition` + Agent tool，見附錄 |

## 範例：費用核准

一個核准或標記費用申請的 agent。一個 tool（`check_policy`）、一個輸入 guardrail（沒有金額就拒絕）、一個 loop。

我們先用 OpenAI Agents SDK 建一遍，再逐個元件搬過去。

## 前置條件

**需要的知識**

- 熟悉 Python 的 `async`/`await`
- 熟悉你要搬離的 OpenAI Agents SDK 元件

**需要的工具**

- Python 3.11 或 3.12
- `ANTHROPIC_API_KEY`（[申請](https://console.anthropic.com)）和 `OPENAI_API_KEY`（[申請](https://platform.openai.com/api-keys)），兩個 SDK 都會真的執行

**建議：**

- 先快速看過 [notebook 00](00_The_one_liner_research_agent.md)，了解 `query()` 和 `ClaudeSDKClient` 的基本用法

> `openai-agents` 釘在 `0.9.3`，它還沒到 1.0，API 常常改。如果你升版，要重新確認 `Agent`/`Runner`/`@function_tool` 的簽名。

```python
%%capture
# openai-agents pinned to 0.9.3 — see prereqs note before bumping
%pip install "openai-agents==0.9.3" claude-agent-sdk python-dotenv
```

```python
import os
import re
from dataclasses import replace

from dotenv import load_dotenv

load_dotenv()

assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY missing from .env"
assert os.getenv("ANTHROPIC_API_KEY"), "ANTHROPIC_API_KEY missing from .env"

OAI_MODEL = "gpt-4.1"
CLAUDE_MODEL = "claude-sonnet-5-5"
```

```python
# ===== OpenAI Agents SDK — full implementation =====
from agents import Agent, GuardrailFunctionOutput, Runner, function_tool, input_guardrail


@function_tool
def check_policy(category: str, amount: float) -> dict:
    """Look up the expense policy for a category. Returns the approval limit. Valid categories: meals, travel, software, other."""
    limits = {"meals": 75.0, "travel": 500.0, "software": 200.0, "other": 50.0}
    return {
        "category": category,
        "limit": limits.get(category.lower(), 50.0),
        "requires_receipt": amount > 25.0,
    }


@input_guardrail
def has_dollar_amount(ctx, agent, user_input: str) -> GuardrailFunctionOutput:
    has_amount = bool(re.search(r"\$\d+", user_input))
    return GuardrailFunctionOutput(
        output_info={"has_amount": has_amount},
        tripwire_triggered=not has_amount,
    )


expense_agent = Agent(
    name="Expense Approver",
    instructions=(
        "You approve or flag expense submissions. "
        "Always call check_policy first to get the limit for the expense category. "
        "Approve if the amount is under the limit; otherwise flag for manager review."
    ),
    tools=[check_policy],
    input_guardrails=[has_dollar_amount],
    model=OAI_MODEL,
)


async def run_oai(msg: str) -> str:
    result = await Runner.run(expense_agent, msg)
    return result.final_output


print(await run_oai("Lunch with Acme, $47"))
```

??? note "輸出"

    ```text
    This lunch expense of $47 falls under the "meals" category, which has an approval limit of $75. Since the amount is below the limit, I approve the expense (assuming a receipt is provided, as required by policy).
    ```

## 一個元件一個元件搬

### `@function_tool` → `@tool` + `create_sdk_mcp_server`

**OpenAI：** `@function_tool` 從 type hint 和 docstring 推導 tool schema。裝飾好的函式直接放進 `tools=[...]`。

**Claude：** `@tool` 把名稱、描述和 schema 當成明確的參數，你寫什麼，模型就看到什麼。handler 是 `async`，接收單一的 `args` dict，回傳 `{"content": [{"type": "text", "text": ...}]}`。tool 會打包成一個 in-process 的 MCP server（雖然叫 MCP，但沒有子行程也沒有網路傳輸），這個 server 就是你傳給 agent 的單位。

函式裡面的邏輯不用改，只有外面的包裝不一樣。

```python
import json

from claude_agent_sdk import create_sdk_mcp_server, tool


@tool(
    "check_policy",
    "Look up the expense policy for a category. Returns the approval limit. Valid categories: meals, travel, software, other.",
    {"category": str, "amount": float},
)
async def check_policy_claude(args):
    limits = {"meals": 75.0, "travel": 500.0, "software": 200.0, "other": 50.0}
    category, amount = args["category"], args["amount"]
    result = {
        "category": category,
        "limit": limits.get(category.lower(), 50.0),
        "requires_receipt": amount > 25.0,
    }
    return {"content": [{"type": "text", "text": json.dumps(result)}]}


policy_server = create_sdk_mcp_server(name="expense", tools=[check_policy_claude])
```

### `Agent(...)` → `ClaudeAgentOptions`

`ClaudeAgentOptions` 裝的是 model、tools 和 system prompt，也就是真正會送給 Claude 的設定。guardrail 邏輯留在你的應用程式碼裡，不用註冊到框架物件上。OpenAI 的 `Agent` 則把這些全部綁在一起。

| `Agent(...)` 欄位 | `ClaudeAgentOptions` 對應 |
|---|---|
| `instructions=...` | `system_prompt=...` |
| `tools=[fn]` | `mcp_servers={...}` + `allowed_tools=[...]` |
| `model=...` | `model=...` |
| `name=...` | 不需要，options 只是設定值，不是有名字的實體。subagent 的名字放在 `AgentDefinition`（見附錄）。 |
| `input_guardrails=[...]` | 在你自己的 run 函式裡呼叫，見下一節 |

`allowed_tools` 裡的 tool 名稱格式是 `mcp__{server_name}__{tool_name}`。

> **關於權限的提醒：** `allowed_tools` 是 allow 規則，只是讓 tool *可用*。agent 能不能不經使用者同意就呼叫，要看 `permission_mode`。像 `check_policy` 這種唯讀的自訂 tool 預設可以直接跑；會寫檔或跑 shell 指令的 tool 會跳出詢問，除非你設 `permission_mode="acceptEdits"` 或 `"bypassPermissions"`。如果你的 tool 不只是讀取，請看[權限指南](https://platform.claude.com/docs/en/agent-sdk/permissions)。

```python
from claude_agent_sdk import ClaudeAgentOptions

expense_system_prompt = (
    "You approve or flag expense submissions. "
    "Always call check_policy first to get the limit for the expense category. "
    "Approve if the amount is under the limit; otherwise flag for manager review."
)

expense_options = ClaudeAgentOptions(
    model=CLAUDE_MODEL,
    system_prompt=expense_system_prompt,
    mcp_servers={"expense": policy_server},
    allowed_tools=["mcp__expense__check_policy"],
    # Be explicit: since claude-agent-sdk 0.2, leaving these unset loads your user and
    # project Claude Code settings and lets the CLI choose the permission mode.
    setting_sources=[],
    permission_mode="default",
)
```

> **內建 tool。** 費用 agent 只用到自訂 tool，但 SDK 內建 `Read`、`Edit`、`Bash`、`Grep` 等等，用名稱加進 `allowed_tools` 即可（例如 `allowed_tools=["Read", "Grep", "mcp__expense__check_policy"]`）。檔案系統的用法見 [notebook 00](00_The_one_liner_research_agent.md)。

### `@input_guardrail` / `@output_guardrail` → 呼叫前後的檢查

**OpenAI：** `@input_guardrail` 檢查使用者的訊息，`@output_guardrail` 檢查 agent 的最終答案。兩者要阻擋時都回傳 `GuardrailFunctionOutput(tripwire_triggered=True)`，這會 raise `InputGuardrailTripwireTriggered`（或 output 版本）。input guardrail 跟 agent 是同時跑的。

**Claude：** 你的檢查就是一般函式。在啟動 client 之前呼叫 input 檢查，loop 結束後對 `ResultMessage.result` 呼叫 output 檢查。

| OAI | Claude |
|---|---|
| `@input_guardrail` decorator | loop 之前呼叫的一般函式 |
| `@output_guardrail` decorator | loop 結束後對 `result.result` 呼叫的一般函式 |
| `tripwire_triggered=True` 會 raise | 提早 return（input）或覆寫結果（output） |
| 註冊在 `Agent(input_guardrails=[...])` | 在你的 run 函式裡呼叫 |

#### 替代做法：`UserPromptSubmit` hook

SDK 的 `UserPromptSubmit` hook 會在 prompt 送到 Claude 之前觸發，而且能擋掉它，結構上最接近 `@input_guardrail`。下面兩種寫法都會給，但 demo 用一般函式，原因有兩個：拒絕訊息掌握在你手上（hook 擋下時 `ResultMessage.result` 回來是空的，原因不會傳給呼叫端），而且 guardrail 邏輯留在你的 run 函式裡看得到，不用註冊到 options 物件上。`@output_guardrail` 沒有乾淨的 hook 對應，`Stop` 在回應完成後才觸發，也不能改寫輸出。想看用 `PreToolUse` hook 管 tool 呼叫的做法，見 [notebook 03](03_The_site_reliability_agent.md)，那是另一種用途。

```python
def has_dollar_amount_check(user_input: str) -> tuple[bool, str | None]:
    """Input check — returns (allowed, rejection_message)."""
    if re.search(r"\$\d+", user_input):
        return True, None
    return False, "I need a dollar amount to process this. Please include one (e.g., '$47')."


def has_decision_check(result: str) -> tuple[bool, str | None]:
    """Output check — returns (allowed, override_message)."""
    # Stem match is intentionally permissive for a demo; tighten for production.
    if re.search(r"\b(approv|flag|review)", result, re.IGNORECASE):
        return True, None
    return False, "I couldn't reach a clear approve/flag decision. Please resubmit."
```

比較用的是同一個檢查改接成 `UserPromptSubmit` hook。callback 會收到 `input_data["prompt"]`，回傳 `{}` 表示放行，回傳 `{"decision": "block", "reason": "..."}` 表示阻擋。這裡的 `HookMatcher` 不需要 `matcher` 參數，因為 `UserPromptSubmit` 對每個 prompt 都會觸發，沒有 tool 名稱可以過濾。

想試的話，把下一節 `ClaudeSDKClient(...)` 呼叫裡的 `options=expense_options` 換成 `options=hooked_options`。有個限制：`UserPromptSubmit` hook 阻擋時，原因目前不會出現在 `ResultMessage.result`，你會拿到空字串而不是拒絕訊息。所以 demo loop 用一般函式，因為它自己控制回傳值。

如果要做 tool 層級的 guardrail，也就是管 agent *做什麼*，而不是使用者*送什麼*，請看 [notebook 03](03_The_site_reliability_agent.md) 的 `PreToolUse` hook 做法。

```python
from claude_agent_sdk import HookMatcher


async def has_dollar_amount_hook(input_data, tool_use_id, context):
    # tool_use_id is None for UserPromptSubmit — it's a uniform signature across all hook types.
    if re.search(r"\$\d+", input_data["prompt"]):
        return {}
    return {"decision": "block", "reason": "I need a dollar amount to process this."}


hooked_options = ClaudeAgentOptions(
    model=CLAUDE_MODEL,
    system_prompt=expense_system_prompt,
    mcp_servers={"expense": policy_server},
    allowed_tools=["mcp__expense__check_policy"],
    hooks={"UserPromptSubmit": [HookMatcher(hooks=[has_dollar_amount_hook])]},
    setting_sources=[],
    permission_mode="default",
)
```

### `Runner.run()` → `ClaudeSDKClient`

**OpenAI：** `result = await Runner.run(agent, msg)` 跑完整個 loop 並回傳 result 物件，文字從 `result.final_output` 讀。

**Claude：** `ClaudeSDKClient` 是 async context manager。呼叫 `.query(msg)` 送出，再迭代 `.receive_response()` 就能即時拿到 event，每個 tool call、每個 text block 和最終結果都會依序出現。event 類型：

| Event | 內容 |
|---|---|
| `SystemMessage` | session 初始化的 metadata |
| `AssistantMessage` | text block 或 tool-use block |
| `UserMessage` | tool-result block |
| `ResultMessage` | 一定是最後一個：`.result`、`.usage`、`.total_cost_usd` |

最終答案是 `messages[-1].result`。

> SDK 也提供無狀態的 `query()` 函式（見 [notebook 00](00_The_one_liner_research_agent.md)），適合只用內建 tool 的一次性呼叫。如果你要透過 `create_sdk_mcp_server` 帶自訂 tool，就該用 `ClaudeSDKClient`，因為它的持久 transport 會處理 in-process MCP 的 handshake。

```python
from utils.agent_visualizer import display_agent_response, print_activity, reset_activity_context

from claude_agent_sdk import ClaudeSDKClient


async def run_claude(msg: str) -> None:
    # Input guardrail — short-circuit before the agent runs
    allowed, rejection = has_dollar_amount_check(msg)
    if not allowed:
        print(rejection)
        return

    reset_activity_context()
    messages = []
    async with ClaudeSDKClient(options=expense_options) as client:
        await client.query(msg)
        async for event in client.receive_response():
            print_activity(event)
            messages.append(event)

    # receive_response() guarantees ResultMessage is the last event yielded
    final = messages[-1].result
    ok, override = has_decision_check(final or "")
    if not ok:
        print(override)
        return

    display_agent_response(messages)


await run_claude("Lunch with Acme, $47")
```

??? note "輸出"

    ```text
    🤖 Thinking...
    🤖 Thinking...
    🤖 Using: mcp__expense__check_policy()
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### Sessions → `ClaudeSDKClient`（記憶體）或 `resume=`（磁碟）

OpenAI 有兩種 session 模式：

| OAI 模式 | 持久性 | Claude 對應 |
|---|---|---|
| `result.to_input_list()` + 重送 | client 把歷史放在記憶體 | 重複使用同一個 `ClaudeSDKClient`，在同一個開著的 context 裡再呼叫 `.query()` |
| `conversation_id` | 在 server 端，行程重啟後還在 | `resume=session_id`，對話紀錄寫在本機磁碟，重啟後還在 |

**記憶體版（下面）：** 讓 `ClaudeSDKClient` 的 context 一直開著，再呼叫 `.query()`。不用重送歷史，行程結束就沒了。

**磁碟版：** 每次執行都會產生 `session_id`（在 `ResultMessage.session_id`）。把它存起來，下次執行時傳 `ClaudeAgentOptions(resume=session_id, ...)`。對話紀錄放在本機檔案系統，不在 Anthropic 的 server 上，所以重啟後還在，但換機器就沒了。

兩種模式下，對話超過 context window 的處理，請看 [`../misc/session_memory_compaction.ipynb`](../misc/session_memory_compaction.md)。

```python
# --- In-memory: reuse the same client ---
async def run_claude_multiturn():
    async with ClaudeSDKClient(options=expense_options) as client:
        await client.query("Lunch with Acme, $47")
        async for _ in client.receive_response():
            pass  # consume the stream

        # Same client — remembers turn 1
        await client.query("What about $90?")
        turn2 = [m async for m in client.receive_response()]
        # receive_response() guarantees ResultMessage is the last event yielded
        return turn2[-1].result


print(await run_claude_multiturn())
```

??? note "輸出"

    ```text
    🚩 **Flagged for Manager Review**

    | Detail | Info |
    |---|---|
    | **Description** | Lunch with Acme |
    | **Category** | Meals |
    | **Amount** | $90.00 |
    | **Policy Limit** | $75.00 |
    | **Over Limit By** | $15.00 |
    | **Status** | **Flagged** |

    The $90 lunch exceeds the $75 meals limit by **$15.00**, so it requires manager approval before it can be reimbursed.
    ```

```python
# --- Disk-backed: capture session_id, resume later ---

# Turn 1: capture the session_id from the ResultMessage (always the last event)
async with ClaudeSDKClient(options=expense_options) as client:
    await client.query("Lunch with Acme, $47")
    turn1 = [m async for m in client.receive_response()]
session_id = turn1[-1].session_id

# Turn 2: new client, new process — resume from disk
resume_opts = replace(expense_options, resume=session_id)
async with ClaudeSDKClient(options=resume_opts) as client:
    await client.query("What about $90?")
    turn2 = [m async for m in client.receive_response()]
print(f"[resumed {session_id[:8]}...] {turn2[-1].result}")
```

??? note "輸出"

    ```text
    [resumed 4fc6dc1e...] Here's the rundown for both expenses:

    | Expense | Amount | Limit | Status |
    |---|---|---|---|
    | Lunch with Acme | $47 | $75 | ✅ **Approved** |
    | Lunch with Acme | $90 | $75 | 🚩 **Flagged for Manager Review** |

    - **$47** – Under the $75 meals limit, so it's **approved**. (Receipt required.)
    - **$90** – Exceeds the $75 meals limit by $15, so it's **flagged for manager review**.
    ```

## 並排比較

把三個測試輸入都丟進兩個 SDK 跑。預期兩邊都會核准 $47 的午餐、標記 $650 的機票，並拒絕沒有金額的輸入。

```python
from agents.exceptions import InputGuardrailTripwireTriggered


async def run_claude_quiet(msg: str) -> str:
    # Same guardrail as run_claude — duplicated here for a minimal comparison helper
    allowed, rejection = has_dollar_amount_check(msg)
    if not allowed:
        return rejection
    async with ClaudeSDKClient(options=expense_options) as client:
        await client.query(msg)
        messages = [m async for m in client.receive_response()]
        # receive_response() guarantees ResultMessage is the last event yielded
        return messages[-1].result or ""


test_inputs = [
    ("Lunch with Acme, $47", "approve"),
    ("Flight to NYC, $650", "flag"),
    ("Need approval for the thing", "guardrail"),
]

for msg, expected in test_inputs:
    print(f"\n{'=' * 60}\nINPUT: {msg}  (expect: {expected})\n{'=' * 60}")

    try:
        oai_out = await run_oai(msg)
    except InputGuardrailTripwireTriggered:
        oai_out = "[guardrail: InputGuardrailTripwireTriggered]"

    claude_out = await run_claude_quiet(msg)

    print(f"OAI:    {str(oai_out)[:200]}")
    print(f"Claude: {str(claude_out)[:200]}")
```

??? note "輸出"

    ```text

    ============================================================
    INPUT: Lunch with Acme, $47  (expect: approve)
    ============================================================
    OAI:    The expense for lunch ($47) is under the meals category limit of $75. This expense is approved.
    Claude: ✅ **Expense Approved**

    | Detail | Info |
    |---|---|
    | **Description** | Lunch with Acme |
    | **Category** | Meals |
    | **Amount** | $47.00 |
    | **Meal Limit** | $75.00 |
    | **Status** | **Approved** |

    Yo

    ============================================================
    INPUT: Flight to NYC, $650  (expect: flag)
    ============================================================
    OAI:    The approval limit for travel expenses is $500. Since your flight to NYC costs $650, this expense exceeds the limit and will be flagged for manager review.
    Claude: 🚩 **Expense Flagged for Manager Review**

    | Detail | Info |
    |---|---|
    | **Description** | Flight to NYC |
    | **Category** | Travel |
    | **Amount** | $650.00 |
    | **Policy Limit** | $500.00 |
    | **Over Lim

    ============================================================
    INPUT: Need approval for the thing  (expect: guardrail)
    ============================================================
    OAI:    [guardrail: InputGuardrailTripwireTriggered]
    Claude: I need a dollar amount to process this. Please include one (e.g., '$47').
    ```

## Tracing

Claude 輸出的是你的團隊已經在跑的標準格式。

**每次執行的指標你本來就拿得到。** 每個 `ResultMessage` 都帶 `.total_cost_usd` 和 `.usage`，包含 input/output token、cache 讀取、cache 寫入和 turn 數。你會在下面的 caching cell 看到。要做程式化的成本追蹤，見 [`../observability/usage_cost_api.ipynb`](../observability/usage_cost_api.md)。

**原生支援 OpenTelemetry。** SDK 和 Claude Code 共用 runtime，啟用時會匯出 OTel 的 metrics 和 events：

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_METRICS_EXPORTER=otlp
export OTEL_LOGS_EXPORTER=otlp
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4317
```

這些對搬遷都不是必要的，不管 telemetry 開不開，你的 agent 跑起來都一樣。

每個 tool call 和 API request 都會發出一個帶 `prompt.id` 標籤的 event，所以你能把所有活動追溯回最初的 prompt。可以接到你現有的 Grafana / Datadog / Honeycomb / Langfuse。完整的 event schema 見[監控文件](https://code.claude.com/docs/en/monitoring-usage)。

## Claude 獨有：prompt caching

system prompt 和 tool schema 在第一次呼叫後會自動快取，不需要設定。之後前綴相同的呼叫，這段前綴大約只付 10% 的 input token 成本。
> 前面的 cell 已經用 `expense_options` 跑過了，所以到這裡 cache 已經熱了，連 Run 1 都會看到大量的 `cache_read_input_tokens`。在全新的 notebook 裡，Run 1 主要是 `cache_creation`，Run 2 主要是 `cache_read`。tool-calling loop 每次 query 會發好幾個 API request，每個都會延伸快取的前綴，所以重複執行時 cache_creation 也不會歸零，但會變少，cache_read 會變多。

```python
for i in range(2):
    async with ClaudeSDKClient(options=expense_options) as client:
        await client.query("Coffee, $6")
        messages = [m async for m in client.receive_response()]
    # receive_response() guarantees ResultMessage is the last event yielded
    usage = messages[-1].usage or {}
    print(
        f"Run {i + 1}: cache_creation={usage.get('cache_creation_input_tokens', 0):>5}  "
        f"cache_read={usage.get('cache_read_input_tokens', 0):>5}  "
        f"input={usage.get('input_tokens', 0):>5}"
    )
```

??? note "輸出"

    ```text
    Run 1: cache_creation=38728  cache_read=66272  input=    4
    Run 2: cache_creation=  659  cache_read=95025  input=    4
    ```

---
## 附錄：遷移 `handoffs`

如果你的 OpenAI Agents SDK app 用了 `handoffs=[...]`，心智模型要在這裡轉個彎。

**OpenAI：** `handoffs=[specialist]` 會暴露一個 `transfer_to_specialist` tool。被呼叫時，specialist **接手**對話，第一個 agent 就結束了。

**Claude：** subagent 透過 `AgentDefinition` 以程式碼定義，傳進 `ClaudeAgentOptions(agents={...})`。orchestrator 透過 Agent tool **委派**工作、拿回結果，並一直掌握控制權。

如果只是純路由（分流到 specialist），差異不大。如果你的 app 非得「agent B 接手之後 A 再也不跑」不可，可以考慮用一個薄薄的 Python dispatcher，而不是讓 LLM 決定路由。

> 你也可能在 Claude Code CLI 的流程裡看到 subagent 被定義成 `.claude/agents/*.md` 檔案（例如 [notebook 01](01_The_chief_of_staff_agent.md)）。那是互動使用的檔案系統路線。如果是以程式碼形式發佈的 SDK 應用，下面這種程式化的 `agents=` 參數比較合適，不依賴檔案系統。

```python
from claude_agent_sdk import AgentDefinition

approver = AgentDefinition(
    description="Approves expenses under policy limits. Use for any submission where the amount is at or under the limit returned by check_policy.",
    prompt="You approve expense submissions that are within policy. Confirm the amount and category, and remind the submitter if a receipt is required.",
    tools=["mcp__expense__check_policy"],
)

escalator = AgentDefinition(
    description="Escalates over-limit expenses to a manager. Use when the submitted amount exceeds the policy limit for its category.",
    prompt="You escalate over-limit expenses. Draft a one-line note to the manager: include the amount, the category, and how far over the limit it is.",
    tools=["mcp__expense__check_policy"],
)

triage_options = ClaudeAgentOptions(
    model=CLAUDE_MODEL,
    system_prompt="Route each expense to the appropriate subagent. Delegate to approver if under limit, escalator if over.",
    mcp_servers={"expense": policy_server},
    allowed_tools=["Agent", "mcp__expense__check_policy"],
    agents={"approver": approver, "escalator": escalator},
    setting_sources=[],
    permission_mode="default",
)

print(f"Orchestrator configured with subagents: {list(triage_options.agents)}")

# Config only — not executed here. For a full end-to-end multi-agent run,
# see ./01_The_chief_of_staff_agent.ipynb
```

??? note "輸出"

    ```text
    Orchestrator configured with subagents: ['approver', 'escalator']
    ```

## 結論

### 你做了什麼

一個費用核准 agent，一個元件一個元件搬過去：`@function_tool` → `@tool`、`Agent` → `ClaudeAgentOptions`、`@input_guardrail`/`@output_guardrail` → 一般的前後檢查、`Runner.run` → `ClaudeSDKClient`，還有記憶體版和磁碟版的 session。

### 重點

- **Tools：** 明確的 schema 表示你寫什麼模型就看到什麼，沒有推導帶來的意外。打包成 in-process MCP server，透過 `ClaudeSDKClient` 傳入。
- **Guardrails：** 一般函式讓拒絕流程在你的程式碼裡，而不是在框架裡。想註冊在 options 上時可以用 `UserPromptSubmit` hook。
- **Sessions：** 記憶體內多輪對話用同一個 `ClaudeSDKClient`；要跨重啟的對話就用 `resume=session_id` 存在磁碟。
- **Tracing：** 原生 OpenTelemetry，可以接上你現有的堆疊。每輪的成本和 token 用量都在每個 `ResultMessage` 上，不用另外接線。

### 下一步

- 多 agent 編排：[01_The_chief_of_staff_agent.ipynb](01_The_chief_of_staff_agent.md)
- tool 生命週期 hooks（`PreToolUse`/`PostToolUse`）：[03_The_site_reliability_agent.ipynb](03_The_site_reliability_agent.md)
- 成本與用量追蹤做法：[../observability/usage_cost_api.ipynb](../observability/usage_cost_api.md)

## 重點整理

- tool 的 schema 在 Claude 這邊是你明確寫的，不靠 type hint 推導，業務邏輯不變，只換包裝。
- OpenAI 的 `Agent` 把設定、tools、guardrails 綁成一個物件，Claude 把它拆成 `ClaudeAgentOptions` 加你自己的應用程式碼。
- guardrail 就是 loop 前後呼叫的一般函式，`UserPromptSubmit` hook 是可選的替代，但阻擋原因不會回傳給呼叫端。
- session 分記憶體版（同一個 `ClaudeSDKClient`）和磁碟版（`resume=session_id`），後者不跨機器。
- handoff 在 Claude 是委派不是接手，orchestrator 始終握有控制權。

## 練習

1. 在費用 agent 的 `check_policy` 之外，加一個輸出 guardrail：如果 `ResultMessage.result` 沒提到金額就覆寫成提示訊息。
2. 把 `allowed_tools` 加上 `"Read"`，並把 system prompt 改成要求 agent 讀一個本機的 policy 檔，觀察權限提示怎麼出現。
3. 用 `ResultMessage.session_id` 存下 session，另開一次執行用 `resume=session_id` 接續上一輪的對話，驗證它記得前一筆費用。
