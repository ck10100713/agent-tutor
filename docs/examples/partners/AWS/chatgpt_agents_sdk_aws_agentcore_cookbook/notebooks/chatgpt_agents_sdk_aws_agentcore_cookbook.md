---
translated: true
source: examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/notebooks/chatgpt_agents_sdk_aws_agentcore_cookbook.ipynb
---

# 用 OpenAI Agents SDK 跟 Amazon Bedrock AgentCore 做一個 ChatGPT plugin

> 原文：[examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/notebooks/chatgpt_agents_sdk_aws_agentcore_cookbook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/notebooks/chatgpt_agents_sdk_aws_agentcore_cookbook.ipynb)

用 OpenAI Agents SDK 搭配 Amazon Bedrock 做一個私有的 ChatGPT 航班助理 plugin，透過 Secure MCP Tunnel 接上 ChatGPT，再驗證 tracing 跟 Promptfoo 評估。

## 這篇在做什麼

替一間虛構的航空公司 Eliza Airlines 做一個私有的航班助理：ChatGPT 透過 MCP 呼叫唯讀 tool，背後是跑在 Amazon Bedrock 模型上的 OpenAI Agents SDK workflow，結果顯示在 ChatGPT 的 widget 裡。`ELZ` 航班都是範例資料，不能訂票、改票或取消。預設路徑是 agent 跑在你自己的工作機上，先做完全不需要雲端憑證的本機檢查，再選擇要不要接 Bedrock 跟 ChatGPT。

## 學完你會

- 對 ChatGPT 暴露唯讀 tool，並驗證輸入跟輸出。
- 用 OpenAI Secure MCP Tunnel 把私有的 tool server 接到 ChatGPT。
- 用 Bedrock 模型跑 Agents SDK workflow，並把結果顯示在 ChatGPT widget。
- 在本機檢查整個整合、評估 agent 的最新回應，並確認 trace 送到哪裡。

## 開跑前

- Python 3.10 以上、`uv`、JupyterLab、Node.js 24 以上跟 npm。
- 本機檢查不需要雲端憑證。實際跑 Bedrock、tunnel、AWS Runtime 的步驟需要對應的權限，可能產生模型、telemetry 或 Runtime 費用。
- Secure MCP Tunnel 要由 Platform 管理員先建好，並綁到你的 OpenAI organization 跟 ChatGPT workspace。
- 想用現成的 AgentCore Runtime 的話，需要 Runtime 擁有者提供 ARN 跟 invoke-only role。這份 notebook 不會幫你部署 Runtime。

Eliza 跟 OpenAI 合作的 cookbook。


## 各元件怎麼串起來

**Model Context Protocol (MCP)** 讓 ChatGPT 能發現 tool、用結構化輸入呼叫、再收到結構化結果。這個 repo 裡的 **MCP adapter** 就是對外提供三個航班 tool 的 server，它會檢查 request、跑 agent，並在把結果回給 ChatGPT 之前先驗證回應。

![Default request flow: ChatGPT sends a tool call through the hosted tunnel and local tunnel-client to the MCP adapter and local Agents SDK agent. The agent calls Amazon Bedrock and exports traces to AWS.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/notebooks/images/cookbook-boundaries.svg)

圖上的箭頭是 tool request 的走向，結果會沿同一條路徑回來，**widget**（ChatGPT 裡的一個小 HTML 畫面）負責顯示驗證過的結果。在 MCP 裡，結果放在 `structuredContent` 欄位。widget 自己不會呼叫航班後端。

你工作機上的 `tunnel-client` 會對 OpenAI 的 hosted tunnel endpoint 開一條對外的 HTTPS 連線，ChatGPT 就能透過它連到 `127.0.0.1:8787/mcp` 的 adapter。這個位址是 **loopback**，只有同一台機器連得到，所以你不需要公開的 MCP URL，也不用開 inbound 防火牆規則。

**OpenAI Agents SDK** 負責跑 Python workflow 跟它的 function tool，**Amazon Bedrock** 透過 OpenAI 相容的 endpoint 提供模型。**AgentCore Observability** 接收 trace（記錄一次執行的步驟、耗時跟錯誤）。**span** 則是 trace 裡的一個操作，例如一次模型呼叫或 tool 呼叫。

預設路徑之外有兩個選項：

- 可以用現成的 **AgentCore Runtime**（AWS 的託管 agent 服務）取代你的工作機來跑 workflow。Runtime 擁有者要提供它的 **Amazon Resource Name (ARN)**（AWS 資源識別碼）跟一個 invoke-only role，部署、憑證跟維運都由擁有者管理。
- `COOKBOOK_TRACING_MODE=dual` 會在 AWS observability 之外，再把 trace 送到 OpenAI Traces，需要另一把 OpenAI Platform trace key。預設值 `aws` 只送到 AWS。

Platform 管理員必須先建好 hosted tunnel，並把它關聯到你的 OpenAI organization 跟 ChatGPT workspace。做任何需要憑證的步驟之前，先照 [README 的權限矩陣](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#enterprise-least-privilege-matrix)來。身分、secret 發放、託管跟資料保留也是你們團隊的責任，細節看[架構指南](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/docs/openai-agentkit-cookbook.md#architecture-boundaries)。


## 前置需求

需要基本的 Python 跟命令列經驗，另外還要有：

- Python 3.10 以上；
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)，用來安裝跟執行 Python 環境；
- 鎖定版本的開發環境裡的 JupyterLab，啟動方式看 [README 的啟動指令](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#optional-notebook-and-developer-checks)；
- Node.js 24 以上跟 npm，MCP adapter 跟評估工具會用到。

本機檢查用範例資料，不需要雲端憑證。實際連線的步驟需要 [README 權限矩陣](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#enterprise-least-privilege-matrix)列的權限，而且可能產生模型、telemetry 或 Runtime 費用。

setup cell 會找到 repo 並 import [notebook helpers](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/notebook_helpers.py)。這些 helper 處理子程序 timeout、限量擷取輸出、過濾憑證、服務清理跟評估報告。request 跟 response 的範例則留在 notebook 裡。


```python
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = next(
    (path for path in (Path.cwd(), *Path.cwd().parents)
     if (path / "runtime-agent" / "pyproject.toml").exists()
     and (path / "mcp-adapter" / "package.json").exists()),
    None,
)
if REPO_ROOT is None:
    raise RuntimeError("Run this notebook from the cookbook repository or notebooks directory.")
RUNTIME_DIR, MCP_DIR = REPO_ROOT / "runtime-agent", REPO_ROOT / "mcp-adapter"
sys.path.insert(0, str(RUNTIME_DIR))

from demo_date import demo_travel_date
from notebook_helpers import (
    live_runtime_environment, local_runtime_service, run,
    run_agent_evaluation, selected_environment,
)

DEMO_TRAVEL_DATE = demo_travel_date()
UV, NODE, NPM = (shutil.which(command) for command in ("uv", "node", "npm"))
if not UV or not NODE or not NPM:
    raise RuntimeError("Install uv and Node.js/npm before executing the notebook.")
print("Repository:", REPO_ROOT)
print("Commit:", run(["git", "rev-parse", "HEAD"], REPO_ROOT).stdout.strip())
for name, command in (("uv", UV), ("Node", NODE), ("npm", NPM)):
    print(name + ":", run([command, "--version"], REPO_ROOT).stdout.strip())
```

## 1. 安裝鎖定版本的相依套件

**lockfile** 記錄了每個相依套件的精確版本。repo 附了 `uv.lock` 跟兩份 npm lockfile，讓你能重現測試過的環境。如果 manifest 跟 lockfile 對不上，`uv sync --locked` 和 `npm ci` 會直接失敗。


```python
run([UV, "sync", "--locked", "--extra", "dev"], RUNTIME_DIR)
run([NPM, "ci"], RUNTIME_DIR)
run([NPM, "ci"], MCP_DIR)
print("Locked dependency environments are ready.")
```

## 2. 跟著一個 request 走過 agent

**schema** 定義了 request 或 response 接受哪些欄位跟值。[RuntimeRequest](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/schemas.py) 會在任何 tool 執行之前，先驗證 action 跟它的參數。以 `search_flights` 來說，必須有出發地、目的地跟旅行日期。

[build_agent](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/agent.py) 把 action 對應到一個 function tool（透過 Agents SDK 暴露給模型的 Python 函式）。它只提供該 action 需要的那一個 tool，並告訴模型只呼叫一次。`agent.py` 的核心設定如下：

```python
Agent(
    name="ChatGPT MCP flight cookbook agent",
    instructions="Call the selected read-only function tool exactly once and return its JSON.",
    model=model or os.environ.get(MODEL_ENV, DEFAULT_MODEL),
    output_type=AgentOutputSchema(dict, strict_json_schema=False),
    model_settings=ModelSettings(
        parallel_tool_calls=False,
        tool_choice=tool_choice,
    ),
    tools=tools,
    tool_use_behavior="stop_on_first_tool",
)
```

這裡 `tools` 放被選中的函式，`tool_choice` 是它的名稱。`stop_on_first_tool` 會直接回傳 tool 的輸出，不會再叫模型改寫。真正執行時，`build_bedrock_model()` 提供 Bedrock client，`Runner.run_sync()` 執行這個 agent，runner 會把回傳的 JSON 驗證成 `RuntimeResponse`。

先建一個搜尋 agent，不呼叫模型，只看它的 tool。範例日期預設是 UTC 今天加 45 天，可以用 `COOKBOOK_DEMO_TRAVEL_DATE` 固定下來，方便重複檢查。


```python
from agent import build_agent
from schemas import RuntimeRequest

search_request = RuntimeRequest(
    action="search_flights",
    origin="DAL",
    destination="MDW",
    travel_date=DEMO_TRAVEL_DATE,
)
flight_agent = build_agent(search_request, execution_mode="local")
print("Selected tool:", flight_agent.tools[0].name)
print("After the tool returns:", flight_agent.tool_use_behavior)
```

接著跑 Python 測試、格式檢查跟型別檢查，再把同一個 request 送進本機 entrypoint。`COOKBOOK_FORCE_LOCAL_TOOLS=1` 會直接呼叫範例函式，所以這個檢查不用模型也不用 AWS。同樣的輸入，這些函式會回同樣的範例結果。

`executionMode` 標示走的路徑：`local` 或 `deployed`。舊的 `provider: "agentcore-runtime"` 欄位是為了相容性保留，不代表 agent 實際跑在哪裡。


```python
run([UV, "run", "pytest", "-q"], RUNTIME_DIR)
run([UV, "run", "ruff", "check", "."], RUNTIME_DIR)
run([UV, "run", "ruff", "format", "--check", "."], RUNTIME_DIR)
run([UV, "run", "pyright"], RUNTIME_DIR)

local_env = selected_environment(overrides={
    "COOKBOOK_FORCE_LOCAL_TOOLS": "1",
    "COOKBOOK_EVENT": search_request.model_dump_json(exclude_none=True),
})
smoke = run([UV, "run", "python", "agent.py"], RUNTIME_DIR, local_env)
local_result = json.loads(smoke.stdout)
assert local_result["provider"] == "agentcore-runtime"
assert local_result["executionMode"] == "local"
assert local_result["action"] == "search_flights"
assert local_result["data"]["flights"]
assert all(flight["travelDate"] == DEMO_TRAVEL_DATE for flight in local_result["data"]["flights"])
print(json.dumps(local_result, indent=2))
```

## 3. 在本機呼叫 Runtime HTTP 介面

AgentCore Python SDK 提供兩個 HTTP endpoint：`/ping` 回報健康狀態，`/invocations` 接收 agent request。helper 會在 8080 port 啟動這個 server，cell 結束時（包含失敗時）關掉它。下面的 request 會從搜尋結果取一個航班，用同一個日期查它的狀態。

這是在你的工作機上，用範例 tool 測試已部署 Runtime 的介面。它的 entrypoint 會把回應標成 `executionMode: "deployed"`，光憑這個標記不能證明真的部署在 AWS。


```python
first_flight = local_result["data"]["flights"][0]
with local_runtime_service(UV, RUNTIME_DIR) as health:
    request = urllib.request.Request(
        "http://127.0.0.1:8080/invocations",
        data=json.dumps({
            "action": "get_live_status",
            "flight_number": first_flight["flightNumber"],
            "origin": first_flight["origin"],
            "destination": first_flight["destination"],
            "travel_date": first_flight["travelDate"],
        }).encode(),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        invocation = json.loads(response.read())
    assert health["status"] == "Healthy"
    assert invocation["executionMode"] == "deployed"
    assert invocation["action"] == "get_live_status"
    assert invocation["data"]["flight"]["flightNumber"] == "ELZ1234"
    assert invocation["data"]["flight"]["travelDate"] == DEMO_TRAVEL_DATE
    print("Health:", health)
    print("Invocation:", json.dumps(invocation, indent=2))
```

## 4. 檢查 MCP adapter 跟 widget

adapter 透過 **Streamable HTTP**（MCP 用來在 HTTP 上交換訊息的傳輸方式）暴露 `search_flights`、`get_upcoming_status`、`get_live_status`。每個 tool 都有定義好的輸入 schema，並回傳對應 action 的輸出 schema。這些 tool 是 **idempotent**：重複呼叫不會改變範例資料。

TypeScript 測試涵蓋 tool discovery、呼叫、回應驗證，以及用假的 AWS sender 測 AWS 呼叫的程式碼。它們也檢查 widget 帶版本的 resource URI、content type（MIME type）跟 **Content Security Policy (CSP)**（限制它能載入哪些資源）。widget 用 `textContent` 顯示結果文字，不會把它當 HTML 解析。這些測試不會真的呼叫 AWS。

關鍵的邊界在 [server.ts](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/mcp-adapter/server.ts)：adapter 把驗證過的資料放在 `structuredContent` 回傳，[flight-widget.html](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/mcp-adapter/public/flight-widget.html) 收到 `ui/notifications/tool-result` 時負責渲染。


```python
run([NPM, "run", "typecheck"], MCP_DIR)
run([NPM, "test"], MCP_DIR)
run([NPM, "run", "build"], MCP_DIR)

widget = (MCP_DIR / "public" / "flight-widget.html").read_text(encoding="utf-8")
assert "ui/notifications/tool-result" in widget
assert "textContent" in widget
assert "<script src=" not in widget
print("Typed MCP server and self-contained widget validated.")
```

## 5. 評估回應並驗證 trace

**Evaluation（評估）** 檢查輸出是否符合預期，**Tracing** 記錄執行過程中發生了什麼。這份 cookbook 用 Promptfoo 幫回應打分數，用 AgentCore Observability 檢視執行紀錄，兩者是分開的檢查。

![Promptfoo scores fresh agent responses before release. AWS receives traces by default, with OpenAI Traces available in dual mode. An optional AWS evaluation path scores a dedicated Runtime's completed spans.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/notebooks/images/tracing-evaluation-paths.svg)

[Promptfoo](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/promptfooconfig.agent.cjs) 會把三個航班情境送進本機的 Agents SDK workflow，再檢查每個回應的結構跟預期行為。**AWS Distro for OpenTelemetry (ADOT)** 負責在 agent 裡埋點，記錄 span 並匯出到 AWS。預設是 `COOKBOOK_TRACING_MODE=aws`，`dual` 則會另外用獨立的 `OPENAI_TRACE_API_KEY` 把 trace 也送到 OpenAI。

先跑 `eval:agent:validate`，它只檢查評估設定，不會呼叫 agent。另一個不需要憑證的檢查是 `eval:run`，它把存好的正向跟反向範例（叫 **fixtures**）丟進一個原樣回傳的 echo provider，用範例回應檢查 assertion。

要評估 agent 的最新回應，啟動 Jupyter 前先設 `RUN_PROMPTFOO_AGENT_EVALUATION=1`，可以用 `PROMPTFOO_AGENT_EVALUATION_CASE_IDS` 只選部分案例。helper 會執行有防護的指令並摘要新報告。報告放在被 git 忽略的 `runtime-agent/evals/results/` 目錄，Promptfoo 的 sharing、telemetry 跟 remote generation 都是關閉的。真的跑 agent 可能產生模型跟 telemetry 費用。

評估報告通過，不代表 trace 有送到。要跑 trace smoke 指令，拿它產生的 **correlation ID**（同一次呼叫的各筆紀錄共用的識別碼），配合 [AWS trace checker](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/docs/tracing-and-publication.md#trace-verification-is-a-separate-step) 去查，並考慮 ingestion 的延遲。在 dual 模式下，驗證的人還必須在 OpenAI Traces 裡找到對應的 ID，這份 notebook 不使用未公開的 trace 查詢 API。

[AgentCore Evaluations](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/docs/aws-evaluation.md) 是 AWS 原生的選用替代方案。它會呼叫一個專用的非正式環境 Runtime，等 CloudWatch 的 span 完成，再用內建 evaluator 打分數。這些 evaluator 需要 prompt、response 跟 tool 的內容，所以 Runtime 擁有者必須核准並啟用內容擷取。Evaluation 跟一般的 ChatGPT request 是分開跑的。


```python
run([NPM, "run", "eval:agent:validate"], RUNTIME_DIR)
print("Promptfoo actual-agent configuration validated.")

if os.getenv("RUN_PROMPTFOO_AGENT_EVALUATION", "0") == "1":
    evaluation_summary = run_agent_evaluation(NODE, RUNTIME_DIR)
    print(json.dumps(evaluation_summary, indent=2))
else:
    print("Skipped fresh agent runs. Set RUN_PROMPTFOO_AGENT_EVALUATION=1 before starting Jupyter.")
```

## 6. 選用：呼叫現成的 AWS Runtime

如果你走預設的本機路徑，這步可以跳過。對現成的 Runtime，這個 cell 會透過 AWS SDK 發出兩次真正的 `InvokeAgentRuntime` 呼叫：先搜尋 DAL 到 MDW 的航班，再查第一筆結果的狀態。它會驗證兩個回應，並檢查航班跟日期維持一致。這個 cell 的輸出不會顯示 trace 跟 session 識別碼。

啟動 Jupyter 前，先設 `RUN_LIVE_AWS=1`，以及 Runtime 擁有者提供的 `AWS_PROFILE`、`AGENTCORE_RUNTIME_AGENT_ARN`、`AGENTCORE_RUNTIME_REGION`。[README 的啟動指令](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#optional-notebook-and-developer-checks)會載入私有的根目錄 `.env`，並保留你的憑證流程匯出的值。設定改了之後要重啟 kernel。需要的 invoke-only 權限列在[權限矩陣](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#enterprise-least-privilege-matrix)。


```python
if os.getenv("RUN_LIVE_AWS", "0") == "1":
    if not os.getenv("AGENTCORE_RUNTIME_AGENT_ARN", "").strip():
        raise RuntimeError("Set AGENTCORE_RUNTIME_AGENT_ARN before enabling RUN_LIVE_AWS.")
    live_env = live_runtime_environment(DEMO_TRAVEL_DATE)
    # Call the built runner directly to keep unrelated .env credentials out.
    live = run([NODE, "dist/live-smoke.js"], MCP_DIR, live_env, timeout_seconds=300)
    live_result = json.loads(live.stdout.strip().splitlines()[-1])
    assert live_result["provider"] == "agentcore-runtime"
    assert live_result["executionMode"] == "deployed"
    assert live_result["action"] == "get_live_status"
    assert live_result["flight"]["flightNumber"] == "ELZ1234"
    assert live_result["flight"]["travelDate"] == DEMO_TRAVEL_DATE
    print(json.dumps(live_result, indent=2))
else:
    print("Skipped live AWS invocation. Set RUN_LIVE_AWS=1 after configuring a sandbox runtime.")
```

## 7. 透過 Secure MCP Tunnel 在 ChatGPT 測試 plugin 連線

本機檢查都通過之後，照 [README 的連線流程](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#7-connect-the-mcp-server-to-chatgpt)做。如果你選了現成的 Runtime，先完成第 6 步。

1. 在 `mcp-adapter/` 目錄跑 `npm start` 啟動私有 MCP server，它會監聽 `http://127.0.0.1:8787/mcp`。
2. 確認 Platform 管理員已建好 hosted tunnel、把它關聯到正確的 OpenAI organization 跟 ChatGPT workspace，並給你完整的 tunnel ID 跟一把有 **Tunnels Read + Use** 權限的 runtime key。然後用這個 tunnel ID 跟 loopback MCP URL 設定 OpenAI `tunnel-client` 的 profile。
3. 跑 `tunnel-client doctor --profile agentcore-cookbook --explain`，再跑 `tunnel-client run --profile agentcore-cookbook`，等 `http://127.0.0.1:8080/readyz` 就緒。
4. 先到 **Settings → Security and login** 開啟 Developer mode，再打開 [ChatGPT Plugins](https://chatgpt.com/plugins)。如果沒有這個設定或 Plugins 頁面，請 workspace 管理員檢查 workspace 政策。
5. 在 Plugins 頁面點加號，輸入給使用者看的名稱跟描述，在 **Connection** 底下選 **Tunnel**，再選擇或貼上完整的 tunnel ID。
6. 選 **No authentication**。tunnel runtime key 是用來讓 `tunnel-client` 向 tunnel 服務驗證身分的，不要貼進 plugin 表單。建立 plugin 連線，等自動 tool discovery 列出 `search_flights`、`get_upcoming_status`、`get_live_status`。
7. 在新對話的 tools 選單加入這個 plugin 連線，然後測試搜尋、即將起飛狀態、即時狀態的 prompt。
8. 確認訂票類的請求選不到任何寫入 tool。

tunnel client 是由內往外開連線。MCP server 要維持在 loopback，不要公開 8787 port，也不要加 inbound 防火牆規則。這一步只測 ChatGPT 裡的連線，不代表其他 OpenAI 產品介面也驗證過。

測試成功代表你有一個可用的私有 plugin 連線。要公開發佈之前，你的團隊還得準備公開的服務 endpoint，並處理營運跟發佈的歸屬、授權、隱私與安全審查，以及必要的送審核准。repo 的 MIT License 只涵蓋程式碼，不等於發佈核准。看[發佈需求](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/docs/tracing-and-publication.md#private-testing-is-not-public-distribution)。


## 結論

你已經看過一個航班 request 怎麼經過驗證過的 MCP 輸入、Agents SDK workflow，最後由 widget 在 ChatGPT 顯示結果。這個範例展示私有 tool server 可以使用 Bedrock 模型，同時不讓憑證進到 widget。

本機檢查不需要雲端憑證，就能驗證範例邏輯跟整合契約。選用的 live 步驟則讓你在自己的環境評估 agent 的最新回應、驗證 trace 送達，並測試私有的 ChatGPT 連線。

要改成自己的應用：

1. 把 [tools.py](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/tools.py) 裡的範例函式，換成對核准服務（例如庫存或訂單狀態 API）的唯讀呼叫。
2. 一起更新 [Python schemas](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/schemas.py)、[MCP tool 註冊](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/mcp-adapter/server.ts)、[MCP response schemas](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/mcp-adapter/schemas/flight.ts) 跟 [widget](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/mcp-adapter/public/flight-widget.html)。要維持嚴格驗證、唯讀 annotation 跟憑證隔離。
3. 在[評估 fixtures](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/runtime-agent/evals/fixtures/flight-status-results.jsonl) 加入有代表性的成功案例、格式錯誤的輸入跟不支援的 action。評估真實 agent 之前，先跑本機檢查。
4. 設定你核准的 Bedrock 模型、tunnel 跟 tracing 目的地。團隊可以讓 agent 留在本機，或提供現成的 Runtime 做託管執行。

測試完要關掉 MCP server 跟 tunnel client，看[維運說明](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/README.md#10-everyday-operation)。[架構指南](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/docs/openai-agentkit-cookbook.md)跟 [AWS IAM 指南](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/chatgpt_agents_sdk_aws_agentcore_cookbook/docs/aws-iam.md)涵蓋你自己服務的託管跟存取決策。


## 貢獻者

這份 cookbook 是 OpenAI 跟 Eliza 合作的成果。

- [Rohan Awasthi](https://www.linkedin.com/in/rohan-awasthi-4a5208233/) (Eliza)
- [Chuck Hernandez](https://www.linkedin.com/in/chuck-hernandez/) (Eliza)
- [Syed Ahmed](https://www.linkedin.com/in/syed-a-usanaemeaapeastwest/) (OpenAI)
- [Steven McAteer](https://www.linkedin.com/in/steven-mcateer/) (Eliza)


## 重點整理

- ChatGPT 透過 MCP 呼叫 tool，adapter 在輸入跟輸出兩端都做 schema 驗證，結果放在 `structuredContent`，由 widget 顯示。
- 用 Secure MCP Tunnel 時，`tunnel-client` 是由內往外連，MCP server 留在 loopback，不用公開 URL 或開 inbound 規則。
- agent 只拿到當次 action 需要的那一個 tool，加上 `stop_on_first_tool`，輸出就是 tool 的原始結果，不會被模型改寫。
- Evaluation 看輸出對不對，Tracing 看執行過程，兩者要分開驗證，評估通過不代表 trace 有送達。
- 本機檢查不用憑證就能驗證邏輯跟契約，真正的 Bedrock、Runtime、tunnel 步驟才需要權限，也才會產生費用。

## 練習

1. 把 `COOKBOOK_DEMO_TRAVEL_DATE` 設成固定日期，重跑搜尋 agent 的檢查，確認兩次輸出一樣。
2. 在 `tools.py` 的範例資料裡加一個新的 `ELZ` 航班，跑本機檢查，看哪些測試或 fixtures 需要一起更新。
3. 在 evaluation fixtures 加一個不支援的 action（例如訂票），讓 `eval:run` 驗證它會被擋下，再用 `PROMPTFOO_AGENT_EVALUATION_CASE_IDS` 只跑這個案例評估真實 agent。
