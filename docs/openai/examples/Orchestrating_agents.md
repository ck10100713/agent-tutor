---
translated: true
source: examples/Orchestrating_agents.ipynb
---
# Orchestrating Agents: Routines and Handoffs

> 原文：[examples/Orchestrating_agents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Orchestrating_agents.ipynb)

用 routine 和 handoff 來編排 agent 工作流程的 cookbook。

## 這篇在做什麼

示範怎麼用 routine（一組自然語言步驟加上工具）寫出客服 agent，再用 handoff 讓多個 agent 把對話接力給彼此。全程只用 Python 跟 Chat Completions，不依賴框架。

## 學完你會

- 寫出一個跑 tool call 的迴圈，把 Python 函式轉成 function schema 丟給模型，並把結果回填到對話。
- 做出 `Agent` class 跟 `transfer_to_XXX` 函式，讓 agent 自己決定什麼時候 handoff。
- 理解函式回傳 `Agent` 物件就能切換目前 agent 的做法，也就是 Swarm 的核心想法。

## 開跑前

- 需要 `OPENAI_API_KEY` 環境變數。


用語言模型時，很多時候只要有好的 prompt 跟對的工具，表現就很穩。不過一旦流程種類很多，事情就會變複雜。這份 cookbook 會示範一種處理方式。

我們會介紹 **routine** 和 **handoff** 的概念，然後走過實作，看怎麼用它們以簡單、強大又可控的方式編排多個 agent。

最後我們提供一個範例 repo [Swarm](https://github.com/openai/swarm)，裡面實作了這些想法，還有更多範例。



先把 import 設定好。

```python
from openai import OpenAI
from pydantic import BaseModel
from typing import Optional
import json


client = OpenAI()
```

# Routines

"routine" 沒有嚴格定義，它想表達的是「一組步驟」的概念。具體來說，我們把 routine 定義為一份自然語言的指令清單（用 system prompt 表示），加上完成這些指令需要的工具。



看個例子。下面我們為客服 agent 定義了一個 routine，指示它先判斷使用者的問題，然後建議解法或是退款。我們也定義了需要的函式 `execute_refund` 和 `look_up_item`。你可以叫它客服 routine、agent、assistant 等等，概念都一樣：一組步驟，加上執行這些步驟的工具。

```python
# Customer Service Routine

system_message = (
    "You are a customer support agent for ACME Inc."
    "Always answer in a sentence or less."
    "Follow the following routine with the user:"
    "1. First, ask probing questions and understand the user's problem deeper.\n"
    " - unless the user has already provided a reason.\n"
    "2. Propose a fix (make one up).\n"
    "3. ONLY if not satisfied, offer a refund.\n"
    "4. If accepted, search for the ID and then execute refund."
    ""
)

def look_up_item(search_query):
    """Use to find item ID.
    Search query can be a description or keywords."""

    # return hard-coded item ID - in reality would be a lookup
    return "item_132612938"


def execute_refund(item_id, reason="not provided"):

    print("Summary:", item_id, reason) # lazy summary
    return "success"
```

routine 的主要優勢是簡單又穩。注意這些指令裡有條件判斷，很像 state machine 或程式裡的分支。對於中小型的 routine，LLM 其實處理得很穩，還有「軟性」遵循的好處：LLM 可以自然地引導對話，不會卡進死路。



## 執行 routine

要執行 routine，我們實作一個簡單的迴圈：
1. 取得使用者輸入。
1. 把使用者訊息加進 `messages`。
1. 呼叫模型。
1. 把模型回應加進 `messages`。


```python
def run_full_turn(system_message, messages):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_message}] + messages,
    )
    message = response.choices[0].message
    messages.append(message)

    if message.content: print("Assistant:", message.content)

    return message


messages = []
while True:
    user = input("User: ")
    messages.append({"role": "user", "content": user})

    run_full_turn(system_message, messages)
```

可以看到，這版目前忽略了 function call，我們來補上。

模型要求函式以 function schema 的格式提供。為了方便，我們定義一個 helper 函式，把 Python 函式轉成對應的 function schema。

```python
import inspect

def function_to_schema(func) -> dict:
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(
            f"Failed to get signature for function {func.__name__}: {str(e)}"
        )

    parameters = {}
    for param in signature.parameters.values():
        try:
            param_type = type_map.get(param.annotation, "string")
        except KeyError as e:
            raise KeyError(
                f"Unknown type annotation {param.annotation} for parameter {param.name}: {str(e)}"
            )
        parameters[param.name] = {"type": param_type}

    required = [
        param.name
        for param in signature.parameters.values()
        if param.default == inspect._empty
    ]

    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            "description": (func.__doc__ or "").strip(),
            "parameters": {
                "type": "object",
                "properties": parameters,
                "required": required,
            },
        },
    }
```

例如：

```python
def sample_function(param_1, param_2, the_third_one: int, some_optional="John Doe"):
    """
    This is my docstring. Call this function when you want.
    """
    print("Hello, world")

schema =  function_to_schema(sample_function)
print(json.dumps(schema, indent=2))
```

??? note "輸出"

    ```text
    {
      "type": "function",
      "function": {
        "name": "sample_function",
        "description": "This is my docstring. Call this function when you want.",
        "parameters": {
          "type": "object",
          "properties": {
            "param_1": {
              "type": "string"
            },
            "param_2": {
              "type": "string"
            },
            "the_third_one": {
              "type": "integer"
            },
            "some_optional": {
              "type": "string"
            }
          },
          "required": [
            "param_1",
            "param_2",
            "the_third_one"
          ]
        }
      }
    }
    ```

現在可以在呼叫模型時，用這個函式把 tools 傳進去。

```python
messages = []

tools = [execute_refund, look_up_item]
tool_schemas = [function_to_schema(tool) for tool in tools]

response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Look up the black boot."}],
            tools=tool_schemas,
        )
message = response.choices[0].message

message.tool_calls[0].function
```

??? note "輸出"

    ```text
    Function(arguments='{"search_query":"black boot"}', name='look_up_item')
    ```

最後，模型呼叫 tool 時，我們要執行對應的函式，並把結果提供回給模型。

做法是用一個 `tool_map` 把 tool 名稱對應到 Python 函式，在 `execute_tool_call` 裡查表並呼叫，最後把結果加進對話。

```python
tools_map = {tool.__name__: tool for tool in tools}

def execute_tool_call(tool_call, tools_map):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print(f"Assistant: {name}({args})")

    # call corresponding function with provided arguments
    return tools_map[name](**args)

for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools_map)

            # add result back to conversation 
            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
            messages.append(result_message)
```

??? note "輸出"

    ```text
    Assistant: look_up_item({'search_query': 'black boot'})
    ```

實務上，我們還會希望模型用這個結果產生另一個回應。那個回應可能「又」包含 tool call，所以直接跑迴圈，直到沒有 tool call 為止。

全部組起來大概長這樣：

```python
tools = [execute_refund, look_up_item]


def run_full_turn(system_message, tools, messages):

    num_init_messages = len(messages)
    messages = messages.copy()

    while True:

        # turn python functions into tools and save a reverse map
        tool_schemas = [function_to_schema(tool) for tool in tools]
        tools_map = {tool.__name__: tool for tool in tools}

        # === 1. get openai completion ===
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_message}] + messages,
            tools=tool_schemas or None,
        )
        message = response.choices[0].message
        messages.append(message)

        if message.content:  # print assistant response
            print("Assistant:", message.content)

        if not message.tool_calls:  # if finished handling tool calls, break
            break

        # === 2. handle tool calls ===

        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools_map)

            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
            messages.append(result_message)

    # ==== 3. return new messages =====
    return messages[num_init_messages:]


def execute_tool_call(tool_call, tools_map):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print(f"Assistant: {name}({args})")

    # call corresponding function with provided arguments
    return tools_map[name](**args)


messages = []
while True:
    user = input("User: ")
    messages.append({"role": "user", "content": user})

    new_messages = run_full_turn(system_message, tools, messages)
    messages.extend(new_messages)
```

有了 routine 之後，假設我們想加更多步驟和工具。加到某個程度還行，但如果 routine 塞太多不同任務，模型就會開始吃力。這時可以用多個 routine：依使用者的請求，載入有對應步驟和工具的 routine 來處理。

動態切換 system instruction 跟 tools 聽起來很嚇人。不過如果把「routine」看成「agent」，**handoff** 的概念就能簡單表達這種切換：一個 agent 把對話交給另一個 agent。

# Handoffs

我們把 **handoff** 定義為：一個 agent（或 routine）把進行中的對話交給另一個 agent，就像打電話被轉接給別人。差別是這裡的 agent 完全知道你之前的對話內容！

要看 handoff 怎麼運作，先定義一個基本的 Agent class。

```python
class Agent(BaseModel):
    name: str = "Agent"
    model: str = "gpt-4o-mini"
    instructions: str = "You are a helpful Agent"
    tools: list = []
```

接著讓程式碼支援它，把 `run_full_turn` 改成接收 `Agent`，而不是分開的 `system_message` 和 `tools`：

```python
def run_full_turn(agent, messages):

    num_init_messages = len(messages)
    messages = messages.copy()

    while True:

        # turn python functions into tools and save a reverse map
        tool_schemas = [function_to_schema(tool) for tool in agent.tools]
        tools_map = {tool.__name__: tool for tool in agent.tools}

        # === 1. get openai completion ===
        response = client.chat.completions.create(
            model=agent.model,
            messages=[{"role": "system", "content": agent.instructions}] + messages,
            tools=tool_schemas or None,
        )
        message = response.choices[0].message
        messages.append(message)

        if message.content:  # print assistant response
            print("Assistant:", message.content)

        if not message.tool_calls:  # if finished handling tool calls, break
            break

        # === 2. handle tool calls ===

        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools_map)

            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
            messages.append(result_message)

    # ==== 3. return new messages =====
    return messages[num_init_messages:]


def execute_tool_call(tool_call, tools_map):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print(f"Assistant: {name}({args})")

    # call corresponding function with provided arguments
    return tools_map[name](**args)
```

現在可以輕鬆跑多個 agent：

```python
def execute_refund(item_name):
    return "success"

refund_agent = Agent(
    name="Refund Agent",
    instructions="You are a refund agent. Help the user with refunds.",
    tools=[execute_refund],
)

def place_order(item_name):
    return "success"

sales_assistant = Agent(
    name="Sales Assistant",
    instructions="You are a sales assistant. Sell the user a product.",
    tools=[place_order],
)


messages = []
user_query = "Place an order for a black boot."
print("User:", user_query)
messages.append({"role": "user", "content": user_query})

response = run_full_turn(sales_assistant, messages) # sales assistant
messages.extend(response)


user_query = "Actually, I want a refund." # implicitly refers to the last item
print("User:", user_query)
messages.append({"role": "user", "content": user_query})
response = run_full_turn(refund_agent, messages) # refund agent
```

??? note "輸出"

    ```text
    User: Place an order for a black boot.
    Assistant: place_order({'item_name': 'black boot'})
    Assistant: Your order for a black boot has been successfully placed! If you need anything else, feel free to ask!
    User: Actually, I want a refund.
    Assistant: execute_refund({'item_name': 'black boot'})
    Assistant: Your refund for the black boot has been successfully processed. If you need further assistance, just let me know!
    ```

很好！不過這裡的 handoff 是我們手動做的，我們希望由 agent 自己決定什麼時候 handoff。一個簡單但出乎意料有效的做法，是給它們 `transfer_to_XXX` 函式，`XXX` 是某個 agent。模型夠聰明，知道什麼時候該呼叫這個函式來 handoff！

### Handoff 函式

現在 agent 可以表達 handoff 的「意圖」，我們還得讓它真的發生。做法有很多種，其中有一種特別乾淨。

我們目前定義的 agent 函式，像 `execute_refund` 或 `place_order`，都是回傳一個字串給模型。如果改成回傳一個 `Agent` 物件，用來表示我們想轉給哪個 agent，會怎樣？像這樣：

```python
refund_agent = Agent(
    name="Refund Agent",
    instructions="You are a refund agent. Help the user with refunds.",
    tools=[execute_refund],
)

def transfer_to_refunds():
    return refund_agent

sales_assistant = Agent(
    name="Sales Assistant",
    instructions="You are a sales assistant. Sell the user a product.",
    tools=[place_order],
)
```

接著更新程式碼，檢查函式回應的型別，如果是 `Agent`，就更新目前使用的 agent！另外，`run_full_turn` 現在需要回傳目前最新使用的 agent，因為可能發生了 handoff。（可以用一個 `Response` class 讓這部分整齊一點。）

```python
class Response(BaseModel):
    agent: Optional[Agent]
    messages: list
```

接著是更新後的 `run_full_turn`：

```python
def run_full_turn(agent, messages):

    current_agent = agent
    num_init_messages = len(messages)
    messages = messages.copy()

    while True:

        # turn python functions into tools and save a reverse map
        tool_schemas = [function_to_schema(tool) for tool in current_agent.tools]
        tools = {tool.__name__: tool for tool in current_agent.tools}

        # === 1. get openai completion ===
        response = client.chat.completions.create(
            model=agent.model,
            messages=[{"role": "system", "content": current_agent.instructions}]
            + messages,
            tools=tool_schemas or None,
        )
        message = response.choices[0].message
        messages.append(message)

        if message.content:  # print agent response
            print(f"{current_agent.name}:", message.content)

        if not message.tool_calls:  # if finished handling tool calls, break
            break

        # === 2. handle tool calls ===

        for tool_call in message.tool_calls:
            result = execute_tool_call(tool_call, tools, current_agent.name)

            if type(result) is Agent:  # if agent transfer, update current agent
                current_agent = result
                result = (
                    f"Transfered to {current_agent.name}. Adopt persona immediately."
                )

            result_message = {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            }
            messages.append(result_message)

    # ==== 3. return last agent used and new messages =====
    return Response(agent=current_agent, messages=messages[num_init_messages:])


def execute_tool_call(tool_call, tools, agent_name):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    print(f"{agent_name}:", f"{name}({args})")

    return tools[name](**args)  # call corresponding function with provided arguments
```

來看一個有更多 Agent 的例子。

```python
def escalate_to_human(summary):
    """Only call this if explicitly asked to."""
    print("Escalating to human agent...")
    print("\n=== Escalation Report ===")
    print(f"Summary: {summary}")
    print("=========================\n")
    exit()


def transfer_to_sales_agent():
    """User for anything sales or buying related."""
    return sales_agent


def transfer_to_issues_and_repairs():
    """User for issues, repairs, or refunds."""
    return issues_and_repairs_agent


def transfer_back_to_triage():
    """Call this if the user brings up a topic outside of your purview,
    including escalating to human."""
    return triage_agent


triage_agent = Agent(
    name="Triage Agent",
    instructions=(
        "You are a customer service bot for ACME Inc. "
        "Introduce yourself. Always be very brief. "
        "Gather information to direct the customer to the right department. "
        "But make your questions subtle and natural."
    ),
    tools=[transfer_to_sales_agent, transfer_to_issues_and_repairs, escalate_to_human],
)


def execute_order(product, price: int):
    """Price should be in USD."""
    print("\n\n=== Order Summary ===")
    print(f"Product: {product}")
    print(f"Price: ${price}")
    print("=================\n")
    confirm = input("Confirm order? y/n: ").strip().lower()
    if confirm == "y":
        print("Order execution successful!")
        return "Success"
    else:
        print("Order cancelled!")
        return "User cancelled order."


sales_agent = Agent(
    name="Sales Agent",
    instructions=(
        "You are a sales agent for ACME Inc."
        "Always answer in a sentence or less."
        "Follow the following routine with the user:"
        "1. Ask them about any problems in their life related to catching roadrunners.\n"
        "2. Casually mention one of ACME's crazy made-up products can help.\n"
        " - Don't mention price.\n"
        "3. Once the user is bought in, drop a ridiculous price.\n"
        "4. Only after everything, and if the user says yes, "
        "tell them a crazy caveat and execute their order.\n"
        ""
    ),
    tools=[execute_order, transfer_back_to_triage],
)


def look_up_item(search_query):
    """Use to find item ID.
    Search query can be a description or keywords."""
    item_id = "item_132612938"
    print("Found item:", item_id)
    return item_id


def execute_refund(item_id, reason="not provided"):
    print("\n\n=== Refund Summary ===")
    print(f"Item ID: {item_id}")
    print(f"Reason: {reason}")
    print("=================\n")
    print("Refund execution successful!")
    return "success"


issues_and_repairs_agent = Agent(
    name="Issues and Repairs Agent",
    instructions=(
        "You are a customer support agent for ACME Inc."
        "Always answer in a sentence or less."
        "Follow the following routine with the user:"
        "1. First, ask probing questions and understand the user's problem deeper.\n"
        " - unless the user has already provided a reason.\n"
        "2. Propose a fix (make one up).\n"
        "3. ONLY if not satesfied, offer a refund.\n"
        "4. If accepted, search for the ID and then execute refund."
        ""
    ),
    tools=[execute_refund, look_up_item, transfer_back_to_triage],
)
```

最後，可以把它放進迴圈跑（這段在 Python notebook 裡跑不起來，建議另外存成 Python 檔來試）：

```python
agent = triage_agent
messages = []

while True:
    user = input("User: ")
    messages.append({"role": "user", "content": user})

    response = run_full_turn(agent, messages)
    agent = response.agent
    messages.extend(response.messages)
```

# Swarm

我們把這些想法打包成一個範例函式庫 [Swarm](https://github.com/openai/swarm)，作為概念驗證。它只是範例，不該直接用在 production。不過你可以拿這些想法和程式碼來建自己的版本！

## 重點整理

- routine 就是「自然語言步驟加工具」，用 system prompt 寫條件分支，模型對中小型流程處理得很穩。
- routine 塞太多任務會變差，這時拆成多個 agent，各自只管一小塊。
- handoff 的本質是換掉 system instruction 和 tools，對話歷史保留不動。
- 讓函式回傳 `Agent` 物件，就能用一般 tool call 的機制完成 handoff，不需要額外的流程控制。

## 練習

1. 在客服 routine 加一個新工具（例如查訂單狀態），並在 `tool_map` 註冊，跑跑看模型會不會用。
2. 新增一個 agent（例如處理投訴），並替它加上 `transfer_to_XXX` 函式，讓現有 agent 可以轉給它。
3. 在 `run_full_turn` 的 handoff 判斷處加一行 print，記錄每次切換前後的 agent 名稱，觀察多輪對話裡 handoff 的時機。
