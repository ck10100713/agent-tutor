---
translated: true
source: examples/voice_solutions/steering_tts.ipynb
---

# 引導 Text-to-Speech，產生更生動的音訊

> 原文：[examples/voice_solutions/steering_tts.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/voice_solutions/steering_tts.ipynb)



## 這篇在做什麼

傳統 TTS API 只能選聲音，沒辦法指定語氣或口音。這篇示範用 audio chat completions，在產生音訊前先給指示，讓你控制語速、語調和口音，聲音會更自然、更符合情境。

## 學完你會

- 分辨傳統 TTS 和 chat completions TTS 能做的事有什麼不同
- 用 prompt 指示產生英式口音、適合兒童學習的音訊
- 產生特定的西班牙語（烏拉圭）口音的音訊

## 開跑前

- OpenAI API key，並且帳號能使用 audio chat completions

## 引導 Text-to-Speech，產生更生動的音訊

我們傳統的 [TTS API](https://platform.openai.com/docs/guides/text-to-speech) 沒辦法引導生成音訊的聲音。例如你想把一段文字轉成音訊，就沒辦法對音訊生成給任何具體指示。

用 [audio chat completions](https://platform.openai.com/docs/guides/audio/quickstart)，你可以在生成音訊之前給具體的指示。這讓你能要求 API 用不同的速度、語氣和口音說話。有了適當的指示，這些聲音會更生動、自然，也更符合情境。

### 傳統 TTS

傳統 TTS 可以指定聲音，但不能指定語氣、口音或任何其他跟情境有關的音訊參數。

```python
from openai import OpenAI
client = OpenAI()

tts_text = """
Once upon a time, Leo the lion cub woke up to the smell of pancakes and scrambled eggs.
His tummy rumbled with excitement as he raced to the kitchen. Mama Lion had made a breakfast feast!
Leo gobbled up his pancakes, sipped his orange juice, and munched on some juicy berries.
"""

speech_file_path = "./sounds/default_tts.mp3"
response = client.audio.speech.create(
    model="tts-1-hd",
    voice="alloy",
    input=tts_text,
)

response.write_to_file(speech_file_path)
```

### Chat Completions TTS

用 chat completions 可以在生成音訊前給具體指示。下面的範例中，我們在兒童學習的情境下產生英式口音。對教育類應用特別有用，因為 assistant 的聲音對學習體驗很重要。

```python
import base64

speech_file_path = "./sounds/chat_completions_tts.mp3"
completion = client.chat.completions.create(
    model="gpt-4o-audio-preview",
    modalities=["text", "audio"],
    audio={"voice": "alloy", "format": "mp3"},
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant that can generate audio from text. Speak in a British accent and enunciate like you're talking to a child.",
        },
        {
            "role": "user",
            "content": tts_text,
        }
    ],
)

mp3_bytes = base64.b64decode(completion.choices[0].message.audio.data)
with open(speech_file_path, "wb") as f:
    f.write(mp3_bytes)

speech_file_path = "./sounds/chat_completions_tts_fast.mp3"
completion = client.chat.completions.create(
    model="gpt-4o-audio-preview",
    modalities=["text", "audio"],
    audio={"voice": "alloy", "format": "mp3"},
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant that can generate audio from text. Speak in a British accent and speak really fast.",
        },
        {
            "role": "user",
            "content": tts_text,
        }
    ],
)

mp3_bytes = base64.b64decode(completion.choices[0].message.audio.data)
with open(speech_file_path, "wb") as f:
    f.write(mp3_bytes)
```

### Chat Completions 多語言 TTS

我們也可以產生不同語言口音的音訊。下面的範例會產生特定的烏拉圭西班牙語口音。

```python
completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {
            "role": "system",
            "content": "You are an expert translator. Translate any text given into Spanish like you are from Uruguay.",
        },
        {
            "role": "user",
            "content": tts_text,
        }
    ],
)
translated_text = completion.choices[0].message.content
print(translated_text)

speech_file_path = "./sounds/chat_completions_tts_es_uy.mp3"
completion = client.chat.completions.create(
    model="gpt-4o-audio-preview",
    modalities=["text", "audio"],
    audio={"voice": "alloy", "format": "mp3"},
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant that can generate audio from text. Speak any text that you receive in a Uruguayan spanish accent and more slowly.",
        },
        {
            "role": "user",
            "content": translated_text,
        }
    ],
)

mp3_bytes = base64.b64decode(completion.choices[0].message.audio.data)
with open(speech_file_path, "wb") as f:
    f.write(mp3_bytes)
```

??? note "輸出"

    ```text
    Había una vez un leoncito llamado Leo que se despertó con el aroma de panqueques y huevos revueltos. Su pancita gruñía de emoción mientras corría hacia la cocina. ¡Mamá León había preparado un festín de desayuno! Leo devoró sus panqueques, sorbió su jugo de naranja y mordisqueó algunas bayas jugosas.
    ```

## 結論

能引導生成音訊的聲音，開啟了更豐富音訊體驗的許多可能。有很多使用情境，例如：
- **更強的表現力**：可引導的 TTS 能調整語氣、音高、速度和情緒，讓聲音傳達不同的心情（例如興奮、平靜、急迫）。
- **語言學習與教育**：可引導的 TTS 能模仿口音、語調和發音，對語言學習者和需要精準語調與重音的教育應用很有幫助。
- **情境化聲音**：可引導的 TTS 會讓聲音配合內容的情境，例如專業文件用正式語氣，社交互動用友善的對話風格。這有助於在虛擬助理和聊天機器人裡創造更自然的對話。


## 重點整理

- 傳統 TTS 只能選聲音，audio chat completions 可以用指示控制語氣、速度和口音。
- 控制手段是自然語言的指示，跟寫 prompt 一樣。
- 指示要配合使用情境，例如兒童教學和專業文件需要的語氣完全不同。
- 口音和語言也能靠指示切換，不需要換模型。

## 練習

1. 改兒童學習範例裡的指示，換成更慢、更興奮的語氣，聽聽差別。
2. 把要念的文字換成你自己的一段話，並指定不同的口音。
3. 同一段文字分別用傳統 TTS 和 chat completions TTS 產生，比較兩者在語氣上的差別。
