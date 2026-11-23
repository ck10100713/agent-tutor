---
translated: true
source: examples/vector_databases/pinecone/Semantic_Search.ipynb
---

# 用 Pinecone 和 OpenAI 做語意搜尋

> 原文：[examples/vector_databases/pinecone/Semantic_Search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/Semantic_Search.ipynb)



## 這篇在做什麼
用 OpenAI Embedding API 產生文字的 embedding，再把它們放進 Pinecone vector database，做出快速又可擴充的語意搜尋。資料用的是 TREC 資料集的 1K 個問題。

## 學完你會
- 用 OpenAI 產生 embedding，並用 `upsert` 把 ID、向量和原文存進 Pinecone
- 把 query 轉成向量，在 Pinecone index 查出最相似的結果
- 測試拼錯或換字的 query，確認搜尋靠的是語意而不是關鍵字

## 開跑前
- OpenAI API key
- Pinecone API key（Pinecone dashboard 可以申請免費的）
- 需要 HuggingFace Datasets 載入資料

這份教學會帶你用 OpenAI Embedding API 產生語言 embedding，然後把這些 embedding 建 index 到 Pinecone vector database，做到快速、可擴充的向量搜尋。

這是一個強大又常見的組合，可用來建置語意搜尋、問答、威脅偵測，以及其他需要對大量文字資料做 NLP 和搜尋的應用。

基本流程如下：

**Embed 與建 index**

* 用 OpenAI Embedding API 為你的文件（或任何文字資料）產生向量 embedding。
* 把這些向量 embedding 上傳到 Pinecone，它可以儲存並索引數百萬到數十億筆 embedding，並以極低延遲搜尋。

**搜尋**

* 把你的 query 文字或文件再次送進 OpenAI Embedding API。
* 取得產生的向量 embedding，當成 query 送到 Pinecone。
* 取回語意相似的文件，即使它們跟 query 沒有任何共同關鍵字。

![Architecture overview](https://files.readme.io/6a3ea5a-pinecone-openai-overview.png)

開始吧...

## 設定

首先要設定環境，並取得 OpenAI 和 Pinecone 的 API key。先從環境開始，我們需要 HuggingFace *Datasets* 來取得資料，還有 OpenAI 和 Pinecone 的 client：

```python
!pip install -qU \
    pinecone-client==3.0.2 \
    openai==1.10.0 \
    datasets==2.16.1
```

??? note "輸出"

    ```text
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 201.4/201.4 kB 2.0 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 225.1/225.1 kB 12.1 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 507.1/507.1 kB 12.4 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 75.9/75.9 kB 4.4 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 115.3/115.3 kB 9.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 134.8/134.8 kB 7.6 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 76.9/76.9 kB 4.7 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 58.3/58.3 kB 3.8 MB/s eta 0:00:00
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 134.8/134.8 kB 5.2 MB/s eta 0:00:00
    [?25hERROR: pip's dependency resolver does not currently take into account all the packages that are installed. This behaviour is the source of the following dependency conflicts.
    llmx 0.0.15a0 requires cohere, which is not installed.
    llmx 0.0.15a0 requires tiktoken, which is not installed.
    tensorflow-probability 0.22.0 requires typing-extensions<4.6.0, but you have typing-extensions 4.9.0 which is incompatible.
    ```

### 建立 embedding

接著初始化與 OpenAI Embeddings *以及* Pinecone vector DB 的連線。可以到 [OpenAI](https://platform.openai.com) 和 [Pinecone](https://app.pinecone.io) 註冊取得 API key。

```python
from openai import OpenAI

client = OpenAI(
    api_key="OPENAI_API_KEY"
)  # get API key from platform.openai.com
```

現在可以像這樣用 OpenAI Ada similarity 模型建立 embedding：

```python
MODEL = "text-embedding-3-small"

res = client.embeddings.create(
    input=[
        "Sample document text goes here",
        "there will be several phrases in each batch"
    ], model=MODEL
)
res
```

```python
print(f"vector 0: {len(res.data[0].embedding)}\nvector 1: {len(res.data[1].embedding)}")
```

??? note "輸出"

    ```text
    vector 0: 1536
    vector 1: 1536
    ```

```python
# we can extract embeddings to a list
embeds = [record.embedding for record in res.data]
len(embeds)
```

??? note "輸出"

    ```text
    2
    ```

接下來，初始化用來儲存向量 embedding 的 Pinecone index。

```python
len(embeds[0])
```

??? note "輸出"

    ```text
    1536
    ```

初始化 Pinecone 連線，你可以在 [Pinecone dashboard](https://app.pinecone.io) 取得免費的 API key。

```python
from pinecone import Pinecone

pc = Pinecone(api_key="...")
```



```python
import time
from pinecone import ServerlessSpec

spec = ServerlessSpec(cloud="aws", region="us-west-2")

index_name = 'semantic-search-openai'

# check if index already exists (if shouldn't if this is your first run)
if index_name not in pc.list_indexes().names():
    # if does not exist, create index
    pc.create_index(
        index_name,
        dimension=len(embeds[0]),  # dimensionality of text-embed-3-small
        metric='dotproduct',
        spec=spec
    )
    # wait for index to be initialized
    while not pc.describe_index(index_name).status['ready']:
        time.sleep(1)

# connect to index
index = pc.Index(index_name)
time.sleep(1)
# view index stats
index.describe_index_stats()
```

??? note "輸出"

    ```text
    {'dimension': 1536,
     'index_fullness': 0.0,
     'namespaces': {},
     'total_vector_count': 0}
    ```

## 填入 index

現在從 TREC 資料集取 1K 個問題

```python
from datasets import load_dataset

# load the first 1K rows of the TREC dataset
trec = load_dataset('trec', split='train[:1000]')
trec
```

??? note "輸出"

    ```text
    /usr/local/lib/python3.10/dist-packages/huggingface_hub/utils/_token.py:88: UserWarning: 
    The secret `HF_TOKEN` does not exist in your Colab secrets.
    To authenticate with the Hugging Face Hub, create a token in your settings tab (https://huggingface.co/settings/tokens), set it as secret in your Google Colab and restart your session.
    You will be able to reuse this secret in all of your notebooks.
    Please note that authentication is recommended but still optional to access public models or datasets.
      warnings.warn(
    ```

    ```text
    Downloading data:   0%|          | 0.00/213k [00:00<?, ?B/s]
    ```

    ```text
    Downloading data:   0%|          | 0.00/17.1k [00:00<?, ?B/s]
    ```

    ```text
    Generating train split:   0%|          | 0/5452 [00:00<?, ? examples/s]
    ```

    ```text
    Generating test split:   0%|          | 0/500 [00:00<?, ? examples/s]
    ```

    ```text
    Dataset({
        features: ['text', 'coarse_label', 'fine_label'],
        num_rows: 1000
    })
    ```

```python
trec[0]
```

??? note "輸出"

    ```text
    {'text': 'How did serfdom develop in and then leave Russia ?',
     'coarse_label': 2,
     'fine_label': 26}
    ```

然後用 OpenAI 為每個句子建立向量 embedding，並把每個句子的 ID、向量 embedding 和原文 `upsert` 到 Pinecone。

```python
from tqdm.auto import tqdm

count = 0  # we'll use the count to create unique IDs
batch_size = 32  # process everything in batches of 32
for i in tqdm(range(0, len(trec['text']), batch_size)):
    # set end position of batch
    i_end = min(i+batch_size, len(trec['text']))
    # get batch of lines and IDs
    lines_batch = trec['text'][i: i+batch_size]
    ids_batch = [str(n) for n in range(i, i_end)]
    # create embeddings
    res = client.embeddings.create(input=lines_batch, model=MODEL)
    embeds = [record.embedding for record in res.data]
    # prep metadata and upsert batch
    meta = [{'text': line} for line in lines_batch]
    to_upsert = zip(ids_batch, embeds, meta)
    # upsert to Pinecone
    index.upsert(vectors=list(to_upsert))
```

??? note "輸出"

    ```text
      0%|          | 0/32 [00:00<?, ?it/s]
    ```

---

# 查詢

資料建好 index 後，就可以開始搜尋了。流程跟建 index 類似。我們從一個文字 `query` 開始，想用它找出相似的句子。跟之前一樣，用 OpenAI 的 text similarity Babbage 模型把它編碼成 *query 向量* `xq`，再用 `xq` 去查詢 Pinecone index。

```python
query = "What caused the 1929 Great Depression?"

xq = client.embeddings.create(input=query, model=MODEL).data[0].embedding
```

現在來查詢...

```python
res = index.query(vector=[xq], top_k=5, include_metadata=True)
res
```

??? note "輸出"

    ```text
    {'matches': [{'id': '932',
                  'metadata': {'text': 'Why did the world enter a global '
                                       'depression in 1929 ?'},
                  'score': 0.751888752,
                  'values': []},
                 {'id': '787',
                  'metadata': {'text': "When was `` the Great Depression '' ?"},
                  'score': 0.597448647,
                  'values': []},
                 {'id': '400',
                  'metadata': {'text': 'What crop failure caused the Irish Famine '
                                       '?'},
                  'score': 0.367482603,
                  'values': []},
                 {'id': '835',
                  'metadata': {'text': 'What were popular songs and types of songs '
                                       'in the 1920s ?'},
                  'score': 0.324545294,
                  'values': []},
                 {'id': '262',
                  'metadata': {'text': 'When did World War I start ?'},
                  'score': 0.320995867,
                  'values': []}],
     'namespace': '',
     'usage': {'read_units': 6}}
    ```

Pinecone 的回應在 `metadata` 欄位裡包含我們的原文，來印出 `top_k` 個最相似的問題和它們各自的相似度分數。

```python
for match in res['matches']:
    print(f"{match['score']:.2f}: {match['metadata']['text']}")
```

??? note "輸出"

    ```text
    0.75: Why did the world enter a global depression in 1929 ?
    0.60: When was `` the Great Depression '' ?
    0.37: What crop failure caused the Irish Famine ?
    0.32: What were popular songs and types of songs in the 1920s ?
    0.32: When did World War I start ?
    ```

看起來不錯，來加點難度，把 *"depression"* 換成錯誤的用詞 *"recession"*。

```python
query = "What was the cause of the major recession in the early 20th century?"

# create the query embedding
xq = client.embeddings.create(input=query, model=MODEL).data[0].embedding

# query, returning the top 5 most similar results
res = index.query(vector=[xq], top_k=5, include_metadata=True)

for match in res['matches']:
    print(f"{match['score']:.2f}: {match['metadata']['text']}")
```

??? note "輸出"

    ```text
    0.63: Why did the world enter a global depression in 1929 ?
    0.55: When was `` the Great Depression '' ?
    0.34: What were popular songs and types of songs in the 1920s ?
    0.33: What crop failure caused the Irish Famine ?
    0.29: What is considered the costliest disaster the insurance industry has ever faced ?
    ```

再來一次...

```python
query = "Why was there a long-term economic downturn in the early 20th century?"

# create the query embedding
xq = client.embeddings.create(input=query, model=MODEL).data[0].embedding

# query, returning the top 5 most similar results
res = index.query(vector=[xq], top_k=5, include_metadata=True)

for match in res['matches']:
    print(f"{match['score']:.2f}: {match['metadata']['text']}")
```

??? note "輸出"

    ```text
    0.62: Why did the world enter a global depression in 1929 ?
    0.54: When was `` the Great Depression '' ?
    0.34: What were popular songs and types of songs in the 1920s ?
    0.33: What crop failure caused the Irish Famine ?
    0.32: What do economists do ?
    ```

很棒，我們的語意搜尋流程顯然能辨識每個 query 的意思，並從已建好 index 的問題裡回傳語意最相似的問題。

用完 index 之後，把它刪掉以節省資源。

```python
pc.delete_index(index_name)
```

---

## 重點整理
- 語意搜尋的架構分兩段：先 embed 並 upsert 文件，查詢時再 embed query 去比對。
- 建 index 和查詢必須用同一個 embedding 模型，向量才在同一個空間。
- Pinecone 存向量的同時，可以在 metadata 放原文，查完就能直接顯示。
- 即使 query 用詞不同或有錯，語意搜尋仍能找到意思相近的內容。
- 用完的 index 要記得刪掉，避免佔用資源。

## 練習
1. 換一個你自己的 query，看回傳的 `top_k` 結果是否合理。
2. 把 `top_k` 改成 10，並觀察相似度分數隨排名下降的情況。
3. 把 upsert 的資料量從 1K 改成 200，重跑同一個 query，比較結果品質有什麼變化。
