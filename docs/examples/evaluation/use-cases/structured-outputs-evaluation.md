---
translated: true
source: examples/evaluation/use-cases/structured-outputs-evaluation.ipynb
---

# Evals API 使用案例：Structured Outputs 評估

> 原文：[examples/evaluation/use-cases/structured-outputs-evaluation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/structured-outputs-evaluation.ipynb)

## 這篇在做什麼

用 OpenAI Evals API 評估模型產生 structured output（JSON）的能力。主要範例是讓模型從 OpenAI SDK 的 Python 檔案抽出函式、類別和常數，再由 rubric 模型打分，最後也示範多語言情緒抽取。

## 學完你會

- 用 `client.evals.create(...)` 建立 eval，搭配自訂的 in-memory 資料集和評分 rubric。
- 對同一個 eval 分別用 Completions 和 Responses endpoint 發起 run，輪詢等它們跑完並存下結果。
- 把 run 的輸出項目撈出來並排比較，找出失敗案例。

## 開跑前

- 需要 `OPENAI_API_KEY`，並安裝 `openai` 等套件。
- 大量跑 eval 的話，可以另外準備有適當額度限制的 organization 層級 key。

這份 notebook 帶你跑幾個聚焦、可直接執行的範例，說明怎麼用 OpenAI **Evals** framework 來**測試、評分並迭代那些要求大型語言模型產生 structured output 的任務**。

> **這為什麼重要？**
> 正式環境的系統常常依賴 JSON、SQL 或特定領域的格式。靠抽查或臨時調整 prompt，很快就撐不住。更好的做法是把期望寫成自動化 eval，讓團隊用安全磚塊而不是沙子來出貨。



## 快速導覽

* **Section 1：前置條件**：環境變數和套件安裝
* **Section 2：實作演練，程式碼符號抽取**：端到端範例，評分模型從原始碼抽出函式和類別名稱的能力。我們保留原本的邏輯，只在外面加上說明。
* **Section 3：其他範例**：常見正式環境模式的草圖，例如情緒抽取，當作額外的評估程式碼範例。
* **Section 4：結果探索**：輕量的 helper，用來撈出 run 輸出並深入檢視失敗案例。



## 前置條件

1. **安裝套件**（以下為最低版本）：

```bash
pip install --upgrade openai
```

2. **認證**，匯出你的 key：

```bash
export OPENAI_API_KEY="sk‑..."
```

3. **選用**：如果打算大量跑 eval，請設定一把有適當額度限制的 [organization 層級 key](https://platform.openai.com/account/org-settings)。


### 使用案例 1：程式碼符號抽取


目標是**從 OpenAI SDK 內的 python 檔案抽出所有函式、類別和常數符號**。
對每個檔案，我們要求模型輸出像這樣的 structured JSON：

```json
{
  "symbols": [
    {"name": "OpenAI", "kind": "class"},
    {"name": "Evals", "kind": "module"},
    ...
  ]
}
```

之後由一個 rubric 模型以 1 到 7 分評分，看**完整性**（有沒有抓到每個符號？）和**品質**（種類 kind 是否正確？）。


### 用自訂資料集評估程式碼抽取品質

我們來走一個例子，用 OpenAI **Evals** framework 搭配自訂的 in-memory 資料集，評估模型從程式碼抽取符號的能力。

### 初始化 SDK client
用我們前面匯出的 `OPENAI_API_KEY` 建立 `openai.OpenAI` client。沒有它什麼都跑不起來。

```python
%pip install --upgrade openai pandas rich --quiet



import os
import time
import openai
from rich import print
import pandas as pd

client = openai.OpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("_OPENAI_API_KEY"),
)
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 24.0 -> 25.1.1
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

### 資料集工廠與評分 rubric
* `get_dataset` 讀取幾個 SDK 檔案，建出一個小型的 in-memory 資料集。
* `structured_output_grader` 定義詳細的評估 rubric。
* `client.evals.create(...)` 把 eval 註冊到平台上。

```python
def get_dataset(limit=None):
    openai_sdk_file_path = os.path.dirname(openai.__file__)

    file_paths = [
        os.path.join(openai_sdk_file_path, "resources", "evals", "evals.py"),
        os.path.join(openai_sdk_file_path, "resources", "responses", "responses.py"),
        os.path.join(openai_sdk_file_path, "resources", "images.py"),
        os.path.join(openai_sdk_file_path, "resources", "embeddings.py"),
        os.path.join(openai_sdk_file_path, "resources", "files.py"),
    ]

    items = []
    for file_path in file_paths:
        items.append({"input": open(file_path, "r").read()})
    if limit:
        return items[:limit]
    return items


structured_output_grader = """
You are a helpful assistant that grades the quality of extracted information from a code file.
You will be given a code file and a list of extracted information.
You should grade the quality of the extracted information.

You should grade the quality on a scale of 1 to 7.
You should apply the following criteria, and calculate your score as follows:
You should first check for completeness on a scale of 1 to 7.
Then you should apply a quality modifier.

The quality modifier is a multiplier from 0 to 1 that you multiply by the completeness score.
If there is 100% coverage for completion and it is all high quality, then you would return 7*1.
If there is 100% coverage for completion but it is all low quality, then you would return 7*0.5.
etc.
"""

structured_output_grader_user_prompt = """
<Code File>
{{item.input}}
</Code File>

<Extracted Information>
{{sample.output_json.symbols}}
</Extracted Information>
"""

logs_eval = client.evals.create(
    name="Code QA Eval",
    data_source_config={
        "type": "custom",
        "item_schema": {
            "type": "object",
            "properties": {"input": {"type": "string"}},
        },
        "include_sample_schema": True,
    },
    testing_criteria=[
        {
            "type": "score_model",
            "name": "General Evaluator",
            "model": "o3",
            "input": [
                {"role": "system", "content": structured_output_grader},
                {"role": "user", "content": structured_output_grader_user_prompt},
            ],
            "range": [1, 7],
            "pass_threshold": 5.5,
        }
    ],
)
```

### 啟動模型 run
這裡對同一個 eval 啟動兩個 run：一個呼叫 **Completions** endpoint，一個呼叫 **Responses** endpoint。

```python
### Kick off model runs
gpt_4one_completions_run = client.evals.runs.create(
    name="gpt-4.1",
    eval_id=logs_eval.id,
    data_source={
        "type": "completions",
        "source": {
            "type": "file_content",
            "content": [{"item": item} for item in get_dataset(limit=1)],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "system",
                    "content": {"type": "input_text", "text": "You are a helpful assistant."},
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": {
                        "type": "input_text",
                        "text": "Extract the symbols from the code file {{item.input}}",
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
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "python_symbols",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "symbols": {
                                "type": "array",
                                "description": "A list of symbols extracted from Python code.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "The name of the symbol."},
                                        "symbol_type": {
                                            "type": "string", "description": "The type of the symbol, e.g., variable, function, class.",
                                        },
                                    },
                                    "required": ["name", "symbol_type"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["symbols"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        },
    },
)

gpt_4one_responses_run = client.evals.runs.create(
    name="gpt-4.1-mini",
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {
            "type": "file_content",
            "content": [{"item": item} for item in get_dataset(limit=1)],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "system",
                    "content": {"type": "input_text", "text": "You are a helpful assistant."},
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": {
                        "type": "input_text",
                        "text": "Extract the symbols from the code file {{item.input}}",
                    },
                },
            ],
        },
        "model": "gpt-4.1-mini",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 10000,
            "top_p": 0.9,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "python_symbols",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "symbols": {
                                "type": "array",
                                "description": "A list of symbols extracted from Python code.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string", "description": "The name of the symbol."},
                                        "symbol_type": {
                                            "type": "string",
                                            "description": "The type of the symbol, e.g., variable, function, class.",
                                        },
                                    },
                                    "required": ["name", "symbol_type"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["symbols"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            },
        },
    },
)
```

### 輪詢工具
接著用一個簡單的迴圈等所有 run 跑完，再把每個 run 的 JSON 存到磁碟，之後可以檢視，或附加到 CI artifact。

```python
### Utility poller
def poll_runs(eval_id, run_ids):
    while True:
        runs = [client.evals.runs.retrieve(rid, eval_id=eval_id) for rid in run_ids]
        for run in runs:
            print(run.id, run.status, run.result_counts)
        if all(run.status in {"completed", "failed"} for run in runs):
            # dump results to file
            for run in runs:
                with open(f"{run.id}.json", "w") as f:
                    f.write(
                        client.evals.runs.output_items.list(
                            run_id=run.id, eval_id=eval_id
                        ).model_dump_json(indent=4)
                    )
            break
        time.sleep(5)

poll_runs(logs_eval.id, [gpt_4one_completions_run.id, gpt_4one_responses_run.id])
```

??? note "輸出"

    ```text
    evalrun_68487dcc749081918ec2571e76cc9ef6 completed
    ResultCounts(errored=0, failed=1, passed=0, total=1)
    ```

    ```text
    evalrun_68487dcdaba0819182db010fe5331f2e completed
    ResultCounts(errored=0, failed=1, passed=0, total=1)
    ```

### 載入輸出以便快速檢視
我們會撈出兩個 run 的輸出項目，方便印出或後處理。

```python
completions_output = client.evals.runs.output_items.list(
    run_id=gpt_4one_completions_run.id, eval_id=logs_eval.id
)

responses_output = client.evals.runs.output_items.list(
    run_id=gpt_4one_responses_run.id, eval_id=logs_eval.id
)
```

### 人類可讀的輸出
來印出 completions 和 responses 的並排對照。

```python
from IPython.display import display, HTML

# Collect outputs for both runs
completions_outputs = [item.sample.output[0].content for item in completions_output]
responses_outputs = [item.sample.output[0].content for item in responses_output]

# Create DataFrame for side-by-side display (truncated to 250 chars for readability)
df = pd.DataFrame({
    "Completions Output": [c[:250].replace('\n', ' ') + ('...' if len(c) > 250 else '') for c in completions_outputs],
    "Responses Output": [r[:250].replace('\n', ' ') + ('...' if len(r) > 250 else '') for r in responses_outputs]
})

# Custom color scheme
custom_styles = [
    {'selector': 'th', 'props': [('font-size', '1.1em'), ('background-color', '#323C50'), ('color', '#FFFFFF'), ('border-bottom', '2px solid #1CA7EC')]},
    {'selector': 'td', 'props': [('font-size', '1em'), ('max-width', '650px'), ('background-color', '#F6F8FA'), ('color', '#222'), ('border-bottom', '1px solid #DDD')]},
    {'selector': 'tr:hover td', 'props': [('background-color', '#D1ECF1'), ('color', '#18647E')]},
    {'selector': 'tbody tr:nth-child(even) td', 'props': [('background-color', '#E8F1FB')]},
    {'selector': 'tbody tr:nth-child(odd) td', 'props': [('background-color', '#F6F8FA')]},
    {'selector': 'table', 'props': [('border-collapse', 'collapse'), ('border-radius', '6px'), ('overflow', 'hidden')]},
]

styled = (
    df.style
    .set_properties(**{'white-space': 'pre-wrap', 'word-break': 'break-word', 'padding': '8px'})
    .set_table_styles(custom_styles)
    .hide(axis="index")
)

display(HTML("""
<h4 style="color: #1CA7EC; font-weight: 600; letter-spacing: 1px; text-shadow: 0 1px 2px rgba(0,0,0,0.08), 0 0px 0px #fff;">
Completions vs Responses Output
</h4>
"""))
display(styled)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <pandas.io.formats.style.Styler at 0x11dc60790>
    ```

### 結果視覺化

下面的圖呈現 structured QA 評估的資料和程式碼輸出，讓你了解資料分布和評估流程。

---

**評估資料概覽**

![Evaluation Data Part 1](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_qa_data_1.png)

![Evaluation Data Part 2](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_qa_data_2.png)

---

**評估程式碼流程**

![Evaluation Code Structure](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_qa_code.png)

---

看過這些圖，你就能更了解評估資料集的結構，以及評估 QA 任務 structured output 的步驟。


### 使用案例 2：多語言情緒抽取
用類似的方式，我們來評估一個產生 structured output 的多語言情緒抽取模型。

```python
# Sample in-memory dataset for sentiment extraction
sentiment_dataset = [
    {
        "text": "I love this product!",
        "channel": "twitter",
        "language": "en"
    },
    {
        "text": "This is the worst experience I've ever had.",
        "channel": "support_ticket",
        "language": "en"
    },
    {
        "text": "It's okay – not great but not bad either.",
        "channel": "app_review",
        "language": "en"
    },
    {
        "text": "No estoy seguro de lo que pienso sobre este producto.",
        "channel": "facebook",
        "language": "es"
    },
    {
        "text": "总体来说，我对这款产品很满意。",
        "channel": "wechat",
        "language": "zh"
    },
]
```

```python
# Define output schema
sentiment_output_schema = {
    "type": "object",
    "properties": {
        "sentiment": {
            "type": "string",
            "description": "overall label: positive / negative / neutral"
        },
        "confidence": {
            "type": "number",
            "description": "confidence score 0-1"
        },
        "emotions": {
            "type": "array",
            "description": "list of dominant emotions (e.g. joy, anger)",
            "items": {"type": "string"}
        }
    },
    "required": ["sentiment", "confidence", "emotions"],
    "additionalProperties": False
}

# Grader prompts
sentiment_grader_system = """You are a strict grader for sentiment extraction.
Given the text and the model's JSON output, score correctness on a 1-5 scale."""

sentiment_grader_user = """Text: {{item.text}}
Model output:
{{sample.output_json}}
"""
```

```python
# Register an eval for the richer sentiment task
sentiment_eval = client.evals.create(
    name="sentiment_extraction_eval",
    data_source_config={
        "type": "custom",
        "item_schema": {          # matches the new dataset fields
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "channel": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["text"],
        },
        "include_sample_schema": True,
    },
    testing_criteria=[
        {
            "type": "score_model",
            "name": "Sentiment Grader",
            "model": "o3",
            "input": [
                {"role": "system", "content": sentiment_grader_system},
                {"role": "user",   "content": sentiment_grader_user},
            ],
            "range": [1, 5],
            "pass_threshold": 3.5,
        }
    ],
)
```

```python
# Run the sentiment eval
sentiment_run = client.evals.runs.create(
    name="gpt-4.1-sentiment",
    eval_id=sentiment_eval.id,
    data_source={
        "type": "responses",
        "source": {
            "type": "file_content",
            "content": [{"item": item} for item in sentiment_dataset],
        },
        "input_messages": {
            "type": "template",
            "template": [
                {
                    "type": "message",
                    "role": "system",
                    "content": {"type": "input_text", "text": "You are a helpful assistant."},
                },
                {
                    "type": "message",
                    "role": "user",
                    "content": {
                        "type": "input_text",
                        "text": "{{item.text}}",
                    },
                },
            ],
        },
        "model": "gpt-4.1",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 100,
            "top_p": 0.9,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "sentiment_output",
                    "schema": sentiment_output_schema,
                    "strict": True,
                },
            },
        },
    },
)
```

### 視覺化 evals 資料
![image](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/evals_sentiment.png)

### 總結與下一步

這份 notebook 示範了怎麼用 OpenAI Evaluation API 評估模型在 structured output 任務上的表現。

**下一步：**
- 建議你拿自己的模型和資料集試試這個 API。
- 也可以看 API 文件，了解更多用法。

更多資訊請看 [OpenAI Evals 文件](https://platform.openai.com/docs/guides/evals)。


## 重點整理

- structured output 要靠自動化 eval 把期望寫成程式，不要靠抽查和臨時改 prompt。
- 一個 eval 由資料集、grader rubric 和註冊動作組成，之後可以對同一個 eval 發起多個 run 比較。
- 用 rubric 模型評分時，把完整性和品質拆成不同維度，結果比較好分析。
- 輪詢 run 並把結果存成 JSON，方便事後檢視或接進 CI。
- 同一套流程換資料集和 rubric 就能套到其他任務，例如多語言情緒抽取。

## 練習

1. 在 `get_dataset` 多加一個你自己的 Python 檔案進資料集，重跑 eval 看分數變化。
2. 修改 `structured_output_grader` 的 rubric，把 1-7 分改成 1-5 分，或加一個新的評分維度，比較兩次 run 的結果。
3. 在輪詢後的輸出裡，只篩出分數低於某個門檻的項目並印出，找出模型最常漏掉哪一種符號。
