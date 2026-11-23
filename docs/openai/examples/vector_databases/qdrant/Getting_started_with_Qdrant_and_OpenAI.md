---
translated: true
source: examples/vector_databases/qdrant/Getting_started_with_Qdrant_and_OpenAI.ipynb
---
# 用 Qdrant 當 OpenAI embedding 的向量資料庫

> 原文：[examples/vector_databases/qdrant/Getting_started_with_Qdrant_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/qdrant/Getting_started_with_Qdrant_and_OpenAI.ipynb)

## 這篇在做什麼
一步步示範把 Qdrant（用 Rust 寫的高效能向量搜尋資料庫）當向量資料庫，存 OpenAI embedding 並做最近鄰搜尋。資料用事先算好的 Wikipedia embedding，Qdrant 跑在本機。

## 學完你會
- 用 Docker 啟動本機 Qdrant，並用 `qdrant-client` 連線
- 建一個同時有 title 和 content 兩種向量的 collection，並把資料載入
- 把 query 轉成 embedding，用 `vector_name` 切換 title 或 content 搜尋

## 開跑前
- 本機有 Docker 可以啟動 Qdrant server
- OpenAI API key，設成環境變數 `OPENAI_API_KEY`

這個 notebook 帶你一步步用 **`Qdrant`** 當 OpenAI embedding 的向量資料庫。[Qdrant](https://qdrant.tech) 是用 Rust 寫的高效能向量搜尋資料庫，提供 RESTful 和 gRPC API 來管理 embedding。官方有 Python 的 [qdrant-client](https://github.com/qdrant/qdrant_client)，方便整合進你的應用。

完整流程是：
1. 使用 OpenAI API 事先算好的 embedding。
2. 把 embedding 存到本機的 Qdrant instance。
3. 用 OpenAI API 把文字 query 轉成 embedding。
4. 用 Qdrant 在建好的 collection 裡做最近鄰搜尋。

### 什麼是 Qdrant

[Qdrant](https://qdrant.tech) 是開源向量資料庫，可以把 neural embedding 連同 metadata（也就是 [payload](https://qdrant.tech/documentation/payload/)）一起存。payload 不只能保存某個 point 的額外屬性，也能拿來過濾。[Qdrant](https://qdrant.tech) 有獨特的過濾機制，直接內建在向量搜尋階段，所以非常有效率。

### 部署方式

[Qdrant](https://qdrant.tech) 有多種啟動方式，可以依應用的目標負載選擇託管方式：

- 本機或地端，用 Docker container
- 在 Kubernetes cluster，用 [Helm chart](https://github.com/qdrant/qdrant-helm)
- 用 [Qdrant Cloud](https://cloud.qdrant.io/)

### 整合

[Qdrant](https://qdrant.tech) 同時提供 RESTful 和 gRPC API，不管你用什麼程式語言都很容易整合。另外也有針對主流語言的官方 client，如果你用 Python，[Python Qdrant client library](https://github.com/qdrant/qdrant_client) 大概是最好的選擇。

```python
! docker compose up -d
```

??? note "輸出"

    ```text
    [1A[1B[0G[?25l[+] Running 1/0
     ✔ Container qdrant-qdrant-1  Running                                      0.0s 
    [?25h
    ```

可以用簡單的 curl 指令確認 server 是否啟動成功：

```python
! curl http://localhost:6333
```

??? note "輸出"

    ```text
    {"title":"qdrant - vector search engine","version":"1.3.0"}
    ```

### 安裝套件

這個 notebook 當然需要 `openai` 和 `qdrant-client`，還會用到一些其他函式庫。下面的指令一次裝好：


```python
! pip install openai qdrant-client pandas wget
```

### 準備 OpenAI API key

OpenAI API key 用來把文件和 query 向量化。

沒有 OpenAI API key 的話，可以到 [https://beta.openai.com/account/api-keys](https://beta.openai.com/account/api-keys) 取得。

拿到 key 之後，執行下面的指令把它加到環境變數 `OPENAI_API_KEY`：

```python
! export OPENAI_API_KEY="your API key"
```

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

## 連線到 Qdrant

用官方 Python 函式庫連到運行中的 Qdrant server 很簡單：

```python
import qdrant_client

client = qdrant_client.QdrantClient(
    host="localhost",
    prefer_grpc=True,
)
```

可以執行任何可用的方法來測試連線：

```python
client.get_collections()
```

??? note "輸出"

    ```text
    CollectionsResponse(collections=[])
    ```

## 載入資料

這一節載入這次練習之前就準備好的資料，所以你不必花自己的額度重算 Wikipedia 文章的 embedding。

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
    'vector_database_wikipedia_articles_embedded (9).zip'
    ```

下載下來的檔案要再解壓縮：

```python
import zipfile

with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip","r") as zip_ref:
    zip_ref.extractall("../data")
```

最後從提供的 CSV 檔載入：

```python
import pandas as pd

from ast import literal_eval

article_df = pd.read_csv('../data/vector_database_wikipedia_articles_embedded.csv')
# Read vectors from strings back into a list
article_df["title_vector"] = article_df.title_vector.apply(literal_eval)
article_df["content_vector"] = article_df.content_vector.apply(literal_eval)
article_df.head()
```

??? note "輸出"

    ```text
       id                                       url   title  \
    0   1   https://simple.wikipedia.org/wiki/April   April   
    1   2  https://simple.wikipedia.org/wiki/August  August   
    2   6     https://simple.wikipedia.org/wiki/Art     Art   
    3   8       https://simple.wikipedia.org/wiki/A       A   
    4   9     https://simple.wikipedia.org/wiki/Air     Air   

                                                    text  \
    0  April is the fourth month of the year in the J...   
    1  August (Aug.) is the eighth month of the year ...   
    2  Art is a creative activity that expresses imag...   
    3  A or a is the first letter of the English alph...   
    4  Air refers to the Earth's atmosphere. Air is a...   

                                            title_vector  \
    0  [0.001009464613161981, -0.020700545981526375, ...   
    1  [0.0009286514250561595, 0.000820168002974242, ...   
    2  [0.003393713850528002, 0.0061537534929811954, ...   
    3  [0.0153952119871974, -0.013759135268628597, 0....   
    4  [0.02224554680287838, -0.02044147066771984, -0...   

                                          content_vector  vector_id  
    0  [-0.011253940872848034, -0.013491976074874401,...          0  
    1  [0.0003609954728744924, 0.007262262050062418, ...          1  
    2  [-0.004959689453244209, 0.015772193670272827, ...          2  
    3  [0.024894846603274345, -0.022186409682035446, ...          3  
    4  [0.021524671465158463, 0.018522677943110466, -...          4
    ```

## 資料建索引

Qdrant 把資料存在 __collection__ 裡，每個物件至少由一個向量描述，也可以帶額外的 metadata，叫 __payload__。我們的 collection 叫 **Articles**，每個物件同時有 **title** 和 **content** 向量。Qdrant 不需要事先設定任何 schema，所以只要簡單設定，就能自由把 point 放進 collection。

我們先建一個 collection，再把預先算好的 embedding 填進去。

```python
from qdrant_client.http import models as rest

vector_size = len(article_df["content_vector"][0])

client.create_collection(
    collection_name="Articles",
    vectors_config={
        "title": rest.VectorParams(
            distance=rest.Distance.COSINE,
            size=vector_size,
        ),
        "content": rest.VectorParams(
            distance=rest.Distance.COSINE,
            size=vector_size,
        ),
    }
)
```

??? note "輸出"

    ```text
    True
    ```

```python
client.upsert(
    collection_name="Articles",
    points=[
        rest.PointStruct(
            id=k,
            vector={
                "title": v["title_vector"],
                "content": v["content_vector"],
            },
            payload=v.to_dict(),
        )
        for k, v in article_df.iterrows()
    ],
)
```

??? note "輸出"

    ```text
    UpdateResult(operation_id=0, status=<UpdateStatus.COMPLETED: 'completed'>)
    ```

```python
# Check the collection size to make sure all the points have been stored
client.count(collection_name="Articles")
```

??? note "輸出"

    ```text
    CountResult(count=25000)
    ```

## 搜尋資料

資料放進 Qdrant 之後，就能查詢 collection 裡最接近的向量。可以多帶一個 `vector_name` 參數，在 title 和 content 搜尋之間切換。因為預先算好的 embedding 是用 OpenAI 的 `text-embedding-ada-002` 模型產生的，搜尋時也必須用同一個模型。


```python
from openai import OpenAI

openai_client = OpenAI()

def query_qdrant(query, collection_name, vector_name="title", top_k=20):
    # Creates embedding vector from user query
    embedded_query = openai_client.embeddings.create(
        input=query,
        model="text-embedding-ada-002",
    ).data[0].embedding

    query_results = client.search(
        collection_name=collection_name,
        query_vector=(
            vector_name, embedded_query
        ),
        limit=top_k,
    )

    return query_results
```

```python
query_results = query_qdrant("modern art in Europe", "Articles")
for i, article in enumerate(query_results):
    print(f"{i + 1}. {article.payload['title']} (Score: {round(article.score, 3)})")
```

??? note "輸出"

    ```text
    1. Museum of Modern Art (Score: 0.875)
    2. Western Europe (Score: 0.867)
    3. Renaissance art (Score: 0.864)
    4. Pop art (Score: 0.86)
    5. Northern Europe (Score: 0.855)
    6. Hellenistic art (Score: 0.853)
    7. Modernist literature (Score: 0.847)
    8. Art film (Score: 0.843)
    9. Central Europe (Score: 0.843)
    10. European (Score: 0.841)
    11. Art (Score: 0.841)
    12. Byzantine art (Score: 0.841)
    13. Postmodernism (Score: 0.84)
    14. Eastern Europe (Score: 0.839)
    15. Cubism (Score: 0.839)
    16. Europe (Score: 0.839)
    17. Impressionism (Score: 0.838)
    18. Bauhaus (Score: 0.838)
    19. Surrealism (Score: 0.837)
    20. Expressionism (Score: 0.837)
    ```

```python
# This time we'll query using content vector
query_results = query_qdrant("Famous battles in Scottish history", "Articles", "content")
for i, article in enumerate(query_results):
    print(f"{i + 1}. {article.payload['title']} (Score: {round(article.score, 3)})")
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn (Score: 0.869)
    2. Wars of Scottish Independence (Score: 0.861)
    3. 1651 (Score: 0.852)
    4. First War of Scottish Independence (Score: 0.85)
    5. Robert I of Scotland (Score: 0.846)
    6. 841 (Score: 0.844)
    7. 1716 (Score: 0.844)
    8. 1314 (Score: 0.837)
    9. 1263 (Score: 0.836)
    10. William Wallace (Score: 0.835)
    11. Stirling (Score: 0.831)
    12. 1306 (Score: 0.831)
    13. 1746 (Score: 0.83)
    14. 1040s (Score: 0.828)
    15. 1106 (Score: 0.827)
    16. 1304 (Score: 0.826)
    17. David II of Scotland (Score: 0.825)
    18. Braveheart (Score: 0.824)
    19. 1124 (Score: 0.824)
    20. Second War of Scottish Independence (Score: 0.823)
    ```

## 重點整理
- Qdrant 把向量和 payload（metadata）一起存，payload 可以用來過濾，過濾直接內建在向量搜尋階段。
- 不用事先定 schema，一個 collection 可以用具名向量同時放 title 和 content 兩種 embedding。
- 存和搜的 embedding 模型要一致，這裡是 `text-embedding-ada-002`。
- Qdrant 同時提供 REST 和 gRPC，部署可以用 Docker、Kubernetes 或雲端。

## 練習
1. 換一句自己的 query，分別用 `vector_name` 為 title 和 content 搜尋。
2. 改搜尋回傳的筆數（limit），看結果變化。
3. 在 collection 的 payload 加一個欄位，搜尋時用 payload filter 過濾結果。
