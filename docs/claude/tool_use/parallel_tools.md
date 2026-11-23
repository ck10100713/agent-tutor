---
translated: true
source: tool_use/parallel_tools.ipynb
---

# 用 batch tool 鼓勵平行 tool call

> 原文：[tool_use/parallel_tools.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/parallel_tools.ipynb)

用 batch tool 這個 meta-pattern，鼓勵 Claude 在同一個 turn 裡平行呼叫多個 tool。

## 這篇在做什麼

示範 Claude 怎麼在一個 turn 裡同時呼叫多個 tool，以及怎麼把每個 `tool_use` 都回覆完。最後再加一個 batch tool，比較兩種做法。

## 學完你會

- 知道平行 tool call 預設就是開的，並能正確回傳同一個 turn 裡所有的 `tool_result`
- 寫出一個把多個 tool 呼叫包起來的 `batch_tool`
- 寫一個同時處理 `batch_tool` 和一般 tool call 的 helper

## 開跑前

需要 Anthropic API key。

Claude 預設可以在同一個 assistant turn 呼叫多個 tool（除非你設 `disable_parallel_tool_use`），而且現在的模型遇到明顯需要多個 tool 的請求，通常會自己這樣做。不過有些 prompt 下模型還是可能一次只呼叫一個，每個 call 就多一趟來回。要讓批次呼叫更明確，可以用 "batch tool"：一個專門用來包裝其他 tool 呼叫的 meta-tool，由你的程式碼拆開後一起執行。

這份 notebook 先示範一般的多 tool 情境，和一個回覆 turn 裡每個 `tool_use` block 的迴圈，再加上 batch tool 做比較。batch tool 是可選的做法：如果模型本來就在一個 turn 回傳你要的所有 call（像下面記錄的這次執行），就不需要它。

```python
from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-sonnet-5-5"
```

## 用多個 tool call 做一次查詢

預設行為是允許 Claude 平行呼叫 tool。搭配預設的 `tool_choice`（`auto`），Claude 可以呼叫你指定的任一個 tool，也可以在同一個 assistant turn 裡呼叫不只一個。

我們給 Claude 一個 `get_weather` 和一個 `get_time` tool。

```python
def get_weather(location):
    # Pretend to get the weather, and just return a fixed value.
    return f"The weather in {location} is 72 degrees and sunny."


def get_time(location):
    # Pretend to get the time, and just return a fixed value.
    return f"The time in {location} is 12:32 PM."


weather_tool = {
    "name": "get_weather",
    "description": "Gets the weather for in a given location",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city and state, e.g. San Francisco, CA",
            },
        },
        "required": ["location"],
    },
}

time_tool = {
    "name": "get_time",
    "description": "Gets the time in a given location",
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The city and state, e.g. San Francisco, CA",
            },
        },
        "required": ["location"],
    },
}


def process_tool_call(tool_name, tool_input):
    if tool_name == "get_weather":
        return get_weather(tool_input["location"])
    elif tool_name == "get_time":
        return get_time(tool_input["location"])
    else:
        raise ValueError(f"Unexpected tool name: {tool_name}")
```

接著把這些 tool 交給 Claude 並做一次查詢。

```python
def make_query_and_print_result(messages, tools=None):
    response = client.messages.create(
        model=MODEL_NAME,
        messages=messages,
        max_tokens=1000,
        tool_choice={"type": "auto"},
        tools=tools or [weather_tool, time_tool],
    )

    for block in response.content:
        match block.type:
            case "text":
                print(block.text)
            case "tool_use":
                print(f"Tool: {block.name}({block.input})")
            case "thinking" | "redacted_thinking":
                pass  # the model may emit a leading thinking block; nothing to print
            case _:
                raise ValueError(f"Unexpected block type: {block.type}")

    return response


MESSAGES = [{"role": "user", "content": "What's the weather and time in San Francisco?"}]

response = make_query_and_print_result(MESSAGES)
```

??? note "輸出"

    ```text
    Tool: get_weather({'location': 'San Francisco, CA'})
    Tool: get_time({'location': 'San Francisco, CA'})
    ```

這次記錄下來的執行裡，Claude 在同一個 turn 就要求了兩個 tool，這在現在的模型上很常見。換個 prompt 或模型，你可能只拿到一個 call，要等你回傳第一個結果才會有第二個，多一趟來回。

不管哪種情況，client 端正確的做法都一樣：把這個 turn 裡**每一個** `tool_use` block 都用對應的 `tool_result` 回覆，全部放在同一則 user message，再繼續。

```python
# Answer every tool_use block in the turn (there may be one or several)
tool_calls = [block for block in response.content if block.type == "tool_use"]

MESSAGES.append({"role": "assistant", "content": response.content})
MESSAGES.append(
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": process_tool_call(tool_call.name, tool_call.input),
            }
            for tool_call in tool_calls
        ],
    }
)

response = make_query_and_print_result(MESSAGES)
```

??? note "輸出"

    ```text
    In San Francisco, CA it's 12:32 PM. The weather is sunny and 72°F.
    ```

兩個結果一起回傳後，Claude 在下一次回應就能回答。如果你的執行是一個一個產生 call，就多花了一輪 request/response：這種循序的「來回」就是下面 batch tool 想減少的。

## 加入 batch tool

我們加一個 `batch_tool`，讓 Claude 有機會把多個 tool call 合併成一個。

```python
import json

batch_tool = {
    "name": "batch_tool",
    "description": "Invoke multiple other tool calls simultaneously",
    "input_schema": {
        "type": "object",
        "properties": {
            "invocations": {
                "type": "array",
                "description": "The tool calls to invoke",
                "items": {
                    "types": "object",
                    "properties": {
                        "name": {
                            "types": "string",
                            "description": "The name of the tool to invoke",
                        },
                        "arguments": {
                            "types": "string",
                            "description": "The arguments to the tool",
                        },
                    },
                    "required": ["name", "arguments"],
                },
            }
        },
        "required": ["invocations"],
    },
}


def process_tool_with_maybe_batch(tool_name, tool_input):
    if tool_name == "batch_tool":
        results = []
        for invocation in tool_input["invocations"]:
            results.append(
                process_tool_call(invocation["name"], json.loads(invocation["arguments"]))
            )
        return "\n".join(results)
    else:
        return process_tool_call(tool_name, tool_input)
```

現在把原本的 weather、time tool 加上這個 batch tool 一起給 Claude，用一個同時需要天氣和時間的查詢，看看會發生什麼事。

```python
MESSAGES = [{"role": "user", "content": "What's the weather and time in San Francisco?"}]

response = make_query_and_print_result(MESSAGES, tools=[weather_tool, time_tool, batch_tool])
```

??? note "輸出"

    ```text
    Tool: get_weather({'location': 'San Francisco, CA'})
    Tool: get_time({'location': 'San Francisco, CA'})
    ```

有了 batch tool，Claude 可以把呼叫包進一個 `batch_tool`，也可以像這次記錄的執行那樣，直接平行呼叫 `get_weather` 和 `get_time`。兩種都能讓所有 call 出現在同一個 turn。下面的 helper 兩種格式都能處理，遇到 `batch_tool` 就拆開。

```python
# Answer every tool_use block in the turn; batch_tool invocations are unpacked by the helper
tool_calls = [block for block in response.content if block.type == "tool_use"]

MESSAGES.append({"role": "assistant", "content": response.content})
MESSAGES.append(
    {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": process_tool_with_maybe_batch(tool_call.name, tool_call.input),
            }
            for tool_call in tool_calls
        ],
    }
)

response = make_query_and_print_result(MESSAGES)
```

??? note "輸出"

    ```text
    In San Francisco, CA, it's 12:32 PM, and the weather is sunny and 72°F.
    ```

## 重點整理

- 平行 tool call 預設是開的，模型常常不需要 batch tool 就會一次呼叫多個。
- 一個 turn 裡有幾個 `tool_use`，就要回幾個 `tool_result`，而且放在同一則 user message。
- batch tool 是把多個呼叫包成一個的 meta-tool，由你的程式碼拆開執行。
- 實務上要同時處理 `batch_tool` 和直接的平行 call 兩種形狀。

## 練習

1. 加第三個 tool（例如 `get_stock_price`），改 query 讓它同時需要三個 tool，看是不是一個 turn 全出現。
2. 在 request 設 `disable_parallel_tool_use=True`，觀察 call 的數量和來回次數有什麼變化。
3. 改寫 helper，讓它把 `batch_tool` 裡的呼叫用 `concurrent.futures` 真正平行執行。
