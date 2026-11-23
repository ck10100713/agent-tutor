---
translated: true
source: managed_agents/CMA_pin_inference_geo.ipynb
---

# 資料落地：固定 agent 的推論地理位置

> 原文：[managed_agents/CMA_pin_inference_geo.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_pin_inference_geo.ipynb)

用 model.inference_geo 把 Managed Agents 的 agent 固定在美國區域做推論，在 session 上確認這個設定，搭配 workspace 的 allowed_inference_geos 政策，並用 agent_with_overrides 為單一 session 覆寫地理位置。

## 這篇在做什麼

示範如何用 `model.inference_geo` 把 Managed Agents 的 agent 固定在特定地理位置做推論，確保模型請求都在指定區域處理。也講這個設定如何跟 workspace 的資料落地政策互動，以及怎麼為單一 session 覆寫。

## 學完你會

- 把 agent 固定到 `us` 推論，並在 session 上確認這個設定。
- 說明 pin 如何對照 workspace 的 `allowed_inference_geos` 和 `default_inference_geo`，以及更新時哪種寫法會清掉 pin。
- 用 `agent_with_overrides` 為單一 session 覆寫地理位置，不動共用的 agent。

## 開跑前

需要 Anthropic API key、`anthropic>=0.121.0`，並且帳號要能使用 Managed Agents beta。第 4 節提到的 workspace 政策是在 Admin API 設定。

處理受規管資料的 agent，上線前要先回答一個問題：它的模型請求在哪裡執行。如果只在 proxy 或 runbook 裡回答，這個保證就是在強制執行它的系統之外。

`model.inference_geo` 把答案放在 agent 的定義上。它固定服務 agent 模型請求的地理位置，會對照 workspace 的資料落地政策驗證，並在每個回合強制執行，所以這個限制跟著 agent 走，即使 agent 上線後政策改變也依然有效。

這份 notebook 會走過：

- 把 agent 固定到 `us` 推論，並在 session 上確認這個設定
- pin 如何對照 workspace 的 `allowed_inference_geos` 和 `default_inference_geo`
- 會清掉 pin 的更新語意
- 用 `agent_with_overrides` 為單一 session 覆寫地理位置

## 1. 設定 client

`inference_geo` 走標準的 `managed-agents-2026-04-01` beta header，要有型別化的欄位需要 `anthropic>=0.121.0`。

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

## 2. 把 agent 固定到美國推論

`inference_geo` 放在 `model` 設定裡，跟 `effort` 和 `speed` 並列。接受的值是 `"global"` 和 `"us"`。不設定的話，每個模型請求會在被處理的當下解析成你 workspace 的 `default_inference_geo`，這表示之後 workspace 預設值的改變，會影響已經在執行的 session。設定之後，這個 pin 就固定在 agent 上。

這個 pin 會被驗證三次：agent 儲存時、從它建立 session 時、以及該 session 處理的每個回合。它是嚴格強制的，不會網開一面。如果 workspace 管理員事後縮小 `allowed_inference_geos`，從現在不被允許的 agent 建立的新 session 會被拒絕，已經在執行的 session 則會拒絕下一個回合。這種嚴格正是重點：workspace 靠它來確保資料落地，所以即使中途政策改變，pin 也守得住。

```python
researcher = client.beta.agents.create(
    name="us_records_analyst",
    description="Answers questions about internal records, pinned to US inference.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-pin-inference-geo"},
    model={"id": MODEL, "inference_geo": "us"},
    system="You answer questions about the records you are given, concisely.",
    tools=[{"type": "agent_toolset_20260401"}],
    betas=BETAS,
)
print(f"{researcher.name}: {researcher.id} v{researcher.version}")
print("inference_geo:", researcher.model.inference_geo)
```

## 3. 在 session 上確認 pin

Session 在建立時會對 agent 的設定做快照，所以 pin 可以在 `session.agent.model` 上看到。從那裡讀回來，就能確認這個 session 的回合都綁定在 `us`，不受 workspace 今天預設值是什麼影響。

```python
env = client.beta.environments.create(
    name="residency-demo",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
    betas=BETAS,
)

session = client.beta.sessions.create(
    agent=researcher.id,
    environment_id=env.id,
    title="Records question, US-pinned",
    initial_events=[
        {
            "type": "user.message",
            "content": [
                {"type": "text", "text": "In one sentence: what is a data residency policy?"}
            ],
        }
    ],
    betas=BETAS,
)
print("session pin:", session.agent.model.inference_geo)

with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "agent.message":
            print("".join(b.text for b in ev.content if b.type == "text"), end="")
        elif ev.type == "session.status_idle":
            print(f"\n[idle] stop_reason={ev.stop_reason.type}")
            break
```

## 4. Workspace 決定 pin 能指向哪裡

Workspace 的資料落地政策放在 Admin API，位於 workspace 的 `data_residency` 區塊：`allowed_inference_geos`（geo 的清單，或字面值 `"unrestricted"`）和 `default_inference_geo`。除非該欄位是 `"unrestricted"`，否則 agent 的 `inference_geo` 必須是 `allowed_inference_geos` 的成員，否則儲存時會得到 400。在 multiagent roster 中，pin 必須全體一致：coordinator 和每個 roster 成員要不是全部設成同一個 geo，就是全部不設。

還有一個值得釐清的更新細節。在 `agents.update` 時，`model` 是整個被取代而不是合併，所以送 `model` 但不帶 `inference_geo` 就會清掉 pin。要換 model id 又保留地理位置，就要重新寫上它。

```python
cleared = client.beta.agents.update(researcher.id, model={"id": MODEL}, betas=BETAS)
print("after model update without geo:", cleared.model.inference_geo)

researcher = client.beta.agents.update(
    researcher.id,
    model={"id": MODEL, "inference_geo": "us"},  # restate the pin
    betas=BETAS,
)
print("restated:", researcher.model.inference_geo)
```

## 5. 為單一 session 覆寫地理位置

Agent 的 pin 是從它建立的每個 session 的預設值。要讓某個 session 在不同地理位置執行、又不想改共用的 agent，可以在 `sessions.create` 傳入 `agent_with_overrides` 物件並覆寫 `model`。覆寫只取代該 session 的 model 設定，agent 資源不受影響。同樣的成員規則適用：你覆寫成的 geo 必須被 workspace 允許，而且 roster 的成員仍然要全體一致。

```python
override = client.beta.sessions.create(
    agent={
        "type": "agent_with_overrides",
        "id": researcher.id,
        "model": {"id": MODEL, "inference_geo": "global"},  # this session only
    },
    environment_id=env.id,
    title="One-off, global geography",
    betas=BETAS,
)
print("override session pin:", override.agent.model.inference_geo)
print(
    "agent still pinned to:",
    client.beta.agents.retrieve(researcher.id, betas=BETAS).model.inference_geo,
)
```

## 6. 清理

```python
from utilities import wait_for_idle_status

wait_for_idle_status(client, session.id)
for s in (session, override):
    client.beta.sessions.archive(s.id, betas=BETAS)
client.beta.agents.archive(researcher.id, betas=BETAS)
client.beta.environments.archive(env.id, betas=BETAS)
print("archived")
```

## pin 的定位

`inference_geo` 是資料落地和合規的控制項。它不管 agent 能讀什麼或資料存在哪裡，只管它的 token 在哪裡被處理。儲存的地理位置是另一個不可變的 workspace 設定（`workspace_geo`），兩者合起來才能回答合規審查會問的問題。

因為它在每個回合都強制執行，而不只是建立時，所以當保證必須經得起 agent 上線後的變更時，pin 就是對的控制項。對於整批 agent，設定 workspace 的 `default_inference_geo`，讓沒 pin 的 agent 繼承正確的地理位置，並把個別 agent 的 pin 留給資料落地絕不能依賴那個預設值的 agent。

## 重點整理
- `model.inference_geo` 把推論地理位置寫進 agent 定義，限制跟著 agent 走。
- Pin 在儲存、建立 session、每個回合都會嚴格驗證，政策中途改變也會生效。
- 沒設 pin 的 agent，每個請求都解析成當下的 workspace `default_inference_geo`。
- `agents.update` 會整個取代 `model`，漏了 `inference_geo` 就會清掉 pin。
- `agent_with_overrides` 能只改單一 session，不影響共用 agent，但仍須符合 workspace 允許清單和 roster 一致性。

## 練習
1. 建立一個 pin 到 `"us"` 的 agent，建 session 後印出 `session.agent.model` 確認。
2. 用 `agents.update` 只改 model id 但不帶 `inference_geo`，再讀回 agent 確認 pin 被清掉，然後補上重試。
3. 用 `agent_with_overrides` 把某個 session 覆寫成 `"global"`，確認共用 agent 的 pin 沒變。
