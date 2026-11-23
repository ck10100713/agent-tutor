---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/GPT_with_vision_for_video_understanding.ipynb
---

# 用 GPT-4.1-mini 的視覺能力和 GPT-4o TTS API 處理並旁白影片

> 原文：[examples/GPT_with_vision_for_video_understanding.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/GPT_with_vision_for_video_understanding.ipynb)



## 這篇在做什麼
這篇示範怎麼把 GPT 的視覺能力用在影片上。GPT-4.1-mini 不能直接吃影片當輸入，但我們可以用視覺能力加上 1M token 的 context window，一次描述整支影片的靜態畫格。
有兩個範例：

1. 用 GPT-4.1-mini 取得影片的描述
2. 用 GPT-4o TTS API 為影片產生旁白

## 學完你會
- 用 OpenCV 把影片切成畫格，並顯示出來確認讀取正確。
- 把畫格送給 GPT-4.1-mini，請它描述影片或寫出旁白腳本。
- 用 GPT-4o TTS 搭配語氣指示，把腳本轉成旁白音檔。

## 開跑前
- 需要 OpenAI API key，圖片輸入和 TTS 都會產生費用。
- 需要安裝 OpenCV，並準備一支影片檔（範例用的是一支[自然紀錄片段](https://www.youtube.com/watch?v=kQ_7GtE529M)）。


```python
from IPython.display import display, Image, Audio

import cv2  # We're using OpenCV to read video, to install !pip install opencv-python
import base64
import time
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

## 1. 用 GPT 的視覺能力取得影片描述


首先用 OpenCV 從一支有野牛和狼的自然[影片](https://www.youtube.com/watch?v=kQ_7GtE529M)中擷取畫格：


```python
video = cv2.VideoCapture("data/bison.mp4")

base64Frames = []
while video.isOpened():
    success, frame = video.read()
    if not success:
        break
    _, buffer = cv2.imencode(".jpg", frame)
    base64Frames.append(base64.b64encode(buffer).decode("utf-8"))

video.release()
print(len(base64Frames), "frames read.")
```

??? note "輸出"

    ```text
    618 frames read.
    ```

顯示畫格，確認有正確讀進來：


```python
display_handle = display(None, display_id=True)
for img in base64Frames:
    display_handle.update(Image(data=base64.b64decode(img.encode("utf-8"))))
    time.sleep(0.025)
```

拿到影片畫格後，寫好 prompt 並送出請求給 GPT（注意，不必送出每一個畫格，GPT 也能理解發生什麼事）：


```python
response = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "These are frames from a video that I want to upload. Generate a compelling description that I can upload along with the video."
                    )
                },
                *[
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{frame}"
                    }
                    for frame in base64Frames[0::25]
                ]
            ]
        }
    ],
)

print(response.output_text)
```

??? note "輸出"

    ```text
    Witness the raw power and strategy of nature in this intense wildlife encounter captured in stunning detail. A determined pack of wolves surrounds a lone bison on a snowy plain, showcasing the relentless dynamics of predator and prey in the wild. As the wolves close in, the bison stands its ground amidst the swirling snow, illustrating a gripping battle for survival. This rare footage offers an up-close look at the resilience and instincts that govern life in the animal kingdom, making it a must-watch for nature enthusiasts and wildlife lovers alike. Experience the drama, tension, and beauty of this extraordinary moment frozen in time.
    ```

## 2. 用 GPT-4.1 和 GPT-4o TTS API 為影片產生旁白


我們來為這支影片做一段 David Attenborough 風格的旁白。用同一批影片畫格，請 GPT 給我們一份簡短腳本：


```python
result = client.responses.create(
    model="gpt-4.1-mini",
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "These are frames of a video. Create a short voiceover script in the style of David Attenborough. Only include the narration."
                    )
                },
                *[
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{frame}"
                    }
                    for frame in base64Frames[0::25]
                ]
            ]
        }
    ]
)

print(result.output_text)
```

??? note "輸出"

    ```text
    In the frozen expanse of the winter landscape, a coordinated pack of wolves moves with calculated precision. Their target, a lone bison, is powerful but vulnerable when isolated. The wolves encircle their prey, their numbers overwhelming, displaying the brutal reality of survival in the wild. As the bison struggles to break free, reinforcements from the herd arrive just in time, charging into the pack. A dramatic clash unfolds, where strength meets strategy in the perpetual battle for life. Here, in the heart of nature’s harshest conditions, every moment is a testament to endurance and the delicate balance of predator and prey.
    ```

接下來用 GPT-4o TTS 模型，提供一組指示說明聲音該是什麼樣子。你可以到 [OpenAI.fm](https://openai.fm) 試玩各種聲音模型和指示。然後把上面用 GPT-4.1-mini 產生的腳本丟進去，產生旁白音訊：


```python
instructions = """
Voice Affect: Calm, measured, and warmly engaging; convey awe and quiet reverence for the natural world.

Tone: Inquisitive and insightful, with a gentle sense of wonder and deep respect for the subject matter.

Pacing: Even and steady, with slight lifts in rhythm when introducing a new species or unexpected behavior; natural pauses to allow the viewer to absorb visuals.

Emotion: Subtly emotive—imbued with curiosity, empathy, and admiration without becoming sentimental or overly dramatic.

Emphasis: Highlight scientific and descriptive language (“delicate wings shimmer in the sunlight,” “a symphony of unseen life,” “ancient rituals played out beneath the canopy”) to enrich imagery and understanding.

Pronunciation: Clear and articulate, with precise enunciation and slightly rounded vowels to ensure accessibility and authority.

Pauses: Insert thoughtful pauses before introducing key facts or transitions (“And then... with a sudden rustle...”), allowing space for anticipation and reflection.
"""

audio_response = response = client.audio.speech.create(
  model="gpt-4o-mini-tts",
  voice="echo",
  instructions=instructions,
  input=result.output_text,
  response_format="wav"
)

audio_bytes = audio_response.content
Audio(data=audio_bytes)
```

## 重點整理
- 模型不吃影片時，把影片抽成畫格再當圖片輸入，是常見的替代做法。
- 不用送出每一格，抽樣的畫格就足以讓模型理解內容，還能省 token。
- 同一批畫格可以用不同 prompt 產生不同產出，例如描述或旁白腳本。
- TTS 模型可以用文字指示控制語氣和風格，腳本內容和聲音風格是分開調整的。

## 練習
1. 調整畫格的抽樣間隔，看描述品質和 token 用量怎麼變。
2. 把旁白的風格從 David Attenborough 換成別的（例如運動賽事轉播），重新產生腳本。
3. 改 TTS 的指示和聲音，產生兩個版本的旁白，比較聽起來的差異。
