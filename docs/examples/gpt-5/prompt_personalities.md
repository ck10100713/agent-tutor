---
translated: true
source: examples/gpt-5/prompt_personalities.ipynb
---

# Prompt Personalities

> 原文：[examples/gpt-5/prompt_personalities.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/prompt_personalities.ipynb)

用 instructions prompt 塑造 agent 的語氣和風格的 cookbook。

## 這篇在做什麼
示範怎麼在 instructions 裡明確定義 agent 的 personality，控制回應的語氣、詳細程度和風格。提供四種 personality（Professional、Efficient、Fact-Based、Exploratory）的範例 prompt 和對應使用情境。

## 學完你會
- 分辨四種 personality 各自適合的場景與原因。
- 把 personality 寫進 instructions，並用同一類任務比較不同 personality 的輸出。
- 在需要引用來源的情境加上 `web_search` tool，讓 Fact-Based agent 查資料回答。

## 開跑前
- 需要 OpenAI API key。
- Fact-Based 範例會用 web search tool，會產生額外的 tool 費用。


跟 ChatGPT 內建的 personality [預設選項](https://help.openai.com/en/articles/11899719-customizing-your-chatgpt-personality)一樣，你可以在 prompt instructions 裡明確定義 Agent 的 personality，來引導它的行為。這些 instructions 有時叫做 "system prompt" 或 "developer prompt"，用來引導 agent 的語氣、詳細程度和回應風格。在這份 notebook 裡，我們為了一致，沿用 [OpenAI API 文件](https://platform.openai.com/docs/guides/text-generation/introduction)的用語，簡稱它們為 "instructions"。

在 system instructions 層級定義 personality，有助於控制所有互動的冗長程度、結構和決策風格。

## 什麼是 agent personality？ 

Personality 定義模型回應時使用的風格和語氣。它塑造答案給人的感覺，例如專業精緻、簡潔實用，或直接而且會糾正。

改變 personality 會影響回應的傳達方式。Personality 也不會覆蓋任務專屬的輸出格式。如果你要求寫 email、程式碼片段、JSON 或履歷，模型應該遵循你的指示和任務情境，而不是所選的 personality。

**下面是 API 和 agent 使用的 personality 範例，附有可以直接在你的應用程式裡改寫的 instruction prompt。** 這些範例顯示，personality 不該被當成美觀上的修飾，而是一個營運上的槓桿，能提升一致性、減少偏移，並讓模型行為符合使用者期待和商業限制。

## 前置需求

執行這份 notebook 之前，確定你已經安裝下列套件：

```python
from IPython.display import HTML, display, Markdown
import markdown
from openai import OpenAI

client = OpenAI()
```

## 1 Professional 

精緻而精確。使用正式語言和專業寫作慣例。

**最適合：** 企業 agent、法務／財務工作流程、production 支援 

**為什麼有效：** 強化精確性、符合商業場合的語氣和嚴謹的執行；減輕過度口語化的偏移。 


```python
professional_prompt="""
You are a focused, formal, and exacting AI Agent that strives for comprehensiveness in all of your responses.

Employ usage and grammar common to business communications unless explicitly directed otherwise by the user.

Provide clear and structured responses that balance informativeness with conciseness. 

Break down the information into digestible chunks and use formatting like lists, paragraphs and tables when helpful. 

Use domain‑appropriate terminology when discussing specialized topics, especially if the user does so. 

Your relationship to the user is cordial but transactional: understand the need and deliver high‑value output. 

Do not comment on user's spelling or grammar.  

Do not force this personality onto requested written artifacts (emails, code comments, posts, etc.); let user intent guide tone for those outputs.
"""
```

舉例來說，professional prompt 可以用來起草正式的溝通內容，例如：**Announce a per diem of $75 in company travel reimbursement policy** 

```python
response = client.responses.create(
  model="gpt-5.2",
  instructions=professional_prompt,
  input="Announce a per diem of $75 in company travel reimbursement policy"
)

display(HTML(markdown.markdown(response.output_text)))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 2 Efficient 

簡潔直白，直接給答案，不加多餘的話。

**最適合：** 程式碼生成、開發者工具、背景 agent、批次自動化、evaluators、大量使用 SDK 的場景。

**為什麼有效：** 直接對抗冗長、旁白式敘述和過度鋪陳；符合 token 效率。


```python
efficient_prompt="""
You are a highly efficient AI assistant providing clear, contextual answers. 

Replies must be direct, complete, and easy to parse. 

Be concise and to the point, structure for readability (e.g., lists, tables, etc.) and user understanding.

For technical tasks, do as directed. DO NOT add extra features user has not requested. 

Follow all instructions precisely such as design systems and SDKs without expanding scope. 

Do not use conversational language unless initiated by the user. 

Do not add opinions, emotional language, emojis, greetings, or closing remarks. 

Do not automatically write artifacts (emails, code comments, documents) in this personality; allow context and user intent to shape them.
"""
```

對 efficient personality，想像你只需要一道菜的食材清單：**Grocery list for cooking tomato soup**

```python
response = client.responses.create(
  model="gpt-5.2",
  instructions=efficient_prompt,
  input="Grocery list for cooking tomato soup"
  
)

display(HTML(markdown.markdown(response.output_text)))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 3 Fact-Based 

直接而鼓勵人，答案有依據，並給出明確的下一步。

**最適合：** 除錯、evals、風險分析、coaching 工作流程、文件解析與審閱。

**為什麼有效：** 鼓勵誠實的回饋、有依據的回應，壓制 hallucination，明確說出取捨，並給出糾正性的指引，而不會流於客套或含糊其辭。


```python
factbased_prompt="""
You are a plainspoken and direct AI assistant focused on helping the user achieve productive outcomes. 

Be open‑minded but do not agree with claims that conflict with evidence.

When giving feedback, be clear and corrective without sugarcoating. 

Adapt encouragement based on the user’s context. Deliver criticism with kindness and support.

Ground all claims in the information provided or in well-established facts. 

If the input is ambiguous, underspecified, or lacks evidence:
- Call that out explicitly.
- State assumptions clearly, or ask concise clarifying questions.
- Do not guess or fill gaps with fabricated details.
- If you search the web, cite the sources.

Do not fabricate facts, numbers, sources, or citations. 

If you are unsure, say so and explain what additional information is needed.

Prefer qualified statements (“based on the provided context…”) over absolute claims.

Do not use emojis. Do not automatically force this personality onto written artifacts; let context and user intent guide style.
"""
```

我們用一個 agent 需要引用來源的例子。Agent 會上網搜尋 **"How many US Federal holidays are there in the year 2026?"** 

**注意：** 使用 `web_search` tool 是選用的，只有在你的使用情境需要搜尋外部資訊時才需要加入。如果你的應用程式不需要網路存取或外部查詢，可以省略 `tools=[{"type": "web_search"}]` 這個參數。

```python
response = client.responses.create(
  model="gpt-5.2",
  instructions=factbased_prompt,
  input="Per the US Federal Government website, how many holidays are there in the year 2026?",
  tools=[{"type": "web_search"}],
)

display(HTML(markdown.markdown(response.output_text)))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 4 Exploratory

充滿探索精神和熱情，清楚解釋概念，同時慶祝知識與發現。

**最適合：** 內部文件 copilot、新人上手協助、技術卓越、訓練／賦能。

**為什麼有效：** 強化探索和深入理解；在團隊中培養技術好奇心和知識分享。


```python
exploratory_prompt="""
You are an enthusiastic and deeply knowledgeable AI Agent who delights in explaining concepts with clarity and context. 

Aim to make learning enjoyable and useful by balancing depth with approachability. 

Use accessible language, add brief analogies or “fun facts” where helpful, and encourage exploration or follow-up questions.

Prioritize accuracy, depth, and making technical topics approachable for all experience levels. 

If a concept is ambiguous or advanced, provide explanations in steps and offer further resources or next steps for learning. 

Structure your responses logically and use formatting (like lists, headings, or tables) to organize complex ideas when helpful. 

Do not use humor for its own sake, and avoid excessive technical detail unless the user requests it. 

Always ensure examples and explanations are relevant to the user’s query and context.
"""
```

我們舉一個要 agent 詳細解釋的例子："What is the weather usually like in San Francisco around January?"

```python
response = client.responses.create(
  model="gpt-5.2",
  instructions=exploratory_prompt,
  input="What is the weather usually like in San Francisco around January?",
  tools=[{"type": "web_search"}],
)

display(HTML(markdown.markdown(response.output_text)))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 結論

Agent personality 是塑造系統在 production 行為的關鍵槓桿。在 system 或 developer prompt 層級明確定義 personality instructions，你就能穩定地引導語氣、冗長程度、結構和決策風格，而不會干擾任務專屬的 instructions 或輸出格式。

這份 cookbook 示範了不同的 personality 設定檔，像 Professional、Efficient、Fact-based 和 Exploratory，如何乾淨地對應到真實使用情境，從企業工作流程、開發者工具，到研究助理和內部賦能。 

實務上，最有效的做法是從一個最小、範圍明確、符合目標工作負載的 personality 開始，用 evals 驗證它，再隨需求變化有意識地演進。避免讓 personality 承載任務邏輯或領域規則，要讓它專注在 agent 怎麼回應，而不是它必須做什麼。

用心運用的話，agent personality 能讓你打造的系統不只更有用，在真實 production 環境中也更可預測、更可擴展、更值得信賴。


## 重點整理
- Personality 管的是怎麼說，不是做什麼，任務邏輯和輸出格式不該放進去。
- 寫在 system 或 developer instructions 層級，才能穩定控制所有互動的風格。
- 不同工作負載適合不同 personality，例如批次自動化用 Efficient，需要引用來源的用 Fact-Based。
- 從最小可用的 personality 開始，用 evals 驗證，再慢慢調整。
- 任務明確指定的格式（email、JSON、程式碼）優先於 personality。

## 練習
1. 把 Professional 的任務換成你自己的情境（例如公告放假），比較它和 Efficient 輸出的長度差異。
2. 拿掉 Fact-Based 範例中的 `tools=[{"type": "web_search"}]`，看回答對年份問題的可靠度怎麼變。
3. 自己寫第五種 personality 的 instructions（例如 Socratic，只用提問引導），套到同一個問題上測試。
