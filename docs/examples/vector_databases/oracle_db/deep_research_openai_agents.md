---
translated: true
source: examples/vector_databases/oracle_db/deep_research_openai_agents.ipynb
---
# 用 Oracle AI Agent Memory 打造 Agent 的長期記憶

> 原文：[examples/vector_databases/oracle_db/deep_research_openai_agents.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/oracle_db/deep_research_openai_agents.ipynb)

用 OpenAI Agents SDK 建一個 deep-research agent，搭配 Oracle 做 session 持久化、長期記憶，並用 Tavily 做網路搜尋。

## 這篇在做什麼

自己實作 Agents SDK 的 `Session` 協定，把短期的對話紀錄存進 Oracle AI Database，再另外用 tool 把研究結論存成長期記憶。範例是一個人類基因組的 deep-research agent，用 Tavily 查網路，並驗證新 session 也能想起之前存下的發現。

## 學完你會

- 對自訂後端（Oracle AI Agent Memory）實作 Agents SDK 的 `Session` 協定。
- 把 Tavily 包成 `function_tool`，再加上 `save_research_finding` 和 `recall_research_findings` 兩個記憶 tool。
- 用新的 `session_id` 驗證 agent 能接續前一次研究，而不是靠舊的對話紀錄。

## 開跑前

- 需要一個跑得到的 Oracle AI Database（本機 Docker 或遠端）。
- 需要 `OPENAI_API_KEY` 和 `TAVILY_API_KEY`（Tavily 有免費額度）。
- 用 Colab 的話，Oracle 資料庫要能從 Colab 連得到，Colab 連不到你筆電上的 `localhost`。

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/oracle_db/deep_research_openai_agents.ipynb) [![Documentation](https://img.shields.io/badge/Documentation-Oracle%20AI%20Agent%20Memory-red?style=flat-square)](https://www.oracle.com/database/ai-agent-memory/)

**框架：** OpenAI Agents SDK | **網路搜尋：** Tavily | **記憶：** Oracle AI Database 上的 Oracle AI Agent Memory

長時間運作的 agent 工作流程，需要的不只是短期的對話重播。它們要能跨 session 記住持久的發現、決定和可重用的 context，這樣 agent 才能從之前的成果繼續，不用每次從頭開始。

這個 notebook 示範的是 **OpenAI Agents SDK 的 Oracle 後端 Session 模式**，它不是通用的 OpenAI 記憶實作。Agents SDK 的 `Session` 介面存的是目前 agent 迴圈的短期對話歷史，持久的研究發現則另外透過明確的記憶 tool 存進 Oracle AI Agent Memory。

範例用一個探索人類基因組的 **deep research agent**，但核心模式更廣：把 OpenAI Agents SDK 的 session 持久化，和一個存放可重用發現的長期記憶層結合。agent 用 Tavily 做即時的網路研究，把 OpenAI Agents SDK 的 session items 存在 Oracle AI Database，並透過專用的 `save_research_finding` tool 存下持久的發現。

## 為什麼長期記憶重要

短期的 session 記憶幫 agent 維持當前對話的連貫。長期記憶解決的是另一個問題：讓 agent 跨 session 保留挑選過的發現、接續之前的工作，避免重新找一遍已經研究過的事實。

在這個範例裡，session items 和持久的發現有不同的生命週期。Session items 是原始的對話狀態，用來在 agent 迴圈裡重播。持久的發現是經過整理、可搜尋的結論，由 agent 刻意透過 tool 存下來。

如果應用已經跑在 Oracle AI Database 上，又需要受治理的持久記憶、對已存發現做語意搜尋，以及在同一個資料庫底層對短期 session 重播和長期記憶做範圍控管，Oracle AI Agent Memory 就適合這個模式。

---

## Agent 應用的運作模式

AI agent 應用大致分成三種運作模式：

| 模式 | 形式 | 典型用途 |
|---|---|---|
| **Assistant** | 一來一往的對話 | 客服、coding copilot、聊天介面 |
| **Deep Research** | 多步驟的自主調查 | 文獻回顧、市場研究、技術範圍評估 |
| **Workflow** | 預先決定好的步驟順序，常帶條件分支 | 簽核流程、合規檢查、結構化分流 |

> **注意：** 這個 notebook 聚焦在 Deep Research 模式。
>
> deep-research agent 會在長時間的調查中規劃、檢索、整合並累積發現。記憶是核心，但不是所有記憶的生命週期都一樣：session items 支援短期的連續性，持久的發現則是 agent 可以跨 session 重用、經過整理的事實。


## 你會學到

- 如何針對自訂後端（Oracle AI Agent Memory）實作 **OpenAI Agents SDK 的 `Session` 協定**
- 如何把 **Tavily** 包成 agent 可呼叫的 `function_tool`
- 如何把長期的研究發現存成持久的 **memory**（和短期對話歷史分開）
- 如何驗證跨 session 的記憶連續性，也就是 agent 能從上次中斷的地方接著做

> **💡 重點：** 短期記憶（當次執行的對話歷史）和長期記憶（跨次執行的持久發現）是對同一個儲存區的不同存取模式。前者用 `Session`，後者用 `add_memory()`。

## 前置條件

- 這個 notebook 建議用 **Python 3.10 或 3.11**
- **Oracle AI Database** 在本機執行（Docker container）或可透過網路連到
- **`OPENAI_API_KEY`**，供 agent 的 LLM 和 embeddings 使用
- **`TAVILY_API_KEY`**，供網路搜尋使用（[tavily.com](https://tavily.com) 有免費額度）
- 目前 kernel 環境裡已安裝 `oracleagentmemory`、`litellm`、`openai-agents`、`tavily-python`、`python-dotenv` 和 `nest_asyncio`

如果在 Colab 跑這個 notebook，Oracle 資料庫必須能從 Colab 的 runtime 連到。Colab 沒辦法用 `localhost` 連到你筆電上的 Docker 資料庫，要嘛把資料庫開放到可連到的主機或網路路徑，要嘛在本機、跟 Docker container 同一台機器上跑 notebook。

本機的 Oracle Database Free Docker container 如果有開放 `1521` 埠，DSN 通常長得像 `localhost:1521/FREEPDB1`。如果你的 container 把 Oracle listener 對應到別的主機埠，`ORACLE_DSN` 就要用那個主機埠。執行連線 cell 之前，先等 container 回報 `DATABASE IS READY TO USE!`。

在 notebook 旁建一個 `.env` 檔，或在 shell 設定這些變數：

```env
OPENAI_API_KEY=
TAVILY_API_KEY=
ORACLE_USER=
ORACLE_PASSWORD=
ORACLE_DSN=
# Optional: set OPENAI_MODEL to use a different OpenAI model
# OPENAI_MODEL=
```

這個 notebook 也接受舊的別名 `DB_USER`、`DB_PASSWORD` 和 `DB_CONNECT_STRING`，不過建議用上面 Oracle 風格的名稱。


## 1. 安裝相依套件

安裝 notebook 需要的套件：`oracleagentmemory` 用於 Oracle 後端的記憶，`litellm` 是 Oracle AI Agent Memory 做 embedding 時用的路徑，`openai-agents` 是 Agents SDK 的 runtime，`tavily-python` 用於網路搜尋，`python-dotenv` 用於環境變數，`nest_asyncio` 則讓 `Runner.run` 能在 Jupyter 的 event loop 裡正常運作。

相依性的分界：`openai-agents` 提供 Agents SDK 的 runtime 和 session 協定，`litellm` 則由 Oracle AI Agent Memory 用來對持久的發現做 embedding 和語意搜尋。單純實作 Agents SDK 的 session，並不需要 Oracle 的長期記憶這條路徑。


```python
%%capture
%pip install -q oracleagentmemory litellm openai-agents tavily-python nest_asyncio python-dotenv
```

## 2. 設定 API key 和 Oracle 連線

從 `.env` 或環境變數載入設定。這個 notebook 刻意**不**提供預設的帳密，缺少必要的值時會提示你輸入，而不是把機密寫進 notebook。

必要的值：

- `OPENAI_API_KEY`
- `TAVILY_API_KEY`
- `ORACLE_USER` 或 `DB_USER`
- `ORACLE_PASSWORD` 或 `DB_PASSWORD`
- `ORACLE_DSN` 或 `DB_CONNECT_STRING`

```python
import os
import getpass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the current working directory or notebook directory.
load_dotenv()
load_dotenv(Path.cwd() / ".env")


def _read_setting(primary: str, *aliases: str, secret: bool = False) -> str:
    """Read a required setting from env vars, falling back to a notebook prompt."""
    for key in (primary, *aliases):
        value = os.getenv(key)
        if value:
            os.environ[primary] = value
            return value

    prompt = f"Enter {primary}: "
    value = getpass.getpass(prompt) if secret else input(prompt)
    if not value:
        raise RuntimeError(f"Missing required setting: {primary}")
    os.environ[primary] = value
    return value


OPENAI_API_KEY = _read_setting("OPENAI_API_KEY", secret=True)
TAVILY_API_KEY = _read_setting("TAVILY_API_KEY", secret=True)
DB_USER = _read_setting("DB_USER", "ORACLE_USER")
DB_PASSWORD = _read_setting("DB_PASSWORD", "ORACLE_PASSWORD", secret=True)
DB_CONNECT_STRING = _read_setting("DB_CONNECT_STRING", "ORACLE_DSN")
MODEL = os.getenv("OPENAI_MODEL") or "gpt-5.4"

# Keep later cells consistent if a notebook user updates these Python variables directly.
os.environ.update({
    "OPENAI_API_KEY": OPENAI_API_KEY,
    "TAVILY_API_KEY": TAVILY_API_KEY,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
    "DB_CONNECT_STRING": DB_CONNECT_STRING,
})

# Jupyter runs an async event loop already; this lets us call async SDK methods cleanly.
import nest_asyncio
nest_asyncio.apply()

print("Configuration loaded from environment variables or prompts.")
print("OpenAI model configured.")
```

??? note "輸出"

    ```text
    Configuration loaded from environment variables or prompts.
    OpenAI model configured.
    ```

## 3. 連到 Oracle AI Database 並初始化 memory client

`OracleAgentMemory` 是受治理的記憶 client。這個 notebook 把自動擷取關掉，讓兩者的區隔很明確：

- **Session items** 是 OpenAI Agents SDK 的短期對話狀態，用來重播。
- **Research findings** 是持久的記憶，只透過 `save_research_finding` tool 寫入。

我們用 `text-embedding-3-small` 對持久的發現做語意搜尋。

> **💡 重點：** `schema_policy` 控制函式庫啟動時怎麼操作資料庫。`REQUIRE_EXISTING` 絕不下 DDL。`CREATE_IF_NECESSARY` 會補上缺少的物件，對 demo 和開發比較安全。`RECREATE` 會刪掉重建物件，在共用的 schema 裡不該當預設值。

```python
import oracledb
from oracleagentmemory.core import OracleAgentMemory
from oracleagentmemory.core.dbschemapolicy import SchemaPolicy

connection = oracledb.connect(
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"],
    dsn=os.environ["DB_CONNECT_STRING"],
)
print("Connected to Oracle AI Database.")

memory_client = OracleAgentMemory(
    connection=connection,
    embedder="text-embedding-3-small",   # OpenAI-compatible; 1536 dims
    extract_memories=False,               # durable findings are saved explicitly via tool calls
    schema_policy=SchemaPolicy.CREATE_IF_NECESSARY,
    table_name_prefix="genome_",         # isolates this example's tables from others
)
print("Memory client ready with safe schema policy:", SchemaPolicy.CREATE_IF_NECESSARY.value)
```

??? note "輸出"

    ```text
    Connected to Oracle AI Database.
    Memory client ready with safe schema policy: create_if_necessary
    ```

## 4. 註冊研究用的 user 和 agent

用獨一無二的執行範圍（run scope），這樣重跑 notebook 時，舊的 demo 記憶就不會和目前這次混在一起。這讓 `CREATE_IF_NECESSARY` 保持安全，也避免讀到前幾次執行留下來的過時長期發現。

```python
from datetime import datetime, timezone

RUN_ID = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
USER_ID = f"genome-researcher-{RUN_ID}"
AGENT_ID = f"deep-research-agent-{RUN_ID}"

for create_fn, eid, info in [
    (memory_client.add_user, USER_ID, "Genomics researcher exploring human disease associations."),
    (memory_client.add_agent, AGENT_ID, "Deep-research agent with web search and long-term memory."),
]:
    try:
        create_fn(eid, info)
        print(f"Registered: {eid}")
    except ValueError:
        print(f"Already exists: {eid}")

print(f"Run scope: {RUN_ID}")
```

??? note "輸出"

    ```text
    Registered: genome-researcher-20260715083601
    Registered: deep-research-agent-20260715083601
    Run scope: 20260715083601
    ```

## 5. 在 Oracle AI Agent Memory 上實作 `Session` 協定

OpenAI Agents SDK 的 `Session` 協定處理的是**短期的 session 持久化**：runner 會取回之前的 items，並在 agent 迴圈中附加新的 items。

在這個實作裡，session items 以 Oracle Agent Memory 的 `message` 記錄儲存，帶 `metadata={"session_item": true}`。它們依 `session_id`、`user_id` 和 `agent_id` 分範圍，只用來重播對話。持久的長期發現則透過 `save_research_finding` tool，另外存成 `memory` 記錄。

> **重要：** 原始的模型和 tool 訊息可能很大又很雜，除非 tool 刻意把簡潔的結論提升上去，否則它們不該出現在長期的研究發現裡。

```python
import json
from typing import Optional
from agents.memory.session import SessionABC


class OracleAgentMemorySession(SessionABC):
    """Session backend that persists OpenAI Agents SDK items in Oracle AI Database.

    Session items are short-term replay state stored as message records. Durable
    research findings are saved separately via the save_research_finding tool.
    """

    def __init__(self, session_id: str, client: OracleAgentMemory, user_id: str, agent_id: str):
        self.session_id = session_id
        self._client = client
        self._store = client._store
        self._user_id = user_id
        self._agent_id = agent_id
        try:
            self._client.create_thread(
                thread_id=session_id,
                user_id=user_id,
                agent_id=agent_id,
                extract_memories=False,
            )
        except ValueError:
            pass  # thread already exists
        self._next_session_seq = self._load_next_session_seq()

    async def get_items(self, limit: Optional[int] = None) -> list:
        records = self._session_records()
        ordered = sorted(records, key=self._session_sort_key)
        if limit:
            ordered = ordered[-limit:]
        return [json.loads(r.content) for r in ordered]

    async def add_items(self, items: list) -> None:
        if not items:
            return
        start_seq = self._next_session_seq
        metadata = [
            {
                "session_item": True,
                "session_id": self.session_id,
                "session_seq": start_seq + offset,
            }
            for offset, _ in enumerate(items)
        ]
        self._store.add(
            contents=[json.dumps(item) for item in items],
            record_type="message",
            thread_ids=self.session_id,
            user_ids=self._user_id,
            agent_ids=self._agent_id,
            roles=[self._message_role(item) for item in items],
            metadata=metadata,
        )
        self._next_session_seq = start_seq + len(items)

    async def pop_item(self) -> Optional[dict]:
        records = self._session_records()
        if not records:
            return None
        last = max(records, key=self._session_sort_key)
        self._store.delete("message", last.id)
        return json.loads(last.content)

    async def clear_session(self) -> None:
        records = self._session_records()
        for r in records:
            self._store.delete("message", r.id)
        self._next_session_seq = 0

    def _session_records(self) -> list:
        return self._store.list(
            "message",
            thread_id=self.session_id,
            user_id=self._user_id,
            agent_id=self._agent_id,
            limit=10_000,
            metadata_filter={"session_item": True},
        )

    def _load_next_session_seq(self) -> int:
        seqs = [self._session_seq(r) for r in self._session_records()]
        seqs = [seq for seq in seqs if seq is not None]
        return max(seqs) + 1 if seqs else 0

    @staticmethod
    def _record_metadata(record) -> dict:
        metadata = getattr(record, "metadata", None) or {}
        if isinstance(metadata, str):
            try:
                return json.loads(metadata)
            except json.JSONDecodeError:
                return {}
        return metadata if isinstance(metadata, dict) else {}

    @classmethod
    def _session_seq(cls, record) -> Optional[int]:
        seq = cls._record_metadata(record).get("session_seq")
        try:
            return int(seq)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _session_sort_key(cls, record) -> tuple:
        seq = cls._session_seq(record)
        if seq is not None:
            return (1, seq)
        # Fallback only covers records created before this notebook stored session_seq.
        created_at = getattr(record, "created_at", "") or ""
        return (0, str(created_at), str(getattr(record, "id", "")))

    @staticmethod
    def _message_role(item: dict) -> str:
        role = item.get("role") if isinstance(item, dict) else None
        if role in {"user", "assistant", "system", "tool"}:
            return role
        return "user"
```

## 6. 定義 agent 的 tool

這個 agent 需要三個 tool：

1. **`tavily_search`**：即時網路搜尋，找最新的基因體學來源
2. **`save_research_finding`**：保存一則持久的研究筆記，供 agent 在之後的 session 回想
3. **`recall_research_findings`**：在長期記憶裡搜尋某個主題之前的發現

第 2 和第 3 個 tool 是 agent 管理**長期**記憶的方式，它們和 `Session` 機制是分開的，`Session` 會自動處理短期的對話歷史。

> **📌 `@function_tool` decorator** 會從 Python 的型別提示自動產生 tool 的 JSON schema，並解析 docstring 當成 LLM 看到的描述。docstring 要寫清楚，因為 LLM 會讀。

```python
from agents import function_tool
from tavily import TavilyClient

_tavily = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

@function_tool
def tavily_search(query: str, max_results: int = 5) -> str:
    """Search the live web for recent, authoritative genomics sources.

    Use this to pull current information from NCBI, OMIM, peer-reviewed journals,
    and other scientific sources. Prefer this over relying on model-internal knowledge
    for facts about specific genes, mutations, or recent studies.

    Args:
        query: Natural-language search query.
        max_results: How many results to return (1-10).
    """
    resp = _tavily.search(
        query=query, max_results=max_results,
        search_depth="advanced", include_answer=True,
    )
    lines = [f"Answer: {resp.get('answer', '')}"]
    for r in resp.get("results", []):
        lines.append(f"- {r['title']} ({r['url']})\n  {r['content'][:300]}")
    return "\n".join(lines)


@function_tool
def save_research_finding(topic: str, finding: str) -> str:
    """Persist a durable research finding the agent should recall in future sessions.

    Use this for claims worth remembering across sessions, for example: "BRCA1
    pathogenic variants are associated with substantially elevated lifetime breast
    cancer risk." Do not use this for conversational acknowledgements, raw tool
    output, or speculation.

    Args:
        topic: Short topic tag (e.g. 'BRCA1', 'TP53 mutations').
        finding: The finding to remember, ideally one sentence.
    """
    memory_id = memory_client.add_memory(
        f"[{topic}] {finding}",
        user_id=USER_ID,
        agent_id=AGENT_ID,
        metadata={"topic": topic, "kind": "research_finding", "durable": True},
    )
    return f"Saved durable research finding (id={memory_id})."


@function_tool
def recall_research_findings(query: str, max_results: int = 5) -> str:
    """Search prior durable research findings for information relevant to a query.

    Use this at the start of a research task to check what is already known.
    Results are ranked by semantic similarity.

    Args:
        query: Natural-language query describing what you want to recall.
        max_results: How many findings to return.
    """
    results = memory_client.search(
        query,
        user_id=USER_ID,
        agent_id=AGENT_ID,
        exact_user_match=True,
        exact_agent_match=True,
        max_results=max_results,
        record_types=["memory"],
    )
    if not results:
        return "(no prior durable findings)"
    return "\n".join(
        f"- {r.content}  [distance={r.distance:.3f}]" for r in results
    )


print("Tools defined: tavily_search, save_research_finding, recall_research_findings")
```

??? note "輸出"

    ```text
    Tools defined: tavily_search, save_research_finding, recall_research_findings
    ```

## 7. 建立研究 agent

agent 的 `instructions` 就是它的 system prompt，你想要的行為就寫在這裡。對 deep-research agent 來說，instructions 應該強調：

1. **先回想再研究**：上網之前先查長期記憶
2. **引用來源**：讓發現可以追溯
3. **存下值得記住的東西**：明確地把持久的結論存下來

> **💡 重點：** deep-research agent 的輸出品質，很大程度取決於 instructions 有沒有分清楚*研究*（檢索加整合）和*對話*（回應加確認）。把這個區別寫進 system prompt。

```python
from agents import Agent, Runner

INSTRUCTIONS = """You are a deep-research agent specialising in human genome exploration.

For every research question:
1. FIRST call `recall_research_findings` to check what is already known from prior sessions.
2. If the prior findings are insufficient or outdated, call `tavily_search` for current sources.
3. Synthesise a clear, cited answer. Prefer authoritative sources (NCBI, OMIM, PubMed).
4. Call `save_research_finding` for each durable conclusion worth remembering across sessions.
   Save one finding per call; keep findings atomic and one sentence long.
5. Present the final answer to the user with inline citations (URLs).

Do not save conversational acknowledgements as findings. Only save factual conclusions.
"""

research_agent = Agent(
    name="GenomeDeepResearcher",
    instructions=INSTRUCTIONS,
    tools=[tavily_search, save_research_finding, recall_research_findings],
    model=MODEL,
)
print(f"Agent created: {research_agent.name}")
```

??? note "輸出"

    ```text
    Agent created: GenomeDeepResearcher
    ```

## 8. 執行一次研究 session

我們建立一個 session（綁定記憶儲存區裡的 `thread_id`），讓 agent 依序處理一連串研究問題。因為傳了 `session=session`，SDK 會在每一輪開始時自動帶入之前的對話 items，並在結束時保存新的 items。

> **📌 職責分離。**
> - `Session` 保存**原始對話**（工作記憶）。
> - agent 的 `save_research_finding` tool 保存**持久的發現**（長期記憶）。
> 兩者都放在同一個 Oracle 資料庫，但透過不同的介面存取。

因為這個範例用即時網路搜尋和模型生成，每次執行的措辭、引用和排序可能不同。要驗證的重點行為是：agent 在研究之前先回想持久的發現、引用來源，並透過記憶 tool 明確地存下新的發現。


```python
from IPython.display import Markdown, display


def _notebook_text(text: str) -> str:
    """Normalize model text so GitHub, VS Code, and terminals render it consistently."""
    return (
        text.replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


SESSION_ID = f"genome-session-{RUN_ID}-001"
session = OracleAgentMemorySession(
    session_id=SESSION_ID,
    client=memory_client,
    user_id=USER_ID,
    agent_id=AGENT_ID,
)

research_questions = [
    "What is BRCA1 and what is its primary function in DNA repair?",
    "What is the typical lifetime breast cancer risk associated with pathogenic BRCA1 variants?",
    "How does BRCA1 interact with BRCA2 in homologous recombination?",
]

session_sections = []
for i, q in enumerate(research_questions, 1):
    result = await Runner.run(research_agent, q, session=session)
    session_sections.append(f"### Q{i}: {q}\n\n{_notebook_text(result.final_output.strip())}")

display(Markdown("\n\n---\n\n".join(session_sections)))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 9. 檢查 agent 記住了什麼

到這裡，agent 已經累積了兩種不同的記錄：

- **短期 session items**：原始的 OpenAI Agents SDK items，用來重播目前 session 的對話。
- **持久的研究發現**：agent 刻意透過 `save_research_finding` 存下的簡潔結論。

兩份清單看起來應該不一樣。Session items 可能包含使用者訊息、tool call 和 tool 輸出。持久的發現則應該是簡短、事實性、可重用的研究筆記，不是原始的 `call_id` JSON 或完整的 tool 輸出。

```python
# Short-term: conversation items replayed each turn.
session_items = await session.get_items()

# Long-term: durable findings the agent deliberately chose to save.
findings = await memory_client.search_async(
    "BRCA1 function and risk",
    user_id=USER_ID,
    agent_id=AGENT_ID,
    exact_user_match=True,
    exact_agent_match=True,
    max_results=10,
    record_types=["memory"],
)


def _split_finding(content: str) -> tuple[str, str]:
    content = _notebook_text(str(content)).strip()
    if content.startswith("[") and "]" in content:
        topic, finding = content[1:].split("]", 1)
        return topic.strip(), finding.strip()
    return "Research finding", content


raw_json_leaks = [r for r in findings if str(r.content).lstrip().startswith("{")]
quality_note = (
    "Clean saved memories only; raw tool or session JSON was not saved."
    if not raw_json_leaks
    else "Review needed: raw tool or session JSON was saved."
)

summary = (
    "### Memory inspection\n\n"
    f"- Short-term session items stored: `{len(session_items)}`\n"
    f"- Durable research findings saved: `{len(findings)}`\n"
    f"- Stored content quality: {quality_note}\n"
)

rows = ["| Topic | Saved finding |", "|---|---|"]
for record in findings:
    topic, finding = _split_finding(record.content)
    rows.append(f"| {topic} | {finding} |")

display(Markdown(summary + "\n" + "\n".join(rows)))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 10. 驗證連續性：用同一個記憶儲存區開新的 session

判斷有記憶的 agent 好不好，真正的測試是它能不能從上次中斷的地方接著做。我們建一個*新的* session（模擬另一個程序或隔天），問一個建立在之前持久發現上的問題。

如果 agent 不靠上次的 session 逐字稿，就能想起前一次執行的 BRCA1 發現，就證明了端到端的持久記憶連續性。

這是教育性的基因體學範例，不是醫療建議。後續問題是請 agent 摘要有指引依據的討論主題並附上引用，不是提供針對特定病人的臨床建議。


```python
# Simulate a fresh session (new session_id, but same run-scoped user/agent).
FRESH_SESSION_ID = f"genome-session-{RUN_ID}-002"
fresh_session = OracleAgentMemorySession(
    session_id=FRESH_SESSION_ID,
    client=memory_client,
    user_id=USER_ID,
    agent_id=AGENT_ID,
)

followup = (
    "Based on the saved BRCA1 findings, list exactly three concise, "
    "guideline-backed topics a clinician might discuss when explaining "
    "screening considerations for pathogenic BRCA1 variants. Keep this "
    "educational, not patient-specific medical advice. Use plain ASCII "
    "punctuation. Include concise inline URL citations for any sources you mention."
)

result = await Runner.run(research_agent, followup, session=fresh_session)
answer = _notebook_text(result.final_output.strip())
display(
    Markdown(
        "### Fresh session follow-up\n\n"
        f"**Question:** {_notebook_text(followup)}\n\n"
        f"{answer}"
    )
)
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

## 11. 清理（選用）

清理的程式碼刻意被註解掉。只有在你想把目前這次執行的 session items 和持久發現從 demo schema 移除時，才取消註解。

前面的設定用的是 `CREATE_IF_NECESSARY`，所以重跑 notebook 預設不會把 schema 刪掉重建。每次執行都用獨一無二的 `RUN_ID`，避免目前的結果和過時的 demo 記憶混在一起。

```python
# await session.clear_session()
# await fresh_session.clear_session()
# for r in await memory_client.search_async("BRCA", user_id=USER_ID, agent_id=AGENT_ID, exact_user_match=True, exact_agent_match=True, max_results=100, record_types=["memory"]):
#     memory_client.delete_memory(r.record.id)
# print("Cleaned up current run.")

connection.close()
print("Connection closed.")
```

??? note "輸出"

    ```text
    Connection closed.
    ```

## 重點回顧

> **🎯 1. `Session` 協定是乾淨的整合點。** 四個 async 方法（`get_items`、`add_items`、`pop_item`、`clear_session`）就足以讓 OpenAI Agents SDK 接上自訂的 session 後端。你不用改 runner，只要實作協定，再用 `session=` 傳入實例。

> **🎯 2. Session 持久化不等於長期記憶。** Session 處理的是當前 agent 迴圈的短期對話重播。持久的發現應該是透過明確 tool 寫入的簡潔結論，不是把原始對話或 tool 輸出整包倒進長期記憶。

> **🎯 3. Instructions 決定記憶怎麼被使用。** deep-research agent 必須被明確告知要*先回想再研究*並*存下持久的結論*。否則 LLM 會把記憶當成可有可無的裝飾，儲存區就會被低價值的內容塞滿。

> **🎯 4. 使用安全的 schema 預設值。** 對 demo 和開發來說，`CREATE_IF_NECESSARY` 比破壞性的重建策略安全。破壞性的 schema 重置只留給獨立的 demo schema。

> **🎯 5. Oracle AI Database 讓兩個層級共用一個受治理的底層。** 短期 session items 和持久發現可以放在同一個後端，同時維持各自的記錄類型和不同的生命週期。

> **🎯 6. 連續性是可以測試的。** 用新的 `session_id`、同樣的 `user_id` 和 `agent_id`，應該能得到一個會根據先前持久發現推論的 agent。這是測有記憶 agent 最簡單的端到端測試。

## 重點整理

- 短期記憶（`Session`，重播對話）和長期記憶（持久的發現）生命週期不同，要分開存、分開存取。
- 實作 `Session` 只要四個 async 方法，不用動 runner。
- 持久記憶要由 tool 明確寫入簡潔的結論，不要把原始 tool 輸出倒進去。
- Instructions 要寫明「先回想再研究、引用來源、存下結論」，agent 才會真的用記憶。
- 用新的 `session_id` 搭配同樣的 user 和 agent，就能測記憶的連續性。

## 練習

1. 把 agent 的研究問題從 BRCA1 換成別的基因，重跑並用「檢查 agent 記住了什麼」那一節比較兩種記錄的內容。
2. 修改 agent 的 `instructions`，拿掉「先回想再研究」那一點，看看新 session 還會不會用到之前的發現。
3. 仿照 `save_research_finding` 再加一個 tool（例如依主題刪除某則發現），並把它加進 agent 的 tools 清單。
