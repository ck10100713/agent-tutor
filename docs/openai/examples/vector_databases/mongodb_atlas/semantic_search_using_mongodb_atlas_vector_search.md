---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/mongodb_atlas/semantic_search_using_mongodb_atlas_vector_search.ipynb
---

# 用 MongoDB Atlas Vector Search 和 OpenAI 做語意搜尋

> 原文：[examples/vector_databases/mongodb_atlas/semantic_search_using_mongodb_atlas_vector_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/mongodb_atlas/semantic_search_using_mongodb_atlas_vector_search.ipynb)



## 這篇在做什麼
用 OpenAI embedding 和 MongoDB Atlas Vector Search 做一個語意搜尋應用。流程是替 sample_mflix 電影資料的 plot 欄位產生 embedding 存回資料庫，建立 vector search index，再用 `$vectorSearch` 找出劇情語意相近的電影。

## 學完你會
- 用 OpenAI embeddings endpoint 為文件欄位產生 embedding，並寫回 MongoDB
- 用 Atlas UI 或 pymongo 建立 vector search index
- 用查詢文字找出語意相近而不是關鍵字相符的電影

## 開跑前
- MongoDB Atlas cluster（免費的就可以，版本需 6.0.11 以上才有 `$vectorSearch`；用 pymongo 建 index 需要 7.0+）
- 在 Atlas 載入 sample dataset（用到 `sample_mflix`）
- OpenAI API key

這個 notebook 示範怎麼用 OpenAI 和 [MongoDB Atlas vector search](https://www.mongodb.com/products/platform/atlas-vector-search) 做一個語意搜尋應用。

```python
!pip install pymongo openai
```

??? note "輸出"

    ```text
    Collecting pymongo
      Downloading pymongo-4.6.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (677 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 677.1/677.1 kB 10.3 MB/s eta 0:00:00
    [?25hCollecting openai
      Downloading openai-1.3.3-py3-none-any.whl (220 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 220.3/220.3 kB 24.4 MB/s eta 0:00:00
    [?25hCollecting dnspython<3.0.0,>=1.16.0 (from pymongo)
      Downloading dnspython-2.4.2-py3-none-any.whl (300 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 300.4/300.4 kB 29.0 MB/s eta 0:00:00
    [?25hRequirement already satisfied: anyio<4,>=3.5.0 in /usr/local/lib/python3.10/dist-packages (from openai) (3.7.1)
    Requirement already satisfied: distro<2,>=1.7.0 in /usr/lib/python3/dist-packages (from openai) (1.7.0)
    Collecting httpx<1,>=0.23.0 (from openai)
      Downloading httpx-0.25.1-py3-none-any.whl (75 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 75.0/75.0 kB 9.8 MB/s eta 0:00:00
    [?25hRequirement already satisfied: pydantic<3,>=1.9.0 in /usr/local/lib/python3.10/dist-packages (from openai) (1.10.13)
    Requirement already satisfied: tqdm>4 in /usr/local/lib/python3.10/dist-packages (from openai) (4.66.1)
    Requirement already satisfied: typing-extensions<5,>=4.5 in /usr/local/lib/python3.10/dist-packages (from openai) (4.5.0)
    Requirement already satisfied: idna>=2.8 in /usr/local/lib/python3.10/dist-packages (from anyio<4,>=3.5.0->openai) (3.4)
    Requirement already satisfied: sniffio>=1.1 in /usr/local/lib/python3.10/dist-packages (from anyio<4,>=3.5.0->openai) (1.3.0)
    Requirement already satisfied: exceptiongroup in /usr/local/lib/python3.10/dist-packages (from anyio<4,>=3.5.0->openai) (1.1.3)
    Requirement already satisfied: certifi in /usr/local/lib/python3.10/dist-packages (from httpx<1,>=0.23.0->openai) (2023.7.22)
    Collecting httpcore (from httpx<1,>=0.23.0->openai)
      Downloading httpcore-1.0.2-py3-none-any.whl (76 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 76.9/76.9 kB 7.9 MB/s eta 0:00:00
    [?25hCollecting h11<0.15,>=0.13 (from httpcore->httpx<1,>=0.23.0->openai)
      Downloading h11-0.14.0-py3-none-any.whl (58 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 58.3/58.3 kB 6.8 MB/s eta 0:00:00
    [?25hInstalling collected packages: h11, dnspython, pymongo, httpcore, httpx, openai
    ERROR: pip's dependency resolver does not currently take into account all the packages that are installed. This behaviour is the source of the following dependency conflicts.
    llmx 0.0.15a0 requires cohere, which is not installed.
    llmx 0.0.15a0 requires tiktoken, which is not installed.
    Successfully installed dnspython-2.4.2 h11-0.14.0 httpcore-1.0.2 httpx-0.25.1 openai-1.3.3 pymongo-4.6.0
    ```


需要兩個前置條件：

1.   **MongoDB Atlas cluster**：要建立永久免費的 MongoDB Atlas cluster，如果還沒有帳號，先建立一個 MongoDB Atlas 帳號。到 [MongoDB Atlas 網站](https://www.mongodb.com/atlas/database) 點「Register」。再到 [MongoDB Atlas](https://account.mongodb.com/account/login) 儀表板設定 cluster。想在 aggregation pipeline 用 `$vectorSearch` operator，Atlas 版本要 6.0.11 或更高。這份教學用免費 cluster 就能做。設定部署時，會要你設定資料庫使用者和網路連線規則。請把使用者名稱和密碼存在安全的地方，並設好正確的 IP 位址規則，cluster 才能正常連線。如果需要更多入門協助，可以看我們的 [MongoDB Atlas 教學](https://www.mongodb.com/basics/mongodb-atlas-tutorial)。

2. **OpenAI API key**：要建立 OpenAI key，需要先建立帳號。有帳號後，到 [OpenAI platform](https://platform.openai.com/)。點右上角的個人頭像打開下拉選單，選「View API keys」。


```python
import getpass

MONGODB_ATLAS_CLUSTER_URI = getpass.getpass("MongoDB Atlas Cluster URI:")
OPENAI_API_KEY = getpass.getpass("OpenAI API Key:")
```

??? note "輸出"

    ```text
    MongoDB Atlas Cluster URI:··········
    OpenAI API Key:··········
    ```

注意：執行完上面的步驟後，會提示你輸入憑證。

這份教學用 [MongoDB sample dataset](https://www.mongodb.com/docs/atlas/sample-data/)。用 Atlas UI 載入 sample dataset。我們會用「sample_mflix」資料庫，裡面有「movies」collection，每份文件都有 title、plot、genres、cast、directors 等欄位。


```python
import openai
import pymongo

client = pymongo.MongoClient(MONGODB_ATLAS_CLUSTER_URI)
db = client.sample_mflix
collection = db.movies

openai.api_key = OPENAI_API_KEY
```

```python
ATLAS_VECTOR_SEARCH_INDEX_NAME = "default"
EMBEDDING_FIELD_NAME = "embedding_openai_nov19_23"
```

# Step 2：設定產生 embedding 的 function

```python
model = "text-embedding-3-small"
def generate_embedding(text: str) -> list[float]:
    return openai.embeddings.create(input = [text], model=model).data[0].embedding
```

# Step 3：建立並儲存 embedding

sample_mflix.movies 這個 sample dataset 的每份文件對應一部電影；我們會對「plot」欄位的資料產生向量 embedding，並存進資料庫。用 OpenAI embeddings endpoint 產生向量 embedding，是做「依意圖」相似度搜尋的必要步驟。

```python
from pymongo import ReplaceOne

# Update the collection with the embeddings
requests = []

for doc in collection.find({'plot':{"$exists": True}}).limit(500):
  doc[EMBEDDING_FIELD_NAME] = generate_embedding(doc['plot'])
  requests.append(ReplaceOne({'_id': doc['_id']}, doc))

collection.bulk_write(requests)
```

??? note "輸出"

    ```text
    BulkWriteResult({'writeErrors': [], 'writeConcernErrors': [], 'nInserted': 0, 'nUpserted': 0, 'nMatched': 50, 'nModified': 50, 'nRemoved': 0, 'upserted': []}, acknowledged=True)
    ```

執行上面的步驟後，「movies」collection 裡的文件，除了原本就有的 title、plot、genres、cast、directors 等欄位，還會多一個「embedding」欄位，名稱由 `EMBEDDING_FIELD_NAME` 變數定義。

注意：為了節省時間，我們只處理 500 份文件。如果要對 sample_mflix 資料庫整個 23,000 多份文件做，會花上一段時間。另一個做法是用 [sample_mflix.embedded_movies collection](https://www.mongodb.com/docs/atlas/sample-data/sample-mflix/#sample_mflix.embedded_movies)，它已經預先有 `plot_embedding` 欄位，裡面是用 OpenAI 的 `text-embedding-3-small` embedding 模型產生的 embedding，可以搭配 Atlas Search 的 vector search 功能使用。




# Step 4：建立 vector search index

我們會在這個 collection 上建立 Atlas Vector Search Index，讓我們可以做近似 KNN 搜尋，語意搜尋就是靠它。
我們會介紹兩種建立 index 的方式：Atlas UI 和 MongoDB python driver。

（選用）[文件：Create a Vector Search Index ](https://www.mongodb.com/docs/atlas/atlas-search/field-types/knn-vector/)

現在到 [Atlas UI](https://cloud.mongodb.com)，照[這裡](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-tutorial/#create-the-atlas-vector-search-index)的步驟建立 Atlas Vector Search index。'dimensions' 欄位的值 1536，對應 OpenAI text-embedding-ada-002。

在 Atlas UI 的 JSON editor 裡使用下面的定義。

```
{
  "mappings": {
    "dynamic": true,
    "fields": {
      "embedding": {
        "dimensions": 1536,
        "similarity": "dotProduct",
        "type": "knnVector"
      }
    }
  }
}
```

（選用）另外，也可以用 [pymongo driver 以程式方式建立這些 vector search index](https://pymongo.readthedocs.io/en/stable/api/pymongo/collection.html#pymongo.collection.Collection.create_search_index)
下面 cell 裡的 python 指令會建立 index（這只在最新版的 MongoDB Python Driver 和 MongoDB server 7.0+ 的 Atlas cluster 上有效）。

```python
collection.create_search_index(
    {"definition":
        {"mappings": {"dynamic": True, "fields": {
            EMBEDDING_FIELD_NAME : {
                "dimensions": 1536,
                "similarity": "dotProduct",
                "type": "knnVector"
                }}}},
     "name": ATLAS_VECTOR_SEARCH_INDEX_NAME
    }
)
```

??? note "輸出"

    ```text
    'default'
    ```

# Step 5：查詢你的資料

這裡的查詢結果，找的是劇情在語意上跟查詢字串相近的電影，而不是靠關鍵字搜尋。

（選用）[文件：Run Vector Search Queries](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-stage/)

```python

def query_results(query, k):
  results = collection.aggregate([
    {
        '$vectorSearch': {
            "index": ATLAS_VECTOR_SEARCH_INDEX_NAME,
            "path": EMBEDDING_FIELD_NAME,
            "queryVector": generate_embedding(query),
            "numCandidates": 50,
            "limit": 5,
        }
    }
    ])
  return results
```

```python
query="imaginary characters from outerspace at war with earthlings"
movies = query_results(query, 5)

for movie in movies:
    print(f'Movie Name: {movie["title"]},\nMovie Plot: {movie["plot"]}\n')
```

## 重點整理
- 語意搜尋比對的是意思，不是關鍵字，靠的是把文字轉成 embedding 向量
- 文件要先用 OpenAI embeddings endpoint 產生向量，並存在文件的一個欄位裡
- Vector search index 的 `dimensions` 必須和 embedding 模型的向量維度一致（範例是 1536）
- 查詢時要把查詢文字也轉成 embedding，再交給 `$vectorSearch` 找最相近的文件

## 練習
1. 把查詢字串換成你自己描述的一段劇情，看回傳的電影是不是語意相近。
2. 把處理的文件數從 500 改成 100，重建 embedding，比較搜尋結果的差別。
3. 改用 `sample_mflix.embedded_movies` collection 的 `plot_embedding` 欄位，調整 index 定義和查詢，跳過自己產生 embedding 的步驟。
