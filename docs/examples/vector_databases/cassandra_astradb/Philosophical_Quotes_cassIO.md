---
translated: true
source: examples/vector_databases/cassandra_astradb/Philosophical_Quotes_cassIO.ipynb
---

# 用 vector embedding、OpenAI 和 Cassandra / Astra DB 做哲學

> 原文：[examples/vector_databases/cassandra_astradb/Philosophical_Quotes_cassIO.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_cassIO.ipynb)



## 這篇在做什麼

用 OpenAI 的 embedding 把一批哲學家名言轉成向量，存進 Cassandra / Astra DB 當 vector store，然後做出名言搜尋引擎，再用搜尋到的名言當範例，讓 LLM 生成新的名言。最後還會示範用 partition 加速只查單一作者的情境。

## 學完你會

- 用 CassIO 建立支援向量和 metadata 的資料表，並批次計算 embedding 後寫入
- 寫出帶 metadata 條件（作者、tag）和距離門檻的相似度搜尋函式
- 把搜尋結果塞進 prompt 模板，做出名言生成器，並用 partition 優化單一作者的查詢

## 開跑前

- 需要 OpenAI API key（呼叫 embedding 和 Chat Completion 會計費）。
- 需要 Astra DB 帳號，並取得 Database Administrator 角色的 Token（長得像 `AstraCS:...`）和 database ID。也可以改用支援 Vector Search 的 Cassandra cluster。


### CassIO 版本

這份快速入門會教你用 OpenAI 的 vector embedding 和 [Apache Cassandra®](https://cassandra.apache.org)（或同樣的，透過 CQL 使用 DataStax [Astra DB](https://docs.datastax.com/en/astra-serverless/docs/vector-search/quickstart.html)）當作資料持久化的 vector store，做出一個「哲學名言搜尋與生成器」。

整個流程大致如下：你會計算並儲存一批著名哲學家名言的 vector embedding，用它們做出強大的搜尋引擎，之後甚至做出能生成新名言的生成器！

這份 notebook 示範了 vector search 的一些標準用法，同時也展現用 [Cassandra](https://cassandra.apache.org/doc/trunk/cassandra/vector-search/overview.html) / [透過 CQL 的 Astra DB](https://docs.datastax.com/en/astra-serverless/docs/vector-search/quickstart.html) 的向量功能入門有多簡單。

如果想了解用 vector search 和文字 embedding 做問答系統的背景，可以看這份很棒的實作 notebook：[Question answering using embeddings](https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_embeddings.ipynb)。

#### _選擇你的框架_

注意這份 notebook 用的是 [CassIO library](https://cassio.org)，但同一件事也有其他技術選擇可以做到。其他選項請看這個資料夾的 [README](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases/cassandra_astradb)。

目錄：
- 環境設定
- 取得資料庫連線
- 連接 OpenAI
- 把名言載入 Vector Store
- 使用案例 1：**名言搜尋引擎**
- 使用案例 2：**名言生成器**
- （選用）善用 Vector Store 的 partition

### 運作方式

**建立索引**

每句名言都用 OpenAI 的 `Embedding` 轉成 embedding 向量，存進 Vector Store 以便之後搜尋。作者名字和其他一些預先算好的 tag 這類 metadata 會一起存，讓搜尋可以客製化。

![1_vector_indexing](https://user-images.githubusercontent.com/14221764/282440878-dc3ed680-7d0e-4b30-9a74-d2d66a7394f7.png)

**搜尋**

要找出跟給定名言相似的名言，會先即時把給定的名言轉成 embedding 向量，再用這個向量去查詢 store 裡相似的向量，也就是先前已建立索引的相似名言。搜尋還可以選擇性地加上 metadata 條件（「找出 Spinoza 寫的、跟這句相似的名言⋯⋯」）。

![2_vector_search](https://user-images.githubusercontent.com/14221764/282440908-683e3ee1-0bf1-46b3-8621-86c31fc7f9c9.png)

關鍵在於，「內容相似的名言」在向量空間裡，對應到距離彼此很近的向量，所以向量相似度搜尋實際上做的就是語意相似度。_這就是 vector embedding 這麼強大的關鍵原因。_

下面的示意圖想傳達這個概念。每句名言轉成向量後就是空間中的一個點。更精確地說，因為 OpenAI 的 embedding 向量跟大多數模型一樣會正規化成_單位長度_，所以這些點是在一個球面上。而且這個球面其實不是三維，是 1536 維！

所以本質上，在向量空間做相似度搜尋，就是回傳離查詢向量最近的那些向量：

![3_vector_space](https://user-images.githubusercontent.com/14221764/262321363-c8c625c1-8be9-450e-8c68-b1ed518f990d.png)

**生成**

給定一個提示（一個主題或一句暫定的名言），先做搜尋，把最前面的結果（名言）放進 LLM 的 prompt，請生成模型照著這些範例_和_最初的提示，編出新的文字。

![4_quote_generation](https://user-images.githubusercontent.com/14221764/282440927-d56f36eb-d611-4342-8026-7736edc6f5c9.png)

## 環境設定

先安裝一些必要的套件：

```python
!pip install --quiet "cassio>=0.1.3" "openai>=1.0.0" datasets
```

```python
from getpass import getpass
from collections import Counter

import cassio
from cassio.table import MetadataVectorCassandraTable

import openai
from datasets import load_dataset
```

## 取得資料庫連線

要透過 CQL 連到你的 Astra DB，需要兩樣東西：
- 一個角色為 "Database Administrator" 的 Token（長得像 `AstraCS:...`）
- database ID（長得像 `3df2a5b6-...`）

    請確定兩個字串都拿到了，登入 [Astra UI](https://astra.datastax.com) 就能取得。詳情請看：[database ID](https://awesome-astra.github.io/docs/pages/astra/faq/#where-should-i-find-a-database-identifier) 和 [Token](https://awesome-astra.github.io/docs/pages/astra/create-token/#c-procedure)。

如果想_連到 Cassandra cluster_（不過必須[支援](https://cassandra.apache.org/doc/trunk/cassandra/vector-search/overview.html) Vector Search），就改成 `cassio.init(session=..., keyspace=...)`，帶入適合你的 cluster 的 session 和 keyspace 名稱。

```python
astra_token = getpass("Please enter your Astra token ('AstraCS:...')")
database_id = input("Please enter your database id ('3df2a5b6-...')")
```

??? note "輸出"

    ```text
    Please enter your Astra token ('AstraCS:...') ········
    Please enter your database id ('3df2a5b6-...') 01234567-89ab-dcef-0123-456789abcdef
    ```

```python
cassio.init(token=astra_token, database_id=database_id)
```

### 建立資料庫連線

這是透過 CQL 建立 Astra DB 連線的方法：

_（順帶一提，只要[改參數](https://docs.datastax.com/en/developer/python-driver/latest/getting_started/#connecting-to-cassandra)，改下面的 `Cluster` 實例化，也可以用任何有 Vector 功能的 Cassandra cluster。）_

### 透過 CassIO 建立 Vector Store

你需要一個支援向量、並且附帶 metadata 的資料表。把它命名為 "philosophers_cassio"：

```python
v_table = MetadataVectorCassandraTable(table="philosophers_cassio", vector_dimension=1536)
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

### 測試呼叫 embedding

快速確認怎麼取得一組輸入文字的 embedding 向量：

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
    result.data[1].embedding      = [-0.010821706615388393, 0.001387271680869162, 0.0035479...
    len(result.data[1].embedding) = 1536
    ```

## 把名言載入 Vector Store

_注意：上面是 OpenAI v1.0+ 的語法。如果用舊版，取得 embedding 的程式碼會不一樣。_

```python
philo_dataset = load_dataset("datastax/philosopher-quotes")["train"]
```

快速檢查一下：

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

你要計算名言的 embedding，連同文字本身和之後會用到的 metadata 一起存進 Vector Store。注意作者會被加成 metadata 欄位，跟名言本身已有的 "tags" 放在一起。

為了加快速度並減少呼叫次數，會對 OpenAI embedding 服務做批次呼叫。

_（注意：為了加快執行，Cassandra 和 CassIO 可以並行寫入，這裡為了讓範例程式碼更直白就沒這樣做。）_

```python
BATCH_SIZE = 50

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
        v_table.put(
            row_id=f"q_{author}_{entry_idx}",
            body_blob=quote,
            vector=emb_result.embedding,
            metadata={**{tag: True for tag in tags}, **{"author": author}},
        )
        print("*", end="")
    print(f" done ({len(b_emb_results.data)})")

print("\nFinished storing entries.")
```

??? note "輸出"

    ```text
    Starting to store entries:
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)
    B ************************************************** done (50)

    Finished storing entries.
    ```

## 使用案例 1：**名言搜尋引擎**

名言搜尋功能要先把輸入的名言轉成向量，再用它查詢 store（另外還要處理搜尋呼叫裡選用的 metadata）。

把搜尋引擎的功能包成函式，方便重複使用：

```python
def find_quote_and_author(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    metadata = {}
    if author:
        metadata["author"] = author
    if tags:
        for tag in tags:
            metadata[tag] = True
    #
    results = v_table.ann_search(
        query_vector,
        n=n,
        metadata=metadata,
    )
    return [
        (result["body_blob"], result["metadata"]["author"])
        for result in results
    ]
```

### 實際測試搜尋

只傳入一句名言：

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

限定某位作者的搜尋：

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

限定某個 tag 的搜尋（tag 是先前跟名言一起存進去的）：

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

### 濾掉不相關的結果

向量相似度搜尋通常會回傳離查詢最近的向量，就算沒有更好的選擇，結果可能有點不相關也一樣。

要控制這個問題，可以取得查詢和每個結果之間實際的「距離」，再設定一個門檻，把超過門檻的結果丟掉。
要把這個門檻調對並不容易，這裡只示範做法。

想感受它怎麼運作，可以試試下面的查詢，改變名言和門檻的選擇，比較結果：

_註（給數學愛好者）：這個「距離」其實就是向量之間的 cosine similarity，也就是內積除以兩個向量長度的乘積。所以它是一個從 -1 到 +1 的數，-1 代表方向完全相反的向量，+1 代表方向完全相同的向量。在別的地方（例如這份 demo 的「CQL」版本），這個值會被重新縮放到 [0, 1] 區間，所以那邊的數值和合適的門檻也會跟著轉換。_

```python
quote = "Animals are our equals."
# quote = "Be good."
# quote = "This teapot is strange."

metric_threshold = 0.84

quote_vector = client.embeddings.create(
    input=[quote],
    model=embedding_model_name,
).data[0].embedding

results = list(v_table.metric_ann_search(
    quote_vector,
    n=8,
    metric="cos",
    metric_threshold=metric_threshold,
))

print(f"{len(results)} quotes within the threshold:")
for idx, result in enumerate(results):
    print(f"    {idx}. [distance={result['distance']:.3f}] \"{result['body_blob'][:70]}...\"")
```

??? note "輸出"

    ```text
    3 quotes within the threshold:
        0. [distance=0.855] "The assumption that animals are without rights, and the illusion that ..."
        1. [distance=0.843] "Animals are in possession of themselves; their soul is in possession o..."
        2. [distance=0.841] "At his best, man is the noblest of all animals; separated from law and..."
    ```

## 使用案例 2：**名言生成器**

這個任務需要 OpenAI 的另一個元件，也就是一個 LLM，根據查詢 Vector Store 得到的輸入來替我們生成名言。

你還需要一個 prompt 模板，用來填入生成名言的 LLM completion 任務。

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

跟搜尋一樣，這個功能最好也包成方便的函式（內部會用到搜尋）：

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

_注意：跟計算 embedding 的情況類似，OpenAI v1.0 之前的版本，Chat Completion API 的程式碼會稍有不同。_

#### 實際測試名言生成

只傳入一段文字（一句「名言」，不過其實給個主題也可以，因為它的 vector embedding 一樣會落在向量空間的正確位置）：

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
    Virtuous politics purifies society, while corrupt politics breeds chaos and decay.
    ```

只用單一哲學家的靈感：

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
    The true measure of humanity lies not in our dominion over animals, but in our ability to show compassion and respect for all living beings.
    ```

## （選用）**Partitioning**

結束這份快速入門之前，有個有趣的主題值得看。一般來說，tags 和名言之間可以是任何關係（例如一句名言有多個 tag），但_作者_實際上是一種精確的分組（它們在名言集合上定義了「不相交的劃分」）：每句名言剛好有一位作者（至少在我們的資料裡是這樣）。

假設你事先知道，你的應用程式通常（或總是）只對_單一作者_做查詢。那你就能充分利用底層的資料庫結構：如果把名言分組放進 **partition**（每位作者一個），只查某位作者的向量查詢會用比較少的資源，回傳也快得多。

這裡不深入細節，那些跟 Cassandra 的儲存內部機制有關，重點是：**如果你的查詢都是在某個群組內執行，考慮照群組做 partition 來提升效能**。

接下來實際看看這個選擇的效果。

首先，你需要 CassIO 提供的另一種資料表抽象：

```python
from cassio.table import ClusteredMetadataVectorCassandraTable
```

```python
v_table_partitioned = ClusteredMetadataVectorCassandraTable(table="philosophers_cassio_partitioned", vector_dimension=1536)
```

現在在新的資料表上重做一次計算 embedding 並寫入的步驟。

跟前面看過的不同，關鍵差異在於現在名言的作者是存成寫入資料列的 _partition id_，而不是加進包山包海的 "metadata" 字典。

順便示範一下：你會_並行_寫入某位作者的所有名言。在 CassIO 裡做法是對每句名言用非同步的 `put_async` 方法，收集回傳的 `Future` 物件清單，之後對它們全部呼叫 `result()` 方法，確保都執行完了。Cassandra / Astra DB 很能支援高度並行的 I/O 操作。

_（注意：其實可以把先前算好的 embedding 快取起來，省下一些 API token，不過這裡想讓程式碼更容易檢視。）_

```python
BATCH_SIZE = 50

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
    futures = []
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
        futures.append(v_table_partitioned.put_async(
            partition_id=author,
            row_id=f"q_{author}_{entry_idx}",
            body_blob=quote,
            vector=emb_result.embedding,
            metadata={tag: True for tag in tags},
        ))
    #
    for future in futures:
        future.result()
    #
    print(f" done ({len(b_emb_results.data)})")

print("\nFinished storing entries.")
```

??? note "輸出"

    ```text
    Starting to store entries:
    B  done (50)
    B  done (50)
    B  done (50)
    B  done (50)
    B  done (50)
    B  done (50)
    B  done (50)
    B  done (50)
    B  done (50)

    Finished storing entries.
    ```

有了這張新資料表，相似度搜尋也要跟著改（注意 `ann_search` 的參數）：

```python
def find_quote_and_author_p(query_quote, n, author=None, tags=None):
    query_vector = client.embeddings.create(
        input=[query_quote],
        model=embedding_model_name,
    ).data[0].embedding
    metadata = {}
    partition_id = None
    if author:
        partition_id = author
    if tags:
        for tag in tags:
            metadata[tag] = True
    #
    results = v_table_partitioned.ann_search(
        query_vector,
        n=n,
        partition_id=partition_id,
        metadata=metadata,
    )
    return [
        (result["body_blob"], result["partition_id"])
        for result in results
    ]
```

這樣就好了：新資料表依然支援「一般」的相似度搜尋⋯⋯

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

⋯⋯但指定作者時，你才會發現_巨大_的效能優勢：

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

嗯，如果你有真實規模的資料集，你_就會_發現效能提升。在這份 demo 裡只有幾十筆資料，沒有明顯差別，不過你應該懂這個概念。

## 結論

恭喜！你學會了怎麼用 OpenAI 做 vector embedding，並用 Cassandra / Astra DB（透過 CQL）儲存，做出一個完整的哲學名言搜尋引擎和名言生成器。

這個範例用 [CassIO](https://cassio.org) 跟 Vector Store 介接，但這不是唯一的選擇。其他選項和跟常見框架的整合，請看 [README](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases/cassandra_astradb)。

想進一步了解 Astra DB 的 Vector Search 功能怎麼成為你的 ML/GenAI 應用的關鍵元素，可以看 [Astra DB](https://docs.datastax.com/en/astra/home/astra.html) 網站上的相關頁面。

## 清除資源

如果想移除這份 demo 用到的所有資源，執行這個 cell（_警告：這會刪除資料表和裡面寫入的資料！_）：

```python
# we peek at CassIO's config to get a direct handle to the DB connection
session = cassio.config.resolve_session()
keyspace = cassio.config.resolve_keyspace()

session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cassio;")
session.execute(f"DROP TABLE IF EXISTS {keyspace}.philosophers_cassio_partitioned;")
```

??? note "輸出"

    ```text
    <cassandra.cluster.ResultSet at 0x7fdcc42e8f10>
    ```

## 重點整理

- 名言轉成 embedding 後，語意相似就等於向量距離近，搜尋本質上就是找最近的向量。
- metadata（作者、tag）可以跟向量一起存，搜尋時當過濾條件。
- 向量搜尋永遠會回傳最近的結果，所以要用距離（cosine similarity）設門檻擋掉不相關的。
- 生成器的做法是先搜尋，再把結果當範例塞進 prompt，這就是簡單的 RAG 模式。
- 如果查詢幾乎都落在某個群組內，用 partition 照群組存放，可以省資源並加快查詢。

## 練習

1. 改搜尋函式的 `n` 參數，並在 prompt 裡改變塞進去的名言數量，觀察生成名言的風格怎麼變。
2. 在「濾掉不相關結果」的範例裡，換幾句不同的查詢名言和門檻，找出一個你覺得結果品質剛好的門檻。
3. 在 partition 版本的資料表，加入第二個維度的過濾（例如只查某位作者且帶特定 tag 的名言），改寫 `ann_search` 的呼叫。
