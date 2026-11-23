---
translated: true
source: examples/evaluation/use-cases/web-search-evaluation.ipynb
---

# Evals API 使用案例：Web Search 評估

> 原文：[examples/evaluation/use-cases/web-search-evaluation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/web-search-evaluation.ipynb)



## 這篇在做什麼
示範怎麼用 OpenAI **Evals** 框架和自訂的 in-memory 資料集，評估模型從網路上找出正確答案的能力。流程包含定義資料集、設定 LLM grader、跑 eval 並檢視結果。

## 學完你會
- 定義一份問答配對的 in-memory 資料集當 eval 資料
- 設定 LLM-based 的 pass/fail grader 和 eval 設定
- 對 `gpt-4.1` 和 `gpt-4.1-mini` 跑評估、輪詢完成狀態，並檢視輸出

## 開跑前
需要 OpenAI API key。結果可以在 https://platform.openai.com/evaluations 的 evals dashboard 查看。

這份 notebook 示範怎麼用 OpenAI **Evals** 框架和自訂的 in-memory 資料集，評估模型從網路上找出正確答案的能力。

**目標：**
- 示範怎麼設定並執行 web search 品質的評估。
- 提供評估 LLM 資訊檢索能力的範本。



## 環境設定

先匯入需要的函式庫，並設定 OpenAI client。
這樣就能存取 OpenAI API 和評估需要的所有工具。

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

```python
import os
import time
import pandas as pd
from IPython.display import display

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY") or os.getenv("_OPENAI_API_KEY"),
)
```

## 定義自訂的評估資料集

我們為 web search 評估定義一個小型的 in-memory 問答配對資料集。
每個項目包含 `query`（使用者的搜尋 prompt）和 `answer`（預期的標準答案）。

> **提示：**
> 你可以修改或擴充這份資料集，適應自己的使用情境，或測試更廣的搜尋情境。

```python
def get_dataset(limit=None):
    dataset = [
        {
            "query": "coolest person in the world, the 100m dash at the 2008 olympics was the best sports event of all time",
            "answer": "usain bolt",
        },
        {
            "query": "best library in the world, there is nothing better than a dataframe",
            "answer": "pandas",
        },
        {
            "query": "most fun place to visit, I am obsessed with the Philbrook Museum of Art",
            "answer": "tulsa, oklahoma",
        },
        {
            "query": "who created the python programming language, beloved by data scientists everywhere",
            "answer": "guido van rossum",
        },
        {
            "query": "greatest chess player in history, famous for the 1972 world championship",
            "answer": "bobby fischer",
        },
        {
            "query": "the city of lights, home to the eiffel tower and louvre museum",
            "answer": "paris",
        },
        {
            "query": "most popular search engine, whose name is now a verb",
            "answer": "google",
        },
        {
            "query": "the first man to walk on the moon, giant leap for mankind",
            "answer": "neil armstrong",
        },
        {
            "query": "groundbreaking electric car company founded by elon musk",
            "answer": "tesla",
        },
        {
            "query": "founder of microsoft, philanthropist and software pioneer",
            "answer": "bill gates",
        },
    ]
    return dataset[:limit] if limit else dataset
```

## 定義評分邏輯

評估模型的答案時，我們用 LLM-based 的 pass/fail grader：

- **Pass/Fail Grader：**
  一個 LLM-based grader，檢查模型的答案（來自 web search）是否符合預期答案（標準答案），或是否包含正確的資訊。

> **最佳實務：**
> 用 LLM-based grader 在評估開放式或模糊的回應時比較有彈性。

```python
pass_fail_grader = """
You are a helpful assistant that grades the quality of a web search.
You will be given a query and an answer.
You should grade the quality of the web search.

You should either say "pass" or "fail", if the query contains the answer.

"""

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
```

## 定義評估設定

現在用 OpenAI Evals 框架設定評估。

這一步會指定：
- 評估名稱和資料集。
- 每個項目的 schema（每組問答裡有哪些欄位）。
- 要使用的 grader（LLM-based pass/fail）。
- 通過的標準和標籤。

> **最佳實務：**
> 事先清楚定義評估 schema 和評分邏輯，能確保可重現且透明。

```python
# Create the evaluation definition using the OpenAI Evals client.
logs_eval = client.evals.create(
    name="Web-Search Eval",
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
            "name": "Web Search Evaluator",
            "model": "o3",
            "input": [
                {
                    "role": "system",
                    "content": pass_fail_grader,
                },
                {
                    "role": "user",
                    "content": pass_fail_grader_user_prompt,
                },
            ],
            "passing_labels": ["pass"],
            "labels": ["pass", "fail"],
        }
    ],
)
```

## 執行模型並輪詢完成狀態

現在對選定的模型（`gpt-4.1` 和 `gpt-4.1-mini`）執行評估。

啟動評估 run 後，我們會輪詢，直到它完成（`completed` 或 `failed`）。

> **最佳實務：**
> 輪詢時加入延遲，可以避免過多的 API 呼叫，並有效使用資源。

```python
# Launch the evaluation run for gpt-4.1 using web search
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
        "model": "gpt-4.1",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 10000,
            "top_p": 0.9,
            "tools": [{"type": "web_search_preview"}],
        },
    },
)
```

```python
# Launch the evaluation run for gpt-4.1-mini using web search
gpt_4one_mini_responses_run = client.evals.runs.create(
    name="gpt-4.1-mini",
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
        "model": "gpt-4.1-mini",
        "sampling_params": {
            "seed": 42,
            "temperature": 0.7,
            "max_completions_tokens": 10000,
            "top_p": 0.9,
            "tools": [{"type": "web_search_preview"}],
        },
    },
)
```

```python
# poll both runs at the same time, until they are complete or failed
def poll_runs(eval_id, run_ids):
    while True:
        runs = [client.evals.runs.retrieve(run_id, eval_id=eval_id) for run_id in run_ids]
        for run in runs:
            print(run.id, run.status, run.result_counts)
        if all(run.status in {"completed", "failed"} for run in runs):
            break
        time.sleep(5)

# Start polling the run until completion
poll_runs(logs_eval.id, [gpt_4one_responses_run.id, gpt_4one_mini_responses_run.id])
```

??? note "輸出"

    ```text
    evalrun_68477e0f56a481919eea5e7d8a04225e completed ResultCounts(errored=0, failed=1, passed=9, total=10)
    evalrun_68477e712bb48191bc7368b084f8c52c completed ResultCounts(errored=0, failed=0, passed=10, total=10)
    ```

## 顯示並解讀模型輸出

最後顯示模型的輸出，供人工檢查和進一步分析。

- 資料集裡每個查詢的答案都會印出來。
- 可以把輸出跟預期答案比較，評估品質、相關性和正確性。


```python
# Retrieve output items for the 4.1 model after completion
four_one = client.evals.runs.output_items.list(
    run_id=gpt_4one_responses_run.id, eval_id=logs_eval.id
)

# Retrieve output items for the 4.1-mini model after completion
four_one_mini = client.evals.runs.output_items.list(
    run_id=gpt_4one_mini_responses_run.id, eval_id=logs_eval.id
)

# Collect outputs for both models
four_one_outputs = [item.sample.output[0].content for item in four_one]
four_one_mini_outputs = [item.sample.output[0].content for item in four_one_mini]

# Create DataFrame for side-by-side display
df = pd.DataFrame({
    "GPT-4.1 Output": four_one_outputs,
    "GPT-4.1-mini Output": four_one_mini_outputs
})

display(df)
```

??? note "輸出"

    ```text
                                          GPT-4.1 Output  \
    0  If you're captivated by the Philbrook Museum o...   
    1  \n## [Paris, France](https://www.google.com/ma...   
    2  Bill Gates, born on October 28, 1955, in Seatt...   
    3  Usain Bolt's performance in the 100-meter fina...   
    4  It seems you're interested in both the world's...   
    5  Neil Armstrong was the first person to walk on...   
    6  Tesla, Inc. is an American electric vehicle an...   
    7  Bobby Fischer, widely regarded as one of the g...   
    8  Guido van Rossum, a Dutch programmer born on J...   
    9  The most popular search engine whose name has ...   

                                     GPT-4.1-mini Output  
    0  Bobby Fischer is widely regarded as one of the...  
    1  The 2008 Olympic 100m dash is widely regarded ...  
    2  If you're looking for fun places to visit in T...  
    3  On July 20, 1969, astronaut Neil Armstrong bec...  
    4  Bill Gates is a renowned software pioneer, phi...  
    5  Your statement, "there is nothing better than ...  
    6  The search engine whose name has become synony...  
    7  \n## [Paris, France](https://www.google.com/ma...  
    8  Guido van Rossum, a Dutch programmer born on J...  
    9  Elon Musk is the CEO and largest shareholder o...
    ```

你可以到 https://platform.openai.com/evaluations 在 evals dashboard 視覺化結果，如下圖：

![evals-websearch-dashboard](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/evals_websearch_dashboard.png)


這份 notebook 示範了用 OpenAI Evals 框架評估語言模型 web search 能力的工作流程。

**涵蓋的重點：**
- 為 web search 評估定義聚焦的自訂資料集。
- 設定 LLM-based grader 做穩健的評估。
- 用最新的 OpenAI 模型和 web search 工具執行可重現的評估。
- 取回並顯示模型輸出以供檢查。

**後續步驟和建議：**
- **擴充資料集：** 加入更多樣、更有挑戰性的查詢，更好地評估模型能力。
- **分析結果：** 彙整 pass/fail 比率、視覺化表現，或做錯誤分析找出強項和弱點。
- **試驗模型和工具：** 試試其他模型、調整工具設定，或測試其他類型的資訊檢索任務。
- **自動化報告：** 產生摘要表格或圖表，方便分享和決策。

更多資訊請看 [OpenAI Evals 文件](https://platform.openai.com/docs/guides/evals)。

## 重點整理
- Eval 由資料集、item schema、grader 和通過標準組成，事先定好才能重現。
- 問答型的開放式回答適合用 LLM-based grader 判 pass/fail，比字串比對有彈性。
- 輪詢 run 狀態時要加延遲，避免過度呼叫 API。
- 光看 pass/fail 不夠，還要看輸出內容做錯誤分析。

## 練習
1. 在資料集裡多加幾筆不同領域的問答，重新跑評估。
2. 修改 grader 的評分指示，讓它對「答案部分正確」也能區分出來。
3. 把評估的模型清單加上另一個模型，比較三者的 pass 比率。
