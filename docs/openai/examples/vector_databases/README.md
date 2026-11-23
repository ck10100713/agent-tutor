---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/README.md
---

# 向量資料庫

> 原文：[examples/vector_databases/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/README.md)



## 這篇在做什麼

OpenAI Cookbook 這個區塊的導覽頁，列出可以支援語意搜尋的各種向量資料庫。每家廠商有自己的資料夾，裡面有一份標準的入門 notebook，示範怎麼把 OpenAI API 搭配它們的產品。

## 學完你會

- 知道向量資料庫在知識檢索應用裡扮演的角色
- 找到各家向量資料庫的入門連結
- 知道 cookbook 裡每家廠商資料夾的結構

這個 OpenAI Cookbook 區塊展示了許多可以支援你語意搜尋情境的向量資料庫。

向量資料庫很適合搭配知識檢索應用。這類應用會把相關的 context 提供給 LLM 來回答問題，藉此減少幻覺。

每家廠商都有自己命名的資料夾，裡面有一份標準 notebook，介紹如何把我們的 API 搭配他們的產品使用，以及他們選擇加入、用來展示功能的補充 notebook。

## 指南與深入介紹
- [AnalyticDB](https://www.alibabacloud.com/help/en/analyticdb-for-postgresql/latest/get-started-with-analyticdb-for-postgresql)
- [Cassandra/Astra DB](https://docs.datastax.com/en/astra-serverless/docs/vector-search/qandasimsearch-quickstart.html)
- [Azure AI Search](https://learn.microsoft.com/azure/search/search-get-started-vector)
- [Azure SQL Database](https://learn.microsoft.com/azure/azure-sql/database/ai-artificial-intelligence-intelligent-applications?view=azuresql)
- [Chroma](https://docs.trychroma.com/getting-started)
- [Elasticsearch](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html)
- [Hologres](https://www.alibabacloud.com/help/en/hologres/latest/procedure-to-use-hologres)
- [Kusto](https://learn.microsoft.com/en-us/azure/data-explorer/web-query-data)
- [Milvus](https://milvus.io/docs/example_code.md)
- [MyScale](https://docs.myscale.com/en/quickstart/)
- [MongoDB](https://www.mongodb.com/products/platform/atlas-vector-search)
- [Neon Postgres](https://neon.tech/docs/ai/ai-intro)
- [Pinecone](https://docs.pinecone.io/docs/quickstart)
- [PolarDB](https://www.alibabacloud.com/help/en/polardb/latest/quick-start)
- [Qdrant](https://qdrant.tech/documentation/quick-start/)
- [Redis](https://github.com/RedisVentures/simple-vecsim-intro)
- [SingleStoreDB](https://www.singlestore.com/blog/how-to-get-started-with-singlestore/)
- [Supabase](https://supabase.com/docs/guides/ai)
- [Tembo](https://tembo.io/docs/product/stacks/ai/vectordb)
- [Typesense](https://typesense.org/docs/guide/)
- [Vespa AI](https://vespa.ai/)
- [Weaviate](https://weaviate.io/developers/weaviate/quickstart)
- [Zilliz](https://docs.zilliz.com/docs/quick-start-1)

## 重點整理

- 向量資料庫存的是 embedding，用相似度找出相關內容。
- 它是檢索增強（RAG）的核心元件，把相關 context 餵給 LLM，能減少幻覺。
- 各家產品的基本流程大同小異：建 collection 或表、寫入 embedding、查詢。
- 選哪家主要看你已有的基礎設施（例如已在用 Postgres、Redis 或 Azure）和功能需求。

## 練習

1. 挑一家你已經在用的資料庫（例如 Redis 或 Postgres 系的），打開它的入門連結，看有沒有向量搜尋功能。
2. 打開兩家的入門 notebook，比較它們建索引的步驟差在哪。
3. 選一家，照 notebook 把自己的一小批文字存進去並查詢。
