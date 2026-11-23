---
translated: true
source: examples/partners/harness_aware_plugin_evals/harness_aware_plugin_evals.ipynb
---
# Plugin 的 Harness-aware 評估

> 原文：[examples/partners/harness_aware_plugin_evals/harness_aware_plugin_evals.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/harness_aware_plugin_evals/harness_aware_plugin_evals.ipynb)

用直接 tool 測試、受控的 model loop 和 Codex harness 三種方式評估一個 MCP plugin，再用共用的測試案例和 trace 診斷並改善它的行為。

## 這篇在做什麼

同一個 plugin 跑三種層級的評估：直接測 tool、自己寫的 function-calling loop、真正的 Codex harness。用同一組測試案例比較，看出為什麼 plugin 在自己的評估裡拿高分，放進產品後卻會失敗，並把差異追到是哪一層造成的。

## 學完你會

- 用同一份 `promptfooconfig.yaml` 測試案例，分別跑直接 tool 測試、standalone function-calling loop 和 Codex harness。
- 讀懂 grader 怎麼檢查 tool call，並用 MCP server 的 `instructions` 欄位修好 Codex 下的失敗案例。
- 設計容易看出問題的測試案例（有 tag、會答錯的情境），並量化跑多次的不穩定程度。

## 開跑前

- 安裝 uv 和 Node.js（含 npm）。
- OpenAI API key（放進 `.env`）；直接 tool 測試和重播已錄好的結果不用 key，其他兩種會呼叫付費模型，預設設定一次約 $0.01。
- Codex 驗證（這裡用 API key）。


## 總覽

一個 plugin 在你自己的評估裡分數很高，放進它要上線的產品後還是可能失敗。差距很大一部分來自模型外面的 harness，因為 harness 決定模型看到的 prompt 和能用的 tool。這篇用三種擬真程度跑同一組測試案例，並示範怎麼把差異追到造成它的那一層。

模型常常需要最新、專門的資料和動作，這是光靠訓練給不了的。[Plugin](https://developers.openai.com/plugins/concepts/plugins) 可以把 skill 或帶有可呼叫 tool 的 MCP server，連同自然語言說明一起打包。這個 plugin 把 Codex harness（現在是 ChatGPT desktop app 的一部分）接到 Bureau of Labor Statistics（BLS）的資料。
因為 [BLS API](https://www.bls.gov/developers/) 需要已知的 series ID，plugin 會先把使用者的問題解析成排序過的候選 series。

這種 plugin 最好用多個層級來評估，在速度、成本和擬真程度之間取得平衡。同一個模型可以在小而受控的 loop 裡把每個模糊的查詢都解對，換到真正的 agent 裡卻幾乎不呼叫 tool。某個設定下的分數不會直接套用到另一個設定，因為分數衡量的是整個設定，不只是模型。

| 做法                               | 測什麼                                                                                              | 漏掉什麼                                                                                                                                       | 需要什麼                                                                                                    | 成本     | 擬真度                                           |
| ---------------------------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------ |
| **直接 tool 測試**            | 直接把結構化輸入送給 tool，最適合除錯 tool 邏輯                                                     | 自然語言解讀和 tool 選擇                                                                                                                       | Tool 程式碼和結構化的測試資料                                                                               | 免費     | 最低                                             |
| **Standalone function-calling loop** | 在受控的 function-calling loop 裡透過 MCP 測自然語言解讀和 tool 選擇                              | Product harness 的行為                                                                                                                         | 執行中的 MCP server、模型 API 權限，以及 loop 程式碼                                                        | 中等     | 中等                                             |
| **Product harness**           | 同樣的查詢透過裝了 plugin 的 [Codex](https://openai.com/codex/) harness 執行                        | 評估環境可能沒重現的 client 專屬行為。拿代表性樣本和目標 client 比對，找出差距                                                                 | 執行中的 MCP server、已安裝的 plugin、Codex 驗證（這裡用 API key），以及 harness 設定                       | 最高     | 最高，但不及 ChatGPT desktop app 本身            |

逐步示範用的是簡化的範例 plugin，跑在合成資料上，刻意只涵蓋部分領域，讓評估失敗會浮現。它也用了精選的五個評估案例。

結果那一章報告的是另外對正式版 BLS plugin 做的評估，共 108 題、涵蓋 56 個 BLS 調查。它的程式碼和資料不隨這篇一起提供。



## 設定

這篇附有可以直接跑的範例。隨附的 [README](https://github.com/openai/openai-cookbook/blob/main/examples/partners/harness_aware_plugin_evals/README.md) 列出前置條件並詳細說明每一步，[Makefile](https://github.com/openai/openai-cookbook/blob/main/examples/partners/harness_aware_plugin_evals/Makefile) 則把每一步包成單一 target。

BLS 領域太複雜，不適合直接拿來教評估的機制。所以接下來用它的縮小版：小到可以整個讀完，在筆電上幾分鐘就能跑完。



### 相依套件

這個範例需要 [uv](https://docs.astral.sh/uv/getting-started/installation/)、[Node.js 和 npm](https://nodejs.org/en/download)，以及給會呼叫模型的那幾次執行用的 OpenAI API key。

Python 套件從隨附的 lockfile 安裝到 kernel 的環境：

```python
!uv sync --active --inexact --no-dev --quiet
```

把 `.env.example` 複製成 `.env` 並填入 key。Standalone loop 的設定從 `.env` 讀取。Codex 的模型和 key 取自 `.env`，server URL 則取自 plugin 的 `.mcp.json`。

直接 tool 測試不用 `.env`，也不花錢。
另外兩種做法需要有效的 OpenAI API key，會產生付費的模型呼叫。
預設設定下，一次執行約 $0.01（以 API 價格計）。
把 `EVAL_MODEL` 設成你的 key 能用的模型。它跟結果那一章比較的模型無關。

因為這兩種做法是透過 HTTP 呼叫 MCP server，所以在任一個 eval 開始前，server 都要先在跑。`make server` 在前景執行，所以要另開一個 terminal。

這篇附的 notebook 跑起來不花錢。直接 tool 測試是即時執行。
另外兩種做法重播 `data/` 底下錄好的結果。設 `RUN_LIVE=1` 的話，standalone loop 和沒有 server instructions 的 Codex 執行會改成即時跑。
有 server instructions 的 Codex 執行除非你手動重現，否則維持使用錄好的結果。
`notebook_setup.py` 裡的 `prepare()` 會載入 `.env` 並讓 Codex 指向這個範例。在即時模式下，它還會檢查 key、清空 `outputs/`、寫入 Codex 設定，必要時啟動 server：

```python
from notebook_setup import prepare, stop_server

RUN_LIVE = prepare()
```

[Promptfoo](https://www.promptfoo.dev/) 是開源的 eval runner。它從 YAML 檔載入測試案例，把每個案例送給 provider（回答它的模型或腳本），並用 assertion 對輸出評分。這個範例用它同時執行 standalone loop 和 Codex，它的設定檔裡包含三種做法共用的測試案例。從 lockfile 安裝 Node 套件（包含 promptfoo）：

```python
if RUN_LIVE:
    !npm ci --silent
```

### 範例 plugin

這篇把四個詞分開使用：

- Tool：暴露給模型的單一函式，由參數的 schema 定義。
- MCP server：實作 Model Context Protocol 的 process，對 client 公開可呼叫的 tool。
- Plugin：把上述這些東西，連同產品安裝它所需的 metadata 一起打包。
- Harness：模型執行時周圍的一切，包括 agent loop、prompt 格式化、tool call 執行、turn 上限和 sandbox policy。

Server 有兩個 tool，都定義在 `server.py`，透過 [FastMCP](https://gofastmcp.com/) 以 HTTP 提供。`resolve(indicators)` 接收一或多個經濟指標，回傳排序過的候選 BLS series，每個都有信心分數。
`fetch_bls_data(series_ids)` 接收 series ID，回傳它們的觀測值，如果 ID 不在 catalog 裡就回傳錯誤紀錄。

這兩個 tool 背後是合成的 fixture 資料，用來以縮小的方式重現真實領域的三種特性（多個有效答案中有預設值、真正的歧義、資料缺口），並刻意不放 CPI。Series ID 看起來像真的 BLS 代碼，例如 `LNS14000000` 和 `CES0000000001`，但本身沒有任何內部結構。三個指標代表這三種特性：

- `unemployment rate` 有刻意設計的歧義。`resolve` 回傳經季節調整的 series 和未調整的 series，依序排好，以調整後的版本作為慣用預設，選擇則留給呼叫端。
- `employment` 回傳兩個衡量不同東西、信心分數相同的候選：家戶調查的就業人數和非農就業人數，沒有預設值可以退回。
- `consumer price index` 沒有對應。Resolver 回傳空的候選清單，並附上說明這個缺口是確定的。

直接呼叫 `resolve` 就能一次看到這三種情況：

```python
from server import IndicatorQuery, resolve

resolve(indicators=[
    IndicatorQuery(indicator="unemployment rate"),
    IndicatorQuery(indicator="employment"),
    IndicatorQuery(indicator="consumer price index"),
])
```

??? note "輸出"

    ```text
    {'results': [{'indicator': 'unemployment rate',
       'candidates': [{'series_id': 'LNS14000000',
         'title': 'Unemployment Rate - Seasonally Adjusted',
         'confidence': 1.0},
        {'series_id': 'LNU04000000',
         'title': 'Unemployment Rate - Not Seasonally Adjusted',
         'confidence': 0.6}]},
      {'indicator': 'employment',
       'candidates': [{'series_id': 'LNS12000000',
         'title': 'Employment Level - Seasonally Adjusted',
         'confidence': 0.5},
        {'series_id': 'CES0000000001',
         'title': 'All Employees, Total Nonfarm - Seasonally Adjusted',
         'confidence': 0.5}]},
      {'indicator': 'consumer price index',
       'candidates': [],
       'note': 'No series in this catalog covers that indicator. This is a definitive answer, not a transient failure.'}]}
    ```

### 範例資料集

範例資料集裡的每個案例都有兩種形式並排：一個是結構化欄位，給確定性檢查傳給 resolver；另一個是自然語言查詢，模型得自己把它轉成同樣的請求。`expected_series_ids` 是共用的預期欄位。空字串代表這個案例不該 fetch 任何 series。歧義案例多一個欄位 `expected_top_ids`：resolver 應該回傳兩個並列的候選，而模型應該什麼都不 fetch 並反問使用者。五個案例都在同一個檔案 `promptfooconfig.yaml`，所以每種做法讀的都是同一份資料。下面列出其中三個：

```yaml
tests:
  - description: unemployment-rate
    vars:
      indicator: unemployment rate
      query: What is the U.S. unemployment rate?
      expected_tools: "resolve,fetch_bls_data"
      expected_series_ids: "LNS14000000"
    metadata:
      mechanism: ambiguous_default
      expected_type: exact

  - description: consumer-price-index
    vars:
      indicator: consumer price index
      query: What is the current consumer price index?
      expected_tools: "resolve"
      expected_series_ids: ""
    metadata:
      mechanism: coverage_gap
      expected_type: gap

  - description: employment-ambiguous
    vars:
      indicator: employment
      query: What is U.S. employment?
      expected_tools: "resolve"
      expected_series_ids: ""
      expected_top_ids: "LNS12000000,CES0000000001"
    metadata:
      mechanism: ambiguous_concept
      expected_type: clarify

```

`mechanism` 標記案例測的是什麼，`expected_type` 標記什麼算正確答案。兩者都存成 promptfoo 的 metadata，grader 不會用到。它們會出現在執行報告裡，讓你可以依這些欄位篩選一次執行：

```shell
npx promptfoo eval -c promptfooconfig.yaml --filter-metadata mechanism=coverage_gap
```

有了這個篩選，你不用逐列手動檢查，就能看出「模型只在覆蓋缺口的案例失敗」這類規律。



## 直接 tool 測試：沒有模型參與的確定性檢查

直接 tool 測試把同一份範例資料集的結構化形式，丟給 plugin 的 `resolve` tool。沒有自然語言問題要解讀，也沒有模型決定要呼叫哪個 tool。這個檢查載入 `promptfooconfig.yaml`，直接從 `server.py` 呼叫 `resolve`，完全不涉及 MCP client、promptfoo 或網路。

```python
import yaml

from server import IndicatorQuery, resolve

with open("promptfooconfig.yaml") as f:
    CASES = [test["vars"] for test in yaml.safe_load(f)["tests"]]


def top_candidates(indicator: str) -> set[str]:
    result = resolve(indicators=[IndicatorQuery(indicator=indicator)])
    candidates = result["results"][0]["candidates"]
    if not candidates:
        return set()
    best = max(candidate["confidence"] for candidate in candidates)
    return {c["series_id"] for c in candidates if c["confidence"] == best}


top_candidates("consumer price index")
```

??? note "輸出"

    ```text
    set()
    ```

Runner 把這組結果和每個案例的預期比較，每個案例印一行。
Consumer price index 案例預期沒有 series，因為它不是這個範例 plugin 認得的四個指標之一。Runner 也會檢查 `resolve` 在那裡回傳的是空的候選清單，而不是亂猜。
`level_one.py` 大約一秒就跑完五個案例：

```python
%run level_one.py
```

??? note "輸出"

    ```text
    PASS  'unemployment rate'                 -> LNS14000000
    PASS  'labor force participation rate'    -> LNS11300000
    PASS  'nonfarm payroll employment'        -> CES0000000001
    PASS  'consumer price index'              -> None
    PASS  'employment'                        -> CES0000000001, LNS12000000

    5/5 passed
    ```

直接 tool 測試的優點包括：

- 又快又免費：不需要 API key、網路呼叫或模型。
- 確定性：同樣的輸入每次輸出都一樣，沒有模型帶來的每次執行的雜訊；案例失敗時腳本會以非零狀態結束，所以可以直接放進 CI。
- 診斷很精準：失敗直接指向 resolver 自己的邏輯，不用懷疑是模型還是 harness 造成的。

直接 tool 測試不會檢查模型能不能把白話問題轉成適當的 tool call 和最終答案。
接下來兩種做法加入模型，先從對同樣五個案例跑 standalone function-calling loop 開始。



## Standalone function-calling loop

Standalone 評估用一個小的、應用程式自己擁有的 function-calling loop，取代 Codex 這種完整的 agent harness。模型收到 MCP tool，選擇要呼叫哪些，觀察結果，然後產生最終答案。

主要優點是：
- 成本較低：同樣的查詢用的 token 比在完整 agent harness 裡少。
- 設定簡單：不用安裝 plugin，沒有 agent home 目錄、shell、approval policy，也沒有容器化的 Codex runtime。
- 除錯直接：沒有隱藏行為，只有一個設定檔，失敗很容易隔離。

這些程式碼片段只要改 prompt 和 tool 名稱，就能改用在別的 MCP server。這個範例用 Promptfoo 執行，但別的 eval runner 也能實作同樣的三種做法。



### Function-calling loop

這個 loop 使用 [Responses API](https://developers.openai.com/api/reference/responses/overview)。它把 MCP tool 暴露出來，並記錄每次呼叫供之後檢視。它把整段對話放在 `input` 裡，並設 `store: False`，所以不需要 server 端的狀態，也能在 zero-data-retention 的 key 上運作。

Server 公告的 tool 就是模型看到的 tool：

```python
async with AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]) as openai, Client(mcp_url) as mcp:
    mcp_tools = await mcp.list_tools()
    tools = [
        {
            "type": "function",
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,
        }
        for tool in mcp_tools
    ]
```

每一步都送出整段對話，沒有要求任何 tool 的回應就結束這次執行：

```python
for step in range(max_steps + 1):
    response = await openai.responses.create(input=conversation, **request)
    function_calls = [item for item in response.output if item.type == "function_call"]
    if not function_calls:
        return {
            "answer": response.output_text,
            "tool_calls": recorded_calls,
            "completed": True,
        }
    if step == max_steps:
        break

    # The API rejects round-tripped items that still carry null-valued fields.
    conversation += [item.model_dump(exclude_none=True) for item in response.output]
    for call in function_calls:
        arguments = json.loads(call.arguments or "{}")
        result = await mcp.call_tool(call.name, arguments)
        recorded_calls.append({"name": call.name, "arguments": arguments, "result": result.structured_content})
```

每個 tool 結果都以 `function_call_output` item 放回對話裡，讓下一步看得到。



### Assertion

Standalone loop 和 Codex 共用 `eval_grading.py` 裡的 `grade`。它檢查的是一次執行的 tool call，不是答案文字。案例通過的條件是：預期的 tool 有執行、預期的 series 有回傳、沒有 fetch 其他 series，而且執行結束時答案不是空的。
「沒有其他 series」這條規則也會抓到在真實 ID 旁邊 fetch 一個捏造 ID 的情況。
對於 `employment-ambiguous`，它檢查 `resolve` 有被呼叫，而且兩個候選都沒被 fetch。它沒辦法判斷這個答案有沒有請使用者釐清，也沒辦法判斷答案有沒有說出取得的數值。這些檢查都不能證明答案是對的。正式的評估還需要答案層級的檢查，例如其中一種 [promptfoo assertion](https://www.promptfoo.dev/docs/configuration/expected-outputs/)。
這篇逐步示範裡五個案例的計數來自這個 grader。正式版的通過率則來自另外的 LLM rubric judge。

對一次手寫、捏造了 CPI series 的執行呼叫 `grade`，會回傳這個判定：

```python
from eval_grading import grade

invented = [{"name": "resolve", "arguments": {"indicators": ["consumer price index"]}, "result": {}},
            {"name": "fetch_bls_data", "arguments": {"series_ids": ["CUUR0000SA0"]}, "result": {}}]
grade(invented, {"expected_tools": "resolve", "expected_series_ids": ""}, "unavailable", completed=True)
```

??? note "輸出"

    ```text
    {'pass': False,
     'score': 0.0,
     'reason': "fetched series outside the expectation: ['CUUR0000SA0']"}
    ```

### 把資料集接到 provider

資料集就是 Setup 裡看到的同一份 `promptfooconfig.yaml`，包含 `tests` 區塊。每個案例的 `vars.query` 是資料的自然語言那一半，`vars.expected_series_ids` 是共用的判定。檔案的其餘部分把這份資料集接到 provider 和 assertion：

```yaml
description: Standalone BLS MCP function-calling evaluation

providers:
  - id: file://provider.py
    label: standalone-mcp
    config:
      model: "{{ env.EVAL_MODEL }}"
      model_reasoning_effort: "{{ env.EVAL_REASONING_EFFORT | default('medium', true) }}"
      mcp_url: "{{ env.MCP_URL }}"

prompts:
  - "{{query}}"

defaultTest:
  assert:
    - type: python
      value: file://assert_result.py
```



### 執行評估

整個 eval 就是一次 promptfoo 呼叫。`--no-cache` 讓重複執行是真的模型執行，而不是 promptfoo 的重播，執行會把完整 trace 寫到 `outputs/l2-results.json`：

```python
if RUN_LIVE:
    !npx promptfoo eval -c promptfooconfig.yaml --no-cache --output outputs/l2-results.json
```

有案例失敗的執行會以非零狀態結束，下面的 Codex 執行就是故意這樣，所以判定要看後面的評分，不是看結束狀態。

![Standalone loop Promptfoo web report](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/harness-aware-level-2-web.png)

*Standalone loop 錄好的五案例執行的 promptfoo 報告。每一列是一個案例，Outputs 欄裡是模型的最終答案，以及 grader 讀取的已記錄 tool call。*

在附上的錄製執行裡，五個案例全部通過，包括 consumer price index 案例。
`resolve` 沒回傳候選，而 loop 的 system prompt 禁止捏造 series ID，所以模型會報告這個缺口。同一個案例在 Codex 下會失敗。



## Product harness：Codex

Promptfoo 的 `openai:codex-sdk` provider 把同樣的五個查詢送給 Codex。它啟動 Codex 時使用裝了 BLS plugin 的 Codex home，並加上使用者在 desktop app 輸入 `@BLS` 時會得到的前綴。

兩種設定拿到的 instruction 也不同。Standalone loop 的 system prompt 告訴模型不要捏造 series ID，並在候選並列時說出兩個。Codex 沒有這種 instruction。



### Codex provider 設定

`config.toml` 以絕對路徑指向 `.codex-home/` marketplace 並啟用 plugin。Repository 附的是 `config.toml.example`。即時執行會寫入目前 checkout 的路徑，`make setup` 在 terminal 裡也是這樣做。

同一個檔案還定義了一個 [permission profile](https://developers.openai.com/codex/permissions)，限制一次執行能存取的範圍：

```toml
default_permissions = "eval"

[permissions.eval.filesystem]
":workspace_roots" = "deny"
```

主要的 provider 設定有：

```yaml
providers:
  - id: openai:codex-sdk
    config:
      model: "{{ env.EVAL_MODEL }}"
      working_dir: .
      enable_streaming: true
      cli_env:
        CODEX_HOME: "{{ env.CODEX_HOME }}"
```

檔案的其餘部分設定 reasoning effort、關閉網路存取和 web search、關掉 approval 和 git repository 檢查，並把 `tests` 指向載入共用資料集的 `level_3_tests.py`。

把專案資料夾裡的 shell 交給 agent，會造成嚴重的評估風險。
`promptfooconfig.yaml` 存著每個測試案例的預期答案，`.env` 存著正式的 API key。有檔案存取權的模型可以讀到它們，並從答案檔直接過關每個案例。Permission profile 就是防止這件事。`deny` 規則讓目錄不能讀寫，讓量測聚焦在 plugin 本身。評估仍然跑得動，因為檔案系統規則不適用於透過 HTTP 的 MCP 流量。明確設定 `CODEX_HOME` 才會讓 Codex 指向 plugin。不設的話，Codex 會從使用者預設的 home 啟動，BLS plugin 不會載入，模型就無法呼叫 `resolve` 或 `fetch_bls_data`。

Prompt 本身維持是自然語言查詢。前綴透過 `defaultTest.options.prefix` 加入，下面的文字和使用者在 desktop app 加上 `@BLS` mention 時 Codex 看到的內容一致。

```yaml
prompts:
  - "{{query}}"

defaultTest:
  options:
    prefix: "[@BLS](plugin://BLS@cookbook-plugins) "
```

![ChatGPT desktop app prefix](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/harness-aware-desktop-prefix.png)

`enable_streaming: true` 讓 promptfoo 在 provider response 裡保留 Codex 的 item stream。
Assertion 從那個 trace 讀 `mcp_tool_call` item，其中任何一個失敗就讓案例失敗，並把它們正規化成和 standalone loop 記錄的相同 `{"name", "arguments", "result"}` 格式，讓兩種做法進入 `eval_grading.py` 裡同一個 grader。

```python
mcp_items = [item for item in raw.get("items", []) if item.get("type") == "mcp_tool_call"]
for item in mcp_items:
    if item.get("error") or item.get("status") == "failed":
        return {
            "pass": False,
            "score": 0.0,
            "reason": f"MCP tool call failed: {item.get('tool')}",
        }

calls = [
    {
        "name": item.get("tool"),
        "arguments": _arguments(item),
        "result": (item.get("result") or {}).get("structured_content"),
    }
    for item in mcp_items
]
```

`assert_codex_result.py` 的其餘部分從 provider response 取出 trace，並在 provider 沒回報錯誤且最終回應不是空的時候，把這次執行算作完成。



### 執行範例

`.env` 填好、server 也在跑的情況下，plugin 會安裝到同一個 `CODEX_HOME`，然後對 `promptfooconfig.codex.yaml` 執行評估。`CODEX_HOME` 透過 Setup 裡載入的環境傳到這兩個指令：

```python
import subprocess

if RUN_LIVE:
    subprocess.run(["npx", "codex", "plugin", "add", "BLS@cookbook-plugins"], check=True)
    !npx promptfoo eval -c promptfooconfig.codex.yaml --no-cache --output outputs/l3-results.json
```

安裝失敗就會讓這個 cell 停下來。不然 Codex 會碰不到任何 tool，每個案例都會因為錯的原因失敗。評分會把五個案例都報告成缺少預期的 tool。

![Codex Promptfoo web report](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/harness-aware-level-3-web.png)

*同樣的五個案例透過 Codex harness 執行，在 server 發布任何指引之前。`consumer-price-index` 失敗，是因為它 fetch 了 resolver 從未回傳的 ID；`employment-ambiguous` 失敗，是因為它 fetch 了 resolver 有回傳的候選，而不是問使用者想要哪一個。*

在 `data/` 底下錄好的執行裡，standalone loop 五個案例全過，Codex 則是五題對三題。全新的即時執行可能得到不同的數量，因為這兩個失敗都取決於模型剛好走的路徑。

範例 server 沒有 CPI series，`resolve` 正確地什麼都沒回傳。Codex 接著自己提供一個 ID：它用 `CUUR0000SA0` 呼叫 `fetch_bls_data`，這是真正的 BLS CPI ID，server 從未回傳過。Codex 寫出的答案是真的，因為它告訴使用者這個數字取不到，但這個沒有依據的 fetch 讓案例失敗。

Employment 案例的失敗方式不同。
Codex 可能在呼叫 `resolve` 之前就把請求縮到單一指標，之後在並列的候選中選一個，或是兩個都 fetch。
確切的路徑每次執行可能不同，但每一種都取得至少一個 series，而不是停下來釐清，所以 grader 判它失敗。

Server 可以給 Codex 缺少的 instruction。MCP server 在 [handshake](https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle) 期間會送出 `instructions` 欄位，規格把它描述成 client 可以加進 system prompt 的提示。Codex 會把它傳給模型。Standalone loop 用自己的 system prompt，忽略這個欄位。

範例讓這個欄位保持空白，所以全新執行仍然能看到這些失敗。在 `FastMCP` constructor 加一個字串就能提供這個指引：

```python
GUIDANCE = """Answer only from this catalog. Call resolve first, passing the indicator the user
asked about without narrowing it. Pass fetch_bls_data only the series IDs that resolve returned,
never one from your own knowledge. If resolve returns no candidate, say the data is unavailable. If
several candidates tie for the best confidence, do not call fetch_bls_data at all. Name them and ask
which one the user wants."""

mcp = FastMCP("BLS evaluation fixture", instructions=GUIDANCE)
```

編輯 `server.py` 之後，重啟 MCP server 並重跑 Codex eval。Server 只在 `initialize` 回應裡送 `instructions`，執行中的 server 會一直送舊的空值。

在有 instructions 的錄製執行（`data/l3-trace-after.json`）裡，Codex 五個案例全部通過，而 tool 和 resolver 都沒改。

在錄好的執行裡，一個案例在 Codex 下約 10 秒，在 standalone loop 約 25 秒。



### 重播三次執行

三次錄好的執行都在 `data/`。Grader 不需要 API key、server 或 Codex 登入就能重新評分。有 instructions 的那次執行永遠從錄製檔載入，因為要即時重現它，得套用程式碼修改並重跑 Codex cell。
`replay.py` 重新評分三次執行，`make replay` 在 terminal 裡執行它：

```python
%run replay.py
```

??? note "輸出"

    ```text
    Standalone loop: 5/5 from data/l2-trace.json
    Codex, empty instructions: 3/5 from data/l3-trace-before.json
        consumer-price-index: fetched series outside the expectation: ['CUUR0000SA0']
        employment-ambiguous: fetched series outside the expectation: ['CES0000000001', 'LNS12000000']
    Codex, with instructions: 5/5 from data/l3-trace-after.json
    ```

Notebook 會停掉它啟動的 server：

```python
stop_server()
```

### 對 ChatGPT desktop app 的抽樣檢查

這篇所有 product harness 的數字都來自 OpenAI Codex SDK provider，不是 ChatGPT desktop app 本身。對這個範例做的檢查顯示，它的 tool call 和 Codex eval 相同，包括推測出來的 `CUUR0000SA0` ID。在真正的專案裡，完整的檢查應該涵蓋更多的範例。

![ChatGPT desktop CPI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/harness-aware-desktop-cpi.png)

*在 ChatGPT desktop app 手動執行 consumer price index 案例。*



## 解讀結果：Model-harness 相容性

範例 plugin 的 CPI 案例以小規模說明了 model-harness 相容性：同樣五個問題，在 standalone loop 和 Codex 下得到不同結果。有即時 API 呼叫、tool 更多的正式版 plugin，範圍比較典型，評估涵蓋 56 個 BLS 調查的 108 個問題。
Benchmark 結果來自這個 108 題的資料集，使用 LLM rubric judge，而不是五案例範例裡的 tool-call 檢查。

| 設定                | 值                                                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| 資料集              | 正式資料集的 held-out 測試切分，56 個 BLS 調查的 108 個單輪問題                                                         |
| Judge               | 針對最終答案的 LLM rubric，`gpt-5.6-sol`                                                                                |
| 版本                | Codex 0.159.2、promptfoo 0.123.1                                                                                        |
| 重複次數            | 表 1 每個模型跑一次，表 2 和表 3 跑三次，皆關閉 response cache                                                          |

*正式版 benchmark 的設定。*



### 三個模型，一個 harness

三個模型在 Codex（product harness）下跑這份資料集。
模型是唯一的變數：

| 模型         | 通過率    | 每題 tool call 數     | 每題 reasoning token 數     |
| ------------ | --------- | --------------------- | --------------------------- |
| GPT-6.1 Sol  | 0.94      | 4.02                  | 19                          |
| GPT-6 Astra  | 0.94      | 3.74                  | 14                          |
| GPT-6 Luna   | 0.88      | 5.54                  | 1,229                       |
*表 1：正式版 plugin 在 Codex 下的通過率和成本，涵蓋 108 題的主要評估資料集，所有模型用同一個 grader。*

這次執行中，GPT-6.1 Sol 和 GPT-6 Astra 在 108 題裡只差一題。這樣的結果證據太少，無法可靠地為兩者排名。

GPT-6 Luna 的分數比較大的模型低，同時 tool call 比 GPT-6.1 Sol 多約 40%，每題的 reasoning token 超過它的 60 倍。



### 觀察到的差距變化

模型之間的差距也取決於產生它的 harness。GPT-5-mini 是舊模型，留下來當比較基準，因為它是這個 plugin 開發時用的便宜 baseline。它在 Codex 下表現下滑，促成了這篇的 harness 比較。GPT-6 Luna 和 GPT-5-mini 在 Codex 下差很多，在 standalone loop 裡則接近得多：

| Harness                                      | GPT-6 Luna   | GPT-5-mini |
| -------------------------------------------- | ------------ | ---------- |
| Product harness (Codex)                      | 0.88         | 0.43       |
| Standalone function-calling loop             | 0.74         | 0.64       |

*表 2：正式版 plugin 在兩種 harness 下的結果，問題和表 1 相同。*

在 standalone loop 裡，GPT-6 Luna 和 GPT-5-mini 平均差約 10 個百分點，單次執行差 1 到 19 點。在 Codex 下差距大得多。和 standalone loop 相比，GPT-6 Luna 多了 14 點，GPT-5-mini 少了 21 點。



### 為什麼 GPT-5-mini 在 Codex 下表現較差

GPT-5-mini 在那裡的失敗，大約一半和 shell 有關。模型呼叫 agent 的 shell，執行了沒有作用的指令。它大約一半的答案以反問使用者收尾。
整份資料集裡，它在 Codex 下每 100 題約有 85 題會呼叫 tool，而同一個 harness 上的 GPT-6 Luna 幾乎每題都會呼叫。Standalone loop 沒有 shell。在相同資料集上，GPT-5-mini 在那裡每 100 題約有 95 題會呼叫 tool。



### 為什麼 GPT-6 Luna 在 standalone loop 表現較差

GPT-6 Luna 失敗的原因不同。在 standalone loop 裡，它大部分失敗的答案不是說要求的資料取不到，就是停在 loop 的步數上限。
在 Codex 下這些 turn 會繼續進行，這可以解釋那裡多出來的大部分每題 tool call，不過這些執行並沒有把機制單獨分離出來驗證。



## 處理 non-determinism

把這篇的通過率當作相對的衡量。Standalone loop 和 Codex 之間的通過率差了 14 和 21 個百分點。下面的重複實驗說明結果在不同次執行之間會怎麼變化。

直接 tool 測試每次都該回傳同樣的判定，因為執行時沒有模型參與。
但涉及模型的執行，即使設定相同，不同次也可能產生不同結果：

- 模型可能選擇另一條路徑來解決任務。
- LLM judge 對同一個答案可能評得不同。
- 差異也可能來自模型或 harness 的外部更新。

用同一個 Codex 設定、GPT-6 Luna，對上面 benchmark 設定的 108 題跑三次，得到下面的分布：

| 重複次數                    | 1     | 2     | 3     |
| --------------------------- | ----- | ----- | ----- |
| 通過率                      | 0.88  | 0.89  | 0.86  |
| 每題 tool call 數           | 5.54  | 5.70  | 5.20  |
| 每題 reasoning token 數     | 1,229 | 1,195 | 1,146 |

*表 3：正式版 plugin 在 Codex 下三次重複執行。*

- 整體通過率幾乎不動：三次之間只差 3 點。
- 個別問題的變動比這個差距暗示的大得多。108 題裡有 23 題（21%）在三次執行中某處在通過和失敗間翻轉，而總體保持穩定。
- Tool call 數的波動一樣大：有一題在某次重複用了 5 次 tool call，另一次用了 19 次。



## 實務心得

用最便宜、又能暴露你正在調查的問題的做法：

- 每當 resolver 邏輯或 fixture 資料改變，就跑直接 tool 測試。
- 在迭代 tool description、prompt、評分或選模型時，用 standalone loop。
- 每個新模型都跑 product harness，不要假設兩種做法的結果一致。如果一致，就在 standalone loop 裡迭代，product harness 留給 release 檢查和給 stakeholder 看的結果。

寫測試案例時，要包含看似合理的答案其實是錯的情況，例如正確答案是一小串 series、需要釐清的請求（「物價在漲嗎？」可能指消費者物價或生產者物價），或是根本沒有資料。給每個案例標記它測什麼、什麼算正確，就像範例的 `mechanism` 和 `expected_type`。這樣就能把執行篩成正在開發的那一塊，同樣的標記也能顯示哪些領域最需要新的測試案例。

把 eval 的 trace 和正式環境的執行比對，抓出設定漏掉的差異，例如 agent instructions、tool 可用性或 runtime 版本。只量一次的通過率，也可能看起來比底下逐案例的實際情況穩定得多。
自動重複跑同樣的案例來量穩定度，並把這個穩定度當成獨立的指標。對同一個問題，判定在不同次執行之間大幅擺盪的系統，可能不如平均分數稍低但行為更可預測的系統有用。

比較便宜的 harness 和較小的模型在快速迭代時有幫助，但它們只是近似真正上線的東西。正式環境的行為來自實際部署的 harness 和模型的組合。相信最後那次執行之前，有幾件事要確認：

- 模型在 eval 裡看到的 framing 和在正式環境一樣，而且每個要傳給它的設定值都有傳到。
- 同樣的設定在關閉 cache 的情況下跑過不只一次。
- 除了通過率，也檢查每題的 tool call 數和 reasoning token 數。
- 有人工審查過具代表性的答案樣本。



### 自己動手試

多層級的結構，以及共用一份資料集和 grader 的模式，是可以重複使用的，但改用在別的 plugin 時，各個元件都需要修改：

| 領域                 | 檔案                                                                  | 動作    | 要改什麼                                                                                                     |
| -------------------- | --------------------------------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------------ |
| MCP server           | `server.py`                                                         | 取代    | 換成目標 server，並更新 standalone loop 和 plugin 使用的 MCP URL。                                           |
| 測試案例             | `promptfooconfig.yaml`                                              | 更新    | 提供領域專屬的查詢、結構化輸入、預期結果和 metadata。                                                        |
| 評估邏輯             | `level_one.py`, `eval_grading.py`                                 | 更新    | 讓直接 tool 測試和共用評分配合目標 tool 的 schema 和預期。Grader 檢查 tool 名稱、參數格式和預期結果欄位，所以這些改變時它也要改。 |
| Instructions         | `provider.py` 和 MCP server 的 `instructions`                     | 更新    | 讓 standalone 的 system prompt 和產品看得到的指引符合想要的行為。Product harness 通常自己提供 system prompt，所以給它的指引要放在 tool description 或 MCP server 的 instructions。 |
| Plugin 設定          | `.codex-home/marketplaces/`, `.mcp.json`, `config.toml.example` | 更新    | 設定 plugin 識別、marketplace 位置、MCP endpoint 和隔離的 Codex home。                                       |
| 評估結構             | 三種做法全部                                                          | 保留    | 維持直接 tool 測試、standalone loop 和 product harness 之間的分離。                                          |



## 延伸閱讀

- [AI Agents That Matter](https://arxiv.org/abs/2407.01502)
  說明評估 agent 和評估模型有什麼不同。
- [τ-bench](https://arxiv.org/abs/2406.12045)
  提出 `pass^k`，也就是 `k` 次獨立嘗試全部成功的機率。
- [Moving from OpenAI Evals to Promptfoo](https://developers.openai.com/cookbook/examples/evaluation/moving-from-openai-evals-to-promptfoo)
  逐案例把 OpenAI Evals 的測試組在 promptfoo 重建。
- [Codex sandboxing](https://developers.openai.com/codex/concepts/sandboxing)
  介紹 Codex 執行可以採用的模式，以及每種模式允許什麼。



## 貢獻者

這份 cookbook 是 OpenAI 和 [deepsense.ai](https://deepsense.ai/) 共同合作的成果，deepsense.ai 建置並評估了 BLS connector。

- [Maciej Domagała](https://www.linkedin.com/in/macdomagala/)
- [Łukasz Dragan](https://www.linkedin.com/in/%C5%82ukasz-d-a22b3986/)
- [Michał Rdzany](https://www.linkedin.com/in/micha%C5%82-rdzany-85567a225/)
- [Danny Wigg](https://www.linkedin.com/in/dannywigg/)

## 重點整理

- 評估分數衡量的是整個設定（模型加 harness），不只是模型，所以同一個 plugin 在 standalone loop 和 Codex 下結果可以差很多。
- 分三層評估：直接 tool 測試便宜又確定，standalone loop 適合快速迭代，product harness 最接近真實但最貴。
- 共用同一份資料集和 grader，才能把差異追到是哪一層造成的。
- MCP server 的 `instructions` 欄位可以給 harness 缺少的指引，不用改 tool 或 resolver。
- 涉及模型的結果會浮動，總通過率穩定也不代表個別案例穩定，要重複跑並把穩定度當成指標。

## 練習

1. 在 `promptfooconfig.yaml` 新增一個案例，查詢一個 resolver 不認得的指標（像 `producer price index`），預期不 fetch 任何 series，再跑直接 tool 測試看 `resolve` 是否回傳空清單。
2. 在 `FastMCP` constructor 的 `instructions` 字串裡寫一段指引（遇到並列候選就反問、不要自己編 series ID），重啟 server 後重跑 Codex eval，看 `consumer-price-index` 和 `employment-ambiguous` 有沒有過。
3. 改 `eval_grading.py` 的 `grade`，加一條檢查最終答案是否有向使用者反問，用 `employment-ambiguous` 驗證，並把 Codex eval 連跑三次，記錄哪些案例的判定在不同次之間翻轉。
