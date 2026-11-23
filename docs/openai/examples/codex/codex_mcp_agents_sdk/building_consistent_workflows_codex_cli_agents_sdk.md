---
translated: true
source: examples/codex/codex_mcp_agents_sdk/building_consistent_workflows_codex_cli_agents_sdk.ipynb
---
# Building Consistent Workflows with Codex CLI & Agents SDK

> 原文：[examples/codex/codex_mcp_agents_sdk/building_consistent_workflows_codex_cli_agents_sdk.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/codex/codex_mcp_agents_sdk/building_consistent_workflows_codex_cli_agents_sdk.ipynb)



## 這篇在做什麼

把 Codex CLI 當成 MCP Server，接進 Agents SDK，先做一個 Designer 加 Developer 的單 agent 範例產生小遊戲，再擴充成有 Project Manager 把關的多 agent 團隊。最後用 Traces 看 agent 之間怎麼交接。

## 學完你會

- 用 `codex mcp` 把 Codex CLI 跑成 MCP Server，並知道它提供的 `codex()` 和 `codex-reply()` 兩個 tool 各做什麼。
- 在 Agents SDK 裡建立 Designer、Developer 這類 agent，讓它們透過 Codex MCP 真的寫出檔案。
- 做出由 Project Manager 檢查產出檔案才放行的 handoff 流程，並在 Traces dashboard 驗證執行過程。

## 開跑前

- 需要 OpenAI API key，放在目錄下 `.env` 裡的 `OPENAI_API_KEY`。
- 需要能跑 Python 與 JavaScript 的開發環境（例如 VS Code 或 Cursor）。
- 多 agent 範例實測大約要跑 11 分鐘，會花 API 費用。


> **已封存的範例：Codex MCP server 已經棄用。** 這份 notebook 用的是 `codex mcp-server`，[目前的文件](https://learn.chatgpt.com/docs/mcp-server)只為既有整合保留它。新的自動化和 CI job，請從 [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk) 開始。如果需要更深的整合，包含管理認證、對話歷史、approval 和串流事件，請用 [Codex app server](https://learn.chatgpt.com/docs/app-server)。這些是不同的介面，下面的程式碼不是遷移範例。

### 讓 agent 開發可重複、可追蹤、可擴展

## 簡介
開發者做什麼事都追求一致性。有了 Codex CLI 和 Agents SDK，這種一致性可以擴展到前所未有的規模。不管你是在重構大型 codebase、推出新功能，還是導入新的測試框架，Codex 都能無縫整合到 CLI、IDE 和雲端工作流程，自動化並落實可重複的開發模式。

這個單元會用 Agents SDK 建立單 agent 和多 agent 系統，並把 Codex CLI 當成 MCP Server 提供出來。這樣可以得到：
- **一致性和可重複性**：給每個 agent 限定範圍的上下文。
- **可擴展的編排**：協調單 agent 和多 agent 系統。
- **可觀測性與可稽核性**：檢視完整的 agent stack trace。

## 內容大綱
- 把 Codex CLI 初始化成 MCP Server：怎麼把 Codex 跑成長時間運作的 MCP process。
- 建立單 agent 系統：用 Codex MCP 處理限定範圍的任務。
- 編排多 agent 工作流程：協調多個專職 agent。
- 追蹤 agent 行為：用 agent trace 取得可見度並做評估。

## 前置需求與設定
開始之前，請確認你有：
- 基本的寫程式經驗：要能自在使用 Python 和 JavaScript。
- 開發環境：需要一個 IDE，像 VS Code 或 Cursor。
- OpenAI API key：在 OpenAI Dashboard 建立或找到你的 API key。


## 環境設定
1. 在你的目錄建立一個 `.env` 資料夾，並加入你的 `OPENAI_API_KEY`
2. 安裝依賴套件


```python
%pip install openai-agents openai ## install dependencies
```

## 把 Codex CLI 初始化成 MCP Server
這裡在 Agents SDK 裡把 Codex CLI 跑成 MCP Server。我們提供 `codex mcp` 的初始化參數。這個指令會把 Codex CLI 啟動成 MCP server，並在 MCP server 上提供兩個 Codex tool：`codex()` 和 `codex-reply()`。這是 Agents SDK 需要呼叫 Codex 時，底層會用的 tool。
- `codex()` 用來建立對話。
- `codex-reply()` 用來延續對話。

```python
import asyncio
from agents import Agent, Runner
from agents.mcp import MCPServerStdio

async def main() -> None:
    async with MCPServerStdio(
        name="Codex CLI",
        params={
            "command": "npx",
            "args": ["-y", "codex", "mcp-server"],
        },
        client_session_timeout_seconds=360000,
    ) as codex_mcp_server:
        print("Codex MCP server started.")
        # We will add more code here in the next section
        return
```

另外注意，我們把 MCP Server 的 timeout 拉長了，讓 Codex CLI 有足夠時間執行並完成任務。

---

## 建立單 agent 系統
先從一個簡單的例子開始用我們的 Codex MCP Server。我們定義兩個 agent：
1. **Designer Agent**：發想並為遊戲寫一份簡短的 brief。
2. **Developer Agent**：依照 Designer 的規格實作一個簡單的遊戲。

```python
developer_agent = Agent(
    name="Game Developer",
    instructions=(
        "You are an expert in building simple games using basic html + css + javascript with no dependencies. "
        "Save your work in a file called index.html in the current directory."
        "Always call codex with \"approval-policy\": \"never\" and \"sandbox\": \"workspace-write\""
    ),
    mcp_servers=[codex_mcp_server],
)

designer_agent = Agent(
    name="Game Designer",
    instructions=(
        "You are an indie game connoisseur. Come up with an idea for a single page html + css + javascript game that a developer could build in about 50 lines of code. "
        "Format your request as a 3 sentence design brief for a game developer and call the Game Developer coder with your idea."
    ),
    model="gpt-5",
    handoffs=[developer_agent],
)

result = await Runner.run(designer_agent, "Implement a fun new game!")
```

注意，我們讓 Developer agent 可以直接把檔案寫到專案目錄，不用問使用者要權限。

現在執行程式，你會看到產生一個 `index.html`。打開檔案，開始玩遊戲吧！

下面是我的 agent 系統做出來的遊戲截圖。你的會不一樣！

| 遊戲進行畫面 | Game Over 分數 |
| :---: | :---: |
| <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/game_example_1.png" alt="Example gameplay" width="320" /> | <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/game_example_2.png" alt="Game Over Score" width="320" /> |

這是完整可執行的程式。注意可能要跑幾分鐘。看到產生 index.html 就代表成功。你也可能看到一些關於格式的 MCP event 警告，可以忽略這些 event。

```python
import os
from dotenv import load_dotenv
import asyncio
from agents import Agent, Runner, set_default_openai_api
from agents.mcp import MCPServerStdio

load_dotenv(override=True) # load the API key from the .env file. We set override to True here to ensure the notebook is loading any changes
set_default_openai_api(os.getenv("OPENAI_API_KEY"))

async def main() -> None:
    async with MCPServerStdio(
        name="Codex CLI",
        params={
            "command": "npx",
            "args": ["-y", "codex", "mcp-server"],
        },
        client_session_timeout_seconds=360000,
    ) as codex_mcp_server:
        developer_agent = Agent(
            name="Game Developer",
            instructions=(
                "You are an expert in building simple games using basic html + css + javascript with no dependencies. "
                "Save your work in a file called index.html in the current directory."
                "Always call codex with \"approval-policy\": \"never\" and \"sandbox\": \"workspace-write\""
            ),
            mcp_servers=[codex_mcp_server],
        )

        designer_agent = Agent(
            name="Game Designer",
            instructions=(
                "You are an indie game connoisseur. Come up with an idea for a single page html + css + javascript game that a developer could build in about 50 lines of code. "
                "Format your request as a 3 sentence design brief for a game developer and call the Game Developer coder with your idea."
            ),
            model="gpt-5",
            handoffs=[developer_agent],
        )

        result = await Runner.run(designer_agent, "Implement a fun new game!")
        # print(result.final_output)


if __name__ == "__main__":
    # Jupyter/IPython already runs an event loop, so calling asyncio.run() here
    # raises "asyncio.run() cannot be called from a running event loop".
    # Workaround: if a loop is running (notebook), use top-level `await`; otherwise use asyncio.run().
    try:
        asyncio.get_running_loop()
        await main()
    except RuntimeError:
        asyncio.run(main())
```

---

## 編排多 agent 工作流程
比較大的流程，我們引入一個 agent 團隊：
- **Project Manager**：拆解任務清單、建立需求，並協調工作。
- **Designer**：產出 UI/UX 規格。
- **Frontend Developer**：實作 UI/UX。
- **Backend Developer**：實作 API 和邏輯。
- **Tester**：依驗收條件驗證輸出。

這個範例裡，我們刻意讓 Project Manager agent 在每個下游專職 agent 之間做 gating 邏輯。這樣能確保 handoff 之前，產出物已經存在。這對應真實世界的企業流程，像 JIRA 任務編排、長鏈的 rollout 和 QA 簽核。

<div align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_codex_workflow.png" alt="Multi-Agent Codex Workflow with Codex MCP" style="max-width: 100%; width: 960px;" />
  <br />
  <em>使用 Codex MCP 的多 agent 編排，透過 gated handoff 產出 artifact。</em>
</div>


在這個結構裡，每個 agent 都有專門的職責。Project Manager 整體負責協調其他所有 agent，並確保整個任務完成。

## 定義 Codex CLI MCP Server
我們設定 MCP Server 來初始化 Codex CLI，做法跟單 agent 範例一樣。

```python
async def main() -> None:
    async with MCPServerStdio(
        name="Codex CLI",
        params={
            "command": "npx",
            "args": ["-y", "codex", "mcp-server"],
        },
        client_session_timeout_seconds=360000,
    ) as codex_mcp_server:
        print("Codex MCP server started.")
        # We will add more code here in the next section
        return
 ```



## 定義各個專職 agent
下面定義每個專職 agent，並讓它們可以存取我們的 Codex MCP server。注意我們也把 `RECOMMENDED_PROMPT_PREFIX` 傳給每個 agent，它能幫系統優化 agent 之間的 handoff。

```python
# Downstream agents are defined first for clarity, then PM references them in handoffs.
designer_agent = Agent(
    name="Designer",
    instructions=(
        f"""{RECOMMENDED_PROMPT_PREFIX}"""
        "You are the Designer.\n"
        "Your only source of truth is AGENT_TASKS.md and REQUIREMENTS.md from the Project Manager.\n"
        "Do not assume anything that is not written there.\n\n"
        "You may use the internet for additional guidance or research."
        "Deliverables (write to /design):\n"
        "- design_spec.md – a single page describing the UI/UX layout, main screens, and key visual notes as requested in AGENT_TASKS.md.\n"
        "- wireframe.md – a simple text or ASCII wireframe if specified.\n\n"
        "Keep the output short and implementation-friendly.\n"
        "When complete, handoff to the Project Manager with transfer_to_project_manager."
        "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
    ),
    model="gpt-5",
    tools=[WebSearchTool()],
    mcp_servers=[codex_mcp_server],
    handoffs=[],
)

frontend_developer_agent = Agent(
    name="Frontend Developer",
    instructions=(
        f"""{RECOMMENDED_PROMPT_PREFIX}"""
        "You are the Frontend Developer.\n"
        "Read AGENT_TASKS.md and design_spec.md. Implement exactly what is described there.\n\n"
        "Deliverables (write to /frontend):\n"
        "- index.html – main page structure\n"
        "- styles.css or inline styles if specified\n"
        "- main.js or game.js if specified\n\n"
        "Follow the Designer’s DOM structure and any integration points given by the Project Manager.\n"
        "Do not add features or branding beyond the provided documents.\n\n"
        "When complete, handoff to the Project Manager with transfer_to_project_manager_agent."
        "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
    ),
    model="gpt-5",
    mcp_servers=[codex_mcp_server],
    handoffs=[],
)

backend_developer_agent = Agent(
    name="Backend Developer",
    instructions=(
        f"""{RECOMMENDED_PROMPT_PREFIX}"""
        "You are the Backend Developer.\n"
        "Read AGENT_TASKS.md and REQUIREMENTS.md. Implement the backend endpoints described there.\n\n"
        "Deliverables (write to /backend):\n"
        "- package.json – include a start script if requested\n"
        "- server.js – implement the API endpoints and logic exactly as specified\n\n"
        "Keep the code as simple and readable as possible. No external database.\n\n"
        "When complete, handoff to the Project Manager with transfer_to_project_manager_agent."
        "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
    ),
    model="gpt-5",
    mcp_servers=[codex_mcp_server],
    handoffs=[],
)

tester_agent = Agent(
    name="Tester",
    instructions=(
        f"""{RECOMMENDED_PROMPT_PREFIX}"""
        "You are the Tester.\n"
        "Read AGENT_TASKS.md and TEST.md. Verify that the outputs of the other roles meet the acceptance criteria.\n\n"
        "Deliverables (write to /tests):\n"
        "- TEST_PLAN.md – bullet list of manual checks or automated steps as requested\n"
        "- test.sh or a simple automated script if specified\n\n"
        "Keep it minimal and easy to run.\n\n"
        "When complete, handoff to the Project Manager with transfer_to_project_manager."
        "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
    ),
    model="gpt-5",
    mcp_servers=[codex_mcp_server],
    handoffs=[],
)
```



每個角色完成工作後，會呼叫 `transfer_to_project_manager_agent`，讓 Project Manager 確認需要的檔案存在（或要求修正），才解鎖下一個團隊。

## 定義 Project Manager Agent
Project Manager 是唯一收到初始 prompt 的 agent，它會在專案目錄建立規劃文件，並在每次轉交之前執行把關邏輯。

```python        
project_manager_agent = Agent(
name="Project Manager",
instructions=(
    f"""{RECOMMENDED_PROMPT_PREFIX}"""
    """
    You are the Project Manager.

    Objective:
    Convert the input task list into three project-root files the team will execute against.

    Deliverables (write in project root):
    - REQUIREMENTS.md: concise summary of product goals, target users, key features, and constraints.
    - TEST.md: tasks with [Owner] tags (Designer, Frontend, Backend, Tester) and clear acceptance criteria.
    - AGENT_TASKS.md: one section per role containing:
        - Project name
        - Required deliverables (exact file names and purpose)
        - Key technical notes and constraints

    Process:
    - Resolve ambiguities with minimal, reasonable assumptions. Be specific so each role can act without guessing.
    - Create files using Codex MCP with {"approval-policy":"never","sandbox":"workspace-write"}.
    - Do not create folders. Only create REQUIREMENTS.md, TEST.md, AGENT_TASKS.md.

    Handoffs (gated by required files):
    1) After the three files above are created, hand off to the Designer with transfer_to_designer_agent and include REQUIREMENTS.md, and AGENT_TASKS.md.
    2) Wait for the Designer to produce /design/design_spec.md. Verify that file exists before proceeding.
    3) When design_spec.md exists, hand off in parallel to both:
        - Frontend Developer with transfer_to_frontend_developer_agent (provide design_spec.md, REQUIREMENTS.md, AGENT_TASKS.md).
        - Backend Developer with transfer_to_backend_developer_agent (provide REQUIREMENTS.md, AGENT_TASKS.md).
    4) Wait for Frontend to produce /frontend/index.html and Backend to produce /backend/server.js. Verify both files exist.
    5) When both exist, hand off to the Tester with transfer_to_tester_agent and provide all prior artifacts and outputs.
    6) Do not advance to the next handoff until the required files for that step are present. If something is missing, request the owning agent to supply it and re-check.

    PM Responsibilities:
    - Coordinate all roles, track file completion, and enforce the above gating checks.
    - Do NOT respond with status updates. Just handoff to the next agent until the project is complete.
    """
),
model="gpt-5",
model_settings=ModelSettings(
    reasoning=Reasoning(effort="medium")
),
handoffs=[designer_agent, frontend_developer_agent, backend_developer_agent, tester_agent],
mcp_servers=[codex_mcp_server],
)
```

建好 Project Manager 之後，腳本會把每個專職 agent 的 handoff 都設回 Project Manager。這樣能確保交付物先回來驗證，才進行下一步。

```python
designer_agent.handoffs = [project_manager_agent]
frontend_developer_agent.handoffs = [project_manager_agent]
backend_developer_agent.handoffs = [project_manager_agent]
tester_agent.handoffs = [project_manager_agent]
```
## 加入你的任務清單
這是 Project Manager 要細化成整個系統具體需求和任務的任務。

```python
task_list = """
Goal: Build a tiny browser game to showcase a multi-agent workflow.

High-level requirements:
- Single-screen game called "Bug Busters".
- Player clicks a moving bug to earn points.
- Game ends after 20 seconds and shows final score.
- Optional: submit score to a simple backend and display a top-10 leaderboard.

Roles:
- Designer: create a one-page UI/UX spec and basic wireframe.
- Frontend Developer: implement the page and game logic.
- Backend Developer: implement a minimal API (GET /health, GET/POST /scores).
- Tester: write a quick test plan and a simple script to verify core routes.

Constraints:
- No external database—memory storage is fine.
- Keep everything readable for beginners; no frameworks required.
- All outputs should be small files saved in clearly named folders.
"""
```

接著執行你的系統，坐著等，就會看到這些 agent 動起來，幾分鐘內做出一個遊戲！下面附了完整可執行的程式。完成後，你會看到產生下面的檔案目錄。注意這個多 agent 編排通常要大約 11 分鐘才會完全跑完。

```markdown
root_directory/
├── AGENT_TASKS.md
├── REQUIREMENTS.md
├── backend
│   ├── package.json
│   └── server.js
├── design
│   ├── design_spec.md
│   └── wireframe.md
├── frontend
│   ├── game.js
│   ├── index.html
│   └── styles.css
└── TEST.md
```

用 `node server.js` 啟動你的 backend server，然後打開 `index.html` 玩你的遊戲。


```python
import os
from dotenv import load_dotenv
import asyncio
from agents import Agent, Runner, WebSearchTool, ModelSettings, set_default_openai_api
from agents.mcp import MCPServerStdio
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from openai.types.shared import Reasoning

load_dotenv(override=True) # load the API key from the .env file. We set override to True here to ensure the notebook is loading any changes
set_default_openai_api(os.getenv("OPENAI_API_KEY"))

async def main() -> None:
    async with MCPServerStdio(
        name="Codex CLI",
        params={"command": "npx", "args": ["-y", "codex", "mcp-server"]},
        client_session_timeout_seconds=360000,
    ) as codex_mcp_server:

        # Downstream agents are defined first for clarity, then PM references them in handoffs.
        designer_agent = Agent(
            name="Designer",
            instructions=(
                f"""{RECOMMENDED_PROMPT_PREFIX}"""
                "You are the Designer.\n"
                "Your only source of truth is AGENT_TASKS.md and REQUIREMENTS.md from the Project Manager.\n"
                "Do not assume anything that is not written there.\n\n"
                "You may use the internet for additional guidance or research."
                "Deliverables (write to /design):\n"
                "- design_spec.md – a single page describing the UI/UX layout, main screens, and key visual notes as requested in AGENT_TASKS.md.\n"
                "- wireframe.md – a simple text or ASCII wireframe if specified.\n\n"
                "Keep the output short and implementation-friendly.\n"
                "When complete, handoff to the Project Manager with transfer_to_project_manager."
                "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
            ),
            model="gpt-5",
            tools=[WebSearchTool()],
            mcp_servers=[codex_mcp_server],
            handoffs=[],
        )

        frontend_developer_agent = Agent(
            name="Frontend Developer",
            instructions=(
                f"""{RECOMMENDED_PROMPT_PREFIX}"""
                "You are the Frontend Developer.\n"
                "Read AGENT_TASKS.md and design_spec.md. Implement exactly what is described there.\n\n"
                "Deliverables (write to /frontend):\n"
                "- index.html – main page structure\n"
                "- styles.css or inline styles if specified\n"
                "- main.js or game.js if specified\n\n"
                "Follow the Designer’s DOM structure and any integration points given by the Project Manager.\n"
                "Do not add features or branding beyond the provided documents.\n\n"
                "When complete, handoff to the Project Manager with transfer_to_project_manager_agent."
                "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
            ),
            model="gpt-5",
            mcp_servers=[codex_mcp_server],
            handoffs=[],
        )

        backend_developer_agent = Agent(
            name="Backend Developer",
            instructions=(
                f"""{RECOMMENDED_PROMPT_PREFIX}"""
                "You are the Backend Developer.\n"
                "Read AGENT_TASKS.md and REQUIREMENTS.md. Implement the backend endpoints described there.\n\n"
                "Deliverables (write to /backend):\n"
                "- package.json – include a start script if requested\n"
                "- server.js – implement the API endpoints and logic exactly as specified\n\n"
                "Keep the code as simple and readable as possible. No external database.\n\n"
                "When complete, handoff to the Project Manager with transfer_to_project_manager_agent."
                "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
            ),
            model="gpt-5",
            mcp_servers=[codex_mcp_server],
            handoffs=[],
        )

        tester_agent = Agent(
            name="Tester",
            instructions=(
                f"""{RECOMMENDED_PROMPT_PREFIX}"""
                "You are the Tester.\n"
                "Read AGENT_TASKS.md and TEST.md. Verify that the outputs of the other roles meet the acceptance criteria.\n\n"
                "Deliverables (write to /tests):\n"
                "- TEST_PLAN.md – bullet list of manual checks or automated steps as requested\n"
                "- test.sh or a simple automated script if specified\n\n"
                "Keep it minimal and easy to run.\n\n"
                "When complete, handoff to the Project Manager with transfer_to_project_manager."
                "When creating files, call Codex MCP with {\"approval-policy\":\"never\",\"sandbox\":\"workspace-write\"}."
            ),
            model="gpt-5",
            mcp_servers=[codex_mcp_server],
            handoffs=[],
        )

        project_manager_agent = Agent(
            name="Project Manager",
            instructions=(
                f"""{RECOMMENDED_PROMPT_PREFIX}"""
                """
                You are the Project Manager.

                Objective:
                Convert the input task list into three project-root files the team will execute against.

                Deliverables (write in project root):
                - REQUIREMENTS.md: concise summary of product goals, target users, key features, and constraints.
                - TEST.md: tasks with [Owner] tags (Designer, Frontend, Backend, Tester) and clear acceptance criteria.
                - AGENT_TASKS.md: one section per role containing:
                  - Project name
                  - Required deliverables (exact file names and purpose)
                  - Key technical notes and constraints

                Process:
                - Resolve ambiguities with minimal, reasonable assumptions. Be specific so each role can act without guessing.
                - Create files using Codex MCP with {"approval-policy":"never","sandbox":"workspace-write"}.
                - Do not create folders. Only create REQUIREMENTS.md, TEST.md, AGENT_TASKS.md.

                Handoffs (gated by required files):
                1) After the three files above are created, hand off to the Designer with transfer_to_designer_agent and include REQUIREMENTS.md, and AGENT_TASKS.md.
                2) Wait for the Designer to produce /design/design_spec.md. Verify that file exists before proceeding.
                3) When design_spec.md exists, hand off in parallel to both:
                   - Frontend Developer with transfer_to_frontend_developer_agent (provide design_spec.md, REQUIREMENTS.md, AGENT_TASKS.md).
                   - Backend Developer with transfer_to_backend_developer_agent (provide REQUIREMENTS.md, AGENT_TASKS.md).
                4) Wait for Frontend to produce /frontend/index.html and Backend to produce /backend/server.js. Verify both files exist.
                5) When both exist, hand off to the Tester with transfer_to_tester_agent and provide all prior artifacts and outputs.
                6) Do not advance to the next handoff until the required files for that step are present. If something is missing, request the owning agent to supply it and re-check.

                PM Responsibilities:
                - Coordinate all roles, track file completion, and enforce the above gating checks.
                - Do NOT respond with status updates. Just handoff to the next agent until the project is complete.
                """
            ),
            model="gpt-5",
            model_settings=ModelSettings(
                reasoning=Reasoning(effort="medium")
            ),
            handoffs=[designer_agent, frontend_developer_agent, backend_developer_agent, tester_agent],
            mcp_servers=[codex_mcp_server],
        )

        designer_agent.handoffs = [project_manager_agent]
        frontend_developer_agent.handoffs = [project_manager_agent]
        backend_developer_agent.handoffs = [project_manager_agent]
        tester_agent.handoffs = [project_manager_agent]

        # Example task list input for the Project Manager
        task_list = """
Goal: Build a tiny browser game to showcase a multi-agent workflow.

High-level requirements:
- Single-screen game called "Bug Busters".
- Player clicks a moving bug to earn points.
- Game ends after 20 seconds and shows final score.
- Optional: submit score to a simple backend and display a top-10 leaderboard.

Roles:
- Designer: create a one-page UI/UX spec and basic wireframe.
- Frontend Developer: implement the page and game logic.
- Backend Developer: implement a minimal API (GET /health, GET/POST /scores).
- Tester: write a quick test plan and a simple script to verify core routes.

Constraints:
- No external database—memory storage is fine.
- Keep everything readable for beginners; no frameworks required.
- All outputs should be small files saved in clearly named folders.
"""

        # Only the Project Manager receives the task list directly
        result = await Runner.run(project_manager_agent, task_list, max_turns=30)
        print(result.final_output)

if __name__ == "__main__":
    # Jupyter/IPython already runs an event loop, so calling asyncio.run() here
    # raises "asyncio.run() cannot be called from a running event loop".
    # Workaround: if a loop is running (notebook), use top-level `await`; otherwise use asyncio.run().
    try:
        asyncio.get_running_loop()
        await main()
    except RuntimeError:
        asyncio.run(main())
```

---

## 用 Traces 追蹤 agent 行為
隨著 agent 系統越來越複雜，看清楚這些 agent 怎麼互動很重要。我們可以用 Traces dashboard，它會記錄：
- prompt、tool call，以及 agent 之間的 handoff。
- MCP Server 呼叫、Codex CLI 呼叫、執行時間和檔案寫入。
- 錯誤和警告。

來看上面那個 agent 團隊的 trace。

<div align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_trace.png" alt="Multi-Agent Codex Workflow with Codex MCP" style="max-width: 100%; width: 960px;" />
</div>

從這份 Trace 可以確認，每次 agent handoff 都由 Project Manager Agent 主導，它會先確認特定產出物存在，才交給下一個 agent。另外，我們也能看到 Codex MCP Server 的具體呼叫，以及每個輸出是呼叫 Responses API 產生的。timeline 的長條標示執行時間，容易找出跑很久的步驟，也看得出控制權怎麼在 agent 之間傳遞。

你甚至可以點進每個 trace，看 prompt、tool call 和其他 metadata 的細節。長期下來，可以用這些資訊進一步調整、優化並追蹤你的 agent 系統表現。

<div align="center">
  <img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/multi_agent_trace_details.png" alt="Multi-Agent Trace Details" style="max-width: 100%; width: 960px;" />
</div>


---

## 這份指南做了什麼的回顧
這份指南走過了用 Codex CLI 和 Agents SDK 建立一致、可擴展工作流程的過程。具體涵蓋了：

- **Codex MCP Server 設定**：怎麼把 Codex CLI 初始化成 MCP server，並讓它成為 agent 互動用的 tool。
- **單 agent 範例**：一個有 Designer Agent 和 Developer Agent 的簡單流程，Codex 以確定性的方式執行限定範圍的任務，產出可玩的遊戲。
- **多 agent 編排**：擴充成有 Project Manager、Designer、Frontend Developer、Backend Developer 和 Tester 的大型流程，對應複雜的任務編排和簽核流程。
- **Traces 與可觀測性**：用內建的 Traces 擷取 prompt、tool call、handoff、執行時間和產出物，讓 agent 行為完全可見，方便 debug、評估和之後的優化。

---

## 往前走：應用這些心得
看過 Codex MCP 和 Agents SDK 的實際運作，下面是你可以在真實專案裡應用這些概念、取得價值的方式：

### 1. 擴展到真實世界的 rollout
- 把同樣的多 agent 編排用在大型程式碼重構（例如 500 個以上的檔案、框架遷移）。
- 用 Codex MCP 的確定性執行，做長時間、可稽核、進度可追蹤的 rollout。

### 2. 加快交付又不失控
- 組織專職 agent 團隊來並行開發，同時保留 gating 邏輯來驗證產出物。
- 縮短新功能、測試或 codebase 現代化的週轉時間。

### 3. 延伸並接上你的開發工作流程
- 透過 webhook，把 MCP 驅動的 agent 接上 Jira、GitHub 或 CI/CD pipeline，做自動、可重複的開發循環。
- 在多 agent 服務編排裡運用 Codex MCP：不只產生程式碼，也包含文件、QA 和部署。


## 重點整理

- Codex CLI 用 `codex mcp` 跑成 MCP Server 後，對 agent 來說就是兩個 tool：`codex()` 開新對話、`codex-reply()` 延續對話。
- 給每個 agent 限定的職責和上下文，是結果可重複的關鍵。
- 多 agent 流程讓專職 agent 做完都 handoff 回 Project Manager，由它檢查產出檔案是否存在才放行，這就是 gating。
- Traces 能看到 prompt、tool call、handoff 和執行時間，agent 系統變複雜後是 debug 和優化的依據。
- 這個 MCP server 方式已封存，新專案應改看 Codex SDK 或 Codex app server。

## 練習

1. 在單 agent 範例改 Designer 的 instructions，換成不同類型的遊戲，重跑看 `index.html` 有什麼變化。
2. 調整 Developer agent 的 instructions，限制它只能修改特定檔案，觀察它的行為，也檢查 MCP Server 的 timeout 設定夠不夠用。
3. 在多 agent 範例的 Project Manager instructions 加一條新的 gating 規則（例如 Tester 前必須存在某份測試文件），跑完後到 Traces dashboard 確認 handoff 順序有照規則走。
