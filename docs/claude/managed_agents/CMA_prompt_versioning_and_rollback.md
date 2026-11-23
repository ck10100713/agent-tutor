---
translated: true
source: managed_agents/CMA_prompt_versioning_and_rollback.ipynb
---
# Managed Agents 教學：prompt 版本管理與 rollback

> 原文：[managed_agents/CMA_prompt_versioning_and_rollback.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_prompt_versioning_and_rollback.ipynb)

Server 端的 prompt 版本管理：建立 v1、用有標註的測試集評估、發佈 v2、偵測到退步，再把 session 釘回 version 1 來 rollback。涵蓋 agents.update、sessions.create 的版本釘選，以及 prompt 不是程式碼時 review gate 該移到哪裡。

## 這篇在做什麼

用一個客服工單分流 agent，示範 Managed Agents 把 prompt 放在 server 端、每次 `agents.update` 都產生新的不可變版本。你會用測試集評分 v1，發佈 v2 後發現退步，再靠釘選版本 rollback，不用重新部署。

## 學完你會

- 建立 agent 並理解每次更新會產生新的 `version`。
- 在 `sessions.create` 釘選特定版本，對同一組測試集做對照評分。
- 不重新部署就 rollback，並知道 review gate 應該放在「釘選的版本號」上。

## 開跑前

- Python 3.11+、`anthropic>=2.0.0`、Anthropic API key。
- 需要同目錄的 `example_data/prompt_versioning_and_rollback/support_tickets.jsonl`。

想像你是 PM，產品的客服系統用 LLM 把進來的工單分流給對的團隊。你想調整分流 prompt，讓更多跟 API 有關的工單送到 platform 團隊。以前 prompt 放在程式碼裡，要改就得開 PR、跑 CI、部署，要還原也要重來一遍。Managed Agents 改成把 prompt 放在 server 端：每次 `agents.update` 都會產生一個新的不可變版本，session 用 ID 選擇要用哪個版本。你還是要 review 和核准 prompt 的變更，但核准的是 config 裡的版本號，而不是程式碼 diff，執行中的服務不用 rebuild 就能套用變更。出問題時，把呼叫端指回舊版本就是 rollback。

這份 cookbook 會建立一個客服工單分流 agent、更新 system prompt，並在表現變差時 rollback。

最後你會：
- 建立 agent 並看到它回傳 `version: 1`
- 對特定版本用有標註的測試集評分
- 發佈 v2 prompt 並看版本號變動
- 不部署就把退步的 agent rollback 到 v1

## 先決條件

**必要：**
- Python 3.11+
- `anthropic>=2.0.0`
- Anthropic API key
- 這個目錄中的 `example_data/prompt_versioning_and_rollback/support_tickets.jsonl` fixture


## Setup


```python
%%capture
%pip install -q "anthropic>=2.0.0" python-dotenv
```

```python
import json
import os
import time
from collections import defaultdict
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
if not os.getenv("ANTHROPIC_API_KEY"):
    raise RuntimeError("Set ANTHROPIC_API_KEY in your environment or .env file")

MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
client = Anthropic()
```

## 建立 agent（version 1）

先建立 Environment（agent 執行的 container 範本）跟 agent 本身。System prompt 很短：把每張工單分類到一個團隊跟優先級，只回 JSON。


```python
env = client.beta.environments.create(name="ticket-triage-env")
ENV_ID = env.id

V1_SYSTEM = """You are a support-ticket triage agent for a usage-billed API product.
Read the ticket and respond with ONLY a single line of raw JSON (no code fences, no prose):
{"team": "<billing|auth|api-platform|dashboard>", "priority": "<P1|P2|P3>"}
Route based on the customer's actual problem, not surface keywords."""

agent = client.beta.agents.create(
    name="ticket-triage",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-prompt-versioning-and-rollback"},
    model=MODEL,
    system=V1_SYSTEM,
)
AGENT_ID = agent.id
print(f"env={ENV_ID}  agent={AGENT_ID} v{agent.version}")
```

??? note "輸出"

    ```text
    env=env_017FKqTdU6dFgEe6zbbVQvE5  agent=agent_011CZo6t9Cr6Eg5TeFFPWPpi v1
    ```

`agents.create` 沒有要求就回傳了 `version: 1`。之後每次更新都會產生同一個 `id` 的新版本，我們就是用這個數字來釘選 session 跟 rollback。


## 載入有標註的測試集

下面有二十張工單，每個團隊五張，正確的分流結果已經標好。這是我們評分用的標準答案。


```python
fixture = Path("example_data/prompt_versioning_and_rollback/support_tickets.jsonl")
tickets = [json.loads(line) for line in fixture.read_text().splitlines()]
teams = sorted({t["team"] for t in tickets})
print(f"{len(tickets)} tickets across {len(teams)} teams: {teams}")
```

??? note "輸出"

    ```text
    20 tickets across 4 teams: ['api-platform', 'auth', 'billing', 'dashboard']
    ```

## 評分 version 1

把每張工單送過 v1，看表現如何。下面的 `triage` helper 會開一個釘選特定版本的 session、送一張工單、輪詢 `events.list` 直到 session 回到 idle，再從 `agent.message` event 解析出 JSON 判斷結果。

這份 cookbook 的重點是 `sessions.create` 的 `agent=` 參數。傳單純字串（`agent=AGENT_ID`）會拿到最新版本。傳 `{"type": "agent", "id": ..., "version": ...}` 則釘選到精確的版本，這正是我們做對照比較需要的。


```python
def triage(version: int, ticket: dict) -> dict:
    """Run one ticket through a pinned agent version and return its verdict."""
    session = client.beta.sessions.create(
        agent={"type": "agent", "id": AGENT_ID, "version": version},
        environment_id=ENV_ID,
    )
    try:
        prompt = "Subject: " + ticket["subject"] + "\n\n" + ticket["body"]
        client.beta.sessions.events.send(
            session.id,
            events=[{"type": "user.message", "content": [{"type": "text", "text": prompt}]}],
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            events = client.beta.sessions.events.list(session.id).data
            if events and events[-1].type == "session.status_idle":
                break
            time.sleep(1)
        else:
            raise TimeoutError(f"session {session.id} did not idle within 60s")
        agent_events = [e for e in events if e.type == "agent.message"]
        reply = "".join(b.text for e in agent_events for b in e.content)
        return json.loads(reply)
    finally:
        try:
            client.beta.sessions.archive(session.id)
        except Exception:  # noqa: S110
            pass


def score(version: int) -> dict:
    """Evaluate all tickets against the given version and return per-team accuracy."""
    hits = defaultdict(lambda: [0, 0])
    for t in tickets:
        pred = triage(version, t)
        hits[t["team"]][1] += 1
        if pred.get("team") == t["team"]:
            hits[t["team"]][0] += 1
    return dict(hits)


v1_scores = score(version=1)
print("v1 results:")
for team, (correct, total) in sorted(v1_scores.items()):
    print(f"  {team:14s} {correct}/{total}")
```

??? note "輸出"

    ```text
    v1 results:
      api-platform   5/5
      auth           5/5
      billing        4/5
      dashboard      5/5
    ```

Model 表現很好，幾乎所有分流都正確。

## 發佈 version 2

現在 PM 發佈她的修改：加一條分流規則，告訴 agent 凡是跟 API 使用或 rate limit 有關的都歸 platform 團隊。`agents.update` 把 agent 更新成新的 system prompt。


```python
V2_SYSTEM = V1_SYSTEM + (
    "\n\nROUTING RULE: If the ticket text mentions API usage, rate limits, quotas, "
    "or request volume, route to api-platform. Apply this rule before any other "
    "consideration; do not second-guess it based on the rest of the ticket."
)
agent = client.beta.agents.update(AGENT_ID, version=agent.version, system=V2_SYSTEM)
print(f"agent {AGENT_ID} now at v{agent.version}")
```

??? note "輸出"

    ```text
    agent agent_011CZo6t9Cr6Eg5TeFFPWPpi now at v2
    ```

### Code review 跑哪去了？

我們只用一個 API 呼叫就改了 agent。這個 notebook 裡完全沒有 review，demo 可以，但 production 不該這樣跑。

`agents.update` 沒有內建的核准流程，workspace 裡任何 key 都能呼叫。如果呼叫端傳的是單純的 agent ID 而不是釘選的版本，下一個 session 就會立刻用新 prompt。這是不用部署的代價，跟 feature flag 或任何透過 API 而非程式碼管理的 config 是同樣的取捨。

把 review 放回去的做法是：production 的呼叫端一律釘選明確的版本，*那個釘選的數字* 才是受變更管控的東西。任何人都可以建立 v2、v3、v10，這些版本放在 server 上沒有流量。要升級就是更新告訴 production 呼叫端該傳哪個版本的 config，這個更新走你正常的 review 流程。這樣建立版本很便宜，又維持你的 SDLC。這仍然是好處，因為你只要更新 config 值，而不是 production 程式碼，所有 runner 就會一起套用變更。


## 評分 version 2

同樣的評估，改釘選 v2。新規則範圍很廣，而在依用量計費的 API 產品裡，billing 工單也會談到 API 用量。


```python
v2_scores = score(version=agent.version)

for team in sorted(v1_scores):
    c1, n1 = v1_scores[team]
    c2, n2 = v2_scores[team]
    flag = "  <-- regressed" if c2 < c1 else ""
    print(team)
    print(f"  v1: {c1}/{n1}")
    print(f"  v2: {c2}/{n2}{flag}")
```

??? note "輸出"

    ```text
    api-platform
      v1: 5/5
      v2: 5/5
    auth
      v1: 5/5
      v2: 5/5
    billing
      v1: 4/5
      v2: 2/5  <-- regressed
    dashboard
      v1: 5/5
      v2: 5/5
    ```

## Rollback

Billing 退步了。Version 1 還在 server 上。Rollback 不是部署，呼叫端只要改回傳 `version: 1`。


```python
billing = [t for t in tickets if t["team"] == "billing"]
rerun = [triage(version=1, ticket=t).get("team") for t in billing]
print(f"billing tickets via version=1: {rerun.count('billing')}/{len(billing)} correct")
```

??? note "輸出"

    ```text
    billing tickets via version=1: 4/5 correct
    ```

因為版本存在 server 端，v2 還在，PM 可以繼續迭代它，同時 production 維持在 v1，或把一小部分流量導到 v2 當 canary。修正準備好時，她可以建立 v3，走一樣的流程升級。


## 清理


```python
client.beta.agents.archive(AGENT_ID)
client.beta.environments.archive(ENV_ID)
print("archived")
```

??? note "輸出"

    ```text
    archived
    ```

## 回顧

機制本身很小（create、update、pin、re-pin），但 prompt 變成 server 端有版本的資源後，你可以獨立於應用程式碼來評估和升級 prompt，可以像上面那樣透過 `update` 執行，或是改 config 裡的版本。

值得帶進你工作流程的幾點：

- 讓 production 呼叫端釘選明確的版本，不要用單純的 agent ID。新版本在你升級之前都是看不見的。
- 把釘選的版本號當作更改 prompt 的關卡。建立版本是探索性的，更新 production 釘選才要走 review。
- 對風險較高的 agent，先把一部分流量導到新版本並比較（就像這個 notebook 做的），再完全升級。你可以把版本管理當成 feature flag 來用。

### 後續

- `client.beta.agents.versions.list(AGENT_ID)` 會回傳 agent 的所有版本。
- `managed_agents/` 裡的其他 notebook 涵蓋 session、自訂 tool 與端到端的模式。


## 重點整理

- Prompt 放 server 端、每次更新產生不可變的新版本，改 prompt 不必改程式碼或重新部署。
- 傳單純 agent ID 會拿到最新版，傳 `{"type": "agent", "id", "version"}` 才是釘選。
- Production 一律釘選版本，把「釘選的版本號」當作受 review 管控的 config。
- 新規則要用有標註的測試集對照評分，才看得出像 billing 這種意外的退步。
- Rollback 就是把呼叫端改回舊版本號，舊版本和新版本都還在 server 上，可以接著迭代或當 canary。

## 練習

1. 把 `triage` 的 `agent=` 改成單純字串 `AGENT_ID`，確認它用的是最新版本。
2. 自己改寫 v2 的規則，讓它只針對 rate limit 而不是所有 API 用量，重跑評分看 billing 還有沒有退步。
3. 用 `client.beta.agents.versions.list(AGENT_ID)` 列出所有版本，然後寫一段程式，把一半的工單導到 v1、一半導到 v2，比較兩邊的準確率。
