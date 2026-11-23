---
translated: true
source: examples/vector_databases/redis/redisqna/redisqna.ipynb
---

# 用 Redis 當 Chat Completions 的 context store

> 原文：[examples/vector_databases/redis/redisqna/redisqna.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/redis/redisqna/redisqna.ipynb)



## 這篇在做什麼

示範把 Redis 當成 ChatGPT 的高速 context 記憶體。先證明模型對知識截止日期之後的事件答不好，再把截止日期之後的新聞文章存進 Redis，用向量搜尋找出最相關的文件，加進 prompt，得到完全不同的回答。

## 學完你會

- 觀察模型在知識截止日期之後的主題上怎麼出錯
- 在 Redis 建立向量索引，並把文字和 embedding 以 JSON 物件存進去
- 把問題轉成 embedding、做 KNN 搜尋，再把找到的文件當 context 重新問模型

## 開跑前

- 一個有 Redis Search 和 Redis JSON 模組的 Redis 實例（可用 Redis Stack Docker container）
- Redis-py 和 OpenAI Python client 函式庫
- OpenAI API key，放在 `.env` 檔

這份 notebook 示範如何把 Redis 當成搭配 ChatGPT 的高速 context 記憶體。

## 前置需求
* 有 Redis Search 和 Redis JSON 模組的 Redis 實例
* Redis-py client 函式庫
* OpenAI Python client 函式庫
* OpenAI API key

## 安裝
安裝範例需要的 Python 模組。

```python
! pip install -q redis openai python-dotenv 'openai[datalib]'
```

## OpenAI API Key
建立一個 .env 檔，把你的 OpenAI key 加進去

```python
OPENAI_API_KEY=your_key
```

## OpenAI 設定
載入 key，並定義 chat completion 的 helper 函式

```python
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
oai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def get_completion(prompt, model="gpt-3.5-turbo"):
    messages = [{"role": "user", "content": prompt}]
    response = oai_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content
```

## 實驗：問一個超出模型知識截止日期的主題
Gpt-3.5-turbo 的訓練資料到 2021 年 9 月為止。我們來問它一個超過這個日期的事，這裡用的是 FTX/Sam Bankman-Fried 的醜聞。這裡為了示範用了舊模型，較新的模型如 gpt-4o 知識截止日期較晚（2023 年底），也適用這個範例。

```python
prompt = "Is Sam Bankman-Fried's company, FTX, considered a well-managed company?"
response = get_completion(prompt)
print(response)
```

??? note "輸出"

    ```text
    Yes, FTX is generally considered a well-managed company. Sam Bankman-Fried, the founder and CEO of FTX, has a strong track record in the cryptocurrency industry and has successfully grown the company into one of the leading cryptocurrency exchanges in the world. FTX has also received positive reviews for its user-friendly platform, innovative products, and strong customer service. Additionally, FTX has been proactive in regulatory compliance and has taken steps to ensure the security of its users' funds. Overall, FTX is seen as a well-managed company in the cryptocurrency space.
    ```

## 資訊不完整
這類 AI 系統有個不好的行為：即使對結果沒把握，它也會給出聽起來很有信心的回答。減輕這個問題的方法之一是重新設計 prompt，如下所示。

```python
prompt ="Is Sam Bankman-Fried's company, FTX, considered a well-managed company?  If you don't know for certain, say unknown."
response = get_completion(prompt)
print(response)
```

??? note "輸出"

    ```text
    FTX is generally considered a well-managed company. Sam Bankman-Fried, the founder and CEO, has a strong reputation in the cryptocurrency industry for his leadership and strategic vision. FTX has also experienced significant growth and success since its founding in 2017. However, without specific insider knowledge or data, it is ultimately unknown whether FTX is definitively considered a well-managed company.
    ```

## 補充 Context
對付資訊不完整的另一個方法，是給系統更多資訊，讓它能做出聰明的判斷，而不是用猜的。我們會用 Redis 當這些額外 context 的來源。我們會拉進 GPT 知識截止日期之後的商業新聞文章，讓系統更了解 FTX 實際上是怎麼被經營的。

## 啟動 Redis Stack Docker container

```python
! docker compose up -d
```

## 連接 Redis client

```python
from redis import from_url

REDIS_URL = 'redis://localhost:6379'
client = from_url(REDIS_URL)
client.ping()
```

??? note "輸出"

    ```text
    True
    ```

## 建立索引
[FT.CREATE](https://redis.io/commands/ft.create/)

```python
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType

schema = [ VectorField('$.vector', 
            "FLAT", 
            {   "TYPE": 'FLOAT32', 
                "DIM": 1536, 
                "DISTANCE_METRIC": "COSINE"
            },  as_name='vector' ),
            TextField('$.content', as_name='content')
        ]
idx_def = IndexDefinition(index_type=IndexType.JSON, prefix=['doc:'])
try: 
    client.ft('idx').dropindex()
except:
    pass
client.ft('idx').create_index(schema, definition=idx_def)
```

??? note "輸出"

    ```text
    b'OK'
    ```

## 把資料檔載入 Redis，存成含文字和向量欄位的 JSON 物件
[Redis JSON](https://redis.io/docs/stack/json/)

```python
directory = './assets/'
model = 'text-embedding-3-small'
i = 1

for file in os.listdir(directory):
    with open(os.path.join(directory, file), 'r') as f:
        content = f.read()
        # Create the embedding using the new client-based method
        response = oai_client.embeddings.create(
            model=model,
            input=[content]
        )
        # Access the embedding from the response object
        vector = response.data[0].embedding
        
        # Store the content and vector using your JSON client
        client.json().set(f'doc:{i}', '$', {'content': content, 'vector': vector})
    i += 1
```

## 把問題 embed，並做 VSS 找出最相關的文件
[KNN Search](https://redis.io/docs/stack/search/reference/vectors/#knn-search)

```python
from redis.commands.search.query import Query
import numpy as np

response = oai_client.embeddings.create(
    input=[prompt],
    model=model
)
# Extract the embedding vector from the response
embedding_vector = response.data[0].embedding

# Convert the embedding to a numpy array of type float32 and then to bytes
vec = np.array(embedding_vector, dtype=np.float32).tobytes()

# Build and execute the Redis query
q = Query('*=>[KNN 1 @vector $query_vec AS vector_score]') \
    .sort_by('vector_score') \
    .return_fields('content') \
    .dialect(2)
params = {"query_vec": vec}

context = client.ft('idx').search(q, query_params=params).docs[0].content
print(context)
```

## 帶著 context 重新問 OpenAI 同一個問題
現在有了相關的 context，把它加進給 OpenAI 的 prompt，就能得到很不一樣的回答。

````python
prompt = f"""
Using the information delimited by triple backticks, answer this question: Is Sam Bankman-Fried's company, FTX, considered a well-managed company?

Context: ```{context}```
"""

response = get_completion(prompt)
print(response)
````

??? note "輸出"

    ```text
    Based on the information provided, FTX, Sam Bankman-Fried's company, is not considered a well-managed company. The company has faced bankruptcy proceedings, mishandling of customer funds, unauthorized transactions, freezing of assets by regulatory authorities, and a lack of trustworthy financial information. The new CEO, John J. Ray III, described the situation as a "complete failure of corporate controls" and indicated gross mismanagement. Additionally, the company's financial situation, lack of record-keeping, and use of inadequate accounting tools despite handling billions of dollars have raised serious concerns about its management practices.
    ```

## 重點整理

- 模型的知識有截止日期，超過的主題它會答不好，卻可能講得很有自信。
- 只改 prompt 能降低過度自信，但無法補上沒有的知識。
- 檢索增強的做法是把外部資料轉成 embedding 存起來，查詢時找最相關的內容放進 prompt。
- Redis 同時扮演向量索引和 JSON 文件儲存，查詢速度快。

## 練習

1. 把實驗問題換成別的截止日期之後的事件，觀察模型沒有 context 時的回答。
2. 修改 prompt，要求模型沒把握就直接說不知道，看回答怎麼改變。
3. 調整 KNN 搜尋回傳的文件數量，把多篇文件都放進 context，比較答案是否更完整。
