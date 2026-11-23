---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/tair/Getting_started_with_Tair_and_OpenAI.ipynb
---

# 用 Tair 當 OpenAI embedding 的向量資料庫

> 原文：[examples/vector_databases/tair/Getting_started_with_Tair_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/tair/Getting_started_with_Tair_and_OpenAI.ipynb)

## 這篇在做什麼
一步步示範把 Tair（阿里雲的雲端記憶體資料庫）當成向量資料庫，存 OpenAI 的 embedding 並做最近鄰搜尋。資料用事先算好的 Wikipedia embedding，不用自己花錢重算。

## 學完你會
- 連上 Tair 並建立 title 和 content 兩個向量 index
- 把預先算好的 embedding 載入 Tair
- 把文字 query 轉成 embedding，再用 Tair 做最近鄰搜尋，並切換 title 或 content 搜尋

## 開跑前
- 一個 Tair 雲端 instance（阿里雲）
- OpenAI API key
- 安裝 `openai`、`tair` 等套件

這個 notebook 帶你一步步用 Tair 當 OpenAI embedding 的向量資料庫。

完整流程是：
1. 使用 OpenAI API 事先算好的 embedding。
2. 把 embedding 存到雲端的 Tair instance。
3. 用 OpenAI API 把文字 query 轉成 embedding。
4. 用 Tair 在建好的 collection 裡做最近鄰搜尋。

### 什麼是 Tair

[Tair](https://www.alibabacloud.com/help/en/tair/latest/what-is-tair) 是阿里雲開發的雲原生記憶體資料庫服務，相容開源 Redis，提供多種資料模型和企業級能力，支援即時線上場景。Tair 也推出了基於新型非揮發性記憶體（NVM）儲存媒介的持久化記憶體優化 instance，可以降低 30% 成本、確保資料持久化，效能幾乎和記憶體資料庫一樣。Tair 已廣泛用在政務、金融、製造、醫療和泛網際網路等領域，滿足高速查詢和運算需求。

[Tairvector](https://www.alibabacloud.com/help/en/tair/latest/tairvector) 是自家的資料結構，提供高效能的即時向量儲存與檢索。TairVector 提供兩種索引演算法：Hierarchical Navigable Small World (HNSW) 和 Flat Search。它也支援多種距離函式，像歐氏距離、內積、Jaccard 距離。和傳統向量檢索服務相比，TairVector 有這些優點：
- 所有資料放在記憶體，支援即時更新索引，降低讀寫延遲。
- 在記憶體使用優化過的資料結構，更有效利用儲存容量。
- 是開箱即用的資料結構，架構簡單有效，沒有複雜的模組或依賴。

### 部署方式

- 使用 [Tair Cloud Vector Database](https://www.alibabacloud.com/help/en/tair/latest/getting-started-overview)。[點這裡](https://www.alibabacloud.com/product/tair)可以快速部署。


## 前置條件

這個練習需要準備幾樣東西：

1. Tair 雲端 server instance。
2. 用來操作 tair 資料庫的 'tair' 函式庫。
3. 一組 [OpenAI API key](https://beta.openai.com/account/api-keys)。



### 安裝套件

這個 notebook 當然需要 `openai` 和 `tair`，還會用到一些其他函式庫。下面的指令一次裝好：


```python
! pip install openai redis tair pandas wget
```

??? note "輸出"

    ```text
    Looking in indexes: http://sg.mirrors.cloud.aliyuncs.com/pypi/simple/
    Requirement already satisfied: openai in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (0.28.0)
    Requirement already satisfied: redis in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (5.0.0)
    Requirement already satisfied: tair in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (1.3.6)
    Requirement already satisfied: pandas in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (2.1.0)
    Requirement already satisfied: wget in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (3.2)
    Requirement already satisfied: requests>=2.20 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from openai) (2.31.0)
    Requirement already satisfied: tqdm in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from openai) (4.66.1)
    Requirement already satisfied: aiohttp in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from openai) (3.8.5)
    Requirement already satisfied: async-timeout>=4.0.2 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from redis) (4.0.3)
    Requirement already satisfied: numpy>=1.22.4 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from pandas) (1.25.2)
    Requirement already satisfied: python-dateutil>=2.8.2 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from pandas) (2.8.2)
    Requirement already satisfied: pytz>=2020.1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from pandas) (2023.3.post1)
    Requirement already satisfied: tzdata>=2022.1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from pandas) (2023.3)
    Requirement already satisfied: six>=1.5 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from python-dateutil>=2.8.2->pandas) (1.16.0)
    Requirement already satisfied: charset-normalizer<4,>=2 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (3.2.0)
    Requirement already satisfied: idna<4,>=2.5 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (3.4)
    Requirement already satisfied: urllib3<3,>=1.21.1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (2.0.4)
    Requirement already satisfied: certifi>=2017.4.17 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from requests>=2.20->openai) (2023.7.22)
    Requirement already satisfied: attrs>=17.3.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (22.1.0)
    Requirement already satisfied: multidict<7.0,>=4.5 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (6.0.4)
    Requirement already satisfied: yarl<2.0,>=1.0 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (1.9.2)
    Requirement already satisfied: frozenlist>=1.1.1 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (1.4.0)
    Requirement already satisfied: aiosignal>=1.1.2 in /root/anaconda3/envs/notebook/lib/python3.10/site-packages (from aiohttp->openai) (1.3.1)
    WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv
    ```

### 準備 OpenAI API key

OpenAI API key 用來把文件和 query 向量化。

沒有 OpenAI API key 的話，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，用 getpass 把它加進來。

```python
import getpass
import openai

openai.api_key = getpass.getpass("Input your OpenAI API key:")
```

??? note "輸出"

    ```text
    Input your OpenAI API key:········
    ```

## 連線到 Tair
先把連線資訊加進環境變數。

用官方 Python 函式庫連到運行中的 Tair server 很簡單。

```python
# The format of url: redis://[[username]:[password]]@localhost:6379/0
TAIR_URL = getpass.getpass("Input your tair url:")
```

??? note "輸出"

    ```text
    Input your tair url:········
    ```

```python
from tair import Tair as TairClient

# connect to tair from url and create a client

url = TAIR_URL
client = TairClient.from_url(url)
```

可以用 ping 測試連線：

```python
client.ping()
```

??? note "輸出"

    ```text
    True
    ```

```python
import wget

embeddings_url = "https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip"

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

??? note "輸出"

    ```text
    100% [......................................................................] 698933052 / 698933052
    ```

    ```text
    'vector_database_wikipedia_articles_embedded (1).zip'
    ```

下載下來的檔案要再解壓縮：

```python
import zipfile
import os
import re
import tempfile

current_directory = os.getcwd()
zip_file_path = os.path.join(current_directory, "vector_database_wikipedia_articles_embedded.zip")
output_directory = os.path.join(current_directory, "../../data")

with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
    zip_ref.extractall(output_directory)


# check the csv file exist
file_name = "vector_database_wikipedia_articles_embedded.csv"
data_directory = os.path.join(current_directory, "../../data")
file_path = os.path.join(data_directory, file_name)


if os.path.exists(file_path):
    print(f"The file {file_name} exists in the data directory.")
else:
    print(f"The file {file_name} does not exist in the data directory.")
```

??? note "輸出"

    ```text
    The file vector_database_wikipedia_articles_embedded.csv exists in the data directory.
    ```

## 建立 Index

Tair 把資料存在 index 裡，每個物件由一個 key 描述。每個 key 包含一個向量和多個 attribute_keys。

我們先建兩個 index，一個放 **title_vector**，一個放 **content_vector**，再把預先算好的 embedding 填進去。

```python
# set index parameters
index = "openai_test"
embedding_dim = 1536
distance_type = "L2"
index_type = "HNSW"
data_type = "FLOAT32"

# Create two indexes, one for title_vector and one for content_vector, skip if already exists
index_names = [index + "_title_vector", index+"_content_vector"]
for index_name in index_names:
    index_connection = client.tvs_get_index(index_name)
    if index_connection is not None:
        print("Index already exists")
    else:
        client.tvs_create_index(name=index_name, dim=embedding_dim, distance_type=distance_type,
                                index_type=index_type, data_type=data_type)
```

??? note "輸出"

    ```text
    Index already exists
    Index already exists
    ```

## 載入資料

這一節載入這次練習之前就準備好的資料，所以你不必花自己的額度重算 Wikipedia 文章的 embedding。

```python
import pandas as pd
from ast import literal_eval
# Path to your local CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'
article_df = pd.read_csv(csv_file_path)

# Read vectors from strings back into a list
article_df['title_vector'] = article_df.title_vector.apply(literal_eval).values
article_df['content_vector'] = article_df.content_vector.apply(literal_eval).values

# add/update data to indexes
for i in range(len(article_df)):
    # add data to index with title_vector
    client.tvs_hset(index=index_names[0], key=article_df.id[i].item(), vector=article_df.title_vector[i], is_binary=False,
                    **{"url": article_df.url[i], "title": article_df.title[i], "text": article_df.text[i]})
    # add data to index with content_vector
    client.tvs_hset(index=index_names[1], key=article_df.id[i].item(), vector=article_df.content_vector[i], is_binary=False,
                    **{"url": article_df.url[i], "title": article_df.title[i], "text": article_df.text[i]})
```

```python
# Check the data count to make sure all the points have been stored
for index_name in index_names:
    stats = client.tvs_get_index(index_name)
    count = int(stats["current_record_count"]) - int(stats["delete_record_count"])
    print(f"Count in {index_name}:{count}")
```

??? note "輸出"

    ```text
    Count in openai_test_title_vector:25000
    Count in openai_test_content_vector:25000
    ```

## 搜尋資料

資料放進 Tair 之後，就能查詢 collection 裡最接近的向量。可以多帶一個 `vector_name` 參數，在 title 和 content 搜尋之間切換。因為預先算好的 embedding 是用 OpenAI 的 `text-embedding-3-small` 模型產生的，搜尋時也必須用同一個模型。


```python
def query_tair(client, query, vector_name="title_vector", top_k=5):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input= query,
        model="text-embedding-3-small",
    )["data"][0]['embedding']
    embedded_query = np.array(embedded_query)

    # search for the top k approximate nearest neighbors of vector in an index
    query_result = client.tvs_knnsearch(index=index+"_"+vector_name, k=top_k, vector=embedded_query)

    return query_result
```

```python
import openai
import numpy as np

query_result = query_tair(client=client, query="modern art in Europe", vector_name="title_vector")
for i in range(len(query_result)):
    title = client.tvs_hmget(index+"_"+"content_vector", query_result[i][0].decode('utf-8'), "title")
    print(f"{i + 1}. {title[0].decode('utf-8')} (Distance: {round(query_result[i][1],3)})")
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Distance: 0.125)
    2. Western Europe (Distance: 0.133)
    3. Renaissance art (Distance: 0.136)
    4. Pop art (Distance: 0.14)
    5. Northern Europe (Distance: 0.145)
    ```

```python
# This time we'll query using content vector
query_result = query_tair(client=client, query="Famous battles in Scottish history", vector_name="content_vector")
for i in range(len(query_result)):
    title = client.tvs_hmget(index+"_"+"content_vector", query_result[i][0].decode('utf-8'), "title")
    print(f"{i + 1}. {title[0].decode('utf-8')} (Distance: {round(query_result[i][1],3)})")
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn (Distance: 0.131)
    2. Wars of Scottish Independence (Distance: 0.139)
    3. 1651 (Distance: 0.147)
    4. First War of Scottish Independence (Distance: 0.15)
    5. Robert I of Scotland (Distance: 0.154)
    ```

## 重點整理
- Tair 的 TairVector 資料結構把向量放在記憶體，提供 HNSW 和 Flat 兩種索引。
- 存和搜用的 embedding 模型要一致，這裡都是 `text-embedding-3-small`。
- 一個 index 對應一種向量欄位，所以 title 和 content 各建一個。
- 用預先算好的 embedding 可以省下重算成本，專心測資料庫流程。

## 練習
1. 換一句自己的 query，分別用 title 和 content 搜尋，比較排名。
2. 改搜尋時回傳的筆數，看結果變化。
3. 在建 index 時換成另一種索引演算法（HNSW 與 Flat），比較搜尋結果和速度。
