---
translated: true
source: examples/vector_databases/myscale/Getting_started_with_MyScale_and_OpenAI.ipynb
---

# 用 MyScale 當 OpenAI embedding 的向量資料庫

> 原文：[examples/vector_databases/myscale/Getting_started_with_MyScale_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/myscale/Getting_started_with_MyScale_and_OpenAI.ipynb)



## 這篇在做什麼

把 OpenAI 預先算好的 Wikipedia embedding 存進雲端的 MyScale，再用 OpenAI API 把查詢文字轉成 embedding，到 MyScale 做最近鄰搜尋。MyScale 是架在 ClickHouse 上的資料庫，向量搜尋可以直接用 SQL 下。

## 學完你會

- 用 `clickhouse-connect` 連上 MyScale 叢集
- 建一張帶向量索引（cosine distance）的 SQL 表，並把 embedding 灌進去
- 把查詢文字轉成 embedding，在 MyScale 裡找出最相近的文章

## 開跑前

- 一個 MyScale 叢集（照 [quickstart](https://docs.myscale.com/en/quickstart/) 建好）
- OpenAI API key

### 什麼是 MyScale

[MyScale](https://myscale.com) 是建在 Clickhouse 上的資料庫，把向量搜尋跟 SQL 分析結合在一起，效能高、全託管。結構化資料跟向量資料可以一起查、一起分析，所有資料處理都有完整的 SQL 支援。

### 部署方式

- 用 [MyScale Console](https://console.myscale.com)，兩分鐘內就能在自己的叢集上用 SQL 跑向量搜尋。


## 前置需求

你需要：

1. 照 [quickstart](https://docs.myscale.com/en/quickstart/) 部署好的 MyScale 叢集。
2. 用來連 MyScale 的 `clickhouse-connect` 套件。
3. 一把 [OpenAI API key](https://beta.openai.com/account/api-keys)，用來把查詢向量化。

### 安裝套件

這份 notebook 需要 `openai`、`clickhouse-connect` 和其他幾個套件，用下面的指令安裝：

```python
! pip install openai clickhouse-connect wget pandas
```

### 設定 OpenAI API key

要用 OpenAI API 就得先有 API key，沒有的話可以到 [OpenAI](https://platform.openai.com/account/api-keys) 申請。

```python
import openai

# get API key from on OpenAI website
openai.api_key = "OPENAI_API_KEY"

# check we have authenticated
openai.Engine.list()
```

## 連上 MyScale

照[連線資訊](https://docs.myscale.com/en/cluster-management/)的說明，從 MyScale console 取得叢集的 host、使用者名稱和密碼，然後像下面這樣建立連線：

```python
import clickhouse_connect

# initialize client
client = clickhouse_connect.get_client(host='YOUR_CLUSTER_HOST', port=8443, username='YOUR_USERNAME', password='YOUR_CLUSTER_PASSWORD')
```

## 載入資料

要載入 OpenAI 提供的 Wikipedia 文章 embedding 資料集，用 `wget` 套件下載。

```python
import wget

embeddings_url = "https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip"

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

下載完用 `zipfile` 套件解壓縮：

```python
import zipfile

with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip", "r") as zip_ref:
    zip_ref.extractall("../data")
```

接著把 `vector_database_wikipedia_articles_embedded.csv` 讀進 Pandas DataFrame：

```python
import pandas as pd

from ast import literal_eval

# read data from csv
article_df = pd.read_csv('../data/vector_database_wikipedia_articles_embedded.csv')
article_df = article_df[['id', 'url', 'title', 'text', 'content_vector']]

# read vectors from strings back into a list
article_df["content_vector"] = article_df.content_vector.apply(literal_eval)
article_df.head()
```

## 建立索引

我們在 MyScale 建一張叫 `articles` 的 SQL 表來放 embedding。表裡有一個 cosine distance 的向量索引，還有 embedding 長度的限制。用下面的程式建表並寫入資料：

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

# upload data in batches
data = article_df.to_records(index=False).tolist()
column_names = article_df.columns.tolist() 

for i in tqdm(range(0, total_records, batch_size)):
    i_end = min(i + batch_size, total_records)
    client.insert("default.articles", data[i:i_end], column_names=column_names)
```

向量索引是在背景自動建的，搜尋前要先檢查建構狀態。

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
    index build status: Built
    ```

## 搜尋資料

資料進了 MyScale 之後就能做向量搜尋，找相似內容。先用 OpenAI API 幫查詢產生 embedding，再用 MyScale 搜。

```python
import openai

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

- MyScale 把向量搜尋放進 SQL，向量欄位跟一般結構化欄位可以在同一個查詢裡用。
- 流程是固定的：預先算好 embedding、建表加向量索引、寫入資料、查詢時再算一次 embedding 去比。
- 查詢和資料必須用同一個 embedding 模型，距離才有意義。
- 向量索引是背景非同步建的，沒建完就搜，結果可能不完整或較慢。

## 練習

1. 把查詢文字換成別的主題，看看回傳的文章標題合不合理。
2. 改搜尋那段，調整回傳筆數，比較結果的相似度分數變化。
3. 在搜尋的 SQL 加上 `WHERE` 條件（例如用標題過濾），體驗向量搜尋跟一般 SQL 條件混用。
