---
translated: true
source: examples/vector_databases/hologres/Getting_started_with_Hologres_and_OpenAI.ipynb
---

# 用 Hologres 當 OpenAI embeddings 的 vector database

> 原文：[examples/vector_databases/hologres/Getting_started_with_Hologres_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/hologres/Getting_started_with_Hologres_and_OpenAI.ipynb)



## 這篇在做什麼
示範把預先算好的 Wikipedia 文章 embeddings 存進阿里雲的 Hologres，建 Proxima 向量索引，再用 OpenAI 把文字 query 轉成 embedding 做最近鄰搜尋。

## 學完你會
- 用 `psycopg2` 連上 Hologres，建立含 title 和 content 向量的資料表與 Proxima 索引。
- 用 COPY 把預算好的 embeddings 匯入，並等索引建完。
- 把 query 轉成 embedding，用 `text-embedding-3-small` 對 title 或 content 向量做相似搜尋。

## 開跑前
- 需要一個 Hologres 雲端實例（阿里雲）。
- 需要 OpenAI API key，設成環境變數 `OPENAI_API_KEY`。
- 需要安裝 `openai` 和 `psycopg2-binary`，匯入資料可能要 5 到 10 分鐘。


這份 notebook 一步步帶你用 Hologres 當 OpenAI embeddings 的 vector database。

這份 notebook 呈現一個完整流程：
1. 使用 OpenAI API 預先算好的 embeddings。
2. 把 embeddings 存進 Hologres 的雲端實例。
3. 用 OpenAI API 把原始文字 query 轉成 embedding。
4. 用 Hologres 在建好的 collection 裡做最近鄰搜尋。
5. 在 prompt engineering 中，把搜尋結果當作 context 提供給大型語言模型

### 什麼是 Hologres

[Hologres](https://www.alibabacloud.com/help/en/hologres/latest/what-is-hologres) 是阿里雲開發的統一即時資料倉儲服務。你可以用 Hologres 即時寫入、更新、處理和分析大量資料。Hologres 支援標準 SQL 語法，相容 PostgreSQL，並支援大部分 PostgreSQL 函式。Hologres 支援線上分析處理（OLAP）和最高到 PB 級資料的 ad hoc 分析，並提供高併發、低延遲的線上資料服務。Hologres 支援多工作負載的細粒度隔離和企業級安全能力。Hologres 與 MaxCompute、Realtime Compute for Apache Flink 和 DataWorks 深度整合，為企業提供全端的線上與離線資料倉儲解決方案。

Hologres 透過採用 [Proxima](https://www.alibabacloud.com/help/en/hologres/latest/vector-processing) 來提供 vector database 功能。

Proxima 是阿里巴巴達摩院開發的高效能軟體函式庫，讓你搜尋向量的最近鄰。Proxima 比類似的開源軟體，像是 Facebook AI Similarity Search (Faiss)，有更高的穩定性和效能。Proxima 提供業界領先效能與效果的基礎模組，可以用來搜尋相似的圖片、影片或人臉。Hologres 與 Proxima 深度整合，提供高效能的向量搜尋服務。

### 部署選項

- [點這裡](https://www.alibabacloud.com/product/hologres)快速部署 [Hologres 資料倉儲](https://www.alibabacloud.com/help/en/hologres/latest/getting-started)。


## 前置需求

為了這個練習，我們需要準備幾樣東西：

1. Hologres 雲端伺服器實例。
2. 用來和 vector database 互動的 'psycopg2-binary' 函式庫。其他 postgresql client 函式庫也可以。
3. 一把 [OpenAI API key](https://beta.openai.com/account/api-keys)。



我們可以跑一個簡單的 curl 指令來驗證伺服器是否成功啟動：


### 安裝需求套件

這份 notebook 當然需要 `openai` 和 `psycopg2-binary` 套件，另外還會用到一些其他函式庫。下面的指令會全部裝好：


```python
! pip install openai psycopg2-binary pandas wget
```

### 準備你的 OpenAI API key

OpenAI API key 用來把文件和 query 向量化。

如果你沒有 OpenAI API key，可以從 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

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

## 連線到 Hologres
先把它加到環境變數，或者你也可以直接改下面 "psycopg2.connect" 的參數。

用官方的 Python 函式庫連到執行中的 Hologres 伺服器很簡單：

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
connection.set_session(autocommit=True)

# Create a new cursor object
cursor = connection.cursor()
```

我們可以跑任何可用的方法來測試連線：

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

## 載入資料

這一節我們會載入這次之前就準備好的資料，所以你不用花自己的額度重新計算 Wikipedia 文章的 embeddings。

```python
!unzip -n vector_database_wikipedia_articles_embedded.zip
!ls -lh vector_database_wikipedia_articles_embedded.csv
```

??? note "輸出"

    ```text
    Archive:  vector_database_wikipedia_articles_embedded.zip
    -rw-r--r--@ 1 geng  staff   1.7G Jan 31 01:19 vector_database_wikipedia_articles_embedded.csv
    ```

看一下資料。

```python
import pandas, json
data = pandas.read_csv('../../data/vector_database_wikipedia_articles_embedded.csv')
data
```

??? note "輸出"

    ```text
              id                                                url   
    0          1            https://simple.wikipedia.org/wiki/April  \
    1          2           https://simple.wikipedia.org/wiki/August   
    2          6              https://simple.wikipedia.org/wiki/Art   
    3          8                https://simple.wikipedia.org/wiki/A   
    4          9              https://simple.wikipedia.org/wiki/Air   
    ...      ...                                                ...   
    24995  98295           https://simple.wikipedia.org/wiki/Geneva   
    24996  98316      https://simple.wikipedia.org/wiki/Concubinage   
    24997  98318  https://simple.wikipedia.org/wiki/Mistress%20%...   
    24998  98326  https://simple.wikipedia.org/wiki/Eastern%20Front   
    24999  98327  https://simple.wikipedia.org/wiki/Italian%20Ca...   

                      title                                               text   
    0                 April  April is the fourth month of the year in the J...  \
    1                August  August (Aug.) is the eighth month of the year ...   
    2                   Art  Art is a creative activity that expresses imag...   
    3                     A  A or a is the first letter of the English alph...   
    4                   Air  Air refers to the Earth's atmosphere. Air is a...   
    ...                 ...                                                ...   
    24995            Geneva  Geneva (,  ,  ,  , ) is the second biggest cit...   
    24996       Concubinage  Concubinage is the state of a woman in a relat...   
    24997  Mistress (lover)  A mistress is a man's long term female sexual ...   
    24998     Eastern Front  Eastern Front can be one of the following:\n\n...   
    24999  Italian Campaign  Italian Campaign can mean the following:\n\nTh...   

                                                title_vector   
    0      [0.001009464613161981, -0.020700545981526375, ...  \
    1      [0.0009286514250561595, 0.000820168002974242, ...   
    2      [0.003393713850528002, 0.0061537534929811954, ...   
    3      [0.0153952119871974, -0.013759135268628597, 0....   
    4      [0.02224554680287838, -0.02044147066771984, -0...   
    ...                                                  ...   
    24995  [-0.015773078426718712, 0.01737344264984131, 0...   
    24996  [-0.00519518880173564, 0.005898841191083193, 0...   
    24997  [-0.023164259269833565, -0.02052430994808674, ...   
    24998  [-0.00681863259524107, 0.002171179046854377, 8...   
    24999  [-0.014151256531476974, -0.008553029969334602,...   

                                              content_vector  vector_id  
    ... (省略 13 行)
    ```

```python
title_vector_length = len(json.loads(data['title_vector'].iloc[0]))
content_vector_length = len(json.loads(data['content_vector'].iloc[0]))

print(title_vector_length, content_vector_length)
```

??? note "輸出"

    ```text
    1536 1536
    ```

### 建立資料表和 proxima 向量索引

Hologres 把資料存在 __tables__ 裡，每個物件至少用一個向量描述。我們的資料表叫 **articles**，每個物件由 **title** 和 **content** 向量一起描述。

我們先建立資料表，並在 **title** 和 **content** 上都建 proxima 索引，然後填入預先算好的 embeddings。

```python
cursor.execute('CREATE EXTENSION IF NOT EXISTS proxima;')
create_proxima_table_sql = '''
BEGIN;
DROP TABLE IF EXISTS articles;
CREATE TABLE articles (
    id INT PRIMARY KEY NOT NULL,
    url TEXT,
    title TEXT,
    content TEXT,
    title_vector float4[] check(
        array_ndims(title_vector) = 1 and 
        array_length(title_vector, 1) = 1536
    ), -- define the vectors
    content_vector float4[] check(
        array_ndims(content_vector) = 1 and 
        array_length(content_vector, 1) = 1536
    ),
    vector_id INT
);

-- Create indexes for the vector fields.
call set_table_property(
    'articles',
    'proxima_vectors', 
    '{
        "title_vector":{"algorithm":"Graph","distance_method":"Euclidean","builder_params":{"min_flush_proxima_row_count" : 10}},
        "content_vector":{"algorithm":"Graph","distance_method":"Euclidean","builder_params":{"min_flush_proxima_row_count" : 10}}
    }'
);  

COMMIT;
'''

# Execute the SQL statements (will autocommit)
cursor.execute(create_proxima_table_sql)
```

### 上傳資料

現在用 [COPY 語句](https://www.alibabacloud.com/help/en/hologres/latest/use-the-copy-statement-to-import-or-export-data)把資料上傳到 Hologres 雲端實例。依網路頻寬，這可能要 5 到 10 分鐘。

```python
import io

# Path to the unzipped CSV file
csv_file_path = '../../data/vector_database_wikipedia_articles_embedded.csv'

# In SQL, arrays are surrounded by {}, rather than []
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
```

proxima 索引會在背景建立。這段期間可以搜尋，但沒有向量索引的話 query 會很慢。用這個指令等索引建完。

```python
cursor.execute('vacuum articles;')
```

```python
# Check the collection size to make sure all the points have been stored
count_sql = "select count(*) from articles;"
cursor.execute(count_sql)
result = cursor.fetchone()
print(f"Count:{result[0]}")
```

??? note "輸出"

    ```text
    Count:25000
    ```

## 搜尋資料

資料上傳完之後，我們就開始在 collection 裡查詢最接近的向量。可以多給一個參數 `vector_name`，在 title 和 content 搜尋之間切換。因為預先算好的 embeddings 是用 `text-embedding-3-small` 這個 OpenAI 模型建立的，搜尋時也必須用它。


```python
import openai
def query_knn(query, table_name, vector_name="title_vector", top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model="text-embedding-3-small",
    )["data"][0]["embedding"]

    # Convert the embedded_query to PostgreSQL compatible format
    embedded_query_pg = "{" + ",".join(map(str, embedded_query)) + "}"

    # Create SQL query
    query_sql = f"""
    SELECT id, url, title, pm_approx_euclidean_distance({vector_name},'{embedded_query_pg}'::float4[]) AS distance
    FROM {table_name}
    ORDER BY distance
    LIMIT {top_k};
    """
    # Execute the query
    cursor.execute(query_sql)
    results = cursor.fetchall()

    return results
```

```python
query_results = query_knn("modern art in Europe", "Articles")
for i, result in enumerate(query_results):
    print(f"{i + 1}. {result[2]} (Score: {round(1 - result[3], 3)})")
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Score: 0.501)
    2. Western Europe (Score: 0.485)
    3. Renaissance art (Score: 0.479)
    4. Pop art (Score: 0.472)
    5. Northern Europe (Score: 0.461)
    6. Hellenistic art (Score: 0.458)
    7. Modernist literature (Score: 0.447)
    8. Art film (Score: 0.44)
    9. Central Europe (Score: 0.439)
    10. Art (Score: 0.437)
    11. European (Score: 0.437)
    12. Byzantine art (Score: 0.436)
    13. Postmodernism (Score: 0.435)
    14. Eastern Europe (Score: 0.433)
    15. Cubism (Score: 0.433)
    16. Europe (Score: 0.432)
    17. Impressionism (Score: 0.432)
    18. Bauhaus (Score: 0.431)
    19. Surrealism (Score: 0.429)
    20. Expressionism (Score: 0.429)
    ```

```python
# This time we'll query using content vector
query_results = query_knn("Famous battles in Scottish history", "Articles", "content_vector")
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
- Hologres 相容 PostgreSQL，所以用一般 postgres client 就能操作，向量搜尋靠 Proxima 索引。
- 建 embeddings 和查詢時要用同一個 embedding 模型，這裡是 `text-embedding-3-small`。
- 每篇文章有 title 和 content 兩組向量，可以選擇對哪一組搜尋。
- 索引在背景建，沒建完前也能查但會慢。
- 流程是預先算好 embeddings、匯入、建索引、query 轉向量、最近鄰搜尋，其他 vector database 也一樣。

## 練習
1. 改 `vector_name` 參數，比較用 title 和 content 搜同一個 query 的結果有何不同。
2. 換一個自己的 query 字串，並把回傳筆數改成 10。
3. 把搜尋結果的內容組成 prompt，傳給 chat model 回答問題，做出簡單的 RAG。
