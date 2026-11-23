---
translated: true
source: examples/codex/Build_iterative_repair_loops_with_Codex.ipynb
---
# 用 Codex 建立迭代修復迴圈

> 原文：[examples/codex/Build_iterative_repair_loops_with_Codex.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/codex/Build_iterative_repair_loops_with_Codex.ipynb)

一份 Codex cookbook，示範怎麼用 review、repair、validation 迴圈，去改善技術文件類的產出。

## 這篇在做什麼

用 Codex CLI 的 headless 模式，做一個「產出、驗證、拿回饋再修」的閉環 agent 流程。範例是修三份故意放舊的 API/SDK 教學 notebook：先 review 找問題，再修，再實際跑一遍驗證，沒過就把失敗當成下一輪的輸入。

## 學完你會

- 把 agent 工作拆成 review、repair、validate 三個階段，每階段用 JSON schema 輸出結構化結果交給下一階段。
- 用 `codex exec` 從 Python 呼叫 Codex，並把驗證結果（執行失敗、judge 評分）餵回下一輪 repair prompt。
- 用每輪的 `record.json` 留下稽核紀錄，並設計停止條件，判斷迴圈有沒有收斂。

## 開跑前

- 需要 `OPENAI_API_KEY`，live 的 repair 迴圈會呼叫付費模型。
- 要安裝 Codex CLI（第一個 code cell 會裝，已經有的話可以跳過）。
- 單獨下載這份 notebook 的話，要把旁邊的 `data/docs/` 資料夾一起下載，範例 notebook 在裡面。

---

這篇 cookbook 講的是閉環的 agent 工作流程：agent 產出一個結果，驗證它，再用回饋改善下一輪。

我們會看一個文件可靠度的流程，用來偵測、修復並驗證過期或壞掉的 API 與 SDK 範例。實際範例用的是故意放舊的 notebook，改編自這個 Cookbook repo。

我們用 Codex 來建這個 agent 迴圈。Codex 會檢視目前的狀態，做聚焦的修改，跑驗證，如果回饋顯示還有問題就再來一輪。

notebook 的任務只是範例。只要 agent 的輸出可以用可信的回饋來衡量，這個模式都適用。

這個流程有三個階段：

- **Review：** 檢視目前的產出，回傳結構化的發現，不修改任何檔案。
- **Repair：** 根據發現和最新的驗證回饋，對複製出來的產出做聚焦的修改。
- **Validate：** 執行相關的檢查，回報還有什麼需要處理。

驗證讓迴圈閉起來。修好的 notebook 必須通過重要的檢查，剩下的問題就成為下一輪 repair 的輸入。


<p align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/codex_iterative_repair_loop.png" alt="Codex iterative repair loop for technical documentation" width="350"/>
</p>


## 設定

這份 notebook 用 [Codex CLI](https://developers.openai.com/codex/cli) 的 headless 模式，所以修復步驟可以從 Python cell 執行，不用聊天介面。第一個 code cell 會安裝 CLI，已經裝好的話可以跳過。

在跑 live 的修復迴圈之前，先在環境裡設好 `OPENAI_API_KEY`。

notebook 預設用一個快速的修復模型，讓完整範例能在合理時間內跑完。想試別的模型，開始之前先設 `REPAIR_MODEL`。安裝 cell 會固定一個已知的 Codex CLI 版本以便重現，想要新版 CLI 的行為時，再自己有意識地更新版本。


```python
!npm install -g @openai/codex@0.130.0
```

```python
import concurrent.futures
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

CANDIDATE_EXAMPLE_DIRS = [Path("."), Path("examples/codex")]
EXAMPLE_DIR = next((base for base in CANDIDATE_EXAMPLE_DIRS if (base / "data" / "docs").exists()), None)

if EXAMPLE_DIR is None:
    raise RuntimeError(
        "This notebook needs its companion sample notebooks. "
        "Download the data folder that ships with this example and place it next to "
        "this notebook as ./data/docs, or run from a checkout where examples/codex/data/docs exists."
    )

DATA_DIR = EXAMPLE_DIR / "data" / "docs"
DEFAULT_RUNS_DIR = Path(tempfile.gettempdir()) / "codex_iterative_repair_loop_outputs"
RUNS_DIR = Path(os.getenv("CODEX_REPAIR_RUNS_DIR", str(DEFAULT_RUNS_DIR))).expanduser()
RUNS_DIR.mkdir(parents=True, exist_ok=True)
```

```python
MODEL = os.getenv("REPAIR_MODEL", "gpt-5.4-mini")
COOKBOOK_CHAT_MODEL = os.getenv("COOKBOOK_CHAT_MODEL", "gpt-5.5")
REPAIR_REASONING_EFFORT = os.getenv("REPAIR_REASONING_EFFORT", "low")

if not os.environ.get("OPENAI_API_KEY"):
    raise ValueError("Set the OPENAI_API_KEY environment variable before running the live Codex repair loop.")

CODEX_CLI = shutil.which("codex")
if CODEX_CLI is None:
    raise RuntimeError("Run the install cell before continuing; Codex CLI is not on PATH.")
```

## 載入範例 artifact

下面的 cell 載入三份配套的 notebook，並彙整驅動修復迴圈的 metadata。

範例刻意做得很小，跑得快，但仍然練到整個架構：review 找出實質問題，repair 做聚焦的修改，validation 產生下一輪要用的回饋。

如果你是單獨下載這份 notebook，也要下載配套的 `data/docs/` 資料夾，放在 notebook 旁邊，再跑下面的 cell。程式碼預期那些範例 notebook 在本機可用。

在這個例子裡，validation 是把每份修好的 notebook 從頭到尾執行一遍。在別的領域，validation 可能是 unit test、政策檢查、schema validator、模擬或人工核准。重點是失敗要變成結構化的回饋，而不是死路。


```python
NOTEBOOKS = [
    DATA_DIR / "qdrant_embeddings_search_pre_repair.ipynb",
    DATA_DIR / "getting_started_evals_pre_repair.ipynb",
    DATA_DIR / "knowledge_retrieval_pre_repair.ipynb",
]


def read_notebook(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def case_metadata(path: Path) -> dict[str, Any]:
    return read_notebook(path).get("metadata", {}).get("codex_case_study", {})


cases = []
for notebook_path in NOTEBOOKS:
    notebook = read_notebook(notebook_path)
    metadata = notebook.get("metadata", {}).get("codex_case_study", {})
    repair_story = metadata.get("repair_story", {})
    cases.append(
        {
            "notebook": notebook_path.name,
            "cells": len(notebook["cells"]),
            "code_cells": sum(cell["cell_type"] == "code" for cell in notebook["cells"]),
            "source": metadata.get("source_path"),
            "target_iteration": repair_story.get("target_iteration"),
            "repair_depth": repair_story.get("repair_depth", ""),
        }
    )

cases
```

??? note "輸出"

    ```text
    [{'notebook': 'qdrant_embeddings_search_pre_repair.ipynb',
      'cells': 5,
      'code_cells': 4,
      'source': 'examples/vector_databases/qdrant/Using_Qdrant_for_embeddings_search.ipynb',
      'target_iteration': 1,
      'repair_depth': 'One-pass cleanup: modernize the local Qdrant query path and clarify the sampled fixture framing.'},
     {'notebook': 'getting_started_evals_pre_repair.ipynb',
      'cells': 5,
      'code_cells': 4,
      'source': 'examples/evaluation/Getting_Started_with_OpenAI_Evals.ipynb',
      'target_iteration': 2,
      'repair_depth': 'Two-pass cleanup: first modernize the obvious stale Evals flow, then use validation feedback to remove result-log brittleness.'},
     {'notebook': 'knowledge_retrieval_pre_repair.ipynb',
      'cells': 5,
      'code_cells': 4,
      'source': 'examples/How_to_call_functions_for_knowledge_retrieval.ipynb',
      'target_iteration': 3,
      'repair_depth': 'Three-pass cleanup: modernize model/API shape, then tighten runnable local setup, then restore the full retrieval teaching flow.'}]
    ```

## 定義業務規則與問題分類

在請 Codex review 或修復 artifact 之前，先給它一份小的共用契約。這樣迴圈會聚焦在重要的問題上，不用叫模型從零推斷每一條產品和風格規則。

下面的規則定義了這些範例 notebook 什麼叫「好」：使用現行的 API 寫法、清楚的 setup、可在本機執行的範例，以及保留原本的教學目標。在別的工作流程裡，這份契約會描述該領域的 source of truth。


```python
business_rules = {
    "preferred_chat_model": COOKBOOK_CHAT_MODEL,
    "preferred_embedding_model": "text-embedding-3-large",
    "modernize": [
        "client.chat.completions.create -> client.responses.create",
        "legacy function-calling schemas -> current tools schema",
        "qdrant.search -> qdrant.query_points",
        "oaieval CLI examples -> current Evals API workflow",
    ],
    "reader_experience": [
        "Make fresh-environment setup explicit.",
        "Keep the included examples runnable with local data and the standard library.",
        "Keep sample repairs self-contained unless the notebook explicitly teaches external setup.",
        "Remove manual result-file placeholders.",
        "State runtime prerequisites and side effects before readers run cells.",
        "Preserve the original teaching goal while modernizing the implementation.",
    ],
}

business_rules
```

## 定義結構化輸出

每個階段都回傳結構化的資料，讓下一階段有具體的東西可以用。

Review 回傳 findings。Repair 回傳修改摘要和更新後 artifact 的路徑。Validation 回傳下一輪要處理的剩餘差異。有了結構化的交接，迴圈更容易 debug、重跑，也更容易套用到其他類型的 artifact。


```python
def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties),
        "additionalProperties": False,
    }


def string_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


finding_schema = object_schema(
    {
        "artifact": {"type": "string"},
        "issue_type": {"type": "string"},
        "severity": {"type": "string"},
        "description": {"type": "string"},
        "suggested_fix_direction": {"type": "string"},
    }
)

review_schema = object_schema(
    {"findings": {"type": "array", "items": finding_schema}}
)

fix_schema = object_schema(
    {
        "artifact": {"type": "string"},
        "iteration": {"type": "integer"},
        "changes_made": string_array(),
        "unresolved_items": string_array(),
        "updated_artifact_path": {"type": "string"},
    }
)

validation_case_schema = object_schema(
    {
        "name": {"type": "string"},
        "passed": {"type": "boolean"},
        "severity": {"type": "string"},
        "evidence": {"type": "string"},
        "feedback": {"type": "string"},
    }
)

validation_schema = object_schema(
    {
        "overall_passed": {"type": "boolean"},
        "cases": {"type": "array", "items": validation_case_schema},
        "remaining_delta": string_array(),
    }
)
```

## Review 階段

review 階段讀 artifact，回傳結構化的 findings。它不跑驗證，也不編輯檔案。這樣分開，第一步才能專注：在改任何東西之前，先找出可能的問題。

我們把 review prompt 連同 JSON schema 一起送給 `codex exec`。schema 讓結果可被機器讀取，所以後面的 cell 可以把 findings 直接傳進 repair prompt，不用從上一個回答的文字裡硬抓。


```python
def notebook_text(path: Path, max_chars: int = 7000) -> str:
    chunks = []
    for index, cell in enumerate(read_notebook(path)["cells"]):
        source = "".join(cell.get("source", []))
        chunks.append(f"cell {index} ({cell['cell_type']})\n{source}")
    text = "\n\n".join(chunks)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[truncated for prompt size]"


def run_command(command: str, *, stdin: str | None = None, cwd: Path | None = None, timeout: int | None = None):
    cwd = Path.cwd() if cwd is None else cwd
    return subprocess.run(
        shlex.split(command),
        input=stdin,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_codex_json(prompt: str, schema: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = run_dir / "prompt.txt"
    schema_file = run_dir / "schema.json"
    answer_file = run_dir / "answer.json"

    prompt_file.write_text(prompt, encoding="utf-8")
    schema_file.write_text(json.dumps(schema, indent=2), encoding="utf-8")

    command = f"""
    {CODEX_CLI} exec
      --model {MODEL}
      --sandbox workspace-write
      --ask-for-approval never
      --config model_reasoning_effort={REPAIR_REASONING_EFFORT}
      --output-schema {schema_file}
      --output-last-message {answer_file}
      -
    """
    result = run_command(command, stdin=prompt)
    (run_dir / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")

    if result.returncode != 0:
        raise RuntimeError(f"Codex exited with {result.returncode}. See {run_dir / 'stderr.txt'}.")

    return json.loads(answer_file.read_text(encoding="utf-8"))


def review_notebook(path: Path, run_dir: Path) -> list[dict[str, Any]]:
    prompt = "\n".join(
        [
            "You are reviewing a public OpenAI Cookbook notebook before publication.",
            f"Artifact: {path.name}",
            "Find issues that would make the notebook stale, hard to run, or confusing for a developer reader.",
            "Do not execute the notebook or edit files.",
            "Use concise issue_type labels such as stale_model, deprecated_api, setup_gap, runtime_risk, or clarity_issue.",
            f"Business rules: {json.dumps(business_rules)}",
            "Base findings only on the notebook content below.",
            "Keep the findings focused; three strong findings are better than a long list.",
            "",
            notebook_text(path),
        ]
    )
    return run_codex_json(prompt, review_schema, run_dir)["findings"]
```

```python
def run_initial_review(path: Path) -> tuple[str, list[dict[str, Any]]]:
    return path.name, review_notebook(path, RUNS_DIR / "initial_review" / path.stem)


with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(NOTEBOOKS))) as executor:
    initial_reviews = dict(executor.map(run_initial_review, NOTEBOOKS))

initial_reviews
```

## Repair 階段

repair 階段拿到目前的 artifact、review 的 findings、業務規則，以及上一輪的驗證回饋（如果有）。迴圈學到越多，prompt 就越具體。

Codex 在 iteration 目錄裡編輯一份複本，並回傳修改內容的簡短摘要。迴圈不假設修改一定有效，是否有效由下一步的 validation 決定。


```python
def repair_prompt(path: Path, updated_path: Path, findings: list[dict[str, Any]], remaining_delta: list[str], iteration: int) -> str:
    repair_story = case_metadata(path).get("repair_story", {})
    return "\n".join(
        [
            "You are repairing a copy of a public OpenAI Cookbook notebook.",
            f"Source notebook: {path}",
            f"Editable copy: {updated_path}",
            f"Iteration: {iteration}",
            "Make the smallest useful edits that address the review findings and validation delta.",
            "Preserve the notebook's teaching flow and original purpose.",
            "Keep sample repairs self-contained unless the notebook explicitly teaches external setup.",
            "For staged examples, focus on the most important remaining issue for this pass instead of rewriting everything at once.",
            "Edit only the editable copy. Do not claim the notebook passes validation.",
            f"Repair depth: {json.dumps(repair_story, indent=2)}",
            f"Business rules: {json.dumps(business_rules, indent=2)}",
            f"Review findings: {json.dumps(findings, indent=2)}",
            f"Remaining validation delta: {json.dumps(remaining_delta, indent=2)}",
        ]
    )


def repair_notebook(path: Path, iteration: int, findings: list[dict[str, Any]], remaining_delta: list[str], case_dir: Path) -> dict[str, Any]:
    updated_path = case_dir / "updated.ipynb"
    updated_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, updated_path)

    prompt = repair_prompt(path, updated_path, findings, remaining_delta, iteration)
    return run_codex_json(prompt, fix_schema, case_dir / "repair")
```

## Validation 階段

validation 的運作像一個小型 eval。我們定義想要的行為，執行相關的檢查，再請一個 judge 依照這份評分標準給結果打分。

以文件範例來說，先執行。很多 notebook 的問題只會在 runtime 出現：缺 import、過期的檔案路徑、依賴舊 API 回應的 cell，或是作者覺得清楚、但新讀者看不懂的 setup 說明。

如果驗證失敗，失敗就成為下一輪修復的證據。這讓下一次修復有觀察到的行為當根據，不只是 diff 看起來對不對。


```python
VALIDATION_CASES = [
    {
        "name": "api_modernization",
        "question": "Does the notebook avoid stale OpenAI API patterns, legacy function-calling syntax, and outdated model names?",
    },
    {
        "name": "setup_reproducibility",
        "question": "Could a reader run the notebook from a fresh environment without hidden manual steps?",
    },
    {
        "name": "artifact_integrity",
        "question": "Did the update preserve the notebook's teaching flow and avoid deleting substantive cells?",
    },
]


def short_output(value: Any, limit: int = 1200) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return str(value)[-limit:]


def execute_notebook(path: Path) -> dict[str, Any]:
    code_cells = sum(cell["cell_type"] == "code" for cell in read_notebook(path)["cells"])
    command = f"jupyter nbconvert --to notebook --execute --inplace {path.name}"

    try:
        result = run_command(
            command,
            cwd=path.parent,
            timeout=int(os.getenv("SAMPLE_NOTEBOOK_TIMEOUT_SECONDS", "300")),
        )
    except FileNotFoundError:
        return {
            "status": "failed",
            "executed_code_cells": 0,
            "error": "Jupyter or nbconvert is not installed or is not available on PATH.",
            "summary": "Install Jupyter with nbconvert before running the validation loop.",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "failed",
            "executed_code_cells": 0,
            "error": f"Notebook execution timed out after {exc.timeout} seconds.",
            "summary": short_output(exc.stderr or exc.stdout),
        }

    output = result.stderr or result.stdout
    return {
        "status": "passed" if result.returncode == 0 else "failed",
        "executed_code_cells": code_cells if result.returncode == 0 else 0,
        "error": "" if result.returncode == 0 else f"Notebook execution exited with code {result.returncode}.",
        "summary": short_output(output),
    }

def validation_prompt(updated_path: Path, before_path: Path, execution: dict[str, Any], iteration: int) -> str:
    repair_story = case_metadata(before_path).get("repair_story", {})
    return "\n".join(
        [
            "You are judging a repaired OpenAI Cookbook notebook.",
            f"Iteration: {iteration}",
            "Score each validation case independently and give concise feedback for the next repair pass.",
            "Set overall_passed to false when execution failed or any case has a material issue.",
            "When execution failed, include the failure in remaining_delta so the next repair pass can address it.",
            "Use the business rules as the source of truth for current model names and API targets.",
            "Do not mark the preferred embedding model or preferred chat model as stale.",
            "For local examples, do not require extra services or package installs when the notebook says it is intentionally self-contained.",
            f"Repair depth: {json.dumps(repair_story, indent=2)}",
            f"Business rules: {json.dumps(business_rules, indent=2)}",
            f"Validation cases: {json.dumps(VALIDATION_CASES, indent=2)}",
            f"Execution evidence: {json.dumps(execution, indent=2)}",
            f"Original cell count: {len(read_notebook(before_path)['cells'])}",
            f"Updated cell count: {len(read_notebook(updated_path)['cells'])}",
            "",
            notebook_text(updated_path),
        ]
    )


def staged_delta(before_path: Path, iteration: int) -> list[str]:
    repair_story = case_metadata(before_path).get("repair_story", {})
    target = int(repair_story.get("target_iteration") or 1)
    if iteration >= target:
        return []
    depth = repair_story.get("repair_depth", "This case is intentionally staged across multiple repair passes.")
    return [f"Continue to iteration {iteration + 1}: {depth}"]


def evaluate_notebook(updated_path: Path, before_path: Path, run_dir: Path, iteration: int) -> dict[str, Any]:
    execution = execute_notebook(updated_path)
    judged = run_codex_json(validation_prompt(updated_path, before_path, execution, iteration), validation_schema, run_dir)
    failed_cases = [case for case in judged["cases"] if not case["passed"]]
    execution_delta = []
    if execution["status"] != "passed":
        execution_delta.append(f"Execution failed: {execution.get('error') or execution.get('summary')}")

    stage_delta = staged_delta(before_path, iteration)
    return {
        "passed": judged["overall_passed"] and execution["status"] == "passed" and not stage_delta,
        "execution_status": execution["status"],
        "executed_code_cells": execution["executed_code_cells"],
        "execution_summary": execution["summary"],
        "findings": failed_cases,
        "remaining_delta": execution_delta + stage_delta + judged["remaining_delta"],
    }
```

## 儲存每輪的輸出

每一輪會寫一個 `record.json`，以這個範例來說，還會在 `CODEX_REPAIR_RUNS_DIR/iteration_N/<sample_name>/` 底下寫一份修好的 notebook。如果沒設 `CODEX_REPAIR_RUNS_DIR`，notebook 會寫到系統的暫存目錄，一般的 repo checkout 就不會被弄髒。

這些檔案就是稽核軌跡。你可以看到 review 找到什麼、Codex 改了什麼、執行有沒有通過，以及什麼回饋被帶進下一輪。

`record.json` 是單次迴圈嘗試的收據。它把階段之間的交接放在同一個地方：

```json
{
  "review": [{"issue_type": "deprecated_api", "severity": "high"}],
  "repair": {
    "changes_made": ["Updated the notebook to use the current API pattern."],
    "updated_artifact_path": "/tmp/codex_iterative_repair_loop_outputs/iteration_1/sample/updated.ipynb"
  },
  "validation": {
    "passed": false,
    "remaining_delta": ["One setup instruction is still unclear."]
  }
}
```

這份精簡的紀錄，讓維護者不用從 notebook 的 diff 和終端機 log 重建整個執行過程，就能審查這個迴圈。


```python
def save_json(payload: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def iteration_dir(number: int) -> Path:
    path = RUNS_DIR / f"iteration_{number}"
    path.mkdir(parents=True, exist_ok=True)
    return path
```

## 執行 iteration 1

每個 notebook 案例彼此獨立，所以我們並行處理。這樣 demo 跑得快，每個範例也照樣走同樣的 review、repair、validation 流程。

Iteration 1 會重用前面 review cell 的初始 findings。這一輪之後，看回傳的 boolean：通過的案例可以停，失敗的案例把驗證回饋帶進下一輪。


```python
current_notebooks = {path.name: path for path in NOTEBOOKS}
history: dict[int, dict[str, Any]] = {}


def review_findings_for(original: Path, current_path: Path, case_dir: Path, previous_results: dict[str, Any] | None) -> list[dict[str, Any]]:
    if previous_results is None:
        return initial_reviews[original.name]
    return review_notebook(current_path, case_dir / "review")


def run_case(number: int, original: Path, run_dir: Path, previous_results: dict[str, Any] | None) -> tuple[str, dict[str, Any], Path]:
    name = original.name
    case_dir = run_dir / original.stem
    current_path = current_notebooks[name]

    findings = review_findings_for(original, current_path, case_dir, previous_results)
    delta = [] if previous_results is None else previous_results[name]["validation"]["remaining_delta"]
    repair = repair_notebook(current_path, number, findings, delta, case_dir)
    updated_path = Path(repair["updated_artifact_path"])
    validation = evaluate_notebook(updated_path, current_path, case_dir / "evaluation", number)

    record = {"review": findings, "repair": repair, "validation": validation}
    save_json(record, case_dir / "record.json")
    return name, record, updated_path


def run_iteration(number: int, previous_results: dict[str, Any] | None = None) -> dict[str, Any]:
    results = {}
    updates = {}
    run_dir = iteration_dir(number)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(NOTEBOOKS))) as executor:
        futures = [executor.submit(run_case, number, original, run_dir, previous_results) for original in NOTEBOOKS]
        for future in concurrent.futures.as_completed(futures):
            name, record, updated_path = future.result()
            results[name] = record
            updates[name] = updated_path

    current_notebooks.update(updates)
    history[number] = results
    return results


iteration_1 = run_iteration(1)
{name: result["validation"]["passed"] for name, result in iteration_1.items()}
```

??? note "輸出"

    ```text
    {'qdrant_embeddings_search_pre_repair.ipynb': True,
     'getting_started_evals_pre_repair.ipynb': False,
     'knowledge_retrieval_pre_repair.ipynb': False}
    ```

## 執行 iteration 2

迴圈從 iteration 2 開始看到回報。Codex 不再只根據最初的 review 工作，它還看得到驗證時發生了什麼。

這會改變任務的性質。我們不是要求大改寫，而是根據上一次執行的證據，要求下一個有用的修復：什麼跑起來了、什麼通過了、什麼還需要處理。

對內附的分階段 fixture 來說，這一輪的設計是清掉中等深度的 Evals 案例，而更深的 Knowledge Retrieval 案例繼續處理一個更小、更具體的差異。


```python
iteration_2 = run_iteration(2, iteration_1)
{name: result["validation"]["passed"] for name, result in iteration_2.items()}
```

??? note "輸出"

    ```text
    {'getting_started_evals_pre_repair.ipynb': True,
     'qdrant_embeddings_search_pre_repair.ipynb': True,
     'knowledge_retrieval_pre_repair.ipynb': False}
    ```

## 執行 iteration 3

Iteration 3 專注在最難的文件案例。

Knowledge Retrieval 這個 fixture 必須把 API 的形狀現代化、用本機資料保持可執行，而且保留 retrieval 的教學流程。這些要求會互相拉扯：讓 notebook 變現代的修復，可能不小心讓它變得比較不能跑，而保持在本機的修復，又可能刪掉太多原本的教學內容。

第三輪給 Codex 最新的 notebook 和最後的驗證差異。這一段示範了為什麼要迭代：agent 針對剩下的具體問題回應，而不是想一次預先處理所有事。


```python
iteration_3 = run_iteration(3, iteration_2)
{name: result["validation"]["passed"] for name, result in iteration_3.items()}
```

??? note "輸出"

    ```text
    {'qdrant_embeddings_search_pre_repair.ipynb': True,
     'getting_started_evals_pre_repair.ipynb': True,
     'knowledge_retrieval_pre_repair.ipynb': True}
    ```

## 彙整改善結果

現在我們可以看整個執行的全貌，不用手動打開每個中間 artifact。下面的摘要呈現最重要的訊號：哪些 artifact 通過、剩下幾個驗證 finding，以及有沒有差異被帶到後面。

以內附的 fixture 來說，預期的樣子很簡單：一份 notebook 在 iteration 1 清掉，另一份在 iteration 2，最難的在 iteration 3。在真實的維護流程裡，這張表會告訴你迴圈有沒有在收斂，還是需要更明確的限制或人工 review。

這份摘要對人工 review 也有用。維護者可以先看通過與失敗的分布，打開仍有差異的紀錄，只檢查已經準備好審查的修復後 artifact。


```python
summary = []
for iteration, results in history.items():
    for artifact, record in results.items():
        validation = record["validation"]
        summary.append(
            {
                "iteration": iteration,
                "artifact": artifact,
                "passed": validation["passed"],
                "findings": len(validation["findings"]),
                "remaining_delta": len(validation["remaining_delta"]),
            }
        )

summary
```

```python
for row in summary:
    print(
        f"iteration={row['iteration']} artifact={row['artifact']} "
        f"passed={row['passed']} findings={row['findings']} delta={row['remaining_delta']}"
    )
```

??? note "輸出"

    ```text
    iteration=1 artifact=qdrant_embeddings_search_pre_repair.ipynb passed=True findings=0 delta=0
    iteration=1 artifact=getting_started_evals_pre_repair.ipynb passed=False findings=0 delta=1
    iteration=1 artifact=knowledge_retrieval_pre_repair.ipynb passed=False findings=1 delta=3
    iteration=2 artifact=getting_started_evals_pre_repair.ipynb passed=True findings=0 delta=0
    iteration=2 artifact=qdrant_embeddings_search_pre_repair.ipynb passed=True findings=0 delta=0
    iteration=2 artifact=knowledge_retrieval_pre_repair.ipynb passed=False findings=0 delta=1
    iteration=3 artifact=qdrant_embeddings_search_pre_repair.ipynb passed=True findings=0 delta=0
    iteration=3 artifact=getting_started_evals_pre_repair.ipynb passed=True findings=0 delta=0
    iteration=3 artifact=knowledge_retrieval_pre_repair.ipynb passed=True findings=0 delta=0
    ```

## 摘要告訴我們什麼

重要的訊號不是 Codex 做了修改，而是隨著迴圈執行，剩下的驗證差異越來越小。

| 輪次 | 要看的訊號 | 為什麼重要 |
| --- | --- | --- |
| Iteration 1 | 最簡單的 fixture 通過，較深的 fixture 留下小的差異。 | 迴圈能先做初步修復，同時把還需要證據的案例帶下去。 |
| Iteration 2 | 中等深度的 fixture 在看過驗證回饋後清掉。 | runtime 和 judge 的回饋變成有用的修復指示。 |
| Iteration 3 | 最深的 fixture 清掉，或留下聚焦的最終差異。 | 迴圈收斂了，或是產出一份清楚的交接給人工 reviewer。 |

`record.json` 讓這件事可稽核。一份有用的紀錄要回答四個問題：review 找到什麼、Codex 改了什麼、notebook 有沒有執行成功、還剩什麼。這就是看起來很厲害的修改，和維護者可以信任的修復流程之間的差別。


## 推廣成持續運作的迴圈

上面固定三輪的執行，拿來教這個模式很好用。但 production 的迴圈應該自己決定何時停。

一個好的迴圈通常因為四個原因之一停下來：驗證通過、迴圈達到最大嘗試次數、剩下的差異不再變化，或是下一個決定需要人工 review。這些停止條件跟 repair prompt 一樣重要。

另一個 production 細節是稽核軌跡。每一輪都要保留 review 的 findings、修復後的 artifact、驗證結果、驗證判斷和剩餘差異。這份紀錄讓維護者了解迴圈為什麼繼續、為什麼停，以及哪個 artifact 已準備好審查。


```python
def repair_until_done(max_iterations: int = 3) -> dict[int, dict[str, Any]]:
    current_notebooks.update({path.name: path for path in NOTEBOOKS})
    previous = None
    loop_history = {}

    for number in range(1, max_iterations + 1):
        previous = run_iteration(number, previous)
        loop_history[number] = previous
        if all(record["validation"]["passed"] for record in previous.values()):
            break

    return loop_history
```

## 還能用在哪裡

notebook 的逐步說明只是教這個架構的其中一種方式。只要 agent 修改的檔案或流程，在被接受之前需要主觀審查以外的東西，同樣的模式都有幫助。

幾個高價值的例子：

- **Protocol 最佳化：** 起草更新交給專家審查，再對照劑量規則、時間限制或必要的安全檢查來驗證。
- **法規修補：** 起草受法規管轄內容的更新，再檢查必要的用語、引用、核准和各司法管轄區專屬的詞彙是否完整保留。
- **客服知識更新：** 更新文章，對照目前的產品行為或已知解法測試，把不一致的地方帶進下一輪。
- **程式碼現代化：** 取代已棄用的 API，跑測試或靜態檢查，用剩下的失敗來引導下一次修復。

共通點是：變更很重要，而且每一輪都需要證據。不論目標是 notebook、政策、protocol、客服文章、pipeline 還是程式碼庫，這個迴圈都給 agent 一個用證據改善它的方法，而且證據是維護者看得懂、審查得了的。


## 結論

迭代修復迴圈讓 agent 式的維護更容易審查和運作，因為它把判斷和證明分開。

Review 找出候選問題。Repair 做聚焦的修改。Validation 執行 artifact 並產生下一個差異。當這些階段用結構化輸出互相交換資料，整個流程就更容易檢視、重複和調整。

核心想法很簡單：不要靠單次執行，而是讓流程能從 artifact 學習、做有範圍的修復，並對真實的驗證回饋做出反應。這個小小的改變，讓 agent 式維護實用許多。

## 重點整理

- 閉環的關鍵是驗證，不是修改。修復有沒有效，要靠實際執行的結果來判斷，不是看 diff 像不像對。
- Review、repair、validate 分開，各自回傳結構化輸出，迴圈才容易 debug、重跑和換到別的 artifact 類型。
- 驗證失敗的證據會讓下一輪 repair prompt 越來越具體，所以重點是剩餘差異有沒有變小。
- 每輪的 `record.json` 是稽核軌跡，維護者靠它看懂迴圈為什麼繼續、為什麼停。
- 正式的迴圈要有明確停止條件：驗證通過、達到最大次數、差異不再變化，或需要人工決定。

## 練習

1. 在跑之前設 `REPAIR_MODEL` 換成另一個模型，比較同樣三份 notebook 各要幾輪才通過。
2. 把 `CODEX_REPAIR_RUNS_DIR` 指到你自己的資料夾，跑完後打開某一輪的 `record.json`，對照 review、repair、validation 三個階段的欄位，確認前一輪的剩餘差異有被帶進下一輪。
3. 把固定三輪的流程改成 while 迴圈，加上「驗證通過、達到最大次數、差異跟上一輪相同」三個停止條件，並在差異沒變時印出提示要人工 review。
