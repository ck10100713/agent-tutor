---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/third_party/financial_document_analysis_with_llamaindex.ipynb
---

# 用 LlamaIndex 做財報文件分析

> 原文：[examples/third_party/financial_document_analysis_with_llamaindex.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/financial_document_analysis_with_llamaindex.ipynb)



## 這篇在做什麼
用 [**LlamaIndex**](https://gpt-index.readthedocs.io/en/latest/) 框架，只寫幾行程式就對 Uber 和 Lyft 的 10-K 財報做分析。從單一文件的簡單問答，到跨文件比較的進階問答。

## 學完你會
- 載入 PDF 並建立 in-memory 的 `VectorStoreIndex`
- 設定 `QueryEngine`，用 `similarity_top_k` 控制檢索的 chunk 數量
- 用 `SubQuestionQueryEngine` 把比較類的複雜問題拆成子問題，跨多份文件回答

## 開跑前
需要 OpenAI API key。PDF 每份超過 100 頁，載入和建索引（要呼叫 OpenAI API 算 embedding）都會花一些時間。

這份範例 notebook 示範怎麼用 [**LlamaIndex**](https://gpt-index.readthedocs.io/en/latest/) 框架，只寫幾行程式就對 [**10-K**](https://en.wikipedia.org/wiki/Form_10-K) 文件做財務分析。

## Notebook 大綱
* [簡介](#Introduction)
* [環境設定](#Setup)
* [資料載入與索引](#Data-Loading-and-Indexing)
* [簡單問答](#Simple-QA)
* [進階問答：比較與對照](#Advanced-QA---Compare-and-Contrast)


## 簡介

### LLamaIndex
[LlamaIndex](https://gpt-index.readthedocs.io/en/latest/) 是 LLM 應用的資料框架。
只要幾行程式就能開始，幾分鐘內就能建出一個 retrieval-augmented generation (RAG) 系統。
對進階使用者，LlamaIndex 提供豐富的工具組，用來匯入和索引資料，還有檢索和 re-ranking 的模組，以及可組合的元件來建構自訂的 query engine。

更多細節請看[完整文件](https://gpt-index.readthedocs.io/en/latest/)。

### 10-K 文件的財務分析
財務分析師工作的一大部分，是從冗長的財務文件裡抽取資訊並整合出洞見。
10-K 表格就是很好的例子，這是美國證券交易委員會 (SEC) 要求的年度報告，全面總結公司的財務表現。
這類文件通常長達數百頁，還有領域專用術語，外行人很難快速消化。


我們示範 LlamaIndex 怎麼用很少的程式碼，幫財務分析師快速抽取資訊，並**跨多份文件**整合出洞見。

## 環境設定

首先要安裝 llama-index 函式庫

```python
!pip install llama-index pypdf
```

接著匯入這份教學用到的所有模組

```python
from langchain import OpenAI

from llama_index import SimpleDirectoryReader, ServiceContext, VectorStoreIndex
from llama_index import set_global_service_context
from llama_index.response.pprint_utils import pprint_response
from llama_index.tools import QueryEngineTool, ToolMetadata
from llama_index.query_engine import SubQuestionQueryEngine
```

開始之前，可以先設定驅動 RAG 系統的 LLM 供應商和模型。
這裡我們選 OpenAI 的 `gpt-3.5-turbo-instruct`。

```python
llm = OpenAI(temperature=0, model_name="gpt-3.5-turbo-instruct", max_tokens=-1)
```

我們建立一個 `ServiceContext` 並設成全域預設，之後所有依賴 LLM 呼叫的操作，都會使用我們在這裡設定的模型。

```python
service_context = ServiceContext.from_defaults(llm=llm)
set_global_service_context(service_context=service_context)
```

## 資料載入與索引

現在載入並解析 2 份 PDF（一份是 Uber 2021 年的 10-K，另一份是 Lyft 2021 年的 10-K）。
底層會把 PDF 轉成純文字的 `Document` 物件，按頁分開。

> 注意：每份文件都超過 100 頁，這個操作可能要跑一段時間。

```python
lyft_docs = SimpleDirectoryReader(input_files=["../data/10k/lyft_2021.pdf"]).load_data()
uber_docs = SimpleDirectoryReader(input_files=["../data/10k/uber_2021.pdf"]).load_data()
```

```python
print(f'Loaded lyft 10-K with {len(lyft_docs)} pages')
print(f'Loaded Uber 10-K with {len(uber_docs)} pages')
```

??? note "輸出"

    ```text
    Loaded lyft 10-K with 238 pages
    Loaded Uber 10-K with 307 pages
    ```

現在可以對載入的文件建立一個（in-memory 的）`VectorStoreIndex`。

> 注意：這個操作要呼叫 OpenAI API 對文件 chunk 計算向量 embedding，所以可能要跑一段時間。

```python
lyft_index = VectorStoreIndex.from_documents(lyft_docs)
uber_index = VectorStoreIndex.from_documents(uber_docs)
```

## 簡單問答

現在可以對我們的索引跑一些查詢了！
做法是先設定一個 `QueryEngine`，它只是記錄我們想怎麼查詢底層索引的一組設定。

對 `VectorStoreIndex` 來說，最常調整的設定是 `similarity_top_k`，它控制要檢索多少個文件 chunk（我們稱為 `Node` 物件）當 context 來回答問題。

```python
lyft_engine = lyft_index.as_query_engine(similarity_top_k=3)
```

```python
uber_engine = uber_index.as_query_engine(similarity_top_k=3)
```

來看幾個實際的查詢！

```python
response = await lyft_engine.aquery('What is the revenue of Lyft in 2021? Answer in millions with page reference')
```

```python
print(response)
```

??? note "輸出"

    ```text

    $3,208.3 million (page 63)
    ```

```python
response = await uber_engine.aquery('What is the revenue of Uber in 2021? Answer in millions, with page reference')
```

```python
print(response)
```

??? note "輸出"

    ```text

    $17,455 (page 53)
    ```

## 進階問答：比較與對照

比較複雜的財務分析常需要參考多份文件。

舉例來說，我們看看怎麼對 Lyft 和 Uber 的財務資料做比較對照的查詢。
為此我們建立一個 `SubQuestionQueryEngine`，它會把複雜的比較對照查詢，拆成比較簡單的子問題，分別交給各自由單一索引支撐的子 query engine 執行。

```python
query_engine_tools = [
    QueryEngineTool(
        query_engine=lyft_engine, 
        metadata=ToolMetadata(name='lyft_10k', description='Provides information about Lyft financials for year 2021')
    ),
    QueryEngineTool(
        query_engine=uber_engine, 
        metadata=ToolMetadata(name='uber_10k', description='Provides information about Uber financials for year 2021')
    ),
]

s_engine = SubQuestionQueryEngine.from_defaults(query_engine_tools=query_engine_tools)
```

來看這些查詢的實際效果！

```python
response = await s_engine.aquery('Compare and contrast the customer segments and geographies that grew the fastest')
```

??? note "輸出"

    ```text
    Generated 4 sub questions.
    [uber_10k] Q: What customer segments grew the fastest for Uber
    [uber_10k] A: in 2021?

    The customer segments that grew the fastest for Uber in 2021 were its Mobility Drivers, Couriers, Riders, and Eaters. These segments experienced growth due to the continued stay-at-home order demand related to COVID-19, as well as Uber's introduction of its Uber One, Uber Pass, Eats Pass, and Rides Pass membership programs. Additionally, Uber's marketplace-centric advertising helped to connect merchants and brands with its platform network, further driving growth.
    [uber_10k] Q: What geographies grew the fastest for Uber
    [uber_10k] A: 
    Based on the context information, it appears that Uber experienced the most growth in large metropolitan areas, such as Chicago, Miami, New York City, Sao Paulo, and London. Additionally, Uber experienced growth in suburban and rural areas, as well as in countries such as Argentina, Germany, Italy, Japan, South Korea, and Spain.
    [lyft_10k] Q: What customer segments grew the fastest for Lyft
    [lyft_10k] A: 
    The customer segments that grew the fastest for Lyft were ridesharing, light vehicles, and public transit. Ridesharing grew as Lyft was able to predict demand and proactively incentivize drivers to be available for rides in the right place at the right time. Light vehicles grew as users were looking for options that were more active, usually lower-priced, and often more efficient for short trips during heavy traffic. Public transit grew as Lyft integrated third-party public transit data into the Lyft App to offer users a robust view of transportation options around them.
    [lyft_10k] Q: What geographies grew the fastest for Lyft
    [lyft_10k] A: 
    It is not possible to answer this question with the given context information.
    ```

```python
print(response)
```

??? note "輸出"

    ```text

    The customer segments that grew the fastest for Uber in 2021 were its Mobility Drivers, Couriers, Riders, and Eaters. These segments experienced growth due to the continued stay-at-home order demand related to COVID-19, as well as Uber's introduction of its Uber One, Uber Pass, Eats Pass, and Rides Pass membership programs. Additionally, Uber's marketplace-centric advertising helped to connect merchants and brands with its platform network, further driving growth. Uber experienced the most growth in large metropolitan areas, such as Chicago, Miami, New York City, Sao Paulo, and London. Additionally, Uber experienced growth in suburban and rural areas, as well as in countries such as Argentina, Germany, Italy, Japan, South Korea, and Spain.

    The customer segments that grew the fastest for Lyft were ridesharing, light vehicles, and public transit. Ridesharing grew as Lyft was able to predict demand and proactively incentivize drivers to be available for rides in the right place at the right time. Light vehicles grew as users were looking for options that were more active, usually lower-priced, and often more efficient for short trips during heavy traffic. Public transit grew as Lyft integrated third-party public transit data into the Lyft App to offer users a robust view of transportation options around them. It is not possible to answer the question of which geographies grew the fastest for Lyft with the given context information.

    In summary, Uber and Lyft both experienced growth in customer segments related to mobility, couriers, riders, and eaters. Uber experienced the most growth in large metropolitan areas, as well as in suburban and rural areas, and in countries such as Argentina, Germany, Italy, Japan, South Korea, and Spain. Lyft experienced the most growth in ridesharing, light vehicles, and public transit. It is not possible to answer the question of which geographies grew the fastest for Lyft with the given context information.
    ```

```python
response = await s_engine.aquery('Compare revenue growth of Uber and Lyft from 2020 to 2021')
```

??? note "輸出"

    ```text
    Generated 2 sub questions.
    [uber_10k] Q: What is the revenue growth of Uber from 2020 to 2021
    [uber_10k] A: 
    The revenue growth of Uber from 2020 to 2021 was 57%, or 54% on a constant currency basis.
    [lyft_10k] Q: What is the revenue growth of Lyft from 2020 to 2021
    [lyft_10k] A: 
    The revenue growth of Lyft from 2020 to 2021 is 36%, increasing from $2,364,681 thousand to $3,208,323 thousand.
    ```

```python
print(response)
```

??? note "輸出"

    ```text

    The revenue growth of Uber from 2020 to 2021 was 57%, or 54% on a constant currency basis, while the revenue growth of Lyft from 2020 to 2021 was 36%. This means that Uber had a higher revenue growth than Lyft from 2020 to 2021.
    ```

## 重點整理
- LlamaIndex 把載入文件、切 chunk、算 embedding、建索引、查詢包成幾行程式。
- `QueryEngine` 只是查詢設定，`similarity_top_k` 決定每次檢索多少個 chunk 當 context。
- 長文件（像 10-K）按頁切成 `Document`，再建成向量索引來檢索。
- 跨文件比較的問題適合用 `SubQuestionQueryEngine` 拆成子問題，各自查詢再整合。

## 練習
1. 調整 `similarity_top_k`（例如 1 和 5），比較同一個問題的回答差異。
2. 把 `gpt-3.5-turbo-instruct` 換成別的 OpenAI 模型，看回答品質有沒有變化。
3. 在子問題引擎裡再加入第三家公司的 10-K，問一個三家公司的比較問題。
