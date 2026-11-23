---
translated: true
source: managed_agents/CMA_operate_in_production.ipynb
---
# Managed Agents 教學：正式環境設定

> 原文：[managed_agents/CMA_operate_in_production.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_operate_in_production.ipynb)

Managed Agents 的正式環境完整流程：以 vault 保存的 MCP 憑證、用 session.status_idled webhook 做 human-in-the-loop 而不用長連線、session.budget_reached webhook、用 inference_geo 釘住資料居留區域，以及資源生命週期的 CRUD 動詞。

## 這篇在做什麼

其他 Managed Agents 的 cookbook 都專注在 agent loop 本身，這篇講的是 loop 周邊的機制：把 Managed Agents 應用放到真實使用者面前之前需要的東西。流程是替一個虛構的終端使用者建 vault、掛上 GitHub MCP 憑證、跑一個在 server 端使用該憑證的 session，再示範正式 server 該註冊的 webhook handler，最後用管理動詞收尾清理。

## 學完你會

- 建立 per-user 的 vault 並附上 MCP 憑證，讓 agent 用該使用者的 token 呼叫 GitHub，而 token 不經過你的程式
- 說明為什麼正式環境的 human-in-the-loop 該用 `session.status_idled` webhook，並看懂 handler 的結構
- 用 `inference_geo` 釘住推論區域，並用 list / retrieve / update / archive / delete 管理資源

## 開跑前

需要 `GITHUB_TOKEN` 環境變數，另外要有 Managed Agents beta 權限的 Anthropic API key。webhook 要在 Console 的 **Settings → Webhooks** 註冊。

其他 Managed Agents 的 cookbook 大多專注在 agent loop 本身，讓 agent 對著一個測試用素材做點有用的事。這篇講的是 loop 周邊的機制，也就是把 Managed Agents 應用放到真實使用者面前之前需要的東西：

1. **MCP toolsets**：用來取代 custom tools，當你的 agent 需要跟 SaaS API 溝通，又不想每次呼叫都繞回你的應用程式時。
2. **Vaults**：保存每個終端使用者的憑證，讓每個人的 GitHub / Linear / Slack token 跟其他人分開，稽核紀錄也乾淨。
3. **Webhooks**：驅動 human-in-the-loop 的工作，不用整段時間都開著長連線的 HTTP。
4. **資源生命週期**動詞（list、retrieve、update、archive、delete）：管理 workspace 隨時間累積的東西。
5. **推論地理位置釘選**（`inference_geo`）：合規要求模型請求要在特定區域執行時使用。

我們會建一個端到端的流程，涵蓋前四項，最後再講地理釘選：替一個虛構的終端使用者建 vault、附上 GitHub MCP 憑證、跑一個在 server 端使用該憑證的 agent session、展示你會在正式 server 註冊的 webhook handler 來驅動同一個 session，並走過事後清理會用的管理動詞。

這個 notebook 需要在環境變數裡有 `GITHUB_TOKEN`。

```python
import os

from anthropic import Anthropic
from utilities import stream_until_end_turn, wait_for_idle_status

MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
client = Anthropic()

GH_TOKEN = os.environ.get("GITHUB_TOKEN")
if not GH_TOKEN:
    raise SystemExit("Set GITHUB_TOKEN to run this notebook.")
```

## 概念：MCP toolsets 和 vaults

**MCP toolsets** 是第三種擴充模式，前兩種是 custom tools（gate notebook）和 `resources=` 掛載（orchestrate notebook）。MCP toolset 讓 agent 指向一個實作 [Model Context Protocol](https://modelcontextprotocol.io/) 的外部 server。agent 在 sandbox 裡直接呼叫那個 server 上的 tools，不繞回你的應用程式：Anthropic 代理呼叫、server 回應、agent 繼續做事。絕大多數公開的 SaaS API（GitHub、Slack、Linear、Stripe、Notion、Salesforce、Asana⋯）要嘛已經有 MCP server，要嘛一個下午就能包出一個，都很適合用 MCP。

經驗法則：如果服務能透過公開網路加 bearer token 連到，MCP toolset 就行得通。如果只能從你自己的網路內部連到，就改用 custom tool，那是 gate notebook 講的。

**Vaults** 回答的是「token 要放哪裡？」這個問題。在建立 session 時寫死單一個 token，對單一租戶的設定可行，但一有終端使用者就行不通了。每個使用者需要自己的 GitHub 憑證，而且你要讓他們彼此隔離。vault 是每個使用者一個的憑證容器，你註冊一次，之後替那個使用者建的每個 session 都用 ID 參照它。你不用自己維護密鑰儲存、不用每個請求都傳 token，稽核紀錄也綁在 vault 上，所以永遠知道 agent 是代表哪個終端使用者在行動。

## 1. 替終端使用者建立 vault

vault 有一個 `display_name`，會顯示在 Console，還有一個 `metadata` dict，通常你會放自己的內部使用者 ID，這樣能把 vault 對回你資料庫裡的紀錄。

```python
vault = client.beta.vaults.create(
    display_name="Cookbook demo user",
    metadata={"internal_user_id": "u_demo_001", "team": "engineering"},
)
print(f"vault: {vault.id}")
```

## 2. 附上 MCP 憑證

憑證存放在 vault 底下。每個憑證把一個 MCP server URL 和 agent 呼叫那個 server 時用的 token 配成一對。對 GitHub Copilot MCP server 來說，最簡單的形式是靜態 bearer token（你的 GitHub PAT）。API 也支援需要 refresh 的完整 OAuth 流程，兩種形式都透過 `auth=` 處理。

```python
credential = client.beta.vaults.credentials.create(
    vault_id=vault.id,
    display_name="GitHub Copilot",
    auth={
        "type": "static_bearer",
        "mcp_server_url": "https://api.githubcopilot.com/mcp/",
        "token": GH_TOKEN,
    },
)
print(f"credential: {credential.id}")
```

## 3. 在 session 上參照 vault

在 `sessions.create` 傳 `vault_ids=[vault.id]`，API 在每次 tool 呼叫時會查出對應的 MCP server URL。agent 本身不會看到 token，你也不用在請求中傳它。agent 定義照常列出 MCP server 就好，憑證的串接是在 session 建立時完成。

```python
agent = client.beta.agents.create(
    name="cookbook-operate",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-operate-in-production"},
    model=MODEL,
    system="You navigate GitHub repositories on behalf of the logged-in user.",
    mcp_servers=[
        {
            "type": "url",
            "name": "github",
            "url": "https://api.githubcopilot.com/mcp/",
        }
    ],
    tools=[
        {
            "type": "mcp_toolset",
            "mcp_server_name": "github",
            "default_config": {
                "enabled": True,
                "permission_policy": {"type": "always_allow"},
            },
        }
    ],
)

env = client.beta.environments.create(
    name="cookbook-operate-env",
    config={"type": "cloud", "networking": {"type": "unrestricted"}},
)

session = client.beta.sessions.create(
    environment_id=env.id,
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    vault_ids=[vault.id],
    title="Operate demo",
)
print(f"session: {session.id}")
```

## 4. 以終端使用者身分跑一輪

agent 現在對 GitHub 做的一切都會走 vault 的憑證。在你自己的系統裡做稽核很直接：你確切知道是哪個終端使用者在行動，因為 vault 透過你在步驟 1 設的 metadata 綁到他們身上。

```python
client.beta.sessions.events.send(
    session_id=session.id,
    events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": "List the three most recently updated repos in the anthropics org.",
                }
            ],
        }
    ],
)
print("--- vault-backed MCP call ---")
stream_until_end_turn(client, session.id)
```

## 5. 正式環境 HITL 用 Webhooks

gate notebook 裡的串流模式在開發時很方便，因為一切都在同一個 process 裡發生，但它在人類 review 期間要一直開著 HTTP 連線，這樣擴展不了，也撐不過 process 重啟。正式環境的做法是在 Console 註冊一個 webhook，在 `session.status_idled` 觸發，這個訊號代表 agent 做完了，或是在等 tool result。

webhook 觸發時，你的 server 檢查事件，把待處理的 escalation 交給 reviewer，等人類處理完再 POST `user.custom_tool_result` 回去。session 就靜靜待機直到你回應，你這邊不需要任何長連線。

如果你的 session 有跑 `budget`（見 [`CMA_cap_session_spend.ipynb`](CMA_cap_session_spend.md)），也要註冊 `session.budget_reached`。它在 session 的 list cost 達到上限時觸發一次，是 supervisor process 需要用來決定每個 session 要提高上限還是維持暫停的訊號。它帶著 session id，所以 handler 的形狀跟 idle 那個一樣：查出 session、決定、行動。

webhook 的註冊是在 Console 的 **Settings → Webhooks** 一次性完成。你會拿到一個 `whsec_...` 簽章密鑰，只在建立時顯示一次，要存進你的 secrets manager。

**下面這段是參考實作，不是 notebook 的 cell。** 請複製到你自己的 server，它依賴 FastAPI（cookbook 沒有安裝），也不會在這個 notebook 的流程裡執行。搭配 gate notebook 的 agent 定義，就足以從正式 server 端到端驅動 gate 工作流程。

```python
import hmac
import hashlib
import json

from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI()
WEBHOOK_SECRET = "whsec_..."  # from Console, load from your secrets manager


def verify(body: bytes, sig: str) -> bool:
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


@app.post("/webhooks/anthropic")
async def receive(req: Request, x_anthropic_signature: str = Header()):
    body = await req.body()
    if not verify(body, x_anthropic_signature):
        raise HTTPException(401)

    event = json.loads(body)
    session_id = event["resource_id"]

    if event["event_type"] == "session.status_idled":
        # Agent went idle. Either it's done OR it called escalate()
        # and is waiting on a user.custom_tool_result. Look at the
        # latest events to decide.
        events = client.beta.sessions.events.list(session_id=session_id)
        pending = [
            e for e in events.data
            if e.type == "agent.custom_tool_use" and e.name == "escalate"
            and not has_result(events, e.id)
        ]
        if pending:
            for tu in pending:
                enqueue_for_review(session_id, tu.id, tu.input)
        else:
            finalize_run(session_id)

    elif event["event_type"] == "session.budget_reached":
        # Session paused at its spend cap with its work intact. Raise
        # the budget to let it continue, or leave it paused and page
        # an operator.
        review_budget(session_id)

    return {"ok": True}


# Called from your review UI once the human decides
def submit_review(session_id: str, custom_tool_use_id: str, decision: str):
    client.beta.sessions.events.send(
        session_id=session_id,
        events=[{
            "type": "user.custom_tool_result",
            "custom_tool_use_id": custom_tool_use_id,
            "content": [{"type": "text",
                         "text": json.dumps({"human_decision": decision})}],
        }],
    )
```

回應 agent 的程式碼跟 gate notebook 的 Part A loop 完全一樣。唯一不同的是你的 server 怎麼得知有事要做：不是本機迴圈去拉事件，而是 webhook 依你的節奏推送通知。

## 6. 釘住推論地理位置

合規要求模型請求要從特定地理位置提供服務時，把它釘在 agent 上，不要依賴 workspace 的預設值：

```python
agent = client.beta.agents.create(
    name="residency-pinned agent",
    model={"id": MODEL, "inference_geo": "us"},
    ...
)
```

可接受的值是 `"global"` 和 `"us"`，受限於 workspace 的 `allowed_inference_geos`。沒設的話，每個請求在服務時會解析成 workspace 的 `default_inference_geo`，所以之後對預設值的變更會影響到已經在跑的 session。有設的話，釘選會在 agent 儲存時、session 建立時、以及每一輪都被驗證：縮小 workspace 的允許清單，會擋掉使用現在不被允許的 agent 的新 session，並拒絕正在跑的 session 的下一輪，而不是讓它們沿用舊規則。這種嚴格才讓釘選能當作資料居留的控制手段。`sessions.create` 上的 `agent_with_overrides` 可以把單一 session 移到另一個允許的地理位置，而不用編輯共用的 agent。完整的步驟說明，包含會清除釘選的 update 語意，在 [`CMA_pin_inference_geo.ipynb`](CMA_pin_inference_geo.md)。

## 7. 資源生命週期：list、retrieve、update、archive

API 裡的每種資源（agents、environments、sessions、vaults、credentials）都有同一套五個動詞：`list`、`retrieve`、`update`、`archive`，以及（部分資源有的）`delete`。我們用 agents 示範完整的一套，再列出其他每種資源可用的動詞當速查。

**archive 和 delete 的差別：** `archive` 會保留紀錄供稽核和取回，但會拆掉任何運行中的 container，並讓該資源不再計入你的 workspace 配額。`delete` 則完全移除紀錄。多數工作流程用 `archive` 是對的，只有在明確需要紀錄消失時（例如測試後清理）才用 `delete`。

```python
listed = client.beta.agents.list(limit=5)
print(f"workspace has at least {len(listed.data)} agents")

retrieved = client.beta.agents.retrieve(agent.id)
print(f"retrieved agent: name={retrieved.name} version={retrieved.version}")

# Updating an agent produces a new version. Pass the current
# version to confirm you're updating from a known state, a
# concurrent update from another process will reject yours rather
# than silently overwriting.
updated = client.beta.agents.update(
    agent.id,
    version=agent.version,
    system="You navigate GitHub repositories. Be terse.",
)
print(f"updated to version {updated.version}")

# Every historical version is queryable.
versions = client.beta.agents.versions.list(agent_id=agent.id)
print(f"agent has {len(versions.data)} versions")
```

## 8. 清理

credentials 和 vaults 都有自己的 archive endpoint。archive 一個 vault **不會**自動 archive 它的 credentials，所以想清乾淨的話，先處理 credentials。

```python
wait_for_idle_status(client, session.id)
client.beta.sessions.archive(session.id)
client.beta.environments.archive(env.id)
client.beta.agents.archive(agent.id)
client.beta.vaults.credentials.archive(credential.id, vault_id=vault.id)
client.beta.vaults.archive(vault.id)
print("archived")
```

## 其他 cookbook

這個 notebook 是正式環境導向的收尾篇。它所包住的工作流程 notebook 如果還沒跑過，值得先跑：

- [`CMA_iterate_fix_failing_tests.ipynb`](CMA_iterate_fix_failing_tests.md)：入門 notebook。透過修一個失敗測試套件的 do-observe-fix 迴圈，介紹 agents、environments、sessions、檔案掛載和串流事件迴圈。
- [`CMA_orchestrate_issue_to_pr.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_orchestrate_issue_to_pr.ipynb)：多輪 agent，透過模擬的 gh CLI 把 issue 一路推到合併的 PR，過程中會從 CI 失敗和 review 意見中恢復。
- [`CMA_explore_unfamiliar_codebase.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_explore_unfamiliar_codebase.ipynb)：grounding 模式，埋了一個過期文件的陷阱。也示範用 `sessions.resources.add` 把更多 context 推進運行中的 session。
- [`CMA_gate_human_in_the_loop.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_gate_human_in_the_loop.ipynb)：custom tool 的 `decide()` 和 `escalate()` 往返，用於 human-in-the-loop 工作流程，搭配上面的 webhook 參考區塊。

## 重點整理

- MCP toolset 讓 agent 直接從 sandbox 呼叫外部 SaaS，不用繞回你的應用程式；只在內網可達的服務才改用 custom tool。
- vault 是 per-user 的憑證容器，session 建立時用 `vault_ids` 參照，agent 看不到 token，稽核也能對回使用者。
- 正式環境的 HITL 用 `session.status_idled` webhook，session 在等人的時候待機，你這邊不用開長連線；有預算的話再加 `session.budget_reached`。
- `inference_geo` 釘在 agent 上，並在儲存、建立 session 和每一輪都驗證，所以能當資料居留的控制。
- 資源都有 list / retrieve / update / archive（/ delete）；大多數情況用 archive，而且要先 archive credentials 再 archive vault。

## 練習

1. 把步驟 1 vault 的 `metadata` 改成你自己的使用者 ID 格式，再用 retrieve 把它讀回來，確認映射可用。
2. 在步驟 6 的 agent 定義改設 `inference_geo` 的值，並在 `sessions.create` 用 `agent_with_overrides` 只改單一 session，比較兩者的效果。
3. 照步驟 7 的做法，對 vaults 或 credentials 跑一次 list 加 archive，並驗證先 archive vault 時，credentials 是否還在。
