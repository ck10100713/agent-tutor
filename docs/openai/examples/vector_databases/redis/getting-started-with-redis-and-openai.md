---
translated: true
source: examples/vector_databases/redis/getting-started-with-redis-and-openai.ipynb
---
# 用 Redis 當 OpenAI 的 vector database

> 原文：[examples/vector_databases/redis/getting-started-with-redis-and-openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/redis/getting-started-with-redis-and-openai.ipynb)



## 這篇在做什麼
示範怎麼把 Redis 當成 vector database，搭配 OpenAI embedding 使用。透過 RediSearch module 對 Redis 裡的向量建索引、做相似度搜尋，另外也會做混合查詢和 HNSW 索引。

## 學完你會
- 用 Docker 起一個 Redis Stack，並用 redis-py 連線。
- 在 Redis 建立向量索引（FLAT 和 HNSW），把已經算好 embedding 的文件載入索引。
- 用 OpenAI query embedding 做向量搜尋，以及結合全文檢索的 hybrid 查詢。

## 開跑前
- 需要 Docker 來跑 Redis Stack（本機 `localhost:6379`，RedisInsight 在 `localhost:8001`）。
- 需要環境變數 `OPENAI_API_KEY`，用來把 query 轉成 embedding。


本篇介紹怎麼把 Redis 當成 vector database，搭配 OpenAI embedding 使用。Redis 是可擴充的即時資料庫，搭配 [RediSearch Module](https://oss.redislabs.com/redisearch/) 就能當 vector database 用。RediSearch module 可以對 Redis 裡的向量建索引和搜尋。這裡會示範怎麼用它來索引和搜尋由 OpenAI API 產生、存在 Redis 裡的向量。

### 什麼是 Redis？

有 web 服務背景的開發者大多都熟悉 Redis。Redis 的核心是開源的 key-value store，可以當 cache、message broker 和資料庫。開發者選 Redis 是因為它快、client library 生態系大，而且已經被大型企業用了很多年。

除了傳統用途，Redis 還提供 [Redis Modules](https://redis.io/modules)，用來替 Redis 擴充新的資料型別和指令。例如 [RedisJSON](https://redis.io/docs/stack/json/)、[RedisTimeSeries](https://redis.io/docs/stack/timeseries/)、[RedisBloom](https://redis.io/docs/stack/bloom/) 和 [RediSearch](https://redis.io/docs/stack/search/)。

### 什麼是 RediSearch？

RediSearch 是一個 [Redis module](https://redis.io/modules)，替 Redis 提供查詢、secondary index、全文檢索和向量搜尋。使用時先對 Redis 資料宣告 index，再用 RediSearch client 查詢。RediSearch 的完整功能請看 [README](README.md) 或 [RediSearch 文件](https://redis.io/docs/stack/search/)。

### 部署方式

Redis 有很多部署方式。本機開發最快的是用 [Redis Stack docker container](https://hub.docker.com/r/redis/redis-stack)，這裡就用它。Redis Stack 包含多個 Redis module，可以組合成快速的多模型資料儲存和查詢引擎。

正式環境最簡單的起手方式是 [Redis Cloud](https://redislabs.com/redis-enterprise-cloud/overview/)，這是全託管的 Redis 服務。你也可以用 [Redis Enterprise](https://redislabs.com/redis-enterprise/overview/) 部署在自己的基礎設施上，它可以跑在 kubernetes、on-premises 或雲端。

另外，每個主要雲端廠商（[AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-e6y7ork67pjwg?sr=0-2&ref_=beagle&applicationId=AWSMPContessa)、[Google Marketplace](https://console.cloud.google.com/marketplace/details/redislabs-public/redis-enterprise?pli=1)、[Azure Marketplace](https://azuremarketplace.microsoft.com/en-us/marketplace/apps/garantiadata.redis_enterprise_1sp_public_preview?tab=Overview)）的 marketplace 都有 Redis Enterprise。



## 前置需求

開始之前，要先準備：

* 啟動一個有 RediSearch 的 Redis 資料庫（redis-stack）
* 安裝套件
    * [Redis-py](https://github.com/redis/redis-py)
* 取得你的 [OpenAI API key](https://beta.openai.com/account/api-keys)

===========================================================

### 啟動 Redis

為了讓範例簡單，我們用 Redis Stack docker container，啟動方式如下

```bash
$ docker-compose up -d
```

它也包含 [RedisInsight](https://redis.com/redis-enterprise/redis-insight/) 這個管理 Redis 的 GUI，docker container 啟動後可以在 [http://localhost:8001](http://localhost:8001) 看到。

這樣就設定好了。接下來匯入套件，建立 client 去連剛剛建好的 Redis 資料庫。

## 安裝套件

Redis-Py 是跟 Redis 溝通的 Python client，我們用它連到 Redis-stack 資料庫。

```python
! pip install redis wget pandas openai
```

===========================================================
## 準備 OpenAI API key

`OpenAI API key` 用來把 query 資料向量化。

如果還沒有 OpenAI API key，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，用下面的指令把它加到環境變數 `OPENAI_API_KEY`：

```python
! export OPENAI_API_KEY="your API key"
```

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os
import openai

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

if os.getenv("OPENAI_API_KEY") is not None:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    print ("OPENAI_API_KEY is ready")
else:
    print ("OPENAI_API_KEY environment variable not found")
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is ready
    ```

## 載入資料

這一段載入已經轉成向量的 embedding 資料，用它來在 Redis 建索引，再搜尋相似的向量。

```python
import sys
import numpy as np
import pandas as pd
from typing import List

# use helper function in nbutils.py to download and read the data
# this should take from 5-10 min to run
if os.getcwd() not in sys.path:
    sys.path.append(os.getcwd())
import nbutils

nbutils.download_wikipedia_data()
data = nbutils.read_wikipedia_data()

data.head()
```

??? note "輸出"

    ```text
    File Downloaded
    ```

    ```text
       id                                       url   title  \
    0   1   https://simple.wikipedia.org/wiki/April   April   
    1   2  https://simple.wikipedia.org/wiki/August  August   
    2   6     https://simple.wikipedia.org/wiki/Art     Art   
    3   8       https://simple.wikipedia.org/wiki/A       A   
    4   9     https://simple.wikipedia.org/wiki/Air     Air   

                                                    text  \
    0  April is the fourth month of the year in the J...   
    1  August (Aug.) is the eighth month of the year ...   
    2  Art is a creative activity that expresses imag...   
    3  A or a is the first letter of the English alph...   
    4  Air refers to the Earth's atmosphere. Air is a...   

                                            title_vector  \
    0  [0.001009464613161981, -0.020700545981526375, ...   
    1  [0.0009286514250561595, 0.000820168002974242, ...   
    2  [0.003393713850528002, 0.0061537534929811954, ...   
    3  [0.0153952119871974, -0.013759135268628597, 0....   
    4  [0.02224554680287838, -0.02044147066771984, -0...   

                                          content_vector vector_id  
    0  [-0.011253940872848034, -0.013491976074874401,...         0  
    1  [0.0003609954728744924, 0.007262262050062418, ...         1  
    2  [-0.004959689453244209, 0.015772193670272827, ...         2  
    3  [0.024894846603274345, -0.022186409682035446, ...         3  
    4  [0.021524671465158463, 0.018522677943110466, -...         4
    ```

## 連到 Redis

Redis 資料庫已經在跑了，可以用 Redis-py client 連線。這裡用預設的 host 和 port，也就是 `localhost:6379`。



```python
import redis
from redis.commands.search.indexDefinition import (
    IndexDefinition,
    IndexType
)
from redis.commands.search.query import Query
from redis.commands.search.field import (
    TextField,
    VectorField
)

REDIS_HOST =  "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = "" # default for passwordless Redis

# Connect to Redis
redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD
)
redis_client.ping()
```

??? note "輸出"

    ```text
    True
    ```

## 在 Redis 建立 Search Index

下面的 cell 示範怎麼指定並建立 Redis 的 search index。步驟是：

1. 設定一些定義索引的常數，例如距離度量和 index 名稱
2. 用 RediSearch 欄位定義 index schema
3. 建立 index

```python
# Constants
VECTOR_DIM = len(data['title_vector'][0]) # length of the vectors
VECTOR_NUMBER = len(data)                 # initial number of vectors
INDEX_NAME = "embeddings-index"           # name of the search index
PREFIX = "doc"                            # prefix for the document keys
DISTANCE_METRIC = "COSINE"                # distance metric for the vectors (ex. COSINE, IP, L2)
```

```python
# Define RediSearch fields for each of the columns in the dataset
title = TextField(name="title")
url = TextField(name="url")
text = TextField(name="text")
title_embedding = VectorField("title_vector",
    "FLAT", {
        "TYPE": "FLOAT32",
        "DIM": VECTOR_DIM,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": VECTOR_NUMBER,
    }
)
text_embedding = VectorField("content_vector",
    "FLAT", {
        "TYPE": "FLOAT32",
        "DIM": VECTOR_DIM,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": VECTOR_NUMBER,
    }
)
fields = [title, url, text, title_embedding, text_embedding]
```

```python
# Check if index exists
try:
    redis_client.ft(INDEX_NAME).info()
    print("Index already exists")
except:
    # Create RediSearch Index
    redis_client.ft(INDEX_NAME).create_index(
        fields = fields,
        definition = IndexDefinition(prefix=[PREFIX], index_type=IndexType.HASH)
)
```

## 把文件載入 Index

有了 search index 之後，就可以載入文件。這裡用和前面範例相同的文件。在 Redis 裡，文件可以存成 HASH，或是 JSON（需要在 RediSearch 之外再用 RedisJSON）。這裡用 HASH。下面的 cell 示範怎麼載入文件。

```python
def index_documents(client: redis.Redis, prefix: str, documents: pd.DataFrame):
    records = documents.to_dict("records")
    for doc in records:
        key = f"{prefix}:{str(doc['id'])}"

        # create byte vectors for title and content
        title_embedding = np.array(doc["title_vector"], dtype=np.float32).tobytes()
        content_embedding = np.array(doc["content_vector"], dtype=np.float32).tobytes()

        # replace list of floats with byte vectors
        doc["title_vector"] = title_embedding
        doc["content_vector"] = content_embedding

        client.hset(key, mapping = doc)
```

```python
index_documents(redis_client, PREFIX, data)
print(f"Loaded {redis_client.info()['db0']['keys']} documents in Redis search index with name: {INDEX_NAME}")
```

??? note "輸出"

    ```text
    Loaded 25000 documents in Redis search index with name: embeddings-index
    ```

## 用 OpenAI Query Embedding 做簡單的向量搜尋

有了 search index 和載入的文件，就可以執行搜尋 query。下面提供一個執行搜尋並回傳結果的函式，用它跑幾個 query，示範怎麼把 Redis 當 vector database 使用。

```python
def search_redis(
    redis_client: redis.Redis,
    user_query: str,
    index_name: str = "embeddings-index",
    vector_field: str = "title_vector",
    return_fields: list = ["title", "url", "text", "vector_score"],
    hybrid_fields = "*",
    k: int = 20,
    print_results: bool = True,
) -> List[dict]:

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(input=user_query,
                                            model="text-embedding-3-small",
                                            )["data"][0]['embedding']

    # Prepare the Query
    base_query = f'{hybrid_fields}=>[KNN {k} @{vector_field} $vector AS vector_score]'
    query = (
        Query(base_query)
         .return_fields(*return_fields)
         .sort_by("vector_score")
         .paging(0, k)
         .dialect(2)
    )
    params_dict = {"vector": np.array(embedded_query).astype(dtype=np.float32).tobytes()}

    # perform vector search
    results = redis_client.ft(index_name).search(query, params_dict)
    if print_results:
        for i, article in enumerate(results.docs):
            score = 1 - float(article.vector_score)
            print(f"{i}. {article.title} (Score: {round(score ,3) })")
    return results.docs
```

```python
# For using OpenAI to generate query embedding
results = search_redis(redis_client, 'modern art in Europe', k=10)
```

??? note "輸出"

    ```text
    0. Museum of Modern Art (Score: 0.875)
    1. Western Europe (Score: 0.868)
    2. Renaissance art (Score: 0.864)
    3. Pop art (Score: 0.86)
    4. Northern Europe (Score: 0.855)
    5. Hellenistic art (Score: 0.853)
    6. Modernist literature (Score: 0.847)
    7. Art film (Score: 0.843)
    8. Central Europe (Score: 0.843)
    9. European (Score: 0.841)
    ```

```python
results = search_redis(redis_client, 'Famous battles in Scottish history', vector_field='content_vector', k=10)
```

??? note "輸出"

    ```text
    0. Battle of Bannockburn (Score: 0.869)
    1. Wars of Scottish Independence (Score: 0.861)
    2. 1651 (Score: 0.853)
    3. First War of Scottish Independence (Score: 0.85)
    4. Robert I of Scotland (Score: 0.846)
    5. 841 (Score: 0.844)
    6. 1716 (Score: 0.844)
    7. 1314 (Score: 0.837)
    8. 1263 (Score: 0.836)
    9. William Wallace (Score: 0.835)
    ```

## Redis 的 Hybrid 查詢

前面的例子示範了怎麼用 RediSearch 做向量搜尋。這一段示範怎麼把向量搜尋和其他 RediSearch 欄位結合成 hybrid search。下面的例子把向量搜尋和全文檢索結合。

```python
def create_hybrid_field(field_name: str, value: str) -> str:
    return f'@{field_name}:"{value}"'

# search the content vector for articles about famous battles in Scottish history and only include results with Scottish in the title
results = search_redis(redis_client,
                       "Famous battles in Scottish history",
                       vector_field="title_vector",
                       k=5,
                       hybrid_fields=create_hybrid_field("title", "Scottish")
                       )
```

??? note "輸出"

    ```text
    0. First War of Scottish Independence (Score: 0.892)
    1. Wars of Scottish Independence (Score: 0.889)
    2. Second War of Scottish Independence (Score: 0.879)
    3. List of Scottish monarchs (Score: 0.873)
    4. Scottish Borders (Score: 0.863)
    ```

```python
# run a hybrid query for articles about Art in the title vector and only include results with the phrase "Leonardo da Vinci" in the text
results = search_redis(redis_client,
                       "Art",
                       vector_field="title_vector",
                       k=5,
                       hybrid_fields=create_hybrid_field("text", "Leonardo da Vinci")
                       )

# find specific mention of Leonardo da Vinci in the text that our full-text-search query returned
mention = [sentence for sentence in results[0].text.split("\n") if "Leonardo da Vinci" in sentence][0]
mention
```

??? note "輸出"

    ```text
    0. Art (Score: 1.0)
    1. Paint (Score: 0.896)
    2. Renaissance art (Score: 0.88)
    3. Painting (Score: 0.874)
    4. Renaissance (Score: 0.846)
    ```

    ```text
    'In Europe, after the Middle Ages, there was a "Renaissance" which means "rebirth". People rediscovered science and artists were allowed to paint subjects other than religious subjects. People like Michelangelo and Leonardo da Vinci still painted religious pictures, but they also now could paint mythological pictures too. These artists also invented perspective where things in the distance look smaller in the picture. This was new because in the Middle Ages people would paint all the figures close up and just overlapping each other. These artists used nudity regularly in their art.'
    ```

## HNSW Index

Up until now, we've been using the ``FLAT`` or "brute-force" index to run our queries. Redis also supports the ``HNSW`` index which is a fast, approximate index. The ``HNSW`` index is a graph-based index that uses a hierarchical navigable small world graph to store vectors. The ``HNSW`` index is a good choice for large datasets where you want to run approximate queries.

到目前為止我們都用 FLAT（也就是暴力搜尋）的 index 來查詢。Redis 也支援 HNSW index，這是一種快速的近似 index。HNSW 是以圖為基礎的 index，用 hierarchical navigable small world graph 來存向量，適合資料量大、可以接受近似查詢的情況。

``HNSW`` will take longer to build and consume more memory for most cases than ``FLAT`` but will be faster to run queries on, especially for large datasets.

多數情況下，HNSW 建索引比 FLAT 久、也吃更多記憶體，但查詢比較快，資料集越大越明顯。

下面的 cell 示範怎麼建 ``HNSW`` index，並用跟前面一樣的資料跑查詢。

```python
# re-define RediSearch vector fields to use HNSW index
title_embedding = VectorField("title_vector",
    "HNSW", {
        "TYPE": "FLOAT32",
        "DIM": VECTOR_DIM,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": VECTOR_NUMBER
    }
)
text_embedding = VectorField("content_vector",
    "HNSW", {
        "TYPE": "FLOAT32",
        "DIM": VECTOR_DIM,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": VECTOR_NUMBER
    }
)
fields = [title, url, text, title_embedding, text_embedding]
```

```python
import time
# Check if index exists
HNSW_INDEX_NAME = INDEX_NAME+ "_HNSW"

try:
    redis_client.ft(HNSW_INDEX_NAME).info()
    print("Index already exists")
except:
    # Create RediSearch Index
    redis_client.ft(HNSW_INDEX_NAME).create_index(
        fields = fields,
        definition = IndexDefinition(prefix=[PREFIX], index_type=IndexType.HASH)
    )

# since RediSearch creates the index in the background for existing documents, we will wait until
# indexing is complete before running our queries. Although this is not necessary for the first query,
# some queries may take longer to run if the index is not fully built. In general, Redis will perform
# best when adding new documents to existing indices rather than new indices on existing documents.
while redis_client.ft(HNSW_INDEX_NAME).info()["indexing"] == "1":
    time.sleep(5)
```

```python
results = search_redis(redis_client, 'modern art in Europe', index_name=HNSW_INDEX_NAME, k=10)
```

??? note "輸出"

    ```text
    0. Western Europe (Score: 0.868)
    1. Northern Europe (Score: 0.855)
    2. Central Europe (Score: 0.843)
    3. European (Score: 0.841)
    4. Eastern Europe (Score: 0.839)
    5. Europe (Score: 0.839)
    6. Western European Union (Score: 0.837)
    7. Southern Europe (Score: 0.831)
    8. Western civilization (Score: 0.83)
    9. Council of Europe (Score: 0.827)
    ```

```python
# compare the results of the HNSW index to the FLAT index and time both queries
def time_queries(iterations: int = 10):
    print(" ----- Flat Index ----- ")
    t0 = time.time()
    for i in range(iterations):
        results_flat = search_redis(redis_client, 'modern art in Europe', k=10, print_results=False)
    t0 = (time.time() - t0) / iterations
    results_flat = search_redis(redis_client, 'modern art in Europe', k=10, print_results=True)
    print(f"Flat index query time: {round(t0, 3)} seconds\n")
    time.sleep(1)
    print(" ----- HNSW Index ------ ")
    t1 = time.time()
    for i in range(iterations):
        results_hnsw = search_redis(redis_client, 'modern art in Europe', index_name=HNSW_INDEX_NAME, k=10, print_results=False)
    t1 = (time.time() - t1) / iterations
    results_hnsw = search_redis(redis_client, 'modern art in Europe', index_name=HNSW_INDEX_NAME, k=10, print_results=True)
    print(f"HNSW index query time: {round(t1, 3)} seconds")
    print(" ------------------------ ")
time_queries()
```

??? note "輸出"

    ```text
     ----- Flat Index ----- 
    0. Museum of Modern Art (Score: 0.875)
    1. Western Europe (Score: 0.867)
    2. Renaissance art (Score: 0.864)
    3. Pop art (Score: 0.861)
    4. Northern Europe (Score: 0.855)
    5. Hellenistic art (Score: 0.853)
    6. Modernist literature (Score: 0.847)
    7. Art film (Score: 0.843)
    8. Central Europe (Score: 0.843)
    9. Art (Score: 0.842)
    Flat index query time: 0.263 seconds

     ----- HNSW Index ------ 
    0. Western Europe (Score: 0.867)
    1. Northern Europe (Score: 0.855)
    2. Central Europe (Score: 0.843)
    3. European (Score: 0.841)
    4. Eastern Europe (Score: 0.839)
    5. Europe (Score: 0.839)
    6. Western European Union (Score: 0.837)
    7. Southern Europe (Score: 0.831)
    8. Western civilization (Score: 0.83)
    9. Council of Europe (Score: 0.827)
    HNSW index query time: 0.129 seconds
     ------------------------
    ```

## 重點整理
- Redis 搭配 RediSearch module 就能當 vector database，不用另外架一套向量資料庫。
- 使用流程是：定義 index schema、把文件（含 embedding）寫進 HASH、再用 query embedding 去搜尋。
- Hybrid 查詢可以把向量相似度和全文檢索等欄位條件組合起來。
- FLAT 是暴力搜尋、結果精確；HNSW 是近似搜尋，建索引較慢、吃記憶體，但大資料集查詢比較快。

## 練習
1. 換一個 query 文字去呼叫頁面上的搜尋函式，看回傳的結果是否合理。
2. 修改搜尋函式的回傳筆數（top K），比較結果變化。
3. 把距離度量常數換成別種（例如 `L2` 換成 `COSINE`），重建 index，比較兩次搜尋結果的分數與排序。
