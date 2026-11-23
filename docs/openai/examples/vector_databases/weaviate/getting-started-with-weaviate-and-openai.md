---
translated: true
source: examples/vector_databases/weaviate/getting-started-with-weaviate-and-openai.ipynb
---
# 用 Weaviate 的 OpenAI vectorize module 做 embedding 搜尋

> 原文：[examples/vector_databases/weaviate/getting-started-with-weaviate-and-openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/getting-started-with-weaviate-and-openai.ipynb)



## 這篇在做什麼

你的資料還沒做過向量化，又想對它做 vector search，這篇示範用 Weaviate 搭配 OpenAI 的 `text2vec-openai` module，讓 Weaviate 自動幫你產生 embedding。流程包含建立 Weaviate instance、連線、設定 schema、匯入資料，最後跑語意搜尋。

## 學完你會

- 建立 Weaviate instance（雲端或 Docker），並用 OpenAI API key 連線
- 設定 schema，指定要用哪個 embedding 模型、哪些欄位要向量化
- 匯入資料並用文字 query 做語意搜尋，不用自己呼叫 embedding API

## 開跑前

- 需要 `OPENAI_API_KEY` 環境變數
- 需要一個 Weaviate instance：Weaviate Cloud Service 帳號（免費 sandbox 就夠），或本機安裝 Docker
- 安裝 `weaviate-client`、`datasets`、`apache-beam`


這份 notebook 適用的情境是：
* 你的資料還沒向量化
* 你想對資料做 Vector Search
* 你想用 Weaviate 搭配 OpenAI module（[text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai)）幫你產生 vector embedding

這份 notebook 會帶你走一個簡單流程：建立 Weaviate instance、（用 OpenAI API key）連線、設定資料 schema、匯入資料（會自動產生資料的 vector embedding），然後跑語意搜尋。

很多客戶都有這種需求：想在安全的環境裡，用自己的資料儲存跟搜尋我們的 embedding，來支援 chatbot、主題建模等正式環境的應用。

## Weaviate 是什麼

Weaviate 是開源的 vector 搜尋引擎，會把資料物件跟它們的 vector 存在一起，所以可以把 vector 搜尋跟結構化過濾結合。

Weaviate 用 KNN 演算法建立針對 vector 最佳化的索引，讓查詢跑得非常快。更多資訊看[這裡](https://weaviate.io/blog/why-is-vector-search-so-fast)。

Weaviate 讓你用自己喜歡的 ML 模型，也能順暢擴充到數十億個資料物件。

### 部署選項

不管你的情境或正式環境怎麼配置，Weaviate 都有對應的選項。你可以用下面幾種方式部署：
* Self-hosted：用 docker 在本機或任何伺服器上部署 Weaviate。
* SaaS：用 [Weaviate Cloud Service (WCS)](https://console.weaviate.io/) 代管你的 Weaviate instance。
* Hybrid-SaaS：把 Weaviate 部署在你自己的私有雲上。

### 程式語言

Weaviate 提供四種 [client library](https://weaviate.io/developers/weaviate/client-libraries)，讓你的應用程式跟它溝通：
* [Python](https://weaviate.io/developers/weaviate/client-libraries/python)
* [JavaScript](https://weaviate.io/developers/weaviate/client-libraries/javascript)
* [Java](https://weaviate.io/developers/weaviate/client-libraries/java)
* [Go](https://weaviate.io/developers/weaviate/client-libraries/go)

另外，Weaviate 也有 [REST 層](https://weaviate.io/developers/weaviate/api/rest/objects)。基本上任何能發 REST request 的語言都能呼叫 Weaviate。

## Demo 流程
流程是：
- **前置設定**：建立 Weaviate instance，安裝需要的函式庫
- **連線**：連到你的 Weaviate instance
- **Schema 設定**：設定資料的 schema
    - *注意*：這裡可以指定要用哪個 OpenAI Embedding Model
    - *注意*：這裡可以設定要索引哪些 property
- **匯入資料**：載入範例資料集並匯入 Weaviate
    - *注意*：匯入時會依 schema 的設定自動建立索引
    - *注意*：你不用自己把資料向量化，Weaviate 會替你跟 OpenAI 溝通
- **執行查詢**：查詢
    - *注意*：你也不用自己把 query 向量化，Weaviate 會替你跟 OpenAI 溝通

跑完這份 notebook 之後，你應該對 vector database 的設定跟使用有基本概念，可以繼續做更複雜、用到我們 embedding 的應用。

## Weaviate 裡的 OpenAI Module
所有 Weaviate instance 都內建 [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai) module。

這個 module 負責在匯入（或任何 CRUD 操作）和執行查詢時處理向量化。

### 不用手動向量化資料
這是好消息。有了 [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai)，你不用手動把資料向量化，Weaviate 需要時會替你呼叫 OpenAI。

你只要做兩件事：
1. 在連接 Weaviate Client 時提供你的 OpenAI API Key
2. 在 Schema 裡指定要用哪個 OpenAI vectorizer

## 前置需求

開始這個專案前，需要先準備：

* 建立一個 `Weaviate` instance
* 安裝函式庫
    * `weaviate-client`
    * `datasets`
    * `apache-beam`
* 取得你的 [OpenAI API key](https://beta.openai.com/account/api-keys)

===========================================================
### 建立 Weaviate instance

建立 Weaviate instance 有 2 個選項：

1. （建議）[Weaviate Cloud Service](https://console.weaviate.io/)：把 Weaviate instance 代管在雲端。免費的 sandbox 對這份 cookbook 綽綽有餘。
2. 用 Docker 在本機安裝並執行 Weaviate。

#### 選項 1：WCS 安裝步驟

用 [Weaviate Cloud Service](https://console.weaviate.io/)（WCS）建立免費的 Weaviate cluster。
1. 建立免費帳號，或登入 [WCS](https://console.weaviate.io/)
2. 用下列設定建立一個 `Weaviate Cluster`：
    * Sandbox：`Sandbox Free`
    * Weaviate Version：用預設值（最新版）
    * OIDC Authentication：`Disabled`
3. 你的 instance 一兩分鐘內就會準備好
4. 記下 `Cluster Id`。這個連結會帶你到 cluster 的完整路徑（之後連線會用到），大概長這樣：`https://your-project-name.weaviate.network` 

#### 選項 2：用 Docker 在本機執行 Weaviate

用 Docker 在本機安裝並執行 Weaviate。
1. 下載 [./docker-compose.yml](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/weaviate/docker-compose.yml) 檔案
2. 打開終端機，切到 docker-compose.yml 所在的目錄，用這個指令啟動 docker：`docker-compose up -d`
3. 準備好之後，你的 instance 就能在 [http://localhost:8080](http://localhost:8080) 使用

注意：要關掉 docker instance 可以執行：`docker-compose down`

##### 延伸閱讀
想進一步了解怎麼用 Docker 跑 Weaviate，請看[安裝文件](https://weaviate.io/developers/weaviate/installation/docker-compose)。

===========================================================    
## 安裝需要的函式庫

執行這個專案前，請確認已經裝好下面的函式庫：

### Weaviate Python client

[Weaviate Python client](https://weaviate.io/developers/weaviate/client-libraries/python) 讓你從 Python 專案跟 Weaviate instance 溝通。

### datasets 和 apache-beam

要載入範例資料，需要 `datasets` 函式庫和它的相依套件 `apache-beam`。

```python
# Install the Weaviate client for Python
!pip install weaviate-client>=3.11.0

# Install datasets and apache-beam to load the sample datasets
!pip install datasets apache-beam
```

===========================================================
## 準備你的 OpenAI API key

`OpenAI API key` 用在匯入時的資料向量化，以及執行查詢。

如果你還沒有 OpenAI API key，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，請把它加到環境變數 `OPENAI_API_KEY`。

```python
# Export OpenAI API Key
!export OPENAI_API_KEY="your key"
```

```python
# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.
import os

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = 'your-key-goes-here'

if os.getenv("OPENAI_API_KEY") is not None:
    print ("OPENAI_API_KEY is ready")
else:
    print ("OPENAI_API_KEY environment variable not found")
```

## 連到你的 Weaviate instance

這一節我們會：

1. 測試環境變數 `OPENAI_API_KEY`，**務必**先完成 [#Prepare-your-OpenAI-API-key](#Prepare-your-OpenAI-API-key) 那一步
2. 用你的 `OpenAI API Key` 連到 Weaviate
3. 測試 client 連線

### Client 

這一步之後，所有 Weaviate 相關操作都會用 `client` 物件來做。

```python
import weaviate
from datasets import load_dataset
import os

# Connect to your Weaviate instance
client = weaviate.Client(
    url="https://your-wcs-instance-name.weaviate.network/",
    # url="http://localhost:8080/",
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

這一節我們會：
1. 設定資料的 schema
2. 選擇 OpenAI module

> 這是第二步，也是最後一個需要 OpenAI 專屬設定的步驟。
> 這之後的說明只會碰到 Weaviate，因為 OpenAI 的工作會自動處理。


## Schema 是什麼

在 Weaviate 裡，你用 __schema__ 描述每一種要搜尋的實體。

Schema 是你告訴 Weaviate 這些事的方式：
* 要用哪個 embedding 模型把資料向量化
* 你的資料由什麼組成（property 名稱和型別）
* 哪些 property 要向量化並建索引

這份 cookbook 用 `Articles` 資料集，裡面有：
* `title`
* `content`
* `url`

我們要向量化 `title` 和 `content`，但不向量化 `url`。

向量化和查詢資料都會用 `text-embedding-3-small`。

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

這一節我們會：
1. 載入 Simple Wikipedia 資料集
2. 設定 Weaviate Batch 匯入（讓匯入更有效率）
3. 把資料匯入 Weaviate

> 注意： <br/>
> 如前面所說，我們不需要手動向量化資料。<br/>
> [text2vec-openai](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai) module 會處理。

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

### 搜尋資料

跟前面一樣，我們對新建的索引發幾個查詢，依結果跟既有 vector 的接近程度取回資料

```python
def query_weaviate(query, collection_name):
    
    nearText = {
        "concepts": [query],
        "distance": 0.7,
    }

    properties = [
        "title", "content", "url",
        "_additional {certainty distance}"
    ]

    result = (
        client.query
        .get(collection_name, properties)
        .with_near_text(nearText)
        .with_limit(10)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]
```

```python
query_result = query_weaviate("modern art in Europe", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']} (Score: {round(article['_additional']['certainty'],3) })")
```

```python
query_result = query_weaviate("Famous battles in Scottish history", "Article")

for i, article in enumerate(query_result):
    print(f"{i+1}. { article['title']} (Score: {round(article['_additional']['certainty'],3) })")
```

謝謝你跟著做，現在你已經能自己架 vector database，並用 embedding 做各種有趣的事，盡情玩吧！想看更複雜的應用，請繼續看這個 repo 裡的其他 cookbook 範例。

## 重點整理

- 用 `text2vec-openai` module，Weaviate 會在匯入和查詢時自動呼叫 OpenAI 產生 embedding，你不用自己向量化。
- OpenAI API key 在連線 client 時提供，embedding 模型在 schema 裡指定。
- Schema 決定資料結構，以及哪些 property 會被向量化（例如 `title`、`content` 要，`url` 不要）。
- Weaviate 把物件和 vector 存在一起，所以 vector 搜尋可以結合結構化過濾。
- Weaviate 可以自己架、用雲端或放在私有雲，client 有多種語言，也能用 REST 呼叫。

## 練習

1. 把 schema 裡的 embedding 模型換成別的 OpenAI 模型，重新匯入，看搜尋結果有沒有變。
2. 改 schema，讓 `url` 也一起向量化（或只向量化 `title`），比較搜尋結果的差異。
3. 把搜尋 query 換成你自己的問題，並調整回傳筆數，看排名前幾名的文章合不合理。
