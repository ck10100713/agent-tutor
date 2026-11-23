---
translated: true
source: misc/pdf_upload_summarization.ipynb
---

# 透過 API 「上傳」PDF 給 Claude

> 原文：[misc/pdf_upload_summarization.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/pdf_upload_summarization.ipynb)

用 Claude API 搭配編碼處理並摘要 PDF 文件。

## 這篇在做什麼

在 notebook 裡模擬 Claude.ai 的上傳 PDF 功能：把 PDF 轉成 base64，用 PDF document block 傳給 Claude，請它摘要一份很長的論文。

## 學完你會

- 把 PDF 檔轉成 base64 編碼的 bytes
- 用 PDF document block 把文件和問題一起送給 Claude
- 對長 PDF 做摘要和問答

## 開跑前

需要 Anthropic API key，以及 `../multimodal/documents` 目錄裡的 PDF 檔。

[Claude.ai](https://www.claude.ai) 有個很棒的功能，就是可以上傳 PDF。我們在 notebook 裡模擬這個功能，然後用它摘要一份長 PDF 來測試。

先安裝 Anthropic client，並建立一個整份 notebook 都會用到的 instance。

```python
%pip install anthropic
```

```python
from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-sonnet-5-5"
```

我們在 `../multimodal/documents` 目錄裡已經有一份 PDF。我們把 PDF 檔轉成 base64 編碼的 bytes，這是 Claude API 的 [PDF document block](https://docs.claude.com/en/docs/build-with-claude/pdf-support) 需要的格式。注意這種抽取方式對文字和視覺元素（像圖表）都有效。

```python
import base64


# Start by reading in the PDF and encoding it as base64
file_name = "../multimodal/documents/constitutional-ai-paper.pdf"
with open(file_name, "rb") as pdf_file:
  binary_data = pdf_file.read()
  base64_encoded_data = base64.standard_b64encode(binary_data)
  base64_string = base64_encoded_data.decode("utf-8")
```

論文下載並放進記憶體之後，我們可以請 Claude 對它做各種有趣的事。我們把文件和一個簡單的問題一起傳給模型。

```python
prompt = """
Please do the following:
1. Summarize the abstract at a kindergarten reading level. (In <kindergarten_abstract> tags.)
2. Write the Methods section as a recipe from the Moosewood Cookbook. (In <moosewood_methods> tags.)
3. Compose a short poem epistolizing the results in the style of Homer. (In <homer_results> tags.)
"""
messages = [
    {
        "role": 'user',
        "content": [
            {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64_string}},
            {"type": "text", "text": prompt}
        ]
    }
]
```

```python
def get_completion(client, messages):
    response = client.messages.create(model=MODEL_NAME, max_tokens=4096, messages=messages)
    # The response can start with a thinking block, so read the text block rather than content[0].
    return next(block.text for block in response.content if block.type == "text")
```

```python
completion = get_completion(client, messages)
print(completion)
```

??? note "輸出"

    ```text
    <kindergarten_abstract>
    The scientists wanted to make computer helpers that are nice and don't do bad things. They taught the computer how to check its own work and fix its mistakes without humans having to tell it what's wrong every time. It's like teaching the computer to be its own teacher! They gave the computer some basic rules to follow, like "be kind" and "don't hurt others." Now the computer can answer questions in a helpful way while still being nice and explaining why some things aren't okay to do.
    </kindergarten_abstract>

    <moosewood_methods>
    Constitutional AI Training Stew
    A nourishing recipe for teaching computers to be helpful and harmless

    Ingredients:
    - 1 helpful AI model, pre-trained
    - A bundle of constitutional principles
    - Several cups of training data
    - A dash of human feedback (for helpfulness only)
    - Chain-of-thought reasoning, to taste

    Method:
    1. Begin by gently simmering your pre-trained AI model in a bath of helpful training data until it responds reliably to instructions.

    2. In a separate bowl, combine your constitutional principles with some example conversations. Mix well until principles are evenly distributed.

    3. Take your helpful AI and ask it to generate responses to challenging prompts. Have it critique its own responses using the constitutional principles, then revise accordingly. Repeat this process 3-4 times until responses are properly seasoned with harmlessness.

    4. For the final garnish, add chain-of-thought reasoning and allow the model to explain its decisions step by step.

    5. Let rest while training a preference model using AI feedback rather than human labels.

    Serves: All users seeking helpful and harmless AI assistance
    Cook time: Multiple training epochs
    Note: Best results come from consistent application of principles throughout the process
    </moosewood_methods>

    <homer_results>
    O Muse! Sing of the AI that learned to be
    Both helpful and harmless, guided by philosophy
    Without human labels marking right from wrong
    The model learned wisdom, grew capable and strong

    Through cycles of critique and thoughtful revision
    It mastered the art of ethical decision
    Better than models trained by human hand
    ... (省略 12 行)
    ```

## 重點整理

- API 沒有「上傳檔案」按鈕，做法是把 PDF 轉成 base64 放進 document block。
- PDF 的文字和圖表等視覺內容都能被讀取。
- 文件和問題放在同一個 request，之後可以接連問不同問題。

## 練習

1. 換成你自己的 PDF，請 Claude 摘要成三個重點。
2. 對同一份 PDF 問一個要看圖表才能回答的問題。
3. 把摘要需求改成輸出特定格式（例如條列加一句結論），比較結果。
