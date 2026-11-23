---
translated: true
source: examples/vector_databases/kusto/README.md
---

# 把 Kusto 當向量資料庫

> 原文：[examples/vector_databases/kusto/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/kusto/README.md)



## 這篇在做什麼
介紹怎麼把 Azure Data Explorer（Kusto）當向量資料庫，存 OpenAI 產生的 embedding，並用內建函式做 cosine similarity 搜尋。這一頁是概覽，實作步驟在另一份 Notebook。

## 學完你會
- 說明為什麼 Kusto 的 dynamic 資料型態適合存向量
- 知道 `series_cosine_similarity_fl` 用來做向量相似度搜尋
- 描述用 Kusto 加 OpenAI embedding 做語意搜尋的四個步驟

## 開跑前
- Azure Data Explorer（Kusto）帳號，可以免費開始
- OpenAI API key，用來產生 embedding


[Azure Data Explorer aka Kusto](https://azure.microsoft.com/en-us/products/data-explorer) 是雲端資料分析服務，讓使用者能對大型資料集做即時進階分析。它特別適合處理大量資料，所以很適合用來儲存和搜尋向量。

Kusto 支援一種特別的資料型態叫 dynamic，可以存陣列、屬性包這類非結構化資料。[Dynamic data type](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/query/scalar-data-types/dynamic) 很適合存向量值。你還可以把原始物件相關的 metadata 存成資料表中獨立的欄位，來擴充向量值。  
Kusto 也支援內建函式 [series_cosine_similarity_fl](https://learn.microsoft.com/en-us/azure/data-explorer/kusto/functions-library/series-cosine-similarity-fl)，用來做向量相似度搜尋。

[免費開始](https://aka.ms/kustofree)使用 Kusto。 

![Kusto_Vector](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/vector_databases/kusto/images/kusto_vector_db.png)

## 開始用 Kusto 和 Open AI embedding

### Demo 情境

![Wiki_embeddings](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/vector_databases/kusto/images/wiki_embeddings.png)

![semantic_search_flow](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/vector_databases/kusto/images/semantic_search_user_flow.png)

想試這個 demo 的話，請照 [Notebook](Getting_started_with_kusto_and_openai_embeddings.md) 裡的說明操作。

它會讓你：  

1. 使用 OpenAI API 建立好的預先計算 embedding。 

2. 把 embedding 存進 Kusto。 

3. 用 OpenAI API 把原始文字查詢轉成 embedding。 

4. 用 Kusto 對存好的 embedding 做 cosine similarity 搜尋。

## 重點整理
- Kusto 擅長處理大量資料，適合拿來存和搜尋向量。
- dynamic 型態可以存向量陣列，metadata 則放在旁邊的獨立欄位。
- 相似度搜尋用內建函式 `series_cosine_similarity_fl`，不需要另外裝向量資料庫。
- 語意搜尋的流程是：存 embedding、把查詢轉成 embedding、再做 cosine similarity。

## 練習
1. 照 Notebook 跑一遍，確認四個步驟各自對應哪一段程式。
2. 在資料表多加一個 metadata 欄位（例如文章標題），查詢結果一併顯示。
3. 換一個自己的查詢句子，看相似度排名最前面的結果是否合理。
