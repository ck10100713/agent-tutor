---
translated: true
source: examples/agents_sdk/building_reliable_agents_memory_compaction.ipynb
---
# 用 Memory 和 Compaction 打造可靠的 Agent

> 原文：[examples/agents_sdk/building_reliable_agents_memory_compaction.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/building_reliable_agents_memory_compaction.ipynb)

這份 cookbook 用 Agents SDK 的 compaction 和 memory，做一個證據審查 agent。

## 這篇在做什麼

用 OpenAI Agents SDK 做一個合規調查用的證據審查 agent，資料是合成的。先從最簡單的 sandbox agent 開始，再加上 compaction 和 memory 兩個可靠性機制，最後產出一份可供人工審閱的 memo。

## 學完你會

- 用 `Manifest` 建立 sandbox 工作區，並用 `SandboxAgent` 搭配 `Filesystem()` 和 `Shell()` 讓 agent 讀檔、寫 memo
- 用 `Compaction()`、`StaticCompactionPolicy` 或強制 checkpoint 讓長時間的對話不被 context window 撐爆
- 用 `Memory()` 只存「工作流程的經驗」，並判斷什麼該進 memory、什麼該留在 memo

## 開跑前

- Python 3.10 以上，安裝 `openai-agents`
- 環境變數 `OPENAI_API_KEY`
- 本機要是 Unix-like 環境（`UnixLocalSandboxClient` 需要）
- `RUN_AGENT` 預設是 `False`，不會呼叫模型；要真的跑才設 `RUN_AGENT = True`

這份 Cookbook 示範怎麼用 OpenAI Agents SDK，為一個合成的合規調查建立證據審查 agent。

你會先從簡單的 sandbox agent 開始，再加上兩個可靠性機制：

- **Compaction**：在 context window 有限的前提下支援長時間對話，把後續回合需要的狀態帶下去，同時縮小 context。
- **Memory**：讓之後的 sandbox agent 執行可以重用先前的工作流程經驗，不用把每一輪舊對話重播一遍。

這個可靠性模式很直接：compaction 讓當前這次執行能繼續，memory 讓後面的執行一開始就有有用的流程指引，而產出的 memo 仍是由人審閱、作為調查依據的唯一來源。

參考資料：

- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [Agents SDK sessions](https://openai.github.io/openai-agents-python/sessions/)
- [Agents SDK sandboxing](https://openai.github.io/openai-agents-python/ref/sandbox/)

## 使用情境：合規調查的證據審查 Agent

合規團隊在調查某個廠商例外是否符合內部政策。證據是一小批檔案：政策條文、例外說明、稽核觀察、核准紀錄和改善計畫。

這個 agent 的工作不是變成調查紀錄本身，而是幫審查人員走過這些證據、追蹤哪裡有變動，並寫出一份簡潔的 memo，把有證據支持的發現和未解問題分開。

這個例子很適合講 memory 和 compaction，因為這類調查有三個真實工作中常見的特徵：

- **紀錄會隨時間變動。** 後來的文件可能縮小或取代先前的假設。
- **對話可能變得很長。** 審查人員可能追問、要求修改，之後再回來接著做。
- **最終產出需要來源依據。** memo 要引用證據、保留不確定性，不能把審查壓扁成一個信心滿滿但沒有依據的結論。

## 這個模式適用在哪

雖然這份 notebook 用合規審查當例子，但只要是知識工作者在審視不斷變化的資訊、並產出可供人稽核的成果，同樣的模式都適用。

適合的情境包括：

- 客服團隊把新的政策更新套用到進行中的升級案件。
- 資安團隊審查事件證據並撰寫事件摘要。
- 財務團隊對照政策、核准和稽核紀錄來核對例外。
- 產品團隊在新產品或新模型發布後更新競品定位。
- 法務或採購團隊審閱合約、email 和核准歷程。
- 併購團隊吸收新的業務規則、作業程序和盡職調查筆記。

每個情境裡，compaction 讓進行中的審查在 context 變大時還能繼續，memory 把可重用的流程經驗帶下去，最終產出仍是經過審閱的成果。

## 你會做出什麼

情境是合規證據審查。團隊會陸續收到政策文件、例外說明、稽核發現、核准紀錄和改善計畫。agent 協助審查證據、保留不確定性，並產出附引用的簡潔 memo。

你會建立：

1. 一個合成的證據工作區，有資料夾結構、manifest 和輸出目錄。
2. 一個簡單的 `SandboxAgent`，能檢視檔案並寫 memo。
3. 給長時間工作用的 compaction checkpoint。
4. 用 SDK memory 產生可重用的流程經驗。
5. 一次把 sandbox 工具、compaction、memory 和產出檔案全部串起來的執行。

`RUN_AGENT` 預設為 `False`，所以不用呼叫模型也能看這份 notebook。只有想執行真正的 sandbox 流程時才設成 `True`。

### 目錄

- [Use Case](#use-case-evidence-review-agent-for-a-compliance-investigation)
- [Where This Pattern Applies](#where-this-pattern-applies)
- [Prerequisites](#prerequisites)
- [Setup](#setup)
- [Using Agents SDK in This Notebook](#using-agents-sdk-in-this-notebook)
- [Memory vs. Compaction](#memory-vs-compaction)
- [Folder Structure and Manifest](#folder-structure-and-manifest)
- [Prepare a Small Evidence Workspace](#prepare-a-small-evidence-workspace)
- [Step 1: Start With a Simple Agent Configuration](#step-1-start-with-a-simple-agent-configuration)
- [Step 2: Add Compaction](#step-2-add-compaction)
- [Step 3: Attach Memory](#step-3-attach-memory)
- [Step 4: Run With Both Compaction and Memory](#step-4-run-with-both-compaction-and-memory)
- [Inspect Generated Artifacts](#inspect-generated-artifacts)

## 前置需求

要跑真正的 agent 流程，你需要：

- Python 3.10 以上。
- `openai-agents` 套件。
- 環境變數 `OPENAI_API_KEY` 裡有 OpenAI API key。
- 本機是 Unix-like 環境，給 `UnixLocalSandboxClient` 用。這份 notebook 用 sandbox `Manifest` 建立的合成檔案，所以不需要外部資料集。

沒有憑證也可以安全地看這份 notebook，因為 `RUN_AGENT` 預設是 `False`。只有想執行由模型驅動的 sandbox 流程時才設成 `True`。


```python
# Install or upgrade the OpenAI Agents SDK.
%pip install --upgrade openai-agents
```

## 設定

這份 notebook 把所有合成檔案寫在 `examples/agents_sdk/.tmp/evidence_review_memory_compaction/` 底下，不需要外部資料。

預設會關掉 tracing，因為有些組織使用 Zero Data Retention (ZDR)，trace 上傳可能被擋。如果是合成資料或非 ZDR 環境，開發時可以設 `ENABLE_TRACING = True` 來看 trace。

```python
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

RUN_AGENT = False
MODEL = "gpt-5.5"
COMPACTION_MODEL = "gpt-5.4-mini"
WORKFLOW_NAME = "evidence-review-memory-compaction"
FORCE_COMPACTION_CHECKPOINT = True
DISABLE_TRACING = True

if DISABLE_TRACING:
    os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "true"
else:
    os.environ.pop("OPENAI_AGENTS_DISABLE_TRACING", None)

if RUN_AGENT and not os.environ.get("OPENAI_API_KEY"):
    raise RuntimeError("Set OPENAI_API_KEY before running the live sandbox workflow.")

print({
    "run_agent": RUN_AGENT,
    "model": MODEL,
    "compaction_model": COMPACTION_MODEL,
    "force_compaction_checkpoint": FORCE_COMPACTION_CHECKPOINT,
    "tracing_disabled": DISABLE_TRACING,
})
```

## 在這份 Notebook 裡使用 Agents SDK

**sandbox agent** 是在受控工作區裡執行的 Agents SDK agent。這份 notebook 的工作區包含合成證據檔、`manifest.csv`、輸出資料夾，以及 SDK 產生的 memory 檔。

sandbox 給 agent 一個有邊界的地方檢視檔案、寫產出。應用程式不用把每份文件貼進 prompt，而是建立工作區，讓 agent 用這些 capability：

- `Filesystem()`：讀寫工作區檔案。
- `Shell()`：列出檔案、檢視文件、跨批次搜尋。
- `Compaction()`：在 context 變大時支援長時間審查。
- `Memory()`：儲存可重用的流程經驗，給未來的 sandbox agent 執行用。

memo 仍是由人審閱的成果。工具幫 agent 做事，compaction 讓它能繼續，memory 讓未來的執行更好，產出檔案則存放可供審閱的結果。

## Memory 和 Compaction 的差別

分辨這兩個概念的好方法，是問它們各自「可以往後帶什麼」。

| 問題 | Compaction | Memory |
|---|---|---|
| 它幫什麼忙？ | 在 context 變大時，讓單次長時間執行繼續下去。 | 用可重用的流程經驗改善未來的執行。 |
| 它摘要什麼？ | 當前的對話和工作狀態。 | 值得重用的模式、偏好和流程經驗。 |
| 該存調查結論嗎？ | 不該。可以保留工作狀態，但 memo 才是審閱過的成果。 | 不該。存流程經驗，不存個案事實。 |
| 什麼時候有用？ | 審查中途，尤其是在後面的批次或追問之前。 | 在重複審查類似證據流程時跨次使用。 |

這份 notebook 裡，合規 memo 是調查成果的依據。memory 刻意只限定在審查人員的偏好和工作習慣，例如先看 manifest、保留不確定性、讓被取代的假設仍然看得到。

## 資料夾結構與 Manifest

agent 在一個小型檔案工作區裡工作。資料夾結構刻意做得簡單：證據檔按批次分組，產出放在 `outputs/`，manifest 則給 agent 一份精簡的文件地圖。

### Manifest 功能

在 Agents SDK 裡，`Manifest` 是 sandbox agent 全新 session 的工作區契約。它描述新 sandbox session 啟動時應該存在的檔案、目錄、mount、環境變數、使用者、群組和相關工作區設定。

本機 SDK 實作定義了這些核心欄位：

| Manifest 欄位 | 控制什麼 | 在這份 Cookbook 怎麼用 |
|---|---|---|
| `root` | 工作區根路徑，預設 `/workspace`。 | 除非 sandbox provider 要求不同的根目錄，否則維持預設。 |
| `entries` | 要實體化的檔案、目錄、本機檔案、本機目錄、repo 或 mount。 | 把 `README.md`、`manifest.csv`、輸入文件和 `outputs/` 放這裡。 |
| `environment` | sandbox 啟動時可用的環境變數。 | 只放非機密的 runtime 設定。憑證不要放進 prompt 或 commit 進 notebook。 |
| `users` / `groups` | sandbox 內部的 OS 帳號與群組，限支援的 provider。 | Cookbook 通常用不到，production 做隔離時有用。 |
| `extra_path_grants` | 額外的路徑授權，特別適合 Unix-local 流程。 | sandbox 需要對 host 路徑有限定範圍的讀寫權限時，少量使用。 |
| `remote_mount_command_allowlist` | 允許對遠端 mount 執行的指令。 | 掛載外部儲存或資料室時，範圍要窄。 |

Manifest entry 的路徑要用相對於工作區的路徑。避免絕對路徑和 `..` 跳脫，這樣同一個 agent 才能在 Unix-local、Docker 和託管 sandbox provider 之間搬移。


### 資料夾與 Manifest 最佳實務

- 把來源文件、manifest、輔助檔和輸出目錄放進 `Manifest`，不要把大量內容貼進 prompt。
- 較長的任務說明放在工作區檔案裡，例如 `README.md`、`task.md` 或 `AGENTS.md`；agent 的 instructions 只講行為和界線。
- 用穩定的文件 ID 和機器可讀的 manifest 檔，讓產出的 memo 能引用來源，審查人員也能順著路徑回到證據。
- 讓 `Memory()` 自己管理 memory 檔案。預設情況下，sandbox memory 使用工作區底下的 `memories/` 和 `sessions/`。
- 產出檔放在 `outputs/`，這樣應用程式在執行後可以檢查、複製、驗證或封存。
- mount 的範圍要窄。如果掛載資料室，只掛 agent 該讀或該寫的部分。
- 機密當成由應用程式或 sandbox provider 注入的 runtime 設定，不要放在 prompt 文字或 commit 的 manifest 內容裡。
- 教學用先拿小型合成的 `File(...)` 或 `Dir(...)` entry，production 規模的資料集再換成 `LocalDir`、`GitRepo` 或儲存空間 mount。


```python
# This is a visual preview of the sandbox workspace structure.
# The next cell builds the actual Manifest entries manually.
WORKSPACE_TREE = """
/workspace/
  README.md
  manifest.csv
  docs/
    batch_1/
    batch_2/
    batch_3/
  outputs/
  memories/    # Generated by Memory()
  sessions/    # Generated by Memory()
""".strip()

print(WORKSPACE_TREE)
```

## 準備一個小型證據工作區

`Manifest` 描述全新 sandbox 工作區的起始檔案。這份教學的工作區包含：

- 一份 `manifest.csv`，按批次和文件 ID 列出文件，
- 三個小型文件批次，
- 一個放審查 memo 的輸出目錄。

之後唯一會掛上的 memory 機制是 SDK 的 `Memory()` capability。調查發現留在產生的審查 memo 裡，在那裡才能被引用和檢查。


```python
from agents.sandbox import Manifest
from agents.sandbox.entries import Dir, File


def workspace_file(text: str) -> File:
    return File(content=textwrap.dedent(text).strip().encode("utf-8") + b"\n")


def build_evidence_manifest() -> Manifest:
    return Manifest(
        entries={
            "README.md": workspace_file(
                """
                # Evidence Review Workspace

                Review the documents in batch order. Cite document IDs from
                `manifest.csv` when making findings. Write the final memo to
                `outputs/compliance_review_memo.md`.
                """
            ),
            "manifest.csv": workspace_file(
                """
                doc_id,batch,path,description
                ACME-B1-001,1,docs/batch_1/payment_policy.txt,Baseline payment policy
                ACME-B1-002,1,docs/batch_1/vendor_exception.txt,Vendor exception note
                ACME-B2-001,2,docs/batch_2/audit_followup.txt,Audit follow-up request
                ACME-B2-002,2,docs/batch_2/approval_thread.txt,Approval clarification
                ACME-B3-001,3,docs/batch_3/remediation_plan.txt,Remediation plan
                """
            ),
            "docs/batch_1/payment_policy.txt": workspace_file(
                """
                doc_id: ACME-B1-001
                ACME requires two approvals for payments over $50,000. Exceptions must
                be logged with Finance Ops and reviewed within five business days.
                """
            ),
            "docs/batch_1/vendor_exception.txt": workspace_file(
                """
                doc_id: ACME-B1-002
                A vendor onboarding exception was approved verbally for Northwind
                Logistics because the renewal was time-sensitive. The note does not show
                a Finance Ops log entry.
                """
            ),
            "docs/batch_2/audit_followup.txt": workspace_file(
                """
                doc_id: ACME-B2-001
                Internal Audit asked Finance Ops to confirm whether Northwind Logistics
                received post-approval review. The request says missing exception logs
                should be treated as a control gap until resolved.
                """
            ),
            "docs/batch_2/approval_thread.txt": workspace_file(
                """
                doc_id: ACME-B2-002
                The approval thread says Legal approved the vendor exception, but Finance
                Ops approval was still pending when the payment was released.
                """
            ),
            "docs/batch_3/remediation_plan.txt": workspace_file(
                """
                doc_id: ACME-B3-001
                The remediation plan requires Finance Ops to reconcile all verbal vendor
                exceptions from Q4 and add retrospective control attestations.
                """
            ),
            "outputs": Dir(),
        }
    )


manifest = build_evidence_manifest()
print(f"Workspace entries: {len(manifest.entries)}")
```

## Step 1：從簡單的 Agent 設定開始

先建立一個沒有 memory、沒有 compaction 的 agent，在加其他機制前把基準行為弄清楚。

有個細節要注意：`SandboxAgent` 的預設值可能包含內建 capability。為了讓這個基準明確，直接傳入你要的完整 capability 清單。這裡只放 agent 檢視檔案和寫產出所需的工作區工具：`Filesystem()` 和 `Shell()`。我們刻意**不**掛 `Compaction()` 或 `Memory()`。

- `Filesystem()` 讓 sandbox agent 能存取檔案型的工作區，讀取已放好的證據並寫出 memo。在 [Sandbox Agents guide](https://developers.openai.com/api/docs/guides/agents/sandboxes#give-the-agent-capabilities) 裡，capability 是把 sandbox 原生的行為和工具掛到 `SandboxAgent` 的方式
- `Shell()` 讓 agent 用終端機指令檢視工作區，例如列出檔案、打開證據文件、跨批次搜尋關鍵字。Sandbox Agents guide 提到 `Shell()` 是預設 capability 之一，[Shell tool guide](https://developers.openai.com/api/docs/guides/tools-shell) 則說明 shell 讓模型有一個終端環境，可以託管或本機執行。
- 這個基準版本用這兩個就夠了：`Filesystem()` 負責工作區讀寫，`Shell()` 負責可預期的檢視和搜尋。等基準流程弄清楚之後，才加 memory 和 compaction。


```python
from agents.sandbox import SandboxAgent
from agents.sandbox.capabilities import Filesystem, Shell

BASELINE_INSTRUCTIONS = """
You are an evidence review agent for a compliance investigation.

Review documents in batch order. Keep these boundaries clear:
- Cite document IDs from `manifest.csv` for each finding.
- If evidence is incomplete, record an open question instead of guessing.
- Write a concise reviewer memo to `outputs/compliance_review_memo.md`.
- Use the generated memo as the reviewer-facing investigation artifact.
""".strip()


def build_baseline_agent() -> SandboxAgent:
    return SandboxAgent(
        name="Evidence Review Agent",
        model=MODEL,
        instructions=BASELINE_INSTRUCTIONS,
        default_manifest=build_evidence_manifest(),
        capabilities=[
            Filesystem(),
            Shell(),
        ],
    )


baseline_agent = build_baseline_agent()
print([type(capability).__name__ for capability in baseline_agent.capabilities])
```

```python
from agents import Runner
from agents.run import RunConfig
from agents.sandbox import SandboxRunConfig
from agents.sandbox.sandboxes.unix_local import UnixLocalSandboxClient

BASELINE_TASK = """
Review Batch 1 only, then draft `outputs/compliance_review_memo.md` for a
compliance reviewer. Include cited findings and open questions.
""".strip()


async def _read_text_file(session, path: str) -> str | None:
    try:
        handle = await session.read(Path(path))
    except Exception as exc:
        if "NotFound" not in type(exc).__name__:
            raise
        return None
    try:
        return handle.read().decode("utf-8", errors="replace")
    finally:
        handle.close()


async def _list_workspace_files(session) -> str:
    result = await session.exec(
        "find outputs memories sessions -maxdepth 4 -type f 2>/dev/null | sort || true",
        timeout=30,
    )
    return result.stdout.decode("utf-8", errors="replace").strip()


async def _read_memory_artifacts(session) -> dict[str, str]:
    memory_artifacts = {}
    for path in ["memories/MEMORY.md", "memories/memory_summary.md"]:
        text = await _read_text_file(session, path)
        if text:
            memory_artifacts[path] = text
    return memory_artifacts


async def run_in_unix_sandbox(agent: SandboxAgent, task: str, *, sdk_session=None) -> dict[str, object]:
    client = UnixLocalSandboxClient()
    session = await client.create(manifest=agent.default_manifest)
    try:
        await session.start()
        result = await Runner.run(
            agent,
            task,
            max_turns=12,
            run_config=RunConfig(
                sandbox=SandboxRunConfig(session=session),
                workflow_name=WORKFLOW_NAME,
                tracing_disabled=DISABLE_TRACING,
            ),
            session=sdk_session,
        )

        compaction_checkpoint = None
        if sdk_session is not None and FORCE_COMPACTION_CHECKPOINT:
            compaction_checkpoint = await force_compaction_checkpoint(sdk_session)

        # Memory generation runs as a sandbox pre-stop hook. Flush it before reading artifacts
        # so `memories/MEMORY.md` and `memories/memory_summary.md` are available here.
        await session.run_pre_stop_hooks()

        memo = await _read_text_file(session, "outputs/compliance_review_memo.md")
        files = await _list_workspace_files(session)
        memory_artifacts = await _read_memory_artifacts(session)

        return {
            "result": result,
            "final_output": str(result.final_output),
            "memo": memo,
            "workspace_files": files,
            "memory_artifacts": memory_artifacts,
            "compaction_checkpoint": compaction_checkpoint,
        }
    finally:
        await session.aclose()


if RUN_AGENT:
    baseline_run = await run_in_unix_sandbox(baseline_agent, BASELINE_TASK)
    print(baseline_run["final_output"])
    print("\n----- END AGENT OUTPUT -----")
else:
    print("RUN_AGENT is False. Baseline agent is configured but not executed.")
```

## Step 2：加上 Compaction

Compaction 是給長時間工作用的。對話變長時，compaction 縮小 context，同時保留後續回合需要的狀態。有三種好用的思考方式：

1. **用 `Compaction()` 自動 compaction**：掛上 capability，context 有壓力時讓 SDK 自己壓縮。
2. **用 `StaticCompactionPolicy` 做門檻式 compaction**：明確設定門檻，適合想要更可預期的 context 大小行為的環境。
3. **用 `OpenAIResponsesCompactionSession.run_compaction({"force": True})` 強制 checkpoint compaction**：在應用程式定義的階段邊界壓縮，例如一個主要審查階段結束後、下一批證據開始前。

這份 notebook 用強制 checkpoint，因為合成資料集刻意做得很小。在 production，自動 compaction 通常是最簡單的起點，想要更嚴格的營運策略時，門檻式 compaction 就很有用。

> **最佳實務**
>
> - 在有意義的工作流程邊界做 compaction，不要每一回合都做。
> - 保留足夠的工作狀態，讓下一階段講得通。
> - 被引用的事實要放在產出檔裡，不要只留在壓縮後的對話狀態。

```python
from agents.sandbox.capabilities import Compaction, StaticCompactionPolicy


def build_compaction_agent(*, demo_threshold: int | None = None) -> SandboxAgent:
    if demo_threshold is None:
        compaction = Compaction()
    else:
        compaction = Compaction(policy=StaticCompactionPolicy(threshold=demo_threshold))

    return SandboxAgent(
        name="Evidence Review Agent with Compaction",
        model=MODEL,
        instructions=(
            BASELINE_INSTRUCTIONS
            + "\n\nWhen context is compacted, preserve the current batch, cited facts, open "
            "questions, artifact paths, and unresolved reviewer concerns."
        ),
        default_manifest=build_evidence_manifest(),
        capabilities=[
            Filesystem(),
            Shell(),
            compaction,
        ],
    )


compaction_agent = build_compaction_agent()
threshold_compaction_agent = build_compaction_agent(demo_threshold=8_000)
print({
    "automatic": [type(capability).__name__ for capability in compaction_agent.capabilities],
    "threshold_policy": [type(capability).__name__ for capability in threshold_compaction_agent.capabilities],
})
```

### Compaction 怎麼被觸發

有 `Compaction()` capability 時，當前 context 夠大就會有資格觸發 server-side compaction。這是目前的預設行為：掛上 capability，讓 SDK 管理 context 壓力。

小型教學裡自動 compaction 很難看到，因為執行可能根本沒接近模型的 context 上限。調低 `StaticCompactionPolicy` 有幫助，但仍然取決於實際渲染出來的 context 有沒有超過門檻。

證據量少的時候，強制 checkpoint 是最清楚的操作模式。`OpenAIResponsesCompactionSession` 這個包裝會儲存 session 歷史，讓應用程式在階段邊界呼叫 `run_compaction({"force": True})`。這樣不用灌大證據量，就能看到 compaction 發生。


```python
from agents.memory import OpenAIResponsesCompactionSession, SQLiteSession


def build_compaction_session() -> OpenAIResponsesCompactionSession:
    underlying = SQLiteSession("evidence_review_session.sqlite")
    return OpenAIResponsesCompactionSession(
        session_id="evidence-review-demo",
        underlying_session=underlying,
        model=COMPACTION_MODEL,
        compaction_mode="input",
    )


async def force_compaction_checkpoint(session: OpenAIResponsesCompactionSession) -> dict[str, int]:
    items_before = await session.get_items()
    await session.run_compaction({"force": True, "compaction_mode": "input"})
    items_after = await session.get_items()
    return {"items_before": len(items_before), "items_after": len(items_after)}


print("Compaction session helper defined. The final run uses it to show an explicit phase checkpoint.")
```

## Step 3：掛上 Memory

Memory 是給跨次執行重用的。這個範例裡，memory 要記的是**流程經驗**，不是調查事實。

適合進 memory 的例子：

- 審查檔案型證據工作區時，先看 manifest。
- 在 memo 裡保留不確定性，不要用猜的。
- 後來的證據縮小了早先的假設時，讓早先的假設仍然看得到。

不適合進 memory 的例子：

- "Northwind Logistics violated policy."
- "ACME's Finance Ops process is deficient."
- 任何屬於 memo 的個案結論。

> **最佳實務**
>
> - memory 用來存穩定的流程經驗和使用者偏好。
> - 個案事實放在經審閱的產出，例如 memo。
> - 在之後的執行依賴生成的 memory 之前，先檢查它。

```python
from agents.sandbox import MemoryGenerateConfig
from agents.sandbox.capabilities import Memory

MEMORY_GENERATION_PROMPT = """
Store reusable workflow lessons only.
Do not store ACME-specific compliance findings, document facts, evidence citations,
or memo conclusions. Those belong in outputs/compliance_review_memo.md.
Memory should help future evidence-review workflows behave better; it should not
become a second investigation record.
""".strip()


def workflow_memory() -> Memory:
    return Memory(
        generate=MemoryGenerateConfig(
            extra_prompt=MEMORY_GENERATION_PROMPT,
        )
    )


def build_memory_agent() -> SandboxAgent:
    return SandboxAgent(
        name="Evidence Review Agent with Memory",
        model=MODEL,
        instructions=BASELINE_INSTRUCTIONS,
        default_manifest=build_evidence_manifest(),
        capabilities=[
            Filesystem(),
            Shell(),
            workflow_memory(),
        ],
    )


memory_agent = build_memory_agent()
print([type(capability).__name__ for capability in memory_agent.capabilities])
```

## Step 4：同時用 Compaction 和 Memory 執行

現在把各部分組起來：

- `Filesystem()` 和 `Shell()` 讓 agent 在證據工作區裡移動。
- `Compaction()` 在 context 變大時讓進行中的審查能繼續。
- `Memory()` 在執行後記下可重用的流程經驗。
- 最終的 memo 仍是調查成果。

下面的任務要求 agent 審查合成證據、寫 memo，再把 memo 讀回來，確認它保留了要求的結構和不確定性。

```python
FINAL_REVIEW_TASK = """
Review all three document batches in order.

For each batch:
1. Read the manifest and relevant documents.
2. Preserve cited findings and uncertainty in your working notes and final memo.
3. Preserve any superseded or narrowed assumption instead of silently deleting it.

After Batch 3, write `outputs/compliance_review_memo.md` with:
- executive summary,
- cited findings table,
- open questions,
- recommended next steps for the reviewer.

Reviewer preference for future runs: keep the memo concise, preserve uncertainty
instead of guessing, and separate reusable workflow lessons from document-specific
compliance findings.
""".strip()


def build_reliable_evidence_agent() -> SandboxAgent:
    return SandboxAgent(
        name="Reliable Evidence Review Agent",
        model=MODEL,
        instructions=(
            BASELINE_INSTRUCTIONS
            + "\n\nUse compaction as working context. Use SDK memory for reusable "
            "workflow lessons across runs. Do not treat memory as the system of record "
            "for ACME-specific findings; those belong in the cited memo artifact."
        ),
        default_manifest=build_evidence_manifest(),
        capabilities=[
            Filesystem(),
            Shell(),
            Compaction(),
            workflow_memory(),
        ],
    )


reliable_agent = build_reliable_evidence_agent()
print([type(capability).__name__ for capability in reliable_agent.capabilities])
```

```python
EXAMPLE_OUTPUT = """
# Compliance Review Memo

## Executive Summary

The current record supports a control-gap finding for the Northwind Logistics
vendor exception, not a final conclusion that policy was intentionally violated.
The strongest evidence is that ACME required two approvals and Finance Ops
logging for payment exceptions, while the Northwind exception appears to have
been released before Finance Ops approval was complete.

Later evidence narrows the initial concern. The record no longer points only to
an undocumented verbal exception; it now points to a specific process weakness:
Legal approval may have been obtained, but Finance Ops review and exception-log
reconciliation remained incomplete at the time of release.

## Cited Findings

| Finding | Support | Status |
|---|---|---|
| Payments over $50,000 required two approvals, and exceptions had to be logged with Finance Ops. | ACME-B1-001 | Supported |
| The Northwind Logistics exception was approved verbally, but the initial note does not show a Finance Ops log entry. | ACME-B1-002 | Supported |
| Internal Audit treated missing exception logs as a control gap until resolved. | ACME-B2-001 | Supported |
| The approval thread indicates Legal approved the exception, but Finance Ops approval was still pending when payment was released. | ACME-B2-002 | Supported |
| The remediation plan requires Finance Ops to reconcile verbal vendor exceptions from Q4 and add retrospective control attestations. | ACME-B3-001 | Supported |

## Open Questions

- Was Finance Ops approval completed after the payment release, and if so, when?
- How many other Q4 verbal vendor exceptions lack retrospective attestations?
- Did any compensating control apply to the Northwind payment before remediation began?

## Recommended Next Steps

1. Reconcile Northwind Logistics against the Finance Ops exception log and payment-release timestamp.
2. Pull the full Q4 population of verbal vendor exceptions into the same review workflow.
3. Classify the issue as a control gap unless later evidence shows timely Finance Ops approval or an approved compensating control.
""".strip()

if not RUN_AGENT:
    print("RUN_AGENT is False, so this cell shows an example memo shape rather than running the model.\n")
    print(EXAMPLE_OUTPUT)
```

## 檢視產生的檔案

agent 最終的回覆有用，但看過 sandbox 執行產生的檔案，可靠性模式會更清楚。這一節把平常看不到的狀態攤開來：

- 給審查人員看的 memo：`outputs/compliance_review_memo.md`，
- SDK 產生的 memory 檔，例如 `memories/MEMORY.md` 和 `memories/memory_summary.md`，
- 這次執行產生的工作區檔案，包括 session log。

產生的 memory 檔不是合規 memo，也不該被當成調查事實。它是可重用的流程 memory。`Task Group` 標題是 memory 系統自己的分組標籤，而 memory generator 用 `MemoryGenerateConfig.extra_prompt` 引導，讓它存流程經驗，而不是 ACME 的特定發現。

如果 `RUN_AGENT = False`，這一節會顯示預期的輸出形狀，而不是真實的 sandbox 產出。


````python
try:
    from IPython.display import Markdown, display
except ImportError:
    Markdown = None
    display = None

memo_text = final_run.get("memo") if "final_run" in globals() else None
workspace_files = final_run.get("workspace_files") if "final_run" in globals() else None
memory_artifacts = final_run.get("memory_artifacts", {}) if "final_run" in globals() else {}
compaction_checkpoint = final_run.get("compaction_checkpoint") if "final_run" in globals() else None

print("Generated workspace files:")
print(workspace_files or "No generated workspace files were captured.")

print("\nMemory and compaction configuration:")
print({
    "final_agent_capabilities": [type(capability).__name__ for capability in reliable_agent.capabilities],
    "sandbox_compaction": "Compaction() is attached to the final agent for automatic context management",
    "sandbox_memory": "Memory(generate=MemoryGenerateConfig(...)) is attached to the final agent",
    "memory_write_policy": "Store reusable workflow lessons, not ACME-specific compliance findings",
    "forced_checkpoint": "OpenAIResponsesCompactionSession.run_compaction({force: True}) after the final review",
    "compaction_model_for_checkpoint": COMPACTION_MODEL,
    "checkpoint_result": compaction_checkpoint,
})

if memory_artifacts:
    for path, text in memory_artifacts.items():
        heading = f"### Generated SDK memory artifact: `{path}`\n\n"
        explanation = (
            "This block is generated by the SDK `Memory()` primitive. It is reusable "
            "workflow memory, not the compliance memo and not the investigation system "
            "of record.\n\n"
            "```text\n----- BEGIN GENERATED SDK MEMORY ARTIFACT -----\n"
        )
        closing = "\n----- END GENERATED SDK MEMORY ARTIFACT -----\n```"
        if display is not None and Markdown is not None:
            display(Markdown(heading + explanation + text + closing))
        else:
            print(f"\nGenerated SDK memory artifact: {path}\n")
            print("----- BEGIN GENERATED SDK MEMORY ARTIFACT -----")
            print(text)
            print("----- END GENERATED SDK MEMORY ARTIFACT -----")
else:
    print("\nNo generated memory artifacts were captured. Set RUN_AGENT = True and rerun the final workflow.")

if memo_text:
    if display is not None and Markdown is not None:
        display(Markdown("## Generated memo: `outputs/compliance_review_memo.md`\n\n" + memo_text))
    else:
        print("\nGenerated memo:\n")
        print(memo_text)
else:
    print("\nNo memo was captured. Set RUN_AGENT = True and rerun the final workflow.")
````

**常見陷阱**

不要把 `Memory()` 當成沒人審閱的事實資料庫。

Memory 應該幫下一次執行記得「怎麼做事」，不該變成一份影子合規紀錄。如果某個結論重要，就把它連同引用寫進經過審閱的產出。

## 結論

你現在有了可靠的長時間 agent 流程的基本元件：

- 受控檔案存取的 sandbox 工作區。
- 幫 agent 在文件間導航的 manifest。
- 應付有限 context window 的 compaction。
- 可重用流程經驗的 memory。
- 作為審閱後調查成果的 memo。

核心的設計選擇是分工：context 幫 agent 做事，memory 幫未來的 agent 做得更好，而人會倚賴的事實放在經審閱的產出裡。

## 重點整理

- Compaction 解決單次長對話的 context 太大，Memory 解決跨次執行的經驗重用，兩者用途不同。
- Memory 只存流程經驗和偏好，個案結論一律寫進有引用的 memo。
- `Manifest` 是 sandbox 工作區的契約，檔案、目錄、mount 都在這裡宣告，不要塞進 prompt。
- Compaction 最好在有意義的階段邊界做，不是每回合都壓。
- 明確傳入 capability 清單，才能清楚看出基準行為，再一個一個疊上 compaction 和 memory。

## 練習

1. 把 `RUN_AGENT` 改成 `True`（需要 `OPENAI_API_KEY`），跑完後打開 `outputs/compliance_review_memo.md` 和 `memories/MEMORY.md`，確認 memo 有引用證據、memory 裡沒有個案結論。
2. 在強制 checkpoint 的 `run_compaction({"force": True})` 之前和之後，各印一次 session 的歷史長度，比較差異。
3. 改用 `StaticCompactionPolicy` 設一個很低的門檻取代強制 checkpoint，看看是否真的有觸發 compaction，並想想為什麼小資料集不容易觸發。
