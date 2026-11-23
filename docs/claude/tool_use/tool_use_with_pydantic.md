---
translated: true
source: tool_use/tool_use_with_pydantic.ipynb
---

# 用 Pydantic 和 Anthropic tool use 做存筆記 tool

> 原文：[tool_use/tool_use_with_pydantic.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/tool_use_with_pydantic.ipynb)

用 Pydantic model 建立有驗證的 tool，讓 Claude 的 tool use 互動有型別安全。

## 這篇在做什麼

建一個存筆記的 tool，筆記帶有作者和 metadata，並用 Pydantic 驗證模型呼叫 tool 時傳來的資料。整個流程從定義 model、處理 tool call 到驗證回應都走一遍。

## 學完你會

- 用 Pydantic 定義 tool 輸入和回應的 schema
- 處理 Claude 的 tool call，並用 Pydantic 驗證內容
- 串起一個完整的 chatbot 互動流程

## 開跑前

需要 Anthropic API key。

這個範例會做一個存筆記的 tool，筆記包含作者和 metadata，並用 Pydantic 驗證模型呼叫 tool 時的回應。我們會定義需要的 Pydantic model、處理 tool call，並確保模型的回應符合預期的 schema。

## Step 1：設定環境
先安裝需要的套件，並設定 Claude API client。

```python
%pip install anthropic pydantic 'pydantic[email]'
```

```python
from anthropic import Anthropic
from pydantic import BaseModel, EmailStr, Field

client = Anthropic()
MODEL_NAME = "claude-opus-5-5"
```

## Step 2：定義 Pydantic model

我們定義 Pydantic model 來表示筆記、作者和模型回應的預期 schema。這樣在存筆記時，就能驗證並檢查模型回應的型別。

```python
class Author(BaseModel):
    name: str
    email: EmailStr


class Note(BaseModel):
    note: str
    author: Author
    tags: list[str] | None = None
    priority: int = Field(ge=1, le=5, default=3)
    is_public: bool = False


class SaveNoteResponse(BaseModel):
    success: bool
    message: str
```

## Step 3：定義 client 端 tool

接著定義 chatbot 用來存筆記的 client 端 tool。

```python
tools = [
    {
        "name": "save_note",
        "description": "A tool that saves a note with the author and metadata.",
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {"type": "string", "description": "The content of the note to be saved."},
                "author": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "The name of the author."},
                        "email": {
                            "type": "string",
                            "format": "email",
                            "description": "The email address of the author.",
                        },
                    },
                    "required": ["name", "email"],
                },
                "priority": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 5,
                    "default": 3,
                    "description": "The priority level of the note (1-5).",
                },
                "is_public": {
                    "type": "boolean",
                    "default": False,
                    "description": "Indicates whether the note is publicly accessible.",
                },
            },
            "required": ["note", "author"],
        },
    }
]
```

## Step 4：實作存筆記 tool
我們寫一個假的存筆記函式，只會印出筆記已成功儲存。如果你真的想把筆記存到某處，可以自己實作這個函式。

```python
def save_note(note: str, author: dict, priority: int = 3, is_public: bool = False) -> None:
    print("Note saved successfully!")
```

## Step 5：處理 tool call 並產生回應
我們寫幾個函式來處理 Claude 發出的 tool call，並產生表示存筆記成功的回應。

```python
def process_tool_call(tool_name, tool_input):
    if tool_name == "save_note":
        note = Note(
            note=tool_input["note"],
            author=Author(name=tool_input["author"]["name"], email=tool_input["author"]["email"]),
            priority=tool_input.get("priority", 3),
            is_public=tool_input.get("is_public", False),
        )
        save_note(note.note, note.author.model_dump(), note.priority, note.is_public)
        return SaveNoteResponse(success=True, message="Note saved successfully!")


def generate_response(save_note_response):
    return f"Response: {save_note_response.message}"
```

## Step 6：和 chatbot 互動

現在寫一個和 chatbot 互動的函式。它會送出 user message、處理 Claude 的 tool call、產生回應、用 Pydantic 驗證模型的回應，最後把結果回給使用者。

```python
def chatbot_interaction(user_message):
    print(f"\n{'=' * 50}\nUser Message: {user_message}\n{'=' * 50}")

    messages = [{"role": "user", "content": user_message}]

    message = client.messages.create(
        model=MODEL_NAME, max_tokens=4096, tools=tools, messages=messages
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

        save_note_response = process_tool_call(tool_name, tool_input)

        print(f"Tool Result: {save_note_response}")

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
                            "content": str(save_note_response),
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

## Step 7：測試 chatbot
用一個範例 query 來測試存筆記。

```python
chatbot_interaction("""
Can you save a private note with the following details?
Note: Remember to buy milk and eggs.
Author: John Doe (johndoe@gmail.com)
Priority: 4
""")
```

??? note "輸出"

    ```text

    ==================================================
    User Message: 
    Can you save a private note with the following details?
    Note: Remember to buy milk and eggs.
    Author: John Doe (johndoe@gmail.com)
    Priority: 4

    ==================================================

    Initial Response:
    Stop Reason: tool_use
    Content: [ContentBlock(text='<thinking>\nThe relevant tool to use here is save_note, as the request is to save a note with specific details.\n\nLet\'s go through the parameters one-by-one:\n\nnote: The user provided the note content: "Remember to buy milk and eggs."\nauthor: The user provided the author details: \n{\n  "name": "John Doe",\n  "email": "johndoe@gmail.com"\n}\nis_public: While the user didn\'t explicitly specify, they asked for a "private note", so we can infer is_public should be false.\npriority: The user specified a priority of 4.\n\nAll the required parameters have been provided or can be reasonably inferred from the request. We have enough information to make the save_note call.\n</thinking>', type='text'), ContentBlockToolUse(id='toolu_015iteV2eC1C7aUodbkotfiS', input={'note': 'Remember to buy milk and eggs.', 'author': {'name': 'John Doe', 'email': 'johndoe@gmail.com'}, 'is_public': False, 'priority': 4}, name='save_note', type='tool_use')]

    Tool Used: save_note
    Tool Input: {'note': 'Remember to buy milk and eggs.', 'author': {'name': 'John Doe', 'email': 'johndoe@gmail.com'}, 'is_public': False, 'priority': 4}
    Note saved successfully!
    Tool Result: success=True message='Note saved successfully!'
    [ContentBlock(text='Your private note has been saved successfully with the following details:\n\nNote: Remember to buy milk and eggs. \nAuthor: John Doe (johndoe@gmail.com)\nPriority: 4\nVisibility: Private\n\nPlease let me know if you need anything else!', type='text')]

    Final Response: Your private note has been saved successfully with the following details:

    Note: Remember to buy milk and eggs. 
    Author: John Doe (johndoe@gmail.com)
    Priority: 4
    Visibility: Private

    Please let me know if you need anything else!
    ```

    ```text
    'Your private note has been saved successfully with the following details:\n\nNote: Remember to buy milk and eggs. \nAuthor: John Doe (johndoe@gmail.com)\nPriority: 4\nVisibility: Private\n\nPlease let me know if you need anything else!'
    ```

這個範例做了一個存筆記的 tool，筆記帶有作者和 metadata。chatbot 用 save_note tool 存筆記，並用 Pydantic 驗證模型呼叫 tool 時的回應。Note、Author 和 SaveNoteResponse 這幾個 model，確保 tool 的輸入和模型的回應符合預期的 schema。

定義清楚的 Pydantic model 並用它驗證模型的回應，讓跟 chatbot 的互動多一層可靠性和安全性。

## 重點整理

- Pydantic model 可以同時當作 tool input 的 schema 和驗證工具。
- 模型傳來的 tool input 不一定可信，進你的程式前先驗證一次。
- 巢狀的 model（Note 裡有 Author）也能自然表達複雜的 tool 輸入。
- tool 實作本身可以先用假的函式，介面確定後再接真的儲存。

## 練習

1. 給 `Note` 加一個 `tags: list[str]` 欄位，看 Claude 會不會自動填入。
2. 把 `Author` 的某個欄位改成必填，並故意讓 query 不提供，觀察驗證失敗時怎麼處理。
3. 把假的存檔函式改成真的寫入 JSON 檔。
