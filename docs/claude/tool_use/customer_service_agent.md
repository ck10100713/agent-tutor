---
translated: true
source: tool_use/customer_service_agent.ipynb
---

# 用 client 端 tool 打造客服 agent

> 原文：[tool_use/customer_service_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/customer_service_agent.ipynb)

用 Claude 搭配客戶查詢和訂單管理的 tool，做一個客服 chatbot。

## 這篇在做什麼

用 Claude 加 client 端 tool 做一個客服 chatbot，能查客戶資料、查訂單明細，也能代客取消訂單。tool 的回應用假資料模擬，重點在看 tool 怎麼定義和串接。

## 學完你會

- 定義 `get_customer_info`、`get_order_details`、`cancel_order` 三個 tool 和它們的 schema
- 寫出處理 tool call 並回傳 `tool_result` 的函式
- 寫出一個會自動處理多輪 tool call 的 chatbot 互動函式

## 開跑前

需要 Anthropic API key。

這份教學要示範怎麼用 Claude 加 client 端 tool 做一個客服 chatbot。chatbot 能查客戶資訊、取得訂單明細，並代替客戶取消訂單。我們會定義需要的 tool，並模擬假的回應來展示 chatbot 的能力。

## Step 1：設定環境

先安裝需要的套件，並設定 Claude API client。

```python
%pip install anthropic
```

```python
import anthropic

client = anthropic.Client()
MODEL_NAME = "claude-opus-5-5"
```

## Step 2：定義 client 端 tool

接著定義 chatbot 協助客戶用的 client 端 tool。我們會建立三個 tool：get_customer_info、get_order_details 和 cancel_order。

```python
tools = [
    {
        "name": "get_customer_info",
        "description": "Retrieves customer information based on their customer ID. Returns the customer's name, email, and phone number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {
                    "type": "string",
                    "description": "The unique identifier for the customer.",
                }
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_order_details",
        "description": "Retrieves the details of a specific order based on the order ID. Returns the order ID, product name, quantity, price, and order status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The unique identifier for the order.",
                }
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "cancel_order",
        "description": "Cancels an order based on the provided order ID. Returns a confirmation message if the cancellation is successful.",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The unique identifier for the order to be cancelled.",
                }
            },
            "required": ["order_id"],
        },
    },
]
```

## Step 3：模擬假的 tool 回應

因為我們沒有真的客戶資料或訂單資訊，所以對 tool 模擬假的回應。實際情況下，這些函式會去操作你真正的客戶資料庫和訂單管理系統。

```python
def get_customer_info(customer_id):
    # Simulated customer data
    customers = {
        "C1": {"name": "John Doe", "email": "john@example.com", "phone": "123-456-7890"},
        "C2": {"name": "Jane Smith", "email": "jane@example.com", "phone": "987-654-3210"},
    }
    return customers.get(customer_id, "Customer not found")


def get_order_details(order_id):
    # Simulated order data
    orders = {
        "O1": {
            "id": "O1",
            "product": "Widget A",
            "quantity": 2,
            "price": 19.99,
            "status": "Shipped",
        },
        "O2": {
            "id": "O2",
            "product": "Gadget B",
            "quantity": 1,
            "price": 49.99,
            "status": "Processing",
        },
    }
    return orders.get(order_id, "Order not found")


def cancel_order(order_id):
    # Simulated order cancellation
    if order_id in ["O1", "O2"]:
        return True
    else:
        return False
```

## Step 4：處理 tool call 並回傳結果

我們寫一個函式來處理 Claude 發出的 tool call，並回傳適當的結果。

```python
def process_tool_call(tool_name, tool_input):
    if tool_name == "get_customer_info":
        return get_customer_info(tool_input["customer_id"])
    elif tool_name == "get_order_details":
        return get_order_details(tool_input["order_id"])
    elif tool_name == "cancel_order":
        return cancel_order(tool_input["order_id"])
```

## Step 5：和 chatbot 互動

現在寫一個和 chatbot 互動的函式。它會送出 user message、處理 Claude 的任何 tool call，最後把最終回應回給使用者。

```python
import json


def chatbot_interaction(user_message):
    print(f"\n{'=' * 50}\nUser Message: {user_message}\n{'=' * 50}")

    messages = [{"role": "user", "content": user_message}]

    response = client.messages.create(
        model=MODEL_NAME, max_tokens=4096, tools=tools, messages=messages
    )

    print("\nInitial Response:")
    print(f"Stop Reason: {response.stop_reason}")
    print(f"Content: {response.content}")

    while response.stop_reason == "tool_use":
        tool_use = next(block for block in response.content if block.type == "tool_use")
        tool_name = tool_use.name
        tool_input = tool_use.input

        print(f"\nTool Used: {tool_name}")
        print("Tool Input:")
        print(json.dumps(tool_input, indent=2))

        tool_result = process_tool_call(tool_name, tool_input)

        print("\nTool Result:")
        print(json.dumps(tool_result, indent=2))

        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": response.content},
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
        ]

        response = client.messages.create(
            model=MODEL_NAME, max_tokens=4096, tools=tools, messages=messages
        )

        print("\nResponse:")
        print(f"Stop Reason: {response.stop_reason}")
        print(f"Content: {response.content}")

    final_response = next(
        (block.text for block in response.content if hasattr(block, "text")),
        None,
    )

    print(f"\nFinal Response: {final_response}")

    return final_response
```

## Step 6：測試 chatbot
用幾個範例 query 測試我們的客服 chatbot。

```python
chatbot_interaction("Can you tell me the email address for customer C1?")
chatbot_interaction("What is the status of order O2?")
chatbot_interaction("Please cancel order O1 for me.")
```

??? note "輸出"

    ```text

    ==================================================
    User Message: Can you tell me the email address for customer C1?
    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>The get_customer_info function retrieves a customer\'s name, email, and phone number given their customer ID. To call this function, I need the customer_id parameter. The user provided the customer ID "C1" in their request, so I have the necessary information to make the API call.</thinking>', type='text'), ContentBlockToolUse(id='toolu_019F9JHokMkJ1dHw5BEh28sA', input={'customer_id': 'C1'}, name='get_customer_info', type='tool_use')]

    Tool Used: get_customer_info
    Tool Input:
    {
      "customer_id": "C1"
    }

    Tool Result:
    {
      "name": "John Doe",
      "email": "john@example.com",
      "phone": "123-456-7890"
    }

    Response:
    Stop Reason: end_turn
    Content: [ContentBlock(text='The email address for customer C1 (John Doe) is john@example.com.', type='text')]

    Final Response: The email address for customer C1 (John Doe) is john@example.com.

    ==================================================
    User Message: What is the status of order O2?
    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>\nBased on the provided functions, the most relevant one for this request is get_order_details, which takes an order_id parameter and returns details about that specific order, including the order status.\n\nThe user has provided an order ID in their request - "O2". So the required order_id parameter can be filled with this value.\n\nSince the required parameter is available, I can proceed with calling the get_order_details function to retrieve the order status for order O2.\n</thinking>', type='text'), ContentBlockToolUse(id='toolu_01K1u68uC94edXx8MVT35eR3', input={'order_id': 'O2'}, name='get_order_details', type='tool_use')]

    Tool Used: get_order_details
    Tool Input:
    {
      "order_id": "O2"
    ... (省略 39 行)
    ```

    ```text
    'Based on the confirmation received, your order O1 has been successfully cancelled. Please let me know if there is anything else I can assist you with.'
    ```

這樣就完成了！我們用 Claude 和 client 端 tool 做出了客服 chatbot，它能依使用者的請求查客戶資訊、取得訂單明細、取消訂單。把 tool 的描述和 schema 定義清楚，Claude 就能有效理解並使用這些 tool 來協助客戶。

你可以接上自己真正的客戶資料庫和訂單管理系統，也可以加更多 tool 處理更多種客服任務，來延伸這個範例。

## 重點整理

- client 端 tool 的 description 和 schema 寫得越清楚，Claude 越能選對 tool 和填對參數。
- 模型只負責決定要呼叫什麼，真正執行在你的程式碼裡，所以能接任何後端。
- 互動函式要處理迴圈：只要回應還要求 tool，就執行並回傳結果，直到模型給最終答案。
- 開發階段用假資料模擬 tool，可以先把對話流程測好。

## 練習

1. 在假資料裡多加一位客戶和一筆訂單，用新的 query 測試。
2. 新增一個 `update_shipping_address` tool，補上 schema 和處理函式。
3. 讓 `cancel_order` 對已出貨的訂單回傳錯誤，觀察 Claude 怎麼向使用者解釋。
