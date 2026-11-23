---
translated: true
source: tool_use/calculator_tool.ipynb
---

# 讓 Claude 使用 calculator tool

> 原文：[tool_use/calculator_tool.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/calculator_tool.ipynb)

給 Claude 一個計算機 tool，用來做算術運算和解數學問題。

## 這篇在做什麼

給 Claude 一個簡單的計算機 tool，讓它根據使用者輸入去做算術。我們定義 tool，並示範 Claude 怎麼和它互動來解數學題。

## 學完你會

- 定義一個接收運算式字串的 tool 和它的 input schema
- 寫出處理 tool call、算出結果並回傳給 Claude 的迴圈
- 知道為什麼 `eval` 只適合 demo，不適合正式環境

## 開跑前

需要 Anthropic API key。

這份教學要示範怎麼給 Claude 一個簡單的計算機 tool，讓它根據使用者輸入做算術運算。我們會定義這個計算機 tool，並展示 Claude 怎麼和它互動來解數學問題。

## Step 1：設定環境

先安裝需要的套件，並設定 Claude API client。

```python
%pip install anthropic
```

```python
from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-opus-5-5"
```

## Step 2：定義 calculator tool
我們定義一個能做基本算術的簡單計算機 tool。這個 tool 接收一個數學運算式當輸入，並回傳結果。

注意我們對輸出的運算式呼叫了 ```eval```。這是不好的做法，一般不應該這樣用，這裡只是為了示範。

```python
import re


def calculate(expression):
    # Remove any non-digit or non-operator characters from the expression
    expression = re.sub(r"[^0-9+\-*/().]", "", expression)

    try:
        # Evaluate the expression using the built-in eval() function
        # Note: eval is used here for demonstration purposes only.
        # In production, use a safer alternative like ast.literal_eval or a math parser.
        result = eval(expression)  # noqa: S307
        return str(result)
    except (SyntaxError, ZeroDivisionError, NameError, TypeError, OverflowError):
        return "Error: Invalid expression"


tools = [
    {
        "name": "calculator",
        "description": "A simple calculator that performs basic arithmetic operations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The mathematical expression to evaluate (e.g., '2 + 3 * 4').",
                }
            },
            "required": ["expression"],
        },
    }
]
```

這個範例定義了一個 calculate 函式，它接收數學運算式當輸入，用 regular expression 移除所有非數字、非運算子的字元，再用內建的 eval() 函式計算運算式。計算成功就把結果以字串回傳；計算時發生錯誤就回傳錯誤訊息。

接著我們定義 calculator tool，input schema 要求一個型別為 string 的 expression 屬性。

## Step 3：和 Claude 互動
現在看看 Claude 怎麼和 calculator tool 互動來解數學問題。

```python
def process_tool_call(tool_name, tool_input):
    if tool_name == "calculator":
        return calculate(tool_input["expression"])


def chat_with_claude(user_message):
    print(f"\n{'=' * 50}\nUser Message: {user_message}\n{'=' * 50}")

    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        messages=[{"role": "user", "content": user_message}],
        tools=tools,
    )

    print("\nInitial Response:")
    print(f"Stop Reason: {message.stop_reason}")
    print(f"Content: {message.content}")

    if message.stop_reason == "tool_use":
        tool_use = next(block for block in message.content if block.type == "tool_use")
        tool_name = tool_use.name
        tool_input = tool_use.input

        print(f"\nTool Used: {tool_name}")
        print(f"Tool Input: {tool_input}")

        tool_result = process_tool_call(tool_name, tool_input)

        print(f"Tool Result: {tool_result}")

        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": message.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use.id,
                            "content": tool_result,
                        }
                    ],
                },
            ],
            tools=tools,
        )
    else:
        response = message

    final_response = next(
        (block.text for block in response.content if hasattr(block, "text")),
        None,
    )
    print(response.content)
    print(f"\nFinal Response: {final_response}")

    return final_response
```

## Step 4：試試看！

既然 Claude 有計算機可用，我們給它幾個範例數學題。

```python
chat_with_claude("What is the result of 1,984,135 * 9,343,116?")
chat_with_claude("Calculate (12851 - 593) * 301 + 76")
chat_with_claude("What is 15910385 divided by 193053?")
```

??? note "輸出"

    ```text

    ==================================================
    User Message: What is the result of 1,984,135 * 9,343,116?
    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>\nThe calculator function is the relevant tool to answer this request, since it involves evaluating a mathematical expression.\n\nThe required parameter for the calculator function is:\nexpression: The mathematical expression to evaluate.\n\nThe human has directly provided the full expression to evaluate in their request: "1,984,135 * 9,343,116". This contains all the information needed for the required expression parameter.\n\nSo I have the necessary information to invoke the calculator tool.\n</thinking>', type='text'), ContentBlockToolUse(id='toolu_01V2mzqp5qkB5QucRFjJUJLD', input={'expression': '1984135 * 9343116'}, name='calculator', type='tool_use')]

    Tool Used: calculator
    Tool Input: {'expression': '1984135 * 9343116'}
    Tool Result: 18538003464660
    [ContentBlock(text='Therefore, the result of 1,984,135 * 9,343,116 is 18,538,003,464,660.', type='text')]

    Final Response: Therefore, the result of 1,984,135 * 9,343,116 is 18,538,003,464,660.

    ==================================================
    User Message: Calculate (12851 - 593) * 301 + 76
    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>\nThe user has provided a mathematical expression to be evaluated: (12851 - 593) * 301 + 76\nThis can be handled by the calculator tool. Let\'s check if the required "expression" parameter is provided:\nexpression: "(12851 - 593) * 301 + 76" - This is directly provided by the user.\nSince the required parameter is present, we can proceed with calling the calculator tool.\n</thinking>', type='text'), ContentBlockToolUse(id='toolu_01Mrrfy9adBzzxvhfZwnyJAe', input={'expression': '(12851 - 593) * 301 + 76'}, name='calculator', type='tool_use')]

    Tool Used: calculator
    Tool Input: {'expression': '(12851 - 593) * 301 + 76'}
    Tool Result: 3689734
    [ContentBlock(text='So the final result of evaluating the expression (12851 - 593) * 301 + 76 is 3689734.', type='text')]

    Final Response: So the final result of evaluating the expression (12851 - 593) * 301 + 76 is 3689734.

    ==================================================
    User Message: What is 15910385 divided by 193053?
    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>\nThe calculator function is the appropriate tool to answer this request, since it can perform basic arithmetic operations like division.\n\nThe calculator function requires a single parameter:\n- expression: The mathematical expression to evaluate\n\nIn this case, the user has provided the full expression to evaluate (15910385 divided by 193053). Since all the required information has been provided, we can proceed with calling the calculator function.\n</thinking>', type='text'), ContentBlockToolUse(id='toolu_01BfnN4LKp7oPRgmRzWeYdBG', input={'expression': '15910385 / 193053'}, name='calculator', type='tool_use')]

    Tool Used: calculator
    ... (省略 5 行)
    ```

    ```text
    'So 15910385 divided by 193053 equals 82.41459599177428.'
    ```

## 重點整理

- tool 的 input schema 決定 Claude 傳進來的參數長什麼樣，這裡只有一個字串 `expression`。
- 語言模型心算容易錯，把運算交給 tool 能得到精確結果。
- 用正規表示式過濾字元再 `eval` 只是示範，正式環境應該用安全的運算式解析器。
- tool 執行出錯時回傳錯誤訊息給模型，讓它能自己處理。

## 練習

1. 給 Claude 一個含括號的複雜運算式，看它是否正確呼叫 tool。
2. 把 `eval` 換成 `ast` 為基礎的安全運算式計算（只允許加減乘除）。
3. 故意問一個會除以零的題目，觀察錯誤訊息回傳後 Claude 的反應。
