---
translated: true
source: examples/agents_api/apps/sev_bot/README.md
---
# 打造處理事故的 SRE agent

> 原文：[examples/agents_api/apps/sev_bot/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/README.md)

在 Slack 裡用服務 telemetry、GitHub、AWS 和過去的事故報告調查事故，復原動作需要人工審核。

## 這篇在做什麼
事故警報進來時，這個 agent 會在 Slack `#oncall` 開一個 thread，調查 production telemetry、GitHub PR 和 commit、AWS 基礎設施，以及類似的歷史事故，然後貼出發現，並請值班人員核准 rollback。範例用 Agents API 的 persistent session、webhook 和 sandbox 把整條流程串起來。

## 學完你會
- 把 PagerDuty、incident.io 或 Alertmanager 的警報轉成「一個事故對應一個 Slack thread 加一個 agent session」。
- 用 `agent.session.action_required` webhook 讓 `propose_rollback` 停下來等人按 Slack 按鈕核准，再繼續跑。
- 把 GitHub MCP、AWS MCP、runbook 和跨事故的 `recall_incidents` 記憶接進同一個 agent。

## 開跑前
- Python 3.14+ 和 `uv`，以及自架 Docker 或第三方 sandbox。
- OpenAI API key 加一把權限受限的 executor key（`OPENAI_EXECUTOR_API_KEY`）。
- 安裝在 `#oncall` 的 Slack app（bot token、signing secret、訊息事件訂閱），且 Slack 要能用 HTTPS 連到你的服務。
- 監控系統（PagerDuty、incident.io 或 Alertmanager）、GitHub 唯讀權限、AWS DevOps Agent 憑證（接真實 AWS 時才需要）。

事故警報會在 Slack `#oncall` 開一個 thread。agent 調查 production telemetry、GitHub pull request 和 commit、AWS 基礎設施，以及類似的過去事故。它貼出調查結果，並請值班人員核准任何 rollback。

## 為什麼用 Agents API？

事故 webhook 觸發工作，值班人員在 Slack 接手。Agents
API 把調查保存在 persistent session 裡，串接營運工具，並在需要由應用程式決定的地方暫停。你的應用程式負責警報去重、值班人員權限、歷史事故紀錄和清理。

這個範例只記錄 rollback 的核准，從不真的執行部署。

![Incident response workflow: receive an alert, investigate evidence, request rollback approval in Slack, save incident memory, and clean up.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_api/apps/sev_bot/assets/workflow.svg)

## 你需要什麼

- Python 3.14+ 和 `uv`。
- 一個 sandbox：自架 Docker 或[第三方供應商](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#sandbox-providers)。
- 一把 OpenAI API key 和另一把受限的 executor key。
- 安裝在 `#oncall` 的 Slack app，有 bot token、signing secret 和訊息事件訂閱。
- PagerDuty、incident.io 或相容 Alertmanager 的監控系統。
- 受影響 GitHub repo 的讀取權限。
- AWS DevOps Agent 憑證或其他唯讀的 AWS 營運整合。

第一次執行會用內建的 `checkout-api` metrics、logs、deployments、GitHub 變更、AWS telemetry 和事故歷史。tool 結果會標示這是範例資料，不是真實 production 診斷。Slack 的訊息是真的會送出。接上你自己的事故時，要把這些 evidence tool 換掉。

## 設定 Slack bot

clone Cookbook，或在你現有的 checkout 裡跑後面的指令：

```bash
git clone https://github.com/openai/openai-cookbook.git
cd openai-cookbook
cp examples/agents_api/apps/sev_bot/.env.example examples/agents_api/apps/sev_bot/.env
docker build -t agent-api-sev-sandbox:latest examples/agents_api/apps/sev_bot
```

用 [`slack-app-manifest.yaml`](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/slack-app-manifest.yaml) 建立 Slack app。把 `https://your-app.example` 換成你應用程式的 HTTPS 位址，安裝 app，並邀請它進 `#oncall`。

把 `OPENAI_API_KEY`、`OPENAI_EXECUTOR_API_KEY`、`SLACK_BOT_TOKEN` 和 `SLACK_SIGNING_SECRET` 加到 `examples/agents_api/apps/sev_bot/.env`。兩把 OpenAI key 要有相同的 owner、organization 和 project。

manifest 在 `/slack/events` 訂閱 `message.channels` 和 `message.groups`，並把核准動作送到 `/slack/actions`。Slack 必須能用 HTTPS 連到這兩個 URL。貼出最初的調查只需要 bot token；後續追問和核准按鈕也需要這些 callback。

每個事故會拿到一個自架的 sandbox，裡面跑 `codex exec-server`。app 只把 `OPENAI_EXECUTOR_API_KEY` 當作 `CODEX_API_KEY` 傳進去；應用程式、Slack、GitHub 和 AWS 的憑證都留在 sandbox 外面。executor key 需要 `api.agents.environments.connect` 權限，以及允許 sandbox 對外網路的 IP 限制。後續追問會重用同一個 sandbox，事故解決或應用程式關閉時會把它刪掉。

要建立有這個權限的 executor key，打開 [Agents > Environments > Keys](https://platform.openai.com/agents?tab=environments&environment_view=keys)，選 **Create**。

app 會把 [`runbooks/`](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/apps/sev_bot/runbooks) 以唯讀方式掛載到 `/workspace/runbooks`。agent 讀 `checkout-api.md` 取得緩解步驟和復原檢查。接上你自己的事故時，每個服務都要加一份以服務命名的 runbook。

## 串接 Agents API 核准 webhook

在 [Project settings > Webhooks](https://platform.openai.com/settings/project/webhooks) 註冊 `https://your-app.example/webhooks/openai`，訂閱 `agent.session.action_required`，並把它的 signing secret 以 `OPENAI_WEBHOOK_SECRET` 加進 `.env`。

這些憑證都設好後，啟動 receiver：

```bash
uv run examples/agents_api/apps/sev_bot/main.py
```

app 會驗證 OpenAI 的簽章，取回 session 的 `required_actions`，並為 `propose_rollback` 貼出 Slack 按鈕。它會存下待處理的 `turn_id` 和 `call_id`，並忽略同一個提案的重複送達。唯讀 tool 仍透過 streaming handler 執行；`propose_rollback` 刻意沒有自動 handler。

Slack callback 把決定回傳給正在等待的 call：

```python
import json

await client.beta.agents.sessions.events.create(
    session.id,
    events=[
        {
            "type": "agent.session.input.tool_result",
            "turn_id": action["turn_id"],
            "call_id": action["call_id"],
            "success": True,
            "output": json.dumps({"decision": "approved", "executed": False}),
        }
    ],
)
```

agent 在核准或拒絕後繼續。核准不等於執行：這個範例從不連到部署系統。要讓 app 持續執行，才能接收 callback 並 stream 最終更新。OpenAI 和 Slack 的 callback 都需要可連到的 HTTPS 位址。如果要部署到超出這個單一 process 範例的環境，請把待處理動作持久化，並使用 durable worker。

## 送出範例事故

從另一個終端機，把附帶的警報送給 receiver：

```bash
curl -X POST http://127.0.0.1:8003/webhooks/alerts \
  -H 'Content-Type: application/json' \
  --data-binary @examples/agents_api/apps/sev_bot/sample_alert.json
```

agent 會把範例調查貼到 `#oncall`，把故障追到 fixture 裡的 pull request #418 和 Redis pool 耗盡。用 Slack thread 裡的按鈕核准或拒絕提議的 rollback。核准只會記錄決定，不會執行部署。

要檢查真實 repo，請照下面設定 GitHub MCP。

## 跟著看實作

這些片段展示 [main.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/main.py)、[alerts.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/alerts.py)
和 [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/agent.py) 裡的事故流程。完整的簽章檢查、
去重、核准處理和清理，請執行上面的 receiver 來看。

### 1. 把警報變成一個調查

receiver 會把各供應商的 payload 正規化，並在背景把調查排進佇列。一個進行中的警報 fingerprint 對應一個事故、一個 Slack thread 和一個
agent session。

```python
from fastapi import BackgroundTasks, Request
from examples.agents_api.apps.sev_bot.alerts import queue_alerts

@app.post("/webhooks/alerts")
async def receive_alert(request: Request, tasks: BackgroundTasks):
    # Authenticate the sender before accepting the payload.
    payload = await request.json()
    return queue_alerts(app.state.bot, payload, tasks)
```

`queue_alerts` 也處理解決事件。可執行的 receiver 會檢查
`ALERT_WEBHOOK_TOKEN`；PagerDuty 或 incident.io 的原生簽章必須在
你的 ingress 驗證完才轉發。

### 2. 建立事故 session

agent 拿到唯讀的 evidence tool，以及一個獨立的函式用來提議
rollback。GitHub 和 AWS MCP tool 只有在 `.env` 設定後才會加入。

```python
from openai import AsyncOpenAI
from examples.agents_api.apps.sev_bot.tools import configured_tools

client = AsyncOpenAI()
instructions = """\
Investigate the incident using service evidence, GitHub, AWS, and past incidents.
Consult /workspace/runbooks/<service>.md and explain impact, likely cause, and next steps.
Use read-only tools and distinguish sample data from live findings.
If a rollout caused the incident, propose a rollback to the previous healthy version.
Approval records a decision; it does not execute a rollback.
"""

session = await client.beta.agents.sessions.create(
    agent={
        "model": "gpt-5.6-sol",
        "instructions": instructions,
        "reasoning": {"effort": "high"},
        "multi_agent": {"enabled": True, "max_concurrent_subagents": 3},
        "tools": configured_tools(),
    },
    environment={"type": "self_hosted", "workspace_directory": "/workspace"},
)
incident.session_id = session.id
```

app 會在 `#oncall` 開一則訊息，並把它的 timestamp 存在事故上。
所有發現和後續追問都用這個 thread。

### 3. 掛上事故 sandbox

sandbox image 裡有 Codex CLI 和 AWS skills。`start_executor` 以唯讀方式掛載
runbooks，並只把 `OPENAI_EXECUTOR_API_KEY` 當作
`CODEX_API_KEY` 傳入。使用 session 回傳的連線值：

```python
import asyncio
from examples.agents_api.apps.sev_bot.agent import start_executor

environment = session.environment
assert environment.type == "self_hosted"
container = await asyncio.to_thread(
    start_executor, environment.id, environment.remote_url,
)
incident.sandbox = container
```

Skills 提供調查指示，不會授予 AWS 存取權。真實的
GitHub 和 AWS 憑證留在服務串接的 MCP tool 那邊。

### 4. Stream 證據並等待核准

只有唯讀 tool 有自動 handler。不要把 `propose_rollback` 放進
handler map，這樣函式呼叫會維持待處理狀態，直到值班人員決定。

```python
handlers = {
    "get_service_evidence": bot.get_service_evidence,
    "recall_incidents": bot.recall_incidents,
}
prompt = """\
Investigate the checkout-api error spike.
Correlate service metrics, deployments, code changes, and past incidents.
Explain customer impact and cite the evidence for your proposed next steps.
"""

async with client.beta.agents.sessions.stream(
    session.id, input=prompt, tool_handlers=handlers,
) as events:
    async for event in events:
        if event.type == "agent.session.turn.output_text.delta":
            print(event.delta, end="", flush=True)
        elif event.type in {"agent.session.failed", "agent.session.turn.failed", "error"}:
            raise RuntimeError(f"Investigation failed: {event.to_dict()}")
```

應用程式收集答案並貼到事故的 Slack thread。
如果 agent 提議 rollback，`agent.session.action_required` webhook
會通知 receiver 取回待處理的函式呼叫並顯示核准
按鈕。[核准 callback](#connect-agents-api-approval-webhooks) 用待處理的 turn 和 call ID
回傳決定。等待決定的期間，要讓 stream 和 receiver
持續執行。

### 5. 繼續處理事故，然後存下解決結果

Slack 的後續追問會取回 `incident.session_id`，並用
同樣的 tool 和 workspace 開始另一個 turn。例如：

```text
Did this Redis connection-pool failure happen before?
What should we check after the rollback?
```

收到已解決的警報時，app 透過
[memory.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/memory.py) 存下報告，貼出最終更新，並關閉 runtime。下一個
事故可以透過 `recall_incidents` 找到那份報告。

清理時，即使其中一個操作失敗，兩個資源都必須嘗試清理：

```python
try:
    await client.beta.agents.sessions.delete(session.id)
finally:
    await asyncio.to_thread(container.remove, force=True)
```

調查失敗後和關閉時，app 也會嘗試清理。
要等所有事故 runtime 都釋放後，才關閉 OpenAI client。

### 預期結果

內建的警報提供的證據會產生像這樣的報告，措辭會有差異：

```text
SEV-1: Checkout API error rate reached 18.7%
Evidence: bundled sample telemetry, not a live production diagnosis.

GitHub: PR #418 reduced the Redis connection pool from 64 to 8.
AWS: ElastiCache shows 143 waiting requests.
History: INC-0931 recorded a similar pool exhaustion incident.
Proposal: Roll back to 2026.08.26.3, pending responder approval.
```

確認發現有引用範例證據，且核准只記錄
決定，不會連到部署系統。

## 串接事故警報

透過你已驗證的 ingress，把事故 webhook 送到：

```text
https://your-app.example/webhooks/alerts
```

Alertmanager 的設定：

```yaml
receivers:
  - name: incident-bot
    webhook_configs:
      - url: https://your-app.example/webhooks/alerts
        http_config:
          authorization:
            credentials: your-shared-token
```

把 `ALERT_WEBHOOK_TOKEN` 設成同一個值。Alertmanager 會把它當 bearer token 送出。警報 fingerprint 用來對進行中的事故去重；先前的事故解決後，之後的警報可以開始新的調查。

PagerDuty 要訂閱 `incident.triggered` 和 `incident.resolved`，並把 PagerDuty 的服務名稱對應到 `operations.json` 裡的一筆。incident.io 要訂閱 `public_incident.incident_created_v2` 和 `public_incident.incident_status_updated_v2`；把 `INCIDENT_SERVICE` 設成該訂閱所影響的服務。多服務事故需要自行調整這個對應。

範例會解析這些供應商的 payload，但不會驗證它們的原生簽章。你的 ingress 必須先驗證 PagerDuty 或 incident.io 簽章，再用 `ALERT_WEBHOOK_TOKEN` 轉發。Slack 簽章由應用程式驗證。

## 使用 AWS skills

[Dockerfile](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/Dockerfile) 在建置 image 時安裝 Codex CLI 和所有 [AWS Agent Toolkit skills](https://github.com/aws/agent-toolkit-for-aws/tree/main/skills)。在 `/workspace` 底下，它會執行：

```bash
npx --yes skills add aws/agent-toolkit-for-aws/skills \
  --agent codex --copy --yes
```

skills 會被複製到 `/workspace/.agents/skills` 供自動探索。agent 會挑選相關的 skills，並視需要載入它們的指示。你可以在事故的 Slack thread 裡問：「List the installed AWS skills and explain which ones help investigate Redis connection exhaustion.」

Skills 提供的是指示，不是 AWS 存取權。讀它們不需要雲端憑證。範例的 evidence tool 留在應用程式裡；要取得真實 AWS 證據，請用唯讀整合。要更新 skills 就重建 image，並且在給予 production 存取權之前先檢查第三方的指示。

## 串接 GitHub

在 `.env` 設定 `GITHUB_TOKEN` 和 `GITHUB_REPOSITORY`。使用只限於受影響 repo 的 fine-grained token，並給予 **Contents** 和 **Pull requests** 的讀取權限。

app 透過唯讀 endpoint `https://api.githubcopilot.com/mcp/readonly` 連到 [GitHub MCP](https://github.com/github/github-mcp-server)。它的 allowlist 有五個 tool：`list_commits`、`get_commit`、`list_pull_requests`、`pull_request_read` 和 `get_file_contents`。Agents API 直接呼叫這些，不需要應用程式 handler，也不用安裝 GitHub CLI。

GitHub 憑證留在 sandbox 外面。如果設定的 MCP server 連不上，session 會失敗，而不是默默略過 repo 檢查。沒有 `GITHUB_TOKEN` 時，`get_service_evidence` 會改回傳內建的範例 PR 和 commit。

## 串接 AWS

[AWS Agent Toolkit](https://github.com/aws/agent-toolkit-for-aws) 包含 observability skills 和給基礎設施調查用的 AWS DevOps Agent MCP server。把 `examples/agents_api/apps/sev_bot/.env` 裡的 `DEVOPS_AGENT_REGION` 和 `DEVOPS_AGENT_TOKEN` 取消註解：

```text
DEVOPS_AGENT_REGION=us-east-1
DEVOPS_AGENT_TOKEN=...
```

應用程式會自動註冊服務串接的 MCP server：

```python
{
    "type": "mcp",
    "server_label": "aws_devops",
    "connection_origin": "service",
    "transport": {
        "type": "http",
        "server_url": "https://connect.aidevops.us-east-1.api.aws/mcp",
        "authorization": f"Bearer {token}",
    },
}
```

沒設定 AWS MCP 時，`get_service_evidence` 會包含內建的 CloudWatch、ECS 和 ElastiCache telemetry。設了 `DEVOPS_AGENT_TOKEN` 後，它會省略那些範例 AWS 資料，讓 agent 用 MCP server 取得 AWS 證據。在你接上自己的監控系統之前，服務 metrics、logs 和 deployments 仍然是範例資料。

## 事故記憶

記憶分兩層：

- **事故內：** 警報 fingerprint 和 Slack thread 對應一個 Agents API session 和 sandbox。後續追問會保留先前的證據、tool 結果、調查脈絡和 workspace 檔案。
- **跨事故：** `recall_incidents` 會搜尋過去的報告，找相關的症狀、根本原因和解決方式。警報解決時，會在 session 關閉前把發現存到 `examples/agents_api/apps/sev_bot/incident_memory.json`。app 啟動時會重新載入這個檔案，沒有存檔時則從 `incident_history.json` 開始。

產生的記憶檔不進 Git，每次存檔都以原子方式取代。刪掉它會把歷史重設成內建範例。這個檔案只跑一個 app process，它不是共用資料庫。

只有已解決事故的歷史能撐過重啟。進行中的 Slack thread、session ID、待處理的核准和 sandbox handle 仍然只存在記憶體。核准 rollback 只會記錄決定，這個範例從不部署或更動 production 基礎設施。

## 調查 tool

- `get_service_evidence` 一次回傳 metrics、近期錯誤 log 和 deployments。
- `recall_incidents` 取得相關的事故歷史和先前的緩解方式。
- `propose_rollback` 請求人工核准，不會更動 production。

只有前兩個有自動 handler。值班人員決定後，由 webhook 和 Slack callback 完成 `propose_rollback`。GitHub 和 AWS 用 MCP 整合；runbook 是 sandbox 裡的檔案。

## 檔案

- [main.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/main.py)：Webhook 路由和應用程式啟動。
- [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/agent.py)：事故調查、核准、解決和清理。
- [alerts.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/alerts.py)：警報正規化和背景任務排程。
- [tools.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/tools.py)：服務證據和 GitHub/AWS MCP tool。
- [slack.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/slack.py)：Slack 訊息、按鈕和 callback 驗證。
- [memory.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/sev_bot/memory.py)：事故歷史的載入、搜尋和原子存檔。

## 重點整理
- 警報 fingerprint 對應一個事故、一個 Slack thread、一個 agent session 和一個 sandbox，後續追問都重用它們。
- 有副作用的動作（`propose_rollback`）刻意不給自動 handler，函式呼叫停在待處理狀態，由 webhook 和人工決定來完成。
- 憑證分離：sandbox 只拿受限的 executor key，GitHub 和 AWS 憑證留在 MCP 那一側。
- 記憶有兩層：事故內靠 session，跨事故靠 `recall_incidents` 搜尋已解決事故的報告。
- 這個範例預設用範例資料且從不真的部署，上 production 前要持久化待處理動作並驗證供應商簽章。

## 練習
1. 在 `incident_history.json` 加一筆你自編的過去事故，送一次範例事故，看 `recall_incidents` 會不會引用它。
2. 照 `checkout-api.md` 的格式為另一個服務寫一份 runbook，並在 `operations.json` 加上對應項目。
3. 仿照 `get_service_evidence` 新增一個唯讀 tool（例如查詢近期設定變更），註冊進 handler map，同時確認 `propose_rollback` 仍然沒有自動 handler。
