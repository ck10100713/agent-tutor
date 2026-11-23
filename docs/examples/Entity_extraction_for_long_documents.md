---
translated: true
source: examples/Entity_extraction_for_long_documents.ipynb
---

# 長文件內容擷取

> 原文：[examples/Entity_extraction_for_long_documents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Entity_extraction_for_long_documents.ipynb)



## 這篇在做什麼

文件太長、塞不進 context window 時，怎麼用 GPT 擷取其中的關鍵數字、日期等內容。做法是把文件切塊，每塊各自處理，再把答案合併成一份清單。範例文件是 F1 財務規章中關於 Power Units 的 PDF。

## 學完你會

- 讀入長 PDF 並抽出文字
- 寫一個擷取用的 prompt 模板，對每個 chunk 跑一次並收集答案
- 把方法擴充到需要推理的較難問題，並知道出錯時怎麼調整

## 開跑前

- OpenAI API key
- 一份要處理的長 PDF（範例用 F1 Power Units 財務規章）

GPT-3 可以幫我們從太大、塞不進 context window 的文件裡，擷取關鍵數字、日期或其他重要內容。解法之一是把文件切塊，每塊分別處理，最後再合併成一份答案清單。

這份 notebook 會依序走過這個做法：
- 讀入一份長 PDF 並抽出文字
- 建立一個 prompt，用來擷取關鍵資訊
- 把文件切塊，逐塊處理，取出任何答案
- 最後合併起來
- 再把這個簡單的做法延伸到另外三個比較難的問題

## 做法

- **設定**：拿一份 PDF（Formula 1 關於 Power Units 的財務規章），抽出文字來做 entity 擷取。我們會用它試著擷取埋在內容裡的答案。
- **簡單 Entity 擷取**：從文件的各個 chunk 擷取關鍵資訊，步驟是：
    - 建立 prompt 模板，裡面有我們的問題，以及預期格式的範例
    - 寫一個函式，輸入一個文字 chunk，跟 prompt 結合後取得回應
    - 執行腳本，把文字切塊、擷取答案，並輸出供解析
- **複雜 Entity 擷取**：問一些需要更強推理才能解出的較難問題

## 設定

```python
!pip install textract
!pip install tiktoken
```

```python
import textract
import os
import openai
import tiktoken

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

# Extract the raw text from each PDF using textract
text = textract.process('data/fia_f1_power_unit_financial_regulations_issue_1_-_2022-08-16.pdf', method='pdfminer').decode('utf-8')
clean_text = text.replace("  ", " ").replace("\n", "; ").replace(';',' ')
```

## 簡單 Entity 擷取

```python
# Example prompt - 
document = '<document>'
template_prompt=f'''Extract key pieces of information from this regulation document.
If a particular piece of information is not present, output \"Not specified\".
When you extract a key piece of information, include the closest page number.
Use the following format:\n0. Who is the author\n1. What is the amount of the "Power Unit Cost Cap" in USD, GBP and EUR\n2. What is the value of External Manufacturing Costs in USD\n3. What is the Capital Expenditure Limit in USD\n\nDocument: \"\"\"<document>\"\"\"\n\n0. Who is the author: Tom Anderson (Page 1)\n1.'''
print(template_prompt)
```

??? note "輸出"

    ```text
    Extract key pieces of information from this regulation document.
    If a particular piece of information is not present, output "Not specified".
    When you extract a key piece of information, include the closest page number.
    Use the following format:
    0. Who is the author
    1. What is the amount of the "Power Unit Cost Cap" in USD, GBP and EUR
    2. What is the value of External Manufacturing Costs in USD
    3. What is the Capital Expenditure Limit in USD

    Document: """<document>"""

    0. Who is the author: Tom Anderson (Page 1)
    1.
    ```

```python
# Split a text into smaller chunks of size n, preferably ending at the end of a sentence
def create_chunks(text, n, tokenizer):
    tokens = tokenizer.encode(text)
    """Yield successive n-sized chunks from text."""
    i = 0
    while i < len(tokens):
        # Find the nearest end of sentence within a range of 0.5 * n and 1.5 * n tokens
        j = min(i + int(1.5 * n), len(tokens))
        while j > i + int(0.5 * n):
            # Decode the tokens and check for full stop or newline
            chunk = tokenizer.decode(tokens[i:j])
            if chunk.endswith(".") or chunk.endswith("\n"):
                break
            j -= 1
        # If no end of sentence found, use n tokens as the chunk size
        if j == i + int(0.5 * n):
            j = min(i + n, len(tokens))
        yield tokens[i:j]
        i = j

def extract_chunk(document,template_prompt):
    prompt = template_prompt.replace('<document>',document)

    messages = [
            {"role": "system", "content": "You help extract information from documents."},
            {"role": "user", "content": prompt}
            ]

    response = client.chat.completions.create(
            model='gpt-4', 
            messages=messages,
            temperature=0,
            max_tokens=1500,
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )
    return "1." + response.choices[0].message.content
```

```python
# Initialise tokenizer
tokenizer = tiktoken.get_encoding("cl100k_base")

results = []
    
chunks = create_chunks(clean_text,1000,tokenizer)
text_chunks = [tokenizer.decode(chunk) for chunk in chunks]

for chunk in text_chunks:
    results.append(extract_chunk(chunk,template_prompt))
    #print(chunk)
    print(results[-1])
```

```python
groups = [r.split('\n') for r in results]

# zip the groups together
zipped = list(zip(*groups))
zipped = [x for y in zipped for x in y if "Not specified" not in x and "__" not in x]
zipped
```

??? note "輸出"

    ```text
    ['1. What is the amount of the "Power Unit Cost Cap" in USD, GBP and EUR: USD 95,000,000 (Page 2); GBP 76,459,000 (Page 2); EUR 90,210,000 (Page 2)',
     '2. What is the value of External Manufacturing Costs in USD: US Dollars 20,000,000 in respect of each of the Full Year Reporting Periods ending on 31 December 2023, 31 December 2024 and 31 December 2025, adjusted for Indexation (Page 10)',
     '3. What is the Capital Expenditure Limit in USD: US Dollars 30,000,000 (Page 32)']
    ```

## 複雜 Entity 擷取

```python
# Example prompt - 
template_prompt=f'''Extract key pieces of information from this regulation document.
If a particular piece of information is not present, output \"Not specified\".
When you extract a key piece of information, include the closest page number.
Use the following format:\n0. Who is the author\n1. How is a Minor Overspend Breach calculated\n2. How is a Major Overspend Breach calculated\n3. Which years do these financial regulations apply to\n\nDocument: \"\"\"<document>\"\"\"\n\n0. Who is the author: Tom Anderson (Page 1)\n1.'''
print(template_prompt)
```

??? note "輸出"

    ```text
    Extract key pieces of information from this regulation document.
    If a particular piece of information is not present, output "Not specified".
    When you extract a key piece of information, include the closest page number.
    Use the following format:
    0. Who is the author
    1. How is a Minor Overspend Breach calculated
    2. How is a Major Overspend Breach calculated
    3. Which years do these financial regulations apply to

    Document: """<document>"""

    0. Who is the author: Tom Anderson (Page 1)
    1.
    ```

```python
results = []

for chunk in text_chunks:
    results.append(extract_chunk(chunk,template_prompt))
    
groups = [r.split('\n') for r in results]

# zip the groups together
zipped = list(zip(*groups))
zipped = [x for y in zipped for x in y if "Not specified" not in x and "__" not in x]
zipped
```

??? note "輸出"

    ```text
    ['1. How is a Minor Overspend Breach calculated: A Minor Overspend Breach arises when a Power Unit Manufacturer submits its Full Year Reporting Documentation and Relevant Costs reported therein exceed the Power Unit Cost Cap by less than 5% (Page 24)',
     '2. How is a Major Overspend Breach calculated: A Material Overspend Breach arises when a Power Unit Manufacturer submits its Full Year Reporting Documentation and Relevant Costs reported therein exceed the Power Unit Cost Cap by 5% or more (Page 25)',
     '3. Which years do these financial regulations apply to: 2026 onwards (Page 1)',
     '3. Which years do these financial regulations apply to: 2023, 2024, 2025, 2026 and subsequent Full Year Reporting Periods (Page 2)',
     '3. Which years do these financial regulations apply to: 2022-2025 (Page 6)',
     '3. Which years do these financial regulations apply to: 2023, 2024, 2025, 2026 and subsequent Full Year Reporting Periods (Page 10)',
     '3. Which years do these financial regulations apply to: 2022 (Page 14)',
     '3. Which years do these financial regulations apply to: 2022 (Page 16)',
     '3. Which years do these financial regulations apply to: 2022 (Page 19)',
     '3. Which years do these financial regulations apply to: 2022 (Page 21)',
     '3. Which years do these financial regulations apply to: 2026 onwards (Page 26)',
     '3. Which years do these financial regulations apply to: 2026 (Page 2)',
     '3. Which years do these financial regulations apply to: 2022 (Page 30)',
     '3. Which years do these financial regulations apply to: 2022 (Page 32)',
     '3. Which years do these financial regulations apply to: 2023, 2024 and 2025 (Page 1)',
     '3. Which years do these financial regulations apply to: 2022 (Page 37)',
     '3. Which years do these financial regulations apply to: 2026 onwards (Page 40)',
     '3. Which years do these financial regulations apply to: 2022 (Page 1)',
     '3. Which years do these financial regulations apply to: 2026 to 2030 seasons (Page 46)',
     '3. Which years do these financial regulations apply to: 2022 (Page 47)',
     '3. Which years do these financial regulations apply to: 2022 (Page 1)',
     '3. Which years do these financial regulations apply to: 2022 (Page 1)',
     '3. Which years do these financial regulations apply to: 2022 (Page 56)',
     '3. Which years do these financial regulations apply to: 2022 (Page 1)',
     '3. Which years do these financial regulations apply to: 2022 (Page 16)',
     '3. Which years do these financial regulations apply to: 2022 (Page 16)']
    ```

## 整合

前兩個答案我們都順利擷取到了，第三個被每頁都出現的日期干擾，不過正確答案其實也在結果裡。

想進一步調整，可以試試：
- 更詳細或更具體的 prompt
- 如果有足夠的訓練資料，fine-tuning 一個模型，讓它很擅長找出特定一組輸出
- 資料切塊的方式：我們用 1000 個 token、不重疊，但更聰明的切法（例如依章節切、依 token 切等）也許能得到更好的結果

不過，只靠最少的調整，我們已經用一份長文件的內容回答了 6 個難度不一的問題，也得到一個可重複使用的做法，能套用到任何需要 entity 擷取的長文件。期待看到你做出什麼！

## 重點整理

- 超出 context window 的文件，用「切塊、逐塊問、合併答案」處理。
- prompt 裡附上預期的輸出格式範例，才方便後續程式解析。
- 簡單的事實擷取容易，需要推理的問題比較容易被雜訊干擾（像每頁重複的日期）。
- 可調整的三個方向：prompt、fine-tuning、切塊方式。

## 練習

1. 把 chunk 大小從 1000 token 改成 500 或 2000，比較擷取結果的差異。
2. 改成讓相鄰 chunk 有重疊，看原本被切斷的資訊能不能被抓到。
3. 修改 prompt，明確告訴模型忽略每頁重複的日期，重跑第三個問題。
