---
translated: true
source: multimodal/how_to_transcribe_text.ipynb
---

# 用 Claude 轉錄文件

> 原文：[multimodal/how_to_transcribe_text.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/multimodal/how_to_transcribe_text.ipynb)

用 Claude 的 vision 把圖片和 PDF 裡的非結構化文字抽出來並結構化。

## 這篇在做什麼

示範用 Claude 讀圖片和 PDF 裡的文字，包含印刷文字、手寫文字、表單，並進一步做文件問答和轉成 JSON。

## 學完你會

- 只轉錄圖片裡你指定的那一部分文字
- 轉錄手寫內容和印刷加手寫混合的表單
- 把圖片裡的非結構化資訊轉成結構化 JSON

## 開跑前

需要 Anthropic API key，以及 notebook 用到的圖片檔。

Claude 很擅長讀取圖片和 PDF 裡的非結構化文字和資訊，並把它們變成結構化文字。我們會看幾個例子，不過先把 notebook 需要的程式碼設定好。

```python
%pip install anthropic IPython
```

```python
import base64

from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-opus-5-5"


def get_base64_encoded_image(image_path):
    with open(image_path, "rb") as image_file:
        binary_data = image_file.read()
        base_64_encoded_data = base64.b64encode(binary_data)
        base64_string = base_64_encoded_data.decode("utf-8")
        return base64_string


def get_response_text(response):
    # The response may lead with a thinking block, so read text blocks by type, not position.
    return "".join(block.text for block in response.content if block.type == "text")
```

## 轉錄印刷文字

用 Claude 比傳統 OCR 系統好的地方，是憑著 Claude 進階的推理能力，你可以精確指定想轉錄什麼。這張圖我們只轉錄答案裡的程式碼。

```python
from IPython.display import Image

Image(filename="../images/transcribe/stack_overflow.png")
```

```python
message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": get_base64_encoded_image("../images/transcribe/stack_overflow.png"),
                },
            },
            {"type": "text", "text": "Transcribe the code in the answer. Only output the code."},
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print(get_response_text(response))
```

??? note "輸出"

    ```text
    import os
    import base64

    image = 'test.jpg'

    encoded_string = ""
    with open(image, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    file = encoded_string
    ```

## 轉錄手寫文字

這個不錯，但我們來試點更難的。Claude 轉錄手寫文字也很強。我們請 Claude 轉錄這張手寫的處方箋。

```python
Image(filename="../images/transcribe/school_notes.png")
```

```python
message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": get_base64_encoded_image("../images/transcribe/school_notes.png"),
                },
            },
            {
                "type": "text",
                "text": "Transcribe this text. Only output the text and nothing else.",
            },
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print(get_response_text(response))
```

??? note "輸出"

    ```text
    Levels of Cellular Organization
    1) Cells group together to make tissue.
    2) Tissues group together to make an organ.
    3) Organs group together to make an organ system
    4) Organ systems group together to make an organism

    Organism -> a living thing that can
    carry out life processes by itself.

    - Multicellular organisms have specialized
    cells to perform specific functions.
    > This makes them more efficient
    and typically have a longer life span.

    Tissue = a group of similar cells
    that perform a common function.
    1) Animals are made of four
    basic types of tissue
    > nervous, epithelial, connective,
    and muscle
    2) Plants have three types
    of tissue
    > transport, protective, and
    ground
    ```

## 轉錄表單
來試試印刷加手寫混合的情況？這在保險單和報告表單等各種文件裡很常見。

```python
Image(filename="../images/transcribe/vehicle_form.jpg")
```

```python
message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": get_base64_encoded_image("../images/transcribe/vehicle_form.jpg"),
                },
            },
            {"type": "text", "text": "Transcribe this form exactly."},
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print(get_response_text(response))
```

??? note "輸出"

    ```text
    VEHICLE INCIDENT REPORT FORM

    Use this form to report accidents, injuries, medical situations, criminal activities, traffic incidents, or student behavior incidents. If possible, a report should be completed within 24 hours of the event.

    Date of Report: 02/29, 2024

    PERSON INVOLVED

    Full Name: John Doe Address: 123 Main St

    Identification: ■ Driver's License No. 474921 □ Passport No. ___________
    □ Other: ____________________

    Phone: (678) 999-8212 E-Mail: john@gmail.com

    THE INCIDENT

    Date of Incident: 02/29/2024 ■ Time: 9:01 ■ AM □ PM

    Location: Corner of 2nd and 3rd

    Describe the Incident: Red car t-boned blue car
    _______________________________________________________
    _______________________________________________________

    INJURIES

    Was anyone injured? □ Yes ■ No

    If yes, describe the injuries: ________________________________________
    _______________________________________________________________
    _______________________________________________________________

    WITNESSES

    Were there witnesses to the incident? □ Yes ■ No

    If yes, enter the witnesses' names and contact info: __________________________
    _______________________________________________________________
    _______________________________________________________________
    ... (省略 2 行)
    ```

## 複雜的文件問答
有了 Claude，我們可以不只轉錄，還能針對非結構化文件裡的資訊提出具體問題。

```python
Image(filename="../images/transcribe/page.jpeg")
```

```python
message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": get_base64_encoded_image("../images/transcribe/page.jpeg"),
                },
            },
            {"type": "text", "text": "Which is the most critical issue for live rep support?"},
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print(get_response_text(response))
```

??? note "輸出"

    ```text
    According to the hierarchy of importance pyramid for Live Rep Support shown in the image, the most critical issue is Product Quality/Liability Issues. This is positioned at the very bottom of the pyramid, indicating it is the most critical or important issue for live rep support to handle.
    ```

## 非結構化資訊 -> JSON

來看看怎麼用 Claude 把圖片裡的非結構化資訊轉成結構化的 JSON 輸出。

```python
Image(filename="../images/transcribe/org_chart.jpeg")
```

```python
message_list = [
    {
        "role": "user",
        "content": [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": get_base64_encoded_image("../images/transcribe/org_chart.jpeg"),
                },
            },
            {
                "type": "text",
                "text": "Turn this org chart into JSON indicating who reports to who. Only output the JSON and nothing else.",
            },
        ],
    }
]

response = client.messages.create(model=MODEL_NAME, max_tokens=2048, messages=message_list)
print(get_response_text(response))
```

??? note "輸出"

    ```text
    {
      "President": {
        "name": "John Smith",
        "directReports": [
          {
            "name": "Susan Jones",
            "title": "VP Marketing",
            "directReports": [
              {
                "name": "Alice Johnson",
                "title": "Manager"
              },
              {
                "name": "Tim Moore",
                "title": "Manager"
              }
            ]
          },
          {
            "name": "Rachel Parker",
            "title": "VP Sales",
            "directReports": [
              {
                "name": "Michael Gross",
                "title": "Manager"
              },
              {
                "name": "Kim Dole",
                "title": "Manager"
              }
            ]
          },
          {
            "name": "Tom Allen",
            "title": "VP Production",
            "directReports": [
              {
                "name": "Kathy Roberts",
                "title": "Manager"
              },
    ... (省略 9 行)
    ```

## 重點整理

- 相比傳統 OCR，Claude 可以用自然語言指定要轉錄哪一部分。
- 手寫、印刷、表單混合的內容都能處理。
- 不只轉錄，也能直接對文件內容做問答。
- 可以要求輸出 JSON，直接接到後續程式。

## 練習

1. 換成你自己的一張含程式碼或表格的圖片，只轉錄其中一塊。
2. 修改 prompt，讓轉錄出的表單欄位用固定的 JSON key 輸出。
3. 對同一份文件問三個不同的問題，比較直接問答和先轉錄再問的差別。
