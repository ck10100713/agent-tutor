---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/qdrant/Using_Qdrant_for_embeddings_search.ipynb
---

# 用 Qdrant 做 embedding 搜尋

> 原文：[examples/vector_databases/qdrant/Using_Qdrant_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/qdrant/Using_Qdrant_for_embeddings_search.ipynb)

## 這篇在做什麼

走一遍簡單流程：下載資料、做 embedding，然後用向量資料庫 Qdrant 建立索引並搜尋。Qdrant 用本機 Docker 跑，collection 裡同時存標題和內文兩組向量，最後用語意搜尋驗證結果。

## 學完你會

- 用 Docker 在本機啟動 Qdrant，並用 `qdrant-client` 連線
- 建立同時有 title 與 content 兩組向量、並帶 payload（id、title、url）的 collection
- 用 `vector_name` 切換標題或內文搜尋，對查詢做語意搜尋

## 開跑前

- 需要 `OPENAI_API_KEY`，查詢時要算 embedding
- 需要 Docker（Docker 記憶體可能要調到 8GB 以上，否則 Qdrant 可能出現 `7 Killed`）
- 範例用的是事先備好的 embedding 資料，查詢必須用 text-embedding-ada-002


這個 notebook 帶你走一個簡單的流程：下載一些資料、做 embedding，然後用幾個向量資料庫建立索引並搜尋。這是客戶常見的需求：他們想在安全的環境裡，把我們的 embedding 連同自己的資料存起來並搜尋，以支援聊天機器人、主題建模等正式上線的使用情境。

### 什麼是向量資料庫

向量資料庫是專門儲存、管理和搜尋 embedding 向量的資料庫。近年來，隨著 AI 在自然語言、影像辨識等非結構化資料上越來越有效，用 embedding 把非結構化資料（文字、音訊、影片等）編碼成向量，交給機器學習模型使用的做法急遽增加。向量資料庫成了企業提供並擴展這些使用情境的有效方案。

### 為什麼要用向量資料庫

向量資料庫讓企業能把我們在這個 repo 分享的許多 embedding 使用情境（例如問答、聊天機器人和推薦服務），放進安全、可擴展的環境裡使用。我們很多客戶用 embedding 在小規模解決了問題，但效能和安全性擋住了他們上線。我們認為向量資料庫是解決這點的關鍵元件，這份指南會帶你走過基本流程：對文字資料做 embedding、存進向量資料庫，並用它做語意搜尋。


### Demo 流程
demo 流程是：
- **設定**：匯入套件並設定必要變數
- **載入資料**：載入資料集，並用 OpenAI embedding 做 embedding
- **Qdrant**
    - *設定*：這裡設定 Qdrant 的 Python client。更多細節看[這裡](https://github.com/qdrant/qdrant_client)
    - *索引資料*：建立一個 collection，帶有 __titles__ 和 __content__ 的向量
    - *搜尋資料*：跑幾個搜尋來確認運作正常

跑完這個 notebook，你應該對向量資料庫的設定和使用有基本了解，可以繼續做更複雜、用到我們 embedding 的使用情境。

## 設定

匯入需要的函式庫，並設定想用的 embedding 模型。

```python
# We'll need to install Qdrant client
!pip install qdrant-client
```

```python
import openai
import pandas as pd
from ast import literal_eval
import qdrant_client # Qdrant's client library for Python

# This can be changed to the embedding model of your choice. Make sure its the same model that is used for generating embeddings
EMBEDDING_MODEL = "text-embedding-ada-002"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## 載入資料

這一節載入我們在這次課程之前就準備好的、已完成 embedding 的資料。

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
    'vector_database_wikipedia_articles_embedded (10).zip'
    ```

```python
import zipfile
with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip","r") as zip_ref:
    zip_ref.extractall("../data")
```

```python
article_df = pd.read_csv('../data/vector_database_wikipedia_articles_embedded.csv')
```

```python
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

```python
# Read vectors from strings back into a list
article_df['title_vector'] = article_df.title_vector.apply(literal_eval)
article_df['content_vector'] = article_df.content_vector.apply(literal_eval)

# Set vector_id to be a string
article_df['vector_id'] = article_df['vector_id'].apply(str)
```

```python
article_df.info(show_counts=True)
```

??? note "輸出"

    ```text
    <class 'pandas.core.frame.DataFrame'>
    RangeIndex: 25000 entries, 0 to 24999
    Data columns (total 7 columns):
     #   Column          Non-Null Count  Dtype 
    ---  ------          --------------  ----- 
     0   id              25000 non-null  int64 
     1   url             25000 non-null  object
     2   title           25000 non-null  object
     3   text            25000 non-null  object
     4   title_vector    25000 non-null  object
     5   content_vector  25000 non-null  object
     6   vector_id       25000 non-null  object
    dtypes: int64(1), object(6)
    memory usage: 1.3+ MB
    ```

## Qdrant

**[Qdrant](https://qdrant.tech/)** 是用 Rust 寫的高效能向量搜尋資料庫。它有地端和雲端版本，這個例子我們用本機部署模式。

整個設定需要：
- 啟動一個本機的 Qdrant 實例
- 設定 collection 並把資料存進去
- 用一些查詢試試看

### 設定

本機部署我們用 Docker，依照 Qdrant 文件：https://qdrant.tech/documentation/quick_start/。Qdrant 只需要一個 container，不過這個 repo 的 `./qdrant/docker-compose.yaml` 有一份 docker-compose.yaml 範例。

你可以切到這個目錄並執行 `docker-compose up -d `，在本機啟動 Qdrant 實例。

> 你可能需要把 Docker 的記憶體上限調到 8GB 以上，不然 Qdrant 可能執行失敗，出現類似 `7 Killed` 的錯誤訊息。


```python
! docker compose up -d
```

??? note "輸出"

    ```text
    [1A[1B[0G[?25l[+] Running 1/0
     ✔ Container qdrant-qdrant-1  Running                                      0.0s 
    [?25h
    ```

```python
qdrant = qdrant_client.QdrantClient(host="localhost", port=6333)
```

```python
qdrant.get_collections()
```

??? note "輸出"

    ```text
    CollectionsResponse(collections=[CollectionDescription(name='Articles')])
    ```

### 索引資料

Qdrant 把資料存在 __collection__ 裡，每個物件至少由一個向量描述，還可以附帶稱為 __payload__ 的額外 metadata。我們的 collection 叫 **Articles**，每個物件由 **title** 和 **content** 兩組向量描述。

我們會使用官方的 [qdrant-client](https://github.com/qdrant/qdrant_client) 套件，它已經內建所有工具方法。

```python
from qdrant_client.http import models as rest
```

```python
# Get the vector size from the first row to set up the collection
vector_size = len(article_df['content_vector'][0])

# Set up the collection with the vector configuration. You need to declare the vector size and distance metric for the collection. Distance metric enables vector database to index and search vectors efficiently.
qdrant.recreate_collection(
    collection_name='Articles',
    vectors_config={
        'title': rest.VectorParams(
            distance=rest.Distance.COSINE,
            size=vector_size,
        ),
        'content': rest.VectorParams(
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
vector_size = len(article_df['content_vector'][0])

qdrant.recreate_collection(
    collection_name='Articles',
    vectors_config={
        'title': rest.VectorParams(
            distance=rest.Distance.COSINE,
            size=vector_size,
        ),
        'content': rest.VectorParams(
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

除了在 `vector` 下定義的向量設定，我們也可以定義 `payload` 設定。payload 是選填欄位，讓你在向量旁邊存額外的 metadata。這裡我們要存文章的 `id`、`title` 和 `url`。搜尋結果會從 payload 回傳最近文章的標題，所以我們也能把文章的 URL（metadata 的一部分）提供給使用者。

```python
from qdrant_client.models import PointStruct # Import the PointStruct to store the vector and payload
from tqdm import tqdm # Library to show the progress bar 

# Populate collection with vectors using tqdm to show progress
for k, v in tqdm(article_df.iterrows(), desc="Upserting articles", total=len(article_df)):
    try:
        qdrant.upsert(
            collection_name='Articles',
            points=[
                PointStruct(
                    id=k,
                    vector={'title': v['title_vector'], 
                            'content': v['content_vector']},
                    payload={
                        'id': v['id'],
                        'title': v['title'],
                        'url': v['url']
                    }
                )
            ]
        )
    except Exception as e:
        print(f"Failed to upsert row {k}: {v}")
        print(f"Exception: {e}")
```

??? note "輸出"

    ```text
    Upserting articles: 100%|█████████████████████████████████████████████████████████████████████████████████████| 25000/25000 [02:52<00:00, 144.82it/s]
    ```

```python
# Check the collection size to make sure all the points have been stored
qdrant.count(collection_name='Articles')
```

??? note "輸出"

    ```text
    CountResult(count=25000)
    ```

### 搜尋資料

資料放進 Qdrant 後，就可以對 collection 查詢最近的向量。我們可以多給一個 `vector_name` 參數，在依標題或依內文搜尋之間切換。請確定用 text-embedding-ada-002 模型，因為檔案裡的原始 embedding 就是用這個模型建立的。

```python
def query_qdrant(query, collection_name, vector_name='title', top_k=20):

    # Creates embedding vector from user query
    embedded_query = openai.embeddings.create(
        input=query,
        model=EMBEDDING_MODEL,
    ).data[0].embedding # We take the first embedding from the list
    
    query_results = qdrant.search(
        collection_name=collection_name,
        query_vector=(
            vector_name, embedded_query
        ),
        limit=top_k, 
        query_filter=None
    )
    
    return query_results
```

```python
query_results = query_qdrant('modern art in Europe', 'Articles', 'title')
for i, article in enumerate(query_results):
    print(f'{i + 1}. {article.payload["title"]}, URL: {article.payload["url"]} (Score: {round(article.score, 3)})')
```

??? note "輸出"

    ```text
    1. Museum of Modern Art, URL: https://simple.wikipedia.org/wiki/Museum%20of%20Modern%20Art (Score: 0.875)
    2. Western Europe, URL: https://simple.wikipedia.org/wiki/Western%20Europe (Score: 0.867)
    3. Renaissance art, URL: https://simple.wikipedia.org/wiki/Renaissance%20art (Score: 0.864)
    4. Pop art, URL: https://simple.wikipedia.org/wiki/Pop%20art (Score: 0.86)
    5. Northern Europe, URL: https://simple.wikipedia.org/wiki/Northern%20Europe (Score: 0.855)
    6. Hellenistic art, URL: https://simple.wikipedia.org/wiki/Hellenistic%20art (Score: 0.853)
    7. Modernist literature, URL: https://simple.wikipedia.org/wiki/Modernist%20literature (Score: 0.847)
    8. Art film, URL: https://simple.wikipedia.org/wiki/Art%20film (Score: 0.843)
    9. Central Europe, URL: https://simple.wikipedia.org/wiki/Central%20Europe (Score: 0.843)
    10. European, URL: https://simple.wikipedia.org/wiki/European (Score: 0.841)
    11. Art, URL: https://simple.wikipedia.org/wiki/Art (Score: 0.841)
    12. Byzantine art, URL: https://simple.wikipedia.org/wiki/Byzantine%20art (Score: 0.841)
    13. Postmodernism, URL: https://simple.wikipedia.org/wiki/Postmodernism (Score: 0.84)
    14. Eastern Europe, URL: https://simple.wikipedia.org/wiki/Eastern%20Europe (Score: 0.839)
    15. Cubism, URL: https://simple.wikipedia.org/wiki/Cubism (Score: 0.839)
    16. Europe, URL: https://simple.wikipedia.org/wiki/Europe (Score: 0.839)
    17. Impressionism, URL: https://simple.wikipedia.org/wiki/Impressionism (Score: 0.838)
    18. Bauhaus, URL: https://simple.wikipedia.org/wiki/Bauhaus (Score: 0.838)
    19. Surrealism, URL: https://simple.wikipedia.org/wiki/Surrealism (Score: 0.837)
    20. Expressionism, URL: https://simple.wikipedia.org/wiki/Expressionism (Score: 0.837)
    ```

```python
# This time we'll query using content vector
query_results = query_qdrant('Famous battles in Scottish history', 'Articles', 'content')
for i, article in enumerate(query_results):
    print(f'{i + 1}. {article.payload["title"]}, URL: {article.payload["url"]} (Score: {round(article.score, 3)})')
```

??? note "輸出"

    ```text
    1. Battle of Bannockburn, URL: https://simple.wikipedia.org/wiki/Battle%20of%20Bannockburn (Score: 0.869)
    2. Wars of Scottish Independence, URL: https://simple.wikipedia.org/wiki/Wars%20of%20Scottish%20Independence (Score: 0.861)
    3. 1651, URL: https://simple.wikipedia.org/wiki/1651 (Score: 0.852)
    4. First War of Scottish Independence, URL: https://simple.wikipedia.org/wiki/First%20War%20of%20Scottish%20Independence (Score: 0.85)
    5. Robert I of Scotland, URL: https://simple.wikipedia.org/wiki/Robert%20I%20of%20Scotland (Score: 0.846)
    6. 841, URL: https://simple.wikipedia.org/wiki/841 (Score: 0.844)
    7. 1716, URL: https://simple.wikipedia.org/wiki/1716 (Score: 0.844)
    8. 1314, URL: https://simple.wikipedia.org/wiki/1314 (Score: 0.837)
    9. 1263, URL: https://simple.wikipedia.org/wiki/1263 (Score: 0.836)
    10. William Wallace, URL: https://simple.wikipedia.org/wiki/William%20Wallace (Score: 0.835)
    11. Stirling, URL: https://simple.wikipedia.org/wiki/Stirling (Score: 0.831)
    12. 1306, URL: https://simple.wikipedia.org/wiki/1306 (Score: 0.831)
    13. 1746, URL: https://simple.wikipedia.org/wiki/1746 (Score: 0.83)
    14. 1040s, URL: https://simple.wikipedia.org/wiki/1040s (Score: 0.828)
    15. 1106, URL: https://simple.wikipedia.org/wiki/1106 (Score: 0.827)
    16. 1304, URL: https://simple.wikipedia.org/wiki/1304 (Score: 0.826)
    17. David II of Scotland, URL: https://simple.wikipedia.org/wiki/David%20II%20of%20Scotland (Score: 0.825)
    18. Braveheart, URL: https://simple.wikipedia.org/wiki/Braveheart (Score: 0.824)
    19. 1124, URL: https://simple.wikipedia.org/wiki/1124 (Score: 0.824)
    20. July 27, URL: https://simple.wikipedia.org/wiki/July%2027 (Score: 0.823)
    ```

## 重點整理

- 向量資料庫專門存放、管理並搜尋 embedding，補足小規模實驗在效能和安全上的缺口。
- Qdrant 的資料單位是 collection，每個物件有一到多組向量，外加 payload 存 metadata。
- 同一個物件可以有多組命名向量（這裡是 title 和 content），查詢時用 `vector_name` 指定要搜哪組。
- 查詢向量必須用建立索引時的同一個 embedding 模型，否則距離沒有意義。
- 本機部署用 Docker 就能起來，記憶體不夠會被系統殺掉。

## 練習

1. 把搜尋的 `vector_name` 從 title 換成 content，用同一個查詢比較兩邊的結果。
2. 把搜尋回傳的筆數（limit）改成 10，並在輸出裡多印出 payload 的 url。
3. 在建立 collection 的 payload 設定多加一個欄位（例如文章長度），重新匯入資料後，把它一起印在搜尋結果裡。
