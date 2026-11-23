---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/azure/embeddings.ipynb
---

# Azure embeddings 範例

> 原文：[examples/azure/embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/azure/embeddings.ipynb)



## 這篇在做什麼

示範用 Azure OpenAI 服務產生 embedding：設定認證、建立模型 deployment，再用建好的 client 取得 embedding。

## 學完你會

- 用 API key 或 Azure Active Directory 兩種方式設定 `AzureOpenAI` client
- 知道 `AzureOpenAI` 會從哪些環境變數推得參數
- 在 Azure OpenAI Studio 建立 embedding 模型的 deployment，並用 deployment 名稱產生 embedding

## 開跑前

- 一個 Azure OpenAI 資源（Azure Portal 可取得 key 和 endpoint）
- 用 Azure AD 認證的話，要安裝 `azure-identity`

這個範例會介紹如何用 Azure OpenAI 服務做 embedding。

## 設定

首先安裝需要的相依套件，並匯入我們會用到的函式庫。

```python
! pip install "openai>=1.0.0,<2.0.0"
! pip install python-dotenv
```

```python
import os
import openai
import dotenv

dotenv.load_dotenv()
```

### 認證

Azure OpenAI 服務支援多種認證機制，包括 API key 和 Azure Active Directory token credential。

```python
use_azure_active_directory = False  # Set this flag to True if you are using Azure Active Directory
```

#### 用 API key 認證

要讓 OpenAI SDK 使用 *Azure API Key*，需要把 `api_key` 設成跟你的 endpoint 相關聯的 key（可以在 [Azure Portal](https://portal.azure.com) 的 *"Resource Management"* 底下的 *"Keys and Endpoints"* 找到）。你也會在這裡看到資源的 endpoint。

```python
if not use_azure_active_directory:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]

    client = openai.AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version="2023-09-01-preview"
    )
```

#### 用 Azure Active Directory 認證
接著看看怎麼用 Azure Active Directory 認證。先安裝 `azure-identity` 函式庫。這個函式庫會提供認證需要的 token credential，並透過 `get_bearer_token_provider` helper 函式幫我們建立 token credential provider。建議用 `get_bearer_token_provider`，不要給 `AzureOpenAI` 一個固定的 token，因為這個 API 會自動快取並更新 token。

想知道如何為 Azure OpenAI 設定 Azure Active Directory 認證，請看[文件](https://learn.microsoft.com/azure/ai-services/openai/how-to/managed-identity)。

```python
! pip install "azure-identity>=1.15.0"
```

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

if use_azure_active_directory:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]

    client = openai.AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"),
        api_version="2023-09-01-preview"
    )
```

> 注意：如果沒有提供下列參數，AzureOpenAI 會從對應的環境變數推得：

- `api_key` 來自 `AZURE_OPENAI_API_KEY`
- `azure_ad_token` 來自 `AZURE_OPENAI_AD_TOKEN`
- `api_version` 來自 `OPENAI_API_VERSION`
- `azure_endpoint` 來自 `AZURE_OPENAI_ENDPOINT`


## Deployment

這一節要建立一個模型的 deployment，用它來產生 embedding。

### Deployment：在 Azure OpenAI Studio 建立
來部署一個做 embedding 用的模型。到 https://portal.azure.com，找到你的 Azure OpenAI 資源，然後進入 Azure OpenAI Studio。點 "Deployments" 分頁，替你想用來做 embedding 的模型建立 deployment。你給模型取的 deployment 名稱，會用在下面的程式裡。

```python
deployment = "" # Fill in the deployment name from the portal here
```

## Embeddings

現在用我們建好的 client 來產生 embedding。

```python
embeddings = client.embeddings.create(
    model=deployment,
    input="The food was delicious and the waiter..."
)
                                
print(embeddings)
```

## 重點整理

- Azure 版跟 OpenAI 版的差別主要在 client 的建立與認證，產生 embedding 的呼叫方式很像。
- Azure 的 `model` 參數填的是你自己取的 deployment 名稱，不是模型名稱。
- 用 Azure AD 認證時，`get_bearer_token_provider` 會自動快取和更新 token，比塞固定 token 好。
- `api_key`、`api_version`、`azure_endpoint` 等都能靠環境變數帶入，程式裡就不用寫死。

## 練習

1. 把 API key 認證的寫法改成只靠環境變數，client 建立時不傳參數。
2. 用另一個 deployment 名稱，或新建一個不同的 embedding 模型 deployment，比較輸出向量的長度。
3. 一次傳入多段文字，檢查回傳的 embedding 數量和順序。
