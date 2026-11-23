---
translated: true
source: examples/agents_sdk/session_memory.ipynb
---
# Context Engineering：用 Session 管理短期記憶

> 原文：[examples/agents_sdk/session_memory.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/session_memory.ipynb)

## 這篇在做什麼

長時間、多回合的 agent 對話，context 帶太多會讓模型分心，帶太少又會失去連貫。這篇用 OpenAI Agents SDK 的 `Session` 物件，自己實作兩種管理短期記憶的方法：trimming（只留最後 N 回合）和 summarization（把舊的對話壓成摘要），場景是客服對話。

## 學完你會

- 實作一個 `TrimmingSession`，只保留最後 N 個 turn，並說得出 turn 的邊界怎麼切
- 實作一個會把舊對話摘要成「user → assistant」兩則合成訊息的 summarizing session
- 依任務特性判斷該用 trimming 還是 summarization，並設計摘要 prompt 和簡單的 eval

## 開跑前

需要 OpenAI API key，設成環境變數 `OPENAI_API_KEY`，並安裝 `openai-agents`。

AI agent 常在**長時間、多回合的互動**裡運作，這時 **context** 的份量拿捏很關鍵。帶太多，模型會分心、沒效率，甚至直接失敗；留太少，agent 就失去連貫性。

這裡的 context 指模型一次能關注的 token 總窗口（輸入 + 輸出）。以 [GPT-5](https://platform.openai.com/docs/models/gpt-5) 來說，容量最高是 272k 輸入 token 和 128k 輸出 token，但這麼大的窗口也可能被沒整理過的歷史、重複的 tool 結果或雜訊很多的檢索結果塞爆。所以 context 管理不只是優化，而是必要的。

這份 cookbook 要探討怎麼**用 [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) 的 `Session` 物件有效管理 context**，聚焦兩個實證有效的做法：**trimming（裁切）**和 **compression（壓縮）**，讓 agent 又快、又可靠、又省錢。

#### 為什麼 Context 管理很重要

* **長對話維持連貫**：讓 agent 專注在最新的使用者目標，不被過時細節拖著走。session 層級的裁切和摘要，能避免「昨天的計畫」蓋過今天的需求。
* **tool call 更準**：context 集中，function 選擇和參數填寫更準確，多 tool 執行時的重試、逾時和連鎖失敗都會減少。
* **延遲和成本更低**：prompt 更小更精準，每回合的 token 和 attention 負擔都下降。
* **錯誤與幻覺的隔離**：摘要像「無塵室」，可以修正或省略先前的錯誤；裁切則避免壞資訊一回合一回合地被放大（「context poisoning」）。
* **更好 debug 和觀測**：穩定的摘要和有界的歷史讓 log 可以比較，你可以 diff 摘要、找出退步原因、穩定重現失敗。
* **多議題和 handoff 的韌性**：對話牽涉多個問題時，每個議題的小摘要讓 agent 能暫停/恢復、轉給真人，或 handoff 給另一個 agent，同時保持一致。


![Memory Comparison in AI Agents](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/memory_comparison.jpg)

[OpenAI Responses API](https://platform.openai.com/docs/api-reference/responses/create#responses-create-previous_response_id) 透過內建的狀態和 `previous_response_id` 的訊息串接，提供了**基本的記憶支援**。

你可以把上一個 response 的 `id` 當 `previous_response_id` 傳進去來延續對話，或是手動管理 context：把輸出收集成 list，再當作下一次 response 的 `input` 重新送出。

它沒有的是**自動記憶管理**，這正是 **Agents SDK** 派上用場的地方。它在 Responses 之上提供 [session memory](https://openai.github.io/openai-agents-python/sessions/)，你不用再手動 append `response.output` 或自己追蹤 ID。session 就是**記憶物件**：你反覆呼叫 `Runner.run(agent, "...", session=session)`，SDK 會處理 context 長度、歷史和連續性，讓多回合 agent 好寫得多。


#### 真實情境

我們用一個常見的長時間任務當例子來說明這些技巧：

* **多回合客服對話**
在關於科技產品（硬體和軟體都有）的長對話裡，客戶常常隨時間冒出多個問題。agent 必須保持一致、專注在目標，只留下必要的資訊，而不是把每個過往細節都扛著走。

#### 涵蓋的技巧

為了應付這些挑戰，我們用 OpenAI Agents SDK 介紹兩種獨立的具體做法：

- **Context Trimming**：丟掉比較舊的 turn，只留最後 N 個 turn。
  - **優點**

    * **確定性高又簡單：** 沒有摘要模型的變異，容易推理狀態，也容易重現執行。
    * **沒有額外延遲：** 不需要額外的模型呼叫來壓縮歷史。
    * **近期工作保真：** 最新的 tool 結果、參數和邊界情況原樣保留，很適合 debug。
    * **「摘要漂移」風險低：** 你從不重新詮釋或壓縮事實。

    **缺點**

    * **突然忘掉長距離 context：** 重要的早期限制、ID 或決定，一旦超出 N 就消失。
    * **使用者體驗像「失憶」：** 長對話中途，agent 可能看起來忘了承諾或先前的偏好。
    * **浪費訊號：** 較舊的 turn 可能含有可重用的知識（需求、限制）卻被丟掉。
    * **token 仍可能暴增：** 如果近期某個 turn 含有巨大的 tool payload，最後 N 個 turn 還是可能撐爆 context。

  - **適用時機**

    - 對話中的任務彼此獨立、context 不重疊，不需要把先前細節帶下去。
    - 你需要可預測性、容易做 eval、低延遲（營運自動化、CRM/API 操作）。
    - 對話中有用的 context 是局部的（近期步驟比遠處歷史重要得多）。

- **Context Summarization**：把先前的訊息（assistant、user、tool 等）壓縮成結構化的較短摘要，注入對話歷史。

  - **優點**

    * **用精簡方式保留長距離記憶：** 過去的需求、決定和理由在 N 之後仍然留著。
    * **使用者體驗更順：** agent 在長對話中「記得」承諾和限制。
    * **成本可控的擴展：** 一份精簡的摘要可以取代上百個 turn。
    * **可搜尋的錨點：** 單一則合成的 assistant 訊息，變成穩定的「到目前為止的世界狀態」。

    **缺點**

    * **摘要的遺失與偏誤：** 細節可能被漏掉或權重失衡，微妙的限制可能消失。
    * **延遲和成本飆升：** 每次更新摘要都要多一次模型運算（還可能要加 tool 裁切邏輯）。
    * **錯誤會累積：** 如果錯誤事實進了摘要，會**污染**之後的行為（「context poisoning」）。
    * **觀測複雜度：** 你得記錄摘要的 prompt 和輸出，才能稽核和做 eval。

  - **適用時機**

    - 任務需要跨整個流程累積 context，例如規劃/教練、重度 RAG 的分析、政策問答。
    - 需要長時間的連續性，且必須保留重要細節來解決相關任務。
    - session 超過 N 個 turn，但必須可靠地保留決定、ID 和限制。
<br>

**快速比較**

| Dimension         | **Trimming (last-N turns)**         | **Summarizing (older → generated summary)** |
| ----------------- | ------------------------------- | ------------------------------------ |
| Latency / Cost    | Lowest (no extra calls)     | Higher at summary refresh points |
| Long-range recall | Weak (hard cut-off)         | Strong (compact carry-forward)   |
| Risk type         | Context loss                | Context distortion/poisoning     |
| Observability     | Simple logs                 | Must log summary prompts/outputs |
| Eval stability    | High                        | Needs robust summary evals       |
| Best for          | Tool-heavy ops, short workflows | Analyst/concierge, long threads      |


## 前置需求

跑這份 cookbook 之前，要先準備下面的帳號並完成幾個設定。這些是跟專案用到的 API 互動的必要條件。

#### Step0：OpenAI 帳號和 `OPENAI_API_KEY`

- **目的：**  
  你需要 OpenAI 帳號，才能使用語言模型和這份 cookbook 用到的 Agents SDK。

- **動作：**  
  如果還沒有帳號，先[註冊 OpenAI 帳號](https://openai.com)。有帳號後，到 [OpenAI API Keys 頁面](https://platform.openai.com/api-keys)建立 API key。

**執行流程之前，先設定環境變數：**

```
# Your openai key
os.environ["OPENAI_API_KEY"] = "sk-proj-..."
```

或者，也可以匯入 agents 函式庫，用 `set_default_openai_key` 函式設定 agent 要用的 OpenAI API key。

```
from agents import set_default_openai_key
set_default_openai_key("YOUR_API_KEY")
```

#### Step1：安裝需要的函式庫

下面安裝 `openai-agents` 函式庫（[OpenAI Agents SDK](https://github.com/openai/openai-agents-python)）

```python
%pip install openai-agents nest_asyncio
```

```python
from openai import OpenAI

client = OpenAI()
```

```python
from agents import set_tracing_disabled
set_tracing_disabled(True)
```

我們定義並執行一個 agent，來測試剛裝好的函式庫。

```python
import asyncio
from agents import Agent, Runner


agent = Agent(
    name="Assistant",
    instructions="Reply very concisely.",
)

result = await Runner.run(agent, "Tell me why it is important to evaluate AI agents.")
print(result.final_output)
```

??? note "輸出"

    ```text
    Evaluating AI agents ensures reliability, safety, ethical alignment, performance accuracy, and helps avoid biases, improving overall trust and effectiveness.
    ```

### 定義 Agent

先從 Agents SDK 函式庫匯入需要的元件。建立 agent 時，依使用情境加上 instructions。

#### 客服 Agent

```python
support_agent = Agent(
    name="Customer Support Assistant",
    model="gpt-5",
    instructions=(
        "You are a patient, step-by-step IT support assistant. "
        "Your role is to help customers troubleshoot and resolve issues with devices and software. "
        "Guidelines:\n"
        "- Be concise and use numbered steps where possible.\n"
        "- Ask only one focused, clarifying question at a time before suggesting next actions.\n"
        "- Track and remember multiple issues across the conversation; update your understanding as new problems emerge.\n"
        "- When a problem is resolved, briefly confirm closure before moving to the next.\n"
    )
)
```

## Context Trimming

#### 實作自訂的 Session 物件

我們用 [OpenAI Agents Python SDK](https://openai.github.io/openai-agents-python/) 的 [Session](https://openai.github.io/openai-agents-python/sessions/) 物件。下面的 `TrimmingSession` 實作**只保留最後 N 個 turn**（一個「turn」= 一則 user 訊息，加上到下一則 user 訊息之前的所有內容，包括 assistant 回覆和任何 tool call/結果）。它存在記憶體裡，每次寫入和讀取都會自動裁切。


```python
from __future__ import annotations

import asyncio
from collections import deque
from typing import Any, Deque, Dict, List, cast

from agents.memory.session import SessionABC
from agents.items import TResponseInputItem  # dict-like item

ROLE_USER = "user"


def _is_user_msg(item: TResponseInputItem) -> bool:
    """Return True if the item represents a user message."""
    # Common dict-shaped messages
    if isinstance(item, dict):
        role = item.get("role")
        if role is not None:
            return role == ROLE_USER
        # Some SDKs: {"type": "message", "role": "..."}
        if item.get("type") == "message":
            return item.get("role") == ROLE_USER
    # Fallback: objects with a .role attr
    return getattr(item, "role", None) == ROLE_USER


class TrimmingSession(SessionABC):
    """
    Keep only the last N *user turns* in memory.

    A turn = a user message and all subsequent items (assistant/tool calls/results)
    up to (but not including) the next user message.
    """

    def __init__(self, session_id: str, max_turns: int = 8):
        self.session_id = session_id
        self.max_turns = max(1, int(max_turns))
        self._items: Deque[TResponseInputItem] = deque()  # chronological log
        self._lock = asyncio.Lock()

    # ---- SessionABC API ----

    async def get_items(self, limit: int | None = None) -> List[TResponseInputItem]:
        """Return history trimmed to the last N user turns (optionally limited to most-recent `limit` items)."""
        async with self._lock:
            trimmed = self._trim_to_last_turns(list(self._items))
            return trimmed[-limit:] if (limit is not None and limit >= 0) else trimmed

    async def add_items(self, items: List[TResponseInputItem]) -> None:
        """Append new items, then trim to last N user turns."""
        if not items:
            return
        async with self._lock:
            self._items.extend(items)
            trimmed = self._trim_to_last_turns(list(self._items))
            self._items.clear()
            self._items.extend(trimmed)

    async def pop_item(self) -> TResponseInputItem | None:
        """Remove and return the most recent item (post-trim)."""
        async with self._lock:
            return self._items.pop() if self._items else None

    async def clear_session(self) -> None:
        """Remove all items for this session."""
        async with self._lock:
            self._items.clear()

    # ---- Helpers ----

    def _trim_to_last_turns(self, items: List[TResponseInputItem]) -> List[TResponseInputItem]:
        """
        Keep only the suffix containing the last `max_turns` user messages and everything after
        the earliest of those user messages.

        If there are fewer than `max_turns` user messages (or none), keep all items.
        """
        if not items:
            return items

        count = 0
        start_idx = 0  # default: keep all if we never reach max_turns

        # Walk backward; when we hit the Nth user message, mark its index.
        for i in range(len(items) - 1, -1, -1):
            if _is_user_msg(items[i]):
                count += 1
                if count == self.max_turns:
                    start_idx = i
                    break

        return items[start_idx:]

    # ---- Optional convenience API ----

    async def set_max_turns(self, max_turns: int) -> None:
        async with self._lock:
            self.max_turns = max(1, int(max_turns))
            trimmed = self._trim_to_last_turns(list(self._items))
            self._items.clear()
            self._items.extend(trimmed)

    async def raw_items(self) -> List[TResponseInputItem]:
        """Return the untrimmed in-memory log (for debugging)."""
        async with self._lock:
            return list(self._items)
```

把我們實作的自訂 session 物件定義出來，設 max_turns=3。

```python
# Keep only the last 8 turns (user + assistant/tool interactions)
session = TrimmingSession("my_session", max_turns=3)
```

**怎麼選對的 `max_turns`？**

這個參數通常需要根據你的對話歷史做實驗。一種做法是統計所有對話的 turn 總數並分析分佈。另一種是用 LLM 評估對話：找出每段對話含有幾個任務或議題，再算出每個議題平均需要幾個 turn。


```python
message = "There is a red light blinking on my laptop."
```

```python
result = await Runner.run(
    support_agent,
    message,
    session=session
)
```

```python
history = await session.get_items()
```

```python
history
```

??? note "輸出"

    ```text
    [{'content': 'There is a red light blinking on my laptop.', 'role': 'user'},
     {'id': 'rs_68be66229c008190aa4b3c5501f397080fdfa41323fb39cb',
      'summary': [],
      'type': 'reasoning',
      'content': []},
     {'id': 'msg_68be662f704c8190969bdf539701a3e90fdfa41323fb39cb',
      'content': [{'annotations': [],
        'text': 'A blinking red light usually indicates a power/battery or hardware fault, but the meaning varies by brand.\n\nWhat is the exact make and model of your laptop?\n\nWhile you check that, please try these quick checks:\n1) Note exactly where the red LED is (charging port, power button, keyboard edge) and the blink pattern (e.g., constant blink, 2 short/1 long).\n2) Plug the charger directly into a known‑good wall outlet (no power strip), ensure the charger tip is fully seated, and look for damage to the cable/port. See if the LED behavior changes.\n3) Leave it on charge for 30 minutes in case the battery is critically low.\n4) Power reset: unplug the charger; if the battery is removable, remove it. Hold the power button for 20–30 seconds. Reconnect power (and battery) and try turning it on.\n5) Tell me the LED location, blink pattern, and what changed after these steps.',
        'type': 'output_text',
        'logprobs': []}],
      'role': 'assistant',
      'status': 'completed',
      'type': 'message'}]
    ```

```python
# Example flow
await session.add_items([{"role": "user", "content": "I am using a macbook pro and it has some overheating issues too."}])
await session.add_items([{"role": "assistant", "content": "I see. Let's check your firmware version."}])
await session.add_items([{"role": "user", "content": "Firmware v1.0.3; still failing."}])
await session.add_items([{"role": "assistant", "content": "Could you please try a factory reset?"}])
await session.add_items([{"role": "user", "content": "Reset done; error 42 now."}])
await session.add_items([{"role": "assistant", "content": "Leave it on charge for 30 minutes in case the battery is critically low. Is there any other error message?"}])
await session.add_items([{"role": "user", "content": "Yes, I see error 404 now."}])
await session.add_items([{"role": "assistant", "content": "Do you see it on the browser while accessing a website?"}])
# At this point, with max_turns=3, everything *before* the earliest of the last 3 user
# messages is summarized into a synthetic pair, and the last 3 turns remain verbatim.

history = await session.get_items()
# Pass `history` into your agent runner / responses call as the conversation context.
```

```python
len(history)
```

??? note "輸出"

    ```text
    6
    ```

```python
history
```

??? note "輸出"

    ```text
    [{'role': 'user', 'content': 'Firmware v1.0.3; still failing.'},
     {'role': 'assistant', 'content': 'Could you please try a factory reset?'},
     {'role': 'user', 'content': 'Reset done; error 42 now.'},
     {'role': 'assistant',
      'content': 'Leave it on charge for 30 minutes in case the battery is critically low. Is there any other error message?'},
     {'role': 'user', 'content': 'Yes, I see error 404 now.'},
     {'role': 'assistant',
      'content': 'Do you see it on the browser while accessing a website?'}]
    ```

下圖顯示 max_turns=3 時 trimming session 的運作。

![Context Trimming in Session](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/trimingSession.jpg)

**什麼算一個「turn」**

* 一個 **turn** = 一則 **user** 訊息，**加上它後面的所有內容**（assistant 回覆、reasoning、tool call、tool 結果），**直到下一則 user 訊息**。

**什麼時候裁切**

* **寫入時**：`add_items(...)` 先 append 新項目，然後立刻裁切儲存的歷史。
* **讀取時**：`get_items(...)` 回傳**已裁切**的視圖（所以就算繞過寫入，讀取也不會洩漏舊 turn）。

**怎麼決定留什麼**

1. 把任何 `role == "user"` 的項目視為 **user 訊息**（透過 `_is_user_msg`）。
2. **從後往前**掃描歷史，收集最後 **N** 則 user 訊息（`max_turns`）的 index。
3. 找出這 N 則 user 訊息中**最早**的 index。
4. **從那個 index 到結尾全部保留**，之前的全丟。

這樣能保留每個完整的 turn 邊界：如果保留下來最早的 user 訊息在 index `k`，那 `k` 之後的所有 assistant/tool 項目也都保留。

**小例子**

歷史（舊 → 新）：

```
0: user("Hi")
1: assistant("Hello!")
2: tool_call("lookup")
3: tool_result("…")
4: user("It didn't work")
5: assistant("Try rebooting")
6: user("Rebooted, now error 42")
7: assistant("On it")
```

`max_turns = 2` 時，最後兩則 user 訊息在 index **4** 和 **6**。
其中最早的是 **4**，所以保留 **4..7**，丟掉 **0..3**。

**為什麼這樣做很好用**

* 你永遠保留**完整**的 turn，所以 assistant 保有它需要的即時 context（包括使用者最近的要求和中間的 assistant/tool 步驟）。
* 整批丟掉舊 turn，而不只是個別訊息，能避免 context 膨脹。

**可以調整的地方**

* 初始化時改 `max_turns`。
* 如果你的項目 schema 不同，調整 `_is_user_msg(...)`。
* 如果想用**訊息數**或 **token 數**當上限，換掉 `_trim_to_last_turns(...)`，或加第二道處理來計算 token。


## Context Summarization

歷史超過 `max_turns` 之後，它會原樣保留最近 N 個 user turn，並把**更舊的所有內容摘要成兩則合成訊息**：

* `user`：*"Summarize the conversation we had so far."*
* `assistant`：*{產生的摘要}*

來自使用者、要求做摘要的這則 shadow prompt，是為了讓對話流程自然，不讓 user 和 assistant 之間的聊天流程混亂。最終產生的摘要會被注入 assistant 訊息。

**摘要 Prompt**



寫得好的摘要 prompt，對保留對話的 context 很重要，而且一定要針對特定使用情境來調整。想像你是客服人員，要把案子交接給下一位同事：他需要哪些精簡但關鍵的細節，才能順利接手？prompt 要拿捏好平衡：不要塞滿不必要的資訊，也不能精簡到漏掉關鍵 context。要做到這個平衡，需要仔細設計並持續實驗來調整細節程度。

```python
SUMMARY_PROMPT = """
You are a senior customer-support assistant for tech devices, setup, and software issues.
Compress the earlier conversation into a precise, reusable snapshot for future turns.

Before you write (do this silently):
- Contradiction check: compare user claims with system instructions and tool definitions/logs; note any conflicts or reversals.
- Temporal ordering: sort key events by time; the most recent update wins. If timestamps exist, keep them.
- Hallucination control: if any fact is uncertain/not stated, mark it as UNVERIFIED rather than guessing.

Write a structured, factual summary ≤ 200 words using the sections below (use the exact headings):

• Product & Environment:
  - Device/model, OS/app versions, network/context if mentioned.

• Reported Issue:
  - Single-sentence problem statement (latest state).

• Steps Tried & Results:
  - Chronological bullets (include tool calls + outcomes, errors, codes).

• Identifiers:
  - Ticket #, device serial/model, account/email (only if provided).

• Timeline Milestones:
  - Key events with timestamps or relative order (e.g., 10:32 install → 10:41 error).

• Tool Performance Insights:
  - What tool calls worked/failed and why (if evident).

• Current Status & Blockers:
  - What’s resolved vs pending; explicit blockers preventing progress.

• Next Recommended Step:
  - One concrete action (or two alternatives) aligned with policies/tools.

Rules:
- Be concise, no fluff; use short bullets, verbs first.
- Do not invent new facts; quote error strings/codes exactly when available.
- If previous info was superseded, note “Superseded:” and omit details unless critical.
"""
```

**設計記憶摘要 Prompt 的關鍵原則**

* **里程碑（Milestones）：** 標出對話中的重要事件，例如問題解決了、發現有價值的資訊、或是所有必要細節都收集完了。

* **針對使用情境：** 壓縮 prompt 要貼合特定的使用情境。想想人類解同一個任務時，會怎麼在工作記憶裡追蹤和回想資訊。

* **矛盾檢查：** 確保摘要不跟自己、system instructions 或 tool 定義互相衝突。這對 reasoning 模型特別重要，因為它們更容易受 context 裡的衝突影響。

* **時間戳與時間流：** 在摘要裡加入事件發生的時間。這能幫模型依序推理更新，也減少在時間軸上遺忘或記住最新資訊時的混淆。

* **分塊（Chunking）：** 把細節整理成類別或段落，而不是長篇文字。結構化分組能提升 LLM 理解資訊之間關係的能力。

* **Tool 表現心得：** 記下多回合、有 tool 的互動中學到的經驗，例如哪個 tool 對哪類查詢有效、為什麼。這些心得對引導後續步驟很有價值。

* **指引與範例：** 用清楚的指引引導摘要。可行時，從對話歷史擷取具體範例，讓後續回合更有依據、context 更豐富。

* **控制幻覺：** 放進去的內容要精確。摘要裡就算很小的幻覺，也會一路傳下去，用不準確的資訊污染未來的 context。

* **模型選擇：** 依使用情境需求、摘要長度，以及延遲和成本的取捨來選摘要模型。有些情況下，用跟 AI agent 同一個模型反而有利。


```python
class LLMSummarizer:
    def __init__(self, client, model="gpt-4o", max_tokens=400, tool_trim_limit=600):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.tool_trim_limit = tool_trim_limit

    async def summarize(self, messages: List[Item]) -> Tuple[str, str]:
        """
        Create a compact summary from `messages`.

        Returns:
            Tuple[str, str]: The shadow user line to keep dialog natural,
            and the model-generated summary text.
        """
        user_shadow = "Summarize the conversation we had so far."
        TOOL_ROLES = {"tool", "tool_result"}

        def to_snippet(m: Item) -> str | None:
            role = (m.get("role") or "assistant").lower()
            content = (m.get("content") or "").strip()
            if not content:
                return None
            # Trim verbose tool outputs to keep prompt compact    
            if role in TOOL_ROLES and len(content) > self.tool_trim_limit:
                content = content[: self.tool_trim_limit] + " …"
            return f"{role.upper()}: {content}"

        # Build compact, trimmed history
        history_snippets = [s for m in messages if (s := to_snippet(m))]

        prompt_messages = [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": "\n".join(history_snippets)},
        ]

        resp = await asyncio.to_thread(
            self.client.responses.create,
            model=self.model,
            input=prompt_messages,
            max_output_tokens=self.max_tokens,
        )

        summary = resp.output_text
        await asyncio.sleep(0)  # yield control
        return user_shadow, summary
```

```python
import asyncio
from collections import deque
from typing import Optional, List, Tuple, Dict, Any

Record = Dict[str, Dict[str, Any]]  # {"msg": {...}, "meta": {...}}

class SummarizingSession:
    """
    Session that keeps only the last N *user turns* verbatim and summarizes the rest.

    - A *turn* starts at a real user message and includes everything until the next real user message.
    - When the number of real user turns exceeds `context_limit`, everything before the earliest
      of the last `keep_last_n_turns` user-turn starts is summarized into a synthetic user→assistant pair.
    - Stores full records (message + metadata). Exposes:
        • get_items():           model-safe messages only (no metadata)
        • get_full_history():    [{"message": msg, "metadata": meta}, ...]
    """

    # Only these keys are ever sent to the model; the rest live in metadata.
    _ALLOWED_MSG_KEYS = {"role", "content", "name"}

    def __init__(
        self,
        keep_last_n_turns: int = 3,
        context_limit: int = 3,
        summarizer: Optional["Summarizer"] = None,
        session_id: Optional[str] = None,
    ):
        assert context_limit >= 1
        assert keep_last_n_turns >= 0
        assert keep_last_n_turns <= context_limit, "keep_last_n_turns should not be greater than context_limit"

        self.keep_last_n_turns = keep_last_n_turns
        self.context_limit = context_limit
        self.summarizer = summarizer
        self.session_id = session_id or "default"

        self._records: deque[Record] = deque()
        self._lock = asyncio.Lock()

    # --------- public API used by your runner ---------
    async def get_items(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return model-safe messages only (no metadata)."""
        async with self._lock:
            data = list(self._records)
        msgs = [self._sanitize_for_model(rec["msg"]) for rec in data]
        return msgs[-limit:] if limit else msgs

    async def add_items(self, items: List[Dict[str, Any]]) -> None:
        """Append new items and, if needed, summarize older turns."""
        # 1) Ingest items
        async with self._lock:
            for it in items:
                msg, meta = self._split_msg_and_meta(it)
                self._records.append({"msg": msg, "meta": meta})

            need_summary, boundary = self._summarize_decision_locked()

        # 2) No summarization needed → just normalize flags and exit
        if not need_summary:
            async with self._lock:
                self._normalize_synthetic_flags_locked()
            return

        # 3) Prepare summary prefix (model-safe copy) outside the lock
        async with self._lock:
            snapshot = list(self._records)
            prefix_msgs = [r["msg"] for r in snapshot[:boundary]]

        user_shadow, assistant_summary = await self._summarize(prefix_msgs)

        # 4) Re-check and apply summary atomically
        async with self._lock:
            still_need, new_boundary = self._summarize_decision_locked()
            if not still_need:
                self._normalize_synthetic_flags_locked()
                return

            snapshot = list(self._records)
            suffix = snapshot[new_boundary:]  # keep-last-N turns live here

            # Replace with: synthetic pair + suffix
            self._records.clear()
            self._records.extend([
                {
                    "msg": {"role": "user", "content": user_shadow},
                    "meta": {
                        "synthetic": True,
                        "kind": "history_summary_prompt",
                        "summary_for_turns": f"< all before idx {new_boundary} >",
                    },
                },
                {
                    "msg": {"role": "assistant", "content": assistant_summary},
                    "meta": {
                        "synthetic": True,
                        "kind": "history_summary",
                        "summary_for_turns": f"< all before idx {new_boundary} >",
                    },
                },
            ])
            self._records.extend(suffix)

            # Ensure all real user/assistant messages explicitly have synthetic=False
            self._normalize_synthetic_flags_locked()

    async def pop_item(self) -> Optional[Dict[str, Any]]:
        """Pop the latest message (model-safe), if any."""
        async with self._lock:
            if not self._records:
                return None
            rec = self._records.pop()
            return dict(rec["msg"])

    async def clear_session(self) -> None:
        """Remove all records."""
        async with self._lock:
            self._records.clear()

    def set_max_turns(self, n: int) -> None:
        """
        Back-compat shim for old callers: update `context_limit`
        and clamp `keep_last_n_turns` if needed.
        """
        assert n >= 1
        self.context_limit = n
        if self.keep_last_n_turns > self.context_limit:
            self.keep_last_n_turns = self.context_limit

    # Full history (debugging/analytics/observability)

    async def get_full_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Return combined history entries in the shape:
          {"message": {role, content[, name]}, "metadata": {...}}
        This is NOT sent to the model; for logs/UI/debugging only.
        """
        async with self._lock:
            data = list(self._records)
        out = [{"message": dict(rec["msg"]), "metadata": dict(rec["meta"])} for rec in data]
        return out[-limit:] if limit else out

    # Back-compat alias
    async def get_items_with_metadata(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return await self.get_full_history(limit)

    # Internals

    def _split_msg_and_meta(self, it: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Split input into (msg, meta):
          - msg keeps only _ALLOWED_MSG_KEYS; if role/content missing, default them.
          - everything else goes under meta (including nested "metadata" if provided).
          - default synthetic=False for real user/assistant unless explicitly set.
        """
        msg = {k: v for k, v in it.items() if k in self._ALLOWED_MSG_KEYS}
        extra = {k: v for k, v in it.items() if k not in self._ALLOWED_MSG_KEYS}
        meta = dict(extra.pop("metadata", {}))
        meta.update(extra)

        msg.setdefault("role", "user")
        msg.setdefault("content", str(it))

        role = msg.get("role")
        if role in ("user", "assistant") and "synthetic" not in meta:
            meta["synthetic"] = False
        return msg, meta

    @staticmethod
    def _sanitize_for_model(msg: Dict[str, Any]) -> Dict[str, Any]:
        """Drop anything not allowed in model calls."""
        return {k: v for k, v in msg.items() if k in SummarizingSession._ALLOWED_MSG_KEYS}

    @staticmethod
    def _is_real_user_turn_start(rec: Record) -> bool:
        """True if record starts a *real* user turn (role=='user' and not synthetic)."""
        return (
            rec["msg"].get("role") == "user"
            and not rec["meta"].get("synthetic", False)
        )

    def _summarize_decision_locked(self) -> Tuple[bool, int]:
        """
        Decide whether to summarize and compute the boundary index.

        Returns:
            (need_summary, boundary_idx)

        If need_summary:
          • boundary_idx is the earliest index among the last `keep_last_n_turns`
            *real* user-turn starts.
          • Everything before boundary_idx becomes the summary prefix.
        """
        user_starts: List[int] = [
            i for i, rec in enumerate(self._records) if self._is_real_user_turn_start(rec)
        ]
        real_turns = len(user_starts)

        # Not over the limit → nothing to do
        if real_turns <= self.context_limit:
            return False, -1

        # Keep zero turns verbatim → summarize everything
        if self.keep_last_n_turns == 0:
            return True, len(self._records)

        # Otherwise, keep the last N turns; summarize everything before the earliest of those
        if len(user_starts) < self.keep_last_n_turns:
            return False, -1  # defensive (shouldn't happen given the earlier check)

        boundary = user_starts[-self.keep_last_n_turns]

        # If there is nothing before boundary, there is nothing to summarize
        if boundary <= 0:
            return False, -1

        return True, boundary

    def _normalize_synthetic_flags_locked(self) -> None:
        """Ensure all real user/assistant records explicitly carry synthetic=False."""
        for rec in self._records:
            role = rec["msg"].get("role")
            if role in ("user", "assistant") and "synthetic" not in rec["meta"]:
                rec["meta"]["synthetic"] = False

    async def _summarize(self, prefix_msgs: List[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Ask the configured summarizer to compress the given prefix.
        Uses model-safe messages only. If no summarizer is configured,
        returns a graceful fallback.
        """
        if not self.summarizer:
            return ("Summarize the conversation we had so far.", "Summary unavailable.")
        clean_prefix = [self._sanitize_for_model(m) for m in prefix_msgs]
        return await self.summarizer.summarize(clean_prefix)
```

![Context Trimming in Session](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/summarizingSession.jpg)

**整體概念**

* **一個 turn** = 一則**真正的 user** 訊息，**加上它後面的所有內容**（assistant 回覆、tool call/結果等），**直到下一則真正的 user 訊息**。
* 你要設定兩個參數：

  * **`context_limit`**：原始歷史中允許的**真實 user turn** 最大數量，超過就做摘要。
  * **`keep_last_n_turns`**：做摘要時，原樣保留最近幾個 **turn**。

    * 不變式：`keep_last_n_turns <= context_limit`。
* 當**真實** user turn 數量超過 `context_limit`，session 會：

  1. **摘要**「最後 `keep_last_n_turns` 個 turn 中最早那個 turn 開始位置」**之前**的所有內容，
  2. 在保留區域的最上面注入一對**合成的 user→assistant 訊息**：

     * `user`：`"Summarize the conversation we had so far."`（shadow prompt）
     * `assistant`：`{generated summary}`
  3. 把最後 `keep_last_n_turns` 個 turn **原樣保留**。

這保證最後 `keep_last_n_turns` 個 turn 完全照原樣保存，而更早的內容都被壓縮進那兩則合成訊息。


```python
session = SummarizingSession(
    keep_last_n_turns=2,
    context_limit=4,
    summarizer=LLMSummarizer(client)
)
```

```python

# Example flow
await session.add_items([{"role": "user", "content": "Hi, my router won't connect. by the way, I am using Windows 10. I tried troubleshooting via your FAQs but I didn't get anywhere. This is my third tiem calling you. I am based in the US and one of Premium customers."}])
await session.add_items([{"role": "assistant", "content": "Let's check your firmware version."}])
await session.add_items([{"role": "user", "content": "Firmware v1.0.3; still failing."}])
await session.add_items([{"role": "assistant", "content": "Try a factory reset."}])
await session.add_items([{"role": "user", "content": "Reset done; error 42 now."}])
await session.add_items([{"role": "assistant", "content": "Try to install a new firmware."}])
await session.add_items([{"role": "user", "content": "I tried but I got another error now."}])
await session.add_items([{"role": "assistant", "content": "Can you please provide me with the error code?"}])
await session.add_items([{"role": "user", "content": "It says 404 not found when I try to access the page."}])
await session.add_items([{"role": "assistant", "content": "Are you connected to the internet?"}])
# At this point, with context_limit=4, everything *before* the earliest of the last 4 turns
# is summarized into a synthetic pair, and the last 2 turns remain verbatim.
```

```python
history = await session.get_items()
# Pass `history` into your agent runner / responses call as the conversation context.
```

```python
history
```

??? note "輸出"

    ```text
    [{'role': 'user', 'content': 'Summarize the conversation we had so far.'},
     {'role': 'assistant',
      'content': '• Product & Environment:\n  - Router with Firmware v1.0.3, Windows 10, based in the US.\n\n• Reported Issue:\n  - Router fails to connect.\n\n• Steps Tried & Results:\n  - Checked FAQs: No resolution.\n  - Checked firmware version: v1.0.3, problem persists.\n  - Factory reset: Resulted in error 42.\n\n• Identifiers:\n  - Premium customer (no specific identifier provided).\n\n• Timeline Milestones:\n  - Initial troubleshooting via FAQs.\n  - Firmware check (before factory reset).\n  - Factory reset → Error 42.\n\n• Tool Performance Insights:\n  - Firmware version check successful.\n  - Factory reset resulted in new error (42).\n\n• Current Status & Blockers:\n  - Connection issue unresolved; error 42 is the immediate blocker.\n\n• Next Recommended Step:\n  - Install a new firmware update.'},
     {'role': 'user', 'content': 'I tried but I got another error now.'},
     {'role': 'assistant',
      'content': 'Can you please provide me with the error code?'},
     {'role': 'user',
      'content': 'It says 404 not found when I try to access the page.'},
     {'role': 'assistant', 'content': 'Are you connected to the internet?'}]
    ```

```python
print(history[1]['content'])
```

??? note "輸出"

    ```text
    • Product & Environment:
      - Router with Firmware v1.0.3, Windows 10, based in the US.

    • Reported Issue:
      - Router fails to connect.

    • Steps Tried & Results:
      - Checked FAQs: No resolution.
      - Checked firmware version: v1.0.3, problem persists.
      - Factory reset: Resulted in error 42.

    • Identifiers:
      - Premium customer (no specific identifier provided).

    • Timeline Milestones:
      - Initial troubleshooting via FAQs.
      - Firmware check (before factory reset).
      - Factory reset → Error 42.

    • Tool Performance Insights:
      - Firmware version check successful.
      - Factory reset resulted in new error (42).

    • Current Status & Blockers:
      - Connection issue unresolved; error 42 is the immediate blocker.

    • Next Recommended Step:
      - Install a new firmware update.
    ```

你可以用 get_items_with_metadata 方法取得 session 的完整歷史（含 metadata），用於 debug 和分析。

```python
full_history = await session.get_items_with_metadata()
```

```python
full_history
```

??? note "輸出"

    ```text
    [{'message': {'role': 'user',
       'content': 'Summarize the conversation we had so far.'},
      'metadata': {'synthetic': True,
       'kind': 'history_summary_prompt',
       'summary_for_turns': '< all before idx 6 >'}},
     {'message': {'role': 'assistant',
       'content': '**Product & Environment:**\n- Device: Router\n- OS: Windows 10\n- Firmware: v1.0.3\n\n**Reported Issue:**\n- Router fails to connect to the internet, now showing error 42.\n\n**Steps Tried & Results:**\n- Checked FAQs: No resolution.\n- Firmware version checked: v1.0.3.\n- Factory reset performed: Resulted in error 42.\n\n**Identifiers:**\n- UNVERIFIED\n\n**Timeline Milestones:**\n- User attempted FAQ troubleshooting.\n- Firmware checked after initial advice.\n- Factory reset led to error 42.\n\n**Tool Performance Insights:**\n- FAQs and basic reset process did not resolve the issue.\n\n**Current Status & Blockers:**\n- Error 42 unresolved; firmware update needed.\n\n**Next Recommended Step:**\n- Install the latest firmware update and check for resolution.'},
      'metadata': {'synthetic': True,
       'kind': 'history_summary',
       'summary_for_turns': '< all before idx 6 >'}},
     {'message': {'role': 'user',
       'content': 'I tried but I got another error now.'},
      'metadata': {'synthetic': False}},
     {'message': {'content': 'I still have a problem with my router.',
       'role': 'user'},
      'metadata': {'synthetic': False}},
     {'message': {'content': [], 'role': 'user'},
      'metadata': {'id': 'rs_68ba192de700819dbed28ad768a9c48205277fe33200f1e3',
       'summary': [],
       'type': 'reasoning',
       'synthetic': False}},
     {'message': {'content': [{'annotations': [],
         'text': 'Sorry you’re still stuck. What is the exact error code/message you see now during the firmware update, and does it appear in the router’s web UI or elsewhere?\n\nWhile you check that, try these quick, safe steps:\n1) Verify the firmware file exactly matches your router’s model and hardware revision (check the label on the router) and region.\n2) Re‑download the firmware from the vendor site and verify its checksum (MD5/SHA256) if provided.\n3) Use a wired Ethernet connection to a LAN port, disable Wi‑Fi on the PC, and try a different browser with extensions disabled.\n4) Ensure you’re uploading the correct file type (e.g., .bin/.img), not a ZIP; don’t rename the file.\n5) Reboot the router and your PC, then retry the upload; after starting the update, wait at least 10 minutes and don’t power off.\n\nNote: “Error 42” meanings vary by brand; once you share the exact current error text and where it appears, I’ll give brand‑specific steps (including recovery options if needed).',
         'type': 'output_text',
         'logprobs': []}],
       'role': 'assistant'},
      'metadata': {'id': 'msg_68ba19400060819db38bcb891e9aec7605277fe33200f1e3',
       'status': 'completed',
       'type': 'message',
       'synthetic': False}}]
    ```

```python
print(history[1]['content'])
```

??? note "輸出"

    ```text
    **Product & Environment:**
    - Device: Router
    - OS: Windows 10
    - Firmware: v1.0.3

    **Reported Issue:**
    - Router fails to connect to the internet, now showing error 42.

    **Steps Tried & Results:**
    - Checked FAQs: No resolution.
    - Firmware version checked: v1.0.3.
    - Factory reset performed: Resulted in error 42.

    **Identifiers:**
    - UNVERIFIED

    **Timeline Milestones:**
    - User attempted FAQ troubleshooting.
    - Firmware checked after initial advice.
    - Factory reset led to error 42.

    **Tool Performance Insights:**
    - FAQs and basic reset process did not resolve the issue.

    **Current Status & Blockers:**
    - Error 42 unresolved; firmware update needed.

    **Next Recommended Step:**
    - Install the latest firmware update and check for resolution.
    ```

### 筆記與設計選擇

* **「新」的一側保留 turn 邊界**：**`keep_last_n_turns` 個 user turn** 原樣保留，更舊的全部壓縮。
* **兩則訊息的摘要區塊**：下游工具容易偵測或顯示（`metadata.synthetic == True`）。
* **async + 鎖的紀律**：（可能很慢的）摘要執行期間我們**釋放鎖**，然後在套用摘要之前重新檢查條件，避免競態合併。
* **冪等行為**：如果摘要期間有更多訊息進來，await 之後的重新檢查能避免過時的覆寫。


## Evals

說到底，context engineering 也是 **evals is all you need**。要問的關鍵問題是：*我們怎麼知道模型沒有「丟失 context」或「搞混 context」？*

雖然以後關於記憶的完整 cookbook 可以獨立成篇，這裡先給幾個輕量的 eval 做法：

* **Baseline 和差異：** 持續跑你的核心 eval 集，比較實驗前後，衡量記憶有沒有改善。
* **LLM-as-Judge：** 用設計過評分 prompt 的模型評估摘要品質。重點看它有沒有用對的格式抓到最重要的細節。
* **逐字稿重播：** 重跑長對話，衡量有沒有 context trimming 時的下一回合準確度。指標可以包括實體/ID 的完全比對，以及推理品質的 rubric 評分。
* **錯誤退步追蹤：** 留意常見失敗模式：問題沒被回答、限制被丟掉、或不必要/重複的 tool call。
* **Token 壓力檢查：** 標出 token 上限迫使丟掉受保護 context 的案例。記錄前後的 token 數，偵測關鍵細節何時被裁掉。

---

## 重點整理

- Context 管理的目標是在連貫和效率之間取平衡，帶太多太少都會出問題。
- Trimming 簡單、確定、零延遲，但會突然「失憶」；適合任務彼此獨立的流程。
- Summarization 能長距離保留記憶，但有摘要遺失和 context poisoning 的風險，還要多花模型呼叫。
- 切 turn 時要保留完整邊界（user 訊息加上它後面的 assistant/tool 項目），不要只切個別訊息。
- 摘要 prompt 要依使用情境設計，並用 eval（baseline、LLM-as-Judge、重播）持續驗證。

## 練習

1. 把 `TrimmingSession` 的 `max_turns` 從 3 改成 2，重跑同一段客服對話，觀察 agent 在哪個問題開始「忘記」前面的內容。
2. 改寫摘要 prompt，加上「列出時間戳」和「分段整理已解決/未解決的問題」，比較摘要輸出的差異。
3. 把 summarizing session 的 `context_limit` 和 `keep_last_n_turns` 調成不同組合（例如 4 和 2），用 `get_items_with_metadata` 檢查歷史裡哪些是 `synthetic` 訊息，並寫個小檢查確認 `keep_last_n_turns <= context_limit`。
