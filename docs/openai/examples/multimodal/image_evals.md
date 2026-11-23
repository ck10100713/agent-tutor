---
translated: true
source: examples/multimodal/image_evals.ipynb
---
# 圖像生成與編輯的 Image Evals

> 原文：[examples/multimodal/image_evals.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/multimodal/image_evals.ipynb)

這份 cookbook 教你怎麼替圖像生成和圖像編輯的場景建 eval。

## 這篇在做什麼

做一套可重複使用的 vision eval harness，用 LLM-as-judge 去評 UI mockup、行銷海報、虛擬試穿和 logo 編輯的輸出。重點是針對每個 workflow 設計 rubric，而不是只問「好不好看」。

## 學完你會

- 用 test case、runner、grader 三個插件組出一套 vision eval harness
- 為生成類和編輯類任務設計 gate（pass/fail）加 0–5 分的 rubric，並寫成 judge prompt
- 把分數轉成單一 pass/fail 的 verdict 規則，並用 failure tag 追蹤問題

## 開跑前

- 需要 `OPENAI_API_KEY`，生成、編輯和 judge 都會呼叫付費的 OpenAI API
- 範例會把圖片存在本機的 `images/` 資料夾

## 前言

圖像模型愈來愈常出現在真實的產品流程裡，像設計 mockup、行銷素材、虛擬試穿，還有對既有品牌素材做高精度修改。要在 production 信任這些系統，光問「好不好看」不夠，你需要**可重複、針對特定 workflow 的評估**，確認輸出符合需求、失敗時安全，而且能穩定進步。

Vision eval 比文字 eval 難，因為「答案」是一張圖，裡面混了：

- **硬性限制**：精確的文字、數量、屬性、局部性（「只改這個區域」）。
- **感知品質**：清晰度、一致性、真實感、美感是否符合。
- **隱藏的失敗模式**：細微的變形、非預期的修改、小小的文字錯誤。這些看一眼沒事，但會違反產品需求，編輯時尤其常見。

好的 vision eval **不是**給「漂亮的圖」打分，而是評這個模型在**特定 workflow 裡可不可靠**。很多圖看起來很強，卻因為文字錯、風格不符品牌、或編輯超出範圍而失敗。Image eval 衡量的是真實 prompt 下的**品質、可控性、可用性**，不只是視覺吸引力。

#### 這份指南涵蓋什麼

這份 cookbook 專注在四大類的實用 image-eval 系統：

**1) 圖像生成 evals**

- 指令遵循（限制有沒有滿足）
- 文字渲染（正確、可讀、位置對）
- 風格控制（美感是否符合、品牌/角色一致性）
- 偏好對齊（rubric 標註加 pairwise 比較）

**2) 圖像編輯 evals**

- 轉換正確性（要求的修改有精確完成）
- 局部性（只改該改的地方）
- 保留性（沒要求改的區域維持不變）
- 空間控制（修改套在正確的物件/區域）

**3) 人類回饋對齊**

- 用 rubric 標註和 pairwise 偏好抓主觀品質和「感覺」
- 用校準技巧讓人的判斷長期保持一致

**4) 建 eval 的策略**

- 先從不能妥協的正確性 gate 開始
- 失敗控制住之後，再加分級的品質指標
- 幫失敗模式打標籤，帶動有針對性的迭代

## 建一套 Vision Eval Harness

Vision eval harness 是一個小而可重複的系統，把「這張圖行不行？」變成跨 prompt、模型、設定都能比較的**結構化結果**。

大方向跟任何 LLM eval 系統的迴圈一樣：

**Inputs → Model → Outputs → Graders → Scores → Feedback → Improvement**

為了讓它在後面的生成和編輯章節都能重複使用，harness 圍繞**三個插件**來建：

1.  **Test cases：**要跑什麼（prompt、評分標準，以及選用的輸入圖片/mask）
2.  **Runners：**怎麼呼叫模型並存下輸出圖片
3.  **Graders：**怎麼替輸出打分（rubric、LLM-as-judge，之後再加人工標註）

**Setup**

只要跑一次。它會：
- 建立 API client
- 在資料夾裡建立 `images/`

```python
import os
from openai import OpenAI

client = OpenAI()

os.makedirs("../../images", exist_ok=True)
```

下面是一個最小的 `vision_harness/` 套件，可以直接放進你的 repo。

想看完整、可執行、可延伸的 harness（可編輯、重現、加自己的 case），見 [examples/evals/imagegen_evals](https://github.com/openai/openai-cookbook/tree/main/examples/evals/imagegen_evals)。


### vision_harness/types.py

核心型別保持通用，這樣圖像生成和圖像編輯都能共用。

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

TaskType = Literal["image_generation", "image_editing"]
ScoreValue = bool | int | float | str


@dataclass(frozen=True)
class ImageInputs:
    """Editing inputs: one or more reference images + optional mask."""
    image_paths: list[Path]
    mask_path: Optional[Path] = None


@dataclass(frozen=True)
class TestCase:
    """A single evaluable example."""
    id: str
    task_type: TaskType
    prompt: str
    criteria: str
    image_inputs: Optional[ImageInputs] = None


@dataclass(frozen=True)
class ModelRun:
    """One model configuration to evaluate (useful for sweeps)."""
    label: str
    task_type: TaskType
    params: dict[str, Any]  # e.g. {"model": "...", "quality": "...", ...}


@dataclass(frozen=True)
class Artifact:
    """A saved artifact from a run (usually an image)."""
    kind: Literal["image"]
    path: Path
    mime: str = "image/png"


@dataclass
class ModelResponse:
    """Normalized output from any runner."""
    artifacts: list[Artifact] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)  # optional debug payload


@dataclass(frozen=True)
class Score:
    key: str
    value: ScoreValue
    reason: str = ""
    tags: Optional[list[str]] = None
```

### vision_harness/io.py

graders（LLM-as-judge）會用到它，有時模型呼叫也會用。


```python
from __future__ import annotations

import base64
from pathlib import Path

_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

def image_to_data_url(path: Path) -> str:
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"
```

### vision_harness/storage.py


```python
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

@dataclass
class OutputStore:
    """
    Simple artifact store that writes directly to the root folder.
    Note: This implementation writes directly to `root` (no per-test subfolders),
    which keeps site-relative image paths stable for cookbook rendering.
    """
    root: Path

    def run_dir(self, test_id: str, model_label: str) -> Path:
        # Ignore test/model subfolders; write everything to the root.
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def new_basename(self, prefix: str) -> str:
        created_ms = int(time.time() * 1000)
        return f"{prefix}_{created_ms}"

    def save_png(self, run_dir: Path, basename: str, idx: int, png_bytes: bytes) -> Path:
        out = run_dir / f"{basename}_{idx}.png"
        out.write_bytes(png_bytes)
        return out
```

### vision_harness/sweeps.py


```python
from __future__ import annotations

from itertools import product
from typing import Any


def grid_sweep(
    *,
    base_label: str,
    task_type: TaskType,
    fixed: dict[str, Any],
    grid: dict[str, list[Any]],
) -> list[ModelRun]:
    keys = list(grid.keys())
    runs: list[ModelRun] = []

    for values in product(*[grid[k] for k in keys]):
        params = dict(fixed)
        label_parts = [base_label]
        for k, v in zip(keys, values):
            params[k] = v
            label_parts.append(f"{k}={v}")
        runs.append(ModelRun(label=",".join(label_parts), task_type=task_type, params=params))

    return runs
```

### vision_harness/runners.py

兩個 runner：一個做**生成**，一個做**編輯**。兩個都回傳標準化的 `ModelResponse`，裡面是存好的輸出圖片。


```python
from __future__ import annotations

import base64
from contextlib import ExitStack
from typing import Optional

from openai import OpenAI


def _mime_for_path(path) -> str:
    suffix = str(path).lower()
    if suffix.endswith(".png"):
        return "image/png"
    if suffix.endswith(".jpg") or suffix.endswith(".jpeg"):
        return "image/jpeg"
    if suffix.endswith(".webp"):
        return "image/webp"
    return "application/octet-stream"


def _extract_b64_items(images_response) -> list[str]:
    b64_items: list[str] = []
    for item in getattr(images_response, "data", []) or []:
        b64 = getattr(item, "b64_json", None)
        if b64:
            b64_items.append(b64)
    return b64_items


class ImageGenerationRunner:
    """Text-to-image runner."""

    def __init__(self, client: Optional[OpenAI] = None):
        self.client = client or OpenAI()

    def run(self, case: TestCase, run_cfg: ModelRun, store: OutputStore) -> ModelResponse:
        assert case.task_type == "image_generation"
        assert run_cfg.task_type == "image_generation"

        params = dict(run_cfg.params)
        model = params.pop("model")
        n = int(params.pop("n", 1))

        run_dir = store.run_dir(case.id, run_cfg.label)
        basename = store.new_basename(f"gen_{case.id}_{run_cfg.label}")

        images_response = self.client.images.generate(
            model=model,
            prompt=case.prompt,
            n=n,
            **params,
        )

        artifacts: list[Artifact] = []
        for idx, b64_json in enumerate(_extract_b64_items(images_response)):
            png_bytes = base64.b64decode(b64_json)
            out_path = store.save_png(run_dir, basename, idx, png_bytes)
            artifacts.append(Artifact(kind="image", path=out_path))

        return ModelResponse(artifacts=artifacts, raw={"model": model, "params": run_cfg.params})


class ImageEditRunner:
    """Image editing runner (reference image(s) + optional mask)."""

    def __init__(self, client: Optional[OpenAI] = None):
        self.client = client or OpenAI()

    def run(self, case: TestCase, run_cfg: ModelRun, store: OutputStore) -> ModelResponse:
        assert case.task_type == "image_editing"
        assert run_cfg.task_type == "image_editing"
        assert case.image_inputs is not None and case.image_inputs.image_paths

        params = dict(run_cfg.params)
        model = params.pop("model")
        n = int(params.pop("n", 1))

        run_dir = store.run_dir(case.id, run_cfg.label)
        basename = store.new_basename(f"edit_{case.id}_{run_cfg.label}")

        with ExitStack() as stack:
            image_files = []
            for p in case.image_inputs.image_paths:
                f = stack.enter_context(p.open("rb"))
                image_files.append((p.name, f, _mime_for_path(p)))

            mask_file = None
            if case.image_inputs.mask_path:
                mf = stack.enter_context(case.image_inputs.mask_path.open("rb"))
                mask_file = (case.image_inputs.mask_path.name, mf, _mime_for_path(case.image_inputs.mask_path))

            edit_kwargs = dict(
                model=model,
                prompt=case.prompt,
                image=image_files,
                n=n,
                **params,
            )
            if mask_file is not None:
                edit_kwargs["mask"] = mask_file

            images_response = self.client.images.edit(**edit_kwargs)

        artifacts: list[Artifact] = []
        for idx, b64_json in enumerate(_extract_b64_items(images_response)):
            png_bytes = base64.b64decode(b64_json)
            out_path = store.save_png(run_dir, basename, idx, png_bytes)
            artifacts.append(Artifact(kind="image", path=out_path))

        return ModelResponse(artifacts=artifacts, raw={"model": model, "params": run_cfg.params})
```

### vision_harness/graders.py

一個乾淨的 grader 介面，加上可重複使用的 **LLM-as-judge** grader。只要改變 judge 輸入的組法，生成和編輯都能用。


```python
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from openai import OpenAI


class Grader(Protocol):
    key: str

    def grade(self, response: ModelResponse, case: TestCase) -> Score | list[Score]: ...


def pick_first_image(response: ModelResponse) -> Optional[Path]:
    for artifact in response.artifacts:
        if artifact.kind == "image":
            return artifact.path
    return None


def build_generation_judge_content(case: TestCase, output_image: Path) -> list[dict]:
    return [
        {
            "type": "input_text",
            "text": f"Prompt:\n{case.prompt}\n\nCriteria:\n{case.criteria}",
        },
        {
            "type": "input_image",
            "image_url": image_to_data_url(output_image),
        },
    ]


def build_editing_judge_content(case: TestCase, output_image: Path) -> list[dict]:
    assert case.image_inputs is not None and case.image_inputs.image_paths
    content: list[dict] = [
        {
            "type": "input_text",
            "text": f"Edit instruction:\n{case.prompt}\n\nCriteria:\n{case.criteria}",
        }
    ]
    for image_path in case.image_inputs.image_paths:
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(image_path),
            }
        )
    if case.image_inputs.mask_path:
        content.append(
            {
                "type": "input_image",
                "image_url": image_to_data_url(case.image_inputs.mask_path),
            }
        )
    content.append(
        {
            "type": "input_image",
            "image_url": image_to_data_url(output_image),
        }
    )
    return content


def default_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "pass": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["pass", "reason"],
        "additionalProperties": False,
    }


@dataclass
class LLMajRubricGrader:
    """
    Reusable vision LLM-as-judge grader.
    - Provide a system prompt + a content_builder for generation/editing.
    - Optionally provide a custom JSON schema and parser.
    """

    key: str
    system_prompt: str
    content_builder: Callable[[TestCase, Path], list[dict]]
    judge_model: str = "gpt-5.2"
    client: Optional[OpenAI] = None

    json_schema_name: str = "vision_eval_result"
    json_schema: dict = field(default_factory=default_schema)
    result_parser: Optional[Callable[[dict, str], Score | list[Score]]] = None

    def _parse_result(self, data: dict) -> Score | list[Score]:
        if self.result_parser:
            return self.result_parser(data, self.key)
        return Score(
            key=self.key,
            value=bool(data.get("pass", False)),
            reason=(data.get("reason") or "").strip(),
            tags=data.get("tags") or None,
        )

    def grade(self, response: ModelResponse, case: TestCase) -> Score | list[Score]:
        output_image = pick_first_image(response)
        if not output_image:
            return Score(key=self.key, value=False, reason="No output image artifact found")

        client = self.client or OpenAI()
        content = self.content_builder(case, output_image)

        completion = client.responses.create(
            model=self.judge_model,
            input=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": content},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": self.json_schema_name,
                    "schema": self.json_schema,
                    "strict": True,
                }
            },
        )

        data = json.loads(completion.output_text)
        return self._parse_result(data)
```

### vision_harness/evaluate.py

一個簡單的評估迴圈，回傳純 Python 資料（沒有「eval row」class）。後面的章節可以在上面自己寫報表或 CSV 工具。


```python
from __future__ import annotations

from typing import Any


def _as_score_list(score_or_scores: Score | list[Score]) -> list[Score]:
    if isinstance(score_or_scores, list):
        return score_or_scores
    return [score_or_scores]


def evaluate(
    *,
    cases: list[TestCase],
    model_runs: list[ModelRun],
    graders: list[Grader],
    output_store: OutputStore,
) -> list[dict[str, Any]]:
    gen_runner = ImageGenerationRunner()
    edit_runner = ImageEditRunner()

    results: list[dict[str, Any]] = []

    for case in cases:
        for run_cfg in model_runs:
            if run_cfg.task_type != case.task_type:
                continue

            if case.task_type == "image_generation":
                response = gen_runner.run(case, run_cfg, output_store)
            elif case.task_type == "image_editing":
                response = edit_runner.run(case, run_cfg, output_store)
            else:
                raise ValueError(f"Unknown task_type: {case.task_type}")

            score_map: dict[str, Any] = {}
            reason_map: dict[str, str] = {}

            for grader in graders:
                scored = grader.grade(response, case)
                for score in _as_score_list(scored):
                    score_map[score.key] = score.value
                    reason_map[score.key] = score.reason

            results.append(
                {
                    "test_id": case.id,
                    "model_label": run_cfg.label,
                    "task_type": case.task_type,
                    "artifact_paths": [str(a.path) for a in response.artifacts],
                    "scores": score_map,
                    "reasons": reason_map,
                    "run_params": run_cfg.params,
                }
            )

    return results
```

### 結果表格的渲染輔助函式

```python
import os
from html import escape
from IPython.display import HTML, display


def summarize_scores(scores: dict[str, object]) -> str:
    return os.linesep.join(f"{k}: {scores[k]}" for k in sorted(scores.keys()))


def summarize_reasons(reasons: dict[str, str]) -> str:
    verdict_reason = (reasons.get("verdict") or "").strip()
    if verdict_reason:
        return verdict_reason
    return os.linesep.join(f"{k}: {reasons[k]}" for k in sorted(reasons.keys()) if reasons[k])


def _pre(text: str) -> str:
    return (
        "<pre style='white-space:pre-wrap; word-break:break-word; margin:0'>"
        f"{escape(text)}"
        "</pre>"
    )


def render_result_table(
    *,
    case: TestCase,
    result: dict[str, object],
    title: str,
) -> None:
    sep = os.linesep
    prompt_text = f"{case.prompt}{sep}{sep}Criteria:{sep}{case.criteria}"
    scores = result["scores"]
    reasons = result["reasons"]

    prompt_html = _pre(prompt_text)
    scores_html = _pre(summarize_scores(scores))
    reasons_html = _pre(summarize_reasons(reasons))

    table_html = (
        "<table style='width:100%; table-layout:fixed; border-collapse:collapse;'>"
        "<colgroup>"
        "<col style='width:33%'>"
        "<col style='width:33%'>"
        "<col style='width:33%'>"
        "</colgroup>"
        "<thead><tr>"
        "<th style='text-align:left; padding:8px; border-bottom:1px solid #ddd'>Input Prompt</th>"
        "<th style='text-align:left; padding:8px; border-bottom:1px solid #ddd'>Scores</th>"
        "<th style='text-align:left; padding:8px; border-bottom:1px solid #ddd'>Reasoning</th>"
        "</tr></thead>"
        "<tbody><tr>"
        f"<td style='text-align:left; padding:8px; vertical-align:top'>{prompt_html}</td>"
        f"<td style='text-align:left; padding:8px; vertical-align:top'>{scores_html}</td>"
        f"<td style='text-align:left; padding:8px; vertical-align:top'>{reasons_html}</td>"
        "</tr></tbody></table>"
    )

    display(HTML(f"<div style='font-weight:600; margin:6px 0'>{escape(title)}</div>"))
    display(HTML(table_html))
```

後面的章節只需要提供：

1.  該場景的 `TestCase` 清單（UI mockup、行銷圖、虛擬試穿、logo 編輯等）
2.  一組 `ModelRun`（單次執行，或用 `grid_sweep` 掃參數）
3.  一組 graders，通常是：
    - **Gating graders**（pass/fail）：不能妥協的項目，例如指令遵循、文字正確性、局部性/保留性
    - **Graded metrics**（0–5）：品質面向，例如真實感/可用性、版面/層次、artifact 嚴重程度
    - 選用：人工 rubric 標註和 pairwise 偏好（存在 harness 之外）

這樣後面的內容可以專心講每個場景**要量什麼**，不用每次重寫 harness 的底層。

## 圖像生成 Evals

**場景點子：UI mockup、行銷圖/海報**

**目標：評估 text-to-image 在真實 prompt 下的品質、可控性和實用性**  
涵蓋：

- **指令遵循**（限制有滿足），
- **文字渲染**（生成的文字正確、可讀、位置對），
- **風格**（要求的美感加視覺品質，可能包含品牌、角色、產品一致性）
- **人類回饋對齊**（rubric 標註加 pairwise 偏好）。

圖像生成模型產出的東西會影響真實工作：UI mockup、產品設計、行銷圖、內部簡報。在這些情境裡，圖不只看好不好看，而是看它有沒有傳達意圖、遵守限制，以及下游的人能不能用。

### UI Mockups

圖像模型產生的 UI mockup 愈來愈常用在早期產品探索、設計發想和內部 review。在這些流程裡，mockup 不只是靈感，而是溝通工具，幫設計師、工程師和利害關係人在東西還沒做出來前討論版面、層次、互動意圖和功能範圍。所以成功的標準比較不是美感，而是輸出能不能合理地當成產品文件使用。

範例：

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/mockup_sample.png" width="400"/> 

這一節用一個畫面層級的例子，示範怎麼評估生成的 UI mockup。目標是看生成的 UI 版面是否連貫、元件是否辨識得出來、呈現的產品體驗是否合理。

**為什麼 UI mockup eval 不一樣**

UI mockup 混合了幾個難評的面向：

1.  **元件保真度（gating）**  
    生成的圖必須清楚呈現要求的畫面類型和狀態。按鈕要看起來能點，輸入框要看起來能編輯，導覽要看起來像導覽。
2.  **版面呈現（graded）**  
    好的 UI mockup 一眼就讓人知道使用者能做什麼、什麼最重要。版面要讓主要動作明顯，次要動作明確居次，資訊的分組要反映真實的互動流程。
3.  **圖中文字渲染（gating）**  
    UI 上的文字就是功能。標籤、標題、call to action 必須清楚可讀而且渲染正確。

**範例任務：生成手機結帳畫面**

- 情境：一個消費型電商 app 需要手機結帳畫面，讓使用者檢視訂單並完成付款。
- Prompt 建議：明確指定畫面類型、平台、必要的 UI 元素、按鈕/連結的確切文字、層次限制，以及不准出現的多餘元素。
- 實作：完整的 prompt 和評分標準在下面的 harness setup code cell 裡（`ui_prompt` 和 `ui_criteria`）。

#### 要評什麼（實用指標）：

##### 1) 指令遵循：Pass / Fail（gate）

多數 UI mockup eval 都從指令保真度開始。最基本的問題很簡單：模型有沒有生出被要求的畫面？如果 prompt 指定手機結帳畫面，輸出就該像手機結帳畫面，不是一般的 landing page。必要的區塊、狀態或限制都該出現，整體結構要符合請求的意圖。這個面向通常權重最高，因為模型如果沒做到核心要求，其他部分都不重要。UI mockup 通過基本指令之後，評估才轉向畫面作為產品文件是否好用、連貫。

**PASS 條件**

- 有正確的畫面類型和平台脈絡。
- 包含所有必要的區塊、狀態或限制。

**FAIL 條件**

- 缺少任何必要元件，或輸出改變了 UI 的用途。

##### 2) 版面與層次：0–5

衡量畫面能不能一眼傳達清楚。

**看什麼：**

- 主要和次要動作之間有清楚的視覺層次
- 對齊和間距一致
- 相關元素的分組合理

##### 3) 文字渲染與可讀性：Pass / Fail（gate）

標籤、標題和 call to action 需要可讀且不含糊。

**PASS 條件**

- 文字可讀、拼字正確、標示合理。
- 字級反映層次（標題、標籤、輔助文字）。

**FAIL 條件**

- 任何關鍵文字無法閱讀、被截斷、拼錯或變形。

##### 4) UI 真實感與可用性：*0–5*

衡量 mockup 像不像一個合理的產品介面。

**看什麼：**

- 輸入框看起來能編輯、按鈕看起來能點
- 導覽看起來像導覽
- 互動元素在視覺上跟靜態內容有區別

##### 5) 人類回饋（快速又高效益）

UI 的「可用性清晰度」是人類最能加值的地方。保持輕量，聚焦在互動意圖。

- Rubric 標註（快）：
  - 你會用這個 mockup 來迭代真實的產品畫面嗎？（Y/N）
  - 如果 N，為什麼？（缺區塊、動作按鈕不清楚、文字看不懂、版面混亂等）
  - 整體可用性清晰度：1–5
- 常見失敗標籤（用來 debug 和迭代）：
  - `wrong_screen_type`
  - `missing_required_section`
  - `extra_ui_elements`
  - `primary_cta_not_clear`
  - `text_unreadable_or_garbled`
  - `affordances_unclear`
  - `layout_confusing`

**Verdict 規則（怎麼把指標變成單一 pass/fail）**

- **指令遵循必須 PASS**
- **版面與層次 ≥ 3**
- **文字渲染必須 PASS**
- **UI 真實感 ≥ 3**

任何一條沒過，整體就是 **FAIL**。

**範例 `TestCase` 集合（小但訊號強）**

先從幾個涵蓋常見 UI mockup 變化和邊界情況的 case 開始。
1.  **手機** **結帳畫面**（上面「結帳 UI mockup」的 prompt）
2.  **極簡版面**（只有 header、訂單總額、主要 CTA）：測稀疏元素下的版面和層次。
3.  **高密度層次**（訂單摘要、付款方式、優惠碼列、稅金、兩個次要動作）：測資訊量大時的層次。
4.  **精確的 CTA 文字**（主按鈕文字必須剛好是 “Place Order”）：測圖中文字渲染的保真度。
5.  **次要動作要存在**（同時有 “Edit Cart” 和 “Change payment method”）：測次要動作是否維持視覺上的從屬。
6.  **位置限制**（要求訂單總額緊貼在主要 CTA 上方）
7.  **平台保真度**（手機版 vs 桌面版）：測畫面外框和平台特徵。

**LLM-as-judge rubric prompt**

下面是對齊你現有 `LLMajRubricGrader` 的 judge prompt。它會回傳結構化的各項指標分數加整體 verdict。

你可以把 JSON schema 改成包含下面的欄位，沿用現有的 grader，或者想的話也可以每個指標拆成獨立的 grader。

#### System Prompt（UI mockup judge）


```python
PROMPT = """<core_mission>
Evaluate whether a generated UI mockup image represents a usable mobile checkout screen by checking screen type fidelity, layout/hierarchy, in-image text rendering, and UI affordance clarity.
</core_mission>

<role>
You are an expert evaluator of UI mockups used by designers and engineers. You care about structural correctness, readable UI text, clear hierarchy, and realistic rendering of UI elements.
</role>

<scope_constraints>
- Judge only against the provided instructions.
- Be strict about required UI elements and exact button/link text.
- Do NOT infer intent beyond what is explicitly stated.
- Do NOT reward creativity that violates constraints.
- Missing or extra required components are serious errors.
- If the UI intent or function is unclear, score conservatively.
</scope_constraints>

<metrics>
1) instruction_following: PASS/FAIL
2) layout_hierarchy: 0–5
3) in_image_text_rendering: PASS/FAIL
4) ui_affordance_rendering: 0–5
</metrics>

Evaluate EACH metric independently using the definitions below.
--------------------------------
1) Instruction Following (PASS / FAIL)
--------------------------------
PASS if:
- All required components are present.
- No unrequested components or features are added.
- The screen matches the requested type and product context.

FAIL if:
- Any required component is missing.
- Any unrequested component materially alters the UI.
- The screen does not match the requested type.

--------------------------------
2) Layout and Hierarchy (0–5)
--------------------------------
5: Layout is clear, coherent, and immediately usable.
   Hierarchy, grouping, spacing, and alignment are strong.

3: Generally understandable, but one notable hierarchy or layout issue
   that would require iteration.

0-2: Layout problems materially hinder usability or comprehension.

--------------------------------
3) In-Image Text Rendering (PASS / FAIL)
--------------------------------
PASS if:
- Text is readable, correctly spelled, and sensibly labeled.
- Font sizes reflect hierarchy (headings vs labels vs helper text).

FAIL if:
- Any critical text is unreadable, cut off, misspelled, or distorted.

--------------------------------
4) UI Affordance Rendering (0–5)
--------------------------------
5: Clearly resembles a real product interface that designers could use.

3: Marginally plausible; intent is visible but execution is weak.

0-2: Poor realism; interface would be difficult to use in practice.

<verdict_rules>
- Instruction Following must PASS.
- In-Image Text Rendering must PASS.
- Layout and Hierarchy score must be ≥ 3.
- UI Affordance Rendering score must be ≥ 3.

If ANY rule fails, the overall verdict is FAIL.
Do not average scores to determine the verdict.
</verdict_rules>

<output_constraints>
Return JSON only.
No extra text.
</output_constraints>
"""
```

#### 建議的 JSON 輸出


```python
{
  "verdict": "PASS",
  "instruction_following": True,
  "layout_hierarchy": 3,
  "in_image_text_rendering": True,
  "ui_affordance_rendering": 4,
  "reason": "..."
}
```

??? note "輸出"

    ```text
    {'verdict': 'PASS',
     'instruction_following': True,
     'layout_hierarchy': 3,
     'in_image_text_rendering': True,
     'ui_affordance_rendering': 4,
     'reason': '...'}
    ```



### UI Mockup 範例：Harness Setup

定義一個 UI mockup 的 test case、一次 model run，以及存在 `images/` 底下的輸出儲存。


```python
# Capture the UI judge prompt before PROMPT is overwritten later.
ui_judge_prompt = PROMPT

ui_prompt = """Generate a high-fidelity mobile checkout screen for an ecommerce app.
Orientation: portrait.
Screen type: checkout / order review.
Use the REQUIRED TEXT:
- Checkout
- Place Order
- Edit Cart
Constraints:
- Order total appears directly above the primary CTA.
- Primary CTA is the most visually prominent element.
- Do not include popups, ads, marketing copy, or extra screens.
- Do not include placeholder or lorem ipsum text.
"""

ui_criteria = """The image clearly depicts a mobile checkout screen.
All required sections are present and visually distinct.
UI elements look clickable/editable and follow common conventions.
Primary vs secondary actions are unambiguous.
No extra UI states, decorative noise, or placeholder text."""

ui_case = TestCase(
    id="ui_checkout_mockup",
    task_type="image_generation",
    prompt=ui_prompt,
    criteria=ui_criteria,
)

ui_run = ModelRun(
    label="gpt-image-1.5-ui",
    task_type="image_generation",
    params={
        "model": "gpt-image-1.5",
        "n": 1,
        "size": "1024x1024",
    },
)

ui_store = OutputStore(root=Path("../../images"))
```



### UI Mockup 範例：執行與評分

跑 harness，用 UI judge rubric 替 UI mockup 評分。


```python
ui_schema = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "instruction_following": {"type": "boolean"},
        "layout_hierarchy": {"type": "number"},
        "in_image_text_rendering": {"type": "boolean"},
        "ui_affordance_rendering": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "instruction_following",
        "layout_hierarchy",
        "in_image_text_rendering",
        "ui_affordance_rendering",
        "reason",
    ],
    "additionalProperties": False,
}


def parse_ui_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="instruction_following", value=bool(data["instruction_following"]), reason=""),
        Score(key="layout_hierarchy", value=float(data["layout_hierarchy"]), reason=""),
        Score(key="in_image_text_rendering", value=bool(data["in_image_text_rendering"]), reason=""),
        Score(key="ui_affordance_rendering", value=float(data["ui_affordance_rendering"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]

ui_grader = LLMajRubricGrader(
    key="ui_eval",
    system_prompt=ui_judge_prompt,
    content_builder=build_generation_judge_content,
    judge_model="gpt-5.2",
    json_schema_name="ui_mockup_eval",
    json_schema=ui_schema,
    result_parser=parse_ui_result,
)

ui_results = evaluate(
    cases=[ui_case],
    model_runs=[ui_run],
    graders=[ui_grader],
    output_store=ui_store,
)

ui_result = ui_results[0]
ui_result
```

??? note "輸出"

    ```text
    {'test_id': 'ui_checkout_mockup',
     'model_label': 'gpt-image-1.5-ui',
     'task_type': 'image_generation',
     'artifact_paths': ['../../images/gen_ui_checkout_mockup_gpt-image-1.5-ui_1769656414221_0.png'],
     'scores': {'instruction_following': True,
      'layout_hierarchy': 5.0,
      'in_image_text_rendering': True,
      'ui_affordance_rendering': 5.0,
      'verdict': 'PASS'},
     'reasons': {'instruction_following': '',
      'layout_hierarchy': '',
      'in_image_text_rendering': '',
      'ui_affordance_rendering': '',
      'verdict': 'All required text is present ("Checkout", "Edit Cart", "Place Order"). Screen clearly matches a mobile checkout/order review with distinct sections (Shipping Information, Payment Method, Items, Order Summary). Order Total appears directly above the primary CTA, and the "Place Order" button is the most visually prominent element. No popups, ads, marketing copy, or lorem/placeholder text. Text is crisp and readable with appropriate hierarchy. UI elements (back arrow, Edit Cart link, Change links, primary CTA) have clear, realistic affordances.'},
     'run_params': {'model': 'gpt-image-1.5', 'n': 1, 'size': '1024x1024'}}
    ```



### UI Mockup 結果

把 prompt、生成的圖和分數放進同一張 pandas 表格。


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gen_ui_checkout_mockup_gpt-image-1.5-ui_1769656414221_0.png" width="400"/> 

```python
render_result_table(case=ui_case, result=ui_result, title="UI Mockup: Prompt vs. Scores")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 行銷圖生成

行銷圖是「高風險的 text-to-image」workflow：輸出是要上線的（或至少要當成可能上線的東西來審）。一張傳單可以看起來「很美」，但文案錯了、優惠不清楚、或版面把關鍵訊息藏起來，照樣算失敗。

這一節用咖啡店的例子示範怎麼評估**傳單生成**。目標是讓評估貼近真實 workflow：行銷或設計師拿到這個輸出，只要少量修改就能用嗎？

範例：

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/sample_flyer.png" width="400"/> 

**為什麼行銷圖 eval 不一樣**

行銷圖結合了三種難題：

1.  精確的文字要求（gating）
2.  版面加層次（graded）
3.  風格加品牌一致性（graded，另可加人工偏好）

**範例任務：生成咖啡店傳單**

- 情境：一家在地咖啡店需要一張傳單，宣傳限時飲品和平日優惠。
- Prompt 建議：明確指定交付物、必要文案、層次，以及不准出現的多餘內容。
- 實作：完整的 prompt 和評分標準在下面的 harness setup code cell 裡（`coffee_generation_prompt` 和 `coffee_criteria`）。

#### 要評什麼（實用指標）：

混用 gate（硬性限制）和分級訊號（品質）。

##### 1) 指令遵循：Pass / Fail（gate）

行銷素材只要不符合規格就很快失敗。

**PASS 條件**

- 交付物類型正確：明確是傳單/海報版面（不是 UI 畫面，也不是隨便一張照片）。
- 必要元件都在（headline、subheadline、優惠、CTA、footer，加主視覺圖）。

**FAIL 條件**

- 缺任何必要元件，或輸出認不出是傳單。

##### 2) 文字渲染正確性：Pass / Fail（gate）

這通常是 production 裡的頭號失敗模式。

**PASS 條件**

- 所有必要的文字字串都存在而且完全正確（拼字、標點、大小寫、符號）。
- 文字可讀（沒有糊掉、被裁切、扭曲或重疊）。

**FAIL 條件**

- 任何必要文字錯誤、缺漏或不可讀，或出現任何多餘的文字。

提醒：如果你的 workflow 要求「文案一字不差」，就把它當硬性 gate，不要用平均把它蓋掉。

##### 3) 版面與層次：0–5

衡量傳單能不能一眼傳達清楚。

**看什麼：**

- 優先順序清楚：headline 最大、subheadline 輔助、優惠突出、footer 次要。
- 對齊和間距看起來是刻意的（沒有擠成一團，也沒有亂飄的元素）。
- 閱讀順序明確。

##### 4) 風格與品牌契合度：0–5

衡量是否符合要求的「調性」，並避開不符品牌的樣子。

**看什麼：**

- 溫暖、舒適、極簡，精品咖啡的視覺語言。
- 配色和字體感一致（不要多種互相衝突的風格）。
- prompt 要求寫實照片時，避免卡通插畫。

##### 5) 視覺品質與 artifact 嚴重程度：0–5

傳單可以「內容正確」但視覺壞掉，照樣不能用。

**看什麼：**

- 沒有變形的物件、壞掉的手/杯子、融化的奶泡質感，文字周圍沒有怪異的 artifact。
- 背景紋理要淡（不要跟文案搶）。
- 主視覺看起來好吃而且合理。

##### 6) 人類回饋（快速又高效益）

UI 的「可用性清晰度」是人類最能加值的地方。保持輕量，聚焦在互動意圖。

- Rubric 標註（快）：
  - 你會用這個 mockup 來迭代真實的產品畫面嗎？（Y/N）
  - 如果 N，為什麼？（缺區塊、動作按鈕不清楚、文字看不懂、版面混亂等）
  - 整體可用性清晰度：1–5
- 常見失敗標籤（用來 debug 和迭代）：
  - `wrong_screen_type`
  - `missing_required_section`
  - `extra_ui_elements`
  - `primary_cta_not_clear`
  - `text_unreadable_or_garbled`
  - `affordances_unclear`
  - `layout_confusing`

**Verdict 規則（怎麼把指標變成單一 pass/fail）**

簡單而嚴格的規則通常很好用：

- **指令遵循必須 PASS**
- **文字渲染必須 PASS**
- **版面與層次 ≥ 3**
- **風格與品牌契合度 ≥ 3**
- **視覺品質 ≥ 3**

任何一條沒過，整體就是 **FAIL**。  
（不要用平均分數去蓋過文字正確性。）

**範例 `TestCase` 集合（小但訊號強）**

先從約 8 到 12 個 case 開始，涵蓋常見的傳單變化和邊界情況。

1. 季節性活動（上面的 “Winter Latte Week” prompt）
2. 極少文字（只有 2 行加 logo 加營業時間）：測稀疏版面
3. 資訊密集（菜單亮點、優惠、兩個 CTA）：測資訊量大時的層次
4. 嚴格禁止多餘文字：測模型會不會憑空塞填充文案
5. 精確標點（“20% OFF • Mon–Thu”）：測符號保真度
6. 兩個優惠（“BOGO Tuesdays” 加 “Happy Hour 2–4”）：測多徽章版面
7. 色系限制（「只用奶油色、深棕、霧橘」）
8. 無障礙版本（高對比、大字、簡單背景）

**LLM-as-judge rubric prompt**

下面是對齊你現有 `LLMajRubricGrader` 的 judge prompt。它會回傳結構化的各項指標分數加整體 verdict。

你可以把 JSON schema 改成包含下面的欄位，沿用現有的 grader，或者想的話也可以每個指標拆成獨立的 grader。


```python
PROMPT = """<core_mission>
Evaluate whether a generated marketing flyer is usable for a real coffee shop
promotion by checking instruction adherence, exact text correctness, layout clarity,
style fit, and artifact severity.
</core_mission>

<role>
You are an expert evaluator of marketing design deliverables.
You care about correctness, readability, hierarchy, and brand-fit.
You do NOT reward creativity that violates constraints.
</role>

<scope_constraints>
- Judge ONLY against the provided prompt and criteria.
- Be strict about required copy: spelling, punctuation, casing, and symbols must match exactly.
- Extra or missing text is a serious error.
- If unsure, score conservatively (lower score).
</scope_constraints>

<metrics>
1) instruction_following: PASS/FAIL
2) text_rendering: PASS/FAIL
3) layout_hierarchy: 0-5
4) style_brand_fit: 0-5
5) visual_quality: 0-5

Use these anchors:
Layout/Hierarchy 5 = instantly readable; clear order; strong spacing/alignment.
3 = understandable but needs iteration (one clear issue).
0-2 = confusing or hard to parse.

Style/Brand Fit 5 = clearly matches requested vibe; consistent; not off-style.
3 = generally matches but with noticeable mismatch.
0-2 = wrong style (e.g. cartoonish when photo-real requested).

Visual Quality 5 = clean; no distracting artifacts; hero image coherent.
3 = minor artifacts but still usable.
0-2 = obvious artifacts or distortions that break usability.
</metrics>

<verdict_rules>
Overall verdict is FAIL if:
- instruction_following is FAIL, OR
- text_rendering is FAIL, OR
- any of layout_hierarchy/style_brand_fit/visual_quality is < 3.
Otherwise PASS.
</verdict_rules>

<output_constraints>
Return JSON only.
No extra text.
</output_constraints>
"""
```

#### 建議的 JSON 輸出


```python
{
  "verdict": "PASS",
  "instruction_following": True,
  "text_rendering": True,
  "layout_hierarchy": 4,
  "style_brand_fit": 4,
  "visual_quality": 3,
  "reason": "..."
}
```

??? note "輸出"

    ```text
    {'verdict': 'PASS',
     'instruction_following': True,
     'text_rendering': True,
     'layout_hierarchy': 4,
     'style_brand_fit': 4,
     'visual_quality': 3,
     'reason': '...'}
    ```



### 咖啡範例：Harness Setup

定義一個行銷傳單的 test case、一次 model run，以及輸出儲存。


```python
# Run the harness for a single coffee flyer generation case.

coffee_generation_prompt = """Create a print-ready vertical A4 flyer for a coffee shop called Sunrise Coffee.
Use a warm, cozy, minimal specialty coffee aesthetic (not cartoonish).
Required text (must be exact):
- WINTER LATTE WEEK
- Try our Cinnamon Oat Latte
- 20% OFF - Mon-Thu
- Order Ahead
- 123 Market St - 7am-6pm
Do not include any other words, prices, URLs, or QR codes.
"""

coffee_criteria = """All required text appears exactly as written and is legible.
Layout reads clearly: shop name -> headline -> subheadline -> offer -> CTA -> footer.
Style matches warm, cozy, specialty coffee and is not cartoonish.
No extra text, watermarks, or irrelevant UI-like elements."""

coffee_case = TestCase(
    id="coffee_flyer_generation",
    task_type="image_generation",
    prompt=coffee_generation_prompt,
    criteria=coffee_criteria,
)

coffee_run = ModelRun(
    label="gpt-image-1.5",
    task_type="image_generation",
    params={
        "model": "gpt-image-1.5",
        "n": 1,
        "size": "1024x1024",
    },
)

# Save artifacts under the repo images/ folder so they render on the site.
coffee_store = OutputStore(root=Path("../../images"))
```

### 咖啡範例：執行與評分

跑 harness，用行銷 judge rubric 替輸出評分。


```python
# Use the prebuilt graders + evaluate helpers with a structured marketing schema.
from openai import OpenAI

marketing_schema = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "instruction_following": {"type": "boolean"},
        "text_rendering": {"type": "boolean"},
        "layout_hierarchy": {"type": "number"},
        "style_brand_fit": {"type": "number"},
        "visual_quality": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "instruction_following",
        "text_rendering",
        "layout_hierarchy",
        "style_brand_fit",
        "visual_quality",
        "reason",
    ],
    "additionalProperties": False,
}


def parse_marketing_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="instruction_following", value=bool(data["instruction_following"]), reason=""),
        Score(key="text_rendering", value=bool(data["text_rendering"]), reason=""),
        Score(key="layout_hierarchy", value=float(data["layout_hierarchy"]), reason=""),
        Score(key="style_brand_fit", value=float(data["style_brand_fit"]), reason=""),
        Score(key="visual_quality", value=float(data["visual_quality"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]


marketing_grader = LLMajRubricGrader(
    key="marketing_eval",
    system_prompt=PROMPT,
    content_builder=build_generation_judge_content,
    judge_model="gpt-5.2",
    json_schema_name="marketing_flyer_eval",
    json_schema=marketing_schema,
    result_parser=parse_marketing_result,
)

coffee_results = evaluate(
    cases=[coffee_case],
    model_runs=[coffee_run],
    graders=[marketing_grader],
    output_store=coffee_store,
)

coffee_result = coffee_results[0]

# Simple alternative: exact text-rendering check via OCR-style extraction.
REQUIRED_TEXT = {
    "WINTER LATTE WEEK",
    "Try our Cinnamon Oat Latte",
    "20% OFF • Mon–Thu",
    "Order Ahead",
    "123 Market St • 7am–6pm",
}


def extract_text_from_flyer(image_path: str | Path, model: str = "gpt-5.2") -> list[str]:
    judge_client = client if "client" in globals() else OpenAI()
    image_url = image_to_data_url(Path(image_path))

    instructions = (
        "List every piece of text visible in this flyer image. "
        "Return one line per text item and preserve capitalization, punctuation, and spacing exactly."
    )

    response = judge_client.responses.create(
        model=model,
        instructions=instructions,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": image_url},
                ],
            }
        ],
    )

    return [line.strip() for line in (response.output_text or "").splitlines() if line.strip()]


coffee_image_path = Path(coffee_result["artifact_paths"][0])
extracted_lines = extract_text_from_flyer(coffee_image_path)

missing = sorted(REQUIRED_TEXT - set(extracted_lines))
extra = sorted(set(extracted_lines) - REQUIRED_TEXT)
text_rendering_pass = not missing and not extra

parts = []
if missing:
    parts.append("missing: " + ", ".join(missing))
if extra:
    parts.append("extra: " + ", ".join(extra))
text_rendering_reason = "; ".join(parts) if parts else "Exact text match."

# Keep both: the judge's text_rendering and the OCR exact-match result.
text_rendering_judge_score = coffee_result["scores"].get("text_rendering")
text_rendering_judge_reason = coffee_result["reasons"].get("text_rendering", "")

coffee_result["scores"]["text_rendering_judge"] = text_rendering_judge_score
coffee_result["reasons"]["text_rendering_judge"] = text_rendering_judge_reason

coffee_result["scores"]["text_rendering_ocr"] = text_rendering_pass
coffee_result["reasons"]["text_rendering_ocr"] = text_rendering_reason

coffee_result
```

??? note "輸出"

    ```text
    {'test_id': 'coffee_flyer_generation',
     'model_label': 'gpt-image-1.5',
     'task_type': 'image_generation',
     'artifact_paths': ['../../images/gen_coffee_flyer_generation_gpt-image-1.5_1769657762450_0.png'],
     'scores': {'instruction_following': True,
      'text_rendering': True,
      'layout_hierarchy': 5.0,
      'style_brand_fit': 5.0,
      'visual_quality': 5.0,
      'verdict': 'PASS',
      'text_rendering_judge': True,
      'text_rendering_ocr': False},
     'reasons': {'instruction_following': '',
      'text_rendering': '',
      'layout_hierarchy': '',
      'style_brand_fit': '',
      'visual_quality': '',
      'verdict': 'All required lines appear and match exactly (including casing, hyphen/en-dash, and punctuation), with no extra words, prices, URLs, or QR codes. Text is crisp and legible. Hierarchy follows the requested order: shop name at top, then headline, subheadline, offer, CTA, and footer address/hours. Visual style is warm, cozy, minimal specialty coffee with a realistic latte photo (not cartoonish). No visible watermarks, UI elements, or distracting artifacts; overall print-flyer quality is clean.',
      'text_rendering_judge': '',
      'text_rendering_ocr': 'missing: 123 Market St • 7am–6pm, 20% OFF • Mon–Thu; extra: 123 Market St - 7am-6pm, 20% OFF - Mon-Thu, SUNRISE COFFEE'},
     'run_params': {'model': 'gpt-image-1.5', 'n': 1, 'size': '1024x1024'}}
    ```



### 傳單生成結果

把生成的圖、prompt 和分數並排顯示。


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gen_coffee_flyer_generation_gpt-image-1.5_1769657762450_0.png" width="400"/> 

```python
render_result_table(case=coffee_case, result=coffee_result, title="Coffee Flyer: Prompt vs. Scores")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

#### 另一種方法：圖轉文字加文字比對

另一種評估方式是把問題換到另一個模態：文字。做法是先用 vision 模型把圖片轉成很詳細的文字描述，再拿生成出來的文字跟預期文字比對。

這個方法特別適合 OCR 類的 workflow。例如你可以用 vision 模型從生成的傳單抽出文字，再把結果的每一行直接跟必要文案比對，確認正確又完整。

```python
import pandas as pd

coffee_image_path = Path(coffee_result["artifact_paths"][0])
extracted_lines = extract_text_from_flyer(coffee_image_path)

required_lines = sorted(REQUIRED_TEXT)
required_set = set(required_lines)
extracted_set = set(extracted_lines)

missing = sorted(required_set - extracted_set)
extra = sorted(extracted_set - required_set)

text_rendering_df = pd.DataFrame(
    {
        "text_rendering_score": [coffee_result["scores"].get("text_rendering")],
        "missing_text": ["\n".join(missing) or "(none)"],
        "extra_text": ["\n".join(extra) or "(none)"],
        "extracted_text": ["\n".join(extracted_lines) or "(no text extracted)"],
    }
)

text_rendering_df
```

??? note "輸出"

    ```text
       text_rendering_score                                missing_text  \
    0                  True  123 Market St • 7am–6pm\n20% OFF • Mon–Thu   

                                              extra_text  \
    0  123 Market St - 7am-6pm\n123 Market St - 7am-6...   

                                          extracted_text  
    0  SUNRISE COFFEE\nWINTER LATTE WEEK\nTry our Cin...
    ```

## 圖像編輯 Evals


### 虛擬試穿（Virtual Try-On）

虛擬試穿（VTO）是一種**圖像編輯** workflow：給一張**人物照片**（自拍或模特兒）和一個**服飾參考**（商品照和/或描述），生成一張衣服看起來**自然穿在身上**的輸出，同時保持人物的身份、姿勢和場景不變。

**為什麼 VTO eval 不一樣**

跟「創意」類的編輯不同，VTO 看的是**保真度加保留性**：

- **保留穿著者**（臉部身份、體型、姿勢）
- **保留商品**（顏色、圖案、logo、材質線索）
- **只改必要的部分**（局部性/保留性）
- **看起來物理上合理**（遮擋、光線、垂墜、皺褶）

範例輸入：

| Full Body | Item 1 |
|:------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/woman_in_museum.png)  | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jacket.png) |
| Item 2 | Item 3 |
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/tank_top.png) | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/boots.png) |

輸出圖片： 

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/outfit.png" width="400"/> 

#### 要評什麼（實用指標）：

##### 1) 把 VTO 當成多參考圖的編輯任務

每個 test case 都要存：

- **輸入的人物圖**（自拍/模特兒）
- **商品參考**（型錄圖、平拍、人台，或有的話「穿著」的參考圖）
- 選用但效益很高：
  - **Mask**：可編輯區域、衣服區域、頭髮/手的遮擋物
  - **Metadata**：類別（上衣/下身/外套）、期望版型（oversized/修身）、色系、長度
  - **編輯指令**：「穿上*這件一模一樣的外套*，不要改變背景或臉。」

這樣 graders 可以拿**輸出同時對照兩個輸入**（人物加商品），而不只是問「好不好看？」

##### 2) 分級指標（只用這三個）

用這些 **0–5** 分來替模型排名和追蹤進步。它們要**分開**（不要在 grader 裡平均），想要 gate 的話，在外面用 verdict 規則處理。

##### A) 臉部相似度（輸出 vs 自拍）：0–5

衡量輸出是不是保留了*同一個人*（身份），而不只是「一張合理的臉」。

- **5**：明顯是同一個人；關鍵五官沒變；沒有明顯的年齡/種族/風格偏移；表情若有變化也很小而且寫實。
- **4**：同一個人；只有近看才會發現的細微差異（形狀/質感稍微平滑、眼睛/嘴巴略有偏移）。
- **3**：大致是同一個人，但至少有一處明顯的身份偏移（五官比例、下顎線、眼睛、鼻子），會降低使用者的信任。
- **2**：身份嚴重偏移；看起來像另一個人或臉被大幅改過。
- **1**：嚴重損壞（臉融化/模糊）或明顯是不同的人。
- **0**：臉不見、無法辨識或被替換。

看什麼：

- 臉部幾何一致（眼鼻嘴間距、下顎線、顴骨）
- 皮膚質感寫實，沒有因「美顏濾鏡」而失去身份
- 沒被要求的話，不要出現多餘的妝容/年齡/風格變化

##### B) 服裝保真度（輸出 vs 提供的商品）：0–5

衡量輸出的衣服是否符合使用者選的*那個特定*商品參考。

- **5**：商品跟參考圖非常接近：類別、色系、圖案/印花、材質線索和關鍵細節（logo、接縫、領口、口袋）都對。
- **4**：明顯是同一件；有 1 到 2 個小偏差（logo 稍糊、色相略偏、細節稍微簡化）。
- **3**：大致正確，但有明顯的不一致（圖案比例不對、材質看起來不同、關鍵設計元素缺漏或多出來）。
- **2**：多處不一致；可能是不同款式或不同商品。
- **1**：商品類別錯誤，或視覺身份嚴重不符。
- **0**：沒穿上衣服、衣服消失，或被換成不相干的衣服。

看什麼：

- 顏色/圖案是否正確（尤其是條紋、格紋、小重複圖案）
- Logo/文字完整（不能憑空冒出字母）
- 結構細節（領口、袖子、下擺、開合方式）

##### C) 體型保留（輸出 vs 自拍）：0–5

衡量模型有沒有保留穿著者的體型、姿勢和比例，**一般服裝效果以外**的部分不該變（例如寬鬆的衣服會改變輪廓，但不該重塑身體結構）。

- **5**：體型比例和姿勢都保留；衣服自然貼合，沒有扭曲軀幹/四肢。
- **4**：有小幅、合理而且符合衣服的輪廓變化；沒有明顯的解剖變形。
- **3**：有明顯的重塑（腰/臀/肩/四肢），感覺有點「AI 風格化」或跟輸入的身體不一致。
- **2**：嚴重扭曲（四肢拉長、關節錯位、軀幹壓縮），在產品使用上無法接受。
- **1**：嚴重的解剖變形（多出或缺少四肢、身體區域融化）。
- **0**：身體無法辨識或根本壞掉。

看什麼：

- 肩寬/臀寬相對輸入是否一致
- 四肢長度和關節位置是否穩定（手肘、膝蓋、手腕）
- 沒有「瘦身」或「膨脹」的 artifact

如果你想要單一的整體 pass/fail，常見的規則是：

- 任一指標 ≤ 2 就 **Fail**
- 所有指標 ≥ 3 才 **Pass**  
  （電商關鍵流程可以再要求服裝保真度 ≥ 4。）

##### 3) 人類回饋：簡單但要一致

人最擅長判斷「我會在購物流程裡信任這個嗎？」

用兩種標註：

- **Rubric 標註**（快、結構化）：
  - 身份有保留嗎？（Y/N）
  - 衣服跟參考圖一致嗎？（Y/N 加哪裡不對）
  - 有不好的 artifact 嗎？（無/輕微/嚴重）
  - 整體能用在電商嗎？（Y/N）
- **Pairwise 偏好**（A vs B）：
  - 哪一個輸出更忠於商品，同時不改變人物？

要定期做**校準**：留一小組「錨點」範例，讓標註者重新評分，防止標準飄移。



### 虛擬試穿範例：Harness Setup

用 `images/` 裡現有的圖片當人物和服飾的參考。


```python
vto_person_path = Path("../../images/base_woman.png")
vto_garment_path = Path("../../images/jacket.png")

vto_prompt = """Put the person in the first image into the jacket shown in the second image.
Keep the person's face, pose, body shape, and background unchanged.
Preserve the garment's color, pattern, and key details.
Do not add extra accessories, text, or new elements."""

vto_criteria = """The output preserves the same person and background.
The jacket matches the reference garment closely.
Body shape and pose remain consistent outside normal garment effects.
The result looks physically plausible."""

vto_case = TestCase(
    id="vto_jacket_tryon",
    task_type="image_editing",
    prompt=vto_prompt,
    criteria=vto_criteria,
    image_inputs=ImageInputs(image_paths=[vto_person_path, vto_garment_path]),
)

vto_run = ModelRun(
    label="gpt-image-1.5-vto",
    task_type="image_editing",
    params={
        "model": "gpt-image-1.5",
        "n": 1,
    },
)

vto_store = OutputStore(root=Path("../../images"))
```



### 虛擬試穿範例：執行與評分

定義對齊 VTO 指標的 judge prompt，然後跑 harness。


```python
vto_judge_prompt = """<core_mission>
Evaluate whether a virtual try-on edit preserves the person while accurately applying the reference garment.
</core_mission>

<role>
You are an expert evaluator of virtual try-on outputs.
You focus on identity preservation, garment fidelity, and body-shape preservation.
</role>

<metrics>
1) facial_similarity: 0-5
2) outfit_fidelity: 0-5
3) body_shape_preservation: 0-5
</metrics>

<verdict_rules>
FAIL if any metric <= 2.
PASS if all metrics >= 3.
</verdict_rules>

<output_constraints>
Return JSON only with the fields specified in the schema.
</output_constraints>
"""

vto_schema = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "facial_similarity": {"type": "number"},
        "outfit_fidelity": {"type": "number"},
        "body_shape_preservation": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "facial_similarity",
        "outfit_fidelity",
        "body_shape_preservation",
        "reason",
    ],
    "additionalProperties": False,
}


def parse_vto_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="facial_similarity", value=float(data["facial_similarity"]), reason=""),
        Score(key="outfit_fidelity", value=float(data["outfit_fidelity"]), reason=""),
        Score(key="body_shape_preservation", value=float(data["body_shape_preservation"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]

vto_grader = LLMajRubricGrader(
    key="vto_eval",
    system_prompt=vto_judge_prompt,
    content_builder=build_editing_judge_content,
    judge_model="gpt-5.2",
    json_schema_name="vto_eval",
    json_schema=vto_schema,
    result_parser=parse_vto_result,
)

vto_results = evaluate(
    cases=[vto_case],
    model_runs=[vto_run],
    graders=[vto_grader],
    output_store=vto_store,
)

vto_result = vto_results[0]
vto_result
```

??? note "輸出"

    ```text
    {'test_id': 'vto_jacket_tryon',
     'model_label': 'gpt-image-1.5-vto',
     'task_type': 'image_editing',
     'artifact_paths': ['../../images/edit_vto_jacket_tryon_gpt-image-1.5-vto_1769658750053_0.png'],
     'scores': {'facial_similarity': 5.0,
      'outfit_fidelity': 4.0,
      'body_shape_preservation': 4.0,
      'verdict': 'PASS'},
     'reasons': {'facial_similarity': '',
      'outfit_fidelity': '',
      'body_shape_preservation': '',
      'verdict': 'The edited output preserves the same face, hairstyle, pose, and plain studio background. The applied jacket closely matches the reference: camel/beige color, notch lapels, single-breasted look with dark buttons, and flap pockets are present and placed plausibly. Minor deviations include slightly different button count/placement and subtle differences in lapel/hem shaping compared to the flat lay. Body proportions and stance remain consistent, with only natural silhouette changes from wearing a structured blazer.'},
     'run_params': {'model': 'gpt-image-1.5', 'n': 1}}
    ```

### 虛擬試穿：選用的 Code Interpreter 裁切工具

如果你需要更細的證據（logo、接縫、合身度、臉部細節），可以再跑一個第二層的 judge，用 Code Interpreter 的 `crop` 工具放大特定區域。這適合用來近距離檢查服裝保真度和身份保留。

```python
vto_output_path = Path(vto_result["artifact_paths"][0])

instructions = """
Tools available:
- crop(image_id, x1, y1, x2, y2): Use to zoom into a specific image's region. Coordinates are integer pixels relative to the top-left of the CURRENT view of that image. Use as few precise crops as necessary to gather evidence.
    - When using crop(image_id, x1, y1, x2, y2), ensure that x2 > x1 and y2 > y1. The coordinates must define a valid rectangle: x1 (left, inclusive), y1 (top, inclusive), x2 (right, exclusive), y2 (bottom, exclusive), with x2 strictly greater than x1 and y2 strictly greater than y1. If you are unsure, double-check your coordinates before cropping to avoid errors.

Images provided:
- Up to 5 user reference photos (ref_1..ref_5) for identity/baseline body context
- 1 clothing-only image (clothing)
- 1 reconstruction image (recon)

Your goals:
1) Judge similarity between the clothing-only image and how it appears on the user in the reconstruction.
2) Judge identity realism (face/hair/skin) vs. user reference photos.
3) Judge overall realism (lighting, shadows, artifacts).

IMPORTANT:
- Use the crop tool when you need more detail. After crop, a new grid overlay is returned for that image.
- You may use the crop tool as many times as needed to gather evidence.
- When confident, produce the final STRICT JSON only. No extra text.
"""
judge_client = client if "client" in globals() else OpenAI()
response_crop = judge_client.responses.create(
    model="gpt-5.2",
    instructions=instructions,
    tools=[
        {
            "type": "code_interpreter",
            "container": {"type": "auto", "memory_limit": "4g"},
        }
    ],
    input=[
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Order: ref_1 (person), clothing (garment reference), recon (try-on output).",
                },
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(vto_person_path),
                },
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(vto_garment_path),
                },
                {
                    "type": "input_image",
                    "image_url": image_to_data_url(vto_output_path),
                },
            ],
        }
    ],
)

response_crop
```

??? note "輸出"

    ```text
    Response(id='resp_03756a1c45c8427000697ad91445ec8196a58b39ee7e0b05b1', created_at=1769658644.0, error=None, incomplete_details=None, instructions="\nTools available:\n- crop(image_id, x1, y1, x2, y2): Use to zoom into a specific image's region. Coordinates are integer pixels relative to the top-left of the CURRENT view of that image. Use as few precise crops as necessary to gather evidence.\n    - When using crop(image_id, x1, y1, x2, y2), ensure that x2 > x1 and y2 > y1. The coordinates must define a valid rectangle: x1 (left, inclusive), y1 (top, inclusive), x2 (right, exclusive), y2 (bottom, exclusive), with x2 strictly greater than x1 and y2 strictly greater than y1. If you are unsure, double-check your coordinates before cropping to avoid errors.\n\nImages provided:\n- Up to 5 user reference photos (ref_1..ref_5) for identity/baseline body context\n- 1 clothing-only image (clothing)\n- 1 reconstruction image (recon)\n\nYour goals:\n1) Judge similarity between the clothing-only image and how it appears on the user in the reconstruction.\n2) Judge identity realism (face/hair/skin) vs. user reference photos.\n3) Judge overall realism (lighting, shadows, artifacts).\n\nIMPORTANT:\n- Use the crop tool when you need more detail. After crop, a new grid overlay is returned for that image.\n- You may use the crop tool as many times as needed to gather evidence.\n- When confident, produce the final STRICT JSON only. No extra text.\n", metadata={}, model='gpt-5.2-2025-12-11', object='response', output=[ResponseCodeInterpreterToolCall(id='ci_03756a1c45c8427000697ad91aaf108196974c45daf37a9a18', code="from PIL import Image, ImageOps\nimg1=Image.open('/mnt/data/143ba8edc474910b395d0d44e2f06a9d-image.png')\nimg2=Image.open('/mnt/data/ababce34a72604310f9dac11e9e5f00f-image.png')\nimg3=Image.open('/mnt/data/6c920ec973b3b1abb80da8b29ee5aa3e-image.png')\nimg1.size, img2.size, img3.size\n", container_id='cntr_697ad91842dc8193a9e214852cbb3fda02ddf8755852a20c', outputs=None, status='completed', type='code_interpreter_call'), ResponseCodeInterpreterToolCall(id='ci_03756a1c45c8427000697ad93101b48196a090b8acf49e7948', code="import matplotlib.pyplot as plt\nplt.figure(figsize=(12,6))\nfor i,img in enumerate([img1,img2,img3],1):\n    plt.subplot(1,3,i); plt.imshow(img); plt.axis('off'); plt.title(i)\nplt.show()\n", container_id='cntr_697ad91842dc8193a9e214852cbb3fda02ddf8755852a20c', outputs=None, status='completed', type='code_interpreter_call'), ResponseCodeInterpreterToolCall(id='ci_03756a1c45c8427000697ad94bf50481969ec6383dc9bd0a40', code="import numpy as np, matplotlib.pyplot as plt\n# crop face regions\nface1=img1.crop((70,20,230,140))\nface3=img3.crop((330,70,690,330))\nplt.figure(figsize=(8,4))\nplt.subplot(1,2,1); plt.imshow(face1); plt.axis('off'); plt.title('ref face')\nplt.subplot(1,2,2); plt.imshow(face3); plt.axis('off'); plt.title('recon face')\nplt.show()\n", container_id='cntr_697ad91842dc8193a9e214852cbb3fda02ddf8755852a20c', outputs=None, status='completed', type='code_interpreter_call'), ResponseCodeInterpreterToolCall(id='ci_03756a1c45c8427000697ad9522568819681f59d41d921f102', code="# crop blazer from clothing and recon for comparison\ncloth=img2.crop((40,40,260,410))\nrecon_blazer=img3.crop((250,250,800,1100))\nplt.figure(figsize=(10,4))\nplt.subplot(1,2,1); plt.imshow(cloth); plt.axis('off'); plt.title('clothing')\nplt.subplot(1,2,2); plt.imshow(recon_blazer); plt.axis('off'); plt.title('recon blazer')\nplt.show()\n", container_id='cntr_697ad91842dc8193a9e214852cbb3fda02ddf8755852a20c', outputs=None, status='completed', type='code_interpreter_call'), ResponseOutputMessage(id='msg_03756a1c45c8427000697ad958266c8196ab64e9c75379f4ce', content=[ResponseOutputText(annotations=[AnnotationContainerFileCitation(container_id='cntr_697ad91842dc8193a9e214852cbb3fda02ddf8755852a20c', end_index=0, file_id='cfile_697ad956d5d4819194b112d8f80b8a9d', filename='cfile_697ad956d5d4819194b112d8f80b8a9d.png', start_index=0, type='container_file_citation')], text='{\n  "clothing_similarity": {\n    "score": 0.9,\n    "notes": [\n      "Blazer color matches well (camel/tan) with similar fabric look.",\n      "Key design elements align: notch lapels, two-button front with dark buttons, flap pockets, and overall single-breasted silhouette.",\n      "Proportions look consistent (hip-length, straight hem, structured shoulders).",\n      "Minor differences: lapel/edge sharpness and pocket flap geometry look slightly simplified in the try-on."\n    ]\n  },\n  "identity_realism": {\n    "score": 0.72,\n    "notes": [\n      "Overall face shape, hair color/part, and general look are fairly consistent with the reference.",\n      "Some identity drift: facial details (eyes/nose/mouth definition) appear smoother/idealized in the try-on compared to the reference.",\n      "Skin texture is more airbrushed in the try-on; less natural micro-detail."\n    ]\n  },\n  "overall_realism": {\n    "score": 0.84,\n    "notes": [\n      "Lighting and shadows are mostly coherent with the studio background; blazer shading reads plausibly on-body.",\n      "Good garment-body integration at shoulders and torso; sleeve placement looks natural.",\n      "Small AI artifacts: slightly softened/blurred edges around lapels and pocket areas; fine fabric texture is reduced."\n    ]\n  }\n}', type='output_text', logprobs=[])], role='assistant', status='completed', type='message')], parallel_tool_calls=True, temperature=1.0, tool_choice='auto', tools=[CodeInterpreter(container=CodeInterpreterContainerCodeInterpreterToolAuto(type='auto', file_ids=None, memory_limit=None), type='code_interpreter')], top_p=0.98, background=False, conversation=None, max_output_tokens=None, max_tool_calls=None, previous_response_id=None, prompt=None, prompt_cache_key=None, prompt_cache_retention=None, reasoning=Reasoning(effort='none', generate_summary=None, summary=None), safety_identifier=None, service_tier='default', status='completed', text=ResponseTextConfig(format=ResponseFormatText(type='text'), verbosity='medium'), top_logprobs=0, truncation='disabled', usage=ResponseUsage(input_tokens=5397, input_tokens_details=InputTokensDetails(cached_tokens=0), output_tokens=717, output_tokens_details=OutputTokensDetails(reasoning_tokens=417), total_tokens=6114), user=None, billing={'payer': 'developer'}, completed_at=1769658722, frequency_penalty=0.0, presence_penalty=0.0, store=True)
    ```



### 虛擬試穿 Eval 結果

把編輯結果和 VTO 分數放進同一張 pandas 表格。


| Full Body | Item 1 |
|:------------:|:--------------:|
| ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/base_woman.png)  | ![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/jacket.png) |

編輯後的圖片：

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/edit_vto_jacket_tryon_gpt-image-1.5-vto_1769658750053_0.png" width="400"/> 


```python
render_result_table(case=vto_case, result=vto_result, title="Virtual Try-On: Prompt vs. Scores")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### Logo 編輯

Logo 編輯是高精度的圖像編輯任務。給一個**既有的 logo** 和一個**範圍很窄的指令**，模型必須精確套用要求的修改，同時把其他東西完美保留。跟創意設計不同，logo 編輯通常只有一個正確答案，任何偏差，即使很細微，都算失敗。


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/logo_sample.png" width="400"/> 


**為什麼 Logo 編輯 eval 不一樣**：

Logo 編輯看的是精確性、局部性和保留性，不是視覺吸引力：

- 保留原始素材的身份
- 保留所有沒要改的文字、幾何、間距和樣式
- 只改明確指定的區域
- 要做到字元層級的正確，對偏移零容忍

小錯誤的風險被放大。一個字母變形、一個數字改掉，或修改溢出到指定區域外，都可能破壞品牌完整性，造成下游的重工。

**範例任務：**

- 輸入：logo 圖片加 mask 或區域描述
- 任務：「把年份從 2024 改成 2026」、「把 C 換成 S」、「加上 TM」

#### 要評什麼（實用指標）：

##### 1) 把 logo 編輯當成有限制的單一參考任務

每個 test case 都要存：

- **輸入的 logo 圖片**
- **編輯指令**，範圍要明確
- 選用但效益很高：
  - 定義哪裡可以改的 mask 或區域描述
  - 用來精確比對的預期目標文字或符號
  - **Metadata**：字型、字級或顏色

Grader 應該把輸出直接跟原始 logo 比較。

##### 2) 分級指標

用這些 **0–5** 分來替模型排名和追蹤進步。分數是套用在所有要求的步驟上，不是逐步驟打分，所以只完成一部分會以可控、可解釋的方式被扣分。

##### A) 編輯意圖正確性：0–5

衡量每個要求的編輯步驟是否都正確套用在正確的目標上。

- **5**：所有編輯步驟都完全照規格套用。每一步的字元層級準確度都完美。
- **4**：所有步驟都正確套用；只有近看才看得出極輕微的瑕疵。
- **3**：所有步驟都有套用，但至少有一步在清晰度或精確度上有明顯劣化。
- **2**：大部分步驟正確，但有一個以上的步驟含有明顯錯誤。
- **1**：有一個以上的步驟錯誤，或套用到錯的元素。
- **0**：大部分步驟缺漏、錯誤或誤用。

##### B) 非目標區域不變性：0–5

衡量要求修改以外的內容，在所有步驟之後是否維持不變。

- **5**：要求修改以外沒有可偵測的變化。
- **4**：只有近看才看得出極輕微的偏移。
- **3**：附近的元素有明顯但有限的偏移。
- **2**：有明確的未要求變動，影響相鄰的文字、符號或背景。
- **1**：整個 logo 有大範圍的非預期變動。
- **0**：Logo 的身份已經被破壞。

##### C) 字元與風格完整性：0–5

Logo 編輯不是創意轉換。輸出必須保留原始素材的身份，包括顏色、筆畫、字形和圖示的一致性。

- **5**：編輯的字元和符號完全符合原始風格。顏色、筆畫、字形和圖示跟原件分不出差別。
- **4**：只有近看才看得出極輕微的偏差，不影響品牌觀感。
- **3**：一個以上的屬性有明顯但有限的偏差，不影響辨識。
- **2**：顏色、筆畫、字形或圖示幾何有明確的不一致，影響視覺的整體感。
- **1**：重大不一致，實質改變了 logo 的外觀。
- **0**：視覺系統已損壞或無法辨識。

**LLM-as-judge rubric prompt**

下面是對齊你現有 `LLMajRubricGrader` 的 judge prompt。它會回傳結構化的各項指標分數加整體 verdict。

你可以把 JSON schema 改成包含下面的欄位，沿用現有的 grader，或者想的話也可以每個指標拆成獨立的 grader。


```python
PROMPT = """<core_mission>
Evaluate whether a logo edit was executed with exact correctness,
strict preservation, and high visual integrity.

Logo editing is a precision task.
Small errors matter.
Near-misses are failures.
</core_mission>

<role>
You are an expert evaluator of high-precision logo and brand asset editing.
You specialize in detecting subtle text errors, unintended changes,
and preservation drift across single-step and multi-step edits.
</role>

<scope_constraints>
- Judge only against the provided edit instruction and input logo.
- Do NOT judge aesthetics or visual appeal.
- Do NOT infer intent beyond what is explicitly stated.
- Be strict, conservative, and consistent across cases.
</scope_constraints>

<metrics_and_scoring>

Evaluate EACH metric independently using the definitions below.
All metrics are scored from 0 to 5.
Scores apply across ALL requested edit steps.

--------------------------------
1) Edit Intent Correctness (0–5)
--------------------------------
Measures whether every requested edit step was applied correctly
to the correct target.

5: All edit steps applied exactly as specified. Character-level
   accuracy is perfect for every step.
4: All steps applied correctly with extremely minor visual
   imperfections visible only on close inspection.
3: All steps applied, but one or more steps show noticeable
   degradation in clarity or precision.
2: Most steps applied correctly, but one or more steps contain
   a meaningful error.
1: One or more steps are incorrect or applied to the wrong element.
0: Most steps missing, incorrect, or misapplied.

What to consider:
- Exact character identity (letters, numbers, symbols)
- Correct sequencing and targeting of multi-step edits
- No ambiguous characters (Common confusions: 0 vs 6, O vs D, R vs B)

--------------------------------
2) Non-Target Invariance (0–5)
--------------------------------
Measures whether content outside the requested edits remains unchanged.

5: No detectable changes outside the requested edits.
4: Extremely minor drift visible only on close inspection.
3: Noticeable but limited drift in nearby elements.
2: Clear unrequested changes affecting adjacent text,
   symbols, or background.
1: Widespread unintended changes across the logo.
0: Logo identity compromised.

What to consider:
- Adjacent letter deformation or spacing shifts
- Background, texture, or color changes
- Cumulative drift from multi-step edits

--------------------------------
3) Character and Style Integrity (0–5)
--------------------------------
Measures whether the edited content preserves the original
logo’s visual system.

This includes color, stroke weight, letterform structure,
and icon geometry.

5: Edited characters and symbols perfectly match the original
   style. Colors, strokes, letterforms, and icons are
   indistinguishable from the original.
4: Extremely minor deviation visible only on close inspection,
   with no impact on brand perception.
3: Noticeable but limited deviation in one or more properties
   that does not break recognition.
2: Clear inconsistency in color, stroke, letterform, or icon
   geometry that affects visual cohesion.
1: Major inconsistency that materially alters the logo’s appearance.
0: Visual system is corrupted or no longer recognizable.

</metrics_and_scoring>

<verdict_rules>
- Edit Intent Correctness must be ≥ 4.
- Non-Target Invariance must be ≥ 4.
- Character and Style Integrity must be ≥ 4.

If ANY metric falls below threshold, the overall verdict is FAIL.
Do not average scores to determine the verdict.
</verdict_rules>

<consistency_rules>
- Score conservatively.
- If uncertain between two scores, choose the lower one.
- Base all scores on concrete visual observations.
- Penalize cumulative degradation across multi-step edits.
</consistency_rules>

<output_constraints>
Return JSON only.
No additional text.
</output_constraints>
"""
```

#### 建議的 JSON 輸出


```python
{
  "verdict": "PASS",
  "edit_intent_correctness": 5,
  "non_target_invariance": 5,
  "character_and_style_integrity": 5,
  "reason": "..."
}
```

??? note "輸出"

    ```text
    {'verdict': 'PASS',
     'edit_intent_correctness': 5,
     'non_target_invariance': 5,
     'character_and_style_integrity': 5,
     'reason': '...'}
    ```



### Logo 編輯範例：Harness Setup

用現有的 logo 圖片和一個範圍很窄的編輯指令。


```python
# Capture the logo judge prompt.
logo_judge_prompt = PROMPT

logo_input_path = Path("../../images/logo_generation_1.png")

logo_prompt = """Edit the logo by changing the text from FIELD to BUTTER .
Do not change any other text, colors, shapes, or layout."""

logo_criteria = """The requested edit is applied exactly.
All non-target content remains unchanged.
Character style, color, and geometry remain consistent with the original."""

logo_case = TestCase(
    id="logo_year_edit",
    task_type="image_editing",
    prompt=logo_prompt,
    criteria=logo_criteria,
    image_inputs=ImageInputs(image_paths=[logo_input_path]),
)

logo_run = ModelRun(
    label="gpt-image-1.5-logo",
    task_type="image_editing",
    params={
        "model": "gpt-image-1.5",
        "n": 1,
    },
)

logo_store = OutputStore(root=Path("../../images"))
```



### Logo 編輯範例：執行與評分

跑 harness，用 logo judge rubric 替 logo 編輯評分。


```python
logo_schema = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "edit_intent_correctness": {"type": "number"},
        "non_target_invariance": {"type": "number"},
        "character_and_style_integrity": {"type": "number"},
        "reason": {"type": "string"},
    },
    "required": [
        "verdict",
        "edit_intent_correctness",
        "non_target_invariance",
        "character_and_style_integrity",
        "reason",
    ],
    "additionalProperties": False,
}


def parse_logo_result(data: dict, base_key: str) -> list[Score]:
    return [
        Score(key="edit_intent_correctness", value=float(data["edit_intent_correctness"]), reason=""),
        Score(key="non_target_invariance", value=float(data["non_target_invariance"]), reason=""),
        Score(key="character_and_style_integrity", value=float(data["character_and_style_integrity"]), reason=""),
        Score(key="verdict", value=str(data["verdict"]), reason=(data.get("reason") or "").strip()),
    ]

logo_grader = LLMajRubricGrader(
    key="logo_eval",
    system_prompt=logo_judge_prompt,
    content_builder=build_editing_judge_content,
    judge_model="gpt-5.2",
    json_schema_name="logo_eval",
    json_schema=logo_schema,
    result_parser=parse_logo_result,
)

logo_results = evaluate(
    cases=[logo_case],
    model_runs=[logo_run],
    graders=[logo_grader],
    output_store=logo_store,
)

logo_result = logo_results[0]
logo_result
```

??? note "輸出"

    ```text
    {'test_id': 'logo_year_edit',
     'model_label': 'gpt-image-1.5-logo',
     'task_type': 'image_editing',
     'artifact_paths': ['../../images/edit_logo_year_edit_gpt-image-1.5-logo_1769659071403_0.png'],
     'scores': {'edit_intent_correctness': 5.0,
      'non_target_invariance': 0.0,
      'character_and_style_integrity': 2.0,
      'verdict': 'FAIL'},
     'reasons': {'edit_intent_correctness': '',
      'non_target_invariance': '',
      'character_and_style_integrity': '',
      'verdict': 'Target text was correctly changed from “FIELD” to “BUTTER” (now reads “BUTTER & FLOUR”). However, major unrequested changes occurred: the background changed from a gray gradient to solid black, and the logo’s overall rendering/contrast differs (the original had a soft glow/embossed look, while the edited version is flatter with different tonal values). These violate the instruction to not change any other colors, shapes, or layout.'},
     'run_params': {'model': 'gpt-image-1.5', 'n': 1}}
    ```



### Logo 編輯 Eval 結果

把編輯後的 logo 和 logo 編輯分數放進同一張 pandas 表格。


<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/edit_logo_year_edit_gpt-image-1.5-logo_1769659071403_0.png" width="400"/> 

```python
render_result_table(case=logo_case, result=logo_result, title="Logo Editing: Prompt vs. Scores")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

##### 3) 手上有 Ground Truth 圖片時的替代做法

如果你已經有正式的參考圖，可以直接跟**設計的 source-of-truth** 比，不用跟模型輸出比。

Ground truth 應該來自設計系統，不是生成的圖：

- 品牌素材庫的資產（向量或高解析度的正式點陣圖）
- 代表正確素材狀態的 Figma frame 或元件

這很自然地對應 logo 編輯的要求，像是「還是同一個素材」和「非預期的偏移就是失敗」。

**範例：OpenAI Logo，農曆新年版**

- 參考圖：正式的 OpenAI logo（來自 Figma 或品牌素材）
- 生成圖：套用要求轉換後的模型輸出



## 結論

圖像模型正從「炫技 demo」走向 production 工具，產出會影響決策、會交到客戶手上的真實素材：畫面、傳單、產品視覺和品牌編輯。這份 cookbook 的核心結論很簡單：你不能用籠統的「看起來不錯」分數來評這些系統，你需要**針對 workflow 的 evals**，而且在不同模型版本、prompt 和設定之間都**可重複**。多模態 LLM 讓這件事可行，它能當可擴充的 judge，前提是搭配嚴謹的 rubric、結構化輸出和人工校準。

實用的 vision-eval 計畫從小處開始，慢慢變銳利：

- **先從 gate 開始。**針對會毀掉真實工作的失敗模式加嚴格的 pass/fail grader：缺必要元件、文案錯誤、編輯溢出指定區域，或保留區域被非預期改動。這樣可以避免「漂亮但是錯」的輸出掩蓋 regression。
- **再疊上分級指標。**硬性失敗控制住之後，用 0–5 的 rubric 抓每個 workflow 在可用性和品質上重要的東西（例如 UI mockup 的層次、行銷的品牌契合度、編輯的保真度/保留性）。
- **標記失敗，迭代更快。**一致的失敗標籤能把一堆輸出變成可執行的工程工作：你可以量化哪裡壞了、找出聚集的根本原因，並在調整 prompt、模型設定、mask 或後處理時追蹤進度。
- **策略性地用人。**人在主觀或模糊的面向（「感覺」、可用性清晰度、可信度）最有價值，但前提是 rubric 要嚴謹，並用校準錨點防止飄移。
- **把 harness 當成產品。**你建好的可重用 harness（test case、runner、grader、儲存的產物）是 regression 測試、參數掃描和並排比較的基礎。久了之後，你的 eval suite 就是安全網：及早抓到細微的失敗，讓改進可以被量測。
- **視需要演進。**你可以隨時間用更複雜的指標重新設計 grader prompt。很自然的下一步是把單次的 grader prompt 拆成多次呼叫，每次專注一個指標。

建出反映圖片實際使用方式的 evals，先確保正確性再談美感，讓迭代由資料驅動。當你的 evals 對齊真實 workflow 的需求，圖像生成和編輯就不再是不可預測的藝術專案，而是團隊能信任的工具。


## 重點整理

- Vision eval 要針對特定 workflow 設計，評的是「這個模型在這個用途上可不可靠」，不是畫面好不好看。
- Harness 拆成 test case、runner、grader 三個插件，換場景只要換 test case 和 judge prompt。
- 先設 gate（指令遵循、文字正確、局部性/保留性），gate 過了才看 0–5 的品質分，而且不能用平均分去蓋掉 gate。
- 編輯類任務要同時對照輸入和輸出，重點是保留性：沒要求改的地方不能動。
- 失敗標籤加人工校準錨點，能讓 eval 長期穩定、也方便找出要修的問題。

## 練習

1. 在 UI mockup 的 verdict 規則裡，把「版面與層次 ≥ 3」改成 ≥ 4，重跑後看有哪些 case 的 verdict 翻轉。
2. 為咖啡店傳單加一個 test case，要求價格寫成 “$4.50” 且不准有其他數字，並在 judge prompt 裡加一條對應的文字渲染 gate。
3. 把 VTO 的三個指標拆成三次獨立的 judge 呼叫（每次只評一個指標），比較單次呼叫和拆開呼叫的分數差異。
