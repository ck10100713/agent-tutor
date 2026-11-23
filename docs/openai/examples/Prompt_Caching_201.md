---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Prompt_Caching_201.ipynb
---
# Prompt Caching 201

> 原文：[examples/Prompt_Caching_201.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Prompt_Caching_201.ipynb)

用來提高 prompt caching 命中率、降低延遲跟成本的 cookbook。

## 這篇在做什麼

這篇講怎麼讓 prompt caching 的命中率更高，包含原理、對成本跟延遲的影響、怎麼量測，以及一整套實戰優化做法。重點是 prefix 要穩、路由要設計好。

## 學完你會

- 解釋 prompt caching 為什麼省錢又省時間，以及 cache 命中的條件
- 用 `cached_tokens` 量測命中率，並用 `prompt_cache_key`、`allowed_tools` 等手法拉高命中率
- 判斷哪些做法會讓 cache 失效（改 tool、塞 timestamp、壓縮對話等）

## 開跑前

需要 OpenAI API key。範例會用到 Responses API，部分功能（Flex、extended caching）要看帳號與模型是否支援。

> **注意：** 這份指南只適用於 GPT-5.6 之前的模型。GPT-5.6 以後請看 [Prompt Caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)。

這是一份實用指南：基本觀念、對效能的影響、怎麼量測，以及優化策略。

## 1. Prompt Caching 基礎

模型的 prompt 常常包含重複的內容，例如 system instructions、tools 跟 messages。當請求帶有系統最近處理過的 prefix 時，OpenAI 可以把它導到已經算過那段 prefix 的伺服器，讓模型重用之前的運算，不用從頭再算。

Prompt Caching 最多可以降低 80% 的 time-to-first-token 延遲，並降低 90% 的 input token 成本。所有 API 請求都會自動套用，沒有額外費用。

這份 cookbook 要更深入講怎麼優化 cache 命中。概觀可以先看 [API docs](https://developers.openai.com/api/docs/guides/prompt-caching) 跟 [Prompt Caching 101](https://developers.openai.com/cookbook/examples/prompt_caching101/)，我們開始吧！

### 1.1 基本觀念

- Cache 命中需要 prefix 完全一樣、而且重複出現。prompt 達 1024 個 token 以上才會自動生效，命中以 128 token 為單位增加。
- 整個請求的 prefix 都能被 cache：messages、圖片、音訊、tool 定義，還有 structured output 的 schema。
- In-memory prompt caching 對所有 API 請求自動生效。Extended prompt caching 則把保留時間拉長到 24 小時。
- 要命中 cache，兩個請求必須有相同的 prefix，而且落在同一台機器。對於共用 prefix 的流量，可以用選填參數 `prompt_cache_key` 改善路由。
- 要仔細評估像 compaction 這類 context engineering 技巧對 cache 的影響。
- 迭代時透過 request log 或 Usage dashboard 監控 cache、成本跟延遲。

## 2. 為什麼 caching 很重要

### 2.1 核心技術原因：跳過 prefill 運算

對輸入 token 跑 transformer 各層的 forward pass，是推論成本跟延遲的主要來源。在 transformer 裡，prompt caching 針對的是 attention 層內的 key 跟 value projection。Attention 讓模型在處理某個 token 時，能衡量輸入序列中各部分的重要性，抓到 context 跟長距離的依賴關係。

當你對 OpenAI 發請求時，系統會先產生 token embedding，再轉成三個向量：query (Q) 代表這個 token 為了理解自己所需要的內容，key (K) 編碼每個 token 代表什麼，value (V) 則是在相關時可以被納入的資訊。模型把當前 token 的 query 跟所有 token 的 key 做內積，得到 attention 分數。經過 softmax 後，這些分數變成權重，決定每個 token 的 value 對更新後的表示貢獻多少。舉例來說，在 “she sat by the river bank” 這句話裡，“river” 給了 “bank” 重要的上下文，把它的意思推向河岸而不是銀行。KV cache 儲存的就是這段 prefix 在所有層跟所有 head 的 key 與 value tensor。

如果你接著發另一個請求 “she sat by the river bank on a cloudy day”，前面那段 prefix 是一樣的。處理新的、沒看過的後綴時，模型會重用 cache 的 tensor，只對新的 token 算 attention。

關鍵是，“river” 跟 “bank” 之間的強語意關聯，已經在上一次 forward pass 時編進那些 cached 的 key 跟 value 裡了。模型不需要重算 “bank” 跟 “river” 怎麼對應。像 “cloudy”、“day” 這樣的新 token 會產生自己的 query，去對 prefix 的 cached key 做 attention。換句話說，語意的基礎已經打好了，模型只是在既有的 attention 狀態上往下蓋，不用從頭再算。

### 2.2 成本影響

Cache 折扣可以很可觀。折扣幅度依模型系列而異，隨著我們的推論架構越來越有效率，最新的模型能提供更高的 cache 折扣。以下是一些例子，完整模型請看定價頁。Prompt Caching 對所有近期模型（gpt-4o 以後）都有開。

| Model | Input <br>(per 1M tokens) | Cached input <br>(per 1M tokens) | Caching Discount |
| --- | --- | --- | --- |
| gpt-4o | $2.50 | $1.25 | 50.00% |
| gpt-4.1 | $2.00 | $0.50 | 75.00% |
| gpt-5-nano | $0.05 | $0.005 | 90.00% |
| gpt-5.2 | $1.75 | $0.175 | 90.00% |
| gpt-realtime (audio) | $32.00 | $0.40 | 98.75% |


### 2.3 延遲影響

降低 time-to-first-token (TTFT) 是提升 cache 命中率的主要動機。Cached token 最多可以降低約 80% 的延遲。

有 caching 的話，延遲大致跟輸出長度成正比，而不是跟整段對話長度成正比，因為完整的歷史 context 不用重新 prefill。cache 命中時，取樣模型的成本是線性的，而不是平方成長。

我把一系列 prompt 跑了 2300 次，畫出 cached 跟 uncached 請求的比較。最短的 prompt（1024 token）cached 請求快 7%，到了最長的一端（150k+ token）TTFT 快了 67%。輸入越長，caching 對首 token 延遲的影響越大。

![Figure 2](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt-caching-201/figure-2.svg)

## 3. 先量測 caching（這樣才能迭代）

### 3.1 單一請求：`cached_tokens`

回應裡有 usage 欄位，告訴你有多少 prompt token 是從 cache 取得的。所有請求的 [Response](https://developers.openai.com/api/docs/api-reference/responses/object) 或 [Chat](https://developers.openai.com/api/docs/api-reference/chat/object) 物件，在 `usage.prompt_tokens_details` 底下都有 `cached_tokens` 欄位，表示有多少 prompt token 被 cache 了。


```
"usage": {
  "prompt_tokens": 2006,
  "completion_tokens": 300,
  "total_tokens": 2306,
  "prompt_tokens_details": {
    "cached_tokens": 1920
  },
  "completion_tokens_details": {
    "reasoning_tokens": 0,
    "accepted_prediction_tokens": 0,
    "rejected_prediction_tokens": 0
  }
}
```



你也可以在 usage dashboard 裡篩選 cached / uncached token，看高層次的概況。

![Figure 3](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt-caching-201/figure-3.png)

## 4. 提高 cache 命中率（實戰手冊）

什麼叫 cache 命中？就是請求的開頭跟之前某個請求有相同的 prefix，系統可以重用先前算好的 key/value tensor，不用重算。提高 cache 命中率，也就是盡量讓 prefix 能被重用，會直接改善效能跟效率，所以這就是我們的目標。


### 4.1 送出超過 1024 token 的 prompt

聽起來反直覺，但有時候把 prompt 加長一點，反而能降低總成本。

假設你的 prompt 是 900 token，永遠不會有 cache 命中。如果加長到 1100 token，並拿到 50% 的 cache 比率，token 成本可以省 33%。如果 cache 比率是 70%，可以省 55%。一旦跨過 caching 門檻、有了足夠的重用，重複 token 的邊際成本就大幅下降。也就是說，稍微長一點但穩定的 prefix，可能比短但永遠不會被 cache 的 prompt 更便宜。

### 4.2 讓 prefix 保持穩定

這是最省力、效果最大的優化：讓 prompt 前面的部分保持不變。

把不會變的內容放在開頭：
- Instructions
- Tool 定義
- Schemas

把會變動的內容（例如使用者輸入、動態值、session 專屬資料）移到最後。前面的 token 就算只有一點小改動，也會讓 exact prefix 比對失效，沒辦法命中 cache。

**從 Codex 學到的**
我們的工程團隊在說明 [Codex agent loop 的架構](https://openai.com/index/unrolling-the-codex-agent-loop/)時，強調 prompt 結構是第一等的效能要素，caching 是最優先的事。在 Codex CLI 裡，system instructions、tool 定義、sandbox 設定跟環境 context，在請求之間都保持一致、順序也固定，以維持又長又穩定的 prompt prefix。當對話中途 runtime 設定改變（例如換工作目錄或 approval mode），agent loop 是在後面追加新 message，而不是修改前面的內容。不去動原本的 prefix，就能保住 cache 命中所需的 exact prefix 比對。

**Tip：用 metadata**
我們看過客戶不小心讓 cache 失效，原因是在請求前面放了 timestamp，想之後查詢或除錯用。把它移到 `metadata`，就不會影響 cache。

### 4.3 保持 tools 跟 schemas 一致

Tools、schemas 跟它們的順序都屬於 cached prefix 的一部分，它們會被插在 developer instructions 之前，所以改動它們就會讓 cache 失效。包含：
- Schema 的 key 改變
- Tool 順序改變
- Instructions 改變


**Tip：調整 tools 又不破壞 prompt caching**
善用 [`allowed_tools`](https://developers.openai.com/api/docs/guides/function-calling/#tool-choice) 這個 `tool_choice` 選項。它可以限制模型在單次請求能呼叫的 tools，而不用改 tools 陣列、也不會讓 cache 失效。把完整工具組都列在 tools 裡，再用 `allowed_tools` 區塊指定這一回合可以用哪些 tool。


```
# Static “tools” stay in the cached prompt prefix: 

tools = [get_weather_def, get_location_def, calendar_def, …] 

# Per-call “allowed_tools” only lives in request metadata, not in the prefix: 

allowed_tools = {"mode":"auto", "tools":["get_weather","get_location"]}
```




### 4.4 用 `prompt_cache_key` 改善路由黏著度

Caching 要生效，兩個請求必須有相同 prefix 且落在同一台機器。請求會依據 prompt 前約 256 個 token 的 hash 被導到推論引擎。當你提供 `prompt_cache_key`，它會跟這個 hash 結合，增加路由的黏著度，也就是有相同 prefix 的請求更可能落在同一個引擎、重用 cached 的 KV 狀態。這很有效：我們有一位做 coding 的客戶，開始用 `prompt_cache_key` 後，命中率從 60% 提升到 87%。

當你送出的請求開頭 context 相同（也就是前 256 個 token），之後才不一樣時，`prompt_cache_key` 特別有用，因為它讓你可以刻意把相關請求分在一組。

每個推論引擎對每個 prefix + `prompt_cache_key` 組合，大約能處理每分鐘 15 個請求。如果流量超過這個速率，例如你送出幾千個共用同一個 prefix 跟 key 的請求，系統會把多出來的請求分散到額外的機器做 load balancing。每台新機器都會有一次 cache miss。

所以你應該選一個粒度，讓每個 prefix + key 組合維持在約 15 RPM 以下。

在 coding 的情境我們看到：
- 每個使用者一個 key，可以提升相關對話之間的重用率（例如在同一個 codebase 工作）。
- 每個對話一個 key，在使用者同時跑很多不相關 thread 時比較好擴展。
也可以讓幾個使用者共用一個 key。簡單的做法是把 user id 做 hash 再對 bucket 數取餘數，讓每個 bucket 的流量接近 15 RPM，這樣 caching 效果最好。


**Tip：試試 Flex Processing，取代 Batch API**
如果你的工作流程對延遲不敏感，可能會用 Batch API。想在 caching 上有更多彈性，可以考慮 Flex Processing。Flex 提供跟 Batch 一樣的 50% token 折扣，但是透過 Responses API 並在每個請求指定 `service_tier="flex"`。這樣你有更多彈性：

- 可以控制請求速率 (RPM)
- 可以使用 extended prompt caching
- 可以帶 prompt_cache_key
因為你可以更精準地調整路由跟 cache 的位置，Flex 在某些工作負載下可以達到更高的 cache 命中率。它特別適合原型開發，或推論量不大但仍想省成本的 production 工作負載。

我做了一個 10,000 個相同請求的對比測試。Flex（使用 extended prompt caching 加 `prompt_cache_key`）的 cache 命中率比 Batch job 高 8.5%，換算下來 input token 成本少了 23%。

![Figure 4](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt-caching-201/figure-4.svg)

Batch API 在 caching 上沒有跟各模型對等：GPT-5 之前的模型不支援，所以如果你在用 o3 或 o4-mini，可以考慮改用 Flex 來享受 caching。最新資訊請看[定價文件](https://developers.openai.com/api/docs/pricing?latest-pricing=flex)。


**Insight：把 `prompt_cache_key` 當成 shard key**
想後端怎麼路由請求時，可以把 `prompt_cache_key` 想成資料庫的 shard key，優化時要考量的事情非常類似。跟 shard key 一樣，粒度是個取捨。每台機器對同一個 prefix 大約只能處理 15 RPM，所以如果同一個 key 用在太多請求上，請求會溢出到多台機器，每台新機器都要重新建立 cache。另一方面，如果 key 太細，流量會分散到各台機器，就失去 cache 重用的好處。路由仍然有 load balancing，`prompt_cache_key` 只是提高相似 prompt 打到同一台伺服器的機率，並不保證黏著，caching 永遠是 best-effort。

### 4.5 用 Responses API 取代 Chat Completions

如同 [Why we built the Responses API](https://developers.openai.com/blog/responses-api/) 所說，我們內部的 benchmark 顯示，相比 Chat Completions，Responses API 的 cache 使用率高 40-80%。
原因是 Responses API 會透過 `previous_response_id`（如果是 stateless，則用 [encrypted reasoning items](https://platform.openai.com/docs/guides/reasoning?api-mode=responses#encrypted-reasoning-items)）在回合之間保留原始的 chain of thought token，Chat Completions 沒辦法保留這些 token。如果你沒有用 reasoning 模型，就不會有 caching 上的改善。想更深入了解，可以看 [Better performance from reasoning models using the Responses API](https://developers.openai.com/cookbook/examples/responses_api/reasoning_items#caching)。

### 4.6 小心處理 Context Engineering

Context engineering 的核心，是決定每次請求要把什麼放進模型的輸入。每個模型的 context window 都是固定的，但精選每次傳什麼，不只是為了不超過上限。輸入變長時，你不只是接近被截斷，還會增加重送的成本，也讓模型要把注意力分散到更多 token 上。有效的 context engineering，就是有意識地管理這個限制。
不過，當你丟掉、摘要或壓縮對話中較早的回合，cache 就會被破壞。從這個角度看，context engineering 跟 prompt caching 本質上互相拉扯，一個重視動態，一個重視穩定。

隨著長時間運行的 agent 跟原生 compaction 工具變多，設計架構時要把 caching 放在心上，在成本跟智慧之間取得平衡。


```
response = client.responses.create(
        model="gpt-5.2-codex",
        input=conversation,
        store=False,
        context_management=[{"type": "compaction", "compact_threshold": 100000}],
    )
```



常見的失敗情形是 tool 太多，讓模型搞不清楚該呼叫哪一個。保持精簡的 tool 範圍，可以提升決策品質，也對長期 context 比較好。如果要針對每次請求挑選 tools，用 4.3 的技巧，靠 [`allowed_tools`](https://developers.openai.com/api/docs/guides/function-calling/#tool-choice) 這個 `tool_choice` 選項來做篩減。


**實用原則**
用你的 eval 來選 compaction 的方法跟頻率，在成本（截斷或摘要減少的總 input token，以及 caching）跟 context engineering 帶來的智慧之間取得平衡。

## 5. 疑難排解：為什麼 cache 命中率偏低

常見原因：
- Tool 或 response format 的 schema 改變
- 碰到模型 context window 上限時的粗暴截斷
- Instructions 或 system prompt 改變
- Reasoning effort 改變
- Cache 過期：時間太久，存起來的 prefix 被丟掉
- 多加了空格、timestamp 或其他動態內容
- 對 reasoning 模型使用 Chat Completions，因為隱藏的 chain-of-thought token 會被丟掉

## 6. Extended Prompt Caching 與 Zero Data Retention

[Extended Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching#extended-prompt-cache-retention) 的做法是，當記憶體滿了，就把 key/value tensor 卸載到 GPU 本地儲存，大幅增加可用於 caching 的容量。對 `gpt-5.5`、`gpt-5.5-pro` 以及之後所有模型，預設是 `24h`，不支援 `in_memory`。

```
{
  "model": "gpt-5.1",
  "input": "Write me a haiku about froge...",
  "prompt_cache_retention": "24h"
}
```



KV tensor 是 prefill 期間由模型 attention 層產生的中間表示。只有 key/value tensor 可能被存在本地儲存，所有原始輸入內容只會保留在記憶體裡。

**Insight：到底 cache 了什麼？**
KV cache 只保存模型的 key/value tensor（hidden state 的線性投影），這樣下一步推論就能重用。KV cache 是一種中間表示，基本上就是模型內部的一堆數字，所以不管保留政策是什麼，原始的文字或多模態輸入都不會被儲存。

## 7. Realtime API

Realtime API 的 caching 跟 Responses API 運作方式一樣：傳進去的所有音訊、文字或圖片都會被 cache，prefix 只要有任何改變就會破壞 cache。不過 Realtime API 的 context window 比較短（目前是 32k），所以管理截斷特別重要。一個 32k context、max output 為 4,096 token 的模型，在發生截斷前，context 裡只能放 28,224 個 token。

### 7.1 Retention Ratio

預設 `(truncation: "auto")` 時，伺服器只會移除剛好夠塞進 context window 的舊 message。這種「剛好就好」的修剪，會在超過上限之後每一回合都稍微移動對話的開頭，這個天真的策略會造成頻繁的 cache miss。
[`retention_ratio`](https://developers.openai.com/api/docs/guides/realtime-costs/#truncation) 設定改變了這點，讓你控制要保留多少較早的 context、丟掉多少。這是一個可設定的截斷策略，讓開發者控制 token context window 保留多少，在保留 context 跟優化 cache 命中之間取得平衡。
例如 `retention_ratio: 0.7` 表示截斷發生時，系統大約保留現有對話視窗的 70%，丟掉最舊的約 30%。這一次丟掉的量比較大，是單次的截斷事件，而不是一小段一小段地移除。


```
{
  "event": "session.update",
  "session": {
    "truncation": {
      "type": "retention_ratio",
      "retention_ratio": 0.7
    }
  }
}
```



這樣會產生更穩定的 prefix，可以跨好幾個回合存活，減少重複破壞 cache。
代價是截斷一次會砍掉比較大塊，所以一次可能失去更多對話歷史，模型可能比逐步截斷更早突然「忘記」對話前面的部分。你等於是用記憶深度換取 cache 穩定性（prefix 更一致）。
下圖是天真的逐回合截斷，跟使用 `retention_ratio` 的影響比較。

![Figure 5](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt-caching-201/figure-5.svg)


## 結論

Prompt caching 是 OpenAI 平台上槓桿最高的優化之一。當你的 prefix 穩定、路由設計得當，就能大幅降低成本跟延遲，而且不用改變模型行為或品質。
核心觀念很簡單但很有力：穩定 prefix、監控 `cached_tokens`、留意約 15 RPM 的限制，並謹慎使用 `prompt_cache_key`。對高流量或不在意延遲的工作負載，可以考慮 Flex Processing 跟 extended retention 來進一步提升 cache 的局部性。
Caching 是 best-effort 而且跟路由有關，但只要有意識地設計，就能帶來很大的效率提升。把它當成任何其他效能系統來對待：先量測、有條理地迭代，並在設計 prompt 時就想著重用。


## 重點整理

- Cache 命中要求 prefix 完全一致，而且落在同一台機器。prompt 要 1024 token 以上才會生效。
- 穩定的東西（instructions、tools、schemas）放前面，會變的東西放後面，動態值如 timestamp 改放 `metadata`。
- `prompt_cache_key` 像 shard key，粒度要抓到每個 prefix + key 組合約 15 RPM 以下。
- 用 Responses API 搭配 reasoning 模型，cache 使用率會比 Chat Completions 高。
- Context engineering（截斷、摘要、compaction）跟 caching 互相拉扯，要用 eval 找平衡。

## 練習

1. 在你的請求之後印出 `usage.prompt_tokens_details.cached_tokens`，連續送同一個長 prompt 兩次，比較第一次跟第二次的數字。
2. 把 prompt 開頭加一個 timestamp 再重送，觀察 `cached_tokens` 掉多少，然後把它改放到 `metadata` 再測一次。
3. 把 tools 陣列固定，改用 `allowed_tools` 在不同請求限制可用的 tool，確認 `cached_tokens` 沒有掉下來。
