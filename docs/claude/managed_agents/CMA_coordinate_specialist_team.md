---
translated: true
source: managed_agents/CMA_coordinate_specialist_team.ipynb
---

# Multiagent：協調一支專家團隊

> 原文：[managed_agents/CMA_coordinate_specialist_team.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/managed_agents/CMA_coordinate_specialist_team.ipynb)

透過 multiagent coordinator 設定組成異質團隊：coordinator 指揮三位專家（用 web search 的研究員、讀檔案的資料管理員、依規則計價的定價員），各自只有限定的 toolset，一起組出銷售提案，另外還有一個 advisor 項目，讓 coordinator 在寫作前諮詢。內容涵蓋 multiagent 欄位、thread_created / thread_message_received 事件類型，以及依角色限定 tool。

## 這篇在做什麼

用 Claude Managed Agents 的 multi-agent coordinator 模式，替虛構公司 Northstar 自動寫銷售提案。Coordinator 依序調度研究員、資料管理員、定價員三個 subagent，最後自己組出提案。

## 學完你會

- 用 `multiagent` roster 定義多個專家 subagent，各有自己的 prompt、模型和 toolset。
- 看懂 coordinator 開出的 thread 和事件，並讀出每位專家回傳的內容。
- 理解為什麼要依角色限定 tool，以及 advisor 項目的用途。

## 開跑前

需要 Anthropic API key，並且帳號要能使用 Managed Agents beta。研究員會用到 web search。

我們用 Claude Managed Agents 和 multi-agent coordinator 模式，替一家虛構公司 Northstar 自動寫銷售提案。Northstar 把工作流程自動化平台賣給中型企業的營運團隊。

目前他們的業務要替每個潛在客戶客製提案：研究客戶所屬產業的公司通常重視什麼，從幾百份案例的資料庫挑兩份相關的，依內部規則表試算價格，再組成兩頁的文件。每一步用的資料來源和判斷方式都不同。

我們讓 coordinator agent 指揮三位專家來做。研究員用 web search 找出該產業的典型狀況。資料管理員讀案例庫，挑出最相符的兩份。定價員只看得到規則檔和席位數。Coordinator 負責排定順序並寫出提案。

## 1. 設定 client

先安裝 SDK 並設定 Anthropic client。multiagent 設定和事件類型都屬於 Managed Agents beta。


```python
%%capture
%pip install -qU "anthropic>=0.121.0" python-dotenv
```

```python
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()

BETAS = ["managed-agents-2026-04-01"]
MODEL = os.environ.get("COOKBOOK_MODEL", "claude-opus-5-5")
ADVISOR_MODEL = os.environ.get("COOKBOOK_ADVISOR_MODEL", "claude-opus-5-5")
client = anthropic.Anthropic()
```

## 2. 定義三個專家 subagent

接著建立三位團隊成員。每位有自己的 system prompt、自己的輸出格式，並且只有工作需要的 tool。研究員有 web search，案例挑選者只能讀本機的案例庫，定價員只看得到 `pricing_rules.md` 和席位數。依角色限定 tool，能避免定價員從網路上抓競爭對手的價格，也能讓整個案例庫不會進到 coordinator 的 context。


```python
def make_agent(name, description, system, tools):
    a = client.beta.agents.create(
        name=name,
        description=description,
        # Tells Anthropic which cookbook this agent came from. Safe to remove.
        metadata={"anthropic_cookbook": "claude-cookbooks/cma-coordinate-specialist-team"},
        model=MODEL,
        system=system,
        tools=tools,
        betas=BETAS,
    )
    print(f"{name}: {a.id}")
    return a.id


prospect_researcher = make_agent(
    "prospect_researcher",
    "Researches what companies in a given industry segment and size tier typically prioritize.",
    """Given a prospect's industry and size, use web search to find:
- What companies in that segment typically list as strategic priorities
- Recent trends or pressures in that industry
- Common operational pain points at that scale
Return via send_to_parent: {"priorities": [...], "recent_moves": [...], "pain_points": [...], "sources": [...]}""",
    [
        {
            "type": "agent_toolset_20260401",
            "configs": [{"name": "web_search"}, {"name": "web_fetch"}],
        }
    ],
)

case_study_picker = make_agent(
    "case_study_picker",
    "Selects the two most relevant case studies from the library for a given prospect profile.",
    """The case study library is in /mnt/user-data/case_studies/. Each file is one customer story.
You will be given a prospect's industry, size, and top priorities. Read the library, score each study on relevance, and pick the two best matches.
Return via send_to_parent: {"picks": [{"file": ..., "customer": ..., "why_relevant": ...}, ...]}""",
    [{"type": "agent_toolset_20260401"}],
)

pricing_modeler = make_agent(
    "pricing_modeler",
    "Builds two or three pricing options for a prospect based on seat count and expected usage.",
    """Pricing rules are in /mnt/user-data/pricing_rules.md. Given a prospect's estimated seat count and usage tier, build:
- a conservative option (annual commit, lower per-seat)
- a flexible option (monthly, higher per-seat)
- if seat count > 500, an enterprise option with a platform fee
Show the first-year total for each. Return via send_to_parent: {"options": [{"name": ..., "structure": ..., "year_one_total": ...}, ...]}""",
    [{"type": "agent_toolset_20260401"}],
)
```

## 3. 給團隊準備素材

資料管理員需要一個案例庫可以挑。我們準備七份簡短的案例，涵蓋醫療、製造、物流、零售、金融科技和公部門，讓你看到它真的挑出符合我們潛在客戶的那兩份。


```python
CASE_STUDIES = [
    {
        "slug": "stclair_health",
        "title": "St. Clair Health",
        "industry": "regional hospital network",
        "employees": 6200,
        "summary": """Challenge: credentialing and prior-auth workflows spread across 11 systems.
Result with Northstar: consolidated to 3 automated workflows; prior-auth turnaround down 58%; $1.9M annual labor savings.""",
    },
    {
        "slug": "blueridge_health_plan",
        "title": "BlueRidge Health Plan",
        "industry": "regional payer",
        "employees": 2800,
        "summary": """Challenge: claims-adjudication exceptions queued in email; 19% required manual rework.
Result with Northstar: exception routing automated end-to-end; rework rate down to 6%; 11-day faster average claim resolution.""",
    },
    {
        "slug": "calder_mfg",
        "title": "Calder Manufacturing",
        "industry": "industrial",
        "employees": 3100,
        "summary": """Challenge: purchase-order approvals averaging 9 days.
Result with Northstar: PO cycle time cut to 2.1 days; 14% reduction in maverick spend.""",
    },
    {
        "slug": "northwind",
        "title": "Northwind Logistics",
        "industry": "3PL",
        "employees": 4400,
        "summary": """Challenge: carrier-onboarding paperwork took 3 weeks per carrier.
Result with Northstar: onboarding down to 4 days; 22% more carriers activated in Q1.""",
    },
    {
        "slug": "harborview_retail",
        "title": "Harborview Retail Group",
        "industry": "specialty retail",
        "employees": 5600,
        "summary": """Challenge: store-level inventory exceptions handled by regional managers over Slack and spreadsheets.
Result with Northstar: exception triage automated across 140 stores; stockout incidents down 31%.""",
    },
    {
        "slug": "aperture_fintech",
        "title": "Aperture Payments",
        "industry": "fintech",
        "employees": 1900,
        "summary": """Challenge: KYC and merchant-onboarding reviews averaging 6 business days.
Result with Northstar: review SLA cut to 36 hours; onboarding throughput up 2.4x with the same team.""",
    },
    {
        "slug": "summit_county",
        "title": "Summit County Government",
        "industry": "public sector",
        "employees": 3700,
        "summary": """Challenge: building-permit applications routed through five departments by paper packet.
Result with Northstar: single digital intake with parallel department review; median permit time 41 to 17 days.""",
    },
]
```

### 產品與定價資料

我們也提供產品一頁式簡介（coordinator 寫「How we help」段落時會讀），以及定價規則檔（定價員用來建立方案選項）。


```python
PRODUCT = """# Northstar Platform — One-Pager
Northstar is a workflow automation platform for mid-market operations teams.
Core capabilities: visual process builder, 200+ SaaS connectors, role-based approvals, SOC 2 Type II.
Typical results: 40-60% reduction in manual ticket handling, 3-week time-to-first-workflow."""

PRICING = """# Pricing Rules (internal)
- Per-seat list: $65/mo (monthly) or $52/mo (annual commit).
- Usage tiers: light = 1.0x, standard = 1.15x, heavy = 1.30x multiplier on per-seat.
- Enterprise (>500 seats): add $48,000/yr platform fee, per-seat drops to $44/mo annual.
- All options include onboarding; enterprise includes a named CSM."""
```

### 接上 coordinator 並開始 session

現在建立 environment、上傳九個檔案，並建立 coordinator，帶著包含三位專家的 `multiagent` roster。每個項目都是完整的 agent，有自己的模型、prompt 和 toolset，所以你可以依角色混用不同等級的模型。

Roster 裡還有一個不是 agent 的項目：`{"type": "advisor", "model": ...}` 指定一個更強的模型，coordinator 可以在回合中途諮詢它。它沒有 tool，也不能被 spawn 或傳訊息。Coordinator 呼叫它的 `advisor` tool，平台會把目前為止的對話給那個模型看，建議再回到這個回合裡。這裡它會在寫作前檢查案例挑選和定價的說法是否合理。完整模式見 [`CMA_consult_an_advisor.ipynb`](CMA_consult_an_advisor.md)。


```python
env = client.beta.environments.create(
    name="proposal-meridian",
    config={"type": "anthropic_cloud", "networking": {"type": "unrestricted"}},
)

resources = []


def mount(path, content):
    f = client.beta.files.upload(file=(os.path.basename(path), content.encode(), "text/plain"))
    resources.append({"type": "file", "file_id": f.id, "mount_path": path})


for cs in CASE_STUDIES:
    body = f"# {cs['title']} ({cs['industry']}, {cs['employees']:,} employees)\n{cs['summary']}"
    mount(f"/mnt/user-data/case_studies/{cs['slug']}.md", body)
mount("/mnt/user-data/product_one_pager.md", PRODUCT)
mount("/mnt/user-data/pricing_rules.md", PRICING)

coordinator = client.beta.agents.create(
    name="Proposal Writer",
    # Tells Anthropic which cookbook this agent came from. Safe to remove.
    metadata={"anthropic_cookbook": "claude-cookbooks/cma-coordinate-specialist-team"},
    model=MODEL,
    system="""You assemble tailored sales proposals.
Given a prospect name and basic profile:
1. Send the prospect's industry and size to prospect_researcher.
2. Send the prospect's industry, size, and (once the researcher reports back) their priorities to case_study_picker.
3. Send the seat count and usage tier to pricing_modeler.
4. Before writing, consult your advisor to check the case-study picks and the pricing framing against the prospect's priorities.
5. Read /mnt/user-data/product_one_pager.md, then write /mnt/session/outputs/proposal.md with sections:
   Executive summary (tied to their priorities), How we help (from the one-pager),
   Proof (the two case studies), Investment (the pricing options), Next steps.
Keep it to two pages.""",
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "coordinator",
        "agents": [
            prospect_researcher,
            case_study_picker,
            pricing_modeler,
            # a stronger model the coordinator can consult mid-turn
            {"type": "advisor", "model": ADVISOR_MODEL},
        ],
    },
    betas=BETAS,
)

session = client.beta.sessions.create(
    agent={"type": "agent", "id": coordinator.id, "version": coordinator.version},
    environment_id=env.id,
    resources=resources,
    title="Proposal: Meridian Health",
    betas=BETAS,
)
print(f"Session {session.id} ready with {len(resources)} files mounted")
```

## 4. 啟動提案流程

送出潛在客戶的資料，看 coordinator 怎麼運作。它會同時啟動研究員和定價員，等研究員的發現回來後再跑案例挑選者，因為挑選者需要那些重點來評分相關度。寫作之前，它會諮詢 advisor，在 stream 上會顯示成一個短暫存在的 `anthropic.advisor` thread。


```python
PROSPECT = {
    "name": "Meridian Health",
    "industry": "regional healthcare system",
    "employees": 8500,
    "estimated_seats": 600,
    "usage_tier": "heavy",
}

client.beta.sessions.events.send(
    session.id,
    betas=BETAS,
    events=[
        {
            "type": "user.message",
            "content": [
                {
                    "type": "text",
                    "text": f"Build a proposal for {PROSPECT['name']}, a {PROSPECT['industry']} with "
                    f"~{PROSPECT['employees']} employees. Estimate {PROSPECT['estimated_seats']} seats "
                    f"at {PROSPECT['usage_tier']} usage. Write to /mnt/session/outputs/proposal.md.",
                }
            ],
        }
    ],
)

with client.beta.sessions.events.stream(session.id, betas=BETAS) as stream:
    for ev in stream:
        if ev.type == "session.thread_created":
            print(f"[spawn] {ev.agent_name}")
        elif ev.type == "agent.thread_message_received":
            if ev.from_agent_name == "anthropic.advisor":
                print("[advice] advisor guidance received")
            else:
                print(f"[report] {ev.from_agent_name} returned")
        elif ev.type == "session.status_idle":
            print("[done]")
            break
```

### 每位成員回傳了什麼

在看組好的提案之前，先印出三份原始的 `send_to_parent` payload，加上 advisor 的建議。每個 subagent 都在自己的 context 裡、只用自己的 tool 跑，所以三份報告看起來差很多；advisor 那一塊就是 coordinator 在寫作前要求的合理性檢查。


```python
def text_of(content):
    return "".join(b.text for b in content if b.type == "text")


for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS):
    if ev.type == "agent.thread_message_received":
        body = text_of(ev.content) or "[redacted]"  # advisor content can be withheld
        label = (
            "advisor guidance"
            if ev.from_agent_name == "anthropic.advisor"
            else f"send_to_parent from {ev.from_agent_name}"
        )
        print(f"━━━ {label} ({len(body)} chars) ━━━")
        print(body[:1200] + (f"\n…[{len(body) - 1200} more chars]" if len(body) > 1200 else ""))
        print()
```

## 5. 讀提案

最後把組好的提案取出來。Coordinator 用 `write` tool 把它寫到 `proposal.md`，所以我們從 log 裡找到那個事件，看它產出的各個段落。想讀完整文件的話，可以直接印出 `proposal`。

```python
proposal = ""
for ev in client.beta.sessions.events.list(session.id, limit=1000, betas=BETAS):
    if (
        ev.type == "agent.tool_use"
        and ev.name == "write"
        and ev.input["file_path"].endswith("proposal.md")
    ):
        proposal = ev.input["content"]
        break

# Show the section structure rather than the full proposal.
for line in proposal.splitlines():
    if line.startswith("#"):
        print(line)
```

## 為什麼用三個 subagent 而不是一個

一個擁有三種 tool 的 agent 也寫得出這份提案，為什麼要拆開？每個角色只有自己的 tool，所以定價員拿不到網路上的競爭對手牌價，因為它只有規則檔。案例挑選者這裡只讀七個檔案，但在 production 可能要讀幾百個，這些量會留在 subagent 的 context 裡，不會塞進 coordinator 的。而 coordinator 可以決定順序和交接方式，不必自己做任何專家的工作。

更多 multi-agent 協調的內容，見 [Managed Agents 文件](https://platform.claude.com/docs/en/managed-agents/multi-agent)。


## 重點整理
- Coordinator 模式把任務拆給各有專長的 subagent，coordinator 只管順序和交接。
- 每個 subagent 有自己的 prompt、模型和 toolset，可以混用不同等級的模型。
- 依角色限定 tool 有兩個好處：避免越權取得資料，也讓大量資料留在 subagent 的 context。
- Advisor 是 roster 裡不是 agent 的項目，讓 coordinator 在回合中途諮詢更強的模型。
- 沒有相依關係的專家可以平行跑，有相依的（例如挑案例要用研究結果）要排先後。

## 練習
1. 在案例庫多加一份案例，確認資料管理員的挑選結果有沒有變。
2. 把定價規則檔改一條規則，看提案裡的定價選項跟著怎麼變。
3. 給定價員多加一個 tool（例如 web search），觀察它是否開始引用外部價格，再決定要不要拿掉。
