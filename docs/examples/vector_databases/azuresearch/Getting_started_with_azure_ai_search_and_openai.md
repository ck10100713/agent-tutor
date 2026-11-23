---
translated: true
source: examples/vector_databases/azuresearch/Getting_started_with_azure_ai_search_and_openai.ipynb
---

# 用 Azure AI Search 當 OpenAI embedding 的 vector database

> 原文：[examples/vector_databases/azuresearch/Getting_started_with_azure_ai_search_and_openai.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/vector_databases/azuresearch/Getting_started_with_azure_ai_search_and_openai.ipynb)



## 這篇在做什麼
示範把 Azure AI Search 當成 vector database，存放 OpenAI 的 embedding，並對 Wikipedia 文章做搜尋。從建 index、上傳資料，一路做到向量搜尋、混合搜尋和語意重排。

## 學完你會
- 用 Azure AI Search 的 Python SDK 建立同時支援 vector search 和 semantic ranker 的 index
- 把帶有預先算好 embedding 的 DataFrame 批次上傳到 index
- 分別跑出向量搜尋、混合搜尋（hybrid）和帶重排的混合搜尋

## 開跑前
- 一個 Azure AI Search Service
- OpenAI API key 或 Azure OpenAI 憑證

這個 notebook 一步步說明怎麼把 Azure AI Search（舊名 Azure Cognitive Search）當成 vector database 搭配 OpenAI embedding 使用。Azure AI Search 是雲端搜尋服務，提供基礎設施、API 和工具，讓開發者針對網頁、行動和企業應用裡的私有、異質內容建立豐富的搜尋體驗。

## 前置條件：
要做這個練習，你需要：
- [Azure AI Search Service](https://learn.microsoft.com/azure/search/)
- [OpenAI Key](https://platform.openai.com/account/api-keys) 或 [Azure OpenAI 憑證](https://learn.microsoft.com/azure/cognitive-services/openai/)

```python
! pip install wget
! pip install azure-search-documents 
! pip install azure-identity
! pip install openai
```

## 匯入需要的函式庫

```python
import json  
import wget
import pandas as pd
import zipfile
from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.core.credentials import AzureKeyCredential  
from azure.search.documents import SearchClient, SearchIndexingBufferedSender  
from azure.search.documents.indexes import SearchIndexClient  
from azure.search.documents.models import (
    QueryAnswerType,
    QueryCaptionType,
    QueryType,
    VectorizedQuery,
)
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchableField,
    SearchFieldDataType,
    SearchIndex,
    SemanticConfiguration,
    SemanticField,
    SemanticPrioritizedFields,
    SemanticSearch,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmKind,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)
```

## 設定 OpenAI

這一段說明怎麼設定 Azure OpenAI 的驗證，可以用 Azure Active Directory (AAD) 或 API key 安全地使用服務。開始前請先備好 Azure OpenAI 的 endpoint 和憑證。AAD 的設定細節請看[官方文件](https://learn.microsoft.com/azure/ai-services/openai/how-to/managed-identity)。


```python
endpoint: str = "YOUR_AZURE_OPENAI_ENDPOINT"
api_key: str = "YOUR_AZURE_OPENAI_KEY"
api_version: str = "2023-05-15"
deployment = "YOUR_AZURE_OPENAI_DEPLOYMENT_NAME"
credential = DefaultAzureCredential()
token_provider = get_bearer_token_provider(
    credential, "https://cognitiveservices.azure.com/.default"
)

# Set this flag to True if you are using Azure Active Directory
use_aad_for_aoai = True 

if use_aad_for_aoai:
    # Use Azure Active Directory (AAD) authentication
    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_version=api_version,
        azure_ad_token_provider=token_provider,
    )
else:
    # Use API key authentication
    client = AzureOpenAI(
        api_key=api_key,
        api_version=api_version,
        azure_endpoint=endpoint,
    )
```

## 設定 Azure AI Search 的 Vector Store

這一段說明怎麼設定 Azure AI Search client 來使用 Vector Store 功能。你可以在 Azure Portal 找到 Azure AI Search 服務的資訊，或用 [Search Management SDK](https://learn.microsoft.com/rest/api/searchmanagement/) 以程式取得。


```python
# Configuration
search_service_endpoint: str = "YOUR_AZURE_SEARCH_ENDPOINT"
search_service_api_key: str = "YOUR_AZURE_SEARCH_ADMIN_KEY"
index_name: str = "azure-ai-search-openai-cookbook-demo"

# Set this flag to True if you are using Azure Active Directory
use_aad_for_search = True  

if use_aad_for_search:
    # Use Azure Active Directory (AAD) authentication
    credential = DefaultAzureCredential()
else:
    # Use API key authentication
    credential = AzureKeyCredential(search_service_api_key)

# Initialize the SearchClient with the selected authentication method
search_client = SearchClient(
    endpoint=search_service_endpoint, index_name=index_name, credential=credential
)
```

## 載入資料


```python
embeddings_url = "https://cdn.openai.com/API/examples/data/vector_database_wikipedia_articles_embedded.zip"

# The file is ~700 MB so this will take some time
wget.download(embeddings_url)
```

??? note "輸出"

    ```text
    'vector_database_wikipedia_articles_embedded.zip'
    ```

```python
with zipfile.ZipFile("vector_database_wikipedia_articles_embedded.zip", "r") as zip_ref:
    zip_ref.extractall("../../data")
```

```python
article_df = pd.read_csv("../../data/vector_database_wikipedia_articles_embedded.csv")

# Read vectors from strings back into a list using json.loads
article_df["title_vector"] = article_df.title_vector.apply(json.loads)
article_df["content_vector"] = article_df.content_vector.apply(json.loads)
article_df["vector_id"] = article_df["vector_id"].apply(str)
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

                                          content_vector vector_id  
    0  [-0.011253940872848034, -0.013491976074874401,...         0  
    1  [0.0003609954728744924, 0.007262262050062418, ...         1  
    2  [-0.004959689453244209, 0.015772193670272827, ...         2  
    3  [0.024894846603274345, -0.022186409682035446, ...         3  
    4  [0.021524671465158463, 0.018522677943110466, -...         4
    ```

##  建立 index
這段程式示範怎麼用 Azure AI Search Python SDK 的 `SearchIndexClient` 定義並建立搜尋 index。這個 index 同時具備 vector search 和 semantic ranker 能力。更多細節請看文件：[建立 Vector Index](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index?.tabs=config-2023-11-01%2Crest-2023-11-01%2Cpush%2Cportal-check-index)

```python
# Initialize the SearchIndexClient
index_client = SearchIndexClient(
    endpoint=search_service_endpoint, credential=credential
)

# Define the fields for the index
fields = [
    SimpleField(name="id", type=SearchFieldDataType.String),
    SimpleField(name="vector_id", type=SearchFieldDataType.String, key=True),
    SimpleField(name="url", type=SearchFieldDataType.String),
    SearchableField(name="title", type=SearchFieldDataType.String),
    SearchableField(name="text", type=SearchFieldDataType.String),
    SearchField(
        name="title_vector",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        vector_search_dimensions=1536,
        vector_search_profile_name="my-vector-config",
    ),
    SearchField(
        name="content_vector",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
        vector_search_dimensions=1536,
        vector_search_profile_name="my-vector-config",
    ),
]

# Configure the vector search configuration
vector_search = VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(
            name="my-hnsw",
            kind=VectorSearchAlgorithmKind.HNSW,
            parameters=HnswParameters(
                m=4,
                ef_construction=400,
                ef_search=500,
                metric=VectorSearchAlgorithmMetric.COSINE,
            ),
        )
    ],
    profiles=[
        VectorSearchProfile(
            name="my-vector-config",
            algorithm_configuration_name="my-hnsw",
        )
    ],
)

# Configure the semantic search configuration
semantic_search = SemanticSearch(
    configurations=[
        SemanticConfiguration(
            name="my-semantic-config",
            prioritized_fields=SemanticPrioritizedFields(
                title_field=SemanticField(field_name="title"),
                keywords_fields=[SemanticField(field_name="url")],
                content_fields=[SemanticField(field_name="text")],
            ),
        )
    ]
)

# Create the search index with the vector search and semantic search configurations
index = SearchIndex(
    name=index_name,
    fields=fields,
    vector_search=vector_search,
    semantic_search=semantic_search,
)

# Create or update the index
result = index_client.create_or_update_index(index)
print(f"{result.name} created")
```

??? note "輸出"

    ```text
    azure-ai-search-openai-cookbook-demo created
    ```

## 上傳資料到 Azure AI Search index

下面的程式說明怎麼把一批文件（也就是已經算好 embedding 的 Wikipedia 文章）從 pandas DataFrame 上傳到 Azure AI Search index。資料匯入策略與 best practice 的詳細說明請看 [Data Import in Azure AI Search](https://learn.microsoft.com/azure/search/search-what-is-data-import)。


```python
from azure.core.exceptions import HttpResponseError

# Convert the 'id' and 'vector_id' columns to string so one of them can serve as our key field
article_df["id"] = article_df["id"].astype(str)
article_df["vector_id"] = article_df["vector_id"].astype(str)
# Convert the DataFrame to a list of dictionaries
documents = article_df.to_dict(orient="records")

# Create a SearchIndexingBufferedSender
batch_client = SearchIndexingBufferedSender(
    search_service_endpoint, index_name, credential
)

try:
    # Add upload actions for all documents in a single call
    batch_client.upload_documents(documents=documents)

    # Manually flush to send any remaining documents in the buffer
    batch_client.flush()
except HttpResponseError as e:
    print(f"An error occurred: {e}")
finally:
    # Clean up resources
    batch_client.close()

print(f"Uploaded {len(documents)} documents in total")
```

??? note "輸出"

    ```text
    Uploaded 25000 documents in total
    ```

如果你的資料集沒有預先算好的 embedding，可以用下面這個函式搭配 `openai` Python 函式庫來產生。你也會看到，做向量搜尋時，query embedding 也是用同一個函式和同一個模型產生。

```python
# Example function to generate document embedding
def generate_embeddings(text, model):
    # Generate embeddings for the provided text using the specified model
    embeddings_response = client.embeddings.create(model=model, input=text)
    # Extract the embedding data from the response
    embedding = embeddings_response.data[0].embedding
    return embedding


first_document_content = documents[0]["text"]
print(f"Content: {first_document_content[:100]}")

content_vector = generate_embeddings(first_document_content, deployment)
print("Content vector generated")
```

??? note "輸出"

    ```text
    Content: April is the fourth month of the year in the Julian and Gregorian calendars, and comes between March
    Content vector generated
    ```

## 執行向量相似度搜尋

```python
# Pure Vector Search
query = "modern art in Europe"
  
search_client = SearchClient(search_service_endpoint, index_name, credential)  
vector_query = VectorizedQuery(vector=generate_embeddings(query, deployment), k_nearest_neighbors=3, fields="content_vector")
  
results = search_client.search(  
    search_text=None,  
    vector_queries= [vector_query], 
    select=["title", "text", "url"] 
)
  
for result in results:  
    print(f"Title: {result['title']}")  
    print(f"Score: {result['@search.score']}")  
    print(f"URL: {result['url']}\n")
```

??? note "輸出"

    ```text
    Title: Documenta
    Score: 0.8599451
    URL: https://simple.wikipedia.org/wiki/Documenta

    Title: Museum of Modern Art
    Score: 0.85260946
    URL: https://simple.wikipedia.org/wiki/Museum%20of%20Modern%20Art

    Title: Expressionism
    Score: 0.852354
    URL: https://simple.wikipedia.org/wiki/Expressionism
    ```

## 執行混合搜尋 (Hybrid Search)
混合搜尋結合傳統關鍵字搜尋與向量相似度搜尋，能提供更相關、更貼近上下文的結果。遇到需要理解語意的複雜查詢時特別有用。

下面的程式示範怎麼執行混合搜尋：

```python
# Hybrid Search
query = "Famous battles in Scottish history"  
  
search_client = SearchClient(search_service_endpoint, index_name, credential)  
vector_query = VectorizedQuery(vector=generate_embeddings(query, deployment), k_nearest_neighbors=3, fields="content_vector")
  
results = search_client.search(  
    search_text=query,  
    vector_queries= [vector_query], 
    select=["title", "text", "url"],
    top=3
)
  
for result in results:  
    print(f"Title: {result['title']}")  
    print(f"Score: {result['@search.score']}")  
    print(f"URL: {result['url']}\n")
```

??? note "輸出"

    ```text
    Title: Wars of Scottish Independence
    Score: 0.03306011110544205
    URL: https://simple.wikipedia.org/wiki/Wars%20of%20Scottish%20Independence

    Title: Battle of Bannockburn
    Score: 0.022253260016441345
    URL: https://simple.wikipedia.org/wiki/Battle%20of%20Bannockburn

    Title: Scottish
    Score: 0.016393441706895828
    URL: https://simple.wikipedia.org/wiki/Scottish
    ```

## 執行混合搜尋並重排 (Reranking，由 Bing 提供)
[Semantic ranker](https://learn.microsoft.com/azure/search/semantic-search-overview) 用語言理解重新排序搜尋結果，能明顯提升相關性。另外你還能拿到摘錄式的 caption、answer 和 highlight。 

```python
# Semantic Hybrid Search
query = "What were the key technological advancements during the Industrial Revolution?"

search_client = SearchClient(search_service_endpoint, index_name, credential)
vector_query = VectorizedQuery(
    vector=generate_embeddings(query, deployment),
    k_nearest_neighbors=3,
    fields="content_vector",
)

results = search_client.search(
    search_text=query,
    vector_queries=[vector_query],
    select=["title", "text", "url"],
    query_type=QueryType.SEMANTIC,
    semantic_configuration_name="my-semantic-config",
    query_caption=QueryCaptionType.EXTRACTIVE,
    query_answer=QueryAnswerType.EXTRACTIVE,
    top=3,
)

semantic_answers = results.get_answers()
for answer in semantic_answers:
    if answer.highlights:
        print(f"Semantic Answer: {answer.highlights}")
    else:
        print(f"Semantic Answer: {answer.text}")
    print(f"Semantic Answer Score: {answer.score}\n")

for result in results:
    print(f"Title: {result['title']}")
    print(f"Reranker Score: {result['@search.reranker_score']}")
    print(f"URL: {result['url']}")
    captions = result["@search.captions"]
    if captions:
        caption = captions[0]
        if caption.highlights:
            print(f"Caption: {caption.highlights}\n")
        else:
            print(f"Caption: {caption.text}\n")
```

??? note "輸出"

    ```text
    Semantic Answer: Advancements  During the industrial revolution, new technology brought many changes. For example:<em>   Canals</em> were built to allow heavy goods to be moved easily where they were needed. The steam engine became the main source of power. It replaced horses and human labor. Cheap iron and steel became mass-produced.
    Semantic Answer Score: 0.90478515625

    Title: Industrial Revolution
    Reranker Score: 3.408700942993164
    URL: https://simple.wikipedia.org/wiki/Industrial%20Revolution
    Caption: Advancements  During the industrial revolution, new technology brought many changes. For example:   Canals were built to allow heavy goods to be moved easily where they were needed. The steam engine became the main source of power. It replaced horses and human labor. Cheap iron and steel became mass-produced.

    Title: Printing
    Reranker Score: 1.603400707244873
    URL: https://simple.wikipedia.org/wiki/Printing
    Caption: Machines to speed printing, cheaper paper, automatic stitching and binding all arrived in the 19th century during the industrial revolution. What had once been done by a few men by hand was now done by limited companies on huge machines. The result was much lower prices, and a much wider readership.

    Title: Industrialisation
    Reranker Score: 1.3238357305526733
    URL: https://simple.wikipedia.org/wiki/Industrialisation
    Caption: <em>Industrialisation</em> (or<em> industrialization)</em> is a process that happens in countries when they start to use machines to do work that was once done by people.<em> Industrialisation changes</em> the things people do.<em> Industrialisation</em> caused towns to grow larger. Many people left farming to take higher paid jobs in factories in towns.
    ```

## 重點整理
- Azure AI Search 能同時當關鍵字搜尋引擎和 vector database，index 的 schema 要同時定義向量欄位。
- 查詢的 embedding 必須和文件用同一個模型產生，向量搜尋才有意義。
- 混合搜尋把關鍵字與向量分數合在一起，通常比單純向量搜尋更穩。
- semantic ranker 是在檢索結果上再做一次語言理解的重排，可進一步提升相關性。

## 練習
1. 換一個查詢句子，比較向量搜尋和混合搜尋回傳的前幾筆結果有什麼不同。
2. 調整搜尋時回傳的筆數（top 參數），觀察結果變化。
3. 在混合搜尋的程式裡，改用不同欄位做向量查詢（例如 title 與 content 的 embedding），比較哪一個結果更準。
