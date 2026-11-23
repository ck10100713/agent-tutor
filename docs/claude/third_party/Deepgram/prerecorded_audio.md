---
translated: true
source: third_party/Deepgram/prerecorded_audio.ipynb
---

# 用 Deepgram 轉錄音檔，並用 Anthropic 準備面試問題！

> 原文：[third_party/Deepgram/prerecorded_audio.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/Deepgram/prerecorded_audio.ipynb)

用 Deepgram 轉錄音檔，並用 Claude 產生面試問題來做準備。

## 這篇在做什麼

這份 notebook 先用 Deepgram 把線上的音檔轉成逐字稿，再把逐字稿送給 Claude，產生一組建議的面試問題。整個流程分成五步，每步一個 cell。

## 學完你會

- 用 Deepgram SDK 轉錄放在 URL 上的音檔，輸出 JSON。
- 解析 Deepgram 的 JSON，印出逐句的純文字逐字稿。
- 把逐字稿丟給 Claude，產生面試問題。

## 開跑前

需要 Deepgram API key（要先註冊 Deepgram，帳號要有剩餘 credit）和 Anthropic API key，並準備一個可公開存取的音檔 URL。

**把這份 notebook 複製到你自己的雲端硬碟，然後照下面的說明做！** 🥳🥳🥳

----------------------------

# 開始：
執行下面三個 cell，就能轉錄任何你想轉的音檔。下面的註解會指出你可以調整哪些變數來改變輸出。

執行這份 notebook 之前，你需要準備幾個要轉錄的音檔 URL。任何音檔都可以。

另外，如果你還沒註冊 Deepgram，可以看這個連結：https://dpgr.am/prerecorded-notebook-signup

# 步驟 1：相依套件

執行這個 cell 下載所有必要的相依套件。

注意：你可以按左邊的播放鈕執行 cell，或點選 cell 後同時按 `shift`+`ENTER`（Mac 是 `shift` + `return`）。

```python
%pip install requests ffmpeg-python
%pip install deepgram-sdk --upgrade
%pip install requests
%pip install anthropic
```

# 步驟 2：音檔 URL

找一些放在伺服器上的音檔來使用這份 notebook。或者用 Deepgram 提供的範例檔，就在下面的程式碼裡。

```python
# Have you completed Step 2 above? 👀
# Do you see your audio file in the folder on the left? 📂
```

# 步驟 3：轉錄

填入下面的變數：


* `DG_KEY` = 你個人的 Deepgram API key
* `AUDIO_FILE_URL` = 你想轉錄的音檔 URL


現在執行 cell！（`Shift` + `Enter`）

-----------



另外，如果你已經是 Deepgram 使用者，在這個 cell 遇到錯誤，最常見的解法是：

1. 你可能需要更新安裝的 deepgram-sdk。
2. 你可能需要檢查 Deepgram 帳號還剩多少 credit。

```python
import requests
from deepgram import DeepgramClient, FileSource, PrerecordedOptions

# Deepgram API key
DG_KEY = "🔑🔑🔑 Your API Key here! 🔑🔑🔑"

# URL of the audio file
AUDIO_FILE_URL = "https://static.deepgram.com/examples/nasa-spacewalk-interview.wav"

# Path to save the transcript JSON file
TRANSCRIPT_FILE = "transcript.json"


def main():
    try:
        # STEP 1: Create a Deepgram client using the API key
        deepgram = DeepgramClient(DG_KEY)

        # Download the audio file from the URL
        response = requests.get(AUDIO_FILE_URL, timeout=60)
        if response.status_code == 200:
            buffer_data = response.content
        else:
            print("Failed to download audio file")
            return

        payload: FileSource = {
            "buffer": buffer_data,
        }

        # STEP 2: Configure Deepgram options for audio analysis
        options = PrerecordedOptions(
            model="nova-2",
            smart_format=True,
        )

        # STEP 3: Call the transcribe_file method with the text payload and options
        response = deepgram.listen.prerecorded.v("1").transcribe_file(payload, options)

        # STEP 4: Write the response JSON to a file
        with open(TRANSCRIPT_FILE, "w") as transcript_file:
            transcript_file.write(response.to_json(indent=4))

        print("Transcript JSON file generated successfully.")

    except Exception as e:
        print(f"Exception: {e}")


if __name__ == "__main__":
    main()
```

如果上面的 cell 成功，你應該會在 content 目錄看到 JSON 輸出檔。注意：cell 執行完到 JSON 檔真的出現之間，可能會有小小的延遲，這是正常的，稍等一下檔案就會出現。

# 步驟 4：看看你的逐字稿

下面這個 function 會解析輸出的 JSON，並印出你剛轉錄的其中一個檔案的逐字稿！（確認你要看的檔案確實已經在 content 目錄裡。）

**把 `OUTPUT` 變數設成你想看逐字稿的檔名。**

然後執行這個 cell（`Shift`+`Enter`），就能看到你音檔的逐句逐字稿！

```python
import json

# Set this variable to the path of the output file you wish to read
OUTPUT = "transcript.json"


# The JSON is loaded with information, but if you just want to read the
# transcript, run the code below!
def print_transcript(transcription_file):
    with open(transcription_file) as file:
        data = json.load(file)
        result = data["results"]["channels"][0]["alternatives"][0]["transcript"]
        result = result.split(".")
        for sentence in result:
            print(sentence + ".")


print_transcript(OUTPUT)
```


如果上面的 cell 成功，你應該會看到音檔逐字稿的純文字版本。

# 步驟 5：用 Anthropic 準備面試問題

現在可以把逐字稿送給 Anthropic 分析，幫我們準備一些面試問題。執行下面的 cell（`Shift`+`Enter`），根據你上面的音檔逐字稿，拿到 Anthropic 提供的一組建議面試問題。

```python
import json

import anthropic

transcription_file = "transcript.json"


# Function to get the transcript from the JSON file
def get_transcript(transcription_file):
    with open(transcription_file) as file:
        data = json.load(file)
        result = data["results"]["channels"][0]["alternatives"][0]["transcript"]
        return result


# Load the transcript from the JSON file
message_text = get_transcript(transcription_file)

# Initialize the Claude API client
client = anthropic.Anthropic(
    # Defaults to os.environ.get("ANTHROPIC_API_KEY")
    # Claude API key
    api_key="🔑🔑🔑 Your API Key here! 🔑🔑🔑"
)

# Prepare the text for the API request
formatted_messages = [{"role": "user", "content": message_text}]

# Generate thoughtful, open-ended interview questions
response = client.messages.create(
    model="claude-opus-5-5",
    max_tokens=1000,
    system="Your task is to generate a series of thoughtful, open-ended questions for an interview based on the given context. The questions should be designed to elicit insightful and detailed responses from the interviewee, allowing them to showcase their knowledge, experience, and critical thinking skills. Avoid yes/no questions or those with obvious answers. Instead, focus on questions that encourage reflection, self-assessment, and the sharing of specific examples or anecdotes.",
    messages=formatted_messages,
)

# Print the generated questions

# Join the text of each TextBlock into a single string
content = "".join(block.text for block in response.content if block.type == "text")

# Split the content by '\n\n'
parts = content.split("\n\n")

# Print each part with an additional line break
for part in parts:
    print(part)
    print("\n")
```

如果這個 cell 成功，你應該會看到根據原始音檔產生的面試問題清單。現在你可以用 Deepgram 轉錄音檔，再用 Anthropic 取得一組面試問題了。

## 重點整理

- 這是一條簡單的 pipeline：語音轉文字（Deepgram）接上 LLM 分析（Claude）。
- 轉錄結果是 JSON，要先解析成純文字再交給 Claude。
- 把逐字稿當作 context，Claude 就能針對內容產生客製化的面試問題。
- 遇到轉錄錯誤，先檢查 SDK 版本和 Deepgram 剩餘 credit。

## 練習

1. 換一個你自己的音檔 URL 來轉錄，確認整條流程還能跑通。
2. 修改步驟 5 的 prompt，讓 Claude 產生 10 題難度由淺到深的問題。
3. 把步驟 5 改成請 Claude 做逐字稿摘要加待辦事項，並要求用 XML 標籤包住輸出再用程式解析。
