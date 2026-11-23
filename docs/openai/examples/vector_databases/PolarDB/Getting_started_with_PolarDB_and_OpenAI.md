---
translated: true
source: examples/vector_databases/PolarDB/Getting_started_with_PolarDB_and_OpenAI.ipynb
---

# 用 PolarDB-PG 當 OpenAI embedding 的向量資料庫

> 原文：[examples/vector_databases/PolarDB/Getting_started_with_PolarDB_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/PolarDB/Getting_started_with_PolarDB_and_OpenAI.ipynb)

## 這篇在做什麼
一步步示範把 PolarDB-PG（阿里雲、相容 PostgreSQL 的雲原生資料庫）當向量資料庫，存 OpenAI embedding 並做最近鄰搜尋。資料用事先算好的 Wikipedia embedding。

## 學完你會
- 用 `psycopg2` 連上 PolarDB-PG
- 建一個有 title 和 content 向量欄位與向量 index 的 relation
- 把 query 轉成 embedding，在 PolarDB-PG 裡做最近鄰搜尋

## 開跑前
- 一個 PolarDB-PG 雲端 instance（阿里雲）
- OpenAI API key，設成環境變數 `OPENAI_API_KEY`

這個 notebook 帶你一步步用 PolarDB-PG 當 OpenAI embedding 的向量資料庫。

完整流程是：
1. 使用 OpenAI API 事先算好的 embedding。
2. 把 embedding 存到雲端的 PolarDB-PG instance。
3. 用 OpenAI API 把文字 query 轉成 embedding。
4. 用 PolarDB-PG 在建好的 collection 裡做最近鄰搜尋。

### 什麼是 PolarDB-PG

[PolarDB-PG](https://www.alibabacloud.com/help/en/polardb/latest/what-is-polardb-2) 是採用讀寫分離架構的高效能向量資料庫。它是阿里雲管理的雲原生資料庫，100% 相容 PostgreSQL，也高度相容 Oracle 語法。它支援處理海量向量資料的儲存與查詢，並透過優化底層執行演算法大幅提升向量運算效率，為使用者提供快速、有彈性、高效能、海量儲存且安全可靠的向量資料庫服務。此外，PolarDB-PG 也支援多維度、多模態的時空資訊引擎和地理資訊引擎。同時 PolarDB-PG 具備完整的 OLAP 功能和服務等級協議，已獲得許多使用者的認可與使用。







### 部署方式

- 使用 [PolarDB-PG Cloud Vector Database](https://www.alibabacloud.com/product/polardb-for-postgresql)。[點這裡](https://www.alibabacloud.com/product/polardb-for-postgresql?spm=a3c0i.147400.6791778070.243.9f204881g5cjpP)可以快速部署。

## 前置條件

這個練習需要準備幾樣東西：

1. PolarDB-PG 雲端 server instance。
2. 用來操作向量資料庫的 'psycopg2' 函式庫。其他 postgresql client 函式庫也可以。
3. 一組 [OpenAI API key](https://beta.openai.com/account/api-keys)。

我們可以用簡單的 curl 指令確認 server 是否啟動成功：

### 安裝套件

這個 notebook 當然需要 `openai` 和 `psycopg2`，還會用到一些其他函式庫。下面的指令一次裝好：


```python
! pip install openai psycopg2 pandas wget
```

準備 OpenAI API key
OpenAI API key 用來把文件和 query 向量化。

沒有 OpenAI API key 的話，可以到 https://beta.openai.com/account/api-keys 取得。

拿到 key 之後，請把它加到環境變數 OPENAI_API_KEY。

如果對用環境變數設 API key 有疑問，請參考 [Best Practices for API Key Safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety)。

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.

if os.getenv("OPENAI_API_KEY") is not None:
    print("OPENAI_API_KEY is ready")
else:
    print("OPENAI_API_KEY environment variable not found")
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is ready
    ```

## 連線到 PolarDB
先把連線資訊加進環境變數，或直接修改下面 "psycopg2.connect" 的參數。

用官方 Python 函式庫連到運行中的 PolarDB server 很簡單：

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
    'vector_database_wikipedia_articles_embedded.zip'
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

## 資料建索引

PolarDB 把資料存在 __relation__ 裡，每個物件至少由一個向量描述。我們的 relation 叫 **articles**，每個物件同時有 **title** 和 **content** 向量。

我們先建一個 relation，並在 **title** 和 **content** 上都建向量 index，再把預先算好的 embedding 填進去。

```python
create_table_sql = '''
CREATE TABLE IF NOT EXISTS public.articles (
    id INTEGER NOT NULL,
    url TEXT,
    title TEXT,
    content TEXT,
    title_vector vector(1536),
    content_vector vector(1536),
    vector_id INTEGER
);

ALTER TABLE public.articles ADD PRIMARY KEY (id);
'''

# SQL statement for creating indexes
create_indexes_sql = '''
CREATE INDEX ON public.articles USING ivfflat (content_vector) WITH (lists = 1000);

CREATE INDEX ON public.articles USING ivfflat (title_vector) WITH (lists = 1000);
'''

# Execute the SQL statements
cursor.execute(create_table_sql)
cursor.execute(create_indexes_sql)

# Commit the changes
connection.commit()
```

## 載入資料

這一節載入這次練習之前就準備好的資料，所以你不必花自己的額度重算 Wikipedia 文章的 embedding。

```python
import io

# Path to your local CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'

# Define a generator function to process the file line by line
def process_file(file_path):
    with open(file_path, 'r') as file:
        for line in file:
            yield line

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

資料放進 PolarDB 之後，就能查詢 collection 裡最接近的向量。可以多帶一個 `vector_name` 參數，在 title 和 content 搜尋之間切換。因為預先算好的 embedding 是用 OpenAI 的 `text-embedding-3-small` 模型產生的，搜尋時也必須用同一個模型。

```python
def query_polardb(query, collection_name, vector_name="title_vector", top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model="text-embedding-3-small",
    )["data"][0]["embedding"]

    # Convert the embedded_query to PostgreSQL compatible format
    embedded_query_pg = "[" + ",".join(map(str, embedded_query)) + "]"

    # Create SQL query
    query_sql = f"""
    SELECT id, url, title, l2_distance({vector_name},'{embedded_query_pg}'::VECTOR(1536)) AS similarity
    FROM {collection_name}
    ORDER BY {vector_name} <-> '{embedded_query_pg}'::VECTOR(1536)
    LIMIT {top_k};
    """
    # Execute the query
    cursor.execute(query_sql)
    results = cursor.fetchall()

    return results
```

```python
import openai

query_results = query_polardb("modern art in Europe", "Articles")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Score: 0.5)
    2. Western Europe (Score: 0.485)
    3. Renaissance art (Score: 0.479)
    4. Pop art (Score: 0.472)
    5. Northern Europe (Score: 0.461)
    6. Hellenistic art (Score: 0.457)
    7. Modernist literature (Score: 0.447)
    8. Art film (Score: 0.44)
    9. Central Europe (Score: 0.439)
    10. European (Score: 0.437)
    11. Art (Score: 0.437)
    12. Byzantine art (Score: 0.436)
    13. Postmodernism (Score: 0.434)
    14. Eastern Europe (Score: 0.433)
    15. Europe (Score: 0.433)
    16. Cubism (Score: 0.432)
    17. Impressionism (Score: 0.432)
    18. Bauhaus (Score: 0.431)
    19. Surrealism (Score: 0.429)
    20. Expressionism (Score: 0.429)
    ```

```python
# This time we'll query using content vector
query_results = query_polardb("Famous battles in Scottish history", "Articles", "content_vector")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn (Score: 0.489)
    2. Wars of Scottish Independence (Score: 0.474)
    3. 1651 (Score: 0.457)
    4. First War of Scottish Independence (Score: 0.452)
    5. Robert I of Scotland (Score: 0.445)
    6. 841 (Score: 0.441)
    7. 1716 (Score: 0.441)
    8. 1314 (Score: 0.429)
    9. 1263 (Score: 0.428)
    10. William Wallace (Score: 0.426)
    11. Stirling (Score: 0.419)
    12. 1306 (Score: 0.419)
    13. 1746 (Score: 0.418)
    14. 1040s (Score: 0.414)
    15. 1106 (Score: 0.412)
    16. 1304 (Score: 0.411)
    17. David II of Scotland (Score: 0.408)
    18. Braveheart (Score: 0.407)
    19. 1124 (Score: 0.406)
    20. July 27 (Score: 0.405)
    ```

## 重點整理
- PolarDB-PG 100% 相容 PostgreSQL，所以用 `psycopg2` 這類標準 client 就能操作。
- 向量放在 relation 的欄位裡，並建向量 index 加速搜尋。
- 存和搜的 embedding 模型要一致，這裡是 `text-embedding-3-small`。
- 搜尋流程是 query 轉 embedding，再丟進資料庫找最近鄰。

## 練習
1. 換一句自己的 query，分別用 title 和 content 搜尋。
2. 改搜尋函式回傳的筆數，觀察結果變化。
3. 在搜尋 SQL 加上 WHERE 條件過濾，再做一次向量搜尋。
