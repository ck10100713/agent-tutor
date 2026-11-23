---
translated: true
source: managed_agents/data_analyst_agent.ipynb
---
# 用 Claude Managed Agents 做一個資料分析 agent

> 原文：[managed_agents/data_analyst_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/data_analyst_agent.ipynb)

做一個分析師 agent，丟 CSV 進去，它會用沙盒環境和檔案掛載，產出一份帶互動圖表的 HTML 敘事報告。

## 這篇在做什麼

你會在 Claude Managed Agents 上建一個資料分析 agent：先建環境，再建 agent，把 CSV 掛進 session，然後送出任務、即時看事件串流，最後把 agent 寫出來的 HTML 報告下載回來。整個流程的重點是 Agent、Environment、Session、Events 這四個概念怎麼串起來。

## 學完你會

- 建出可重複使用的環境（預裝 pandas、plotly）和分析用 agent。
- 把資料集上傳並掛進 session，讓 agent 直接讀。
- 即時追蹤 agent 的執行過程，並用 Files API 下載它產出的 `report.html`。

## 開跑前

- 需要 `ANTHROPIC_API_KEY`，而且帳號要有 Managed Agents 的 beta 權限。
- 用 Colab 的話，把金鑰放在 Colab 的 Secrets（左側鑰匙圖示），再用 `userdata.get` 讀進環境變數即可。

## 簡介

每個團隊都有人會被丟一份 CSV，然後被問「這裡面有什麼有趣的東西？」這篇要做的 agent 就是替他回答：上傳一份 CSV，拿回一份帶互動圖表的 HTML 敘事報告。

你會跑在 [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 上。這是 Anthropic 代管的 runtime，專門跑有狀態、會用 tool 的 agent，有四個核心概念：

- **Agent**：模型、system prompt、tool、MCP server 和 skill
- **Environment**：設定好的容器模板（套件、網路存取）
- **Session**：在某個 environment 裡跑的 agent 實例，負責一個具體任務並產出結果
- **Events**：你的應用程式和 agent 之間交換的訊息（使用者輸入、tool 結果、狀態更新）

Agent 加上 environment 就能開出 session。你把資料當 resource 掛上去，再靠送 event、讀串流來驅動它。

沙盒、tool 執行和 context 管理都由 Anthropic 處理。如果你想完全掌控 agent loop 和部署方式，可以改用 [Claude Agent SDK](https://platform.claude.com/docs/en/api/agent-sdk/overview)。

### 你會學到什麼

做完之後你可以：

- 建好可重複使用的資料分析 environment 和 agent
- 把資料集交給 agent
- 看 agent 執行時的進度
- 下載報告和它產生的其他檔案

### 事前準備

- Python 3.11+
- 從 [Console](https://platform.claude.com/settings/keys) 拿一組 Anthropic API key，設成 `ANTHROPIC_API_KEY`

安裝套件：

```python
%%capture
%pip install -q "anthropic>=2.0.0" python-dotenv
```

```python
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv, set_key

load_dotenv()
client = Anthropic()
MODEL = "claude-sonnet-5-5"
```

## 1. 建立 environment

**Environment** 是可重複使用的容器規格。這裡先宣告 `pandas` 和 `plotly`，之後每個 session 一開始就裝好了，agent 可以直接開始分析，不用先 `pip install`。

這裡網路設成 `unrestricted`，這樣 agent 才能從 CDN 載入 plotly。不過這代表它可以連到網路上任何地方，正式環境請改用 [host allowlist](https://platform.claude.com/docs/en/managed-agents/environments)。

```python
env = client.beta.environments.create(
    name="cookbook-data-analyst-env",
    config={
        "type": "cloud",
        "networking": {"type": "unrestricted"},
        "packages": {
            "type": "packages",
            "pip": ["pandas", "plotly"],
        },
    },
)
```

## 2. 建立 agent

**Agent** 是把模型、system prompt 和一組 tool 配在一起。輸出品質大部分取決於 system prompt；這份 prompt 會要求敘事結構、用具體數字支撐的發現，以及在同一個 HTML 檔裡嵌入多張 plotly 圖表的正確寫法。

[`agent_toolset_20260401`](https://platform.claude.com/docs/en/managed-agents/tools) 提供八個 tool：`bash`、`read`、`write`、`edit`、`glob`、`grep`、`web_fetch` 和 `web_search`。這裡全部設成 `always_allow`，但兩個 web tool 是關掉的，因為這次分析不用上網。

```python
ANALYST_SYSTEM_PROMPT = """\
You are a senior data analyst producing a publication-quality report.

## Style
- Professional and precise. Let the data speak with concrete numbers.
- Short paragraphs (2-3 sentences) between charts.
- Lead with the most actionable finding.

## Execution
- Write .py scripts and run them with `python3 script.py`.
- Sample large tables (`nrows=` / `.sample()`) instead of loading everything.
- Sanity-check key metrics before building narrative around them.

## Charts
- Build each chart as its own `go.Figure()`, embed with
  `fig.to_html(include_plotlyjs=False, full_html=False)`, and load plotly
  from the CDN once in <head>.
- Always set `marker_color` and `template='simple_white'`.

## Output
Write a single self-contained `report.html` to /mnt/session/outputs/
with inline CSS, 3+ embedded plotly charts, and a closing section of
actionable recommendations. Confirm "Saved: report.html" when done.
"""

agent = client.beta.agents.create(
    name="cookbook-data-analyst",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/data-analyst-agent"},
    model=MODEL,
    system=ANALYST_SYSTEM_PROMPT,
    tools=[
        {
            "type": "agent_toolset_20260401",
            # default_config applies to every tool in the set;
            # entries in configs override specific tools.
            "default_config": {
                "enabled": True,
                "permission_policy": {"type": "always_allow"},
            },
            "configs": [
                {"name": "web_search", "enabled": False},
                {"name": "web_fetch", "enabled": False},
            ],
        }
    ],
)
```

## 3. 上傳資料集

附的範例 CSV 只有 50 列，幾分鐘就能分析完。你可以換成任何 CSV（或一個裝 CSV 的 zip），後面的流程完全一樣。

```python
DATA_PATH = Path("example_data/data_analyst_agent/sales_data.csv")

with DATA_PATH.open("rb") as f:
    dataset = client.beta.files.upload(file=(DATA_PATH.name, f, "text/csv"))

print(f"Uploaded {DATA_PATH.name} ({dataset.size_bytes} bytes) as {dataset.id}")
```

??? note "輸出"

    ```text
    Uploaded sales_data.csv (2833 bytes) as file_011CZqKKomgL45BLo2J8K5X9
    ```

## 4. 建立 session 並送出任務

**Session** 把 agent 綁到 environment 和掛載的檔案上。傳入 `{"type": "agent", "id": ..., "version": ...}` 就會重用前面建好、有版本的 agent。`resources` 會把上傳的檔案掛到容器內指定的絕對路徑。

建好 session 之後，送一個帶任務內容的 `user.message` event，agent 就會馬上開工。

```python
MOUNT_PATH = f"/mnt/session/uploads/{DATA_PATH.name}"

session = client.beta.sessions.create(
    environment_id=env.id,
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    resources=[{"type": "file", "file_id": dataset.id, "mount_path": MOUNT_PATH}],
    title="Sales analysis",
)

ANALYSIS_PROMPT = f"""\
Analyze the e-commerce orders in {MOUNT_PATH}.

Columns: order_id, customer_id, product, category, price, quantity,
order_date, region.

Focus on revenue by category and region, repeat-customer behavior, and
one surprising pattern. Produce report.html per your system instructions.
"""

client.beta.sessions.events.send(
    session.id,
    events=[
        {"type": "user.message", "content": [{"type": "text", "text": ANALYSIS_PROMPT}]},
    ],
)
print(f"Session {session.id} running")
```

??? note "輸出"

    ```text
    Session sesn_011CZqKKqyPRph9J5khKLn6u running
    ```

## 5. 串流執行過程

到 [Console](https://platform.claude.com/) 的 **Sessions** 打開這個 session，可以即時看到每個 event、tool 呼叫和 token 數：

<img src="https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/managed_agents/example_data/data_analyst_agent/console_session.png" alt="Session trace in the Console" width="700" />

下面的 helper 會追同一條 event 串流，`agent.message` 的文字和 `agent.tool_use` 的呼叫一出現就印出來，遇到 `session.status_idle` 就結束。

```python
def wait_for_idle(session_id: str) -> None:
    for ev in client.beta.sessions.events.stream(session_id):
        t = ev.type
        if t == "agent.message":
            for block in ev.content:
                if block.type == "text":
                    text = block.text
                    print(text[:300] + ("..." if len(text) > 300 else ""))
        elif t in ("agent.tool_use", "agent.mcp_tool_use"):
            print(f"  [{ev.name}]")
        elif t == "session.status_idle":
            return
        elif t == "session.status_terminated":
            raise RuntimeError(
                "Session terminated before going idle. "
                f"Trace: https://platform.claude.com/sessions/{session_id}"
            )


wait_for_idle(session.id)
```

## 6. 取回報告

Agent 寫進 `/mnt/session/outputs/` 的任何檔案都會被保存，並透過 Files API 用 `scope_id=<session_id>` 取得。寫在容器其他位置的檔案不會保存。

[Files API](https://platform.claude.com/docs/en/api/beta/files/list) 是另一個還在 beta 的功能，所以這裡要用 `scope_id` 的話，也要帶上 Managed Agents 的 beta header。

```python
outputs = client.beta.files.list(scope_id=session.id, betas=["managed-agents-2026-04-01"])
for f in outputs.data:
    print(f.filename, f.size_bytes)

# The list also includes the mounted input CSV; pick out the report.
report = next((f for f in outputs.data if f.filename == "report.html"), None)
if report is None:
    raise RuntimeError(f"report.html not found. Files: {[f.filename for f in outputs.data]}")
content = client.beta.files.download(report.id)
Path("report.html").write_bytes(content.read())
print("Downloaded report.html")
```

??? note "輸出"

    ```text
    report.html 53728
    sales_data.csv 2833
    Downloaded report.html
    ```

## 7. 清理與下一步

Agent 和 environment 建一次就能跨多次執行重用；每段對話則要新開一個 session。報告拿到之後，把這個 session 封存，釋放它的容器。下面幾行會把 agent 和 environment 的 ID 存進 `.env`，讓 [`slack_data_bot.ipynb`](slack_data_bot.md) 能用它們開新的 session。

> **警告：** 跑下一個 cell 之前，先確認 `.env` 已經在 `.gitignore` 裡，千萬不要 commit。

```python
client.beta.sessions.archive(session.id)

set_key(".env", "ANALYST_ENV_ID", env.id)
set_key(".env", "ANALYST_AGENT_ID", agent.id)
set_key(".env", "ANALYST_AGENT_VERSION", str(agent.version))
print("Saved ANALYST_ENV_ID, ANALYST_AGENT_ID, ANALYST_AGENT_VERSION to .env")
```

??? note "輸出"

    ```text
    Saved ANALYST_ENV_ID, ANALYST_AGENT_ID, ANALYST_AGENT_VERSION to .env
    ```

到這裡你已經完整做完一個資料分析 agent：可重複使用的 environment 和 agent、掛了你的 CSV 的 session、即時的 event 串流，以及下載下來的 HTML 報告。

接下來可以：

- 打開下載的 `report.html`，看敘事和圖表。
- 在 [Console](https://platform.claude.com/) 打開這個 session，查看 token 用量和完整的 event log。
- 繼續看 [`slack_data_bot.ipynb`](slack_data_bot.md)，學怎麼從 Slack 驅動這個 agent。

## 重點整理

- Managed Agents 的結構是 Agent（模型加 prompt 加 tool）、Environment（容器模板）、Session（兩者組合的執行實例）、Events（雙方溝通的訊息）。
- Environment 預先裝好套件，session 一開就能分析；agent 和 environment 建一次重用，session 每段對話新開。
- 輸出品質主要看 system prompt，所以要在 prompt 裡把報告結構、數字佐證、圖表嵌入方式講清楚。
- 檔案要寫到 `/mnt/session/outputs/` 才會保存，之後用 Files API 加上 `scope_id` 下載。
- 網路 `unrestricted` 只適合試玩，正式環境要用 host allowlist。

## 練習

1. 把範例 CSV 換成你自己的資料，重跑第 3 到第 6 步，看報告內容有什麼不同。
2. 改 agent 的 system prompt，要求報告最前面加一段三句話的摘要，再重跑一次比較差異。
3. 把 environment 的網路改成 host allowlist（只放行載入 plotly 的 CDN 網域），確認報告的圖表還是能正常顯示。
