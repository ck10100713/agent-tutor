---
translated: true
source: examples/Context_summarization_with_realtime_api.ipynb
---
# 用 Realtime API 做 Context Summarization

> 原文：[examples/Context_summarization_with_realtime_api.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Context_summarization_with_realtime_api.ipynb)



## 這篇在做什麼
從頭做一個語音 bot：從麥克風收音、即時串流到 Realtime API、即時播放回覆。對話變長、token 累積太多時，自動把舊的對話壓成一段摘要，讓回答品質不會掉。

## 學完你會
- 把麥克風 PCM‑16 音訊用 asyncio queue 和 WebSocket 串流到 Realtime API，並處理 `response.done` 等回傳事件。
- 寫一個 `ConversationState` 記錄所有對話，監控 token 用量，超過門檻就在背景做摘要。
- 用 `conversation.item.create` 把摘要插到對話最前面，再用 `conversation.item.delete` 刪掉被摘要的舊訊息，並驗證摘要真的進了 context。

## 開跑前
- Python 3.10 以上。
- 需要 `OPENAI_API_KEY`（Realtime API 會計費）。
- 需要麥克風和喇叭，作業系統跳出權限詢問時要允許。

## 1. 概述
做一個端到端的**語音 bot**：聽你的麥克風、即時說話回應，並且**摘要很長的對話**，讓品質不會下降。

### 你會學到什麼
1. **即時麥克風串流** → OpenAI *Realtime*（voice‑to‑voice）endpoint。
2. 每一輪都有**即時逐字稿與語音播放**。
3. 一個**對話狀態容器**，儲存**每一則** user / assistant 訊息。
4. **自動 “context trim”**：當 token 視窗變得很大（可設定），較舊的對話會被壓縮成摘要。
5. **可擴充的設計**，可以改成客服 bot、kiosk 或多語言助理。


### 先決條件

| Requirement | Details |
|-------------|---------|
| **Python ≥ 3.10** | 確保不會遇到問題 |
| **OpenAI API key** | 在 shell 設定 `OPENAI_API_KEY`，或直接貼在程式裡（*正式環境不建議*） |
| 麥克風 + 喇叭 | 若系統詢問，請授予權限 |


**需要協助設定 key？**  
> 照著[官方快速入門指南](https://platform.openai.com/docs/quickstart#step-2-set-your-api-key)做。


*備註：*
> 1. gpt-realtime 支援 32k token 的 context window，不過在某些情境下，context 塞越多 token，你可能會發現表現變差。
> 2. Token window = 模型在這個 session 中目前記在記憶裡的所有 token（文字和音訊 token）。

### 一行安裝（在新的 cell 執行）

*新的 API 參數：*
> 1. Realtime API GA 新增了 [`truncation`](https://platform.openai.com/docs/api-reference/realtime-client-events/session/update#realtime-client-events/session/update-session-realtime-session-configuration-truncation) 參數。這個參數會自動優化 context 的截斷，保留相關資訊，同時最大化 cache 命中率。

```python
# Run once to install or upgrade dependencies (comment out if already installed)
# !pip install --upgrade openai websockets sounddevice simpleaudio
```

```python
# Standard library imports
import os
import sys
import io
import json
import base64
import pathlib
import wave
from dataclasses import dataclass, field
from typing import List, Literal

# Third-party imports
import asyncio
import numpy as np
import sounddevice as sd         # microphone capture
import simpleaudio               # speaker playback
import websockets                # WebSocket client
import openai                    # OpenAI Python SDK >= 1.14.0
```

```python
# Set your API key safely
openai.api_key = os.getenv("OPENAI_API_KEY", "")
if not openai.api_key:
    raise ValueError("OPENAI_API_KEY not found – please set env var or edit this cell.")
```

## 2. Token 使用量：文字 vs 語音

大的 token 視窗很珍貴，每多用一個 token 就多一分延遲和成本。  
**音訊**的輸入 token 視窗成長得比純文字快很多，因為振幅、時間和其他聲學細節都要被表示出來。

實際上，同一句話用音訊的 token 通常比文字多出**約 10 倍**。


* gpt-realtime 最多接受 **32k token**，而且 token 越多，遵循指令的能力可能越飄。
* 每一輪 user / assistant 對話都會消耗 token，視窗**只會越來越大**。
* **策略**：把較舊的對話摘要成一則 assistant 訊息，保留最近幾輪的原文，然後繼續。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/text-vs-audio-tokens.png" alt="drawing" width="800"/>

## 3. 輔助函式
下面的輔助函式讓我們能跑完整個 script。

### 3.1 對話狀態
跟 HTTP 式的 Chat Completions 不同，Realtime API 維持一個開著的、**有狀態**的 session，有兩個關鍵元件：

| Component       | Purpose |
|----------------|---------|
| **Session**     | 控制全域設定：model、voice、modalities、VAD 等。 |
| **Conversation** | 儲存 user 和 assistant 之間一輪一輪的訊息，包括音訊和文字。 |

這個 notebook 把這兩個元件包進一個簡單的 `ConversationState` 物件，讓邏輯保持乾淨、追蹤歷史，並在 context window 快滿時管理摘要。

```python
@dataclass
class Turn:
    """One utterance in the dialogue (user **or** assistant)."""
    role: Literal["user", "assistant"]
    item_id: str                    # Server‑assigned identifier
    text: str | None = None         # Filled once transcript is ready

@dataclass
class ConversationState:
    """All mutable data the session needs — nothing more, nothing less."""
    history: List[Turn] = field(default_factory=list)         # Ordered log
    waiting: dict[str, asyncio.Future] = field(default_factory=dict)  # Pending transcript fetches
    summary_count: int = 0

    latest_tokens: int = 0          # Window size after last reply
    summarising: bool = False       # Guard so we don’t run two summaries at once
```

一個快速看逐字稿的 helper：

```python
def print_history(state) -> None:
    """Pretty-print the running transcript so far."""
    print("—— Conversation so far ———————————————")
    for turn in state.history:
        text_preview = (turn.text or "").strip().replace("\n", " ")
        print(f"[{turn.role:<9}] {text_preview}  ({turn.item_id})")
    print("——————————————————————————————————————————")
```

### 3.2 · 串流音訊
我們把原始 PCM‑16 麥克風資料直接串流進 Realtime API。

流程是：mic ─► async.Queue ─► WebSocket ─► Realtime API

#### 3.2.1 擷取麥克風輸入
先寫一個 coroutine，它會：

* 以 **24 kHz、單聲道、PCM‑16** 開啟預設麥克風（這是 Realtime 接受的[格式](https://platform.openai.com/docs/api-reference/realtime-sessions/create#realtime-sessions-create-input_audio_format)之一）。  
* 把串流切成 **約 40 ms** 的區塊。  
* 把每個區塊丟進 `asyncio.Queue`，讓另一個 task（下一節）可以轉送給 OpenAI。

```python
async def mic_to_queue(pcm_queue: asyncio.Queue[bytes]) -> None:
    """
    Capture raw PCM‑16 microphone audio and push ~CHUNK_DURATION_MS chunks
    to *pcm_queue* until the surrounding task is cancelled.

    Parameters
    ----------
    pcm_queue : asyncio.Queue[bytes]
        Destination queue for PCM‑16 frames (little‑endian int16).
    """
    blocksize = int(SAMPLE_RATE_HZ * CHUNK_DURATION_MS / 1000)

    def _callback(indata, _frames, _time, status):
        if status:                               # XRuns, device changes, etc.
            print("⚠️", status, file=sys.stderr)
        try:
            pcm_queue.put_nowait(bytes(indata))  # 1‑shot enqueue
        except asyncio.QueueFull:
            # Drop frame if upstream (WebSocket) can’t keep up.
            pass

    # RawInputStream is synchronous; wrap in context manager to auto‑close.
    with sd.RawInputStream(
        samplerate=SAMPLE_RATE_HZ,
        blocksize=blocksize,
        dtype="int16",
        channels=1,
        callback=_callback,
    ):
        try:
            # Keep coroutine alive until cancelled by caller.
            await asyncio.Event().wait()
        finally:
            print("⏹️  Mic stream closed.")
```

#### 3.2.2 把音訊區塊送到 API

麥克風 task 現在會把原始 PCM‑16 區塊不斷放進 `asyncio.Queue`。  
下一步：從 queue 取出區塊，做 **base‑64 編碼**（協定要求是 JSON 安全的文字），再把每個區塊當成 `input_audio_buffer.append` 事件送到 Realtime WebSocket。

```python
# Helper function to encode audio chunks in base64
b64 = lambda blob: base64.b64encode(blob).decode()

async def queue_to_websocket(pcm_queue: asyncio.Queue[bytes], ws):
    """Read audio chunks from queue and send as JSON events."""
    try:
        while (chunk := await pcm_queue.get()) is not None:
            await ws.send(json.dumps({
                "type": "input_audio_buffer.append",
                "audio": b64(chunk),
            }))
    except websockets.ConnectionClosed:
        print("WebSocket closed – stopping uploader")
```

#### 3.2.3 處理收到的事件 
音訊到達 server 後，Realtime API 會在**同一條** WebSocket 上持續推送 JSON 事件。  
理解這些事件對下面幾件事很重要：

* 印出即時逐字稿  
* 把增量音訊播放給使用者  
* 維持準確的 [`Conversation State`](https://platform.openai.com/docs/api-reference/realtime-server-events/conversation/created)，之後 context trimming 才會正確  


| Event type | When it arrives | Why it matters | Typical handler logic |
|------------|-----------------|---------------|-----------------------|
| **`session.created`** | Immediately after the WebSocket handshake | Confirms the session is open and provides the `session.id`. | Log the ID for traceability and verify the connection. |
| **`session.updated`** | After you send a `session.update` call | Acknowledges that the server applied new session settings. | Inspect the echoed settings and update any local cache. |
| **`conversation.item.created`** (user) | A few ms after the user stops speaking (client VAD fires) | Reserves a timeline slot; transcript may still be **`null`**. | Insert a *placeholder* user turn in `state.history` marked “pending transcript”. |
| **`conversation.item.retrieved`** | ~100 – 300 ms later, once audio transcription is complete | Supplies the final user transcript (with timing). | Replace the placeholder with the transcript and print it if desired. |
| **`response.audio.delta`** | Every 20 – 60 ms while the assistant is speaking | Streams PCM‑16 audio chunks (and optional incremental text). | Buffer each chunk and play it; optionally show partial text in the console. |
| **`response.done`** | After the assistant’s last token | Signals both audio & text are complete; includes usage stats. | Finalize the assistant turn, update `state.latest_tokens`, and log usage. |
| **`conversation.item.deleted`** | Whenever you prune with `conversation.item.delete` | Confirms a turn was removed, freeing tokens on the server. | Mirror the deletion locally so your context window matches the server’s. |



### 3.3 偵測何時該摘要
Realtime 模型有 **32k token 的大視窗**，但 context 塞越多，品質可能在到達上限之前就開始飄。

我們的目標：當累積的視窗接近安全門檻（這個 notebook 預設 **2 000 tokens**）時**自動摘要**，然後把被取代的舊對話在本機*和* server 端都刪掉。

我們監控 `response.done` 回傳的 latest_tokens。當它超過 SUMMARY_TRIGGER，且對話輪數多於 KEEP_LAST_TURNS 時，就啟動一個背景的摘要 coroutine。

我們把最後 2 輪以外的所有內容壓縮成一段法文，然後：

1. 把這一段插到對話最前面，當作一則新訊息。

2. 刪除被拿去做摘要的那些訊息 item。

之後我們會問語音 agent 摘要是什麼語言，來測試摘要有沒有成功插進 Realtime API 的 Conversation context。

```python
async def run_summary_llm(text: str) -> str:
    """Call a lightweight model to summarise `text`."""
    resp = await asyncio.to_thread(lambda: openai.chat.completions.create(
        model=SUMMARY_MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": "Summarise in French the following conversation "
                            "in one concise paragraph so it can be used as "
                            "context for future dialogue."},
            {"role": "user", "content": text},
        ],
    ))
    return resp.choices[0].message.content.strip()
```

重要的實作細節：
- 摘要是以 SYSTEM 訊息而不是 ASSISTANT 訊息的形式加入。測試發現，在很長的對話中，用 ASSISTANT 訊息放摘要，可能讓模型誤把音訊回應切換成文字回應。改用 SYSTEM 訊息放摘要（也可以附加額外的自訂指令），就能清楚告訴模型這是設定 context 的指令，避免它錯誤地沿用目前 user 與 assistant 互動的 modality。

```python
async def summarise_and_prune(ws, state):
    """Summarise old turns, delete them server‑side, and prepend a single summary
    turn locally + remotely."""
    state.summarising = True
    print(
        f"⚠️  Token window ≈{state.latest_tokens} ≥ {SUMMARY_TRIGGER}. Summarising…",
    )
    old_turns, recent_turns = state.history[:-KEEP_LAST_TURNS], state.history[-KEEP_LAST_TURNS:]
    convo_text = "\n".join(f"{t.role}: {t.text}" for t in old_turns if t.text)
    
    if not convo_text:
        print("Nothing to summarise (transcripts still pending).")
        state.summarising = False

    summary_text = await run_summary_llm(convo_text) if convo_text else ""
    state.summary_count += 1
    summary_id = f"sum_{state.summary_count:03d}"
    state.history[:] = [Turn("assistant", summary_id, summary_text)] + recent_turns
    
    print_history(state)    

    # Create summary on server
    await ws.send(json.dumps({
        "type": "conversation.item.create",
        "previous_item_id": "root",
        "item": {
            "id": summary_id,
            "type": "message",
            "role": "system",
            "content": [{"type": "input_text", "text": summary_text}],
        },
    }))

    # Delete old items
    for turn in old_turns:
        await ws.send(json.dumps({
            "type": "conversation.item.delete",
            "item_id": turn.item_id,
        }))

    print(f"✅ Summary inserted ({summary_id})")
    
    state.summarising = False
```

下面的函式讓我們可以隨時間輪詢逐字稿。當使用者的音訊沒有馬上被轉錄時很有用，我們之後可以再取得最終結果。

```python
async def fetch_full_item(
    ws, item_id: str, state: ConversationState, attempts: int = 1
):
    """
    Ask the server for a full conversation item; retry up to 5× if the
    transcript field is still null.  Resolve the waiting future when done.
    """
    # If there is already a pending fetch, just await it
    if item_id in state.waiting:
        return await state.waiting[item_id]

    fut = asyncio.get_running_loop().create_future()
    state.waiting[item_id] = fut

    await ws.send(json.dumps({
        "type": "conversation.item.retrieve",
        "item_id": item_id,
    }))
    item = await fut

    # If transcript still missing retry (max 5×)
    if attempts < 5 and not item.get("content", [{}])[0].get("transcript"):
        await asyncio.sleep(0.4 * attempts)
        return await fetch_full_item(ws, item_id, state, attempts + 1)

    # Done – remove the marker
    state.waiting.pop(item_id, None)
    return item
```

## 4. 端到端流程示範

執行下面兩個 cell 來啟動互動 session。中斷 cell 就會停止錄音。

> **注意：**  
> 這個 notebook 使用 `SUMMARY_TRIGGER = 2000` 和 `KEEP_LAST_TURNS = 2`，讓摘要比較容易快速示範。  
> 正式環境請依你的應用需求調整這些值。  
> - 典型的 `SUMMARY_TRIGGER` 落在 **20,000–32,000 tokens** 之間，要看你的使用情境中 context 變大後表現會怎麼退化。

```python
# Audio/config knobs
SAMPLE_RATE_HZ    = 24_000   # Required by pcm16
CHUNK_DURATION_MS = 40       # chunk size for audio capture
BYTES_PER_SAMPLE  = 2        # pcm16 = 2 bytes/sample
SUMMARY_TRIGGER   = 2_000    # Summarise when context ≥ this
KEEP_LAST_TURNS   = 2       # Keep these turns verbatim
SUMMARY_MODEL     = "gpt-4o-mini"  # Cheaper, fast summariser
```

```python
# --------------------------------------------------------------------------- #
# Realtime session                                                          #
# --------------------------------------------------------------------------- #
async def realtime_session(model="gpt-realtime", voice="shimmer", enable_playback=True):
    """
    Main coroutine: connects to the Realtime endpoint, spawns helper tasks,
    and processes incoming events in a big async‑for loop.
    """
    state = ConversationState()  # Reset state for each run

    pcm_queue: asyncio.Queue[bytes] = asyncio.Queue()
    assistant_audio: List[bytes] = []

    # ----------------------------------------------------------------------- #
    # Open the WebSocket connection to the Realtime API                       #
    # ----------------------------------------------------------------------- #
    url = f"wss://api.openai.com/v1/realtime?model={model}"
    headers = {"Authorization": f"Bearer {openai.api_key}"}

    async with websockets.connect(url, extra_headers=headers, max_size=1 << 24) as ws:
        # ------------------------------------------------------------------- #
        # Wait until server sends session.created                             #
        # ------------------------------------------------------------------- #
        while json.loads(await ws.recv())["type"] != "session.created":
            pass
        print("session.created ✅")

        # ------------------------------------------------------------------- #
        # Configure session: voice, modalities, audio formats, transcription  #
        # ------------------------------------------------------------------- #
        await ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "type": "realtime",
                model: "gpt-realtime",
                "voice": voice,
                "modalities": ["audio", "text"],
                "input_audio_format": "pcm16",
                "output_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-transcribe"},
            },
        }))

        # ------------------------------------------------------------------- #
        # Launch background tasks: mic capture → queue → websocket            #
        # ------------------------------------------------------------------- #
        mic_task = asyncio.create_task(mic_to_queue(pcm_queue))
        upl_task = asyncio.create_task(queue_to_websocket(pcm_queue, ws))

        print("🎙️ Speak now (Ctrl‑C to quit)…")

        try:
            # ------------------------------------------------------------------- #
            # Main event loop: process incoming events from the websocket         #
            # ------------------------------------------------------------------- #
            async for event_raw in ws:
                event = json.loads(event_raw)
                etype = event["type"]

                # --------------------------------------------------------------- #
                # User just spoke ⇢ conversation.item.created (role = user)        #
                # --------------------------------------------------------------- #
                if etype == "conversation.item.created" and event["item"]["role"] == "user":
                    item = event["item"]
                    text = None
                    if item["content"]:
                        text = item["content"][0].get("transcript")
                    
                    state.history.append(Turn("user", event["item"]["id"], text))
                    
                    # If transcript not yet available, fetch it later
                    if text is None:
                        asyncio.create_task(fetch_full_item(ws, item["id"], state))

                # --------------------------------------------------------------- #
                # Transcript fetched ⇢ conversation.item.retrieved                 #
                # --------------------------------------------------------------- #
                elif etype == "conversation.item.retrieved":
                    content = event["item"]["content"][0]
                    # Fill missing transcript in history
                    for t in state.history:
                        if t.item_id == event["item"]["id"]:
                            t.text = content.get("transcript")
                            break

                # --------------------------------------------------------------- #
                # Assistant audio arrives in deltas                               #
                # --------------------------------------------------------------- #
                elif etype == "response.audio.delta":
                    assistant_audio.append(base64.b64decode(event["delta"]))

                # --------------------------------------------------------------- #
                # Assistant reply finished ⇢ response.done                        #
                # --------------------------------------------------------------- #
                elif etype == "response.done":
                    for item in event["response"]["output"]:
                        if item["role"] == "assistant":
                            txt = item["content"][0]["transcript"]
                            state.history.append(Turn("assistant", item["id"], txt))
                            # print(f"\n🤖 {txt}\n")
                    state.latest_tokens = event["response"]["usage"]["total_tokens"]
                    print(f"—— response.done  (window ≈{state.latest_tokens} tokens) ——")
                    print_history(state)
                    
                    # Fetch any still‑missing user transcripts
                    for turn in state.history:
                        if (turn.role == "user"
                            and turn.text is None
                            and turn.item_id not in state.waiting):
                            asyncio.create_task(
                                fetch_full_item(ws, turn.item_id, state)
                            )

                    # Playback collected audio once reply completes
                    if enable_playback and assistant_audio:
                        simpleaudio.play_buffer(b"".join(assistant_audio), 1, BYTES_PER_SAMPLE, SAMPLE_RATE_HZ)
                        assistant_audio.clear()

                    # Summarise if context too large – fire in background so we don't block dialogue
                    if state.latest_tokens >= SUMMARY_TRIGGER and len(state.history) > KEEP_LAST_TURNS and not state.summarising:
                        asyncio.create_task(summarise_and_prune(ws, state))

        except KeyboardInterrupt:
            print("\nStopping…")
        finally:
            mic_task.cancel()
            await pcm_queue.put(None)
            await upl_task
```

```python
# Run the realtime session (this cell blocks until you stop it)
await realtime_session()
```

```raw
session.created ✅
🎙️ Speak now (Ctrl‑C to quit)…
—— response.done  (window ≈979 tokens) ——
—— Conversation so far ———————————————
[user     ] Can you tell me a quick story?  (item_BTuMOcpUqp8qknKhLzlkA)
[assistant] Once upon a time, in a cozy little village, there was a cat named Whiskers who was always getting into trouble. One sunny day, Whiskers found a mysterious glowing stone in the garden. Curious, he pawed at it, and poof! The stone granted him the ability to talk to birds. Whiskers and his new bird friends had grand adventures, solving mysteries and exploring the village. And from that day on, Whiskers was known as the most adventurous cat in the village. The end.  (item_BTuMPRWxqpv0ph6QM46DK)
——————————————————————————————————————————
—— response.done  (window ≈2755 tokens) ——
—— Conversation so far ———————————————
[user     ] Can you tell me a quick story?  (item_BTuMOcpUqp8qknKhLzlkA)
[assistant] Once upon a time, in a cozy little village, there was a cat named Whiskers who was always getting into trouble. One sunny day, Whiskers found a mysterious glowing stone in the garden. Curious, he pawed at it, and poof! The stone granted him the ability to talk to birds. Whiskers and his new bird friends had grand adventures, solving mysteries and exploring the village. And from that day on, Whiskers was known as the most adventurous cat in the village. The end.  (item_BTuMPRWxqpv0ph6QM46DK)
[user     ] Can you tell me three extremely funny stories?  (item_BTuNN64LdULM21OyC4vzN)
[assistant] Sure, let's dive into some giggle-worthy tales:  **Story One:** There was a forgetful baker named Benny who baked a hundred cakes for a big wedding. But on the big day, he forgot where he put them! The entire town joined in to find the missing cakes, only to discover Benny had stored them in his neighbor's garage, thinking it was his pantry. The wedding turned into a town-wide cake feast!  **Story Two:** A mischievous dog named Sparky loved to play pranks. One day, he swapped his owner's phone with a squeaky toy, causing a hilarious mix-up of barks, squeaks, and confused calls. Sparky's owner ended up having a full conversation with the mailman, all in squeaks!  **Story Three:** In a small town, a parrot named Polly became a local celebrity for reciting tongue twisters. One day, Polly challenged the mayor to a tongue twister duel. The mayor, tongue-tied and laughing, declared Polly the official town jester. Polly squawked with pride, and the town rang with laughter for days.  (item_BTuNNpNxki5ynSQ5c3Xsa)
——————————————————————————————————————————
⚠️  Token window ≈2755 ≥ 2000. Summarising…
—— Conversation so far ———————————————
[assistant] L'utilisateur a demandé une histoire rapide, et l'assistant a raconté celle d'un chat nommé Whiskers qui, après avoir trouvé une pierre mystérieuse dans son jardin, a obtenu le pouvoir de parler aux oiseaux. Avec ses nouveaux amis oiseaux, Whiskers a vécu de grandes aventures, résolvant des mystères et explorant le village, devenant ainsi le chat le plus aventurier du village.  (sum_001)
[user     ] Can you tell me three extremely funny stories?  (item_BTuNN64LdULM21OyC4vzN)
[assistant] Sure, let's dive into some giggle-worthy tales:  **Story One:** There was a forgetful baker named Benny who baked a hundred cakes for a big wedding. But on the big day, he forgot where he put them! The entire town joined in to find the missing cakes, only to discover Benny had stored them in his neighbor's garage, thinking it was his pantry. The wedding turned into a town-wide cake feast!  **Story Two:** A mischievous dog named Sparky loved to play pranks. One day, he swapped his owner's phone with a squeaky toy, causing a hilarious mix-up of barks, squeaks, and confused calls. Sparky's owner ended up having a full conversation with the mailman, all in squeaks!  **Story Three:** In a small town, a parrot named Polly became a local celebrity for reciting tongue twisters. One day, Polly challenged the mayor to a tongue twister duel. The mayor, tongue-tied and laughing, declared Polly the official town jester. Polly squawked with pride, and the town rang with laughter for days.  (item_BTuNNpNxki5ynSQ5c3Xsa)
——————————————————————————————————————————
✅ Summary inserted (sum_001)
—— response.done  (window ≈2147 tokens) ——
—— Conversation so far ———————————————
[assistant] L'utilisateur a demandé une histoire rapide, et l'assistant a raconté celle d'un chat nommé Whiskers qui, après avoir trouvé une pierre mystérieuse dans son jardin, a obtenu le pouvoir de parler aux oiseaux. Avec ses nouveaux amis oiseaux, Whiskers a vécu de grandes aventures, résolvant des mystères et explorant le village, devenant ainsi le chat le plus aventurier du village.  (sum_001)
[user     ] Can you tell me three extremely funny stories?  (item_BTuNN64LdULM21OyC4vzN)
[assistant] Sure, let's dive into some giggle-worthy tales:  **Story One:** There was a forgetful baker named Benny who baked a hundred cakes for a big wedding. But on the big day, he forgot where he put them! The entire town joined in to find the missing cakes, only to discover Benny had stored them in his neighbor's garage, thinking it was his pantry. The wedding turned into a town-wide cake feast!  **Story Two:** A mischievous dog named Sparky loved to play pranks. One day, he swapped his owner's phone with a squeaky toy, causing a hilarious mix-up of barks, squeaks, and confused calls. Sparky's owner ended up having a full conversation with the mailman, all in squeaks!  **Story Three:** In a small town, a parrot named Polly became a local celebrity for reciting tongue twisters. One day, Polly challenged the mayor to a tongue twister duel. The mayor, tongue-tied and laughing, declared Polly the official town jester. Polly squawked with pride, and the town rang with laughter for days.  (item_BTuNNpNxki5ynSQ5c3Xsa)
[user     ]   (item_BTuPLaCv8ATdIwAQ2rLgO)
[assistant] Sure! The first summary I provided between us was in French.  (item_BTuPLa7BaSQToGCVOmfBK)
```

---
我們跟 Voice AI 聊了一段。幾輪之後，總 token 數達到 SUMMARY_MAX，觸發了對話摘要的步驟，產生了前面訊息的摘要。

因為總共有 N = 4 則訊息，我們摘要前 N - 2 = 2 則：
```txt
—— Conversation so far ———————————————
[user     ] Can you tell me a quick story?  (item_BTuMOcpUqp8qknKhLzlkA)
[assistant] Once upon a time, in a cozy little village, there was a cat named Whiskers who was always getting into trouble. One sunny day, Whiskers found a mysterious glowing stone in the garden. Curious, he pawed at it, and poof! The stone granted him the ability to talk to birds. Whiskers and his new bird friends had grand adventures, solving mysteries and exploring the village. And from that day on, Whiskers was known as the most adventurous cat in the village. The end.  (item_BTuMPRWxqpv0ph6QM46DK)
```

接著我們產生法文摘要，用 root: true 旗標插進對話歷史，讓摘要出現在對話的第一則。之後，我們用 `"type": "conversation.item.delete"` 把被摘要的原始 item 刪掉。

為了驗證摘要有插進去，我們問 Voice AI 摘要是什麼語言，它正確回答：

```txt
[assistant] Sure! The first summary I provided between us was in French.  (item_BTuPLa7BaSQToGCVOmfBK)
```

## 5 · 實際應用

Context summarisation 對**長時間進行的語音體驗**很有用。  
以下是一些應用點子：

| Use‑case | Added Value | Why Useful |
|----------|-------------|------------|
| **Customer‑support voicebot** | 24/7 natural phone tree; auto‑generate ticket summaries | Summarizes long customer calls for efficient handoff and record-keeping, reducing agent workload and improving response quality. |
| **Language tutor** | Real‑time conversation practice with corrective feedback | Helps track learner progress and highlights recurring mistakes, enabling personalized feedback and more effective language acquisition. |
| **AI therapist / coach** | Safe, always‑available listener that remembers sessions | Maintains continuity across sessions by recalling key topics and emotional tone, supporting a more empathetic and effective experience. |
| **Meeting assistant** | Live transcripts + concise action‑item recap in Slack | Distills lengthy meetings into actionable summaries, saving team members time and ensuring important points are not missed. |


## 6 · 下一步與延伸閱讀
試跑這個 notebook，並試著把 context summary 整合進你的應用。

可以試試這幾件事：
| Try this… | What you’ll learn |
|-----------|------------------|
| **A/B test summarisation**<br/>Run your eval suite with summarisation *on* vs *off*. | Whether trimming actually improves quality for your domain—and how it affects latency & cost. |
| **Swap summary styles**<br/>Change the system prompt to bullet points, JSON, English vs French, etc. | Which format the downstream assistant absorbs best; how language choice influences follow‑up answers. |
| **Vary thresholds**<br/>Play with `SUMMARY_TRIGGER_TOKENS` (2 k → 8 k). | The sweet spot between model drift and summarisation overhead. |
| **Cost tracing**<br/>Log `usage.total_tokens` before/after summarisation. | Concrete ROI: token savings per hour of conversation. |


### 參考資源：
- [OpenAI Realtime Guide](https://platform.openai.com/docs/guides/realtime)
- [OpenAI Realtime Conversations](https://platform.openai.com/docs/guides/realtime-conversations)
- [OpenAI Realtime API Reference](https://platform.openai.com/docs/api-reference/realtime)
- [Voice AI and Voice Agents](https://voiceaiandvoiceagents.com/)

## 重點整理
- Realtime API 是有狀態的 session，音訊 token 比文字多很多（約 10 倍），所以 context 長得很快。
- 視窗雖有 32k，但品質常在到達上限前就開始飄，所以要在安全門檻自動摘要。
- 摘要策略是保留最近幾輪原文，把舊的壓成一則訊息放到最前面，再刪掉原本的 item，本機和 server 的歷史要同步。
- 摘要用 SYSTEM 訊息放，避免模型在長對話中從音訊回應誤切成文字回應。
- 門檻（`SUMMARY_TRIGGER`、`KEEP_LAST_TURNS`）要依實際用例調整，示範用 2000，正式環境常在 2 萬到 3.2 萬之間。

## 練習
1. 把 `SUMMARY_TRIGGER` 從 2000 改成 4000，觀察要聊幾輪才會觸發摘要，以及觸發時 `latest_tokens` 的值。
2. 把摘要的語言從法文改成英文或繁體中文，再問語音 agent 摘要是什麼語言，確認新的摘要有被插進 context。
3. 把 `KEEP_LAST_TURNS` 從 2 改成 4，並在每次摘要前後印出 `usage.total_tokens`，比較省下多少 token。
