---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/neon/neon-postgres-vector-search-pgvector.ipynb
---

# 用 Neon Postgres 做向量相似度搜尋

> 原文：[examples/vector_databases/neon/neon-postgres-vector-search-pgvector.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/neon/neon-postgres-vector-search-pgvector.ipynb)

## 這篇在做什麼
示範把 [Neon Serverless Postgres](https://neon.tech/) 搭配 `pgvector` extension 當成 OpenAI embedding 的向量資料庫。你會建表、載入 25000 筆預先算好的 Wikipedia embedding，再用 SQL 做相似度搜尋。

## 學完你會
- 在 Neon 啟用 `pgvector`，建出有 title 和 content 向量欄位與 index 的表
- 把 CSV 裡的 embedding 載入 Postgres
- 寫一個 `query_neon` 函式，把文字轉成 embedding 並用 SQL 做最近鄰搜尋

## 開跑前
- 一個 Neon Postgres 資料庫與連線字串（`DATABASE_URL`）
- 在資料庫執行 `CREATE EXTENSION vector;`
- OpenAI API key（環境變數 `OPENAI_API_KEY`）

這個 notebook 帶你用 [Neon Serverless Postgres](https://neon.tech/) 當 OpenAI embedding 的向量資料庫，內容包括：

1. 使用 OpenAI API 產生的 embedding。
2. 把 embedding 存到 Neon Serverless Postgres 資料庫。
3. 用 OpenAI API 把文字 query 轉成 embedding。
4. 用 Neon 搭配 `pgvector` extension 做向量相似度搜尋。

## 前置條件

開始前請確認你已經有：

1. 一個 Neon Postgres 資料庫。你可以註冊帳號，幾個簡單步驟就能建好一個有現成 `neondb` 資料庫的 project。步驟看 [Sign up](https://neon.tech/docs/get-started-with-neon/signing-up) 和 [Create your first project](https://neon.tech/docs/get-started-with-neon/setting-up-a-project)。
2. Neon 資料庫的連線字串。可以從 Neon **Dashboard** 的 **Connection Details** widget 複製。看 [Connect from any application](https://neon.tech/docs/connect/connect-from-any-app)。
3. `pgvector` extension。在 Neon 執行 `CREATE EXTENSION vector;` 安裝。步驟看 [Enable the pgvector extension](https://neon.tech/docs/extensions/pgvector#enable-the-pgvector-extension)。
4. 你的 [OpenAI API key](https://platform.openai.com/account/api-keys)。
5. Python 和 `pip`。

### 安裝需要的模組

這個 notebook 需要 `openai`、`psycopg2`、`pandas`、`wget` 和 `python-dotenv`。可以用 `pip` 安裝：


```python
! pip install openai psycopg2 pandas wget python-dotenv
```

### 準備 OpenAI API key

需要 OpenAI API key 來為文件和 query 產生向量。

沒有 OpenAI API key 的話，到 https://platform.openai.com/account/api-keys 取得。

把 OpenAI API key 設成作業系統的環境變數，或在提示時為這個 session 輸入。如果要設環境變數，變數名稱用 `OPENAI_API_KEY`。

怎麼把 OpenAI API key 設成環境變數，可以參考 [Best Practices for API Key Safety](https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety)。

### 測試 OpenAI key

```python
# Test to ensure that your OpenAI API key is defined as an environment variable or provide it when prompted
# If you run this notebook locally, you may have to reload the terminal and the notebook to make the environment available

import os
from getpass import getpass

# Check if OPENAI_API_KEY is set as an environment variable
if os.getenv("OPENAI_API_KEY") is not None:
    print("Your OPENAI_API_KEY is ready")
else:
    # If not, prompt for it
    api_key = getpass("Enter your OPENAI_API_KEY: ")
    if api_key:
        print("Your OPENAI_API_KEY is now available for this session")
        # Optionally, you can set it as an environment variable for the current session
        os.environ["OPENAI_API_KEY"] = api_key
    else:
        print("You did not enter your OPENAI_API_KEY")
```

??? note "輸出"

    ```text
    Your OPENAI_API_KEY is ready
    ```

## 連線到 Neon 資料庫

在下面提供 Neon 資料庫連線字串，或用 `DATABASE_URL` 變數定義在 `.env` 檔裡。怎麼取得 Neon 連線字串，看 [Connect from any application](https://neon.tech/docs/connect/connect-from-any-app)。

```python
import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# The connection string can be provided directly here.
# Replace the next line with Your Neon connection string.
connection_string = "postgres://<user>:<password>@<hostname>/<dbname>"

# If connection_string is not directly provided above, 
# then check if DATABASE_URL is set in the environment or .env.
if not connection_string:
    connection_string = os.environ.get("DATABASE_URL")

    # If neither method provides a connection string, raise an error.
    if not connection_string:
        raise ValueError("Please provide a valid connection string either in the code or in the .env file as DATABASE_URL.")

# Connect using the connection string
connection = psycopg2.connect(connection_string)

# Create a new cursor object
cursor = connection.cursor()
```

測試資料庫連線：

```python
# Execute this query to test the database connection
cursor.execute("SELECT 1;")
result = cursor.fetchone()

# Check the query result
if result == (1,):
    print("Your database connection was successful!")
else:
    print("Your connection failed.")
```

??? note "輸出"

    ```text
    Your database connection was successful!
    ```

這份指南使用 OpenAI Cookbook `examples` 目錄裡預先算好的 Wikipedia 文章 embedding，所以你不必花自己的 OpenAI 額度算 embedding。

匯入預先算好的 embedding zip 檔：

```python
import wget

embeddings_url = "https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip"

# The file is ~700 MB. Importing it will take several minutes.
wget.download(embeddings_url)
```

??? note "輸出"

    ```text
    'vector_database_wikipedia_articles_embedded.zip'
    ```

解壓縮下載的 zip 檔：

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


# Check to see if the csv file was extracted
file_name = "vector_database_wikipedia_articles_embedded.csv"
data_directory = os.path.join(current_directory, "../../data")
file_path = os.path.join(data_directory, file_name)


if os.path.exists(file_path):
    print(f"The csv file {file_name} exists in the data directory.")
else:
    print(f"The csv file {file_name} does not exist in the data directory.")
```

??? note "輸出"

    ```text
    The file vector_database_wikipedia_articles_embedded.csv exists in the data directory.
    ```

## 建表並為向量 embedding 加 index

資料庫裡建出來的向量表叫 **articles**。每個物件有 **title** 和 **content** 向量。

**title** 和 **content** 兩個向量欄位都定義了 index。

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

把預先算好的向量資料從 `.csv` 檔載入 `articles` 表。共有 25000 筆，所以要預期這個操作需要幾分鐘。

```python
import io

# Path to your local CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'

# Define a generator function to process the csv file
def process_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            yield line

# Create a StringIO object to store the modified lines
modified_lines = io.StringIO(''.join(list(process_file(csv_file_path))))

# Create the COPY command for copy_expert
copy_command = '''
COPY public.articles (id, url, title, content, title_vector, content_vector, vector_id)
FROM STDIN WITH (FORMAT CSV, HEADER true, DELIMITER ',');
'''

# Execute the COPY command using copy_expert
cursor.copy_expert(copy_command, modified_lines)

# Commit the changes
connection.commit()
```

檢查筆數，確認資料已載入。應該有 25000 筆。

```python
# Check the size of the data
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

資料存進 Neon 資料庫後，就能查詢最近鄰。

先定義 `query_neon` 函式，向量相似度搜尋時會執行它。這個函式會依使用者的 query 產生 embedding、準備 SQL query，並帶著 embedding 執行。你載入資料庫的預先算好 embedding 是用 OpenAI 的 `text-embedding-3-small` 模型產生，所以做相似度搜尋時也必須用同一個模型產生 embedding。

函式有 `vector_name` 參數，可以選擇依 "title" 或 "content" 搜尋。

```python
def query_neon(query, collection_name, vector_name="title_vector", top_k=20):

    # Create an embedding vector from the user query
    embedded_query = openai.Embedding.create(
        input=query,
        model="text-embedding-3-small",
    )["data"][0]["embedding"]

    # Convert the embedded_query to PostgreSQL compatible format
    embedded_query_pg = "[" + ",".join(map(str, embedded_query)) + "]"

    # Create the SQL query
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

用 `title_vector` embedding 做相似度搜尋：

```python
# Query based on `title_vector` embeddings
import openai

query_results = query_neon("Greek mythology", "Articles")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. Greek mythology (Score: 0.998)
    2. Roman mythology (Score: 0.7)
    3. Greek underworld (Score: 0.637)
    4. Mythology (Score: 0.635)
    5. Classical mythology (Score: 0.629)
    6. Japanese mythology (Score: 0.615)
    7. Norse mythology (Score: 0.569)
    8. Greek language (Score: 0.566)
    9. Zeus (Score: 0.534)
    10. List of mythologies (Score: 0.531)
    11. Jupiter (mythology) (Score: 0.53)
    12. Greek (Score: 0.53)
    13. Gaia (mythology) (Score: 0.526)
    14. Titan (mythology) (Score: 0.522)
    15. Mercury (mythology) (Score: 0.521)
    16. Ancient Greece (Score: 0.52)
    17. Greek alphabet (Score: 0.52)
    18. Venus (mythology) (Score: 0.515)
    19. Pluto (mythology) (Score: 0.515)
    20. Athena (Score: 0.514)
    ```

用 `content_vector` embedding 做相似度搜尋：

```python
# Query based on `content_vector` embeddings
query_results = query_neon("Famous battles in Greek history", "Articles", "content_vector")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. 222 BC (Score: 0.489)
    2. Trojan War (Score: 0.458)
    3. Peloponnesian War (Score: 0.456)
    4. History of the Peloponnesian War (Score: 0.449)
    5. 430 BC (Score: 0.441)
    6. 168 BC (Score: 0.436)
    7. Ancient Greece (Score: 0.429)
    8. Classical Athens (Score: 0.428)
    9. 499 BC (Score: 0.427)
    10. Leonidas I (Score: 0.426)
    11. Battle (Score: 0.421)
    12. Greek War of Independence (Score: 0.421)
    13. Menelaus (Score: 0.419)
    14. Thebes, Greece (Score: 0.417)
    15. Patroclus (Score: 0.417)
    16. 427 BC (Score: 0.416)
    17. 429 BC (Score: 0.413)
    18. August 2 (Score: 0.412)
    19. Ionia (Score: 0.411)
    20. 323 (Score: 0.409)
    ```

## 重點整理
- 已經在用 Postgres 的話，`pgvector` 讓你不用另外架向量資料庫就能做相似度搜尋。
- 向量欄位要建 index，資料量大時搜尋才快。
- 搜尋用的 embedding 模型必須和存入資料時一致。
- 流程都是同一個套路：query 轉 embedding，再丟進資料庫找最近鄰。

## 練習
1. 換一句自己的 query，用 `query_neon` 分別搜 title 和 content。
2. 改函式裡回傳的筆數，看結果變化。
3. 在 SQL 加上 WHERE 條件（例如 title 包含某個字），做一個混合過濾的搜尋。
