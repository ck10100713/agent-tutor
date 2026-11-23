---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/How_to_call_functions_with_chat_models.ipynb
---

# 如何用 chat models 呼叫 function

> 原文：[examples/How_to_call_functions_with_chat_models.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb)



## 這篇在做什麼
示範怎麼用 Chat Completions API 搭配外部 function 擴充 GPT 模型的能力。先看模型怎麼產生 function 參數，再真的拿這些參數去執行，做出一個能回答資料庫問題的 agent。

## 學完你會
- 定義 `tools` 的 function 規格，讓模型產生符合規格的參數，並用 `tool_choice` 強制或禁止呼叫。
- 處理 parallel function calling（一次回合呼叫多個 function）。
- 實作完整的 function call 迴圈，讓模型產生 SQL 並對 SQLite 資料庫執行、回答問題。

## 開跑前
- 需要 OpenAI API key。
- 後半段用 Chinook 範例 SQLite 資料庫，需要先下載。
- SQL 生成在 production 有風險，範例僅供學習。


這份 notebook 說明怎麼把 Chat Completions API 和外部 function 結合，來擴充 GPT 模型的能力。

`tools` 是 Chat Completion API 的選用參數，可以用來提供 function 規格。目的是讓模型產生符合所提供規格的 function 參數。注意 API 實際上不會執行任何 function call，要由開發者用模型的輸出自己去執行。

在 `tools` 參數裡，如果有提供 `functions` 參數，模型預設會自己判斷什麼時候適合用其中一個 function。把 `tool_choice` 參數設成 `{"type": "function", "function": {"name": "my_function"}}`，可以強制 API 使用特定 function。把 `tool_choice` 設成 `"none"`，則可以強制 API 不使用任何 function。如果有用到 function，回應會包含 `"finish_reason": "tool_calls"`，以及一個 `tool_calls` 物件，裡面有 function 名稱和產生的 function 參數。

### 概觀

這份 notebook 有下面兩個部分：

- **如何產生 function 參數：** 指定一組 function，用 API 產生 function 參數。
- **如何用模型產生的參數呼叫 function：** 真的用模型產生的參數去執行 function，把流程串成完整迴圈。

## 如何產生 function 參數

```python
!pip install scipy --quiet
!pip install tenacity --quiet
!pip install tiktoken --quiet
!pip install termcolor --quiet
!pip install openai --quiet
```

```python
import json
from openai import OpenAI
from tenacity import retry, wait_random_exponential, stop_after_attempt
from termcolor import colored  

GPT_MODEL = "gpt-5"
client = OpenAI()
```

### 工具函式

首先定義幾個工具函式，用來呼叫 Chat Completions API，並維護和追蹤對話狀態。

```python
@retry(wait=wait_random_exponential(multiplier=1, max=40), stop=stop_after_attempt(3))
def chat_completion_request(messages, tools=None, tool_choice=None, model=GPT_MODEL):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        return response
    except Exception as e:
        print("Unable to generate ChatCompletion response")
        print(f"Exception: {e}")
        return e
```

```python
def pretty_print_conversation(messages):
    role_to_color = {
        "system": "red",
        "user": "green",
        "assistant": "blue",
        "function": "magenta",
    }
    
    for message in messages:
        if message["role"] == "system":
            print(colored(f"system: {message['content']}\n", role_to_color[message["role"]]))
        elif message["role"] == "user":
            print(colored(f"user: {message['content']}\n", role_to_color[message["role"]]))
        elif message["role"] == "assistant" and message.get("tool_calls"):
            print(colored(f"assistant: {message['tool_calls']}\n", role_to_color[message["role"]]))
        elif message["role"] == "assistant" and not message.get("tool_calls"):
            print(colored(f"assistant: {message['content']}\n", role_to_color[message["role"]]))
        elif message["role"] == "function":
            print(colored(f"function ({message['name']}): {message['content']}\n", role_to_color[message["role"]]))
```

### 基本概念

我們來建立一些 function 規格，用來對接一個假想的天氣 API。把這些 function 規格傳給 Chat Completions API，產生符合規格的 function 參數。

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Get the current weather",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "The temperature unit to use. Infer this unit from the forecast location.",
                    },
                },
                "required": ["location", "format"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_n_day_weather_forecast",
            "description": "Get an N-day weather forecast",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "format": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": "The temperature unit to use. Infer this unit from the forecast location.",
                    },
                    "num_days": {
                        "type": "integer",
                        "description": "The number of days to forecast",
                    }
                },
                "required": ["location", "format", "num_days"]
            },
        }
    },
]
```

如果我們問模型目前的天氣，它會回覆一些釐清問題。

```python
messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "What's the weather like today"})
chat_response = chat_completion_request(
    messages, tools=tools
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: What's the weather like today

    assistant: Sure—what city and state (or country) should I check? Also, do you prefer Celsius or Fahrenheit?
    ```

等我們提供缺少的資訊後，它就會替我們產生適當的 function 參數。

```python
messages.append({"role": "user", "content": "I'm in Glasgow, Scotland."})
chat_response = chat_completion_request(
    messages, tools=tools
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: What's the weather like today

    assistant: Sure—what city and state (or country) should I check? Also, do you prefer Celsius or Fahrenheit?

    user: I'm in Glasgow, Scotland.

    assistant: [{'id': 'call_k2QgGc9GT9WjxD76GvR0Ot8q', 'function': {'arguments': '{"location": "Glasgow, Scotland", "format": "celsius"}', 'name': 'get_current_weather'}, 'type': 'function'}, {'id': 'call_RtnXV5t49lqbWwhvGoEPZ7KY', 'function': {'arguments': '{"location": "Glasgow, Scotland", "format": "celsius", "num_days": 1}', 'name': 'get_n_day_weather_forecast'}, 'type': 'function'}]
    ```

換個方式問，就能讓它去用我們告訴它的另一個 function。

```python
messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "what is the weather going to be like in Glasgow, Scotland over the next x days"})
chat_response = chat_completion_request(
    messages, tools=tools
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: what is the weather going to be like in Glasgow, Scotland over the next x days

    assistant: How many days would you like the forecast for in Glasgow, Scotland? For example: 3, 5, 7, 10, or 14.
    ```

模型又一次向我們要求釐清，因為它的資訊還不夠。這次它已經知道預報的地點，但需要知道預報要幾天。

```python
messages.append({"role": "user", "content": "5 days"})
chat_response = chat_completion_request(
    messages, tools=tools
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: what is the weather going to be like in Glasgow, Scotland over the next x days

    assistant: How many days would you like the forecast for in Glasgow, Scotland? For example: 3, 5, 7, 10, or 14.

    user: 5 days

    assistant: [{'id': 'call_lNzOVLrNSaSVjL3O3bN110af', 'function': {'arguments': '{"location":"Glasgow, Scotland","format":"celsius","num_days":5}', 'name': 'get_n_day_weather_forecast'}, 'type': 'function'}]
    ```

#### 強制使用特定 function 或不使用 function

我們可以用 function_call 參數強制模型使用特定的 function，例如 get_n_day_weather_forecast。這樣做會逼模型對怎麼使用它做出假設。

```python
# in this cell we force the model to use get_n_day_weather_forecast
messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "Give me a weather report for Toronto, Canada."})
chat_response = chat_completion_request(
    messages, tools=tools, tool_choice={"type": "function", "function": {"name": "get_n_day_weather_forecast"}}
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: Give me a weather report for Toronto, Canada.

    assistant: [{'id': 'call_3hoMjl55OQ7LxfwhFyjxwv1T', 'function': {'arguments': '{"location":"Toronto, Canada","format":"celsius","num_days":5}', 'name': 'get_n_day_weather_forecast'}, 'type': 'function'}]
    ```

```python
# if we don't force the model to use get_n_day_weather_forecast it may not
messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "Give me a weather report for Toronto, Canada."})
chat_response = chat_completion_request(
    messages, tools=tools
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: Give me a weather report for Toronto, Canada.

    assistant: [{'id': 'call_wv5mdjEQJnBPuSci3xw09Tom', 'function': {'arguments': '{"location":"Toronto, ON","format":"celsius"}', 'name': 'get_current_weather'}, 'type': 'function'}]
    ```

我們也可以強制模型完全不使用 function。這樣會讓它無法產生正式的 function call。

```python
messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "Give me the current weather (use Celcius) for Toronto, Canada."})
chat_response = chat_completion_request(
    messages, tools=tools, tool_choice="none"
)
messages.append(chat_response.choices[0].message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    system: Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.

    user: Give me the current weather (use Celcius) for Toronto, Canada.

    assistant: I don’t have live access to pull the current conditions right now. To get Toronto’s current weather in Celsius, check any of these quickly:
    - Environment Canada: weather.gc.ca (search “Toronto”)
    - The Weather Network: theweathernetwork.com/ca/weather/ontario/toronto
    - Google: search “Toronto weather” (shows °C by default in Canada)
    - AccuWeather or Weather.com (set units to °C)

    If you paste the current readings here (temperature, feels-like, wind, precipitation), I can interpret them and advise on what to wear or plan for.
    ```

### Parallel Function Calling

較新的模型，例如 gpt-5、gpt-4.1 或 gpt-4o，可以在一個回合裡呼叫多個 function。

```python
messages = []
messages.append({"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."})
messages.append({"role": "user", "content": "what is the weather going to be like in San Francisco and Glasgow over the next 4 days"})
chat_response = chat_completion_request(
    messages, tools=tools, model="gpt-4o"
)

assistant_message = chat_response.choices[0].message.tool_calls
assistant_message
```

??? note "輸出"

    ```text
    [ChatCompletionMessageFunctionToolCall(id='call_KlZ3Fqt3SviC6o66dVMYSa2Q', function=Function(arguments='{"location": "San Francisco, CA", "format": "fahrenheit", "num_days": 4}', name='get_n_day_weather_forecast'), type='function'),
     ChatCompletionMessageFunctionToolCall(id='call_YAnH0VRB3oqjqivcGj3Cd8YA', function=Function(arguments='{"location": "Glasgow, UK", "format": "celsius", "num_days": 4}', name='get_n_day_weather_forecast'), type='function')]
    ```

## 如何用模型產生的參數呼叫 function

下一個範例會示範怎麼執行輸入由模型產生的 function，並用它實作一個能回答資料庫問題的 agent。為了簡單，我們用 [Chinook 範例資料庫](https://www.sqlitetutorial.net/sqlite-sample-database/)。

*注意：* 在 production 環境，SQL 生成可能風險很高，因為模型產生正確 SQL 的可靠度並不完美。

### 指定一個執行 SQL query 的 function

首先定義一些好用的工具函式，從 SQLite 資料庫取出資料。

```python
import sqlite3

conn = sqlite3.connect("data/Chinook.db")
print("Opened database successfully")
```

??? note "輸出"

    ```text
    Opened database successfully
    ```

```python
def get_table_names(conn):
    """Return a list of table names."""
    table_names = []
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table';")
    for table in tables.fetchall():
        table_names.append(table[0])
    return table_names


def get_column_names(conn, table_name):
    """Return a list of column names."""
    column_names = []
    columns = conn.execute(f"PRAGMA table_info('{table_name}');").fetchall()
    for col in columns:
        column_names.append(col[1])
    return column_names


def get_database_info(conn):
    """Return a list of dicts containing the table name and columns for each table in the database."""
    table_dicts = []
    for table_name in get_table_names(conn):
        columns_names = get_column_names(conn, table_name)
        table_dicts.append({"table_name": table_name, "column_names": columns_names})
    return table_dicts
```

現在我們可以用這些工具函式取出資料庫 schema 的表示。

```python
database_schema_dict = get_database_info(conn)
database_schema_string = "\n".join(
    [
        f"Table: {table['table_name']}\nColumns: {', '.join(table['column_names'])}"
        for table in database_schema_dict
    ]
)
```

跟之前一樣，我們為想讓 API 產生參數的 function 定義 function 規格。注意我們把資料庫 schema 放進 function 規格裡，這對模型了解資料庫很重要。

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "ask_database",
            "description": "Use this function to answer user questions about music. Input should be a fully formed SQL query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": f"""
                                SQL query extracting info to answer the user's question.
                                SQL should be written using this database schema:
                                {database_schema_string}
                                The query should be returned in plain text, not in JSON.
                                """,
                    }
                },
                "required": ["query"],
            },
        }
    }
]
```

### 執行 SQL query

現在來實作真正對資料庫執行 query 的 function。

```python
def ask_database(conn, query):
    """Function to query SQLite database with a provided SQL query."""
    try:
        results = str(conn.execute(query).fetchall())
    except Exception as e:
        results = f"query failed with error: {e}"
    return results
```

##### 用 Chat Completions API 觸發 function call 的步驟： 

**Step 1**：用可能讓模型選擇使用 tool 的內容去 prompt 模型。tool 的描述，像是 function 名稱和簽章，定義在 'Tools' 清單裡，並在 API 呼叫時傳給模型。如果模型選了 tool，回應裡就會包含 function 名稱和參數。<br>
  
**Step 2**：用程式檢查模型是否想呼叫 function。如果是，進到 step 3。 <br>  
**Step 3**：從回應取出 function 名稱和參數，用這些參數呼叫 function，並把結果附加到 messages。 <br>    
**Step 4**：用 message 清單呼叫 chat completions API 取得回應。 

```python
# Step #1: Prompt with content that may result in function call. In this case the model can identify the information requested by the user is potentially available in the database schema passed to the model in Tools description. 
messages = [{
    "role":"user", 
    "content": "What is the name of the album with the most tracks?"
}]

response = client.chat.completions.create(
    model=GPT_MODEL, 
    messages=messages, 
    tools=tools, 
    tool_choice="auto"
)

# Append the message to messages list
response_message = response.choices[0].message 
messages.append(response_message.to_dict())
pretty_print_conversation(messages)
```

??? note "輸出"

    ```text
    user: What is the name of the album with the most tracks?

    assistant: [{'id': 'call_pGRtZZGfd2o41GHlZcEdB9he', 'function': {'arguments': '{"query":"WITH track_counts AS (\\n  SELECT a.AlbumId, a.Title, COUNT(t.TrackId) AS track_count\\n  FROM Album a\\n  JOIN Track t ON t.AlbumId = a.AlbumId\\n  GROUP BY a.AlbumId, a.Title\\n)\\nSELECT Title\\nFROM track_counts\\nWHERE track_count = (SELECT MAX(track_count) FROM track_counts);"}', 'name': 'ask_database'}, 'type': 'function'}]
    ```

```python
# Step 2: determine if the response from the model includes a tool call.   
tool_calls = response_message.tool_calls
if tool_calls:
    # If true the model will return the name of the tool / function to call and the argument(s)  
    tool_call_id = tool_calls[0].id
    tool_function_name = tool_calls[0].function.name
    tool_query_string = json.loads(tool_calls[0].function.arguments)['query']

    # Step 3: Call the function and retrieve results. Append the results to the messages list.      
    if tool_function_name == 'ask_database':
        results = ask_database(conn, tool_query_string)
        
        messages.append({
            "role":"tool", 
            "tool_call_id":tool_call_id, 
            "name": tool_function_name, 
            "content":results
        })
        
        # Step 4: Invoke the chat completions API with the function response appended to the messages list
        # Note that messages with role 'tool' must be a response to a preceding message with 'tool_calls'
        model_response_with_function_call = client.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
        )  # get a new response from the model where it can see the function response
        print(f"Result found in database: {model_response_with_function_call.choices[0].message.content}")
    else: 
        print(f"Error: function {tool_function_name} does not exist")
else: 
    # Model did not identify a function to call, result can be returned to the user 
    print(response_message.content)
```

??? note "輸出"

    ```text
    Result found in database: Greatest Hits
    ```

## 下一步

看我們另一份 [notebook](How_to_call_functions_for_knowledge_retrieval.md)，示範怎麼用 Chat Completions API 和 function 做知識檢索，以對話方式和知識庫互動。

## 重點整理
- 模型不會執行 function，它只產生 function 名稱和參數，執行要由你的程式做。
- `tool_choice` 可以讓模型自己決定、強制用某個 function，或完全不用。
- 資訊不夠時模型會追問，而不是亂猜參數，除非你強制它呼叫。
- 完整的 function call 是四步：給 tools、判斷是否呼叫、執行並把結果加回 messages、再呼叫一次 API。
- 讓模型產生 SQL 時，把資料庫 schema 放進 function 描述，模型才寫得對，但 production 要小心風險。

## 練習
1. 在天氣範例的 function 規格加一個 `unit` 參數（celsius 或 fahrenheit），看模型怎麼追問或填值。
2. 把 `tool_choice` 改成 `"none"` 和指定 function 各跑一次，比較回應的 `finish_reason`。
3. 在 SQL 執行 function 加檢查，只允許 SELECT 語句，並用一個要求刪除資料的問題測試。
