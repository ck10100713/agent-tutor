---
translated: true
source: examples/vector_databases/redis/Using_Redis_for_embeddings_search.ipynb
---
# 用 Redis 做 embedding 搜尋

> 原文：[examples/vector_databases/redis/Using_Redis_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/redis/Using_Redis_for_embeddings_search.ipynb)



## 這篇在做什麼

用 Docker 跑一個 Redis Stack，把已經做過 embedding 的資料建成索引，再用 vector 搜尋和「vector 加全文搜尋」的 hybrid 搜尋來查資料。用的是 redis-py client 和 RediSearch module。

## 學完你會

- 用 Docker 啟動帶 RediSearch 的 Redis Stack，並用 redis-py 連線
- 定義索引 schema（含 vector 欄位和距離指標），把文件以 HASH 存進 Redis
- 寫出只回傳指定欄位的 vector 查詢，以及結合全文搜尋的 hybrid 查詢

## 開跑前

- 需要 Docker 來跑 Redis Stack
- 需要 `OPENAI_API_KEY` 環境變數


這份 notebook 帶你走一個簡單流程：下載一些資料、做 embedding，然後用幾種 vector database 建索引並搜尋。很多客戶都有這種需求：想在安全的環境裡，用自己的資料儲存跟搜尋我們的 embedding，來支援 chatbot、主題建模等正式環境的應用。

### Vector Database 是什麼

Vector database 是專門用來儲存、管理和搜尋 embedding vector 的資料庫。近年用 embedding 把非結構化資料（文字、音訊、影片等）編碼成 vector，再交給機器學習模型使用的做法爆炸性成長，因為 AI 在自然語言、影像辨識等非結構化資料的應用上越來越有效。Vector database 成為企業交付並擴充這些應用的有效方案。

### 為什麼要用 Vector Database

Vector database 讓企業可以把我們在這個 repo 分享的許多 embedding 應用（例如問答、chatbot 和推薦服務），放到安全、可擴充的環境裡使用。很多客戶在小規模時用 embedding 解決了問題，但效能和安全性擋住了他們上線，我們認為 vector database 是解決這件事的關鍵元件。這份指南會走過基本流程：對文字資料做 embedding、存進 vector database，再拿來做語意搜尋。


### Demo 流程
流程是：
- **Setup**：匯入套件並設定需要的變數
- **載入資料**：載入資料集，並用 OpenAI embedding 做向量化
- **Redis**
    - *Setup*：設定 Redis-Py client。更多細節看[這裡](https://github.com/redis/redis-py)
    - *建立索引*：對所有可用欄位建立 vector 搜尋和 hybrid 搜尋（vector 加全文搜尋）用的搜尋索引。
    - *搜尋資料*：針對不同目標跑幾個範例查詢。

跑完這份 notebook 之後，你應該對 vector database 的設定跟使用有基本概念，可以繼續做更複雜、用到我們 embedding 的應用。

## Setup

匯入需要的函式庫，並設定我們要用的 embedding 模型。

```python
# We'll need to install the Redis client
!pip install redis

#Install wget to pull zip file
!pip install wget
```

```python
import openai

from typing import List, Iterator
import pandas as pd
import numpy as np
import os
import wget
from ast import literal_eval

# Redis client library for Python
import redis

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## 載入資料

這一節載入我們在這次之前就準備好的 embedding 資料。

```python
embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

```python
import zipfile
with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip","r") as zip_ref:
    zip_ref.extractall("../data")
```

```python
article_df = pd.read_csv('../data/vector_database_wikipedia_articles_embedded.csv')
```

```python
article_df.head()
```

??? note "輸出"

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

                                          content_vector  vector_id  
    0  [-0.011253940872848034, -0.013491976074874401,...          0  
    1  [0.0003609954728744924, 0.007262262050062418, ...          1  
    2  [-0.004959689453244209, 0.015772193670272827, ...          2  
    3  [0.024894846603274345, -0.022186409682035446, ...          3  
    4  [0.021524671465158463, 0.018522677943110466, -...          4
    ```

```python
# Read vectors from strings back into a list
article_df['title_vector'] = article_df.title_vector.apply(literal_eval)
article_df['content_vector'] = article_df.content_vector.apply(literal_eval)

# Set vector_id to be a string
article_df['vector_id'] = article_df['vector_id'].apply(str)
```

```python
article_df.info(show_counts=True)
```

??? note "輸出"

    ```text
    <class 'pandas.core.frame.DataFrame'>
    RangeIndex: 25000 entries, 0 to 24999
    Data columns (total 7 columns):
     #   Column          Non-Null Count  Dtype 
    ---  ------          --------------  ----- 
     0   id              25000 non-null  int64 
     1   url             25000 non-null  object
     2   title           25000 non-null  object
     3   text            25000 non-null  object
     4   title_vector    25000 non-null  object
     5   content_vector  25000 non-null  object
     6   vector_id       25000 non-null  object
    dtypes: int64(1), object(6)
    memory usage: 1.3+ MB
    ```

# Redis

這份教學接下來介紹的 vector database 是 **[Redis](https://redis.io)**。你很可能已經認識 Redis，但你可能不知道它有 [RediSearch module](https://github.com/RediSearch/RediSearch)。企業使用 Redis 搭配 RediSearch module 已經很多年了，涵蓋所有主要雲端供應商、Redis Cloud 以及地端環境。最近 Redis 團隊在這個 module 裡，除了 RediSearch 原有的功能，還加上了 vector 儲存和搜尋能力。

因為 Redis 周邊生態很大，你需要的語言多半都有 client library。你可以用任何標準 Redis client library 執行 RediSearch 指令，但用包好 RediSearch API 的函式庫最方便。下面列幾個例子，更多 client library 可以看[這裡](https://redis.io/resources/clients/)。

| Project | Language | License | Author | Stars |
|----------|---------|--------|---------|-------|
| [jedis][jedis-url] | Java | MIT | [Redis][redis-url] | ![Stars][jedis-stars] |
| [redis-py][redis-py-url] | Python | MIT | [Redis][redis-url] | ![Stars][redis-py-stars] |
| [node-redis][node-redis-url] | Node.js | MIT | [Redis][redis-url] | ![Stars][node-redis-stars] |
| [nredisstack][nredisstack-url] | .NET | MIT | [Redis][redis-url] | ![Stars][nredisstack-stars] |
| [redisearch-go][redisearch-go-url] | Go | BSD | [Redis][redisearch-go-author] | [![redisearch-go-stars]][redisearch-go-url] |
| [redisearch-api-rs][redisearch-api-rs-url] | Rust | BSD | [Redis][redisearch-api-rs-author] | [![redisearch-api-rs-stars]][redisearch-api-rs-url] |

[redis-url]: https://redis.com

[redis-py-url]: https://github.com/redis/redis-py
[redis-py-stars]: https://img.shields.io/github/stars/redis/redis-py.svg?style=social&amp;label=Star&amp;maxAge=2592000
[redis-py-package]: https://pypi.python.org/pypi/redis

[jedis-url]: https://github.com/redis/jedis
[jedis-stars]: https://img.shields.io/github/stars/redis/jedis.svg?style=social&amp;label=Star&amp;maxAge=2592000
[Jedis-package]: https://search.maven.org/artifact/redis.clients/jedis

[nredisstack-url]: https://github.com/redis/nredisstack
[nredisstack-stars]: https://img.shields.io/github/stars/redis/nredisstack.svg?style=social&amp;label=Star&amp;maxAge=2592000
[nredisstack-package]: https://www.nuget.org/packages/nredisstack/

[node-redis-url]: https://github.com/redis/node-redis
[node-redis-stars]: https://img.shields.io/github/stars/redis/node-redis.svg?style=social&amp;label=Star&amp;maxAge=2592000
[node-redis-package]: https://www.npmjs.com/package/redis

[redis-om-python-url]: https://github.com/redis/redis-om-python
[redis-om-python-author]: https://redis.com
[redis-om-python-stars]: https://img.shields.io/github/stars/redis/redis-om-python.svg?style=social&amp;label=Star&amp;maxAge=2592000

[redisearch-go-url]: https://github.com/RediSearch/redisearch-go
[redisearch-go-author]: https://redis.com
[redisearch-go-stars]: https://img.shields.io/github/stars/RediSearch/redisearch-go.svg?style=social&amp;label=Star&amp;maxAge=2592000

[redisearch-api-rs-url]: https://github.com/RediSearch/redisearch-api-rs
[redisearch-api-rs-author]: https://redis.com
[redisearch-api-rs-stars]: https://img.shields.io/github/stars/RediSearch/redisearch-api-rs.svg?style=social&amp;label=Star&amp;maxAge=2592000


接下來的 cell 會帶你把 Redis 當 vector database 來用。你們很多人應該已經習慣 Redis API，所以大部分內容看起來會很熟悉。

## Setup

部署帶 RediSearch 的 Redis 有很多種方式。最簡單的起步方式是用 Docker，不過還有許多可行的部署選項。其他部署方式請看這個 repo 裡的 [Redis 目錄](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/redis)。

這份教學會在 Docker 上用 Redis Stack。

執行下面的 docker 指令，啟動帶 RediSearch 的 Redis 版本（Redis Stack）

```bash
$ cd redis
$ docker compose up -d
```
這也包含管理 Redis 資料庫用的 [RedisInsight](https://redis.com/redis-enterprise/redis-insight/) GUI，docker container 啟動後可以在 [http://localhost:8001](http://localhost:8001) 看到。

設定完成，準備好了！接下來匯入並建立 client，用來跟剛建好的 Redis 資料庫溝通。

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

## 建立搜尋索引

下面的 cell 會示範怎麼在 Redis 指定並建立搜尋索引。我們會：

1. 設定一些定義索引用的常數，例如距離指標和索引名稱
2. 用 RediSearch 欄位定義索引 schema
3. 建立索引


```python
# Constants
VECTOR_DIM = len(article_df['title_vector'][0]) # length of the vectors
VECTOR_NUMBER = len(article_df)                 # initial number of vectors
INDEX_NAME = "embeddings-index"                 # name of the search index
PREFIX = "doc"                                  # prefix for the document keys
DISTANCE_METRIC = "COSINE"                      # distance metric for the vectors (ex. COSINE, IP, L2)
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

## 把文件載入索引

有了搜尋索引，就可以把文件載入。我們會用前面範例用過的同一批文件。在 Redis 裡，文件可以用 Hash 或 JSON（如果除了 RediSearch 還有用 RedisJSON）資料型別儲存。這個範例用 HASH 型別。下面的 cell 會示範怎麼把文件載入索引。

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
index_documents(redis_client, PREFIX, article_df)
print(f"Loaded {redis_client.info()['db0']['keys']} documents in Redis search index with name: {INDEX_NAME}")
```

??? note "輸出"

    ```text
    Loaded 25000 documents in Redis search index with name: embeddings-index
    ```

## 執行搜尋查詢

現在有了搜尋索引，也載入了文件，就可以執行搜尋查詢了。下面會提供一個函式，負責執行搜尋查詢並回傳結果。我們用這個函式跑幾個查詢，示範怎麼把 Redis 當 vector database 用。每個範例會展示用 Redis 開發搜尋應用時要留意的特定功能。

1. **Return Fields**：你可以指定搜尋結果要回傳哪些欄位。如果你只想回傳文件的一部分欄位，這很有用，而且不用另外呼叫去取文件。下面的範例只會在搜尋結果回傳 `title` 欄位。
2. **Hybrid Search**：你可以把 vector 搜尋跟其他 RediSearch 欄位（例如全文搜尋、tag、geo 和 numeric）結合，做 hybrid 搜尋。下面的範例會把 vector 搜尋跟全文搜尋結合。


```python
def search_redis(
    redis_client: redis.Redis,
    user_query: str,
    index_name: str = "embeddings-index",
    vector_field: str = "title_vector",
    return_fields: list = ["title", "url", "text", "vector_score"],
    hybrid_fields = "*",
    k: int = 20,
) -> List[dict]:

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(input=user_query,
                                            model=EMBEDDING_MODEL,
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
    for i, article in enumerate(results.docs):
        score = 1 - float(article.vector_score)
        print(f"{i}. {article.title} (Score: {round(score ,3) })")
    return results.docs
```

```python
# For using OpenAI to generate query embedding
openai.api_key = os.getenv("OPENAI_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
results = search_redis(redis_client, 'modern art in Europe', k=10)
```

??? note "輸出"

    ```text
    0. Museum of Modern Art (Score: 0.875)
    1. Western Europe (Score: 0.867)
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

## 用 Redis 做 Hybrid 查詢

前面的範例示範了怎麼用 RediSearch 跑 vector 搜尋查詢。這一節會示範怎麼把 vector 搜尋跟其他 RediSearch 欄位結合，做 hybrid 搜尋。下面的範例會把 vector 搜尋跟全文搜尋結合。

```python
def create_hybrid_field(field_name: str, value: str) -> str:
    return f'@{field_name}:"{value}"'
```

```python
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

想看更多把 Redis 當 vector database 的範例，請看這個 repo 裡 ``vector_databases/redis`` 目錄下的 README 和範例

## 重點整理

- Vector database 讓 embedding 應用能放到安全、可擴充的環境，是從原型走向正式上線的關鍵元件。
- Redis 靠 RediSearch module 同時支援 vector 搜尋和原有的全文、tag、geo、numeric 搜尋。
- 流程是先定義索引 schema（欄位、vector 維度、距離指標），再把文件載入，最後才查詢。
- 查詢時可以指定回傳欄位，省掉再取文件的一次呼叫。
- Hybrid 搜尋把 vector 相似度和欄位條件結合，適合需要同時考慮語意和精確條件的場景。

## 練習

1. 把查詢函式的回傳欄位多加一個（例如 `text`），看輸出有什麼變化。
2. 換一個搜尋 query，調整回傳筆數，觀察排名結果合不合理。
3. 修改 hybrid 查詢裡的全文搜尋條件，比較只用 vector 搜尋和加了全文條件之後的結果差異。
