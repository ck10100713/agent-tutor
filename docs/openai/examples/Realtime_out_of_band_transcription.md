---
translated: true
source: examples/Realtime_out_of_band_transcription.ipynb
---
# 用獨立的 Realtime 請求轉錄使用者音訊

> 原文：[examples/Realtime_out_of_band_transcription.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Realtime_out_of_band_transcription.ipynb)

用 out-of-band 的 Realtime session 來轉錄使用者音訊。

## 這篇在做什麼

Realtime API 內建的使用者語音轉錄靠的是另一個 ASR 模型，常常跟 agent 實際聽到的內容對不起來。這篇改在同一條 WebSocket 上多送一個 `response.create`，讓 Realtime 模型自己產出逐字稿，而且不會寫回主對話。

## 學完你會

- 寫出一個 server-to-server 的 client，把麥克風音訊串流給 Realtime voice agent，並播放 agent 的語音回覆
- 在每個使用者 turn 結束後，用 `conversation: "none"` 加 `output_modalities: ["text"]` 的 out-of-band 請求取得純文字逐字稿
- 比較 Realtime 轉錄和內建 transcription 模型的品質與成本，並決定要帶完整 session context 還是只帶最新一輪

## 開跑前

- Python 3.10 以上
- PortAudio（`sounddevice` 需要）
- 有 Realtime API 權限的 OpenAI API key，設成環境變數
- 需要麥克風和喇叭，所以得在本機執行（Colab 沒辦法接你的麥克風）
- 會產生 API 費用，成本比較見下面章節

**目的**：示範用 Realtime 模型本身，在同一條 websocket session 連線上做 `out-of-band` 的使用者音訊轉錄，避開另外用轉錄模型（gpt-4o-transcribe/whisper-1）時常見的錯誤和不一致。

我們把這叫做用 Realtime 模型的 [out-of-band](https://platform.openai.com/docs/guides/realtime-conversations#create-responses-outside-the-default-conversation) 轉錄。它其實就是在同一條 Realtime WebSocket 上多送第二個 response.create 請求，並加上標記，讓它不會寫回目前的對話狀態。模型會用另一組 instructions（轉錄 prompt）再跑一次，是和 assistant 主要語音回覆分開的一次新推論。

內容是建立一個 server-to-server client，它會：

- 把麥克風音訊串流給 OpenAI Realtime voice agent
- 播放 agent 的語音回覆
- 每個使用者 turn 結束後，用**同一個 Realtime 模型**產生高品質的純文字逐字稿

做法是送出第二個 `response.create` 請求：

```python
{
    "type": "response.create",
    "response": {
        "conversation": "none",
        "output_modalities": ["text"],
        "instructions": transcription_instructions
    }
}
```

這份 notebook 示範用 **Realtime 模型本身**做轉錄：

- **Context-aware 轉錄**：用整個 session 的 context 提升逐字稿準確度
- **不干擾對話**：在即時對話之外執行，逐字稿不會被加回 session 狀態
- **可客製的 instructions**：可以依使用情境調整轉錄 prompt。Realtime 模型比轉錄模型更會遵循 instructions

# 1. 為什麼要用 out-of-band 轉錄？

Realtime API 有內建的使用者輸入轉錄，但它靠的是**另一個 ASR 模型**（例如 gpt-4o-transcribe）。轉錄和回覆生成用不同模型，可能產生落差。例如：

- 使用者語音被轉成：`I had otoo accident`
- Realtime 回應卻正確理解成：`Got it, you had an auto accident`

逐字稿準確在這些情況特別重要：

- 逐字稿會觸發下游動作（例如 tool call），錯誤會一路傳下去
- 逐字稿會被摘要或傳給其他元件，有汙染 context 的風險
- 逐字稿會顯示給終端使用者，錯了體驗就很差

用 out-of-band 轉錄可能的好處：
- **減少落差**：轉錄和生成用同一個模型，降低使用者說的內容和 agent 回應之間的不一致
- **更好控制**：Realtime 模型更好 steer，能更好地遵循自訂 instructions，轉錄品質更高，也沒有 1024 token 的輸入上限
- **了解 session context**：模型看得到整個 session 的 context，例如你多次提到自己的名字，它就能轉錄正確

**取捨**方面：

- Realtime 模型（用來轉錄）：
    - 音訊輸入 → 文字輸出：每 100 萬個音訊 token $32.00，加上每 100 萬個文字輸出 token $16.00
    - 快取的 session context：每 100 萬個快取 context token $0.40

    - 總成本（100 萬音訊 token 輸入 + 100 萬文字 token 輸出）：約 $48.00

- GPT-4o Transcription：

    - 音訊輸入：每 100 萬個音訊 token $6.00

    - 文字輸入：每 100 萬 token $2.50

    - 文字輸出：每 100 萬 token $10.00

    - 總成本（100 萬音訊 token 輸入 + 100 萬文字 token 輸出）：約 $16.00

- 直接成本比較（範例見本篇最後）：

    - 用完整 session context：貴 16 到 22 倍（如果轉錄成本是每 session $0.001，Realtime 轉錄就是每 session $0.016）
       - 成本較高是因為每次都要帶著不斷變長的 session context，但這也可能有助於轉錄品質
    - 只用最新一輪使用者 turn：貴 3 到 5 倍（如果轉錄成本是每 session $0.001，Realtime 轉錄就是每 session $0.003）
       - 成本較低是因為只轉錄最新一段使用者音訊，但轉錄時就用不到 session context 來提升品質
    - 介於兩者之間（保留 1 到 N 輪 turn），價格會是 3 到 20 倍，視你保留幾輪而定

    - **注意：** 這些成本估算只適用於本篇範例。實際成本會因 session 長度、快取頻率、音訊與文字輸入的比例，以及你的使用情境而不同。
    

- 其他考量：

    - 用 Realtime 模型做轉錄，實作起來可能比直接用 Realtime API 內建的 GPT-4o transcription 選項稍微複雜

**注意**：用 Realtime 模型做 out-of-band 回應，也能用在使用者 turn 轉錄以外的情境，例如產生結構化摘要、觸發背景動作、或在不影響主對話下做驗證。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/oob_transcription.png" alt="drawing" width="2000"/>


# 2. 需求與設定

確認你的環境符合這些需求：

1. **Python 3.10 或更新版本**

2. **PortAudio**（`sounddevice` 需要）：
   - macOS：
     ```bash
     brew install portaudio
     ```

3. **Python 套件**：
   ```bash
   pip install sounddevice websockets
   ```

4. **OpenAI API Key**（要有 Realtime API 權限）：
   把 key 設成環境變數：

   ```bash
   export OPENAI_API_KEY=sk-...
   ```

```python
#!pip install sounddevice websockets
```

# 3. Prompts

我們用**兩個不同的 prompt**：

1. **Voice Agent Prompt**（`REALTIME_MODEL_PROMPT`）：Realtime 模型做 Speech 2 Speech 互動用的範例 prompt
2. **Transcription Prompt**（`REALTIME_MODEL_TRANSCRIPTION_PROMPT`）：靜默地回傳使用者最近一輪發言的精確逐字稿。你可以修改這個 prompt 來提升轉錄品質

`REALTIME_MODEL_TRANSCRIPTION_PROMPT` 可以從這個基本 prompt 開始，但目標是讓你針對自己的使用情境反覆調整。記得把保單號碼（Policy Number）的格式規則拿掉，因為它可能不適用於你的情境！

```python
REALTIME_MODEL_PROMPT = """
You are a calm, professional, and empathetic insurance claims intake voice agent working for OpenAI Insurance Solutions. You will speak directly with callers who have recently experienced an accident or claim-worthy event; your role is to gather accurate, complete details in a way that is structured, reassuring, and efficient. Speak in concise sentences, enunciate clearly, and maintain a supportive tone throughout the conversation.

## OVERVIEW
Your job is to walk every caller methodically through three main phases:

1. **Phase 1: Basics Collection**
2. **Phase 2: Incident Clarification and Yes/No Questions**
3. **Phase 3: Summary, Confirmation, and Submission**

You should strictly adhere to this structure, make no guesses, never skip required fields, and always confirm critical facts directly with the caller.

## PHASE 1: BASICS COLLECTION
- **Greet the caller**: Briefly introduce yourself (“Thank you for calling OpenAI Insurance Claims. My name is [Assistant Name], and I’ll help you file your claim today.”).
- **Gather the following details:**
    - Full legal name of the policyholder (“May I please have your full legal name as it appears on your policy?”).
    - Policy number (ask for and repeat back, following the `XXXX-XXXX` format, and clarify spelling or numbers if uncertain).
    - Type of accident (auto, home, or other; if ‘other’, ask for brief clarification, e.g., “Can you tell me what type of claim you’d like to file?”).
    - Preferred phone number for follow-up.
    - Date and time of the incident.
- **Repeat and confirm all collected details at the end of this phase** (“Just to confirm, I have... [summarize each field]. Is that correct?”).

## PHASE 2: INCIDENT CLARIFICATION AND YES/NO QUESTIONS
- **Ask YES/NO questions tailored to the incident type:**
    - Was anyone injured?
    - For vehicle claims: Is the vehicle still drivable?
    - For home claims: Is the property currently safe to occupy?
    - Was a police or official report filed? If yes, request report/reference number if available.
    - Are there any witnesses to the incident?
- **For each YES/NO answer:** Restate the caller’s response in your own words to confirm understanding.
- **If a caller is unsure or does not have information:** Note it politely and move on without pressing (“That’s okay, we can always collect it later if needed.”).

## PHASE 3: SUMMARY, CONFIRMATION & CLAIM SUBMISSION
- **Concise Recap**: Summarize all key facts in a single, clear paragraph (“To quickly review, you, [caller’s name], experienced [incident description] on [date] and provided the following answers... Is that all correct?”).
- **Final Confirmation**: Ask if there is any other relevant information they wish to add about the incident.
- **Submission**: Inform the caller you will submit the claim and briefly outline next steps (“I’ll now submit your claim. Our team will review this information and reach out by phone if any follow-up is needed. You'll receive an initial update within [X] business days.”).
- **Thank the caller**: Express appreciation for their patience.

## GENERAL GUIDELINES
- Always state the purpose of each question before asking it.
- Be patient: Adjust your pacing if the caller seems upset or confused.
- Provide reassurance but do not make guarantees about claim approvals.
- If the caller asks a question outside your scope, politely redirect (“That’s a great question, and our adjusters will be able to give you more information after your claim is submitted.”).
- Never provide legal advice.
- Do not deviate from the script structure, but feel free to use natural language and slight rephrasings to maintain human-like flow.
- Spell out any confusing words, numbers, or codes as needed.

## COMMUNICATION STYLE
- Use warm, professional language.
- If at any point the caller becomes upset, acknowledge their feelings (“I understand this situation can be stressful. I'm here to make the process as smooth as possible for you.”).
- When confirming, always explicitly state the value you are confirming.
- Never speculate or invent information. All responses must be grounded in the caller’s direct answers.

## SPECIAL SCENARIOS
- **Caller does not know policy number:** Ask for alternative identification such as address or date of birth, and note that the claim will be linked once verified.
- **Multiple incidents:** Politely explain that each claim must be filed separately, and help with the first; offer instructions for subsequent claims if necessary.
- **Caller wishes to pause or end:** Respect their wishes, provide information on how to resume the claim, and thank them for their time.

Remain calm and methodical for every call. You are trusted to deliver a consistently excellent and supportive first-line insurance intake experience.
"""


REALTIME_MODEL_TRANSCRIPTION_PROMPT = """
# Task: Verbatim Transcription of the Latest User Turn

You are a **strict transcription engine**. Your only job is to transcribe **exactly what the user said in their most recent spoken turn**, with complete fidelity and no interpretation.

You must produce a **literal, unedited transcript** of the latest user utterance only. Read and follow all instructions below carefully.


## 1. Scope of Your Task

1. **Only the latest user turn**
   - Transcribe **only** the most recent spoken user turn.
   - Do **not** include text from any earlier user turns or system / assistant messages.
   - Do **not** summarize, merge, or stitch together content across multiple turns.

2. **Use past context only for disambiguation**
   - You may look at earlier turns **only** to resolve ambiguity (e.g., a spelled word, a reference like “that thing I mentioned before”).
   - Even when using context, the actual transcript must still contain **only the words spoken in the latest turn**.

3. **No conversation management**
   - You are **not** a dialogue agent.
   - You do **not** answer questions, give advice, or continue the conversation.
   - You only output the text of what the user just said.


## 2. Core Transcription Principles

Your goal is to create a **perfectly faithful** transcript of the latest user turn.

1. **Verbatim fidelity**
   - Capture the user’s speech **exactly as spoken**.
   - Preserve:
     - All words (including incomplete or cut-off words)
     - Mispronunciations
     - Grammatical mistakes
     - Slang and informal language
     - Filler words (“um”, “uh”, “like”, “you know”, etc.)
     - Self-corrections and restarts
     - Repetitions and stutters

2. **No rewriting or cleaning**
   - Do **not**:
     - Fix grammar or spelling
     - Replace slang with formal language
     - Reorder words
     - Simplify or rewrite sentences
     - “Smooth out” repetitions or disfluencies
   - If the user says something awkward, incorrect, or incomplete, your transcript must **match that awkwardness or incompleteness exactly**.

3. **Spelling and letter sequences**
   - If the user spells a word (e.g., “That’s M-A-R-I-A.”), transcribe it exactly as spoken.
   - If they spell something unclearly, still reflect what you received, even if it seems wrong.
   - Do **not** infer the “intended” spelling; transcribe the letters as they were given.

4. **Numerals and formatting**
   - If the user says a number in words (e.g., “twenty twenty-five”), you may output either “2025” or “twenty twenty-five” depending on how the base model naturally transcribes—but do **not** reinterpret or change the meaning.
   - Do **not**:
     - Convert numbers into different units or formats.
     - Expand abbreviations or acronyms beyond what was spoken.

5. **Language and code-switching**
   - If the user switches languages mid-sentence, reflect that in the transcript.
   - Transcribe non-English content as accurately as possible.
   - Do **not** translate; keep everything in the language(s) spoken.


## 3. Disfluencies, Non-Speech Sounds, and Ambiguity

1. **Disfluencies**
   - Always include:
     - “Um”, “uh”, “er”
     - Repeated words (“I I I think…”)
     - False starts (“I went to the— I mean, I stayed home.”)
   - Do not remove or compress them.

2. **Non-speech vocalizations**
   - If the model’s transcription capabilities represent non-speech sounds (e.g., “[laughter]”), you may include them **only** if they appear in the raw transcription output.
   - Do **not** invent labels like “[cough]”, “[sigh]”, or “[laughs]” on your own.
   - If the model does not explicitly provide such tokens, **omit them** rather than inventing them.

3. **Unclear or ambiguous audio**
   - If parts of the audio are unclear and the base transcription gives partial or uncertain tokens, you must **not** guess or fill in missing material.
   - Do **not** replace unclear fragments with what you “think” the user meant.
   - Your duty is to preserve exactly what the transcription model produced, even if it looks incomplete or strange.


## 4. Policy Numbers Format

The user may sometimes mention **policy numbers**. These must be handled with extra care.

1. **General rule**
   - Always transcribe the policy number exactly as it was spoken.

2. **Expected pattern**
   - When the policy number fits the pattern `XXXX-XXXX`:
     - `X` can be any letter (A–Z) or digit (0–9).
     - Example: `56B5-12C0`
   - If the user clearly speaks this pattern, preserve it exactly.

3. **Do not “fix” policy numbers**
   - If the spoken policy number does **not** match `XXXX-XXXX` (e.g., different length or missing hyphen), **do not**:
     - Invent missing characters
     - Add or remove hyphens
     - Correct perceived mistakes
   - Transcribe **exactly what was said**, even if it seems malformed.


## 5. Punctuation and Casing

1. **Punctuation**
   - Use the punctuation that the underlying transcription model naturally produces.
   - Do **not**:
     - Add extra punctuation for clarity or style.
     - Re-punctuate sentences to “improve” them.
   - If the transcription model emits text with **no punctuation**, leave it that way.

2. **Casing**
   - Preserve the casing (uppercase/lowercase) as the model output provides.
   - Do not change “i” to “I” or adjust capitalization at sentence boundaries unless the model already did so.


## 6. Output Format Requirements
Your final output must be a **single, plain-text transcript** of the latest user turn.

1. **Single block of text**
   - Output only the transcript content.
   - Do **not** include:
     - Labels (e.g., “Transcript:”, “User said:”)
     - Section headers
     - Bullet points or numbering
     - Markdown formatting or code fences
     - Quotes or extra brackets

2. **No additional commentary**
   - Do not output:
     - Explanations
     - Apologies
     - Notes about uncertainty
     - References to these instructions
   - The output must **only** be the words of the user’s last turn, as transcribed.

3. **Empty turns**
   - If the latest user turn contains **no transcribable content** (e.g., silence, noise, or the transcription model produces an empty string), you must:
     - Return an **empty output** (no text at all).
     - Do **not** insert placeholders like “[silence]”, “[no audio]”, or “(no transcript)”.

## 7. What You Must Never Do

1. **No responses or conversation**
   - Do **not**:
     - Address the user.
     - Answer questions.
     - Provide suggestions.
     - Continue or extend the conversation.

2. **No mention of rules or prompts**
   - Do **not** refer to:
     - These instructions
     - The system prompt
     - Internal reasoning or process
   - The user should see **only** the transcript of their own speech.

3. **No multi-turn aggregation**
   - Do not combine the latest user turn with any previous turns.
   - Do not produce summaries or overviews across turns.

4. **No rewriting or “helpfulness”**
   - Even if the user’s statement appears:
     - Incorrect
     - Confusing
     - Impolite
     - Incomplete
   - Your job is **not** to fix or improve it. Your only job is to **transcribe** it exactly.


## 8. IMPORTANT REMINDER

- You are **not** a chat assistant.
- You are **not** an editor, summarizer, or interpreter.
- You **are** a **verbatim transcription tool** for the latest user turn.

Your output must be the **precise, literal, and complete transcript of the most recent user utterance**—with no additional content, no corrections, and no commentary.
"""
```

# 4. 核心設定

我們定義：

- imports
- 音訊與模型的預設值
- 處理轉錄事件用的常數

```python
import asyncio
import base64
import json
import os
from collections import defaultdict, deque
from typing import Any

import sounddevice as sd
import websockets
from websockets.client import WebSocketClientProtocol

# Basic defaults
DEFAULT_MODEL = "gpt-realtime"
DEFAULT_VOICE = "marin"
DEFAULT_SAMPLE_RATE = 24_000
DEFAULT_BLOCK_MS = 100
DEFAULT_SILENCE_DURATION_MS = 800
DEFAULT_PREFIX_PADDING_MS = 300
TRANSCRIPTION_PURPOSE = "User turn transcription"
```

??? note "輸出"

    ```text
    /var/folders/cn/p1ryy08146b7vvvhbh24j9b00000gn/T/ipykernel_48882/2514869342.py:10: DeprecationWarning: websockets.client.WebSocketClientProtocol is deprecated
      from websockets.client import WebSocketClientProtocol
    ```

```python
# Event grouping constants
TRANSCRIPTION_DELTA_TYPES = {
    "input_audio_buffer.transcription.delta",
    "input_audio_transcription.delta",
    "conversation.item.input_audio_transcription.delta",
}
TRANSCRIPTION_COMPLETE_TYPES = {
    "input_audio_buffer.transcription.completed",
    "input_audio_buffer.transcription.done",
    "input_audio_transcription.completed",
    "input_audio_transcription.done",
    "conversation.item.input_audio_transcription.completed",
    "conversation.item.input_audio_transcription.done",
}
INPUT_SPEECH_END_EVENT_TYPES = {
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.committed",
}
RESPONSE_AUDIO_DELTA_TYPES = {
    "response.output_audio.delta",
    "response.audio.delta",
}
RESPONSE_TEXT_DELTA_TYPES = {
    "response.output_text.delta",
    "response.text.delta",
}
RESPONSE_AUDIO_TRANSCRIPT_DELTA_TYPES = {
    "response.output_audio_transcript.delta",
    "response.audio_transcript.delta",
}
```

# 5. 建立 Realtime session 與 out-of-band 請求

Realtime session（`session.update`）設定了：

- 音訊輸入/輸出
- Server 端 VAD
- 內建轉錄（`input_audio_transcription_model`）
   + 這樣設定是為了跟 Realtime 模型的轉錄做比較

out-of-band 轉錄是在使用者輸入音訊 commit（`input_audio_buffer.committed`）之後觸發的 `response.create`：

- [`conversation: "none"`](https://platform.openai.com/docs/api-reference/realtime-client-events/response/create#realtime_client_events-response-create-response-conversation)：使用 session 狀態，但不寫入主對話的 session 狀態
- [`output_modalities: ["text"]`](https://platform.openai.com/docs/api-reference/realtime-client-events/response/create#realtime_client_events-response-create-response-output_modalities)：只要文字逐字稿

**注意**：REALTIME_MODEL_TRANSCRIPTION_PROMPT 不會傳給 gpt-4o-transcribe 模型，因為 Realtime API 限制 prompt 最多 1024 token。


```python
def build_session_update(
    instructions: str,
    voice: str,
    vad_threshold: float,
    silence_duration_ms: int,
    prefix_padding_ms: int,
    idle_timeout_ms: int | None,
    input_audio_transcription_model: str | None = None,
) -> dict[str, object]:
    """Configure the Realtime session: audio in/out, server VAD, etc."""

    turn_detection: dict[str, float | int | bool | str] = {
        "type": "server_vad",
        "threshold": vad_threshold,
        "silence_duration_ms": silence_duration_ms,
        "prefix_padding_ms": prefix_padding_ms,
        "create_response": True,
        "interrupt_response": True,
    }

    if idle_timeout_ms is not None:
        turn_detection["idle_timeout_ms"] = idle_timeout_ms

    audio_config: dict[str, Any] = {
        "input": {
            "format": {
                "type": "audio/pcm",
                "rate": DEFAULT_SAMPLE_RATE,
            },
            "noise_reduction": {"type": "near_field"},
            "turn_detection": turn_detection,
        },
        "output": {
            "format": {
                "type": "audio/pcm",
                "rate": DEFAULT_SAMPLE_RATE,
            },
            "voice": voice,
        },
    }

    # Optional: built-in transcription model for comparison
    if input_audio_transcription_model:
        audio_config["input"]["transcription"] = {
            "model": input_audio_transcription_model,
        }

    session: dict[str, object] = {
        "type": "realtime",
        "output_modalities": ["audio"],
        "instructions": instructions,
        "audio": audio_config,
    }

    return {
        "type": "session.update",
        "session": session,
    }


def build_transcription_request(
    transcription_instructions: str,
    item_ids: list[str] | None = None,
) -> dict[str, object]:
    """Ask the SAME Realtime model for an out-of-band transcript of selected user turns.
       If item_ids is provided, the model will only consider the turns with the given IDs. You can use this to limit the session context window.
    """

    response: dict[str, object] = {
        "conversation": "none",  # <--- out-of-band
        "output_modalities": ["text"],
        "metadata": {"purpose": TRANSCRIPTION_PURPOSE},  # easier to identify in the logs
        "instructions": transcription_instructions,
    }

    if item_ids:
        response["input"] = [
            {"type": "item_reference", "id": item_id} for item_id in item_ids
        ]

    return {
        "type": "response.create",
        "response": response,
    }
```

# 6. 音訊串流：麥克風 → Realtime → 喇叭

接著定義：

- `encode_audio`：base64 helper
- `playback_audio`：用預設輸出裝置播放 assistant 音訊
- `send_audio_from_queue`：把緩衝的麥克風音訊送到 `input_audio_buffer`
- `stream_microphone_audio`：從麥克風擷取 PCM16 並餵進 queue


```python
def encode_audio(chunk: bytes) -> str:
    """Base64-encode a PCM audio chunk for WebSocket transport."""
    return base64.b64encode(chunk).decode("utf-8")


async def playback_audio(
    playback_queue: asyncio.Queue,
    stop_event: asyncio.Event,
) -> None:
    """Stream assistant audio back to the speakers in (near) real time."""

    try:
        with sd.RawOutputStream(
            samplerate=DEFAULT_SAMPLE_RATE,
            channels=1,
            dtype="int16",
        ) as stream:
            while not stop_event.is_set():
                chunk = await playback_queue.get()
                if chunk is None:
                    break
                try:
                    stream.write(chunk)
                except Exception as exc:
                    print(f"Audio playback error: {exc}", flush=True)
                    break
    except Exception as exc:
        print(f"Failed to open audio output stream: {exc}", flush=True)


async def send_audio_from_queue(
    ws: WebSocketClientProtocol,
    queue: asyncio.Queue[bytes | None],
    stop_event: asyncio.Event,
) -> None:
    """Push raw PCM chunks into input_audio_buffer via the WebSocket."""

    while not stop_event.is_set():
        chunk = await queue.get()
        if chunk is None:
            break
        encoded_chunk = encode_audio(chunk)
        message = {"type": "input_audio_buffer.append", "audio": encoded_chunk}
        await ws.send(json.dumps(message))

    if not ws.closed:
        commit_payload = {"type": "input_audio_buffer.commit"}
        await ws.send(json.dumps(commit_payload))


async def stream_microphone_audio(
    ws: WebSocketClientProtocol,
    stop_event: asyncio.Event,
    shared_state: dict,
    block_ms: int = DEFAULT_BLOCK_MS,
) -> None:
    """Capture live microphone audio and send it to the realtime session."""

    loop = asyncio.get_running_loop()
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    blocksize = int(DEFAULT_SAMPLE_RATE * (block_ms / 1000))

    def on_audio(indata, frames, time_info, status):  # type: ignore[override]
        """Capture a mic callback chunk and enqueue it unless the mic is muted."""
        if status:
            print(f"Microphone status: {status}", flush=True)
        # Simple echo protection: mute mic when assistant is talking
        if not stop_event.is_set() and not shared_state.get("mute_mic", False):
            data = bytes(indata)
            loop.call_soon_threadsafe(audio_queue.put_nowait, data)

    print(
        f"Streaming microphone audio at {DEFAULT_SAMPLE_RATE} Hz (mono). "
        "Speak naturally; server VAD will stop listening when you pause."
    )
    sender = asyncio.create_task(send_audio_from_queue(ws, audio_queue, stop_event))

    with sd.RawInputStream(
        samplerate=DEFAULT_SAMPLE_RATE,
        blocksize=blocksize,
        channels=1,
        dtype="int16",
        callback=on_audio,
    ):
        await stop_event.wait()

    await audio_queue.put(None)
    await sender
```

# 7. 擷取並比較逐字稿

下面的函式讓每個使用者 turn 產生**兩份逐字稿**：

- **Realtime 模型逐字稿**：來自我們的 out-of-band `response.create` 呼叫
- **內建 ASR 逐字稿**：來自標準轉錄模型（`input_audio_transcription_model`）

我們把兩者對齊後清楚地顯示在 terminal：

```text
=== User Turn (Realtime Transcript) ===
...

=== User Turn (Built-in ASR Transcript) ===
...
```


```python
def flush_pending_transcription_prints(shared_state: dict) -> None:
    """Whenever we've printed a realtime transcript, print the matching transcription-model output."""

    pending_prints: deque | None = shared_state.get("pending_transcription_prints")
    input_transcripts: deque | None = shared_state.get("input_transcripts")
    transcription_model_costs: deque | None = shared_state.get("transcription_model_costs")
    debug_usage_and_cost: bool = bool(shared_state.get("debug_usage_and_cost", False))

    if not pending_prints or not input_transcripts:
        return

    while pending_prints and input_transcripts:
        comparison_text = input_transcripts.popleft()
        pending_prints.popleft()
        print("=== User turn (Transcription model) ===")
        if comparison_text:
            print(comparison_text, flush=True)
        else:
            print("<not available>", flush=True)

        # After printing the transcription text, print any stored granular cost.
        cost_info = None
        if transcription_model_costs:
            cost_info = transcription_model_costs.popleft()

        if cost_info and debug_usage_and_cost:
            audio_input_cost = cost_info.get("audio_input_cost", 0.0)
            text_input_cost = cost_info.get("text_input_cost", 0.0)
            text_output_cost = cost_info.get("text_output_cost", 0.0)
            total_cost = cost_info.get("total_cost", 0.0)

            usage = cost_info.get("usage")
            if usage:
                print("[Transcription model usage]")
                print(json.dumps(usage, indent=2))

            print(
                "[Transcription model cost estimate] "
                f"audio_in=${audio_input_cost:.6f}, "
                f"text_in=${text_input_cost:.6f}, "
                f"text_out=${text_output_cost:.6f}, "
                f"total=${total_cost:.6f}",
                flush=True,
            )

        print()
```

# 8. 監聽 Realtime 事件

`listen_for_events` 負責驅動整個 session：

- 監看 `speech_started` / `speech_stopped` / `committed`
- only_last_user_turn == False 時，使用者 turn 結束（`input_audio_buffer.committed`）就送出 out-of-band 轉錄請求
- only_last_user_turn == True 時，使用者 turn 被加進對話（`conversation.item.added"`）才送出 out-of-band 轉錄請求
- 計算兩種轉錄方式的 token 用量與成本
- 把 assistant 音訊串流到播放 queue
- 依 `response_id` 緩衝文字 delta

```python
# Pricing constants (USD per 1M tokens). See https://platform.openai.com/pricing.
# gpt-4o-transcribe
GPT4O_TRANSCRIBE_AUDIO_INPUT_PRICE_PER_1M = 6.00
GPT4O_TRANSCRIBE_TEXT_INPUT_PRICE_PER_1M = 2.50
GPT4O_TRANSCRIBE_TEXT_OUTPUT_PRICE_PER_1M = 10.00

# gpt-realtime
REALTIME_TEXT_INPUT_PRICE_PER_1M = 4
REALTIME_TEXT_CACHED_INPUT_PRICE_PER_1M = 0.4
REALTIME_TEXT_OUTPUT_PRICE_PER_1M = 16.00
REALTIME_AUDIO_INPUT_PRICE_PER_1M = 32.00
REALTIME_AUDIO_CACHED_INPUT_PRICE_PER_1M = 0.40
REALTIME_AUDIO_OUTPUT_PRICE_PER_1M = 64.00

def _compute_transcription_model_cost(usage: dict | None) -> dict | None:
    if not usage:
        return None

    input_details = usage.get("input_token_details") or {}
    audio_input_tokens = input_details.get("audio_tokens") or 0
    text_input_tokens = input_details.get("text_tokens") or 0
    output_tokens = usage.get("output_tokens") or 0

    audio_input_cost = (
        audio_input_tokens * GPT4O_TRANSCRIBE_AUDIO_INPUT_PRICE_PER_1M
        / 1_000_000
    )
    text_input_cost = (
        text_input_tokens * GPT4O_TRANSCRIBE_TEXT_INPUT_PRICE_PER_1M
        / 1_000_000
    )
    text_output_cost = (
        output_tokens * GPT4O_TRANSCRIBE_TEXT_OUTPUT_PRICE_PER_1M
        / 1_000_000
    )
    total_cost = audio_input_cost + text_input_cost + text_output_cost

    return {
        "audio_input_cost": audio_input_cost,
        "text_input_cost": text_input_cost,
        "text_output_cost": text_output_cost,
        "total_cost": total_cost,
        "usage": usage,
    }

def _compute_realtime_oob_cost(usage: dict | None) -> dict | None:
    if not usage:
        return None

    input_details = usage.get("input_token_details") or {}
    output_details = usage.get("output_token_details") or {}
    cached_details = input_details.get("cached_tokens_details") or {}

    text_input_tokens = input_details.get("text_tokens") or 0
    cached_text_tokens = (
        cached_details.get("text_tokens")
        or input_details.get("cached_tokens")
        or 0
    )
    non_cached_text_input_tokens = max(text_input_tokens - cached_text_tokens, 0)

    audio_input_tokens = input_details.get("audio_tokens") or 0
    cached_audio_tokens = cached_details.get("audio_tokens") or 0
    non_cached_audio_input_tokens = max(audio_input_tokens - cached_audio_tokens, 0)

    text_output_tokens = output_details.get("text_tokens") or 0
    audio_output_tokens = output_details.get("audio_tokens") or 0

    text_input_cost = (
        non_cached_text_input_tokens * REALTIME_TEXT_INPUT_PRICE_PER_1M
        / 1_000_000
    )
    cached_text_input_cost = (
        cached_text_tokens * REALTIME_TEXT_CACHED_INPUT_PRICE_PER_1M
        / 1_000_000
    )
    audio_input_cost = (
        non_cached_audio_input_tokens * REALTIME_AUDIO_INPUT_PRICE_PER_1M
        / 1_000_000
    )
    cached_audio_input_cost = (
        cached_audio_tokens * REALTIME_AUDIO_CACHED_INPUT_PRICE_PER_1M
        / 1_000_000
    )
    text_output_cost = (
        text_output_tokens * REALTIME_TEXT_OUTPUT_PRICE_PER_1M
        / 1_000_000
    )
    audio_output_cost = (
        audio_output_tokens * REALTIME_AUDIO_OUTPUT_PRICE_PER_1M
        / 1_000_000
    )

    total_cost = (
        text_input_cost
        + cached_text_input_cost
        + audio_input_cost
        + cached_audio_input_cost
        + text_output_cost
        + audio_output_cost
    )

    return {
        "text_input_cost": text_input_cost,
        "cached_text_input_cost": cached_text_input_cost,
        "audio_input_cost": audio_input_cost,
        "cached_audio_input_cost": cached_audio_input_cost,
        "text_output_cost": text_output_cost,
        "audio_output_cost": audio_output_cost,
        "total_cost": total_cost,
        "usage": usage,
    }
```

```python
async def listen_for_events(
    ws: WebSocketClientProtocol,
    stop_event: asyncio.Event,
    transcription_instructions: str,
    max_turns: int | None,
    playback_queue: asyncio.Queue,
    shared_state: dict,
) -> None:
    """Print assistant text + transcripts and coordinate mic muting."""

    responses: dict[str, dict[str, bool]] = {}
    buffers: defaultdict[str, str] = defaultdict(str)
    transcription_model_buffers: defaultdict[str, str] = defaultdict(str)
    completed_main_responses = 0
    awaiting_transcription_prompt = False
    input_transcripts = shared_state.setdefault("input_transcripts", deque())
    pending_transcription_prints = shared_state.setdefault(
        "pending_transcription_prints", deque()
    )
    transcription_model_costs = shared_state.setdefault(
        "transcription_model_costs", deque()
    )
    debug_usage_and_cost: bool = bool(shared_state.get("debug_usage_and_cost", False))
    only_last_user_turn: bool = bool(shared_state.get("only_last_user_turn", False))
    last_user_audio_item_id: str | None = None

    async for raw in ws:
        if stop_event.is_set():
            break

        message = json.loads(raw)
        message_type = message.get("type")

        # --- User speech events -------------------------------------------------
        if message_type == "input_audio_buffer.speech_started":
            print("\n[client] Speech detected; streaming...", flush=True)
            awaiting_transcription_prompt = True

        elif message_type in INPUT_SPEECH_END_EVENT_TYPES:
            if message_type == "input_audio_buffer.speech_stopped":
                print("[client] Detected silence; preparing transcript...", flush=True)

            # Default behavior: trigger immediately after audio commit unless
            # only_last_user_turn requires waiting for conversation.item.added.
            if awaiting_transcription_prompt and not only_last_user_turn:
                request_payload = build_transcription_request(
                    transcription_instructions,
                    item_ids=None,
                )
                await ws.send(json.dumps(request_payload))
                awaiting_transcription_prompt = False

        elif message_type == "conversation.item.added":
            item = message.get("item") or {}
            item_id = item.get("id")
            role = item.get("role")
            status = item.get("status")
            content_blocks = item.get("content") or []
            has_user_audio = any(
                block.get("type") == "input_audio" for block in content_blocks
            )

            if (
                role == "user"
                and status == "completed"
                and has_user_audio
                and item_id
            ):
                last_user_audio_item_id = item_id

                if only_last_user_turn and awaiting_transcription_prompt:
                    request_payload = build_transcription_request(
                        transcription_instructions,
                        item_ids=[item_id],
                    )
                    await ws.send(json.dumps(request_payload))
                    awaiting_transcription_prompt = False

        # --- Built-in transcription model stream -------------------------------
        elif message_type in TRANSCRIPTION_DELTA_TYPES:
            buffer_id = message.get("buffer_id") or message.get("item_id") or "default"
            delta_text = (
                message.get("delta")
                or (message.get("transcription") or {}).get("text")
                or ""
            )
            if delta_text:
                transcription_model_buffers[buffer_id] += delta_text

        elif message_type in TRANSCRIPTION_COMPLETE_TYPES:
            buffer_id = message.get("buffer_id") or message.get("item_id") or "default"
            final_text = (
                (message.get("transcription") or {}).get("text")
                or message.get("transcript")
                or ""
            )
            if not final_text:
                final_text = transcription_model_buffers.pop(buffer_id, "").strip()
            else:
                transcription_model_buffers.pop(buffer_id, None)

            if not final_text:
                item = message.get("item")
                if item:
                    final_text = item.get("transcription")
                final_text = final_text or ""

            # Compute and store cost estimate for the transcription model (e.g., gpt-4o-transcribe).
            usage = message.get("usage") or {}
            cost_info = _compute_transcription_model_cost(usage)
            transcription_model_costs.append(cost_info)

            final_text = (final_text or "").strip()
            if final_text:
                input_transcripts.append(final_text)
                flush_pending_transcription_prints(shared_state)

        # --- Response lifecycle (Realtime model) --------------------------------
        elif message_type == "response.created":
            response = message.get("response", {})
            response_id = response.get("id")
            metadata = response.get("metadata") or {}
            responses[response_id] = {
                "is_transcription": metadata.get("purpose") == TRANSCRIPTION_PURPOSE,
                "done": False,
            }

        elif message_type in RESPONSE_AUDIO_DELTA_TYPES:
            response_id = message.get("response_id")
            if response_id is None:
                continue
            b64_audio = message.get("delta") or message.get("audio")
            if not b64_audio:
                continue
            try:
                audio_chunk = base64.b64decode(b64_audio)
            except Exception:
                continue

            if (
                response_id in responses
                and not responses[response_id]["is_transcription"]
            ):
                shared_state["mute_mic"] = True

            await playback_queue.put(audio_chunk)

        elif message_type in RESPONSE_TEXT_DELTA_TYPES:
            response_id = message.get("response_id")
            if response_id is None:
                continue
            buffers[response_id] += message.get("delta", "")
            

        elif message_type in RESPONSE_AUDIO_TRANSCRIPT_DELTA_TYPES:
            response_id = message.get("response_id")
            if response_id is None:
                continue
            buffers[response_id] += message.get("delta", "")        

        elif message_type == "response.done":
            response = message.get("response", {})
            response_id = response.get("id")
            if response_id is None:
                continue
            if response_id not in responses:
                responses[response_id] = {"is_transcription": False, "done": False}
            responses[response_id]["done"] = True

            is_transcription = responses[response_id]["is_transcription"]

            # For out-of-band transcription responses, compute usage-based cost estimates.
            usage = response.get("usage") or {}
            oob_cost_info: dict | None = None
            if usage and is_transcription:
                oob_cost_info = _compute_realtime_oob_cost(usage)

            text = buffers.get(response_id, "").strip()
            if text:
                if is_transcription:
                    print("\n=== User turn (Realtime transcript) ===")
                    print(text, flush=True)
                    if debug_usage_and_cost and oob_cost_info:
                        usage_for_print = oob_cost_info.get("usage")
                        if usage_for_print:
                            print("[Realtime out-of-band transcription usage]")
                            print(json.dumps(usage_for_print, indent=2))
                        print(
                            "[Realtime out-of-band transcription cost estimate] "
                            f"text_in=${oob_cost_info['text_input_cost']:.6f}, "
                            f"text_in_cached=${oob_cost_info['cached_text_input_cost']:.6f}, "
                            f"audio_in=${oob_cost_info['audio_input_cost']:.6f}, "
                            f"audio_in_cached=${oob_cost_info['cached_audio_input_cost']:.6f}, "
                            f"text_out=${oob_cost_info['text_output_cost']:.6f}, "
                            f"audio_out=${oob_cost_info['audio_output_cost']:.6f}, "
                            f"total=${oob_cost_info['total_cost']:.6f}",
                            flush=True,
                        )
                    print()
                    pending_transcription_prints.append(object())
                    flush_pending_transcription_prints(shared_state)
                else:
                    print("\n=== Assistant response ===")
                    print(text, flush=True)
                    print()

            if not is_transcription:
                shared_state["mute_mic"] = False
                completed_main_responses += 1

                if max_turns is not None and completed_main_responses >= max_turns:
                    stop_event.set()
                    break

        elif message_type == "error":
            print(f"Error from server: {message}")

        else:
            pass

        await asyncio.sleep(0)
```

# 9. 執行腳本

這一步執行的程式讓你看到 Realtime 模型轉錄和轉錄模型轉錄的對照。程式會：

- 載入設定和 prompt
- 建立 WebSocket 連線
- 啟動並行 task：
  - `listen_for_events`（處理進來的訊息）
  - `stream_microphone_audio`（送出麥克風音訊）
  - assistant 說話時把麥克風靜音
  - `playback_audio`（播放 assistant 回應）
  - 兩份逐字稿都回來後，印出 realtime 和轉錄模型的逐字稿。它用 shared_state 確保兩者都回來才印
- 持續執行直到你 `interrupt`

輸出看起來會像這樣：
```python
[client] Speech detected; streaming...
[client] Detected silence; preparing transcript...

=== User turn (Realtime transcript) ===
Hello.

=== User turn (Transcription model) ===
Hello


=== Assistant response ===
Hello, and thank you for calling. Let's start with your full name, please.
```


```python
async def run_realtime_session(
    api_key: str | None = None,
    server: str = "wss://api.openai.com/v1/realtime",
    model: str = DEFAULT_MODEL,
    voice: str = DEFAULT_VOICE,
    instructions: str = REALTIME_MODEL_PROMPT,
    transcription_instructions: str = REALTIME_MODEL_TRANSCRIPTION_PROMPT,
    input_audio_transcription_model: str | None = "gpt-4o-transcribe",
    silence_duration_ms: int = DEFAULT_SILENCE_DURATION_MS,
    prefix_padding_ms: int = DEFAULT_PREFIX_PADDING_MS,
    vad_threshold: float = 0.6,
    idle_timeout_ms: int | None = None,
    max_turns: int | None = None,
    timeout_seconds: int = 0,
    debug_usage_and_cost: bool = True,
    only_last_user_turn: bool = False,
) -> None:
    """Connect to the Realtime API, stream audio both ways, and print transcripts."""
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    ws_url = f"{server}?model={model}"
    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    session_update_payload = build_session_update(
        instructions=instructions,
        voice=voice,
        vad_threshold=vad_threshold,
        silence_duration_ms=silence_duration_ms,
        prefix_padding_ms=prefix_padding_ms,
        idle_timeout_ms=idle_timeout_ms,
        input_audio_transcription_model=input_audio_transcription_model,
    )
    stop_event = asyncio.Event()
    playback_queue: asyncio.Queue = asyncio.Queue()
    shared_state: dict = {
        "mute_mic": False,
        "input_transcripts": deque(),
        "pending_transcription_prints": deque(),
        "debug_usage_and_cost": debug_usage_and_cost,
        "only_last_user_turn": only_last_user_turn,
    }

    async with websockets.connect(
        ws_url, additional_headers=headers, max_size=None
    ) as ws:
        await ws.send(json.dumps(session_update_payload))

        listener_task = asyncio.create_task(
            listen_for_events(
                ws,
                stop_event=stop_event,
                transcription_instructions=transcription_instructions,
                max_turns=max_turns,
                playback_queue=playback_queue,
                shared_state=shared_state,
            )
        )
        mic_task = asyncio.create_task(
            stream_microphone_audio(ws, stop_event, shared_state=shared_state)
        )
        playback_task = asyncio.create_task(playback_audio(playback_queue, stop_event))

        try:
            if timeout_seconds and timeout_seconds > 0:
                await asyncio.wait_for(stop_event.wait(), timeout=timeout_seconds)
            else:
                await stop_event.wait()
        except asyncio.TimeoutError:
            print("Timed out waiting for responses; closing.")
        except asyncio.CancelledError:
            print("Session cancelled; closing.")
        finally:
            stop_event.set()
            await playback_queue.put(None)
            await ws.close()
            await asyncio.gather(
                listener_task, mic_task, playback_task, return_exceptions=True
            )
```

```python
await run_realtime_session(debug_usage_and_cost=False)
```

??? note "輸出"

    ```text
    Streaming microphone audio at 24000 Hz (mono). Speak naturally; server VAD will stop listening when you pause.

    [client] Speech detected; streaming...
    [client] Detected silence; preparing transcript...

    === User turn (Realtime transcript) ===
    Hello.

    === User turn (Transcription model) ===
    Hello


    === Assistant response ===
    Hello! Let's get started with your claim. Can you tell me your full name, please?


    [client] Speech detected; streaming...
    [client] Detected silence; preparing transcript...

    === User turn (Realtime transcript) ===
    My name is M I N H A J U L H O Q U E

    === User turn (Transcription model) ===
    My name is Minhajul Hoque.


    === Assistant response ===
    Thank you. Just to confirm, I heard your full name as Minhajul Hoque. Is that correct?


    [client] Speech detected; streaming...
    [client] Detected silence; preparing transcript...

    === User turn (Realtime transcript) ===
    Yep.

    === User turn (Transcription model) ===
    Yep.


    ... (省略 56 行)
    ```

從上面的例子可以看到：
- Realtime 模型的轉錄品質在各個 turn 都持平或更好。其中一個 turn，轉錄模型漏掉了「this is important.」，Realtime 轉錄則正確抓到
- Realtime 模型正確套用了保單號碼格式規則（XXXX-XXXX）
- 因為有整個 session 的 context，包括我先前把名字拼出來的 turn，assistant 再問一次名字時，Realtime 模型能正確轉錄我的名字，轉錄模型則出錯（例如「Minhaj ul Haq」）

## 含成本計算的範例

不同的使用者音訊轉錄方式，價差很大。GPT-4o-Transcribe 是最划算的做法：只收原始音訊輸入和少量文字輸出，每個 turn 的逐字稿只要零點幾美分。相較之下，用 Realtime 模型做 out-of-band 轉錄比較貴。如果只用 Realtime 轉錄最新一輪使用者 turn，通常比 GPT-4o-Transcribe 貴約 3 到 5 倍。如果每次轉錄請求都帶完整 session context，成本會升到約 16 到 20 倍。原因是每個送給 Realtime 模型的請求都要用較高的價格重新處理整個 session context，而且對話越長成本越高。

### 轉錄完整 session context 的成本
我們先看一個用完整 session context 做 realtime out-of-band 轉錄的例子：

```python
await run_realtime_session(debug_usage_and_cost=True)
```

??? note "輸出"

    ```text
    Streaming microphone audio at 24000 Hz (mono). Speak naturally; server VAD will stop listening when you pause.

    [client] Speech detected; streaming...
    [client] Detected silence; preparing transcript...
    conversation.item.added: {'id': 'item_Cfpt8RCQdpsNsz2OZ4rxQ', 'type': 'message', 'status': 'completed', 'role': 'user', 'content': [{'type': 'input_audio', 'transcript': None}]}
    conversation.item.added: {'id': 'item_Cfpt9JS3PCvlCxoO15mLt', 'type': 'message', 'status': 'in_progress', 'role': 'assistant', 'content': []}

    === User turn (Realtime transcript) ===
    Hello. How can I help you today?
    [Realtime out-of-band transcription usage]
    {
      "total_tokens": 1841,
      "input_tokens": 1830,
      "output_tokens": 11,
      "input_token_details": {
        "text_tokens": 1830,
        "audio_tokens": 0,
        "image_tokens": 0,
        "cached_tokens": 0,
        "cached_tokens_details": {
          "text_tokens": 0,
          "audio_tokens": 0,
          "image_tokens": 0
        }
      },
      "output_token_details": {
        "text_tokens": 11,
        "audio_tokens": 0
      }
    }
    [Realtime out-of-band transcription cost estimate] text_in=$0.007320, text_in_cached=$0.000000, audio_in=$0.000000, audio_in_cached=$0.000000, text_out=$0.000176, audio_out=$0.000000, total=$0.007496

    === User turn (Transcription model) ===
    Hello
    [Transcription model usage]
    {
      "type": "tokens",
      "total_tokens": 19,
      "input_tokens": 16,
      "input_token_details": {
    ... (省略 388 行)
    ```

#### 轉錄成本比較

##### 成本摘要

* **Realtime Out-of-Band (OOB)：** 總共 $0.040974（每 turn 約 $0.006829）
* **Dedicated Transcription：** 總共 $0.002114（每 turn 約 $0.000352）
* **用完整 session context 時，OOB 約貴 19 倍**

##### 考量

* **快取：** 因為這些對話很短，除了最初的 system prompt 之外，快取幫助不大
* **轉錄 system prompt：** 轉錄模型用的是極簡的 system prompt，所以實際輸入成本通常會更高

##### 建議的省錢策略

* **把轉錄限制在最近幾個 turn：** 縮小音訊/文字 context 能大幅降低 OOB 轉錄成本

##### 了解快取行為

* 要讓快取有效，prompt instructions 要穩定（通常要 1,024 token 以上）
* OOB 和主 assistant session 用不同的 instructions prompt，會各自有獨立的快取

### 只轉錄最新一輪的成本
可以用 input item_references 把轉錄限制在最新一輪使用者 turn，像這樣：
```python
    if item_ids:
        response["input"] = [
            {"type": "item_reference", "id": item_id} for item_id in item_ids
        ]

    return {
        "type": "response.create",
        "response": response,
    }
```

只轉錄最近一輪使用者 turn，會限制送給模型的 session context，成本因此降低。但這個做法有取捨：模型看不到先前的對話歷史，就無法靠它消除歧義或修正錯誤（例如正確回想先前提到的使用者名稱）。另外，因為你每次都在更換被參照的 input，幾乎享受不到快取的好處，cache prefix 每個 turn 都在變，沒辦法累積可重用的 context。

接著看第二個例子，只用最近一輪使用者音訊做 realtime out-of-band 轉錄：

```python
await run_realtime_session(debug_usage_and_cost=True, only_last_user_turn=True)
```

??? note "輸出"

    ```text
    Streaming microphone audio at 24000 Hz (mono). Speak naturally; server VAD will stop listening when you pause.

    [client] Speech detected; streaming...
    [client] Detected silence; preparing transcript...

    === User turn (Realtime transcript) ===
    Hello.
    [Realtime out-of-band transcription usage]
    {
      "total_tokens": 1813,
      "input_tokens": 1809,
      "output_tokens": 4,
      "input_token_details": {
        "text_tokens": 1809,
        "audio_tokens": 0,
        "image_tokens": 0,
        "cached_tokens": 0,
        "cached_tokens_details": {
          "text_tokens": 0,
          "audio_tokens": 0,
          "image_tokens": 0
        }
      },
      "output_token_details": {
        "text_tokens": 4,
        "audio_tokens": 0
      }
    }
    [Realtime out-of-band transcription cost estimate] text_in=$0.007236, text_in_cached=$0.000000, audio_in=$0.000000, audio_in_cached=$0.000000, text_out=$0.000064, audio_out=$0.000000, total=$0.007300

    === User turn (Transcription model) ===
    Hello
    [Transcription model usage]
    {
      "type": "tokens",
      "total_tokens": 17,
      "input_tokens": 14,
      "input_token_details": {
        "text_tokens": 0,
        "audio_tokens": 14
    ... (省略 250 行)
    ```

#### 成本分析摘要

Realtime Out-of-Band 轉錄（OOB）

* **總成本：** $0.013354
* **每 turn 平均：** 約 $0.001908

Dedicated 轉錄模型

* **總成本：** $0.002630
* **每 turn 平均：** 約 $0.000376


成本差異

* **用 OOB 的額外成本：** **+$0.010724**
* **成本倍數：** OOB 比 dedicated 轉錄模型貴約 **5 倍**

這個做法比用完整 session context 便宜很多。你要評估自己的情境，決定一般轉錄、帶完整 context 的 out-of-band 轉錄，還是只轉錄最新一輪，哪個最適合。也可以折衷，例如只在輸入裡帶最後 N 個 turn。


# 結論

如果有以下情況，可以考慮 **out-of-band 轉錄**：

* 就算優化過轉錄模型的 prompt，逐字稿還是不可靠
* 你需要更可靠、更好控制的轉錄方式
* 目前的逐字稿沒辦法正確正規化實體（entity），造成下游問題

也要記得這些取捨：
- 成本：out-of-band（OOB）轉錄比較貴。確定多出來的花費，對你一般的 session 長度和業務需求來說划算
- 複雜度：實作 OOB 轉錄需要額外的工程投入，才能把各個環節正確接起來。只有在好處對你的情境很重要時才選這個做法

如果決定採用這個方法，請確保：

* 正確設定轉錄的觸發點，確保它在音訊 commit 之後才啟動
* 仔細迭代並調整 prompt，讓它貼近你的情境和需求

## 文件：
- https://platform.openai.com/docs/guides/realtime-conversations#create-responses-outside-the-default-conversation
- https://platform.openai.com/docs/api-reference/realtime-client-events/response/create#realtime_client_events-response-create-response-conversation
- https://platform.openai.com/docs/api-reference/realtime-client-events/response/create#realtime_client_events-response-create-response-output_modalities

## 重點整理

- out-of-band 轉錄就是在同一條 WebSocket 上多送一個 `response.create`，用 `conversation: "none"` 不污染主對話，用 `output_modalities: ["text"]` 只拿文字
- 轉錄和回覆用同一個模型，可以減少兩者對不上的情況，也能吃到整個 session 的 context
- 逐字稿品質的提升要付成本：帶完整 context 約貴 16 到 20 倍，只帶最新一輪約貴 3 到 5 倍
- 轉錄 prompt 可以自己調整，Realtime 模型比轉錄模型更會遵循 instructions
- 觸發時機要放在音訊 commit 之後，而且只在品質要求高、值得多花錢時才用

## 練習

1. 把轉錄 prompt 裡的保單號碼格式規則拿掉，改成你自己想要的格式規則（例如電話號碼），用麥克風唸一次看逐字稿有沒有照做。
2. 在 `response.create` 的 `conversation: "none"` 之外，把 `output_modalities` 的用途改成請模型輸出這一輪的簡短摘要，而不是逐字稿，觀察結果。
3. 用 input item_references 只轉錄最新一輪，再改成保留最近 N 個 turn，比較兩種做法的成本和轉錄品質差異。
