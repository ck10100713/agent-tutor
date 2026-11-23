---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/cassandra_astradb/README.md
---

# Cassandra / Astra DB

> 原文：[examples/vector_databases/cassandra_astradb/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/README.md)



## 這篇在做什麼

這是 Cassandra / Astra DB 範例資料夾的導覽頁。資料夾裡的 notebook 用不同的函式庫和 API，做同一個標準的 RAG 工作流程，讓你比較哪種存取方式適合自己。

## 學完你會

- 知道 Astra DB 的向量搜尋可以透過 HTTP API（AstraPy）或 CQL（CassIO、純 CQL）使用
- 根據自己想要的抽象層級，挑出對應的 notebook
- 知道每個範例做的事：搜尋與生成哲學名言

## 開跑前

- DataStax Astra DB 帳號，或支援向量搜尋的 Cassandra 叢集
- OpenAI API key

這個資料夾裡的 demo 示範如何使用 **DataStax Astra DB** 目前提供的向量搜尋功能。Astra DB 是建在 Apache Cassandra® 上的 serverless Database-as-a-Service。

這些範例 notebook 用不同的函式庫和 API，實作同一個標準的 GenAI RAG 工作負載。

想透過 HTTP API 介面使用 [Astra DB](https://docs.datastax.com/en/astra/home/astra.html)，請看 "AstraPy" notebook（`astrapy` 是跟資料庫互動的 Python client）。

如果你偏好用 CQL 存取資料庫（不管是用 [Astra DB](https://docs.datastax.com/en/astra-serverless/docs/vector-search/overview.html)，還是[支援向量搜尋](https://cassandra.apache.org/doc/trunk/cassandra/vector-search/overview.html)的 Cassandra 叢集），請看 "CQL" 或 "CassIO" notebook，兩者的差別在於你操作時的抽象層級。

想進一步了解 Astra DB 和它的向量搜尋功能，請到 [datastax.com](https://docs.datastax.com/en/astra/home/astra.html)。

### 範例 notebook

下面的範例展示 OpenAI 和 DataStax Astra DB 多容易搭配，做出以向量為基礎的 AI 應用。可以用本機的 Jupyter 跑，也可以用 Colab notebook 跑：

| Use case | Target database | Framework | Notebook | Google Colab |
| -------- | --------------- | --------- | -------- | ------------ |
| Search/generate quotes | Astra DB | AstraPy | [Notebook](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_AstraPy.ipynb) | [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_AstraPy.ipynb) |
| Search/generate quotes | Cassandra / Astra DB through CQL | CassIO | [Notebook](Philosophical_Quotes_cassIO.md) | [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_cassIO.ipynb) |
| Search/generate quotes | Cassandra / Astra DB through CQL | Plain Cassandra language | [Notebook](Philosophical_Quotes_CQL.md) | [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_CQL.ipynb) |

### 向量相似度的視覺化

![3_vector_space](https://user-images.githubusercontent.com/14221764/262321363-c8c625c1-8be9-450e-8c68-b1ed518f990d.png)

## 重點整理

- Astra DB 是 Cassandra 上的 serverless 服務，內建向量搜尋。
- 同一個 RAG 流程有三種接法：AstraPy（HTTP API）、CassIO（CQL，高階抽象）、純 CQL（低階）。
- 三者的差別是抽象層級，要自己控制細節就選越低階的，想少寫程式就選越高階的。
- 這幾份範例都能在本機 Jupyter 或 Colab 上跑。

## 練習

1. 先挑 AstraPy 的 notebook 跑一遍，記下建 collection 和查詢各用了哪幾行。
2. 再開 CassIO 或 CQL 的 notebook，對照同一步驟的寫法差在哪。
3. 把範例的查詢句換成你自己的主題，看回傳的名言是否合理。
