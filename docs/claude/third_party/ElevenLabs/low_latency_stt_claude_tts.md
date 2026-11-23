---
translated: true
source: third_party/ElevenLabs/low_latency_stt_claude_tts.ipynb
---

# 用 ElevenLabs 做低延遲語音助理

> 原文：[third_party/ElevenLabs/low_latency_stt_claude_tts.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/ElevenLabs/low_latency_stt_claude_tts.ipynb)

用 ElevenLabs 做語音轉文字和文字轉語音，搭配 Claude 建立低延遲語音助理。

## 這篇在做什麼

用 ElevenLabs 負責語音轉文字（STT）和文字轉語音（TTS），Claude 負責產生回答，串成一個語音助理。重點是逐步量測 streaming 對延遲的改善，從普通呼叫一路優化到 WebSocket 串流。

## 學完你會

- 用 ElevenLabs 做 TTS 和 STT，並量測各步驟延遲。
- 用 Claude streaming API 縮短第一個 token 的等待時間。
- 把 Claude 的串流輸出接到 ElevenLabs WebSocket TTS，兼顧低延遲和自然語調。

## 開跑前

需要兩組 API key：ElevenLabs 和 Anthropic。ElevenLabs 的 TTS、STT 用量可能計費。

這份 notebook 示範如何用 ElevenLabs 做語音轉文字和文字轉語音，搭配 Claude 給出智慧回應，建立低延遲的語音助理。我們會量測 streaming 回應帶來的效能提升。

這份 notebook 會示範：

1. 用 ElevenLabs TTS 把文字轉成語音
2. 用 ElevenLabs speech-to-text 轉錄音訊
3. 用 Claude 產生回應
4. 用 Claude 的 streaming API 優化延遲

---

## 安裝

先安裝需要的相依套件：

```python
%pip install --upgrade pip
```

```python
%pip install -r requirements.txt
```

## Imports

匯入 ElevenLabs 整合、Claude API 存取和音訊播放需要的函式庫：

```python
import io
import os
import time

import anthropic
import elevenlabs
from dotenv import load_dotenv
from IPython.display import Audio
```

## API Keys

設定 ElevenLabs 和 Anthropic 的 API key。

**設定步驟：**

1. 把 `.env.example` 複製成這個目錄下的 `.env`
2. 編輯 `.env`，填入你真正的 API key：
   - 取得 ElevenLabs API key：https://elevenlabs.io/app/developers/api-keys
   - 取得 Anthropic API key：https://console.anthropic.com/settings/keys

key 會自動從 `.env` 檔載入。

```python
# Load environment variables from .env file

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
```

## 初始化 Clients

建立 ElevenLabs 和 Anthropic 兩個服務的 client：

```python
assert ELEVENLABS_API_KEY is not None, (
    "ERROR: ELEVENLABS_API_KEY not found. Please copy .env.example to .env and add your API keys."
)
assert ANTHROPIC_API_KEY is not None, (
    "ERROR: ANTHROPIC_API_KEY not found. Please copy .env.example to .env and add your API keys."
)

elevenlabs_client = elevenlabs.ElevenLabs(
    api_key=ELEVENLABS_API_KEY, base_url="https://api.elevenlabs.io"
)

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
```

## 列出可用的模型和聲音

看看 ElevenLabs 有哪些可用的模型和聲音。我們會自動選第一個可用的聲音，當作助理回應的聲音：

```python
print("Available Models and Voices:\n")
for model in elevenlabs_client.models.list():
    print(f"{model.name}: {model.model_id}")

print()

voices = elevenlabs_client.voices.search().voices
for voice in voices:
    print(f"{voice.name}: {voice.voice_id}")

# Select the first voice for assistant responses
selected_voice = voices[0]
VOICE_ID = selected_voice.voice_id

print(f"\nSelected voice: {selected_voice.name} with ID: {VOICE_ID}")
```

??? note "輸出"

    ```text
    Available Models and Voices:

    Eleven v3 (alpha): eleven_v3
    Eleven Multilingual v2: eleven_multilingual_v2
    Eleven Flash v2.5: eleven_flash_v2_5
    Eleven Turbo v2.5: eleven_turbo_v2_5
    Eleven Turbo v2: eleven_turbo_v2
    Eleven Flash v2: eleven_flash_v2
    Eleven Multilingual v1: eleven_multilingual_v1
    Eleven English v1: eleven_monolingual_v1
    Eleven English v2: eleven_english_sts_v2
    Eleven Multilingual v2: eleven_multilingual_sts_v2

    Rachel: 21m00Tcm4TlvDq8ikWAM
    Drew: 29vD33N1CtxCmqQRPOHJ
    Clyde: 2EiwWnXFnvU5JabPnv8n
    Paul: 5Q0t7uMcjvnagumLfvZi
    Aria: 9BWtsMINqrJLrRacOk9x
    Domi: AZnzlk1XvdvUeBnXmlld
    Dave: CYw3kZ02Hs0563khs1Fj
    Roger: CwhRBWXzGAHq8TQ4Fs17
    Fin: D38z5RcWu1voky8WS1ja
    Sarah: EXAVITQu4vr4xnSDxMaL

    Selected voice: Rachel with ID: 21m00Tcm4TlvDq8ikWAM
    ```

## 產生輸入音訊

用 ElevenLabs 的 TTS 做一個範例音檔，模擬使用者對語音助理的輸入：

```python
audio = elevenlabs_client.text_to_speech.convert(
    voice_id=VOICE_ID,  # Use the dynamically selected voice
    output_format="mp3_44100_128",
    model_id="eleven_v3",
    text="Hello, Claude. ",
)

audio_data = io.BytesIO()
for chunk in audio:
    audio_data.write(chunk)

Audio(audio_data.getvalue())
```

??? note "輸出"

    ```text
    <IPython.lib.display.Audio object>
    ```

## 語音轉錄

用 ElevenLabs 的 speech-to-text 模型轉錄輸入的音訊，並量測轉錄延遲：

```python
audio_data.seek(0)

start_time = time.time()

transcription = elevenlabs_client.speech_to_text.convert(file=audio_data, model_id="scribe_v1")

end_time = time.time()
transcription_time = end_time - start_time

print(f"Transcribed text: {transcription.text}")
print(f"Transcription time: {transcription_time:.2f} seconds")
```

??? note "輸出"

    ```text
    Transcribed text: Hello, Claude.
    Transcription time: 0.54 seconds
    ```

## 取得 Claude 的回應

把轉錄出的文字送給 Claude，量測回應時間。這裡用 `claude-haiku-5-5` 搭配 `effort: "low"`，回應又快品質又好：

```python
start_time = time.time()

message = anthropic_client.messages.create(
    model="claude-haiku-5-5",
    max_tokens=1000,
    output_config={"effort": "low"},
    messages=[{"role": "user", "content": transcription.text}],
)

end_time = time.time()
non_streaming_response_time = end_time - start_time

print("".join(b.text for b in message.content if b.type == "text"))
print(f"\nResponse time: {non_streaming_response_time:.2f} seconds")
```

??? note "輸出"

    ```text
    Hello! It's nice to meet you. How can I help you today?

    Response time: 1.03 seconds
    ```

## 用 Streaming 優化

用 Claude 的 streaming API 改善回應延遲。這樣能更快收到最初的 token，大幅降低使用者感受到的延遲：

```python
start_time = time.time()
first_token_time = None

claude_full_response = ""

with anthropic_client.messages.stream(
    model="claude-haiku-5-5",
    max_tokens=1000,
    output_config={"effort": "low"},
    messages=[{"role": "user", "content": transcription.text}],
) as stream:
    for text in stream.text_stream:
        claude_full_response += text
        print(text, end="", flush=True)
        if first_token_time is None:
            first_token_time = time.time()

streaming_time_to_first_token = first_token_time - start_time
print(
    f"\n\nStreaming time to first token: {streaming_time_to_first_token:.2f} seconds - reducing perceived latency by {(non_streaming_response_time - streaming_time_to_first_token) * 100 / non_streaming_response_time:.2f}%"
)
```

??? note "輸出"

    ```text
    Hello! It's nice to meet you. How can I help you today?

    Streaming time to first token: 0.71 seconds - reducing perceived latency by 30.71%
    ```

文字轉語音也一樣，可以串流回應來減少沉默的時間。

```python
start_time = time.time()
first_audio_chunk_time = None

audio_buffer = io.BytesIO()

audio_generator = elevenlabs_client.text_to_speech.stream(
    voice_id=VOICE_ID,
    output_format="mp3_44100_128",
    text=claude_full_response,
    model_id="eleven_turbo_v2_5",
)

for chunk in audio_generator:
    if first_audio_chunk_time is None:
        first_audio_chunk_time = time.time()
    audio_buffer.write(chunk)

streaming_tts_time_to_first_chunk = first_audio_chunk_time - start_time
print(f"Streaming TTS time to first audio chunk: {streaming_tts_time_to_first_chunk:.2f} seconds")

Audio(audio_buffer.getvalue())
```

??? note "輸出"

    ```text
    Streaming TTS time to first audio chunk: 0.39 seconds
    ```

## 把 Claude 直接串流到 TTS（逐句）

Claude 的 streaming 和 TTS 我們已經分別優化過，能不能合在一起？我們串流 Claude 的回應，一收到完整句子就立刻合成音訊。

這個做法用標點（`.`、`!`、`?`）偵測句子邊界，每個句子一偵測到就送去 TTS，進一步降低延遲。

```python
import re

sentence_pattern = re.compile(r"[.!?]+")
sentence_buffer = ""
audio_chunks = []

start_time = time.time()
first_audio_time = None

with anthropic_client.messages.stream(
    model="claude-haiku-5-5",
    max_tokens=1000,
    output_config={"effort": "low"},
    messages=[{"role": "user", "content": transcription.text}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
        sentence_buffer += text

        if sentence_pattern.search(sentence_buffer):
            sentences = sentence_pattern.split(sentence_buffer)

            # Process all complete sentences (all but the last element)
            for i in range(len(sentences) - 1):
                complete_sentence = sentences[i].strip()
                if complete_sentence:
                    audio_gen = elevenlabs_client.text_to_speech.stream(
                        voice_id=VOICE_ID,
                        output_format="mp3_44100_128",  # Free tier format
                        text=complete_sentence,
                        model_id="eleven_turbo_v2_5",
                    )

                    sentence_audio = io.BytesIO()
                    for chunk in audio_gen:
                        if first_audio_time is None:
                            first_audio_time = time.time()
                        sentence_audio.write(chunk)

                    audio_chunks.append(sentence_audio.getvalue())

            sentence_buffer = sentences[-1]

if sentence_buffer.strip():
    audio_gen = elevenlabs_client.text_to_speech.stream(
        voice_id=VOICE_ID,
        output_format="mp3_44100_128",
        text=sentence_buffer.strip(),
        model_id="eleven_turbo_v2_5",
    )
    sentence_audio = io.BytesIO()
    for chunk in audio_gen:
        sentence_audio.write(chunk)
    audio_chunks.append(sentence_audio.getvalue())

sentence_streaming_time_to_first_audio = first_audio_time - start_time
print(f"\n\nTime to first audio: {sentence_streaming_time_to_first_audio:.2f} seconds")

combined_pcm = b"".join(audio_chunks)
Audio(combined_pcm)
```

??? note "輸出"

    ```text
    Hello! It's nice to meet you. How can I help you today?

    Time to first audio: 1.48 seconds
    ```

### 問題：音訊聽起來斷斷續續

這個做法的延遲很漂亮，但音質有問題。每個句子是獨立合成的，聽起來不連貫、不自然。句子之間的語調（節奏、重音、抑揚）沒辦法順暢銜接。

原因是 TTS 模型不知道後面會接什麼，所以每個句子都被當成獨立的一句話處理。

## WebSocket Streaming：兩全其美

ElevenLabs 提供 WebSocket API 來解決這個問題。我們不必等完整句子，Claude 一產生文字 chunk，就能直接串流給 TTS 引擎。

WebSocket API：
- 接受串流文字輸入（不需要自己緩衝句子）
- 跨 chunk 維持上下文，語調自然
- 音訊 chunk 一準備好就回傳
- 以最好的音質達到最低的延遲

來實作這個終極優化：

## 建立 Production 等級的語音助理

這份 notebook 示範的技巧是即時語音助理的基礎。WebSocket streaming 能把延遲降到最低，同時保持自然的音質。

### 主要的實作挑戰

做 production 系統時，除了基本的 streaming，還要解決幾個額外的問題：

1. **連續音訊播放：** 音訊 chunk 必須無縫播放，不能有空隙或爆音，需要仔細管理 buffer 並預先緩衝。

2. **麥克風輸入：** 即時從麥克風錄音，並正確處理音訊格式和取樣率。

3. **對話狀態：** 跨輪次保存對話歷史，讓 Claude 能參考前面的內容。

4. **音質：** 在不同音訊格式（PCM、WAV）之間轉換，避免編碼造成雜訊。

### 完整實作

我們寫了一支完整的語音助理腳本，涵蓋上面所有技巧：

**`stream_voice_assistant_websocket.py`**：一支可上線等級的對話式語音助理，功能有：
- 麥克風錄音，按 Enter 停止
- ElevenLabs 語音轉文字
- Claude streaming 並保留對話歷史
- 以 WebSocket 做 TTS，延遲最小
- 自訂音訊 queue，確保播放不間斷
- 連續的對話迴圈

執行這支腳本，體驗功能完整的語音助理：

```bash
python stream_voice_assistant_websocket.py
```

這展示了這份 notebook 的 streaming 優化如何落實成真實應用，並做到 production 品質的音訊處理。

## 重點整理
- 語音助理的延遲來自 STT、LLM、TTS 三段，每段都能用 streaming 縮短。
- Claude streaming 讓你不用等完整回答，第一批 token 到了就能往下游送。
- 逐句送 TTS 延遲低，但每句獨立合成，語調會斷。
- ElevenLabs WebSocket TTS 能邊收文字邊保持上下文，是延遲和音質的最佳平衡。
- 上線還要處理連續播放、麥克風輸入、對話歷史和音訊格式。

## 練習
1. 換一個聲音或換一段輸入文字，重新量測 STT 和 Claude 的延遲。
2. 把 Claude 呼叫的 `effort` 從 `"low"` 改成別的值，比較延遲和回答品質。
3. 修改逐句串流的斷句規則（例如加入逗號），聽聽看延遲和連貫度的變化。
