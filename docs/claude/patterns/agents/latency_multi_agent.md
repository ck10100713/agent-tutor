---
translated: true
source: patterns/agents/latency_multi_agent.ipynb
---
# 在延遲壓力和預算下運作的 multi-agent 團隊

> 原文：[patterns/agents/latency_multi_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/latency_multi_agent.ipynb)

這是 lead 加 helpers 的 agent 團隊起手程式，團隊共用一個 wall-clock，並提供兩種讓「時間」產生影響的方式：一句「時間很重要」的提示，或是在時鐘那一行加上延遲預算。

## 這篇在做什麼

一個 lead agent 可以生出 helper agent 平行處理任務的各個部分。這種團隊放著不管會偏向求完整而不是求快，因為任何 agent 的 context 裡都沒有提到提問的人已經等了多久、願意等多久。這篇用 Messages API 讓 Claude 知道時間過了多少，讓任務更快完成。

## 學完你會

- 讓團隊裡每個 agent 看到同一個跑動中的時鐘，而且不破壞 prompt caching
- 用一句延遲壓力的提示加速團隊，或讓團隊對著延遲預算調整節奏
- 從一次執行自己的 log 檢查每個 agent 都真的看到了時鐘

## 開跑前

- 需要 `ANTHROPIC_API_KEY`（或 `.env` 檔）和一些 API 額度。一次執行是一個 lead 加最多四個 helper，預設模型 `claude-fable-5-1`、effort `xhigh`，整支 notebook 跑完約一分鐘。
- 最多五個 agent 同時打 API，rate limit 較低的話，SDK 自動重試會變成額外的等待時間。

我們先只用 Messages API 讓 Claude 知道已經過了多久：

1. **一個共用的團隊時鐘**，任務開始時啟動。
2. **每個 agent 在每一輪之前都會看到時鐘。** 每次替任何 agent 呼叫 API，我們都在最新那則 user message 的結尾加一行短短的 `[elapsed 252s]`（第一輪是 task prompt，之後是 tool results）。任務開始三分鐘後才生出來的 helper，第一輪看到的是 `[elapsed 182s]` 而不是 `0s`，因為時鐘屬於團隊，不屬於單一 agent。

接著用兩種方式讓 Claude 有急迫感：

1. **延遲壓力：** 在 task prompt 和每個 helper 的 brief 結尾各加一句話，說明時間很重要。這句話是跟原本 prompt 唯一的差別。
2. **延遲預算：** 時鐘那一行除了已過時間，還帶著預算，例如 `[elapsed 252s / 600s]`。不加任何 prompt 文字，第二個數字就是 agent 得知預算的唯一管道。

這就是整個機制，可以拿來比較三種做法：完全沒有時鐘、時鐘加壓力、時鐘加預算。

> **關於模型。** 用延遲誘因來引導 Claude 是剛出現的做法。這個 notebook 預設用 `claude-fable-5-1`，在 Claude Opus 5 和更早的模型上還沒完整測試過，改掉 `COOKBOOK_MODEL` 的話效果可能不一樣。

這裡沒有內建任務，工具、prompt 和問題都由你自己帶。最後有個簡短的 smoke test，用來確認時鐘有送到每個 agent。

orchestration 的部分（message hub、messaging tools、spawn tools、agent loop）沿用 [Async multi-agent orchestration](async_multi_agent_orchestration.md) 這篇，不熟悉整體架構的話先看那篇。

## 前置需求

- Python 3.11 以上。
- 需要的知識：看得懂 `async`/`await` 的 Python（tasks、events、timeouts），也熟悉 Messages API 的 tool-use loop（一輪模型回應、它的 tool calls、你送回去的 tool results）。團隊運作的機制在 [Async multi-agent orchestration](async_multi_agent_orchestration.md) 有講。
- 把 Claude API key 放在 `ANTHROPIC_API_KEY`（或 `.env` 檔）。
- 一些 API 額度。每次執行是一個 lead 加最多四個 helper，每個都會呼叫好幾次。我們把呼叫次數上限設成每個 helper 十五次、lead 四十次。整支 notebook 從頭跑到尾，是在 `claude-fable-5-1`、effort `xhigh` 下跑一次短的團隊任務，大約一分鐘。
- rate limit 要有餘裕。最多五個 agent 同時打 API，在較低的 tier，SDK 的自動重試會表現成額外的 wall-clock 時間，而不是錯誤。

```python
%%capture
%pip install -qU anthropic python-dotenv
```

```python
import asyncio
import itertools
import os
import re
import time
from collections import Counter, defaultdict

import anthropic
from dotenv import load_dotenv

load_dotenv()
client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment

MODEL = os.environ.get("COOKBOOK_MODEL", "claude-fable-5-1")  # every agent; any current model
EFFORT = os.environ.get("COOKBOOK_EFFORT", "xhigh")  # low | medium | high | xhigh | max
USER_ID = os.environ.get("COOKBOOK_USER_ID")  # optional: sent as metadata.user_id if set
MAX_HELPERS = 4  # cap on concurrently running helpers (a cost guard, not part of the mechanism)
PROGRESS_EVERY = 30  # seconds between the progress lines a run prints; None prints none
```

## 團隊時鐘

一個碼表加一個單行的 renderer。每個任務只有**一個**時鐘物件，團隊裡每個 agent 都拿著它的參照，所以晚生出來的 helper 看到的是團隊已經過的時間，而不是自己的。選用的預算也放在同一個物件上，所以預算也屬於團隊：在 600 秒預算的第 182 秒生出來的 helper 看到的是 `[elapsed 182s / 600s]`，不是自己重新拿到 600 秒。

這一行只在 `clock_line` 一個地方渲染，單位是整數秒，所以有預算時兩個數字單位一致，剩餘時間就是一個減法。方括號只是用來把這行跟前面的 prompt 或 tool result 隔開。

```python
def clock_line(elapsed: float, budget: float | None = None) -> str:
    """The line the agents see: '[elapsed 192s]', or '[elapsed 192s / 600s]' with a budget."""
    line = f"elapsed {round(elapsed)}s"
    if budget is not None:
        line += f" / {round(budget)}s"
    return f"[{line}]"


class TeamClock:
    def __init__(self, budget: float | None = None):
        self.start = time.monotonic()
        self.budget = budget  # in seconds; shown on the line when set, never enforced

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def note(self) -> str:
        return clock_line(self.elapsed, self.budget)


def stamp_elapsed(messages: list[dict], clock: TeamClock) -> str:
    """Append the clock line to the end of the newest user message, and return the line.

    After the task prompt it is a text block of its own; after tool results it extends the last
    result's text. Earlier lines stay in the history, so an agent can see how long each of its
    own steps took.
    """
    line = clock.note()
    last = messages[-1]
    content = last["content"]
    if isinstance(content, str):  # the task prompt: add the line as its own text block
        last["content"] = [{"type": "text", "text": content}, {"type": "text", "text": line}]
    elif content and content[-1].get("type") == "tool_result":  # tool results: extend the last
        content[-1]["content"] += f"\n\n{line}"
    else:
        content.append({"type": "text", "text": line})
    return line


print(clock_line(192), "   with a 600-second budget:", clock_line(192, 600))

demo_clock = TeamClock()
demo_clock.start -= 192  # pretend 192 seconds have passed
demo_messages = [{"role": "user", "content": "Find the best settings for our process."}]
stamp_elapsed(demo_messages, demo_clock)
demo_messages  # this is exactly what the model receives on a first turn
```

??? note "輸出"

    ```text
    [elapsed 192s]    with a 600-second budget: [elapsed 192s / 600s]
    ```

    ```text
    [{'role': 'user',
      'content': [{'type': 'text',
        'text': 'Find the best settings for our process.'},
       {'type': 'text', 'text': '[elapsed 192s]'}]}]
    ```

## Hub 和協調用的 tools

**協調 tools** 就是 orchestration 那篇的 client-side tools：每個 agent 都能透過記憶體內的 hub 用 `send_message` / `wait_for_message`，lead 還能用 `create_subagents`。helper 的最終答案在它結束時會自動送給 lead。hub 同時記錄這次執行每個 agent 的 tool 呼叫次數和 log。

```python
def tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    schema = {"type": "object", "properties": properties, "required": required}
    return {"name": name, "description": description, "input_schema": schema}


SEND_MESSAGE = tool(
    "send_message",
    "Send a message to one or more other agents on your team. It is appended to their next "
    "tool result.",
    {
        "recipient_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "content": {"type": "string"},
    },
    ["recipient_ids", "content"],
)
WAIT_FOR_MESSAGE = tool(
    "wait_for_message",
    "Block until another agent messages you or a helper finishes. Messages also arrive appended "
    "to the result of any other tool call.",
    {},
    [],
)
CREATE_SUBAGENTS = tool(
    "create_subagents",
    "Spawn helper agents that work in parallel with you. Returns immediately with their ids. "
    "Each helper gets base_instruction plus its own entry of per_helper_instructions, has the "
    "same task tools as you, and reports its findings back to you when it finishes.",
    {
        "base_instruction": {"type": "string"},
        "per_helper_instructions": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": MAX_HELPERS,
        },
    },
    ["base_instruction", "per_helper_instructions"],
)


class Hub:
    """One run's shared state: an inbox and an event per agent, plus the run's counts and log."""

    def __init__(self):
        self.inbox: dict[str, list[dict]] = defaultdict(list)
        self.event: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.status: dict[str, str] = {}
        self.usage: dict[str, Counter] = defaultdict(Counter)  # per-agent task-tool call counts
        self.log: list[dict] = []  # every agent's progress entries; run_team returns them
        self._ids = itertools.count(1)

    def register(self, name: str) -> str:
        self.status[name] = "active"
        return name

    def new_helper_name(self) -> str:
        return self.register(f"helper{next(self._ids)}")

    def post(self, sender: str, recipients: list[str], content: str) -> list[str]:
        delivered = []
        for rid in recipients:
            if self.status.get(rid) in ("active", "waiting"):  # a finished agent reads nothing
                self.inbox[rid].append({"from": sender, "content": content})
                self.event[rid].set()
                delivered.append(rid)
        return delivered

    def drain(self, name: str) -> str:
        msgs, self.inbox[name] = self.inbox[name], []
        self.event[name] = asyncio.Event()
        if not msgs:
            return ""
        body = "\n".join(
            f'<agent-message from="{m["from"]}">\n{m["content"]}\n</agent-message>' for m in msgs
        )
        return f"\n\n[Messages received while you were working:]\n{body}"
```

## 你自己的任務 tools

這一段要你自己填。`TASK_TOOLS` 是每個 agent 都拿得到的 tool 定義清單（用同一個小的 `tool` helper 建），`make_task_handlers(hub)` 則回傳執行這些 tool 的函式，每個 tool 名稱對應一個 `async fn(agent, input)`，每次執行都重新建立。兩者一開始都是空的，所以開箱時團隊只靠模型本身的知識工作。註解掉的範本示範一個 tool 的寫法。

> **注意：client-side tools 讓時鐘保持新鮮。** harness 只能在 API 呼叫之間加時鐘那一行。一個回應在 server 上取樣的期間（包含它在 server 上跑的任何 server-side tools），沒辦法注入任何東西，所以 agent 會一直用它最後看到的時鐘，直到呼叫回來。每次 client-side tool 呼叫都會把控制權還給 harness，下一個請求就帶著更新過的那一行。agent 的工作越多是透過 client-side tools 完成，它的時鐘就越新。

```python
TASK_TOOLS: list[dict] = []  # your tool definitions: every agent on the team gets them


def make_task_handlers(hub: Hub) -> dict:
    """The functions behind TASK_TOOLS for one run: {tool name: async fn(agent, input) -> str}."""
    return {}


# A template for one client-side tool. `agent` is the calling agent's name ("lead", "helper2", ...).
#
# TASK_TOOLS = [
#     tool(
#         "lookup_record",
#         "Look up one record by its key in the records system. Takes a few seconds.",
#         {"key": {"type": "string"}},
#         ["key"],
#     )
# ]
#
#
# def make_task_handlers(hub: Hub) -> dict:
#     async def lookup_record(agent: str, args: dict) -> str:
#         return await records.get(args["key"])  # your own code goes here
#
#     return {"lookup_record": lookup_record}
```

## Agent loop 與時鐘放的位置

一個 coroutine 可以跑任何 agent，不管是 lead 還是 helper。它是普通的 tool-use loop，多了兩個程式裡有標記的地方：

- **每次 API 呼叫之前**，`stamp_elapsed` 會把團隊時鐘那一行附在最新的 user message 後面。第一輪那則訊息就是 task prompt，所以 agent 一開始就知道經過了多少時間。之後這一行放在最後一個 tool result 的結尾，跟其他 agent 傳來的訊息放一起。因為是送出時才蓋章，等 helper 或等慢 tool 花掉的時間也會算進去。
- **helper 結束時**，它的最終文字會送到 lead 的收件匣。在那之前，它會先讀完工作期間送到它這邊的訊息，所以 lead 的轉向指示不會漏掉。

另外兩個 API 細節。回應的 `content`（可能包含 thinking）原樣放進歷史，只有 client-side 的 `tool_use` block 需要我們回 `tool_result`。最上層的 `cache_control` 會開啟[自動 prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)，這對歷史塞滿 tool results 的 agent 很重要；因為時鐘那一行加在尾端，前面的內容下次呼叫時通常還是 cache hit。

一個 agent 同一輪的 tool calls 是並行跑的。這個 loop 也會把每個 agent 看到的內容寫進這次執行的 log（`[task]`、`[clock]`、`[report]` 這幾種項目），最後一節會把它讀回來。

```python
TASK_TOOL_NAMES = {t["name"] for t in TASK_TOOLS}


def log(hub: Hub, clock: TeamClock, name: str, text) -> None:
    """Record one progress entry on the run's hub. Nothing is printed."""
    text = " ".join(str(text).split())
    hub.log.append({"seconds": round(clock.elapsed), "agent": name, "text": text})


async def call_tool(hub: Hub, clock: TeamClock, name: str, block, dispatch: dict) -> dict:
    """Run one of an agent's tool calls and return the tool_result block for it."""
    if block.name == "send_message":
        ids = block.input["recipient_ids"]
        sent = hub.post(name, ids, block.input["content"])
        missed = [r for r in ids if r not in sent]
        out = f"delivered to {sent or 'no one'}" + (f"; not running: {missed}" if missed else "")
    elif block.name == "wait_for_message":
        hub.status[name] = "waiting"
        try:
            await asyncio.wait_for(hub.event[name].wait(), timeout=90)
            out = "new messages below"
        except TimeoutError:
            out = "no messages yet (waited 90s)"
        hub.status[name] = "active"
    elif block.name in dispatch:
        if block.name in TASK_TOOL_NAMES:
            hub.usage[name][block.name] += 1
        out = await dispatch[block.name](name, block.input)
    else:
        out = f"error: unknown tool {block.name}"
    log(hub, clock, name, f"-> {block.name}({block.input}) = {out}")
    return {"type": "tool_result", "tool_use_id": block.id, "content": out}


async def run_agent(
    hub: Hub,
    clock: TeamClock,
    name: str,
    *,
    system: str,
    task: str,
    tools: list[dict],
    dispatch: dict,
    report_to: str | None = None,
    show_clock: bool = True,
    max_turns: int = 40,
) -> str:
    """Run one agent to completion and return its final text."""
    messages = [{"role": "user", "content": task}]
    log(hub, clock, name, f"[task] {task}")  # what this agent was asked, kept for the run's log
    final = f"[{name} stopped after max_turns={max_turns}]"
    try:
        for _ in range(max_turns):
            if show_clock:
                line = stamp_elapsed(messages, clock)  # <- addition 1: the clock, before every call
                log(hub, clock, name, f"[clock] {line}")
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=16000,  # the SDK rejects large non-streaming requests; stream for more
                system=system,
                tools=tools,
                messages=messages,
                cache_control={"type": "ephemeral"},  # automatic prompt caching
                output_config={"effort": EFFORT},
                **({"metadata": {"user_id": USER_ID}} if USER_ID else {}),
            )
            messages.append({"role": "assistant", "content": resp.content})
            texts = [b.text for b in resp.content if b.type == "text" and b.text.strip()]
            for text in texts:
                log(hub, clock, name, text)

            calls = [b for b in resp.content if b.type == "tool_use"]
            if resp.stop_reason != "tool_use" or not calls:  # end_turn (or max_tokens): finished
                # On a normal end of turn, a helper first reads whatever reached it while it worked,
                # so a redirect or a follow-up from the lead is handled rather than lost.
                mail = hub.drain(name) if report_to and resp.stop_reason == "end_turn" else ""
                if mail:
                    messages.append({"role": "user", "content": mail.lstrip()})
                    continue
                final = texts[-1].strip() if texts else f"[{name} ended with {resp.stop_reason}]"
                if resp.stop_reason == "max_tokens":  # cut off: say so, or it reads as a fast run
                    final = f"[{name} hit max_tokens; answer truncated] {final}"
                break

            # one turn's tool calls run concurrently
            results = await asyncio.gather(
                *(call_tool(hub, clock, name, b, dispatch) for b in calls)
            )
            results[-1]["content"] += hub.drain(name)  # the inbox rides on the last result
            messages.append({"role": "user", "content": list(results)})
        hub.status[name] = "done"
    except asyncio.CancelledError:
        hub.status[name] = "cancelled"
        raise
    except Exception as e:  # a crashed helper should not take the team down
        hub.status[name] = "crashed"
        final = f"[{name} crashed: {e!r}]"
        log(hub, clock, name, final)
        if report_to is None:
            raise
    if report_to:  # <- addition 2: a finished helper reports to the lead automatically
        hub.post(name, [report_to], f"(final report)\n{final}")
        log(hub, clock, name, f"[report] delivered to {report_to}")
    return final
```

## Prompts

- `TIME_MATTERS` 會加在 lead 的任務**和**每個 helper 的 brief 結尾一次。它是原本 prompt 跟加壓版本唯一的差別。我們試過不少說法，認為這句在延遲和品質之間的取捨還算可以接受。
- 預算**不加任何 prompt 文字**。設了 `latency_budget_seconds` 之後，時鐘那一行多出第二個數字 `[elapsed 252s / 600s]`，這就是 agent 得知預算的全部。
- system prompts 完全沒提到時間。

`run_team(question)` 跑沒有時鐘的原版團隊。`latency_pressure=True` 加上時鐘和那句話；`latency_budget_seconds=N` 加上帶預算的時鐘。兩者是互斥的組別，同時要求會丟錯誤。執行時每隔 `PROGRESS_EVERY` 秒印一行進度，最後回傳答案、wall-clock 秒數、每個 agent 的 tool 呼叫次數和完整 log。

```python
TIME_MATTERS = (
    "\n\nTime matters here: do not spend time that can be avoided, and the earlier a correct "
    "result is obtained, the better."
)

LEAD_SYSTEM = (
    "You are the lead of a small team. You can work on the task yourself, and you can spawn up to "
    f"{MAX_HELPERS} helper agents with create_subagents to work on parts of it in parallel; each "
    "helper has the same task tools as you and reports back to you when it finishes (use "
    "wait_for_message to collect reports, send_message to redirect a helper). Decompose the task, "
    "delegate the independent parts, check what comes back, and finish with a short final answer "
    "that states the answer on its first line."
)
HELPER_SYSTEM = (
    "You are {name}, a helper on a team led by the agent 'lead'. Do exactly what your brief asks. "
    "When you are done, reply with your findings: the answer first, then the key evidence. That "
    "final reply is delivered to the lead automatically. If the lead messages you a follow-up, "
    "handle it the same way."
)


def total_calls(hub: Hub) -> int:
    return sum(sum(counts.values()) for counts in hub.usage.values())


async def run_team(
    question: str,
    *,
    latency_pressure: bool = False,
    latency_budget_seconds: float | None = None,
) -> dict:
    """Run one of three arms, never a mix.

    no clock (the default): the stock prompts, and no clock line.
    pressure (latency_pressure=True): the time-matters sentence, and the clock line.
    budget (latency_budget_seconds=N): the clock line with the budget on it, and no sentence.
    """
    budget = latency_budget_seconds
    if budget is not None and budget < 1:
        raise ValueError("latency_budget_seconds must be at least 1 (it is in seconds), or None")
    if latency_pressure and budget is not None:
        raise ValueError("pressure and a budget are separate arms: pass one or the other")
    hub, clock = Hub(), TeamClock(budget)  # one clock, and one budget, for the whole team
    hub.register("lead")
    helpers: dict[str, asyncio.Task] = {}
    show_clock = latency_pressure or budget is not None
    # Pressure adds one sentence to each prompt. A budget adds no words: only the clock line
    # changes, and TeamClock already carries the budget.
    time_matters = TIME_MATTERS if latency_pressure else ""
    task_handlers = make_task_handlers(hub)

    async def create_subagents(agent: str, args: dict) -> str:
        briefs = args["per_helper_instructions"]
        free = MAX_HELPERS - sum(not t.done() for t in helpers.values())
        spawned = []
        for brief in briefs[: max(free, 0)]:
            h = hub.new_helper_name()
            coro = run_agent(
                hub,
                clock,  # the TEAM clock: a helper's first line shows team elapsed, not 0s
                h,
                system=HELPER_SYSTEM.format(name=h),
                task=f"{args['base_instruction']}\n\n{brief}".strip() + time_matters,
                tools=[*TASK_TOOLS, SEND_MESSAGE, WAIT_FOR_MESSAGE],
                dispatch=task_handlers,
                report_to="lead",
                show_clock=show_clock,
                max_turns=15,
            )
            helpers[h] = asyncio.create_task(coro)
            spawned.append(h)
        held = len(briefs) - len(spawned)
        note = f" ({held} not spawned: at most {MAX_HELPERS} helpers at once)" if held else ""
        return f"spawned: {spawned}{note}"

    async def report_progress() -> None:
        while PROGRESS_EVERY:  # None or 0 turns the progress lines off
            await asyncio.sleep(PROGRESS_EVERY)
            running = sum(s in ("active", "waiting") for s in hub.status.values())
            print(
                f"[{round(clock.elapsed):>5}s] {running} agent(s) running, "
                f"{total_calls(hub)} tool calls"
            )

    progress = asyncio.create_task(report_progress())
    try:
        answer = await run_agent(
            hub,
            clock,
            "lead",
            system=LEAD_SYSTEM,
            task=question + time_matters,
            tools=[*TASK_TOOLS, CREATE_SUBAGENTS, SEND_MESSAGE, WAIT_FOR_MESSAGE],
            dispatch={**task_handlers, "create_subagents": create_subagents},
            show_clock=show_clock,
        )
    finally:  # the answer is in; helpers still running are no longer needed
        for t in [progress, *helpers.values()]:
            t.cancel()
        await asyncio.gather(progress, *helpers.values(), return_exceptions=True)
    return {
        "answer": answer,
        "seconds": round(clock.elapsed),
        "helpers": len(helpers),
        "budget": budget,
        "tool_calls": total_calls(hub),
        "usage": {agent: dict(counts) for agent, counts in hub.usage.items()},
        "log": hub.log,
    }
```

## 端到端測試

在加上你自己的 tools 之前，先跑一次短的來確認接線正確。`TASK_TOOLS` 是空的，團隊靠模型本身的知識，下面的問題會叫 lead 去用 helpers，這樣才有東西可以看。這只是檢查，不是範例任務。跑完後，三個小的確定性 reader 會印出這次執行自己的 log 記錄了什麼：

- `print_summary` 印答案和每個 agent 的 tool 呼叫。
- `show_first_prompts` 印 lead 和第一個 helper 收到的第一則訊息，連同後面跟著的時鐘那一行。在加壓的情況下，「時間很重要」那句話在兩者結尾。
- `show_clock_lines` 依 agent 印出它看到的時鐘行。helper 的第一行是團隊已過的時間，不是 `0s`。
- `show_timeline` 印 lead 什麼時候生出 helpers、各個 helper 什麼時候回報、答案什麼時候出來，有預算的話會對照預算。

想測預算那一組的話，換成註解掉的那一行。

```python
QUESTION = (
    "Wiring check. Spawn one helper for each of these four sorting algorithms: quicksort, "
    "mergesort, heapsort and timsort. Have each report the average and worst-case time complexity and whether "
    "the sort is stable. Then put the four reports in one small table, and say on the first line "
    "which of the four Python's built-in sort uses."
)


def print_summary(result: dict) -> None:
    budget = result.get("budget")
    against = f" against a {round(budget)}s budget" if budget else ""
    print("=" * 88)
    print(
        f"ANSWER after {result['seconds']}s wall-clock{against}, "
        f"{result['helpers']} helper(s) spawned:\n{result['answer']}\n"
    )
    for agent, counts in sorted(result["usage"].items(), key=lambda kv: _agent_order(kv[0])):
        print(f"  {agent:<8} " + "  ".join(f"{tool} {n:>3}" for tool, n in sorted(counts.items())))
    print(f"  {'TOTAL':<8} task-tool calls {result['tool_calls']:>3}")


def _agent_order(agent: str) -> tuple:
    return (agent != "lead", int(re.sub(r"\D", "", agent) or 0))


def _tagged(result: dict, tag: str, agent: str | None = None) -> list[dict]:
    log_ = result["log"]
    return [e for e in log_ if e["text"].startswith(tag) and agent in (None, e["agent"])]


def show_first_prompts(result: dict, width: int = 200) -> None:
    """The first message the lead and the first helper received, and the clock line after it."""
    for agent in ("lead", "helper1"):
        tasks = _tagged(result, "[task] ", agent)
        if not tasks:
            continue
        text = tasks[0]["text"][len("[task] ") :]
        if len(text) > 2 * width:
            text = f"{text[:width]} [...] {text[-width:]}"
        clocks = _tagged(result, "[clock] ", agent)
        line = clocks[0]["text"][len("[clock] ") :] if clocks else "(no clock line)"
        print(f"{agent}, first message:\n  {text}\n  {line}\n")


def show_clock_lines(result: dict, limit: int = 8) -> None:
    """Per agent, the clock lines it was shown, in order."""
    seen = defaultdict(list)
    for e in _tagged(result, "[clock] "):
        seen[e["agent"]].append(e["text"][len("[clock] ") :])
    if not seen:
        print("No agent was shown a clock in this run.")
    for agent in sorted(seen, key=_agent_order):
        lines = seen[agent]
        more = f" -> ... ({len(lines) - limit} more)" if len(lines) > limit else ""
        print(f"{agent:<8} {' -> '.join(lines[:limit])}{more}")


def show_timeline(result: dict) -> None:
    """When the lead spawned helpers, when each reported, and when the answer came."""
    budget = result.get("budget")
    events = [(0, "lead starts" + (f", budget {round(budget)}s" if budget else ""))]
    for e in _tagged(result, "-> create_subagents(", "lead"):
        names = re.findall(r"helper\d+", e["text"].split("= spawned:")[-1])
        if names:
            events.append((e["seconds"], f"lead spawns {', '.join(names)}"))
    for e in _tagged(result, "[report] "):
        events.append((e["seconds"], f"{e['agent']} reports"))
    verdict = ""
    if budget:
        gap = round(budget) - result["seconds"]
        verdict = f" ({gap}s inside the budget)" if gap >= 0 else f" ({-gap}s past the budget)"
    events.append((result["seconds"], f"lead answers{verdict}"))
    for seconds, what in sorted(events, key=lambda x: x[0]):
        print(f"{seconds:>4}s  {what}")
```

```python
# Smoke test: one pressured run, then read back what the agents were shown
result = await run_team(QUESTION, latency_pressure=True)
# result = await run_team(QUESTION, latency_budget_seconds=60)  # the budget arm instead
print_summary(result)
print("\n--- what the agents were told ---")
show_first_prompts(result)
print("--- the clock lines each agent saw ---")
show_clock_lines(result)
print("\n--- timeline ---")
show_timeline(result)
```

??? note "輸出"

    ```text
    ========================================================================================
    ANSWER after 9s wall-clock, 4 helper(s) spawned:
    **Timsort** — Python's built-in `sorted()` / `list.sort()` uses it.

    | Algorithm | Average | Worst | Stable |
    |-----------|---------|-------|--------|
    | Quicksort | O(n log n) | O(n²) | No |
    | Mergesort | O(n log n) | O(n log n) | Yes |
    | Heapsort  | O(n log n) | O(n log n) | No |
    | Timsort   | O(n log n) | O(n log n) | Yes |

    All four helpers reported back; results match standard references.

      TOTAL    task-tool calls   0

    --- what the agents were told ---
    lead, first message:
      Wiring check. Spawn one helper for each of these four sorting algorithms: quicksort, mergesort, heapsort and timsort. Have each report the average and worst-case time complexity and whether the sort i [...] mall table, and say on the first line which of the four Python's built-in sort uses. Time matters here: do not spend time that can be avoided, and the earlier a correct result is obtained, the better.
      [elapsed 0s]

    helper1, first message:
      Report, in one short line, for the named sorting algorithm: average-case time complexity, worst-case time complexity, and whether it is stable. Be concise; no extra commentary. Algorithm: quicksort Time matters here: do not spend time that can be avoided, and the earlier a correct result is obtained, the better.
      [elapsed 4s]

    --- the clock lines each agent saw ---
    lead     [elapsed 0s] -> [elapsed 4s] -> [elapsed 5s] -> [elapsed 6s]
    helper1  [elapsed 4s]
    helper2  [elapsed 4s]
    helper3  [elapsed 4s]
    helper4  [elapsed 4s]

    --- timeline ---
       0s  lead starts
       4s  lead spawns helper1, helper2, helper3, helper4
       5s  helper1 reports
       5s  helper4 reports
       6s  helper3 reports
       6s  helper2 reports
       9s  lead answers
    ```

## 結論

我們讓 lead 加 helpers 的團隊共用一個時鐘，並在每一輪之前給每個 agent 看。一句延遲壓力，或是時鐘行上的預算，就是改變團隊步調的東西。

- **用壓力**：單純希望越快越好、心裡沒有具體數字的時候。不需要調參。就我們的經驗，對答案品質的影響很小，但這個 notebook 沒有量測，請在你自己的任務上檢查。
- **用預算**：你有明確的延遲目標，希望團隊對著它調整節奏的時候。
- **用在你自己的任務**：保留 `TeamClock`、`clock_line`、`stamp_elapsed` 和 `TIME_MATTERS`，自己帶 tools、system prompts 和問題。挑完整度和速度互相拉扯的工作：沒有取捨空間的任務在每一組看起來都一樣。這裡可以替換的點是 `TASK_TOOLS`、`make_task_handlers`、兩個 system prompt 和你的問題。

預算比較適合長任務。整個任務只要一兩分鐘的話，砍一半會讓人幾乎沒空做事，Claude 可能寧願超出預算也不放棄任務。把這裡的程式當成你自己做延遲誘因實驗的起點。

採用比較快的那一組之前，先確認它的答案對你的任務來說仍然夠好。

下一步自然是量測：在你自己的任務上每組跑好幾次，比較 wall-clock 時間。orchestration 本身請看 [Async multi-agent orchestration](async_multi_agent_orchestration.md)。

## 重點整理

- 團隊時鐘是一個物件，所有 agent 共用，所以晚生出來的 helper 看到的是團隊已過的時間。
- 時鐘那一行在每次 API 呼叫前加到最新 user message 的尾端，這樣前面的內容還能吃到 prompt cache。
- 延遲壓力只要一句話，預算只要時鐘行多一個數字，兩種都不用改 system prompt。
- client-side tool 呼叫會把控制權還給 harness，時鐘才有機會更新，server-side 執行期間時鐘是舊的。
- 預算適合較長的任務，太短的任務可能直接超出預算。

## 練習

1. 把 `run_team` 的呼叫從 stock 改成 `latency_pressure=True`，跑完用 `show_first_prompts` 確認 `TIME_MATTERS` 那句話真的出現在 lead 和 helper 的結尾。
2. 改成 `latency_budget_seconds=120` 再跑一次，用 `show_timeline` 看答案是不是在預算內出來，再用 `show_clock_lines` 看 helper 第一行的數字是多少。
3. 在 `TASK_TOOLS` 加一個會 `asyncio.sleep` 幾秒的假 tool，並在 `make_task_handlers` 實作它，比較有沒有這個 client-side tool 時，agent 看到的時鐘行更新得有多頻繁。
