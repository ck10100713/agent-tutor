---
translated: true
source: examples/deep_research_api/introduction_to_deep_research_api_agents.ipynb
---

# 用 Agents SDK 搭配 Deep Research API

> 原文：[examples/deep_research_api/introduction_to_deep_research_api_agents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/deep_research_api/introduction_to_deep_research_api_agents.ipynb)



## 這篇在做什麼
示範怎麼用 OpenAI Deep Research API 加上 Agents SDK，建出單 agent 和多 agent 的研究流程。多 agent 版本會先釐清使用者需求、把需求改寫成研究說明，再交給 research agent 去查。

## 學完你會
- 跑一個單 agent 的 deep research，並 stream 它的進度。
- 組出 Triage、Clarifier、Instruction Builder、Research 四個 agent 的 pipeline。
- 印出 agent 之間的互動流程，並從最終輸出抽出 URL citations。

## 開跑前
- 需要 OpenAI API key，設成環境變數 `OPENAI_API_KEY`。
- 需要安裝 Agents SDK 和 OpenAI Python SDK。
- Deep Research 比一般 Responses API 貴，要有對應額度。

這份 cookbook 示範怎麼用 OpenAI Deep Research API 和 OpenAI [Agents SDK](https://openai.github.io/openai-agents-python/) 建立 agentic 研究流程。它是[基礎篇 cookbook](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api) 的延續，沒看過的話建議先看。

你會學到怎麼編排單 agent 和多 agent pipeline、怎麼豐富使用者的 query 來提升輸出品質、怎麼 stream 研究進度、怎麼整合網路搜尋和[用 MCP 搜內部檔案](https://cookbook.openai.com/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme)，以及怎麼設計一個穩健的研究應用。

Deep Research Agents 適合需要規劃、整合資料、使用 tool 或多步驟 reasoning 的任務。簡單的事實查詢、一般問答或短對話不要用，直接用 openai.responses API 會更快也更便宜。

### 前置需求
* OpenAI API key（在環境中設成 OPENAI_API_KEY）
* Agents SDK 和 OpenAI Python SDK

### 設定
*安裝套件*

```python
%pip install --upgrade "openai>=1.88" "openai-agents>=0.0.19"
```

### 匯入函式庫並設定 client

**Zero Data Retention**

下面用 os.environ 設定關掉 Data Retention。這讓企業可以在 Zero Data Retention 的環境下使用 Deep Research。如果資料保留對你不是限制，建議保持開啟，這樣 agent 工作流程能自動留下追蹤紀錄，也能深度整合 evaluations 和 fine tuning 等平台工具。

```python
import os
from agents import Agent, Runner, WebSearchTool, RunConfig, set_default_openai_client, HostedMCPTool
from typing import List, Dict, Optional
from pydantic import BaseModel
from openai import AsyncOpenAI

# Use env var for API key and set a long timeout
client = AsyncOpenAI(timeout=600.0)
set_default_openai_client(client)
os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1" # Disable tracing for Zero Data Retention (ZDR) Organizations
```

### 基本的 Deep Research Agent

Basic Research Agent 用 `gpt-5.6-terra` 模型做 deep research，在智慧和成本之間取平衡。它用 `WebSearchTool` 存取公開網路，並把研究結果直接 stream 回 notebook。

**學習目標：**

做完這段，你就能跑一個單 agent 的研究任務並 stream 它的進度。

```python
# Define the research agent
research_agent = Agent(
    name="Research Agent",
    model="gpt-5.6-terra",
    tools=[WebSearchTool()],
    instructions="You perform deep empirical research based on the user's question."
)

# Async function to run the research and print streaming progress
async def basic_research(query):
    print(f"Researching: {query}")
    result_stream = Runner.run_streamed(
        research_agent,
        query
    )

    async for ev in result_stream.stream_events():
        if ev.type == "agent_updated_stream_event":
            print(f"\n--- switched to agent: {ev.new_agent.name} ---")
            print(f"\n--- RESEARCHING ---")
        elif (
            ev.type == "raw_response_event"
            and hasattr(ev.data, "item")
            and hasattr(ev.data.item, "action")
        ):
            action = ev.data.item.action or {}
            if action.get("type") == "search":
                print(f"[Web search] query={action.get('query')!r}")

    # streaming is complete → final_output is now populated
    return result_stream.final_output

# Run the research and print the result
result = await basic_research("Research the economic impact of semaglutide on global healthcare systems.")
print(result)
```

### 帶有釐清步驟的多 Agent 研究

多 Agent Deep Research

想想怎麼進一步提升 Deep Research 產出的品質。這裡用多 agent 架構，在把 query 交給 deep research agent 之前，先補上更多關於使用者問題、以及我們期待最終報告長什麼樣子的資訊。


## 子 Agent 的 Prompt 強化

輔助 agent 的 prompt 是特別設計的，目的是給使用者最初的 query 加上結構和嚴謹度，讓最終研究輸出品質更好。

```python
# ─────────────────────────────────────────────────────────────
#  Prompts
# ─────────────────────────────────────────────────────────────

CLARIFYING_AGENT_PROMPT =  """
    If the user hasn't specifically asked for research (unlikely), ask them what research they would like you to do.

        GUIDELINES:
        1. **Be concise while gathering all necessary information** Ask 2–3 clarifying questions to gather more context for research.
        - Make sure to gather all the information needed to carry out the research task in a concise, well-structured manner. Use bullet points or numbered lists if appropriate for clarity. Don't ask for unnecessary information, or information that the user has already provided.
        2. **Maintain a Friendly and Non-Condescending Tone**
        - For example, instead of saying “I need a bit more detail on Y,” say, “Could you share more detail on Y?”
        3. **Adhere to Safety Guidelines**
        """

RESEARCH_INSTRUCTION_AGENT_PROMPT = """

        Based on the following guidelines, take the users query, and rewrite it into detailed research instructions. OUTPUT ONLY THE RESEARCH INSTRUCTIONS, NOTHING ELSE. Transfer to the research agent.

        GUIDELINES:
        1. **Maximize Specificity and Detail**
        - Include all known user preferences and explicitly list key attributes or dimensions to consider.
        - It is of utmost importance that all details from the user are included in the expanded prompt.

        2. **Fill in Unstated But Necessary Dimensions as Open-Ended**
        - If certain attributes are essential for a meaningful output but the user has not provided them, explicitly state that they are open-ended or default to “no specific constraint.”

        3. **Avoid Unwarranted Assumptions**
        - If the user has not provided a particular detail, do not invent one.
        - Instead, state the lack of specification and guide the deep research model to treat it as flexible or accept all possible options.

        4. **Use the First Person**
        - Phrase the request from the perspective of the user.

        5. **Tables**
        - If you determine that including a table will help illustrate, organize, or enhance the information in your deep research output, you must explicitly request that the deep research model provide them.
        Examples:
        - Product Comparison (Consumer): When comparing different smartphone models, request a table listing each model’s features, price, and consumer ratings side-by-side.
        - Project Tracking (Work): When outlining project deliverables, create a table showing tasks, deadlines, responsible team members, and status updates.
        - Budget Planning (Consumer): When creating a personal or household budget, request a table detailing income sources, monthly expenses, and savings goals.
        Competitor Analysis (Work): When evaluating competitor products, request a table with key metrics—such as market share, pricing, and main differentiators.

        6. **Headers and Formatting**
        - You should include the expected output format in the prompt.
        - If the user is asking for content that would be best returned in a structured format (e.g. a report, plan, etc.), ask the Deep Research model to “Format as a report with the appropriate headers and formatting that ensures clarity and structure.”

        7. **Language**
        - If the user input is in a language other than English, tell the model to respond in this language, unless the user query explicitly asks for the response in a different language.

        8. **Sources**
        - If specific sources should be prioritized, specify them in the prompt.
        - Prioritize Internal Knowledge. Only retrieve a single file once.
        - For product and travel research, prefer linking directly to official or primary websites (e.g., official brand sites, manufacturer pages, or reputable e-commerce platforms like Amazon for user reviews) rather than aggregator sites or SEO-heavy blogs.
        - For academic or scientific queries, prefer linking directly to the original paper or official journal publication rather than survey papers or secondary summaries.
        - If the query is in a specific language, prioritize sources published in that language.

        IMPORTANT: Ensure that the complete payload to this function is valid JSON
        IMPORTANT: SPECIFY REQUIRED OUTPUT LANGUAGE IN THE PROMPT
        """
```

# 四個 Agent 的 Deep Research Pipeline

1. **Triage Agent**  
   - 檢查使用者的 query  
   - 如果缺少背景資訊，就轉給 Clarifier Agent，否則轉給 Instruction Agent  

2. **Clarifier Agent**  
   - 問後續問題  
   - 等使用者（或模擬的）回答  

3. **Instruction Builder Agent**  
   - 把補充過的輸入轉成精確的研究說明  

4. **Research Agent** (`gpt-5.6-sol`)  
   - 用 `WebSearchTool` 做網路規模的實證研究
   - 用 MCP 搜內部知識庫，如果有相關文件，agent 會把相關片段納入參考資料。   
   - Stream 中間事件，讓過程透明
   - 輸出最終的研究成果（我們之後會解析它）

![../../images/agents_dr.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent_dr.png)

想知道 MCP server 是怎麼建的，[看這份資料](https://cookbook.openai.com/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme )。

```python
# ─────────────────────────────────────────────────────────────
# Structured outputs (needed only for Clarifying agent)
# ─────────────────────────────────────────────────────────────
class Clarifications(BaseModel):
    questions: List[str]

# ─────────────────────────────────────────────────────────────
# Agents
# ─────────────────────────────────────────────────────────────
research_agent = Agent(
    name="Research Agent",
    model="gpt-5.6-sol",
    instructions="Perform deep empirical research based on the user's instructions.",
    tools=[WebSearchTool(),
           HostedMCPTool(
            tool_config={
                "type": "mcp",
                "server_label": "file_search",
                "server_url": "https://<url>/sse",
                "require_approval": "never",
            }
        )
    ]
)

instruction_agent = Agent(
    name="Research Instruction Agent",
    model="gpt-4o-mini",
    instructions=RESEARCH_INSTRUCTION_AGENT_PROMPT,
    handoffs=[research_agent],
)

clarifying_agent = Agent(
    name="Clarifying Questions Agent",
    model="gpt-4o-mini",
    instructions=CLARIFYING_AGENT_PROMPT,
    output_type=Clarifications,
    handoffs=[instruction_agent],
)

triage_agent = Agent(
    name="Triage Agent",
    instructions=(
        "Decide whether clarifications are required.\n"
        "• If yes → call transfer_to_clarifying_questions_agent\n"
        "• If no  → call transfer_to_research_instruction_agent\n"
        "Return exactly ONE function-call."
    ),
    handoffs=[clarifying_agent, instruction_agent],
)


# ─────────────────────────────────────────────────────────────
#  Auto-clarify helper
# ─────────────────────────────────────────────────────────────
async def basic_research(
    query: str,
    mock_answers: Optional[Dict[str, str]] = None,
    verbose: bool = False,
):
    stream = Runner.run_streamed(
        triage_agent,
        query,
        run_config=RunConfig(tracing_disabled=True),
    )

    async for ev in stream.stream_events():
        if isinstance(getattr(ev, "item", None), Clarifications):
            reply = []
            for q in ev.item.questions:
                ans = (mock_answers or {}).get(q, "No preference.")
                reply.append(f"**{q}**\n{ans}")
            stream.send_user_message("\n\n".join(reply))
            continue
        if verbose:
            print(ev)

    #return stream.final_output
    return stream

# ─────────────────────────────────────────────────────────────
#  Example run
# ─────────────────────────────────────────────────────────────
result = await basic_research(
    "Research the economic impact of semaglutide on global healthcare systems.",
    mock_answers={},   # or provide canned answers
)
```

## Agent 互動流程

Agent SDK 本身的 trace 就能看，不過你也可能想印出人類可讀的高階 agent 互動流程，包含 tool call。執行 print_agent_interaction，就會得到簡化後的 agent 步驟序列，內容有：agent 名稱、事件類型（handoff、tool call、message output）、tool call 的簡要資訊（tool 名稱和參數）。


```python
import json

def parse_agent_interaction_flow(stream):
    print("=== Agent Interaction Flow ===")
    count = 1

    for item in stream.new_items:
        # Agent name, fallback if missing
        agent_name = getattr(item.agent, "name", "Unknown Agent") if hasattr(item, "agent") else "Unknown Agent"

        if item.type == "handoff_call_item":
            func_name = getattr(item.raw_item, "name", "Unknown Function")
            print(f"{count}. [{agent_name}] → Handoff Call: {func_name}")
            count += 1

        elif item.type == "handoff_output_item":
            print(f"{count}. [{agent_name}] → Handoff Output")
            count += 1

        elif item.type == "mcp_list_tools_item":
            print(f"{count}. [{agent_name}] → mcp_list_tools_item")
            count += 1

        elif item.type == "reasoning_item":
            print(f"{count}. [{agent_name}] → Reasoning step")
            count += 1

        elif item.type == "tool_call_item":
            tool_name = getattr(item.raw_item, "name", None)

            # Skip tool call if tool_name is missing or empty
            if not isinstance(tool_name, str) or not tool_name.strip():
                continue  # skip silently

            tool_name = tool_name.strip()

            args = getattr(item.raw_item, "arguments", None)
            args_str = ""

            if args:
                try:
                    parsed_args = json.loads(args)
                    if parsed_args:
                        args_str = json.dumps(parsed_args)
                except Exception:
                    if args.strip() and args.strip() != "{}":
                        args_str = args.strip()

            args_display = f" with args {args_str}" if args_str else ""

            print(f"{count}. [{agent_name}] → Tool Call: {tool_name}{args_display}")
            count += 1

        elif item.type == "message_output_item":
            print(f"{count}. [{agent_name}] → Message Output")
            count += 1

        else:
            print(f"{count}. [{agent_name}] → {item.type}")
            count += 1

# Example usage:
parse_agent_interaction_flow(result)
```

## Citations

下面這段 Python 會抽出並印出最終輸出相關的 URL citations：

```python
def print_final_output_citations(stream, preceding_chars=50):
    # Iterate over new_items in reverse to find the last message_output_item(s)
    for item in reversed(stream.new_items):
        if item.type == "message_output_item":
            for content in getattr(item.raw_item, 'content', []):
                if not hasattr(content, 'annotations') or not hasattr(content, 'text'):
                    continue
                text = content.text
                for ann in content.annotations:
                    if getattr(ann, 'type', None) == 'url_citation':
                        title = getattr(ann, 'title', '<no title>')
                        url = getattr(ann, 'url', '<no url>')
                        start = getattr(ann, 'start_index', None)
                        end = getattr(ann, 'end_index', None)

                        if start is not None and end is not None and isinstance(text, str):
                            # Calculate preceding snippet start index safely
                            pre_start = max(0, start - preceding_chars)
                            preceding_text = text[pre_start:start].replace('\n', ' ').strip()
                            excerpt = text[start:end].replace('\n', ' ').strip()
                            print("# --------")
                            print("# MCP CITATION SAMPLE:")
                            print(f"#   Title:       {title}")
                            print(f"#   URL:         {url}")
                            print(f"#   Location:    chars {start}–{end}")
                            print(f"#   Preceding:   '{preceding_text}'")
                            print(f"#   Excerpt:     '{excerpt}'\n")
                        else:
                            # fallback if no indices available
                            print(f"- {title}: {url}")
            break

# Usage
print_final_output_citations(result)
```

```python
## Deep Research Research Report

print(result.final_output)
```

### 結論

有了這份 notebook 的模式，你就有基礎去建立可擴展、可上 production 的研究流程。範例不只示範怎麼編排多 agent pipeline 和 stream 研究進度，也示範怎麼整合網路搜尋和 MCP 來取得外部知識。

用 agentic 工作流程，你可以不只做簡單問答，而是處理需要規劃、整合和使用 tool 的複雜多步驟研究。這個模組化的多 agent 設計（triage、clarification、instruction、research 四種 agent）可以調整到各種領域，從醫療、金融到技術盡職調查和市場分析。

隨著 Deep Research API 和 Agents SDK 持續演進，這些模式能讓你站在自動化、以資料為基礎的研究最前線。不論你是在做內部知識工具、自動化競爭情報，還是支援專家分析師，這些工作流程都是個扎實又好擴充的起點。

**Happy researching!**


## 重點整理
- Deep Research 適合需要規劃、整合和多步驟 reasoning 的任務，簡單問答用一般 Responses API 就好。
- 把 query 先釐清、再改寫成研究說明，能明顯提升最終報告品質。
- 多 agent 靠 handoff 分工：triage 判斷、clarifier 追問、instruction builder 整理、research agent 執行。
- Stream 事件讓你能看到研究過程，也方便做 agent 互動流程的輸出。
- Zero Data Retention 是設定選項，沒有限制的話保留資料能得到 trace 和平台整合的好處。

## 練習
1. 把 Basic Research Agent 的 query 換成你自己的主題，執行並觀察 stream 出來的事件。
2. 修改 Triage Agent 的 instructions，讓它在 query 少於某個長度時一律先走 Clarifier。
3. 在 citations 的程式碼中，加上去除重複 URL 並按網域分組印出的邏輯。
