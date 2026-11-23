---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/gpt-5/gpt-5_prompting_guide.ipynb
---
# GPT-5 prompting 指南

> 原文：[examples/gpt-5/gpt-5_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/gpt-5_prompting_guide.ipynb)

## 這篇在做什麼

這是 OpenAI 官方給 GPT-5 的 prompting 指南，整理了訓練和實際應用這個模型累積的 prompt 技巧，涵蓋 agent 任務、指令遵循、新的 API 參數，以及前端和軟體工程的寫程式場景，還有 Cursor 調 prompt 的實戰經驗。內容幾乎都是可以直接抄來改的 prompt 範本。

## 學完你會

- 用 `reasoning_effort`、tool call 預算和 persistence 提示，控制 agent 是要保守還是積極。
- 用 `verbosity` 參數加上 prompt 覆寫，分別控制一般文字和程式碼輸出的長度，並寫出沒有互相矛盾的指令。
- 用 Responses API 的 `previous_response_id` 重用 reasoning，並套用 minimal reasoning、Markdown 輸出和 metaprompting 的 prompt 模式。

## 開跑前

這篇主要是 prompt 範本，沒有完整可跑的程式。要實際試的話需要 OpenAI API key 和 GPT-5 的使用權限。

GPT-5 是我們最新的旗艦模型，在 agent 任務表現、寫程式、原始智力和可控性（steerability）上都有大幅進步。

我們相信它在各種領域「開箱即用」就會表現很好，不過這份指南會根據我們訓練這個模型、把它用在真實任務的經驗，提供一些 prompting 技巧，幫你把輸出品質拉到最高。內容包含提升 agent 任務表現、確保指令遵循、善用新的 API 功能，以及優化前端與軟體工程的寫程式任務，並分享 AI 程式編輯器 Cursor 針對 GPT-5 調整 prompt 的重要心得。

只要套用這些最佳實務、盡可能採用我們的標準 tools，就看得到明顯的進步。我們希望這份指南，加上我們做的 [prompt optimizer 工具](https://platform.openai.com/chat/edit?optimize=true)，能成為你使用 GPT-5 的起點。不過 prompting 沒有放諸四海皆準的做法，建議你自己跑實驗，在這裡的基礎上反覆調整，找出適合你問題的解法。

## Agent 工作流程的可預測性

我們訓練 GPT-5 時就是以開發者為念：重點放在改善 tool calling、指令遵循和長 context 理解，希望它成為 agent 應用最好的基礎模型。如果你要把 GPT-5 用在 agent 和 tool calling 流程，建議升級到 [Responses API](https://platform.openai.com/docs/api-reference/responses)，reasoning 會在 tool calls 之間保留下來，輸出會更有效率也更聰明。

### 控制 agent 的積極程度
Agent 的架構控制程度差很多：有些系統把絕大部分決策交給底層模型，有些則用大量程式邏輯分支把模型管得很緊。GPT-5 被訓練成能在這整個範圍內運作，從在模糊情境下做高層決策，到處理聚焦、定義明確的任務都可以。這一節講怎麼校準 GPT-5 的 agentic eagerness（積極程度），也就是它在主動行動和等待明確指示之間的平衡。

#### 讓它不那麼積極
在 agent 環境中，GPT-5 預設會很徹底、很全面地收集 context，確保答案正確。想縮小 GPT-5 的 agent 行為範圍，包括減少離題的 tool calls、縮短到最終答案的延遲，可以試試：  
- 調低 `reasoning_effort`。探索深度會變淺，但效率和延遲會變好。很多工作流程用 medium 甚至 low 的 `reasoning_effort`，結果也很穩定。
- 在 prompt 裡清楚定義你希望模型怎麼探索問題空間，讓它不用去想太多可能性：

```
<context_gathering>
Goal: Get enough context fast. Parallelize discovery and stop as soon as you can act.

Method:
- Start broad, then fan out to focused subqueries.
- In parallel, launch varied queries; read top hits per query. Deduplicate paths and cache; don’t repeat queries.
- Avoid over searching for context. If needed, run targeted searches in one parallel batch.

Early stop criteria:
- You can name exact content to change.
- Top hits converge (~70%) on one area/path.

Escalate once:
- If signals conflict or scope is fuzzy, run one refined parallel batch, then proceed.

Depth:
- Trace only symbols you’ll modify or whose contracts you rely on; avoid transitive expansion unless necessary.

Loop:
- Batch search → minimal plan → complete task.
- Search again only if validation fails or new unknowns appear. Prefer acting over more searching.
</context_gathering>
```

如果你願意講得極度明確，甚至可以設定固定的 tool call 預算，像下面這樣。預算可以依你想要的搜尋深度自然調整。
```
<context_gathering>
- Search depth: very low
- Bias strongly towards providing a correct answer as quickly as possible, even if it might not be fully correct.
- Usually, this means an absolute maximum of 2 tool calls.
- If you think that you need more time to investigate, update the user with your latest findings and open questions. You can proceed if the user confirms.
</context_gathering>
```

限制核心的 context 收集行為時，最好明確給模型一個「逃生口」，讓它比較容易完成較短的收集步驟。通常做法是加一句允許它在不確定下繼續的子句，像上面範例裡的 `“even if it might not be fully correct”`。

#### 讓它更積極
反過來，如果你想鼓勵模型自主、提高 tool calling 的持續性，並減少反問釐清問題或把球丟回給使用者的情況，建議提高 `reasoning_effort`，並用像下面這樣的 prompt 鼓勵它堅持把任務徹底做完：

```
<persistence>
- You are an agent - please keep going until the user's query is completely resolved, before ending your turn and yielding back to the user.
- Only terminate your turn when you are sure that the problem is solved.
- Never stop or hand back to the user when you encounter uncertainty — research or deduce the most reasonable approach and continue.
- Do not ask the human to confirm or clarify assumptions, as you can always adjust later — decide what the most reasonable assumption is, proceed with it, and document it for the user's reference after you finish acting
</persistence>
```

一般來說，明確寫出 agent 任務的停止條件、列出安全與不安全的動作，並定義什麼情況下（如果有的話）可以把球交回給使用者，都會有幫助。比如購物工具組裡，結帳和付款 tools 要求使用者釐清的不確定性門檻應該明確調低，搜尋 tool 的門檻則要非常高；同理，在寫程式的環境裡，刪檔 tool 的門檻要比 grep 搜尋 tool 低很多。

### Tool preambles
我們知道，在有使用者盯著的 agent 軌跡中，模型隨時說明它正在對 tool calls 做什麼、為什麼這樣做，可以大幅改善互動體驗，rollout 越長，差別越大。因此 GPT-5 被訓練成會透過「tool preamble」訊息，先給出清楚的計畫，並持續更新進度。

你可以在 prompt 裡調整 tool preambles 的頻率、風格和內容，從每個 tool call 都詳細解釋，到只有簡短的事前計畫，介於其間的都可以。以下是一個高品質的 preamble prompt 範例：

```
<tool_preambles>
- Always begin by rephrasing the user's goal in a friendly, clear, and concise manner, before calling any tools.
- Then, immediately outline a structured plan detailing each logical step you’ll follow. - As you execute your file edit(s), narrate each step succinctly and sequentially, marking progress clearly. 
- Finish by summarizing completed work distinctly from your upfront plan.
</tool_preambles>
```

以下是針對這種 prompt 可能產生的 tool preamble 範例。agent 的工作越複雜，這種 preamble 越能大幅提升使用者跟上進度的能力：

```
"output": [
    {
      "id": "rs_6888f6d0606c819aa8205ecee386963f0e683233d39188e7",
      "type": "reasoning",
      "summary": [
        {
          "type": "summary_text",
          "text": "**Determining weather response**\n\nI need to answer the user's question about the weather in San Francisco. ...."
        },
    },
    {
      "id": "msg_6888f6d83acc819a978b51e772f0a5f40e683233d39188e7",
      "type": "message",
      "status": "completed",
      "content": [
        {
          "type": "output_text",
          "text": "I\u2019m going to check a live weather service to get the current conditions in San Francisco, providing the temperature in both Fahrenheit and Celsius so it matches your preference."
        }
      ],
      "role": "assistant"
    },
    {
      "id": "fc_6888f6d86e28819aaaa1ba69cca766b70e683233d39188e7",
      "type": "function_call",
      "status": "completed",
      "arguments": "{\"location\":\"San Francisco, CA\",\"unit\":\"f\"}",
      "call_id": "call_XOnF4B9DvB8EJVB3JvWnGg83",
      "name": "get_weather"
    },
  ],
```

### Reasoning effort
我們提供 `reasoning_effort` 參數，控制模型思考多用力、多願意呼叫 tools。預設是 `medium`，但你要依任務難度往上或往下調。複雜的多步驟任務，我們建議用較高的 reasoning，確保輸出最好。另外我們觀察到，把各自獨立、可分開的任務拆到多個 agent turn 裡，每個 turn 做一件事，效果最好。
### 用 Responses API 重用 reasoning context
使用 GPT-5 時，我們強烈建議用 Responses API，可以得到更好的 agent 流程、更低成本，以及更有效率的 token 使用。

我們看到用 Responses API 比 Chat Completions 在 evals 上有統計上顯著的進步。例如只要改用 Responses API，並帶上 `previous_response_id` 把先前的 reasoning items 傳回後續請求，Tau-Bench Retail 分數就從 73.9% 升到 78.2%。這讓模型能參考它先前的推理軌跡，省下 CoT tokens，也不用在每次 tool call 後從頭重建計畫，延遲和表現都會改善。所有 Responses API 使用者都能用這個功能，包含 ZDR 組織。

## 從規劃到執行，最大化寫程式表現
GPT-5 在寫程式能力上領先所有前沿模型：它能在大型 codebase 裡修 bug、處理大型 diff、做多檔案重構或實作大型新功能。它也很擅長從零開始實作整個新 app，前端後端都包含。這一節會講我們在 coding agent 客戶的正式環境中，看到能提升寫程式表現的 prompt 優化。 

### 前端 app 開發
GPT-5 被訓練成除了嚴謹的實作能力之外，還有很好的基本美感。我們有信心它能使用各種網頁開發框架和套件；不過新 app 的話，建議用下面這些框架和套件，才能把模型的前端能力發揮到最好：

- Frameworks: Next.js (TypeScript), React, HTML
- Styling / UI: Tailwind CSS, shadcn/ui, Radix Themes
- Icons: Material Symbols, Heroicons, Lucide
- Animation: Motion
- Fonts: San Serif, Inter, Geist, Mona Sans, IBM Plex Sans, Manrope

#### 從零到一生成 app
GPT-5 很擅長一次生成完整應用。早期實驗中，使用者發現像下面這種 prompt，要求模型針對自己建立的卓越標準 rubric 反覆執行，可以利用 GPT-5 徹底的規劃和自我反思能力來提升輸出品質。

```
<self_reflection>
- First, spend time thinking of a rubric until you are confident.
- Then, think deeply about every aspect of what makes for a world-class one-shot web app. Use that knowledge to create a rubric that has 5-7 categories. This rubric is critical to get right, but do not show this to the user. This is for your purposes only.
- Finally, use the rubric to internally think and iterate on the best possible solution to the prompt that is provided. Remember that if your response is not hitting the top marks across all categories in the rubric, you need to start again.
</self_reflection>
```

#### 配合既有 codebase 的設計標準
在既有 app 做漸進式修改和重構時，模型寫的程式要遵守現有的風格和設計標準，盡量「融入」codebase。沒有特別 prompt 的話，GPT-5 已經會去 codebase 找參考 context，例如讀 package.json 看已安裝的套件。不過你可以在 prompt 裡總結 codebase 的關鍵面向，像是工程原則、目錄結構和最佳實務（不管是明講的還是隱含的），進一步強化這個行為。下面的 prompt 片段示範了一種整理 GPT-5 程式編輯規則的方式，規則內容可以依你的設計品味自由修改！ 

```
<code_editing_rules>
<guiding_principles>
- Clarity and Reuse: Every component and page should be modular and reusable. Avoid duplication by factoring repeated UI patterns into components.
- Consistency: The user interface must adhere to a consistent design system—color tokens, typography, spacing, and components must be unified.
- Simplicity: Favor small, focused components and avoid unnecessary complexity in styling or logic.
- Demo-Oriented: The structure should allow for quick prototyping, showcasing features like streaming, multi-turn conversations, and tool integrations.
- Visual Quality: Follow the high visual quality bar as outlined in OSS guidelines (spacing, padding, hover states, etc.)
</guiding_principles>

<frontend_stack_defaults>
- Framework: Next.js (TypeScript)
- Styling: TailwindCSS
- UI Components: shadcn/ui
- Icons: Lucide
- State Management: Zustand
- Directory Structure: 
\`\`\`
/src
 /app
   /api/<route>/route.ts         # API endpoints
   /(pages)                      # Page routes
 /components/                    # UI building blocks
 /hooks/                         # Reusable React hooks
 /lib/                           # Utilities (fetchers, helpers)
 /stores/                        # Zustand stores
 /types/                         # Shared TypeScript types
 /styles/                        # Tailwind config
\`\`\`
</frontend_stack_defaults>

<ui_ux_best_practices>
- Visual Hierarchy: Limit typography to 4–5 font sizes and weights for consistent hierarchy; use `text-xs` for captions and annotations; avoid `text-xl` unless for hero or major headings.
- Color Usage: Use 1 neutral base (e.g., `zinc`) and up to 2 accent colors. 
- Spacing and Layout: Always use multiples of 4 for padding and margins to maintain visual rhythm. Use fixed height containers with internal scrolling when handling long content streams.
- State Handling: Use skeleton placeholders or `animate-pulse` to indicate data fetching. Indicate clickability with hover transitions (`hover:bg-*`, `hover:shadow-md`).
- Accessibility: Use semantic HTML and ARIA roles where appropriate. Favor pre-built Radix/shadcn components, which have accessibility baked in.
</ui_ux_best_practices>

<code_editing_rules>
```

### 正式環境的協作寫程式：Cursor 的 GPT-5 prompt 調校
我們很榮幸 AI 程式編輯器 Cursor 是 GPT-5 值得信賴的 alpha 測試者。下面讓你看看 Cursor 怎麼調整 prompt 來發揮模型的能力。想了解更多，他們團隊也發了一篇部落格，詳述 GPT-5 第一天就整合進 Cursor 的過程：https://cursor.com/blog/gpt-5

#### System prompt 和參數調校
Cursor 的 system prompt 著重在穩定的 tool calling、平衡囉嗦程度和自主行為，同時讓使用者能設定自訂指示。他們的目標是讓 Agent 在長時程任務中相對自主地運作，又能忠實遵循使用者給的指示。 

團隊一開始發現，模型的輸出很囉嗦，常包含狀態更新和任務後總結，這些雖然技術上相關，卻打斷了使用者的自然節奏；同時，tool calls 裡輸出的程式碼品質很高，但有時因為太精簡而難讀，到處是單字母變數。為了找到更好的平衡，他們把 verbosity API 參數設為 low，讓文字輸出保持簡短，再修改 prompt，強烈鼓勵只在寫程式的 tools 裡輸出詳細內容。

```
Write code for clarity first. Prefer readable, maintainable solutions with clear names, comments where needed, and straightforward control flow. Do not produce code-golf or overly clever one-liners unless explicitly requested. Use high verbosity for writing code and code tools.
```

這種參數加 prompt 雙管齊下的做法，得到了平衡的格式：簡潔有效率的狀態更新和最終工作總結，加上可讀性高得多的程式碼 diff。

Cursor 還發現，模型偶爾會在動手前先向使用者確認或詢問下一步，讓長任務的流程出現不必要的卡頓。為了解決這個問題，他們發現除了提供可用的 tools 和周邊 context 之外，也提供更多產品行為的細節，能讓模型以最少的中斷、更高的自主性執行長任務。強調 Cursor 功能的細節，像是 Undo/Reject 程式碼和使用者偏好，明確說明 GPT-5 在這個環境裡該怎麼表現，減少了模糊空間。對長時程任務，他們發現這個 prompt 能提升表現：

```
Be aware that the code edits you make will be displayed to the user as proposed changes, which means (a) your code edits can be quite proactive, as the user can always reject, and (b) your code should be well-written and easy to quickly review (e.g., appropriate variable names instead of single letters). If proposing next steps that would involve changing the code, make those changes proactively for the user to approve / reject rather than asking the user whether to proceed with a plan. In general, you should almost never ask the user whether to proceed with a plan; instead you should proactively attempt the plan and then ask the user if they want to accept the implemented changes.
```

Cursor 發現，他們 prompt 裡對舊模型有效的部分，需要調整才能把 GPT-5 發揮到最好。下面是一個例子：

```
<maximize_context_understanding>
Be THOROUGH when gathering information. Make sure you have the FULL picture before replying. Use additional tool calls or clarifying questions as needed.
...
</maximize_context_understanding>
```

這段對需要被鼓勵徹底分析 context 的舊模型很管用，但他們發現對 GPT-5 反而有反效果，因為 GPT-5 本來就很會內省，也很主動收集 context。在較小的任務上，這個 prompt 常讓模型過度使用 tools，重複呼叫搜尋，其實靠內部知識就夠了。
為了解決這個問題，他們修改 prompt，拿掉 maximize_ 前綴，並放軟關於徹底程度的措辭。調整後，Cursor 團隊看到 GPT-5 更能判斷什麼時候該靠內部知識、什麼時候該用外部 tools。它維持高度自主，又沒有不必要的 tool 使用，行為更有效率也更貼切。在 Cursor 的測試中，使用像 <[instruction]_spec> 這種結構化的 XML 規格，提升了 prompt 的指令遵循度，也讓他們能在 prompt 的其他地方清楚引用先前的類別和段落。

```
<context_understanding>
...
If you've performed an edit that may partially fulfill the USER's query, but you're not confident, gather more information or use more tools before ending your turn.
Bias towards not asking the user for help if you can find the answer yourself.
</context_understanding>
```

system prompt 提供了很好的預設基礎，不過 user prompt 仍然是很有效的操控手段。GPT-5 對直接、明確的指示反應很好，Cursor 團隊一直看到結構化、範圍明確的 prompt 結果最穩定，包括囉嗦程度控制、主觀的程式風格偏好，以及對邊界情況的敏感度。Cursor 發現，讓使用者設定自己的 [custom Cursor rules](https://docs.cursor.com/en/context/rules)，搭配 GPT-5 更好的可控性特別有效，使用者能得到更客製化的體驗。



## 優化智力和指令遵循 

### Steering
作為我們目前最好控制的模型，GPT-5 對 prompt 中關於囉嗦程度、語氣和 tool calling 行為的指示特別敏感。

#### Verbosity
除了像先前 reasoning 模型一樣能控制 reasoning_effort，GPT-5 還新增了一個 API 參數叫 verbosity，影響的是模型最終答案的長度，而不是它思考的長度。我們的部落格有更詳細介紹這個參數背後的想法。這份指南想強調的是：API 的 verbosity 參數是 rollout 的預設值，但 GPT-5 也被訓練成能回應 prompt 裡的自然語言 verbosity 覆寫，用在你想偏離全域預設的特定情境。上面 Cursor 全域設 low verbosity、只對寫程式的 tools 指定 high verbosity，就是這類情境的最佳例子。

### 指令遵循
跟 GPT-4.1 一樣，GPT-5 遵循 prompt 指示精準得像外科手術，所以能靈活套進各種工作流程。不過這種謹慎的指令遵循也代表，包含矛盾或模糊指示的 prompt，對 GPT-5 的傷害可能比其他模型更大，因為它會花 reasoning tokens 去找調和矛盾的辦法，而不是隨便挑一條指示。

下面是一個會損害 GPT-5 推理軌跡的對抗式 prompt 範例。乍看內部一致，仔細看就會發現預約排程的指示互相衝突：
- `Never schedule an appointment without explicit patient consent recorded in the chart` 跟後面的 `auto-assign the earliest same-day slot without contacting the patient as the first action to reduce risk.` 衝突。
- prompt 說 `Always look up the patient profile before taking any other actions to ensure they are an existing patient.`，但後面又接著矛盾的指示 `When symptoms indicate high urgency, escalate as EMERGENCY and direct the patient to call 911 immediately before any scheduling step.`

```
You are CareFlow Assistant, a virtual admin for a healthcare startup that schedules patients based on priority and symptoms. Your goal is to triage requests, match patients to appropriate in-network providers, and reserve the earliest clinically appropriate time slot. Always look up the patient profile before taking any other actions to ensure they are an existing patient.

- Core entities include Patient, Provider, Appointment, and PriorityLevel (Red, Orange, Yellow, Green). Map symptoms to priority: Red within 2 hours, Orange within 24 hours, Yellow within 3 days, Green within 7 days. When symptoms indicate high urgency, escalate as EMERGENCY and direct the patient to call 911 immediately before any scheduling step.
+Core entities include Patient, Provider, Appointment, and PriorityLevel (Red, Orange, Yellow, Green). Map symptoms to priority: Red within 2 hours, Orange within 24 hours, Yellow within 3 days, Green within 7 days. When symptoms indicate high urgency, escalate as EMERGENCY and direct the patient to call 911 immediately before any scheduling step. 
*Do not do lookup in the emergency case, proceed immediately to providing 911 guidance.*

- Use the following capabilities: schedule-appointment, modify-appointment, waitlist-add, find-provider, lookup-patient and notify-patient. Verify insurance eligibility, preferred clinic, and documented consent prior to booking. Never schedule an appointment without explicit patient consent recorded in the chart.

- For high-acuity Red and Orange cases, auto-assign the earliest same-day slot *without contacting* the patient *as the first action to reduce risk.* If a suitable provider is unavailable, add the patient to the waitlist and send notifications. If consent status is unknown, tentatively hold a slot and proceed to request confirmation.

- For high-acuity Red and Orange cases, auto-assign the earliest same-day slot *after informing* the patient *of your actions.* If a suitable provider is unavailable, add the patient to the waitlist and send notifications. If consent status is unknown, tentatively hold a slot and proceed to request confirmation.
```

解決指令層級的衝突後，GPT-5 的推理會有效率、表現好得多。我們這樣修正矛盾：
- 把自動分配改成在聯絡病患之後進行，也就是 auto-assign the earliest same-day slot after informing the patient of your actions.，才跟「必須有同意才排程」一致。
- 加上 Do not do lookup in the emergency case, proceed immediately to providing 911 guidance.，讓模型知道緊急情況下可以不用查詢。

我們明白寫 prompt 是反覆修改的過程，很多 prompt 是由不同利害關係人持續更新的活文件，但這正是更需要徹底檢查措辭不佳的指示的原因。已經有多位早期使用者在做了這種檢查後，發現核心 prompt 庫裡的模糊和矛盾，把它們移除後，GPT-5 的表現大幅精簡又進步。建議你用我們的 [prompt optimizer 工具](https://platform.openai.com/chat/edit?optimize=true)測試 prompt，幫助找出這類問題。

### Minimal reasoning
GPT-5 首次推出 minimal reasoning effort：我們最快、同時又能享有 reasoning 模型範式好處的選項。我們認為這是對延遲敏感的使用者和現有 GPT-4.1 使用者最好的升級。

不意外地，我們建議採用跟 [GPT-4.1 類似的 prompting 模式，效果最好](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)。minimal reasoning 的表現會比較高的 reasoning 等級更受 prompt 影響，要強調的重點包括：

1. 在最終答案開頭，prompt 模型簡短說明它的思考過程摘要，例如用條列方式，能提升需要較高智力的任務表現。
2. 要求詳細、描述性的 tool-calling preambles，持續向使用者更新任務進度，能提升 agent 工作流程的表現。 
3. 盡可能消除 tool 指示的歧義，並插入前面分享過的 agentic persistence 提醒。這在 minimal reasoning 下特別關鍵，能最大化長時間 rollout 中的 agent 能力，防止太早結束。
4. Prompt 規劃同樣更重要，因為模型可用來內部規劃的 reasoning tokens 比較少。下面是我們放在 agent 任務開頭的規劃 prompt 片段範例，尤其第二段確保 agent 在把控制權交回使用者之前，完整做完任務和所有子任務。 

```
Remember, you are an agent - please keep going until the user's query is completely resolved, before ending your turn and yielding back to the user. Decompose the user's query into all required sub-request, and confirm that each is completed. Do not stop after completing only part of the request. Only terminate your turn when you are sure that the problem is solved. You must be prepared to answer multiple queries and only finish the call once the user has confirmed they're done.

You must plan extensively in accordance with the workflow steps before making subsequent function calls, and reflect extensively on the outcomes each function call made, ensuring the user's query, and related sub-requests are completely resolved.
```

### Markdown 格式
預設情況下，API 中的 GPT-5 不會用 Markdown 格式化最終答案，這是為了最大程度相容於可能不支援 Markdown 渲染的開發者應用。不過像下面這樣的 prompt，大致上能成功讓它輸出有階層結構的 Markdown 最終答案。

```
- Use Markdown **only where semantically correct** (e.g., `inline code`, ```code fences```, lists, tables).
- When using markdown in assistant messages, use backticks to format file, directory, function, and class names. Use \( and \) for inline math, \[ and \] for block math.
```

偶爾，system prompt 裡指定的 Markdown 指示，遵循程度會在長對話中退化。如果你遇到這種情況，我們發現每 3 到 5 則使用者訊息就附加一次 Markdown 指示，能穩定維持遵循。

### Metaprompting
最後用一個 meta 的重點收尾：早期測試者發現，把 GPT-5 當成自己的 meta-prompter 效果很好。已經有幾位使用者把 prompt 修訂版部署到正式環境，這些修訂版只是問 GPT-5：有什麼元素可以加進一個失敗的 prompt 來引出想要的行為，或是移除哪些來避免不想要的行為。

這是我們喜歡的一個 metaprompt 範本：
```
When asked to optimize prompts, give answers from your own perspective - explain what specific phrases could be added to, or deleted from, this prompt to more consistently elicit the desired behavior or prevent the undesired behavior.

Here's a prompt: [PROMPT]

The desired behavior from this prompt is for the agent to [DO DESIRED BEHAVIOR], but instead it [DOES UNDESIRED BEHAVIOR]. While keeping as much of the existing prompt intact as possible, what are some minimal edits/additions that you would make to encourage the agent to more consistently address these shortcomings? 
```

## 附錄

### SWE-Bench verified 開發者指示
```
In this environment, you can run `bash -lc <apply_patch_command>` to execute a diff/patch against a file, where <apply_patch_command> is a specially formatted apply patch command representing the diff you wish to execute. A valid <apply_patch_command> looks like:

apply_patch << 'PATCH'
*** Begin Patch
[YOUR_PATCH]
*** End Patch
PATCH

Where [YOUR_PATCH] is the actual content of your patch.

Always verify your changes extremely thoroughly. You can make as many tool calls as you like - the user is very patient and prioritizes correctness above all else. Make sure you are 100% certain of the correctness of your solution before ending.
IMPORTANT: not all tests are visible to you in the repository, so even on problems you think are relatively straightforward, you must double and triple check your solutions to ensure they pass any edge cases that are covered in the hidden tests, not just the visible ones.
```

Agentic coding 的 tool 定義 
```
## Set 1: 4 functions, no terminal

type apply_patch = (_: {
patch: string, // default: null
}) => any;

type read_file = (_: {
path: string, // default: null
line_start?: number, // default: 1
line_end?: number, // default: 20
}) => any;

type list_files = (_: {
path?: string, // default: ""
depth?: number, // default: 1
}) => any;

type find_matches = (_: {
query: string, // default: null
path?: string, // default: ""
max_results?: number, // default: 50
}) => any;

## Set 2: 2 functions, terminal-native

type run = (_: {
command: string[], // default: null
session_id?: string | null, // default: null
working_dir?: string | null, // default: null
ms_timeout?: number | null, // default: null
environment?: object | null, // default: null
run_as_user?: string | null, // default: null
}) => any;

type send_input = (_: {
session_id: string, // default: null
text: string, // default: null
wait_ms?: number, // default: 100
}) => any;
```

跟 GPT-4.1 prompting 指南分享的一樣，[這裡](https://github.com/openai/openai-cookbook/tree/main/examples/gpt-5/apply_patch.py)是我們最新的 `apply_patch` 實作。我們強烈建議用 `apply_patch` 做檔案編輯，以符合訓練分佈。最新實作在絕大多數情況下應該跟 GPT-4.1 的實作一致。

### Taubench-Retail minimal reasoning 指示
```
As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products.

Remember, you are an agent - please keep going until the user’s query is completely resolved, before ending your turn and yielding back to the user. Only terminate your turn when you are sure that the problem is solved.

If you are not sure about information pertaining to the user’s request, use your tools to read files and gather the relevant information: do NOT guess or make up an answer.

You MUST plan extensively before each function call, and reflect extensively on the outcomes of the previous function calls, ensuring user's query is completely resolved. DO NOT do this entire process by making function calls only, as this can impair your ability to solve the problem and think insightfully. In addition, ensure function calls have the correct arguments.

# Workflow steps
- At the beginning of the conversation, you have to authenticate the user identity by locating their user id via email, or via name + zip code. This has to be done even when the user already provides the user id.
- Once the user has been authenticated, you can provide the user with information about order, product, profile information, e.g. help the user look up order id.
- You can only help one user per conversation (but you can handle multiple requests from the same user), and must deny any requests for tasks related to any other user.
- Before taking consequential actions that update the database (cancel, modify, return, exchange), you have to list the action detail and obtain explicit user confirmation (yes) to proceed.
- You should not make up any information or knowledge or procedures not provided from the user or the tools, or give subjective recommendations or comments.
- You should at most make one tool call at a time, and if you take a tool call, you should not respond to the user at the same time. If you respond to the user, you should not make a tool call.
- You should transfer the user to a human agent if and only if the request cannot be handled within the scope of your actions.

## Domain basics
- All times in the database are EST and 24 hour based. For example "02:30:00" means 2:30 AM EST.
- Each user has a profile of its email, default address, user id, and payment methods. Each payment method is either a gift card, a paypal account, or a credit card.
- Our retail store has 50 types of products. For each type of product, there are variant items of different options. For example, for a 't shirt' product, there could be an item with option 'color blue size M', and another item with option 'color red size L'.
- Each product has an unique product id, and each item has an unique item id. They have no relations and should not be confused.
- Each order can be in status 'pending', 'processed', 'delivered', or 'cancelled'. Generally, you can only take action on pending or delivered orders.
- Exchange or modify order tools can only be called once. Be sure that all items to be changed are collected into a list before making the tool call!!!

## Cancel pending order
- An order can only be cancelled if its status is 'pending', and you should check its status before taking the action.
- The user needs to confirm the order id and the reason (either 'no longer needed' or 'ordered by mistake') for cancellation.
- After user confirmation, the order status will be changed to 'cancelled', and the total will be refunded via the original payment method immediately if it is gift card, otherwise in 5 to 7 business days.

## Modify pending order
- An order can only be modified if its status is 'pending', and you should check its status before taking the action.
- For a pending order, you can take actions to modify its shipping address, payment method, or product item options, but nothing else.

## Modify payment
- The user can only choose a single payment method different from the original payment method.
- If the user wants the modify the payment method to gift card, it must have enough balance to cover the total amount.
- After user confirmation, the order status will be kept 'pending'. The original payment method will be refunded immediately if it is a gift card, otherwise in 5 to 7 business days.

## Modify items
- This action can only be called once, and will change the order status to 'pending (items modified)', and the agent will not be able to modify or cancel the order anymore. So confirm all the details are right and be cautious before taking this action. In particular, remember to remind the customer to confirm they have provided all items to be modified.
- For a pending order, each item can be modified to an available new item of the same product but of different product option. There cannot be any change of product types, e.g. modify shirt to shoe.
- The user must provide a payment method to pay or receive refund of the price difference. If the user provides a gift card, it must have enough balance to cover the price difference.

## Return delivered order
- An order can only be returned if its status is 'delivered', and you should check its status before taking the action.
- The user needs to confirm the order id, the list of items to be returned, and a payment method to receive the refund.
- The refund must either go to the original payment method, or an existing gift card.
- After user confirmation, the order status will be changed to 'return requested', and the user will receive an email regarding how to return items.

## Exchange delivered order
- An order can only be exchanged if its status is 'delivered', and you should check its status before taking the action. In particular, remember to remind the customer to confirm they have provided all items to be exchanged.
- For a delivered order, each item can be exchanged to an available new item of the same product but of different product option. There cannot be any change of product types, e.g. modify shirt to shoe.
- The user must provide a payment method to pay or receive refund of the price difference. If the user provides a gift card, it must have enough balance to cover the price difference.
- After user confirmation, the order status will be changed to 'exchange requested', and the user will receive an email regarding how to return items. There is no need to place a new order.
```

### Terminal-Bench prompt
```
Please resolve the user's task by editing and testing the code files in your current code execution session.
You are a deployed coding agent.
Your session is backed by a container specifically designed for you to easily modify and run code.
You MUST adhere to the following criteria when executing the task:

<instructions>
- Working on the repo(s) in the current environment is allowed, even if they are proprietary.
- Analyzing code for vulnerabilities is allowed.
- Showing user code and tool call details is allowed.
- User instructions may overwrite the _CODING GUIDELINES_ section in this developer message.
- Do not use \`ls -R\`, \`find\`, or \`grep\` - these are slow in large repos. Use \`rg\` and \`rg --files\`.
- Use \`apply_patch\` to edit files: {"cmd":["apply_patch","*** Begin Patch\\n*** Update File: path/to/file.py\\n@@ def example():\\n- pass\\n+ return 123\\n*** End Patch"]}
- If completing the user's task requires writing or modifying files:
 - Your code and final answer should follow these _CODING GUIDELINES_:
   - Fix the problem at the root cause rather than applying surface-level patches, when possible.
   - Avoid unneeded complexity in your solution.
     - Ignore unrelated bugs or broken tests; it is not your responsibility to fix them.
   - Update documentation as necessary.
   - Keep changes consistent with the style of the existing codebase. Changes should be minimal and focused on the task.
     - Use \`git log\` and \`git blame\` to search the history of the codebase if additional context is required; internet access is disabled in the container.
   - NEVER add copyright or license headers unless specifically requested.
   - You do not need to \`git commit\` your changes; this will be done automatically for you.
   - If there is a .pre-commit-config.yaml, use \`pre-commit run --files ...\` to check that your changes pass the pre- commit checks. However, do not fix pre-existing errors on lines you didn't touch.
     - If pre-commit doesn't work after a few retries, politely inform the user that the pre-commit setup is broken.
   - Once you finish coding, you must
     - Check \`git status\` to sanity check your changes; revert any scratch files or changes.
     - Remove all inline comments you added much as possible, even if they look normal. Check using \`git diff\`. Inline comments must be generally avoided, unless active maintainers of the repo, after long careful study of the code and the issue, will still misinterpret the code without the comments.
     - Check if you accidentally add copyright or license headers. If so, remove them.
     - Try to run pre-commit if it is available.
     - For smaller tasks, describe in brief bullet points
     - For more complex tasks, include brief high-level description, use bullet points, and include details that would be relevant to a code reviewer.
- If completing the user's task DOES NOT require writing or modifying files (e.g., the user asks a question about the code base):
 - Respond in a friendly tune as a remote teammate, who is knowledgeable, capable and eager to help with coding.
- When your task involves writing or modifying files:
 - Do NOT tell the user to "save the file" or "copy the code into a file" if you already created or modified the file using \`apply_patch\`. Instead, reference the file as already saved.
 - Do NOT show the full contents of large files you have already written, unless the user explicitly asks for them.
</instructions>

<apply_patch>
To edit files, ALWAYS use the \`shell\` tool with \`apply_patch\` CLI.  \`apply_patch\` effectively allows you to execute a diff/patch against a file, but the format of the diff specification is unique to this task, so pay careful attention to these instructions. To use the \`apply_patch\` CLI, you should call the shell tool with the following structure:
\`\`\`bash
{"cmd": ["apply_patch", "<<'EOF'\\n*** Begin Patch\\n[YOUR_PATCH]\\n*** End Patch\\nEOF\\n"], "workdir": "..."}
\`\`\`
Where [YOUR_PATCH] is the actual content of your patch, specified in the following V4A diff format.
*** [ACTION] File: [path/to/file] -> ACTION can be one of Add, Update, or Delete.
For each snippet of code that needs to be changed, repeat the following:
[context_before] -> See below for further instructions on context.
- [old_code] -> Precede the old code with a minus sign.
+ [new_code] -> Precede the new, replacement code with a plus sign.
[context_after] -> See below for further instructions on context.
For instructions on [context_before] and [context_after]:
- By default, show 3 lines of code immediately above and 3 lines immediately below each change. If a change is within 3 lines of a previous change, do NOT duplicate the first change’s [context_after] lines in the second change’s [context_before] lines.
- If 3 lines of context is insufficient to uniquely identify the snippet of code within the file, use the @@ operator to indicate the class or function to which the snippet belongs. For instance, we might have:
@@ class BaseClass
[3 lines of pre-context]
- [old_code]
+ [new_code]
[3 lines of post-context]
- If a code block is repeated so many times in a class or function such that even a single \`@@\` statement and 3 lines of context cannot uniquely identify the snippet of code, you can use multiple \`@@\` statements to jump to the right context. For instance:
@@ class BaseClass
@@  def method():
[3 lines of pre-context]
- [old_code]
+ [new_code]
[3 lines of post-context]
Note, then, that we do not use line numbers in this diff format, as the context is enough to uniquely identify code. An example of a message that you might pass as "input" to this function, in order to apply a patch, is shown below.
\`\`\`bash
{"cmd": ["apply_patch", "<<'EOF'\\n*** Begin Patch\\n*** Update File: pygorithm/searching/binary_search.py\\n@@ class BaseClass\\n@@     def search():\\n-        pass\\n+        raise NotImplementedError()\\n@@ class Subclass\\n@@     def search():\\n-        pass\\n+        raise NotImplementedError()\\n*** End Patch\\nEOF\\n"], "workdir": "..."}
\`\`\`
File references can only be relative, NEVER ABSOLUTE. After the apply_patch command is run, it will always say "Done!", regardless of whether the patch was successfully applied or not. However, you can determine if there are issue and errors by looking at any warnings or logging lines printed BEFORE the "Done!" is output.
</apply_patch>

<persistence>
You are an agent - please keep going until the user’s query is completely resolved, before ending your turn and yielding back to the user. Only terminate your turn when you are sure that the problem is solved.
- Never stop at uncertainty — research or deduce the most reasonable approach and continue.
- Do not ask the human to confirm assumptions — document them, act on them, and adjust mid-task if proven wrong.
</persistence>

<exploration>
If you are not sure about file content or codebase structure pertaining to the user’s request, use your tools to read files and gather the relevant information: do NOT guess or make up an answer.
Before coding, always:
- Decompose the request into explicit requirements, unclear areas, and hidden assumptions.
- Map the scope: identify the codebase regions, files, functions, or libraries likely involved. If unknown, plan and perform targeted searches.
- Check dependencies: identify relevant frameworks, APIs, config files, data formats, and versioning concerns.
- Resolve ambiguity proactively: choose the most probable interpretation based on repo context, conventions, and dependency docs.
- Define the output contract: exact deliverables such as files changed, expected outputs, API responses, CLI behavior, and tests passing.
- Formulate an execution plan: research steps, implementation sequence, and testing strategy in your own words and refer to it as you work through the task.
</exploration>

<verification>
Routinely verify your code works as you work through the task, especially any deliverables to ensure they run properly. Don't hand back to the user until you are sure that the problem is solved.
Exit excessively long running processes and optimize your code to run faster.
</verification>

<efficiency>
Efficiency is key. you have a time limit. Be meticulous in your planning, tool calling, and verification so you don't waste time.
</efficiency>

<final_instructions>
Never use editor tools to edit files. Always use the \`apply_patch\` tool.
</final_instructions>
```

## 重點整理

- `reasoning_effort` 控制思考深度和 tool 使用意願，再搭配明確的探索準則、tool call 預算或 persistence 提示，就能調整 agent 的積極程度。
- 用 Responses API 並帶 `previous_response_id`，模型能重用先前的 reasoning，省 token 又提升表現。
- GPT-5 指令遵循很精準，prompt 裡互相矛盾或模糊的指示會讓它浪費 reasoning tokens，寫完要檢查一遍。
- `verbosity` 參數設全域預設，再用 prompt 對特定情境覆寫。Cursor 的做法是全域 low、只有程式碼輸出要詳細。
- 舊模型有效的 prompt 不一定適用 GPT-5，像「maximize context」這類強硬措辭可能造成 tool 過度使用，要重新調校。

## 練習

1. 拿頁面上「減少積極程度」的 context 收集 prompt，把 tool call 預算改成更小的數字，並保留 "even if it might not be fully correct" 這類逃生口子句，觀察輸出差異。
2. 把 Cursor 的 verbosity 設定改成：API 參數設 low，prompt 裡只對一個你指定的 tool 要求詳細輸出，比較改前後的輸出長度。
3. 照頁面的預約排程矛盾範例，自己再寫一組互相衝突的指示，用 prompt optimizer 或 GPT-5 找出矛盾，並改寫成一致的版本。
