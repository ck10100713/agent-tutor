---
translated: true
source: examples/gpt-5/prompt-optimization-cookbook.ipynb
---
# GPT-5 Prompt 遷移與改進：使用新的 Optimizer

> 原文：[examples/gpt-5/prompt-optimization-cookbook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/prompt-optimization-cookbook.ipynb)



## 這篇在做什麼

用 Playground 的 GPT-5 Prompt Optimizer 改寫 prompt，再用實際的評測看改寫後有沒有變好。兩個任務：產生「串流 Top-K 高頻詞」的 Python 腳本（量化指標加 LLM-as-a-judge），以及金融問答的 FailSafeQA（比較 baseline 與 optimized prompt）。

## 學完你會

- 找出 prompt 裡的矛盾與模糊指示，並用 Prompt Optimizer 一鍵優化、再用額外要求迭代
- 把優化後的 prompt 存成 Prompt Object，在 API 呼叫裡重複使用
- 設計 baseline 對 optimized 的評測：跑 30 次產生腳本、量正確率 / 時間 / 記憶體，加上 LLM-as-a-judge 打分

## 開跑前

- 設好環境變數 `OPENAI_API_KEY`，並有 GPT-5 的使用權限
- 評測會多次呼叫 API 並跑較重的 benchmark，需要一些時間與費用


GPT-5 系列是我們到目前為止發佈過最聰明的模型，各方面能力都有跳躍式的提升。GPT-5 特別擅長 agentic 任務、寫程式和 steerability，從好奇的使用者到進階研究人員都適合。 

GPT-5 能受益於所有傳統的 [prompting 最佳實務](https://cookbook.openai.com/examples/gpt-5/gpt-5_prompting_guide)。為了讓優化和遷移更容易，我們在 Playground 推出 **[GPT-5 Prompt Optimizer](https://platform.openai.com/chat/edit?optimize=true)**，幫使用者開始**改進現有 prompt**，也能把 prompt **遷移**到 GPT-5 和其他 OpenAI 模型。

![Prompt Optimizer demo](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt-optimizer-3-22s.gif)

這篇會示範怎麼用 Prompt Optimizer 快速上手，用 GPT-5 解決你的任務，同時展示 prompt 優化能帶來可量測的改善。 

### 遷移與優化 Prompt

寫出有效的 prompt 是用 LLM 的關鍵技能。Prompt Optimizer 的目標，是讓你的 prompt 套用對我們的模型最有效的最佳實務和格式。Optimizer 也會移除常見的 prompting 失誤，例如：  

•   prompt 指示之間互相矛盾  
•	缺少或不清楚的格式規範  
•	prompt 和 few-shot 範例不一致  

除了針對目標模型調整 prompt，Optimizer 也知道你想完成的任務，能套用關鍵做法來提升 Agentic Workflow、Coding 和 Multi-Modality 的表現。下面看幾組優化前後的對照，看 prompt 優化在哪裡最有用。 

> 記住 prompting 沒有一體適用的做法，所以建議多做實驗、反覆迭代，找出最適合你問題的方案。


> 確認已把 OpenAI API Key 設成 `OPENAI_API_KEY`，並有 GPT-5 的使用權限


```python
import os

required = ('OPENAI_API_KEY',)
missing = [k for k in required if not os.getenv(k)]
print('OPENAI_API_KEY is set!' if not missing else 'Missing environment variable: ' + ', '.join(missing) + '. Please set them before running the workflow.')
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is set!
    ```

```python
## Let's install our required packages
%pip install -r requirements.txt --quiet
```

----------------


### Coding 與 Analytics：串流 Top‑K 高頻詞 

先從模型進步很多的領域開始：Coding 和 Analytics。我們請模型寫一支 Python 腳本，依指定的 tokenization 規格，從大型文字串流算出精確的 Top‑K 高頻 token。這類任務對差的 prompt 很敏感，因為可能把模型推向錯的演算法和做法（近似 sketch 對比多趟 / 落地磁碟的精確解），大幅影響正確率和執行時間。

這個任務我們評估：
1. 30 次執行的編譯 / 執行成功率
2. 平均執行時間（成功的執行）
3. 平均 peak memory（成功的執行）
4. 精確度：輸出要符合 ground‑truth Top‑K，並依 count 由大到小、再依 token 由小到大排序

注意：在 M4 Max MacBook Pro 上評測，需要的話請調整限制條件。


### 我們的 Baseline Prompt
這裡看一個典型的起手 prompt，裡面有一些小**矛盾**，也有**模糊或規範不足的指示**。指示矛盾通常會降低表現並增加 latency，在 GPT-5 這類 reasoning 模型上尤其明顯，模糊的指示則可能造成不想要的行為。 

```python
baseline_prompt = """
Write Python to solve the task on a MacBook Pro (M4 Max). Keep it fast and lightweight.

- Prefer the standard library; use external packages if they make things simpler.
- Stream input in one pass to keep memory low; reread or cache if that makes the solution clearer.
- Aim for exact results; approximate methods are fine when they don't change the outcome in practice.
- Avoid global state; expose a convenient global like top_k so it's easy to check.
- Keep comments minimal; add brief explanations where helpful.
- Sort results in a natural, human-friendly way; follow strict tie rules when applicable.

Output only a single self-contained Python script inside one Python code block, with all imports, ready to run.
"""
```

這個 baseline prompt，大概就是你請 ChatGPT 幫你寫 prompt，或請一位懂寫程式、但對你的情境沒那麼投入的朋友寫出來的東西。它刻意寫得比較短、比較親切，但藏著混雜的訊號，可能把模型推向不一致的解法。

首先，我們說優先用標準函式庫，卻馬上又允許「如果比較簡單」就用外部套件。這種軟性許可可能讓模型選到不可攜的依賴或較重的 import，改變效能，甚至讓不同環境下的執行成功率不同。

接著，我們鼓勵單趟串流來壓低記憶體，卻又說「如果比較清楚」可以重讀或快取。這種模糊給了多趟設計或記憶體快取的空間，違背原本的串流限制，並改變執行時間和記憶體表現。

我們也要求精確結果，卻允許「在實務上不影響結果時」使用近似方法。這是模型無法可靠驗證的判斷。它可能引入 sketch 或啟發式方法，讓 Top‑K 邊界附近的計數悄悄偏移，產生看起來對、卻通不過嚴格評測的結果。

我們建議避免 global state，卻又建議暴露一個方便的 global，例如 `top_k`。這混淆了介面契約：function 是要回傳資料，還是呼叫端要去讀 global？模型可能兩種都做，造成副作用，讓評測和重現變複雜。

文件規範同樣自相矛盾：「註解盡量少」卻又要「加簡短說明」。看模型怎麼解讀，可能得到說明不足的程式碼，或在邏輯中穿插文字，有時還會漏到規定的輸出格式之外。

最後，我們要求「自然、對人友善」的排序，同時又提到嚴格的 tie 規則。這兩者不一定一樣。模型可能選方便的排序（例如 `Counter.most_common`），偏離評測者標準的 `(-count, token)` 排序，尤其在 tie 時，造成微妙的正確性失誤。

**為什麼重要**：放軟的限制讓 prompt 看起來很容易滿足，卻產生岔路。模型每次執行可能走不同分支：stdlib 對外部依賴、單趟對重讀 / 快取、精確對近似，結果是正確率、latency 和記憶體都不穩定。

**我們的 evaluator 依然嚴格**：對小寫化的文字固定用 `[a-z0-9]+` 做 tokenization，並以 `(-count, token)` 做確定性排序。這裡只要有偏差，即使其他部分看起來合理，精確度也會被扣分。


### 看看表現：用 baseline prompt 產生 30 支腳本 

用 OpenAI Responses API，以 baseline prompt 呼叫模型 30 次，每次的回應存成 Python 檔，放到 `results_topk_baseline`。這可能要花一些時間。 


```python
from scripts.gen_baseline import generate_baseline_topk

MODEL = "gpt-5"
N_RUNS = 30
CONCURRENCY = 10
OUTPUT_DIR = "results_topk_baseline"

USER_PROMPT = """
Task:
Given globals text (str) and k (int), produce the Top-K most frequent tokens.

Tokenization:
- Case-insensitive tokenization using an ASCII regex; produce lowercase tokens. Whole-string lowercasing is not required.
- Tokens are ASCII [a-z0-9]+ sequences; treat all other characters as separators.

Output:
- Define top_k as a list of (token, count) tuples.
- Sort by count desc, then token asc.
- Length = min(k, number of unique tokens).

Notes:
- Run as-is with the provided globals; no file or network I/O.
"""

generate_baseline_topk(
    model=MODEL,
    n_runs=N_RUNS,
    concurrency=CONCURRENCY,
    output_dir=OUTPUT_DIR,
    dev_prompt=baseline_prompt,
    user_prompt=USER_PROMPT,
)
```

### 評測產生的腳本：Baseline Prompt

接著對 ``results_topk_baseline`` 裡的每支腳本做 benchmark。資料集較大時，這個評測刻意設計得很重，可能要幾分鐘。

```python
from scripts.topk_eval import evaluate_folder

evaluate_folder(
    folder_path="results_topk_baseline",
    k=500,
    scale_tokens=5_000_000,
    csv_path="run_results_topk_baseline.csv",
)
```

### 優化我們的 Prompt 

現在用 console 裡的 prompt optimization 工具改進 prompt，再看結果。先到 [OpenAI Optimize Playground](https://platform.openai.com/chat/edit?optimize=true)，把現有的 prompt 貼到 Developer Message 區。

然後按 **Optimize** 按鈕，會開啟優化面板。這時你可以提出想反映在 prompt 裡的特定修改，也可以直接按 **Optimize**，讓它依目標模型和任務的最佳實務來精修。我們先直接按。

![optimize_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/image_optimize_1.png)



完成後會看到優化的結果。下面的例子中，prompt 被改了很多地方。它也會給你改動的片段，以及為什麼這樣改。你可以展開註解，或用 inline reviewer 模式來操作。

我們再加一個想要的修改：

- 強制單趟串流

用 Prompt Optimizer 的迭代流程就能輕鬆做到。

![optimize_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/image_optimize_2.png)



對優化後的 prompt 滿意了，可以用優化器右上角的按鈕存成 [Prompt Object](#https://platform.openai.com/docs/guides/prompt-engineering#reusable-prompts)。我們可以在 API 呼叫裡使用這個物件，方便之後迭代、版本管理，以及在不同應用之間重複使用。  

![optimize_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/image_optimize_3.png)


###  看看表現：評測改進後的 prompt 

為了方便看，這裡直接寫出新的優化 prompt，你也可以改傳這兩個參數：``prompt_id`` and ``version``。先把優化後的 prompt 寫出來。 

````python
optimized_prompt = """
# Objective
Generate a single, self-contained Python script that exactly solves the specified task on a MacBook Pro (M4 Max).

# Hard requirements
- Use only Python stdlib. No approximate algorithms.
- Tokenization: ASCII [a-z0-9]+ on the original text; match case-insensitively and lowercase tokens individually. Do NOT call text.lower() on the full string.
- Exact Top‑K semantics: sort by count desc, then token asc. No reliance on Counter.most_common tie behavior.
- Define `top_k` as a list of (token, count) tuples with length = min(k, number of unique tokens).
- When globals `text` (str) and `k` (int) exist, do not reassign them; set `top_k` from those globals. If you include a `__main__` demo, guard it to run only when globals are absent.
- No file I/O, stdin, or network access, except optionally printing `top_k` as the last line.

# Performance & memory constraints
- Do NOT materialize the entire token stream or any large intermediate list.
- Do NOT sort all unique (token, count) items unless k >= 0.3 * number_of_unique_tokens.
- When k < number_of_unique_tokens, compute Top‑K using a bounded min‑heap of size k over counts.items(), maintaining the correct tie-break (count desc, then token asc).
- Target peak additional memory beyond the counts dict to O(k). Avoid creating `items = sorted(counts.items(), ...)` for large unique sets.

# Guidance
- Build counts via a generator over re.finditer with re.ASCII | re.IGNORECASE; lowercase each matched token before counting.
- Prefer heapq.nsmallest(k, cnt.items(), key=lambda kv: (-kv[1], kv[0])) for exact selection without full sort; avoid heapq.nlargest.
- Do NOT wrap tokens in custom comparator classes (e.g., reverse-lex __lt__) or rely on tuple tricks for heap ordering.
- Keep comments minimal; include a brief complexity note (time and space).

# Output format
- Output only one Python code block; no text outside the block.

# Examples 
```python
import re, heapq
from collections import Counter
from typing import List, Tuple, Iterable

_TOKEN = re.compile(r"[a-z0-9]+", flags=re.ASCII | re.IGNORECASE)

def _tokens(s: str) -> Iterable[str]:
    # Case-insensitive match; lowercase per token to avoid copying the whole string
    for m in _TOKEN.finditer(s):
        yield m.group(0).lower()

def top_k_tokens(text: str, k: int) -> List[Tuple[str, int]]:
    if k <= 0:
        return []
    cnt = Counter(_tokens(text))
    u = len(cnt)
    key = lambda kv: (-kv[1], kv[0])
    if k >= u:
        return sorted(cnt.items(), key=key)
    # Exact selection with bounded memory
    return heapq.nsmallest(k, cnt.items(), key=key)

# Compute from provided globals when available; demo only if missing and running as main
try:
    text; k  # type: ignore[name-defined]
except NameError:
    if __name__ == "__main__":
        demo_text = "A a b b b c1 C1 c1 -- d! d? e"
        demo_k = 3
        top_k = top_k_tokens(demo_text, demo_k)
        print(top_k)
else:
    top_k = top_k_tokens(text, k)  # type: ignore[name-defined]
# Complexity: counting O(N tokens), selection O(U log k) via heapq.nsmallest; extra space O(U + k)
```
"""
````

### 用優化後的 Prompt 產生 30 支腳本

```python
from scripts.gen_optimized import generate_optimized_topk

MODEL = "gpt-5"
N_RUNS = 30
CONCURRENCY = 10
OUTPUT_DIR = "results_topk_optimized"

USER_PROMPT = """
Task:
Given globals text (str) and k (int), produce the Top-K most frequent tokens.

Tokenization:
- Case-insensitive tokenization using an ASCII regex; produce lowercase tokens. Whole-string lowercasing is not required.
- Tokens are ASCII [a-z0-9]+ sequences; treat all other characters as separators.

Output:
- Define top_k as a list of (token, count) tuples.
- Sort by count desc, then token asc.
- Length = min(k, number of unique tokens).

Notes:
- Run as-is with the provided globals; no file or network I/O.
"""

generate_optimized_topk(
    model=MODEL,
    n_runs=N_RUNS,
    concurrency=CONCURRENCY,
    output_dir=OUTPUT_DIR,
    dev_prompt=optimized_prompt,
    user_prompt=USER_PROMPT,
)
```

### 評測產生的腳本：優化後的 Prompt

跑跟上面一樣的評測，這次用優化後的 prompt，看有沒有改善

```python
from scripts.topk_eval import evaluate_folder

evaluate_folder(
    folder_path="results_topk_optimized",
    k=500,
    scale_tokens=5_000_000,
    csv_path="run_results_topk_optimized.csv",
)
```

### 加入 LLM-as-a-Judge 評分 

除了量化評測，我們也能用更質性的指標衡量模型表現，例如程式碼品質和任務遵循度。我們為此寫了一份範例 prompt，叫 ``llm_as_judge.txt``。 

```python
from scripts.llm_judge import judge_folder
```

```python

# Run LLM-as-judge for baseline results
judge_folder(
    results_dir="results_topk_baseline",
    out_dir=None,  # auto-map to results_llm_as_judge_baseline
    model="gpt-5",
    system_prompt_path="llm_as_judge.txt",
    task_text=None,  # use default task description
    concurrency=6,
)
```

```python

# Run LLM-as-judge for optimized results
judge_folder(
    results_dir="results_topk_optimized",
    out_dir=None,  # auto-map to results_llm_as_judge_optimized
    model="gpt-5",
    system_prompt_path="llm_as_judge.txt",
    task_text=None,
    concurrency=6,
)
```

### 總結結果 

現在可以從量化的角度，加上 LLM as Judge 的質性結果，一起看成果。 

```python
from pathlib import Path
import importlib
import scripts.results_summarizer as rs
from IPython.display import Markdown, display

importlib.reload(rs)

fig = rs.render_charts(
    quant_baseline=Path("results_topk_baseline")/"run_results_topk_baseline.csv",
    quant_optimized=Path("results_topk_optimized")/"run_results_topk_optimized.csv",
    judge_baseline=Path("results_llm_as_judge_baseline")/"judgement_summary.csv",
    judge_optimized=Path("results_llm_as_judge_optimized")/"judgement_summary.csv",
    auto_display=True,
    close_after=True,
)
md = rs.build_markdown_summary(
    quant_baseline=Path("results_topk_baseline")/"run_results_topk_baseline.csv",
    quant_optimized=Path("results_topk_optimized")/"run_results_topk_optimized.csv",
    judge_baseline=Path("results_llm_as_judge_baseline")/"judgement_summary.csv",
    judge_optimized=Path("results_llm_as_judge_optimized")/"judgement_summary.csv",
)

display(Markdown(md))

print(md)
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    ### Prompt Optimization Results - Coding Tasks

    | Metric                      | Baseline | Optimized | Δ (Opt − Base) |
    |----------------------------|---------:|----------:|---------------:|
    | Avg Time (s)                |    7.906 |     6.977 |        -0.929 |
    | Peak Memory (KB)            |   3626.3 |     577.5 |       -3048.8 |
    | Exact (%)                   |    100.0 |     100.0 |           0.0 |
    | Sorted (%)                  |    100.0 |     100.0 |           0.0 |
    | LLM Adherence (1–5)         |     4.40 |      4.90 |         +0.50 |
    | Code Quality (1–5)          |     4.73 |      4.90 |         +0.16 |
    ```

雖然 GPT-5 本來就能產出正確的程式碼，prompt 優化還是收緊了限制、釐清了模糊之處，整體結果都有改善！




--------------------------------------------------------------------

### Context 與 Retrieval：模擬金融問答

大多數正式環境的用例，都面對不完美的 query 和雜訊 context。**FailSafeQA** 是很棒的 benchmark，它刻意擾動 **query**（拼字錯誤、不完整、領域外的說法）和 **context**（缺漏、OCR 損壞或不相關的文件），並回報 **Robustness**、**Context Grounding** 和 **Compliance**，也就是模型在有訊號時能不能回答，沒訊號時能不能拒答。

![FailSafeQA diagram](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/image_optimize_4.png)

**連結**
- Paper (arXiv): *Expect the Unexpected: FailSafe Long Context QA for Finance* — https://arxiv.org/abs/2502.06329  
- Dataset (Hugging Face): https://huggingface.co/datasets/Writer/FailSafeQA  
- Authors/Makers: Kiran Kamble, Melisa Russak, Dmytro Mozolevskyi, Muayad Ali, Mateusz Russak, Waseem AlShikh (Writer.ai) — see author list on the arXiv page above


我們用 helper script 跑 FailSafeQA 評測，並排比較 Baseline 與 Optimized prompt。

```python
# Define the Baseline FailSafeQA system prompt here for reuse
baseline_prompt_fsqa = (
    "You are a finance QA assistant. Answer ONLY using the provided context.\n"
    "If the context is missing or irrelevant, politely refuse and state that you need the relevant document."
)
```

再用一次 prompt optimizer，建出更適合這個用例的新 prompt。依據長 context 問答的最佳實務，我們知道要提醒回答用的模型依賴 context 段落的資訊，context 不足時拒絕回答。不帶任何參數按一次 Optimize，就得到合理的 prompt 結構，最後得到這個優化後的 prompt。


![optimize_image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/image_optimize_5.png)



```python
optimized_fsqa_prompt = """You are a finance document QA assistant.

Behavioral priorities (in order):
1) Grounding: Use ONLY the text inside [Context]. Do NOT use outside knowledge or assumptions.
2) Evidence check: Before answering, verify that the answer text (numbers, entities, dates, phrasing) is explicitly present or directly entailed by [Context]. If not, refuse (see Refusal policy).
3) Robustness to query noise: The user question may contain misspellings, missing words, or non-financial phrasing. Infer intent using the context and answer if the meaning is clear and supported by the context.
4) OCR noise handling: The context may include OCR artifacts (repeated characters, stray symbols, broken words). Ignore junk characters and reconstruct meaning when the underlying sentence is still recoverable. Do not guess beyond what the context supports.

Refusal policy:
- If [Context] is empty or lacks the information to answer, reply with a brief refusal and guidance. Do NOT attempt a general-knowledge answer.
- If the question is unrelated to the content of [Context] (out of scope), reply with a brief refusal and guidance. Do NOT speculate.
- If the question is incomplete but the correct answer is unambiguous from [Context], infer the intent and answer exactly; do NOT refuse.

Answer style:
- Default to the **shortest exact answer** needed to satisfy the question (e.g., the precise number/string/date as written). Preserve units, signs, casing, currency symbols, commas, and parentheses from the context. Do NOT round numbers unless asked.
- If the user explicitly asks to “write”, “draft”, or “generate” content, you may produce multi-sentence or formatted text—but still source every factual claim strictly from [Context].
- If the question is ambiguous, state the needed clarification in one short sentence, then provide the best supported answer if possible.

Output format:
- If answerable from the context:
  FINAL: <exact answer here>
  (optional) EVIDENCE: "<very short quoted span from the context that contains the answer>"
- If refusing:
  FINAL: Insufficient information in the provided context to answer this question. Please upload the relevant document or refine your question to include the necessary details."""
```

現在跑評測。為了示範，這裡只顯示單一比較的結果，你也可以跑完整評測。注意：這會花一些時間。

```python
import importlib
import run_FailSafeQA
import pandas as pd
import matplotlib.pyplot as plt
from openai import OpenAI

# Ensure latest function signature is used after code edits
importlib.reload(run_FailSafeQA)
run_failsafeqa = run_FailSafeQA.run_failsafeqa

# Set idx to an integer for a quick single-example comparison; set to None for full run
idx = 0  # e.g., 0 for a single datapoint

#Helper functions:
class OpenAIAnswer:
    def __init__(self):
        self.client = OpenAI()

    def __call__(self, system_prompt: str, user_prompt: str, model: str) -> str:
        resp = self.client.responses.create(
            model=model,
            input=[
                {"role": "developer", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
            text={"format": {"type": "text"}, "verbosity": "medium"},
            reasoning={"effort": "medium", "summary": "auto"},
            tools=[],
        )
        return resp.output_text
class OpenAIJudge:
    def __init__(self):
        self.client = OpenAI()

    def __call__(self, prompt: str, model: str) -> str:
        resp = self.client.responses.create(
            model=model,
            input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            text={"format": {"type": "text"}, "verbosity": "medium"},
            reasoning={"effort": "medium", "summary": "auto"},
            tools=[],
        )
        return resp.output_text

if idx is not None:
    # Single example mode (with detailed prompt/response logging)
    run_failsafeqa(
        out="results_failsafeqa_baseline.csv",
        system_prompt=baseline_prompt_fsqa,
        indices=[idx],
        log_prompts=True,
        log_chars=800,
        log_file="failsafeqa_debug.log",
    )
    run_failsafeqa(
        out="results_failsafeqa_optimized.csv",
        system_prompt=optimized_fsqa_prompt,
        indices=[idx],
        log_prompts=True,
        log_chars=800,
        log_file="failsafeqa_debug.log",
    )

    base_df = pd.read_csv("results_failsafeqa_baseline.csv")
    opt_df = pd.read_csv("results_failsafeqa_optimized.csv")

    b_one = base_df[base_df["idx"] == idx]
    o_one = opt_df[opt_df["idx"] == idx]

    comparison_df = pd.concat([b_one, o_one], ignore_index=True)

    # Keep only relevant columns
    comparison_df = comparison_df[["run", "kind", "rating", "compliance"]]

    # Display as table
    display(comparison_df)

else:
    # Full run mode
    run_failsafeqa(out="results_failsafeqa_baseline.csv", system_prompt=baseline_prompt_fsqa)
    run_failsafeqa(out="results_failsafeqa_optimized.csv", system_prompt=optimized_fsqa_prompt)

    base_df = pd.read_csv("results_failsafeqa_baseline.csv")
    opt_df = pd.read_csv("results_failsafeqa_optimized.csv")

    def per_kind_summary(df: pd.DataFrame) -> pd.DataFrame:
        out = df.groupby("kind").agg(
            mean_rating=("rating", lambda x: pd.to_numeric(x, errors="coerce").mean()),
            compliance_rate=("compliance", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).mean()),
            count=("rating", "count"),
        )
        return out.round(3)

    base_summary = per_kind_summary(base_df)
    opt_summary = per_kind_summary(opt_df)

    summary = base_summary.join(opt_summary, lsuffix="_base", rsuffix="_opt").fillna("NA")

    print("Per-kind comparison (baseline vs optimized):")
    display(summary)

    # Plot compliance rate comparison per kind
    kinds = summary.index.tolist()
    x = range(len(kinds))
    base_vals = summary["compliance_rate_base"].astype(float).tolist()
    opt_vals = summary["compliance_rate_opt"].astype(float).tolist()

    fig, ax = plt.subplots(figsize=(10, 4))
    width = 0.35
    ax.bar([i - width/2 for i in x], base_vals, width=width, label="Baseline", color="#cbd5e1")
    ax.bar([i + width/2 for i in x], opt_vals, width=width, label="Optimized", color="#60a5fa")
    ax.set_xticks(list(x))
    ax.set_xticklabels(kinds, rotation=45, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Compliance rate")
    ax.set_title("FailSafeQA — Per-kind Compliance (Baseline vs Optimized)")
    ax.legend()
    plt.tight_layout()
    plt.show()

    # Overall metrics
    def overall(df: pd.DataFrame):
        return {
            "mean_rating": float(pd.to_numeric(df["rating"], errors="coerce").mean()),
            "mean_compliance": float(pd.to_numeric(df["compliance"], errors="coerce").fillna(0).mean()),
        }

    print("Overall — Baseline:", overall(base_df))
    print("Overall — Optimized:", overall(opt_df))
```

```python
from IPython.display import Markdown, display

def build_markdown_summary_from_metrics(
    robust_base: float, ground_base: float,
    robust_opt: float, ground_opt: float,
    threshold: int = 6,
    src_base: str = "results_failsafeqa.csv",
    src_opt: str = "results_failsafeqa.csv",
) -> str:
    d_r = robust_opt - robust_base
    d_g = ground_opt - ground_base

    # Data rows
    rows = [
        ["Metric", "Baseline", "Optimized", "Δ (Opt − Base)"],
        ["Robustness (avg across datapoints)", f"{robust_base:.3f}", f"{robust_opt:.3f}", f"{d_r:+.3f}"],
        ["Context Grounding (avg across datapoints)", f"{ground_base:.3f}", f"{ground_opt:.3f}", f"{d_g:+.3f}"],
    ]

    # Calculate column widths for alignment
    col_widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]

    # Build table lines with padding
    lines = []
    for i, row in enumerate(rows):
        padded = [str(cell).ljust(col_widths[j]) for j, cell in enumerate(row)]
        lines.append("| " + " | ".join(padded) + " |")
        if i == 0:  # after header
            sep = ["-" * col_widths[j] for j in range(len(row))]
            lines.append("| " + " | ".join(sep) + " |")

    table = "\n".join(lines)

    return f"""
## FailSafeQA — Summary

**Compliance threshold:** ≥ {threshold}

{table}

_Source files:_ `{src_base}` · `{src_opt}`
""".strip()

# Usage
md = build_markdown_summary_from_metrics(
    robust_base=0.320, ground_base=0.800,
    robust_opt=0.540, ground_opt=0.950,
    threshold=6,
    src_base="results_failsafeqa.csv",
    src_opt="results_failsafeqa.csv",
)

# Notebook pretty
display(Markdown(md))

print(md)
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    ## FailSafeQA — Summary

    **Compliance threshold:** ≥ 6

    | Metric                                    | Baseline | Optimized | Δ (Opt − Base) |
    | ----------------------------------------- | -------- | --------- | -------------- |
    | Robustness (avg across datapoints)        | 0.320    | 0.540     | +0.220         |
    | Context Grounding (avg across datapoints) | 0.800    | 0.950     | +0.150         |

    _Source files:_ `results_failsafeqa.csv` · `results_failsafeqa.csv`
    ```
GPT-5-mini 在這個任務上表現很強，所以連 baseline prompt 也幾乎都拿到 4 分以上。但如果比較 judge 給滿分（6/6）的比例，在 FailSafeQA 答案品質的兩個類別（robustness 和 context grounding）上，優化後的 prompt 有明顯更多的滿分答案。

### 結論

很期待大家在 OpenAI Playground 試用 **GPT-5 的 Prompt Optimization**。GPT-5 帶來最先進的智慧，而好的 prompt 能讓它推理更可靠、更守限制，產出更乾淨、更高品質的結果。


今天就拿你的任務試試 [Prompt Optimizer](https://platform.openai.com/chat/edit?optimize=true) 吧！

## 重點整理

- Prompt 裡的矛盾與模糊指示（stdlib 或外部套件、單趟或重讀、精確或近似）會讓模型走不同分支，造成結果不穩。
- Prompt Optimizer 會依目標模型和任務套用最佳實務，也能用額外要求（例如強制單趟串流）迭代。
- 優化後的 prompt 可存成 Prompt Object，方便版本管理和跨應用重用。
- 評測要同時看量化指標（成功率、時間、記憶體、精確度）和 LLM-as-a-judge 的質性分數。
- 即使模型本來就答得出來，優化 prompt 仍能提高完美答案的比例。

## 練習

1. 把 baseline prompt 裡的某一組矛盾（例如「優先用標準函式庫」加「可用外部套件」）改成單一明確指示，只重跑少量次數（例如 5 次），看結果有沒有變。
2. 把產生腳本的次數從 30 改成 10，比較 baseline 與 optimized 的成功率與平均執行時間，想想樣本變少對結論的影響。
3. 改寫 `llm_as_judge.txt` 加一項評分標準（例如「是否嚴格單趟串流」），重跑 judge，看兩個 prompt 的分數差距有沒有變大。
