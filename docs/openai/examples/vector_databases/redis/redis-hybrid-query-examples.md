---
translated: true
source: examples/vector_databases/redis/redis-hybrid-query-examples.ipynb
---

# 用 Redis 和 OpenAI 執行 hybrid VSS 查詢

> 原文：[examples/vector_databases/redis/redis-hybrid-query-examples.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/redis/redis-hybrid-query-examples.ipynb)



## 這篇在做什麼
把 Redis 當向量資料庫，存 OpenAI embedding，並跑 hybrid 查詢：同時結合向量相似度搜尋（VSS）和 Redis 的全文（lexical）搜尋。資料是一份電商商品資料集。

## 學完你會
- 用 docker 啟動 Redis Stack，並用 redis-py 連線
- 定義 RediSearch index schema，把 OpenAI embedding 寫進 HASH 文件
- 對同一個 index 執行純向量查詢，以及向量加全文過濾的 hybrid 查詢

## 開跑前
- Docker（用來跑 redis-stack）
- OpenAI API key，設成環境變數 `OPENAI_API_KEY`


這份 notebook 介紹怎麼把 Redis 當作向量資料庫來搭配 OpenAI embedding，並用 Redis Query and Search 的能力執行結合 VSS 和 lexical 搜尋的 hybrid 查詢。Redis 是可擴充的即時資料庫，搭配 [RediSearch Module](https://oss.redislabs.com/redisearch/) 就能當向量資料庫。Redis Query and Search 讓你可以在 Redis 裡對向量建索引和搜尋。這份 notebook 會示範怎麼用它，對用 OpenAI API 建立並存在 Redis 的向量做索引和搜尋。

Hybrid 查詢把向量相似度和傳統 Redis Query and Search 對 GEO、NUMERIC、TAG 或 TEXT 資料的過濾能力結合起來，讓應用程式碼更簡單。電商情境常見的 hybrid 查詢例子，是找出跟某張查詢圖片外觀相似的商品，並限制在某個 GEO 位置有貨、價格也在某個範圍內。

## 前置需求

開始這個專案之前，需要先準備：

* 啟動有 RediSearch 的 Redis 資料庫（redis-stack）
* 安裝函式庫
    * [Redis-py](https://github.com/redis/redis-py)
* 取得你的 [OpenAI API key](https://beta.openai.com/account/api-keys)

===========================================================

### 啟動 Redis

為了讓範例簡單，我們用 Redis Stack 的 docker container，啟動方式如下

```bash
$ docker-compose up -d
```

它也包含用來管理 Redis 資料庫的 [RedisInsight](https://redis.com/redis-enterprise/redis-insight/) GUI，docker container 啟動後可以在 [http://localhost:8001](http://localhost:8001) 看到。

設定完成，可以開始了！接下來我們匯入套件，並建立 client 來跟剛建好的 Redis 資料庫溝通。

## 安裝需要的套件

Redis-Py 是跟 Redis 溝通的 Python client，我們用它來跟 Redis-stack 資料庫溝通。 

```python
! pip install redis pandas openai
```

??? note "輸出"

    ```text
    Defaulting to user installation because normal site-packages is not writeable
    Requirement already satisfied: redis in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (4.5.4)
    Requirement already satisfied: pandas in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (2.0.1)
    Requirement already satisfied: openai in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (0.27.6)
    Requirement already satisfied: async-timeout>=4.0.2 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from redis) (4.0.2)
    Requirement already satisfied: python-dateutil>=2.8.2 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from pandas) (2.8.2)
    Requirement already satisfied: pytz>=2020.1 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from pandas) (2023.3)
    Requirement already satisfied: tzdata>=2022.1 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from pandas) (2023.3)
    Requirement already satisfied: numpy>=1.20.3 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from pandas) (1.23.4)
    Requirement already satisfied: requests>=2.20 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from openai) (2.28.1)
    Requirement already satisfied: tqdm in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from openai) (4.64.1)
    Requirement already satisfied: aiohttp in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from openai) (3.8.4)
    Requirement already satisfied: six>=1.5 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from python-dateutil>=2.8.2->pandas) (1.16.0)
    Requirement already satisfied: charset-normalizer<3,>=2 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from requests>=2.20->openai) (2.1.1)
    Requirement already satisfied: idna<4,>=2.5 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from requests>=2.20->openai) (3.4)
    Requirement already satisfied: urllib3<1.27,>=1.21.1 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from requests>=2.20->openai) (1.26.12)
    Requirement already satisfied: certifi>=2017.4.17 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from requests>=2.20->openai) (2022.9.24)
    Requirement already satisfied: attrs>=17.3.0 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from aiohttp->openai) (23.1.0)
    Requirement already satisfied: multidict<7.0,>=4.5 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from aiohttp->openai) (6.0.4)
    Requirement already satisfied: yarl<2.0,>=1.0 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from aiohttp->openai) (1.9.2)
    Requirement already satisfied: frozenlist>=1.1.1 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from aiohttp->openai) (1.3.3)
    Requirement already satisfied: aiosignal>=1.1.2 in /Users/michael.yuan/Library/Python/3.9/lib/python/site-packages (from aiohttp->openai) (1.3.1)
    ```

===========================================================
## 準備你的 OpenAI API key

`OpenAI API key` 用來把查詢資料向量化。

如果還沒有 OpenAI API key，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，用下面的指令把它加到環境變數 `OPENAI_API_KEY`：

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os
import openai

os.environ["OPENAI_API_KEY"] = '<YOUR_OPENAI_API_KEY>'

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

這一節載入並清理一份電商資料集。我們會用 OpenAI 產生 embedding，用這些資料在 Redis 建立 index，再搜尋相似的向量。

```python
import pandas as pd
import numpy as np
from typing import List

from utils.embeddings_utils import (
    get_embeddings,
    distances_from_embeddings,
    tsne_components_from_embeddings,
    chart_from_components,
    indices_of_nearest_neighbors_from_distances,
)

EMBEDDING_MODEL = "text-embedding-3-small"

# load in data and clean data types and drop null rows
df = pd.read_csv("../../data/styles_2k.csv", on_bad_lines='skip')
df.dropna(inplace=True)
df["year"] = df["year"].astype(int)
df.info()

# print dataframe
n_examples = 5
df.head(n_examples)
```

??? note "輸出"

    ```text
    <class 'pandas.core.frame.DataFrame'>
    Index: 1978 entries, 0 to 1998
    Data columns (total 10 columns):
     #   Column              Non-Null Count  Dtype 
    ---  ------              --------------  ----- 
     0   id                  1978 non-null   int64 
     1   gender              1978 non-null   object
     2   masterCategory      1978 non-null   object
     3   subCategory         1978 non-null   object
     4   articleType         1978 non-null   object
     5   baseColour          1978 non-null   object
     6   season              1978 non-null   object
     7   year                1978 non-null   int64 
     8   usage               1978 non-null   object
     9   productDisplayName  1978 non-null   object
    dtypes: int64(2), object(8)
    memory usage: 170.0+ KB
    ```

    ```text
          id gender masterCategory subCategory  articleType baseColour  season   
    0  15970    Men        Apparel     Topwear       Shirts  Navy Blue    Fall  \
    1  39386    Men        Apparel  Bottomwear        Jeans       Blue  Summer   
    2  59263  Women    Accessories     Watches      Watches     Silver  Winter   
    3  21379    Men        Apparel  Bottomwear  Track Pants      Black    Fall   
    4  53759    Men        Apparel     Topwear      Tshirts       Grey  Summer   

       year   usage                             productDisplayName  
    0  2011  Casual               Turtle Check Men Navy Blue Shirt  
    1  2012  Casual             Peter England Men Party Blue Jeans  
    2  2016  Casual                       Titan Women Silver Watch  
    3  2011  Casual  Manchester United Men Solid Black Track Pants  
    4  2012  Casual                          Puma Men Grey T-shirt
    ```

```python
df["product_text"] = df.apply(lambda row: f"name {row['productDisplayName']} category {row['masterCategory']} subcategory {row['subCategory']} color {row['baseColour']} gender {row['gender']}".lower(), axis=1)
df.rename({"id":"product_id"}, inplace=True, axis=1)

df.info()
```

??? note "輸出"

    ```text
    <class 'pandas.core.frame.DataFrame'>
    Index: 1978 entries, 0 to 1998
    Data columns (total 11 columns):
     #   Column              Non-Null Count  Dtype 
    ---  ------              --------------  ----- 
     0   product_id          1978 non-null   int64 
     1   gender              1978 non-null   object
     2   masterCategory      1978 non-null   object
     3   subCategory         1978 non-null   object
     4   articleType         1978 non-null   object
     5   baseColour          1978 non-null   object
     6   season              1978 non-null   object
     7   year                1978 non-null   int64 
     8   usage               1978 non-null   object
     9   productDisplayName  1978 non-null   object
     10  product_text        1978 non-null   object
    dtypes: int64(2), object(9)
    memory usage: 185.4+ KB
    ```

```python
# check out one of the texts we will use to create semantic embeddings
df["product_text"][0]
```

??? note "輸出"

    ```text
    'name turtle check men navy blue shirt category apparel subcategory topwear color navy blue gender men'
    ```

## 連線到 Redis

Redis 資料庫已經在跑了，現在可以用 Redis-py client 連線。我們使用 Redis 資料庫預設的 host 和 port，也就是 `localhost:6379`。



```python
import redis
from redis.commands.search.indexDefinition import (
    IndexDefinition,
    IndexType
)
from redis.commands.search.query import Query
from redis.commands.search.field import (
    TagField,
    NumericField,
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

## 在 Redis 建立搜尋 Index

下面的 cell 示範怎麼指定並建立 Redis 的搜尋 index。步驟如下：

1. 設定定義 index 用的一些常數，例如距離度量和 index 名稱
2. 用 RediSearch 欄位定義 index schema
3. 建立 index

```python
# Constants
INDEX_NAME = "product_embeddings"           # name of the search index
PREFIX = "doc"                            # prefix for the document keys
DISTANCE_METRIC = "L2"                # distance metric for the vectors (ex. COSINE, IP, L2)
NUMBER_OF_VECTORS = len(df)
```

```python
# Define RediSearch fields for each of the columns in the dataset
name = TextField(name="productDisplayName")
category = TagField(name="masterCategory")
articleType = TagField(name="articleType")
gender = TagField(name="gender")
season = TagField(name="season")
year = NumericField(name="year")
text_embedding = VectorField("product_vector",
    "FLAT", {
        "TYPE": "FLOAT32",
        "DIM": 1536,
        "DISTANCE_METRIC": DISTANCE_METRIC,
        "INITIAL_CAP": NUMBER_OF_VECTORS,
    }
)
fields = [name, category, articleType, gender, season, year, text_embedding]
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

## 產生 OpenAI Embedding 並把文件載入 Index

有了搜尋 index，就能把文件載入。我們用前面載入的 styles 資料集 dataframe。在 Redis 裡可以用 HASH 或 JSON（如果除了 RediSearch 還用了 RedisJSON）資料型態儲存文件，這個範例用 HASH。下面的 cell 示範怎麼取得各商品的 OpenAI embedding，並把文件載入 index。

```python
# Use OpenAI get_embeddings batch requests to speed up embedding creation
def embeddings_batch_request(documents: pd.DataFrame):
    records = documents.to_dict("records")
    print("Records to process: ", len(records))
    product_vectors = []
    docs = []
    batchsize = 1000

    for idx,doc in enumerate(records,start=1):
        # create byte vectors
        docs.append(doc["product_text"])
        if idx % batchsize == 0:
            product_vectors += get_embeddings(docs, EMBEDDING_MODEL)
            docs.clear()
            print("Vectors processed ", len(product_vectors), end='\r')
    product_vectors += get_embeddings(docs, EMBEDDING_MODEL)
    print("Vectors processed ", len(product_vectors), end='\r')
    return product_vectors
```

```python
def index_documents(client: redis.Redis, prefix: str, documents: pd.DataFrame):
    product_vectors = embeddings_batch_request(documents)
    records = documents.to_dict("records")
    batchsize = 500

    # Use Redis pipelines to batch calls and save on round trip network communication
    pipe = client.pipeline()
    for idx,doc in enumerate(records,start=1):
        key = f"{prefix}:{str(doc['product_id'])}"

        # create byte vectors
        text_embedding = np.array((product_vectors[idx-1]), dtype=np.float32).tobytes()

        # replace list of floats with byte vectors
        doc["product_vector"] = text_embedding

        pipe.hset(key, mapping = doc)
        if idx % batchsize == 0:
            pipe.execute()
    pipe.execute()
```

```python
%%time
index_documents(redis_client, PREFIX, df)
print(f"Loaded {redis_client.info()['db0']['keys']} documents in Redis search index with name: {INDEX_NAME}")
```

??? note "輸出"

    ```text
    Records to process:  1978
    Loaded 1978 documents in Redis search index with name: product_embeddings
    CPU times: user 619 ms, sys: 78.9 ms, total: 698 ms
    Wall time: 3.34 s
    ```

## 用 OpenAI 查詢 Embedding 做簡單向量搜尋

現在有搜尋 index，文件也載入了，就能執行搜尋查詢。下面提供一個函式，用來執行搜尋查詢並回傳結果。用這個函式跑幾個查詢，示範怎麼把 Redis 當向量資料庫使用。

```python
def search_redis(
    redis_client: redis.Redis,
    user_query: str,
    index_name: str = "product_embeddings",
    vector_field: str = "product_vector",
    return_fields: list = ["productDisplayName", "masterCategory", "gender", "season", "year", "vector_score"],
    hybrid_fields = "*",
    k: int = 20,
    print_results: bool = True,
) -> List[dict]:

    # Use OpenAI to create embedding vector from user query
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
        for i, product in enumerate(results.docs):
            score = 1 - float(product.vector_score)
            print(f"{i}. {product.productDisplayName} (Score: {round(score ,3) })")
    return results.docs
```

```python
# Execute a simple vector search in Redis
results = search_redis(redis_client, 'man blue jeans', k=10)
```

??? note "輸出"

    ```text
    0. John Players Men Blue Jeans (Score: 0.791)
    1. Lee Men Tino Blue Jeans (Score: 0.775)
    2. Peter England Men Party Blue Jeans (Score: 0.763)
    3. Lee Men Blue Chicago Fit Jeans (Score: 0.761)
    4. Lee Men Blue Chicago Fit Jeans (Score: 0.761)
    5. French Connection Men Blue Jeans (Score: 0.74)
    6. Locomotive Men Washed Blue Jeans (Score: 0.739)
    7. Locomotive Men Washed Blue Jeans (Score: 0.739)
    8. Do U Speak Green Men Blue Shorts (Score: 0.736)
    9. Palm Tree Kids Boy Washed Blue Jeans (Score: 0.732)
    ```

## 用 Redis 做 Hybrid 查詢

前面的範例示範了怎麼用 RediSearch 執行向量搜尋。這一節會示範怎麼把向量搜尋和其他 RediSearch 欄位結合成 hybrid 搜尋。下面的範例把向量搜尋和全文搜尋結合。

```python
# improve search quality by adding hybrid query for "man blue jeans" in the product vector combined with a phrase search for "blue jeans"
results = search_redis(redis_client,
                       "man blue jeans",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@productDisplayName:"blue jeans"'
                       )
```

??? note "輸出"

    ```text
    0. John Players Men Blue Jeans (Score: 0.791)
    1. Lee Men Tino Blue Jeans (Score: 0.775)
    2. Peter England Men Party Blue Jeans (Score: 0.763)
    3. French Connection Men Blue Jeans (Score: 0.74)
    4. Locomotive Men Washed Blue Jeans (Score: 0.739)
    5. Locomotive Men Washed Blue Jeans (Score: 0.739)
    6. Palm Tree Kids Boy Washed Blue Jeans (Score: 0.732)
    7. Denizen Women Blue Jeans (Score: 0.725)
    8. Jealous 21 Women Washed Blue Jeans (Score: 0.713)
    9. Jealous 21 Women Washed Blue Jeans (Score: 0.713)
    ```

```python
# hybrid query for shirt in the product vector and only include results with the phrase "slim fit" in the title
results = search_redis(redis_client,
                       "shirt",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@productDisplayName:"slim fit"'
                       )
```

??? note "輸出"

    ```text
    0. Basics Men White Slim Fit Striped Shirt (Score: 0.633)
    1. ADIDAS Men's Slim Fit White T-shirt (Score: 0.628)
    2. Basics Men Blue Slim Fit Checked Shirt (Score: 0.627)
    3. Basics Men Blue Slim Fit Checked Shirt (Score: 0.627)
    4. Basics Men Red Slim Fit Checked Shirt (Score: 0.623)
    5. Basics Men Navy Slim Fit Checked Shirt (Score: 0.613)
    6. Lee Rinse Navy Blue Slim Fit Jeans (Score: 0.558)
    7. Tokyo Talkies Women Navy Slim Fit Jeans (Score: 0.552)
    ```

```python
# hybrid query for watch in the product vector and only include results with the tag "Accessories" in the masterCategory field
results = search_redis(redis_client,
                       "watch",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@masterCategory:{Accessories}'
                       )
```

??? note "輸出"

    ```text
    0. Titan Women Gold Watch (Score: 0.544)
    1. Being Human Men Grey Dial Blue Strap Watch (Score: 0.544)
    2. Police Men Black Dial Watch PL12170JSB (Score: 0.544)
    3. Titan Men Black Watch (Score: 0.543)
    4. Police Men Black Dial Chronograph Watch PL12777JS-02M (Score: 0.542)
    5. CASIO Youth Series Digital Men Black Small Dial Digital Watch W-210-1CVDF I065 (Score: 0.542)
    6. Titan Women Silver Watch (Score: 0.542)
    7. Police Men Black Dial Watch PL12778MSU-61 (Score: 0.541)
    8. Titan Raga Women Gold Watch (Score: 0.539)
    9. ADIDAS Original Men Black Dial Chronograph Watch ADH2641 (Score: 0.539)
    ```

```python
# hybrid query for sandals in the product vector and only include results within the 2011-2012 year range
results = search_redis(redis_client,
                       "sandals",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='@year:[2011 2012]'
                       )
```

??? note "輸出"

    ```text
    0. Enroute Teens Orange Sandals (Score: 0.701)
    1. Fila Men Camper Brown Sandals (Score: 0.692)
    2. Clarks Men Black Leather Closed Sandals (Score: 0.691)
    3. Coolers Men Black Sandals (Score: 0.69)
    4. Coolers Men Black Sandals (Score: 0.69)
    5. Enroute Teens Brown Sandals (Score: 0.69)
    6. Crocs Dora Boots Pink Sandals (Score: 0.69)
    7. Enroute Men Leather Black Sandals (Score: 0.685)
    8. ADIDAS Men Navy Blue Benton Sandals (Score: 0.684)
    9. Coolers Men Black Sports Sandals (Score: 0.684)
    ```

```python
# hybrid query for sandals in the product vector and only include results within the 2011-2012 year range from the summer season
results = search_redis(redis_client,
                       "blue sandals",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='(@year:[2011 2012] @season:{Summer})'
                       )
```

??? note "輸出"

    ```text
    0. ADIDAS Men Navy Blue Benton Sandals (Score: 0.691)
    1. Enroute Teens Brown Sandals (Score: 0.681)
    2. ADIDAS Women's Adi Groove Blue Flip Flop (Score: 0.672)
    3. Enroute Women Turquoise Blue Flats (Score: 0.671)
    4. Red Tape Men Black Sandals (Score: 0.67)
    5. Enroute Teens Orange Sandals (Score: 0.661)
    6. Vans Men Blue Era Scilla Plaid Shoes (Score: 0.658)
    7. FILA Men Aruba Navy Blue Sandal (Score: 0.657)
    8. Quiksilver Men Blue Flip Flops (Score: 0.656)
    9. Reebok Men Navy Twist Sandals (Score: 0.656)
    ```

```python
# hybrid query for a brown belt filtering results by a year (NUMERIC) with a specific article types (TAG) and with a brand name (TEXT)
results = search_redis(redis_client,
                       "brown belt",
                       vector_field="product_vector",
                       k=10,
                       hybrid_fields='(@year:[2012 2012] @articleType:{Shirts | Belts} @productDisplayName:"Wrangler")'
                       )
```

??? note "輸出"

    ```text
    0. Wrangler Men Leather Brown Belt (Score: 0.67)
    1. Wrangler Women Black Belt (Score: 0.639)
    2. Wrangler Men Green Striped Shirt (Score: 0.575)
    3. Wrangler Men Purple Striped Shirt (Score: 0.549)
    4. Wrangler Men Griffith White Shirt (Score: 0.543)
    5. Wrangler Women Stella Green Shirt (Score: 0.542)
    ```

## 重點整理
- Redis 搭配 RediSearch（redis-stack）就能當向量資料庫，同時處理向量和一般資料。
- Hybrid 查詢是在向量相似度之外，再用 GEO、NUMERIC、TAG、TEXT 欄位過濾，邏輯放在資料庫端，應用程式碼更簡單。
- 建 index 要先定義 schema（含向量欄位、距離度量），再把文件寫進去，這裡用 HASH 型態存。
- 查詢文字也要用同一個 embedding 模型向量化，才能跟 index 裡的向量比較。
- 純向量搜尋找「意思相近」，加上全文條件後能同時要求關鍵字符合。

## 練習
1. 換一句自己的查詢文字，跑簡單向量搜尋，看回傳的商品是否合理。
2. 改變回傳筆數（例如 top 3 改成 top 10），觀察結果排名的變化。
3. 把 hybrid 查詢的全文條件換成另一個關鍵字，比較有無該條件時結果有什麼不同。
