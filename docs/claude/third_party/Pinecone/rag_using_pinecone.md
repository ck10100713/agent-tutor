---
translated: true
source: third_party/Pinecone/rag_using_pinecone.ipynb
---

# 用 Pinecone 做 Retrieval-augmented generation

> 原文：[third_party/Pinecone/rag_using_pinecone.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/Pinecone/rag_using_pinecone.ipynb)

把 Claude 接上 Pinecone 向量資料庫，做 retrieval-augmented generation 和語意搜尋。

## 這篇在做什麼

這份 notebook 示範用 retrieval-augmented generation（RAG）把 Claude 接到你放在 Pinecone 向量資料庫裡的資料。流程是把 Amazon 商品描述做成 embedding 存進 Pinecone，再讓 Claude 產生搜尋關鍵字、檢索、回答問題。

## 學完你會

- 用 Voyage AI 的 embedding model 把資料集轉成向量，並上傳到 Pinecone index。
- 用自然語言問題對向量資料庫做語意搜尋。
- 讓 Claude 先從問題產生搜尋關鍵字擴大檢索，再根據檢索結果回答。

## 開跑前

需要三組 API key：Claude API key、免費的 Pinecone API key、免費的 Voyage AI API key。

這份 notebook 示範怎麼用 retrieval-augmented generation（RAG）把 Claude 接到你的 Pinecone 向量資料庫資料。步驟如下：

1. 用 Voyage AI 的 embedding model 對資料集做 embedding
2. 把 embedding 上傳到 Pinecone index
3. 從向量資料庫檢索資訊
4. 讓 Claude 利用資料庫裡的資訊回答問題

## Setup
首先安裝需要的套件，並設定這份 notebook 會用到的 API key。我們需要一組 [Claude API key](https://docs.claude.com/en/api/overview)、一組免費的 [Pinecone API key](https://docs.pinecone.io/docs/quickstart)，以及一組免費的 [Voyage AI API key](https://docs.voyageai.com/install/)。

```python
%pip install anthropic datasets pinecone-client voyageai
```

```python
# Insert your API keys here
ANTHROPIC_API_KEY = "<YOUR_ANTHROPIC_API_KEY>"
PINECONE_API_KEY = "<YOUR_PINECONE_API_KEY>"
VOYAGE_API_KEY = "<YOUR_VOYAGE_API_KEY>"
```

## 下載資料集
現在下載 Amazon 商品資料集，裡面有超過 1 萬筆 Amazon 商品描述，並載入成 DataFrame。

```python
import pandas as pd

# Download the JSONL file
!wget  https://www-cdn.anthropic.com/48affa556a5af1de657d426bcc1506cdf7e2f68e/amazon-products.jsonl

data = []
with open("amazon-products.jsonl") as file:
    for line in file:
        try:
            data.append(eval(line))  # noqa: S307
        except (SyntaxError, ValueError):
            # Skip malformed lines in the dataset
            pass

df = pd.DataFrame(data)
display(df.head())
len(df)
```

## 向量資料庫

要建立向量資料庫，先要有 Pinecone 的免費 API key。拿到 key 之後，可以這樣初始化資料庫：

```python
from pinecone import Pinecone

pc = Pinecone(api_key=PINECONE_API_KEY)
```

接著設定 index 規格，讓我們定義要部署 index 的雲端供應商和區域。所有可用的供應商和區域列表在[這裡](https://docs.pinecone.io/guides/index-data/indexing-overview)。


```python
from pinecone import ServerlessSpec

spec = ServerlessSpec(cloud="aws", region="us-west-2")
```

然後初始化 index。我們會用 Voyage 的 "voyage-2" model 建立 embedding，所以把維度設成 1024。

```python
import time

index_name = "amazon-products"
existing_indexes = [index_info["name"] for index_info in pc.list_indexes()]

# check if index already exists (it shouldn't if this is first time)
if index_name not in existing_indexes:
    # if does not exist, create index
    pc.create_index(
        index_name,
        dimension=1024,  # dimensionality of voyage-2 embeddings
        metric="dotproduct",
        spec=spec,
    )
    # wait for index to be initialized
    while not pc.describe_index(index_name).status["ready"]:
        time.sleep(1)

# connect to index
index = pc.Index(index_name)
time.sleep(1)
# view index stats
index.describe_index_stats()
```

應該會看到新的 Pinecone index 的 total_vector_count 是 0，因為我們還沒加入任何向量。

## Embeddings
要開始使用 Voyage 的 embedding，到[這裡](https://www.voyageai.com)取得 API key。

現在設定 Voyage client，並示範怎麼用 `embed` 方法建立 embedding。想進一步了解怎麼把 Voyage embedding 跟 Claude 一起用，見[這份 notebook](https://github.com/anthropics/claude-cookbooks/blob/main/third_party/VoyageAI/how_to_create_embeddings.md)。

```python
import voyageai

vo = voyageai.Client(api_key=VOYAGE_API_KEY)

texts = ["Sample text 1", "Sample text 2"]

result = vo.embed(texts, model="voyage-2", input_type="document")
print(result.embeddings[0])
print(result.embeddings[1])
```

## 把資料上傳到 Pinecone index

embedding model 設定好之後，就可以把商品描述做成 embedding，並上傳到 Pinecone index。

```python
from time import sleep

from tqdm.auto import tqdm

descriptions = df["text"].tolist()
batch_size = 100  # how many embeddings we create and insert at once

for i in tqdm(range(0, len(descriptions), batch_size)):
    # find end of batch
    i_end = min(len(descriptions), i + batch_size)
    descriptions_batch = descriptions[i:i_end]
    # create embeddings (try-except added to avoid RateLimitError. Voyage currently allows 300/requests per minute.)
    done = False
    while not done:
        try:
            res = vo.embed(descriptions_batch, model="voyage-2", input_type="document")
            done = True
        except Exception:
            sleep(5)

    embeds = [record for record in res.embeddings]
    # create unique IDs for each text
    ids_batch = [f"description_{idx}" for idx in range(i, i_end)]

    # Create metadata dictionaries for each text
    metadata_batch = [{"description": description} for description in descriptions_batch]

    to_upsert = list(zip(ids_batch, embeds, metadata_batch, strict=False))

    # upsert to Pinecone
    index.upsert(vectors=to_upsert)
```

## 查詢

index 填好資料後，就可以開始查詢。我們可以拿一個自然語言問題，做成 embedding 後對 index 查詢，回傳語意相近的商品描述。

```python
USER_QUESTION = (
    "I want to get my daughter more interested in science. What kind of gifts should I get her?"
)

question_embed = vo.embed([USER_QUESTION], model="voyage-2", input_type="query")
results = index.query(vector=question_embed.embeddings, top_k=5, include_metadata=True)
results
```

??? note "輸出"

    ```text
    {'matches': [{'id': 'description_1771',
                  'metadata': {'description': 'Product Name: Scientific Explorer '
                                              'My First Science Kids Science '
                                              'Experiment Kit\n'
                                              '\n'
                                              'About Product: Experiments to spark '
                                              'creativity and curiosity | Grow '
                                              'watery crystals, create a rainbow '
                                              'in a plate, explore the science of '
                                              'color and more | Represents STEM '
                                              '(Science, Technology, Engineering, '
                                              'Math) principles – open ended toys '
                                              'to construct, engineer, explorer '
                                              'and experiment | Includes cross '
                                              'linked polyacrylamide, 3 color '
                                              'tablets, 3 mixing cups, 3 test '
                                              'tubes, caps and stand, pipette, '
                                              'mixing tray, magnifier and '
                                              'instructions | Recommended for '
                                              'children 4 years of age and older '
                                              'with adult supervision\n'
                                              '\n'
                                              'Categories: Toys & Games | Learning '
                                              '& Education | Science Kits & Toys'},
                  'score': 0.772703767,
                  'values': []},
                 {'id': 'description_3133',
                  'metadata': {'description': 'Product Name: Super Science Magnet '
                                              'Kit.\n'
                                              '\n'
                                              'About Product: \n'
                                              '\n'
                                              'Categories: Toys & Games | Learning '
                                              '& Education | Science Kits & Toys'},
                  'score': 0.765997052,
                  'values': []},
                 {'id': 'description_1792',
                  'metadata': {'description': 'Product Name: BRIGHT Atom Model - '
                                              'Student\n'
                                              '\n'
    ... (省略 56 行)
    ```

## 優化搜尋

這些結果不錯，但還可以再優化。用 Claude 可以從使用者的問題產生搜尋關鍵字。這樣能對 index 做廣泛、多樣的搜尋，拿到更相關的商品描述。

```python
import anthropic

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL_NAME = "claude-haiku-5-5"


def get_completion(messages):
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=messages,
    )
    return "".join(b.text for b in response.content if b.type == "text")
```

```python
def create_keyword_messages(question):
    user_content = f"""Given a question, generate a list of 5 very diverse search keywords that can be used to search for products on Amazon.

The question is: {question}

Output your keywords as a JSON object that has one property "keywords" that is a list of strings. Wrap the JSON in <json></json> tags and output nothing else."""
    return [{"role": "user", "content": user_content}]
```

Anthropic client 和 prompt 都準備好之後，就能從問題產生關鍵字了。這個 prompt 要求 Claude 把 JSON 包在 `<json></json>` 標籤裡，這樣我們才能穩定地抽出來。

```python
import re

raw = get_completion(create_keyword_messages(USER_QUESTION))
keyword_json = re.search(r"<json>(.*?)</json>", raw, re.DOTALL).group(1).strip()
print(keyword_json)
```

```python
import json

# Extract the keywords from the JSON
data = json.loads(keyword_json)
keywords_list = data["keywords"]
print(keywords_list)
```

現在有了關鍵字清單，把每個關鍵字做成 embedding，對 index 查詢，回傳前 3 個最相關的商品描述。

```python
results_list = []
for keyword in keywords_list:
    # get the embeddings for the keywords
    query_embed = vo.embed([keyword], model="voyage-2", input_type="query")
    # search for the embeddings in the Pinecone index
    search_results = index.query(vector=query_embed.embeddings, top_k=3, include_metadata=True)
    # append the search results to the list
    for search_result in search_results.matches:
        results_list.append(search_result["metadata"]["description"])
print(len(results_list))
```

## 用 Claude 回答

現在有了一份商品描述清單，把它們格式化成 Claude 訓練時看過的搜尋 template，再把格式化後的描述傳給另一個 prompt。

```python
# Formatting search results
def format_results(extracted: list[str]) -> str:
    result = "\n".join(
        [
            f'<item index="{i + 1}">\n<page_content>\n{r}\n</page_content>\n</item>'
            for i, r in enumerate(extracted)
        ]
    )

    return f"\n<search_results>\n{result}\n</search_results>"


def create_answer_messages(results_list, question):
    user_content = f"""{format_results(results_list)}

Using the search results provided within the <search_results></search_results> tags, please answer the following question <question>{question}</question>. Do not reference the search results in your answer."""
    return [{"role": "user", "content": user_content}]
```

最後，問原本使用者的問題，並從 Claude 拿到答案。

```python
answer = get_completion(create_answer_messages(results_list, USER_QUESTION))
print(answer)
```

## 重點整理

- RAG 的流程是：資料做 embedding、存進向量資料庫、查詢相近內容、再讓 LLM 根據檢索結果回答。
- Embedding 的維度要跟 index 設定一致（voyage-2 是 1024）。
- 直接拿使用者問題搜尋可行，但讓 Claude 先產生多個關鍵字，能讓檢索範圍更廣、更多樣。
- 要求輸出包在 `<json>` 標籤裡，能讓程式穩定解析 Claude 的結果。
- 檢索結果要整理成 Claude 熟悉的 template 格式，回答才會比較準。

## 練習

1. 改變查詢的自然語言問題，看回傳的商品描述是否符合預期。
2. 把每個關鍵字取回的結果從前 3 個改成前 5 個，觀察 Claude 回答的差異。
3. 修改產生關鍵字的 prompt，要求 Claude 產生更多（或更少）的關鍵字，比較檢索結果的多樣性與最後答案的品質。
