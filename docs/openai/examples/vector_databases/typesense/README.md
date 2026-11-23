---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/typesense/README.md
---

# Typesense

> 原文：[examples/vector_databases/typesense/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/typesense/README.md)



## 這篇在做什麼

介紹 Typesense，一個開源、全放在記憶體的搜尋引擎，說明為什麼它適合搭配 OpenAI embedding 做向量搜尋，並指向實際範例 notebook 和官方文件。

## 學完你會

- 說出 Typesense 的特色：索引放 RAM、預設值友善、可以結合屬性過濾和向量查詢
- 知道除了向量搜尋，它還有哪些現成功能可用
- 找到範例 notebook 和向量搜尋文件

## 開跑前

- 自己架設 Typesense，或使用 Typesense Cloud 帳號

Typesense 是開源的記憶體內搜尋引擎，你可以[自己架設](https://typesense.org/docs/guide/install-typesense.html#option-2-local-machine-self-hosting)，也可以跑在 [Typesense Cloud](https://cloud.typesense.org/) 上。

## 為什麼選 Typesense？

Typesense 注重效能，把整個索引存在 RAM 裡（磁碟上有備份），也注重開箱即用的開發體驗，簡化可用選項並提供好的預設值。

它也讓你把屬性過濾和向量查詢結合起來，取得最相關的文件。

### 其他功能

除了向量儲存與搜尋，Typesense 還提供下面這些功能：

- Typo Tolerance：開箱即用，能妥善處理打錯字。
- Tunable Ranking：輕鬆把搜尋結果調到最合適。
- Sorting：查詢時動態依某個欄位排序（像「價格由低到高」這種功能很有用）。
- Faceting & Filtering：逐層鑽研、縮小結果。
- Grouping & Distinct：把相似結果分組，呈現更多樣的內容。
- Federated Search：單一 HTTP 請求就能跨多個 collection（索引）搜尋。
- Scoped API Keys：產生只允許存取特定資料的 API key，適合多租戶應用。
- Synonyms：把詞定義為彼此等價，搜尋一個詞時也會回傳同義詞的結果。
- Curation & Merchandizing：把特定記錄固定提升到搜尋結果的某個位置，用來主打。
- Raft-based Clustering：架設高可用的分散式叢集。
- Seamless Version Upgrades：新版本出來時，升級只要換掉執行檔再重啟 Typesense。
- No Runtime Dependencies：Typesense 是單一執行檔，一個指令就能在本機或正式環境執行。

## 怎麼用

- 想了解怎麼用 Typesense 搭配 OpenAI embedding，請看這個範例 notebook：[examples/vector_databases/Using_vector_databases_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/Using_vector_databases_for_embeddings_search.ipynb)
- 想進一步了解 Typesense 的向量搜尋功能，請看文件：[https://typesense.org/docs/0.24.1/api/vector-search.html](https://typesense.org/docs/0.24.1/api/vector-search.html)。

## 重點整理

- Typesense 把索引放在記憶體，主打速度和好上手。
- 向量查詢可以跟屬性過濾組合，不用先搜完再自己篩。
- 它同時是完整的搜尋引擎，打錯字容忍、排序、facet 這些功能都內建。
- 單一執行檔、無執行期相依，部署和升級都簡單。

## 練習

1. 打開範例 notebook，找出它建立 collection 時，向量欄位是怎麼定義的。
2. 在範例的查詢加上一個屬性過濾條件，看結果怎麼被縮小。
3. 讀向量搜尋文件，試著列出查詢向量時可以調整的參數。
