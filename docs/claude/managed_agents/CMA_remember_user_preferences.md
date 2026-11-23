---
translated: true
source: managed_agents/CMA_remember_user_preferences.ipynb
---
# 打造記得使用者的 agent

> 原文：[managed_agents/CMA_remember_user_preferences.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_remember_user_preferences.ipynb)

替你的 Claude Managed Agents 加上 Memory store，讓它們在多次互動中學習並記住使用者的偏好。

## 這篇在做什麼

大多數 agent 每次對話都從零開始。這篇替一個零售品牌建一個購物助理：第一次來訪時學到顧客的偏好並存進專屬的 memory store，下一次來訪時不用重講就自動回想起來。

## 學完你會

- 建立 memory store，並透過 session 的 `resources` 掛到 agent 的環境裡
- 用兩個獨立的 session 示範記憶跨次來訪保留，並從自己的程式讀取、檢視 agent 寫下的記憶
- 用你已知的資料預先寫入 store，或掛上共用的唯讀 store，並用版本紀錄做稽核與修正

## 開跑前

需要有 Claude Managed Agents beta 權限的 Anthropic API key，放在 `ANTHROPIC_API_KEY`。

大多數 agent 每次對話都從頭開始。顧客告訴你的購物助理他們的尺寸、預算、以及避開哪些材質，下次回來時 agent 全忘了。他們得重複說一遍，體驗感覺很泛用，不夠個人化。

我們剛推出 Claude Managed Agents 的 Memory 來解決這件事。把它想成 agent 為每個顧客拿到的一本共用筆記本：Claude 在 session 中記下相關的事，同一個顧客下次回來時這些筆記還在。設定只要一個 API 呼叫。

在這份指南中，你會替一個零售品牌建一個範例購物助理。agent 會在顧客第一次來訪時學習偏好、存進該使用者專屬的 memory store，並在下一次來訪時自動回想，不用再被告知。

## 你要建的東西

- 一個存放某位顧客購物偏好的 **memory store**
- 一個設定成會檢查並更新該 store 的**購物 agent**
- **兩個獨立的 session**，示範記憶跨次來訪保留
- 從你自己的應用程式**檢視與預先寫入**記憶的模式

## 記憶怎麼運作

把 memory store 掛到 session 時，它會以目錄的形式出現在 agent 的環境裡，路徑是 `/mnt/memory/{store-name}`，Claude 用標準的檔案 tools 在那裡讀寫檔案。你的應用程式透過 REST API 對同樣的檔案有完整的讀寫權限，所以你可以用已知的事實預先寫入 store、稽核 agent 寫了什麼、或把全部匯出到你自己的系統。

> **Beta 功能。** Memory stores 是 Claude Managed Agents 公開 beta 的一部分。API 在正式發布前可能改變。Python SDK 對 `client.beta` 底下的每個方法會自動加上必要的 `anthropic-beta` header。

## 前置需求

- 有 Claude Managed Agents beta 權限的 Anthropic API key。設在 `ANTHROPIC_API_KEY` 環境變數。
- Python 3.11 或更新版本。
- Anthropic Python SDK。Memory store 的方法需要較新的版本：

```bash
uv add anthropic
# or: pip install -U anthropic
```

## 設定 client

```python
%%capture
%pip install -q "anthropic>=2.0.0"
```

```python
import os

from anthropic import Anthropic
from utilities import wait_for_idle_status

MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")

client = Anthropic()
```

### 對話輪次的 helper

Managed agent 的 session 是事件驅動的：你送一則 user message，再串流事件直到 session 進入 idle。為了讓這份指南其餘部分好讀，把這個迴圈包成一個 helper，印出 agent 的回覆和它動到 `/mnt/memory/` 底下的檔案。

```python
def run_turn(session_id: str, user_text: str) -> str:
    """Send one user message and stream the agent's response until it goes idle.

    Returns the agent's full text reply for callers who want it programmatically.
    """
    print(f"\n[user]  {user_text}")
    reply_parts: list[str] = []

    with client.beta.sessions.events.stream(session_id) as stream:
        client.beta.sessions.events.send(
            session_id,
            events=[
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": user_text}],
                }
            ],
        )
        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        reply_parts.append(block.text)
                        print(f"[agent] {block.text}")

            elif event.type == "agent.tool_use":
                # Surface reads and writes to the memory mount so you can see
                # the agent checking and updating its memory.
                inp = event.input or {}
                target = inp.get("file_path") or inp.get("command", "")
                if "/mnt/memory/" in str(target):
                    print(f"  [memory] {event.name}: {target}")

            elif event.type == "session.status_idle":
                # Break on any idle reason so an unexpected stop_reason
                # (such as requires_action) cannot hang the loop.
                break

            elif event.type == "session.status_terminated":
                break

    wait_for_idle_status(client, session_id)
    return "".join(reply_parts)
```

## 步驟 1：建立 memory store

memory store 是一個有名字的文字檔容器，範圍是你的 workspace。在正式部署裡，你通常會為每個終端使用者建一個 store，並在自己的資料庫維護使用者 ID 對 store ID 的對應。

你在這裡設的 `description` 會在 store 掛上時被放進 agent 的 system prompt，所以用它告訴 Claude 這個 store 是做什麼的。

```python
store = client.beta.memory_stores.create(
    name="Shopper Preferences",
    description=(
        "Personal shopping preferences for a single customer: "
        "sizes, style, budget, favorite brands, and materials to avoid."
    ),
)

print(store.id)  # memstore_01...
```

??? note "輸出"

    ```text
    memstore_01NKkumXZXY8mEhoRA3xhBvN
    ```

## 步驟 2：定義購物 agent

每個 managed agent session 都需要一個 **agent**（模型、system prompt 和 tools）和一個 **environment**（agent 運行的 container）。這些可以建一次，在許多顧客和 session 之間重複使用。

給 agent 內建的 `agent_toolset`，裡面有它用來讀寫記憶的檔案 tools。`agent_toolset_20260401` 這個型別字串是 toolset 的 API 識別碼，不是模型別名，所以新模型發布時不需要更新它。

```python
environment = client.beta.environments.create(
    name="shopping-demo",
    config={"type": "cloud", "networking": {"type": "limited"}},
)

agent = client.beta.agents.create(
    name="Personal Shopper",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-remember-user-preferences"},
    model=MODEL,
    system=(
        "You are a personal shopping assistant for a retail brand. "
        "Help the customer find products that match their taste and budget, "
        "and remember what you learn about them for future visits."
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

print(agent.id)  # agent_01...
```

??? note "輸出"

    ```text
    agent_011CaMbJoHMUyR5TjeFDtMG9
    ```

## 步驟 3：第一次來訪，agent 學習偏好

現在啟動一個 session，並透過 `resources` 陣列掛上 memory store。`instructions` 欄位是每次掛載的指引，告訴 Claude 在這個 session 裡怎麼使用這個 store。

因為這是顧客第一次來訪，store 是空的。注意輸出裡的 `[memory]` 行：agent 檢查 store、發現還沒有東西，然後寫一個新檔案記下它學到的。

```python
memory_resource = {
    "type": "memory_store",
    "memory_store_id": store.id,
    "access": "read_write",
    "instructions": (
        "This customer's personal preferences: sizes, style, budget, and "
        "materials to avoid. Check it at the start of every conversation "
        "and update it whenever you learn something new."
    ),
}

session_one = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
    resources=[memory_resource],
)

# The response tells you where the store is mounted inside the agent's environment.
for resource in session_one.resources:
    if resource.type == "memory_store":
        print(f"Mounted at {resource.mount_path}")
```

??? note "輸出"

    ```text
    Mounted at /mnt/memory/shopper-preferences
    ```

```python
run_turn(
    session_one.id,
    "Hi! I'm looking for a new jacket. A few things about me: I wear a size "
    "medium, I only buy vegan leather (no animal leather please), my budget "
    "is usually under $200, and I love earth tones. What would you suggest?",
)
```

??? note "輸出"

    ```text
    [user]  Hi! I'm looking for a new jacket. A few things about me: I wear a size medium, I only buy vegan leather (no animal leather please), my budget is usually under $200, and I love earth tones. What would you suggest?
    [agent] Let me check if I have any info about you on file, and save your preferences right away!
      [memory] bash: cat /mnt/memory/shopper-preferences 2>/dev/null || echo "No file found"
      [memory] write: /mnt/memory/shopper-preferences
      [memory] write: /mnt/memory/shopper-preferences/preferences.md
    [agent] I've saved your preferences for future visits! Now, here are some great **vegan leather jacket picks in earth tones under $200** that I'd suggest:

    ---

    ### 🌿 Top Picks for You

    #### 1. **Olive Moto Jacket** — ~$110–$150
    A classic biker silhouette in a deep **olive green** faux leather. Look for styles with zip-detail sleeves and a fitted waist. Great for casual or edgy looks.
    - *Why you'll love it:* Earthy tone, very on-trend, versatile for layering.

    #### 2. **Camel/Tan Oversized Blazer-Jacket** — ~$80–$160
    A structured vegan leather blazer in **camel or tan** gives a polished, sophisticated vibe. Works dressed up or down.
    - *Why you'll love it:* Classic earth tone, medium sizing runs well in this style, timeless investment.

    #### 3. **Rust/Cognac Bomber Jacket** — ~$90–$170
    A **rust or cognac-toned** vegan leather bomber is a bold earth-tone statement piece with a relaxed, comfortable fit.
    - *Why you'll love it:* Rich warm color, bomber silhouettes are flattering in medium, cozy feel.

    #### 4. **Terracotta Cropped Jacket** — ~$75–$140
    A cropped vegan leather jacket in **terracotta** pairs beautifully with high-waisted jeans or wide-leg trousers.
    - *Why you'll love it:* Trendy silhouette, stunning earthy hue, well within budget.

    ---

    ### 🛍️ Brands to Check Out
    Here are some brands known for quality vegan leather within your budget:
    - **ASOS** – Wide range of faux leather styles in various earth tones
    - **Free People** – Boho-leaning earth tone options
    - **H&M** – Affordable vegan leather jackets in seasonal colors
    - **Lulus** – Great selection of trendy vegan styles under $100
    - **Noize** – A dedicated vegan outerwear brand, often has earthy tones under $200

    ---

    Do any of these styles appeal to you? I can help narrow it down further — for example, do you prefer a **fitted or relaxed fit**, or a particular style like moto, bomber, or blazer? 😊
    ```

## 步驟 4：檢視 agent 存了什麼

agent 寫到掛載點的所有東西都是一般的 memory 文件，你的應用程式能透過 API 讀取、編輯或刪除。用 `view="full"` 列出 store 的內容，回應就會包含檔案內容。

你可以這樣做出產品裡的「我們對你的了解」頁面、把記憶同步到你自己的資料庫、或讓人類 reviewer 修正 agent 弄錯的地方。

```python
page = client.beta.memory_stores.memories.list(
    store.id,
    view="full",
)

for memory in page.data:
    if memory.type == "memory":
        print(f"=== {memory.path} ===")
        print(memory.content)
        print()
```

??? note "輸出"

    ```text
    === /preferences.md ===
    # Shopper Preferences

    ## Sizes
    - Tops/Jackets: Medium

    ## Style
    - Loves earth tones (browns, tans, olive, terracotta, camel, rust, etc.)
    - Interested in jackets

    ## Budget
    - Usually under $200

    ## Materials
    - VEGAN LEATHER ONLY — absolutely no animal leather
    - (No other material restrictions noted yet)

    ## Favorite Brands
    - None noted yet

    ## Other Notes
    - First visit; preferences collected 2026-04-23
    ```

你應該會看到一個檔案（通常像 `/preferences.md`），內含顧客提到的尺寸、預算、材質和顏色偏好，依主題整理。檔名和結構是 Claude 自己選的。

## 步驟 5：再次來訪，agent 自己回想

這是關鍵時刻。建立一個**全新的 session**，並掛上**同一個 memory store**。顧客不重複任何偏好，但 agent 會從記憶中讀取，並依此調整推薦。

```python
session_two = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
    resources=[memory_resource],  # same store, new session
)

run_turn(
    session_two.id,
    "Hey, I'm back! I need a bag for work. Any recommendations?",
)
```

??? note "輸出"

    ```text
    [user]  Hey, I'm back! I need a bag for work. Any recommendations?
    [agent] Welcome back! Let me check your preferences before making any recommendations!
      [memory] read: /mnt/memory/shopper-preferences
      [memory] bash: ls /mnt/memory/shopper-preferences/
      [memory] read: /mnt/memory/shopper-preferences/preferences.md
    [agent] Great news — I already have your preferences on file! Here's what I kept in mind for you:

    - 🎨 **Style:** Earth tones (browns, tans, olive, camel, etc.)
    - 💰 **Budget:** Under $200
    - 🌱 **Materials:** Vegan leather only — no animal leather

    With that in mind, here are some work bag recommendations that would suit you perfectly:

    ---

    ### 🛍️ Top Picks for a Work Bag

    1. **Structured Tote in Camel Vegan Leather** — A polished, professional look in a warm earth tone. Fits a laptop + daily essentials. Great desk-to-commute bag.

    2. **Olive Canvas & Vegan Leather Trim Laptop Bag** — A sleek crossbody/shoulder bag with a relaxed but put-together vibe. The canvas keeps it lightweight.

    3. **Tan Vegan Leather Satchel** — A classic work satchel with a top handle and shoulder strap. Timeless silhouette, stays under budget.

    4. **Terracotta Faux-Leather Tote** — A bold but grounded earth tone that adds personality to a work outfit without being over the top.

    ---

    Do any of these styles appeal to you? I can also ask a few quick questions to narrow it down further:

    - **Do you prefer a tote, backpack, crossbody, or briefcase-style?**
    - **Do you need to carry a laptop, and if so, what size?**
    - **Do you lean more structured/professional or relaxed/casual for work?**
    ```

注意輸出中，agent 在回答之前先讀了 `/mnt/memory/shopper-preferences/`，然後推薦純素皮革、大地色系、200 美元以下的包包，儘管這則訊息完全沒提到這些。偏好從第一個 session 帶了過來。

## 進階：正式環境的模式

### 用你現有的資料預先寫入 store

如果你已經從顧客的帳號資料或購買紀錄知道一些事，可以在第一個 session 之前先寫進 store，讓 agent 一開始就掌握資訊。在真實的應用裡，你會在建立任何 session 之前跑這個預先寫入的步驟；它出現在示範之後，只是為了讓上面「學習再回想」的主流程保持專注。

> **注意：** 請在 notebook 結尾的清理 cell 之前執行這個 cell，因為 `store` 會在那裡被刪除。

```python
# Optional: run before the cleanup cell.
seeded = client.beta.memory_stores.memories.create(
    store.id,
    path="/purchase-history.md",
    content=(
        "## Recent purchases\n"
        "- Canvas tote, olive, $89 (Jan 2026)\n"
        "- Wool beanie, rust, $34 (Dec 2025)\n"
    ),
)
print(f"Seeded {seeded.path}")
```

??? note "輸出"

    ```text
    Seeded /purchase-history.md
    ```

### 結合每個顧客專屬和共用的 stores

一個 session 最多可掛八個 memory store，各自有自己的存取等級。常見的模式是每個顧客一個可讀寫的 store，加上一個每個 session 都共用的、品牌通用知識的唯讀 store。

```python
catalog = client.beta.memory_stores.create(
    name="Product Catalog Notes",
    description="Current promotions, sizing guidance, and stock notes.",
)

session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
    resources=[
        {
            "type": "memory_store",
            "memory_store_id": store.id,
            "access": "read_write",
            "instructions": "This customer's personal preferences.",
        },
        {
            "type": "memory_store",
            "memory_store_id": catalog.id,
            "access": "read_only",
            "instructions": "Brand-wide product guidance. Consult before recommending items.",
        },
    ],
)

# Remember to clean up the catalog store when you are done:
# client.beta.memory_stores.delete(catalog.id)
```

### 稽核與修正

每次寫入 memory store 都會記錄成一個不可變的版本，並附上做出該寫入的 session。用 `client.beta.memory_stores.memory_versions.list(...)` 檢視歷史，用 `client.beta.memory_stores.memories.update(...)` 修正 agent 弄錯的檔案。完整的 API 請看 [Memory API reference](https://docs.anthropic.com/en/docs/managed-agents/memory)。

## 清理

刪除你在跟著這份指南操作時建立的資源。

```python
wait_for_idle_status(client, session_one.id)
wait_for_idle_status(client, session_two.id)

client.beta.sessions.archive(session_one.id)
client.beta.sessions.archive(session_two.id)
client.beta.memory_stores.delete(store.id)
client.beta.agents.archive(agent.id)
client.beta.environments.archive(environment.id)
```

## 總結

你建了一個會跨次來訪記住顧客的購物 agent，做法是：

1. 為顧客建立 memory store
2. 透過 `resources` 把它掛到每個 session
3. 讓 Claude 在學到新偏好時，讀寫 `/mnt/memory/` 底下的檔案
4. 透過 Memory API 從你自己的應用程式檢視那些檔案

接下來你可以把自己的使用者 ID 對應到 memory store ID、用現有的顧客資料預先寫入 stores，並在上面疊一層共用的唯讀 store 放品牌通用知識。

### 這個系列的其他 notebook

- [`CMA_iterate_fix_failing_tests.ipynb`](CMA_iterate_fix_failing_tests.md)：入門 notebook。透過修一個失敗測試套件的 do-observe-fix 迴圈，介紹 agents、environments、sessions、檔案掛載和串流事件迴圈。
- [`CMA_operate_in_production.ipynb`](CMA_operate_in_production.md)：正式環境設定的故事：以 vault 保存的 MCP 憑證、用 `session.status_idled` webhook 做 HITL 而不用長連線，以及資源生命週期的 CRUD 動詞。

### 了解更多

- [Claude Managed Agents overview](https://docs.anthropic.com/en/docs/managed-agents/overview)
- [Memory stores API reference](https://docs.anthropic.com/en/docs/managed-agents/memory)
- [Session resources](https://docs.anthropic.com/en/docs/managed-agents/memory#attach-a-memory-store-to-a-session)

## 重點整理

- memory store 掛到 session 後，就是 agent 環境裡 `/mnt/memory/{store-name}` 的一個目錄，Claude 用一般檔案 tools 讀寫，你的應用程式用 API 讀寫同樣的檔案。
- store 的 `description` 會被放進 system prompt，用來告訴 Claude 這個 store 的用途，掛載時的 `instructions` 則是這個 session 專用的使用指引。
- 記憶跨 session 保留，所以只要掛同一個 store，新 session 不用顧客重講就能回想偏好。
- 正式環境通常一個終端使用者一個 store，一個 session 最多掛八個，可以混搭可讀寫的個人 store 和唯讀的共用 store。
- 每次寫入都有不可變的版本紀錄，可以稽核，也能修正 agent 寫錯的內容。

## 練習

1. 在步驟 3 第一次來訪的對話裡，多講一個新的偏好（例如不喜歡某個品牌），再用步驟 4 的 `view="full"` 檢查 agent 有沒有把它寫進檔案。
2. 在步驟 5 的再次來訪裡，換一個問題，看 agent 回答前是否仍然先讀 `/mnt/memory/shopper-preferences/`，並確認推薦符合偏好。
3. 照「用你現有的資料預先寫入 store」的做法，在第一個 session 之前先寫入一筆已知偏好，再用 `memory_versions.list` 看每次寫入是哪個 session 做的。
