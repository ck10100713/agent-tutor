---
translated: true
source: examples/vector_databases/neon/README.md
---
# Neon 當作向量資料庫

> 原文：[examples/vector_databases/neon/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/neon/README.md)



## 這篇在做什麼

介紹 Neon（serverless Postgres）怎麼靠 pgvector 擴充功能當向量資料庫，儲存和查詢 embedding。這頁是簡介和資源索引，實際操作在 repo 裡的 notebook。

## 學完你會

- 說明 Neon 用 pgvector 提供向量搜尋的方式。
- 列出 notebook 的流程：用 OpenAI API 產生 embedding、存進 Neon、把查詢文字轉成 embedding、做向量相似度搜尋。
- 知道 Neon 的 autoscaling、read replica 和 serverless driver 能怎麼幫 AI 應用擴充。

## 開跑前

實際跑 notebook 需要 OpenAI API key 和一個 Neon 帳號（建立 Postgres 專案）。


[Neon](https://neon.tech/) 是為雲端打造的 serverless Postgres。Neon 把運算和儲存分開，提供 autoscaling、資料庫 branching、scale-to-zero 等現代的開發功能。

## 向量搜尋

Neon 透過 [pgvector](https://neon.tech/docs/extensions/pgvector) 這個開源的 PostgreSQL 擴充功能支援向量搜尋，讓 Postgres 能當向量資料庫，儲存和查詢 embedding。

## OpenAI cookbook notebook

可以看這個 repo 裡的 notebook，了解怎麼把 Neon Serverless Postgres 當作你的向量資料庫。

### 用 Neon Postgres 搭配 pgvector 和 OpenAI 做語意搜尋

在這份 notebook 你會學到：

1. 使用 OpenAI API 產生的 embedding
2. 把 embedding 存進 Neon Serverless Postgres 資料庫
3. 用 OpenAI API 把原始文字查詢轉成 embedding
4. 用 Neon 搭配 `pgvector` 擴充功能做向量相似度搜尋

## 擴充支援

Neon 讓你能用下列功能擴充 AI 應用：

- [Autoscaling](https://neon.tech/docs/introduction/read-replicas)：如果你的 AI 應用在一天中某些時段或不同時間負載很重，Neon 可以自動調整運算資源，不需要手動介入。沒有流量時，Neon 還能縮到零。
- [Instant read replicas](https://neon.tech/docs/introduction/read-replicas)：Neon 支援即時 read replica，這是獨立的唯讀運算實例，讀取的資料跟你的讀寫運算實例相同。有了 read replica，你可以把 AI 應用的讀取工作從讀寫實例分流到專用的唯讀實例。
- [Neon serverless driver](https://neon.tech/docs/serverless/serverless-driver)：Neon 提供給 JavaScript 和 TypeScript 應用使用的低延遲 serverless PostgreSQL driver，讓你能從 serverless 和 edge 環境查詢資料，查詢時間可以低於 10ms。

## 更多範例

- [Build an AI-powered semantic search application](https://github.com/neondatabase/yc-idea-matcher) - 提交一個新創點子，取得 YCombinator 以前投資過的類似點子清單
- [Build an AI-powered chatbot](https://github.com/neondatabase/ask-neon) - 把 Postgres 當作向量資料庫的 Postgres 問答聊天機器人
- [Vercel Postgres pgvector Starter](https://vercel.com/templates/next.js/postgres-pgvector) - 用 Vercel Postgres（由 Neon 提供）做向量相似度搜尋

## 其他資源

- [Building AI applications with Neon](https://neon.tech/ai)
- [Neon AI & embeddings documentation](https://neon.tech/docs/ai/ai-intro)
- [Building an AI-powered Chatbot using Vercel, OpenAI, and Postgres](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/neon/neon.tech/blog/building-an-ai-powered-chatbot-using-vercel-openai-and-postgres)
- [Web-based AI SQL Playground and connecting to Postgres from the browser](https://neon.tech/blog/postgres-ai-playground)
- [pgvector GitHub repository](https://github.com/pgvector/pgvector)

## 重點整理

- Neon 是 serverless Postgres，加上 pgvector 擴充功能就能當向量資料庫。
- 語意搜尋的流程是：產生 embedding、存進資料庫、把查詢也轉成 embedding、做相似度搜尋。
- Autoscaling 和 scale-to-zero 適合流量忽高忽低的 AI 應用。
- Read replica 可以把讀取流量從讀寫實例分出去。

## 練習

1. 照 notebook 的流程，用一小批自己的文字資料產生 embedding 並存進 Neon，確認資料表裡有向量欄位。
2. 換一個查詢句子做相似度搜尋，印出前 3 筆結果和它們的距離，觀察排序是否合理。
3. 改查詢的筆數上限（`LIMIT`），再試著對向量欄位建立索引，比較資料量變大時的查詢速度。
