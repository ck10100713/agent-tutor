---
translated: true
source: tool_use/extracting_structured_json.ipynb
---

# 用 Claude 和 tool use 擷取結構化 JSON

> 原文：[tool_use/extracting_structured_json.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/extracting_structured_json.ipynb)

用 Claude 的 tool use 能力，從各種輸入擷取結構化的 JSON 資料。

## 這篇在做什麼

定義自訂 tool，讓 Claude 對不同類型的輸入輸出格式良好的 JSON，涵蓋摘要、實體擷取、情緒分析、文字分類，以及 schema 事先未知的情況。

## 學完你會

- 設計 `input_schema`，讓 Claude 以 tool 呼叫的形式輸出結構化 JSON。
- 用同樣的手法做摘要、NER、情緒分析和文字分類。
- 用開放式的 schema 處理事先不知道 key 的情況。

## 開跑前

需要 Anthropic API key。

這份 cookbook 會看各種用 Claude 和 tool use 功能，從不同類型的輸入擷取結構化 JSON 資料的例子。我們會定義自訂 tool，讓 Claude 為摘要、實體擷取、情緒分析等任務產生格式良好的 JSON 輸出。

如果你想取得結構化 JSON 資料但不用 tool，可以看我們的「[How to enable JSON mode](https://github.com/anthropics/anthropic-cookbook/blob/main/misc/how_to_enable_json_mode.ipynb)」cookbook。

## 設定環境

先安裝需要的函式庫並設定 Claude API client。

```python
%pip install anthropic requests beautifulsoup4
```

```python
import json

import requests
from anthropic import Anthropic
from bs4 import BeautifulSoup

client = Anthropic()
MODEL_NAME = "claude-haiku-5-5"
```

## 範例 1：文章摘要

這個範例用 Claude 產生一篇文章的 JSON 摘要，欄位包括作者、主題、摘要、連貫性分數、說服力分數和反方論點。

```python
tools = [
    {
        "name": "print_summary",
        "description": "Prints a summary of the article.",
        "input_schema": {
            "type": "object",
            "properties": {
                "author": {"type": "string", "description": "Name of the article author"},
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": 'Array of topics, e.g. ["tech", "politics"]. Should be as specific as possible, and can overlap.',
                },
                "summary": {
                    "type": "string",
                    "description": "Summary of the article. One or two paragraphs max.",
                },
                "coherence": {
                    "type": "integer",
                    "description": "Coherence of the article's key points, 0-100 (inclusive)",
                },
                "persuasion": {
                    "type": "number",
                    "description": "Article's persuasion score, 0.0-1.0 (inclusive)",
                },
            },
            "required": ["author", "topics", "summary", "coherence", "persuasion", "counterpoint"],
        },
    }
]

url = "https://www.anthropic.com/news/third-party-testing"
response = requests.get(url, timeout=30)
soup = BeautifulSoup(response.text, "html.parser")
article = " ".join([p.text for p in soup.find_all("p")])

query = f"""
<article>
{article}
</article>

Use the `print_summary` tool.
"""

response = client.messages.create(
    model=MODEL_NAME, max_tokens=4096, tools=tools, messages=[{"role": "user", "content": query}]
)
json_summary = None
for content in response.content:
    if content.type == "tool_use" and content.name == "print_summary":
        json_summary = content.input
        break

if json_summary:
    print("JSON Summary:")
    print(json.dumps(json_summary, indent=2))
else:
    print("No JSON summary found in the response.")
```

??? note "輸出"

    ```text
    JSON Summary:
    {
      "author": "Anthropic",
      "topics": [
        "AI policy",
        "AI safety",
        "third-party testing",
        "AI regulation",
        "national security",
        "regulatory capture",
        "open-weight models",
        "AI evaluation"
      ],
      "summary": "Anthropic argues that the AI sector needs an effective third-party testing regime for frontier AI systems, and that this regime should be developed through collaboration among industry, government, and academia. The company says such testing is needed to address issues like election integrity, harmful discrimination, and national security misuse, and that more capable future systems will require more expansive oversight. Anthropic expects that some form of third-party testing will eventually be a legal requirement for widely deploying AI models. It favors prototyping testing regimes now, since the standards, testers, and market structure are not yet clear. The post notes that frontier models are general-purpose \"everything machines\" whose downstream behavior inherits their capabilities and weaknesses, so existing sector-specific rules fit poorly. It cites precedents in food, medicine, automobiles, and aerospace, and proposes that national-security-relevant capabilities, such as meaningful uplift for bioweapons or complex cyberattacks, be tested first, with possible responses including removing capabilities, gating them behind know-your-customer checks, or notifying government agencies.\n\nThe post also describes Anthropic's Responsible Scaling Policy as a self-governance step, but argues that self-governance by single companies is insufficient and that testing must be broadly trusted and apply to all frontier developers. It addresses open-weight models and regulatory capture, acknowledging these as contested issues, and advocates a \"minimal viable policy\" because regulations tend to be hard to remove once passed. Specific policy asks include more government funding for AI evaluation, public-sector research infrastructure, tests for national-security capabilities, and scenario planning for advanced systems. The post ends with updates on Anthropic's testing collaborations (including METR and talks with Hugging Face), election safeguards, and a Singapore office, some of which are only loosely connected to the main argument.",
      "coherence": 70,
      "persuasion": 0.7,
      "counterpoint": "The author is a frontier AI developer advocating for a regime that could raise compliance costs and favor well-resourced incumbents, which the post itself only partly addresses. Its proposals rely on testing methods that may not accurately measure safety, and the post offers little evidence that the proposed tests work. Open-weight advocates and smaller developers would likely argue that mandatory testing and licensing would entrench large players and limit open research. The post's list of required ingredients and responsible testers is also left incomplete, and its closing updates on elections and a Singapore office are unrelated to the core policy argument."
    }
    ```

## 範例 2：具名實體辨識
這個範例用 Claude 對給定的文字做具名實體辨識（NER），並以結構化 JSON 格式回傳實體。

```python
tools = [
    {
        "name": "print_entities",
        "description": "Prints extract named entities.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "The extracted entity name."},
                            "type": {
                                "type": "string",
                                "description": "The entity type (e.g., PERSON, ORGANIZATION, LOCATION).",
                            },
                            "context": {
                                "type": "string",
                                "description": "The context in which the entity appears in the text.",
                            },
                        },
                        "required": ["name", "type", "context"],
                    },
                }
            },
            "required": ["entities"],
        },
    }
]

text = "John works at Google in New York. He met with Sarah, the CEO of Acme Inc., last week in San Francisco."

query = f"""
<document>
{text}
</document>

Use the print_entities tool.
"""

response = client.messages.create(
    model=MODEL_NAME, max_tokens=4096, tools=tools, messages=[{"role": "user", "content": query}]
)

json_entities = None
for content in response.content:
    if content.type == "tool_use" and content.name == "print_entities":
        json_entities = content.input
        break

if json_entities:
    print("Extracted Entities (JSON):")
    print(json_entities)
else:
    print("No entities found in the response.")
```

??? note "輸出"

    ```text
    Extracted Entities (JSON):
    {'entities': [{'name': 'John', 'type': 'PERSON', 'context': 'John works at Google in New York.'}, {'name': 'Google', 'type': 'ORGANIZATION', 'context': 'John works at Google in New York.'}, {'name': 'New York', 'type': 'LOCATION', 'context': 'John works at Google in New York.'}, {'name': 'Sarah', 'type': 'PERSON', 'context': 'He met with Sarah, the CEO of Acme Inc., last week in San Francisco.'}, {'name': 'Acme Inc.', 'type': 'ORGANIZATION', 'context': 'He met with Sarah, the CEO of Acme Inc., last week in San Francisco.'}, {'name': 'San Francisco', 'type': 'LOCATION', 'context': 'He met with Sarah, the CEO of Acme Inc., last week in San Francisco.'}]}
    ```

## 範例 3：情緒分析
這個範例用 Claude 對給定的文字做情緒分析，並以結構化 JSON 格式回傳情緒分數。

```python
tools = [
    {
        "name": "print_sentiment_scores",
        "description": "Prints the sentiment scores of a given text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "positive_score": {
                    "type": "number",
                    "description": "The positive sentiment score, ranging from 0.0 to 1.0.",
                },
                "negative_score": {
                    "type": "number",
                    "description": "The negative sentiment score, ranging from 0.0 to 1.0.",
                },
                "neutral_score": {
                    "type": "number",
                    "description": "The neutral sentiment score, ranging from 0.0 to 1.0.",
                },
            },
            "required": ["positive_score", "negative_score", "neutral_score"],
        },
    }
]

text = "The product was okay, but the customer service was terrible. I probably won't buy from them again."

query = f"""
<text>
{text}
</text>

Use the print_sentiment_scores tool.
"""

response = client.messages.create(
    model=MODEL_NAME, max_tokens=4096, tools=tools, messages=[{"role": "user", "content": query}]
)

json_sentiment = None
for content in response.content:
    if content.type == "tool_use" and content.name == "print_sentiment_scores":
        json_sentiment = content.input
        break

if json_sentiment:
    print("Sentiment Analysis (JSON):")
    print(json.dumps(json_sentiment, indent=2))
else:
    print("No sentiment analysis found in the response.")
```

??? note "輸出"

    ```text
    Sentiment Analysis (JSON):
    {
      "positive_score": 0.1,
      "negative_score": 0.7,
      "neutral_score": 0.2
    }
    ```

## 範例 4：文字分類
這個範例用 Claude 把給定的文字分到預先定義的類別，並以結構化 JSON 格式回傳分類結果。

```python
tools = [
    {
        "name": "print_classification",
        "description": "Prints the classification results.",
        "input_schema": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "The category name."},
                            "score": {
                                "type": "number",
                                "description": "The classification score for the category, ranging from 0.0 to 1.0.",
                            },
                        },
                        "required": ["name", "score"],
                    },
                }
            },
            "required": ["categories"],
        },
    }
]

text = "The new quantum computing breakthrough could revolutionize the tech industry."

query = f"""
<document>
{text}
</document>

Use the print_classification tool. The categories can be Politics, Sports, Technology, Entertainment, Business.
"""

response = client.messages.create(
    model=MODEL_NAME, max_tokens=4096, tools=tools, messages=[{"role": "user", "content": query}]
)

json_classification = None
for content in response.content:
    if content.type == "tool_use" and content.name == "print_classification":
        json_classification = content.input
        break

if json_classification:
    print("Text Classification (JSON):")
    print(json.dumps(json_classification, indent=2))
else:
    print("No text classification found in the response.")
```

??? note "輸出"

    ```text
    Text Classification (JSON):
    {
      "categories": [
        {
          "name": "Technology",
          "score": 0.95
        },
        {
          "name": "Business",
          "score": 0.3
        },
        {
          "name": "Politics",
          "score": 0.02
        },
        {
          "name": "Sports",
          "score": 0.01
        },
        {
          "name": "Entertainment",
          "score": 0.02
        }
      ]
    }
    ```

## 範例 5：處理未知的 key

有些情況下，你事先不知道 JSON 物件的確切形狀。這個範例提供一個開放式的 `input_schema`，並透過 prompt 指示 Claude 如何使用這個 tool。

```python
tools = [
    {
        "name": "print_all_characteristics",
        "description": "Prints all characteristics which are provided.",
        "input_schema": {"type": "object", "additionalProperties": True},
    }
]

query = """Given a description of a character, your task is to extract all the characteristics of the character and print them using the print_all_characteristics tool.

The print_all_characteristics tool takes an arbitrary number of inputs where the key is the characteristic name and the value is the characteristic value (age: 28 or eye_color: green).

<description>
The man is tall, with a beard and a scar on his left cheek. He has a deep voice and wears a black leather jacket.
</description>

Now use the print_all_characteristics tool."""

response = client.messages.create(
    model=MODEL_NAME,
    max_tokens=4096,
    tools=tools,
    tool_choice={"type": "tool", "name": "print_all_characteristics"},
    messages=[{"role": "user", "content": query}],
)

tool_output = None
for content in response.content:
    if content.type == "tool_use" and content.name == "print_all_characteristics":
        tool_output = content.input
        break

if tool_output:
    print("Characteristics (JSON):")
    print(json.dumps(tool_output, indent=2))
else:
    print("Something went wrong.")
```

??? note "輸出"

    ```text
    Characteristics (JSON):
    {
      "height": "tall",
      "gender": "man",
      "facial_hair": "beard",
      "distinguishing_marks": "scar on left cheek",
      "voice": "deep",
      "clothing": "black leather jacket"
    }
    ```

這些範例示範了如何用 Claude 和 tool use 功能，為各種自然語言處理任務擷取結構化 JSON 資料。透過定義帶有特定 input schema 的自訂 tool，你可以引導 Claude 產生格式良好的 JSON 輸出，方便在你的應用程式中解析和使用。

## 重點整理
- 把 tool 的 `input_schema` 當成輸出格式的定義，Claude 填入的參數就是你要的 JSON。
- 同一招可以套用在摘要、NER、情緒分析、分類等各種擷取任務。
- 欄位的 description 和型別限制是引導輸出品質的主要手段。
- schema 不確定時可以用開放式 `input_schema`，再靠 prompt 說明怎麼使用 tool。

## 練習
1. 在摘要範例的 schema 多加一個欄位（例如 `key_quotes`），看 Claude 是否填入。
2. 把情緒分析的分數欄位改成列舉型別（positive / neutral / negative），比較輸出。
3. 在範例 5 換一段不同的文字，觀察 Claude 自行決定的 key 有什麼變化。
