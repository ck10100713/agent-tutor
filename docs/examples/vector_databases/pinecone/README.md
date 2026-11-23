---
translated: true
source: examples/vector_databases/pinecone/README.md
---

# Pinecone 向量資料庫

> 原文：[examples/vector_databases/pinecone/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/README.md)



## 這篇在做什麼

介紹 Pinecone 這個託管的向量資料庫，並列出資料夾裡搭配 OpenAI 的三個範例：GPT-4 檢索增強、生成式問答、語意搜尋。

## 學完你會

- 說明向量搜尋是什麼，Pinecone 提供了哪些好處
- 知道資料夾裡三個範例各自的用途
- 依需求挑出該先看哪一份 notebook

## 開跑前

- Pinecone 帳號（免費方案支援最多 500 萬筆向量）

[向量搜尋](https://www.pinecone.io/learn/vector-search-basics/)是一項創新技術，把複雜資料表示成數學向量，讓開發者和工程師能有效地儲存、搜尋和推薦資訊。比較這些向量之間的相似度，就能順暢、直覺地快速取得相關資訊。

[Pinecone](https://pinecone.io/) 是一個為開發者和工程師設計的[向量資料庫](https://www.pinecone.io/learn/vector-database/)。作為託管服務，它減輕了維護和工程的負擔，讓你專心從資料中挖掘有價值的洞察。免費方案最多支援 500 萬筆向量，是體驗向量搜尋功能、成本很低的入門管道。用 Pinecone，你會體驗到出色的速度、準確度和可擴展性，也能使用單階段 metadata 過濾和最先進的 sparse-dense index 等進階功能。

## 範例

這個資料夾放的是 Pinecone 和 OpenAI 搭配使用的範例，之後會陸續增加，歡迎回來看更新！

| Name | Description | Google Colab |
| --- | --- | --- |
| [GPT-4 Retrieval Augmentation](GPT4_Retrieval_Augmentation.md) | How to supercharge GPT-4 with retrieval augmentation | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/master/examples/vector_databases/pinecone/GPT4_Retrieval_Augmentation.ipynb) |
| [Generative Question-Answering](Gen_QA.md) | A simple walkthrough demonstrating the use of Generative Question-Answering | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/master/examples/vector_databases/pinecone/Gen_QA.ipynb) |
| [Semantic Search](Semantic_Search.md) | A guide to building a simple semantic search process | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/master/examples/vector_databases/pinecone/Semantic_Search.ipynb) |

## 重點整理

- 向量搜尋把資料轉成向量，靠相似度找出相關資訊。
- Pinecone 是託管服務，不用自己維運。
- 單階段 metadata 過濾可以在向量查詢時同時套條件。
- 範例從簡單的語意搜尋到檢索增強，由淺入深。

## 練習

1. 先照 Semantic Search 範例跑一遍，確認能查到結果。
2. 接著看 Gen_QA，找出檢索到的內容是在哪裡放進 prompt 的。
3. 把 GPT-4 Retrieval Augmentation 的資料換成你自己的文件。
