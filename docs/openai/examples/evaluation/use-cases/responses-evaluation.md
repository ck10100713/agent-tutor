---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/use-cases/responses-evaluation.ipynb
---

# Evals API 使用案例：Responses 評估

> 原文：[examples/evaluation/use-cases/responses-evaluation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/responses-evaluation.ipynb)

這份 cookbook 示範怎麼用已儲存的 Responses API log 來評估新模型。

## 這篇在做什麼
這個 eval 要比較新模型（gpt-4.1-mini）和舊模型（gpt-4o-mini）在一批已儲存 response 上的表現。好處是對多數開發者來說，不用花時間自己組一整套 eval，因為資料早就存在你的 [logs 頁面](https://platform.openai.com/logs)裡。

## 學完你會
- 用 Responses API 產生範例流量，並確認它們被存進 logs。
- 用篩選條件指定要評估哪些已儲存的 response，建立 eval run 評估原始回覆。
- 對同一批資料跑新模型（gpt-4.1-mini）的 run，到 dashboard 比較結果。

## 開跑前
- 需要 OpenAI API key。
- 你的 org 必須沒有停用資料 logging（例如 zdr），否則看不到儲存的 response。

```python
import openai
import os


client = openai.OpenAI()
```

我們想看 gpt-4.1 和 gpt-4o 在解釋程式碼庫這件事上表現如何。因為只有在已經有使用者流量時才能使用 responses 資料來源，所以我們先用 4o 產生一些範例流量，再比較 gpt-4.1 的表現。

我們會從 OpenAI SDK 取幾個範例程式檔，請 gpt-4o 解釋給我們聽。

```python
openai_sdk_file_path = os.path.dirname(openai.__file__)

# Get some example code files from the OpenAI SDK 
file_paths   = [
    os.path.join(openai_sdk_file_path, "resources", "evals", "evals.py"),
    os.path.join(openai_sdk_file_path, "resources", "responses", "responses.py"),
    os.path.join(openai_sdk_file_path, "resources", "images.py"),
    os.path.join(openai_sdk_file_path, "resources", "embeddings.py"),
    os.path.join(openai_sdk_file_path, "resources", "files.py"),
]

print(file_paths[0])
```

現在來產生一些 response。

```python
for file_path in file_paths:
    response = client.responses.create(
        input=[
            {"role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "What does this file do?"
                },
                {
                    "type": "input_text",
                    "text": open(file_path, "r").read(),
                },
            ]},
        ],
        model="gpt-4o-mini",
    )
    print(response.output_text)
```

注意，要讓這個流程成立，你必須在沒有停用資料 logging（例如透過 zdr 等）的 org 上操作。如果不確定是不是這樣，到 https://platform.openai.com/logs?api=responses 看看能不能看到剛剛產生的 response。

````python
grader_system_prompt = """
You are **Code-Explanation Grader**, an expert software engineer and technical writer.  
Your job is to score how well *Model A* explained the purpose and behaviour of a given source-code file.

### What you receive
1. **File contents** – the full text of the code file (or a representative excerpt).  
2. **Candidate explanation** – the answer produced by Model A that tries to describe what the file does.

### What to produce
Return a single JSON object that can be parsed by `json.loads`, containing:
```json
{
  "steps": [
    { "description": "...", "result": "float" },
    { "description": "...", "result": "float" },
    { "description": "...", "result": "float" }
  ],
  "result": "float"
}
```
• Each object in `steps` documents your reasoning for one category listed under “Scoring dimensions”.  
• Place your final 1 – 7 quality score (inclusive) in the top-level `result` key as a **string** (e.g. `"5.5"`).

### Scoring dimensions (evaluate in this order)

1. **Correctness & Accuracy ≈ 45 %**  
   • Does the explanation match the actual code behaviour, interfaces, edge cases, and side effects?  
   • Fact-check every technical claim; penalise hallucinations or missed key functionality.

2. **Completeness & Depth ≈ 25 %**  
   • Are all major components, classes, functions, data flows, and external dependencies covered?  
   • Depth should be appropriate to the file’s size/complexity; superficial glosses lose points.

3. **Clarity & Organization ≈ 20 %**  
   • Is the explanation well-structured, logically ordered, and easy for a competent developer to follow?  
   • Good use of headings, bullet lists, and concise language is rewarded.

4. **Insight & Usefulness ≈ 10 %**  
   • Does the answer add valuable context (e.g., typical use cases, performance notes, risks) beyond line-by-line paraphrase?  
   • Highlighting **why** design choices matter is a plus.

### Error taxonomy
• **Major error** – Any statement that materially misrepresents the file (e.g., wrong API purpose, inventing non-existent behaviour).  
• **Minor error** – Small omission or wording that slightly reduces clarity but doesn’t mislead.  
List all found errors in your `steps` reasoning.

### Numeric rubric
1  Catastrophically wrong; mostly hallucination or irrelevant.  
2  Many major errors, few correct points.  
3  Several major errors OR pervasive minor mistakes; unreliable.  
4  Mostly correct but with at least one major gap or multiple minors; usable only with caution.  
5  Solid, generally correct; minor issues possible but no major flaws.  
6  Comprehensive, accurate, and clear; only very small nit-picks.  
7  Exceptional: precise, thorough, insightful, and elegantly presented; hard to improve.

Use the full scale. Reserve 6.5 – 7 only when you are almost certain the explanation is outstanding.

Then set `"result": "4.0"` (example).

Be rigorous and unbiased.
"""
user_input_message = """**User input**

{{item.input}}

**Response to evaluate**

{{sample.output_text}}
"""
````

```python
logs_eval = client.evals.create(
    name="Code QA Eval",
    data_source_config={
        "type": "logs",
    },
    testing_criteria=[
        {
			"type": "score_model",
            "name": "General Evaluator",
            "model": "o3",
            "input": [{
                "role": "system",
                "content": grader_system_prompt,
            }, {
                "role": "user",
                "content": user_input_message,
            },
            ],
            "range": [1, 7],
            "pass_threshold": 5.5,
        }
    ]
)
```

首先，啟動一次 run 來評估原始回覆有多好。做法只要設定篩選條件，指定要評估哪些 response。

```python
gpt_4o_mini_run = client.evals.runs.create(
    name="gpt-4o-mini",
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {"type": "responses", "limit": len(file_paths)}, # just grab the most recent responses
    },
)
```

接著看看 4.1-mini 的表現！

```python
gpt_41_mini_run = client.evals.runs.create(
    name="gpt-4.1-mini",
    eval_id=logs_eval.id,
    data_source={
        "type": "responses",
        "source": {"type": "responses", "limit": len(file_paths)},
        "input_messages": {
            "type": "item_reference",
            "item_reference": "item.input",
        },
        "model": "gpt-4.1-mini",
    }
)
```

現在到 dashboard 看結果如何！

```python
gpt_4o_mini_run.report_url
```

## 重點整理
- 已存在 logs 的 Responses 流量可以直接當 eval 資料，不用另外準備資料集。
- 比較新舊模型時，用同一批輸入、同樣的評分方式，結果才公平。
- 篩選條件決定評估範圍，可以只挑特定模型或特定時段的 response。
- 這個做法要求資料沒有被關閉 logging，用之前先確認。

## 練習
1. 把要解釋的程式檔換成別的檔案，重新產生範例流量。
2. 修改篩選條件，只評估其中一部分 response，看 run 的樣本數怎麼變。
3. 把比較的新模型換成另一個模型，跑一次 run，並在 dashboard 比較三者的差異。
