---
translated: true
source: examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.ipynb
---
# 用音訊 diarization 建一條 speaker-aware 的會議分析 pipeline

> 原文：[examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.ipynb)

建一條接近正式環境的參考 pipeline，把錄音變成標好講者的逐字稿、摘要、決議、風險和後續行動。

## 這篇在做什麼

用 `gpt-4o-transcribe-diarize` 把會議錄音轉成標好講者（speaker）的 segment，整理成帶有固定 segment ID 的 JSON 和 Markdown，再用 structured outputs 抽出會議摘要、決議、風險、行動項目，每一項都附上指向逐字稿的證據引用。最後還會跑本地的 guardrail 檢查，決定哪些輸出要送人工審核。

預設的 cell 用一份合成的 diarized 逐字稿，不需要 API key 就能跑完。真的丟音檔去呼叫 API 是要自己打開的選項。

## 學完你會

- 用 `response_format="diarized_json"` 呼叫 Transcriptions API，並用 reference clip 把講者對應到真實名字。
- 設計一個要求 `evidence_refs`（segment ID 加引用原文）的 strict structured output schema，讓每個抽出來的項目都能機械式驗證。
- 寫出 guardrail 和評估：redaction、證據驗證、人工審核路由、deterministic eval 和可選的 LLM-as-judge。

## 開跑前

- Python 3.10 以上。
- 真的跑音檔需要 `OPENAI_API_KEY` 環境變數，會產生 API 費用。預設的合成 demo 不用。
- 音檔要 25 MB 以下，格式是 `mp3`、`mp4`、`mpeg`、`mpga`、`m4a`、`wav`、`webm`。
- 可選：最多 4 段短的單人 reference clip。

很多組織本來就會錄下重要的對話，但光有逐字稿通常不夠做可靠的後續追蹤。缺的那一層是講者歸屬：誰提出疑慮、誰做出承諾、證據在錄音的哪個位置。有了 speaker-aware 的逐字稿，你可以把客戶需求跟業務的後續承諾分開、把結構化的證據引用跟行動項目放在一起，並且在內容進到 CRM、ticket 系統或知識庫之前，先把敏感的承諾送進審核流程。

只要下游流程取決於「誰說了什麼」，這個模式就有用：

- 業務探索和方案諮詢：把客戶需求、業務承諾、決策標準、阻礙和下一步連同證據一起記下來。
- 客戶成功和客戶管理：把 QBR、續約電話和 onboarding 會議，變成有出處的風險、產品需求和後續計畫。
- 客服升級和事件檢討：在建 ticket 或寫 postmortem 之前，保留時間線、回報的症狀、負責人的承諾和未解問題。
- 招募和面試流程：摘要候選人或面試官的回饋，同時讓引用的話對上正確的講者。
- 受監管或高風險的審查：在儲存醫療、金融、法律或法遵相關對話的筆記前，加上 redaction、證據檢查和人工審核。

對營收團隊來說，價值通常不是多生出一份摘要，而是減少對話和系統紀錄（system of record）之間的資訊漏失。這樣的 pipeline 可以幫團隊更快記下能直接進 CRM 的下一步、更早發現續約或擴展的風險、留住預測更新背後的證據，並且用有出處的例子來輔導業務或客服，而不是靠軼事式的筆記。目標不是把判斷自動化掉，而是讓交接、審核和後續行動更完整、可稽核。

這個 notebook 示範如何用 OpenAI 的音訊 diarization 建一條接近正式環境、通話後處理的會議分析 pipeline。流程如下：

1. 接收一個會議錄音檔。
2. 可選：用短的 reference clip 對應已知講者。
3. 用 `response_format="diarized_json"` 呼叫 `gpt-4o-transcribe-diarize`。
4. 把標好講者的 segment 整理成帶有固定 segment ID 的 JSON 和 Markdown。
5. 用 structured outputs 抽出會議摘要、決議、風險、明確提出的問題、建議的後續動作、行動項目、證據引用和後續 email 草稿。
6. 寫出可供審閱的產出檔和本地 guardrail 報告。

預設的 cell 用合成的 diarized 逐字稿，不需要 API key。真實音檔的呼叫要自己開，所以整份 notebook 從頭到尾跑一遍都很安全。


## 架構

![Architecture diagram](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/audio/speaker_aware_meeting_intelligence/images/architecture.svg)

| Layer | Responsibility | Output |
| --- | --- | --- |
| Audio intake | Accept a call recording and optional known-speaker clips. | `meeting.wav`, `Agent=agent.wav` |
| Pipeline runner | Validate inputs, encode references as data URLs, call OpenAI, and write artifacts. | Run metadata and output directory |
| Diarization | Call `gpt-4o-transcribe-diarize` with `response_format="diarized_json"` and `chunking_strategy="auto"`. | Speaker-labeled segments |
| Transcript normalization | Convert API output into consistent JSON and Markdown with stable segment IDs. | `transcript_segments.json`, `speaker_labeled_transcript.md` |
| Meeting intelligence | Extract summary, decisions, actions, risks, explicit questions, suggested follow-ups, quotes, and follow-up email with structured evidence references. | `meeting_intelligence.json`, `meeting_brief.md` |
| Guardrails and review gate | Redact sensitive fields, verify evidence references, optionally moderate content, and route risky outputs for review. | `guardrail_report.json` |

這個設計刻意採用 request-based 的做法。如果是即時語音體驗、瀏覽器擷取或電話串流，Realtime API 比較適合。要做可留存的通話後 diarization，這個模式用 Transcriptions API，再對標好講者的逐字稿跑 structured extraction。


## 為什麼 speaker-aware 的逐字稿很重要

會議分析的第一版常常是「把逐字稿丟給模型做摘要」。做 demo 沒問題，但放到客戶流程裡就會出事，因為它丟掉了誰說了什麼。客戶可能提出一項需求，業務可能做出一項承諾，而主管需要看得出兩者的差別。

有了 speaker-aware 的 diarization，應用程式的其他部分結構會好很多：

- 行動項目可以帶上做出承諾的講者。
- 風險可以直接引用客戶說的那句疑慮。
- 後續 email 草稿不會把業務的承諾寫成客戶的。
- QA 審核者可以用 segment ID 和時間戳抽查講者歸屬。
- CRM 同步作業可以存可機械驗證的證據，而不是看不透的摘要。


## 安全與 guardrail

會議分析應該當成處理敏感資料的流程，而不只是轉錄或摘要的任務。原始錄音可能包含客戶名稱、商業條款、客服細節、健康或財務資訊，還有內部策略。Speaker reference clip 也可能很敏感，因為它綁著某個人的聲音。一旦 pipeline 把音訊變成結構化輸出，這些輸出可能流進 CRM 紀錄、客服 ticket、客戶計畫、dashboard 或審核佇列。

當輸出會影響商業流程時，安全和 guardrail 最重要。業務通話的摘要可能記下價格或合約承諾。客服升級可能包含影響正式環境的事故或客戶憑證。招募的討論可能含有候選人的回饋。受監管產業的會議可能包含需要保留期限、存取控制或 redaction 政策的資料。對這些流程，最安全的做法是：盡量減少原始音訊的保存、適當時對敏感內容做 redaction、要求輸出附帶證據，並且在寫入下游之前，把有風險或信心低的輸出送給人工審核。

內附的 regex redaction 只是示意：它只遮蔽基本的 email 和電話格式，不是完整的 PII 或 DLP 系統。對於姓名、地址、帳號識別碼、憑證、健康資料、財務資料或受監管流程，請使用符合政策的 PII/DLP 偵測器，並且在寫入下游前保留人工審核關卡。

在 structured extraction 這一步，notebook 對 Responses API 的呼叫設了 `store=False`，所以產生的會議分析回應不會被存成應用程式狀態。`store=False` 是請求層級很實用的控制，但它跟替整個組織或專案啟用 Zero Data Retention 不一樣。如果你的流程需要更嚴格的保留保證，請看 OpenAI 的 [data controls 文件](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint)，確認適合你情境的保留設定。

| Risk | Guardrail |
| --- | --- |
| Recording or speaker-reference misuse | Require consent and policy approval before recording, diarization, or reference-clip use. Treat speaker references as sensitive biometric-adjacent data. |
| Over-retention of raw audio | Do not save the raw transcription response by default. Keep raw audio and reference clips only as long as needed. Encrypt and restrict access if retained. |
| Prompt injection inside transcripts | Treat transcript text as untrusted evidence. Keep instructions in the system message and require the model to use only transcript-backed facts. |
| Unsupported action items or decisions | Use strict structured outputs and require evidence references that point to real segment IDs and quotes. |
| Sensitive content in generated notes | Run redaction before summarization where possible, then run post-generation checks on the transcript and brief. |
| Harmful or policy-sensitive content | Optionally call the Moderation API with `omni-moderation-latest` on transcript text and generated brief text. Moderation detects harmful content; it is not a replacement for privacy review. |
| Unsafe downstream writes | Do not write directly to CRM, ticketing, or analytics systems from the model output. Put a human review gate in front of medium/high risks, missing evidence, moderation flags, or raw-response retention. |
| Silent quality drift | Log model versions, prompt versions, schema versions, audio duration, redaction state, moderation state, and reviewer decisions. Sample calls for evals. |


## 前置需求

- Python 3.10 或更新版本。
- 真實音訊要跑的話，需要在 `OPENAI_API_KEY` 放一把 OpenAI API key。
- 真實音訊要跑的話，需要一個支援格式的會議錄音。
- 上傳的音檔必須在 25 MB 以下。支援的輸入格式是 `mp3`、`mp4`、`mpeg`、`mpga`、`m4a`、`wav` 和 `webm`。
- 可選：最多四段短的單人 reference clip。speech-to-text 指南建議 2 到 10 秒的 reference，用 multipart form data 傳送時要編碼成 data URL。

### 在本機跑這個 notebook

從 Cookbook repo 的本機 clone 開始，建一個虛擬環境，安裝 Jupyter 和 OpenAI SDK，然後開啟這個 notebook：

```bash
git clone https://github.com/openai/openai-cookbook.git
cd openai-cookbook
python3 -m venv .venv
source .venv/bin/activate
python -m pip install jupyter "openai>=1.93.0"
export OPENAI_API_KEY="your-api-key"
jupyter notebook examples/audio/speaker_aware_meeting_intelligence/speaker_aware_meeting_intelligence.ipynb
```

下面的合成 demo 只用 Python 標準函式庫，不會呼叫 API。要跑真實音訊的話，你也可以在現有的 notebook 環境裡直接安裝 OpenAI SDK。如果是在 Colab，直接在 cell 裡用 `!pip install openai` 就可以：

```python
%pip install "openai>=1.93.0"
```


## 核心的 diarization 請求

核心的 API 請求刻意寫得很短：

```python
client = OpenAI(timeout=30 * 60)

with open("meeting.wav", "rb") as audio_file:
    stream = client.audio.transcriptions.create(
        model="gpt-4o-transcribe-diarize",
        file=audio_file,
        response_format="diarized_json",
        chunking_strategy="auto",
        stream=True,
        extra_body={
            "known_speaker_names": ["Agent"],
            "known_speaker_references": [to_data_url(Path("agent_reference.wav"))],
        },
    )
    for event in stream:
        if event.type == "transcript.text.segment":
            print(event.speaker, event.text, event.start, event.end)
```

重點細節有：

- 需要 segment 層級的講者 metadata 時，用 `response_format="diarized_json"`。
- 音訊超過 30 秒時，用 `chunking_strategy="auto"`。
- 對已經錄完的錄音，想在 segment 定稿時就逐步拿到結果，用 `stream=True`。
- Python SDK 預設的 read timeout 是 10 分鐘，下面的 helper 為了較長的錄音改用 30 分鐘。
- 已知講者的名字和 reference 要一起傳，而且順序一致。
- Reference clip 要短、而且只有一個講者。


## Diarization 和講者辨識的差別

Diarization 回答的是「每一段是哪個聲音在講」。它會在同一份錄音裡把聲音分開，但不會建立永久的身分檔案，也不會記得這次通話的 `speaker_0` 和下次通話的 `speaker_0` 是同一個人。沒有 reference 時，通用標籤仍然有用，因為它保留了歸屬：pipeline 可以分辨提出需求的講者和做出承諾的講者。

已知講者的 reference 是針對當次請求的選用身分提示：

| Input | Result |
| --- | --- |
| Meeting audio only | The model separates voices, usually with generic labels such as `speaker_0` and `speaker_1`. |
| Meeting audio plus a named reference clip | Matching segments can use the supplied name; unmatched speakers can remain generic. |
| A later or historical recording | Pass the reference clip again. Labels do not carry across recordings automatically. |

### 把 reference clip 跟會議錄音一起傳

會議錄音和 reference clip 是同一個 transcription 請求裡兩個分開的輸入。不要把 reference clip 接到會議音訊後面。會議用 `file=...` 上傳；每段 reference clip 編碼成 data URL，透過 `known_speaker_references` 傳送，名字則放在 `known_speaker_names` 裡相同的位置。
下面的 helper 包裝了這個請求的形式。例如，這段會傳一份會議錄音，加上另一段內部業務代表說話的短 clip：

```python
meeting_audio = Path("customer_call.wav")
known_speakers = [
    ("Internal rep", Path("internal_rep_reference.wav")),
]

raw_transcription = transcribe_with_diarization(
    audio_file=meeting_audio,
    known_speakers=known_speakers,
)
```

請用乾淨、取得同意、2 到 10 秒、只有一個講者而且背景噪音很少的 clip。對於固定出現的內部講者，正式的應用程式可以維護一個有存取控制的 reference registry，每次請求時附上對應的 clip。對於歷史錄音，每份錄音都跑同樣的流程；只要 clip 乾淨、單人，reference clip 也可以來自較早且取得同意的通話。把 reference 當成敏感資料，用有代表性的音訊評估比對品質，高風險的下游寫入要保留人工審核。


```python
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from IPython.display import JSON, Markdown, display
except ImportError:  # Makes this cell safe in non-notebook runners.
    JSON = None
    Markdown = None

    def display(value):
        print(value)


def show_markdown(text: str) -> None:
    if Markdown:
        display(Markdown(text))
    else:
        print(text)


def show_json(payload: Any, expanded: bool = False) -> None:
    if JSON:
        display(JSON(payload, expanded=expanded))
    else:
        print(json.dumps(payload, indent=2))


DEFAULT_TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
DEFAULT_SUMMARY_MODEL = os.getenv("OPENAI_MEETING_INTELLIGENCE_MODEL", "gpt-4.1-mini")
DEFAULT_MODERATION_MODEL = "omni-moderation-latest"
SUPPORTED_REFERENCE_MIME_PREFIXES = ("audio/", "video/")
MAX_AUDIO_UPLOAD_BYTES = 25_000_000
DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS = 30 * 60

print("Notebook helpers loaded")
```

```python
@dataclass(frozen=True)
class Segment:
    segment_id: str
    speaker: str
    start: float
    end: float
    text: str


DEMO_SEGMENTS = [
    Segment(
        segment_id="seg_001",
        speaker="Solutions Engineer",
        start=0.0,
        end=9.2,
        text="Thanks for joining. I would like to understand where your support handoff breaks down today.",
    ),
    Segment(
        segment_id="seg_002",
        speaker="Customer",
        start=9.3,
        end=22.4,
        text="The biggest issue is that escalation notes are inconsistent. Managers spend Monday morning reconstructing what happened from call recordings.",
    ),
    Segment(
        segment_id="seg_003",
        speaker="Solutions Engineer",
        start=22.5,
        end=38.1,
        text="So the priority is reliable call summaries, who committed to what, and enough evidence that the team trusts the handoff.",
    ),
    Segment(
        segment_id="seg_004",
        speaker="Customer",
        start=38.2,
        end=55.0,
        text="Exactly. We also need risks called out, especially compliance-sensitive promises, and we need to push action items into our CRM.",
    ),
    Segment(
        segment_id="seg_005",
        speaker="Solutions Engineer",
        start=55.1,
        end=70.3,
        text="I will send a prototype that includes speaker-aware transcripts, action items with evidence, and a redaction pass before CRM sync.",
    ),
]


PII_PATTERNS = [
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b"), "[email]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"), "[phone]"),
]

print(f"Loaded {len(DEMO_SEGMENTS)} synthetic transcript segments")
```

## 步驟 1：定義 structured output schema

會議分析的結果常常要餵給系統紀錄。用 strict structured outputs，下游程式碼才會拿到穩定的格式，不支持的欄位會被拒絕，而不是被默默接受。這個 schema 也要求結構化的 `evidence_refs`：每個抽出來的項目都必須引用逐字稿的 `segment_id` 和該 segment 裡的一段引文，這樣 guardrail 就能機械式驗證內容有沒有依據。


```python
EVIDENCE_REF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "segment_id": {"type": "string"},
        "quote": {"type": "string"},
    },
    "required": ["segment_id", "quote"],
}

EVIDENCE_REFS_SCHEMA: dict[str, Any] = {
    "type": "array",
    "items": EVIDENCE_REF_SCHEMA,
}

NULLABLE_STRING_SCHEMA: dict[str, Any] = {"type": ["string", "null"]}


MEETING_INTELLIGENCE_SCHEMA: dict[str, Any] = {
    "name": "meeting_intelligence",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "participants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string"},
                        "inferred_role": NULLABLE_STRING_SCHEMA,
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                    },
                    "required": ["speaker", "inferred_role", "evidence_refs"],
                },
            },
            "customer_context": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "fact": {"type": "string"},
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                    },
                    "required": ["fact", "evidence_refs"],
                },
            },
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "decision": {"type": "string"},
                        "speaker_or_group": NULLABLE_STRING_SCHEMA,
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                    },
                    "required": ["decision", "speaker_or_group", "evidence_refs"],
                },
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "owner_speaker": NULLABLE_STRING_SCHEMA,
                        "task": {"type": "string"},
                        "due_date_or_trigger": NULLABLE_STRING_SCHEMA,
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                    },
                    "required": ["owner_speaker", "task", "due_date_or_trigger", "evidence_refs"],
                },
            },
            "risks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "risk": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                        "mitigation": {"type": "string"},
                    },
                    "required": ["risk", "severity", "evidence_refs", "mitigation"],
                },
            },
            "explicit_questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question": {"type": "string"},
                        "asked_by_speaker": {"type": "string"},
                        "directed_to_speaker": NULLABLE_STRING_SCHEMA,
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                    },
                    "required": ["question", "asked_by_speaker", "directed_to_speaker", "evidence_refs"],
                },
            },
            "suggested_follow_ups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "question": {"type": "string"},
                        "rationale": {"type": "string"},
                        "evidence_refs": EVIDENCE_REFS_SCHEMA,
                    },
                    "required": ["question", "rationale", "evidence_refs"],
                },
            },
            "notable_quotes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string"},
                        "quote": {"type": "string"},
                        "timestamp": {"type": "string"},
                        "segment_id": {"type": "string"},
                    },
                    "required": ["speaker", "quote", "timestamp", "segment_id"],
                },
            },
            "follow_up_email": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["subject", "body"],
            },
        },
        "required": [
            "summary",
            "participants",
            "customer_context",
            "decisions",
            "action_items",
            "risks",
            "explicit_questions",
            "suggested_follow_ups",
            "notable_quotes",
            "follow_up_email",
        ],
    },
}

print("Structured output schema ready")
```

## 步驟 2：建立音訊和逐字稿的 helper

已知講者的 reference 是選用的。沒有的話，diarization 還是能把講者分開，只是標籤可能是通用的，例如 `speaker_0` 或 `speaker_1`。有 reference 時，API 可以把 segment 對應到你提供的名字。

請用短而乾淨、只有一個講者、背景噪音少的 reference clip。只有在取得同意而且有明確業務需求時，才保留 reference clip。


```python
def to_data_url(path) -> str:
    path = Path(path)
    mime_type, _ = mimetypes.guess_type(path)
    if mime_type is None:
        mime_type = "audio/wav"
    elif not mime_type.startswith(SUPPORTED_REFERENCE_MIME_PREFIXES):
        raise ValueError(f"Reference clip must be an audio or video file, got {mime_type}: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def transcribe_with_diarization(
    audio_file: Path,
    known_speakers: list[tuple[str, Path]],
    model: str = DEFAULT_TRANSCRIPTION_MODEL,
    request_timeout_seconds: float = DEFAULT_TRANSCRIPTION_TIMEOUT_SECONDS,
    stream_transcription: bool = True,
) -> Any:
    if not audio_file.is_file():
        raise FileNotFoundError(f"Audio file does not exist or is not a regular file: {audio_file}")

    if request_timeout_seconds <= 0:
        raise ValueError("request_timeout_seconds must be positive.")

    audio_size_bytes = audio_file.stat().st_size
    if audio_size_bytes > MAX_AUDIO_UPLOAD_BYTES:
        raise ValueError(
            f"Audio file is {audio_size_bytes:,} bytes; "
            "the Audio Transcriptions API accepts uploads up to 25 MB. "
            "Compress or split the recording before retrying."
        )

    from openai import OpenAI

    client = OpenAI(timeout=request_timeout_seconds)
    params: dict[str, Any] = {
        "model": model,
        "response_format": "diarized_json",
        "chunking_strategy": "auto",
        "stream": stream_transcription,
    }

    if known_speakers:
        if len(known_speakers) > 4:
            raise ValueError("gpt-4o-transcribe-diarize accepts up to 4 known speaker references.")
        params["extra_body"] = {
            "known_speaker_names": [name for name, _ in known_speakers],
            "known_speaker_references": [to_data_url(path) for _, path in known_speakers],
        }

    with audio_file.open("rb") as audio:
        response = client.audio.transcriptions.create(file=audio, **params)
        if stream_transcription:
            return collect_streamed_transcription(response)
        return response


def to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return {key: to_plain(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_plain(item) for item in value]
    return value


def collect_streamed_transcription(events: Any) -> dict[str, Any]:
    segments: list[dict[str, Any]] = []
    full_text = ""
    usage: Any = None

    for event in events:
        data = to_plain(event)
        if not isinstance(data, dict):
            continue

        event_type = data.get("type")
        if event_type == "transcript.text.segment":
            segments.append(data)
        elif event_type == "transcript.text.done":
            full_text = str(data.get("text") or "")
            usage = data.get("usage")

    if not segments:
        raise ValueError("No diarized transcript segments were emitted by the transcription stream.")
    return {"segments": segments, "text": full_text, "usage": usage}


def normalize_segments(transcription: Any) -> list[Segment]:
    data = to_plain(transcription)
    raw_segments = data.get("segments", []) if isinstance(data, dict) else []
    segments: list[Segment] = []

    for index, item in enumerate(raw_segments):
        if hasattr(item, "model_dump"):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue

        text = str(item.get("text", "")).strip()
        if not text:
            continue

        segment_id = str(item.get("segment_id") or item.get("id") or f"seg_{len(segments) + 1:03d}")
        segments.append(
            Segment(
                segment_id=segment_id,
                speaker=str(item.get("speaker") or f"Speaker {index + 1}"),
                start=float(item.get("start") or 0.0),
                end=float(item.get("end") or 0.0),
                text=text,
            )
        )

    if not segments and isinstance(data, dict) and data.get("text"):
        segments.append(Segment(segment_id="seg_001", speaker="Speaker 1", start=0.0, end=0.0, text=str(data["text"])))

    if not segments:
        raise ValueError("No transcript segments were found in the transcription response.")
    return segments

print("Audio and transcript helpers ready")
```

## 步驟 3：正規化逐字稿

正規化後的逐字稿是音訊處理和會議分析之間的合約。它讓你可以不重新轉錄音訊就重跑摘要、檢查歸屬品質，並且縮短原始音訊的保存時間。

每個 segment 都會得到固定的 `segment_id`，例如 `seg_005`。之後模型必須在 `evidence_refs` 裡引用這些 ID，guardrail 步驟會驗證每段引文真的出現在所引用的 segment 裡。

下面的 regex redaction helper 只是示意：它只遮蔽基本的 email 和電話格式，不是完整的 PII 或 DLP 系統。敏感或受監管的流程，請用符合政策的偵測器加上人工審核。


```python
def redact_text(text: str) -> str:
    redacted = text
    for pattern, replacement in PII_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_segments(segments: list[Segment]) -> list[Segment]:
    return [
        Segment(
            segment_id=segment.segment_id,
            speaker=segment.speaker,
            start=segment.start,
            end=segment.end,
            text=redact_text(segment.text),
        )
        for segment in segments
    ]


def pii_matches(text: str) -> list[str]:
    matches: list[str] = []
    for pattern, replacement in PII_PATTERNS:
        if pattern.search(text):
            matches.append(replacement.strip("[]"))
    return sorted(set(matches))


def format_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    minutes, remainder_ms = divmod(total_ms, 60_000)
    secs, millis = divmod(remainder_ms, 1000)
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def transcript_as_markdown(segments: list[Segment]) -> str:
    lines = ["# Speaker-Labeled Transcript", ""]
    for segment in segments:
        start = format_timestamp(segment.start)
        end = format_timestamp(segment.end)
        lines.append(f"**{segment.segment_id} | {segment.speaker} [{start}-{end}]**: {segment.text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def transcript_for_model(segments: list[Segment]) -> str:
    return "\n".join(
        f"{segment.segment_id} | {segment.speaker} | {format_timestamp(segment.start)}-{format_timestamp(segment.end)} | {segment.text}"
        for segment in segments
    )


show_markdown(transcript_as_markdown(DEMO_SEGMENTS))
```

## 步驟 4：抽取結構化的會議分析

模型拿到標好講者的逐字稿，而且只能用這份逐字稿當證據。最安全的預設做法，是輸出空陣列，而不是看似合理但沒有依據的 CRM 筆記。schema 也用了必填但可為 null 的欄位，例如 `due_date_or_trigger`、`inferred_role` 和 `directed_to_speaker`，這樣未知的值會維持 `null`，不會被猜測填滿。

對每個抽出來的事實、行動項目、風險、問題或建議，模型都會回傳帶有 `segment_id` 和引文的 `evidence_refs`。這讓審核者有一條可讀的出處軌跡，也讓程式碼有具體的東西可以驗證。


```python
def response_output_text_or_raise(response: Any) -> str:
    data = to_plain(response)
    status = data.get("status") if isinstance(data, dict) else getattr(response, "status", None)
    if status and status != "completed":
        details = data.get("incomplete_details") if isinstance(data, dict) else getattr(response, "incomplete_details", None)
        raise RuntimeError(f"Responses API returned status={status!r}; incomplete_details={details!r}")

    refusals: list[str] = []
    if isinstance(data, dict):
        for item in data.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal" or content.get("refusal"):
                    refusals.append(str(content.get("refusal") or content.get("text") or content))
    if refusals:
        raise RuntimeError(f"Responses API returned a refusal: {refusals[0]}")

    content = getattr(response, "output_text", None)
    if content is None and isinstance(data, dict):
        content = data.get("output_text")
    content = str(content or "").strip()
    if not content:
        raise RuntimeError("The model returned an empty response.")
    return content


def parse_meeting_intelligence_json(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Responses API returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Responses API returned JSON, but the top-level value was not an object.")
    return parsed


def generate_meeting_intelligence(segments: list[Segment], model: str = DEFAULT_SUMMARY_MODEL) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    transcript = transcript_for_model(segments)

    completion = client.responses.create(
        model=model,
        temperature=0,
        store=False,
        input=[
            {
                "role": "system",
                "content": (
                    "You create meeting intelligence from speaker-labeled transcripts. "
                    "Use only the transcript as evidence. Do not invent names, dates, decisions, "
                    "commitments, or implementation details. If evidence is missing, leave the relevant array empty. "
                    "Use null for unknown roles, owners, due dates or triggers, directed-to speakers, or decision owners. "
                    "Put single-speaker commitments in action_items, not decisions. "
                    "Only include decisions when the transcript shows an explicit decision or agreement. "
                    "Put only questions actually asked in explicit_questions. "
                    "Put inferred next questions in suggested_follow_ups with rationale and evidence_refs. "
                    "Every extracted item must include evidence_refs with segment_id values copied from the transcript "
                    "and quote text copied from that same segment. Do not fabricate segment IDs or quotes. "
                    "Use empty arrays instead of unsupported items. "
                    "If the follow-up email signer is unknown, end with [Your name]."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract a customer-safe meeting brief from this transcript. "
                    "Transcript rows use: segment_id | speaker | timestamp range | text.\n\n"
                    f"{transcript}"
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": MEETING_INTELLIGENCE_SCHEMA["name"],
                "strict": MEETING_INTELLIGENCE_SCHEMA["strict"],
                "schema": MEETING_INTELLIGENCE_SCHEMA["schema"],
            }
        },
    )

    content = response_output_text_or_raise(completion)
    return parse_meeting_intelligence_json(content)


def demo_meeting_intelligence() -> dict[str, Any]:
    return {
        "summary": (
            "The customer needs a dependable post-call handoff process. Their main pain point is "
            "inconsistent escalation notes, which forces managers to reconstruct calls manually. "
            "The proposed path is a speaker-aware transcript, evidence-backed action items, risk "
            "detection, redaction, and CRM sync."
        ),
        "participants": [
            {
                "speaker": "Solutions Engineer",
                "inferred_role": "OpenAI technical seller or solution owner",
                "evidence_refs": [
                    {
                        "segment_id": "seg_001",
                        "quote": "I would like to understand where your support handoff breaks down today.",
                    },
                    {
                        "segment_id": "seg_005",
                        "quote": "I will send a prototype that includes speaker-aware transcripts, action items with evidence, and a redaction pass before CRM sync.",
                    },
                ],
            },
            {
                "speaker": "Customer",
                "inferred_role": "Customer stakeholder for support operations",
                "evidence_refs": [
                    {
                        "segment_id": "seg_002",
                        "quote": "The biggest issue is that escalation notes are inconsistent.",
                    },
                    {
                        "segment_id": "seg_004",
                        "quote": "we need to push action items into our CRM.",
                    },
                ],
            },
        ],
        "customer_context": [
            {
                "fact": "Escalation notes are inconsistent today.",
                "evidence_refs": [
                    {
                        "segment_id": "seg_002",
                        "quote": "The biggest issue is that escalation notes are inconsistent.",
                    }
                ],
            },
            {
                "fact": "Managers spend time reconstructing calls from recordings.",
                "evidence_refs": [
                    {
                        "segment_id": "seg_002",
                        "quote": "Managers spend Monday morning reconstructing what happened from call recordings.",
                    }
                ],
            },
            {
                "fact": "The customer wants action items pushed into their CRM.",
                "evidence_refs": [{"segment_id": "seg_004", "quote": "we need to push action items into our CRM."}],
            },
        ],
        "decisions": [],
        "action_items": [
            {
                "owner_speaker": "Solutions Engineer",
                "task": "Send a prototype that includes speaker-aware transcripts, action items with evidence, and a redaction pass before CRM sync.",
                "due_date_or_trigger": None,
                "evidence_refs": [
                    {
                        "segment_id": "seg_005",
                        "quote": "I will send a prototype that includes speaker-aware transcripts, action items with evidence, and a redaction pass before CRM sync.",
                    }
                ],
            }
        ],
        "risks": [
            {
                "risk": "Compliance-sensitive promises need to be identified in meeting notes.",
                "severity": "medium",
                "evidence_refs": [
                    {
                        "segment_id": "seg_004",
                        "quote": "We also need risks called out, especially compliance-sensitive promises",
                    }
                ],
                "mitigation": "Route compliance-sensitive risks to human review before CRM sync.",
            }
        ],
        "explicit_questions": [
            {
                "question": "Where does your support handoff break down today?",
                "asked_by_speaker": "Solutions Engineer",
                "directed_to_speaker": "Customer",
                "evidence_refs": [
                    {
                        "segment_id": "seg_001",
                        "quote": "I would like to understand where your support handoff breaks down today.",
                    }
                ],
            }
        ],
        "suggested_follow_ups": [
            {
                "question": "Which CRM object and fields should receive action items?",
                "rationale": "The customer asked to push action items into their CRM but did not specify the target schema or workflow.",
                "evidence_refs": [{"segment_id": "seg_004", "quote": "we need to push action items into our CRM."}],
            }
        ],
        "notable_quotes": [
            {
                "speaker": "Customer",
                "quote": "Managers spend Monday morning reconstructing what happened from call recordings.",
                "timestamp": "00:09.300",
                "segment_id": "seg_002",
            }
        ],
        "follow_up_email": {
            "subject": "Prototype for speaker-aware meeting handoffs",
            "body": (
                "Hi,\n\nThanks for the conversation. I heard that inconsistent escalation notes, "
                "evidence-backed action items, compliance-sensitive risk detection, and CRM sync "
                "are the core requirements. I will send a prototype with speaker-aware transcripts, "
                "action items with evidence, and a redaction pass before CRM sync.\n\nBest,\n[Your name]"
            ),
        },
    }


show_json(demo_meeting_intelligence(), expanded=False)
```

## 步驟 5：產生可審閱的會議簡報

這份審閱用的產出會把講者、segment ID、時間戳和引文證據，放在決議、風險和行動項目旁邊，讓人在內容寫入下游之前可以先抽查。


```python
def clean_markdown_cell(value: Any) -> str:
    if value is None:
        return "_Not specified._"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def render_evidence_refs(refs: Any) -> str:
    if not isinstance(refs, list) or not refs:
        return "_No evidence refs._"

    rendered = []
    for ref in refs:
        if not isinstance(ref, dict):
            continue
        segment_id = clean_markdown_cell(ref.get("segment_id", ""))
        quote = clean_markdown_cell(ref.get("quote", ""))
        rendered.append(f"`{segment_id}`: {quote}")
    return "<br>".join(rendered) if rendered else "_No evidence refs._"


def markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, Any]]) -> str:
    if not rows:
        return "_None identified._"

    header = "| " + " | ".join(title for title, _ in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        values = []
        for _, key in columns:
            value = key(row) if callable(key) else row.get(key, "")
            values.append(clean_markdown_cell(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, divider, *body])


def render_meeting_brief(intelligence: dict[str, Any]) -> str:
    follow_up = intelligence.get("follow_up_email", {})
    evidence_column = ("Evidence", lambda row: render_evidence_refs(row.get("evidence_refs", [])))
    lines = [
        "# Meeting Brief",
        "",
        "## Summary",
        "",
        str(intelligence.get("summary", "")).strip() or "_No summary generated._",
        "",
        "## Participants",
        "",
        markdown_table(
            intelligence.get("participants", []),
            [("Speaker", "speaker"), ("Inferred role", "inferred_role"), evidence_column],
        ),
        "",
        "## Customer Context",
        "",
        markdown_table(intelligence.get("customer_context", []), [("Fact", "fact"), evidence_column]),
        "",
        "## Decisions",
        "",
        markdown_table(
            intelligence.get("decisions", []),
            [("Decision", "decision"), ("Owner", "speaker_or_group"), evidence_column],
        ),
        "",
        "## Action Items",
        "",
        markdown_table(
            intelligence.get("action_items", []),
            [
                ("Owner", "owner_speaker"),
                ("Task", "task"),
                ("Due date or trigger", "due_date_or_trigger"),
                evidence_column,
            ],
        ),
        "",
        "## Risks",
        "",
        markdown_table(
            intelligence.get("risks", []),
            [("Risk", "risk"), ("Severity", "severity"), evidence_column, ("Mitigation", "mitigation")],
        ),
        "",
        "## Explicit Questions",
        "",
        markdown_table(
            intelligence.get("explicit_questions", []),
            [
                ("Question", "question"),
                ("Asked by", "asked_by_speaker"),
                ("Directed to", "directed_to_speaker"),
                evidence_column,
            ],
        ),
        "",
        "## Suggested Follow-ups",
        "",
        markdown_table(
            intelligence.get("suggested_follow_ups", []),
            [("Question", "question"), ("Rationale", "rationale"), evidence_column],
        ),
        "",
        "## Notable Quotes",
        "",
        markdown_table(
            intelligence.get("notable_quotes", []),
            [("Speaker", "speaker"), ("Quote", "quote"), ("Timestamp", "timestamp"), ("Segment ID", "segment_id")],
        ),
        "",
        "## Follow-up Email Draft",
        "",
        f"**Subject:** {follow_up.get('subject', '')}",
        "",
        str(follow_up.get("body", "")).strip(),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


demo_brief = render_meeting_brief(demo_meeting_intelligence())
show_markdown(demo_brief)
```

## 步驟 6：加上 guardrail 並寫出產出檔

範例會寫出一份 `guardrail_report.json`，裡面是這些本地檢查：

- 正規化後的逐字稿 segment；
- 基本的 email 和電話 PII 格式；
- 指向真實 segment ID 且引文吻合的證據引用；
- 中度或高度風險的輸出；
- 可選的 moderation 標記；
- 原始 transcription 回應的儲存。


```python
def summarize_moderation_response(response: Any) -> dict[str, Any]:
    data = to_plain(response)
    summaries: list[dict[str, Any]] = []

    for result in data.get("results", []) if isinstance(data, dict) else []:
        categories = result.get("categories", {}) if isinstance(result, dict) else {}
        category_scores = result.get("category_scores", {}) if isinstance(result, dict) else {}
        flagged_categories = sorted(key for key, value in categories.items() if bool(value))
        top_scores = dict(sorted(category_scores.items(), key=lambda item: float(item[1] or 0.0), reverse=True)[:5])
        summaries.append(
            {
                "flagged": bool(result.get("flagged")) if isinstance(result, dict) else False,
                "flagged_categories": flagged_categories,
                "top_category_scores": top_scores,
            }
        )

    return {
        "id": data.get("id") if isinstance(data, dict) else None,
        "model": data.get("model") if isinstance(data, dict) else DEFAULT_MODERATION_MODEL,
        "flagged": any(item["flagged"] for item in summaries),
        "results": summaries,
    }


def moderate_text(text: str, model: str = DEFAULT_MODERATION_MODEL) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    response = client.moderations.create(model=model, input=text)
    return summarize_moderation_response(response)


def iter_evidence_refs(value: Any, path: str = "$") -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            next_path = f"{path}.{key}"
            if key == "evidence_refs":
                found.append((next_path, inner))
            else:
                found.extend(iter_evidence_refs(inner, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(iter_evidence_refs(item, f"{path}[{index}]"))
    return found


def normalize_for_quote_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def validate_evidence_refs(intelligence: dict[str, Any], segments: list[Segment]) -> list[dict[str, Any]]:
    segment_by_id = {segment.segment_id: segment for segment in segments}
    problems: list[dict[str, Any]] = []

    for path, refs in iter_evidence_refs(intelligence):
        if not isinstance(refs, list) or not refs:
            problems.append({"path": path, "issue": "missing_or_empty_evidence_refs"})
            continue

        for index, ref in enumerate(refs):
            ref_path = f"{path}[{index}]"
            if not isinstance(ref, dict):
                problems.append({"path": ref_path, "issue": "evidence_ref_is_not_an_object"})
                continue

            segment_id = str(ref.get("segment_id", "")).strip()
            quote = str(ref.get("quote", "")).strip()
            if not segment_id or not quote:
                problems.append({"path": ref_path, "issue": "missing_segment_id_or_quote", "segment_id": segment_id})
                continue

            segment = segment_by_id.get(segment_id)
            if segment is None:
                problems.append({"path": ref_path, "issue": "unknown_segment_id", "segment_id": segment_id})
                continue

            if normalize_for_quote_match(quote) not in normalize_for_quote_match(segment.text):
                problems.append(
                    {
                        "path": ref_path,
                        "issue": "quote_not_found_in_segment",
                        "segment_id": segment_id,
                        "quote": quote,
                    }
                )

    for index, quote in enumerate(intelligence.get("notable_quotes", [])):
        if not isinstance(quote, dict):
            continue
        segment_id = str(quote.get("segment_id", "")).strip()
        quote_text = str(quote.get("quote", "")).strip()
        segment = segment_by_id.get(segment_id)
        if segment is None:
            problems.append({"path": f"$.notable_quotes[{index}]", "issue": "unknown_segment_id", "segment_id": segment_id})
        elif normalize_for_quote_match(quote_text) not in normalize_for_quote_match(segment.text):
            problems.append(
                {
                    "path": f"$.notable_quotes[{index}]",
                    "issue": "quote_not_found_in_segment",
                    "segment_id": segment_id,
                    "quote": quote_text,
                }
            )

    return problems


def add_guardrail_check(checks: list[dict[str, Any]], name: str, status: str, detail: str, evidence = None) -> None:
    check: dict[str, Any] = {"name": name, "status": status, "detail": detail}
    if evidence is not None:
        check["evidence"] = evidence
    checks.append(check)


def build_guardrail_report(
    segments: list[Segment],
    intelligence: dict[str, Any],
    meeting_brief: str,
    redaction_enabled: bool,
    raw_saved: bool,
    moderation_results: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    transcript_text = transcript_for_model(segments)

    add_guardrail_check(
        checks,
        "transcript_segments_present",
        "pass" if segments else "fail",
        f"Found {len(segments)} normalized transcript segments.",
    )

    pii_found = pii_matches(transcript_text + "\n" + meeting_brief)
    pii_detail = (
        "Basic PII patterns remain after redaction."
        if redaction_enabled
        else "Basic PII patterns were detected; run with redaction or review before storage."
    )
    add_guardrail_check(
        checks,
        "basic_pii_scan",
        "review" if pii_found else "pass",
        pii_detail if pii_found else "No basic email or phone patterns detected.",
        {"matches": pii_found, "redaction_enabled": redaction_enabled},
    )

    evidence_ref_problems = validate_evidence_refs(intelligence, segments)
    add_guardrail_check(
        checks,
        "evidence_refs",
        "review" if evidence_ref_problems else "pass",
        (
            "Some evidence references are missing, cite unknown segments, or quote text that is not present in the cited segment."
            if evidence_ref_problems
            else "All evidence references point to real segments with matching quote text."
        ),
        {"problem_count": len(evidence_ref_problems), "examples": evidence_ref_problems[:5]},
    )

    risks = intelligence.get("risks", [])
    review_risks = [risk for risk in risks if str(risk.get("severity", "")).lower() in {"medium", "high"}]
    severity_counts = {
        "low": sum(1 for risk in risks if str(risk.get("severity", "")).lower() == "low"),
        "medium": sum(1 for risk in risks if str(risk.get("severity", "")).lower() == "medium"),
        "high": sum(1 for risk in risks if str(risk.get("severity", "")).lower() == "high"),
    }
    add_guardrail_check(
        checks,
        "risk_outputs",
        "review" if review_risks else "pass",
        "Medium or high risks should be reviewed before downstream writes." if review_risks else "No medium or high risks identified.",
        {"severity_counts": severity_counts},
    )

    moderation_flagged = [name for name, result in moderation_results.items() if isinstance(result, dict) and result.get("flagged")]
    if moderation_results:
        add_guardrail_check(
            checks,
            "moderation",
            "review" if moderation_flagged else "pass",
            "Moderation flagged content that should be reviewed." if moderation_flagged else "Moderation did not flag transcript or brief content.",
            {"flagged_artifacts": moderation_flagged},
        )
    else:
        add_guardrail_check(checks, "moderation", "not_run", "Moderation was not requested. Use moderation for content safety classification.")

    add_guardrail_check(
        checks,
        "raw_response_storage",
        "review" if raw_saved else "pass",
        "Raw transcription response was saved; confirm retention and access controls." if raw_saved else "Raw transcription response was not saved.",
    )

    status = "review_required" if any(check["status"] in {"review", "fail"} for check in checks) else "pass"
    if any(check["status"] == "fail" for check in checks):
        status = "fail"

    return {
        "status": status,
        "recommended_next_step": "Send artifacts to human review before downstream writes." if status != "pass" else "Artifacts passed local guardrail checks.",
        "checks": checks,
        "moderation": moderation_results,
    }

print("Guardrail helpers ready")
```

```python
def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_artifacts(
    output_dir: Path,
    segments: list[Segment],
    intelligence: dict[str, Any],
    guardrail_report: dict[str, Any],
    raw_payload = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "transcript_segments.json", [asdict(segment) for segment in segments])
    (output_dir / "speaker_labeled_transcript.md").write_text(transcript_as_markdown(segments), encoding="utf-8")
    write_json(output_dir / "meeting_intelligence.json", intelligence)
    (output_dir / "meeting_brief.md").write_text(render_meeting_brief(intelligence), encoding="utf-8")
    write_json(output_dir / "guardrail_report.json", guardrail_report)
    if raw_payload is not None:
        write_json(output_dir / "raw_transcription_response.json", to_plain(raw_payload))


def run_pipeline_from_segments(
    segments: list[Segment],
    output_dir: Path,
    intelligence = None,
    redaction_enabled: bool = False,
    moderation_results = None,
    raw_saved: bool = False,
    raw_payload = None,
) -> dict[str, Any]:
    if redaction_enabled:
        segments = redact_segments(segments)
    if intelligence is None:
        intelligence = generate_meeting_intelligence(segments)
    meeting_brief = render_meeting_brief(intelligence)
    guardrail_report = build_guardrail_report(
        segments=segments,
        intelligence=intelligence,
        meeting_brief=meeting_brief,
        redaction_enabled=redaction_enabled,
        raw_saved=raw_saved,
        moderation_results=moderation_results or {},
    )
    write_artifacts(output_dir, segments, intelligence, guardrail_report, raw_payload=raw_payload if raw_saved else None)
    return {
        "segments": segments,
        "intelligence": intelligence,
        "meeting_brief": meeting_brief,
        "guardrail_report": guardrail_report,
        "output_dir": output_dir,
    }

print("Artifact helpers ready")
```

## 步驟 7：跑 deterministic 的 demo fixture

這一段是不需要網路的 deterministic demo，不是模型品質的 eval。它用一份固定的合成 diarized 逐字稿，和一個固定的預期會議分析物件，讓審閱者不用 API key 也能跑 notebook。

### 這個 fixture 檢查什麼

這個 fixture 會走過跟真實音訊相同的產出檔和 guardrail 路徑：逐字稿渲染、JSON 寫入、Markdown 簡報渲染、PII redaction helper、證據引用驗證、可為 null 的欄位，以及審核路由。

### 這個 fixture 不檢查什麼

它不衡量轉錄品質、diarization 準確度，也不衡量模型對新會議的抽取品質。下面的 eval 區段會加上 deterministic 評分和一個可選的 LLM-as-judge 做法來處理那一層。


```python
output_dir = Path(tempfile.mkdtemp(prefix="meeting-intelligence-demo-"))
demo_run = run_pipeline_from_segments(
    segments=DEMO_SEGMENTS,
    output_dir=output_dir,
    intelligence=demo_meeting_intelligence(),
)

print(f"Wrote meeting intelligence artifacts to {output_dir}")
for artifact_name in [
    "transcript_segments.json",
    "speaker_labeled_transcript.md",
    "meeting_intelligence.json",
    "meeting_brief.md",
    "guardrail_report.json",
]:
    artifact_path = output_dir / artifact_name
    print(f"- {artifact_path} ({artifact_path.stat().st_size} bytes)")
```

```python
segments = json.loads((output_dir / "transcript_segments.json").read_text())
segments[:2]
```

```python
show_markdown((output_dir / "speaker_labeled_transcript.md").read_text())
```

```python
meeting_intelligence_json = json.loads((output_dir / "meeting_intelligence.json").read_text())
show_json(meeting_intelligence_json, expanded=False)
```

```python
show_markdown((output_dir / "meeting_brief.md").read_text())
```

```python
guardrail_report = json.loads((output_dir / "guardrail_report.json").read_text())
show_json(guardrail_report, expanded=True)
```

## 步驟 8：用真實音訊跑

下一個 cell 刻意設成要自己開。把 `RUN_REAL_AUDIO = True`，填上你本機的音檔路徑，並確認已經設好 `OPENAI_API_KEY`。

Transcriptions API 接受最大 25 MB 的檔案。`chunking_strategy="auto"` 是對合格的上傳切 segment，不會把過大的檔案切開。比較長的會議，要先壓縮成支援的低 bitrate 格式，或在轉錄前切成有大小上限的檔案，合併結果時再保留或位移時間戳。
長錄音也可能超過 Python SDK 預設的 read timeout。這個 helper 預設用串流取得定稿的 diarized segment，並保留 30 分鐘的 timeout 當後盾。只有在你明確需要單一的非串流回應時才把 `stream_transcription=False`；如果超長的錄音用單一請求不夠可靠，就把它切開。

### 讀者怎麼提供檔案

這份 cookbook 以 notebook 為主，發布的內容裡沒有獨立的 `.py` 指令。把會議錄音和選用的 reference clip 放在 notebook kernel 讀得到的地方。在本機 Jupyter，可以是放在 notebook 旁邊的資料夾，或磁碟上的絕對路徑。在 Colab 這類託管的 notebook，要先把檔案上傳到 session 裡。

例如，讀者可能有這樣的檔案：

```text
audio/
  customer_call.mp3
  internal_rep_reference.wav
```

然後把設定變數指向那些檔案：

```python
AUDIO_FILE = Path("audio/customer_call.mp3")
KNOWN_SPEAKERS = {
    "Internal rep": Path("audio/internal_rep_reference.wav"),
}
```

`AUDIO_FILE` 是原始的會議錄音。`KNOWN_SPEAKERS` 把你想在輸出中看到的標籤，對應到另一段 2 到 10 秒的 reference clip；helper 是把這段 clip 隨請求一起送出，而不是接在會議音訊後面。在正式的應用程式裡，同一個 helper 可以接收由上傳建立的暫存檔，或從物件儲存下載的檔案。

第一次跑接近正式環境的流程時，保持簡單：

- 用一份會議音檔。
- 較長的錄音用 `chunking_strategy="auto"`。
- 只有在取得同意而且有明確業務需求時，才加已知講者的 reference。
- 儲存之前先跑 redaction。
- 如果有害內容分類是你審核政策的一部分，就跑 moderation。


```python
RUN_REAL_AUDIO = False
AUDIO_FILE = Path("/path/to/meeting.wav")
# Keep each reference clip separate from AUDIO_FILE. Use a clean, consented 2-10 second sample of one speaker.
KNOWN_SPEAKERS = {
    # "Internal rep": Path("/path/to/internal_rep_reference.wav"),
    # "Customer": Path("/path/to/customer_reference.wav"),
}
# Demonstration only: masks basic email and phone patterns, not a complete PII/DLP solution.
REDACT_REAL_AUDIO = True
MODERATE_REAL_AUDIO = False
SAVE_RAW_RESPONSE = False
REAL_OUTPUT_DIR = Path(tempfile.mkdtemp(prefix="meeting-intelligence-real-"))

if RUN_REAL_AUDIO:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running on real audio.")
    if not AUDIO_FILE.is_file():
        raise FileNotFoundError(AUDIO_FILE)

    known_speakers = [(speaker_name, reference_path) for speaker_name, reference_path in KNOWN_SPEAKERS.items()]
    raw_transcription = transcribe_with_diarization(AUDIO_FILE, known_speakers)
    real_segments = normalize_segments(raw_transcription)
    if REDACT_REAL_AUDIO:
        real_segments = redact_segments(real_segments)

    moderation_results: dict[str, Any] = {}
    if MODERATE_REAL_AUDIO:
        moderation_results["transcript"] = moderate_text(transcript_for_model(real_segments))

    real_intelligence = generate_meeting_intelligence(real_segments)
    real_brief = render_meeting_brief(real_intelligence)
    if MODERATE_REAL_AUDIO:
        moderation_results["meeting_brief"] = moderate_text(real_brief)

    real_report = build_guardrail_report(
        segments=real_segments,
        intelligence=real_intelligence,
        meeting_brief=real_brief,
        redaction_enabled=REDACT_REAL_AUDIO,
        raw_saved=SAVE_RAW_RESPONSE,
        moderation_results=moderation_results,
    )
    write_artifacts(
        REAL_OUTPUT_DIR,
        real_segments,
        real_intelligence,
        real_report,
        raw_payload=raw_transcription if SAVE_RAW_RESPONSE else None,
    )
    print(f"Wrote real-audio artifacts to {REAL_OUTPUT_DIR}")
else:
    print("Skipped real audio run. Set RUN_REAL_AUDIO = True after configuring AUDIO_FILE and OPENAI_API_KEY.")
```

## 步驟 9：跑 deterministic 的 smoke 和 regression 檢查

這些檢查是 deterministic 的，不會呼叫 API。把它們當成 notebook 運作機制的 smoke test 和 regression 測試，不是模型品質的 eval。

### Smoke test 檢查

前幾項檢查確認 notebook 寫出所有預期的產出檔，並把中度風險的輸出送去審核。

### Regression 檢查

其餘的 assertion 會抓 schema 可為 null 的行為、證據引用、demo 中沒有依據的說法、回應邊界情況、redaction 和時間戳格式的退化。


```python
expected_files = {
    "transcript_segments.json",
    "speaker_labeled_transcript.md",
    "meeting_intelligence.json",
    "meeting_brief.md",
    "guardrail_report.json",
}
assert expected_files.issubset({path.name for path in output_dir.iterdir()})
assert guardrail_report["status"] == "review_required"
assert any(check["name"] == "risk_outputs" and check["status"] == "review" for check in guardrail_report["checks"])
assert any(check["name"] == "evidence_refs" and check["status"] == "pass" for check in guardrail_report["checks"])

action_schema = MEETING_INTELLIGENCE_SCHEMA["schema"]["properties"]["action_items"]["items"]["properties"]
participant_schema = MEETING_INTELLIGENCE_SCHEMA["schema"]["properties"]["participants"]["items"]["properties"]
question_schema = MEETING_INTELLIGENCE_SCHEMA["schema"]["properties"]["explicit_questions"]["items"]["properties"]
assert "null" in action_schema["due_date_or_trigger"]["type"]
assert "null" in action_schema["owner_speaker"]["type"]
assert "null" in participant_schema["inferred_role"]["type"]
assert "null" in question_schema["directed_to_speaker"]["type"]

assert demo_run["segments"][0].segment_id == "seg_001"
assert demo_run["intelligence"]["decisions"] == []
assert demo_run["intelligence"]["action_items"][0]["due_date_or_trigger"] is None
assert demo_run["intelligence"]["action_items"][0]["evidence_refs"][0]["segment_id"] == "seg_005"
assert demo_run["intelligence"]["explicit_questions"]
assert demo_run["intelligence"]["suggested_follow_ups"]
assert validate_evidence_refs(demo_run["intelligence"], demo_run["segments"]) == []
assert "structured outputs" not in demo_run["intelligence"]["follow_up_email"]["body"].lower()
assert "`seg_005`" in demo_run["meeting_brief"]
assert "_Not specified._" in demo_run["meeting_brief"]

broken_intelligence = json.loads(json.dumps(demo_run["intelligence"]))
broken_intelligence["action_items"][0]["evidence_refs"] = [{"segment_id": "seg_999", "quote": "I will send a prototype"}]
assert validate_evidence_refs(broken_intelligence, demo_run["segments"])

broken_intelligence = json.loads(json.dumps(demo_run["intelligence"]))
broken_intelligence["action_items"][0]["evidence_refs"] = [{"segment_id": "seg_005", "quote": "I will send the contract tomorrow"}]
assert validate_evidence_refs(broken_intelligence, demo_run["segments"])

try:
    response_output_text_or_raise({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}})
    raise AssertionError("Expected incomplete response to raise")
except RuntimeError as exc:
    assert "incomplete" in str(exc)

try:
    response_output_text_or_raise({"status": "completed", "output": [{"content": [{"type": "refusal", "refusal": "Cannot comply."}]}]})
    raise AssertionError("Expected refusal response to raise")
except RuntimeError as exc:
    assert "refusal" in str(exc).lower()

try:
    response_output_text_or_raise({"status": "completed", "output_text": ""})
    raise AssertionError("Expected empty response to raise")
except RuntimeError as exc:
    assert "empty" in str(exc).lower()

try:
    parse_meeting_intelligence_json("not json")
    raise AssertionError("Expected invalid JSON to raise")
except RuntimeError as exc:
    assert "invalid JSON" in str(exc)

redacted = redact_segments([
    Segment("seg_test", "Customer", 0.0, 3.0, "Email me at alex@example.com or call 415-555-0100.")
])
assert redacted[0].segment_id == "seg_test"
assert redacted[0].text == "Email me at [email] or call [phone]."
assert format_timestamp(6000) == "100:00.000"

with tempfile.NamedTemporaryFile(suffix=".wav") as oversized_audio:
    oversized_audio.truncate(MAX_AUDIO_UPLOAD_BYTES + 1)
    oversized_audio.flush()
    try:
        transcribe_with_diarization(Path(oversized_audio.name), [])
        raise AssertionError("Expected oversized audio to raise")
    except ValueError as exc:
        assert "25 MB" in str(exc)

with tempfile.NamedTemporaryFile(suffix=".wav") as tiny_audio:
    try:
        transcribe_with_diarization(Path(tiny_audio.name), [], request_timeout_seconds=0)
        raise AssertionError("Expected invalid timeout to raise")
    except ValueError as exc:
        assert "positive" in str(exc)

streamed_transcription = collect_streamed_transcription([
    {"type": "transcript.text.segment", "id": "seg_stream", "speaker": "A", "start": 0.0, "end": 1.0, "text": "Hello"},
    {"type": "transcript.text.done", "text": "Hello", "usage": {"total_tokens": 1}},
])
streamed_segments = normalize_segments(streamed_transcription)
assert streamed_segments[0].segment_id == "seg_stream"
assert streamed_segments[0].speaker == "A"
assert streamed_transcription["usage"]["total_tokens"] == 1

print("Notebook demo validation passed")
```

## 步驟 10：跑 deterministic eval

這一段針對有標註的 demo fixture 跑一個小型的 deterministic eval。它還不是廣泛的正式環境 eval，但示範了在加入模型評分之前，怎麼用可重現的規則為抽取品質打分。

下面的 scorer 衡量行動項目的 precision/recall、明確問題的 precision/recall、沒有依據的決議、可為 null 的未知欄位，以及證據引用是否有效。正式環境請把 `GOLD_EVAL_LABELS` 換成更大的標註資料集，並對每個範例跑同樣的 scorer。


```python
GOLD_EVAL_LABELS: dict[str, Any] = {
    "action_items": [
        {
            "owner_speaker": "Solutions Engineer",
            "task_contains": ["send a prototype", "speaker-aware transcripts", "redaction pass", "crm sync"],
            "due_date_or_trigger": None,
            "evidence_segment_ids": ["seg_005"],
        }
    ],
    "explicit_questions": [
        {
            "question_contains": ["support handoff", "break down"],
            "asked_by_speaker": "Solutions Engineer",
            "directed_to_speaker": "Customer",
            "evidence_segment_ids": ["seg_001"],
        }
    ],
    "decisions": [],
}


def normalize_for_eval(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def evidence_ref_segment_ids(item: dict[str, Any]) -> set[str]:
    return {str(ref.get("segment_id", "")) for ref in item.get("evidence_refs", []) if isinstance(ref, dict)}


def contains_all_fragments(text: Any, fragments: list[str]) -> bool:
    normalized = normalize_for_eval(text)
    return all(normalize_for_eval(fragment) in normalized for fragment in fragments)


def action_item_matches_label(item: dict[str, Any], label: dict[str, Any]) -> bool:
    return (
        item.get("owner_speaker") == label.get("owner_speaker")
        and item.get("due_date_or_trigger") == label.get("due_date_or_trigger")
        and contains_all_fragments(item.get("task"), label.get("task_contains", []))
        and set(label.get("evidence_segment_ids", [])).issubset(evidence_ref_segment_ids(item))
    )


def explicit_question_matches_label(item: dict[str, Any], label: dict[str, Any]) -> bool:
    return (
        item.get("asked_by_speaker") == label.get("asked_by_speaker")
        and item.get("directed_to_speaker") == label.get("directed_to_speaker")
        and contains_all_fragments(item.get("question"), label.get("question_contains", []))
        and set(label.get("evidence_segment_ids", [])).issubset(evidence_ref_segment_ids(item))
    )


def precision_recall(predicted: list[dict[str, Any]], labels: list[dict[str, Any]], matcher) -> dict[str, Any]:
    matched_label_indexes: set[int] = set()
    matched_predictions = 0

    for item in predicted:
        for index, label in enumerate(labels):
            if index in matched_label_indexes:
                continue
            if matcher(item, label):
                matched_label_indexes.add(index)
                matched_predictions += 1
                break

    precision = matched_predictions / len(predicted) if predicted else (1.0 if not labels else 0.0)
    recall = len(matched_label_indexes) / len(labels) if labels else 1.0
    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "matched_predictions": matched_predictions,
        "predicted_count": len(predicted),
        "label_count": len(labels),
    }


def evidence_ref_count(intelligence: dict[str, Any]) -> int:
    return sum(len(refs) for _, refs in iter_evidence_refs(intelligence) if isinstance(refs, list)) + len(intelligence.get("notable_quotes", []))


def run_deterministic_evals(
    intelligence: dict[str, Any],
    segments: list[Segment],
    labels: dict[str, Any],
) -> dict[str, Any]:
    action_item_scores = precision_recall(
        intelligence.get("action_items", []),
        labels.get("action_items", []),
        action_item_matches_label,
    )
    explicit_question_scores = precision_recall(
        intelligence.get("explicit_questions", []),
        labels.get("explicit_questions", []),
        explicit_question_matches_label,
    )
    evidence_problems = validate_evidence_refs(intelligence, segments)
    total_evidence_refs = evidence_ref_count(intelligence)
    valid_evidence_ref_rate = (
        round((total_evidence_refs - len(evidence_problems)) / total_evidence_refs, 3)
        if total_evidence_refs
        else 1.0
    )
    action_items = intelligence.get("action_items", [])
    nullable_due_date_rate = (
        round(sum(1 for item in action_items if item.get("due_date_or_trigger") is None) / len(action_items), 3)
        if action_items
        else 1.0
    )
    unsupported_decision_count = len(intelligence.get("decisions", [])) if not labels.get("decisions") else 0

    pass_conditions = [
        action_item_scores["precision"] == 1.0,
        action_item_scores["recall"] == 1.0,
        explicit_question_scores["precision"] == 1.0,
        explicit_question_scores["recall"] == 1.0,
        valid_evidence_ref_rate == 1.0,
        nullable_due_date_rate == 1.0,
        unsupported_decision_count == 0,
    ]

    return {
        "status": "pass" if all(pass_conditions) else "review_required",
        "action_items": action_item_scores,
        "explicit_questions": explicit_question_scores,
        "valid_evidence_ref_rate": valid_evidence_ref_rate,
        "evidence_ref_problem_count": len(evidence_problems),
        "unsupported_decision_count": unsupported_decision_count,
        "nullable_due_date_rate": nullable_due_date_rate,
    }


deterministic_eval_report = run_deterministic_evals(
    demo_run["intelligence"],
    demo_run["segments"],
    GOLD_EVAL_LABELS,
)
show_json(deterministic_eval_report, expanded=True)
assert deterministic_eval_report["status"] == "pass"
```

## 步驟 11：加上可選的 LLM-as-judge eval

LLM-as-judge eval 適合評 deterministic scorer 無法完整捕捉的品質，例如摘要有沒有用、有沒有漏掉後續動作，以及這份簡報對審核者有沒有幫助。它要呼叫 API、而且會隨 judge 模型而有差異，所以保持選用。請搭配 deterministic scorer 一起用，不要取代它們。

下面的 judge 會收到逐字稿、結構化輸出和一份評分標準（rubric），然後回傳分數和審核發現。預設的不連網 notebook 執行請讓 `RUN_LLM_JUDGE_EVAL = False`。


```python
RUN_LLM_JUDGE_EVAL = False
LLM_JUDGE_MODEL = os.getenv("OPENAI_MEETING_INTELLIGENCE_JUDGE_MODEL", DEFAULT_SUMMARY_MODEL)

LLM_JUDGE_SCHEMA: dict[str, Any] = {
    "name": "meeting_intelligence_judge",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "outcome": {"type": "string", "enum": ["pass", "review", "fail"]},
            "overall_score": {"type": "number"},
            "scores": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "grounding": {"type": "number"},
                    "action_item_correctness": {"type": "number"},
                    "completeness": {"type": "number"},
                    "safety_review_readiness": {"type": "number"},
                },
                "required": ["grounding", "action_item_correctness", "completeness", "safety_review_readiness"],
            },
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "area": {"type": "string"},
                        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                        "explanation": {"type": "string"},
                    },
                    "required": ["area", "severity", "explanation"],
                },
            },
        },
        "required": ["outcome", "overall_score", "scores", "findings"],
    },
}


def run_llm_judge_eval(segments: list[Segment], intelligence: dict[str, Any], model: str = LLM_JUDGE_MODEL) -> dict[str, Any]:
    from openai import OpenAI

    client = OpenAI()
    transcript = transcript_for_model(segments)
    completion = client.responses.create(
        model=model,
        temperature=0,
        store=False,
        input=[
            {
                "role": "system",
                "content": (
                    "You are judging a meeting-intelligence extraction. Grade only against the transcript. "
                    "Penalize unsupported claims, missing major action items, missing customer risks, incorrect speaker attribution, "
                    "and outputs that are not ready for human review. Return calibrated scores from 0 to 1."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Transcript:\n"
                    f"{transcript}\n\n"
                    "Meeting intelligence JSON:\n"
                    f"{json.dumps(intelligence, indent=2)}"
                ),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": LLM_JUDGE_SCHEMA["name"],
                "strict": LLM_JUDGE_SCHEMA["strict"],
                "schema": LLM_JUDGE_SCHEMA["schema"],
            }
        },
    )
    return parse_meeting_intelligence_json(response_output_text_or_raise(completion))


if RUN_LLM_JUDGE_EVAL:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY before running the LLM judge eval.")
    llm_judge_report = run_llm_judge_eval(demo_run["segments"], demo_run["intelligence"])
    show_json(llm_judge_report, expanded=True)
else:
    print("Skipped LLM judge eval. Set RUN_LLM_JUDGE_EVAL = True after configuring OPENAI_API_KEY.")
```

## 正式環境強化檢查表

在把這個範例變成客戶流程之前，用這份檢查表過一遍：

| Concern | Recommendation |
| --- | --- |
| Consent | Make sure call recording, diarization, and known-speaker references are permitted in your product, policy, and region. |
| Raw audio retention | Store raw audio only as long as needed. Persist normalized transcript segments when possible. |
| Large recordings | Reject files over 25 MB before upload. Compress or split longer meetings, then preserve timestamp offsets when combining results. |
| PII and DLP | Treat the included email and phone regexes as illustrative only. Use a policy-approved PII/DLP detector and human review for sensitive or regulated workflows. |
| Speaker references | Treat reference clips as sensitive data. Store minimally, encrypt at rest, and rotate/delete when no longer needed. |
| Evidence | Require structured evidence references on decisions, risks, and action items. Validate that each reference points to a real segment ID and quote. |
| Human review | Route high-risk summaries, compliance promises, pricing claims, or contractual terms for review. |
| Moderation | Use the Moderation API for harmful-content classification when notes may contain unsafe content. Keep privacy and compliance checks separate. |
| Retry behavior | Retry transient API errors with backoff. Avoid duplicating downstream CRM writes by using idempotency keys. |
| Observability | Log model names, prompt versions, schema versions, audio duration, latency, redaction status, and reviewer decisions. |
| Evaluation | Sample calls weekly. Track speaker attribution accuracy, action-item precision, and unsupported-claim rate. |


## 正式環境的評估指引

上面的 deterministic eval 刻意做得很小：它證明這套評分模式在有標註的 fixture 上可行。在把輸出寫進下游系統之前，正式的團隊應該把它擴充成有代表性的 eval 集。從一小批取得同意的錄音或逐字稿 fixture 開始，建立人工審核過的標註，並保留一份 holdout 集，在 prompt、schema 或模型變動時做 regression 測試。

| Area | Example metrics |
| --- | --- |
| Speaker attribution | Speaker-label accuracy, diarization error rate, speaker-turn boundary accuracy, known-speaker match rate. |
| Transcript grounding | Quote exactness, timestamp correctness, evidence-reference validity, unsupported-claim rate. |
| Structured extraction | Precision and recall for action items, decisions, risks, explicit questions, suggested follow-ups, and customer requirements. |
| Safety and privacy | PII redaction recall, moderation flag recall, false-positive review rate, raw-audio retention compliance. |
| Workflow impact | Time-to-CRM-update, reviewer override rate, follow-up completion rate, renewal or escalation risk detection latency. |

一個實用的第一個 eval 很簡單：請審核者把每個抽出的行動項目標成正確、部分正確、沒有依據，或是輸出中漏掉的。對產生的項目追蹤 precision，對人工標註的標準答案追蹤 recall。對於引文和證據，優先用跟逐字稿 segment 文字做完全比對或近似完全比對的檢查，這樣聽起來有幫助但沒有依據的摘要才不會被漏放過去。LLM-as-judge 可以幫忙評有用程度和完整度，但請把 deterministic 的依據檢查留在流程裡，因為它們比較容易重現。


## 下一步

你可以把同一條 pipeline 改用在：
- 季度業務檢討（QBR）之後的客戶成功交接。
- 重視責任歸屬和原話引用的客服升級。
- 會餵給 CRM 下一步的業務探索通話。
- 每位面試官都需要有出處筆記的招募面試檢討。
- 需要更強審核和保留控制的醫療或金融服務流程。

即時的情境，請用 Realtime 做通話中的體驗，需要可留存、有證據支持的會議分析時，仍然要跑這條通話後的 diarization pipeline。

相關文件：

- [Audio and speech guide](https://developers.openai.com/api/docs/guides/audio)
- [Speech-to-text and speaker diarization](https://developers.openai.com/api/docs/guides/speech-to-text)
- [Structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [Moderation](https://developers.openai.com/api/docs/guides/moderation)
- [Safety best practices](https://developers.openai.com/api/docs/guides/safety-best-practices)
- [Realtime guide](https://developers.openai.com/api/docs/guides/realtime)


## 重點整理

- 光有逐字稿不夠，diarization 保留了「誰說的」，行動項目、風險和 email 草稿才不會把話記到錯的人身上。
- Diarization 只在單一錄音內分開聲音，不會跨錄音記住身分；要有真實名字，每次請求都要重新傳 reference clip。
- 強制每個抽出的項目附上 `segment_id` 和引文，程式就能機械式驗證有沒有依據，不用靠人眼相信摘要。
- 模型輸出不要直接寫進 CRM 或 ticket，中高風險、缺證據、moderation 被標記的內容要先過人工審核。
- 評估分兩層：deterministic scorer 管可重現的依據和 precision/recall，LLM-as-judge 管有用程度，兩者搭配而不是互相取代。

## 練習

1. 把 `KNOWN_SPEAKERS` 的設定改成只給一位講者的 reference clip（或完全不給），跑一次 demo 或真實音訊，看輸出裡講者標籤從名字變回 `speaker_0` 的差別。
2. 在 guardrail 步驟用的 regex redaction helper 裡，多加一個格式（例如簡單的信用卡號或身分證字號樣式），然後在 demo 的合成逐字稿塞一句含有該格式的話，確認 `guardrail_report.json` 有抓到。
3. 在 `GOLD_EVAL_LABELS` 裡新增一筆你自己設計的行動項目，故意讓 demo 的預期輸出漏掉它，跑 deterministic eval，觀察 action-item recall 怎麼掉，再想想要怎麼調 prompt 或 schema 補回來。
