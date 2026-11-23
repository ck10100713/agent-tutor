---
translated: true
source: managed_agents/CMA_verify_with_outcome_grader.ipynb
---

# Outcomes：會自己驗證成果的 agent

> 原文：[managed_agents/CMA_verify_with_outcome_grader.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_verify_with_outcome_grader.ipynb)

用 Outcomes 建一個評分再修改的迴圈：writer 寫一份附引用的研究簡報，無狀態的 grader 把每個 URL 都抓下來、依 rubric 逐句核對引文，回饋會驅動修改直到簡報通過。內容包含 user.define_outcome、span.outcome_evaluation_* 事件，以及怎麼寫出 grader 做得了事的 rubric。

## 這篇在做什麼

agent 很會產出「看起來做完了」的東西。這篇用 Claude Managed Agents 的 Outcomes，讓平台另外開一個只負責檢查的 grader，依你寫的 rubric 重讀 writer 的成品，沒通過就把逐項缺口退回去，writer 修改後再跑一輪。你會看到整個迴圈跑完，包含 grader 抓到一個真實的問題。

## 學完你會

- 寫出 grader 能確實執行的 rubric
- 帶著 Outcome 開一個 session，讓 agent 朝目標工作
- 追蹤評分再修改的迴圈，讀懂 grader 的回饋
- 判斷什麼時候 Outcomes 是對的工具

## 開跑前

需要有 Claude Managed Agents beta 權限的 Anthropic API key，要有 API 額度，因為 writer 和 grader 都會上網抓資料。

Agent 很會產出「看起來做完了」的東西。請它寫一份附引用的研究簡報，你會拿到一份整齊、有註腳的文件。仔細看通常還有改進空間：某個主題只帶過一點、引文跟原始來源有出入、引用的是新聞稿而不是原始的申報文件。要抓出這些得靠人工的 review 迴圈：你讀成品、找出問題、再下 prompt。而這幾輪裡你說的大部分是回饋，其實在 agent 開工前就能先寫下來。

Claude Managed Agents 的 [Outcomes](https://platform.claude.com/docs/en/managed-agents/define-outcomes) 替 session 多配一個只負責檢查的 agent。你寫一份 **rubric** 說明「做完」長什麼樣、怎麼驗證，平台會在獨立的 context window 裡開出一個 **grader**。grader 看不到 writer 的思考過程，也不知道它走了哪些捷徑。每次 writer 做完一輪，它就依 rubric 重讀成品，要嘛放行，要嘛退回一份逐項的缺口清單。writer 修改後迴圈再跑，次數上限由你設定。

這份指南會讓你看完整個迴圈。writer 寫一頁關於電動車快充經濟的簡報，附上來源的逐字引文。grader 會獨立抓取每個被引用的 URL、在頁面上搜尋引文字串、檢查引文真的支持那個論點，並依七項清單給覆蓋度打分。你會看到它抓到一個真實的問題（該引用 10-K 的地方放了新聞稿附件），也會看到 writer 去找到正確的文件。

## 你會學到

- 寫出 grader 做得了事的 rubric
- 帶著 Outcome 開 session，讓 agent 朝它工作
- 追蹤評分再修改的迴圈，讀 grader 的回饋
- 辨認 Outcomes 什麼時候是對的工具


## 1. 設定環境

先安裝 SDK 並建立 Anthropic client。`define_outcome` 事件和 outcome-evaluation 的 span 類型都屬於 Managed Agents beta。


```python
%%capture
%pip install -q anthropic python-dotenv
```

```python
import os
import re
import time

import anthropic
from dotenv import load_dotenv

load_dotenv()

BETAS = ["managed-agents-2026-04-01"]
MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
client = anthropic.Anthropic()
```

## 2. 建立 writer 並開 session

接著建立 writer agent 並開一個 session。writer 的 system prompt 要求它最多引用六個來源，每個附一段簡短的逐字引文，讓 grader 有具體的東西可以核對。


```python
env = client.beta.environments.create(
    name="research-brief",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
)

writer = client.beta.agents.create(
    name="Research Analyst",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-verify-with-outcome-grader"},
    model=MODEL,
    system="""You are a research analyst. You write one-page business briefs.

Cite every factual claim with an inline footnote [n]. End the brief with a Sources section in this exact format, one entry per line:

[n] "verbatim quote from the page, 25 words or fewer" - Title - URL

Only cite pages you actually fetched and read. The quote must be copied character-for-character from the page. Cite no more than 6 sources total. Pick the strongest; do not pad. Save the brief to /mnt/session/outputs/brief.md.""",
    tools=[
        {
            "type": "agent_toolset_20260401",
            "configs": [
                {"name": "web_search"},
                {"name": "web_fetch"},
                {"name": "read"},
                {"name": "write"},
            ],
        }
    ],
    betas=BETAS,
)

session = client.beta.sessions.create(
    agent={"type": "agent", "id": writer.id, "version": writer.version},
    environment_id=env.id,
    title="Brief: EV fast-charging unit economics",
    betas=BETAS,
)
print(f"Session {session.id}")
```

??? note "輸出"

    ```text
    Session sesn_011CakRYQjc4NMXdRy4qKZy5
    ```

## 3. 寫出 grader 做得了事的 rubric

`define_outcome` 事件給 session 兩樣東西：**description**（交付物的描述，writer 會讀）和 **rubric**（grader 會讀）。每次 writer 做完一輪，平台會開一個全新的 grader，用跟 writer 相同的模型和 tools，給它 rubric，讓它檢查成品。grader 回傳逐項的判定，有任何一項沒過，說明就直接回給 writer 做下一次修改。

rubric 是你影響 grader 的唯一槓桿，措辭決定 grader 到底有沒有真的檢查。預設的失敗模式是 grader 什麼都放行。如果 rubric 寫「檢查簡報有涵蓋 demand charges」，grader 可以快速掃過簡報，看到一段講 demand charges 的文字，寫一句確認它存在，完全不用打開任何來源。大部分的初稿就這樣過關，迴圈根本不會跑。如果 rubric 寫「打開簡報，找到 demand-charges 那一節，確認它給出 $/kW 的數字或佔營運成本的百分比」，grader 就得拿出證據。能抓到偽裝成 10-K 的新聞稿的，就是這種 grader。

每份 rubric 都值得做的幾件事：

| 原則 | 實際做法 |
|---|---|
| **每個項目都要能檢查** | 任務寫「named-operator economics」。rubric 把它釘死：來自 10-K 或 10-Q 的 GAAP 淨損，並引用 `sec.gov` 上的申報文件。rubric 永遠要比任務更具體。 |
| **讓 grader 賺到 `satisfied`** | 在 grader 放行任何東西前，要求具體證據（抓過的頁面、追蹤過的公式、`file:line` 參照）。grader 太嚴只會多花一輪，太鬆則是讓有問題的版本留在原地就結束迴圈。 |
| **描述目標，不描述步驟** | rubric 指定某個指令的話，指令不能用時會悄悄失敗，你在意的檢查根本沒跑。定義什麼算證明就好，grader 有 writer 的完整工具組，會自己找方法。 |
| **預想 writer 的捷徑** | 「不要用鏡像站、轉貼或搜尋摘要來佐證。」沒有這行，失效的來源會被換成爬蟲頁面，grader 還是放行。 |
| **規定回饋格式** | grader 的說明是 writer 唯一的訊號。要求先給一行計分板，再每個失敗項一條，寫清楚哪裡錯、該怎麼做。 |
| **告訴 grader 什麼可以忽略** | 沒有不該觸發的清單，grader 會在文風小毛病、既有問題、範圍蔓延上打轉。把界線外的東西寫清楚，並要它在提出每個發現前先自我檢查。 |

> **還沒有 rubric？** 把一份已知很好的成品範例交給 Claude，請它分析好在哪，再把分析轉成判斷標準。這個折衷做法通常贏過從空白頁開始寫標準。

下面是這份簡報的任務和 rubric。並排讀，注意 rubric 具體多少。它比任務多出細節的每個地方，都是 grader 真的能執行的檢查。


```python
TASK = """Write a brief on the unit economics of public DC fast charging in the United States.
The brief should cover:
  1. Capex range
  2. Demand charges
  3. Utilization breakeven
  4. Subsidy programs
  5. Named-operator economics
  6. A contrarian or skeptical source
  7. Hardware vs install cost split
"""


RUBRIC = """
You are reviewing a research brief at /mnt/session/outputs/brief.md against a coverage checklist and verifying its citations. The writer was told the seven topics to cover; this rubric defines what counts as sufficient coverage for each topic, and how to verify citations.

COVERAGE CHECKLIST. Each item has a specific area:
  1. Capex range: a dollar range for installed cost per DC fast-charging stall or station.
  2. Demand charges: quantified impact on opex (a $/kW figure or a % of operating cost).
  3. Utilization breakeven: a breakeven or target utilization threshold (% or kWh/day).
  4. Subsidy programs: NEVI or another public funding program, named.
  5. Named operator: the GAAP net income or net loss from a specific public charging operator's most recent 10-K or 10-Q, and the citation for it must be the SEC filing itself (sec.gov), not a press release, earnings-call recap, or news article.
  6. Contrarian source: at least one cited source whose thesis is that the economics are unfavorable or structurally challenged.
  7. Cost split: a hardware vs soft-cost (install, permitting, grid) breakdown or ratio.

CITATION CHECK. For every [n] entry in the Sources section:
  a. LIVE: Fetch the URL with web_fetch. Mark LIVE only if web_fetch returns the readable page directly. Mark DEAD if 404, parked, login-walled, paywalled, returns a bot-block/403, or renders only via JavaScript. Do NOT corroborate via mirrors, reposts, or search snippets; the cited URL itself must fetch.
  b. VERBATIM: Search the fetched page for the quoted string. Mark QUOTE_MATCH if the exact string appears (treat curly vs straight quotes as equivalent); NOT_FOUND otherwise.
  c. SUPPORTS CLAIM: Mark SUPPORTS_CLAIM if the quoted passage actually backs the claim it's cited on in the brief; UNSUPPORTED if it's tangential, contradicts the claim, or is just a general statement of fact.

OUTPUT FORMAT:

Line 1: Coverage N/7. Citations M/K verified.

Then, for each failed item in the coverage checklist, create a new bullet, name the item and say what specific bar it failed in one sentence max per bullet. For example: "Item 3 Utilization breakeven - MISSING. <what's missing>".

Then, for each failed citation, create a new bullet with the format: "[n] domain - REASON. <what's wrong and what to do>". One sentence max per bullet. For example: "[3] evgo.com - DEAD. The URL returns a 403 error and appears to be behind a bot block. No mirrors or reposts; the cited URL itself must fetch."
"""

client.beta.sessions.events.send(
    session.id,
    betas=BETAS,
    events=[
        {
            "type": "user.define_outcome",
            "description": TASK,
            "rubric": {"type": "text", "content": RUBRIC},
            "max_iterations": 5,
        },
    ],
)
```

??? note "輸出"

    ```text
    BetaManagedAgentsSendSessionEvents(data=[BetaManagedAgentsUserDefineOutcomeEvent(id='sevt_011CakRYTKNkXJN7eh4kRs1r', description='Write a brief on the unit economics of public DC fast charging in the United States.\nThe brief should cover:\n  1. Capex range\n  2. Demand charges\n  3. Utilization breakeven\n  4. Subsidy programs\n  5. Named-operator economics\n  6. A contrarian or skeptical source\n  7. Hardware vs install cost split\n', max_iterations=5, outcome_id='outc_011CakRYTKNkJ83CBexcz13e', processed_at=datetime.datetime(2026, 5, 6, 1, 10, 30, 512206, tzinfo=TzInfo(0)), rubric=BetaManagedAgentsTextRubric(content='\nYou are reviewing a research brief at /mnt/session/outputs/brief.md against a coverage checklist and verifying its citations. The writer was told the seven topics to cover; this rubric defines what counts as sufficient coverage for each topic, and how to verify citations.\n\nCOVERAGE CHECKLIST. Each item has a specific area:\n  1. Capex range: a dollar range for installed cost per DC fast-charging stall or station.\n  2. Demand charges: quantified impact on opex (a $/kW figure or a % of operating cost).\n  3. Utilization breakeven: a breakeven or target utilization threshold (% or kWh/day).\n  4. Subsidy programs: NEVI or another public funding program, named.\n  5. Named operator: the GAAP net income or net loss from a specific public charging operator\'s most recent 10-K or 10-Q, and the citation for it must be the SEC filing itself (sec.gov), not a press release, earnings-call recap, or news article.\n  6. Contrarian source: at least one cited source whose thesis is that the economics are unfavorable or structurally challenged.\n  7. Cost split: a hardware vs soft-cost (install, permitting, grid) breakdown or ratio.\n\nCITATION CHECK. For every [n] entry in the Sources section:\n  a. LIVE: Fetch the URL with web_fetch. Mark LIVE only if web_fetch returns the readable page directly. Mark DEAD if 404, parked, login-walled, paywalled, returns a bot-block/403, or renders only via JavaScript. Do NOT corroborate via mirrors, reposts, or search snippets; the cited URL itself must fetch.\n  b. VERBATIM: Search the fetched page for the quoted string. Mark QUOTE_MATCH if the exact string appears (treat curly vs straight quotes as equivalent); NOT_FOUND otherwise.\n  c. SUPPORTS CLAIM: Mark SUPPORTS_CLAIM if the quoted passage actually backs the claim it\'s cited on in the brief; UNSUPPORTED if it\'s tangential, contradicts the claim, or is just a general statement of fact.\n\nOUTPUT FORMAT: \n\nLine 1: Coverage N/7. Citations M/K verified.\n\nThen, for each failed item in the coverage checklist, create a new bullet, name the item and say what specific bar it failed in one sentence max per bullet. For example: "Item 3 Utilization breakeven - MISSING. <what\'s missing>".\n\nThen, for each failed citation, create a new bullet with the format: "[n] domain - REASON. <what\'s wrong and what to do>". One sentence max per bullet. For example: "[3] evgo.com - DEAD. The URL returns a 403 error and appears to be behind a bot block. No mirrors or reposts; the cited URL itself must fetch."\n', type='text'), type='user.define_outcome')])
    ```

上面這次呼叫的幾點說明：

- **description 和 rubric 各有任務。** description 告訴 writer 要做什麼，rubric 告訴 grader 怎麼檢查。兩者對成品的位置和格式要一致；如果互相矛盾（例如 description 要求 inline 輸出，rubric 卻去評 `/mnt/session/outputs/` 的檔案），迴圈會回傳 `failed`，而不是原地空轉。
- **`max_iterations` 預設是 3（最大 20）。** 這份 rubric 很嚴格、writer 需要空間，所以我們設成 5。如果每次執行都撞到上限，而且 grader 每次找到同類問題，代表 writer 無法根據回饋行動，你是在為不會收斂的迭代付錢。
- **inline rubric 和檔案 rubric。** 在 notebook 裡 inline 文字就夠。正式環境你會用 Files API 上傳一次 rubric，改傳 `rubric: {"type": "file", "file_id": ...}`，這樣能跨 session 重複使用，也能像程式碼一樣被 review。

**為什麼不直接把 rubric 放進 system prompt？** 可以，而且對 writer 瞄準目標有幫助。但知道標準的 writer 還是在替自己打分數。它相信自己通過就會說通過，不會回頭重抓一個已經引用過的 URL，也不會發現它記得的引文跟頁面上的有點不同。grader 沒得選，這些檢查它非做不可。它用全新的 context window 開始，手上只有 rubric 和成品，而且平台在它對每個項目給出判定之前，不會讓迴圈繼續。這種分離，不管 prompt 寫得多好，單一 prompt 都做不到。


## 4. 看 review 迴圈跑

我們串流事件，並在每個階段發生時呈現出來。writer 寫完一份草稿時印一個橫幅，每次評估之後顯示 grader 的回饋。

下面迴圈用的兩個顯示 helper：`banner` 畫一條帶標籤的分隔線，`render_feedback` 把 server 包在每則 grader 說明外面的制式文字拿掉。


```python
HR = "━" * 46


def banner(label, tag=""):
    print(f"\n{HR}\n{label}  {tag}".rstrip())


def render_feedback(fb: str):
    # Strip the server's per-criterion wrapper and trailer.
    s = re.sub(
        r"^An independent grader found.*?:\n\n- .*?\((?:partially |not )?met\): ",
        "",
        fb,
        count=1,
        flags=re.S,
    )
    s = re.sub(r"\n\nPlease revise your work.*$", "", s, flags=re.S)
    print(s)
```

```python
TERMINAL = {"satisfied", "max_iterations_reached", "failed", "interrupted"}
t0, res, iters = time.time(), None, 0
n_search, last_len = 0, 0

with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "agent.tool_use":
            if ev.name in ("web_search", "web_fetch"):
                n_search += 1
            if ev.name == "write" and ev.input["file_path"].endswith("brief.md"):
                last_len = len(ev.input["content"])
        elif ev.type == "span.outcome_evaluation_start":
            banner("writer · " + ("draft" if iters == 0 else f"revision {iters}"))
            print(f"searched/fetched {n_search}× · wrote brief.md ({last_len:,} chars)")
            n_search = 0
        elif ev.type == "span.outcome_evaluation_end":
            res = ev.result
            banner(
                f"grader · pass {iters}",
                "✓ satisfied" if res == "satisfied" else "⟳ needs_revision",
            )
            render_feedback(ev.explanation)
            iters += 1
            if res in TERMINAL:
                break

m, s = divmod(int(time.time() - t0), 60)
print(f"\ndone: {res} after {iters} pass{'es' if iters != 1 else ''} · {m}m {s:02d}s")
```

??? note "輸出"

    ```text

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    writer · draft
    searched/fetched 18× · wrote brief.md (7,607 chars)

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    grader · pass 0  ⟳ needs_revision
    The brief covers 5 of 7 required topics adequately. Item 2 (Demand charges) fails the quantification bar: the brief describes demand charges qualitatively as the 'single largest operational wildcard' but never states a $/kW figure (McKinsey's footnote of $20/kW is never quoted in the text) or a % of operating cost. Item 5 (Named operator) fails the citation requirement: EVgo's Q1 2024 net loss of $28.2M is cited to evchargingstations.com [6], a third-party news article, not an SEC filing from sec.gov as the rubric explicitly requires. All 6 citations are LIVE, and all 6 quoted strings match the fetched pages and support the claims they are attached to — but [6] is the wrong source type for the Named Operator criterion.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    writer · revision 1
    searched/fetched 6× · wrote brief.md (7,989 chars)

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    grader · pass 1  ⟳ needs_revision
    Six of seven coverage items are fully met: (1) capex range with hardware $45K–$100K and install $40K–$150K per charger; (2) demand charges quantified at $20/kW and $9,600/month for a 480kW station; (3) utilization breakeven at 20% vs. 7.5% national average; (4) NEVI Formula Program named with $5B allocation; (6) contrarian source—Great Plains Institute 'nearly all DCFC scenarios lose money' fully cited and live; (7) hardware vs. install cost split clearly broken out. All six citations fetch live, every quoted string matches exactly, and all citations support the claims they are attached to (6/6 verified). Item 5 (Named operator) fails the rubric's specific requirement: the rubric demands GAAP net income/loss from a 10-K or 10-Q, and the citation must be the SEC filing itself—not a press release. The brief cites EVgo's FY2024 GAAP net loss of $126.7M, but the citation [6] is an 8-K EX-99.1 (earnings press release exhibit), explicitly labelled '(8-K EX-99.1)' in the Sources section. The rubric specifically excludes press releases, and an 8-K EX-99.1 is precisely that—a press release filed with the SEC—not a 10-K or 10-Q annual/quarterly report.

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    writer · revision 2
    searched/fetched 7× · wrote brief.md (7,989 chars)

    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    grader · pass 2  ✓ satisfied
    All 7 coverage items are fully met: (1) Capex range gives hardware $45K-$100K+ and installation $40K-$150K+ per charger, plus NEVI average $915,420/station. (2) Demand charges quantified at $20/kW (explicit $/kW figure) with $9,600/month example. (3) Utilization breakeven at 20% or $0.53/kWh threshold explicitly modeled. (4) NEVI and IRA Section 30C named as subsidy programs. (5) EVgo GAAP net loss of $126.7M for FY2024 cited from the SEC filing itself (sec.gov XBRL R4.htm), not a press release. (6) Great Plains Institute contrarian source cited with thesis that 'nearly all DCFC scenarios lose money.' (7) Hardware vs. install cost split explicitly broken out. All 6 citations are LIVE (URLs return readable pages), all quoted strings appear verbatim in the fetched pages, and all support the claims they are cited on.

    done: satisfied after 3 passes · 12m 56s
    ```

### 剛剛發生了什麼

迴圈跑了三次評分。

第一份草稿涵蓋了七項中的五項。grader 因為兩個缺漏退回：demand charges 只有質性描述、沒有每 kW 的金額，而 named-operator 那節引用的是第三方新聞文章，不是 SEC 申報文件。writer 補上 $20/kW 的數字，並去 sec.gov 找 EVgo FY2024 的淨損。

第二次評分過了七項中的六項。writer 引用的那份 sec.gov 文件是 8-K Exhibit 99.1，也就是申報時附上的財報新聞稿，不是 rubric 要求的 10-K 或 10-Q。grader 讀了 URL，辨認出它是新聞稿附件，就是依這個差別退回。第三次 writer 在 EDGAR 找到 EVgo 真正的 10-K，grader 放行：七項全部涵蓋、6/6 引用有效、引文吻合且確實支持論點。

兩次退回都是因為 rubric 畫了 grader 檢查得到的線。「一個 $/kW 數字或佔營運成本的百分比」和「SEC 申報文件本身，不是新聞稿」是 rubric 作者做的決定；任務本身（「涵蓋 demand charges」、「named-operator economics」）兩個都會放行。第二次退回值得細讀。writer 找到一個 `sec.gov` 的 URL，表面上滿足任務，grader 還是退回，因為 rubric 區分了 8-K 新聞稿附件和 10-K。沒有這個區分，迴圈會提早一輪結束，簡報也比較差。

**注意**，上面的 trace 來自原始 cookbook 的執行。你自己跑的話，結果很可能不同。

## 5. 讀最終簡報

最後，把 writer 產出的最新版 `brief.md` 抓下來，看它涵蓋什麼、引用什麼。想讀完整內文的話，直接印 `content`。

```python
# Reconstruct the final brief from the event log: full content on `write`,
# then apply each `edit` (old_string -> new_string) in order.
content = ""
for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS):
    if ev.type != "agent.tool_use" or "brief.md" not in str(ev.input.get("file_path", "")):
        continue
    if ev.name == "write":
        content = ev.input["content"]
    elif ev.name == "edit":
        content = content.replace(ev.input["old_string"], ev.input["new_string"], 1)

# Show the structure and sources rather than the full prose.
for line in content.splitlines():
    if line.startswith(("#", "[")):
        print(line)
```

??? note "輸出"

    ```text
    # Unit Economics of Public DC Fast Charging in the United States
    ## 1. Capex Range
    ## 2. Demand Charges
    ## 3. Utilization Breakeven
    ## 4. Subsidy Programs
    ## 5. Named-Operator Economics
    ## 6. Contrarian / Skeptical View
    ## 7. Hardware vs. Installation Cost Split
    ## Sources
    [1] "A 150 to 350kW DCFC charging unit can cost anywhere from $45,000 to over $100,000, and installation costs can range from $40,000 to over $150,000." - Can public EV fast-charging stations be profitable in the United States? - https://www.mckinsey.com/features/mckinsey-center-for-future-mobility/our-insights/can-public-ev-fast-charging-stations-be-profitable-in-the-united-states
    [2] "Waiving demand charges for fast chargers will shift costs to all ratepayers, including non-EV drivers." - Fast charging, high costs: Eliminating demand charges won't solve the problem - https://www.utilitydive.com/news/eliminating-demand-charges-wont-solve-EV-station-problems/689395/
    [3] "the average total NEVI project cost is $915,420. The median total cost is $802,267" - NEVI DC Fast Charging Station Total Project Cost Averages $915,000 - https://www.paren.app/blog/nevi-dc-fast-charging-station-total-project-cost-averages-915-000
    [4] "Today's economics and the average electric utility rates mean that nearly all DCFC scenarios lose money" - 'Nearly all' high voltage EV charging stations lose money: Report - https://www.utilitydive.com/news/nearly-all-high-voltage-ev-charging-stations-lose-money-report/561026/
    [5] "apportions a total of $5 billion to States, D.C., and Puerto Rico over five years, from Fiscal Year 2022 through 2026" - Federal Funding Programs - https://www.transportation.gov/rural/ev/toolkit/ev-infrastructure-funding-and-financing/federal-funding-programs
    [6] "Consolidated Statements of Operations - USD ($)$ in Thousands | 12 Months Ended Dec. 31, 2024 | Dec. 31, 2023" - EVgo Inc. Form 10-K, Consolidated Statements of Operations (XBRL), Period: 2024-12-31 - https://www.sec.gov/Archives/edgar/data/1821159/000155837025002400/R4.htm
    ```

## 你學到了什麼

- **能寫下「好」長什麼樣的時候，Outcomes 才適用。** 注重細節和要求面面俱到的任務最適合；主觀品質的任務只要 rubric 把標準釘住，也可以。
- **rubric 必須讓 grader 拿出證據。** 否則它會放行看到的任何東西。
- **grader 是獨立且無狀態的。** 它在自己的 context window 裡跑，writer 說服不了它，而且每次迭代都是全新的 grader 重新檢查整份成品。
- **一次一個 outcome，但可以串接。** 迴圈結束後，session 又回到對話狀態，下一個 `user.define_outcome` 會開始新的迴圈。

更多資料請看 [Outcomes 文件](https://platform.claude.com/docs/en/managed-agents/define-outcomes)。


## 重點整理

- Outcomes 的價值是把「檢查」交給一個獨立的 grader，writer 自己評自己的成品不會做的事（重抓 URL、核對引文），grader 一定得做。
- rubric 的具體程度決定 grader 有沒有真的在檢查，寫得比任務更具體，才抓得到「看起來符合其實不符合」的情況。
- 要求 grader 拿出證據，並規定回饋格式，writer 才拿得到能行動的訊號。
- `max_iterations` 是成本上限，如果一直撞到上限，通常是 writer 無法根據回饋行動。
- description 和 rubric 要對成品位置和格式一致，否則迴圈會直接 `failed`。

## 練習

1. 把 `define_outcome` 的 `max_iterations` 從 5 改成 2，重跑一次，看看 grader 在上限內能不能把簡報修到通過，沒通過時事件長什麼樣。
2. 在 rubric 加一條新標準，例如「每個來源的引文不得超過 25 個字」，並寫清楚 grader 要怎麼檢查，觀察 grader 的回饋有沒有出現這一項。
3. 把 rubric 裡「不要用鏡像站、轉貼或搜尋摘要來佐證」那行拿掉，重跑並比較 writer 有沒有用比較偷懶的來源通過。
