---
translated: true
source: multimodal/reading_charts_graphs_powerpoints.ipynb
---
# 處理圖表和簡報

> 原文：[multimodal/reading_charts_graphs_powerpoints.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/multimodal/reading_charts_graphs_powerpoints.ipynb)

用 Claude 的視覺分析能力，從圖表和簡報裡取出洞察。

## 這篇在做什麼

這篇示範怎麼把圖表和整份簡報（slide deck）交給 Claude 讀：先用 PDF 支援直接問圖表的問題，再處理簡報的頁數上限和 RAG 問題，做法是讓 Claude 依序把整份簡報「旁白」成文字。

## 學完你會

- 把圖表 PDF 搭配文字問題傳給 Claude API，並用幾個技巧提高答對率
- 把簡報轉成 PDF 直接餵給 Claude 分析
- 用逐頁 narration 把簡報轉成純文字，接進只吃文字的流程（例如向量搜尋）

## 開跑前

需要 Anthropic API key，以及要分析的圖表 PDF 和簡報 PDF（notebook 會附範例檔）。

Claude 很擅長處理圖表和整份簡報。依你的使用情境，有不少技巧可以善用。這份 recipe 會示範用 Claude 處理這些素材的常見模式。

## 圖表

大部分時候，用 Claude 處理圖表很簡單。來看怎麼把它們讀進來並傳給 Claude，以及一些提升結果的常見技巧。

### 讀入並呼叫 Claude API
把圖表傳給 Claude 最好的方式，是善用它的視覺能力和 PDF 支援功能。也就是把圖表的 PDF 文件，連同一個關於它的文字問題一起給 Claude。

```python
# Install and create the Anthropic client.
%pip install anthropic
```

```python
import base64

from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-sonnet-5-5"
```

```python
# Make a useful helper function.
def get_completion(messages):
    response = client.messages.create(model=MODEL_NAME, max_tokens=8192, messages=messages)
    return "".join(block.text for block in response.content if block.type == "text")
```

```python
# To start, we'll need a PDF. We will be using the .pdf document located at cvna_2021_annual_report.pdf.
# Start by reading in the PDF and encoding it as base64.
with open("./documents/cvna_2021_annual_report.pdf", "rb") as pdf_file:
    binary_data = pdf_file.read()
    base_64_encoded_data = base64.b64encode(binary_data)
    base64_string = base_64_encoded_data.decode("utf-8")
```

來看怎麼把這份文件和一個簡單的問題一起傳給 model。

```python
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64_string,
                },
            },
            {"type": "text", "text": "What's in this document? Answer in a single sentence."},
        ],
    }
]

print(get_completion(messages))
```

??? note "輸出"

    ```text
    This is a page from Carvana's 2021 Annual Report showing four key metrics: retail units sold, total revenue, total markets at year end, and car vending machines, all displaying significant growth from 2014 to 2021.
    ```

不錯！現在來問一些更實用的問題。

```python
questions = [
    "What was CVNA revenue in 2020?",
    "How many additional markets has Carvana added since 2014?",
    "What was 2016 revenue per retail unit sold?",
]

for index, question in enumerate(questions):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64_string,
                    },
                },
                {"type": "text", "text": question},
            ],
        }
    ]

    print(f"\n----------Question {index + 1}----------")
    print(get_completion(messages))
```

??? note "輸出"

    ```text

    ----------Question 1----------
    According to the graph showing Total Revenue ($M), Carvana's revenue in 2020 was $5,587 million (or approximately $5.59 billion).

    ----------Question 2----------
    According to the "TOTAL MARKETS AT YEAR END" graph, Carvana started with 4 markets in 2014 and grew to 311 markets by 2021. Therefore, Carvana added 307 markets since 2014 (311 - 4 = 307 additional markets).

    ----------Question 3----------
    Let me calculate this for you:

    2016 Revenue: $365 million
    2016 Retail Units Sold: 18,761 units

    $365 million ÷ 18,761 units = $19,455 per unit (rounded to nearest dollar)

    So in 2016, Carvana's revenue per retail unit sold was approximately $19,455.
    ```

如你所見，Claude 能回答相當細節的圖表問題。不過有些技巧能幫你把效果發揮到最好。
- 有時 Claude 的算術能力會礙事。你會發現上面第三題如果多取樣幾次，偶爾會因為算錯而輸出錯誤的最終答案。可以考慮提供計算機 tool 給 Claude，避免這類錯誤。
- 對超級複雜的圖表，可以要求 Claude「先描述你在文件裡看到的每個資料點」，達到跟傳統 Chain of Thought 類似的改善。
- Claude 偶爾會在依賴很多顏色傳達資訊的圖表上吃力，例如有很多組的分組長條圖。請 Claude 先用 HEX 色碼辨識圖上的顏色，可以提高準確度。

## 簡報

既然我們知道 Claude 是圖表高手，接下來自然要擴展到圖表和圖形真正的家：簡報！

簡報是許多領域的關鍵資訊來源，包括金融服務。雖然你*可以*用 PyPDF 這類套件從簡報擷取文字，但簡報大量依賴圖表，這樣做往往不是好選擇，因為 model 很難取得它們真正需要的資訊。

所以 PDF 支援功能是很好的替代方案。它處理 PDF 文件時會同時使用擷取出的文字和視覺。這一節會說明怎麼在 Claude 裡用 PDF 文件檢視簡報，以及怎麼處理這個做法的一些常見陷阱。

把一般簡報交給 Claude 最好的方式，是下載成 PDF 直接提供給 Claude。

```python
# Open the multi-page PDF document the same way we did earlier.
with open("./documents/twilio_q4_2023.pdf", "rb") as pdf_file:
    binary_data = pdf_file.read()
    base_64_encoded_data = base64.b64encode(binary_data)
    base64_string = base_64_encoded_data.decode("utf-8")
```

```python
# Now let's pass the document directly to Claude. Note that Claude will process both the text and visual elements of the document.
question = "What was Twilio y/y revenue growth for fiscal year 2023?"
content = [
    {
        "type": "document",
        "source": {"type": "base64", "media_type": "application/pdf", "data": base64_string},
    },
    {"type": "text", "text": question},
]

messages = [{"role": "user", "content": content}]

print(get_completion(messages))
```

??? note "輸出"

    ```text
    According to the financial results shown in the presentation, Twilio's year-over-year revenue growth for fiscal year 2023 was 9%. This can be found in the "Total Company Results Highlights" section, which shows FY 2023 revenue growth of 9%.
    ```

這個做法是很好的起點，有些使用情境下表現最好。不過有一些限制。
- 一個請求裡，所有提供的文件加起來最多 100 頁（我們打算隨時間提高這個上限）。
- 如果你把簡報內容用在 RAG，把多模態 PDF 放進 embedding 可能造成問題。

幸好，我們可以利用 Claude 的視覺能力，得到比一般 PDF 文字擷取品質高得多的簡報**文字形式**表示。

我們發現最好的做法，是請 Claude 從頭到尾依序為整份簡報做旁白，把目前這張投影片和它之前的旁白一起傳給它。來看怎麼做。

```python
# Define a prompt for narrating our slide deck. We would adjut this prompt based on the nature of the deck, but keep the structure largely the same.
prompt = """
You are the Twilio CFO, narrating your Q4 2023 earnings presentation.

The entire earnings presentation document is provided to you.
Please narrate this presentation from Twilio's Q4 2023 Earnings as if you were the presenter. Do not talk about any things, especially acronyms, if you are not exactly sure you know what they mean.

Do not leave any details un-narrated as some of your viewers are vision-impaired, so if you don't narrate every number they won't know the number.

Structure your response like this:
<narration>
    <page_narration id=1>
    [Your narration for page 1]
    </page_narration>

    <page_narration id=2>
    [Your narration for page 2]
    </page_narration>

    ... and so on for each page
</narration>

Use excruciating detail for each page, ensuring you describe every visual element and number present. Show the full response in a single message.
"""
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64_string,
                },
            },
            {"type": "text", "text": prompt},
        ],
    }
]

# Now we use our prompt to narrate the entire deck. A full narration of this 27-page deck runs well
# past 20K output tokens, so this call gets a much larger max_tokens budget than our helper and
# streams the response (the SDK requires streaming for requests this long). We keep the final
# message so we can check stop_reason below. Note that this may take a few minutes to run.
with client.messages.stream(model=MODEL_NAME, max_tokens=32000, messages=messages) as stream:
    narration_response = stream.get_final_message()
completion = "".join(block.text for block in narration_response.content if block.type == "text")
```

```python
import re

# Next we'll parse the response from Claude using regex
pattern = r"<narration>(.*?)</narration>"
match = re.search(pattern, completion.strip(), re.DOTALL)
if match:
    narration = match.group(1)
else:
    raise ValueError(
        f"No complete <narration> block found (stop_reason={narration_response.stop_reason!r}). "
        "If stop_reason is 'max_tokens', the response was truncated: raise max_tokens above."
    )
```

現在我們有了文字形式的旁白（離完美還很遠，但已經相當不錯），就能把這份簡報用在任何純文字的流程，包括向量搜尋！

最後做個確認，對只有旁白的設定問幾個問題！

```python
questions = [
    "What percentage of q4 total revenue was the Segment business line?",
    "Has the rate of growth of quarterly revenue been increasing or decreasing? Give just an answer.",
    "What was acquisition revenue for the year ended december 31, 2023 (including negative revenues)?",
]

for index, question in enumerate(questions):
    prompt = f"""You are an expert financial analyst analyzing a transcript of Twilio's earnings call.
Here is the transcript:
<transcript>
{narration}
</transcript>

Please answer the following question:
<question>
{question}
</question>"""
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]

    print(f"\n----------Question {index + 1}----------")
    print(get_completion(messages))
```

??? note "輸出"

    ```text

    ----------Question 1----------
    Let me calculate this:

    Segment revenue in Q4 2023: $75 million
    Total revenue in Q4 2023: $1,076 million

    $75M ÷ $1,076M = 0.0697 or approximately 7%

    Therefore, the Segment business line represented approximately 7% of Twilio's total Q4 2023 revenue.

    ----------Question 2----------
    Decreasing. The transcript shows Q4 2023 revenue growth was 5% year-over-year, while for the full year 2023 revenue growth was 9% year-over-year, indicating a slowing growth rate. Additionally, the Q1 2024 guidance projects even lower growth of 2-3% year-over-year, confirming the declining trend.

    ----------Question 3----------
    Let me help calculate the acquisition revenue for 2023.

    From the transcript, we can see:
    - Total revenue for 2023: $4,154 million
    - Organic revenue for 2023: $4,146 million

    Therefore, acquisition revenue would be:
    Total Revenue - Organic Revenue = $4,154M - $4,146M = $8 million

    So the acquisition revenue for the year ended December 31, 2023 was $8 million.

    This can be verified by the fact that the difference between total revenue growth (9%) and organic revenue growth (10%) also suggests a small contribution from acquisitions.
    ```

看起來不錯！有了這些技巧，你就可以開始把 model 用在像簡報這種大量圖表的內容上了。

## 重點整理

- 圖表最好用 PDF 加文字問題的方式餵給 Claude，善用視覺和 PDF 支援
- 算術容易出錯就加計算機 tool；圖很複雜就先要求描述每個資料點；顏色多就先要求辨識 HEX 色碼
- 簡報用 PyPDF 擷取文字常常拿不到圖表資訊，直接給 PDF 比較好，但有 100 頁上限，也不適合直接放進 RAG embedding
- 讓 Claude 逐頁帶著前面旁白做 narration，能得到可用在純文字流程的高品質表示

## 練習

1. 對圖表的問題 prompt 加上「先描述你看到的每個資料點」，比較答案有沒有更準。
2. 把上面算術題搭配一個簡單的 calculator tool，確認最終答案不再偶爾算錯。
3. 改簡報 narration 的 prompt，讓每張投影片的旁白限制在 3 句內，再用旁白文字問第 14 個 cell 同樣的問題，比較差異。
