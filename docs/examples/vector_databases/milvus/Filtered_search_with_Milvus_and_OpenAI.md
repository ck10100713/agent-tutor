---
translated: true
source: examples/vector_databases/milvus/Filtered_search_with_Milvus_and_OpenAI.ipynb
---
# 用 Milvus 和 OpenAI 做過濾式搜尋

> 原文：[examples/vector_databases/milvus/Filtered_search_with_Milvus_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/milvus/Filtered_search_with_Milvus_and_OpenAI.ipynb)

## 這篇在做什麼

用 OpenAI 替電影簡介產生 embedding，存進 Milvus，再用語意搜尋找出相關的電影。搜尋時還能加上 metadata 的過濾條件，縮小結果範圍。

## 學完你會

- 用 Docker 啟動 Milvus standalone，並用 `pymilvus` 建立 collection 和 index
- 批次呼叫 OpenAI embedding，連同 title、type、release_year、rating 一起寫進 Milvus
- 用「描述文字加過濾表達式」的查詢，做帶 metadata 條件的向量搜尋

## 開跑前

- 需要 OpenAI API key
- 需要 Docker，用來跑 Milvus（檔案資料夾裡的 `docker-compose.yaml`）
- 這是 notebook 的內容，本機要先裝好下面提到的套件

### 找你的下一部電影

這份 notebook 會用 OpenAI 替電影簡介產生 embedding，再用這些 embedding 在 Milvus 裡找相關的電影。為了縮小搜尋結果、嘗試新東西，我們會用過濾做 metadata 搜尋。這個範例的資料集來自 HuggingFace datasets，有 8 千多筆電影資料。

先下載這份 notebook 需要的套件：
- `openai` 用來跟 OpenAI 的 embedding 服務溝通
- `pymilvus` 用來跟 Milvus server 溝通
- `datasets` 用來下載資料集
- `tqdm` 用來顯示進度條


```python
! pip install openai pymilvus datasets tqdm
```

套件裝好就能開始了。先把 Milvus 服務啟動。要跑的檔案是這個檔案所在資料夾裡的 `docker-compose.yaml`。這個指令會啟動一個 Milvus standalone 實例，我們用它來做這次測試。  

```python
! docker compose up -d
```

??? note "輸出"

    ```text
    E0317 14:06:38.344884000 140704629352640 fork_posix.cc:76]             Other threads are currently calling into gRPC, skipping fork() handlers
    ```

    ```text
    [1A[1B[0G[?25l[+] Running 1/0
     ⠿ Network milvus          Created                                         0.1s
     ⠋ Container milvus-etcd   Creating                                        0.0s
     ⠋ Container milvus-minio  Creating                                        0.0s
    [?25h[1A[1A[1A[1A[0G[?25l[+] Running 1/3
     ⠿ Network milvus          Created                                         0.1s
     ⠙ Container milvus-etcd   Creating                                        0.1s
     ⠙ Container milvus-minio  Creating                                        0.1s
    [?25h[1A[1A[1A[1A[0G[?25l[+] Running 2/3
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-etcd        Starting                                   0.2s
     ⠿ Container milvus-minio       Starting                                   0.2s
     ⠿ Container milvus-standalone  Created                                    0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-etcd        Starting                                   0.3s
     ⠿ Container milvus-minio       Starting                                   0.3s
     ⠿ Container milvus-standalone  Created                                    0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-etcd        Starting                                   0.4s
     ⠿ Container milvus-minio       Starting                                   0.4s
     ⠿ Container milvus-standalone  Created                                    0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-etcd        Starting                                   0.5s
     ⠿ Container milvus-minio       Starting                                   0.5s
     ⠿ Container milvus-standalone  Created                                    0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-etcd        Starting                                   0.6s
     ⠿ Container milvus-minio       Starting                                   0.6s
     ⠿ Container milvus-standalone  Created                                    0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-etcd        Starting                                   0.7s
     ⠿ Container milvus-minio       Starting                                   0.7s
     ⠿ Container milvus-standalone  Created                                    0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
    ... (省略 49 行)
    ```

Milvus 跑起來之後，就可以設定全域變數：
- HOST：Milvus 的主機位址
- PORT：Milvus 的 port 號碼
- COLLECTION_NAME：collection 在 Milvus 裡的名稱
- DIMENSION：embedding 的維度
- OPENAI_ENGINE：要用哪個 embedding 模型
- openai.api_key：你的 OpenAI 帳號 key
- INDEX_PARAM：collection 用的 index 設定
- QUERY_PARAM：搜尋用的參數
- BATCH_SIZE：一次 embed 並插入多少部電影

```python
import openai

HOST = 'localhost'
PORT = 19530
COLLECTION_NAME = 'movie_search'
DIMENSION = 1536
OPENAI_ENGINE = 'text-embedding-3-small'
openai.api_key = 'sk-your_key'

INDEX_PARAM = {
    'metric_type':'L2',
    'index_type':"HNSW",
    'params':{'M': 8, 'efConstruction': 64}
}

QUERY_PARAM = {
    "metric_type": "L2",
    "params": {"ef": 64},
}

BATCH_SIZE = 1000
```

```python
from pymilvus import connections, utility, FieldSchema, Collection, CollectionSchema, DataType

# Connect to Milvus Database
connections.connect(host=HOST, port=PORT)
```

```python
# Remove collection if it already exists
if utility.has_collection(COLLECTION_NAME):
    utility.drop_collection(COLLECTION_NAME)
```

```python
# Create collection which includes the id, title, and embedding.
fields = [
    FieldSchema(name='id', dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name='title', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='type', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='release_year', dtype=DataType.INT64),
    FieldSchema(name='rating', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='description', dtype=DataType.VARCHAR, max_length=64000),
    FieldSchema(name='embedding', dtype=DataType.FLOAT_VECTOR, dim=DIMENSION)
]
schema = CollectionSchema(fields=fields)
collection = Collection(name=COLLECTION_NAME, schema=schema)
```

```python
# Create the index on the collection and load it.
collection.create_index(field_name="embedding", index_params=INDEX_PARAM)
collection.load()
```

## 資料集
Milvus 跑起來之後，就可以開始抓資料。Hugging Face Datasets 是一個存放各種使用者資料集的 hub，這個範例用的是 HuggingLearners 的 netflix-shows 資料集。它包含 8 千多部電影和它們的 metadata。我們要把每一筆簡介 embed，連同 title、type、release_year 和 rating 一起存進 Milvus。

```python
import datasets

# Download the dataset 
dataset = datasets.load_dataset('hugginglearners/netflix-shows', split='train')
```

??? note "輸出"

    ```text
    Found cached dataset csv (/Users/filiphaltmayer/.cache/huggingface/datasets/hugginglearners___csv/hugginglearners--netflix-shows-03475319fc65a05a/0.0.0/6b34fb8fcf56f7c8ba51dc895bfa2bfbe43546f190a60fcf74bb5e8afdcc2317)
    ```

## 插入資料
資料已經在本機了，就可以開始做 embedding 並插入 Milvus。Embedding 函式吃文字，回傳 list 格式的 embedding。

```python
# Simple function that converts the texts to embeddings
def embed(texts):
    embeddings = openai.Embedding.create(
        input=texts,
        engine=OPENAI_ENGINE
    )
    return [x['embedding'] for x in embeddings['data']]
```

下一步才是真正的插入。我們走訪所有項目，累積成 batch，一達到設定的 batch size 就插入。迴圈結束後，如果還有剩下的 batch，就把最後一批也插入。

```python
from tqdm import tqdm

data = [
    [], # title
    [], # type
    [], # release_year
    [], # rating
    [], # description
]

# Embed and insert in batches
for i in tqdm(range(0, len(dataset))):
    data[0].append(dataset[i]['title'] or '')
    data[1].append(dataset[i]['type'] or '')
    data[2].append(dataset[i]['release_year'] or -1)
    data[3].append(dataset[i]['rating'] or '')
    data[4].append(dataset[i]['description'] or '')
    if len(data[0]) % BATCH_SIZE == 0:
        data.append(embed(data[4]))
        collection.insert(data)
        data = [[],[],[],[],[]]

# Embed and insert the remainder 
if len(data[0]) != 0:
    data.append(embed(data[4]))
    collection.insert(data)
    data = [[],[],[],[],[]]
```

??? note "輸出"

    ```text
    100%|██████████| 8807/8807 [00:31<00:00, 276.82it/s]
    ```

## 查詢資料庫
資料安全存進 Milvus 之後，就可以做查詢了。查詢吃一個 tuple，裡面是你要搜尋的電影描述和要用的過濾條件。過濾語法的更多說明在[這裡](https://milvus.io/docs/boolean.md)。搜尋會先印出你的描述和過濾表達式，接著對每個結果印出分數、title、type、release year、rating 和該電影的簡介。

```python
import textwrap

def query(query, top_k = 5):
    text, expr = query
    res = collection.search(embed(text), anns_field='embedding', expr = expr, param=QUERY_PARAM, limit = top_k, output_fields=['title', 'type', 'release_year', 'rating', 'description'])
    for i, hit in enumerate(res):
        print('Description:', text, 'Expression:', expr)
        print('Results:')
        for ii, hits in enumerate(hit):
            print('\t' + 'Rank:', ii + 1, 'Score:', hits.score, 'Title:', hits.entity.get('title'))
            print('\t\t' + 'Type:', hits.entity.get('type'), 'Release Year:', hits.entity.get('release_year'), 'Rating:', hits.entity.get('rating'))
            print(textwrap.fill(hits.entity.get('description'), 88))
            print()

my_query = ('movie about a fluffly animal', 'release_year < 2019 and rating like \"PG%\"')

query(my_query)
```

??? note "輸出"

    ```text
    Description: movie about a fluffly animal Expression: release_year < 2019 and rating like "PG%"
    Results:
    	Rank: 1 Score: 0.30083978176116943 Title: The Lamb
    		Type: Movie Release Year: 2017 Rating: PG
    A big-dreaming donkey escapes his menial existence and befriends some free-spirited
    animal pals in this imaginative retelling of the Nativity Story.

    	Rank: 2 Score: 0.33528298139572144 Title: Puss in Boots
    		Type: Movie Release Year: 2011 Rating: PG
    The fabled feline heads to the Land of Giants with friends Humpty Dumpty and Kitty
    Softpaws on a quest to nab its greatest treasure: the Golden Goose.

    	Rank: 3 Score: 0.33528298139572144 Title: Puss in Boots
    		Type: Movie Release Year: 2011 Rating: PG
    The fabled feline heads to the Land of Giants with friends Humpty Dumpty and Kitty
    Softpaws on a quest to nab its greatest treasure: the Golden Goose.

    	Rank: 4 Score: 0.3414868116378784 Title: Show Dogs
    		Type: Movie Release Year: 2018 Rating: PG
    A rough and tough police dog must go undercover with an FBI agent as a prim and proper
    pet at a dog show to save a baby panda from an illegal sale.

    	Rank: 5 Score: 0.3414868116378784 Title: Show Dogs
    		Type: Movie Release Year: 2018 Rating: PG
    A rough and tough police dog must go undercover with an FBI agent as a prim and proper
    pet at a dog show to save a baby panda from an illegal sale.
    ```

## 重點整理

- 流程是：簡介轉 embedding、連同 metadata 存進 Milvus、查詢時用 embedding 找相似度。
- Milvus 的 collection 除了向量，還可以存 title、type、release_year、rating 等欄位，這些欄位才能拿來過濾。
- 過濾是在向量搜尋時一起套用的條件，不是搜完再手動篩，所以回來的結果都已經符合條件。
- 批次 embed 和批次插入，比一筆一筆處理有效率，記得迴圈結束後補插最後一批。

## 練習

1. 把 `BATCH_SIZE` 改大或改小，觀察插入全部資料的時間怎麼變。
2. 在查詢的過濾表達式裡，改用 `release_year` 做範圍條件（例如只找 2015 年之後的片），比較結果跟沒過濾時有什麼不同。
3. 再加一個過濾條件，同時限制 `type` 和 `rating`，並用同一段描述比較不同組合的結果。
