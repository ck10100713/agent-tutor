---
translated: true
source: examples/vector_databases/elasticsearch/README.md
---

# Elasticsearch

> 原文：[examples/vector_databases/elasticsearch/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/README.md)



## 這篇在做什麼
Elasticsearch 是很常見的搜尋與分析引擎，也是一個[向量資料庫](https://www.elastic.co/elasticsearch/vector-database)，能有效率地大規模建立、儲存和搜尋向量 embedding。
這篇介紹 Elasticsearch 搭配 OpenAI 的兩本 notebook：語意搜尋，以及在它之上做的 retrieval augmented generation (RAG)。

## 學完你會
- 把 OpenAI Wikipedia embeddings 資料集索引進 Elasticsearch。
- 用 `openai ada-02` 模型編碼問題，做語意搜尋。
- 取語意搜尋的最佳結果，丟給 Chat Completions API 做 RAG。

## 開跑前
- 需要一個 Elasticsearch 環境和 OpenAI API key。

技術細節請看 [Elasticsearch 文件](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html)。

[`elasticsearch-labs`](https://github.com/elastic/elasticsearch-labs) repo 裡有可執行的 Python notebook、範例 app 和測試 Elastic 平台的資源。

## OpenAI cookbook notebooks 📒

看看這個 repo 裡的 notebook，用 Elasticsearch 當向量資料庫搭配 OpenAI。

### [Semantic search](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb)

在這本 notebook 裡你會學到：

 - 把 OpenAI Wikipedia embeddings 資料集索引進 Elasticsearch
 - 用 `openai ada-02` 模型對問題編碼
 - 執行語意搜尋

<hr>


### [Retrieval augmented generation](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-retrieval-augmented-generation.ipynb)

這本 notebook 建立在語意搜尋那本之上：

- 從語意搜尋中選出最佳結果
- 把那個結果送到 OpenAI [Chat Completions](https://platform.openai.com/docs/guides/gpt/chat-completions-api) API 端點，做 retrieval augmented generation (RAG)

## 重點整理
- Elasticsearch 本來就是搜尋引擎，加上向量欄位後就能當向量資料庫用。
- 語意搜尋的流程是：先把資料做 embedding 索引，查詢時再把問題編碼，找最近的向量。
- RAG 是在語意搜尋後再多一步，把搜尋結果當上下文交給 chat 模型生成答案。
- 查詢和資料必須用同一個 embedding 模型編碼，向量才能比較。

## 練習
1. 打開 semantic search notebook，換一個你自己的問題搜尋，看前幾筆結果合不合理。
2. 在 RAG notebook 裡把「取最佳一筆」改成取前三筆，一起放進 prompt。
3. 比較只用搜尋結果回答，和用 RAG 讓模型整理後回答，兩者的差異。
