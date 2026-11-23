---
translated: true
source: examples/responses_api/responses_example.ipynb
---

# 用 Responses API 做 web search 與狀態管理

> 原文：[examples/responses_api/responses_example.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/responses_api/responses_example.ipynb)



## 這篇在做什麼
介紹 Responses API 的幾個核心特色：有狀態的對話、內建 hosted tool（例如 web search），以及原生支援多模態。最後用一次 API 呼叫完成「看圖加搜尋網路」。

## 學完你會
- 用 Responses API 發出請求，並用前一個 response 接續（或分岔）對話
- 把 `web_search` 這類 hosted tool 直接傳給 API，讓它自己決定要不要用
- 在一次呼叫裡結合圖片輸入和 web search，省下 Chat Completions 需要的多次往返

## 開跑前
需要 OpenAI API key。

## 什麼是 Responses API？

Responses API 是跟 OpenAI 模型互動的新方式，設計上比以前的 API 更簡單、更有彈性。它讓你容易建立進階的 AI 應用，可以使用多個 tool、處理多輪對話，並處理不同類型的資料（不只是文字）。

不像舊的 API，例如主要為文字設計的 Chat Completions，或需要大量設定的 Assistants API，Responses API 是從頭開始為以下目標打造：

- 流暢的多輪互動（在單一 API 呼叫裡，跨多個步驟延續對話）
- 輕鬆使用強大的 hosted tool（像是 file search、web search 和 code interpreter）
- 對送給模型的上下文有細緻的控制

隨著 AI 模型越來越有能力做複雜、長時間的 reasoning，開發者需要一個既非同步又有狀態的 API。Responses API 就是為了滿足這些需求而設計。

在這份指南裡，你會看到 Responses API 提供的一些新功能，以及幫助你上手的實用範例。

## 基礎
就設計來說，從表面上看，Responses API 跟 Completions API 很像。

```python
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```

```python
response = client.responses.create(
    model="gpt-4o-mini",
    input="tell me a joke",
)
```

```python
print(response.output[0].content[0].text)
```

??? note "輸出"

    ```text
    Why did the scarecrow win an award?

    Because he was outstanding in his field!
    ```

Response API 的一個關鍵特色是有狀態。這代表你不用自己管理對話的狀態，API 會幫你處理。例如，你隨時可以取回某個 response，它會包含完整的對話歷史。

```python
fetched_response = client.responses.retrieve(
response_id=response.id)

print(fetched_response.output[0].content[0].text)
```

??? note "輸出"

    ```text
    Why did the scarecrow win an award?

    Because he was outstanding in his field!
    ```

你可以引用前一個 response 來繼續對話。

```python
response_two = client.responses.create(
    model="gpt-4o-mini",
    input="tell me another",
    previous_response_id=response.id
)
```

```python
print(response_two.output[0].content[0].text)
```

??? note "輸出"

    ```text
    Why don't skeletons fight each other?

    They don't have the guts!
    ```

你當然也可以自己管理上下文。不過讓 OpenAI 幫你維護上下文的一個好處，是你可以在任何一點分岔 response，從那個點繼續對話。

```python
response_two_forked = client.responses.create(
    model="gpt-4o-mini",
    input="I didn't like that joke, tell me another and tell me the difference between the two jokes",
    previous_response_id=response.id # Forking and continuing from the first response
)

output_text = response_two_forked.output[0].content[0].text
print(output_text)
```

??? note "輸出"

    ```text
    Sure! Here’s another joke:

    Why don’t scientists trust atoms?

    Because they make up everything!

    **Difference:** The first joke plays on a pun involving "outstanding" in a literal sense versus being exceptional, while the second joke relies on a play on words about atoms "making up" matter versus fabricating stories. Each joke uses wordplay, but they target different concepts (farming vs. science).
    ```

## Hosted Tool

Responses API 的另一個好處，是新增了對 `file_search` 和 `web_search` 這類 hosted tool 的支援。你不用手動呼叫 tool，只要把 tool 傳進去，API 就會決定要用哪個 tool 並使用它。

下面是用 `web_search` tool 把網路搜尋結果納入回應的範例。

```python
response = client.responses.create(
    model="gpt-4o",  # or another supported model
    input="What's the latest news about AI?",
    tools=[
        {
            "type": "web_search"
        }
    ]
)
```

```python
import json
print(json.dumps(response.output, default=lambda o: o.__dict__, indent=2))
```

??? note "輸出"

    ```text
    [
      {
        "id": "ws_67bd64fe91f081919bec069ad65797f1",
        "status": "completed",
        "type": "web_search_call"
      },
      {
        "id": "msg_67bd6502568c8191a2cbb154fa3fbf4c",
        "content": [
          {
            "annotations": [
              {
                "index": null,
                "title": "Huawei improves AI chip production in boost for China's tech goals",
                "type": "url_citation",
                "url": "https://www.ft.com/content/f46b7f6d-62ed-4b64-8ad7-2417e5ab34f6?utm_source=chatgpt.com"
              },
              {
                "index": null,
                "title": "Apple cheers Trump with $500bn US investment plan; more losses on Wall Street - as it happened",
                "type": "url_citation",
                "url": "https://www.theguardian.com/business/live/2025/feb/24/euro-hits-one-month-high-german-election-result-stock-markets-dax-bank-of-england-business-live-news?utm_source=chatgpt.com"
              },
              {
                "index": null,
                "title": "Microsoft axes data center leases as DeepSeek casts doubt on massive AI spend: report",
                "type": "url_citation",
                "url": "https://nypost.com/2025/02/24/business/microsoft-axes-some-ai-data-center-leases-td-cowen-says/?utm_source=chatgpt.com"
              },
              {
                "index": null,
                "title": "Alibaba Plans to Invest $52B in AI, Cloud Over Next Three Years",
                "type": "url_citation",
                "url": "https://www.investopedia.com/alibaba-plans-to-invest-usd52b-in-ai-cloud-over-next-three-years-11684981?utm_source=chatgpt.com"
              },
              {
                "index": null,
                "title": "JPMorgan Unit Backs Albert Invent at a $270 Million Valuation",
                "type": "url_citation",
                "url": "https://www.wsj.com/articles/jpmorgan-unit-backs-albert-invent-at-a-270-million-valuation-1ab03c96?utm_source=chatgpt.com"
    ... (省略 11 行)
    ```

## 多模態、tool 加持的對話

Responses API 原生支援文字、圖片和音訊模態。 
把所有東西結合起來，我們可以透過 responses API，用一次 API 呼叫做出完整多模態、有 tool 加持的互動。

```python
import base64

from IPython.display import Image, display

# Display the image from the provided URL
url = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/Cat_August_2010-4.jpg/2880px-Cat_August_2010-4.jpg"
display(Image(url=url, width=400))

response_multimodal = client.responses.create(
    model="gpt-4o",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": 
                 "Come up with keywords related to the image, and search on the web using the search tool for any news related to the keywords"
                 ", summarize the findings and cite the sources."},
                {"type": "input_image", "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/15/Cat_August_2010-4.jpg/2880px-Cat_August_2010-4.jpg"}
            ]
        }
    ],
    tools=[
        {"type": "web_search"}
    ]
)
```

??? note "輸出"

    ```text
    <IPython.core.display.Image object>
    ```

```python
import json
print(json.dumps(response_multimodal.__dict__, default=lambda o: o.__dict__, indent=4))
```

??? note "輸出"

    ```text
    {
        "id": "resp_67bd65392a088191a3b802a61f4fba14",
        "created_at": 1740465465.0,
        "error": null,
        "metadata": {},
        "model": "gpt-4o-2024-08-06",
        "object": "response",
        "output": [
            {
                "id": "msg_67bd653ab9cc81918db973f0c1af9fbb",
                "content": [
                    {
                        "annotations": [],
                        "text": "Based on the image of a cat, some relevant keywords could be:\n\n- Cat\n- Feline\n- Pet\n- Animal care\n- Cat behavior\n\nI'll search for recent news related to these keywords.",
                        "type": "output_text",
                        "logprobs": null
                    }
                ],
                "role": "assistant",
                "type": "message"
            },
            {
                "id": "ws_67bd653c7a548191af86757fbbca96e1",
                "status": "completed",
                "type": "web_search_call"
            },
            {
                "id": "msg_67bd653f34fc8191989241b2659fd1b5",
                "content": [
                    {
                        "annotations": [
                            {
                                "index": null,
                                "title": "Cat miraculously survives 3 weeks trapped in sofa during family's cross-country move",
                                "type": "url_citation",
                                "url": "https://nypost.com/2025/02/24/us-news/cat-miraculously-survives-3-weeks-trapped-in-sofa-during-familys-cross-country-move/?utm_source=chatgpt.com"
                            },
                            {
                                "index": null,
                                "title": "Ex-College Soccer Player Accused of Killing Fellow Athlete Brother, Cat Using Knife, Golf Club: Prosecutors",
    ... (省略 72 行)
    ```

在上面的例子裡，我們可以用 `web_search` tool，在一次 API 呼叫中搜尋跟圖片相關的新聞，而如果用 Chat Completions，就需要多次往返。

用 Responses API，一個請求就能分析圖片、呼叫 hosted web search，並摘要結果。同樣的流程用 Chat Completions，則需要應用程式自己執行 tool call，並在另一個請求裡送出結果。

下圖比較了兩種流程。

![Responses vs Completions](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/comparisons.png)

## 重點整理
- Responses API 是有狀態的，用 response id 就能接續對話，不用自己維護完整歷史。
- 可以從任何一個 response 分岔出不同的對話分支。
- hosted tool 只要傳給 API，由它決定要不要用、怎麼用，不用自己處理 tool call 迴圈。
- 一次請求就能同時處理圖片輸入和 web search，比 Chat Completions 少很多往返。

## 練習
1. 把基礎範例的問題換成你自己的，確認能取回 response 和對話歷史。
2. 從同一個 response 分岔出兩條不同的追問，比較兩條分支的回答。
3. 修改 web search 範例的 prompt，改成查詢你關心的主題的最新消息，並檢查回應中引用的來源。
