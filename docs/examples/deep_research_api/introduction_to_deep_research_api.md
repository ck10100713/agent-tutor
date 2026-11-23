---
translated: true
source: examples/deep_research_api/introduction_to_deep_research_api.ipynb
---
# OpenAI API 的 deep research 入門

> 原文：[examples/deep_research_api/introduction_to_deep_research_api.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/deep_research_api/introduction_to_deep_research_api.ipynb)



## 這篇在做什麼

介紹 Deep Research API 怎麼用。你丟一個高層次的問題，它會自己拆解子問題、搜尋網路、整合結果，回傳附引用的結構化報告。範例用 semaglutide 的經濟影響研究當主題，並示範怎麼解析回應、看中間步驟、接 MCP，以及加上改寫 prompt 的流程。

## 學完你會

- 用 `responses` endpoint 搭配 `web_search_preview`、`background` 模式呼叫 Deep Research 模型
- 解析回應：取出最終報告、inline citation，以及 reasoning、web search、code 執行等中間步驟
- 用輕量模型先改寫或澄清使用者的 prompt，再交給 Deep Research

## 開跑前

- OpenAI API key（Deep Research 模型要付費）
- 如果要試 MCP 的部分，需要一個可用的 MCP server 和你自己的文件

---

## 背景

Deep Research API 讓你自動化需要推理、規劃，以及整合真實世界資訊的複雜研究流程。它的設計是接收高層次的查詢，利用一個具備 agent 能力的模型，拆解任務、執行網路搜尋、整合結果，最後回傳結構化、引用豐富的報告。

不同於 ChatGPT 把這個過程隱藏起來，API 讓你直接用程式存取。送出請求後，模型會自行規劃子問題，使用網路搜尋和程式碼執行等 tool，產生最終的結構化回應。這份 cookbook 會簡單介紹 Deep Research API 和使用方式。

可以透過 `responses` endpoint 使用 Deep Research，支援下面的模型：

- `o3-deep-research-2025-06-26`：針對深入整合和較高品質的輸出最佳化
- `o4-mini-deep-research-2025-06-26`：輕量且較快，適合對延遲敏感的情境

## 設定

### 安裝需要的套件
安裝最新版的 OpenAI Python SDK。

```python
!pip install --upgrade openai
```

### 認證
匯入 OpenAI client，並用你的 API key 初始化。

```python
from openai import OpenAI
OPENAI_API_KEY="" # YOUR OPENAI_API_KEY
#OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY)
```

## 開始使用

我們來走一遍 Deep Research API 呼叫的範例。假設我們在一家醫療金融服務公司，任務是針對最近用來治療第二型糖尿病和肥胖的藥物（特別是 semaglutide）的經濟影響，產出一份深入報告。目標是把臨床結果、成本效益和各地區的價格資料，整合成有結構、有引用佐證的分析，供投資、保險給付策略或政策建議參考。

開始之前，我們要：
- 在 system message 裡放入我們的角色，說明想產出的報告類型。
- 把 `summary` 參數設成 `"auto"`，取得最好的摘要。想要更詳細的報告，可以把 `summary` 設成 `"detailed"`。
- 加入必要的 `web_search_preview` tool，也可以選擇性加上 `code_interpreter`。
- 把 `background` 參數設成 `True`。因為 Deep Research 任務可能要跑好幾分鐘，開啟 background 模式可以讓你非同步執行請求，不用擔心 timeout 或其他連線問題。

```python
system_message = """
You are a professional researcher preparing a structured, data-driven report on behalf of a global health economics team. Your task is to analyze the health question the user poses.

Do:
- Focus on data-rich insights: include specific figures, trends, statistics, and measurable outcomes (e.g., reduction in hospitalization costs, market size, pricing trends, payer adoption).
- When appropriate, summarize data in a way that could be turned into charts or tables, and call this out in the response (e.g., “this would work well as a bar chart comparing per-patient costs across regions”).
- Prioritize reliable, up-to-date sources: peer-reviewed research, health organizations (e.g., WHO, CDC), regulatory agencies, or pharmaceutical earnings reports.
- Include inline citations and return all source metadata.

Be analytical, avoid generalities, and ensure that each section supports data-backed reasoning that could inform healthcare policy or financial modeling.
"""

user_query = "Research the economic impact of semaglutide on global healthcare systems."

response = client.responses.create(
  model="o3-deep-research",
  input=[
    {
      "role": "developer",
      "content": [
        {
          "type": "input_text",
          "text": system_message,
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": user_query,
        }
      ]
    }
  ],
  reasoning={
    "summary": "auto"
  },
  tools=[
    {
      "type": "web_search_preview"
    },
    {
      "type": "code_interpreter",
      "container": {
        "type": "auto",
        "file_ids": []
      }
    }
  ]
)
```

## 解析回應

Deep Research API 的回應包含結構化的最終答案、inline citation、reasoning 步驟的摘要，以及來源的 metadata。

### 取出最終報告

這是報告的主要文字輸出。


```python
# Access the final report from the response object
print(response.output[-1].content[0].text)
```

### 取得 inline citation 和 metadata
回應文字裡的 inline citation 都有標註，並連結到對應的來源 metadata。每個 annotation 包含：
- start_index 和 end_index：citation 對應到文字中的字元範圍
- title：來源的簡短標題
- url：完整的來源 URL

有了這個結構，你就能建立引用清單或參考文獻、在下游應用加上可點擊的超連結，並標示與追溯報告中有資料佐證的論述。

```python
annotations = response.output[-1].content[0].annotations
for i, citation in enumerate(annotations):
    print(f"Citation {i+1}:")
    print(f"  Title: {citation.title}")
    print(f"  URL: {citation.url}")
    print(f"  Location: chars {citation.start_index}–{citation.end_index}")
```

### 檢視中間步驟
Deep Research API 也會公開 agent 做過的所有中間步驟，包含 reasoning 步驟、網路搜尋呼叫和程式碼執行。你可以用這些來 debug、分析，或視覺化最終答案是怎麼組出來的。
每個中間步驟都存在 `response.output` 裡，`type` 欄位表示它是哪一種。

#### Reasoning 步驟
這些是模型在推理子問題時產生的內部摘要或計畫。

```python
# Find the first reasoning step
reasoning = next(item for item in response.output if item.type == "reasoning")
for s in reasoning.summary:
    print(s.text)
```

#### 網路搜尋呼叫
這些顯示執行過哪些搜尋查詢，能幫你追蹤模型取得了哪些資訊。

```python
# Find the first web search step
search = next(item for item in response.output if item.type == "web_search_call")
print("Query:", search.action["query"])
print("Status:", search.status)
```

#### 程式碼執行
如果模型用了 code interpreter（例如解析資料或產生圖表），這些步驟會以 "code_interpreter_call" 或類似的 type 出現。

```python
# Find a code execution step (if any)
code_step = next((item for item in response.output if item.type == "code_interpreter_call"), None)
if code_step:
    print(code_step.input)
    print(code_step.output)
else:
    print("No code execution steps found.")
```

#### Model Context Protocol (MCP)

假設你想在 Deep Research 任務中引入自己的內部文件。Deep Research 模型和 Responses API 都支援 MCP 型的 tool，所以你可以擴充它們，去查詢你的私有知識庫或其他第三方服務。

在下面的例子裡，我們設定一個 MCP tool，讓 Deep Research 可以隨需取得你組織內部的 semaglutide 研究。這個 MCP server 是 OpenAI File Storage 服務的 proxy，會自動把你上傳的檔案向量化，方便高效檢索。

想看這個簡單的 MCP server 是_怎麼_建的，請參考[這份相關的 cookbook](https://cookbook.openai.com/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme)。

```python
# system_message includes reference to internal file lookups for MCP.
system_message = """
You are a professional researcher preparing a structured, data-driven report on behalf of a global health economics team. Your task is to analyze the health question the user poses.

Do:
- Focus on data-rich insights: include specific figures, trends, statistics, and measurable outcomes (e.g., reduction in hospitalization costs, market size, pricing trends, payer adoption).
- When appropriate, summarize data in a way that could be turned into charts or tables, and call this out in the response (e.g., “this would work well as a bar chart comparing per-patient costs across regions”).
- Prioritize reliable, up-to-date sources: peer-reviewed research, health organizations (e.g., WHO, CDC), regulatory agencies, or pharmaceutical earnings reports.
- Include an internal file lookup tool to retrieve information from our own internal data sources. If you’ve already retrieved a file, do not call fetch again for that same file. Prioritize inclusion of that data.
- Include inline citations and return all source metadata.

Be analytical, avoid generalities, and ensure that each section supports data-backed reasoning that could inform healthcare policy or financial modeling.
"""

user_query = "Research the economic impact of semaglutide on global healthcare systems."

response = client.responses.create(
  model="o3-deep-research-2025-06-26",
  input=[
    {
      "role": "developer",
      "content": [
        {
          "type": "input_text",
          "text": system_message,
        }
      ]
    },
    {
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": user_query,
        }
      ]
    }
  ],
  reasoning={
    "summary": "auto"
  },
  tools=[
    {
      "type": "web_search_preview"
    },
    { # ADD MCP TOOL SUPPORT
      "type": "mcp",
      "server_label": "internal_file_lookup",
      "server_url": "https://<your_mcp_server>/sse/", # Update to the location of *your* MCP server
      "require_approval": "never"
    }
  ]
)
```

## 檢視你的回應

研究報告的前 100 個字元，後面接著 citation 和 MCP tool 呼叫。

```python
# Grab the full report text once
report_text = response.output[-1].content[0].text

print("REPORT EXCERPT:")
print(report_text[:100])   # first 100 chars
print("--------")

annotations = response.output[-1].content[0].annotations
target_url = "https://platform.openai.com/storage/files"

for citation in annotations:
    if citation.url.startswith(target_url):
        start, end = citation.start_index, citation.end_index

        # extract exactly the cited span
        excerpt       = report_text[start:end]

        # extract up to 100 chars immediately before the citation
        pre_start     = max(0, start - 100)
        preceding_txt = report_text[pre_start:start]

        print("MCP CITATION SAMPLE:")
        print(f"  Title:       {citation.title}")
        print(f"  URL:         {citation.url}")
        print(f"  Location:    chars {start}–{end}")
        print(f"  Preceding:   {preceding_txt!r}")
        print(f"  Excerpt:     {excerpt!r}")
        break

print("--------")


# EXAMPLE MCP CITATION

# REPORT EXCERPT:
# # Introduction
# Semaglutide – a glucagon-like peptide-1 (GLP-1) analogue – has rapidly become a blo
# --------
# MCP CITATION SAMPLE:
#   Title:       Document file-WqbCdYNqNzGuFfCAeWyZfp
#   URL:         https://platform.openai.com/storage/files/file-WqbCdYNqNzGuFfCAeWyZfp
#   Location:    chars 237–331
#   Preceding:   'and obesity due to its potent clinical efficacy (often inducing ~10–15% body weight loss in trials) '
#   Excerpt:     '([platform.openai.com](https://platform.openai.com/storage/files/file-WqbCdYNqNzGuFfCAeWyZfp))'


# print the MCP tool calls
calls = [
    (item.name, item.server_label, item.arguments)
    for item in response.output
    if item.type == "mcp_call" and item.arguments
]
for name, server, args in calls:
    print(f"{name}@{server} → {args}")
print("--------")
```

## ChatGPT 和 Deep Research API 的澄清問題差異
如果你在 ChatGPT 用過 Deep Research，可能注意到送出查詢後它常會追問。這是刻意的：ChatGPT 會用一個中間模型（像 gpt-4.1）幫忙釐清你的意圖，並在研究開始前收集更多 context（例如你的偏好、目標或限制）。這個額外的步驟能讓系統調整網路搜尋，回傳更相關、更有針對性的結果。

相較之下，Deep Research API 跳過這個澄清步驟。因為模型預期一開始就拿到完整的 prompt，不會要求額外的 context，也不會補足缺漏的資訊，它只會根據收到的輸入開始研究，所以身為開發者，你可以自行設定這個處理步驟，來改寫使用者 prompt 或問一組澄清問題。

要從 API 得到穩定可靠的好輸出，可以用兩種做法。
- 用另一個輕量模型（例如 gpt-4.1）做 prompt rewriter，在把使用者查詢交給研究模型前，先擴充或具體化。
- 把所有相關細節都放進去：想要的範圍、比較對象、指標、地區、偏好的來源，以及預期的輸出格式。

這樣的設計讓開發者完全掌控研究任務怎麼被框定，但也讓輸入 prompt 的品質責任更重。下面是一個通用的 rewriting_prompt 範例，用來更好地引導後續的 deep research 查詢。

![../../images/intro_dr.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/intro_dr.png)

這是一個改寫 prompt 的範例：

```python
suggested_rewriting_prompt = """
You will be given a research task by a user. Your job is to produce a set of instructions for a researcher that will complete the task. Do NOT complete the task yourself, just provide instructions on how to complete it.

GUIDELINES:
1. **Maximize Specificity and Detail**
- Include all known user preferences and explicitly list key attributes or dimensions to consider.
- It is of utmost importance that all details from the user are included in the instructions.

2. **Fill in Unstated But Necessary Dimensions as Open-Ended**
- If certain attributes are essential for a meaningful output but the user has not provided them, explicitly state that they are open-ended or default to no specific constraint.

3. **Avoid Unwarranted Assumptions**
- If the user has not provided a particular detail, do not invent one.
- Instead, state the lack of specification and guide the researcher to treat it as flexible or accept all possible options.

4. **Use the First Person**
- Phrase the request from the perspective of the user.

5. **Tables**
- If you determine that including a table will help illustrate, organize, or enhance the information in the research output, you must explicitly request that the researcher provide them.
Examples:
- Product Comparison (Consumer): When comparing different smartphone models, request a table listing each model's features, price, and consumer ratings side-by-side.
- Project Tracking (Work): When outlining project deliverables, create a table showing tasks, deadlines, responsible team members, and status updates.
- Budget Planning (Consumer): When creating a personal or household budget, request a table detailing income sources, monthly expenses, and savings goals.
Competitor Analysis (Work): When evaluating competitor products, request a table with key metrics, such as market share, pricing, and main differentiators.

6. **Headers and Formatting**
- You should include the expected output format in the prompt.
- If the user is asking for content that would be best returned in a structured format (e.g. a report, plan, etc.), ask the researcher to format as a report with the appropriate headers and formatting that ensures clarity and structure.

7. **Language**
- If the user input is in a language other than English, tell the researcher to respond in this language, unless the user query explicitly asks for the response in a different language.

8. **Sources**
- If specific sources should be prioritized, specify them in the prompt.
- For product and travel research, prefer linking directly to official or primary websites (e.g., official brand sites, manufacturer pages, or reputable e-commerce platforms like Amazon for user reviews) rather than aggregator sites or SEO-heavy blogs.
- For academic or scientific queries, prefer linking directly to the original paper or official journal publication rather than survey papers or secondary summaries.
- If the query is in a specific language, prioritize sources published in that language.
"""
```

```python
response = client.responses.create(
    instructions=suggested_rewriting_prompt,
    model="gpt-4.1-2025-04-14",
    input="help me plan a trip to france",
)
```

```python
new_query = response.output[0].content[0].text
print(new_query)
```

在這個例子裡，使用者送出的是泛泛、開放式的查詢，沒有說明旅行日期、目的地偏好、預算、興趣或同行的人等關鍵細節。改寫 prompt 把查詢改寫後，Deep Research 會嘗試產生廣泛、涵蓋面大的回應，預先考慮常見的使用情境。

這種行為在呈現各種選項時很有用，但常常導致內容冗長、延遲變高、token 用量增加，因為模型必須考慮許多可能的情境。對於會觸發複雜規劃或整合任務的查詢（例如多目的地的旅遊行程、比較型研究、產品選擇）尤其如此。

與其馬上照廣泛的研究計畫進行，我們改試試用較輕量的模型，先溫和地向使用者問澄清問題，再產生完整答案，然後用改寫 prompt 讓模型得到更清楚的輸出。

```python
suggested_clariying_prompt = """"
You will be given a research task by a user. Your job is NOT to complete the task yet, but instead to ask clarifying questions that would help you or another researcher produce a more specific, efficient, and relevant answer.

GUIDELINES:
1. **Maximize Relevance**
- Ask questions that are *directly necessary* to scope the research output.
- Consider what information would change the structure, depth, or direction of the answer.

2. **Surface Missing but Critical Dimensions**
- Identify essential attributes that were not specified in the user’s request (e.g., preferences, time frame, budget, audience).
- Ask about each one *explicitly*, even if it feels obvious or typical.

3. **Do Not Invent Preferences**
- If the user did not mention a preference, *do not assume it*. Ask about it clearly and neutrally.

4. **Use the First Person**
- Phrase your questions from the perspective of the assistant or researcher talking to the user (e.g., “Could you clarify...” or “Do you have a preference for...”)

5. **Use a Bulleted List if Multiple Questions**
- If there are multiple open questions, list them clearly in bullet format for readability.

6. **Avoid Overasking**
- Prioritize the 3–6 questions that would most reduce ambiguity or scope creep. You don’t need to ask *everything*, just the most pivotal unknowns.

7. **Include Examples Where Helpful**
- If asking about preferences (e.g., travel style, report format), briefly list examples to help the user answer.

8. **Format for Conversational Use**
- The output should sound helpful and conversational—not like a form. Aim for a natural tone while still being precise.
"""


response = client.responses.create(
    instructions=suggested_clariying_prompt,
    model="gpt-4.1-2025-04-14",
    input="help me plan a trip to france",
)

new_query = response.output[0].content[0].text
print(new_query)
```

```python
user_follow_up = """I'd like to travel in August. I'd like to visit Paria and Nice. I'd like to keep it under $1500 for a 7 day trip without including flights.
I'm going with my friend. we're both in our mid-twenties. i like history, really good french food and wine, and hiking
"""
instructions_for_DR = client.responses.create(
    instructions=suggested_rewriting_prompt,
    model="gpt-4.1-2025-04-14",
    input=user_follow_up,
)
instructions_for_deep_research = instructions_for_DR.output[0].content[0].text
print(instructions_for_deep_research)
```

```python
deep_research_call = client.responses.create(
  model="o4-mini-deep-research-2025-06-26",
  input=[
    {
      "role": "developer",
      "content": [
        {
          "type": "input_text",
          "text": instructions_for_deep_research,
        }
      ]
    },
  ],
  reasoning={
    "summary": "auto"
  },
  tools=[
    {
      "type": "web_search_preview"
    },
  ]
)
```

```python
# Access the final report from the response object
print(deep_research_call.output[-1].content[0].text)
```

這樣就完成了！一份為你即將到來的法國之旅量身打造的 deep research 報告！

這份 notebook 探討了怎麼用 Deep Research API 自動化複雜的真實世界研究任務，從分析 semaglutide 的經濟影響，到規劃一趟適合你的法國旅行。需要有結構、有引用、以真實證據為基礎的答案時，Deep Research 特別好用。幾個突出的使用情境包括：
- 產品比較和市場分析
- 競爭情報和策略報告
- 技術文獻回顧和政策整合


不管你是想建構研究 agent、產生結構化報告，或是把高品質的整合能力放進你的工作流程，希望這裡的範例能幫你起步。

接下來？[Deep Research Agents](https://cookbook.openai.com/examples/deep_research_api/introduction_to_deep_research_api_agents)

## 重點整理

- Deep Research 是 agent 式的模型，會自己拆子問題、搜尋、整合，用 `responses` endpoint 呼叫，任務很久所以要開 `background`。
- 回應不只有報告，`response.output` 裡有 reasoning、搜尋、程式碼執行等中間步驟，可用來 debug 和追溯來源。
- Inline citation 的 annotation 帶字元範圍、標題和 URL，可以直接做參考文獻或超連結。
- 它不像 ChatGPT 會先追問，prompt 要自己寫完整，或用輕量模型先改寫、澄清。
- MCP tool 能讓 Deep Research 查你自己的私有資料。

## 練習

1. 把 `summary` 從 `"auto"` 改成 `"detailed"`，比較 reasoning 摘要的差異。
2. 換成 `o4-mini-deep-research-2025-06-26`，比較跑的時間和報告品質。
3. 把研究主題換成你自己的，並寫一段程式用 annotation 的 start_index、end_index、url 產出一份參考文獻清單。
