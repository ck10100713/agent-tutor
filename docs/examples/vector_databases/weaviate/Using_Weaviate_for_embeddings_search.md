---
translated: true
source: examples/vector_databases/weaviate/Using_Weaviate_for_embeddings_search.ipynb
---

# 用 Weaviate 做 embeddings 搜尋

> 原文：[examples/vector_databases/weaviate/Using_Weaviate_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/Using_Weaviate_for_embeddings_search.ipynb)



## 這篇在做什麼

帶你走一遍完整流程：載入已經做好 embedding 的資料、建立 Weaviate 的 schema 並寫入、再用向量做相似度搜尋。最後也示範讓 Weaviate 內建的 OpenAI module 自動幫你產生 query 的 embedding。

## 學完你會

- 用 Docker 或 Weaviate Cloud Service 起一個 Weaviate，並用 Python client 連上去。
- 建立 `Article` schema，把標題向量寫進去，然後用向量查詢找相近的文章。
- 用 `with_near_text` 讓 Weaviate 的 text2vec-openai module 自動產生 embedding 來搜尋。

## 開跑前

- 自架需要 [Docker](https://www.docker.com/)，也可以改用 Weaviate Cloud Service 建免費 cluster。
- 用 `with_near_text` 需要 `OPENAI_API_KEY`。

這個 notebook 帶你走一個簡單的流程：下載資料、做 embedding，然後用幾種 vector database 建立索引並搜尋。很多客戶需要在安全的環境裡，把我們的 embeddings 和自己的資料一起儲存、搜尋，來支援聊天機器人、topic modelling 等正式環境的情境，這就是這個流程要解決的。

### 什麼是 Vector Database

vector database 是專門用來儲存、管理和搜尋 embedding 向量的資料庫。近年來，隨著 AI 在自然語言、圖像辨識等非結構化資料上的效果越來越好，用 embeddings 把非結構化資料（文字、音訊、影片等）編碼成向量，給機器學習模型使用的做法暴增。vector database 就是企業用來落地並擴展這些情境的有效方案。

### 為什麼要用 Vector Database

vector database 讓企業可以把這個 repo 裡分享過的許多 embeddings 使用情境（例如問答、聊天機器人和推薦服務），放到安全、可擴展的環境裡。很多客戶用 embeddings 在小規模時能解決問題，但效能和安全性讓他們沒辦法上正式環境。我們認為 vector database 是解決這件事的關鍵元件，這份指南會帶你走過基本流程：對文字資料做 embedding、存進 vector database，再用來做語意搜尋。


### Demo 流程
流程如下：
- **Setup**：匯入套件並設定需要的變數
- **載入資料**：載入資料集並用 OpenAI embeddings 做 embedding
- **Weaviate**
    - *Setup*：在這裡設定 Weaviate 的 Python client。更多細節看[這裡](https://weaviate.io/developers/weaviate/current/client-libraries/python.html)
    - *建立索引資料*：我們會建立一個包含 __title__ 搜尋向量的索引
    - *搜尋資料*：跑幾個搜尋確認功能正常

跑完這個 notebook 之後，你應該對怎麼設定和使用 vector database 有基本的理解，可以繼續做更複雜的 embeddings 應用。

## Setup

匯入需要的函式庫，並設定想用的 embedding 模型。

```python
# We'll need to install the Weaviate client
!pip install weaviate-client

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

# Weaviate's client library for Python
import weaviate

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## 載入資料

這一節載入我們事先準備好、已經做過 embedding 的資料。

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

## Weaviate

我們要探索的另一個 vector database 選項是 **Weaviate**，它同時提供託管的 [SaaS](https://console.weaviate.io/) 和自架的[開源](https://github.com/weaviate/weaviate)版本。前面已經看過雲端的 vector database，所以這裡試試自架的版本。

我們會：
- 在本機部署 Weaviate
- 在 Weaviate 建立索引
- 把資料存進去
- 送出一些相似度搜尋 query
- 試一個真實的使用情境


### 自備向量的做法
這份 cookbook 提供的資料已經產生好向量。如果你的資料本來就已經向量化，這是個好做法。

### 用 OpenAI module 自動向量化
如果你的資料還沒向量化，可以把用 OpenAI 做向量化的工作交給 Weaviate。
Weaviate 內建 [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai) module，會幫你處理這些時機的向量化：
* 匯入時
* 任何 CRUD 操作
* 語意搜尋

想一步一步學怎麼一次完成匯入和向量化，看 [Getting Started with Weaviate and OpenAI module cookbook](getting-started-with-weaviate-and-openai.md)。

### Setup

要在本機執行 Weaviate，需要 [Docker](https://www.docker.com/)。照 Weaviate 文件[這裡](https://weaviate.io/developers/weaviate/installation/docker-compose)的說明，我們在這個 repo 做了一個範例 docker-compose.yml，放在 [`docker-compose.yml`](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/docker-compose.yml)。

啟動 Docker 之後，進到 `examples/vector_databases/weaviate/` 目錄執行 `docker-compose up -d`，就能在本機啟動 Weaviate。

#### SaaS
你也可以用 [Weaviate Cloud Service](https://console.weaviate.io/)（WCS）建立免費的 Weaviate cluster。
1. 建立免費帳號或登入 [WCS](https://console.weaviate.io/)
2. 用以下設定建立一個 `Weaviate Cluster`：
    * Sandbox：`Sandbox Free`
    * Weaviate Version：用預設（最新版）
    * OIDC Authentication：`Disabled`
3. instance 一兩分鐘內就會準備好
4. 記下 `Cluster Id`。這個連結會帶你到 cluster 的完整路徑（之後連線會用到），大概長這樣：`https://your-project-name-suffix.weaviate.network` 

```python
# Option #1 - Self-hosted - Weaviate Open Source 
client = weaviate.Client(
    url="http://localhost:8080",
    additional_headers={
        "X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")
    }
)
```

```python
# Option #2 - SaaS - (Weaviate Cloud Service)
client = weaviate.Client(
    url="https://your-wcs-instance-name.weaviate.network",
    additional_headers={
        "X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")
    }
)
```

```python
client.is_ready()
```

### 建立索引資料

在 Weaviate 裡，你用 __schema__ 來描述每一種要搜尋的實體。 

這裡我們建立一個叫 **Article** 的 schema，包含上面準備好的 **title** 向量，供我們搜尋。

接下來幾個步驟，緊跟 Weaviate 提供的[文件](https://weaviate.io/developers/weaviate/quickstart)。


```python
# Clear up the schema, so that we can recreate it
client.schema.delete_all()
client.schema.get()

# Define the Schema object to use `text-embedding-3-small` on `title` and `content`, but skip it for `url`
article_schema = {
    "class": "Article",
    "description": "A collection of articles",
    "vectorizer": "text2vec-openai",
    "moduleConfig": {
        "text2vec-openai": {
          "model": "ada",
          "modelVersion": "002",
          "type": "text"
        }
    },
    "properties": [{
        "name": "title",
        "description": "Title of the article",
        "dataType": ["string"]
    },
    {
        "name": "content",
        "description": "Contents of the article",
        "dataType": ["text"],
        "moduleConfig": { "text2vec-openai": { "skip": True } }
    }]
}

# add the Article schema
client.schema.create_class(article_schema)

# get the schema to make sure it worked
client.schema.get()
```

??? note "輸出"

    ```text
    {'classes': [{'class': 'Article',
       'description': 'A collection of articles',
       'invertedIndexConfig': {'bm25': {'b': 0.75, 'k1': 1.2},
        'cleanupIntervalSeconds': 60,
        'stopwords': {'additions': None, 'preset': 'en', 'removals': None}},
       'moduleConfig': {'text2vec-openai': {'model': 'ada',
         'modelVersion': '002',
         'type': 'text',
         'vectorizeClassName': True}},
       'properties': [{'dataType': ['string'],
         'description': 'Title of the article',
         'moduleConfig': {'text2vec-openai': {'skip': False,
           'vectorizePropertyName': False}},
         'name': 'title',
         'tokenization': 'word'},
        {'dataType': ['text'],
         'description': 'Contents of the article',
         'moduleConfig': {'text2vec-openai': {'skip': True,
           'vectorizePropertyName': False}},
         'name': 'content',
         'tokenization': 'word'}],
       'replicationConfig': {'factor': 1},
       'shardingConfig': {'virtualPerPhysical': 128,
        'desiredCount': 1,
        'actualCount': 1,
        'desiredVirtualCount': 128,
        'actualVirtualCount': 128,
        'key': '_id',
        'strategy': 'hash',
        'function': 'murmur3'},
       'vectorIndexConfig': {'skip': False,
        'cleanupIntervalSeconds': 300,
        'maxConnections': 64,
        'efConstruction': 128,
        'ef': -1,
        'dynamicEfMin': 100,
        'dynamicEfMax': 500,
        'dynamicEfFactor': 8,
        'vectorCacheMaxObjects': 1000000000000,
        'flatSearchCutoff': 40000,
    ... (省略 3 行)
    ```

```python
### Step 1 - configure Weaviate Batch, which optimizes CRUD operations in bulk
# - starting batch size of 100
# - dynamically increase/decrease based on performance
# - add timeout retries if something goes wrong

client.batch.configure(
    batch_size=100,
    dynamic=True,
    timeout_retries=3,
)
```

??? note "輸出"

    ```text
    <weaviate.batch.crud_batch.Batch at 0x3f0ca0fa0>
    ```

```python
### Step 2 - import data

print("Uploading data with vectors to Article schema..")

counter=0

with client.batch as batch:
    for k,v in article_df.iterrows():
        
        # print update message every 100 objects        
        if (counter %100 == 0):
            print(f"Import {counter} / {len(article_df)} ")
        
        properties = {
            "title": v["title"],
            "content": v["text"]
        }
        
        vector = v["title_vector"]
        
        batch.add_data_object(properties, "Article", None, vector)
        counter = counter+1

print(f"Importing ({len(article_df)}) Articles complete")
```

??? note "輸出"

    ```text
    Uploading data with vectors to Article schema..
    Import 0 / 25000 
    Import 100 / 25000 
    Import 200 / 25000 
    Import 300 / 25000 
    Import 400 / 25000 
    Import 500 / 25000 
    Import 600 / 25000 
    Import 700 / 25000 
    Import 800 / 25000 
    Import 900 / 25000 
    Import 1000 / 25000 
    Import 1100 / 25000 
    Import 1200 / 25000 
    Import 1300 / 25000 
    Import 1400 / 25000 
    Import 1500 / 25000 
    Import 1600 / 25000 
    Import 1700 / 25000 
    Import 1800 / 25000 
    Import 1900 / 25000 
    Import 2000 / 25000 
    Import 2100 / 25000 
    Import 2200 / 25000 
    Import 2300 / 25000 
    Import 2400 / 25000 
    Import 2500 / 25000 
    Import 2600 / 25000 
    Import 2700 / 25000 
    Import 2800 / 25000 
    Import 2900 / 25000 
    Import 3000 / 25000 
    Import 3100 / 25000 
    Import 3200 / 25000 
    Import 3300 / 25000 
    Import 3400 / 25000 
    Import 3500 / 25000 
    Import 3600 / 25000 
    Import 3700 / 25000 
    Import 3800 / 25000 
    ... (省略 212 行)
    ```

```python
# Test that all data has loaded – get object count
result = (
    client.query.aggregate("Article")
    .with_fields("meta { count }")
    .do()
)
print("Object count: ", result["data"]["Aggregate"]["Article"])
```

??? note "輸出"

    ```text
    Object count:  [{'meta': {'count': 25000}}]
    ```

```python
# Test one article has worked by checking one object
test_article = (
    client.query
    .get("Article", ["title", "content", "_additional {id}"])
    .with_limit(1)
    .do()
)["data"]["Get"]["Article"][0]

print(test_article["_additional"]["id"])
print(test_article["title"])
print(test_article["content"])
```

??? note "輸出"

    ```text
    000393f2-1182-4e3d-abcf-4217eda64be0
    Lago d'Origlio
    Lago d'Origlio is a lake in the municipality of Origlio, in Ticino, Switzerland.

    Lakes of Ticino
    ```

### 搜尋資料

跟前面一樣，我們對新建的索引送出一些 query，根據跟現有向量的接近程度取回結果

```python
def query_weaviate(query, collection_name, top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model=EMBEDDING_MODEL,
    )["data"][0]['embedding']
    
    near_vector = {"vector": embedded_query}

    # Queries input schema with vectorised user query
    query_result = (
        client.query
        .get(collection_name, ["title", "content", "_additional {certainty distance}"])
        .with_near_vector(near_vector)
        .with_limit(top_k)
        .do()
    )
    
    return query_result
```

```python
query_result = query_weaviate("modern art in Europe", "Article")
counter = 0
for article in query_result["data"]["Get"]["Article"]:
    counter += 1
    print(f"{counter}. { article['title']} (Certainty: {round(article['_additional']['certainty'],3) }) (Distance: {round(article['_additional']['distance'],3) })")
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Certainty: 0.938) (Distance: 0.125)
    2. Western Europe (Certainty: 0.934) (Distance: 0.133)
    3. Renaissance art (Certainty: 0.932) (Distance: 0.136)
    4. Pop art (Certainty: 0.93) (Distance: 0.14)
    5. Northern Europe (Certainty: 0.927) (Distance: 0.145)
    6. Hellenistic art (Certainty: 0.926) (Distance: 0.147)
    7. Modernist literature (Certainty: 0.924) (Distance: 0.153)
    8. Art film (Certainty: 0.922) (Distance: 0.157)
    9. Central Europe (Certainty: 0.921) (Distance: 0.157)
    10. European (Certainty: 0.921) (Distance: 0.159)
    11. Art (Certainty: 0.921) (Distance: 0.159)
    12. Byzantine art (Certainty: 0.92) (Distance: 0.159)
    13. Postmodernism (Certainty: 0.92) (Distance: 0.16)
    14. Eastern Europe (Certainty: 0.92) (Distance: 0.161)
    15. Europe (Certainty: 0.919) (Distance: 0.161)
    16. Cubism (Certainty: 0.919) (Distance: 0.161)
    17. Impressionism (Certainty: 0.919) (Distance: 0.162)
    18. Bauhaus (Certainty: 0.919) (Distance: 0.162)
    19. Expressionism (Certainty: 0.918) (Distance: 0.163)
    20. Surrealism (Certainty: 0.918) (Distance: 0.163)
    ```

```python
query_result = query_weaviate("Famous battles in Scottish history", "Article")
counter = 0
for article in query_result["data"]["Get"]["Article"]:
    counter += 1
    print(f"{counter}. {article['title']} (Score: {round(article['_additional']['certainty'],3) })")
```

??? note "輸出"

    ```text
    1. Historic Scotland (Score: 0.946)
    2. First War of Scottish Independence (Score: 0.946)
    3. Battle of Bannockburn (Score: 0.946)
    4. Wars of Scottish Independence (Score: 0.944)
    5. Second War of Scottish Independence (Score: 0.94)
    6. List of Scottish monarchs (Score: 0.937)
    7. Scottish Borders (Score: 0.932)
    8. Braveheart (Score: 0.929)
    9. John of Scotland (Score: 0.929)
    10. Guardians of Scotland (Score: 0.926)
    11. Holyrood Abbey (Score: 0.925)
    12. Scottish (Score: 0.925)
    13. Scots (Score: 0.925)
    14. Robert I of Scotland (Score: 0.924)
    15. Scottish people (Score: 0.924)
    16. Edinburgh Castle (Score: 0.924)
    17. Alexander I of Scotland (Score: 0.924)
    18. Robert Burns (Score: 0.924)
    19. Battle of Bosworth Field (Score: 0.922)
    20. David II of Scotland (Score: 0.922)
    ```

### 讓 Weaviate 處理向量 embedding

Weaviate 有[內建的 OpenAI module](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai)，會處理 query 和任何 CRUD 操作所需的 embedding 產生步驟。

這讓你可以用 `with_near_text` filter 執行向量查詢，它會用你的 `OPEN_API_KEY`。

```python
def near_text_weaviate(query, collection_name):
    
    nearText = {
        "concepts": [query],
        "distance": 0.7,
    }

    properties = [
        "title", "content",
        "_additional {certainty distance}"
    ]

    query_result = (
        client.query
        .get(collection_name, properties)
        .with_near_text(nearText)
        .with_limit(20)
        .do()
    )["data"]["Get"][collection_name]
    
    print (f"Objects returned: {len(query_result)}")
    
    return query_result
```

```python
query_result = near_text_weaviate("modern art in Europe","Article")
counter = 0
for article in query_result:
    counter += 1
    print(f"{counter}. { article['title']} (Certainty: {round(article['_additional']['certainty'],3) }) (Distance: {round(article['_additional']['distance'],3) })")
```

??? note "輸出"

    ```text
    Objects returned: 20
    1. Museum of Modern Art (Certainty: 0.938) (Distance: 0.125)
    2. Western Europe (Certainty: 0.934) (Distance: 0.133)
    3. Renaissance art (Certainty: 0.932) (Distance: 0.136)
    4. Pop art (Certainty: 0.93) (Distance: 0.14)
    5. Northern Europe (Certainty: 0.927) (Distance: 0.145)
    6. Hellenistic art (Certainty: 0.926) (Distance: 0.147)
    7. Modernist literature (Certainty: 0.923) (Distance: 0.153)
    8. Art film (Certainty: 0.922) (Distance: 0.157)
    9. Central Europe (Certainty: 0.921) (Distance: 0.157)
    10. European (Certainty: 0.921) (Distance: 0.159)
    11. Art (Certainty: 0.921) (Distance: 0.159)
    12. Byzantine art (Certainty: 0.92) (Distance: 0.159)
    13. Postmodernism (Certainty: 0.92) (Distance: 0.16)
    14. Eastern Europe (Certainty: 0.92) (Distance: 0.161)
    15. Europe (Certainty: 0.919) (Distance: 0.161)
    16. Cubism (Certainty: 0.919) (Distance: 0.161)
    17. Impressionism (Certainty: 0.919) (Distance: 0.162)
    18. Bauhaus (Certainty: 0.919) (Distance: 0.162)
    19. Surrealism (Certainty: 0.918) (Distance: 0.163)
    20. Expressionism (Certainty: 0.918) (Distance: 0.163)
    ```

```python
query_result = near_text_weaviate("Famous battles in Scottish history","Article")
counter = 0
for article in query_result:
    counter += 1
    print(f"{counter}. { article['title']} (Certainty: {round(article['_additional']['certainty'],3) }) (Distance: {round(article['_additional']['distance'],3) })")
```

??? note "輸出"

    ```text
    Objects returned: 20
    1. Historic Scotland (Certainty: 0.946) (Distance: 0.107)
    2. First War of Scottish Independence (Certainty: 0.946) (Distance: 0.108)
    3. Battle of Bannockburn (Certainty: 0.946) (Distance: 0.109)
    4. Wars of Scottish Independence (Certainty: 0.944) (Distance: 0.111)
    5. Second War of Scottish Independence (Certainty: 0.94) (Distance: 0.121)
    6. List of Scottish monarchs (Certainty: 0.937) (Distance: 0.127)
    7. Scottish Borders (Certainty: 0.932) (Distance: 0.137)
    8. Braveheart (Certainty: 0.929) (Distance: 0.141)
    9. John of Scotland (Certainty: 0.929) (Distance: 0.142)
    10. Guardians of Scotland (Certainty: 0.926) (Distance: 0.148)
    11. Holyrood Abbey (Certainty: 0.925) (Distance: 0.15)
    12. Scottish (Certainty: 0.925) (Distance: 0.15)
    13. Scots (Certainty: 0.925) (Distance: 0.15)
    14. Robert I of Scotland (Certainty: 0.924) (Distance: 0.151)
    15. Scottish people (Certainty: 0.924) (Distance: 0.152)
    16. Edinburgh Castle (Certainty: 0.924) (Distance: 0.153)
    17. Alexander I of Scotland (Certainty: 0.924) (Distance: 0.153)
    18. Robert Burns (Certainty: 0.924) (Distance: 0.153)
    19. Battle of Bosworth Field (Certainty: 0.922) (Distance: 0.155)
    20. David II of Scotland (Certainty: 0.922) (Distance: 0.157)
    ```

## 重點整理

- vector database 專門存 embedding 向量並做相似度搜尋，讓 embeddings 應用能放進可擴展、安全的環境。
- Weaviate 用 schema 描述要搜尋的實體，向量跟資料一起存。
- 資料已有向量就自備向量，還沒有的話可以交給內建的 text2vec-openai module。
- 查詢時只要給文字，module 就會幫你把 query 轉成向量，不用自己呼叫 embeddings API。
- 自架和 SaaS 兩種部署方式，只差連線的 URL，其餘流程一樣。

## 練習

1. 換一個搜尋 query 文字，比較自備向量查詢和 `with_near_text` 查詢的結果差在哪。
2. 調整查詢的回傳筆數上限，觀察結果數量和相似度排序的變化。
3. 在 schema 裡多加一個屬性（例如文章內文的向量或文字欄位），重新匯入資料後，改用它來搜尋。
