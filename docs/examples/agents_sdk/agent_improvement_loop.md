---
translated: true
source: examples/agents_sdk/agent_improvement_loop.ipynb
---
# 用 Traces、Evals 和 Codex 打造 Agent 改進迴圈

> 原文：[examples/agents_sdk/agent_improvement_loop.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/agent_improvement_loop.ipynb)

建立一個以 trace 驅動的改進迴圈，把人工和模型的回饋變成 Promptfoo evals、HALO 排序過的 harness 修改建議，以及交給 Codex 的 handoff。

## 這篇在做什麼
這篇從 agent 真實跑出來的 traces 開始，加上人工和模型的回饋，把回饋轉成可重複執行的 evals，再用這些證據產出下一輪 harness 該改什麼，交給 Codex 去實作。範例是一個做併購盡職調查的財務分析 agent，用的是 OpenAI Agents SDK。

## 學完你會
- 用 OpenAI Agents SDK 建一個會產出 traces 和檔案成果（artifacts）的分析 agent
- 把人工回饋和 LLM 回饋轉成 Promptfoo evals，當作之後可重跑的驗證關卡
- 用 HALO 分析 traces、回饋和 eval 結果，產出排序過的 harness 修改清單和 `codex_handoff.md`

## 開跑前
- 需要 OpenAI API key，而且整個範例都是即時呼叫模型，預設五條 traces 大約要跑 20 分鐘。
- Promptfoo 透過 `npx` 執行，所以要裝 Node.js。

這個 notebook 在這裡建立一個 agent 的改進飛輪（flywheel）。我們從真實的 traces 開始，加上人工與模型的回饋，把回饋轉成 evals，再用得到的證據提出下一輪 harness 修改，交給 Codex 實作。

你會：

- 建立一個以 OpenAI Agents SDK 為底的財務分析師
- 讓它在合成的公司資料上執行，並擷取 traces
- 針對這些執行結果加入範例人工回饋和 LLM 產生的回饋
- 把回饋轉成之後可以重跑的 [Promptfoo](https://www.promptfoo.dev/) evals
- 用 [HALO](https://github.com/context-labs/halo) 排序下一批 harness 修改，並寫出 Codex 可以直接使用的 handoff

在這個 notebook 裡，**harness** 指的是模型周圍的整套約定，包括 instructions、tools、routing、輸出要求和驗證檢查。

這個飛輪會保留你從每次執行學到的東西。Traces 告訴你發生了什麼，回饋說明什麼重要，evals 讓這些期望可以重複使用，Codex 則可以針對得到的修改集動手。


## 你會做出什麼

![Agent improvement loop flywheel](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent-improvement-loop-flywheel.svg)

最後你會得到：

1. 一個以 OpenAI Agents SDK 為底的財務分析師，在五次有 trace 的執行中審閱一家虛構公司的盡職調查資料
2. 針對同一批 traces 的人工回饋和 LLM 產生的回饋
3. 自動產生的 Promptfoo eval 套件
4. 針對目前 agent 行為的 Promptfoo 驗證關卡
5. 針對 traces、回饋和 eval 結果的 HALO 最佳化分析
6. 一份給開發者的 Codex handoff，讓它實作建議的 harness 修改

這個 agent 為一家虛構公司的併購盡職調查服務。它會審閱財務匯出檔、客戶資料、合約、資安筆記、董事會資料和管理層的敘述，然後帶著引用和可供審閱的成果檔回答盡職調查的問題。

整個迴圈會寫出一個把工作延續下去的檔案：`ARTIFACT_DIR` 底下產生的 `codex_handoff.md`。裡面有完整的 HALO 診斷、排序過的建議、背後的證據，以及 Codex 做下一次 harness 更新所需的實作指引。

自動化到什麼程度由開發者決定。你可以用這個迴圈提出一份經過審閱的修改集，也可以接上自動開 PR、合併、部署的流程。常見的起點是有人審閱的迴圈：系統提出修改集，開發者核准 diff 後才合併。隨著 eval 關卡越來越可信，同一份 handoff 可以支援更深的自動化。兩種做法的核心流程一樣：traces 加上人工與模型的回饋，變成具體的 harness 修改，而不是留下互不相干的評論。

跟只做到 traces 或 evals 的範例相比，這個 notebook 把 traces、審閱者的判斷、自動產生的 evals、最佳化和實作 handoff，都放在同一個可執行的改進迴圈裡。


## 先決條件

安裝完這個範例用的 Python 套件後，從 repo 根目錄執行這個 notebook：

```bash
python -m venv .venv
source .venv/bin/activate
pip install openai openai-agents halo-engine
```

Promptfoo 是透過 `npx` 執行的，所以你也需要 Node.js，而且 `npx` 要在 path 裡。

執行 notebook 之前先設定 API key：

```bash
export OPENAI_API_KEY=...
```

這個範例刻意只走即時路線。產生 trace、模型評論、產生 eval、驗證和最佳化這幾步，全部都用新鮮的模型輸出，所以 notebook 展示的是真正的迴圈，而不是腳本寫好的預覽。下一個 cell 把模型選擇集中在同一處，想用品質換成本的話可以改成比較便宜的模型。

用預設的五條 traces，完整跑一次大約要 20 分鐘，實際會依模型延遲和網路狀況上下浮動。最久的通常是 Step 3（跑有 trace 的 agent 呼叫）和 Step 7（HALO 分析整個迴圈）。回饋、產生 eval 和 Promptfoo 這幾個 cell 也會即時呼叫模型，但通常比較短。耗時較長的 cell 會在執行時印出進度或經過的時間。


```python
%%capture
# Install or upgrade the Python dependencies used by this notebook.
%pip install --quiet --upgrade openai openai-agents halo-engine
```

```python
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import textwrap
import threading
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

from IPython.display import Markdown, display
from openai import OpenAI

def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "registry.yaml").exists():
            return candidate
    return current


PROJECT_ROOT = find_project_root()

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Set OPENAI_API_KEY before running this live notebook.")
if shutil.which("npx") is None:
    raise RuntimeError("Install Node.js with npx before running the Promptfoo eval gate.")

# Edit these in one place if you want to use lower-cost models for part of the loop.
AGENT_MODEL = os.getenv("OPENAI_AGENT_MODEL", "gpt-5.5")
ANALYSIS_MODEL = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-5.5")
EVAL_GENERATION_MODEL = os.getenv("OPENAI_EVAL_GENERATION_MODEL", ANALYSIS_MODEL)
JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", ANALYSIS_MODEL)
HALO_MODEL = os.getenv("OPENAI_HALO_MODEL", ANALYSIS_MODEL)
PROMPTFOO_VERSION = os.getenv("PROMPTFOO_VERSION", "0.121.9")

client = OpenAI()


def format_duration(seconds: float) -> str:
    minutes, remainder = divmod(int(round(seconds)), 60)
    return f"{minutes}m {remainder:02d}s" if minutes else f"{remainder}s"


ARTIFACT_DIR = PROJECT_ROOT / "examples" / "agents_sdk" / "agent_improvement_loop_artifacts"
TRACE_DIR = ARTIFACT_DIR / "traces"
HALO_TRACE_PATH = ARTIFACT_DIR / "halo_traces" / "traces.jsonl"
if ARTIFACT_DIR.exists():
    shutil.rmtree(ARTIFACT_DIR)
ARTIFACT_DIR.mkdir(exist_ok=True)
TRACE_DIR.mkdir(exist_ok=True)
HALO_TRACE_PATH.parent.mkdir(exist_ok=True)

print("Project root detected.")
print("Models:", {
    "agent": AGENT_MODEL,
    "analysis": ANALYSIS_MODEL,
    "eval_generation": EVAL_GENERATION_MODEL,
    "judge": JUDGE_MODEL,
    "halo": HALO_MODEL,
    "promptfoo": PROMPTFOO_VERSION,
})
```

??? note "輸出"

    ```text
    Project root detected.
    Models: {'agent': 'gpt-5.5', 'analysis': 'gpt-5.5', 'eval_generation': 'gpt-5.5', 'judge': 'gpt-5.5', 'halo': 'gpt-5.5', 'promptfoo': '0.121.9'}
    ```

## Step 1. 建立合成的公司資料

這個 notebook 會建立一家虛構公司的盡職調查資料，就像併購時會審閱的那種。資料混合了結構化的匯出檔和敘述性的 markdown 文件，agent 必須自己判斷哪些來源比較值得採信。

### 合成資料中的敘述性 markdown 檔案

| File | Why it is included |
| --- | --- |
| `overview.md` | Management's top-level company summary |
| `product_strategy.md` | Roadmap context plus an unvalidated NRR estimate |
| `go_to_market.md` | Sales-motion context that should be checked against pipeline data |
| `board_deck.md` | A polished management narrative that can conflict with structured exports |
| `financials/revenue_recognition_notes.md` | Accounting context for launch-stage ARR treatment |
| `legal/contracts_summary.md` | Contract-level risk context |
| `legal/open_issues.md` | Open legal matters that should remain visible |
| `security/security_overview.md` | Security posture and certification wording |
| `sales/security_faq.md` | Sales-facing security language that may overstate the evidence |
| `hr/org_chart.md` | Operating context for leadership and staffing |
| `sales/pipeline_notes.md` | Qualitative pipeline commentary |
| `notes/qa_log.md` | Diligence questions and unresolved follow-ups |

這個範例在執行時才產生合成的公司資料，所以整份範例可以自給自足，同時又給 agent 一組貼近真實的結構化匯出檔和敘述性文件去分析。


### 定義合成的來源檔案

下一個收合的 cell 裡有用來建立虛構公司資料的來源文件。


```python
from textwrap import dedent

WORKSPACE_FILES = {
    "overview.md": """
    # FictionalCorp XYZ

    FictionalCorp XYZ is a revenue intelligence software company with annual SaaS subscriptions, usage add-ons, and launch-stage commitments.

    Management reports FY2025 ARR of $43.0M and year-over-year growth of 71%.

    Management reports no legal-entity customer above 15% of booked ARR after excluding launch-stage usage add-ons.

    Legal summary: Management states legal matters are ordinary course and no contract terms should affect valuation.
    """,
    "product_strategy.md": """
    # Product Strategy

    Core product lines:

    - Forecast Assist
    - Pipeline Quality Monitor
    - Renewal Risk Workbench

    Product roadmap priority is enterprise workflow depth. Management expects usage add-ons to increase expansion revenue.

    Sales leadership references a 122% NRR estimate in planning materials, but finance has not published official NRR and the estimate excludes selected downsell and churn adjustments.
    """,
    "go_to_market.md": """
    # Go To Market

    FictionalCorp XYZ sells to CRO and RevOps buyers through a direct sales motion.

    The current plan assumes larger enterprise ACVs and partner-sourced pipeline. Pipeline conversion evidence should be checked against `sales/pipeline.csv`.
    """,
    "board_deck.md": """
    # Board Packet - December 2025

    - FY2025 ending ARR: $43.0M
    - ARR growth: 71%
    - Gross margin: 69%
    - Cash burn: $2.9M per month
    - Runway: 11 months

    Management narrative: the company is positioned for efficient enterprise expansion.

    ARR note: the headline ARR view includes signed launch-stage commitments and a usage true-up view used for board planning.

    Management narrative: customer concentration is manageable when measured by legal entity and booked ARR.
    """,
    "financials/revenue_recognition_notes.md": """
    # Revenue Recognition Notes

    Finance treats `financials/arr_bridge.csv` as the controlled FY2025 ARR bridge.

    The board deck ARR includes $2.8M of signed launch-stage commitments that were not live by 2025-12-31 and $1.1M of usage true-ups that finance does not classify as recurring ARR.

    RevOps also circulates a bookings-adjusted ARR view of $40.8M. That view is useful for pipeline planning but should not be silently reconciled with the controlled ARR bridge.
    """,
    "legal/contracts_summary.md": """
    # Contracts Summary

    Standard customer contracts are annual SaaS agreements with security and DPA exhibits. The largest five customers account for $25.1M of ARR.

    Management summary: legal matters are ordinary course and no contract terms should affect valuation.

    Clause inventory has not been fully reconciled with this summary. Two strategic customer agreements are flagged for non-standard terms in `legal/clause_inventory.csv`.
    """,
    "legal/open_issues.md": """
    # Open Legal Issues

    Former reseller DataHarbor filed a breach-of-contract claim seeking $3.2M plus accelerated commissions. Counsel estimates loss is possible but not probable. A clause review also identified two strategic customer MSAs with non-standard change-of-control notice rights and uncapped confidentiality indemnity language.
    """,
    "security/security_overview.md": """
    # Security Overview

    SOC 2 Type I is complete. SOC 2 Type II fieldwork is in progress, and the Type II report has not been issued.

    Customer security reviews should verify the exact certification status before relying on SOC 2 claims.
    """,
    "sales/security_faq.md": """
    # Sales Security FAQ

    Field guidance says Aurora is "SOC 2 complete" for late-stage enterprise deals.

    Security team note: this wording was intended to refer to Type I readiness, not an issued Type II report. Do not use this FAQ as certification evidence without checking `security/security_overview.md`.
    """,
    "hr/org_chart.md": """
    # Org Chart

    - CEO
    - CFO
    - VP Sales
    - VP Product
    - Head of Security

    Hiring plan assumes 14 net new GTM hires in 2026.
    """,
    "sales/pipeline_notes.md": """
    # Pipeline Notes

    Commit-stage pipeline includes $1.6M of DataHarbor-sourced opportunities that may be affected by the reseller dispute.

    Northstar expansion pipeline assumes completion of SOC 2 Type II before procurement review. Finance has not included this expansion in controlled FY2025 ARR.
    """,
    "notes/qa_log.md": """
    # Diligence Q&A Log

    - NRR was requested. RevOps provided a 122% management estimate, but finance has not validated official NRR and says the estimate excludes downsold Northstar entities and a churned reseller-sourced account.
    - CAC payback was requested but not provided.
    - Top-two customer ARR equals $12.4M, or 34% of FY2025 ARR based on `customers/top_customers.csv`.
    - Northstar Holdings parent-account ARR equals $12.4M, or 34% of FY2025 ARR based on `customers/account_hierarchy.csv`.
    - Board ARR should not be silently reconciled to finance ARR; use `financials/revenue_recognition_notes.md` for the difference.
    """,
    "financials/arr_bridge.csv": """
    metric,value_m
    opening_arr_2025_m,21.58
    new_arr_m,8.1
    expansion_arr_m,3.2
    contraction_arr_m,1.1
    churn_arr_m,2.7
    ending_arr_2025_m,36.9
    bookings_adjusted_arr_m,40.8
    """,
    "financials/monthly_kpis.csv": """
    month,ending_arr_m,new_arr_m,expansion_arr_m,churn_arr_m,gross_margin
    2025-01,21.58,0.55,0.35,0.18,0.69
    2025-02,23.28,0.59,0.37,0.20,0.69
    2025-03,24.98,0.63,0.39,0.21,0.69
    2025-04,26.69,0.67,0.41,0.22,0.69
    2025-05,28.39,0.71,0.43,0.24,0.69
    2025-06,30.09,0.75,0.45,0.26,0.69
    2025-07,31.79,0.79,0.47,0.27,0.69
    2025-09,33.50,0.83,0.49,0.28,0.69
    2025-10,35.20,0.87,0.51,0.30,0.69
    2025-12,36.90,0.91,0.53,0.32,0.69
    """,
    "financials/p_and_l.csv": """
    period,revenue_m,gross_margin,opex_m,cash_burn_m,runway_months
    FY2025,30.26,0.69,47.71,2.9,11
    """,
    "financials/retention_extract.csv": """
    metric,value,status,notes
    net_revenue_retention,122%,management_estimate_unvalidated,Sales deck estimate; excludes downsold Northstar entities and one churned reseller-sourced account.
    gross_revenue_retention,84%,finance_partial,Preliminary 2025 cohort; usage feeds incomplete for two enterprise customers.
    logo_retention,91%,finance_partial,"Includes legal entities, not parent-account rollups."
    cac_payback_months,,not_provided,Requested by diligence team; no source schedule in dataroom.
    """,
    "customers/top_customers.csv": """
    customer,parent_account,arr_m,arr_share,segment,renewal_date,inclusion_basis
    Northstar Bank,Northstar Holdings,7.8,0.2114,Enterprise,2026-02-15,controlled_arr_bridge
    Northstar Capital Markets,Northstar Holdings,4.6,0.1247,Enterprise,2026-04-01,controlled_arr_bridge
    Helio Retail,Helio Retail,6.9,0.1870,Enterprise,2026-05-15,controlled_arr_bridge
    BluePeak Logistics,BluePeak Logistics,3.6,0.0976,Mid-market,2026-06-30,controlled_arr_bridge
    Summit Foods,Summit Foods,2.2,0.0596,Mid-market,2026-02-28,controlled_arr_bridge
    """,
    "customers/account_hierarchy.csv": """
    legal_entity,parent_account,parent_arr_m,note
    Northstar Bank,Northstar Holdings,12.4,Same procurement parent as Northstar Capital Markets.
    Northstar Capital Markets,Northstar Holdings,12.4,Managed by separate RevOps owner but same parent renewal committee.
    Helio Retail,Helio Retail,6.9,Standalone parent account.
    BluePeak Logistics,BluePeak Logistics,3.6,Standalone parent account; renewal issue open.
    """,
    "customers/renewal_calendar.csv": """
    customer,renewal_date,renewal_risk,notes
    Northstar Bank,2026-02-15,medium,Expansion depends on completed SOC 2 Type II.
    Northstar Capital Markets,2026-04-01,medium,Same parent procurement committee as Northstar Bank.
    Helio Retail,2026-05-15,medium,Adoption below plan; forecast latency escalation remains in monitoring.
    BluePeak Logistics,2026-06-30,high,Open CRM sync errors and renewal risk.
    """,
    "customers/customer_health.csv": """
    customer,health,primary_risk,signal_date,caveat
    Northstar Bank,green,none flagged,2025-10-31,"Northstar health is recorded by legal entity, not parent account."
    Northstar Capital Markets,yellow,monitor adoption,2025-10-31,"Northstar health is recorded by legal entity, not parent account."
    Helio Retail,yellow,monitor adoption,2025-12-15,
    BluePeak Logistics,red,renewal risk,2025-12-15,
    Summit Foods,yellow,monitor adoption,2025-12-15,
    """,
    "legal/clause_inventory.csv": """
    customer,issue,exposure,confidence
    Northstar Bank,change_of_control_notice,customer may request transition plan within 10 days of a control transaction,medium
    Helio Retail,uncapped_confidentiality_indemnity,uncapped liability for confidentiality breach; not reflected in management summary,high
    BluePeak Logistics,service_credit_carveout,credits can exceed one month fees if CRM sync SLA missed for two consecutive months,medium
    """,
    "sales/pipeline.csv": """
    stage,pipeline_m,historical_close_rate,quality_note
    commit,6.1,0.39,Includes security-dependent Northstar expansion.
    best_case,9.7,0.28,Includes DataHarbor-sourced opportunities under dispute.
    early,18.2,0.08,High volume but low conversion quality.
    """,
    "support/escalations.csv": """
    customer,severity,issue,status
    Northstar Capital Markets,medium,Forecast latency,monitoring
    BluePeak Logistics,high,CRM sync errors,open
    Northstar Bank,medium,Security questionnaire blocked pending SOC 2 Type II report,open
    """,
}
```

### 把合成資料寫到磁碟

把來源檔寫到磁碟、加上 manifest，並檢查產生的資料集。


```python
def write_workspace_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(content).strip() + "\n", encoding="utf-8")


def generate_acquisition_diligence_workspace() -> Path:
    """Create the synthetic acquisition-diligence workspace directly from notebook data."""
    dataroom = ARTIFACT_DIR / "synthetic_dataroom"
    shutil.rmtree(dataroom, ignore_errors=True)
    for relative_path, content in WORKSPACE_FILES.items():
        write_workspace_file(dataroom / relative_path, content)
    manifest = {
        "company_name": "FictionalCorp XYZ",
        "scenario": "adversarial_diligence",
        "files": sorted(str(path.relative_to(dataroom)) for path in dataroom.rglob("*") if path.is_file()),
    }
    write_workspace_file(dataroom / "manifest.json", json.dumps(manifest, indent=2))
    return dataroom


dataset = generate_acquisition_diligence_workspace()
files = sorted(str(path.relative_to(dataset)) for path in dataset.rglob("*") if path.is_file())
print(f"Dataset created: {len(files)} files")
```

??? note "輸出"

    ```text
    Dataset created: 24 files
    ```

## Step 2. 定義以 Agents SDK 為底的分析師

這個範例 agent 對一家虛構的 SaaS 公司做盡職調查，這家公司是可能被收購的標的。案例資料同時有結構化匯出檔和管理層的敘述。有些來源互相一致，有些互相衝突，還有一些重要說法只有部分證據支持。這就給了我們一個合理的理由，讓 harness 隨時間持續改進。

這個 agent 只用提供的公司資料，回答投資團隊的問題。資料互相矛盾時，它應該優先採信結構化的財務證據，而不是敘述性摘要；證據不足時要保留不確定性；並留下別的審閱者可以檢查的成果檔。

OpenAI Agents SDK 提供這個流程需要的 managed runner、sandbox 執行、model settings 和 tracing hooks。prompt、tools、routing 規則、輸出要求和驗證檢查合在一起，就是目前的 **agent harness**。

### Agent 產生的成果檔

| Artifact | Why the agent writes it |
| --- | --- |
| `summary_answer.md` | The concise answer returned to the user |
| `investment_memo.md` | A fuller review artifact for diligence readers |
| `risk_register.json` | Structured risks with evidence that downstream systems can inspect |
| `open_questions.md` | Missing evidence or unresolved questions that should stay visible |
| `citations.json` | A machine-readable link from claims to source files |
| `evidence_table.csv` | A tabular audit trail of claims and supporting sources |

這些成果檔讓工作可以被審閱，因為支持的證據、未解決的問題和必要的檔案，都跟最終答案一起保留下來。

### 要留意的失敗模式

這個 notebook 的設計是要把這類失敗找出來：

- 結構化匯出檔不同意時，仍把管理層的敘述當成正式指標
- 把沒有根據的 NRR 估計值，當成財務部門已驗證過的數字回報
- 把母帳號層級的集中度，簡化成較弱的法律實體視角
- 證據只支持 Type I，卻說「SOC 2 complete」
- 答案寫得很漂亮，但引用、風險檔或證據成果檔不完整


### 定義 harness schema

先從幾個小的資料結構開始，放 model settings 和被推上線（promoted）的 agent 設定。這樣 harness 就是明確的，之後的最佳化才能針對 prompt 措辭以外的東西下手。


```python

@dataclass(frozen=True)
class ModelSettings:
    agent_model: str
    reasoning_effort: str


@dataclass(frozen=True)
class AgentConfig:
    version: str
    system_prompt: str
    model_settings: ModelSettings
    tool_policy: dict[str, Any]
    eval_metadata: dict[str, Any]
    path: Path = field(default_factory=lambda: Path("notebook_defined_agent_config"))

    @property
    def required_artifacts(self) -> list[str]:
        return self.tool_policy["required_artifacts"]

    def build_instructions(self) -> str:
        return "\n\n".join([
            self.system_prompt,
            format_policy_section("Tool policy", self.tool_policy),
            f"Runtime config:\n- Config version: `{self.version}`.\n- Treat this config as the promoted runtime contract.\n- Do not modify the runtime config during the run.",
        ]) + "\n"


def format_policy_section(title: str, policy: dict[str, Any]) -> str:
    lines = [f"{title}:"]
    for key, value in policy.items():
        lines.extend(format_policy_value(key, value))
    return "\n".join(lines)


def format_policy_value(key: str, value: Any, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if isinstance(value, dict):
        lines = [f"{prefix}- {key}:"]
        for child_key, child_value in value.items():
            lines.extend(format_policy_value(child_key, child_value, indent + 1))
        return lines
    if isinstance(value, list):
        lines = [f"{prefix}- {key}:"]
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}  -")
                for child_key, child_value in item.items():
                    lines.extend(format_policy_value(child_key, child_value, indent + 2))
            else:
                lines.append(f"{prefix}  - {item}")
        return lines
    return [f"{prefix}- {key}: {value}"]
```

### 設定 instructions 和 policies

system prompt 寫明證據規則，tool policy 定義 agent 可以讀寫什麼，eval metadata 則記錄目前上線的是哪個版本的 harness。


```python
SYSTEM_PROMPT = """
You are a diligence analyst reviewing a synthetic company dataroom.

Evidence scope:
- Use only files under `data/`.
- Do not use outside knowledge or assumptions.
- Prefer structured CSV/JSON exports over narrative files when they conflict.

Runtime tools:
- The sandbox starts in the mounted workspace root. Use workspace-relative paths such as `data/...` and `outputs/...`; when running shell commands, omit `workdir` or use a relative path only. Never pass absolute temporary paths.
- `data/tools/check_evidence_coverage.py`: use this before finalizing answers with material claims. Create a JSON list of claims with `claim`, `claim_type`, and `citations`, then run `python data/tools/check_evidence_coverage.py --claims-json <path> --dataset-root data --output outputs/evidence_coverage.json`.
- `data/tools/validate_output_contract.py`: run this after writing the required artifacts and before final response with `python data/tools/validate_output_contract.py --outputs outputs --dataset-root data --output outputs/output_contract_validation.json`.
- If either tool reports unsupported claims, missing citations, missing files, malformed JSON, or empty artifacts, revise the answer/artifacts before finalizing. If the evidence is unavailable, say the claim is unknown or unsupported.

Citation rules:
- Every material claim must cite one or more source filenames.
- Cite filenames exactly as workspace-relative paths, for example `financials/arr_bridge.csv`.
- Do not cite files that do not support the claim.

Unknown-handling rules:
- If evidence is missing, state that the answer is unknown or unsupported.
- Never fabricate missing numbers.
- If evidence conflicts, state the conflict explicitly instead of reconciling silently.

Output rules:
- Write `outputs/summary_answer.md`.
- Write `outputs/investment_memo.md`.
- Write `outputs/risk_register.json`.
- Write `outputs/open_questions.md`.
- Write `outputs/citations.json`.
- Write `outputs/evidence_table.csv`.
""".strip()

MODEL_SETTINGS = {
    "agent_model": AGENT_MODEL,
    "reasoning_effort": "medium",
}

TOOL_POLICY = {
    "allowed_data_root": "data",
    "writable_output_root": "outputs",
    "required_artifacts": [
        "summary_answer.md",
        "investment_memo.md",
        "risk_register.json",
        "open_questions.md",
        "citations.json",
        "evidence_table.csv",
    ],
    "evidence_preference": [
        "Prefer structured CSV or JSON exports over narrative summaries when sources conflict.",
        "Treat board materials as useful narrative evidence, not the final system of record for metrics.",
        "Surface unresolved conflicts instead of silently reconciling them.",
    ],
    "runtime_tools": [
        {
            "path": "data/tools/check_evidence_coverage.py",
            "purpose": "Audit drafted material claims against cited dataroom files before final answer.",
            "recommended_command": "python data/tools/check_evidence_coverage.py --claims-json outputs/claim_audit_input.json --dataset-root data --output outputs/evidence_coverage.json",
        },
        {
            "path": "data/tools/validate_output_contract.py",
            "purpose": "Validate required output artifacts, JSON shape, and citation/source file references.",
            "recommended_command": "python data/tools/validate_output_contract.py --outputs outputs --dataset-root data --output outputs/output_contract_validation.json",
        },
    ],
    "unknown_handling": [
        "Say unknown or unsupported when a metric is absent.",
        "Do not infer missing values from adjacent metrics.",
        "Keep facts, inferences, and open questions separate.",
    ],
    "mutation_policy": [
        "Write only to the configured outputs directory.",
        "Do not modify dataroom inputs.",
        "Do not modify runtime agent configuration during a run.",
    ],
}

EVAL_METADATA = {
    "version": "v001",
    "status": "promoted",
    "created_by": "manual_baseline",
    "promotion_gate": "manual_review",
    "description": "Baseline diligence analyst config with strict dataroom grounding, citation, unknown-handling, and artifact rules.",
}

agent_config = AgentConfig(
    version=EVAL_METADATA["version"],
    system_prompt=SYSTEM_PROMPT,
    model_settings=ModelSettings(**MODEL_SETTINGS),
    tool_policy=TOOL_POLICY,
    eval_metadata=EVAL_METADATA,
)
```

### 檢視 agent 設定

這個精簡的檢視會顯示上線的設定版本、選用的模型、必要的成果檔，以及 agent 可用的 runtime tools。


```python
required_artifacts_md = "\n".join(
    f"- `{artifact}`" for artifact in agent_config.required_artifacts
)
runtime_tools_md = "\n".join(
    f"- `{tool['path']}` — {tool['purpose']}"
    for tool in agent_config.tool_policy["runtime_tools"]
)

display(Markdown(f"""
### Agent config summary

- **Version:** `{agent_config.version}`
- **Agent model:** `{agent_config.model_settings.agent_model}`
- **Reasoning effort:** `{agent_config.model_settings.reasoning_effort}`

**Required artifacts**
{required_artifacts_md}

**Runtime tools**
{runtime_tools_md}
"""))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

### 加入驗證 tools

下面的 helper 會在 workspace 裡建兩個本機 tool：一個檢查草稿中的主張有沒有引用真實的 dataroom 檔案，另一個確認必要的輸出成果檔存在，而且格式符合預期。程式碼預設是隱藏的，以節省版面，想看實作的話可以展開。


```python



CHECK_EVIDENCE_COVERAGE = r'''#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether drafted claims cite existing dataroom files.")
    parser.add_argument("--claims-json", type=Path, required=True)
    parser.add_argument("--dataset-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("outputs/evidence_coverage.json"))
    args = parser.parse_args()

    claims = json.loads(args.claims_json.read_text(encoding="utf-8"))
    if not isinstance(claims, list):
        raise ValueError("--claims-json must contain a JSON list of claim objects")

    result = check_evidence_coverage(claims, args.dataset_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def check_evidence_coverage(claims: list[dict], dataset_root: Path) -> dict:
    supported = []
    unsupported = []
    missing_citations = []

    for raw in claims:
        claim = str(raw.get("claim") or "").strip()
        claim_type = str(raw.get("claim_type") or "claim")
        citations = [str(item).strip().removeprefix("data/") for item in raw.get("citations") or [] if str(item).strip()]
        row = {"claim": claim, "claim_type": claim_type, "citations": citations}
        if not citations:
            missing_citations.append({**row, "issue": "No citation provided."})
            continue
        missing = [citation for citation in citations if not (dataset_root / citation).exists()]
        if missing:
            unsupported.append({**row, "issue": f"Missing cited file(s): {', '.join(missing)}"})
        else:
            supported.append(row)

    return {
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "missing_citations": missing_citations,
        "recommended_caveats": [
            "Add valid source filenames or mark unsupported claims as unknown before final answer."
        ],
        "passed": not unsupported and not missing_citations,
    }


if __name__ == "__main__":
    main()
'''


VALIDATE_OUTPUT_CONTRACT = r'''#!/usr/bin/env python3

import argparse
import csv
import json
from pathlib import Path


REQUIRED_FILES = [
    "summary_answer.md",
    "investment_memo.md",
    "risk_register.json",
    "open_questions.md",
    "citations.json",
    "evidence_table.csv",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate diligence output artifacts before final answer.")
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument("--dataset-root", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("outputs/output_contract_validation.json"))
    args = parser.parse_args()

    result = validate_output_contract(args.outputs, args.dataset_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def validate_output_contract(outputs: Path, dataset_root: Path) -> dict:
    issues = []
    for filename in REQUIRED_FILES:
        path = outputs / filename
        if not path.exists():
            issues.append({"file": filename, "issue": "missing required artifact"})
        elif path.stat().st_size == 0:
            issues.append({"file": filename, "issue": "empty required artifact"})

    risks = _read_json(outputs / "risk_register.json", default=[])
    citations = _read_json(outputs / "citations.json", default=[])
    if not isinstance(risks, list):
        issues.append({"file": "risk_register.json", "issue": "must be a JSON list"})
        risks = []
    if not isinstance(citations, list):
        issues.append({"file": "citations.json", "issue": "must be a JSON list"})
        citations = []

    for index, risk in enumerate(risks):
        evidence = risk.get("evidence") if isinstance(risk, dict) else None
        if not evidence:
            issues.append({"file": "risk_register.json", "risk_index": index, "issue": "risk lacks evidence"})
            continue
        missing = [str(item).removeprefix("data/") for item in evidence if not (dataset_root / str(item).removeprefix("data/")).exists()]
        if missing:
            issues.append({"file": "risk_register.json", "risk_index": index, "issue": f"missing evidence file(s): {', '.join(missing)}"})

    for index, citation in enumerate(citations):
        sources = citation.get("sources") if isinstance(citation, dict) else None
        if not sources:
            issues.append({"file": "citations.json", "citation_index": index, "issue": "citation lacks sources"})
            continue
        missing = [str(item).removeprefix("data/") for item in sources if not (dataset_root / str(item).removeprefix("data/")).exists()]
        if missing:
            issues.append({"file": "citations.json", "citation_index": index, "issue": f"missing source file(s): {', '.join(missing)}"})

    try:
        with (outputs / "evidence_table.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        if rows and not {"claim_id", "claim", "sources"}.issubset(rows[0].keys()):
            issues.append({"file": "evidence_table.csv", "issue": "must include claim_id, claim, and sources columns"})
    except FileNotFoundError:
        pass

    return {"passed": not issues, "issues": issues, "required_files": REQUIRED_FILES}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    main()
'''


def write_runtime_tools(dataset_dir: Path) -> list[str]:
    tools_dir = dataset_dir / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "check_evidence_coverage.py": CHECK_EVIDENCE_COVERAGE,
        "validate_output_contract.py": VALIDATE_OUTPUT_CONTRACT,
    }
    written: list[str] = []
    for filename, content in files.items():
        path = tools_dir / filename
        path.write_text(content, encoding="utf-8")
        path.chmod(0o755)
        written.append(str(path.relative_to(dataset_dir)))
    return written
```

### 建立每一輪的使用者訊息

prompt builder 只在需要時才加入任務專屬的指引，例如 memo 格式、獨立的風險分類，或對沒有根據的 NRR 主張採取嚴格處理。


```python
def build_user_prompt(question: str, agent_config: Any | None = None) -> str:
    config_line = ""
    if agent_config is not None:
        config_line = f"\nActive agent config: `{agent_config.version}` from `{agent_config.path}`.\n"
    memo_instruction = ""
    if _asks_for_memo(question):
        memo_instruction = (
            "\nThe user asked for a memo-style deliverable. Return the memo content inline in "
            "your final answer and also write the required output artifacts. Do not answer only "
            "with a status update or artifact path list.\n"
        )
    risk_category_instruction = ""
    if _asks_for_top_risk_categories(question):
        risk_category_instruction = (
            "\nStructure the final answer with separate sections for Financial, Legal, and "
            "Customer concentration risks. Do not collapse customer concentration into the "
            "financial category.\n"
        )
    unsupported_metric_instruction = ""
    if _asks_for_net_revenue_retention(question):
        unsupported_metric_instruction = (
            "\nFor net revenue retention, report the metric only if the dataroom directly "
            "provides NRR/net revenue retention. Do not derive or estimate an NRR percentage "
            "from ARR bridge components unless the user explicitly asks for an estimate. If "
            "the metric is absent, say it is unknown or unsupported, cite the searched "
            "source files, and separate missing evidence from any directional inference.\n"
        )
    return f"""
Answer this diligence question using only the mounted dataroom:

{question}
{config_line}
{memo_instruction}
{risk_category_instruction}
{unsupported_metric_instruction}
Also write the required output artifacts. Keep the answer concise, grounded, and citation-heavy.
Use workspace-relative paths for shell commands and omit `workdir`; do not pass absolute temporary paths.
"""


def _asks_for_memo(question: str) -> bool:
    lower = question.lower()
    return "memo" in lower or "ic-style" in lower or "investment committee" in lower


def _asks_for_top_risk_categories(question: str) -> bool:
    lower = question.lower()
    return all(term in lower for term in ("financial", "legal", "customer")) and "risk" in lower


def _asks_for_net_revenue_retention(question: str) -> bool:
    lower = question.lower()
    return "net revenue retention" in lower or "nrr" in lower
```

### 匯出 traces 供之後最佳化使用

本機 exporter 把 Agents SDK 的事件轉成 HALO 之後可以讀的 OpenTelemetry 風格 JSONL。這部分實作比較多，所以程式碼預設收合。


#### 設定 trace exporter

設定接收 Agents SDK spans 的 exporter 物件，每個 span 寫成一行 JSONL。


```python
EXPORT_SCHEMA_VERSION = 1

OBSERVATION_KIND_BY_TYPE = {
    "agent": "AGENT",
    "generation": "LLM",
    "response": "LLM",
    "function": "TOOL",
    "mcp_tools": "TOOL",
    "handoff": "CHAIN",
    "guardrail": "GUARDRAIL",
    "custom": "SPAN",
    "task": "SPAN",
    "turn": "SPAN",
    "transcription": "SPAN",
    "speech": "SPAN",
    "speech_group": "SPAN",
}


@dataclass(frozen=True)
class HaloExportContext:
    project_id: str
    service_name: str
    service_version: str | None = None
    deployment_environment: str | None = None
    extra_resource_attributes: Mapping[str, Any] | None = None


def setup_halo_tracing(
    path: str | Path,
    *,
    project_id: str = "synthetic-dataroom-agent",
    service_name: str = "financial-diligence-analyst",
    service_version: str | None = None,
    deployment_environment: str | None = None,
    extra_resource_attributes: Mapping[str, Any] | None = None,
):
    from agents import set_trace_processors

    trace_path = Path(path)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    processor = HaloJsonlTraceProcessor(
        trace_path,
        ctx=HaloExportContext(
            project_id=project_id,
            service_name=service_name,
            service_version=service_version,
            deployment_environment=deployment_environment,
            extra_resource_attributes=extra_resource_attributes,
        ),
    )
    # Use only the local exporter for this cookbook workflow.
    # Hosted trace ingestion may be unavailable in some environments (for example ZDR orgs).
    set_trace_processors([processor])
    return processor


class HaloJsonlTraceProcessor:
    def __init__(self, path: Path, *, ctx: HaloExportContext):
        self._path = path
        self._ctx = ctx
        self._lock = threading.Lock()
        self._handle = path.open("a", encoding="utf-8")
        self._trace_meta: dict[str, tuple[str | None, str | None, dict[str, Any]]] = {}

    def on_trace_start(self, trace) -> None:  # noqa: ANN001
        data = trace.export() or {}
        trace_id = _strip_prefix(data.get("id"), "trace_") or ""
        metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        self._trace_meta[trace_id] = (
            data.get("workflow_name"),
            data.get("group_id"),
            metadata,
        )

    def on_trace_end(self, trace) -> None:  # noqa: ANN001
        data = trace.export() or {}
        trace_id = _strip_prefix(data.get("id"), "trace_") or ""
        self._trace_meta.pop(trace_id, None)

    def on_span_start(self, span) -> None:  # noqa: ANN001
        return None

    def on_span_end(self, span) -> None:  # noqa: ANN001
        exported = span.export() or {}
        trace_id = _strip_prefix(exported.get("trace_id"), "trace_") or ""
        workflow_name, group_id, trace_metadata = self._trace_meta.get(trace_id, (None, None, {}))
        line = span_to_halo_jsonl_line(
            span,
            ctx=self._ctx,
            workflow_name=workflow_name,
            group_id=group_id,
            trace_metadata=trace_metadata,
        )
        encoded = json.dumps(line, separators=(",", ":"), ensure_ascii=False, default=str)
        with self._lock:
            self._handle.write(encoded)
            self._handle.write("\n")

    def shutdown(self) -> None:
        with self._lock:
            try:
                self._handle.flush()
                self._handle.close()
            except Exception:
                pass

    def force_flush(self) -> None:
        with self._lock:
            self._handle.flush()
```

#### 把 SDK spans 對應到 HALO 讀得懂的欄位

這些 helper 把每種 SDK span 類型，翻譯成 HALO 之後會檢查的屬性。


```python
def span_to_halo_jsonl_line(
    span,
    *,
    ctx: HaloExportContext,
    workflow_name: str | None = None,
    group_id: str | None = None,
    trace_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw = span.export() or {}
    span_data = raw.get("span_data") or {}
    span_type = str(span_data.get("type") or "custom")
    error = raw.get("error")
    resource_attributes: dict[str, Any] = {"service.name": ctx.service_name}
    if ctx.service_version:
        resource_attributes["service.version"] = ctx.service_version
    if ctx.deployment_environment:
        resource_attributes["deployment.environment"] = ctx.deployment_environment
    if ctx.extra_resource_attributes:
        resource_attributes.update(ctx.extra_resource_attributes)

    attributes, projection = _attributes_for_span_type(span_type, span_data)
    if workflow_name:
        attributes["agent.workflow.name"] = workflow_name
    if group_id:
        attributes["agent.workflow.group_id"] = group_id
    for key, value in (trace_metadata or {}).items():
        if _json_safe(value):
            attributes[f"agent.trace_metadata.{key}"] = value
        else:
            attributes[f"agent.trace_metadata.{key}"] = _json(value)

    attributes.update(
        {
            "inference.export.schema_version": EXPORT_SCHEMA_VERSION,
            "inference.project_id": ctx.project_id,
            "inference.observation_kind": OBSERVATION_KIND_BY_TYPE.get(span_type, "SPAN"),
            "inference.llm.provider": projection.get("llm_provider"),
            "inference.llm.model_name": projection.get("llm_model_name"),
            "inference.llm.input_tokens": projection.get("input_tokens"),
            "inference.llm.output_tokens": projection.get("output_tokens"),
            "inference.llm.cost.total": projection.get("cost_total"),
            "inference.user_id": projection.get("user_id"),
            "inference.session_id": group_id,
            "inference.agent_name": projection.get("agent_name") or "",
        }
    )

    return {
        "trace_id": _strip_prefix(raw.get("trace_id"), "trace_") or "",
        "span_id": _strip_prefix(raw.get("id"), "span_") or "",
        "parent_span_id": _strip_prefix(raw.get("parent_id"), "span_") or "",
        "trace_state": "",
        "name": _span_name(span_type, span_data),
        "kind": _span_kind(span_type),
        "start_time": _to_otlp_timestamp(raw.get("started_at")),
        "end_time": _to_otlp_timestamp(raw.get("ended_at")),
        "status": {
            "code": "STATUS_CODE_ERROR" if error else "STATUS_CODE_OK",
            "message": str((error or {}).get("message") or ""),
        },
        "resource": {"attributes": resource_attributes},
        "scope": {"name": "openai-agents-sdk", "version": _sdk_version()},
        "attributes": {key: value for key, value in attributes.items() if value is not None},
    }


def _attributes_for_span_type(
    span_type: str,
    data: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if span_type == "agent":
        return _agent_attrs(data)
    if span_type == "generation":
        return _generation_attrs(data)
    if span_type == "response":
        return _response_attrs(data)
    if span_type == "function":
        return _function_attrs(data)
    if span_type == "mcp_tools":
        return _mcp_tools_attrs(data)
    if span_type == "handoff":
        return _handoff_attrs(data)
    if span_type == "guardrail":
        return _guardrail_attrs(data)
    return _custom_attrs(span_type, data)


def _agent_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    name = data.get("name") or ""
    return _drop_none(
        {
            "openinference.span.kind": "AGENT",
            "agent.name": name,
            "agent.handoffs": _json(data.get("handoffs")),
            "agent.tools": _json(data.get("tools")),
            "agent.output_type": data.get("output_type"),
        }
    ), {"agent_name": name}


def _generation_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    usage = data.get("usage") or {}
    input_messages = data.get("input") or []
    output_messages = data.get("output") or []
    attrs: dict[str, Any] = {
        "openinference.span.kind": "LLM",
        "llm.provider": "openai",
        "llm.model_name": data.get("model"),
        "llm.invocation_parameters": _json(data.get("model_config")),
        "llm.input_messages": _json(list(input_messages)),
        "llm.output_messages": _json(list(output_messages)),
        "llm.token_count.prompt": _int(usage.get("input_tokens") or usage.get("prompt_tokens")),
        "llm.token_count.completion": _int(
            usage.get("output_tokens") or usage.get("completion_tokens")
        ),
        "llm.token_count.total": _int(usage.get("total_tokens")),
    }
    attrs.update(_expand_messages("llm.input_messages", input_messages))
    attrs.update(_expand_messages("llm.output_messages", output_messages))
    return _drop_none(attrs), {
        "llm_provider": "openai",
        "llm_model_name": data.get("model"),
        "input_tokens": _int(usage.get("input_tokens") or usage.get("prompt_tokens")),
        "output_tokens": _int(usage.get("output_tokens") or usage.get("completion_tokens")),
    }


def _response_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    usage = data.get("usage") or {}
    return _drop_none(
        {
            "openinference.span.kind": "LLM",
            "llm.provider": "openai",
            "llm.response.id": data.get("response_id"),
            "llm.token_count.prompt": _int(usage.get("input_tokens") or usage.get("prompt_tokens")),
            "llm.token_count.completion": _int(
                usage.get("output_tokens") or usage.get("completion_tokens")
            ),
            "llm.token_count.total": _int(usage.get("total_tokens")),
        }
    ), {
        "llm_provider": "openai",
        "input_tokens": _int(usage.get("input_tokens") or usage.get("prompt_tokens")),
        "output_tokens": _int(usage.get("output_tokens") or usage.get("completion_tokens")),
    }


def _function_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _drop_none(
        {
            "openinference.span.kind": "TOOL",
            "tool.name": data.get("name"),
            "input.value": data.get("input"),
            "output.value": data.get("output"),
            "mcp.data": _json(data.get("mcp_data")),
        }
    ), {}


def _mcp_tools_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _drop_none(
        {
            "openinference.span.kind": "TOOL",
            "mcp.server": data.get("server"),
            "mcp.tools.listed": _json(data.get("result")),
        }
    ), {}


def _handoff_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _drop_none(
        {
            "openinference.span.kind": "CHAIN",
            "agent.handoff.from": data.get("from_agent"),
            "agent.handoff.to": data.get("to_agent"),
        }
    ), {"agent_name": data.get("to_agent")}


def _guardrail_attrs(data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return _drop_none(
        {
            "openinference.span.kind": "GUARDRAIL",
            "guardrail.name": data.get("name"),
            "guardrail.triggered": bool(data.get("triggered")),
        }
    ), {}


def _custom_attrs(span_type: str, data: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    attrs: dict[str, Any] = {
        "openinference.span.kind": "CHAIN",
        "sdk.span.type": span_type,
    }
    if data.get("name"):
        attrs["sdk.span.name"] = data.get("name")
    payload = data.get("data") or {}
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            attrs[f"sdk.data.{key}"] = value if _json_safe(value) else _json(value)
    if "usage" in data:
        attrs["llm.token_count.total"] = _int((data.get("usage") or {}).get("total_tokens"))
    return _drop_none(attrs), {}
```

#### 正規化 helper 的值

最後這組 helper 讓匯出的 spans 裡的 ID、時間戳和序列化的值保持一致。


```python
def _strip_prefix(value: Any, prefix: str) -> str | None:
    if not value:
        return None
    text = str(value)
    return text[len(prefix) :] if text.startswith(prefix) else text


def _to_otlp_timestamp(value: str | None) -> str:
    if not value:
        return ""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.") + f"{parsed.microsecond:06d}000Z"


def _span_kind(span_type: str) -> str:
    return "SPAN_KIND_CLIENT" if span_type in {"generation", "response"} else "SPAN_KIND_INTERNAL"


def _span_name(span_type: str, data: Mapping[str, Any]) -> str:
    if data.get("name"):
        return f"{span_type}.{data['name']}"
    if data.get("model"):
        return f"{span_type}.{data['model']}"
    return span_type


def _expand_messages(prefix: str, messages: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for index, message in enumerate(messages or []):
        if not isinstance(message, Mapping):
            continue
        role = message.get("role")
        content = message.get("content")
        if role is not None:
            attrs[f"{prefix}.{index}.message.role"] = role
        if isinstance(content, str):
            attrs[f"{prefix}.{index}.message.content"] = content
        elif content is not None:
            attrs[f"{prefix}.{index}.message.content"] = _json(content)
        for tool_index, tool_call in enumerate(message.get("tool_calls") or []):
            function = (tool_call or {}).get("function") or {}
            attrs[f"{prefix}.{index}.message.tool_calls.{tool_index}.tool_call.id"] = (
                tool_call or {}
            ).get("id")
            attrs[
                f"{prefix}.{index}.message.tool_calls.{tool_index}.tool_call.function.name"
            ] = function.get("name")
            attrs[
                f"{prefix}.{index}.message.tool_calls.{tool_index}.tool_call.function.arguments"
            ] = function.get("arguments")
        if message.get("tool_call_id"):
            attrs[f"{prefix}.{index}.message.tool_call_id"] = message["tool_call_id"]
        if message.get("name"):
            attrs[f"{prefix}.{index}.message.name"] = message["name"]
    return {key: value for key, value in attrs.items() if value is not None}


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, default=str, separators=(",", ":"))


def _json_safe(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _drop_none(values: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _sdk_version() -> str:
    try:
        return version("openai-agents")
    except Exception:
        return "unknown"
```

### 執行 SDK agent

`run_sdk_agent()` 直接呼叫 Agents SDK 的 runner，並處理每次有 trace 的執行都會重複的設定：掛載資料、接上 tracing、執行 agent，以及收集輸出的成果檔。


```python
async def run_sdk_agent(
    dataset_dir: Path,
    output_dir: Path,
    question: str,
    model: str,
    agent_config: AgentConfig,
    trace_id: str | None = None,
    trace_metadata: dict[str, Any] | None = None,
    halo_trace_path: str | Path | None = None,
    halo_project_id: str = "financial_diligence_analyst_optimization_context",
) -> str:
    from agents import ModelSettings as SDKModelSettings
    from agents import Runner, custom_span, flush_traces, trace
    from agents.run import RunConfig
    from agents.sandbox import Manifest, SandboxAgent, SandboxRunConfig
    from agents.sandbox.entries import Dir, LocalDir
    from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient
    from openai.types.shared import Reasoning

    output_dir.mkdir(parents=True, exist_ok=True)
    with staged_dataset_mount(dataset_dir) as staged_dataset_dir:
        write_runtime_manifest(staged_dataset_dir)
        reasoning = Reasoning(effort=agent_config.model_settings.reasoning_effort)
        agent = SandboxAgent(
            name="Synthetic dataroom diligence analyst",
            model=model,
            model_settings=SDKModelSettings(reasoning=reasoning),
            instructions=agent_config.build_instructions(),
            default_manifest=Manifest(
                entries={
                    "data": LocalDir(src=staged_dataset_dir),
                    "outputs": Dir(),
                }
            ),
        )
        client = UnixLocalSandboxClient()
        session = None
        halo_processor = None
        if halo_trace_path is not None:
            halo_processor = setup_halo_tracing(
                halo_trace_path,
                project_id=halo_project_id,
                service_version=agent_config.version,
                deployment_environment="notebook" if trace_metadata else None,
                extra_resource_attributes={
                    "agent.config.version": agent_config.version,
                    "agent.config.path": str(agent_config.path),
                },
            )
        trace_context = (
            trace(
                workflow_name="Synthetic dataroom diligence",
                trace_id=trace_id,
                metadata=trace_metadata,
            )
            if trace_id
            else None
        )
        if trace_context is not None:
            trace_context.__enter__()
        try:
            with custom_span(
                "sandbox_workspace",
                {
                    "tool.name": "sandbox_workspace",
                    "tool.input": {
                        "mounted": "data",
                        "writable": "outputs",
                        "dataset_dir": str(dataset_dir),
                        "staged_dataset_dir": str(staged_dataset_dir),
                        "agent_config": str(agent_config.path),
                        "agent_config_version": agent_config.version,
                    },
                },
                disabled=trace_context is None,
            ):
                with custom_span(
                    "agent_config",
                    {
                        "tool.name": "agent_config",
                        "tool.input": {
                            "version": agent_config.version,
                            "required_artifacts": agent_config.required_artifacts,
                        },
                    },
                    disabled=trace_context is None,
                ):
                    pass
                session = await client.create(manifest=agent.default_manifest)
            async with session:
                result = await Runner.run(
                    agent,
                    build_user_prompt(question, agent_config),
                    run_config=RunConfig(
                        sandbox=SandboxRunConfig(session=session),
                        workflow_name="Synthetic dataroom diligence",
                        trace_id=trace_id,
                        trace_metadata=trace_metadata,
                        tracing_disabled=trace_id is None,
                    ),
                    max_turns=30,
                )
                for filename in agent_config.required_artifacts:
                    try:
                        with custom_span(
                            "artifact_write",
                            {
                                "tool.name": "artifact_write",
                                "tool.input": {"filename": filename},
                            },
                            disabled=trace_context is None,
                        ):
                            with await session.read(Path("outputs") / filename) as handle:
                                (output_dir / filename).write_bytes(handle.read())
                    except Exception:
                        continue
                return str(result.final_output)
        finally:
            delete = getattr(client, "delete", None)
            if delete is not None and session is not None:
                try:
                    await delete(session)
                except Exception:
                    pass
            if trace_context is not None:
                trace_context.__exit__(None, None, None)
            if halo_processor is not None:
                try:
                    flush_traces()
                except Exception:
                    pass
                try:
                    halo_processor.shutdown()
                except Exception:
                    pass


@contextmanager
def staged_dataset_mount(dataset_dir: Path) -> Iterator[Path]:
    """Prepare a writable SDK mount copy without mutating the source dataroom."""
    with tempfile.TemporaryDirectory(prefix="synthetic-dataroom-mount-") as tmp:
        staged_dir = Path(tmp) / dataset_dir.name
        shutil.copytree(dataset_dir, staged_dir)
        write_runtime_tools(staged_dir)
        yield staged_dir.resolve()


def write_runtime_manifest(dataset_dir: Path) -> None:
    manifest = {
        "runtime_scope": "sdk_agent_visible_dataroom",
        "files": sorted(
            str(path.relative_to(dataset_dir))
            for path in dataset_dir.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        ),
    }
    (dataset_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
```

## Step 3. 產生有 trace 的執行

問題刻意設計得很多樣，讓 eval 套件涵蓋 agent 可能出錯的幾種方式。這個 notebook 預設跑五條 traces，讓即時執行的路徑保持實用，同時仍涵蓋幾種不同的行為。之後想要更廣的涵蓋範圍，還有一個更大的題庫可以用。

每次執行都走非同步的 Agents SDK 路徑，寫出真實的 trace 和必要的成果檔。


```python
QUESTION_BANK = [
    "What do runway and burn tell us about near-term financing risk?",
    "How strong is revenue quality, and which ARR figure should we rely on?",
    "What is the real customer concentration risk after parent-account rollups?",
    "What legal exposure should an acquirer investigate first?",
    "How ready is the company for enterprise security review?",
    "Which contradictions appear across the board deck, finance exports, and management narratives?",
    "What unsupported metrics should we refuse to infer from the dataroom?",
    "What follow-up questions should management answer before an investment committee review?",
    "What are the top three diligence risks, ranked by severity?",
    "Which claims in the materials look directionally useful but still need stronger evidence?",
]

# Using 5 questions as the default, with more available if you want broader coverage later.

DEFAULT_TRACE_INDICES = [0, 1, 2, 4, 6]
TRACE_LIMIT = len(DEFAULT_TRACE_INDICES)
QUESTIONS = [QUESTION_BANK[index] for index in DEFAULT_TRACE_INDICES]


@dataclass
class TraceRecord:
    trace_id: str
    sdk_trace_id: str
    trace_label: str
    question: str
    answer: str
    output_dir: str
    mode: str


def sdk_trace_id(label: str) -> str:
    # Agents SDK trace uploads expect ids shaped like `trace_<hex>`.
    return f"trace_{hashlib.sha256(label.encode('utf-8')).hexdigest()[:32]}"


def exported_trace_id(label: str) -> str:
    # The local HALO exporter strips the SDK `trace_` prefix before writing JSONL.
    return sdk_trace_id(label).removeprefix("trace_")


async def generate_traces(dataset: Path, questions: list[str]) -> list[TraceRecord]:
    traces: list[TraceRecord] = []
    for index, question in enumerate(questions, start=1):
        label = f"trace-{index:02d}"
        print(f"Running {label}/{len(questions):02d}: {question}")
        output_dir = TRACE_DIR / f"trace_{index:02d}"
        output_dir.mkdir(parents=True, exist_ok=True)
        real_sdk_trace_id = sdk_trace_id(label)
        real_exported_trace_id = exported_trace_id(label)
        answer = await run_sdk_agent(
            dataset_dir=dataset,
            output_dir=output_dir,
            question=question,
            model=AGENT_MODEL,
            agent_config=agent_config,
            trace_id=real_sdk_trace_id,
            trace_metadata={"notebook_trace_id": label},
            halo_trace_path=HALO_TRACE_PATH,
        )
        traces.append(
            TraceRecord(
                trace_id=real_exported_trace_id,
                sdk_trace_id=real_sdk_trace_id,
                trace_label=label,
                question=question,
                answer=answer,
                output_dir=str(output_dir.relative_to(PROJECT_ROOT)),
                mode="sdk",
            )
        )
    return traces


trace_generation_started = time.perf_counter()
traces = await generate_traces(dataset, QUESTIONS)
print(f"Trace generation completed in {format_duration(time.perf_counter() - trace_generation_started)}")
assert len(traces) == TRACE_LIMIT

for trace in traces:
    print(f"{trace.trace_label}: {trace.question}")
    print(textwrap.shorten(trace.answer.replace("\n", " "), width=180, placeholder="..."))
    print()
```

??? note "輸出"

    ```text
    Running trace-01/05: What do runway and burn tell us about near-term financing risk?
    Running trace-02/05: How strong is revenue quality, and which ARR figure should we rely on?
    Running trace-03/05: What is the real customer concentration risk after parent-account rollups?
    Running trace-04/05: How ready is the company for enterprise security review?
    Running trace-05/05: What unsupported metrics should we refuse to infer from the dataroom?
    Trace generation completed in 7m 59s
    trace-01: What do runway and burn tell us about near-term financing risk?
    Near-term financing risk is elevated. Finance reports `$2.9M` monthly cash burn and `11 months` runway, and the board packet corroborates both figures....

    trace-02: How strong is revenue quality, and which ARR figure should we rely on?
    **Answer** - Revenue quality is **moderate, not clean**: real scale and 69% gross margin, but ARR definition drift, unvalidated retention, concentration, and renewal risk weaken...

    trace-03: What is the real customer concentration risk after parent-account rollups?
    **Answer** - Real concentration risk is **high**: Northstar Bank + Northstar Capital Markets roll up to **Northstar Holdings at $12.4M**, or **33.6% of controlled FY2025 ARR**....

    trace-04: How ready is the company for enterprise security review?
    **Answer** - The company is **partially ready, but not ready for frictionless enterprise security review**: SOC 2 Type I is complete, but SOC 2 Type II fieldwork is still in...

    trace-05: What unsupported metrics should we refuse to infer from the dataroom?
    **Answer** Refuse to infer these unsupported or conflicted metrics from the dataroom: - `CAC payback`: explicitly `not_provided`; requested but not supplied....
    ```

### 檢視 agent 的成果檔

每次有 trace 的執行，都會寫出 harness 要求的完整成果檔。下面第一次執行會顯示 agent 產出的檔案，讓你可以一起檢查答案、證據和未解決的問題。


````python
def show_trace_artifacts(trace: TraceRecord) -> None:
    output_dir = PROJECT_ROOT / trace.output_dir
    for artifact in agent_config.required_artifacts:
        path = output_dir / artifact
        language = {
            ".md": "markdown",
            ".json": "json",
            ".csv": "csv",
        }.get(path.suffix, "text")
        display(Markdown(f"### `{artifact}`\n```{language}\n{path.read_text(encoding='utf-8').rstrip()}\n```"))


show_trace_artifacts(traces[0])
````

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

## Step 4. 產生範例人工回饋和模型洞察

這一節模擬人類專家在 agent 執行後審閱 traces。在真實的盡職調查流程裡，這可能是財務主管，或是其他知道哪些細節對決策重要的案件專家。在這個範例中，審閱者指出幾件事：母帳號的彙總比法律實體的集中度更重要；沒有驗證過的管理層 NRR 估計值，不該變成正式指標；證據只支持 Type I 時，說「SOC 2 complete」太含糊。

模型產生的洞察則分開處理。在完全自動化的路徑中，會由 LLM 審閱同樣的 traces，並提出反覆出現的問題或缺少的行為。這道額外的處理增加涵蓋範圍，而領域專家的審閱則加入立基於實際工作的專業判斷。
````python
def feedback_item(
    trace: TraceRecord,
    summary: str,
    required: list[str],
    prohibited: list[str],
    theme: str,
) -> dict[str, Any]:
    return {
        "feedback_id": f"human-{trace.trace_label}",
        "trace_id": trace.trace_id,
        "trace_label": trace.trace_label,
        "question": trace.question,
        "source_type": "human_feedback",
        "theme": theme,
        "summary": summary,
        "required_observations": required,
        "prohibited_claims": prohibited,
    }


def generate_mock_human_feedback(traces: list[TraceRecord]) -> list[dict[str, Any]]:
    specs_by_question = {
        "What do runway and burn tell us about near-term financing risk?": (
            "State both the 11-month runway and rising burn as financing risk, not just a generic red flag.",
            ["Name the 11-month runway", "Tie burn to near-term financing pressure"],
            ["Do not imply the company has more than 12 months of runway"],
            "financial_risk",
        ),
        "How strong is revenue quality, and which ARR figure should we rely on?": (
            "Use the controlled ARR bridge as the reliable figure and preserve the board-versus-finance contradiction.",
            ["Prefer finance ARR over board ARR", "Preserve the ARR contradiction"],
            ["Do not silently reconcile the ARR gap"],
            "revenue_quality",
        ),
        "What is the real customer concentration risk after parent-account rollups?": (
            "Roll concentration up to Northstar Holdings. Legal-entity framing understates the real dependency.",
            ["Mention parent-account concentration", "Use account_hierarchy.csv"],
            ["Do not stop at legal-entity concentration"],
            "customer_concentration",
        ),
        "How ready is the company for enterprise security review?": (
            "Be exact about certification status: Type I is complete; Type II is still in progress.",
            ["Distinguish Type I from Type II", "Treat sales FAQ as weaker evidence"],
            ["Do not say SOC 2 is simply complete"],
            "security_readiness",
        ),
        "What unsupported metrics should we refuse to infer from the dataroom?": (
            "Refuse official NRR and CAC payback when the dataroom does not support them.",
            ["Mark official NRR unsupported", "Mark CAC payback unsupported"],
            ["Do not promote the management NRR estimate into an official metric"],
            "unsupported_metrics",
        ),
    }
    return [feedback_item(trace, *specs_by_question[trace.question]) for trace in traces]


def extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    candidate = fenced.group(1).strip() if fenced else text
    return json.loads(candidate)


def generate_llm_feedback(traces: list[TraceRecord]) -> list[dict[str, Any]]:
    payload = [asdict(trace) for trace in traces]
    response = client.responses.create(
        model=ANALYSIS_MODEL,
        input=f"""
You are reviewing traces from a financial diligence analyst agent.
Return JSON only: a list of objects with keys `insight_id`, `trace_id`, `question`, `source_type`, and `observations`.
Use `source_type` = `llm_insight`.
For `trace_id`, copy the provided `trace_id` field exactly; do not use `sdk_trace_id` or `trace_label`.
For each trace, identify concise recurring-behavior observations that could help generate evals later.
Do not restate the whole answer. Do not invent unavailable evidence.

Traces:
{json.dumps(payload, indent=2)}
""".strip(),
    )
    parsed = extract_json(response.output_text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON list of LLM insights.")
    trace_labels = {trace.trace_id: trace.trace_label for trace in traces}
    for item in parsed:
        try:
            item["trace_label"] = trace_labels[item["trace_id"]]
        except KeyError as exc:
            raise ValueError(f"Unknown trace_id in LLM feedback: {item['trace_id']}") from exc
    return parsed


feedback_started = time.perf_counter()
human_feedback = generate_mock_human_feedback(traces)
llm_feedback = generate_llm_feedback(traces)
print(f"Feedback generation completed in {format_duration(time.perf_counter() - feedback_started)}")
assert len(human_feedback) == TRACE_LIMIT
assert len(llm_feedback) == TRACE_LIMIT

print("Human feedback items:", len(human_feedback))
print("LLM insight items:", len(llm_feedback))
print("\nExample human feedback:")
print(json.dumps(human_feedback[0], indent=2))
print("\nExample LLM insight:")
print(json.dumps(llm_feedback[0], indent=2))
````

??? note "輸出"

    ```text
    Feedback generation completed in 13s
    Human feedback items: 5
    LLM insight items: 5

    Example human feedback:
    {
      "feedback_id": "human-trace-01",
      "trace_id": "43d9b03619a9d2ed4d2f3e3fd17c8bf4",
      "trace_label": "trace-01",
      "question": "What do runway and burn tell us about near-term financing risk?",
      "source_type": "human_feedback",
      "theme": "financial_risk",
      "summary": "State both the 11-month runway and rising burn as financing risk, not just a generic red flag.",
      "required_observations": [
        "Name the 11-month runway",
        "Tie burn to near-term financing pressure"
      ],
      "prohibited_claims": [
        "Do not imply the company has more than 12 months of runway"
      ]
    }

    Example LLM insight:
    {
      "insight_id": "llm_insight_01",
      "trace_id": "43d9b03619a9d2ed4d2f3e3fd17c8bf4",
      "question": "What do runway and burn tell us about near-term financing risk?",
      "source_type": "llm_insight",
      "observations": [
        "Flags elevated financing risk when runway is under 12 months and monthly burn is cited from finance and board sources.",
        "Prefers finance-controlled ARR over board headline ARR when ARR definitions conflict.",
        "Explicitly identifies missing liquidity data such as cash balance, debt availability, covenants, and financing plan.",
        "Includes source citations for key numeric claims and notes validation/artifact completion."
      ],
      "trace_label": "trace-01"
    }
    ```

## Step 5. 從 traces 和回饋產生 Promptfoo evals

eval 套件是由 LLM 根據目前收集到的證據動態產生的：有 trace 的行為、人工回饋和模型產生的觀察。這把評論變成測試，下一版 harness 修改之後可以再跑一次。

Promptfoo 是用來評測和 red-teaming LLM 應用的開源 CLI 和函式庫。在這個 notebook 裡，產生出來的行為會變成 Promptfoo 的測試案例：每個案例可以結合字面比對的 assertions 和 LLM rubric judge，所以同一個關卡既能檢查精確的要求，也能檢查審閱者在語意上的意圖。

evals 是值得讓領域專家和開發者投入人力的地方。完全自動化的流程可以很快提出有用的 evals，但在它們進入長期測試套件之前，人還是應該檢查這些 evals 準不準確、有沒有代表性，以及衡量的是不是真正重要的行為。


```python
def generate_feedback_derived_evals(
    traces: list[TraceRecord],
    human_feedback: list[dict[str, Any]],
    llm_feedback: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    min_eval_count = min(5, max(2, len(traces)))
    max_eval_count = min(7, max(min_eval_count, len(traces) + 2))
    response = client.responses.create(
        model=EVAL_GENERATION_MODEL,
        input=f"""
You are designing an eval suite for an OpenAI Agents SDK-backed financial diligence analyst.
Use the traces, human feedback, and LLM insights below to generate {min_eval_count} to {max_eval_count} durable eval definitions.
Return JSON only: a list of objects with keys `eval_id`, `title`, `scoring_method`, `expected_behavior`, `source_trace_id`, `rubric`, `deterministic_assertions`, `suggested_pass_example`, and `suggested_fail_example`.
`scoring_method` must be one of `deterministic`, `llm_judge`, or `hybrid`.
`source_trace_id` must exactly match the provided `trace_id` field for the trace whose answer should be scored. Do not use `sdk_trace_id` or `trace_label` for this field; those are only for SDK transport and human-readable references.
`rubric` must be a concise pass/fail grading rubric suitable for Promptfoo `llm-rubric`.
`deterministic_assertions` must be a list of Promptfoo-style assertion objects and may use only `contains`, `icontains`, or `not-contains` when a literal check is clearly useful; otherwise return an empty list.
Prefer reusable behaviors over one-off trace restatements.

Traces:
{json.dumps([asdict(trace) for trace in traces], indent=2)}

Human feedback:
{json.dumps(human_feedback, indent=2)}

LLM insights:
{json.dumps(llm_feedback, indent=2)}
""".strip(),
    )
    parsed = extract_json(response.output_text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON list of eval definitions.")
    trace_labels = {trace.trace_id: trace.trace_label for trace in traces}
    for item in parsed:
        try:
            item["source_trace_label"] = trace_labels[item["source_trace_id"]]
        except KeyError as exc:
            raise ValueError(f"Unknown source_trace_id in generated eval: {item['source_trace_id']}") from exc
    return parsed


eval_generation_started = time.perf_counter()
eval_suite = generate_feedback_derived_evals(traces, human_feedback, llm_feedback)
print(f"Eval generation completed in {format_duration(time.perf_counter() - eval_generation_started)}")
assert all({"title", "scoring_method", "suggested_pass_example", "suggested_fail_example", "expected_behavior", "source_trace_id", "rubric", "deterministic_assertions"} <= set(item) for item in eval_suite)


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(str(row[column]) for column in columns) + " |" for row in rows]
    return "\n".join([header, divider, *body])


display(Markdown(markdown_table(eval_suite, ["title", "scoring_method", "expected_behavior"])))

for item in eval_suite:
    print(f"\n{item['title']}")
    print(" pass:", item["suggested_pass_example"])
    print(" fail:", item["suggested_fail_example"])
```

??? note "輸出"

    ```text
    Eval generation completed in 52s
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text

    Runway and burn must be translated into near-term financing risk
     pass: Near-term financing risk is elevated: the company has only 11 months of runway and meaningful monthly burn, creating pressure to reduce burn, improve cash conversion, or raise capital within a sub-12-month window.
     fail: Financing risk appears manageable because the company has enough runway for the next year and should be able to continue operating without near-term funding pressure.

    Revenue quality assessment must prefer finance-controlled ARR and preserve ARR contradictions
     pass: Revenue quality is moderate, not clean. For underwriting, use the finance-controlled ARR bridge at $36.9M, while treating the $43.0M board ARR and $40.8M bookings-adjusted view as non-comparable or planning figures because they include items not classified as recurring ARR.
     fail: Revenue quality is strong and the company has $43.0M of ARR; the board number can be used because it reconciles to the finance ARR bridge after normal adjustments.

    Customer concentration must be assessed after parent-account rollups
     pass: Concentration risk is high after parent rollups: Northstar Bank and Northstar Capital Markets roll up to Northstar Holdings at about $12.4M, roughly one-third of finance-controlled ARR. Looking only at legal entities understates the dependency.
     fail: Customer concentration is acceptable because no single legal entity exceeds the threshold after reviewing the top-customer list.

    Enterprise security readiness must distinguish SOC 2 Type I from Type II
     pass: The company is partially ready, not frictionless: SOC 2 Type I is complete, but Type II fieldwork is still in progress and no Type II report is available. Sales materials saying 'SOC 2 complete' should be treated cautiously because enterprise buyers are waiting on Type II evidence.
     fail: The company is ready for enterprise security review because SOC 2 is complete and the sales FAQ confirms there should be no security blocker.

    Unsupported metrics must be refused rather than inferred
     pass: Refuse to infer CAC payback because it is not provided. Also refuse to treat 122% NRR as official; it is an unvalidated management estimate and should not be used as a definitive retention metric.
     fail: The company has 122% official NRR and CAC payback appears attractive based on its revenue growth, so both can be used in underwriting.
    ```

## Step 6. 用 Promptfoo 驗證目前的 harness

Promptfoo 會拿產生的測試去跑目前 trace 的輸出，讓迴圈知道 harness 現在哪些地方表現不錯、哪些期望還沒達到。Promptfoo 適合這個角色，因為它可以把針對字面要求的確定性檢查，和針對語意品質的 `llm-rubric` judge 結合起來。

在這個 notebook 裡，Promptfoo 關卡是對既有的 trace 輸出打分數。要驗證未來的 harness 修改版，就把 trace 輸出的 provider 換成會執行候選 agent 的 provider。這些 Promptfoo 結果會成為下面傳給 HALO 的最佳化輸入的一部分。即使 eval 的產生是自動化的，人還是可以在讓它們反覆引導最佳化之前，先把比較弱的 evals 收緊。


### 建立 Promptfoo 測試 harness

provider 把既有的 trace 輸出回給 Promptfoo，test builder 則把產生的 eval 定義變成可以執行的 Promptfoo 案例。


```python
PROMPTFOO_PROVIDER = r'''from __future__ import annotations

import json
from pathlib import Path


def call_api(prompt: str, options: dict, context: dict) -> dict:
    config = options.get("config", {})
    trace_outputs = json.loads(Path(config["trace_outputs_path"]).read_text(encoding="utf-8"))
    trace_id = (context.get("vars") or {}).get("trace_id")
    trace = trace_outputs[trace_id]
    return {
        "output": trace["answer"],
        "metadata": {
            "trace_id": trace_id,
            "question": trace["question"],
        },
    }
'''


def trace_for_eval(item: dict[str, Any], traces: list[TraceRecord]) -> TraceRecord:
    trace_by_id = {trace.trace_id: trace for trace in traces}
    try:
        return trace_by_id[item["source_trace_id"]]
    except KeyError as exc:
        raise ValueError(f"Unknown source_trace_id in generated eval: {item['source_trace_id']}") from exc

def promptfoo_test_from_eval(item: dict[str, Any], trace: TraceRecord) -> dict[str, Any]:
    assertions = [
        assertion
        for assertion in item.get("deterministic_assertions") or []
        if isinstance(assertion, dict)
        and assertion.get("type") in {"contains", "icontains", "not-contains"}
        and assertion.get("value")
    ]
    assertions.append({
        "type": "llm-rubric",
        "provider": f"openai:{JUDGE_MODEL}",
        "threshold": 0.8,
        "value": item["rubric"],
    })
    return {
        "description": item["title"],
        "vars": {
            "question": trace.question,
            "trace_id": trace.trace_id,
            "trace_label": trace.trace_label,
        },
        "metadata": {
            "eval_id": item["eval_id"],
            "scoring_method": item["scoring_method"],
        },
        "assert": assertions,
    }


def write_promptfoo_artifacts(eval_suite: list[dict[str, Any]], traces: list[TraceRecord]) -> dict[str, Path]:
    promptfoo_dir = ARTIFACT_DIR / "promptfoo"
    promptfoo_dir.mkdir(parents=True, exist_ok=True)
    provider_path = promptfoo_dir / "trace_output_provider.py"
    trace_outputs_path = promptfoo_dir / "trace_outputs.json"
    config_path = promptfoo_dir / "promptfooconfig.yaml"
    output_path = promptfoo_dir / "promptfoo_results.json"

    provider_path.write_text(PROMPTFOO_PROVIDER, encoding="utf-8")
    trace_outputs_path.write_text(
        json.dumps({trace.trace_id: asdict(trace) for trace in traces}, indent=2) + "\n",
        encoding="utf-8",
    )
    tests = [promptfoo_test_from_eval(item, trace_for_eval(item, traces)) for item in eval_suite]
    config = {
        "description": "Feedback-derived diligence eval gate",
        "prompts": ["{{question}}"],
        "providers": [{
            "id": "file://trace_output_provider.py",
            "label": "current-trace-output",
            "config": {"trace_outputs_path": str(trace_outputs_path)},
        }],
        "tests": tests,
    }
    # JSON is valid YAML, which keeps the generated config easy to inspect without
    # adding another serialization dependency to the notebook.
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return {
        "dir": promptfoo_dir,
        "provider": provider_path,
        "trace_outputs": trace_outputs_path,
        "config": config_path,
        "output": output_path,
    }


def promptfoo_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = (data.get("results") or {}).get("outputs") or (data.get("results") or {}).get("results") or []
    rows = []
    for result in results:
        grading = result.get("gradingResult") or {}
        components = grading.get("componentResults") or []
        failing_component = next(
            (
                component
                for component in components
                if isinstance(component, dict) and component.get("pass") is False
            ),
            None,
        )
        reason = str(grading.get("reason") or "")
        if not reason and failing_component:
            reason = str(failing_component.get("reason") or "")
        if not reason and components and isinstance(components[0], dict):
            reason = str(components[0].get("reason") or "")
        test_case = result.get("testCase") or {}
        test_vars = test_case.get("vars") or {}
        rows.append({
            "eval_id": (test_case.get("metadata") or {}).get("eval_id"),
            "title": test_case.get("description") or "Untitled",
            "trace_id": test_vars.get("trace_id"),
            "trace_label": test_vars.get("trace_label"),
            "passed": bool(result.get("success")),
            "score": result.get("score"),
            "explanation": reason,
        })
    return {
        "backend": "promptfoo",
        "total": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "rows": rows,
    }
```

### 執行 Promptfoo 關卡

執行產生的測試套件，並總結目前 harness 的結果。


```python
def run_promptfoo_feedback_eval_gate(eval_suite: list[dict[str, Any]], traces: list[TraceRecord]) -> dict[str, Any]:
    artifacts = write_promptfoo_artifacts(eval_suite, traces)
    command = [
        "npx",
        "--yes",
        f"promptfoo@{PROMPTFOO_VERSION}",
        "eval",
        "--no-cache",
        "--no-table",
        "-c",
        str(artifacts["config"]),
        "-o",
        str(artifacts["output"]),
    ]
    env = os.environ.copy()
    env["PROMPTFOO_PYTHON"] = sys.executable
    env["PROMPTFOO_CONFIG_DIR"] = str(artifacts["dir"] / ".promptfoo")
    env["PROMPTFOO_DISABLE_WAL_MODE"] = "true"
    process = subprocess.run(
        command,
        cwd=artifacts["dir"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if not artifacts["output"].exists():
        raise RuntimeError(f"Promptfoo did not write results. Output:\n{process.stdout[-4000:]}")
    summary = promptfoo_summary(artifacts["output"])
    summary["command"] = command
    summary["returncode"] = process.returncode
    summary["result_path"] = str(artifacts["output"].relative_to(PROJECT_ROOT))
    summary["log_tail"] = process.stdout[-4000:]
    return summary


promptfoo_started = time.perf_counter()
gate_result = run_promptfoo_feedback_eval_gate(eval_suite, traces)
print(f"Promptfoo gate completed in {format_duration(time.perf_counter() - promptfoo_started)}")
display(Markdown(markdown_table(gate_result["rows"], ["title", "trace_label", "passed", "score", "explanation"])))
print({key: gate_result[key] for key in ["backend", "total", "passed", "failed", "result_path"]})
```

??? note "輸出"

    ```text
    Promptfoo gate completed in 9s
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    {'backend': 'promptfoo', 'total': 5, 'passed': 5, 'failed': 0, 'result_path': 'examples/agents_sdk/agent_improvement_loop_artifacts/promptfoo/promptfoo_results.json'}
    ```

## Step 7. 執行 HALO 並寫出 handoff

HALO 是 Hierarchical Agent Loop Optimization 的縮寫，是一套從執行 traces 改進 agent harness 的方法論，也是一個 Python 套件。[HALO repository](https://github.com/context-labs/halo) 描述的迴圈是：收集 traces、分析反覆出現的 harness 層級失敗、把報告交給 coding agent，harness 改完後再重複一次。

迴圈走到這裡，就會把累積的證據變成提議的 harness 修改。HALO 會一起審閱目前的 harness、agent traces、人工回饋、模型回饋、產生的 evals 和 Promptfoo 結果，然後產出一組排好序的修改，供下一輪實作使用。

HALO 在這裡的價值是，它同時對整個迴圈做推理。它能把人的判斷、執行時的行為和 eval 結果放在一起用，再把結果包成 handoff，讓 Codex 能據此實作改進 harness 的程式碼修改。


### 收集 HALO 的輸入

建立一個 context 物件，把目前的 harness、traces、回饋、evals 和關卡結果放在一起。


```python
from datetime import datetime, timezone


def serialize_agent_config(config: AgentConfig) -> dict[str, Any]:
    return {
        "version": config.version,
        "system_prompt": config.system_prompt,
        "model_settings": asdict(config.model_settings),
        "tool_policy": config.tool_policy,
        "eval_metadata": config.eval_metadata,
    }


def build_halo_context(
    traces: list[TraceRecord],
    human_feedback: list[dict[str, Any]],
    llm_feedback: list[dict[str, Any]],
    eval_suite: list[dict[str, Any]],
    gate_result: dict[str, Any],
    agent_config: AgentConfig,
) -> dict[str, Any]:
    return {
        "traces": [asdict(trace) for trace in traces],
        "human_feedback": human_feedback,
        "llm_feedback": llm_feedback,
        "eval_suite": eval_suite,
        "gate_result": gate_result,
        "agent_config": serialize_agent_config(agent_config),
    }


def synthetic_trace_id(value: str) -> str:
    return hashlib.sha256(f"halo-context-{value}".encode("utf-8")).hexdigest()[:32]


def synthetic_span_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def synthetic_span(*, trace_id: str, span_id: str, name: str, observation_kind: str, attributes: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": "",
        "trace_state": "",
        "name": name,
        "kind": "SPAN_KIND_INTERNAL",
        "start_time": now,
        "end_time": now,
        "status": {"code": "STATUS_CODE_OK", "message": ""},
        "resource": {"attributes": {"service.name": "financial-diligence-analyst"}},
        "scope": {"name": "halo-optimization-context", "version": "1"},
        "attributes": {
            "openinference.span.kind": observation_kind,
            "inference.export.schema_version": 1,
            "inference.project_id": "financial_diligence_analyst_optimization_context",
            "inference.observation_kind": observation_kind,
            **attributes,
        },
    }


def halo_input_summary(context: dict[str, Any]) -> str:
    rows = [
        ("Current harness config", 1, "global config span", "system prompt, model settings, tool policy, eval metadata"),
        ("SDK execution traces", len(context["traces"]), "original runtime traces", "agent steps, tool calls, outputs"),
        ("Human feedback", len(context["human_feedback"]), "appended to the source trace", "reviewer summary, required observations, prohibited claims"),
        ("LLM feedback", len(context["llm_feedback"]), "appended to the source trace", "model-generated observations"),
        ("Generated eval definitions", len(context["eval_suite"]), "appended to the source trace", "expected behavior, rubric, pass/fail examples"),
        ("Promptfoo row results", len(context["gate_result"]["rows"]), "appended to the source trace", "pass/fail outcome and explanation"),
        ("Promptfoo gate summary", 1, "global summary span", "suite totals across all evals"),
    ]
    lines = [
        "### HALO input summary",
        "",
        "| Input signal | Count | Where it lives | What is included |",
        "| --- | ---: | --- | --- |",
    ]
    lines.extend(f"| {name} | {count} | {location} | {included} |" for name, count, location, included in rows)
    return "\n".join(lines)
```

### 把回饋、產生的 evals 和 eval 結果附到 traces 上

寫出 HALO 要檢查的合併後 trace 檔。人工回饋、LLM 回饋、產生的 eval 定義和每一列的 Promptfoo 結果，都會附到對應的執行 trace 上。整體的關卡摘要維持全域，因為它描述的是整個套件。


```python
def write_halo_optimization_context(context: dict[str, Any]) -> Path:
    context_path = ARTIFACT_DIR / "halo_optimization_context.jsonl"
    lines = HALO_TRACE_PATH.read_text(encoding="utf-8").splitlines() if HALO_TRACE_PATH.exists() else []
    lines.append(json.dumps(synthetic_span(
        trace_id=synthetic_trace_id("current-harness-config"),
        span_id=synthetic_span_id("current-harness-config"),
        name="harness.config",
        observation_kind="HARNESS_CONFIG",
        attributes={
            "harness.version": context["agent_config"]["version"],
            "harness.system_prompt": context["agent_config"]["system_prompt"],
            "harness.model_settings": json.dumps(context["agent_config"]["model_settings"]),
            "harness.tool_policy": json.dumps(context["agent_config"]["tool_policy"]),
            "harness.eval_metadata": json.dumps(context["agent_config"]["eval_metadata"]),
            "optimizer.signal_source": "harness_config",
        },
    )))
    for index, item in enumerate(context["human_feedback"]):
        lines.append(json.dumps(synthetic_span(
            trace_id=item["trace_id"],
            span_id=synthetic_span_id(f"human-feedback-{index}"),
            name="human_feedback.comment",
            observation_kind="HUMAN_FEEDBACK",
            attributes={
                "feedback.id": item["feedback_id"],
                "feedback.trace_id": item["trace_id"],
                "feedback.trace_label": item["trace_label"],
                "feedback.question": item["question"],
                "feedback.summary": item["summary"],
                "feedback.required_observations": json.dumps(item["required_observations"]),
                "feedback.prohibited_claims": json.dumps(item["prohibited_claims"]),
                "optimizer.signal_source": "human_feedback",
            },
        )))
    for index, item in enumerate(context["llm_feedback"]):
        lines.append(json.dumps(synthetic_span(
            trace_id=item["trace_id"],
            span_id=synthetic_span_id(f"llm-insight-{index}"),
            name="llm_feedback.insight",
            observation_kind="LLM_FEEDBACK",
            attributes={
                "llm_feedback.id": item["insight_id"],
                "llm_feedback.trace_id": item["trace_id"],
                "llm_feedback.trace_label": item["trace_label"],
                "llm_feedback.question": item["question"],
                "llm_feedback.observations": json.dumps(item["observations"]),
                "optimizer.signal_source": "llm_feedback",
            },
        )))
    for index, item in enumerate(context["eval_suite"]):
        lines.append(json.dumps(synthetic_span(
            trace_id=item["source_trace_id"],
            span_id=synthetic_span_id(f"generated-eval-{index}"),
            name="generated_eval.definition",
            observation_kind="EVAL",
            attributes={
                "eval.id": item["eval_id"],
                "eval.trace_id": item["source_trace_id"],
                "eval.trace_label": item["source_trace_label"],
                "eval.title": item["title"],
                "eval.method": item["scoring_method"],
                "eval.expected_behavior": item["expected_behavior"],
                "eval.pass_example": item["suggested_pass_example"],
                "eval.fail_example": item["suggested_fail_example"],
                "optimizer.signal_source": "generated_eval",
            },
        )))
    lines.append(json.dumps(synthetic_span(
        trace_id=synthetic_trace_id("eval-gate-summary"),
        span_id=synthetic_span_id("eval-gate-summary"),
        name="eval_gate.summary",
        observation_kind="EVAL_RESULT",
        attributes={
            "eval_gate.total": context["gate_result"]["total"],
            "eval_gate.passed": context["gate_result"]["passed"],
            "eval_gate.failed": context["gate_result"]["failed"],
            "optimizer.signal_source": "eval_gate",
        },
    )))
    for index, item in enumerate(context["gate_result"]["rows"]):
        lines.append(json.dumps(synthetic_span(
            trace_id=item["trace_id"],
            span_id=synthetic_span_id(f"eval-gate-row-{index}"),
            name="eval_gate.result",
            observation_kind="EVAL_RESULT",
            attributes={
                "eval.id": item["eval_id"],
                "eval.title": item["title"],
                "eval.trace_id": item["trace_id"],
                "eval.trace_label": item["trace_label"],
                "eval.passed": item["passed"],
                "eval.explanation": item["explanation"],
                "optimizer.signal_source": "eval_gate",
            },
        )))
    context_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return context_path
```

### 定義 HALO 的輸出 prompt

這個 prompt 告訴 HALO 要產出什麼樣的報告，包括 Codex 在最終 handoff 檔裡應該收到的各個段落。你可以依公司的工作流程、審閱流程或使用情境來客製。


```python
def render_halo_prompt() -> str:
    return """
Analyze the financial diligence analyst optimization context as the central source of truth.
The JSONL contains the current harness configuration, agent execution traces, human feedback, LLM insights, generated eval definitions, and eval-gate results.
Treat human feedback as first-class evidence.
Before recommending a change, compare the evidence against the current harness config and distinguish:
- a requirement that is missing from the harness,
- a requirement already present but not reliably followed in execution, and
- an implementation or observability defect.

Write an implementation-first Codex handoff in this exact top-level order:
1. `## Executive summary`
2. `## Top 3 changes to implement first`
3. `## Ranked recommendation table`
4. `## Supporting diagnosis and evidence`
5. `## Detailed recommendations`
6. `## Insights by feedback source`
7. `## Machine-readable summary`

Section requirements:
- `## Executive summary`: briefly state what the current harness already does well, what the highest-value remaining gaps are, and whether the current eval gate passed.
- `## Top 3 changes to implement first`: list the three most valuable implementation moves with concise rationale.
- `## Ranked recommendation table`: include rank, recommendation, impact, confidence, implementation effort, evidence, and validation.
- `## Supporting diagnosis and evidence`: include recurring harness-level failure modes, classify each against the current harness as missing requirement vs already-present-but-not-reliably-followed vs implementation/observability defect, and state the evidence source for each.
- `## Detailed recommendations`: use these exact subsection headings in this order and do not use the word "owner" in them:
  - `### Behavior contract`
    - `#### Prompt`
    - `#### Skills`
  - `### Runtime implementation`
    - `#### Tools`
    - `#### Control flow`
    - `#### Routing`
  - `### Output contract`
    - `#### Artifact schema`
  - `### Observability and evals`
    - `#### Observability`
    - `#### Evals`
- `## Insights by feedback source`: summarize what came from traces, human feedback, LLM feedback, generated evals, eval-gate results, and harness config.
- `## Machine-readable summary`: include one fenced JSON block with `top_priorities`.

Do not add extra top-level sections outside that order.
""".strip()
```

### 執行 HALO 並整理報告

HALO 會收到五條 SDK 執行 traces，加上兩條合成的全域 traces：一條記錄目前的 harness 設定，另一條記錄 Promptfoo 關卡摘要。這就是為什麼它的 trace 數量比前面建立的五次 agent 執行還多。

產生完整的最佳化報告、儲存 handoff 檔，並在 notebook 裡顯示優先度最高的建議。


```python
async def run_halo_optimization(context_path: Path) -> str:
    from agents import set_trace_processors
    from engine.agents.agent_config import AgentConfig as HaloAgentConfig
    from engine.engine_config import EngineConfig
    from engine.main import stream_engine_async
    from engine.sandbox.sandbox import Sandbox
    from engine.model_config import ModelConfig
    from engine.models.engine_output import AgentOutputItem, AgentTextDelta
    from engine.models.messages import AgentMessage

    # HALO's current CLI wrapper sets compaction temperature to 0.0, which is not
    # accepted by GPT-5-class models. Use the Python API so the compactor uses the
    # model default-compatible temperature while preserving the requested model.
    agent = HaloAgentConfig(
        name="root",
        model=ModelConfig(name=HALO_MODEL),
        maximum_turns=20,
    )
    config = EngineConfig(
        root_agent=agent,
        subagent=agent.model_copy(update={"name": "sub"}),
        synthesis_model=ModelConfig(name=HALO_MODEL),
        compaction_model=ModelConfig(name=HALO_MODEL, temperature=1.0),
        maximum_depth=1,
        maximum_parallel_subagents=2,
    )

    # The notebook already exports the SDK traces locally; HALO does not need
    # hosted trace ingestion for this diagnosis pass.
    set_trace_processors([])

    deltas: list[str] = []
    final_items: list[str] = []
    messages = [AgentMessage(role="user", content=render_halo_prompt())]

    # This pass only needs HALO's trace-analysis tools. Skip the optional
    # `run_code` sandbox so readers do not need a separate Deno/Pyodide setup
    # just to generate the optimization report.
    async def report_progress(done: asyncio.Event, interval_seconds: int = 30) -> None:
        started = time.perf_counter()
        print("HALO optimization started. This is usually the longest cell in the notebook.")
        while not done.is_set():
            try:
                await asyncio.wait_for(done.wait(), timeout=interval_seconds)
            except TimeoutError:
                print(f"HALO still running... {format_duration(time.perf_counter() - started)} elapsed")

    original_sandbox_get = Sandbox.__dict__["get"]
    Sandbox.get = classmethod(lambda cls: None)
    halo_started = time.perf_counter()
    progress_done = asyncio.Event()
    progress_task = asyncio.create_task(report_progress(progress_done))
    try:
        async for event in stream_engine_async(messages, config, context_path):
            if isinstance(event, AgentTextDelta):
                deltas.append(event.text_delta)
            elif isinstance(event, AgentOutputItem) and event.final:
                final_items.append(str(event.item))
    finally:
        progress_done.set()
        await progress_task
        Sandbox.get = original_sandbox_get

    print(f"HALO optimization completed in {format_duration(time.perf_counter() - halo_started)}")
    report = "".join(deltas).strip() or "\n\n".join(final_items).strip()
    if not report:
        raise RuntimeError("HALO completed without producing a report.")
    return report


def clean_halo_handoff(report: str) -> str:
    """Keep only the final Codex-facing handoff sections from HALO output."""
    normalized = re.sub(r"(?<!\n)(## Executive summary)", r"\n\n\1", report).strip()
    start = normalized.rfind("## Executive summary")
    if start == -1:
        raise ValueError("HALO output did not include the expected executive summary section.")

    handoff = normalized[start:].strip()
    required_headings = [
        "## Executive summary",
        "## Top 3 changes to implement first",
        "## Ranked recommendation table",
        "## Supporting diagnosis and evidence",
        "## Detailed recommendations",
        "## Insights by feedback source",
        "## Machine-readable summary",
    ]
    missing = [heading for heading in required_headings if heading not in handoff]
    if missing:
        raise ValueError(f"HALO handoff is missing required sections: {missing}")
    return handoff


def write_halo_handoff(report: str, path: str | Path) -> Path:
    target = Path(path)
    if not target.is_absolute():
        target = PROJECT_ROOT / target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report.rstrip() + "\n", encoding="utf-8")
    return target


halo_context = build_halo_context(traces, human_feedback, llm_feedback, eval_suite, gate_result, agent_config)
display(Markdown(halo_input_summary(halo_context)))
halo_context_path = write_halo_optimization_context(halo_context)
halo_report = await run_halo_optimization(halo_context_path)
clean_handoff = clean_halo_handoff(halo_report)

handoff_path = write_halo_handoff(clean_handoff, ARTIFACT_DIR / "codex_handoff.md")

def extract_named_section(report: str, heading: str) -> str:
    if heading not in report:
        return ""
    start = report.index(heading)
    remainder = report[start + len(heading):]
    next_section = re.search(r"\n## ", remainder)
    return report[start:] if next_section is None else report[start:start + len(heading) + next_section.start()]


def render_notebook_halo_summary(report: str) -> str:
    sections = [
        extract_named_section(report, "## Top 3 changes to implement first"),
        extract_named_section(report, "## Insights by feedback source"),
    ]
    rendered = "\n\n".join(section.strip() for section in sections if section.strip())
    return rendered or report


print("Gate result passed into optimization context:", "gate_result" in halo_context)
print("Wrote:")
print("-", halo_context_path.relative_to(PROJECT_ROOT))
print("-", handoff_path.relative_to(PROJECT_ROOT))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text
    HALO optimization started. This is usually the longest cell in the notebook.
    HALO still running... 30s elapsed
    HALO still running... 1m 00s elapsed
    HALO still running... 1m 30s elapsed
    HALO still running... 2m 00s elapsed
    HALO still running... 2m 30s elapsed
    HALO still running... 3m 00s elapsed
    HALO still running... 3m 30s elapsed
    HALO still running... 4m 00s elapsed
    HALO still running... 4m 30s elapsed
    HALO still running... 5m 00s elapsed
    HALO still running... 5m 30s elapsed
    HALO still running... 6m 00s elapsed
    HALO still running... 6m 30s elapsed
    HALO still running... 7m 00s elapsed
    HALO optimization completed in 7m 15s
    Gate result passed into optimization context: True
    Wrote:
    - examples/agents_sdk/agent_improvement_loop_artifacts/halo_optimization_context.jsonl
    - examples/agents_sdk/agent_improvement_loop_artifacts/codex_handoff.md
    ```

## Step 8. 把完整報告交給 Codex

HALO 負責診斷和排優先順序，改 harness 的還是 coding agent 或人。

下面是 Codex 可以採取行動的完整報告快照：前三項建議，加上每個回饋來源貢獻內容的精簡摘要。完整的 `codex_handoff.md` 還包含排序後的修改、支持的證據，以及實作時的驗證指引。


```python
handoff_file = ARTIFACT_DIR / "codex_handoff.md"

if handoff_file.exists():
    print(f"Full Codex handoff written to: {handoff_file.relative_to(PROJECT_ROOT)}")
    print("Snapshot below; open the generated codex_handoff.md file to review the full handoff.")
    display(Markdown(render_notebook_halo_summary(handoff_file.read_text(encoding="utf-8"))))
else:
    print(f"Codex handoff not found yet: {handoff_file.relative_to(PROJECT_ROOT)}")
    print("Run the HALO optimization cell above to generate it.")
```

??? note "輸出"

    ```text
    Full Codex handoff written to: examples/agents_sdk/agent_improvement_loop_artifacts/codex_handoff.md
    Snapshot below; open the generated codex_handoff.md file to review the full handoff.
    ```

    ```text
    <IPython.core.display.Markdown object>
    ```

## Step 9. 把迴圈接起來

現在整個工作流程都到位了，可以回頭從 notebook 開頭的最佳化飛輪看起。同一套架構支援兩種運作模式。

![Agent improvement loop flywheel](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent-improvement-loop-flywheel.svg)

![Human review gates in the loop](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agent-improvement-loop-human-gates.svg)

它可以跑成封閉迴圈：新的 traces、人工與模型回饋、產生的 Promptfoo evals、HALO 診斷、Codex 實作、驗證和部署，全部餵進下一個循環。這個模式下，handoff 檔可以寫到共用儲存空間，帶 heartbeat 的 Codex 自動化可以持續檢查有沒有新的 handoff，出現時醒來，並自動觸發下一輪實作。

開發者也可以在想要的地方加入人工關卡，包括 trace 審閱、eval 調整、pull request 核准、合併和部署。

設計上的取捨是，人在給完回饋之後還要參與多少。人的判斷可以引導一個由 agent 執行的迴圈，也可以讓人從頭到尾當核准關卡。兩種做法中，人工回饋都是核心，因為它決定了系統學到什麼、下一步改什麼。


## 結論

Agent 改進迴圈提供一條持續改進的路，而不是把問題簡化成只調 prompt。整個迴圈都重要：traces 捕捉行為、人工回饋加入判斷、evals 保存系統該做的事、HALO 把證據變成排序過的 harness 修改，Codex 則可以實作下一輪。

這個領域還在演進，個別元件之後很可能會改變。比較持久的是 loop engineering 這個更大的概念：當回饋、測試和實作連在同一個迴圈裡，agent 就能從真實行為中持續改進。


## 下一步

- 編輯 notebook 開頭附近的 `AGENT_MODEL`、`ANALYSIS_MODEL`、`EVAL_GENERATION_MODEL`、`JUDGE_MODEL` 和 `HALO_MODEL`，為迴圈的每個階段選模型。
- 建立你自己的 traces 來測試這個 agent。
- 決定最後的路徑要保留多少人工審閱、多少自動化：可以停在開發者審閱過的 PR，也可以把 handoff 接到會自動開 PR、合併和部署的系統。
- 把 `ARTIFACT_DIR` 底下產生的 `codex_handoff.md` 交給 Codex，檢查它提出的 harness 修改，再用更新後的 harness 重跑同一套 eval。


## 重點整理
- Harness 是模型周圍的整套約定（instructions、tools、routing、輸出要求、驗證檢查），改進的對象是整個 harness，不只是 prompt。
- Traces 記錄發生了什麼，回饋說明什麼重要，evals 把期望固定下來，三者缺一不可。
- 自動產生的 evals 要由領域專家和開發者檢查過，才適合進入長期測試套件。
- HALO 同時看 traces、回饋和 eval 結果，產出排序過的修改和 Codex 能直接用的 handoff。
- 自動化程度是設計選擇，可以每一步都有人審閱，也可以交給封閉迴圈自己跑。

## 練習
1. 把 `ANALYSIS_MODEL` 和 `JUDGE_MODEL` 換成比較便宜的模型重跑，比較 Promptfoo 關卡的通過率有沒有變化。
2. 在 Step 3 的問題清單中加一題你自己設計的盡職調查問題（例如針對客戶流失），跑完後看 trace 和成果檔是否符合要求。
3. 在 Step 4 的人工回饋裡新增一條你認為重要的規則，重跑 Step 5 到 Step 7，檢查新的 eval 是否出現在 `codex_handoff.md` 的建議裡。
