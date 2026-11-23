---
translated: true
source: examples/Whisper_processing_guide.ipynb
---

# 強化 Whisper 逐字稿：前處理與後處理技巧

> 原文：[examples/Whisper_processing_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Whisper_processing_guide.ipynb)



## 這篇在做什麼

教你在送進 Whisper 之前先把音檔修剪、切段，轉完逐字稿後再補標點、修正產品術語、處理 Unicode 問題，讓逐字稿更清楚。範例音檔是一段 ChatGPT 寫的虛構財報電話會議，由作者朗讀。

## 學完你會

- 用 PyDub 偵測並裁掉音檔開頭的靜音，再把音檔切成多段
- 寫後處理函式：移除非 ASCII 字元、補格式與標點、修正術語（例如 "five two nine" 改成 "529"）
- 把各段逐字稿串起來，得到整份處理過的結果

## 開跑前

- OpenAI API key（呼叫 Whisper 轉錄）
- 安裝 PyDub，並準備一個音檔

這份 notebook 是改善 Whisper 逐字稿的指南。我們會透過修剪和切段整理音訊資料，提升 Whisper 的轉錄品質。轉錄完之後，再修飾輸出：補標點、調整產品術語（例如把 'five two nine' 改成 '529'）、減輕 Unicode 問題。這些做法能讓逐字稿更清楚，但別忘了，依你自己的使用情境客製可能更有幫助。



## 設定

先匯入幾個函式庫：

- [PyDub](http://pydub.com/) 是簡單好用的 Python 音訊處理函式庫，可以切片、串接、匯出音檔。

- `IPython.display` 模組的 `Audio` 類別可以建立音訊控制元件，在 Jupyter notebook 裡播放聲音，直接在 notebook 裡播放音訊資料很方便。

- 音檔方面，我們用一段 ChatGPT 寫的虛構財報電話會議，由作者朗讀。這個音檔相對較短，但希望能讓你清楚看到這些前處理和後處理步驟怎麼套用到任何音檔。

```python
from openai import OpenAI
import os
import urllib
from IPython.display import Audio
from pathlib import Path
from pydub import AudioSegment
import ssl
```

```python
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

```python
# set download paths
earnings_call_remote_filepath = "https://cdn.openai.com/API/examples/data/EarningsCall.wav"

# set local save locations
earnings_call_filepath = "data/EarningsCall.wav"

# download example audio files and save locally
ssl._create_default_https_context = ssl._create_unverified_context
urllib.request.urlretrieve(earnings_call_remote_filepath, earnings_call_filepath)
```

??? note "輸出"

    ```text
    ('data/EarningsCall.wav', <http.client.HTTPMessage at 0x11be41f50>)
    ```

有時候開頭有很長靜音的檔案，會讓 Whisper 轉錄錯誤。我們用 Pydub 偵測並修剪靜音。

這裡把分貝閾值設成 20，你可以依需要調整。

```python
# Function to detect leading silence
# Returns the number of milliseconds until the first sound (chunk averaging more than X decibels)
def milliseconds_until_sound(sound, silence_threshold_in_decibels=-20.0, chunk_size=10):
    trim_ms = 0  # ms

    assert chunk_size > 0  # to avoid infinite loop
    while sound[trim_ms:trim_ms+chunk_size].dBFS < silence_threshold_in_decibels and trim_ms < len(sound):
        trim_ms += chunk_size

    return trim_ms
```

```python
def trim_start(filepath):
    path = Path(filepath)
    directory = path.parent
    filename = path.name
    audio = AudioSegment.from_file(filepath, format="wav")
    start_trim = milliseconds_until_sound(audio)
    trimmed = audio[start_trim:]
    new_filename = directory / f"trimmed_{filename}"
    trimmed.export(new_filename, format="wav")
    return trimmed, new_filename
```

```python
def transcribe_audio(file,output_dir):
    audio_path = os.path.join(output_dir, file)
    with open(audio_path, 'rb') as audio_data:
        transcription = client.audio.transcriptions.create(
            model="whisper-1", file=audio_data)
        return transcription.text
```

我們有時會看到逐字稿裡被插入 unicode 字元，移除所有非 ASCII 字元應該能減輕這個問題。

注意：如果你轉錄的是希臘文、斯拉夫文、阿拉伯文、中文等語言，就不要用這個函式。

```python
# Define function to remove non-ascii characters
def remove_non_ascii(text):
    return ''.join(i for i in text if ord(i)<128)
```

這個函式會替逐字稿加上格式和標點。Whisper 產生的逐字稿有標點，但沒有格式。

```python
# Define function to add punctuation
def punctuation_assistant(ascii_transcript):

    system_prompt = """You are a helpful assistant that adds punctuation to text.
      Preserve the original words and only insert necessary punctuation such as periods,
     commas, capialization, symbols like dollar sings or percentage signs, and formatting.
     Use only the context provided. If there is no context provided say, 'No context provided'\n"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": ascii_transcript
            }
        ]
    )
    return response
```

我們的音檔是一場虛構財報電話會議的錄音，裡面有很多金融產品。這個函式可以確保 Whisper 把金融產品名稱轉錯的時候，能被修正回來。

```python
# Define function to fix product mispellings
def product_assistant(ascii_transcript):
    system_prompt = """You are an intelligent assistant specializing in financial products;
    your task is to process transcripts of earnings calls, ensuring that all references to
     financial products and common financial terms are in the correct format. For each
     financial product or common term that is typically abbreviated as an acronym, the full term 
    should be spelled out followed by the acronym in parentheses. For example, '401k' should be
     transformed to '401(k) retirement savings plan', 'HSA' should be transformed to 'Health Savings Account (HSA)'
    , 'ROA' should be transformed to 'Return on Assets (ROA)', 'VaR' should be transformed to 'Value at Risk (VaR)'
, and 'PB' should be transformed to 'Price to Book (PB) ratio'. Similarly, transform spoken numbers representing 
financial products into their numeric representations, followed by the full name of the product in parentheses. 
For instance, 'five two nine' to '529 (Education Savings Plan)' and 'four zero one k' to '401(k) (Retirement Savings Plan)'.
 However, be aware that some acronyms can have different meanings based on the context (e.g., 'LTV' can stand for 
'Loan to Value' or 'Lifetime Value'). You will need to discern from the context which term is being referred to 
and apply the appropriate transformation. In cases where numerical figures or metrics are spelled out but do not 
represent specific financial products (like 'twenty three percent'), these should be left as is. Your role is to
 analyze and adjust financial product terminology in the text. Once you've done that, produce the adjusted 
 transcript and a list of the words you've changed"""
    response = client.chat.completions.create(
        model="gpt-4",
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": ascii_transcript
            }
        ]
    )
    return response
```

這個函式會建立一個新檔案，檔名是在原檔名後面加上 'trimmed'

```python
# Trim the start of the original audio file
trimmed_audio = trim_start(earnings_call_filepath)
```

```python
trimmed_audio, trimmed_filename = trim_start(earnings_call_filepath)
```

我們的假財報音檔長度偏短，所以切段的設定要配合調整。切段長度可以依需要調整。

```python
# Segment audio
trimmed_audio = AudioSegment.from_wav(trimmed_filename)  # Load the trimmed audio file

one_minute = 1 * 60 * 1000  # Duration for each segment (in milliseconds)

start_time = 0  # Start time for the first segment

i = 0  # Index for naming the segmented files

output_dir_trimmed = "trimmed_earnings_directory"  # Output directory for the segmented files

if not os.path.isdir(output_dir_trimmed):  # Create the output directory if it does not exist
    os.makedirs(output_dir_trimmed)

while start_time < len(trimmed_audio):  # Loop over the trimmed audio file
    segment = trimmed_audio[start_time:start_time + one_minute]  # Extract a segment
    segment.export(os.path.join(output_dir_trimmed, f"trimmed_{i:02d}.wav"), format="wav")  # Save the segment
    start_time += one_minute  # Update the start time for the next segment
    i += 1  # Increment the index for naming the next file
```

```python
# Get list of trimmed and segmented audio files and sort them numerically
audio_files = sorted(
    (f for f in os.listdir(output_dir_trimmed) if f.endswith(".wav")),
    key=lambda f: int(''.join(filter(str.isdigit, f)))
)
```

```python
# Use a loop to apply the transcribe function to all audio files
transcriptions = [transcribe_audio(file, output_dir_trimmed) for file in audio_files]
```

```python
# Concatenate the transcriptions
full_transcript = ' '.join(transcriptions)
```

```python
print(full_transcript)
```

??? note "輸出"

    ```text
    Good afternoon, everyone. And welcome to FinTech Plus Sync's second quarter 2023 earnings call. I'm John Doe, CEO of FinTech Plus. We've had a stellar Q2 with a revenue of 125 million, a 25% increase year over year. Our gross profit margin stands at a solid 58%, due in part to cost efficiencies gained from our scalable business model. Our EBITDA has surged to 37.5 million, translating to a remarkable 30% EBITDA margin. Our net income for the quarter rose to 16 million, which is a noteworthy increase from 10 million in Q2 2022. Our total addressable market has grown substantially thanks to the expansion of our high yield savings product line and the new RoboAdvisor platform. We've been diversifying our asset-backed securities portfolio, investing heavily in collateralized. debt obligations, and residential mortgage-backed securities. We've also invested $25 million in AAA rated corporate bonds, enhancing our risk adjusted returns. As for our balance sheet, total assets reached $1.5 billion with total liabilities at $900 million, leaving us with a solid equity base of $600 million. Our debt-to-equity ratio stands at 1.5, a healthy figure considering our expansionary phase. We continue to see substantial organic user growth, with customer acquisition cost dropping by 15% and lifetime value growing by 25%. Our LTVCAC ratio is at an impressive 3.5%. In terms of risk management, we have a value-at-risk model in place with a 99%... confidence level indicating that our maximum loss will not exceed 5 million in the next trading day. We've adopted a conservative approach to managing our leverage and have a healthy tier one capital ratio of 12.5%. Our forecast for the coming quarter is positive. We expect revenue to be around 135 million and 8% quarter over quarter growth driven primarily by our cutting edge blockchain solutions and AI driven predictive analytics. We're also excited about the upcoming IPO of our FinTech subsidiary Pay Plus, which we expect to raise 200 million, significantly bolstering our liquidity and paving the way for aggressive growth strategies. We thank our shareholders for their continued faith in us and we look forward to an even more successful Q3. Thank you so much.
    ```

```python
# Remove non-ascii characters from the transcript
ascii_transcript = remove_non_ascii(full_transcript)
```

```python
print(ascii_transcript)
```

??? note "輸出"

    ```text
    Good afternoon, everyone. And welcome to FinTech Plus Sync's second quarter 2023 earnings call. I'm John Doe, CEO of FinTech Plus. We've had a stellar Q2 with a revenue of 125 million, a 25% increase year over year. Our gross profit margin stands at a solid 58%, due in part to cost efficiencies gained from our scalable business model. Our EBITDA has surged to 37.5 million, translating to a remarkable 30% EBITDA margin. Our net income for the quarter rose to 16 million, which is a noteworthy increase from 10 million in Q2 2022. Our total addressable market has grown substantially thanks to the expansion of our high yield savings product line and the new RoboAdvisor platform. We've been diversifying our asset-backed securities portfolio, investing heavily in collateralized. debt obligations, and residential mortgage-backed securities. We've also invested $25 million in AAA rated corporate bonds, enhancing our risk adjusted returns. As for our balance sheet, total assets reached $1.5 billion with total liabilities at $900 million, leaving us with a solid equity base of $600 million. Our debt-to-equity ratio stands at 1.5, a healthy figure considering our expansionary phase. We continue to see substantial organic user growth, with customer acquisition cost dropping by 15% and lifetime value growing by 25%. Our LTVCAC ratio is at an impressive 3.5%. In terms of risk management, we have a value-at-risk model in place with a 99%... confidence level indicating that our maximum loss will not exceed 5 million in the next trading day. We've adopted a conservative approach to managing our leverage and have a healthy tier one capital ratio of 12.5%. Our forecast for the coming quarter is positive. We expect revenue to be around 135 million and 8% quarter over quarter growth driven primarily by our cutting edge blockchain solutions and AI driven predictive analytics. We're also excited about the upcoming IPO of our FinTech subsidiary Pay Plus, which we expect to raise 200 million, significantly bolstering our liquidity and paving the way for aggressive growth strategies. We thank our shareholders for their continued faith in us and we look forward to an even more successful Q3. Thank you so much.
    ```

```python
# Use punctuation assistant function
response = punctuation_assistant(ascii_transcript)
```

```python
# Extract the punctuated transcript from the model's response
punctuated_transcript = response.choices[0].message.content
```

```python
print(punctuated_transcript)
```

??? note "輸出"

    ```text
    Good afternoon, everyone. And welcome to FinTech Plus Sync's second quarter 2023 earnings call. I'm John Doe, CEO of FinTech Plus. We've had a stellar Q2 with a revenue of $125 million, a 25% increase year over year. Our gross profit margin stands at a solid 58%, due in part to cost efficiencies gained from our scalable business model. Our EBITDA has surged to $37.5 million, translating to a remarkable 30% EBITDA margin. Our net income for the quarter rose to $16 million, which is a noteworthy increase from $10 million in Q2 2022. Our total addressable market has grown substantially thanks to the expansion of our high yield savings product line and the new RoboAdvisor platform. We've been diversifying our asset-backed securities portfolio, investing heavily in collateralized debt obligations, and residential mortgage-backed securities. We've also invested $25 million in AAA rated corporate bonds, enhancing our risk-adjusted returns. As for our balance sheet, total assets reached $1.5 billion with total liabilities at $900 million, leaving us with a solid equity base of $600 million. Our debt-to-equity ratio stands at 1.5, a healthy figure considering our expansionary phase. We continue to see substantial organic user growth, with customer acquisition cost dropping by 15% and lifetime value growing by 25%. Our LTVCAC ratio is at an impressive 3.5%. In terms of risk management, we have a value-at-risk model in place with a 99% confidence level indicating that our maximum loss will not exceed $5 million in the next trading day. We've adopted a conservative approach to managing our leverage and have a healthy tier one capital ratio of 12.5%. Our forecast for the coming quarter is positive. We expect revenue to be around $135 million and 8% quarter over quarter growth driven primarily by our cutting-edge blockchain solutions and AI-driven predictive analytics. We're also excited about the upcoming IPO of our FinTech subsidiary Pay Plus, which we expect to raise $200 million, significantly bolstering our liquidity and paving the way for aggressive growth strategies. We thank our shareholders for their continued faith in us and we look forward to an even more successful Q3. Thank you so much.
    ```

```python
# Use product assistant function
response = product_assistant(punctuated_transcript)
```

```python
# Extract the final transcript from the model's response
final_transcript = response.choices[0].message.content
```

```python
print(final_transcript)
```

??? note "輸出"

    ```text
    Good afternoon, everyone. And welcome to FinTech Plus Sync's second quarter 2023 earnings call. I'm John Doe, CEO of FinTech Plus. We've had a stellar second quarter (Q2) with a revenue of $125 million, a 25% increase year over year. Our gross profit margin stands at a solid 58%, due in part to cost efficiencies gained from our scalable business model. Our Earnings Before Interest, Taxes, Depreciation, and Amortization (EBITDA) has surged to $37.5 million, translating to a remarkable 30% EBITDA margin. Our net income for the quarter rose to $16 million, which is a noteworthy increase from $10 million in second quarter (Q2) 2022. Our total addressable market has grown substantially thanks to the expansion of our high yield savings product line and the new RoboAdvisor platform. We've been diversifying our asset-backed securities portfolio, investing heavily in Collateralized Debt Obligations (CDOs), and Residential Mortgage-Backed Securities (RMBS). We've also invested $25 million in AAA rated corporate bonds, enhancing our risk-adjusted returns. As for our balance sheet, total assets reached $1.5 billion with total liabilities at $900 million, leaving us with a solid equity base of $600 million. Our Debt-to-Equity (D/E) ratio stands at 1.5, a healthy figure considering our expansionary phase. We continue to see substantial organic user growth, with Customer Acquisition Cost (CAC) dropping by 15% and Lifetime Value (LTV) growing by 25%. Our LTV to CAC (LTVCAC) ratio is at an impressive 3.5%. In terms of risk management, we have a Value at Risk (VaR) model in place with a 99% confidence level indicating that our maximum loss will not exceed $5 million in the next trading day. We've adopted a conservative approach to managing our leverage and have a healthy Tier 1 Capital ratio of 12.5%. Our forecast for the coming quarter is positive. We expect revenue to be around $135 million and 8% quarter over quarter growth driven primarily by our cutting-edge blockchain solutions and AI-driven predictive analytics. We're also excited about the upcoming Initial Public Offering (IPO) of our FinTech subsidiary Pay Plus, which we expect to raise $200 million, significantly bolstering our liquidity and paving the way for aggressive growth strategies. We thank our shareholders for their continued faith in us and we look forward to an even more successful third quarter (Q3). Thank you so much.

    Words Changed:
    1. Q2 -> second quarter (Q2)
    2. EBITDA -> Earnings Before Interest, Taxes, Depreciation, and Amortization (EBITDA)
    3. Q2 2022 -> second quarter (Q2) 2022
    4. CDOs -> Collateralized Debt Obligations (CDOs)
    5. RMBS -> Residential Mortgage-Backed Securities (RMBS)
    6. D/E -> Debt-to-Equity (D/E)
    7. CAC -> Customer Acquisition Cost (CAC)
    8. LTV -> Lifetime Value (LTV)
    9. LTVCAC -> LTV to CAC (LTVCAC)
    10. VaR -> Value at Risk (VaR)
    11. IPO -> Initial Public Offering (IPO)
    12. Q3 -> third quarter (Q3)
    ```

## 重點整理

- 前處理動音檔（修剪靜音、切段），後處理動文字（標點、術語、字元），兩邊都有改善空間。
- 開頭太長的靜音會讓 Whisper 轉錯，先裁掉比較穩。
- 移除非 ASCII 字元能擋掉怪字元，但非英文語言不能用。
- 術語修正是依你的領域客製的，換一個領域就要換一份對照。

## 練習

1. 改分貝閾值（目前是 20），聽聽修剪結果有什麼不同。
2. 在術語修正的函式裡加一個你自己領域的詞（例如把某個縮寫念法對應回正確寫法）。
3. 調整切段長度，比較不同長度下各段逐字稿的銜接是否順。
