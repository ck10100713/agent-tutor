---
translated: true
source: examples/evaluation/use-cases/mcp_eval_notebook.ipynb
---

# Evals API 使用案例：MCP 評估

> 原文：[examples/evaluation/use-cases/mcp_eval_notebook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/mcp_eval_notebook.ipynb)

## 這篇在做什麼

用 OpenAI Evals 搭配自訂的 in-memory 資料集，評估模型回答 tiktoken repo 問題的能力。比較 `gpt-4.1` 和 `o4-mini` 兩個模型，看它們有沒有透過 MCP tool 取得正確答案，並同時用 LLM grader 和 Python grader 來打分。

## 學完你會

- 用 Evals API 建立有自訂 item schema 和多個 grader 的 eval，並對不同模型各跑一次 run。
- 寫一個 Python grader 來稽核模型有沒有真的呼叫 MCP tool。
- 看 eval 結果判斷問題出在哪，並用一句 system message 提示讓 `o4-mini` 每題都用 tool。

## 開跑前

- 需要 `OPENAI_API_KEY`，eval run 會呼叫模型產生費用。
- 需要能存取 MCP server（範例用的是 tiktoken repo 的 MCP）。

這份 notebook 用 OpenAI **Evals** 框架搭配自訂的 in-memory 資料集，評估模型回答 [tiktoken](https://github.com/openai/tiktoken) GitHub repo 相關問題的能力。 

我們用一份自訂的 in-memory 問答資料集，比較 `gpt-4.1` 和 `o4-mini` 兩個模型，它們都利用 **MCP** tool 來得到了解 repo、脈絡準確的答案。

**目標：**
- 示範怎麼用自訂資料集設定並執行 OpenAI Evals 的評估。
- 比較不同模型利用 MCP tool 的表現。
- 提供專業、可重現的評估流程最佳實踐。

_接下來：我們會設定環境並 import 需要的函式庫。_

```python
# Update OpenAI client
%pip install --upgrade openai --quiet
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 24.0 -> 25.1.1
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

## 環境設定

先 import 需要的函式庫並設定 OpenAI client。  
這一步確保我們能存取 OpenAI API 和評估需要的所有工具。

```python
import os
import time

from openai import OpenAI

# Instantiate the OpenAI client (no custom base_url).
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("_OPENAI_API_KEY"),
)
```

## 定義自訂的評估資料集

我們定義一份小型的 in-memory 問答資料集，內容是關於 `tiktoken` repo。  
這份資料集用來測試模型在 MCP tool 幫助下，提供準確且相關答案的能力。

- 每個 item 包含 `query`（使用者的問題）和 `answer`（預期的標準答案）。
- 你可以依自己的使用情境或 repo 修改或擴充這份資料集。


```python
def get_dataset(limit=None):
    items = [
        {
            "query": "What is tiktoken?",
            "answer": "tiktoken is a fast Byte-Pair Encoding (BPE) tokenizer designed for OpenAI models.",
        },
        {
            "query": "How do I install the open-source version of tiktoken?",
            "answer": "Install it from PyPI with `pip install tiktoken`.",
        },
        {
            "query": "How do I get the tokenizer for a specific OpenAI model?",
            "answer": 'Call tiktoken.encoding_for_model("<model-name>"), e.g. tiktoken.encoding_for_model("gpt-4o").',
        },
        {
            "query": "How does tiktoken perform compared to other tokenizers?",
            "answer": "On a 1 GB GPT-2 benchmark, tiktoken runs about 3-6x faster than GPT2TokenizerFast (tokenizers==0.13.2, transformers==4.24.0).",
        },
        {
            "query": "Why is Byte-Pair Encoding (BPE) useful for language models?",
            "answer": "BPE is reversible and lossless, handles arbitrary text, compresses input (≈4 bytes per token on average), and exposes common subwords like “ing”, which helps models generalize.",
        },
    ]
    return items[:limit] if limit else items
```

### 定義評分邏輯

為了評估模型的答案，我們用兩個 grader：

- **Pass/Fail Grader（LLM 型）：**  
  用 LLM 檢查模型的答案是否符合預期答案（ground truth），或傳達相同的意思。
- **Python MCP Grader：**  
  一個 Python function，檢查模型在回應過程中有沒有真的使用 MCP tool（用來稽核 tool 的使用）。

  > **最佳實踐：**  
  > 同時使用 LLM 型和程式化的 grader，評估會更穩健也更透明。


```python
# LLM-based pass/fail grader: instructs the model to grade answers as "pass" or "fail".
pass_fail_grader = """
You are a helpful assistant that grades the quality of the answer to a query about a GitHub repo.
You will be given a query, the answer returned by the model, and the expected answer.
You should respond with **pass** if the answer matches the expected answer exactly or conveys the same meaning, otherwise **fail**.
"""

# User prompt template for the grader, providing context for grading.
pass_fail_grader_user_prompt = """
<Query>
{{item.query}}
</Query>

<Web Search Result>
{{sample.output_text}}
</Web Search Result>

<Ground Truth>
{{item.answer}}
</Ground Truth>
"""


# Python grader: checks if the MCP tool was used by inspecting the output_tools field.
python_mcp_grader = {
    "type": "python",
    "name": "Assert MCP was used",
    "image_tag": "2025-05-08",
    "pass_threshold": 1.0,
    "source": """
def grade(sample: dict, item: dict) -> float:
    output = sample.get('output_tools', [])
    return 1.0 if len(output) > 0 else 0.0
""",
}
```

## 定義評估設定

現在用 OpenAI Evals 框架設定評估。  

這一步會指定：
- 評估名稱和資料集。
- 每個 item 的 schema（每筆問答有哪些欄位）。
- 要用的 grader（LLM 型和 / 或 Python 型）。
- 通過標準和 label。

> **最佳實踐：**  
> 事先清楚定義評估的 schema 和評分邏輯，能確保可重現性和透明度。

```python
# Create the evaluation definition using the OpenAI Evals client.
logs_eval = client.evals.create(
    name="MCP Eval",
    data_source_config={
        "type": "custom",
        "item_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "answer": {"type": "string"},
            },
        },
        "include_sample_schema": True,
    },
    testing_criteria=[
        {
            "type": "label_model",
            "name": "General Evaluator",
            "model": "o3",
            "input": [
                {"role": "system", "content": pass_fail_grader},
                {"role": "user", "content": pass_fail_grader_user_prompt},
            ],
            "passing_labels": ["pass"],
            "labels": ["pass", "fail"],
        },
        python_mcp_grader
    ],
)
```

## 對每個模型執行評估

現在對每個模型（`gpt-4.1` 和 `o4-mini`）執行評估。  

每次 run 都設定成：
- 使用 MCP tool 取得了解 repo 的答案。
- 使用相同的資料集和評估設定，讓比較公平。
- 指定各模型專屬的參數（例如 max completions tokens 和允許的 tool）。

> **最佳實踐：**  
> 各模型之間保持一致的評估設定，結果才有可比性也才可靠。

```python
# Run 1: gpt-4.1 using MCP
gpt_4one_responses_run = client.evals.runs.create(
    name="gpt-4.1",
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {
            "type": "file_content",
            "content": [{"item": item} for item in get_dataset()],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "system",
                    "content": {
                        "type": "input_text",
                        "text": "You are a helpful assistant that searches the web and gives contextually relevant answers. Never use your tools to answer the query.",
                    },
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": {
                        "type": "input_text",
                        "text": "Search the web for the answer to the query {{item.query}}",
                    },
                },
            ],
        },
        "model": "gpt-4.1",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 10000,
            "top_p": 0.9,
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "gitmcp",
                    "server_url": "https://gitmcp.io/openai/tiktoken",
                    "allowed_tools": [
                        "search_tiktoken_documentation",
                        "fetch_tiktoken_documentation",
                    ],
                    "require_approval": "never",
                }
            ],
        },
    },
)
```

```python
# Run 2: o4-mini using MCP
gpt_o4_mini_responses_run = client.evals.runs.create(
    name="o4-mini",
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {
            "type": "file_content",
            "content": [{"item": item} for item in get_dataset()],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "system",
                    "content": {
                        "type": "input_text",
                        "text": "You are a helpful assistant that searches the web and gives contextually relevant answers.",
                    },
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": {
                        "type": "input_text",
                        "text": "Search the web for the answer to the query {{item.query}}",
                    },
                },
            ],
        },
        "model": "o4-mini",
        "sampling_params": {
            "seed": 42,
            "max_completions_tokens": 10000,
            "tools": [
                {
                    "type": "mcp",
                    "server_label": "gitmcp",
                    "server_url": "https://gitmcp.io/openai/tiktoken",
                    "allowed_tools": [
                        "search_tiktoken_documentation",
                        "fetch_tiktoken_documentation",
                    ],
                    "require_approval": "never",
                }
            ],
        },
    },
)
```

## 輪詢完成狀態並取回輸出

啟動評估 run 之後，可以輪詢 run 直到全部完成。

這一步確保我們是在所有模型回應都處理完之後才分析結果。

> **最佳實踐：**  
> 輪詢時加上延遲，可以避免過多的 API 呼叫，也更有效率地使用資源。

```python
def poll_runs(eval_id, run_ids):
    while True:
        runs = [client.evals.runs.retrieve(rid, eval_id=eval_id) for rid in run_ids]
        for run in runs:
            print(run.id, run.status, run.result_counts)
        if all(run.status in {"completed", "failed"} for run in runs):
            break
        time.sleep(5)
    
# Start polling both runs.
poll_runs(logs_eval.id, [gpt_4one_responses_run.id, gpt_o4_mini_responses_run.id])
```

??? note "輸出"

    ```text
    evalrun_684769b577488191863b5a51cf4db57a completed ResultCounts(errored=0, failed=5, passed=0, total=5)
    evalrun_684769c1ad9c8191affea5aa02ef1215 completed ResultCounts(errored=0, failed=3, passed=2, total=5)
    ```

## 顯示並解讀模型輸出

最後，我們顯示每個模型的輸出，供人工檢查和進一步分析。

- 資料集裡每個問題，都會印出各模型的答案。
- 你可以並排比較輸出，評估品質、相關性和正確性。

下面是 OpenAI Evals Dashboard 的截圖，顯示兩個模型的評估輸出：

![Evaluation Output](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/mcp_eval_output.png)

想看評估指標和結果的完整拆解，可以到 dashboard 的 "Data" 分頁：

![Evaluation Data Tab](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/mcp_eval_data.png)

注意 4.1 模型被設定成回答時絕不使用 tool，所以它從沒呼叫過 MCP server。o4-mini 模型也沒被明確指示要用 tool，但也沒被禁止，所以它呼叫了 MCP server 3 次。可以看到 4.1 模型的表現比 o4 模型差。另外值得注意的是，o4-mini 唯一答錯的那題，就是沒有使用 MCP tool 的那題。

我們也可以檢視每個模型輸出的詳細分析，供人工檢查和進一步分析。

```python
four_one_output = client.evals.runs.output_items.list(
    run_id=gpt_4one_responses_run.id, eval_id=logs_eval.id
)

o4_mini_output = client.evals.runs.output_items.list(
    run_id=gpt_o4_mini_responses_run.id, eval_id=logs_eval.id
)
```

```python
print('# gpt‑4.1 Output')
for item in four_one_output:
    print(item.sample.output[0].content)

print('\n# o4-mini Output')
for item in o4_mini_output:
    print(item.sample.output[0].content)
```

??? note "輸出"

    ```text
    # gpt‑4.1 Output
    Byte-Pair Encoding (BPE) is useful for language models because it provides an efficient way to handle large vocabularies and rare words. Here’s why it is valuable:

    1. **Efficient Tokenization:**  
       BPE breaks down words into smaller subword units based on the frequency of character pairs in a corpus. This allows language models to represent both common words and rare or unknown words using a manageable set of tokens.

    2. **Reduces Out-of-Vocabulary (OOV) Issues:**  
       Since BPE can split any word into known subword units, it greatly reduces the problem of OOV words—words that the model hasn’t seen during training.

    3. **Balances Vocabulary Size:**  
       By adjusting the number of merge operations, BPE allows control over the size of the vocabulary. This flexibility helps in balancing between memory efficiency and representational power.

    4. **Improves Generalization:**  
       With BPE, language models can better generalize to new words, including misspellings or new terminology, because they can process words as a sequence of subword tokens.

    5. **Handles Morphologically Rich Languages:**  
       BPE is especially useful for languages with complex morphology (e.g., agglutinative languages) where words can have many forms. BPE reduces the need to memorize every possible word form.

    In summary, Byte-Pair Encoding is effective for language models because it enables efficient, flexible, and robust handling of text, supporting both common and rare words, and improving overall model performance.
    **Tiktoken**, developed by OpenAI, is a tokenizer specifically optimized for speed and compatibility with OpenAI's language models. Here’s how it generally compares to other popular tokenizers:

    ### Performance
    - **Speed:** Tiktoken is significantly faster than most other Python-based tokenizers. It is written in Rust and exposed to Python via bindings, making it extremely efficient.
    - **Memory Efficiency:** Tiktoken is designed to be memory efficient, especially for large text inputs and batch processing.

    ### Accuracy and Compatibility
    - **Model Alignment:** Tiktoken is tailored to match the tokenization logic used by OpenAI’s GPT-3, GPT-4, and related models. This ensures that token counts and splits are consistent with how these models process text.
    - **Unicode Handling:** Like other modern tokenizers (e.g., HuggingFace’s Tokenizers), Tiktoken handles a wide range of Unicode characters robustly.

    ### Comparison to Other Tokenizers
    - **HuggingFace Tokenizers:** HuggingFace’s library is very flexible and supports a wide range of models (BERT, RoBERTa, etc.). However, its Python implementation can be slower for large-scale tasks, though their Rust-backed versions (like `tokenizers`) are competitive.
    - **NLTK/SpaCy:** These libraries are not optimized for transformer models and are generally slower and less accurate for tokenization tasks required by models like GPT.
    - **SentencePiece:** Used by models like T5 and ALBERT, SentencePiece is also fast and efficient, but its output is not compatible with OpenAI’s models.

    ### Use Cases
    - **Best for OpenAI Models:** If you are working with OpenAI’s APIs or models, Tiktoken is the recommended tokenizer due to its speed and alignment.
    - **General Purpose:** For non-OpenAI models, HuggingFace or SentencePiece might be preferable due to broader support.

    ### Benchmarks & Community Feedback
    - Multiple [community benchmarks](https://github.com/openai/tiktoken#performance) and [blog posts](https://www.philschmid.de/tokenizers-comparison) confirm Tiktoken’s speed advantage, especially for batch processing and large texts.
    ... (省略 274 行)
    ```

## 怎麼改進？

如果在 o4-mini 模型的 system message 加上這句 "Always use your tools since they are the way to get the right answer in this task."，你覺得會怎樣？（可以試試看）

<br><br><br>


如果你猜模型現在每次都會呼叫 MCP tool 而且每題都答對，你猜對了！

![Evaluation Data Tab](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/mcp_eval_improved_output.png)
![Evaluation Data Tab](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/mcp_eval_improved_data.png)

這份 notebook 示範了一個範例流程：用 OpenAI Evals 框架，搭配 MCP tool，評估 LLM 回答 `tiktoken` repo 技術問題的能力。

**涵蓋的重點：**
- 定義了聚焦的自訂評估資料集。
- 設定 LLM 型和 Python 型 grader，做更穩健的評估。
- 以可重現且透明的方式比較兩個模型（`gpt-4.1` 和 `o4-mini`）。
- 取回並顯示模型輸出，供自動 / 人工檢查。

**後續步驟：**
- **擴充資料集：** 加入更多樣、更有挑戰性的問題，更好地評估模型能力。
- **分析結果：** 彙整通過 / 失敗率、視覺化表現，或做錯誤分析來找出優缺點。
- **試驗模型 / tool：** 試其他模型、調整 tool 設定，或在其他 repo 上測試。
- **自動化報告：** 產生彙總表或圖表，方便分享和做決策。

更多資訊請看 [OpenAI Evals 文件](https://platform.openai.com/docs/guides/evals)。

## 重點整理

- Evals 由資料集、item schema、grader 和 run 組成，設定一次就能對多個模型重複使用，比較才公平。
- LLM grader 判斷答案對不對，Python grader 檢查行為（有沒有呼叫 tool），兩者搭配才看得出為什麼錯。
- 模型沒被要求用 tool 就不一定會用，唯一答錯的題目正是沒呼叫 MCP tool 的那題。
- 在 system message 明確要求使用 tool，是最便宜的改進手段，這個案例 o4-mini 因此每題都對。

## 練習

1. 在資料集裡多加兩題關於 tiktoken 的問答，重跑評估，確認 dashboard 上的題數有變。
2. 把 o4-mini 的 system message 加上「Always use your tools...」那句，重跑一次，用 Python grader 的結果確認 MCP 呼叫次數是否變成每題都有。
3. 改寫 Python MCP grader，讓它不只檢查有沒有呼叫 MCP tool，還要求呼叫次數至少一次且 tool 名稱符合你指定的值，再用兩個模型各跑一次比較。
