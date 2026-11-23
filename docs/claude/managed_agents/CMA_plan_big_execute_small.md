---
translated: true
source: managed_agents/CMA_plan_big_execute_small.ipynb
---
# Orchestrator 模式：大模型負責規劃，小模型負責執行

> 原文：[managed_agents/CMA_plan_big_execute_small.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_plan_big_execute_small.ipynb)

透過 multiagent 設定組成雙模型團隊：frontier orchestrator 負責規劃與彙整，便宜的 search worker 在平行的 thread 裡處理耗 token 的網頁閱讀。再跟一個嚴謹度相同、只用 frontier 模型的對照組比較真實帳單。內容包含每個 thread 的 usage.list_cost 計量、成本歸屬，以及用 session budget 當 fan-out 的護欄。

## 這篇在做什麼

很多 agent 工作其實包含兩種性質差很多的活：少量的規劃與判斷，加上大量的機械式閱讀與執行。這篇用網路研究當例子，讓 frontier 模型只負責規劃和彙整，便宜的 worker 去讀網頁，然後拿真實帳單跟「單一 frontier agent 自己全做」的對照組比。

## 學完你會

- 用 `multiagent` 區塊設定一個雙模型團隊：frontier orchestrator 加上便宜的 search worker
- 從 session event stream 即時追蹤委派過程（`thread_created`、`thread_message_sent`、`thread_message_received`）
- 跑一個嚴謹度對齊的 solo-frontier 對照組，用真實帳單比較成本

## 開跑前

- 需要 Anthropic API key，而且要有 Managed Agents beta 的使用權限
- 會真的花錢跑 web search 研究，session 有設 $10 的 budget 上限

## Introduction

大部分 agent 工作量裡面藏著兩種很不一樣的活：少量的規劃與判斷，以及大量的機械式閱讀和執行。網路研究是最極端的例子，也是這本 notebook 用的範例：要對照權威來源驗證二十個事實，得讓模型讀過幾十萬 token 的網頁，用 frontier 的費率算，這筆閱讀費會佔掉大部分成本。

Orchestrator 模式把兩種工作拆開。Frontier 模型負責規劃研究和彙整答案，但它完全不碰原始網頁；便宜的 worker 在各自平行的 context window 裡負責閱讀，再把整理過的發現回報回來。這本 notebook 用誠實的方式量測這個拆分：它會在同一個問題上跑現實中的替代方案，也就是一個擁有相同工具、被要求相同驗證標準的 frontier agent，然後比較真實帳單和實際花費的時間。在作者的執行結果裡（那是在 notebook 改用 `multiagent_20261001` type 之前跑的），兩組讀的量差不多，團隊有 84-98% 的 input token 是用 worker 費率計費。

**這本 cookbook 結束時，你會學會：**

- 用 `multiagent` 區塊設定雙模型團隊：frontier orchestrator 加上便宜的 search worker
- 透過 session event stream 即時追蹤一次委派（`thread_created`、`thread_message_sent`、`thread_message_received`）
- 跑一個嚴謹度對齊的 solo-frontier 對照組，比較真實帳單
- 用型別化的每 thread 累計 `usage` 計量每個 thread

同樣的經濟邏輯適用於任何「便宜模型可以負責耗 token 那一段」的工作：文件審閱、log 分析、程式碼全面掃描。


![Architecture of the orchestrator pattern: the user's question goes to a frontier-model orchestrator with no tools of its own; it sends one brief per park to parallel small-model search workers and gets distilled findings back; only the workers touch the open web, via web search and page fetch; the orchestrator synthesizes the final answer.](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/managed_agents/example_data/plan_big_execute_small/architecture_diagram.png)


## 事前準備

開始之前，請確認你具備：

**需要的知識：**
- Python 基礎
- 熟悉 Managed Agents 基本概念：agent、environment、session，以及 streaming event loop（[`CMA_iterate_fix_failing_tests.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_iterate_fix_failing_tests.ipynb) 會把這些都介紹一遍）

**需要的工具：**
- Python 3.11 以上
- Anthropic API key（[在這裡申請](https://console.anthropic.com)），且要有 Managed Agents beta 的存取權

如果你還沒看過 `multiagent` 區塊，可以先看 [multiagent orchestration 文件](https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration)。這本 notebook 用最簡單的團隊，只有一種 worker，因為重點是成本結構，不是團隊設計。

## 設定


```python
%%capture
%pip install -qU "anthropic>=2.0.0" python-dotenv
```

```python
import os
import time

import anthropic
from dotenv import load_dotenv

load_dotenv()

BETAS = ["managed-agents-2026-04-01"]

# The frontier model plans and synthesizes; the cheap model reads the web.
# COOKBOOK_COORDINATOR_MODEL is the older name for the same setting, kept for setups that use it.
ORCHESTRATOR_MODEL = os.environ.get("COOKBOOK_ORCHESTRATOR_MODEL") or os.environ.get(
    "COOKBOOK_COORDINATOR_MODEL", "claude-fable-5-1"
)
WORKER_MODEL = os.environ.get("COOKBOOK_WORKER_MODEL", "claude-sonnet-5-5")

client = anthropic.Anthropic()
```

## 1. 團隊：便宜的閱讀者，貴的思考者

整個團隊只要兩個 agent 定義。

**Worker** 是個普通的 agent：一個模型、縮限到 `web_search` + `web_fetch` 的 toolset，加上 system prompt。文件把它叫 subagent，只要你把它列在 `subagents.predefined_agents`，orchestrator 就能委派工作給它。每個 worker 實例在自己的 session thread 裡研究一個聚焦的子問題，所以它讀的巨大網頁不會進到其他人的 context。

**Orchestrator** 自己沒有任何 tool，只有一個列出 worker 的 `multiagent` 區塊。這個區塊就是讓它能委派的關鍵：server 會自動給它 `create_agent`、`send_to_agent`、`list_agents`，worker 也同樣自動拿到 `send_to_parent`。這些 tool 你都不用自己定義。

這個區塊還關掉兩個 `multiagent_20261001` type 預設開啟的功能：一是 orchestrator 自己定義的 inline agent，二是 workflow run（server 執行 orchestrator 寫的程式，去跑很多 agent 再合併結果）。只要其中一個開著，orchestrator 就可能把工作交給你列出的 worker 以外的 agent，這樣就沒辦法保證這本 notebook 要量測的拆分。把 `subagents.inline_agents` 和 `workflows` 設成 `{"type": "disabled"}`，就能讓所有委派的任務都落在你列的 worker 上。

關於 orchestrator 跟你列的 worker 之間的關係，有兩件事要知道。第一，`predefined_agents` 列表是在 orchestrator 建立或更新時做快照，所以如果你改了 worker 的定義，要更新或重建 orchestrator。第二個比較不明顯：**orchestrator 看不到 worker 的 system prompt**。它的 `create_agent` tool 只吃 agent 名稱和一個 task 字串。Orchestrator 對 worker 行為的所有認知都來自它自己的 system prompt，所以要讓 orchestrator prompt 裡對 worker 的描述，跟 worker 實際的 prompt 保持一致，server 不會幫你檢查。（如果有多種 worker，要在 orchestrator 的 prompt 裡明確寫出名稱。）


```python
worker = client.beta.agents.create(
    name="search-worker",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-plan-big-execute-small"},
    model=WORKER_MODEL,
    # Everything off except the two web tools: the worker's job is
    # reading, and scoping keeps the cheap model from wandering into
    # bash or the filesystem. It's also the security boundary: workers
    # read arbitrary (untrusted) web pages, so a worker that can only
    # search, fetch, and report back is the blast radius you want for
    # that input, and the orchestrator reading the reports is given
    # no tools of its own.
    tools=[
        {
            "type": "agent_toolset_20260401",
            "default_config": {"enabled": False},
            "configs": [
                {"name": "web_search", "enabled": True},
                {"name": "web_fetch", "enabled": True},
            ],
        }
    ],
    system=(
        "You are a search worker researching one focused sub-question for "
        "an orchestrator. Use web_search and web_fetch to find the answer. "
        "Be thorough: try multiple query phrasings, follow promising "
        "links, and cross-check facts across sources. Report back with "
        "the specific answer you found and the evidence (URLs, quotes) "
        "that supports it. If you could not find a definitive answer, say "
        "exactly what you did find and what remains uncertain. Always "
        "finish by calling send_to_parent with your report."
    ),
    betas=BETAS,
)

orchestrator = client.beta.agents.create(
    name="search-orchestrator",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-plan-big-execute-small"},
    model=ORCHESTRATOR_MODEL,
    multiagent={
        "type": "multiagent_20261001",
        "subagents": {
            "type": "enabled",
            # Delegate only to the worker listed here. Inline agents,
            # which the orchestrator would define itself, are on by
            # default and would run on the orchestrator's model.
            "inline_agents": {"type": "disabled"},
            "predefined_agents": [{"type": "agent", "id": worker.id}],
        },
        # Workflow runs are also on by default with multiagent_20261001.
        # Off here, so every delegated task goes to the worker.
        "workflows": {"type": "disabled"},
    },
    system=(
        "You are coordinating a team of search workers to answer a hard "
        "web-research question. Your workers have web_search and "
        "web_fetch; you do not. Break the question into focused "
        "sub-questions and delegate each to a worker via create_agent. "
        "Run several workers in parallel on independent sub-questions, "
        "and do not draw any conclusion until every worker has "
        "reported. When a worker reports, decide whether its "
        "findings answer the sub-question or whether to send a follow-up "
        "with send_to_agent. If a worker returns an infrastructure error "
        "(rate limit, timeout) instead of findings, re-assign the same "
        "sub-question to a fresh worker. Once every worker has reported "
        "and you have enough evidence, synthesize the workers' findings "
        "into a single final answer to the original question."
    ),
    betas=BETAS,
)

print(f"worker       {worker.id}")
print(f"orchestrator {orchestrator.id}")
```

## 2. 跑一個研究問題

幫 orchestrator 建一個 environment 和 session，把問題當成 `user.message` 送出去，然後 stream。Session 層級的 stream 就是 orchestrator 的 primary thread，是整個執行過程的濃縮視圖。Worker thread 會以委派流量的形式出現在裡面：worker 被生出來時是 `session.thread_created`，orchestrator 交給它一個子問題時是 `agent.thread_message_sent`，發現回來時是 `agent.thread_message_received`。

這個問題是個覆蓋型任務：二十個事實（10 個公園 x 2 個屬性），每個都要對照特定的權威來源驗證。覆蓋型問題最能凸顯這個模式，因為閱讀是必要的：沒人能憑記憶回答，所以唯一的問題是閱讀用什麼費率計費，以及是不是平行進行。（探索型問題，也就是在很大的搜尋空間裡找一個藏起來的答案，像 [BrowseComp](https://arxiv.org/abs/2504.12516) 這類 benchmark，比較看重 frontier 模型的搜尋直覺，差距會縮小。）

Fan-out 是看資料決定的：orchestrator 自己決定要生幾個 worker，所以 prompt 裡沒有任何東西限制上限。下面的 session 帶了一個 `budget`，是對整個團隊所有 thread 的 list cost 強制執行的上限。$10 的上限寬鬆到正常執行不會碰到，但萬一某個爛問題讓 orchestrator 無止盡地生 worker，session 會在上限處暫停，而不是把帳單越跑越高。暫停的機制，以及之後怎麼調高上限，寫在 [`CMA_cap_session_spend.ipynb`](CMA_cap_session_spend.md)。

```python
env = client.beta.environments.create(
    name="research-fanout",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
)

session = client.beta.sessions.create(
    agent=orchestrator.id,
    environment_id=env.id,
    # guardrail on data-dependent fan-out: cap the whole team's list cost
    budget={"type": "limit", "max_list_cost": {"currency": "USD", "amount": "1000"}},
    betas=BETAS,
)

QUESTION = (
    "For each of the ten largest national parks in the contiguous United "
    "States by area, find: the current standard private-vehicle entrance "
    "fee, and whether the park currently requires a timed-entry or "
    "day-use reservation for peak season. Each fact must be verified "
    "against that park's official nps.gov pages (fees page and alerts/"
    "reservations page) - not from third-party summaries. Give park, fee, "
    "reservation requirement, and the nps.gov URLs you used."
)

t_start = time.monotonic()

client.beta.sessions.events.send(
    session.id,
    betas=BETAS,
    events=[{"type": "user.message", "content": [{"type": "text", "text": QUESTION}]}],
)


def text_of(content):
    return "".join(b.text for b in content or [] if b.type == "text")


def clip(s, n=160):
    return s[:n] + ("..." if len(s) > n else "")


final_answer = ""
with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        match ev.type:
            case "agent.message":
                if text := text_of(ev.content).strip():
                    final_answer = text
                    print(f"[orchestrator] {clip(text, 200)}")
            case "session.thread_created":
                print(f"[spawn] {ev.agent_name} ({ev.session_thread_id})")
            case "agent.thread_message_sent":
                print(f"[delegate -> {ev.to_agent_name}] {clip(text_of(ev.content))}")
            case "agent.thread_message_received":
                print(f"[report <- {ev.from_agent_name}] {clip(text_of(ev.content))}")
            case "session.status_idle":
                break

print(f"\n[team finished in {time.monotonic() - t_start:.0f}s]")
print("=" * 70)
print(final_answer)
```

要注意的形狀是：每一行 `[delegate ->]` 都是一則小訊息，每一行 `[report <-]` 都是整理過的摘要。產生這些報告的幾 MB 搜尋結果和抓取的網頁，完全沒有進到 orchestrator 的 context。這個分離就是整個成本故事。為了公平定價，下一節會跑現實中的替代方案，然後兩邊都計量。


## 3. 跑對照組：單一 frontier agent，同樣的驗證標準

不用這個模式的話要花多少？現實中的替代方案是單一 frontier agent 加上同樣兩個 web tool。有個細節決定這個比較是公平還是沒意義：**solo agent 必須被要求同樣的驗證標準。** 如果讓 frontier 模型自己判斷，它很節省，每個事實只讀一個來源，成本很低，但那是較低嚴謹度的產品，不是同樣的工作換個價錢。所以下面的 solo prompt 要求團隊已經在做的事：每個事實都要用兩次獨立的 fetch 驗證，有衝突要重新檢查並標記。

同樣的問題，安靜的 stream。


```python
solo = client.beta.agents.create(
    name="solo-researcher",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-plan-big-execute-small"},
    model=ORCHESTRATOR_MODEL,
    tools=[
        {
            "type": "agent_toolset_20260401",
            "default_config": {"enabled": False},
            "configs": [
                {"name": "web_search", "enabled": True},
                {"name": "web_fetch", "enabled": True},
            ],
        }
    ],
    system=(
        "You research hard web questions with audit-grade rigor. Use "
        "web_search and web_fetch. For EVERY fact you report, verify it "
        "from at least two independent fetches (the authoritative page "
        "plus one corroborating source), and re-fetch when two sources "
        "disagree. Never carry a fact forward on one source or from "
        "memory. In your answer, give each fact with both source URLs, "
        "and explicitly flag any fact where sources conflicted. Before "
        "finishing, audit your own answer: list each claim and check it "
        "has two cited sources."
    ),
    betas=BETAS,
)

t_solo = time.monotonic()
solo_session = client.beta.sessions.create(agent=solo.id, environment_id=env.id, betas=BETAS)
client.beta.sessions.events.send(
    solo_session.id,
    betas=BETAS,
    events=[{"type": "user.message", "content": [{"type": "text", "text": QUESTION}]}],
)

solo_answer = ""
with client.beta.sessions.events.stream(solo_session.id, betas=BETAS) as stream:
    for ev in stream:
        match ev.type:
            case "agent.message":
                if text := text_of(ev.content).strip():
                    solo_answer = text
            case "session.status_idle":
                break

print(f"[solo finished in {time.monotonic() - t_solo:.0f}s]")
print(clip(solo_answer, 300))
```

## 4. 計量並計價兩次執行

成本歸屬是 API 內建的。每個 session thread 都帶有累計的 `usage`，session 跟每個 thread 都會回報 `usage.list_cost`：由 server 端用公開牌價算出的 token 成本。列出 thread，取 primary thread（`parent_thread_id is None`）當 orchestrator，子 thread 就是 worker。solo session 就是沒有子 thread。Session 自己的 `list_cost` 就是總額，所以主要數字不用自己維護費率表。

（如果你需要每個 request 的細節，在各 thread 自己的 event feed 裡，session 層級的 feed 只帶 primary thread 的 `span.model_request_end` event。）

API 給不了的一個數字是反事實：這個團隊的工作量如果全用 frontier 費率會收多少。這需要把費率表套到 token 數上，所以程式碼保留了 [pricing 頁面](https://platform.claude.com/docs/en/about-claude/pricing)上的 input、output、cache-read 費率，只用在這個假設情境：5 分鐘 cache write 是 input 費率的 1.25 倍，1 小時 write 是 2 倍，cache read 用各模型的 cache-read 費率；其他真實數字都用 `list_cost`。

```python
# $ / MTok input, output, and cache-read rates from the pricing page,
# used only for the all-frontier counterfactual below; the real bills
# come from the API's server-side list_cost.
PRICES = {
    "claude-fable-5-1": {"input": 10.0, "output": 50.0, "cache_read": 0.25},
    "claude-sonnet-5-5": {"input": 2.0, "output": 10.0, "cache_read": 0.20},
}


def total_input(u):
    cache = u.cache_creation  # None on threads with no cache activity
    return (
        u.input_tokens
        + u.cache_read_input_tokens
        + (cache.ephemeral_5m_input_tokens if cache else 0)
        + (cache.ephemeral_1h_input_tokens if cache else 0)
    )


def counterfactual_cost(u, model):
    """Re-price a thread's tokens at another model's rates (the what-if)."""
    p = PRICES[model]
    cache = u.cache_creation
    return (
        u.input_tokens * p["input"]
        + (cache.ephemeral_5m_input_tokens if cache else 0) * p["input"] * 1.25
        + (cache.ephemeral_1h_input_tokens if cache else 0) * p["input"] * 2.0
        + u.cache_read_input_tokens * p["cache_read"]
        + u.output_tokens * p["output"]
    ) / 1e6


def dollars(list_cost):
    return float(list_cost.amount) / 100  # amount is an integer string in cents


def report(session_id):
    session_usage = client.beta.sessions.retrieve(session_id, betas=BETAS).usage
    threads = list(client.beta.sessions.threads.list(session_id, betas=BETAS))
    primary = next(t for t in threads if t.parent_thread_id is None)
    workers = [t for t in threads if t.parent_thread_id is not None]
    workers_in = sum(total_input(t.usage) for t in workers)
    print(
        f"  primary thread ({primary.agent.model.id}): "
        f"{total_input(primary.usage):>9,} in / {primary.usage.output_tokens:>6,} out"
        f"  -> ${dollars(primary.usage.list_cost):.2f}"
    )
    if workers:
        print(
            f"  {len(workers)} worker(s): {workers_in:>9,} in / "
            f"{sum(t.usage.output_tokens for t in workers):>6,} out"
            f"  -> ${sum(dollars(t.usage.list_cost) for t in workers):.2f}"
        )
        print(
            f"  workers' share of input: {workers_in / (workers_in + total_input(primary.usage)):.0%}"
        )
    total = dollars(session_usage.list_cost)
    print(f"  total cost (session usage.list_cost): ${total:.2f}")
    return total, threads


print("split team (fable orchestrator + sonnet workers):")
split_cost, split_threads = report(session.id)

print("\nsolo frontier agent:")
solo_cost, _ = report(solo_session.id)

# The counterfactual that isolates the rate split: this run's team
# workload with every token billed at the frontier rate.
frontier_team_cost = sum(counterfactual_cost(t.usage, ORCHESTRATOR_MODEL) for t in split_threads)

print(f"\nsolo / split cost ratio on this pair of runs: {solo_cost / split_cost:.1f}x")
print(f"the split team's workload at all-frontier rates: ${frontier_team_cost:.2f}")
```

下面描述的結果來自作者的執行，是在這本 notebook 改用 `multiagent_20261001` type 之前跑的。兩次執行讀的量差不多，這就是對齊驗證標準的意義。差別在閱讀用什麼費率計費，以及工作的形狀：團隊的二十次查詢以平行的 worker thread 用便宜費率跑，而 solo agent 在一個 frontier 計價的 context 裡逐一慢慢處理。在作者的執行中，團隊有 84-98% 的 input token 用 worker 費率計費。Token 量每次都不同，所以任何單次印出的比例都只是一個樣本，穩定的是結構。

四個誠實的提醒，都是做這本 notebook 時實際觀察到的：

* **比較要在嚴謹度對齊的前提下進行。** 讓 solo frontier agent 自己判斷，它讀得少很多（每個事實一個來源），比團隊便宜，但那是不同的、較低嚴謹度的產品。只有在驗證標準固定時，兩組才能比。
* **委派有基本成本。** 每個 worker thread 都要付固定的設置開銷。把同樣的工作拆成更多、更窄的 brief，我們的帳單反而上升，brief 的粒度有最佳點。
* **驗證標準只涵蓋你放進去的東西。** 作者有一次執行中，兩組都對照 nps.gov 驗證了全部二十個事實，但兩組都憑模型記憶建出公園清單，把 Kings Canyon 放進了本來該是 Great Smoky Mountains 的第 10 名（以面積算 Kings Canyon 是第 12）。事實被稽核了，問題的拆解沒有。如果前提很重要，多花一次委派讓 worker 驗證它。
* **Orchestrator 只知道你告訴它的事。** Server 上沒有任何東西讓它看到 worker 的 prompt（見第 1 節），所以成本效益也取決於你在 orchestrator prompt 裡是否準確描述 worker 的行為。

什麼時候這個拆分*不划算*？窄問題的閱讀量太少，沒什麼好套利。如果 orchestrator 用自己的知識回答（沒有委派），你就白付了一趟 frontier 的來回，要留意沒有任何 `[spawn]` 行的執行。另外，如果任務需要 frontier 對原始材料本身做判斷（細微的文件分析，而不是找事實），便宜的閱讀者可能把關鍵內容摘要掉。

## 總結

這份指南裡，你建了最便宜又有用的多 agent 團隊形狀，並量測它換到什麼：

* **設定雙模型團隊**：沒有自己 tool 的 frontier orchestrator，只有列出 worker 的 `multiagent` 區塊，加上限縮在 web tool 的便宜 worker
* **即時追蹤委派**：透過 session stream 上的 `thread_created` / `thread_message_sent` / `thread_message_received`
* **跑嚴謹度對齊的 solo-frontier 對照組**，比較的是真實帳單和實際花費時間，不是估算
* **計量每個 thread**：用每個 session thread 都帶的型別化累計 `usage`（`session.usage` 是整個團隊的總額）

進一步可以做：

1. 加入有限縮 toolset 的專才 worker 類型，[`CMA_coordinate_specialist_team.ipynb`](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_coordinate_specialist_team.ipynb) 示範三個角色的團隊，以及為什麼按角色限縮很重要
2. 把每 thread 的計量放進你的 production telemetry：thread 層級的 usage 讓你能按每次委派歸屬花費，而不只是按 session
3. 在你自己耗 token 的工作量上試同樣的拆分：文件審閱和 log 分類跟網路研究有一樣偏重閱讀、覆蓋型的特性

參考：[multiagent orchestration 文件](https://platform.claude.com/docs/en/managed-agents/multiagent-orchestration)。

## 重點整理

- 很多 agent 工作可以拆成「少量規劃判斷」和「大量機械閱讀」，前者給 frontier 模型，後者給便宜的 worker。
- 成本節省來自 orchestrator 的 context 完全不碰原始網頁，worker 只回報整理過的摘要。
- 比較成本一定要對齊驗證嚴謹度，否則 solo agent 只讀一個來源看起來便宜，但其實是不同的產品。
- 委派有固定開銷，brief 拆得太細反而更貴，而且 orchestrator 看不到 worker 的 prompt，兩邊描述要自己對齊。
- Fan-out 數量由 orchestrator 決定，session 的 `budget` 是防止失控的護欄。

## 練習

1. 把 session 的 `budget` 從 $10 調成很小的數字（例如 $0.5），重跑一次，觀察 session 在哪個時間點暫停。
2. 把 worker 的 system prompt 改成要求「每個事實只讀一個來源」，但不要改 orchestrator 的 prompt，看看 worker 實際行為和 orchestrator 預期不一致時，結果跟 `list_cost` 有什麼變化。
3. 把研究問題從 10 個公園改成 20 個公園（或其他你熟悉的覆蓋型主題），比較 team 跟 solo 的成本差距是否變大，並從每個 thread 的 `usage` 算出平均每個 worker 的花費。
