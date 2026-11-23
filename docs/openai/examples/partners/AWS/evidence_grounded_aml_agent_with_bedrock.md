---
translated: true
source: examples/partners/AWS/evidence_grounded_aml_agent_with_bedrock.ipynb
---
# 在 Amazon Bedrock 上用 Agents SDK 做 AML 分析

> 原文：[examples/partners/AWS/evidence_grounded_aml_agent_with_bedrock.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/AWS/evidence_grounded_aml_agent_with_bedrock.ipynb)

用 OpenAI Agents SDK 和 Amazon Bedrock 上的 GPT-5.6 Sol 跑一個合成資料的 AML（反洗錢）分析，用確定性的證據驗證結構化的 claim，測試失敗案例，並由應用程式自己掌控人工審核關卡。

## 這篇在做什麼

用 OpenAI Agents SDK 搭配 Amazon Bedrock 上的 GPT-5.6 Sol，對一筆合成的反洗錢案例做分析。預設走離線的確定性結果，從頭跑到尾不會呼叫模型；明確開啟旗標後才會讓 agent 用唯讀 tool 實際跑。兩條路徑都會拿確定性的計算去驗證模型提出的重要 claim。

## 學完你會

- 用 Pydantic 定義結構化輸出，讓每個 finding 都帶著 evidence ID 和計算值，可以被機器檢查
- 用型別化的 context 搭配唯讀 tool，把 agent 的資料範圍限制在單一 tenant 和單一 case
- 做出「驗證 claim 有沒有真的被證據支持」的 validator，並設計由應用程式掌控的人工審核與重新審核流程

## 開跑前

- 預設的離線路徑需要 Python 3.10 以上和 `uv`，不需要 AWS 帳號
- 要跑付費的 agent，需要 AWS 憑證（走標準 credential chain）和 `openai.gpt-5.6-sol` 的存取權限
- 環境變數：`RUN_ANALYSIS_DEMO=true` 跑分析 agent，`RUN_DRAFTING_DEMO=true` 跑草稿 agent，有 named profile 的話先設 `AWS_PROFILE`

警告：這是一個合成資料的範例。警示（alert）只是調查的起點，不能證明有不法行為。模型提出評估，應用程式驗證結構化的 claim 並控制流程狀態，是否開始撰寫草稿由有資格的人來決定。這裡的所有資料都是合成的，不會真的送出可疑活動報告（SAR），也不是正式的合規政策實作。

## 工作流程的邊界

這份 notebook 把確定性證據、模型提案、應用程式控制、人類決定權分成四個獨立的邊界。

![Four boundaries for the regulated-investigation workflow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/partners/AWS/evidence-grounded-four-boundaries.png)


## 1. 啟動 notebook

預設的離線路徑需要 Python 3.10 以上和 `uv`。選用的付費 Bedrock 路徑還需要透過標準 credential chain 取得 AWS 憑證，以及 `openai.gpt-5.6-sol` 的存取權限。從 [openai/openai-cookbook](https://github.com/openai/openai-cookbook) 的 clone 裡執行：

```bash
cd /path/to/openai-cookbook
unset VIRTUAL_ENV
export AWS_REGION=us-east-2
uv run --with jupyterlab jupyter lab
```

打開 `examples/partners/AWS/evidence_grounded_aml_agent_with_bedrock.ipynb`。預設執行時兩個付費旗標都是關的。想跑分析 agent，在啟動 Jupyter 前設 `RUN_ANALYSIS_DEMO=true`；想跑選用的草稿 agent，設 `RUN_DRAFTING_DEMO=true`。如果你的組織用 named profile，先設 `AWS_PROFILE`。不要把 AWS 憑證貼進 notebook。


```python
%pip install -U "openai[bedrock]>=2.46.0" "openai-agents>=0.18.2" "pydantic>=2.13.0" --quiet
```

## 2. 設定 Amazon Bedrock

兩個付費 demo 都要明確設定環境旗標才會跑。只要有一個旗標開著，SDK 就會用 AWS credential chain，並在付費推論前用另一個 client 透過 Bedrock Mantle 的 discovery endpoint 列出模型。兩個旗標都關著時，這個 cell 不會建立 client，也不會呼叫 AWS。


```python
import json
import math
import os
from datetime import datetime
from typing import Literal

from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    function_tool,
    set_default_openai_api,
    set_default_openai_client,
)
from agents.items import ToolCallItem, ToolCallOutputItem
from openai import AsyncOpenAI
from openai.providers import bedrock
from openai.types.shared import Reasoning
from pydantic import BaseModel, Field

AWS_REGION = os.getenv("AWS_REGION", "us-east-2")
MODEL_ID = os.getenv("BEDROCK_MODEL", "openai.gpt-5.6-sol")
RUN_ANALYSIS_DEMO = (
    os.getenv("RUN_ANALYSIS_DEMO", "false").casefold() == "true"
)
RUN_DRAFTING_DEMO = (
    os.getenv("RUN_DRAFTING_DEMO", "false").casefold() == "true"
)
RUN_BEDROCK_DEMOS = RUN_ANALYSIS_DEMO or RUN_DRAFTING_DEMO

set_default_openai_api("responses")

if RUN_BEDROCK_DEMOS:
    client = AsyncOpenAI(provider=bedrock(region=AWS_REGION))
    models_client = AsyncOpenAI(
        provider=bedrock(
            region=AWS_REGION,
            base_url=(
                f"https://bedrock-mantle.{AWS_REGION}.api.aws/v1"
            ),
        )
    )
    set_default_openai_client(client, use_for_tracing=False)
    available_models = await models_client.models.list()
    available_model_ids = {model.id for model in available_models.data}
    if MODEL_ID not in available_model_ids:
        raise RuntimeError(
            f"{MODEL_ID!r} is not visible in {AWS_REGION}. "
            "Verify the AWS account, Region, and Bedrock model access."
        )
    print({"region": AWS_REGION, "model": MODEL_ID, "preflight": "passed"})
else:
    print("Paid Bedrock demonstrations disabled; no AWS call was made.")
```

## 3. 載入合成案例

這個案例是同一天三筆現金入帳，接著一筆外匯出款。金額刻意挑得好重現，它們是 demo 用的規則，不是法規門檻。每個應用程式 context 都由 factory 建立一份全新的型別化案例。


```python
DEMO_CASH_AMOUNT_MIN = 9_000
DEMO_CASH_AMOUNT_MAX = 10_000
DEMO_RAPID_MOVEMENT_RATIO = 0.90
DEMO_REQUIRED_CASH_CREDITS = 3

class Transaction(BaseModel):
    id: str
    timestamp: str
    direction: Literal["CREDIT", "DEBIT"]
    channel: Literal["CASH", "WIRE"]
    amount: int = Field(gt=0)
    currency: str
    counterparty: str
    country_code: str


class InvestigationCase(BaseModel):
    case_id: str
    subject: str
    subject_type: Literal["BUSINESS"]
    stated_business: str
    risk_tier: Literal["STANDARD"]
    alert_reason: str
    transactions: list[Transaction]


def build_synthetic_case() -> InvestigationCase:
    return InvestigationCase(
        case_id="SYNTH-AML-001",
        subject="Northstar Imports LLC",
        subject_type="BUSINESS",
        stated_business="Wholesale home goods",
        risk_tier="STANDARD",
        alert_reason=(
            "Unusual cash activity followed by an outbound wire"
        ),
        transactions=[
            Transaction(
                id="TXN-001",
                timestamp="2026-05-04T09:20:00Z",
                direction="CREDIT",
                channel="CASH",
                amount=9200,
                currency="USD",
                counterparty="Synthetic cash deposit A",
                country_code="US",
            ),
            Transaction(
                id="TXN-002",
                timestamp="2026-05-04T11:05:00Z",
                direction="CREDIT",
                channel="CASH",
                amount=9500,
                currency="USD",
                counterparty="Synthetic cash deposit B",
                country_code="US",
            ),
            Transaction(
                id="TXN-003",
                timestamp="2026-05-04T13:40:00Z",
                direction="CREDIT",
                channel="CASH",
                amount=9800,
                currency="USD",
                counterparty="Synthetic cash deposit C",
                country_code="US",
            ),
            Transaction(
                id="TXN-004",
                timestamp="2026-05-04T16:10:00Z",
                direction="DEBIT",
                channel="WIRE",
                amount=28200,
                currency="USD",
                counterparty="Synthetic overseas supplier",
                country_code="GB",
            ),
        ],
    )


print(build_synthetic_case().model_dump_json(indent=2))
```

## 4. 定義輸出與證據 tool

輸出 schema 讓重要的 claim 可以被機器檢查。每個 finding 都帶著自己的 evidence ID 和計算值。validator 會重新計算這些值，因為光是 transaction ID 有效，並不代表 claim 有證據支持。

型別化的 `InvestigationContext` 把範圍限制在一個 tenant、一個 case、一次分析和審核歷史。每個請求都建立自己的 context 實例，透過 `Runner.run(..., context=...)` 傳進去，tool 再用 `RunContextWrapper` 存取。context 本身不是模型的輸入，每個唯讀 tool 自己決定要回傳哪些欄位。

兩個 tool 回傳原始事實，一個 tool 套用透明的 demo 檢查。這些檢查找出的是值得調查的訊號，不是意圖、不法行為，也不代表一定要申報。


```python
class Finding(BaseModel):
    finding_type: Literal["STRUCTURING_SIGNAL", "RAPID_MOVEMENT_SIGNAL"]
    title: str
    explanation: str
    evidence_ids: list[str] = Field(min_length=1)
    cash_credit_count: int = Field(ge=0)
    cash_credit_total_usd: int = Field(ge=0)
    outbound_wire_usd: int | None
    movement_ratio_percent: float | None


class RiskAssessment(BaseModel):
    case_id: str
    assessment_posture: Literal[
        "ROUTINE_REVIEW",
        "ENHANCED_REVIEW",
        "ESCALATE_FOR_QUALIFIED_REVIEW",
    ]
    executive_summary: str
    findings: list[Finding] = Field(min_length=2, max_length=2)
    information_gaps: list[str] = Field(min_length=1)
    recommended_next_steps: list[str] = Field(min_length=1)
    drafting_authorized: Literal[False]
    filing_decision: Literal["NOT_DETERMINED"]


class EvidenceCitation(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(min_length=1)


class SarDraft(BaseModel):
    case_id: str
    narrative: str
    draft_status: Literal[
        "DRAFT_READY_FOR_HUMAN_REVIEW", "INSUFFICIENT_INFORMATION"
    ]
    citations: list[EvidenceCitation] = Field(min_length=1)
    disclaimer: str


ReviewDecision = Literal["APPROVE_DRAFTING", "REJECT_DRAFTING"]
ReviewStatus = Literal[
    "PENDING_REVIEW",
    "PENDING_REREVIEW",
    "APPROVE_DRAFTING",
    "REJECT_DRAFTING",
]


class HumanReviewEvent(BaseModel):
    event: Literal["HUMAN_REVIEW"] = "HUMAN_REVIEW"
    analysis_revision: int = Field(ge=1)
    reviewer_alias: str
    decision: ReviewDecision
    rationale: str


class AnalysisRevisedEvent(BaseModel):
    event: Literal["ANALYSIS_REVISED"] = "ANALYSIS_REVISED"
    from_revision: int = Field(ge=1)
    to_revision: int = Field(ge=2)
    rework_note: str


ReviewEvent = HumanReviewEvent | AnalysisRevisedEvent


class InvestigationContext(BaseModel):
    tenant_id: str
    case: InvestigationCase
    analysis: RiskAssessment | None = None
    analysis_revision: int = Field(default=0, ge=0)
    review_status: ReviewStatus = "PENDING_REVIEW"
    review_history: list[ReviewEvent] = Field(default_factory=list)
    draft: SarDraft | None = None


def new_investigation_context() -> InvestigationContext:
    return InvestigationContext(
        tenant_id="SYNTHETIC-TENANT-001",
        case=build_synthetic_case(),
    )


run_context = new_investigation_context()
```

```python
def require_known_case(
    wrapper: RunContextWrapper[InvestigationContext],
    case_id: str,
) -> InvestigationCase:
    case = wrapper.context.case
    if case_id != case.case_id:
        raise ValueError(f"Unknown case in this request context: {case_id}")
    return case


@function_tool(failure_error_function=None)
def get_case_profile(
    wrapper: RunContextWrapper[InvestigationContext],
    case_id: str,
) -> str:
    """Return the synthetic profile and alert context for one case."""

    case = require_known_case(wrapper, case_id)
    profile = case.model_dump(exclude={"transactions"})
    return json.dumps(profile)


@function_tool(failure_error_function=None)
def list_case_transactions(
    wrapper: RunContextWrapper[InvestigationContext],
    case_id: str,
) -> str:
    """Return all synthetic transactions and their evidence identifiers."""

    case = require_known_case(wrapper, case_id)
    return json.dumps(
        [transaction.model_dump() for transaction in case.transactions]
    )


def parse_transaction_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def detect_typology_signals(
    case: InvestigationCase,
) -> list[dict[str, object]]:
    transactions = case.transactions
    cash_credits = [
        transaction
        for transaction in transactions
        if transaction.direction == "CREDIT"
        and transaction.channel == "CASH"
        and DEMO_CASH_AMOUNT_MIN
        <= transaction.amount
        < DEMO_CASH_AMOUNT_MAX
    ]
    if len(cash_credits) < DEMO_REQUIRED_CASH_CREDITS:
        return []

    activity_dates = {
        parse_transaction_timestamp(item.timestamp).date()
        for item in cash_credits
    }
    currencies = {item.currency for item in cash_credits}
    if len(activity_dates) != 1 or len(currencies) != 1:
        return []

    cash_total = sum(item.amount for item in cash_credits)
    latest_cash_timestamp = max(
        parse_transaction_timestamp(item.timestamp)
        for item in cash_credits
    )
    rapid_wires = [
        transaction
        for transaction in transactions
        if transaction.direction == "DEBIT"
        and transaction.channel == "WIRE"
        and transaction.currency in currencies
        and parse_transaction_timestamp(transaction.timestamp).date()
        in activity_dates
        and parse_transaction_timestamp(transaction.timestamp)
        > latest_cash_timestamp
        and transaction.amount
        >= cash_total * DEMO_RAPID_MOVEMENT_RATIO
    ]

    cash_ids = [item.id for item in cash_credits]
    signals = [
        {
            "finding_type": "STRUCTURING_SIGNAL",
            "evidence_ids": cash_ids,
            "cash_credit_count": len(cash_credits),
            "cash_credit_total_usd": cash_total,
            "outbound_wire_usd": None,
            "movement_ratio_percent": None,
        }
    ]
    if rapid_wires:
        wire = rapid_wires[0]
        signals.append(
            {
                "finding_type": "RAPID_MOVEMENT_SIGNAL",
                "evidence_ids": [*cash_ids, wire.id],
                "cash_credit_count": len(cash_credits),
                "cash_credit_total_usd": cash_total,
                "outbound_wire_usd": wire.amount,
                "movement_ratio_percent": round(
                    wire.amount / cash_total * 100, 1
                ),
            }
        )
    return signals


@function_tool(failure_error_function=None)
def run_typology_checks(
    wrapper: RunContextWrapper[InvestigationContext],
    case_id: str,
) -> str:
    """Return transparent demo signals and their calculated support."""

    case = require_known_case(wrapper, case_id)
    return json.dumps(detect_typology_signals(case))


print(json.dumps(detect_typology_signals(run_context.case), indent=2))
```

## 5. 執行分析 agent

instructions 要求 agent 用到全部三個 tool，並回傳型別化的結果。設了 `RUN_ANALYSIS_DEMO=true` 時，`Runner.run` 會管理付費的模型與 tool 迴圈。預設路徑用的是有標示的確定性 fixture，裡面帶著模擬的 tool call 證據，讓後面的驗證和審核 cell 不用 AWS 憑證、不用付費推論也能跑。這個 fixture 不能證明 Agents SDK 的 orchestration 真的運作。


```python
MODEL_SETTINGS = ModelSettings(
    reasoning=Reasoning(effort="medium"),
    store=False,
)

analysis_agent = Agent[InvestigationContext](
    name="Synthetic AML Analysis Agent",
    model=MODEL_ID,
    model_settings=MODEL_SETTINGS,
    output_type=RiskAssessment,
    tools=[
        get_case_profile,
        list_case_transactions,
        run_typology_checks,
    ],
    instructions=(
        "Analyze exactly one synthetic AML case. Call get_case_profile, "
        "list_case_transactions, and run_typology_checks. Copy the "
        "deterministic tool's evidence IDs and computed values into the "
        "matching structured finding fields. Do not introduce other amounts "
        "in the finding explanations. Treat signals as prompts for qualified "
        "review, not proof of intent or wrongdoing. Identify missing "
        "information. Set drafting_authorized to false and filing_decision "
        "to NOT_DETERMINED. Do not draft or file a SAR, change case state, "
        "approve your own work, or claim that filing is required. Return "
        "only the RiskAssessment schema."
    ),
)

REQUIRED_ANALYSIS_TOOLS = {
    "get_case_profile",
    "list_case_transactions",
    "run_typology_checks",
}

FINDING_TEXT = {
    "STRUCTURING_SIGNAL": (
        "Cash-credit pattern",
        "The deterministic check identified same-day cash credits.",
    ),
    "RAPID_MOVEMENT_SIGNAL": (
        "Rapid movement pattern",
        "The deterministic check identified a later outbound wire.",
    ),
}


def build_offline_assessment(
    context: InvestigationContext,
) -> RiskAssessment:
    findings = []
    for signal in detect_typology_signals(context.case):
        title, explanation = FINDING_TEXT[signal["finding_type"]]
        findings.append(
            Finding(
                finding_type=signal["finding_type"],
                title=title,
                explanation=explanation,
                evidence_ids=signal["evidence_ids"],
                cash_credit_count=signal["cash_credit_count"],
                cash_credit_total_usd=signal["cash_credit_total_usd"],
                outbound_wire_usd=signal["outbound_wire_usd"],
                movement_ratio_percent=signal["movement_ratio_percent"],
            )
        )
    return RiskAssessment(
        case_id=context.case.case_id,
        assessment_posture="ESCALATE_FOR_QUALIFIED_REVIEW",
        executive_summary=(
            "Synthetic signals require qualified review."
        ),
        findings=findings,
        information_gaps=[
            "Source-of-funds records remain unverified."
        ],
        recommended_next_steps=[
            "Obtain source records for qualified human review."
        ],
        drafting_authorized=False,
        filing_decision="NOT_DETERMINED",
    )


if RUN_ANALYSIS_DEMO:
    result = await Runner.run(
        analysis_agent,
        f"Analyze synthetic case {run_context.case.case_id}.",
        context=run_context,
        max_turns=8,
        run_config=RunConfig(
            tracing_disabled=True,
            workflow_name="Validated synthetic AML analysis",
        ),
    )
    assessment = result.final_output
    tool_calls = {
        item.raw_item.name
        for item in result.new_items
        if isinstance(item, ToolCallItem)
    }
    analysis_source = "paid Agents SDK run"
else:
    assessment = build_offline_assessment(run_context)
    tool_calls = set(REQUIRED_ANALYSIS_TOOLS)
    analysis_source = "offline fixture with simulated tool calls"

print("Analysis source:", analysis_source)
print("Tool-call evidence:", sorted(tool_calls))
print(assessment.model_dump_json(indent=2))
```

## 6. 驗證「有證據支持」，不只是引用格式正確

validator 做三種不同的檢查：

1. **引用有效：** 每個 evidence ID 都存在於這個 case 裡。
2. **claim 有支持：** 每種 finding 類型都要對上應用程式確定性程式碼回傳的交易和計算值。
3. **結構化權限：** `drafting_authorized` 必須維持 `false`，`filing_decision` 必須維持 `NOT_DETERMINED`。

schema 讓模型沒辦法透過這些結構化欄位授予自己撰寫草稿的權限，或做出申報決定。validator 沒辦法分類所有可能的自由文字改寫。敘述內容、資訊缺口、相關性和處置結果，仍然要由有資格的審核者評估。正式系統還應該加上專家審過的資料集、trace grading、對抗性案例和針對政策的測試。


```python
def validate_risk_assessment(
    candidate: RiskAssessment,
    observed_tool_calls: set[str],
    context: InvestigationContext,
) -> dict[str, bool]:
    expected = {
        signal["finding_type"]: signal
        for signal in detect_typology_signals(context.case)
    }
    valid_evidence_ids = {
        transaction.id for transaction in context.case.transactions
    }
    observed = {
        finding.finding_type: finding for finding in candidate.findings
    }
    unique_finding_types = len(observed) == len(candidate.findings)

    valid_citations = all(
        finding.evidence_ids
        and set(finding.evidence_ids).issubset(valid_evidence_ids)
        for finding in candidate.findings
    )
    supported_claims = unique_finding_types and set(observed) == set(expected)
    if supported_claims:
        for finding_type, expected_support in expected.items():
            finding = observed[finding_type]
            supported_claims = supported_claims and (
                set(finding.evidence_ids)
                == set(expected_support["evidence_ids"])
                and finding.cash_credit_count
                == expected_support["cash_credit_count"]
                and finding.cash_credit_total_usd
                == expected_support["cash_credit_total_usd"]
                and finding.outbound_wire_usd
                == expected_support["outbound_wire_usd"]
                and (
                    finding.movement_ratio_percent is None
                    and expected_support["movement_ratio_percent"] is None
                    or finding.movement_ratio_percent is not None
                    and expected_support["movement_ratio_percent"] is not None
                    and math.isclose(
                        finding.movement_ratio_percent,
                        expected_support["movement_ratio_percent"],
                        abs_tol=0.1,
                    )
                )
            )

    checks = {
        "case identity": candidate.case_id == context.case.case_id,
        "required tools": REQUIRED_ANALYSIS_TOOLS.issubset(
            observed_tool_calls
        ),
        "valid citations": valid_citations,
        "material claims supported": supported_claims,
        "structured authority denied": (
            candidate.drafting_authorized is False
            and candidate.filing_decision == "NOT_DETERMINED"
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("Assessment validation failed: " + ", ".join(failed))
    return checks


checks = validate_risk_assessment(assessment, tool_calls, run_context)
for check_name in checks:
    print("PASS:", check_name)
```

## 7. 測試負面案例

這些本機測試在不額外呼叫模型的情況下，示範失敗時的行為。捏造的金額可以用真實的 transaction ID，卻還是沒有證據支持。無效的 ID、缺少 tool call、結構化欄位宣稱權限、審核被駁回，是各自獨立的失敗模式。


```python
def expect_validation_failure(
    label: str,
    candidate: RiskAssessment,
    observed_tools: set[str],
    context: InvestigationContext,
) -> None:
    try:
        validate_risk_assessment(candidate, observed_tools, context)
    except ValueError as exc:
        print(f"PASS ({label}):", exc)
    else:
        raise AssertionError(f"Expected validation failure: {label}")


fabricated_claim = assessment.model_copy(deep=True)
fabricated_claim.findings[0].cash_credit_total_usd = 50_000
expect_validation_failure(
    "fabricated amount", fabricated_claim, tool_calls, run_context
)

invalid_citation = assessment.model_copy(deep=True)
invalid_citation.findings[0].evidence_ids = ["TXN-999"]
expect_validation_failure(
    "invalid citation", invalid_citation, tool_calls, run_context
)

missing_tool_calls = tool_calls - {"run_typology_checks"}
expect_validation_failure(
    "missing tool", assessment, missing_tool_calls, run_context
)

invalid_authority = assessment.model_copy(deep=True)
invalid_authority.drafting_authorized = True
invalid_authority.filing_decision = "FILE_REQUIRED"
expect_validation_failure(
    "structured authority", invalid_authority, tool_calls, run_context
)
```

## 8. 保留駁回紀錄，並要求明確重新審核

核准的邊界現在由應用程式掌管。它先存下通過驗證的評估，記錄一次駁回，並證明草稿仍然被擋住。接著把修訂後的評估當成新的 revision 提交，再審核一次。原本的駁回會留在 `review_history` 裡，不會被重設或覆蓋。

合成的審核者別名和型別化 context 讓整個範例可以放在一份 notebook 裡看。並行的服務必須為每個請求和每個 tenant 建立獨立的 context。正式系統要從認證取得審核者身分、對 case 和操作做授權、把 revision 和決定持久化儲存，並維護獨立治理的稽核紀錄。


```python
run_context.analysis = assessment
run_context.analysis_revision = 1
run_context.review_status = "PENDING_REVIEW"
run_context.review_history.clear()
run_context.draft = None


def record_human_review(
    context: InvestigationContext,
    reviewer_alias: str,
    decision: ReviewDecision,
    rationale: str,
) -> HumanReviewEvent:
    if context.review_status not in {
        "PENDING_REVIEW",
        "PENDING_REREVIEW",
    }:
        raise RuntimeError("The current analysis revision is not awaiting review")
    if len(rationale.strip()) < 12:
        raise ValueError("Review rationale is too short")

    event = HumanReviewEvent(
        analysis_revision=context.analysis_revision,
        reviewer_alias=reviewer_alias,
        decision=decision,
        rationale=rationale,
    )
    context.review_history.append(event)
    context.review_status = decision
    return event


def require_drafting_allowed(
    context: InvestigationContext,
) -> RiskAssessment:
    analysis = context.analysis
    history = context.review_history
    latest = history[-1] if history else None
    if not isinstance(analysis, RiskAssessment):
        raise RuntimeError(  # noqa: TRY004 - unmet workflow precondition
            "A validated analysis is required before drafting"
        )
    if (
        not isinstance(latest, HumanReviewEvent)
        or latest.decision != "APPROVE_DRAFTING"
        or latest.analysis_revision != context.analysis_revision
    ):
        raise RuntimeError(
            "The current analysis revision lacks qualified-human approval"
        )
    return analysis


def submit_revised_analysis(
    context: InvestigationContext,
    candidate: RiskAssessment,
    observed_tools: set[str],
    rework_note: str,
) -> None:
    if context.review_status != "REJECT_DRAFTING":
        raise RuntimeError("A rejected review is required before rework")
    validate_risk_assessment(candidate, observed_tools, context)
    previous_revision = context.analysis_revision
    context.analysis = candidate
    context.analysis_revision = previous_revision + 1
    context.review_status = "PENDING_REREVIEW"
    context.review_history.append(
        AnalysisRevisedEvent(
            from_revision=previous_revision,
            to_revision=previous_revision + 1,
            rework_note=rework_note,
        )
    )


record_human_review(
    run_context,
    reviewer_alias="synthetic-qualified-reviewer",
    decision="REJECT_DRAFTING",
    rationale="The information gaps require revision before drafting.",
)
try:
    require_drafting_allowed(run_context)
except RuntimeError as exc:
    print("PASS (rejected review blocks drafting):", exc)
else:
    raise AssertionError("A rejected review must block drafting")

revised_assessment = assessment.model_copy(deep=True)
revised_assessment.information_gaps.append(
    "The draft must state that source-of-funds records remain unverified."
)
submit_revised_analysis(
    run_context,
    revised_assessment,
    tool_calls,
    rework_note="Added the reviewer's unresolved source-of-funds limitation.",
)
record_human_review(
    run_context,
    reviewer_alias="synthetic-qualified-reviewer",
    decision="APPROVE_DRAFTING",
    rationale="Re-reviewed revision 2 and approved draft preparation only.",
)
require_drafting_allowed(run_context)
print(
    json.dumps(
        [event.model_dump() for event in run_context.review_history],
        indent=2,
    )
)
```

## 9. 核准之後才定義草稿 agent

notebook 在應用程式的關卡之後才定義草稿 agent。這個 agent 能讀目前核准的分析和原始證據，但沒有任何核准、改狀態或申報的 tool。執行它是選用的，會多一次付費推論呼叫。啟動 Jupyter 前設 `RUN_DRAFTING_DEMO=true`。證據 tool 的例外會直接往上拋，不會變成模型看得到的錯誤輸出。儲存草稿前，應用程式會從原始的 run-item payload 確認每個必要的證據呼叫都有產出，再檢查目前的 case ID、evidence ID 和免責聲明。本機的負面測試涵蓋缺少 tool 輸出和 case 不符兩種情況，不需要呼叫模型。有資格的審核者還是得確認每一句敘述都有支持。


```python
@function_tool(failure_error_function=None)
def get_reviewed_analysis(
    wrapper: RunContextWrapper[InvestigationContext],
    case_id: str,
) -> str:
    """Return the current analysis only after explicit human approval."""

    require_known_case(wrapper, case_id)
    return require_drafting_allowed(wrapper.context).model_dump_json()


sar_drafting_agent = Agent[InvestigationContext](
    name="Synthetic SAR Draft Preparation Agent",
    model=MODEL_ID,
    model_settings=MODEL_SETTINGS,
    output_type=SarDraft,
    tools=[
        get_case_profile,
        list_case_transactions,
        get_reviewed_analysis,
    ],
    instructions=(
        "Prepare a synthetic draft for qualified human review only. Call all "
        "three tools. Use neutral chronological language and cite supplied "
        "transaction IDs and copy the supplied case ID exactly. Never submit "
        "or file anything. The disclaimer must "
        "say this is an AI-generated draft requiring qualified human review. "
        "Return only SarDraft."
    ),
)

REQUIRED_DRAFTING_TOOLS = {
    "get_case_profile",
    "list_case_transactions",
    "get_reviewed_analysis",
}


def raw_item_string(raw_item: object, field_name: str) -> str | None:
    if isinstance(raw_item, dict):
        value = raw_item.get(field_name)
    else:
        value = getattr(raw_item, field_name, None)
    return value if isinstance(value, str) else None


def raw_call_id(raw_item: object) -> str | None:
    return raw_item_string(raw_item, "call_id") or raw_item_string(
        raw_item, "id"
    )


def completed_function_tools(items: list[object]) -> set[str]:
    tool_names_by_call_id: dict[str, str] = {}
    completed_call_ids: set[str] = set()
    for item in items:
        if isinstance(item, ToolCallItem):
            call_id = raw_call_id(item.raw_item)
            tool_name = raw_item_string(item.raw_item, "name")
            if call_id is not None and tool_name is not None:
                tool_names_by_call_id[call_id] = tool_name
        elif isinstance(item, ToolCallOutputItem):
            call_id = raw_call_id(item.raw_item)
            if call_id is not None:
                completed_call_ids.add(call_id)
    return {
        tool_name
        for call_id, tool_name in tool_names_by_call_id.items()
        if call_id in completed_call_ids
    }


simulated_run_items: list[object] = [
    ToolCallItem(
        agent=sar_drafting_agent,
        raw_item={
            "type": "function_call",
            "call_id": "synthetic-call-001",
            "name": "get_reviewed_analysis",
            "arguments": "{}",
        },
    ),
    ToolCallOutputItem(
        agent=sar_drafting_agent,
        raw_item={
            "type": "function_call_output",
            "call_id": "synthetic-call-001",
            "output": "{}",
        },
        output="{}",
    ),
]
if completed_function_tools(simulated_run_items) != {
    "get_reviewed_analysis"
}:
    raise AssertionError("Raw run-item correlation failed")
print("PASS (raw run-item correlation)")


def validate_sar_draft(
    candidate: SarDraft,
    context: InvestigationContext,
    completed_tool_names: set[str],
) -> dict[str, bool]:
    draft_ids = {
        evidence_id
        for citation in candidate.citations
        for evidence_id in citation.evidence_ids
    }
    valid_evidence_ids = {
        transaction.id for transaction in context.case.transactions
    }
    checks = {
        "required tools completed": (
            REQUIRED_DRAFTING_TOOLS.issubset(completed_tool_names)
        ),
        "case identity": candidate.case_id == context.case.case_id,
        "valid citations": bool(draft_ids)
        and draft_ids.issubset(valid_evidence_ids),
        "human-review disclaimer": (
            "qualified human review" in candidate.disclaimer.casefold()
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("Draft validation failed: " + ", ".join(failed))
    return checks


wrong_case_draft = SarDraft(
    case_id="SYNTH-AML-OTHER",
    narrative="Synthetic local test fixture.",
    draft_status="INSUFFICIENT_INFORMATION",
    citations=[
        EvidenceCitation(
            claim="A synthetic transaction exists.",
            evidence_ids=["TXN-001"],
        )
    ],
    disclaimer="AI-generated draft requiring qualified human review.",
)
try:
    validate_sar_draft(
        wrong_case_draft, run_context, set(REQUIRED_DRAFTING_TOOLS)
    )
except ValueError as exc:
    print("PASS (wrong-case draft rejected):", exc)
else:
    raise AssertionError("A wrong-case draft must be rejected")

missing_tool_draft = wrong_case_draft.model_copy(
    update={"case_id": run_context.case.case_id}
)
try:
    validate_sar_draft(
        missing_tool_draft,
        run_context,
        REQUIRED_DRAFTING_TOOLS - {"get_reviewed_analysis"},
    )
except ValueError as exc:
    print("PASS (missing draft tool rejected):", exc)
else:
    raise AssertionError("A draft missing a required tool must be rejected")


if RUN_DRAFTING_DEMO:
    require_drafting_allowed(run_context)
    draft_run = await Runner.run(
        sar_drafting_agent,
        f"Prepare a synthetic draft for {run_context.case.case_id}.",
        context=run_context,
        max_turns=8,
        run_config=RunConfig(
            tracing_disabled=True,
            workflow_name="Synthetic SAR draft preparation",
        ),
    )
    draft = draft_run.final_output
    completed_drafting_tools = completed_function_tools(
        draft_run.new_items
    )
    draft_checks = validate_sar_draft(
        draft, run_context, completed_drafting_tools
    )
    run_context.draft = draft
    for check_name in draft_checks:
        print("PASS:", check_name)
    print(draft.model_dump_json(indent=2))
else:
    print("Optional drafting run skipped; the approved gate remains testable.")
```

## 10. 這個範例證明了什麼

- 明確開啟後，Agents SDK 會透過 Amazon Bedrock 跑有界的模型與 tool 迴圈。
- 預設的離線 fixture 不會呼叫 AWS 或模型，也不能證明 Agents SDK 的 orchestration。
- 型別化的 context 把 tool 和流程狀態限制在單一請求、單一 tenant。
- Pydantic 讓重要的 finding 結構化，但正確性來自確定性的支持檢查。
- ID 有效和 claim 有支持是分開測試的。
- 被駁回的工作維持駁回，直到修訂後的分析明確通過重新審核。
- 結構化欄位讓草稿權限維持 false，申報決定維持未決定。
- 草稿在應用程式掌管的核准之後才能進行，申報不在範圍內。

這份 notebook 是學習素材，不是正式的 AML 系統。真正部署需要機構核准的政策、身分與授權、受保護的資料處理、持久的流程和稽核紀錄、領域專家審過的 eval、監控、事件應變，以及法務與合規審查。AgentCore 部署和完整的 AWS 基礎設施應該另外用一份文件說明。


## 參考資料

- [OpenAI models in Amazon Bedrock](https://developers.openai.com/api/docs/guides/amazon-bedrock)
- [OpenAI Agents SDK guide](https://developers.openai.com/api/docs/guides/agents)
- [OpenAI Agents SDK for Python](https://github.com/openai/openai-agents-python)
- [Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals)
- [GPT-5.6 Sol model documentation](https://developers.openai.com/api/docs/models/gpt-5.6-sol)
- [Amazon Bedrock GPT-5.6 Sol model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-56-sol.html)
- [FinCEN Suspicious Activity Reports](https://www.fincen.gov/suspicious-activity-reports-sars)


## 重點整理

- 模型只負責提案，驗證和流程狀態由應用程式程式碼掌控。
- 結構化輸出加上確定性重算，才能確認 claim 真的有證據支持，ID 存在不等於有支持。
- 型別化 context 把 tool 的資料範圍限制在單一請求和 tenant。
- 授權欄位（drafting_authorized、filing_decision）用 schema 鎖死，模型沒辦法自己給自己權限。
- 駁回紀錄要保留，修訂後必須明確重新審核。

## 練習

1. 把 case 裡其中一筆交易金額改掉，跑驗證 cell，看哪一種 finding 的檢查會失敗。
2. 在負面案例的 cell 裡多加一個測試：讓 `drafting_authorized` 為 `true`，確認 validator 會擋下來。
3. 讓分析 agent 多一個你自己寫的唯讀 tool（例如回傳某筆交易的對手方資訊），並把它加進「必須呼叫的 tool」檢查裡。
