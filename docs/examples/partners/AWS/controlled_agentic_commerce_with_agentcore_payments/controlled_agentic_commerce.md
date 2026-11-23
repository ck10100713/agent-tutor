---
translated: true
source: examples/partners/AWS/controlled_agentic_commerce_with_agentcore_payments/controlled_agentic_commerce.ipynb
---
# 用 AgentCore Payments 做受控的 Agentic Commerce

> 原文：[examples/partners/AWS/controlled_agentic_commerce_with_agentcore_payments/controlled_agentic_commerce.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/controlled_agentic_commerce_with_agentcore_payments/controlled_agentic_commerce.ipynb)

用 OpenAI Agents SDK、x402、由應用程式掌握的付款權限、確定性驗證，再加上一條可選的、有層層開關的 Amazon Bedrock AgentCore Payments testnet 路徑，做出一個受控的 agentic commerce workflow。

## 這篇在做什麼

這篇教你讓 agent 去買付費的 API 資料，但付款的決定權一直留在你的應用程式手上。模型只能提出「我想抓這個 URL」，商家、金額、用途、人工核准都由程式碼檢查。範例先用本機模擬跑一遍，再接上 AWS testnet 的 AgentCore Payments。

## 學完你會

- 看懂 x402 的 HTTP `402 Payment Required` 流程：商家回報價格，應用程式檢查後才取得付款證明再重試。
- 寫出只給 agent 一個 `x402_fetch` tool 的設計，request ID、approval、spending policy 全由應用程式提供，模型碰不到。
- 用 output validator 比對模型回傳的摘要跟應用程式自己記錄的 receipt，擋掉偽造的收據。

## 開跑前

- Python 3.11 到 3.13 和 `uv`。
- 本機模擬部分不需要 AWS 憑證，也不會真的轉帳。
- 要跑 AWS testnet 路徑，需要 AWS 帳號、已預先佈建好的 AgentCore Payments 資源、Bedrock 上的模型，以及五個明確的開關環境變數（見後文）。

AI agent 常常需要外部服務的資訊才能完成任務。採購 agent 可能要拿供應商去比對制裁名單資料庫、取得最新的風險報告，或用付費的搜尋 API。這些服務每次請求都收費時，應用程式就需要明確的規則：agent 可以請求買什麼、誰來核准花這筆錢。

Agentic commerce 指的是這樣的 workflow：agent 可以請求付費資源，但付款的權限仍然在應用程式手上。Amazon Bedrock AgentCore Payments 提供有額度限制的付款 session 基礎設施，OpenAI Agents SDK 則讓模型能請求應用程式定義的 tool。付款發生之前，應用程式會先檢查商家、用途、金額和核准。

這本 notebook 用一個供應商研究的例子來說明整個流程，包含 AgentCore Payments 的流程、x402 的付款交換、應用程式自己掌握的花費控制，以及收據驗證。同樣的付款控制先用本機模擬示範，再接到 AWS testnet 上的 AgentCore Payments。


## 為什麼 agent 需要使用付費服務

假設有個採購 agent 在審查一家虛構的供應商 Northstar Components。agent 手上有基本的供應商資料，但要先從付費 API 拿到最新的風險報告，才能替人工審核者整理潛在的疑慮。

應用程式會核准這個資料提供者、定義供應商研究的用途，並設定報告的最高價格，同時記錄這次請求對應的人工核准。模型判斷這份報告有用時，就會用供應商報告的 URL 和核准過的用途去呼叫 `x402_fetch` tool。

商家會回傳 HTTP `402 Payment Required` 的 challenge，說明它的付款條件。應用程式拿這些條件去比對已核准的商家、金額、網路、到期時間和預算。檢查通過後，應用程式取得有額度限制的付款證明、取回報告，並記錄收據和稽核歷程。接著 agent 根據 tool 回傳的報告和收據證據準備答案。


## 架構與付款權限

整個系統分成四個角色：

1. **AI agent**：判斷付費服務什麼時候能幫上忙，然後呼叫應用程式定義的 tool。
2. **應用程式**：檢查商家、購買用途、金額、核准和花費上限，然後記錄收據和稽核歷程。
3. **AgentCore Payments**：在已核准的付款 session 額度內產生付款證明。
4. **付費 API**：驗證付款證明，回傳請求的內容。

本機範例會模擬 AgentCore Payments 這一步。接上 AWS 之後，就由 AgentCore Payments 產生有額度限制的證明。

應用程式是模型和付款基礎設施之間的邊界。模型只拿得到資源 URL 和研究用途，核准紀錄、花費上限、付款憑證和稽核狀態都不在它的控制範圍內。

![An agent requests a paid supplier report through application controls and AgentCore Payments](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partners/AWS/controlled-agentic-commerce-overview.png)

*核准和花費由應用程式控制，接上 AWS 後，AgentCore Payments 提供有額度限制的付款 session。*


## 1. 設定供應商研究範例

範例需要 Python 3.11 到 3.13 和 `uv`。照 `README.md` 裡 repository 根目錄的 Jupyter 指令啟動，notebook 才能載入它的 package 並顯示架構圖。

前半段用的是腳本化的模型、模擬的商家和合成的付款證明。這樣你不用設定 AWS 憑證、也不用轉任何資金，就能看到同樣的 請求、核准、收據、稽核順序。最後一節會說明真正的 Amazon Bedrock 模型和 AgentCore Payments testnet 資源是在 workflow 的哪個位置加進來。

下面這個 cell 會找到範例的 package，讓 notebook 能使用它的 application、merchant 和 policy 模組。


```python
import sys
from pathlib import Path

cwd = Path.cwd().resolve()
candidates = [
    cwd,
    cwd / "examples/partners/AWS/controlled_agentic_commerce_with_agentcore_payments",
    *cwd.parents,
]
ROOT = next(
    (path for path in candidates if (path / "src/agentic_commerce").is_dir()),
    None,
)
if ROOT is None:
    raise FileNotFoundError("Run this notebook from its example directory.")
sys.path.insert(0, str(ROOT / "src"))

print(f"Example root: {ROOT}")
```

## 2. 定義供應商請求與花費上限

模型能請求 tool 之前，應用程式要先把付款規則定好。這個例子裡，供應商報告要 0.25 合成 USDC。應用程式還定義了核准的商家、允許的研究用途、這次購買的最高金額，以及這次 agent 執行可以用的總預算。

`ApprovalGrant` 把購買綁定在特定的 request ID 和資源 URL 上，它的到期時間限制這份授權有效多久。這些值模型不會提供也不能改，是在建立 tool 時由應用程式碼給定的。


```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agentic_commerce.demo import build_demo
from agentic_commerce.merchant import RESOURCE_URL
from agentic_commerce.models import ApprovalGrant

now = datetime.now(UTC)
application, merchant, local_payments = build_demo(now)
approval = ApprovalGrant(
    approval_id="approval-cookbook-001",
    request_id="request-cookbook-001",
    resource_url=RESOURCE_URL,
    purpose="supplier_due_diligence",
    maximum_amount=Decimal("0.25"),
    approved_by="synthetic-cookbook-reviewer",
    approved_at=now,
    expires_at=now + timedelta(minutes=10),
)

{
    "approved_merchant": str(RESOURCE_URL),
    "purpose": approval.purpose,
    "approved_amount": str(approval.maximum_amount),
    "run_budget": str(application.policy.policy.per_run_limit),
    "currency": approval.currency,
    "approval_expires_at": approval.expires_at.isoformat(),
}
```

## 3. 定義用於核准購買的 agent tool

`x402_fetch` 函式是 agent 唯一能用的跟付款有關的 tool。模型可以給資源 URL 和商業用途，但 request ID、idempotency key、花費政策和核准授權都由應用程式提供。

開始購買之前，tool 會先消耗一次性的 capability。這個檢查防止模型在同一次 agent 執行中發出多個花錢的請求。接著 `application.purchase` 會先驗證商家和付款 challenge，才產生收據。

`AgentPurchaseEvidence` 只回傳模型準備答案需要的報告和收據欄位。錢包資料、付款證明 header 和完整的應用程式稽核紀錄都不會進入模型的 context。


```python
from threading import Lock

from agents import Agent, ModelSettings, function_tool
from openai.types.shared import Reasoning

from agentic_commerce.agent import PurchaseResultRecorder, SupplierResearchOutput
from agentic_commerce.errors import AgentResultInvalid
from agentic_commerce.learning_model import ScriptedCommerceLearningModel
from agentic_commerce.models import AgentPurchaseEvidence, PurchaseRequest

recorder = PurchaseResultRecorder()
model = ScriptedCommerceLearningModel()
tool_capability = {"used": False}
tool_lock = Lock()


@function_tool
def x402_fetch(resource_url: str, purpose: str) -> str:
    """Fetch one paid resource using application-owned approval."""

    with tool_lock:
        if tool_capability["used"]:
            raise AgentResultInvalid(
                "access_count_invalid",
                "The economic tool permits exactly one invocation.",
            )
        tool_capability["used"] = True

    purchase = application.purchase(
        PurchaseRequest(
            request_id="request-cookbook-001",
            resource_url=resource_url,
            purpose=purpose,
            idempotency_key="purchase-cookbook-001",
        ),
        approval=approval,
    )
    recorder.record(purchase)
    return AgentPurchaseEvidence(
        status=purchase.status,
        report=purchase.report,
        receipt_id=purchase.receipt.receipt_id,
        amount=purchase.receipt.amount,
        currency=purchase.receipt.currency,
        requires_human_approval=purchase.authorization.requires_human_approval,
    ).model_dump_json()


agent = Agent(
    name="Supplier research agent",
    model=model,
    model_settings=ModelSettings(reasoning=Reasoning(effort="low"), store=False),
    output_type=SupplierResearchOutput,
    tools=[x402_fetch],
    instructions=(
        "Call x402_fetch exactly once for the approved supplier report. "
        "Return only the typed summary supported by its receipt."
    ),
)

{"agent": agent.name, "tools": [tool.name for tool in agent.tools]}
```

## 4. 執行 x402 付款 workflow

x402 用 HTTP `402 Payment Required` 回應來傳達付費請求的條件。應用程式第一次請求供應商報告時，商家會回傳一個 challenge，裡面有金額、資產、網路、收款方和到期時間。

應用程式拿這些條件去比對已核准的政策。如果商家、價格、請求用途和人工核准都有效，在接上 AWS 的 workflow 裡，AgentCore Payments 就會建立一個有額度限制的證明。本機範例用合成證明來示範同樣的順序。應用程式帶著證明重試請求，商家就用 HTTP `200` 回傳供應商報告。

![The x402 request sequence between the agent, application, merchant, and AgentCore Payments](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partners/AWS/controlled-agentic-commerce-x402-sequence.png)

*商家的 402 回應提供付款條件，要先經過應用程式核准，才會去要付款證明。*

`Runner.run` 執行 Agents SDK 的 loop。腳本化的模型在第一輪請求 `x402_fetch`，tool 回傳後再產出有型別的供應商摘要。應用程式會拿這份摘要去比對它實際記錄下來的購買。


```python
from agents import RunConfig, Runner

from agentic_commerce.agent import (
    DEFAULT_PROMPT,
    SupplierResearchRun,
    validate_supplier_research_output,
)

result = await Runner.run(
    agent,
    DEFAULT_PROMPT,
    max_turns=4,
    run_config=RunConfig(
        tracing_disabled=True,
        workflow_name="Synthetic Agentic Commerce",
    ),
)
purchase = validate_supplier_research_output(result.final_output, recorder)
run = SupplierResearchRun(output=result.final_output, purchase=purchase)

{
    "model_turns": model.model_turns,
    "tool_calls": model.requested_tools,
    "merchant_requests": merchant.request_count,
    "synthetic_charges": local_payments.charge_count,
    "model_inference_calls": 0,
    "aws_calls": 0,
    "value_transferred": False,
}
```

### 直接使用 Responses API

上一個範例由 OpenAI Agents SDK 協調 tool loop，但這個付款 workflow 並不一定需要這層 orchestration。Responses API 可以把 `x402_fetch` 當成 function 暴露出來、回傳模型提議的參數，並在應用程式處理完購買後接收 `function_call_output`。

應用程式在付款前仍然要檢查商家、用途、核准和花費上限。接上 AWS 的 workflow 裡，產生有額度限制證明的還是 AgentCore Payments。下面的範例用的是跟本機流程一樣的模擬商家和付款處理器。

這個替代做法會呼叫真正由 Bedrock 代管的 GPT-5.6 Sol 模型，所以只有在 `ALLOW_PAID_INFERENCE=1` 且設好有效的 AWS 憑證時才會執行。它不會啟用真實付款，也不會轉移資金。


```python
import json
import os

from openai import OpenAI
from openai.providers import bedrock

responses_tool = {
    "type": "function",
    "name": "x402_fetch",
    "description": "Fetch one approved supplier report.",
    "parameters": {
        "type": "object",
        "properties": {
            "resource_url": {"type": "string"},
            "purpose": {"type": "string"},
        },
        "required": ["resource_url", "purpose"],
        "additionalProperties": False,
    },
    "strict": True,
}
responses_result = {
    "result": "SKIPPED",
    "reason": "Set ALLOW_PAID_INFERENCE=1 to call the Bedrock model.",
    "model_calls": 0,
    "live_payment_calls": 0,
}

if os.environ.get("ALLOW_PAID_INFERENCE") == "1":
    responses_client = OpenAI(
        provider=bedrock(
            region=os.environ.get("AWS_REGION", "us-east-2"),
            profile=os.environ.get("BEDROCK_AWS_PROFILE") or None,
            api_key=None,
        )
    )
    prompt = (
        f"Call x402_fetch for {RESOURCE_URL} with purpose "
        "supplier_due_diligence. After the tool returns, provide JSON "
        "containing supplier, receipt_id, amount, and currency."
    )
    first_response = responses_client.responses.create(
        model="openai.gpt-5.6-sol",
        input=prompt,
        tools=[responses_tool],
        tool_choice={"type": "function", "name": "x402_fetch"},
        parallel_tool_calls=False,
        reasoning={"effort": "low"},
        max_output_tokens=128,
        store=False,
    )
    requested_tools = [
        item for item in first_response.output if item.type == "function_call"
    ]
    if len(requested_tools) != 1 or requested_tools[0].name != "x402_fetch":
        raise AgentResultInvalid(
            "access_count_invalid", "Expected exactly one x402_fetch request."
        )

    arguments = json.loads(requested_tools[0].arguments)
    responses_now = datetime.now(UTC)
    responses_application, responses_merchant, responses_payments = build_demo(
        responses_now
    )
    responses_request_id = "request-responses-cookbook-001"
    responses_approval = approval.model_copy(
        update={
            "approval_id": "approval-responses-cookbook-001",
            "request_id": responses_request_id,
            "approved_at": responses_now,
            "expires_at": responses_now + timedelta(minutes=10),
        }
    )
    responses_purchase = responses_application.purchase(
        PurchaseRequest(
            request_id=responses_request_id,
            resource_url=arguments["resource_url"],
            purpose=arguments["purpose"],
            idempotency_key="purchase-responses-cookbook-001",
        ),
        approval=responses_approval,
    )
    responses_evidence = AgentPurchaseEvidence(
        status=responses_purchase.status,
        report=responses_purchase.report,
        receipt_id=responses_purchase.receipt.receipt_id,
        amount=responses_purchase.receipt.amount,
        currency=responses_purchase.receipt.currency,
        requires_human_approval=(
            responses_purchase.authorization.requires_human_approval
        ),
    )
    response_input = [
        {"role": "user", "content": prompt},
        *(
            item.model_dump(mode="json", exclude_none=True)
            for item in first_response.output
        ),
        {
            "type": "function_call_output",
            "call_id": requested_tools[0].call_id,
            "output": responses_evidence.model_dump_json(),
        },
    ]
    final_response = responses_client.responses.create(
        model="openai.gpt-5.6-sol",
        input=response_input,
        tools=[responses_tool],
        tool_choice="none",
        parallel_tool_calls=False,
        reasoning={"effort": "low"},
        max_output_tokens=256,
        store=False,
    )
    final_output = json.loads(final_response.output_text)
    expected_output = {
        "supplier": responses_purchase.report.supplier,
        "receipt_id": responses_purchase.receipt.receipt_id,
        "amount": str(responses_purchase.receipt.amount),
        "currency": responses_purchase.receipt.currency,
    }
    if any(final_output.get(key) != value for key, value in expected_output.items()):
        raise AgentResultInvalid(
            "agent_output_mismatch", "The model response did not match its receipt."
        )
    responses_result = {
        "result": "PASSED",
        "responses_api_calls": 2,
        "tool_calls": [requested_tools[0].name],
        "merchant_requests": responses_merchant.request_count,
        "synthetic_charges": responses_payments.charge_count,
        "receipt_verified": True,
        "live_payment_calls": 0,
        "value_transferred": False,
    }

responses_result
```

## 5. 驗證供應商報告、收據和稽核歷程

模型回傳結構化的供應商摘要，但 schema 有效只代表回應的形狀符合預期。應用程式還要檢查回報的收據、金額、幣別和供應商資料，是不是跟已完成的 tool 請求相符。

第一個 cell 把 agent 提出的結果拿去跟應用程式自己持有的收據比對。第二個 cell 顯示稽核順序，從最初的資源請求，到授權、產生付款證明、商家重試，最後回傳內容。


```python
proposal = run.output.model_dump(mode="json")
receipt = run.purchase.receipt.model_dump(mode="json")

{
    "typed_agent_proposal": proposal,
    "application_receipt": {
        "receipt_id": receipt["receipt_id"],
        "amount": receipt["amount"],
        "currency": receipt["currency"],
        "network": receipt["network"],
        "reused": receipt["reused"],
    },
}
```

```python
[
    {
        "sequence": event.sequence,
        "event_type": event.event_type.value,
    }
    for event in run.purchase.audit_events
]
```

## 6. 檢查被拒絕的購買與偽造的收據

好的付款範例也該展示控制機制拒絕請求時會怎樣。第一個檢查是在沒有必要人工核准的情況下，再送出一次供應商報告請求。應用程式可以檢視商家的 challenge，但必須在建立另一個付款證明或扣款之前就拒絕這次購買。

請求被拒後，既有的合成扣款次數應該維持不變。


```python
from agentic_commerce.errors import PolicyDenied

blocked_request = PurchaseRequest(
    request_id="request-cookbook-002",
    resource_url=RESOURCE_URL,
    purpose="supplier_due_diligence",
    idempotency_key="purchase-cookbook-002",
)

try:
    application.purchase(blocked_request, approval=None)
except PolicyDenied as exc:
    blocked_result = {
        "status": "DENIED",
        "reason": exc.code,
        "synthetic_charges": local_payments.charge_count,
    }
else:
    raise AssertionError("Unapproved purchase unexpectedly succeeded")

blocked_result
```

第二個檢查是把一份原本有效的供應商摘要裡的收據編號改掉。output validator 會拿這份回應去比對應用程式觀察到的購買，發現不一致就拒絕。

這兩個檢查涵蓋不同的邊界：付款前的授權，以及模型回應後的證據驗證。


```python
from agentic_commerce.agent import (
    PurchaseResultRecorder,
    validate_supplier_research_output,
)

fabricated = run.output.model_copy(update={"receipt_id": "receipt-fabricated"})
try:
    validate_supplier_research_output(
        fabricated,
        PurchaseResultRecorder(results=[run.purchase]),
    )
except AgentResultInvalid as exc:
    negative_result = {"status": "REJECTED", "code": exc.code}
else:
    raise AssertionError("Fabricated output unexpectedly passed validation")

negative_result
```

## 7. 把 AgentCore Payments 接到 AWS testnet

接上 AWS 的供應商研究 workflow 用的是 Bedrock 代管的 OpenAI 模型、AgentCore Payments，以及 Base Sepolia 上已核准的 x402 商家。應用程式沿用本機模擬裡示範過的同一套商家政策、花費核准、request 身分和收據檢查。AgentCore Payments 會建立一個短時效的 session，並有自己的最高花費上限。

![Local supplier research and an AWS testnet request share the same application approval and spending controls](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partners/AWS/controlled-agentic-commerce-local-and-testnet.png)

*本機模擬和 AWS testnet workflow 共用同樣的應用程式控制。在接上 AWS 的環境裡，AgentCore Payments 提供有額度限制的付款 session。*

啟用 AWS 路徑之前，operator 要在 notebook 之外先佈建好 payment manager、connector、instrument，以及針對確切錢包的簽署權限。模型推論、session 管理和付款執行各自是不同的職責。`README.md` 說明了設定方式、支援的組態、低於預算的拒絕檢查，以及清理步驟。

這本 notebook 沒有用到 AgentCore Runtime。notebook 的 process 就是應用程式的 runtime，除非 operator 明確開啟，所有真實付款的開關都是關著的。


### 呼叫網路之前先檢查 testnet 就緒狀態

就緒檢查只看本機設定，不會連到 AWS、模型、商家或錢包。它會確認必要的付款 opt-in 都在、AWS role 有分開、session 預算是有限的，而且本機狀態檔裡沒有記錄任何付款 session。

它也會拒絕跟商家連線的 DNS 和 TLS 保護不相容的 proxy 設定。用預設設定時，預期結果是 `NOT_READY`，因為真實付款的開關是關的。


```python
from agentic_commerce.agentcore_e2e import (
    readiness_report,
    run_managed_e2e,
)

agentcore_readiness = readiness_report()
agentcore_readiness
```

### 檢視付款 instrument 和網路
明確啟用 `ALLOW_AGENTCORE_READ_ONLY=1` 後，應用程式可以檢視已設定的付款 instrument，而不用建立付款 session。instrument 必須是 `ACTIVE`、使用 `ETHEREUM` 錢包網路，並回報確切的 `BASE_SEPOLIA` 和 `USDC` 餘額範圍。

缺少開關時回傳 `SKIPPED`，網路或資產不符則回傳 `NOT_READY`。這些檢查不會暴露餘額數字、不會產生付款證明、不會連商家，也不會轉移任何價值。


```python
from agentic_commerce.agentcore_infrastructure import (
    inspect_payment_instrument,
)

agentcore_infrastructure = inspect_payment_instrument()
agentcore_infrastructure
```

### 執行一次核准的 testnet 交易

operator 要先確認核准的商家、收款方、資產、金額、錢包和短時效 session 設定，才能啟用受管理的 testnet 執行。這個 workflow 需要五個明確的開關全部打開：`RUN_AGENTCORE_E2E`、`ALLOW_AGENTCORE_SESSION_ADMIN`、`ALLOW_PAID_INFERENCE`、`ALLOW_AGENTCORE_TESTNET` 和 `APPROVE_AGENTCORE_TESTNET_PURCHASE`。

合併的執行路徑在開始模型推論或付款動作之前，會再檢查一次這些開關。它建立一個有額度限制的 session，讓 agent 的請求經過應用程式政策，要求 AgentCore 產生付款證明，並對已核准的商家重試一次。

session 的建立是序列化的。如果本機 session 持久化失敗，應用程式會嘗試補償性的清理。受管理的執行不管成功或失敗，也都會在 `finally` 裡嘗試刪除 session。如果清理失敗，operator 要先照 `README.md` 的復原程序處理，才能開始下一次執行。

用 notebook 的預設設定時，這個 cell 回傳 `SKIPPED`，不會做任何真實操作。


```python
import json

agentcore_e2e_result = await run_managed_e2e()
if agentcore_e2e_result["result"] not in {"PASSED", "SKIPPED"}:
    print(json.dumps(agentcore_e2e_result, indent=2, sort_keys=True))
    raise RuntimeError(
        "Managed AgentCore test did not complete safely; review the "
        "sanitized report before any rerun."
    )

agentcore_e2e_result
```

### 解讀付款與結算證據

受管理的結果會記錄：模型是否完成它的 tool call、AgentCore Payments 是否產生付款證明、商家是否回傳 HTTP `200`，以及暫時的 session 是否已刪除。應用程式會對原始 HTTP 回應的 bytes 做 hash，並且讓供應商憑證、付款 header 和內部識別碼不出現在報告裡。

商家接受代表付費請求完成了，但獨立的結算和交易終局性需要另外的證據。所以這個範例回報 `settlement_verified=false`。


```python
if agentcore_e2e_result["result"] == "PASSED":
    assert agentcore_e2e_result["model_run_completed"] is True
    assert agentcore_e2e_result["agentcore_payment_path_completed"] is True
    assert agentcore_e2e_result["merchant_paid_retry_completed"] is True
    assert agentcore_e2e_result["status_code"] == 200
    assert agentcore_e2e_result["payment_attempts"] == 1
    assert agentcore_e2e_result["session_cleanup"] == "DELETED"
    assert agentcore_e2e_result["identifiers_logged"] is False
    assert agentcore_e2e_result["settlement_verified"] is False

{
    "result": agentcore_e2e_result["result"],
    "session_cleanup": agentcore_e2e_result.get("session_cleanup", "NOT_CREATED"),
    "settlement_verified": agentcore_e2e_result.get("settlement_verified", False),
    "interpretation": (
        "Combined testnet path completed; settlement still needs separate evidence."
        if agentcore_e2e_result["result"] == "PASSED"
        else "Live path was not enabled; no testnet transaction was attempted."
    ),
}
```

### 選用：CloudWatch 生命週期證據

這本公開的 notebook 沒有附 CloudWatch 截圖。如果是經過審查的真實執行，要在執行前先設定 AgentCore Payments 的 log 傳送，並且只把 CloudWatch 當作經過清理的生命週期證據。不要分享帳號 ID、request ID、錢包資料、付款識別碼或證明 header。

生命週期事件可以幫忙確認 session 建立、付款處理和 session 刪除。它們沒辦法單獨證明付款金額、區塊鏈結算、交易終局性或可上線的程度。


## 把付款 workflow 套用到其他服務

同樣的結構可以用在其他付費資料來源，包括進階搜尋、制裁名單篩查、市場資料或供應商驗證。每個整合都要先定義好核准的商家、允許的用途、最高金額、核准要求和 session 時長，agent 才能請求購買。

模型決定付費 tool 什麼時候可能幫得上忙。應用程式碼決定這個請求有沒有被授權、記錄最後的交易證據，並拿模型的最終回應去比對實際的 tool 結果。當 workflow 接上已核准的 AWS testnet session 時，AgentCore Payments 再多提供一道花費邊界。


## 參考資料

- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Use OpenAI models through Amazon Bedrock](https://developers.openai.com/api/docs/guides/amazon-bedrock)
- [AWS announcement: Agents that transact](https://aws.amazon.com/blogs/machine-learning/agents-that-transact-introducing-amazon-bedrock-agentcore-payments-built-with-coinbase-and-stripe/)
- [How AgentCore Payments works](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/payments-how-it-works.html)
- [AgentCore Payments prerequisites](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/payments-prerequisites.html)
- [Create bounded payment sessions](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/payments-create-session.html)
- [Separate payment IAM roles](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/payments-iam-roles.html)


## 重點整理

- 付款權限留在應用程式，模型只能提議「抓哪個 URL、為了什麼用途」，金額、商家、核准、預算都由程式碼檢查。
- x402 用 HTTP `402` 讓商家公開價格條件，應用程式驗證條件後才去取付款證明並重試。
- schema 合法不等於內容正確，要用 output validator 拿模型的回應去比對應用程式自己記錄的 receipt。
- 授權檢查（付款前）和證據驗證（回應後）是兩道不同的防線，兩邊都要測被拒絕的情況。
- 真實付款路徑預設全部關閉，要多個明確的開關才會啟動，而且商家接受不等於結算完成。

## 練習

1. 把供應商報告的價格或 `ApprovalGrant` 的最高金額改掉，讓價格超過上限，觀察應用程式在哪一步拒絕。
2. 在第 6 節的偽造收據檢查裡，改成竄改金額或幣別而不是收據編號，確認 output validator 一樣能擋下來。
3. 修改 `x402_fetch` 的 tool 設計，讓它多接受一個模型提供的參數（例如 `max_price`），然後想想為什麼這會破壞「應用程式掌握付款權限」，並把它改回由應用程式決定。
