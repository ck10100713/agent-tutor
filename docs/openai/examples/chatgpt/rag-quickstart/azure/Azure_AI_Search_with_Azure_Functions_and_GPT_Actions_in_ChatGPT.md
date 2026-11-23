---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/rag-quickstart/azure/Azure_AI_Search_with_Azure_Functions_and_GPT_Actions_in_ChatGPT.ipynb
---
# Azure AI Search with Azure Functions and GPT Actions in ChatGPT

> 原文：[examples/chatgpt/rag-quickstart/azure/Azure_AI_Search_with_Azure_Functions_and_GPT_Actions_in_ChatGPT.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/rag-quickstart/azure/Azure_AI_Search_with_Azure_Functions_and_GPT_Actions_in_ChatGPT.ipynb)



## 這篇在做什麼

這篇一步步帶你把 Azure AI Search 當 vector database，存放用 OpenAI embedding 處理過的文件，再用 Azure Function 包成 API，接到 ChatGPT 的 Custom GPT 當 GPT Action。整套 RAG 基礎設施都在 Azure 裡，只把一個 endpoint 開出去給 ChatGPT 之類的平台用。

## 學完你會

- 把文件切 chunk、做 embedding、加 metadata，上傳到 Azure AI Search 的 index
- 在本機測試純 vector search 和 hybrid search
- 部署 Azure Function，並產生 OpenAPI spec 和 instructions 接進 Custom GPT

## 開跑前

- 有權限建立 Azure AI Search Service 和 Function App 的 Azure 帳號，以及 subscription ID 和 resource group（會產生 Azure 費用）
- OpenAI API Key
- 本機要有 Azure CLI 和 Azure Functions Core Tools（文中的程式碼會嘗試幫你安裝）

這篇的 notebook 說明了怎麼用 Azure AI Search（舊名 Azure Cognitive Search）當 vector database 搭配 OpenAI embedding，再在上面建立 Azure Function，接到 ChatGPT 的 Custom GPT。

這可以給想把 RAG 基礎設施放在 Azure 內，並把它開成 endpoint 來整合 ChatGPT 等其他平台的客戶參考。

Azure AI Search 是雲端搜尋服務，提供開發者基礎設施、API 和工具，用來在網頁、行動和企業應用程式裡，對私有的異質內容建立豐富的搜尋體驗。

Azure Functions 是 serverless 運算服務，執行事件驅動的程式碼，自動管理基礎設施、擴展，並整合其他 Azure 服務。

## 前置需求：
要完成這個練習，你需要：
- 有權限建立 [Azure AI Search Service](https://learn.microsoft.com/azure/search/) 和 Azure Function Apps 的 Azure 使用者
- Azure subscription ID 和一個 resource group。
- [OpenAI Key](https://platform.openai.com/account/api-keys) 

# 架構
下面是這個方案的架構圖，我們會一步步走過。

![azure-rag-architecture.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/azure-rag-architecture.png)


> 注意：這種 vector data store 加 serverless function 的架構，也可以套用到其他 vector data store。例如想在 Azure 內用 Postgres，就把 [Configure Azure AI Search Settings](#configure-azure-ai-search-settings) 那步改成設定 Postgres 的需求，把 [Create Azure AI Vector Search](#create-azure-ai-vector-search) 改成在 Postgres 建資料庫和資料表，再把這個 repository 裡的 `function_app.py` 改成查 Postgres，不再查 Azure AI Search。資料準備和 Azure Function 的建立則維持不變。


# 目錄：

1. **[環境設定](#set-up-environment)**
    安裝並 import 需要的函式庫，設定 Azure 相關設定。包含：
     - [Install and Import Required Libraries](#install-and-import-required-libraries)
     - [Configure OpenAI Settings](#configure-openai-settings)
     - [Configure Azure AI Search Settings](#configure-azure-ai-search-settings)
 

2. **[準備資料](#prepare-data)** 把文件做 embedding 並收集額外 metadata，準備好上傳。這裡用 OpenAI 文件的一小部分當範例資料。
 
3. **[建立 Azure AI Vector Search](#create-azure-ai-vector-search)** 建立 Azure AI Vector Search 並上傳準備好的資料。包含：
     - [Create Index](#create-index)：在 Azure AI Search 建立 index 的步驟。
     - [Upload Data](#upload-data)：上傳資料到 Azure AI Search 的說明。
     - [Test Search](#test-search)：測試搜尋功能的步驟。
 
4. **[建立 Azure Function](#create-azure-function)** 建立跟 Azure AI Vector Search 互動的 Azure Function。包含：
     - [Create Storage Account](#create-storage-account)：為 Azure Function 建立 storage account 的步驟。
     - [Create Function App](#create-function-app)：在 Azure 建立 function app 的說明。
 
5. **[接進 ChatGPT 的 Custom GPT](#input-in-a-custom-gpt-in-chatgpt)** 把 Azure Function 整合到 ChatGPT 的 Custom GPT。包含：
     - [Create OpenAPI Spec](#create-openapi-spec)：為 Azure Function 建立 OpenAPI 規格的步驟。
     - [Create GPT Instructions](#create-gpt-instructions)：為這個整合建立 GPT 專用 instructions 的說明。




# 環境設定
先 import 需要的函式庫並設定 Azure 相關設定，環境就準備好了。

## 安裝並 import 需要的函式庫
為了好讀，我們把函式庫分成標準 Python 函式庫、第三方函式庫和 Azure 相關函式庫。

```python
! pip install -q wget
! pip install -q azure-search-documents 
! pip install -q azure-identity
! pip install -q openai
! pip install -q azure-mgmt-search
! pip install -q pandas
! pip install -q azure-mgmt-resource 
! pip install -q azure-mgmt-storage
! pip install -q pyperclip
! pip install -q PyPDF2
! pip install -q tiktoken
```

```python
# Standard Libraries
import json  
import os
import platform
import subprocess
import csv
from itertools import islice
import uuid
import shutil
import concurrent.futures

# Third-Party Libraries
import pandas as pd
from PyPDF2 import PdfReader
import tiktoken
from dotenv import load_dotenv
import pyperclip

# OpenAI Libraries (note we use OpenAI directly here, but you can replace with Azure OpenAI as needed)
from openai import OpenAI

# Azure Identity and Credentials
from azure.identity import DefaultAzureCredential, InteractiveBrowserCredential
from azure.core.credentials import AzureKeyCredential  
from azure.core.exceptions import HttpResponseError

# Azure Search Documents
from azure.search.documents import SearchClient, SearchIndexingBufferedSender  
from azure.search.documents.indexes import SearchIndexClient  
from azure.search.documents.models import (
    VectorizedQuery
)
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    HnswParameters,
    SearchField,
    SearchableField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
    VectorSearch,
    VectorSearchAlgorithmKind,
    VectorSearchAlgorithmMetric,
    VectorSearchProfile,
)

# Azure Management Clients
from azure.mgmt.search import SearchManagementClient
from azure.mgmt.resource import ResourceManagementClient, SubscriptionClient
from azure.mgmt.storage import StorageManagementClient
```

## 設定 OpenAI
進行這一節前，先確認你有 OpenAI API key。


```python
openai_api_key = os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as an env var>") # Saving this as a variable to reference in function app in later step
openai_client = OpenAI(api_key=openai_api_key)
embeddings_model = "text-embedding-3-small" # We'll use this by default, but you can change to your text-embedding-3-large if desired
```

## 設定 Azure AI Search
你可以在 Azure Portal 找到 Azure AI Search 服務的資訊，或用 [Search Management SDK](https://learn.microsoft.com/rest/api/searchmanagement/) 用程式取得。


#### 前置需求：
- Azure 的 Subscription ID
- Azure 的 Resource Group 名稱
- Azure 的 Region

```python
# Update the below with your values
subscription_id="<enter_your_subscription_id>"
resource_group="<enter_your_resource_group>"

## Make sure to choose a region that supports the proper products. We've defaulted to "eastus" below. https://azure.microsoft.com/en-us/explore/global-infrastructure/products-by-region/#products-by-region_tab5
region = "eastus"
credential = InteractiveBrowserCredential()
subscription_client = SubscriptionClient(credential)
subscription = next(subscription_client.subscriptions.list())
```

#### 建立並設定 Azure AI Search Service
下面會產生一個唯一的 search service 名稱、設定服務屬性，然後建立 search service。

```python
# Initialize the SearchManagementClient with the provided credentials and subscription ID
search_management_client = SearchManagementClient(
    credential=credential,
    subscription_id=subscription_id,
)

# Generate a unique name for the search service using UUID, but you can change this if you'd like.
generated_uuid = str(uuid.uuid4())
search_service_name = "search-service-gpt-demo" + generated_uuid
## The below is the default endpoint structure that is created when you create a search service. This may differ based on your Azure settings.
search_service_endpoint = 'https://'+search_service_name+'.search.windows.net'

# Create or update the search service with the specified parameters
response = search_management_client.services.begin_create_or_update(
    resource_group_name=resource_group,
    search_service_name=search_service_name,
    service={
        "location": region,
        "properties": {"hostingMode": "default", "partitionCount": 1, "replicaCount": 1},
        # We are using the free pricing tier for this demo. You are only allowed one free search service per subscription.
        "sku": {"name": "free"},
        "tags": {"app-name": "Search service demo"},
    },
).result()

# Convert the response to a dictionary and then to a pretty-printed JSON string
response_dict = response.as_dict()
response_json = json.dumps(response_dict, indent=4)

print(response_json)
print("Search Service Name:" + search_service_name)
print("Search Service Endpoint:" + search_service_endpoint)
```

#### 取得 Search Service API Key
Search service 跑起來之後，需要 [Search Service API Key](https://learn.microsoft.com/en-us/azure/search/search-security-api-keys?tabs=rest-use,portal-find,portal-query)，用它來建立 index，之後也用它執行搜尋。

```python
# Retrieve the admin keys for the search service
try:
    response = search_management_client.admin_keys.get(
        resource_group_name=resource_group,
        search_service_name=search_service_name,
    )
    # Extract the primary API key from the response and save as a variable to be used later
    search_service_api_key = response.primary_key
    print("Successfully retrieved the API key.")
except Exception as e:
    print(f"Failed to retrieve the API key: {e}")
```

# 準備資料
我們要把 oai_docs 資料夾裡幾頁 OpenAI 文件做 embedding 並存起來。先對每一份做 embedding、加進 CSV，再用這個 CSV 上傳到 index。

為了處理超過 8191 tokens context 的長文字檔，可以分別使用各 chunk 的 embedding，或用某種方式合併，例如平均（依各 chunk 大小加權）。

我們從 Python 自己的 cookbook 拿一個把序列切成 chunk 的 function。

```python
def batched(iterable, n):
    """Batch data into tuples of length n. The last batch may be shorter."""
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while (batch := tuple(islice(it, n))):
        yield batch
```

接著定義一個 function，把字串編碼成 token，再切成 chunk。我們用 tiktoken，這是 OpenAI 開源的快速 tokenizer。

想了解更多用 Tiktoken 計算 token 的方法，看[這篇 cookbook](https://cookbook.openai.com/examples/how_to_count_tokens_with_tiktoken)。



```python
def chunked_tokens(text, chunk_length, encoding_name='cl100k_base'):
    # Get the encoding object for the specified encoding name. OpenAI's tiktoken library, which is used in this notebook, currently supports two encodings: 'bpe' and 'cl100k_base'. The 'bpe' encoding is used for GPT-3 and earlier models, while 'cl100k_base' is used for newer models like GPT-4.
    encoding = tiktoken.get_encoding(encoding_name)
    # Encode the input text into tokens
    tokens = encoding.encode(text)
    # Create an iterator that yields chunks of tokens of the specified length
    chunks_iterator = batched(tokens, chunk_length)
    # Yield each chunk from the iterator
    yield from chunks_iterator
```

最後寫一個能安全處理 embedding 請求的 function，即使輸入文字超過最大 context 長度也沒問題，做法是把輸入 token 切 chunk，每個 chunk 各自做 embedding。average 旗標設成 True 會回傳各 chunk embedding 的加權平均，設成 False 則直接回傳原封不動的 chunk embedding 清單。

> 注意：這裡還有其他更進階的做法，包括：
> - 用 GPT-4o 擷取圖片 / 圖表描述來做 embedding。
> - chunk 之間保留重疊文字，減少重要 context 被截斷。
> - 依段落或章節切 chunk。
> - 為每篇文章加更多描述性 metadata。

```python
## Change the below based on model. The below is for the latest embeddings models from OpenAI, so you can leave as is unless you are using a different embedding model..
EMBEDDING_CTX_LENGTH = 8191
EMBEDDING_ENCODING='cl100k_base'
```

```python
def generate_embeddings(text, model):
    # Generate embeddings for the provided text using the specified model
    embeddings_response = openai_client.embeddings.create(model=model, input=text)
    # Extract the embedding data from the response
    embedding = embeddings_response.data[0].embedding
    return embedding

def len_safe_get_embedding(text, model=embeddings_model, max_tokens=EMBEDDING_CTX_LENGTH, encoding_name=EMBEDDING_ENCODING):
    # Initialize lists to store embeddings and corresponding text chunks
    chunk_embeddings = []
    chunk_texts = []
    # Iterate over chunks of tokens from the input text
    for chunk in chunked_tokens(text, chunk_length=max_tokens, encoding_name=encoding_name):
        # Generate embeddings for each chunk and append to the list
        chunk_embeddings.append(generate_embeddings(chunk, model=model))
        # Decode the chunk back to text and append to the list
        chunk_texts.append(tiktoken.get_encoding(encoding_name).decode(chunk))
    # Return the list of chunk embeddings and the corresponding text chunks
    return chunk_embeddings, chunk_texts
```

接著定義一個 helper function 來收集文件的額外 metadata。這可以拿來當搜尋 query 的 metadata filter，也能為搜尋保留更豐富的資料。

在這個範例，我從一份類別清單中挑選，之後用在 metadata filter。

```python
## These are the categories I will be using for the categorization task. You can change these as needed based on your use case.
categories = ['authentication','models','techniques','tools','setup','billing_limits','other']

def categorize_text(text, categories):
    # Create a prompt for categorization
    messages = [
        {"role": "system", "content": f"""You are an expert in LLMs, and you will be given text that corresponds to an article in OpenAI's documentation.
         Categorize the document into one of these categories: {', '.join(categories)}. Only respond with the category name and nothing else."""},
        {"role": "user", "content": text}
    ]
    try:
        # Call the OpenAI API to categorize the text
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages
        )
        # Extract the category from the response
        category = response.choices[0].message.content
        return category
    except Exception as e:
        print(f"Error categorizing text: {str(e)}")
        return None
```

現在定義幾個 helper function，處理 data 資料夾內 oai_docs 資料夾裡的 .txt 檔。你也可以拿自己的資料來用，支援 .txt 和 .pdf 檔。

```python
def extract_text_from_pdf(pdf_path):
    # Initialize the PDF reader
    reader = PdfReader(pdf_path)
    text = ""
    # Iterate through each page in the PDF and extract text
    for page in reader.pages:
        text += page.extract_text()
    return text

def process_file(file_path, idx, categories, embeddings_model):
    file_name = os.path.basename(file_path)
    print(f"Processing file {idx + 1}: {file_name}")
    
    # Read text content from .txt files
    if file_name.endswith('.txt'):
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
    # Extract text content from .pdf files
    elif file_name.endswith('.pdf'):
        text = extract_text_from_pdf(file_path)
    
    title = file_name
    # Generate embeddings for the title
    title_vectors, title_text = len_safe_get_embedding(title, embeddings_model)
    print(f"Generated title embeddings for {file_name}")
    
    # Generate embeddings for the content
    content_vectors, content_text = len_safe_get_embedding(text, embeddings_model)
    print(f"Generated content embeddings for {file_name}")
    
    category = categorize_text(' '.join(content_text), categories)
    print(f"Categorized {file_name} as {category}")
    
    # Prepare the data to be appended
    data = []
    for i, content_vector in enumerate(content_vectors):
        data.append({
            "id": f"{idx}_{i}",
            "vector_id": f"{idx}_{i}",
            "title": title_text[0],
            "text": content_text[i],
            "title_vector": json.dumps(title_vectors[0]),  # Assuming title is short and has only one chunk
            "content_vector": json.dumps(content_vector),
            "category": category
        })
        print(f"Appended data for chunk {i + 1}/{len(content_vectors)} of {file_name}")
    
    return data
```

現在用這個 helper function 處理 OpenAI 文件。想用自己的資料，改下面 `process_files` 的資料夾就行。

注意這會並行處理選定資料夾裡的文件，所以 txt 檔應該不到 30 秒，PDF 會稍久一點。

```python
## Customize the location below if you are using different data besides the OpenAI documentation. Note that if you are using a different dataset, you will need to update the categories list as well.
folder_name = "../../../data/oai_docs"

files = [os.path.join(folder_name, f) for f in os.listdir(folder_name) if f.endswith('.txt') or f.endswith('.pdf')]
data = []

# Process each file concurrently
with concurrent.futures.ThreadPoolExecutor() as executor:
    futures = {executor.submit(process_file, file_path, idx, categories, embeddings_model): idx for idx, file_path in enumerate(files)}
    for future in concurrent.futures.as_completed(futures):
        try:
            result = future.result()
            data.extend(result)
        except Exception as e:
            print(f"Error processing file: {str(e)}")

# Write the data to a CSV file
csv_file = os.path.join("..", "embedded_data.csv")
with open(csv_file, 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ["id", "vector_id", "title", "text", "title_vector", "content_vector","category"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow(row)
        print(f"Wrote row with id {row['id']} to CSV")

# Convert the CSV file to a Dataframe
article_df = pd.read_csv("../embedded_data.csv")
# Read vectors from strings back into a list using json.loads
article_df["title_vector"] = article_df.title_vector.apply(json.loads)
article_df["content_vector"] = article_df.content_vector.apply(json.loads)
article_df["vector_id"] = article_df["vector_id"].apply(str)
article_df["category"] = article_df["category"].apply(str)
article_df.head()
```

現在有一個 `embedded_data.csv` 檔，有六個欄位，可以上傳到我們的 vector database 了！

# 建立 Azure AI Vector Search

##  建立 index
我們用 Azure AI Search Python SDK 的 `SearchIndexClient` 定義並建立 search index。這個 index 同時支援 vector search 和 hybrid search。細節請看 Microsoft 文件的[建立 Vector Index](https://learn.microsoft.com/azure/search/vector-search-how-to-create-index?.tabs=config-2023-11-01%2Crest-2023-11-01%2Cpush%2Cportal-check-index)

```python
index_name = "azure-ai-search-openai-cookbook-demo"
# index_name = "<insert_name_for_index>"

index_client = SearchIndexClient(
    endpoint=search_service_endpoint, credential=AzureKeyCredential(search_service_api_key)
)
# Define the fields for the index. Update these based on your data.
# Each field represents a column in the search index
fields = [
    SimpleField(name="id", type=SearchFieldDataType.String),  # Simple string field for document ID
    SimpleField(name="vector_id", type=SearchFieldDataType.String, key=True),  # Key field for the index
    # SimpleField(name="url", type=SearchFieldDataType.String),  # URL field (commented out)
    SearchableField(name="title", type=SearchFieldDataType.String),  # Searchable field for document title
    SearchableField(name="text", type=SearchFieldDataType.String),  # Searchable field for document text
    SearchField(
        name="title_vector",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),  # Collection of single values for title vector
        vector_search_dimensions=1536,  # Number of dimensions in the vector
        vector_search_profile_name="my-vector-config",  # Profile name for vector search configuration
    ),
    SearchField(
        name="content_vector",
        type=SearchFieldDataType.Collection(SearchFieldDataType.Single),  # Collection of single values for content vector
        vector_search_dimensions=1536,  # Number of dimensions in the vector
        vector_search_profile_name="my-vector-config",  # Profile name for vector search configuration
    ),
    SearchableField(name="category", type=SearchFieldDataType.String, filterable=True),  # Searchable field for document category
]

# This configuration defines the algorithm and parameters for vector search
vector_search = VectorSearch(
    algorithms=[
        HnswAlgorithmConfiguration(
            name="my-hnsw",  # Name of the HNSW algorithm configuration
            kind=VectorSearchAlgorithmKind.HNSW,  # Type of algorithm
            parameters=HnswParameters(
                m=4,  # Number of bi-directional links created for every new element
                ef_construction=400,  # Size of the dynamic list for the nearest neighbors during construction
                ef_search=500,  # Size of the dynamic list for the nearest neighbors during search
                metric=VectorSearchAlgorithmMetric.COSINE,  # Distance metric used for the search
            ),
        )
    ],
    profiles=[
        VectorSearchProfile(
            name="my-vector-config",  # Name of the vector search profile
            algorithm_configuration_name="my-hnsw",  # Reference to the algorithm configuration
        )
    ],
)

# Create the search index with the vector search configuration
# This combines all the configurations into a single search index
index = SearchIndex(
    name=index_name,  # Name of the index
    fields=fields,  # Fields defined for the index
    vector_search=vector_search  # Vector search configuration

)

# Create or update the index
# This sends the index definition to the Azure Search service
result = index_client.create_index(index)
print(f"{result.name} created")  # Output the name of the created index
```

## 上傳資料

現在把前面存在 `embedded_data.csv` 的文章，從 pandas DataFrame 上傳到 Azure AI Search index。資料匯入策略和最佳實務的詳細指南，請看 [Data Import in Azure AI Search](https://learn.microsoft.com/azure/search/search-what-is-data-import)。


```python
# Convert the 'id' and 'vector_id' columns to string so one of them can serve as our key field
article_df["id"] = article_df["id"].astype(str)
article_df["vector_id"] = article_df["vector_id"].astype(str)

# Convert the DataFrame to a list of dictionaries
documents = article_df.to_dict(orient="records")

# Log the number of documents to be uploaded
print(f"Number of documents to upload: {len(documents)}")

# Create a SearchIndexingBufferedSender
batch_client = SearchIndexingBufferedSender(
    search_service_endpoint, index_name, AzureKeyCredential(search_service_api_key)
)
# Get the first document to check its schema
first_document = documents[0]

# Get the index schema
index_schema = index_client.get_index(index_name)

# Get the field names from the index schema
index_fields = {field.name: field.type for field in index_schema.fields}

# Check each field in the first document
for field, value in first_document.items():
    if field not in index_fields:
        print(f"Field '{field}' is not in the index schema.")

# Check for any fields in the index schema that are not in the documents
for field in index_fields:
    if field not in first_document:
        print(f"Field '{field}' is in the index schema but not in the documents.")

try:
    if documents:
        # Add upload actions for all documents in a single call
        upload_result = batch_client.upload_documents(documents=documents)

        # Check if the upload was successful
        # Manually flush to send any remaining documents in the buffer
        batch_client.flush()
        
        print(f"Uploaded {len(documents)} documents in total")
    else:
        print("No documents to upload.")
except HttpResponseError as e:
    print(f"An error occurred: {e}")
    raise  # Re-raise the exception to ensure it errors out
finally:
    # Clean up resources
    batch_client.close()
```

## 測試搜尋
資料上傳完後，下面在本機測試 vector 相似度搜尋和 hybrid search，確認運作正常。

兩種都可以測：純 vector search 是把 `None` 傳給下面的 `search_text`，只用 vector 相似度搜尋。Hybrid search 則把 query 文字 `query` 傳給 `search_text`，把傳統關鍵字搜尋跟 vector 相似度搜尋結合，給出更相關、更貼合 context 的結果。

```python
query = "What model should I use to embed?"
# Note: we'll have the GPT choose the category automatically once we put it in ChatGPT
category ="models"

search_client = SearchClient(search_service_endpoint, index_name, AzureKeyCredential(search_service_api_key))
vector_query = VectorizedQuery(vector=generate_embeddings(query, embeddings_model), k_nearest_neighbors=3, fields="content_vector")
  
results = search_client.search(  
    search_text=None, # Pass in None if you want to use pure vector search, and `query` if you want to use hybrid search
    vector_queries= [vector_query], 
    select=["title", "text"],
    filter=f"category eq '{category}'" 
)

for result in results:  
    print(result)
```

## 建立 Azure Function

Azure Functions 是在我們新做的 AI 搜尋上建立 API 的簡單方法。程式碼（見這個資料夾的 `function_app.py`，或[這個連結](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/rag-quickstart/azure/function_app.py)）做的事如下：

1. 接收輸入：使用者的 query、search index endpoint、index 名稱、k_nearest_neighbors*、要用的搜尋欄位（content_vector 或 title_vector），以及是否使用 hybrid query
2. 把使用者的 query 做 embedding。
3. 執行 vector search，取回相關文字 chunk。
4. 把這些相關文字 chunk 當回應 body 回傳。

*在 vector search 裡，k_nearest_neighbors 指定搜尋要回傳多少個「最近」的 vector（以 cosine similarity 計算）。例如 k_nearest_neighbors 設成 3，搜尋會回傳 index 裡跟 query vector 最相似的 3 個 vector。

> 注意這個 Azure Function _沒有任何驗證_。不過你可以照[這裡](https://learn.microsoft.com/en-us/azure/azure-functions/security-concepts?tabs=v4)的文件幫它加上驗證。

### 建立 storage account

可以用下面的程式碼建立新的 storage account，也可以跳過這個區塊，把後面的步驟改成用現有的 storage account。可能要花到 30 秒。

```python
## Update below with a different name
storage_account_name = "<enter-storage-account-name>"

## Use below SKU or any other SKU as per your requirement
sku = "Standard_LRS"
resource_client = ResourceManagementClient(credential, subscription_id)
storage_client = StorageManagementClient(credential, subscription_id)

# Create resource group if it doesn't exist
rg_result = resource_client.resource_groups.create_or_update(resource_group, {"location": region})

# Create storage account
storage_async_operation = storage_client.storage_accounts.begin_create(
    resource_group,
    storage_account_name,
    {
        "sku": {"name": sku},
        "kind": "StorageV2",
        "location": region,
    },
)
storage_account = storage_async_operation.result()

print(f"Storage account {storage_account.name} created")
```

### 建立 Function App
這個 Function App 就是 Python 程式碼被 GPT Action 觸發後執行的地方。想多了解 Function App，看[這裡](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview?pivots=programming-language-csharp)的文件。

要部署 Function App，需要用 Azure CLI 和 Azure Functions Core Tools。

> 下面的程式會依你的平台類型，嘗試在 virtual environment 裡安裝並執行。如果不成功，請看 Azure 文件安裝 [Azure Function Core Tools](https://learn.microsoft.com/en-us/azure/azure-functions/create-first-function-cli-python?tabs=linux,bash,azure-cli,browser) 和 [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)。裝好後，切到這個資料夾，在 terminal 執行下面的 `subprocess.run` 指令。

先確認環境裡有執行 Azure 指令需要的工具。安裝可能要幾分鐘。

```python
os_type = platform.system()

if os_type == "Windows":
    # Install Azure Functions Core Tools on Windows
    subprocess.run(["npm", "install", "-g", "azure-functions-core-tools@3", "--unsafe-perm", "true"], check=True)
    # Install Azure CLI on Windows
    subprocess.run(["powershell", "-Command", "Invoke-WebRequest -Uri https://aka.ms/installazurecliwindows -OutFile .\\AzureCLI.msi; Start-Process msiexec.exe -ArgumentList '/I AzureCLI.msi /quiet' -Wait"], check=True)
elif os_type == "Darwin":  # MacOS
    # Install Azure Functions Core Tools on MacOS
    if platform.machine() == 'arm64':
        # For M1 Macs
        subprocess.run(["arch", "-arm64", "brew", "install", "azure-functions-core-tools@3"], check=True)
    else:
        # For Intel Macs
        subprocess.run(["brew", "install", "azure-functions-core-tools@3"], check=True)
    # Install Azure CLI on MacOS
    subprocess.run(["brew", "update"], check=True)
    subprocess.run(["brew", "install", "azure-cli"], check=True)
elif os_type == "Linux":
    # Install Azure Functions Core Tools on Linux
    subprocess.run(["curl", "https://packages.microsoft.com/keys/microsoft.asc", "|", "gpg", "--dearmor", ">", "microsoft.gpg"], check=True, shell=True)
    subprocess.run(["sudo", "mv", "microsoft.gpg", "/etc/apt/trusted.gpg.d/microsoft.gpg"], check=True)
    subprocess.run(["sudo", "sh", "-c", "'echo \"deb [arch=amd64] https://packages.microsoft.com/repos/microsoft-ubuntu-$(lsb_release -cs)-prod $(lsb_release -cs) main\" > /etc/apt/sources.list.d/dotnetdev.list'"], check=True, shell=True)
    subprocess.run(["sudo", "apt-get", "update"], check=True)
    subprocess.run(["sudo", "apt-get", "install", "azure-functions-core-tools-3"], check=True)
    # Install Azure CLI on Linux
    subprocess.run(["curl", "-sL", "https://aka.ms/InstallAzureCLIDeb", "|", "sudo", "bash"], check=True, shell=True)
else:
    # Raise an error if the operating system is not supported
    raise OSError("Unsupported operating system")

# Verify the installation of Azure Functions Core Tools
subprocess.run(["func", "--version"], check=True)
# Verify the installation of Azure CLI
subprocess.run(["az", "--version"], check=True)

subprocess.run([
    "az", "login"
], check=True)
```

接著要建立一個 `local.settings.json`，放 Azure 的關鍵環境變數

```python
local_settings_content = f"""
{{
  "IsEncrypted": false,
  "Values": {{
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "OPENAI_API_KEY": "{openai_api_key}",
    "EMBEDDINGS_MODEL": "{embeddings_model}",
    "SEARCH_SERVICE_API_KEY": "{search_service_api_key}",
  }}
}}
"""

with open("local.settings.json", "w") as file:
    file.write(local_settings_content)
```

檢查 `local.settings.json`，確認環境變數跟你預期的一致。

現在幫你的 app 取個名字，就可以建立 Function App 並發佈 function 了。

```python
# Replace this with your own values. This name will appear in the URL of the API call https://<app_name>.azurewebsites.net
app_name = "<app-name>"

subprocess.run([
    "az", "functionapp", "create",
    "--resource-group", resource_group,
    "--consumption-plan-location", region,
    "--runtime", "python",
    "--name", app_name,
    "--storage-account", storage_account_name,
    "--os-type", "Linux",
], check=True)
```

Function App 建好後，要把設定變數加進去給 function 用。具體來說需要 `OPENAI_API_KEY`、`SEARCH_SERVICE_API_KEY` 和 `EMBEDDINGS_MODEL`，因為 `function_app.py` 程式碼都會用到。

```python
# Collect the relevant environment variables 
env_vars = {
    "OPENAI_API_KEY": openai_api_key,
    "SEARCH_SERVICE_API_KEY": search_service_api_key,
    "EMBEDDINGS_MODEL": embeddings_model
}

# Create the settings argument for the az functionapp create command
settings_args = []
for key, value in env_vars.items():
    settings_args.append(f"{key}={value}")

subprocess.run([
    "az", "functionapp", "config", "appsettings", "set",
    "--name", app_name,
    "--resource-group", resource_group,
    "--settings", *settings_args
], check=True)
```

現在可以把 function 程式碼 `function_app.py` 發佈到 Azure Function 了。部署可能要花到 10 分鐘。完成後，我們就有一個建在 Azure AI Search 之上、由 Azure Function 提供的 API endpoint。

```python
subprocess.run([
    "func", "azure", "functionapp", "publish", app_name
], check=True)
```

## 接進 ChatGPT 的 Custom GPT
現在有了查詢這個 Vector Search Index 的 Azure Function，把它做成 GPT Action 吧！

GPT 的說明看[這裡](https://openai.com/index/introducing-gpts/)，GPT Actions 的說明看[這裡](https://platform.openai.com/docs/actions)。下面的內容分別用作 GPT 的 instructions 和 GPT Action 的 OpenAPI spec。


### 建立 OpenAPI Spec
下面是一份範例 OpenAPI spec。執行下面的區塊後，一份可用的 spec 會被複製到剪貼簿，可以貼到 GPT Action。

注意預設沒有任何驗證，不過你可以照[這篇 cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function#part-2-set-up-auth) Authentication 那段的做法，或看[這裡](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization)的文件，幫 Azure Functions 設定 OAuth。

```python

spec = f"""
openapi: 3.1.0
info:
  title: Vector Similarity Search API
  description: API for performing vector similarity search.
  version: 1.0.0
servers:
  - url: https://{app_name}.azurewebsites.net/api
    description: Main (production) server
paths:
  /vector_similarity_search:
    post:
      operationId: vectorSimilaritySearch
      summary: Perform a vector similarity search.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                search_service_endpoint:
                  type: string
                  description: The endpoint of the search service.
                index_name:
                  type: string
                  description: The name of the search index.
                query:
                  type: string
                  description: The search query.
                k_nearest_neighbors:
                  type: integer
                  description: The number of nearest neighbors to return.
                search_column:
                  type: string
                  description: The name of the search column.
                use_hybrid_query:
                  type: boolean
                  description: Whether to use a hybrid query.
                category:
                  type: string
                  description: category to filter.
              required:
                - search_service_endpoint
                - index_name
                - query
                - k_nearest_neighbors
                - search_column
                - use_hybrid_query
      responses:
        '200':
          description: A successful response with the search results.
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                          description: The identifier of the result item.
                        score:
                          type: number
                          description: The similarity score of the result item.
                        content:
                          type: object
                          description: The content of the result item.
        '400':
          description: Bad request due to missing or invalid parameters.
        '500':
          description: Internal server error.
"""
pyperclip.copy(spec)
print("OpenAPI spec copied to clipboard")
print(spec)
```

### 建立 GPT Instructions

instructions 可以隨你需要修改。prompt engineering 的技巧看我們[這裡](https://platform.openai.com/docs/guides/prompt-engineering)的文件。

```python
instructions = f'''
You are an OAI docs assistant. You have an action in your knowledge base where you can make a POST request to search for information. The POST request should always include: {{
    "search_service_endpoint": "{search_service_endpoint}",
    "index_name": {index_name},
    "query": "<user_query>",
    "k_nearest_neighbors": 1,
    "search_column": "content_vector",
    "use_hybrid_query": true,
    "category": "<category>"
}}. Only the query and category change based on the user's request. Your goal is to assist users by performing searches using this POST request and providing them with relevant information based on the query.

You must only include knowledge you get from your action in your response.
The category must be from the following list: {categories}, which you should determine based on the user's query. If you cannot determine, then do not include the category in the POST request.
'''
pyperclip.copy(instructions)
print("GPT Instructions copied to clipboard")
print(instructions)
```

現在我們有一個會查詢 vector database 的 GPT 了！

# 回顧
我們成功把 Azure AI Search 整合到 ChatGPT 的 GPT Actions，做法如下：
1. 用 OpenAI embedding 對文件做 embedding，並用 gpt-4o 加上一些額外 metadata。
2. 把資料上傳到 Azure AI Search。
3. 用 Azure Functions 建一個 endpoint 來查詢。
4. 把它整合進 Custom GPT。

我們的 GPT 現在能檢索資訊來回答使用者的問題，答案更準，也更貼合我們的資料。下面是這個 GPT 實際運作的樣子：

# ![azure-rag-quickstart-gpt.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/azure-rag-quickstart-gpt.png)


## 重點整理

- 這個架構是「vector store + serverless function + GPT Action」，換成 Postgres 等其他 vector store 時，只需要改建 index 和 `function_app.py` 的查詢部分。
- 超過 8191 tokens 的長文字要切 chunk 分別 embedding，再視需要用加權平均合併。
- Index 同時支援純 vector search 和 hybrid search（關鍵字加 vector 相似度），hybrid 通常結果更貼合 context。
- Function 做的事很單純：把 query 做 embedding、搜出前 k 個相近的 chunk、回傳文字，其餘交給 GPT 回答。
- 範例的 Azure Function 預設沒有驗證，正式使用前要自己加上（例如 OAuth）。

## 練習

1. 在 Test Search 那段，把 hybrid search 和純 vector search（`search_text` 傳 `None`）用同一個 query 各跑一次，比較回傳結果的差別。
2. 調整 k_nearest_neighbors（例如從 3 改成 5），或把搜尋欄位在 content_vector 和 title_vector 之間切換，看結果怎麼變。
3. 修改 metadata 那段 helper function 的類別清單，換成你自己的資料夾和分類，重新產生 `embedded_data.csv` 並上傳，再把 GPT instructions 改成會依分類查詢。
