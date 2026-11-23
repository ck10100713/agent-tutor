---
translated: true
source: examples/o-series/o3o4-mini_prompting_guide.ipynb
---
# o3/o4-mini Function Calling 指南

> 原文：[examples/o-series/o3o4-mini_prompting_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/o-series/o3o4-mini_prompting_guide.ipynb)

用 prompt 的最佳做法，改善 o3/o4-mini 的 function calling。

## 這篇在做什麼

這篇整理 o3/o4-mini 這兩個 reasoning 模型在 function calling 上的 prompting 技巧，包含 developer message 怎麼寫、function description 怎麼寫、怎麼降低幻覺和偷懶，以及搭配 Responses API 和 hosted tool 的做法。

## 學完你會

1. 用 developer message 設定角色、規定 tool call 的順序，並劃清什麼時候該用或不該用 tool。
2. 把使用條件、few-shot 範例和關鍵規則放進 function description，並用 `strict` 和明確指示降低 tool call 的幻覺。
3. 用 Responses API 把 reasoning item 帶回去，並規劃 hosted tool、自訂 function 和 MCP 混用時的 tool 路由。

## 開跑前

文中的範例 cell 會呼叫 OpenAI API，需要 `OPENAI_API_KEY`。

## 簡介
o3/o4-mini 是我們 o-series 模型的最新成員，訓練成回答之前會想比較久。它們是我們到目前為止發布最聰明的模型，在 tool calling 能力上比 o1/o3-mini 大幅進步。這些模型被訓練成在自己的 chain of thought（CoT）裡原生使用 tool，讓它們在判斷什麼時候、怎麼用 tool 上推理得更好。我們已經發布一份指南，說明怎麼透過 Responses API 用這些模型[呼叫 function](https://cookbook.openai.com/examples/reasoning_function_calls)，這篇建立在它之上，告訴你怎麼讓這些模型的 function calling 表現最好。

## 改善 function calling 表現的 prompt 指引
要充分發揮 o3/o4-mini 背後的 function calling 能力，我們建議在 developer prompt 和 function description 兩邊都遵循一些最佳做法。

### 關於 reasoning 模型的 developer prompt、system prompt 和 function description
我們引入 developer message，讓 reasoning 模型明確知道某個指令來自開發者。在 o-series 模型裡，開發者提供的任何 system message 都會在內部自動轉成 developer message。實務上，可以把 developer prompt 當成傳統的 system prompt，不過為了清楚和正確，這篇把所有這類指令都稱為 developer prompt/message。

文中提到 function description 時，指的是 API 請求裡 tool 參數中，每個 function 物件的 description 欄位裡的說明文字。這段描述告訴模型什麼時候、怎麼用這個 function。下面是我們 function calling [文件](https://platform.openai.com/docs/guides/function-calling)裡的例子：

```
tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "Get current temperature for provided coordinates in celsius.",
    "parameters": {
        "type": "object",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"}
        },
        "required": ["latitude", "longitude"],
        "additionalProperties": False
    },
    "strict": True
}]
```
這裡的 `"Get current temperature for provided coordinates in celsius."` 就是 function description。

定義講完了，可以開始看最佳做法。



### 用 developer message 設定 context
1. 一般 context：跟一般 prompt engineering 的最佳做法一致，role prompting 有助於設定基本行為、語氣，並列出可能的動作範圍。例如：
```
You are an AI retail agent.

As a retail agent, you can help users cancel or modify pending orders, return or exchange delivered orders, modify their default user address, or provide information about their own profile, orders, and related products.
```
2. Function call 的順序：o3/o4-mini 被訓練成用 tool 達成目標，但它在 tool call 的順序上可能出錯。為了預防這類情況，建議明確列出完成某些任務的順序。例如，要預防 coding agent 可能在還不存在的目錄裡建檔這種失敗情況，加上下面這段通常就夠了：
```
check to see if directories exist before making files
```
對於大量且定義明確的任務，可以進一步明確列出要呼叫的 function 順序，讓它更穩健，例如：
```
To Process a refund for a delivered order, follow the following steps:
1. Confirm the order was delivered. Use: `order_status_check`
2. Check the refund eligibility policy. Use: `refund_policy_check`
3. Create the refund request. Use: `refund_create`
4. Notify the user of refund status. Use: `user_notify`
```

3. 定義何時使用 tool 的界線：釐清模型何時該呼叫、何時不該呼叫某些 tool 很有幫助。這在 developer prompt 層級和 tool description 層級都可以做。下面是一個 developer prompt 範例：
```
Be proactive in using tools to accomplish the user's goal. If a task cannot be completed with a single step, keep going and use multiple tools as needed until the task is completed. Do not stop at the first failure. Try alternative steps or tool combinations until you succeed.

- Use tools when:
  - The user wants to cancel or modify an order.
  - The user wants to return or exchange a delivered product.
  - The user wants to update their address or contact details.
  - The user asks for current or personalized order or profile info.

- Do not use tools when:
  - The user asks a general question like “What’s your return policy?”
  - The user asks something outside your retail role (e.g., “Write a poem”).

If a task is not possible due to real constraints (For example, trying to cancel an already delivered order), explain why clearly and do not call tools blindly.
```

### Function Description
function 的 description 應該說明它什麼時候該被呼叫，以及參數該怎麼組。

function 的 description 是釐清「何時該呼叫」和「參數怎麼組」的理想位置。這能成為 reasoning 模型和 tool API 之間持久的介面契約。

一般來說，function description 定義它做什麼、怎麼呼叫。Developer 指示則是給使用這些 tool 的 agent 的指引。所以如果有多個 tool 可以用在相近的目的，開發者可以在指示裡區分它們。如果 agentic 工作流需要偏好某個 tool 使用順序，或某些 tool 要常用、某些要少用，這些也要寫進 developer 指示。

結構良好的 description 能把關鍵條件和參數要求放在前面，提高準確度並減少誤觸發。它也讓開發者能把「主動程度」的控制規則，放在 developer prompt 之外、更靠近 tool 定義的地方。

1. 使用條件：就像你能透過 developer prompt 調整 function calling 的主動程度，也可以在 function description 層級進一步調整 function 怎麼被呼叫。下面是 file_create function 的例子：
```
Creates a new file with the specified name and contents in a target directory. This function should be used when persistent storage is needed and the file does not already exist.
- Only call this function if the target directory exists. Check first using the `directory_check` tool.  
- Do not use for temporary or one-off content—prefer direct responses for those cases.  
- Do not overwrite existing files. Always ensure the file name is unique.
- Do not overwrite existing files.  
  If replacement is intended and confirmed, use `file_delete` followed by `file_create`, or use `file_update` instead.
```
2. Few shot prompting：雖然 reasoning 模型從 few-shot prompting 得到的好處，不像非 reasoning 模型那麼多，但我們發現 few-shot prompting 能改善 tool calling 表現，尤其是模型很難準確組出 function 參數的時候。例如，下面是一個 grep tool 的 tool description 範例，當作 tool description 傳入：

```
Use this tool to run fast, exact regex searches over text files using the `ripgrep` engine.


- Always escape special regex characters: ( ) [ ] { } + * ? ^ $ | . \\
- Use `\\` to escape any of these characters when they appear in your search string.
- Do NOT perform fuzzy or semantic matches.
- Return only a valid regex pattern string.

Examples:
Literal            -> Regex Pattern         
function(          -> function\\(           
value[index]       -> value\\[index\\]      
file.txt           -> file\\.txt            
user|admin         -> user\\|admin          
path\to\file       -> path\\\\to\\\\file     
```

3. 關鍵規則放前面，減少干擾：注意上面的範例裡，跳脫特殊字元的指示，相對來說是模型最先讀到的東西之一。**比較差**的寫法會是：
```
Performs a fast regex-based text search that looks for exact pattern matches within files or entire directories, leveraging the ripgrep tool for high-speed scanning.
Output follows ripgrep formatting and can optionally display line numbers and matched lines.
To manage verbosity, results are limited to a maximum of 50 hits.
You can fine-tune the search by specifying inclusion or exclusion rules based on file types or path patterns.
This method is ideal when searching for literal text snippets or specific regular expressions.
It offers more accuracy than semantic methods when the goal is to locate a known string or structure.
It’s generally recommended over semantic search when you’re looking for a specific identifier—such as a function name, variable, or keyword—within a defined set of directories or file types.
```

這個寫法表現不好，因為 prompt 有很多內容不是規範性的，而且最重要的參數組法規則沒有放在最顯眼的位置。在這個 ripgrep tool 的 tool calling 準確度 eval 上，前一個 prompt 比這一個高了 6%。





### 預防 function calling 的幻覺
我們知道 o3 模型可能比其他模型更容易產生幻覺。這些幻覺可能表現成模型承諾在背景呼叫 tool 卻沒有真的做，或承諾在之後的回合呼叫 tool 等等。遇到這類情況，在幾個地方講清楚有助於減少這類幻覺：

1. 明確指示：明確指示模型避免常見的幻覺，例如在不可能的情況下承諾之後會呼叫 function。

```
Do NOT promise to call a function later. If a function call is required, emit it now; otherwise respond normally.
```

2. 及早抓出錯誤的參數：
把 `strict` 設成 `true`，能確保 function call 可靠地遵守 [function schema](https://platform.openai.com/docs/guides/function-calling?api-mode=responses#strict-mode)。我們建議盡可能開啟。

如果你的參數還有額外複雜的格式要求（例如要是合法的 python 程式碼等），加上下面這個指示可以提醒模型預期的格式。

```
Validate arguments against the format before sending the call; if you are unsure, ask for clarification instead of guessing.
```

3. 另一個關於偷懶行為的說明：
我們知道 o3 有少數偷懶的情況，例如說自己沒有足夠時間完成任務、承諾之後另外跟進，或即使明確要求更詳細，還是給很簡短的答案。我們發現下面這些做法有助於改善：

    a. 不相關的主題開新對話：
       切換到新的或不相關的主題時，開一個新的對話串，不要在同一個 context 裡繼續。這能幫模型專注在目前的主題，避免被之前不相關的 context 影響，那有時會導致回答不完整或偷懶。例如，你之前在討論程式除錯，現在想問文件的最佳做法，不需要之前的對話 context，就開新對話，確保清楚和專注。

    b. 清單太長時，丟掉不相關的過往 tool call 和輸出，改在 user message 裡用摘要當作 context：
       如果對話歷史裡有一長串已經不相關的過往 tool call 或輸出，就把它們從 context 移除，改在 user message 裡提供重要資訊的簡短摘要。這樣 context 比較好管理，模型也只會拿到最相關的資訊。例如，你有一長串 tool 輸出，可以把關鍵結果摘要起來，下一則訊息只放那份摘要。

    c. 我們持續在改進模型，預期未來的版本會解決這個問題。


### 避免 Chain of Thought prompting
這些模型是 reasoning 模型，會產生內部的 chain of thought，所以不需要明確 prompt 它們在 tool call 之間規劃和推理。因此，開發者不該要求模型更廣泛地規劃，來引導它在每次 function call 前多推理。要求 reasoning 模型多推理，反而可能傷害表現。

順帶說明一下 reasoning summary：模型在呼叫 tool 之前會輸出 reasoning token，但不一定會附上摘要，因為我們的 reasoning summary 需要有一定數量的實質 reasoning token 才會產生摘要。


# Responses API

### 用 reasoning item 提升表現
我們發布過一份 [cookbook](https://cookbook.openai.com/examples/responses_api/reasoning_items)，詳細說明使用 Responses API 的好處。這份指南裡還是值得重提幾個主要重點。o3/o4-mini 都是在單一回合內，tool call 之間保留內部 reasoning 的情況下訓練的。所以在推論時，在 tool call 之間保留這些 reasoning item，會讓模型更聰明、表現更好，也就是更能判斷什麼時候、怎麼呼叫 tool。Responses 讓你能保留這些 reasoning item（由我們維護，或者如果你不想讓我們處理狀態管理，就自己透過加密內容維護），Chat Completion 則做不到。換到 Responses API，讓模型在 function call 之間能存取 reasoning item，是讓 function call 表現最大化最簡單的方法。下面是 cookbook 裡的範例，為了方便重現在這裡，示範怎麼用 `encrypted_content` 把 reasoning item 傳回去，而我們這邊不保留任何狀態：


```python
from openai import OpenAI
import requests
import json
client = OpenAI()


def get_weather(latitude, longitude):
    response = requests.get(f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,wind_speed_10m&hourly=temperature_2m,relative_humidity_2m,wind_speed_10m")
    data = response.json()
    return data['current']['temperature_2m']


tools = [{
    "type": "function",
    "name": "get_weather",
    "description": "Get current temperature for provided coordinates in celsius.",
    "parameters": {
        "type": "object",
        "properties": {
            "latitude": {"type": "number"},
            "longitude": {"type": "number"}
        },
        "required": ["latitude", "longitude"],
        "additionalProperties": False
    },
    "strict": True
}]

context = [{"role": "user", "content": "What's the weather like in Paris today?"}]

response = client.responses.create(
    model="o3",
    input=context,
    tools=tools,
    store=False,
    include=["reasoning.encrypted_content"] # Encrypted chain of thought is passed back in the response
)


context += response.output # Add the response to the context (including the encrypted chain of thought)
tool_call = response.output[1]
args = json.loads(tool_call.arguments)



result = get_weather(args["latitude"], args["longitude"])

context.append({                               
    "type": "function_call_output",
    "call_id": tool_call.call_id,
    "output": str(result)
})

response_2 = client.responses.create(
    model="o3",
    input=context,
    tools=tools,
    store=False,
    include=["reasoning.encrypted_content"]
)

print(response_2.output_text)
```

??? note "輸出"

    ```text
    The current temperature in Paris is about 18.8 °C.
    ```

## 用 hosted tool 打造 agentic 體驗
Responses API 支援一組 hosted/內建 tool。我們最近也在 Responses API 加入了[新的 tool 和功能](https://openai.com/index/new-tools-and-features-in-the-responses-api/)，讓連接外部服務的 agentic 應用更容易建構。有了 Responses API 的內建 tool，開發者只要一次 API 呼叫，就能建出更強的 agent。

你可以在同一個 session 裡混用 hosted tool 和自訂 tool。這解鎖了強大的組合模式，但也讓 tool 路由的清楚程度變得關鍵。以下是幾個具體建議：

1. 在 developer prompt 裡明確定義 tool 的使用界線：如果多個 tool 能扮演相近的角色（例如 python tool 和自訂的計算機），就告訴模型偏好哪一個、什麼時候用。這能減少歧義、提高準確度，也避免 tool 用太多或太少。
```
You are a helpful research assistant with access to the following tools:
- python tool: for any computation involving math, statistics, or code execution
- calculator: for basic arithmetic or unit conversions when speed is preferred

Always use the python tool for anything involving logic, scripts, or multistep math. Use the calculator tool only for simple 1-step math problems.
```

2. 釐清什麼時候內部知識不夠：雖然 o3/o4-mini 常常能自己解決任務，tool 可能提供更可靠的答案。用 system prompt 引導模型，在 tool 比較合適時，不要「試著自己解決」。

```
You have access to a `code_interpreter`. Always prefer using `code_interpreter` when a user asks a question involving:
- math problems
- data analysis
- generating or executing code
- formatting or transforming structured text

Avoid doing these directly in your own response. Always use the tool instead.
```

3. 因為 developer prompt 是集中、持久的契約，想混用 hosted tool 和自訂 function 時，就在這裡把 tool 的決策界線寫清楚，包括功能重疊的範圍、信心程度的期待，或 fallback 行為：

```
Use `python` for general math, data parsing, unit conversion, or logic tasks that can be solved without external lookup—for example, computing the total cost from a list of prices.

Use `calculate_shipping_cost` when the user asks for shipping estimates, as it applies business-specific logic and access to live rate tables. Do not attempt to estimate these using the `python` tool.

When both could be used (e.g., calculating a delivery fee), prefer `calculate_shipping_cost` for accuracy and policy compliance. Fall back to `python` only if the custom tool is unavailable or fails.
```
4. 關於 MCP：我們有一份更詳細的[指南](https://cookbook.openai.com/examples/mcp/mcp_tool_guide)，說明使用 MCP tool 的最佳做法，但為了完整，這裡重提幾個高層次的準則（這些不是 o3/o4-mini 專屬，但仍然相關）。

* 過濾 tool 避免 payload 膨脹：善用 allowed_tools 參數，只用必要的 tool，省下不必要的 context。因為你不一定需要 MCP server 回傳的所有 tool，可以透過 allowed_tools 欄位只過濾出需要的。


```
    "tools": [
        {
            "type": "mcp",
            "server_label": "gitmcp",
            "server_url": "https://gitmcp.io/openai/tiktoken",
            "allowed_tools": ["search_tiktoken_documentation", "fetch_tiktoken_documentation"],
            "require_approval": "never"
        }
```

* 用 caching 降低延遲，並把 reasoning 模型留給高複雜度的任務：確保你有傳回 `mcp_list_tools`，或帶上 `previous_response_id`，這樣 API 就不需要一再不必要地重新匯入 tool 清單。
* MCP 搭配其他 tool 使用：你可以混用 MCP、其他 hosted tool 和自己定義的 function。混用時，在整體的 developer prompt 裡定義決策界線，明確說明什麼時候該用哪個 tool，會很有幫助。MCP tool 指南裡有[一個很好的範例](https://cookbook.openai.com/examples/mcp/mcp_tool_guide#using-mcp-with-other-tools)。


### 常見問題（FAQ）

**Q：多少個 function 算太多？**

**A：** o3 和 o4-mini 沒有硬性的 function 數量上限，但根據訓練資料分佈和觀察到的模型行為，有一些實務上的指引。截至 2025 年 5 月，tool 少於約 100 個、每個 tool 的參數少於約 20 個的設定，算在訓練分佈內，應該能在預期的可靠度範圍內運作。表現仍取決於你的 prompt 設計和任務複雜度。

即使技術上在訓練分佈內，tool 越多也可能帶來歧義或混淆。以下是關鍵考量：

* function description 的清楚程度變得關鍵：如果多個 tool 用途重疊或描述含糊，模型可能呼叫錯的，或猶豫著不呼叫任何一個。

* tool 清單大小會影響延遲和推理深度：清單越長，模型在推理階段要解析的選項越多。雖然 o3/o4-mini 能靠整合的推理流程處理，但如果 schema 不夠清楚或呼叫條件不夠明確，表現可能下降。

* tool 幻覺會隨複雜度增加：尤其是 o3，有人回報在 tool 集合很大又定義不足時，會出現幻想或臆測的 tool call。明確的指示能緩解（例如「只能用 tool X、Y、Z。不要自己發明 tool call，也不要拖到之後的回合」）。

最終表現會依用途而異，所以投資在你信得過、可以拿來迭代的 eval 很重要。


**Q：tool 裡面可以有很深的巢狀參數嗎，還是應該把 schema 「攤平」？**

**A：** 同樣沒有硬性指引。不過，即使你的巢狀結構技術上支援，很深層的參數樹也可能影響表現或可靠度。不確定的時候，建議傾向把參數做成扁平的。

扁平結構通常比較容易讓模型推理：在比較扁平的 schema 裡，參數欄位在最上層，一眼就看得到。這減少內部解析和組織結構的需要，能避免像是巢狀物件只填一半，或欄位組合無效的問題。在很深的巢狀物件裡，尤其是有重複或語意相近的欄位名稱時，模型更可能漏掉或誤用參數。

巢狀有助於組織複雜邏輯，但需要額外小心：對於天生就有結構化輸入的領域，像是設定 payload、豐富的搜尋過濾條件或表單提交，巢狀有助於整理相關參數。不過，你得用清楚的欄位描述、anyOf 邏輯或 strict schema 這類技巧，防止無效的參數組合並提高模型可靠度。

最好的選擇方式是用你自己的 eval 測試並衡量成功率。沒有「一體適用」的答案，因為呼叫行為是湧現的，而且對 prompt 很敏感。


**Q：這份 function-calling 指引適用於自訂的 tool 格式嗎？**

**A：** 不保證。這份文件的指引假設你用標準的 `tools` 模型參數傳入 function schema，就像我們 function calling [一般指南](https://platform.openai.com/docs/guides/function-calling)裡示範的那樣。我們的 o3/o4-mini 模型被訓練成原生理解並使用這些 schema 來選 tool 和組參數。

如果你是在開發者撰寫的 prompt 裡，用自然語言提供自訂的 tool 定義（例如在 developer message 或 user message 裡內嵌定義 tool），這份指引可能不完全適用。這種情況下：
模型不是依靠它內部的 tool schema 先驗。
你可能需要更明確地提供 few-shot 範例、輸出格式和 tool 選擇條件。
沒有 schema 層級的錨點，參數組裝的可靠度可能下降。

可以的話用結構化的 tools 參數。如果一定要用自由文字定義 tool，就把它當成自訂協定，並相應地測試。

## 重點整理

- developer message 負責角色、tool 的順序和使用界線，function description 負責什麼時候呼叫、參數怎麼組。
- 關鍵規則放在 description 最前面，並避免太多非規範性的內容，few-shot 範例在模型組不好參數時有幫助。
- 對 o3 的幻覺和偷懶，要明確指示、開 `strict`，並在換主題時開新對話，或把過長的 tool 歷史摘要掉。
- 這些是 reasoning 模型，不需要也不該要求它們在 tool call 之間多規劃，在 Responses API 保留 reasoning item 反而更有幫助。
- 混用 hosted tool、MCP 和自訂 function 時，把路由規則寫進 developer prompt，並用 `allowed_tools` 控制 tool 數量，schema 盡量扁平。

## 練習

1. 把文中 grep tool 的 description，改成把跳脫字元的規則放在最後面，比較一下兩種寫法的 tool call 參數有沒有差別。
2. 在 developer prompt 加一段明確指示，禁止承諾之後才呼叫 tool，並用一個資訊不足的問題測試模型的反應。
3. 在 MCP 範例裡用 `allowed_tools` 只留下一兩個 tool，檢查請求的 payload 和模型行為有沒有改變。
