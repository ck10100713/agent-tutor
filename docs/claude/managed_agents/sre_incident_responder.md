---
translated: true
source: managed_agents/sre_incident_responder.ipynb
---
# 用 Claude Managed Agents 打造 SRE 事故應變 agent

> 原文：[managed_agents/sre_incident_responder.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/sre_incident_responder.ipynb)

把 Claude 接進你的 on-call 流程：告警一響，agent 就讀 log 和 runbook、找出根本原因、開修復 PR，然後等你核准才 merge。

## 這篇在做什麼

半夜三點告警響了，要有人撈 log、找對的 runbook、追出錯誤設定、開 PR、等人核准。這篇用 Claude Managed Agents 讓 agent 先做完第一輪，等你上線時修復 PR 已經在等你 review，最後一關仍由人決定。

PagerDuty、GitHub、Datadog 都用本機 fixture 模擬，所以只要 `ANTHROPIC_API_KEY` 就能跑。

## 學完你會

- 上傳 Skill 並掛到 Claude Managed Agent 上
- 把內建 toolset 和你自己處理的 custom tool 混在一起用，並用 webhook payload 啟動 session
- 把破壞性動作卡在人工核准後面，並在 Console 讀完整的 session trace

## 開跑前

- 環境變數 `ANTHROPIC_API_KEY`
- 安裝相依套件（見下面的 cell）

## 簡介

正式環境半夜三點告警響起，得有人撈 log、找對 runbook、追出錯誤設定、開 PR、拿到核准。agent 可以幫你做第一輪，等你坐到電腦前，修復已經在等 review，前提是它有對的 context，而且最後一個決定由人下。

[Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 提供可擴展的基礎設施、sandbox 和安全機制，讓你輕鬆做出這個東西。這篇教學會把它們接在一起：

- 一個模擬的 **PagerDuty webhook**，用一次 API 呼叫觸發你的 Claude Managed Agent。
- 一個 **Skill** 教 agent 你們團隊的 runbook 慣例，讓它知道該去哪裡找。
- 內建的 `bash`/`read`/`edit` tool 讓它在 sandbox 裡調查 log 和 infrastructure code。
- **Custom tool** 讓它開 pull request，並在 merge 前請人核准。這些呼叫由你的程式處理，所以「開 PR」實際要做什麼由你決定。
- **Anthropic Console** 自動記錄每一步，給你完整的 observability。

下面所有東西只需要 `ANTHROPIC_API_KEY`。PagerDuty、GitHub、Datadog 都用本機 fixture 模擬，讓你專心看 Managed Agents 的部分；結尾會說明怎麼把每個模擬換成真的服務。

### 你會學到

- 上傳 Skill 並掛到 Claude Managed Agent
- 混用內建 toolset 和由你的應用程式處理的 custom tool
- 用 webhook payload 啟動 session
- 把破壞性動作卡在人工核准後面
- 在 Console 讀完整的 session trace

### 前置需求

在環境中設好 `ANTHROPIC_API_KEY`，然後安裝相依套件：

```python
%pip install -q "anthropic>=2.0.0" python-dotenv
```

```python
import json
import os
import time
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv
from utilities import wait_for_idle_status

load_dotenv()
client = Anthropic()
MODEL = os.getenv("COOKBOOK_MODEL", "claude-opus-5-5")
FIXTURE = Path("example_data/sre")
```

## 1. 上傳 runbook skill

[**Skill**](https://platform.claude.com/docs/en/managed-agents/skills) 是一個小型檔案系統 bundle，平台會用 progressive disclosure 的方式掛進 agent 的 context：agent 一開始只看到一行描述，相關時才去讀內文。放團隊慣例很適合，這些東西不該塞在 system prompt。

下面的範例 skill 只編碼一條規則：*動 infrastructure 之前先查 runbook*，就像真實團隊的 playbook。你用 Skills API 上傳一次，之後在每個需要的 agent 上用 ID 引用。

```python
# A real skill is usually a folder on disk (SKILL.md plus any helper
# scripts or reference docs) that you zip and upload. For this tutorial
# the SKILL.md is small enough to keep inline.
RUNBOOK_SKILL = """\
---
name: incident-runbooks
description: How to triage production incidents using the team runbooks.
---

# Incident runbooks

When an alert references a service, locate that service's recent logs
and identify the failure signature (the repeating error class, exit
code, or status pattern).

Consult the team runbooks before proposing any fix. Runbooks are
organised by failure signature — for example `oom.md`, `5xx.md`,
`latency.md`. Each one lists the triage steps for that class of
failure and the configuration that usually needs to change.

Any fix to infrastructure code must be opened as a pull request that
cites the runbook you followed. Do not patch live resources directly.
"""

skill = client.beta.skills.create(
    display_name="incident-runbooks",
    files=[("incident-runbooks/SKILL.md", RUNBOOK_SKILL.encode(), "text/markdown")],
)
print(f"skill: {skill.id} (version {skill.latest_version_id})")
```

??? note "輸出"

    ```text
    skill: skill_01WPWHALbtEVBUWG6mHa7Tna (version 1775588716519983)
    ```

## 2. 建立 agent

agent 的 `tools` 清單結合三種能力：

- [`agent_toolset_20260401`](https://platform.claude.com/docs/en/managed-agents/tools)：內建的 `bash`、`read`、`grep`、`edit` 等 tool，在 sandbox *裡面*執行。agent 用它們來調查。
- 第 1 步的 runbook **skill**。
- 三個 **custom tool**：`open_pull_request`、`request_approval`、`merge_pull_request`。agent 可以呼叫，但由*你的應用程式*執行。它們是 agent 接觸 sandbox 外部系統的管道，也是你把人放進流程的地方。

system prompt 只放角色和工作流程。告警本身會當成第一個 user event 送進來，所以同一個 agent 可以處理任何事故。

```python
SRE_SYSTEM_PROMPT = """\
You are an on-call SRE agent. Each user message is a PagerDuty alert
payload. Triage it to root cause and ship the minimal safe fix.

The session workspace contains the recent logs, the infrastructure
repo, and the team runbooks for the alerting service. Explore it to
find what you need.

Workflow for every alert:
1. Read the logs and identify the failure signature.
2. Find the root cause in the infrastructure repo, save a copy of the
   original file, edit it in place, then produce a unified diff with
   `diff -u`.
3. open_pull_request(title, body, diff) with the fix.
4. request_approval(summary) and wait for the human's decision.
5. Only if the result is "approved", merge_pull_request(pr_number).
   Otherwise stop and report.

Never call merge_pull_request unless request_approval returned
"approved". Keep the fix minimal — do not refactor unrelated config.
"""

agent = client.beta.agents.create(
    name="cookbook-sre-responder",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/sre-incident-responder"},
    model=MODEL,
    system=SRE_SYSTEM_PROMPT,
    skills=[{"type": "custom", "skill_id": skill.id, "version": skill.latest_version_id}],
    tools=[
        {
            "type": "agent_toolset_20260401",
            "default_config": {
                "enabled": True,
                "permission_policy": {"type": "always_allow"},
            },
            "configs": [
                {"name": "web_search", "enabled": False},
                {"name": "web_fetch", "enabled": False},
            ],
        },
        {
            "type": "custom",
            "name": "open_pull_request",
            "description": "Open a pull request against the infra repo with the proposed fix.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "diff": {"type": "string", "description": "Unified diff of the change."},
                },
                "required": ["title", "body", "diff"],
            },
        },
        {
            "type": "custom",
            "name": "request_approval",
            "description": "Ask the on-call human to approve the proposed PR before merging.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                },
                "required": ["summary"],
            },
        },
        {
            "type": "custom",
            "name": "merge_pull_request",
            "description": "Merge an approved pull request.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pr_number": {"type": "integer"},
                },
                "required": ["pr_number"],
            },
        },
    ],
)
print(f"agent: {agent.id} v{agent.version}")
```

??? note "輸出"

    ```text
    agent: agent_011CZpw3Y76Vu4t2j2QEosVa v1
    ```

## 3. 建立 environment 並掛載資料

agent 要調查需要工作區裡有三樣東西：最近的服務 log、infrastructure repo、團隊 runbook。每一個都用 Files API 上傳，列在 `resources` 裡，這樣每個 session 都會把它們掛到 system prompt 預期的路徑。用 `limited` 網路的雲端 environment 就夠了，因為 agent 只需要自己的檔案系統。

為了讓這個 notebook 只靠 `ANTHROPIC_API_KEY` 就能跑，infra「repo」只是一份 manifest，裡面的 `memory: 128Mi` 限制太低。正式環境你會把這個上傳換成 `github_repository` resource，直接把真的 repo clone 進 sandbox：

```python
{
    "type": "github_repository",
    "url": "https://github.com/your-org/infra",
    "authorization_token": os.environ["GITHUB_TOKEN"],
    "checkout": {"type": "branch", "name": "main"},
    "mount_path": "infra",
}
```

```python
env = client.beta.environments.create(
    name="cookbook-sre-env",
    config={"type": "cloud", "networking": {"type": "limited"}},
)


def upload(path: Path, mime: str) -> str:
    with path.open("rb") as f:
        return client.beta.files.upload(file=(path.name, f, mime)).id


log_id = upload(FIXTURE / "logs/checkout-svc.log", "text/plain")
manifest_id = upload(FIXTURE / "infra/k8s/checkout-deploy.yaml", "text/yaml")
runbook_id = upload(FIXTURE / "runbooks/oom.md", "text/markdown")

RESOURCES = [
    {"type": "file", "file_id": log_id, "mount_path": "logs/checkout-svc.log"},
    {"type": "file", "file_id": manifest_id, "mount_path": "infra/k8s/checkout-deploy.yaml"},
    {"type": "file", "file_id": runbook_id, "mount_path": "runbooks/oom.md"},
]
print(f"environment: {env.id}")
```

??? note "輸出"

    ```text
    environment: env_01R6hmJkd6BhpPotXnoC7rqU
    ```

## 4. 處理事故告警

下面的 handler 是你實際會部署的那個函式，也就是事故發生時由告警系統呼叫的 Flask 或 FastAPI route。它建立一個引用 agent 和 environment 的 session，掛載資料，並把告警 JSON 當成第一個 `user.message` event 送出。這個範例用 [PagerDuty V3 webhook](https://developer.pagerduty.com/docs/webhooks-overview) 的 payload，不過任何能 POST JSON 的 pager 做法都一樣；這裡直接用 fixture 呼叫 handler。

```python
def handle_pagerduty_webhook(payload: dict) -> str:
    incident = payload["event"]["data"]
    session = client.beta.sessions.create(
        environment_id=env.id,
        agent={"type": "agent", "id": agent.id, "version": agent.version},
        resources=RESOURCES,
        title=f"[{incident['service']['summary']}] {incident['title']}",
    )
    client.beta.sessions.events.send(
        session.id,
        events=[
            {
                "type": "user.message",
                "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            }
        ],
    )
    return session.id


with (FIXTURE / "alert.json").open() as f:
    alert = json.load(f)

session_id = handle_pagerduty_webhook(alert)
print(f"session: {session_id}")
```

??? note "輸出"

    ```text
    session: sesn_011CZpw3gtC691y7qmaLNmLM
    ```

## 5. 處理 agent 的 custom tool 呼叫

內建 tool 和你的 custom tool 在這裡會合。agent 的 `read`/`bash`/`edit` 呼叫在容器上執行，在 event log 以 `agent.tool_use` 出現，這就是調查過程，你只要印出來。但 agent 呼叫你的 custom tool 時，session 會進入 `idle`，`stop_reason.type == "requires_action"`，等*你的應用程式*用 `user.custom_tool_result` 回應。

下面的迴圈輪詢 `events.list`，`open_pull_request` 和 `merge_pull_request` 直接寫進本機 list 來回應（那就是 GitHub 的模擬），但 `request_approval` 一出現就**返回**，因為這個需要人。

正式環境裡「需要人」通常是*貼到 Slack*：把 agent 的摘要連同 **Approve** 按鈕貼到 on-call 頻道，有人按了再把結果送回去。[`slack_data_bot` cookbook](slack_data_bot.md) 示範了 Bolt 的接法；這裡為了讓 notebook 自成一體，下一個 cell 直接內聯核准。

```python
prs: list[dict] = []
pending_approvals: list[dict] = []
seen_events: set[str] = set()


def handle_custom_tool(name: str, args: dict) -> dict:
    if name == "open_pull_request":
        n = len(prs) + 1
        prs.append({"number": n, "merged": False, **args})
        print(f"\n── PR #{n}: {args['title']} ──")
        return {"pr_number": n, "url": f"mock://infra/pull/{n}"}
    if name == "merge_pull_request":
        prs[args["pr_number"] - 1]["merged"] = True
        return {"merged": True}
    raise ValueError(f"unhandled tool {name}")


def run_until_approval_or_end(session_id: str) -> str | None:
    """Poll the session's event log, servicing custom tools, until either
    a request_approval call arrives (return its event_id so the caller
    can respond) or the agent ends its turn (return None)."""
    custom_calls: dict[str, object] = {}
    responded: set[str] = set()
    while True:
        idle_stop = None
        for ev in client.beta.sessions.events.list(session_id):
            if ev.id in seen_events:
                continue
            seen_events.add(ev.id)
            if ev.type == "agent.message":
                for block in ev.content:
                    if block.type == "text":
                        print(block.text, end="")
            elif ev.type == "agent.tool_use":
                print(f"\n  [{ev.name}]")
            elif ev.type == "agent.custom_tool_use":
                custom_calls[ev.id] = ev
                print(f"\n→ {ev.name}")
            elif ev.type == "session.status_idle":
                idle_stop = ev.stop_reason
            elif ev.type == "session.status_terminated":
                return None
        if idle_stop is None:
            time.sleep(1.0)
            continue
        if idle_stop.type == "end_turn":
            return None
        if idle_stop.type == "requires_action":
            for event_id in idle_stop.event_ids:
                if event_id in responded:
                    continue
                call = custom_calls[event_id]
                if call.name == "request_approval":
                    pending_approvals.append({"event_id": event_id, **call.input})
                    return event_id
                result = handle_custom_tool(call.name, call.input)
                client.beta.sessions.events.send(
                    session_id,
                    events=[
                        {
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": event_id,
                            "content": [{"type": "text", "text": json.dumps(result)}],
                        }
                    ],
                )
                responded.add(event_id)
        time.sleep(1.0)


approval_event_id = run_until_approval_or_end(session_id)
```

??? note "輸出"

    ```text
    I'll help you triage this production incident. The alert shows checkout-svc pods are crash-looping with 7 restarts in 5 minutes. Let me start by exploring the workspace to find logs and the infrastructure configuration.
      [bash]
    Let me check the session directory for logs and infrastructure files:
      [bash]
    Perfect! Let me examine the logs first to identify the failure signature:
      [read]
    Perfect! I've identified the failure signature. The logs show a clear **OutOfMemoryError** pattern:

    **Failure Signature:**
    - Service starts and warms pricing cache (14,092 entries)
    - Heap memory grows rapidly: 101MB → 118MB → 121MB (against 128MB limit)
    - `pricing.recompute` function attempts allocation during garbage collection pause (412ms GC pause observed)
    - Container gets OOMKilled (exit 137) after ~2 minutes
    - Service restarts and immediately repeats the cycle

    Now let me examine the deployment configuration to identify the root cause:
      [read]
    **Root Cause Analysis:**

    The deployment has memory limits set to **128Mi** (both request and limit). From the logs, I can see:

    1. **Pricing cache loads 14,092 entries** during startup (lines 9, 23, 32)
    2. **Heap pressure builds immediately:**
       - After 90 seconds: 101MB (79% of 128MB)
       - After 110 seconds: 118MB (92% of 128MB)  
       - After 120 seconds: 121MB (94% of 128MB)
    3. **Pricing recompute fails** to allocate 8MB (lines 15-16, 26-27, 34)
    4. **Consistent pattern:** OOMKilled every ~2 minutes on all restarts

    The memory limit is **insufficient** for:
    - Service startup + dependencies
    - Pricing cache (14k+ entries)
    - Normal operation headroom
    - GC operations (412ms pause observed suggests high memory pressure)

    **Fix:** Increase memory limits to provide adequate headroom for the pricing cache workload.

    Let me create a backup and apply the fix:
      [bash]
    Now I'll update the memory limits to 512Mi (4x current limit, which is standard practice for memory-pressure issues):
    ... (省略 13 行)
    ```

agent 讀了 log，透過 skill 把 `OOMKilled` 特徵對應到 `runbooks/oom.md`，在 `infra/k8s/checkout-deploy.yaml` 找到 128Mi 的記憶體限制，改掉它、開了 PR，現在在等你。下面是會出現在你 `#oncall` Slack 頻道的訊息：

```python
pr = prs[0]
print(pr["body"], "\n")
print(pr["diff"])
print("\n" + "─" * 60)
print("APPROVAL REQUESTED:", pending_approvals[0]["summary"])
```

??? note "輸出"

    ```text
    ## Issue
    checkout-svc pods are in a CrashLoopBackOff state due to OutOfMemoryError. The service consistently crashes after ~2 minutes with 7 restarts in the last 5 minutes.

    ## Root Cause
    The deployment had memory limits set to 128Mi, which is insufficient for the pricing cache operation:
    - Pricing cache warms with 14,092 entries during startup
    - Heap pressure builds to 118-121MB (92-94% of limit) within 90 seconds
    - pricing.recompute fails to allocate 8MB, causing OOMKilled (exit 137)
    - Service restarts and repeats the cycle

    ## Fix
    Increase memory allocation to provide adequate headroom:
    - **Memory request:** 128Mi → 256Mi
    - **Memory limit:** 128Mi → 512Mi

    This provides 4x headroom for the pricing cache and normal operations while remaining resource-efficient (512Mi limit is standard for Java/similar workloads with caching).

    ## Verification
    The fix addresses the immediate OOMKilled pattern in logs and aligns memory resources with the actual cache size and operational requirements. 

    --- a/k8s/checkout-deploy.yaml
    +++ b/k8s/checkout-deploy.yaml
    @@ -21,10 +21,10 @@ spec:
               resources:
                 requests:
                   cpu: 250m
    -              memory: 128Mi
    +              memory: 256Mi
                 limits:
                   cpu: 500m
    -              memory: 128Mi
    +              memory: 512Mi
               readinessProbe:
                 httpGet:
                   path: /healthz

    ────────────────────────────────────────────────────────────
    APPROVAL REQUESTED: **Incident:** checkout-svc CrashLoopBackOff with OOMKilled (7 restarts in 5 min)

    **Root Cause:** Memory limit (128Mi) insufficient for 14k-entry pricing cache
    ... (省略 4 行)
    ```

## 6. 核准並讓 agent merge

把 `"approved"` 當成 `request_approval` 的結果送回去。agent 會繼續執行、呼叫 `merge_pull_request`，然後結束這一輪。Slack 版本裡，這個送出動作在你的按鈕點擊 handler 裡，payload 完全一樣。

```python
client.beta.sessions.events.send(
    session_id,
    events=[
        {
            "type": "user.custom_tool_result",
            "custom_tool_use_id": approval_event_id,
            "content": [{"type": "text", "text": json.dumps({"decision": "approved"})}],
        }
    ],
)

run_until_approval_or_end(session_id)
print(f"\n\nPR #{pr['number']} merged: {prs[0]['merged']}")
```

??? note "輸出"

    ```text
    Great! The fix has been approved. Now merging:
    → merge_pull_request
    ## ✅ Incident Resolved

    **Summary:**
    - **Status:** MERGED (PR #1)
    - **Failure:** checkout-svc crash-loop with OOMKilled (exit 137)
    - **Root Cause:** Memory limit of 128Mi was insufficient for pricing cache (14,092 entries)
    - **Fix Applied:** 
      - Memory request: 128Mi → 256Mi
      - Memory limit: 128Mi → 512Mi

    **What Happened:**
    1. Service loaded 14k+ pricing cache entries during startup
    2. Heap grew to 118-121MB within ~2 minutes (92-94% of 128Mi limit)
    3. pricing.recompute failed to allocate 8MB, triggering OutOfMemoryError
    4. Container was OOMKilled and restarted, repeating the cycle

    **Expected Outcome:**
    With 512Mi limit and 256Mi request, the service will have sufficient memory headroom for:
    - Pricing cache operations
    - Normal request processing
    - JVM garbage collection pauses
    - No more CrashLoopBackOff

    The deployment update will trigger a rolling restart of the 3 replicas, allowing pods to spawn with the new memory configuration.

    PR #1 merged: True
    ```

## 7. 在 Console 檢視這次執行

因為調查是以 Managed Agents session 執行，上面的每一步，包括檔案讀取、`bash` diff、manifest 修改、三次 custom tool 呼叫、你送出的核准，都會存成 session 上的 event。在 [Console](https://platform.claude.com/) 的 **Managed Agents → Sessions** 打開，就能看到完整稽核軌跡，不用額外埋點：

<img src="https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/managed_agents/example_data/sre/console_session.png" alt="Console session view for the incident-response run" width="700" />

### 清理

封存 session 和你建立的資源。

```python
wait_for_idle_status(client, session_id)
client.beta.sessions.archive(session_id)
client.beta.environments.archive(env.id)
client.beta.agents.archive(agent.id)
client.beta.skills.delete(skill.id)  # deleting a skill also deletes its versions
print("archived")
```

??? note "輸出"

    ```text
    archived
    ```

## 下一步：接上正式環境

三個替換就能把 notebook 變成 on-call 系統。

**在 Slack 核准。** `request_approval` 一到，就用 Block Kit 按鈕貼到 on-call 頻道，並在 action handler 裡送回 `user.custom_tool_result`。[`slack_data_bot` cookbook](slack_data_bot.md) 涵蓋 Bolt app 的設定；跟核准有關的部分很少：

```python
def post_for_approval(session_id, event_id, summary):
    slack.client.chat_postMessage(
        channel=ONCALL_CHANNEL,
        text=summary,
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": summary}},
            {"type": "actions", "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "Approve"},
                 "action_id": "approve", "value": f"{session_id}:{event_id}"},
                {"type": "button", "text": {"type": "plain_text", "text": "Reject"},
                 "action_id": "reject", "value": f"{session_id}:{event_id}"},
            ]},
        ],
    )

@slack.action("approve")
def on_approve(ack, body):
    ack()
    session_id, event_id = body["actions"][0]["value"].split(":")
    client.beta.sessions.events.send(
        session_id,
        events=[{"type": "user.custom_tool_result",
                 "custom_tool_use_id": event_id,
                 "content": [{"type": "text",
                              "text": json.dumps({"decision": "approved"})}]}],
    )
```

想完全拿掉輪詢迴圈，可以在 `session.requires_action` 註冊 Console webhook：agent 一暫停平台就會呼叫你的 endpoint，你從那裡貼到 Slack。

**用 GitHub 取代模擬。** 拿掉 `open_pull_request` / `merge_pull_request` 這兩個 custom tool，改給 agent GitHub MCP server，token 存在 vault 裡，永遠不會出現在你的程式碼中。[`CMA_operate_in_production.ipynb`](CMA_operate_in_production.md) 會帶你走過 per-user 憑證。

```python
agent = client.beta.agents.create(
    ...,
    mcp_servers=[{"type": "url", "name": "github",
                  "url": "https://api.githubcopilot.com/mcp/"}],
    tools=[{"type": "agent_toolset_20260401", ...},
           {"type": "mcp_toolset", "server_name": "github"},
           {"type": "custom", "name": "request_approval", ...}],
)
session = client.beta.sessions.create(..., vault_ids=[github_vault.id])
```

**用即時 log 取代 fixture。** 透過 environment config 傳入 `DD_API_KEY` / `DD_APP_KEY`，讓 agent 從 `bash` 用 `curl` 呼叫 Datadog Logs API，而不是讀掛載的檔案。

> 另見 [Agent SDK site-reliability agent](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/03_The_site_reliability_agent.ipynb)：同一個問題，改用本機 Agent SDK 而不是代管的 Managed Agents runtime 來解。


## 你學到了什麼

- 從任何外部事件觸發 session：一個 PagerDuty webhook 的 API 呼叫就啟動了整個流程。
- 掛上 **Skill**，讓 agent 有你團隊的慣例。
- 用 **resources** 掛載資料：程式碼用 `github_repository`，log 和 runbook 用 `file`。
- 用 **custom tool** 回呼你的應用程式，並透過 `requires_action` 把動作卡在人工核准後面。
- 在 **Console** 的 session 畫面免費拿到完整稽核軌跡。

把模擬換成 GitHub MCP、Slack 核准按鈕和即時 log，就能上 on-call。

## 重點整理

- Managed Agents 把 sandbox、基礎設施和稽核軌跡都包好，你只需要定義 agent、環境和 tool。
- Skill 用 progressive disclosure 放團隊慣例，不佔 system prompt。
- 內建 tool 在 sandbox 內跑，custom tool 由你的程式執行，後者是接外部系統和插入人工核准的地方。
- 告警走第一個 user event 進來，agent 本身不綁特定事故，同一個可以處理任何告警。
- session 停在 `requires_action` 就是等人的訊號，把核准結果用 `user.custom_tool_result` 送回就會繼續。

## 練習

1. 把 fixture 裡的 `memory: 128Mi` 換成別的值，或改掉告警 JSON 的內容，看 agent 找到的原因和 PR 怎麼變。
2. 在核准那步送出別的回應（例如拒絕），觀察 agent 有沒有照樣呼叫 `merge_pull_request`，並調整 system prompt 讓它在被拒絕時停手。
3. 再加一個 custom tool（例如 `post_status_update`），在 agent 建立時列進 `tools`，並在處理迴圈加一個分支回應它。
