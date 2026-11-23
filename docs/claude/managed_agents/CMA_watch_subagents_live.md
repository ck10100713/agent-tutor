---
translated: true
source: managed_agents/CMA_watch_subagents_live.ipynb
---
# Multiagent：即時觀看課程設計團隊工作

> 原文：[managed_agents/CMA_watch_subagents_live.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_watch_subagents_live.ipynb)

用 per-thread 的 event deltas 即時串流 coordinator 和它的 subagents，用 initial_events 在建立 session 時就帶入第一則訊息，替每個 agent 設定模型 effort，並且更新 agent 時不用先取版本號。

## 這篇在做什麼

coordinator 把工作委派給 subagents 時，你會看不到 subagent 的進度，因為它的輸出要整輪結束才看得到。這篇組合四個 Managed Agents API 功能，讓每個 subagent 的文字能在自己的 stream 上即時預覽，並用一個規劃七年級科學單元的團隊來示範。

## 學完你會

- 為每個 thread 各開一個串流，用 `event_deltas` 即時看 coordinator 和各個 subagent 的文字，並用 accumulator 跟最後的正式事件對帳
- 用 `initial_events` 讓 session 建立當下就開始工作，並用 `model.effort` 對不同角色設定不同成本
- 用不帶 `version` 的 `agents.update` 改 prompt，並知道 multiagent 的 roster 為什麼要連 coordinator 一起更新

## 開跑前

需要有 Managed Agents beta 權限的 Anthropic API key，以及 `anthropic>=0.118.0`。researcher 用 web search，會產生額外的工具與 token 費用。

coordinator 把工作委派給 subagents 時，有一個可觀測性的缺口。session 層級的 stream 會在模型生成時預覽主 thread 的文字，但 subagent 的輸出要等它整輪都緩衝完才看得到。如果 researcher 跑了兩分鐘，你就會盯著空白看兩分鐘。

這個 notebook 組合四個 Managed Agents API 功能來補這個缺口：

- **Per-thread delta 串流。** 每個 session thread 的 stream 接受跟 session 層級 stream 相同的 `event_deltas` 參數，所以 subagent 的文字能在自己的 stream 上即時預覽。
- **建立 session 時的 initial events。** `sessions.create` 接受 `initial_events`，所以 session 在建立它的同一個呼叫裡就開始工作。
- **模型上的 effort。** `model.effort` 設定 Claude 每次推論呼叫要多努力，每個 agent 各自設定。在團隊裡，這是每個角色的成本槓桿。
- **agent update 的 version 變成選用。** `agents.update` 把目前的 version 當成選用的並行控制 key，而不是必填。

你要建的團隊規劃一個為期一週的七年級科學單元：coordinator 委派給一個標準研究員（web search、高 effort）和一個課程撰寫者（不能上網），再組裝出單元計畫。如果 `multiagent` coordinator 模式對你還陌生，先看 [`CMA_coordinate_specialist_team.ipynb`](CMA_coordinate_specialist_team.md)，這個 notebook 是建立在那些結構上。

## 1. 設定 client

這些功能都走標準的 `managed-agents-2026-04-01` beta header。這個 notebook 裡的 SDK 呼叫（`sessions.create` 的 `initial_events`、thread stream 的 `event_deltas`、`model.effort`）需要 `anthropic>=0.118.0`。

```python
%%capture
%pip install -qU "anthropic>=2.0.0" python-dotenv
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

## 2. 建立兩位專家

researcher 拿到 web search 和 `high` 的 effort，因為標準對齊是很吃判斷的工作：它要衡量哪些 performance expectations 真的適合這個單元，而不是把找到的全部列出來。`effort` 放在 `model` 物件裡，接受 `low`、`medium`、`high`、`xhigh` 或 `max`（可以是純字串，也可以是 `{"type": "high"}`）。不是每個模型都接受每個等級，無效的組合在建立時就會被拒絕。

effort 也是團隊主要的成本槓桿：較高的等級讓 Claude 每次推論呼叫可以花更多 token，較低的等級則壓低花費。因為是每個 agent 各自設定，你只替需要深度的角色買深度。在更大的團隊裡，格式整理或分流的角色可以降到 `low`，不用動 researcher 的預算。

effort 要設在 agent 上，不是 per-session：放在 per-session `model` override 裡的 `effort` 不會生效。

web tools 的設定也接受允許與封鎖的網域清單，所以正式部署可以把這個 researcher 限制在它該信任的標準網站。設定格式見 [Configuring the toolset](https://platform.claude.com/docs/en/managed-agents/tools#configuring-the-toolset)。

```python
RESEARCHER_SYSTEM = """You research US middle school science standards.
Given a unit topic and grade level, use web search to find:
- The two or three NGSS performance expectations the unit should target
- What students are expected to already know, and where the topic leads next
- Two or three documented student misconceptions for the topic
Return via send_to_parent:
{"standards": [...], "prior_knowledge": ..., "leads_to": ...,
 "misconceptions": [...], "sources": [...]}"""

standards_researcher = client.beta.agents.create(
    name="standards_researcher",
    description="Finds the NGSS standards and documented misconceptions for a science topic.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-watch-subagents-live"},
    model={"id": MODEL, "effort": "high"},
    system=RESEARCHER_SYSTEM,
    tools=[
        {
            "type": "agent_toolset_20260401",
            "configs": [{"name": "web_search"}, {"name": "web_fetch"}],
        }
    ],
    betas=BETAS,
)
```

課程撰寫者只根據 coordinator 交給它的內容工作。停用 web tools，可以讓它的課程建立在 researcher 審過的發現上，而不是新搜尋到的任何東西。

```python
WRITER_SYSTEM = """You write middle school lesson plans.
You will be given a topic, grade level, target standards, and known misconceptions.
Draft five 45-minute lessons, one per day. For each day give:
- Objective (tied to a target standard)
- Warm-up (5 min)
- Main activity (30 min)
- Exit ticket (one question that probes a misconception where possible)
Return via send_to_parent: {"days": [{"day": 1, "objective": ..., "warm_up": ...,
"main_activity": ..., "exit_ticket": ...}, ...]}"""

lesson_writer = client.beta.agents.create(
    name="lesson_writer",
    description="Drafts a day-by-day lesson sequence from standards and misconceptions.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-watch-subagents-live"},
    model={"id": MODEL},
    system=WRITER_SYSTEM,
    tools=[
        {
            "type": "agent_toolset_20260401",
            "configs": [
                {"name": "web_search", "enabled": False},
                {"name": "web_fetch", "enabled": False},
            ],
        }
    ],
    betas=BETAS,
)
```

建立的回應會回傳解析後的模型設定，包含你省略的欄位。researcher 顯示你設的 `high`，writer 顯示模型預設的 effort。如果 `effort` 回傳 `None`，代表你組織的 beta header 還沒帶這個功能：欄位是被丟掉，不是被拒絕，所以這個回傳值是抓出這件事的地方。

```python
for agent in (standards_researcher, lesson_writer):
    effort = getattr(agent.model, "effort", None)
    print(f"{agent.name}: {agent.id} v{agent.version} effort={effort and effort.type}")
```

## 3. 建立 coordinator

coordinator 帶著 `multiagent` roster。spawn 和委派的 tools 會從 roster 自動注入，而且 roster 會把每個子 agent 釘在目前的版本。這個釘選之後在你更新 researcher 時很重要。

```python
COORDINATOR_SYSTEM = """You plan one-week teaching units.
Given a topic and grade level:
1. Send the topic and grade to standards_researcher.
2. When the researcher reports back, send the topic, grade, target standards, and
misconceptions to lesson_writer.
3. Write /mnt/session/outputs/unit_plan.md with sections: Overview, Standards alignment,
Day-by-day plan (from the writer), Misconceptions to watch for, Materials.
Keep it under three pages. To revise the plan, rewrite the whole file with the write
tool rather than patching it with edit. While a subagent is working, wait silently: no
status commentary until its report arrives."""

coordinator = client.beta.agents.create(
    name="unit_planner",
    description="Plans one-week teaching units by delegating research and drafting.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-watch-subagents-live"},
    model={"id": MODEL},
    system=COORDINATOR_SYSTEM,
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "coordinator",
        "agents": [standards_researcher.id, lesson_writer.id],
    },
    betas=BETAS,
)
print(f"{coordinator.name}: {coordinator.id} v{coordinator.version}")
```

## 4. 啟動 session，第一則訊息內嵌

沒有 `initial_events` 的話，啟動 session 要兩次呼叫：先建立，再送一則 `user.message`。在建立時帶入第一則訊息，就把它合成一次。這個陣列最多接受 50 個 `user.message` 和 `user.define_outcome` 事件，依序處理，驗證是全有或全無：任何一個事件失敗，就不會建立 session。非空的清單會在同一個呼叫裡啟動 agent loop，所以 session 回來時已經朝 `running` 前進了。

如果你想讓單元計畫對照 rubric 評分，在這裡加一個 `user.define_outcome` 事件（必須包含 `rubric`，每次建立只允許一個）。[`CMA_verify_with_outcome_grader.ipynb`](CMA_verify_with_outcome_grader.md) 講的就是那個迴圈。

```python
import time

env = client.beta.environments.create(
    name="curriculum-studio",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
    betas=BETAS,
)

session = client.beta.sessions.create(
    agent=coordinator.id,
    environment_id=env.id,
    title="Unit plan: water cycle, grade 7",
    initial_events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": "Plan a one-week unit on the water cycle for 7th grade science. "
                    "Classes are 45 minutes. Write the plan to /mnt/session/outputs/unit_plan.md.",
                }
            ],
        }
    ],
    betas=BETAS,
)

deadline = time.monotonic() + 60
while session.status == "idle" and time.monotonic() < deadline:
    time.sleep(1)
    session = client.beta.sessions.retrieve(session.id, betas=BETAS)

print(f"{session.id}: {session.status}")
if session.status == "idle":
    events = client.beta.sessions.events.list(session.id, limit=1, betas=BETAS)
    if next(iter(events), None) is None:
        raise RuntimeError(
            "The session has no events: your organization's beta header does not carry "
            "initial_events yet. The field is dropped at the gateway, not rejected."
        )
    raise RuntimeError(
        "The seeded message is in the event log but the session is still idle after 60s. "
        "Re-run this cell to keep waiting."
    )
```

## 5. 即時看整個團隊

預覽在設計上是限定 thread 的。一個連線只預覽它讀的那個 thread：session 層級的 stream 預覽主 thread，子 agent 的預覽只出現在它自己 stream 的 `GET /v1/sessions/{session_id}/threads/{thread_id}/stream`。所以模式是每個 thread 一個 stream：用 session 層級的 stream 讀 coordinator，每當 `session.thread_created` 事件宣告一個子 agent（帶著 `session_thread_id` 和 `agent_name`），就在背景 thread 裡接上那個 thread 的 stream 的 watcher。

有兩條規則形塑了程式碼：

- **預覽是草稿緩衝，緩衝完的事件才是正式紀錄。** delta 是盡力而為，高負載時可能中斷。後面接著來的緩衝 `agent.message` 帶著完整內容。SDK 的 `accumulate_managed_agents_event` helper 會把 `event_start`、`event_delta` 和緩衝事件合併成一份快照，正式紀錄一到就取代預覽。每個 stream 連線跑一個 accumulator。
- **不重播。** 在模型請求開始之後才開的連線，收不到那個進行中請求的 deltas，重連也不會重播漏掉的 deltas。在 `session.thread_created` 到達時就立刻接上 watcher，才能從子 agent 的第一個回應起就抓到它的工作。

每個 watcher 在 `session.thread_status_idle` 時結束，這是子 agent 的這一輪完成時發出的事件。

```python
import threading

from anthropic.lib.sessions import accumulate_managed_agents_event

print_lock = threading.Lock()
current_speaker = None
reconciliations = []


def say(speaker, text):
    """Print streamed text, labeling it whenever the speaker changes."""
    global current_speaker
    with print_lock:
        if speaker != current_speaker:
            print(f"\n\n=== {speaker} ===")
            current_speaker = speaker
        print(text, end="", flush=True)


def text_of(event):
    if event is None:
        return ""
    return "".join(block.text for block in event.content if block.type == "text")


def fold_preview(snapshot, ev, speaker):
    """Fold one preview event into the speaker's snapshot and return the new snapshot.

    Prints delta text as it arrives. When the buffered record lands, logs a
    reconciliation row comparing it against the accumulated preview. The id
    check guards the case where every delta for a message was shed: the
    snapshot then still holds the previous message, not a preview of this one.
    """
    if ev.type == "event_delta":
        say(speaker, ev.delta.content.text)
    elif ev.type == "agent.message":
        preview = text_of(snapshot) if snapshot and snapshot.id == ev.id else ""
        final = text_of(ev)
        reconciliations.append((speaker, len(preview), len(final), final.startswith(preview)))
    return accumulate_managed_agents_event(snapshot, ev)


def watch_child(thread_id, agent_name):
    """Stream one child thread, previewing its text as the model generates it."""
    snapshot = None
    with client.beta.sessions.threads.events.stream(
        thread_id,
        session_id=session.id,
        event_deltas=["agent.message"],
        betas=BETAS,
    ) as thread_stream:
        for ev in thread_stream:
            if ev.type in ("event_start", "event_delta", "agent.message"):
                snapshot = fold_preview(snapshot, ev, agent_name)
            elif ev.type == "agent.tool_use":
                detail = ev.input.get("query", "") if ev.name == "web_search" else ""
                say(agent_name, f"\n[{ev.name}] {detail}")
            elif ev.type in ("session.thread_status_idle", "session.thread_status_terminated"):
                break
```

主迴圈把同一個 `fold_preview` 用在 coordinator 的文字上，另外加上只出現在主 thread 的協調事件：子 agent 生出時的 `session.thread_created`、coordinator 交辦任務時的 `agent.thread_message_sent`、子 agent 回報時的 `agent.thread_message_received`。從子 thread 交叉貼上來的 tool 呼叫帶有 `session_thread_id`，所以迴圈會略過它們：子 agent 自己的 watcher 會顯示。

迴圈在任何 `session.status_idle` 結束，stop reason 不是 `end_turn` 時會印出來：等待 tool 確認或重試耗盡的 session 應該讓 cell 結束，而不是卡住。兩個迴圈也會在 terminated 狀態事件時中斷，所以無法恢復的 session 錯誤會結束 cell，而不是讓 stream 一直開著。

```python
watchers = []
snapshot = None

with client.beta.sessions.events.stream(
    session.id, event_deltas=["agent.message"], betas=BETAS
) as stream:
    for ev in stream:
        if ev.type in ("event_start", "event_delta", "agent.message"):
            snapshot = fold_preview(snapshot, ev, "unit_planner")
        elif ev.type == "session.thread_created":
            say("unit_planner", f"\n[spawned {ev.agent_name}]")
            watcher = threading.Thread(
                target=watch_child,
                args=(ev.session_thread_id, ev.agent_name),
                daemon=True,
            )
            watcher.start()
            watchers.append(watcher)
        elif ev.type == "agent.thread_message_sent":
            say("unit_planner", f"\n[task sent to {ev.to_agent_name}]")
        elif ev.type == "agent.thread_message_received":
            say("unit_planner", f"\n[{ev.from_agent_name} reported back]")
        elif ev.type == "agent.tool_use" and not ev.session_thread_id:
            # session_thread_id marks a call cross-posted from a child thread;
            # that child's watcher already shows it
            say("unit_planner", f"\n[{ev.name}]")
        elif ev.type == "session.status_terminated":
            break
        elif ev.type == "session.status_idle":
            if ev.stop_reason.type != "end_turn":
                say("unit_planner", f"\n[idle without end_turn: {ev.stop_reason.type}]")
            break

for watcher in watchers:
    watcher.join(timeout=60)
if any(watcher.is_alive() for watcher in watchers):
    print("\n[a child stream is still open after the join timeout]")
```

如果 stream 連上了卻只送來緩衝事件，代表 `event_deltas` 參數是被剝掉而不是被拒絕：這是 beta header 沒帶這個功能的特徵。thread stream URL 回 404，代表路徑錯誤或缺少 managed-agents beta header（thread endpoints 要有 beta 才能用）。正確路徑是 `/threads/{thread_id}/stream`，不是 `/threads/{thread_id}/events/stream`。

完整的串流規格（delta 的形狀、對帳保證、疑難排解表）在 [events and streaming](https://platform.claude.com/docs/en/managed-agents/events-and-streaming#event-deltas)。

## 6. 把預覽對照正式紀錄

把一份預覽的 deltas 串起來，得到的是緩衝事件文字的前綴：是前綴，不一定是全部，因為高負載時 deltas 可能被丟掉。這個保證讓對帳可以只做一次取代。下面每一列是一個緩衝的 `agent.message`，跟 accumulator 在正式紀錄到達時已經建出的預覽做比對。

```python
for agent_name, preview_chars, final_chars, is_prefix in reconciliations:
    print(
        f"{agent_name:22s} preview {preview_chars:5d} chars | "
        f"final {final_chars:5d} chars | preview is prefix: {is_prefix}"
    )
```

## 7. 讀單元計畫

coordinator 的 prompt 要它用整個檔案的 `write` 呼叫來寫計畫，所以完整文件在事件 log 裡，對那個檔案的最後一次 `write` 就是最終版。如果你自己的 agent 是用 `edit` 修補檔案，就直接讀檔案本身，不要重播 writes。

```python
unit_plan = ""
for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS):
    if (
        ev.type == "agent.tool_use"
        and ev.name == "write"
        and ev.input.get("file_path", "").endswith("unit_plan.md")
    ):
        unit_plan = ev.input["content"]  # keep the last write, in case of revisions

# Show the structure rather than the full plan. Print unit_plan to read it all.
for line in unit_plan.splitlines():
    if line.startswith("#"):
        print(line)
```

## 8. 改 prompt 不用走版本往返

假設 review 回饋說每個對齊的論點都需要把標準的代碼放在旁邊。`agents.update` 把 agent 目前的 `version` 當成選用的並行控制 key：省略它，更新就無條件套用，由 server 幫你遞增版本。部署腳本不需要為了寫回去而先讀取 agent。

有可能多個寫入者同時存在時，要帶 `version`（不符時回 409，所以你永遠是從已知狀態更新）。單一流程擁有這個 agent 時可以省略，例如同步已簽入的 agent 定義的 CI job。

```python
updated = client.beta.agents.update(
    standards_researcher.id,
    system=RESEARCHER_SYSTEM
    + "\nCite the performance expectation code (for example MS-ESS2-4) next to every "
    "alignment claim.",
    betas=BETAS,
)
print(f"standards_researcher v{standards_researcher.version} -> v{updated.version}")
```

multiagent 設定有一個注意事項：coordinator 的 roster 在 coordinator 建立時就釘住了 researcher 的版本，所以現有的 coordinator 會繼續委派給舊版本。更新 coordinator（它的 `multiagent` 欄位或任何欄位）會依最新的子 agent 版本重新解析 roster。

## 9. 清理

```python
from utilities import wait_for_idle_status

wait_for_idle_status(client, session.id)
client.beta.sessions.archive(session.id, betas=BETAS)
client.beta.environments.archive(env.id, betas=BETAS)
print("archived")
```

## 重點整理

- session 層級的 stream 只預覽主 thread，子 agent 的即時預覽要在它自己的 thread stream 上，所以要一個 thread 一個 watcher。
- 預覽是草稿，緩衝事件才是正式紀錄；deltas 可能被丟掉，而且不會重播，所以 watcher 要在 `session.thread_created` 到達時馬上接上。
- `initial_events` 把建立 session 和送第一則訊息合成一次呼叫，驗證是全有或全無。
- `effort` 是設在 agent 上的成本槓桿，只替需要深度的角色提高；per-session override 裡的 effort 不會生效。
- `agents.update` 的 `version` 是選用的並行控制，有多個寫入者就帶，單一流程可省；更新子 agent 後要更新 coordinator 才會用新版本。

## 練習

1. 把 lesson writer 的 `effort` 從預設改成 `low`，researcher 維持 `high`，建立後看回傳的模型設定有沒有如預期。
2. 在第 5 節的 watcher 程式裡，只讓 researcher 的 stream 印出預覽，其他 thread 只在 idle 時印一行，比較輸出的差別。
3. 照第 8 節改 researcher 的 prompt 後，先不更新 coordinator 跑一次，再更新 coordinator 跑一次，確認 coordinator 委派的是哪一版。
