---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/mcp/databricks_mcp_cookbook.ipynb
---
# 用 OpenAI Agent SDK 和 Databricks MCP Server 做供應鏈 Copilot

> 原文：[examples/mcp/databricks_mcp_cookbook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/databricks_mcp_cookbook.ipynb)

## 這篇在做什麼

用 OpenAI Agent SDK 搭配 Databricks Managed MCP，做一個能查庫存、需求預測、原料依賴和 e-mail 的供應鏈 agent。後端用 FastAPI 提供串流 `/chat`，前端是 React 聊天介面。

## 學完你會

- 設定 `~/.databrickscfg`，讓程式用 `WorkspaceClient(profile=...)` 認證，不必把 token 寫進程式碼。
- 把 Databricks 的 vector search 和 Unity Catalog function 當成 MCP tool 接進 Agent。
- 用第二個 agent 做 output guardrail，並在 OpenAI Traces 看 agent 呼叫了哪些 tool。

## 開跑前

- 需要 Databricks workspace，並啟用 Serverless compute 和 Unity Catalog。
- 需要 Databricks personal access token（PAT）、`DATABRICKS_HOST`，以及 `OPENAI_API_KEY`。
- 要用範例資料的話，需把 accelerator repo clone 到 Databricks workspace 跑過。

## 方案總覽

在供應鏈營運中，agent 可以回答直接影響服務水準和營收的問題：庫存和產能夠不夠滿足目前需求？製造延遲會發生在哪裡，又會怎麼往下游傳？調整哪些工作流程能把中斷降到最低？

![Databricks MCP UI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/databricks_mcp_ui.png)

這份 cookbook 說明怎麼用 OpenAI Agent SDK 和 Databricks Managed MCP 打造供應鏈 copilot。MCP 讓 agent 能查詢結構化和非結構化的企業資料，例如庫存、銷售、供應商 feed、當地活動等，達到即時可視性、提早發現原料短缺，並主動給建議。底下有一層 orchestration 把這些整合起來：
- 查詢結構化的庫存、需求和供應商資料
- 每個批發商的時間序列預測
- 以 graph 為基礎的原料需求和運輸最佳化
- 向量索引的 e-mail 封存，可對非結構化通訊做語意搜尋
- 營收風險計算

讀完這份指南，你會部署一個範本，能查詢分散的資料來源和預測模型、標出正在浮現的瓶頸，並建議主動的行動。它能回答這類問題：
- What products are dependent on L6HUK material?
- How much revenue is at risk if we can’t produce the forecasted amount of product autoclave_1?
- Which products have delays right now?
- Are there any delays with syringe_1? 
- What raw materials are required for syringe_1?
- Are there any shortages with one of the following raw materials: O4GRQ, Q5U3A, OAIFB or 58RJD?
- What are the delays associated with wholesaler 9?

相關人員只要送出自然語言 prompt，就能立刻拿到答案。
這份指南會一步步帶你在自己的環境實作這個方案。

## 架構

這份 cookbook 的架構是在你 Databricks 現有的分析工作負載上疊一層 OpenAI Agent。你可以把 Databricks 的元件開放成可呼叫的 Unity Catalog function。agent 用 [OpenAI Agent SDK](https://openai.github.io/openai-agents-python/) 實作，並連到 [Databricks Managed MCP servers](https://docs.databricks.com/aws/en/generative-ai/agent-framework/mcp)。

結果是一個近乎即時的單一對話介面，提供細粒度的預測、動態的庫存建議，以及整條供應鏈的資料導向決策。這個架構讓 agent 層能運用你現有的企業資料（結構化和非結構化）、傳統 ML 模型和 graph 分析能力。

![Databricks MCP Architecture](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/databricks_mcp_architecture.png)

## 設定 Databricks 認證

你可以在 `~/.databrickscfg` 加一個 profile 來設定 Databricks 認證。[Databricks configuration profile](https://docs.databricks.com/aws/en/dev-tools/auth/config-profiles) 包含 Databricks 認證所需的設定和資訊。

程式裡的 `WorkspaceClient(profile=...)` 會讀到這個 profile，告訴 SDK 要載入哪一組存好的憑證，所以你的程式碼不需要嵌入 token。另一個做法是建立 `DATABRICKS_HOST` 和 `DATABRICKS_TOKEN` 之類的環境變數，但建議用 `~/.databrickscfg`。

到 Settings → Developer → Access tokens → Generate new token 產生 workspace 的[personal access token (PAT)](https://docs.databricks.com/aws/en/dev-tools/auth/pat#databricks-personal-access-tokens-for-workspace-users)，再記到 `~/.databrickscfg`。

要建立這個 Databricks configuration profile 檔，可以執行 [Databricks CLI](https://docs.databricks.com/aws/en/dev-tools/cli/) 的 databricks configure 指令，或照下面步驟：
- 如果沒有 `~/.databrickscfg`，先建立：touch `~/.databrickscfg`
- 打開檔案：`nano ~/.databrickscfg`
- 加入一段 profile，寫上 workspace URL 和 personal access token (PAT)（之後隨時可以再加其他 profile）：


```bash
[DEFAULT]
host  = https://dbc-a1b2345c-d6e7.cloud.databricks.com # add your workspace URL here
token = dapi123...    # add your PAT here
```


接著可以用 Databricks CLI 或 SDK 跑 `databricks clusters list` 當 sanity check。如果沒要求輸入憑證就回傳資料，代表 host 正確、token 有效。

前提是 Databricks workspace 要啟用 Serverless compute 和 Unity Catalog。

## （選用）設定 Databricks 供應鏈資料

這份 cookbook 可以用你自己的 Databricks 供應鏈資料集和分析工作負載。

你也可以用 Databricks Supply Chain Optimization Solution Accelerator 的客製版本加快設定。做法是把這個 GitHub [repository](https://github.com/lara-openai/databricks-supply-chain) clone 到你的 Databricks workspace，照 README [檔案](https://github.com/lara-openai/databricks-supply-chain/blob/main/README.md)的說明做。跑完後，Agent 之後要透過 MCP 存取的所有資產都會建好，從原始的企業資料表、非結構化 e-mail，到傳統 ML 模型和 graph 工作負載。

如果你要用自己的資料集和模型，請依 accelerator 的做法，把相關元件包成 Unity Catalog function，並定義 Vector Search index。你也可以開放 Genie Spaces。

範例資料模擬一個真實的製藥網路：三間工廠生產 30 種產品，送到五個配送中心，每個配送中心服務 30 到 60 個批發商。repo 內含每個產品與批發商組合的時間序列需求、配送中心到批發商的對應、工廠到配送中心的成本矩陣、工廠產出上限，以及標記出貨延遲的 e-mail 封存。

![Pharma Network](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pharma_network.png)

要回答供應鏈營運的問題，得建模上游瓶頸如何在生產、物流和出貨之間層層擴散，相關人員才能縮短 lead time、避免庫存過多並控制成本。這些 notebook 把原始資料轉成受治理、可呼叫的產物：
- 需求預測與彙總（[notebook 2](https://github.com/lara-openai/databricks-supply-chain/blob/main/02_Fine_Grained_Demand_Forecasting.py)）：用 Holt-Winters 季節性模型（或任何你偏好的時間序列方法），對每個批發商和配送中心產生未來一週的 SKU 需求。它用 Pandas UDF 發揮 Spark 的平行化能力來處理大規模預測（把你的單機資料科學程式碼分散到多個節點）。預測再彙總成每個產品的配送中心層級總量，輸出是 product_demand_forecasted 這張表。
- 原料規劃（[notebook 3](https://github.com/lara-openai/databricks-supply-chain/blob/main/03_Derive_Raw_Material_Demand.py)）：用 graph 處理建出產品到原料的對應，沿 bill-of-materials 階層往上推需求，大規模算出零組件需求。我們把 bill-of-materials 轉成 graph，讓產品預測能換算成精確的原料需求，產出 raw_material_demand 和 raw_material_supply 兩張表。
- 運輸最佳化（[notebook 4](https://github.com/lara-openai/databricks-supply-chain/blob/main/04_Optimize_Transportation.py)）：在產能和需求限制下，把工廠到配送中心的運輸成本降到最低，同樣用 Pandas UDF，建議結果輸出到 shipment_recommendations。
- 語意 e-mail 搜尋（[notebook 6](https://github.com/lara-openai/databricks-supply-chain/blob/main/06_Vector_Search.py)）：用 OpenAI embedding model 把供應鏈經理的 e-mail 嵌入 vector index，讓語意查詢能找出延遲和風險訊號。

每個洞察都在 [notebook 5](https://github.com/lara-openai/databricks-supply-chain/blob/main/05_Data_Analysis_%26_Functions.py) 和 [notebook 7](https://github.com/lara-openai/databricks-supply-chain/blob/main/07_More_Functions.py) 包成 Unity Catalog (UC) function，例如 product_from_raw、raw_from_product、revenue_risk、lookup_product_demand、query_unstructured_emails。因為 UC 同時治理資料表、模型和 vector index，Agent 可以在執行時自己決定要做預測、追 BOM 依賴、評估營收影響、查歷史，還是搜尋 e-mail，而且一律在呼叫者的資料存取權限內。

最後得到一條端到端的 pipeline：預測需求、找出原料缺口、最佳化物流、浮現隱藏風險，讓分析師可以臨時提問並看到延遲警示。

所有 notebook 都跑完後（執行 notebook 1 就會全部跑完），Databricks 環境就緒，可以開始建 Agent 並連到 Databricks。

## 連接 Databricks MCP servers

目前 [MCP spec](https://openai.github.io/openai-agents-python/mcp/) 依傳輸機制定義三種 server：
- stdio server 以你應用程式的 subprocess 執行，可以想成在「本機」跑。
- HTTP over SSE server 在遠端執行，透過 URL 連線。
- Streamable HTTP server 在遠端執行，使用 MCP spec 定義的 Streamable HTTP transport。

[Databricks 代管的 MCP endpoint](https://docs.databricks.com/aws/en/generative-ai/agent-framework/mcp)（vector-search、Unity Catalog function、Genie）都在標準 HTTPS URL 後面，實作的是 MCP spec 定義的 Streamable HTTP transport。要確認 workspace 已啟用 serverless，才能連到 Databricks managed MCP。

## 把 Databricks MCP servers 整合進 OpenAI Agent

OpenAI Agent 的程式碼在[這裡](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/README.md)。先安裝需要的套件：

```python
pip install -r requirements.txt
```

你需要 OpenAI API key 才能安全地存取 API。如果你剛接觸 OpenAI API，可以[註冊帳號](https://platform.openai.com/signup)，照[這些步驟](https://platform.openai.com/docs/libraries?project_id=proj_2NqyDkmG63zyr3TzOh64F2ac#create-and-export-an-api-key)建立 key 並存放在安全的地方。

這份 cookbook 示範用 FastAPI 提供這個 Agent，再透過 React UI 聊天。不過 `main.py` 本身就是獨立的 REPL，所以裝好套件並設好必要的憑證（包含上面說的 Databricks host 和 personal access token）後，只要一行指令就能直接在命令列跑 Agent：

```python
python main.py
```
[main.py](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/main.py) 負責 agent 邏輯的編排，用 OpenAI Agent SDK，並把 Databricks MCP 的 vector-search endpoint 和 Unity Catalog function 開放成可呼叫的 tool。它先讀環境變數，取得目標 catalog、schema 和 Unity Catalog (UC) function 路徑，然後提供兩個 tool：vector_search 查詢 Databricks Vector Search index，uc_function 則透過 MCP 執行 Unity Catalog function。兩個 tool 都用 httpx 發出帶認證的 POST request，回傳 Databricks REST API 的原始 JSON。兩個 helper 都透過 _databricks_ctx() 這個 utility（由 DatabricksOAuthClientProvider 支撐）取得 workspace host 和 Personal Access Token。

在 run_agent() 裡，程式建立一個叫「Assistant」的 Agent，範圍被嚴格限定在供應鏈主題。每個回應都必須呼叫這兩個已註冊 tool 的其中一個，guardrail 會強迫 agent 拒絕物流、庫存、採購、預測以外的問題。每個使用者 prompt 都在 SDK 的 trace context 裡處理。一個簡單的 REPL 驅動互動：使用者輸入被包進 OpenTelemetry 風格的 trace，透過 Runner.run 送出，最後印出最終答案（或 guardrail 的拒絕訊息）。程式由 main() 裡的 asyncio.run 啟動，整個流程完全非同步、不會阻塞。

```python
"""
CLI assistant that uses Databricks MCP Vector Search and UC Functions via the OpenAI Agents SDK.
"""

import asyncio
import os
import httpx
from typing import Dict, Any
from agents import Agent, Runner, function_tool, gen_trace_id, trace
from agents.exceptions import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
)
from agents.model_settings import ModelSettings
from databricks_mcp import DatabricksOAuthClientProvider
from databricks.sdk import WorkspaceClient
from supply_chain_guardrails import supply_chain_guardrail

CATALOG = os.getenv("MCP_VECTOR_CATALOG", "main") # override catalog, schema, functions_path name if your data assets sit in a different location
SCHEMA = os.getenv("MCP_VECTOR_SCHEMA", "supply_chain_db")
FUNCTIONS_PATH = os.getenv("MCP_FUNCTIONS_PATH", "main/supply_chain_db")
DATABRICKS_PROFILE = os.getenv("DATABRICKS_PROFILE", "DEFAULT") # override if using a different profile name 
HTTP_TIMEOUT = 30.0  # seconds


async def _databricks_ctx():
    """Return (workspace, PAT token, base_url)."""
    ws = WorkspaceClient(profile=DATABRICKS_PROFILE)
    token = DatabricksOAuthClientProvider(ws).get_token()
    return ws, token, ws.config.host


@function_tool
async def vector_search(query: str) -> Dict[str, Any]:
    """Query Databricks MCP Vector Search index."""
    ws, token, base_url = await _databricks_ctx()
    url = f"{base_url}/api/2.0/mcp/vector-search/{CATALOG}/{SCHEMA}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(url, json={"query": query}, headers=headers)
        resp.raise_for_status()
        return resp.json()


@function_tool
async def uc_function(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a Databricks Unity Catalog function with parameters."""
    ws, token, base_url = await _databricks_ctx()
    url = f"{base_url}/api/2.0/mcp/functions/{FUNCTIONS_PATH}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"function": function_name, "params": params}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def run_agent():
    agent = Agent(
        name="Assistant",
        instructions="You are a supply-chain assistant for Databricks MCP; you must answer **only** questions that are **strictly** about supply-chain data, logistics, inventory, procurement, demand forecasting, etc; for every answer you must call one of the registered tools; if the user asks anything not related to supply chain, reply **exactly** with 'Sorry, I can only help with supply-chain questions'.",
        tools=[vector_search, uc_function],
        model_settings=ModelSettings(model="gpt-4o", tool_choice="required"),
        output_guardrails=[supply_chain_guardrail],
    )

    print("Databricks MCP assistant ready. Type a question or 'exit' to quit.")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break

        trace_id = gen_trace_id()
        with trace(workflow_name="Databricks MCP Agent", trace_id=trace_id):
            try:
                result = await Runner.run(starting_agent=agent, input=user_input)
                print("Assistant:", result.final_output)
            except InputGuardrailTripwireTriggered:
                print("Assistant: Sorry, I can only help with supply-chain questions.")
            except OutputGuardrailTripwireTriggered:
                print("Assistant: Sorry, I can only help with supply-chain questions.")


def main():
    asyncio.run(run_agent())


if __name__ == "__main__":
    main()
```

[databricks_mcp.py](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/databricks_mcp.py) 是專注在認證的抽象層：它從指定的 WorkspaceClient（ws.config.token）取得我們前面建立的 Personal Access Token，讓應用程式其他部分不用碰 Databricks 專屬的 OAuth 邏輯。因為所有 token 處理細節都限制在這個模組，日後 Databricks 的認證機制改變，只要更新這個檔案就好。


```python
"""
Databricks OAuth client provider for MCP servers.
"""

class DatabricksOAuthClientProvider:
    def __init__(self, ws):
        self.ws = ws

    def get_token(self):
        # For Databricks SDK >=0.57.0, token is available as ws.config.token
        return self.ws.config.token
```

[supply_chain_guardrails.py](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/supply_chain_guardrails.py) 實作一個輕量的 output guardrail，做法是另外啟動第二個 agent（「Supply‑chain check」）來分類候選答案。主 agent 把草稿回覆交給這個檢查者，它回傳一個帶 Boolean is_supply_chain 的 Pydantic 物件。如果這個值是 false，guardrail 就觸發 tripwire，呼叫端改用拒絕訊息。

```python
"""
Output guardrail that blocks answers not related to supply-chain topics.
"""
from __future__ import annotations

from pydantic import BaseModel
from agents import Agent, Runner, GuardrailFunctionOutput
from agents import output_guardrail
from agents.run_context import RunContextWrapper

class SupplyChainCheckOutput(BaseModel):
    reasoning: str
    is_supply_chain: bool


guardrail_agent = Agent(
    name="Supply-chain check",
    instructions=(
        "Check if the text is within the domain of supply-chain analytics and operations "
        "Return JSON strictly matching the SupplyChainCheckOutput schema"
    ),
    output_type=SupplyChainCheckOutput,
)


@output_guardrail
async def supply_chain_guardrail(
    ctx: RunContextWrapper, agent: Agent, output
) -> GuardrailFunctionOutput:
    """Output guardrail that blocks non-supply-chain answers"""
    text = output if isinstance(output, str) else getattr(output, "response", str(output))
    result = await Runner.run(guardrail_agent, text, context=ctx.context)
    return GuardrailFunctionOutput(
        output_info=result.final_output,
        tripwire_triggered=not result.final_output.is_supply_chain,
    )
```

## 用 FastAPI 提供 agent 服務

啟動後端（FastAPI），執行下面的指令：

```python
python -m uvicorn api_server:app --reload --port 8000
```

API 會在 http://localhost:8000 提供服務（FastAPI 文件在 http://localhost:8000/docs）。

[api_server.py](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/api_server.py) 是 FastAPI 後端，把你的 agent 開放成串流的 /chat API endpoint。啟動時它先設定 CORS，讓本機前端能連上，接著定義 `build_mcp_servers()`：向呼叫者的 Databricks workspace 認證，建立兩個 HTTP「server tool」（一個給 vector search，一個給 Unity Catalog function），並預先連線以降低延遲。每個進來的 POST /chat 帶一則使用者訊息。handler 會建立一個新的 Agent，它的 mcp_servers 清單由這些串流 tool 組成，model 被強制每一輪都要呼叫 tool。

```python
"""
FastAPI wrapper that exposes the agent as a streaming `/chat` endpoint.
"""

import os
import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.exceptions import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
)
from agents import Agent, Runner, gen_trace_id, trace
from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams
from agents.model_settings import ModelSettings
from databricks_mcp import DatabricksOAuthClientProvider
from databricks.sdk import WorkspaceClient

from supply_chain_guardrails import supply_chain_guardrail

CATALOG = os.getenv("MCP_VECTOR_CATALOG", "main")
SCHEMA = os.getenv("MCP_VECTOR_SCHEMA", "supply_chain_db")
FUNCTIONS_PATH = os.getenv("MCP_FUNCTIONS_PATH", "main/supply_chain_db")
DATABRICKS_PROFILE = os.getenv("DATABRICKS_PROFILE", "DEFAULT")
HTTP_TIMEOUT = 30.0  # seconds

app = FastAPI()

# Allow local dev front‑end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str


async def build_mcp_servers():
    """Initialise Databricks MCP vector & UC‑function servers."""
    ws = WorkspaceClient(profile=DATABRICKS_PROFILE)
    token = DatabricksOAuthClientProvider(ws).get_token()

    base = ws.config.host
    vector_url = f"{base}/api/2.0/mcp/vector-search/{CATALOG}/{SCHEMA}"
    fn_url = f"{base}/api/2.0/mcp/functions/{FUNCTIONS_PATH}"

    async def _proxy_tool(request_json: dict, url: str):
        import httpx

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=request_json, headers=headers)
            resp.raise_for_status()
            return resp.json()

    headers = {"Authorization": f"Bearer {token}"}

    servers = [
        MCPServerStreamableHttp(
            MCPServerStreamableHttpParams(
                url=vector_url,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            ),
            name="vector_search",
            client_session_timeout_seconds=60,
        ),
        MCPServerStreamableHttp(
            MCPServerStreamableHttpParams(
                url=fn_url,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            ),
            name="uc_functions",
            client_session_timeout_seconds=60,
        ),
    ]

    # Ensure servers are initialized before use
    await asyncio.gather(*(s.connect() for s in servers))
    return servers


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        servers = await build_mcp_servers()

        agent = Agent(
            name="Assistant",
            instructions="Use the tools to answer the questions.",
            mcp_servers=servers,
            model_settings=ModelSettings(tool_choice="required"),
            output_guardrails=[supply_chain_guardrail],
        )

        trace_id = gen_trace_id()

        async def agent_stream():
            logging.info(f"[AGENT_STREAM] Input message: {req.message}")
            try:
                with trace(workflow_name="Databricks MCP Example", trace_id=trace_id):
                    result = await Runner.run(starting_agent=agent, input=req.message)
                    logging.info(f"[AGENT_STREAM] Raw agent result: {result}")
                    try:
                        logging.info(
                            f"[AGENT_STREAM] RunResult __dict__: {getattr(result, '__dict__', str(result))}"
                        )
                        raw_responses = getattr(result, "raw_responses", None)
                        logging.info(f"[AGENT_STREAM] RunResult raw_responses: {raw_responses}")
                    except Exception as log_exc:
                        logging.warning(f"[AGENT_STREAM] Could not log RunResult details: {log_exc}")
                    yield result.final_output
            except InputGuardrailTripwireTriggered:
                # Off-topic question denied by guardrail
                yield "Sorry, I can only help with supply-chain questions."
            except OutputGuardrailTripwireTriggered:
                # Out-of-scope answer blocked by guardrail
                yield "Sorry, I can only help with supply-chain questions."
            except Exception:
                logging.exception("[AGENT_STREAM] Exception during agent run")
                yield "[ERROR] Exception during agent run. Check backend logs for details."

        return StreamingResponse(agent_stream(), media_type="text/plain")

    except Exception:
        logging.exception("chat_endpoint failed")
        return StreamingResponse(
            (line.encode() for line in ["Internal server error 🙈"]),
            media_type="text/plain",
            status_code=500,
        )
```

endpoint 會在 agent 推理和呼叫 MCP tool 的同時，把 token 串流回瀏覽器。

## 用 React 聊天 UI 與使用者互動

在另一個 terminal 執行下面的指令，啟動前端（React UI）：

```python
cd ui
npm install
npm run dev
```

應用程式會在 http://localhost:5173 提供服務。

[/ui 資料夾](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/ui)裡的 React 聊天 UI 提供好用的網頁介面來跟後端 agent 互動。它有顯示對話記錄的元件和送出訊息的文字輸入框。

使用者送出訊息時，UI 把它送到後端的 /chat endpoint，並即時串流 agent 的回應，新內容一到就更新聊天視窗。設計重點是對話式的體驗，讓使用者方便提問並從 Databricks 驅動的 agent 拿到答案，全部在一個回應式、可互動的網頁應用裡完成。

其中 [ChatUI.jsx](https://github.com/openai/openai-cookbook/blob/main/examples/mcp/building-a-supply-chain-copilot-with-agent-sdk-and-databricks-mcp/ui/src/components/ChatUI.jsx) 這個檔案包含聊天介面的核心邏輯，包括使用者訊息怎麼送到後端，以及 agent 的串流回應怎麼即時處理和顯示。

```python
"""
Code snippet handling the token stream coming from the FastAPI /chat endpoint.
"""
const reader = response.body.getReader();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  assistantMsg.text += new TextDecoder().decode(value);
  setMessages(m => {
    const copy = [...m];
    copy[copy.length - 1] = { ...assistantMsg };
    return copy;
  });
}
```

UI 會在 agent 回應抵達時串流顯示，帶來流暢的即時聊天體驗。這也清楚展示 UI 如何從後端 agent 得到互動式、對話式的回饋。

![Databricks MCP UI](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/databricks_mcp_ui.png)

## 操作這個 app

打開 http://localhost:5173，試試下面這些 prompt：
- What products are dependent on L6HUK material?
- How much revenue is at risk if we can’t produce the forecasted amount of product autoclave_1?
- Which products have delays right now?
- Are there any delays with syringe_1? 
- What raw materials are required for syringe_1?
- Are there any shortages with one of the following raw materials: O4GRQ, Q5U3A, OAIFB or 58RJD?
- What are the delays associated with wholesaler 9?
agent 會呼叫相關的 tool，整理出有依據的答案給使用者。


## 在 OpenAI API Dashboard 追蹤 Agent 呼叫

在 OpenAI API [dashboard](https://platform.openai.com/prompts) 可以打開 Traces 檢視，看 agent 呼叫過的每個 function。下面的例子裡，agent 先呼叫 raw_from_product 取得某個產品相關的原料，再呼叫 revenue_risk 估算原料短缺的營收影響。

![Tracing Dashboard](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/tracing_dashboard_databricks_mcp.png)

## 下一步

* 可以考慮加上多輪對話能力
* 如果要改成適用你自己的 workspace，也可以加 Genie Space MCP servers

## 參考資料
- Databricks Managed MCP [文件](https://docs.databricks.com/aws/en/generative-ai/agent-framework/mcp)
- OpenAI Agent SDK [文件](https://openai.github.io/openai-agents-python/)
- OpenAI Agent Guardrails [文件](https://openai.github.io/openai-agents-python/guardrails/)
- `openai-agents-python` 範例[程式片段](https://github.com/openai/openai-agents-python/tree/main/examples/mcp/streamablehttp_example)

## 重點整理

- MCP 讓 agent 用統一方式呼叫企業資料平台的能力，這篇把 Databricks 的 vector search 和 Unity Catalog function 都包成 tool。
- 把預測、BOM 追蹤、營收風險等分析先包成受治理的 UC function，agent 就能在呼叫者權限內自己決定該用哪個。
- 認證邏輯集中在 `databricks_mcp.py` 一個模組，之後認證機制改了只動這裡。
- output guardrail 用第二個小 agent 分類答案是否屬於供應鏈，讓主 agent 守住主題範圍。
- 同一個 agent 可以用 REPL、FastAPI 串流 endpoint 加 React UI 兩種方式提供服務，並能在 Traces 看到每次 tool 呼叫。

## 練習

1. 照 `main.py` 的 REPL 方式跑 agent，問頁面上列的任一個問題，再到 OpenAI Traces 看它呼叫了哪些 tool。
2. 改 `supply_chain_guardrails.py` 裡檢查 agent 的指令，把允許的主題擴大或縮小一個範圍，再問一個邊界問題，看 guardrail 會不會觸發。
3. 在 `api_server.py` 的 `build_mcp_servers()` 多加一個 MCP server（例如 Genie Space），並確認 agent 能呼叫它。
