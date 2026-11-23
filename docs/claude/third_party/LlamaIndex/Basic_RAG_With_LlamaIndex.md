---
translated: true
source: third_party/LlamaIndex/Basic_RAG_With_LlamaIndex.ipynb
---

# 用 LlamaIndex 建立 RAG pipeline

> 原文：[third_party/LlamaIndex/Basic_RAG_With_LlamaIndex.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/LlamaIndex/Basic_RAG_With_LlamaIndex.ipynb)

用 LlamaIndex 建立基本的 RAG pipeline，做文件檢索與問答。

## 這篇在做什麼

用 LlamaIndex 一步步建出基本的 RAG pipeline：設定模型、下載與載入資料、建 index、建 query engine，最後做查詢。

## 學完你會

- 設定 Claude LLM 和 embedding 模型
- 載入文件並建立 vector index
- 建立 query engine，對文件提問

## 開跑前

需要 Anthropic API key，以及 embedding 模型所需的設定（依 notebook 的設定 cell）。

這份 notebook 我們要建立 LlamaIndex 的基本 RAG Pipeline。pipeline 有下面這些步驟。

1. 設定 LLM 和 Embedding 模型。
2. 下載資料。
3. 載入資料。
4. 為資料建 Index。
5. 建立 Query Engine。
6. 查詢。

### 安裝

```python
%pip install llama-index
%pip install llama-index-llms-anthropic
%pip install llama-index-embeddings-huggingface
```

### 設定 API Key

```python
import os

os.environ["ANTHROPIC_API_KEY"] = "YOUR Claude API KEY"
```

### 設定 LLM 和 Embedding 模型

我們使用 Anthropic 的 `Claude Opus 5.5` 模型。

```python
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.anthropic import Anthropic
```

```python
llm = Anthropic(model="claude-opus-5-5")
embed_model = HuggingFaceEmbedding(model_name="BAAI/bge-base-en-v1.5")
```

??? note "輸出"

    ```text
    config.json:   0%|          | 0.00/777 [00:00<?, ?B/s]
    ```

    ```text
    model.safetensors:   0%|          | 0.00/438M [00:00<?, ?B/s]
    ```

    ```text
    tokenizer_config.json:   0%|          | 0.00/366 [00:00<?, ?B/s]
    ```

    ```text
    vocab.txt:   0%|          | 0.00/232k [00:00<?, ?B/s]
    ```

    ```text
    tokenizer.json:   0%|          | 0.00/711k [00:00<?, ?B/s]
    ```

    ```text
    special_tokens_map.json:   0%|          | 0.00/125 [00:00<?, ?B/s]
    ```

```python
from llama_index.core import Settings

Settings.llm = llm
Settings.embed_model = embed_model
Settings.chunk_size = 512
```

### 下載資料

```python
!mkdir -p 'data/paul_graham/'
!wget 'https://raw.githubusercontent.com/run-llama/llama_index/main/docs/examples/data/paul_graham/paul_graham_essay.txt' -O 'data/paul_graham/paul_graham_essay.txt'
```

??? note "輸出"

    ```text
    --2024-03-08 06:51:30--  https://raw.githubusercontent.com/run-llama/llama_index/main/docs/examples/data/paul_graham/paul_graham_essay.txt
    Resolving raw.githubusercontent.com (raw.githubusercontent.com)... 185.199.109.133, 185.199.108.133, 185.199.110.133, ...
    Connecting to raw.githubusercontent.com (raw.githubusercontent.com)|185.199.109.133|:443... connected.
    HTTP request sent, awaiting response... 200 OK
    Length: 75042 (73K) [text/plain]
    Saving to: ‘data/paul_graham/paul_graham_essay.txt’

    data/paul_graham/pa 100%[===================>]  73.28K  --.-KB/s    in 0.002s  

    2024-03-08 06:51:30 (34.6 MB/s) - ‘data/paul_graham/paul_graham_essay.txt’ saved [75042/75042]
    ```

```python
from llama_index.core import (
    SimpleDirectoryReader,
    VectorStoreIndex,
)
```

### 載入資料

```python
documents = SimpleDirectoryReader("./data/paul_graham").load_data()
```

### 為資料建 Index

```python
index = VectorStoreIndex.from_documents(
    documents,
)
```

### 建立 Query Engine

```python
query_engine = index.as_query_engine(similarity_top_k=3)
```

### 測試 Query

```python
response = query_engine.query("What did author do growing up?")
```

```python
print(response)
```

??? note "輸出"

    ```text
    Based on the information provided, the author worked on two main things outside of school before college: writing and programming.

    For writing, he wrote short stories as a beginning writer, though he felt they were awful, with hardly any plot and just characters with strong feelings.

    In terms of programming, in 9th grade he tried writing his first programs on an IBM 1401 computer that his school district used. He and his friend got permission to use it, programming in an early version of Fortran using punch cards. However, he had difficulty figuring out what to actually do with the computer at that stage given the limited inputs available.
    ```

## 重點整理

- RAG 的基本流程是載入、切分、建 index、檢索、再讓 LLM 根據檢索結果回答。
- embedding 模型負責把文字變成向量，用來找相關段落。
- query engine 把檢索和生成包成一個介面。
- LLM 和 embedding 模型是兩個獨立的設定，可以各自替換。

## 練習

1. 換成你自己的文件資料夾，建 index 後提問。
2. 問一個文件裡沒有的問題，觀察模型怎麼回答。
3. 調整 query engine 的檢索筆數（`similarity_top_k`），比較答案。
