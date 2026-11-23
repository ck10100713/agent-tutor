---
translated: true
source: examples/chatgpt/rag-quickstart/pinecone-retool/gpt-action-pinecone-retool-rag.ipynb
---
# Pinecone Vector Database 與 Retool Workflow 搭配 GPT Actions

> 原文：[examples/chatgpt/rag-quickstart/pinecone-retool/gpt-action-pinecone-retool-rag.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/rag-quickstart/pinecone-retool/gpt-action-pinecone-retool-rag.ipynb)



## 這篇在做什麼

用 Pinecone 當 vector database 存 OpenAI embedding，再用 Retool workflow 包成一個 REST endpoint，最後讓 Custom GPT 透過 action 呼叫它，做出一個能查你自己資料的 RAG。Retool 只是其中一種把 Pinecone 接到 ChatGPT 的做法。

## 學完你會

- 把文字轉成 embedding，建立 Pinecone index 並 upsert 進去，再用 query 驗證搜尋結果。
- 在 Retool 建一個 Python workflow，用 webhook trigger 對外提供 vector search API。
- 寫出 OpenAPI spec 並設定 API Key 驗證，讓 Custom GPT 以 action 呼叫這個 workflow。

## 開跑前

需要準備這些帳號和資源：

- Pinecone 帳號
- Retool 帳號
- 啟用 actions 的 Custom GPT
- OpenAI API key

[Pinecone](https://www.pinecone.io/) 是全託管的 vector database，專門用來儲存、索引和查詢大規模 vector embedding。它能做快速有效的相似度搜尋，很適合推薦系統、semantic search、自然語言處理這類 AI 應用。

[Retool](https://retool.com/) 是 low-code 平台，連接資料庫、API 和第三方服務，簡化內部工具的開發。只要很少的程式碼就能做出介面和 workflow，很適合簡化業務流程和整合複雜系統。


## 目錄

1. [設定 Pinecone](#setup-pinecone)
2. [設定 Notebook](#setup-notebook)
3. [準備資料](#prepare-data)
4. [建立 Pinecone Index](#create-a-pinecone-index)
5. [寫入 Pinecone Index](#populate-the-pinecone-index)
4. [建立 Retool Workflow](#create-a-retool-app)
5. [建立 Custom GPT Action](#create-a-custom-gpt-action)


## 設定 Pinecone

如果還沒有 Pinecone 帳號，先註冊一個。看到下面的畫面就可以進行下一節。到 API Keys 建立一把新的 API key。


![Vectors in Pinecone](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pinecone-dashboard.png)


## 設定 Notebook

安裝 OpenAI 和 Pinecone 需要的套件。

```python
!pip install -qU openai pinecone
```

匯入 OpenAI 和 Pinecone 套件。

```python

from pinecone.grpc import PineconeGRPC as Pinecone
from pinecone import ServerlessSpec
from openai import OpenAI
client = OpenAI() 

pc = Pinecone(api_key="YOUR API KEY")
## OpenAI key by default is set to the environment variable `OPENAI_API_KEY`
```

## 準備資料

定義一份範例資料集，用來 embed 後存進 Pinecone，並讓 ChatGPT 搜尋。

```python
data = [
    {"id": "vec1", "text": "OpenAI is a leading AI research organization focused on advancing artificial intelligence."},
    {"id": "vec2", "text": "The ChatGPT platform is renowned for its natural language processing capabilities."},
    {"id": "vec3", "text": "Many users leverage ChatGPT for tasks like creative writing, coding assistance, and customer support."},
    {"id": "vec4", "text": "OpenAI has revolutionized AI development with innovations like GPT-4 and its user-friendly APIs."},
    {"id": "vec5", "text": "ChatGPT makes AI-powered conversations accessible to millions, enhancing productivity and creativity."},
    {"id": "vec6", "text": "OpenAI was founded in December 2015 as an organization dedicated to advancing digital intelligence for the benefit of humanity."}
]
```

現在可以把文字轉成 embedding 了。下面是這個函式最簡單的實作。如果你的文字比所用模型的 context window 還長，就要先把文字切成較小的 chunk。

```python
def embed(text):
    text = text.replace("\n", " ")  # Ensure text doesn't have newlines
    res = client.embeddings.create(input=[text], model="text-embedding-3-large")
    
    return res.data[0].embedding

doc_embeds = [embed(d["text"]) for d in data]

print(doc_embeds)
```

## 建立 Pinecone Index

下一步是建立 Pinecone index。這裡用程式建立，你也可以在 Pinecone dashboard 上建。

```python
def create_index():
    index_name = "openai-cookbook-pinecone-retool"

    if not pc.has_index(index_name):
        pc.create_index(
            name=index_name,
            dimension=3072,
            metric="cosine",
            spec=ServerlessSpec(
                cloud='aws',
                region='us-east-1'
            )
        )
    
    return pc.Index(index_name)

index = create_index()
```

## 寫入 Pinecone Index

index 建好了，可以把 embedding 寫進去。寫入之前，要把 ID 和原始文字一起附加到 embedding 上，這樣查詢 index 時才能取回原文。

upsert vector 時要選一個 namespace。這是選填的，但如果想在同一個 index 存多份資料集，可以用它來分區。例如要存一份客服問題的資料集和一份產品描述的資料集，可以建兩個 namespace，各自獨立查詢。

```python
def append_vectors(data, doc_embeds):
    vectors = []
    for d, e in zip(data, doc_embeds):
        vectors.append({
            "id": d['id'],
            "values": e,
            "metadata": {'text': d['text']}
        })

    return vectors

vectors = append_vectors(data, doc_embeds)
```

```python
index.upsert(
    vectors=vectors,
    namespace="ns1"
)
```

??? note "輸出"

    ```text
    upserted_count: 6
    ```

現在應該能在 Pinecone Dashboard 看到這些 vector。

![Vectors in Pinecone](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/pinecone-dashboard-2.png)

這些 vector 現在應該已經顯示在 Pinecone Dashboard 了。

要測試搜尋功能，可以查詢 index。下面拿一個範例問題，用同一個 embedding 函式轉換，再到 index 裡找匹配的 vector。

`top_k` 是想回傳的結果數量。
`include_values` 和 `include_metadata` 用來回傳結果的 embedding 和原始文字。

```python
query = "When was OpenAI founded?"

x = embed(query)

results = index.query(
    namespace="ns1",
    vector=x,
    top_k=1,
    include_values=False,
    include_metadata=True
)

print(results)
```

??? note "輸出"

    ```text
    {'matches': [{'id': 'vec6',
                  'metadata': {'text': 'OpenAI was founded in December 2015 as an '
                                       'organization dedicated to advancing '
                                       'digital intelligence for the benefit of '
                                       'humanity.'},
                  'score': 0.7864019,
                  'sparse_values': {'indices': [], 'values': []},
                  'values': []}],
     'namespace': 'ns1',
     'usage': {'read_units': 6}}
    ```

## 建立 Retool Workflow

vector database 可以用了，接著建一個 Retool workflow 連到它，讓 ChatGPT 能執行查詢。

打開 Retool，建立一個新的 workflow。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retool-new-workflow.png" alt="Create Retool Workflowt" width="500"/>

你應該會看到下面的畫面。

![Retool Workflow 2](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retool-workflow-1.png)

這個例子用 Python 查詢 Pinecone index，所以需要匯入 `pinecone` 和 `openai` 套件。先切換到 Python。

<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(55.43981481481482% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/DnaN9MnRjDaBL9HWKabX?embed&embed_mobile=inline&embed_desktop=inline&show_copy_link=true" title="Cookbook - Retool Libraries" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

現在可以把程式碼加到 code block 裡了。

先宣告剛匯入到這個 workflow 的套件。


```python
from pinecone import Pinecone
from openai import OpenAI
```

接著設定 Pinecone 和 OpenAI 的 API key。可以直接寫在 code block 裡，也可以用 [Retool Configuration Variables](https://docs.retool.com/org-users/guides/config-vars)。比較推薦用 configuration variable，因為更安全，下面就是這種寫法。


```python
client = OpenAI(api_key=retoolContext.configVars.openai_api_key) 
pc = Pinecone(api_key=retoolContext.configVars.pinecone_api_key)
```

然後在 Retool 的程式碼片段裡，重用前面的 OpenAI Embedding 和 Pinecone 查詢函式，並回傳結果。下面是完成的 code block。

```startTrigger.data.query``` is a variable passed in from the start trigger of the workflow. This is where the user query from ChatGPT will be passed in.

```python
from pinecone import Pinecone
from openai import OpenAI

client = OpenAI(api_key=retoolContext.configVars.openai_api_key) 
pc = Pinecone(api_key=retoolContext.configVars.pinecone_api_key)
index = pc.Index("openai-cookbook-pinecone-retool")


def embed(query):
    res = client.embeddings.create(
        input=query,
        model="text-embedding-3-large"
    )
    doc_embeds = [r.embedding for r in res.data] 
    return doc_embeds 

x = embed([startTrigger.data.query])

results = index.query(
    namespace="ns1",
    vector=x[0],
    top_k=2,
    include_values=False,
    include_metadata=True
)

return results.to_dict()['matches']
```

在 UI 裡會長得像這樣。點 code block 上方的執行按鈕就能測試，結果會顯示在 code block 下方的 Data 區。

![Retool Workflow 3](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retool-workflow-2.png)

現在 workflow 有一個 start trigger，會接收使用者的 query 並傳給 Vector_Search code block，由它從 Pinecone index 回傳前 2 筆結果。接下來要加一個 block，把這些結果拿去回應 start trigger 的請求。


<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(55.43981481481482% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/6lyRo3PP2iWq814KvY1f?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Cookbook - Retool Return" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

最後要把 start trigger 設成可以用 API 呼叫，這樣才能當 ChatGPT action 使用。

到 Triggers，打開 Webhook 的開關，再點 Webhook 進入設定畫面。可以選擇加一個 Alias 來描述這個 webhook 會觸發什麼。這裡取名為 `vector_search`，這樣 URL 裡會有比較好辨識的名稱。完成後按 Save Changes。

![Retool Workflow 4](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retool-workflow-3.png)

最後一步是部署 workflow。點畫面上方的 Deploy 按鈕，workflow 就能透過 API 存取了。要測試的話，點 Alias URL 旁的複製按鈕，選 Copy as cURL，然後在終端機執行。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retool-workflow-4.png" alt="Retool Workflow 5" width="400"/>


## 建立 Custom GPT Action

現在有了可用的 Vector Database，也有一個透過 Retool Workflow 用 API 查詢它的方式。下一步是用 action 把 Retool Workflow 接到 ChatGPT。

到你的 GPT，建立一個新的 action。下面是連接 Retool Workflow 所需的 OpenAPI spec 範例。你要把 URL 和 API key 換成自己的。

```openapi
openapi: 3.1.0
info:
  title: Vector Search API
  description: An API for performing vector-based search queries.
  version: 1.0.0
servers:
  - url: YOUR_URL_HERE
    description: Sandbox server for the Vector Search API
paths:
  /url/vector-search:
    post:
      operationId: performVectorSearch
      summary: Perform a vector-based search query.
      description: Sends a query to the vector search API and retrieves results.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: The search query.
              required:
                - query
      responses:
        '200':
          description: Successful response containing search results.
        '400':
          description: Bad Request. The input data is invalid.
        '500':
          description: Internal Server Error. Something went wrong on the server side.
```

在 Authentication 區塊，把驗證方式設成 API Key。貼上 Retool Workflow trigger 設定裡的 API key。再把 Auth Type 設成 Custom，Custom Header Name 填 ```X-Workflow-Api-Key```

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/chatgpt-auth-config.png" alt="ChatGPT Auth Config" width="400"/>


設定完成。你可以傳訊息給你的 GPT，問一個向量資料庫裡有的資訊來測試。

<img src="https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt-rag-result.png" alt="GPT RAG Result" width="600"/>

## 重點整理

- ChatGPT 本身不能直接連 vector database，要中間包一層 HTTP endpoint，再用 Custom GPT action 去呼叫。
- 查詢時要用跟寫入時同一個 embedding 模型，才能做相似度比對。
- 寫入時把原文放在 metadata，查詢結果才能直接回傳原文。
- namespace 可以在同一個 index 裡把不同資料集分區，各自查詢。
- API key 放在 Retool Configuration Variables 比寫在程式碼裡安全。

## 練習

1. 把查詢的 `top_k` 從 2 改成 3，看看回傳的結果有什麼不同。
2. 在範例資料集裡多加幾筆文字，重新 upsert 到另一個 namespace，查詢時指定那個 namespace。
3. 修改 Retool 的 Vector_Search code block，把回傳結果只留下 metadata 裡的原文，並同步調整 OpenAPI spec 的 response schema。
