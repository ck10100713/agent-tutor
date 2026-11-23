---
translated: true
source: patterns/agents/async_multi_agent_orchestration.ipynb
---

# Async multi-agent orchestration

> 原文：[patterns/agents/async_multi_agent_orchestration.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/async_multi_agent_orchestration.ipynb)

兩種 async multi-agent pattern：透過共用 hub 讓 peer 互傳訊息的固定 N-agent 團隊，以及動態 spawn 的 async subagent，只留下最核心的訊息傳遞和生命週期機制。

## 這篇在做什麼

用最精簡的程式示範兩種 multi-agent 編排方式：固定人數的 agent 團隊，和動態產生的 subagent。沒有任何領域任務，只看訊息怎麼傳、tool 以什麼順序被呼叫。

## 學完你會

- 寫出一個讓多個 agent 透過 inbox 和 `asyncio.Event` 互傳訊息的 message hub
- 寫出能跑任何 agent 的 tool-use 迴圈，並把收到的訊息接在 tool result 後面
- 實作 spawn、get_status、kill 的 subagent 生命週期

## 開跑前

需要 Anthropic API key。

這份 cookbook 展示 Claude Opus 4.8 system card 裡 multi-agent 結果背後的兩種編排 pattern 的**形狀**：**固定 N-agent 團隊**和 **async subagent**。這裡沒有領域任務，只有訊息傳遞和 subagent 的機制，讓你清楚看到哪些 tool 以什麼順序觸發，再換上你自己的 tool 和任務。

全部用公開的 [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python) 加 `asyncio`，任何 API key 都能跑，通常三十秒內跑完。

## 設定

```python
%pip install -qU anthropic
```

```python
import asyncio
import itertools
from collections import Counter, defaultdict

import anthropic

MODEL = "claude-opus-5-5"  # swap for the newest Claude model available to you
client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env
```

## 共用的基礎元件

### Message hub

每個 agent 都有一個 inbox list 和一個用來阻塞等待的 `asyncio.Event`。`drain` 清空 inbox 並回傳結構化訊息，`render` 把它們格式化成文字，附加到 tool result 後面。

```python
class Hub:
    def __init__(self):
        self.inbox: dict[str, list[dict]] = defaultdict(list)
        self.event: dict[str, asyncio.Event] = defaultdict(asyncio.Event)
        self.status: dict[str, str] = {}
        self._ids = itertools.count(1)

    def register(self, name: str):
        self.status[name] = "active"
        _ = self.inbox[name], self.event[name]

    def new_name(self, prefix="helper") -> str:
        n = f"{prefix}{next(self._ids)}"
        self.register(n)
        return n

    def post(self, sender: str, recipients: list[str], content: str) -> list[str]:
        delivered = []
        for rid in recipients:
            if rid in self.status:
                self.inbox[rid].append({"from": sender, "content": content})
                self.event[rid].set()
                delivered.append(rid)
        return delivered

    def drain(self, name: str) -> list[dict]:
        msgs, self.inbox[name] = self.inbox[name], []
        self.event[name] = asyncio.Event()
        return msgs

    @staticmethod
    def render(msgs: list[dict]) -> str:
        if not msgs:
            return ""
        body = "\n".join(
            f'<agent-message from="{m["from"]}">\n{m["content"]}\n</agent-message>' for m in msgs
        )
        return f"\n\n[Messages received while you were working:]\n{body}"
```

### 訊息 tool

兩種 pattern 裡的每個 agent 都有這兩個 tool。

```python
SEND_MESSAGE = {
    "name": "send_message",
    "description": (
        "Send a message to one or more other agents. It will appear appended to their next tool "
        "result. This is the ONLY way to reach other agents — plain text in your turn goes nowhere."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "recipient_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "content": {"type": "string"},
        },
        "required": ["recipient_ids", "content"],
    },
}
WAIT_FOR_MESSAGE = {
    "name": "wait_for_message",
    "description": (
        "Block until another agent messages you. Note: messages also arrive automatically appended "
        "to the result of ANY other tool call, so only use this when you have nothing else to do."
    ),
    "input_schema": {"type": "object", "properties": {}},
}
BASE_TOOLS = [SEND_MESSAGE, WAIT_FOR_MESSAGE]
```

### 基本 agent 迴圈

一個函式就能跑任何 agent：標準的 tool-use 迴圈，把 `send_message` / `wait_for_message` 派送到 hub，其他 tool 交給 `extra_dispatch`，並且**把清空的 inbox 附加在最後一個 tool result 後面**，所以 agent 不用輪詢，訊息會直接帶進來。每次 tool call 和 inbox 投遞都會即時印出，讓你看著編排過程展開，最後再印一份摘要 trace。

```python
TRACE: dict[str, list[str]] = defaultdict(list)


def _snip(s, n=60):
    s = str(s).replace("\n", " ")
    return s if len(s) <= n else s[:n] + "…"


async def run_agent(
    hub: Hub,
    name: str,
    system: str,
    first_user_turn: str,
    tools: list = None,
    extra_dispatch=None,
    max_turns: int = 20,
) -> str:
    tools = tools or BASE_TOOLS
    extra_dispatch = extra_dispatch or {}
    messages = [{"role": "user", "content": first_user_turn}]

    try:
        for _ in range(max_turns):
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=system,
                tools=tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})

            if resp.stop_reason == "end_turn":
                hub.status[name] = "done"
                return "".join(getattr(b, "text", "") for b in resp.content)
            if resp.stop_reason != "tool_use":
                raise RuntimeError(f"unexpected stop_reason: {resp.stop_reason}")

            results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                TRACE[name].append(block.name)
                if block.name == "send_message":
                    rids = block.input["recipient_ids"]
                    delivered = hub.post(name, rids, block.input["content"])
                    unknown = [r for r in rids if r not in delivered]
                    out = f"delivered to {delivered}" + (f"; unknown: {unknown}" if unknown else "")
                elif block.name == "wait_for_message":
                    hub.status[name] = "idling"
                    try:
                        await asyncio.wait_for(hub.event[name].wait(), timeout=60)
                        out = "woke: new messages"
                    except TimeoutError:
                        out = "woke: 60s timeout"
                    hub.status[name] = "active"
                elif block.name in extra_dispatch:
                    out = await extra_dispatch[block.name](block)
                else:
                    out = f"error: no dispatch for {block.name}"
                print(f"  [{name}] {block.name}({_snip(block.input)}) → {_snip(out)}")
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})

            inbox = hub.drain(name)
            for m in inbox:
                print(f"  [{name}] ← received from {m['from']}: {_snip(m['content'])}")
            if results:
                results[-1]["content"] += hub.render(inbox)  # ← the key line
            messages.append({"role": "user", "content": results})

        hub.status[name] = "done"
        return f"[{name} hit max_turns={max_turns}]"
    except Exception:
        hub.status[name] = "crashed"
        raise


def print_trace():
    for agent in sorted(TRACE):
        counts = Counter(TRACE[agent])
        print(f"  {agent}: " + ", ".join(f"{n}×{t}" for t, n in counts.most_common()))
    TRACE.clear()
```

---
## Part 1 · 固定 N-Agent 團隊

三個 agent，一個 **lead** 和兩個 **helper**，各有一句話的 persona。它們只會用 `send_message` 互相自我介紹，lead 寫一句話總結並結束這次執行。沒有領域 tool，純粹走訊息路徑。

```python
TEAM_SYSTEM = "You are {name}, one of 3 agents working together (peers: {peers})."

TASKS = {
    "lead": "You are the lead. Introduce yourself to the others. Once everyone has introduced "
    "themselves, finish with a one-sentence summary of the team.",
    "helper1": "You are a backend engineer named Ada. Introduce yourself to the others, then wait "
    "for their replies.",
    "helper2": "You are a designer named Bo. Introduce yourself to the others, then wait for their "
    "replies.",
}


async def run_team() -> str:
    hub = Hub()
    names = list(TASKS)
    for n in names:
        hub.register(n)

    helper_tasks = [
        asyncio.create_task(
            run_agent(
                hub,
                n,
                system=TEAM_SYSTEM.format(name=n, peers=[p for p in names if p != n]),
                first_user_turn=TASKS[n],
            )
        )
        for n in names[1:]
    ]
    try:
        return await run_agent(
            hub,
            "lead",
            system=TEAM_SYSTEM.format(name="lead", peers=names[1:]),
            first_user_turn=TASKS["lead"],
        )
    finally:
        for t in helper_tasks:
            t.cancel()
        await asyncio.gather(*helper_tasks, return_exceptions=True)
```

```python
answer = await run_team()
print(f"\n[lead final answer]\n{answer}\n\nTool-call summary:")
print_trace()
```

??? note "輸出"

    ```text
      [helper1] send_message({'recipient_ids': ['lead', 'helper2'], 'content': "Hi all, I…) → delivered to ['lead', 'helper2']
      [helper2] send_message({'recipient_ids': ['lead', 'helper1'], 'content': "Hi everyo…) → delivered to ['lead', 'helper1']
      [helper2] ← received from helper1: Hi all, I'm Ada, a backend engineer on the team. I focus on …
      [lead] send_message({'recipient_ids': ['helper1', 'helper2'], 'content': "Hi tea…) → delivered to ['helper1', 'helper2']
      [lead] ← received from helper1: Hi all, I'm Ada, a backend engineer on the team. I focus on …
      [lead] ← received from helper2: Hi everyone! I'm Bo, the designer on the team. Looking forwa…
      [helper1] wait_for_message({}) → woke: new messages
      [helper1] ← received from helper2: Hi everyone! I'm Bo, the designer on the team. Looking forwa…
      [helper1] ← received from lead: Hi team, I'm lead, the coordinator for our group. Looking fo…
      [helper2] wait_for_message({}) → woke: new messages
      [helper2] ← received from lead: Hi team, I'm lead, the coordinator for our group. Looking fo…
      [lead] send_message({'recipient_ids': ['helper1', 'helper2'], 'content': "Thanks…) → delivered to ['helper1', 'helper2']

    [lead final answer]
    Everyone has introduced themselves, and I've shared the summary.

    **Team summary:** We're a three-person team with me (lead) coordinating, Ada handling backend engineering (APIs, databases, architecture), and Bo driving design — a well-rounded crew ready to build great things together.

    Tool-call summary:
      helper1: 1×send_message, 1×wait_for_message
      helper2: 1×send_message, 1×wait_for_message
      lead: 2×send_message
    ```

---
## Part 2 · Async Subagent（動態 spawn）

現在給 lead **subagent tool** 和一個簡單的 client 端 `sleep(seconds)` tool。lead 會 spawn 三個 helper，每個 sleep *N* 秒、用 `send_message` 回報 "done" 給 lead，然後 `wait_for_message` 等進一步指示。spawn 呼叫會立刻回傳，lead 在它們執行時用 `get_status` 檢查，用 `wait_for_message` 收集回報，最後 `kill_subagents` 把三個都解散。沒有領域邏輯，只有完整的 spawn / status / collect / kill 流程。

```python
SLEEP = {
    "name": "sleep",
    "description": "Sleep for the given number of seconds, then return.",
    "input_schema": {
        "type": "object",
        "properties": {"seconds": {"type": "integer", "minimum": 0, "maximum": 10}},
        "required": ["seconds"],
    },
}
SUBAGENT_TOOLS = [
    {
        "name": "create_subagents",
        "description": "Spawn helper subagents. Returns immediately — helpers run concurrently in the "
        "background in parallel with you. Each gets base_instruction, optionally + "
        "per_subagent_instructions[i].",
        "input_schema": {
            "type": "object",
            "properties": {
                "base_instruction": {"type": "string"},
                "per_subagent_instructions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 10,
                },
            },
            "required": ["base_instruction"],
        },
    },
    {
        "name": "get_status",
        "description": "Status of every helper (active / idling / done / crashed).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "kill_subagents",
        "description": "Cancel running helpers you no longer need.",
        "input_schema": {
            "type": "object",
            "properties": {
                "subagent_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}
            },
            "required": ["subagent_ids"],
        },
    },
]


async def dispatch_sleep(block) -> str:
    s = int(block.input["seconds"])
    await asyncio.sleep(s)
    return f"slept {s}s"
```

```python
async def run_spawn_lead() -> str:
    hub = Hub()
    hub.register("lead")
    helpers: dict[str, asyncio.Task] = {}

    async def _create(block):
        base = block.input["base_instruction"]
        per = block.input.get("per_subagent_instructions") or [""]
        spawned = []
        for suffix in per:
            h = hub.new_name()
            helpers[h] = asyncio.create_task(
                run_agent(
                    hub,
                    h,
                    system=f"You are {h}, a helper.",
                    first_user_turn=f"{base}\n\n{suffix}".strip(),
                    tools=[SLEEP, *BASE_TOOLS],
                    extra_dispatch={"sleep": dispatch_sleep},
                )
            )
            spawned.append(h)
        return f"spawned: {', '.join(spawned)}"

    async def _status(block):
        return "\n".join(f"{n}: {s}" for n, s in hub.status.items() if n != "lead") or "(none)"

    async def _kill(block):
        killed_ids, to_await = [], []
        for sid in block.input["subagent_ids"]:
            if sid in helpers and not helpers[sid].done():
                helpers[sid].cancel()
                hub.status[sid] = "done"
                to_await.append(helpers.pop(sid))
                killed_ids.append(sid)
        await asyncio.gather(*to_await, return_exceptions=True)
        return f"cancelled: {', '.join(killed_ids)}" if killed_ids else "no matching active helpers"

    try:
        return await run_agent(
            hub,
            "lead",
            system="You are the lead.",
            first_user_turn=(
                "Spawn three helper agents. Instruct each to sleep a different number of seconds "
                "(1, 2, 3), report back to you 'done, slept Ns', then wait for your further "
                "instructions. After that, check that they're running, collect all three reports, "
                "then dismiss all three helpers. Finish with a one-line summary."
            ),
            tools=[*SUBAGENT_TOOLS, *BASE_TOOLS],
            extra_dispatch={
                "create_subagents": _create,
                "get_status": _status,
                "kill_subagents": _kill,
            },
        )
    finally:
        for t in helpers.values():
            t.cancel()
        await asyncio.gather(*helpers.values(), return_exceptions=True)
```

```python
answer = await run_spawn_lead()
print(f"\n[lead final answer]\n{answer}\n\nTool-call summary:")
print_trace()
```

??? note "輸出"

    ```text
      [lead] create_subagents({'base_instruction': 'You are a helper agent. Follow your sp…) → spawned: helper1, helper2, helper3
      [lead] get_status({}) → helper1: active helper2: active helper3: active
      [helper1] sleep({'seconds': 1}) → slept 1s
      [helper2] sleep({'seconds': 2}) → slept 2s
      [helper1] send_message({'recipient_ids': ['lead'], 'content': 'done, slept 1s'}) → delivered to ['lead']
      [lead] wait_for_message({}) → woke: new messages
      [lead] ← received from helper1: done, slept 1s
      [helper3] sleep({'seconds': 3}) → slept 3s
      [helper2] send_message({'recipient_ids': ['lead'], 'content': 'done, slept 2s'}) → delivered to ['lead']
      [lead] wait_for_message({}) → woke: new messages
      [lead] ← received from helper2: done, slept 2s
      [helper3] send_message({'recipient_ids': ['lead'], 'content': 'done, slept 3s'}) → delivered to ['lead']
      [lead] wait_for_message({}) → woke: new messages
      [lead] ← received from helper3: done, slept 3s
      [lead] kill_subagents({'subagent_ids': ['helper1', 'helper2', 'helper3']}) → cancelled: helper1, helper2, helper3

    [lead final answer]
    Summary: All 3 helpers were spawned and confirmed active, each reported back successfully ("done, slept 1s/2s/3s"), and all three were then dismissed.

    Tool-call summary:
      helper1: 1×sleep, 1×send_message, 1×wait_for_message
      helper2: 1×sleep, 1×send_message, 1×wait_for_message
      helper3: 1×sleep, 1×send_message, 1×wait_for_message
      lead: 3×wait_for_message, 1×create_subagents, 1×get_status, 1×kill_subagents
    ```

---
## 下一步

換成你自己的領域 tool：加進 `tools`，並在 `extra_dispatch` 加對應的 handler。上面的 `Hub`、`run_agent` 和兩個 team runner 就是全部需要的東西，剩下是你的任務和 tool。

完整的 tool 定義參考請看 [tool use guide](https://docs.claude.com/en/docs/tool-use)。

## 重點整理

- 訊息 hub 加 inbox，就能讓 agent 之間互傳訊息，不需要輪詢。
- 把 inbox 內容附加到最後一個 tool result，是讓訊息自然進入 agent 上下文的簡單做法。
- 固定團隊和動態 subagent 共用同一個 agent 迴圈，差別只在多了哪些 tool。
- subagent 的生命週期就是 spawn、查 status、收集回報、kill，spawn 是非同步、立刻回傳。

## 練習

1. 把 Part 1 的 persona 改成三個不同角色，看 lead 的總結怎麼變。
2. 在 Part 2 把 helper 數量從 3 改成 5，各自 sleep 不同秒數，觀察回報順序。
3. 加一個自己的 tool（例如 `fetch_number`）到 `tools` 和 `extra_dispatch`，讓 helper 回報它的結果而不是 "done"。
