---
translated: true
source: multimodal/getting_started_with_vision.ipynb
---

# 入門：怎麼把圖片傳給 Claude

> 原文：[multimodal/getting_started_with_vision.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/multimodal/getting_started_with_vision.ipynb)

教學：把圖片傳給 Claude API，做以視覺為基礎的文字分析。

## 這篇在做什麼

示範怎麼把圖片放進 Claude API 的 request，包含 base64 編碼的圖片，以及直接給圖片 URL 的做法。

## 學完你會

- 用 base64 編碼把圖片放進 message
- 只用 URL 就把圖片傳給 Claude
- 請 Claude 描述或分析傳入的圖片

## 開跑前

需要 Anthropic API key，以及 notebook 用到的圖片檔。

Claude 模型的 API 支援圖片輸入。你可以這樣把圖片傳給 Claude：

```python
%pip install anthropic httpx IPython
```

```python
from IPython.display import Image

Image(filename="../images/sunset.jpeg")
```

```python
import base64

from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-opus-5-5"

with open("../images/sunset.jpeg", "rb") as image_file:
    binary_data = image_file.read()
    base_64_encoded_data = base64.b64encode(binary_data)
    base64_string = base_64_encoded_data.decode("utf-8")


message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": base64_string},
            },
            {"type": "text", "text": "Write a sonnet based on this image."},
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print("".join(block.text for block in response.content if block.type == "text"))
```

??? note "輸出"

    ```text
    **Lighthouse at Dusk**

    The sun has slipped below the ocean's rim
    And left a band of ember on the sea;
    Above, the blue grows deep, the light grows dim,
    Where one thin moon hangs pale and silently.
    The water, hushed to silk, forgets its spray,
    And lies like mist against the pitted stone,
    Whose ancient face, worn hollow day by day,
    Has borne the tide's long argument alone.
    Upon the point, a striped and slender tower
    Ignites its lamp against the coming night,
    And holds through every slow and darkened hour
    A promise kept in one small spark of light.
      So when my own horizon dims to blue,
      May some small light stand watch and guide me through.
    ```

## 用 URL 傳圖片

如果你手上只有圖片的 URL，還是可以只用幾行短短的程式碼把它傳給 Claude。

```python
IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/Machu_Picchu%2C_Peru_%282018%29.jpg/1920px-Machu_Picchu%2C_Peru_%282018%29.jpg"
Image(url=IMAGE_URL)
```

??? note "輸出"

    ```text
    <IPython.core.display.Image object>
    ```

```python
import httpx

image_response = httpx.get(IMAGE_URL, follow_redirects=True)
image_response.raise_for_status()  # fail loudly instead of base64-encoding an error page
IMAGE_DATA = base64.b64encode(image_response.content).decode("utf-8")

message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": IMAGE_DATA},
            },
            {"type": "text", "text": "Describe this image in two sentences."},
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print("".join(block.text for block in response.content if block.type == "text"))
```

??? note "輸出"

    ```text
    This image shows the ancient Inca citadel of Machu Picchu in Peru, with its weathered stone buildings, terraced fields, and bright green central plaza perched on a mountain ridge. Behind the ruins rises the steep, vegetation-covered peak of Huayna Picchu, framed by lush Andean mountains under a vivid blue sky with scattered white clouds.
    ```

## 重點整理

- 圖片是 message content 裡的一種 block，和文字 block 並列。
- 傳圖片有兩種方式：base64 編碼，或直接給 URL。
- 圖片和文字問題放在同一則 user message。

## 練習

1. 換成自己的圖片，請 Claude 描述。
2. 在同一則 message 放兩張圖片，請它比較。
3. 改用 URL 方式傳同一張圖，確認結果和 base64 一致。
