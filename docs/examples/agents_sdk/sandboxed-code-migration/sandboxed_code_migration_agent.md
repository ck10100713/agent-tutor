---
translated: true
source: examples/agents_sdk/sandboxed-code-migration/sandboxed_code_migration_agent.ipynb
---
# Migrate a Legacy Codebase with Sandbox Agents

> 原文：[examples/agents_sdk/sandboxed-code-migration/sandboxed_code_migration_agent.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/sandboxed-code-migration/sandboxed_code_migration_agent.ipynb)

建立一個 sandbox 化的 code-migration agent，把現代化工作拆成互相隔離的任務，並回傳驗證過的 patch bundle。

## 這篇在做什麼

用 Agents SDK 做一個程式碼遷移 agent：agent 的 harness 留在可信任的 host，shell 指令和檔案編輯則在隔離的 sandbox 裡跑。範例把兩個服務的 OpenAI client wrapper，從 Chat Completions 遷移到 Responses API，每個服務各回傳一份 patch。

## 學完你會

- 把 agent harness 放在 host，只讓 sandbox 執行 shell 指令和檔案編輯。
- 把遷移工作拆成一個個 repo shard，用 manifest 控制每個 sandbox 只拿到該任務需要的檔案。
- 對每個任務驗證 test、patch、typed result 和 audit log，並把 sandbox 換成 Docker、E2B 或 Cloudflare 而不改 agent。

## 開跑前

- Python 3.10 以上，並在本機啟動 Docker。
- 設好 `OPENAI_API_KEY` 環境變數，並安裝有 sandbox 支援的 OpenAI Agents SDK。
- 想用託管 sandbox 的話，需要 E2B 的 `E2B_API_KEY`，或 Cloudflare 的 Worker URL 和 API key。


程式碼現代化永遠做不完。過時的依賴、安全風險、合規壓力和舊的寫法，會在大型 codebase 裡不斷累積，而一個巨大的遷移 PR 很難 review，merge 起來也有風險。code-migration agent 應該在受控的環境裡，一次處理一個限定範圍的任務：檢視相關的 repo、編輯檔案、跑檢查，然後回傳 patch。

這份 cookbook 用 Agents SDK，而且 harness 在 sandbox「外面」：orchestration 留在可信任的 host process，shell 指令和檔案編輯則在隔離的執行環境裡跑。這樣的分離讓 host harness 可以使用 secret、tool 和外部服務，同時只給 sandbox 任務所需的檔案和指令。

這份 cookbook 結束時，你可以做到：

- 把 agent harness 放在執行 shell 指令和檔案編輯的執行環境之外
- 把現代化工作切成任務大小的 repo shard
- 用 test、檢查、產出物和 audit log 驗證每個 shard
- 換 sandbox provider 而不用重寫 agent

範例是兩個服務的程式碼遷移。每個服務在自己的 sandbox 跑，並回傳自己的 patch bundle，這個形式也能用來為 review 和 CI 開各自獨立的 pull request。在每個 sandbox 裡，agent 把一個 OpenAI client wrapper 從 [Chat Completions](https://platform.openai.com/docs/api-reference/chat) 遷移到 [Responses API](https://platform.openai.com/docs/api-reference/responses)。過程中它會跑測試、修改 app 和測試、跑編譯檢查、重跑測試，最後回傳一份有型別的遷移報告和 patch。

我們用本機的 Docker 跑 sandbox。provider 專屬的程式碼只集中在建立 sandbox 的地方，所以同一套 harness 和 agent，可以指向 E2B 或 Cloudflare 這類託管 sandbox provider，不用改 `SandboxAgent`、tools、manifest 或 prompt。


## 架構：sandbox 當作 tool

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/agents_sdk/sandboxed-code-migration/assets/sandbox-as-a-tool-architecture.svg" alt="Agents SDK harness running outside a swappable sandbox" width="900"/>

可信任的 host process 擁有 Agents SDK harness、tools、MCP server、憑證、policy 和 audit。執行環境只拿到當前任務限定範圍的 workspace，以及執行指令和編輯檔案所需、面向 sandbox 的能力。

另一種模式是啟動一個 coding agent，它的 harness、agent loop、tools 和檔案系統全都在 sandbox 裡。這也行得通，但會把 orchestration 和 tool 整合，推到執行產生程式碼的同一個環境裡。

在這個模式下，sandbox 是 harness 在 agent 需要檔案系統、terminal 指令、跑測試或產生 patch 時才去呼叫的東西。更大的 agent stack 留在 harness 這一側。

流程：

1. 你的 app 收到遷移請求，把它切成任務大小的 repo shard。
2. 對每個任務，host 端的 Agents SDK harness 啟動一個 agent，並建立一個全新的 sandbox。
3. harness 把該任務的 repo 和遷移 brief 放進 sandbox。
4. agent 用 sandbox tool 檢視檔案、編輯程式碼、跑測試。
5. host 收到該任務的報告和 patch，寫下 audit log、刪除 sandbox，再做下一個任務。


## 需求

- Python 3.10+
- Docker，在本機執行，供 Docker sandbox 範例使用
- 一個 OpenAI API key，以 `OPENAI_API_KEY` 匯出
- 有 sandbox 支援的 OpenAI Agents SDK
- 選用：託管 sandbox provider 的憑證，例如 E2B 的 `E2B_API_KEY`，或 Cloudflare 的 Worker URL 和 API key

API key 要放在 host 的環境裡。不要加進掛載的 repo 或 sandbox manifest。

## 安裝依賴

Clone 這個 cookbook，然後進入這個範例目錄：

```bash
git clone https://github.com/openai/openai-cookbook.git
cd openai-cookbook/examples/agents_sdk/sandboxed-code-migration
```

從該目錄打開 `sandboxed_code_migration_agent.ipynb`，並安裝下面的依賴。跑完整的 agent demo 之前要先啟動 Docker。

```python
%pip install -r requirements.txt --quiet
```

## 匯入 host 端的 harness

匯入這個範例用的小型 host 端 runner。它會建立 sandbox session、啟動 agent loop、寫出回傳的產出物、記錄 audit log，並讓 provider 憑證遠離掛載的 repo。完整檔案在 [`src/run_migration_agent.py`](https://github.com/openai/openai-cookbook/blob/main/examples/agents_sdk/sandboxed-code-migration/src/run_migration_agent.py)，notebook 把重要的部分抽到下面的逐步說明裡。

```python
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agents import ModelSettings
from agents.mcp import MCPServer
from agents.sandbox import Manifest, SandboxAgent
from agents.sandbox.capabilities import ApplyPatch, Shell
from agents.sandbox.entries import LocalDir, LocalFile

EXAMPLE_ROOT = Path.cwd()
sys.path.insert(0, str(EXAMPLE_ROOT))

from src.run_migration_agent import (
    AGENT_INSTRUCTIONS,
    DEFAULT_MIGRATION_TASKS,
    DEVELOPER_INSTRUCTIONS,
    MigrationResult,
    MigrationTask,
    OPENAI_RESPONSES_MIGRATION_DOC_URL,
    run_migration_campaign,
)

migration_tasks = list(DEFAULT_MIGRATION_TASKS)
task = migration_tasks[0]

print("Migration campaign:")
for migration_task in migration_tasks:
    print(f"- {migration_task.name}: {migration_task.repo_path}")
print(f"\nInspecting first task: {task.name}")
```

## 1. 定義遷移任務

這份 cookbook 在 `repo_fixtures/` 裡附了兩個小的 fixture repo。如果你直接照 notebook 跑，host harness 會把每個 fixture repo 掛載到全新的 sandbox 裡，路徑是 `/workspace/repo`，並要求 agent 照著該 repo 的 `MIGRATION.md` 做。

任務清單把每個遷移 shard 指向一個本機 repo：

```python
@dataclass(frozen=True)
class MigrationTask:
    name: str
    repo_path: Path

    @property
    def migration_brief_path(self) -> Path:
        return self.repo_path / "MIGRATION.md"

DEFAULT_MIGRATION_TASKS = (
    MigrationTask(
        name="support_reply_service",
        repo_path=EXAMPLE_ROOT / "repo_fixtures" / "support_reply_service",
    ),
    MigrationTask(
        name="case_summary_service",
        repo_path=EXAMPLE_ROOT / "repo_fixtures" / "case_summary_service",
    ),
)
```

要改成適用你自己的 codebase，把任務的 `repo_path` 換掉，並編輯它的 `MIGRATION.md`。通用的執行 prompt 可以不用改，因為它是叫 agent 照掛載 repo 裡的 brief 做。

在 agent 動手之前，先檢視一個任務：遷移 brief、OpenAI client wrapper，以及應用的呼叫端。

```python
print(task.migration_brief_path.read_text())
```

現在來看兩個主要的程式碼目標：OpenAI client wrapper，以及用到它的應用呼叫端。


```python
print((task.repo_path / "customer_support_bot" / "client.py").read_text())
```

```python
print((task.repo_path / "customer_support_bot" / "replies.py").read_text())
```

## 2. 在 agent 動手前先驗證 baseline

agent 編輯 repo 之前，先自己跑同樣的測試。agent 在改任何檔案之前，也會在該任務的 sandbox 裡跑這個 baseline 測試指令。

```python
baseline = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
    cwd=task.repo_path,
    text=True,
    capture_output=True,
    check=False,
)
print(baseline.stdout)
print(baseline.stderr)
assert baseline.returncode == 0
```

```python
check = subprocess.run(
    [sys.executable, "-m", "compileall", "-q", "customer_support_bot", "tests"],
    cwd=task.repo_path,
    text=True,
    capture_output=True,
    check=False,
)
print(check.stdout)
print(check.stderr)
assert check.returncode == 0
```

## 3. 準備 sandbox workspace

manifest 就是 sandbox 的邊界。它告訴 sandbox client 要放哪些 host 檔案，以及這些檔案在執行環境裡要出現在哪裡。這裡我們把 agent instructions 和一個任務 repo 複製到 `/workspace`。

真實的遷移裡，只放目標 checkout、任務指示，以及這次執行需要的檔案。憑證、客戶儲存空間和 memory 都留在 host harness。下面的 helper 就是因此寫得很小：它只放共用的 agent instructions 和當前遷移任務的 repo。


```python
def build_manifest(task: MigrationTask | None = None) -> Manifest:
    task = task or DEFAULT_MIGRATION_TASKS[0]
    return Manifest(
        root="/workspace",
        entries={
            "migration_agent/AGENTS.md": LocalFile(
                src=EXAMPLE_ROOT / "migration_agent" / "AGENTS.md"
            ),
            "repo": LocalDir(src=task.repo_path),
        },
    )

manifest = build_manifest(task)
print(f"manifest root: {manifest.root}")
for workspace_path in manifest.entries:
    print(workspace_path)
```

## 4. 定義 sandbox agent

這個 agent 有兩個面向 sandbox 的能力：用於 terminal 工作的 `Shell()`，和用於編輯檔案的 `ApplyPatch()`。定義裡其他東西都留在 host harness：instructions、model 設定、MCP server 和有型別的輸出 contract。


```python
def build_agent(
    *,
    model: str,
    manifest: Manifest,
    mcp_servers: list[MCPServer] | None = None,
) -> SandboxAgent:
    return SandboxAgent(
        name="Code Migration Agent",
        model=model,
        instructions=AGENT_INSTRUCTIONS,
        developer_instructions=DEVELOPER_INSTRUCTIONS,
        default_manifest=manifest,
        capabilities=[Shell(), ApplyPatch()],
        mcp_servers=list(mcp_servers or []),
        model_settings=ModelSettings(tool_choice="required"),
        output_type=MigrationResult,
    )

agent = build_agent(model="gpt-5.4", manifest=manifest)
print(agent.name)
print([capability.type for capability in agent.capabilities])
print(agent.output_type)
```

### 選用：連接 host 端的 MCP server

因為 harness 在 sandbox 外面，它可以從可信任的 host process 連接 MCP server。sandbox 不需要 MCP 憑證，也不需要廣泛的網路存取。

這個 runner 可以選擇性地從 host harness 連接公開的 OpenAI docs MCP。agent 可以用那份文件上下文，而 shell 指令和 patch 還是在 sandbox 裡跑。

遷移要盡量保持確定性。抓取核可的遷移指南，而不是讓 agent 每次執行都去搜尋文件。

```python
OPTIONAL_OPENAI_DOCS_MCP_URL = "https://developers.openai.com/mcp"

print("Optional host-side MCP:")
print(f"  server: {OPTIONAL_OPENAI_DOCS_MCP_URL}")
print(f"  pinned doc: {OPENAI_RESPONSES_MIGRATION_DOC_URL}")
print("To opt in for the full run, set this before the agent cell:")
print(f'  os.environ["OPENAI_DOCS_MCP_URL"] = "{OPTIONAL_OPENAI_DOCS_MCP_URL}"')
```

## 5. 執行遷移 campaign

完整的執行是 host 端對遷移任務的一個迴圈。對每個任務，harness 建立 manifest 和 agent，建立全新的 sandbox session，並把這個 session 傳給 `Runner.run_streamed`。任務完成後，host 把回傳的 patch bundle 寫到 `outputs/<task_name>/` 下，並在開始下一個任務之前刪除 sandbox。

```python
manifest = build_manifest(task)
agent = build_agent(model=model, manifest=manifest, mcp_servers=mcp_servers)
client, session = await create_sandbox(backend, manifest, docker_image=docker_image)

try:
    async with session:
        result = Runner.run_streamed(
            agent,
            [{"role": "user", "content": f"Task name: {task.name}\n\n{prompt}"}],
            max_turns=30,
            run_config=RunConfig(
                sandbox=SandboxRunConfig(session=session),
                workflow_name=f"Sandboxed code migration: {task.name} ({backend})",
                tracing_disabled=not enable_hosted_tracing,
            ),
        )
        async for event in result.stream_events():
            if event.type == "run_item_stream_event" and event.name in {"tool_called", "tool_output"}:
                append_audit_event(audit_log_path, {"event": event.name})
finally:
    await client.delete(session)
```

上面的片段是 `run_migration_task` 的核心，下面能執行的 cell 會呼叫完整的 helper。執行有加保護，讓 notebook 可以不呼叫模型就跑完。想端到端執行用 Docker 的遷移時，把 `RUN_FULL_AGENT_DEMO` 改成 `True`。

```python
RUN_FULL_AGENT_DEMO = False
enable_hosted_tracing = False

# Optional: uncomment to let the host harness fetch the pinned Responses migration guide.
# os.environ["OPENAI_DOCS_MCP_URL"] = "https://developers.openai.com/mcp"

if RUN_FULL_AGENT_DEMO:
    campaign = await run_migration_campaign(
        tasks=migration_tasks,
        backend=os.getenv("SANDBOX_BACKEND", "docker"),
        model=os.getenv("OPENAI_MODEL", "gpt-5.4"),
        prompt=(
            "Migrate the mounted repo from Chat Completions to the Responses API. "
            "Follow migration_agent/AGENTS.md and repo/MIGRATION.md. "
            "Run the required baseline tests, patch the app and tests, "
            "run the check command, run the final tests, produce a diff, "
            "and return the structured migration result."
        ),
        docker_image=os.getenv("SANDBOX_DOCKER_IMAGE", "python:3.14-slim"),
        output_root=EXAMPLE_ROOT / "outputs",
        enable_hosted_tracing=enable_hosted_tracing,
    )
    for summary in campaign.task_summaries:
        print(f"{summary.task_name}: {summary.patch_path}")
else:
    print("Skipped. Set RUN_FULL_AGENT_DEMO=True to run the Docker-backed campaign.")
```

## 6. 檢視回傳的產出物

host runner 會把每個任務有型別的結果寫到磁碟。sandbox 在執行後可以消失，每個任務的報告、patch、JSON 結果和 audit log 都保留在 `outputs/<task_name>/`，campaign 摘要在 `outputs/batch_summary.json`。

```python
artifact_names = [
    "migration_report.md",
    "migration.patch",
    "migration_result.json",
    "migration_audit.jsonl",
]

for migration_task in migration_tasks:
    print(f"\n=== {migration_task.name} ===")
    task_output_dir = EXAMPLE_ROOT / "outputs" / migration_task.name
    for artifact_name in artifact_names:
        path = task_output_dir / artifact_name
        if path.exists():
            print(f"\n--- {path.name} ---")
            print(path.read_text()[:3000])
        else:
            print(f"not generated yet: {path}")
```

### 選用：驗證產生的產出物

host 可以在把 patch 給使用者看、或套用到真實 repo 之前，先檢查每個回傳的 patch、有型別的結果和 audit log。這個 eval 是確定性的：它讀取 campaign 的輸出，只要有任務沒有產生預期的 contract 就會失敗。


```python
if (EXAMPLE_ROOT / "outputs" / "batch_summary.json").exists():
    subprocess.run([sys.executable, "evals.py"], cwd=EXAMPLE_ROOT, check=True)
else:
    print("Skipped. Run the full agent demo before running artifact evals.")
```

## 7. 選用：更換 sandbox provider

這一節展示三種 sandbox 後端：本機執行用 Docker、託管 sandbox 用 E2B、託管的 worker 型 sandbox 用 Cloudflare。模式都一樣：換的是 sandbox client，不是 agent。

Docker：

```python
client = DockerSandboxClient(docker.from_env())
session = await client.create(
    manifest=manifest,
    options=DockerSandboxClientOptions(image="python:3.14-slim"),
)
```

E2B：

```python
client = E2BSandboxClient()
session = await client.create(
    manifest=manifest,
    options=E2BSandboxClientOptions(
        sandbox_type=E2BSandboxType.E2B,
    ),
)
```

從 CLI 執行 E2B：

```bash
export E2B_API_KEY="..."
python src/run_migration_agent.py --backend e2b
```

Cloudflare：

```python
client = CloudflareSandboxClient()
session = await client.create(
    manifest=manifest,
    options=CloudflareSandboxClientOptions(
        worker_url=os.environ["CLOUDFLARE_SANDBOX_WORKER_URL"],
        api_key=os.environ.get("CLOUDFLARE_SANDBOX_API_KEY"),
    ),
)
```

從 CLI 執行 Cloudflare：

```bash
export CLOUDFLARE_SANDBOX_WORKER_URL="https://..."
export CLOUDFLARE_SANDBOX_API_KEY="..."
python src/run_migration_agent.py --backend cloudflare
```

從 CLI 執行 Docker：

```bash
python src/run_migration_agent.py --backend docker
```

## Production 注意事項

Production 程式碼應該把 orchestration、執行、資料存取和回傳的輸出，放在各自獨立的信任邊界後面。把每個遷移任務當作獨立的 review 單位。

| Boundary | Production pattern |
| --- | --- |
| Harness | Keep orchestration, tools, credentials, policy, and audit on the host. |
| Sandbox | Stage only the task workspace. Run commands and edits there. Tear it down after the task. |
| Data access | Route customer storage and network access through the host, not directly through the sandbox. |
| Output | Validate sandbox output in the host before showing it to users or applying changes. |


## Tracing 和 ZDR

這個範例每次執行都用 `RunConfig.tracing_disabled=True` 關閉託管的 tracing。要在跑這份 cookbook 的 CLI 時開啟，傳入 `--enable-hosted-tracing`。如果想讓整個 process 都關閉 tracing，Agents SDK 也支援全域的 `OPENAI_AGENTS_DISABLE_TRACING=1` 環境變數。

## 接下來

要把這個模式改成適用你的情況，把 `migration_tasks` 換成你自己的 repo、package 或服務。每個任務給一個 checkout 和一份 `MIGRATION.md`。驗證指令要寫明確，並且回傳 patch 給人 review，而不是自動套用 host 端的變更。再加上確定性的 eval 來檢查遷移 contract，而不只是看測試套件有沒有過。

當工作橫跨很多 package，例如 Jest 到 Vitest 的遷移，host harness 可以用 repo metadata 或一個 manager agent 來規劃 shard。每個 shard 都應該產出跟這份 cookbook 一樣的東西：來自隔離 sandbox 的驗證過的 patch、報告和 audit trail。

## 重點整理

- harness 放 host、sandbox 只當 tool 用，這樣憑證、MCP 和 policy 都不會進到執行生成程式碼的環境。
- 把大型遷移切成一個任務一個 repo shard，每個 shard 各自產出 patch，比一個巨大的 PR 好 review。
- manifest 是 sandbox 的邊界，只放該任務需要的檔案。
- host 要驗證 sandbox 回傳的東西（patch、typed result、audit log），不要直接套用。
- provider 專屬的程式碼只在建立 sandbox 的地方，換 Docker、E2B、Cloudflare 不用動 agent。

## 練習

1. 把 `RUN_FULL_AGENT_DEMO` 改成 `True`，用 Docker 完整跑一次，然後到 `outputs/<task_name>/` 看 patch、報告和 audit log。
2. 在 `migration_tasks` 加第三個任務，指向你自己準備的小 repo 和它的 `MIGRATION.md`，確認 agent 照它的 brief 做。
3. 照「驗證產生的產出物」那段，加一條自己的確定性檢查，例如 patch 裡不能還有 Chat Completions 的呼叫，並在沒過時讓流程失敗。
