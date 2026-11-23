---
translated: true
source: examples/vector_databases/weaviate/question-answering-with-weaviate-and-openai.ipynb
---

# 用 Weaviate 的 OpenAI Q&A 模組做問答

> 原文：[examples/vector_databases/weaviate/question-answering-with-weaviate-and-openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/question-answering-with-weaviate-and-openai.ipynb)



## 這篇在做什麼

從零開始架一個 Weaviate，匯入 Simple Wikipedia 文章，然後直接在 Weaviate 裡對資料問問題。向量化交給 `text2vec-openai` 模組，答案生成交給 `qna-openai` 模組，你不用自己呼叫 embedding 或 completions API。

## 學完你會

- 建立 Weaviate instance（WCS 或 Docker），並用 OpenAI API key 連線
- 設計 schema，指定用哪個 embedding model、哪些欄位要向量化
- 批次匯入資料，並用 `ask` 查詢拿到附帶答案的結果

## 開跑前

- `OPENAI_API_KEY` 環境變數
- 一個 Weaviate instance：Weaviate Cloud Service 的免費 sandbox，或本機 Docker
- 本機安裝 `weaviate-client`、`datasets`、`apache-beam`。在 Colab 上直接在 cell 裡用 `%pip install` 就好

這份 notebook 的情境是：
* 你的資料還沒向量化
* 你想用 [OpenAI completions](https://beta.openai.com/docs/api-reference/completions) endpoint 對資料做 Q&A（[了解更多](https://weaviate.io/developers/weaviate/modules/reader-generator-modules/qna-openai)）
* 你想用 Weaviate 的 OpenAI 模組（[text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai)）幫你產生 vector embedding

這份 notebook 帶你走一個簡單的流程：架好 Weaviate instance、用 OpenAI API key 連線、設定資料 schema、匯入資料（會自動產生 vector embedding），最後跑問答。

## Weaviate 是什麼

Weaviate 是開源的 vector search engine，會把資料物件和它們的向量一起存起來。這樣就能把 vector search 跟結構化過濾結合。

Weaviate 用 KNN 演算法建立針對向量最佳化的 index，查詢會非常快。詳見[這裡](https://weaviate.io/blog/why-is-vector-search-so-fast)。

Weaviate 讓你用自己喜歡的 ML 模型，也能順暢擴展到數十億個資料物件。

### 部署選項

不管你的情境或正式環境怎麼設，Weaviate 都有對應的選項。可以用下列方式部署：
* Self-hosted：用 docker 在本機或任何伺服器上部署 Weaviate。
* SaaS：用 [Weaviate Cloud Service (WCS)](https://console.weaviate.io/) 託管你的 Weaviate instance。
* Hybrid-SaaS：把 Weaviate 部署在你自己的私有雲。

### 程式語言

Weaviate 提供四種 [client library](https://weaviate.io/developers/weaviate/client-libraries)，讓你的 app 跟它溝通：
* [Python](https://weaviate.io/developers/weaviate/client-libraries/python)
* [JavaScript](https://weaviate.io/developers/weaviate/client-libraries/javascript)
* [Java](https://weaviate.io/developers/weaviate/client-libraries/java)
* [Go](https://weaviate.io/developers/weaviate/client-libraries/go)

另外 Weaviate 也有 [REST layer](https://weaviate.io/developers/weaviate/api/rest/objects)，所以只要支援 REST request 的語言都能呼叫它。

## Demo 流程
流程如下：
- **前置設定**：建立 Weaviate instance 並安裝需要的 library
- **連線**：連到你的 Weaviate instance
- **Schema 設定**：設定資料的 schema
    - *注意*：這裡可以指定要用哪個 OpenAI Embedding Model
    - *注意*：這裡可以設定哪些 property 要建 index
- **匯入資料**：載入 demo 資料集並匯入 Weaviate
    - *注意*：匯入時會依 schema 的設定自動建立 index
    - *注意*：你不需要自己把資料向量化，Weaviate 會跟 OpenAI 溝通幫你做
- **執行查詢**：查詢
    - *注意*：你不需要自己把 query 向量化，Weaviate 會跟 OpenAI 溝通幫你做
    - *注意*：`qna-openai` 模組會自動呼叫 OpenAI completions endpoint

跑完這份 notebook，你應該就大致了解怎麼架設並使用 vector database 做問答。

## Weaviate 的 OpenAI 模組
所有 Weaviate instance 都內建 [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai) 和 [qna-openai](https://weaviate.io/developers/weaviate/modules/reader-generator-modules/qna-openai) 模組。

第一個模組負責在匯入資料（或任何 CRUD 操作）和執行搜尋查詢時做向量化。第二個模組負責跟 OpenAI completions endpoint 溝通。

### 不需要手動向量化資料
這點很方便。有了 [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai)，你不用手動向量化資料，Weaviate 需要時會自己呼叫 OpenAI。

你只要做兩件事：
1. 連 Weaviate Client 時提供你的 OpenAI API Key
2. 在 Schema 裡指定要用哪個 OpenAI vectorizer

## 前置需求

開始這個專案前，需要先準備：

* 建立一個 `Weaviate` instance
* 安裝 library
    * `weaviate-client`
    * `datasets`
    * `apache-beam`
* 取得你的 [OpenAI API key](https://beta.openai.com/account/api-keys)

===========================================================
### 建立 Weaviate instance

建立 Weaviate instance 有兩個選項：

1. （建議）[Weaviate Cloud Service](https://console.weaviate.io/)：把 Weaviate instance 託管在雲端。這份 cookbook 用免費 sandbox 就綽綽有餘。
2. 用 Docker 在本機安裝並執行 Weaviate。

#### 選項 1：WCS 安裝步驟

用 [Weaviate Cloud Service](https://console.weaviate.io/) (WCS) 建立免費的 Weaviate cluster。
1. 建立免費帳號，或登入 [WCS](https://console.weaviate.io/)
2. 用下面的設定建立 `Weaviate Cluster`：
    * Sandbox: `Sandbox Free`
    * Weaviate Version: 用預設（最新版）
    * OIDC Authentication: `Disabled`
3. instance 一兩分鐘內就會準備好
4. 記下 `Cluster Id`。這個連結會帶你到 cluster 的完整路徑（之後連線會用到），大概長這樣：`https://your-project-name.weaviate.network`

#### 選項 2：用 Docker 跑本機 Weaviate instance

用 Docker 在本機安裝並執行 Weaviate。
1. 下載 [./docker-compose.yml](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/docker-compose.yml)
2. 打開 terminal，切到 docker-compose.yml 所在的目錄，用 `docker-compose up -d` 啟動 docker
3. 準備好後，instance 可以在 [http://localhost:8080](http://localhost:8080) 連到

注意：要關掉 docker instance 可以執行：`docker-compose down`

##### 了解更多
想進一步了解怎麼用 Docker 跑 Weaviate，請看[安裝文件](https://weaviate.io/developers/weaviate/installation/docker-compose)。

===========================================================    
## 安裝需要的 library

執行這個專案前，請先確認裝好下面的 library：

### Weaviate Python client

[Weaviate Python client](https://weaviate.io/developers/weaviate/client-libraries/python) 讓你的 Python 專案能跟 Weaviate instance 溝通。

### datasets 與 apache-beam

要載入範例資料，需要 `datasets` library 和它的相依套件 `apache-beam`。

```python
# Install the Weaviate client for Python
!pip install weaviate-client>3.11.0

# Install datasets and apache-beam to load the sample datasets
!pip install datasets apache-beam
```

===========================================================
## 準備你的 OpenAI API key

`OpenAI API key` 用在匯入資料時的向量化，以及查詢時。

如果還沒有 OpenAI API key，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 後，請把它放進環境變數 `OPENAI_API_KEY`。

```python
# Export OpenAI API Key
!export OPENAI_API_KEY="your key"
```

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os

# Note. alternatively you can set a temporary env variable like this:
# os.environ['OPENAI_API_KEY'] = 'your-key-goes-here'

if os.getenv("OPENAI_API_KEY") is not None:
    print ("OPENAI_API_KEY is ready")
else:
    print ("OPENAI_API_KEY environment variable not found")
```

## 連到你的 Weaviate instance

這一節要做的是：

1. 測試環境變數 `OPENAI_API_KEY`，**請確認**你已完成 [#Prepare-your-OpenAI-API-key](#Prepare-your-OpenAI-API-key) 那一步
2. 用你的 `OpenAI API Key` 連到 Weaviate
3. 測試 client 連線

### Client

完成這一步後，之後所有 Weaviate 相關操作都用 `client` 物件來做。

```python
import weaviate
from datasets import load_dataset
import os

# Connect to your Weaviate instance
client = weaviate.Client(
    url="https://your-wcs-instance-name.weaviate.network/",
#   url="http://localhost:8080/",
    auth_client_secret=weaviate.auth.AuthApiKey(api_key="<YOUR-WEAVIATE-API-KEY>"), # comment out this line if you are not using authentication for your Weaviate instance (i.e. for locally deployed instances)
    additional_headers={
        "X-OpenAI-Api-Key": os.getenv("OPENAI_API_KEY")
    }
)

# Check if your instance is live and ready
# This should return `True`
client.is_ready()
```

# Schema

這一節要做的是：
1. 設定資料的 schema
2. 選擇 OpenAI 模組

> 這是第二個、也是最後一個需要 OpenAI 專屬設定的步驟。
> 這之後的說明只會講 Weaviate，因為 OpenAI 的工作會自動處理。


## 什麼是 schema

在 Weaviate 裡，你用 __schema__ 描述每一種要搜尋的實體。

Schema 是用來告訴 Weaviate：
* 要用哪個 embedding model 把資料向量化
* 你的資料由什麼組成（property 名稱和型別）
* 哪些 property 要向量化並建 index

這份 cookbook 用 `Articles` 資料集，裡面有：
* `title`
* `content`
* `url`

我們要向量化 `title` 和 `content`，但不向量化 `url`。

向量化和查詢資料用 `text-embedding-3-small`，Q&A 用 `gpt-3.5-turbo-instruct`。

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
        }, 
        "qna-openai": {
          "model": "gpt-3.5-turbo-instruct",
          "maxTokens": 16,
          "temperature": 0.0,
          "topP": 1,
          "frequencyPenalty": 0.0,
          "presencePenalty": 0.0
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
        "dataType": ["text"]
    },
    {
        "name": "url",
        "description": "URL to the article",
        "dataType": ["string"],
        "moduleConfig": { "text2vec-openai": { "skip": True } }
    }]
}

# add the Article schema
client.schema.create_class(article_schema)

# get the schema to make sure it worked
client.schema.get()
```

## 匯入資料

這一節要做的是：
1. 載入 Simple Wikipedia 資料集
2. 設定 Weaviate Batch import（讓匯入更有效率）
3. 把資料匯入 Weaviate

> 注意：<br/>
> 如前面所說，我們不需要手動向量化資料。<br/>
> [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai) 模組會處理。

```python
### STEP 1 - load the dataset

from datasets import load_dataset
from typing import List, Iterator

# We'll use the datasets library to pull the Simple Wikipedia dataset for embedding
dataset = list(load_dataset("wikipedia", "20220301.simple")["train"])

# For testing, limited to 2.5k articles for demo purposes
dataset = dataset[:2_500]

# Limited to 25k articles for larger demo purposes
# dataset = dataset[:25_000]

# for free OpenAI acounts, you can use 50 objects
# dataset = dataset[:50]
```

```python
### Step 2 - configure Weaviate Batch, with
# - starting batch size of 100
# - dynamically increase/decrease based on performance
# - add timeout retries if something goes wrong

client.batch.configure(
    batch_size=10, 
    dynamic=True,
    timeout_retries=3,
#   callback=None,
)
```

```python
### Step 3 - import data

print("Importing Articles")

counter=0

with client.batch as batch:
    for article in dataset:
        if (counter %10 == 0):
            print(f"Import {counter} / {len(dataset)} ")

        properties = {
            "title": article["title"],
            "content": article["text"],
            "url": article["url"]
        }
        
        batch.add_data_object(properties, "Article")
        counter = counter+1

print("Importing Articles complete")
```

```python
# Test that all data has loaded – get object count
result = (
    client.query.aggregate("Article")
    .with_fields("meta { count }")
    .do()
)
print("Object count: ", result["data"]["Aggregate"]["Article"], "\n")
```

```python
# Test one article has worked by checking one object
test_article = (
    client.query
    .get("Article", ["title", "url", "content"])
    .with_limit(1)
    .do()
)["data"]["Get"]["Article"][0]

print(test_article['title'])
print(test_article['url'])
print(test_article['content'])
```

### 對資料做問答

跟前面一樣，我們對新建的 Index 下一些查詢，依跟現有向量的接近程度拿回結果。

```python
def qna(query, collection_name):
    
    properties = [
        "title", "content", "url",
        "_additional { answer { hasAnswer property result startPosition endPosition } distance }"
    ]

    ask = {
        "question": query,
        "properties": ["content"]
    }

    result = (
        client.query
        .get(collection_name, properties)
        .with_ask(ask)
        .with_limit(1)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]
```

```python
query_result = qna("Did Alanis Morissette win a Grammy?", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['_additional']['answer']['result']} (Distance: {round(article['_additional']['distance'],3) })")
```

```python
query_result = qna("What is the capital of China?", "Article")

for i, article in enumerate(query_result):
    if article['_additional']['answer']['hasAnswer'] == False:
      print('No answer found')
    else:
      print(f"{i+1}. { article['_additional']['answer']['result']} (Distance: {round(article['_additional']['distance'],3) })")
```

謝謝你一路跟著做，現在你已經能架設自己的 vector database，並用 embedding 做各種有趣的事，祝玩得開心！更複雜的使用情境，請繼續看這個 repo 裡的其他 cookbook 範例。

## 重點整理

- Weaviate 把資料物件和向量放在一起，所以能把 vector search 和結構化過濾合用。
- 用 `text2vec-openai` 模組後，匯入資料和查詢時的向量化都由 Weaviate 代為呼叫 OpenAI，你只要在連線時給 API key。
- Schema 決定用哪個 embedding model、哪些 property 要向量化，所以像 `url` 這種不需要語意搜尋的欄位可以排除。
- `qna-openai` 模組把檢索到的內容交給 completions 模型生成答案，等於內建一個簡單的 RAG 流程。
- 批次匯入可以讓大量資料進得更有效率。

## 練習

1. 把 schema 裡的向量化設定改成連 `url` 也一起向量化（或只向量化 `title`），重新匯入後比較查詢結果有什麼不同。
2. 改一個自己的問題丟給 Q&A 查詢，並調整回傳的結果數量，觀察答案跟來源文章的關係。
3. 把 Q&A 用的模型或 embedding model 換成別的，重建 schema 後重新匯入，比較答案品質。
