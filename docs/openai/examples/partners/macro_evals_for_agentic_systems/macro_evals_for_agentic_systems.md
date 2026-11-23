---
translated: true
source: examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems.ipynb
---
# Agentic 系統的 Macro Evals

> 原文：[examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/partners/macro_evals_for_agentic_systems/macro_evals_for_agentic_systems.ipynb)

示範怎麼評估 multi-agent 系統：把 trace 層級的 eval 訊號分群成反覆出現的行為模式，再鑽進影響最大的那個模式。

## 這篇在做什麼

用一份合成的電動車訂單 multi-agent 流程，示範 macro eval 的完整做法：先對每條 trace 做低層 eval，再把 trace 壓成文件、分群找出反覆出現的行為模式，最後挑一個影響最大的模式往回追可疑的 agent 或 handoff。資料都是預先算好的，不用 OpenAI API key 就能跑完。

## 學完你會

- 把一批 agent trace 整理成 `traces_df`、`events_df` 和可以分群的 trace 文件
- 用 BERTopic 風格的流程（embedding、UMAP、HDBSCAN）找出行為模式，並用 impact score 排優先順序
- 用 AgentTrace 風格的圖分析，從 focus event 往回找出該先檢查的 agent、tool 和 handoff

## 開跑前

不需要 OpenAI API key。資料放在範例資料夾的 `data/` 底下，如果放在別處，設環境變數 `MACRO_EVALS_DATA_ROOT`；labels 單獨放的話設 `MACRO_EVALS_LABELS_PATH`。

agentic 系統出問題時，常常不只是某一次回答不好。可能 handoff 太晚、某個 specialist agent 在很多次 run 都漏掉同一個訊號，或是 review 流程被不該觸發的案例觸發。要改善系統，團隊得看整批 trace 反覆出現的行為。

這篇走一遍 multi-agent 系統的 macro-eval 流程。我們用一個合成的電動車訂單 workflow，specialist agent 負責定價、法規、供應、工廠分派、排程和放行決策，同時市場和營運條件一直在變。

notebook 使用預先算好的合成 trace 和存好的低層 eval labels，所以不需要 OpenAI API key 就能跑完整個流程。

你會學到：
1. 產生或收集大量有 trace 的 agent run；
2. 對每個完成的 run 做低層 eval；
3. 把每條 trace 變成精簡的文件；
4. 在整批資料裡找出反覆出現的行為模式；
5. 鑽進一個高影響的模式，找出人接下來該檢查系統哪裡。

目標不是替每條 trace 建出完美的分類。目標是示範 AI 工程團隊怎麼從成千上萬個 agent 事件，收斂成少數技術人員和業務人員都看得懂的模式。


## 端到端的 Agentic 系統地圖

![End-to-end macro evals architecture](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/agentic-system-architecture.svg)

關鍵想法是，這個 notebook 評估的是一個存下來的 agentic 系統，不是一般的聊天紀錄。情境輸入驅動一群有編排的 specialist agent，runtime 產出 trace bundle，存好的 Promptfoo labels 會接到正規化後的 trace 上，macro-eval 層再把這些證據變成 pattern 和 diagnosis 的視圖。


## 1. 為什麼要 Macro Evals？

Eval 是 AI 團隊衡量系統有沒有在正常運作的方法。對單純的模型呼叫，eval 可能是拿一個輸出去對 rubric 或參考答案。對 agentic 系統，還要評估它有沒有用對 tool、有沒有交給對的 specialist、高風險時有沒有停下來 review，以及有沒有緊扣業務情境。

Multi-agent 系統更難，因為最終答案只是長流程裡的最後一個事件。放行建議看起來合理，但 trace 可能顯示定價 agent 忽略了某個優惠、供應 agent 漏掉缺貨，或 orchestrator 繞過了必要的 review 步驟。

這個 notebook 把問題分成兩層：

- **Lower-level evals** 評分單一 agent、handoff、tool 和完成的 run。在這個範例裡，Promptfoo 扮演 agent 層級的 eval，評分一次 run 在最終決策品質、政策正確性、specialist 分派、市場變動和 review 是否恰當上的表現。
- **Macro evals** 看很多低層發現的整體。它們問的是：哪些問題一再重複、集中在哪裡、agent 流程的哪個部分該先檢查？

整篇會用四個方便閱讀的標籤：

- `case_type`：產生出來的業務情境，例如乾淨訂單、validation 擋下、供應商替代或定價例外。
- `run_outcome`：run 怎麼結束，例如完成、等待 review、被擋下或失敗。
- `eval_finding`：低層的訊號，說明哪裡看起來有問題或有風險。
- `behavior_pattern`：從很多 trace 中找出來、反覆出現的模式。

一個好用的心智模型：`case_type` 是設定，`run_outcome` 是結局，`eval_finding` 是局部症狀，`behavior_pattern` 是整批資料層級的模式。


```python
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise RuntimeError("This notebook requires Python 3.11 or newer.")

if not Path("requirements.txt").is_file():
    raise FileNotFoundError("requirements.txt must be in the same folder as this notebook.")

%pip install -q --upgrade pip setuptools wheel
%pip install -q --only-binary=:all: -r requirements.txt
```

## 環境設定與資料

安裝相依套件，然後載入這個範例附的離線資料。存好的 Promptfoo labels 在本機資料夾裡，所以這個 notebook 不需要另外的 Promptfoo 設定、Promptfoo run artifact 或 OpenAI API key。

預期的檔案：

```text
data/trace_results.jsonl
data/run_summary.json
data/trace_bundles.zip
data/eval_labels.jsonl
```

`trace_bundles.zip` 第一次跑 notebook 時會自動解壓到本機 cache。完整的 SQLite trace snapshot 可以放在 `data/trace_snapshot.sqlite` 做選用的補充，但整個流程不一定要有它。

如果你的資料在範例資料夾以外，把 `MACRO_EVALS_DATA_ROOT` 設成那個目錄。labels 放在別處的話，設 `MACRO_EVALS_LABELS_PATH`。


```python
from __future__ import annotations

import json
import os
import sqlite3
import sys
import warnings
import zipfile
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from IPython.display import Markdown, display

pd.set_option("display.max_colwidth", 180)
pd.set_option("display.max_rows", 100)
warnings.filterwarnings("ignore", message="n_jobs value 1 overridden.*")


def find_example_root(start: Path | None = None) -> Path:
    start = (start or Path.cwd()).resolve()
    candidates = [start, *start.parents, start / "examples/partners/macro_evals_for_agentic_systems"]
    for candidate in candidates:
        if (candidate / "helpers/data_prep.py").is_file() and (candidate / "helpers/macro_eval_pipeline.py").is_file():
            return candidate
    raise FileNotFoundError("Could not locate the macro evals example root.")


EXAMPLE_ROOT = find_example_root()
HELPERS_ROOT = EXAMPLE_ROOT / "helpers"
if str(HELPERS_ROOT) not in sys.path:
    sys.path.insert(0, str(HELPERS_ROOT))

from data_prep import add_public_label_columns, build_trace_documents, load_promptfoo_label_rows, normalize_bundle
from macro_eval_pipeline import (
    drill_down_topic_root_causes,
    pick_focus_topic,
    plot_root_cause_story,
    plot_suspect_leaderboard,
    plot_topic_heatmap,
    plot_topic_leaderboard,
    plot_topic_scatter,
    plot_trace_swimlane,
    run_macro_discovery,
    slice_topics_by_metadata,
)


def display_path(path: Path | None) -> str:
    if path is None:
        return "not found"
    try:
        return str(path.resolve().relative_to(EXAMPLE_ROOT))
    except ValueError:
        return str(path)


def as_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else EXAMPLE_ROOT / path


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def find_material(label: str, names: list[str], *, kind: str = "file", required: bool = True) -> Path | None:
    checked: list[Path] = []
    for root in DATA_ROOTS:
        for name in names:
            if not name:
                continue
            candidate = as_path(name) if Path(name).expanduser().is_absolute() else root / name
            checked.append(candidate)
            if kind == "dir":
                exists = candidate.is_dir() and any(candidate.glob("*.json"))
            else:
                exists = candidate.is_file()
            if exists:
                return candidate.resolve()
    if required:
        checked_text = "\n".join(f"- {display_path(path)}" for path in checked)
        raise FileNotFoundError(f"Missing {label}. Checked:\n{checked_text}")
    return None


def ensure_trace_bundle_dir(bundle_dir: Path | None, bundle_zip: Path | None) -> Path:
    if bundle_dir is not None:
        return bundle_dir
    if bundle_zip is None:
        raise FileNotFoundError("Missing trace bundles. Expected data/trace_bundles/ or data/trace_bundles.zip.")
    cache_dir = bundle_zip.parent / ".macro_eval_cache" / "trace_bundles"
    marker = cache_dir / ".extracted_from_trace_bundles_zip"
    if not marker.is_file() or not any(cache_dir.glob("*.json")):
        cache_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(bundle_zip) as archive:
            for member in archive.infolist():
                if member.is_dir() or not member.filename.endswith(".json"):
                    continue
                (cache_dir / Path(member.filename).name).write_bytes(archive.read(member))
        marker.write_text(str(bundle_zip.stat().st_mtime_ns), encoding="utf-8")
    return cache_dir.resolve()


env_data_root = os.environ.get("MACRO_EVALS_DATA_ROOT")
DATA_ROOTS = unique_paths(
    ([as_path(env_data_root)] if env_data_root else [])
    + [
        EXAMPLE_ROOT / "data",
    ]
)

RESULTS_PATH = find_material("trace results", ["trace_results.jsonl", "metadata/results.jsonl", "results.jsonl"])
SUMMARY_PATH = find_material("run summary", ["run_summary.json", "metadata/summary.json", "summary.json"])
SQLITE_PATH = find_material("optional trace snapshot", ["trace_snapshot.sqlite"], required=False)
BUNDLE_ZIP_PATH = find_material("trace bundle archive", ["trace_bundles.zip", "bundles.zip"], required=False)
BUNDLE_DIR = ensure_trace_bundle_dir(find_material("trace bundles", ["trace_bundles", "bundles"], kind="dir", required=False), BUNDLE_ZIP_PATH)
PROGRESS_PATH = find_material("run progress", ["run_progress.json", "metadata/progress.json", "progress.json"], required=False)
PROMPTFOO_LABELS_PATH = find_material(
    "lower-level eval labels",
    [
        os.environ.get("MACRO_EVALS_LABELS_PATH", ""),
        "eval_labels.jsonl",
        "metadata/eval_labels.jsonl",
    ],
    required=False,
)

DATA_ROOT = next((root for root in DATA_ROOTS if RESULTS_PATH.is_relative_to(root)), DATA_ROOTS[0])
TRACE_LIMIT = int(os.environ.get("MACRO_EVALS_TRACE_LIMIT", "0")) or None
DISCOVERY_DOC_COLUMN = "doc_structured_summary"
DISCOVERY_MIN_CLUSTER_SIZE = int(os.environ.get("MACRO_EVALS_DISCOVERY_MIN_CLUSTER_SIZE", "24"))
RANDOM_STATE = 42

resolved_paths_df = pd.DataFrame(
    [
        ("Trace results", RESULTS_PATH),
        ("Run summary", SUMMARY_PATH),
        ("Trace bundle archive", BUNDLE_ZIP_PATH),
        ("Expanded trace bundles", BUNDLE_DIR),
        ("Optional trace snapshot", SQLITE_PATH),
        ("Run progress", PROGRESS_PATH),
        ("Lower-level eval labels", PROMPTFOO_LABELS_PATH),
    ],
    columns=["material", "path"],
)
resolved_paths_df["path"] = resolved_paths_df["path"].map(display_path)

display(Markdown("### Data materials"))
display(resolved_paths_df)
display(Markdown(f"Example root: `{display_path(EXAMPLE_ROOT)}`  \nData root: `{display_path(DATA_ROOT)}`"))
```

## 2. 模擬情境：變動世界裡的汽車訂單

模擬的業務是電動車訂單和配置後流程。客戶選好了車款配置，公司要決定訂單能不能照原樣進行、需要調整、要改派、需要替代料件，或是該暫停 review。

模擬包含了讓真實汽車履約很難做的那些限制：

- 零組件供應和供應商替代；
- 工廠產能和生產排程；
- 定價例外、促銷和優惠；
- 關稅和有日期的市場訊號；
- 各地區的法規限制；
- 客戶澄清和升級處理的路徑；
- 風險或模糊案例的放行 review 門檻。

agent swarm 依這些業務職責來組織。orchestrator 收到訂單和當前環境，再委派給 specialist，像是 validation、供應風險、採購規劃、產能平衡、工廠分派、市場情報、定價、法規、客戶溝通和放行 review。

這很自然對應到 OpenAI Agents SDK。在 SDK 裡，agent 是 workflow 的核心單位：它把模型、instructions 和選用的 runtime 行為（tools、handoffs、guardrails、structured outputs）包在一起。模擬照這個模式做：

- **specialized agents** 把決策某一塊的 instructions 和 tools 包起來；
- **handoffs** 讓 orchestrator 把工作委派給另一個 specialist agent，不用把所有職責塞進同一個 prompt；
- **function tools** 用結構化的輸入輸出提供訂單資料、環境訊號和核准標記；
- **guardrails 和 review 門檻** 代表風險或模糊案例的驗證、擋下和人工 review 流程；
- **structured outputs** 讓後續的評分和彙整成為可能；
- **traces** 保留 model call、tool call、handoff、guardrail 和自訂 span 的結構化紀錄，供 debug 和 macro 層級的分析使用。

notebook 後面的低層 evals 都建立在這個模擬情境上。如果 case type 說是關稅壓力下的供應商替代，trace 就應該顯示它注意到供應、政策、市場和 review 風險。如果 case type 是乾淨的，多餘的升級處理本身就是一個 finding。


```python
def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def result_run_id(row: dict[str, Any]) -> str | None:
    if row.get("run_id"):
        return str(row["run_id"])
    if row.get("bundle_path"):
        return Path(str(row["bundle_path"])).stem
    return None


def sqlite_table_counts(db_path: Path | None) -> pd.DataFrame:
    tables = [
        "runs",
        "configs",
        "traces",
        "trace_events",
        "spans",
        "review_packets",
        "environment_events",
        "environment_decisions",
    ]
    if db_path is None:
        return pd.DataFrame([{"table": table, "row_count": 0} for table in tables])
    with sqlite3.connect(db_path) as conn:
        existing_tables = {
            row[0]
            for row in conn.execute("select name from sqlite_master where type = 'table'")
        }
        rows = [
            {
                "table": table,
                "row_count": conn.execute(f"select count(*) from {table}").fetchone()[0] if table in existing_tables else 0,
            }
            for table in tables
        ]
    return pd.DataFrame(rows)


def load_sqlite_runs(db_path: Path | None) -> pd.DataFrame:
    if db_path is None:
        return pd.DataFrame()
    summary_fields = [
        "scenario_family",
        "validation_outcome",
        "review_status",
        "review_decision",
        "triage_outcome",
        "market_regime",
        "price_regime",
        "schedule_regime",
        "agent_version_set",
        "orchestrator_mode",
        "rogue_window_id",
        "factory_release_state",
        "trace_family",
        "loop_count",
        "retry_count",
        "arbitration_count",
        "compound_issue_count",
        "specialist_activations",
        "environment_event_ids",
        "findings",
        "failure_agent",
        "error_code",
        "error_message",
    ]
    rows = []
    with sqlite3.connect(db_path) as conn:
        for row in conn.execute("select run_id, config_id, trace_id, status, terminal_state, started_at, ended_at, summary_json from runs"):
            run_id, config_id, trace_id, status, terminal_state, started_at, ended_at, summary_json = row
            summary = json.loads(summary_json or "{}")
            item = {field: summary.get(field) for field in summary_fields}
            item.update(
                {
                    "run_id": run_id,
                    "config_id": config_id,
                    "trace_id": trace_id,
                    "sqlite_status": status,
                    "sqlite_terminal_state": terminal_state,
                    "started_at": started_at,
                    "ended_at": ended_at,
                }
            )
            rows.append(item)
    runs = pd.DataFrame(rows)
    if runs.empty:
        return runs
    runs["started_at"] = pd.to_datetime(runs["started_at"], utc=True, errors="coerce")
    runs["ended_at"] = pd.to_datetime(runs["ended_at"], utc=True, errors="coerce")
    runs["findings_count_sqlite"] = runs["findings"].apply(lambda value: len(value or []))
    runs["specialist_activation_count_sqlite"] = runs["specialist_activations"].apply(lambda value: len(value or []))
    runs["environment_event_count_sqlite"] = runs["environment_event_ids"].apply(lambda value: len(value or []))
    return runs


batch_summary = read_json(SUMMARY_PATH)
results_rows = read_jsonl(RESULTS_PATH)
sqlite_runs_df = load_sqlite_runs(SQLITE_PATH)
table_counts_df = sqlite_table_counts(SQLITE_PATH)

result_ids = {rid for row in results_rows if (rid := result_run_id(row))}
bundle_ids = {path.stem for path in BUNDLE_DIR.glob("*.json")}
missing_result_rows = [row for row in results_rows if result_run_id(row) is None]

def table_count(table_name: str) -> int:
    rows = table_counts_df.loc[table_counts_df["table"].eq(table_name), "row_count"]
    return int(rows.iloc[0]) if not rows.empty else 0


dataset_profile_df = pd.DataFrame(
    [
        ("requested_batch_size", batch_summary.get("batch_size") or batch_summary.get("requested_runs")),
        ("results_rows", len(results_rows)),
        ("bundle_backed_result_rows", len(result_ids)),
        ("runner_error_rows_without_bundle", len(missing_result_rows)),
        ("bundle_files_available", len(bundle_ids)),
        ("bundle_files_not_in_results", len(bundle_ids - result_ids)),
        ("saved_promptfoo_label_rows", len(read_jsonl(PROMPTFOO_LABELS_PATH)) if PROMPTFOO_LABELS_PATH else 0),
        ("sqlite_available", SQLITE_PATH is not None),
        ("sqlite_runs", len(sqlite_runs_df)),
        ("sqlite_trace_events", table_count("trace_events")),
        ("sqlite_spans", table_count("spans")),
    ],
    columns=["metric", "value"],
)

display(dataset_profile_df)
if SQLITE_PATH is not None:
    display(table_counts_df)

if missing_result_rows:
    display(Markdown(
        f"The batch has `{len(results_rows):,}` result rows, but `{len(missing_result_rows):,}` ended before a bundle was written. "
        f"The macro analysis therefore focuses on the `{len(result_ids):,}` bundle-backed traces that can be normalized and graded retrospectively."
    ))

if SQLITE_PATH is None:
    display(Markdown(
        "This packaged version omits the large SQLite mirror. The notebook uses the JSONL result rows, trace bundles, and saved Promptfoo labels for the end-to-end workflow."
    ))
```

### 一個 Bundle 代表什麼

在這個 notebook 裡，**bundle** 是一次模擬的客戶訂單互動的證據包。

想像一個客戶配好了一台電動車，公司要決定下一步。swarm 收到這張訂單，加上當前的營運環境：供應限制、工廠產能、促銷、優惠、關稅、競爭壓力和 review 門檻。agent 接著把工作分派給各個 specialist，產生最終狀態。bundle 就是事後稽核這次互動需要的全部資料。

bundle 重要，因為 macro evals 需要最終答案背後的 workflow 證據。要知道諮詢過哪些 agent、呼叫過哪些 tool、哪些環境訊號在作用、有沒有要求 review，以及 workflow 在哪裡轉向。有了這些證據，才能從「這一次 run 發生了什麼？」走到「很多次 run 之間，哪些 workflow 模式一再重複？」


```python
def bundle_path_for_result(result_row: dict[str, Any]) -> Path | None:
    raw = result_row.get("bundle_path")
    if not raw:
        return None
    return BUNDLE_DIR / Path(str(raw)).name


def bundle_event_counts(bundle: dict[str, Any]) -> dict[str, int]:
    events = bundle.get("events") or []
    spans = bundle.get("spans") or []
    event_types = pd.Series([event.get("event_type") or "unknown" for event in events])
    span_types = pd.Series([span.get("span_type") or "unknown" for span in spans])
    agents = {
        event.get("agent_name")
        for event in events
        if event.get("agent_name")
    } | {
        span.get("agent_name")
        for span in spans
        if span.get("agent_name")
    }
    return {
        "events": len(events),
        "spans": len(spans),
        "handoffs": int(event_types.eq("handoff").sum() + span_types.eq("handoff").sum()),
        "tool_or_function_calls": int(event_types.eq("function").sum() + span_types.eq("function").sum()),
        "status_updates": int(event_types.eq("status").sum()),
        "unique_agents_seen": len(agents),
        "environment_signals": len(bundle.get("environment_events") or []),
        "has_review_packet": int(bool(bundle.get("review_packet"))),
    }


def human_event_type(value: str) -> str:
    cleaned = str(value or "").replace("product_launch", "product_launch")
    return cleaned.replace("_", " ")


bundle_rows = []
sample_bundle = None
sample_result_row = None
for result_row in results_rows:
    bundle_path = bundle_path_for_result(result_row)
    if bundle_path is None or not bundle_path.is_file():
        continue
    bundle = read_json(bundle_path)
    counts = bundle_event_counts(bundle)
    counts["run_id"] = result_run_id(result_row)
    counts["case_type"] = result_row.get("scenario_family")
    counts["final_status"] = result_row.get("final_status") or result_row.get("status")
    counts["review_status"] = result_row.get("review_status")
    bundle_rows.append(counts)
    if sample_bundle is None and result_row.get("scenario_family") != "clean_simple":
        sample_bundle = bundle
        sample_result_row = result_row

bundle_profile_df = pd.DataFrame(bundle_rows)
typical_bundle_df = pd.DataFrame(
    [
        ("analyzable customer-order interactions", len(bundle_profile_df), "One completed trace bundle per simulated order interaction."),
        ("median normalized events per interaction", int(bundle_profile_df["events"].median()), "Status updates, handoffs, function/tool events, responses, and findings."),
        ("median SDK spans per interaction", int(bundle_profile_df["spans"].median()), "Lower-level SDK trace spans behind the event log."),
        ("median handoff records per interaction", int(bundle_profile_df["handoffs"].median()), "Delegations between orchestrator and specialist agents."),
        ("median tool/function calls per interaction", int(bundle_profile_df["tool_or_function_calls"].median()), "Structured reads, checks, and evaluation calls inside the run."),
        ("median agents observed per interaction", int(bundle_profile_df["unique_agents_seen"].median()), "How many specialist roles appear in a typical trace."),
        ("median environment signals per interaction", int(bundle_profile_df["environment_signals"].median()), "Tariff, incentive, stockout, promotion, competitor, launch, or schedule signals active for the order."),
        ("interactions with review packets", int(bundle_profile_df["has_review_packet"].sum()), "Runs where the simulated business process produced a review artifact."),
    ],
    columns=["reader_metric", "value", "plain_english_meaning"],
)
display(typical_bundle_df)

bundle_anatomy_df = pd.DataFrame(
    [
        ("run", "Run id, trace id, terminal state, batch metadata, and synthetic order context.", "Lets us join one interaction across tables and understand its business setup."),
        ("events", "A normalized event log: status updates, handoffs, tool/function activity, responses, and findings.", "This is the main evidence stream used for trace documents and AgentTrace-style diagnosis."),
        ("spans", "OpenAI Agents SDK trace spans for handoffs, function calls, responses, and timing.", "Gives lower-level execution structure behind the event log."),
        ("environment_events", "The dated world state active for the order: tariffs, incentives, stockouts, promotions, competitor pressure, launches, and schedule/capacity signals.", "Lets evals check whether the swarm reacted to the world it was given."),
        ("review_packet", "A simulated review artifact with findings, recommended action, allowed actions, and review status.", "Lets us evaluate whether escalation or review was appropriate."),
        ("snapshots", "Optional inventory, capacity, and environment snapshots.", "Provides operational context when a case depends on supply or scheduling."),
    ],
    columns=["bundle_part", "what_it_contains", "why_it_matters_for_macro_evals"],
)
display(bundle_anatomy_df)
```

```python
if sample_bundle is not None and sample_result_row is not None:
    run_config = (sample_bundle.get("run") or {}).get("config") or {}
    metadata = run_config.get("metadata") or {}
    generation = metadata.get("generation_params") or {}
    customer = run_config.get("customer") or {}
    active_event_types = sorted({human_event_type(value) for value in generation.get("active_event_types") or []})
    specialists = sample_result_row.get("specialist_activations") or generation.get("specialist_activations") or []
    review_packet = sample_bundle.get("review_packet") or {}

    example_interaction_df = pd.DataFrame(
        [
            ("what the interaction represents", "One synthetic customer order moving through the post-configuration workflow."),
            ("case_type", sample_result_row.get("scenario_family")),
            ("synthetic customer region", customer.get("region") or "not recorded"),
            ("business issue cluster", generation.get("issue_cluster") or sample_result_row.get("scenario")),
            ("active world signals", ", ".join(active_event_types[:8]) + (" ..." if len(active_event_types) > 8 else "")),
            ("specialists activated", ", ".join(map(str, specialists[:8])) + (" ..." if len(specialists) > 8 else "")),
            ("final status", sample_result_row.get("final_status") or sample_result_row.get("status")),
            ("review status", sample_result_row.get("review_status") or review_packet.get("status") or "not recorded"),
            ("event evidence", f"{len(sample_bundle.get('events') or []):,} events and {len(sample_bundle.get('spans') or []):,} SDK spans"),
        ],
        columns=["field", "example_value"],
    )
    display(example_interaction_df)
```

### 怎麼看 Dataset Profile

dataset profile 告訴我們即將評估的模擬業務流程的規模和質地。每個可分析的 row 是一次客戶訂單互動，帶有足夠的 trace 證據，可以重建 agent swarm 看到了什麼、諮詢了哪些 specialist，以及 workflow 怎麼結束。

這批資料要求 swarm 處理 1,000 筆合成的訂單互動。其中 992 筆有 bundle：一份完整的證據包，可以用來評分這次 run、建 trace 文件、跟相似的 run 分群，並在事後檢視 agent 走過的路徑。這個規模夠大，能找出重複的行為，同時保有說明單一案例所需的 trace 細節。

典型的 bundle 是一個模擬業務流程的結構化紀錄：訂單設定、當時的世界事件、specialist handoff、tool/function 活動、review 產物和最終狀態。這就是這份資料能支撐 macro evals 的原因。我們能評估單一決策，也能問在數百筆豐富的互動紀錄中，有沒有出現重複的 workflow 模式。


```python
scenario_counts_df = (
    pd.DataFrame(results_rows)
    .assign(case_type=lambda df: df["scenario_family"].fillna("unknown"))
    .groupby("case_type", as_index=False)
    .size()
    .rename(columns={"size": "run_count"})
    .sort_values("run_count", ascending=False)
)

fig = px.bar(
    scenario_counts_df,
    x="run_count",
    y="case_type",
    orientation="h",
    title="Synthetic simulation coverage by generated case type",
    text="run_count",
    color="run_count",
    color_continuous_scale="Teal",
)
fig.update_layout(height=max(420, 28 * len(scenario_counts_df)), margin=dict(l=20, r=20, t=60, b=30))
fig.update_yaxes(title="", categoryorder="total ascending")
fig.update_xaxes(title="Run count")
fig.show()

display(scenario_counts_df.head(15))
```

### `case_type` 是什麼意思

`case_type` 是產生器給的情境標籤。它描述在任何 eval 或分群發生之前，swarm 被要求處理的是哪一種業務情境。

這份資料裡的例子：

- `clean_simple`：相對單純的訂單，正確的行為通常是不做多餘的 review 就完成。
- `validation_block_simple`：配置有 validation 問題，所以 swarm 應該避免過度自信地放行。
- `supplier_substitution_compound`：零組件供應造成替代決策，常常連帶影響後續的分派和排程。
- `pricing_exception_compound`：定價、優惠或毛利政策需要 specialist review。
- `regional_compliance_compound`：訂單需要地區政策或法規的處理。

上面的長條圖是涵蓋度的視圖。它顯示模擬是否產生了足夠多樣的情境，能在不同業務壓力下評估 swarm。好的 macro-eval 資料集要同時有一般案例和壓力案例，因為要能比較不同設定下的行為，重複出現的模式才有意義。


```python
CASE_TYPE_DESCRIPTIONS = {
    "clean_simple": "Straightforward order; should usually complete with minimal routing.",
    "validation_block_simple": "Configuration or buildability issue; should avoid unsupported release.",
    "release_block_simple": "Release readiness is blocked; should defer or request review.",
    "capacity_hold_simple": "Factory capacity or scheduling pressure; should route to fulfillment planning.",
    "pricing_exception_compound": "Pricing, incentives, margin, or tariff pressure; should involve pricing/policy owners.",
    "escalation_resume_compound": "An escalation or review flow needs to resume cleanly.",
    "supplier_substitution_compound": "Supplier availability forces substitution or procurement planning.",
    "regional_compliance_compound": "Regional compliance or policy constraints affect release.",
    "clarification_needed_compound": "Customer intent or configuration details are ambiguous.",
    "schedule_incentive_compound": "Timing, scheduling, and incentive windows interact.",
    "tradeoff_recommended_compound": "The system should weigh competing business tradeoffs.",
    "dual_failure_recovery_compound": "Multiple failures require coordinated recovery.",
    "ambiguous_customer_intent_compound": "The customer request is underspecified or conflicting.",
    "conflicting_multi_agent_compound": "Specialists may surface conflicting recommendations.",
}

case_type_guide_df = scenario_counts_df.copy()
case_type_guide_df["plain_english"] = case_type_guide_df["case_type"].map(CASE_TYPE_DESCRIPTIONS).fillna(
    "Generated scenario type from the synthetic simulation."
)
display(case_type_guide_df.head(12))
```

上面的表把產生器的標籤轉成業務語言。這很重要，因為同一個後續模式在不同設定下意義不同。供應商替代案例裡的履約改派可能是對的，同樣的改派出現在乾淨案例裡，就可能是不必要的複雜度。


## 3. 用 Promptfoo 做低層 Agent Evals

成熟的 multi-agent 系統不該只靠檢查最終答案。每個啟用的 agent 通常都需要自己的 evals：這個 specialist 有沒有用對證據、呼叫對 tool、遵守政策、在對的時間 handoff，並產出系統其他部分可以信任的輸出？

Promptfoo 在這個 notebook 裡扮演這個角色。它代表低層的 eval 層，在實際的 production workflow 裡通常會放在 agent 旁邊。在線上系統裡，有些檢查可能即時跑，有些非同步跑，有些抽樣給人工 review。實作細節沒那麼重要，重要的是約定：每次 run 都該帶著 eval 訊號，說明在 agent 和 workflow 層級哪些地方看起來正確、有風險或有錯。

在這份資料裡，Promptfoo 用一組問題替完成的 trace 評分，這些問題對應團隊在真實系統裡會建的 agent 層級 evals：
- 最終決策有沒有順著當前的問題得出？
- 系統有沒有遵守定價、關稅、優惠、地區和政策的限制？
- orchestrator 有沒有啟用該案例所暗示的 specialist？
- 這次 run 有沒有回應有日期的市場訊號，而不是把世界當成靜止的？
- review 或升級處理跟風險成不成比例？

這些檢查產生 `eval_finding`。失敗的低層 eval 是一個局部訊號：一條 trace、一個 rubric、一個症狀。後面的 macro-eval 章節要問的是，這些局部訊號放大到整批資料會變成什麼。它們是隨機散落，還是顯露出重複的行為模式，指向特定的 agent、handoff、tool 或業務政策？


```python
PROMPTFOO_RUBRICS = [
    ("final_decision_quality", "Final decision is supported by the active issues, terminal state, and agent outputs."),
    ("policy_compliance_correctness", "Policy, tariff, incentive, and regional compliance context is handled correctly."),
    ("routing_specialist_activation", "Specialist routing matches the issues present in the bundle."),
    ("market_drift_awareness", "Changing market conditions and dated environment signals are noticed."),
    ("review_appropriateness", "Review and escalation behavior is proportionate to the case risk."),
]
PROMPTFOO_ASSERTION_FALLBACK = {
    f"assertion_{idx}": metric for idx, (metric, _) in enumerate(PROMPTFOO_RUBRICS, start=1)
}


def clean_metric_name(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value)
    return PROMPTFOO_ASSERTION_FALLBACK.get(text, text)


def clean_metric_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [metric for item in values if (metric := clean_metric_name(item))]


def clean_metric_dict(values: Any) -> dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    return {clean_metric_name(key) or str(key): value for key, value in values.items()}


def clean_promptfoo_labels(labels_df: pd.DataFrame) -> pd.DataFrame:
    if labels_df.empty:
        return labels_df
    cleaned = labels_df.copy()

    # Accept older draft label files that used metric/passed/score/reason columns.
    if "promptfoo_pass" not in cleaned.columns and "passed" in cleaned.columns:
        cleaned["promptfoo_pass"] = cleaned["passed"]
    if "promptfoo_failed_checks" not in cleaned.columns:
        if "metric" in cleaned.columns:
            cleaned["promptfoo_failed_checks"] = cleaned.apply(
                lambda row: [] if bool(row.get("promptfoo_pass", True)) else [row.get("metric")],
                axis=1,
            )
        else:
            cleaned["promptfoo_failed_checks"] = [[] for _ in range(len(cleaned))]
    if "promptfoo_score_mean" not in cleaned.columns and "score" in cleaned.columns:
        cleaned["promptfoo_score_mean"] = cleaned["score"]
    if "promptfoo_primary_finding" not in cleaned.columns:
        if "metric" in cleaned.columns:
            cleaned["promptfoo_primary_finding"] = cleaned.apply(
                lambda row: None if bool(row.get("promptfoo_pass", True)) else row.get("metric"),
                axis=1,
            )
        else:
            cleaned["promptfoo_primary_finding"] = None
    if "promptfoo_check_scores" not in cleaned.columns:
        cleaned["promptfoo_check_scores"] = cleaned.apply(
            lambda row: {row.get("metric", "unknown"): row.get("score")} if "score" in cleaned.columns else {},
            axis=1,
        )
    if "promptfoo_rationales" not in cleaned.columns:
        cleaned["promptfoo_rationales"] = cleaned.apply(
            lambda row: {row.get("metric", "unknown"): row.get("reason")} if "reason" in cleaned.columns else {},
            axis=1,
        )

    cleaned["promptfoo_pass"] = cleaned["promptfoo_pass"].astype("boolean")
    cleaned["promptfoo_primary_finding"] = cleaned["promptfoo_primary_finding"].apply(clean_metric_name)
    cleaned["promptfoo_failed_checks"] = cleaned["promptfoo_failed_checks"].apply(clean_metric_list)
    cleaned["promptfoo_check_scores"] = cleaned["promptfoo_check_scores"].apply(clean_metric_dict)
    cleaned["promptfoo_rationales"] = cleaned["promptfoo_rationales"].apply(clean_metric_dict)
    return cleaned


rubric_df = pd.DataFrame(PROMPTFOO_RUBRICS, columns=["rubric", "plain_english_question"])
display(rubric_df)

promptfoo_labels_df = clean_promptfoo_labels(load_promptfoo_label_rows(PROMPTFOO_LABELS_PATH))

if promptfoo_labels_df.empty:
    display(Markdown("No Promptfoo labels were found. The notebook will continue with deterministic review and runtime signals only."))
else:
    pass_counts_df = (
        promptfoo_labels_df["promptfoo_pass"]
        .map({True: "pass", False: "fail"})
        .fillna("unknown")
        .value_counts()
        .rename_axis("promptfoo_result")
        .reset_index(name="trace_count")
    )
    display(Markdown(f"Loaded `{len(promptfoo_labels_df):,}` Promptfoo label rows from `{display_path(PROMPTFOO_LABELS_PATH)}`."))
    display(pass_counts_df)

    fig = px.pie(
        pass_counts_df,
        names="promptfoo_result",
        values="trace_count",
        title="Promptfoo grading result across bundle-backed traces",
        color="promptfoo_result",
        color_discrete_map={"pass": "#4daf4a", "fail": "#e41a1c", "unknown": "#999999"},
        hole=0.45,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.show()

    failed_metric_df = (
        promptfoo_labels_df.explode("promptfoo_failed_checks")
        .dropna(subset=["promptfoo_failed_checks"])
        .groupby("promptfoo_failed_checks", as_index=False)
        .size()
        .rename(columns={"promptfoo_failed_checks": "rubric", "size": "failed_trace_count"})
        .sort_values("failed_trace_count", ascending=False)
    )
    display(failed_metric_df)

    if not failed_metric_df.empty:
        fig = px.bar(
            failed_metric_df,
            x="failed_trace_count",
            y="rubric",
            orientation="h",
            title="Which lower-level rubric failed most often?",
            text="failed_trace_count",
            color="failed_trace_count",
            color_continuous_scale="Reds",
        )
        fig.update_layout(height=360, margin=dict(l=20, r=20, t=60, b=30))
        fig.update_yaxes(title="", categoryorder="total ascending")
        fig.update_xaxes(title="Failed traces")
        fig.show()
```

### 解讀 Promptfoo 的輸出

圓餅圖是最簡單的低層成績單：把通過所有 rubric 檢查的 trace，跟至少有一項檢查失敗的 trace 分開。在線上的 multi-agent 系統裡，這一層可以告訴我們，在做任何 macro 分析之前，哪些 run 值得先關注。

失敗 rubric 的長條圖回答一個更有用的問題：哪一類 agent 或 workflow 問題最常出現？在這份資料裡，最終決策品質是最主要的低層 finding，政策正確性、review 恰當性和市場變動意識也都有出現。這表示 macro 層應該少關注零星的語法錯誤，多關注重複的決策模式。

這是通往 macro evals 的橋。Promptfoo 給每條 trace 局部的 eval labels。notebook 其餘部分要問的是，這些 labels 在整批資料裡怎麼組織起來。換句話說，agent 層級的 evals 產生原始訊號，macro evals 把很多這樣的訊號變成系統重複行為的地圖。


## 4. 建立分析用資料集

現在把 run bundle 正規化成兩張分析用的表：

- `traces_df`：一個 run 一列，有 metadata、結果、findings 和文件欄位。
- `events_df`：一個正規化後的 trace event 一列，包含 handoff、tool call、狀態事件、model response 和 review/finding 標記。

我們也建 trace 文件。文件是 BERTopic 風格那一節要拿來分群的建模對象。notebook 用 `doc_structured_summary`，因為它夠精簡，同時保留了情境、分派、狀態轉換、handoff、findings 和最終狀態。

公開的分析路徑是：

`case_type -> run_outcome -> eval_finding -> behavior_pattern`

前三個標籤在分群前就已知，第四個是探索之後才出現。


```python
OUTCOME_GROUP_MAP = {
    "completed": "successful_completion",
    "awaiting_review": "review_escalation",
    "blocked": "hard_failure",
    "failed": "hard_failure",
}
SEVERITY_BY_OUTCOME = {
    "successful_completion": ("low", 1.0),
    "review_escalation": ("medium", 2.0),
    "in_progress": ("medium", 1.5),
    "blocked": ("high", 2.5),
    "hard_failure": ("high", 3.0),
}


def local_bundle_path(result_row: dict[str, Any]) -> Path:
    return BUNDLE_DIR / Path(str(result_row["bundle_path"])).name


def load_normalized_bundle_tables(results: list[dict[str, Any]], limit: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected_rows = [row for row in results if result_run_id(row) and row.get("bundle_path")]
    if limit is not None:
        selected_rows = selected_rows[:limit]

    normalized = []
    for record_index, result_row in enumerate(selected_rows, start=1):
        bundle_path = local_bundle_path(result_row)
        if not bundle_path.is_file():
            continue
        bundle = read_json(bundle_path)
        normalized.append(normalize_bundle(bundle, result_row, record_index, bundle_path))

    trace_rows = [trace_row for trace_row, _ in normalized]
    event_rows = [event for _, trace_events in normalized for event in trace_events]
    traces = pd.DataFrame(trace_rows)
    events = pd.DataFrame(event_rows)

    if not events.empty:
        events["ts"] = pd.to_datetime(events["ts"], utc=True, errors="coerce")
        events["ended_at"] = pd.to_datetime(events["ended_at"], utc=True, errors="coerce")
        events = events.sort_values(["trace_id", "sequence_index", "ts", "event_id"]).reset_index(drop=True)
    return traces, events


load_started = perf_counter()
traces_df, events_df = load_normalized_bundle_tables(results_rows, limit=TRACE_LIMIT)
print(f"Loaded {len(traces_df):,} normalized traces and {len(events_df):,} normalized events in {perf_counter() - load_started:.1f}s.")

result_metadata_cols = [
    "run_id",
    "market_regime",
    "price_regime",
    "schedule_regime",
    "agent_version_set",
    "orchestrator_mode",
    "rogue_window_id",
    "factory_release_state",
    "trace_family",
    "specialist_activations",
    "environment_event_ids",
]
result_metadata_df = pd.DataFrame(results_rows)
result_metadata_cols = [column for column in result_metadata_cols if column in result_metadata_df.columns]
if "run_id" in result_metadata_cols:
    traces_df = traces_df.merge(
        result_metadata_df[result_metadata_cols].drop_duplicates(subset=["run_id"]),
        on="run_id",
        how="left",
        suffixes=("", "_result"),
    )
    for column in result_metadata_cols:
        if column == "run_id":
            continue
        result_col = f"{column}_result"
        if result_col in traces_df.columns:
            traces_df[column] = traces_df[column].combine_first(traces_df[result_col]) if column in traces_df.columns else traces_df[result_col]
            traces_df = traces_df.drop(columns=[result_col])

for column, default in {
    "market_regime": "unknown",
    "price_regime": "unknown",
    "schedule_regime": "unknown",
    "agent_version_set": "unknown",
    "orchestrator_mode": "unknown",
}.items():
    if column not in traces_df.columns:
        traces_df[column] = default

sqlite_enrichment_cols = [
    "run_id",
    "sqlite_status",
    "sqlite_terminal_state",
    "scenario_family",
    "validation_outcome",
    "review_status",
    "review_decision",
    "triage_outcome",
    "market_regime",
    "price_regime",
    "schedule_regime",
    "agent_version_set",
    "orchestrator_mode",
    "rogue_window_id",
    "factory_release_state",
    "trace_family",
    "loop_count",
    "retry_count",
    "arbitration_count",
    "compound_issue_count",
    "findings_count_sqlite",
]

if not sqlite_runs_df.empty:
    traces_df = traces_df.merge(sqlite_runs_df[sqlite_enrichment_cols], on="run_id", how="left", suffixes=("", "_sqlite"))

    for column in [
        "scenario_family",
        "validation_outcome",
        "review_status",
        "review_decision",
        "triage_outcome",
        "market_regime",
        "price_regime",
        "schedule_regime",
        "agent_version_set",
        "orchestrator_mode",
        "rogue_window_id",
        "factory_release_state",
        "trace_family",
        "loop_count",
        "retry_count",
        "arbitration_count",
        "compound_issue_count",
    ]:
        sqlite_col = f"{column}_sqlite"
        if sqlite_col in traces_df.columns:
            traces_df[column] = traces_df[sqlite_col].combine_first(traces_df.get(column))
            traces_df = traces_df.drop(columns=[sqlite_col])

    traces_df["runtime_status"] = traces_df["sqlite_status"].combine_first(traces_df["runtime_status"])
    traces_df["terminal_state"] = traces_df["sqlite_terminal_state"].combine_first(traces_df["terminal_state"])
    traces_df["findings_count"] = traces_df["findings_count_sqlite"].combine_first(traces_df["findings_count"]).fillna(0)
else:
    traces_df["findings_count"] = traces_df.get("findings_count", pd.Series(0, index=traces_df.index)).fillna(0)

traces_df["outcome_group"] = traces_df["runtime_status"].map(OUTCOME_GROUP_MAP).fillna("unknown")
traces_df["severity_label"] = traces_df["outcome_group"].map(lambda value: SEVERITY_BY_OUTCOME.get(value, ("medium", 2.0))[0])
traces_df["severity_weight"] = traces_df["outcome_group"].map(lambda value: SEVERITY_BY_OUTCOME.get(value, ("medium", 2.0))[1])
traces_df["has_failure"] = (
    traces_df["outcome_group"].ne("successful_completion")
    | traces_df["validation_outcome"].fillna("passed").ne("passed")
    | traces_df["findings_count"].fillna(0).gt(0)
)
traces_df["impact_score"] = (
    traces_df["severity_weight"].fillna(1.0)
    * (1.0 + traces_df["findings_count"].fillna(0))
    * (1.0 + traces_df["loop_count"].fillna(0) / 4.0)
)

documents_df = build_trace_documents(traces_df, events_df)
traces_with_docs_df = traces_df.merge(documents_df, on="trace_id", how="left")
labeled_traces_df = add_public_label_columns(traces_with_docs_df, promptfoo_labels_df=promptfoo_labels_df)
labeled_traces_df["eval_finding"] = labeled_traces_df["eval_finding"].apply(lambda value: clean_metric_name(value) or "none")
labeled_traces_df["promptfoo_failed"] = labeled_traces_df.get("promptfoo_pass").eq(False)

analysis_profile_df = pd.DataFrame(
    [
        ("normalized_traces", len(labeled_traces_df)),
        ("normalized_events", len(events_df)),
        ("case_types", labeled_traces_df["case_type"].nunique()),
        ("run_outcomes", labeled_traces_df["run_outcome"].nunique()),
        ("eval_findings", labeled_traces_df["eval_finding"].nunique()),
        ("promptfoo_failed_traces", int(labeled_traces_df["promptfoo_failed"].sum())),
        ("failure_or_review_traces", int(labeled_traces_df["has_failure"].sum())),
    ],
    columns=["metric", "value"],
)
display(analysis_profile_df)
display(labeled_traces_df[["run_id", "case_type", "run_outcome", "eval_finding", "market_regime", "agent_version_set", "impact_score"]].head(10))
```

### 解讀 Analysis Profile

上面的 profile 確認低層 eval 層已經接到正規化後的 trace 上。重要的數字有：

- normalized traces：有 bundle 支撐、我們能檢視的資料；
- normalized events：這些 trace 背後的事件層級證據；
- case types：產生器產出的情境涵蓋度；
- Promptfoo 判失敗或帶有 review/failure 的 trace：跟 macro 探索最相關的低層訊號母體。

實際的數量取決於你跑完整的 notebook，還是設 `MACRO_EVALS_TRACE_LIMIT` 做 smoke test。範例列顯示 notebook 怎麼把原始資料簡化成好讀的 labels。舉例來說，一個以 review 收尾、帶 `final_decision_quality` finding 的 `pricing_exception_compound` 案例，在後面的流程裡就很容易追蹤。


```python
def humanize_label(value: Any, max_len: int = 48) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        text = "missing"
    else:
        text = str(value)
    text = text.replace("_", " ")
    return text if len(text) <= max_len else text[: max_len - 3].rstrip() + "..."


def plot_label_sankey(frame: pd.DataFrame, columns: list[str], title: str, min_count: int = 1):
    working = frame[columns].copy()
    for column in columns:
        working[column] = working[column].fillna("missing").astype(str)

    node_labels: list[str] = []
    node_lookup: dict[tuple[str, str], int] = {}
    sources: list[int] = []
    targets: list[int] = []
    values: list[int] = []

    def node_id(column: str, value: str) -> int:
        key = (column, value)
        if key not in node_lookup:
            node_lookup[key] = len(node_labels)
            node_labels.append(f"{column}: {humanize_label(value)}")
        return node_lookup[key]

    for left, right in zip(columns[:-1], columns[1:]):
        pairs = working.groupby([left, right]).size().reset_index(name="count")
        pairs = pairs[pairs["count"].ge(min_count)]
        for _, row in pairs.iterrows():
            sources.append(node_id(left, row[left]))
            targets.append(node_id(right, row[right]))
            values.append(int(row["count"]))

    fig = go.Figure(
        data=[
            go.Sankey(
                arrangement="snap",
                node=dict(label=node_labels, pad=14, thickness=14),
                link=dict(source=sources, target=targets, value=values),
            )
        ]
    )
    fig.update_layout(title=title, height=620, margin=dict(l=20, r=20, t=60, b=20))
    return fig


flow_sample_df = labeled_traces_df[["case_type", "run_outcome", "eval_finding"]].copy()
plot_label_sankey(
    flow_sample_df,
    ["case_type", "run_outcome", "eval_finding"],
    "Before clustering: generated case -> run outcome -> lower-level finding",
    min_count=3,
).show()

label_crosswalk_df = (
    labeled_traces_df.groupby(["case_type", "run_outcome", "eval_finding"], dropna=False)
    .size()
    .reset_index(name="trace_count")
    .sort_values("trace_count", ascending=False)
    .head(18)
)
display(label_crosswalk_df)
```

### 第一張 Sankey 圖告訴我們什麼

第一張 Sankey 圖是分群前的視圖。它顯示產生出來的 case type 怎麼流向 run outcome 和低層 findings。

從左往右看：

- 從某個 `case_type` 出發的寬帶，代表這個情境常出現；
- 分到 `run_outcome` 的分流，顯示這個情境傾向完成、暫停、被擋下還是失敗；
- 最後流入 `eval_finding` 的帶子，顯示附著了哪個低層 rubric 或 runtime 訊號。

這對團隊已經有用。業務人員可以問模擬有沒有產生對的壓力類型，AI 工程師可以問某些情境是不是過度產生同一種低層 finding。它還回答不了的是，這些 findings 是不是代表同一個底層行為模式，所以下一步要分群。


### Trace 文件：把 Run 變成可比較的文字

原始的 agent trace 太細，無法直接分群。它可能有數百個事件、很長的 model response、tool payload 和重複的狀態更新。建構文件這一步，是把每個 run 壓成可比較的檢視，同時保留對 macro evals 重要的資訊。

好的 trace 文件包含：

- 業務設定（`case_type`、選到的路徑、當時的環境訊號）；
- run 的結果和嚴重程度；
- 重要的 handoff 和 specialist 啟用；
- review/finding 標記；
- 簡短的狀態轉換摘要。

文件的樣子決定了分群演算法被允許注意到什麼。把 agent handoff 放進去，有助於 macro eval 找出分派模式。把環境訊號放進去，有助於找出市場變動造成的失敗。所以 trace 文件的品質是 eval 設計的一部分，不是機械式的清理。


### Failure 與 Focus-Event 詞彙表

原始 trace 有很多事件層級的標籤。為了讓 notebook 好讀，我們不要求讀者全部學會。AgentTrace 風格那一節主要關心 focus event：trace 裡系統看起來需要注意的明顯時刻。

在這個模擬裡，常見的 focus-event 訊號有：

- `review finding`：review 或 validation 的環節記錄了一個問題。
- `review required` 或 `awaiting_review`：因為模擬的業務流程要求 review，run 暫停了。
- `failed` 或 `blocked`：run 走到一個退化的終止狀態。
- `triage route` 或改派訊號：因為需要另一個負責人處理，workflow 轉向了。
- tool 警告或政策標記：結構化的 tool 輸出顯示有風險、模糊或政策限制。

這些是 observability 訊號，不是根本原因的證明。它們告訴 diagnosis 這一步要從哪裡錨定、往回搜尋。


```python
focus_event_guide_df = pd.DataFrame(
    [
        ("review finding", "An issue was recorded by review, validation, or a grading surface.", "Start from this when the trace has an explicit finding."),
        ("review required / awaiting_review", "The simulated business process paused for review.", "Check whether review was justified by the active risk."),
        ("failed / blocked", "The run ended in a degraded terminal state.", "Walk backward to the last handoff, tool, or specialist decision."),
        ("triage route / reroute", "The workflow changed ownership or path.", "Inspect whether routing matched the case type and environment signals."),
        ("tool warning / policy marker", "A structured tool exposed risk or policy context.", "Check whether later decisions used or ignored that signal."),
    ],
    columns=["focus_event_signal", "meaning", "how_to_use_it"],
)
display(focus_event_guide_df)
```

```python
example_candidates = labeled_traces_df[
    labeled_traces_df["promptfoo_failed"].fillna(False)
    & labeled_traces_df[DISCOVERY_DOC_COLUMN].fillna("").astype(str).str.len().gt(0)
]
if example_candidates.empty:
    example_candidates = labeled_traces_df[labeled_traces_df[DISCOVERY_DOC_COLUMN].fillna("").astype(str).str.len().gt(0)]

example_row = example_candidates.sort_values("impact_score", ascending=False).iloc[0]
display(Markdown(
    f"**Example trace document**  \n"
    f"`case_type={example_row['case_type']}` | `run_outcome={example_row['run_outcome']}` | "
    f"`eval_finding={example_row['eval_finding']}` | `impact_score={example_row['impact_score']:.2f}`"
))
print(str(example_row[DISCOVERY_DOC_COLUMN])[:2400])
```

上面的範例文件是一條 trace 被呈現成精簡的敘述。它刻意比散文更密，但比原始的事件 log 更容易比較。改用這套流程時，要花真正的時間在建構文件。通常文件做得好，比用更複雜的分群設定更能得到有用的行為模式。


## 5. BERTopic 風格的探索

探索這一步受 BERTopic 一系列方法啟發。高層的想法是模組化的：

1. **把每份 trace 文件表示成向量。** 如果 trace $i$ 的文件是 $d_i$，embedding 模型產生向量 $e_i = f(d_i)$。
2. **降低向量的維度。** 像 UMAP 這樣的 reducer 把 $e_i$ 映射到低維的點 $z_i$，並保留有用的局部鄰近關係。
3. **對密集區域分群。** 像 HDBSCAN 這樣的密度分群器把相近的點分成一群，並且可以把離群點標成雜訊。
4. **表示每個 topic。** 對每個 cluster，計算能把它和其餘語料區分開來的詞。

這個 notebook 用 helper module 讓實作保持精簡，但主要的數學想法都看得到：

- 當一條 trace 的文件向量在降維後的空間裡靠近其他 trace 向量，它就屬於 cluster $k$。
- 一個詞適合用來標記 cluster $k$，是當它在 $k$ 裡常出現，在其他地方較少出現。
- 一個簡單、考慮類別的詞分數是：

$$
score(t, k) = tf(t, k) \times \log\left(\frac{1 + N}{1 + df(t)}\right)
$$

其中 $tf(t, k)$ 是詞 $t$ 在 cluster $k$ 裡的詞頻，$df(t)$ 是詞出現在其中的 cluster/文件數，$N$ 是比較母體的大小。實際實作可以不同，但直覺是穩定的：label 應該描述是什麼讓這個 cluster 與眾不同。

最後，我們用一個 triage 指標替 pattern 排名：

$$
impact\_score(k) = prevalence\_share(k) \times severity\_weighted\_prevalence(k)
$$

這不是通用的風險公式。它是實用的優先排序分數：一個 pattern 同時常見又嚴重時，就更重要。


```python
discovery_input_df = labeled_traces_df.loc[
    labeled_traces_df["has_failure"]
    | labeled_traces_df["promptfoo_failed"].fillna(False)
    | labeled_traces_df["run_outcome"].isin(["review_needed", "blocked", "runtime_error"])
].copy()
discovery_input_df = discovery_input_df.loc[
    discovery_input_df[DISCOVERY_DOC_COLUMN].fillna("").astype(str).str.len().gt(0)
].copy()

if len(discovery_input_df) < 8:
    broader_input_df = labeled_traces_df.loc[
        labeled_traces_df[DISCOVERY_DOC_COLUMN].fillna("").astype(str).str.len().gt(0)
    ].copy()
    if len(broader_input_df) > len(discovery_input_df):
        display(Markdown(
            "The current sample has very few failure/review traces, so discovery is broadened to all traces with documents."
        ))
        discovery_input_df = broader_input_df

if len(discovery_input_df) < 2:
    raise ValueError("Macro discovery needs at least two trace documents. Increase MACRO_EVALS_TRACE_LIMIT or run the full notebook.")

effective_min_cluster_size = min(DISCOVERY_MIN_CLUSTER_SIZE, max(2, len(discovery_input_df) // 4))
effective_n_neighbors = min(30, max(2, len(discovery_input_df) - 1))

print(f"Discovery input traces: {len(discovery_input_df):,}")
print(f"Discovery min_cluster_size: {effective_min_cluster_size}")
print(f"Discovery n_neighbors: {effective_n_neighbors}")

discovery_started = perf_counter()
discovery = run_macro_discovery(
    discovery_input_df,
    document_column=DISCOVERY_DOC_COLUMN,
    min_cluster_size=effective_min_cluster_size,
    n_neighbors=effective_n_neighbors,
    top_n_terms=8,
    random_state=RANDOM_STATE,
    failure_only=False,
)
discovery_seconds = perf_counter() - discovery_started

topic_info_df = discovery.topic_info_df.copy()
work_df = discovery.trace_topic_df.copy()
work_df["behavior_pattern"] = work_df["topic_label"].fillna(work_df["topic_id"].astype(str))
topic_info_df["behavior_pattern"] = topic_info_df["topic_label"].fillna(topic_info_df["topic_id"].astype(str))

display(
    pd.DataFrame(
        [
            ("discovery_seconds", round(discovery_seconds, 2)),
            ("input_traces", len(discovery_input_df)),
            ("topics_including_noise", topic_info_df["topic_id"].nunique()),
            ("non_noise_patterns", int(topic_info_df["topic_id"].ne(-1).sum())),
        ],
        columns=["metric", "value"],
    )
)

display(
    topic_info_df[
        ["topic_id", "behavior_pattern", "trace_count", "prevalence", "impact_score", "dominant_owner", "keywords_text"]
    ].sort_values("impact_score", ascending=False).head(12)
)
```

### 解讀探索的輸出

探索的摘要告訴我們有多少條 trace 被分群，以及找回了多少個非雜訊的行為模式。我們只對已經有 failure、review、runtime 或 Promptfoo 訊號的 trace 做探索，因為這篇專注在系統需要關注的地方。

topic 表要當成 triage 看板來讀：

- `trace_count` 和 `prevalence` 告訴我們這個 pattern 多常出現。
- `severity_weighted_prevalence` 告訴我們這個 pattern 裡的 trace 傾向多嚴重。
- `impact_score` 把 prevalence 和嚴重度合成一個排名。
- `dominant_owner` 是啟發式的負責人標籤，不是指派。
- `keywords_text` 給出讓這個 pattern 與眾不同的詞。

高影響的行為模式不一定就是 defect。它是 reviewer 該先看的地方，因為這個模式常見、後果嚴重，或兩者皆是。


```python
impact_explanation_df = (
    topic_info_df[topic_info_df["topic_id"].ne(-1)]
    [["behavior_pattern", "trace_count", "prevalence", "severity_weighted_prevalence", "impact_score"]]
    .sort_values("impact_score", ascending=False)
    .head(8)
    .copy()
)
impact_explanation_df["formula"] = "prevalence x severity_weighted_prevalence"
display(impact_explanation_df)
```

上面的表讓 impact score 變得具體。一個 pattern 排名高，可能因為它出現在很多 trace，也可能因為它集中了較高嚴重度的 trace，或兩者都是。在汽車 configurator 的情境裡，這有助於分辨罕見的邊緣案例，和可能影響很多訂單、反覆發生的營運行為。


```python
leaderboard_fig = plot_topic_leaderboard(topic_info_df[topic_info_df["topic_id"].ne(-1)].copy(), top_n=10)
leaderboard_fig.update_layout(title_text="Behavior patterns by weighted impact")
leaderboard_fig.show()

scatter_df = discovery.topic_assignments.copy()
if "topic_label" in scatter_df.columns:
    scatter_df["behavior_pattern"] = scatter_df["topic_label"].fillna(scatter_df["topic_id"].astype(str))
    scatter_fig = plot_topic_scatter(
        scatter_df,
        color_col="behavior_pattern",
        hover_cols=("run_id", "case_type", "run_outcome", "eval_finding"),
        title="Trace map after discovery",
    )
    scatter_fig.update_layout(legend_title_text="Behavior pattern")
    scatter_fig.show()
```

### 解讀 Leaderboard 和 Trace Map

leaderboard 是投資組合式的視圖：依加權影響替行為模式排名。用它決定哪個 pattern 該先得到人的關注。

trace map 是幾何視圖：每個點是一份 trace 文件，放在跟它文字相近的 trace 附近。相鄰的點常有相同的分派路徑、findings 或環境訊號。顏色代表探索出來的行為模式。把這張圖當成診斷用，不是精確的地理位置。它的作用是揭露表格裡可能很難看出的 cluster 和離群點。

在這份資料裡，像履約改派、定價漂移、法規關卡和輪圈/內裝不匹配這些 pattern，對應到看得出來的業務問題。這是低層 evals 第一次變成 macro 層級的故事：很多案例裡都看得到重複的 agent 行為。


```python
case_pattern_df = (
    work_df[work_df["topic_id"].ne(-1)]
    .groupby(["case_type", "behavior_pattern"], dropna=False)
    .size()
    .reset_index(name="trace_count")
)
if not case_pattern_df.empty:
    case_totals = case_pattern_df.groupby("case_type")["trace_count"].transform("sum")
    case_pattern_df["share_within_case_type"] = case_pattern_df["trace_count"] / case_totals
    display(case_pattern_df.sort_values(["share_within_case_type", "trace_count"], ascending=[False, False]).head(20))

    heatmap_input_df = case_pattern_df.rename(
        columns={
            "case_type": "slice_value",
            "share_within_case_type": "slice_share",
        }
    )
    heatmap_input_df["lift"] = heatmap_input_df["slice_share"] / heatmap_input_df.groupby("behavior_pattern")["trace_count"].transform(lambda s: s.sum() / len(work_df))
    plot_topic_heatmap(
        heatmap_input_df,
        row_col="behavior_pattern",
        col_col="slice_value",
        value_col="slice_share",
        title="Behavior pattern concentration by generated case type",
        top_n_rows=8,
        top_n_cols=10,
    ).show()

pattern_eval_df = (
    work_df[work_df["topic_id"].ne(-1)]
    .assign(promptfoo_failed=lambda df: df["promptfoo_pass"].eq(False))
    .groupby(["behavior_pattern", "eval_finding"], dropna=False)
    .agg(trace_count=("trace_id", "count"), promptfoo_fail_rate=("promptfoo_failed", "mean"))
    .reset_index()
    .sort_values(["trace_count", "promptfoo_fail_rate"], ascending=False)
    .head(20)
)
display(pattern_eval_df)
```

### 解讀 Case-Type Heatmap

heatmap 問的是：哪些產生出來的情境集中了哪些行為模式？

每一列是一個行為模式，每一欄是一個 case type。顏色越深或數值越大，代表該 pattern 在那個情境切片裡越常見。這有助於分辨預期的行為和意外的行為。舉例來說，履約改派的 pattern 在供應商替代或產能案例裡可能是預期的，出現在乾淨案例裡就比較可疑。

圖下方的表把 pattern 連回低層 findings。如果某個行為模式反覆帶有 `final_decision_quality` finding，AI 工程師可能會檢查 prompt、tool schema 或 handoff 政策。如果 pattern 對應到某個業務特有的 case type，產品或營運人員可以問，模擬的政策本身實不實際。


### 跨切片比較 Pattern

這一步放在這裡，是因為 BERTopic 風格的探索剛好替每條有風險的 trace 指定了 `behavior_pattern`。分群之前，我們能比較產生的案例、結果和低層 eval findings。分群之後，可以問更有用的 macro-eval 問題：**每個探索出來的行為模式集中在哪裡？**

這個比較不是 BERTopic 論文裡的核心公式。它是我們在 topic 指派之後加上的簡單 cohort 分析層。想法是比較兩個占比：

- **overall pattern share**：在所有被分群的 trace 裡，屬於這個行為模式的占比是多少？
- **slice pattern share**：在一個切片裡，例如 `case_type = supplier_substitution_compound`，屬於這個行為模式的占比是多少？

然後計算：

$$
lift = \frac{slice\ pattern\ share}{overall\ pattern\ share}
$$
Lift 是 `1.0`，代表這個 pattern 在那個切片出現的頻率跟整體差不多。高於 `1.0`，代表它集中在那個切片。低於 `1.0`，代表它在那裡比較少見。

在 macro evals 裡，這是從探索走向行動的橋。如果能說出一個行為模式出現在哪裡（某個產生的情境、某個 agent 版本、某個編排模式、某個市場狀態或某個 review 狀態），它就比較容易調查。


```python
slice_lift_source_df = work_df[work_df["topic_id"].ne(-1)].copy()
overall_pattern_share = (
    slice_lift_source_df["behavior_pattern"]
    .value_counts(normalize=True)
    .rename("overall_pattern_share")
    .reset_index()
    .rename(columns={"index": "behavior_pattern"})
)
slice_pattern_counts_df = (
    slice_lift_source_df.groupby(["case_type", "behavior_pattern"], dropna=False)
    .size()
    .reset_index(name="trace_count")
)
slice_totals = (
    slice_lift_source_df.groupby("case_type", dropna=False)
    .size()
    .rename("slice_total")
    .reset_index()
)
slice_lift_df = (
    slice_pattern_counts_df
    .merge(slice_totals, on="case_type", how="left")
    .merge(overall_pattern_share, on="behavior_pattern", how="left")
)
slice_lift_df["slice_pattern_share"] = slice_lift_df["trace_count"] / slice_lift_df["slice_total"]
slice_lift_df["lift"] = slice_lift_df["slice_pattern_share"] / slice_lift_df["overall_pattern_share"].replace(0, np.nan)
slice_lift_view_df = (
    slice_lift_df[slice_lift_df["trace_count"].ge(5)]
    .sort_values(["lift", "trace_count"], ascending=[False, False])
    .head(12)
    .loc[:, ["case_type", "behavior_pattern", "trace_count", "slice_pattern_share", "overall_pattern_share", "lift"]]
)
display(slice_lift_view_df)
```

上面的表要當成調查佇列來讀。它標出特別集中在某個 `case_type` 的行為模式，同時要求至少有少量支持的 trace。舉例來說，如果某個分派 pattern 在供應商替代案例裡比整體常見得多，就表示團隊在把它當成通用的系統問題之前，應該先檢查供應商 tool、採購 handoff 和履約政策。


```python
plot_label_sankey(
    work_df[["case_type", "run_outcome", "eval_finding", "behavior_pattern"]].copy(),
    ["case_type", "run_outcome", "eval_finding", "behavior_pattern"],
    "After clustering: generated case -> outcome -> eval finding -> behavior pattern",
    min_count=4,
).show()

public_label_view_df = (
    work_df[["run_id", "case_type", "run_outcome", "eval_finding", "behavior_pattern", "impact_score"]]
    .sort_values("impact_score", ascending=False)
    .head(12)
)
display(public_label_view_df)
```

### 第二張 Sankey 圖多了什麼

第二張 Sankey 圖把探索出來的 `behavior_pattern` 加成最後一步：

`case_type -> run_outcome -> eval_finding -> behavior_pattern`

這是 macro-eval 的關鍵動作。前三個標籤描述產生的設定、結局和局部症狀。最後一個標籤顯示這些局部症狀是不是收斂成較少數、重複出現的營運模式。

業務人員可以用它問「哪些訂單情境製造了最多重複的營運問題？」AI 工程師可以用它問「哪些低層 findings 其實是同一個分派或決策模式？」兩種視角都有用，Sankey 給了他們共同的地圖。


## 6. AgentTrace 風格的 Diagnosis

探索告訴我們什麼在重複。Diagnosis 問的是該先檢查哪裡。

對選定的行為模式，我們重建一個輕量的執行圖：

$$
G = (V, E)
$$

其中每個節點 $v \in V$ 是一個正規化的 trace event，每條邊 $e \in E$ 透過時間順序、handoff、tool call 和附近的執行上下文把事件連起來。接著選一個 focus event，也叫 anchor。在這個模擬裡，focus event 通常是 review/finding 標記、跟 failure 有關的狀態，或後期的決策事件。

從那個 anchor 出發，diagnosis 沿著圖往回走，替上游的嫌疑對象打分數。分數刻意做得可以解釋：

$$
suspect\_score =
0.4 \cdot proximity +
0.3 \cdot frequency +
0.2 \cdot bridge +
0.1 \cdot role
$$

- **Proximity** 獎勵靠近 focus event 的事件。
- **Frequency** 獎勵在同一個行為模式的抽樣 trace 裡反覆出現的事件。
- **Bridge** 獎勵連接執行圖不同部分的事件。
- **Role** 獎勵 agent/tool 角色看起來跟該 finding 有關的事件。

這不是因果關係的證明。它是把「這個 pattern 很重要」變成「先檢查這些 agent、tool、handoff 或 review 政策」的辦法。


```python
focus_topic = pick_focus_topic(topic_info_df, exclude_noise=True)
focus_topic_id = focus_topic["topic_id"]

display(Markdown(
    f"Investigating behavior pattern `{focus_topic['behavior_pattern']}` "
    f"from topic `{focus_topic_id}` with `{int(focus_topic['trace_count'])}` traces."
))
display(focus_topic[["topic_id", "behavior_pattern", "trace_count", "prevalence", "impact_score", "dominant_owner", "keywords_text"]].to_frame("value"))

root_cause = drill_down_topic_root_causes(
    discovery,
    events_df=events_df,
    topic_id=focus_topic_id,
    top_n_traces=12,
    max_depth=5,
)

def public_suspect_label(value: Any) -> str:
    text = str(value or "unknown")
    if text.startswith("failure: "):
        return "eval/review signal: " + text.removeprefix("failure: ")
    if text.startswith("handoff: "):
        return "handoff involving " + text.removeprefix("handoff: ")
    if text.startswith("function: "):
        return "tool/function call by " + text.removeprefix("function: ")
    if text.startswith("response: "):
        return "agent response by " + text.removeprefix("response: ")
    return text

if not root_cause.suspect_summary.empty:
    suspect_display_df = root_cause.suspect_summary.head(12).copy()
    suspect_display_df["reader_label"] = suspect_display_df["suspect_label"].apply(public_suspect_label)
    suspect_display_df["is_eval_or_review_signal"] = suspect_display_df["reader_label"].str.startswith("eval/review signal")
    display_columns = [
        column
        for column in [
            "reader_label",
            "node_kind",
            "agent_name",
            "tool_name",
            "lane_label",
            "mean_score",
            "trace_coverage_share",
        ]
        if column in suspect_display_df.columns
    ]
    display(suspect_display_df[display_columns])

    focus_signal_df = suspect_display_df[suspect_display_df["is_eval_or_review_signal"]].head(1)
    operational_suspect_df = suspect_display_df[~suspect_display_df["is_eval_or_review_signal"]].head(1)
    if not focus_signal_df.empty:
        focus_signal = focus_signal_df.iloc[0]
        operational_label = (
            operational_suspect_df.iloc[0]["reader_label"]
            if not operational_suspect_df.empty
            else "the next highest-ranked non-review event"
        )
        display(Markdown(
            "#### Reading the focus signal\n\n"
            f"The leading signal is `{focus_signal['reader_label']}` from `{focus_signal.get('agent_name', 'unknown')}`. "
            "In this simulation, a review finding means that a specialist or review surface recorded a structured issue while processing one customer order. "
            "For a fulfillment-reroute pattern, that signal is best read as the point where the workflow says: this order has enough supply, routing, policy, or review risk to deserve attention. "
            f"The first operational inspection target after that signal is `{operational_label}`."
        ))

    suspect_plot_df = root_cause.suspect_summary.head(10).copy()
    suspect_plot_df["suspect_label"] = suspect_plot_df["suspect_label"].apply(public_suspect_label)
    plot_suspect_leaderboard(suspect_plot_df).show()
else:
    display(Markdown("No repeated upstream suspects were recovered for this behavior pattern."))
```

### 解讀 Suspect Leaderboard

focus 行為模式是依 impact score 選出來的。依你跑完整資料集還是較小的 smoke-test 樣本，選到的 pattern 可能不同，但讀法一樣：從影響最高的 pattern 開始，檢視哪些 review 訊號、handoff、tool 或 specialist 回應反覆出現在 focus event 附近。

像 `eval/review signal: review finding` 這樣的列並不神秘。在模擬裡，review finding 是當 specialist 或 review 環節觀察到一個應該影響訂單決策的問題時，產生的結構化標記。它是我們往回追的終點：workflow 累積了足夠的證據，可以說「這張訂單需要注意」的那一刻。

更能採取行動的是那個標記周圍的營運事件：牽涉 orchestrator 的 handoff、monitor 或 orchestration agent 發出的 tool/function call、採購規劃的 handoff，以及相關的 specialist 回應。macro eval 指向這個 pattern 之後，這些就是人該檢查的地方。

從技術角度看，這個輸出告訴 AI 工程師該檢查：

- 點名的那些 agent 的 instructions 和 tool 約定；
- 重複出現的轉換周圍的 handoff 規則；
- 系統記錄 review 標記是不是太早或太晚；
- 某個 tool 輸出是不是被忽略或被過度加權。

從業務角度看，同一個輸出告訴營運或產品人員，哪個業務職能看起來擁有這個 pattern。履約、定價、法規或澄清的 pattern，應該讓對應的業務負責人加入下一次 review，不只是 prompt 工程師。


```python
if root_cause.selected_path_nodes:
    plot_root_cause_story(root_cause.__dict__, title="Representative path into the focus event").show()

if not root_cause.representative_trace_window.empty:
    plot_trace_swimlane(root_cause.representative_trace_window, title="Representative focus-event window").show()

if not root_cause.suspect_summary.empty:
    summary_suspects_df = root_cause.suspect_summary.copy()
    summary_suspects_df["reader_label"] = summary_suspects_df["suspect_label"].apply(public_suspect_label)
    review_signal_df = summary_suspects_df[summary_suspects_df["reader_label"].str.startswith("eval/review signal")].head(1)
    operational_target_df = summary_suspects_df[~summary_suspects_df["reader_label"].str.startswith("eval/review signal")].head(1)
    review_signal = review_signal_df.iloc[0] if not review_signal_df.empty else summary_suspects_df.iloc[0]
    operational_target = operational_target_df.iloc[0] if not operational_target_df.empty else summary_suspects_df.iloc[0]
    display(Markdown(
        "### Diagnosis summary\n\n"
        f"For behavior pattern `{focus_topic['behavior_pattern']}`, the focus signal is "
        f"`{review_signal['reader_label']}`. In the auto-order simulation, this means the trace reached a review/eval checkpoint where a specialist found an issue that could affect fulfillment or release. "
        f"The first operational target to inspect is `{operational_target['reader_label']}`. "
        "Read the story strip and swimlane as the path into that checkpoint: which agents handled the order, which handoffs occurred before the marker, and whether the workflow used the right supply, routing, and review signals before deciding what to do next."
    ))
```

### 解讀 Story Strip 和 Swimlane

story strip 是通往 focus event 的路徑。在這次 run 裡，focus event 是選定行為模式內的一個 review/eval 檢查點。這是模擬的業務流程在說，這張訂單有個值得 review 的問題。

swimlane 視圖保留更多時間結構。它依 lane 或 agent 顯示 focus event 周圍一段時間窗的事件，focus event 會被標亮。從左往右讀，就是訂單穿過 swarm 的過程：

- review finding 之前是哪個 specialist 處理訂單？
- orchestrator 有沒有在對的時間把工作分派給對的業務負責人？
- 有沒有 tool/function call 浮現了應該改變訂單決策的資訊？
- review 有沒有發生在 workflow 對放行、改派、定價、法規或客戶溝通的建議做出承諾之前？

對業務讀者來說，這張圖把抽象的 pattern 變成營運故事：這一批訂單反覆走到類似的 review 點。對 AI 工程師來說，它縮小了下一步的 debug 範圍：檢查 review 標記周圍的 orchestration 和 handoff 路徑，尤其是 diagnosis 摘要裡標出的第一個非 review 嫌疑對象。


## 7. 我們學到什麼，接下來做什麼

這份 cookbook 走過四個層次的證據：

1. **模擬設定：** 業務在供應、定價、產能、法規和市場條件變動下，產生電動車訂單案例。
2. **低層 evals：** Promptfoo 提供 agent/workflow 層級的 eval 訊號：決策品質、政策正確性、分派、市場意識和 review 恰當性。
3. **Macro 探索：** BERTopic 風格的分群把低層 findings 分成反覆出現的行為模式，並依影響排名。
4. **Trace diagnosis：** AgentTrace 風格的圖分析檢視一個高影響的 pattern，找出重複出現的上游嫌疑對象。

這個做法的規模化方式，是把人的注意力導向既常見又有後果的 pattern。reviewer 不用從頭讀數百條 trace，可以從一個行為模式開始，看代表性的例子，再決定哪個 agent、tool、handoff 或業務規則值得追蹤。

給 AI 工程團隊的實務下一步：

- 把最明確的低層 eval 失敗提升成 regression suite；
- 抽樣檢查一小批自動評分，校準 rubric 的嚴格度；
- 依模型版本、prompt 版本和 orchestration 模式追蹤行為模式；
- 為影響最高的 pattern 指派業務負責人；
- 改系統之前，先檢查排名最前面的嫌疑 agent、tool 和 handoff。

給業務人員的實務下一步：

- 判斷產生的 case type 是否符合真實的營運風險；
- 檢查高影響的 pattern 是否對應到重要的客戶或營運結果；
- 驗證 review 門檻有沒有產生預期的業務行為；
- 用 Sankey 和 heatmap 視圖決定哪些情境需要更好的政策或流程設計。

核心的結論很簡單：agent 層級的 evals 告訴我們哪些局部行為看起來有風險，macro evals 告訴我們這些風險放大到系統規模會變成什麼。

**延伸閱讀**

- OpenAI Agents SDK documentation: [Agents SDK use cases](https://developers.openai.com/api/docs/libraries#use-the-agents-sdk)
- BERTopic documentation: [overview](https://maartengr.github.io/BERTopic/index.html) and [algorithm walkthrough](https://maartengr.github.io/BERTopic/algorithm/algorithm.html)
- Promptfoo documentation: [OpenAI Agents provider](https://www.promptfoo.dev/docs/providers/openai-agents/) and [chat conversations](https://www.promptfoo.dev/docs/configuration/chat/)
- AgentTrace paper: [Causal Graph Tracing for Root Cause Analysis in Deployed Multi-Agent Systems](https://arxiv.org/abs/2603.14688)


## 貢獻者
這份 cookbook 是 OpenAI 和 Slalom 的共同合作成果。

- [Shikhar Kwatra](https://www.linkedin.com/in/shikharkwatra/)
- [Will Thieme](https://www.linkedin.com/in/will-thieme-8689758b/)
- [Bradley Strauss](https://www.linkedin.com/in/bradleyjstrauss/)


## 重點整理

- Agent 層級的 evals 只給局部訊號，macro evals 把很多訊號彙整成反覆出現的行為模式。
- 把 trace 壓成文件的方式，決定分群能注意到什麼，這是 eval 設計的一部分。
- BERTopic 風格流程是 embedding、降維、密度分群、再用詞分數標記，並用 prevalence 乘上嚴重度的 impact score 排優先順序。
- 用 lift 比較 pattern 在各切片的集中程度，能判斷一個行為是預期還是可疑。
- AgentTrace 風格的 diagnosis 從 focus event 往回打分，給的是該先檢查哪裡的線索，不是因果證明。

## 練習

1. 把 suspect score 的權重從 `0.4/0.3/0.2/0.1` 改成更重視 frequency（例如 `0.2/0.5/0.2/0.1`），看嫌疑排行榜的前幾名有沒有變。
2. 把 `MACRO_EVALS_TRACE_LIMIT` 設小做 smoke test，比較 impact score 排名第一的 pattern 跟跑完整資料集時是否相同。
3. 改 `doc_structured_summary` 的內容，例如拿掉 handoff 資訊，重新分群，觀察哪些行為模式消失或合併。
