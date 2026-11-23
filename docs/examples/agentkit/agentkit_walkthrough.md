---
translated: true
source: examples/agentkit/agentkit_walkthrough.ipynb
---

# 用 AgentKit 建置、部署、優化 agentic workflow

> 原文：[examples/agentkit/agentkit_walkthrough.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agentkit/agentkit_walkthrough.ipynb)



## 這篇在做什麼

用 AgentKit 的三個元件走完一輪完整流程：先在 Agent Builder 拉出一個三個 agent 串接的 workflow（讀履歷、分析職涯落差、推薦線上課程），再用 ChatKit 把它嵌進自己的前端聊天 app，最後用 Evals 做 prompt optimization 跟 trace grading 改善表現。

## 學完你會

- 在 Agent Builder 建多 agent workflow，設定 reasoning、structured output、Web Search，並用 Preview 測試跟 Publish。
- 用 ChatKit starter template 加上 workflow ID，部署聊天 app，並用 theme、Widget Builder 自訂外觀跟課程卡片。
- 用 Datasets 的 model grader 做單一 agent 的 prompt optimization，再用 trace grading 評估整條 workflow。

## 開跑前

- 一個可以用 Agent Builder、ChatKit、Evals 的 OpenAI Platform 帳號。
- 部署前端要有 Node.js 跟 npm，並把 workflow ID 填進 `.env.local` 的 `NEXT_PUBLIC_CHATKIT_WORKFLOW_ID`。

## 簡介

在 DevDay 2025，我們推出了 [AgentKit](https://openai.com/index/introducing-agentkit/)，這是一整套讓開發者跟企業建置、部署、優化 agent 的工具。AgentKit 是一組互相連動的積木：

* [Agent Builder](https://platform.openai.com/docs/guides/agents/agent-builder)：用視覺化方式建置跟迭代 agent workflow  
* [ChatKit](https://platform.openai.com/docs/guides/chatkit)：輕鬆把聊天式 workflow 嵌進你的 app  
* [Evals](https://platform.openai.com/docs/guides/evals?api-mode=responses)：改善 LLM 應用的表現

**這份 cookbook 會從頭到尾走一遍 AgentKit，我們會建置、部署並優化一個 app。你會了解 AgentKit 的各個積木怎麼串在一起，讓你更快、更穩地把 agentic workflow 推上正式環境。** 

步驟如下：

1. 在 Agent Builder 建一個 workflow，當作 app 的後端  
2. 用 ChatKit web component 部署前端聊天 app  
3. 在 Evals 用 prompt optimization 跟 trace grading 優化 workflow 的表現

## 用 Agent Builder 建多 agent workflow

先用 Agent Builder 建出支撐 app 的初始 workflow。Agent Builder 是一個視覺化畫布，你可以拖放 node 來設計 agentic workflow。更多功能跟支援的 node 清單可以看[這裡](https://platform.openai.com/docs/guides/agent-builder)，這份 cookbook 只做一個簡單的 workflow：三個 Agent node 依序執行。

我們要做一個靠精選學習推薦來幫人加速職涯發展的 app。使用者上傳履歷、說出理想工作，就會根據他們需要補強的技能，收到一組精選課程。所以我們會建三個 agent： 

1. **履歷擷取** agent：解析上傳的履歷，擷取相關技能跟經歷  
2. **職涯分析** agent：分析他們相對於目標工作的知識落差  
3. **課程推薦** agent：用上游的資訊推薦相關的線上課程。

我們依序建每一個 agent。

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_workflow.png" /></center></div>

### 1. 履歷擷取 agent

這個 agent 負責解析上傳的履歷，回傳技能跟經歷的結構化輸出，供下游分析使用。我們用下面的 prompt：


```text
Extract and summarize information from the input resume, organizing your output by category and providing context where available.
- Analyze the provided input to identify skills and professional experiences.
- For each skill or experience, extract the supporting context or evidence from the text (e.g., for the skill of Python, context might be “used Python in data analysis for three years at [Company]”).
- Continue reviewing the text until all skills and experiences are extracted.
```

這個 agent 用 `gpt-5`，reasoning 先設 `minimal`，之後需要的話隨時可以換模型。我們也會強制結構化回應（把 Output format 選成 JSON 並加上 schema），讓模型回傳我們要的精確資料格式。（這個結構化輸出的 JSON schema 在[這裡](https://cdn.openai.com/cookbook/agent_walkthrough/Skills_schema.json)。）

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_json_schema.png" width="50%"/></center></div>

### 2. 職涯分析 agent

這個 agent 分析一個人要達成目標職位或職涯目標，在技能跟知識上的落差。這個 agent 一樣用 `gpt-5`，reasoning effort 選 `low`，這個程度的分析用它就夠了，回應速度也夠快。

```text
Your role is to analyze skill and knowledge gaps for an individual to progress to a desired professional or career goal. 

You will receive a list of the already-obtained skills and experiences of an individual, as well as a description of the goal. First, understand the goal and analyze the critical skills or knowledge areas required for achieving the goal. Then, compare the requirements to what the individual already possesses. 

Return a list of the top 3-5 skills that the individual does not possess, but are important for their professional goal. Along with each skill, include a brief description.

Individual's expressed goal: 
{{workflow.input_as_text}}

Already-obtained skills and experiences:
{{input.output_text}}
```

注意我們的 prompt 包含用 {{大括號}} 包起來的前面 node 的 context。你也可以點「Add context」，查看能提供給模型的 context 變數。

### 3. 課程推薦 agent

這個 agent 會用 web search tool 找出符合技能落差的線上訓練課程。我們用 `gpt-5`、`minimal` reasoning，並幫這個 agent 配上 Web Search。

```text
Your job is to identify and recommend online training courses that help develop one or more of the skills identified. Given the list of required skills and descriptions below, return a list of 3-5 online courses along with course details.

Skills: {{input.output_text}}
```

## 測試 workflow

**初始 workflow 建好了，可以用 Agent Builder 的 Preview 功能試跑！** 我們先 Publish workflow，這會建立一份有名稱、有版本的副本（附唯一的 workflow ID），可以分享給同事，也可以部署或在版本之間回退。

Preview 讓你在 Agent Builder 裡，用跟聊天使用者一樣的方式跟 workflow 互動。上傳履歷、輸入理想工作的描述再點 Submit，就會看到 workflow 在畫面左邊一個個 node 逐步執行，右邊則看得到每個 node 的輸出。

這裡我上傳了一位想成為學區督學的老師的履歷當範例。


<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_workflow_preview.png" /></center></div>

我們可以看著 workflow 依序走過履歷解析、技能分析跟 web search。workflow 跑完後，如預期看到一份符合搜尋條件的線上課程清單。

**一切正常，可以部署 app 了！** 先確定你做的修改都已 publish，並取得 workflow ID。需要再找 ID 時，可以點畫面上方的「Code」。

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_code.png" /></center></div>

另外，你可以用「Agents SDK」分頁取得剛建好的 workflow 的程式碼，它是用 Agents SDK 套件（[JavaScript/TypeScript](https://github.com/openai/openai-agents-js) 或 [Python](https://github.com/openai/openai-agents-python)）實作的。如果你想在自己的環境跑 workflow，或加上自訂功能繼續開發，這是個好選擇。（不過這樣你會錯過整合使用 AgentKit 的一些好處，後面會說明。）

## 用 ChatKit 部署聊天 app

部署 app 時，我們用 [ChatKit starter template](https://github.com/openai/openai-chatkit-starter-app)，它能幫我們用 ChatKit web component 快速架起聊天 app。

在那之前，先說明 AgentKit 這一整套工具提供的完整部署選項。我們已經看過怎麼在 Agent Builder 建 workflow，然後直接在工具裡執行（Preview），或匯出成 Agents SDK 程式碼在自己的環境用。接下來示範怎麼用 Agent Builder 的 workflow ID，在你自己的前端建一個聊天體驗，並以你建好的 workflow 當後端。（順帶一提，你也可以只用 ChatKit SDK 提供的完整聊天 GUI，不接 workflow 後端，細節看[這裡](https://platform.openai.com/docs/guides/custom-chatkit)。）

所以我們從 ChatKit starter template 開始，把 workflow 接進去。starter template 讓我們很容易用剛建好的 workflow 架起聊天 app。照 repo 的 [Getting Started](https://github.com/openai/openai-chatkit-starter-app?tab=readme-ov-file#getting-started) 說明做：把 Agent Builder 的 workflow ID 填成 `.env.local` 裡 `NEXT_PUBLIC_CHATKIT_WORKFLOW_ID` 的值，再跑 `npm install` 跟 `npm run dev` 測試 app。

短短幾分鐘，workflow 就嵌進前端聊天介面並跑起來了！

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_chat_app.png" /></center></div>

## 快速迭代 workflow 跟使用者體驗

AgentKit 最有價值的地方之一，是能讓你很快地實驗、迭代、改善 agentic 應用。我們做幾個小改動，讓 app 功能更好，聊天體驗更豐富。

**首先加上自訂 theme**，讓前端有自己的風格，同時保留原生的聊天體驗。這裡有個很好用的資源是 [ChatKit Studio](https://chatkit.studio/)，裡面有可以探索 ChatKit 自訂選項的 playground、Widget Builder（等下會用到），還有範例 app 跟作品集可以參考。要取得自訂 theme，我們用 ChatKit [Playground](https://chatkit.studio/playground) 視覺化地選好想要的樣式，再點 Playground 畫面上方的 `</>` 圖示取得設定程式碼。 

我們會用這段程式碼裡的 `theme` 物件，覆蓋 [lib/config.ts](https://github.com/openai/openai-chatkit-starter-app/blob/main/lib/config.ts) 裡的預設 theme。在同一個檔案裡，我們也把 starter prompt、問候文字跟輸入框 placeholder 改成更合適的內容：

```text
export const GREETING = "Upload your resume, and tell me the job you're looking to get!";
export const PLACEHOLDER_INPUT = "Describe your dream job, and don't forget to attach your resume!"; 
```

**接著設計自訂 widget**，用更直觀的格式顯示推薦課程，讓使用者更容易理解跟比較。我們可以用 [Widget Builder](https://widgets.chatkit.studio/)，只要描述想要的輸出，就能得到 LLM 生成的起點，再進一步編輯。這個範例要把課程用結構清楚的列表呈現，推薦下方再顯示一段摘要。在 Widget Builder 裡不只看得到 widget 程式碼（左上）、範例資料（左下），還有資料在 widget 裡呈現給終端使用者的樣子（右邊）。

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_widget_builder.png" /></center></div>

設計滿意後，就可以下載 .widget 檔。（下面截圖用的檔案在[這裡](https://cdn.openai.com/cookbook/agent_walkthrough/Course%20recommendation.widget)。）

要在聊天 app 實際用上我們設計的 widget，**必須讓 workflow 在推薦 agent 的回應裡回傳 widget component**。所以我們回到 `Course recommendations` agent，把 Output format 選成 `Widget`，並上傳 .widget 檔。

agent 會自動知道要輸出填充 widget 所需的 JSON 格式。不過我們得更新 agent 的 prompt，更精確地告訴模型每個課程需要取得哪些資訊。 

```text
Your job is to identify and recommend online training courses that help develop one or more of the skills identified. Given the list of required skills, return a list of 3-5 online courses along with course details including course name, provider (school or program), recommendation reason (a brief sentence on why you're recommending the course), course format, and URL. In addition to the list of courses, share a few-sentence summary of the recommendations you're making. 
```

最後，因為處理的是履歷，我們要在 workflow 加一個 guardrail，確保不會把個人可識別資訊（PII）傳到不該去的地方。我們把這個 guardrail 插在履歷解析 agent 跟職涯分析 agent 之間，讓履歷 agent 下游的任何環節都拿不到姓名、聯絡方式等 PII。


<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_guardrails.png" /></center></div>

## 用 prompt optimization 跟 trace grading 改善系統表現

現在來看 Evals 的原生整合，怎麼讓你輕鬆優化單一 agent 跟整個 workflow。假設我們的聊天 app 已經部署了，可能先給一批內部使用者或 beta 測試者用，我們也有一些使用者跟系統互動的真實範例。

如果這個應用要發展成效能跟品質都很關鍵的正式系統，我們會更早、更有系統地把 eval 放進開發流程。（想了解怎麼建立初始 eval 跟 ground truth、把 eval 對應到商業指標，並逐步改善系統以達成商業目標，可以看 [Eval Driven System Design](https://cookbook.openai.com/examples/partners/eval_driven_system_design/receipt_inspection)。）

不過這份 cookbook 比較不談 eval 在 LLM 應用開發裡的技巧，重點是 AgentKit 怎麼讓你更輕鬆地實作這些技巧。我們用兩種方式改善表現：先用 prompt optimization 工具**優化 workflow 裡的單一 agent node**，再用 trace grading **優化整個 workflow**。

### 單一 agent 優化

我們想深入 Course recommendations agent，看看能不能提升它給使用者的推薦品質。我們從測試環境挑出一些這個 agent 的範例 prompt。（你也可以在 API 平台的 [Logs 分頁](https://platform.openai.com/logs?api=responses)取得完成的紀錄。這份 cookbook 用的資料集可以從[這裡](https://cdn.openai.com/cookbook/agent_walkthrough/course_recommendations_dataset.csv)取得。）

可以直接從 Agent Builder 開始優化 agent。選 Course recommendations agent，點 agent 視窗右下角的「Evaluate」，就會直接進到 Evals 裡的 **Datasets** 功能。 

可以看到 agent 的設定已經複製過來，可以開始優化了。先上傳含範例 prompt 的資料檔（欄位名稱要跟你的輸入、輸出變數一致），再點「Generate output」產生回應。

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_generate_output.png" /></center></div>

接下來建立一些 **human annotation（人工標註）** 跟 **model grader（模型評分器）**。選「Columns」新增 Rating（讚/倒讚）跟 Feedback（文字輸入）欄位，並手動檢視樣本，填上高品質的回饋。我們也會加幾個 model grader，依我們指定的標準自動評估 agent 的輸出。以這個範例來說，我們可能關心課程推薦是否跟找出的技能落差相關（relevance）、是否涵蓋所有技能落差（coverage），以及呈現的推薦摘要是否合適（style）。

下面是各項標準的 model grader prompt 範例： 

```text
[relevance] You are evaluating whether a list of recommended courses is relevant to the skills described. Return a pass if all courses are relevant to at least one skill, and fail otherwise.

[coverage] You are evaluating whether a list of recommended courses covers all of the skills described. Return a pass if all of the skills are covered by at least one course, and fail otherwise.

[summary] You are evaluating whether the summary recommendation provided is relevant, thoughtful, and related to the recommended courses proposed. Evaluate the summary recommendation on a scale of 0 to 1, with 1 being the highest quality. 
```

model grader 用 GPT-5，並替摘要 grader 設 0.7 的門檻。

接著選 Grade > All graders，對系統輸出跑這些 grader。評分進行時，格子會逐漸填入，顯示每個範例在各項 model grader 標準上的得分。

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_grading.png" /></center></div>

**接下來是神奇的地方：點 Optimize，就能依我們提供的回饋（包含 model grader 的輸出跟人工回饋），自動改寫 prompt。** 

看新的 prompt，可以發現多了 **Requirements** 跟 **Output** format 兩個區塊，指示模型把課程描述寫得更具體，並盡量更完整涵蓋各項技能。 

```text
Requirements:

- Use the web search tool to find and verify real, currently available online courses and their direct URLs.
- Return 3–5 courses that collectively cover the skills. If a course spans multiple skills, indicate it. 
- Be specific and concise. Each course description must be one sentence (max 35 words) focused on outcomes and topics tied to the skills. 
- Provide plain text only; no citations or references.

Output format:

1) Summary (2–4 sentences) explaining how the selections address the skills and any coverage tradeoffs. 
2) Courses (3–5 items). For each course, include exactly:` 
   - Course name — Provider (school or program)
   - Description: [one sentence, max 35 words]  
   - URL: [direct course page]
   - Skills covered: [list skill names from below]
```

現在點 Update，就能把新 prompt 自動放進 Agent Builder 的 workflow。**只花幾分鐘，我們就用真實的 prompt 範例跟回饋自動改善系統表現，而且全部都在 Agent Builder 跟 Evals 工具裡完成。**

（雖然這份 cookbook 是用評分輸出自動優化 prompt，但實務上檢視具體的失敗案例通常很有幫助，可以了解模型在哪些地方會出錯。這種分析能幫我們產生更精準的人工或模型評分回饋，甚至合成資料，來改善特定失敗模式的表現。）


### 整個 workflow 優化

等我們對每個 agent node 的表現都滿意後，就可以把注意力轉到整個 workflow。

以前，要分析、改善包含多個 agent 的複雜 workflow，你得讀完整條 trace，才能搞清楚系統到底在哪裡、為什麼失敗。trace 很多的時候，這個過程非常耗時。

用 **trace grading**，現在可以用自動化的 model grading，對整批 trace 做端到端評估。我們建立 grader 來描述想修正的行為，並自動對整個資料集執行這些 grader。

開始時，回到 Agent Builder 裡的 workflow，點畫面上方的 Evaluate。這能讓我們深入看 workflow 執行時產生的 trace，包含所有 node 的輸入跟輸出（這裡就是每個 agent 的 prompt 跟回應）。 

我們可以建立針對整條 trace 的 grader，替**橫跨多個 agent** 的端到端 workflow 定義評估標準。例如，確保最終的推薦摘要（agent 3 的輸出）跟使用者一開始提到的職涯目標（agent 1 的輸入）相關。也可以檢查推薦的課程（agent 3 的輸出）沒有重複使用者已有的技能（agent 1 的輸出）。 

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_traces.png" /></center></div>

如果 workflow 有條件判斷或 while 迴圈，還可以評估更複雜的多步驟行為，例如客服 agent 跟使用者來回超過三輪就該轉給主管。

訂好完整的評分標準後，選 Grade all 對 trace 評分。這會帶我們到 Evaluations 分頁，可以看到新建立了一個 eval，也啟動了一次 eval run。

<div><center><img src="https://cdn.openai.com/cookbook/agent_walkthrough/agentkit_walkthrough_trace_evals.png" /></center></div>

然後可以深入失敗案例的 workflow trace，了解那次 workflow 為什麼失敗、怎麼改善系統來避免。這個做法靠反覆找出失敗模式、評估系統表現、針對性改進，讓你更有效率地優化複雜 workflow。

## 回顧與資源

我們示範了 **Agent Builder**、**ChatKit** 跟 **Evals** 如何一起幫你建置、部署、優化 agentic workflow。

以一個具體範例來說，這個職涯發展 app 會分析履歷、找出技能落差並推薦線上課程。我們看到 Agent Builder 讓設計跟建置多 agent workflow 變得容易，ChatKit 讓我們把這些 workflow 嵌進豐富又可自訂的聊天 UI，Evals 則用真實資料做 prompt optimization 跟 trace grading，把整個迴圈閉起來。

想了解更多，下面是這份 cookbook 提到的一些資源：

* [Agent Builder documentation](#)
* [ChatKit starter template](#)
* [ChatKit Studio](#)
* [Agents SDK](#)
* [Evals](#)

Happy building!

## 重點整理

- AgentKit 三個元件各管一段：Agent Builder 建 workflow、ChatKit 把它嵌進前端、Evals 做優化，用同一個 workflow ID 串起來。
- workflow 要先 Publish 才有版本跟 workflow ID，之後可以分享、部署或回退。
- 每個 agent node 可以各自選模型、reasoning effort、output format（JSON schema 或 Widget）跟 tool，不需要一刀切。
- 用 guardrail 擋 PII，可以放在 workflow 中間，讓下游 agent 看不到敏感資料。
- 單一 agent 用 human annotation 加 model grader 做 prompt optimization，整條 workflow 用 trace grading 看跨 agent 的端到端行為。

## 練習

1. 在 `lib/config.ts` 改掉 starter prompt 跟問候文字，換成符合你自己情境（例如不同職業）的內容，重跑 `npm run dev` 看效果。
2. 在 Agent Builder 把職涯分析 agent 的 reasoning effort 從 `low` 改成 `medium`，用同一份履歷在 Preview 比較輸出差異。
3. 在 Evals 的 trace grading 新增一個 grader，檢查推薦課程是否真的對應到職涯分析 agent 找出的每一項技能落差，跑 Grade all 後看失敗的 trace。
