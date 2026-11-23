---
translated: true
source: managed_agents/CMA_with_mongodb_atlas.ipynb
---
# 用 MongoDB Atlas 和 Claude Managed Agents 做詐欺審查 agent

> 原文：[managed_agents/CMA_with_mongodb_atlas.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_with_mongodb_atlas.ipynb)

把 MongoDB Atlas 接到 Claude Managed Agent 上，當作它的檢索引擎、graph store 和 system of record。內容包含三種不外洩憑證的連接方式、四種可以直接搬走用的檢索模式（vector、full-text、reciprocal rank fusion、$graphLookup），以及一個有人工把關的詐欺審查 agent，它把決策和 append-only 稽核紀錄寫進同一個 cluster。

## 這篇在做什麼

在 Claude Managed Agents（CMA）上跑一個審查可疑交易的 agent，資料全放在 MongoDB Atlas：用四種檢索方式找證據，高風險案例暫停等人工決定，最後把決策和稽核紀錄寫回同一個 cluster。重點是 MongoDB 憑證永遠留在你這邊，不會進到 agent 的 context 或 sandbox。

## 學完你會

- 用 host-side custom tool 把 MongoDB 接進 Managed Agent，憑證不外洩
- 把 vector、full-text、hybrid、graph 四種檢索寫成 agent 可呼叫的 tool
- 用 CMA 原生的 `requires_action` 讓風險決策等人工確認，並把決策與稽核紀錄寫進 MongoDB

## 開跑前

- 需要 `MONGO_URI`（Atlas 的 SRV 連線字串）和 Anthropic API 存取。免費的 M0 cluster 就能跑完全部內容。
- 選配：`MDB_ATLAS_API_KEY` 或 `VOYAGE_API_KEY`，用來啟用即時 embedding 和 rerank；沒設也能跑，因為 seed 資料已附預先算好的 embedding。
- 在 Colab 上把這些變數放進 Secrets，再用 `userdata.get` 讀進環境變數即可。

這本 cookbook 示範怎麼把 **MongoDB Atlas** 接到跑在
[Claude Managed Agents](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/README.md)（CMA）上的 agent，讓它當檢索引擎、graph store 和 system of record。只用標準的 CMA 模式（custom tool 和 MCP toolset），
**不需要平台層級的 MongoDB 整合**。可執行的輔助程式放在這本 notebook 旁邊的 [`mongodb_on_cma/`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma)。每一節都連到完整檔案，讓正文專注在 *MongoDB 接在哪裡* 和 *agent 帶來什麼價值*。

**MongoDB 接在哪裡：** 多數 agent 架構會拼湊三四個系統：做語意搜尋的 vector database、另一個做關鍵字的引擎、一個管關係的 graph store，還有存紀錄本身的 operational database。每個接縫都是多一次整合、多一組憑證、多一個 agent 對世界的認知可能出現落差的地方。MongoDB 把這些收成一個引擎：同一批文件可以用 **vector**（`$vectorSearch`）搜、用 **full-text**（`$search`）搜、用 reciprocal rank fusion（RRF，`$rankFusion`）把兩者混合成 **hybrid**，也能當 **graph**（`$graphLookup`）走訪，而且就是 agent 讀、寫、存決策的那批文件。一種查詢語言、一個 cluster、一條連線（`pymongo`）。

**Agent 帶來什麼價值：** CMA 在 Anthropic 那邊跑 agent loop 和 sandbox，你的應用程式掌握通往 MongoDB 的**資料路徑**。Agent 針對 MongoDB 檢索回來的內容推理，遇到高風險的判斷就透過 CMA 原生的 `requires_action` 閘門暫停等人，再把結論寫回去，整個過程資料庫憑證都不會進到 agent 的 context 或 sandbox。

> 這裡的 MongoDB 是你的**營運資料庫和檢索引擎**，是由你的應用程式控制的 system of record。這跟 CMA 在平台上原生管理的 memory 功能是兩回事，兩者可以互補。

**讀完你會能：**

- 用三種方式把不外洩憑證的 MongoDB Atlas 資料路徑接進 Claude Managed Agent。
- 把 vector、full-text、hybrid、graph 檢索搬進 agent 的 custom tool。
- 把風險高的 agent 決策擋在 CMA 原生的 human-in-the-loop 暫停後面。
- 讓一個 MongoDB Atlas cluster 同時當 agent 的 system of record 和稽核骨幹。

範例是一個**有人工把關的詐欺審查 agent**，但這些模式跟產業無關：換掉 collection 和 tool，同樣的形狀就能用在客服、研究或營運 agent。

## 本篇內容

1. [把 MongoDB 接到 managed agent](#1-connect-mongodb-to-a-managed-agent)
2. [檢索：四種模式，一個引擎](#2-retrieve-four-patterns-one-engine)
3. [端到端 agent：有人工把關的詐欺審查](#3-the-end-to-end-agent-human-in-the-loop-fraud-review)
4. [MongoDB Atlas 當 system of record 和稽核骨幹](#4-mongodb-atlas-as-the-system-of-record-and-audit-backbone)
5. [回顧](#5-recap)

```python
%%capture
# Third-party dependencies: the Anthropic SDK (drives Claude Managed Agents via client.beta.*),
# pymongo (the host-side data path), python-dotenv, and cryptography + pyjwt (sign/verify the
# AP2 mandates). This installs the PyPI packages only — the notebook also imports the adjacent
# `mongodb_on_cma/` package and `utilities.py`, so run it from a clone of this repo (see Setup).
%pip install -q "anthropic>=2.0.0" pymongo python-dotenv cryptography pyjwt
```

## 前置條件

**需要的知識：** Python 和 `pymongo` 基礎，加上對 Claude API 有點概念。剛接觸 MongoDB + Claude？
[library-RAG notebook](../third_party/MongoDB/rag_using_mongodb.md) 先從 `$vectorSearch` 講起。剛接觸 custom tool 閘門？
[`CMA_gate_human_in_the_loop.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_gate_human_in_the_loop.ipynb) 會教一次完整的來回流程。

**需要的工具：** Python 3.11+、[Anthropic API key](https://console.anthropic.com)，以及一個 MongoDB Atlas cluster。

## 設定

**必要：** `MONGO_URI`（Atlas 的 SRV 連線字串）加上 Anthropic API 存取。**免費的 M0 cluster 就能跑完這本 cookbook 的全部內容**，包含 vector、full-text、hybrid `$rankFusion` 和 graph 走訪，所以不需要付費方案。Hybrid 搜尋用原生的 `$rankFusion` stage，需要 MongoDB 8.0 以上；目前所有 Atlas cluster（包含 M0）都是 8.0 以上，預設就滿足。

```bash
uv sync --all-extras   # from the repo root
cp .env.example .env    # then add MONGO_URI (and Anthropic auth, if not already configured)
```

**選配的 embedding/rerank 供應商：** Seed 資料附了預先算好的 embedding，所以不用供應商也能跑。要啟用即時 embedding 和 reranker，請設定 `MDB_ATLAS_API_KEY`（MongoDB Atlas AI endpoint，同時提供 `/v1/embeddings` 和 `/v1/rerank`）或 `VOYAGE_API_KEY`（`voyageai` SDK）**其中一個**。`ENABLE_RERANK=1` 會加上 reranker 作為第二階段。`AUTO_APPROVE=1` 會讓人工閘門以固定結果自動處理，方便 CI。`COOKBOOK_MODEL` 可以覆蓋 agent 的模型（預設 `claude-haiku-5-5`）。

**還沒有 Atlas cluster？** 搭配的 notebook [`rag_using_mongodb.ipynb`](../third_party/MongoDB/rag_using_mongodb.md) 會帶你建立免費 cluster 並取得 `MONGO_URI`；索引設定可以看 [Atlas Search index 文件](https://www.mongodb.com/docs/atlas/atlas-search/create-index/)。

教學用的程式碼**直接寫在這本 notebook 裡**：四個檢索 pipeline builder（第 2 節）、custom tool 的 handler，以及 `requires_action` 閘門迴圈（第 3 節）。Notebook 旁邊的 [`mongodb_on_cma/`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma) 套件只放你 import 就好、不用讀的設定樣板：[`config.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/config.py)（索引名稱和可調參數）、
[`embeddings.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/embeddings.py)（Atlas/Voyage client）、
[`tools.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/tools.py)（Atlas seed/索引設定，以及共用的決策/稽核文件整形函式）、[`ap2_mandates.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/ap2_mandates.py)（AP2 簽章/驗證，是個密碼學黑盒，透過 `verify_mandates` 呼叫），以及
[`seed.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/seed.py)（範例資料載入器）。Import 它們、連上 client，並決定這次執行的設定。

```python
import hashlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import dotenv
from anthropic import Anthropic
from mongodb_on_cma import (
    EMBED_DIM,
    build_audit_event,
    build_decision_doc,
    ensure_indexes,
    has_anthropic_auth,
    load_seed,
    make_embedding_client,
    missing_required_env,
    preflight,
    prepare_seed,
    rerank,
    resolve_model,
    seed_collection,
    server_version,
    supports_rank_fusion,
)
from mongodb_on_cma.ap2_mandates import (
    attach_mandates,
    store_mandate_receipt,
    tool_verify_mandates,
)
from pymongo import MongoClient
from utilities import wait_for_idle_status

dotenv.load_dotenv()

missing = missing_required_env()
assert not missing, f"Set these in your environment / .env: {missing}"
# Anthropic auth is a soft check: an API key, an auth token, or a profile (e.g. the `ant`
# CLI's workload-identity federation) all work, so warn rather than block if none is set.
if not has_anthropic_auth():
    print(
        "warning: no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_PROFILE found; "
        "relying on the SDK / `ant` CLI to resolve credentials."
    )

MODEL = resolve_model()
ENABLE_RERANK = os.getenv("ENABLE_RERANK", "").lower() in ("1", "true")
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "").lower() in ("1", "true")

# Quiet the SDK's one-shot notice that ANTHROPIC_API_KEY shadows profile/federation
# auto-discovery — expected when an API key is set; harmless under `ant` / WIF auth.
logging.getLogger("anthropic.lib.credentials._auth").setLevel(logging.ERROR)
client = Anthropic()
mongo = MongoClient(os.environ["MONGO_URI"])
db = mongo["fraud_review_demo"]
coll = db["transactions"]
ai_client = make_embedding_client()  # Atlas / Voyage / None (seed ships precomputed vectors)

print(
    f"model={MODEL}  rerank={'on' if ENABLE_RERANK else 'off'}  provider={'yes' if ai_client else 'none'}"
)
```

??? note "輸出"

    ```text
    warning: no ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / ANTHROPIC_PROFILE found; relying on the SDK / `ant` CLI to resolve credentials.
    model=claude-haiku-4-5  rerank=on  provider=yes
    ```

## 1. 把 MongoDB 接到 managed agent

Agent loop 和它的 sandbox 是 **Anthropic 代管**的，這就是「Managed」的意思。你唯一要自己架的是通往 MongoDB 的**資料路徑**。不管走哪條路，MongoDB 憑證都在*你*這一側的邊界內：不會進到 agent 的 context、雲端 sandbox 的環境，或 agent 讀得到的檔案。

> **為什麼這本 cookbook 用 `client.beta.*` 跟 CMA 溝通，而不是 Claude Agent SDK。**
> Managed Agents（CMA）是一個[代管的 REST API](https://platform.claude.com/docs/en/managed-agents/overview)：
> Anthropic 跑 agent loop 和 sandbox，你透過標準 Anthropic SDK 的 beta 介面
> （`client.beta.agents`、`client.beta.sessions`、`client.beta.sessions.events`）建立 agent/session 並串流事件來驅動它。
> 並沒有另一個「CMA SDK」，這就是使用 CMA 的方式。
> [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)
> （`claude-agent-sdk`，在 repo 的
> [`claude_agent_sdk/`](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk) cookbook 裡展示）是另一個產品：它是一個把 agent loop 跑在**你自己的 process 內**、你自己的基礎設施上的 library。兩者互補，你可以先用 Agent SDK 在本機做原型，再到 CMA 上線，但像這樣的 CMA 整合是建在 beta sessions/events API 上。這個選擇也讓下面的憑證邊界成立：因為是*你的* process 處理每一次 custom-tool 呼叫，所以 MongoDB 的密鑰留在 host 端（見 Path A）。

接資料路徑有三種方式。**這本 cookbook 全程用 Path A**，它是建議的、最輕量的模式，也能讓憑證完全留在 host 端。Path B 和 C 在後面簡述作為完整說明。

### Path A：host 端 custom tool（建議）

你的應用程式定義一個 `custom` tool。Agent 呼叫它時，session 會以 `requires_action` 暫停，由**你的** process 用 `pymongo` 執行查詢，再回傳一個 `user.custom_tool_result`。密鑰不會進 sandbox，MongoDB 可以放在私有 VPC 裡，agent 也被限制在固定且受稽核的查詢集合內。這是最輕的路徑，不用常駐伺服器，也是 Anthropic 對任何帶密鑰的資料來源所建議的模式。

為了看清楚接線，這裡用一個很小的 `find_notes` tool 搭配一個用完即丟的 `notes` collection 走完整個來回。**這就是核心整合：幾行 `pymongo`，在 host 端執行，躲在 custom tool 後面。** 第 3 節會把這個形狀放大成五個 tool 和真實的工作量。

```python
notes = mongo["cookbook_mongodb_on_cma"]["notes"]
notes.delete_many({})
notes.insert_many(
    [
        {"note_id": "n1", "tag": "todo", "text": "Renew the SSL certificate before it expires."},
        {"note_id": "n2", "tag": "idea", "text": "Add a dark-mode toggle to the dashboard."},
        {"note_id": "n3", "tag": "todo", "text": "Email the quarterly report to the finance team."},
    ]
)

notes_agent = client.beta.agents.create(
    name="cookbook-mongodb-notes",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-with-mongodb-atlas"},
    model=MODEL,
    system=(
        "You answer questions about the user's notes. Use the find_notes tool to fetch notes "
        "(optionally filtered by `tag`) before answering, then give a concise final answer."
    ),
    tools=[
        {
            "type": "agent_toolset_20260401",
            "default_config": {"enabled": True, "permission_policy": {"type": "always_allow"}},
        },
        {
            "type": "custom",
            "name": "find_notes",
            "description": "Return stored notes, optionally filtered by tag (e.g. 'todo', 'idea').",
            "input_schema": {
                "type": "object",
                "properties": {"tag": {"type": "string", "description": "optional tag filter"}},
                "required": [],
            },
        },
    ],
)
notes_env = client.beta.environments.create(
    name="cookbook-mongodb-notes-env", config={"type": "cloud", "networking": {"type": "limited"}}
)
notes_session = client.beta.sessions.create(
    environment_id=notes_env.id,
    agent={"type": "agent", "id": notes_agent.id, "version": notes_agent.version},
    title="MongoDB notes (host-side custom tool)",
)
print(f"seeded {notes.count_documents({})} notes; session: {notes_session.id}")
```

??? note "輸出"

    ```text
    seeded 3 notes; session: sesn_016ufm58BVJ8aZeWjUt39bsq
    ```

開啟事件 stream、問一個問題，然後驅動這個來回：每次 `agent.custom_tool_use` 出現，就用 `pymongo` 在 **host 端**執行查詢，再回傳 `user.custom_tool_result`。結果用 `{"_id": 0}` 做 projection，因為原始的 MongoDB `ObjectId` 不能 JSON 序列化。

```python
def run_find_notes(args: dict) -> dict:
    """Host-side handler: pymongo runs here; _id (ObjectId) is projected out so the result is JSON-able."""
    flt = {"tag": args["tag"]} if args.get("tag") else {}
    return {"notes": list(notes.find(flt, {"_id": 0}))}


tool_use_events, responded, round_trips = {}, set(), []
question = "Using find_notes, list every note tagged 'todo', then tell me how many there are."

with client.beta.sessions.events.stream(notes_session.id) as stream:
    client.beta.sessions.events.send(
        session_id=notes_session.id,
        events=[{"type": "user.message", "content": [{"type": "text", "text": question}]}],
    )
    for ev in stream:
        if ev.type == "agent.custom_tool_use":
            tool_use_events[ev.id] = ev
        elif ev.type == "session.status_idle" and ev.stop_reason:
            if ev.stop_reason.type == "requires_action":
                for event_id in ev.stop_reason.event_ids:
                    if event_id in responded:
                        continue
                    tev = tool_use_events[event_id]
                    result = (
                        run_find_notes(tev.input)
                        if tev.name == "find_notes"
                        else {"error": "unknown"}
                    )
                    if tev.name == "find_notes":
                        round_trips.append(
                            {"tool_input": tev.input, "returned": len(result["notes"])}
                        )
                    client.beta.sessions.events.send(
                        session_id=notes_session.id,
                        events=[
                            {
                                "type": "user.custom_tool_result",
                                "custom_tool_use_id": event_id,
                                "content": [{"type": "text", "text": json.dumps(result)}],
                            }
                        ],
                    )
                    responded.add(event_id)
            elif ev.stop_reason.type == "end_turn":
                break
        elif ev.type == "session.status_terminated":
            break

wait_for_idle_status(client, notes_session.id)
print("host-side find_notes round-trips:")
for rt in round_trips:
    print(f"  find_notes({rt['tool_input']}) -> {rt['returned']} notes")

client.beta.sessions.archive(notes_session.id)
client.beta.environments.archive(notes_env.id)
client.beta.agents.archive(notes_agent.id)
notes.drop()
print("archived the demo agent / environment / session; dropped the notes collection")
```

??? note "輸出"

    ```text
    host-side find_notes round-trips:
      find_notes({'tag': 'todo'}) -> 2 notes
    archived the demo agent / environment / session; dropped the notes collection
    ```

### 其他選項（簡述）

Path A 是預設，這本 cookbook 其餘部分都用它。如果它不適用，還有兩個替代方案，跟著讀的話用不到：

- **Path B：sandbox 內的 `pymongo`（自架 sandbox）。** 如果你在自己的基礎設施上跑 sandbox，MongoDB client 可以放在 sandbox *裡面*，agent 直接從它的 `bash` tool 查 MongoDB，`MONGO_URI` 就是一般的容器環境變數。只有自架 sandbox 才選這個（在雲端 sandbox 上，連線字串會出現在 session 歷史裡）。可執行的映像檔：[`mongodb_on_cma/self_hosted_sandbox/`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/self_hosted_sandbox)。
- **Path C：自架 MongoDB MCP server。** 把官方的 MongoDB MCP server 架在 HTTPS 後面，並註冊成 `mcp_toolset`，這樣 agent 可以用完整的查詢介面（`find`、`aggregate`、`$vectorSearch`），而不是固定的查詢集合。用的是標準的 CMA MCP + vault 接法。

取捨一句話講完：**Path A** 讓查詢集合固定、密鑰留在你的後端（最安全的預設）；**Path B** 讓 sandbox 直接存取；**Path C** 給 agent 最寬的查詢介面，代價是要多跑一個伺服器。不確定就留在 Path A。

## 2. 檢索：四種模式，一個引擎

Agent 的根據有多紮實，取決於檢索。這四種 MongoDB 檢索模式在這裡**單獨展示**：這是 builder，這是它回傳的東西，讓你可以只搬一種模式到自己 agent 的 tool 裡。每一個都是單純的 aggregation-pipeline builder，第 3 節的 agent 就是透過 tool 呼叫這些同樣的函式。

| 模式 | Builder | MongoDB stage |
| --- | --- | --- |
| Vector search | `build_vector_pipeline` | `$vectorSearch` |
| Full-text search | `build_lexical_pipeline` | `$search` |
| Hybrid (reciprocal rank fusion) | `build_rank_fusion_pipeline` | `$rankFusion` (8.0+) |
| Graph traversal | `build_graph_pipeline` | `$graphLookup` |

Builder 定義在下一個 cell 裡，每個都回傳一串 aggregation stage，你可以搬到自己的 collection。索引名稱和 projection 的欄位來自 [`config.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/config.py)；`EMBED_DIM` 和索引常數在上面的設定 cell 已經 import 了。

先從 [`example_data/mongodb_on_cma/`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/example_data/mongodb_on_cma/seed_transactions.jsonl) 載入 seed 資料並建立索引。這份資料附了預先算好的 embedding，所以不用供應商 key 也能跑。

```python
# The four retrieval builders — each returns a plain aggregation pipeline you can lift into your
# own collection. These are the functions Section 3's agent calls through its custom tools.
from mongodb_on_cma.config import (
    DECIDED_STATUSES,
    LEXICAL_PATHS,
    PROJECT_FIELDS,
    SEARCH_INDEX_NAME,
    VECTOR_INDEX_NAME,
)


def _project_stage(with_score: bool = False) -> dict:
    proj: dict[str, Any] = {f: 1 for f in PROJECT_FIELDS}
    proj["_id"] = 0
    if with_score:
        proj["score"] = {"$meta": "score"}
    return {"$project": proj}


def build_vector_pipeline(
    qvec, *, limit, candidates=None, vector_index=VECTOR_INDEX_NAME, status_in=DECIDED_STATUSES
) -> list[dict]:
    return [
        {
            "$vectorSearch": {
                "index": vector_index,
                "path": "embedding",
                "queryVector": qvec,
                "numCandidates": candidates or max(50, limit * 10),
                "limit": limit,
                "filter": {"status": {"$in": list(status_in)}},
            }
        },
        _project_stage(),
    ]


def build_lexical_pipeline(query, *, limit, search_index=SEARCH_INDEX_NAME) -> list[dict]:
    return [
        {"$search": {"index": search_index, "text": {"query": query, "path": LEXICAL_PATHS}}},
        {"$limit": limit},
        _project_stage(),
    ]


def build_rank_fusion_pipeline(
    qvec,
    query,
    *,
    k,
    vector_index=VECTOR_INDEX_NAME,
    search_index=SEARCH_INDEX_NAME,
    status_in=DECIDED_STATUSES,
) -> list[dict]:
    # $rankFusion (MongoDB 8.0+) runs both input pipelines and fuses them by reciprocal rank —
    # one aggregation, server-side. Each input pipeline gets weight 1 (uniform). To bias toward
    # semantic vs. lexical, add "combination": {"weights": {"vector": w, "lexical": w}}.
    candidates = max(50, k * 10)
    per_branch = max(k * 4, 20)
    return [
        {
            "$rankFusion": {
                "input": {
                    "pipelines": {
                        "vector": [
                            {
                                "$vectorSearch": {
                                    "index": vector_index,
                                    "path": "embedding",
                                    "queryVector": qvec,
                                    "numCandidates": candidates,
                                    "limit": per_branch,
                                    "filter": {"status": {"$in": list(status_in)}},
                                }
                            }
                        ],
                        "lexical": [
                            {
                                "$search": {
                                    "index": search_index,
                                    "text": {"query": query, "path": LEXICAL_PATHS},
                                }
                            },
                            {"$limit": per_branch},
                        ],
                    }
                },
            }
        },
        {"$limit": k},
        _project_stage(with_score=True),
    ]


def build_graph_pipeline(
    account_id: str, *, max_depth: int = 4, collection: str = "transactions"
) -> list[dict]:
    return [
        {"$match": {"sender.account_number": account_id}},
        {
            "$graphLookup": {
                "from": collection,
                "startWith": "$recipient.account_number",
                "connectFromField": "recipient.account_number",
                "connectToField": "sender.account_number",
                "as": "chain",
                "maxDepth": max_depth,
                "depthField": "depth",
            }
        },
    ]


def summarize_ring(graph_doc: dict, *, seed_account: str) -> dict:
    # Turn a $graphLookup chain into fraud-ring signals: circular flow back to the seed account,
    # layering (many small transfers), and overall network size.
    chain: list[dict] = list(graph_doc.get("chain", []))
    accounts: set[str] = set()
    small_transfers = 0
    circular_flow = False
    for edge in chain:
        sender = (edge.get("sender") or {}).get("account_number")
        recipient = (edge.get("recipient") or {}).get("account_number")
        accounts.update(a for a in (sender, recipient) if a)
        if recipient == seed_account:
            circular_flow = True
        if float(edge.get("amount", 0) or 0) < 1000:
            small_transfers += 1
    network_size = len(chain)
    layering = small_transfers >= 5
    return {
        "network_size": network_size,
        "unique_accounts": len(accounts),
        "circular_flow": circular_flow,
        "layering": layering,
        "suspicious_patterns": circular_flow or layering or network_size >= 3,
    }
```

```python
docs = prepare_seed(load_seed(), now=datetime.now(UTC))
count = seed_collection(coll, docs)
print(f"seeded {count} transactions")

# Create the vector + Atlas Search indexes if absent, then block until both are queryable AND
# actually reflect the freshly-seeded docs (Atlas Search is eventually consistent).
ensure_indexes(coll, dim=EMBED_DIM)

check = preflight(coll)
for issue in check["issues"]:
    print("PREFLIGHT:", issue)
assert check["ok"], "Fix the preflight issues above before continuing."

# This cookbook uses the native `$rankFusion` stage for hybrid search, which needs MongoDB 8.0+.
# Every current Atlas cluster — including the free M0 tier — runs 8.0 or later, so this holds by
# default; the check just fails loudly if you point MONGO_URI at an older self-hosted server.
version = server_version(coll)
assert supports_rank_fusion(version), (
    f"MongoDB {version} predates $rankFusion (needs 8.0+). Use an Atlas cluster (any tier) or a "
    f"self-hosted MongoDB 8.0+."
)
print(f"server={version}  hybrid search=$rankFusion (native)")
```

??? note "輸出"

    ```text
    seeded 20 transactions
    server=8.0.27  hybrid search=$rankFusion (native)
    ```

### 模式 1：Vector search（`$vectorSearch`）

語意召回：找出 `embedding` 最接近 query vector 的文件。這個範例拿一份既有文件的 embedding 當 query（一個待審案例在找已有結論的前例），所以不需要呼叫 embedding API。Builder 透過 `status` 欄位只篩已決議的案例。

```python
query_doc = coll.find_one({"transaction_id": "txn-review-struct"})  # a pending case
hits = list(coll.aggregate(build_vector_pipeline(query_doc["embedding"], limit=3)))
print("nearest decided precedents:")
for h in hits:
    print(f"  {h['transaction_id']}: {h['text'][:72]}")
```

??? note "輸出"

    ```text
    nearest decided precedents:
      txn-struct-01: Cash deposit of 4950 USD, just under the 5000 reporting threshold. Third
      txn-struct-02: Cash deposit of 4900 USD just below the 5000 CTR threshold, same account
      txn-struct-03: Transfer of 4999 USD deliberately under 5000 to avoid reporting. Pattern
    ```

### 模式 2：Full-text search（`$search`，BM25）

對文字欄位做關鍵字和詞組比對，這正是 embedding 會模糊掉的精確名字、ID 和代碼會被抓到的地方。

```python
hits = list(
    coll.aggregate(
        build_lexical_pipeline("cash deposit just under the reporting threshold", limit=3)
    )
)
print("full-text matches:")
for h in hits:
    print(f"  {h['transaction_id']}: {h['text'][:72]}")
```

??? note "輸出"

    ```text
    full-text matches:
      txn-struct-01: Cash deposit of 4950 USD, just under the 5000 reporting threshold. Third
      txn-review-struct: Cash deposit of 4950 USD, just under the 5000 reporting threshold, follo
      txn-struct-02: Cash deposit of 4900 USD just below the 5000 CTR threshold, same account
    ```

### 模式 3：Hybrid（reciprocal rank fusion）

把 vector 和 full-text 的排名融合成一個結果集。`$rankFusion`（MongoDB 8.0+）在 server 端跑兩條輸入 pipeline，並用 reciprocal rank 合併，不用在 client 端合併，也不用多一趟來回。

```python
qvec, query = query_doc["embedding"], "structuring: cash deposit just under the threshold"
hits = list(coll.aggregate(build_rank_fusion_pipeline(qvec, query, k=3)))
print("hybrid via $rankFusion (server-side):")
for h in hits:
    print(f"  {h['transaction_id']}: {h['text'][:72]}")
```

??? note "輸出"

    ```text
    hybrid via $rankFusion (server-side):
      txn-struct-01: Cash deposit of 4950 USD, just under the 5000 reporting threshold. Third
      txn-struct-02: Cash deposit of 4900 USD just below the 5000 CTR threshold, same account
      txn-struct-03: Transfer of 4999 USD deliberately under 5000 to avoid reporting. Pattern
    ```

### 模式 4：Graph traversal（`$graphLookup`）

沿著 `sender.account_number -> recipient.account_number` 的連結找出一張網路（這裡是一個循環的資金流動環）。這是*關係*訊號，刻意跟上面的相似度排名分開。

```python
graph_doc = next(
    iter(coll.aggregate(build_graph_pipeline("ACC-RING-A", collection=coll.name))), {"chain": []}
)
ring = summarize_ring(graph_doc, seed_account="ACC-RING-A")
print(
    f"graph traversal from ACC-RING-A: network_size={ring['network_size']} "
    f"circular_flow={ring['circular_flow']} suspicious={ring['suspicious_patterns']}"
)
```

??? note "輸出"

    ```text
    graph traversal from ACC-RING-A: network_size=4 circular_flow=True suspicious=True
    ```

**依你的領域調整。** 每個 builder 都是通用的形狀：用任何模型 embed 你的文字，並把 `build_vector_pipeline` 指到你的欄位；設定 full-text 要搜的路徑；調整 `$rankFusion` 輸入的權重來偏向語意或字面；把 graph 的 `connectFromField`/`connectToField` 改成你的關係（引用、組織圖、供應鏈）。四個都定義在上面的 cell 裡，直接搬到你自己的專案即可。

## 3. 端到端 agent：有人工把關的詐欺審查

現在把所有東西串起來。一個 Managed Agent 審查被標記的交易，每個建議都以第 2 節的 MongoDB 訊號為依據（透過 Path A 的來回，以 **custom tool** 的形式提供），遇到高風險案例就暫停等人工。決策和 append-only 的稽核紀錄會寫回同一個 cluster。

<p align="center">
  <img src="https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/images/cma_with_mongodb_atlas.jpg" width="70%" alt="The agent loop runs on Anthropic; the data path runs in your notebook. MongoDB Atlas serves the retrieval signals and stores the decision and audit trail." />
</p>

**Agent loop 跑在 Anthropic**；**資料路徑跑在你的 notebook**。因此 `MONGO_URI` 和 embedding key 都不會進到 agent 或它的 sandbox。等人的過程是持久的：session 會在 server 端透過 `requires_action` 閒置，直到你回應。下面簡單的串流迴圈是給開發用的（正式環境請用 webhook 模式，從持久的後端來驅動）。

### AP2 mandate：先驗證，再推理

這個 agent 審查的是 *agent 發起*的付款，所以在做任何行為分析之前，會先驗證 **AP2（Agent Payments Protocol）** mandate，也就是證明使用者授權了這筆付款的密碼學簽章憑證。AP2 是 agent 驅動商務的[開放協定](https://github.com/google-agentic-commerce/AP2)。它的 mandate（**Checkout Mandate** 和 **Payment Mandate**）是防竄改的簽章數位物件，構成一條可稽核的鏈。要跟著這本 cookbook 走不需要學這個協定：**呼叫 `verify_mandates` tool，然後依它的判定行動**（valid、constraints-satisfied 和 double-spend）。簽章和驗證的細節（ES256 JWT）都封裝在 [`ap2_mandates.py`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma/ap2_mandates.py) 裡，簽好的 mandate 和收據跟交易一起存在 MongoDB。

下面的 cell 扮演「Trusted Surface」（產生金鑰對，並把簽好的 mandate 附到待審案例上）。私鑰只留在本機 Python 狀態，絕不進 agent、tool 結果或資料庫。

```python
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

ts_private_key = ec.generate_private_key(ec.SECP256R1())  # Trusted Surface key, fresh each run
AGENT_PK = (
    ts_private_key.public_key()
    .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    .hex()
)
ts_public_key = ts_private_key.public_key()

PENDING = [
    "txn-review-clean",
    "txn-review-fraud",
    "txn-review-struct",  # seeded human-override case under AUTO_APPROVE
    "txn-review-high",
    "txn-review-ring",
]
mandates = attach_mandates(coll, PENDING, agent_pk=AGENT_PK, ts_private_key=ts_private_key)
print(f"attached AP2 mandates to {len(mandates)} transactions  agent_pk={AGENT_PK[:16]}…")
```

??? note "輸出"

    ```text
    attached AP2 mandates to 5 transactions  agent_pk=04e1e32b7414d6f7…
    ```

### Custom tool 和 host 端的 handler

每個 tool 都是 `type: "custom"` 的 tool。Agent 呼叫其中一個時，session 會暫停，由**這本 notebook** 用 `pymongo` 執行 handler 並把 JSON 結果送回去，agent 從不碰資料庫或連線字串。Handler 的實作定義在下一個 cell：它們包裝了第 2 節的 builder 加上 AP2 驗證（`verify_mandates`）。`HANDLERS` 只對應五個資料 tool；`escalate` 刻意不在裡面，因為閘門迴圈會把它交給人工處理者，而不是 handler（見下一節）。

```python
# The host-side tool implementations — the pymongo work behind each custom tool. These run in
# THIS process (never the sandbox), reusing the Section 2 builders. The dispatch wiring + the
# AP2/record-decision wrappers are in the next cell; build_decision_doc / build_audit_event
# (imported above) shape the persisted documents and are shared with the AP2 module.


def _jsonable(value):
    """Recursively coerce Mongo/BSON values (ObjectId, datetime, ...) into JSON-safe types."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _pick_fields(candidate):
    keep = ("transaction_id", "text", "amount", "sender", "recipient", "decision", "score")
    return _jsonable({k: candidate[k] for k in keep if k in candidate})


def rerank_pool_size(k: int, fanout: int, *, enable_rerank: bool) -> int:
    return k * fanout if enable_rerank else k


def merge_rerank(candidates, rerank_results, *, top_k) -> list[dict]:
    def _score(r):
        s = getattr(r, "relevance_score", None)
        return (
            (s if s is not None else r.get("relevance_score", float("-inf")))
            if isinstance(r, dict)
            else (s if s is not None else float("-inf"))
        )

    seen: set[str] = set()
    out: list[dict] = []
    for result in sorted(rerank_results, key=_score, reverse=True):
        index = getattr(result, "index", None)
        if index is None and isinstance(result, dict):
            index = result.get("index")
        score = getattr(result, "relevance_score", None)
        if score is None and isinstance(result, dict):
            score = result.get("relevance_score")
        if index is None or index < 0 or index >= len(candidates):
            continue
        candidate = candidates[index]
        cid = str(candidate.get("transaction_id", index))
        if cid in seen:
            continue
        seen.add(cid)
        out.append({**candidate, "score": score})
        if len(out) >= top_k:
            break
    return out


def tool_get_transaction(coll, transaction_id) -> dict:
    doc = coll.find_one({"transaction_id": transaction_id})
    if not doc:
        return {"error": "not_found", "transaction_id": transaction_id}
    return _jsonable({k: v for k, v in doc.items() if k not in ("embedding", "_id")})


def tool_hybrid_search_similar_frauds(
    coll,
    transaction_id,
    k,
    *,
    enable_rerank=False,
    fanout=5,
    reranker=None,
    vector_index=VECTOR_INDEX_NAME,
    search_index=SEARCH_INDEX_NAME,
    status_in=DECIDED_STATUSES,
) -> dict:
    txn = coll.find_one({"transaction_id": transaction_id})
    if not txn:
        return {"error": "not_found", "transaction_id": transaction_id, "similar": []}
    qvec = txn["embedding"]
    query = txn.get("text", "")
    pool_k = rerank_pool_size(k, fanout, enable_rerank=enable_rerank)
    candidates = list(
        coll.aggregate(
            build_rank_fusion_pipeline(
                qvec,
                query,
                k=pool_k,
                vector_index=vector_index,
                search_index=search_index,
                status_in=status_in,
            )
        )
    )
    candidates = [c for c in candidates if str(c.get("transaction_id")) != str(transaction_id)]
    if enable_rerank and reranker is not None and candidates:
        results = reranker(query, [c.get("text", "") for c in candidates], top_k=k)
        candidates = merge_rerank(candidates, results, top_k=k)
    else:
        candidates = candidates[:k]
    return {"similar": [_pick_fields(c) for c in candidates]}


def tool_detect_fraud_ring(coll, account_id, *, max_depth=4) -> dict:
    pipeline = build_graph_pipeline(account_id, max_depth=max_depth, collection=coll.name)
    docs = list(coll.aggregate(pipeline))
    return _jsonable(summarize_ring(docs[0] if docs else {"chain": []}, seed_account=account_id))


def tool_record_decision(
    db,
    transaction_id,
    decision,
    *,
    confidence,
    risk_factors,
    reasoning,
    reviewed_by,
    escalated=False,
    recommended_decision=None,
) -> dict:
    decision_doc = build_decision_doc(
        transaction_id,
        decision,
        confidence=confidence,
        risk_factors=risk_factors,
        reasoning=reasoning,
        reviewed_by=reviewed_by,
    )
    db["transaction_decisions"].insert_one(decision_doc)
    if escalated:
        audit = build_audit_event(
            "escalated_to_human",
            transaction_id,
            decision_id=decision_doc["decision_id"],
            severity="warning",
            event_data={"human_decision": decision, "recommended_decision": recommended_decision},
        )
    else:
        audit = build_audit_event(
            "decision_stored", transaction_id, decision_id=decision_doc["decision_id"]
        )
    db["audit_events"].insert_one(audit)
    # Advance the lifecycle status to past tense (approve -> approved) so a decided case matches
    # the seed's vocabulary and DECIDED_STATUSES, making it eligible as precedent in later reviews.
    status = {"approve": "approved", "reject": "rejected"}.get(decision, decision)
    db["transactions"].update_one({"transaction_id": transaction_id}, {"$set": {"status": status}})
    return {"recorded": True, "decision_id": decision_doc["decision_id"]}
```

```python
TOOLS = [
    {
        "type": "custom",
        "name": "verify_mandates",
        "description": "Validate the AP2 Checkout and Payment Mandate JWTs (signature, constraints, "
        "double-spend). Run this FIRST. If valid=false, constraints_satisfied=false, or "
        "double_spend_detected=true, reject immediately.",
        "input_schema": {
            "type": "object",
            "properties": {"transaction_id": {"type": "string"}},
            "required": ["transaction_id"],
        },
    },
    {
        "type": "custom",
        "name": "get_transaction",
        "description": "Fetch the full transaction record under review.",
        "input_schema": {
            "type": "object",
            "properties": {"transaction_id": {"type": "string"}},
            "required": ["transaction_id"],
        },
    },
    {
        "type": "custom",
        "name": "hybrid_search_similar_frauds",
        "description": "Retrieve the most similar prior (already-decided) cases as precedent, using "
        "hybrid vector + full-text search.",
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction_id": {"type": "string"},
                "k": {"type": "integer", "description": "how many precedents (default 5)"},
            },
            "required": ["transaction_id"],
        },
    },
    {
        "type": "custom",
        "name": "detect_fraud_ring",
        "description": "Trace the account's sender->recipient chain for circular-flow / mule / layering patterns.",
        "input_schema": {
            "type": "object",
            "properties": {"account_id": {"type": "string"}},
            "required": ["account_id"],
        },
    },
    {
        "type": "custom",
        "name": "record_decision",
        "description": "Persist the final approve/reject decision with reasoning and an audit event.",
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approve", "reject"]},
                "confidence": {"type": "number"},
                "risk_factors": {"type": "array", "items": {"type": "string"}},
                "reasoning": {"type": "string"},
                "escalated": {"type": "boolean"},
                "recommended_decision": {"type": "string", "enum": ["approve", "reject"]},
            },
            "required": ["transaction_id", "decision", "reasoning"],
        },
    },
    {
        "type": "custom",
        "name": "escalate",
        "description": "Send a risky case to a human reviewer for the final decision. Use for "
        "medium-confidence, high-value, structuring, or fraud-ring cases.",
        "input_schema": {
            "type": "object",
            "properties": {
                "transaction_id": {"type": "string"},
                "recommended_decision": {"type": "string", "enum": ["approve", "reject"]},
                "confidence": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["transaction_id", "recommended_decision", "reason"],
        },
    },
]
```

```python
# Host-side handlers — map each data tool to its handler function.
reranker = (
    (lambda q, ds, top_k: rerank(q, ds, client=ai_client, top_k=top_k))
    if (ENABLE_RERANK and ai_client)
    else None
)


def _verify_mandates(inp):
    result = tool_verify_mandates(db, inp["transaction_id"], ts_public_key)
    ok = result["valid"] and result["constraints_satisfied"] and not result["double_spend_detected"]
    print(f"\n  [verify_mandates] {inp['transaction_id']}: {'pass' if ok else 'FAIL'}")
    return result


def _hybrid(inp):
    return tool_hybrid_search_similar_frauds(
        coll,
        inp["transaction_id"],
        inp.get("k", 5),
        enable_rerank=ENABLE_RERANK,
        reranker=reranker,
    )


def _record(inp):
    result = tool_record_decision(
        db,
        inp["transaction_id"],
        inp["decision"],
        confidence=inp.get("confidence", 0),
        risk_factors=inp.get("risk_factors", []),
        reasoning=inp.get("reasoning", ""),
        reviewed_by="human" if inp.get("escalated") else "agent",
        escalated=inp.get("escalated", False),
        recommended_decision=inp.get("recommended_decision"),
    )
    if (
        inp["decision"] == "approve"
    ):  # store the AP2 receipt that later powers double-spend detection
        txn_doc = coll.find_one(
            {"transaction_id": inp["transaction_id"]},
            {"checkout_mandate_jwt": 1, "mandate_id": 1, "agent_pk": 1},
        )
        if txn_doc and txn_doc.get("mandate_id"):
            checkout_hash = hashlib.sha256(txn_doc["checkout_mandate_jwt"].encode()).hexdigest()
            store_mandate_receipt(
                db, txn_doc["mandate_id"], txn_doc["agent_pk"], checkout_hash, "approve"
            )
    return result


HANDLERS = {
    "verify_mandates": _verify_mandates,
    "get_transaction": lambda inp: tool_get_transaction(coll, inp["transaction_id"]),
    "hybrid_search_similar_frauds": _hybrid,
    "detect_fraud_ring": lambda inp: tool_detect_fraud_ring(coll, inp["account_id"]),
    "record_decision": _record,
}
```

### 建立 agent、environment 和 session

`model`、`system` 和 `tools` 屬於 **agent**。Session 引用它並配置 sandbox。網路設為 `limited`：agent 只能透過 host 端的來回存取 MongoDB。

```python
SYSTEM = """You are a financial fraud reviewer. You will be given transaction IDs to review.

For EACH transaction, in order:
1. Call get_transaction to read it.
2. Call verify_mandates to validate the AP2 mandate chain (signature, constraints, double-spend).
   HARD GATE: if verify_mandates returns valid=false, constraints_satisfied=false, OR
   double_spend_detected=true, call record_decision immediately with decision="reject" and
   skip the remaining steps for that transaction.
3. Call hybrid_search_similar_frauds to retrieve similar decided precedents.
4. Call detect_fraud_ring on the sender's account_number to check for ring/mule patterns.
5. Weigh the precedents, the ring signal, the amount, and your confidence. Then make EXACTLY
   ONE terminal call for that transaction:
   - You MUST call escalate (do NOT call record_decision yourself) whenever ANY of these holds:
       * a structuring amount ($4,900-$4,999),
       * a high-value amount (>= $50,000) that you would otherwise approve,
       * detect_fraud_ring reports suspicious_patterns, or
       * your confidence is medium (~75-85).
     Give your recommended_decision and a short reason.
   - Otherwise (a clear-cut case matching none of the above), call record_decision (approve/reject).

When you escalate, you will receive the human's decision. Then call record_decision with that
decision, escalated=true, and recommended_decision set to what you had recommended.

Be concise. Move to the next transaction after recording a decision."""

agent = client.beta.agents.create(
    name="MongoDB Atlas fraud reviewer",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-with-mongodb-atlas"},
    model=MODEL,
    system=SYSTEM,
    tools=TOOLS,
)
environment = client.beta.environments.create(
    name="fraud-review-env", config={"type": "cloud", "networking": {"type": "limited"}}
)
session = client.beta.sessions.create(
    agent={"type": "agent", "id": agent.id, "version": agent.version},
    environment_id=environment.id,
    title="Fraud review",
)
print("session:", session.id)
print(f"Watch in Console: https://platform.claude.com/workspaces/default/sessions/{session.id}")
```

??? note "輸出"

    ```text
    session: sesn_01LbAUC1V36CQS3Sk26eixTc
    Watch in Console: https://platform.claude.com/workspaces/default/sessions/sesn_01LbAUC1V36CQS3Sk26eixTc
    ```

### 帶著人工閘門執行審查

開啟事件 stream、送出待審交易的佇列，並用 `run_gate_loop` 驅動閘門迴圈：資料 tool 的呼叫自動由 `HANDLERS` 處理，`escalate` 呼叫則暫停等人工。設了 `AUTO_APPROVE`（例如在 CI）時，閘門會固定地處理，並在預設的 structuring 案例上**推翻 agent**，讓你看得到人工判定不同的情況。否則會在行內問你。

```python
OVERRIDE_IDS = {"txn-review-struct"}


def resolve_human_decision(recommendation, *, auto_approve, override_ids, txn_id) -> str:
    """Stand in for a human reviewer. In CI (auto_approve) it concurs with the agent, except on
    the seeded override_ids where it flips the verdict so a differing human decision is visible."""
    opposite = "reject" if recommendation == "approve" else "approve"
    if auto_approve and txn_id in set(override_ids):
        return opposite
    return recommendation


def resolver(tool_input):
    txn_id = tool_input.get("transaction_id", "")
    recommended = tool_input.get("recommended_decision", "reject")
    if AUTO_APPROVE:
        decision = resolve_human_decision(
            recommended, auto_approve=True, override_ids=OVERRIDE_IDS, txn_id=txn_id
        )
        flag = "  <-- HUMAN OVERRIDE" if decision != recommended else ""
        print(f"  [human/auto] {txn_id}: agent recommended {recommended} -> human {decision}{flag}")
        return decision
    print(
        f"\n  ESCALATED {txn_id} (agent recommends {recommended}): {tool_input.get('reason', '')}"
    )
    return (
        "approve"
        if input("  Your decision [approve/reject]: ").strip().lower().startswith("a")
        else "reject"
    )


def send_result(custom_tool_use_id, result):
    client.beta.sessions.events.send(
        session_id=session.id,
        events=[
            {
                "type": "user.custom_tool_result",
                "custom_tool_use_id": custom_tool_use_id,
                "content": [{"type": "text", "text": json.dumps(result)}],
            }
        ],
    )


def run_gate_loop(stream, send, *, handlers, resolver) -> dict:
    """Drive the session to completion, servicing custom-tool calls as they arrive.

    This is the whole Path A round-trip for a real workload. Each `agent.custom_tool_use`
    event names a tool and its input; the session then goes idle with
    `stop_reason == "requires_action"` until we answer. We look up the tool in `handlers`
    (which run `pymongo` host-side — the credential never leaves this process), and route the
    special `escalate` tool to the human `resolver` instead. We post each result back with
    `send`, and the session resumes. Break on a terminal idle (`end_turn`) or termination.
    """
    pending: dict[str, Any] = {}
    responded: set[str] = set()
    serviced: list[tuple[str, dict]] = []
    for ev in stream:
        if ev.type == "agent.custom_tool_use":
            pending[ev.id] = ev
        elif ev.type == "session.status_idle":
            stop = getattr(ev, "stop_reason", None)
            if stop is None:
                continue
            if stop.type != "requires_action":
                break  # end_turn / retries_exhausted — the run is done
            for event_id in stop.event_ids or []:
                if event_id in responded:
                    continue
                call = pending.get(event_id)
                if call is None:
                    continue
                if call.name == "escalate":
                    result = {"human_decision": resolver(call.input)}
                else:
                    handler = handlers.get(call.name)
                    result = (
                        handler(call.input) if handler else {"error": f"unknown tool {call.name}"}
                    )
                responded.add(event_id)
                send(event_id, result)
                serviced.append((call.name, result))
        elif ev.type == "session.status_terminated":
            break
    return {"serviced": serviced, "responded": sorted(responded)}


kickoff = {
    "type": "user.message",
    "content": [
        {"type": "text", "text": "Review these flagged transactions: " + ", ".join(PENDING)}
    ],
}
run_start = datetime.now(UTC)

with client.beta.sessions.events.stream(session_id=session.id) as stream:
    client.beta.sessions.events.send(session_id=session.id, events=[kickoff])
    gate_result = run_gate_loop(stream, send_result, handlers=HANDLERS, resolver=resolver)

wait_for_idle_status(client, session.id)
print(f"\nserviced {len(gate_result['serviced'])} tool calls")
```

??? note "輸出"

    ```text

      [verify_mandates] txn-review-clean: pass

      [verify_mandates] txn-review-fraud: pass

      [verify_mandates] txn-review-struct: pass

      [verify_mandates] txn-review-high: pass

      [verify_mandates] txn-review-ring: pass

      ESCALATED txn-review-struct (agent recommends reject): Structuring indicator: cash deposit of $4,950 just under $5,000 CTR threshold, matching precedent (txn-struct-01, txn-struct-02) showing pattern of deliberate sub-threshold deposits from same account. Amount in structuring range per policy. Requires human review.
    ```

    ```text
      Your decision [approve/reject]:  reject
    ```

    ```text

      ESCALATED txn-review-high (agent recommends approve): High-value wire of $75,000 from Northwind Foods to Pacific Logistics for bulk shipment. Legitimate business transaction matching precedent txn-high-01 ($120,000 supplier wire, approved). Mandate valid, no fraud signals. Escalation required per policy for high-value transactions ≥ $50,000.
    ```

    ```text
      Your decision [approve/reject]:  approve
    ```

    ```text

      ESCALATED txn-review-ring (agent recommends reject): Money-mule ring detected. Sender ACC-RING-A (Quartz Trading) is part of a 4-account network with circular flows. Precedent txn-ring-01 (same sender/recipient, $920, rejected) shows identical pattern. Fraud ring analysis confirms suspicious_patterns, circular_flow. Requires human review for definitive ring-case determination.
    ```

    ```text
      Your decision [approve/reject]:  reject
    ```

    ```text

    serviced 28 tool calls
    ```

### 檢視決策和稽核紀錄

從 MongoDB 讀回決策和稽核紀錄。決策和稽核 collection 是 **append-only**，所以讀回的範圍限定在這次執行。最後的 assert 讓這變成**自我檢查**：重跑時如果沒重現預期的 lane 分布，就會明確失敗。

人工推翻的次數反映閘門是怎麼處理的：有 `AUTO_APPROVE` 時是 1（會顯示 `txn-review-struct` 上預設的推翻），互動式執行時，只要你每次升級案例都同意 agent 的建議就是 0，兩種都是正常的。

```python
from collections import Counter

decisions = list(db["transaction_decisions"].find({"created_at": {"$gte": run_start}}, {"_id": 0}))
audits = list(db["audit_events"].find({"timestamp": {"$gte": run_start}}, {"_id": 0}))

print("Decisions by lane:")
lanes = Counter()
for d in decisions:
    txn = coll.find_one({"transaction_id": d["transaction_id"]})
    lanes[f"{(txn['lane'] if txn else '?')} -> {d['decision']}"] += 1
for k, v in sorted(lanes.items()):
    print(f"  {k}: {v}")

overrides = [
    a
    for a in audits
    if a["event_type"] == "escalated_to_human"
    and a["event_data"].get("human_decision") != a["event_data"].get("recommended_decision")
]
print(
    f"\nescalated_to_human events: {sum(1 for a in audits if a['event_type'] == 'escalated_to_human')}"
)
print(f"human overrides (verdict != agent recommendation): {len(overrides)}")
for a in overrides:
    ed = a["event_data"]
    print(
        f"  {a['transaction_id']}: agent {ed['recommended_decision']} -> human {ed['human_decision']}"
    )

# Self-check — fail loudly if this run didn't produce the expected result.
decided_lanes = {coll.find_one({"transaction_id": d["transaction_id"]})["lane"] for d in decisions}
assert decided_lanes == {"clean_approve", "clear_reject", "high_value", "ring", "structuring"}, (
    f"expected all 5 lanes decided, saw {sorted(decided_lanes)}"
)
assert len(decisions) == len(PENDING), f"expected {len(PENDING)} decisions, got {len(decisions)}"
assert sum(1 for a in audits if a["event_type"] == "escalated_to_human") >= 1, (
    "expected >=1 escalation"
)
if AUTO_APPROVE:
    assert overrides, "AUTO_APPROVE run should show the seeded override on txn-review-struct"
print("\nself-check OK")
```

??? note "輸出"

    ```text
    Decisions by lane:
      clean_approve -> approve: 1
      clear_reject -> reject: 1
      high_value -> approve: 1
      ring -> reject: 1
      structuring -> reject: 1

    escalated_to_human events: 3
    human overrides (verdict != agent recommendation): 0

    self-check OK
    ```

## 4. MongoDB Atlas 當 system of record 和稽核骨幹

退一步看這次執行的狀態放在哪：agent 做的一切都持久存在它檢索用的同一個 cluster 裡。這就是寫入端的單一引擎好處：`transactions` 是營運紀錄（每個案例從 `pending` 前進到 `approved` 或 `rejected`），`transaction_decisions` 放不可變的判決，`audit_events` 是 append-only 軌跡，`mandate_receipts` 支撐 double-spend 偵測。一個案例從頭到尾的樣子：

```python
case = "txn-review-struct"
txn = coll.find_one({"transaction_id": case}, {"_id": 0, "embedding": 0})
print(f"operational record: {case}  lane={txn['lane']}  status={txn['status']}")

decision = db["transaction_decisions"].find_one(
    {"transaction_id": case, "created_at": {"$gte": run_start}}, {"_id": 0}
)
print(
    f"decision record:    {decision['decision']}  reviewed_by={decision['reviewed_by']}  confidence={decision['confidence_score']}"
)

print("audit trail (append-only):")
for a in (
    db["audit_events"]
    .find({"transaction_id": case, "timestamp": {"$gte": run_start}}, {"_id": 0})
    .sort("timestamp", 1)
):
    extra = ""
    if a["event_type"] == "escalated_to_human":
        ed = a["event_data"]
        extra = f"  (agent recommended {ed['recommended_decision']}, human decided {ed['human_decision']})"
    print(f"  {a['timestamp']:%H:%M:%S}  {a['event_type']}  severity={a['severity']}{extra}")

txn_mandate = coll.find_one({"transaction_id": case}, {"mandate_id": 1, "agent_pk": 1})
if txn_mandate and txn_mandate.get("mandate_id"):
    receipt = db["mandate_receipts"].find_one({"mandate_id": txn_mandate["mandate_id"]}, {"_id": 0})
    if receipt:
        print(
            f"mandate receipt:    mandate_id={receipt['mandate_id'][:12]}…  decision={receipt['decision']}"
        )
```

??? note "輸出"

    ```text
    operational record: txn-review-struct  lane=structuring  status=rejected
    decision record:    reject  reviewed_by=human  confidence=0.9
    audit trail (append-only):
      13:49:22  escalated_to_human  severity=warning  (agent recommended reject, human decided reject)
    ```

**正式環境用 webhook（只提示，這裡不執行）：** 上面的串流迴圈適合開發，但撐不過重啟。正式環境請註冊 `session.status_idled` 的 webhook：你的 handler 把案例排給審查員，之後再 POST `user.custom_tool_result`。**資料 tool 的 handler 完全相同**，只有觸發方式改變。見 [`CMA_operate_in_production.ipynb`](CMA_operate_in_production.md)。

```python
client.beta.sessions.archive(session.id)
client.beta.environments.archive(environment.id)
# Agents are reusable across runs; archiving is optional and permanent.
mongo.close()
print("archived session + environment; closed MongoDB connection")
```

??? note "輸出"

    ```text
    archived session + environment; closed MongoDB connection
    ```

## 5. 回顧

你把 MongoDB Atlas 接到 Claude Managed Agent，一次 build 就從連線做到 system of record：

- **Connect**：三種不外洩憑證的資料路徑（host 端 custom tool、自架 sandbox、自架 MCP），MongoDB 密鑰永遠在你這一側。
- **Retrieve**：vector、full-text、hybrid RRF 和 graph 走訪，作為可搬走的 pipeline builder，定義在第 2 節裡。
- **Gate**：風險決策擋在 CMA 原生的 `requires_action` 人工暫停之後。
- **Persist**：決策、append-only 稽核軌跡和 AP2 收據，都存在 agent 檢索用的同一個 cluster。

整合面很小：custom tool 後面幾行 `pymongo`。換掉 collection 和 tool，同樣的形狀就能讓任何 agent 以 MongoDB 為依據。檢索 builder、tool handler 和閘門迴圈都在這本 notebook 裡；[`mongodb_on_cma/`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/mongodb_on_cma) 套件只放設定樣板。

## 重點整理

- Managed Agent 的 agent loop 和 sandbox 在 Anthropic 那邊，你只自架資料路徑。用 host 端 custom tool，密鑰就不會進 agent 或 sandbox。
- 一個 MongoDB 引擎同時提供 vector、full-text、hybrid（RRF）和 graph 檢索，不用拼湊多個系統，也少掉多組憑證和資料不同步的問題。
- 四種檢索各抓不同訊號：vector 抓語意相近，full-text 抓精確的名字和代碼，hybrid 兩者兼顧，graph 抓關係網路。
- `requires_action` 閘門讓高風險決策停下來等人，session 在 server 端閒置，不怕等很久。
- 決策和稽核紀錄寫在同一個 cluster 並採 append-only，agent 的行為事後可追溯。

## 練習

1. 把 Path A 範例的 `find_notes` 加一個 `limit` 參數，讓 agent 可以指定回傳幾筆，並在 handler 裡傳給 `pymongo`。
2. 調整 `build_rank_fusion_pipeline` 兩條輸入 pipeline 的權重，偏向 full-text，看同一個 query 的排名怎麼變。
3. 把 `build_graph_pipeline` 的 `connectFromField`/`connectToField` 和 `maxDepth` 改一改，觀察圈出來的循環資金網路範圍怎麼變，再想想換成引用或組織圖要改哪些欄位。
