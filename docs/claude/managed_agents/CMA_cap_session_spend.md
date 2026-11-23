---
translated: true
source: managed_agents/CMA_cap_session_spend.ipynb
---
# Budgets: 限制 session 能花多少錢

> 原文：[managed_agents/CMA_cap_session_spend.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_cap_session_spend.ipynb)

幫 Managed Agents session 設定強制執行的 list-cost 預算，從 session.usage event 觀察花費累積，接住 budget_reached 暫停，並用 sessions.update 調高、調低或移除上限。

## 這篇在做什麼

無人看管的 agent 在成本上沒有自然的停止點。這篇示範在建立 session 時設 `budget`，讓花費到上限就自動暫停，然後調高上限讓工作接著做完。

## 學完你會

- 在 `sessions.create` 設定 `budget`，並讀 `usage.list_cost` 跟 `session.usage` snapshot。
- 辨認 `budget_reached` 這種暫停停止原因，以及暫停時 session 保留了什麼。
- 用 `sessions.update` 調高、調低或移除預算上限。

## 開跑前

- 需要 Anthropic API key，使用 Managed Agents。
- 需要 `anthropic>=0.121.0`。
- 範例用到 web search 跟 web fetch，會產生實際的 token 費用（預算設為 10 美分）。

無人看管的 agent 在成本上沒有自然的停止點。帶 web search 的研究任務可能又多抓一百次網頁，coding loop 可能重試一個不穩定的測試到早上。沒有上限的話，你會從帳單才發現。

Session budget 是對單一 session 強制執行的花費上限。建立 session 時設定最高 list cost，平台會用公開 list price 追蹤該 session 每個 thread 的 token 成本，累計達到上限時，session 會進入 idle，停止原因是 `budget_reached`。檔案、tool 狀態跟對話都完整保留。調高上限，工作就從停下來的地方繼續。

這篇 notebook 會講：

- 在 `sessions.create` 設定 `budget`
- 讀取 `usage.list_cost`，以及這一輪結束時 stream 送來的 `session.usage` snapshot
- `budget_reached` 停止，以及暫停的 session 保留了什麼
- 用 `sessions.update` 調高、調低、移除上限

## 1. 設定 client

Budget 使用標準的 `managed-agents-2026-04-01` beta header。`budget` 參數跟 `session.usage` 上的成本欄位需要 `anthropic>=0.121.0`。

```python
%%capture
%pip install -qU "anthropic>=0.121.0" python-dotenv
```

```python
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

BETAS = ["managed-agents-2026-04-01"]
MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
client = anthropic.Anthropic()
```

## 2. 建立有機會超支的 agent

這個範例的 agent 負責寫競爭情勢簡報。它有 web search 跟 web fetch，prompt 完全沒限制它要讀幾個來源。這種沒有邊界的特性，正是預算的用武之地。

```python
env = client.beta.environments.create(
    name="budget-demo",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
    betas=BETAS,
)

analyst = client.beta.agents.create(
    name="market_analyst",
    description="Writes sourced competitive landscape briefs.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-cap-session-spend"},
    model={"id": MODEL},
    system="""You write competitive landscape briefs for product teams.
Given a market, use web search and web fetch to find the notable vendors, their
positioning, and recent moves. Read primary sources rather than aggregators.
Write the brief to /mnt/session/outputs/brief.md with a Sources section listing every
URL you relied on. Keep researching until you are confident the brief is complete.""",
    tools=[
        {
            "type": "agent_toolset_20260401",
            "configs": [{"name": "web_search"}, {"name": "web_fetch"}],
        }
    ],
    betas=BETAS,
)
print(f"{analyst.name}: {analyst.id} v{analyst.version}")
```

??? note "輸出"

    ```text
    market_analyst: agent_staging_014U3BWzuiSNDwfzubN38hnz v1
    ```

## 3. 建立有預算的 session

`sessions.create` 的 `budget` 欄位設定上限：

```json
{"type": "limit", "max_list_cost": {"currency": "USD", "amount": "10"}}
```

選數字之前有幾點要知道：

- `amount` 是以該幣別最小單位表示的整數字串：`"50"` 是 50 美分，`"2500"` 是 25.00 美元。它必須維持字串，小數的分會被拒絕，所以不會有浮點數捨入。只接受 `USD`，API 回傳的所有成本金額（包括 `usage.list_cost`）都用同樣的編碼。
- 上限計算的是 model token 成本，用公開 list price，加總 session 內每個 thread，包括 subagent thread。不管你有沒有談到折扣，一律用 list price，所以上限會在實際收費當下或之前觸發，你也可以用 `session.usage` 加公開費率表重現這個數字。
- Session 可能用到的每個 model 都要有公開 list price，沒有的話建立會失敗，錯誤為 `model_not_budgetable`。
- 不設 `budget` 就是沒有上限。Budget 只能在建立時附加：沒有預算的 session 之後不能再加，所以要事先決定。

這裡的上限是 10 美分，刻意設很低，讓停止在幾分鐘內就出現。`usd` helper 會把最小單位的金額轉成美元，下面所有輸出都用它。

```python
from decimal import Decimal


def usd(money) -> str:
    """Render an integer minor-unit amount ("50" = fifty cents) as dollars."""
    return f"${Decimal(money.amount) / 100:.2f}"


session = client.beta.sessions.create(
    agent=analyst.id,
    environment_id=env.id,
    title="Landscape brief: observability platforms",
    budget={
        "type": "limit",
        "max_list_cost": {"currency": "USD", "amount": "10"},
    },
    initial_events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": "Write a competitive landscape brief on the observability "
                    "platform market: the main vendors, how each positions itself, "
                    "and any notable moves in the last year.",
                }
            ],
        }
    ],
    betas=BETAS,
)
print(session.id, session.status)
print("budget:", usd(session.budget.max_list_cost))
```

??? note "輸出"

    ```text
    sesn_staging_01ELJgA2vqTR6EmjX8viwHZi running
    budget: $0.10
    ```

## 4. 觀察花費累積

除了一般的 `agent.message` 跟 `agent.tool_use` event，每次 session 回到 `idle` 時，stream 都會送一個 `session.usage` snapshot。裡面有累計的 token 數、追蹤到的 `list_cost`，以及設定的 `budget`，所以這一輪一結束，你不用再呼叫 `sessions.retrieve` 就知道花了多少。

Loop 在 `session.status_idle` 時結束。有預算的情況下，結束一輪的停止原因有兩種：agent 做完時是 `end_turn`，上限先觸發時是 `budget_reached`。

```python
stop_reason = None

with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "agent.tool_use":
            print(f"[{ev.name}] {str(ev.input)[:80]}")
        elif ev.type == "session.usage":
            print(f"  usage: {usd(ev.usage.list_cost)} of {usd(ev.budget.max_list_cost)}")
        elif ev.type == "session.status_idle":
            stop_reason = ev.stop_reason.type
            print(f"[idle] stop_reason={stop_reason}")
            break

assert stop_reason == "budget_reached", (
    f"expected budget_reached, got {stop_reason}: lower the cap in step 3 "
    "or give the agent a bigger task"
)
```

??? note "輸出"

    ```text
    [repl] {'script': '\nlet queries = [\n  "Datadog positioning observability platform 202
    [web_search] {'query': 'Datadog positioning observability platform 2025'}
    [web_search] {'query': 'New Relic observability platform positioning 2025'}
    [web_search] {'query': 'Dynatrace observability platform AI 2025'}
    [web_search] {'query': 'Splunk Cisco observability 2025'}
    [web_search] {'query': 'Grafana Labs observability platform 2025 announcement'}
    [web_search] {'query': 'Elastic observability 2025'}
    [web_search] {'query': 'Honeycomb observability 2025'}
    [web_search] {'query': 'Chronosphere observability 2025 acquisition'}
    [web_search] {'query': 'Datadog acquisition 2024 2025'}
    [web_search] {'query': 'Grafana Labs acquisition 2024 2025'}
    ```

    ```text
      usage: $0.12 of $0.10
    [idle] stop_reason=budget_reached
    ```

## 5. 檢查暫停的 session

`budget_reached` 是暫停，不是失敗。Session 停在 `idle`，`usage` 反映到目前為止的所有花費，container 裡仍保有 agent 在上限觸發前寫的東西。什麼都不用重跑。

上限是在 model request 之間檢查的，所以記錄到的 `list_cost` 可能稍微超過 `max_list_cost`：跨過線的那個 request 會完成，然後 session 才暫停。設上限時要把這一個 request 的誤差算進去。

```python
paused = client.beta.sessions.retrieve(session.id, betas=BETAS)

print("status:      ", paused.status)
print("list cost:   ", usd(paused.usage.list_cost))
print("cap:         ", usd(paused.budget.max_list_cost))
print("tokens:       in", paused.usage.input_tokens, "out", paused.usage.output_tokens)
print("active secs: ", round(paused.usage.active_seconds, 1))
```

??? note "輸出"

    ```text
    status:       idle
    list cost:    $0.12
    cap:          $0.10
    tokens:       in 471 out 606
    active secs:  13.7
    ```

Event log 會顯示 agent 做到哪：它呼叫過的 tool，以及如果已經開始說明，它最後的訊息。深入研究中的 agent 可能在上限觸發時還什麼都沒寫，所以訊息要當作選擇性的。

```python
events = list(client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS))
tool_calls = [ev for ev in events if ev.type == "agent.tool_use"]
messages = [ev for ev in events if ev.type == "agent.message"]

print(f"tool calls before the cap: {len(tool_calls)}")
if messages:
    last = messages[-1]
    print("".join(b.text for b in last.content if b.type == "text")[:600])
else:
    print("(no agent.message yet: the agent was still gathering sources when the cap fired)")
```

??? note "輸出"

    ```text
    tool calls before the cap: 11
    (no agent.message yet: the agent was still gathering sources when the cap fired)
    ```

## 6. 調高上限讓它做完

`sessions.update` 接受同樣形狀的 `budget`。把 `max_list_cost` 調到高於已花費的成本，就會解除暫停，session 會自己從停下來的狀態繼續被中斷的那一輪。

把上限調到小於或等於 session 已花費的金額會被 400 拒絕：`max_list_cost` 必須高於已消耗的 list cost，所以更新永遠不會讓 session 卡在自己的歷史上。第一個呼叫示範被拒絕，第二個才真的調高上限。調高之後不需要再送訊息，session 會回到 `running`，接續被中斷的那一輪。

```python
try:
    client.beta.sessions.update(
        session.id,
        budget={"type": "limit", "max_list_cost": {"currency": "USD", "amount": "1"}},
        betas=BETAS,
    )
except anthropic.BadRequestError as e:
    print("lower rejected:", e.message)

client.beta.sessions.update(
    session.id,
    budget={"type": "limit", "max_list_cost": {"currency": "USD", "amount": "500"}},
    betas=BETAS,
)
print("cap raised to $5.00")
```

??? note "輸出"

    ```text
    lower rejected: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': "`budget.max_list_cost` must be greater than the session's consumed list cost"}, 'request_id': 'req_staging_011CdiPi8iPJKWdiuurZuDkB'}
    ```

    ```text
    cap raised to $5.00
    ```

```python
with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "session.status_running":
            print("[resumed]")
        elif ev.type == "agent.tool_use":
            print(f"[{ev.name}]")
        elif ev.type == "session.status_idle":
            print(f"[idle] stop_reason={ev.stop_reason.type}")
            break

done = client.beta.sessions.retrieve(session.id, betas=BETAS)
print("final list cost:", usd(done.usage.list_cost), "of cap", usd(done.budget.max_list_cost))
```

??? note "輸出"

    ```text
    [resumed]
    ```

    ```text
    [repl]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    [web_search]
    ```

    ```text
    [repl]
    [web_fetch]
    [web_fetch]
    [web_fetch]
    [web_fetch]
    [web_fetch]
    [web_fetch]
    [web_fetch]
    [web_fetch]
    ```

    ```text
    [repl]
    [web_fetch]
    ```

    ```text
    [web_fetch]
    [web_fetch]
    ```

    ```text
    [web_fetch]
    ```

    ```text
    [web_fetch]
    [web_fetch]
    ```

    ```text
    [web_fetch]
    [web_fetch]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [bash]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [web_search]
    ```

    ```text
    [repl]
    [web_fetch]
    ```

    ```text
    [web_fetch]
    ```

    ```text
    [web_fetch]
    ```

    ```text
    [web_fetch]
    ```

    ```text
    [repl]
    [web_fetch]
    ```

    ```text
    [web_fetch]
    [web_fetch]
    ```

    ```text
    [write]
    ```

    ```text
    [write]
    ```

    ```text
    [bash]
    ```

    ```text
    [idle] stop_reason=end_turn
    ```

    ```text
    final list cost: $1.83 of cap $5.00
    ```

## 7. 讀簡報

Agent 帶著完整的 context 接續工作，並完成了寫入。從 event log 取出它產生的檔案。

```python
brief = ""
for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS):
    if (
        ev.type == "agent.tool_use"
        and ev.name == "write"
        and ev.input.get("file_path", "").endswith("brief.md")
    ):
        brief = ev.input["content"]  # keep the last write, in case of revisions

print(brief[:1500] + ("\n..." if len(brief) > 1500 else ""))
```

??? note "輸出"

    ```text
    # Competitive Landscape Brief: Observability Platform Market

    *Scope: commercial platforms for metrics, logs, traces, and related telemetry (APM, infrastructure monitoring, log management, digital experience monitoring) used by engineering, IT operations, and SRE teams. Window for "recent moves": roughly the last twelve months of vendor activity found in primary sources (mid‑2025 through mid‑2026).*

    ## 1. Market shape

    Observability has consolidated into a market with a handful of large, broad "full platform" vendors (Datadog, Splunk/Cisco, Dynatrace, New Relic, Elastic, Grafana Labs), a tier of cost‑ and scale‑focused challengers (Chronosphere, Coralogix, Honeycomb, SolarWinds, LogicMonitor, Sumo Logic), hyperscaler-native tooling bundled into the cloud platforms (AWS CloudWatch, Azure Monitor, Google Cloud Observability), and an open standard — OpenTelemetry — that now sits underneath almost every vendor's ingestion layer and was elevated to CNCF "graduated" status, cementing it as the de facto instrumentation standard (CNCF, announcement). Gartner's 2025 Magic Quadrant for Observability Platforms evaluated 20 vendors (AWS, Apica, BMC Helix, Chronosphere, Coralogix, Datadog, Dynatrace, Elastic, Grafana Labs, Honeycomb, IBM, ITRS, LogicMonitor, Microsoft, New Relic, Oracle, ScienceLogic, SolarWinds, Splunk, Sumo Logic), naming Datadog, Splunk, Dynatrace, New Relic, Elastic, Grafana Labs, Chronosphere, and IBM as Leaders (Gartner, 7 July 2025; corroborated by Datadog, Splunk
    ...
    ```

## 8. 移除預算

更新時傳 `budget=None` 會清除上限，之後這個 session 就沒有上限。完全省略 `budget` 則保留現有上限。這是兩種不同的請求：`None` 是明確移除，沒傳是保留。

移除是永久的，跟只能在建立時附加是同樣的理由：session 一旦沒有預算，就不能再加上。上限可以隨意調高調低，但移除要當作單向門。

```python
uncapped = client.beta.sessions.update(session.id, budget=None, betas=BETAS)
print("budget:", uncapped.budget)
```

??? note "輸出"

    ```text
    budget: None
    ```

## 9. 清理

```python
from utilities import wait_for_idle_status

wait_for_idle_status(client, session.id)
client.beta.sessions.archive(session.id, betas=BETAS)
client.beta.environments.archive(env.id, betas=BETAS)
print("archived")
```

??? note "輸出"

    ```text
    archived
    ```

## Budget 適合用在哪

Budget 是針對單一 session 的控制，限制的是一次執行，不是整個組織、workspace 或一天的流量，所以它跟你已經在那些層級設的花費限制是疊加的，不是取代。只要 session 在沒人看著的情況下跑，就該用它：cron 排程的部署、webhook 觸發的 agent、coordinator 展開多少工作取決於資料的長時間 multiagent 工作。

如果是沒有在 stream 的大量 session，改訂閱 `session.budget_reached` webhook，不用一直開著連線。它會在 session 達到上限時觸發一次，payload 會指出是哪個 session，讓 supervisor 程序決定要調高上限還是讓 session 繼續暫停。Webhook 模式在 [`CMA_operate_in_production.ipynb`](CMA_operate_in_production.md) 有講。

## 重點整理

- Budget 是對單一 session 強制執行的花費上限，用公開 list price 計算所有 thread 的 token 成本。
- 達到上限是暫停（`budget_reached`），不是失敗，檔案、tool 狀態、對話都保留。
- 上限在 model request 之間檢查，實際花費可能多出一個 request，設值時要留餘裕。
- Budget 只能在建立時附加；之後可以調高調低，也可以移除，但移除後不能再加回來。
- 無人看管的 session 一律建議設 budget，並搭配 `session.budget_reached` webhook 做監督。

## 練習

1. 把 `amount` 從 `"10"` 改成 `"5"`，觀察停止會在多早出現，以及最後的 `list_cost` 超出多少。
2. 在 session 暫停後，先試著把上限調到低於已花費金額，確認收到 400，再調高到能完成。
3. 在做完後用 `budget=None` 移除預算，再嘗試重新設定一個 budget，看 API 回什麼。
