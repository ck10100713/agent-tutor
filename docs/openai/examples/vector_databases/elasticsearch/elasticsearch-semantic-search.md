---
translated: true
source: examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb
---
# 用 Elasticsearch 和 OpenAI 做語意搜尋

> 原文：[examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb)

## 這篇在做什麼
把 OpenAI 的 Wikipedia 向量資料集索引進 Elasticsearch，用 OpenAI embeddings endpoint 把問題轉成向量，再對 index 做 kNN 語意搜尋。

## 學完你會
- 建立有 `dense_vector` 欄位 mapping 的 Elasticsearch index
- 用 bulk API 分批把 DataFrame 索引進去
- 把問題 embed 後，用 kNN query 做語意搜尋

## 開跑前
- Elasticsearch 的 Elastic Cloud deployment（可註冊免費試用），需要 Cloud ID 和密碼
- OpenAI API key

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/elasticsearch/elasticsearch-semantic-search.ipynb)


這個 notebook 示範怎麼：
- 把 OpenAI Wikipedia 向量資料集索引進 Elasticsearch
- 用 OpenAI [`embeddings`](https://platform.openai.com/docs/api-reference/embeddings) endpoint 把問題 embed
- 用編碼後的問題對 Elasticsearch index 做語意搜尋

## 安裝套件並 import 模組

```python
# install packages

! python3 -m pip install -qU openai pandas wget elasticsearch

# import modules

from getpass import getpass
from elasticsearch import Elasticsearch, helpers
import wget
import zipfile
import pandas as pd
import json
from openai import OpenAI
```

## 連線到 Elasticsearch

ℹ️ 這個 notebook 使用 Elastic Cloud 上的 Elasticsearch deployment。
如果你還沒有 Elastic deployment，可以註冊免費的 [Elastic Cloud trial](https://cloud.elastic.co/registration?utm_source=github&utm_content=openai-cookbook)。

要連到 Elasticsearch，需要用你 deployment 的 Cloud ID 和密碼建立 client instance。

到 https://cloud.elastic.co/deployments 選你的 deployment，就能找到它的 Cloud ID。

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

##  把 CSV 讀進 Pandas DataFrame

接著用 Pandas 把解壓縮後的 CSV 讀進 DataFrame。這樣之後比較容易批次索引進 Elasticsearch。

```python

wikipedia_dataframe = pd.read_csv("data/vector_database_wikipedia_articles_embedded.csv")
```

## 建立有 mapping 的 index

現在要建一個有必要 mapping 的 Elasticsearch index，這樣才能把資料索引進去。

`title_vector` 和 `content_vector` 欄位我們用 `dense_vector` 欄位型別。這是特殊的欄位型別，可以在 Elasticsearch 存 dense vector。

之後做 kNN 搜尋時，會以這些 `dense_vector` 欄位為目標。


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

??? note "輸出"

    ```text
    ObjectApiResponse({'acknowledged': True, 'shards_acknowledged': True, 'index': 'wikipedia_vector_index'})
    ```

## 把資料索引進 Elasticsearch

下面這個函式會產生需要的 bulk action，可以傳給 Elasticsearch 的 Bulk API，這樣能在單一請求裡有效率地索引多份文件。

DataFrame 的每一列，函式都會 yield 一個代表要索引的單一文件的 dictionary。

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

DataFrame 很大，所以我們分批索引，每批 `100` 筆。我們用 Python client 的 bulk API [helpers](https://www.elastic.co/guide/en/elasticsearch/client/python-api/current/client-helpers.html#bulk-helpers) 把資料索引進 Elasticsearch。

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

用簡單的 match query 測試一下 index。

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
    /var/folders/vz/v2f6_x6s0kg51j2vbm5rlhww0000gn/T/ipykernel_27262/2105931364.py:1: DeprecationWarning: The 'body' parameter is deprecated and will be removed in a future version. Instead use individual parameters.
      print(client.search(index="wikipedia_vector_index", body={
    ```

## 用 OpenAI embedding 模型編碼問題

要做語意搜尋，query 必須用和索引文件時相同的 embedding 模型來編碼。
這個範例要用 `text-embedding-3-small` 模型。

需要你的 OpenAI [API key](https://platform.openai.com/account/api-keys) 來產生 embedding。

```python
# Create OpenAI client
openai_client = OpenAI()

# Define question
question = 'Is the Atlantic the biggest ocean in the world?'

question_embedding = openai_client.embeddings.create(
    input=question,
    model="text-embedding-3-small"
)
```

## 執行語意搜尋 query

現在可以用編碼後的問題對 Elasticsearch index 下 query 了。我們會用 Elasticsearch 的 [kNN query](https://www.elastic.co/guide/en/elasticsearch/reference/current/knn-search.html) 選項做 k 最近鄰搜尋。

先定義一個小函式，把結果漂亮地印出來。

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

現在執行 `kNN` query。

```python
response = client.search(
  index = "wikipedia_vector_index",
  knn={
      "field": "content_vector",
      "query_vector":  question_embedding.data[0].embedding,
      "k": 10,
      "num_candidates": 100
    }
)
pretty_response(response)
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

## 下一步

成功了！現在你知道怎麼把 Elasticsearch 當向量資料庫存 embedding、呼叫 OpenAI `embeddings` endpoint 編碼 query，並執行語意搜尋。

可以多試不同的 query。如果想用自己的資料，也可以試試不同的 embedding 模型。

ℹ️ 也可以看另一個 notebook [用 Elasticsearch 和 OpenAI 做 retrieval augmented generation](elasticsearch-retrieval-augmented-generation.md)。它以這個範例為基礎，示範怎麼把 Elasticsearch 搭配 OpenAI [chat completions](https://platform.openai.com/docs/api-reference/chat) API 做 retrieval augmented generation (RAG)。

## 重點整理
- 向量要存在 `dense_vector` 欄位型別，之後 kNN 搜尋就以它為目標。
- 大量資料用 bulk API 分批索引，比逐筆送有效率。
- query 的 embedding 模型必須和索引文件時用的一致。
- kNN query 回傳的是向量空間裡最接近問題的文件，也就是語意搜尋。

## 練習
1. 換一個自己的問題做 kNN 搜尋，看回來的文章合不合理。
2. 改 kNN query 的 `k` 和 `num_candidates`，觀察結果變化。
3. 把搜尋目標從 `content_vector` 改成 `title_vector`，比較兩者結果。
