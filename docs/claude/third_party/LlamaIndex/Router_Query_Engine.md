---
translated: true
source: third_party/LlamaIndex/Router_Query_Engine.ipynb
---
# RouterQuery engine

> 原文：[third_party/LlamaIndex/Router_Query_Engine.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/LlamaIndex/Router_Query_Engine.ipynb)

用 LlamaIndex 的 RouterQueryEngine 把查詢路由到不同的 index，做多文件搜尋。

## 這篇在做什麼

用 LlamaIndex 的 `RouterQueryEngine`，讓 Claude 依問題的性質決定要走哪個 query engine。同一份文件建兩種 index，一個做摘要、一個做向量檢索，再由 router 自動選擇用哪一個回答。

## 學完你會

- 對同一份文件建立 summary index 和 vector index，並各自包成 query engine tool
- 用 `RouterQueryEngine` 讓 LLM 根據問題自動選擇對應的 tool
- 用不同類型的問題測試，觀察 router 選了哪個 engine

## 開跑前

- 需要 Anthropic API key。
- 需要 embedding 模型（看你在「設定 LLM 與 Embedding 模型」那節選的是哪個，可能要額外的 API key）。
- 在 Colab 上用 `pip install` 安裝套件，並用 Secrets 或直接設定環境變數放 API key。

在這本 notebook 裡，我們會看 `RouterQueryEngine`，它把使用者的查詢路由到可用的 query engine tool 其中之一。這些 tool 可以是同一份文件上的不同 index/query engine，也可以是不同文件的。

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

我們會用 Anthropic 的 `Claude Opus 5.5` LLM。

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

```python
!mkdir -p 'data/paul_graham/'
!wget 'https://raw.githubusercontent.com/jerryjliu/llama_index/main/docs/examples/data/paul_graham/paul_graham_essay.txt' -O 'data/paul_graham/paul_graham_essay.txt'
```

??? note "輸出"

    ```text
    --2024-03-08 07:04:27--  https://raw.githubusercontent.com/jerryjliu/llama_index/main/docs/examples/data/paul_graham/paul_graham_essay.txt
    Resolving raw.githubusercontent.com (raw.githubusercontent.com)... 185.199.109.133, 185.199.110.133, 185.199.108.133, ...
    Connecting to raw.githubusercontent.com (raw.githubusercontent.com)|185.199.109.133|:443... connected.
    HTTP request sent, awaiting response... 200 OK
    Length: 75042 (73K) [text/plain]
    Saving to: ‘data/paul_graham/paul_graham_essay.txt’

    data/paul_graham/pa 100%[===================>]  73.28K  --.-KB/s    in 0.002s  

    2024-03-08 07:04:27 (28.6 MB/s) - ‘data/paul_graham/paul_graham_essay.txt’ saved [75042/75042]
    ```

### 載入文件

```python
# load documents
from llama_index.core import SimpleDirectoryReader

documents = SimpleDirectoryReader("data/paul_graham").load_data()
```

### 建立 Index 和 Query Engine

```python
from llama_index.core import SummaryIndex, VectorStoreIndex

# Summary Index for summarization questions
summary_index = SummaryIndex.from_documents(documents)

# Vector Index for answering specific context questions
vector_index = VectorStoreIndex.from_documents(documents)
```

```python
# Summary Index Query Engine
summary_query_engine = summary_index.as_query_engine(
    response_mode="tree_summarize",
    use_async=True,
)

# Vector Index Query Engine
vector_query_engine = vector_index.as_query_engine()
```

### 為 summary 和 vector query engine 建立 tool

```python
from llama_index.core.tools.query_engine import QueryEngineTool

# Summary Index tool
summary_tool = QueryEngineTool.from_defaults(
    query_engine=summary_query_engine,
    description="Useful for summarization questions related to Paul Graham eassy on What I Worked On.",
)

# Vector Index tool
vector_tool = QueryEngineTool.from_defaults(
    query_engine=vector_query_engine,
    description="Useful for retrieving specific context from Paul Graham essay on What I Worked On.",
)
```

### 建立 Router Query Engine

```python
from llama_index.core.query_engine.router_query_engine import RouterQueryEngine
from llama_index.core.selectors.llm_selectors import LLMSingleSelector
```

```python
# Create Router Query Engine
query_engine = RouterQueryEngine(
    selector=LLMSingleSelector.from_defaults(),
    query_engine_tools=[
        summary_tool,
        vector_tool,
    ],
)
```

### 測試查詢

```python
response = query_engine.query("What is the summary of the document?")
```

??? note "輸出"

    ```text
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Selecting query engine 0: The question is asking for a summary of the document. Choice 1 specifically mentions that it is useful for summarization questions related to Paul Graham's essay on What I Worked On, making it the most relevant choice for answering the given question..
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
response = query_engine.query("What did Paul Graham do growing up?")
```

??? note "輸出"

    ```text
    HTTP Request: POST https://api.anthropic.com/v1/messages "HTTP/1.1 200 OK"
    Selecting query engine 1: The question asks about specific details from Paul Graham's life, which would likely be found in the original essay. A summary of the essay may not include all the relevant details about what he did growing up..
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

- Router 的作用是讓 LLM 看問題，在多個 query engine tool 之間挑一個，不用你寫死規則。
- 摘要類問題適合 summary index，針對細節的問題適合 vector index，兩者擅長的事不一樣。
- 每個 tool 都要有清楚的描述，router 就是靠描述來判斷該選誰。
- Router 可以選的 tool 不限於同一份文件的不同 index，也能是不同文件的 engine。

## 練習

1. 對現有文件問一個摘要型問題和一個細節型問題，看 log 確認 router 各自選了哪個 engine。
2. 把其中一個 tool 的描述改得含糊，再問同樣的問題，看 router 的選擇會不會變。
3. 再建一個針對另一份文件的 vector index，加進 tool 清單，讓 router 可以在三個 engine 之間選。
