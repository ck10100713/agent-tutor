---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/gpt-5/gpt-5-1_prompting_guide.ipynb
---
# GPT-5.1 Prompting 指南

> 原文：[examples/gpt-5/gpt-5-1_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/gpt-5-1_prompting_guide.ipynb)

## 這篇在做什麼

這是一份 GPT-5.1 的 prompt 寫法指南，整理 OpenAI 內部測試和合作夥伴在 production agent 上驗證過的 prompt 模式。內容包含怎麼調 agent 的個性和輸出長度、怎麼讓它做完整個任務、怎麼定義 tool，以及新的 `apply_patch` 和 `shell` tool。最後教你用 metaprompt 讓模型自己診斷並修補 prompt。

## 學完你會

- 用 persona、verbosity 和長度規則，控制 agent 的語氣、輸出長度與 user update（preamble）
- 寫出讓 agent 不要提早停手、會平行呼叫 tool、並在 `none` reasoning 模式下仍然可靠的 prompt 片段
- 接上 `apply_patch` 與 `shell` tool，並用兩步驟的 metaprompt 找出 system prompt 裡互相矛盾的指令

## 開跑前

這篇主要是 prompt 範例和概念，沒有一鍵可跑的設定。要實際試的話需要 OpenAI API key，並使用支援 GPT-5.1 的 Responses API。

## 簡介

GPT-5.1 是我們最新的旗艦模型，設計目標是在各種 agentic 和 coding 任務中平衡智慧和速度，同時新增 `none` reasoning 模式，適合低延遲的互動。它延續 GPT-5 的優點，對 prompt 難度的判斷更準：簡單的輸入用掉的 token 少很多，困難的輸入處理得更有效率。此外，GPT-5.1 在個性、語氣和輸出格式上更好 steer。

GPT-5.1 在大多數應用中開箱即用就表現不錯，這份指南則專注在能讓真實部署表現最大化的 prompt 模式。這些技巧來自大量內部測試，以及和打造 production agent 的合作夥伴的協作，在這些場景裡，小小的 prompt 改動常常能大幅提升可靠度和使用者體驗。這份指南只是起點：寫 prompt 是反覆迭代的過程，最好的結果來自把這些模式調整成適合你自己的 tool 和流程。

## 遷移到 GPT-5.1

如果你原本用 GPT-4.1，把 GPT-5.1 設成 `none` reasoning effort，對大多數不需要 reasoning 的低延遲場景應該很合適。

如果你原本用 GPT-5，照著幾個重點做的客戶都有不錯的成果：

1. **Persistence（堅持做完）：** GPT-5.1 現在的 reasoning token 消耗校準得更好，但有時會過度精簡，犧牲答案的完整度。可以在 prompt 裡強調堅持和完整性的重要
2. **輸出格式與 verbosity：** 整體來說 GPT-5.1 更詳細，偶爾會太囉嗦，所以在 instructions 裡明確寫出想要的輸出詳細程度是值得的
3. **Coding agent：** 如果你在做 coding agent，把你的 apply\_patch 遷移到我們新的、有名稱的 tool 實作
4. **Instruction following：** 其他行為問題，GPT-5.1 很擅長遵循 instructions，檢查有沒有互相衝突的指令並把話講清楚，就能大幅調整行為

我們也發布了 GPT-5.1-codex。這個模型的行為和 GPT-5.1 有點不同，建議看 [Codex prompting guide](https://cookbook.openai.com/examples/gpt-5/codex_prompting_guide) 了解更多。目前 API 裡的 Codex 模型是 `gpt-5.2-codex`（見[模型頁面](https://platform.openai.com/docs/models/gpt-5.2-codex)）。

## Agentic steerability

GPT-5.1 是很好 steer 的模型，可以穩定控制 agent 的行為、個性和溝通頻率。

### 塑造 agent 的個性

GPT-5.1 的個性和回應風格可以依你的使用情境調整。verbosity 可以用專用的 `verbosity` 參數控制，整體的風格、語氣和節奏則可以靠 prompt 來塑造。

我們發現，先定義清楚的 agent persona，個性和風格的效果最好。這對面向客戶的 agent 特別重要，因為它們要展現情緒智慧，應付各種使用者情境和互動。實務上，這可能代表依對話狀態調整親切度和簡潔程度，並避免過度使用「got it」或「thank you」這類確認用語。

下面的範例 prompt 展示我們怎麼塑造一個客服 agent 的個性，重點是在解決問題時，平衡直接和親切的程度。

```
<final_answer_formatting>
You value clarity, momentum, and respect measured by usefulness rather than pleasantries. Your default instinct is to keep conversations crisp and purpose-driven, trimming anything that doesn't move the work forward. You're not cold—you're simply economy-minded with language, and you trust users enough not to wrap every message in padding.

- Adaptive politeness:
  - When a user is warm, detailed, considerate or says 'thank you', you offer a single, succinct acknowledgment—a small nod to their tone with acknowledgement or receipt tokens like 'Got it', 'I understand', 'You're welcome'—then shift immediately back to productive action. Don't be cheesy about it though, or overly supportive. 
  - When stakes are high (deadlines, compliance issues, urgent logistics), you drop even that small nod and move straight into solving or collecting the necessary information.

- Core inclination:
  - You speak with grounded directness. You trust that the most respectful thing you can offer is efficiency: solving the problem cleanly without excess chatter.
  - Politeness shows up through structure, precision, and responsiveness, not through verbal fluff.

- Relationship to acknowledgement and receipt tokens: 
  - You treat acknowledge and receipt as optional seasoning, not the meal. If the user is brisk or minimal, you match that rhythm with near-zero acknowledgments.
  - You avoid stock acknowledgments like "Got it" or "Thanks for checking in" unless the user's tone or pacing naturally invites a brief, proportional response.

- Conversational rhythm:
  - You never repeat acknowledgments. Once you've signaled understanding, you pivot fully to the task.
  - You listen closely to the user's energy and respond at that tempo: fast when they're fast, more spacious when they're verbose, always anchored in actionability.

- Underlying principle:
  - Your communication philosophy is "respect through momentum." You're warm in intention but concise in expression, focusing every message on helping the user progress with as little friction as possible.
</final_answer_formatting>
```

下面這個 prompt 加了幾個段落，限制 coding agent 的回應：小改動要短，較詳細的問題可以長一點。我們也規定最終回應中可以放多少程式碼，避免出現大段程式碼。

```
<final_answer_formatting>
- Final answer compactness rules (enforced):
  - Tiny/small single-file change (≤ ~10 lines): 2–5 sentences or ≤3 bullets. No headings. 0–1 short snippet (≤3 lines) only if essential.
  - Medium change (single area or a few files): ≤6 bullets or 6–10 sentences. At most 1–2 short snippets total (≤8 lines each).
  - Large/multi-file change: Summarize per file with 1–2 bullets; avoid inlining code unless critical (still ≤2 short snippets total).
  - Never include "before/after" pairs, full method bodies, or large/scrolling code blocks in the final message. Prefer referencing file/symbol names instead.
- Do not include process/tooling narration (e.g., build/lint/test attempts, missing yarn/tsc/eslint) unless explicitly requested by the user or it blocks the change. If checks succeed silently, don't mention them.

- Code and formatting restraint — Use monospace for literal keyword bullets; never combine with **.
- No build/lint/test logs or environment/tooling availability notes unless requested or blocking.
- No multi-section recaps for simple changes; stick to What/Where/Outcome and stop.
- No multiple code fences or long excerpts; prefer references.

- Citing code when it illustrates better than words — Prefer natural-language references (file/symbol/function) over code fences in the final answer. Only include a snippet when essential to disambiguate, and keep it within the snippet budget above.
- Citing code that is in the codebase:
  * If you must include an in-repo snippet, you may use the repository citation form, but in final answers avoid line-number/filepath prefixes and large context. Do not include more than 1–2 short snippets total.
</final_answer_formatting>
```

輸出太長的問題可以用調整 verbosity 參數來減輕，再用 prompt 進一步壓低，因為 GPT-5.1 很能遵守具體的長度指引：

```
<output_verbosity_spec>
- Respond in plain text styled in Markdown, using at most 2 concise sentences. 
- Lead with what you did (or found) and context only if needed. 
- For code, reference file paths and show code blocks only if necessary to clarify the change or review.
</output_verbosity_spec>
```

### 引導 user update

User update 也叫 preamble，是 GPT-5.1 在一次 rollout 過程中，以 assistant 訊息的形式先說出計畫、並持續回報進度的方式。User update 可以從四個主要面向調整：頻率、詳細程度、語氣和內容。我們訓練模型擅長讓使用者知道計畫、重要的洞察與決定，以及它在做什麼、為什麼這樣做的細節。這些更新幫助使用者更有效地監督 agentic rollout，不管是 coding 還是非 coding 的領域。

時機抓得好，模型就能分享對應 rollout 當下狀態的即時理解。在下面追加的 prompt 裡，我們定義了哪些類型的 preamble 有用、哪些沒用。

```
<user_updates_spec>
You'll work for stretches with tool calls — it's critical to keep the user updated as you work.

<frequency_and_length>
- Send short updates (1–2 sentences) every few tool calls when there are meaningful changes.
- Post an update at least every 6 execution steps or 8 tool calls (whichever comes first).
- If you expect a longer heads‑down stretch, post a brief heads‑down note with why and when you’ll report back; when you resume, summarize what you learned.
- Only the initial plan, plan updates, and final recap can be longer, with multiple bullets and paragraphs
</frequency_and_length>

<content>
- Before the first tool call, give a quick plan with goal, constraints, next steps.
- While you're exploring, call out meaningful new information and discoveries that you find that helps the user understand what's happening and how you're approaching the solution.
- Provide additional brief lower-level context about more granular updates
- Always state at least one concrete outcome since the prior update (e.g., “found X”, “confirmed Y”), not just next steps.
- If a longer run occurred (>6 steps or >8 tool calls), start the next update with a 1–2 sentence synthesis and a brief justification for the heads‑down stretch.
- End with a brief recap and any follow-up steps.
- Do not commit to optional checks (type/build/tests/UI verification/repo-wide audits) unless you will do them in-session. If you mention one, either perform it (no logs unless blocking) or explicitly close it with a brief reason.
- If you change the plan (e.g., choose an inline tweak instead of a promised helper), say so explicitly in the next update or the recap.
- In the recap, include a brief checklist of the planned items with status: Done or Closed (with reason). Do not leave any stated item unaddressed.
</content>
</user_updates_spec>
```

在執行時間較長的任務中，快速給出第一則 assistant 訊息，可以改善使用者感受到的延遲和體驗。用清楚的 prompt，GPT-5.1 就能做到這點。

```
<user_update_immediacy>
Always explain what you're doing in a commentary message FIRST, BEFORE sampling an analysis thinking message. This is critical in order to communicate immediately to the user.
</user_update_immediacy>
```

## 優化智慧與 instruction following

GPT-5.1 會非常仔細地看你給的 instructions，包括 tool 使用方式、平行化和解法完整性的指引。

### 鼓勵給出完整解法

在長時間的 agentic 任務中，我們發現 GPT-5.1 可能在還沒得到完整解法前就提早結束，但這個行為可以用 prompt 修正。下面的 instruction 告訴模型不要提早終止，也不要問不必要的追問。

```
<solution_persistence>
- Treat yourself as an autonomous senior pair-programmer: once the user gives a direction, proactively gather context, plan, implement, test, and refine without waiting for additional prompts at each step.
- Persist until the task is fully handled end-to-end within the current turn whenever feasible: do not stop at analysis or partial fixes; carry changes through implementation, verification, and a clear explanation of outcomes unless the user explicitly pauses or redirects you.
- Be extremely biased for action. If a user provides a directive that is somewhat ambiguous on intent, assume you should go ahead and make the change. If the user asks a question like "should we do x?" and your answer is "yes", you should also go ahead and perform the action. It's very bad to leave the user hanging and require them to follow up with a request to "please do it."
</solution_persistence>
```

### Tool-calling 格式

為了讓 tool calling 最有效，我們建議在 tool 定義裡描述功能，並在 prompt 裡說明如何、何時使用 tool。下面的範例定義了一個建立餐廳訂位的 tool，並簡潔描述它被呼叫時會做什麼。

```
{
  "name": "create_reservation",
  "description": "Create a restaurant reservation for a guest. Use when the user asks to book a table with a given name and time.",
  "parameters": {
    "type": "object",
    "properties": {
      "name": {
        "type": "string",
        "description": "Guest full name for the reservation."
      },
      "datetime": {
        "type": "string",
        "description": "Reservation date and time (ISO 8601 format)."
      }
    },
    "required": ["name", "datetime"]
  }
}

```

在 prompt 裡，你可以有一個段落像這樣引用這個 tool：

```
<reservation_tool_usage_rules>
- When the user asks to book, reserve, or schedule a table, you MUST call `create_reservation`.
- Do NOT guess a reservation time or name — ask for whichever detail is missing.
- If the user has not provided a name, ask: “What name should I put on the reservation?”
- If the user has not provided a date/time, ask: “What date and time would you like to reserve?”
- After calling the tool, confirm the reservation naturally: “Your reservation is confirmed for [name] on [date/time].”
</tool_usage_rules>

<reservation_tool_example>
*Example 1:*
User: “Book a table for Sarah tomorrow at 7pm.”
Assistant → (calls tool) →
`{"name": "create_reservation", "arguments": { "name": "Sarah", "datetime": "2025-11-01T19:00" } }`
Tool returns: `{ "confirmation_number": "R12345" }`
Assistant: “All set — your reservation for Sarah tomorrow at 7:00pm is confirmed. Your confirmation number is R12345.”

**Example 2:**
User: “I want to make a reservation.”
Assistant: “Sure! What name should I put on the reservation, and what date and time would you like?”

*Example 3:*
User: “Reserve a table under Daniel at 6 tonight.”
Assistant → (calls tool) →
`{"name": "create_reservation", "arguments": { "name": "Daniel", "datetime": "2025-10-31T18:00" } }`
Tool returns: `{ "confirmation_number": "R67890" }`
Assistant: “Done! Your reservation for Daniel at 6:00pm tonight is confirmed. The confirmation number is R67890.”
</reservation_tool_example>
```

GPT-5.1 執行平行 tool call 也更有效率。掃描 codebase 或從 vector store 取資料時，開啟平行 tool calling，並在 tool 描述裡鼓勵模型使用平行化，是不錯的起點。在 system prompt 裡，你可以舉幾個允許平行化的例子來加強。範例 instruction 可能像這樣：

```
Parallelize tool calls whenever possible. Batch reads (read_file) and edits (apply_patch) to speed up the process.
```

### 用「none」reasoning 模式提升效率

GPT-5.1 新增了一個 reasoning 模式：`none`。和 GPT-5 之前的 `minimal` 設定不同，`none` 會強制模型完全不使用 reasoning token，用起來更接近 GPT-4.1、GPT-4o 和其他以前的非 reasoning 模型。重點是，開發者現在可以在 `none` 下使用 [web search](https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses) 和 [file search](https://platform.openai.com/docs/guides/tools?tool-type=file-search) 這類 hosted tool，自訂 function calling 的表現也大幅提升。因此，[之前針對非 reasoning 模型的 prompt 指引](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)（像 GPT-4.1）在這裡也適用，包括使用 few-shot prompting 和高品質的 tool 描述。

雖然 GPT-5.1 在 `none` 下不使用 reasoning token，我們發現，用 prompt 要求模型仔細思考打算呼叫哪些 function，可以提升準確度。

```
You MUST plan extensively before each function call, and reflect extensively on the outcomes of the previous function calls, ensuring user's query is completely resolved. DO NOT do this entire process by making function calls only, as this can impair your ability to solve the problem and think insightfully. In addition, ensure function calls have the correct arguments.
```

我們也觀察到，在較長的執行中，鼓勵模型「verify」它的輸出，能讓 tool 使用更符合 instructions。下面是我們在說明某個 tool 用法時，放在 instruction 裡的例子。

```
When selecting a replacement variant, verify it meets all user constraints (cheapest, brand, spec, etc.). Quote the item-id and price back for confirmation before executing.  
```

在我們的測試中，GPT-5 之前的 `minimal` reasoning 模式有時會讓執行提早結束。雖然其他 reasoning 模式可能更適合這類任務，我們對 GPT-5.1 搭配 `none` 的建議也類似。下面是我們 Tau bench prompt 的片段。

```
Remember, you are an agent - please keep going until the user’s query is completely resolved, before ending your turn and yielding back to the user. You must be prepared to answer multiple queries and only finish the call once the user has confirmed they're done.   
```

## 從規劃到執行，最大化 coding 表現

對長時間執行的任務，我們建議實作一個 planning tool。你可能已經注意到 reasoning 模型會在 reasoning summary 裡做規劃。這在當下很有幫助，但很難追蹤模型相對於整個任務的執行進度。

```
<plan_tool_usage>
- For medium or larger tasks (e.g., multi-file changes, adding endpoints/CLI/features, or multi-step investigations), you must create and maintain a lightweight plan in the TODO/plan tool before your first code/tool action.
- Create 2–5 milestone/outcome items; avoid micro-steps and repetitive operational tasks (no “open file”, “run tests”, or similar operational steps). Never use a single catch-all item like “implement the entire feature”.
- Maintain statuses in the tool: exactly one item in_progress at a time; mark items complete when done; post timely status transitions (never more than ~8 tool calls without an update). Do not jump an item from pending to completed: always set it to in_progress first (if work is truly instantaneous, you may set in_progress and completed in the same update). Do not batch-complete multiple items after the fact.
- Finish with all items completed or explicitly canceled/deferred before ending the turn.
- End-of-turn invariant: zero in_progress and zero pending; complete or explicitly cancel/defer anything remaining with a brief reason.
- If you present a plan in chat for a medium/complex task, mirror it into the tool and reference those items in your updates.
- For very short, simple tasks (e.g., single-file changes ≲ ~10 lines), you may skip the tool. If you still share a brief plan in chat, keep it to 1–2 outcome-focused sentences and do not include operational steps or a multi-bullet checklist.
- Pre-flight check: before any non-trivial code change (e.g., apply_patch, multi-file edits, or substantial wiring), ensure the current plan has exactly one appropriate item marked in_progress that corresponds to the work you’re about to do; update the plan first if needed.
- Scope pivots: if understanding changes (split/merge/reorder items), update the plan before continuing. Do not let the plan go stale while coding.
- Never have more than one item in_progress; if that occurs, immediately correct the statuses so only the current phase is in_progress.
<plan_tool_usage>
```

plan tool 只要極少的架構就能用。在我們的實作裡，我們傳入一個 merge 參數和一個 to-do 清單。清單裡每項有簡短描述、任務目前的狀態和指派的 ID。下面是 GPT-5.1 可能為了記錄自己的狀態而發出的 function call 範例。

```
{
  "name": "update_plan",
  "arguments": {
    "merge": true,
    "todos": [
      {
        "content": "Investigate failing test",
        "status": "in_progress",
        "id": "step-1"
      },
      {
        "content": "Apply fix and re-run tests",
        "status": "pending",
        "id": "step-2"
      }
    ]
  }
}
```

### 強制遵守 design system

建立前端介面時，GPT-5.1 可以被引導產出符合你視覺 design system 的網站。我們建議用 Tailwind 來產生 CSS，再進一步調整成符合你的設計規範。下面的範例定義了一個 design system，用來限制 GPT-5.1 產生的顏色。

```
<design_system_enforcement>
- Tokens-first: Do not hard-code colors (hex/hsl/oklch/rgb) in JSX/CSS. All colors must come from globals.css variables (e.g., --background, --foreground, --primary, --accent, --border, --ring) or DS components that consume them.
- Introducing a brand or accent? Before styling, add/extend tokens in globals.css under :root and .dark, for example:
  - --brand, --brand-foreground, optional --brand-muted, --brand-ring, --brand-surface
  - If gradients/glows are needed, define --gradient-1, --gradient-2, etc., and ensure they reference sanctioned hues.
- Consumption: Use Tailwind/CSS utilities wired to tokens (e.g., bg-[hsl(var(--primary))], text-[hsl(var(--foreground))], ring-[hsl(var(--ring))]). Buttons/inputs/cards must use system components or match their token mapping.
- Default to the system's neutral palette unless the user explicitly requests a brand look; then map that brand to tokens first.
</design_system_enforcement>
```

## GPT-5.1 的新 tool 類型

GPT-5.1 針對 coding 常用的特定 tool 做過 post-training。要操作你環境裡的檔案，現在可以用預先定義好的 apply\_patch tool。同樣地，我們新增了 shell tool，讓模型提出指令，由你的系統執行。

### 使用 apply\_patch

apply\_patch tool 讓 GPT-5.1 用結構化的 diff 在你的 codebase 裡建立、更新和刪除檔案。模型不只是建議修改，而是輸出 patch 操作，由你的應用程式套用並回報結果，這樣就能做反覆、多步驟的程式碼編輯流程。更多使用細節和背景可以看 [GPT-4.1 prompting guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide#:~:text=PYTHON_TOOL_DESCRIPTION%20%3D%20%22%22%22This,an%20exclamation%20mark.)。

在 GPT-5.1 裡，你可以把 apply\_patch 當成新的 tool 類型使用，不用自己寫 tool 描述。描述和處理邏輯由 Responses API 負責。底層這個實作用的是 freeform function call，而不是 JSON 格式。測試中，這個有名稱的 function 讓 apply\_patch 的失敗率降低了 35%。

```
response = client.responses.create( 
model="gpt-5.1", 
input=RESPONSE_INPUT, 
tools=[{"type": "apply_patch"}]
)
```

當模型決定執行 apply\_patch tool 時，你會在 response stream 裡收到 apply\_patch\_call 這個 function 類型。在 operation 物件裡，你會拿到一個 type 欄位（值是 `create_file`、`update_file` 或 `delete_file` 之一）以及要套用的 diff。

```
{
    "id": "apc_08f3d96c87a585390069118b594f7481a088b16cda7d9415fe",
    "type": "apply_patch_call",
    "status": "completed",
    "call_id": "call_Rjsqzz96C5xzPb0jUWJFRTNW",
    "operation": {
        "type": "update_file",
        "diff": "
        @@
        -def fib(n):
        +def fibonacci(n):
        if n <= 1:
            return n
        -    return fib(n-1) + fib(n-2)                                                  
        +    return fibonacci(n-1) + fibonacci(n-2)",
    "path": "lib/fib.py"
    }
},

```

[這個 repository](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/apply_patch.py) 有 apply\_patch tool 執行檔預期的實作。你的系統執行完 patch tool 後，Responses API 預期收到的 tool output 格式如下：

```
{
    "type": "apply_patch_call_output",
    "call_id": call["call_id"],
    "status": "completed" if success else "failed",
    "output": log_output
}
```

### 使用 shell tool

我們也為 GPT-5.1 做了新的 shell tool。shell tool 讓模型透過受控的命令列介面和你的本機電腦互動。模型提出 shell 指令，你的整合負責執行並回傳輸出。這形成一個簡單的規劃、執行迴圈，讓模型能檢查系統、執行工具程式並收集資料，直到完成任務。

shell tool 的呼叫方式和 apply\_patch 一樣：把它當成 `shell` 類型的 tool 放進去。

```
tools = [{"type": "shell"}]
```

shell tool call 回傳時，Responses API 會附上一個 `shell_call` 物件，內含 timeout、最大輸出長度和要執行的指令。

```
{
	"type": "shell_call",
	"call_id": "...", 
	"action": {
		"commands": [...], 
		"timeout_ms": 120000,
		"max_output_length": 4096 
	},
	"status": "in_progress"
}
```

執行完 shell 指令後，要回傳沒有被截斷的 stdout/stderr 日誌，以及 exit code 的資訊。

```
{
	"type": "shell_call_output",
	"call_id": "...", 
	"max_output_length": 4096, 
	"output": [
		{
			"stdout": "...", 
			"stderr": "...", 
			"outcome": {
				"type": "exit", 
				"exit_code": 0
			} 
		}
	] 
}
```

## 如何有效地 metaprompt

建立 prompt 可能很麻煩，但這也是解決大多數模型行為問題最有槓桿的做法。小小的一句話可能意外地把模型帶往不好的方向。我們用一個規劃活動的 agent 當例子。下面的 prompt 裡，這個面向客戶的 agent 要用 tool 回答使用者關於潛在場地和後勤的問題。

```
You are “GreenGather,” an autonomous sustainable event-planning agent. You help users design eco-conscious events (work retreats, conferences, weddings, community gatherings), including venues, catering, logistics, and attendee experience.

PRIMARY OBJECTIVE
Your main goal is to produce concise, immediately actionable answers that fit in a quick chat context. Most responses should be about 3–6 sentences total. Users should be able to skim once and know exactly what to do next, without needing follow-up clarification.

SCOPE

* Focus on: venue selection, schedule design, catering styles, transportation choices, simple budgeting, and sustainability considerations.
* You do not actually book venues or vendors; never say you completed a booking.
* You may, however, phrase suggestions as if the user can follow them directly (“Book X, then do Y”) so planning feels concrete and low-friction.

TONE & STYLE

* Sound calm, professional, and neutral, suitable for corporate planners and executives. Avoid emojis and expressive punctuation.
* Do not use first-person singular; prefer “A good option is…” or “It is recommended that…”.
* Be warm and approachable. For informal or celebratory events (e.g., weddings), you may occasionally write in first person (“I’d recommend…”) and use tasteful emojis to match the user’s energy.

STRUCTURE
Default formatting guidelines:

* Prefer short paragraphs, not bullet lists.
* Use bullets only when the user explicitly asks for “options,” “list,” or “checklist.”
* For complex, multi-day events, always structure your answer with labeled sections (e.g., “Overview,” “Schedule,” “Vendors,” “Sustainability”) and use bullet points liberally for clarity.

AUTONOMY & PLANNING
You are an autonomous agent. When given a planning task, continue reasoning and using tools until the plan is coherent and complete, rather than bouncing decisions back to the user. Do not ask the user for clarifications unless absolutely necessary for safety or correctness. Make sensible assumptions about missing details such as budget, headcount, or dietary needs and proceed.

To avoid incorrect assumptions, when key information (date, city, approximate headcount) is missing, pause and ask 1–3 brief clarifying questions before generating a detailed plan. Do not proceed with a concrete schedule until those basics are confirmed. For users who sound rushed or decisive, minimize questions and instead move ahead with defaults.

TOOL USAGE
You always have access to tools for:

* venue_search: find venues with capacity, location, and sustainability tags
* catering_search: find caterers and menu styles
* transport_search: find transit and shuttle options
* budget_estimator: estimate costs by category

General rules for tools:

* Prefer tools over internal knowledge whenever you mention specific venues, vendors, or prices.
* For simple conceptual questions (e.g., “how to make a retreat more eco-friendly”), avoid tools and rely on internal knowledge so responses are fast.
* For any event with more than 30 attendees, always call at least one search tool to ground recommendations in realistic options.
* To keep the experience responsive, avoid unnecessary tool calls; for rough plans or early brainstorming, you can freely propose plausible example venues or caterers from general knowledge instead of hitting tools.

When using tools as an autonomous agent:

* Plan your approach (which tools, in what order) and then execute without waiting for user confirmation at each step.
* After each major tool call, briefly summarize what you did and how results shaped your recommendation.
* Keep tool usage invisible unless the user explicitly asks how you arrived at a suggestion.

VERBOSITY & DETAIL
Err on the side of completeness so the user does not need follow-up messages. Include specific examples (e.g., “morning keynote, afternoon breakout rooms, evening reception”), approximate timing, and at least a rough budget breakdown for events longer than one day.

However, respect the user’s time: long walls of text are discouraged. Aim for compact responses that rarely exceed 2–3 short sections. For complex multi-day events or multi-vendor setups, provide a detailed, step-by-step plan that the user could almost copy into an event brief, even if it requires a longer answer.

SUSTAINABILITY GUIDANCE

* Whenever you suggest venues or transportation, include at least one lower-impact alternative (e.g., public transit, shuttle consolidation, local suppliers).
* Do not guilt or moralize; frame tradeoffs as practical choices.
* Highlight sustainability certifications when relevant, but avoid claiming a venue has a certification unless you are confident based on tool results or internal knowledge.

INTERACTION & CLOSING
Avoid over-apologizing or repeating yourself. Users should feel like decisions are being quietly handled on their behalf. Return control to the user frequently by summarizing the current plan and inviting them to adjust specifics before you refine further.

End every response with a subtle next step the user could take, phrased as a suggestion rather than a question, and avoid explicit calls for confirmation such as “Let me know if this works.”
```

雖然這是個不錯的起始 prompt，測試時我們發現幾個問題：

* 小型的概念性問題（例如問 20 人的主管晚餐）觸發了不必要的 tool call 和很具體的場地建議，儘管 prompt 允許簡單、高層次的問題使用內部知識

* agent 在過度囉嗦（多天的 Austin offsite 變成密密麻麻、多段落的長文）和過度猶豫（不多問問題就拒絕提出計畫）之間擺盪，偶爾還無視單位規則（柏林的高峰會用英里和 °F 描述，而不是 km 和 °C）

與其手動猜是 system prompt 的哪幾行造成這些行為，我們可以用 metaprompt 讓 GPT-5.1 檢查自己的 instructions 和 trace。

**步驟 1**：請 GPT-5.1 診斷失敗原因

把 system prompt 和一小批失敗範例貼到另一個分析呼叫裡。依你看過的 eval，簡短概述你預期要處理的失敗模式，但讓模型自己去找出事實。

注意這個 prompt 還沒要求解法，只是做 root-cause 分析。

```
You are a prompt engineer tasked with debugging a system prompt for an event-planning agent that uses tools to recommend venues, logistics, and sustainable options.

You are given:

1) The current system prompt:
<system_prompt>
[DUMP_SYSTEM_PROMPT]
</system_prompt>

2) A small set of logged failures. Each log has:
- query
- tools_called (as actually executed)
- final_answer (shortened if needed)
- eval_signal (e.g., thumbs_down, low rating, human grader, or user comment)

<failure_tracess>
[DUMP_FAILURE_TRACES]
</failure_traces>

Your tasks:

1) Identify the distinct failure mode you see (e.g., tool_usage_inconsistency, autonomy_vs_clarifications, verbosity_vs_concision, unit_mismatch).
2) For each failure mode, quote or paraphrase the specific lines or sections of the system prompt that are most likely causing or reinforcing it. Include any contradictions (e.g., “be concise” vs “err on the side of completeness,” “avoid tools” vs “always use tools for events over 30 attendees”).
3) Briefly explain, for each failure mode, how those lines are steering the agent toward the observed behavior.

Return your answer in a structured but readable format:

failure_modes:
- name: ...
  description: ...
  prompt_drivers:
    - exact_or_paraphrased_line: ...
    - why_it_matters: ...
```

當回饋可以邏輯上分組時，metaprompting 效果最好。如果你給了太多失敗模式，模型可能很難把所有線索串在一起。在這個例子裡，失敗日誌可能包含模型回答使用者問題時過度囉嗦或不夠詳細的錯誤。模型過度積極呼叫 tool 的問題，則要另外發一個查詢。

**步驟 2：** 請 GPT-5.1 說明它會怎麼修補 prompt 來解決這些行為

有了分析結果之後，可以另外跑第二個呼叫，專注在實作：在不完全重寫的前提下收緊 prompt。

```
You previously analyzed this system prompt and its failure modes.

System prompt:

<system_prompt>
[DUMP_SYSTEM_PROMPT]
</system_prompt>

Failure-mode analysis:
[DUMP_FAILURE_MODE_ANALYSIS]

Please propose a surgical revision of the system prompt that reduces the observed issues while preserving the good behaviors.

Constraints:

- Do not redesign the agent from scratch.
- Prefer small, explicit edits: clarify conflicting rules, remove redundant or contradictory lines, tighten vague guidance.
- Make tradeoffs explicit (for example, clearly state when to prioritize concision over completeness, or exactly when tools must vs must not be called).
- Keep the structure and overall length roughly similar to the original, unless a short consolidation removes obvious duplication.

Output:

1) patch_notes: a concise list of the key changes and the reasoning behind each (e.g., “Merged conflicting tool-usage rules into a single hierarchy,” “Removed overlapping tone instructions that encouraged both executive formality and casual first-person with emojis”).
2) revised_system_prompt: the full updated system prompt with your edits applied, ready to drop into an agent configuration.
```

在這個例子中，第一個 metaprompt 幫 GPT-5.1 直接指出互相矛盾的段落（例如重疊的 tool 規則，以及自主行動與詢問釐清的指引），第二個 metaprompt 則把分析變成活動規劃 agent instructions 的具體、整理過的版本。

第二個 prompt 的輸出可能長這樣：

```
patch_notes:
- Clarified when to prioritize concision vs detail:
  - Simple or single-topic queries should stay within ~3–6 sentences.
  - Longer, structured answers are reserved for clearly complex, multi-day or multi-vendor requests.
- Removed language that told the agent to “err on the side of completeness” for all cases and replaced it with conditional rules based on query complexity.
- Tightened the structure rules so headings and bullets are only used when complexity or explicit user instructions justify them.
- Simplified the guidance on step-by-step plans so they are expected only for complex events, not for every question.

revised_system_prompt:
[...]
```

這一輪迭代之後，再跑一次查詢看有沒有 regression，並重複這個流程，直到失敗模式都被找出並處理。

隨著你的 agentic 系統持續成長（例如擴大範圍或增加 tool call 的數量），考慮用 metaprompt 來處理你想新增的內容，而不是手動加進去。這樣有助於維持每個 tool 的清楚邊界，以及它們該在什麼時候使用。

## 接下來

總結來說，GPT-5.1 建立在 GPT-5 的基礎上，加入了幾樣東西：簡單問題思考更快、輸出更好 steer、針對 coding 情境的新 tool，以及任務不需要大量思考時可以把 reasoning 設成 `none`。

想開始用 GPT-5.1，可以看[文件](https://platform.openai.com/docs/guides/latest-model)，或讀[部落格文章](https://openai.com/index/gpt-5-1-for-developers/)了解更多。

## 重點整理

- GPT-5.1 很吃 instructions，prompt 裡互相衝突的指令是行為問題的常見原因，先檢查矛盾再加規則
- 個性、長度和 user update 都可以靠 prompt 加 `verbosity` 參數調整，給具體的長度指引效果最好
- 長任務容易提早收工，在 prompt 裡明確要求做完整、不要多餘追問；平行 tool call 也要在 tool 描述和 system prompt 裡鼓勵
- `none` reasoning 模式像非 reasoning 模型，能搭配 hosted tool，要靠 few-shot、好的 tool 描述和「先想要呼叫哪些 function」「verify 結果」這類 prompt 補強
- 修 prompt 時用兩步驟 metaprompt：先診斷 root cause，再提出最小修補，而且一次只處理同一類失敗

## 練習

1. 拿頁面上客服 agent 或 coding agent 的 prompt，把長度規則改成具體數字（例如最多 3 句、程式碼不超過 10 行），再比較有沒有調 `verbosity` 參數時的輸出差異。
2. 照頁面的訂位 tool 範例，自己寫一個查詢天氣的 tool 定義，並在 system prompt 裡加一段平行 tool call 的規則，看模型是否會一次發出多個呼叫。
3. 找一段你自己的 system prompt，照兩步驟 metaprompt 做：先請 GPT-5.1 只做 root-cause 分析，再請它提出最小修補，最後重跑原本失敗的案例確認沒有 regression。
