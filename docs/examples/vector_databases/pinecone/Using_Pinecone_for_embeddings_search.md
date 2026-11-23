---
translated: true
source: examples/vector_databases/pinecone/Using_Pinecone_for_embeddings_search.ipynb
---

# 用 Pinecone 做 embedding 搜尋

> 原文：[examples/vector_databases/pinecone/Using_Pinecone_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/pinecone/Using_Pinecone_for_embeddings_search.ipynb)

## 這篇在做什麼
走一遍完整流程：載入已經 embed 好的資料，建到 Pinecone 這個託管式向量資料庫，再用語意搜尋查詢。一個 index 裡用不同 namespace 分開 title 和 content。

## 學完你會
- 建立 Pinecone index，並用 namespace 分隔 title 和 content 的向量
- 把 embedding 寫進對應的 namespace
- 對各個 namespace 下相似度搜尋 query，驗證結果

## 開跑前
到 [Pinecone](https://www.pinecone.io) 註冊，並把 API key 存成環境變數 `PINECONE_API_KEY`。另外需要 OpenAI API key。

這個 notebook 帶你走一個簡單流程：下載資料、做 embedding，再用向量資料庫建索引並搜尋。很多客戶想在安全的環境裡儲存、搜尋自己資料的 embedding，來支援聊天機器人、主題建模等正式環境的用途，這就是常見的需求。

### 什麼是向量資料庫

向量資料庫是專門用來儲存、管理和搜尋 embedding 向量的資料庫。近年 AI 在自然語言、影像辨識等非結構化資料的應用越來越有效，把文字、音訊、影片等非結構化資料編碼成向量給機器學習模型使用的做法也快速成長，向量資料庫就成了企業落地這些應用並擴大規模的有效方案。

### 為什麼要用向量資料庫

向量資料庫讓企業能把這個 repo 裡分享過的許多 embedding 用例（例如問答、聊天機器人、推薦服務），放到安全、可擴展的環境中運行。很多客戶在小規模時 embedding 能解決問題，但效能和安全性擋住了上線，我們認為向量資料庫是解決這件事的關鍵元件。這份指南會走過基本流程：embed 文字資料、存進向量資料庫，並用來做語意搜尋。


### Demo 流程
流程如下：
- **設定**：import 套件、設定需要的變數
- **載入資料**：載入資料集，並用 OpenAI embedding 處理
- **Pinecone**
    - *設定*：這裡設定 Pinecone 的 Python client，詳情看[這裡](https://docs.pinecone.io/docs/quickstart)
    - *建索引*：建立一個 index，用 namespace 分開 __titles__ 和 __content__
    - *搜尋*：用搜尋 query 測試兩個 namespace，確認可以正常運作

跑完這個 notebook，你應該對向量資料庫怎麼設定和使用有基本概念，之後可以進一步做更複雜、運用 embedding 的用例。

## 設定

import 需要的函式庫，並設定想用的 embedding 模型。

```python
# We'll need to install the Pinecone client
!pip install pinecone-client

#Install wget to pull zip file
!pip install wget
```

??? note "輸出"

    ```text
    Requirement already satisfied: pinecone-client in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (2.2.2)
    Requirement already satisfied: requests>=2.19.0 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (2.31.0)
    Requirement already satisfied: pyyaml>=5.4 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (6.0)
    Requirement already satisfied: loguru>=0.5.0 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (0.7.0)
    Requirement already satisfied: typing-extensions>=3.7.4 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (4.5.0)
    Requirement already satisfied: dnspython>=2.0.0 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (2.3.0)
    Requirement already satisfied: python-dateutil>=2.5.3 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (2.8.2)
    Requirement already satisfied: urllib3>=1.21.1 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (1.26.16)
    Requirement already satisfied: tqdm>=4.64.1 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (4.65.0)
    Requirement already satisfied: numpy>=1.22.0 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from pinecone-client) (1.25.0)
    Requirement already satisfied: six>=1.5 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from python-dateutil>=2.5.3->pinecone-client) (1.16.0)
    Requirement already satisfied: charset-normalizer<4,>=2 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from requests>=2.19.0->pinecone-client) (3.1.0)
    Requirement already satisfied: idna<4,>=2.5 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from requests>=2.19.0->pinecone-client) (3.4)
    Requirement already satisfied: certifi>=2017.4.17 in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (from requests>=2.19.0->pinecone-client) (2023.5.7)
    Requirement already satisfied: wget in /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages (3.2)
    ```

```python
import openai

from typing import List, Iterator
import pandas as pd
import numpy as np
import os
import wget
from ast import literal_eval

# Pinecone's client library for Python
import pinecone

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

??? note "輸出"

    ```text
    /Users/colin.jarvis/Documents/dev/cookbook/openai-cookbook/vector_db/lib/python3.10/site-packages/pinecone/index.py:4: TqdmExperimentalWarning: Using `tqdm.autonotebook.tqdm` in notebook mode. Use `tqdm.tqdm` instead to force console mode (e.g. in jupyter console)
      from tqdm.autonotebook import tqdm
    ```

## 載入資料

這一節載入我們在[這篇文章](../../Embedding_Wikipedia_articles_for_search.md)準備好的 embed 資料。

```python
embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
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

## Pinecone

下一個選項是 **Pinecone**，一個託管式向量資料庫，提供雲原生的選擇。

進行這一步前，你需要先到 [Pinecone](https://www.pinecone.io) 註冊，並把 API key 存成名為 ```PINECONE_API_KEY``` 的環境變數。

這一節我們會：
- 建一個有多個 namespace 的 index，分別放文章 title 和 content
- 把資料存進 index，讓文章 **title** 和 **content** 各有獨立可搜尋的 "namespace"
- 下幾個相似度搜尋 query，確認設定正常

```python
api_key = os.getenv("PINECONE_API_KEY")
pinecone.init(api_key=api_key)
```

### 建立 Index

首先要建一個 index，叫 `wikipedia-articles`。有了 index 之後，就能建多個 namespace，讓同一個 index 能支援不同用途的搜尋。詳情請看 [Pinecone 文件](https://docs.pinecone.io/docs/namespaces#:~:text=Pinecone%20allows%20you%20to%20partition,different%20subsets%20of%20your%20index.)。

如果想平行批次寫入 index 來加快速度，Pinecone 文件有一份很好的[平行批次寫入指南](https://docs.pinecone.io/docs/insert-data#sending-upserts-in-parallel)。

```python
# Models a simple batch generator that make chunks out of an input DataFrame
class BatchGenerator:
    
    
    def __init__(self, batch_size: int = 10) -> None:
        self.batch_size = batch_size
    
    # Makes chunks out of an input DataFrame
    def to_batches(self, df: pd.DataFrame) -> Iterator[pd.DataFrame]:
        splits = self.splits_num(df.shape[0])
        if splits <= 1:
            yield df
        else:
            for chunk in np.array_split(df, splits):
                yield chunk

    # Determines how many chunks DataFrame contains
    def splits_num(self, elements: int) -> int:
        return round(elements / self.batch_size)
    
    __call__ = to_batches

df_batcher = BatchGenerator(300)
```

```python
# Pick a name for the new index
index_name = 'wikipedia-articles'

# Check whether the index with the same name already exists - if so, delete it
if index_name in pinecone.list_indexes():
    pinecone.delete_index(index_name)
    
# Creates new index
pinecone.create_index(name=index_name, dimension=len(article_df['content_vector'][0]))
index = pinecone.Index(index_name=index_name)

# Confirm our index was created
pinecone.list_indexes()
```

??? note "輸出"

    ```text
    ['podcasts', 'wikipedia-articles']
    ```

```python
# Upsert content vectors in content namespace - this can take a few minutes
print("Uploading vectors to content namespace..")
for batch_df in df_batcher(article_df):
    index.upsert(vectors=zip(batch_df.vector_id, batch_df.content_vector), namespace='content')
```

??? note "輸出"

    ```text
    Uploading vectors to content namespace..
    ```

```python
# Upsert title vectors in title namespace - this can also take a few minutes
print("Uploading vectors to title namespace..")
for batch_df in df_batcher(article_df):
    index.upsert(vectors=zip(batch_df.vector_id, batch_df.title_vector), namespace='title')
```

??? note "輸出"

    ```text
    Uploading vectors to title namespace..
    ```

```python
# Check index size for each namespace to confirm all of our docs have loaded
index.describe_index_stats()
```

??? note "輸出"

    ```text
    {'dimension': 1536,
     'index_fullness': 0.1,
     'namespaces': {'content': {'vector_count': 25000},
                    'title': {'vector_count': 25000}},
     'total_vector_count': 50000}
    ```

### 搜尋資料

現在輸入幾個測試用的搜尋，確認能得到不錯的結果

```python
# First we'll create dictionaries mapping vector IDs to their outputs so we can retrieve the text for our search results
titles_mapped = dict(zip(article_df.vector_id,article_df.title))
content_mapped = dict(zip(article_df.vector_id,article_df.text))
```

```python
def query_article(query, namespace, top_k=5):
    '''Queries an article using its title in the specified
     namespace and prints results.'''

    # Create vector embeddings based on the title column
    embedded_query = openai.Embedding.create(
                                            input=query,
                                            model=EMBEDDING_MODEL,
                                            )["data"][0]['embedding']

    # Query namespace passed as parameter using title vector
    query_result = index.query(embedded_query, 
                                      namespace=namespace, 
                                      top_k=top_k)

    # Print query results 
    print(f'\nMost similar results to {query} in "{namespace}" namespace:\n')
    if not query_result.matches:
        print('no query result')
    
    matches = query_result.matches
    ids = [res.id for res in matches]
    scores = [res.score for res in matches]
    df = pd.DataFrame({'id':ids, 
                       'score':scores,
                       'title': [titles_mapped[_id] for _id in ids],
                       'content': [content_mapped[_id] for _id in ids],
                       })
    
    counter = 0
    for k,v in df.iterrows():
        counter += 1
        print(f'{v.title} (score = {v.score})')
    
    print('\n')

    return df
```

```python
query_output = query_article('modern art in Europe','title')
```

??? note "輸出"

    ```text

    Most similar results to modern art in Europe in "title" namespace:

    Museum of Modern Art (score = 0.875177085)
    Western Europe (score = 0.867441177)
    Renaissance art (score = 0.864156306)
    Pop art (score = 0.860346854)
    Northern Europe (score = 0.854658186)
    ```

```python
content_query_output = query_article("Famous battles in Scottish history",'content')
```

??? note "輸出"

    ```text

    Most similar results to Famous battles in Scottish history in "content" namespace:

    Battle of Bannockburn (score = 0.869336188)
    Wars of Scottish Independence (score = 0.861470938)
    1651 (score = 0.852588475)
    First War of Scottish Independence (score = 0.84962213)
    Robert I of Scotland (score = 0.846214116)
    ```

## 重點整理
- Pinecone 是託管式向量資料庫，不用自己維運，需要 API key。
- namespace 讓同一個 index 可以分割成不同子集，這裡拿來分開 title 和 content。
- 每個 namespace 獨立搜尋，所以可以選要對標題還是內文做語意比對。
- 大量寫入時可以平行批次 upsert 加速。

## 練習
1. 換一句自己的 query，分別搜 title 和 content namespace。
2. 改搜尋的 `top_k`，看回傳筆數和排序變化。
3. 新增第三個 namespace（例如只放文章前 200 字的摘要向量），並對它做搜尋。
