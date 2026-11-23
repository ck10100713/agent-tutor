---
translated: true
source: claude_agent_sdk/08_Dynamic_workflows.ipynb
---
# 用 dynamic workflow 大規模調度 subagent

> 原文：[claude_agent_sdk/08_Dynamic_workflows.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/08_Dynamic_workflows.ipynb)

從 Agent SDK 觸發 dynamic workflow，用平行的 verifier 和 skeptic subagent 對照來源文件查核一份報告。

## 這篇在做什麼

拿一份投資人更新草稿，用 Claude Code 的 dynamic workflow 逐條查核裡面 10 個事實宣稱。Claude 會自己寫一支 JavaScript 調度腳本，派一堆 subagent 平行驗證，再讓挑錯的 skeptic 複查，最後出一份 go/no-go 報告。

## 學完你會

- 判斷一個任務該用單一 agent、subagent 還是 dynamic workflow
- 用 Python Agent SDK 觸發 workflow，並串流看進度
- 看懂 Claude 寫出來的調度腳本，認得 fan-out 和對抗式驗證這些模式

## 開跑前

- 需要 `ANTHROPIC_API_KEY`（放在 `.env`）。
- Python 3.11 以上，`claude-agent-sdk` 0.2.90 以上（內含 Claude Code CLI v2.1.154 以上）。
- 整本跑完大約花 2 到 4 美元的 API 費用，失敗重試會更多。
- 在 Colab 上直接用 Secrets 設 `ANTHROPIC_API_KEY`，再跑安裝 cell 即可。

## 簡介

查核一份投資人更新，要檢查很多彼此獨立的宣稱，每條都要真的下判斷，還要確保驗證真的有跑。這個量一個 context window 不太裝得下。Dynamic workflow 是 Claude Code 的功能，專門處理需要的 agent 數量超過單一對話能協調的任務。它不是一輪一輪地調度，而是讓 Claude 針對任務寫一支 JavaScript 調度腳本，交給 `Workflow` tool，由 runtime 在背景執行。腳本可以平行或分階段派 subagent，把結果存在變數裡，再用普通程式碼做串接邏輯（過濾、迴圈、驗證）。因為 Agent SDK 驅動的就是 Claude Code runtime，所以可以直接從 Python 啟動 workflow。

每個 subagent 都是完整的 Claude Code agent。它從乾淨的 context 開始，只看得到腳本給它的 prompt，在你 session 的工作目錄裡用你設定的 tool allowlist 做事。預設每個 agent 都用 session 的模型，但腳本可以把某個階段改派給別的模型：機械式的擷取用便宜的，困難的判斷用最強的。你可以從 prompt 引導，也可以用環境變數 `CLAUDE_CODE_SUBAGENT_MODEL` 一次覆蓋所有 agent。Runtime 最多同時跑 16 個 agent（CPU 核心少的機器更少），一次 run 最多 1,000 個 agent；規劃的工作超過並行上限就會排隊等空位。

因為計畫寫在程式碼裡而不是模型的 context window，每個項目的處理方式都一致，驗證因為腳本寫了就一定會跑，一次 run 可以協調幾十到上百個 agent，而且腳本是個你可以讀、改、存、重跑的檔案。代價是 token：很多 subagent 會花掉多很多 token。以下情況值得用 workflow：任務超過一個 context window、驗證必須由結構強制執行、或調度本身值得保留。

**讀完這本 cookbook，你會能：**

- 判斷什麼時候任務需要 dynamic workflow，而不是單一 agent 或 subagent
- 從 Python Agent SDK 觸發 dynamic workflow 並串流進度
- 讀懂 Claude 寫的調度腳本，認出裡面的模式（fan-out、對抗式驗證）

範例是對照來源文件查核一份投資人更新草稿。同樣的形狀（很多片段、需要真判斷、有驗證步驟）也出現在文件稽核、內容遷移、研究整合和分流佇列。

> **Note:** 這本 notebook 裡所有公司名稱、指標和客戶資料都是虛構的，只用於示範。

## 前置條件

**需要的知識：**

- Python 基礎，包含 `async`/`await`
- 熟悉 Claude Agent SDK 基本用法（`query()` 和 `ClaudeAgentOptions`）。新手請先看 [notebook 00](00_The_one_liner_research_agent.md)。

**需要的工具：**

- Python 3.11 以上
- Anthropic API key（[在這裡申請](https://platform.claude.com/)），放在 `.env` 的 `ANTHROPIC_API_KEY`

Agent SDK 內建它驅動的 Claude Code CLI，dynamic workflow 就在那個 runtime 裡。需要 CLI **v2.1.154 以上**，`claude-agent-sdk` 0.2.90 以上才會內建。下面的安裝 cell 已經設好最低版本，不用再設定別的。

Dynamic workflow 在所有付費方案、Anthropic API 存取，以及 Amazon Bedrock、Google Cloud 的 Agent Platform、Microsoft Foundry 上都能用，最新細節見 [dynamic workflows 文件](https://code.claude.com/docs/en/workflows)。

> **費用提醒：** workflow 會派很多 subagent，token 用量明顯比單一 agent 的 session 多。這本 notebook 從頭跑到尾大約花 2 到 4 美元的 API 費用，某個階段失敗重試會更多。Workflow 跑完會印出費用。

## 設定

安裝 SDK 並載入 API key。下面的版本下限保證 SDK 版本內建的 Claude Code CLI 支援 dynamic workflow，下一個 cell 會檢查。如果你在已經 import 舊版的 kernel 裡升級 SDK，要重啟 kernel，Python 才會載入新版。

```python
%%capture
%pip install -U "claude-agent-sdk>=0.2.90" python-dotenv
```

```python
import re
import shutil
import time
from pathlib import Path

from dotenv import load_dotenv
from IPython.display import Markdown, display

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    TaskProgressMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

load_dotenv()

MODEL = "claude-sonnet-5-5"

# Dynamic workflows require Claude Code v2.1.154+; SDK 0.2.90 and later bundle a compatible CLI.
version_match = re.match(r"(\d+)\.(\d+)\.(\d+)", claude_agent_sdk.__version__)
sdk_version = tuple(int(g) for g in version_match.groups()) if version_match else (0, 0, 0)
assert sdk_version >= (0, 2, 90), (
    f"claude-agent-sdk {claude_agent_sdk.__version__} is too old for dynamic workflows - "
    "re-run the install cell, then restart the kernel"
)
print(f"claude-agent-sdk {claude_agent_sdk.__version__}")
```

??? note "輸出"

    ```text
    claude-agent-sdk 0.2.168
    ```

### 建立 OrbitCart 工作區

我們虛構的公司叫 **OrbitCart**，是一家線上單車用品店。下一個 cell 會在磁碟上寫出一個小工作區：`investor_update.md` 是一份投資人更新草稿，裡面有 10 個事實宣稱；`sources/` 目錄放這些宣稱該對得上的真實資料（月銷售 CSV、客戶調查結果、uptime 報告、媒體報導檔）。

草稿裡刻意埋了問題，讓 workflow 有真東西可以抓：

- **宣稱 1、4、5、6 跟來源矛盾。** 銷售 CSV 顯示 Q2 營收是 $4.61M，比 Q1 高 28%，但草稿寫 $4.8M 和 42%。調查的 NPS 是 62，不是 71。Uptime 報告顯示本季平均 99.71%（包含 5 月一次六小時的事故），不是 99.99%。TechPedal 說 OrbitCart 是「one of the fastest-growing online cycling retailers」，不是「the fastest-growing cycling retailer」。
- **宣稱 7 和 8 無法驗證。** 沒有任何來源提到 6 月的限時特賣或客服解決時間。
- **宣稱 2、3、9、10 至少有一個來源支持。**

Agent 是對檔案工作，所以資料放在磁碟上，但我們在 notebook 裡建立，讓你看清楚 agent 會看到什麼。跑完之後，我們會拿 workflow 的判定去對這份標準答案。

```python
WORKSPACE = Path("orbitcart_data").resolve()
SOURCES = WORKSPACE / "sources"
SOURCES.mkdir(parents=True, exist_ok=True)

# --- The draft investor update: 10 claims for the fact-check workflow ---
(WORKSPACE / "investor_update.md").write_text("""\
# OrbitCart - Q2 2026 Investor Update (DRAFT)

*Prepared by the founding team. Not yet reviewed.*

Dear investors,

Q2 was OrbitCart's strongest quarter yet. Highlights:

1. **Revenue:** Q2 revenue reached **$4.8M, up 42% from Q1**.
2. **Order volume:** We processed **over 38,000 orders** in the quarter.
3. **Customers:** Our active customer base grew to **12,400**.
4. **Customer love:** We earned a **Net Promoter Score of 71**.
5. **Reliability:** The platform maintained **99.99% uptime** across the quarter.
6. **Press:** TechPedal called us **"the fastest-growing cycling retailer in North America."**
7. **Growth:** Our June flash sale was **the biggest single sales day in company history**.
8. **Support:** Customer support resolution time improved to **under 4 hours**.
9. **Catalog:** We launched **3 new product categories** this quarter.
10. **Trust:** **Zero customer data was lost** during the brief May service interruption.

We look forward to discussing these results at the board meeting.

- The OrbitCart team
""")

# --- Source documents: the ground truth the claims should trace back to ---
(SOURCES / "monthly_sales.csv").write_text("""\
month,revenue_usd,orders,new_customers
2026-01,1150000,9800,1020
2026-02,1180000,10100,990
2026-03,1270000,9900,1100
2026-04,1480000,12800,1410
2026-05,1520000,12400,1380
2026-06,1610000,13200,1640
""")

(SOURCES / "customer_survey.txt").write_text("""\
OrbitCart Customer Survey - Q2 2026 Results
Survey window: June 10-17, 2026 | Responses: 2,140

Net Promoter Score (NPS): 62  (Q1: 58)
Active customers at end of Q2: 12,400
Support satisfaction (CSAT): 4.4 / 5

Selected verbatim feedback:
- "Ordering was painless and the bike arrived two days early." (Pro customer, Denver)
- "Great selection, but I wish there were more filter options." (Free customer, Toronto)
- "The team plan made it easy to outfit our whole shop." (Team customer, Portland)
""")

(SOURCES / "uptime_report.txt").write_text("""\
OrbitCart Platform Reliability Report - Q2 2026

April 2026:  99.97% uptime, no incidents
May 2026:    99.18% uptime
  - May 14: checkout degraded for 5h 58m during a database failover.
    No customer data was lost. Root cause: connection pool exhaustion.
June 2026:   99.98% uptime, no incidents

Quarter average: 99.71%
""")

(SOURCES / "press_coverage.md").write_text("""\
# Press mentions - Q2 2026

## TechPedal, May 3, 2026
"OrbitCart has quietly become one of the fastest-growing online cycling retailers
in North America, on the strength of a no-friction checkout and a generous
returns window."

## Gear & Grease Weekly, June 21, 2026
"The Portland-based startup recently expanded into bike maintenance tools, indoor
training equipment, and cycling apparel - three categories that traditional bike
shops have struggled to move online."
""")

print(f"Workspace: {WORKSPACE.name}/")
print(f"Investor update claims: 10 | Source documents: {len(list(SOURCES.iterdir()))}")
```

??? note "輸出"

    ```text
    Workspace: orbitcart_data/
    Investor update claims: 10 | Source documents: 4
    ```

## Subagent 與 workflow 的差別

Agent SDK 本來就有兩種跑多步驟任務的方式，dynamic workflow 是第三種。三者的差別可以濃縮成一個問題：**誰握有計畫？**

|  | 單一 agent | Subagent | Dynamic workflow |
|---|---|---|---|
| **是什麼** | 一個 agent 一步一步做 | 主 agent 派出的 worker | 由 runtime 執行的腳本 |
| **誰決定下一步** | Claude，一輪一輪 | Claude，一輪一輪 | 腳本 |
| **中間結果放哪** | Claude 的 context window | 主 agent 的 context window | 腳本變數 |
| **可重複的是什麼** | prompt | worker 的定義 | 整個調度流程 |
| **規模** | 一個 context window | 每輪幾個委派任務 | 每次 run 幾十到上百個 agent |
| **中斷** | 該輪重來 | 該輪重來 | 同一個 session 內可續跑 |

用 **subagent**（[notebook 01](01_The_chief_of_staff_agent.md) 的模式）時，Claude 是調度者。它一輪一輪決定要委派什麼，沒有任何機制保證它每一塊都會派、最後會合併結果、或真的驗證過什麼。每個 worker 的結果都會回到主 agent 的 context，委派 4 個沒問題，4 百個就不行了。計畫也只存在 Claude 的 context 裡：中斷之後工作得從頭來。

**Dynamic workflow** 把這些特性全部反過來。由腳本決定跑什麼，中間結果放在腳本變數，腳本本身是你可以讀、存、改、重跑的產物。代價是 token，因為 workflow 會派很多 subagent。適合用的時機是任務**大到一個 context window 裝不下**、你要**用結構強制驗證**、或**調度本身值得保留**。

## Dynamic workflow 的結構

從 Agent SDK 觸發 workflow 要做兩件事：

1. **在 `allowed_tools` 允許 `Workflow` tool。** 這是 Claude 啟動 workflow 用的 tool，SDK 會自動核准這個清單裡的 tool。
2. **在 prompt 裡用白話要求 workflow**：「use a workflow to…」。Claude 會把這種直接請求當成同意用腳本調度，而不是一輪一輪做。（互動式 CLI 另外有關鍵字觸發和 `/effort ultracode` 模式；從 SDK 來，直接講清楚就夠了。）

Claude 呼叫 `Workflow` tool 時，會把它為你的任務寫好的完整 JavaScript 調度腳本傳進去。Runtime **在背景**執行腳本：你的 `query()` stream 保持連線，agent 在跑的同時進度事件會持續傳回來。因為啟動是一輪、完成是另一輪，stream 每一輪都會吐一個 `ResultMessage`。最後一個帶著最終結果，下面的 `run_agent()` 輔助函式留的就是那個。在 SDK 裡沒有互動式權限提示，tool 呼叫依你設定的權限規則走，所以我們才設明確的 `allowed_tools` 清單。（你可能看到 `Bash` 這類唯讀呼叫在 allowlist 外也成功：非互動式執行會自動允許唯讀指令、拒絕其他。）Workflow 派出的 subagent 以 `acceptEdits` 模式執行，並繼承這份 allowlist。

第一次跑之前有幾件事要知道：

- **腳本是真的產物。** Runtime 會把它寫到 `~/.claude/projects/` 底下你 session 目錄的檔案，並把路徑放進 tool 結果，所以下面的 `run_agent()` 可以抓到。我們會在跑完後讀這支腳本。
- **發現的結果回到腳本，而不是寫成報告檔。** Workflow 的 agent 把發現當作回傳值交回，結果才會進到腳本變數。在我們的執行裡，agent 想寫 `SUMMARY.md` 這類報告檔時，會被告知改成回傳內容。真正的成品（轉好的文件、程式碼、資料檔）則照常寫到磁碟。
- **執行可能失敗，也可以續跑。** 如果某個階段中途失敗（例如 agent 用完 structured output 的重試次數），你會在 log 看到 `[Failed]` 通知，Claude 通常會重新啟動 workflow。已經完成的 agent 回傳快取結果，所以重試大多只重做失敗的階段，費用會相應增加。這是續跑機制在運作，不是 notebook 壞了。
- **行為與上限。** Workflow 同時最多跑 16 個 agent（CPU 核心少的機器更少），每次 run 最多 1,000 個 agent。調度腳本本身碰不到你的檔案系統或 shell，只有它派出的 agent 可以。停掉的 run 在同一個 session 內可續跑，新 session 就從頭開始。

我們自己寫了一個小 logger，沒有重用這個資料夾的 `agent_visualizer` 輔助工具，因為 workflow 會發出 `TaskProgressMessage` 和 `TaskNotificationMessage` 事件，那些工具沒涵蓋。下一個 cell 定義這次 run 要用的輔助函式：`run_agent()` 串流一次 query 並印出精簡的活動 log，`workflow_options()` 建出 `ClaudeAgentOptions`，`show_script()` 顯示 Claude 產生的調度腳本。

````python
# The Workflow tool result mentions the persisted script path and task ID in plain
# text; these regexes scrape it. A convenience for this demo, not a stable API.
SCRIPT_PATH_RE = re.compile(r"Script file: (.+?\.js)")
TASK_ID_RE = re.compile(r"Task ID: (\S+)")


async def run_agent(prompt: str, options: ClaudeAgentOptions) -> dict:
    """Stream a query through the Agent SDK and print a compact activity log.

    Returns a dict with the final result text, the total cost, and - when a
    workflow ran - the path of the orchestration script Claude generated.
    """
    info = {"result": None, "cost_usd": None, "script_path": None}
    last_tool_count = 0  # throttle progress lines
    started = time.monotonic()

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    # Show the first line of Claude's narration
                    if narration := block.text.strip():
                        print(f"\nClaude: {narration.splitlines()[0]}")
                elif isinstance(block, ToolUseBlock):
                    if block.name == "Workflow":
                        script = block.input.get("script", "")
                        n_lines = len(script.splitlines())
                        print(
                            f"\n[Workflow tool] Claude wrote a {n_lines}-line orchestration script"
                        )
                    else:
                        print(f"  -> {block.name}")

        elif isinstance(msg, UserMessage):
            blocks = msg.content if isinstance(msg.content, list) else []
            for block in blocks:
                if not isinstance(block, ToolResultBlock):
                    continue
                text = block.content if isinstance(block.content, str) else str(block.content)
                if match := SCRIPT_PATH_RE.search(text):
                    info["script_path"] = match.group(1)
                    task = TASK_ID_RE.search(text)
                    task_id = task.group(1) if task else "?"
                    print(f"[Launched] Workflow running in the background (task {task_id})")

        elif isinstance(msg, TaskProgressMessage):
            # Progress arrives every few seconds; print a line every ~8 new agent tool calls
            tools = msg.usage.get("tool_uses", 0)
            if tools - last_tool_count >= 8:
                last_tool_count = tools
                tokens = msg.usage.get("total_tokens", 0)
                seconds = msg.usage.get("duration_ms", 0) / 1000
                print(
                    f"    ... {tools:>3} agent tool calls | {tokens:>9,} tokens | {seconds:>4.0f}s"
                )

        elif isinstance(msg, TaskNotificationMessage):
            print(f"[{msg.status.capitalize()}] {msg.summary}")

        elif isinstance(msg, ResultMessage):
            # A background workflow yields one result per turn: the launch turn, then the
            # final turn after the workflow completes. Keep the latest and report once.
            info["result"] = msg.result
            info["cost_usd"] = msg.total_cost_usd

    cost = f" | ${info['cost_usd']:.2f}" if info["cost_usd"] is not None else ""
    minutes = (time.monotonic() - started) / 60
    print(f"\n=== Run complete in {minutes:.1f} min{cost} ===")
    return info


def show_script(info: dict) -> None:
    """Render the orchestration script Claude generated during a run."""
    path = info.get("script_path")
    if not path or not Path(path).exists():
        print("No workflow script was generated in this run.")
        return
    display(Markdown(f"```javascript\n{Path(path).read_text()}\n```"))


def workflow_options() -> ClaudeAgentOptions:
    """ClaudeAgentOptions for a workflow-enabled agent working in the OrbitCart workspace."""
    return ClaudeAgentOptions(
        cwd=str(WORKSPACE),
        model=MODEL,
        allowed_tools=["Read", "Write", "Edit", "Glob", "Grep", "Workflow"],
        permission_mode="acceptEdits",
        max_turns=40,
        setting_sources=[],  # self-contained: don't load user/project Claude Code settings
    )
````

## 範例：查核投資人更新

**任務：** 法務要求 `investor_update.md` 每一條宣稱都追溯到來源文件才肯簽核。共有 10 條宣稱和四個來源檔。

**為什麼用 workflow：** 單一 agent 查 10 條宣稱，會把所有來源文件都累積在 context 裡，查到第 7 條就開始略讀。「再檢查一次你的發現」也只是一句指示，context 吃緊時就會被跳過。下面的 workflow 讓驗證變成*結構*的一部分：
1. **擷取：** 一個 agent 讀草稿，抽出每一條事實宣稱
2. **驗證：** *每條宣稱*一個 agent，各自在乾淨的 context 裡重新讀來源
3. **對抗式檢查：** 一個 skeptic agent 在判定被接受之前逐條挑戰
4. **報告：** 一個 agent 把判定整理成 go/no-go 報告

這就是 **fan-out + 對抗式驗證** 模式。注意下面的 prompt 有多少篇幅在描述工作的*形狀*，而不是任務本身。用 workflow 時，prompt 描述的是你要的 harness。

```python
FACT_CHECK_PROMPT = """\
Use a workflow to fact-check the draft investor update at investor_update.md against
the source documents in sources/.

Structure the workflow exactly like this:

1. EXTRACT: one agent reads investor_update.md and extracts its ten numbered
   highlights as structured output (claim number, claim text). Keep the draft's own
   numbering 1-10 and treat each numbered highlight as exactly one claim, even when it
   bundles two figures.

2. VERIFY: one agent per claim, running in parallel. Each verifier reads the source
   documents in sources/ and returns a verdict as structured output:
   - "confirmed" if a source directly supports the claim (quote the supporting line)
   - "contradicted" if a source conflicts with it (quote the conflicting line and
     state the correct figure)
   - "unverifiable" if no source covers it
   Verifiers must quote the exact lines they relied on. Pay attention to subtle
   differences between what a source says and what the draft claims it says.

3. SKEPTIC: for every "confirmed" verdict, one skeptic agent re-reads the cited
   source and tries to refute the confirmation. If the skeptic finds the citation
   does not actually support the claim, the verdict changes to "contradicted".

4. REPORT: one final agent compiles a markdown fact-check report: a table of every
   claim with its verdict and evidence, then a summary of what must be fixed before
   the update can be sent. Return this report as the workflow result.

The working directory is already set to the folder containing these files. Refer to
every file by relative path (e.g. investor_update.md, sources/monthly_sales.csv) in
the script and in agent prompts; do not embed absolute paths.
"""

factcheck_info = await run_agent(FACT_CHECK_PROMPT, workflow_options())
```

??? note "輸出"

    ```text
      -> Skill
    ```

    ```text

    [Workflow tool] Claude wrote a 79-line orchestration script
    [Launched] Workflow running in the background (task wl0y94urk)
    ```

    ```text

    Claude: The fact-check workflow is running in the background (run ID `wf_1f07705a-65b`). It has four stages:
    ```

    ```text
        ...   9 agent tool calls |    38,330 tokens |   12s
    ```

    ```text
        ...  17 agent tool calls |    65,728 tokens |   19s
    ```

    ```text
        ...  25 agent tool calls |    93,097 tokens |   27s
    ```

    ```text
        ...  33 agent tool calls |   132,471 tokens |   35s
    ```

    ```text
        ...  41 agent tool calls |   171,435 tokens |   43s
    ```

    ```text
        ...  50 agent tool calls |   198,723 tokens |   52s
    ```

    ```text
    [Completed] Dynamic workflow "Extract, verify, skeptic-check, and report on claims in investor_update.md" completed
    ```

    ```text

    Claude: The workflow finished. Of the ten claims, four are contradicted, two are unverifiable, and four are confirmed (some with wording caveats). The skeptic upheld all four confirmations, so none were flipped to contradicted.

    === Run complete in 1.3 min | $0.60 ===
    ```

```python
display(Markdown(factcheck_info["result"] or "_(no result returned)_"))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

拿標準答案（我們在資料裡埋的雷）來對照判定：

| 宣稱 | 埋的真相 |
|---|---|
| 1. "$4.8M, up 42%" | **矛盾。** CSV 加總 Q2 為 $4.61M，比 Q1 的 $3.6M 高 28% |
| 4. "NPS of 71" | **矛盾。** 調查寫 62 |
| 5. "99.99% uptime" | **矛盾。** 可靠度報告寫 99.71%，5 月有 6 小時事故 |
| 6. TechPedal 引言 | **矛盾。** 文章寫的是「*one of* the fastest-growing *online* cycling retailers」，不是「the fastest-growing」 |
| 7. 限時特賣、8. 客服時間 | **無法驗證。** 沒有來源涵蓋 |
| 2, 3, 9, 10 | **有來源支持** |

宣稱 6 值得多講一下。一個趕工的 agent 常常會忽略「the fastest-growing」和「one of the fastest-growing」的差別。一個 context 裡沒有其他東西的專職 verifier，再被 skeptic 挑戰，就很難被矇混過去。這種精準度來自 workflow 的結構，不是來自更聰明的模型。

如果 workflow 對有支持的宣稱判得比我們的標準答案*更嚴*，不用意外。宣稱 3、9、10 是 skeptic 這一輪常會挑戰的類型：調查確認了 12,400 這個數字，但沒有來源建立「grew」所需的先前基準（宣稱 3）；媒體報導說公司「recently expanded」到三個品類，但沒確認這些上線發生在 Q2 *之內*（宣稱 9）；而且 5 月雖然沒有資料遺失，skeptic 可能反對把六小時停機稱為「brief」interruption（宣稱 10）。不管你的 run 是確認還是標記它們，那都是對抗式檢查在發揮作用。過度嚴格的標記只花人工複審一分鐘，過度寬鬆的放行會賠掉投資人的信任。

### 讀 Claude 寫的腳本

最有啟發的產物就是腳本本身，因為它顯示工作是怎麼組織的。`Workflow` tool 的結果包含了持久化腳本的路徑，`run_agent()` 把它抓下來了。讀腳本時注意 `schema` 選項，它強制 verifier 回傳結構化判定；也注意各階段之間的純 JavaScript 邏輯：只把確認的判定送給 skeptic 不花任何 token。

```python
show_script(factcheck_info)
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

### 怎麼讀 workflow 腳本

每支 workflow 腳本都用同樣的積木。完整選項記載在 [Agent SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript) 的 Workflow tool 條目，不過把常見的 primitive 對應到上面看到的內容，大部分就學會了：

| Primitive | 做什麼 |
|---|---|
| `export const meta = {name, description, phases}` | 宣告 workflow 的名稱和階段；進度 UI 會依這些階段把 agent 分組 |
| `agent(prompt, options)` | 派出一個 **context 乾淨**的 subagent：它只看得到給它的 prompt 字串，其他都看不到。Options 可以設 `label`、`phase`、結構化輸出用的 JSON `schema`，以及 `model` |
| `parallel([...])` | 同時跑一批 agent，並**等全部完成**（barrier）才繼續 |
| `pipeline(items, stage1, stage2, ...)` | 讓每個項目**各自獨立**走過一串階段，所以項目 A 可以在第 2 階段，項目 B 還在第 1 階段 |
| `phase("...")` | 標記接下來的 agent 屬於哪個階段 |
| 呼叫之間的純 JavaScript | 過濾、去重、合併、迴圈，全都精確、即時、不花 token |
| `return {...}` | 腳本回傳什麼，就有什麼回到你的 session |

這個設計帶來三個特性：

1. **計畫由程式碼強制執行。** Skeptic 這一輪在 verifier 之後跑，是因為腳本的控制流程這樣排序，不靠 Claude 記得某條指示。
2. **Claude 的 context 保持乾淨。** 每個判定和引用的來源行都留在腳本變數裡，只有最後整理好的報告回到啟動 workflow 的 session。
3. **腳本是你的。** 它是磁碟上的檔案，你可以讀（我們剛讀過）、改、存進專案的 `.claude/workflows/` 目錄，再用名稱重跑。調度流程就變成團隊可重複使用的資產。

## 什麼時候該用 workflow

Dynamic workflow 在難度曲線的最上端；它以下的情況，單一 agent 和 subagent 仍然是對的工具。一個合理的判斷指南：

| 選擇... | 當... |
|---|---|
| **單一 agent** | 任務塞得進一個 context window，不需要獨立驗證。大部分任務都在這。 |
| **Subagent** | 你需要幾個專門的 worker（研究員、審查員），而且主 agent 要隨結果調整計畫 |
| **Dynamic workflow** | 任務超出一個 context window（很多項目、很多來源）、需要不能省的驗證、或是會重複的流程 |

這本 notebook 帶來三個控制成本的習慣：

1. **在 prompt 裡把結構講明白。** 你描述的 harness 就是你得到的 harness，包含跑多少驗證、哪些階段可以用比較便宜的模型。
2. **注意每次 run 的費用。** 上面那次 run 印了費用。全部都驗證的 workflow 比什麼都不驗證的貴，這個旋鈕就是在 prompt 裡調的。
3. **資料規模要實在。** 我們用 10 條宣稱和四個來源，讓這本 notebook 幾分鐘就跑完。同樣的結構可以放大到幾百個項目。腳本不在意規模，你的 token 預算在意。

## 清理

移除這本 notebook 建立的工作區。如果你想先翻翻檔案和查核證據，就跳過這個 cell；要再跑一次查核前，得重跑建立工作區的 cell。

```python
shutil.rmtree(WORKSPACE, ignore_errors=True)
print("Workspace removed.")
```

??? note "輸出"

    ```text
    Workspace removed.
    ```

## 你學到了什麼

對照簡介裡的目標：

- **什麼時候用 workflow：** 任務超出一個 context window、驗證必須是結構性而非可選、或調度值得保留的時候。這條線以下，單一 agent 和 subagent 仍是對的工具。
- **怎麼從 Agent SDK 觸發：** 在 `allowed_tools` 允許 `Workflow` tool，在 prompt 裡要求 workflow，再透過 `query()` 串流整個 run（啟動、進度事件、完成）。
- **怎麼讀 Claude 寫的腳本：** `meta` 宣告階段，`agent()` 派出 context 乾淨的 worker，`parallel()` 是 barrier，`pipeline()` 讓項目串流過各階段，中間的邏輯由純 JavaScript 免費處理。這次查核用的是 **fan-out + 對抗式驗證**；同樣的 primitive 也能組成 pipeline、tournament 和分流佇列。
- **怎麼讓 workflow 可重用：** 腳本是檔案。存進專案的 `.claude/workflows/` 目錄並 commit，之後在那個專案工作的任何人（或 agent）都能用名稱重跑同一套調度。

## 下一步

- **把這個模式用在你自己的資料上。** 查核 workflow 適用任何「宣稱對來源」的問題：報告、行銷文案、文件。同樣的結構（擷取、平行驗證、挑戰、彙整）也適用於內容遷移、分流佇列和「靠判斷幫很多東西排名」的問題。
- **在 Claude Code CLI 試試 workflow**，可以用 `/workflows` 互動式觀看執行，並用一個按鍵存下來。見 [dynamic workflows 文件](https://code.claude.com/docs/en/workflows)。
- **比較這個系列的其他調度方式：**[notebook 01](01_The_chief_of_staff_agent.md) 深入講 subagent，[Building Effective Agents patterns](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/README.md) 則直接對 Messages API 實作同樣的調度想法。
- **讀 Anthropic 工程部落格談 multi-agent 系統的文章**，[How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)，講 multi-agent 什麼時候勝過單一 agent、代價是什麼。

## 重點整理

- Dynamic workflow 的關鍵是「誰握有計畫」：subagent 是 Claude 一輪一輪決定，workflow 是腳本決定，所以流程可重複、可保存。
- 驗證靠結構強制執行，不靠 prompt 裡一句「請再檢查」。每條宣稱一個乾淨 context 的 verifier，再加 skeptic 挑戰，就是 fan-out + 對抗式驗證。
- 中間結果放在腳本變數，只有最終報告回到主 session，所以 context 不會被撐爆，各階段之間的過濾和合併也不花 token。
- 代價是 token，只有任務超出一個 context window、驗證不能省、或流程要重複用時才值得。
- 腳本是檔案，存進 `.claude/workflows/` 就能當團隊資產重跑。

## 練習

1. 把 workflow 的 prompt 改成要求只用便宜的模型做擷取階段，跑完看費用差多少。
2. 在 `investor_update.md` 多加一條你自己編的宣稱（一條有來源支持、一條沒有），預測 workflow 的判定，再跑看對不對。
3. 把 prompt 改成不要 skeptic 階段，比較宣稱 3、9、10 的判定跟有 skeptic 時有什麼不同，並把腳本存進 `.claude/workflows/` 重跑一次。
