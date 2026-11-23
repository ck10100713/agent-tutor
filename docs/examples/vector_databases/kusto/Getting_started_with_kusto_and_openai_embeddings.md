---
translated: true
source: examples/vector_databases/kusto/Getting_started_with_kusto_and_openai_embeddings.ipynb
---

# 用 Kusto 當 embedding 的向量資料庫

> 原文：[examples/vector_databases/kusto/Getting_started_with_kusto_and_openai_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/kusto/Getting_started_with_kusto_and_openai_embeddings.ipynb)



## 這篇在做什麼

示範把 Azure Data Explorer（Kusto）當成向量資料庫，搭配 OpenAI embedding。流程是載入預先算好的 Wikipedia embedding、存進 Kusto、用 OpenAI 把查詢轉成 embedding，再用 Kusto 做 cosine similarity 搜尋。

## 學完你會

- 把 DataFrame 裡的向量透過 Spark 寫進 Kusto 資料表
- 用 Azure OpenAI 或 OpenAI 產生查詢的 embedding，並選對模型
- 用 `series-cosine-similarity-fl` 這個 UDF 在 Kusto 裡找最相近的向量

## 開跑前

- 一個 Azure Data Explorer（Kusto）伺服器實例
- Azure OpenAI 憑證，或 OpenAI API key
- 在資料庫裡先建好 `series-cosine-similarity-fl` 函式

這份 notebook 一步一步說明如何用 Azure Data Explorer（Kusto）當向量資料庫，搭配 OpenAI embedding。

這份 notebook 呈現的是端到端的流程：

1. 使用 OpenAI API 預先算好的 embedding。
2. 把 embedding 存進 Kusto。
3. 用 OpenAI API 把原始文字查詢轉成 embedding。
4. 用 Kusto 對儲存的 embedding 做 cosine similarity 搜尋。


### 前置需求

這次練習需要先準備幾樣東西：

1. Azure Data Explorer(Kusto) 伺服器實例。https://azure.microsoft.com/en-us/products/data-explorer
3. Azure OpenAI 憑證或 OpenAI API key。

```python
%pip install wget
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, -1, Finished, Available)
    ```

    ```text
    Collecting wget
      Downloading wget-3.2.zip (10 kB)
      Preparing metadata (setup.py) ... [?25ldone
    [?25hBuilding wheels for collected packages: wget
      Building wheel for wget (setup.py) ... [?25l- done
    [?25h  Created wheel for wget: filename=wget-3.2-py3-none-any.whl size=9657 sha256=10fd8aa1d20fd49c36389dc888acc721d0578c5a0635fc9fc5dc642c0f49522e
      Stored in directory: /home/trusted-service-user/.cache/pip/wheels/8b/f1/7f/5c94f0a7a505ca1c81cd1d9208ae2064675d97582078e6c769
    Successfully built wget
    Installing collected packages: wget
    Successfully installed wget-3.2

    [notice] A new release of pip is available: 23.0 -> 23.1.2
    [notice] To update, run: /nfs4/pyenv-27214bb4-edfd-4fdd-b888-8a99075a1416/bin/python -m pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

    ```text
    Warning: PySpark kernel has been restarted to use updated packages.
    ```

```python
%pip install openai
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, -1, Finished, Available)
    ```

    ```text
    Collecting openai
      Downloading openai-0.27.6-py3-none-any.whl (71 kB)
    [2K     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 71.9/71.9 kB 1.7 MB/s eta 0:00:0000:01
    [?25hRequirement already satisfied: tqdm in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from openai) (4.65.0)
    Requirement already satisfied: requests>=2.20 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from openai) (2.28.2)
    Requirement already satisfied: aiohttp in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from openai) (3.8.4)
    Requirement already satisfied: urllib3<1.27,>=1.21.1 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.20->openai) (1.26.14)
    Requirement already satisfied: certifi>=2017.4.17 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.20->openai) (2022.12.7)
    Requirement already satisfied: idna<4,>=2.5 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.20->openai) (3.4)
    Requirement already satisfied: charset-normalizer<4,>=2 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.20->openai) (2.1.1)
    Requirement already satisfied: attrs>=17.3.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from aiohttp->openai) (22.2.0)
    Requirement already satisfied: frozenlist>=1.1.1 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from aiohttp->openai) (1.3.3)
    Requirement already satisfied: multidict<7.0,>=4.5 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from aiohttp->openai) (6.0.4)
    Requirement already satisfied: yarl<2.0,>=1.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from aiohttp->openai) (1.8.2)
    Requirement already satisfied: async-timeout<5.0,>=4.0.0a3 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from aiohttp->openai) (4.0.2)
    Requirement already satisfied: aiosignal>=1.1.2 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from aiohttp->openai) (1.3.1)
    Installing collected packages: openai
    Successfully installed openai-0.27.6

    [notice] A new release of pip is available: 23.0 -> 23.1.2
    [notice] To update, run: /nfs4/pyenv-27214bb4-edfd-4fdd-b888-8a99075a1416/bin/python -m pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

    ```text
    Warning: PySpark kernel has been restarted to use updated packages.
    ```

```python
%pip install azure-kusto-data
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, -1, Finished, Available)
    ```

    ```text
    Requirement already satisfied: azure-kusto-data in /nfs4/pyenv-27214bb4-edfd-4fdd-b888-8a99075a1416/lib/python3.10/site-packages (4.1.4)
    Requirement already satisfied: msal<2,>=1.9.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-kusto-data) (1.21.0)
    Requirement already satisfied: python-dateutil>=2.8.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-kusto-data) (2.8.2)
    Requirement already satisfied: azure-core<2,>=1.11.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-kusto-data) (1.26.4)
    Requirement already satisfied: requests>=2.13.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-kusto-data) (2.28.2)
    Requirement already satisfied: ijson~=3.1 in /nfs4/pyenv-27214bb4-edfd-4fdd-b888-8a99075a1416/lib/python3.10/site-packages (from azure-kusto-data) (3.2.0.post0)
    Requirement already satisfied: azure-identity<2,>=1.5.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-kusto-data) (1.12.0)
    Requirement already satisfied: six>=1.11.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-core<2,>=1.11.0->azure-kusto-data) (1.16.0)
    Requirement already satisfied: typing-extensions>=4.3.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-core<2,>=1.11.0->azure-kusto-data) (4.5.0)
    Requirement already satisfied: cryptography>=2.5 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-identity<2,>=1.5.0->azure-kusto-data) (40.0.1)
    Requirement already satisfied: msal-extensions<2.0.0,>=0.3.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from azure-identity<2,>=1.5.0->azure-kusto-data) (1.0.0)
    Requirement already satisfied: PyJWT[crypto]<3,>=1.0.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from msal<2,>=1.9.0->azure-kusto-data) (2.6.0)
    Requirement already satisfied: urllib3<1.27,>=1.21.1 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.13.0->azure-kusto-data) (1.26.14)
    Requirement already satisfied: charset-normalizer<4,>=2 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.13.0->azure-kusto-data) (2.1.1)
    Requirement already satisfied: idna<4,>=2.5 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.13.0->azure-kusto-data) (3.4)
    Requirement already satisfied: certifi>=2017.4.17 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from requests>=2.13.0->azure-kusto-data) (2022.12.7)
    Requirement already satisfied: cffi>=1.12 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from cryptography>=2.5->azure-identity<2,>=1.5.0->azure-kusto-data) (1.15.1)
    Requirement already satisfied: portalocker<3,>=1.0 in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from msal-extensions<2.0.0,>=0.3.0->azure-identity<2,>=1.5.0->azure-kusto-data) (2.7.0)
    Requirement already satisfied: pycparser in /home/trusted-service-user/cluster-env/trident_env/lib/python3.10/site-packages (from cffi>=1.12->cryptography>=2.5->azure-identity<2,>=1.5.0->azure-kusto-data) (2.21)

    [notice] A new release of pip is available: 23.0 -> 23.1.2
    [notice] To update, run: /nfs4/pyenv-27214bb4-edfd-4fdd-b888-8a99075a1416/bin/python -m pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

    ```text
    Warning: PySpark kernel has been restarted to use updated packages.
    ```

### 下載預先算好的 Embedding



這一節會載入準備好的 embedding 資料，你不需要花自己的額度重算 Wikipedia 文章的 embedding。


```python
import wget

embeddings_url = "https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip"

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 17, Finished, Available)
    ```

    ```text
    'vector_database_wikipedia_articles_embedded.zip'
    ```

```python

import zipfile

with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip","r") as zip_ref:
    zip_ref.extractall("/lakehouse/default/Files/data")
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 18, Finished, Available)
    ```

```python
import pandas as pd

from ast import literal_eval

article_df = pd.read_csv('/lakehouse/default/Files/data/vector_database_wikipedia_articles_embedded.csv')
# Read vectors from strings back into a list
article_df["title_vector"] = article_df.title_vector.apply(literal_eval)
article_df["content_vector"] = article_df.content_vector.apply(literal_eval)
article_df.head()
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 19, Finished, Available)
    ```

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

### 把向量存進 Kusto 資料表


根據 dataframe 的內容，在 Kusto 建立資料表並載入向量。spark 選項 CreakeIfNotExists 會在資料表不存在時自動建立。


```python
# replace with your AAD Tenant ID, Kusto Cluster URI, Kusto DB name and Kusto Table
AAD_TENANT_ID = ""
KUSTO_CLUSTER =  ""
KUSTO_DATABASE = "Vector"
KUSTO_TABLE = "Wiki"
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 37, Finished, Available)
    ```

```python

kustoOptions = {"kustoCluster": KUSTO_CLUSTER, "kustoDatabase" :KUSTO_DATABASE, "kustoTable" : KUSTO_TABLE }

# Replace the auth method based on your desired authentication mechanism  - https://github.com/Azure/azure-kusto-spark/blob/master/docs/Authentication.md
access_token=mssparkutils.credentials.getToken(kustoOptions["kustoCluster"])
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 21, Finished, Available)
    ```

```python
#Pandas data frame to spark dataframe
sparkDF=spark.createDataFrame(article_df)
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 22, Finished, Available)
    ```

    ```text
    /opt/spark/python/lib/pyspark.zip/pyspark/sql/pandas/conversion.py:604: FutureWarning: iteritems is deprecated and will be removed in a future version. Use .items instead.
    ```

```python
# Write data to a Kusto table
sparkDF.write. \
format("com.microsoft.kusto.spark.synapse.datasource"). \
option("kustoCluster",kustoOptions["kustoCluster"]). \
option("kustoDatabase",kustoOptions["kustoDatabase"]). \
option("kustoTable", kustoOptions["kustoTable"]). \
option("accessToken", access_token). \
option("tableCreateOptions", "CreateIfNotExist").\
mode("Append"). \
save()
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 23, Finished, Available)
    ```

### 設定 OpenAI API key
# 

OpenAI API key 用來把文件和查詢向量化。可以照說明建立並取得 Azure OpenAI 的 key 和 endpoint。https://learn.microsoft.com/en-us/azure/cognitive-services/openai/tutorials/embeddings


請務必使用 `text-embedding-3-small` 模型。預先算好的 embedding 是用 `text-embedding-3-small` 建的，所以搜尋時也必須用同一個模型。


```python
import openai
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 43, Finished, Available)
    ```

#### 如果用 Azure Open AI

```python
openai.api_version = '2022-12-01'
openai.api_base = '' # Please add your endpoint here
openai.api_type = 'azure'
openai.api_key = ''  # Please add your api key here

def embed(query):
    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
            input=query,
            deployment_id="embed", #replace with your deployment id
            chunk_size=1
    )["data"][0]["embedding"]
    return embedded_query
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 44, Finished, Available)
    ```

#### 如果用 Open AI

只有打算用 Open AI 做 embedding 時才執行這個 cell

```python
openai.api_key = ""


def embed(query):
    # Creates embedding vector from user query
    embedded_query = openai.Embedding.create(
        input=query,
        model="text-embedding-3-small",
    )["data"][0]["embedding"]
    return embedded_query
```

### 為搜尋詞產生 embedding

```python

searchedEmbedding = embed("places where you worship")
#print(searchedEmbedding)
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 45, Finished, Available)
    ```

#### 在 Kusto 做語意搜尋

我們會在 Kusto 資料表裡搜尋最接近的向量。

相似度搜尋會用 series-cosine-similarity-fl 這個 UDF。

繼續之前，請先在你的資料庫建立這個函式：
https://learn.microsoft.com/en-us/azure/data-explorer/kusto/functions-library/series-cosine-similarity-fl?tabs=query-defined

```python
from azure.kusto.data import KustoClient, KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError
from azure.kusto.data.helpers import dataframe_from_result_table
import pandas as pd
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 35, Finished, Available)
    ```

```python
KCSB = KustoConnectionStringBuilder.with_aad_device_authentication(
    KUSTO_CLUSTER)
KCSB.authority_id = AAD_TENANT_ID
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 38, Finished, Available)
    ```

```python
KUSTO_CLIENT = KustoClient(KCSB)
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 39, Finished, Available)
    ```

```python
KUSTO_QUERY = "Wiki | extend similarity = series_cosine_similarity_fl(dynamic("+str(searchedEmbedding)+"), content_vector,1,1) | top 10 by similarity desc "

RESPONSE = KUSTO_CLIENT.execute(KUSTO_DATABASE, KUSTO_QUERY)
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 48, Finished, Available)
    ```

```python
df = dataframe_from_result_table(RESPONSE.primary_results[0])
df
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 49, Finished, Available)
    ```

    ```text
          id                                                url  \
    0    852           https://simple.wikipedia.org/wiki/Temple   
    1  78094  https://simple.wikipedia.org/wiki/Christian%20...   
    2  59154  https://simple.wikipedia.org/wiki/Service%20of...   
    3  51910          https://simple.wikipedia.org/wiki/Worship   
    4  29576            https://simple.wikipedia.org/wiki/Altar   
    5  92507           https://simple.wikipedia.org/wiki/Shrine   
    6    815        https://simple.wikipedia.org/wiki/Synagogue   
    7  68080  https://simple.wikipedia.org/wiki/Shinto%20shrine   
    8  57790           https://simple.wikipedia.org/wiki/Chapel   
    9    142  https://simple.wikipedia.org/wiki/Church%20%28...   

                    title                                               text  \
    0              Temple  A temple is a building where people go to prac...   
    1   Christian worship  In Christianity, worship has been thought as b...   
    2  Service of worship  A service of worship is a religious meeting wh...   
    3             Worship  Worship is a word often used in religion.  It ...   
    4               Altar  An altar is a place, often a table, where a re...   
    5              Shrine  A shrine is a holy or sacred place with someth...   
    6           Synagogue  A synagogue is a place where Jews meet to wors...   
    7       Shinto shrine  A Shinto shrine is a sacred place or site wher...   
    8              Chapel  A chapel is a place for Christian worship. The...   
    9   Church (building)  A church is a building that was constructed to...   

                                            title_vector  \
    0  [-0.021837441250681877, -0.007722342386841774,...   
    1  [0.0017675267299637198, -0.008890199474990368,...   
    2  [-0.007969820871949196, 0.0004240311391185969,...   
    3  [0.0036036288365721703, -0.01276545226573944, ...   
    4  [0.007887467741966248, -0.02706138789653778, -...   
    5  [-0.011601685546338558, 0.006366696208715439, ...   
    6  [-0.017317570745944977, 0.0022673190105706453,...   
    7  [0.0035740730818361044, 0.0028098472394049168,...   
    8  [-0.01371884811669588, 0.0031672674231231213, ...   
    9  [0.0021336888894438744, 0.0029748091474175453,...   

                                          content_vector  vector_id  similarity  
    0  [-0.0019541378132998943, 0.007151313126087189,...        413    0.834495  
    1  [0.020530683919787407, 0.0024345638230443, -0....      20320    0.832132  
    2  [0.003784010885283351, -0.0030924836173653603,...      15519    0.831633  
    ... (省略 7 行)
    ```

```python
searchedEmbedding = embed("unfortunate events in history")
```

```python
KUSTO_QUERY = "Wiki | extend similarity = series_cosine_similarity_fl(dynamic("+str(searchedEmbedding)+"), title_vector,1,1) | top 10 by similarity desc "
RESPONSE = KUSTO_CLIENT.execute(KUSTO_DATABASE, KUSTO_QUERY)

df = dataframe_from_result_table(RESPONSE.primary_results[0])
df
```

??? note "輸出"

    ```text
    StatementMeta(, 7e5070d2-4560-4fb8-a3a8-6a594acd58ab, 52, Finished, Available)
    ```

    ```text
          id                                                url  \
    0    848          https://simple.wikipedia.org/wiki/Tragedy   
    1   4469  https://simple.wikipedia.org/wiki/The%20Holocaust   
    2  64216  https://simple.wikipedia.org/wiki/List%20of%20...   
    3   4397  https://simple.wikipedia.org/wiki/List%20of%20...   
    4  23073         https://simple.wikipedia.org/wiki/Disaster   
    5   4382  https://simple.wikipedia.org/wiki/List%20of%20...   
    6  13528  https://simple.wikipedia.org/wiki/A%20Series%2...   
    7  42874  https://simple.wikipedia.org/wiki/History%20of...   
    8   4452         https://simple.wikipedia.org/wiki/Accident   
    9    324          https://simple.wikipedia.org/wiki/History   

                                title  \
    0                         Tragedy   
    1                   The Holocaust   
    2      List of historical plagues   
    3               List of disasters   
    4                        Disaster   
    5     List of terrorist incidents   
    6  A Series of Unfortunate Events   
    7            History of the world   
    8                        Accident   
    9                         History   

                                                    text  \
    0  In theatre, a tragedy as defined by Aristotle ...   
    1  The Holocaust, sometimes called The Shoah (), ...   
    2  This list contains famous or well documented o...   
    3  This is a list of disasters, both natural and ...   
    4  A disaster is something very not good that hap...   
    5  The following is a list by date of acts and fa...   
    6  A Series of Unfortunate Events is a series of ...   
    7  The history of the world (also called human hi...   
    8  An accident is when something goes wrong when ...   
    9  History is the study of past events. People kn...   

                                            title_vector  \
    0  [-0.019502468407154083, -0.010160734876990318,...   
    1  [-0.030233195051550865, -0.024401605129241943,...   
    2  [-0.010667890310287476, -0.0003575817099772393...   
    ... (省略 19 行)
    ```

## 重點整理

- Kusto 沒有專門的向量索引，靠 cosine similarity 的 UDF 在儲存的向量上算相似度。
- 預先算好的 embedding 讓你省下重算的成本，但查詢必須用同一個模型（`text-embedding-3-small`）。
- Azure OpenAI 和 OpenAI 都能產生查詢 embedding，差別在認證與 endpoint 設定。
- 流程跟其他向量資料庫一致：存向量、查詢轉向量、比相似度。

## 練習

1. 換一個搜尋詞，看回傳的文章是否相關。
2. 調整查詢回傳的筆數上限，觀察結果變化。
3. 刻意改用另一個 embedding 模型產生查詢向量，看結果為什麼會變差。
