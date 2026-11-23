---
translated: true
source: fable_5_fallback_billing/guide.ipynb
---
# Claude Fable 5 的 classifier fallback 與計費

> 原文：[fable_5_fallback_billing/guide.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/fable_5_fallback_billing/guide.ipynb)

偵測 Fable 5 的安全 classifier 擋下請求的情況，並用 server-side 或 SDK 的 client-side fallback 退回 Opus 4.8，包含 streaming 的行為和新的計費規則。

## 這篇在做什麼

Claude Fable 5 對某些領域（資安、生物等）有自動安全檢查，被擋下時 API 會回 `stop_reason: "refusal"`。這篇教你怎麼辨識這種 classifier block，並設定 fallback 讓請求自動改由 Opus 4.8 回答，也講清楚被擋的請求和 fallback 怎麼計費。

## 學完你會

- 看 `stop_reason` 和 `stop_details.category` 分辨 classifier block 和一般 model refusal。
- 用 `fallbacks` 參數加 beta header 設定 server-side fallback，並在 streaming 與非 streaming 下用 `usage.iterations` 判斷是哪個模型回答的。
- 在不能用 server-side fallback 的環境，用 SDK 的 middleware 做 client-side fallback，並理解 `fallback_credit_token` 怎麼讓重試以 cache-read 價計費。

## 開跑前

- 需要 `ANTHROPIC_API_KEY`，而且帳號要有 Claude Fable 5 和 Opus 4.8 的存取權。
- Server-side fallback 只在 Claude API 和 Claude Platform on AWS 可用。

Claude Fable 5 在資安、生物、化學這類領域能力很強，同樣的能力也可能被壞人拿來做網路攻擊或危險武器。所以 Claude Fable 5 在這些特定領域加了防護，每個請求都會跑自動安全檢查。這些檢查會擋下的請求包括：

- **攻擊性資安技術**：開發 exploit、惡意程式或攻擊工具
- **生物與生命科學**：實驗方法或分子機制
- **開發競爭用 AI 模型**：可能協助建構前沿 AI 系統的請求
- **擷取模型的[摘要思考](https://platform.claude.com/docs/en/build-with-claude/extended-thinking#summarized-thinking)**

這些防護刻意設得保守，優先求穩健，所以無害的技術工作有時也會觸發。我們讓 Fable 5 在所有跟生物和資安相關的主題都 fallback 到 Opus 4.8 再上線，這樣你能更快在其他領域用上 Fable 的 Mythos 級能力。上線後我們會持續降低 Fable 5 的誤判率。

**API 客戶應該設定從 Claude Fable 5 到 Opus 4.8 的 fallback**，可以用[內建的 server-side fallback](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons#server-side-fallback) 功能（原生 Claude API 和 Claude Platform on AWS 可用），或用 Anthropic SDK helper 寫的 [client-side fallback](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons#client-side-fallback) 邏輯。

有些在任何輸出之前就被擋下的請求會計費，而帶到 fallback 請求的 cached prompt 前綴，會以較低的 cache-read 價計費，不用當成新的 cache write。**不用 server-side fallback 時**，要拿到這個較低費率需要一個 fallback credit token，SDK 的 fallback middleware 會幫你兌換，見[下方](#4-billing-changes)。

## 這篇涵蓋什麼

1. [classifier block 長什麼樣子](#1-what-a-classifier-block-looks-like)
2. [Server-side fallback（建議）](#2-server-side-fallback-recommended)
3. [Streaming](#3-streaming)
4. [計費變更](#4-billing-changes)
5. [用 SDK 做 client-side fallback](#5-client-side-fallback-with-the-sdk)
6. [常見的反模式](#6-common-anti-patterns)


```python
%%capture
%pip install -U "anthropic>=0.108.0"
```

```python
import os

from dotenv import load_dotenv

load_dotenv()

PRIMARY_MODEL = "claude-fable-5"
FALLBACK_MODEL = "claude-opus-4-8"
SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-06-01"
FALLBACK_CREDIT_BETA = "fallback-credit-2026-06-01"

# Anthropic() reads ANTHROPIC_API_KEY from the environment. Add it to a .env
# file (loaded above) or export it in your shell before running the live examples.
if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "ANTHROPIC_API_KEY is not set - add it to .env or export it."
    )
```

## 1. classifier block 長什麼樣子

*Classifier block* 是請求看起來違反我們的防護時 API 回傳的東西。API 回 `200`，帶 `stop_reason: "refusal"`，以及一個描述類別的 `stop_details` 物件：

```json
{
  "stop_reason": "refusal",
  "stop_details": {
    "type": "refusal",
    "category": "cyber",
    "explanation": "This request triggered restrictions on violative cyber content and was blocked under Anthropic's Usage Policy..."
  },
  "content": [...]
}
```

判斷邏輯要看 **`stop_reason`，不要看 `content` 或 `stop_details`**。`stop_details` 只是參考資訊，可能是 `null`，這種情況要當成一般的 refusal（不屬於下面任何類別）。

有值時，`category` 會是 `"cyber"`、`"bio"`、`"frontier_llm"` 或 `"reasoning_extraction"` 其中之一。這能幫你調整 fallback 的選擇：

| category | 觸發情況 |
| --- | --- |
| `cyber` | 攻擊性資安內容（exploit、惡意程式、攻擊工具） |
| `bio` | 生物 / 生命科學內容（實驗方法、分子機制） |
| `frontier_llm` | 可能協助開發競爭用 AI 模型的請求 |
| `reasoning_extraction` | 試圖擷取模型[摘要思考](https://platform.claude.com/docs/en/build-with-claude/extended-thinking#summarized-thinking)的請求 |

Classifier block 跟 **model refusal**（模型本身因其他政策理由拒絕）不一樣。兩者都會以 `stop_reason: "refusal"` 出現，但 `stop_details.category` 會告訴你是哪個 classifier 擋的。

> **注意：** **沒有**使用 server-side fallback 功能時，`stop_details` 還會帶一個 `fallback_credit_token`，用來讓你的 fallback 模型請求以 cache read 計費，見[計費變更](#4-billing-changes)。


## 2. Server-side fallback（建議）

Messages API 可以幫你跑 fallback。傳入 `fallbacks`，值是 `[{"model": "claude-opus-4-8"}]`，加上 `server-side-fallback-2026-06-01` beta header。如果 Fable 的 classifier 擋下這一輪，API 會自動用 Opus 4.8 重試，並加上標註讓你知道發生了什麼。

自動 fallback 功能目前支援 **Claude API** 和 **Claude Platform on AWS**。目前只支援從 Fable 5 退到 Opus 4.8，我們預期之後會擴充。

```bash
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: server-side-fallback-2026-06-01" \
  -H "content-type: application/json" \
  -d '{
    "model": "claude-fable-5",
    "max_tokens": 1024,
    "fallbacks": [
      { "model": "claude-opus-4-8" }
    ],
    "messages": [
      { "role": "user", "content": "Hello, world" }
    ]
  }'
```

### fallback 跑不起來的時候

你設定了 `fallbacks`，但 API 連不到 fallback 模型（rate limit 用完或過載），這一輪仍會以 refusal 回來，`stop_details.recommended_model` 會給出該直接重試的標準模型 id：

```json
{
  "stop_reason": "refusal",
  "stop_details": {
    "type": "refusal",
    "category": "cyber",
    "recommended_model": "claude-opus-4-8"
  }
}
```

`recommended_model` **只**在這個情況才會有值（有設定 fallbacks，而且 fallback 沒能執行）。沒設定 fallbacks 的一般 block 沒有這個欄位，所以[第 1 節](#1-what-a-classifier-block-looks-like)的基本範例裡看不到。


```python
# Fable applies extra safety filters. With a fallback chain configured, the API
# retries blocked turns on the next model server-side. A stop_reason of "refusal"
# means the whole chain refused.

from anthropic import Anthropic

client = Anthropic()


def chat_turn(messages, max_tokens=1024):
    """One API call; the server handles the fallback."""
    return client.beta.messages.create(
        model=PRIMARY_MODEL,
        max_tokens=max_tokens,
        messages=messages,
        betas=[SERVER_SIDE_FALLBACK_BETA],
        fallbacks=[{"model": FALLBACK_MODEL}],
    )
```

### 偵測 fallback（非 streaming）

fallback 的回應在每個切換點都有一個 `{"type": "fallback"}` content block，`usage.iterations` 記錄每個模型的用量。注意 **sticky-served** 的輪次，也就是因為對話中較早的輪次已經 fallback，所以直接導向 fallback 模型的請求，**不會**有 fallback block，因為請求是直接路由的，`content` 裡沒有邊界可標。要判斷某一輪是不是 fallback 模型回答的，`usage.iterations` 才是可靠的方式。


```python
def fallback_hops(response):
    """(from_model, to_model) for each hop that ran and blocked this turn."""
    hops = []
    for b in response.content:
        if getattr(b, "type", None) == "fallback":
            d = b.model_dump() if hasattr(b, "model_dump") else dict(b)
            hops.append((d["from"]["model"], d["to"]["model"]))
    return hops


def served_by_fallback(response):
    """True whenever a fallback model served the response, INCLUDING a
    sticky-served turn (which carries no fallback block). usage.iterations is
    the best way to check whether a turn was served by a fallback model."""
    iters = getattr(response.usage, "iterations", None) or []
    return any(
        (i.get("type") if isinstance(i, dict) else getattr(i, "type", None))
        == "fallback_message"
        for i in iters
    )


response = chat_turn([{"role": "user", "content": "Hello, world"}])
hops = fallback_hops(response)
for from_model, to_model in hops:
    print(f"[{from_model} blocked \u2014 continued on {to_model}]")
if not hops and served_by_fallback(response):
    print(f"[sticky: served directly by {response.model}]")
```

### streaming 時偵測 fallback

留意 block 是 `{"type": "fallback"}` 的 `content_block_start` 事件，那標示串流中的切換點。但要確定每一輪的答案，請像非 streaming 回應一樣，檢查**最終**訊息的 `usage.iterations`。這個檢查在所有情況都可靠，包括直接由 fallback 模型服務的串流，所以把它當成判斷依據，不要只靠串流中的事件。


```python
with client.beta.messages.stream(
    model=PRIMARY_MODEL,
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello, world"}],
    betas=[SERVER_SIDE_FALLBACK_BETA],
    fallbacks=[{"model": FALLBACK_MODEL}],
) as stream:
    for event in stream:
        if (
            getattr(event, "type", None) == "content_block_start"
            and getattr(event.content_block, "type", None) == "fallback"
        ):
            fb = event.content_block
            fb = fb.model_dump() if hasattr(fb, "model_dump") else dict(fb)
            print(f"[switching: {fb['from']['model']} -> {fb['to']['model']}]")
    final = stream.get_final_message()

# Definitive per-turn check, same as non-streaming: usage.iterations also
# catches a stream served directly by the fallback model (no in-stream event).
if served_by_fallback(final):
    print(f"[fallback model served this stream: {final.model}]")
```

### fallback 回應的結構

fallback 回應包含 `message.model`（最後實際回答的模型）、標示每個切換點的 `{"type": "fallback"}` content block，以及 `usage.iterations` 裡每次嘗試的用量：

```json
{
  "id": "msg_01Ab...",
  "type": "message",
  "role": "assistant",
  "model": "claude-opus-4-8",
  "content": [
    { "type": "fallback", "from": { "model": "claude-fable-5" }, "to": { "model": "claude-opus-4-8" } },
    { "type": "text", "text": "..." }
  ],
  "stop_reason": "end_turn",
  "stop_details": null,
  "usage": {
    "input_tokens": 412, "output_tokens": 264,
    "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
    "iterations": [
      { "type": "message", "model": "claude-fable-5", "input_tokens": 408, "output_tokens": 0,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0 },
      { "type": "fallback_message", "model": "claude-opus-4-8", "input_tokens": 412, "output_tokens": 264,
        "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0 }
    ]
  }
}
```

**每次嘗試的覆寫。** 每個 fallback 項目可以只針對該次嘗試覆寫 `max_tokens`、`thinking`、`output_config` 和 `speed`（`output_config` 和 `speed` 另外需要跟對應的頂層欄位相同的 beta header）。把項目的覆寫合併進去後的請求，必須是對該項目模型來說格式正確的直接請求。

```json
{
  "model": "claude-fable-5",
  "max_tokens": 1024,
  "fallbacks": [
    { "model": "claude-opus-4-8", "max_tokens": 8192, "thinking": {"type": "disabled"}, "speed": "fast" }
  ],
  "messages": [
    { "role": "user", "content": "Hello, world" }
  ]
}
```

**計費。** `usage.input_tokens` 每一輪只算一次。`usage.output_tokens` 反映最後的答案。需要精確的各模型用量歸屬時，請用 `usage.iterations`。


## 3. Streaming

streaming 下，fallback 設計成自動運作。如果 classifier 在**任何輸出送到你這邊之前**就擋下，串流一開始就是 fallback 模型的回應。這個重試是看不見的，也不會發出 fallback SSE 事件。

如果 classifier 在**串流中途**擋下，重試也在同一個串流上進行：已輸出的部分會保留，用一個 `{"type": "fallback"}` content block 標出邊界，fallback 模型從那段已輸出的內容接著繼續。已經串流出來的東西絕不會被丟掉。


```python
def stream_turn(messages, max_tokens=1024):
    with client.beta.messages.stream(
        model=PRIMARY_MODEL,
        max_tokens=max_tokens,
        messages=messages,
        betas=[SERVER_SIDE_FALLBACK_BETA],
        fallbacks=[{"model": FALLBACK_MODEL}],
    ) as stream:
        # Nothing streamed is ever discarded: after a mid-stream block, the
        # final message is partial + fallback block + continuation.
        final = stream.get_final_message()

    if final.stop_reason == "refusal":
        return final  # the whole chain refused
    text = "".join(b.text for b in final.content if b.type == "text")
    print(f"{final.model}: {text}")
    return final
```

## 4. 計費變更

這一節說明被擋下的請求和 fallback 怎麼計費。使用 fallback 和 Anthropic SDK helper 時，這些行為會自動套用。**只有要採用 cache-read 計費變更時才需要動作，而且只限於沒用 server-side fallback 的情況。**

**1. 部分類別的 pre-stream block 會計費。** 請求在任何輸出 token 回傳之前就被擋下，如果它的 `stop_details.category` 是 `"bio"`、`"frontier_llm"` 或 `"reasoning_extraction"`，會跟其他請求一樣，以被請求模型的費率計費。從 2026 年 9 月 23 日起，其他類別或沒有類別的 pre-stream block 不計費；目前的清單見 [Refusals and fallback](https://platform.claude.com/docs/en/build-with-claude/refusals-and-fallback#how-refusals-are-billed)。只對誤判率低的類別的防護計費，主要是提高反覆嘗試繞過防護的成本。如果在被計費的 block 之後 fallback，fallback 請求也會計費，兩筆都收，不過下面第 2 點會抵銷重試的 prompt-cache 成本。

請求在串流中途（輸出 token 已開始串流之後）被擋下，不論類別，都會以一般費率計 input tokens 和已串流的輸出。

**2. Fable 5 → Opus 4.8 fallback 的 input tokens 以 cache hit 計費。** 一般來說，切換到另一個模型會被當成 [cache *write*](https://platform.claude.com/docs/en/build-with-claude/prompt-caching#how-prompt-caching-works) 計費，是基本 input-token 成本的 1.25 倍（5 分鐘 TTL）或 2 倍（60 分鐘 TTL）。這裡我們把這些 Opus tokens 當成已經被快取過來計費，也就是 cache *read*，是基本 input-token 價格的 10%。

- **使用 server-side fallback 功能：** 這個計費變更自動套用。
- **沒有使用 server-side fallback 功能：** 見下面的 credit-token 流程。

### 兌換 fallback credit token（只限 client-side fallback）

被安全 classifier 擋下的 Fable 請求，會在 `stop_details` 裡帶一個 `fallback_credit_token`。**只有**被擋的請求有可計費的 cached 前綴時才會有這個 token，否則是 `null`。

兌換方式：

1. 送後續的 Opus 4.8 請求時，加上 `anthropic-beta: fallback-credit-2026-06-01` header。
2. 把 token 當成頂層參數 `fallback_credit_token` 傳入。
3. 影響 prompt 內容的欄位要跟被擋的請求**完全相同**，也就是一模一樣的 `system`、`messages` 和 `tools`。

Fable 請求上被快取的前綴，就會以 cache-read 費率計費，而不是 cache-write。切換成本會退還，所以重試的花費就跟整段對話一直都在 Opus 上一樣。

**有效條件：** token 只在 Opus 4.8 請求上有效，而且該請求必須在被擋的 Fable 5 請求之後 **5 分鐘內**，並且來自**同一個 org 和 workspace**。

**串流中途被擋。** 如果 Fable 5 請求在串流輸出 token 的中途被擋，`stop_details` 還會在 credit token 之外帶 `fallback_has_prefill_claim: true`。意思是在後續的 Opus 4.8 請求裡，你可以把那段部分輸出當成 assistant prefill 附加上去，從 Fable 停下來的地方繼續，這在 Opus 4.8 請求裡[一般是不允許的](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/increase-consistency#prefill-claudes-response)。


```python
def redeem_credit_after_block(blocked_response, messages, system=None, tools=None, max_tokens=1024):
    """Retry a classifier-blocked Fable turn on Opus 4.8, redeeming the
    fallback credit token so the cached prefix is billed at the cache-read
    rate. Use this only when you are NOT using server-side fallback.

    Pass the same `system`, `messages`, and `tools` as the blocked request."""
    details = blocked_response.stop_details
    credit = getattr(details, "fallback_credit_token", None) if details else None

    # The system, messages, and tools must be IDENTICAL to the blocked request.
    kwargs = {"model": FALLBACK_MODEL, "max_tokens": max_tokens, "messages": messages}
    if system is not None:
        kwargs["system"] = system
    if tools is not None:
        kwargs["tools"] = tools
    if credit is not None:  # present only when the blocked request had a cached prefix
        kwargs["betas"] = [FALLBACK_CREDIT_BETA]
        kwargs["extra_body"] = {"fallback_credit_token": credit}

    return client.beta.messages.create(**kwargs)
```

## 5. 用 SDK 做 client-side fallback

Server-side fallback 在原生 Claude API 和 Claude Platform on AWS 可用，但目前不支援 Amazon Bedrock、Vertex AI、Microsoft Foundry 或 Message Batches API。對這些環境，或任何你想把 fallback 邏輯放在 client 的情況，Anthropic SDK（Python、TypeScript、Go、Java、C#）都附了 **refusal-fallback middleware**。

在 client 上設定一次你的 fallback 模型清單和一個 `BetaFallbackState`，然後照常呼叫 `client.beta.messages`。這個 middleware 會：
- 把 `stop_reason: "refusal"` 的那一輪用清單中的下一個模型重試（如果 fallback 也拒絕，就繼續往清單下面走；如果每一項都拒絕，就回傳最初的 refusal，不會丟例外）；
- **在每個請求自動送出 `fallback-credit-2026-06-01` beta header**，所以不用自己管 token 就能拿到[第 4 節](#4-billing-changes)的 cache-read 計費變更；
- 幫你管理對話歷史裡的 `fallback` content block；
- 把接受請求的模型記在 `BetaFallbackState`，讓後續輪次固定用它。

它跟 server-side 的 `fallbacks` 參數**互斥**，二選一。（要從裝了 middleware 的應用程式送 server-side `fallbacks` 請求，請用另一個沒裝 middleware 的 client 實例。）


```python
from anthropic import Anthropic, BetaFallbackState, BetaRefusalFallbackMiddleware

# Install the middleware once, with your fallback chain. No per-request betas needed.
client = Anthropic(
    middleware=[BetaRefusalFallbackMiddleware([{"model": FALLBACK_MODEL}])],
)

state = BetaFallbackState()  # reuse across turns to pin follow-ups to the accepting model

# Non-streaming: a refused Fable turn is retried on Opus 4.8 transparently.
with state:
    message = client.beta.messages.create(
        model=PRIMARY_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello, Claude"}],
    )
print(f"served by: {message.model}")

# Streaming: on a refusal the middleware splices the fallback model's events
# onto the same open stream.
with (
    state,
    client.beta.messages.stream(
        model=PRIMARY_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello, Claude"}],
    ) as stream,
):
    for event in stream:
        if event.type == "text":
            print(event.text, end="", flush=True)
    final = stream.get_final_message()
print(f"\nserved by: {final.model}")
```

## 6. 常見的反模式

**每個請求都要設 fallback，不是每個帳號設一次。** 沒有帳號層級或 session 層級的開關能啟用 Opus 4.8 fallback。每次 API 呼叫都必須帶 fallback 設定。沒開 fallbacks 的呼叫會回傳 refusal，不會默默地用 fallback 模型重試。

**檢查每一條會組出請求的程式路徑。** 重試按鈕、訊息重新產生、tool-use 接續這類功能常常自己組請求，每一個都可能默默漏掉 fallback 設定。在每個進入點都明確設定 fallback。（想快速在整個 codebase 加上 fallbacks，見[遷移指南](https://platform.claude.com/docs/en/about-claude/models/migration-guide)和 [claude-api skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/claude-api-skill)。）

**subagent 的呼叫也要帶 fallback，而且行為是各 agent 各自的。** 如果你的應用在一個 session 裡跑多個 agent，每個 agent 的呼叫都需要 fallback 設定。發生 refusal 時，只有收到它的那個 agent 會轉到 fallback 模型，其他 agent 還是留在 Fable。不要以為一個 agent 的 fallback 會套用到整個 session。（Claude Code 的 sub-agent 也一樣：只有碰到 refusal 的那個 sub-agent 會退到 Opus，session 其餘部分繼續用 Fable 5。）

**refusal 之後重送同一個請求只會再被 refuse。** 被拒絕的內容還在對話歷史裡，所以重送給同一個模型會再次觸發 block。遇到 `stop_reason: "refusal"` 時，改在 fallback 模型上重試，並另外設一個標記，讓你的 router 知道這段對話接下來都留在 fallback 模型。

**用 `usage.iterations` 建立服務模型的分析，不要用你請求的模型。** 回應的 `model` 欄位是實際回答的模型，所以由 fallback 服務的輪次會顯示 Opus 4.8。以*請求*的模型記錄的分析，在用到 fallback 時都會是錯的。可靠的逐輪檢查方式是最終 usage 紀錄裡的 `usage.iterations`。

**小心處理 streaming 截斷。** 在串流中途碰到 classifier block 時，要省略 fallback 之前出現的任何 `thinking`、`tool_use` 或其他 block。被截斷的 `tool_use` block 是無法解析的 JSON，而且另一個模型的 `thinking` block 會讓下一次呼叫失敗。如果沒有用 server-side fallback 而要繼續，請使用 `stop_details` 裡的 `fallback_has_prefill_claim` 授權，不要把部分回應貼進一個已完成的 assistant turn。

## 重點整理

- 判斷 classifier block 要看 `stop_reason: "refusal"`，`stop_details` 只是參考，可能是 `null`。
- 能用 server-side fallback 就用它，計費的 cache-read 優惠會自動套用；不能用時，靠 SDK middleware 做 client-side fallback 並自動兌換 credit token。
- 要確認哪個模型回答了這一輪，看最終訊息的 `usage.iterations`，不要看你請求的模型，也不要只靠 fallback block，因為 sticky-served 的輪次沒有它。
- fallback 是每個請求各自設定，retry、regenerate、subagent 這些會自己組請求的路徑最容易漏掉。
- 串流中途被擋時，要丟掉被截斷的 `tool_use` 和 `thinking`，用 `fallback_has_prefill_claim` 的授權接續，不要自己拼接。

## 練習

1. 寫一小段程式，對一個非 streaming 的回應，用 `usage.iterations` 判斷是不是由 Opus 4.8 回答，並印出每個模型的 input 與 output tokens。
2. 把頁面上的 server-side fallback 請求改成每次嘗試都覆寫 `max_tokens`，確認 fallback 項目合併後仍然是對 Opus 4.8 格式正確的請求。
3. 改用 SDK 的 refusal-fallback middleware 寫一個 client-side 版本，並模擬 Fable 被擋的情況，檢查 `BetaFallbackState` 有沒有讓下一輪直接用 fallback 模型。
