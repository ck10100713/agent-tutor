---
translated: true
source: third_party/LlamaIndex/Multi_Document_Agents.ipynb
---

# Multi-document agents

> 原文：[third_party/LlamaIndex/Multi_Document_Agents.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/LlamaIndex/Multi_Document_Agents.ipynb)

用 DocumentAgents 搭配 ReAct Agent 模式，為大量文件建立 RAG。

## 這篇在做什麼

文件數量很多時，用 `DocumentAgents` 的概念搭配 `ReAct Agent` 建 RAG：每份文件有自己的 agent，再用最上層的 retriever 依問題挑出合適的 agent。範例用五個城市的 Wikipedia 頁面。

## 學完你會

- 為每份文件建立各自的 ReAct agent
- 把 agent 包成 IndexNode，讓最上層 retriever 可以挑選
- 用不同的問題測試 agent 如何選到對的文件 agent

## 開跑前

需要 Anthropic API key，以及 embedding 模型所需的設定（依 notebook 的設定 cell）。

這份 notebook 我們要看文件數量很多時，怎麼用 `DocumentAgents` 的概念搭配 `ReAct Agent` 建 RAG。

### 安裝

```python
%pip install llama-index
%pip install llama-index-llms-anthropic
%pip install llama-index-embeddings-huggingface
```

### 設定 Logging

```python
# NOTE: This is ONLY necessary in jupyter notebook.
# Details: Jupyter runs an event-loop behind the scenes.
#          This results in nested event-loops when we start an event-loop to make async queries.
#          This is normally not allowed, we use nest_asyncio to allow it for convenience.
import nest_asyncio

nest_asyncio.apply()

import logging
import sys

# Set up the root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Set logger level to INFO

# Clear out any existing handlers
logger.handlers = []

# Set up the StreamHandler to output to sys.stdout (Colab's output)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)  # Set handler level to INFO

# Add the handler to the logger
logger.addHandler(handler)

from IPython.display import HTML, display
```

### 設定 Claude API Key

```python
import os

os.environ["ANTHROPIC_API_KEY"] = "YOUR Claude API KEY"
```

### 設定 LLM 和 Embedding 模型

我們使用 Anthropic 的 `Claude Opus 5.5` LLM。

```python
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.anthropic import Anthropic
```

```python
llm = Anthropic(model="claude-opus-5-5")
embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
```

```python
from llama_index.core import Settings

Settings.llm = llm
Settings.embed_model = embed_model
Settings.chunk_size = 512
```

### 下載文件

我們用 `Toronto`、`Seattle`、`Chicago`、`Boston`、`Houston` 這幾個城市的 Wikipedia 頁面來建 RAG pipeline。

```python
wiki_titles = ["Toronto", "Seattle", "Chicago", "Boston", "Houston"]

from pathlib import Path

import requests

for title in wiki_titles:
    response = requests.get(
        "https://en.wikipedia.org/w/api.php",
        params={
            "action": "query",
            "format": "json",
            "titles": title,
            "prop": "extracts",
            # 'exintro': True,
            "explaintext": True,
        },
        timeout=30,
    ).json()
    page = next(iter(response["query"]["pages"].values()))
    wiki_text = page["extract"]

    data_path = Path("data")
    if not data_path.exists():
        Path.mkdir(data_path)

    with open(data_path / f"{title}.txt", "w") as fp:
        fp.write(wiki_text)
```

### 載入文件

```python
# Load all wiki documents

from llama_index.core import SimpleDirectoryReader

city_docs = {}
for wiki_title in wiki_titles:
    city_docs[wiki_title] = SimpleDirectoryReader(
        input_files=[f"data/{wiki_title}.txt"]
    ).load_data()
```

#### 為每個城市建立 ReAct Agent 

```python
from llama_index.core import SummaryIndex, VectorStoreIndex
from llama_index.core.agent import ReActAgent
from llama_index.core.tools import QueryEngineTool, ToolMetadata

# Build agents dictionary
agents = {}

for wiki_title in wiki_titles:
    # build vector index
    vector_index = VectorStoreIndex.from_documents(
        city_docs[wiki_title],
    )
    # build summary index
    summary_index = SummaryIndex.from_documents(
        city_docs[wiki_title],
    )
    # define query engines
    vector_query_engine = vector_index.as_query_engine()
    summary_query_engine = summary_index.as_query_engine()

    # define tools
    query_engine_tools = [
        QueryEngineTool(
            query_engine=vector_query_engine,
            metadata=ToolMetadata(
                name="vector_tool",
                description=(f"Useful for retrieving specific context from {wiki_title}"),
            ),
        ),
        QueryEngineTool(
            query_engine=summary_query_engine,
            metadata=ToolMetadata(
                name="summary_tool",
                description=(f"Useful for summarization questions related to {wiki_title}"),
            ),
        ),
    ]

    # build agent
    agent = ReActAgent.from_tools(
        query_engine_tools,
        llm=llm,
        verbose=True,
    )

    agents[wiki_title] = agent
```

#### 為每個 Agent 定義 IndexNode

```python
from llama_index.core.schema import IndexNode

# define top-level nodes
objects = []
for wiki_title in wiki_titles:
    # define index node that links to these agents
    wiki_summary = (
        f"This content contains Wikipedia articles about {wiki_title}. Use"
        " this index if you need to lookup specific facts about"
        f" {wiki_title}.\nDo not use this index if you want to analyze"
        " multiple cities."
    )
    node = IndexNode(text=wiki_summary, index_id=wiki_title, obj=agents[wiki_title])
    objects.append(node)
```

#### 定義最上層 Retriever 來選擇 Agent

```python
vector_index = VectorStoreIndex(
    objects=objects,
)
query_engine = vector_index.as_query_engine(similarity_top_k=1, verbose=True)
```

#### 測試 Query

應該依 query 為特定的 agent 選擇 vector tool 或 summary tool。

```python
# should use Toronto agent -> vector tool
response = query_engine.query("What is the population of Toronto?")
```

??? note "輸出"

    ```text
    Retrieval entering Toronto: ReActAgent
    Retrieving from object ReActAgent with query What is the population of Toronto?
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: I need to use a tool to help me answer the question.
    Action: vector_tool
    Action Input: {'input': 'What is the population of Toronto?'}
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Observation: According to the context information, the population of Toronto in 2021 was 2,794,356, making it the fourth-most populous city in North America.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: I can answer without using any more tools.
    Answer: According to the information provided, the population of Toronto in 2021 was 2,794,356, making it the fourth-most populous city in North America.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    ```

```python
display(HTML(f'<p style="font-size:20px">{response.response}</p>'))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# should use Houston agent -> vector tool
response = query_engine.query("Who and when was Houston founded?")
```

??? note "輸出"

    ```text
    Retrieval entering Houston: ReActAgent
    Retrieving from object ReActAgent with query Who and when was Houston founded?
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: I need to use a tool to help me answer the question about who founded Houston and when it was founded.
    Action: vector_tool
    Action Input: {'input': 'Who founded Houston and when was it founded?'}
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Observation: Houston was founded by land investors on August 30, 1836, at the confluence of Buffalo Bayou and White Oak Bayou, a point now known as Allen's Landing. The city was incorporated on June 5, 1837 and named after former General Sam Houston, who was president of the Republic of Texas at the time.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: The vector_tool provided the key information needed to answer the question of who founded Houston and when it was founded. I can now provide a complete answer without using any more tools.
    Answer: Houston was founded by land investors on August 30, 1836. The city was incorporated on June 5, 1837 and named after Sam Houston, who was the president of the Republic of Texas at the time. The location where Houston was founded is at the confluence of Buffalo Bayou and White Oak Bayou, which is now known as Allen's Landing.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    ```

```python
display(HTML(f'<p style="font-size:20px">{response.response}</p>'))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# should use Boston agent -> summary tool
response = query_engine.query("Summarize about the sports teams in Boston")
```

??? note "輸出"

    ```text
    Retrieval entering Boston: ReActAgent
    Retrieving from object ReActAgent with query Summarize about the sports teams in Boston
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: I need to use a tool to help me answer the question.
    Action: summary_tool
    Action Input: {'input': 'Summarize the sports teams in Boston'}
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Observation: Boston has teams in the four major North American men's professional sports leagues plus Major League Soccer, and has won 39 championships in these leagues:

    - The Boston Red Sox (MLB) play at Fenway Park. They are one of the most storied franchises in baseball.

    - The Boston Celtics (NBA) play at TD Garden. Along with the Los Angeles Lakers, they have won the most NBA championships with 17. 

    - The Boston Bruins (NHL) also play at TD Garden. They were the first American NHL team and are an Original Six franchise.

    - The New England Patriots (NFL) play in nearby Foxborough. They have won 6 Super Bowls in the 2000s and 2010s.

    - The New England Revolution (MLS) also play in Foxborough.

    Boston also has several other professional sports teams like the Boston Breakers (women's soccer) and Boston Cannons (lacrosse). The area's many colleges field competitive NCAA Division I teams, especially in ice hockey. The annual Boston Marathon is one of the world's most famous running events.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: The summary tool provided a good overview of the major sports teams in Boston. I think I can provide a concise summary answer to the original question based on this information.
    Answer: Boston is home to successful professional sports teams in baseball (Red Sox), basketball (Celtics), hockey (Bruins), football (Patriots), and soccer (Revolution). The Red Sox, Celtics, and Bruins are some of the most historic franchises in their respective leagues. In total, Boston teams have won 39 championships in the four major North American sports leagues and MLS. The area also hosts the famous Boston Marathon each year and has many competitive college sports programs, especially in ice hockey.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    ```

```python
display(HTML(f'<p style="font-size:20px">{response.response}</p>'))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# should use Seattle agent -> summary tool
response = query_engine.query("Give me a summary on all the positive aspects of Chicago")
```

??? note "輸出"

    ```text
    Retrieval entering Chicago: ReActAgent
    Retrieving from object ReActAgent with query Give me a summary on all the positive aspects of Chicago
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: I need to use a tool to help me summarize the positive aspects of Chicago.
    Action: summary_tool
    Action Input: {'input': 'Provide a summary of the positive aspects and attributes of the city of Chicago'}
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Observation: Based on the provided information, some of the positive aspects and attributes of Chicago include:

    - Chicago is the third most populous city in the U.S. and a major transportation hub. It is an important component in global distribution.

    - The city has a diverse economy, with major industries including finance, commerce, industry, technology, telecommunications, and transportation. Chicago has the second largest central business district in the U.S. 

    - Chicago is an international hub for finance, culture, commerce, and industry. It has the largest derivatives market in the world and is a major financial center.

    - The city is a popular tourist destination known for its architecture, skyscrapers, parks, museums, and unique cuisine. Major attractions include Millennium Park, Navy Pier, the Magnificent Mile, and numerous cultural institutions.

    - Chicago has a rich history in the visual and performing arts, literature, film, theater, and music. It has influential art museums, a strong tradition of jazz and blues music, and acclaimed theater, dance, and comedy scenes.

    - The city has an extensive public transportation system including rail lines and buses. It also has a large network of parks and open spaces.

    - Chicago is home to several top universities, numerous major company headquarters, and a variety of unique neighborhoods and communities reflecting its diverse population and history.

    In summary, Chicago stands out for its economic strength, cultural vibrancy, tourist appeal, transportation infrastructure, higher education, and cosmopolitan character. The context portrays Chicago in an overall positive light as a thriving, world-class American city.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Thought: The summary tool provided a good overview of the positive aspects of Chicago. I think I can provide a satisfactory answer to the original question based on the information given.
    Answer: Chicago has many positive attributes that make it a vibrant and appealing city:

    Economy and Business: Chicago has a diverse and thriving economy, serving as a major hub for industries like finance, commerce, telecommunications, and transportation. It is home to the second largest central business district in the U.S. and the world's largest derivatives market.

    Tourism and Culture: Chicago is a popular tourist destination known for its iconic architecture, world-class museums, unique cuisine, and beautiful parks like Millennium Park. The city has a rich artistic heritage in visual arts, music (especially jazz and blues), theater, dance and comedy.

    Transportation: Chicago is a critical transportation center for the U.S. with an extensive public transit network of trains and buses. Its airports and rail lines make it an important link in the nation's distribution network.

    Education: Numerous prestigious universities call Chicago home, adding to its intellectual capital. 

    Diversity: Chicago's many neighborhoods reflect the diverse backgrounds and cultures of its residents, resulting in a cosmopolitan, international character.

    Overall, Chicago stands out as a world-class city known for its robust economy, vibrant cultural scene, strong transportation infrastructure, acclaimed educational institutions, and global status. The city has many strengths and positive qualities that make it an attractive place to live, work, and visit.
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    ```

```python
display(HTML(f'<p style="font-size:20px">{response.response}</p>'))
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 重點整理

- 文件一多，把所有內容塞進一個 index 效果會變差，每份文件一個 agent 更好管理。
- 兩層結構：最上層挑文件，文件層的 agent 再決定用 vector tool 或 summary tool。
- IndexNode 把 agent 包成可檢索的節點，讓 retriever 能在 agent 之間做選擇。
- 問題的範圍決定走哪條路：具體細節走 vector，整體概觀走 summary。

## 練習

1. 再加一個城市的 Wikipedia 頁面，建立它的 agent 並放進 retriever。
2. 問一個跨兩個城市比較的問題，觀察最上層選了哪些 agent。
3. 分別問「概觀型」和「細節型」的問題，看文件 agent 選哪種 tool。
