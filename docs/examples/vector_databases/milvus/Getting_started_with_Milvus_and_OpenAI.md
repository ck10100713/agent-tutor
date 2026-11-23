---
translated: false
source: examples/vector_databases/milvus/Getting_started_with_Milvus_and_OpenAI.ipynb
---

# Getting started with Milvus and OpenAI

> 原文：[examples/vector_databases/milvus/Getting_started_with_Milvus_and_OpenAI.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/milvus/Getting_started_with_Milvus_and_OpenAI.ipynb)



<!-- tutor:goals -->

### Finding your next book

In this notebook we will be going over generating embeddings of book descriptions with OpenAI and using those embeddings within Milvus to find relevant books. The dataset in this example is sourced from HuggingFace datasets, and contains a little over 1 million title-description pairs.

Lets begin by first downloading the required libraries for this notebook:
- `openai` is used for communicating with the OpenAI embedding service
- `pymilvus` is used for communicating with the Milvus server
- `datasets` is used for downloading the dataset
- `tqdm` is used for the progress bars


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

With the required packages installed we can get started. Lets begin by launching the Milvus service. The file being run is the `docker-compose.yaml` found in the folder of this file. This command launches a Milvus standalone instance which we will use for this test.  

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

With Milvus running we can setup our global variables:
- HOST: The Milvus host address
- PORT: The Milvus port number
- COLLECTION_NAME: What to name the collection within Milvus
- DIMENSION: The dimension of the embeddings
- OPENAI_ENGINE: Which embedding model to use
- openai.api_key: Your OpenAI account key
- INDEX_PARAM: The index settings to use for the collection
- QUERY_PARAM: The search parameters to use
- BATCH_SIZE: How many texts to embed and insert at once

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
This segment deals with Milvus and setting up the database for this use case. Within Milvus we need to setup a collection and index the collection. 

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

## Dataset
With Milvus up and running we can begin grabbing our data. Hugging Face Datasets is a hub that holds many different user datasets, and for this example we are using Skelebor's book dataset. This dataset contains title-description pairs for over 1 million books. We are going to embed each description and store it within Milvus along with its title. 

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

## Insert the Data
Now that we have our data on our machine we can begin embedding it and inserting it into Milvus. The embedding function takes in text and returns the embeddings in a list format. 

```python
# Simple function that converts the texts to embeddings
def embed(texts):
    embeddings = openai.Embedding.create(
        input=texts,
        engine=OPENAI_ENGINE
    )
    return [x['embedding'] for x in embeddings['data']]
```

This next step inserts the data. Because there are so many data points, you can stop the insertion cell early if you want to test the workflow immediately. Using fewer data points will probably reduce the accuracy of the results, but it should still be sufficient for a test. 

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

## Query the Database
With our data safely inserted in Milvus, we can now perform a query. The query takes in a string or a list of strings and searches them. The output includes your query and each result's score, title, and book description. 

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

<!-- tutor:summary -->
