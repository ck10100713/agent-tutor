---
translated: true
source: examples/partners/schemaflow_design_guide/schemaflow_cookbook.ipynb
---

# SchemaFlow：用 agent 做資料庫變更影響分析、SQL 產生與 eval guardrail

> 原文：[examples/partners/schemaflow_design_guide/schemaflow_cookbook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/schemaflow_design_guide/schemaflow_cookbook.ipynb)

用 OpenAI Agents SDK 建一條分階段的 SchemaFlow pipeline：解析資料庫變更需求、分析影響、規劃上線步驟、產生 SQL、加 guardrail、存 artifact，還可以選擇接 File Search 做 grounding，最後用 Promptfoo 跑 eval。

## 這篇在做什麼

把一段自然語言的資料庫變更需求（例如「幫 ODS 的客戶表加一個 loyalty tier 欄位並回填」），丟進一條由多個 agent 組成的流程。流程會一步步產出結構化 JSON、影響分析、上線計畫和 SQL 草稿，再用確定性的檢查把關。最後整包結果存成 JSON，還能用 Promptfoo 自動評測。

## 學完你會

- 用 Agents SDK 把一個大任務拆成 parse、impact、plan、SQL 四個各管一件事的 agent，並用 Pydantic 定義每個階段的輸出格式。
- 在階段之間加確定性的 guardrail（欄位型別、nullable、必要 SQL 關鍵字），在壞資料流到下游之前就擋掉。
- 把整個流程存成可稽核的 artifact，並產生 Promptfoo 的 provider、assertion 和 config 來重複跑 eval。

## 開跑前

- 需要 `OPENAI_API_KEY`，會呼叫付費的模型。
- 想用 PDF 做 File Search grounding，需要自備一份 PDF（會建 OpenAI vector store）。
- 跑 Promptfoo eval 需要 Node.js 和 npm。
- 最後的 Neo4j 儀表板是選配，需要一個跑著的 Neo4j。

---

這篇 cookbook 帶你用 OpenAI Agents SDK 走完一條端到端的 **AI 輔助資料庫變更流程**。

它示範怎麼用 OpenAI 的工具生態，去編排複雜、重資料的流程，適用於現代企業的基礎架構。目前的範例是零售業的 schema 變更與影響分析，但底層的架構模式跟領域無關，可以延伸。同樣的流程設計也能套用到製造、製藥、醫療、物流、金融、供應鏈等產業，只要有結構化資料流程、營運推理、retrieval 增強分析和自動驗證的需求都適用。

範例用的是零售的 loyalty tier 變更，不過同樣的模式可以用在很多資料庫變更需求上，只要團隊需要可追溯的影響分析和可審查的實作產出。

流程從一段自然語言的資料庫變更需求開始，先轉成結構化 JSON，再選擇性地用 PDF 的 File Search 為影響分析提供依據，接著產生安全的上線計畫，跨資料平台各層起草 SQL，用確定性的 guardrail 驗證輸出，存成可重用的 artifact，最後可選擇用 Promptfoo 評測整個流程。

這份 notebook 刻意做成自給自足：所有核心流程邏輯、prompt、guardrail、artifact 產生和 eval 的 runtime 檔案，都是由 notebook 的 cell 建出來的。

<a id="overview"></a>

---

## 總覽

Schema 變更看起來很單純。像「加一個 nullable 欄位並回填」這種需求，可能牽動 landing table、staging model、維度表、mart、報表邏輯、lineage 假設、驗證檢查、rollback 程序和上線順序。

範例用零售客戶資料，因為依賴關係容易看懂，但很多分析和平台團隊都會遇到同樣的交接問題。

這份 cookbook 示範一個實用的模式：把 agent 當成資料庫工程的**變更分析與實作助理**。它不是叫一個模型直接吐出最終 SQL，而是把任務拆成明確的階段：

1. 把自然語言需求解析成結構化 JSON。
2. 分析受影響的物件和營運風險。
3. 建立包含 precheck、postcheck 和 rollback 指引的上線計畫。
4. 跨平台各層產生 SQL。
5. 跑確定性的 sanity check。
6. 存成機器可讀的 artifact。
7. 選擇性地對目前的流程跑 Promptfoo eval。

最後的產出不只是一份 SQL 腳本，而是一包可稽核的內容：解析後的變更需求、影響分析、計畫、SQL、驗證結果、選配的 RAG 證據摘要，以及 eval 輸出。

<a id="why-this-matters"></a>

---

## 為什麼重要

資料庫變更需求通常要經過好幾次交接：產品負責人描述需求，資料工程師詮釋，平台團隊評估風險，analytics engineer 把欄位往下游推，reviewer 檢查是否安全。每一次交接都可能掉資訊。

SchemaFlow 的做法是把自由格式的變更需求，變成結構化、可檢視的流程。

這很重要，因為資料庫變更會藏著不少失敗模式：

- 加在 ODS 的欄位，可能沒有傳到 staging、core 或 mart。
- nullable 欄位可能不小心被產成 `NOT NULL`。
- 需求明明要回填歷史資料，backfill 邏輯卻被漏掉。
- 需要的 index 被忽略。
- 沒查參考文件的話，下游報表的依賴關係可能根本不知道。
- 產出的 SQL 看起來合理，但過不了基本的一致性檢查。

這份 cookbook 展示怎麼降低這些風險：分階段的 agent 推理、型別化輸出、選配的 retrieval 上下文、確定性的 guardrail、存下來的 artifact，以及可重複跑的 eval。

<a id="key-benefits"></a>

---

## 主要好處

- **結構化詮釋**：把自然語言的資料庫需求轉成標準化的 `change_json` 契約。
- **職責分離**：parse、影響分析、上線規劃、SQL 產生各用一個專職 agent。
- **選配的 RAG grounding**：讓 impact 分析 agent 對上傳的 PDF（例如 IFD、schema 規格或 lineage 文件）使用 File Search。
- **型別化的階段輸出**：parse、impact、plan 三個階段用 Pydantic model 和 Agents SDK 的 output schema。
- **Guardrail 優先**：階段之間加確定性檢查，明顯的失敗在下游吃到壞狀態之前就被抓到。
- **可追溯**：agent 執行、guardrail、artifact 產生和 eval 執行都會產出 OpenAI Agents SDK 的 trace 和 span。
- **可攜的 artifact**：最終的流程包以 JSON 存在 `artifacts/notebook_runs/` 下。
- **為 eval 而設計**：從 notebook 的即時狀態產生 Promptfoo 的 provider、assertion、config 和結果檔。
- **不碰資料庫**：只產生 SQL 草稿和驗證輸出，不會對真實資料庫執行。

<a id="what-youll-build"></a>

---

## 你會做出什麼

跑完這份 notebook，你會有一條可運作的 SchemaFlow pipeline，產出：

- 解析後的資料庫變更需求：
  - title
  - domain
  - target schema
  - target table
  - 標準化後的 operations
  - notes

- 影響分析報告：
  - 受影響的 table、column、index、view 或關聯
  - 風險
  - 假設
  - 選配的 File Search 證據摘要

- 上線計畫：
  - 實作步驟
  - prechecks
  - postchecks
  - rollback 動作

- 一份 SQL 草稿，包含四個必要區段：
  - `LANDING (ODS)`
  - `STAGING (STG)`
  - `CORE (DIM/FACT/VIEW)`
  - `MARTS (SERVING)`

- 驗證結果：
  - 預期 table 檢查
  - 預期 column 檢查
  - 必要關鍵字檢查，例如 `ALTER TABLE`、`UPDATE` 或 `CREATE INDEX`

- 存下來的 JSON artifact：
  - 變更需求
  - 影響分析
  - 計畫
  - SQL
  - 驗證
  - 選配的 RAG metadata

- Promptfoo eval 工具組：
  - Python provider
  - Python assertion 檔
  - 產生出來的 Promptfoo config
  - parse-only eval case
  - full-flow eval case
  - 帶時間戳的 JSON 和 HTML eval 報告
  

<a id="introduction-use-case-and-solution"></a>

---

## 簡介：使用情境與解法

這份 cookbook 聚焦在企業資料工程常見的情境：利害關係人用自然語言提出 schema 變更，資料團隊要把它變成可實作的計畫。

這裡用零售領域只是為了讓流程具體。同樣的分階段做法，可以調整到其他來源系統、資料產品和審查流程。

這份 notebook 的預設需求是：

```text
Add LOYALTY_TIER VARCHAR(20) to ODS.ODS_CUSTOMER_PROFILE as nullable.
Backfill from CORE.DIM_CUSTOMER on CUSTOMER_ID where IS_CURRENT=true.
Add a non-unique index on (CUSTOMER_ID, LOYALTY_TIER).
```

人類資料工程師在寫 production SQL 之前，通常得先回答幾個問題：

- 要改哪個 schema 的哪張表？
- 要加的欄位、型別和 nullability 到底是什麼？
- 需不需要回填歷史資料？
- 需求有沒有暗示要建 index？
- 哪些下游層需要把這個欄位傳下去？
- reviewer 該注意哪些風險？
- 上線前後要跑哪些檢查？
- 合理的 rollback 步驟是什麼？
- 產出的 SQL 有沒有包含該有的元素？

SchemaFlow 把這些做成分階段的 agent 流程。每個階段產出型別化的中間結果給下一階段用，再由確定性的檢查驗證，之後 notebook 才存最終的流程包，並選擇性地跑 eval。

<a id="workflow-overview"></a>

---

## 流程總覽

大方向上，SchemaFlow 照這個順序跑：

![schemaflow_seq_diagram.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/schemaflow_seq_diagram.png)

這份 notebook 的安排是讓你先跑核心流程，再決定要不要跑選配的 Promptfoo 評測。


<a id="table-of-contents"></a>

---

## 目錄

### 概念說明

- [Overview](#overview)
- [Why This Matters](#why-this-matters)
- [Key Benefits](#key-benefits)
- [What You'll Build](#what-youll-build)
- [Introduction: Use Case and Solution](#introduction-use-case-and-solution)
- [Workflow Overview](#workflow-overview)
- [Architecture - Design Patterns](#architecture-design-patterns)
- [System Design](#system-design)
- [Execution Workflow](#execution-workflow)

### Notebook 實作

1. [Environment Setup](#environment-setup)
2. [Input](#input)
3. [Optional PDF RAG Context](#optional-pdf-rag-context)
4. [Stages 1-2: Parse Change Request + Impact Analysis](#stages-1-2-parse-change-request--impact-analysis)
   - [Impact Dashboard Preview](#impact-dashboard-preview)
   - [Stages 1-2 Output Guardrails](#stages-1-2-output-guardrails)
5. [Stages 3-4: Execution Plan + SQL Generation](#stages-3-4-execution-plan--sql-generation)
   - [Stages 3-4 Output Guardrails](#stages-3-4-output-guardrails)
6. [Stage 5: Lightweight SQL Sanity Checks](#stage-5-lightweight-sql-sanity-checks)
7. [Final Bundle](#final-bundle)
8. [Save Artifact](#save-artifact)
   - [Post-Artifact Generation Sanity Check](#post-artifact-generation-sanity-check)
9. [Optional Cleanup](#optional-cleanup)
   - [Pre-Promptfoo Checks / Guardrails](#pre-promptfoo-checks--guardrails)
10. [Evaluate the Flow with Promptfoo](#evaluate-the-flow-with-promptfoo)
    - [Promptfoo Runtime Directory Setup](#promptfoo-runtime-directory-setup)
    - [Node.js and npm Runtime Check](#nodejs-and-npm-runtime-check)
    - [Publish SchemaFlow Core Runtime](#publish-schemaflow-core-runtime)
    - [Promptfoo Provider Runtime](#promptfoo-provider-runtime)
    - [Promptfoo Assertion Runtime](#promptfoo-assertion-runtime)
    - [Build Promptfoo Test Cases and Config](#build-promptfoo-test-cases-and-config)
    - [Run Promptfoo Eval](#run-promptfoo-eval)
    - [Review Latest Promptfoo Results](#review-latest-promptfoo-results)

### 參考

- [Notes, Assumptions, and Extension Points](#notes-assumptions-and-extension-points)

<a id="architecture-design-patterns"></a>

---

## 架構：設計模式

SchemaFlow 用的是分階段、以契約驅動的 agent 架構。目標是不要把模型當成單一的黑盒 SQL 產生器。每個階段只負責一件事，產出的東西可以檢視、驗證、追蹤和重用。

### 1. Agent 專職化

每個 agent 只做一件主要的事：

| Agent | 職責 | 主要輸出 |
|---|---|---|
| Parse Agent | 從自然語言需求抽出結構化欄位 | `change_json` |
| Impact Agent | 找出受影響的物件、假設和風險 | `impact_json` |
| Plan Agent | 把變更和影響轉成上線步驟 | `plan_json` |
| SQL Agent | 跨資料平台各層起草 SQL | `sql_text` |

這樣拆比較好 debug。如果 SQL 少了一個欄位，你可以回頭看問題是從 parse、impact、plan 還是 SQL 產生哪一步開始的。

### 2. 型別化的輸出契約

這份 notebook 為結構化的階段定義了 Pydantic model：

- `ChangeRequestModel`
- `ImpactModel`
- `PlanModel`

這些 model 用 `AgentOutputSchema` 包起來，讓 Agents SDK 知道預期的輸出形狀。模型呼叫之後，流程還會做輸出正規化，確保下游階段執行前，該有的 key 都在。
### 3. 用 Retrieval 增強的影響分析

PDF RAG 這段是選配的。當你設定了 `PDF_PATH`，notebook 會：

1. 建一個 OpenAI vector store。
2. 上傳 PDF。
3. 讓 OpenAI 解析、切 chunk、做 embedding 並建索引。
4. 給 Impact Agent 一個 `FileSearchTool`。
5. 記下 File Search 回傳結果的摘要。

當變更需求需要以 IFD、schema 文件、lineage 檔、data contract 或架構參考資料為依據時，這個功能就很有用。

### 4. 階段之間的 Guardrail 關卡

notebook 在幾個主要階段之後加了確定性的檢查：

- Stages 1-2 的 guardrail 驗證 parse 和 impact 的輸出。
- Stages 3-4 的 guardrail 驗證計畫完整度、資料型別傳遞和 nullability 處理。
- Stage 5 的 SQL 檢查驗證預期的 table、column 和 SQL 關鍵字是否存在。
- Post-artifact 檢查確認存下來的 JSON artifact 存在而且讀得回來。
- Pre-Promptfoo 檢查確認 notebook 的狀態已經準備好跑 eval。

這些檢查不能取代人工 review，但可以及早抓到常見的無聲失敗。

### 5. 以 Artifact 為中心的執行

最終的 bundle 是整個流程的主要 artifact，記錄了 review 或 debug 這次執行所需的狀態：

```text
bundle = {
  "summary": ...,
  "rag": ...,
  "change_json": ...,
  "impact_json": ...,
  "plan": ...,
  "sql": ...,
  "validation": ...
}
```

notebook 會把這個 bundle 存在 `artifacts/notebook_runs/` 底下。

### 6. 從 Notebook 狀態產生 Eval Runtime

Promptfoo 在另一個 process 執行，沒辦法直接讀 notebook kernel 裡的變數。為了解決這點，第 10 節會從目前的 notebook 狀態寫出一個小的可重用 Python module 和 Promptfoo 的 runtime 檔案。

這樣 prompt 的修改、`CHANGE_TEXT` 的修改和模型設定的變更，在你重新產生 eval 檔案後都會反映出來。

<a id="system-design"></a>

---

## 系統設計

### 元件架構

![schemaflow_system_design.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/schemaflow_system_design.png)

### 主要的 Runtime 物件

| 物件 | 建立位置 | 用途 |
|---|---|---|
| `CHANGE_TEXT` | Input 區段 | 自然語言的資料庫變更需求 |
| `change_json` | Stage 1 | 對需求的結構化詮釋 |
| `rag_vector_store_id` | 選配的 PDF RAG 區段 | 上傳 PDF 上下文用的託管 vector store ID |
| `rag_file_search_results` | Stage 2 | 回傳給 Impact Agent 的 File Search 結果摘要 |
| `impact_json` | Stage 2 | 受影響的物件、風險和假設 |
| `plan_json` | Stage 3 | 上線計畫、檢查和 rollback 指引 |
| `sql_text` | Stage 4 | SQL 草稿 |
| `validation` | Stage 5 | 確定性的 SQL sanity check 結果 |
| `bundle` | Final Bundle 區段 | 彙整後的流程輸出 |
| `out_path` | Save Artifact 區段 | 存下來的 JSON artifact 路徑 |
| `promptfoo_config` | Promptfoo 區段 | 產生出來的 eval 設定 |

### 重要的邊界

SchemaFlow 產生的是實作草稿。它**不會**對資料庫執行 SQL、套用 migration、開 pull request，或修改 production 系統。

<a id="execution-workflow"></a>

---

## 執行流程

照順序跑 notebook。

### 核心流程

1. **Environment Setup**
   - import 相依套件。
   - 確認 OpenAI Agents SDK 的版本。
   - 讀取 `OPENAI_API_KEY`。
   - 設定 tracing 和模型選擇。

2. **Input**
   - 定義 `CHANGE_TEXT`。
   - 這是核心流程唯一需要的業務輸入。

3. **選配的 PDF RAG 上下文**
   - 保持 `PDF_PATH = None` 就不用 retrieval。
   - 把 `PDF_PATH` 設成本機 PDF，就會為影響分析啟用 File Search 上下文。

4. **Stages 1-2**
   - 解析變更需求。
   - 分析影響。
   - 影響分析時可選擇使用 File Search。

5. **Stages 1-2 Guardrails**
   - 確認 parse 輸出格式正確。
   - 確認 impact 輸出包含 target。
   - 確認受影響的物件都有必要欄位。

6. **Stages 3-4**
   - 產生執行計畫。
   - 跨 landing、staging、core、mart 各層產生 SQL。

7. **Stages 3-4 Guardrails**
   - 確認計畫各區段都有內容。
   - 確認資料型別有被傳遞。
   - 確認 nullability 的行為符合需求。

8. **Stage 5 SQL Sanity Checks**
   - 檢查 SQL 是否為空。
   - 檢查預期的 target table 和 column。
   - 檢查需求暗示的必要 SQL 動作。

9. **Final Bundle 與 Artifact**
   - 組出完整的輸出 bundle。
   - 存成 JSON。
   - 確認 artifact 讀寫來回沒問題。

### 選配的 Eval 流程

10. **Pre-Promptfoo Checks**
    - 確認 notebook 狀態已準備好跑 eval。

11. **產生 Promptfoo Runtime**
    - 建立可重用的 SchemaFlow core module。
    - 寫 Promptfoo provider。
    - 寫 Promptfoo assertion 檔。
    - 產生 Promptfoo 測試案例和 config。

12. **執行 Promptfoo Eval**
    - 跑 parse-only 和 full-flow 的 eval。
    - 存帶時間戳的 JSON 和 HTML 報告。
    - 更新 `schemaflow_cookbook_eval_latest.*` 這些別名檔。

<a id="environment-setup"></a>

---

## 1) 環境設定

這一節準備 SchemaFlow 流程的 runtime。

setup cell 做了這些事：

- import 整份 notebook 會用到的標準 Python 工具。
- import OpenAI client。
- import OpenAI Agents SDK 的基本元件：
  - `Agent`
  - `Runner`
  - `RunConfig`
  - `AgentOutputSchema`
  - `FileSearchTool`
  - tracing 和 span 的 helper
- 確認安裝的 `openai-agents` 套件符合最低版本要求。
- 從環境變數讀 `OPENAI_API_KEY`，沒有就跳出提示請你輸入。
- 用 `OPENAI_MODEL` 設定模型，預設是 `gpt-5.5`。
- 建立一個 trace group ID，讓相關的 agent 執行和 guardrail span 可以歸成一組。

這個 demo 刻意開啟敏感 trace payload，讓 prompt、輸出、eval bundle 和 tool 資料都看得到。用在 production 時，處理私有資料之前請先檢查這個設定。

```python
%pip install --quiet -U "openai" "openai-agents>=0.17.0"
```

```python
import os
import json
import re
import uuid
from datetime import datetime, timezone
from getpass import getpass
from importlib.metadata import PackageNotFoundError, version

try:
    from openai import OpenAI
except Exception as e:
    raise RuntimeError("Install dependency first: pip install -U openai") from e

MIN_AGENTS_SDK_VERSION = "0.17.0"
try:
    from agents import (
        Agent,
        AgentOutputSchema,
        FileSearchTool,
        Runner,
        RunConfig,
        custom_span,
        flush_traces,
        function_span,
        guardrail_span,
        trace,
    )
except Exception as e:
    raise RuntimeError(
        'Install or upgrade the OpenAI Agents SDK first: pip install -U "openai-agents>=0.17.0"'
    ) from e


def _version_tuple(value):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


try:
    AGENTS_SDK_VERSION = version("openai-agents")
except PackageNotFoundError as e:
    raise RuntimeError('Install the OpenAI Agents SDK first: pip install -U "openai-agents>=0.17.0"') from e

if _version_tuple(AGENTS_SDK_VERSION) < _version_tuple(MIN_AGENTS_SDK_VERSION):
    raise RuntimeError(
        f'OpenAI Agents SDK {MIN_AGENTS_SDK_VERSION}+ is required; found {AGENTS_SDK_VERSION}. '
        'Upgrade with: pip install -U "openai-agents>=0.17.0"'
    )

def _clean_openai_api_key(value):
    key = (value or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required.")
    return key


if not os.getenv("OPENAI_API_KEY", "").strip():
    os.environ["OPENAI_API_KEY"] = getpass("Enter your OpenAI API key: ")
os.environ["OPENAI_API_KEY"] = _clean_openai_api_key(os.getenv("OPENAI_API_KEY"))
OPENAI_ORG_ID = os.getenv("OPENAI_ORG_ID", "").strip()
if OPENAI_ORG_ID:
    os.environ["OPENAI_ORG_ID"] = OPENAI_ORG_ID

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")
TRACE_INCLUDE_SENSITIVE_DATA = os.getenv("OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA", "false").lower() in {"1", "true", "yes", "on"}
os.environ["OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"] = "true" if TRACE_INCLUDE_SENSITIVE_DATA else "false"
SCHEMAFLOW_TRACE_GROUP_ID = os.getenv("SCHEMAFLOW_TRACE_GROUP_ID") or (
    "schemaflow-cookbook-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
)
os.environ["SCHEMAFLOW_TRACE_GROUP_ID"] = SCHEMAFLOW_TRACE_GROUP_ID
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
print("Using model:", MODEL)
print("OpenAI Agents SDK:", AGENTS_SDK_VERSION)
print("OpenAI organization:", os.getenv("OPENAI_ORG_ID") or "(default for API key)")
print("Trace group:", SCHEMAFLOW_TRACE_GROUP_ID)
print("Trace payloads include prompts/outputs:", TRACE_INCLUDE_SENSITIVE_DATA)
```

````python
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel, ConfigDict, Field


class SchemaFlowBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class OperationModel(SchemaFlowBaseModel):
    op: str
    details: dict = Field(default_factory=dict)


class ChangeRequestModel(SchemaFlowBaseModel):
    title: str | None = None
    domain: str | None = None
    target_schema: str | None = None
    target_table: str | None = None
    operations: list[OperationModel] = Field(default_factory=list)
    notes: list = Field(default_factory=list)


class ImpactObjectModel(SchemaFlowBaseModel):
    type: str
    name: str
    reason: str
    source: str


class ImpactModel(SchemaFlowBaseModel):
    impacted_objects: list[ImpactObjectModel] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class PlanStepModel(SchemaFlowBaseModel):
    id: str
    description: str


class PlanModel(SchemaFlowBaseModel):
    plan_steps: list[PlanStepModel] = Field(default_factory=list)
    prechecks: list[str] = Field(default_factory=list)
    postchecks: list[str] = Field(default_factory=list)
    rollback: list[str] = Field(default_factory=list)


CHANGE_OUTPUT_SCHEMA = AgentOutputSchema(ChangeRequestModel, strict_json_schema=False)
IMPACT_OUTPUT_SCHEMA = AgentOutputSchema(ImpactModel, strict_json_schema=False)
PLAN_OUTPUT_SCHEMA = AgentOutputSchema(PlanModel, strict_json_schema=False)


def _parse_json_text(text: str):
    text = (text or "{}").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _model_dump(value):
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, type):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except TypeError:
            pass
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        try:
            return {k: v for k, v in vars(value).items() if not k.startswith("_")}
        except TypeError:
            pass
    return value


def _agent_output_to_json(value):
    value = _model_dump(value)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return _parse_json_text(value)
    return json.loads(json.dumps(value, default=str))


def _agent_output_to_text(value):
    value = _model_dump(value)
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _trace_metadata(metadata: dict | None = None):
    cleaned = {}
    for key, value in (metadata or {}).items():
        if value is None:
            cleaned[str(key)] = ""
        elif isinstance(value, bool):
            cleaned[str(key)] = "true" if value else "false"
        elif isinstance(value, (dict, list, tuple, set)):
            cleaned[str(key)] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            cleaned[str(key)] = str(value)
    return cleaned


def _schemaflow_run_config(workflow_name: str, metadata: dict | None = None):
    return RunConfig(
        workflow_name=workflow_name,
        group_id=SCHEMAFLOW_TRACE_GROUP_ID,
        trace_include_sensitive_data=TRACE_INCLUDE_SENSITIVE_DATA,
        trace_metadata=_trace_metadata({"notebook": "schemaflow_cookbook", **(metadata or {})}),
    )


def _runner_run_sync(agent, prompt: str, *, workflow_name: str, metadata: dict | None = None, max_turns: int = 4):
    kwargs = {"run_config": _schemaflow_run_config(workflow_name, metadata), "max_turns": max_turns}
    try:
        return Runner.run_sync(agent, prompt, **kwargs)
    except RuntimeError as exc:
        if "event loop" not in str(exc).lower():
            raise
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: Runner.run_sync(agent, prompt, **kwargs)).result()


def run_schemaflow_json_agent(*, name, instructions, prompt, output_schema, model=MODEL, tools=None, workflow_name=None, metadata=None):
    agent = Agent(name=name, instructions=instructions, model=model, output_type=output_schema, tools=tools or [])
    result = _runner_run_sync(agent, prompt, workflow_name=workflow_name or name, metadata={"agent": name, **(metadata or {})})
    return _agent_output_to_json(result.final_output), result


def run_schemaflow_text_agent(*, name, instructions, prompt, model=MODEL, tools=None, workflow_name=None, metadata=None):
    agent = Agent(name=name, instructions=instructions, model=model, tools=tools or [])
    result = _runner_run_sync(agent, prompt, workflow_name=workflow_name or name, metadata={"agent": name, **(metadata or {})})
    return _agent_output_to_text(result.final_output), result


def _collect_file_search_results(value):
    results = []
    seen = set()

    def visit(node):
        if node is None or isinstance(node, (str, int, float, bool, bytes)):
            return
        if isinstance(node, type) or callable(node):
            return
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)

        node = _model_dump(node)
        if node is None or isinstance(node, (str, int, float, bool, bytes)):
            return
        if isinstance(node, type) or callable(node):
            return

        if isinstance(node, dict):
            if node.get("type") == "file_search_call":
                for result in node.get("results", []) or []:
                    result = _model_dump(result)
                    if isinstance(result, dict):
                        text = result.get("text") or result.get("content") or ""
                        if isinstance(text, list):
                            text = "\n".join(str(x) for x in text)
                        results.append({"file_id": result.get("file_id"), "filename": result.get("filename") or result.get("file_name") or result.get("title"), "score": result.get("score"), "text_preview": str(text)[:1200]})
            for child in node.values():
                visit(child)
        elif isinstance(node, (list, tuple, set)):
            for child in node:
                visit(child)

    visit(value)
    return results


def agent_file_search_results(run_result):
    return _collect_file_search_results(run_result)


def trace_function_result(name: str, *, input_obj=None, output_obj=None):
    with function_span(
        name,
        input=json.dumps(input_obj, ensure_ascii=False, default=str) if input_obj is not None else None,
        output=json.dumps(output_obj, ensure_ascii=False, default=str) if output_obj is not None else None,
    ):
        pass


def pretty(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))
````

<a id="input"></a>

---

## 2) 輸入

這一節定義 SchemaFlow 要處理的資料庫變更需求。可以把它想成資料團隊收到的精簡工單、issue 或訊息，之後才會被轉成實作細節。

預設的需求要流程做這些事：

1. 在 `ODS.ODS_CUSTOMER_PROFILE` 加 `LOYALTY_TIER VARCHAR(20)`。
2. 把新欄位當成 nullable。
3. 從 `CORE.DIM_CUSTOMER` 回填。
4. 用 `CUSTOMER_ID` 做 join。
5. 來源只取 `IS_CURRENT=true` 的當前紀錄。
6. 在 `(CUSTOMER_ID, LOYALTY_TIER)` 上加一個非 unique 的 index。

這個輸入刻意寫得精簡，但內容夠豐富，能把整個流程都練過一遍：

- 解析 target schema 和 table
- 抽出欄位名稱、型別和 nullability
- 辨識 backfill 的需求
- 辨識 index 的需求
- 產生跨多層的 SQL
- 對預期的 table、column 和 SQL 動作做驗證檢查

```python
CHANGE_TEXT = """Add LOYALTY_TIER VARCHAR(20) to ODS.ODS_CUSTOMER_PROFILE as nullable.
Backfill from CORE.DIM_CUSTOMER on CUSTOMER_ID where IS_CURRENT=true.
Add a non-unique index on (CUSTOMER_ID, LOYALTY_TIER)."""
print(CHANGE_TEXT)
```

<a id="optional-pdf-rag-context"></a>

---

## 3) 選配的 PDF RAG 上下文

SchemaFlow 有沒有 retrieval 上下文都能跑，所以你可以先只用變更需求開始，等變更真的需要時再加參考文件。

下面 code cell 裡的範例 PDF 路徑，指向 cookbook 資料夾 `data/` 底下附的檔案，不是嵌在 notebook 裡的 bytes。如果是靜態的文章預覽或一般執行，請保持 `PDF_PATH = None`。

預設 `PDF_PATH = None` 時，notebook 只用自然語言的變更需求。這樣就足以展示核心的分階段流程。

想讓 Impact Agent 的分析以參考資料為依據時，把 `PDF_PATH` 設成本機 PDF，例如：

- 介面設計文件
- schema 規格
- lineage 文件
- data contract
- 平台架構筆記
- 下游依賴文件

設定了 PDF 之後，這一節會：

1. 驗證檔案存在而且是 PDF。
2. 建一個有效期限一天的 OpenAI vector store。
3. 把 PDF 上傳到 vector store。
4. 讓 OpenAI 處理解析、切 chunk、embedding 和 retrieval。
5. 把 vector store ID 存起來給 Impact Agent 用。
6. 之後再彙整影響分析時 File Search 回傳的結果。

這樣 cookbook 可以保持輕量，因為不需要本機的 embedding model、Chroma、Neo4j、LangGraph，也不需要專案專屬的 Python module。

```python
from pathlib import Path

# Optional PDF RAG example.
# The GitHub repo includes this sample PDF under schemaflow_cookbook/data.
# When running from a repo checkout in the cookbook folder, uncomment the path below to upload it to File Search.
# For meaningful retrieval hits, pair it with the LOYALTY_TIER change request used in this notebook.
PDF_PATH = None
# PDF_PATH = "data/sample_customer_loyalty_ifd.pdf"
RAG_MAX_RESULTS = 6
rag_vector_store = None
rag_vector_store_id = None
rag_vector_store_file = None
rag_file_search_results = []
impact_response = None


def create_pdf_vector_store(pdf_path):
    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path}")
    with trace("SchemaFlow PDF Vector Store", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"step": "pdf_vector_store", "pdf_path": str(pdf_path)}):
        with custom_span("Create vector store", {"pdf_path": str(pdf_path)}):
            vector_store = client.vector_stores.create(name=f"schemaflow-cookbook-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}", expires_after={"anchor": "last_active_at", "days": 1})
        with custom_span("Upload PDF to vector store", {"vector_store_id": vector_store.id, "pdf_path": str(pdf_path)}):
            with pdf_path.open("rb") as handle:
                vector_store_file = client.vector_stores.files.upload_and_poll(vector_store_id=vector_store.id, file=handle)
        trace_function_result("PDF vector store ready", input_obj={"pdf_path": str(pdf_path)}, output_obj={"vector_store_id": vector_store.id, "status": getattr(vector_store_file, "status", "unknown")})
        flush_traces()
    return vector_store, vector_store_file


if PDF_PATH:
    rag_vector_store, rag_vector_store_file = create_pdf_vector_store(PDF_PATH)
    rag_vector_store_id = rag_vector_store.id
    print("Created vector store:", rag_vector_store_id)
    print("Uploaded PDF status:", getattr(rag_vector_store_file, "status", "unknown"))
else:
    print("No PDF configured. Leave PDF_PATH as None to run without RAG, or set it to a local PDF path.")
```

<a id="stages-1-2-parse-change-request--impact-analysis"></a>

---

## 4) Stages 1-2：解析變更需求與影響分析

這一節連續跑前兩個 agent 階段。兩者合起來回答兩個實務問題：到底要求了什麼，還有什麼可能受影響？

### Stage 1：解析變更需求

Parse Agent 把 `CHANGE_TEXT` 轉成結構化的 `change_json` 物件。

預期的欄位包括：

- `title`
- `domain`
- `target_schema`
- `target_table`
- `operations`
- `notes`

這個階段建立的是標準化契約，之後每個下游階段都會用它。如果 parse 漏掉了 target table、column、資料型別、nullability、backfill 或 index 的意圖，後面的階段就可能產出不完整的結果。所以 notebook 在這個階段之後馬上做驗證。

### Stage 2：影響分析

Impact Agent 讀進 `change_json`，產出 `impact_json`。

預期的欄位包括：

- `impacted_objects`
- `risks`
- `assumptions`

如果前面設定了 `PDF_PATH`，Impact Agent 還會拿到一個連到上傳 PDF vector store 的 `FileSearchTool`。這樣模型在回傳影響結論之前，可以先搜參考文件。

輸出刻意偏保守。當 agent 不確定時，應該明說假設和風險，而不是編出沒有文件依據的確定性。

<a id="impact-dashboard-preview"></a>

---

### Impact Dashboard 預覽

影響分析階段產出的結構化 `impact_json`，可以畫成受影響物件與關聯的圖。

下面的預覽是客戶 loyalty lineage 圖的樣子，它是 notebook 後面選配的 Neo4j 儀表板區段建出來的。跑那一節就能用範例的知識圖譜 seed 產生本機的圖形 UI，並互動式地檢視受影響的物件。

<img
  src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/schemaflow_kbgraph-small.gif"
  alt="Impact dashboard graph preview"
  style="width: 100%; max-width: 500px;"
/>


```python
# =============================================================
# Stage 1 - Parse Change Request
# =============================================================
print("=" * 60)
print("Stage 1 - Parse Change Request")
print("=" * 60)
PARSE_SYSTEM = """
You are a precise information extraction system for database change requests.
Return STRICT JSON only (no prose, no code fences, no comments).
Required keys:
{
  "title": str,
  "domain": str|null,
  "target_schema": str|null,
  "target_table": str|null,
  "operations": [{"op": str, "details": object}],
  "notes": []
}
Rules:
- Use lowercase op names.
- If schema/table unknown, set null.
- Keep details explicit and typed where possible.
""".strip()
parse_user = "Change Request:\n\n" + CHANGE_TEXT
change_json, parse_agent_result = run_schemaflow_json_agent(name="SchemaFlow Parse Agent", instructions=PARSE_SYSTEM, prompt=parse_user, output_schema=CHANGE_OUTPUT_SCHEMA, workflow_name="SchemaFlow Stage 1 Parse", metadata={"stage": "parse_change_request"})
if isinstance(change_json, dict):
    change_json.setdefault("title", None)
    change_json.setdefault("domain", None)
    change_json.setdefault("target_schema", None)
    change_json.setdefault("target_table", None)
    if not isinstance(change_json.get("operations"), list):
        change_json["operations"] = [change_json.get("operations")] if change_json.get("operations") else []
    if not isinstance(change_json.get("notes"), list):
        change_json["notes"] = []
pretty(change_json)

# =============================================================
# Stage 2 - Impact Analysis
# =============================================================
print("\n" + "=" * 60)
print("Stage 2 - Impact Analysis")
print("=" * 60)
IMPACT_SYSTEM = """
You are a cautious impact analysis assistant.
Inputs:
- change_json: normalized change request.
- optional File Search context from an uploaded IFD/reference PDF.
Task:
Return JSON exactly as:
{
  "impacted_objects": [
    {"type":"table|column|fk|index|view","name":str,"reason":str,"source":"file_search|ifd|inference"}
  ],
  "risks": [str],
  "assumptions": [str]
}
Rules:
- Be conservative when uncertain.
- Call out data quality/backfill risks explicitly.
- If File Search context is available, use it to ground table, column, and downstream-impact claims.
""".strip()
impact_user_parts = ["CHANGE_JSON:\n" + json.dumps(change_json, ensure_ascii=False)]
impact_tools = []
if rag_vector_store_id:
    impact_tools.append(FileSearchTool(vector_store_ids=[rag_vector_store_id], max_num_results=RAG_MAX_RESULTS, include_search_results=True))
    impact_user_parts.append("Use the file_search tool against the uploaded PDF to look for relevant IFD, schema, table, column, lineage, and downstream dependency context before returning JSON.")
impact_json, impact_agent_result = run_schemaflow_json_agent(name="SchemaFlow Impact Agent", instructions=IMPACT_SYSTEM, prompt="\n\n".join(impact_user_parts), output_schema=IMPACT_OUTPUT_SCHEMA, tools=impact_tools, workflow_name="SchemaFlow Stage 2 Impact Analysis", metadata={"stage": "impact_analysis", "rag_enabled": bool(rag_vector_store_id)})
impact_response = impact_agent_result
try:
    rag_file_search_results = agent_file_search_results(impact_agent_result)
except Exception as exc:
    rag_file_search_results = []
    print(f"File Search result summary skipped: {type(exc).__name__}: {exc}")
if rag_vector_store_id:
    print("File Search results returned:", len(rag_file_search_results))
    for i, result in enumerate(rag_file_search_results, start=1):
        print(f"{i}. {result.get('filename') or result.get('file_id')} score={result.get('score')}")
if isinstance(impact_json, dict):
    impact_json.setdefault("impacted_objects", [])
    impact_json.setdefault("risks", [])
    impact_json.setdefault("assumptions", [])
pretty(impact_json)
flush_traces()
```

<a id="stages-1-2-output-guardrails"></a>

---

### Stages 1-2 輸出 Guardrails

這個 guardrail cell 在流程繼續之前，對 Parse 和 Impact 的輸出做確定性檢查。

檢查內容：

- `change_json` 有 target schema。
- `change_json` 有 target table。
- `change_json.operations` 是非空的 list。
- `impact_json.impacted_objects` 至少有一個物件。
- impact 輸出有提到解析出來的 target table。
- 每個受影響的物件都有基本必要欄位，例如 type、name 和 reason。

這些檢查刻意做得輕量。它們不能證明分析很完整，但可以在 Plan Agent 或 SQL Agent 吃到格式錯誤或不完整的狀態之前，先抓到明顯的失敗。

```python
# Stages 1-2 Output Guardrails - inspects change_json (Parse) and impact_json (Impact).
stages_1_2_guardrails = []
with trace("SchemaFlow Stages 1-2 Guardrails", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "stages_1_2_guardrails"}):
    def _check(name, ok, detail=""):
        ok = bool(ok)
        stages_1_2_guardrails.append({"name": name, "ok": ok, "detail": detail})
        with guardrail_span(name, triggered=not ok):
            trace_function_result(name + " detail", output_obj={"ok": ok, "detail": detail})

    _target_schema = (change_json.get("target_schema") or "").strip() if isinstance(change_json, dict) else ""
    _target_table = (change_json.get("target_table") or "").strip() if isinstance(change_json, dict) else ""
    _ops = change_json.get("operations") if isinstance(change_json, dict) else None
    _check("parse_output_well_formed", bool(_target_schema) and bool(_target_table) and isinstance(_ops, list) and len(_ops) > 0, f"target={_target_schema}.{_target_table}, ops={len(_ops or [])}")
    _impacted = impact_json.get("impacted_objects") if isinstance(impact_json, dict) else []
    _target_fqn = f"{_target_schema}.{_target_table}" if (_target_schema and _target_table) else ""
    _target_in_impact = any(isinstance(o, dict) and (o.get("name", "").upper() == _target_fqn.upper() or (_target_table and _target_table.upper() in o.get("name", "").upper())) for o in (_impacted or []))
    _check("impact_includes_target", bool(_impacted) and _target_in_impact, f"{len(_impacted or [])} impacted object(s), target_match={_target_in_impact}")
    _malformed = [i for i, o in enumerate(_impacted or []) if not (isinstance(o, dict) and o.get("type") and o.get("name") and o.get("reason"))]
    _check("impacted_objects_well_formed", not _malformed, "all populated" if not _malformed else f"missing fields at indices {_malformed[:5]}")
    stages_1_2_guardrails_passed = all(c["ok"] for c in stages_1_2_guardrails)
    trace_function_result("Stages 1-2 guardrails summary", output_obj={"passed": stages_1_2_guardrails_passed, "checks": stages_1_2_guardrails})
    flush_traces()
print(f"Stages 1-2 Output Guardrails: {'PASS' if stages_1_2_guardrails_passed else 'FAIL'}")
for _c in stages_1_2_guardrails:
    _flag = "OK  " if _c["ok"] else "FAIL"
    print(f"  [{_flag}] {_c['name']:35s} {_c['detail']}")
```

<a id="stages-3-4-execution-plan--sql-generation"></a>

---

## 5) Stages 3-4：執行計畫與 SQL 產生

這一節跑實作規劃和 SQL 產生兩個階段。到這裡，流程從理解需求轉成起草實作交接內容。

### Stage 3：執行計畫

Plan Agent 的輸入是：

- `change_json`
- `impact_json`

它回傳 `plan_json`，裡面有四個區段：

- `plan_steps`
- `prechecks`
- `postchecks`
- `rollback`

目的是在產生 SQL 之前，先把實作策略講清楚。這樣能把「該做什麼」和「該起草怎樣的 SQL」分開。

### Stage 4：SQL 產生

SQL Agent 的輸入是：

- `change_json`
- `plan_json`

它回傳一份純文字的 SQL 腳本。prompt 要求依序包含四個區段：1. `-- === LANDING (ODS) ===`
2. `-- === STAGING (STG) ===`
3. `-- === CORE (DIM/FACT/VIEW) ===`
4. `-- === MARTS (SERVING) ===`

產生的 SQL 只是給人審查的草稿，任何 production 使用之前，都要經過工程師檢查。

```python
# =============================================================
# Stage 3 - Execution Plan
# =============================================================
print("=" * 60)
print("Stage 3 - Execution Plan")
print("=" * 60)
PLAN_SYSTEM = """
You are a senior data engineer creating a safe execution plan.
Inputs:
- change_json
- impact_json
Return JSON:
{
  "plan_steps": [{"id": "str", "description": "str"}],
  "prechecks": [str],
  "postchecks": [str],
  "rollback": [str]
}
Guidance:
- Include practical pre/post checks.
- Keep steps executable and concise.
""".strip()
plan_user = "\n\n".join(["CHANGE_JSON:\n" + json.dumps(change_json, ensure_ascii=False), "IMPACT_JSON:\n" + json.dumps(impact_json, ensure_ascii=False)])
plan_json, plan_agent_result = run_schemaflow_json_agent(name="SchemaFlow Plan Agent", instructions=PLAN_SYSTEM, prompt=plan_user, output_schema=PLAN_OUTPUT_SCHEMA, workflow_name="SchemaFlow Stage 3 Execution Plan", metadata={"stage": "execution_plan"})
if isinstance(plan_json, dict):
    plan_json.setdefault("plan_steps", [])
    plan_json.setdefault("prechecks", [])
    plan_json.setdefault("postchecks", [])
    plan_json.setdefault("rollback", [])
pretty(plan_json)

# =============================================================
# Stage 4 - SQL Generation
# =============================================================
print("\n" + "=" * 60)
print("Stage 4 - SQL Generation")
print("=" * 60)
SQL_SYSTEM = """
You are a senior data engineer producing SQL for multi-layer data stacks.
Output a SINGLE plaintext script with FOUR sections in order:
1) -- === LANDING (ODS) ===
2) -- === STAGING (STG) ===
3) -- === CORE (DIM/FACT/VIEW) ===
4) -- === MARTS (SERVING) ===

Rules:
- PostgreSQL dialect.
- Prefer idempotent DDL where possible.
- Propagate requested changes through downstream layers.
- Include concise assumptions as comments.
""".strip()
sql_user = "\n\n".join(["CHANGE_JSON:\n" + json.dumps(change_json, ensure_ascii=False), "PLAN_JSON:\n" + json.dumps(plan_json, ensure_ascii=False)])
sql_text, sql_agent_result = run_schemaflow_text_agent(name="SchemaFlow SQL Agent", instructions=SQL_SYSTEM, prompt=sql_user, workflow_name="SchemaFlow Stage 4 SQL Generation", metadata={"stage": "sql_generation"})
print(sql_text[:5000])
flush_traces()
```

<a id="stages-3-4-output-guardrails"></a>

---

### Stages 3-4 輸出 Guardrails

這個 guardrail cell 在 notebook 進入最後的 SQL sanity check 之前，先驗證計畫和 SQL 草稿。

檢查內容：

- 計畫的四個區段都有內容：
  - `plan_steps`
  - `prechecks`
  - `postchecks`
  - `rollback`
- `CHANGE_TEXT` 要求的資料型別有出現在產生的 SQL 裡
- 需求是 nullable 的話，不會不小心建出 `NOT NULL` 限制
- 需求明確要求 `NOT NULL` 時，SQL 有反映出來

這些檢查是 Stage 5 的補充。Stages 3-4 的 guardrail 著重在計畫完整度和語意一致性，Stage 5 則著重在預期的 SQL 詞彙和動作。

```python
# Stages 3-4 Output Guardrails - inspects plan_json (Plan) and sql_text (SQL).
import re as _re
stages_3_4_guardrails = []
with trace("SchemaFlow Stages 3-4 Guardrails", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "stages_3_4_guardrails"}):
    def _check(name, ok, detail=""):
        ok = bool(ok)
        stages_3_4_guardrails.append({"name": name, "ok": ok, "detail": detail})
        with guardrail_span(name, triggered=not ok):
            trace_function_result(name + " detail", output_obj={"ok": ok, "detail": detail})

    _plan = plan_json if isinstance(plan_json, dict) else {}
    _plan_missing = [k for k in ["plan_steps", "prechecks", "postchecks", "rollback"] if not _plan.get(k)]
    _check("plan_sections_populated", not _plan_missing, "all four populated" if not _plan_missing else f"empty: {_plan_missing}")
    _dtype_match = _re.search(r"\b(?:add\s+\w+\s+|column\s+\w+\s+)((?:VAR)?CHAR\s*\([^)]*\)|TEXT|INTEGER|INT|BIGINT|BOOLEAN|DATE|TIMESTAMP|NUMERIC\s*\([^)]*\)|DECIMAL\s*\([^)]*\)|FLOAT|DOUBLE)", CHANGE_TEXT, flags=_re.IGNORECASE)
    if _dtype_match:
        _dtype = " ".join(_dtype_match.group(1).upper().split())
        _check("data_type_propagated_to_sql", _dtype.lower() in sql_text.lower(), f"expected '{_dtype}' in SQL")
    else:
        _check("data_type_propagated_to_sql", True, "no data type referenced in CHANGE_TEXT (skipped)")
    _change_lower = CHANGE_TEXT.lower()
    _sql_lower = sql_text.lower()
    _expected_cols = []
    for _op in (change_json.get("operations") if isinstance(change_json, dict) else []) or []:
        _details = _op.get("details") if isinstance(_op, dict) else None
        if isinstance(_details, dict):
            for _key in ("column", "column_name", "name"):
                _val = _details.get(_key)
                if isinstance(_val, str) and _val.strip():
                    _expected_cols.append(_val.strip().lower())
    if "not null" in _change_lower:
        _check("nullability_matches_request", "not null" in _sql_lower, "request: NOT NULL")
    elif "nullable" in _change_lower:
        _ddl_lines = []
        for line in sql_text.split("\n"):
            _line = line.strip().lower()
            if not any(c in _line for c in _expected_cols):
                continue
            if "add column" in _line or any(_line.startswith(c + " ") or _line.startswith(c + "\t") for c in _expected_cols):
                _ddl_lines.append(line.strip())
        _bad_lines = [line for line in _ddl_lines if "not null" in line.lower()]
        _check("nullability_matches_request", not _bad_lines, "no NOT NULL on nullable column DDL" if not _bad_lines else f"NOT NULL conflict in {len(_bad_lines)} DDL line(s)")
    else:
        _check("nullability_matches_request", True, "no explicit nullability requested (skipped)")
    stages_3_4_guardrails_passed = all(c["ok"] for c in stages_3_4_guardrails)
    trace_function_result("Stages 3-4 guardrails summary", output_obj={"passed": stages_3_4_guardrails_passed, "checks": stages_3_4_guardrails})
    flush_traces()
print(f"Stages 3-4 Output Guardrails: {'PASS' if stages_3_4_guardrails_passed else 'FAIL'}")
for _c in stages_3_4_guardrails:
    _flag = "OK  " if _c["ok"] else "FAIL"
    print(f"  [{_flag}] {_c['name']:35s} {_c['detail']}")
```

<a id="stage-5-lightweight-sql-sanity-checks"></a>

---

## 6) Stage 5：輕量的 SQL Sanity Checks

這一節對本次 notebook 執行產生的 SQL 做確定性檢查。

這不是完整的 SQL parser，也不會執行 SQL。它只檢查原始需求、解析後的變更物件和產生的腳本之間，有沒有明顯對不上的地方。這些檢查刻意做得小而好解釋，讀的人能清楚看到哪些通過、哪些失敗，之後才存檔或拿去 eval。

檢查項目：

- SQL 輸出是否為空
- 是否缺少 target table
- 是否缺少預期的 column
- 從需求推出的必要 SQL 關鍵字：
  - `ALTER TABLE`
  - 需求暗示 backfill 或從來源填值時要有 `UPDATE`
  - 需求提到 index 時要有 `CREATE INDEX`

輸出存在 `validation`，它會成為最終 bundle 的一部分，也會被 Promptfoo 的 full-flow assertion 使用。

```python
with trace("SchemaFlow Stage 5 SQL Sanity Checks", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "sql_sanity_checks"}):
    issues = []
    sql_lower = sql_text.lower()
    change_lower = CHANGE_TEXT.lower()
    if not sql_text.strip():
        issues.append("SQL output is empty")
    expected_schema = (change_json.get("target_schema") or "").strip()
    expected_table = (change_json.get("target_table") or "").strip()
    if expected_table and expected_table.lower() not in sql_lower:
        issues.append(f"Expected target table missing from SQL: {expected_table}")
    expected_columns = []
    for operation in change_json.get("operations", []):
        details = operation.get("details") if isinstance(operation, dict) else None
        if not isinstance(details, dict):
            continue
        for key in ["column", "column_name", "name"]:
            value = details.get(key)
            if isinstance(value, str) and value.strip():
                expected_columns.append(value.strip())
    for column in dict.fromkeys(expected_columns):
        if column.lower() not in sql_lower:
            issues.append(f"Expected column missing from SQL: {column}")
    required_keywords = ["ALTER TABLE"]
    if any(term in change_lower for term in ["backfill", "update", "source it from"]):
        required_keywords.append("UPDATE")
    if "index" in change_lower:
        required_keywords.append("CREATE INDEX")
    for keyword in dict.fromkeys(required_keywords):
        if keyword.lower() not in sql_lower:
            issues.append(f"Expected keyword missing: {keyword}")
    validation = {"valid": len(issues) == 0, "issues": issues, "checks": {"expected_schema": expected_schema or None, "expected_table": expected_table or None, "expected_columns": list(dict.fromkeys(expected_columns)), "required_keywords": list(dict.fromkeys(required_keywords))}}
    with guardrail_span("stage5_sql_sanity", triggered=not validation["valid"]):
        trace_function_result("Stage 5 SQL sanity result", output_obj=validation)
    flush_traces()
pretty(validation)
```

<a id="final-bundle"></a>

---

## 7) Final Bundle

這一節組出 SchemaFlow 的主要輸出物件。

最終的 `bundle` 包含：

- `summary`
- `rag`
- `change_json`
- `impact_json`
- `plan`
- `sql`
- `validation`

這個物件是本次 notebook 執行的審查交接 artifact。它把模型產生的輸出、確定性的驗證結果和選配的 retrieval metadata 集中在一起，reviewer 不用從分散的 cell 重建整個流程。

印出的 summary 簡要列出這次執行最重要的資訊：

- 解析出的 title
- 解析出的 target
- RAG 命中數
- 計畫步驟數
- 驗證狀態
- 驗證問題

```python
with trace("SchemaFlow Final Bundle", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "final_bundle"}):
    bundle = {
        "summary": {"matched_tables": [], "impact_risks": impact_json.get("risks", []), "rag_hits": len(rag_file_search_results)},
        "rag": {"vector_store_id": rag_vector_store_id, "file_search_results": rag_file_search_results},
        "change_json": change_json,
        "impact_json": impact_json,
        "plan": plan_json,
        "sql": sql_text,
        "validation": validation,
    }
    trace_function_result("Final bundle assembled", output_obj=bundle)
    flush_traces()
pretty({"title": change_json.get("title"), "target": ".".join([x for x in [change_json.get("target_schema"), change_json.get("target_table")] if x]), "rag_hits": len(rag_file_search_results), "plan_steps": len(plan_json.get("plan_steps", [])), "valid": validation.get("valid"), "issues": validation.get("issues", [])})
```

<a id="save-artifact"></a>

---

## 8) 儲存 Artifact

這一節把最終的 `bundle` 以 JSON 寫到磁碟。

Artifact 存在：

```text
artifacts/notebook_runs/
```

每次執行都會得到一個帶時間戳的檔名，方便你比較不同 prompt、模型、輸入或檢索文件之間的輸出差異。

存下來的 artifact 可以用在：

- code review
- 稽核紀錄
- debug
- regression 比對
- 建立 eval fixture
- 下游自動化

```python
from pathlib import Path
with trace("SchemaFlow Save Artifact", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "save_artifact"}):
    out_dir = Path("artifacts/notebook_runs")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"schemaflow_cookbook_run_{ts}.json"
    out_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    trace_function_result("Notebook artifact saved", input_obj={"bundle_keys": sorted(bundle.keys())}, output_obj={"path": str(out_path.resolve()), "bytes": out_path.stat().st_size})
    flush_traces()
print("Saved artifact:", out_path.resolve())
```

<a id="post-artifact-generation-sanity-check"></a>

---

### Post-Artifact 產生後的 Sanity Check

這個 cell 驗證存下來的 artifact 能用。

它檢查：

- artifact 檔案存在
- artifact 檔案不是空的
- 檔案可以用 `json.loads` 載入
- 磁碟上的頂層 key 跟記憶體裡的 `bundle` 一致

這樣檔案寫入的問題會馬上被發現，不會等到後面的 review、eval 或自動化步驟才吃到遺失或壞掉的 artifact。

```python
# Post-Artifact Generation Sanity Check - re-reads the file Save Artifact wrote.
post_artifact_checks = []
with trace("SchemaFlow Post-Artifact Guardrails", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "post_artifact_guardrails"}):
    def _check(name, ok, detail=""):
        ok = bool(ok)
        post_artifact_checks.append({"name": name, "ok": ok, "detail": detail})
        with guardrail_span(name, triggered=not ok):
            trace_function_result(name + " detail", output_obj={"ok": ok, "detail": detail})
    _size = out_path.stat().st_size if out_path.exists() else 0
    _check("artifact_file_persisted", out_path.exists() and _size > 0, f"{_size} bytes")
    if out_path.exists():
        try:
            _roundtrip = json.loads(out_path.read_text(encoding="utf-8"))
            _check("artifact_roundtrip_keys_match", set(_roundtrip.keys()) == set(bundle.keys()), f"disk_keys={sorted(_roundtrip.keys())}")
        except Exception as _exc:
            _check("artifact_roundtrip_keys_match", False, str(_exc))
    else:
        _check("artifact_roundtrip_keys_match", False, "saved file missing")
    post_artifact_sanity_passed = all(c["ok"] for c in post_artifact_checks)
    trace_function_result("Post-artifact guardrails summary", output_obj={"passed": post_artifact_sanity_passed, "checks": post_artifact_checks})
    flush_traces()
print(f"Post-Artifact Sanity Check: {'PASS' if post_artifact_sanity_passed else 'FAIL'}")
for _c in post_artifact_checks:
    _flag = "OK  " if _c["ok"] else "FAIL"
    print(f"  [{_flag}] {_c['name']:30s} {_c['detail']}")
```

<a id="optional-cleanup"></a>

---

## 9) 選配的清理

這一節處理選配 PDF vector store 的清理。

預設 `DELETE_VECTOR_STORE_AFTER_RUN = False`。

這個預設對互動式 notebook 比較安全，因為 vector store 建立時有一天的到期政策。暫時留著，方便你檢查 trace、重跑下游階段或 debug File Search 的行為。

如果想在 notebook 跑完後立刻刪掉 vector store，執行這個 cell 之前先把 `DELETE_VECTOR_STORE_AFTER_RUN = True` 設好。

如果沒有設定 PDF，這個 cell 只會回報沒有建立 vector store。

```python
DELETE_VECTOR_STORE_AFTER_RUN = False
with trace("SchemaFlow Optional Cleanup", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata=_trace_metadata({"stage": "optional_cleanup", "delete_vector_store_after_run": DELETE_VECTOR_STORE_AFTER_RUN})):
    if rag_vector_store_id and DELETE_VECTOR_STORE_AFTER_RUN:
        with custom_span("Delete vector store", {"vector_store_id": rag_vector_store_id}):
            client.vector_stores.delete(vector_store_id=rag_vector_store_id)
        print("Deleted vector store:", rag_vector_store_id)
    elif rag_vector_store_id:
        trace_function_result("Vector store retained", output_obj={"vector_store_id": rag_vector_store_id, "expiration": "1 day"})
        print("Vector store retained with one-day expiration:", rag_vector_store_id)
    else:
        trace_function_result("No vector store cleanup", output_obj={"created": False})
        print("No vector store was created.")
    flush_traces()
```

<a id="pre-promptfoo-checks--guardrails"></a>

---

### Pre-Promptfoo Checks / Guardrails

這個 cell 是跑 Promptfoo 之前的準備關卡。

Promptfoo 在另一個 process 執行流程，所以在產生 eval 檔案之前，要先確認 notebook 的狀態完整而且內部一致。

preflight 檢查包括：

- `bundle` 存在於 notebook kernel 裡。
- `bundle` 反映目前的 `change_json` 和 `plan_json`。
- Stage 5 的驗證通過。
- Stages 1-2 的 guardrail 通過。
- Stages 3-4 的 guardrail 通過。
- 存下來的 artifact sanity check 通過。
- `CHANGE_TEXT` 跟解析出的 bundle target 一致。
- `OPENAI_API_KEY` 存在。
- 安裝的 Agents SDK 版本符合最低要求。

如果這一節回報失敗，先重跑或修好前面的 notebook 區段，再跑 Promptfoo。

```python
# Pre-Promptfoo Checks / Guardrails - deterministic, no LLM calls.
import os
import re as _re
pre_promptfoo_checks = []
with trace("SchemaFlow Pre-Promptfoo Guardrails", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"stage": "pre_promptfoo_guardrails"}):
    def _check(name, ok, detail=""):
        ok = bool(ok)
        pre_promptfoo_checks.append({"name": name, "ok": ok, "detail": detail})
        with guardrail_span(name, triggered=not ok):
            trace_function_result(name + " detail", output_obj={"ok": ok, "detail": detail})
    _bundle = globals().get("bundle")
    _check("bundle_in_scope", isinstance(_bundle, dict) and "validation" in _bundle, f"keys={sorted(_bundle.keys()) if isinstance(_bundle, dict) else 'n/a'}")
    _check("bundle_in_sync_with_kernel", bundle.get("change_json") == change_json and bundle.get("plan") == plan_json, "bundle reflects current change_json + plan_json")
    _check("stage5_validation_passed", bool(validation.get("valid")), f"{len(validation.get('issues', []))} issue(s) recorded by Stage 5")
    _check("stages_1_2_guardrails_passed", bool(globals().get("stages_1_2_guardrails_passed", False)), "consumed from Stages 1-2 Output Guardrails cell")
    _check("stages_3_4_guardrails_passed", bool(globals().get("stages_3_4_guardrails_passed", False)), "consumed from Stages 3-4 Output Guardrails cell")
    _check("post_artifact_sanity_passed", bool(globals().get("post_artifact_sanity_passed", False)), "consumed from Post-Artifact Sanity Check cell")
    _target_match = _re.search(r"\b(?:to|from|in|on)\s+([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)", CHANGE_TEXT, flags=_re.IGNORECASE)
    if _target_match:
        _live_target = _target_match.group(2).upper()
        _bundle_target = (bundle.get("change_json", {}).get("target_table") or "").upper()
        _check("change_text_consistent_with_bundle", _live_target == _bundle_target, f"live='{_live_target}', bundle='{_bundle_target}'")
    else:
        _check("change_text_consistent_with_bundle", True, "no extractable target in CHANGE_TEXT (skipped)")
    _check("openai_api_key_set_in_env", bool(os.getenv("OPENAI_API_KEY")), "present" if os.getenv("OPENAI_API_KEY") else "missing")
    _check("agents_sdk_min_version", _version_tuple(AGENTS_SDK_VERSION) >= _version_tuple(MIN_AGENTS_SDK_VERSION), f"found={AGENTS_SDK_VERSION}, required>={MIN_AGENTS_SDK_VERSION}")
    pre_promptfoo_passed = all(c["ok"] for c in pre_promptfoo_checks)
    trace_function_result("Pre-Promptfoo readiness summary", output_obj={"passed": pre_promptfoo_passed, "checks": pre_promptfoo_checks})
    flush_traces()
print("=" * 60)
print(f"Pre-Promptfoo Readiness: {'PASS' if pre_promptfoo_passed else 'FAIL'}")
print("=" * 60)
for _c in pre_promptfoo_checks:
    _flag = "OK  " if _c["ok"] else "FAIL"
    print(f"  [{_flag}] {_c['name']:35s} {_c['detail']}")
if not pre_promptfoo_passed:
    print()
    print("One or more readiness checks failed. Promptfoo will likely fail or eval stale state.")
    print("Investigate the failed checks above before running Section 10.")
```

<a id="evaluate-the-flow-with-promptfoo"></a>

---

## 10) 用 Promptfoo 評測流程

Promptfoo 現在是 OpenAI 的一部分。這一節用 Promptfoo 的 Jupyter/Colab 模式，從 notebook cell 跑 eval，同時讓 SchemaFlow 的邏輯保持在好讀的 Python 裡。Promptfoo 本身透過 Node.js 執行，被評測的流程則透過 Promptfoo 的 Python `file://` provider 和 Python assertion 整合進來。

這個選配區段把 notebook 流程變成可重複跑的 eval。

核心的 notebook 執行只驗證一個即時範例。Promptfoo 多提供一套可重用的 eval 工具組，用產生出來的 provider 和 assertion 檔跑 parse-only 與 full-flow 的檢查，當你調整 prompt、模型或輸入、又想讓流程保持穩定時就很有用。

因為 Promptfoo 會啟動另一個 Python process，它沒辦法直接存取只存在於 notebook kernel 裡的變數。為了解決這點，接下來的 cell 會從目前的 notebook 狀態發布 runtime 檔案：

- 可重用的 `schemaflow_cookbook_core.py` module
- 一個 Python Promptfoo provider
- 一個 Python Promptfoo assertion 檔
- 產生出來的 eval case
- 產生出來的 Promptfoo config

這一節包含三層驗證：

1. **Input preflight**
   - 寫 config 之前的確定性檢查
   - 不呼叫模型

2. **Parse-only eval**
   - 檢查 Stage 1 的行為
   - 驗證 target、operation 是否存在、預期新增的欄位和預期的資料型別

3. **Full-flow eval**
   - 檢查下游的影響分析、SQL 詞彙和驗證狀態

Eval 結果會印在 notebook 裡，並匯出成帶時間戳的 JSON 和 HTML 檔，存放在：

```text
artifacts/promptfoo/results/
```

最近一次成功的執行還會更新：

```text
schemaflow_cookbook_eval_latest.json
schemaflow_cookbook_eval_latest.html
```

Runtime 注意事項：核心的 SchemaFlow cell 需要 Python 和 OpenAI API key。Promptfoo 的 cell 另外需要在同一個可執行 notebook 的 runtime 裡有 Node.js 和 npm。

eval 跑完後，Promptfoo 會提供一個精簡的檢視，包含目前的變更需求、預期欄位、parse-only 檢查和 full-flow 檢查。

用這個檢視可以回答這些問題：

- Parse Agent 有抽出預期的 target table 嗎？
- 它有偵測到預期新增的欄位嗎？
- 它有保留要求的資料型別嗎？
- full flow 有產出 impact 風險嗎？
- SQL 有包含必要的詞彙嗎？
- 確定性驗證通過了嗎？

![Promptfoo eval results view](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/schemaflow_promptfoo.gif)


<a id="promptfoo-runtime-directory-setup"></a>

---

### Promptfoo Runtime 目錄設定

這個 cell 在 notebook 旁邊建立 Promptfoo config、log、cache、npm cache 和結果用的目錄。

把這些目錄放在 `artifacts/promptfoo/` 底下，讓 eval runtime 可攜，也不用依賴使用者家目錄下的全域 Promptfoo 狀態。

這個 cell 也會匯出環境變數，讓產生出來的 provider、assertion 和 Promptfoo 指令都用同一個 trace group 和本機 runtime 路徑。

```python
from pathlib import Path
import os
PROMPTFOO_DIR = Path("artifacts/promptfoo")
PROMPTFOO_DIR.mkdir(parents=True, exist_ok=True)
PROMPTFOO_CONFIG_DIR = PROMPTFOO_DIR / ".promptfoo"
PROMPTFOO_LOG_DIR = PROMPTFOO_CONFIG_DIR / "logs"
PROMPTFOO_CACHE_DIR = PROMPTFOO_CONFIG_DIR / "cache"
PROMPTFOO_RESULTS_DIR = PROMPTFOO_DIR / "results"
NPM_CACHE_DIR = PROMPTFOO_DIR / ".npm-cache"
for path in (PROMPTFOO_CONFIG_DIR, PROMPTFOO_LOG_DIR, PROMPTFOO_CACHE_DIR, PROMPTFOO_RESULTS_DIR, NPM_CACHE_DIR):
    path.mkdir(parents=True, exist_ok=True)
os.environ["PROMPTFOO_CONFIG_DIR"] = str(PROMPTFOO_CONFIG_DIR.resolve())
os.environ["PROMPTFOO_LOG_DIR"] = str(PROMPTFOO_LOG_DIR.resolve())
os.environ["PROMPTFOO_CACHE_PATH"] = str(PROMPTFOO_CACHE_DIR.resolve())
os.environ["npm_config_cache"] = str(NPM_CACHE_DIR.resolve())
os.environ["npm_config_update_notifier"] = "false"
os.environ["npm_config_loglevel"] = "error"
os.environ["SCHEMAFLOW_TRACE_GROUP_ID"] = SCHEMAFLOW_TRACE_GROUP_ID
os.environ["OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"] = os.getenv("OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA", "false")
print("Promptfoo runtime dir:", PROMPTFOO_DIR.resolve())
print("Promptfoo config dir:", PROMPTFOO_CONFIG_DIR.resolve())
print("Promptfoo results dir:", PROMPTFOO_RESULTS_DIR.resolve())
print("Notebook-local npm cache:", NPM_CACHE_DIR.resolve())
print("Promptfoo trace group:", SCHEMAFLOW_TRACE_GROUP_ID)
```

<a id="nodejs-and-npm-runtime-check"></a>

---

### Node.js 與 npm Runtime 檢查

即使 SchemaFlow 的 provider 和 assertion 邏輯是用 Python 寫的，Promptfoo 還是透過 Node.js 執行。

這個 cell 確認 notebook 的 runtime 有支援的 `node` 和 `npm`。

這個檢查刻意做得明確。notebook 不會偷偷安裝或升級 Node，因為那要看執行環境。

在本機 macOS 的 notebook 上，這個 cell 會優先選支援的 `nvm` Node runtime，再看常見的 Homebrew 路徑。這樣可以確保 notebook 和終端機用同一個 Node ABI，避免過期的 native 相依套件。

如果檢查失敗，先修好 runtime，再重跑 Promptfoo 區段。

```python
import os
import re
import shutil
import subprocess
from pathlib import Path

REQUIRED_NODE = "^20.20.0 or >=22.22.0"
COMMON_NODE_DIRS = ["/opt/homebrew/bin", "/usr/local/bin"]


def _nvm_node_dirs():
    root = Path.home() / ".nvm" / "versions" / "node"
    if not root.exists():
        return []
    candidates = []
    for node_bin in root.glob("*/bin/node"):
        version = _node_version(str(node_bin))
        if version and _node_is_supported(version[1]):
            candidates.append((version[1], str(node_bin.parent)))
    return [path for _, path in sorted(candidates, reverse=True)]


def _node_version(node_cmd="node"):
    try:
        raw = subprocess.check_output([node_cmd, "--version"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", raw)
    if not match:
        return None
    return raw, tuple(int(part) for part in match.groups())


def _node_is_supported(version_tuple):
    major, minor, patch = version_tuple
    return (major == 20 and minor >= 20) or (major >= 22)


def _prepend_path(path_dir):
    parts = os.environ.get("PATH", "").split(os.pathsep)
    parts = [p for p in parts if p and p != path_dir]
    os.environ["PATH"] = path_dir + os.pathsep + os.pathsep.join(parts)


def ensure_promptfoo_node_runtime():
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    current = _node_version("node") if node_path else None

    if current and npm_path and _node_is_supported(current[1]):
        print(f"Node OK: {node_path} ({current[0]})")
        print(f"npm: {npm_path}")
        return

    for candidate_dir in [*_nvm_node_dirs(), *COMMON_NODE_DIRS]:
        candidate_node = Path(candidate_dir) / "node"
        candidate_npm = Path(candidate_dir) / "npm"
        if not candidate_node.exists() or not candidate_npm.exists():
            continue
        candidate = _node_version(str(candidate_node))
        if candidate and _node_is_supported(candidate[1]):
            _prepend_path(candidate_dir)
            print(f"Switched notebook PATH to supported Node: {candidate_node} ({candidate[0]})")
            print(f"npm: {candidate_npm}")
            return

    detected = current[0] if current else "not found"
    raise RuntimeError(
        "Promptfoo requires Node.js " + REQUIRED_NODE + ".\n"
        f"Detected Node: {detected}.\n\n"
        "Use an executable runtime with supported Node/npm before continuing.\n"
        "Examples:\n"
        "- Google Colab or Codespaces: run the notebook in that runtime and rerun this cell.\n"
        "- macOS nvm: `nvm install 22 && nvm use 22`, then start Jupyter from that terminal.\n"
        "- macOS Homebrew: `brew install node`, then start Jupyter from a terminal where the intended Node is first on PATH.\n"
        "- nvm: `nvm install 22 && nvm use 22`, then start Jupyter from that same shell.\n\n"
        "Static notebook preview in a browser cannot run Promptfoo evals."
    )


ensure_promptfoo_node_runtime()
```

<a id="publish-schemaflow-core-runtime"></a>

---

### 發布 SchemaFlow Core Runtime

Promptfoo 在另一個 Python process 裡執行被評測的流程。這個 cell 寫出一個可重用的 Python module，名稱是：

```text
artifacts/promptfoo/schemaflow_cookbook_core.py
```

產生的 module 包含 notebook 裡用的同一套 SchemaFlow 核心邏輯：

- Pydantic model
- Agents SDK 設定
- 輸出正規化的 helper
- Parse Agent 的執行
- Impact Agent 的執行
- 選配的 PDF vector store 建立
- Plan Agent 的執行
- SQL Agent 的執行
- SQL 驗證
- parse-only eval 的進入點
- full-flow eval 的進入點

prompt 字串是從目前 notebook 的變數注入的。也就是說，如果你改了上面的 Parse、Impact、Plan 或 SQL prompt 再重跑這個 cell，Promptfoo runtime 就會拿到更新後的 prompt。

````python
from pathlib import Path

CORE_MODULE_TEMPLATE = r'''
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from openai import OpenAI
from pydantic import BaseModel, ConfigDict, Field
from agents import Agent, AgentOutputSchema, FileSearchTool, Runner, RunConfig, custom_span, flush_traces, function_span, guardrail_span, trace

MODEL = os.getenv("OPENAI_MODEL", __MODEL_DEFAULT__)
PARSE_SYSTEM = __PARSE_SYSTEM__
IMPACT_SYSTEM = __IMPACT_SYSTEM__
PLAN_SYSTEM = __PLAN_SYSTEM__
SQL_SYSTEM = __SQL_SYSTEM__
MIN_AGENTS_SDK_VERSION = "0.17.0"
TRACE_INCLUDE_SENSITIVE_DATA = os.getenv("OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA", "false").lower() in {"1", "true", "yes", "on"}
SCHEMAFLOW_TRACE_GROUP_ID = os.getenv("SCHEMAFLOW_TRACE_GROUP_ID", "schemaflow-cookbook-promptfoo")


def _version_tuple(value):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


try:
    AGENTS_SDK_VERSION = version("openai-agents")
except PackageNotFoundError as exc:
    raise RuntimeError('Install the OpenAI Agents SDK: pip install -U "openai-agents>=0.17.0"') from exc
if _version_tuple(AGENTS_SDK_VERSION) < _version_tuple(MIN_AGENTS_SDK_VERSION):
    raise RuntimeError(f"OpenAI Agents SDK {MIN_AGENTS_SDK_VERSION}+ is required; found {AGENTS_SDK_VERSION}.")


class SchemaFlowBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class OperationModel(SchemaFlowBaseModel):
    op: str
    details: dict = Field(default_factory=dict)


class ChangeRequestModel(SchemaFlowBaseModel):
    title: str | None = None
    domain: str | None = None
    target_schema: str | None = None
    target_table: str | None = None
    operations: list[OperationModel] = Field(default_factory=list)
    notes: list = Field(default_factory=list)


class ImpactObjectModel(SchemaFlowBaseModel):
    type: str
    name: str
    reason: str
    source: str


class ImpactModel(SchemaFlowBaseModel):
    impacted_objects: list[ImpactObjectModel] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


class PlanStepModel(SchemaFlowBaseModel):
    id: str
    description: str


class PlanModel(SchemaFlowBaseModel):
    plan_steps: list[PlanStepModel] = Field(default_factory=list)
    prechecks: list[str] = Field(default_factory=list)
    postchecks: list[str] = Field(default_factory=list)
    rollback: list[str] = Field(default_factory=list)


CHANGE_OUTPUT_SCHEMA = AgentOutputSchema(ChangeRequestModel, strict_json_schema=False)
IMPACT_OUTPUT_SCHEMA = AgentOutputSchema(ImpactModel, strict_json_schema=False)
PLAN_OUTPUT_SCHEMA = AgentOutputSchema(PlanModel, strict_json_schema=False)


def _clean_openai_api_key(value):
    key = (value or "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is required for SchemaFlow evals")
    return key


def _ensure_openai_api_key(api_key=None):
    if api_key is not None:
        os.environ["OPENAI_API_KEY"] = _clean_openai_api_key(api_key)
    else:
        os.environ["OPENAI_API_KEY"] = _clean_openai_api_key(os.getenv("OPENAI_API_KEY"))
    org_id = os.getenv("OPENAI_ORG_ID", "").strip()
    if org_id:
        os.environ["OPENAI_ORG_ID"] = org_id


def _get_client(api_key=None):
    _ensure_openai_api_key(api_key)
    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _parse_json_text(text):
    text = (text or "{}").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _model_dump(value):
    if value is None or isinstance(value, (str, int, float, bool, bytes)):
        return value
    if isinstance(value, type):
        return value
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump()
        except TypeError:
            pass
    if hasattr(value, "to_dict"):
        try:
            return value.to_dict()
        except TypeError:
            pass
    if hasattr(value, "__dict__"):
        try:
            return {k: v for k, v in vars(value).items() if not k.startswith("_")}
        except TypeError:
            pass
    return value


def _agent_output_to_json(value):
    value = _model_dump(value)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return _parse_json_text(value)
    return json.loads(json.dumps(value, default=str))


def _agent_output_to_text(value):
    value = _model_dump(value)
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _trace_metadata(metadata=None):
    cleaned = {}
    for key, value in (metadata or {}).items():
        if value is None:
            cleaned[str(key)] = ""
        elif isinstance(value, bool):
            cleaned[str(key)] = "true" if value else "false"
        elif isinstance(value, (dict, list, tuple, set)):
            cleaned[str(key)] = json.dumps(value, ensure_ascii=False, default=str)
        else:
            cleaned[str(key)] = str(value)
    return cleaned


def _schemaflow_run_config(workflow_name, metadata=None):
    return RunConfig(
        workflow_name=workflow_name,
        group_id=SCHEMAFLOW_TRACE_GROUP_ID,
        trace_include_sensitive_data=TRACE_INCLUDE_SENSITIVE_DATA,
        trace_metadata=_trace_metadata({"runtime": "promptfoo", **(metadata or {})}),
    )


def _runner_run_sync(agent, prompt, *, workflow_name, metadata=None, max_turns=4):
    kwargs = {"run_config": _schemaflow_run_config(workflow_name, metadata), "max_turns": max_turns}
    try:
        return Runner.run_sync(agent, prompt, **kwargs)
    except RuntimeError as exc:
        if "event loop" not in str(exc).lower():
            raise
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: Runner.run_sync(agent, prompt, **kwargs)).result()


def run_schemaflow_json_agent(*, name, instructions, prompt, output_schema, model=None, tools=None, workflow_name=None, metadata=None):
    agent = Agent(name=name, instructions=instructions, model=model or MODEL, output_type=output_schema, tools=tools or [])
    result = _runner_run_sync(agent, prompt, workflow_name=workflow_name or name, metadata={"agent": name, **(metadata or {})})
    return _agent_output_to_json(result.final_output), result


def run_schemaflow_text_agent(*, name, instructions, prompt, model=None, tools=None, workflow_name=None, metadata=None):
    agent = Agent(name=name, instructions=instructions, model=model or MODEL, tools=tools or [])
    result = _runner_run_sync(agent, prompt, workflow_name=workflow_name or name, metadata={"agent": name, **(metadata or {})})
    return _agent_output_to_text(result.final_output), result


def trace_function_result(name, *, input_obj=None, output_obj=None):
    with function_span(
        name,
        input=json.dumps(input_obj, ensure_ascii=False, default=str) if input_obj is not None else None,
        output=json.dumps(output_obj, ensure_ascii=False, default=str) if output_obj is not None else None,
    ):
        pass


def _collect_file_search_results(value):
    results = []
    seen = set()

    def visit(node):
        if node is None or isinstance(node, (str, int, float, bool, bytes)):
            return
        if isinstance(node, type) or callable(node):
            return
        node_id = id(node)
        if node_id in seen:
            return
        seen.add(node_id)

        node = _model_dump(node)
        if node is None or isinstance(node, (str, int, float, bool, bytes)):
            return
        if isinstance(node, type) or callable(node):
            return

        if isinstance(node, dict):
            if node.get("type") == "file_search_call":
                for result in node.get("results", []) or []:
                    result = _model_dump(result)
                    if isinstance(result, dict):
                        text = result.get("text") or result.get("content") or ""
                        if isinstance(text, list):
                            text = "\n".join(str(x) for x in text)
                        results.append({"file_id": result.get("file_id"), "filename": result.get("filename") or result.get("file_name") or result.get("title"), "score": result.get("score"), "text_preview": str(text)[:1200]})
            for child in node.values():
                visit(child)
        elif isinstance(node, (list, tuple, set)):
            for child in node:
                visit(child)

    visit(value)
    return results


def normalize_change(change_json):
    if not isinstance(change_json, dict):
        change_json = {}
    change_json.setdefault("title", None)
    change_json.setdefault("domain", None)
    change_json.setdefault("target_schema", None)
    change_json.setdefault("target_table", None)
    if not isinstance(change_json.get("operations"), list):
        change_json["operations"] = [change_json.get("operations")] if change_json.get("operations") else []
    if not isinstance(change_json.get("notes"), list):
        change_json["notes"] = []
    return change_json


def parse_change(change_text, model=None):
    change_json, _ = run_schemaflow_json_agent(
        name="SchemaFlow Parse Agent",
        instructions=PARSE_SYSTEM,
        prompt="Change Request:\n\n" + change_text,
        output_schema=CHANGE_OUTPUT_SCHEMA,
        model=model,
        workflow_name="SchemaFlow Eval Parse",
        metadata={"eval_stage": "parse"},
    )
    return normalize_change(change_json)


def run_schemaflow_parse(change_text, *, model=None, api_key=None):
    _ensure_openai_api_key(api_key)
    with custom_span("SchemaFlow Promptfoo Parse Eval", {"eval_mode": "parse_only", "group_id": SCHEMAFLOW_TRACE_GROUP_ID}):
        try:
            change_json = parse_change(change_text, model=model)
            bundle = {"eval_mode": "parse_only", "change_text": change_text, "change_json": change_json, "validation": {"valid": True, "issues": []}}
            trace_function_result("Promptfoo parse bundle", input_obj={"change_text": change_text}, output_obj=bundle)
            return bundle
        finally:
            flush_traces()


def normalize_impact(impact_json):
    if not isinstance(impact_json, dict):
        impact_json = {}
    impact_json.setdefault("impacted_objects", [])
    impact_json.setdefault("risks", [])
    impact_json.setdefault("assumptions", [])
    return impact_json


def normalize_plan(plan_json):
    if not isinstance(plan_json, dict):
        plan_json = {}
    plan_json.setdefault("plan_steps", [])
    plan_json.setdefault("prechecks", [])
    plan_json.setdefault("postchecks", [])
    plan_json.setdefault("rollback", [])
    return plan_json


def resolve_eval_pdf_path(pdf_path):
    requested = Path(pdf_path).expanduser()
    module_dir = Path(__file__).resolve().parent
    candidates = [requested]
    if not requested.is_absolute():
        candidates.extend([
            module_dir / requested,
            module_dir.parent / requested,
            module_dir.parent.parent / requested,
        ])
    resolved_candidates = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in resolved_candidates:
            continue
        resolved_candidates.append(resolved)
        if resolved.exists():
            return resolved
    attempted = ", ".join(str(candidate) for candidate in resolved_candidates)
    raise FileNotFoundError(f"PDF not found: {pdf_path}. Tried: {attempted}")


def create_pdf_vector_store(client, pdf_path, name_prefix="schemaflow-cookbook"):
    pdf_path = resolve_eval_pdf_path(pdf_path)
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {pdf_path}")
    with custom_span("Promptfoo create vector store", {"pdf_path": str(pdf_path)}):
        vector_store = client.vector_stores.create(name=f"{name_prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}", expires_after={"anchor": "last_active_at", "days": 1})
    with custom_span("Promptfoo upload PDF to vector store", {"vector_store_id": vector_store.id, "pdf_path": str(pdf_path)}):
        with pdf_path.open("rb") as handle:
            vector_store_file = client.vector_stores.files.upload_and_poll(vector_store_id=vector_store.id, file=handle)
    trace_function_result("Promptfoo vector store ready", input_obj={"pdf_path": str(pdf_path)}, output_obj={"vector_store_id": vector_store.id, "status": getattr(vector_store_file, "status", "unknown")})
    return vector_store, vector_store_file


def delete_vector_store(client, vector_store_id):
    if not vector_store_id:
        return
    try:
        with custom_span("Promptfoo delete vector store", {"vector_store_id": vector_store_id}):
            client.vector_stores.delete(vector_store_id=vector_store_id)
    except Exception:
        pass


def validate_sql(sql_text, required_keywords=None):
    issues = []
    if not (sql_text or "").strip():
        issues.append("SQL output is empty")
    for keyword in required_keywords or ["ALTER TABLE"]:
        if keyword.lower() not in (sql_text or "").lower():
            issues.append(f"Expected keyword missing: {keyword}")
    validation = {"valid": len(issues) == 0, "issues": issues}
    with guardrail_span("promptfoo_sql_validation", triggered=not validation["valid"]):
        trace_function_result("Promptfoo SQL validation", output_obj=validation)
    return validation


def run_schemaflow_case(change_text, *, pdf_path=None, rag_max_results=6, model=None, api_key=None, validation_keywords=None, delete_vector_store_after_run=True):
    client = _get_client(api_key=api_key)
    vector_store_id = None
    rag_file_search_results = []
    with custom_span("SchemaFlow Promptfoo Full Flow Eval", {"eval_mode": "full_flow", "pdf_path": pdf_path or "", "group_id": SCHEMAFLOW_TRACE_GROUP_ID}):
        try:
            change_json = parse_change(change_text, model=model)
            impact_user_parts = ["CHANGE_JSON:\n" + json.dumps(change_json, ensure_ascii=False)]
            impact_tools = []
            if pdf_path:
                vector_store, _ = create_pdf_vector_store(client, pdf_path, name_prefix="schemaflow-promptfoo")
                vector_store_id = vector_store.id
                impact_tools.append(FileSearchTool(vector_store_ids=[vector_store_id], max_num_results=rag_max_results, include_search_results=True))
                impact_user_parts.append("Use the file_search tool against the uploaded PDF to look for relevant IFD, schema, table, column, lineage, and downstream dependency context before returning JSON.")
            impact_json, impact_result = run_schemaflow_json_agent(name="SchemaFlow Impact Agent", instructions=IMPACT_SYSTEM, prompt="\n\n".join(impact_user_parts), output_schema=IMPACT_OUTPUT_SCHEMA, model=model, tools=impact_tools, workflow_name="SchemaFlow Eval Impact", metadata={"eval_stage": "impact", "rag_enabled": bool(vector_store_id)})
            impact_json = normalize_impact(impact_json)
            try:
                rag_file_search_results = _collect_file_search_results(impact_result)
            except Exception as exc:
                rag_file_search_results = []
                trace_function_result("Promptfoo File Search summary skipped", output_obj={"error": f"{type(exc).__name__}: {exc}"})
            plan_user = "\n\n".join(["CHANGE_JSON:\n" + json.dumps(change_json, ensure_ascii=False), "IMPACT_JSON:\n" + json.dumps(impact_json, ensure_ascii=False)])
            plan_json, _ = run_schemaflow_json_agent(name="SchemaFlow Plan Agent", instructions=PLAN_SYSTEM, prompt=plan_user, output_schema=PLAN_OUTPUT_SCHEMA, model=model, workflow_name="SchemaFlow Eval Plan", metadata={"eval_stage": "plan"})
            plan_json = normalize_plan(plan_json)
            sql_user = "\n\n".join(["CHANGE_JSON:\n" + json.dumps(change_json, ensure_ascii=False), "PLAN_JSON:\n" + json.dumps(plan_json, ensure_ascii=False)])
            sql_text, _ = run_schemaflow_text_agent(name="SchemaFlow SQL Agent", instructions=SQL_SYSTEM, prompt=sql_user, model=model, workflow_name="SchemaFlow Eval SQL", metadata={"eval_stage": "sql"})
            validation = validate_sql(sql_text, required_keywords=validation_keywords)
            bundle = {"summary": {"matched_tables": [], "impact_risks": impact_json.get("risks", []), "rag_hits": len(rag_file_search_results)}, "rag": {"enabled": bool(vector_store_id), "vector_store_id": vector_store_id, "hits": len(rag_file_search_results), "file_search_results": rag_file_search_results}, "change_json": change_json, "impact_json": impact_json, "plan": plan_json, "sql": sql_text, "validation": validation}
            trace_function_result("Promptfoo full-flow bundle", input_obj={"change_text": change_text}, output_obj=bundle)
            return bundle
        finally:
            if delete_vector_store_after_run:
                delete_vector_store(client, vector_store_id)
            flush_traces()
'''

core_module = (CORE_MODULE_TEMPLATE
    .replace("__MODEL_DEFAULT__", repr(MODEL))
    .replace("__PARSE_SYSTEM__", repr(PARSE_SYSTEM))
    .replace("__IMPACT_SYSTEM__", repr(IMPACT_SYSTEM))
    .replace("__PLAN_SYSTEM__", repr(PLAN_SYSTEM))
    .replace("__SQL_SYSTEM__", repr(SQL_SYSTEM)))
core_path = PROMPTFOO_DIR / "schemaflow_cookbook_core.py"
core_path.write_text(core_module, encoding="utf-8")
print("Published SchemaFlow core:", core_path.resolve())
````

<a id="promptfoo-provider-runtime"></a>

---

### Promptfoo Provider Runtime

這個 cell 寫出 Promptfoo 的 provider 檔：

```text
artifacts/promptfoo/schemaflow_cookbook_eval_provider.py
```

provider 是 Promptfoo 和 SchemaFlow 之間的橋樑。

對每個 Promptfoo 測試案例，它會讀這些變數：

- `change_text`
- `eval_mode`
- 選配的 `pdf_path`
- 選配的 `rag_max_results`
- 驗證用的關鍵字

然後選擇兩條執行路徑之一：

- `parse_only` 只跑 Stage 1，回傳 parse bundle。
- `full_flow` 跑完整的 SchemaFlow pipeline，回傳完整的 bundle。

provider 回傳 JSON，讓 Promptfoo assertion 可以直接檢查結構化欄位，不用去解析 notebook 的文字輸出。

```python
%%writefile artifacts/promptfoo/schemaflow_cookbook_eval_provider.py
import json
import os
from agents import flush_traces, function_span, trace
from schemaflow_cookbook_core import run_schemaflow_case, run_schemaflow_parse
SCHEMAFLOW_TRACE_GROUP_ID = os.getenv("SCHEMAFLOW_TRACE_GROUP_ID", "schemaflow-cookbook-promptfoo")

def _json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return [value]
    return parsed if isinstance(parsed, list) else [parsed]

def _trace_function_result(name, *, input_obj=None, output_obj=None):
    with function_span(name, input=json.dumps(input_obj, ensure_ascii=False, default=str) if input_obj is not None else None, output=json.dumps(output_obj, ensure_ascii=False, default=str) if output_obj is not None else None):
        pass

def call_api(prompt, options, context):
    vars_ = (context or {}).get("vars", {})
    change_text = vars_.get("change_text") or prompt
    eval_mode = vars_.get("eval_mode", "full_flow")
    with trace("SchemaFlow Promptfoo Provider", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"eval_mode": eval_mode}):
        try:
            if eval_mode == "parse_only":
                bundle = run_schemaflow_parse(change_text)
            elif eval_mode == "full_flow":
                bundle = run_schemaflow_case(change_text, pdf_path=vars_.get("pdf_path"), rag_max_results=int(vars_.get("rag_max_results") or 6), validation_keywords=_json_list(vars_.get("validation_keywords_json")))
                bundle["eval_mode"] = "full_flow"
            else:
                raise ValueError(f"Unsupported eval_mode: {eval_mode}")
            _trace_function_result("Promptfoo provider output", input_obj={"eval_mode": eval_mode, "change_text": change_text, "vars": vars_}, output_obj=bundle)
            return {"output": json.dumps(bundle, ensure_ascii=False)}
        finally:
            flush_traces()
```

<a id="promptfoo-assertion-runtime"></a>

---

### Promptfoo Assertion Runtime

這個 cell 寫出 Promptfoo 的 assertion 檔：

```text
artifacts/promptfoo/schemaflow_cookbook_eval_assert.py
```

assertion 檔對兩種 eval 模式的 provider 輸出做驗證。

對 `parse_only`，它檢查：

- 輸出是合法的 JSON
- target schema 和 table 符合預期
- 至少有一個解析出的 operation
- 預期新增的 column 有出現在解析出的 operations 裡
- 預期的資料型別以結構化的方式出現在解析出的 operations 裡

對 `full_flow`，它檢查：

- 輸出是合法的 JSON
- target schema 和 table 符合預期
- 至少有一個解析出的 operation
- 有 impact 風險
- 有必要的 SQL 詞彙
- 驗證通過

assertion 也會送出 guardrail span，讓 eval 失敗在 trace 裡看得到。

```python
%%writefile artifacts/promptfoo/schemaflow_cookbook_eval_assert.py
import json
import os
import re
from agents import flush_traces, function_span, guardrail_span, trace
SCHEMAFLOW_TRACE_GROUP_ID = os.getenv("SCHEMAFLOW_TRACE_GROUP_ID", "schemaflow-cookbook-promptfoo")

def _json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return [value]
    return parsed if isinstance(parsed, list) else [parsed]

def _normalize_name(value):
    return (value or "").replace('"', "").replace("'", "").strip().upper()

def _normalize_text(value):
    return " ".join(str(value or "").upper().replace('"', "").replace("'", "").split())

def _compact_text(value):
    return re.sub(r"\s+", "", _normalize_text(value))

def _operation_text(bundle):
    operations = bundle.get("change_json", {}).get("operations", [])
    return _normalize_text(json.dumps(operations, ensure_ascii=False))

def _trace_function_result(name, *, input_obj=None, output_obj=None):
    with function_span(name, input=json.dumps(input_obj, ensure_ascii=False, default=str) if input_obj is not None else None, output=json.dumps(output_obj, ensure_ascii=False, default=str) if output_obj is not None else None):
        pass

def _check_target(bundle, expected_schema, expected_table):
    if not expected_schema or not expected_table:
        return True, "target expectation not configured"
    change = bundle.get("change_json", {})
    actual_schema = _normalize_name(change.get("target_schema"))
    actual_table = _normalize_name(change.get("target_table"))
    return actual_schema == _normalize_name(expected_schema) and actual_table == _normalize_name(expected_table), f"expected target {_normalize_name(expected_schema)}.{_normalize_name(expected_table)}, got {actual_schema}.{actual_table}"

def _check_expected_text(bundle, value, label):
    if not value:
        return True, f"{label} expectation not configured"
    haystack = _operation_text(bundle)
    needle = _normalize_text(value)
    return needle in haystack, f"expected parsed {label} {needle} in operations"

def _check_expected_data_type(bundle, value):
    if not value:
        return True, "data type expectation not configured"
    haystack = _operation_text(bundle)
    compact_haystack = _compact_text(haystack)
    compact_needle = _compact_text(value)
    if compact_needle in compact_haystack:
        return True, "data type matched"
    match = re.match(r"([A-Z]+)\(?([0-9,]*)\)?", compact_needle)
    if not match:
        return False, f"expected parsed data type {value} in operations"
    base_type, size = match.groups()
    if base_type and base_type not in compact_haystack:
        return False, f"expected parsed data type base {base_type} in operations"
    if size:
        missing_sizes = [part for part in size.split(",") if part and part not in compact_haystack]
        if missing_sizes:
            return False, f"expected parsed data type size {size} in operations"
    return True, "data type matched structurally"

def get_assert(output, context):
    vars_ = (context or {}).get("vars", {})
    eval_mode = vars_.get("eval_mode", "full_flow")
    with trace("SchemaFlow Promptfoo Assertion", group_id=SCHEMAFLOW_TRACE_GROUP_ID, metadata={"eval_mode": eval_mode}):
        try:
            try:
                bundle = json.loads(output)
            except Exception as exc:
                result = {"pass": False, "score": 0, "reason": f"Provider output was not JSON: {exc}"}
                with guardrail_span("provider_output_json", triggered=True):
                    _trace_function_result("Promptfoo assertion parse failure", input_obj={"output": output}, output_obj=result)
                return result
            checks = []
            ok, reason = _check_target(bundle, vars_.get("expected_schema"), vars_.get("expected_table"))
            checks.append(("target_matches_expected", ok, reason))
            operations = bundle.get("change_json", {}).get("operations", [])
            checks.append(("parsed_operation_present", isinstance(operations, list) and len(operations) > 0, "expected at least one parsed operation"))
            if eval_mode == "parse_only":
                ok, reason = _check_expected_text(bundle, vars_.get("expected_added_column"), "added column")
                checks.append(("expected_added_column", ok, reason))
                ok, reason = _check_expected_data_type(bundle, vars_.get("expected_data_type"))
                checks.append(("expected_data_type", ok, reason))
            else:
                risks = bundle.get("impact_json", {}).get("risks", [])
                checks.append(("impact_risks_present", isinstance(risks, list) and len(risks) > 0, "expected at least one impact risk"))
                sql_text = bundle.get("sql") or bundle.get("sql_text") or ""
                missing_terms = [term for term in _json_list(vars_.get("sql_terms_json")) if term.lower() not in sql_text.lower()]
                checks.append(("sql_terms_present", not missing_terms, "missing SQL terms: " + ", ".join(missing_terms)))
                validation = bundle.get("validation", {})
                checks.append(("validation_passed", bool(validation.get("valid")), "validation issues: " + "; ".join(validation.get("issues", []))))
            for name, ok, reason in checks:
                with guardrail_span(name, triggered=not ok):
                    _trace_function_result("Promptfoo assertion check", output_obj={"name": name, "ok": ok, "reason": reason})
            passed = [ok for _, ok, _ in checks if ok]
            failures = [reason for _, ok, reason in checks if not ok]
            score = len(passed) / len(checks) if checks else 0
            result = {"pass": score == 1, "score": score, "reason": "All checks passed" if not failures else "; ".join(failures)}
            _trace_function_result("Promptfoo assertion result", input_obj={"vars": vars_}, output_obj=result)
            return result
        finally:
            flush_traces()
```

<a id="build-promptfoo-test-cases-and-config"></a>

---

### 建立 Promptfoo 測試案例與 Config

這個 cell 從目前 notebook 的輸入建立 Promptfoo 測試案例。

預設會從目前的 `CHANGE_TEXT` 建兩個測試案例，若有設定 PDF 也會帶上 `PDF_PATH`：

1. 一個 parse-only 測試
2. 一個 full-flow 測試

helper 函式會從變更需求推出預期值，包括：

- 預期的 schema
- 預期的 table
- 預期新增的 column
- 預期的資料型別
- 預期的 SQL 詞彙
- 預期的驗證關鍵字

這個 cell 也包含選配的 regression fixture。設定：

```python
RUN_EXTRA_REGRESSION_CASES = True
```

就能把這些額外的案例加進產生的 config。

在寫出 `promptfooconfig.yaml` 之前，這個 cell 會先跑確定性的 input preflight 檢查。這樣可以避免明顯格式錯誤的 eval 輸入，造成讓人困惑的 Promptfoo 失敗。

```python
import json
import re
import sys
from pathlib import Path


def infer_eval_expectations(change_text):
    target_match = re.search(
        r"\b(?:to|from|in|on)\s+([A-Za-z_][\w$]*)\.([A-Za-z_][\w$]*)",
        change_text,
        flags=re.IGNORECASE,
    )
    column_type_match = re.search(
        r"\badd\s+([A-Za-z_][\w$]*)\s+((?:VAR)?CHAR\s*\([^)]*\)|TEXT|INTEGER|INT|BIGINT|BOOLEAN|DATE|TIMESTAMP|NUMERIC\s*\([^)]*\)|DECIMAL\s*\([^)]*\)|FLOAT|DOUBLE)",
        change_text,
        flags=re.IGNORECASE,
    )

    expected_schema = target_match.group(1).upper() if target_match else None
    expected_table = target_match.group(2).upper() if target_match else None
    added_column = column_type_match.group(1).upper() if column_type_match else None
    data_type = " ".join(column_type_match.group(2).upper().split()) if column_type_match else None

    sql_terms = []
    validation_keywords = ["ALTER TABLE"]
    if expected_table:
        sql_terms.append(expected_table)
    if added_column:
        sql_terms.append(added_column)
    if data_type:
        sql_terms.append(data_type)
    sql_terms.append("ALTER TABLE")

    lower_text = change_text.lower()
    if any(term in lower_text for term in ["backfill", "update", "source it from"]):
        sql_terms.append("UPDATE")
        validation_keywords.append("UPDATE")
    if "index" in lower_text:
        sql_terms.append("CREATE INDEX")
        validation_keywords.append("CREATE INDEX")

    return {
        "expected_schema": expected_schema,
        "expected_table": expected_table,
        "expected_added_column": added_column,
        "expected_data_type": data_type,
        "sql_terms": list(dict.fromkeys(sql_terms)),
        "validation_keywords": list(dict.fromkeys(validation_keywords)),
    }


def build_eval_case(description, change_text, **overrides):
    expectations = infer_eval_expectations(change_text)
    vars_ = {
        "change_text": change_text,
        "sql_terms_json": json.dumps(expectations["sql_terms"], ensure_ascii=False),
        "validation_keywords_json": json.dumps(expectations["validation_keywords"], ensure_ascii=False),
    }
    for key in ["expected_schema", "expected_table", "expected_added_column", "expected_data_type"]:
        if expectations.get(key):
            vars_[key] = expectations[key]
    vars_.update({k: v for k, v in overrides.items() if v is not None})
    return {"description": description, "vars": vars_}


def _json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    parsed = json.loads(value)
    return parsed if isinstance(parsed, list) else [parsed]


def preflight_eval_case(case):
    vars_ = case["vars"]
    errors = []
    warnings = []
    change_text = vars_.get("change_text", "")
    sql_terms = _json_list(vars_.get("sql_terms_json"))

    if len(change_text.strip()) < 20:
        errors.append("change_text is missing or too short")
    if not vars_.get("expected_schema") or not vars_.get("expected_table"):
        errors.append("could not infer target schema/table")
    if not vars_.get("expected_added_column"):
        warnings.append("could not infer added column")
    if not vars_.get("expected_data_type"):
        warnings.append("could not infer added column data type")
    if len(sql_terms) <= 1:
        warnings.append("few SQL terms inferred")
    if vars_.get("pdf_path"):
        pdf_path = Path(vars_["pdf_path"]).expanduser()
        if not pdf_path.exists():
            errors.append(f"pdf_path does not exist: {pdf_path}")
        elif pdf_path.suffix.lower() != ".pdf":
            errors.append(f"pdf_path is not a PDF: {pdf_path}")

    return {"description": case["description"], "errors": errors, "warnings": warnings}


def as_promptfoo_test(case, eval_mode):
    vars_ = dict(case["vars"])
    vars_["eval_mode"] = eval_mode
    label = "Parse-only" if eval_mode == "parse_only" else "Full flow"
    return {"description": f"{label}: {case['description']}", "vars": vars_}


CURRENT_NOTEBOOK_EVAL_CASE = build_eval_case(
    "Current notebook change request",
    CHANGE_TEXT,
    pdf_path=str(Path(PDF_PATH).expanduser().resolve()) if PDF_PATH else None,
)

RUN_EXTRA_REGRESSION_CASES = False

EXTRA_REGRESSION_CASES = [
    build_eval_case(
        "Product style color propagation",
        """Add COLOR_CODE VARCHAR(10) to ODS.ODS_PLIM_STYLE as nullable.
Source it from FLEX.STYLE.COLOR_CODE when available and propagate the field through staging and mart outputs used by product reporting.""",
    ),
    build_eval_case(
        "Optional customer note field",
        """Add CUSTOMER_SEGMENT_NOTE VARCHAR(255) to ODS.ODS_CUSTOMER_PROFILE as nullable.
No historical backfill is required. The field is optional metadata for analyst annotations and should not block existing loads.""",
    ),
]

ADDITIONAL_EVAL_CASES = EXTRA_REGRESSION_CASES if RUN_EXTRA_REGRESSION_CASES else []
INPUT_EVAL_CASES = [CURRENT_NOTEBOOK_EVAL_CASE, *ADDITIONAL_EVAL_CASES]
INPUT_PREFLIGHT_RESULTS = [preflight_eval_case(case) for case in INPUT_EVAL_CASES]
INPUT_PREFLIGHT_ERRORS = [
    f"{result['description']}: {error}"
    for result in INPUT_PREFLIGHT_RESULTS
    for error in result["errors"]
]

print("Input preflight:")
for result in INPUT_PREFLIGHT_RESULTS:
    status = "PASS" if not result["errors"] else "FAIL"
    print(f"- {status}: {result['description']}")
    for warning in result["warnings"]:
        print(f"  warning: {warning}")
    for error in result["errors"]:
        print(f"  error: {error}")
if INPUT_PREFLIGHT_ERRORS:
    raise ValueError("Input preflight failed:\n" + "\n".join(INPUT_PREFLIGHT_ERRORS))

PROMPTFOO_PARSE_EVAL_CASES = [as_promptfoo_test(case, "parse_only") for case in INPUT_EVAL_CASES]
PROMPTFOO_FULL_FLOW_EVAL_CASES = [as_promptfoo_test(case, "full_flow") for case in INPUT_EVAL_CASES]
PROMPTFOO_EVAL_CASES = [*PROMPTFOO_PARSE_EVAL_CASES, *PROMPTFOO_FULL_FLOW_EVAL_CASES]

promptfoo_config = {
    "description": "SchemaFlow cookbook evals",
    "prompts": ["{{change_text}}"],
    "providers": [{
        "id": "file://schemaflow_cookbook_eval_provider.py",
        "config": {"pythonExecutable": sys.executable},
    }],
    "defaultTest": {
        "assert": [{
            "type": "python",
            "value": "file://schemaflow_cookbook_eval_assert.py",
        }],
    },
    "tests": PROMPTFOO_EVAL_CASES,
}

config_path = PROMPTFOO_DIR / "promptfooconfig.yaml"
config_text = "# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json\n" + json.dumps(
    promptfoo_config,
    indent=2,
    ensure_ascii=False,
)
config_path.write_text(config_text, encoding="utf-8")

print("Promptfoo config:", config_path.resolve())
print("Promptfoo Python executable:", sys.executable)
print("Promptfoo eval cases:", len(PROMPTFOO_EVAL_CASES))
for case in PROMPTFOO_EVAL_CASES:
    vars_ = case["vars"]
    target = ".".join(part for part in [vars_.get("expected_schema"), vars_.get("expected_table")] if part)
    print("-", case["description"], "->", target or "target not inferred")
```

<a id="run-promptfoo-eval"></a>

---

### 執行 Promptfoo Eval

這個 cell 從 notebook 以非互動的方式執行 Promptfoo。這個指令：

- 在 `artifacts/promptfoo/` 底下執行
- 使用產生出來的 `promptfooconfig.yaml`
- 使用 notebook 本機的 Promptfoo config、cache、log 和 npm cache
- 以 concurrency `1` 執行，讓 notebook 的行為可預測
- 讓 CLI 輸出留在 notebook 裡看得到
- 寫出帶時間戳的 JSON 和 HTML 報告
- 成功執行後更新 latest 別名檔

匯出的結果檔存放在：

```text
artifacts/promptfoo/results/
```

如果前面的 Node.js/npm runtime 檢查失敗，請先修好 runtime 再跑這個 cell。

```python
%%bash
set -euo pipefail
cd artifacts/promptfoo
export PROMPTFOO_CONFIG_DIR="$PWD/.promptfoo"
export PROMPTFOO_LOG_DIR="$PWD/.promptfoo/logs"
export PROMPTFOO_CACHE_PATH="$PWD/.promptfoo/cache"
export npm_config_cache="$PWD/.npm-cache"
export npm_config_update_notifier=false
export npm_config_loglevel=error
export SCHEMAFLOW_TRACE_GROUP_ID="${SCHEMAFLOW_TRACE_GROUP_ID:-schemaflow-cookbook-promptfoo}"
export OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA="${OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA:-false}"
mkdir -p "$PROMPTFOO_LOG_DIR" "$PROMPTFOO_CACHE_PATH" results
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
RESULT_JSON="results/schemaflow_cookbook_eval_${RUN_ID}.json"
RESULT_HTML="results/schemaflow_cookbook_eval_${RUN_ID}.html"
npx --yes promptfoo@latest eval \
  -c promptfooconfig.yaml \
  --max-concurrency 1 \
  --no-progress-bar \
  --description "SchemaFlow cookbook eval ${RUN_ID}" \
  -o "$RESULT_JSON" "$RESULT_HTML"
cp "$RESULT_JSON" results/schemaflow_cookbook_eval_latest.json
cp "$RESULT_HTML" results/schemaflow_cookbook_eval_latest.html
printf '\nSaved Promptfoo results:\n  %s\n  %s\n' "$RESULT_JSON" "$RESULT_HTML"
printf 'Latest aliases:\n  %s\n  %s\n' "results/schemaflow_cookbook_eval_latest.json" "results/schemaflow_cookbook_eval_latest.html"
printf 'Trace group:\n  %s\n' "$SCHEMAFLOW_TRACE_GROUP_ID"
```

<a id="review-latest-promptfoo-results"></a>

---

### 檢視最新的 Promptfoo 結果

這個 cell 檢查最新的 Promptfoo 結果別名檔是否存在，並印出它們的路徑和大小。

預期的檔案：

```text
artifacts/promptfoo/results/schemaflow_cookbook_eval_latest.json
artifacts/promptfoo/results/schemaflow_cookbook_eval_latest.html
```

如果最新的 JSON 檔存在，這個 cell 也會印出可用的 eval metadata，例如 eval ID 和彙總統計。

這一節可以拿來快速確認 eval 已完成，而且結果檔已成功匯出。

```python
from pathlib import Path
import json

results_dir = Path("artifacts/promptfoo/results")
latest_json = results_dir / "schemaflow_cookbook_eval_latest.json"
latest_html = results_dir / "schemaflow_cookbook_eval_latest.html"

for path in (latest_json, latest_html):
    if path.exists():
        print(f"{path.name}: {path.resolve()} ({path.stat().st_size:,} bytes)")
    else:
        print(f"Missing expected Promptfoo result: {path.resolve()}")

if latest_json.exists():
    data = json.loads(latest_json.read_text())
    eval_id = data.get("evalId")
    results = data.get("results", {})
    stats = results.get("stats", {}) if isinstance(results, dict) else {}
    if eval_id:
        print("Eval ID:", eval_id)
    if stats:
        print("Stats:", stats)
```

## 11) 選配：Neo4j 知識圖譜與儀表板

這個選配區段**完全自給自足**，而且**不影響上面的核心 pipeline**。它用一個小型的合成客戶 loyalty 圖譜 seed，加上內嵌的儀表板程式碼，讓 cookbook 保持可攜。你可以把它當成視覺化的附錄：沒有 Neo4j 核心流程照樣能跑，但圖形檢視能讓 lineage 和下游影響更容易檢查。

**這一節依序做的事：**

1. **Step 1 - Seed**：用內嵌的 Python 資料結構，定義一個合成的客戶 loyalty 圖譜，包含 ODS、staging、core、mart 和 CRM 物件、它們的欄位、lineage 和 join，不需要外部檔案。
2. **Step 2 - AI Enrichment**：用第 1 節已載入的 OpenAI `client`，為每個欄位填上 `semantic_meaning`（2-5 個字的簡短標籤，例如 `natural-key`、`foreign-key`、`monetary-amount`、`timestamp`）。
3. **Step 3 - Upsert 到 Neo4j**：用 idempotent 的 `MERGE` Cypher，把豐富化後的資料寫進跑著的 Neo4j。節點會標上 `SchemaFlowCookbook` label，讓儀表板忽略舊的本機範例資料。
4. **Dashboard**：在 notebook 旁邊寫一個小的 FastAPI server 加 D3.js 頁面，在 `http://127.0.0.1:8005` 啟動，並印出可點擊的連結。

**這一節的前置條件：**

- 一個跑著的 Neo4j，例如用 Docker：`docker run -d -p 7687:7687 -p 7474:7474 -e NEO4J_AUTH=neo4j/change-me-please neo4j:5`（Neo4j Desktop 或 AuraDB 免費方案也可以）。
- `NEO4J_URI`、`NEO4J_USER`、`NEO4J_PASSWORD`（從環境變數載入，或在下面的提示輸入）。
- 儀表板用的一個空閒本機 port `8005`（可用 `NEO4J_DASHBOARD_PORT` 覆寫）。
- 選配套件 `neo4j`、`fastapi`、`uvicorn`，缺的話下一個 cell 會按需安裝。

如果缺少任何前置條件，下面每個 cell 都會直接跳過並顯示清楚的訊息，不會丟例外，notebook 其他部分不受影響。


### 11.1) 環境設定與選配相依套件

沿用第 1 節載入 OpenAI 環境的做法。只有在 `neo4j`、`fastapi`、`uvicorn` 無法 import 時才會按需安裝，然後從環境變數讀 `NEO4J_URI`、`NEO4J_USER` 和 `NEO4J_PASSWORD`（缺的話用 `getpass` 提示輸入）。任何提示如果直接按 Enter 不輸入，這一節就會停用（`NEO4J_SECTION_ENABLED = False`），後面的 cell 會乾淨地跳過。

```python
import os
import subprocess
import sys
from getpass import getpass
from urllib.parse import urlparse

NEO4J_SECTION_ENABLED = True


def _ensure_pkg(pkg, import_name=None):
    name = import_name or pkg
    try:
        __import__(name)
        return True
    except Exception:
        print(f"Installing {pkg} (only needed for Section 11)...", flush=True)
        rc = subprocess.call([sys.executable, "-m", "pip", "install", "-q", pkg])
        if rc != 0:
            print(f"  pip install {pkg} failed (rc={rc}); Section 11 will be skipped.")
            return False
        try:
            __import__(name)
            return True
        except Exception as e:
            print(f"  Import still failing after install of {pkg}: {e}")
            return False


for _pkg, _imp in [("neo4j", "neo4j"), ("fastapi", "fastapi"), ("uvicorn", "uvicorn")]:
    if not _ensure_pkg(_pkg, _imp):
        NEO4J_SECTION_ENABLED = False

if not os.getenv("NEO4J_URI"):
    os.environ["NEO4J_URI"] = getpass("Enter NEO4J_URI (e.g. neo4j://127.0.0.1:7687) or press Enter to skip: ")
if not os.getenv("NEO4J_USER"):
    os.environ["NEO4J_USER"] = getpass("Enter NEO4J_USER (default 'neo4j') or press Enter to skip: ") or "neo4j"
if not os.getenv("NEO4J_PASSWORD"):
    os.environ["NEO4J_PASSWORD"] = getpass("Enter NEO4J_PASSWORD or press Enter to skip: ")

NEO4J_URI = (os.getenv("NEO4J_URI") or "").strip()
NEO4J_USER = (os.getenv("NEO4J_USER") or "").strip()
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD") or ""

def _normalize_neo4j_uri(uri):
    parsed = urlparse(uri)
    if parsed.scheme in {"bolt", "bolt+ssc", "bolt+s", "neo4j", "neo4j+ssc", "neo4j+s"}:
        return uri
    if parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return f"neo4j://{parsed.hostname}:7687"
    return uri

_normalized_neo4j_uri = _normalize_neo4j_uri(NEO4J_URI)
if _normalized_neo4j_uri != NEO4J_URI:
    print(f"Converted Neo4j browser URL {NEO4J_URI!r} to driver URI {_normalized_neo4j_uri!r}.")
    NEO4J_URI = _normalized_neo4j_uri
    os.environ["NEO4J_URI"] = NEO4J_URI

if not (NEO4J_URI and NEO4J_USER and NEO4J_PASSWORD):
    print("Neo4j credentials not fully provided. Section 11 will be skipped (other cells will short-circuit safely).")
    NEO4J_SECTION_ENABLED = False
else:
    print(f"Neo4j configured: {NEO4J_USER}@{NEO4J_URI}")

print(f"NEO4J_SECTION_ENABLED = {NEO4J_SECTION_ENABLED}")
```

### 11.2) Step 1 - Seed：定義知識圖譜資料

建出圖譜的記憶體內資料結構：schema、table（含 `description`、`primary_key`）、column（含 `type`、`nullable`、`is_primary_key`、選配的 `description`，以及下一步要由 AI 填的 `semantic_meaning` 佔位值）、foreign key、view、lineage 邊（`DERIVED_FROM`）和 join。

這個內嵌的合成零售圖譜，跟 cookbook 的變更需求對齊：`LOYALTY_TIER` 加在 `ODS.ODS_CUSTOMER_PROFILE`，來源是 `CORE.DIM_CUSTOMER`，並傳遞到下游的 staging、mart 和 CRM 消費者。

**這裡不呼叫 Neo4j**，這個 cell 只準備 Python 資料結構。要到 Step 3 才會寫入。


```python
SCHEMAS = ["ODS", "STG", "CORE", "MARTS", "CRM"]

TABLES = {
    "ODS.ODS_CUSTOMER_PROFILE": {
        "description": "Raw customer profile table that receives LOYALTY_TIER in this change.",
        "primary_key": ["CUSTOMER_ID"],
        "columns": [
            {"name": "CUSTOMER_ID", "type": "VARCHAR(32)", "nullable": False,
             "description": "Stable customer identifier from the source system.",
             "semantic_meaning": "customer-identifier"},
            {"name": "EMAIL_HASH", "type": "VARCHAR(64)", "nullable": True,
             "description": "Hashed email value used for matching without exposing PII."},
            {"name": "CUSTOMER_STATUS", "type": "VARCHAR(20)", "nullable": True},
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": True,
             "description": "Nullable loyalty segment added by the change request and backfilled from CORE.DIM_CUSTOMER.",
             "semantic_meaning": "loyalty-segment"},
            {"name": "UPDATED_AT", "type": "TIMESTAMP", "nullable": True},
            {"name": "INGESTED_AT", "type": "TIMESTAMP", "nullable": True},
        ],
    },
    "ODS.ODS_ORDER": {
        "description": "Raw order header feed used to measure loyalty-tier revenue impact.",
        "primary_key": ["ORDER_ID"],
        "columns": [
            {"name": "ORDER_ID", "type": "VARCHAR(40)", "nullable": False,
             "semantic_meaning": "order-identifier"},
            {"name": "ORDER_TS", "type": "TIMESTAMP", "nullable": False},
            {"name": "CUSTOMER_ID", "type": "VARCHAR(32)", "nullable": True},
            {"name": "ORDER_STATUS", "type": "VARCHAR(30)", "nullable": True},
            {"name": "NET_AMOUNT", "type": "NUMERIC(12,2)", "nullable": True},
        ],
    },
    "STG.STG_CUSTOMER_PROFILE": {
        "description": "Staging table that normalizes customer profile rows for downstream dimensions and views.",
        "primary_key": ["CUSTOMER_ID"],
        "columns": [
            {"name": "CUSTOMER_ID", "type": "VARCHAR(32)", "nullable": False,
             "semantic_meaning": "customer-identifier"},
            {"name": "CUSTOMER_STATUS", "type": "VARCHAR(20)", "nullable": True},
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": True,
             "description": "Propagated loyalty segment from ODS.ODS_CUSTOMER_PROFILE.",
             "semantic_meaning": "loyalty-segment"},
            {"name": "PROFILE_UPDATED_AT", "type": "TIMESTAMP", "nullable": True},
        ],
    },
    "STG.STG_ORDER_ENRICHED": {
        "description": "Staging order table enriched with customer status and loyalty tier for metrics.",
        "primary_key": ["ORDER_ID"],
        "columns": [
            {"name": "ORDER_ID", "type": "VARCHAR(40)", "nullable": False},
            {"name": "CUSTOMER_ID", "type": "VARCHAR(32)", "nullable": True},
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": True,
             "semantic_meaning": "loyalty-segment"},
            {"name": "ORDER_TS", "type": "TIMESTAMP", "nullable": False},
            {"name": "NET_AMOUNT", "type": "NUMERIC(12,2)", "nullable": True},
        ],
    },
    "CORE.DIM_CUSTOMER": {
        "description": "Conformed customer dimension and source for the LOYALTY_TIER backfill.",
        "primary_key": ["CUSTOMER_SK"],
        "columns": [
            {"name": "CUSTOMER_SK", "type": "BIGINT", "nullable": False,
             "semantic_meaning": "surrogate-key"},
            {"name": "CUSTOMER_ID", "type": "VARCHAR(32)", "nullable": False,
             "semantic_meaning": "customer-identifier"},
            {"name": "EMAIL_HASH", "type": "VARCHAR(64)", "nullable": True},
            {"name": "COUNTRY_CODE", "type": "VARCHAR(2)", "nullable": True},
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": True,
             "description": "Current loyalty segment used as the backfill source.",
             "semantic_meaning": "loyalty-segment"},
            {"name": "IS_CURRENT", "type": "BOOLEAN", "nullable": False,
             "semantic_meaning": "current-row-flag"},
            {"name": "VALID_FROM_TS", "type": "TIMESTAMP", "nullable": True},
            {"name": "VALID_TO_TS", "type": "TIMESTAMP", "nullable": True},
        ],
    },
    "CORE.DIM_LOYALTY_TIER": {
        "description": "Reference dimension for loyalty tier labels, rank, and benefits.",
        "primary_key": ["LOYALTY_TIER"],
        "columns": [
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": False,
             "semantic_meaning": "loyalty-segment"},
            {"name": "TIER_RANK", "type": "INTEGER", "nullable": True},
            {"name": "TIER_DESCRIPTION", "type": "VARCHAR(255)", "nullable": True},
            {"name": "ACTIVE_FLAG", "type": "BOOLEAN", "nullable": True},
        ],
    },
    "CORE.FACT_ORDER": {
        "description": "Order fact table used by revenue and customer 360 marts.",
        "primary_key": ["ORDER_ID"],
        "columns": [
            {"name": "ORDER_ID", "type": "VARCHAR(40)", "nullable": False},
            {"name": "CUSTOMER_SK", "type": "BIGINT", "nullable": True},
            {"name": "ORDER_TS", "type": "TIMESTAMP", "nullable": False},
            {"name": "NET_AMOUNT", "type": "NUMERIC(12,2)", "nullable": True,
             "semantic_meaning": "monetary-amount"},
        ],
    },
    "CORE.FACT_CUSTOMER_ACTIVITY": {
        "description": "Daily customer activity fact used for retention and loyalty reporting.",
        "primary_key": ["CUSTOMER_SK", "ACTIVITY_DATE"],
        "columns": [
            {"name": "CUSTOMER_SK", "type": "BIGINT", "nullable": False},
            {"name": "ACTIVITY_DATE", "type": "DATE", "nullable": False},
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": True,
             "semantic_meaning": "loyalty-segment"},
            {"name": "ORDER_COUNT", "type": "INTEGER", "nullable": True},
            {"name": "NET_AMOUNT", "type": "NUMERIC(12,2)", "nullable": True},
        ],
    },
    "CRM.CUSTOMER_SEGMENT_EXPORT": {
        "description": "Activation export consumed by marketing journeys and retention campaigns.",
        "primary_key": ["CUSTOMER_ID"],
        "columns": [
            {"name": "CUSTOMER_ID", "type": "VARCHAR(32)", "nullable": False},
            {"name": "LOYALTY_TIER", "type": "VARCHAR(20)", "nullable": True,
             "semantic_meaning": "loyalty-segment"},
            {"name": "SEGMENT_CODE", "type": "VARCHAR(40)", "nullable": True},
            {"name": "EXPORT_BATCH_ID", "type": "VARCHAR(40)", "nullable": True},
        ],
    },
}

VIEWS = {
    "MARTS.VW_CUSTOMER_360": {"description": "Customer 360 view with profile, loyalty tier, and recent activity."},
    "MARTS.VW_LOYALTY_REVENUE": {"description": "Revenue by loyalty tier for dashboarding and finance checks."},
    "MARTS.VW_RETENTION_BY_TIER": {"description": "Retention metrics grouped by current loyalty tier."},
}

# (from_schema, from_table, from_col, to_schema, to_table, to_col)
FOREIGN_KEYS = [
    ("ODS",  "ODS_ORDER",              "CUSTOMER_ID",  "ODS",  "ODS_CUSTOMER_PROFILE", "CUSTOMER_ID"),
    ("STG",  "STG_CUSTOMER_PROFILE",   "CUSTOMER_ID",  "ODS",  "ODS_CUSTOMER_PROFILE", "CUSTOMER_ID"),
    ("STG",  "STG_ORDER_ENRICHED",     "CUSTOMER_ID",  "STG",  "STG_CUSTOMER_PROFILE", "CUSTOMER_ID"),
    ("CORE", "DIM_CUSTOMER",           "CUSTOMER_ID",  "ODS",  "ODS_CUSTOMER_PROFILE", "CUSTOMER_ID"),
    ("CORE", "DIM_CUSTOMER",           "LOYALTY_TIER", "CORE", "DIM_LOYALTY_TIER",    "LOYALTY_TIER"),
    ("CORE", "FACT_ORDER",             "CUSTOMER_SK",  "CORE", "DIM_CUSTOMER",        "CUSTOMER_SK"),
    ("CORE", "FACT_CUSTOMER_ACTIVITY", "CUSTOMER_SK",  "CORE", "DIM_CUSTOMER",        "CUSTOMER_SK"),
    ("CORE", "FACT_CUSTOMER_ACTIVITY", "LOYALTY_TIER", "CORE", "DIM_LOYALTY_TIER",    "LOYALTY_TIER"),
    ("CRM",  "CUSTOMER_SEGMENT_EXPORT", "CUSTOMER_ID",  "ODS",  "ODS_CUSTOMER_PROFILE", "CUSTOMER_ID"),
]

DERIVED_FROM = [
    ("ODS.ODS_CUSTOMER_PROFILE",      "CORE.DIM_CUSTOMER"),
    ("STG.STG_CUSTOMER_PROFILE",      "ODS.ODS_CUSTOMER_PROFILE"),
    ("STG.STG_ORDER_ENRICHED",        "ODS.ODS_ORDER"),
    ("STG.STG_ORDER_ENRICHED",        "STG.STG_CUSTOMER_PROFILE"),
    ("CORE.DIM_CUSTOMER",             "STG.STG_CUSTOMER_PROFILE"),
    ("CORE.DIM_CUSTOMER",             "CORE.DIM_LOYALTY_TIER"),
    ("CORE.FACT_ORDER",               "STG.STG_ORDER_ENRICHED"),
    ("CORE.FACT_ORDER",               "CORE.DIM_CUSTOMER"),
    ("CORE.FACT_CUSTOMER_ACTIVITY",   "CORE.FACT_ORDER"),
    ("CORE.FACT_CUSTOMER_ACTIVITY",   "CORE.DIM_CUSTOMER"),
    ("MARTS.VW_CUSTOMER_360",         "CORE.DIM_CUSTOMER"),
    ("MARTS.VW_CUSTOMER_360",         "CORE.FACT_CUSTOMER_ACTIVITY"),
    ("MARTS.VW_LOYALTY_REVENUE",      "CORE.FACT_ORDER"),
    ("MARTS.VW_LOYALTY_REVENUE",      "CORE.DIM_LOYALTY_TIER"),
    ("MARTS.VW_RETENTION_BY_TIER",    "CORE.FACT_CUSTOMER_ACTIVITY"),
    ("MARTS.VW_RETENTION_BY_TIER",    "CORE.DIM_LOYALTY_TIER"),
    ("CRM.CUSTOMER_SEGMENT_EXPORT",   "MARTS.VW_CUSTOMER_360"),
    ("CRM.CUSTOMER_SEGMENT_EXPORT",   "MARTS.VW_RETENTION_BY_TIER"),
]

JOINS = [
    ("STG.STG_ORDER_ENRICHED",      "STG.STG_CUSTOMER_PROFILE"),
    ("CORE.FACT_ORDER",             "CORE.DIM_CUSTOMER"),
    ("CORE.FACT_CUSTOMER_ACTIVITY", "CORE.DIM_CUSTOMER"),
    ("CORE.FACT_CUSTOMER_ACTIVITY", "CORE.DIM_LOYALTY_TIER"),
    ("MARTS.VW_CUSTOMER_360",       "CORE.DIM_CUSTOMER"),
    ("MARTS.VW_LOYALTY_REVENUE",    "CORE.DIM_LOYALTY_TIER"),
    ("MARTS.VW_RETENTION_BY_TIER",  "CORE.DIM_LOYALTY_TIER"),
]

for _tid, _meta in TABLES.items():
    _pk = set(_meta.get("primary_key", []) or [])
    for _c in _meta["columns"]:
        _c.setdefault("is_primary_key", _c["name"] in _pk)
        _c.setdefault("description", None)
        _c.setdefault("semantic_meaning", None)

_total_cols = sum(len(t["columns"]) for t in TABLES.values())
_total_pks = sum(len(t.get("primary_key", []) or []) for t in TABLES.values())
print(f"Seed prepared: {len(SCHEMAS)} schemas, {len(TABLES)} tables, {len(VIEWS)} views, "
      f"{_total_cols} columns ({_total_pks} primary keys), {len(FOREIGN_KEYS)} FKs, "
      f"{len(DERIVED_FROM)} DERIVED_FROM edges, {len(JOINS)} JOINS edges.")
```

### 11.3) Step 2 - AI Enrichment

用第 1 節已初始化的 OpenAI `client` 和 `MODEL`，為每個目前值是 `None` 的欄位產生簡短的 `semantic_meaning` 標籤（2-5 個字，例如 `natural-key`、`foreign-key`、`monetary-amount`、`timestamp`、`descriptive-text`）。每個欄位一次 LLM 呼叫，回應是純文字。prompt 內嵌定義，讓這個 cell 自給自足。

成本控制：每次執行最多 **`MAX_ENRICH_COLS = 30`** 個欄位（可用環境變數 `SEED_AI_ENRICH_LIMIT` 覆寫）。設 `SEED_AI_ENRICH=0` 可完全跳過豐富化。單一欄位的失敗會被捕捉並記錄，cell 不會丟例外。如果第 11 節在 Step 0 被停用，這個 cell 會整個跳過。

```python
ENRICH_SYSTEM = (
    "You are a data architect assistant. Your task is to provide concise semantic-meaning "
    "tags (2-5 words) for database columns. Do not add any preamble or explanation."
)


def _enrich_one(_client, _model, table_name, c):
    user_prompt = (
        f"Provide a short 2-5 word semantic-meaning tag for a database column "
        f"named '{c['name']}'. It is part of the table '{table_name}'. "
        f"It has a data type of '{c.get('type','UNKNOWN')}'. "
        f"Examples of valid tags: natural-key, foreign-key, surrogate-key, "
        f"monetary-amount, timestamp, descriptive-text, category-code, count, boolean-flag. "
        f"Return only the tag, with no quotes, no punctuation at the end, no extra prose."
    )
    try:
        resp = _client.responses.create(
            model=_model,
            input=[
                {"role": "system", "content": ENRICH_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = (getattr(resp, "output_text", None) or "").strip()
        if not text:
            for item in (getattr(resp, "output", []) or []):
                for sub in getattr(item, "content", []) or []:
                    t = getattr(sub, "text", None)
                    if isinstance(t, str):
                        text += t
                    elif isinstance(sub, dict):
                        text += sub.get("text", "")
        text = text.strip().strip('"').strip("'").strip(".")
        return text or None
    except Exception as e:
        print(f"  ! enrichment failed for {table_name}.{c['name']}: {type(e).__name__}: {e}")
        return None


def _run_ai_enrichment():
    if not NEO4J_SECTION_ENABLED:
        print("Section 11 disabled (see Step 0). Skipping AI enrichment.")
        return

    enabled = (os.getenv("SEED_AI_ENRICH", "1").strip().lower() in ("1", "true", "yes", "on"))
    max_cols = int(os.getenv("SEED_AI_ENRICH_LIMIT", "30"))

    if not enabled:
        print("AI enrichment disabled via SEED_AI_ENRICH=0. Columns will be upserted without semantic_meaning.")
        return

    try:
        _c = client
        _m = MODEL
    except NameError:
        print("OpenAI client/MODEL not found. Run Section 1 first, then re-run this cell.")
        return

    missing = []
    for tid, meta in TABLES.items():
        for col in meta["columns"]:
            if not col.get("semantic_meaning"):
                missing.append((tid, col))

    cap = min(len(missing), max_cols)
    print(f"AI enrichment: {len(missing)} column(s) need semantic_meaning; processing first {cap} "
          f"(cap via SEED_AI_ENRICH_LIMIT, model='{_m}').")

    updated = 0
    for tid, col in missing[:cap]:
        tag = _enrich_one(_c, _m, tid, col)
        if tag:
            col["semantic_meaning"] = tag
            updated += 1
            print(f"  + {tid}.{col['name']}: {tag}")

    print(f"\nAI enrichment complete: {updated}/{cap} columns updated.")


_run_ai_enrichment()
```

### 11.4) Step 3 - 把豐富化後的圖譜 Upsert 到 Neo4j

用 Step 0 載入的環境變數開 Neo4j driver，建立唯一性限制，再對下列內容做 idempotent 的 `MERGE` upsert：

- **Schema**（`Schema` 節點，用 `:CONTAINS` 邊連到 Table/View）
- **Table**，含 `description`
- **Column**，含 `type`、`nullable`、`is_primary_key`、`description`、`semantic_meaning`
- **Foreign Key**，以 `Column-[:FK_TO]->Column` 表示
- **View**，含 `description`
- **Lineage**，以 `(Table|View)-[:DERIVED_FROM]->(Table|View)` 表示
- **Join**，以 `(Table|View)-[:JOINS]->(Table|View)` 表示

Cypher 刻意內嵌寫出，讓這個 cell 自給自足。`MERGE` 的寫法對應上面內嵌的 seed 結構，而且每個 cookbook 節點都會有 `SchemaFlowCookbook` label，所以重跑只會更新這份範例圖譜，不會讓儀表板露出舊的本機 seed 資料。

整個操作包在 `try/except` 裡。如果連不上 Neo4j，cell 會印出清楚的診斷訊息然後返回，不會丟例外。

```python
def _upsert_to_neo4j():
    if not NEO4J_SECTION_ENABLED:
        print("Section 11 disabled (see Step 0). Skipping Neo4j upsert.")
        return

    try:
        from neo4j import GraphDatabase
    except Exception as e:
        print(f"neo4j package not importable: {e}. Skipping upsert.")
        return

    try:
        drv = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    except Exception as e:
        print(f"Neo4j driver init failed: {e}. Skipping upsert.")
        return

    counts = {"schemas": 0, "tables": 0, "columns": 0, "fks": 0,
              "views": 0, "derived": 0, "joins": 0}
    try:
        with drv.session() as s:
            s.run("RETURN 1 AS ok").single()
            print(f"Neo4j connection OK ({NEO4J_USER}@{NEO4J_URI})")

            for cypher in [
                "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Table)  REQUIRE t.id  IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Column) REQUIRE c.id  IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (v:View)   REQUIRE v.id  IS UNIQUE",
                "CREATE CONSTRAINT IF NOT EXISTS FOR (sc:Schema) REQUIRE sc.name IS UNIQUE",
            ]:
                s.run(cypher)

            for sch in SCHEMAS:
                s.run("MERGE (sc:Schema {name:$name}) SET sc:SchemaFlowCookbook", name=sch)
                counts["schemas"] += 1

            for tid, meta in TABLES.items():
                schema, table = tid.split(".", 1)
                s.run(
                    """
                    MERGE (sc:Schema {name:$schema})
                    SET sc:SchemaFlowCookbook
                    MERGE (t:Table {id:$id})
                      ON CREATE SET t.created_by='schemaflow-cookbook'
                    SET t:SchemaFlowCookbook,
                        t.name=$table,
                        t.schema=$schema,
                        t.type='TABLE',
                        t.description = coalesce($desc, t.description)
                    MERGE (sc)-[:CONTAINS]->(t)
                    """,
                    id=tid, schema=schema, table=table, desc=meta.get("description"),
                )
                counts["tables"] += 1
                for c in meta["columns"]:
                    cid = f"{tid}.{c['name']}"
                    s.run(
                        """
                        MERGE (t:Table {id:$tid})
                        SET t:SchemaFlowCookbook
                        MERGE (c:Column {id:$cid})
                          ON CREATE SET c.created_by='schemaflow-cookbook'
                        SET c:SchemaFlowCookbook,
                            c.name=$name,
                            c.type=$dtype,
                            c.nullable=$nullable,
                            c.is_primary_key=$is_pk,
                            c.description=coalesce($description, c.description),
                            c.semantic_meaning=coalesce($smean, c.semantic_meaning)
                        MERGE (t)-[:HAS_COLUMN]->(c)
                        """,
                        tid=tid, cid=cid, name=c["name"],
                        dtype=c.get("type", "UNKNOWN"),
                        nullable=bool(c.get("nullable", True)),
                        is_pk=bool(c.get("is_primary_key", False)),
                        description=c.get("description"),
                        smean=c.get("semantic_meaning"),
                    )
                    counts["columns"] += 1

            for f_s, f_t, f_c, t_s, t_t, t_c in FOREIGN_KEYS:
                s.run(
                    """
                    MATCH (src:Column {id:$src})
                    MATCH (dst:Column {id:$dst})
                    SET src:SchemaFlowCookbook, dst:SchemaFlowCookbook
                    MERGE (src)-[:FK_TO]->(dst)
                    """,
                    src=f"{f_s}.{f_t}.{f_c}",
                    dst=f"{t_s}.{t_t}.{t_c}",
                )
                counts["fks"] += 1

            for vid, vmeta in VIEWS.items():
                schema, name = vid.split(".", 1)
                s.run(
                    """
                    MERGE (sc:Schema {name:$schema})
                    SET sc:SchemaFlowCookbook
                    MERGE (v:View {id:$id})
                      ON CREATE SET v.created_by='schemaflow-cookbook'
                    SET v:SchemaFlowCookbook,
                        v.name=$name,
                        v.schema=$schema,
                        v.type='VIEW',
                        v.description = coalesce($desc, v.description)
                    MERGE (sc)-[:CONTAINS]->(v)
                    """,
                    id=vid, schema=schema, name=name, desc=vmeta.get("description"),
                )
                counts["views"] += 1

            for a, b in DERIVED_FROM:
                a_lbl = "View:SchemaFlowCookbook" if a in VIEWS else "Table:SchemaFlowCookbook"
                b_lbl = "View:SchemaFlowCookbook" if b in VIEWS else "Table:SchemaFlowCookbook"
                s.run(
                    f"MATCH (x:{a_lbl} {{id:$a}}),(y:{b_lbl} {{id:$b}}) "
                    "MERGE (x)-[:DERIVED_FROM]->(y)",
                    a=a, b=b,
                )
                counts["derived"] += 1

            for a, b in JOINS:
                a_lbl = "View:SchemaFlowCookbook" if a in VIEWS else "Table:SchemaFlowCookbook"
                b_lbl = "View:SchemaFlowCookbook" if b in VIEWS else "Table:SchemaFlowCookbook"
                s.run(
                    f"MATCH (x:{a_lbl} {{id:$a}}),(y:{b_lbl} {{id:$b}}) "
                    "MERGE (x)-[:JOINS]->(y)",
                    a=a, b=b,
                )
                counts["joins"] += 1

        print("Upsert complete:")
        for k, v in counts.items():
            print(f"  {k:>10}: {v}")
        print("Dashboard scope: nodes labeled :SchemaFlowCookbook. Re-run the dashboard launch cell to refresh the UI.")
    except Exception as e:
        print(f"Upsert failed: {type(e).__name__}: {e}")
    finally:
        try:
            drv.close()
        except Exception:
            pass

_upsert_to_neo4j()
```

### 11.5) 啟動本機儀表板

接下來的六個 cell 會設定並啟動一個小型的 FastAPI + D3.js 儀表板，連到你的 Neo4j。檔案放在 notebook 旁邊的 `_neo4j_dashboard/`，你可以直接讀和改，不用 base64，也沒有編碼的花招。

1. **Prep cell**：`mkdir _neo4j_dashboard/` 並選儀表板的 port（預設 `8005`，可用 `NEO4J_DASHBOARD_PORT` 覆寫）。
2. **`%%writefile _neo4j_dashboard/graph_server.py`**：FastAPI 後端，提供 `GET /api/knowledge-graph`（讀）、`POST /api/update-column-semantic-meaning`（寫）、`POST /api/update-relationship`、`POST /api/delete-relationship`。
3. **`%%writefile _neo4j_dashboard/index.html`**：DOM 骨架，含統計列、SVG 圖形容器、側邊欄，以及 AI Semantic Insights 面板（有 Edit / Save 按鈕）。
4. **`%%writefile _neo4j_dashboard/style.css`**：所有視覺樣式。
5. **`%%writefile _neo4j_dashboard/script.js`**：D3 force simulation、點擊處理和 fetch 呼叫。Edit 按鈕會把 Semantic Meaning 的值變成輸入框，Save 會把每個值 POST 給後端，後端再對 Neo4j 執行 `MATCH ... SET c.semantic_meaning = ...`。
6. **啟動 cell**：用 `subprocess.Popen` 在 `127.0.0.1:8005` 啟動 `uvicorn graph_server:app`，最多輪詢 `GET /api/knowledge-graph` 20 秒，等圖譜 API 就緒後才印出可點擊的 Markdown 連結，同時印出 server 的 PID。

這些 cell 會在 notebook 旁邊產生一個小型本機儀表板應用，並用 `semantic_meaning` 當作可編輯的欄位洞察欄位。你可以打開任何產生出來的檔案，在 notebook 工作區裡調整顏色、加 endpoint 等，修改會在下次重跑 writefile 和啟動 cell 時生效。重跑啟動 cell 時，會重啟同一個 kernel 啟動的前一個儀表板 process，瀏覽器就不會停在過期的圖譜資料上。

**之後要停止儀表板**，執行 `kill <pid>`（PID 由啟動 cell 印出），或直接重啟 Jupyter kernel。

```python
import os
from pathlib import Path

DASHBOARD_DIR = Path("_neo4j_dashboard").resolve()
DASHBOARD_PORT = int(os.getenv("NEO4J_DASHBOARD_PORT", "8005"))

DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)
print(f"Dashboard directory ready: {DASHBOARD_DIR}")
print(f"Dashboard port: {DASHBOARD_PORT} (override via NEO4J_DASHBOARD_PORT)")
```

```python
%%writefile _neo4j_dashboard/graph_server.py
import os
import json
from fastapi import FastAPI, Response, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from neo4j import GraphDatabase

app = FastAPI()

# Neo4j connection details from environment variables
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def fetch_knowledge_graph_data():
    """Queries Neo4j to build the database hierarchy and relationships."""
    db_hierarchy = {}
    relationships = []
    db_name = "SCHEMAFLOW_GRAPH_DB" # Synthetic graph database label for this cookbook

    with driver.session() as session:
        # 1. Fetch hierarchy (tables and columns)
        hierarchy_query = """        MATCH (t:Table:SchemaFlowCookbook)
        OPTIONAL MATCH (t)-[:HAS_COLUMN]->(c:Column:SchemaFlowCookbook)
        RETURN t.schema AS schema_name, t.name AS table_name, t.type as table_type, collect({
            column_name: c.name,
            data_type: c.type,
            semantic_meaning: c.semantic_meaning
        }) AS columns
        """
        hierarchy_result = session.run(hierarchy_query)
        for record in hierarchy_result:
            schema_name = record["schema_name"] or "default_schema"
            table_name = record["table_name"]
            if not table_name: continue

            if db_name not in db_hierarchy:
                db_hierarchy[db_name] = {"schemas": {}}
            if schema_name not in db_hierarchy[db_name]["schemas"]:
                db_hierarchy[db_name]["schemas"][schema_name] = {"tables": {}}

            table_columns = {c['column_name']: c for c in record["columns"] if c and c.get('column_name')}
            db_hierarchy[db_name]["schemas"][schema_name]["tables"][table_name] = {
                "table_type": record["table_type"] or "TABLE",
                "columns": table_columns
            }

        # 2. Fetch relationships between tables
        relationship_query = """        MATCH (source:Table:SchemaFlowCookbook)-[r]-(target:Table:SchemaFlowCookbook)
        WHERE id(source) < id(target)
        RETURN 
            source.schema AS source_schema, source.name AS source_table,
            target.schema AS target_schema, target.name AS target_table,
            type(r) AS relationship_type
        """
        relationship_result = session.run(relationship_query)
        for record in relationship_result:
            source_id = f"{db_name}.{record['source_schema']}.{record['source_table']}"
            target_id = f"{db_name}.{record['target_schema']}.{record['target_table']}"
            relationships.append({
                "source": source_id,
                "target": target_id,
                "type": record["relationship_type"]
            })

    return {"database_hierarchy": db_hierarchy, "relationships": relationships}

@app.get("/api/knowledge-graph")
async def get_knowledge_graph():
    """Endpoint to fetch and return the knowledge graph data."""
    data = fetch_knowledge_graph_data()
    # Return as a JSON response, ensuring proper content type
    return Response(content=json.dumps(data), media_type="application/json")


class RelationshipUpdateRequest(BaseModel):
    source_table_id: str
    target_table_id: str
    old_relationship_type: str
    new_relationship_type: str

class RelationshipDeleteRequest(BaseModel):
    source_table_id: str
    target_table_id: str
    relationship_type: str

class ColumnSemanticUpdateRequest(BaseModel):
    table_id: str
    column_name: str
    semantic_meaning: str



@app.post("/api/update-relationship")
async def update_relationship(request: RelationshipUpdateRequest):
    """Endpoint to update the type of a relationship between two tables."""
    try:
        _, source_schema, source_table = request.source_table_id.split('.', 2)
        _, target_schema, target_table = request.target_table_id.split('.', 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid table_id format. Expected 'db.schema.table'.")

    # This query is complex because Cypher doesn't allow dynamic relationship types in SET.
    # We must delete the old relationship and create a new one.
    # NOTE: Using an installed APOC procedure (apoc.refactor.rename.type) would simplify this.
    # This query is now direction-agnostic.
    update_query = f"""    MATCH (source:Table:SchemaFlowCookbook {{name: $source_table, schema: $source_schema}})
    MATCH (target:Table:SchemaFlowCookbook {{name: $target_table, schema: $target_schema}})
    MATCH (source)-[r:`{request.old_relationship_type}`]-(target)
    CREATE (source)-[new_r:`{request.new_relationship_type}`]->(target)
    DELETE r
    RETURN type(new_r) as new_type
    """

    with driver.session() as session:
        result = session.run(
            update_query,
            source_table=source_table,
            source_schema=source_schema,
            target_table=target_table,
            target_schema=target_schema,
        )
        updated_record = result.single()
        if updated_record:
            return {"status": "success", "updated_relationship": dict(updated_record)}
        else:
            raise HTTPException(status_code=404, detail="Relationship not found or not updated.")

@app.post("/api/delete-relationship")
async def delete_relationship(request: RelationshipDeleteRequest):
    """Endpoint to delete a specific relationship between two tables."""
    try:
        _, source_schema, source_table = request.source_table_id.split('.', 2)
        _, target_schema, target_table = request.target_table_id.split('.', 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid table_id format. Expected 'db.schema.table'.")

    # This query is now direction-agnostic.
    delete_query = f"""    MATCH (source:Table:SchemaFlowCookbook {{name: $source_table, schema: $source_schema}})-[r:`{request.relationship_type}`]-(target:Table:SchemaFlowCookbook {{name: $target_table, schema: $target_schema}})
    DELETE r
    RETURN count(r) as deleted_count
    """

    with driver.session() as session:
        result = session.run(
            delete_query,
            source_table=source_table,
            source_schema=source_schema,
            target_table=target_table,
            target_schema=target_schema,
        )
        # Even if nothing is deleted, the query succeeds. We just confirm it ran.
        return {"status": "success"}




@app.post("/api/update-column-semantic-meaning")
async def update_column_semantic_meaning(request: ColumnSemanticUpdateRequest):
    """Endpoint to update the semantic_meaning of a specific column."""
    try:
        _, schema_name, table_name = request.table_id.split('.', 2)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid table_id format. Expected 'db.schema.table'.")

    update_query = """    MATCH (t:Table:SchemaFlowCookbook {name: $table_name, schema: $schema_name})-[:HAS_COLUMN]->(c:Column:SchemaFlowCookbook {name: $column_name})
    SET c.semantic_meaning = $semantic_meaning
    RETURN c.name AS column_name, c.semantic_meaning AS new_meaning
    """

    with driver.session() as session:
        result = session.run(
            update_query,
            table_name=table_name,
            schema_name=schema_name,
            column_name=request.column_name,
            semantic_meaning=request.semantic_meaning,
        )
        updated_record = result.single()
        if updated_record:
            return {"status": "success", "updated_column": dict(updated_record)}
        else:
            raise HTTPException(status_code=404, detail="Column not found or not updated.")



# Mount the current directory to serve static files (HTML, CSS, JS)
# The `html=True` argument makes it serve index.html for the root path.
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=current_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    print("Starting server...")
    print(f"Connect to Neo4j at: {NEO4J_URI}")
    print("View the Graph UI at http://127.0.0.1:8005")
    uvicorn.run(app, host="127.0.0.1", port=8005)
```

```python
%%writefile _neo4j_dashboard/index.html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SchemaFlow Knowledge Graph</title>
    <link rel="stylesheet" href="style.css?v=5">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
</head>
<body>
    <div class="container" id="mainContainer" style="display:none;">
        <div class="header">
            <div class="header-content">
                <div class="header-text">
                    <h1>Knowledge Graph View</h1>
                    <div class="subtitle">AI-Powered Database Schema Visualization & Analytics</div>
                </div>
            </div>
        </div>
        
        <div class="stats-bar" id="statsBar">
            <!-- Stats will be populated by JS -->
        </div>
        
        <div class="main-content">
            <div class="graph-container">
                <div class="graph-header">
                    <span>🕸️ Interactive Schema Network</span>
                    <div class="controls">
                        <button class="control-btn" onclick="resetGraph()">🔄 Reset</button>
                        <button class="control-btn" onclick="togglePhysics()">⚡ Physics</button>
                        <button class="control-btn" onclick="fitToScreen()">📐 Fit</button>
                        <button class="control-btn" onclick="toggleRelationships()">🔗 Toggle Relations</button>
                    </div>
                </div>
                <svg id="graph"></svg>
                <div id="tooltip" class="tooltip"></div>
                <div id="loadingGraph" class="loading-overlay"><h2>Loading Graph...</h2></div>
            </div>
            
            <div class="sidebar">
                <div class="panel">
                    <div class="panel-header">🎯 Legend & Controls</div>
                    <div class="panel-content">
                        <div class="legend">
                            <div class="legend-item"><div class="legend-circle" style="background:#4CAF50;"></div><span>Database</span></div>
                            <div class="legend-item"><div class="legend-circle" style="background:#2196F3;"></div><span>Schema</span></div>
                            <div class="legend-item"><div class="legend-circle" style="background:#FF9800;"></div><span>Table</span></div>
                        </div>
                        <p style="font-size:0.9em;color:#6c757d;margin-top:15px;line-height:1.6">💡 <strong>Interactive Features:</strong><br>• Drag nodes to reorganize layout<br>• Hover over nodes for quick details<br>• Click nodes to view full information<br>• Use control buttons for navigation<br>• Zoom and pan to explore large schemas</p>
                    </div>
                </div>
                
                <div class="panel">
                    <div class="panel-header">
                        <span>📊 Selected Node Details</span>
                        <div class="controls">
                            <button id="editNodeBtn" class="control-btn" style="display:none;">✏️ Edit</button>
                            <button id="saveNodeBtn" class="control-btn" style="display:none;">💾 Save</button>
                        </div>
                    </div>
                    <div class="panel-content">
                        <div id="nodeDetails">
                            <p style="color:#6c757d;text-align:center;padding:30px;font-style:italic">Click on any node in the graph to view detailed information</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="ai-insights-section">
            <div class="insights-header">
                <span>🧠 AI-Powered Column Semantic Insights</span>
                <div class="controls">
                    <button id="editInsightsBtn" class="control-btn">✏️ Edit</button>
                    <button id="saveInsightsBtn" class="control-btn" style="display:none;">💾 Save</button>
                </div>
            </div>
            <div class="insights-grid" id="insightsGrid">
                <!-- Insights will be populated by JS -->
            </div>
        </div>
    </div>

    <div id="loadingScreen" class="loading-overlay">
        <h2>Fetching Knowledge Graph from Neo4j...</h2>
        <p>This may take a moment.</p>
    </div>

    <div id="errorScreen" class="loading-overlay" style="display:none;">
        <div style="text-align: center; padding: 40px; background: white; border-radius: 16px; border: 2px solid #dc3545; max-width: 600px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
            <div style="font-size: 4em; margin-bottom: 20px; opacity: 0.7;">⚠️</div>
            <h1 style="font-size: 2em; color: #dc3545; margin-bottom: 15px;">Knowledge Graph Error</h1>
            <p id="errorMessage" style="font-size: 1.1em; color: #495057; line-height: 1.6;"></p>
        </div>
    </div>
    
    <script src="script.js?v=7"></script>
</body>
</html>
```

```python
%%writefile _neo4j_dashboard/style.css
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','Roboto',sans-serif;background:#f8f9fa;min-height:100vh;color:#1a1a1a}
.container{max-width:1800px;margin:0 auto;padding:20px}
.header{background:white;color:#1a1a1a;padding:40px;border-radius:16px;text-align:center;margin-bottom:30px;box-shadow:0 6px 25px rgba(0,0,0,0.2);position:relative;overflow:hidden;border:2px solid #c0c0c0}
.header::before{content:'';position:absolute;top:0;left:0;right:0;bottom:0;background:linear-gradient(135deg,rgba(248,249,250,0.8) 0%,rgba(233,236,239,0.8) 100%)}
.header-content{position:relative;z-index:2;display:flex;align-items:center;justify-content:center;gap:20px}
.logo-container{display:flex;align-items:center;gap:15px}
.logo-img{width:80px;height:80px;border-radius:12px;object-fit:cover;border:2px solid #6c757d}
.header-text{text-align:center}
.header h1{font-size:3.2em;margin-bottom:15px;text-shadow:none;font-weight:300;color:#2c2c2c}
.header .subtitle{font-size:1.3em;opacity:0.9;font-weight:300;letter-spacing:0.5px;color:#4a4a4a}
.stats-bar{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:20px;margin-bottom:30px}
.stat-item{background:white;padding:25px;border-radius:12px;text-align:center;box-shadow:0 4px 12px rgba(0,0,0,0.2);border:2px solid #c0c0c0;transition:transform 0.3s ease,box-shadow 0.3s ease}
.stat-item:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.25)}
.stat-number{font-size:2.2em;font-weight:bold;color:#2c2c2c;display:block;margin-bottom:8px}
.stat-label{color:#4a4a4a;font-size:0.9em;text-transform:uppercase;font-weight:600;letter-spacing:1px}
.main-content{display:grid;grid-template-columns:1fr 350px;gap:30px;margin-bottom:30px}
.graph-container{background:white;border-radius:16px;box-shadow:0 6px 25px rgba(0,0,0,0.2);overflow:hidden;position:relative;border:2px solid #c0c0c0}
.graph-header{background:white;color:#2c2c2c;padding:20px 25px;font-size:1.3em;font-weight:600;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #c0c0c0}
.controls{display:flex;gap:12px}
.control-btn{background:#f8f9fa;border:2px solid #4a4a4a;color:#2c2c2c;padding:8px 16px;border-radius:6px;cursor:pointer;font-size:0.9em;transition:all 0.3s ease}
.control-btn:hover{background:#e9ecef;transform:translateY(-1px);box-shadow:0 4px 8px rgba(0,0,0,0.2)}
#graph{width:100%;height:650px;background:#ffffff}
.sidebar{display:flex;flex-direction:column;gap:20px}
.panel{background:white;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.2);overflow:hidden;border:2px solid #c0c0c0}
.panel-header{background:#f8f9fa;color:#2c2c2c;padding:18px 20px;font-weight:600;font-size:1.1em;border-bottom:2px solid #c0c0c0}
.panel-content{padding:20px;max-height:400px;overflow-y:auto;color:#2c2c2c}
.node-info{background:#f8f9fa;border-radius:8px;padding:15px;margin-bottom:12px;border:2px solid #c0c0c0}
.node-name{font-weight:bold;color:#2c2c2c;margin-bottom:8px;font-size:1.1em}
.node-details{font-size:0.9em;color:#4a4a4a;line-height:1.4;word-wrap:break-word;overflow-wrap:break-word;}
.legend{display:flex;flex-wrap:wrap;gap:15px;margin-bottom:20px}
.legend-item{display:flex;align-items:center;gap:8px;font-size:0.95em;color:#2c2c2c}
.legend-circle{width:14px;height:14px;border-radius:50%;border:2px solid #4a4a4a}
.tooltip{position:absolute;background:white;color:#2c2c2c;padding:12px 16px;border-radius:8px;font-size:0.9em;pointer-events:none;z-index:1000;opacity:0;border:2px solid #c0c0c0;box-shadow:0 6px 18px rgba(0,0,0,0.25);transform:translateX(-50%);text-align:center;}
.ai-insights-section{grid-column:1/-1;background:white;border-radius:16px;box-shadow:0 6px 25px rgba(0,0,0,0.2);overflow:hidden;border:2px solid #c0c0c0}
.insights-header{background:#f8f9fa;color:#2c2c2c;padding:25px 30px;font-size:1.4em;font-weight:600;border-bottom:2px solid #c0c0c0}
.insights-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:20px;padding:30px}
.insight-item{background:#f8f9fa;border-radius:10px;padding:20px;border:2px solid #c0c0c0;transition:transform 0.3s ease,box-shadow 0.3s ease}
.insight-item:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,0.25)}
.insight-column{font-weight:bold;color:#2c2c2c;margin-bottom:10px;font-size:1.1em}
.insight-meta{color:#4a4a4a;font-size:0.85em;margin-bottom:12px}
.insight-description{color:#2c2c2c;line-height:1.5;font-size:0.9em}
.loading-overlay { position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: rgba(255,255,255,0.9); display: flex; align-items: center; justify-content: center; z-index: 1001; color: #495057; flex-direction: column; }
.loading-overlay h2 { margin-bottom: 15px; }

.edge-label {
    background: rgba(248, 249, 250, 0.9);
    padding: 1px 4px;
    border-radius: 4px;
    font-weight: 600;
    color: #2563eb;
    border: 1px solid #2563eb;
    pointer-events: none; /* So it doesn't interfere with mouse events on the line */
}

#graph circle:hover {
    stroke: #495057;
    stroke-width: 3px;
}
@media (max-width:1400px){.main-content{grid-template-columns:1fr}.sidebar{grid-template-columns:repeat(auto-fit,minmax(300px,1fr));display:grid}}
@media (max-width:768px){.header h1{font-size:2.2em}.stats-bar{grid-template-columns:repeat(2,1fr)}.insights-grid{grid-template-columns:1fr;padding:20px}.header-content{flex-direction:column;gap:15px}.logo-img{width:60px;height:60px}}
```

```python
%%writefile _neo4j_dashboard/script.js
document.addEventListener('DOMContentLoaded', function() {
    fetch('/api/knowledge-graph')
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (!data || !data.database_hierarchy || Object.keys(data.database_hierarchy).length === 0) {
                throw new Error('No knowledge graph data found in database response.');
            }
            graphDataStore = data; // Store data globally
            document.getElementById('loadingScreen').style.display = 'none';
            document.getElementById('mainContainer').style.display = 'block';
            renderKnowledgeGraph(data);
        })
        .catch(error => {
            console.error('Error fetching or processing knowledge graph:', error);
            document.getElementById('loadingScreen').style.display = 'none';
            const errorMessage = document.getElementById('errorMessage');
            const errorScreen = document.getElementById('errorScreen');
            if (errorMessage) {
                errorMessage.textContent = "Failed to load knowledge graph: " + error.message;
            }
            if (errorScreen) {
                errorScreen.style.display = 'flex';
            }
        });

    const _ei = document.getElementById('editInsightsBtn'); if (_ei) _ei.addEventListener('click', toggleEditMode);
    const _si = document.getElementById('saveInsightsBtn'); if (_si) _si.addEventListener('click', saveChanges);
    const _en = document.getElementById('editNodeBtn'); if (_en) _en.addEventListener('click', toggleNodeEditMode);
    const _sn = document.getElementById('saveNodeBtn'); if (_sn) _sn.addEventListener('click', saveNodeChanges);
});

let simulation, physicsEnabled = true;
let svg, width, height, tooltip, zoom;
let relationshipsVisible = true;
let graphDataStore = {}; // To store the full graph data for later access
let isEditMode = false;
let isNodeEditMode = false;


function renderKnowledgeGraph(knowledgeGraph) {
    const nodes = [];
    const links = [];
    const databaseStats = {};
    let totalSchemas = 0;
    let totalTables = 0;
    let totalColumns = 0;
    const columnInsights = [];

    if (knowledgeGraph.database_hierarchy) {
        // Add relationships from the API to the links array
        if (knowledgeGraph.relationships && Array.isArray(knowledgeGraph.relationships)) {
            knowledgeGraph.relationships.forEach(rel => {
                // Validate relationship data
                if (rel.source && rel.target && rel.type) {
                    links.push({
                        source: rel.source,
                        target: rel.target,
                        type: 'relationship',
                        label: rel.type.replace(/_/g, ' ')
                    });
                }
            });
        }

        Object.entries(knowledgeGraph.database_hierarchy).forEach(([dbName, dbData]) => {
            // Validate dbData structure
            if (!dbData || typeof dbData !== 'object') {
                console.warn(`Invalid database data for ${dbName}`);
                return;
            }

            const dbNode = { id: dbName, name: dbName, type: 'database', size: 30, level: 0 };
            nodes.push(dbNode);

            const schemaCount = Object.keys(dbData.schemas || {}).length;
            databaseStats[dbName] = { schemas: schemaCount, tables: 0, columns: 0 };
            totalSchemas += schemaCount;

            Object.entries(dbData.schemas || {}).forEach(([schemaName, schemaData]) => {
                // Validate schemaData structure
                if (!schemaData || typeof schemaData !== 'object') {
                    console.warn(`Invalid schema data for ${schemaName}`);
                    return;
                }

                const schemaId = `${dbName}.${schemaName}`;
                const schemaNode = { id: schemaId, name: schemaName, type: 'schema', size: 20, level: 1, parent: dbName };
                nodes.push(schemaNode);
                links.push({ source: dbName, target: schemaId, type: 'hierarchy' });

                const tableCount = Object.keys(schemaData.tables || {}).length;
                databaseStats[dbName].tables += tableCount;
                totalTables += tableCount;

                Object.entries(schemaData.tables || {}).forEach(([tableName, tableData]) => {
                    // Validate tableData structure
                    if (!tableData || typeof tableData !== 'object') {
                        console.warn(`Invalid table data for ${tableName}`);
                        return;
                    }

                    const tableId = `${dbName}.${schemaName}.${tableName}`;
                    const columnCount = Object.keys(tableData.columns || {}).length;
                    const tableNode = { 
                        id: tableId, 
                        name: `${schemaName}.${tableName}`,
                        schemaName: schemaName,
                        tableName: tableName,
                        type: 'table', 
                        size: Math.max(8, Math.min(15, columnCount / 2)), 
                        level: 2, 
                        parent: schemaId, 
                        columnCount: columnCount, 
                        tableType: tableData.table_type || 'TABLE' 
                    };
                    nodes.push(tableNode);
                    links.push({ source: schemaId, target: tableId, type: 'hierarchy' });
                    databaseStats[dbName].columns += columnCount;
                    totalColumns += columnCount;

                    Object.entries(tableData.columns || {}).forEach(([columnName, columnData]) => {
                        // Validate columnData structure
                        if (columnData && typeof columnData === 'object' && 
                            columnData.semantic_meaning) {
                            columnInsights.push({
                                column: columnData.column_name || columnName,
                                table: `${dbName}.${schemaName}.${tableName}`,
                                type: columnData.data_type || 'Unknown',
                                semantic: columnData.semantic_meaning || '',
                                relationships: Array.isArray(columnData.potential_relationships) ? 
                                    columnData.potential_relationships : []
                            });
                        }
                    });
                });
            });
        });
    }

    // Populate UI elements with safe DOM access
    const dbNameHeader = document.getElementById('dbNameHeader');
    if (dbNameHeader) {
        const firstDbName = Object.keys(databaseStats)[0] || 'Unknown Database';
        dbNameHeader.textContent = `${firstDbName} Knowledge Graph`;
    }

    const statsBar = document.getElementById('statsBar');
    if (statsBar) {
        statsBar.innerHTML = `
            <div class="stat-item"><span class="stat-number">${Object.keys(databaseStats).length}</span><div class="stat-label">Databases</div></div>
            <div class="stat-item"><span class="stat-number">${totalSchemas}</span><div class="stat-label">Schemas</div></div>
            <div class="stat-item"><span class="stat-number">${totalTables.toLocaleString()}</span><div class="stat-label">Tables</div></div>
            <div class="stat-item"><span class="stat-number">${totalColumns.toLocaleString()}</span><div class="stat-label">Columns</div></div>
            <div class="stat-item"><span class="stat-number">${columnInsights.length}</span><div class="stat-label">AI Insights</div></div>
        `;
    }

    const insightsGrid = document.getElementById('insightsGrid');
    if (insightsGrid) {
        if (columnInsights.length > 0) {
            insightsGrid.innerHTML = columnInsights.map(insight => `
                <div class="insight-item" data-table-id="${escapeHtml(insight.table)}" data-column-name="${escapeHtml(insight.column)}">
                    <div class="insight-column">${escapeHtml(insight.column)}</div>
                    <div class="insight-meta">📊 ${escapeHtml(formatTablePath(insight.table))} • ${escapeHtml(insight.type)}</div>
                    <div class="insight-description">
                        <div class="semantic-meaning-container"><strong>Semantic Meaning:</strong> <span class="semantic-text">${insight.semantic ? escapeHtml(insight.semantic) : ''}</span></div>

                        ${insight.relationships.length > 0 ? 
                            `<br><br><strong>Related Fields:</strong> ${insight.relationships.slice(0, 3).map(escapeHtml).join(', ')}` : ''}
                    </div>
                </div>
            `).join('');
        } else {
            insightsGrid.innerHTML = `
                <div style="grid-column:1/-1;text-align:center;padding:60px;color:#999">
                    <div style="font-size:3em;margin-bottom:20px;opacity:0.5">🤖</div>
                    <h3 style="margin-bottom:10px;color:#ccc">No AI Insights Available</h3>
                    <p>Column semantic meanings have not been generated for this schema yet.</p>
                </div>
            `;
        }
    }

    // Initialize D3 graph if D3 is available
    if (typeof d3 !== 'undefined') {
        svg = d3.select("#graph");
        if (!svg.empty()) {
            width = parseInt(svg.style("width")) || 800;
            height = parseInt(svg.style("height")) || 600;
            tooltip = d3.select("#tooltip");
            const colorScale = {database: "#4CAF50", schema: "#2196F3", table: "#FF9800"};

            initializeGraph({nodes, links}, colorScale);

            const loadingGraph = document.getElementById('loadingGraph');
            if (loadingGraph) {
                loadingGraph.style.display = 'none';
            }
        }
    } else {
        console.error('D3.js library is not loaded');
    }
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTablePath(tableId) {
    const parts = String(tableId || '').split('.');
    if (parts.length >= 3) {
        return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`;
    }
    return String(tableId || '');
}

function initializeGraph(graphData, colorScale) {
    if (!svg || !graphData.nodes || !Array.isArray(graphData.nodes)) {
        console.error('Invalid graph data or SVG element');
        return;
    }

    svg.selectAll("*").remove();

    simulation = d3.forceSimulation(graphData.nodes)
        .force("link", d3.forceLink(graphData.links).id(d => d.id).distance(d => d.type === 'relationship' ? 200 : 100))
        .force("charge", d3.forceManyBody().strength(-600))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("x", d3.forceX(width / 2).strength(0.05))
        .force("y", d3.forceY(height / 2).strength(0.05))
        .force("collision", d3.forceCollide().radius(d => d.size + 10));

    zoom = d3.zoom().scaleExtent([0.1, 4]).on("zoom", (event) => {
        container.attr("transform", event.transform);
    });
    const container = svg.append("g");
    svg.call(zoom).on("dblclick.zoom", null);

    // Create link groups
    const linkGroup = container.append("g").selectAll("g")
        .data(graphData.links)
        .enter().append("g")
        .attr('class', d => d.type === 'relationship' ? 'relationship-link-group' : 'hierarchy-link-group');

    // Create links
    const link = linkGroup.append("line")
        .attr("stroke", d => d.type === "relationship" ? "#2563eb" : "#666")
        .style("stroke", d => d.type === "relationship" ? "#2563eb" : "#666")
        .attr("stroke-opacity", d => d.type === "relationship" ? 0.9 : 0.7)
        .attr("stroke-width", d => d.type === "relationship" ? 1.5 : 2)
        .attr("stroke-dasharray", d => d.type === "relationship" ? "8, 4" : "none");

    // Create edge labels
    const edgeLabels = linkGroup.append("text")
        .attr('class', 'edge-label')
        .attr('font-size', 10)
        .attr('fill', '#2563eb')
        .text(d => d.label || '');

    // Create nodes
    const node = container.append("g").selectAll("circle")
        .data(graphData.nodes)
        .enter().append("circle")
        .attr("r", d => d.size)
        .attr("fill", d => colorScale[d.type] || "#ccc")
        .attr("stroke", "#fff")
        .attr("stroke-width", 3)
        .style("cursor", "pointer")
        .style("filter", "drop-shadow(0px 4px 8px rgba(0,0,0,0.3))")
        .call(d3.drag()
            .on("start", dragstarted)
            .on("drag", dragged)
            .on("end", dragended)
        )
        .on("mouseover", showTooltip)
        .on("mouseout", hideTooltip)
        .on("click", showNodeDetails);

    // Create labels
    const label = container.append("g").selectAll("text")
        .data(graphData.nodes)
        .enter().append("text")
        .text(d => d.name)
        .attr("font-size", d => Math.max(11, d.size / 2.2))
        .attr("text-anchor", "middle")
        .attr("dy", "0.35em")
        .attr("fill", "#333")
        .style("pointer-events", "none")
        .style("user-select", "none")
        .style("font-weight", "600");

    // Simulation tick function
    simulation.on("tick", () => {
        link.attr("x1", d => d.source.x)
            .attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x)
            .attr("y2", d => d.target.y);

        node.attr("cx", d => d.x)
            .attr("cy", d => d.y);

        label.attr("x", d => d.x)
             .attr("y", d => d.y);

        edgeLabels
            .attr('x', d => (d.source.x + d.target.x) / 2)
            .attr('y', d => (d.source.y + d.target.y) / 2)
            .attr('transform', d => {
                const angle = Math.atan((d.target.y - d.source.y) / (d.target.x - d.source.x)) * 180 / Math.PI;
                return `rotate(${angle}, ${(d.source.x + d.target.x) / 2}, ${(d.source.y + d.target.y) / 2})`;
            });
    });

    setTimeout(fitToScreen, 500);
}

// Drag functions
function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}

function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
}

function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    if (!physicsEnabled) {
        d.fx = event.x;
        d.fy = event.y;
    } else {
        d.fx = null;
        d.fy = null;
    }
}

// Tooltip functions
function showTooltip(event, d) {
    if (!tooltip) return;

    const transform = d3.zoomTransform(svg.node());
    const [screenX, screenY] = transform.apply([d.x, d.y]);

    let content = `<strong>${escapeHtml(d.name)}</strong><br><span style="color:#2563eb">Type:</span> ${escapeHtml(d.type)}`;
    if (d.columnCount) content += `<br><span style="color:#2563eb">Columns:</span> ${d.columnCount}`;
    if (d.tableType) content += `<br><span style="color:#2563eb">Table Type:</span> ${escapeHtml(d.tableType)}`;

    tooltip.html(content)
        .style("left", `${screenX}px`)
        .style("top", `${screenY + d.size + 10}px`)
        .style("opacity", 1);
}

function hideTooltip() {
    if (tooltip) {
        tooltip.style("opacity", 0);
    }
}

// Node details function
function showNodeDetails(event, d) {
    let details = `<div class="node-info"><div class="node-name">${escapeHtml(d.name)}</div><div class="node-details"><strong>Type:</strong> ${escapeHtml(d.type)}<br><strong>Full Path:</strong> ${escapeHtml(d.id)}<br>${d.schemaName ? `<strong>Schema:</strong> ${escapeHtml(d.schemaName)}<br>` : ''}${d.tableName ? `<strong>Table:</strong> ${escapeHtml(d.tableName)}<br>` : ''}<strong>Hierarchy Level:</strong> ${d.level}<br>${d.columnCount ? `<strong>Column Count:</strong> ${d.columnCount}<br>` : ''}${d.tableType ? `<strong>Table Type:</strong> ${escapeHtml(d.tableType)}<br>` : ''}${d.parent ? `<strong>Parent Node:</strong> ${escapeHtml(d.parent)}<br>` : ''}</div></div>`;

    const editNodeBtn = document.getElementById('editNodeBtn');
    const saveNodeBtn = document.getElementById('saveNodeBtn');

    if (d.type === 'table' && graphDataStore.relationships && Array.isArray(graphDataStore.relationships)) {
        const connectedRelations = graphDataStore.relationships.filter(rel => rel.source === d.id || rel.target === d.id);
        if (connectedRelations.length > 0) {
            editNodeBtn.style.display = 'inline-block';
            let relationsHtml = '<div class="node-info" style="margin-top:10px;"><div class="node-name">Relationships</div><div class="node-details"><ul class="relationship-list">';
            connectedRelations.forEach(rel => {
                const isSource = rel.source === d.id;
                const otherTable = formatTablePath(isSource ? rel.target : rel.source);
                const otherTableId = isSource ? rel.target : rel.source;
                const relationType = rel.type.replace(/_/g, ' ');
                relationsHtml += `<li data-source-id="${escapeHtml(d.id)}" data-target-id="${escapeHtml(otherTableId)}" data-old-type="${escapeHtml(rel.type)}"> • <strong class="relationship-type">${escapeHtml(relationType)}</strong> ${isSource ? 'to' : 'from'} <strong>${escapeHtml(otherTable)}</strong></li>`;
            });
            relationsHtml += '</ul></div></div>';
            details += relationsHtml;
        } else {
            editNodeBtn.style.display = 'none';
            saveNodeBtn.style.display = 'none';
        }
    } else {
        editNodeBtn.style.display = 'none';
        saveNodeBtn.style.display = 'none';
    }

    const nodeDetailsElement = document.getElementById('nodeDetails');
    if (nodeDetailsElement) {
        nodeDetailsElement.innerHTML = details;
    }
    highlightConnectedNodes(d);
}

function resetGraph() {
    if (!svg) return;
    svg.selectAll("circle").style("opacity", 1).style("stroke", "#fff").style("stroke-width", 3);
    svg.selectAll("line").style("opacity", d => d.type === "relationship" ? 0.9 : 0.7);
    svg.selectAll("text").style("opacity", 1);
    if (simulation) {
        simulation.alpha(1).restart();
    }
    const nodeDetailsElement = document.getElementById('nodeDetails');
    if (nodeDetailsElement) {
        nodeDetailsElement.innerHTML = '<p style="color:#999;text-align:center;padding:30px;font-style:italic">Click on any node in the graph to view detailed information</p>';
    }
}

function togglePhysics() {
    physicsEnabled = !physicsEnabled;
    if (physicsEnabled) {
        if (simulation) {
            simulation.alpha(1).restart();
            simulation.nodes().forEach(d => {
                d.fx = null;
                d.fy = null;
            });
        }
    } else {
        if (simulation) {
            simulation.stop();
        }
    }
}

function toggleRelationships() {
    relationshipsVisible = !relationshipsVisible;
    if (svg) {
        svg.selectAll('.relationship-link-group').style('display', relationshipsVisible ? 'block' : 'none');
    }
}

// Highlight connected nodes
function highlightConnectedNodes(selectedNode) {
    if (!svg) return;

    svg.selectAll("circle").style("opacity", 0.3);
    svg.selectAll("line").style("opacity", 0.1);
    svg.selectAll("text").style("opacity", 0.3);

    const connectedNodes = new Set([selectedNode.id]);

    svg.selectAll("line")
        .filter(l => l.source.id === selectedNode.id || l.target.id === selectedNode.id)
        .style("opacity", 1)
        .each(l => {
            connectedNodes.add(l.source.id);
            connectedNodes.add(l.target.id);
        });

    svg.selectAll("circle")
        .filter(n => connectedNodes.has(n.id))
        .style("opacity", 1);

    svg.selectAll("circle")
        .filter(n => n.id === selectedNode.id)
        .style("stroke", "#cc6600")
        .style("stroke-width", 5);

    svg.selectAll("text")
        .filter(d => connectedNodes.has(d.id))
        .style("opacity", 1);
}




function toggleEditMode() {
    isEditMode = !isEditMode;
    const editBtn = document.getElementById('editInsightsBtn');
    const saveBtn = document.getElementById('saveInsightsBtn');
    const containers = document.querySelectorAll('.semantic-meaning-container');

    if (editBtn) editBtn.style.display = isEditMode ? 'none' : 'inline-block';
    if (saveBtn) saveBtn.style.display = isEditMode ? 'inline-block' : 'none';

    containers.forEach(container => {
        const textSpan = container.querySelector('.semantic-text');
        const currentText = textSpan ? textSpan.textContent : '';

        if (isEditMode) {
            container.innerHTML = `<strong>Semantic Meaning:</strong> <input type="text" class="semantic-input" style="width: 80%; min-height: 36px; border: 2px solid #2563eb; border-radius: 6px; padding: 6px 10px; font-family: inherit; font-size: 1rem; line-height: 1.4; box-sizing: border-box;" value="${escapeHtml(currentText)}">`;
        } else {
            const input = container.querySelector('.semantic-input');
            const newText = input ? input.value : currentText;
            container.innerHTML = `<strong>Semantic Meaning:</strong> <span class="semantic-text">${escapeHtml(newText)}</span>`;
        }
    });
}

function saveChanges() {
    const insightItems = document.querySelectorAll('.insight-item');
    const updatePromises = [];

    insightItems.forEach(item => {
        const input = item.querySelector('.semantic-input');
        if (input) {
            const tableId = item.dataset.tableId;
            const columnName = item.dataset.columnName;
            const newMeaning = input.value;

            const promise = fetch('/api/update-column-semantic-meaning', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    table_id: tableId,
                    column_name: columnName,
                    semantic_meaning: newMeaning,
                }),
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Failed to save semantic_meaning for ' + columnName);
                }
                return response.json();
            })
            .catch(error => console.error('Save error:', error));

            updatePromises.push(promise);
        }
    });

    Promise.all(updatePromises).then(() => {
        console.log('All semantic_meaning changes saved.');
        toggleEditMode();
    }).catch(err => {
        console.error("Error saving one or more semantic meanings.", err);
        toggleEditMode();
    });
}

function toggleNodeEditMode() {
    isNodeEditMode = !isNodeEditMode;
    const editBtn = document.getElementById('editNodeBtn');
    const saveBtn = document.getElementById('saveNodeBtn');
    const relationshipItems = document.querySelectorAll('#nodeDetails .relationship-list li');

    editBtn.style.display = isNodeEditMode ? 'none' : 'inline-block';
    saveBtn.style.display = isNodeEditMode ? 'inline-block' : 'none';

    relationshipItems.forEach(item => {
        const typeElement = item.querySelector('.relationship-type');
        if (isNodeEditMode) {
            const currentType = typeElement.textContent;
            // Make a larger, comfortable input for editing
            typeElement.innerHTML = `<input type="text" class="relationship-type-input" style="display:block; width: 100%; min-height: 44px; border: 2px solid #2563eb; border-radius: 6px; padding: 10px 12px; font-family: inherit; font-size: 1rem; line-height: 1.4; box-sizing: border-box;" value="${escapeHtml(currentType)}">`;

            const deleteBtn = document.createElement('span');
            deleteBtn.className = 'delete-rel-btn';
            deleteBtn.innerHTML = ' 🗑️';
            deleteBtn.style.cursor = 'pointer';
            deleteBtn.onclick = () => {
                item.classList.toggle('marked-for-deletion');
                item.style.textDecoration = item.classList.contains('marked-for-deletion') ? 'line-through' : 'none';
            };
            item.appendChild(deleteBtn);
        } else {
            const input = item.querySelector('.relationship-type-input');
            const newType = input ? input.value : typeElement.textContent;
            typeElement.innerHTML = escapeHtml(newType);
            item.querySelector('.delete-rel-btn')?.remove();
        }
    });
}

async function saveNodeChanges() {
    const relationshipItems = document.querySelectorAll('#nodeDetails .relationship-list li');
    const promises = [];

    relationshipItems.forEach(item => {
        const sourceId = item.dataset.sourceId;
        const targetId = item.dataset.targetId;
        const oldType = item.dataset.oldType;
        const input = item.querySelector('.relationship-type-input');
        const newType = input ? input.value.replace(/\s+/g, '_') : oldType; // Sanitize new type

        if (item.classList.contains('marked-for-deletion')) {
            promises.push(fetch('/api/delete-relationship', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    source_table_id: sourceId, 
                    target_table_id: targetId, 
                    relationship_type: oldType 
                })
            }));
        } else if (newType !== oldType.replace(/_/g, ' ')) {
            promises.push(fetch('/api/update-relationship', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    source_table_id: sourceId, 
                    target_table_id: targetId, 
                    old_relationship_type: oldType, 
                    new_relationship_type: newType 
                })
            }));
        }
    });

    await Promise.all(promises);
    console.log('Node changes saved.');
    toggleNodeEditMode(); // Switch back to view mode

    // Refetch graph data to show changes
    const mainContainer = document.getElementById('mainContainer');
    if(mainContainer) mainContainer.style.display = 'none';
    const loadingScreen = document.getElementById('loadingScreen');
    if(loadingScreen) loadingScreen.style.display = 'block';

    // Re-trigger the initial fetch
    document.dispatchEvent(new Event('DOMContentLoaded'));
}

// Placeholder for fitToScreen function if not defined elsewhere
function fitToScreen() {
    if (!svg || !zoom) return;

    const bounds = svg.select('g').node().getBBox();
    const fullWidth = width;
    const fullHeight = height;
    const widthScale = fullWidth / bounds.width;
    const heightScale = fullHeight / bounds.height;
    const scale = Math.min(widthScale, heightScale) * 0.8;

    const translate = [
        fullWidth / 2 - scale * (bounds.x + bounds.width / 2),
        fullHeight / 2 - scale * (bounds.y + bounds.height / 2)
    ];

    svg.transition()
        .duration(750)
        .call(zoom.transform, d3.zoomIdentity.translate(translate[0], translate[1]).scale(scale));
}
```

```python
import json as _json
import subprocess
import sys
import time
import urllib.request


def _launch_dashboard():
    if not NEO4J_SECTION_ENABLED:
        print("Section 11 disabled (see Step 0). Skipping dashboard launch.")
        return None

    required = ["graph_server.py", "index.html", "style.css", "script.js"]
    missing = [f for f in required if not (DASHBOARD_DIR / f).exists()]
    if missing:
        print(f"Dashboard files missing in {DASHBOARD_DIR}: {missing}.")
        print("Run the four %%writefile cells above first, then re-run this cell.")
        return None

    previous_proc = globals().get("_dashboard_proc")
    if previous_proc is not None and getattr(previous_proc, "poll", lambda: None)() is None:
        print(f"Stopping previous dashboard process (pid={previous_proc.pid}) before restart.")
        previous_proc.terminate()
        try:
            previous_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            previous_proc.kill()
            previous_proc.wait(timeout=5)

    env = os.environ.copy()
    env["NEO4J_URI"] = NEO4J_URI
    env["NEO4J_USER"] = NEO4J_USER
    env["NEO4J_PASSWORD"] = NEO4J_PASSWORD
    env["PYTHONUNBUFFERED"] = "1"

    log_path = DASHBOARD_DIR / "uvicorn.log"
    log_fh = open(log_path, "w")

    cmd = [
        sys.executable, "-m", "uvicorn", "graph_server:app",
        "--host", "127.0.0.1", "--port", str(DASHBOARD_PORT),
        "--app-dir", str(DASHBOARD_DIR),
        "--log-level", "warning",
    ]

    try:
        proc = subprocess.Popen(cmd, env=env, stdout=log_fh,
                                stderr=subprocess.STDOUT, cwd=str(DASHBOARD_DIR))
    except Exception as e:
        print(f"Failed to spawn uvicorn: {e}")
        log_fh.close()
        return None

    print(f"Dashboard starting (pid={proc.pid}) on port {DASHBOARD_PORT}; log -> {log_path}")

    url = f"http://127.0.0.1:{DASHBOARD_PORT}"
    ready = False
    for i in range(20):
        time.sleep(1)
        if proc.poll() is not None:
            print(f"Server process exited early (rc={proc.returncode}). See {log_path} for details.")
            return proc
        try:
            with urllib.request.urlopen(f"{url}/api/knowledge-graph", timeout=2) as r:
                _ = _json.loads(r.read())
                print(f"Dashboard ready after ~{i+1}s")
                ready = True
                break
        except Exception:
            continue

    if ready:
        print(f"\nDashboard URL: {url}")
        try:
            from IPython.display import display, Markdown
            display(Markdown(f"**[Open Neo4j Knowledge Graph Dashboard]({url})**"))
        except Exception:
            pass
    else:
        print(f"Dashboard did not respond at {url} within 20s. "
              f"Check {log_path} (Neo4j unreachable is the most common cause).")
        print("No dashboard link emitted because the graph API was not ready.")

    print(f"\nTo stop the dashboard later, run:  kill {proc.pid}")
    return proc


_dashboard_proc = _launch_dashboard()
```

<a id="notes-assumptions-and-extension-points"></a>

---

## 備註、假設與擴充點

### 這份 Cookbook 的設計用途

這份 cookbook 是一個精簡、自給自足的 agent 式資料庫變更流程示範。它要展示怎麼組合：

- 分階段的 agent 編排
- 型別化的中間輸出
- 選配的 retrieval 上下文
- 確定性的 guardrail
- trace instrumentation
- artifact 產生
- Promptfoo eval

這個流程刻意做成可攜，不依賴專案專屬的外部 module、本機 vector database、graph database 或即時的資料倉儲連線。零售範例刻意寫得具體，但同樣的分階段模式可以調整到其他需要 schema 變更分析、實作規劃和審查的領域。

### 這份 Cookbook 不做的事

這份 notebook 不會：

- 對資料庫執行 SQL
- 檢視即時的 schema catalog
- 開 pull request
- 修改 production 基礎設施
- 用資料庫 parser 驗證 SQL
- 強制執行組織專屬的 migration 標準
- 取代人工 code review

產生的 SQL 應該當成待審查的草稿。

### Tracing 與敏感資料

為了發布時的衛生，notebook 預設用遮蔽過的 trace。只有在非敏感的 demo 執行、而且刻意要保留 prompt 和輸出 payload 時，才把 `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=true`。

在拿這個流程處理敏感的企業資料之前，請先檢查：

- `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA`
- API key 的處理方式
- PDF 上傳政策
- 資料保存期限的預期
- 產生出來的 artifact 的存取控制

### 選配的 PDF RAG

選配的 RAG 路徑使用 OpenAI Vector Stores 和 Agents SDK 的 `FileSearchTool`。

當影響分析應該以參考 PDF 為依據時很有用，例如：

- 介面設計文件
- 欄位實作定義
- schema 文件
- lineage 文件
- 下游依賴筆記

vector store 設定成閒置一天後自動過期。你也可以在清理區段立刻刪掉它。

### Promptfoo Eval 路徑

Promptfoo 區段會在下面這個路徑產生 runtime 檔案：

```text
artifacts/promptfoo/
```

產生的 core module 會注入目前 notebook 的 prompt 字串，所以重跑產生 cell 之後，prompt 和 `CHANGE_TEXT` 的修改都會反映出來。

預設的 eval 流程包含：

- 確定性的 input preflight
- 針對目前需求的一個 parse-only eval
- 針對目前需求的一個 full-flow eval

把 `RUN_EXTRA_REGRESSION_CASES = True` 就會加入選配的 regression fixture。

### 建議的 Production 擴充

要做成 production 等級的實作，可以考慮加上：

- schema catalog 查詢
- 資料庫專屬的 SQL 驗證
- SQL 格式化與 lint
- 整合 migration framework
- 自動建立 pull request
- 整合 data lineage 圖
- 核准流程
- 針對破壞性變更的政策檢查
- 更完整的 eval 套件
- golden test fixture
- 組織專屬的 SQL 範本
- 各環境專屬的部署計畫

### 建議的 Review 檢查清單

在把產生的輸出用在真實實作之前，請檢查：

- 解析出的 target schema 和 table
- 解析出的 operations
- 資料型別和 nullability
- backfill 邏輯
- index 策略
- 下游傳遞的假設
- prechecks 和 postchecks
- rollback 的可行性
- 產生的 SQL 方言相容性
- 驗證問題
- trace 輸出
- 存下來的 artifact 內容
- Promptfoo eval 結果

<a id="contributors"></a>

---

## 貢獻者

這份 cookbook 是 OpenAI 和 [Altimetrik](https://www.altimetrik.com/) 的共同合作成果。

- [Shikhar Kwatra](https://www.linkedin.com/in/shikharkwatra/)
- [Atharva Joshi](https://www.linkedin.com/in/attharvaj3147/)
- [Mohan Kocherlakota](https://www.linkedin.com/in/mohan-kocherlakota/)
- [Adam Horvath](https://www.linkedin.com/in/horadam/)
- [Shashwat Jha](https://www.linkedin.com/in/shashjha/)


## 重點整理

- 不要叫一個模型直接吐出最終 SQL，把任務拆成 parse、impact、plan、SQL 四個專職 agent，出問題時才知道是哪一階段開始錯。
- 每個階段用 Pydantic model 加 `AgentOutputSchema` 規定輸出形狀，下游拿到的是契約，不是自由文字。
- 確定性的 guardrail 補足模型的不穩定，專門抓 nullable 變成 `NOT NULL`、漏掉 backfill 或 index 這類無聲失敗。
- 整個流程的結果收進一個可稽核的 `bundle` 並存成 JSON，review、debug 和 regression 比對都靠它。
- Promptfoo 在另一個 process 跑，所以要從 notebook 狀態寫出 provider、assertion 和 config，這樣改 prompt 後 eval 才跟著更新。

## 練習

1. 把 `CHANGE_TEXT` 改成要求 `NOT NULL` 的欄位（例如 `TIER_CODE VARCHAR(10) NOT NULL`），重跑 Stages 3-4 guardrail，觀察 nullability 的檢查怎麼反映這個變化。
2. 在 Stage 5 的 SQL 檢查裡，加一條規則：如果需求提到「unique」，SQL 必須包含 `UNIQUE`，然後拿一份沒有 unique 的 SQL 測試它會不會報錯。
3. 設定 `RUN_EXTRA_REGRESSION_CASES = True`，並自己新增一個 regression fixture（例如改 `DIM_CUSTOMER` 的欄位型別），重新產生 Promptfoo config 後跑 eval，看 parse-only 和 full-flow 哪個先失敗。
