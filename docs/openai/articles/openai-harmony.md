---
translated: true
source: articles/openai-harmony.md
---

# OpenAI Harmony 回應格式

> 原文：[articles/openai-harmony.md](https://github.com/openai/openai-cookbook/blob/main/articles/openai-harmony.md)



## 這篇在做什麼

`gpt-oss` 系列模型是用 harmony 回應格式訓練的，這個格式定義了對話結構、reasoning 輸出和 function call 的寫法。這篇從 role、channel 講到特殊 token、system / developer 訊息，再到 tool call 和 structured output，適合要自己架 inference 的人。

## 學完你會

- 分清楚 `system`、`developer`、`user`、`assistant`、`tool` 五種 role 和 `analysis`、`commentary`、`final` 三種 channel 各自的用途。
- 用 `openai_harmony` 函式庫 render 對話，或自己照 `<|start|>`、`<|message|>`、`<|end|>` 的格式手刻 prompt。
- 正確組出 function calling 的輸入：定義 `functions` namespace、處理 `to=functions.xxx` 的呼叫，以及把 tool 輸出和前一段 CoT 一起丟回去。

## 開跑前

只有自己架 `gpt-oss` inference 才需要這些。透過 API 或 Ollama 之類的服務使用的話，格式會由它們處理。

[`gpt-oss` 模型](https://openai.com/open-models)是用 harmony 回應格式訓練的，這個格式用來定義對話結構、產生 reasoning 輸出，以及組織 function call。如果你不是直接用 `gpt-oss`，而是透過 API 或 Ollama 這類 provider，就不用管這些，因為 inference 方案會處理格式。如果你是自己架 inference，這份指南會帶你走過 prompt 格式。這個格式刻意模仿 OpenAI Responses API，用過那個 API 的話應該會覺得眼熟。`gpt-oss` 不能不用 harmony 格式，不然會無法正常運作。

## 概念

### Roles

模型處理的每則訊息都有一個 role。模型認得五種 role：

| Role        | 用途                                                                                                                                                                                 |
| :---------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `system`    | system 訊息用來指定 reasoning effort、knowledge cutoff 這類 meta 資訊，還有內建 tool                                                                         |
| `developer` | developer 訊息用來提供給模型的指示（一般稱為「system prompt」的東西）和可用的 function tool                |
| `user`      | 通常代表模型的輸入                                                                                                                                           |
| `assistant` | 模型的輸出，可以是 tool call 或訊息。輸出也可能帶有一個「channel」，標示這則訊息的意圖。 |
| `tool`      | 代表 tool call 輸出的訊息。訊息裡的 role 會用具體的 tool 名稱。                                                                      |

這些 role 同時也是模型遇到指示衝突時採用的資訊優先順序：`system` \> `developer` \> `user` \> `assistant` \> `tool`

#### Channels

assistant 訊息可以輸出到三種「channel」，用來區分給使用者看的回應和內部用的訊息。

| Channel      | 用途                                                                                                                                                                                                                                                                                                                                                            |
| :----------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `final`      | 標在 final channel 的訊息是要給終端使用者看的，代表模型的回應。                                                                                                                                                                                                                                 |
| `analysis`   | 這是模型拿來做 chain of thought (CoT) 的訊息。**重要：** analysis channel 的訊息不符合 final 訊息的安全標準，避免顯示給終端使用者。                                                                                                                             |
| `commentary` | function tool call 通常會在 `commentary` channel 觸發，內建 tool 通常在 `analysis` channel 觸發。不過內建 tool 偶爾還是會輸出到 `commentary`。這個 channel 偶爾也會被模型用來在呼叫多個 function 前產生 [preamble](#preambles)。 |

## Harmony renderer 函式庫

可以的話，建議透過 [PyPI](https://pypi.org/project/openai-harmony/) 或 [crates.io](https://crates.io/crates/openai-harmony) 使用我們的 harmony renderer，它會自動把你的訊息 render 成正確格式，並轉成模型能處理的 token。

下面的範例用 renderer 建出 system prompt 和一小段對話。

```python
from openai_harmony import (
    Author,
    Conversation,
    DeveloperContent,
    HarmonyEncodingName,
    Message,
    Role,
    SystemContent,
    ToolDescription,
    load_harmony_encoding,
    ReasoningEffort
)

encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)

system_message = (
    SystemContent.new()
        .with_reasoning_effort(ReasoningEffort.HIGH)
        .with_conversation_start_date("2025-06-28")
)

developer_message = (
    DeveloperContent.new()
        .with_instructions("Always respond in riddles")
        .with_function_tools(
            [
                ToolDescription.new(
                    "get_current_weather",
                    "Gets the current weather in the provided location.",
                    parameters={
                        "type": "object",
                        "properties": {
                            "location": {
                                "type": "string",
                                "description": "The city and state, e.g. San Francisco, CA",
                            },
                            "format": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "default": "celsius",
                            },
                        },
                        "required": ["location"],
                    },
                ),
            ]
	)
)

convo = Conversation.from_messages(
    [
        Message.from_role_and_content(Role.SYSTEM, system_message),
        Message.from_role_and_content(Role.DEVELOPER, developer_message),
        Message.from_role_and_content(Role.USER, "What is the weather in Tokyo?"),
        Message.from_role_and_content(
            Role.ASSISTANT,
            'User asks: "What is the weather in Tokyo?" We need to use get_current_weather tool.',
        ).with_channel("analysis"),
        Message.from_role_and_content(Role.ASSISTANT, '{"location": "Tokyo"}')
        .with_channel("commentary")
        .with_recipient("functions.get_current_weather")
        .with_content_type("<|constrain|> json"),
        Message.from_author_and_content(
            Author.new(Role.TOOL, "functions.get_current_weather"),
            '{ "temperature": 20, "sunny": true }',
        ).with_channel("commentary"),
    ]
)

tokens = encoding.render_conversation_for_completion(convo, Role.ASSISTANT)

# After receiving a token response
# Do not pass in the stop token
parsed_response = encoding.parse_messages_from_completion_tokens(new_tokens, Role.ASSISTANT)
```

另外 openai_harmony 函式庫也有 StreamableParser，可以在模型產生新 token 的同時做解析和解碼。例如串流輸出、處理解碼時的 unicode 字元就很好用。

```python
from openai_harmony import (
    load_harmony_encoding,
    Role,
    StreamableParser,
    HarmonyEncodingName
)

encoding = load_harmony_encoding(HarmonyEncodingName.HARMONY_GPT_OSS)
stream = StreamableParser(encoding, role=Role.ASSISTANT)

tokens = [
    200005,35644,200008,1844,31064,25,392,4827,382,220,17,659,220,17,16842,12295,81645,
    13,51441,6052,13,200007,200006,173781,200005,17196,200008,17,659,220,17,314,220,19,
    13,200002
]

for token in tokens:
    stream.process(token)
    print("--------------------------------")
    print("current_role", stream.current_role)
    print("current_channel", stream.current_channel)
    print("last_content_delta", stream.last_content_delta)
    print("current_content_type", stream.current_content_type)
    print("current_recipient", stream.current_recipient)
    print("current_content", stream.current_content)
```

## Prompt 格式

如果你要自己寫 renderer，就得遵守下面的格式。

### 特殊 token

模型用一組特殊 token 來辨識輸入的結構。用 [tiktoken](https://github.com/openai/tiktoken) 的話，這些 token 編在 `o200k_harmony` encoding 裡。所有特殊 token 的格式都是 `<|type|>`。

| 特殊 token           | 用途                                                                                                                                     | Token ID |
| :---------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | :------- |
| <&#124;start&#124;>     | 表示一則[訊息](#message-format)的開頭。後面接訊息的「header」資訊，從 [role](#roles) 開始 | `200006` |
| <&#124;end&#124;>       | 表示一則[訊息](#message-format)的結尾                                                                                           | `200007` |
| <&#124;message&#124;>   | 表示從訊息的「header」轉到實際內容                                                                    | `200008` |
| <&#124;channel&#124;>   | 表示轉到 header 裡的 [channel](#channels) 資訊                                                                                  | `200005` |
| <&#124;constrain&#124;> | 表示轉到 [tool call](#receiving-tool-calls) 裡的資料型別定義                                                | `200003` |
| <&#124;return&#124;>    | 表示模型已經取樣完回應訊息。是有效的「stop token」，代表你該停止 inference。             | `200002` |
| <&#124;call&#124;>      | 表示模型想呼叫 tool。是有效的「stop token」，代表你該停止 inference。                                   | `200012` |

### 訊息格式

harmony 回應格式由「訊息」組成，模型可能一次產生多則訊息。訊息的一般結構如下：

```
<|start|>{header}<|message|>{content}<|end|>
```

`{header}` 包含一串 meta 資訊，其中有 [role](#roles)。`<|end|>` 代表一則完整訊息的結尾，但模型也可能用其他 stop token，例如呼叫 tool 時用 `<|call|>`，表示整個 completion 完成時用 `<|return|>`。

### 聊天對話格式

照上面的訊息格式，最基本的聊天格式是一則 `user` 訊息，加上一則 `assistant` 訊息的開頭。

#### 輸入範例

```
<|start|>user<|message|>What is 2 + 2?<|end|>
<|start|>assistant
```

輸出會從指定 `channel` 開始，例如用 `analysis` 輸出 chain of thought。模型可能輸出多則訊息（主要是 CoT 訊息），並用 `<|end|>` token 分隔。

產生完之後，它會以 `<|return|>` token 停下來，表示最終答案產生完了，或以 `<|call|>` 停下來，表示需要執行一次 tool call。不管哪一種，都代表你該停止 inference。

#### 輸出範例

```
<|channel|>analysis<|message|>User asks: "What is 2 + 2?" Simple arithmetic. Provide answer.<|end|>
<|start|>assistant<|channel|>final<|message|>2 + 2 = 4.<|return|>
```

`final` channel 會包含給使用者請求的答案。chain-of-thought 的細節看 [reasoning 一節](#reasoning)。

**實作注意：** `<|return|>` 只是解碼時的 stop token。把 assistant 產生的回覆加進下一個 turn 的對話歷史時，要把結尾的 `<|return|>` 換成 `<|end|>`，讓存起來的訊息是完整的 `<|start|>{header}<|message|>{content}<|end|>`。所以 prompt 裡先前的訊息都該以 `<|end|>` 結尾。監督式訓練的目標或範例以 `<|return|>` 結尾是合適的，但要保存的歷史要正規化成 `<|end|>`。

### System 訊息格式

system 訊息用來給系統一般性的資訊。這跟其他 prompt 格式裡所謂的「system prompt」不一樣，那個請看 [developer 訊息格式](#developer-message-format)。

我們用 system 訊息來定義：

1. 模型的 **identity**：這個應該一直維持 `You are ChatGPT, a large language model trained by OpenAI.`。想改模型的身分，請用 [developer 訊息](#developer-message-format)裡的指示。
2. Meta **日期**：具體是 `Knowledge cutoff:` 和 `Current date:`
3. **reasoning effort**：可指定的等級是 `high`、`medium`、`low`
4. 可用的 channel：要有最好的表現，這個應該對應到 `analysis`、`commentary` 和 `final`。
5. 內建 tool：模型訓練過 `python` 和 `browser` 兩個 tool。細節看[內建 tool 一節](#built-in-tools)。

**如果你有定義 function，** 還要加一段註記，說明所有 function tool call 都必須送到 `commentary` channel。

要有最好的表現，請盡量貼近這個格式。

#### System 訊息範例

最基本、你該用的 system 訊息如下：

```
<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2025-06-28

Reasoning: high

# Valid channels: analysis, commentary, final. Channel must be included for every message.<|end|>
```

如果 developer 訊息區段裡有 function call，就用：

```
<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2025-06-28

Reasoning: high

# Valid channels: analysis, commentary, final. Channel must be included for every message.
Calls to these tools must go to the commentary channel: 'functions'.<|end|>
```

### Developer 訊息格式

developer 訊息就是一般所謂的「system prompt」。它包含給模型的指示，也可以另外放可用的 [function tool](#function-calling) 清單，或你要模型遵守的 [structured output](#structured-output) 輸出格式。

如果你沒有用 function tool calling，developer 訊息就長這樣：

```
<|start|>developer<|message|># Instructions

{instructions}<|end|>
```

其中 `{instructions}` 換成你的「system prompt」。

要定義 function calling 的 tool，請看[專門的章節](#function-calling)。
要定義 structured output 用的輸出格式，請看[指南裡的這一節](#structured-output)。

### Reasoning

gpt-oss 模型是 reasoning 模型。預設會做 medium 等級的 reasoning。要控制 reasoning，可以在 [system 訊息](#system-message-format)裡指定等級為 `low`、`medium` 或 `high`。建議的格式是：

```
Reasoning: high
```

模型會把原始的 chain-of-thought (CoT) 以 assistant 訊息輸出到 `analysis` channel，最終回應則輸出到 `final`。

例如問 `What is 2 + 2?` 時，模型輸出可能長這樣：

```
<|channel|>analysis<|message|>User asks: "What is 2 + 2?" Simple arithmetic. Provide answer.<|end|>
<|start|>assistant<|channel|>final<|message|>2 + 2 = 4.<|return|>
```

這裡的 CoT 是

```
User asks: “What is 2 + 2?” Simple arithmetic. Provide answer.
```

實際的答案是：

```
2 + 2 = 4
```

**重要：**
模型在 chain-of-thought 上的訓練沒有達到 final 輸出同等的安全標準。不要把 chain-of-thought 顯示給使用者，因為裡面可能有有害內容。[詳情看 model card](https://openai.com/index/gpt-oss-model-card/)。

#### 後續取樣時處理 reasoning 輸出

一般來說，如果 assistant 的回應是以 `final` channel 的訊息結束，後續取樣時要把先前的 CoT 內容丟掉。也就是說，假設第一次的輸入是這樣：

```
<|start|>user<|message|>What is 2 + 2?<|end|>
<|start|>assistant
```

產生的輸出是：

```
<|channel|>analysis<|message|>User asks: "What is 2 + 2?" Simple arithmetic. Provide answer.<|end|>
<|start|>assistant<|channel|>final<|message|>2 + 2 = 4.<|return|>
```

為了讓模型正常運作，下一次取樣的輸入應該是

```
<|start|>user<|message|>What is 2 + 2?<|end|>
<|start|>assistant<|channel|>final<|message|>2 + 2 = 4.<|end|>
<|start|>user<|message|>What about 9 / 2?<|end|>
<|start|>assistant
```

例外是 tool / function calling。模型可以在 chain-of-thought 裡呼叫 tool，所以後續取樣時要把之前的 chain-of-thought 一起傳回去當輸入。完整範例看 [function calling 一節](#function-calling)。

### Function calling

#### 定義可用的 tool

模型能用的所有 function 都要定義在 [developer 訊息](#developer-message-format)裡一個專門的 `Tools` 區段。

定義 function 時，我們用類似 TypeScript 的型別語法，並把 function 包在專門的 `functions` namespace 裡。為了提高 function calling 的準確度，要盡量貼近這個格式。你可以看 harmony renderer 的 codebase，了解我們怎麼把參數的 JSON schema 定義轉成這種格式，一些通則如下：

- 沒有參數的 function 定義成 `type {function_name} = () => any`
- 有參數的 function，把參數命名為 `_` 並 inline 型別定義
- 欄位說明用註解寫在欄位定義的上一行
- 回傳型別一律用 `any`
- 每個 function 定義後面留一個空行
- 把 function 包在一個 namespace 裡，通常用 `functions`，避免跟模型可能訓練過的[其他 tool](#built-in-tools) 衝突。

這是一個包含兩個 function 定義的完整輸入範例：

```
<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2025-06-28

Reasoning: high

# Valid channels: analysis, commentary, final. Channel must be included for every message.
Calls to these tools must go to the commentary channel: 'functions'.<|end|><|start|>developer<|message|># Instructions

Use a friendly tone.

# Tools

## functions

namespace functions {

// Gets the location of the user.
type get_location = () => any;

// Gets the current weather in the provided location.
type get_current_weather = (_: {
// The city and state, e.g. San Francisco, CA
location: string,
format?: "celsius" | "fahrenheit", // default: celsius
}) => any;

// Gets the current weather in the provided list of locations.
type get_multiple_weathers = (_: {
// List of city and state, e.g. ["San Francisco, CA", "New York, NY"]
locations: string[],
format?: "celsius" | "fahrenheit", // default: celsius
}) => any;

} // namespace functions<|end|><|start|>user<|message|>What is the weather like in SF?<|end|><|start|>assistant
```

#### 接收 tool call

模型決定呼叫 tool 時，會在訊息的 header 用 `to={name}` 的格式定義 `recipient`。例如它決定觸發上面的 `get_current_weather` function，header 裡會寫 `to=functions.get_current_weather`，channel 則依 [system 訊息](#system-message-format)的規定是 `commentary`。**recipient 可能出現在 header 的 role 或 channel 部分。**

模型也可能指定 `<|constrain|>` token 來標示 tool call 的輸入型別。這裡因為是用 JSON 傳入，所以 `<|constrain|>` 設成 `json`。

```
<|channel|>analysis<|message|>Need to use function get_current_weather.<|end|><|start|>assistant<|channel|>commentary to=functions.get_current_weather <|constrain|>json<|message|>{"location":"San Francisco"}<|call|>
```

#### 處理 tool call

function call 處理完後，我們要把輸出交還給模型，做法是在 call 訊息後面加一則新的 tool 訊息來放輸出。

tool 訊息的格式如下：

```
<|start|>{toolname} to=assistant<|channel|>commentary<|message|>{output}<|end|>
```

所以以上面的例子來說

```
<|start|>functions.get_current_weather to=assistant<|channel|>commentary<|message|>{"sunny": true, "temperature": 20}<|end|>
```

收集完 tool call 的輸出後，就可以用完整的內容跑 inference：

```
<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2025-06-28

Reasoning: high

# Valid channels: analysis, commentary, final. Channel must be included for every message.
Calls to these tools must go to the commentary channel: 'functions'.<|end|><|start|>developer<|message|># Instructions

Use a friendly tone.

# Tools

## functions

namespace functions {

// Gets the location of the user.
type get_location = () => any;

// Gets the current weather in the provided location.
type get_current_weather = (_: {
// The city and state, e.g. San Francisco, CA
location: string,
format?: "celsius" | "fahrenheit", // default: celsius
}) => any;

// Gets the current weather in the provided list of locations.
type get_multiple_weathers = (_: {
// List of city and state, e.g. ["San Francisco, CA", "New York, NY"]
locations: string[],
format?: "celsius" | "fahrenheit", // default: celsius
}) => any;

} // namespace functions<|end|><|start|>user<|message|>What is the weather like in SF?<|end|><|start|>assistant<|channel|>analysis<|message|>Need to use function get_current_weather.<|end|><|start|>assistant<|channel|>commentary to=functions.get_current_weather <|constrain|>json<|message|>{"location":"San Francisco"}<|call|><|start|>functions.get_current_weather to=assistant<|channel|>commentary<|message|>{"sunny": true, "temperature": 20}<|end|><|start|>assistant
```

如上所示，我們傳回模型繼續取樣的不只有 function 輸出，還有先前的 chain-of-thought（"Need to use function get_current_weather."），讓模型有必要的資訊可以接著做 chain-of-thought 或給出最終答案。

#### Preambles

有時模型會選擇產生「preamble」，告訴使用者它接下來要呼叫哪些 tool，例如它打算呼叫多個 tool 的時候。這時它會在 `commentary` channel 產生一則 assistant 訊息，跟 chain-of-thought 不同，這是要給終端使用者看的。

```
<|channel|>analysis<|message|>{long chain of thought}<|end|><|start|>assistant<|channel|>commentary<|message|>**Action plan**:
1. Generate an HTML file
2. Generate a JavaScript for the Node.js server
3. Start the server
---
Will start executing the plan step by step<|end|><|start|>assistant<|channel|>commentary to=functions.generate_file<|constrain|>json<|message|>{"template": "basic_html", "path": "index.html"}<|call|>
```

這裡模型產生了一份行動計畫，讓使用者知道它接下來要執行的多個步驟。

### Structured output

要控制模型的輸出行為，可以在 [developer 訊息](#developer-message-format)的結尾用下面的結構定義 response format：

```
# Response Formats

## {format name}

// {description or context}
{schema}<|end|>
```

format 名稱的作用類似你在 [Responses API](https://platform.openai.com/docs/guides/structured-outputs?api-mode=responses#how-to-use) 裡替 schema 指定的名稱，schema 則是 JSON Schema。

例如這是一則定義購物清單 schema 的 developer 訊息：

```
<|start|>developer<|message|># Instructions

You are a helpful shopping assistant

# Response Formats

## shopping_list

{"properties":{"items":{"type":"array","description":"entries on the shopping list","items":{"type":"string"}}},"type":"object"}<|end|><|start|>user<|message|>I need to buy coffee, soda and eggs<|end|><|start|>assistant

```

不過光靠這個 prompt 只能影響模型的行為，不保證完全符合 schema。要做到這點，你還是得自己建 grammar，並在取樣時強制執行 schema。

### 內建 tool

`gpt-oss` 模型訓練時學了兩個常見的 tool：一個是瀏覽資訊，一個是執行 python 程式碼，用來改善結果。

如果你想自己做這些功能，請用下面的格式來提高可靠度和準確度。

這些 tool 要定義在 [system 訊息](#system-message-format)，不是 developer 訊息，做法是加一個 `# Tools` 區段。

#### Browser tool

要定義 browser tool，把它加到 system prompt 區段：

```
<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2025-06-28

Reasoning: high

# Tools

## browser

// Tool for browsing.
// The `cursor` appears in brackets before each browsing display: `[{cursor}]`.
// Cite information from the tool using the following format:
// `【{cursor}†L{line_start}(-L{line_end})?】`, for example: `【6†L9-L11】` or `【8†L3】`.
// Do not quote more than 10 words directly from the tool output.
// sources=web (default: web)
namespace browser {

// Searches for information related to `query` and displays `topn` results.
type search = (_: {
query: string,
topn?: number, // default: 10
source?: string,
}) => any;

// Opens the link `id` from the page indicated by `cursor` starting at line number `loc`, showing `num_lines` lines.
// Valid link ids are displayed with the formatting: `【{id}†.*】`.
// If `cursor` is not provided, the most recent page is implied.
// If `id` is a string, it is treated as a fully qualified URL associated with `source`.
// If `loc` is not provided, the viewport will be positioned at the beginning of the document or centered on the most relevant passage, if available.
// Use this function without `id` to scroll to a new location of an opened page.
type open = (_: {
id?: number | string, // default: -1
cursor?: number, // default: -1
loc?: number, // default: -1
num_lines?: number, // default: -1
view_source?: boolean, // default: false
source?: string,
}) => any;

// Finds exact matches of `pattern` in the current page, or the page given by `cursor`.
type find = (_: {
pattern: string,
cursor?: number, // default: -1
}) => any;

} // namespace browser

# Valid channels: analysis, commentary, final. Channel must be included for every message.<|end|>
```

如果模型決定在瀏覽器裡執行動作，它會用跟 [function call](#function-calling) 一樣的格式，但有兩個明顯的例外：

1. 請求會送到 `analysis` channel
2. recipient 分別是 `browser.search`、`browser.open`、`browser.find`

#### Python tool

```
<|start|>system<|message|>You are ChatGPT, a large language model trained by OpenAI.
Knowledge cutoff: 2024-06
Current date: 2025-06-28

Reasoning: high

# Tools

## python

Use this tool to execute Python code in your chain of thought. The code will not be shown to the user. This tool should be used for internal reasoning, but not for code that is intended to be visible to the user (e.g. when creating plots, tables, or files).

When you send a message containing Python code to python, it will be executed in a stateful Jupyter notebook environment. python will respond with the output of the execution or time out after 120.0 seconds. The drive at '/mnt/data' can be used to save and persist user files. Internet access for this session is UNKNOWN. Depends on the cluster.

# Valid channels: analysis, commentary, final. Channel must be included for every message.<|end|>
```

如果模型決定執行 Python 程式碼，它會用跟 [function call](#function-calling) 一樣的格式，但有兩個例外：

3. 請求會送到 `analysis` channel
4. recipient 一律是 `python`

## 重點整理

- harmony 的訊息由 header 加內容組成，用 `<|start|>`、`<|message|>`、`<|end|>` 這些特殊 token 切開，role 的優先順序是 system > developer > user > assistant > tool。
- assistant 輸出分三個 channel：`analysis` 是 CoT，不能給使用者看；`commentary` 放 function call 和 preamble；`final` 才是給使用者的答案。
- 一般情況下，下一輪取樣要丟掉舊的 CoT；只有 tool call 的情況要把 CoT 一起傳回去。
- `<|return|>` 和 `<|call|>` 是 stop token，存進歷史時 `<|return|>` 要改成 `<|end|>`。
- structured output 只是在 prompt 裡影響行為，要保證符合 schema 還是得在取樣時強制 grammar。

## 練習

1. 照頁面上 renderer 的範例，把 reasoning effort 從 medium 改成 high，印出 render 後的 token 或文字，確認 system 訊息裡的 reasoning 那一行變了。
2. 手寫一則多輪對話的 prompt 字串：第一輪的 assistant 回覆從 `<|return|>` 正規化成 `<|end|>`，並丟掉舊的 CoT，接著加第二個 user 問題。
3. 仿照頁面上的 `get_current_weather`，在 `functions` namespace 裡定義一個有參數的新 function，然後手寫模型的 tool call、tool 回傳訊息，以及要丟回模型的完整輸入（記得帶上前一段 CoT）。
