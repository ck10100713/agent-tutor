---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/elasticsearch/elasticsearch-retrieval-augmented-generation.ipynb
---
# 用 Elasticsearch 和 OpenAI 做 retrieval augmented generation

> 原文：[examples/vector_databases/elasticsearch/elasticsearch-retrieval-augmented-generation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-retrieval-augmented-generation.ipynb)



## 這篇在做什麼

把 OpenAI 的 Wikipedia embedding 資料集索引進 Elasticsearch，用 embedding 把問題轉成向量做 kNN 語意搜尋，再把最相關的結果交給 Chat Completions API 產生回答。這就是一個完整的 RAG 流程，檢索交給 Elasticsearch，生成交給 LLM。

## 學完你會

- 在 Elasticsearch 建立含 `dense_vector` 欄位的 index，並用 bulk API 分批寫入資料。
- 用 `text-embedding-3-small` 把問題編碼，對 index 跑 kNN 語意搜尋。
- 把最高分的搜尋結果當 context，用 `messages` 的 system 和 user 訊息組成 RAG prompt 送給 `gpt-3.5-turbo`。

## 開跑前

- 需要 Elasticsearch 部署，這篇用的是 Elastic Cloud，沒有的話可以註冊免費的 [Elastic Cloud trial](https://cloud.elastic.co/registration?utm_source=github&utm_content=openai-cookbook)，並準備好 Cloud ID 和密碼。
- 需要 OpenAI API key。

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-retrieval-augmented-generation.ipynb)


這份 notebook 示範如何：
- 把 OpenAI Wikipedia vector 資料集索引進 Elasticsearch
- 用 OpenAI [`embeddings`](https://platform.openai.com/docs/api-reference/embeddings) endpoint 把問題轉成 embedding
- 用編碼後的問題，在 Elasticsearch index 上做 semantic search
- 把排名最前面的搜尋結果送到 OpenAI [Chat Completions](https://platform.openai.com/docs/guides/gpt/chat-completions-api) API endpoint，做 retrieval augmented generation（RAG）

ℹ️ 如果你已經做過我們的 semantic search notebook，可以直接跳到最後一步！

## 安裝套件並匯入模組

```python
# install packages

!python3 -m pip install -qU openai pandas wget elasticsearch

# import modules

from getpass import getpass
from elasticsearch import Elasticsearch, helpers
import wget
import zipfile
import pandas as pd
import json
import openai
```

## 連接 Elasticsearch

ℹ️ 這份 notebook 用的是 Elastic Cloud 上的 Elasticsearch 部署。
如果你還沒有 Elastic 部署，可以註冊免費的 [Elastic Cloud trial](https://cloud.elastic.co/registration?utm_source=github&utm_content=openai-cookbook)。

要連接 Elasticsearch，需要用你部署的 Cloud ID 和密碼建立一個 client instance。

到 https://cloud.elastic.co/deployments 選擇你的部署，就能找到 Cloud ID。

```python
CLOUD_ID = getpass("Elastic deployment Cloud ID")
CLOUD_PASSWORD = getpass("Elastic deployment Password")
client = Elasticsearch(
  cloud_id = CLOUD_ID,
  basic_auth=("elastic", CLOUD_PASSWORD) # Alternatively use `api_key` instead of `basic_auth`
)

# Test connection to Elasticsearch
print(client.info())
```

??? note "輸出"

    ```text
    {'name': 'instance-0000000001', 'cluster_name': '29ef9817e13142f5ba0ea7b29c2a86e2', 'cluster_uuid': 'absjWgQvRw63IlwWKisN8w', 'version': {'number': '8.9.1', 'build_flavor': 'default', 'build_type': 'docker', 'build_hash': 'a813d015ef1826148d9d389bd1c0d781c6e349f0', 'build_date': '2023-08-10T05:02:32.517455352Z', 'build_snapshot': False, 'lucene_version': '9.7.0', 'minimum_wire_compatibility_version': '7.17.0', 'minimum_index_compatibility_version': '7.0.0'}, 'tagline': 'You Know, for Search'}
    ```

## 下載資料集

這一步下載 OpenAI Wikipedia embeddings 資料集，並解壓縮 zip 檔。

```python
embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'
wget.download(embeddings_url)

with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip",
"r") as zip_ref:
    zip_ref.extractall("data")
```

## 把 CSV 檔讀進 Pandas DataFrame

接著用 Pandas 把解壓後的 CSV 檔讀成 DataFrame。這樣之後比較容易批次索引進 Elasticsearch。

```python

wikipedia_dataframe = pd.read_csv("data/vector_database_wikipedia_articles_embedded.csv")
```

## 建立含 mapping 的 index

現在需要建立一個帶有必要 mapping 的 Elasticsearch index，這樣才能把資料索引進去。

`title_vector` 和 `content_vector` 欄位用 `dense_vector` 欄位型別。這是一種特殊的欄位型別，讓我們可以在 Elasticsearch 儲存 dense vector。

之後做 kNN 搜尋時，會需要指定這個 `dense_vector` 欄位。


```python
index_mapping= {
    "properties": {
      "title_vector": {
          "type": "dense_vector",
          "dims": 1536,
          "index": "true",
          "similarity": "cosine"
      },
      "content_vector": {
          "type": "dense_vector",
          "dims": 1536,
          "index": "true",
          "similarity": "cosine"
      },
      "text": {"type": "text"},
      "title": {"type": "text"},
      "url": { "type": "keyword"},
      "vector_id": {"type": "long"}
      
    }
}

client.indices.create(index="wikipedia_vector_index", mappings=index_mapping)
```

## 把資料索引進 Elasticsearch

下面的函式會產生所需的 bulk action，可以傳給 Elasticsearch 的 Bulk API，一次請求就能有效率地索引多筆文件。

對 DataFrame 的每一列，這個函式會 yield 一個代表單筆待索引文件的 dictionary。

```python
def dataframe_to_bulk_actions(df):
    for index, row in df.iterrows():
        yield {
            "_index": 'wikipedia_vector_index',
            "_id": row['id'],
            "_source": {
                'url' : row["url"],
                'title' : row["title"],
                'text' : row["text"],
                'title_vector' : json.loads(row["title_vector"]),
                'content_vector' : json.loads(row["content_vector"]),
                'vector_id' : row["vector_id"]
            }
        }
```

因為 dataframe 很大，我們每批 `100` 筆分批索引。用 Python client 的 bulk API [helpers](https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/client-helpers.html#bulk-helpers) 把資料索引進 Elasticsearch。

```python
start = 0
end = len(wikipedia_dataframe)
batch_size = 100
for batch_start in range(start, end, batch_size):
    batch_end = min(batch_start + batch_size, end)
    batch_dataframe = wikipedia_dataframe.iloc[batch_start:batch_end]
    actions = dataframe_to_bulk_actions(batch_dataframe)
    helpers.bulk(client, actions)
```

用一個簡單的 match query 測試 index。

```python
print(client.search(index="wikipedia_vector_index", body={
    "_source": {
        "excludes": ["title_vector", "content_vector"]
    },
    "query": {
        "match": {
            "text": {
                "query": "Hummingbird"
            }
        }
    }
}))
```

??? note "輸出"

    ```text
    /var/folders/vz/v2f6_x6s0kg51j2vbm5rlhww0000gn/T/ipykernel_27978/2105931364.py:1: DeprecationWarning: The 'body' parameter is deprecated and will be removed in a future version. Instead use individual parameters.
      print(client.search(index="wikipedia_vector_index", body={
    ```

## 用 OpenAI embedding 模型編碼問題

要做 kNN 搜尋，查詢必須用跟索引文件時相同的 embedding 模型編碼。
這個例子要用 `text-embedding-3-small` 模型。

產生 embedding 需要你的 OpenAI [API key](https://platform.openai.com/account/api-keys)。

```python
# Get OpenAI API key
OPENAI_API_KEY = getpass("Enter OpenAI API key")

# Set API key
openai.api_key = OPENAI_API_KEY

# Define model
EMBEDDING_MODEL = "text-embedding-3-small"

# Define question
question = 'Is the Atlantic the biggest ocean in the world?'

# Create embedding
question_embedding = openai.Embedding.create(input=question, model=EMBEDDING_MODEL)
```

## 執行 semantic search 查詢

現在可以用編碼後的問題對 Elasticsearch index 跑查詢了。我們會做 k-nearest neighbors 搜尋，用 Elasticsearch 的 [kNN query](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html) 選項。

先定義一個小函式來漂亮地印出結果。

```python
# Function to pretty print Elasticsearch results

def pretty_response(response):
    for hit in response['hits']['hits']:
        id = hit['_id']
        score = hit['_score']
        title = hit['_source']['title']
        text = hit['_source']['text']
        pretty_output = (f"\nID: {id}\nTitle: {title}\nSummary: {text}\nScore: {score}")
        print(pretty_output)
```

接著執行 `kNN` 查詢。

```python
response = client.search(
  index = "wikipedia_vector_index",
  knn={
      "field": "content_vector",
      "query_vector":  question_embedding["data"][0]["embedding"],
      "k": 10,
      "num_candidates": 100
    }
)
pretty_response(response)

top_hit_summary = response['hits']['hits'][0]['_source']['text'] # Store content of top hit for final step
```

??? note "輸出"

    ```text

    ID: 1936
    Title: Atlantic Ocean
    Summary: The Atlantic Ocean is the world's second largest ocean.  It covers a total area of about . It covers about 20 percent of the Earth's surface. It is named after the god Atlas from Greek mythology.

    Geologic history 
    The Atlantic formed when the Americas moved west from Eurasia and Africa. This began sometime in the Cretaceous period, roughly 135 million years ago. It was part of the break-up of the supercontinent Pangaea.

    The east coast of South America is shaped somewhat like the west coast of Africa, and this gave a clue that continents moved over long periods of time (continental drift). The Atlantic Ocean is still growing now, because of sea-floor spreading from the mid-Atlantic Ridge, while the Pacific Ocean is said to be shrinking because the sea floor is folding under itself or subducting into the mantle.

    Geography
    The Atlantic Ocean is bounded on the west by North and South America. It connects to the Arctic Ocean through the Denmark Strait, Greenland Sea, Norwegian Sea and Barents Sea. It connects with the Mediterranean Sea through the Strait of Gibraltar.

    In the southeast, the Atlantic merges into the Indian Ocean. The 20° East meridian defines its border.

    In the southwest, the Drake Passage connects it to the Pacific Ocean. The Panama Canal links the Atlantic and Pacific.

    The Atlantic Ocean is second in size to the Pacific. It occupies an area of about . The volume of the Atlantic, along with its adjacent seas (the seas next to it), is 354,700,000 cubic kilometres.

    The average depth of the Atlantic, along with its adjacent seas, is . The greatest depth is Milwaukee Deep near Puerto Rico, where the Ocean is  deep.

    Gulf Stream 
    The Atlantic Ocean has important ocean currents.  One of these, called the Gulf Stream, flows across the North Atlantic.  Water gets heated by the sun in the Caribbean Sea and then moves northwest toward the North Pole.  This makes France, the British Isles, Iceland, and Norway in Europe much warmer in winter than Newfoundland and Nova Scotia in Canada. Without the Gulf Stream, the climates of northeast Canada and northwest Europe might be the same, because these places are about the same distance from the North Pole.

    There are currents in the South Atlantic too, but the shape of this sea means that it has less effect on South Africa.

    Geology 
    The main feature of the Atlantic Ocean's seabed is a large underwater mountain chain called the Mid-Atlantic Ridge.  It runs from north to south under the Ocean. This is at the boundary of four tectonic plates: Eurasian, North American, South American and African. The ridge extends from Iceland in the north to about 58° south.

    The salinity of the surface waters of the open ocean ranges from 3337 parts per thousand and varies with latitude and season.

    References

    Other websites 
    LA Times special Altered Oceans 
    Oceanography Image of the Day, from the Woods Hole Oceanographic Institution
    National Oceanic and Atmospheric Administration 
    NOAA In-situ Ocean Data Viewer  Plot and download ocean observations

    www.cartage.org.lb 
    ... (省略 325 行)
    ```

成功了！我們用 kNN 對資料集做了 semantic search，並找到排名最前面的結果。

接下來可以用 Chat Completions API，把排名最高的搜尋結果當作額外 context，變點生成式 AI 的魔法。

## 用 Chat Completions API 做 retrieval augmented generation

現在可以把問題和文字送到 OpenAI 的 chat completion API。

把 LLM 模型和檢索模型一起用，就叫做 retrieval augmented generation（RAG）。我們讓 Elasticsearch 做它最擅長的事，也就是檢索相關文件。再讓 LLM 做它最擅長的事，也就是以檢索到的文件為 context 來產生摘要、回答問題這類任務。

模型會用排名最高的 kNN 結果當 context，針對問題產生回應。用 `messages` 清單來塑造你給模型的 prompt。這個例子用的是 `gpt-3.5-turbo` 模型。

```python
summary = openai.ChatCompletion.create(
  model="gpt-3.5-turbo",
  messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Answer the following question:" 
         + question 
         + "by using the following text:" 
         + top_hit_summary},
    ]
)

choices = summary.choices

for choice in choices:
    print("------------------------------------------------------------")
    print(choice.message.content)
    print("------------------------------------------------------------")
```

??? note "輸出"

    ```text
    ------------------------------------------------------------
    No, the Atlantic Ocean is not the biggest ocean in the world. It is the second largest ocean, covering about 20 percent of the Earth's surface. The Pacific Ocean is the largest ocean in the world.
    ------------------------------------------------------------
    ```



### 程式碼說明

這段程式碼做的事：

- 用 OpenAI 的模型產生回應
- 把包含一則 system 訊息和一則 user 訊息的對話送給模型
- system 訊息把 assistant 的角色設成「helpful assistant」
- user 訊息包含原本 kNN 查詢指定的問題，以及一些輸入文字
- 模型的回應存在 `summary.choices` 變數裡

## 後續步驟

這只是其中一個把 Elasticsearch 跟 OpenAI 模型結合、做 retrieval augmented generation 的例子。RAG 讓你不用走訓練或 fine-tuning 模型那種昂貴又複雜的過程，直接用現成的模型，再補上額外的 context。

把這個當作你自己實驗的藍圖。

要為不同的使用情境調整對話，可以自訂 system 訊息來定義 assistant 的行為或角色。調整 user 訊息來指定任務（例如摘要或問答）和想要的回應格式。

## 重點整理

- RAG 的分工：Elasticsearch 負責檢索相關文件，LLM 負責用這些文件當 context 來生成回答。
- kNN 搜尋時，查詢必須用跟索引時同一個 embedding 模型（這裡是 `text-embedding-3-small`）編碼，向量才有可比性。
- `dense_vector` 欄位型別讓 Elasticsearch 能存向量，之後 kNN 查詢要指定它。
- 資料量大時用 bulk API 分批寫入，比逐筆索引有效率。
- RAG 不需要訓練或 fine-tuning，改 system 和 user 訊息就能換任務和輸出格式。

## 練習

1. 把 kNN 查詢的 `k` 改大一點，觀察回傳的結果和排名有什麼變化。
2. 改 system 訊息，讓 assistant 用特定角色或語氣回答，看輸出怎麼改變。
3. 讓 kNN 查詢改搜 `title_vector` 欄位，並把前 3 筆結果的文字都組進 user 訊息當 context，再比較回答和只用第 1 筆時有什麼差別。
