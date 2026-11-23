---
translated: true
source: examples/vector_databases/supabase/README.md
---
# Supabase 向量資料庫

> 原文：[examples/vector_databases/supabase/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/supabase/README.md)



## 這篇在做什麼

這是 Supabase Vector 的簡介頁，說明怎麼把 OpenAI embedding 存進 Postgres，用 pgvector 做向量搜尋。頁面本身沒有程式碼，主要是導覽和資源連結。

## 學完你會

- 知道 Supabase、Postgres 和 pgvector 各自負責什麼。
- 知道 Supabase 在 Postgres 之外提供哪些服務（REST、GraphQL、Realtime、Auth、Storage、Edge functions），可以跟向量搜尋搭配。
- 找得到 Supabase 搭配 OpenAI embedding 的語意搜尋範例和進階文件。

## 開跑前

要實際動手需要 Supabase 帳號（或自架），以及 OpenAI API key。

[Supabase](https://supabase.com/docs) 是開源的 Firebase 替代方案，底層是 [Postgres](https://en.wikipedia.org/wiki/PostgreSQL)，一個可以上 production 的 SQL 資料庫。

[Supabase Vector](https://supabase.com/docs/guides/ai) 是建在 [pgvector](https://github.com/pgvector/pgvector) 上的向量工具組。pgvector 是 Postgres 的擴充套件，讓你把 embedding 跟應用程式其他資料放在同一個資料庫裡。搭配 pgvector 的索引演算法，資料量大的時候向量搜尋還是[很快](https://supabase.com/blog/increase-performance-pgvector-hnsw)。

Supabase 在 Postgres 上面加了一整套服務和工具，讓開發 app 更快，包括：

- [Auto-generated REST APIs](https://supabase.com/docs/guides/api)
- [Auto-generated GraphQL APIs](https://supabase.com/docs/guides/graphql)
- [Realtime APIs](https://supabase.com/docs/guides/realtime)
- [Authentication](https://supabase.com/docs/guides/auth)
- [File storage](https://supabase.com/docs/guides/storage)
- [Edge functions](https://supabase.com/docs/guides/functions)

這些服務可以跟 pgvector 一起用，在 Postgres 裡儲存和查詢 embedding。

## OpenAI Cookbook 範例

下面是教你怎麼用 OpenAI embedding 模型搭配 Supabase Vector 的指南和資源。

| Guide                                    | Description                                                |
| ---------------------------------------- | ---------------------------------------------------------- |
| [Semantic search](semantic-search.md) | Store, index, and query embeddings at scale using pgvector |

## 其他資源

- [Vector columns](https://supabase.com/docs/guides/ai/vector-columns)
- [Vector indexes](https://supabase.com/docs/guides/ai/vector-indexes)
- [RAG with permissions](https://supabase.com/docs/guides/ai/rag-with-permissions)
- [Going to production](https://supabase.com/docs/guides/ai/going-to-prod)
- [Deciding on compute](https://supabase.com/docs/guides/ai/choosing-compute-addon)

## 重點整理

- Supabase 底層就是 Postgres，向量功能靠 pgvector 擴充套件提供。
- embedding 跟業務資料放同一個資料庫，不用另外維護一套向量資料庫。
- 加上索引（例如 HNSW）後，大量資料的向量搜尋仍然夠快。
- Supabase 的 Auth、Storage、REST API 等服務可以直接跟向量查詢組合起來用。

## 練習

1. 打開 [Vector columns](https://supabase.com/docs/guides/ai/vector-columns)，找出怎麼在資料表加一個 `vector(1536)` 欄位，並說明 1536 這個數字對應哪個 embedding 模型的維度。
2. 讀 [Vector indexes](https://supabase.com/docs/guides/ai/vector-indexes)，比較 HNSW 和 IVFFlat 的差別，寫下你的資料量下會選哪個。
3. 照 [Semantic search](semantic-search.md) 的流程跑一次，再讀 [RAG with permissions](https://supabase.com/docs/guides/ai/rag-with-permissions)，想想怎麼讓不同使用者只搜尋得到自己有權限的文件。
