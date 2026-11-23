---
translated: true
source: examples/vector_databases/myscale/Using_MyScale_for_embeddings_search.ipynb
---

# 用 MyScale 做 embedding 搜尋

> 原文：[examples/vector_databases/myscale/Using_MyScale_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/myscale/Using_MyScale_for_embeddings_search.ipynb)

## 這篇在做什麼
走一遍完整流程：載入已經 embed 好的資料，建到 MyScale（建在 ClickHouse 上、結合向量搜尋與 SQL 分析的資料庫），再用 SQL 做向量搜尋。

## 學完你會
- 連上 MyScale cluster，建立有向量 index（cosine distance）的 SQL 表
- 把 embedding 資料寫進表，並檢查向量 index 的建置狀態
- 用 OpenAI 把 query 轉成 embedding，再用 MyScale 做向量搜尋

## 開跑前
- 一個 MyScale cluster，從 [MyScale Console](https://console.myscale.com) 取得 host、username、password
- OpenAI API key

這個 notebook 帶你走一個簡單流程：下載資料、做 embedding，再用向量資料庫建索引並搜尋。很多客戶想在安全的環境裡儲存、搜尋自己資料的 embedding，來支援聊天機器人、主題建模等正式環境的用途，這就是常見的需求。

### 什麼是向量資料庫

向量資料庫是專門用來儲存、管理和搜尋 embedding 向量的資料庫。近年 AI 在自然語言、影像辨識等非結構化資料的應用越來越有效，把文字、音訊、影片等非結構化資料編碼成向量給機器學習模型使用的做法也快速成長，向量資料庫就成了企業落地這些應用並擴大規模的有效方案。

### 為什麼要用向量資料庫

向量資料庫讓企業能把這個 repo 裡分享過的許多 embedding 用例（例如問答、聊天機器人、推薦服務），放到安全、可擴展的環境中運行。很多客戶在小規模時 embedding 能解決問題，但效能和安全性擋住了上線，我們認為向量資料庫是解決這件事的關鍵元件。這份指南會走過基本流程：embed 文字資料、存進向量資料庫，並用來做語意搜尋。


### Demo 流程
流程如下：
- **設定**：import 套件、設定需要的變數
- **載入資料**：載入資料集，並用 OpenAI embedding 處理
- **MyScale**
    - *設定*：設定 MyScale 的 Python client，詳情看[這裡](https://docs.myscale.com/en/python-client/)
    - *建索引*：建一個表，並為 __content__ 建索引。
    - *搜尋*：針對不同目標跑幾個範例 query。

跑完這個 notebook，你應該對向量資料庫怎麼設定和使用有基本概念，之後可以進一步做更複雜、運用 embedding 的用例。

## 設定

import 需要的函式庫，並設定想用的 embedding 模型。

```python
# We'll need to install the MyScale client
!pip install clickhouse-connect

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

# MyScale's client library for Python
import clickhouse_connect

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## 載入資料

這一節載入我們事先準備好、已經 embed 完的資料。

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

## MyScale
下一個要看的向量資料庫是 [MyScale](https://myscale.com)。

[MyScale](https://myscale.com) 是建在 Clickhouse 上的資料庫，結合向量搜尋和 SQL 分析，提供高效能、簡化且完全託管的體驗。它設計用來對結構化資料和向量資料做聯合查詢與分析，所有資料處理都有完整的 SQL 支援。

用 [MyScale Console](https://console.myscale.com)，兩分鐘內就能在你的 cluster 部署並用 SQL 執行向量搜尋。

### 連線到 MyScale

照著[連線資訊](https://docs.myscale.com/en/cluster-management/)那一節，從 MyScale console 取得 cluster 的 host、username 和 password，並如下面所示用它們建立 cluster 的連線：

```python
# initialize client
client = clickhouse_connect.get_client(host='YOUR_CLUSTER_HOST', port=8443, username='YOUR_USERNAME', password='YOUR_CLUSTER_PASSWORD')
```

### 資料建索引

我們會在 MyScale 建一個叫 `articles` 的 SQL 表來存 embedding 資料。表裡會有一個 cosine distance 度量的向量 index，以及 embedding 長度的限制。用下面的程式碼建立 articles 表並寫入資料：

```python
# create articles table with vector index
embedding_len=len(article_df['content_vector'][0]) # 1536

client.command(f"""
CREATE TABLE IF NOT EXISTS default.articles
(
    id UInt64,
    url String,
    title String,
    text String,
    content_vector Array(Float32),
    CONSTRAINT cons_vector_len CHECK length(content_vector) = {embedding_len},
    VECTOR INDEX article_content_index content_vector TYPE HNSWFLAT('metric_type=Cosine')
)
ENGINE = MergeTree ORDER BY id
""")

# insert data into the table in batches
from tqdm.auto import tqdm

batch_size = 100
total_records = len(article_df)

# we only need subset of columns
article_df = article_df[['id', 'url', 'title', 'text', 'content_vector']]

# upload data in batches
data = article_df.to_records(index=False).tolist()
column_names = article_df.columns.tolist()

for i in tqdm(range(0, total_records, batch_size)):
    i_end = min(i + batch_size, total_records)
    client.insert("default.articles", data[i:i_end], column_names=column_names)
```

??? note "輸出"

    ```text
      0%|          | 0/250 [00:00<?, ?it/s]
    ```

向量 index 會在背景自動建置，所以搜尋前要先檢查它的建置狀態。

```python
# check count of inserted data
print(f"articles count: {client.command('SELECT count(*) FROM default.articles')}")

# check the status of the vector index, make sure vector index is ready with 'Built' status
get_index_status="SELECT status FROM system.vector_indices WHERE name='article_content_index'"
print(f"index build status: {client.command(get_index_status)}")
```

??? note "輸出"

    ```text
    articles count: 25000
    index build status: InProgress
    ```

### 搜尋資料

資料在 MyScale 建好索引後，就能做向量搜尋找出相似內容。我們先用 OpenAI API 為 query 產生 embedding，再用 MyScale 執行向量搜尋。

```python
query = "Famous battles in Scottish history"

# creates embedding vector from user query
embed = openai.Embedding.create(
    input=query,
    model="text-embedding-3-small",
)["data"][0]["embedding"]

# query the database to find the top K similar content to the given query
top_k = 10
results = client.query(f"""
SELECT id, url, title, distance(content_vector, {embed}) as dist
FROM default.articles
ORDER BY dist
LIMIT {top_k}
""")

# display results
for i, r in enumerate(results.named_results()):
    print(i+1, r['title'])
```

??? note "輸出"

    ```text
    1 Battle of Bannockburn
    2 Wars of Scottish Independence
    3 1651
    4 First War of Scottish Independence
    5 Robert I of Scotland
    6 841
    7 1716
    8 1314
    9 1263
    10 William Wallace
    ```

## 重點整理
- MyScale 把向量搜尋和 SQL 放在一起，可以對結構化資料和向量資料做聯合查詢。
- 向量 index 在背景建置，搜尋前要先確認建置完成。
- 建表時就指定距離度量（這裡是 cosine）和 embedding 長度限制。
- 搜尋流程仍是 query 轉 embedding，再用 SQL 找最近鄰。

## 練習
1. 換一句自己的 query 做搜尋，看回來的內容是否相關。
2. 改搜尋 SQL 的 LIMIT，看回傳筆數變化。
3. 在搜尋 SQL 加一個 WHERE 條件過濾其他欄位，結合結構化與向量查詢。
