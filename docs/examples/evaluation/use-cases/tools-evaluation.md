---
translated: true
source: examples/evaluation/use-cases/tools-evaluation.ipynb
---

# Evals API 使用案例：評估 tool 呼叫

> 原文：[examples/evaluation/use-cases/tools-evaluation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/tools-evaluation.ipynb)



## 這篇在做什麼

用 Evals API 評估模型從原始碼擷取結構化資訊的能力：從 Python 檔案裡找出定義的 symbol（函式、類別、方法、變數）。模型透過 tool 呼叫回傳結果，再由 grader 依 rubric 打分，並同時比較 Completions 和 Responses 兩個 endpoint。

## 學完你會

- 用 SDK 的檔案建一個小型資料集，並寫一份 grading rubric
- 用 `client.evals.create(...)` 建 eval，再對同一個 eval 啟動兩個 run
- 寫輪詢程式等 run 完成，並檢視模型回傳的 symbols

## 開跑前

- OpenAI API key（環境變數 `OPENAI_API_KEY`）
- 如果要評估帶 tool 的 assistant，帳號要啟用 Assistants v2 beta

這份 cookbook 示範如何用 tool evaluation **衡量並提升模型從原始碼擷取結構化資訊的能力**。具體來說，是找出 Python 檔案裡定義的 *symbol*（函式、類別、方法和變數）。

## 設定<a name="Setup"></a>

安裝最新的 **openai** Python 套件（≥ 1.14.0），並設定 `OPENAI_API_KEY` 環境變數。如果也想評估*帶 tool 的 assistant*，要在帳號啟用 *Assistants v2 beta*。

```bash
pip install --upgrade openai
export OPENAI_API_KEY=sk‑...
```
下面匯入 SDK、建立 client，並定義一個 helper，用 **openai** 套件本身的檔案建一個小資料集。

```python
%pip install --upgrade openai pandas jinja2 rich --quiet

import os
import time
import openai
from rich import print

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
* `get_dataset` 讀取幾個 SDK 檔案，建一個小型的記憶體內資料集。
* `structured_output_grader` 定義一份詳細的評分 rubric。
* `sampled.output_tools[0].function.arguments.symbols` 指的是根據 tool 呼叫，模型從程式碼檔案擷取出的 symbol。
* `client.evals.create(...)` 會把 eval 註冊到平台上。

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
{{sample.output_tools[0].function.arguments.symbols}}
</Extracted Information>
"""
```

### 建立 Eval

這裡建一個 eval，用來評估從程式碼檔案擷取資訊的品質。


```python
logs_eval = client.evals.create(
    name="Code QA Eval",
    data_source_config={
        "type": "custom",
        "item_schema": {"type": "object", "properties": {"input": {"type": "string"}}},
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
            "pass_threshold": 5.0,
        }
    ],
)

symbol_tool = {
    "name": "extract_symbols",
    "description": "Extract the symbols from the code file",
    "parameters": {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "array",
                "description": "A list of symbols extracted from Python code.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the symbol."},
                        "symbol_type": {"type": "string", "description": "The type of the symbol, e.g., variable, function, class."},
                    },
                    "required": ["name", "symbol_type"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["symbols"],
        "additionalProperties": False,
    },
}
```

### 啟動模型 run
這裡對同一個 eval 啟動兩個 run：一個呼叫 **Completions** endpoint，一個呼叫 **Responses** endpoint。

```python
gpt_4one_completions_run = client.evals.runs.create(
    name="gpt-4.1",
    eval_id=logs_eval.id,
    data_source={
        "type": "completions",
        "source": {"type": "file_content", "content": [{"item": item} for item in get_dataset(limit=1)]},
        "input_messages": {
            "type": "template",
            "template": [
                {"type": "message", "role": "system", "content": {"type": "input_text", "text": "You are a helpful assistant."}},
                {"type": "message", "role": "user", "content": {"type": "input_text", "text": "Extract the symbols from the code file {{item.input}}"}},
            ],
        },
        "model": "gpt-4.1",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 10000,
            "top_p": 0.9,
            "tools": [{"type": "function", "function": symbol_tool}],
        },
    },
)

gpt_4one_responses_run = client.evals.runs.create(
    name="gpt-4.1-mini",
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {"type": "file_content", "content": [{"item": item} for item in get_dataset(limit=1)]},
        "input_messages": {
            "type": "template",
            "template": [
                {"type": "message", "role": "system", "content": {"type": "input_text", "text": "You are a helpful assistant."}},
                {"type": "message", "role": "user", "content": {"type": "input_text", "text": "Extract the symbols from the code file {{item.input}}"}},
            ],
        },
        "model": "gpt-4.1-mini",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 10000,
            "top_p": 0.9,
            "tools": [{"type": "function", **symbol_tool}],
        },
    },
)
```

### 輪詢工具

我們寫一個輪詢工具，用來取得 eval run 的結果。

```python
def poll_runs(eval_id, run_ids):
    # poll both runs at the same time, until they are complete or failed
    while True:
        runs = [client.evals.runs.retrieve(run_id, eval_id=eval_id) for run_id in run_ids]
        for run in runs:
            print(run.id, run.status, run.result_counts)
        if all(run.status in ("completed", "failed") for run in runs):
            break
        time.sleep(5)


poll_runs(logs_eval.id, [gpt_4one_completions_run.id, gpt_4one_responses_run.id])
```

??? note "輸出"

    ```text
    evalrun_6848e2269570819198b757fe12b979da completed
    ResultCounts(errored=0, failed=1, passed=0, total=1)
    ```

    ```text
    evalrun_6848e227d3a481918a9b970c897b5998 completed
    ResultCounts(errored=0, failed=1, passed=0, total=1)
    ```

```python

### Get Output
completions_output = client.evals.runs.output_items.list(
    run_id=gpt_4one_completions_run.id, eval_id=logs_eval.id
)

responses_output = client.evals.runs.output_items.list(
    run_id=gpt_4one_responses_run.id, eval_id=logs_eval.id
)
```

### 檢視結果<a name="Inspecting-results"></a>

對 completions 和 responses 都印出模型回傳的 *symbols* 字典。你可以拿它跟參考答案比對，或算 precision / recall。

```python
import json
import pandas as pd
from IPython.display import display, HTML

def extract_symbols(output_list):
    symbols_list = []
    for item in output_list:
        try:
            args = item.sample.output[0].tool_calls[0]["function"]["arguments"]
            symbols = json.loads(args)["symbols"]
            symbols_list.append(symbols)
        except Exception as e:
            symbols_list.append([{"error": str(e)}])
    return symbols_list

completions_symbols = extract_symbols(completions_output)
responses_symbols = extract_symbols(responses_output)

def symbols_to_html_table(symbols):
    if symbols and isinstance(symbols, list):
        df = pd.DataFrame(symbols)
        return (
            df.style
            .set_properties(**{
                'white-space': 'pre-wrap',
                'word-break': 'break-word',
                'padding': '2px 6px',
                'border': '1px solid #C3E7FA',
                'font-size': '0.92em',
                'background-color': '#FDFEFF'
            })
            .set_table_styles([{
                'selector': 'th',
                'props': [
                    ('font-size', '0.95em'),
                    ('background-color', '#1CA7EC'),
                    ('color', '#fff'),
                    ('border-bottom', '1px solid #18647E'),
                    ('padding', '2px 6px')
                ]
            }])
            .hide(axis='index')
            .to_html()
        )
    return f"<div style='padding:4px 0;color:#D9534F;font-style:italic;font-size:0.9em'>{str(symbols)}</div>"

table_rows = []
max_len = max(len(completions_symbols), len(responses_symbols))
for i in range(max_len):
    c_html = symbols_to_html_table(completions_symbols[i]) if i < len(completions_symbols) else ""
    r_html = symbols_to_html_table(responses_symbols[i]) if i < len(responses_symbols) else ""
    table_rows.append(f"""
      <tr style="height:1.2em;">
          <td style="vertical-align:top; background:#F6F8FA; border-right:1px solid #E3E3E3; padding:2px 4px;">{c_html}</td>
          <td style="vertical-align:top; background:#F6F8FA; padding:2px 4px;">{r_html}</td>
      </tr>
    """)

table_html = f"""
<div style="margin-bottom:0.5em;margin-top:0.2em;">
  <h4 style="color:#1CA7EC;font-weight:600;letter-spacing:0.5px;
     text-shadow:0 1px 2px rgba(0,0,0,0.06), 0 0px 0px #fff;font-size:1.05em;margin:0 0 0.35em 0;">
    Completions vs Responses Output Symbols
  </h4>
  <table style="border-collapse:separate;border-spacing:0 0.2em;width:100%;border-radius:5px;overflow:hidden;box-shadow:0 1px 7px #BEE7FA22;">
    <thead>
      <tr style="height:1.4em;">
              <th style="width:50%;background:#323C50;color:#fff;font-size:1em;padding:6px 10px;border-bottom:2px solid #1CA7EC;text-align:center;">Completions Output</th>
      <th style="width:50%;background:#323C50;color:#fff;font-size:1em;padding:6px 10px;border-bottom:2px solid #1CA7EC;text-align:center;">Responses Output</th>
      </tr>
    </thead>
    <tbody>
      {''.join(table_rows)}
    </tbody>
  </table>
</div>
"""

display(HTML(table_html))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

### 在 Evals Dashboard 視覺化

你可以到 Evals Dashboard 查看資料的視覺化。


![evals_tool_dashboard](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/evals_tool_dashboard.png)


run 完成後，也可以在 Evals Dashboard 看失敗案例的說明，如下圖。

![evals_tool_failed](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/eval_tools_fail.png)




這份 notebook 示範了如何用 OpenAI Evals，評估並改善模型透過 tool 呼叫從 Python 程式碼擷取結構化資訊的能力。


OpenAI Evals 提供了穩健、可重現的框架，用來評估 LLM 在結構化擷取任務上的表現。結合清楚的 tool schema、嚴謹的 grading rubric 和結構良好的資料集，你就能衡量並提升整體表現。

*更多細節請看 [OpenAI Evals 文件](https://platform.openai.com/docs/guides/evals)。*

## 重點整理

- eval 由資料集、grader 和 run 三塊組成，同一個 eval 可以對不同設定重複跑，才能公平比較。
- 結構化擷取靠 tool schema 約束輸出格式，grader 再去比對內容對不對。
- rubric 寫得越明確，評分越穩定，失敗原因也越好分析。
- 拿到 symbols 之後還可以自己算 precision / recall，不必只靠 grader 的分數。

## 練習

1. 改 `get_dataset` 讀的檔案，換成別的 SDK 檔案，看分數怎麼變。
2. 修改 `structured_output_grader` 的 rubric，讓它對漏掉的 symbol 扣更重，重跑比較。
3. 把兩個 run 的 symbols 輸出跟自己手動整理的答案比對，算出 precision 和 recall。
