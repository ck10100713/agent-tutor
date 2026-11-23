---
translated: true
source: examples/o1/Using_chained_calls_for_o1_structured_outputs.ipynb
---

# 用串接呼叫讓 o1 輸出 structured output

> 原文：[examples/o1/Using_chained_calls_for_o1_structured_outputs.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/o1/Using_chained_calls_for_o1_structured_outputs.ipynb)



## 這篇在做什麼

最初發布的 o1 reasoning 模型（2024 年 9 月）不支援 structured outputs。這篇示範兩種方式讓 `o1-preview` 回傳有效的 JSON：直接在 prompt 裡要求，以及把 o1 的回應接給 `gpt-4o-mini`，用它的 structured outputs 功能整理格式。

## 學完你會

- 用 prompt 讓 `o1-preview` 回傳 JSON，並知道它的限制
- 把 `o1-preview` 的輸出串到 `gpt-4o-mini`，取得符合 schema 的結果
- 判斷什麼時候值得多花一次呼叫換型別安全

## 開跑前

- OpenAI API key，帳號能使用 `o1-preview` 和 `gpt-4o-mini`

最初發布的版本（2024 年 9 月）的 [o1](https://openai.com/index/introducing-openai-o1-preview/) reasoning 模型能力很強，但不支援 [structured outputs](https://platform.openai.com/docs/guides/structured-outputs/examples)。

這代表用 o1 發出的請求沒有可靠的型別安全，要靠 prompt 本身讓它回傳可用的 JSON。

在這份指南裡，我們會探討兩種方法，在使用 OpenAI API 時，引導 o1 模型（特別是 `o1-preview`）回傳有效的 JSON 格式。

# Prompting

用 `o1-preview` 回傳 JSON 最簡單的方式，就是在 prompt 裡明確要求。

我們來跑一個範例：
- 抓一個公司清單的 wikipedia 頁面
- 判斷哪些公司最能從 AI 能力獲益
- 用 JSON 格式回傳，這樣其他系統就能接著處理

```python
import requests
from openai import OpenAI

client = OpenAI()

def fetch_html(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        return None

url = "https://en.wikipedia.org/wiki/List_of_largest_companies_in_the_United_States_by_revenue"
html_content = fetch_html(url)

json_format = """
{
    companies: [
        {
            \"company_name\": \"OpenAI\",
            \"page_link\": \"https://en.wikipedia.org/wiki/OpenAI\",
            \"reason\": \"OpenAI would benefit because they are an AI company...\"
        }
    ]
}
"""

o1_response = client.chat.completions.create(
    model="o1-preview",
    messages=[
        {
            "role": "user", 
            "content": f"""
You are a business analyst designed to understand how AI technology could be used across large corporations.

- Read the following html and return which companies would benefit from using AI technology: {html_content}.
- Rank these propects by opportunity by comparing them and show me the top 3. Return only as a JSON with the following format: {json_format}"
"""
        }
    ]
)

print(o1_response.choices[0].message.content)
```

??? note "輸出"

    ```text
    {
        "companies": [
            {
                "company_name": "Walmart",
                "page_link": "https://en.wikipedia.org/wiki/Walmart",
                "reason": "Walmart could benefit from AI technology by enhancing their supply chain management, optimizing inventory levels, improving customer service through AI-powered chatbots, and providing personalized shopping experiences. AI can help Walmart forecast demand more accurately, reduce operational costs, and increase overall efficiency."
            },
            {
                "company_name": "UnitedHealth Group",
                "page_link": "https://en.wikipedia.org/wiki/UnitedHealth_Group",
                "reason": "UnitedHealth Group could leverage AI technology to improve patient care through predictive analytics, personalize treatment plans, detect fraudulent claims, and streamline administrative processes. AI can assist in early disease detection, improve diagnostic accuracy, and enhance data analysis for better health outcomes."
            },
            {
                "company_name": "Ford Motor Company",
                "page_link": "https://en.wikipedia.org/wiki/Ford_Motor_Company",
                "reason": "Ford Motor Company could benefit from AI technology by advancing autonomous vehicle development, optimizing manufacturing processes with automation and robotics, implementing predictive maintenance, and enhancing the in-car experience with AI-driven features. AI can help Ford improve safety, reduce production costs, and innovate new transportation solutions."
            }
        ]
    }
    ```

注意回應已經相當不錯，它回傳了有適當內容的 JSON。不過，它碰到的問題跟現有只靠 prompt 推出 JSON 的用法一樣：
- 你得手動把這個 JSON 處理成你的型別安全結構
- 模型的拒絕（refusal）不會[由 API 以獨立的結構明確回傳](https://platform.openai.com/docs/guides/structured-outputs/refusals)

# Structured Outputs

現在改用 [structured outputs](https://platform.openai.com/docs/guides/structured-outputs) 來做。要啟用這個功能，我們會把 `o1-preview` 的回應接到另一個發給 `gpt-4o-mini` 的後續請求，它可以有效處理 o1-preview 初次回應回傳的資料。

```python
from pydantic import BaseModel
from devtools import pprint

class CompanyData(BaseModel):
    company_name: str
    page_link: str
    reason: str

class CompaniesData(BaseModel):
    companies: list[CompanyData]

o1_response = client.chat.completions.create(
    model="o1-preview",
    messages=[
        {
            "role": "user", 
            "content": f"""
You are a business analyst designed to understand how AI technology could be used across large corporations.

- Read the following html and return which companies would benefit from using AI technology: {html_content}.
- Rank these propects by opportunity by comparing them and show me the top 3. Return each with {CompanyData.__fields__.keys()}
"""
        }
    ]
)

o1_response_content = o1_response.choices[0].message.content

response = client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=[
        {
            "role": "user", 
            "content": f"""
Given the following data, format it with the given response format: {o1_response_content}
"""
        }
    ],
    response_format=CompaniesData,
)

pprint(response.choices[0].message.parsed)
```

??? note "輸出"

    ```text
    CompaniesData(
        companies=[
            CompanyData(
                company_name='Walmart',
                page_link='https://en.wikipedia.org/wiki/Walmart',
                reason=(
                    'As the largest retailer, Walmart can significantly benefit from AI by optimizing supply chain and inv'
                    'entory management, improving demand forecasting, personalizing customer experiences, and enhancing in'
                    '-store operations through AI-driven analytics.'
                ),
            ),
            CompanyData(
                company_name='JPMorgan Chase',
                page_link='https://en.wikipedia.org/wiki/JPMorgan_Chase',
                reason=(
                    'As a leading financial institution, JPMorgan Chase can leverage AI for fraud detection, risk manageme'
                    'nt, personalized banking services, algorithmic trading, and enhancing customer service with AI-powere'
                    'd chatbots and virtual assistants.'
                ),
            ),
            CompanyData(
                company_name='UnitedHealth Group',
                page_link='https://en.wikipedia.org/wiki/UnitedHealth_Group',
                reason=(
                    'Being a major player in healthcare, UnitedHealth Group can utilize AI to improve patient care through'
                    ' predictive analytics, enhance diagnostics, streamline administrative processes, and reduce costs by '
                    'optimizing operations with AI-driven solutions.'
                ),
            ),
        ],
    )
    ```

# 結論

Structured outputs 讓你的程式有可靠的型別安全，prompt 也更簡單。此外，它讓你可以重用物件 schema，更容易整合進現有的工作流程。

o1 系列模型目前沒有 structured outputs 支援，但我們可以把兩個請求串在一起，重用 `gpt-4o-mini` 現有的 structured outputs 功能。這個流程目前需要兩次呼叫，但第二次 `gpt-4o-mini` 呼叫的成本，相較於 `o1-preview`/`o1-mini` 的呼叫應該很低。

## 重點整理

- 只靠 prompt 要 JSON，沒有型別保證，refusal 也不會單獨回傳。
- structured outputs 用 schema 約束輸出，程式碼可以直接拿到型別安全的物件。
- 串接模式是讓推理強的模型負責思考，再讓支援 structured outputs 的便宜模型負責整理格式。
- 多一次便宜的呼叫，換到可靠的格式，通常划算。

## 練習

1. 換掉 prompt 裡的主題（例如改成評估別種產業的公司），看 JSON 結構是否仍然穩定。
2. 在第二次呼叫的 schema 多加一個欄位（例如理由的簡短摘要），重跑看看輸出。
3. 比較兩種方式的輸出，並檢查 prompt-only 的結果是否真的總是能被 `json.loads` 解析。
