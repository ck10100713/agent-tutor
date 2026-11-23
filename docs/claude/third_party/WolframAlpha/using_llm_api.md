---
translated: true
source: third_party/WolframAlpha/using_llm_api.ipynb
---

# 把 Wolfram Alpha LLM API 當成 Claude 的 tool

> 原文：[third_party/WolframAlpha/using_llm_api.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/WolframAlpha/using_llm_api.ipynb)

把 Wolfram Alpha LLM API 接成 Claude 的 tool，處理需要計算的查詢和答案。

## 這篇在做什麼

這篇把 Wolfram Alpha LLM API 包成一個 tool 給 Claude 用。Claude 遇到需要精確計算的問題時，會把 query 送給 Wolfram Alpha，拿到算好的結果再整理成回答。

## 學完你會

- 寫一個函式，把 query 做 URL 編碼後呼叫 Wolfram Alpha LLM API，成功回傳結果、失敗回傳錯誤訊息
- 用只含一個 `query` 字串欄位的 input schema 定義 `wolfram_alpha` tool
- 讓 Claude 自己決定什麼時候呼叫這個 tool，並用算出來的結果回答問題

## 開跑前

需要 Anthropic API key 和 Wolfram Alpha 的 App ID，App ID 可以在[這裡](https://developer.wolframalpha.com/access)免費申請。

這份教學示範如何把 Wolfram Alpha LLM API 整合成 Claude 可以用的 tool。Claude 能把 query 送給 Wolfram Alpha API 並取得計算好的回應，再用它來回答使用者的問題。

## 步驟 1：設定環境
先安裝需要的函式庫並設定 Claude API client。我們還需要設定使用 WolframAlpha 的 APP ID。你可以在[這裡](https://developer.wolframalpha.com/access)免費註冊，替這個專案建立新的 App ID。

```python
import json
import urllib.parse

import requests
from anthropic import Anthropic

client = Anthropic()

# Replace 'YOUR_APP_ID' with your actual Wolfram Alpha AppID
WOLFRAM_APP_ID = "YOUR_APP_ID"
MODEL_NAME = "claude-haiku-5-5"
```

## 步驟 2：定義 Wolfram Alpha LLM API tool
我們定義一個 tool，讓 Claude 能把 query 送給 Wolfram Alpha LLM API，並取得計算好的回應。

```python
import urllib.parse

import requests


def wolfram_alpha_query(query):
    # URL-encode the query
    encoded_query = urllib.parse.quote(query)

    # Make a request to the Wolfram Alpha LLM API
    url = (
        f"https://www.wolframalpha.com/api/v1/llm-api?input={encoded_query}&appid={WOLFRAM_APP_ID}"
    )
    response = requests.get(url, timeout=30)

    if response.status_code == 200:
        return response.text
    else:
        return f"Error: {response.status_code}: {response.text}"


tools = [
    {
        "name": "wolfram_alpha",
        "description": "A tool that allows querying the Wolfram Alpha knowledge base. Useful for mathematical calculations, scientific data, and general knowledge questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "The query to send to the Wolfram Alpha API.",
                }
            },
            "required": ["search_query"],
        },
    }
]
```

這段程式碼定義了一個 wolfram_alpha_query 函式，它接收 query 作為輸入，做 URL 編碼，並用提供的 AppID 對 Wolfram Alpha LLM API 發出請求。請求成功時，函式回傳 API 算出的回應；有問題時回傳錯誤訊息。

接著我們定義 wolfram_alpha tool，它的 input schema 預期只有一個型別為 string 的 `query` 屬性。


## 步驟 3：跟 Claude 互動
現在來看看 Claude 如何跟 Wolfram Alpha tool 互動，回答使用者的問題。

```python
def process_tool_call(tool_name, tool_input):
    if tool_name == "wolfram_alpha":
        return wolfram_alpha_query(tool_input["search_query"])


def chat_with_claude(user_message):
    print(f"\n{'=' * 50}\nUser Message: {user_message}\n{'=' * 50}")
    prompt = f"""Here is a question: {user_message}. Please use the Wolfram Alpha tool to answer it. Do not reflect on the quality of the returned search results in your response."""

    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        tools=tools,
        messages=[{"role": "user", "content": prompt}],
    )

    print("\nInitial Response:")
    print(f"Stop Reason: {message.stop_reason}")
    print(f"Content: {message.content}")

    if message.stop_reason == "tool_use":
        tool_use = next(block for block in message.content if block.type == "tool_use")
        tool_name = tool_use.name
        tool_input = tool_use.input

        print(f"\nTool Used: {tool_name}")
        print("Tool Input:")
        print(json.dumps(tool_input, indent=2))

        tool_result = process_tool_call(tool_name, tool_input)

        print("\nTool Result:")
        print(str(json.dumps(tool_result, indent=2)))

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=2000,
            tools=tools,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": message.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": str(tool_result),
                        }
                    ],
                },
            ],
        )

        print("\nResponse:")
        print(f"Stop Reason: {response.stop_reason}")
        print(f"Content: {response.content}")
    else:
        response = message

    final_response = None
    for block in response.content:
        if block.type == "text":
            final_response = block.text
            break

    print(f"\nFinal Response: {final_response}")

    return final_response
```

## 步驟 4：試試看！
現在 Claude 有了 Wolfram Alpha 可用，我們丟幾個範例問題給它。

```python
# Example usage
print(chat_with_claude("What are the 5 largest countries in the world by population?"))
print(chat_with_claude("Calculate the square root of 1764."))
print(chat_with_claude("What is the distance between Earth and Mars?"))
```

??? note "輸出"

    ```text

    ==================================================
    User Message: What are the 5 largest countries in the world by population?
    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>\nThe query "What are the 5 largest countries in the world by population?" can be answered well using the wolfram_alpha tool, which has knowledge about countries and populations. The search_query parameter is the only required parameter, and the query text provided by the user can be used directly as the search_query value without any additional information needed. \n</thinking>', type='text'), ContentBlockToolUse(id='toolu_01VCQ5xAzMNdyXYsepbSAJLY', input={'search_query': 'What are the 5 largest countries in the world by population?'}, name='wolfram_alpha', type='tool_use')]

    Tool Used: wolfram_alpha
    Tool Input:
    {
      "search_query": "What are the 5 largest countries in the world by population?"
    }

    Tool Result:
    "Query:\n\"What are the 5 largest countries in the world by population?\"\n\nInput interpretation:\n5 largest countries | by population\nin all countries, dependencies, and territories\n\nResult:\n1 | India | 1.43 billion people | \n2 | China | 1.43 billion people | \n3 | United States | 340 million people | \n4 | Indonesia | 278 million people | \n5 | Pakistan | 241 million people | \n\nNames:\n | full name | full native name\nIndia | Republic of India | Bh\u0101rat\u012bya Ga\u1e47ar\u0101jya\nChina | People's Republic of China | Zhonghua Renmin Gongheguo\nUnited States | United States of America | \nIndonesia | Republic of Indonesia | Republik Indonesia\nPakistan | Islamic Republic of Pakistan | Isl\u0101m\u012b Jumh\u016br\u012b-ye P\u0101kist\u0101n\n\nFlags:\nimage: https://www6b3.wolframalpha.com/Calculate/MSP/MSP2444241bhh00e1he97fd0000383004g53722f9bd?MSPStoreType=image/png&s=14\nWolfram Language code: Dataset[EntityValue[{Entity[\"Country\", \"India\"], Entity[\"Country\", \"China\"], Entity[\"Country\", \"UnitedStates\"], Entity[\"Country\", \"Indonesia\"], Entity[\"Country\", \"Pakistan\"]}, EntityProperty[\"Country\", \"Flag\"], \"EntityAssociation\"]]\n\nLocations:\nimage: https://www6b3.wolframalpha.com/Calculate/MSP/MSP2445241bhh00e1he97fd00002684a23aaahea47d?MSPStoreType=image/png&s=14\n\nGeographic properties:\ntotal area | total | 9.736 million mi^2 (square miles)\n | largest | 3.719 million mi^2 (square miles) (world rank: 3rd) (United States)\n | smallest | 307374 mi^2 (square miles) (world rank: 36th) (Pakistan)\nland area | total | 9.283 million mi^2 (square miles)\n | largest | 3.601 million mi^2 (square miles) (world rank: 2nd) (China)\n | smallest | 297637 mi^2 (square miles) (world rank: 36th) (Pakistan)\ncontinent | all | Asia | North America\n\nDemographics:\npopulation | total | 3.71 billion people\n | highest | 1.43 billion people (world rank: 1st) (2023 estimate) (India)\n | lowest | 241 million people (world rank: 5th) (2023 estimate) (Pakistan)\npopulation density | average | 390 people/mi^2\n | median | 385 people/mi^2\n | highest | 1226 people/mi^2 (world rank: 31st) (2021 estimate) (India)\n | lowest | 95.4 people/mi^2 (world rank: 183rd) (2021 estimate) (United States)\npopulation growth | average | 0.455 %/yr\n | median | 0.631 %/yr\n | highest | 1.83 %/yr (world rank: 56th) (2021 estimate) (Pakistan)\n | lowest | 0.004 %/yr (world rank: 188th) (2021 estimate) (China)\nlife expectancy | mean | 73 yr\n | median | 71.9 yr\n | highest | 78.9 yr (world rank: 66th) (2020 estimate) (United States)\n | lowest | 67.4 yr (world rank: 186th) (2020 estimate) (Pakistan)\nmedian age | median | 29.4 yr\n | highest | 37.9 yr (world rank: 70th) (2021 estimate) (China)\n | lowest | 20.2 yr (world rank: 191st) (2021 estimate) (Pakistan)\n\nCapital cities:\nIndia | New Delhi, Delhi\nChina | Beijing\nUnited States | Washington, District of Columbia\nIndonesia | Jakarta\nPakistan | Islamabad, F.C.T.\n\nEconomic properties:\nGDP | total | $48.51 trillion per year\n | median | $3.385 trillion per year\n | highest | $25.46 trillion per year (world rank: 1st) (2022 estimates) (United States)\n | lowest | $376.5 billion per year (world rank: 43rd) (2022 estimates) (Pakistan)\nGDP at parity | total | $73.22 trillion per year\n | median | $11.87 trillion per year\n | highest | $30.33 trillion per year (world rank: 1st) (2022 estimates) (China)\n | lowest | $1.518 trillion per year (world rank: 22nd) (2022 estimates) (Pakistan)\nreal GDP | total | $41.72 trillion per year\n | median | $2.955 trillion per year\n | highest | $20.95 trillion per year (world rank: 1st) (2022 estimates) (United States)\n | lowest | $362.2 billion per year (world rank: 37th) (2022 estimates) (Pakistan)\nGDP per capita | average | $13203 per year per person\n | median | $4788 per year per person\n | highest | $76399 per year per person (world rank: 12th) (2022 estimates) (United States)\n | lowest | $1597 per year per person (world rank: 197th) (2022 estimates) (Pakistan)\nGDP real growth | mean | +4.71% per year\n | median | +5.309% per year\n | highest | +7.003% per year (world rank: 38th) (2022 estimates) (India)\n | lowest | +2.062% per year (world rank: 157th) (2022 estimates) (United States)\nGini index | median | 0.371\n | highest | 0.398 (world rank: 102nd) (2018, 2020, 2021, and 2022 estimates) (United States)\n | lowest | 0.296 (world rank: 24th) (2018, 2020, 2021, and 2022 estimates) (Pakistan)\n | distribution | \nconsumer price inflation | mean | +8.15% per year\n | median | +6.7% per year\n | highest | +19.87% per year (world rank: 21st) (2022 estimates) (Pakistan)\n | lowest | +1.97% per year (world rank: 175th) (2022 estimates) (China)\n\nEmployment:\nunemployment rate | mean | 5.16%\n | median | 4.89%\n | highest | 7.33% (world rank: 74th highest) (2022 estimates) (India)\n | lowest | 3.55% (world rank: 162nd highest) (2022 estimates) (Indonesia)\nlong-term unemployment rate | mean | 1.57%\n | median | 1.42%\n | highest | 3.18% (world rank: 44th highest) (2010 and 2014 estimates) (India)\n | lowest | 0.127% (world rank: 111th highest) (2010 and 2014 estimates) (Pakistan)\nlabor force | highest | 781.8 million people (58.24% of population) (world rank: 1st) (2022 estimates) (China)\n | lowest | 78.91 million people (35.22% of population) (world rank: 6th) (2022 estimates) (Pakistan)\n | distribution | \neconomically active children | median | 3.7%\n | highest | 13% (world rank: 50th) (2010, 2011, and 2012 estimates) (Pakistan)\n | lowest | 1.7% (world rank: 90th) (2010, 2011, and 2012 estimates) (India)\n\nUN Human Development Index:\n | India | China | United States | Indonesia | Pakistan\nhealth | 0.743 (world rank: 131st) | 0.861 (world rank: 58th) | 0.911 (world rank: 36th) | 0.755 (world rank: 126th) | 0.713 (world rank: 137th)\neducation | 0.535 (world rank: 131st) | 0.631 (world rank: 108th) | 0.9 (world rank: 8th) | 0.622 (world rank: 112th) | 0.395 (world rank: 169th)\nliving standards | 0.61 (world rank: 126th) | 0.739 (world rank: 82nd) | 0.948 (world rank: 11th) | 0.696 (world rank: 103rd) | 0.592 (world rank: 133rd)\ntotal | 0.624 (world rank: 131st) | 0.738 (world rank: 90th) | 0.92 (world rank: 10th) | 0.689 (world rank: 113th) | 0.55 (world rank: 147th)\n(2015 estimate)\n\nWikipedia page hits history:\nimage: https://www6b3.wolframalpha.com/Calculate/MSP/MSP2448241bhh00e1he97fd00006a6g1ee3gbhghh18?MSPStoreType=image/png&s=14\n\nWolfram|Alpha website result for \"What are the 5 largest countries in the world by population?\":\nhttps://www6b3.wolframalpha.com/input?i=What+are+the+5+largest+countries+in+the+world+by+population%3F"

    Response:
    Stop Reason: end_turn
    Content: [ContentBlock(text='According to Wolfram Alpha, the 5 largest countries in the world by population are:\n\n1. India - 1.43 billion people\n2. China - 1.43 billion people \n3. United States - 340 million people\n4. Indonesia - 278 million people\n5. Pakistan - 241 million people\n\nTogether these 5 countries account for about 3.71 billion people. India and China have the largest populations, each with around 1.43 billion people. The United States has the 3rd largest population at 340 million. Indonesia and Pakistan round out the top 5 with 278 million and 241 million people respectively.', type='text')]

    Final Response: According to Wolfram Alpha, the 5 largest countries in the world by population are:

    1. India - 1.43 billion people
    2. China - 1.43 billion people 
    3. United States - 340 million people
    4. Indonesia - 278 million people
    5. Pakistan - 241 million people

    Together these 5 countries account for about 3.71 billion people. India and China have the largest populations, each with around 1.43 billion people. The United States has the 3rd largest population at 340 million. Indonesia and Pakistan round out the top 5 with 278 million and 241 million people respectively.
    According to Wolfram Alpha, the 5 largest countries in the world by population are:

    1. India - 1.43 billion people
    2. China - 1.43 billion people 
    3. United States - 340 million people
    4. Indonesia - 278 million people
    5. Pakistan - 241 million people

    Together these 5 countries account for about 3.71 billion people. India and China have the largest populations, each with around 1.43 billion people. The United States has the 3rd largest population at 340 million. Indonesia and Pakistan round out the top 5 with 278 million and 241 million people respectively.
    ... (省略 60 行)
    ```

## 重點整理

- 外部計算服務可以包成一個簡單的 tool：一個函式加一個 input schema。
- tool 的函式要處理失敗情況，回傳錯誤訊息讓 Claude 知道發生什麼事，而不是直接丟例外。
- query 要先做 URL 編碼再送出，不然特殊字元會弄壞請求。
- 是否呼叫 tool 由 Claude 根據問題決定，需要精確計算時它會借助 Wolfram Alpha。

## 練習

1. 對 Claude 問一個不需要計算的問題（例如問候），確認它不會呼叫 `wolfram_alpha`。
2. 把 App ID 故意改錯，看 `wolfram_alpha_query` 回傳的錯誤訊息，以及 Claude 怎麼回應。
3. 在 tool 的 description 裡加上「只用來處理數學與單位換算」，再丟一個歷史問題，觀察 Claude 的呼叫行為有沒有改變。
