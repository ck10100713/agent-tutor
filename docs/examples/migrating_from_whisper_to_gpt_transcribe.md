---
translated: true
source: examples/migrating_from_whisper_to_gpt_transcribe.ipynb
---
# Migrate from Whisper to GPT-Transcribe and GPT-Live-Transcribe

> 原文：[examples/migrating_from_whisper_to_gpt_transcribe.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/migrating_from_whisper_to_gpt_transcribe.ipynb)

用前後對照的範例，把現有的 Whisper 整合遷移到 GPT-Transcribe 和 GPT-Live-Transcribe，涵蓋檔案、串流和 Realtime 轉寫。

## 這篇在做什麼

說明怎麼把原本用 `whisper-1` 或 `gpt-realtime-whisper` 的轉寫程式，換成新的 `gpt-transcribe` 和 `gpt-live-transcribe`。每個情境都有 Before 和 After 的程式碼，並列出要注意的地方。

## 學完你會

- 依情境（錄好的檔案、即時字幕、手動 commit 的 Realtime turn）選對模型和遷移路徑。
- 把 `language` 改成 `languages` 陣列，並用 `prompt` 和 `keywords` 提供上下文。
- 處理新模型的 JSON 輸出、串流事件和 `languages: []` 這種偵測語言結果。

## 開跑前

- Python 3.11 以上，並安裝 OpenAI Python SDK。
- 設好 `OPENAI_API_KEY` 環境變數。
- 準備一個錄好的檔案 `meeting.wav`，或把 `audio_path` 改成你自己的檔案。
- 帳號要能使用範例裡的轉寫模型。


## Overview

OpenAI 新的轉寫模型給現有 Whisper 使用者兩條專注的升級路徑。GPT-Transcribe（`gpt-transcribe`）設計用來準確轉寫已完成的音訊，也就是上傳的檔案。GPT-Live-Transcribe（`gpt-live-transcribe`）則是為低延遲、持續串流的轉寫設計。

整體來說，API endpoint 沒變。檔案請求繼續用 POST /v1/audio/transcriptions。Realtime 整合繼續設定 transcription session 並處理轉寫事件。不同的是支援的請求欄位、輸出格式，以及上下文和多語言的 hint。

### 不變的部分

- 檔案轉寫繼續用現有的 Audio API transcription endpoint。
- Realtime 轉寫繼續用現有的 Realtime transcription session、WebSocket 或 WebRTC 傳輸，以及轉寫事件。
- 應用還是提供音訊、接收轉寫文字，並處理 API 或連線錯誤。

### 會變的部分

- 已完成的檔案、串流的檔案逐字稿、或是 commit 過的 Realtime turn，用 `gpt-transcribe`。
- 持續串流、低延遲的即時轉寫，用 `gpt-live-transcribe`。
- 把舊的 `language` hint 換成新模型的 `languages` 陣列。
- 用 `prompt` 放自由格式的上下文，用 `keywords` 放音訊中預期會出現的字面詞彙。
- GPT-Transcribe 會輸出偵測到的語言，要處理，包括空的 languages 陣列。

## 1. 選擇你的遷移路徑

- 錄好的會議、通話或上傳的音訊：在 POST /v1/audio/transcriptions 上，把 `whisper-1` 遷移到 `gpt-transcribe`。
- 即時字幕或持續進來的麥克風音訊：在 Realtime transcription session 裡，把 `gpt-realtime-whisper` 遷移到 `gpt-live-transcribe`。
- 手動 commit 音訊 turn 之後要更高準確度的轉寫：在 WebSocket 的 Realtime transcription session 裡用 `gpt-transcribe`。
即時音訊和串流輸出是兩個獨立的決定。已完成的檔案可以產生串流的逐字稿事件，Realtime session 也可以等音訊 turn 被 commit 之後才產生 delta。

## 2. 遷移錄好的音訊

最小的檔案遷移會保留 endpoint、SDK 呼叫和檔案上傳。把 model 識別名稱換掉，然後處理 JSON 轉寫回應。


### 前置需求

- Python 3.11 或更新版本。
- OpenAI Python SDK：`python -m pip install --upgrade openai`。
- 一個 `OPENAI_API_KEY` 環境變數。
- 一個錄好的檔案 `meeting.wav`，或把 `audio_path` 改成指向你自己的檔案。
- 有權限使用範例中的轉寫模型。

檔案範例會發出真實的 API 請求。Realtime 範例只是組出 session payload。`gpt-live-transcribe` 用 WebSocket 或 WebRTC，commit-turn 的 `gpt-transcribe` 用 WebSocket。


```python
import json
from pathlib import Path

from openai import OpenAI

client = OpenAI()
audio_path = Path("meeting.wav")
```

**Before：Whisper 檔案轉寫**


```python
with audio_path.open("rb") as audio:
    before = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio,
    )

print(before.text)
```

**After：GPT-Transcribe**


```python
with audio_path.open("rb") as audio:
    after = client.audio.transcriptions.create(
        model="gpt-transcribe",
        file=audio,
        response_format="json",
    )

print(after.text)
```

**該做與不該做**

- 注意新模型回傳 JSON。如果現有應用要求 `text`、`verbose_json`、`srt` 或 `vtt`，不要假設同樣的 response_format 還有效。這些格式請繼續用 Whisper，或是明確建立並測試你的應用需要的下游轉換。

## 3. 更新語言 hint 和領域上下文

舊的 Whisper 整合通常只送單一個 `language` 值，並把領域詞彙放在自由格式的 prompt 裡。新模型可以接受多個預期輸入語言，也把結構化的 keyword hint 和一般 prompt 分開。


**Before：單一語言的 Whisper 請求**


```python
from openai import OpenAI

client = OpenAI()

with open("meeting.wav", "rb") as audio:
    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio,
        language="en",
        prompt="A support call about AC-42.",
    )

print(result.text)
```

**After：多語言的 GPT-Transcribe 請求**


```python
from openai import OpenAI

client = OpenAI()

with open("meeting.wav", "rb") as audio:
    result = client.audio.transcriptions.create(
        model="gpt-transcribe",
        file=audio,
        prompt="A customer support call about billing.",
        extra_body={
            "keywords": ["AC-42", "Premium Plus"],
            "languages": ["en", "fr"],
        },
    )

print(result.text)
```

**該做與不該做**

- 用 `prompt` 描述錄音的主題或場景。
- 用 `keywords` 放字面上的產品名稱、藥品名稱、帳號識別碼，或其他實際可能被說出來的領域詞彙。
- 用 `languages` 表示預期會出現的口說語言。
- 不要同時送 `language` 和 `languages`。
- 發請求前先驗證 keyword 輸入：每個 keyword 必須是單行的字面值，且不能包含 `<`、`>`、carriage return 或 line feed。不合法的 keyword 輸入會讓整個請求或 session update 被拒絕。

## 4. 串流已完成檔案的轉寫

串流指的是轉寫輸出，不是音訊輸入。應用先提供一個錄好的檔案，API 再邊轉寫邊串流出文字。


**Before：會 block 的 Whisper 檔案請求**


```python
with audio_path.open("rb") as audio:
    before = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio,
    )

print(before.text)

# whisper-1 does not provide transcript.text.delta events.
```

**After：串流的 GPT-Transcribe 檔案請求**


```python
with audio_path.open("rb") as audio:
    stream = client.audio.transcriptions.create(
        model="gpt-transcribe",
        file=audio,
        stream=True,
    )

    for event in stream:
        if event.type == "transcript.text.delta":
            print(event.delta, end="", flush=True)
        elif event.type == "transcript.text.done":
            print("\nFinal:", event.text)
```

**該做與不該做**

- 用轉寫事件區分進行中和已完成的逐字稿。收到 `transcript.text.delta` 事件就更新你的逐字稿或進度 UI，再用 `transcript.text.done` 把逐字稿標為最終版。
- 不要把檔案串流說成即時音訊擷取：檔案必須已經存在。

## 5. 遷移持續的即時轉寫

即時字幕的流程要保留 Realtime 連線和 transcription-session 的架構。改轉寫模型，並更新模型專屬的設定。


**Before：GPT-Realtime-Whisper**


```python
legacy_realtime_session = json.loads(
    r'''
{
  "type": "session.update",
  "session": {
    "type": "transcription",
    "audio": {
      "input": {
        "transcription": {
          "model": "gpt-realtime-whisper",
          "language": "en"
        },
        "turn_detection": null
      }
    }
  }
}
'''
)

print(json.dumps(legacy_realtime_session, indent=2))
```

**After：GPT-Live-Transcribe**


```python
live_transcription_session = json.loads(
    r'''
{
  "type": "session.update",
  "session": {
    "type": "transcription",
    "audio": {
      "input": {
        "transcription": {
          "model": "gpt-live-transcribe",
          "prompt": "A support call about a plan.",
          "keywords": ["AC-42", "Premium Plus"],
          "languages": ["en", "fr"],
          "delay": "low"
        },
        "turn_detection": null
      }
    }
  }
}
'''
)

print(json.dumps(live_transcription_session, indent=2))
```

**該做與不該做**

- 繼續處理 `conversation.item.input_audio_transcription.delta` 和 `conversation.item.input_audio_transcription.completed`。
- 保留現有以 item_id 為基礎的對帳邏輯。
- 用模型的 `delay` 設定，在更快的 partial 逐字稿和更準確的最終逐字稿之間取捨。
- 保留現有的 WebSocket 或 WebRTC 傳輸，Realtime 轉寫兩種都支援。

## 6. 在 committed-turn 的 Realtime session 使用 GPT-Transcribe

GPT-Transcribe 不只能用在上傳的檔案。如果你的應用需要在手動 commit 音訊 turn 之後有更高準確度的轉寫，可以在 WebSocket 的 Realtime session 裡，把它當作輸入轉寫模型。


**Before：舊的即時轉寫 session**


```python
legacy_live_session = json.loads(
    r'''
{
  "type": "session.update",
  "session": {
    "type": "transcription",
    "audio": {
      "input": {
        "transcription": {
          "model": "gpt-realtime-whisper",
          "language": "en"
        }
      }
    }
  }
}
'''
)

print(json.dumps(legacy_live_session, indent=2))
```

**After：committed-turn 的 GPT-Transcribe session**


```python
committed_turn_session = json.loads(
    r'''
{
  "type": "session.update",
  "session": {
    "type": "transcription",
    "audio": {
      "input": {
        "transcription": {
          "model": "gpt-transcribe",
          "prompt": "A customer support call.",
          "keywords": ["AC-42"],
          "languages": ["en", "fr"]
        },
        "turn_detection": null
      }
    }
  }
}
'''
)

print(json.dumps(committed_turn_session, indent=2))
```

**該做與不該做**

- 先把音訊 append 到 input buffer，再送 `input_audio_buffer.commit`。轉寫是對每個 commit 的音訊區塊進行，不是持續的即時字幕。GPT-Transcribe 可能會在該區塊的 completed 事件之前，先送出逐字稿的 delta 事件。

## 7. 更新回應和事件處理

GPT-Transcribe 可以在完成的檔案結果和 Realtime 結果裡，附上偵測到的輸入語言。這些是模型回傳的預測，不是把呼叫者給的語言 hint 再講一遍。


**Before：沒有語言預測的逐字稿**


```python
legacy_transcription_response = json.loads(
    r'''
{
  "text": "Bonjour, pouvez-vous m'entendre ?"
}
'''
)

print(json.dumps(legacy_transcription_response, indent=2))
```

**After：GPT-Transcribe 偵測語言的回應**


```python
detected_language_response = json.loads(
    r'''
{
  "text": "Bonjour, pouvez-vous m'entendre ?",
  "languages": [
    { "code": "fr" }
  ]
}
'''
)

print(json.dumps(detected_language_response, indent=2))

language_codes = [
    item["code"]
    for item in detected_language_response.get("languages", [])
]
print("Detected languages:", language_codes)
```

**該做與不該做**

- 把 `languages: []` 當成合法結果處理，這代表模型無法做出可靠的預測。
- 不要推論成沒人說話、請求失敗，或是回傳了一個合成的 `unknown` 語言。GPT-Live-Transcribe 在初版 contract 裡不會回傳偵測語言的預測。
- Realtime 要檢查 `conversation.item.input_audio_transcription.completed`，GPT-Transcribe 可能會把同樣的語言 metadata 附在這個事件上。

## 8. 切換前先檢查相容性

有些現有的轉寫功能，在 `gpt-transcribe` 或 `gpt-live-transcribe` 裡沒有直接可替換的對應。

- 字幕：如果整合依賴原生 SRT 或 VTT 輸出，保留 `whisper-1`。
- 時間戳：保留明確支援 word 或 segment 時間戳的模型和 response format。
- 翻譯：如果應用要把音訊翻成英文，保留 `/v1/audio/translations` 搭配支援翻譯的模型。
- 說話者分離（diarization）：如果應用需要說話者標籤，在 `/v1/audio/transcriptions` 用 `gpt-4o-transcribe-diarize`，並設 `response_format: "diarized_json"`。超過 30 秒的錄音要設 `chunking_strategy: "auto"`。這個模型不支援 Realtime API。

## 9. 切換前後做評估

兩個模型都用同一批有代表性的音訊片段。比較三者：baseline、直接只換模型的版本，以及加上新上下文欄位的版本。這樣能分清楚進步是來自模型本身，還是來自 prompt、keywords 或語言 hint。

### 評估轉寫品質

- 在有代表性的錄音上的整體 word error rate。
- 名字、產品名稱、藥品名稱、帳號識別碼、數字和 email 地址的完全比對準確率。
- 口音、背景噪音、電話音訊和短句的表現。
- 切換語言和混合語言說話時的準確度。
- Keyword 幻覺：確認逐字稿沒有插入實際沒被說出來的 hint 詞。
- 最終逐字稿的完整度，以及預期的語言 metadata。

### 評估串流和營運行為

- 到第一個逐字稿 delta 的時間，檔案串流和即時音訊要分開報告。
- 從明確 commit turn 到最終逐字稿的時間。
- 延遲的中位數和尾端，包括 p95 或團隊現有的 service-level 門檻。
- partial 逐字稿文字在完成前變動的頻率。
- 重疊 turn 之間的事件順序和 item_id 對帳。
- 重連、重試、空音訊和 session 中斷時的行為。
- 實際的請求價格和 production rate limit，以正式發布的資料為準。

## 常見的遷移錯誤

- 只因為 `gpt-transcribe` 針對已完成音訊優化，就把它當成跟 Realtime 不相容。
- 因為處理要在 commit 之後才開始，就說 GPT-Transcribe 無法串流。
- 以為檔案的串流輸出代表 endpoint 能接受持續的麥克風串流。
- 同時送舊的 `language` 和新模型的 `languages`。
- 對不支援的模型，期待它有字幕格式、時間戳、說話者標籤或偵測語言的輸出。
- 把空的偵測語言陣列當成 API 錯誤。
- 把 keywords 強塞進逐字稿，而不是把它們當作 hint。
- 以為每個 Realtime 模型都支援同樣的 voice activity detection 和延遲控制。


## 相關資源

- [Speech to text](https://developers.openai.com/api/docs/guides/speech-to-text)
- [Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
- [GPT-4o Transcribe Diarize](https://developers.openai.com/api/docs/models/gpt-4o-transcribe-diarize)


## 重點整理

- 遷移要先分情境：錄好的檔案用 `gpt-transcribe`，持續即時字幕用 `gpt-live-transcribe`，手動 commit 的 turn 用 Realtime 裡的 `gpt-transcribe`。
- 「串流輸出」和「即時音訊輸入」是兩件事，檔案也能串流輸出逐字稿。
- 語言和上下文的欄位變了：`language` 換成 `languages`，領域詞彙拆到 `keywords`，而且 `language` 跟 `languages` 不能一起送。
- 新模型不是全能替代品，字幕、時間戳、翻譯、diarization 要看情況保留舊模型或換別的模型。
- 遷移完要用同一批音訊做前後比較，才分得出進步來自模型還是來自新增的 hint。

## 練習

1. 把 Section 2 的 Whisper 檔案轉寫改成 `gpt-transcribe`，確認回應格式是 JSON，再檢查你的程式有沒有仰賴 `text` 或 `srt` 格式。
2. 在 Section 3 的請求裡，把單一 `language` 改成 `languages` 陣列，並加入兩三個 `keywords`，用一份有專有名詞的錄音比較前後差異。
3. 照 Section 7 的做法，在處理 completed 事件的程式裡，加上對 `languages: []` 的處理分支，並用一段幾乎沒有人聲的音訊測試。
