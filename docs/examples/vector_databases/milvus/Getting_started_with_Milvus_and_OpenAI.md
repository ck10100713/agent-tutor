---
translated: true
source: examples/vector_databases/milvus/Getting_started_with_Milvus_and_OpenAI.ipynb
---

# Milvus 與 OpenAI 入門

> 原文：[examples/vector_databases/milvus/Getting_started_with_Milvus_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/milvus/Getting_started_with_Milvus_and_OpenAI.ipynb)



## 這篇在做什麼

用 OpenAI 幫書籍簡介產生 embedding，存進本機啟動的 Milvus，再用語意搜尋找相關的書。資料集來自 HuggingFace，有 100 多萬筆書名跟簡介。

## 學完你會

- 用 docker-compose 在本機啟動 Milvus standalone
- 建立 collection 和索引，並把批次產生的 embedding 寫進去
- 輸入一個字串或字串清單，查出最相似的書和分數

## 開跑前

- 本機要能跑 Docker（用資料夾裡的 `docker-compose.yaml` 啟動 Milvus）
- OpenAI API key

### 找下一本想看的書

這份 notebook 會用 OpenAI 產生書籍簡介的 embedding，再用這些 embedding 在 Milvus 裡找相關的書。資料集來自 HuggingFace datasets，有 100 多萬筆書名和簡介配對。

先安裝這份 notebook 需要的套件：
- `openai` 用來呼叫 OpenAI 的 embedding 服務
- `pymilvus` 用來跟 Milvus 伺服器溝通
- `datasets` 用來下載資料集
- `tqdm` 用來顯示進度條


```python
! pip install openai pymilvus datasets tqdm
```

??? note "輸出"

    ```text
    Looking in indexes: https://pypi.org/simple, https://pypi.ngc.nvidia.com
    Requirement already satisfied: openai in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (0.27.2)
    Requirement already satisfied: pymilvus in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (2.2.2)
    Requirement already satisfied: datasets in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (2.10.1)
    Requirement already satisfied: tqdm in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (4.64.1)
    Requirement already satisfied: aiohttp in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from openai) (3.8.4)
    Requirement already satisfied: requests>=2.20 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from openai) (2.28.2)
    Requirement already satisfied: pandas>=1.2.4 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (1.5.3)
    Requirement already satisfied: ujson<=5.4.0,>=2.0.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (5.1.0)
    Requirement already satisfied: mmh3<=3.0.0,>=2.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (3.0.0)
    Requirement already satisfied: grpcio<=1.48.0,>=1.47.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (1.47.2)
    Requirement already satisfied: grpcio-tools<=1.48.0,>=1.47.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pymilvus) (1.47.2)
    Requirement already satisfied: huggingface-hub<1.0.0,>=0.2.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.12.1)
    Requirement already satisfied: dill<0.3.7,>=0.3.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.3.6)
    Requirement already satisfied: xxhash in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (3.2.0)
    Requirement already satisfied: pyyaml>=5.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (5.4.1)
    Requirement already satisfied: fsspec[http]>=2021.11.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (2023.1.0)
    Requirement already satisfied: packaging in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (23.0)
    Requirement already satisfied: numpy>=1.17 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (1.23.5)
    Requirement already satisfied: multiprocess in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.70.14)
    Requirement already satisfied: pyarrow>=6.0.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (10.0.1)
    Requirement already satisfied: responses<0.19 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from datasets) (0.18.0)
    Requirement already satisfied: multidict<7.0,>=4.5 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (6.0.4)
    Requirement already satisfied: frozenlist>=1.1.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (1.3.3)
    Requirement already satisfied: async-timeout<5.0,>=4.0.0a3 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (4.0.2)
    Requirement already satisfied: yarl<2.0,>=1.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (1.8.2)
    Requirement already satisfied: aiosignal>=1.1.2 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (1.3.1)
    Requirement already satisfied: charset-normalizer<4.0,>=2.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (3.0.1)
    Requirement already satisfied: attrs>=17.3.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from aiohttp->openai) (22.2.0)
    Requirement already satisfied: six>=1.5.2 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from grpcio<=1.48.0,>=1.47.0->pymilvus) (1.16.0)
    Requirement already satisfied: protobuf<4.0dev,>=3.12.0 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from grpcio-tools<=1.48.0,>=1.47.0->pymilvus) (3.20.1)
    Requirement already satisfied: setuptools in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from grpcio-tools<=1.48.0,>=1.47.0->pymilvus) (65.6.3)
    Requirement already satisfied: filelock in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from huggingface-hub<1.0.0,>=0.2.0->datasets) (3.9.0)
    Requirement already satisfied: typing-extensions>=3.7.4.3 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from huggingface-hub<1.0.0,>=0.2.0->datasets) (4.5.0)
    Requirement already satisfied: python-dateutil>=2.8.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pandas>=1.2.4->pymilvus) (2.8.2)
    Requirement already satisfied: pytz>=2020.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from pandas>=1.2.4->pymilvus) (2022.7.1)
    Requirement already satisfied: urllib3<1.27,>=1.21.1 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from requests>=2.20->openai) (1.26.14)
    Requirement already satisfied: idna<4,>=2.5 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from requests>=2.20->openai) (3.4)
    Requirement already satisfied: certifi>=2017.4.17 in /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages (from requests>=2.20->openai) (2022.12.7)
    ```

套件裝好就可以開始了。先啟動 Milvus 服務。執行的檔案是這個檔案所在資料夾裡的 `docker-compose.yaml`，這個指令會啟動一個 Milvus standalone 實例供測試使用。

```python
! docker compose up -d
```

??? note "輸出"

    ```text
    [1A[1B[0G[?25l[+] Running 0/0
     ⠋ Network milvus  Creating                                                0.1s
    [?25h[1A[1A[0G[?25l[+] Running 1/1
     ⠿ Network milvus          Created                                         0.1s
     ⠋ Container milvus-minio  Creating                                        0.1s
     ⠋ Container milvus-etcd   Creating                                        0.1s
    [?25h[1A[1A[1A[1A[0G[?25l[+] Running 1/3
     ⠿ Network milvus          Created                                         0.1s
     ⠙ Container milvus-minio  Creating                                        0.2s
     ⠙ Container milvus-etcd   Creating                                        0.2s
    [?25h[1A[1A[1A[1A[0G[?25l[+] Running 1/3
     ⠿ Network milvus          Created                                         0.1s
     ⠹ Container milvus-minio  Creating                                        0.3s
     ⠹ Container milvus-etcd   Creating                                        0.3s
    [?25h[1A[1A[1A[1A[0G[?25l[+] Running 3/3
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-minio       Created                                    0.3s
     ⠿ Container milvus-etcd        Created                                    0.3s
     ⠋ Container milvus-standalone  Creating                                   0.1s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 3/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-minio       Created                                    0.3s
     ⠿ Container milvus-etcd        Created                                    0.3s
     ⠙ Container milvus-standalone  Creating                                   0.2s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 4/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-minio       Created                                    0.3s
     ⠿ Container milvus-etcd        Created                                    0.3s
     ⠿ Container milvus-standalone  Created                                    0.3s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-minio       Starting                                   0.7s
     ⠿ Container milvus-etcd        Starting                                   0.7s
     ⠿ Container milvus-standalone  Created                                    0.3s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
     ⠿ Network milvus               Created                                    0.1s
     ⠿ Container milvus-minio       Starting                                   0.8s
     ⠿ Container milvus-etcd        Starting                                   0.8s
     ⠿ Container milvus-standalone  Created                                    0.3s
    [?25h[1A[1A[1A[1A[1A[0G[?25l[+] Running 2/4
    ... (省略 110 行)
    ```

Milvus 跑起來之後，設定全域變數：
- HOST：Milvus 的主機位址
- PORT：Milvus 的 port
- COLLECTION_NAME：在 Milvus 裡 collection 的名字
- DIMENSION：embedding 的維度
- OPENAI_ENGINE：要用哪個 embedding 模型
- openai.api_key：你的 OpenAI 帳號 key
- INDEX_PARAM：collection 用的索引設定
- QUERY_PARAM：搜尋參數
- BATCH_SIZE：一次要 embed 並寫入多少筆文字

```python
import openai

HOST = 'localhost'
PORT = 19530
COLLECTION_NAME = 'book_search'
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

## Milvus
這一段處理 Milvus 本身，為這個用途準備資料庫。在 Milvus 裡要先建 collection，然後替 collection 建索引。

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
Milvus 準備好之後就可以抓資料了。Hugging Face Datasets 是一個收了很多使用者資料集的 hub，這個範例用 Skelebor 的書籍資料集，裡面有 100 多萬本書的書名和簡介配對。我們會把每本的簡介 embed，連同書名一起存進 Milvus。

```python
import datasets

# Download the dataset and only use the `train` portion (file is around 800Mb)
dataset = datasets.load_dataset('Skelebor/book_titles_and_descriptions_en_clean', split='train')
```

??? note "輸出"

    ```text
    /Users/filiphaltmayer/miniconda3/envs/haystack/lib/python3.9/site-packages/tqdm/auto.py:22: TqdmWarning: IProgress not found. Please update jupyter and ipywidgets. See https://ipywidgets.readthedocs.io/en/stable/user_install.html
      from .autonotebook import tqdm as notebook_tqdm
    Found cached dataset parquet (/Users/filiphaltmayer/.cache/huggingface/datasets/Skelebor___parquet/Skelebor--book_titles_and_descriptions_en_clean-3596935b1d8a7747/0.0.0/2a3b91fbd88a2c90d1dbbb32b460cf621d31bd5b05b934492fdef7d8d6f236ec)
    ```

## 寫入資料
資料都在本機之後，就可以 embed 並寫進 Milvus。embedding 函式吃文字，回傳 list 格式的 embedding。

```python
# Simple function that converts the texts to embeddings
def embed(texts):
    embeddings = openai.Embedding.create(
        input=texts,
        engine=OPENAI_ENGINE
    )
    return [x['embedding'] for x in embeddings['data']]
```

下一步是寫入資料。因為資料點非常多，如果想馬上測試流程，可以提早中斷這個 cell。資料變少準確度大概會下降，但拿來測試還是夠用。

```python
from tqdm import tqdm

data = [
    [], # title
    [], # description
]

# Embed and insert in batches
for i in tqdm(range(0, len(dataset))):
    data[0].append(dataset[i]['title'])
    data[1].append(dataset[i]['description'])
    if len(data[0]) % BATCH_SIZE == 0:
        data.append(embed(data[1]))
        collection.insert(data)
        data = [[],[]]

# Embed and insert the remainder 
if len(data[0]) != 0:
    data.append(embed(data[1]))
    collection.insert(data)
    data = [[],[]]
```

??? note "輸出"

    ```text
      0%|          | 1999/1032335 [00:06<57:22, 299.31it/s]
    ```

    ```text
    KeyboardInterrupt:
    ```

## 查詢資料庫
資料都安全寫進 Milvus 後就可以查詢了。查詢可以吃一個字串或字串清單，並對它們搜尋。輸出會包含你的查詢，以及每筆結果的分數、書名和書籍簡介。

```python
import textwrap

def query(queries, top_k = 5):
    if type(queries) != list:
        queries = [queries]
    res = collection.search(embed(queries), anns_field='embedding', param=QUERY_PARAM, limit = top_k, output_fields=['title', 'description'])
    for i, hit in enumerate(res):
        print('Description:', queries[i])
        print('Results:')
        for ii, hits in enumerate(hit):
            print('\t' + 'Rank:', ii + 1, 'Score:', hits.score, 'Title:', hits.entity.get('title'))
            print(textwrap.fill(hits.entity.get('description'), 88))
            print()
```

```python
query('Book about a k-9 from europe')
```

??? note "輸出"

    ```text
    RPC error: [search], <MilvusException: (code=1, message=code: UnexpectedError, reason: code: CollectionNotExists, reason: can't find collection: book_search)>, <Time:{'RPC start': '2023-03-17 14:22:18.368461', 'RPC error': '2023-03-17 14:22:18.382086'}>
    ```

    ```text
    MilvusException: <MilvusException: (code=1, message=code: UnexpectedError, reason: code: CollectionNotExists, reason: can't find collection: book_search)>
    ```

## 重點整理

- 向量資料庫的基本流程是建 collection、建索引、寫入 embedding、查詢，每個向量資料庫大同小異。
- 資料量大時要用批次處理 embedding 和寫入，BATCH_SIZE 是主要的調整點。
- 查詢時用的 embedding 模型要跟寫入時一致，DIMENSION 也要對得上。
- 測試時不用灌完整個資料集，少量資料就能驗證流程，只是結果品質會差一些。

## 練習

1. 把 BATCH_SIZE 改小，觀察寫入的速度與進度條的變化。
2. 換一組查詢字串（例如描述你喜歡的小說類型），看回傳的書是否符合直覺。
3. 一次傳入多個查詢字串，比較各自的結果與分數。
