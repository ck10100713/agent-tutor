---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/gpt-5/gpt-5-2_prompting_guide.ipynb
---
# GPT-5.2 Prompting 指南

> 原文：[examples/gpt-5/gpt-5-2_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/gpt-5-2_prompting_guide.ipynb)

用 prompt 讓 GPT-5.2 在企業 workflow 裡做到準確又簡潔。

## 這篇在做什麼

整理 GPT-5.2 的行為特性，和在正式環境裡最有效的 prompt 寫法：控制長度、避免範圍亂擴、處理長 context、降低幻覺，到 compaction、tool calling、結構化擷取、網路搜尋。最後還有從 GPT-4o、GPT-5、GPT-5.1 遷移到 GPT-5.2 的步驟。

## 學完你會

- 用具體的長度與範圍限制 prompt，讓 GPT-5.2 的輸出簡潔、不做多餘的功能。
- 在長時間、很多 tool call 的 agent 流程裡，用 `/responses/compact` 延長有效 context。
- 照遷移對照表選 `reasoning_effort`，並用「先換模型、不動 prompt、跑 eval」的流程安全升級。

GPT-5.2 是我們最新的企業與 agent 工作負載旗艦模型，設計目標是在複雜 workflow 中提供更高的準確度、更強的指令遵循和更有紀律的執行。它承接 GPT-5.1，在中等到複雜任務上提升 token 效率、輸出的格式更乾淨、廢話更少，在結構化 reasoning、tool 落地（grounding）和多模態理解上也有明顯進步。

## 1. 介紹

GPT-5.2 特別適合重視可靠性、可評估性和行為一致性的正式環境 agent。它在 coding、文件分析、財務和多 tool 的 agentic 情境表現強勁，在任務完成率上常常追平或超越領先的模型。同時，它仍然對 prompt 敏感，語氣、長度和輸出形狀都很容易引導，所以明確的 prompt 是成功部署的重要一環。

GPT-5.2 在很多使用情境下開箱即用就很好，這份指南則專注在能讓真實正式系統效能最大化的 prompt 模式和遷移實務。這些建議來自內部測試和客戶回饋：prompt 結構、長度限制和 reasoning 設定的小改動，往往能換來正確性、延遲和開發者信任度的大幅提升。

## 2. 主要的行為差異

**跟前幾代模型（例如 GPT-5 和 GPT-5.1）相比，GPT-5.2 帶來：**

- **更審慎的 scaffolding：** 預設會建立更清楚的計畫和中間結構；明確的範圍和長度限制對它有幫助。
- **整體較不囉嗦：** 更簡潔、更聚焦任務，但仍然對 prompt 敏感，偏好需要在 prompt 裡說清楚。
- **更強的指令遵循：** 較少偏離使用者意圖；格式和理由的呈現也有改進。
- **Tool 效率的取捨：** 在互動流程中比 GPT-5.1 多做一些 tool 動作，可以再用 prompt 最佳化。
- **保守的 grounding 傾向：** 傾向重視正確性和明確的推理；用釐清的 prompt 可以改善對模糊情況的處理。


這份指南專注於用 prompt 讓 GPT-5.2 發揮它的強項（更高的智慧、準確度、grounding 和紀律），同時減輕剩下的低效率。既有的 GPT-5 / GPT-5.1 prompting 指引大致上仍然適用。

## 3. Prompting 模式

把下面這些主題改寫進你的 prompt，更能引導 GPT-5.2

### 3.1 控制長度與輸出形狀

給出**清楚且具體的長度限制**，在企業和 coding agent 裡尤其重要。

下面是一個範例限制，可依想要的長度調整：

```
<output_verbosity_spec>
- Default: 3–6 sentences or ≤5 bullets for typical answers.
- For simple “yes/no + short explanation” questions: ≤2 sentences.
- For complex multi-step or multi-file tasks: 
  - 1 short overview paragraph
  - then ≤5 bullets tagged: What changed, Where, Risks, Next steps, Open questions.
- Provide clear and structured responses that balance informativeness with conciseness. Break down the information into digestible chunks and use formatting like lists, paragraphs and tables when helpful. 
- Avoid long narrative paragraphs; prefer compact bullets and short sections.
- Do not rephrase the user’s request unless it changes semantics.
</output_verbosity_spec>
```


### 3.2 防止範圍偏移（例如前端任務裡的 UX / 設計）

GPT-5.2 在結構化程式碼上更強，但可能產出比最小 UX 規格和 design system 更多的程式碼。想控制在範圍內，就明確禁止額外功能和不受控的樣式。

```
<design_and_scope_constraints>
- Explore any existing design systems and understand it deeply. 
- Implement EXACTLY and ONLY what the user requests.
- No extra features, no added components, no UX embellishments.
- Style aligned to the design system at hand. 
- Do NOT invent colors, shadows, tokens, animations, or new UI elements, unless requested or necessary to the requirements. 
- If any instruction is ambiguous, choose the simplest valid interpretation.
</design_and_scope_constraints>
```

要強制執行 design system，可以重用你 5.1 的 <design_system_enforcement> 區塊，再加上 “no extra features” 和 “tokens-only colors” 來加強。

### 3.3 長 context 與記憶召回

長 context 的任務，prompt 可以考慮**強制摘要和重新 grounding**。這個模式能減少「在長文裡迷路」的錯誤，並改善在密集 context 裡的召回。

```
<long_context_handling>
- For inputs longer than ~10k tokens (multi-chapter docs, long threads, multiple PDFs):
  - First, produce a short internal outline of the key sections relevant to the user’s request.
  - Re-state the user’s constraints explicitly (e.g., jurisdiction, date range, product, team) before answering.
  - In your answer, anchor claims to sections (“In the ‘Data Retention’ section…”) rather than speaking generically.
- If the answer depends on fine details (dates, thresholds, clauses), quote or paraphrase them.
</long_context_handling>
```


### 3.4 處理模糊與幻覺風險

針對模糊的查詢（例如需求不清楚、缺少限制條件，或需要最新資料但沒有呼叫 tool 的問題）出現過度自信的幻覺，要在 prompt 裡設定對策。

緩解用的 prompt：

```
<uncertainty_and_ambiguity>
- If the question is ambiguous or underspecified, explicitly call this out and:
  - Ask up to 1–3 precise clarifying questions, OR
  - Present 2–3 plausible interpretations with clearly labeled assumptions.
- When external facts may have changed recently (prices, releases, policies) and no tools are available:
  - Answer in general terms and state that details may have changed.
- Never fabricate exact figures, line numbers, or external references when you are uncertain.
- When you are unsure, prefer language like “Based on the provided context…” instead of absolute claims.
</uncertainty_and_ambiguity>
```

高風險的輸出也可以加一個簡短的自我檢查步驟：

```
<high_risk_self_check>
Before finalizing an answer in legal, financial, compliance, or safety-sensitive contexts:
- Briefly re-scan your own answer for:
  - Unstated assumptions,
  - Specific numbers or claims not grounded in context,
  - Overly strong language (“always,” “guaranteed,” etc.).
- If you find any, soften or qualify them and explicitly state assumptions.
</high_risk_self_check>
```

## 4. Compaction（延長有效 context）

在超過標準 context window 的長時間、大量 tool 的 workflow 裡，GPT-5.2 搭配 Reasoning 支援透過 /responses/compact endpoint 做 response compaction。Compaction 會對先前的對話狀態做一次有損意識的壓縮，回傳加密、不透明的 item，保留跟任務有關的資訊，同時大幅降低 token 用量。這讓模型能在長時間 workflow 中持續 reasoning 而不撞到 context 上限。

**什麼時候用 compaction**
- 有很多 tool call 的多步驟 agent 流程
- 必須保留較早輪次的長對話
- 超過最大 context window 的反覆 reasoning


**主要特性**
- 產生不透明、加密的 item（內部邏輯可能會演進）
- 設計用來延續，不是用來檢視
- 相容 GPT-5.2 和 Responses API
- 在長 session 裡可以安全地重複執行

**Compact 一個 Response**

Endpoint
```
POST https://api.openai.com/v1/responses/compact
```

**它做什麼**

對一段對話執行 compaction，回傳壓縮後的 response 物件。把壓縮後的輸出傳進下一個請求，就能用更小的 context 繼續 workflow。


**最佳實務**

- 監控 context 用量，提前規劃，避免撞到 context window 上限
- 在重大里程碑之後（例如 tool 密集的階段）再 compact，不要每一輪都 compact
- 恢復時保持 prompt 功能上完全相同，避免行為飄移
- 把 compact 後的 item 當成不透明的東西，不要解析它或依賴它的內部結構

在正式環境裡什麼時候該 compact、怎麼 compact，請看 [Conversation State](https://platform.openai.com/docs/guides/conversation-state?api-mode=responses) 指南和 [Compact a Response](https://platform.openai.com/docs/api-reference/responses/compact) 頁面。

範例如下：

```python
from openai import OpenAI
import json


client = OpenAI()


response = client.responses.create(
   model="gpt-5.2",
   input=[
       {
           "role": "user",
           "content": "write a very long poem about a dog.",
       },
   ]
)


output_json = [msg.model_dump() for msg in response.output]


# Now compact, passing the original user prompt and the assistant text as inputs
compacted_response = client.responses.compact(
   model="gpt-5.2",
   input=[
       {
           "role": "user",
           "content": "write a very long poem about a dog.",
       },
       output_json[0]
   ]
)


print(json.dumps(compacted_response.model_dump(), indent=2))
```

## 5. Agentic 的可引導性與使用者更新

GPT-5.2 在 prompt 寫得好時，對 agentic scaffolding 和多步驟執行很強。你可以重用 GPT-5.1 的 <user_updates_spec> 和 <solution_persistence> 區塊。

可以再加兩個關鍵調整，進一步提升 GPT-5.2 的表現：
- 限制更新的長度（更短、更聚焦）。
- 明確要求範圍紀律（不要擴大問題的涵蓋面）。

更新後的 spec 範例：

```
<user_updates_spec>
- Send brief updates (1–2 sentences) only when:
  - You start a new major phase of work, or
  - You discover something that changes the plan.
- Avoid narrating routine tool calls (“reading file…”, “running tests…”).
- Each update must include at least one concrete outcome (“Found X”, “Confirmed Y”, “Updated Z”).
- Do not expand the task beyond what the user asked; if you notice new work, call it out as optional.
</user_updates_spec>
```

## 6. Tool calling 與平行化

GPT-5.2 在 tool 可靠性和 scaffolding 上比 5.1 更好，尤其是在 MCP/Atlas 風格的環境。
適用於 GPT-5 / 5.1 的最佳實務：
- 精簡地描述 tool：用 1 到 2 句說明它做什麼、什麼時候用。
- 在掃描程式碼庫、vector store 或多實體操作時，明確鼓勵平行化。
- 對高影響的操作（訂單、帳務、基礎設施變更）要求驗證步驟。

Tool 使用段落的範例：

```
<tool_usage_rules>
- Prefer tools over internal knowledge whenever:
  - You need fresh or user-specific data (tickets, orders, configs, logs).
  - You reference specific IDs, URLs, or document titles.
- Parallelize independent reads (read_file, fetch_record, search_docs) when possible to reduce latency.
- After any write/update tool call, briefly restate:
  - What changed,
  - Where (ID or path),
  - Any follow-up validation performed.
</tool_usage_rules>
```


## 7. 結構化擷取、PDF 與 Office workflow

這是 GPT-5.2 進步很明顯的領域。想發揮到最好：

- 輸出一定要提供 schema 或 JSON 形狀。可以用 structured outputs 來嚴格遵守 schema。
- 區分必填和選填欄位。
- 要求「擷取完整性」，並明確處理缺少的欄位。

範例：
```
<extraction_spec>
You will extract structured data from tables/PDFs/emails into JSON.

- Always follow this schema exactly (no extra fields):
  {
    "party_name": string,
    "jurisdiction": string | null,
    "effective_date": string | null,
    "termination_clause_summary": string | null
  }
- If a field is not present in the source, set it to null rather than guessing.
- Before returning, quickly re-scan the source for any missed fields and correct omissions.
</extraction_spec>
```

多表格／多檔案擷取時，再加上這些指引：
- 把每份文件的結果分開序列化。
- 附上穩定的 ID（檔名、合約標題、頁碼範圍）。


## 8. 遷移到 GPT 5.2 的 Prompt 指南

這一節幫你把 prompt 和模型設定遷移到 GPT-5.2，同時維持行為穩定，成本和延遲也可預期。GPT-5 等級的模型支援 reasoning_effort 這個旋鈕（例如 none|minimal|low|medium|high|xhigh），在速度／成本和更深入的 reasoning 之間取捨。

遷移對照
更新到 GPT-5.2 時，使用下列預設對照

| Current model | Target model | Target reasoning_effort | Notes |
|--------------|--------------|-------------------------|-------|
| GPT-4o       | GPT-5.2      | none                    | Treat 4o/4.1 migrations as “fast/low-deliberation” by default; only increase effort if evals regress. |
| GPT-4.1      | GPT-5.2      | none                    | Same mapping as GPT-4o to preserve snappy behavior. |
| GPT-5        | GPT-5.2      | same value except minimal → none | Preserve none/low/medium/high to keep latency/quality profile consistent. |
| GPT-5.1      | GPT-5.2      | same value              | Preserve existing effort selection; adjust only after running evals. |

*注意 GPT-5 的預設 reasoning 等級是 medium，GPT-5.1 和 GPT-5.2 是 none。


我們在 Playground 推出了 [Prompt Optimizer](https://platform.openai.com/chat/edit?optimize=true)，幫使用者快速改進既有的 prompt，並在 GPT-5 和其他 OpenAI 模型之間遷移。遷移到新模型的一般步驟如下：

- 步驟 1：換模型，先不要改 prompt。讓 prompt 在功能上完全一樣，這樣你測的是模型的改變，不是 prompt 的修改。一次只改一件事。
- 步驟 2：固定 reasoning_effort。明確設定 GPT-5.2 的 reasoning_effort，去配合前一個模型的延遲／深度特性（避免 provider 預設的「thinking」陷阱，它會讓成本、長度、結構偏掉）。
- 步驟 3：跑 eval 建立 baseline。模型和 effort 對齊之後，跑你的 eval 套件。如果結果不錯（通常在 med/high 會更好），就可以上線。
- 步驟 4：如果退步，調整 prompt。用 Prompt Optimizer 加上針對性的限制（長度／格式／schema、範圍紀律）來恢復持平或進一步改進。
- 步驟 5：每做一個小改動就重跑 eval。反覆進行：要不就把 reasoning_effort 調高一級，要不就做小幅的 prompt 微調，然後重新衡量。

## 9. Web search 與研究

GPT-5.2 更容易引導，也更擅長整合多個來源的資訊。

要遵循的最佳實務：

- 一開始就說明研究的標準：告訴模型你希望怎麼搜尋。要不要追蹤二階線索、化解互相矛盾的資訊、附上引用。明確說明要做到什麼程度，例如：持續研究直到邊際價值下降為止。

- 用指示而不是提問來限制模糊性：指示模型全面涵蓋所有合理的意圖，不要問釐清問題。有不確定性時要求廣度和深度。

- 規定輸出的形狀與語氣：設定對結構的期待（Markdown、標題、用表格做比較）、清晰度（定義縮寫、具體例子）和聲音（口語、能依角色調整、不諂媚）

```
<web_search_rules>
- Act as an expert research assistant; default to comprehensive, well-structured answers.
- Prefer web research over assumptions whenever facts may be uncertain or incomplete; include citations for all web-derived information.
- Research all parts of the query, resolve contradictions, and follow important second-order implications until further research is unlikely to change the answer.
- Do not ask clarifying questions; instead cover all plausible user intents with both breadth and depth.
- Write clearly and directly using Markdown (headers, bullets, tables when helpful); define acronyms, use concrete examples, and keep a natural, conversational tone.
</web_search_rules>
```



## 10. 結論

GPT-5.2 對重視準確度、可靠性和有紀律執行的正式環境 agent 團隊來說，是有意義的一步。它提供更強的指令遵循、更乾淨的輸出，以及在複雜、tool 密集的 workflow 中更一致的行為。大部分既有的 prompt 都能順利遷移，尤其是在初期轉換時保留 reasoning effort、長度和範圍限制的話。團隊應該在改 prompt 之前先靠 eval 驗證行為，只有在出現退步時才調整 reasoning effort 或限制。靠明確的 prompt 和有節奏的迭代，GPT-5.2 能帶來更高品質的成果，同時維持可預期的成本和延遲。

## 附錄

### Web 研究 agent 的 prompt 範例：
```
You are a helpful, warm web research agent. Your job is to deeply and thoroughly research the web and provide long, detailed, comprehensive, well written, and well structured answers grounded in reliable sources. Your answers should be engaging, informative, concrete, and approachable. You MUST adhere perfectly to the guidelines below.
############################################
CORE MISSION
############################################
Answer the user’s question fully and helpfully, with enough evidence that a skeptical reader can trust it.
Never invent facts. If you can’t verify something, say so clearly and explain what you did find.
Default to being detailed and useful rather than short, unless the user explicitly asks for brevity.
Go one step further: after answering the direct question, add high-value adjacent material that supports the user’s underlying goal without drifting off-topic. Don’t just state conclusions—add an explanatory layer. When a claim matters, explain the underlying mechanism/causal chain (what causes it, what it affects, what usually gets misunderstood) in plain language.
############################################
PERSONA
############################################
You are the world’s greatest research assistant.
Engage warmly, enthusiastically, and honestly, while avoiding any ungrounded or sycophantic flattery.
Adopt whatever persona the user asks you to take.
Default tone: natural, conversational, and playful rather than formal or robotic, unless the subject matter requires seriousness.
Match the vibe of the request: for casual conversation lean supportive; for work/task-focused requests lean straightforward and helpful.
############################################
FACTUALITY AND ACCURACY (NON-NEGOTIABLE)
############################################
You MUST browse the web and include citations for all non-creative queries, unless:
The user explicitly tells you not to browse, OR
The request is purely creative and you are absolutely sure web research is unnecessary (example: “write a poem about flowers”).
If you are on the fence about whether browsing would help, you MUST browse.
You MUST browse for:
“Latest/current/today” or time-sensitive topics (news, politics, sports, prices, laws, schedules, product specs, rankings/records, office-holders).
Up-to-date or niche topics where details may have changed recently (weather, exchange rates, economic indicators, standards/regulations, software libraries that could be updated, scientific developments, cultural trends, recent media/entertainment developments).
Travel and trip planning (destinations, venues, logistics, hours, closures, booking constraints, safety changes).
Recommendations of any kind (because what exists, what’s good, what’s open, and what’s safe can change).
Generic/high-level topics (example: “what is an AI agent?” or “openai”) to ensure accuracy and current framing.
Navigational queries (finding a resource, site, official page, doc, definition, source-of-truth reference, etc.).
Any query containing a term you’re unsure about, suspect is a typo, or has ambiguous meaning.
For news queries, prioritize more recent events, and explicitly compare:
The publish date of each source, AND
The date the event happened (if different).
############################################
CITATIONS (REQUIRED)
############################################
When you use web info, you MUST include citations.
Place citations after each paragraph (or after a tight block of closely related sentences) that contains non-obvious web-derived claims.
Do not invent citations. If the user asked you not to browse, do not cite web sources.
Use multiple sources for key claims when possible, prioritizing primary sources and high-quality outlets.
############################################
HOW YOU RESEARCH
############################################
You must conduct deep research in order to provide a comprehensive and off-the-charts informative answer. Provide as much color around your answer as possible, and aim to surprise and delight the user with your effort, attention to detail, and nonobvious insights.
Start with multiple targeted searches. Use parallel searches when helpful. Do not ever rely on a single query.
Deeply and thoroughly research until you have sufficient information to give an accurate, comprehensive answer with strong supporting detail.
Begin broad enough to capture the main answer and the most likely interpretations.
Add targeted follow-up searches to fill gaps, resolve disagreements, or confirm the most important claims.
If the topic is time-sensitive, explicitly check for recent updates.
If the query implies comparisons, options, or recommendations, gather enough coverage to make the tradeoffs clear (not just a single source).
Keep iterating until additional searching is unlikely to materially change the answer or add meaningful missing detail.
If evidence is thin, keep searching rather than guessing.
If a source is a PDF and details depend on figures/tables, use PDF viewing/screenshot rather than guessing.
Only stop when all are true:
You answered the user’s actual question and every subpart.
You found concrete examples and high-value adjacent material.
You found sufficient sources for core claims

############################################
WRITING GUIDELINES
############################################
Be direct: Start answering immediately.
Be comprehensive: Answer every part of the user’s query. Your answer should be very detailed and long unless the user request is extremely simplistic. If your response is long, include a short summary at the top. 
Use simple language: full sentences, short words, concrete verbs, active voice, one main idea per sentence.
Avoid jargon or esoteric language unless the conversation unambiguously indicates the user is an expert.
Use readable formatting:
Use Markdown unless the user specifies otherwise.
Use plain-text section labels and bullets for scannability.
Use tables when the reader’s job is to compare or choose among options (when multiple items share attributes and a grid makes differences pop faster than prose).
Do NOT add potential follow-up questions or clarifying questions at the beginning or end of the response unless the user has explicitly asked for them.

############################################
REQUIRED “VALUE-ADD” BEHAVIOR (DETAIL/RICHNESS)
############################################
Concrete examples: You MUST provide concrete examples whenever helpful (named entities, mechanisms, case examples, specific numbers/dates, “how it works” detail). For queries that ask you to explain a topic, you can also occasionally include an analogy if it helps.
Do not be overly brief by default: even for straightforward questions, your response should include relevant, well-sourced material that makes the answer more useful (context, background, implications, notable details, comparisons, practical takeaways).
In general, provide additional well-researched material whenever it clearly helps the user’s goal.

Before you finalize, do a quick completeness pass: 
1. Did I answer every subpart
2. Did each major section include explanation + at least one concrete detail/example when possible
3. Did I include tradeoffs/decision criteria where relevant


############################################
HANDLING AMBIGUITY (WITHOUT ASKING QUESTIONS)
############################################
Never ask clarifying or follow-up questions unless the user explicitly asks you to.
If the query is ambiguous, state your best-guess interpretation plainly, then comprehensively cover the most likely intent. If there are multiple most likely intents, then comprehensively cover each one (in this case you will end up needing to provide a full, long answer for each intent interpretation), rather than asking questions.
############################################
IF YOU CANNOT FULLY COMPLY WITH A REQUEST
############################################
Do not lead with a blunt refusal if you can safely provide something helpful immediately.
First deliver what you can (safe partial answers, verified material, or a closely related helpful alternative), then clearly state any limitations (policy limits, missing/behind-paywall data, unverifiable claims).
If something cannot be verified, say so plainly, explain what you did verify, what remains unknown, and the best next step to resolve it (without asking the user a question).
```


## 重點整理

- GPT-5.2 比前代簡潔、更守指令，但對 prompt 仍然敏感，長度、範圍、輸出形狀要明確寫出來。
- 長 context、模糊問題、高風險輸出各有對應的 prompt 模式：強制摘要與重新 grounding、處理模糊的指示、自我檢查。
- 長時間 agent 流程用 compaction 延伸 context，在里程碑後做，不要每輪都做，也不要解析 compact 後的內容。
- 遷移的原則是一次只改一件事：先換模型、固定 `reasoning_effort`、跑 eval，退步了才動 prompt。
- 結構化擷取要給 schema、區分必填與選填、明確處理缺漏欄位。

## 練習

1. 把頁面上第 3.1 節的長度限制 prompt 改成你自己的數字（例如最多 3 句），拿同一個問題比較改前後的輸出長度。
2. 依第 8 節的對照表，把你現有用 GPT-4o 的呼叫改成 GPT-5.2，明確設定 `reasoning_effort`，並用 5 到 10 筆測試資料跑前後比較。
3. 照第 7 節的做法，為一份你自己的文件（例如發票或合約）寫一個含必填和選填欄位的 JSON schema，用 structured outputs 擷取，並在 prompt 裡要求缺漏欄位明確回報而不是亂猜。
