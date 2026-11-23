---
translated: true
source: examples/vector_databases/SingleStoreDB/README.md
---

# SingleStoreDB

> 原文：[examples/vector_databases/SingleStoreDB/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/SingleStoreDB/README.md)



## 這篇在做什麼
這篇介紹 SingleStoreDB 的向量搜尋能力，以及這個資料夾裡搭配 OpenAI 的範例。
SingleStoreDB 透過 [Vector Functions](https://docs.singlestore.com/managed-service/en/reference/sql-reference/vector-functions.html) 原生支援向量搜尋，可以用 SQL 做很快的 nearest-neighbor 搜尋，找出語意相近的物件。

## 學完你會
- 知道 SingleStoreDB 用 dot_product 和 euclidean_distance 做向量相似度搜尋。
- 了解這類向量搜尋常見的應用，例如人臉辨識、商品圖片搜尋、文字語意搜尋。
- 找到對應的範例 notebook，實作用語意搜尋提升 QA 的準確度。

**[SingleStoreDB](https://singlestore.com)** 透過 [Vector Functions](https://docs.singlestore.com/managed-service/en/reference/sql-reference/vector-functions.html) 提供一級的向量搜尋支援。我們的向量資料庫子系統在 2017 年首度推出，之後持續強化，讓你用 SQL 就能做極快的 nearest-neighbor 搜尋，找出語意相似的物件。

SingleStoreDB 支援向量，以及用 dot_product（用於 cosine similarity）和 euclidean_distance 函式做的向量相似度搜尋。客戶用這些函式做人臉辨識、商品圖片搜尋，以及以文字為基礎的語意搜尋。隨著生成式 AI 技術爆發，這些能力成為文字型 AI 聊天機器人的穩固基礎。

不過別忘了，SingleStoreDB 是高效能、可擴充的現代 SQL DBMS，支援多種資料模型，包括結構化資料、以 JSON 為基礎的半結構化資料、時間序列、全文檢索、空間資料、key-value，當然還有向量資料。現在就用 SingleStoreDB 來驅動你的下一個智慧應用吧。

![SingleStore Open AI](https://user-images.githubusercontent.com/8846480/236985121-48980956-fdc5-49c8-b006-f3a412142676.png)

## 範例

這個資料夾放的是 SingleStoreDB 搭配 OpenAI 的範例，之後還會持續新增情境。

| Name | Description |
| --- | --- |
| [OpenAI wikipedia semantic search](OpenAI_wikipedia_semantic_search.md) | 在 QA 中透過 SingleStoreDB 語意搜尋提升 ChatGPT 的準確度 |

## 重點整理
- SingleStoreDB 把向量搜尋放進 SQL 資料庫，不需要另外維護一套向量資料庫。
- 向量相似度靠 dot_product 和 euclidean_distance 兩個函式。
- 同一個資料庫同時能放結構化、JSON、全文、時間序列和向量，混合查詢比較方便。
- 語意搜尋拿來給 LLM 補上下文，是提升 QA 準確度的常見做法。

## 練習
1. 打開 OpenAI wikipedia semantic search 範例，找出它用 dot_product 還是 euclidean_distance。
2. 把範例裡的查詢問題換成你自己的，看回傳的結果合不合理。
3. 把相似度函式換成另一個，比較兩者排序結果的差異。
