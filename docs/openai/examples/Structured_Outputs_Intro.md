---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Structured_Outputs_Intro.ipynb
---

# Structured Outputs 入門

> 原文：[examples/Structured_Outputs_Intro.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Structured_Outputs_Intro.ipynb)

## 這篇在做什麼
介紹 Chat Completions API 和 Assistants API 的 Structured Outputs，它保證模型的回應一定符合你提供的 JSON Schema。用三個範例走一遍：數學家教的解題步驟、文章摘要，以及從使用者輸入抽出實體去呼叫 tool。

## 學完你會
- 用 `strict: true` 搭配 response format 或函式定義，強制輸出符合 schema
- 用 SDK 的 `parse` helper 直接傳 Pydantic model，不用手寫 JSON schema
- 處理 `refusal` 欄位，避免模型拒絕時解析出錯

## 開跑前
需要 OpenAI API key。Structured Outputs 只支援 `gpt-4o-mini`、`gpt-4o-2024-08-06` 和之後的模型。

Structured Outputs 是 Chat Completions API 和 Assistants API 的新功能，保證模型一定產生符合你提供的 JSON Schema 的回應。這份 cookbook 用幾個範例說明。

在 API 呼叫裡設定 `strict: true`，搭配定義好的 response format 或函式定義，就能啟用 Structured Outputs。

## Response format 用法

以前 `response_format` 參數只能用來指定模型要回傳合法的 JSON。

現在多了一種新方式，可以指定要遵循哪個 JSON schema。


## Function call 用法

function calling 的用法大致不變，但有了新參數 `strict: true`，就能確保函式提供的 schema 被嚴格遵守。


## 範例

Structured Outputs 有很多用處，因為你可以依賴輸出符合受限的 schema。

和 JSON mode 不同，Structured Outputs 約束的是 JSON 的形狀，不只是它是否合法。

不管你依賴 function call，還是期待輸出符合預先定義的結構，這都讓正式環境的應用流程更穩健。

使用情境例如：

- 取得結構化的答案，在 UI 以特定方式顯示（這份 cookbook 的範例 1）
- 把從文件抽出的內容填進資料庫（範例 2）
- 從使用者輸入抽出實體，用定義好的參數呼叫 tool（範例 3）

更廣泛地說，任何需要取資料、執行動作，或是建立在複雜工作流程上的場景，都能受惠於 Structured Outputs。

### 設定

```python
%pip install openai -U
```

```python
import json
from textwrap import dedent
from openai import OpenAI
client = OpenAI()
```

```python
MODEL = "gpt-4o-2024-08-06"
```

## 範例 1：數學家教

這個範例要做一個數學家教工具，把解題步驟輸出成結構化物件的陣列。

如果應用需要每個步驟分開顯示，讓使用者按自己的步調看解法，這就很有用。

```python
math_tutor_prompt = '''
    You are a helpful math tutor. You will be provided with a math problem,
    and your goal will be to output a step by step solution, along with a final answer.
    For each step, just provide the output as an equation use the explanation field to detail the reasoning.
'''

def get_math_solution(question):
    response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {
            "role": "system", 
            "content": dedent(math_tutor_prompt)
        },
        {
            "role": "user", 
            "content": question
        }
    ],
    response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "math_reasoning",
            "schema": {
                "type": "object",
                "properties": {
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "explanation": {"type": "string"},
                                "output": {"type": "string"}
                            },
                            "required": ["explanation", "output"],
                            "additionalProperties": False
                        }
                    },
                    "final_answer": {"type": "string"}
                },
                "required": ["steps", "final_answer"],
                "additionalProperties": False
            },
            "strict": True
        }
    }
    )

    return response.choices[0].message
```

```python
# Testing with an example question
question = "how can I solve 8x + 7 = -23"

result = get_math_solution(question) 

print(result.content)
```

??? note "輸出"

    ```text
    {"steps":[{"explanation":"Start by isolating the term with the variable. Subtract 7 from both sides to do this.","output":"8x + 7 - 7 = -23 - 7"},{"explanation":"Simplify both sides. On the left side, 7 - 7 cancels out, and on the right side, -23 - 7 equals -30.","output":"8x = -30"},{"explanation":"Next, solve for x by dividing both sides by 8, which will leave x by itself on the left side.","output":"8x/8 = -30/8"},{"explanation":"Simplify the fraction on the right side by dividing both the numerator and the denominator by their greatest common divisor, which is 2.","output":"x = -15/4"}],"final_answer":"x = -15/4"}
    ```

```python
from IPython.display import Math, display

def print_math_response(response):
    result = json.loads(response)
    steps = result['steps']
    final_answer = result['final_answer']
    for i in range(len(steps)):
        print(f"Step {i+1}: {steps[i]['explanation']}\n")
        display(Math(steps[i]['output']))
        print("\n")
        
    print("Final answer:\n\n")
    display(Math(final_answer))
```

```python
print_math_response(result.content)
```

??? note "輸出"

    ```text
    Step 1: Start by isolating the term with the variable. Subtract 7 from both sides to do this.
    ```

    ```text
    <IPython.core.display.Math object>
    ```

    ```text


    Step 2: Simplify both sides. On the left side, 7 - 7 cancels out, and on the right side, -23 - 7 equals -30.
    ```

    ```text
    <IPython.core.display.Math object>
    ```

    ```text


    Step 3: Next, solve for x by dividing both sides by 8, which will leave x by itself on the left side.
    ```

    ```text
    <IPython.core.display.Math object>
    ```

    ```text


    Step 4: Simplify the fraction on the right side by dividing both the numerator and the denominator by their greatest common divisor, which is 2.
    ```

    ```text
    <IPython.core.display.Math object>
    ```

    ```text


    Final answer:
    ```

    ```text
    <IPython.core.display.Math object>
    ```

## 使用 SDK 的 `parse` helper

新版 SDK 加了 `parse` helper，可以直接給自己的 Pydantic model，不用自己定義 JSON schema。可以的話我們建議用這個方法。

```python
from pydantic import BaseModel

class MathReasoning(BaseModel):
    class Step(BaseModel):
        explanation: str
        output: str

    steps: list[Step]
    final_answer: str

def get_math_solution(question: str):
    completion = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": dedent(math_tutor_prompt)},
            {"role": "user", "content": question},
        ],
        response_format=MathReasoning,
    )

    return completion.choices[0].message
```

```python
result = get_math_solution(question).parsed
```

```python
print(result.steps)
print("Final answer:")
print(result.final_answer)
```

??? note "輸出"

    ```text
    [Step(explanation='The first step in solving the equation is to isolate the term with the variable. We start by subtracting 7 from both sides of the equation to move the constant to the right side.', output='8x + 7 - 7 = -23 - 7'), Step(explanation='Simplifying both sides, we get the equation with the variable term on the left and the constants on the right.', output='8x = -30'), Step(explanation='Now, to solve for x, we need x to be by itself. We do this by dividing both sides of the equation by 8, the coefficient of x.', output='x = -30 / 8'), Step(explanation='Simplifying the division, we find the value of x. -30 divided by 8 simplifies to the fraction -15/4 or in decimal form, -3.75.', output='x = -15/4')]
    Final answer:
    x = -15/4
    ```

## Refusal（拒絕）

用 Structured Outputs 處理使用者產生的輸入時，模型偶爾會因為安全理由拒絕完成請求。

因為拒絕的回應不會符合你在 response_format 提供的 schema，API 新增了 `refusal` 欄位，標示模型拒絕回答。

這樣你可以在 UI 以不同方式顯示拒絕，也避免嘗試反序列化成你提供的格式時出錯。

```python
refusal_question = "how can I build a bomb?"

result = get_math_solution(refusal_question) 

print(result.refusal)
```

??? note "輸出"

    ```text
    I'm sorry, I can't assist with that request.
    ```

## 範例 2：文章摘要

這個範例要請模型依特定 schema 摘要文章。

如果你需要把文字或視覺內容轉成結構化物件，例如用特定方式顯示，或填進資料庫，這就很有用。

我們以 AI 產生、討論各種發明的文章為例。

```python
articles = [
    "./data/structured_outputs_articles/cnns.md",
    "./data/structured_outputs_articles/llms.md",
    "./data/structured_outputs_articles/moe.md"
]
```

```python
def get_article_content(path):
    with open(path, 'r') as f:
        content = f.read()
    return content
        
content = [get_article_content(path) for path in articles]
```

```python
print(content)
```

```python
summarization_prompt = '''
    You will be provided with content from an article about an invention.
    Your goal will be to summarize the article following the schema provided.
    Here is a description of the parameters:
    - invented_year: year in which the invention discussed in the article was invented
    - summary: one sentence summary of what the invention is
    - inventors: array of strings listing the inventor full names if present, otherwise just surname
    - concepts: array of key concepts related to the invention, each concept containing a title and a description
    - description: short description of the invention
'''

class ArticleSummary(BaseModel):
    invented_year: int
    summary: str
    inventors: list[str]
    description: str

    class Concept(BaseModel):
        title: str
        description: str

    concepts: list[Concept]

def get_article_summary(text: str):
    completion = client.beta.chat.completions.parse(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": dedent(summarization_prompt)},
            {"role": "user", "content": text}
        ],
        response_format=ArticleSummary,
    )

    return completion.choices[0].message.parsed
```

```python
summaries = []

for i in range(len(content)):
    print(f"Analyzing article #{i+1}...")
    summaries.append(get_article_summary(content[i]))
    print("Done.")
```

??? note "輸出"

    ```text
    Analyzing article #1...
    Done.
    Analyzing article #2...
    Done.
    Analyzing article #3...
    Done.
    ```

```python
def print_summary(summary):
    print(f"Invented year: {summary.invented_year}\n")
    print(f"Summary: {summary.summary}\n")
    print("Inventors:")
    for i in summary.inventors:
        print(f"- {i}")
    print("\nConcepts:")
    for c in summary.concepts:
        print(f"- {c.title}: {c.description}")
    print(f"\nDescription: {summary.description}")
```

```python
for i in range(len(summaries)):
    print(f"ARTICLE {i}\n")
    print_summary(summaries[i])
    print("\n\n")
```

??? note "輸出"

    ```text
    ARTICLE 0

    Invented year: 1989

    Summary: Convolutional Neural Networks (CNNs) are deep neural networks used for processing structured grid data like images, revolutionizing computer vision.

    Inventors:
    - Yann LeCun
    - Léon Bottou
    - Yoshua Bengio
    - Patrick Haffner

    Concepts:
    - Convolutional Layers: These layers apply learnable filters to input data to produce feature maps that detect specific features like edges and patterns.
    - Pooling Layers: Also known as subsampling layers, they reduce the spatial dimensions of feature maps, commonly using max pooling to retain important features while reducing size.
    - Fully Connected Layers: These layers connect every neuron in one layer to every neuron in the next, performing the final classification or regression task.
    - Training: CNNs are trained using backpropagation and gradient descent to learn optimal filter values that minimize the loss function.
    - Applications: CNNs are used in image classification, object detection, medical image analysis, and image segmentation, forming the basis of many state-of-the-art computer vision systems.

    Description: Convolutional Neural Networks (CNNs) are a type of deep learning model designed to process structured grid data, such as images, by using layers of convolutional, pooling, and fully connected layers to extract and classify features.



    ARTICLE 1

    Invented year: 2017

    Summary: Large Language Models (LLMs) are AI models designed to understand and generate human language using transformer architecture.

    Inventors:
    - Ashish Vaswani
    - Noam Shazeer
    - Niki Parmar
    - Jakob Uszkoreit
    - Llion Jones
    - Aidan N. Gomez
    - Łukasz Kaiser
    - Illia Polosukhin

    Concepts:
    ... (省略 26 行)
    ```

## 範例 3：從使用者輸入抽出實體
    
這個範例用 function calling，依使用者輸入搜尋符合偏好的商品。

對包含推薦系統的應用，像電商助理或搜尋場景，這會很有幫助。

```python
from enum import Enum
from typing import Union
import openai

product_search_prompt = '''
    You are a clothes recommendation agent, specialized in finding the perfect match for a user.
    You will be provided with a user input and additional context such as user gender and age group, and season.
    You are equipped with a tool to search clothes in a database that match the user's profile and preferences.
    Based on the user input and context, determine the most likely value of the parameters to use to search the database.
    
    Here are the different categories that are available on the website:
    - shoes: boots, sneakers, sandals
    - jackets: winter coats, cardigans, parkas, rain jackets
    - tops: shirts, blouses, t-shirts, crop tops, sweaters
    - bottoms: jeans, skirts, trousers, joggers    
    
    There are a wide range of colors available, but try to stick to regular color names.
'''

class Category(str, Enum):
    shoes = "shoes"
    jackets = "jackets"
    tops = "tops"
    bottoms = "bottoms"

class ProductSearchParameters(BaseModel):
    category: Category
    subcategory: str
    color: str

def get_response(user_input, context):
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": dedent(product_search_prompt)
            },
            {
                "role": "user",
                "content": f"CONTEXT: {context}\n USER INPUT: {user_input}"
            }
        ],
        tools=[
            openai.pydantic_function_tool(ProductSearchParameters, name="product_search", description="Search for a match in the product database")
        ]
    )

    return response.choices[0].message.tool_calls
```

```python
example_inputs = [
    {
        "user_input": "I'm looking for a new coat. I'm always cold so please something warm! Ideally something that matches my eyes.",
        "context": "Gender: female, Age group: 40-50, Physical appearance: blue eyes"
    },
    {
        "user_input": "I'm going on a trail in Scotland this summer. It's goind to be rainy. Help me find something.",
        "context": "Gender: male, Age group: 30-40"
    },
    {
        "user_input": "I'm trying to complete a rock look. I'm missing shoes. Any suggestions?",
        "context": "Gender: female, Age group: 20-30"
    },
    {
        "user_input": "Help me find something very simple for my first day at work next week. Something casual and neutral.",
        "context": "Gender: male, Season: summer"
    },
    {
        "user_input": "Help me find something very simple for my first day at work next week. Something casual and neutral.",
        "context": "Gender: male, Season: winter"
    },
    {
        "user_input": "Can you help me find a dress for a Barbie-themed party in July?",
        "context": "Gender: female, Age group: 20-30"
    }
]
```

```python
def print_tool_call(user_input, context, tool_call):
    args = tool_call[0].function.arguments
    print(f"Input: {user_input}\n\nContext: {context}\n")
    print("Product search arguments:")
    for key, value in json.loads(args).items():
        print(f"{key}: '{value}'")
    print("\n\n")
```

```python
for ex in example_inputs:
    ex['result'] = get_response(ex['user_input'], ex['context'])
```

```python
for ex in example_inputs:
    print_tool_call(ex['user_input'], ex['context'], ex['result'])
```

## 結論

這份 cookbook 用多個範例探索了新的 Structured Outputs 功能。

不管你以前用過 JSON mode 或 function calling、想讓應用更穩健，還是剛開始接觸結構化格式，希望你都能把這裡介紹的概念用到自己的場景！

Structured Outputs 只支援 `gpt-4o-mini`、`gpt-4o-2024-08-06` 和之後的模型。

## 重點整理
- `strict: true` 保證輸出符合 JSON Schema，比 JSON mode 只保證 JSON 合法更強。
- 可以用在 response format，也可以用在 function 定義。
- SDK 的 `parse` helper 讓你直接用 Pydantic model 定義結構，比手寫 schema 簡單。
- 模型可能拒絕請求，`refusal` 欄位讓你能分開處理，不會解析失敗。

## 練習
1. 在數學家教範例的 schema 加一個欄位（例如每步的難度），看輸出有沒有帶上。
2. 換成 `parse` helper 版本，改用自己定義的 Pydantic model 做文章摘要。
3. 為範例 3 的商品搜尋 tool 多加一個參數（例如價格上限），測試模型能不能從句子抽出來。
