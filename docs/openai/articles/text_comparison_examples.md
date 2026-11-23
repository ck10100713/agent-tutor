---
translated: true
source: articles/text_comparison_examples.md
---

# Embedding 的使用情境

> 原文：[articles/text_comparison_examples.md](https://github.com/openai/openai-cookbook/blob/main/articles/text_comparison_examples.md)



## 這篇在做什麼
整理 embedding 常見的四種用途：語意搜尋、問答、推薦，以及客製化 embedding。每種用途都指到對應的範例 notebook，這篇比較像觀念地圖。

## 學完你會
- 說明語意搜尋「預先計算」和「即時計算」兩個階段各做什麼
- 知道怎麼結合搜尋結果和 prompt，讓模型根據文件回答問題
- 理解客製化 embedding 是靠訓練一個矩陣來改變向量或距離函數

[OpenAI API embeddings endpoint](https://beta.openai.com/docs/guides/embeddings) 可以用來衡量文字之間的相關性或相似度。

借助 GPT-3 對文字的理解，這些 embedding 在非監督式學習和遷移學習的 benchmark 上[達到 state-of-the-art 的結果](https://arxiv.org/abs/2201.10005)。

Embedding 可用於語意搜尋、推薦、分群分析、近似重複偵測等等。

更多資訊請看 OpenAI 的部落格公告：

- [Introducing Text and Code Embeddings (Jan 2022)](https://openai.com/blog/introducing-text-and-code-embeddings/)
- [New and Improved Embedding Model (Dec 2022)](https://openai.com/blog/new-and-improved-embedding-model/)

想跟其他 embedding 模型比較，可以看 [Massive Text Embedding Benchmark (MTEB) Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)

## 語意搜尋 (Semantic search)

Embedding 可以單獨拿來搜尋，也可以當成大型系統裡的一個 feature。

最簡單的搜尋用法如下：

- 搜尋之前（預先計算）：
  - 把文本切成比 token 上限小的 chunk（`text-embedding-3-small` 的上限是 8,191 tokens）
  - 對每個 chunk 做 embedding
  - 把 embedding 存進你自己的資料庫，或是 [Pinecone](https://www.pinecone.io)、[Weaviate](https://weaviate.io)、[Qdrant](https://qdrant.tech) 這類 vector search 服務
- 搜尋當下（即時計算）：
  - 對搜尋 query 做 embedding
  - 在資料庫找出最接近的 embedding
  - 回傳排名最前面的結果

用 embedding 做搜尋的範例在 [Semantic_text_search_using_embeddings.ipynb](../examples/Semantic_text_search_using_embeddings.md)。

在更進階的搜尋系統裡，embedding 的 cosine similarity 可以是排序結果時眾多 feature 之一。

## 問答 (Question answering)

想從 GPT-3 得到可靠、誠實的答案，最好的做法是給它來源文件，讓它能在裡面找到正確答案。用上面的語意搜尋流程，你可以低成本地在大量文件中找出相關資訊，再透過 prompt 交給 GPT-3 回答問題。範例在 [Question_answering_using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_embeddings.ipynb)。

## 推薦 (Recommendations)

推薦和搜尋很像，只是輸入不是自由文字的 query，而是集合裡的項目。

用 embedding 做推薦的範例在 [Recommendation_using_embeddings.ipynb](../examples/Recommendation_using_embeddings.md)。

跟搜尋一樣，這些 cosine similarity 分數可以直接拿來排序項目，也可以當成更大排序演算法的 feature。

## 客製化 Embedding

OpenAI 的 embedding 模型權重不能 fine-tune，但你還是可以用訓練資料來客製化 embedding，讓它更適合你的應用。

在 [Customizing_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Customizing_embeddings.ipynb) 裡，我們提供了一個用訓練資料客製化 embedding 的方法。概念是訓練一個自訂矩陣，拿 embedding 向量去乘它，得到客製化後的新 embedding。訓練資料夠好的話，這個矩陣會強調和你的訓練標籤相關的特徵。你可以把這個矩陣乘法看成 (a) 修改 embedding，或 (b) 修改用來衡量 embedding 之間距離的距離函數，兩種看法是等價的。

## 重點整理
- Embedding 把文字變成向量，用向量距離衡量語意相近程度。
- 語意搜尋分兩段：事先把文件切 chunk、embed 並存起來，搜尋時只需 embed query 再找最近的向量。
- 問答的關鍵是先檢索相關文件，再放進 prompt，這樣答案比較可靠。
- 推薦就是輸入從 query 換成項目的搜尋。
- 模型權重不能 fine-tune，但可以訓練一個矩陣來客製化 embedding。

## 練習
1. 打開語意搜尋的範例 notebook，換一個自己的 query，看回傳的前三筆是否合理。
2. 把語意搜尋範例的 chunk 大小調小一半，比較檢索結果有什麼差別。
3. 讀客製化 embedding 的 notebook，改變訓練資料的比例或標籤，觀察客製化矩陣對相似度分數的影響。
