---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/mongodb_atlas/README.md
---

# MongoDB Atlas Vector Search

> 原文：[examples/vector_databases/mongodb_atlas/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/mongodb_atlas/README.md)



## 這篇在做什麼
這篇簡介 MongoDB Atlas Vector Search。它是全託管服務，讓你在 MongoDB 裡有效索引高維向量資料，並做快速的向量相似度搜尋。

## 學完你會
- 知道 Atlas Vector Search 可以當新專案獨立的向量資料庫，也可以替既有的 MongoDB collection 加上向量搜尋。
- 了解它能在 AWS、Azure、GCP 等主要公有雲上使用。
- 知道去哪裡查官方文件。

## 開跑前
- 需要一個 MongoDB Atlas 帳號。

[Atlas Vector Search](https://www.mongodb.com/products/platform/atlas-vector-search) 是全託管服務，簡化了在 MongoDB 中有效索引高維向量資料、並執行快速向量相似度搜尋的流程。有了 Atlas Vector Search，你可以把 MongoDB 當成新專案獨立的向量資料庫，也可以替既有的 MongoDB collection 加上向量搜尋功能。你能在任何主要的公有雲（AWS、Azure、GCP）上使用向量搜尋的強大能力，開箱即得到大規模擴充和資料安全，並且透過 FedRamp、SoC2 合規等機制做到企業級可用。

文件：[連結](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/)

## 重點整理
- Atlas Vector Search 把向量搜尋做進 MongoDB，不需要另外架一套向量資料庫。
- 既有的 collection 可以直接加上向量搜尋，適合已經用 MongoDB 的團隊。
- 託管服務包辦擴充和安全，並支援主要公有雲。

## 練習
1. 打開官方文件，找出建立向量索引需要指定哪些設定。
2. 想想你現有的某個 collection，列出哪個欄位適合做 embedding。
