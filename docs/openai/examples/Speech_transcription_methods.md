---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Speech_transcription_methods.ipynb
---
# 用 OpenAI API 比較各種語音轉文字方法

> 原文：[examples/Speech_transcription_methods.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Speech_transcription_methods.ipynb)

比較各種語音轉文字（speech-to-text）方法，幫你挑出適合的做法。

## 這篇在做什麼

用 OpenAI API 實際跑四種語音轉文字的做法：整檔上傳、整檔上傳加串流、Realtime WebSocket、Agents SDK 的 VoicePipeline。每種都講適用情境、優缺點，並附可執行的程式。

## 學完你會

- 用 `gpt-4o-transcribe` 轉錄一個音檔，並用 `stream=True` 讓結果邊產生邊顯示
- 透過 WebSocket 連 Realtime API，送 pcm16 音訊並接收即時逐字稿
- 用 Agents SDK 的 `VoicePipeline` 做即時轉錄，並依延遲、格式限制、實作難度選對方法

## 開跑前

- 需要 OpenAI API key，設成環境變數 `OPENAI_API_KEY`
- 需要安裝相關套件（見下方安裝步驟），並準備 WAV 音檔

## 概覽

這份 notebook 帶你快速上手用 OpenAI API 做語音轉文字（STT）。你會看到幾種實用的方法、各自的使用情境和注意事項。

讀完後，你可以依自己的情境選出合適的轉錄方法。

*注意：*
- *為了簡單，這裡用 WAV 音檔，**沒有**示範即時麥克風串流（例如從網頁應用程式或直接接麥克風）。*
- *這裡用 WebSocket 連 Realtime API。你也可以用 WebRTC，細節看 [OpenAI docs](https://platform.openai.com/docs/guides/realtime#connect-with-webrtc)。*

### 📊 快速對照
| Mode                           | Latency to **first token** | Best for (real examples)                                     | Advantages | Key limitations                |
|--------------------------------|---------------------------|--------------------------------------------------------------|-----------------------------------------------------------|-----------------------------------------------------------|
| File upload + `stream=False` (blocking) | seconds  | Voicemail, meeting recordings | Simple to set up | • No partial results, users see nothing until file finishes <br>• Max 25 MB per request (you must chunk long audio) |
| File upload + `stream=True`    | subseconds | Voice memos in mobile apps | Simple to set up & provides a “live” feel via token streaming | • Still requires a completed file <br>• You implement progress bars / chunked uploads |
| Realtime WebSocket             | subseconds | Live captions in webinars | True real-time; accepts a continuous audio stream | • Audio must be pcm16, g711_ulaw, or g711_alaw <br>• Session ≤ 30 min, reconnect & stitch <br>• You handle speaker-turn formatting to build the full transcript |
| Agents SDK VoicePipeline       | subseconds | Internal help-desk assistant | Real-time streaming and easy to build agentic workflows | • Python-only beta <br>• API surface may change |

## 安裝（只要做一次）

在新的 Python 環境裡，取消註解並執行下面這個 cell：

```python
!pip install --upgrade -q openai openai-agents websockets sounddevice pyaudio nest_asyncio resampy httpx websocket-client
```

這會裝好跟著做需要的套件。

## 驗證

開始前，先確認你已經把 OpenAI API key 設成名為 OPENAI_API_KEY 的環境變數。通常在終端機或 notebook 環境設定：`export OPENAI_API_KEY="your-api-key-here"`

跑下一個 cell 確認 API key 有設好。

```python
# ─── Standard Library ──────────────────────────────────────────────────────────
import asyncio
import struct
import base64          # encode raw PCM bytes → base64 before sending JSON
import json            # compose/parse WebSocket messages
import os
import time
from typing import List
from pathlib import Path

# ─── Third-Party ───────────────────────────────────────────────────────────────
import nest_asyncio
import numpy as np
from openai import OpenAI
import resampy         # high-quality sample-rate conversion
import soundfile as sf # reads many audio formats into float32 arrays
import websockets      # asyncio-based WebSocket client
from agents import Agent
from agents.voice import (
    SingleAgentVoiceWorkflow,
    StreamedAudioInput,
    VoicePipeline,
    VoicePipelineConfig,
)
from IPython.display import Audio, display
# ───────────────────────────────────────────────────────────────────────────────
nest_asyncio.apply()

# ✏️  Put your key in an env-var or just replace the call below.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)
print("✅ OpenAI client ready")
```

??? note "輸出"

    ```text
    ✅ OpenAI client ready
    ```

---
## 1 · 用音檔做語音轉文字
*model = gpt-4o-transcribe*

### 什麼時候用
* 你手上有完整的音檔（最大 25 MB）。支援的輸入格式有 mp3、mp4、mpeg、mpga、m4a、wav、webm。
* 適合批次處理，例如 podcast、客服錄音、語音備忘錄。
* 不需要即時回饋或部分結果。

### 運作方式


![STT Not Streaming Transcription flow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/speech-to-text-not-streaming.png)

#### 優點

- **好上手：** 一個 HTTP request 就好，很適合自動化或後端腳本。  
- **準確：** 一次處理整段音訊，上下文完整，轉錄品質比較好。  
- **支援多種檔案：** 能處理 WAV、MP3、MP4、M4A、FLAC、Ogg 等。  

#### 限制

- **沒有部分結果：** 要等處理完才看得到逐字稿。  
- **延遲隨長度增加：** 錄音越長，等越久。  
- **檔案大小上限：** 最大 25 MB（約 30 分鐘的 16 kHz 單聲道 WAV）。  
- **只適合離線：** 不適合即時字幕或對話式 AI 這類即時情境。  

先預覽一下音檔。這個音檔是我從[這裡](https://pixabay.com/sound-effects/search/male-speech/)下載的。

```python
AUDIO_PATH = Path('./data/sample_audio_files/lotsoftimes-78085.mp3')  # change me
MODEL_NAME = "gpt-4o-transcribe"

if AUDIO_PATH.exists():
    display(Audio(str(AUDIO_PATH)))
else:
    print('⚠️ Provide a valid audio file')
```

接著呼叫 STT endpoint 來轉錄音訊。

```python
if AUDIO_PATH.exists():
    with AUDIO_PATH.open('rb') as f:
        transcript = client.audio.transcriptions.create(
            file=f,
            model=MODEL_NAME,
            response_format='text',
        )
    print('\n--- TRANSCRIPT ---\n')
    print(transcript)
```

??? note "輸出"

    ```text

    --- TRANSCRIPT ---

    And lots of times you need to give people more than one link at a time. A band could give their fans a couple new videos from a live concert, a behind-the-scenes photo gallery, an album to purchase, like these next few links.
    ```

## 2 · 用音檔做語音轉文字：串流
*model = gpt-4o-transcribe*
### 什麼時候用
- 你已經有完整錄好的音檔。  
- 你想在結果（部分或最終）一產生就立刻拿到。  
- 部分回饋能改善體驗的情境，例如上傳很長的語音備忘錄。

![STT Streaming Transcription flow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/speech-to-text-streaming.png)

#### 優點
- **有即時感：** 使用者幾乎馬上就看到轉錄更新。  
- **看得到進度：** 中間的逐字稿顯示目前進度。  
- **體驗更好：** 即時回饋讓使用者不會等到無聊。  

#### 限制
- **要先有完整音檔：** 不適合即時的音訊來源。  
- **實作成本：** 串流邏輯和進度更新要自己處理。  

```python
if AUDIO_PATH.exists():
    with AUDIO_PATH.open('rb') as f:
        stream = client.audio.transcriptions.create(
            file=f,
            model=MODEL_NAME,
            response_format='text',
              stream=True
)

for event in stream:
    # If this is an incremental update, you can get the delta using `event.delta`
    if getattr(event, "delta", None): 
        print(event.delta, end="", flush=True)
        time.sleep(0.05) # simulate real-time pacing
        
    # When transcription is complete, you can get the final transcript using `event.text`
    elif getattr(event, "text", None):
        print()
        print("\n" + event.text)
```

??? note "輸出"

    ```text
    And lots of times you need to give people more than one link at a time. A band could give their fans a couple new videos from a live concert, a behind-the-scenes photo gallery, an album to purchase, like these next few links.

    And lots of times you need to give people more than one link at a time. A band could give their fans a couple new videos from a live concert, a behind-the-scenes photo gallery, an album to purchase, like these next few links.
    ```

---
## 3 · Realtime Transcription API
*model = gpt-4o-transcribe*
### 什麼時候用
* 需要即時字幕的情境（例如會議、demo）。
* 需要內建的語音活動偵測（VAD）、降噪，或 token 層級的 log probability。
* 你能處理 WebSocket 和即時事件串流。


### 運作方式

![Realtime Transcription flow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/realtime_api_transcription.png)

#### 優點
- **超低延遲：** 通常 300 到 800 ms，幾乎即時轉錄。  
- **動態更新：** 支援部分與最終逐字稿，體驗更好。  
- **進階功能：** 內建 turn detection、降噪，還可以選擇回傳詳細的 log probability。  

#### 限制
- **整合複雜：** 要管理 WebSocket、Base64 編碼，並做好錯誤處理。  
- **session 限制：** 每個 session 最長 30 分鐘。  
- **格式受限：** 只接受原始 PCM（不能用 MP3 或 Opus）。pcm16 的輸入必須是 16-bit PCM、24kHz 取樣率、單聲道、little-endian。

```python
TARGET_SR     = 24_000
PCM_SCALE     = 32_767
CHUNK_SAMPLES = 3_072                 # ≈128 ms at 24 kHz
RT_URL        = "wss://api.openai.com/v1/realtime?intent=transcription"

EV_DELTA      = "conversation.item.input_audio_transcription.delta"
EV_DONE       = "conversation.item.input_audio_transcription.completed"
# ── helpers ────────────────────────────────────────────────────────────────
def float_to_16bit_pcm(float32_array):
    clipped = [max(-1.0, min(1.0, x)) for x in float32_array]
    pcm16 = b''.join(struct.pack('<h', int(x * 32767)) for x in clipped)
    return pcm16

def base64_encode_audio(float32_array):
    pcm_bytes = float_to_16bit_pcm(float32_array)
    encoded = base64.b64encode(pcm_bytes).decode('ascii')
    return encoded

def load_and_resample(path: str, sr: int = TARGET_SR) -> np.ndarray:
    """Return mono PCM-16 as a NumPy array."""
    data, file_sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if file_sr != sr:
        data = resampy.resample(data, file_sr, sr)
    return data

async def _send_audio(ws, pcm: np.ndarray, chunk: int, sr: int) -> None:
    """Producer: stream base-64 chunks at real-time pace, then signal EOF."""
    dur = 0.025 # Add pacing to ensure real-time transcription
    t_next = time.monotonic()

    for i in range(0, len(pcm), chunk):
        float_chunk = pcm[i:i + chunk]
        payload = {
            "type":  "input_audio_buffer.append",
            "audio": base64_encode_audio(float_chunk),
        }
        await ws.send(json.dumps(payload))
        t_next += dur
        await asyncio.sleep(max(0, t_next - time.monotonic()))

    await ws.send(json.dumps({"type": "input_audio_buffer.end"}))

async def _recv_transcripts(ws, collected: List[str]) -> None:
    """
    Consumer: build `current` from streaming deltas, promote it to `collected`
    whenever a …completed event arrives, and flush the remainder on socket
    close so no words are lost.
    """
    current: List[str] = []

    try:
        async for msg in ws:
            ev = json.loads(msg)

            typ = ev.get("type")
            if typ == EV_DELTA:
                delta = ev.get("delta")
                if delta:
                    current.append(delta)
                    print(delta, end="", flush=True)
            elif typ == EV_DONE:
                # sentence finished → move to permanent list
                collected.append("".join(current))
                current.clear()
    except websockets.ConnectionClosedOK:
        pass

    # socket closed → flush any remaining partial sentence
    if current:
        collected.append("".join(current))

def _session(model: str, vad: float = 0.5) -> dict:
    return {
        "type": "transcription_session.update",
        "session": {
            "input_audio_format": "pcm16",
            "turn_detection": {"type": "server_vad", "threshold": vad},
            "input_audio_transcription": {"model": model},
        },
    }

async def transcribe_audio_async(
    wav_path,
    api_key,
    *,
    model: str = MODEL_NAME,
    chunk: int = CHUNK_SAMPLES,
) -> str:
    pcm = load_and_resample(wav_path)
    headers = {"Authorization": f"Bearer {api_key}", "OpenAI-Beta": "realtime=v1"}

    async with websockets.connect(RT_URL, additional_headers=headers, max_size=None) as ws:
        await ws.send(json.dumps(_session(model)))

        transcripts: List[str] = []
        await asyncio.gather(
            _send_audio(ws, pcm, chunk, TARGET_SR),
            _recv_transcripts(ws, transcripts),
        )  # returns when server closes

    return " ".join(transcripts)
```

```python
transcript = await transcribe_audio_async(AUDIO_PATH, OPENAI_API_KEY)
transcript
```

??? note "輸出"

    ```text
    And lots of times you need to give people more than one link at a time.A band could give their fans a couple new videos from a live concert, a behind-the-scenes photo galleryLike these next few linksAn album to purchase.
    ```

    ```text
    'And lots of times you need to give people more than one link at a time. A band could give their fans a couple new videos from a live concert, a behind-the-scenes photo gallery Like these next few linksAn album to purchase. '
    ```

---
## 4 · Agents SDK 即時轉錄
*models = gpt-4o-transcribe, gpt-4o-mini*
### 什麼時候用
* 想用 OpenAI Agents SDK，以最少的設定做即時轉錄和語音合成。
* 想把轉錄直接接進 agent 驅動的 workflow。
* 想讓 SDK 高階地管理音訊輸入輸出、WebSocket 和 buffer。


### 運作方式

![Agents Transcription flow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agents_sdk_transcription.png)

**優點**

- **幾乎不用寫樣板程式：** `VoicePipeline` 幫你處理重新取樣、VAD、buffer、token 驗證和重連。  
- **和 agent 無縫整合：** 可以用即時音訊轉錄直接跟 GPT agent 互動。

**限制**

- **只有 Python 的 beta：** 其他語言還沒有，API 可能會變。  
- **可控性較低：** 想調 VAD 門檻或封包排程，得去翻 SDK 內部。  

```python
# ── 1 · agent that replies in French ---------------------------------------
fr_agent = Agent(
    name="Assistant-FR",
    instructions=
        "Translate the user's words into French.",
    model="gpt-4o-mini",
)

# ── 2 · workflow that PRINTS what it yields --------------------------------
class PrintingWorkflow(SingleAgentVoiceWorkflow):
    """Subclass that prints every chunk it yields (the agent's reply)."""

    async def run(self, transcription: str):
        # Optionally: also print the user transcription
        print()
        print("[User]:", transcription)
        print("[Assistant]: ", end="", flush=True)
        async for chunk in super().run(transcription):
            print(chunk, end="", flush=True)   # <-- agent (French) text
            yield chunk                        # still forward to TTS


pipeline = VoicePipeline(
    workflow=PrintingWorkflow(fr_agent),
    stt_model=MODEL_NAME,
    config=VoicePipelineConfig(tracing_disabled=True),
)

# ── 3 · helper to stream ~40 ms chunks at 24 kHz ---------------------------
def load_and_resample(path: str, sr: int = 24_000) -> np.ndarray:
    """Return mono PCM-16 as a NumPy array."""
    data, file_sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)
    if file_sr != sr:
        data = resampy.resample(data, file_sr, sr)
    return data
        
def audio_chunks(path: str, target_sr: int = 24_000, chunk_ms: int = 40):
    # 1️⃣ reuse the helper
    audio = load_and_resample(path, target_sr)

    # 2️⃣ float-32 → int16 NumPy array
    pcm = (np.clip(audio, -1, 1) * 32_767).astype(np.int16)

    # 3️⃣ yield real-time sized hops
    hop = int(target_sr * chunk_ms / 1_000)
    for off in range(0, len(pcm), hop):
        yield pcm[off : off + hop]

# ── 4 · stream the file ----------------------------------------------------
async def stream_audio(path: str):
    sai = StreamedAudioInput()
    run_task = asyncio.create_task(pipeline.run(sai))

    for chunk in audio_chunks(path):
        await sai.add_audio(chunk)
        await asyncio.sleep(len(chunk) / 24_000)   # real-time pacing

    # just stop pushing; session ends automatically
    await run_task        # wait for pipeline to finish
```

```python
await stream_audio(AUDIO_PATH)
```

??? note "輸出"

    ```text

    [User]: And lots of times you need to give people more than one link at a time.
    [Assistant]: Et souvent, vous devez donner aux gens plusieurs liens à la fois.
    [User]: A band could give their fans a couple new videos from a live concert, a behind-the-scenes photo gallery.
    [Assistant]: Un groupe pourrait donner à ses fans quelques nouvelles vidéos d'un concert live, ainsi qu'une galerie de photos des coulisses.
    [User]: An album to purchase.
    [Assistant]:
    ```

    ```text
    Un album à acheter.
    [User]: like these next few links.
    [Assistant]: comme ces quelques liens suivants.
    ```

## 結論  

這份 notebook 帶你用 OpenAI API 和 Agents SDK 試了多種語音轉文字的做法，從簡單的檔案上傳到完整互動的即時串流。每種做法適合的情境不同，挑最符合你產品需求的那個。

### 重點
- **依情境選方法：**  
  • 離線批次工作 → 檔案轉錄。  
  • 接近即時的更新 → HTTP 串流。  
  • 對話式、低延遲的體驗 → WebSocket 或 Agents SDK。  
- **權衡取捨：** 延遲、實作成本、支援格式和 session 限制，每種做法都不一樣。  
- **保持更新：** 模型和 SDK 持續改進，新功能常常上線。

### 下一步
1. 自己跑一遍 notebook。
2. 把你選的 workflow 整合進你的應用程式。
3. 回饋給我們！社群的意見會推動下一輪模型升級。  

## 參考資料
* 看 [Transcriptions API docs](https://platform.openai.com/docs/api-reference/audio)。
* 讀 [Realtime guide](https://platform.openai.com/docs/guides/realtime?use-case=transcription)。
* 看 [Agents SDK reference](https://openai.github.io/openai-agents-python/)。
* 看 [Agents SDK Voice Pipeline reference](https://openai.github.io/openai-agents-python/voice/)

## 重點整理

- 四種方法的差別主要在延遲、是否需要完整音檔、實作複雜度。
- 離線批次用整檔上傳最簡單，要有即時感但已有音檔就加 `stream=True`。
- 真正的即時音訊串流要用 Realtime WebSocket，但要自己處理格式（pcm16）、session 30 分鐘上限和逐字稿拼接。
- Agents SDK 的 `VoicePipeline` 把重取樣、VAD、重連都包起來，代價是目前只有 Python beta 且可控性較低。

## 練習

1. 換一個你自己的 WAV 音檔，跑第 1 節的轉錄，看看結果。
2. 把整檔上傳改成 `stream=True`，印出每個 delta 事件的時間，感受第一個 token 出現的延遲跟第 1 節差多少。
3. 在 Realtime WebSocket 的範例裡，調整 turn detection 或降噪的設定，比較逐字稿的切分有什麼不同。
