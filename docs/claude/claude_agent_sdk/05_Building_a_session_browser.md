---
translated: true
source: claude_agent_sdk/05_Building_a_session_browser.ipynb
---
# 打造 session browser

> 原文：[claude_agent_sdk/05_Building_a_session_browser.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/05_Building_a_session_browser.ipynb)

列出、讀取、重新命名、加 tag、fork 磁碟上的 Agent SDK session，不用自己寫 transcript parser 就能做出對話歷史側邊欄。

## 這篇在做什麼

把 agent 做成產品（桌面 app、IDE 外掛、內部聊天機器人）之後，使用者第一個會要的是側邊欄：看到上週二的對話、跳回去繼續、還能分支出新方向又不弄丟原本的。agent loop 只是產品的一半，另一半是 session 管理。

Claude Agent SDK 會把每段對話寫成磁碟上的 JSONL transcript，也提供一組函式把 transcript 讀回來整理，所以你不用自己寫檔案 parser，也不用手動掃 `~/.claude/projects/`。

## 學完你會

- 列出並渲染專案的歷史 session，含分頁，以及 branch、標題、最後修改時間這些 metadata
- 不啟動 agent 就把已存的 session 訊息讀回 UI，並能 rename、加 tag、過濾
- 在任意一點 fork session，並把 fork 當成活的 `query()` 繼續跑

## 開跑前

- Python 3.11 以上、Claude Code CLI（`npm install -g @anthropic-ai/claude-code`）、Anthropic API key
- 需要 `claude-agent-sdk` v0.1.51 以上

Claude Code Desktop 和 VS Code 外掛的 session 側邊欄就是這個做法。同樣的 primitive 可以套在任何你要疊在 Agent SDK 上的 UI。

## 前置需求

開始之前，確認你具備：

**需要的知識**

- Python 基礎，包括 `async`/`await`
- 對 Agent SDK 的 `query()` 函式有基本認識（簡介見 [Notebook 00](00_The_one_liner_research_agent.md)）

**需要的工具**

- Python 3.11 或更高
- Claude Code CLI（`npm install -g @anthropic-ai/claude-code`）
- Anthropic API key（[在這裡取得](https://console.anthropic.com)）

## 設定

安裝需要的相依套件。session 管理函式從 `claude-agent-sdk` v0.1.51 開始提供。

```python
%%capture
%pip install -U "claude-agent-sdk>=0.1.51" python-dotenv pandas
```

從 `.env` 載入 API key 並設定模型。這裡用 Haiku，因為示範的 session 很短，我們要便宜又快；真實產品你會挑適合自己 agent 的模型。

```python
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-5-5"

# All demo sessions live under this project directory. Using a dedicated
# cwd keeps the demo isolated from your real Claude Code sessions.
# Note: this path resolves relative to the kernel's working directory
# (claude_agent_sdk/ when launched per the README).
DEMO_DIR = str(Path("session_browser_demo").resolve())
os.makedirs(DEMO_DIR, exist_ok=True)
print(f"Demo project dir: {DEMO_DIR}")
```

??? note "輸出"

    ```text
    Demo project dir: /path/to/claude-cookbooks/claude_agent_sdk/session_browser_demo
    ```

# 第 1 部分：先建幾個 session 來管理

session 管理函式讀的是 `query()`（或 Claude Code CLI）已經寫好的 transcript。為了有東西可以瀏覽，我們先跑三段簡短對話，並記下它們的 session ID。

`cwd` 選項告訴 SDK 這段對話屬於哪個專案目錄。transcript 會存在 `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`，所以 `cwd` 相同的呼叫都會歸到同一個 bucket。之後 `list_sessions(directory=...)` 讀的就是這個 bucket。

我們停用 tool，並把每次執行限制在一輪，讓 token 用量降到最低。

```python
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query


async def run_one_turn(prompt: str) -> str:
    """Run a single-turn conversation and return its session_id."""
    opts = ClaudeAgentOptions(
        model=MODEL,
        cwd=DEMO_DIR,
        max_turns=1,
        allowed_tools=[],  # text-only, no tool loop
        setting_sources=[],  # self-contained: don't load user/project settings
        permission_mode="default",
    )
    session_id = None
    async for msg in query(prompt=prompt, options=opts):
        if isinstance(msg, ResultMessage):
            session_id = msg.session_id
            preview = (msg.result or "")[:80]
            print(f"[{session_id[:8]}] {preview}...")
    if session_id is None:
        raise RuntimeError("No ResultMessage received; check API key and SDK version.")
    return session_id
```

三個 prompt，三個 session。真實產品裡，這些會是使用者問 agent 的內容。

```python
prompts = [
    "Give me three name ideas for a CLI tool that manages git worktrees.",
    "Explain the difference between a mutex and a semaphore in one paragraph.",
    "Write a haiku about merge conflicts.",
]

demo_session_ids = []
for p in prompts:
    sid = await run_one_turn(p)
    demo_session_ids.append(sid)

print(f"\nCreated {len(demo_session_ids)} sessions.")
```

??? note "輸出"

    ```text
    [54b0d2d8] Here are three name ideas for a git worktree management CLI tool:

    1. **Roots** ...
    ```

    ```text
    [9bc70b72] A **mutex** (mutual exclusion lock) is a synchronization primitive that allows o...
    ```

    ```text
    [7146a49b] Merge conflicts arise
    Both versions now fight for truth
    Rebase fixes all...

    Created 3 sessions.
    ```

# 第 2 部分：列出並檢視 session

## 建立 session 清單

`list_sessions()` 掃描專案的 transcript 目錄，回傳每個 session 的 metadata，由新到舊排序。它讀檔案 stat 加上每個 transcript 的頭尾，所以即使目錄有上百個檔案也很快。不會啟動 subprocess，也不會呼叫 API。

每個 `SDKSessionInfo` 帶有渲染選單一列所需的資訊：顯示用摘要、最後修改時間、git branch、工作目錄，以及你設定過的自訂標題或 tag。

```python
from datetime import datetime

import pandas as pd

from claude_agent_sdk import SDKSessionInfo, list_sessions

sessions = list_sessions(directory=DEMO_DIR)

# Render as a table. In a real UI this would be your sidebar component.
rows = []
for s in sessions:
    rows.append(
        {
            "id": s.session_id[:8],
            "summary": (s.summary[:50] + "...") if len(s.summary) > 50 else s.summary,
            "modified": datetime.fromtimestamp(s.last_modified / 1000).strftime("%H:%M:%S"),
            "branch": s.git_branch or "-",
            "tag": s.tag or "-",
        }
    )

pd.DataFrame(rows)
```

??? note "輸出"

    ```text
             id                                            summary  modified  \
    0  7146a49b               Write a haiku about merge conflicts.  16:50:58   
    1  9bc70b72  Explain the difference between a mutex and a s...  16:50:54   
    2  54b0d2d8  Give me three name ideas for a CLI tool that m...  16:50:52   

      branch tag  
    0   main   -  
    1   main   -  
    2   main   -
    ```

歷史很長時，傳 `limit` 和 `offset` 來分頁。session 選單通常先載入第一頁，使用者捲動時再抓更多：

```python
page_2 = list_sessions(directory=DEMO_DIR, limit=20, offset=20)
```

如果你的 app 已經存了 session ID（例如在自己的資料庫裡跟使用者紀錄放在一起），只需要那一列，`get_session_info()` 比列出全部便宜。

```python
from claude_agent_sdk import get_session_info

info = get_session_info(demo_session_ids[0], directory=DEMO_DIR)

print(f"Session:      {info.session_id}")
print(f"Summary:      {info.summary}")
print(f"First prompt: {info.first_prompt}")
print(f"Created:      {datetime.fromtimestamp(info.created_at / 1000)}")
print(f"Size:         {info.file_size:,} bytes")
```

??? note "輸出"

    ```text
    Session:      54b0d2d8-2cdc-45f6-9888-8951545c93c2
    Summary:      Give me three name ideas for a CLI tool that manages git worktrees.
    First prompt: Give me three name ideas for a CLI tool that manages git worktrees.
    Created:      2026-10-21 16:50:47.943000
    Size:         166,035 bytes
    ```

## 讀取 session 的訊息

使用者在側邊欄點一個 session，你就把它的對話載入主畫面。`get_session_messages()` 從 transcript 重建訊息鏈，依序回傳 user 和 assistant 的輪次。跟列表函式一樣，它純粹是讀檔，agent 不需要在執行。

每個 `SessionMessage` 有 `type`（`"user"` 或 `"assistant"`）、`uuid`，以及一個 `message` dict，格式跟 Anthropic Messages API 一樣（`role`、`content`）。

```python
from claude_agent_sdk import get_session_messages

messages = get_session_messages(demo_session_ids[0], directory=DEMO_DIR)

for m in messages:
    role = m.type
    # content is a list of blocks; pull out the text ones
    text_parts = [
        b.get("text", "")
        for b in m.message.get("content", [])
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    text = " ".join(text_parts).strip()
    print(f"[{role:>9}] {text[:100]}")
```

??? note "輸出"

    ```text
    [     user] 
    [assistant] 
    [assistant] Here are three name ideas for a git worktree management CLI tool:

    1. **Roots** — Simple, memorable,
    ```

session 很長時，用 `limit` 和 `offset` 一次載入一個區段。聊天畫面可以在開啟時載入最後 50 則，使用者往上捲再抓更舊的頁。offset 依時間順序（最舊的在前）計算，所以第 0 頁是對話的開頭。

# 第 3 部分：用標題和 tag 整理

## 重新命名 session

自動產生的摘要拿來快速瀏覽沒問題，但使用者常想給 session 一個真正的名字。`rename_session()` 會在 transcript 附加一筆標題；下次讀取時 `list_sessions()` 會把它當成 `custom_title` 帶出來。

附加很便宜而且是 idempotent：rename 兩次就是新標題贏，不會重寫檔案。

```python
from claude_agent_sdk import rename_session

rename_session(demo_session_ids[0], "Worktree CLI naming brainstorm", directory=DEMO_DIR)
rename_session(demo_session_ids[2], "Haiku corner", directory=DEMO_DIR)

# Verify the titles stuck
for s in list_sessions(directory=DEMO_DIR):
    label = s.custom_title or "(auto)"
    print(f"{s.session_id[:8]}  custom_title={label!r}  summary={s.summary[:40]!r}")
```

??? note "輸出"

    ```text
    54b0d2d8  custom_title='Worktree CLI naming brainstorm'  summary='Worktree CLI naming brainstorm'
    7146a49b  custom_title='Haiku corner'  summary='Haiku corner'
    9bc70b72  custom_title='(auto)'  summary='Explain the difference between a mutex a'
    ```

## 加 tag 與過濾

Tag 是附在 session 上的單一字串。你的產品需要什麼分類都可以用，例如 `"archived"`、`"needs-review"`、`"favorite"`。傳 `None` 就清掉 tag。

常見的做法是 soft-delete：不刪 transcript 檔，而是標上 `"__hidden"`，在列表檢視時把它過濾掉。資料還能救回來。

```python
from claude_agent_sdk import tag_session

# Mark two sessions as favorites, hide the other
tag_session(demo_session_ids[0], "favorite", directory=DEMO_DIR)
tag_session(demo_session_ids[2], "favorite", directory=DEMO_DIR)
tag_session(demo_session_ids[1], "__hidden", directory=DEMO_DIR)


def visible_sessions(directory: str, tag_filter: str | None = None) -> list[SDKSessionInfo]:
    """List sessions, hiding soft-deletes and optionally filtering by tag."""
    results = []
    for s in list_sessions(directory=directory):
        if s.tag == "__hidden":
            continue
        if tag_filter is not None and s.tag != tag_filter:
            continue
        results.append(s)
    return results


favorites = visible_sessions(DEMO_DIR, tag_filter="favorite")
print(f"Visible favorites: {len(favorites)}")
for s in favorites:
    print(f"  {s.session_id[:8]}  [{s.tag}]  {s.custom_title or s.summary}")
```

??? note "輸出"

    ```text
    Visible favorites: 2
      54b0d2d8  [favorite]  Worktree CLI naming brainstorm
      7146a49b  [favorite]  Haiku corner
    ```

Tag 是單一值，不是 list。如果你需要多個維度（例如狀態加分類），就把它們編進一個字串，像 `"review:urgent"`，讀取時再解析，或是把更豐富的狀態存進你自己的資料庫，以 `session_id` 當 key。

# 第 4 部分：Fork 與 resume

## 從既有對話分支

Fork 會把 session 的 transcript 複製到新檔案，並重新對應訊息 ID。原本的不受影響。這是「試試不同做法」這類功能的基礎：使用者保留原本的對話串，同時拿到一個新的來實驗。

`fork_session()` 寫入新檔並回傳它的 ID。它不會執行 agent，所以 fork 會一直待在磁碟上，直到你用 `query()` resume 它。

```python
from claude_agent_sdk import fork_session

source = demo_session_ids[0]

fork = fork_session(
    source,
    directory=DEMO_DIR,
    title="Worktree CLI names (round 2)",
)

print(f"Source: {source}")
print(f"Fork:   {fork.session_id}")

# The fork starts with the same message history as the source
source_msgs = get_session_messages(source, directory=DEMO_DIR)
fork_msgs = get_session_messages(fork.session_id, directory=DEMO_DIR)
print(f"Source has {len(source_msgs)} messages, fork has {len(fork_msgs)}")
```

??? note "輸出"

    ```text
    Source: 54b0d2d8-2cdc-45f6-9888-8951545c93c2
    Fork:   21100fd5-9fad-4f9f-bd06-7c430084e1b3
    Source has 3 messages, fork has 3
    ```

想從特定時間點而不是完整歷史分支，傳 `up_to_message_id`。fork 會包含來源 transcript 到該訊息（含）為止。訊息 UUID 可以從 `get_session_messages()[i].uuid` 取得。

## 把 fork resume 成活的 query

fork 只是一個 transcript 檔。要把它變回進行中的對話，把它的 ID 交給 `ClaudeAgentOptions.resume`。agent 會載入 fork 出來的歷史並從那裡繼續。

```python
resume_opts = ClaudeAgentOptions(
    model=MODEL,
    cwd=DEMO_DIR,
    max_turns=1,
    allowed_tools=[],
    setting_sources=[],
    permission_mode="default",
    resume=fork.session_id,
)

async for msg in query(
    prompt="Those were okay. Give me three more names, but punnier.",
    options=resume_opts,
):
    if isinstance(msg, ResultMessage):
        print(f"[fork {fork.session_id[:8]} resumed]")
        print(msg.result)
```

??? note "輸出"

    ```text
    [fork 21100fd5 resumed]
    Here are three punnier names for a git worktree management CLI tool:

    1. **Root Beer** — A play on the beverage and managing multiple "roots" of worktrees. Catchy and memorable: `root-beer checkout`, `root-beer list`.

    2. **Rebase-ment** — A pun combining "rebase" (a git operation) with "basement" (a foundation/lower level). Perfect for a dev-audience that appreciates git puns: `rebase-ment add`, `rebase-ment clean`.

    3. **Leaf It** — A wordplay on "leave it" and "leaf" (tree part). Lighthearted and punny: `leaf-it create`, `leaf-it switch`. Bonus: the repo could have a leaf emoji in the docs.

    **My pick:** **Rebase-ment** — it's the cleverest for a developer audience, and it actually describes the tool's function (managing the base/foundation of your worktrees).
    ```

原本的 session 還在那裡，沒有變動。再列一次，你會看到來源和 fork 是兩列獨立的資料，歷史各自獨立。

```python
for s in list_sessions(directory=DEMO_DIR):
    marker = "(fork)" if s.session_id == fork.session_id else "      "
    print(f"{marker} {s.session_id[:8]}  {s.custom_title or s.summary[:50]}")
```

??? note "輸出"

    ```text
    (fork) 21100fd5  Worktree CLI names (round 2)
           54b0d2d8  Worktree CLI naming brainstorm
           9bc70b72  Explain the difference between a mutex and a semap
           7146a49b  Haiku corner
    ```

# 清理

`delete_session()` 會移除 transcript 檔。這是硬刪除，所以對使用者面對的 UI 來說，第 3 部分的 soft-delete tag 做法通常是比較安全的預設。

這裡我們用它清掉示範建出來的所有東西。

```python
from claude_agent_sdk import delete_session

# Clean up every session in the demo dir, including the fork
for s in list_sessions(directory=DEMO_DIR):
    delete_session(s.session_id, directory=DEMO_DIR)
    print(f"Deleted {s.session_id[:8]}")

remaining = list_sessions(directory=DEMO_DIR)
print(f"\n{len(remaining)} session(s) remaining.")
```

??? note "輸出"

    ```text
    Deleted 21100fd5
    Deleted 54b0d2d8
    Deleted 9bc70b72
    Deleted 7146a49b

    0 session(s) remaining.
    ```

# 回顧

我們針對 Agent SDK 的本機 transcript 儲存，做出了 session browser 的核心：

- 用 `list_sessions()` **列出**，就拿到渲染側邊欄所需的一切，而且能擴展，因為它讀的是檔案 stat 和頭尾片段，而不是解析整個 transcript。
- 用 `get_session_messages()` **讀取**，不啟動 agent 就能把對話載回來顯示。
- 用 `rename_session()` 和 `tag_session()` **整理**，是附加 metadata 紀錄，所以很便宜，而且最新一次呼叫有效。
- 用 `fork_session()` 加 `options.resume` **分支**，讓使用者在不碰原對話的前提下分支並繼續。

這些全都是對 `~/.claude/projects/` 的純檔案操作。不管 agent subprocess 有沒有在跑都能用，而且看到的是跟 Claude Code CLI 寫的同一批 transcript。

## 接下來去哪

- **接上 UI。** 這些函式跟 UI 無關；放在 FastAPI route 或 Electron IPC handler 後面，就是 session 側邊欄的後端。
- **跨主機的 session。** transcript 存在本機磁碟。要跨機器共用，就同步檔案，或把 session ID 和訊息索引到你自己的儲存。做法見 [Manage sessions on disk](https://docs.claude.com/en/agent-sdk/local-session-management)。
- **TypeScript。** `@anthropic-ai/claude-agent-sdk` 有同樣的 API，只是用 camelCase 命名（`listSessions`、`forkSession` 等）。見 [TypeScript SDK reference](https://docs.claude.com/en/agent-sdk/typescript)。
- **更大的圖。** Notebook [00](00_The_one_liner_research_agent.md) 到 [03](03_The_site_reliability_agent.md) 講怎麼打造 agent 本身。這個 notebook 講的是管理它留下來的東西。

## 重點整理

- Agent SDK 把每段對話存成 JSONL transcript，session 管理函式都是對這些檔案的純讀寫，不需要 agent 在跑。
- 列表靠檔案 stat 加頭尾片段，所以 session 再多也快；要分頁用 `limit` / `offset`。
- rename 和 tag 是附加紀錄，最新的贏；tag 只有單一值，soft-delete 用 `"__hidden"` 這類做法最安全。
- fork 複製 transcript 並重新對應 ID，原本的不動；用 `options.resume` 才會變成活的對話。

## 練習

1. 把示範的三個 prompt 換成你自己的，用 `list_sessions()` 的 `limit=2` 和 `offset` 試著分頁看全部。
2. 對其中一個 session 用 `rename_session()` 改名，再用 `tag_session()` 標成 `"__hidden"`，寫個過濾條件讓列表不顯示它。
3. 用 `get_session_messages()` 取一個 session 的某則訊息 `uuid`，傳給 `fork_session()` 的 `up_to_message_id`，resume 後問一個新問題，並列出來源與 fork 的內容比較。
