---
translated: true
source: articles/gpt-oss/handle-raw-cot.md
---

# 怎麼處理 gpt-oss 的 raw chain of thought

> 原文：[articles/gpt-oss/handle-raw-cot.md](https://github.com/openai/openai-cookbook/blob/main/articles/gpt-oss/handle-raw-cot.md)



## 這篇在做什麼
說明 gpt-oss 模型的 raw chain of thought (CoT) 該怎麼處理。涵蓋 harmony 格式、Chat Completions API 和 Responses API 對 CoT 的規範，以及為什麼不能把 raw CoT 直接給終端使用者看。

## 學完你會
- 知道 CoT 在 harmony 格式裡放哪個 channel，以及後續回合哪些訊息該丟掉、哪些該保留
- 照 OpenRouter 的慣例在 Chat Completions API 實作 `reasoning` 欄位
- 在 Responses API 處理新增的 `reasoning_text` content 和相關事件

[gpt-oss 模型](https://openai.com/open-models)提供 raw chain of thought (CoT)，原本是給模型實作者做分析和安全研究用的，但它對 tool calling 的表現也很關鍵，因為 tool call 可以是 CoT 的一部分。同時，raw CoT 可能包含有害內容，也可能向使用者透露實作者不想透露的資訊（例如給模型的指示裡的規則）。所以你不應該把 raw CoT 顯示給終端使用者。

## Harmony / chat template 的處理

模型把 raw CoT 編碼成我們 [harmony response format](https://cookbook.openai.com/articles/openai-harmony) 的一部分。如果你在自己寫 chat template 或直接處理 token，請先[看 harmony 指南](https://cookbook.openai.com/articles/openai-harmony)。

重點整理幾件事：

1. CoT 會輸出到 `analysis` channel
2. 在後續 sampling 回合中，有訊息送到 `final` channel 之後，所有 `analysis` 訊息都應該丟掉。送到 `commentary` channel 的 function call 可以保留
3. 如果 assistant 最後一則訊息是任何類型的 tool call，那麼直到前一則 `final` 訊息為止的 analysis 訊息，在後續 sampling 時都應該保留，直到 `final` 訊息產生

## Chat Completions API

如果你在實作 Chat Completions API，OpenAI 已發布的規格裡沒有處理 chain of thought 的官方規範，因為我們的託管模型短期內不會提供這個功能。請改為遵循 [OpenRouter 的以下慣例](https://openrouter.ai/docs/use-cases/reasoning-tokens)，包括：

1. 除非請求裡指定 `reasoning: { exclude: true }`，否則 raw CoT 會包含在回應裡。[細節看這裡](https://openrouter.ai/docs/use-cases/reasoning-tokens#legacy-parameters)
2. raw CoT 以輸出訊息上的 `reasoning` 屬性公開
3. 對 delta 事件來說，delta 有 `reasoning` 屬性
4. 在後續回合，你應該能收到先前的 reasoning（以 `reasoning` 傳入），並依照上面 chat template 段落指定的行為處理它。

有疑問時，請遵循 OpenRouter 實作的慣例和行為。

## Responses API

對於 Responses API，我們擴充了 Responses API 規格來涵蓋這個情況。下面是規格變更的型別定義。大致上我們做了：

1. 在 `reasoning` 上新增 `content` 屬性。這讓可以顯示給終端使用者的 reasoning `summary`，能跟 raw CoT 同時回傳（raw CoT 不該顯示給終端使用者，但對可解釋性研究可能有幫助）。
2. 新增一種叫 `reasoning_text` 的 content type
3. 新增兩個事件：`response.reasoning_text.delta` 用來串流 raw CoT 的 delta，`response.reasoning_text.done` 用來表示一個 CoT 回合已完成
4. 在後續回合，你應該能收到先前的 reasoning，並依照上面 chat template 段落指定的行為處理它。

**Item type 的變更**

```typescript
type ReasoningItem = {
  id: string;
  type: "reasoning";
  summary: SummaryContent[];
  // new
  content: ReasoningTextContent[];
};

type ReasoningTextContent = {
  type: "reasoning_text";
  text: string;
};

type ReasoningTextDeltaEvent = {
  type: "response.reasoning_text.delta";
  sequence_number: number;
  item_id: string;
  output_index: number;
  content_index: number;
  delta: string;
};

type ReasoningTextDoneEvent = {
  type: "response.reasoning_text.done";
  sequence_number: number;
  item_id: string;
  output_index: number;
  content_index: number;
  text: string;
};
```

**事件的變更**

```typescript
...
{
	type: "response.content_part.added"
	...
}
{
	type: "response.reasoning_text.delta",
	sequence_number: 14,
	item_id: "rs_67f47a642e788191aec9b5c1a35ab3c3016f2c95937d6e91",
	output_index: 0,
	content_index: 0,
	delta: "The "
}
...
{
	type: "response.reasoning_text.done",
	sequence_number: 18,
	item_id: "rs_67f47a642e788191aec9b5c1a35ab3c3016f2c95937d6e91",
	output_index: 0,
	content_index: 0,
	text: "The user asked me to think"
}
```

**回應輸出範例**

```typescript
"output": [
  {
    "type": "reasoning",
    "id": "rs_67f47a642e788191aec9b5c1a35ab3c3016f2c95937d6e91",
    "summary": [
      {
        "type": "summary_text",
        "text": "**Calculating volume of gold for Pluto layer**\n\nStarting with the approximation..."
      }
    ],
    "content": [
      {
        "type": "reasoning_text",
        "text": "The user asked me to think..."
      }
    ]
  }
]

```

## 把 raw CoT 顯示給終端使用者

如果你提供聊天介面給使用者，不應該顯示 raw CoT，因為它可能包含有害內容或其他你不打算給使用者看的資訊（例如 developer message 裡的指示）。我們建議改為顯示摘要過的 CoT，類似我們在 API 或 ChatGPT 的 production 實作，由 summarizer 模型審查並阻擋有害內容，不讓它顯示出來。

## 重點整理
- raw CoT 是給實作者分析和安全研究用的，同時對 tool calling 效能也很重要。
- 不要把 raw CoT 顯示給終端使用者，因為可能有有害內容或洩漏 instructions。
- harmony 格式裡 CoT 在 `analysis` channel，`final` 訊息出現後要丟掉 analysis，但 tool call 進行中要保留。
- Chat Completions 用 `reasoning` 欄位，Responses API 用 `reasoning_text` content 和對應的串流事件。
- 要給使用者看就用摘要過的 CoT。

## 練習
1. 寫一個函式，輸入一串帶 channel 標記的訊息，依 harmony 規則在 `final` 之後丟掉 `analysis` 訊息。
2. 在 Chat Completions 的回應處理裡，加入 `reasoning` 欄位的解析，並依 `exclude` 設定決定要不要保留。
3. 在串流處理裡加入 `response.reasoning_text.delta` 事件的分支，把 raw CoT 記到 log、但不輸出給使用者。
