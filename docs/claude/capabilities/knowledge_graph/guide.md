---
translated: true
source: capabilities/knowledge_graph/guide.ipynb
---

# 用 Claude 建構 knowledge graph

> 原文：[capabilities/knowledge_graph/guide.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/capabilities/knowledge_graph/guide.ipynb)

用 Claude 從非結構化文字建 knowledge graph：擷取 entity、挖掘 relation、去重，再做 multi-hop 的圖查詢。

## 這篇在做什麼

拿六篇 Apollo 計畫的 Wikipedia 摘要，只靠 prompt 走完整條 knowledge graph pipeline：擷取 entity 和 triple、用 Claude 做 entity resolution、組成 NetworkX 圖、再做摘要和 multi-hop 查詢。最後用 gold set 量化品質。

## 學完你會

- 用 structured outputs（Pydantic 加 `client.messages.parse()`）從任意文字擷取有型別的 entity 和 subject–predicate–object triple，不需要訓練資料
- 用 Claude 把不同寫法的 entity 合併成 canonical 節點，取代脆弱的字串相似度 heuristic
- 組出並查詢圖，把子圖序列化給 Claude 回答 multi-hop 問題，並用 precision/recall 評估品質

## 開跑前

- Python 3.11 以上
- Anthropic API key
- 範例會從 Wikipedia REST API 抓資料，需要能連網

你手上有一堆非結構化文件，要回答跨文件的問題，像「誰跟做過專案 X 的人合作過」、「哪些供應商跟這次事故有關」。沒有任何單一文件含有答案，RAG 檢索也不會幫你把事實串起來。你需要 knowledge graph：**entity** 當節點，**有型別的 relation** 當邊，讓 multi-hop 推理變成圖的走訪。

以前建一個得在你的領域訓練 named-entity recognizer、訓練 relation classifier、寫 entity-resolution heuristic，資料一變三樣都要維護。有了 Claude，這三個階段都變成一個 prompt。

## 你會學到

做完這份指南，你可以：

- 用 **structured outputs** 從任意文字擷取有型別的 entity 和 subject–predicate–object triple，不需要訓練資料
- 用 **Claude 驅動的 entity resolution**，把不同寫法的變體合併成 canonical 節點，取代脆弱的字串相似度 heuristic
- 組出並查詢記憶體內的圖，把子圖序列化回 Claude 來做 **multi-hop 問題**
- 用 **對照 gold set 的 precision/recall** 衡量擷取品質，並思考 Haiku 和 Sonnet 之間的成本與品質取捨

全部在記憶體裡跑，不用資料庫。需要擴充時，這些技巧可以直接搬到 Neo4j、Neptune 或 Postgres adjacency table。

## 前置條件
- Python 3.11 以上
- Anthropic API key（[在這裡申請](https://console.anthropic.com)）
- 對圖有基本概念（節點、邊、走訪）

## 設定

```python
%%capture
%pip install anthropic requests networkx matplotlib python-dotenv pydantic
```

```python
import json
from collections import defaultdict
from pathlib import Path
from typing import Literal
from urllib.parse import quote

import anthropic
import matplotlib.pyplot as plt
import networkx as nx
import requests
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()
client = anthropic.Anthropic()

EXTRACTION_MODEL = "claude-haiku-5-5"
SYNTHESIS_MODEL = "claude-sonnet-5-5"
```

我們用兩個模型。Haiku 負責大量、有 schema 限制的擷取工作，這時速度和成本比細膩度重要。Sonnet 負責 entity resolution 和摘要，因為模型要在跨文件的互相矛盾證據間做權衡。

## 建立語料

我們需要幾篇提到重疊 entity 的文件，entity resolution 才有事可做。Apollo 計畫是很好的測試場：六篇簡短的 Wikipedia 摘要，都提到 NASA、月球、幾位太空人和一種運載火箭，但每篇的稱呼都略有不同。

我們從 Wikipedia REST API 抓摘要而不是全文，以降低 token 成本。production pipeline 會把完整文件切 chunk，擷取邏輯是一樣的。

```python
ARTICLE_TITLES = [
    "Apollo program",
    "Apollo 11",
    "Neil Armstrong",
    "Saturn V",
    "Buzz Aldrin",
    "Kennedy Space Center",
]

WIKI_API = "https://en.wikipedia.org/api/rest_v1/page/summary/"
HEADERS = {"User-Agent": "claude-cookbooks/1.0 (https://github.com/anthropics/claude-cookbooks)"}


def fetch_summary(title: str) -> str:
    slug = quote(title.replace(" ", "_"), safe="")
    r = requests.get(WIKI_API + slug, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()["extract"]


documents = []
for i, title in enumerate(ARTICLE_TITLES):
    try:
        documents.append({"id": i, "title": title, "text": fetch_summary(title)})
    except requests.RequestException as e:
        print(f"Skipping {title}: {e}")

if not documents:
    raise RuntimeError("No documents loaded — check network and Wikipedia API availability")
print(f"Loaded {len(documents)} documents\n")
print(f"Sample — {documents[0]['title']}:\n{documents[0]['text'][:300]}...")
```

??? note "輸出"

    ```text
    Loaded 6 documents

    Sample — Apollo program:
    The Apollo program, also known as Project Apollo, was the United States human spaceflight program led by NASA, which landed the first humans on the Moon in 1969. The Apollo program was conceived in 1960 in the Dwight D. Eisenhower presidency during Project Mercury and executed after Project Gemini. ...
    ```

## Entity 與 relation 擷取

傳統 NER 會把文字片段標上標籤（PERSON、ORG、LOC），傳統 relation extraction 再把片段配對分類成 relation 類型。兩者通常都要每個領域各自的標註訓練資料。

我們把兩個階段合併成每份文件一次 Claude 呼叫。關鍵是 **structured outputs**：用 Pydantic model 定義輸出的形狀，傳給 `client.messages.parse()`。Claude 的回應保證符合該 schema，回來就是有型別的 Python 物件，不用 regex 解析、不會有 JSON decode 錯誤、也不用一堆防禦性的 `isinstance` 檢查。

```python
EntityType = Literal["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "ARTIFACT"]
ENTITY_TYPES = ["PERSON", "ORGANIZATION", "LOCATION", "EVENT", "ARTIFACT"]


class Entity(BaseModel):
    name: str
    type: EntityType
    description: str


class Relation(BaseModel):
    source: str
    predicate: str
    target: str


class ExtractedGraph(BaseModel):
    entities: list[Entity]
    relations: list[Relation]


EXTRACTION_PROMPT = """Extract a knowledge graph from the document below.

<document>
{text}
</document>

Guidelines:
- Extract only entities that are central to what this document is about — skip incidental mentions.
- For each entity, write a one-sentence description grounded in this document. These descriptions are used later to disambiguate entities with similar names.
- Predicates should be short verb phrases ("commanded", "launched from", "part of").
- Every relation must connect two entities you extracted."""


def extract(text: str) -> ExtractedGraph:
    response = client.messages.parse(
        model=EXTRACTION_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}],
        output_format=ExtractedGraph,
    )
    return response.parsed_output
```

```python
raw_entities = []
raw_relations = []

for doc in documents:
    try:
        result = extract(doc["text"])
    except anthropic.APIError as e:
        print(f"Skipping {doc['title']}: {e}")
        continue
    for ent in result.entities:
        raw_entities.append({**ent.model_dump(), "source_doc": doc["title"]})
    for rel in result.relations:
        raw_relations.append({**rel.model_dump(), "source_doc": doc["title"]})
    print(
        f"{doc['title']:<25} {len(result.entities):>3} entities  {len(result.relations):>3} relations"
    )

print(f"\nTotal: {len(raw_entities)} raw entities, {len(raw_relations)} raw relations")
```

??? note "輸出"

    ```text
    Apollo program              7 entities    6 relations
    Apollo 11                   7 entities    6 relations
    Neil Armstrong              3 entities    3 relations
    Saturn V                    6 entities    6 relations
    Buzz Aldrin                 8 entities   10 relations
    Kennedy Space Center        9 entities   13 relations

    Total: 40 raw entities, 44 raw relations
    ```

看看擷取到什麼。注意同一個真實世界的 entity 在不同文件裡以不同寫法出現，這就是下一步要解的 entity resolution 問題。

```python
by_type = defaultdict(list)
for e in raw_entities:
    by_type[e["type"]].append(e["name"])

for etype, names in sorted(by_type.items()):
    print(f"{etype} ({len(names)}):")
    for name in sorted(set(names)):
        print(f"  {name}")
    print()
```

??? note "輸出"

    ```text
    ARTIFACT (3):
      Lunar Module Eagle
      Saturn V
      Skylab

    EVENT (13):
      Apollo
      Apollo 11
      Apollo program
      Artemis
      Gemini 12
      Project Gemini
      Project Mercury
      Skylab
      Space Shuttle

    LOCATION (9):
      Cape Canaveral Space Force Station
      Kennedy Space Center Launch Complex 39
      Merritt Island
      Moon

    ORGANIZATION (6):
      John F. Kennedy Space Center
      NASA

    PERSON (9):
      Buzz Aldrin
      Dwight D. Eisenhower
      Edwin Aldrin
      John F. Kennedy
      Michael Collins
      Neil Armstrong
    ```

## Entity resolution

原始擷取結果有重疊的 mention：「NASA」和「National Aeronautics and Space Administration」、「Neil Armstrong」和「Armstrong」，可能還有「the Moon」和「Moon」。直接拿這些建圖，同一個概念會被拆在互不相連的節點上，一團亂。

傳統做法是字串相似度（edit distance、token 的 Jaccard）加 blocking 規則。這對打字錯誤有效，但對「Edwin Aldrin」和「Buzz Aldrin」就沒用，這兩個名字沒有任何字元重疊，卻是同一個人。

我們改成請 Claude 對每種類型的 entity 分群，用擷取時的一行描述當消歧的 context。描述很重要：「Armstrong，第一個在月球上行走的人」和「Armstrong，爵士小號手」名字相同，但不該合併。

```python
class Cluster(BaseModel):
    canonical: str
    aliases: list[str]


class ResolvedClusters(BaseModel):
    clusters: list[Cluster]


RESOLVE_PROMPT = """Below are {entity_type} entities extracted from several documents. Some are different surface forms of the same real-world entity.

<entities>
{entity_list}
</entities>

Cluster them. Each input name must appear in exactly one cluster's aliases list. Entities that are genuinely distinct get their own single-element cluster. Use the descriptions to avoid merging entities that merely share a name. The canonical name should be the most complete, unambiguous form."""


def resolve(entity_type: str, entities: list[dict]) -> list[Cluster]:
    unique = {}
    for e in entities:
        unique.setdefault(e["name"], e["description"])
    entity_list = "\n".join(f"- {name}: {desc}" for name, desc in unique.items())

    response = client.messages.parse(
        model=SYNTHESIS_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": RESOLVE_PROMPT.format(entity_type=entity_type, entity_list=entity_list),
            }
        ],
        output_format=ResolvedClusters,
    )
    return response.parsed_output.clusters
```

有兩種失敗模式要留意。第一，Claude 沒放進任何 cluster 的原始名稱，會悄悄從圖裡消失，因為 `alias_to_canonical` 沒有它的條目。production 的 resolver 應該對沒配對到的名稱退回成單一元素的 cluster，才不會漏掉東西。第二，resolver 可能 **over-merge**：像「Gemini 12」這種特定任務，可能因為描述重疊被併進比較大的「Project Gemini」。前者掉節點，後者掉精準度，都值得在下面的輸出裡抽查。

```python
alias_to_canonical = {}
canonical_info = {}

for etype in ENTITY_TYPES:
    entities_of_type = [e for e in raw_entities if e["type"] == etype]
    if not entities_of_type:
        continue
    try:
        clusters = resolve(etype, entities_of_type)
    except anthropic.APIError as e:
        print(f"Resolve failed for {etype}: {e}; treating each name as its own cluster")
        clusters = [
            Cluster(canonical=n, aliases=[n]) for n in {x["name"] for x in entities_of_type}
        ]
    for cluster in clusters:
        canonical_info[cluster.canonical] = {"type": etype, "aliases": cluster.aliases}
        for alias in cluster.aliases:
            alias_to_canonical[alias] = cluster.canonical

before = len({e["name"] for e in raw_entities})
after = len(canonical_info)
print(f"Entity resolution: {before} unique names → {after} canonical entities\n")

for canonical, info in sorted(canonical_info.items()):
    aliases = [a for a in info["aliases"] if a != canonical]
    alias_str = f"  (also: {', '.join(aliases)})" if aliases else ""
    print(f"{info['type']:<14} {canonical}{alias_str}")
```

??? note "輸出"

    ```text
    Entity resolution: 23 unique names → 21 canonical entities

    EVENT          Apollo 11
    EVENT          Apollo program  (also: Apollo)
    EVENT          Artemis
    PERSON         Buzz Aldrin  (also: Edwin Aldrin)
    LOCATION       Cape Canaveral Space Force Station
    PERSON         Dwight D. Eisenhower
    EVENT          Gemini 12
    PERSON         John F. Kennedy
    ORGANIZATION   John F. Kennedy Space Center
    LOCATION       Kennedy Space Center Launch Complex 39
    ARTIFACT       Lunar Module Eagle
    LOCATION       Merritt Island
    PERSON         Michael Collins
    LOCATION       Moon
    ORGANIZATION   NASA
    PERSON         Neil Armstrong
    EVENT          Project Gemini
    EVENT          Project Mercury
    ARTIFACT       Saturn V
    ARTIFACT       Skylab
    EVENT          Space Shuttle
    ```

## 組裝圖

有了乾淨的 alias map，我們把每個 relation 的端點改寫成 canonical 名稱，再載入 NetworkX。用 `MultiDiGraph` 是因為兩個 entity 之間可能有好幾種不同的 predicate（「launched from」和「operated by」），而且方向有意義（「Armstrong commanded Apollo 11」和「Apollo 11 commanded Armstrong」不是同一條邊）。

每個節點帶有它的類型、提到它的文件集合和 mention 次數。每條邊帶有 predicate 和來源文件。

```python
G = nx.MultiDiGraph()

for e in raw_entities:
    canonical = alias_to_canonical.get(e["name"])
    if canonical is None:
        continue
    if canonical not in G:
        G.add_node(
            canonical,
            type=canonical_info[canonical]["type"],
            description=e["description"],
            source_docs=[],
            mentions=0,
        )
    G.nodes[canonical]["source_docs"].append(e["source_doc"])
    G.nodes[canonical]["mentions"] += 1

for r in raw_relations:
    src = alias_to_canonical.get(r["source"])
    tgt = alias_to_canonical.get(r["target"])
    if src and tgt and src != tgt:
        G.add_edge(src, tgt, predicate=r["predicate"], source_doc=r["source_doc"])

for n in G.nodes:
    G.nodes[n]["source_docs"] = sorted(set(G.nodes[n]["source_docs"]))

print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
print(f"Connected components: {nx.number_weakly_connected_components(G)}")
print("\nMost connected entities:")
for node, deg in sorted(G.degree(), key=lambda x: -x[1])[:5]:
    print(f"  {node:<35} degree {deg:>2}  ({G.nodes[node]['type']})")
```

??? note "輸出"

    ```text
    Graph: 21 nodes, 44 edges
    Connected components: 1

    Most connected entities:
      Apollo 11                           degree 12  (EVENT)
      Apollo program                      degree 11  (EVENT)
      John F. Kennedy Space Center        degree  9  (ORGANIZATION)
      Moon                                degree  7  (LOCATION)
      NASA                                degree  6  (ORGANIZATION)
    ```

```python
COLOR = {
    "PERSON": "#4e79a7",
    "ORGANIZATION": "#f28e2c",
    "LOCATION": "#76b7b2",
    "EVENT": "#e15759",
    "ARTIFACT": "#af7aa1",
}

plt.figure(figsize=(14, 10))
pos = nx.spring_layout(G, k=1.5, seed=42)
node_colors = [COLOR[G.nodes[n]["type"]] for n in G.nodes]
node_sizes = [300 + 200 * G.degree(n) for n in G.nodes]

nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=node_sizes, alpha=0.9)
nx.draw_networkx_labels(G, pos, font_size=8)
nx.draw_networkx_edges(G, pos, alpha=0.3, arrows=True, arrowsize=10)

handles = [
    plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=10, label=t)
    for t, c in COLOR.items()
    if any(G.nodes[n]["type"] == t for n in G.nodes)
]
plt.legend(handles=handles, loc="upper left")
plt.title("Apollo Program Knowledge Graph")
plt.axis("off")
plt.tight_layout()
plt.show()
```

節點大小對應 degree，hub 就是把整個語料串起來的 entity。顏色代表類型：如果圖大多是同一種顏色，表示語料範圍窄；顏色分布均勻，代表擷取器找到了完整的人、地、物。只有一個連通分量，表示 entity resolution 做對了；如果出現零散的孤島，就是本該合併卻沒合併的變體。

## Entity 摘要

目前每個節點只有最早提到它的那份文件裡的一行描述。對 hub 節點（出現在很多文件裡的那些）可以做得更好：把每次 mention 集合起來，加上圖的鄰域當 context，讓 Claude 合成一份完整的檔案。

這一步讓一張標籤的圖變成一張知識的圖。這些摘要就是你放進搜尋結果、或餵給下游 QA 的節點內容。

```python
class TimeRange(BaseModel):
    start: str  # YYYY or YYYY-MM, or "unknown"
    end: str  # YYYY or YYYY-MM, or "ongoing"


class EntityProfile(BaseModel):
    summary: str
    key_facts: list[str]
    time_range: TimeRange


SUMMARIZE_PROMPT = """Generate a knowledge-graph profile for this entity.

Entity: {name} ({etype})

Source excerpts mentioning this entity:
{excerpts}

Known relations in the graph:
{relations}

Write a 2-3 paragraph factual summary synthesized from the excerpts, resolving any contradictions by preferring the most specific claim. Include 3-5 atomic key facts, each traceable to the sources. For the time range, use YYYY or YYYY-MM format, or "unknown"/"ongoing" where appropriate. Do not invent facts not supported by the excerpts."""


def summarize_entity(name: str) -> EntityProfile:
    # Reads module-level G and documents built earlier in the notebook.
    docs_with_entity = G.nodes[name]["source_docs"]
    excerpts = "\n\n".join(
        f"[{d['title']}]\n{d['text']}" for d in documents if d["title"] in docs_with_entity
    )
    relations = (
        "\n".join(
            f"- {name} --{d['predicate']}--> {tgt}" for _, tgt, d in G.out_edges(name, data=True)
        )
        + "\n"
        + "\n".join(
            f"- {src} --{d['predicate']}--> {name}" for src, _, d in G.in_edges(name, data=True)
        )
    )

    response = client.messages.parse(
        model=SYNTHESIS_MODEL,
        max_tokens=4096,
        messages=[
            {
                "role": "user",
                "content": SUMMARIZE_PROMPT.format(
                    name=name, etype=G.nodes[name]["type"], excerpts=excerpts, relations=relations
                ),
            }
        ],
        output_format=EntityProfile,
    )
    return response.parsed_output
```

```python
hub_nodes = [n for n, _ in sorted(G.degree(), key=lambda x: -x[1])[:3]]

for node in hub_nodes:
    profile = summarize_entity(node)
    G.nodes[node]["profile"] = profile.model_dump()
    print(f"═══ {node} ═══")
    print(profile.summary)
    print(f"\nTime range: {profile.time_range.start} – {profile.time_range.end}")
    print("Key facts:")
    for fact in profile.key_facts:
        print(f"  • {fact}")
    print()
```

??? note "輸出"

    ```text
    ═══ Apollo 11 ═══
    Apollo 11 was the American spaceflight that first landed humans on the Moon. It was the fifth crewed mission of NASA's Apollo program, conducted by NASA, and took place in 1969. The Lunar Module Eagle was part of the mission. The crew was Commander Neil Armstrong, Command Module Pilot Michael Collins, and Lunar Module Pilot Edwin Buzz Aldrin. All three were on their second and final spaceflight. Armstrong became the first person to walk on the Moon, and Aldrin was the second. Aldrin had earlier made three spacewalks on NASA's 1966 Gemini 12 mission. Armstrong died in 2012 and Collins in 2021, which leaves Aldrin as the last surviving Apollo 11 crew member and the oldest living astronaut.

    Time range: 1969 – 1969
    Key facts:
      • Apollo 11 was the first spaceflight to land humans on the Moon.
      • Apollo 11 was the fifth crewed mission of NASA's Apollo program.
      • The crew was Neil Armstrong (Commander), Michael Collins (Command Module Pilot) and Buzz Aldrin (Lunar Module Pilot), each on their second and final spaceflight.
      • Neil Armstrong, commander of Apollo 11, became the first person to walk on the Moon, followed by Buzz Aldrin as the second.
      • Aldrin is the last surviving Apollo 11 crew member following the deaths of Armstrong in 2012 and Collins in 2021.

    ═══ Apollo program ═══
    The Apollo program, also known as Project Apollo, was the United States human spaceflight program led by NASA. It landed the first humans on the Moon in 1969. It was conceived in 1960 during the Eisenhower presidency, while Project Mercury was under way, and was executed after Project Gemini. It was later dedicated to President John F. Kennedy's goal, stated in his May 25, 1961 address to Congress, of landing a man on the Moon and returning him safely to the Earth before the decade was out.

    Apollo 11 was the first mission to land humans on the Moon and the fifth crewed mission of the program. Its crew was Neil Armstrong, Michael Collins and Edwin "Buzz" Aldrin. The Saturn V, a three-stage, liquid-fueled, human-rated super heavy-lift rocket, was developed under the program for lunar exploration. Nine of the thirteen Saturn V launches sent 24 astronauts toward the Moon, from Apollo 8 to Apollo 17.

    Launch operations for Apollo were carried out from Kennedy Space Center Launch Complex 39 and managed by the Kennedy Space Center on Merritt Island, Florida. The sources do not state an exact end date for the program.

    Time range: 1960 – unknown
    Key facts:
      • The Apollo program was the U.S. human spaceflight program led by NASA, and it landed the first humans on the Moon in 1969.
      • The program was conceived in 1960 during the Eisenhower presidency and executed after Project Gemini.
      • Apollo 11, crewed by Neil Armstrong, Michael Collins and Buzz Aldrin, was the fifth crewed Apollo mission and the first to land humans on the Moon.
      • The Saturn V rocket was developed under the Apollo program, and nine of its thirteen launches carried 24 astronauts toward the Moon from Apollo 8 to Apollo 17.
      • Apollo launch operations were carried out from Kennedy Space Center Launch Complex 39 and managed by the Kennedy Space Center.

    ═══ John F. Kennedy Space Center ═══
    The John F. Kennedy Space Center (KSC) is one of the ten field centers of NASA. It is located on Merritt Island, on the east coast of Florida. Since 1968, KSC has served as NASA's primary launch center for American spaceflight, research, and technology.

    Launch operations for the Apollo, Skylab, Space Shuttle, and Artemis programs were carried out from Kennedy Space Center Launch Complex 39 and managed by KSC. Launch Complex 39 is part of the center.

    KSC is adjacent to Cape Canaveral Space Force Station (CCSFS). The management of the two entities works closely together, shares resources, and operates facilities on each other's property.

    Time range: 1968 – ongoing
    Key facts:
      • The John F. Kennedy Space Center is one of the ten field centers of NASA.
      • KSC is located on Merritt Island, Florida, on the east coast of the state.
      • Since 1968, KSC has been NASA's primary launch center of American spaceflight, research, and technology.
      • Launch operations for the Apollo, Skylab, Space Shuttle, and Artemis programs were carried out from Launch Complex 39 and managed by KSC.
      • KSC is adjacent to Cape Canaveral Space Force Station; the two share resources and operate facilities on each other's property.
    ```

## 查詢圖

建 knowledge graph 的回報是 multi-hop 推理：回答需要串起從沒在同一份文件共同出現的事實的問題。「哪些地點跟搭過 Apollo 11 的人有關？」需要擷取器在一份文件找到 人物→任務 的邊，在另一份找到 人物→地點 的邊，然後 resolver 把人物節點統一，這兩種邊才會接在一起。

我們把相關的子圖序列化成 triple，讓 Claude 在上面推理。為了對照，先用沒有圖 context 的方式問同一個問題。

```python
def serialize_subgraph(center: str, hops: int = 2) -> str:
    nodes = {center}
    frontier = {center}
    for _ in range(hops):
        nxt = set()
        for n in frontier:
            nxt |= set(G.successors(n)) | set(G.predecessors(n))
        frontier = nxt - nodes
        nodes |= frontier
    sub = G.subgraph(nodes)
    lines = [f"({s}) --[{d['predicate']}]--> ({t})" for s, t, d in sub.edges(data=True)]
    return "\n".join(sorted(set(lines)))


def ask(question: str, graph_context: str | None = None) -> str:
    if graph_context is not None:
        prompt = f"""Answer using only the knowledge graph below. Cite the specific edges that support your answer.

<graph>
{graph_context}
</graph>

Question: {question}"""
    else:
        prompt = question
    response = client.messages.create(
        model=SYNTHESIS_MODEL,
        max_tokens=4096,  # leaves room for adaptive thinking before the answer
        messages=[{"role": "user", "content": prompt}],
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise ValueError(f"No text block in response (stop_reason={response.stop_reason})")
    return text_block.text
```

```python
center = next((n for n in G.nodes if "Apollo" in n), hub_nodes[0])
print(f"Querying 2-hop neighborhood of: {center}\n")
subgraph = serialize_subgraph(center, hops=2)

question = "Which locations are connected to people who were part of Apollo 11, and how?"

print("WITHOUT graph context:")
print(ask(question))
print("\n" + "─" * 60 + "\n")
print("WITH graph context:")
print(ask(question, subgraph))
```

??? note "輸出"

    ```text
    Querying 2-hop neighborhood of: Apollo program

    WITHOUT graph context:
    # Locations linked to Apollo 11 people

    I've grouped these by connection type, focusing mainly on the three crew members, with a few others at the end.

    ## Birthplaces and hometowns
    - **Wapakoneta, Ohio**: Neil Armstrong's hometown, now home to the Armstrong Air & Space Museum.
    - **Glen Ridge and Montclair, New Jersey**: Buzz Aldrin was born in Glen Ridge and attended Montclair High School.
    - **Rome, Italy**: Michael Collins was born here, where his father was a U.S. Army officer.

    ## Education and military training
    - **Purdue University (Indiana)**: Armstrong studied aeronautical engineering here.
    - **U.S. Military Academy, West Point (New York)**: Both Aldrin and Collins graduated from here.
    - **MIT (Massachusetts)**: Aldrin earned his doctorate in astronautics, with a thesis on orbital rendezvous.
    - **Korea**: Armstrong flew Navy combat missions, and Aldrin flew Air Force combat missions.

    ## Careers before and after Apollo
    - **Edwards Air Force Base / NASA Flight Research Center (California)**: Armstrong was a research test pilot here, and Collins attended the test pilot school.
    - **Lewis Research Center (Cleveland, Ohio)**: Armstrong's early NASA work.
    - **Washington, D.C.**: Collins became the director of the National Air and Space Museum.
    - **University of Cincinnati**: Armstrong taught aerospace engineering here after leaving NASA.

    ## Mission sites
    - **Kennedy Space Center, Launch Complex 39A (Florida)**: The launch site on July 16, 1969.
    - **Tranquility Base (Sea of Tranquility, Moon)**: Armstrong and Aldrin's landing site.
    - **Johnson Space Center / Mission Control (Houston)**: The flight controllers' base, including Flight Director Gene Kranz and capsule communicator Charlie Duke.
    - **Tracking stations**: Goldstone (California), Honeysuckle Creek and Parkes Observatory (Australia). Parkes and Honeysuckle Creek were crucial for relaying the moonwalk TV broadcast.
    - **Pacific Ocean, southwest of Hawaii**: The splashdown site, where the USS *Hornet* recovered the crew.
    - **Honolulu and Houston**: The crew was quarantined, first in a mobile unit aboard the *Hornet* and then at the Lunar Receiving Laboratory.

    ## Later life and death
    - **Armstrong** lived near Lebanon, Ohio, and died in Cincinnati in 2012. He was buried at sea in the Philippine Sea.
    - **Collins** retired in Florida (Naples and Marco Island area), died in 2021, and is buried at Arlington National Cemetery.
    - **Aldrin** has lived in California and Florida, and remains an advocate for Mars exploration.

    If you're interested in a particular person or type of place (for example mission control staff, or a travel itinerary of museums and sites), I can go deeper.

    ────────────────────────────────────────────────────────────
    ... (省略 13 行)
    ```

沒有 grounding 的答案來自 Claude 的預訓練，可能是對的，Apollo 11 太有名了。但有 grounding 的答案是**可追溯的**：每個說法都引用我們從特定文件擷取的邊。在 Claude 沒有先備知識的私有語料上，只有有 grounding 的答案才行得通。

## 評估

Knowledge graph 的品質用對照 gold set 的 precision 和 recall 衡量。我們在 `data/sample_triples.json` 附了一小份手工標註的集合，涵蓋其中兩篇文章，另外 `data/alias_map.json` 把各種寫法的變體正規化成 gold 的名稱，讓「the Moon」和「Moon」算同一個命中。

下面的檢查並列兩種分數：原始擷取器輸出，以及經過 resolution 步驟 `alias_to_canonical` 之後的同一批 entity。當 resolver 選的 canonical 名稱是 alias map 認得的（或和 gold 完全一致），resolved recall 會上升。當它選了 alias map 沒涵蓋的冗長形式，例如「Neil Alden Armstrong」，resolved recall 反而可能*下降*，因為原本對得上 gold 的名稱，resolution 之後就對不上了。這不是 resolver 的 bug，是評分上的假象。解法是每次看到評分器不認得的 canonical 名稱，就擴充 `alias_map.json`。

這個 cell 只對 entity 評分。獨立的 script 也會對 relation 評分，用 (source, target) 配對比對並忽略 predicate 的措辭，所以它的 relation recall 是上界。從 repo 根目錄執行：

```bash
uv run python capabilities/knowledge_graph/evaluation/eval_extraction.py
```

```python
# Expects the kernel launched from this notebook's directory
# (capabilities/knowledge_graph/). Falls back to repo root.
data_dir = Path("data")
if not data_dir.exists():
    data_dir = Path("capabilities/knowledge_graph/data")

with open(data_dir / "sample_triples.json", encoding="utf-8") as f:
    gold = json.load(f)
with open(data_dir / "alias_map.json", encoding="utf-8") as f:
    ALIASES = json.load(f)


def norm(name: str) -> str:
    lower = name.lower().strip()
    return ALIASES.get(lower, lower)


def prf(predicted: set, gold: set) -> tuple[float, float, float]:
    tp = len(predicted & gold)
    p = tp / len(predicted) if predicted else 0.0
    r = tp / len(gold) if gold else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


print("Raw extraction vs resolved-graph recall against gold:\n")
for doc_title, labels in gold.items():
    gold_names = {norm(e["name"]) for e in labels["entities"]}

    raw = {norm(e["name"]) for e in raw_entities if e["source_doc"] == doc_title}
    rp, rr, rf = prf(raw, gold_names)

    resolved = {
        norm(alias_to_canonical.get(e["name"], e["name"]))
        for e in raw_entities
        if e["source_doc"] == doc_title
    }
    _, resolved_r, _ = prf(resolved, gold_names)

    print(f"{doc_title:<20}  raw F1={rf:.2f} (P={rp:.2f} R={rr:.2f})  resolved R={resolved_r:.2f}")
    missed = gold_names - resolved
    if missed:
        print(f"  still missed after resolution: {', '.join(sorted(missed))}")
```

??? note "輸出"

    ```text
    Raw extraction vs resolved-graph recall against gold:

    Apollo 11             raw F1=0.78 (P=1.00 R=0.64)  resolved R=0.64
      still missed after resolution: columbia, kennedy space center, lunar module eagle, saturn v
    Neil Armstrong        raw F1=0.55 (P=1.00 R=0.38)  resolved R=0.38
      still missed after resolution: gemini 8, korean war, nasa, purdue university, united states navy
    ```

## 擴充規模

這份 notebook 在記憶體裡處理六份文件。production 的 knowledge graph 是從數千份文件建出來的。幾點擴充的筆記：

**擷取成本。** Haiku 便宜到可以跑大型語料，但當你的擷取 schema 和指令固定時，[prompt caching](https://docs.claude.com/en/docs/build-with-claude/prompt-caching) 能進一步降低成本：cache 住 system prompt 和 schema，只有文件文字才付全價。[Message Batches API](https://docs.claude.com/en/docs/build-with-claude/batch-processing) 對可以等最多 24 小時的工作提供五折。

**大規模的 entity resolution。** 把一萬個 PERSON entity 一次塞給 Claude 行不通。先做 block：用便宜的訊號（同姓、token 重疊、embedding 相似度）把候選分組，讓 Claude 只在小 block 內裁決。上面的 resolution prompt 不用改，就能處理 50 到 100 個一組的 block。

**增量更新。** 新文件進來時，擷取它的 entity，對現有的 canonical 集合（而不是彼此）做 resolution，只加入新的邊。只有在 entity 的來源文件集合有明顯變動時，才重新做摘要。

**儲存。** NetworkX 撐到幾十萬條邊都沒問題。更大的規模，這個 schema 可以直接對應到 property graph（Neo4j、Neptune）或三張 Postgres 表：`entities(id, name, type, summary)`、`relations(source_id, target_id, predicate)`、`aliases(entity_id, alias)`。擷取和 resolution 的程式碼不用改，只換持久層。

## 總結

你只靠 prompt 就建完整條 knowledge graph pipeline：

- **擷取**：每份文件一次 structured-output 呼叫，取代了以前要訓練的 NER 模型加 relation classifier。Pydantic schema 是唯一需要的「訓練」。
- **Resolution**：Claude 用擷取時的描述當 context 把各種寫法分群，抓到字串相似度完全漏掉的「Edwin Aldrin」→「Buzz Aldrin」。
- **摘要**：hub 節點得到跨所有提到它的文件合成的完整檔案，有結構化的時間範圍和可追溯的關鍵事實。
- **查詢**：序列化的子圖讓 Claude 能回答 multi-hop 問題，並附上邊層級的引用，答案根植於你建的圖，而不是預訓練。

`evaluation/` 裡的評估工具給你一個回饋迴圈：改擷取 prompt、重跑評分器、看 F1 怎麼動。這個迴圈就是把 demo 變成 production 系統的關鍵。

## 相關 cookbook

- [Extracting structured JSON](../../tool_use/extracting_structured_json.md)：同樣擷取模式的 tool-use 做法，適合你已經在 agentic tool-calling 流程裡時用
- [Retrieval augmented generation](../retrieval_augmented_generation/guide.md)：需要文件檢索而不是事實走訪時的互補做法
- [Contextual embeddings](../contextual-embeddings/guide.md)：在 embedding 前先豐富 chunk，同樣是「索引前加 context」的想法，用在向量搜尋上

## 重點整理

- Knowledge graph 讓 multi-hop 問題變成圖走訪，這是 RAG 檢索串不起來的
- 擷取和 resolution 都變成 prompt：structured outputs 保證 schema，Claude 用描述消歧
- Entity resolution 有兩個失敗模式：漏掉沒被分群的名稱，以及 over-merge，都要抽查
- 用子圖 triple 讓 Claude 推理，答案可追溯到具體的邊和來源文件
- 評分用 gold set 的 precision/recall，canonical 名稱不在 alias map 時要擴充 map，不然分數會失真

## 練習

1. 把擷取用的模型從 Haiku 換成 Sonnet，比較擷取到的 entity 數量和品質差異。
2. 修改 resolution 的邏輯，對沒被任何 cluster 涵蓋的名稱退回單一元素 cluster，確認沒有節點消失。
3. 在語料加入第七篇文章，只對新文章擷取，並對現有 canonical 集合做 resolution，再增量加進圖裡。
