---
translated: true
source: tool_use/automatic-context-compaction.ipynb
---
# 自動 context compaction

> 原文：[tool_use/automatic-context-compaction.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/automatic-context-compaction.ipynb)

在長時間執行的 agent 流程裡，自動壓縮對話歷史，避免撞到 context 上限。

## 這篇在做什麼

用一個客服 agent 一張一張處理 support ticket 的例子，示範對話歷史怎麼隨著 tool 呼叫一路變大。再用 tool runner 的 `compact_before_next_turn()` 在適當時機把歷史壓成一份摘要，讓任務可以繼續跑下去。最後比較有沒有 compaction 的 token 用量。

## 學完你會

- 看懂 tool 密集的 agent 流程為什麼 token 會線性成長，並用數字量出來。
- 在 tool runner 的迴圈裡加上 threshold 判斷，呼叫 `compact_before_next_turn()` 觸發 compaction。
- 設計「每個項目互相獨立」的流程，讓摘要只留完成紀錄、丟掉細節。

## 開跑前

- Python 3.11 以上
- Anthropic API key，放在 `.env` 的 `ANTHROPIC_API_KEY`
- Anthropic SDK >= 2.0.0（用到 `compact-2026-09-04` beta）

長時間執行的 agent 任務常常會超過 context 上限。tool 用得多的流程，或是很長的對話，會很快把 token 的 context window 吃光。在 [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) 這篇裡我們講過，管理 context 可以避免效能下降和 context rot。

Anthropic Python SDK 的 tool runner 可以幫你處理這件事：當你的迴圈判斷對話已經太大，呼叫一次 `runner.compact_before_next_turn()`，API 就會在 server 端把歷史做成摘要，runner 之後從這份摘要接著跑，任務就能超出模型的 context window 限制繼續進行。

這份 cookbook 用一個 **agentic 客服流程** 來示範 context compaction。假設你做了一個 AI 客服 agent，要處理一整個 support ticket 佇列。每張 ticket 都要分類問題、搜尋知識庫、設定優先級、轉給對應的團隊、草擬回覆，最後標記完成。一張接一張處理下去，對話歷史就會塞滿分類結果、知識庫搜尋和草擬的回覆，很快吃掉幾千個 token。

## 什麼是 context compaction？

用 tool 打造 agentic 流程時，agent 在複雜任務上反覆迭代，對話會變得非常長。runner 驅動的 compaction 分四步處理：

1. 你的迴圈監控每一輪對話的 token 用量
2. 超過你設的 threshold 時，呼叫 `runner.compact_before_next_turn()`
3. 目前這一輪（包含它的 tool 呼叫）跑完後，runner 送出 compaction 請求。API 在 server 端把對話做成摘要，回傳單一個 `compaction` block（`stop_reason == "compaction"`）
4. runner 用這個 block 取代整段對話歷史，用壓縮後的 context 繼續任務

## 這份 cookbook 讀完，你會：

 - 了解怎麼在迭代式流程裡有效管理 context 上限
 - 寫出能用自動 context compaction 的 agent
 - 設計能在多次迭代中保持專注的流程

##  先決條件

開始前請確認你具備：

**需要的知識**

- 對 agentic 模式和 tool calling 有基本認識

**需要的工具**

- Python 3.11 或更高版本
- Anthropic API key
- Anthropic SDK >= 2.0.0（用到 `compact-2026-09-04` beta）

> **只想讓 compaction 自動發生？** 透過 `context_management` 啟用的 [server-side compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)，會在 input token 超過你設的 trigger（50k token 以上）時自己壓縮，完全不用寫迴圈邏輯。
>
> 這份 cookbook 講的是 **runner 驅動的 compaction**，由你的程式碼決定 *什麼時候* 壓縮。適合 threshold 很低、有天然的項目邊界（例如每處理 N 張 ticket 壓一次），或是想自訂摘要指示的情況。

## 設定

先安裝需要的套件：

```python
# %pip install -qU anthropic python-dotenv
```

注意：確認你的 .env 檔裡有：

`ANTHROPIC_API_KEY=your_key_here`

載入環境變數並設定 client。我們也會載入一個輔助工具，用來把 Claude 的 message 回應視覺化。


```python
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-5-5"
```

## 先把場景準備好

在 [utils/customer_service_tools.py](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/utils/customer_service_tools.py) 裡，我們定義了幾個處理客服 ticket 的函式：

- `get_next_ticket()` - 從佇列取出下一張還沒處理的 ticket
- `classify_ticket(ticket_id, category)` - 把問題分類成 billing、technical、account、product 或 shipping
- `search_knowledge_base(query)` - 找相關的說明文章和解法
- `set_priority(ticket_id, priority)` - 指定優先級（low、medium、high、urgent）
- `route_to_team(ticket_id, team)` - 把 ticket 轉給適當的客服團隊
- `draft_response(ticket_id, response_text)` - 產生要給客戶看的回覆
- `mark_complete(ticket_id)` - 把處理完的 ticket 結案

有了這些 tool，客服 agent 就能有系統地處理 ticket。每張 ticket 都要分類、查資料、排優先級、轉派、草擬回覆。連續處理 20 到 30 張時，對話歷史會被每一次分類、每一次知識庫搜尋、每一份草擬回覆的 tool 結果塞滿，token 就線性成長。

tool 上用了 `beta_tool` decorator，讓 Claude agent 可以使用它們。decorator 會抓出函式的參數和 docstring，當成 tool metadata 提供給 Claude。

```python
import anthropic
from anthropic import beta_tool

@beta_tool
def get_next_ticket() -> dict:
    """Retrieve the next unprocessed support ticket from the queue."""
    ...
```


```python
import anthropic
from utils.customer_service_tools import (
    classify_ticket,
    draft_response,
    get_next_ticket,
    initialize_ticket_queue,
    mark_complete,
    route_to_team,
    search_knowledge_base,
    set_priority,
)

client = anthropic.Anthropic()

tools = [
    get_next_ticket,
    classify_ticket,
    search_knowledge_base,
    set_priority,
    route_to_team,
    draft_response,
    mark_complete,
]
```

## 基準：不用 compaction 跑跑看

先看一個貼近實況的客服場景：處理一個 support ticket 佇列。

流程如下：

**每張 ticket：**
1. 用 `get_next_ticket()` 取得 ticket
2. 分類問題（billing、technical、account、product、shipping）
3. 搜尋知識庫找相關資訊
4. 設定適當的優先級（low、medium、high、urgent）
5. 轉給正確的團隊
6. 草擬客戶回覆
7. 標記 ticket 完成
8. 換下一張

**挑戰**：佇列裡有 5 張 ticket，每張要 7 次 tool 呼叫，Claude 會呼叫 35 次以上。每一步的結果，包含分類、知識庫搜尋、草擬的回覆，都會累積在對話歷史裡。沒有 compaction 的話，這些資料每一張 ticket 都會留在記憶體裡，到第 5 張時 context 已經包含前 4 張的完整細節。

我們先 **不用 compaction** 跑一次，看看會發生什麼事：

```python
from anthropic.types.beta import BetaMessageParam

num_tickets = 5
initialize_ticket_queue(num_tickets)

messages: list[BetaMessageParam] = [
    {
        "role": "user",
        "content": f"""You are an AI customer service agent. Your task is to process support tickets from a queue.

For EACH ticket, you must complete ALL these steps:

1. **Fetch ticket**: Call get_next_ticket() to retrieve the next unprocessed ticket
2. **Classify**: Call classify_ticket() to categorize the issue (billing/technical/account/product/shipping)
3. **Research**: Call search_knowledge_base() to find relevant information for this ticket type
4. **Prioritize**: Call set_priority() to assign priority (low/medium/high/urgent) based on severity
5. **Route**: Call route_to_team() to assign to the appropriate team
6. **Draft**: Call draft_response() to create a helpful customer response using KB information
7. **Complete**: Call mark_complete() to finalize this ticket
8. **Continue**: Immediately fetch the next ticket and repeat

IMPORTANT RULES:
- Process tickets ONE AT A TIME in sequence
- Complete ALL 7 steps for each ticket before moving to the next
- Keep fetching and processing tickets until you get an error that the queue is empty
- There are {num_tickets} tickets total - process all of them
- Be thorough but efficient

Begin by fetching the first ticket.""",
    }
]

total_input = 0
total_output = 0
turn_count = 0

runner = client.beta.messages.tool_runner(
    model=MODEL,
    max_tokens=4096,
    tools=tools,
    messages=messages,
)

for message in runner:
    messages_list = list(runner._params["messages"])
    turn_count += 1
    total_input += message.usage.input_tokens
    total_output += message.usage.output_tokens
    print(
        f"Turn {turn_count:2d}: Input={message.usage.input_tokens:7,} tokens | "
        f"Output={message.usage.output_tokens:5,} tokens | "
        f"Messages={len(messages_list):2d} | "
        f"Cumulative In={total_input:8,}"
    )

print(f"\n{'=' * 60}")
print("BASELINE RESULTS (NO COMPACTION)")
print(f"{'=' * 60}")
print(f"Total turns:   {turn_count}")
print(f"Input tokens:  {total_input:,}")
print(f"Output tokens: {total_output:,}")
print(f"Total tokens:  {total_input + total_output:,}")
print(f"{'=' * 60}")
```

??? note "輸出"

    ```text
    Turn  1: Input=  1,732 tokens | Output=   30 tokens | Messages= 1 | Cumulative In=   1,732
    ```

    ```text
    Turn  2: Input=  1,964 tokens | Output=  318 tokens | Messages= 3 | Cumulative In=   3,696
    ```

    ```text
    Turn  3: Input=  2,881 tokens | Output=  378 tokens | Messages= 5 | Cumulative In=   6,577
    ```

    ```text
    Turn  4: Input=  3,516 tokens | Output=   30 tokens | Messages= 7 | Cumulative In=  10,093
    ```

    ```text
    Turn  5: Input=  3,744 tokens | Output=  313 tokens | Messages= 9 | Cumulative In=  13,837
    ```

    ```text
    Turn  6: Input=  4,875 tokens | Output=  409 tokens | Messages=11 | Cumulative In=  18,712
    ```

    ```text
    Turn  7: Input=  5,538 tokens | Output=   30 tokens | Messages=13 | Cumulative In=  24,250
    ```

    ```text
    Turn  8: Input=  5,758 tokens | Output=  309 tokens | Messages=15 | Cumulative In=  30,008
    ```

    ```text
    Turn  9: Input=  6,619 tokens | Output=  443 tokens | Messages=17 | Cumulative In=  36,627
    ```

    ```text
    Turn 10: Input=  7,316 tokens | Output=   30 tokens | Messages=19 | Cumulative In=  43,943
    ```

    ```text
    Turn 11: Input=  7,533 tokens | Output=  314 tokens | Messages=21 | Cumulative In=  51,476
    ```

    ```text
    Turn 12: Input=  8,404 tokens | Output=  365 tokens | Messages=23 | Cumulative In=  59,880
    ```

    ```text
    Turn 13: Input=  9,019 tokens | Output=   30 tokens | Messages=25 | Cumulative In=  68,899
    ```

    ```text
    Turn 14: Input=  9,238 tokens | Output=  342 tokens | Messages=27 | Cumulative In=  78,137
    ```

    ```text
    Turn 15: Input=  9,910 tokens | Output=  413 tokens | Messages=29 | Cumulative In=  88,047
    ```

    ```text
    Turn 16: Input= 10,580 tokens | Output=   30 tokens | Messages=31 | Cumulative In=  98,627
    ```

    ```text
    Turn 17: Input= 10,642 tokens | Output=  454 tokens | Messages=33 | Cumulative In= 109,269

    ============================================================
    BASELINE RESULTS (NO COMPACTION)
    ============================================================
    Total turns:   17
    Input tokens:  109,269
    Output tokens: 4,238
    Total tokens:  113,507
    ============================================================
    ```

有了基準，就比較看得出沒有 compaction 時 context 是怎麼長大的。可以看到每一輪都是線性成長，因為每一輪的 input 都多了新的 token。

這會讓 token 消耗很高，也很快就可能碰到 context 上限：光是 5 張 ticket，累積的 input 就超過十萬 token。

來看看不用 compaction 處理完 5 張 ticket 後，Claude 的最終回應：

```python
print("".join(block.text for block in message.content if block.type == "text"))
```

??? note "輸出"

    ```text
    I processed all 5 tickets, and the queue is now empty. Each one was classified, prioritized, routed, given a draft response and marked complete.

    | Ticket | Category | Priority | Team | Notes |
    |---|---|---|---|---|
    | TICKET-1 (Morgan Jones) | billing | medium | billing-team | The charge date (10-09) doesn't match the signup date (10-04), so I flagged it for billing to review. |
    | TICKET-2 (Jane Smith) | technical | medium | tech-support | The subject line says upload error, but the description is about device sync. I drafted a response for the sync problem. |
    | TICKET-3 (Alex Johnson) | account | high | account-services | The email in the message differs from the ticket's contact email, so the draft asks the customer to confirm their registered address. |
    | TICKET-4 (Morgan Davis) | account | high | account-services | The customer lost their phone and their backup codes aren't being accepted, so they're locked out. The draft asks for identity verification. |
    | TICKET-5 (Sam Williams) | shipping | medium | logistics-team | The knowledge base has no shipping category. The draft asks for photos and promises no replacement timeline or policy. |

    On three tickets the subject line and the description didn't match (TICKET-1, 2 and 4). I went by the description each time. You may want to check those three.
    ```

### 搞清楚問題在哪

在上面的基準流程裡，Claude 必須：
- 依序處理 **5 張 support ticket**
- 每張完成 **7 個步驟**（取得、分類、查資料、排優先級、轉派、草擬、完成）
- 進行 **35 次 tool 呼叫**，結果全部累積在對話歷史裡
- 把 **每一次分類、每一次知識庫搜尋、每一份草擬回覆** 都存在記憶體裡

**為什麼會這樣**：
1. **token 線性成長**：每次用 tool，整段對話歷史（包含之前所有 tool 結果）都會再送給 Claude 一次
2. **context 被污染**：處理 Ticket B 時，Ticket A 的分類和草擬回覆還留在 context 裡
3. **成本越滾越大**：到 Ticket #5 時，每次 API 呼叫都帶著前 4 張 ticket 的資料
4. **回應變慢**：處理超大的 context 比較花時間
5. **有撞到上限的風險**：最後一定會碰到 context window 上限


**真正需要的**：Ticket A 做完後，我們只需要一份 **簡短摘要**（已解決、類別、優先級），不需要完整的分類結果、知識庫搜尋和整份草擬回覆。細節的流程應該丟掉，只留完成摘要。

來看看自動 context compaction 怎麼解決這個問題。

## 啟用自動 context compaction

跑一模一樣的客服流程，但這次開啟 context compaction。tool runner 的迴圈只要改兩個地方：

- 傳入 **`betas=["compact-2026-09-04"]`**，runner 才能送 compaction 請求
- 每一輪結束後，拿 `message.usage.input_tokens` 跟 threshold 比，超過就呼叫 **`runner.compact_before_next_turn()`**。這個呼叫只是 *排程* compaction：runner 會先把目前這一輪的 tool 呼叫跑完，再去要摘要。它可以帶一個選用的設定 `{"type": "summarize", "instructions": "..."}`，用來取代 server 預設的摘要 prompt（見下面的 *自訂摘要指示*）

compaction 這一輪跟其他 message 一樣由 runner yield 出來，`stop_reason == "compaction"`，內容是單一個放著摘要的 `compaction` block。它的 token 用量記在 `usage.iterations` 底下，而不是最上層的計數器，下面的輔助函式已經處理了這點。

這個客服流程我們用 **5,000 token 的 threshold**，也就是處理幾張 ticket 之後就會觸發 compaction。這樣 Claude 可以：
1. **保留完成摘要**（已解決的 ticket、類別、結果）
2. **丟掉詳細的 tool 結果**（完整知識庫文章、完整分類內容、草擬的回覆全文）
3. 處理下一批 ticket 時 **重新開始**

這就像真人客服的做法：解決 ticket、簡短記錄、換下一件。

```python
# Re-initialize queue and run with compaction
initialize_ticket_queue(num_tickets)

COMPACTION_THRESHOLD = 5000  # input tokens; low on purpose for the demo


def turn_tokens(message) -> tuple[int, int]:
    """Input/output tokens for one runner turn.

    A compaction turn reports zero top-level tokens and lists the summarization
    call under usage.iterations, so sum those instead.
    """
    if message.stop_reason == "compaction" and message.usage.iterations:
        return (
            sum(it.input_tokens for it in message.usage.iterations),
            sum(it.output_tokens for it in message.usage.iterations),
        )
    return message.usage.input_tokens, message.usage.output_tokens


total_input_compact = 0
total_output_compact = 0
turn_count_compact = 0
compaction_count = 0

runner = client.beta.messages.tool_runner(
    model=MODEL,
    max_tokens=4096,
    tools=tools,
    messages=messages,
    betas=["compact-2026-09-04"],
)

for message in runner:
    turn_count_compact += 1
    input_tokens, output_tokens = turn_tokens(message)
    total_input_compact += input_tokens
    total_output_compact += output_tokens
    messages_list = list(runner._params["messages"])

    if message.stop_reason == "compaction":
        # Before its next request the runner replaces the whole history with this single block.
        compaction_count += 1
        summary = next(block.content for block in message.content if block.type == "compaction")
        print(f"\n{'=' * 60}")
        print(
            f"🔄 Compaction occurred! {len(messages_list)} messages condensed into one summary block"
        )
        print("   Summary after compaction:")
        print(summary)
        print(f"\n{'=' * 60}")
    elif message.stop_reason == "tool_use" and input_tokens > COMPACTION_THRESHOLD:
        # Schedule a compaction; it runs once this turn's tool calls are answered.
        # (Only on tool_use turns: the final end_turn answer needs no compaction.)
        runner.compact_before_next_turn()

    print(
        f"Turn {turn_count_compact:2d}: Input={input_tokens:7,} tokens | "
        f"Output={output_tokens:5,} tokens | "
        f"Messages={len(messages_list):2d} | "
        f"Cumulative In={total_input_compact:8,}"
    )

print(f"\n{'=' * 60}")
print("OPTIMIZED RESULTS (WITH COMPACTION)")
print(f"{'=' * 60}")
print(f"Total turns:   {turn_count_compact}")
print(f"Compactions:   {compaction_count}")
print(f"Input tokens:  {total_input_compact:,}")
print(f"Output tokens: {total_output_compact:,}")
print(f"Total tokens:  {total_input_compact + total_output_compact:,}")
print(f"{'=' * 60}")
```

??? note "輸出"

    ```text
    Turn  1: Input=  1,732 tokens | Output=   30 tokens | Messages= 1 | Cumulative In=   1,732
    ```

    ```text
    Turn  2: Input=  1,955 tokens | Output=  317 tokens | Messages= 3 | Cumulative In=   3,687
    ```

    ```text
    Turn  3: Input=  2,602 tokens | Output=  101 tokens | Messages= 5 | Cumulative In=   6,289
    ```

    ```text
    Turn  4: Input=  3,233 tokens | Output=  317 tokens | Messages= 7 | Cumulative In=   9,522
    ```

    ```text
    Turn  5: Input=  3,803 tokens | Output=   30 tokens | Messages= 9 | Cumulative In=  13,325
    ```

    ```text
    Turn  6: Input=  4,033 tokens | Output=  392 tokens | Messages=11 | Cumulative In=  17,358
    ```

    ```text
    Turn  7: Input=  5,026 tokens | Output=  321 tokens | Messages=13 | Cumulative In=  22,384
    ```

    ```text

    ============================================================
    🔄 Compaction occurred! 15 messages condensed into one summary block
       Summary after compaction:
    ## Progress summary

    **Task**: Process 5 support tickets one at a time. For each ticket: get_next_ticket → classify_ticket → search_knowledge_base → set_priority → route_to_team → draft_response → mark_complete. Keep going until the queue is empty (the 5 tickets are expected in total).

    **Completed so far (2 of 5):**
    - **TICKET-1** (John Williams, tracking number 1Z856942470332 reported invalid): classified shipping, priority medium, routed to logistics-team. The draft response made no unsupported claims and said the logistics team would verify the number. Marked complete.
    - **TICKET-2** (Alex Jones, order #ORD-66101: received Yellow Widget Lite instead of Green Device Max; the subject line said "change delivery address", which doesn't match the description): classified shipping, priority medium, routed to logistics-team. The draft apologized, said logistics would arrange the correct item and return instructions, and offered to pass on a new address if needed. Marked complete.

    **Notes on the tools:**
    - The KB only has the categories billing, technical, and account. "shipping" returns an error. For shipping tickets, I searched the nearest available category (billing for return/refund topics, technical for tracking). Neither had shipping-specific content, so the drafts avoided inventing policy details.
    - KB content seen: the billing refund policy (refunds take 5-7 business days for valid cancellations, pro-rated for annual plans), payment methods (Visa, Mastercard, Amex, PayPal; update them in Account Settings), and the billing cycle. Technical covers common errors, system requirements (4GB RAM, Chrome 90+/Firefox 88+/Safari 14+), and troubleshooting (clear cache, incognito, enable JavaScript).
    - Valid teams: billing-team, tech-support, account-services, product-success, logistics-team.
    - Independent calls (classify, search, priority, route) can be made in parallel. Draft and mark_complete come after them.

    **Next step**: Call get_next_ticket for TICKET-3, then repeat the full workflow for TICKET-3, 4, and 5. Stop when the queue returns an empty error. Then give a brief final summary of all processed tickets.

    ============================================================
    Turn  8: Input=  5,661 tokens | Output=  758 tokens | Messages=15 | Cumulative In=  28,045
    ```

    ```text
    Turn  9: Input=  2,087 tokens | Output=   30 tokens | Messages= 1 | Cumulative In=  30,132
    ```

    ```text
    Turn 10: Input=  2,303 tokens | Output=  355 tokens | Messages= 3 | Cumulative In=  32,435
    ```

    ```text
    Turn 11: Input=  3,145 tokens | Output=  355 tokens | Messages= 5 | Cumulative In=  35,580
    ```

    ```text
    Turn 12: Input=  3,751 tokens | Output=   30 tokens | Messages= 7 | Cumulative In=  39,331
    ```

    ```text
    Turn 13: Input=  3,982 tokens | Output=  314 tokens | Messages= 9 | Cumulative In=  43,313
    ```

    ```text
    Turn 14: Input=  4,890 tokens | Output=  426 tokens | Messages=11 | Cumulative In=  48,203
    ```

    ```text
    Turn 15: Input=  5,569 tokens | Output=   30 tokens | Messages=13 | Cumulative In=  53,772
    ```

    ```text

    ============================================================
    🔄 Compaction occurred! 15 messages condensed into one summary block
       Summary after compaction:
    ## Progress summary

    **Task**: Process 5 support tickets one at a time. For each ticket: get_next_ticket → classify_ticket → search_knowledge_base → set_priority → route_to_team → draft_response → mark_complete. Keep going until the queue is empty (the 5 tickets are expected in total).

    **Completed so far (4 of 5):**
    - **TICKET-1** (John Williams, tracking number reported invalid): shipping, medium, logistics-team. Draft made no unsupported claims. Marked complete.
    - **TICKET-2** (Alex Jones, wrong item received on order #ORD-66101; the subject line didn't match the description): shipping, medium, logistics-team. Marked complete.
    - **TICKET-3** (Alex Jones, password reset emails not arriving): account, medium, account-services. The draft cited the KB (emails come from noreply@support.example.com, the link expires in 1 hour). It flagged that the ticket email (customer8695@) differs from the email in the description (customer6750@) and asked the customer to confirm which is registered. Marked complete.
    - **TICKET-4** (John Smith, unrecognized $49.99 charge on 2026-10-20): billing, high, billing-team. The draft explained the billing cycle, did not claim to know what the charge was, mentioned refund policy conditionally, and asked for the last four digits only. Marked complete.

    **Currently in progress: TICKET-5** (just fetched, no actions taken yet):
    - Jane Brown, customer4919@example.com, subject "Account locked after failed login". She says the account was locked after too many wrong password attempts. She now remembers her password, but the unlock email link isn't working. Pre-set category: account. Created 2026-10-19.
    - Plan: classify as account, search the account KB (e.g. "account locked unlock"), set priority (medium, or high since she is locked out), route to account-services. Then draft a response that doesn't invent unlock policy beyond what the KB returns, and mark complete. The KB has password_reset (emails from noreply@support.example.com, check spam, link expires in 1 hour), 2fa_backup, and email_change, so there may be no lockout-specific entry. If so, say the Account Services team will verify her identity and help unlock the account, and suggest requesting a new link since the old one may have expired.

    **Notes on the tools:**
    - The KB only has the categories billing, technical, and account. "shipping" returns an error.
    - Valid teams: billing-team, tech-support, account-services, product-success, logistics-team.
    - Independent calls (classify, search, priority, route) can be made in parallel. Draft and mark_complete come after them (these two can also go in parallel).

    **Next steps**: Finish TICKET-5 with the full workflow. Then call get_next_ticket once more to confirm the queue is empty. Then give a brief final summary of all 5 processed tickets, noting the oddities flagged: the TICKET-2 subject/description mismatch, the TICKET-3 email mismatch, and the absence of a shipping KB category.

    ============================================================
    Turn 16: Input=  5,840 tokens | Output=1,027 tokens | Messages=15 | Cumulative In=  59,612
    ```

    ```text
    Turn 17: Input=  2,356 tokens | Output=  309 tokens | Messages= 1 | Cumulative In=  61,968
    ```

    ```text
    Turn 18: Input=  3,217 tokens | Output=  386 tokens | Messages= 3 | Cumulative In=  65,185
    ```

    ```text
    Turn 19: Input=  3,910 tokens | Output=  460 tokens | Messages= 5 | Cumulative In=  69,095

    ============================================================
    OPTIMIZED RESULTS (WITH COMPACTION)
    ============================================================
    Total turns:   19
    Compactions:   2
    Input tokens:  69,095
    Output tokens: 5,988
    Total tokens:  75,083
    ============================================================
    ```

開了 context compaction 後，每一輪的 token 用量不再線性成長：每次 compaction 之後會掉下來，接下來的輪次從摘要開始，而不是從完整歷史開始。

跟基準比起來，這次用掉的 input token 少很多（總數見下面的比較表）。我們也把每次 compaction 回傳的摘要印出來，可以看到之前的 ticket 細節是怎麼被濃縮的。

來看看開了 compaction 處理完 5 張 ticket 後的最終回應。

```python
print("".join(block.text for block in message.content if block.type == "text"))
```

??? note "輸出"

    ```text
    All 5 tickets are processed and the queue is empty.

    | Ticket | Customer | Issue | Category | Priority | Team |
    |---|---|---|---|---|---|
    | TICKET-1 | John Williams | Tracking number reported invalid | shipping | medium | logistics-team |
    | TICKET-2 | Alex Jones | Wrong item received on order #ORD-66101 | shipping | medium | logistics-team |
    | TICKET-3 | Alex Jones | Password reset emails not arriving | account | medium | account-services |
    | TICKET-4 | John Smith | Unrecognized $49.99 charge | billing | high | billing-team |
    | TICKET-5 | Jane Brown | Account locked, unlock link not working | account | high | account-services |

    Each ticket has a draft response and is marked complete.

    Three things to check:
    - **TICKET-2:** The subject line doesn't match the description. I went by the description.
    - **TICKET-3:** The email on the ticket (customer8695@) differs from the one in the description (customer6750@). The draft asks the customer to confirm which one is registered.
    - **Knowledge base gaps:** The knowledge base has no shipping category, so the shipping drafts make no policy claims. It also has no entry on account lockouts. The TICKET-5 draft only cites the password-reset link expiry and hands the unlock to Account Services.
    ```

### 比較結果

開了 compaction 後，兩次執行的 token 節省量差異很明顯，而且流程品質和最終摘要都保住了。

自動 context compaction 帶來的變化：

1. **幾張 ticket 之後 context 重置**：當幾張 ticket 的 tool 結果讓某一輪的 input 超過 5k，迴圈就呼叫 `compact_before_next_turn()`，然後 runner：
   - 先跑完目前這一輪的 tool 呼叫，再送出 compaction 請求
   - 收到 server 產生的摘要，放在 `compaction` block 裡
   - 把對話歷史（詳細的分類、知識庫搜尋、回覆）換成這個 block
   - 只帶著摘要繼續

2. **input token 維持在一定範圍**：不會隨著處理的 ticket 變多累積到 100k 以上，每次 compaction 後 input token 都會重置。處理 Ticket #5 時，我們不會背著 Ticket #1-4 的完整 tool 結果。

3. **任務順利完成**：流程一路順暢跑完所有 ticket，沒有撞到 context 上限

4. **品質保住了**：摘要保留了關鍵資訊：
   - 處理過的 ticket ID
   - 指定的類別和優先級
   - 轉派的團隊
   - 整體進度
   
   所有 ticket 仍然都有被正確分類、排優先級、轉派和回覆。

5. **流程很自然**：這跟真人客服的做法一樣：解決 ticket、在系統裡簡短記一筆、結案、換下一件。處理新 ticket 時，你不會把每篇知識庫文章和完整回覆草稿都開著。

來把節省的 token 視覺化：

```python
# Compare baseline vs compaction
print("=" * 70)
print("TOKEN USAGE COMPARISON")
print("=" * 70)
print(f"{'Metric':<30} {'Baseline':<20} {'With Compaction':<20}")
print("-" * 70)
print(f"{'Input tokens:':<30} {total_input:>19,} {total_input_compact:>19,}")
print(f"{'Output tokens:':<30} {total_output:>19,} {total_output_compact:>19,}")
print(
    f"{'Total tokens:':<30} {total_input + total_output:>19,} {total_input_compact + total_output_compact:>19,}"
)
print(f"{'Compactions:':<30} {'N/A':>19} {compaction_count:>19}")
print("=" * 70)

# Calculate savings
token_savings = (total_input + total_output) - (total_input_compact + total_output_compact)
savings_percent = (
    (token_savings / (total_input + total_output)) * 100 if (total_input + total_output) > 0 else 0
)

print(f"\n💰 Token Savings: {token_savings:,} tokens ({savings_percent:.1f}% reduction)")
```

??? note "輸出"

    ```text
    ======================================================================
    TOKEN USAGE COMPARISON
    ======================================================================
    Metric                         Baseline             With Compaction     
    ----------------------------------------------------------------------
    Input tokens:                              109,269              69,095
    Output tokens:                               4,238               5,988
    Total tokens:                              113,507              75,083
    Compactions:                                   N/A                   2
    ======================================================================

    💰 Token Savings: 38,424 tokens (33.9% reduction)
    ```

## compaction 底層怎麼運作

呼叫 `runner.compact_before_next_turn()` 時，tool runner 會：
1. **讓目前這一輪跑完**：先執行還沒做的 tool 呼叫並附上結果，因為 API 沒辦法壓縮一段以未回應的 tool 呼叫結尾的對話
2. **送出 compaction 請求**：同樣的模型、system prompt、tools 和 messages，再加上 `compaction={"type": "summarize"}`。摘要之後不會再取樣，所以這個請求只回傳摘要
3. **收到 `compaction` block**：API 在 server 端把對話做成摘要（已完成的 ticket、進度、接下來要做什麼），以單一個 content block 回傳，`stop_reason == "compaction"`
4. **取代歷史**：runner 把整個 message 列表（包含所有 tool 結果）換成那一個 block，而且它必須放在最前面、不能被修改
5. **繼續處理**：下一個請求從壓縮後的 context 接著跑，Claude 去處理下一張 ticket

## 自訂 compaction 設定

可以依你的使用情境調整 compaction 的行為。主要的設定有：

### 調整 threshold

用 runner 驅動的 compaction，threshold 就是你自己的迴圈邏輯，所以可以是任何數值或任何條件（例如「每三次 `mark_complete` 呼叫之後」）：

```python
COMPACTION_THRESHOLD = 5000  # Compact after processing a few tickets

for message in runner:
    if message.stop_reason == "tool_use" and message.usage.input_tokens > COMPACTION_THRESHOLD:
        runner.compact_before_next_turn()
```

threshold 不要設太低，否則摘要本身就可能再觸發一次 compaction。我們為了示範設 5,000 token，實務上要多試幾種設定，找出適合你流程的值。

一般的參考原則：

- **低 threshold（5k-20k）**：
  - 用在邊界清楚的迭代式任務處理
  - compaction 比較頻繁，累積的 context 很少
  - 最適合依序處理一個個項目
  
- **中 threshold（50k-100k）**：
  - 多階段流程，天然的檢查點比較少、比較大
  - 在保留 context 和管理 context 之間取平衡
  - 適合 tool 呼叫很貴的流程
  
- **高 threshold（100k-150k）**：
  - 需要大量歷史 context 的任務
  - compaction 比較少，保留較多原始細節
  - 每次呼叫成本較高，但壓縮次數少

如果你只要一個 50k 以上的固定 token trigger，完全不需要迴圈邏輯：傳一個 `context_management` 的 compaction edit，API 就會自動壓縮（見 [compaction 文件](https://platform.claude.com/docs/en/build-with-claude/compaction)）。runner 不允許這個 edit 跟 `compact_before_next_turn()` 同時用，所以每個 runner 擇一。

**處理 ticket 的情況**：5k threshold 很合適，因為每張 ticket 的流程會產生大量 tool 結果，但 ticket 之間互相獨立。解決 Ticket A 後，處理 Ticket B 時就不需要它詳細的知識庫搜尋。

### 自訂摘要指示

你可以傳 `instructions` 取代 server 預設的摘要 prompt。客服流程需要保留特定類型的資訊，這個功能特別有用。

例如，可以依我們的需求定義一個自訂 prompt：
- 所有已完成 ticket 的 **ticket 摘要**
- 指定的 **類別和優先級**
- **轉派的團隊**
- **進度狀態**（已完成幾張、剩幾張）
- 流程的 **下一步**

```python
runner.compact_before_next_turn(
    {
        "type": "summarize",
        "instructions": """You are processing customer support tickets from a queue.

Create a focused summary that preserves:

1. **COMPLETED TICKETS**: For each ticket you've fully processed:
   - Ticket ID and customer name
   - Issue category and priority assigned
   - Team routed to
   - Brief outcome

2. **PROGRESS STATUS**: 
   - How many tickets you've completed
   - Approximately how many remain in the queue

3. **NEXT STEPS**: Continue processing the next ticket

Format with clear sections.""",
    }
)
```

## 沒有 tool 的情況：簡單的聊天迴圈

上面的例子聚焦在 tool 密集的 agentic 流程，但 context compaction 對 **由使用者主導的簡單對話應用** 也很有用。

**注意：** `compact_before_next_turn()` 是 tool runner 的方法。在單純的聊天迴圈裡，你可以自己在 `client.beta.messages.create()` 呼叫上送 `compaction={"type": "summarize"}`，再把回傳的 block 放到 `messages` 最前面；或是像下面這樣手動實作摘要，這種做法適用任何模型，摘要 prompt 也完全由你掌控。

想像一個聊天應用，使用者跟 Claude 進行很長的對話：討論複雜的主題、反覆調整想法、或一步步解決問題。對話變長之後，你會碰到一樣的 context 累積問題。

**差別**：token 成長的來源不是 tool 使用，而是來回的對話本身。每一次交流都讓歷史變長：
- 使用者提問
- Claude 給詳細回答
- 使用者要求釐清或展開
- Claude 補充更多脈絡
- 這樣重複幾十次甚至幾百次

沒有 compaction 的話，到第 50 輪時，每次 API 呼叫都要送出整段對話歷史（全部 50 次交流）。

**解法**：用同樣的模式在聊天迴圈裡手動實作 compaction：
1. 每一輪結束後追蹤 token 用量
2. 超過 threshold 就要求一份摘要
3. 用摘要取代對話歷史
4. 用壓縮後的 context 繼續對話

來看怎麼實作：

```python
#!/usr/bin/env python3
"""
Simple Compaction Example - User-Driven Chat Loop

This shows the basic pattern for a chat application with compaction.
No tools required - just a simple loop where the user drives continuation.
"""

# Configuration
COMPACTION_THRESHOLD = 3000  # Compact when tokens exceed this (low for demo purposes)

# Structured summarization prompt for compaction
SUMMARY_PROMPT = """You have been working on the task described above but have not yet completed it. Write a continuation summary that will allow you (or another instance of yourself) to resume work efficiently in a future context window where the conversation history will be replaced with this summary. Your summary should be structured, concise, and actionable. Include:

1. **Task Overview**
   - The user's core request and success criteria
   - Any clarifications or constraints they specified

2. **Current State**
   - What has been completed so far
   - Files created, modified, or analyzed (with paths if relevant)
   - Key outputs or artifacts produced

3. **Important Discoveries**
   - Technical constraints or requirements uncovered
   - Decisions made and their rationale
   - Errors encountered and how they were resolved
   - What approaches were tried that didn't work (and why)

4. **Next Steps**
   - Specific actions needed to complete the task
   - Any blockers or open questions to resolve
   - Priority order if multiple steps remain

5. **Context to Preserve**
   - User preferences or style requirements
   - Domain-specific details that aren't obvious
   - Any promises made to the user

Be concise but complete—err on the side of including information that would prevent duplicate work or repeated mistakes.
 Write in a way that enables immediate resumption of the task.

Wrap your summary in <summary></summary> tags."""

# Message history
messages = []

print("Chat with Claude (type 'quit' to exit, or just hit Enter to continue)")
print("This is a demonstration - try having a conversation and watch compaction trigger")
print("=" * 60)

# Simulate a conversation for demo purposes
demo_messages = [
    "Help me understand how Python decorators work",
    "Can you show me an example with a timing decorator?",
    "How would I make a decorator that takes arguments?",
]

for user_input in demo_messages:
    print(f"\nYou: {user_input}")

    # Add user message
    messages.append({"role": "user", "content": user_input})

    # Get Claude's response
    response = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=messages,
    )

    messages.append(
        {
            "role": "assistant",
            "content": response.content,
        }
    )

    print("\nClaude: ", end="")
    for block in response.content:
        if block.type == "text":
            print(f"{block.text[:300]} ...")

    # Check if we should compact
    usage = response.usage

    # Calculate total tokens (includes cache tokens)
    total_input_tokens = (
        usage.input_tokens
        + (usage.cache_creation_input_tokens or 0)
        + (usage.cache_read_input_tokens or 0)
    )
    total_tokens = total_input_tokens + usage.output_tokens

    cache_info = ""
    if usage.cache_creation_input_tokens or usage.cache_read_input_tokens:
        cache_info = f" (cache: {usage.cache_creation_input_tokens or 0} write + {usage.cache_read_input_tokens or 0} read)"

    print(
        f"\n[Tokens: {total_input_tokens} in{cache_info} + {usage.output_tokens} out = {total_tokens} total]"
    )

    if total_tokens > COMPACTION_THRESHOLD:
        print(f"\n{'=' * 60}")
        print(f"🔄 Compacting conversation... {len(messages)} messages → ", end="", flush=True)

        # Get summary using structured prompt
        summary_response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            messages=messages + [{"role": "user", "content": SUMMARY_PROMPT}],
        )

        summary_text = "".join(
            block.text for block in summary_response.content if block.type == "text"
        )

        # Replace history with summary
        messages = [{"role": "user", "content": summary_text}]

        print("1 message")
        print(f"{'=' * 60}\n")

print(f"Final conversation messages: {messages[-1].get('content')}")

print("\nDemo complete! In a real application, this loop would continue with user input.")
```

??? note "輸出"

    ```text
    Chat with Claude (type 'quit' to exit, or just hit Enter to continue)
    This is a demonstration - try having a conversation and watch compaction trigger
    ============================================================

    You: Help me understand how Python decorators work
    ```

    ```text

    Claude: # Python Decorators

    A decorator is a function that takes another function and returns a modified or enhanced version of it, without you changing the original function's code.

    ## 1. The building blocks

    Decorators rely on two Python features.

    **Functions are objects.** You can assign them to varia ...

    [Tokens: 20 in + 1497 out = 1517 total]

    You: Can you show me an example with a timing decorator?
    ```

    ````text

    Claude: # Timing Decorator: Full Example

    ## Basic version

    ```python
    import time
    import functools

    def timer(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            result = func(*args, **kwargs)
            elapsed = time.perf_counter() - start
            p ...

    [Tokens: 1536 in + 1437 out = 2973 total]

    You: How would I make a decorator that takes arguments?
    ````

    ````text

    Claude: # Decorators That Take Arguments

    ## The core idea

    A normal decorator is a function that takes a function. To pass arguments, add one more layer: a function that takes the arguments and **returns** a decorator.

    ```
    decorator_factory(args)  →  decorator(func)  →  wrapper(*args, **kwargs)
    ```

    ## Th ...

    [Tokens: 2992 in + 1641 out = 4633 total]

    ============================================================
    🔄 Compacting conversation... 6 messages →
    ````

    ```text
    1 message
    ============================================================

    Final conversation messages: <summary>
    ## Continuation Summary

    ### 1. Task Overview
    The user is learning Python decorators through a conversational Q&A. There is no fixed deliverable or file output. The goal is clear, accurate, example-driven explanations. No explicit constraints were given beyond the questions asked. The task is not "unfinished" in a strict sense; the conversation is open-ended and the user may ask further follow-ups.

    ### 2. Current State
    Three user questions have been answered, all in chat (no files created or modified):

    1. **"Help me understand how Python decorators work"** – Covered: functions as first-class objects, nested/returned functions, manual decoration (`greet = shout(greet)`), `@` syntax as sugar, `*args/**kwargs` wrappers, `functools.wraps`, decorators with arguments (brief), a timing example, stacking order (`@a @b def f` = `a(b(f))`), a table of common built-in decorators (`staticmethod`, `classmethod`, `property`, `lru_cache`, `dataclass`), and a mental model. Ended by offering to go deeper on class-based decorators, decorating classes, and closures.
    2. **"Can you show me an example with a timing decorator?"** – Provided: a basic `timer` using `time.perf_counter()`, usage with args/return values, a `try/finally` version so timing prints even on exceptions, a configurable version `timer(label=None, log=False)` (requires parentheses), an `async_timer` for coroutines, a step-by-step call flow, and a note pointing to `timeit` for serious benchmarking.
    3. **"How would I make a decorator that takes arguments?"** – Provided: the three-layer pattern (factory → decorator → wrapper), the desugaring `@repeat(3)` = `repeat(3)(func)`, closures as the reason inner layers see outer args, a `require_role` access-control example, an optional-parentheses pattern (`func=None, *, times=2`), common mistakes (missing parentheses, missing returns, omitting `wraps`), and a class-based alternative (`__init__` stores args, `__call__` takes the function).

    ### 3. Important Discoveries / Decisions
    - Consistent teaching approach: build from first principles, show the desugared equivalent, then give practical examples.
    - Always include `@functools.wraps(func)` in examples, and explain why.
    - Use `time.perf_counter()` over `time.time()` for timing.
    - Use `try/finally` in timing decorators so exceptions don't skip the measurement.
    - Async functions need an `async def wrapper` with `await`; a sync wrapper would only time coroutine creation.
    - No errors or failed approaches have occurred.

    ### 4. Next Steps
    - No required actions remain. Await the user's next question.
    - Likely follow-ups, already offered or naturally adjacent: class-based decorators (a class with `__call__` that wraps a function, and keeping state such as call counters), decorating classes, closures in depth, `lru_cache`/memoization, decorators on methods (handling `self`), stacking order subtleties, a retry/caching/validation decorator example, type hints for decorators (`ParamSpec`, `TypeVar`), and testing decorated functions (`__wrapped__`).

    ### 5. Context to Preserve
    - Style: Markdown with headers, short code blocks with printed output shown in comments or output blocks, brief explanatory prose, and a concise summary or mental model at the end. Code is runnable and minimal.
    - The user appears to be a learner, so build up concepts incrementally and avoid unexplained jargon.
    - Promises made: offered to go deeper on class-based decorators, decorating classes, and how closures work, if the user wants.
    </summary>

    Demo complete! In a real application, this loop would continue with user input.
    ```

### 了解聊天迴圈的模式

上面的例子示範了在對話情境下的手動 compaction。運作方式如下：

**主要元件**：

1. **追蹤 token**：每次回應後，計算總 token（input + output + cache token）
2. **檢查 threshold**：總數超過 threshold 就觸發 compaction
3. **要求摘要**：把同一份結構化的 SUMMARY_PROMPT 送給 Claude
4. **取代歷史**：整段 message 歷史換成只有摘要
5. **繼續**：下一則使用者訊息接在摘要後面，而不是完整歷史

**適合用這個模式的情況**：

- **長時間的腦力激盪**：使用者跟 Claude 花很多輪探索想法
- **學習對話**：教學或解說橫跨幾十次交流
- **反覆修改**：使用者針對草稿、設計或解法持續給回饋
- **聊天應用**：任何多輪對話的介面

**跟 tool runner 的差異**：

| 面向 | Tool Runner（`compact_before_next_turn`） | 聊天迴圈（手動） |
|--------|------------------------|-------------------|
| **觸發** | 你的 threshold 檢查排程，runner 挑時機 | 你自己實作 threshold 檢查 |
| **摘要** | server 端產生，以 `compaction` block 回傳 | 你自己發 API 呼叫，用自己的 prompt |
| **歷史管理** | runner 取代 messages | 你手動取代列表 |
| **使用情境** | 有 tool 的 agentic 流程 | 使用者主導的對話 |

**上線時要考慮**：

1. **調整 threshold**：實際應用用比較大的值
2. **自訂摘要 prompt**：配合你的對話類型調整（腦力激盪、技術支援、教學各不同）
3. **給使用者提示**：顯示像「正在摘要對話...」的訊息，讓使用者知道為什麼停了一下
4. **保留關鍵 context**：確保摘要 prompt 抓得到你的使用者在意的領域資訊

這個模式讓你完全掌控 compaction 的時機和方式，很適合不使用 tool runner 的對話應用。

## 限制與注意事項

自動 context compaction 很強，但有幾個重要限制要知道：

### 衡量 threshold

**注意你算的是什麼**：這份 cookbook 以 `usage.input_tokens` 當觸發條件。開了 prompt caching 的話，大部分歷史會出現在 `cache_read_input_tokens`，而 server-side tool 迴圈（web search、code execution）每一輪會回報多個 `usage.iterations`。要把真正反映歷史大小的計數器加起來，否則觸發會太晚或太早。

**時機**：排程的 compaction 只會在目前這一輪的 tool 呼叫都回應完之後才執行；如果執行結束時最後一輪還有未回應的 tool 呼叫，就會跳過（並給警告）。

### 資訊遺失

**取捨**：摘要一定會丟掉一些資訊。Claude 很會抓重點，但有些細節還是會被壓縮或省略。

**以處理 ticket 為例**：
- ✅ **保留**：ticket ID、類別、優先級、團隊、結果、進度狀態
- ❌ **遺失**：知識庫文章全文、草擬回覆全文、詳細的分類推理

這通常可以接受，你不需要永遠留著每篇知識庫文章和完整回覆，只要完成紀錄就好。

**緩解方式**：
- 用自訂摘要 prompt 保留關鍵資訊
- 需要大量歷史 context 的任務，把 threshold 設高一點
- 把任務設計成模組化（每個階段建立在摘要上，而不是原始細節上）

### 什麼時候不要用 compaction

以下情況避免使用：

1. **短任務**：任務在 50k-100k token 內就完成的話，compaction 只是多餘的負擔
2. **需要完整稽核紀錄的任務**：有些任務需要存取之前的所有細節
3. **高度迭代的精修**：每一步都嚴重依賴前面所有步驟的精確細節

### 什麼時候該用 compaction

compaction 很適合：

1. **依序處理**：像我們的 ticket 流程，一個接一個處理多個項目
2. **多階段流程**：每個階段結束前可以先摘要進度再往下走
3. **迭代式資料處理**：分批處理大型資料集，或一次處理一個實體
4. **長時間分析**：跨很多實體分析資料
5. **批次作業**：處理上百個互相獨立的項目

**處理 ticket 是最典型的使用情境**，因為：
- 每張 ticket 的流程大致獨立
- 你需要的是完成摘要，不是完整的 tool 結果
- 有天然的壓縮時機（處理完幾張之後）
- 流程是迭代且循序的

## 總結

自動 context compaction 讓長時間執行的 agentic 流程可以超出一般的 context 上限。這份 cookbook 透過客服 ticket 處理流程，探討了 compaction 的用法。

### 下一步

試著在你自己的流程裡實作 compaction：
1. 找出天然的壓縮時機（每處理完一個項目、每完成一個階段等）
2. 如果每個項目邊界清楚，從積極一點的 threshold 開始（5k-10k）
3. 用自訂摘要 prompt 保留關鍵資訊
4. 監控 compaction 什麼時候觸發，確認品質沒掉
5. 依你的實際需求調整 threshold

更多 context 管理的內容，見 [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)。

## 重點整理

- 有 tool 的 agent 迴圈每一輪都會把整段歷史重送一次，token 用量線性成長，成本和延遲跟著漲。
- compaction 的核心是把舊歷史換成一份摘要，只保留進度和結果，丟掉可重新取得的細節。
- runner 驅動的做法由你的程式決定時機，`compact_before_next_turn()` 只是排程，runner 會等當前這輪 tool 呼叫回完才壓縮。
- 項目互相獨立的流程（像逐張處理 ticket）最適合 compaction；需要完整稽核紀錄或每步都依賴前面細節的任務不適合。
- 如果只要固定的 50k 以上 trigger，用 server-side compaction 就好，不用自己寫迴圈。

## 練習

1. 把 threshold 從 5,000 改成 10,000 或 20,000 再跑一次，看 compaction 觸發的次數和總 input token 怎麼變。
2. 改掉 compaction 設定裡的 `instructions`，要求摘要額外記下每張 ticket 的回覆語氣（正式或親切），再看摘要有沒有照做。
3. 把觸發條件從 token 數改成「每完成 2 次 `mark_complete` 就 compact」，比較跟 token threshold 的差別。
