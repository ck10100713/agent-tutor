---
translated: true
source: examples/vector_databases/weaviate/README.md
---

# Weaviate 與 OpenAI

> 原文：[examples/vector_databases/weaviate/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/README.md)

## 這篇在做什麼

介紹開源向量搜尋引擎 Weaviate，以及它跟 OpenAI embedding 搭配的幾種用法。這頁是目錄，列出三個範例（語意搜尋、hybrid search、問答）和一份 docker-compose，說明有三種方式可以跑 Weaviate。

## 學完你會

- 說得出 Weaviate 能做的三種搜尋：相似度搜尋、hybrid search、generative search
- 知道 Weaviate 的三種部署方式：Docker、Weaviate Cloud Service、Kubernetes
- 依需求挑出該看的範例，例如用 `text2vec-openai` 做語意搜尋，或用 `qna-openai` 做問答

## 開跑前

- 各範例需要 `OPENAI_API_KEY`
- 部署方式要有 Docker、Weaviate Cloud Service 帳號或 Kubernetes 叢集擇一


[​Weaviate](https://weaviate.io) 是開源的向量搜尋引擎（[docs](https://weaviate.io/developers/weaviate) - [Github](https://github.com/weaviate/weaviate)），能儲存並搜尋 OpenAI embedding _以及_資料物件。這個資料庫可以做相似度搜尋、hybrid search（結合多種搜尋技術，例如關鍵字搜尋和向量搜尋），以及 generative search（像問答）。Weaviate 也支援各式各樣以 OpenAI 為基礎的模組（例如 [`text2vec-openai`](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai)、[`qna-openai`](https://weaviate.io/developers/weaviate/modules/reader-generator-modules/qna-openai)），讓你快速有效地向量化並查詢資料。

你可以用三種方式執行 Weaviate（需要的話包含 OpenAI 模組）：

1. 在 Docker container 裡跑開源版（[範例](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/docker-compose.yml)）
2. 使用 Weaviate Cloud Service（[開始使用](https://weaviate.io/developers/weaviate/quickstart/installation#weaviate-cloud-service)）
3. 在 Kubernetes 叢集裡（[了解更多](https://weaviate.io/developers/weaviate/installation/kubernetes)）

### 範例

這個資料夾包含各式各樣的 Weaviate 與 OpenAI 範例。

| Name | Description | language | Google Colab |
| --- | --- | --- | --- |
| [Getting Started with Weaviate and OpenAI](getting-started-with-weaviate-and-openai.md) | A simple getting started for *semantic vector search* using the OpenAI vectorization module in Weaviate (`text2vec-openai`) | Python Notebook | [link](https://colab.research.google.com/drive/1RxpDE_ruCnoBB3TfwAZqdjYgHJhtdwhK) |
| [Hybrid Search with Weaviate and OpenAI](hybrid-search-with-weaviate-and-openai.md) | A simple getting started for *hybrid search* using the OpenAI vectorization module in Weaviate (`text2vec-openai`) | Python Notebook | [link](https://colab.research.google.com/drive/1E75BALWoKrOjvUhaznJKQO0A-B1QUPZ4) |
| [Question Answering with Weaviate and OpenAI](question-answering-with-weaviate-and-openai.md) | A simple getting started for *question answering (Q&A)* using the OpenAI Q&A module in Weaviate (`qna-openai`) | Python Notebook | [link](https://colab.research.google.com/drive/1pUerUZrJaknEboDxDxsuf3giCK0MJJgm) |
| [Docker-compose example](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/docker-compose.yml) | A Docker-compose file with all OpenAI modules enabled | Docker |

## 重點整理

- Weaviate 同時存 embedding 和資料物件，支援相似度、hybrid 和 generative 三種搜尋。
- hybrid search 結合關鍵字搜尋和向量搜尋，適合只靠語意會漏掉精確字詞的情況。
- OpenAI 模組（`text2vec-openai`、`qna-openai`）讓 Weaviate 自己負責向量化與問答，不用你另外呼叫 API。
- 部署可選 Docker、雲端服務或 Kubernetes，測試時 Docker 最快。

## 練習

1. 照 docker-compose 範例，在本機起一個啟用 OpenAI 模組的 Weaviate，並確認服務有回應。
2. 跑 Getting Started 範例，把查詢字串換成你自己的主題，觀察語意搜尋的結果。
3. 比較同一個查詢在語意搜尋和 hybrid search 範例裡的結果差異，找出一個 hybrid 明顯比較好的例子。
