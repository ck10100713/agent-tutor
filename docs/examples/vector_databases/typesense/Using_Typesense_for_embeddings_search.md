---
translated: true
source: examples/vector_databases/typesense/Using_Typesense_for_embeddings_search.ipynb
---

# 用 Typesense 做 embedding 搜尋

> 原文：[examples/vector_databases/typesense/Using_Typesense_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/typesense/Using_Typesense_for_embeddings_search.ipynb)



## 這篇在做什麼
這篇走一遍完整流程：載入已經 embed 好的資料、寫進 Typesense 這個向量搜尋引擎，再對標題和內容欄位做最近鄰搜尋。

## 學完你會
- 用 docker 在本機起一個 Typesense 服務，並用 Python client 連上
- 建立開啟向量索引的 collection，並把 embedding 批次寫進去
- 對 `title_vector`、`content_vector` 欄位做 nearest-neighbor 查詢

## 開跑前
- 本機要裝 Docker（或改用 Typesense Cloud，拿 hostname 和 API key 即可）
- OpenAI API key，用來把查詢文字轉成 embedding


這份 notebook 帶你走一個簡單的流程：下載資料、做 embedding，然後用向量資料庫建索引和搜尋。很多客戶想在安全的環境裡，用自己的資料存放和搜尋我們的 embedding，來支援 chatbot、主題建模等正式上線的應用，這就是常見的需求。

### 什麼是向量資料庫

向量資料庫是專門用來儲存、管理和搜尋 embedding 向量的資料庫。近年 AI 在自然語言、影像辨識等非結構化資料上越來越有效，用 embedding 把文字、音訊、影片等非結構化資料編碼成向量，再交給機器學習模型使用，這種做法大量成長。向量資料庫就是企業用來落地並擴大這些應用的有效方案。

### 為什麼要用向量資料庫

向量資料庫能讓企業把我們在這個 repo 分享的許多 embedding 應用（例如問答、chatbot、推薦服務）放到安全、可擴充的環境裡。很多客戶在小規模時 embedding 效果很好，但效能和安全性卡住了上線。我們認為向量資料庫是解決這個問題的關鍵元件，這份指南會帶你走過基本流程：embed 文字資料、存進向量資料庫、拿來做語意搜尋。


### Demo 流程
流程如下：
- **Setup**：匯入套件並設定需要的變數
- **載入資料**：載入資料集，用 OpenAI embedding 處理
- **Typesense**
    - *Setup*：設定 Typesense Python client，更多細節看[這裡](https://typesense.org/docs/0.24.0/api/)
    - *Index Data*：建立 collection，並對 __titles__ 和 __content__ 建索引
    - *Search Data*：依不同目的跑幾個範例查詢

跑完這份 notebook，你應該對怎麼設定和使用向量資料庫有基本概念，之後可以往更複雜的、用到 embedding 的應用前進。

## Setup

匯入需要的函式庫，並設定要用的 embedding 模型。

```python
# We'll need to install the Typesense client
!pip install typesense

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

# Typesense's client library for Python
import typesense

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## 載入資料

這一節載入事先準備好、已經 embed 完的資料。

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

## Typesense

接下來看的向量庫是 [Typesense](https://typesense.org/)，它是開源的 in-memory 搜尋引擎，可以自己 host，也可以用 [Typesense Cloud](https://cloud.typesense.org)。

Typesense 重視效能，整個索引放在 RAM（磁碟有備份）；也重視開箱即用的開發體驗，簡化選項並提供好的預設值。它也讓你同時用屬性過濾和向量查詢。

這個範例會在本機用 docker 起 Typesense server，把向量建索引，然後跑一些 nearest-neighbor 搜尋。如果用 Typesense Cloud，可以跳過 docker 設定，直接從叢集 dashboard 拿 hostname 和 API key。

### Setup

要在本機跑 Typesense 需要 [Docker](https://www.docker.com/)。照 Typesense 文件[這裡](https://typesense.org/docs/guide/install-typesense.html#docker-compose)的說明，我們在 repo 裡放了一個範例 docker-compose.yml，路徑是 [`docker-compose.yml`](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/typesense/docker-compose.yml)。

Docker 啟動後，切到 `examples/vector_databases/typesense/` 目錄執行 `docker-compose up -d`，就能在本機啟動 Typesense。

docker compose 檔裡預設 API key 是 `xyz`，預設 port 是 `8108`。

```python
import typesense

typesense_client = \
    typesense.Client({
        "nodes": [{
            "host": "localhost",  # For Typesense Cloud use xxx.a1.typesense.net
            "port": "8108",       # For Typesense Cloud use 443
            "protocol": "http"    # For Typesense Cloud use https
          }],
          "api_key": "xyz",
          "connection_timeout_seconds": 60
        })
```

### 建立索引

要在 Typesense 裡索引向量，先建一個 Collection（Document 的集合），並對特定欄位開啟向量索引。同一份 document 裡也可以存多個向量欄位。

```python
# Delete existing collections if they already exist
try:
    typesense_client.collections['wikipedia_articles'].delete()
except Exception as e:
    pass

# Create a new collection

schema = {
    "name": "wikipedia_articles",
    "fields": [
        {
            "name": "content_vector",
            "type": "float[]",
            "num_dim": len(article_df['content_vector'][0])
        },
        {
            "name": "title_vector",
            "type": "float[]",
            "num_dim": len(article_df['title_vector'][0])
        }
    ]
}

create_response = typesense_client.collections.create(schema)
print(create_response)

print("Created new collection wikipedia-articles")
```

??? note "輸出"

    ```text
    {'created_at': 1687165065, 'default_sorting_field': '', 'enable_nested_fields': False, 'fields': [{'facet': False, 'index': True, 'infix': False, 'locale': '', 'name': 'content_vector', 'num_dim': 1536, 'optional': False, 'sort': False, 'type': 'float[]'}, {'facet': False, 'index': True, 'infix': False, 'locale': '', 'name': 'title_vector', 'num_dim': 1536, 'optional': False, 'sort': False, 'type': 'float[]'}], 'name': 'wikipedia_articles', 'num_documents': 0, 'symbols_to_index': [], 'token_separators': []}
    Created new collection wikipedia-articles
    ```

```python
# Upsert the vector data into the collection we just created
#
# Note: This can take a few minutes, especially if your on an M1 and running docker in an emulated mode

print("Indexing vectors in Typesense...")

document_counter = 0
documents_batch = []

for k,v in article_df.iterrows():
    # Create a document with the vector data

    # Notice how you can add any fields that you haven't added to the schema to the document.
    # These will be stored on disk and returned when the document is a hit.
    # This is useful to store attributes required for display purposes.

    document = {
        "title_vector": v["title_vector"],
        "content_vector": v["content_vector"],
        "title": v["title"],
        "content": v["text"],
    }
    documents_batch.append(document)
    document_counter = document_counter + 1

    # Upsert a batch of 100 documents
    if document_counter % 100 == 0 or document_counter == len(article_df):
        response = typesense_client.collections['wikipedia_articles'].documents.import_(documents_batch)
        # print(response)

        documents_batch = []
        print(f"Processed {document_counter} / {len(article_df)} ")

print(f"Imported ({len(article_df)}) articles.")
```

??? note "輸出"

    ```text
    Indexing vectors in Typesense...
    Processed 100 / 25000 
    Processed 200 / 25000 
    Processed 300 / 25000 
    Processed 400 / 25000 
    Processed 500 / 25000 
    Processed 600 / 25000 
    Processed 700 / 25000 
    Processed 800 / 25000 
    Processed 900 / 25000 
    Processed 1000 / 25000 
    Processed 1100 / 25000 
    Processed 1200 / 25000 
    Processed 1300 / 25000 
    Processed 1400 / 25000 
    Processed 1500 / 25000 
    Processed 1600 / 25000 
    Processed 1700 / 25000 
    Processed 1800 / 25000 
    Processed 1900 / 25000 
    Processed 2000 / 25000 
    Processed 2100 / 25000 
    Processed 2200 / 25000 
    Processed 2300 / 25000 
    Processed 2400 / 25000 
    Processed 2500 / 25000 
    Processed 2600 / 25000 
    Processed 2700 / 25000 
    Processed 2800 / 25000 
    Processed 2900 / 25000 
    Processed 3000 / 25000 
    Processed 3100 / 25000 
    Processed 3200 / 25000 
    Processed 3300 / 25000 
    Processed 3400 / 25000 
    Processed 3500 / 25000 
    Processed 3600 / 25000 
    Processed 3700 / 25000 
    Processed 3800 / 25000 
    Processed 3900 / 25000 
    ... (省略 212 行)
    ```

```python
# Check the number of documents imported

collection = typesense_client.collections['wikipedia_articles'].retrieve()
print(f'Collection has {collection["num_documents"]} documents')
```

??? note "輸出"

    ```text
    Collection has 25000 documents
    ```

### 搜尋資料

向量匯入 Typesense 之後，就能對 `title_vector` 或 `content_vector` 欄位做最近鄰搜尋。

```python
def query_typesense(query, field='title', top_k=20):

    # Creates embedding vector from user query
    openai.api_key = os.getenv("OPENAI_API_KEY", "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    embedded_query = openai.Embedding.create(
        input=query,
        model=EMBEDDING_MODEL,
    )['data'][0]['embedding']

    typesense_results = typesense_client.multi_search.perform({
        "searches": [{
            "q": "*",
            "collection": "wikipedia_articles",
            "vector_query": f"{field}_vector:([{','.join(str(v) for v in embedded_query)}], k:{top_k})"
        }]
    }, {})

    return typesense_results
```

```python
query_results = query_typesense('modern art in Europe', 'title')

for i, hit in enumerate(query_results['results'][0]['hits']):
    document = hit["document"]
    vector_distance = hit["vector_distance"]
    print(f'{i + 1}. {document["title"]} (Distance: {vector_distance})')
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Distance: 0.12482291460037231)
    2. Western Europe (Distance: 0.13255876302719116)
    3. Renaissance art (Distance: 0.13584274053573608)
    4. Pop art (Distance: 0.1396539807319641)
    5. Northern Europe (Distance: 0.14534103870391846)
    6. Hellenistic art (Distance: 0.1472070813179016)
    7. Modernist literature (Distance: 0.15296930074691772)
    8. Art film (Distance: 0.1567266583442688)
    9. Central Europe (Distance: 0.15741699934005737)
    10. European (Distance: 0.1585891842842102)
    ```

```python
query_results = query_typesense('Famous battles in Scottish history', 'content')

for i, hit in enumerate(query_results['results'][0]['hits']):
    document = hit["document"]
    vector_distance = hit["vector_distance"]
    print(f'{i + 1}. {document["title"]} (Distance: {vector_distance})')
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn (Distance: 0.1306111216545105)
    2. Wars of Scottish Independence (Distance: 0.1384994387626648)
    3. 1651 (Distance: 0.14744246006011963)
    4. First War of Scottish Independence (Distance: 0.15033596754074097)
    5. Robert I of Scotland (Distance: 0.15376019477844238)
    6. 841 (Distance: 0.15609073638916016)
    7. 1716 (Distance: 0.15615153312683105)
    8. 1314 (Distance: 0.16280347108840942)
    9. 1263 (Distance: 0.16361045837402344)
    10. William Wallace (Distance: 0.16464537382125854)
    ```

謝謝你跟著做完，現在你已經能設定自己的向量資料庫，並用 embedding 做很多有趣的事。更複雜的用法請繼續看這個 repo 裡其他 cookbook 範例。

## 重點整理
- 向量資料庫專門存 embedding 並做相似度搜尋，是 embedding 應用走向正式環境的關鍵元件。
- Typesense 是 in-memory 的開源搜尋引擎，索引放 RAM，查詢快。
- 一個 document 可以有多個向量欄位，這篇分別對標題和內容建向量。
- 向量查詢可以跟屬性過濾搭配使用。
- 流程固定是：embed 資料、建 collection 並開向量索引、寫入、用查詢向量做最近鄰搜尋。

## 練習
1. 換一句查詢文字，分別對 `title_vector` 和 `content_vector` 搜尋，比較結果差異。
2. 調整搜尋回傳的筆數（`k` 之類的參數），看結果數量怎麼變。
3. 在 collection schema 加一個可過濾的欄位，查詢時同時用屬性過濾和向量搜尋。
