---
translated: true
source: claude_agent_sdk/07_Hosting_the_agent.ipynb
---

# 把 agent 部署上線

> 原文：[claude_agent_sdk/07_Hosting_the_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/07_Hosting_the_agent.ipynb)

把 notebook 00 的 research agent 部署到三個成熟度的層級（Docker、Modal、Kubernetes），每一層用同一個 container image 和同一個 HTTP 介面。

## 這篇在做什麼

這篇把 notebook 00 那個 research agent 包成 container，用同一個 image 和同一組 HTTP API，依序部署到 Docker、Modal 和 Kubernetes。agent 程式碼完全不變，變的只是 container 外面的營運機制：誰負責啟動、路由、管理生命週期和保存 session。

## 學完你會

- 把 Agent SDK 的 agent 包成 Docker image，用一次性模式跑批次工作，或用 FastAPI server 持續接對話
- 用 `resume=` 加 `/data` volume，讓 container 重啟後對話還能接下去
- 說得出 Docker、Modal、Kubernetes 三層各適合什麼情境，以及什麼時候該往上升級

## 開跑前

需要 Docker、Anthropic API key，做 Tier 2 還要有 Modal 帳號，Tier 3 用本機的 kind cluster。整份跑完大約 $1 到 $2 的 API 費用加幾分錢的 Modal 運算。這份 notebook 需要本機 Docker 跟 `modal setup` 開瀏覽器，不適合在 Colab 裡完整跑，Colab 上建議只讀不跑。

你在 [notebook 00](00_The_one_liner_research_agent.md) 做了一個 research agent，它跑在你的筆電上。現在別人要用它：隊友、cron job、web app、客戶。這表示它得跑在*你終端機以外的地方*，要一直活著，重啟後對話還在，而且不能洩漏你的 API key。

這份 notebook 拿同一個 agent，部署過三個層級：

| 層級 | 跑在哪 | 什麼時候用 |
|---|---|---|
| **1. Docker** | 你的機器 / 單一 VM | 開發迴圈、內部工具、單一租戶 |
| **2. Modal** | 託管的 serverless | 想要一個 URL 和 scale-to-zero，又不想管基礎設施 |
| **3. Kubernetes** | 你自己的 cluster | 多租戶、受管制環境、要完全掌控 |

三個層級的 agent 程式碼、container image 和 HTTP 介面**完全一樣**，只有 container 外圍的營運機制不同。一旦 agent 被包進 container、前面有穩定的介面，選 host 就只是部署決策，不是重寫。

> **整份 notebook 從頭跑到尾的成本：** 大約 Anthropic API **$1 到 $2**，加上 Modal 運算**幾分錢**。每一層都有清理步驟。

所有部署相關的程式碼都在這份 notebook 旁邊的 [`hosting/`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/hosting) 資料夾。

## 開始前：你真的該用 Agent SDK 嗎？

如果你在做**面向客戶的聊天產品**，先看 [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)。託管、session 和 UI 都是現成的，這份 notebook 大部分你都可以跳過。

需要**程式化控制**時，Agent SDK 才是對的選擇：批次和任務型的 agent、內部工具、嵌在你自己後端的 agent，或是必須自己掌握基礎設施的受管制環境。如果你是這種情況，請繼續讀。

## 心智模型

三個名詞要分清楚：

- **process** 是一個載入了 SDK 的 Python 直譯器行程，它會跟 Anthropic API 溝通。
- **session** 是一段對話：prompt 歷史、tool 呼叫和結果，SDK 會寫到磁碟，之後可以用 `resume=` 接回來。
- **container** 是打包好的 process 加上它的檔案系統：你的 agent 程式碼、SDK（內含它驅動的 Claude Code CLI），以及放 session 的地方。

跟 in-process 的 SDK（OpenAI Agents SDK、Google ADK）不一樣，那些 SDK 的 "agent" 是你在 web server 裡 instantiate 的物件，而 Claude Agent SDK 的 agent **本身就是**一個 process。這讓隔離變得很簡單（一個 container 就是一個爆炸半徑），但也表示部署是分散式系統問題，不是 `pip install` 能解決的。

每個層級的部署都要做同樣四件事：

```
┌────────────────────────────────────────────────────────────────────┐
│  caller ──► gateway ──► [ spawn | route ] ──► agent container ──► API
│                 │                                     │
│                 └── auth (not the agent's job)        └── /data  (persist)
│                                                                      │
│  orchestrator ──────────────── lifecycle ────────────────────────────┘
└────────────────────────────────────────────────────────────────────┘
```

1. 有工作進來時**啟動**一個 container
2. 把每個請求**路由**到擁有該 session 的 container
3. **生命週期**：關掉閒置的 container，重啟當掉的
4. **持久化** session 紀錄，讓重啟不會丟掉對話

Tier 1 這四件事都手動做。Tier 2 把啟動和生命週期交給 Modal。Tier 3 把四件事都交給 Kubernetes 加一個小 gateway。agent container 從頭到尾沒變。

## 要部署的 agent

我們重用 notebook 00 的 [`research_agent/agent.py`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/research_agent/agent.py)，就是那個有 `WebSearch` 和 `Read` 的一行式 research agent。如果還沒做過 notebook 00，請先做，這份 notebook 假設 agent 已經能跑。

`hosting/` 只多了一個薄薄的 HTTP server 和一個 Dockerfile。system prompt 直接來自 `research_agent.agent`，我們用 import 而不是複製。有一個刻意的差異：託管版 server 把 tool 清單縮減成只有 `WebSearch`。server 上沒有上傳路徑，`Read` 能碰到的檔案只剩其他 session 的紀錄和 container 自己的環境，而被 prompt injection 的網頁結果可能誘導 agent 把這些洩漏出去。`server.py` 裡的註解寫了完整理由。

```python
from research_agent.agent import DEFAULT_MODEL, RESEARCH_SYSTEM_PROMPT

print(f"model: {DEFAULT_MODEL}")
print(RESEARCH_SYSTEM_PROMPT)
```

??? note "輸出"

    ```text
    model: claude-opus-4-6
    You are a research agent specialized in AI.

    When providing research findings:
    - Always include source URLs as citations
    - Format citations as markdown links: [Source Title](URL)
    - Group sources in a "Sources:" section at the end of your response
    ```

### 設定

在 `hosting/.env` 放你的 API key。這個檔案已被 gitignore。

```python
%%bash
test -f hosting/.env || cp hosting/.env.example hosting/.env
echo 'Edit hosting/.env and set ANTHROPIC_API_KEY, then re-run this cell.'
grep -q '^ANTHROPIC_API_KEY=sk-ant-' hosting/.env \
  && ! grep -q 'your-key-here' hosting/.env \
  && echo '✅ key looks set'
```

??? note "輸出"

    ```text
    Edit hosting/.env and set ANTHROPIC_API_KEY, then re-run this cell.
    ```

    ```text
    ✅ key looks set
    ```

---
## Tier 1a：一次性，一個 prompt、一個 container、做完就結束

最簡單的部署：一個 container 從環境變數讀 prompt，把 agent 跑**一次**，印出結果就結束。沒有 server、沒有 session、沒有狀態。


> **模型備註：** 託管層預設用 `claude-sonnet-5-5`，讓你在跑這份 notebook 時測試請求比較便宜。在 `hosting/.env` 設 `MODEL=claude-opus-5-5` 就能跟 notebook 00 的設定完全一致。

這已經夠做很多實際工作了：發票處理、夜間報表產生、批次翻譯、一次性分析。如果你的 agent 的工作是「拿輸入、產出輸出、結束」，這一節之後的東西你都用不到。

[`Dockerfile`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/hosting/Dockerfile) 把 agent、SDK 和 SDK 底層驅動的 Claude Code CLI 打包在一起。build context 是 `claude_agent_sdk/`（這個目錄），不是 `hosting/`，因為 image 還需要 `research_agent/` 和 `utils/`：

```python
%%bash
docker build -f hosting/Dockerfile -t research-agent . | tail -n 3
```

??? note "輸出"

    ```text
    #0 building with "orbstack" instance using docker driver

    #1 [internal] load build definition from D
    ```

    ```text
    ockerfile
    #1 transferring dockerfile: 2.30kB done
    #1 DONE 0.0s

    #2 resolve image config for docker-i
    ```

    ```text
    mage://docker.io/docker/dockerfile:1
    ```

    ```text
    #2 DONE 0.6s
    ```

    ```text

    #3 docker-image://docker.io/docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f
    ```

    ```text
    543c0d03998580f9cb89
    #3 CACHED

    #4 [internal] load metadata for docker.io/library/python:3.11-slim
    ```

    ```text
    #4 DONE 0.5s
    ```

    ```text

    #5 [1/9] FROM docker.io/library/python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a
    ```

    ```text
    9fc0e6e38295747e49ac0
    #5 DONE 0.0s

    #6 [internal] load build context
    #6 transferring context: 814.53
    ```

    ```text
    kB 0.0s done
    #6 DONE 0.0s

    #7 [3/9] WORKDIR /app
    #7 CACHED

    #8 [6/9] COPY research_agent/ ./research
    ```

    ```text
    _agent/
    #8 CACHED

    #9 [7/9] COPY utils/ ./utils/
    #9 CACHED

    #10 [2/9] RUN apt-get update  && apt-get
    ```

    ```text
     install -y --no-install-recommends curl ca-certificates  && curl -fsSL https://deb.nodesource.com/s
    ```

    ```text
    etup_20.x | bash -  && apt-get install -y --no-install-recommends nodejs  && npm install -g @anthrop
    ```

    ```text
    ic-ai/claude-code@2.1.140  && apt-get purge -y curl  && apt-get autoremove -y  && rm -rf /var/lib/ap
    ```

    ```text
    t/lists/*
    #10 CACHED

    #11 [4/9] COPY hosting/requirements.txt ./hosting/requirements.txt
    #11 CACHED
    ```

    ```text

    #12 [5/9] RUN pip install --no-cache-dir -r hosting/requirements.txt
    #12 CACHED

    #13 [8/9] COPY hos
    ```

    ```text
    ting/server.py hosting/run_once.py hosting/entrypoint.sh ./hosting/
    #13 CACHED

    #14 [9/9] RUN chmod
    ```

    ```text
    +x hosting/entrypoint.sh  && touch hosting/__init__.py
    #14 CACHED

    #15 exporting to image
    #15 export
    ```

    ```text
    ing layers done
    #15 writing image sha256:b77b20f557cef5e4b9ef01212f3ba3a0895ee97ff8e31f79d9e1dc0cfb7
    ```

    ```text
    414f5 done
    #15 naming to docker.io/library/research-agent done
    #15 DONE 0.0s
    ```

```python
%%bash
docker run --rm --env-file hosting/.env \
  -e PROMPT='What is the Claude Agent SDK, in one paragraph?' \
  research-agent
```

??? note "輸出"

    ```text
    🤖 Thinking...
    ```

    ```text
    🤖 Using: ToolSearch()
    ```

    ```text
    ✓ Tool completed
    ```

    ```text
    🤖 Thinking...
    ```

    ```text
    🤖 Using: WebSearch()
    ```

    ```text
    ✓ Tool completed
    ```

    ```text
    🤖 Using: WebSearch()
    ```

    ```text
    ✓ Tool completed
    ```

    ```text
    🤖 Thinking...
    ```

    ```text
    The **Claude Agent SDK** is a developer toolkit from Anthropic — available in Python and TypeScrip
    ```

    ```text
    t — that gives developers access to the same tools, agent loop, and context management that power
    ```

    ```text
    Claude Code, enabling them to build fully autonomous AI agents that can read files, run terminal com
    ```

    ```text
    mands, search the web, edit code, and interact with external APIs without requiring developers to ma
    ```

    ```text
    nually implement a tool execution loop. Unlike the standard Claude API (where the developer must han
    ```

    ```text
    dle tool-use loops themselves), the Agent SDK lets Claude manage the agentic loop autonomously, maki
    ```

    ```text
    ng it straightforward to build sophisticated agents such as finance assistants, personal assistants,
    ```

    ```text
     customer support bots, and deep research agents that can operate with minimal human intervention.
    ```

    ```text
    ---

    **Sources:**
    - [Agent SDK Overview – Claude Code Docs](https://code.claude.com/docs/en/agent-
    ```

    ```text
    sdk/overview)
    - [Building Agents with the Claude Agent SDK – Anthropic Engineering](https://www.an
    ```

    ```text
    thropic.com/engineering/building-agents-with-the-claude-agent-sdk)
    - [Agent SDK Overview – Anthrop
    ```

    ```text
    ic API Docs](https://docs.anthropic.com/en/docs/claude-code/sdk/sdk-overview)
    - [claude-agent-sdk-py
    ```

    ```text
    thon – GitHub](https://github.com/anthropics/claude-agent-sdk-python)
    - [claude-agent-sdk-typescri
    ```

    ```text
    pt – GitHub](https://github.com/anthropics/claude-agent-sdk-typescript)
    ```

就這樣。`entrypoint.sh` 看到沒有 `serve` 參數，[`run_once.py`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/hosting/run_once.py) 就會用 `$PROMPT` 呼叫 `research_agent.agent.send_query()`，然後以 exit code 0 結束。

**什麼時候這樣就夠：** 每次呼叫都獨立的任務型工作。可以從 cron、queue worker、CI 步驟，或任何你會跑 CLI 的地方執行。

---
## Tier 1b：混合模式，加個 server 讓對話能繼續

一次性模式沒辦法維持對話，每次 `docker run` 都是新的 session。聊天型的 agent 需要一個長時間運行的 process，接收後續訊息，並每次 resume 對的 session。

[`hosting/server.py`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/hosting/server.py) 是一個約 100 行的 FastAPI app，只做這件事，沒有別的。這個介面是每一層都要遵守的契約：

```
GET  /health                            → 200 {"status": "ok"}
POST /sessions/{session_id}/messages    → 200 text/event-stream of SDK messages
```

`server.py` 有兩點值得注意：

- **server 沒有 auth。** docstring 寫得很明顯。auth 是 gateway 的工作（tier 3 會示範放在哪裡）。server 只驗證 `session_id` 的格式，並信任呼叫端。
- **它維護一個小的對照表，從你的 `session_id` 對應到 SDK 內部的 ID。** SDK 自己產生 session ID，你不能指定。server 從第一輪的 `ResultMessage` 學到 SDK 的 ID，後續訊息就傳給 `resume=`。這個對照表存在 `/data` 下，跟紀錄放在一起。

用 docker-compose 啟動，它也會把 `./sessions` 掛到 `/data`，讓紀錄在重啟後還在：

```python
%%bash
cd hosting/docker && docker compose up --build -d
sleep 3
curl -s http://localhost:8000/health
```

??? note "輸出"

    ```text
     Image research-agent Building
    ```

    ```text
    #1 [internal] load local bake definitions
    ```

    ```text
    #1 reading from stdin 579B done
    #1 DONE 0.0s
    ```

    ```text

    #2 [internal] load build definition from Dockerfile
    #2 transferring dockerfile: 2.30kB done
    ```

    ```text
    #2 DONE 0.0s

    #3 resolve image config for docker-image://docker.io/docker/dockerfile:1
    ```

    ```text
    #3 DONE 0.2s
    ```

    ```text

    #4 docker-image://docker.io/docker/dockerfile:1@sha256:87999aa3d42bdc6bea60565083ee17e86d1f3339802f
    ```

    ```text
    543c0d03998580f9cb89
    #4 CACHED
    ```

    ```text

    #5 [internal] load metadata for docker.io/library/python:3.11-slim
    ```

    ```text
    #5 DONE 0.2s
    ```

    ```text

    #6 [1/9] FROM docker.io/library/python:3.11-slim@sha256:a3ab0b966bc4e91546a033e22093cb840908979487a
    ```

    ```text
    9fc0e6e38295747e49ac0
    #6 DONE 0.0s

    #7 [internal] load build context
    #7 transferring context: 494B d
    ```

    ```text
    one
    #7 DONE 0.0s

    #8 [2/9] RUN apt-get update  && apt-get install -y --no-install-recommends curl ca
    ```

    ```text
    -certificates  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash -  && apt-get install -y -
    ```

    ```text
    -no-install-recommends nodejs  && npm install -g @anthropic-ai/claude-code@2.1.140  && apt-get purge
    ```

    ```text
     -y curl  && apt-get autoremove -y  && rm -rf /var/lib/apt/lists/*
    #8 CACHED

    #9 [3/9] WORKDIR /app
    ```

    ```text
    #9 CACHED

    #10 [4/9] COPY hosting/requirements.txt ./hosting/requirements.txt
    #10 CACHED

    #11 [7/9]
    ```

    ```text
    COPY utils/ ./utils/
    #11 CACHED

    #12 [5/9] RUN pip install --no-cache-dir -r hosting/requirements.tx
    ```

    ```text
    t
    #12 CACHED

    #13 [6/9] COPY research_agent/ ./research_agent/
    #13 CACHED

    #14 [8/9] COPY hosting/se
    ```

    ```text
    rver.py hosting/run_once.py hosting/entrypoint.sh ./hosting/
    #14 CACHED

    #15 [9/9] RUN chmod +x host
    ```

    ```text
    ing/entrypoint.sh  && touch hosting/__init__.py
    #15 CACHED
    ```

    ```text
    #16 exporting to image
    #16 exporting layers done
    #16 writing image sha256:feb4e050b95b69f43fa027a2b5
    ```

    ```text
    a8c87974fba11cd890ba7c669db4aaa459fca0 done
    #16 naming to docker.io/library/research-agent done
    #16
    ```

    ```text
    DONE 0.0s

    #17 resolving provenance for metadata file
    ```

    ```text
    #17 DONE 0.0s
    ```

    ```text
     Image research-agent Built
    ```

    ```text
     Network docker_default Creating
    ```

    ```text
     Network docker_default Created
    ```

    ```text
     Container docker-research-agent-1 Creating
    ```

    ```text
     Container docker-research-agent-1 Created
    ```

    ```text
     Container docker-research-agent-1 Starting
    ```

    ```text
     Container docker-research-agent-1 Started
    ```

    ```text
    {"status":"ok"}
    ```

送一個 prompt 並串流回應（`-N` 關掉 curl 的緩衝，讓你即時看到 event）：

```python
%%bash
curl -N -s -X POST http://localhost:8000/sessions/demo-1/messages \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"What are the three most interesting AI agent trends right now?"}'
```

??? note "輸出"

    ```text
    event: message
    data: {"subtype": "init", "data": {"type": "system", "subtype": "init", "cwd": "/app", "session_id": "77597263-a169-4236-b3d4-8ec14f90fd2b", "tools": ["Task", "TaskOutput", "Bash", "Glob", "Grep", "ExitPlanMode", "Read", "Edit", "Write", "N … [truncated]

    event: message
    data: {"content": [{"id": "toolu_01LpCYD1mQgNAmiDYq55RHyC", "name": "WebSearch", "input": {"query": "AI agent trends 2026"}}], "model": "claude-sonnet-4-6", "parent_tool_use_id": null, "error": null, "usage": {"input_tokens": 685, "cache_cr … [truncated]

    [... 6 events omitted — thinking blocks, tool loading, and web-search result payloads ...]

    event: message
    data: {"content": [{"text": "Great question! Based on the latest research and reports, here are the **three most interesting AI agent trends** right now in 2026:\n\n---\n\n## \ud83e\udd1d 1. Multi-Agent Systems & Orchestration\nThe era of the single, all-purpose AI agent is giving way to **coordinat … [truncated]

    event: message
    data: {"subtype": "success", "duration_ms": 20980, "duration_api_ms": 20812, "is_error": false, "num_turns": 3, "session_id": "77597263-a169-4236-b3d4-8ec14f90fd2b", "stop_reason": "end_turn", "total_cost_usd": 0.0502906, "usage": {"input_t … [truncated]

    event: done
    data:
    ```

現在對**同一個** `session_id` 送後續訊息。agent 記得第一輪，因為 server resume 了那個 session：

```python
%%bash
curl -N -s -X POST http://localhost:8000/sessions/demo-1/messages \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Tell me more about the second one."}'
```

??? note "輸出"

    ```text
    event: message
    data: {"subtype": "init", "data": {"type": "system", "subtype": "init", "cwd": "/app", "session_id": "77597263-a169-4236-b3d4-8ec14f90fd2b", "tools": ["Task", "TaskOutput", "Bash", "Glob", "Grep", "ExitPlanMode", "Read", "Edit", "Write", "N … [truncated]

    event: message
    data: {"content": [{"id": "toolu_01YU5m6b66Kh6GcSN1Kbv7zq", "name": "WebSearch", "input": {"query": "context engineering AI agents 2026 techniques best practices"}}], "model": "claude-sonnet-4-6", "parent_tool_use_id": null, "error": null, … [truncated]

    [... 5 events omitted — thinking blocks, tool loading, and web-search result payloads ...]

    event: message
    data: {"content": [{"text": "## \ud83e\uddf1 Deep Dive: Context Engineering\n\nContext engineering has quickly become **the defining AI skill of 2026**. Here's a thorough breakdown:\n\n---\n\n### What Is It, Exactly?\n\nContext engineering is the discipline of **designing what information an AI mode … [truncated]

    event: message
    data: {"subtype": "success", "duration_ms": 26895, "duration_api_ms": 26791, "is_error": false, "num_turns": 3, "session_id": "77597263-a169-4236-b3d4-8ec14f90fd2b", "stop_reason": "end_turn", "total_cost_usd": 0.08444499999999999, "usage": … [truncated]

    event: done
    data:
    ```

重啟 container 再送*另一個*後續訊息。volume mount 保留了 `/data`，所以對話還在：

```python
%%bash
cd hosting/docker && docker compose restart && sleep 3
curl -N -s -X POST http://localhost:8000/sessions/demo-1/messages \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Summarize what we have discussed so far."}'
```

??? note "輸出"

    ```text
     Container docker-research-agent-1 Restarting
    ```

    ```text
     Container docker-research-agent-1 Started
    ```

    ```text
    event: message
    data: {"subtype": "init", "data": {"type": "system", "subtype": "init", "cwd": "/app
    ```

    ```text
    ", "session_id": "77597263-a169-4236-b3d4-8ec14f90fd2b", "tools": ["Task", "TaskOutput", "Bash", "Gl
    ```

    ```text
    ob", "Grep", "ExitPlanMode", "Read", "Edit", "Write", "NotebookEdit", "WebFetch", "TodoWrite", "WebS
    ```

    ```text
    earch", "TaskStop", "AskUserQuestion", "Skill", "EnterPlanMode", "EnterWorktree", "ExitWorktree", "C
    ```

    ```text
    ronCreate", "CronDelete", "CronList", "RemoteTrigger", "ToolSearch"], "mcp_servers": [], "model": "c
    ```

    ```text
    laude-sonnet-4-6", "permissionMode": "default", "slash_commands": ["update-config", "debug", "simpli
    ```

    ```text
    fy", "batch", "loop", "schedule", "claude-api", "compact", "context", "cost", "heapdump", "init", "p
    ```

    ```text
    r-comments", "release-notes", "review", "security-review", "insights"], "apiKeySource": "ANTHROPIC_A
    ```

    ```text
    PI_KEY", "claude_code_version": "2.1.81", "output_style": "default", "agents": ["general-purpose", "
    ```

    ```text
    statusline-setup", "Explore", "Plan"], "skills": ["update-config", "debug", "simplify", "batch", "lo
    ```

    ```text
    op", "schedule", "claude-api"], "plugins": [], "uuid": "753db5ec-c432-4634-abb4-048eda1e6acd", "fast
    ```

    ```text
    _mode_state": "off"}, "type": "SystemMessage"}
    ```

    ```text
    event: message
    data: {"content": [{"thinking": "The user wants a summary of our conversation so far
    ```

    ```text
    . No tools needed for this.", "signature": "EtYBCmcIDRgCIkBg3e+9ruTNyro9yQA8kMewU6BzRzlQR/MAvKWUy2kk
    ```

    ```text
    CH0rl6bddOJ1gJBmcF4L3GPf/pgLkImzUqg1JV4RfUNgKAEyEWNsYXVkZS1zb25uZXQtNC02OABCCHRoaW5raW5nEgxfs2ACXCyv
    ```

    ```text
    Me8OUvQaDA4MA9sG7f/fI1we2yIwQvNMoFyTGl2/Ps+arqqgLoLYtySrkCOrgNmwcZFIbzQOFWiSJIcsqA7inm8T8n90Kh0wlw1t
    ```

    ```text
    FbJw0suOLM6okhU+eNc0gCr59ENLuBeZhBgC"}], "model": "claude-sonnet-4-6", "parent_tool_use_id": null, "
    ```

    ```text
    error": null, "usage": {"input_tokens": 7108, "cache_creation_input_tokens": 0, "cache_read_input_to
    ```

    ```text
    kens": 0, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}, "outpu
    ```

    ```text
    t_tokens": 0, "service_tier": "standard", "inference_geo": "global"}, "type": "AssistantMessage"}
    ```

    ```text
    event: message
    data: {"content": [{"text": "Sure! Here's a summary of our conversation so far:\n\n-
    ```

    ```text
    --\n\n### \ud83d\uddc2\ufe0f Conversation Summary\n\n**1. Top 3 AI Agent Trends (May 2026)**\nYou as
    ```

    ```text
    ked about the most interesting AI agent trends right now. Based on web research, the three highlight
    ```

    ```text
    ed were:\n\n- \ud83e\udd1d **Multi-Agent Systems & Orchestration** \u2014 Specialized agents working
    ```

    ```text
     in coordinated teams, replacing single all-purpose agents. Gartner reported a 1,445% surge in multi
    ```

    ```text
    -agent system inquiries.\n- \ud83e\uddf1 **Context Engineering** \u2014 Designing the full informati
    ```

    ```text
    on architecture around an agent (memory, retrieval, data sources, token budgets) to ensure reliable,
    ```

    ```text
     high-quality outputs at scale.\n- \ud83d\udee1\ufe0f **Governance & Deterministic Guardrails** \u20
    ```

    ```text
    14 Shifting from viewing governance as a compliance burden to an enabler, combining dynamic AI with
    ```

    ```text
    human oversight to safely deploy agents in high-stakes scenarios.\n\n---\n\n**2. Deep Dive into Cont
    ```

    ```text
    ext Engineering**\nYou asked for more detail on the second trend. Key takeaways included:\n\n- **Con
    ```

    ```text
    text Engineering \u2260 Prompt Engineering** \u2014 It's a broader discipline covering the entire in
    ```

    ```text
    formation lifecycle of an agent.\n- **Core techniques** include RAG, memory management, context comp
    ```

    ```text
    ression, context offloading, state persistence, and tool output structuring.\n- **Why it matters for
    ```

    ```text
     agents** \u2014 Unlike chatbots, agents accumulate context over many steps, making careful informat
    ```

    ```text
    ion design critical to avoid context rot and token blowouts.\n- **RAG alone isn't enough** \u2014 77
    ```

    ```text
    % of IT leaders agree RAG is insufficient for production AI on its own.\n- Proper context engineerin
    ```

    ```text
    g can improve agent task completion rates dramatically (e.g., **83% \u2192 96%**).\n\n---\n\nWould y
    ```

    ```text
    ou like to explore any of these topics further?"}], "model": "claude-sonnet-4-6", "parent_tool_use_i
    ```

    ```text
    d": null, "error": null, "usage": {"input_tokens": 7108, "cache_creation_input_tokens": 0, "cache_re
    ```

    ```text
    ad_input_tokens": 0, "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens":
    ```

    ```text
     0}, "output_tokens": 0, "service_tier": "standard", "inference_geo": "global"}, "type": "AssistantM
    ```

    ```text
    essage"}
    ```

    ```text
    event: message
    data: {"subtype": "success", "duration_ms": 8163, "duration_api_ms": 8025, "is_error
    ```

    ```text
    ": false, "num_turns": 1, "session_id": "77597263-a169-4236-b3d4-8ec14f90fd2b", "stop_reason": "end_
    ```

    ```text
    turn", "total_cost_usd": 0.028029, "usage": {"input_tokens": 7108, "cache_creation_input_tokens": 0,
    ```

    ```text
     "cache_read_input_tokens": 0, "output_tokens": 447, "server_tool_use": {"web_search_requests": 0, "
    ```

    ```text
    web_fetch_requests": 0}, "service_tier": "standard", "cache_creation": {"ephemeral_1h_input_tokens":
    ```

    ```text
     0, "ephemeral_5m_input_tokens": 0}, "inference_geo": "", "iterations": [{"input_tokens": 7108, "out
    ```

    ```text
    put_tokens": 447, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "cache_creation":
    ```

    ```text
    {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 0}, "type": "message"}], "speed": "sta
    ```

    ```text
    ndard"}, "result": "Sure! Here's a summary of our conversation so far:\n\n---\n\n### \ud83d\uddc2\uf
    ```

    ```text
    e0f Conversation Summary\n\n**1. Top 3 AI Agent Trends (May 2026)**\nYou asked about the most intere
    ```

    ```text
    sting AI agent trends right now. Based on web research, the three highlighted were:\n\n- \ud83e\udd1
    ```

    ```text
    d **Multi-Agent Systems & Orchestration** \u2014 Specialized agents working in coordinated teams, re
    ```

    ```text
    placing single all-purpose agents. Gartner reported a 1,445% surge in multi-agent system inquiries.\
    ```

    ```text
    n- \ud83e\uddf1 **Context Engineering** \u2014 Designing the full information architecture around an
    ```

    ```text
     agent (memory, retrieval, data sources, token budgets) to ensure reliable, high-quality outputs at
    ```

    ```text
    scale.\n- \ud83d\udee1\ufe0f **Governance & Deterministic Guardrails** \u2014 Shifting from viewing
    ```

    ```text
    governance as a compliance burden to an enabler, combining dynamic AI with human oversight to safely
    ```

    ```text
     deploy agents in high-stakes scenarios.\n\n---\n\n**2. Deep Dive into Context Engineering**\nYou as
    ```

    ```text
    ked for more detail on the second trend. Key takeaways included:\n\n- **Context Engineering \u2260 P
    ```

    ```text
    rompt Engineering** \u2014 It's a broader discipline covering the entire information lifecycle of an
    ```

    ```text
     agent.\n- **Core techniques** include RAG, memory management, context compression, context offloadi
    ```

    ```text
    ng, state persistence, and tool output structuring.\n- **Why it matters for agents** \u2014 Unlike c
    ```

    ```text
    hatbots, agents accumulate context over many steps, making careful information design critical to av
    ```

    ```text
    oid context rot and token blowouts.\n- **RAG alone isn't enough** \u2014 77% of IT leaders agree RAG
    ```

    ```text
     is insufficient for production AI on its own.\n- Proper context engineering can improve agent task
    ```

    ```text
    completion rates dramatically (e.g., **83% \u2192 96%**).\n\n---\n\nWould you like to explore any of
    ```

    ```text
     these topics further?", "structured_output": null, "type": "ResultMessage"}
    ```

    ```text
    event: done
    data:
    ```

```python
%%bash
# Teardown tier 1
cd hosting/docker && docker compose down
```

??? note "輸出"

    ```text
     Container docker-research-agent-1 Stopping
    ```

    ```text
     Container docker-research-agent-1 Stopped 
     Container docker-research-agent-1 Removing
    ```

    ```text
     Container docker-research-agent-1 Removed
    ```

    ```text
     Network docker_default Removing
    ```

    ```text
     Network docker_default Removed
    ```

---
## Tier 2：Modal，同一個 image，現在變成一個 URL

Tier 1 跑在你的機器上。Tier 2 透過 `modal.Sandbox` 在 [Modal](https://modal.com) 上跑**同一個 Dockerfile**，你會拿到公開的 HTTPS URL、scale-to-zero，而且不用管任何 server。

那個 URL 是*公開*的：任何拿到它的人都能花你的 API 預算。Tier 1 和 3 假設前面有一個做認證的 gateway，tier 2 沒有 gateway，所以 `modal_app.py` 會為每次部署產生一個 bearer token，並以 `AGENT_AUTH_TOKEN` 傳進去。`server.py` 只在設了這個環境變數時才檢查 token，所以其他層級不受影響。

[`hosting/modal/modal_app.py`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/hosting/modal/modal_app.py) 很短，因為 agent 完全沒變：

```python
app = modal.App.lookup("research-agent-hosting", create_if_missing=True)
image = modal.Image.from_dockerfile("hosting/Dockerfile", context_dir=".")
auth_token = secrets.token_urlsafe(32)
sandbox = modal.Sandbox.create(
    "serve",  # appended to the image's ENTRYPOINT, like compose's `command:`
    app=app,
    image=image,
    secrets=[
        modal.Secret.from_name("anthropic"),
        modal.Secret.from_dict({"AGENT_AUTH_TOKEN": auth_token}),
    ],
    volumes={"/data": sessions_volume},
    encrypted_ports=[8000],
)
print(sandbox.tunnels()[8000].url)
```

持久化用掛在 `/data` 的 `modal.Volume`，跟 tier 1 一樣用 `CLAUDE_CONFIG_DIR` 的做法。（如果你的工作負載有很多 sandbox 同時寫入，遇到 Volume commit 語意的問題，可以換成 [`SessionStore`](https://code.claude.com/docs/en/agent-sdk/session-storage)；tier 3 和正式環境也是用這個。）

一次性的設定，**要在你的終端機做**（`modal setup` 會開瀏覽器，所以不能在 notebook cell 裡跑）：

```bash
pip install modal
modal setup
```

然後建立 Modal 會注入成 `ANTHROPIC_API_KEY` 的 secret：

```python
%%bash
modal secret create anthropic ANTHROPIC_API_KEY="$(grep ANTHROPIC_API_KEY hosting/.env | cut -d= -f2)"
```

??? note "輸出"

    ```text
    Created a new secret 'anthropic' with the key 'ANTHROPIC_API_KEY'
    ```

    ```text

    Use it in your Modal app:
    ```

    ```text

    @app.[38;2;248;248;242;48;
    ```

    ```text
    2;39;40;34mfunction(secret
    ```

    ```text
    s=[[38;2;248;248;242;4
    ```

    ```text
    8;2;39;40;34mmodal.Secret[
    ```

    ```text
    0m.from_name[38;2;248;248;
    ```

    ```text
    242;48;2;39;40;34m("anthro
    ```

    ```text
    pic")[38;2;248;248;24
    ```

    ```text
    2;48;2;39;40;34m])
    ```

    ```text
    def [38;2;166;226;46;48;2
    ```

    ```text
    ;39;40;34msome_function()
    ```

    ```text
    [0m:
    ```

    ```text
                     
        os[
    ```

    ```text
    0m.getenv[38;2;248;248;242
    ```

    ```text
    ;48;2;39;40;34m("ANTHROPIC
    ```

    ```text
    _API_KEY")[48;2;39;40
    ```

    ```text
    ;34m
    ```

```python
%%bash
python hosting/modal/modal_app.py | tee /tmp/modal_deploy.out
MODAL_URL=$(awk '/^url:/ {print $2}' /tmp/modal_deploy.out)
MODAL_TOKEN=$(awk '/^token:/ {print $2}' /tmp/modal_deploy.out)
{ echo "MODAL_URL=$MODAL_URL"; echo "MODAL_TOKEN=$MODAL_TOKEN"; } > /tmp/modal_url.env
```

??? note "輸出"

    ```text
    sandbox: sb-7R7zQ7TtX0h9eKZ8qslvwo
    url:     https://ta-01ks91e217n9fymaxjtdc9k5bh-8000-kn9n102ljd7y4
    ```

    ```text
    majwav00kwg0.w.modal.host
    token:   sb-…redacted…

    ⚠️  The URL is p
    ```

    ```text
    ublic. The token is the only thing gating it — don't share both.

    Try it:
      curl -N -X POST https:
    ```

    ```text
    //ta-01ks91e217n9fymaxjtdc9k5bh-8000-kn9n102ljd7y4majwav00kwg0.w.modal.host/sessions/demo-1/messages
    ```

    ```text
     \
        -H 'Authorization: Bearer sb-…redacted…' \
        -H 'Content-Type
    ```

    ```text
    : application/json' \
        -d '{"prompt":"What are the latest AI agent trends?"}'
    ```

```python
%%bash
source /tmp/modal_url.env
curl -N -s -X POST "$MODAL_URL/sessions/demo-1/messages" \
  -H "Authorization: Bearer $MODAL_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Give me a one-sentence summary of the Claude Agent SDK."}'
```

??? note "輸出"

    ```text
    event: message
    data: {"subtype": "init", "data": {"type": "system", "subtype": "init", "cwd": "/app", "session_id": "1566ffe4-2b20-4a68-82ff-283984b64451", "tools": ["Task", "TaskOutput", "Bash", "Glob", "Grep", "ExitPlanMode", "Read", "Edit", "Write", "N … [truncated]

    event: message
    data: {"content": [{"id": "toolu_01PPS8yzMBzMnRhG2Hnpk5VL", "name": "WebSearch", "input": {"query": "Claude Agent SDK Anthropic 2026"}}], "model": "claude-sonnet-4-6", "parent_tool_use_id": null, "error": null, "usage": {"input_tokens": 120 … [truncated]

    [... 5 events omitted — thinking blocks, tool loading, and web-search result payloads ...]

    event: message
    data: {"content": [{"text": "The **Claude Agent SDK** is Anthropic's framework that gives developers programmatic access to the same tools, agent loop, and context management that power Claude Code \u2014 enabling the creation of AI agents that can autonomously read files, run commands, search the w … [truncated]

    event: message
    data: {"subtype": "success", "duration_ms": 12879, "duration_api_ms": 12871, "is_error": false, "num_turns": 3, "session_id": "1566ffe4-2b20-4a68-82ff-283984b64451", "stop_reason": "end_turn", "total_cost_usd": 0.045893199999999995, "usage" … [truncated]

    event: done
    data:
    ```

同樣的介面、同樣的 image、不同的 host。沒人呼叫時，Modal 會把 sandbox 縮到零，你不用付費。

清理一下，避免閒置資源被計費：

```python
%%bash
python hosting/modal/teardown.py
```

??? note "輸出"

    ```text
    terminating sandbox sb-7R7zQ7TtX0h9eKZ8qslvwo
    deleted volume research-agent-sessions
    ```

---
## Tier 3：Kubernetes，需要自己掌握基礎設施時

Tier 3 是給多租戶的正式環境、受管制環境，或任何需要完全控制網路、隔離和成本的地方。agent image 和介面仍然一模一樣，新增的是它*外圍*的機制：

- 前面有一個 **gateway**，負責認證呼叫端，只轉發它們擁有的 `session_id`。`server.py` 省略的 auth 終於在這裡處理。
- **每個 session 一個 pod** 的路由（gateway → Redis → pod），讓每段對話有自己的爆炸半徑。
- 預先暖機的 pod 組成的 **standby pool**，讓新 session 不用等 cold start。
- **出站封鎖**（NetworkPolicy 加上白名單 proxy），讓被 prompt injection 的 agent 只能連到 `api.anthropic.com`，其他都不行。

完整的 manifest、gateway 和逐步的架構說明在 [`hosting/kubernetes/`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/hosting/kubernetes)。它能在本機的 [kind](https://kind.sigs.k8s.io/) cluster 上從頭跑到尾，不需要雲端帳號：

```bash
cd hosting/kubernetes
ANTHROPIC_API_KEY=sk-ant-... ./kind-quickstart.sh
```

quickstart 會印出兩個示範租戶（`alice` 和 `bob`）的 bearer token。gateway 把每個 session 限定給建立它的租戶：跟 tier 1、2 一樣的 `curl -N POST /sessions/{id}/messages`，現在打到 `:8080` 的 gateway，帶 `Authorization: Bearer <alice-token>` header，對 alice 有效，同樣的請求換成 bob 的 token 就會收到 403。README 的 *Deploying to your own cluster* 一節說明真實 cluster 要改的 registry 和 ingress。

*Kubernetes 這一層建立在 Joe Shamon 和 Ben Lehrburger 的內部工作之上。*


---
## 準備好上正式環境

有兩個正式環境的問題，各用幾行就能接上。下面的 cell 示範程式碼，完整的正式環境檢查清單（auth、graceful shutdown、idle timeout 調校、autoscaling、成本控制）在 [hosting 文件](https://code.claude.com/docs/en/agent-sdk/hosting)。

### Observability

SDK 對每一輪和每個 tool 呼叫都會發出 OpenTelemetry span。用兩個環境變數指向你的 collector 即可，`server.py` 不用改任何程式碼（[文件](https://code.claude.com/docs/en/agent-sdk/observability)）：

```python
# In docker-compose.yml / modal_app.py / your k8s Deployment:
#   OTEL_EXPORTER_OTLP_ENDPOINT=http://your-collector:4317
#   OTEL_SERVICE_NAME=research-agent
```

### Liveness

`GET /health` 已經在 `server.py` 裡了。把你的 orchestrator 的 liveness probe 指向它（compose 的 `healthcheck:`、Modal health check、k8s `livenessProbe`）。

### 超越 volume 的持久化

`/data` volume mount 對單機和 Modal 來說夠用。多機的正式環境要用 [`SessionStore` adapter](https://code.claude.com/docs/en/agent-sdk/session-storage)，把紀錄鏡像到共用儲存（S3、Postgres、Redis）。注意 SessionStore 只是鏡像，本機磁碟一定會先寫，鏡像失敗會發出 `mirror_error`，但不會中斷 agent。

### Wire format
`server.py` 直接串流 SDK 的原始訊息型別。以 cookbook 來說沒問題，但正式的 API 應該定義一個穩定的 wire format，這樣 SDK 升版才不會弄壞 client。

---
## 選擇你的層級

| 層級 | 它給你什麼 | 什麼時候選 | 什麼時候往上升 |
|---|---|---|---|
| **1. Docker** | 一個跑在你控制的機器上的 container。Compose 負責重啟，bind mount 保留 `/data`。你要維運一台 Docker host。 | 開發迴圈、內部工具、單一租戶的 app、cron/批次工作。可以手動重啟，且你的網路外沒人會呼叫它。 | 這台機器外的人需要一個 URL，或「手動重啟」變得不可接受。 |
| **2. Modal** | 同一個 image 放在公開 HTTPS URL 後面，有 scale-to-zero 和遠端 build。你什麼都不用維運。 | 你今天就想要一個可呼叫的 endpoint，流量很突發或大部分時間是零，而且每次部署一個 bearer token 的 auth 就夠用。 | 你需要真正的多租戶隔離、網路層級的出站控制，或你的 platform 團隊要求工作負載跑在他們的 cluster 上。 |
| **3. Kubernetes** | 每個 session 一個 pod 的隔離、帶租戶範圍 session 的認證 gateway、出站封鎖和暖機的 standby pool。你要維運 cluster、gateway 和 Redis。 | 多租戶的正式環境、受管制環境，或你本來就在跑 Kubernetes，想讓 agent 跟其他一切用同一套營運模型。 | 這是這份 notebook 階梯的頂端，再往後是調校 autoscaling、多區域路由和持久的 session store，而不是遷移。 |

[hosting guide](https://code.claude.com/docs/en/agent-sdk/hosting) 的部署模式可以直接對應這些層級。**Ephemeral sessions**（模式 1：一個 prompt、一個 process、結束）就是 tier 1a：沒有 server，在任何 host 上從 cron 或 queue worker 跑 container。**Long-running** 和 **hybrid sessions**（模式 2 和 3，process 跨輪次持有或重建對話狀態）就是 `server.py` 用 `resume=` 加 `/data` volume 實作的，tier 1b、2 和 3 都是這個形狀，差別只在誰負責讓那個 process 活著、呼叫端怎麼連到它。**Single containers**（模式 4，很多 session 多工塞進一個 container）正是 tier 1b 和 2 在做的事，tier 3 則是在這樣不再可接受、每個 session 需要自己的爆炸半徑時才出場。


---
## 附錄：移植到其他供應商

同一個 `hosting/Dockerfile`，部署指令不同。每個都開放 port 8000 並給你一個 URL，要持久化的話在 `/data` 掛點東西。

**Fly Machines**
```bash
fly launch --dockerfile hosting/Dockerfile --no-deploy  # run from claude_agent_sdk/
fly volumes create data --size 1
fly deploy
```

**E2B**
```python
from e2b import Sandbox
sbx = Sandbox(template="research-agent")  # template built from hosting/Dockerfile
sbx.commands.run("./hosting/entrypoint.sh serve", background=True)
url = sbx.get_host(8000)
```

**Daytona**
```python
from daytona import Daytona, CreateSandboxFromImageParams
sbx = Daytona().create(CreateSandboxFromImageParams(image="research-agent"))
sbx.process.exec("./hosting/entrypoint.sh serve")
```

**Cloudflare Containers**
```ts
// wrangler.toml points at hosting/Dockerfile
export class Agent extends Container { defaultPort = 8000 }
```

**Vercel Sandbox**
```ts
import { Sandbox } from "@vercel/sandbox";
const sbx = await Sandbox.create({ image: "research-agent", ports: [8000] });
await sbx.runCommand({ cmd: "./hosting/entrypoint.sh", args: ["serve"], detached: true });
```

## 重點整理

- Claude Agent SDK 的 agent 本身就是一個 process，隔離容易，但部署是分散式系統問題。
- 任何層級都要做四件事：啟動、路由、生命週期、持久化 session。三個層級只是把這四件事交給不同的東西。
- agent 程式碼、image 和 HTTP 介面不變，選 host 是部署決策，不是重寫。
- `server.py` 刻意不做 auth 也只開 `WebSearch`，認證放 gateway，並把 prompt injection 能碰到的東西降到最低。
- 一次性任務用 tier 1a 就夠；要持續對話靠 `resume=` 加持久化的 `/data`；要多租戶隔離才上 Kubernetes。

## 練習

1. 照 Tier 1a 跑一次，把 `$PROMPT` 換成另一個研究題目，確認 container 印出結果後以 exit code 0 結束。
2. 在 Tier 1b，對同一個 `session_id` 送兩輪訊息，然後重啟 container 再送第三輪，確認 agent 還記得前面的內容，再試著不掛 `./sessions` volume，看看會發生什麼。
3. 在 `hosting/.env` 設 OpenTelemetry 的環境變數指向本機的 collector，看每一輪和每個 tool 呼叫的 span。
