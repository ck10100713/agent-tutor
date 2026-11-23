---
translated: true
source: examples/Function_calling_with_an_OpenAPI_spec.ipynb
---

# 用 OpenAPI 規格做 function calling

> 原文：[examples/Function_calling_with_an_OpenAPI_spec.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Function_calling_with_an_OpenAPI_spec.ipynb)

## 這篇在做什麼

把一份 OpenAPI 規格轉成 chat completions API 能用的 function 定義，再讓模型依使用者指示產生呼叫這些 function 的 JSON 參數，並串接多個呼叫完成複雜操作。範例 API 是一個活動（event）管理服務。

## 學完你會

- 寫 `openapi_to_functions`，解析 `$ref`、取出 `operationId`、描述與參數，產生 function 定義清單
- 把這些定義交給 chat completions API，讓模型產生呼叫參數
- 在自己的程式裡執行 function 呼叫，並把多個呼叫串起來

## 開跑前

- 需要 `OPENAI_API_KEY`，呼叫模型會產生費用
- 建議先看過 function calling 的基礎教學


網路上很多東西都由 RESTful API 驅動。讓 GPT 能呼叫它們，就開啟了很多可能性。這個 notebook 示範怎麼讓 GPT 聰明地呼叫 API，用到 OpenAPI 規格和串接的 function call。

[OpenAPI Specification (OAS)](https://swagger.io/specification/) 是公認的標準，用機器可讀、可解讀的格式描述 RESTful API 的細節。它讓人和電腦都能理解服務的功能，也可以用來教 GPT 怎麼呼叫 API。

這個 notebook 分成兩大部分：

1. 怎麼把範例 OpenAPI 規格轉成 chat completions API 用的 function 定義清單。
2. 怎麼用 chat completions API 依使用者指示聰明地呼叫這些 function。

建議繼續之前先熟悉 [function-calling](How_to_call_functions_with_chat_models.md)。


```python
!pip install -q jsonref # for resolving $ref's in the OpenAPI spec
!pip install -q openai
```

??? note "輸出"

    ```text
    DEPRECATION: textract 1.6.5 has a non-standard dependency specifier extract-msg<=0.29.*. pip 23.3 will enforce this behaviour change. A possible replacement is to upgrade to a newer version of textract or contact the author to suggest that they release a version with a conforming dependency specifiers. Discussion can be found at https://github.com/pypa/pip/issues/12063

    [notice] A new release of pip is available: 23.2.1 -> 23.3.1
    [notice] To update, run: pip install --upgrade pip
    DEPRECATION: textract 1.6.5 has a non-standard dependency specifier extract-msg<=0.29.*. pip 23.3 will enforce this behaviour change. A possible replacement is to upgrade to a newer version of textract or contact the author to suggest that they release a version with a conforming dependency specifiers. Discussion can be found at https://github.com/pypa/pip/issues/12063

    [notice] A new release of pip is available: 23.2.1 -> 23.3.1
    [notice] To update, run: pip install --upgrade pip
    ```

```python
import os
import json
import jsonref
from openai import OpenAI
import requests
from pprint import pp

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

## 怎麼把 OpenAPI 規格轉成 function 定義


這裡用的範例 OpenAPI 規格是用 `gpt-4` 產生的。我們會把這份範例規格轉成一組 function 定義，提供給 chat completion API。模型會依使用者的指示，產生一個 JSON 物件，裡面是呼叫這些 function 所需的參數。

繼續之前，先看看這份產生出來的規格。OpenAPI 規格包含 API 的 endpoint、支援的操作、接受的參數、可處理的請求，以及回傳的回應。規格是用 JSON 格式定義。

規格中的 endpoint 包含這些操作：

- 列出所有活動
- 建立新活動
- 依 ID 取得活動
- 依 ID 刪除活動
- 依 ID 更新活動名稱

規格裡每個操作都有 `operationId`，我們把規格解析成 function 規格時，會用它當 function 名稱。規格也包含 schema，定義每個操作的參數的資料型別與結構。

你可以在這裡看到 schema：


```python
with open('./data/example_events_openapi.json', 'r') as f:
    openapi_spec = jsonref.loads(f.read()) # it's important to load with jsonref, as explained below

display(openapi_spec)
```

??? note "輸出"

    ```text
    {'openapi': '3.0.0',
     'info': {'version': '1.0.0',
      'title': 'Event Management API',
      'description': 'An API for managing event data'},
     'paths': {'/events': {'get': {'summary': 'List all events',
        'operationId': 'listEvents',
        'responses': {'200': {'description': 'A list of events',
          'content': {'application/json': {'schema': {'type': 'array',
             'items': {'type': 'object',
              'properties': {'id': {'type': 'string'},
               'name': {'type': 'string'},
               'date': {'type': 'string', 'format': 'date-time'},
               'location': {'type': 'string'}},
              'required': ['name', 'date', 'location']}}}}}}},
       'post': {'summary': 'Create a new event',
        'operationId': 'createEvent',
        'requestBody': {'required': True,
         'content': {'application/json': {'schema': {'type': 'object',
            'properties': {'id': {'type': 'string'},
             'name': {'type': 'string'},
             'date': {'type': 'string', 'format': 'date-time'},
             'location': {'type': 'string'}},
            'required': ['name', 'date', 'location']}}}},
        'responses': {'201': {'description': 'The event was created',
          'content': {'application/json': {'schema': {'type': 'object',
             'properties': {'id': {'type': 'string'},
              'name': {'type': 'string'},
              'date': {'type': 'string', 'format': 'date-time'},
              'location': {'type': 'string'}},
             'required': ['name', 'date', 'location']}}}}}}},
      '/events/{id}': {'get': {'summary': 'Retrieve an event by ID',
        'operationId': 'getEventById',
        'parameters': [{'name': 'id',
          'in': 'path',
          'required': True,
          'schema': {'type': 'string'}}],
        'responses': {'200': {'description': 'The event',
          'content': {'application/json': {'schema': {'type': 'object',
             'properties': {'id': {'type': 'string'},
              'name': {'type': 'string'},
    ... (省略 35 行)
    ```

對 OpenAPI 規格有了清楚的了解後，就可以把它解析成 function 規格。

我們可以寫一個簡單的 `openapi_to_functions` 函式來產生定義清單，每個 function 是一個 dictionary，包含下列 key：

- `name`：對應 OpenAPI 規格裡定義的 API endpoint 的 operation 識別碼。
- `description`：function 的簡短描述或摘要，概述這個 function 做什麼。
- `parameters`：定義 function 預期輸入參數的 schema，說明每個參數的型別、必填或選填，以及其他相關細節。

對 schema 裡定義的每個 endpoint，我們需要做這些事：

1. **解析 JSON reference**：在 OpenAPI 規格裡，常用 JSON reference（也叫 $ref）避免重複。這些 reference 指向會在多處使用的定義。例如多個 API endpoint 回傳相同的物件結構時，可以只定義一次，在需要的地方引用。我們需要解析這些 reference，並用它們指向的內容取代。

2. **取得 function 的名稱：**我們直接用 operationId 當 function 名稱。也可以改用 endpoint 的 path 加操作當 function 名稱。

3. **取得描述和參數：**我們會遍歷 `description`、`summary`、`requestBody` 和 `parameters` 欄位，填入 function 的描述和參數。

實作如下：


```python
def openapi_to_functions(openapi_spec):
    functions = []

    for path, methods in openapi_spec["paths"].items():
        for method, spec_with_ref in methods.items():
            # 1. Resolve JSON references.
            spec = jsonref.replace_refs(spec_with_ref)

            # 2. Extract a name for the functions.
            function_name = spec.get("operationId")

            # 3. Extract a description and parameters.
            desc = spec.get("description") or spec.get("summary", "")

            schema = {"type": "object", "properties": {}}

            req_body = (
                spec.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema")
            )
            if req_body:
                schema["properties"]["requestBody"] = req_body

            params = spec.get("parameters", [])
            if params:
                param_properties = {
                    param["name"]: param["schema"]
                    for param in params
                    if "schema" in param
                }
                schema["properties"]["parameters"] = {
                    "type": "object",
                    "properties": param_properties,
                }

            functions.append(
                {"type": "function", "function": {"name": function_name, "description": desc, "parameters": schema}}
            )

    return functions


functions = openapi_to_functions(openapi_spec)

for function in functions:
    pp(function)
    print()
```

??? note "輸出"

    ```text
    {'type': 'function',
     'function': {'name': 'listEvents',
                  'description': 'List all events',
                  'parameters': {'type': 'object', 'properties': {}}}}

    {'type': 'function',
     'function': {'name': 'createEvent',
                  'description': 'Create a new event',
                  'parameters': {'type': 'object',
                                 'properties': {'requestBody': {'type': 'object',
                                                                'properties': {'id': {'type': 'string'},
                                                                               'name': {'type': 'string'},
                                                                               'date': {'type': 'string',
                                                                                        'format': 'date-time'},
                                                                               'location': {'type': 'string'}},
                                                                'required': ['name',
                                                                             'date',
                                                                             'location']}}}}}

    {'type': 'function',
     'function': {'name': 'getEventById',
                  'description': 'Retrieve an event by ID',
                  'parameters': {'type': 'object',
                                 'properties': {'parameters': {'type': 'object',
                                                               'properties': {'id': {'type': 'string'}}}}}}}

    {'type': 'function',
     'function': {'name': 'deleteEvent',
                  'description': 'Delete an event by ID',
                  'parameters': {'type': 'object',
                                 'properties': {'parameters': {'type': 'object',
                                                               'properties': {'id': {'type': 'string'}}}}}}}

    {'type': 'function',
     'function': {'name': 'updateEventDetails',
                  'description': "Update an event's details by ID",
                  'parameters': {'type': 'object',
                                 'properties': {'requestBody': {'type': 'object',
                                                                'properties': {'name': {'type': 'string'},
                                                                               'date': {'type': 'string',
    ... (省略 7 行)
    ```

## 怎麼讓 GPT 呼叫這些 function


現在有了這些 function 定義，就可以讓 GPT 依使用者輸入聰明地呼叫它們。

要注意的是，chat completions API 不會執行 function，它只會產生 JSON，讓你在自己的程式裡用來呼叫 function。

更多 function calling 的資訊，請看我們專門的 [function-calling 指南](How_to_call_functions_with_chat_models.md)。


```python
SYSTEM_MESSAGE = """
You are a helpful assistant.
Respond to the following prompt by using function_call and then summarize actions.
Ask for clarification if a user request is ambiguous.
"""

# Maximum number of function calls allowed to prevent infinite or lengthy loops
MAX_CALLS = 5


def get_openai_response(functions, messages):
    return client.chat.completions.create(
        model="gpt-3.5-turbo-16k",
        tools=functions,
        tool_choice="auto",  # "auto" means the model can pick between generating a message or calling a function.
        temperature=0,
        messages=messages,
    )


def process_user_instruction(functions, instruction):
    num_calls = 0
    messages = [
        {"content": SYSTEM_MESSAGE, "role": "system"},
        {"content": instruction, "role": "user"},
    ]

    while num_calls < MAX_CALLS:
        response = get_openai_response(functions, messages)
        message = response.choices[0].message
        print(message)
        try:
            print(f"\n>> Function call #: {num_calls + 1}\n")
            pp(message.tool_calls)
            messages.append(message)

            # For the sake of this example, we'll simply add a message to simulate success.
            # Normally, you'd want to call the function here, and append the results to messages.
            messages.append(
                {
                    "role": "tool",
                    "content": "success",
                    "tool_call_id": message.tool_calls[0].id,
                }
            )

            num_calls += 1
        except:
            print("\n>> Message:\n")
            print(message.content)
            break

    if num_calls >= MAX_CALLS:
        print(f"Reached max chained function calls: {MAX_CALLS}")


USER_INSTRUCTION = """
Instruction: Get all the events.
Then create a new event named AGI Party.
Then delete event with id 2456.
"""

process_user_instruction(functions, USER_INSTRUCTION)
```

??? note "輸出"

    ```text
    ChatCompletionMessage(content=None, role='assistant', function_call=None, tool_calls=[ChatCompletionMessageToolCall(id='call_jmlvEyMRMvOtB80adX9RbqIV', function=Function(arguments='{}', name='listEvents'), type='function')])

    >> Function call #: 1

    [ChatCompletionMessageToolCall(id='call_jmlvEyMRMvOtB80adX9RbqIV', function=Function(arguments='{}', name='listEvents'), type='function')]
    ChatCompletionMessage(content=None, role='assistant', function_call=None, tool_calls=[ChatCompletionMessageToolCall(id='call_OOPOY7IHMq3T7Ib71JozlUQJ', function=Function(arguments='{\n  "requestBody": {\n    "id": "1234",\n    "name": "AGI Party",\n    "date": "2022-12-31",\n    "location": "New York"\n  }\n}', name='createEvent'), type='function')])

    >> Function call #: 2

    [ChatCompletionMessageToolCall(id='call_OOPOY7IHMq3T7Ib71JozlUQJ', function=Function(arguments='{\n  "requestBody": {\n    "id": "1234",\n    "name": "AGI Party",\n    "date": "2022-12-31",\n    "location": "New York"\n  }\n}', name='createEvent'), type='function')]
    ChatCompletionMessage(content=None, role='assistant', function_call=None, tool_calls=[ChatCompletionMessageToolCall(id='call_Kxluu3fJSOsZNNCn3JIlWAAM', function=Function(arguments='{\n  "parameters": {\n    "id": "2456"\n  }\n}', name='deleteEvent'), type='function')])

    >> Function call #: 3

    [ChatCompletionMessageToolCall(id='call_Kxluu3fJSOsZNNCn3JIlWAAM', function=Function(arguments='{\n  "parameters": {\n    "id": "2456"\n  }\n}', name='deleteEvent'), type='function')]
    ChatCompletionMessage(content='Here are the actions I performed:\n\n1. Retrieved all the events.\n2. Created a new event named "AGI Party" with the ID "1234", scheduled for December 31, 2022, in New York.\n3. Deleted the event with the ID "2456".', role='assistant', function_call=None, tool_calls=None)

    >> Function call #: 4

    None

    >> Message:

    Here are the actions I performed:

    1. Retrieved all the events.
    2. Created a new event named "AGI Party" with the ID "1234", scheduled for December 31, 2022, in New York.
    3. Deleted the event with the ID "2456".
    ```

### 結論

我們示範了怎麼把 OpenAPI 規格轉成 function 規格，交給 GPT 讓它聰明地呼叫，也展示了怎麼把這些呼叫串起來執行複雜操作。

這個系統可能的延伸方向，包括處理需要條件判斷或迴圈的更複雜使用者指示、整合真實的 API 執行實際操作，以及改善錯誤處理與驗證，確保指示可行、function 呼叫成功。


## 重點整理

- OpenAPI 規格已經包含 function calling 需要的資訊，可以自動轉成 function 定義，不用手寫。
- 轉換重點是解開 `$ref`，用 `operationId` 當 name，再整合描述與參數。
- 模型只負責產生呼叫用的 JSON，真正執行 function 的是你自己的程式。
- 多個 function call 可以依序串接，讓模型完成需要多步驟的操作。
- 要用在真實 API，還得加上錯誤處理和參數驗證。

## 練習

1. 在範例規格裡加一個 endpoint（例如依名稱搜尋活動），重新跑 `openapi_to_functions`，確認新的 function 定義出現。
2. 改用 endpoint 的 path 加 HTTP method 當 function 名稱，取代 `operationId`。
3. 寫一個簡單的假實作（in-memory 的活動清單），執行模型回傳的 function call，把結果回傳給模型，完成「建立活動後再改名」的串接。
