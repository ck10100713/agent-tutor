---
translated: true
source: examples/responses_api/reasoning_items.ipynb
---
# 用 Responses API 讓 reasoning model 表現更好

> 原文：[examples/responses_api/reasoning_items.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/responses_api/reasoning_items.ipynb)



## 這篇在做什麼

說明 o3、o4-mini 這類 reasoning model 搭配 Responses API 時，reasoning item 是怎麼運作的。內容包含為什麼 function calling 要把 reasoning item 傳回去、這對 cache 和成本有什麼影響、不能 stateful 的組織怎麼用 encrypted reasoning item，還有怎麼拿 reasoning summary。

## 學完你會

- 讀懂 response 裡的 reasoning item 和 reasoning token 數，並用 `previous_response_id` 或手動把 output 加回 `input` 來傳遞它。
- 在 function calling 的情境下，正確把 reasoning item 帶進下一輪請求。
- 用 `include=["reasoning.encrypted_content"]` 做 stateless 的流程，並取得 reasoning summary 顯示給使用者。

## 開跑前

需要 OpenAI API key，並且帳號要能使用 o3 或 o4-mini。

### 總覽

搭配 OpenAI 最新的 reasoning model 使用 Responses API，能讓你的應用有更高的智慧、更低的成本和更有效率的 token 使用。這個 API 也能取得 reasoning summary，支援 hosted tool 之類的功能，並且為之後的新功能保留了彈性。



我們最近發布了兩個最先進的 reasoning model：o3 和 o4-mini，它們擅長把推理能力和 agentic 的 tool 使用結合起來。很多人不知道的是，充分利用我們（相對）新的 Responses API 可以提升它們的表現。這份 cookbook 說明怎麼把這些模型發揮到極致，並探討 reasoning 和 function calling 在背後怎麼運作。只要讓模型取得先前的 reasoning item，就能確保它以最高智慧、最低成本運作。

我們在另一份 [cookbook](https://cookbook.openai.com/examples/responses_api/responses_example) 和 [API reference](https://platform.openai.com/docs/api-reference/responses) 介紹過 Responses API。重點是：Responses API 跟 Completions API 類似，但有改進和新增功能。我們也為 Responses 推出了 encrypted content，讓無法以 stateful 方式使用 API 的人更能受惠！

## Reasoning Model 怎麼運作

在說明 Responses API 能怎麼幫上忙之前，先快速複習 [reasoning model](https://platform.openai.com/docs/guides/reasoning?api-mode=responses) 怎麼運作。像 o3 和 o4-mini 這樣的模型會一步一步拆解問題，產生一條編碼了推理過程的內部 chain of thought。基於安全考量，這些 reasoning token 只會以摘要的形式提供給使用者。

在多輪對話裡，每一輪結束後 reasoning token 都會被丟棄，而每個步驟的 input 和 output token 會被送進下一步。

![reasoning-context](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/reasoning-turns.png)
圖片引用自我們的[文件](https://platform.openai.com/docs/guides/reasoning?api-mode=responses#how-reasoning-works)

來看看回傳的 response 物件：

```python
from openai import OpenAI
import os
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
```

```python
response = client.responses.create(
    model="o4-mini",
    input="tell me a joke",
)
```

```python
import json

print(json.dumps(response.model_dump(), indent=2))
```

??? note "輸出"

    ```text
    {
      "id": "resp_6820f382ee1c8191bc096bee70894d040ac5ba57aafcbac7",
      "created_at": 1746989954.0,
      "error": null,
      "incomplete_details": null,
      "instructions": null,
      "metadata": {},
      "model": "o4-mini-2025-04-16",
      "object": "response",
      "output": [
        {
          "id": "rs_6820f383d7c08191846711c5df8233bc0ac5ba57aafcbac7",
          "summary": [],
          "type": "reasoning",
          "status": null
        },
        {
          "id": "msg_6820f3854688819187769ff582b170a60ac5ba57aafcbac7",
          "content": [
            {
              "annotations": [],
              "text": "Why don\u2019t scientists trust atoms?  \nBecause they make up everything!",
              "type": "output_text"
            }
          ],
          "role": "assistant",
          "status": "completed",
          "type": "message"
        }
      ],
      "parallel_tool_calls": true,
      "temperature": 1.0,
      "tool_choice": "auto",
      "tools": [],
      "top_p": 1.0,
      "max_output_tokens": null,
      "previous_response_id": null,
      "reasoning": {
        "effort": "medium",
        "generate_summary": null,
    ... (省略 24 行)
    ```

從 response 物件的 JSON dump 可以看到，除了 `output_text`，模型還產生了一個 reasoning item。這個 item 代表模型內部的 reasoning token，並以 ID 的形式呈現，例如 `rs_6820f383d7c08191846711c5df8233bc0ac5ba57aafcbac7`。因為 Responses API 是 stateful 的，這些 reasoning token 會保留下來：只要在後續訊息裡帶上它們的 ID，之後的回應就能取得同樣的 reasoning item。如果你在多輪對話裡用 `previous_response_id`，模型會自動取得之前產生的所有 reasoning item。

你也可以看到模型產生了多少 reasoning token。例如 input 是 10 個 token，response 包含 148 個 output token，其中 128 個是沒有顯示在最終 assistant 訊息裡的 reasoning token。

等等，剛才的圖不是說前幾輪的 reasoning 會被丟棄嗎？那為什麼還要在後面的輪次傳回去？

問得好！在一般的多輪對話裡，你不需要帶 reasoning item 或 token，模型訓練時就是讓它沒有這些也能產生最好的輸出。但只要涉及 tool 使用，情況就不同了。如果某一輪包含 function call（可能需要在 API 外多跑一趟），你就必須帶上 reasoning item，可以透過 `previous_response_id`，或明確把 reasoning item 加進 `input`。來看一個簡單的 function calling 例子怎麼運作。

```python
import requests

def get_weather(latitude, longitude):
    response = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m")
    data = response.json()
    return data['current']['temperature_2m']


tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "Get current temperature for provided coordinates in celsius.",
    "parameters": {
        "type": "object",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"}
        },
        "required": ["latitude", "longitude"],
        "additionalProperties": False
    },
    "strict": True
}]

context = [{"role": "user", "content": "What's the weather like in Paris today?"}]

response = client.responses.create(
    model="o4-mini",
    input=context,
    tools=tools,
)


response.output
```

??? note "輸出"

    ```text
    [ResponseReasoningItem(id='rs_68210c71a95c81919cc44afadb9d220400c77cc15fd2f785', summary=[], type='reasoning', status=None),
     ResponseFunctionToolCall(arguments='{"latitude":48.8566,"longitude":2.3522}', call_id='call_9ylqPOZUyFEwhxvBwgpNDqPT', name='get_weather', type='function_call', id='fc_68210c78357c8191977197499d5de6ca00c77cc15fd2f785', status='completed')]
    ```

經過一番推理，o4-mini 判斷需要更多資訊，於是呼叫一個 function 去取得。我們可以呼叫這個 function 並把輸出回傳給模型。關鍵是，為了讓模型發揮最高智慧，我們應該把 reasoning item 也帶上，做法很簡單，就是把所有 output 都加回下一輪的 context。

```python
context += response.output # Add the response to the context (including the reasoning item)

tool_call = response.output[1]
args = json.loads(tool_call.arguments)


# calling the function
result = get_weather(args["latitude"], args["longitude"]) 

context.append({                               
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": str(result)
})

# we are calling the api again with the added function call output. Note that while this is another API call, we consider this as a single turn in the conversation.
response_2 = client.responses.create(
    model="o4-mini",
    input=context,
    tools=tools,
)

print(response_2.output_text)
```

??? note "輸出"

    ```text
    The current temperature in Paris is 16.3°C. If you’d like more details—like humidity, wind speed, or a brief description of the sky—just let me know!
    ```

這個玩具範例可能看不出明顯好處，因為不管有沒有 reasoning item，模型多半都能表現得不錯。但我們自己的測試不是這樣：在 SWE-bench 這類更嚴謹的 benchmark 上，同樣的 prompt 和設定，帶上 reasoning item 讓成績提升約 **3%**。

## Caching

如上所示，reasoning model 會產生 reasoning token 和 completion token，API 對兩者的處理方式不同。這個差異會影響 caching 的運作，也影響效能和延遲。下圖說明這些概念：

![reasoning-context](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/responses-diagram.png)

在第 2 輪，第 1 輪的所有 reasoning item 都會被忽略並移除，因為模型不會重複使用先前輪次的 reasoning item。所以圖裡第四次 API 呼叫無法完整命中 cache，因為 prompt 裡缺了那些 reasoning item。不過帶上它們沒有壞處，API 會直接丟掉跟當前輪次無關的 reasoning item。注意 caching 只影響超過 1024 token 的 prompt。在我們的測試中，從 Completions API 換成 Responses API，cache 使用率從 40% 提升到 80%。更高的 cache 使用率代表更低的成本（例如 `o4-mini` 有 cache 的 input token 比沒 cache 的便宜 75%），延遲也更好。

## Encrypted Reasoning Item

有些組織，例如有 [Zero Data Retention (ZDR)](https://openai.com/enterprise-privacy/) 要求的，因為合規或資料保留政策，無法以 stateful 的方式使用 Responses API。為了支援這些情況，OpenAI 提供 [encrypted reasoning item](https://platform.openai.com/docs/guides/reasoning?api-mode=responses#encrypted-reasoning-items)，讓你的 workflow 保持 stateless，同時仍能受惠於 reasoning item。

使用 encrypted reasoning item 的方式：
- 在 API 呼叫的 `include` 欄位加入 `["reasoning.encrypted_content"]`。
- API 會回傳 reasoning token 的加密版本，你可以像一般 reasoning item 一樣在後續請求傳回去。

對 ZDR 組織，OpenAI 會自動強制 `store=false`。當請求包含 `encrypted_content` 時，它會在記憶體中解密（絕不寫入磁碟），用來產生下一個回應，然後安全地丟棄。任何新的 reasoning token 都會立刻加密並回傳給你，確保不會留下任何中間狀態。

下面是簡單的程式碼修改，示範怎麼做：

```python
context = [{"role": "user", "content": "What's the weather like in Paris today?"}]

response = client.responses.create(
    model="o3",
    input=context,
    tools=tools,
    store=False, #store=false, just like how ZDR is enforced
    include=["reasoning.encrypted_content"] # Encrypted chain of thought is passed back in the response
)
```

```python
# take a look at the encrypted reasoning item
print(response.output[0])
```

??? note "輸出"

    ```text
    ResponseReasoningItem(id='rs_6821243503d481919e1b385c2a154d5103d2cbc5a14f3696', summary=[], type='reasoning', status=None, encrypted_content='gAAAAABoISQ24OyVRYbkYfukdJoqdzWT-3uiErKInHDC-lgAaXeky44N77j7aibc2elHISjAvX7OmUwMU1r7NgaiHSVWL5BtWgXVBp4BMFkWZpXpZY7ff5pdPFnW3VieuF2cSo8Ay7tJ4aThGUnXkNM5QJqk6_u5jwd-W9cTHjucw9ATGfGqD2qHrXyj6NEW9RmpWHV2SK41d5TpUYdN0xSuIUP98HBVZ2VGgD4MIocUm6Lx0xhRl9KUx19f7w4Sn7SCpKUQ0zwXze8UsQOVvv1HQxk_yDosbIg1SylEj38H-DNLil6yUFlWI4vGWcPn1bALXphTR2EwYVR52nD1rCFEORUd7prS99i18MUMSAhghIVv9OrpbjmfxJh8bSQaHu1ZDTMWcfC58H3i8KnogmI7V_h2TKAiLTgSQIkYRHnV3hz1XwaUqYAIhBvP6c5UxX-j_tpYpB_XCpD886L0XyJxCmfr9cwitipOhHr8zfLVwMI4ULu-P3ftw7QckIVzf71HFLNixrQlkdgTn-zM6aQl5BZcJgwwn3ylJ5ji4DQTS1H3AiTrFsEt4kyiBcE2d7tYA_m3G8L-e4-TuTDdJZtLaz-q8J12onFaKknGSyU6px8Ki4IPqnWIJw8SaFMJ5fSUYJO__myhp7lbbQwuOZHIQuvKutM-QUuR0cHus_HtfWtZZksqvVCVNBYViBxD2_KvKJvR-nN62zZ8sNiydIclt1yJfIMkiRErfRTzv92hQaUtdqz80UiW7FBcN2Lnzt8awXCz1pnGyWy_hNQe8C7W35zRxJDwFdb-f3VpanJT0tNmU5bfEWSXcIVmiMZL1clwzVNryf9Gk482LaWPwhVYrhv2MkhKMPKdeAZWVhZbgm0eTT8a4DgbwcYRGhoXMGxrXWzOdvAY536DkrI_0xsJk8-Szb5Y2EH0xPxN4-CdB_fMPP60TPEQTOP1Qc64cJcQ9p2JE5Jfz59bubF_QGajC9-FtHkD6Q5pT-6CbhuD6xrFJMgxQPcggSDaWL_4260fZCdf6nzMlwPRD3wrfsxs6rFyd8pLC-2SOh9Iv297xAjes8xcnyqvMKSuCkjARr11gJCe0EXnx87NWt2rfW8ODUU0qFYbjFx8Rj9WJtnvQBNyqp7t5LLLf12S8pyyeKTv0ePqC3xDuWdFKmELDUZjarkkCyMHoO12EbXa6YCpY_MpA01c2vV5plrcouVPSwRK0ahbPs0mQnQnDAkfi2XVS0Bzgk2GpNONGf7KWkzD7uTgDtg9UbWI0v_-f-iiBM2kKDz_dIb1opZfaxZEloyiQ2MnWQj2MRefL7WM_0c3IyTAccICN-diGn2f1im82uL9maELcbYn')
    ```

設定 `include=["reasoning.encrypted_content"]` 之後，傳回去的 reasoning item 裡多了一個 `encrypted_content` 欄位。這份加密內容代表模型的 reasoning 狀態，完全保存在 client 端，OpenAI 不保留任何資料。我們可以像之前處理 reasoning item 那樣把它傳回去。

```python
context += response.output # Add the response to the context (including the encrypted chain of thought)
tool_call = response.output[1]
args = json.loads(tool_call.arguments)



result = 20 #mocking the result of the function call

context.append({                               
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": str(result)
})

response_2 = client.responses.create(
    model="o3",
    input=context,
    tools=tools,
    store=False,
    include=["reasoning.encrypted_content"]
)

print(response_2.output_text)
```

??? note "輸出"

    ```text
    It’s currently about 20 °C in Paris.
    ```

只要改一下 `include` 欄位，就能傳回加密的 reasoning item，並用它提升模型在智慧、成本和延遲上的表現。

現在你應該具備充分運用我們最新 reasoning model 的知識了！

## Reasoning Summary

Responses API 另一個有用的功能是支援 reasoning summary。我們不會公開原始的 chain of thought token，但使用者可以取得它們的[摘要](https://platform.openai.com/docs/guides/reasoning?api-mode=responses#reasoning-summaries)。

```python
# Make a hard call to o3 with reasoning summary included

response = client.responses.create(
    model="o3",
    input="What are the main differences between photosynthesis and cellular respiration?",
    reasoning={"summary": "auto"},

    
)

# Extract the first reasoning summary text from the response object
first_reasoning_item = response.output[0]  # Should be a ResponseReasoningItem
first_summary_text = first_reasoning_item.summary[0].text if first_reasoning_item.summary else None
print("First reasoning summary text:\n", first_summary_text)
```

??? note "輸出"

    ```text
    First reasoning summary text:
     **Analyzing biological processes**

    I think the user is looking for a clear explanation of the differences between certain processes. I should create a side-by-side comparison that lists out key elements like the formulas, energy flow, locations, reactants, products, organisms involved, electron carriers, and whether the processes are anabolic or catabolic. This structured approach will help in delivering a comprehensive answer. It’s crucial to cover all aspects to ensure the user understands the distinctions clearly.
    ```

Reasoning summary 的文字讓你能讓使用者看到模型的思考過程。例如在有多次 function call 的對話中，使用者可以看到呼叫了哪些 function，以及每次呼叫背後的理由，不用等到最終的 assistant 訊息。這讓你的應用在使用體驗上更透明、更有互動性。

## 結論

善用 OpenAI Responses API 和最新的 reasoning model，你的應用可以有更高的智慧、更高的透明度和更好的效率。不管是用 reasoning summary、為合規而用 encrypted reasoning item，或是最佳化成本和延遲，這些工具都能讓你做出更穩健、更有互動性的 AI 體驗。

祝開發順利！

## 重點整理

- Reasoning token 每輪結束就會丟棄，一般多輪對話不需要帶 reasoning item。
- 一旦有 function call，就要把 reasoning item 帶回下一輪，可用 `previous_response_id` 或把 output 加回 `input`，在 SWE-bench 上約有 3% 的提升。
- 用 Responses API 能提高 cache 使用率（文中測到 40% 到 80%），省成本也降延遲。
- 不能 stateful 的組織（例如 ZDR）可以用 `reasoning.encrypted_content` 在 client 端保存加密的 reasoning 狀態。
- Reasoning summary 可以讓使用者看到每次 function call 背後的理由。

## 練習

1. 把第一個範例 response 的 `usage` 印出來，確認 reasoning token 佔了多少 output token。
2. 在 function calling 的範例裡，把加回 context 的 output 改成只帶 function call 的結果、不帶 reasoning item，比較行為有沒有差。
3. 在請求裡加上 `include=["reasoning.encrypted_content"]` 和 `store=False`，把回傳的加密 reasoning item 手動放進下一輪的 `input`，並同時開啟 reasoning summary 印出摘要。
