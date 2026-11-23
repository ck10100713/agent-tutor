---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/rag-quickstart/gcp/Getting_started_with_bigquery_vector_search_and_openai.ipynb
---
# 用 GCP Functions 把 BigQuery 向量搜尋接到 ChatGPT 的 GPT Actions

> 原文：[examples/chatgpt/rag-quickstart/gcp/Getting_started_with_bigquery_vector_search_and_openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/rag-quickstart/gcp/Getting_started_with_bigquery_vector_search_and_openai.ipynb)



## 這篇在做什麼

用 Google Cloud BigQuery 當向量資料庫，存 OpenAI 產生的 embedding，再包一個 Google Cloud Function 當 API，最後接到 ChatGPT 的 Custom GPT。整套 RAG 基礎設施都留在 GCP 裡，只對外開一個 endpoint 給 ChatGPT 之類的平台用。

## 學完你會

- 把文件切 chunk、產生 embedding、用 gpt-4o 補 metadata，存成 CSV
- 在 BigQuery 建表，上傳向量，跑純向量搜尋和帶 metadata 過濾的搜尋
- 用 gcloud 部署 Cloud Function，並產生 OpenAPI spec 讓 Custom GPT 呼叫

## 開跑前

- 一個 GCP 專案，帳號要有建 BigQuery dataset 和 Cloud Function 的權限
- 裝好並登入 [GCP CLI](https://cloud.google.com/sdk/docs/downloads-interactive)
- OpenAI API key
- ChatGPT Plus、Teams 或 Enterprise 訂閱

## 整體架構

下面是這個方案的架構圖，後面會一步一步走過：

![bigquery-rag-architecture.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/bigquery_rag_architecture.png)

## 目錄

1. **[環境設定](#set-up-environment)** 安裝並匯入需要的套件，設定 GCP。包含：
    - [安裝並匯入套件](#install-and-import-required-libraries)
    - [設定 GCP 專案](#configure-gcp-project)
    - [設定 OpenAI](#configure-openai-settings)


2. **[準備資料](#prepare-data)** 把文件做 embedding，順便抓額外的 metadata。範例資料用的是一小部分 OpenAI 文件。

3. **[建立有向量搜尋的 BigQuery 表](#create-bigquery-table-with-vector-search)**  
建 BigQuery 表並上傳準備好的資料。包含：

    - [建立 Dataset](#create-bigquery-dataset)：在 BigQuery 建 dataset。
    - [建表並上傳資料](#creating-table-and-upload-data)：在 BigQuery 建表。

4. **[建立 GCP Function](#create-gcp-function)** 用 gcloud CLI 加上前面算好的環境變數

5. **[接進 ChatGPT 的 Custom GPT](#input-in-a-custom-gpt-in-chatgpt)** 對 BigQuery 裡的 embedding 資料做搜尋：

    - [向量搜尋](#test-search)：跑向量搜尋查詢。
    - [Metadata 過濾搜尋](#perform-search-with-metadata-filtering)：加上 metadata 過濾。

# 環境設定

## 安裝並匯入套件
下面的套件可以分成 Python 標準函式庫、第三方套件和 GCP 相關套件。

```python
! pip install -q google-auth
! pip install -q openai
! pip install -q pandas
! pip install -q google-cloud-functions
! pip install -q python-dotenv
! pip install -q pyperclip
! pip install -q PyPDF2
! pip install -q tiktoken
! pip install -q google-cloud-bigquery
! pip install -q pyyaml
```

```python
# Standard Libraries
import json  
import os
import csv
import shutil
from itertools import islice
import concurrent.futures
import yaml

# Third-Party Libraries
import pandas as pd
import numpy as np
from PyPDF2 import PdfReader
import tiktoken
from dotenv import load_dotenv
import pyperclip

# OpenAI Libraries
from openai import OpenAI

# Google Cloud Identity and Credentials
from google.auth import default
from google.cloud import bigquery
from google.cloud import functions_v1
```

## 設定 GCP 專案

如果還沒設定過，這裡會安裝 GCP CLI、登入 GCP 並設定預設專案。

```python
# Add gcloud to PATH
os.environ['PATH'] += os.pathsep + os.path.expanduser('~/google-cloud-sdk/bin')

# Verify gcloud is in PATH
! gcloud --version
```

```python
! gcloud auth application-default login
```

```python
project_id = "<insert_project_id>"  # Replace with your actual project ID
! gcloud config set project {project_id}
```

```python
! gcloud services enable cloudfunctions.googleapis.com
! gcloud services enable cloudbuild.googleapis.com
! gcloud services enable bigquery.googleapis.com
```

## 設定 OpenAI

這段設定 OpenAI 的認證，開始前先準備好你的 OpenAI API key。

```python
openai_api_key = os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as an env var>") # Saving this as a variable to reference in function app in later step
openai_client = OpenAI(api_key=openai_api_key)
embeddings_model = "text-embedding-3-small" # We'll use this by default, but you can change to your text-embedding-3-large if desired
```

## 設定有向量搜尋功能的 GCP BigQuery

這段說明怎麼在 BigQuery 建 dataset，並存浮點數向量，用來做 embedding 和向量搜尋。

```python
from google.auth import default

# Use default credentials
credentials, project_id = default()
region = "us-central1" # e.g: "us-central1"
print("Default Project ID:", project_id)
```

# 準備資料
我們會把 oai_docs 資料夾裡幾頁 OpenAI 文件做 embedding 並存起來。先逐一 embed，寫進 CSV，再用這個 CSV 上傳到索引。

這裡用到[這份 cookbook](https://github.com/openai/openai-cookbook/blob/main/examples/Embedding_long_inputs.ipynb) 提過的技巧。這是一個很快的 embed 做法，沒有考慮章節結構，沒有用 vision 模型描述圖表，長文件的 chunk 之間也沒有重疊。

要處理超過 8191 tokens 上限的長文字，可以把每個 chunk 的 embedding 分開用，或是合併，例如依 chunk 大小加權平均。

先拿 Python 官方 cookbook 裡把序列切成 chunk 的函式。

```python
def batched(iterable, n):
    """Batch data into tuples of length n. The last batch may be shorter."""
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while (batch := tuple(islice(it, n))):
        yield batch
```

接著定義一個函式，把字串編碼成 token 再切成 chunk。用的是 OpenAI 開源的快速 tokenizer，tiktoken。

想多了解怎麼用 tiktoken 算 token，看[這份 cookbook](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken)。



```python
def chunked_tokens(text, chunk_length, encoding_name='cl100k_base'):
    # Get the encoding object for the specified encoding name. OpenAI's tiktoken library, which is used in this notebook, currently supports two encodings: 'bpe' and 'cl100k_base'. The 'bpe' encoding is used for GPT-3 and earlier models, while 'cl100k_base' is used for newer models like GPT-4.
    encoding = tiktoken.get_encoding(encoding_name)
    # Encode the input text into tokens
    tokens = encoding.encode(text)
    # Create an iterator that yields chunks of tokens of the specified length
    chunks_iterator = batched(tokens, chunk_length)
    # Yield each chunk from the iterator
    yield from chunks_iterator
```

最後寫一個安全處理 embedding 請求的函式，輸入文字超過最大 context 長度也沒問題，做法是把 token 切 chunk，每個 chunk 各自 embed。`average` 設成 True 會回傳 chunk embedding 的加權平均，設成 False 就直接回傳原本的 chunk embedding 列表。

> 注意：這裡還有其他做法：
> - 用 GPT-4o 抓圖片或圖表的描述再拿去 embed
> - 依段落或章節切 chunk
> - 為每篇文章加更多描述性的 metadata。

```python
EMBEDDING_CTX_LENGTH = 8191
EMBEDDING_ENCODING='cl100k_base'
```

```python
def generate_embeddings(text, model):
    # Generate embeddings for the provided text using the specified model
    embeddings_response = openai_client.embeddings.create(model=model, input=text)
    # Extract the embedding data from the response
    embedding = embeddings_response.data[0].embedding
    return embedding

def len_safe_get_embedding(text, model=embeddings_model, max_tokens=EMBEDDING_CTX_LENGTH, encoding_name=EMBEDDING_ENCODING):
    # Initialize lists to store embeddings and corresponding text chunks
    chunk_embeddings = []
    chunk_texts = []
    # Iterate over chunks of tokens from the input text
    for chunk in chunked_tokens(text, chunk_length=max_tokens, encoding_name=encoding_name):
        # Generate embeddings for each chunk and append to the list
        chunk_embeddings.append(generate_embeddings(chunk, model=model))
        # Decode the chunk back to text and append to the list
        chunk_texts.append(tiktoken.get_encoding(encoding_name).decode(chunk))
    # Return the list of chunk embeddings and the corresponding text chunks
    return chunk_embeddings, chunk_texts
```

接著定義一個 helper 來抓文件的額外 metadata。這個例子是從一份類別清單裡挑一個，之後用來做 metadata 過濾。

```python
categories = ['authentication','models','techniques','tools','setup','billing_limits','other']

def categorize_text(text, categories):

    # Create a prompt for categorization
    messages = [
        {"role": "system", "content": f"""You are an expert in LLMs, and you will be given text that corresponds to an article in OpenAI's documentation.
         Categorize the document into one of these categories: {', '.join(categories)}. Only respond with the category name and nothing else."""},
        {"role": "user", "content": text}
    ]
    try:
        # Call the OpenAI API to categorize the text
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )

        # Extract the category from the response
        category = response.choices[0].message.content
        return category
    except Exception as e:
        print(f"Error categorizing text: {str(e)}")
        return None

# Example usage
```

再定義幾個 helper 來處理 oai_docs 資料夾裡的 .txt 檔。你可以拿去處理自己的資料，它支援 .txt 和 .pdf。

```python
def extract_text_from_pdf(pdf_path):
    # Initialize the PDF reader
    reader = PdfReader(pdf_path)
    text = ""
    # Iterate through each page in the PDF and extract text
    for page in reader.pages:
        text += page.extract_text()
    return text

def process_file(file_path, idx, categories, embeddings_model):
    file_name = os.path.basename(file_path)
    print(f"Processing file {idx + 1}: {file_name}")
    
    # Read text content from .txt files
    if file_name.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
    # Extract text content from .pdf files
    elif file_name.endswith('.pdf'):
        text = extract_text_from_pdf(file_path)
    
    title = file_name
    # Generate embeddings for the title
    title_vectors, title_text = len_safe_get_embedding(title, embeddings_model)
    print(f"Generated title embeddings for {file_name}")
    
    # Generate embeddings for the content
    content_vectors, content_text = len_safe_get_embedding(text, embeddings_model)
    print(f"Generated content embeddings for {file_name}")
    
    category = categorize_text(' '.join(content_text), categories)
    print(f"Categorized {file_name} as {category}")
    
    # Prepare the data to be appended
    data = []
    for i, content_vector in enumerate(content_vectors):
        data.append({
            "id": f"{idx}_{i}",
            "vector_id": f"{idx}_{i}",
            "title": title_text[0],
            "text": content_text[i],
            "title_vector": json.dumps(title_vectors[0]),  # Assuming title is short and has only one chunk
            "content_vector": json.dumps(content_vector),
            "category": category
        })
        print(f"Appended data for chunk {i + 1}/{len(content_vectors)} of {file_name}")
    
    return data
```

現在用這個 helper 處理 OpenAI 文件。想換成自己的資料，改下面 process_files 的資料夾就好。

注意它會並行處理資料夾裡的文件，txt 檔大概 30 秒內跑完，PDF 會稍微久一點。

```python
## Customize the location below if you are using different data besides the OpenAI documentation. Note that if you are using a different dataset, you will need to update the categories list as well.
folder_name = "../../../data/oai_docs"

files = [os.path.join(folder_name, f) for f in os.listdir(folder_name) if f.endswith('.txt') or f.endswith('.pdf')]
data = []

# Process each file concurrently
with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = {executor.submit(process_file, file_path, idx, categories, embeddings_model): idx for idx, file_path in enumerate(files)}
    for future in concurrent.futures.as_completed(futures):
        try:
            result = future.result()
            data.extend(result)
        except Exception as e:
            print(f"Error processing file: {str(e)}")

# Write the data to a CSV file
csv_file = os.path.join("..", "embedded_data.csv")
with open(csv_file, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ["id", "vector_id", "title", "text", "title_vector", "content_vector","category"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow(row)
        print(f"Wrote row with id {row['id']} to CSV")

# Convert the CSV file to a Dataframe
article_df = pd.read_csv("../embedded_data.csv")
# Read vectors from strings back into a list using json.loads
article_df["title_vector"] = article_df.title_vector.apply(json.loads)
article_df["content_vector"] = article_df.content_vector.apply(json.loads)
article_df["vector_id"] = article_df["vector_id"].apply(str)
article_df["category"] = article_df["category"].apply(str)
article_df.head()
```

現在有一個 `embedded_data.csv`，六個欄位，可以上傳到向量資料庫了！

# 建立有向量搜尋的 BigQuery 表

## 建立 BigQuery dataset

用 Google SDK 建一個叫 "oai_docs" 的 dataset，表名叫 "embedded_data"，這些變數和 region 都可以改。

*PS：我們不建 BigQuery index。index 能提升向量搜尋效能，但需要資料超過 1k 筆，我們的範例沒那麼多。你自己的案例可以考慮加。*

```python
# Create bigquery table

from google.cloud import bigquery
from google.api_core.exceptions import Conflict

# Define the dataset ID (project_id.dataset_id)
raw_dataset_id = 'oai_docs'
dataset_id = project_id + '.' + raw_dataset_id

client = bigquery.Client(credentials=credentials, project=project_id)

# Construct a full Dataset object to send to the API
dataset = bigquery.Dataset(dataset_id)

# Specify the geographic location where the dataset should reside
dataset.location = "US"

# Send the dataset to the API for creation
try:
    dataset = client.create_dataset(dataset, timeout=30)
    print(f"Created dataset {client.project}.{dataset.dataset_id}")
except Conflict:
    print(f"dataset {dataset.dataset_id } already exists")
```

```python
# Read the CSV file, properly handling multiline fields
csv_file_path = "../embedded_data.csv"
df = pd.read_csv(csv_file_path, engine='python', quotechar='"', quoting=1)

# Display the first few rows of the dataframe
df.head()
```

## 建表並上傳資料

建表時要指定欄位名稱和型別。注意 'content_vector' 這個欄位，它讓每一筆可以存一組浮點數向量，之後向量搜尋就靠它。

這段程式會迴圈讀前面產生的 CSV，把資料插入 BigQuery。
如果重複執行，會插入多筆一模一樣的資料，搜尋結果會比較不準（你可以對 ID 加唯一限制，或每次先清空資料庫）。

```python
# Read the CSV file, properly handling multiline fields
dataset_id = project_id + '.' + raw_dataset_id
client = bigquery.Client(credentials=credentials, project=project_id)
csv_file_path = "../embedded_data.csv"
df = pd.read_csv(csv_file_path, engine='python', quotechar='"', quoting=1)

# Preprocess the data to ensure content_vector is correctly formatted
# removing last and first character which are brackets [], comma splitting and converting to float
def preprocess_content_vector(row):
    row['content_vector'] = [float(x) for x in row['content_vector'][1:-1].split(',')]
    return row

# Apply preprocessing to the dataframe
df = df.apply(preprocess_content_vector, axis=1)

# Define the schema of the final table
final_schema = [
    bigquery.SchemaField("id", "STRING"),
    bigquery.SchemaField("vector_id", "STRING"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("text", "STRING"),
    bigquery.SchemaField("title_vector", "STRING"),
    bigquery.SchemaField("content_vector", "FLOAT64", mode="REPEATED"),
    bigquery.SchemaField("category", "STRING"),
]

# Define the final table ID
raw_table_id = 'embedded_data'
final_table_id = f'{dataset_id}.' + raw_table_id

# Create the final table object
final_table = bigquery.Table(final_table_id, schema=final_schema)

# Send the table to the API for creation
final_table = client.create_table(final_table, exists_ok=True)  # API request
print(f"Created final table {project_id}.{final_table.dataset_id}.{final_table.table_id}")

# Convert DataFrame to list of dictionaries for BigQuery insertion
rows_to_insert = df.to_dict(orient='records')

# Upload data to the final table
errors = client.insert_rows_json(f"{final_table.dataset_id}.{final_table.table_id}", rows_to_insert)  # API request

if errors:
    print(f"Encountered errors while inserting rows: {errors}")
else:
    print(f"Successfully loaded data into {dataset_id}:{final_table_id}")
```

# 測試搜尋
資料上傳後，先在本機測試純向量相似度搜尋和帶 metadata 過濾的搜尋，確認運作正常。

下面這個查詢是純向量搜尋，沒有用 category 過濾。

```python
query = "What model should I use to embed?"
category = "models"

embedding_query = generate_embeddings(query, embeddings_model)
embedding_query_list = ', '.join(map(str, embedding_query))

query = f"""
WITH search_results AS (
  SELECT query.id AS query_id, base.id AS base_id, distance
  FROM VECTOR_SEARCH(
    TABLE oai_docs.embedded_data, 'content_vector',
    (SELECT ARRAY[{embedding_query_list}] AS content_vector, 'query_vector' AS id),
    top_k => 2, distance_type => 'COSINE', options => '{{"use_brute_force": true}}')
)
SELECT sr.query_id, sr.base_id, sr.distance, ed.text, ed.title
FROM search_results sr
JOIN oai_docs.embedded_data ed ON sr.base_id = ed.id
ORDER BY sr.distance ASC
"""

query_job = client.query(query)
results = query_job.result()  # Wait for the job to complete

for row in results:
    print(f"query_id: {row['query_id']}, base_id: {row['base_id']}, distance: {row['distance']}, text_truncated: {row['text'][0:100]}")
```

## 帶 metadata 過濾的搜尋
Metadata 過濾可以在語意最接近的結果之上，再限制必須符合某些屬性。

下面的程式示範怎麼執行帶 metadata 過濾的查詢：

```python

query = "What model should I use to embed?"
category = "models"

embedding_query = generate_embeddings(query, embeddings_model)
embedding_query_list = ', '.join(map(str, embedding_query))


query = f"""
WITH search_results AS (
  SELECT query.id AS query_id, base.id AS base_id, distance
  FROM VECTOR_SEARCH(
    (SELECT * FROM oai_docs.embedded_data WHERE category = '{category}'), 
    'content_vector',
    (SELECT ARRAY[{embedding_query_list}] AS content_vector, 'query_vector' AS id),
    top_k => 4, distance_type => 'COSINE', options => '{{"use_brute_force": true}}')
)
SELECT sr.query_id, sr.base_id, sr.distance, ed.text, ed.title, ed.category
FROM search_results sr
JOIN oai_docs.embedded_data ed ON sr.base_id = ed.id
ORDER BY sr.distance ASC
"""


query_job = client.query(query)
results = query_job.result()  # Wait for the job to complete

for row in results:
    print(f"category: {row['category']}, title: {row['title']}, base_id: {row['base_id']}, distance: {row['distance']}, text_truncated: {row['text'][0:100]}")
```

# 建立 GCP Function

## 匯出變數

我們要部署這個資料夾裡的 `main.py`（也可以看[這裡](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/rag-quickstart/gcp/main.py)）。

第一步，匯出變數，讓它知道要查哪個表和 dataset，以及用 OpenAI API 產生 embedding 要用的設定。

```python
# Create a dictionary to store the environment variables (they were used previously and are just retrieved)
env_variables = {
    'OPENAI_API_KEY': openai_api_key,
    'EMBEDDINGS_MODEL': embeddings_model,
    'PROJECT_ID': project_id,
    'DATASET_ID': raw_dataset_id,
    'TABLE_ID': raw_table_id
}

# Write the environment variables to a YAML file
with open('env.yml', 'w') as yaml_file:
    yaml.dump(env_variables, yaml_file, default_flow_style=False)

print("env.yml file created successfully.")
```

## 部署 Function

接著為目前的專案建立一個叫 "openai_docs_search" 的 Google Function，執行下面的 CLI 指令，用到前面建立的環境變數。注意這個 function 不用認證，任何地方都能呼叫，正式環境不要這樣用，或是自己加認證機制。

```python
! gcloud functions deploy openai_docs_search \
  --runtime python39 \
  --trigger-http \
  --allow-unauthenticated \
  --env-vars-file env.yml
```

# 接進 ChatGPT 的 Custom GPT

現在有了查詢這個向量索引的 GCP Function，把它變成 GPT Action 吧！

GPTs 的文件看[這裡](https://openai.com/index/introducing-gpts/)，GPT Actions 看[這裡](https://platform.openai.com/docs/actions)。下面的內容拿來當 GPT 的 instructions 和 GPT Action 的 OpenAPI spec。

## 建立 OpenAPI Spec

下面是一份 OpenAPI spec 範例。執行下面的區塊後，可用的 spec 會複製到剪貼簿，貼到 GPT Action 裡就行。

注意預設沒有任何認證，不過你可以照 GCP 的[文件](https://cloud.google.com/functions/docs/securing/authenticating)幫 GCP Functions 加上認證。

```python
spec = f"""
openapi: 3.1.0
info:
  title: OpenAI API documentation search
  description: API to perform a semantic search over OpenAI APIs
  version: 1.0.0
servers:
  - url: https://{region}-{project_id}.cloudfunctions.net
    description: Main (production) server
paths:
  /openai_docs_search:
    post:
      operationId: openai_docs_search
      summary: Perform a search
      description: Returns search results for the given query parameters.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: The search query string
                top_k:
                  type: integer
                  description: Number of top results to return. Maximum is 3.
                category:
                  type: string
                  description: The category to filter on, on top of similarity search (used for metadata filtering). Possible values are {categories}.
      responses:
        '200':
          description: A JSON response with the search results
          content:
            application/json:
              schema:
                type: object
                properties:
                  items:
                    type: array
                    items:
                      type: object
                      properties:
                        text:
                          type: string
                          example: "Learn how to turn text into numbers, unlocking use cases like search..."
                        title:
                          type: string
                          example: "embeddings.txt"
                        distance:
                          type: number
                          format: float
                          example: 0.484939891778730
                        category:
                          type: string
                          example: "models"
"""
print(spec)
pyperclip.copy(spec)
print("OpenAPI spec copied to clipboard")
```

## 建立 GPT Instructions

Instructions 可以自己改。prompt engineering 的技巧看我們的[文件](https://platform.openai.com/docs/guides/prompt-engineering)。

```python
instructions = f'''
You are an OpenAI docs assistant. You have an action in your knowledge base where you can make a POST request to search for information. The POST request should always include: {{
    "query": "<user_query>",
    "k_": <integer>,
    "category": <string, but optional>
}}. Your goal is to assist users by performing searches using this POST request and providing them with relevant information based on the query.

You must only include knowledge you get from your action in your response.
The category must be from the following list: {categories}, which you should determine based on the user's query. If you cannot determine, then do not include the category in the POST request.
'''
pyperclip.copy(instructions)
print("GPT Instructions copied to clipboard")
print(instructions)
```

# 回顧

我們已經把 GCP BigQuery 向量搜尋接到 ChatGPT 的 GPT Actions，做了這幾件事：
1. 用 OpenAI embeddings 對文件做 embedding，並用 gpt-4o 補上一些 metadata。
2. 把資料（原文和 embedding 向量）上傳到 GCP BigQuery。
3. 在 GCP Functions 建一個 endpoint 來取資料。
4. 把它接進 Custom GPT。

這個 GPT 現在能檢索資料來回答使用者問題，答案會更準確，也更貼近你的資料。下面是實際運作的樣子：

![gcp-rag-quickstart-gpt.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gcp_rag_quickstart_gpt.png)

## 重點整理

- 整個 RAG 流程可以全放在 GCP：BigQuery 存向量，Cloud Function 當查詢 API，ChatGPT 透過 GPT Action 呼叫。
- 長文件超過 embedding 模型的 token 上限時，要切 chunk 各自 embed，再視情況取加權平均。
- 存向量時順便存 metadata（例如類別），搜尋時就能同時用語意和屬性過濾。
- 範例的 Function 沒有認證，正式環境一定要加。
- 重複上傳會產生重複資料，影響搜尋品質，要自己處理唯一性。

## 練習

1. 把 process_files 的資料夾換成你自己的 .txt 文件，重跑一次，看 `embedded_data.csv` 的內容。
2. 修改 metadata 的類別清單，加一個你自己的類別，再用帶過濾的查詢確認只回傳該類別的結果。
3. 把 chunk 之間加一點重疊（改切 chunk 的函式），比較搜尋結果有沒有改善。
