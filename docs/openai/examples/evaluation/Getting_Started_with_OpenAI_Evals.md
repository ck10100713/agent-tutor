---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/Getting_Started_with_OpenAI_Evals.ipynb
---
# Getting Started with OpenAI Evals

> 原文：[examples/evaluation/Getting_Started_with_OpenAI_Evals.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/Getting_Started_with_OpenAI_Evals.ipynb)



## 這篇在做什麼

用 OpenAI Evals 這個開源框架，替「讓模型產生 SQL」這個任務建一組 eval：先做資料集和 YAML 設定，再用 `oaieval` 跑，最後翻 log 看哪些題答錯。

## 學完你會

- 知道 eval 的兩種評分方式（程式邏輯比對、model grading），以及 basic 和 model-graded 模板各適合什麼情境。
- 能做出 `jsonl` 格式的 eval 資料集，也能用 GPT-4 生成 synthetic data，再寫出 registry 用的 YAML。
- 能用 `oaieval` 跑 eval，並從 `/tmp/evallogs` 的 log 找出失敗的 sample 來分析。

## 開跑前

- 要 clone [openai/evals](https://github.com/openai/evals) 並照它的說明安裝。
- 設好 `OPENAI_API_KEY` 環境變數，跑 eval 會花 API 費用。



**注意：OpenAI 現在有託管版的 evals 產品和 API，建議改用那個。
見 [Evals](https://platform.openai.com/docs/guides/evals)**

[OpenAI Evals](https://github.com/openai/evals/tree/main) 框架包含：
1. 一個用來評估 LLM（大型語言模型）或建構在 LLM 上的系統的框架。
2. 一個開源的 eval registry，收錄各種有難度的 eval。

這份 notebook 會講：
* eval 和 [OpenAI Evals](https://github.com/openai/evals/tree/main) 函式庫的簡介
* 建立一個 eval
* 執行一個 eval

#### 什麼是 evaluations / `evals`？

Evaluation 就是驗證、測試你的 LLM 應用產生的輸出。有扎實的 eval，應用會比較穩、比較可靠，程式或模型換版時也不容易壞掉。eval 是一個用來衡量 LLM 或 LLM 系統輸出品質的任務：給一個輸入 prompt，產生一個輸出，再拿一組理想答案去評估這個輸出，得出系統的品質。

#### 為什麼 eval 重要

如果你在用 `GPT-4` 這類 foundation model 開發，寫好的 eval 是你能做的最有效益的事之一。開發 AI 方案是反覆迭代的過程，[沒有 eval 的話，很難也很花時間去搞清楚](https://youtu.be/XGJNo8TpuVA?feature=shared&t=1089)不同模型版本和 prompt 會怎麼影響你的使用情境。

OpenAI 會[持續升級模型](https://platform.openai.com/docs/models/continuous-model-upgrades)，有了 eval，你可以用標準化的方式快速測試新模型在你的情境表現如何。針對自己的目標建一套 eval，就能很快知道新模型適不適合。你也可以把 eval 放進 CI/CD pipeline，確保上線前準確率有達標。

#### eval 的類型

評分 completion 主要有兩種：自己寫驗證邏輯，或是讓模型自己檢查答案。下面各舉例說明。

**寫程式邏輯來檢查答案**

最簡單也最常見的 eval 是一個輸入配一個理想答案。例如輸入是「Obama 第一次當選總統是哪一年？」，理想答案是「2008」。把輸入餵給模型拿到 completion，如果模型說「2008」就算對。我們可以寫個字串比對，檢查 completion 有沒有包含「2008」。

另一個例子是要求產生合法的 JSON：寫段程式嘗試把 completion 當 JSON 解析，解析得過就算對。

**Model grading：兩階段流程，模型先回答問題，再請模型檢查這個回答對不對。**

假設輸入是要模型寫一個好笑的笑話。模型產生 completion 之後，我們再建一個新的輸入問模型：「下面這個笑話好笑嗎？先一步一步推理，再回答 yes 或 no」，並把 completion 放進去。如果新的 completion 最後是 "yes"，原本的 completion 就算對。

Model grading 用最新、最強的模型（像 `GPT-4`）效果最好，而且要讓它先推理再下判斷。model grading 本身有錯誤率，所以大規模跑之前，要先用人工評估驗證它的表現。最好用跟產生答案不同的模型來評分，例如用 `GPT-4` 評 `GPT-3.5` 的答案。

#### OpenAI Eval 模板

我們在使用 eval 的過程中發現有幾種「模板」可以涵蓋很多不同的 benchmark，並且把它們實作在 OpenAI Evals 函式庫裡，讓新 eval 更好寫。目前內建兩種模板：

* **Basic Eval Templates**：用確定性的函式比對輸出和 ideal_answers。適合預期回答變化很小的情況，像選擇題，或答案很直接的簡單問題。

* **Model-Graded Templates**：用 LLM 比對輸出和 ideal_answers 並判斷準不準。適合回答可能變化很大的情況，像開放式問題，這時讓模型自己評分是可行的自動化評估方式。


### 環境設定

先到 [github.com/openai/evals](https://github.com/openai/evals)，用 `git clone git@github.com:openai/evals.git` clone 專案，並照[安裝說明](https://github.com/openai/evals)做完。

之後要跑 eval，需要設定 OpenAI API key。拿到 key 後，用 `OPENAI_API_KEY` 環境變數指定。

跑 eval 前請留意 API 的費用。

```python
from openai import OpenAI
import pandas as pd

client = OpenAI()
```

## 為 OpenAI Evals 框架建立 eval

eval 的核心是一份資料集，加上一個定義在 YAML 檔裡的 eval class。要開始建一個 eval，我們需要：

1. `jsonl` 格式的測試資料集。
2. 要用的 eval 模板。

### 建立 eval 資料集
這次的情境是評估模型產生語法正確 SQL 的能力，資料表跟汽車製造有關。

首先要寫出想評估的 system prompt，裡面放給模型的指示，加上資料表結構的概要：
```
"TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]"
```

針對這個 prompt，我們可以問一個具體的問題：
```
"Q: how many car makers are their in germany?"
```

並且有一個預期答案：
```
"A: SELECT count ( * )  FROM CAR_MAKERS AS T1 JOIN COUNTRIES AS T2 ON T1.Country   =   T2.CountryId WHERE T2.CountryName   =   'germany'"
```

資料集需要是下面這個格式：
```
"input": [{"role": "system", "content": "<input prompt>"}, {"role": "user", "content": <user input>}, "ideal": "correct answer"]
```

全部組起來就是：
```
{"input": [{"role": "system", "content": "TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]\n"}, {"role": "system", "content": "Q: how many car makers are their in germany"}, "ideal": ["A: SELECT count ( * )  FROM CAR_MAKERS AS T1 JOIN COUNTRIES AS T2 ON T1.Country   =   T2.CountryId WHERE T2.CountryName   =   'germany'"]}
```


加速建 eval 資料集的一個方法，是用 `GPT-4` 生成 synthetic data。

````````````python
## Use GPT-4 to generate synthetic data
# Define the system prompt and user input (these should be filled as per the specific use case)
system_prompt = """You are a helpful assistant that can ask questions about a database table and write SQL queries to answer the question.
    A user will pass in a table schema and your job is to return a question answer pairing. The question should relevant to the schema of the table,
    and you can speculate on its contents. You will then have to generate a SQL query to answer the question. Below are some examples of what this should look like.

    Example 1
    ```````````
    User input: Table museum, columns = [*,Museum_ID,Name,Num_of_Staff,Open_Year]\nTable visit, columns = [*,Museum_ID,visitor_ID,Num_of_Ticket,Total_spent]\nTable visitor, columns = [*,ID,Name,Level_of_membership,Age]\nForeign_keys = [visit.visitor_ID = visitor.ID,visit.Museum_ID = museum.Museum_ID]\n
    Assistant Response:
    Q: How many visitors have visited the museum with the most staff?
    A: SELECT count ( * )  FROM VISIT AS T1 JOIN MUSEUM AS T2 ON T1.Museum_ID   =   T2.Museum_ID WHERE T2.Num_of_Staff   =   ( SELECT max ( Num_of_Staff )  FROM MUSEUM ) 
    ```````````

    Example 2
    ```````````
    User input: Table museum, columns = [*,Museum_ID,Name,Num_of_Staff,Open_Year]\nTable visit, columns = [*,Museum_ID,visitor_ID,Num_of_Ticket,Total_spent]\nTable visitor, columns = [*,ID,Name,Level_of_membership,Age]\nForeign_keys = [visit.visitor_ID = visitor.ID,visit.Museum_ID = museum.Museum_ID]\n
    Assistant Response:
    Q: What are the names who have a membership level higher than 4?
    A: SELECT Name   FROM VISITOR AS T1 WHERE T1.Level_of_membership   >   4 
    ```````````

    Example 3
    ```````````
    User input: Table museum, columns = [*,Museum_ID,Name,Num_of_Staff,Open_Year]\nTable visit, columns = [*,Museum_ID,visitor_ID,Num_of_Ticket,Total_spent]\nTable visitor, columns = [*,ID,Name,Level_of_membership,Age]\nForeign_keys = [visit.visitor_ID = visitor.ID,visit.Museum_ID = museum.Museum_ID]\n
    Assistant Response:
    Q: How many tickets of customer id 5?
    A: SELECT count ( * )  FROM VISIT AS T1 JOIN VISITOR AS T2 ON T1.visitor_ID   =   T2.ID WHERE T2.ID   =   5 
    ```````````
    """

user_input = "Table car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]"

messages = [{
        "role": "system",
        "content": system_prompt
    },
    {
        "role": "user",
        "content": user_input
    }
]

completion = client.chat.completions.create(
    model="gpt-4-turbo-preview",
    messages=messages,
    temperature=0.7,
    n=5
)

for choice in completion.choices:
    print(choice.message.content + "\n")
````````````

??? note "輸出"

    ```text
    Q: What is the average horsepower for cars made in Europe?
    A: SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN model_list ON car_names.Model = model_list.Model JOIN car_makers ON model_list.Maker = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId JOIN continents ON countries.Continent = continents.ContId WHERE continents.Continent = 'Europe'

    Q: What is the average horsepower for cars made in the USA?
    A: SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN car_makers ON car_names.MakeId = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId WHERE countries.CountryName = 'USA'

    Q: What is the average horsepower for cars produced in countries from the continent with the id '3'?
    A: SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN model_list ON car_names.Model = model_list.Model JOIN car_makers ON model_list.Maker = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId JOIN continents ON countries.Continent = continents.ContId WHERE continents.ContId = '3'

    Q: What is the average horsepower for cars made by makers from Europe?
    A: SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN model_list ON car_names.Model = model_list.Model JOIN car_makers ON model_list.Maker = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId JOIN continents ON countries.Continent = continents.ContId WHERE continents.Continent = 'Europe'

    Q: What is the average horsepower for cars made in the USA?

    A: SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN car_makers ON car_names.MakeId = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId WHERE countries.CountryName = 'USA'
    ```

拿到 synthetic data 之後，要把它轉成符合 eval 資料集的格式。

```python
eval_data = []
input_prompt = "TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]"

for choice in completion.choices:
    question = choice.message.content.split("Q: ")[1].split("\n")[0]  # Extracting the question
    answer = choice.message.content.split("\nA: ")[1].split("\n")[0]  # Extracting the answer
    eval_data.append({
        "input": [
            {"role": "system", "content": input_prompt},
            {"role": "user", "content": question},
        ],
        "ideal": answer
    })

for item in eval_data:
    print(item)
```

??? note "輸出"

    ```text
    {'input': [{'role': 'system', 'content': 'TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]'}, {'role': 'user', 'content': 'What is the average horsepower for cars made in Europe?'}], 'ideal': "SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN model_list ON car_names.Model = model_list.Model JOIN car_makers ON model_list.Maker = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId JOIN continents ON countries.Continent = continents.ContId WHERE continents.Continent = 'Europe'"}
    {'input': [{'role': 'system', 'content': 'TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]'}, {'role': 'user', 'content': 'What is the average horsepower for cars made in the USA?'}], 'ideal': "SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN car_makers ON car_names.MakeId = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId WHERE countries.CountryName = 'USA'"}
    {'input': [{'role': 'system', 'content': 'TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]'}, {'role': 'user', 'content': "What is the average horsepower for cars produced in countries from the continent with the id '3'?"}], 'ideal': "SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN model_list ON car_names.Model = model_list.Model JOIN car_makers ON model_list.Maker = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId JOIN continents ON countries.Continent = continents.ContId WHERE continents.ContId = '3'"}
    {'input': [{'role': 'system', 'content': 'TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]'}, {'role': 'user', 'content': 'What is the average horsepower for cars made by makers from Europe?'}], 'ideal': "SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN model_list ON car_names.Model = model_list.Model JOIN car_makers ON model_list.Maker = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId JOIN continents ON countries.Continent = continents.ContId WHERE continents.Continent = 'Europe'"}
    {'input': [{'role': 'system', 'content': 'TASK: Answer the following question with syntactically correct SQLite SQL. The SQL should be correct and be in context of the previous question-answer pairs.\nTable car_makers, columns = [*,Id,Maker,FullName,Country]\nTable car_names, columns = [*,MakeId,Model,Make]\nTable cars_data, columns = [*,Id,MPG,Cylinders,Edispl,Horsepower,Weight,Accelerate,Year]\nTable continents, columns = [*,ContId,Continent]\nTable countries, columns = [*,CountryId,CountryName,Continent]\nTable model_list, columns = [*,ModelId,Maker,Model]\nForeign_keys = [countries.Continent = continents.ContId,car_makers.Country = countries.CountryId,model_list.Maker = car_makers.Id,car_names.Model = model_list.Model,cars_data.Id = car_names.MakeId]'}, {'role': 'user', 'content': 'What is the average horsepower for cars made in the USA?'}], 'ideal': "SELECT AVG(cars_data.Horsepower) FROM cars_data JOIN car_names ON cars_data.Id = car_names.MakeId JOIN car_makers ON car_names.MakeId = car_makers.Id JOIN countries ON car_makers.Country = countries.CountryId WHERE countries.CountryName = 'USA'"}
    ```

接著要建 eval registry，這樣才能在框架裡跑它。

evals 框架需要一個 `.yaml` 檔，包含這些欄位：
* `id`：eval 的識別名稱
* `description`：eval 的簡短描述
* `disclaimer`：關於 eval 的補充說明
* `metrics`：有三種 metric 可選：match、includes、fuzzyMatch

我們這個 eval 的設定如下：

```python
"""
spider-sql:
  id: spider-sql.dev.v0
  metrics: [accuracy]
  description: Eval that scores SQL code from 194 examples in the Spider Text-to-SQL test dataset. The problems are selected by taking the first 10 problems for each database that appears in the test set.
    Yu, Tao, et al. \"Spider; A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task.\" Proceedings of the 2018 Conference on Empirical Methods in Natural Language Processing, 2018, https://doi.org/10.18653/v1/d18-1425.
  disclaimer: Problems are solved zero-shot with no prompting other than the schema; performance may improve with training examples, fine tuning, or a different schema format. Evaluation is currently done through model-grading, where SQL code is not actually executed; the model may judge correct SQL to be incorrect, or vice-versa.
spider-sql.dev.v0:
  class: evals.elsuite.modelgraded.classify:ModelBasedClassify
  args:
    samples_jsonl: sql/spider_sql.jsonl
    eval_type: cot_classify
    modelgraded_spec: sql
  """""
```

??? note "輸出"

    ```text
    '\nspider-sql:\n  id: spider-sql.dev.v0\n  metrics: [accuracy]\n  description: Eval that scores SQL code from 194 examples in the Spider Text-to-SQL test dataset. The problems are selected by taking the first 10 problems for each database that appears in the test set.\n    Yu, Tao, et al. "Spider; A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task." Proceedings of the 2018 Conference on Empirical Methods in Natural Language Processing, 2018, https://doi.org/10.18653/v1/d18-1425.\n  disclaimer: Problems are solved zero-shot with no prompting other than the schema; performance may improve with training examples, fine tuning, or a different schema format. Evaluation is currently done through model-grading, where SQL code is not actually executed; the model may judge correct SQL to be incorrect, or vice-versa.\nspider-sql.dev.v0:\n  class: evals.elsuite.modelgraded.classify:ModelBasedClassify\n  args:\n    samples_jsonl: sql/spider_sql.jsonl\n    eval_type: cot_classify\n    modelgraded_spec: sql\n  '
    ```

## 執行 eval

我們用 `oaieval` CLI 來跑這個 eval。先安裝函式庫：如果是在本機跑 [OpenAI Evals library](https://github.com/openai/evals)，用 `pip install .`；如果是跑現成的 eval，用 `pip install oaieval`。

然後用 CLI 執行：`oaieval gpt-3.5-turbo spider-sql`

這個指令需要一個模型名稱和一個 eval 名稱。另外要注意，我們提供兩個 CLI：`oaieval` 跑單一 eval，`oaievalset` 跑一組 eval。有效的 eval 名稱定義在 `evals/registry/evals` 底下的 YAML 檔，對應的實作在 `evals/elsuite`。

```python
!pip install evals --quiet
```

`oaieval` CLI 有很多 flag 可以改預設行為，用 `oaieval --help` 可以看完整清單。

指令跑完後，你會在 console 看到最終的準確率報告，還有一個暫存檔的路徑，裡面是完整報告。

`oaieval` 會到 `evals/registry/evals` 目錄找 `spider-sql` 的 eval YAML 檔，格式就是前面 cell 4 的那份。資料集的路徑寫在 eval YAML 的 args 參數裡，是 `samples_jsonl: sql/spider_sql.jsonl`，內容是 JSONL 格式（就是上面第 3 步產生的那份）。

指令跑完後，你會在 console 看到最終的準確率報告，還有一個暫存檔的路徑，裡面是完整報告。

```python
!oaieval gpt-3.5-turbo spider-sql --max_samples 25
```

??? note "輸出"

    ```text
    [2024-03-26 19:44:39,836] [registry.py:257] Loading registry from /Users/shyamal/.virtualenvs/openai/lib/python3.11/site-packages/evals/registry/evals
    [2024-03-26 19:44:43,623] [registry.py:257] Loading registry from /Users/shyamal/.evals/evals
    [2024-03-26 19:44:43,635] [oaieval.py:189] Run started: 240327024443FACXGMKA
    [2024-03-26 19:44:43,663] [registry.py:257] Loading registry from /Users/shyamal/.virtualenvs/openai/lib/python3.11/site-packages/evals/registry/modelgraded
    [2024-03-26 19:44:43,851] [registry.py:257] Loading registry from /Users/shyamal/.evals/modelgraded
    [2024-03-26 19:44:43,853] [data.py:90] Fetching /Users/shyamal/.virtualenvs/openai/lib/python3.11/site-packages/evals/registry/data/sql/spider_sql.jsonl
    [2024-03-26 19:44:43,878] [eval.py:36] Evaluating 25 samples
    [2024-03-26 19:44:43,952] [eval.py:144] Running in threaded mode with 10 threads!
      0%|                                                    | 0/25 [00:00<?, ?it/s][2024-03-26 19:44:44,810] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:44,829] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:44,991] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:45,090] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:45,145] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:45,971] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:46,040] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:46,069] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:46,378] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:46,587] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:47,412] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
      4%|█▊                                          | 1/25 [00:03<01:23,  3.46s/it][2024-03-26 19:44:47,714] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
      8%|███▌                                        | 2/25 [00:03<00:36,  1.60s/it][2024-03-26 19:44:47,947] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     12%|█████▎                                      | 3/25 [00:03<00:21,  1.02it/s][2024-03-26 19:44:48,413] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:48,643] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     16%|███████                                     | 4/25 [00:04<00:18,  1.15it/s][2024-03-26 19:44:48,909] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     20%|████████▊                                   | 5/25 [00:04<00:12,  1.54it/s][2024-03-26 19:44:49,131] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:49,500] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:49,530] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     24%|██████████▌                                 | 6/25 [00:05<00:12,  1.56it/s][2024-03-26 19:44:49,962] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:49,964] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:49,967] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     28%|████████████▎                               | 7/25 [00:06<00:10,  1.73it/s][2024-03-26 19:44:50,577] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:50,602] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:50,634] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:50,862] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:51,503] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:51,608] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     40%|█████████████████▏                         | 10/25 [00:07<00:08,  1.79it/s][2024-03-26 19:44:51,801] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
     44%|██████████████████▉                        | 11/25 [00:07<00:06,  2.09it/s][2024-03-26 19:44:51,856] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:51,969] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    [2024-03-26 19:44:52,227] [_client.py:1026] HTTP Request: POST https://api.openai.com/v1/chat/completions "HTTP/1.1 200 OK"
    ... (省略 25 行)
    ```

`oaievalset` 需要一個模型名稱和一個 eval set 名稱，有效的選項定義在 `evals/registry/eval_sets` 底下的 YAML 檔。

### 查看 eval log

eval log 放在 `/tmp/evallogs`，每次跑 eval 都會產生一個獨立的 log 檔。

```python
log_name = '240327024443FACXGMKA_gpt-3.5-turbo_spider-sql.jsonl' # "EDIT THIS" - copy from above
events = f"/tmp/evallogs/{log_name}"
display(pd.read_json(events, lines=True).head(5))
```

??? note "輸出"

    ```text
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       spec  \
    0  {'completion_fns': ['gpt-3.5-turbo'], 'eval_name': 'spider-sql.dev.v0', 'base_eval': 'spider-sql', 'split': 'dev', 'run_config': {'completion_fns': ['gpt-3.5-turbo'], 'eval_spec': {'cls': 'evals.elsuite.modelgraded.classify:ModelBasedClassify', 'registry_path': '/Users/shyamal/.virtualenvs/openai/lib/python3.11/site-packages/evals/registry', 'args': {'samples_jsonl': 'sql/spider_sql.jsonl', 'eval_type': 'cot_classify', 'modelgraded_spec': 'sql'}, 'key': 'spider-sql.dev.v0', 'group': 'sql'}, 'seed': 20220722, 'max_samples': 25, 'command': '/Users/shyamal/.virtualenvs/openai/bin/oaieval gpt-3.5-turbo spider-sql --max_samples 25', 'initial_settings': {'visible': False}}, 'created_by': '', 'run_id': '240327024443FACXGMKA', 'created_at': '2024-03-27 02:44:43.626043'}   
    1                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   NaN   
    2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   NaN   
    3                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   NaN   
    4                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   NaN   

                                                      final_report  \
    0                                                          NaN   
    1  {'counts/Correct': 20, 'counts/Incorrect': 5, 'score': 0.8}   
    2                                                          NaN   
    3                                                          NaN   
    4                                                          NaN   

                     run_id  event_id          sample_id      type  \
    0                   NaN       NaN                NaN       NaN   
    1                   NaN       NaN                NaN       NaN   
    2  240327024443FACXGMKA       0.0  spider-sql.dev.88  sampling   
    3  240327024443FACXGMKA       1.0  spider-sql.dev.82  sampling   
    4  240327024443FACXGMKA       2.0  spider-sql.dev.25  sampling   

                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               data  \
    0                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           NaN   
    1                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           NaN   
    2  {'prompt': [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.
    Use only the following tables and columns:
    Table: players. Columns: player_id (number), first_name (text), last_name (text), hand (text), birth_date (time), country_code (text)
    Table: matches. Columns: best_of (number), draw_size (number), loser_age (number), loser_entry (text), loser_hand (text), loser_ht (number), loser_id (number), loser_ioc (text), loser_name (text), loser_rank (number), loser_rank_points (number), loser_seed (number), match_num (number), minutes (number), round (text), score (text), surface (text), tourney_date (time), tourney_id (text), tourney_level (text), tourney_name (text), winner_age (number), winner_entry (text), winner_hand (text), winner_ht (number), winner_id (number), winner_ioc (text), winner_name (text), winner_rank (number), winner_rank_points (number), winner_seed (number), year (number)
    Table: rankings. Columns: ranking_date (time), ranking (number), player_id (number), ranking_points (number), tours (number)

    Question: Find the average rank of winners in all matches.
    ', 'role': 'system'}], 'sampled': ['SELECT AVG(winner_rank) AS average_rank_of_winners
    FROM matches;']}   
    3                                   {'prompt': [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.
    Use only the following tables and columns:
    Table: players. Columns: player_id (number), first_name (text), last_name (text), hand (text), birth_date (time), country_code (text)
    Table: matches. Columns: best_of (number), draw_size (number), loser_age (number), loser_entry (text), loser_hand (text), loser_ht (number), loser_id (number), loser_ioc (text), loser_name (text), loser_rank (number), loser_rank_points (number), loser_seed (number), match_num (number), minutes (number), round (text), score (text), surface (text), tourney_date (time), tourney_id (text), tourney_level (text), tourney_name (text), winner_age (number), winner_entry (text), winner_hand (text), winner_ht (number), winner_id (number), winner_ioc (text), winner_name (text), winner_rank (number), winner_rank_points (number), winner_seed (number), year (number)
    Table: rankings. Columns: ranking_date (time), ranking (number), player_id (number), ranking_points (number), tours (number)

    Question: Find the total number of matches.
    ... (省略 21 行)
    ```

```python
# processing the log events generated by oaieval

with open(events, "r") as f:
    events_df = pd.read_json(f, lines=True)
```

這個檔案裡是 eval 的結構化 log。第一筆記錄詳細描述了這次 eval 的規格，包括 completion function、eval 名稱、執行設定、建立者名稱、run ID 和建立時間。

```python
display(events_df.iloc[0].spec)
```

??? note "輸出"

    ```text
    {'completion_fns': ['gpt-3.5-turbo'],
     'eval_name': 'spider-sql.dev.v0',
     'base_eval': 'spider-sql',
     'split': 'dev',
     'run_config': {'completion_fns': ['gpt-3.5-turbo'],
      'eval_spec': {'cls': 'evals.elsuite.modelgraded.classify:ModelBasedClassify',
       'registry_path': '/Users/shyamal/.virtualenvs/openai/lib/python3.11/site-packages/evals/registry',
       'args': {'samples_jsonl': 'sql/spider_sql.jsonl',
        'eval_type': 'cot_classify',
        'modelgraded_spec': 'sql'},
       'key': 'spider-sql.dev.v0',
       'group': 'sql'},
      'seed': 20220722,
      'max_samples': 25,
      'command': '/Users/shyamal/.virtualenvs/openai/bin/oaieval gpt-3.5-turbo spider-sql --max_samples 25',
      'initial_settings': {'visible': False}},
     'created_by': '',
     'run_id': '240327024443FACXGMKA',
     'created_at': '2024-03-27 02:44:43.626043'}
    ```

再來看提供最終報告的那筆記錄。

```python
display(events_df.dropna(subset=['final_report']).iloc[0]['final_report'])
```

??? note "輸出"

    ```text
    {'counts/Correct': 20, 'counts/Incorrect': 5, 'score': 0.8}
    ```

我們也可以看個別的 eval event，裡面有各個 sample（`sample_id`）、結果、event 類型和 metadata。

```python
pd.set_option('display.max_colwidth', None)  # None means no truncation
display(events_df.iloc[2][['run_id', 'event_id', 'sample_id', 'type', 'data', 'created_at']])
```

??? note "輸出"

    ```text
    run_id                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                240327024443FACXGMKA
    event_id                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               0.0
    sample_id                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                spider-sql.dev.88
    type                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              sampling
    data          {'prompt': [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.
    Use only the following tables and columns:
    Table: players. Columns: player_id (number), first_name (text), last_name (text), hand (text), birth_date (time), country_code (text)
    Table: matches. Columns: best_of (number), draw_size (number), loser_age (number), loser_entry (text), loser_hand (text), loser_ht (number), loser_id (number), loser_ioc (text), loser_name (text), loser_rank (number), loser_rank_points (number), loser_seed (number), match_num (number), minutes (number), round (text), score (text), surface (text), tourney_date (time), tourney_id (text), tourney_level (text), tourney_name (text), winner_age (number), winner_entry (text), winner_hand (text), winner_ht (number), winner_id (number), winner_ioc (text), winner_name (text), winner_rank (number), winner_rank_points (number), winner_seed (number), year (number)
    Table: rankings. Columns: ranking_date (time), ranking (number), player_id (number), ranking_points (number), tours (number)

    Question: Find the average rank of winners in all matches.
    ', 'role': 'system'}], 'sampled': ['SELECT AVG(winner_rank) AS average_rank_of_winners
    FROM matches;']}
    created_at                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                2024-03-27 02:44:44.821110+00:00
    Name: 2, dtype: object
    ```

```python
# Inspect samples
for i, row in events_df[events_df['type'] == 'sampling'].head(5).iterrows():
    data = pd.json_normalize(row['data'])
    print(f"Prompt: {data['prompt'].iloc[0]}")
    print(f"Sampled: {data['sampled'].iloc[0]}")
    print("-" * 10)
```

??? note "輸出"

    ````text
    Prompt: [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.\nUse only the following tables and columns:\nTable: players. Columns: player_id (number), first_name (text), last_name (text), hand (text), birth_date (time), country_code (text)\nTable: matches. Columns: best_of (number), draw_size (number), loser_age (number), loser_entry (text), loser_hand (text), loser_ht (number), loser_id (number), loser_ioc (text), loser_name (text), loser_rank (number), loser_rank_points (number), loser_seed (number), match_num (number), minutes (number), round (text), score (text), surface (text), tourney_date (time), tourney_id (text), tourney_level (text), tourney_name (text), winner_age (number), winner_entry (text), winner_hand (text), winner_ht (number), winner_id (number), winner_ioc (text), winner_name (text), winner_rank (number), winner_rank_points (number), winner_seed (number), year (number)\nTable: rankings. Columns: ranking_date (time), ranking (number), player_id (number), ranking_points (number), tours (number)\n\nQuestion: Find the average rank of winners in all matches.\n', 'role': 'system'}]
    Sampled: ['SELECT AVG(winner_rank) AS average_rank_of_winners\nFROM matches;']
    ----------
    Prompt: [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.\nUse only the following tables and columns:\nTable: players. Columns: player_id (number), first_name (text), last_name (text), hand (text), birth_date (time), country_code (text)\nTable: matches. Columns: best_of (number), draw_size (number), loser_age (number), loser_entry (text), loser_hand (text), loser_ht (number), loser_id (number), loser_ioc (text), loser_name (text), loser_rank (number), loser_rank_points (number), loser_seed (number), match_num (number), minutes (number), round (text), score (text), surface (text), tourney_date (time), tourney_id (text), tourney_level (text), tourney_name (text), winner_age (number), winner_entry (text), winner_hand (text), winner_ht (number), winner_id (number), winner_ioc (text), winner_name (text), winner_rank (number), winner_rank_points (number), winner_seed (number), year (number)\nTable: rankings. Columns: ranking_date (time), ranking (number), player_id (number), ranking_points (number), tours (number)\n\nQuestion: Find the total number of matches.\n', 'role': 'system'}]
    Sampled: ['SELECT COUNT(*) AS total_matches\nFROM matches;']
    ----------
    Prompt: [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.\nUse only the following tables and columns:\nTable: continents. Columns: ContId (number), Continent (text)\nTable: countries. Columns: CountryId (number), CountryName (text), Continent (number)\nTable: car_makers. Columns: Id (number), Maker (text), FullName (text), Country (text)\nTable: model_list. Columns: ModelId (number), Maker (number), Model (text)\nTable: car_names. Columns: MakeId (number), Model (text), Make (text)\nTable: cars_data. Columns: Id (number), MPG (text), Cylinders (number), Edispl (number), Horsepower (text), Weight (number), Accelerate (number), Year (number)\n\nQuestion: How many countries exist?\n', 'role': 'system'}]
    Sampled: ['SELECT COUNT(*) AS TotalCountries\nFROM countries;']
    ----------
    Prompt: [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.\nUse only the following tables and columns:\nTable: TV_Channel. Columns: id (text), series_name (text), Country (text), Language (text), Content (text), Pixel_aspect_ratio_PAR (text), Hight_definition_TV (text), Pay_per_view_PPV (text), Package_Option (text)\nTable: TV_series. Columns: id (number), Episode (text), Air_Date (text), Rating (text), Share (number), 18_49_Rating_Share (text), Viewers_m (text), Weekly_Rank (number), Channel (text)\nTable: Cartoon. Columns: id (number), Title (text), Directed_by (text), Written_by (text), Original_air_date (text), Production_code (number), Channel (text)\n\nQuestion: What is the name and directors of all the cartoons that are ordered by air date?\n', 'role': 'system'}]
    Sampled: ['SELECT Title, Directed_by\nFROM Cartoon\nORDER BY Original_air_date;']
    ----------
    Prompt: [{'content': 'Answer the following question with syntactically correct SQLite SQL. Be creative but the SQL must be correct.\nUse only the following tables and columns:\nTable: stadium. Columns: Stadium_ID (number), Location (text), Name (text), Capacity (number), Highest (number), Lowest (number), Average (number)\nTable: singer. Columns: Singer_ID (number), Name (text), Country (text), Song_Name (text), Song_release_year (text), Age (number), Is_male (others)\nTable: concert. Columns: concert_ID (number), concert_Name (text), Theme (text), Stadium_ID (text), Year (text)\nTable: singer_in_concert. Columns: concert_ID (number), Singer_ID (text)\n\nQuestion: Show the name and the release year of the song by the youngest singer.\n', 'role': 'system'}]
    Sampled: ['```sql\nSELECT s.Name, s.Song_release_year\nFROM singer s\nWHERE s.Age = (SELECT MIN(Age) FROM singer)\n```']
    ----------
    ````

接著看失敗的案例，了解哪些測試沒過。

````python
def pretty_print_text(prompt):
    # Define markers for the sections
    markers = {
        "question": "[Question]:",
        "expert": "[Expert]:",
        "submission": "[Submission]:",
        "end": "[END DATA]"
    }
    
    # Function to extract text between markers
    def extract_text(start_marker, end_marker):
        start = prompt.find(start_marker) + len(start_marker)
        end = prompt.find(end_marker)
        text = prompt[start:end].strip()
        if start_marker == markers["question"]:
            text = text.split("\n\nQuestion:")[-1].strip() if "\n\nQuestion:" in text else text
        elif start_marker == markers["submission"]:
            text = text.replace("```sql", "").replace("```", "").strip()
        return text
    
    # Extracting text for each section
    question_text = extract_text(markers["question"], markers["expert"])
    expert_text = extract_text(markers["expert"], markers["submission"])
    submission_text = extract_text(markers["submission"], markers["end"])
    
    # HTML color codes and formatting
    colors = {
        "question": '<span style="color: #0000FF;">QUESTION:<br>', 
        "expert": '<span style="color: #008000;">EXPECTED:<br>',  
        "submission": '<span style="color: #FFA500;">SUBMISSION:<br>' 
    }
    color_end = '</span>'
    
    # Display each section with color
    from IPython.display import display, HTML
    display(HTML(f"{colors['question']}{question_text}{color_end}"))
    display(HTML(f"{colors['expert']}{expert_text}{color_end}"))
    display(HTML(f"{colors['submission']}{submission_text}{color_end}"))
````

```python
# Inspect metrics where choice is made and print only the prompt, result, and expected result if the choice is incorrect
for i, row in events_df[events_df['type'] == 'metrics'].iterrows():
    if row['data']['choice'] == 'Incorrect':
        # Get the previous row's data, which contains the prompt and the expected result
        prev_row = events_df.iloc[i-1]
        prompt = prev_row['data']['prompt'][0]['content'] if 'prompt' in prev_row['data'] and len(prev_row['data']['prompt']) > 0 else "Prompt not available"
        expected_result = prev_row['data'].get('ideal', 'Expected result not provided')
        
        # Current row's data will be the actual result
        result = row['data'].get('result', 'Actual result not provided')
        
        pretty_print_text(prompt)
        print("-" * 40)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    ----------------------------------------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    ----------------------------------------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    ----------------------------------------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    ----------------------------------------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    ----------------------------------------
    ```

看了一些失敗案例，我們發現：
* 第二個錯誤答案多做了一個不必要的 `Templates` 資料表 join，eval 正確辨識出來並標為錯誤。
* 其他幾個答案只是語法上有小差異，就被標成錯。
  * 碰到這種情況，值得想想是要繼續調整 prompt 來固定某些寫法風格，還是要修改評估套件，把這類差異算進去。
  * 這種失敗也暗示可能需要 model-graded eval，才能準確評分。

# 結論

建立有效的 eval 是開發 LLM 應用的核心環節。OpenAI Evals 框架提供了現成的 eval 建構架構，讓你可以很快為不同使用情境開出新測試。這篇一步一步示範了怎麼建 eval、跑 eval、分析結果。

這篇的例子是 eval 很單純的用法。接著用這個框架時，建議針對實際的 production 情境，去做更複雜的 model-graded eval。祝評估順利！

## 重點整理

- eval 的本質是「輸入 + 理想答案 + 評分方式」，換模型或改 prompt 時它是你的回歸測試。
- 答案變化小就用 basic 模板（match、includes、fuzzyMatch），答案開放就用 model-graded，而且最好用不同模型來評分。
- eval 資料集是 `jsonl`，每筆有 prompt 跟 ideal answer，再用 YAML 註冊到 registry 才能被 `oaieval` 找到。
- 失敗案例要看，因為有時是模型真的錯，有時只是比對規則太死，這時該改的是評分方式。

## 練習

1. 把 YAML 裡的 metric 換成另一種（例如 match 換成 includes），重跑 eval，看準確率和失敗案例怎麼變。
2. 用 `GPT-4` 再生成一批不同資料表的 SQL 樣本，轉成 `jsonl` 加進資料集，跑跑看。
3. 挑一個因為語法小差異被判錯的 sample，想辦法讓它能算對，例如改 prompt 固定寫法，或改用 model-graded 模板評分。
