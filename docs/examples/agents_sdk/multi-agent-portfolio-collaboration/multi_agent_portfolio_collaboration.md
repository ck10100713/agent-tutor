---
translated: true
source: examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration.ipynb
---

# 用 OpenAI Agents SDK 做多 Agent 投資組合協作

> 原文：[examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/multi-agent-portfolio-collaboration/multi_agent_portfolio_collaboration.ipynb)

用 OpenAI Agents SDK 建立多 agent 投資組合分析 workflow 的 Cookbook。

## 這篇在做什麼

這篇用 OpenAI Agents SDK 做一個投資研究系統：Portfolio Manager agent 當總指揮，把總經、基本面、量化三位專家 agent 當成 tool 來呼叫，最後整合成一份投資備忘錄。過程中會用到自訂 Python function、託管 tool（Code Interpreter、WebSearch）和外部 MCP server。

## 學完你會

- 用「agent as a tool」模式，讓一個中央 agent 把其他 agent 當 tool 呼叫並整合結果。
- 在同一個 workflow 裡混用 SDK 支援的三種 tool：自訂 function、託管 tool 和 MCP server。
- 用 `parallel_tool_calls=True` 讓多個專家 agent 同時跑，並用 OpenAI Traces 觀察每一步。

## 開跑前

- 需要 `OPENAI_API_KEY`。
- 需要 `FRED_API_KEY`（拿 FRED 經濟數據用，免費申請）。
- 跑一次完整 workflow 可能要 10 分鐘，會產生 OpenAI API 費用。

## 簡介

*這份指南寫給已經熟悉 OpenAI 模型和 LLM agent、想看看怎麼編排一組 agent 來處理真實又複雜的任務的讀者。*

**你會學到什麼**

這個 notebook 會教你用 OpenAI Agents SDK 設計並實作一套複雜的多 agent 協作系統。具體來說，你會看到：
- 怎麼建立一個 workflow，讓多位專家 agent（Macro、Fundamental、Quantitative）在 Portfolio Manager agent 之下協作，解決一個有挑戰性的投資研究問題。
- 使用「agents as a tool」的做法，由一個中央 agent 負責編排，並把其他 agent 當成 tool 來處理特定子任務。
- 在同一個整合的 workflow 裡用到 SDK 支援的所有主要 tool 類型（自訂 Python function、像 Code Interpreter 和 WebSearch 這樣的託管 tool，以及外部 MCP server）。
- 在 agent 模式中落實模組化、平行執行和可觀測性的最佳實務。

**為什麼重要**

「agents as a tool」是建立透明、可稽核、可擴充的多 agent 協作的有力做法。這個範例示範如何用 OpenAI Agents SDK 結合深度專業分工、平行執行和穩健的編排。

讀完這份指南，你會有一份清楚的藍圖，可以為研究、分析或任何受益於專家協作的複雜任務，建立自己的多 agent workflow。



---

## 目錄

1. [什麼是多 Agent 協作？](#what-is-multi-agent-collaboration)
2. [協作模式：Handoff 與 Agent-as-Tool](#collaboration-patterns-handoff-vs-agent-as-tool)
3. [架構概覽](#architecture-overview)
4. [支援的 Tool 類型](#supported-tool-types)
5. [環境設定](#setup)
6. [執行 Workflow](#running-the-workflow)
7. [Head Portfolio Manager (PM) Agent](#the-head-portfolio-manager-pm-agent)
8. [拆解 Head Portfolio Manager Agent](#breaking-down-the-head-portfolio-manager-agent)
9. [輸出範例](#example-output)
10. [建構 Agent 的最佳實務](#best-practices-when-building-agents)
11. [延伸閱讀與最佳實務](#further-reading--best-practices)



---

## 什麼是多 Agent 協作？

**多 agent 協作**指的是多個自主 agent（LLM「節點」）互相協調，達成單一 agent 很難處理的總體目標。不是塞一個巨大的 prompt，而是每個 agent 負責一個特定子任務或專業領域，再由一層編排邏輯把這些 agent「節點」串成一個連貫的 workflow。這種做法適合複雜的系統，例如財務分析可以拆成總體經濟分析、公司基本面分析和量化訊號分析，各由一位專家 agent 處理。這些 agent 共享資訊，結果合併後產出最終成果。



### 協作模式：Handoff 與 Agent-as-Tool

OpenAI Agents SDK 支援多種讓 agent 一起工作的模式：

- **Handoff 協作：** 一個 agent 可以在問題處理到一半時，把控制權 _handoff_ 給另一個 agent。在 handoff 架構中，每個 agent 都知道其他 agent 的存在，可以自己決定什麼時候交給更適合的 agent。這對開放式或對話式的 workflow 很有彈性，但比較難維持對整個任務的全局視野。[詳見 SDK 文件。](https://openai.github.io/openai-agents-python/handoffs/)

- **Agent as a Tool：** 這種做法由一個 agent（通常是中央規劃者或經理）**把其他 agent 當成 tool 來呼叫**。子 agent 不會接手對話；主 agent 為特定子任務呼叫它們，再把結果整合進來。這個模型只有一條控制主線（主 agent 編排一切），通常讓協調更簡單。**這個 repo 採用 agent-as-tool 模型：** Portfolio Manager agent 一直掌控全局，需要專業時就把其他專家 agent 當 tool 使用。這個選擇讓整體推理保持透明，也能讓子任務平行執行，很適合複雜的分析。

更多關於這些協作模式，請見 [OpenAI Agents SDK 文件](https://openai.github.io/openai-agents-python/multi_agent/)。

---

## 架構概覽

我們的系統採用**中心輻射式設計**。**Portfolio Manager agent** 是中心（中央協調者），**專家 agent** 是輻條。使用者的問題（例如「預計降息會怎麼影響我持有的 GOOGL？」）會先交給 Portfolio Manager。Portfolio Manager agent 的 prompt 要它拆解問題，並委派給合適的專家 agent。它把每位專家當成可呼叫的 tool，用來處理分析的對應部分。三位專家都回報給 Portfolio Manager，再由它整合出給使用者的最終答案。

![Multi-Agent Investment Report Workflow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_agent_architecture.png)



---

## 支援的 Tool 類型

Agents SDK 的一大優點，是定義 agent 可用的 **tool** 很有彈性。Tool 可以是簡單的 Python function，也可以是外部服務。這個專案用到：

- **MCP (Model Context Protocol) Server：** 用標準化的方式把 agent 連到外部 tool 和資料來源。這個專案用一個本機 MCP server 提供 Yahoo Finance 資料（見 `mcp/yahoo_finance_server.py`）。[了解更多：OpenAI MCP 文件](https://openai.github.io/openai-agents-python/mcp/) | [MCP Spec](https://modelcontextprotocol.io/)

- **OpenAI 託管 Tool：** 託管 tool 是 OpenAI 提供的內建、託管式 tool，不需要自己實作。它們開箱即用就有強大的能力，例如 **Code Interpreter**（做量化／統計分析）和 **WebSearch**（取得最新新聞和資料）。這些 tool 很容易整合，由 OpenAI 維護，讓 agent 不用額外設定就能執行程式碼、即時擷取資訊這類進階動作。

- **自訂 Tool：** 自訂 tool 就是任何你定義並註冊成 agent tool 的 Python function。Agents SDK 讓這件事很簡單：只要裝飾你的 function，SDK 就會自動抽出它的名稱、docstring 和 input schema。這很適合領域專屬的邏輯、資料存取或 workflow 擴充。 
  在我們的專案裡，自訂 tool 用來存取 FRED 經濟數據（[見 FRED API](https://fred.stlouisfed.org/docs/api/api_key.html)）和做檔案系統操作。

自訂 tool 讓你完全有彈性，把 agent 的能力延伸到內建或託管 tool 之外。[見 SDK 文件的 function tool 說明。](https://openai.github.io/openai-agents-python/tools/#function-tools)

> **想加更多 tool？** SDK 支援很多種 tool 類型，包括 web search、file search、程式碼執行等等。[完整的支援 tool 清單請見 SDK 文件。](https://openai.github.io/openai-agents-python/tools/)

---

## 環境設定

```python
# Install required dependencies
!pip install -r requirements.txt
```

**執行 workflow 之前，先設定環境變數：**
- `OPENAI_API_KEY`（用於 OpenAI 存取）
- `FRED_API_KEY`（用於 FRED 經濟數據，見 [FRED API key 申請說明](https://fred.stlouisfed.org/docs/api/api_key.html)）

```python
import os

missing = []
if not os.environ.get('OPENAI_API_KEY'):
    missing.append('OPENAI_API_KEY')
if not os.environ.get('FRED_API_KEY'):
    missing.append('FRED_API_KEY')

if missing:
    print(f"Missing environment variable(s): {', '.join(missing)}. Please set them before running the workflow.")
else:
    print("All required API keys are set.")
```

---

## 執行 Workflow 

問題可以改成任何你想問的，但請保留日期欄位以提高準確度！

<div style="border-left: 4px solidrgb(0, 0, 0); padding: 0.5em; background:rgb(255, 229, 229);">
<strong>免責聲明：</strong> 這個範例僅供教學用途。做任何投資決定之前，請諮詢合格的財務專業人士。
</div>


Workflow 由把使用者請求送給 Head Portfolio Manager (PM) agent 開始。PM agent 編排整個流程，視需要委派給專家 agent 和 tool。你可以用 OpenAI Traces 即時監看 workflow，它能詳細呈現每個 agent 和 tool 的呼叫。

把下面程式碼裡的 `question` 改成任何你想問的，但請保留日期欄位以提高準確度！

<div style="border-left: 4px solid #f39c12; padding: 0.5em; background: #fffbe6;">
<strong>注意：</strong> 依任務複雜度而定，這個請求最多可能要跑 10 分鐘。
</div>


```python
import datetime
import json
import os
from pathlib import Path
from contextlib import AsyncExitStack
from agents import Runner, add_trace_processor, trace
from agents.tracing.processors import BatchTraceProcessor
from utils import FileSpanExporter, output_file
from investment_agents.config import build_investment_agents
import asyncio

add_trace_processor(BatchTraceProcessor(FileSpanExporter()))

async def run_workflow():
    if "OPENAI_API_KEY" not in os.environ:
        raise EnvironmentError("OPENAI_API_KEY not set — set it as an environment variable before running.")

    today_str = datetime.date.today().strftime("%B %d, %Y")
    question = (
        f"Today is {today_str}. "
        "How would the planned interest rate reduction effect my holdings in GOOGL if they were to happen?"
        "Considering all the factors effecting its price right now (Macro, Technical, Fundamental, etc.), what is a realistic price target by the end of the year?"
    )
    bundle = build_investment_agents()

    async with AsyncExitStack() as stack:
        for agent in [getattr(bundle, "fundamental", None), getattr(bundle, "quant", None)]:
            if agent is None:
                continue
            for server in getattr(agent, "mcp_servers", []):
                await server.connect()
                await stack.enter_async_context(server)

        print("Running multi-agent workflow with tracing enabled...\n")
        with trace(
            "Investment Research Workflow",
            metadata={"question": question[:512]}
        ) as workflow_trace:
            print(
                f"\n🔗 View the trace in the OpenAI console: "
                f"https://platform.openai.com/traces/trace?trace_id={workflow_trace.trace_id}\n"
            )

            response = None
            try:
                response = await asyncio.wait_for(
                    Runner.run(bundle.head_pm, question, max_turns=40),
                    timeout=1200
                )
            except asyncio.TimeoutError:
                print("\n❌ Workflow timed out after 20 minutes.")

            report_path = None
            try:
                if hasattr(response, 'final_output'):
                    output = response.final_output
                    if isinstance(output, str):
                        data = json.loads(output)
                        if isinstance(data, dict) and 'file' in data:
                            report_path = output_file(data['file'])
            except Exception as e:
                print(f"Could not parse investment report path: {e}")

            print(f"Workflow Completed Response from Agent: {response.final_output if hasattr(response, 'final_output') else response}, investment report created: {report_path if report_path else '[unknown]'}")

# In a Jupyter notebook cell, run:
await run_workflow()
```


---

## 拆解 Head Portfolio Manager Agent

Head Portfolio Manager (PM) agent 是整個 workflow 的編排者。它協調一組專家 agent，各自專注在不同的專業領域。這個設計是刻意的：讓單一 agent 扛下所有可能的職責，會得到膚淺、籠統的輸出，也讓系統難以長期維護和改進。

### 為什麼這樣設計？
把問題拆給各有明確角色的專家 agent，你會得到：

- **更深入、更高品質的研究：** 每個 agent 可以專注在自己的領域，用適合的 tool 和 prompt 做事。PM agent 再把這些觀點整合起來，得到更細緻、更穩健的答案。

- **模組化與清晰：** 你可以更新、測試或改進一個 agent，而不影響其他 agent。這讓系統隨著需求演進更容易維護和擴充。

- **平行化帶來更快的結果：** 彼此獨立的 agent 可以同時工作，大幅縮短完成複雜多面向分析的時間。

- **一致性與可稽核：** 結構化、由 prompt 驅動的 workflow，確保每次執行都遵循最佳實務、容易除錯，並產出可信、可檢視的結果。

這個做法適合任何需要深度、專業分工和可靠性的應用，不論你在做研究助理、決策輔助工具，或是任何受益於專家協作與編排的系統。

**實際上怎麼實作：**
- 每位專家 agent（Fundamental、Macro、Quantitative）都用 SDK 的 `function_tool` decorator 包成可呼叫的 tool，並給自訂的名稱和描述。這讓 PM agent 的 toolset 明確又對 LLM 友善。

- Head PM agent 用 `run_all_specialists_parallel` tool 同時呼叫三位專家，靠 `parallel_tool_calls=True` 取得最高的速度和效率。

- Agent 的 prompt 從一個 markdown 檔（`pm_base.md`）載入，裡面不只寫了公司的投資理念，也有詳細的 tool 使用規則和一步一步的 workflow。這確保每次執行都一致、可稽核，並符合最佳實務。

- 收集並審閱專家的輸出之後，PM agent 用專門的 memo editor tool 組裝、排版並定稿投資報告。這種職責分離讓 workflow 保持模組化，也容易擴充。

- 系統設計成可擴充：你可以新增專家 agent、更換 tool 或更新 prompt，而不會破壞整體的編排邏輯。所有 tool call、agent 決策和輸出都記錄在 OpenAI Traces，完全透明、方便除錯。

這些實作選擇直接支撐了上面的好處，讓深入、模組化又可靠的多 agent 研究 workflow 容易維護、稽核和改進。

### Head Portfolio Manager Agent：程式碼

```python
from agents import Agent, ModelSettings, function_tool
from utils import load_prompt, DISCLAIMER

def build_head_pm_agent(fundamental, macro, quant, memo_edit_tool):
    def make_agent_tool(agent, name, description):
        @function_tool(name_override=name, description_override=description)
        async def agent_tool(input):
            return await specialist_analysis_func(agent, input)
        return agent_tool
    fundamental_tool = make_agent_tool(fundamental, "fundamental_analysis", "Generate the Fundamental Analysis section.")
    macro_tool = make_agent_tool(macro, "macro_analysis", "Generate the Macro Environment section.")
    quant_tool = make_agent_tool(quant, "quantitative_analysis", "Generate the Quantitative Analysis section.")

    @function_tool(name_override="run_all_specialists_parallel", description_override="Run all three specialist analyses (fundamental, macro, quant) in parallel and return their results as a dict.")
    async def run_all_specialists_tool(fundamental_input, macro_input, quant_input):
        return await run_all_specialists_parallel(
            fundamental, macro, quant,
            fundamental_input, macro_input, quant_input
        )

    return Agent(
        name="Head Portfolio Manager Agent",
        instructions=(load_prompt("pm_base.md") + DISCLAIMER),
        model="gpt-4.1",
        tools=[fundamental_tool, macro_tool, quant_tool, memo_edit_tool, run_all_specialists_tool],
        model_settings=ModelSettings(parallel_tool_calls=True, tool_choice="auto", temperature=0)
    )
    ```

### Head PM 的 System Prompt：落實最佳實務

PM agent 的 system prompt（見 `prompts/pm_base.md`）是整個 workflow 的核心。它寫進了：
- 公司的理念（原創性、風險意識、挑戰共識）
- 明確的 tool 使用規則（什麼時候用平行 tool、input 怎麼組織）
- 完整的多步驟 workflow（判斷任務類型、提供指引、審閱輸出、組裝備忘錄、處理缺漏資料）

這份 prompt 確保每次執行都：
- **一致：** 每次都遵循同樣的高標準和流程。
- **可稽核：** 每個步驟、tool call 和決策都看得到 trace。
- **高品質：** 輸出具原創性、有風險意識，並經過嚴格審閱。

```python
# Render the actual system prompt used by the Head Portfolio Manager agent
from pathlib import Path
from IPython.display import Markdown, display

pm_prompt_path = Path("prompts/pm_base.md")
if pm_prompt_path.exists():
    with pm_prompt_path.open("r", encoding="utf-8") as f:
        content = f.read()
    display(Markdown(content))
else:
    print("System prompt not found at prompts/pm_base.md")
```

---

## 輸出範例

這是透過這個 workflow 產生的投資報告範例。你的輸出會寫到該目錄下的 `outputs` 資料夾。 

<details>
<summary>點擊展開投資備忘錄</summary>

# 投資備忘錄：Alphabet Inc. (GOOGL) – 預計降息的影響（2025 年 5 月）

## 摘要

Alphabet Inc. (GOOGL) 目前股價為 \$171.42，市值 \$1.88 兆，本益比 16.91。投資論點是溫和偏多：聯準會預計降息是小幅利多，但不是 GOOGL 股價走勢的主要推手。最原創、最有差異化的洞見（完全符合我們公司的願景）是：GOOGL 對利率的直接敏感度不高（與 10 年期殖利率的最高週相關係數約 0.29），真正的風險報酬取決於 AI 驅動的成長能否持續、類股輪動和監管逆風。這個論點有穩健的技術面、強勁的基本面和壓倒性正面的分析師情緒支撐，但也受限於 AI 熱度消退，或總經／監管衝擊出現的風險。共識觀點有證據支持：GOOGL 的業務仍具韌性，但另一種觀點，也就是降息未能刺激科技股、或類股輪動限制報酬，不應被忽略。主要風險包括監管行動、總經不確定性，以及 AI 敘事轉向的可能。最好情況下，GOOGL 在 2025 年底可能達到 \$200–\$210；最壞情況下，回測 \$160–\$170 是可能的。這份備忘錄著重情境規劃、原創的量化分析，以及對共識與相反觀點的批判性評估，體現了公司的願景。

## 基本面觀點

Alphabet 的核心業務由數位廣告（Google Search、YouTube）的主導地位，以及成長中的雲端與 AI 業務驅動。最新一季（2025 年第一季）營收為 \$902 億、淨利 \$345 億、EPS \$2.81，淨利率 38.3%。過去一年利潤率有所改善，公司的規模以及在 AI 與雲端的領先地位提供了持久的護城河。不過，近期分析師目標價已下修（Bernstein：\$165，UBS：\$209，Wolfe：\$210），反映出對監管和總經風險的謹慎。共識觀點是合理的：Alphabet 的財務實力和創新能力很明顯，但監管審查和總經逆風（例如景氣下滑時廣告預算減少）是真實的風險。最原創的洞見是公司適應和創新的能力，可能抵銷部分風險。分析以證據為基礎，近幾季的資料顯示利潤率穩定或改善：

| Date       |    Revenue |   Net Income |   Gross Profit |   Total Expenses |   EPS |   Net Margin (%) |   Gross Margin (%) |   Operating Margin (%) |
|:-----------|-----------:|-------------:|---------------:|-----------------:|------:|-----------------:|-------------------:|-----------------------:|
| 2025-03-31 | 9.0234e+10 |   3.454e+10  |     5.3873e+10 |       5.9628e+10 |  2.81 |          38.28 |            59.70 |                33.92 |
| 2024-12-31 | 9.6469e+10 |   2.6536e+10 |     5.5856e+10 |       6.5497e+10 |  2.15 |          27.51 |            57.90 |                32.11 |
| 2024-09-30 | 8.8268e+10 |   2.6301e+10 |     5.1794e+10 |       5.9747e+10 |  2.12 |          29.80 |            58.68 |                32.31 |
| 2024-06-30 | 8.4742e+10 |   2.3619e+10 |     4.9235e+10 |       5.7317e+10 |  1.89 |          27.87 |            58.10 |                32.36 |
| 2024-03-31 | 8.0539e+10 |   2.3662e+10 |     4.6827e+10 |       5.5067e+10 |  1.89 |          29.38 |            58.14 |                31.63 |

近期分析師情緒壓倒性偏正面，目前有 56 個買進、12 個持有、0 個賣出建議：

| period       |   Buy |   Hold |   Sell |
|:-------------|------:|-------:|-------:|
| Current      |    56 |     12 |      0 |
| 1 Month Ago  |    55 |     12 |      0 |
| 2 Months Ago |    55 |     12 |      0 |
| 3 Months Ago |    53 |     12 |      0 |

基本面觀點符合公司願景，因為它專注於證據和情境規劃，而不是單純跟隨共識。如果分析沒有考慮監管或總經衝擊的影響，就會偏離公司願景，但這裡已經處理了。

## 總經觀點

總體經濟環境好壞參半。美國實質 GDP 持續擴張（\$23.5 兆，2025 年第一季），失業率低（4.2%），通膨仍偏高（CPI：320.3）。聯準會把利率維持在 4.25–4.50%，態度耐心，並關注不斷演變的風險。美元強勢（DXY：123.4），近期的關稅帶來不確定性。投資人正從美國科技股輪動到亞洲股市，反映出對高估值的擔憂和對海外更好成長前景的期待。共識的總經看法是降息將支撐科技股估值，但我們公司願景所支持的另一種觀點是，類股輪動和貿易政策可能抵銷這些好處。極端風險情境包括降息支撐 GOOGL 的基本情境（目標價 \$180–\$190），以及貿易緊張或類股輪動限制報酬的下行情境。分析以證據為基礎，使用 FRED 資料和近期政策聲明，並明確考慮最佳與最差情境。總經觀點因挑戰共識並為多種結果做規劃，完全符合公司願景。

## 量化觀點

量化分析確認 GOOGL 對利率的直接敏感度不高。與 10 年期公債殖利率的平均週相關係數是 0.29，與聯邦基金利率則是 0.05，顯示利率變動不是 GOOGL 報酬的主要驅動力。技術面穩健：GOOGL 在主要均線之上，動能為正，波動度適中。情境分析顯示降息是小幅利多，但如果這個走勢已經被反映在價格裡，或技術面破壞，回檔 5–10% 是可能的。分析師情緒非常正面，基本面（營收、利潤率）正在改善。量化摘要統計：

| Metric                                  |     Value |
|:----------------------------------------|----------:|
| Mean daily corr (FEDFUNDS, GOOGL)       | 0.05 |
| Mean daily reg slope (FEDFUNDS, GOOGL)  | 0.02 |
| Mean daily corr (DGS10, GOOGL)          | 0.13 |
| Mean daily reg slope (DGS10, GOOGL)     | 0.05 |
| Mean weekly corr (FEDFUNDS, GOOGL)      | 0.05 |
| Mean weekly reg slope (FEDFUNDS, GOOGL) | 0.03 |
| Mean weekly corr (DGS10, GOOGL)         | 0.29 |
| Mean weekly reg slope (DGS10, GOOGL)    | 0.09 |

主要圖表：

![GOOGL Daily Returns](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_googl_daily_returns.png)
![GOOGL Moving Averages](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_googl_moving_averages.png)
![GOOGL RSI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_googl_rsi.png)
![GOOGL Rolling Volatility](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_googl_rolling_volatility.png)
![Cumulative Return Comparison](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_cumulative_return_comparison.png)
![Rolling Volatility Comparison](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_rolling_volatility_comparison.png)
![Rolling Corr/Reg Daily Fed Funds](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_rolling_corr_reg_daily_fedfunds.png)
![Rolling Corr/Reg Daily 10Y](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_rolling_corr_reg_daily_dgs10.png)
![Rolling Corr/Reg Weekly Fed Funds](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_rolling_corr_reg_weekly_fedfunds.png)
![Rolling Corr/Reg Weekly 10Y](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_rolling_corr_reg_weekly_dgs10.png)
![GOOGL Quarterly Trends](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_GOOGL_quarterly_trends.png)
![GOOGL Quarterly Margins](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_GOOGL_quarterly_margins.png)
![GOOGL Analyst Recommendations Trend](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_collab_GOOGL_analyst_recommendations_trend.png)

量化觀點的原創之處在於聚焦情境分析和不高的利率敏感度，並因為不單純跟隨共識而符合公司願景。限制包括疫情後的資料窗口較短，以及 GOOGL 的價格受利率以外的多重因素（AI、廣告市場、監管）驅動。

## Portfolio Manager 觀點

PM 的整合結論是，三個專家的段落都收斂在溫和偏多的展望，2025 年底合理的目標價為 \$190–\$210。最原創的洞見是 GOOGL 的直接利率敏感度不高，真正的風險是 AI 驅動的成長能否持續，還是類股輪動和監管逆風會限制報酬。量化段落強調了穩健的技術面和情緒，但也指出下行情境中回測 \$160–\$170 的風險。基本面和總經段落強調監控監管與貿易政策的重要性。如果對大型科技股低配，現在是合理的進場點，但部位大小應反映類股輪動或總經失望的風險。另一種觀點，也就是降息未能刺激科技股或 AI 敘事轉向，不應被忽略。部位大小和風險管理是關鍵，完全符合公司對情境規劃和差異化洞見的願景。

## 建議與問題的答案

建議是維持或小幅增加 GOOGL 的曝險，尤其是對大型科技股低配的情況，基本情境下 2025 年底目標價為 \$200–\$210。這體現了公司願景，著重原創、以證據為基礎的情境分析，而不是單純跟隨共識。這個建議有穩健的基本面、正面的技術面和強勁的分析師情緒支撐，但也受限於類股輪動、監管行動或 AI 敘事轉向的風險。如果這些風險成真，回測 \$160–\$170 是可能的。部位大小和風險管理應反映這些情境。這個做法有差異化、以證據為導向，且完全符合公司的願景。

**END_OF_MEMO**

*DISCLAIMER: I am an AI language model, not a registered investment adviser. Information provided is educational and general in nature. Consult a qualified financial professional before making any investment decisions.*

</details>


## 建構 Agent 的最佳實務

最有效的 agent 系統結合了模組化的 agent 設計、清楚的 tool 定義、平行執行和結構化的 prompt。這個做法是 OpenAI Agents SDK 的核心，讓你的 workflow 穩健、可擴充，也容易除錯或擴展。

**OpenAI Agents SDK 中支撐這些最佳實務的主要功能：**
- **Agent loop：** 自動處理 tool call、LLM 推理和 workflow 控制。
- **Python 優先的編排：** 用熟悉的 Python 寫法來串接、組合和編排 agent。
- **Handoff：** 在 agent 之間委派任務，達到專業分工和模組化。
- **Guardrail：** 驗證輸入／輸出，遇到錯誤提早中斷，提升可靠度。
- **Function tool：** 把任何 Python function 註冊成 tool，自動產生 schema 並驗證。
- **Tracing：** 視覺化、除錯並監控 workflow 的每一步，完全透明。

設計良好的 tool、周全的編排和謹慎的模型選擇，是建構有效 agent 系統的關鍵。這個範例用 GPT-4.1 系列模型，因為它們有很強的分析和 tool 使用能力（[見 GPT-4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)）。想看更深入的架構最佳實務，請見附帶的 [A Practical Guide to Building Agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)。把這些元素結合起來，你就能得到穩健、可擴充、容易除錯或擴展的系統。

歡迎用你自己的投資問題試試這個範例，也請分享任何回饋！祝你開發順利。

---

## 延伸閱讀與最佳實務

- [OpenAI Agents SDK Documentation](https://openai.github.io/openai-agents-python/)
- [OpenAI Agents SDK: Multi-Agent Orchestration](https://openai.github.io/openai-agents-python/multi_agent/)
- [OpenAI Agents SDK: Tool List](https://openai.github.io/openai-agents-python/tools/)
- [OpenAI Agents SDK: MCP Documentation](https://openai.github.io/openai-agents-python/mcp/)

- [MCP Spec](https://spec.modelcontextprotocol.io/specification/2024-11-05/architecture/)
- [OpenAI Cookbook](https://github.com/openai/openai-cookbook)
- ([GPT-4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide))
- [A Practical Guide to Building Agents (PDF)](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)

---

## 重點整理

- 多 agent 協作是把複雜任務拆給各有專長的 agent，再由編排層整合，比一個巨大 prompt 更深入也更好維護。
- Handoff 是把控制權交出去；agent-as-tool 是主 agent 保有控制權、把其他 agent 當 tool 呼叫，比較透明、好稽核。
- 一個 workflow 可以同時混用自訂 function tool、OpenAI 託管 tool 和 MCP server。
- 彼此獨立的子任務用平行 tool call 同時跑，能大幅縮短總時間。
- 把規則和流程寫進 system prompt 檔，再搭配 Traces，讓每次執行一致、可追蹤。

## 練習

1. 把 `question` 換成你自己的問題（例如換一檔股票），保留日期欄位，跑完後到 OpenAI Traces 看三位專家是不是真的同時被呼叫。
2. 打開 `prompts/pm_base.md`，改一條 tool 使用規則（例如要求備忘錄多一段風險情境），重跑並比較輸出差異。
3. 仿照 Fundamental 專家的包法，用 `function_tool` 新增第四位專家（例如 Sentiment agent），把它加進 Head PM 的 tool 清單和 prompt。
