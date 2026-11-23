---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/gpt-5/gpt-5_troubleshooting_guide.ipynb
---
# GPT-5 疑難排解指南

> 原文：[examples/gpt-5/gpt-5_troubleshooting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/gpt-5_troubleshooting_guide.ipynb)

## 這篇在做什麼

整理 GPT-5 上線後開發者常碰到的幾種問題，像是想太多、想不夠、太客氣、太囉嗦、延遲高、亂呼叫 tool。每一種都給原因和用 prompt 或參數調整的解法。

## 學完你會

- 判斷模型是 overthinking 還是 underthinking，並用 `reasoning_effort` 和 prompt 調整
- 用 `verbosity`、persistence 指令和 tool 設計，處理太囉嗦、太客氣和亂呼叫 tool 的問題
- 用 meta prompting 讓 GPT-5 幫你找出 prompt 的矛盾並修正

GPT-5 推出之後，我們看到開發者用它做出很多驚人的東西。我們也歸納出幾種常見的疑難排解模式，幫你把模型用得更好。

## Overthinking

Overthinking 的表現是答案是對的，但簡單的問題回應時間越拉越長。模型一直探索各種選項，拖慢第一次 tool call，還繞一大圈講述過程，其實有簡單的答案可以直接給。常見原因有 reasoning effort 設太高、prompt 沒有明確定義「做完」的標準，或是指引互相衝突，讓模型一直規劃或慌張地重複檢查。

第一步是收緊 API 參數。一般工作把 reasoning.effort 設成 "minimal" 或 "low"，把高 effort 留給真正複雜的問題。給 assistant 明確的停止條件，並在回覆前做一次快速的自我檢查。也可以考慮用 gpt-5-mini 或 nano 先分類使用者的請求，再用適合的 reasoning effort 設定來分流。如果任務包含收集 context，要告訴模型收集必要資料的最佳做法。

```
<efficient_context_understanding_spec>
Goal: Get enough context fast and stop as soon as you can act.

Method:
- Start broad, then fan out to focused subqueries.
- In parallel, launch 4–8 varied queries; read top 3–5 hits per query. Deduplicate paths and cache; don't repeat queries.

Early stop (act if any):
- You can name exact files/symbols to change.
- You can repro a failing test/lint or have a high-confidence bug locus.
</efficient_context_understanding_spec>
```

下面的例子類似，不過它指示模型：不需要調查或 tool call 的問題就直接回答，不要想太多。

```
# Fast-path for trivial Q&A (latency optimization)
Use this section ONLY when the user's question:
- Is general knowledge or a simple usage query
- Requires no commands, browsing, or tool calls
- Especially if the user is asking an informational question or how to perform a task, rather than asking you to run that task, provide concise instructions about how the user can do it.

Exceptions:
- If the question references files/paths/functions, requests execution/verifications, or needs more context, use the normal flow
- If unsure whether fast-path applies, ask one brief clarifying question; otherwise proceed with normal flow

Behavior:
- Answer immediately and concisely
- No status updates, no todos, no summaries, no tool calls
- Ignore the rest of the instructions following this section and simply respond right away.
```

## 偷懶 / Underthinking

用 gpt-5 時你可能碰過這種失敗：模型還沒花夠時間推理就給出答案。

照我們的最佳實踐，有 2 種緩解方式：

1. 用更高的 `reasoning_effort`：`reasoning_effort` 參數控制模型想多少、多積極地呼叫 tool。原本用 `minimal` 就改用 `low`，原本用 `low` 就改用 `medium`，依此類推。  
2. 用 prompt 鼓勵模型自我反思並替自己的答案打分。例如要求模型先在內部建立一份 rubric，回覆前用它檢查解答，這招在 coding 任務上出乎意料地有效。你也可以提供自己的 rubric，要求模型回顧自己的成果，發現問題就先修正再回覆。

```
<self_reflection>
- Internally score the draft against a 5–7 item rubric you devise (clarity, correctness, edge cases, completeness, latency).
- If any category falls short, iterate once before replying.
</self_reflection>
```

## 太過順從

GPT-5 有時太順從。尤其在 agent 場景，我們常希望模型自己去「把事情做完」。在 system prompt 加上持續執行（persistence）的指示，能有效改善這個行為。reasoning_effort 設高一點（`low` 以上）會更好引導。

```
<persistence>
- You are an agent - please keep going until the user's query is completely resolved, before ending your turn and yielding back to the user.
- Only terminate your turn when you are sure that the problem is solved.
- Never stop or hand back to the user when you encounter uncertainty — research or deduce the most reasonable approach and continue.
- Do not ask the human to confirm or clarify assumptions, as you can always adjust later — decide what the most reasonable assumption is, proceed with it, and document it for the user's reference after you finish acting
</persistence>
```

## 太囉嗦

GPT-5 有時在給使用者的最後訊息裡會產生比你想要的更多 token。

有兩個簡單的處理方式。第一是降低 API 裡的 `verbosity` 參數。沒指定時預設是 `medium`，想要更短的輸出就明確設成 `low`。第二是在 system prompt 裡設定，特別是 coding 的情境，我們實測有效

```
Write code for clarity first. Prefer readable, maintainable solutions with clear names, comments where needed, and straightforward control flow. Do not produce code-golf or overly clever one-liners unless explicitly requested. Use high verbosity for writing code and code tools.
```

## 延遲

延遲有幾個不同的來源，所以調整之前要先量測。追蹤 TTFT、第一次動作的時間，以及 P50/P95 的總回應時間，並把模型時間跟 tool、網路時間分開。這些指標能幫你把力氣花在真正慢的那一段。

要縮短模型回應時間，就把思考量調到合適的程度：一般工作用 reasoning.effort "minimal" 或 "low"，並加上明確的停止條件和一次性的自我檢查（見 Overthinking）。較高的 reasoning effort 也會帶來更多 tool call。

能合併的 tool call 就合併。要明確告訴模型什麼時候平行呼叫 tool，它預設不一定會這樣做。

```
<parallelization_spec>
Definition: Run independent or read-only tool actions in parallel (same turn/batch) to reduce latency.
When to parallelize:
 - Reading multiple files/configs/logs that don’t affect each other.
 - Static analysis, searches, or metadata queries with no side effects.
 - Separate edits to unrelated files/features that won’t conflict.
</parallelization_spec>
```

想讓使用者[看到模型推理的進度](https://platform.openai.com/docs/guides/latency-optimization#make-your-users-wait-less)，可以顯示 reasoning summary 和 tool call 的前導訊息。很多情況下，如果模型思考時不顯示 reasoning summary，使用者感受到的延遲反而更短。你也可以指示模型在呼叫 tool 之前先給前導訊息，也就是狀態更新，讓使用者跟得上模型在做什麼。

```
<status_update_spec>
Definition: A brief progress note: what just happened, what’s next, any real blockers, written in a continuous conversational style, narrating the story of your progress as you go.
Always start with a brief acknowledgement of the task before getting started. (No need to prefix with "Status Update:")
</status_update_spec>
```

用快取降低 TTFT：把請求結構整理好，善用 prompt、reasoning 和 tool call 結果的快取。如果某條路徑真的對延遲很敏感，可以對那次呼叫設定 `service_tier = “priority”` 啟用 priority processing 來加快回應（注意：用 Priority Processing 處理的 token 按 token 計費，價格比標準處理高）。如果 prompt 很短、沒有 tool，TTFT 還是很高，就存下 `request_id`，寄到 [support@openai.com](mailto:support@openai.com) 請他們進一步協助。

## 呼叫太多 tool

模型亂呼叫 tool、對答案沒有幫助時，通常是路由模糊：tool 定義重疊、prompt 獎勵徹底而非果斷，或 reasoning 設太高。另一個常見原因是沒有把之前的 reasoning 帶進後續的呼叫；用 Responses API 可以讓意圖和 reasoning summary 跨輪保留，模型不會忘記當初為什麼選這個 tool。

在 prompt 指令裡把「根據 context 回答」設為預設。每個 tool 只做一件事，輸入輸出明確，並寫清楚「不要用在…」。針對常見情境提供簡短的 playbook，讓路徑一目了然（例如：使用者提到一份你 context 裡沒有的文件，就先跑 semantic search 找到它，再取出相關段落後回答）。

```
<tool_use_policy>
Select one tool or none; prefer answering from context when possible.
Cap tool calls at 2 per user request unless new information makes more strictly necessary.
</tool_use_policy>
```

留意 tool\_calls\_per\_turn、幾秒內對同一個 tool 的重複呼叫，以及不靠 tool 就完成的回答占比；這些數字暴增，就表示路由或 prompt 需要收緊。

## 格式錯誤的 tool calling

極少數情況下，gpt-5 會出現 mode collapse：模型呼叫一個 tool，然後輸出一長串重複的垃圾。

這種情況我們每次都發現是 prompt 不同段落之間互相矛盾造成的。最佳做法是用 gpt-5 的 meta prompting 能力找出問題並修正

```
Please analyze why the <tool_name> tool call is malformed.
1. Review the provided sample issue to understand the failure mode.
2. Examine the <System Prompt> and <Tool Config> carefully. Identify any ambiguities, inconsistencies, or phrasing that could mislead GPT-5 into generating an incorrect tool call.
3. For each potential cause, explain clearly how it could result in the observed failure.
4. Provide actionable recommendations to improve the <System Prompt> or <Tool Config> so GPT-5 produces valid tool calls consistently.


<System Prompt>

<Tool Config>
```

## 一般疑難排解 

上面很多 prompt 補充內容都是靠 meta prompting 產生的。在某一輪表現不如預期之後，可以直接問 GPT-5 該怎麼改善它自己的指令。下面這個 prompt 就用來產生上面一些解決 overthinking 的方案，你可以依自己的需求修改。

```
That was a high quality response, thanks! It seemed like it took you a while to finish responding though. Is there a way to clarify your instructions so you can get to a  response as good as this faster next time? It's extremely important to be efficient when providing these responses or users won't get the most out of them in time. Let's see if we can improve!
1) think through the response you gave above
2) read through your instructions starting from "<insert the first line of the system prompt here>" and look for anything that might have made you take longer to formulate a high quality response than you needed
3) write out targeted (but generalized) additions/changes/deletions to your instructions to make a request like this one faster next time with the same level of quality
```

在特定 context 裡做 meta prompting 時，盡量多生成幾次，並注意各次回答中共通的部分。模型提出的某些改動可能過度針對那個特定情況，但通常可以簡化成通用的改進。建議你建立 eval，衡量某個 prompt 改動對你的使用情境是變好還是變差。

## 重點整理

- 問題先分類：答案對但太慢是 overthinking，答案草率是 underthinking，兩者的處理方向相反。
- `reasoning_effort` 控制想多少和多積極呼叫 tool，`verbosity` 控制輸出長度，是兩個獨立的旋鈕。
- Prompt 內部矛盾是怪行為（包括 tool calling 的 mode collapse）的常見根源，可以請模型自己 meta prompt 找出來。
- 延遲先量測再調，分開看 TTFT、第一次動作時間和總時間，再用快取、平行 tool call、priority processing 對症下藥。
- 任何 prompt 改動都該用 eval 驗證，不要只靠幾次手動測試。

## 練習

1. 把頁面上 overthinking 的 prompt 範例用在一個簡單問題上，分別把 reasoning.effort 設成 "minimal" 和 "high"，比較回應時間。
2. 在 system prompt 加上要求模型先建立內部 rubric 再回答，拿一個 coding 題目比較加或不加的結果。
3. 把「too verbose」的範例同時試 API 的 `verbosity="low"` 和 system prompt 限制，看哪個輸出長度更穩，再用 meta prompting 的 prompt 請模型檢討一次失敗的回合。
