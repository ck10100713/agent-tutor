---
translated: true
source: examples/vector_databases/analyticdb/Getting_started_with_AnalyticDB_and_OpenAI.ipynb
---

# 用 AnalyticDB 當 OpenAI embeddings 的向量資料庫

> 原文：[examples/vector_databases/analyticdb/Getting_started_with_AnalyticDB_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/analyticdb/Getting_started_with_AnalyticDB_and_OpenAI.ipynb)



## 這篇在做什麼
一步一步帶你把 AnalyticDB 當成 OpenAI embeddings 的向量資料庫。用預先算好的 Wikipedia 文章 embedding，存進雲端的 AnalyticDB，再用查詢文字做最近鄰搜尋。

## 學完你會
- 用 psycopg2 連上 AnalyticDB，建立存放 title 和 content 向量的 relation 與向量索引
- 載入預先算好的 embedding 資料並寫入資料庫
- 把查詢文字轉成 embedding，並在 title 或 content 向量上搜尋最相近的文章

## 開跑前
需要 OpenAI API key（設成環境變數 `OPENAI_API_KEY`），以及一個 AnalyticDB 雲端實例，連線參數也要設好。

這份 notebook 一步一步帶你把 AnalyticDB 當成 OpenAI embeddings 的向量資料庫。

這份 notebook 呈現的是端到端流程：
1. 使用 OpenAI API 預先算好的 embedding。
2. 把 embedding 存進 AnalyticDB 的雲端實例。
3. 用 OpenAI API 把原始文字問題轉成 embedding。
4. 用 AnalyticDB 在建好的 collection 裡做最近鄰搜尋。

### 什麼是 AnalyticDB

[AnalyticDB](https://www.alibabacloud.com/help/en/analyticdb-for-postgresql/latest/product-introduction-overview) 是高效能的分散式向量資料庫。它完全相容 PostgreSQL 語法，用起來很輕鬆。AnalyticDB 是阿里雲託管的雲原生資料庫，有效能強的向量運算引擎。開箱即用，可以擴展到處理數十億個資料向量，功能豐富，包括索引演算法、結構化與非結構化資料功能、即時更新、距離度量、scalar filtering、time travel 搜尋等。同時具備完整的 OLAP 資料庫功能，並提供 SLA 承諾，可用於 production。

### 部署選項

- 使用 [AnalyticDB Cloud Vector Database](https://www.alibabacloud.com/help/zh/analyticdb-for-postgresql/latest/overview-2)。[點這裡](https://www.alibabacloud.com/product/hybriddb-postgresql)可以快速部署。


## 前置條件

要做這個練習，需要先準備幾樣東西：

1. AnalyticDB 雲端 server 實例。
2. 'psycopg2' 函式庫，用來跟向量資料庫互動。其他 postgresql client 函式庫也可以。
3. 一組 [OpenAI API key](https://beta.openai.com/account/api-keys)。



可以用簡單的 curl 指令確認 server 有沒有成功啟動：


### 安裝需求套件

這份 notebook 需要 `openai` 和 `psycopg2` 套件，另外還會用到一些其他函式庫。下面的指令會全部裝好：


```python
! pip install openai psycopg2 pandas wget
```

### 準備 OpenAI API key

OpenAI API key 用來把文件和查詢向量化。

如果還沒有 OpenAI API key，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，請把它加到環境變數 `OPENAI_API_KEY`。

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

if os.getenv("OPENAI_API_KEY") is not None:
    print("OPENAI_API_KEY is ready")
else:
    print("OPENAI_API_KEY environment variable not found")
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is ready
    ```

## 連接 AnalyticDB
先把連線參數加到環境變數，或者直接修改下面 "psycopg2.connect" 的參數。

用官方 Python 函式庫連接執行中的 AnalyticDB server 很簡單：

```python
import os
import psycopg2

# Note. alternatively you can set a temporary env variable like this:
# os.environ["PGHOST"] = "your_host"
# os.environ["PGPORT"] "5432"),
# os.environ["PGDATABASE"] "postgres"),
# os.environ["PGUSER"] "user"),
# os.environ["PGPASSWORD"] "password"),

connection = psycopg2.connect(
    host=os.environ.get("PGHOST", "localhost"),
    port=os.environ.get("PGPORT", "5432"),
    database=os.environ.get("PGDATABASE", "postgres"),
    user=os.environ.get("PGUSER", "user"),
    password=os.environ.get("PGPASSWORD", "password")
)

# Create a new cursor object
cursor = connection.cursor()
```

可以執行任何可用的方法來測試連線：

```python

# Execute a simple query to test the connection
cursor.execute("SELECT 1;")
result = cursor.fetchone()

# Check the query result
if result == (1,):
    print("Connection successful!")
else:
    print("Connection failed.")
```

??? note "輸出"

    ```text
    Connection successful!
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
    'vector_database_wikipedia_articles_embedded.zip'
    ```

下載的檔案接著要解壓縮：

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

## 索引資料

AnalyticDB 把資料存在 __relation__ 裡，每個物件至少由一個向量描述。我們的 relation 叫做 **articles**，每個物件同時由 **title** 和 **content** 向量描述。\

我們先建立 relation，並對 **title** 和 **content** 都建立向量索引，再把預先算好的 embedding 填進去。

```python
create_table_sql = '''
CREATE TABLE IF NOT EXISTS public.articles (
    id INTEGER NOT NULL,
    url TEXT,
    title TEXT,
    content TEXT,
    title_vector REAL[],
    content_vector REAL[],
    vector_id INTEGER
);

ALTER TABLE public.articles ADD PRIMARY KEY (id);
'''

# SQL statement for creating indexes
create_indexes_sql = '''
CREATE INDEX ON public.articles USING ann (content_vector) WITH (distancemeasure = l2, dim = '1536', pq_segments = '64', hnsw_m = '100', pq_centers = '2048');

CREATE INDEX ON public.articles USING ann (title_vector) WITH (distancemeasure = l2, dim = '1536', pq_segments = '64', hnsw_m = '100', pq_centers = '2048');
'''

# Execute the SQL statements
cursor.execute(create_table_sql)
cursor.execute(create_indexes_sql)

# Commit the changes
connection.commit()
```

## 載入資料

這一段要載入在這次練習之前就準備好的資料，所以你不用花自己的額度重算 Wikipedia 文章的 embedding。

```python
import io

# Path to your local CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'

# Define a generator function to process the file line by line
def process_file(file_path):
    with open(file_path, 'r') as file:
        for line in file:
            # Replace '[' with '{' and ']' with '}'
            modified_line = line.replace('[', '{').replace(']', '}')
            yield modified_line

# Create a StringIO object to store the modified lines
modified_lines = io.StringIO(''.join(list(process_file(csv_file_path))))

# Create the COPY command for the copy_expert method
copy_command = '''
COPY public.articles (id, url, title, content, title_vector, content_vector, vector_id)
FROM STDIN WITH (FORMAT CSV, HEADER true, DELIMITER ',');
'''

# Execute the COPY command using the copy_expert method
cursor.copy_expert(copy_command, modified_lines)

# Commit the changes
connection.commit()
```

```python
# Check the collection size to make sure all the points have been stored
count_sql = """select count(*) from public.articles;"""
cursor.execute(count_sql)
result = cursor.fetchone()
print(f"Count:{result[0]}")
```

??? note "輸出"

    ```text
    Count:25000
    ```

## 搜尋資料

資料放進資料庫之後，就可以開始對 collection 查詢最接近的向量。我們可以提供額外的參數 `vector_name`，在以 title 搜尋和以 content 搜尋之間切換。因為預先算好的 embedding 是用 OpenAI 的 `text-embedding-3-small` 模型建立的，搜尋時也必須用同一個模型。


```python
def query_analyticdb(query, collection_name, vector_name="title_vector", top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model="text-embedding-3-small",
    )["data"][0]["embedding"]

    # Convert the embedded_query to PostgreSQL compatible format
    embedded_query_pg = "{" + ",".join(map(str, embedded_query)) + "}"

    # Create SQL query
    query_sql = f"""
    SELECT id, url, title, l2_distance({vector_name},'{embedded_query_pg}'::real[]) AS similarity
    FROM {collection_name}
    ORDER BY {vector_name} <-> '{embedded_query_pg}'::real[]
    LIMIT {top_k};
    """
    # Execute the query
    cursor.execute(query_sql)
    results = cursor.fetchall()

    return results
```

```python
import openai

query_results = query_analyticdb("modern art in Europe", "Articles")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Score: 0.75)
    2. Western Europe (Score: 0.735)
    3. Renaissance art (Score: 0.728)
    4. Pop art (Score: 0.721)
    5. Northern Europe (Score: 0.71)
    6. Hellenistic art (Score: 0.706)
    7. Modernist literature (Score: 0.694)
    8. Art film (Score: 0.687)
    9. Central Europe (Score: 0.685)
    10. European (Score: 0.683)
    11. Art (Score: 0.683)
    12. Byzantine art (Score: 0.682)
    13. Postmodernism (Score: 0.68)
    14. Eastern Europe (Score: 0.679)
    15. Europe (Score: 0.678)
    16. Cubism (Score: 0.678)
    17. Impressionism (Score: 0.677)
    18. Bauhaus (Score: 0.676)
    19. Surrealism (Score: 0.674)
    20. Expressionism (Score: 0.674)
    ```

```python
# This time we'll query using content vector
query_results = query_analyticdb("Famous battles in Scottish history", "Articles", "content_vector")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn (Score: 0.739)
    2. Wars of Scottish Independence (Score: 0.723)
    3. 1651 (Score: 0.705)
    4. First War of Scottish Independence (Score: 0.699)
    5. Robert I of Scotland (Score: 0.692)
    6. 841 (Score: 0.688)
    7. 1716 (Score: 0.688)
    8. 1314 (Score: 0.674)
    9. 1263 (Score: 0.673)
    10. William Wallace (Score: 0.671)
    11. Stirling (Score: 0.663)
    12. 1306 (Score: 0.662)
    13. 1746 (Score: 0.661)
    14. 1040s (Score: 0.656)
    15. 1106 (Score: 0.654)
    16. 1304 (Score: 0.653)
    17. David II of Scotland (Score: 0.65)
    18. Braveheart (Score: 0.649)
    19. 1124 (Score: 0.648)
    20. July 27 (Score: 0.646)
    ```

## 重點整理
- AnalyticDB 相容 PostgreSQL 語法，所以可以用一般的 PostgreSQL client（如 psycopg2）操作。
- 每個物件可以有多個向量欄位（這裡是 title 和 content），各自建索引，搜尋時選要比對哪一個。
- 查詢時的 embedding 模型要跟建資料時一致，這裡都是 `text-embedding-3-small`。
- 用預先算好的 embedding 可以省掉重算的成本。

## 練習
1. 換幾個不同的查詢文字，比較 title 搜尋和 content 搜尋的結果差在哪。
2. 調整搜尋回傳的筆數，看結果的相關性怎麼變化。
3. 把查詢改用別的 embedding 模型，觀察搜尋結果為什麼會變得不準。
