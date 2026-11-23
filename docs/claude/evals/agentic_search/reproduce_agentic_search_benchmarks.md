---
translated: true
source: evals/agentic_search/reproduce_agentic_search_benchmarks.ipynb
---
# 在 Messages API 重現 Claude 的 agentic search benchmark 分數

> 原文：[evals/agentic_search/reproduce_agentic_search_benchmarks.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/evals/agentic_search/reproduce_agentic_search_benchmarks.ipynb)

建一個 Messages API harness，用 programmatic tool calling、server-side compaction 和 task budget，重現公開發表的 DeepSearchQA 與 BrowseComp 分數。

## 這篇在做什麼

Claude 公布的 agentic search 分數可以在公開的 Messages API 上重現，關鍵在 harness 的設定。這篇一步步建出一個搜尋 agent 迴圈，逐一說明 programmatic tool calling、compaction、task budget 等參數為什麼重要，最後用 model-as-judge 算 F1。

## 學完你會

- 用 programmatic tool calling、server-side compaction 和 task budget 建出一個長流程的 agentic search 迴圈
- 正確處理 `pause_turn` 的 round-trip，並用自訂 compaction instructions 保住原始問題
- 換掉資料集、幾行設定和 grader，就把同一個 harness 套到 BrowseComp 或你自己的 deep-research benchmark

## 開跑前

- Anthropic API key，要能使用 `web_search`、`web_fetch`、`code_execution` 這三個 server tool
- 會花錢：notebook 的即時 cell 跑 3 題 demo，大約 5 到 10 分鐘、幾美元；完整 900 題要幾百美元

Claude 公布的 [agentic search 分數](https://www.anthropic.com/system-cards)（DeepSearchQA、BrowseComp）**可以在公開的 Messages API 上重現**。關鍵是 harness 的設定：有幾個 API 參數在短對話裡不重要，但當 agent 跑了 30 次以上的 tool call、橫跨幾十萬 token 時，就變得舉足輕重。

第三方評測分數偏低的常見原因就是 harness 設定。這本 cookbook 會逐一講解每個參數，並說明為什麼重要。

> **成本與執行時間**：這本 notebook 的即時 cell 會跑 **3 題 demo**（大約 5 到 10 分鐘，幾美元的 API 花費）。重現完整的 900 題 benchmark，在中等並行度下要花幾百美元和幾小時；這本 notebook 不會重跑完整版。


## 這本 cookbook 結束時，你會學會：

- **建立**一個 agentic search 迴圈，用 programmatic tool calling、server-side compaction 和 task budget，重現 Claude 公布的 agentic search 分數。
- **理解**每個設定選擇為什麼對長流程的 agentic 任務重要。
- **調整**同一個 harness 到 BrowseComp 或你自己的 deep-research benchmark，只要換資料集、幾行設定和 grader。


## 事前準備

**需要的知識**
- 熟悉 Messages API 和基本的 tool use
- 了解 agentic loop 的概念（呼叫模型 → 處理 tool use → 再呼叫）

**需要的工具**
- Python 3.11+
- `anthropic >= 0.111.0`
- 有權使用 `web_search`、`web_fetch` 和 `code_execution` server tool 的 Anthropic API key（[如何啟用](https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool)）

**建議先看**
- [Programmatic Tool Calling cookbook](https://platform.claude.com/cookbook/tool-use-programmatic-tool-calling-ptc)，介紹我們這裡用的模式
- [Automatic Context Compaction cookbook](https://platform.claude.com/cookbook/tool-use-automatic-context-compaction)，我們會大量依賴它


## 設定


```python
%%capture
%pip install -U "anthropic>=0.111.0" pandas python-dotenv
```

```python
import time

import anthropic
import pandas as pd
from dotenv import load_dotenv
from utils.agentic_search import (
    SAMPLE_QUESTIONS,
    USER_PROMPT_TEMPLATE,
    extract_result_tag,
    grade_response,
    summarize_response,
)

load_dotenv()

MODEL = "claude-sonnet-5-5"
# Hold the grader model fixed so scores are comparable across the model under test.
GRADER_MODEL = "claude-opus-4-6"

# With server-side tools, a single streamed call can run for many minutes of
# in-sandbox tool execution before the first token arrives. We raise the read
# timeout to 60 minutes; with streaming this is a per-event ceiling, not a
# whole-response one, so it only matters for the gap before the first event.
client = anthropic.Anthropic(
    max_retries=20,
    timeout=anthropic.Timeout(5.0, read=3600.0, write=600.0, pool=600.0),
)
```

## 任務

這裡有三個 DeepSearchQA 格式的 demo 問題。每題都有答案，但必須經過多輪搜尋、閱讀和交叉比對才能回答：


```python
for q in SAMPLE_QUESTIONS:
    print(f"[{q['example_id']}] ({q['answer_type']})")
    print(f"  Q: {q['problem']}")
    print(f"  A: {q['answer']}\n")
```

??? note "輸出"

    ```text
    [demo-0] (Single Answer)
      Q: Among the chief executives of the four largest US banks by total assets as of Q1 2024, which one had held their CEO position the longest?
      A: Jamie Dimon

    [demo-1] (Set Answer)
      Q: Which three countries had the largest installed offshore wind capacity at the end of 2023?
      A: China, United Kingdom, Germany

    [demo-2] (Set Answer)
      Q: List the films that won the Palme d'Or at the Cannes Film Festival in 2021, 2022, and 2023, and name the director of each.
      A: Titane (Julia Ducournau), Triangle of Sadness (Ruben Östlund), Anatomy of a Fall (Justine Triet)
    ```

我們把每個問題包進一段簡短的 prompt，要求 Claude 自由規劃，並把最終答案放進 `<result>` 標籤，這樣 grader 才能乾淨地抽出答案：


```python
print(USER_PROMPT_TEMPLATE.format(question=SAMPLE_QUESTIONS[0]["problem"]))
```

??? note "輸出"

    ```text
    I want you to answer the following question.

    <question>Among the chief executives of the four largest US banks by total assets as of Q1 2024, which one had held their CEO position the longest?</question>

    First plan out your response. This part can be as long as needed. You may need to run many searches, this is totally fine.

    Then provide a short and concise answer in <result> tags. For questions expecting multiple answers, separate them with commas.
    ```

模型需要規劃、搜尋網路、抓取並閱讀網頁、執行計算，持續到有把握為止，再給出能被評分的乾淨最終答案。這句話幾乎每個部分，都是天真的 harness 會悄悄丟分的地方。我們會一塊一塊把迴圈建出來。

> 上面這三個問題是為這本 cookbook 寫的（不是取自 DeepSearchQA-900），讓即時 cell 又快又便宜。真正的 benchmark 請看下面的*資料集*。

### 資料集

| Benchmark | Size | Where to get it |
|---|---|---|
| **BrowseComp** | 1,266 questions | [Wei et al., 2025](https://arxiv.org/html/2504.12516v1) (OpenAI) |
| **DeepSearchQA** | 900 questions | [Kaggle Benchmarks](https://www.kaggle.com/benchmarks/google/dsqa) ([paper](https://arxiv.org/abs/2601.20975)) |

Harness 預期每一列都有 `problem`、`answer` 和 `answer_type` 欄位；載入時請把來源 schema 對應過去。


## 1. Tools：programmatic tool calling

效率上最大的槓桿是 **[programmatic tool calling](https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling)**（PTC）：Claude 不直接呼叫 `web_search` 和 `web_fetch`、讓每個結果都來回經過 API，而是在 `code_execution` sandbox 裡寫 Python，並在*程式碼裡面*呼叫 search/fetch。只有程式碼印出的摘要會回到對話中。

對 deep research 來說這非常必要。單一問題可能發出 50 次以上的 fetch。沒有 PTC 的話，每個網頁內容都會進到 context；有 PTC 的話，模型在 sandbox 裡讀取，只把需要的部分帶出來。

做法是只把 `code_execution` 列為可直接呼叫的 tool，並把 `web_search`/`web_fetch` 標成可以從 code execution *裡面*呼叫，而且結果不放進 response：


```python
TOOLS = [
    {
        "type": "code_execution_20260521",
        "name": "code_execution",
    },
    {
        "type": "web_search_20260318",
        "name": "web_search",
        "max_uses": 10_000,
        "allowed_callers": ["code_execution_20260521"],
        "response_inclusion": "excluded",
    },
    {
        "type": "web_fetch_20260318",
        "name": "web_fetch",
        "max_uses": 10_000,
        "max_content_tokens": 1_000_000,
        "allowed_callers": ["code_execution_20260521"],
        "response_inclusion": "excluded",
    },
]

BETAS = [
    "compact-2026-01-12",
    "task-budgets-2026-03-13",
]
```

有兩個細節值得一提：

- **`code_execution_20260521`** 使用的 tool prompt 會揭露 sandbox 每個 cell 的 wall-clock 時間限制，所以 Claude 會把長時間的搜尋切成較短的 cell，而不是寫一個會 timeout 的大迴圈。
- **`response_inclusion: "excluded"`** 讓 `web_search` 和 `web_fetch` 的結果留在 sandbox 裡；response 裡其他所有東西（`thinking`、`text`、`server_tool_use`、code-execution 結果、`compaction`）都會在 §3 用 `model_dump()` round-trip。


## 2. Thinking、effort、budget 和 compaction

四個 request 層級的參數，告訴 Claude *要多努力*以及*怎麼管理自己的 context*：


```python
THINKING = {"type": "adaptive"}

OUTPUT_CONFIG = {
    "effort": "max",
    "task_budget": {"type": "tokens", "total": 3_000_000},
}

# Match the system-card configuration. To reproduce a different model's score,
# use the effort tier and compaction trigger from that model's model card.
COMPACTION_TRIGGER = 200_000

COMPACT_INSTRUCTIONS = (
    "Your summary MUST begin by restating the user's ORIGINAL QUESTION "
    "verbatim and in full, wrapped in <original_question> and "
    "</original_question> tags. Then summarize the research progress so "
    "far: key sources found, data extracted, partial answers, and what "
    "remains to be done. Do NOT call any tools. Your summary MUST also "
    "include this instruction verbatim: 'Provide your final answer "
    "wrapped in <result> and </result> tags.'"
)

CONTEXT_MANAGEMENT = {
    "edits": [
        {
            "type": "compact_20260112",
            "trigger": {"type": "input_tokens", "value": COMPACTION_TRIGGER},
            "instructions": COMPACT_INSTRUCTIONS,
        }
    ]
}
```

### 為什麼 `COMPACT_INSTRUCTIONS` 這麼重要

當對話到達觸發門檻時，API 會做 compaction：另一次模型呼叫把歷史摘要起來，agent 從摘要繼續。預設的摘要 prompt 設計上與任務無關；它不知道*對 benchmark 來說*，原始問題和答案格式指示是絕對必須保留的兩樣東西。[自訂 `instructions`](https://platform.claude.com/docs/en/build-with-claude/compaction#custom-summarization-instructions) 就是告訴它的方式。

沒有這些 instructions 的話，compaction 之後的 agent 手上有*它找到了什麼*的摘要，卻沒有*它被問了什麼*，而在長問題上它常常會要求使用者重述問題，這樣就是零分。

這個效果隨 compaction 觸發的頻率放大：在低觸發門檻下最大（單一問題可能 compact 好幾次），在這裡用的 200K 觸發門檻下較小，但不管怎樣，這都是 harness 裡最便宜的保險。

> **注意**：最新的 Claude model card 回報的 DeepSearchQA *沒有* compaction（模型有 1M token 的 context window，所以 1M budget 的任務放得進一個 window），而 BrowseComp 是在 3M 總 budget *有* compaction 下回報的。我們這裡用 3M budget 的 BrowseComp 設定，讓 compaction 有意義；在 DeepSearchQA 上，大部分問題還是遠低於 1M 就結束，不會觸發它。

另外三個：

| Parameter | Why |
|---|---|
| `thinking: adaptive` | 讓 Claude 在結果出乎意料時於 tool call 之間思考，不意外時就跳過思考 |
| `effort` | Model card 的數字是在模型最高的 effort 等級下回報的 |
| `task_budget.total` | 告訴 Claude 它橫跨所有 turn 和 compaction 的累計輸出 budget，讓它自己掌握節奏，而不是太早放棄 |


## 3. Round-trip 迴圈

使用 server-side tool 時，每次 API 呼叫內部可以跑很多次 tool 迭代，然後以 `stop_reason="pause_turn"` 回傳做 checkpoint。我們在 client 端的工作只是：取出 response content，附加成 assistant turn，再呼叫一次。一直做到 `stop_reason="end_turn"`。

有一個 helper 讓跨 turn 的 request body 保持整齊：


```python
def truncate_to_last_compaction(messages: list[dict]) -> list[dict]:
    """Drop history that precedes the most recent compaction block.

    The server already discarded that history when it compacted; resending it is
    pure overhead and on long runs can exceed the 32 MB request-body limit.
    `messages[0]` (the original user prompt) is always kept so the request still
    starts with a user turn.
    """
    for mi in range(len(messages) - 1, 0, -1):
        content = messages[mi].get("content")
        if not isinstance(content, list):
            continue
        for bi in range(len(content) - 1, -1, -1):
            blk = content[bi]
            if isinstance(blk, dict) and blk.get("type") == "compaction":
                trimmed = {**messages[mi], "content": content[bi:]}
                return [messages[0], trimmed, *messages[mi + 1 :]]
    return messages
```

接著是迴圈本身。它是單一函式，雖然長，但每一行都是真實 benchmark 執行需要的：


```python
def sample(question: str, *, max_turns: int = 100) -> dict:
    """Run one question to completion through the agentic search loop."""
    # cache_control on the user message turns on prompt caching for the whole
    # request, so the server-side tool loop caches between iterations.
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": USER_PROMPT_TEMPLATE.format(question=question),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
    ]
    request = {
        "model": MODEL,
        "max_tokens": 64_000,
        "tools": TOOLS,
        "betas": BETAS,
        "thinking": THINKING,
        "output_config": OUTPUT_CONFIG,
        "context_management": CONTEXT_MANAGEMENT,
        "messages": messages,
    }

    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}
    transcript: list[str] = []
    tool_calls = 0
    start = time.time()

    for turn in range(max_turns):
        # Stream so the per-event read-timeout applies, not a per-response one.
        with client.beta.messages.stream(**request) as stream:
            response = stream.get_final_message()

        usage["input_tokens"] += response.usage.input_tokens
        usage["output_tokens"] += response.usage.output_tokens
        usage["cache_read_input_tokens"] += (
            getattr(response.usage, "cache_read_input_tokens", 0) or 0
        )
        tool_calls += sum(
            1 for b in response.content if getattr(b, "type", "") == "server_tool_use"
        )
        transcript.append(f"--- turn {turn} ---\n" + summarize_response(response))

        # Persist the code-execution container so state survives across turns.
        if getattr(response, "container", None) is not None:
            request["container"] = response.container.id

        # Round-trip: append assistant content, drop pre-compaction history.
        messages.append(
            {
                "role": "assistant",
                "content": [b.model_dump(exclude_none=True) for b in response.content],
            }
        )
        messages[:] = truncate_to_last_compaction(messages)

        if response.stop_reason == "end_turn":
            final_text = "".join(
                b.text for b in response.content if getattr(b, "type", "") == "text"
            )
            return {
                "text": final_text,
                "result": extract_result_tag(final_text),
                "turns": turn + 1,
                "tool_calls": tool_calls,
                "elapsed_s": time.time() - start,
                "usage": usage,
                "transcript": transcript,
            }
        if response.stop_reason not in ("pause_turn", "max_tokens"):
            raise RuntimeError(f"unexpected stop_reason={response.stop_reason}")

    raise RuntimeError(f"did not finish within {max_turns} turns")
```

### 重試

SDK 會在連線錯誤、`408`、`409`、`429` 和 `≥500` 的回應時，用 exponential backoff [自動重試](https://platform.claude.com/docs/en/api/sdks/python#retries)，也會遵守 API 在 rate-limit 回應中送的 `Retry-After` header。預設是重試 2 次；跑完整 benchmark 時，我們在 client 上設 `max_retries=20`（在上面的*設定*裡），這樣執行中途短暫過載不會讓某題被算成零分。

> **發現隱形的 tool 限流**：server-tool 的 rate limit 跟模型的 token limit 是分開的。用完它不會丟出 API 錯誤；`too_many_requests` 會以 tool-result 錯誤的形式出現在 response 裡，Claude 通常會在 sandbox 內重試。如果完整 benchmark 跑出來分數意外偏低又沒有例外，檢查 `result["transcript"]`，看有沒有 code-execution cell 印出 `rate_limit_error` 或 `too_many_requests`。Client 端的解法是降低並行度（或聯絡 Anthropic support 要更高的 tool rate limit）；client 重試沒用，因為 API 呼叫回的是 200。
>
> 同樣地，把每題的 `sample()` 呼叫包在 `try/except` 裡，這樣單一的 `stop_reason="refusal"` 或無法恢復的錯誤，只會讓那題算零分，而不是中斷整個執行。


## 4. 端到端跑一題

我們來跑第一題。這個 cell 預期要跑一兩分鐘：在那個單一的 `stream()` 呼叫背後，Claude 正在寫並執行好幾次搜尋程式碼。


```python
result = sample(SAMPLE_QUESTIONS[0]["problem"])

print(f"tool_calls={result['tool_calls']}  elapsed={result['elapsed_s']:.0f}s")
print(
    f"tokens: in={result['usage']['input_tokens']:,}  out={result['usage']['output_tokens']:,}  "
    f"cache_read={result['usage']['cache_read_input_tokens']:,}"
)
print()
print("Final <result>:", result["result"])
```

??? note "輸出"

    ```text
    tool_calls=4  elapsed=56s
    tokens: in=130  out=3,842  cache_read=39,703

    Final <result>: **Jamie Dimon**, CEO of **JPMorgan Chase**, had held his CEO position the longest among the chief executives of the four largest US banks by total assets (JPMorgan Chase, Bank of America, Citigroup, and Wells Fargo) as of Q1 2024. Dimon became JPMorgan Chase's CEO on January 1, 2006 — roughly 18 years by Q1 2024 — compared to Brian Moynihan (Bank of America CEO since January 2010), Charles Scharf (Wells Fargo CEO since October 2019), and Jane Fraser (Citigroup CEO since March 2021).
    ```

Transcript 顯示工作的形狀。每個 turn 都是一批 sandbox 內 tool call 之後的 `pause_turn` checkpoint：


```python
for line in result["transcript"]:
    print(line + "\n")
```

??? note "輸出"

    ```text
    --- turn 0 ---
      [thinking]  963 chars
      [text]      I'll research this step by step: first identifying the four largest US banks by total assets as of Q
      [tool_use]  code_execution
      [code_execution_tool_result]
      [thinking]  82 chars
      [tool_use]  code_execution
      [code_execution_tool_result]
      [thinking]  511 chars
      [tool_use]  code_execution
      [code_execution_tool_result]
      [thinking]  1365 chars
      [tool_use]  code_execution
      [code_execution_tool_result]
      [thinking]  700 chars
      [text]      Based on my research, I now have sufficient information to answer this question.  **Summary of findi
      [text]      "JPMorgan Chase & Co., the largest US bank by total assets, reported a sequential increase of $215.3
      [text]       were the other top banks, a ranking that held consistently across 2024.  Their respective CEOs and 
      [text]      Dimon became CEO on January 1, 2006 and one year later also became Chairman of the Board.
      [text]        2. **Bank of America – Brian Moynihan**: 
      [text]      Moynihan took office on January 1, 2010, and also is a member of the Bank of America board of direct
      [text]        3. **Wells Fargo – Charles Scharf**: 
      [text]      The current CEO and President is Charles W. Scharf, appointed in September 2019
      [text]      , with his effective start date being October 21, 2019 according to Wells Fargo's official announcem
      [text]      Jane Fraser is a British-American banking executive who has been chief executive officer (CEO) of Ci
      [text]      , becoming the first woman to lead a major U.S. bank.  Comparing the start dates — 2006 for Dimon, 2
      usage: in=130 out=3,842 cache_read=39,703 stop=end_turn
    ```

## 5. 評分

Benchmark 評分用 model-as-judge 的 F1 grader。Grader 看到問題、標準答案和抽出來的 `<result>` 文字，然後回報找到了哪些標準答案項目，以及出現哪些不在標準答案集合裡的額外項目。從這些我們算出 precision、recall 和 F1。

有兩件事要做對：

- **對 `<result>` 標籤評分，不是整份 response。** 完整 response 包含規劃的文字和搜尋摘要；餵給 grader 會讓 false positive 和 false negative 都膨脹。`extract_result_tag()` 只抽出最終答案。
- **固定 grader 模型。** 不管 `MODEL` 是什麼，我們都用 `GRADER_MODEL = "claude-opus-4-6"`。用受測的模型自己評分，會讓不同模型的分數無法比較。

Grader prompt 很直接：


~~~text
Your task is to evaluate whether a given response arrived at the correct answer.

Question: <question>{question}</question>
Correct answer (type: {answer_type}): <correct_answer>{answer}</correct_answer>
Response to evaluate: <response>{response}</response>

For each expected answer item, indicate whether it appears in the response.
Then list any answers in the response that are NOT in the correct-answer list.
Wording does not need to match exactly.

Reply in this exact XML format:
<evaluation>
  <explanation>one sentence</explanation>
  <correctness_details>
    <item answer="expected_item_1" correct="true|false"/>
  </correctness_details>
  <excessive_answers>
    <item>extra_item_if_any</item>
  </excessive_answers>
</evaluation>
~~~

解析和 precision/recall/F1 的算術放在 [`utils/agentic_search.py`](https://github.com/anthropics/claude-cookbooks/blob/main/evals/agentic_search/utils/agentic_search.py)；這裡我們直接呼叫它：


```python
grade = grade_response(client, GRADER_MODEL, SAMPLE_QUESTIONS[0], result["text"])
print(f"answer    : {grade['extracted_answer']}")
print(f"precision : {grade['precision']:.2f}")
print(f"recall    : {grade['recall']:.2f}")
print(f"F1        : {grade['f1']:.2f}")
```

??? note "輸出"

    ```text
    answer    : **Jamie Dimon**, CEO of **JPMorgan Chase**, had held his CEO position the longest among the chief executives of the four largest US banks by total assets (JPMorgan Chase, Bank of America, Citigroup, and Wells Fargo) as of Q1 2024. Dimon became JPMorgan Chase's CEO on January 1, 2006 — roughly 18 years by Q1 2024 — compared to Brian Moynihan (Bank of America CEO since January 2010), Charles Scharf (Wells Fargo CEO since October 2019), and Jane Fraser (Citigroup CEO since March 2021).
    precision : 1.00
    recall    : 1.00
    F1        : 1.00
    ```

## 6. 跑 demo 集

現在三題全跑，用量和 F1 放進比較表。（要跑完整的 900 題 benchmark，把 `SAMPLE_QUESTIONS` 換成完整資料集並加上並行；見*下一步*。）


```python
rows = []
for q in SAMPLE_QUESTIONS:
    r = sample(q["problem"])
    g = grade_response(client, GRADER_MODEL, q, r["text"])
    rows.append(
        {
            "id": q["example_id"],
            "tool_calls": r["tool_calls"],
            "in_tokens": r["usage"]["input_tokens"],
            "out_tokens": r["usage"]["output_tokens"],
            "f1": g["f1"],
            "answer": g["extracted_answer"][:60],
        }
    )

df = pd.DataFrame(rows)
print(df.to_string(index=False))
print(f"\nMean F1: {df['f1'].mean():.2f}")
# in_tokens is the uncached billed input; with caching on, most of the actual
# context is cache reads (tracked separately in usage.cache_read_input_tokens).
print(f"Total tokens: {df['in_tokens'].sum():,} in / {df['out_tokens'].sum():,} out")
```

??? note "輸出"

    ```text
        id  tool_calls  in_tokens  out_tokens  f1                                                        answer
    demo-0          11        312       10503 1.0  **Jamie Dimon**, CEO of **JPMorgan Chase** (the largest US b
    demo-1           7        208        9768 1.0  The three countries with the largest installed offshore wind
    demo-2           3        104        1592 1.0 - **2021**: *Titane* — directed by Julia Ducournau\n- **2022*

    Mean F1: 1.00
    Total tokens: 624 in / 21,863 out
    ```

## 7. 擴展到完整 benchmark

用這本 notebook 的設定跑完整的 DeepSearchQA-900 和 BrowseComp-1266，可以重現公布的 model-card 分數。各模型公布的 agentic search 分數，請看各自的 [Claude model card](https://www.anthropic.com/system-cards)。


## 8. 套用到 BrowseComp

BrowseComp 的問題是單一答案（「Which 1995 film…」），不是集合型的，所以 harness 唯一的改動是 grader：


```python
from utils.agentic_search import grade_browsecomp

# Grading: a single-letter judge (A=correct, B=incorrect, C=abstain).
# accuracy = fraction of "A" verdicts.
bc_grade = grade_browsecomp(client, GRADER_MODEL, SAMPLE_QUESTIONS[0], result["text"])
print(bc_grade)
```

??? note "輸出"

    ```text
    {'example_id': 'demo-0', 'extracted_answer': "**Jamie Dimon**, CEO of **JPMorgan Chase**, had held his CEO position the longest among the chief executives of the four largest US banks by total assets (JPMorgan Chase, Bank of America, Citigroup, and Wells Fargo) as of Q1 2024. Dimon became JPMorgan Chase's CEO on January 1, 2006 — roughly 18 years by Q1 2024 — compared to Brian Moynihan (Bank of America CEO since January 2010), Charles Scharf (Wells Fargo CEO since October 2019), and Jane Fraser (Citigroup CEO since March 2021).", 'grader_letter': 'A', 'accuracy': 1.0}
    ```

Tool、beta 和 `sample()` 迴圈都不變。如果你想嚴格重現，請查 model card 上 BrowseComp 回報時用的 effort 等級和 compaction 觸發門檻；§2 的值是個不錯的預設。

重點就是：迴圈一旦對了，換 benchmark 只要換資料集、幾行設定和一個 grader。


## 總結

你建了一個 agentic search 迴圈，它：

- 從 code execution **以程式方式呼叫** `web_search` 和 `web_fetch`，讓 50 次以上的網頁抓取不會灌爆 context（§1）。
- 告訴 Claude **要多努力**（`effort`、`task_budget`）和**怎麼思考**（`adaptive`）（§2）。
- 靠**在 compaction prompt 裡重述問題**撐過 compaction，這是高 compaction 頻率下最大的槓桿（§2）。
- 正確 round-trip `pause_turn` response，保留 code container 並修剪 compaction 之前的歷史（§3）。
- 用 model-as-judge F1 grader 評分，並重現公布的 DeepSearchQA 分數（§5–7）。


## 下一步

- **擴展到完整 benchmark**：把 `sample()` 包進 `concurrent.futures.ThreadPoolExecutor`（client 是 thread-safe 的）；SDK 內建的重試已經涵蓋 429/529。並行度 50 時，DeepSearchQA-900 大約 2 小時跑完。
- **試試 multi-agent 版本**：[Async Multi-Agent Orchestration cookbook](https://platform.claude.com/cookbook/patterns-agents-async-multi-agent-orchestration) 示範 N 個 agent 的團隊如何用更低的延遲，超過這個單一 agent 迴圈的準確度。
- **移植到你自己的 benchmark**：合約是 `[{problem, answer, answer_type}]` 的資料列、幾行設定和一個 grader 函式。迴圈本身不變。
- **讀 model card**：各模型的 [Claude model card](https://www.anthropic.com/system-cards) 記載了每個公布的 benchmark 數字是用什麼設定產生的。


## 重點整理

- 長流程 agent 的分數高低，很大程度取決於 harness 設定，不只是模型本身。
- Programmatic tool calling 讓網頁內容留在 sandbox，只把摘要帶回對話，是效率上最大的槓桿。
- Compaction 的自訂 instructions 要明確要求保留原始問題和答案格式，否則 agent 會忘記自己被問了什麼。
- Server tool 的限流不會丟 API 錯誤，分數異常低時要去看 transcript，不是只看 exception。
- 評分要固定 grader 模型，並且只對 `<result>` 標籤內的內容評分。

## 練習

1. 把 `SAMPLE_QUESTIONS` 改成只跑一題，並印出每個 `pause_turn` 的次數，看這題實際用了幾輪。
2. 把 `COMPACT_INSTRUCTIONS` 拿掉（用預設摘要），再把 compaction 觸發門檻調低，比較同一題的答案和 F1 有沒有變差。
3. 照 §8 把 grader 換成單一答案版本，用你自己寫的 3 題 `problem`/`answer`/`answer_type` 資料列跑一次，確認整個迴圈不用改。
