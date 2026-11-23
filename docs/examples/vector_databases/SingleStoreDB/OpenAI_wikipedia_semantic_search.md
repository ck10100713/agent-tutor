---
translated: true
source: examples/vector_databases/SingleStoreDB/OpenAI_wikipedia_semantic_search.ipynb
---

# 用 SingleStoreDB 做語意搜尋

> 原文：[examples/vector_databases/SingleStoreDB/OpenAI_wikipedia_semantic_search.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/SingleStoreDB/OpenAI_wikipedia_semantic_search.ipynb)



## 這篇在做什麼
這本 notebook 示範怎麼用 SingleStoreDB 的向量儲存和函式，搭配 ChatGPT 做出互動式問答應用。
流程是先直接問 ChatGPT（問一個超過 2021 年的事情，它答不出來），再把冬季奧運的資料存進 SingleStoreDB，語意搜尋找出相關內容，當作上下文送給 ChatGPT，得到更準確的答案。

## 學完你會
- 看出 ChatGPT 在沒有上下文時，對超過訓練資料日期的問題怎麼答不準。
- 把 CSV 資料整理後存進 SingleStoreDB，並用 JSON_ARRAY_PACK 壓縮向量。
- 用語意搜尋找出相關內容，組成上下文送給 ChatGPT，拿到更準確的回答。

## 開跑前
- 需要 OpenAI API key。
- 需要一個 SingleStoreDB 環境。如果在 SingleStoreDB 開啟[試用](https://www.singlestore.com/cloud-trial/)，可以在他們的範例 notebook 中找到同一本 notebook，並使用原生連線。

## 先直接跟 ChatGPT 對話，看看會得到什麼回應

```python
!pip install openai --quiet
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 23.0.1 -> 23.1.2
    [notice] To update, run: python3.11 -m pip install --upgrade pip
    ```

```python
import openai

EMBEDDING_MODEL = "text-embedding-3-small"
GPT_MODEL = "gpt-3.5-turbo"
```

## 連接 OpenAI，看看問一個 2021 年之後的日期時會得到什麼結果

```python
openai.api_key = 'OPENAI API KEY'

response = openai.ChatCompletion.create(
  model=GPT_MODEL,
  messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Who won the gold medal for curling in Olymics 2022?"},
    ]
)

print(response['choices'][0]['message']['content'])
```

??? note "輸出"

    ```text
    I'm sorry, I cannot provide information about events that have not occurred yet. The Winter Olympics 2022 will be held in Beijing, China from February 4 to 20, 2022. The curling events will take place during this time and the results will not be known until after the competition has concluded.
    ```

# 取得冬季奧運的資料，並把資訊作為上下文提供給 ChatGPT

## 1. 設定

```python
!pip install matplotlib plotly.express scikit-learn tabulate tiktoken wget --quiet
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 23.0.1 -> 23.1.2
    [notice] To update, run: python3.11 -m pip install --upgrade pip
    ```

```python
import pandas as pd
import os
import wget
import ast
```

## 步驟 1：從 CSV 取得資料並整理

```python
# download pre-chunked text and pre-computed embeddings
# this file is ~200 MB, so may take a minute depending on your connection speed
embeddings_path = "https://cdn.openai.com/API/examples/data/winter_olympics_2022.csv"
file_path = "winter_olympics_2022.csv"

if not os.path.exists(file_path):
    wget.download(embeddings_path, file_path)
    print("File downloaded successfully.")
else:
    print("File already exists in the local file system.")
```

??? note "輸出"

    ```text
    File downloaded successfully.
    ```

```python
df = pd.read_csv(
    "winter_olympics_2022.csv"
)

# convert embeddings from CSV str type back to list type
df['embedding'] = df['embedding'].apply(ast.literal_eval)
```

```python
df
```

```python
df.info(show_counts=True)
```

??? note "輸出"

    ```text
    <class 'pandas.core.frame.DataFrame'>
    RangeIndex: 6059 entries, 0 to 6058
    Data columns (total 2 columns):
     #   Column     Non-Null Count  Dtype 
    ---  ------     --------------  ----- 
     0   text       6059 non-null   object
     1   embedding  6059 non-null   object
    dtypes: object(2)
    memory usage: 94.8+ KB
    ```

## 2. 設定 SingleStore DB

```python
import singlestoredb as s2

conn = s2.connect("<user>:<Password>@<host>:3306/")

cur = conn.cursor()
```

```python
# Create database
stmt = """
    CREATE DATABASE IF NOT EXISTS winter_wikipedia2;
"""

cur.execute(stmt)
```

??? note "輸出"

    ```text
    1
    ```

```python
#create table
stmt = """
CREATE TABLE IF NOT EXISTS winter_wikipedia2.winter_olympics_2022 (
    id INT PRIMARY KEY,
    text TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
    embedding BLOB
);"""

cur.execute(stmt)
```

??? note "輸出"

    ```text
    0
    ```

## 3. 用 dataframe df 填入資料表，並用 JSON_ARRAY_PACK 壓縮

```python
%%time

# Prepare the statement
stmt = """
    INSERT INTO winter_wikipedia2.winter_olympics_2022 (
        id,
        text,
        embedding
    )
    VALUES (
        %s,
        %s,
        JSON_ARRAY_PACK_F64(%s)
    )
"""

# Convert the DataFrame to a NumPy record array
record_arr = df.to_records(index=True)

# Set the batch size
batch_size = 1000

# Iterate over the rows of the record array in batches
for i in range(0, len(record_arr), batch_size):
    batch = record_arr[i:i+batch_size]
    values = [(row[0], row[1], str(row[2])) for row in batch]
    cur.executemany(stmt, values)
```

??? note "輸出"

    ```text
    CPU times: user 8.79 s, sys: 4.63 s, total: 13.4 s
    Wall time: 11min 4s
    ```

## 4. 用上面同一個問題做語意搜尋，並把結果再送給 OpenAI


```python
from utils.embeddings_utils import get_embedding

def strings_ranked_by_relatedness(
    query: str,
    df: pd.DataFrame,
    relatedness_fn=lambda x, y: 1 - spatial.distance.cosine(x, y),
    top_n: int = 100
) -> tuple:
    """Returns a list of strings and relatednesses, sorted from most related to least."""

    # Get the embedding of the query.
    query_embedding_response = get_embedding(query, EMBEDDING_MODEL)

    # Create the SQL statement.
    stmt = """
        SELECT
            text,
            DOT_PRODUCT_F64(JSON_ARRAY_PACK_F64(%s), embedding) AS score
        FROM winter_wikipedia2.winter_olympics_2022
        ORDER BY score DESC
        LIMIT %s
    """

    # Execute the SQL statement.
    results = cur.execute(stmt, [str(query_embedding_response), top_n])

    # Fetch the results
    results = cur.fetchall()

    strings = []
    relatednesses = []

    for row in results:
        strings.append(row[0])
        relatednesses.append(row[1])

    # Return the results.
    return strings[:top_n], relatednesses[:top_n]
```

```python
from tabulate import tabulate

strings, relatednesses = strings_ranked_by_relatedness(
    "curling gold medal",
    df,
    top_n=5
)

for string, relatedness in zip(strings, relatednesses):
    print(f"{relatedness=:.3f}")
    print(tabulate([[string]], headers=['Result'], tablefmt='fancy_grid'))
```

## 5. 把正確的上下文送給 ChatGPT，得到更準確的答案

```python
import tiktoken

def num_tokens(text: str, model: str = GPT_MODEL) -> int:
    """Return the number of tokens in a string."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))


def query_message(
    query: str,
    df: pd.DataFrame,
    model: str,
    token_budget: int
) -> str:
    """Return a message for GPT, with relevant source texts pulled from SingleStoreDB."""
    strings, relatednesses = strings_ranked_by_relatedness(query, df, "winter_olympics_2022")
    introduction = 'Use the below articles on the 2022 Winter Olympics to answer the subsequent question. If the answer cannot be found in the articles, write "I could not find an answer."'
    question = f"\n\nQuestion: {query}"
    message = introduction
    for string in strings:
        next_article = f'\n\nWikipedia article section:\n"""\n{string}\n"""'
        if (
            num_tokens(message + next_article + question, model=model)
            > token_budget
        ):
            break
        else:
            message += next_article
    return message + question


def ask(
    query: str,
    df: pd.DataFrame = df,
    model: str = GPT_MODEL,
    token_budget: int = 4096 - 500,
    print_message: bool = False,
) -> str:
    """Answers a query using GPT and a table of relevant texts and embeddings in SingleStoreDB."""
    message = query_message(query, df, model=model, token_budget=token_budget)
    if print_message:
        print(message)
    messages = [
        {"role": "system", "content": "You answer questions about the 2022 Winter Olympics."},
        {"role": "user", "content": message},
    ]
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=0
    )
    response_message = response["choices"][0]["message"]["content"]
    return response_message
```

## 6. 取得 ChatGPT 的答案

```python
from pprint import pprint

answer = ask('Who won the gold medal for curling in Olymics 2022?')

pprint(answer)
```

??? note "輸出"

    ```text
    ("There were three curling events at the 2022 Winter Olympics: men's, women's, "
     'and mixed doubles. The gold medalists for each event are:\n'
     '\n'
     "- Men's: Sweden (Niklas Edin, Oskar Eriksson, Rasmus Wranå, Christoffer "
     'Sundgren, Daniel Magnusson)\n'
     "- Women's: Great Britain (Eve Muirhead, Vicky Wright, Jennifer Dodds, Hailey "
     'Duff, Mili Smith)\n'
     '- Mixed doubles: Italy (Stefania Constantini, Amos Mosaner)')
    ```

## 重點整理
- 模型不知道訓練資料之後的事，這類問題要靠外部資料補上。
- 做法是 RAG：先搜尋相關內容，再把它當上下文放進 prompt。
- 向量存進資料庫前可以用 JSON_ARRAY_PACK 壓縮，查詢時用 SQL 函式算相似度。
- 同一個問題，沒有上下文和有上下文的回答，差別一眼就看得出來，適合拿來驗證 RAG 有沒有效。

## 練習
1. 把範例問題換成另一個冬季奧運相關的問題，比較有無上下文的回答。
2. 改語意搜尋回傳的筆數，看送給 ChatGPT 的上下文變多或變少時，答案有什麼變化。
3. 把資料換成你自己的 CSV，重做整個建表、存向量、搜尋的流程。
