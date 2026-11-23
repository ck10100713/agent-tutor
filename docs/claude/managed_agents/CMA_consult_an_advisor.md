---
translated: true
source: managed_agents/CMA_consult_an_advisor.ipynb
---
# Advisor：讓工作中的 agent 在一輪中途請教更強的 model

> 原文：[managed_agents/CMA_consult_an_advisor.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_consult_an_advisor.ipynb)

在 Managed Agents 的 roster 加一個 advisor 項目，讓中階的工作 model 能在一輪裡請教更強的 model，從 event stream 讀每次諮詢、用 advisor thread 的 usage 算成本，並處理被遮蔽（redacted）的回傳。

## 這篇在做什麼

這篇示範在 Managed Agents 的 `multiagent` roster 裡加一個 advisor 項目，讓 Sonnet 工作到一半遇到難決策時，自己呼叫更強的 Opus 給建議。你會從 event stream 看到每次諮詢，並用 thread 的 usage 算出實際花了多少。

## 學完你會

- 在 agent 的 `multiagent` roster 加上 `{"type": "advisor", "model": ...}`，並用 system prompt 設定什麼時候該諮詢
- 從 primary stream 讀出諮詢 thread 的生命週期，並用 `usage.list_cost` 算出成本
- 處理 advisor 輸出被 redacted 的情況，以及 advisor 搭配 specialist 團隊的用法

## 開跑前

- 需要 Anthropic API key，且帳號有 Managed Agents 使用權限
- 需要 `anthropic>=0.121.0`
- 範例會用到 Opus 當 advisor，費用比純 Sonnet 高

所有輪次都跑在最強的 model 上是安全的選擇，也是最貴的。跑在中階 model 上很便宜，直到 agent 碰到任務中需要更多判斷力的那個決定，那時它已經往下做了。一般的解法是自己做升級機制：偵測困難情況、打包 context、呼叫更大的 model、再把答案塞回去。

advisor 把這件事放在 session 裡面做。你在 agent 的 `multiagent` roster 裡用 `{"type": "advisor", "model": ...}` 項目指定第二個更強的 model。primary thread 就會有一個 `advisor` tool 能在一輪中途呼叫：平台把到目前為止的對話放到 advisor model 面前，把它的建議回傳給工作 model，然後繼續 sampling。每次諮詢都是一個短命的平台 thread，有自己的 token usage，所以你看得到它何時發生，也能精確算出花了多少。

這個 notebook 會走過：

- 在 agent 加上 advisor 項目
- 告訴工作 model 什麼時候該諮詢
- 從 event stream 讀一次諮詢，並從 thread 讀它的成本
- advisor 輸出被 redacted 時有什麼不同

## 1. 設定 client

advisor 項目放在 `multiagent` 區塊，使用標準的 `managed-agents-2026-04-01` beta header。有型別的 roster 形狀需要 `anthropic>=0.121.0`。

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
WORKER_MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
ADVISOR_MODEL = os.environ.get("COOKBOOK_ADVISOR_MODEL", "claude-opus-5-5")
client = anthropic.Anthropic()
```

## 2. 給 Sonnet agent 一個 Opus advisor

advisor 是在 roster 裡宣告的，不是 tool 定義，也不是另外建立的 agent。這個項目放在 `multiagent.agents` 裡，跟任何 specialist 並列，而 roster 只有 advisor 一個項目也是合法的：agent 會諮詢但不會產生 subagent。server 在儲存時會強制幾條規則：

- 每個 roster 最多一個 advisor 項目。
- `model` 必須是允許當 advisor 的，agent 自己的 model 和它的搭配也必須是平台允許的。不合格的搭配會在 `agents.create` 直接得到 400，不會等到執行時才出意外。
- 這個項目佔用 roster 中 `anthropic.advisor` 這個名字，所以 specialist 不能用這個名字。

執行時，平台會把這個項目以 `advisor` tool 的形式呈現給工作 model。這個 tool 不接受輸入，因為 advisor 讀的是到呼叫為止的整段對話，而不是工作 model 寫的查詢。所以 system prompt 是你設定諮詢策略的地方：它控制的是 model 何時會去用這個 tool。

```python
SYSTEM = """You are a backend engineer designing HTTP APIs.
You have an advisor: a more capable model that can review your conversation so far and
send back guidance. Consult it with the advisor tool before you commit to any decision
that would be expensive to reverse once clients depend on it: identifier and idempotency
schemes, pagination contracts, error semantics, versioning. Do routine drafting yourself.
When you consult, act on the guidance you get back and say what you changed.
Write your final design to /mnt/session/outputs/design.md."""

designer = client.beta.agents.create(
    name="api_designer",
    description="Designs HTTP APIs, escalating irreversible decisions to an advisor.",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-consult-an-advisor"},
    model={"id": WORKER_MODEL},
    system=SYSTEM,
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "coordinator",
        "agents": [
            {"type": "advisor", "model": ADVISOR_MODEL},
        ],
    },
    betas=BETAS,
)
print(f"{designer.name}: {designer.id} v{designer.version}")
print("roster:", [entry.to_dict() for entry in designer.multiagent.agents])
```

??? note "輸出"

    ```text
    api_designer: agent_staging_018FvRjvrM6ASGuXXcDTAvdH v1
    roster: [{'model': 'claude-opus-5', 'type': 'advisor'}]
    ```

## 3. 交給它一個裡面有難題的任務

為會動到錢的 endpoint 設計 idempotency 機制，就是 prompt 要 agent 往上升級的那種決定：寫起來便宜，client 一旦依賴它就很貴才改得動。設計的其餘部分都是例行公事，所以校準得好的 agent 會在這一點諮詢，其餘自己草擬。

諮詢的花費只受諮詢那一輪限制：advisor token 是在工作 model 之外另外計費，而且沒有每次諮詢的上限。session 帶有 `budget`，這樣過度愛升級的習慣會在已知的上限暫停，而不是把帳單越燒越高（機制見 [`CMA_cap_session_spend.ipynb`](CMA_cap_session_spend.md)）。

```python
env = client.beta.environments.create(
    name="advisor-demo",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
    betas=BETAS,
)

session = client.beta.sessions.create(
    agent=designer.id,
    environment_id=env.id,
    title="Design: refunds API",
    budget={"type": "limit", "max_list_cost": {"currency": "USD", "amount": "500"}},
    initial_events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": "Design the REST surface for a refunds resource on a payments "
                    "API: create, retrieve, list. Refund creation is retried by mobile "
                    "clients on flaky networks, and a double refund costs real money. "
                    "Cover the request/response shapes, idempotency, pagination on list, "
                    "and error codes.",
                }
            ],
        }
    ],
    betas=BETAS,
)
print(session.id, session.status)
```

??? note "輸出"

    ```text
    sesn_staging_013TqQwzrbUZDX1KJW2b9KnC running
    ```

## 4. 在 primary stream 上看一次諮詢

諮詢不是 `agent.tool_use` event。它在 primary stream 上以 thread 生命週期的形式出現，`agent_name` 設為 `anthropic.advisor`：

```
session.thread_created            agent_name: anthropic.advisor
session.thread_status_running     agent_name: anthropic.advisor
agent.thread_message_received     from_agent_name: anthropic.advisor, content: [{type: "text", ...}]
session.thread_status_idle        agent_name: anthropic.advisor
session.thread_status_terminated  agent_name: anthropic.advisor
```

發出諮詢的 thread 全程維持 `running`。建議在呼叫的當下送達，sampling 繼續，所以從外面看，primary thread 暫停，一個 advisor thread 出現又消失，然後 primary thread 帶著建議繼續。每次諮詢都是一個全新的 thread，送出建議後自己結束。

```python
def advice_text(content):
    """Render an advisor delivery: joined text, or a marker for the redacted arm."""
    if any(block.type == "redacted" for block in content):
        return "[redacted advice: content withheld by the advisor model's policy]"
    return "".join(block.text for block in content if block.type == "text")


consultations = 0

with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "session.thread_created" and ev.agent_name == "anthropic.advisor":
            consultations += 1
            print(f"\n--- consulting advisor #{consultations} ({ev.session_thread_id}) ---")
        elif (
            ev.type == "agent.thread_message_received" and ev.from_agent_name == "anthropic.advisor"
        ):
            print(advice_text(ev.content)[:800])
            print("--- advice received, primary thread resumes ---\n")
        elif ev.type == "agent.message":
            print("".join(b.text for b in ev.content if b.type == "text"), end="")
        elif ev.type == "session.status_idle":
            print(f"\n[idle] stop_reason={ev.stop_reason.type}")
            break

print(f"\nconsultations this turn: {consultations}")
```

??? note "輸出"

    ```text

    --- consulting advisor #1 (sthr_staging_01PnQEQPc1nLxUK4S2vcVbCL) ---
    ```

    ```text
    [redacted advice: content withheld by the advisor model's policy]
    --- advice received, primary thread resumes ---
    ```

    ```text
    Incorporated the advisor's feedback directly into the design — the most consequential changes were:

    - **Idempotency became a stored resource with a claim→execute→finalize lifecycle**, not a simple header check. This closes the "processor succeeded but our server died before recording it" window, which a naive check-then-execute design leaves open.
    - **Added a second, independent safety layer**: a server-side invariant (`sum(active refunds) + new_amount <= captured_amount`) enforced under a row lock, so the system is safe even if a client reuses/loses its idempotency key.
    - **Made refund creation explicitly asynchronous** (`201` + `status: pending`, terminal states `succeeded|failed|canceled`) instead of implying synchronous success.
    - **Added a recovery path** (`GET /refunds?idempotency_key=...`) for clients that lose the response to a request that actually succeeded — critical for flaky mobile networks.
    - **Switched list pagination to opaque cursor-based** instead of offset, since refunds are append-heavy and offset pagination skips/duplicates rows under concurrent inserts.
    - **Made the retry policy part of the documented contract** (which codes are safe to retry, and that retries must reuse the same idempotency key), not just implicit.
    - **Resolved the nesting question**: creation under `/payments/{id}/refunds` for natural scoping and clean 404s; retrieve/list stay top-level at `/refunds`.

    Full design written below.
    ```

    ```text
    The design is written to `/mnt/session/outputs/design.md`.

    **Summary of the approach:**

    - **Endpoints:** `POST /v1/payments/{payment_id}/refunds` (create, scoped to parent), `GET /v1/refunds/{id}` (retrieve), `GET /v1/refunds` (list) — top-level for retrieve/list per advisor guidance.
    - **Idempotency — the centerpiece:** `Idempotency-Key` header is required and persisted as its own resource with a **claim → execute → finalize** lifecycle (claim written in the same transaction as the pending refund), so a crash after the processor succeeds but before we record it can't produce a silent duplicate on retry. Replay rules are explicit: same key+body replays the original response, same key+different body is a `422`, same key still in-flight is a `409`.
    - **Second safety net, independent of the header:** a server-enforced invariant (`sum(active refunds) + new_amount <= captured_amount`) under a row lock, protecting against buggy clients that regenerate keys or omit them.
    - **Async-first status model:** `201` means "accepted," not "money moved" — `pending → succeeded|failed|canceled`.
    - **Recovery path:** `GET /v1/refunds?idempotency_key=...` so a client that lost the response never needs to guess by retrying a write.
    - **Pagination:** opaque cursor on `(created_at DESC, id DESC)`, not offset, since refunds are append-only and growing.
    - **Errors:** one envelope (`type`, `code`, `message`, `param`, `request_id`), plus an explicit table of which codes are safe to retry with the same key — documented as part of the API contract, not left to client guesswork.

    All of this reflects the advisor's review — the biggest change from my initial draft was moving idempotency from "check a header" to "a durably-claimed resource," and adding the amount-conservation invariant as a belt-and-suspenders check that holds even when the idempotency layer is bypassed.
    [idle] stop_reason=end_turn

    consultations this turn: 1
    ```

## 5. 計算諮詢的成本

因為每次諮詢都是真正的 session thread，成本記在那個 thread 上，而不是不可見地混進 primary thread 的數字。用 `session.thread_created` event 裡的 id 取出每個 advisor thread，讀它的 `usage`。token 數在那裡，`usage.list_cost` 也在：thread 的 token 以 advisor model 的公開牌價計算，是以美元最小單位表示的整數字串（`"131"` 是 $1.31），所以成本直接從 API 取得，不用自己維護價目表。這些 token 是在 primary thread 之外另外計費，而且已經算進 session 層級的 `usage` 彙總裡，彙總也有自己的 `list_cost`。

完成的諮詢是一個 `terminated` thread。它仍然能取回，但它的 `agent` 不是一般那種快照的 agent：平台 advisor 沒有 Agent 資源支撐，所以 thread 帶的是 roster 項目本身，`{"type": "advisor", "model": ...}`。這個 `agent.type` 為 `"advisor"`，是區分平台 advisor thread 和一般子 thread 的可靠方式，比名字更可靠。

```python
from decimal import Decimal


def usd(money) -> str:
    """Render an integer minor-unit amount ("131" = $1.31) as dollars."""
    return f"${Decimal(money.amount) / 100:.2f}"


advisor_thread_ids = [
    ev.session_thread_id
    for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS)
    if ev.type == "session.thread_created" and ev.agent_name == "anthropic.advisor"
]

advisor_in = advisor_out = 0
advisor_cents = Decimal("0")
for thread_id in advisor_thread_ids:
    thread = client.beta.sessions.threads.retrieve(thread_id, session_id=session.id, betas=BETAS)
    usage = thread.usage
    advisor_in += usage.input_tokens or 0
    advisor_out += usage.output_tokens or 0
    advisor_cents += Decimal(usage.list_cost.amount)
    print(
        f"{thread.id}  agent.type={thread.agent.type}  model={thread.agent.model}  "
        f"status={thread.status}  "
        f"in={usage.input_tokens} out={usage.output_tokens}  {usd(usage.list_cost)}"
    )

total = client.beta.sessions.retrieve(session.id, betas=BETAS).usage
print(f"\nadvisor tokens: in={advisor_in} out={advisor_out}  cost=${advisor_cents / 100:.2f}")
print(
    f"session total:  in={total.input_tokens} out={total.output_tokens}  "
    f"cost={usd(total.list_cost)}  (advisor included)"
)
```

??? note "輸出"

    ```text
    sthr_staging_01PnQEQPc1nLxUK4S2vcVbCL  agent.type=advisor  model=claude-opus-5  status=terminated  in=603 out=2468  $0.07

    advisor tokens: in=603 out=2468  cost=$0.07
    session total:  in=15553 out=8491  cost=$0.21  (advisor included)
    ```

## 6. 讀設計成果

agent 用 `write` tool 寫出最後的文件。從 event log 取出它，看 idempotency 那一節，那就是諮詢發揮作用的地方。

```python
design = ""
for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS):
    if (
        ev.type == "agent.tool_use"
        and ev.name == "write"
        and ev.input.get("file_path", "").endswith("design.md")
    ):
        design = ev.input["content"]  # keep the last write, in case of revisions

for line in design.splitlines():
    if line.startswith("#"):
        print(line)
print()
print(design[:1200])
```

??? note "輸出"

    ```text
    # Refunds API Design
    ## 1. Resources & endpoints
    ## 2. Idempotency (the core problem: safe retries on flaky mobile networks)
    ### 2.1 Header contract
    ### 2.2 Server-side lifecycle (claim → execute → finalize)
    ### 2.3 Replay semantics (what a retry actually gets back)
    ### 2.4 Second, independent safety layer: a business invariant
    ### 2.5 Recovery path for lost responses
    ## 3. Request / response shapes
    ### 3.1 Create
    ### 3.2 Retrieve
    ### 3.3 List
    ## 4. Error model

    # Refunds API Design

    ## 1. Resources & endpoints

    | Action | Method & path |
    |---|---|
    | Create a refund | `POST /v1/payments/{payment_id}/refunds` |
    | Retrieve a refund | `GET /v1/refunds/{refund_id}` |
    | List refunds | `GET /v1/refunds` |
    | Look up by idempotency key (recovery) | `GET /v1/refunds?idempotency_key={key}` |

    **Why creation is nested but retrieve/list are top-level:** creation under the parent
    gives a natural scope for the amount-conservation invariant ("refunds of this payment")
    and a clean `404` when `payment_id` doesn't exist or isn't owned by the caller. Retrieve
    and list don't need that scope, and clients generally want to fetch/list refunds without
    knowing the parent — so they stay at a flat `/refunds` collection. Both resources are
    versioned via the URL (`/v1/...`); breaking changes get a new version, not a new header.

    Refund IDs: `re_<26-char base32 ulid>` — sortable by creation time, opaque, collision-safe,
    visually distinct from payment IDs (`pi_...`). Never expose database auto-increment IDs.

    ## 2. Idempotency (the core problem: safe retries on flaky mobile networks)

    ### 2.1 Header contract

    - `Idempotency-Key` is **required** on `POST .../refunds`. Cl
    ```

## 7. 建議被 redacted 的時候

你能不能讀到諮詢內容，是 advisor model 的屬性，由管轄 Messages API advisor tool 的同一套 Anthropic 政策決定。對於政策扣留輸出的 model，傳遞 event 帶的是 `[{"type": "redacted"}]` 佔位 block 而不是文字，advisor thread 自己的 `agent.message` event 也是佔位。

redaction 改變的是你觀察到的內容，不是 agent 使用的內容。工作 model 無論如何都讀到完整的建議，所以設計還是會進步。所有結構性的東西都還看得到：thread、它的狀態轉換、它的時間，以及它的 `usage`，這也是為什麼第 4 步的 `advice_text` helper 會顯示標記而不是當掉。advisor 自己的推理在兩種政策下都不會送出，只有它的最終文字。

由於政策可以在 API 不變的情況下改變，任何消費這些 event 的程式，都要把 `text` 和 `redacted` 兩種分支當成同樣正常。

## 8. advisor 搭配 specialist 團隊

advisor 項目和一般 roster 成員共用 `agents` 陣列，所以 coordinator 可以在同一個 session 裡委派給 specialist，也能請教更強的 model。只有 primary thread 能諮詢。它產生的 specialist 沒有自己的 advisor，而且 advisor thread 不受子 thread 並行數上限限制，所以已經到子 thread 上限的 coordinator 仍然可以諮詢。

```python
client.beta.agents.create(
    name="research_coordinator",
    model={"id": WORKER_MODEL},
    system="Delegate research to your specialists, then synthesize their reports.",
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "coordinator",
        "agents": [
            "agent_01Res...",                                # a specialist, by id
            {"type": "agent", "id": "agent_01Aud...", "version": 3},
            {"type": "advisor", "model": ADVISOR_MODEL},     # the advisor
        ],
    },
    betas=BETAS,
)
```

coordinator 模式本身、每個角色的 tool 範圍限制和委派 event 類型，在 [`CMA_coordinate_specialist_team.ipynb`](CMA_coordinate_specialist_team.md) 裡講。advisor 在 session 建立時就固定了：在 agent 上改它，只影響之後建立的 session，不影響已經在跑的。

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

## 重點整理

- advisor 讓中階 model 在一輪中途請教更強的 model，省去自己做升級機制，貴的 model 只在難決策時才用
- advisor 在 `multiagent` roster 宣告，tool 不吃輸入，所以「何時諮詢」要靠 system prompt 設定
- 每次諮詢是獨立 thread，成本可從 thread 的 `usage.list_cost` 精確取得；advisor token 另計，要用 `budget` 設上限
- advisor 輸出可能被 redacted，處理 event 的程式要同時接受 `text` 和 `redacted`
- 只有 primary thread 能諮詢，advisor 在 session 建立時固定

## 練習

1. 改第 2 步的 system prompt，把「何時該諮詢」的條件放寬或收緊，觀察諮詢次數變化。
2. 在第 5 步的成本計算 cell 中，加總所有 advisor thread 的 `list_cost`，並跟 session 層級 `usage` 的 `list_cost` 比對。
3. 照第 8 步，在 roster 加一個 specialist，讓 coordinator 同時委派工作又諮詢 advisor，從 stream 區分兩種 thread。
