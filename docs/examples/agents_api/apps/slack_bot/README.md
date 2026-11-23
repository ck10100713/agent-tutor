---
translated: true
source: examples/agents_api/apps/slack_bot/README.md
---
# 用 Agents API 做一個 Slack bot

> 原文：[examples/agents_api/apps/slack_bot/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/README.md)

把 Slack thread 接到持久的 agent session、工作場所的 tool 和隔離的 sandbox。

## 這篇在做什麼

在 Slack 裡 tag 這個 bot，就能請它搜尋對話、調查專案、分析資料，或準備 GitHub pull request。每個 Slack thread 都有自己的 Agents API session 和隔離的工作空間，後續追問可以接著之前的調查繼續。

## 學完你會

- 把 Slack thread 對應到 Agents API session，讓追問能延續上下文
- 建立 session、掛上 Docker sandbox，並把 agent 的進度串流回 Slack
- 設定範圍受限的 Slack tool 和 Notion、Google Drive、GitHub 的 MCP 連線，並在對話結束時清理資源

## 開跑前

- Python 3.14+ 和 `uv`
- Sandbox：自架 Docker，或第三方 provider
- OpenAI API key，加上一組權限受限的 executor key（需要 `api.agents.environments.connect`）
- 一個你有權限安裝 internal app 的 Slack workspace
- 選用：Notion、Google Drive、GitHub 的憑證


Tag 你的 bot，就能搜尋對話、調查專案、分析資料，或準備 GitHub pull request。每個 Slack thread 都有自己的 Agents API
session 和隔離的工作空間。

## 為什麼用 Agents API？

Slack 提供觸發和介面。Agents API 把對話和 tool 結果保存在 session 裡、執行 agent，並串流它的進度。你的
應用程式控制 Slack 存取、工作場所憑證和 sandbox
生命週期。後續追問可以延續調查，不用重複原本的 context。

![Slack bot workflow: create or resume a thread session, search connected tools, work in a sandbox, and respond to follow-up requests.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_api/apps/slack_bot/assets/workflow.svg)

## 需要準備什麼

- Python 3.14+ 和 `uv`。
- 一個 sandbox：自架 Docker，或[第三方 provider](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#sandbox-providers)。
- 一組 OpenAI API key，和另一組權限受限的 executor key。
- 一個你可以安裝 internal application 的 Slack workspace。

## 1. Build sandbox image

在 repository 根目錄執行：

```bash
cp examples/agents_api/apps/slack_bot/.env.example examples/agents_api/apps/slack_bot/.env
docker build -t agent-api-sandbox:latest examples/agents_api/sandboxes/docker/application_managed
```

在 `examples/agents_api/apps/slack_bot/.env` 設定 `OPENAI_API_KEY` 和 `OPENAI_EXECUTOR_API_KEY`。兩把 key 要有相同的擁有者、組織和 project。只有 executor key 會進到 sandbox。它需要 `api.agents.environments.connect` 權限，以及允許 sandbox 對外網路的 IP 限制。應用程式會自動載入這個檔案。

要建立有所需權限的 executor key，打開 [Agents > Environments > Keys](https://platform.openai.com/agents?tab=environments&environment_view=keys) 並選 **Create**。

正式環境可以把 Docker 換成代管的 [sandbox provider](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#sandbox-providers)。

## 2. 建立 Slack app

1. 用 `examples/agents_api/apps/slack_bot/slack-app-manifest.yaml` 建立 app。
2. 把它安裝到你的 workspace，並複製 **Bot User OAuth Token**。
3. 建立一個有 `connections:write` scope 的 app-level token。

把兩個 token 都加到 `examples/agents_api/apps/slack_bot/.env`：

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

啟動 bot：

```bash
uv run examples/agents_api/apps/slack_bot/main.py
```

Socket Mode 不需要公開的 webhook 或 OAuth callback 就能接收訊息。
bot 只能讀它所屬的對話。

## 3. 在 Slack tag bot

把 bot 邀請進頻道，然後 mention 它：

```text
@Agent Teammate Summarize this week's launch decisions and find the owner.
```

在同一個 Slack thread 追問：

```text
Find the related GitHub issue and explain the likely cause.

Reproduce the problem, prepare a fix, and open a pull request.

Only include customer-facing changes.
```

第一則訊息會建立一個 `self_hosted` Agents API session，並啟動一個執行 `codex exec-server` 的 Docker
container。後續回覆會沿用同一個 session 和工作空間。送出 `stop` 可以取消進行中的 request。

## 跟著看實作

下面的片段展示 [main.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/main.py)、[agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/agent.py)
和 [connections.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/connections.py) 的主要步驟。完整的
事件處理和清理邏輯請執行上面的應用程式，這些片段不是另一個應用。

### 1. 把每個 Slack thread 對應到一個 session

用 workspace、channel 和原始訊息的 timestamp 當作對話的
key。同一個 thread 裡的後續 mention 會沿用這個 key。

```python
@app.event("app_mention")
async def on_mention(event, context, say):
    thread_ts = event.get("thread_ts") or event["ts"]
    thread_id = f"{context.team_id}:{event['channel']}:{thread_ts}"
    answer = await bot.answer(
        event["text"],
        thread_id=thread_id,
        team_id=context.team_id,
        channel_id=event["channel"],
    )
    await say(text=answer, thread_ts=thread_ts)
```

可執行的 handler 還會移除 bot 自己的 mention、忽略重複送達的事件，並把進行中 request 期間收到的訊息，
導向 steering 或取消。

### 2. 給 agent 範圍受限的 tool

Slack tool 在你的應用程式裡用 bot token 執行。[tools.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/tools.py)
提供四個函式：`search_slack_messages`、`read_slack_channel`、
`find_teammate` 和 `list_slack_files`。訊息和檔案的存取綁定在
觸發 request 的 channel，不是由模型選的 channel。

例如搜尋 tool 會過濾 channel 最近的訊息：

```python
async def search_slack_messages(arguments):
    response = await slack.conversations_history(channel=channel_id, limit=100)
    query = arguments["query"].casefold()
    return {
        "messages": [
            message for message in response["messages"]
            if query in message.get("text", "").casefold()
        ][:20]
    }
```

這是搜尋最近的歷史紀錄，不是整個 Slack workspace。選用的 Notion、
Google Drive 和 GitHub 連線改用服務連接的 MCP tool。
設定方式請看[連接共用的工作場所工具](#connect-shared-workplace-tools)。

### 3. 建立 session 並掛上它的 sandbox

`Connections.get()` 會回傳 workspace 的 tool 定義和選用的 vault。
建立 session 一次，然後把它的 ID 存在 thread key 底下。

```python
from openai import AsyncOpenAI
from examples.agents_api.apps.slack_bot.connections import Connections

client = AsyncOpenAI()
connections = Connections(client)
vault_id, tools = await connections.get(team_id)

instructions = """\
Search connected tools and cite the records behind your answer.
Use your workspace to analyze data, inspect repositories, and prepare changes.
Change external systems only when the user explicitly asks.
Delegate complex investigations when helpful.
"""

session = await client.beta.agents.sessions.create(
    agent={
        "model": "gpt-5.6-sol",
        "instructions": instructions,
        "reasoning": {"effort": "medium"},
        "multi_agent": {"enabled": True, "max_concurrent_subagents": 3},
        "tools": tools,
    },
    environment={"type": "self_hosted", "workspace_directory": "/workspace"},
    vault_ids=[vault_id] if vault_id is not None else [],
)
sessions[thread_id] = session.id
```

用回傳的連線 URL 和 environment ID 啟動 `codex exec-server`。
只有權限受限的 executor key 會進到 container。

```python
import asyncio
import os
import docker

environment = session.environment
assert environment.type == "self_hosted"
container = await asyncio.to_thread(
    docker.from_env().containers.run,
    "agent-api-sandbox:latest",
    [
        "codex", "exec-server",
        "--remote", environment.remote_url,
        "--environment-id", environment.id,
    ],
    environment={"CODEX_API_KEY": os.environ["OPENAI_EXECUTOR_API_KEY"]},
    detach=True,
    auto_remove=True,
    init=True,
)
```

### 4. 把調查過程串流到 Slack

啟動 turn 時傳入應用程式的 handler。SDK 會對 function call 執行這些 handler，
Agents API 則處理服務連接的 MCP tool。

```python
from examples.agents_api.apps.slack_bot.tools import slack_handlers

parts = []
async with client.beta.agents.sessions.stream(
    session.id,
    input=question,
    tool_handlers=slack_handlers(slack, channel_id),
) as events:
    async for event in events:
        if event.type == "agent.session.turn.output_text.delta":
            parts.append(event.delta)
        elif event.type in {"agent.session.failed", "agent.session.turn.failed", "error"}:
            raise RuntimeError(f"Investigation failed: {event.to_dict()}")

await slack.chat_postMessage(
    channel=channel_id, thread_ts=thread_ts, text="".join(parts),
)
```

應用程式也用 `agent.session.turn.item.added` 和
`agent.session.subagent.created`，在 tool 和 specialist 工作時更新同一則進度訊息。
它不會把每個 text delta 都當成新的 Slack 訊息發出去。

### 5. 繼續、steer 或取消

thread 閒置時，用存好的 session ID 啟動另一個 stream。進行中的 turn 期間，
送一個 message event 來 steer 現有的工作：

```python
await client.beta.agents.sessions.events.create(
    sessions[thread_id],
    events=[{
        "type": "agent.session.input.message",
        "input": [{
            "role": "user",
            "content": [{"type": "input_text", "text": "Only include launch blockers."}],
        }],
    }],
)
```

如果是 `stop`，改送 `{"type": "agent.session.input.cancel"}`。取消
結束的是進行中的 turn，不是整段對話，之後的 request 還是會沿用 session
和工作空間。

### 6. 釋放對話佔用的資源

sandbox 留著給後續追問用，等對話過期，再刪除 session 並移除
container。[SlackBot.close()](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/agent.py) 會在應用程式關閉時做這件事。
部署長時間執行的 bot 時，要加上過期政策。

```python
try:
    await client.beta.agents.sessions.delete(session.id)
finally:
    await asyncio.to_thread(container.remove, force=True)
```

清理完所有對話後，再關閉 OpenAI client。這個範例把 session ID、
sandbox handle 和 thread 對應都放在記憶體裡。如果對話需要撐過應用程式重啟，
就要把它們持久化。

## 連接共用的工作場所工具

bot 已經有搜尋目前 Slack channel、讀取最近
訊息、找同事和列出共用檔案的 tool。把任何選用的共用
工作場所憑證加到 `.env`：

```bash
NOTION_TOKEN=...
GOOGLE_DRIVE_TOKEN=...
GITHUB_TOKEN=...
```

應用程式會把設定好的憑證存在 Slack
workspace 共用的一個 vault 裡，並連接對應的 MCP server：

- Notion: `https://mcp.notion.com/mcp`
- Google Drive: `https://drivemcp.googleapis.com/mcp/v1`
- GitHub: `https://api.githubcopilot.com/mcp/`

例如 vault 存 GitHub token，tool 定義裡只放
server URL。把 vault ID 加到 session 的 `vault_ids`：

```python
vault = await client.beta.agents.vaults.create(
    name="Slack integrations",
    metadata={"slack_team_id": team_id, "owner": "slack_bot"},
)
await client.beta.agents.vaults.credentials.create(
    vault.id,
    name="GitHub",
    auth={
        "type": "static_bearer",
        "mcp_server_url": "https://api.githubcopilot.com/mcp/",
        "token": os.environ["GITHUB_TOKEN"],
    },
)
github_tool = {
    "type": "mcp",
    "server_label": "github",
    "connection_origin": "service",
    "transport": {"type": "http", "server_url": "https://api.githubcopilot.com/mcp/"},
}
```

把 `github_tool` 加到 agent 的 tools。可執行的應用程式會找到並重複使用它的
workspace vault，不會為每個 thread 都建一個。

Notion 和 Google Drive 需要共用帳號的 OAuth access token，
Notion 的代管 MCP server 不接受 internal integration secret。GitHub
接受範圍適當的 personal access token。所有能用這個 bot 的人
都共用這些連線，所以只讓這個帳號存取預定給該群人的文件和
repository。開 pull request 也需要有必要 repository 權限的
GitHub 憑證。

### 讓 Agents API 更新 Google Drive 存取權

透過你的 [Google OAuth app](https://developers.google.com/identity/protocols/oauth2/web-server#offline) 取得授權，要求 offline access，且只要求 bot 需要的 Drive scope。把授權加到 `.env`：

```bash
GOOGLE_DRIVE_TOKEN=...
GOOGLE_DRIVE_REFRESH_TOKEN=...
GOOGLE_DRIVE_CLIENT_ID=...
GOOGLE_DRIVE_CLIENT_SECRET=...
GOOGLE_DRIVE_TOKEN_EXPIRES_AT=2026-09-01T12:00:00Z
```

填入 access token 實際的到期時間，不知道的話就留空。bot 會建立一個 `mcp_oauth` vault 憑證，帶有 Google 的 token endpoint 和 refresh 設定。Agents API 會在需要時更新 access token，初始的同意流程由你的應用程式負責。

重啟 bot 時會重複使用已存的 OAuth 憑證，不會用 `.env` 裡的舊值覆蓋已更新的 token。如果這個 workspace 已經有靜態的 Google Drive 憑證，改用 OAuth refresh 之前要先封存它一次。要更新或撤銷既有的授權，請透過 vault 憑證 API，改 `.env` 不會取代它。

## 檔案

- [main.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/main.py)：Slack 事件和應用程式啟動。
- [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/agent.py)：Agent session、sandbox、串流和清理。
- [tools.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/tools.py)：Slack 搜尋、channel、同事和檔案 tool。
- [connections.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/slack_bot/connections.py)：MCP 連線和 vault 憑證。

## 重點整理

- 一個 Slack thread 對應一個 Agents API session，用 workspace、channel 和原始訊息 timestamp 當 key，追問就能延續上下文。
- Slack 只是觸發和介面，session、agent 執行和串流由 Agents API 負責，憑證和 sandbox 生命週期由你的應用程式控制。
- 只有權限受限的 executor key 進 sandbox，Slack tool 的存取範圍綁在觸發的 channel，而不是讓模型自己選。
- 進行中的 turn 可以 steer 或取消，取消只結束該 turn，session 和工作空間還在。
- 對話結束要刪 session、移除 container。範例的狀態都在記憶體裡，需要撐過重啟就得自己持久化。

## 練習

1. 照 README 設好 `.env` 並啟動 bot，在頻道 tag 它問一個問題，再在同一個 thread 追問，確認它有接續上下文。
2. 在 `tools.py` 的搜尋 tool 裡，調整它過濾的最近訊息數量，看搜尋結果怎麼變。
3. 設定 `GitHub` 憑證，把 `github_tool` 加進 agent 的 tools，請 bot 讀一個 repository 的內容。
