---
translated: true
source: claude_agent_sdk/02_The_observability_agent.ipynb
---

# The observability agent

> 原文：[claude_agent_sdk/02_The_observability_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/02_The_observability_agent.ipynb)

透過 MCP server 把 agent 接到外部系統，做 GitHub 監控跟 CI 工作流程。

## 這篇在做什麼

用 Claude Agent SDK 把 Git MCP server 跟 GitHub MCP server 接到 agent 上，讓 agent 能查 commit 歷史、看 GitHub Actions 的 CI 狀況。最後把這個流程包成一個可重用的 observability agent module。

## 學完你會

- 用 MCP server 設定讓 agent 取得 Git 跟 GitHub 的 tool。
- 讓 agent 監控 GitHub Actions workflow，分辨真正的失敗跟權限限制。
- 用 `send_query` 包好的 module 做多輪對話（`continue_conversation=True`）。

## 開跑前

- 需要 GitHub Personal Access Token（Fine-grained，預設選項即可），放進 `.env` 的 `GITHUB_TOKEN`。
- 需要 Docker 在本機執行，GitHub MCP server 跑在容器裡。

```python
import os
import shutil
import subprocess
from typing import Any

from dotenv import load_dotenv
from IPython.display import Markdown, display
from utils.agent_visualizer import (
    display_agent_response,
    print_activity,
    reset_activity_context,
    visualize_conversation,
)

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
```

前面的 notebook 我們做了基本的 research agent 跟 Chief of Staff 多 agent 框架。這些 agent 已經很強，但能做的事還是有限：web search agent 只能搜尋網路，Chief of Staff agent 只能操作自己的檔案系統。

這是個很大的限制，因為真實世界的 agent 常常要跟資料庫、API、檔案系統和其他專門服務互動。[MCP (Model Context Protocol)](https://modelcontextprotocol.io/docs/getting-started/intro) 是開源的 AI 與 tool 整合標準，能讓 agent 輕鬆連到這些外部系統。這篇 notebook 會說明怎麼把 MCP server 接到 agent 上。

**想知道更多 MCP 細節？** 完整的設定說明、設定最佳實務和疑難排解，請看 [Claude Code MCP documentation](https://docs.claude.com/en/docs/claude-code/mcp)。

## MCP Server 簡介
### 1. Git MCP server

先讓 agent 能理解並操作 Git repository。把 [Git MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/git) 加進 agent 後，它會多出 13 個 Git 專用 tool，可以查 commit 歷史、檢查檔案變更、建立 branch，甚至 commit。這會把 agent 從被動的觀察者變成開發流程的積極參與者。這個範例我們設定 agent 只用 Git tool 來探索 repository 的歷史。內容很簡單，但可以想像，agent 能自動建立 pull request、分析程式碼演進模式，或是幫忙管理跨多個 repository 的複雜 Git 流程。

```python
# Get the git repository root (mcp_server_git requires a valid git repo path)
# os.getcwd() may return a subdirectory, so we find the actual repo root
git_executable = shutil.which("git")
if git_executable is None:
    raise RuntimeError("Git executable not found in PATH")

git_repo_root = subprocess.run(  # noqa: S603
    [git_executable, "rev-parse", "--show-toplevel"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()

# Define our git MCP server (installed via uv sync from pyproject.toml)
git_mcp: dict[str, Any] = {
    "git": {
        "command": "uv",
        "args": ["run", "python", "-m", "mcp_server_git", "--repository", git_repo_root],
    }
}
```

```python
messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-5-5",
        mcp_servers=git_mcp,
        allowed_tools=["mcp__git"],
        # disallowed_tools ensures the agent ONLY uses MCP tools, not Bash with git commands.
        # "Agent" is the subagent tool (named "Task" before claude-agent-sdk 0.2).
        disallowed_tools=["Bash", "Agent", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
        setting_sources=[],  # only the MCP servers configured here; no user/project settings
    )
) as agent:
    await agent.query(
        "Explore this repo's git history and provide a brief summary of recent activity."
    )
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)
```

??? note "輸出"

    ```text
    🤖 Using: mcp__git__git_log()
    🤖 Using: mcp__git__git_status()
    🤖 Using: mcp__git__git_branch()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: mcp__git__git_log()
    🤖 Using: mcp__git__git_status()
    🤖 Using: mcp__git__git_branch()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    ```

```python
display(Markdown(f"\nResult:\n{messages[-1].result}"))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

### 2. GitHub MCP server

接著從本機 Git 操作升級到完整的 GitHub 平台整合。換成[官方 GitHub MCP server](https://github.com/github/github-mcp-server/tree/main)，agent 能用 100 多個 tool 操作整個 GitHub 生態，從管理 issue 跟 pull request，到監控 CI/CD workflow、分析程式碼安全警示。這個 server 公開跟私有 repository 都能處理，讓 agent 能自動化原本需要很多手動步驟的 GitHub 流程。

#### Step 1: 設定 GitHub Token

你需要一個 GitHub Personal Access Token。到[這裡](https://github.com/settings/personal-access-tokens/new)申請，然後放進 .env 檔：```GITHUB_TOKEN="<token>"```
> 注意：申請時選 "Fine-grained" token 並用預設選項（公開 repo、不需帳號權限），這是讓這個 demo 跑起來最簡單的方式。

另外這個範例需要在你的機器上跑 [Docker](https://www.docker.com/products/docker-desktop/)。因為 GitHub MCP server 為了安全跟隔離，是在容器環境中執行。

**Docker 快速設定：**
- 從 [docker.com](https://www.docker.com/products/docker-desktop/) 安裝 Docker Desktop
- 確認 Docker 有在跑（系統匣會看到 Docker 圖示）
- 在終端機用 `docker --version` 驗證
- **疑難排解：** 如果 Docker 啟動不了，檢查 BIOS 有沒有開啟虛擬化。詳細設定請看 [Docker documentation](https://docs.docker.com/get-docker/)
- 如果在 Colab 跑：Colab 沒有 Docker，這段建議在本機執行。

#### Step 2: 定義 MCP server 並啟動 agent loop！

```python
# define our github mcp server
load_dotenv(override=True)
github_mcp: dict[str, Any] = {
    "github": {
        "command": "docker",
        "args": [
            "run",
            "-i",
            "--rm",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "ghcr.io/github/github-mcp-server",
        ],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_TOKEN")},
    }
}
```

```python
# run our agent
messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-5-5",
        mcp_servers=github_mcp,
        allowed_tools=["mcp__github"],
        # disallowed_tools ensures the agent ONLY uses MCP tools, not Bash with gh CLI
        disallowed_tools=["Bash", "Agent", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
        setting_sources=[],
    )
) as agent:
    await agent.query(
        "Search for the anthropics/claude-agent-sdk-python repository and give me a few key facts about it."
    )
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)
```

??? note "輸出"

    ```text
    🤖 Using: mcp__github__search_repositories()
    ✓ Tool completed
    🤖 Thinking...
    ```

```python
display(Markdown(f"\nResult:\n{messages[-1].result}"))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 實際案例：Observability agent

只要這麼簡單的設定，我們就已經有一個像是自我修復軟體系統的 agent 了！

```python
load_dotenv(override=True)

prompt = """Analyze the CI health for facebook/react repository.

Examine the most recent runs of the 'CI' workflow and provide:
1. Current status and what triggered the run (push, PR, schedule, etc.)
2. If failing: identify the specific failing jobs/tests and assess severity
3. If passing: note any concerning patterns (long duration, flaky history)
4. Recommended actions with priority (critical/high/medium/low)

Provide a concise operational summary suitable for an on-call engineer.
Do not create issues or PRs - this is a read-only analysis."""

github_mcp: dict[str, Any] = {
    "github": {
        "command": "docker",
        "args": [
            "run",
            "-i",
            "--rm",
            "-e",
            "GITHUB_PERSONAL_ACCESS_TOKEN",
            "ghcr.io/github/github-mcp-server",
        ],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": os.environ.get("GITHUB_TOKEN")},
    }
}

messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model="claude-opus-5-5",
        mcp_servers=github_mcp,
        allowed_tools=["mcp__github"],
        # IMPORTANT: disallowed_tools is required to actually RESTRICT tool usage.
        # Without this, allowed_tools only controls permission prompting, not availability.
        # The agent would still have access to Bash (and could use `gh` CLI instead of MCP).
        disallowed_tools=["Bash", "Agent", "WebSearch", "WebFetch"],
        permission_mode="acceptEdits",
        setting_sources=[],
    )
) as agent:
    await agent.query(prompt)
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)
```

??? note "輸出"

    ```text
    🤖 Using: mcp__github__get_file_contents()
    🤖 Using: mcp__github__list_commits()
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: mcp__github__get_file_contents()
    🤖 Using: mcp__github__get_file_contents()
    🤖 Using: mcp__github__list_pull_requests()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: mcp__github__get_commit()
    🤖 Using: mcp__github__get_commit()
    🤖 Using: mcp__github__get_commit()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: mcp__github__search_issues()
    🤖 Using: mcp__github__search_issues()
    ✓ Tool completed
    ✓ Tool completed
    ... (省略 1 行)
    ```

```python
display(Markdown(f"\nResult:\n{messages[-1].result}"))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

```python
reset_activity_context()
visualize_conversation(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
reset_activity_context()
display_agent_response(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

### Observability Agent 做成 Module

`observability_agent/agent.py` 這個 module 把 observability 的模式包成可重用的 `send_query` function。它內部會 import 並使用 `utils.agent_visualizer` 的共用視覺化工具：
- **`reset_activity_context()`**：每次 query 開始時自動呼叫
- **`print_activity()`**：執行過程中即時回饋
- **`display_agent_response()`**：顯示最終結果（由 `display_result` 參數控制）

所以你用很少的程式碼就能使用這個 module：

```python
# Reload the module to pick up any changes (useful during development)
from observability_agent.agent import send_query

# The module handles activity display, context reset, and result visualization internally
result = await send_query(
    "Check the CI status for the last 2 runs in anthropics/claude-agent-sdk-python. Just do 3 tool calls, be efficient."
)
```

??? note "輸出"

    ```text
    🤖 Using: mcp__github__list_commits()
    ✓ Tool completed
    🤖 Using: mcp__github__get_commit()
    🤖 Using: mcp__github__get_commit()
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

多輪對話也很順，只要傳 `continue_conversation=True`：

```python
# Example 2: Multi-turn conversation for deeper monitoring
result1 = await send_query("What's the current CI status for facebook/react?")
```

??? note "輸出"

    ```text
    🤖 Using: mcp__github__list_pull_requests()
    🤖 Using: mcp__github__list_commits()
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__pull_request_read()
    🤖 Using: mcp__github__get_commit()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# Continue the conversation to dig deeper
result2 = await send_query(
    "Are there any flaky tests in the recent failures? You can only make one tool call.",
    continue_conversation=True,
)
```

??? note "輸出"

    ```text
    🤖 Using: mcp__github__search_issues()
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

## 結論

我們示範了 Claude Code SDK 怎麼透過 Model Context Protocol (MCP) 無縫整合外部系統。從 Git MCP server 的本機 Git 操作開始，逐步擴展到完整的 GitHub 平台整合，可使用 100 多個 GitHub 專用 tool。這讓 agent 從本機助理變成強大的 observability 系統，能監控 workflow、分析 CI/CD 失敗，並提供可行動的 production 系統洞察。

把 MCP server 接到 agent 後，我們做出了一個自主的 observability 系統，它監控 GitHub Actions workflow，分辨真正的失敗與安全限制，並詳細分析測試失敗。這個系統展示了 agent 如何主動參與 DevOps 流程，從被動監控走向智慧化的事件回應。

到這裡，Claude Code SDK 教學系列暫時告一段落。我們從簡單的 research agent，走到複雜的多 agent 協作，最後到透過 MCP 整合外部系統。這些模式合起來，是打造能處理真實世界複雜度的 production 級 agent 系統的基礎，同時兼顧治理、合規和 observability。

### 三本 Notebook 學到的東西

**Notebook 00（Research Agent）**
- SDK 基本功：`query()` 跟 `ClaudeSDKClient`
- 用 WebSearch 和 Read 做基本 tool 使用
- 簡單的 agent loop 與對話管理

**Notebook 01（Chief of Staff）**
- 進階功能：memory、output style、planning mode
- 透過 subagent 做多 agent 協作
- 用 hook 跟自訂 command 做治理
- 企業級 agent 架構

**Notebook 02（Observability Agent）**
- 透過 MCP server 整合外部系統
- 即時監控與事件回應
- production 工作流程自動化
- 可擴展的 agent 部署模式

三個 agent 的完整實作都在各自的目錄（`research_agent/`、`chief_of_staff_agent/`、`observability_agent/`），可以當作整合進你 production 系統的參考。

## 重點整理

- MCP 是開源標準，讓 agent 用統一方式連到 Git、GitHub 這類外部系統。
- Git MCP server 提供本機 repo 操作，GitHub MCP server 提供平台層級（issue、PR、CI/CD、安全警示）的 100 多個 tool。
- 只要 agent 能讀 CI 狀態，就能分辨真正的測試失敗跟權限造成的失敗。
- 把常用流程包成 module（像 `send_query`），後續查詢和多輪對話的程式碼就很短。

## 練習

1. 把 Git MCP server 那段的 prompt 改成問「最近 5 個 commit 改了哪些檔案」，看 agent 用了哪些 tool。
2. 在 GitHub MCP server 的設定中換成你自己的公開 repo，讓 agent 回報最近一次 workflow run 的狀態。
3. 用 `send_query` 搭配 `continue_conversation=True`，先問失敗原因，再追問「怎麼修」。
