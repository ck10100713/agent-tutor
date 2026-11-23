---
translated: true
source: observability/opentelemetry_tracing.ipynb
---
# 用 OpenTelemetry 追蹤 Claude API 請求和 Managed Agents session

> 原文：[observability/opentelemetry_tracing.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/observability/opentelemetry_tracing.ipynb)

逐個 attribute 讀懂 Python SDK 為 Messages API 請求、stream、tool runner 迴圈和 Managed Agents session 發出的 OpenTelemetry span。接著匯出到 OTLP backend，再加上 Console destination，讓 API 在伺服器端產生的 span 也進到同一條 trace。

## 這篇在做什麼

Claude 請求變慢或變貴時，光看請求本身不知道時間和 token 花在哪。這篇用 OpenTelemetry span 把它攤開：先在本機印出 SDK 發出的 span，逐個 attribute 解讀，再把 SDK 和 Managed Agents 的 span 巢狀地放進你自己的 span 底下。最後設定匯出，讓 API 端的 span 也串進同一條 trace。

## 學完你會

- 逐個讀懂 SDK span 的 attribute，知道哪些該拿來告警、分組、加總。
- 把 SDK span 巢狀放進你自己的 span 底下，涵蓋一般請求、stream、tool 迴圈和 Managed Agents session。
- 匯出到 OTLP backend，並加上 Console destination，讓 API 的 span 跟 SDK 的 span 在同一條 trace。

## 開跑前

- Claude API 憑證：`ANTHROPIC_API_KEY`（環境變數或 notebook 旁的 `.env`），或 `ant auth login` 的 profile。在 Colab 的話，把金鑰放進 Secrets，再讀進環境變數。
- 第 6 節需要 Managed Agents beta 權限，會建一個雲端 environment 和一個短 session。
- 選用：第 7 節要一個 OTLP endpoint 和它的 auth header；第 8 節要 Anthropic 組織的 admin 角色。

---

一個變慢或變貴的 Claude 請求不會告訴你時間和 token 花在哪。OpenTelemetry（OTel）span 會，而且 span 來自兩個地方。Claude SDK 在你的 process 裡發出 span，每送一個請求一個。Claude API 在 Anthropic 那邊，針對每個請求內部的工作發出 span，直接送到你的 observability backend。SDK 會在每個請求加上 `traceparent` header，API 把它的 span 掛在底下，所以兩邊會跟你自己的 handler 和資料庫 span 一起落在同一條 trace。

這個 notebook 會即時印出 SDK 的 span。API 的 span 不會經過你的 process，所以這裡用參考用的樹狀圖呈現。兩邊都還在 beta：span 名稱和 attribute 在版本之間可能改變。

*Span* 是一個有計時的步驟，帶名稱、kind、狀態和 key-value attribute。*Trace* 是共用同一個 trace ID 的 span 樹。

| | SDK span | API span |
|---|---|---|
| 由誰發出 | `anthropic` 套件，在你的 process 內 | Claude API，在 Anthropic 內部 |
| 涵蓋 | SDK 送出的每個請求，以及它的 tool-runner helper 執行的每個 tool（第 5 節） | API 在請求內部做的事：每次模型執行、每個伺服器端 tool（如 `web_search`）、每次 context 壓縮，以及每個 Managed Agents turn（第 6 節） |
| Span kind | 請求是 `CLIENT`，tool 是 `INTERNAL` | 請求是 `SERVER`，內部的步驟是 `INTERNAL` |
| 怎麼收到 | 你自己的 OTel exporter（第 7 節） | 一個 *destination*：你的 backend 的 OTLP（OpenTelemetry Protocol）HTTPS endpoint 加 auth header，在 Console 註冊一次（第 8 節） |
| 怎麼串起來 | 每個請求上的 `traceparent` header | API 讀那個 header，把它的 span 掛到 SDK 的 span 底下 |
| 可用範圍 | Claude API、Amazon Bedrock、Google Vertex AI、Microsoft Foundry | 只有 Claude API |

兩邊都用 [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai)，所以看得懂 `gen_ai.*` attribute 的 backend 不用自訂對應就能顯示模型、token 數和訊息。Span 名稱和 attribute 在各官方 SDK 之間是一樣的。

做完之後你可以：

- 逐個 attribute 讀 SDK span，知道哪些要拿來告警、分組、加總
- 把 SDK span 巢狀放進你自己的 span：一般請求、stream、tool 迴圈和 Managed Agents session
- 匯出到 OTLP backend，並加上讓 API 的 span 進到同一條 trace 的 Console destination

**文件**

- [OpenTelemetry for the Claude API](https://platform.claude.com/docs/en/manage-claude/opentelemetry)：概覽、content mode、範例 trace、token 計算
- [Use OpenTelemetry with the Claude SDK](https://platform.claude.com/docs/en/manage-claude/opentelemetry/sdk)：各語言的設定、所有 client 選項和環境變數
- [Use OpenTelemetry with the Claude API](https://platform.claude.com/docs/en/manage-claude/opentelemetry/api)：destination、傳送、對整段對話取樣
- [OpenTelemetry span reference](https://platform.claude.com/docs/en/api/opentelemetry/spans)：每個 span、attribute 和父子關係

## 1. 設定

**前置條件**

- Claude API 憑證：`ANTHROPIC_API_KEY`（在環境或 notebook 旁的 `.env`），或 `ant auth login` 的 profile。`anthropic.Anthropic()` 兩種都會自己找到
- Python 3.11+
- 熟悉 [Messages API](https://platform.claude.com/docs/en/api/messages)。第 6 節假設你懂 [Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 的基本概念，需要 Managed Agents beta 權限，並會建一個雲端 environment 和一個短 session
- 選用，給第 7 節：一個 OTLP endpoint 和它的 auth header
- 選用，給第 8 節：你 Anthropic 組織的 admin 角色

`anthropic` 套件只依賴 `opentelemetry-api`，這是介面套件，本身什麼都不記錄。要一起裝 `opentelemetry-sdk` 和一個 exporter：

```python
%%capture
%pip install -qU "anthropic>=1.14.0" opentelemetry-sdk opentelemetry-exporter-otlp-proto-http python-dotenv
```

*Tracer provider* 建立 span 並交給 *span processor*，processor 再傳給 *exporter*。這個 notebook 在同一個 provider 上註冊兩個 processor：

- 一個記憶體內的 exporter，讓每一節都能印出它產生的 span
- 一個 OTLP exporter，只有設了 `OTEL_EXPORTER_OTLP_ENDPOINT` 才會加，讓同樣的 span 也送到你的 backend（第 7 節）

`trace.set_tracer_provider()` 讓這個 provider 變成全域的。SDK 會發到全域 provider，所以 `anthropic.Anthropic()` 不需要任何追蹤參數。要在第一個想追蹤的呼叫之前註冊好 provider。

```python
import json
import os
from collections import defaultdict

import anthropic
from dotenv import load_dotenv
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

load_dotenv()

MODEL = os.environ.get("COOKBOOK_MODEL", "claude-sonnet-5-5")
BETAS = ["managed-agents-2026-04-01"]  # beta header for the Managed Agents calls in section 6

# service.name is how your backend labels these spans. The API's spans arrive as "claude-platform".
provider = TracerProvider(resource=Resource.create({"service.name": "otel-cookbook"}))

memory_exporter = InMemorySpanExporter()
provider.add_span_processor(SimpleSpanProcessor(memory_exporter))

if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    # Reads OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS from the environment.
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))

trace.set_tracer_provider(provider)
tracer = trace.get_tracer("otel-cookbook")

client = anthropic.Anthropic()
print("anthropic", anthropic.__version__)
client.open_telemetry
```

??? note "輸出"

    ```text
    anthropic 1.13.0
    ```

    ```text
    {'propagation': True,
     'traces': {'enabled': True,
      'content_mode': 'metadata_only',
      'max_content_bytes': 750000}}
    ```

`client.open_telemetry` 顯示合併了 constructor 參數和 `ANTHROPIC_OPEN_TELEMETRY*` 環境變數之後的追蹤設定。[SDK 指南](https://platform.claude.com/docs/en/manage-claude/opentelemetry/sdk)列出所有選項，包括用 `open_telemetry=False` 對單一 client 關掉 span。追蹤和 `traceparent` 傳遞是開的，`content_mode` 是 `metadata_only`：span 帶識別碼、時間、token 數，以及你的 tool 和 agent 的名稱與描述，但不含 prompt 和回應。

下一個 cell 定義 `print_traces()`，它把收集到的 span 印成樹狀，帶出 `KEY_ATTRIBUTES` 列的 attribute，然後清空緩衝。傳 `show="all"` 會印出每個 attribute。

```python
KEY_ATTRIBUTES = [
    "gen_ai.operation.name",
    "gen_ai.request.model",
    "gen_ai.request.stream",
    "gen_ai.response.model",
    "gen_ai.conversation.id",
    "gen_ai.agent.id",
    "gen_ai.agent.name",
    "anthropic.session.id",
    "anthropic.session.environment.id",
    "anthropic.environment.id",
    "gen_ai.tool.name",
    "gen_ai.tool.call.id",
    "anthropic.message.stop_reason",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.cache_read.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.response.time_to_first_chunk",
    "anthropic.request.id",
    "http.response.status_code",
    "error.type",
    "gen_ai.system_instructions",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.tool.call.arguments",
    "anthropic.tool_result.content",
    "anthropic.content.truncated",
]


def print_traces(show: str = "key") -> None:
    spans = sorted(memory_exporter.get_finished_spans(), key=lambda s: s.start_time or 0)
    memory_exporter.clear()
    span_ids = {s.context.span_id for s in spans}
    children = defaultdict(list)
    roots = []
    for s in spans:
        parent_id = s.parent.span_id if s.parent else None
        (children[parent_id] if parent_id in span_ids else roots).append(s)

    def walk(span, depth):
        pad = "    " * depth
        seconds = (span.end_time - span.start_time) / 1e9
        kind, status = span.kind.name, span.status.status_code.name
        print(f"{pad}{span.name}  [{kind}  {status}  {seconds:.2f}s]")
        if show == "all":
            keys = list(span.attributes)
        else:
            keys = [k for k in KEY_ATTRIBUTES if k in span.attributes]
        for k in keys:
            print(f"{pad}  │ {k} = {span.attributes[k]}")
        for child in children[span.context.span_id]:
            walk(child, depth + 1)

    for root in roots:
        print(f"── trace {root.context.trace_id:032x}")
        walk(root, 0)
        print()
```

## 2. 追蹤一個 Messages API 請求

送一個請求，印出它 span 上的每個 attribute。`with_raw_response` 只是為了顯示 SDK 附上的 `traceparent` header。單純的 `client.messages.create()` 會產生同樣的 span。

```python
raw = client.messages.with_raw_response.create(
    model=MODEL,
    max_tokens=100,
    messages=[{"role": "user", "content": "In one word, what is the capital of France?"}],
)
message = raw.parse()
print("Claude:", message.content[0].text)
print("traceparent sent:", raw.http_response.request.headers["traceparent"])
print()
print_traces(show="all")
```

??? note "輸出"

    ```text
    Claude: Paris
    traceparent sent: 00-1d5dcf464f37ba0cf3357bef68d5319e-a33e2f3d458804bc-03

    ── trace 1d5dcf464f37ba0cf3357bef68d5319e
    anthropic.messages.create  [CLIENT  OK  0.69s]
      │ server.address = api.anthropic.com
      │ server.port = 443
      │ http.request.method = POST
      │ http.route = /v1/messages
      │ gen_ai.provider.name = anthropic
      │ gen_ai.operation.name = chat
      │ gen_ai.request.model = claude-sonnet-5-5
      │ gen_ai.request.max_tokens = 100
      │ url.scheme = https
      │ url.path = /v1/messages
      │ url.full = https://api.anthropic.com/v1/messages
      │ anthropic.request.id = req_011Cg1MqD5J9qv8hW8Nr9hJ6
      │ anthropic.organization.id = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
      │ anthropic.workspace.id = wrkspc_xxxxxxxxxxxxxxxxxxxxxxxx
      │ gen_ai.response.id = msg_011Cg1MqDLRghkLPbApauf2r
      │ gen_ai.response.model = claude-sonnet-5-5
      │ anthropic.message.stop_reason = end_turn
      │ gen_ai.usage.input_tokens = 20
      │ gen_ai.usage.cache_write.input_tokens = 0
      │ gen_ai.usage.cache_read.input_tokens = 0
      │ anthropic.usage.cache_creation.ephemeral_5m_input_tokens = 0
      │ anthropic.usage.cache_creation.ephemeral_1h_input_tokens = 0
      │ anthropic.response.service_tier = standard
      │ gen_ai.usage.output_tokens = 5
      │ gen_ai.usage.reasoning.output_tokens = 0
      │ http.response.status_code = 200
    ```

### 怎麼讀這個 span

**名稱和 kind。** 名稱是 `anthropic.` 加上用點連起來的 API 方法、去掉 `beta`：`client.messages.create()` 變成 `anthropic.messages.create`，`client.beta.sessions.events.send()` 變成 `anthropic.sessions.events.send`。Kind 是 `CLIENT`，因為這是 SDK 對外送請求的視角。同一個請求在 API 端的 span 名稱相同，kind 是 `SERVER`，到你的 backend 之後會直接掛在這個 span 底下（第 8 節）。

**狀態。** `OK` 代表呼叫有回來。`ERROR` 代表它拋出例外，`error.type` 說明原因：API 錯誤類型如 `rate_limit_error` 或 `overloaded_error`、HTTP 狀態如 `502`，或傳輸失敗時的 `connection_error` / `client_timeout_error`。一個 span 涵蓋整個呼叫，包括重試；SDK 重試過的話會出現 `http.request.resend_count`。

**`traceparent` header** 是 API 找到這個 span 的方式。格式是 `00-<trace id>-<span id>-<flags>`。Trace ID 跟它下面印的一樣，span ID 是這個 span 的，所以 API 會把它的 `SERVER` span 掛在這裡。`flags` 裡，bit 0 是 sampled 旗標，bit 1 標示 trace ID 是隨機的，所以 `03` 表示兩者都有。SDK 透過你應用程式的全域 *propagator*（把 trace context 序列化進 header 的 OTel 元件）寫入這個 header，所以如果你系統其他部分設定的是別種格式如 B3，也要加上 W3C trace-context propagator，否則 API 讀不到。

**Attribute，依群組：**

| 群組 | Attribute | 告訴你什麼 |
|---|---|---|
| Operation | `gen_ai.operation.name=chat`、`gen_ai.provider.name=anthropic` | GenAI 慣例的標記，backend 用來辨識這是 LLM 呼叫 |
| Request | `gen_ai.request.model`、`gen_ai.request.max_tokens`，以及你有設的話：`gen_ai.request.temperature`、`gen_ai.request.top_p`、`gen_ai.request.top_k`、`gen_ai.request.stream`、`gen_ai.request.reasoning.level`（`effort` 設定）、`anthropic.thinking.type`、`anthropic.beta` | 你要求了什麼 |
| Response | `gen_ai.response.id`（`msg_` ID）、`gen_ai.response.model`、`anthropic.message.stop_reason`、`anthropic.response.service_tier` | 回來了什麼。如果你傳的是 alias，或由 fallback 模型處理了請求，`response.model` 會跟 `request.model` 不同。對 `stop_reason=max_tokens` 設告警可以抓到被截斷的答案 |
| Usage | `gen_ai.usage.input_tokens`、`gen_ai.usage.output_tokens`、`gen_ai.usage.cache_read.input_tokens`、`gen_ai.usage.cache_write.input_tokens`、`anthropic.usage.cache_creation.ephemeral_5m_input_tokens` 和 `ephemeral_1h_input_tokens`、`gen_ai.usage.reasoning.output_tokens` | Token 數。`gen_ai.usage.input_tokens` 等於 `Message` 物件的 `usage.input_tokens + cache_read_input_tokens + cache_creation_input_tokens`，所以已經包含 cache 的 attribute，不能再加一次。Reasoning（thinking）的 token 包含在 `output_tokens` 裡 |
| Correlation | `anthropic.request.id`、`anthropic.organization.id`、`anthropic.workspace.id` | `anthropic.request.id` 就是 `request-id` response header：回報給 support 時引用它，也用它把這個 span 跟 API 的 `SERVER` span 配對。Organization 和 workspace ID 讓你在共用的 backend 裡按 workspace 拆流量 |
| HTTP | `http.request.method`、`http.route`、`http.response.status_code`、`url.full`，以及其他 `url.*` 和 `server.*` client attribute | 標準的 HTTP client 語意，所以一般的 HTTP dashboard 也能用 |

## 3. 把 SDK span 巢狀放進你自己的 span，並記錄內容

跟第 2 節相比：

1. 呼叫在 `tracer.start_as_current_span("answer_question")` 裡執行，所以 SDK span 成為它的子 span。實際上外層 span 會是你的 request handler 或背景工作。
2. 第二個 client 把 `traces.content_mode` 設成 `content`。它的 span 會多出 `gen_ai.system_instructions`、`gen_ai.input.messages` 和 `gen_ai.output.messages`。環境變數 `ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE=content` 對所有 client 有同樣效果。
3. `with_options()` 用 `conversation_id` 標記這次呼叫，它會變成 `gen_ai.conversation.id`。多輪對話裡每個請求都給同一個 ID，backend 才能把它們歸成一組。這個 ID 即使在 `metadata_only` 模式也會匯出，所以不要放使用者資料。`with_options()` 會整個取代 `open_telemetry` 選項而不是合併，所以要把 client 目前的值展開進新的，就像這個 cell 用 `content_client.open_telemetry` 做的那樣。

```python
content_client = anthropic.Anthropic(open_telemetry={"traces": {"content_mode": "content"}})
conversation = content_client.with_options(
    open_telemetry={**content_client.open_telemetry, "conversation_id": "conv_sky_0001"}
)

with tracer.start_as_current_span("answer_question"):
    reply = conversation.messages.create(
        model=MODEL,
        max_tokens=200,
        system="Answer in one short sentence.",
        messages=[{"role": "user", "content": "Why is the sky blue?"}],
    )
print("Claude:", reply.content[0].text)
print()
print_traces()
```

??? note "輸出"

    ```text
    Claude: The sky looks blue because air molecules scatter short-wavelength blue light from the sun much more strongly than longer-wavelength red light, sending blue light to our eyes from every direction.

    ── trace 52022f8b623ba8736bbe49dd41134822
    answer_question  [INTERNAL  UNSET  0.93s]
        anthropic.messages.create  [CLIENT  OK  0.93s]
          │ gen_ai.operation.name = chat
          │ gen_ai.request.model = claude-sonnet-5-5
          │ gen_ai.response.model = claude-sonnet-5-5
          │ gen_ai.conversation.id = conv_sky_0001
          │ anthropic.message.stop_reason = end_turn
          │ gen_ai.usage.input_tokens = 28
          │ gen_ai.usage.cache_read.input_tokens = 0
          │ gen_ai.usage.output_tokens = 61
          │ anthropic.request.id = req_011Cg1MqGVBR9wQkir7ZK9Qf
          │ http.response.status_code = 200
          │ gen_ai.system_instructions = [{"type":"text","content":"Answer in one short sentence."}]
          │ gen_ai.input.messages = [{"role":"user","parts":[{"type":"text","content":"Why is the sky blue?"}]}]
          │ gen_ai.output.messages = [{"role":"assistant","parts":[{"type":"text","content":"The sky looks blue because air molecules scatter short-wavelength blue light from the sun much more strongly than longer-wavelength red light, sending blue light to our eyes from every direction."}]}]
    ```

你的 `answer_question` span 狀態是 `UNSET`，因為你的程式碼沒有設定。Backend 把 `UNSET` 當成功處理，所以沒問題。

三個 content attribute 是 JSON 字串，採 GenAI 慣例的訊息格式，不是 Messages API 的格式。每則訊息是 `{"role", "parts": [...]}`，每個 part 有一個 `type`：

| Messages API 區塊 | Span 裡的 part |
|---|---|
| `text` | `{"type": "text", "content": "..."}` |
| `thinking` | `{"type": "reasoning", "content": "..."}`（區塊的 `signature` 欄位會被丟掉） |
| `tool_use`、`server_tool_use`、`mcp_tool_use` | `{"type": "tool_call", "id", "name", "arguments"}` |
| `tool_result` 和伺服器端 tool 結果 | `{"type": "tool_call_response", "id", "response": [...]}` |
| `image`、`document`、其他任何東西 | `{"type": "anthropic_image"}` 之類：只有 type，絕不含資料 |

SDK 對每個 span 的內容上限是 750,000 bytes（`traces.max_content_bytes`）。超過時它保留最新的幾輪（也就是你 debug 要看的那些）：先移除 system prompt 和最早的訊息，並設 `anthropic.content.truncated=true`。欄位上限小的 backend 需要更低的上限，例如 Honeycomb 的 64 KB 欄位可以用 `{"traces": {"max_content_bytes": 50_000}}`。
Prompt 和回應常含使用者資料，匯出之後就受你 backend 的保留政策管轄，不是 Anthropic 的。除非你的資料處理政策涵蓋匯出 prompt，否則正式環境請維持 `metadata_only`。`metadata_only` 仍然會匯出 tool 名稱和描述、agent 名稱、MCP（Model Context Protocol）server 名稱，以及你的 `conversation_id`。

## 4. 追蹤 stream

Stream 請求用同樣的 span 名稱，多兩個 attribute：`gen_ai.request.stream=true`，以及 `gen_ai.response.time_to_first_chunk`，也就是從送出請求到第一個 `content_block_delta` event 的秒數。把後者當成你的 time-to-first-token 指標。Extended thinking 在 stream 時，第一個 delta 是 thinking delta，不是看得到的文字。

```python
with tracer.start_as_current_span("stream_haiku"):
    with content_client.messages.stream(
        model=MODEL,
        max_tokens=2000,
        messages=[{"role": "user", "content": "Write a haiku about distributed tracing."}],
    ) as stream:
        for text in stream.text_stream:
            print(text, end="", flush=True)
print("\n")
print_traces()
```

??? note "輸出"

    ```text
    A request departs,
    spans bloom through a hundred hops,
    one trace ID binds.

    ── trace 0876bf2b7afa9308edae081812829315
    stream_haiku  [INTERNAL  UNSET  1.47s]
        anthropic.messages.create  [CLIENT  OK  1.47s]
          │ gen_ai.operation.name = chat
          │ gen_ai.request.model = claude-sonnet-5-5
          │ gen_ai.request.stream = True
          │ gen_ai.response.model = claude-sonnet-5-5
          │ anthropic.message.stop_reason = end_turn
          │ gen_ai.usage.input_tokens = 22
          │ gen_ai.usage.cache_read.input_tokens = 0
          │ gen_ai.usage.output_tokens = 167
          │ gen_ai.response.time_to_first_chunk = 0.459185962
          │ anthropic.request.id = req_011Cg1MqL8CWWD7WAudzj5UY
          │ http.response.status_code = 200
          │ gen_ai.input.messages = [{"role":"user","parts":[{"type":"text","content":"Write a haiku about distributed tracing."}]}]
          │ gen_ai.output.messages = [{"role":"assistant","parts":[{"type":"reasoning","content":"Haiku 5-7-5. Let me write.\n\n\"A request departs—\" count: A(1) re-quest(2) de-parts(2) =5. \n\"spans bloom through a hundred hops,\" spans(1) bloom(1) through(1) a(1) hun-dred(2) hops(1) =7.\n\"one trace ID binds.\" one(1) trace(1) I-D(2) binds(1)=5.\n\nGood."},{"type":"text","content":"A request departs,\nspans bloom through a hundred hops,\none trace ID binds."}]}]
    ```

如果模型回答前有思考，`gen_ai.output.messages` 會在 `text` part 前面有一個 `reasoning` part。這就是 `thinking` 區塊的 span 形式（第 3 節的表格），它的 token 算在 `gen_ai.usage.output_tokens` 裡，所以一首 17 音節的俳句可以花到一百多個 output token。

Stream span 的規則：

- Span 在 stream 被讀到底或被關閉時結束，不是在 header 到達時。它的持續時間是整個回應的實際經過時間。如果提早停止讀取，要關閉 stream（`with` 區塊會幫你做），否則 span 會一直開著。提早關閉的 stream 以 `UNSET` 結束，不是 `OK`。
- 只有 `messages.stream()` 會記錄 `gen_ai.output.messages`，因為它會累積最終的訊息。`messages.create(stream=True)` 吐出的是原始 event，所以它的 span 有 usage 和 stop reason，但沒有輸出內容。
- 你在讀取迴圈裡開的 span 是 SDK span 的兄弟，不是子 span，因為迴圈本體執行時 SDK span 不是目前的 span。想把每個 chunk 的處理跟請求歸成一組，就把呼叫和迴圈一起包在你自己的 span 裡，就像這裡的 `stream_haiku` 那樣。

## 5. 追蹤 tool runner

`client.beta.messages.tool_runner()` 會在 Claude 和你的 tool 之間來回，直到 Claude 不再要求 tool。開了追蹤之後，迴圈、每個請求和每次 tool 執行都有自己的 span。這棵樹能看出一個問題花了幾次來回、時間花在哪。

```python
from anthropic import beta_tool


@beta_tool
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    # A real tool would call a weather API here. With HTTP client instrumentation
    # installed, that call would get its own span under this tool's span.
    return json.dumps({"city": city, "temp_c": 18, "conditions": "fog"})


with tracer.start_as_current_span("weather_question"):
    runner = content_client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=500,
        tools=[get_weather],
        messages=[{"role": "user", "content": "Weather in San Francisco? One sentence."}],
    )
    final = runner.until_done()
print("Claude:", final.content[-1].text)
print()
print_traces()
```

??? note "輸出"

    ```text
    Claude: San Francisco is foggy right now, with a temperature of 18°C (about 64°F).

    ── trace de0633442f5078398a8c8dec46514cf4
    weather_question  [INTERNAL  UNSET  1.94s]
        anthropic.messages.tool_runner  [INTERNAL  OK  1.94s]
          │ gen_ai.operation.name = invoke_agent
          │ gen_ai.request.model = claude-sonnet-5-5
            anthropic.messages.create  [CLIENT  OK  1.31s]
              │ gen_ai.operation.name = chat
              │ gen_ai.request.model = claude-sonnet-5-5
              │ gen_ai.response.model = claude-sonnet-5-5
              │ anthropic.message.stop_reason = tool_use
              │ gen_ai.usage.input_tokens = 397
              │ gen_ai.usage.cache_read.input_tokens = 0
              │ gen_ai.usage.output_tokens = 52
              │ anthropic.request.id = req_011Cg1MqSatuPgV7MCvqiegX
              │ http.response.status_code = 200
              │ gen_ai.input.messages = [{"role":"user","parts":[{"type":"text","content":"Weather in San Francisco? One sentence."}]}]
              │ gen_ai.output.messages = [{"role":"assistant","parts":[{"type":"tool_call","id":"toolu_01Fco8q4hEyZ4QFHvejscxZP","name":"get_weather","arguments":{"city":"San Francisco"}}]}]
            anthropic.custom_tool_use get_weather  [INTERNAL  OK  0.00s]
              │ gen_ai.operation.name = execute_tool
              │ gen_ai.tool.name = get_weather
              │ gen_ai.tool.call.id = toolu_01Fco8q4hEyZ4QFHvejscxZP
              │ gen_ai.tool.call.arguments = {"city":"San Francisco"}
              │ anthropic.tool_result.content = [{"type":"text","text":"{\"city\": \"San Francisco\", \"temp_c\": 18, \"conditions\": \"fog\"}"}]
            anthropic.messages.create  [CLIENT  OK  0.59s]
              │ gen_ai.operation.name = chat
              │ gen_ai.request.model = claude-sonnet-5-5
              │ gen_ai.response.model = claude-sonnet-5-5
              │ anthropic.message.stop_reason = end_turn
              │ gen_ai.usage.input_tokens = 484
              │ gen_ai.usage.cache_read.input_tokens = 0
              │ gen_ai.usage.output_tokens = 31
              │ anthropic.request.id = req_011Cg1MqYBVGjkuKxFDq79LQ
              │ http.response.status_code = 200
              │ gen_ai.input.messages = [{"role":"user","parts":[{"type":"text","content":"Weather in San Francisco? One sentence."}]},{"role":"assistant","parts":[{"type":"tool_call","id":"toolu_01Fco8q4hEyZ4QFHvejscxZP","name":"get_weather","arguments":{"city":"San Francisco"}}]},{"role":"user","parts":[{"type":"tool_call_response","id":"toolu_01Fco8q4hEyZ4QFHvejscxZP","response":[{"type":"text","text":"{\"city\": \"San Francisco\", \"temp_c\": 18, \"conditions\": \"fog\"}"}]}]}]
              │ gen_ai.output.messages = [{"role":"assistant","parts":[{"type":"text","content":"San Francisco is foggy right now, with a temperature of 18°C (about 64°F)."}]}]
    ```

- **`anthropic.messages.tool_runner`**（`INTERNAL`，`gen_ai.operation.name=invoke_agent`）涵蓋整個迴圈。它的持續時間就是這個問題端到端的延遲。它沒有 usage attribute，所以算成本要加總它的子 span。如果你要停掉一個不會再繼續的 runner，呼叫 `runner.close()`，它也會結束這個 span。
- **第一個 `anthropic.messages.create`** 以 `anthropic.message.stop_reason=tool_use` 結束，在 content mode 下它的 `gen_ai.output.messages` 有一個 `tool_call` part，帶著 Claude 選的參數。
- **`anthropic.custom_tool_use get_weather`**（`INTERNAL`，`gen_ai.operation.name=execute_tool`）是你的函式在執行。Tool span 的名稱是 tool 種類、一個空格、再加 tool 名稱。`gen_ai.tool.call.id` 是這三個 span 之間的 join key：同一個 `toolu_` ID 出現在前一個請求輸出裡的 `tool_call` part，也出現在下一個請求輸入裡的 `tool_call_response` part。在 content mode 下，`gen_ai.tool.call.arguments` 和 `anthropic.tool_result.content` 存放輸入和輸出。如果函式拋出例外，這個 span 的狀態是 `ERROR`、`error.type=tool_error`，迴圈會繼續，把錯誤文字當作 tool 結果。
- **第二個 `anthropic.messages.create`** 以 `end_turn` 結束。它的 `gen_ai.usage.input_tokens` 因為 tool 呼叫和結果而變多，這就是這趟來回看得見的成本。

Tool span 有三種：

- `anthropic.custom_tool_use <name>`：你定義、由 SDK tool runner 執行的 tool。只有 SDK span。
- `anthropic.mcp_tool_use <name>`：來自 MCP server 的 tool，由 SDK 的 MCP helper 或 API 的 MCP connector 執行。
- `anthropic.tool_use <name>`：伺服器端 tool 如 `web_search`，或 Managed Agents 預建 toolset 裡的 tool 如 `bash`，由 API 執行。只有 API span，在 Messages API 上掛在請求的 `SERVER` span 底下，在 Managed Agents session 裡掛在 turn span 底下。

## 6. 追蹤 Managed Agents session

Managed Agents session 在 Anthropic 的基礎設施上、在一個 *environment*（agent 的 tool 執行所在的容器）裡跑 agent 迴圈，所以 turn、model-request 和 toolset-tool 的 span 都是 API span。SDK 對每個 Sessions API 請求貢獻一個 span，它的 `traceparent` header 把 API 的 turn span 拉進你的 trace。你在本機執行的自訂 tool，span 由你自己給。

這個範例定義一個帶預建 toolset（`agent_toolset_20260401`：bash、檔案讀寫編輯和搜尋 tool）加一個自訂 tool 的 agent，然後把 `initial_events` 傳給 `sessions.create`，讓 session 和它的第一個 turn 在同一個請求裡開始。API 把 turn 掛在啟動它的請求底下，所以第一個 `anthropic.session.turn` span 在 `anthropic.sessions.create` 底下。沒有 `initial_events` 的話，它會在第一個 `sessions.events.send` 底下。

```python
agent = client.beta.agents.create(
    name="release-notes-helper",
    description="Looks up a package version and reports on it.",
    model=MODEL,
    system="You are concise. Use tools when they help. Reply in two sentences or fewer.",
    tools=[
        {"type": "agent_toolset_20260401"},
        {
            "type": "custom",
            "name": "get_latest_version",
            "description": "Return the latest released version of a package on the internal registry.",
            "input_schema": {
                "type": "object",
                "properties": {"package": {"type": "string"}},
                "required": ["package"],
            },
        },
    ],
    betas=BETAS,
)
environment = client.beta.environments.create(
    name="otel-cookbook",
    config={
        "type": "anthropic_cloud",
        "networking": {"type": "limited"},
    },  # no outbound network needed
    betas=BETAS,
)
print(f"agent {agent.id} v{agent.version}, environment {environment.id}")
print_traces()
```

??? note "輸出"

    ```text
    agent agent_01Rn9W7qwgEHGV6cNc9Kmgpx v1, environment env_01KqmS21fqFhcjWuufz33532
    ── trace ff57054bb43bf540b4baeb9ace55354f
    anthropic.agents.create  [CLIENT  OK  0.16s]
      │ gen_ai.agent.id = agent_01Rn9W7qwgEHGV6cNc9Kmgpx
      │ anthropic.request.id = req_011Cg1Mqad5pkAMgdir3L3mq
      │ http.response.status_code = 200

    ── trace f45b9758bf9bbe4925326bb443a9fb01
    anthropic.environments.create  [CLIENT  OK  0.29s]
      │ anthropic.environment.id = env_01KqmS21fqFhcjWuufz33532
      │ anthropic.request.id = req_011Cg1MqbJ1hyVqRJiQNUVTE
      │ http.response.status_code = 200
    ```

建立資源的呼叫會把新的 ID 放在它的 span 上（`gen_ai.agent.id`、`anthropic.environment.id`），所以你可以找到建立任何資源的那個請求。

下一個 cell 把 session 包在一個 `handle_ticket` span 裡，就像 web handler 或 queue consumer 會做的那樣。裡面：

1. 帶 `initial_events` 的 `sessions.create` 建出已經是 `running` 狀態的 session。
2. 迴圈讀 event 串流直到 `session.status_idle`。當 stop reason 是 `requires_action`，代表 agent 在等自訂 tool，程式碼就在自己的 span 裡執行它，並送出 `user.custom_tool_result`。那個 `events.send` 請求會開始第二個 turn，迴圈再重新打開串流去讀它，這就是輸出裡有兩個 `events.stream` span 的原因。
3. 其他任何 stop reason（`end_turn`、`retries_exhausted`），迴圈就結束。

```python
import datetime


def get_latest_version(package: str) -> str:
    released = datetime.date.today() - datetime.timedelta(days=3)
    return json.dumps({"package": package, "version": "4.2.0", "released": released.isoformat()})


with tracer.start_as_current_span("handle_ticket") as span:
    session = client.beta.sessions.create(
        agent=agent.id,
        environment_id=environment.id,
        title="OTel cookbook demo",
        initial_events=[
            {
                "type": "user.message",
                "content": [
                    {
                        "type": "text",
                        "text": "Find the latest version of the `acme-billing` package with your tool, "
                        f"then use bash to compute how many days ago it was released (today is {datetime.date.today()}).",
                    }
                ],
            }
        ],
        betas=BETAS,
    )
    span.set_attribute("anthropic.session.id", session.id)
    print(f"session {session.id} is {session.status}\n")

    pending_tool_calls = {}
    done = False
    while not done:
        with client.beta.sessions.events.stream(session.id, betas=BETAS) as events:
            for event in events:
                if event.type == "agent.custom_tool_use":
                    pending_tool_calls[event.id] = event
                elif event.type == "agent.tool_use":
                    print(f"[{event.name}] {json.dumps(event.input)[:80]}")
                elif event.type == "agent.message":
                    print("".join(b.text for b in event.content if b.type == "text"))
                elif event.type == "session.status_idle":
                    if event.stop_reason.type != "requires_action":
                        done = True
                        break
                    results = []
                    for event_id in event.stop_reason.event_ids:
                        call = pending_tool_calls.pop(event_id)
                        with tracer.start_as_current_span(
                            f"run_tool {call.name}",
                            attributes={
                                "gen_ai.operation.name": "execute_tool",
                                "gen_ai.tool.name": call.name,
                                "gen_ai.tool.call.id": call.id,
                                "anthropic.session.id": session.id,
                            },
                        ):
                            output = get_latest_version(**call.input)
                        print(f"[{call.name}] {call.input} -> {output}")
                        results.append(
                            {
                                "type": "user.custom_tool_result",
                                "custom_tool_use_id": call.id,
                                "content": [{"type": "text", "text": output}],
                            }
                        )
                    client.beta.sessions.events.send(session.id, events=results, betas=BETAS)
                    break  # reopen the stream for the next turn

print()
print_traces()
```

??? note "輸出"

    ```text
    session sesn_01DDAMC6SZFVHAnsWqExd4kN is running

    [get_latest_version] {'package': 'acme-billing'} -> {"package": "acme-billing", "version": "4.2.0", "released": "2026-10-11"}
    [bash] {"command": "echo $(( ($(date -d 2026-10-14 +%s) - $(date -d 2026-10-11 +%s)) / 
    The latest `acme-billing` is version 4.2.0, released on 2026-10-11, which is 3 days before today (2026-10-14).

    ── trace 784c6c3872a0dffcd06983f6d5aa40a3
    handle_ticket  [INTERNAL  UNSET  5.29s]
      │ anthropic.session.id = sesn_01DDAMC6SZFVHAnsWqExd4kN
        anthropic.sessions.create  [CLIENT  OK  0.56s]
          │ gen_ai.request.model = claude-sonnet-5-5
          │ gen_ai.agent.id = agent_01Rn9W7qwgEHGV6cNc9Kmgpx
          │ gen_ai.agent.name = release-notes-helper
          │ anthropic.session.id = sesn_01DDAMC6SZFVHAnsWqExd4kN
          │ anthropic.session.environment.id = env_01KqmS21fqFhcjWuufz33532
          │ anthropic.request.id = req_011Cg1MqcedDcVaVnDndVcnP
          │ http.response.status_code = 200
        anthropic.sessions.events.stream  [CLIENT  UNSET  1.24s]
          │ anthropic.session.id = sesn_01DDAMC6SZFVHAnsWqExd4kN
          │ anthropic.request.id = req_011Cg1Mqf3VbYzhzc5cmAHzL
          │ http.response.status_code = 200
        run_tool get_latest_version  [INTERNAL  UNSET  0.00s]
          │ gen_ai.operation.name = execute_tool
          │ anthropic.session.id = sesn_01DDAMC6SZFVHAnsWqExd4kN
          │ gen_ai.tool.name = get_latest_version
          │ gen_ai.tool.call.id = sevt_01Eif9fEB6vLWRZM7RtZiTon
        anthropic.sessions.events.send  [CLIENT  OK  0.28s]
          │ anthropic.session.id = sesn_01DDAMC6SZFVHAnsWqExd4kN
          │ anthropic.request.id = req_011Cg1MqjNgj8NCyuWASXWpt
          │ http.response.status_code = 200
        anthropic.sessions.events.stream  [CLIENT  UNSET  3.48s]
          │ anthropic.session.id = sesn_01DDAMC6SZFVHAnsWqExd4kN
          │ anthropic.request.id = req_011Cg1MqkMitp9XvBeBvSf3t
          │ http.response.status_code = 200
    ```

### 怎麼讀 session 的 trace

`handle_ticket` 底下的 SDK span：

- **`anthropic.sessions.create`** 帶有 `anthropic.session.id`、`gen_ai.agent.id`、`gen_ai.agent.name`、`gen_ai.request.model` 和 `anthropic.session.environment.id`。這個 session 之後的 span（SDK 和 API 的）都帶同樣的 `anthropic.session.id`。按它分組就能看到一個 session 跨越多個請求和 trace 的全貌。你自己的 span 也要設它（cell 在 `handle_ticket` 上設了），這樣同一個查詢也找得到它們。請求在 turn 一開始就回傳，所以 API 的 turn span 比它所掛的請求 span 跑得更久。
- **`anthropic.sessions.events.stream`** 的狀態是 `UNSET`，不是 `OK`。Event 串流沒有自然的結尾，所以關閉它是取消而不是成功（跟第 4 節同一條規則）。每個 `events.stream` span 都預期是 `UNSET`，只對 `ERROR` 告警。
- **`run_tool get_latest_version`** 是你的 span。SDK 沒有執行這個 tool，所以命名和 attribute 由你決定。Cell 照抄 SDK 的慣例（`gen_ai.operation.name=execute_tool`、`gen_ai.tool.name`、`gen_ai.tool.call.id`、`anthropic.session.id`），讓它在 dashboard 上跟 tool-runner 的 span 對得上。`client.beta.sessions.events.tool_runner()` helper 會幫你執行 tool，並發出帶這些 attribute 的 `anthropic.custom_tool_use <name>` span。

加了 destination 之後 API 會多給什麼（第 8 節）。*Thread* 是 session 內一個 agent 的對話：單 agent 的 session 有一個，multi-agent session 每個 subagent 一個。這些 span 以 `service.name=claude-platform` 到達，並透過 `traceparent` 掛在 SDK span 底下：

```
handle_ticket                                      INTERNAL  (yours)
├── anthropic.sessions.create                      CLIENT    (SDK)
│   └── anthropic.sessions.create                  SERVER    (API)
│       └── anthropic.session.turn                 INTERNAL  stop_reason=requires_action
│           └── anthropic.model_request            INTERNAL  gen_ai.usage.*  (asks for get_latest_version)
├── anthropic.sessions.events.stream               CLIENT    (SDK)
│   └── anthropic.sessions.events.stream           SERVER    (API)
├── run_tool get_latest_version                    INTERNAL  (yours)
├── anthropic.sessions.events.send                 CLIENT    (SDK)
│   └── anthropic.sessions.events.send             SERVER    (API)
│       └── anthropic.session.turn                 INTERNAL  stop_reason=end_turn
│           ├── anthropic.model_request            INTERNAL  gen_ai.usage.*
│           ├── anthropic.tool_use bash            INTERNAL  gen_ai.tool.call.id
│           └── anthropic.model_request            INTERNAL  gen_ai.usage.*  (final answer)
└── anthropic.sessions.events.stream               CLIENT    (SDK)
    └── anthropic.sessions.events.stream           SERVER    (API)
```

- **`anthropic.session.turn`**（`gen_ai.operation.name=invoke_agent`）是某個 thread 上一個 agent turn，從 `running` 到閒置。它的父 span 是啟動它的請求：`initial_events` 是 `sessions.create`，之後的訊息和 tool 結果是 `sessions.events.send`。`anthropic.session.turn.stop_reason` 跟迴圈從 idle event 讀到的 stop reason 相同（`end_turn`、`requires_action`、`retries_exhausted`）。當 destination 的 content mode 是 Full content，turn 會帶 `gen_ai.input.messages` 和 `gen_ai.output.messages`，thread 的第一個 turn 還帶 `gen_ai.system_instructions`。SDK client 的 `content_mode` 對 API span 沒有影響。
- **`anthropic.model_request`** 是 turn 內的一次模型呼叫，帶 `gen_ai.usage.*` attribute。要加總一個 session 的 token，就加總它的 `anthropic.model_request` span（用了 outcome 的話再加 `anthropic.session.outcome_evaluation` span）。Turn span 沒有 usage attribute，所以對整條 trace 加總不會重複計算。
- **`anthropic.tool_use <name>`** 是 API 在 environment 裡執行的預建 toolset tool。`anthropic.mcp_tool_use <name>` 是 MCP tool，帶 `anthropic.mcp.server.name`。
- API 的 turn、model-request 和 tool span 上的 **`gen_ai.conversation.id`** 是 thread ID。按它分組並依開始時間排序，就能把一個 thread 當逐字稿讀。Multi-agent session 裡，另一個 thread 上的 turn 會巢狀在呼叫它的 turn 底下，而因為另一個 thread 回覆而開始的 turn 沒有父請求，所以它會開一條新的 trace，要用 `anthropic.session.id` 去找。這個 thread ID 跟你在第 3 節設的 `conversation_id` 是兩回事，後者只標記 SDK span。

## 7. 把 span 送到你的 backend

SDK 自己沒有 exporter 設定。它發到你註冊的任何 provider，所以送 span 就是標準的 OTel 設定。在啟動 kernel 前設好 OTLP 環境變數，setup cell 的 `BatchSpanProcessor(OTLPSpanExporter())` 就會匯出這個 notebook 產生的每個 span：

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4318"          # base URL, the exporter appends /v1/traces
export OTEL_EXPORTER_OTLP_HEADERS="authorization=Bearer <token>"    # comma-separated key=value pairs, if your backend needs auth
export OTEL_SERVICE_NAME="ticket-service"                           # optional, overrides the Resource in code
```

`http://localhost:4318` 是本機 OpenTelemetry Collector 的預設 OTLP/HTTP port，Collector 是廠商中立的 proxy，負責批次、重試、遮蔽，並把 span 分送到一個或多個 backend。每個主流 backend 也都有文件說明直接的 OTLP/HTTP endpoint 和 auth header。正式環境請在你的服務和廠商之間放一個 Collector，讓應用程式碼不必持有廠商憑證；用 `BatchSpanProcessor` 而不是 `SimpleSpanProcessor`；結束時呼叫 `provider.shutdown()`，最後一批才會送出。

```python
if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    provider.force_flush()
    print("Flushed SDK spans to", os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"])
else:
    print("OTEL_EXPORTER_OTLP_ENDPOINT is not set, spans stayed in memory.")
```

??? note "輸出"

    ```text
    OTEL_EXPORTER_OTLP_ENDPOINT is not set, spans stayed in memory.
    ```

## 8. 把 API 的 span 加進同一條 trace

SDK span 到網路邊界就結束。模型執行、伺服器端 tool、壓縮和 Managed Agents turn 都發生在 API 內部。API 把這些當作自己的 span 匯出到一個 *destination*：你在組織裡註冊的 OTLP/HTTP endpoint 加 header（最多 10 個，每個可限定在全部或部分 workspace）。Destination 不需要改程式碼，而且涵蓋組織裡的每個 client，不管是不是 SDK。

要新增一個（只限組織 admin），到 Console 的 [Settings > Telemetry destinations](https://platform.claude.com/settings/telemetry-destinations)，選 **Add destination**，選你的 provider 或 **Custom**，然後填：

| 欄位 | 值 |
|---|---|
| OTLP endpoint URL | 你 backend 的 OTLP/HTTP endpoint 的 HTTPS 基底 URL：port 443、用 hostname 不是 IP、不能有 redirect。API 只會傳送到公開的 HTTPS host，所以 destination 不能指向內部基礎設施。不要附加 `/v1/traces` |
| Request headers | 你 backend 的 auth header。儲存後值是 write-only |
| Content mode | **Metadata only** 或 **Full content**。跟 SDK 的 `traces.content_mode` 各自獨立，所以兩邊要分別慎重設定 |
| Workspaces | 全部、選定的，或除了某些之外的全部 |
| Maximum content size | 選填。空的話每個 span 最多 8 MiB。欄位上限小的 backend 請調低 |

API 以 gzip 的 OTLP/HTTP protobuf 傳送，至少一次（用 trace ID 加 span ID 去重），並在第一個 span 之後約一分鐘內把 destination 標為 **Healthy**。如果 destination 有 redirect、解析到私有 IP，或連續 24 小時失敗，API 會停用它。

### 把 API span 和 SDK span 配對

在你的 backend 以 `service.name = claude-platform` 過濾，就只看到 API span。對一個 Messages API 請求，API 會發出一個跟 SDK span 同名的 `SERVER` span，底下是它執行的每個步驟各一個 span：

```
anthropic.messages.create                SERVER    parented under the SDK CLIENT span by traceparent
├── anthropic.model_request              INTERNAL  one per model run, with gen_ai.usage.*
├── anthropic.tool_use web_search        INTERNAL  one per server-tool use (anthropic.mcp_tool_use <name> for the MCP connector)
├── anthropic.model_request              INTERNAL  the run after the tool result
└── anthropic.compaction                 INTERNAL  when context compaction ran, with its own usage
```
設好 destination 並把 `web_search` 加進 tool 之後，第 5 節的 tool-runner trace 會變成：

```
weather_question                                   INTERNAL  (yours)
└── anthropic.messages.tool_runner                 INTERNAL  (SDK)
    ├── anthropic.messages.create                  CLIENT    (SDK)
    │   └── anthropic.messages.create              SERVER    (API)
    │       ├── anthropic.model_request            INTERNAL
    │       ├── anthropic.tool_use web_search      INTERNAL
    │       └── anthropic.model_request            INTERNAL  asks for get_weather
    ├── anthropic.custom_tool_use get_weather      INTERNAL  (SDK)
    └── anthropic.messages.create                  CLIENT    (SDK)
        └── anthropic.messages.create              SERVER    (API)
            └── anthropic.model_request            INTERNAL  final answer
```

兩邊來源都開時，有四條規則讓查詢保持正確：

- **用 kind 或 service 區分配對的兩個 span。** SDK span 是 `CLIENT`，來自你的 `service.name`。API span 是 `SERVER`，來自 `claude-platform`。兩者帶同一個 `anthropic.request.id`。
- **每個請求只從一個來源算 token。** `CLIENT` span、`SERVER` span，以及它底下的 `anthropic.model_request` span 回報的是同一份 usage。加總 `SERVER` span 或它們的 `anthropic.model_request` 子 span，不要兩個一起加，有 `anthropic.compaction` span 的話再加上去。Managed Agents 則是加總 `anthropic.model_request` 和 `anthropic.session.outcome_evaluation`。
- **你的 sampler 控制 API span 的量。** 如果你的 sampler 丟掉一條 trace，`traceparent` 裡的 sampled bit 就是關的，API 對那個請求什麼都不發。沒有 `traceparent` 的請求，API span 會在一條新的 trace 裡。
- **不要用 span 來計費。** 傳送是至少一次，所以會有重複，而停用的 destination 或未取樣的 trace 會丟 span。對帳請用 [Usage and Cost API](usage_cost_api.md)。

## 9. 清理

封存是永久的。想保留 agent 和 environment 重複使用，就跳過這個 cell。`provider.shutdown()` 會結束這個 kernel 的追蹤，所以重跑前面的 cell 之前要先重啟 kernel。

```python
client.beta.sessions.archive(session.id, betas=BETAS)
client.beta.agents.archive(agent.id, betas=BETAS)
client.beta.environments.archive(environment.id, betas=BETAS)
memory_exporter.clear()
provider.shutdown()  # flushes the OTLP batch processor if one was added
print("archived and flushed")
```

??? note "輸出"

    ```text
    archived and flushed
    ```

## 用在正式環境

- 把每個工作單位（request handler、queue 訊息、cron 執行）包在你自己的一個 span 裡，並在裡面呼叫 SDK，這樣 SDK 和 API 的 span 就會落在造成它們的那個操作底下。
- 透過 OpenTelemetry Collector 用 `BatchSpanProcessor` 匯出，在你的資料政策允許前讓 `content_mode` 維持 `metadata_only`，每個 backend 在 Console 註冊一個 destination。
- 對 `ERROR` 狀態和 `anthropic.message.stop_reason=max_tokens` 設告警。Stream 和 event-stream span 上的 `UNSET` 視為正常。
- 成本檢視每個請求只用一個來源：`SERVER` span 或 `anthropic.model_request`，不要疊在 `CLIENT` span 上。再用 Usage and Cost API 對帳。

## 文件

- [OpenTelemetry for the Claude API](https://platform.claude.com/docs/en/manage-claude/opentelemetry)：概覽、content mode、範例 trace、token 計算
- [Use OpenTelemetry with the Claude SDK](https://platform.claude.com/docs/en/manage-claude/opentelemetry/sdk)：各語言的設定、所有 client 選項和環境變數
- [Use OpenTelemetry with the Claude API](https://platform.claude.com/docs/en/manage-claude/opentelemetry/api)：destination、傳送、對整段對話取樣
- [OpenTelemetry span reference](https://platform.claude.com/docs/en/api/opentelemetry/spans)：每個 span、attribute 和父子關係

## 重點整理

- Span 有兩個來源：SDK 在你的 process 內發出 `CLIENT` / `INTERNAL` span，API 在 Anthropic 內部發出 `SERVER` span，靠 `traceparent` header 串成同一條 trace。
- 內容預設只記 metadata（`metadata_only`），prompt 和回應含使用者資料，要不要匯出由你的資料政策決定。
- 狀態的讀法：`ERROR` 才告警，stream 和 event-stream 的 `UNSET` 是正常的；`stop_reason=max_tokens` 值得單獨告警。
- Token 每個請求只能從一個來源算，`CLIENT`、`SERVER` 和 `model_request` 報的是同一份 usage，疊起來會重複。
- Managed Agents 的 turn、model request 和 toolset tool 都是 API span，要加了 Console destination 才看得到，並用 `anthropic.session.id` 把整個 session 串起來。

## 練習

1. 把第 3 節範例裡 `conversation_id` 換成你自己的值，並對同一個 ID 連送兩個請求，確認兩個 span 的 `gen_ai.conversation.id` 一樣。
2. 在 `print_traces()` 傳 `show="all"` 跑第 5 節的 tool runner，找出 `gen_ai.tool.call.id` 並對照前後兩個 `messages.create` span，確認它出現在哪裡。
3. 設 `OTEL_EXPORTER_OTLP_ENDPOINT` 指向本機的 Collector（`http://localhost:4318`），把 `content_mode` 維持 `metadata_only`，確認 backend 收到的 span 沒有 prompt 內容。
