---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/vector_databases/cassandra_astradb/Philosophical_Quotes_CQL.ipynb
---
# Philosophy with vector embeddings, OpenAI and Cassandra / Astra DB

> 原文：[examples/vector_databases/cassandra_astradb/Philosophical_Quotes_CQL.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_CQL.ipynb)



## 這篇在做什麼

這篇用 OpenAI embedding 加 Cassandra（或透過 CQL 使用的 DataStax Astra DB）當 vector store，做一個「哲學名言搜尋加生成器」。你會把一批哲學家的名言轉成 embedding 存進資料庫，用來做語意搜尋，再把搜尋結果餵給 LLM 生成新的名言。

## 學完你會

- 用 CQL 建立帶 vector 欄位的 table，並建立 ANN 搜尋以及 author / tag 篩選用的 index
- 批次呼叫 OpenAI embedding 並寫入 Cassandra，做出可依作者、tag 和相似度門檻過濾的搜尋 function
- 把搜尋結果塞進 prompt，用 chat completion 生成新名言，並用 partition 加速單一作者的查詢

## 開跑前

- 一個 Astra DB 帳號與資料庫（或任何支援 Vector 的 Cassandra cluster），需要 Secure Connect Bundle 與 token
- OpenAI API Key

### CQL 版本

在這個 quickstart 裡，你會用 OpenAI 的 vector embedding 和 [Apache Cassandra®](https://cassandra.apache.org)（或等價的 DataStax [Astra DB through CQL](https://docs.datastax.com/en/astra-serverless/docs/vector-search/quickstart.html)）當 vector store 做資料持久化，打造一個「哲學名言搜尋與生成器」。

這個 notebook 的基本流程如下：先計算並儲存一批知名哲學家名言的 vector embedding，用它們做出強大的搜尋引擎，接著甚至做出新名言的生成器！

這個 notebook 示範了 vector search 的幾種標準用法，也展示了 [Cassandra](https://cassandra.apache.org/doc/trunk/cassandra/vector-search/overview.html) / [Astra DB through CQL](https://docs.datastax.com/en/astra-serverless/docs/vector-search/quickstart.html) 的 vector 功能有多容易上手。

想了解如何用 vector search 和文字 embedding 做問答系統，可以看這個很棒的實作 notebook：[Question answering using embeddings](https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_embeddings.ipynb)。

#### _選擇你的框架_

注意這個 notebook 用的是 [Cassandra drivers](https://docs.datastax.com/en/developer/python-driver/latest/)，直接執行 CQL（Cassandra Query Language）語句，不過同樣的事也可以用其他技術完成。其他選項請看這個資料夾的 [README](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases/cassandra_astradb)。這個 notebook 可以在 Colab 或一般 Jupyter notebook 執行。

目錄：
- Setup
- Get DB connection
- Connect to OpenAI
- Load quotes into the Vector Store
- Use case 1: **quote search engine**
- Use case 2: **quote generator**
- (Optional) exploit partitioning in the Vector Store

### 運作方式

**Indexing**

每則名言都用 OpenAI 的 `Embedding` 轉成 embedding vector，存進 Vector Store 供之後搜尋。旁邊還會存一些 metadata，包括作者名字和幾個預先算好的 tag，讓搜尋可以客製。

![1_vector_indexing_cql](https://user-images.githubusercontent.com/14221764/282437237-1e763166-a863-4332-99b8-323ba23d1b87.png)

**Search**

要找跟輸入名言相似的名言，會先即時把輸入轉成 embedding vector，再用這個 vector 去查詢 store 裡相似的 vector，也就是之前 index 過的相似名言。搜尋還可以再用 metadata 限制（「找 Spinoza 寫的、跟這句相似的名言……」）。

![2_vector_search_cql](https://user-images.githubusercontent.com/14221764/282437291-85335612-a845-444e-bed7-e4cf014a9f17.png)

關鍵在於「內容相似的名言」在 vector 空間裡會變成距離相近的 vector，所以 vector 相似度搜尋實際上就是在做語意相似度比對。_這就是 vector embedding 這麼強大的主因。_

下面的示意圖想傳達這個概念。每則名言轉成 vector 之後，就是空間裡的一個點。其實是在一個球面上，因為 OpenAI 的 embedding vector 跟大多數模型一樣，都被正規化成_單位長度_。而且這個球面不是三維，是 1536 維！

所以本質上，在 vector 空間做相似度搜尋，就是回傳離 query vector 最近的 vector：

![3_vector_space](https://user-images.githubusercontent.com/14221764/262321363-c8c625c1-8be9-450e-8c68-b1ed518f990d.png)

**Generation**

給一個提示（主題或一句草稿名言），先做搜尋，再把前幾筆結果（名言）餵進 LLM 的 prompt，請生成模型照著這些範例_和_最初的提示，發明一段新文字。

![4_quote_generation](https://user-images.githubusercontent.com/14221764/282437321-881bd273-3443-4987-9a11-350d3288dd8e.png)

## 設定

安裝並 import 需要的相依套件：

```python
!pip install --quiet "cassandra-driver>=0.28.0" "openai>=1.0.0" datasets
```

```python
import os
from uuid import uuid4
from getpass import getpass
from collections import Counter

from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider

import openai
from datasets import load_dataset
```

_下一個 cell 不用太在意，它是用來偵測 Colab，並讓你上傳 SCB 檔（見下方）：_

```python
try:
    from google.colab import files
    IS_COLAB = True
except ModuleNotFoundError:
    IS_COLAB = False
```

## 取得資料庫連線

建立 `Session` 物件（連到你的 Astra DB instance 的連線）需要幾個 secret。

_（注意：有些步驟在 Google Colab 和本機 Jupyter 上略有不同，所以 notebook 會偵測執行環境類型。）_

```python
# Your database's Secure Connect Bundle zip file is needed:
if IS_COLAB:
    print('Please upload your Secure Connect Bundle zipfile: ')
    uploaded = files.upload()
    if uploaded:
        astraBundleFileTitle = list(uploaded.keys())[0]
        ASTRA_DB_SECURE_BUNDLE_PATH = os.path.join(os.getcwd(), astraBundleFileTitle)
    else:
        raise ValueError(
            'Cannot proceed without Secure Connect Bundle. Please re-run the cell.'
        )
else:
    # you are running a local-jupyter notebook:
    ASTRA_DB_SECURE_BUNDLE_PATH = input("Please provide the full path to your Secure Connect Bundle zipfile: ")

ASTRA_DB_APPLICATION_TOKEN = getpass("Please provide your Database Token ('AstraCS:...' string): ")
ASTRA_DB_KEYSPACE = input("Please provide the Keyspace name for your Database: ")
```

??? note "輸出"

    ```text
    Please provide the full path to your Secure Connect Bundle zipfile:  /path/to/secure-connect-DatabaseName.zip
    Please provide your Database Token ('AstraCS:...' string):  ········
    Please provide the Keyspace name for your Database:  my_keyspace
    ```

### 建立資料庫連線

建立 Astra DB 連線的方式如下：

_（順帶一提，任何 Cassandra cluster 只要有 Vector 功能都能用，只要[修改參數](https://docs.datastax.com/en/developer/python-driver/latest/getting_started/#connecting-to-cassandra)，也就是下面 `Cluster` 實例化的參數就行。）_

```python
# Don't mind the "Closing connection" error after "downgrading protocol..." messages you may see,
# it is really just a warning: the connection will work smoothly.
cluster = Cluster(
    cloud={
        "secure_connect_bundle": ASTRA_DB_SECURE_BUNDLE_PATH,
    },
    auth_provider=PlainTextAuthProvider(
        "token",
        ASTRA_DB_APPLICATION_TOKEN,
    ),
)

session = cluster.connect()
keyspace = ASTRA_DB_KEYSPACE
```

### 用 CQL 建立 Vector table

你需要一個支援 vector、並帶有 metadata 的 table，把它叫做 "philosophers_cql"。

每一列存：一則名言、它的 vector embedding、名言作者，以及一組 "tags"。還需要一個 primary key 來確保每列唯一。

下面是建立這個 table 的完整 CQL 指令（這個語句和後面語句的 CQL 語法，請看[這一頁](https://docs.datastax.com/en/dse/6.7/cql/cql/cqlQuickReference.html)）：

```python
create_table_statement = f"""CREATE TABLE IF NOT EXISTS {keyspace}.philosophers_cql (
    quote_id UUID PRIMARY KEY,
    body TEXT,
    embedding_vector VECTOR<FLOAT, 1536>,
    author TEXT,
    tags SET<TEXT>
);"""
```

把這個語句交給資料庫 Session 執行：

```python
session.execute(create_table_statement)
```

??? note "輸出"

    ```text
    <cassandra.cluster.ResultSet at 0x7feee37b3460>
    ```

#### 為 ANN 搜尋加上 vector index

要在 table 的 vector 上做 ANN（approximate-nearest-neighbor）搜尋，需要在 `embedding_vector` 欄位建立專用 index。

_建立 index 時，你可以[選擇](https://docs.datastax.com/en/astra-serverless/docs/vector-search/cql.html#_create_the_vector_schema_and_load_the_data_into_the_database)用來計算 vector 距離的「相似度函數」：因為對單位長度的 vector（例如 OpenAI 的）來說，「cosine difference」等於「dot product」，所以這裡用運算成本較低的 dot product。_

執行這個 CQL 語句：

```python
create_vector_index_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_embedding_vector
    ON {keyspace}.philosophers_cql (embedding_vector)
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex'
    WITH OPTIONS = {{'similarity_function' : 'dot_product'}};
"""
# Note: the double '{{' and '}}' are just the F-string escape sequence for '{' and '}'

session.execute(create_vector_index_statement)
```

??? note "輸出"

    ```text
    <cassandra.cluster.ResultSet at 0x7feeefd3da00>
    ```

#### 為作者和 tag 篩選加 index

這樣就足以對 table 做 vector 搜尋……但你還想能選擇性指定作者和 / 或一些 tag 來限制名言搜尋範圍。再建立兩個 index 來支援：

```python
create_author_index_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_author
    ON {keyspace}.philosophers_cql (author)
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex';
"""
session.execute(create_author_index_statement)

create_tags_index_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_tags
    ON {keyspace}.philosophers_cql (VALUES(tags))
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex';
"""
session.execute(create_tags_index_statement)
```

??? note "輸出"

    ```text
    <cassandra.cluster.ResultSet at 0x7fef2c64af70>
    ```

## 連接 OpenAI

### 設定你的 secret key

```python
OPENAI_API_KEY = getpass("Please enter your OpenAI API Key: ")
```

??? note "輸出"

    ```text
    Please enter your OpenAI API Key:  ········
    ```

### 測試 embedding 呼叫

快速看一下怎麼對一串輸入文字取得 embedding vector：

```python
client = openai.OpenAI(api_key=OPENAI_API_KEY)
embedding_model_name = "text-embedding-3-small"

result = client.embeddings.create(
    input=[
        "This is a sentence",
        "A second sentence"
    ],
    model=embedding_model_name,
)
```

_注意：上面是 OpenAI v1.0+ 的語法。如果用舊版，取得 embedding 的程式碼會不一樣。_

```python
print(f"len(result.data)              = {len(result.data)}")
print(f"result.data[1].embedding      = {str(result.data[1].embedding)[:55]}...")
print(f"len(result.data[1].embedding) = {len(result.data[1].embedding)}")
```

??? note "輸出"

    ```text
    len(result.data)              = 2
    result.data[1].embedding      = [-0.0108176339417696, 0.0013546717818826437, 0.00362232...
    len(result.data[1].embedding) = 1536
    ```

## 把名言載入 Vector Store

取得名言資料集。_（我們改編並擴充了[這個 Kaggle 資料集](https://www.kaggle.com/datasets/mertbozkurt5/quotes-by-philosophers)，已經可以直接用在這個 demo。）_

```python
philo_dataset = load_dataset("datastax/philosopher-quotes")["train"]
```

快速檢視：

```python
print("An example entry:")
print(philo_dataset[16])
```

??? note "輸出"

    ```text
    An example entry:
    {'author': 'aristotle', 'quote': 'Love well, be loved and do something of value.', 'tags': 'love;ethics'}
    ```

檢查資料集大小：

```python
author_count = Counter(entry["author"] for entry in philo_dataset)
print(f"Total: {len(philo_dataset)} quotes. By author:")
for author, count in author_count.most_common():
    print(f"    {author:<20}: {count} quotes")
```

??? note "輸出"

    ```text
    Total: 450 quotes. By author:
        aristotle           : 50 quotes
        schopenhauer        : 50 quotes
        spinoza             : 50 quotes
        hegel               : 50 quotes
        freud               : 50 quotes
        nietzsche           : 50 quotes
        sartre              : 50 quotes
        plato               : 50 quotes
        kant                : 50 quotes
    ```

### 把名言寫入 vector store

你會計算名言的 embedding，連同文字本身和之後要用的 metadata 一起存進 Vector Store。

為了加快速度、減少呼叫次數，會對 OpenAI embedding 服務做批次呼叫。

資料庫寫入用 CQL 語句完成。但因為這個寫入會執行很多次（只是值不同），最好先 _prepare_ 語句，再一直重複執行。

_（注意：為了更快寫入，Cassandra drivers 可以並行 insert，但為了讓 demo 程式碼更簡單，這裡沒有這樣做。）_

```python
prepared_insertion = session.prepare(
    f"INSERT INTO {keyspace}.philosophers_cql (quote_id, author, body, embedding_vector, tags) VALUES (?, ?, ?, ?, ?);"
)

BATCH_SIZE = 20

num_batches = ((len(philo_dataset) + BATCH_SIZE - 1) // BATCH_SIZE)

quotes_list = philo_dataset["quote"]
authors_list = philo_dataset["author"]
tags_list = philo_dataset["tags"]

print("Starting to store entries:")
for batch_i in range(num_batches):
    b_start = batch_i * BATCH_SIZE
    b_end = (batch_i + 1) * BATCH_SIZE
    # compute the embedding vectors for this batch
    b_emb_results = client.embeddings.create(
        input=quotes_list[b_start : b_end],
        model=embedding_model_name,
    )
    # prepare the rows for insertion
    print("B ", end="")
    for entry_idx, emb_result in zip(range(b_start, b_end), b_emb_results.data):
        if tags_list[entry_idx]:
            tags = {
                tag
                for tag in tags_list[entry_idx].split(";")
            }
        else:
            tags = set()
        author = authors_list[entry_idx]
        quote = quotes_list[entry_idx]
        quote_id = uuid4()  # a new random ID for each quote. In a production app you'll want to have better control...
        session.execute(
            prepared_insertion,
            (quote_id, author, quote, emb_result.embedding, tags),
        )
        print("*", end="")
    print(f" done ({len(b_emb_results.data)})")

print("\nFinished storing entries.")
```

??? note "輸出"

    ```text
    Starting to store entries:
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ******************** done (20)
    B ********** done (10)

    Finished storing entries.
    ```

## 用法 1：**名言搜尋引擎**

要做名言搜尋功能，先把輸入名言轉成 vector，再用它查詢 store（當然還要處理搜尋呼叫中選用的 metadata）。

把搜尋引擎的功能封裝成 function，方便重複使用：

```python
def find_quote_and_author(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    # depending on what conditions are passed, the WHERE clause in the statement may vary.
    where_clauses = []
    where_values = []
    if author:
        where_clauses += ["author = %s"]
        where_values += [author]
    if tags:
        for tag in tags:
            where_clauses += ["tags CONTAINS %s"]
            where_values += [tag]
    # The reason for these two lists above is that when running the CQL search statement the values passed
    # must match the sequence of "?" marks in the statement.
    if where_clauses:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql
            WHERE {' AND '.join(where_clauses)}
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    else:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    # For best performance, one should keep a cache of prepared statements (see the insertion code above)
    # for the various possible statements used here.
    # (We'll leave it as an exercise to the reader to avoid making this code too long.
    # Remember: to prepare a statement you use '?' instead of '%s'.)
    query_values = tuple(where_values + [query_vector] + [n])
    result_rows = session.execute(search_statement, query_values)
    return [
        (result_row.body, result_row.author)
        for result_row in result_rows
    ]
```

### 實際測試搜尋

只傳入一則名言：

```python
find_quote_and_author("We struggle all our life for nothing", 3)
```

??? note "輸出"

    ```text
    [('Life to the great majority is only a constant struggle for mere existence, with the certainty of losing it at last.',
      'schopenhauer'),
     ('We give up leisure in order that we may have leisure, just as we go to war in order that we may have peace.',
      'aristotle'),
     ('Perhaps the gods are kind to us, by making life more disagreeable as we grow older. In the end death seems less intolerable than the manifold burdens we carry',
      'freud')]
    ```

限定作者的搜尋：

```python
find_quote_and_author("We struggle all our life for nothing", 2, author="nietzsche")
```

??? note "輸出"

    ```text
    [('To live is to suffer, to survive is to find some meaning in the suffering.',
      'nietzsche'),
     ('What makes us heroic?--Confronting simultaneously our supreme suffering and our supreme hope.',
      'nietzsche')]
    ```

限定 tag 的搜尋（tag 是前面跟名言一起存的）：

```python
find_quote_and_author("We struggle all our life for nothing", 2, tags=["politics"])
```

??? note "輸出"

    ```text
    [('Mankind will never see an end of trouble until lovers of wisdom come to hold political power, or the holders of power become lovers of wisdom',
      'plato'),
     ('Everything the State says is a lie, and everything it has it has stolen.',
      'nietzsche')]
    ```

### 去掉不相關的結果

Vector 相似度搜尋通常會回傳離 query 最近的 vector，就算沒有更好的結果，也會回傳可能有點不相關的東西。

要控制這個問題，可以取得 query 和每筆結果之間實際的「相似度」，再設一個門檻，把超過門檻的結果丟掉。
要把這個門檻調對並不容易：這裡只示範做法。

想感受它怎麼運作，試試下面的 query，改變名言和門檻的選擇來比較結果：

_注意（給喜歡數學的人）：這個值把 cosine similarity 從 -1 到 1 的範圍重新縮放到 0 到 1。Cosine similarity 是內積除以兩個 vector 範數的乘積。縮放後的值，方向相反的 vector 是 0，平行的 vector 是 1。其他相似度度量請看[文件](https://docs.datastax.com/en/astra-serverless/docs/vector-search/cql.html#_create_the_vector_schema_and_load_the_data_into_the_database)，並記得 `SELECT` 查詢用的度量要跟建立 index 時用的一致，結果才有意義、才會正確排序。_

```python
quote = "Animals are our equals."
# quote = "Be good."
# quote = "This teapot is strange."

similarity_threshold = 0.92

quote_vector = client.embeddings.create(
    input=[quote],
    model=embedding_model_name,
).data[0].embedding

# Once more: remember to prepare your statements in production for greater performance...

search_statement = f"""SELECT body, similarity_dot_product(embedding_vector, %s) as similarity
    FROM {keyspace}.philosophers_cql
    ORDER BY embedding_vector ANN OF %s
    LIMIT %s;
"""
query_values = (quote_vector, quote_vector, 8)

result_rows = session.execute(search_statement, query_values)
results = [
    (result_row.body, result_row.similarity)
    for result_row in result_rows
    if result_row.similarity >= similarity_threshold
]

print(f"{len(results)} quotes within the threshold:")
for idx, (r_body, r_similarity) in enumerate(results):
    print(f"    {idx}. [similarity={r_similarity:.3f}] \"{r_body[:70]}...\"")
```

??? note "輸出"

    ```text
    3 quotes within the threshold:
        0. [similarity=0.927] "The assumption that animals are without rights, and the illusion that ..."
        1. [similarity=0.922] "Animals are in possession of themselves; their soul is in possession o..."
        2. [similarity=0.920] "At his best, man is the noblest of all animals; separated from law and..."
    ```

## 用法 2：**名言生成器**

這個任務需要 OpenAI 的另一個元件，也就是一個 LLM，來幫我們生成名言（根據查詢 Vector Store 得到的輸入）。

你還需要一個 prompt 模板，填好後用在生成名言的 LLM completion 任務。

```python
completion_model_name = "gpt-3.5-turbo"

generation_prompt_template = """"Generate a single short philosophical quote on the given topic,
similar in spirit and form to the provided actual example quotes.
Do not exceed 20-30 words in your quote.

REFERENCE TOPIC: "{topic}"

ACTUAL EXAMPLES:
{examples}
"""
```

跟搜尋一樣，這個功能最好也包成方便的 function（內部會用到搜尋）：

```python
def generate_quote(topic, n=2, author=None, tags=None):
    quotes = find_quote_and_author(query_quote=topic, n=n, author=author, tags=tags)
    if quotes:
        prompt = generation_prompt_template.format(
            topic=topic,
            examples="\n".join(f"  - {quote[0]}" for quote in quotes),
        )
        # a little logging:
        print("** quotes found:")
        for q, a in quotes:
            print(f"**    - {q} ({a})")
        print("** end of logging")
        #
        response = client.chat.completions.create(
            model=completion_model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=320,
        )
        return response.choices[0].message.content.replace('"', '').strip()
    else:
        print("** no quotes found.")
        return None
```

_注意：跟 embedding 計算一樣，OpenAI v1.0 以前的 Chat Completion API 程式碼會略有不同。_

#### 實際測試名言生成

只傳入一段文字（一則「名言」，其實也可以只給一個主題，因為它的 vector embedding 還是會落在 vector 空間的正確位置）：

```python
q_topic = generate_quote("politics and virtue")
print("\nA new generated quote:")
print(q_topic)
```

??? note "輸出"

    ```text
    ** quotes found:
    **    - Happiness is the reward of virtue. (aristotle)
    **    - Our moral virtues benefit mainly other people; intellectual virtues, on the other hand, benefit primarily ourselves; therefore the former make us universally popular, the latter unpopular. (schopenhauer)
    ** end of logging

    A new generated quote:
    True politics is not the pursuit of power, but the cultivation of virtue for the betterment of all.
    ```

只用單一哲學家的啟發：

```python
q_topic = generate_quote("animals", author="schopenhauer")
print("\nA new generated quote:")
print(q_topic)
```

??? note "輸出"

    ```text
    ** quotes found:
    **    - Because Christian morality leaves animals out of account, they are at once outlawed in philosophical morals; they are mere 'things,' mere means to any ends whatsoever. They can therefore be used for vivisection, hunting, coursing, bullfights, and horse racing, and can be whipped to death as they struggle along with heavy carts of stone. Shame on such a morality that is worthy of pariahs, and that fails to recognize the eternal essence that exists in every living thing, and shines forth with inscrutable significance from all eyes that see the sun! (schopenhauer)
    **    - The assumption that animals are without rights, and the illusion that our treatment of them has no moral significance, is a positively outrageous example of Western crudity and barbarity. Universal compassion is the only guarantee of morality. (schopenhauer)
    ** end of logging

    A new generated quote:
    Do not judge the worth of a soul by its outward form, for within every animal lies an eternal essence that deserves our compassion and respect.
    ```

## （選用）**Partitioning**

結束這個 quickstart 前，有個有趣的主題值得看。一般來說 tag 和名言可以是任意關係（例如一則名言有多個 tag），但_作者_實際上是精確的分組（它們對名言集合定義了「互斥的分割」）：每則名言恰好有一位作者（至少在我們的資料裡是這樣）。

現在假設你事先知道應用程式通常（或總是）只對_單一作者_做查詢。那就能充分利用底層資料庫結構：如果把名言分組放進 **partition**（每位作者一個），只針對某位作者的 vector 查詢會用更少資源，也會快很多。

這裡不深入細節，那跟 Cassandra 的儲存內部機制有關：重點是 **如果你的查詢是在某個群組內執行，就考慮照群組做 partition 來提升效能**。

現在來看這個選擇的實際效果。

依作者 partition 需要新的 table schema：建立一個叫 "philosophers_cql_partitioned" 的新 table，連同必要的 index：

```python
create_table_p_statement = f"""CREATE TABLE IF NOT EXISTS {keyspace}.philosophers_cql_partitioned (
    author TEXT,
    quote_id UUID,
    body TEXT,
    embedding_vector VECTOR<FLOAT, 1536>,
    tags SET<TEXT>,
    PRIMARY KEY ( (author), quote_id )
) WITH CLUSTERING ORDER BY (quote_id ASC);"""

session.execute(create_table_p_statement)

create_vector_index_p_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_embedding_vector_p
    ON {keyspace}.philosophers_cql_partitioned (embedding_vector)
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex'
    WITH OPTIONS = {{'similarity_function' : 'dot_product'}};
"""

session.execute(create_vector_index_p_statement)

create_tags_index_p_statement = f"""CREATE CUSTOM INDEX IF NOT EXISTS idx_tags_p
    ON {keyspace}.philosophers_cql_partitioned (VALUES(tags))
    USING 'org.apache.cassandra.index.sai.StorageAttachedIndex';
"""
session.execute(create_tags_index_p_statement)
```

??? note "輸出"

    ```text
    <cassandra.cluster.ResultSet at 0x7fef149d7940>
    ```

現在對新 table 重複「計算 embedding 並寫入」的步驟。

你可以直接用前面同樣的寫入程式碼，因為差異都藏在「幕後」：資料庫會依這個新 table 的 partition 方式，用不同的方式儲存寫入的列。

不過為了示範，你會用 Cassandra drivers 提供的一個方便功能，輕鬆並行執行多個查詢（這裡是 `INSERT`）。Cassandra / Astra DB through CQL 對這點支援得很好，client 端程式碼只要改很少，就能大幅加速。

_（注意：其實還可以把之前算好的 embedding 快取起來，省一些 API token，不過這裡想讓程式碼好檢視。）_

```python
from cassandra.concurrent import execute_concurrent_with_args
```

```python
prepared_insertion = session.prepare(
    f"INSERT INTO {keyspace}.philosophers_cql_partitioned (quote_id, author, body, embedding_vector, tags) VALUES (?, ?, ?, ?, ?);"
)

BATCH_SIZE = 50

num_batches = ((len(philo_dataset) + BATCH_SIZE - 1) // BATCH_SIZE)

quotes_list = philo_dataset["quote"]
authors_list = philo_dataset["author"]
tags_list = philo_dataset["tags"]

print("Starting to store entries:")
for batch_i in range(num_batches):
    print("[...", end="")
    b_start = batch_i * BATCH_SIZE
    b_end = (batch_i + 1) * BATCH_SIZE
    # compute the embedding vectors for this batch
    b_emb_results = client.embeddings.create(
        input=quotes_list[b_start : b_end],
        model=embedding_model_name,
    )
    # prepare this batch's entries for insertion
    tuples_to_insert = []
    for entry_idx, emb_result in zip(range(b_start, b_end), b_emb_results.data):
        if tags_list[entry_idx]:
            tags = {
                tag
                for tag in tags_list[entry_idx].split(";")
            }
        else:
            tags = set()
        author = authors_list[entry_idx]
        quote = quotes_list[entry_idx]
        quote_id = uuid4()  # a new random ID for each quote. In a production app you'll want to have better control...
        # append a *tuple* to the list, and in the tuple the values are ordered to match "?" in the prepared statement:
        tuples_to_insert.append((quote_id, author, quote, emb_result.embedding, tags))
    # insert the batch at once through the driver's concurrent primitive
    conc_results = execute_concurrent_with_args(
        session,
        prepared_insertion,
        tuples_to_insert,
    )
    # check that all insertions succeed (better to always do this):
    if any([not success for success, _ in conc_results]):
        print("Something failed during the insertions!")
    else:
        print(f"{len(b_emb_results.data)}] ", end="")

print("\nFinished storing entries.")
```

??? note "輸出"

    ```text
    Starting to store entries:
    [...50] [...50] [...50] [...50] [...50] [...50] [...50] [...50] [...50] 
    Finished storing entries.
    ```

雖然 table schema 不同，相似度搜尋背後的資料庫查詢基本上一樣：

```python
def find_quote_and_author_p(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    # Depending on what conditions are passed, the WHERE clause in the statement may vary.
    # Construct it accordingly:
    where_clauses = []
    where_values = []
    if author:
        where_clauses += ["author = %s"]
        where_values += [author]
    if tags:
        for tag in tags:
            where_clauses += ["tags CONTAINS %s"]
            where_values += [tag]
    if where_clauses:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql_partitioned
            WHERE {' AND '.join(where_clauses)}
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    else:
        search_statement = f"""SELECT body, author FROM {keyspace}.philosophers_cql_partitioned
            ORDER BY embedding_vector ANN OF %s
            LIMIT %s;
        """
    query_values = tuple(where_values + [query_vector] + [n])
    result_rows = session.execute(search_statement, query_values)
    return [
        (result_row.body, result_row.author)
        for result_row in result_rows
    ]
```

就這樣，新 table 仍然能正常支援「一般」的相似度搜尋……

```python
find_quote_and_author_p("We struggle all our life for nothing", 3)
```

??? note "輸出"

    ```text
    [('Life to the great majority is only a constant struggle for mere existence, with the certainty of losing it at last.',
      'schopenhauer'),
     ('We give up leisure in order that we may have leisure, just as we go to war in order that we may have peace.',
      'aristotle'),
     ('Perhaps the gods are kind to us, by making life more disagreeable as we grow older. In the end death seems less intolerable than the manifold burdens we carry',
      'freud')]
    ```

……但指定作者時，你會注意到_巨大_的效能優勢：

```python
find_quote_and_author_p("We struggle all our life for nothing", 2, author="nietzsche")
```

??? note "輸出"

    ```text
    [('To live is to suffer, to survive is to find some meaning in the suffering.',
      'nietzsche'),
     ('What makes us heroic?--Confronting simultaneously our supreme suffering and our supreme hope.',
      'nietzsche')]
    ```

嗯，如果資料集大小接近實際情況，你_會_注意到效能提升。在這個 demo 裡只有幾十筆資料，感覺不出差別，不過你應該懂這個概念了。

## 結論

恭喜！你學會了怎麼用 OpenAI 做 vector embedding、用 Astra DB / Cassandra 做儲存，打造出精緻的哲學搜尋引擎和名言生成器。

這個範例用 [Cassandra drivers](https://docs.datastax.com/en/developer/python-driver/latest/)，直接執行 CQL（Cassandra Query Language）語句跟 Vector Store 互動，但這不是唯一選擇。其他選項和跟常見框架的整合，請看 [README](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases/cassandra_astradb)。

想了解 Astra DB 的 Vector Search 功能如何成為你的 ML / GenAI 應用的關鍵元件，請到 [Astra DB](https://docs.datastax.com/en/astra-serverless/docs/vector-search/overview.html) 網站上相關頁面。

## 清除資源

如果想移除這個 demo 用到的所有資源，執行這個 cell（_警告：這會刪除 table 和裡面寫入的資料！_）：

```python
session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cql;")
session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cql_partitioned;")
```

??? note "輸出"

    ```text
    <cassandra.cluster.ResultSet at 0x7fef149096a0>
    ```

## 重點整理

- Vector search 的核心是「語意相似等於 vector 距離近」，OpenAI embedding 是單位長度，所以 cosine 和 dot product 結果等價，用 dot product 比較省運算。
- Vector index 只負責 ANN 搜尋，想依作者、tag 篩選要另外建 index。
- 搜尋永遠會回傳最近的結果，就算不相關，要靠相似度門檻把太遠的結果丟掉。
- 生成器的做法就是「先搜尋，再把前幾筆結果塞進 prompt」，是最簡單的 RAG 形式。
- 如果查詢總是限定在某個分組（例如單一作者），用 partition 能明顯加速。

## 練習

1. 在搜尋的相似度門檻範例，換不同的名言並調整門檻，觀察多少結果會被丟掉。
2. 對 "philosophers_cql" 做一個限定 tag 的搜尋，改用自己想的 tag，並把 prompt 模板改成要求生成的名言用不同語氣。
3. 在 partitioned table 上多寫一個 function，同時限制作者和相似度門檻，並把 embedding 結果先快取起來，避免重新插入時重複呼叫 API。
