---
translated: true
source: tool_use/vision_with_tools.ipynb
---

# 結合 vision 和 tool

> 原文：[tool_use/vision_with_tools.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/vision_with_tools.ipynb)

結合 Claude 的 vision 和 tool，從營養標示這類圖片抽出結構化資料。

## 這篇在做什麼

把 vision 和 tool use 結合，分析一張營養標示的圖片，並用自訂 tool 抽出結構化的營養資訊。

## 學完你會

- 定義一個用來承接抽取結果的 tool 和它的欄位
- 把圖片和 prompt 一起送給 Claude，讓它呼叫 tool
- 取得整齊的 JSON 營養資料

## 開跑前

需要 Anthropic API key，以及 notebook 用到的營養標示圖片。

這份教學要示範怎麼把 Vision 和 tool use 結合，分析一張營養標示的圖片，並用自訂 tool 抽出結構化的營養資訊。

## 設定
先安裝需要的套件，並設定 Claude API client：

```python
%pip install anthropic IPython
```

```python
import base64

from anthropic import Anthropic
from IPython.display import Image

client = Anthropic()
MODEL_NAME = "claude-opus-5-5"
```

# 定義營養標示抽取 Tool
接著定義一個叫 "print_nutrition_info" 的自訂 tool，從圖片抽出結構化的營養資訊。這個 tool 有 calories、total fat、cholesterol、total carbs 和 protein 這幾個屬性：

```python
nutrition_tool = {
    "name": "print_nutrition_info",
    "description": "Extracts nutrition information from an image of a nutrition label",
    "input_schema": {
        "type": "object",
        "properties": {
            "calories": {"type": "integer", "description": "The number of calories per serving"},
            "total_fat": {
                "type": "integer",
                "description": "The amount of total fat in grams per serving",
            },
            "cholesterol": {
                "type": "integer",
                "description": "The amount of cholesterol in milligrams per serving",
            },
            "total_carbs": {
                "type": "integer",
                "description": "The amount of total carbohydrates in grams per serving",
            },
            "protein": {
                "type": "integer",
                "description": "The amount of protein in grams per serving",
            },
        },
        "required": ["calories", "total_fat", "cholesterol", "total_carbs", "protein"],
    },
}
```

## 分析營養標示圖片
現在把它們組合起來。我們載入一張營養標示圖片，連同 prompt 一起傳給 Claude，讓 Claude 呼叫 "print_nutrition_info" tool，把結構化的營養資訊抽成格式整齊的 JSON 物件：

```python
Image(filename="../images/tool_use/nutrition_label.png")
```

```python
def get_base64_encoded_image(image_path):
    with open(image_path, "rb") as image_file:
        binary_data = image_file.read()
        base_64_encoded_data = base64.b64encode(binary_data)
        base64_string = base_64_encoded_data.decode("utf-8")
        return base64_string


message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": get_base64_encoded_image("../images/tool_use/nutrition_label.png"),
                },
            },
            {
                "type": "text",
                "text": "Please print the nutrition information from this nutrition label image.",
            },
        ],
    }
]

response = client.messages.create(
    model=MODEL_NAME, max_tokens=4096, messages=message_list, tools=[nutrition_tool]
)

if response.stop_reason == "tool_use":
    last_content_block = next(
        (b for b in response.content if b.type == "tool_use"), response.content[-1]
    )
    if last_content_block.type == "tool_use":
        tool_name = last_content_block.name
        tool_inputs = last_content_block.input
        print(f"=======Claude Wants To Call The {tool_name} Tool=======")
        print(tool_inputs)

else:
    print("No tool was called. This shouldn't happen!")
```

??? note "輸出"

    ```text
    =======Claude Wants To Call The print_nutrition_info Tool=======
    {'calories': 200, 'total_fat': 15, 'cholesterol': 30, 'total_carbs': 30, 'protein': 5}
    ```

## 重點整理

- tool 的 input schema 可以當作「抽取格式」，模型會把圖片內容填進去。
- 這是取得結構化輸出的常見做法，不必真的執行任何東西。
- vision 和 tool use 能在同一個 request 搭配使用。
- 欄位定義得越明確，抽取結果越穩定。

## 練習

1. 在 tool 裡多加 `sodium` 和 `sugar` 欄位，看 Claude 能否抽出。
2. 換成另一張營養標示圖片測試。
3. 把某個欄位設成選填，用缺少該資訊的圖片測試行為。
