---
translated: true
source: managed_agents/CMA_iterate_fix_failing_tests.ipynb
---

# Managed Agents 教學：反覆修到測試通過

> 原文：[managed_agents/CMA_iterate_fix_failing_tests.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_iterate_fix_failing_tests.ipynb)

Claude Managed Agents API 的入門教學。透過讓 agent 修好 calc.py 套件裡三個被故意埋下的 bug，走過 agent / environment / session 的建立、檔案掛載和 streaming event loop。

## 這篇在做什麼

這是入門 notebook。我們用 agent 最常做的一件事來認識 Managed Agents API：試一下、看結果、再試。上傳一個埋了兩個 bug 的小套件，叫 agent 讓測試通過，看它跑測試、讀 traceback、改程式、重跑，直到全綠。

## 學完你會

- 建立 agent、environment、session，並把檔案掛進 session 的容器
- 用 SSE event stream 即時看 agent 的每一步，並在 `end_turn` 時結束
- 獨立驗證 agent 的成果，最後用 archive 收尾

## 開跑前

需要 Anthropic API key，而且帳號要有 Managed Agents 的使用權限。

這個 notebook 是入門篇。你會學到 Managed Agents API 的基本介面，做的是 agent 最普遍的事：試一下、看發生什麼、再試一次。我們上傳一個有兩個埋好 bug 的小套件，叫 agent 讓測試通過，然後看它跑這個 loop：跑測試、讀 traceback、改程式碼、重跑，直到全綠。

過程中你會看到這本 cookbook 其他篇都建立在上面的 API 形狀：agent / environment / session、檔案掛載、event stream 和 archive 呼叫。做完這篇，你就具備端到端驅動一個 agent 所需的一切。

## 概念

要認識三種資源：

- **Agent**：可重複使用的設定（model、system prompt、tools）
- **Environment**：容器模板（套件、網路）
- **Session**：把 agent 和 environment 綁在一起，掛載 agent 需要的檔案，並產生 event stream

agent 和 environment 建一次，就能在很多 session 重複使用。每個 session 是一次獨立的執行。

```python
import os
from pathlib import Path

from anthropic import Anthropic

MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")

client = Anthropic()
FIXTURE = Path("example_data") / "iterate"
```

## 1. 建立 agent

system prompt 刻意寫得很少。我們希望 agent 自己想出 iterate loop，而不是照一步步的腳本走，測試輸出本身就足以讓任務很明確，不用再手把手教。

`agent_toolset_20260401` 是內建的 toolset：bash、read、write、edit、glob、grep、web_fetch 和 web_search。把 `permission_policy` 設成 `always_allow`，agent 執行這些 tool 時就不用來回確認。

```python
agent = client.beta.agents.create(
    name="cookbook-iterate",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-iterate-fix-failing-tests"},
    model=MODEL,
    system=(
        "You are a debugging agent. Your job is to make failing tests pass. "
        "Run the tests, read the failures, fix the code, repeat until green. "
        "Stop when every assertion passes."
    ),
    tools=[
        {
            "type": "agent_toolset_20260401",
            "default_config": {
                "enabled": True,
                "permission_policy": {"type": "always_allow"},
            },
        }
    ],
)
```

## 2. 建立 environment

environment 是容器模板。`type: cloud` 會跑在 Anthropic 代管的 sandbox。`networking: limited` 會擋掉任意的對外流量，這個 notebook 完全不需要網路，所以鎖起來。

```python
env = client.beta.environments.create(
    name="cookbook-iterate-env",
    config={"type": "cloud", "networking": {"type": "limited"}},
)
```

## 3. 上傳會失敗的測試

透過 Files API 上傳檔案取得 ID，第 4 步再把它們掛到 session 上。

`calc.py` 有兩個被埋下的 bug，`test_calc.py` 有三個 assertion 抓得到它們。其中一個失敗（`test_mean`）是另外兩個的下游，這悄悄地教 agent 不要過度修正：`mean()` 內部會呼叫 `add` 和 `divide`，所以那兩個修好後，`test_mean` 自己就會通過，完全不用直接改 `mean()`。

```python
calc_file = client.beta.files.upload(
    file=("calc.py", (FIXTURE / "calc.py").read_bytes(), "text/x-python")
)
test_file = client.beta.files.upload(
    file=("test_calc.py", (FIXTURE / "test_calc.py").read_bytes(), "text/x-python")
)
print(f"uploaded: {calc_file.id}, {test_file.id}")
```

## 4. 建立 session

session 把 agent 和 environment 綁在一起，掛載 agent 需要的檔案，並啟動一個全新的容器。`resources=` 就是在 agent 啟動前把資料放進容器的方式，orchestrate notebook 會示範用同一個欄位 clone GitHub repo，而不是一個個掛檔案。

檔案會掛在 `/mnt/session/uploads/<mount_path>` 底下，這是唯讀的。agent 要先把檔案複製到可寫的目錄（像 `/mnt/user` 或 `/tmp`）才能編輯，之後想取回的東西要放在 `/mnt/session/outputs/`。

```python
session = client.beta.sessions.create(
    environment_id=env.id,
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    resources=[
        {"type": "file", "file_id": calc_file.id, "mount_path": "calc.py"},
        {"type": "file", "file_id": test_file.id, "mount_path": "test_calc.py"},
    ],
    title="Get the tests green",
)
print(f"session: {session.id}")
```

## 5. 驅動 agent 並看它工作

分兩步：送一個帶任務的 `user.message` event，然後讀 event stream 直到 agent 到達 `end_turn`。

stream 是 server-sent event 連線。我們用它（而不是 polling，見最後的補充）是因為 agent 會花約 30 秒反覆嘗試，我們想即時看到每一輪。

要記住兩個模式：

1. **先開 stream，再送。** `with` 區塊會開啟 SSE 連線，在區塊裡 `send` 的東西保證看得到。先送再開，可能會漏掉在空窗期發生的 event。
2. **在 `session.status_idle` 且 `stop_reason.type == "end_turn"` 時離開。** session 只要在等輸入就會進入 idle，包括一輪結束，也包括 custom tool call 需要回應的時候。靠 `stop_reason.type` 區分，`end_turn` 是我們的離開訊號。gate notebook 會示範同一個 loop 的 `requires_action` 那一邊。

```python
with client.beta.sessions.events.stream(session.id) as stream:
    client.beta.sessions.events.send(
        session_id=session.id,
        events=[
            {
                "type": "user.message",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "The tests in /mnt/session/uploads/test_calc.py are "
                            "failing. Copy both files into /mnt/user, iterate "
                            "on calc.py until every test passes, then write the "
                            "final calc.py to /mnt/session/outputs/calc.py. "
                            "pytest isn't installed here, run the assertions "
                            "directly with `python3 -c ...` instead."
                        ),
                    }
                ],
            }
        ],
    )
    print("--- iterate loop ---")
    for ev in stream:
        match ev.type:
            case "agent.message":
                for b in ev.content:
                    if b.type == "text":
                        print(b.text, end="")
            case "agent.tool_use":
                print(f"\n[{ev.name}]")
            case "session.status_idle" if ev.stop_reason and ev.stop_reason.type == "end_turn":
                break
            case "session.status_terminated":
                break
```

那個 `match ev.type:` 區塊就是標準的 streaming 模式。這本 cookbook 其他 notebook 都是從 `utilities.py` import 它，名字是 `stream_until_end_turn`，不再重複寫 loop。下面的 verify 步驟就用它。

`wait_for_idle_status` 是 `utilities.py` 的第二個 helper。它處理第 7 步提示框說的 race：即使 stream 已經送出 `session.status_idle`，session 紀錄上 server 端的 `status` 欄位可能還短暫顯示 `running`，這時馬上呼叫 `archive()` 會得到 400。這個 helper 就是 polling `sessions.retrieve` 直到欄位穩定。先 stream 然後馬上 archive 的程式碼都需要它。

```python
from utilities import stream_until_end_turn, wait_for_idle_status
```

## 6. 驗證

不要直接相信 agent 的話。獨立再跑一次每個 assertion，並印出最後的 `calc.py`。如果 agent 在最後一次 loop 內的測試和這一輪結束之間改過頭或搞壞了什麼，這步會抓到。

```python
client.beta.sessions.events.send(
    session_id=session.id,
    events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Re-run every assertion from "
                        "/mnt/session/uploads/test_calc.py one more time "
                        "against your final calc.py with `python3 -c ...` "
                        "to confirm they all pass, then cat the final "
                        "/mnt/session/outputs/calc.py."
                    ),
                }
            ],
        }
    ],
)
stream_until_end_turn(client, session.id)
```

## 7. 清理

archive 是把 session、environment 或 agent 標記為結束的方式。它會拆掉還活著的容器，讓資源不再計入 workspace 的配額，並從預設的列表隱藏，但會保留紀錄、設定和 event 歷史，供稽核或之後有人想用 ID 取回。想完全移除紀錄的話，大多數資源也有獨立的 `delete` endpoint（operate notebook 會詳細講資源生命週期），但跑完之後幾乎都是用 `archive`。

```python
wait_for_idle_status(client, session.id)
client.beta.sessions.archive(session.id)
client.beta.environments.archive(env.id)
client.beta.agents.archive(agent.id)
print("archived")
```

## 補充：用 polling 取代 streaming

第 5 步的 streaming 模式，適合 agent 要花好幾秒以上、你想看即時進度的情況。任務比較短，或 production 程式不想維持長時間的 HTTP 連線時，可以改用 `events.list` polling 做同樣的事：

```python
client.beta.sessions.events.send(session_id=..., events=[...])
while True:
    time.sleep(2)
    events = client.beta.sessions.events.list(session.id).data
    last = events[-1] if events else None
    if last and last.type == "session.status_terminated":
        break
    if (
        last
        and last.type == "session.status_idle"
        and last.stop_reason
        and last.stop_reason.type == "end_turn"
    ):
        break
# walk events to print agent.message text
```

取捨：

想看 agent 工作時 streaming 比較好。每個 tool call、每段部分訊息、每次狀態轉換，server 一送出就會到，開發新流程時正需要這個。代價是要維持一條長時間的 SSE 連線：你的 process 必須在整輪期間活著，中間不能暫停再恢復，網路在不對的時間點閃一下就可能讓你在 stream 中途斷掉，而且沒有乾淨的方法接回斷點。

polling 則剛好相反。它沒有狀態、process 重啟也撐得住，跟不想掛著連線的 webhook handler 和 queue worker 很好搭。代價是延遲和進度被藏起來：下次 poll 前你什麼都看不到，回饋被 poll 間隔限制住，長時間的一輪在做完前看起來就是一片安靜。

在 production 裡，agent 可能跑好幾分鐘、你的 handler 又不能掛著連線時，要用的就是 polling 模式（或它在 production 的版本，gate notebook 示範的 `session.status_idled` webhook）。

## 接下來看什麼

iterate loop 是 agent loop 最簡單的形狀。同目錄還有四個 notebook 建立在同樣的 API 形狀上，示範你能驅動的其他流程：

- [`CMA_orchestrate_issue_to_pr.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_orchestrate_issue_to_pr.ipynb) — 多輪 agent，在比較長的 tool 鏈裡保留狀態：讀 issue、寫修正、開 PR、從 CI 失敗中恢復、處理 review 意見、最後 merge。
- [`CMA_explore_unfamiliar_codebase.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_explore_unfamiliar_codebase.ipynb) — agent 被丟進從沒看過的 repo 時的 grounding 模式，裡面埋了過時文件的陷阱。也示範用 `sessions.resources.add` 把更多 context 推進執行中的 session。
- [`CMA_gate_human_in_the_loop.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_gate_human_in_the_loop.ipynb) — human-in-the-loop 流程用的 custom tool `decide()` 和 `escalate()` 來回互動。涵蓋 `requires_action` 的 idle 彈回和平行 tool call 去重。
- [`CMA_operate_in_production.ipynb`](CMA_operate_in_production.md) — production 設定：vault 保管的 MCP 憑證、不用長連線就能做 HITL 的 `session.status_idled` webhook，以及資源生命週期的 CRUD。

## 重點整理

- Agent 是可重用的設定，environment 是容器模板，session 把兩者綁起來並掛載檔案，一次執行就是一個 session
- 先開 SSE stream 再送 `user.message`，才不會漏掉 event；以 `status_idle` 加 `stop_reason.type == "end_turn"` 判斷結束
- agent 自己能跑「測試、讀錯誤、修改、重跑」的 loop，system prompt 不用寫步驟
- 不要信 agent 的自我回報，結束後獨立再驗證一次
- 收尾用 `archive`，保留紀錄但釋放資源；短任務或無法掛長連線時改用 polling

## 練習

1. 把 session 建立時的 `networking` 設定留著不動，改 system prompt，要求 agent 每次修改後先說明原因，看 stream 輸出的變化。
2. 在上傳的 `test_calc.py` 多加一個 assertion（例如 `multiply`），觀察 agent 會不會順手修到對應的 bug。
3. 把第 5 步的 streaming 換成 sidebar 的 `events.list` polling，自己設定 poll 間隔，比較看到進度的延遲。
