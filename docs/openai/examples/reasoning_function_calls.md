---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/reasoning_function_calls.ipynb
---

# 用 Reasoning 模型處理 Function Call

> 原文：[examples/reasoning_function_calls.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/reasoning_function_calls.ipynb)



## 這篇在做什麼
示範怎麼把 function calling 跟 reasoning 模型（o3、o4-mini 這類）搭配使用。重點是 reasoning 模型可能在思考過程中連續呼叫好幾次 function，所以要用 loop 來處理，並且在手動管理對話時保留 reasoning 項目。

## 學完你會
- 用 Responses API 呼叫 reasoning 模型，並看出隱藏的 reasoning tokens 用了多少
- 寫出一個 loop，處理模型串連多次 function call 的情況
- 不靠 `previous_response_id`，自己維護對話項目陣列，並保留 reasoning 和 function call 結果

## 開跑前
需要 OpenAI API key，並有權限使用 o4-mini 之類的 reasoning 模型。

OpenAI 現在支援在 [reasoning 模型](https://platform.openai.com/docs/guides/reasoning?api-mode=responses)上使用 function calling。Reasoning 模型經過訓練，會照邏輯思考鏈推理，比較適合複雜或多步驟的任務。
> _Reasoning models like o3 and o4-mini are LLMs trained with reinforcement learning to perform reasoning. Reasoning models think before they answer, producing a long internal chain of thought before responding to the user. Reasoning models excel in complex problem solving, coding, scientific reasoning, and multi-step planning for agentic workflows. They're also the best models for Codex CLI, our lightweight coding agent._

大部分情況下，透過 API 使用這些模型很簡單，跟一般的 chat 模型差不多。

不過有些細節要注意，尤其是用到 function calling 這類功能的時候。

這份 notebook 的範例全部用較新的 [Responses API](https://community.openai.com/t/introducing-the-responses-api/1140929)，它幫你把對話狀態管理包得很方便。但這裡講的原則，用舊的 chat completions API 也一樣適用。

## 呼叫 reasoning 模型

```python
# pip install openai
# Import libraries 
import json
from openai import OpenAI
from uuid import uuid4
from typing import Callable

client = OpenAI()
MODEL_DEFAULTS = {
    "model": "o4-mini", # 200,000 token context window
    "reasoning": {"effort": "low", "summary": "auto"}, # Automatically summarise the reasoning process. Can also choose "detailed" or "none"
}
```

先用 Responses API 對 reasoning 模型做一個簡單的呼叫。
我們把 reasoning effort 設成 low，然後用方便的 `output_text` 屬性取得回應。
接著可以追問後續問題，用 `previous_response_id` 讓 OpenAI 自動幫我們管理對話歷史。

```python
response = client.responses.create(
    input="Which of the last four Olympic host cities has the highest average temperature?",
    **MODEL_DEFAULTS
)
print(response.output_text)

response = client.responses.create(
    input="what about the lowest?",
    previous_response_id=response.id,
    **MODEL_DEFAULTS
)
print(response.output_text)
```

??? note "輸出"

    ```text
    Among the last four Summer Olympic host cities—Tokyo (2020), Rio de Janeiro (2016), London (2012) and Beijing (2008)—Rio de Janeiro has by far the warmest climate. Average annual temperatures are roughly:

    • Rio de Janeiro: ≈ 23 °C  
    • Tokyo: ≈ 16 °C  
    • Beijing: ≈ 13 °C  
    • London: ≈ 11 °C  

    So Rio de Janeiro has the highest average temperature.
    Among those four, London has the lowest average annual temperature, at about 11 °C.
    ```

很簡單！

我們問的問題相對複雜，模型可能需要先推理出計畫，再一步步執行，但這段推理我們看不到，只是多等一下才拿到回應。

不過如果檢查輸出，會發現模型用了一批隱藏的 reasoning tokens，它們佔用 context window，但不會顯示給終端使用者。
我們可以在回應裡看到這些 token 的數量，以及推理的摘要（但看不到實際用的 token 內容）。

```python
print(next(rx for rx in response.output if rx.type == 'reasoning').summary[0].text)
response.usage.to_dict()
```

??? note "輸出"

    ```text
    **Determining lowest temperatures**

    The user is asking about the lowest average temperatures of the last four Olympic host cities: Tokyo, Rio, London, and Beijing. I see London has the lowest average temperature at around 11°C. If I double-check the annual averages: Rio is about 23°C, Tokyo is around 16°C, and Beijing is approximately 13°C. So, my final answer is London with an average of roughly 11°C. I could provide those approximate values clearly for the user.
    ```

    ```text
    {'input_tokens': 136,
     'input_tokens_details': {'cached_tokens': 0},
     'output_tokens': 89,
     'output_tokens_details': {'reasoning_tokens': 64},
     'total_tokens': 225}
    ```

知道這些 reasoning tokens 很重要，因為這表示 context window 會比傳統 chat 模型消耗得更快。

## 呼叫自訂 function
如果我們問的複雜請求同時需要用到自訂 tool，會怎樣？
* 假設我們還有一些關於奧運城市的問題，而且有一個內部資料庫，裡面存著每個城市的 ID。
* 模型可能需要在推理到一半時呼叫我們的 tool，才能回傳結果。
* 我們來做一個產生隨機 UUID 的 function，然後請模型針對這些 UUID 做推理。


```python

def get_city_uuid(city: str) -> str:
    """Just a fake tool to return a fake UUID"""
    uuid = str(uuid4())
    return f"{city} ID: {uuid}"

# The tool schema that we will pass to the model
tools = [
    {
        "type": "function",
        "name": "get_city_uuid",
        "description": "Retrieve the internal ID for a city from the internal database. Only invoke this function if the user needs to know the internal ID for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The name of the city to get information about"}
            },
            "required": ["city"]
        }
    }
]

# This is a general practice - we need a mapping of the tool names we tell the model about, and the functions that implement them.
tool_mapping = {
    "get_city_uuid": get_city_uuid
}

# Let's add this to our defaults so we don't have to pass it every time
MODEL_DEFAULTS["tools"] = tools

response = client.responses.create(
    input="What's the internal ID for the lowest-temperature city?",
    previous_response_id=response.id,
    **MODEL_DEFAULTS)
print(response.output_text)
```

這次沒有拿到 `output_text`。來看看 response 的 output。

```python
response.output
```

??? note "輸出"

    ```text
    [ResponseReasoningItem(id='rs_68246219e8288191af051173b1d53b3f0c4fbdb0d4a46f3c', summary=[], type='reasoning', status=None),
     ResponseFunctionToolCall(arguments='{"city":"London"}', call_id='call_Mx6pyTjCkSkmASETsVASogoC', name='get_city_uuid', type='function_call', id='fc_6824621b8f6c8191a8095df7230b611e0c4fbdb0d4a46f3c', status='completed')]
    ```

除了 reasoning 步驟，模型也正確判斷出需要呼叫 tool，並回傳要送給我們 function 的指令。

接著我們執行 function，把結果送回給模型，讓它繼續推理。
Function 的回應是一種特殊的訊息，所以下一則訊息也要組成特殊的 input 格式：
```json
{
    "type": "function_call_output",
    "call_id": function_call.call_id,
    "output": tool_output
}
```

```python
# Extract the function call(s) from the response
new_conversation_items = []
function_calls = [rx for rx in response.output if rx.type == 'function_call']
for function_call in function_calls:
    target_tool = tool_mapping.get(function_call.name)
    if not target_tool:
        raise ValueError(f"No tool found for function call: {function_call.name}")
    arguments = json.loads(function_call.arguments) # Load the arguments as a dictionary
    tool_output = target_tool(**arguments) # Invoke the tool with the arguments
    new_conversation_items.append({
        "type": "function_call_output",
        "call_id": function_call.call_id, # We map the response back to the original function call
        "output": tool_output
    })
```

```python
response = client.responses.create(
    input=new_conversation_items,
    previous_response_id=response.id,
    **MODEL_DEFAULTS
)
print(response.output_text)
```

??? note "輸出"

    ```text
    The internal ID for London is 816bed76-b956-46c4-94ec-51d30b022725.
    ```

這裡運作得很好，因為我們知道只需要一次 function call 模型就能回應。但我們也得考慮到，推理過程可能需要執行多次 tool call 的情況。

我們再加第二個 function 來做網路搜尋。

OpenAI 的 web search tool 在 reasoning 模型上沒辦法直接用（截至 2025 年 5 月，之後可能會改變），但用 4o mini 或其他支援 web search 的模型自己做一個自訂的搜尋 function 並不難。

```python
def web_search(query: str) -> str:
    """Search the web for information and return back a summary of the results"""
    result = client.responses.create(
        model="gpt-4o-mini",
        input=f"Search the web for '{query}' and reply with only the result.",
        tools=[{"type": "web_search_preview"}],
    )
    return result.output_text

tools.append({
        "type": "function",
        "name": "web_search",
        "description": "Search the web for information and return back a summary of the results",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query to search the web for."}
            },
            "required": ["query"]
        }
    })
tool_mapping["web_search"] = web_search
```

## 依序執行多個 function

有些 OpenAI 模型支援 `parallel_tool_calls` 參數，讓模型回傳一個 function 陣列，我們就能平行執行。不過 reasoning 模型可能產生必須依序執行的 function call，因為有些步驟會依賴前面步驟的結果。
所以我們要定義一個通用的模式，來處理任意複雜的推理流程：
* 在對話的每一步，啟動一個 loop
* 如果 response 裡有 function call，就要假設推理還在進行，把 function 結果（以及中間的 reasoning）送回模型繼續推論
* 如果沒有 function call，而是收到 type 為 'message' 的 response.output，就可以確定 agent 已經推理完了，跳出 loop

```python
# Let's wrap our logic above into a function which we can use to invoke tool calls.
def invoke_functions_from_response(response,
                                   tool_mapping: dict[str, Callable] = tool_mapping
                                   ) -> list[dict]:
    """Extract all function calls from the response, look up the corresponding tool function(s) and execute them.
    (This would be a good place to handle asynchroneous tool calls, or ones that take a while to execute.)
    This returns a list of messages to be added to the conversation history.
    """
    intermediate_messages = []
    for response_item in response.output:
        if response_item.type == 'function_call':
            target_tool = tool_mapping.get(response_item.name)
            if target_tool:
                try:
                    arguments = json.loads(response_item.arguments)
                    print(f"Invoking tool: {response_item.name}({arguments})")
                    tool_output = target_tool(**arguments)
                except Exception as e:
                    msg = f"Error executing function call: {response_item.name}: {e}"
                    tool_output = msg
                    print(msg)
            else:
                msg = f"ERROR - No tool registered for function call: {response_item.name}"
                tool_output = msg
                print(msg)
            intermediate_messages.append({
                "type": "function_call_output",
                "call_id": response_item.call_id,
                "output": tool_output
            })
        elif response_item.type == 'reasoning':
            print(f'Reasoning step: {response_item.summary}')
    return intermediate_messages
```

現在來示範剛剛講的 loop。

```python
initial_question = (
    "What are the internal IDs for the cities that have hosted the Olympics in the last 20 years, "
    "and which of those cities have recent news stories (in 2025) about the Olympics? "
    "Use your internal tools to look up the IDs and the web search tool to find the news stories."
)

# We fetch a response and then kick off a loop to handle the response
response = client.responses.create(
    input=initial_question,
    **MODEL_DEFAULTS,
)
while True:   
    function_responses = invoke_functions_from_response(response)
    if len(function_responses) == 0: # We're done reasoning
        print(response.output_text)
        break
    else:
        print("More reasoning required, continuing...")
        response = client.responses.create(
            input=function_responses,
            previous_response_id=response.id,
            **MODEL_DEFAULTS
        )
```

??? note "輸出"

    ```text
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Beijing'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'London'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Rio de Janeiro'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Tokyo'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Paris'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Turin'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Vancouver'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Sochi'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: get_city_uuid({'city': 'Pyeongchang'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: web_search({'query': '2025 Beijing Olympics news'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: web_search({'query': '2025 London Olympics news'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: web_search({'query': '2025 Rio de Janeiro Olympics news'})
    More reasoning required, continuing...
    Reasoning step: []
    Invoking tool: web_search({'query': '2025 Tokyo Olympics news'})
    More reasoning required, continuing...
    Reasoning step: []
    ... (省略 59 行)
    ```

## 手動編排對話
目前為止都很順利！看模型暫停執行去跑一個 function，再繼續推理，真的很酷。
實務上，上面的例子其實很簡單，正式環境的情況可能複雜很多：
* Context window 可能長得太大，我們會想剪掉較舊、較不相關的訊息，或是把到目前為止的對話做摘要
* 我們可能想讓使用者在對話中前後切換，並重新產生答案
* 我們可能想把訊息存在自己的資料庫做稽核，而不是依賴 OpenAI 的儲存和編排
* 等等

這些情況下，我們會想完全掌控對話。不用 `previous_message_id`，而是把 API 當成「無狀態」的，自己建立並維護一個對話項目陣列，每次都當作 input 送給模型。

這對 reasoning 模型來說有一些特別的細節要注意。
* 尤其是，一定要在對話歷史裡保留 reasoning 和 function call 的回應。
* 模型就是靠這些來記得它已經走過哪些思考鏈步驟。如果沒包含，API 會報錯。

我們用手動編排訊息的方式，把上面的例子再跑一次，並追蹤 token 用量。

---
*注意，下面的程式碼是為了好讀而寫的，實務上處理邊界情況可能需要更完整的流程*

```python
# Let's initialise our conversation with the first user message
total_tokens_used = 0
user_messages = [
    (
        "Of those cities that have hosted the summer Olympic games in the last 20 years - "
        "do any of them have IDs beginning with a number and a temperate climate? "
        "Use your available tools to look up the IDs for each city and make sure to search the web to find out about the climate."
    ),
    "Great thanks! We've just updated the IDs - could you please check again?"
    ]

conversation = []
for message in user_messages:
    conversation_item = {
        "role": "user",
        "type": "message",
        "content": message
    }
    print(f"{'*' * 79}\nUser message: {message}\n{'*' * 79}")
    conversation.append(conversation_item)
    while True: # Response loop
        response = client.responses.create(
            input=conversation,
            **MODEL_DEFAULTS
        )
        total_tokens_used += response.usage.total_tokens
        reasoning = [rx.to_dict() for rx in response.output if rx.type == 'reasoning']
        function_calls = [rx.to_dict() for rx in response.output if rx.type == 'function_call']
        messages = [rx.to_dict() for rx in response.output if rx.type == 'message']
        if len(reasoning) > 0:
            print("More reasoning required, continuing...")
            # Ensure we capture any reasoning steps
            conversation.extend(reasoning)
            print('\n'.join(s['text'] for r in reasoning for s in r['summary']))
        if len(function_calls) > 0:
            function_outputs = invoke_functions_from_response(response)
            # Preserve order of function calls and outputs in case of multiple function calls (currently not supported by reasoning models, but worth considering)
            interleaved = [val for pair in zip(function_calls, function_outputs) for val in pair]
            conversation.extend(interleaved)
        if len(messages) > 0:
            print(response.output_text)
            conversation.extend(messages)
        if len(function_calls) == 0:  # No more functions = We're done reasoning and we're ready for the next user message
            break
print(f"Total tokens used: {total_tokens_used} ({total_tokens_used / 200_000:.2%} of o4-mini's context window)")
```

??? note "輸出"

    ```text
    *******************************************************************************
    User message: Of those cities that have hosted the summer Olympic games in the last 20 years - do any of them have IDs beginning with a number and a temperate climate? Use your available tools to look up the IDs for each city and make sure to search the web to find out about the climate.
    *******************************************************************************
    More reasoning required, continuing...
    **Clarifying Olympic Cities**

    The user is asking about cities that hosted the Summer Olympics in the last 20 years. The relevant years to consider are 2004 Athens, 2008 Beijing, 2012 London, 2016 Rio de Janeiro, and 2020 Tokyo. If we're considering 2025, then 2004 would actually be 21 years ago, so I should focus instead on the years from 2005 onwards. Therefore, the cities to include are Beijing, London, Rio, and Tokyo. I’ll exclude Paris since it hasn’t hosted yet.
    Reasoning step: [Summary(text="**Clarifying Olympic Cities**\n\nThe user is asking about cities that hosted the Summer Olympics in the last 20 years. The relevant years to consider are 2004 Athens, 2008 Beijing, 2012 London, 2016 Rio de Janeiro, and 2020 Tokyo. If we're considering 2025, then 2004 would actually be 21 years ago, so I should focus instead on the years from 2005 onwards. Therefore, the cities to include are Beijing, London, Rio, and Tokyo. I’ll exclude Paris since it hasn’t hosted yet.", type='summary_text')]
    Invoking tool: get_city_uuid({'city': 'Beijing'})
    Invoking tool: get_city_uuid({'city': 'London'})
    Invoking tool: get_city_uuid({'city': 'Rio de Janeiro'})
    Invoking tool: get_city_uuid({'city': 'Tokyo'})
    More reasoning required, continuing...

    Reasoning step: []
    Invoking tool: web_search({'query': 'London climate'})
    Invoking tool: web_search({'query': 'Tokyo climate'})
    More reasoning required, continuing...

    I looked up the internal IDs and climates for each Summer-Olympics host of the last 20 years:

    • Beijing  
      – ID: 937b336d-2708-4ad3-8c2f-85ea32057e1e (starts with “9”)  
      – Climate: humid continental (cold winters, hot summers) → not temperate

    • London  
      – ID: ee57f35a-7d1b-4888-8833-4ace308fa004 (starts with “e”)  
      – Climate: temperate oceanic (mild, moderate rainfall)

    • Rio de Janeiro  
      – ID: 2a70c45e-a5b4-4e42-8d2b-6c1dbb2aa2d9 (starts with “2”)  
      – Climate: tropical (hot/wet)

    • Tokyo  
      – ID: e5de3686-a7d2-42b8-aca5-6b6e436083ff (starts with “e”)  
      – Climate: humid subtropical (hot, humid summers; mild winters)

    The only IDs that begin with a numeral are Beijing (“9…”) and Rio (“2…”), but neither city has a temperate climate. Therefore, none of the last-20-years hosts combine an ID starting with a number with a temperate climate.
    *******************************************************************************
    User message: Great thanks! We've just updated the IDs - could you please check again?
    ... (省略 28 行)
    ```

## 總結
這份 cookbook 示範了怎麼把 function calling 跟 OpenAI 的 reasoning 模型結合，完成依賴外部資料來源（包括網路搜尋）的多步驟任務。

重要的是，我們講了 function calling 流程裡 reasoning 模型特有的細節：
* 模型可能依序做出多個 function call 或 reasoning 步驟，有些步驟依賴前面步驟的結果
* 我們無法預知會有幾步，所以必須用 loop 來處理 response
* Responses API 用 `previous_response_id` 參數讓編排很輕鬆，但需要手動控制時，必須維持對話項目的正確順序，才能保留「思考鏈」

---

這裡的範例都很簡單，但你可以想像這個技巧如何延伸到更真實的場景，例如：

* 查詢客戶的交易紀錄和近期往來信件，判斷他是否符合優惠資格
* 調閱近期交易 log、地理位置資料和裝置 metadata，評估交易是詐欺的可能性
* 查看公司內部 HR 資料庫，取得員工的福利使用情況、年資和近期政策變更，回答個人化的 HR 問題
* 讀取內部儀表板、競爭對手新聞和市場分析，整理出符合主管關注領域的每日簡報

## 重點整理
- Reasoning 模型會產生隱藏的 reasoning tokens，佔用 context window 但看不到內容
- 模型可能在推理中途要求呼叫 function，且次數不固定，所以要用 loop 處理
- 判斷結束的條件是 output 裡出現 type 為 message 的項目，而不是有沒有 function call
- 用 `previous_response_id` 最省事，手動管理時則必須保留 reasoning 和 function call 結果，否則 API 會報錯

## 練習
1. 把第一個範例的 reasoning effort 從 low 改成 high，比較 reasoning tokens 的數量差多少。
2. 把產生 UUID 的 function 換成一個回傳固定資料的 function（例如城市名稱對應 ID），看模型怎麼使用結果。
3. 在手動編排的版本裡，故意把 reasoning 項目從歷史中拿掉，觀察 API 回傳什麼錯誤。
