---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/chroma/Using_Chroma_for_embeddings_search.ipynb
---

# 用 Chroma 做 embedding 搜尋

> 原文：[examples/vector_databases/chroma/Using_Chroma_for_embeddings_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/chroma/Using_Chroma_for_embeddings_search.ipynb)

## 這篇在做什麼
走一遍完整流程：載入已經 embed 好的資料，建到 Chroma 這個向量資料庫，再用語意搜尋查詢。Chroma 是開源、可自架、預設跑在記憶體的向量資料庫。

## 學完你會
- 建立 Chroma client，並為 title 和 content 各建一個 collection
- 用 Chroma 內建的 OpenAI embedding function，讓它幫你處理 query 的 embedding
- 對 collection 下 query，再用 ID 對回原本的 dataframe 看結果

## 開跑前
需要 OpenAI API key（query 時會呼叫 embedding 模型）。

這個 notebook 帶你走一個簡單流程：下載資料、做 embedding，再用向量資料庫建索引並搜尋。很多客戶想在安全的環境裡儲存、搜尋自己資料的 embedding，來支援聊天機器人、主題建模等正式環境的用途，這就是常見的需求。

### 什麼是向量資料庫

向量資料庫是專門用來儲存、管理和搜尋 embedding 向量的資料庫。近年 AI 在自然語言、影像辨識等非結構化資料的應用越來越有效，把文字、音訊、影片等非結構化資料編碼成向量給機器學習模型使用的做法也快速成長，向量資料庫就成了企業落地這些應用並擴大規模的有效方案。

### 為什麼要用向量資料庫

向量資料庫讓企業能把這個 repo 裡分享過的許多 embedding 用例（例如問答、聊天機器人、推薦服務），放到安全、可擴展的環境中運行。很多客戶在小規模時 embedding 能解決問題，但效能和安全性擋住了上線，我們認為向量資料庫是解決這件事的關鍵元件。這份指南會走過基本流程：embed 文字資料、存進向量資料庫，並用來做語意搜尋。


### Demo 流程
流程如下：
- **設定**：import 套件、設定需要的變數
- **載入資料**：載入資料集，並用 OpenAI embedding 處理
- **Chroma**：
    - *設定*：這裡設定 Chroma 的 Python client，詳情看[這裡](https://docs.trychroma.com/usage-guide)
    - *建索引*：為 __title__ 和 __content__ 各建一個帶向量的 collection
    - *搜尋*：跑幾個搜尋確認可以正常運作

跑完這個 notebook，你應該對向量資料庫怎麼設定和使用有基本概念，之後可以進一步做更複雜、運用 embedding 的用例。

## 設定

import 需要的函式庫，並設定想用的 embedding 模型。

```python
# Make sure the OpenAI library is installed
%pip install openai

# We'll need to install the Chroma client
%pip install chromadb

# Install wget to pull zip file
%pip install wget

# Install numpy for data manipulation
%pip install numpy
```

??? note "輸出"

    ```text
    Collecting openai
      Obtaining dependency information for openai from https://files.pythonhosted.org/packages/67/78/7588a047e458cb8075a4089d721d7af5e143ff85a2388d4a28c530be0494/openai-0.27.8-py3-none-any.whl.metadata
      Downloading openai-0.27.8-py3-none-any.whl.metadata (13 kB)
    Collecting requests>=2.20 (from openai)
      Obtaining dependency information for requests>=2.20 from https://files.pythonhosted.org/packages/70/8e/0e2d847013cb52cd35b38c009bb167a1a26b2ce6cd6965bf26b47bc0bf44/requests-2.31.0-py3-none-any.whl.metadata
      Using cached requests-2.31.0-py3-none-any.whl.metadata (4.6 kB)
    Collecting tqdm (from openai)
      Using cached tqdm-4.65.0-py3-none-any.whl (77 kB)
    Collecting aiohttp (from openai)
      Obtaining dependency information for aiohttp from https://files.pythonhosted.org/packages/fa/9e/49002fde2a97d7df0e162e919c31cf13aa9f184537739743d1239edd0e67/aiohttp-3.8.5-cp310-cp310-macosx_11_0_arm64.whl.metadata
      Downloading aiohttp-3.8.5-cp310-cp310-macosx_11_0_arm64.whl.metadata (7.7 kB)
    Collecting charset-normalizer<4,>=2 (from requests>=2.20->openai)
      Obtaining dependency information for charset-normalizer<4,>=2 from https://files.pythonhosted.org/packages/ec/a7/96835706283d63fefbbbb4f119d52f195af00fc747e67cc54397c56312c8/charset_normalizer-3.2.0-cp310-cp310-macosx_11_0_arm64.whl.metadata
      Using cached charset_normalizer-3.2.0-cp310-cp310-macosx_11_0_arm64.whl.metadata (31 kB)
    Collecting idna<4,>=2.5 (from requests>=2.20->openai)
      Using cached idna-3.4-py3-none-any.whl (61 kB)
    Collecting urllib3<3,>=1.21.1 (from requests>=2.20->openai)
      Obtaining dependency information for urllib3<3,>=1.21.1 from https://files.pythonhosted.org/packages/9b/81/62fd61001fa4b9d0df6e31d47ff49cfa9de4af03adecf339c7bc30656b37/urllib3-2.0.4-py3-none-any.whl.metadata
      Downloading urllib3-2.0.4-py3-none-any.whl.metadata (6.6 kB)
    Collecting certifi>=2017.4.17 (from requests>=2.20->openai)
      Using cached certifi-2023.5.7-py3-none-any.whl (156 kB)
    Collecting attrs>=17.3.0 (from aiohttp->openai)
      Using cached attrs-23.1.0-py3-none-any.whl (61 kB)
    Collecting multidict<7.0,>=4.5 (from aiohttp->openai)
      Using cached multidict-6.0.4-cp310-cp310-macosx_11_0_arm64.whl (29 kB)
    Collecting async-timeout<5.0,>=4.0.0a3 (from aiohttp->openai)
      Using cached async_timeout-4.0.2-py3-none-any.whl (5.8 kB)
    Collecting yarl<2.0,>=1.0 (from aiohttp->openai)
      Using cached yarl-1.9.2-cp310-cp310-macosx_11_0_arm64.whl (62 kB)
    Collecting frozenlist>=1.1.1 (from aiohttp->openai)
      Obtaining dependency information for frozenlist>=1.1.1 from https://files.pythonhosted.org/packages/67/6a/55a49da0fa373ac9aa49ccd5b6393ecc183e2a0904d9449ea3ee1163e0b1/frozenlist-1.4.0-cp310-cp310-macosx_11_0_arm64.whl.metadata
      Downloading frozenlist-1.4.0-cp310-cp310-macosx_11_0_arm64.whl.metadata (5.2 kB)
    Collecting aiosignal>=1.1.2 (from aiohttp->openai)
      Using cached aiosignal-1.3.1-py3-none-any.whl (7.6 kB)
    Using cached openai-0.27.8-py3-none-any.whl (73 kB)
    Using cached requests-2.31.0-py3-none-any.whl (62 kB)
    Downloading aiohttp-3.8.5-cp310-cp310-macosx_11_0_arm64.whl (343 kB)
    [2K   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 343.9/343.9 kB 11.4 MB/s eta 0:00:00
    [?25hUsing cached charset_normalizer-3.2.0-cp310-cp310-macosx_11_0_arm64.whl (124 kB)
    Downloading frozenlist-1.4.0-cp310-cp310-macosx_11_0_arm64.whl (46 kB)
    ... (省略 141 行)
    ```

```python
import openai
import pandas as pd
import os
import wget
from ast import literal_eval

# Chroma's client library for Python
import chromadb

# I've set this to our new embeddings model, this can be changed to the embedding model of your choice
EMBEDDING_MODEL = "text-embedding-3-small"

# Ignore unclosed SSL socket warnings - optional in case you get these errors
import warnings

warnings.filterwarnings(action="ignore", message="unclosed", category=ResourceWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

## 載入資料

這一節載入我們事先準備好、已經 embed 完的資料。

```python
embeddings_url = 'https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip'

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

??? note "輸出"

    ```text
    'vector_database_wikipedia_articles_embedded.zip'
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

# Chroma

我們要把這些 embed 好的文件建到向量資料庫並搜尋。第一個選項是 **Chroma**，一個好上手、開源、可自架、跑在記憶體的向量資料庫，專門設計給 embedding 搭配 LLM 使用。

這一節會做：
- 建立 Chroma client
- 為每一類 embedding 建 collection
- 查詢每個 collection

### 建立 Chroma client

建立 Chroma client。預設 Chroma 是暫時性的，跑在記憶體裡。
不過你可以輕鬆設成持久化，把資料寫到磁碟。

```python
chroma_client = chromadb.EphemeralClient() # Equivalent to chromadb.Client(), ephemeral.
# Uncomment for persistent client
# chroma_client = chromadb.PersistentClient()
```

### 建立 collection

Chroma collection 可以儲存任意 metadata 並依它過濾，方便查詢 embed 資料的子集。

Chroma 已經整合了 OpenAI 的 embedding function，最好的用法是在建立 collection 時指定，如下。
你也可以改成 'bring your own embeddings'（自帶 embedding）。詳情看[這裡](https://docs.trychroma.com/embeddings)

```python
from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

# Test that your OpenAI API key is correctly set as an environment variable
# Note. if you run this notebook locally, you will need to reload your terminal and the notebook for the env variables to be live.

# Note. alternatively you can set a temporary env variable like this:
# os.environ["OPENAI_API_KEY"] = 'sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'

if os.getenv("OPENAI_API_KEY") is not None:
    openai.api_key = os.getenv("OPENAI_API_KEY")
    print ("OPENAI_API_KEY is ready")
else:
    print ("OPENAI_API_KEY environment variable not found")


embedding_function = OpenAIEmbeddingFunction(api_key=os.environ.get('OPENAI_API_KEY'), model_name=EMBEDDING_MODEL)

wikipedia_content_collection = chroma_client.create_collection(name='wikipedia_content', embedding_function=embedding_function)
wikipedia_title_collection = chroma_client.create_collection(name='wikipedia_titles', embedding_function=embedding_function)
```

??? note "輸出"

    ```text
    OPENAI_API_KEY is ready
    ```

### 填入 collection

Chroma collection 可以填入任何你想要的 metadata 並依它過濾。需要的話，Chroma 也能把文字跟向量一起存，並在單一個 `query` 呼叫裡一起回傳。

這個用例我們只存 embedding 和 ID，再用 ID 去對回原本的 dataframe。

```python
# Add the content vectors
wikipedia_content_collection.add(
    ids=article_df.vector_id.tolist(),
    embeddings=article_df.content_vector.tolist(),
)

# Add the title vectors
wikipedia_title_collection.add(
    ids=article_df.vector_id.tolist(),
    embeddings=article_df.title_vector.tolist(),
)
```

### 搜尋 collection

如果有設定 embedding function（像這個範例），Chroma 會幫你處理 query 的 embedding。

```python
def query_collection(collection, query, max_results, dataframe):
    results = collection.query(query_texts=query, n_results=max_results, include=['distances']) 
    df = pd.DataFrame({
                'id':results['ids'][0], 
                'score':results['distances'][0],
                'title': dataframe[dataframe.vector_id.isin(results['ids'][0])]['title'],
                'content': dataframe[dataframe.vector_id.isin(results['ids'][0])]['text'],
                })
    
    return df
```

```python
title_query_result = query_collection(
    collection=wikipedia_title_collection,
    query="modern art in Europe",
    max_results=10,
    dataframe=article_df
)
title_query_result.head()
```

??? note "輸出"

    ```text
              id     score            title  \
    2      23266  0.249646              Art   
    11777  15436  0.271688  Hellenistic art   
    12178  23265  0.279306    Byzantine art   
    13215  11777  0.294415         Art film   
    15436  22108  0.305937  Renaissance art   

                                                     content  
    2      Art is a creative activity that expresses imag...  
    11777  The art of the Hellenistic time (from 400 B.C....  
    12178  Byzantine art is a form of Christian Greek art...  
    13215  Art films are a type of movie that is very dif...  
    15436  Many of the most famous and best-loved works o...
    ```

```python
content_query_result = query_collection(
    collection=wikipedia_content_collection,
    query="Famous battles in Scottish history",
    max_results=10,
    dataframe=article_df
)
content_query_result.head()
```

??? note "輸出"

    ```text
              id     score            title  \
    2923   13135  0.261328             1651   
    3694   13571  0.277058         Stirling   
    6248    2923  0.294823              841   
    6297   13568  0.300756             1746   
    11702  11708  0.307572  William Wallace   

                                                     content  
    2923   \n\nEvents \n January 1 – Charles II crowned K...  
    3694   Stirling () is a city in the middle of Scotlan...  
    6248   \n\nEvents \n June 25: Battle of Fontenay – Lo...  
    6297   \n\nEvents \n January 8 – Bonnie Prince Charli...  
    11702  William Wallace was a Scottish knight who foug...
    ```

現在你已經有一個基本的 embedding 搜尋了，可以[前往 Chroma 文件](https://docs.trychroma.com/usage-guide#using-where-filters)，學更多怎麼在 query 加過濾條件、更新 / 刪除 collection 裡的資料，以及怎麼部署 Chroma。

## 重點整理
- 向量資料庫專門存、管、搜 embedding，是 embedding 應用走向正式環境的關鍵元件。
- Chroma 預設跑在記憶體，要保存資料就改成持久化設定。
- collection 在建立時指定 OpenAI embedding function，query 時就不用自己算 embedding。
- title 和 content 各建一個 collection，可以分別對不同欄位做語意搜尋。
- collection 可以只存向量和 ID，再用 ID 回頭對原始 dataframe。

## 練習
1. 換一句自己的 query 搜尋 title collection，再搜 content collection，比較結果差異。
2. 改 query 的結果筆數（`n_results`），看回傳數量和排序變化。
3. 把 client 改成持久化設定，重跑兩次，確認第二次不用重建 collection 也能查。
