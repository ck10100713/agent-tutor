---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/deeplake/deeplake_langchain_qa.ipynb
---

# 用 LangChain、Deep Lake 和 OpenAI 做問答

> 原文：[examples/vector_databases/deeplake/deeplake_langchain_qa.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/deeplake/deeplake_langchain_qa.ipynb)

## 這篇在做什麼
用 LangChain、當成 vector store 的 [Deep Lake](https://activeloop.ai/) 和 OpenAI embedding，做出一個問答系統。流程是載入文字資料集、建 vector store、加入文字，再對它問問題。

## 學完你會
- 載入 Deep Lake 的文字資料集
- 用 LangChain 初始化 Deep Lake vector store，並用 `add_texts` 分批寫入
- 以 GPT-3.5-Turbo 為 LLM，建立對 vector store 的問答

## 開跑前
需要 OpenAI API key。

這個 notebook 示範怎麼用 LangChain、[Deep Lake](https://activeloop.ai/) 當 vector store，搭配 OpenAI embedding 實作問答系統。步驟如下：

1. 載入 Deep Lake 文字資料集
2. 初始化 [LangChain 的 Deep Lake vector store](https://docs.activeloop.ai/tutorials/vector-store/deep-lake-vector-store-in-langchain)
3. 把文字加進 vector store
4. 對資料庫執行 query
5. 完成！

你也可以看其他教學，例如對任何類型資料（PDF、json、csv、文字）做問答：[和任何資料聊天](https://www.activeloop.ai/resources/data-chad-an-ai-app-with-lang-chain-deep-lake-to-chat-with-any-data/)（資料存在 Deep Lake）、[程式碼理解](https://www.activeloop.ai/resources/lang-chain-gpt-4-for-code-understanding-twitter-algorithm/)、[PDF 問答](https://www.activeloop.ai/resources/ultimate-guide-to-lang-chain-deep-lake-build-chat-gpt-to-answer-questions-on-your-financial-data/)，或是[推薦歌曲](https://www.activeloop.ai/resources/3-ways-to-build-a-recommendation-engine-for-songs-with-lang-chain/)。

## 安裝需要的套件
先安裝下面的套件。

```python
!pip install deeplake langchain openai tiktoken
```

## 驗證
在這裡提供你的 OpenAI API key：

```python
import getpass
import os

os.environ['OPENAI_API_KEY'] = getpass.getpass()
```

??? note "輸出"

    ```text
    ··········
    ```

## 載入 Deep Lake 文字資料集
這個範例使用 [cohere-wikipedia-22](https://app.activeloop.ai/davitbun/cohere-wikipedia-22) 資料集中 20000 筆的子集。

```python
import deeplake

ds = deeplake.load("hub://activeloop/cohere-wikipedia-22-sample")
ds.summary()
```

??? note "輸出"

    ```text
    \
    ```

    ```text
    Opening dataset in read-only mode as you don't have write permissions.
    ```

    ```text
    -
    ```

    ```text
    This dataset can be visualized in Jupyter Notebook by ds.visualize() or at https://app.activeloop.ai/activeloop/cohere-wikipedia-22-sample
    ```

    ```text
    |
    ```

    ```text
    hub://activeloop/cohere-wikipedia-22-sample loaded successfully.

    Dataset(path='hub://activeloop/cohere-wikipedia-22-sample', read_only=True, tensors=['ids', 'metadata', 'text'])

      tensor    htype     shape      dtype  compression
     -------   -------   -------    -------  ------- 
       ids      text    (20000, 1)    str     None   
     metadata   json    (20000, 1)    str     None   
       text     text    (20000, 1)    str     None
    ```

看幾個樣本：

```python
ds[:3].text.data()["value"]
```

??? note "輸出"

    ```text
    ['The 24-hour clock is a way of telling the time in which the day runs from midnight to midnight and is divided into 24 hours, numbered from 0 to 23. It does not use a.m. or p.m. This system is also referred to (only in the US and the English speaking parts of Canada) as military time or (only in the United Kingdom and now very rarely) as continental time. In some parts of the world, it is called railway time. Also, the international standard notation of time (ISO 8601) is based on this format.',
     'A time in the 24-hour clock is written in the form hours:minutes (for example, 01:23), or hours:minutes:seconds (01:23:45). Numbers under 10 have a zero in front (called a leading zero); e.g. 09:07. Under the 24-hour clock system, the day begins at midnight, 00:00, and the last minute of the day begins at 23:59 and ends at 24:00, which is identical to 00:00 of the following day. 12:00 can only be mid-day. Midnight is called 24:00 and is used to mean the end of the day and 00:00 is used to mean the beginning of the day. For example, you would say "Tuesday at 24:00" and "Wednesday at 00:00" to mean exactly the same time.',
     'However, the US military prefers not to say 24:00 - they do not like to have two names for the same thing, so they always say "23:59", which is one minute before midnight.']
    ```

## LangChain 的 Deep Lake vector store
先定義 `dataset_path`，這是你的 Deep Lake vector store 存放文字 embedding 的位置。

```python
dataset_path = 'wikipedia-embeddings-deeplake'
```

我們把 OpenAI 的 `text-embedding-3-small` 設成 embedding function，並在 `dataset_path` 初始化 Deep Lake vector store……

```python
from langchain.embeddings.openai import OpenAIEmbeddings
from langchain.vectorstores import DeepLake

embedding = OpenAIEmbeddings(model="text-embedding-3-small")
db = DeepLake(dataset_path, embedding=embedding, overwrite=True)
```

……然後用 `add_texts` 方法，一次一批把樣本填進去。

```python
from tqdm.auto import tqdm

batch_size = 100

nsamples = 10  # for testing. Replace with len(ds) to append everything
for i in tqdm(range(0, nsamples, batch_size)):
    # find end of batch
    i_end = min(nsamples, i + batch_size)

    batch = ds[i:i_end]
    id_batch = batch.ids.data()["value"]
    text_batch = batch.text.data()["value"]
    meta_batch = batch.metadata.data()["value"]

    db.add_texts(text_batch, metadatas=meta_batch, ids=id_batch)
```

??? note "輸出"

    ```text
      0%|          | 0/1 [00:00<?, ?it/s]
    ```

    ```text

    creating embeddings:   0%|          | 0/1 [00:00<?, ?it/s][A
    creating embeddings: 100%|██████████| 1/1 [00:02<00:00,  2.11s/it]

    100%|██████████| 10/10 [00:00<00:00, 462.42it/s]
    ```

    ```text
    Dataset(path='wikipedia-embeddings-deeplake', tensors=['text', 'metadata', 'embedding', 'id'])

      tensor      htype      shape      dtype  compression
      -------    -------    -------    -------  ------- 
       text       text      (10, 1)      str     None   
     metadata     json      (10, 1)      str     None   
     embedding  embedding  (10, 1536)  float32   None   
        id        text      (10, 1)      str     None
    ```

## 對資料庫執行使用者 query
底層的 Deep Lake dataset 物件可以透過 `db.vectorstore.dataset` 取得，也可以用 `db.vectorstore.summary()` 摘要資料結構，它顯示 4 個 tensor、10 筆樣本：

```python
db.vectorstore.summary()
```

??? note "輸出"

    ```text
    Dataset(path='wikipedia-embeddings-deeplake', tensors=['text', 'metadata', 'embedding', 'id'])

      tensor      htype      shape      dtype  compression
      -------    -------    -------    -------  ------- 
       text       text      (10, 1)      str     None   
     metadata     json      (10, 1)      str     None   
     embedding  embedding  (10, 1536)  float32   None   
        id        text      (10, 1)      str     None
    ```

現在在 vector store 上設定問答，LLM 用 GPT-3.5-Turbo。

```python
from langchain.chains import RetrievalQA
from langchain.chat_models import ChatOpenAI

# Re-load the vector store in case it's no longer initialized
# db = DeepLake(dataset_path = dataset_path, embedding_function=embedding)

qa = RetrievalQA.from_chain_type(llm=ChatOpenAI(model='gpt-3.5-turbo'), chain_type="stuff", retriever=db.as_retriever())
```

試著執行一個 prompt 並檢查輸出。這個 API 內部會做 embedding 搜尋，找出最相關的資料放進 LLM 的 context。

```python
query = 'Why does the military not say 24:00?'
qa.run(query)
```

??? note "輸出"

    ```text
    'The military prefers not to say 24:00 because they do not like to have two names for the same thing. Instead, they always say "23:59", which is one minute before midnight.'
    ```

大功告成！

## 重點整理
- 問答系統的核心是檢索加生成：先用 embedding 搜尋找相關文字，再放進 LLM 的 context。
- LangChain 把 Deep Lake 包成 vector store，用 `add_texts` 就能寫入資料。
- 寫入和查詢要用同一個 embedding function（這裡是 `text-embedding-3-small`）。
- vector store 的資料位置由 `dataset_path` 決定。

## 練習
1. 換一個自己的問題送進問答鏈，檢查答案是否來自資料集內容。
2. 改檢索時取回的文件數量，看答案有什麼變化。
3. 把 LLM 換成別的模型，比較同一個問題的回答。
