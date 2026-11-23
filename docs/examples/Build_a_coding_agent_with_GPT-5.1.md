---
translated: true
source: examples/Build_a_coding_agent_with_GPT-5.1.ipynb
---

# 用 GPT 5.1 打造 Coding Agent

> 原文：[examples/Build_a_coding_agent_with_GPT-5.1.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Build_a_coding_agent_with_GPT-5.1.ipynb)



## 這篇在做什麼
用 Agents SDK 搭配 GPT-5.1，做一個能從一句 prompt 蓋出全新 app、再根據回饋持續修改的 coding agent。agent 配備 `shell`、`web_search`、`apply_patch` 和 Context7 MCP 四種 tool。

## 學完你會
- 用 Agents SDK 定義 agent，並自己實作 `ShellExecutor` 來執行模型提出的 shell 指令。
- 加上 `apply_patch` tool 讓 agent 原地修改檔案，並接上 Context7 MCP server 取得最新文件。
- 讓 agent 從零建出一個 NextJS dashboard，再改成呼叫 OpenAI Responses API 做摘要。

## 開跑前
- 需要 OpenAI API key，並能使用 `gpt-5.1`。
- 本機要有 Node 環境，因為 agent 會用 shell 建立 NextJS 專案。
- Context7 MCP 是外部服務，需要能連到 context7.com。

GPT-5.1 的 coding 能力特別強，加上 [Responses API](https://platform.openai.com/docs/api-reference/responses) 新增的程式碼編輯和指令執行 tool，現在要做出能處理整個 codebase、快速迭代的 coding agent 比以前容易得多。

這份指南會用 [Agents SDK](https://openai.github.io/openai-agents-python/) 做一個 **能根據 prompt 蓋出全新 app，並依使用者回饋持續改進的 coding agent**。我們的 agent 會有這些 tool：

- **apply_patch**：編輯檔案
- **shell**：執行 shell 指令
- **web_search**：從網路取得最新資訊
- **Context7 MCP**：取得最新文件

一開始先專注在 `shell` 和 `web_search`，用網路上取得的脈絡產生新專案。接著加入 `apply_patch`，讓 agent 能迭代修改 codebase，再接上 [Context7 MCP server](https://context7.com/)，讓它能依最新的文件寫程式。

## 設定 agent

有了 Agents SDK，定義 agent 只需要提供 instructions 和 tool 清單。這個例子我們要用最新的 `gpt-5.1` 模型，因為它的 coding 能力是目前最先進的。

我們先啟用 `web_search`，讓 agent 能上網查最新資訊，以及 `shell`，讓 agent 能提出 shell 指令，處理建立專案骨架、安裝相依套件、執行 build 之類的工作。

shell tool 的運作方式是：模型提出它認為該執行的指令，實際執行並回傳輸出的是你的環境。

Agents SDK 幫你自動處理大部分的指令執行流程，你只需要實作 shell executor，也就是那些指令實際執行的環境。

```python
%pip install openai-agents openai asyncio
```

```python
import os 

# Make sure your OpenAI API key is defined (you can set it on your global environment, or export it manually)
# export OPENAI_API_KEY="sk-..."
assert "OPENAI_API_KEY" in os.environ, "Please set OPENAI_API_KEY first."
```

### 定義工作環境和 shell executor

為了簡單，我們在本機執行 shell 指令，並把它們隔離在專屬的 workspace 目錄裡，確保 agent 只會碰到那個資料夾裡的檔案。

**注意：** 正式環境一定要在 sandbox 裡執行 shell 指令。任意執行指令本來就有風險，必須嚴格控管。

```python
# Create an isolated workspace for shell commands
from pathlib import Path

workspace_dir = Path("coding-agent-workspace").resolve()
workspace_dir.mkdir(exist_ok=True)

print(f"Workspace directory: {workspace_dir}")
```

??? note "輸出"

    ```text
    Workspace directory: /Users/katia/dev/openai-cookbook/examples/coding-agent-workspace
    ```

接著定義一個小的 `ShellExecutor` class，它會：

- 接收 agent 送來的 `ShellCommandRequest`
- 視需要在執行指令前詢問核准
- 用 `asyncio.create_subprocess_shell` 執行
- 回傳包含輸出的 `ShellResult`

所有指令都在 `cwd=workspace_dir` 下執行，所以只會影響那個子資料夾裡的檔案。

```python
import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from agents import (
    ShellTool,
    ShellCommandRequest,
    ShellCommandOutput,
    ShellCallOutcome,
    ShellResult,
)


async def require_approval(commands: Sequence[str]) -> None:
    """
    Ask for confirmation before running shell commands.

    Set SHELL_AUTO_APPROVE=1 in your environment to skip this prompt
    (useful when you're iterating a lot or running in CI).
    """
    if os.environ.get("SHELL_AUTO_APPROVE") == "1":
        return

    print("Shell command approval required:")
    for entry in commands:
        print(" ", entry)
    response = input("Proceed? [y/N] ").strip().lower()
    if response not in {"y", "yes"}:
        raise RuntimeError("Shell command execution rejected by user.")


class ShellExecutor:
    """
    Shell executor for the notebook cookbook.

    - Runs all commands inside `workspace_dir`
    - Captures stdout/stderr
    - Enforces an optional timeout from `action.timeout_ms`
    - Returns a ShellResult with ShellCommandOutput entries using ShellCallOutcome
    """

    def __init__(self, cwd: Path):
        self.cwd = cwd

    async def __call__(self, request: ShellCommandRequest) -> ShellResult:
        action = request.data.action
        await require_approval(action.commands)

        outputs: list[ShellCommandOutput] = []

        for command in action.commands:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=self.cwd,
                env=os.environ.copy(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            timed_out = False
            try:
                timeout = (action.timeout_ms or 0) / 1000 or None
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                stdout_bytes, stderr_bytes = await proc.communicate()
                timed_out = True

            stdout = stdout_bytes.decode("utf-8", errors="ignore")
            stderr = stderr_bytes.decode("utf-8", errors="ignore")

            # Use ShellCallOutcome instead of exit_code/status fields directly
            outcome = ShellCallOutcome(
                type="timeout" if timed_out else "exit",
                exit_code=getattr(proc, "returncode", None),
            )

            outputs.append(
                ShellCommandOutput(
                    command=command,
                    stdout=stdout,
                    stderr=stderr,
                    outcome=outcome,
                )
            )

            if timed_out:
                # Stop running further commands if this one timed out
                break

        return ShellResult(
            output=outputs,
            provider_data={"working_directory": str(self.cwd)},
        )


shell_tool = ShellTool(executor=ShellExecutor(cwd=workspace_dir))
```

### 定義 agent

```python
# Define the agent's instructions
INSTRUCTIONS = '''
You are a coding assistant. The user will explain what they want to build, and your goal is to run commands to generate a new app.
You can search the web to find which command you should use based on the technical stack, and use commands to create code files. 
You should also install necessary dependencies for the project to work. 
'''
```

```python
from agents import Agent, Runner, ShellTool, WebSearchTool

coding_agent = Agent(
    name="Coding Agent",
    model="gpt-5.1",
    instructions=INSTRUCTIONS,
    tools=[
        WebSearchTool(),
        shell_tool
    ]
)
```

## 開始一個新專案

我們送一個 prompt 給 coding agent，再檢查它在 `workspace_dir` 裡建出的檔案。
這個例子會用 [shadcn](https://ui.shadcn.com/) 函式庫建一個 NextJS dashboard。

**注意：** 有時候會遇到 `MaxTurnsExceeded` 錯誤，或是專案有相依套件的錯誤。重跑一次 agent loop 就好。正式環境裡，你會實作外部迴圈或使用者輸入處理，在建立專案失敗時重試。

```python
prompt = "Create a new NextJS app that shows dashboard-01 from https://ui.shadcn.com/blocks on the home page"
```

```python
import asyncio
from agents import ItemHelpers, RunConfig

async def run_coding_agent_with_logs(prompt: str):
    """
    Run the coding agent and stream logs about what's happening
    """
    print("=== Run starting ===")
    print(f"[user] {prompt}\n")

    result = Runner.run_streamed(
        coding_agent,
        input=prompt
    )

    async for event in result.stream_events():
        
        # High-level items: messages, tool calls, tool outputs, MCP, etc.
        if event.type == "run_item_stream_event":
            item = event.item

            # 1) Tool calls (function tools, web_search, shell, MCP, etc.)
            if item.type == "tool_call_item":
                raw = item.raw_item
                raw_type_name = type(raw).__name__

                # Special-case the ones we care most about in this cookbook
                if raw_type_name == "ResponseFunctionWebSearch":
                    print("[tool] web_search_call – agent is calling web search")
                elif raw_type_name == "LocalShellCall":
                    # LocalShellCall.action.commands is where the commands live
                    commands = getattr(getattr(raw, "action", None), "commands", None)
                    if commands:
                        print(f"[tool] shell – running commands: {commands}")
                    else:
                        print("[tool] shell – running command")
                else:
                    # Generic fallback for other tools (MCP, function tools, etc.)
                    print(f"[tool] {raw_type_name} called")

            # 2) Tool call outputs
            elif item.type == "tool_call_output_item":
                # item.output is whatever your tool returned (could be structured)
                output_preview = str(item.output)
                if len(output_preview) > 400:
                    output_preview = output_preview[:400] + "…"
                print(f"[tool output] {output_preview}")

            # 3) Normal assistant messages
            elif item.type == "message_output_item":
                text = ItemHelpers.text_message_output(item)
                print(f"[assistant]\n{text}\n")

            # 4) Other event types (reasoning, MCP list tools, etc.) – ignore
            else:
                pass

    print("=== Run complete ===\n")

    # Once streaming is done, result.final_output contains the final answer
    print("Final answer:\n")
    print(result.final_output)
```

```python
await run_coding_agent_with_logs(prompt)
```

??? note "輸出"

    ```text
    === Run starting ===
    [user] Create a new NextJS app that shows dashboard-01 from https://ui.shadcn.com/blocks on the home page

    Shell command approval required:
      npx create-next-app@latest shadcn-dashboard --typescript --eslint --tailwind --app --src-dir --import-alias "@/*"
      cd shadcn-dashboard && npm install shadcn-ui class-variance-authority clsx tailwind-merge lucide-react
      cd shadcn-dashboard && npx shadcn-ui@latest init -y
    Proceed? [y/N] y
    [tool] ResponseOutputMessage called
    [tool output] $ npx create-next-app@latest shadcn-dashboard --typescript --eslint --tailwind --app --src-dir --import-alias "@/*"
    [?25l[2K[1G? Would you like to use React Compiler? › No / Yes

    $ cd shadcn-dashboard && npm install shadcn-ui class-variance-authority clsx tailwind-merge lucide-react
    stderr:
    /bin/sh: line 0: cd: shadcn-dashboard…
    Shell command approval required:
      yes "No" | npx create-next-app@latest shadcn-dashboard --typescript --eslint --tailwind --app --src-dir --import-alias "@/*"
      cd shadcn-dashboard && npm install shadcn-ui class-variance-authority clsx tailwind-merge lucide-react
      cd shadcn-dashboard && npx shadcn@latest init -y
    Proceed? [y/N] y
    [tool] ResponseOutputMessage called
    [tool output] $ yes "No" | npx create-next-app@latest shadcn-dashboard --typescript --eslint --tailwind --app --src-dir --import-alias "@/*"
    [?25l[2K[1G? Would you like to use React Compiler? › No / Yes[2K[1G[2K[1G✔ Would you like to use React Compiler? … No / Yes
    [?2…
    Shell command approval required:
      cd shadcn-dashboard && yes "" | npx shadcn@latest init
      cd shadcn-dashboard && npx shadcn@latest add button card dropdown-menu input label progress select separator sheet sidebar skeleton tabs avatar
    Proceed? [y/N] y
    [tool] ResponseOutputMessage called
    [tool output] $ cd shadcn-dashboard && yes "" | npx shadcn@latest init
    [?25l? Which color would you like to use as the base color? › - Use arrow-keys. Return to submit.
    ❯   Neutral
        Gray
        Zinc
        Stone
        Slate
    [2K[1G✔ Which color would you like to use as the …
    Shell command approval required:
      cd shadcn-dashboard && ls
      cd shadcn-dashboard && sed -n '1,200p' src/app/page.tsx
    ... (省略 313 行)
    ```

Agent 建完初始專案後（你會看到 "=== Run complete ===" 的 log，接著是最終答案），可以用下面的指令檢查輸出：

```bash
cd coding-agent-workspace/<name_of_the_project>
npm run dev
```

你應該會看到類似這樣的畫面： 
![dashboard screenshot](https://cdn.openai.com/cookbook/dashboard_screenshot1.jpg)


## 迭代專案 

現在有了 app 的初版，可以用 apply_patch tool 開始迭代。我們也想加入對 OpenAI Responses API 的呼叫，這需要模型能取得最新的文件。為此，我們把 agent 接到 [Context7 MCP server](https://context7.com/)，它提供最新的文件。

### 設定 `apply_patch` tool 做原地編輯

注意：正式環境通常會想在 sandbox 的專案 workspace（例如暫時性的 container）裡執行這些編輯，並搭配 IDE 使用。

```python
import hashlib
import os
from pathlib import Path

from agents import ApplyPatchTool
from agents.editor import ApplyPatchOperation, ApplyPatchResult


class ApprovalTracker:
    """Tracks which apply_patch operations have already been approved."""

    def __init__(self) -> None:
        self._approved: set[str] = set()

    def fingerprint(self, operation: ApplyPatchOperation, relative_path: str) -> str:
        hasher = hashlib.sha256()
        hasher.update(operation.type.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(relative_path.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update((operation.diff or "").encode("utf-8"))
        return hasher.hexdigest()

    def remember(self, fingerprint: str) -> None:
        self._approved.add(fingerprint)

    def is_approved(self, fingerprint: str) -> bool:
        return fingerprint in self._approved


class WorkspaceEditor:
    """
    Minimal editor for the apply_patch tool:
    - keeps all edits under `root`
    - optional manual approval (APPLY_PATCH_AUTO_APPROVE=1 to skip prompts)
    """

    def __init__(self, root: Path, approvals: ApprovalTracker, auto_approve: bool = False) -> None:
        self._root = root.resolve()
        self._approvals = approvals
        self._auto_approve = auto_approve or os.environ.get("APPLY_PATCH_AUTO_APPROVE") == "1"

    def create_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        relative = self._relative_path(operation.path)
        self._require_approval(operation, relative)
        target = self._resolve(operation.path, ensure_parent=True)
        diff = operation.diff or ""
        content = apply_unified_diff("", diff, create=True)
        target.write_text(content, encoding="utf-8")
        return ApplyPatchResult(output=f"Created {relative}")

    def update_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        relative = self._relative_path(operation.path)
        self._require_approval(operation, relative)
        target = self._resolve(operation.path)
        original = target.read_text(encoding="utf-8")
        diff = operation.diff or ""
        patched = apply_unified_diff(original, diff)
        target.write_text(patched, encoding="utf-8")
        return ApplyPatchResult(output=f"Updated {relative}")

    def delete_file(self, operation: ApplyPatchOperation) -> ApplyPatchResult:
        relative = self._relative_path(operation.path)
        self._require_approval(operation, relative)
        target = self._resolve(operation.path)
        target.unlink(missing_ok=True)
        return ApplyPatchResult(output=f"Deleted {relative}")

    def _relative_path(self, value: str) -> str:
        resolved = self._resolve(value)
        return resolved.relative_to(self._root).as_posix()

    def _resolve(self, relative: str, ensure_parent: bool = False) -> Path:
        candidate = Path(relative)
        target = candidate if candidate.is_absolute() else (self._root / candidate)
        target = target.resolve()
        try:
            target.relative_to(self._root)
        except ValueError:
            raise RuntimeError(f"Operation outside workspace: {relative}") from None
        if ensure_parent:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def _require_approval(self, operation: ApplyPatchOperation, display_path: str) -> None:
        fingerprint = self._approvals.fingerprint(operation, display_path)
        if self._auto_approve or self._approvals.is_approved(fingerprint):
            self._approvals.remember(fingerprint)
            return

        print("\n[apply_patch] approval required")
        print(f"- type: {operation.type}")
        print(f"- path: {display_path}")
        if operation.diff:
            preview = operation.diff if len(operation.diff) < 400 else f"{operation.diff[:400]}…"
            print("- diff preview:\n", preview)
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in {"y", "yes"}:
            raise RuntimeError("Apply patch operation rejected by user.")
        self._approvals.remember(fingerprint)


def apply_unified_diff(original: str, diff: str, create: bool = False) -> str:
    """
    Simple "diff" applier (adapt this based on your environment)

    - For create_file, the diff can be the full desired file contents,
      optionally with leading '+' on each line.
    - For update_file, we treat the diff as the new file contents:
      keep lines starting with ' ' or '+', drop '-' lines and diff headers.

    This avoids context/delete mismatch errors while still letting the model
    send familiar diff-like patches.
    """
    if not diff:
        return original

    lines = diff.splitlines()
    body: list[str] = []

    for line in lines:
        if not line:
            body.append("")
            continue

        # Skip typical unified diff headers / metadata
        if line.startswith("@@") or line.startswith("---") or line.startswith("+++"):
            continue

        prefix = line[0]
        content = line[1:]

        if prefix in ("+", " "):
            body.append(content)
        elif prefix in ("-", "\\"):
            # skip deletions and "\ No newline at end of file"
            continue
        else:
            # If it doesn't look like diff syntax, keep the full line
            body.append(line)

    text = "\n".join(body)
    if diff.endswith("\n"):
        text += "\n"
    return text


approvals = ApprovalTracker()
editor = WorkspaceEditor(root=workspace_dir, approvals=approvals, auto_approve=True)
apply_patch_tool = ApplyPatchTool(editor=editor)
```

### 連接 Context7 MCP server

```python
# Optional: set CONTEXT7_API_KEY in your environment for higher rate limits
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY")
```

```python
from agents import HostedMCPTool

context7_tool = HostedMCPTool(
    tool_config={
        "type": "mcp",
        "server_label": "context7",
        "server_url": "https://mcp.context7.com/mcp",
        # Basic usage works without auth; for higher rate limits, pass your key here.
        **(
            {"authorization": f"Bearer {CONTEXT7_API_KEY}"}
            if CONTEXT7_API_KEY
            else {}
        ),
        "require_approval": "never",
    },
)
```

### 更新 agent

我們建立一個新的 agent，加上這兩個額外的 tool，並相應更新 instructions。
為了避免套用 diff 時 context 對不上，這個 agent 會被指定不要用指令編輯檔案。

```python
UPDATED_INSTRUCTIONS = """
You are a coding assistant helping a user with an existing project.
Use the apply_patch tool to edit files based on their feedback. 
When editing files:
- Never edit code via shell commands.
- Always read the file first using `cat` with the shell tool.
- Then generate a unified diff relative to EXACTLY that content.
- Use apply_patch only once per edit attempt.
- If apply_patch fails, stop and report the error; do NOT retry.
You can search the web to find which command you should use based on the technical stack, and use commands to install dependencies if needed.
When the user refers to an external API, use the Context7 MCP server to fetch docs for that API.
For example, if they want to use the OpenAI API, search docs for the openai-python or openai-node sdk depending on the project stack.
"""
```

```python
updated_coding_agent = Agent(
    name="Updated Coding Agent",
    model="gpt-5.1",
    instructions=UPDATED_INSTRUCTIONS,
    tools=[
        WebSearchTool(),
        shell_tool,
        apply_patch_tool,
        context7_tool,
    ]
)
```

### 執行 agent 修改專案

```python
import asyncio
from agents import ItemHelpers, Runner


async def run_updated_coding_agent_with_logs(prompt: str):
    """
    Run the updated coding agent (shell + web + apply_patch + Context7 MCP)
    and stream logs about what's happening.

    - Logs web_search, shell, apply_patch, and MCP (Context7) calls.
    - For apply_patch, logs the outputs returned by the editor.
    - At the end, shows a single "Apply all changes?" prompt for the tutorial.
    """
    print("=== Run starting ===")
    print(f"[user] {prompt}\n")

    apply_patch_seen = False

    # Start streamed run
    result = Runner.run_streamed(
        updated_coding_agent,
        input=prompt,
    )

    async for event in result.stream_events():
        if event.type != "run_item_stream_event":
            continue

        item = event.item

        # 1) Tool calls (function tools, web_search, shell, MCP, etc.)
        if item.type == "tool_call_item":
            raw = item.raw_item
            raw_type_name = type(raw).__name__

            # web_search (hosted Responses tool)
            if raw_type_name == "ResponseFunctionWebSearch":
                print("[tool] web_search – agent is calling web search")

            # shell (new ShellTool executor)
            elif raw_type_name == "LocalShellCall":
                action = getattr(raw, "action", None)
                commands = getattr(action, "commands", None) if action else None
                if commands:
                    print(f"[tool] shell – running commands: {commands}")
                else:
                    print("[tool] shell – running command")

            # MCP (e.g. Context7)
            elif "MCP" in raw_type_name or "Mcp" in raw_type_name:
                tool_name = getattr(raw, "tool_name", None)
                if tool_name is None:
                    action = getattr(raw, "action", None)
                    tool_name = getattr(action, "tool", None) if action else None
                server_label = getattr(raw, "server_label", None)
                label_str = f" (server={server_label})" if server_label else ""
                if tool_name:
                    print(f"[tool] mcp{label_str} – calling tool {tool_name!r}")
                else:
                    print(f"[tool] mcp{label_str} – MCP tool call")

            # Generic fallback for other tools (including hosted ones)
            else:
                print(f"[tool] {raw_type_name} called")

        # 2) Tool call outputs (where apply_patch shows up)
        elif item.type == "tool_call_output_item":
            raw = item.raw_item
            output_preview = str(item.output)

            # Detect apply_patch via raw_item type or output format
            is_apply_patch = False
            if isinstance(raw, dict) and raw.get("type") == "apply_patch_call_output":
                is_apply_patch = True
            elif any(
                output_preview.startswith(prefix)
                for prefix in ("Created ", "Updated ", "Deleted ")
            ):
                is_apply_patch = True

            if is_apply_patch:
                apply_patch_seen = True
                if len(output_preview) > 400:
                    output_preview = output_preview[:400] + "…"
                print(f"[apply_patch] {output_preview}\n")
            else:
                if len(output_preview) > 400:
                    output_preview = output_preview[:400] + "…"
                print(f"[tool output]\n{output_preview}\n")

        # 3) Normal assistant messages
        elif item.type == "message_output_item":
            text = ItemHelpers.text_message_output(item)
            print(f"[assistant]\n{text}\n")

        # 4) Other event types – ignore for now
        else:
            pass

    print("=== Run complete ===\n")

    # Final answer
    print("Final answer:\n")
    print(result.final_output)

    # Single end-of-run confirmation about edits
    if apply_patch_seen:
        _ = print("\n[apply_patch] One or more apply_patch calls were executed.")
    else:
        print("\n[apply_patch] No apply_patch calls detected in this run.")
```

```python
edit_prompt = '''Update the dashboard to add a 'summarize' button in the top right corner.
When clicked, use the OpenAI Responses API with the gpt-5.1 model to generate a summary of the metrics on the dashboard, and display it in a modal.'''
```

```python
await run_updated_coding_agent_with_logs(edit_prompt)
```

??? note "輸出"

    ```text
    === Run starting ===
    [user] Update the dashboard to add a 'summarize' button in the top right corner.
    When clicked, use the OpenAI Responses API with the gpt-5.1 model to generate a summary of the metrics on the dashboard, and display it in a modal.

    Shell command approval required:
      ls
      ls -R
      cat package.json || pip show flask || pip show django || echo 'no package.json'
    Proceed? [y/N] y
    [tool] ResponseOutputMessage called
    [tool output]
    $ ls
    shadcn-dashboard

    $ ls -R
    shadcn-dashboard

    ./shadcn-dashboard:
    components.json
    eslint.config.mjs
    next-env.d.ts
    next.config.ts
    package-lock.json
    package.json
    postcss.config.mjs
    public
    README.md
    src
    tsconfig.json

    ./shadcn-dashboard/public:
    file.svg
    globe.svg
    next.svg
    vercel.svg
    window.svg

    ./shadcn-dashboard/src:
    app
    …
    ... (省略 537 行)
    ```

Agent 更新完專案後（你會看到 "=== Run complete ===" 的 log，接著是最終答案），就會看到更新後的 UI，裡面有呼叫 OpenAI Responses API 來摘要 dashboard 內容。

**注意**：如果這一步失敗，可以重跑 agent loop。正式環境裡，你會實作外層迴圈來處理錯誤，或等待使用者輸入再迭代。

![final dashboard screenshot](https://cdn.openai.com/cookbook/dashboard_screenshot2.jpg)

## 總結

這份教學我們做了一個 coding agent：能建立專案骨架、用 patch 改進專案、執行指令，還能跟上外部文件的更新。把 GPT 5.1 跟 Agents SDK，以及 `shell`、`apply_patch`、`web_search`、Context7 MCP 這些 tool 組合起來，你可以做出不只是產生程式碼的 agent，而是真的會處理 codebase：執行指令、套用修改、拉進最新脈絡，把專案從頭到尾演進下去。

這個流程是打造 agent 的有力藍圖，讓 agent 更像協作夥伴而不是工具。你可以延伸這個模式，把 agent 整合進 IDE 或 code sandbox、從零產生新 app、處理大型 codebase，甚至即時跟開發者協作。

## 重點整理
- Agents SDK 定義 agent 只需要 instructions 加 tool 清單，shell 的指令往返流程 SDK 幫你處理。
- shell tool 是模型提議指令、你的環境實際執行。這代表安全責任在你，正式環境一定要 sandbox。
- `apply_patch` 讓 agent 精準改檔，比用 shell 指令改檔更不容易出現 context 對不上的問題。
- MCP server（這裡是 Context7）能讓 agent 取得最新文件，寫出符合新 API 的程式。
- 專案生成可能失敗或超過 turn 上限，正式環境要自己在外層加重試和使用者回饋。

## 練習
1. 把 workspace 目錄換成別的名字，並在 `ShellExecutor` 執行前加一個印出指令的 log，觀察 agent 實際跑了哪些指令。
2. 修改初始 prompt，把 NextJS dashboard 換成別種 app（例如待辦清單），看 agent 怎麼調整。
3. 在 `ShellExecutor` 加入核准機制，遇到 `rm` 之類的指令時要求人工確認才執行。
