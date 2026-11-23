---
translated: true
source: examples/agents_sdk/migrate-from-claude-agent-sdk/README.md
---

# 從 Claude Agent SDK 遷移到 OpenAI Agents SDK

> 原文：[examples/agents_sdk/migrate-from-claude-agent-sdk/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/migrate-from-claude-agent-sdk/README.md)

教你把 Claude Agent SDK 的應用遷移到 OpenAI Agents SDK，包含 tool 對應、guardrails、handoffs、approvals 和 sandbox 邊界。

## 這篇在做什麼

用一個訂機票助理當範例，把原本用 Claude Agent SDK 寫的 agent，一步步改寫成 OpenAI Agents SDK 版本。重點不只是換 API，而是理解兩邊在 harness、sandbox、權限和多 agent 歸屬上的架構差異。

## 學完你會

- 分得清楚 Claude 的「harness 在 sandbox 裡」和 OpenAI 的「harness 與 compute 分離」兩種架構，並決定哪些事放在受信任的 runtime、哪些放進 sandbox。
- 把 `@tool` 自訂工具改成 `@function_tool`，把 hooks 與權限檢查對應到 guardrails、approvals 或 `RunHooks`。
- 用 `agent.as_tool(...)` 或 `handoffs=[...]` 實作多 agent，並加上 human approval 與對話狀態策略。

## 開跑前

範例程式需要 Claude 與 OpenAI 的 API key，並且要把 `MODEL`、`GUARDRAIL_MODEL` 設成你帳號可用的模型。

## 為什麼要遷移

更新後的 [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents) 提供一個 model-native 的 harness，可以協調 tools、檔案、記憶、approvals 和 sandbox 運算。它是開源的，你可以自己看、自己改 runtime 的行為。不用每換一個模型就重做這些零件，直接用一套標準 SDK，agent loop 也一直是看得到、改得動的。

很多 Claude Agent SDK 的應用都遵循 Claude Code 的運作模式：載入專案指示、載入 skills、開放檔案/shell/web 工具、視需要定義 subagents，然後讓 Claude 的 harness 在 workspace 裡面運作。新的 OpenAI Agents SDK 把 agent harness 和運算環境分得更明確。

最重要的架構差異：

- **Claude Agent SDK 的模式：** harness 跑在 sandbox 裡面。agent loop、MCP/tools、檔案存取、執行環境都在 sandbox 內。
- **新的 OpenAI Agents SDK 模式：** harness 跟 compute 分開。受信任的應用 runtime 掌管 agent loop、tools、approvals、secrets、guardrails、tracing，還有業務系統的存取權。

讀完之後，你會有一個遷移好的應用，行為跟原本的 Claude 版一致，但執行、安全、狀態和責任歸屬都變得明確。

## 架構

### 把 sandbox 當成 tool

Claude Agent SDK 的應用遵循 Claude Code 的模式：sandbox 就是 agent 的主要工作區。agent loop、tools、檔案系統和執行環境通常放在一起。sandbox 和內部系統之間可能有一層 gateway，讓 sandbox 能發出受控的請求，而不用直接持有敏感憑證。

<figure>
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_sdk/migrate-from-claude-agent-sdk/assets/claude-agent-sdk-pattern.png" alt="Diagram of a Claude Agent SDK pattern where the server starts a coding agent inside a sandbox that contains the harness, agent loop, tools, and filesystem, with gateway-mediated access to data, APIs, and the web." />
  <figcaption>
    Claude Agent SDK apps often put the harness and execution environment in the
    same sandbox boundary.
  </figcaption>
</figure>

在 OpenAI Agents SDK 的模式裡，harness 跟 compute（sandbox）是分開的。sandbox 是 harness 可以呼叫的一個 tool，agent 需要限定範圍的運算、檔案存取、程式執行、artifacts 或可執行的 skills 時才用。

<figure>
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_sdk/migrate-from-claude-agent-sdk/assets/openai-agents-sdk-pattern.png" alt="Diagram of an OpenAI Agents SDK pattern where the trusted application runtime owns secrets, the harness, the agent loop, and tools, while sandbox compute handles shell commands and filesystem work." />
  <figcaption>
    OpenAI Agents SDK apps keep orchestration in the trusted runtime and use the
    sandbox as an execution surface.
  </figcaption>
</figure>

信任的控制權留在 host 應用裡，sandbox 只拿來做以 workspace 為中心的執行。

這樣比較安全，也比較好維運，因為 secrets、approval 決定和業務系統存取都在執行環境之外。sandbox 的輸入、輸出和 approvals 都由應用掌控。

### Skills 和指示檔

遷移 Claude Agent SDK 專案時，要依職責把指示檔和 skill 檔拆開。

| Claude                                 | OpenAI                            | 遷移規則                                                                                 |
| -------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------- |
| `CLAUDE.md` product behavior           | `Agent.instructions`              | Keep the agent role, task policy, tool-use rules, and response format here.                    |
| `CLAUDE.md` repo or workspace guidance | `AGENTS.md`                       | Keep repo-wide conventions, test commands, output paths, and non-default workspace rules here. |
| `.claude/skills/*/SKILL.md`            | `.agents/skills/*/SKILL.md`       | Convert reusable workflows into OpenAI skills.                                                 |
| Skill references, templates, examples  | `references/` or `assets/`        | Keep reference material out of the main prompt.                                                |
| Skill scripts or executables           | Sandbox-backed skill execution    | Run executable skill logic in a sandbox.                                                       |
| `.claude/agents/*.md`                  | Explicit `Agent(...)` definitions | For each Claude subagent, create a named `Agent(...)` and clear instructions.                  |

Agent 身分、可重用的流程、參考資料、可執行邏輯、runtime 設定，這幾樣要分開放。

### Lifecycle callbacks 和權限

Claude 的 lifecycle callback 可以檢查一次 tool call，決定要不要繼續、擋下來，或是請求權限。OpenAI 的 lifecycle callbacks 運作方式不同：它們是告訴你的應用「執行中發生了什麼」，不是處理 approvals 和權限的主要地方。

唯讀的 Claude callbacks（例如 logging 或 telemetry）遷到 OpenAI 的 callbacks。會批准或改變執行流程的 Claude callbacks，則遷到 OpenAI 的 guardrails 或 approvals。

| Use of callback              | Claude pattern                     | Migration to OpenAI                    |
| ---------------------------- | ---------------------------------- | -------------------------------------- |
| Log a tool call              | `PreToolUse` / `PostToolUse`       | `RunHooks` or `AgentHooks`             |
| Block a risky tool call      | Callback returns a blocking result | Tool guardrail or approval             |
| Ask a human before an action | Permission callback                | `needs_approval` and `RunState` resume |

### Subagents 和歸屬

OpenAI Agents SDK 把 agent 的歸屬講得很明確。

主 agent 要保持控制權、呼叫專家、整合結果並產生最終回答時，用 `agent.as_tool(...)`。

專家要接手整個對話、負責最終回應時，用 `handoffs=[...]`。

### 要遷移哪些東西

大部分遷移歸結為十個決定：

| Claude concept            | Migration                                                                                                        |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Sandbox boundary          | Decide what to run in isolated compute vs trusted runtime                                                        |
| Instructions and skills   | Map `CLAUDE.md` / agent instructions to `Agent.instructions`; convert reusable workflows into OpenAI skills.     |
| Custom tools              | Convert business/domain actions into typed `@function_tool` functions                                            |
| Built-in tools            | Choose the right execution surface: hosted, local/runtime, or sandbox-based                                      |
| Guardrails                | Add guardrails at input, output, and tool boundaries                                                             |
| Agent loop                | Use `Runner.run(...)`                                                                                            |
| Multi-agent ownership     | Use `agent.as_tool(...)` to keep the orchestrator in control, or pass control to specialist via `handoffs=[...]` |
| Conversation continuation | Choose separate strategies for conversation context, paused-run resume, and sandbox-session resume               |
| Approvals                 | Gate side effects behind human approval and resume from interruptions                                            |
| Lifecycle callbacks       | Move logging/tracing to `RunHooks` or `AgentHooks`. Move blocking, approval, or execution-shaping logic to guardrails, approvals, or filters |

先釐清每個 Claude 功能原本提供什麼行為，再挑 OpenAI 裡能保住這個行為、且執行與安全邊界正確的那個介面。

## 範例：訂機票助理

這份指南用一個訂機票助理當貫穿全文的範例。

原本的 Claude 應用會：

- 搜尋可訂的航班。
- 檢查差旅政策。
- 有合規選項時推薦一個。
- 選項都不合政策時建議升級處理（escalation）。

使用者請求範例：

```text
Book SFO to JFK on 2026-05-10 under $700.
```

### 共用的領域行為

下面 Claude 和 OpenAI 的範例都用這組資料和政策規則。

```python
from dataclasses import asdict, dataclass


@dataclass
class Flight:
    flight_id: str
    origin: str
    destination: str
    date: str
    departure_time: str
    arrival_time: str
    price_usd: int
    refundable: bool


FLIGHTS = [
    Flight("AS-301", "SFO", "JFK", "2026-05-10", "08:10", "16:45", 642, True),
    Flight("UA-882", "SFO", "JFK", "2026-05-10", "11:20", "19:58", 735, True),
    Flight("DL-441", "SFO", "JFK", "2026-05-10", "13:05", "21:35", 689, False),
]


def flight_to_dict(flight: Flight) -> dict:
    return asdict(flight)


def find_flight(flight_id: str) -> Flight | None:
    return next((flight for flight in FLIGHTS if flight.flight_id == flight_id), None)


def policy_verdict(flight: Flight, max_price_usd: int) -> dict:
    within_budget = flight.price_usd <= max_price_usd
    compliant = within_budget and flight.refundable
    reasons = []

    if not within_budget:
        reasons.append(f"price_usd exceeds max_price_usd={max_price_usd}")
    if not flight.refundable:
        reasons.append("flight is non-refundable")

    return {
        "flight_id": flight.flight_id,
        "compliant": compliant,
        "reasons": reasons or ["within budget and refundable"],
    }
```

## Claude Agent SDK 的基準實作

在 Claude Agent SDK 裡，用 `ClaudeAgentOptions` 設定 agent 行為。

Tool 的開放與 tool 的核准是兩種獨立的控制。`tools` 選擇內建 Claude Code tools 的基本集合，`mcp_servers` 把 MCP server 的 tools 加進 session。`allowed_tools` 是權限白名單：符合的 tool call 會自動核准，但沒列在裡面的 tool 並不會從 Claude 的 tool 集合中移除。

這個範例裡，Claude 應用加了一個 in-process MCP server，裡面有兩個自訂業務 tools，並自動核准這兩個 tool call，讓 demo 不用跳出核准提示就能跑：

- `search_flights` - 依路線、日期和預算找出候選航班。
- `check_travel_policy` - 依預算和退票政策評估候選航班。

### Claude 的自訂 tools

```python
from typing import Any
import asyncio
import json

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    tool,
)


@tool(
    "search_flights",
    "Search flights for a route and date under a maximum budget.",
    {
        "type": "object",
        "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
            "date": {"type": "string"},
            "max_price_usd": {"type": "integer"},
        },
        "required": ["origin", "destination", "date"],
    },
)
async def search_flights(args: dict[str, Any]) -> dict[str, Any]:
    max_price_usd = args.get("max_price_usd", 9999)
    matches = [
        flight_to_dict(flight)
        for flight in FLIGHTS
        if flight.origin == args["origin"]
        and flight.destination == args["destination"]
        and flight.date == args["date"]
        and flight.price_usd <= max_price_usd
    ]
    return {
        "content": [
            {"type": "text", "text": json.dumps({"flights": matches})}
        ]
    }


@tool(
    "check_travel_policy",
    "Check whether a flight is compliant with travel policy.",
    {
        "type": "object",
        "properties": {
            "flight_id": {"type": "string"},
            "max_price_usd": {"type": "integer"},
        },
        "required": ["flight_id", "max_price_usd"],
    },
)
async def check_travel_policy(args: dict[str, Any]) -> dict[str, Any]:
    flight = find_flight(args["flight_id"])
    if flight is None:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"flight_id": args["flight_id"], "error": "not_found"}
                    ),
                }
            ],
            "is_error": True,
        }

    verdict = policy_verdict(flight, args["max_price_usd"])
    return {"content": [{"type": "text", "text": json.dumps(verdict)}]}
```

### Claude 的 run loop

```python
travel_tools = create_sdk_mcp_server(
    name="travel",
    version="1.0.0",
    tools=[search_flights, check_travel_policy],
)

options = ClaudeAgentOptions(
    system_prompt=(
        "You help users evaluate flight options. "
        "Always search flights and check travel policy before recommending. "
        "Recommend a compliant option when one exists. "
        "If no compliant option exists, recommend escalation instead. "
        "Do not purchase tickets or charge a card."
    ),
    mcp_servers={"travel": travel_tools},
    # Pre-approve these travel MCP tools so the demo runs without
    # permission prompts. This does not hide or disable other tools.
    # Use `tools` and/or `disallowed_tools` for hard availability limits.
    allowed_tools=[
        "mcp__travel__search_flights",
        "mcp__travel__check_travel_policy",
    ],
)


async def main() -> None:
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Book SFO to JFK on 2026-05-10 under $700.")

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        print(block.text)

            if isinstance(message, ResultMessage) and message.subtype == "success":
                print("FINAL:", message.result)


asyncio.run(main())
```

預期結果：助理應該推薦 AS-301，因為它是要求日期的 SFO 到 JFK、票價 $642、可退票。它不該推薦 DL-441，雖然低於 $700，但政策要求可退票的票價。

### Claude 基準版建立了哪些行為

| Behavior                      | Claude implementation                                                                                                                                                                                     | Migration implementation                                                                                                                                                                             |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent instruction hierarchy   | `ClaudeAgentOptions(system_prompt=...)`                                                                                                                                                                   | Move the instructions into `Agent(..., instructions=...)`.                                                                                                                                           |
| Custom business tools         | `@tool(...)` functions registered in `create_sdk_mcp_server(...)`                                                                                                                                         | Move each business action to `@function_tool` with typed parameters and structured return values.                                                                                                    |
| Tool exposure and permissions | `mcp_servers={...}` exposes the custom travel MCP tools. `tools=[...]` would select built-in Claude Code tools if needed. `allowed_tools=[...]` pre-approves matching calls; it doesn't hide other tools. | Put only the OpenAI tools the agent should see in `Agent.tools`. Use approval for side effects. Treat Claude automatic approval as a permission-policy decision, rather than tool-exposure decision. |
| Agent loop                    | `ClaudeSDKClient.query(...)` and `receive_response()`                                                                                                                                                     | Use `Runner.run(...)` and preserve the built-in model/tool loop.                                                                                                                                     |

## 遷移路徑：從 Claude 基準版到 OpenAI

| Claude Agent SDK                          | OpenAI Agents SDK                                                         | Migration-safe rule                                                                                                                                                                            |
| ----------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ClaudeAgentOptions` + `system_prompt`    | `Agent(name, instructions, model, tools)`                                 | Define one responsibility per agent.                                                                                                                                                           |
| `CLAUDE.md`, `.claude/skills/*/SKILL.md`  | `AGENTS.md`, OpenAI skills, agent instructions                            | Map workspace guidance to `AGENTS.md`, reusable procedures to skills, and agent behavior to instructions.                                                                                      |
| `@tool` schema + handler                  | `@function_tool`                                                          | Map business behavior. Use typed parameters and structured return values for business actions.                                                                                                 |
| `tools`, `mcp_servers`, `allowed_tools`   | `Agent.tools` plus approvals where needed                                 | Map tool exposure and approval. Tools and `mcp_servers` expose Claude tools. Expose callable tools through `Agent.tools` and add approval gates for sensitive actions.                         |
| Built-in Read/Edit/Bash/WebSearch         | Hosted tools, `ShellTool`, `ApplyPatchTool`, or sandbox                   | Choose based on execution boundary.                                                                                                                                                            |
| Lifecycle callbacks and permission checks | Callbacks, guardrails, approvals, and filters                             | In OpenAI, `RunHooks` and `AgentHooks` are mainly for lifecycle side effects like logging and tracing. Use guardrails, approvals, or filters when the app needs to block or approve execution. |
| Subagents                                 | `agent.as_tool(...)` or `handoffs=[...]`                                  | Use `agent.as_tool(...)` when the main agent keeps control. Use handoffs when the specialist agent takes over.                                                                                 |
| `query(...)` or `ClaudeSDKClient`         | `Runner.run(...)`                                                         | Keep the built-in SDK loop.                                                                                                                                                                    |
| Claude sessions / client continuity       | `Session`, `previous_response_id`, `conversation_id`, or explicit history | Choose one continuation strategy per conversation.                                                                                                                                             |

### 遷移後的 OpenAI 自訂 tools

業務動作變成 Python 函式。函式名稱、type hints、docstring 和回傳值，就是模型看到的 tool 合約。

```python
from agents import Agent, Runner, function_tool


@function_tool
def search_flights(
    origin: str,
    destination: str,
    date: str,
    max_price_usd: int = 9999,
) -> list[dict]:
    """Search flights for a route and date under a maximum budget."""
    return [
        flight_to_dict(flight)
        for flight in FLIGHTS
        if flight.origin == origin
        and flight.destination == destination
        and flight.date == date
        and flight.price_usd <= max_price_usd
    ]


@function_tool
def check_travel_policy(flight_id: str, max_price_usd: int) -> dict:
    """Check whether a flight is compliant with travel policy."""
    flight = find_flight(flight_id)
    if flight is None:
        return {"flight_id": flight_id, "error": "not_found"}
    return policy_verdict(flight, max_price_usd)
```

### 遷移後的 OpenAI agent 和 run loop

把 `MODEL` 和 `GUARDRAIL_MODEL` 設成任何目前支援 Responses、且支援你的應用所需 Agents SDK 功能的模型。

```python
MODEL = "gpt-5.5"
GUARDRAIL_MODEL = "gpt-5.5-mini"


agent = Agent(
    name="Flight Booking Assistant",
    model=MODEL,
    instructions=(
        "You help users evaluate flight options. "
        "Always search flights and check travel policy before recommending. "
        "Recommend a compliant option when one exists. "
        "If no compliant option exists, recommend escalation instead. "
        "Do not purchase tickets or charge a card."
    ),
    tools=[search_flights, check_travel_policy],
)

result = await Runner.run(
    agent,
    "Book SFO to JFK on 2026-05-10 under $700.",
)
print(result.final_output)
```

預期結果：助理應該推薦 AS-301，因為它是要求日期的 SFO 到 JFK、票價 $642、可退票。它不該推薦 DL-441，雖然低於 $700，但政策要求可退票的票價。

## 逐步遷移

### Step 1：定義第一個 OpenAI agent

如果原本一個 Claude agent 從頭到尾處理單一任務，通常就對應一個 OpenAI Agent。

以訂機票為例：

- **Agent：** Flight Booking Assistant
- **職責：** 搜尋航班、檢查政策，並建議訂票或升級處理。

### Step 2：移植自訂 tools

照這個順序移植自訂 tools：

1. 業務動作本身保持不變。
2. 收緊函式簽章。
3. 寫 docstring 說明什麼時候該用這個 tool。
4. 回傳 agent 能檢視的結構化資料。

預設規則：

依行為對應自訂 tools。`search_flights`、`check_travel_policy` 這類領域動作變成 `@function_tool` 函式。通用的檔案或 shell 基本操作，不要移植成自訂業務 tools。

### Step 3：依執行邊界對應內建 tools

Claude 應用常會開放檔案/bash tools。遷移時不要把它們做成自訂業務 tools。

業務或領域動作用 `@function_tool`。OpenAI 代管的檢索或執行用 hosted tools。偶爾需要本機/runtime 動作時用 `ShellTool` 或 `ApplyPatchTool`。任務需要隔離的 workspace 時，用 `SandboxAgent` 搭配 sandbox capabilities。

| Claude capability                              | OpenAI migration                                                                                                                                                |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Web search or external lookup                  | Use `WebSearchTool` for web search, `HostedMCPTool` for remote MCP tools, or a typed `@function_tool` when the lookup is a business-system action.              |
| Retrieval over indexed files or knowledge base | Use `FileSearchTool` for retrieval over OpenAI vector stores.                                                                                                   |
| Business system call                           | Use `@function_tool` or MCP in the trusted runtime.                                                                                                             |
| Shell command or script                        | Use hosted/local `ShellTool` for occasional shell access. Use [`SandboxAgent`](https://developers.openai.com/api/docs/guides/agents/sandboxes) with `Shell()` when commands should run inside an isolated or resumable workspace. |
| File read, edit, or search                     | Use [`SandboxAgent`](https://developers.openai.com/api/docs/guides/agents/sandboxes) with `Shell()` and, when needed, `Filesystem()` for workspace file inspection, search, or generated artifacts.                               |
| Patch or code edit                             | Use [`SandboxAgent`](https://developers.openai.com/api/docs/guides/agents/sandboxes) with `ApplyPatch()` and `Shell()` for sandbox code edits and validation. Use `ApplyPatchTool` when implementing outside a sandbox.           |

注意：如果 Claude 應用自己定義了 `read_file`、`write_file`、`grep_files`、`run_bash` 這類 helper，不要 1:1 移植。把檔案讀取、編輯、搜尋和 shell 指令，對應到最接近的 OpenAI 內建 tool，並搭配 sandbox workspace。

### Step 4：把驗證搬到對的 guardrail 邊界

如果你的 Claude 應用靠 hooks 來擋動作、要求核准或改變執行行為，就把這些邏輯對應到合適的 OpenAI 做法：guardrails、approvals 或 hooks。

在 run 開始前、tool 執行前、最終回答送出前需要做的驗證，用 guardrails。

| Need                                                   | OpenAI boundary                |
| ------------------------------------------------------ | ------------------------------ |
| Incoming request must contain route, date, and budget  | Input guardrail.               |
| Final answer must include recommendation or escalation | Output guardrail.              |
| Tool call must obey parameter constraints              | Tool guardrail.                |
| Action changes production state or spends money        | Approval and run-state resume. |

範例：在 tools 執行前，要求訂票的必要欄位都齊全。

先定義 guardrail，再掛到訂機票 agent 上。把 guardrail 設成 blocking 模式，就會在主 agent 能呼叫任何 tool 之前先檢查請求。input guardrails 預設是跟主 agent 平行跑，延遲比較低。這裡設 `run_in_parallel=False`，因為這個驗證必須先完成，agent 才能開始用 tool。

```python
from pydantic import BaseModel
from agents import (
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    input_guardrail,
)


class BookingRequestCheck(BaseModel):
    is_flight_booking_request: bool
    has_route: bool
    has_date: bool
    has_budget: bool
    reasoning: str


booking_guardrail_agent = Agent(
    name="Booking request guardrail",
    model=GUARDRAIL_MODEL,
    instructions=(
        "Decide whether the user is asking for a flight-booking recommendation. "
        "The request is ready only if it includes a route, travel date, and budget."
    ),
    output_type=BookingRequestCheck,
)


@input_guardrail(run_in_parallel=False)
async def require_ready_booking_request(
    ctx: RunContextWrapper[None],
    agent: Agent,
    user_input: str | list[TResponseInputItem],
) -> GuardrailFunctionOutput:
    result = await Runner.run(
        booking_guardrail_agent,
        user_input,
        context=ctx.context,
    )
    check = result.final_output
    ready = (
        check.is_flight_booking_request
        and check.has_route
        and check.has_date
        and check.has_budget
    )
    return GuardrailFunctionOutput(
        output_info=check,
        tripwire_triggered=not ready,
    )


agent = Agent(
    name="Flight Booking Assistant",
    model=MODEL,
    instructions=(
        "You help users evaluate flight options. "
        "Always search flights and check travel policy before recommending. "
        "Recommend a compliant option when one exists. "
        "If no compliant option exists, recommend escalation instead. "
        "Do not purchase tickets or charge a card."
    ),
    tools=[search_flights, check_travel_policy],
    input_guardrails=[require_ready_booking_request],
)
```

### Step 5：決定多 agent 的歸屬

兩種典型模式：

- manager agent 要保持最終回應的所有權時，用 `agent.as_tool(...)`。
- 專家要接手並負責最終回應時，用 `handoffs=[...]`。

關鍵問題是歸屬。

#### 模式 A：專家當成 tool

主 orchestrator agent 要保持控制權時用這個模式。專家以 tool 的形式執行，回傳一個精簡的結果，由 orchestrator 決定下一步以及怎麼回答使用者。
```python
from agents import Agent, ModelSettings, Runner


pricing_specialist = Agent(
    name="Pricing Specialist",
    model=MODEL,
    instructions="Analyze candidate flights and return a short pricing verdict.",
)

manager = Agent(
    name="Travel Manager",
    model=MODEL,
    instructions=(
        "Call pricing_tool first, then give the final customer-facing recommendation yourself."
    ),
    tools=[
        pricing_specialist.as_tool(
            tool_name="pricing_tool",
            tool_description="Analyze flight pricing and policy fit.",
        )
    ],
    model_settings=ModelSettings(tool_choice="required"),
)

# Expected final owner: Travel Manager.
```

#### 模式 B：handoff 給專家

專家 agent 要接手時用這個模式。orchestrator 把對話 handoff 出去，專家接著負責後續步驟和最終回應。

```python
booking_specialist = Agent(
    name="Booking Specialist",
    model=MODEL,
    instructions="You own final flight-booking recommendations once transferred.",
)

triage = Agent(
    name="Travel Triage",
    model=MODEL,
    instructions="Always hand off flight-booking tasks to Booking Specialist.",
    handoffs=[booking_specialist],
    model_settings=ModelSettings(tool_choice="required"),
)

# Expected final owner: Booking Specialist.
```

### Step 6：選一種對話狀態策略

| Strategy               | Use when                                                                 |
| ---------------------- | ------------------------------------------------------------------------ |
| `session`              | You want to persist local conversation history.                          |
| `previous_response_id` | You continue from the immediate previous response.                       |
| `conversation_id`      | You want server-managed durable conversation state.                      |
| Explicit input history | You want your application to fully control which prior items to include. |

重要區別：對話延續是把 context 帶進新的一輪；run-state resume 是讓被中斷的同一個 run 接著跑。

### Step 7：副作用動作加上人工 approval

動作需要人工核准時用 approvals，例如刷卡、刪資料、改動 production 狀態。

Approval 的生命週期：

1. Run 跑到需要核准的地方。
2. Run 暫停。
3. 中斷事項（interruptions）浮現，等人審查。
4. 應用核准或拒絕。
5. 同一個 run 從 RunState 繼續。

```python
@function_tool(needs_approval=True)
async def add_checked_bag(booking_id: str, bags: int) -> dict:
    """Add checked bags to an existing booking after human approval."""
    return {
        "booking_id": booking_id,
        "bags_added": bags,
        "status": "submitted",
    }


first = await Runner.run(agent, "Add one checked bag to booking AS-301.")
state = first.to_state()

for interruption in first.interruptions:
    state.approve(interruption)  # or state.reject(interruption)

resumed = await Runner.run(agent, state)
print("FINAL:", resumed.final_output)
```

## 最終驗證清單

組成完整應用之前，先一個一個積木檢查遷移結果。

| Area                  | Pass condition                                                                                                                                                              |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agent boundary        | One clear responsibility maps to one OpenAI agent.                                                                                                                          |
| Custom tools          | Typed parameters, clear function documentation, structured returns; generic file/shell primitives map to `ShellTool` / `ApplyPatchTool` (or sandbox), not 1:1 custom tools. |
| Built-in tool mapping | Each tool has an explicit execution boundary.                                                                                                                               |
| Built-in loop         | `Runner.run(...)` handles the normal model/tool loop.                                                                                                                       |
| Guardrails            | Complete requests pass; incomplete inputs trigger the expected guardrail.                                                                                                   |
| Multi-agent ownership | `agent.as_tool(...)` preserves parent ownership; handoff transfers ownership.                                                                                               |
| Continuation          | Prior turns carry through the chosen strategy consistently.                                                                                                                 |
| Approvals             | Approval-gated actions pause, surface interruptions, then resume or reject cleanly.                                                                                         |
| [Sandbox](https://developers.openai.com/api/docs/guides/agents/sandboxes) | Agent access stays limited to the intended workspace and execution surface.                                                                                                 |
| Lifecycle callbacks   | Logging and tracking callbacks map to `RunHooks` or `AgentHooks`. Callbacks that block, approve, or reshape execution map to guardrails, approvals, or filters.             |
| Subagents             | Each subagent maps to `agent.as_tool(...)` or `handoffs=[...]` with explicit ownership.                                                                                     |
| End-to-end behavior   | The migrated app preserves original Claude business behavior.                                                                                                               |

## 建議的測試順序

1. 用遷移好的自訂 tools 跑基準 agent。
2. 加上 input 和 output guardrails。
3. 只在需要的地方加 tool 層級的檢查。
4. 加入專家 agents。
5. 用 `agent.as_tool(...)` 或 `handoffs=[...]` 檢查歸屬。
6. 加上對話延續。
7. 加上副作用的 approvals。
8. 如果流程需要隔離，再加 sandbox。
9. 把 Claude 和 OpenAI 的情境並排跑。
10. 比較最終回答品質、tool calls、安全行為和狀態處理。

## 結論

成功的遷移會保留業務任務，只更新執行模型。

- **需要隔離的地方才加 sandbox。**
  OpenAI 的 Agents SDK 把受信任的應用和執行風險或有狀態工作的 workspace 分開。agent 需要限定範圍的檔案、指令執行、artifacts 或可恢復的 workspace 狀態時，才用 sandbox。

- **業務動作遷移成明確的 tools。**
  搜尋航班、建立 ticket 這類動作，要變成有型別輸入、輸出可預期的業務 tools。不要把通用的 shell 或檔案存取重建成業務 tools。

- **tool 存取和 approvals 分開處理。**
  在 Claude 裡，選 tool 和預先核准看起來有關聯。在 OpenAI 的模型裡，先決定 agent 看得到哪些 tools，再為需要人工審查的動作加 approval 檢查。

- **guardrails 和 approvals 各司其職。**
  guardrails 用來檢查請求和輸出。approvals 用來暫停有風險的副作用。lifecycle callbacks 用在 logging、tracing 和 audit 事件。

- **多 agent 歸屬：主 agent 要繼續負責時用 `agent.as_tool(...)`。**
  專家要負責最終回應時用 `handoffs=[...]`。

## 重點整理

- 最大的架構差異是 Claude 的 harness 在 sandbox 裡，OpenAI 的 harness 跟 compute 分離，secrets、approvals 和業務系統存取都留在受信任的 runtime。
- 遷移是依行為對應，不是 1:1 翻譯：業務動作變 `@function_tool`，通用檔案/shell 操作改用 `ShellTool`、`ApplyPatchTool` 或 sandbox。
- 工具開放和核准是兩件事。先決定 `Agent.tools` 讓 agent 看到什麼，再用 approvals 管副作用。
- Claude hooks 要依用途拆開：logging 去 `RunHooks`/`AgentHooks`，要擋或核准的邏輯去 guardrails、approvals 或 filters。
- 多 agent 的關鍵是歸屬：`as_tool` 讓主 agent 保留最終回應，`handoffs` 讓專家接手。

## 練習

1. 在範例的政策規則和資料裡，把預算上限改成 $600，跑一次看助理會推薦 AS-301 還是改成建議 escalation，確認結果符合預期。
2. 在 `search_flights` 的 `@function_tool` 版本裡，修改 docstring，加上「預算沒給時不要呼叫」這類使用時機說明，觀察模型的 tool 呼叫有沒有變化。
3. 把 Step 4 的 input guardrail 的 `run_in_parallel=False` 改成 `True`，比較兩種設定下，缺少日期的請求有沒有已經先呼叫了 tool。
