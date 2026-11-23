---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/azure/chat_with_your_own_data.ipynb
---
# 用你自己的資料跑 Azure Chat Completion 模型（preview）

> 原文：[examples/azure/chat_with_your_own_data.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/azure/chat_with_your_own_data.ipynb)



## 這篇在做什麼

示範怎麼用 Azure OpenAI 的「on your data」功能，讓 GPT-3.5-Turbo、GPT-4 這類 chat 模型直接根據你自己的文件回答問題，不用訓練也不用 fine-tuning。這個功能目前還是 preview。

做法是 Azure AI Search 先依使用者的問題和對話歷史去索引裡撈資料，再把撈到的內容補進 prompt 丟給模型。回答因此有根據，不會只靠模型訓練時學到的舊知識。

## 學完你會

- 設定 `AzureOpenAI` client，用 API key 或 Azure Active Directory 兩種方式驗證
- 在 Chat Completions 請求的 `dataSources` 帶入 Azure AI Search 的 endpoint、key 和 index，讓回答根據你的資料
- 從回應的 `context` 看模型引用了哪些資料，也能改用 `stream=True` 串流輸出

## 開跑前

要先在 Azure Portal 準備好這些資源：

- 已部署 chat 模型的 Azure OpenAI 資源
- Azure AI Search（舊名 Azure Cognitive Search）資源
- Azure Blob Storage 資源
- 要拿來當資料的文件，並已建好 index

這些都是付費的外部服務。上傳文件跟建 index 的步驟看這份 [Quickstart](https://learn.microsoft.com/azure/ai-services/openai/use-your-data-quickstart?pivots=programming-language-studio&tabs=command-line)。

## 運作方式

[Azure OpenAI on your own data](https://learn.microsoft.com/azure/ai-services/openai/concepts/use-your-data) 把模型跟你的資料接起來。搭配 Azure AI Search，系統會根據使用者輸入和對話歷史，從指定的資料來源撈資料，補進 prompt 再送給模型，模型就能用這些上下文來產生回答。

資料、隱私和安全相關的細節看 [Data, privacy, and security for Azure OpenAI Service](https://learn.microsoft.com/legal/cognitive-services/openai/data-privacy?context=%2Fazure%2Fai-services%2Fopenai%2Fcontext%2Fcontext)。

如果想看其他知識檢索或語意搜尋的做法，可以參考 cookbook 的 [vector databases](https://github.com/openai/openai-cookbook/tree/main/examples/vector_databases) 範例。

## 前置需求

要使用 Azure OpenAI Service，得先在 [Azure Portal](https://portal.azure.com) 建好對應的資源（詳細步驟看 [Microsoft Docs](https://learn.microsoft.com/azure/cognitive-services/openai/how-to/create-resource?pivots=web-portal)）。

要讓 Azure OpenAI 模型用你自己的資料，需要：

1. Azure OpenAI 的使用權限，以及一個已部署 chat 模型（例如 GPT-3 或 GPT-4）的資源
2. Azure AI Search（舊名 Azure Cognitive Search）資源
3. Azure Blob Storage 資源
4. 要當資料的文件（可用的來源見 [data source options](https://learn.microsoft.com/azure/ai-services/openai/concepts/use-your-data#data-source-options)）


從上傳文件到 blob storage，再到用 Azure AI Studio 建 index 的完整流程，請看這份 [Quickstart](https://learn.microsoft.com/azure/ai-services/openai/use-your-data-quickstart?pivots=programming-language-studio&tabs=command-line)。

## 環境設定

先安裝需要的套件。

```python
! pip install "openai>=1.0.0,<2.0.0"
! pip install python-dotenv
```

這個範例用 `dotenv` 載入環境變數。要連 Azure OpenAI 和 Search index，請在 `.env` 檔用 `KEY=VALUE` 的格式加上這些變數：

* `AZURE_OPENAI_ENDPOINT`：Azure OpenAI 的 endpoint。在 Azure Portal 你的 Azure OpenAI 資源底下的 "Keys and Endpoints" 可以找到。
* `AZURE_OPENAI_API_KEY`：Azure OpenAI 的 API key，位置同上。如果用 Azure Active Directory 驗證（見下方 `Authentication using Microsoft Active Directory`）就不用設。
* `SEARCH_ENDPOINT`：AI Search 的 endpoint。在 Azure Portal 的 Search 資源 "Overview" 頁可以找到這個 URL。
* `SEARCH_KEY`：AI Search 的 API key，在 Search 資源的 "Keys" 底下。
* `SEARCH_INDEX_NAME`：你用自己資料建好的 index 名稱。

```python
import os
import openai
import dotenv

dotenv.load_dotenv()
```

### 驗證（Authentication）

Azure OpenAI service 支援好幾種驗證方式，包含 API key 和 Azure Active Directory 的 token credentials。

```python
use_azure_active_directory = False  # Set this flag to True if you are using Azure Active Directory
```

#### 用 API key 驗證

要讓 OpenAI SDK 用 *Azure API Key*，把 `api_key` 設成你 endpoint 對應的 key（在 [Azure Portal](https://portal.azure.com) 的 *"Resource Management"* 底下 *"Keys and Endpoints"* 可以找到）。你的資源 endpoint 也在同一個地方。

```python
if not use_azure_active_directory:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    # set the deployment name for the model we want to use
    deployment = "<deployment-id-of-the-model-to-use>"

    client = openai.AzureOpenAI(
        base_url=f"{endpoint}/openai/deployments/{deployment}/extensions",
        api_key=api_key,
        api_version="2023-09-01-preview"
    )
```

#### 用 Azure Active Directory 驗證
接下來看怎麼用 Azure Active Directory 驗證。先裝 `azure-identity`，它提供驗證需要的 token credentials，再透過 `get_bearer_token_provider` 這個 helper 建出 token credential provider。建議用 `get_bearer_token_provider`，不要給 `AzureOpenAI` 一個固定的 token，因為它會自動快取並更新 token。

怎麼設定 Azure Active Directory 驗證，詳見[文件](https://learn.microsoft.com/azure/ai-services/openai/how-to/managed-identity)。

```python
! pip install "azure-identity>=1.15.0"
```

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

if use_azure_active_directory:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]
    api_key = os.environ["AZURE_OPENAI_API_KEY"]
    # set the deployment name for the model we want to use
    deployment = "<deployment-id-of-the-model-to-use>"

    client = openai.AzureOpenAI(
        base_url=f"{endpoint}/openai/deployments/{deployment}/extensions",
        azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"),
        api_version="2023-09-01-preview"
    )
```

> 注意：如果沒有明確提供，AzureOpenAI 會從對應的環境變數推得下列參數：

- `api_key` 來自 `AZURE_OPENAI_API_KEY`
- `azure_ad_token` 來自 `AZURE_OPENAI_AD_TOKEN`
- `api_version` 來自 `OPENAI_API_VERSION`
- `azure_endpoint` 來自 `AZURE_OPENAI_ENDPOINT`


## 用你自己的資料跑 Chat completion 模型

### 設定情境

這個範例要讓模型根據 Azure AI services 的文件資料來回答。照前面的 [Quickstart](https://learn.microsoft.com/azure/ai-services/openai/use-your-data-quickstart?tabs=command-line&pivots=programming-language-studio) 做，我們已經把 [Azure AI services and machine learning](https://learn.microsoft.com/azure/ai-services/cognitive-services-and-machine-learning) 這頁文件的 [markdown](https://github.com/MicrosoftDocs/azure-docs/blob/main/articles/ai-services/cognitive-services-and-machine-learning.md) 檔加進 search index。現在模型就可以回答 Azure AI services 和 machine learning 的問題了。

### 程式碼

現在可以用 Chat Completions 搭配你自己的資料。在 `dataSources` 裡給 search endpoint、key 和 index 名稱，之後問模型的問題都會根據你的資料回答。回應裡還會多一個 `context` 屬性，顯示模型回答時參考了哪些資料。

```python
completion = client.chat.completions.create(
    messages=[{"role": "user", "content": "What are the differences between Azure Machine Learning and Azure AI services?"}],
    model=deployment,
    extra_body={
        "dataSources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": os.environ["SEARCH_ENDPOINT"],
                    "key": os.environ["SEARCH_KEY"],
                    "indexName": os.environ["SEARCH_INDEX_NAME"],
                }
            }
        ]
    }
)
print(f"{completion.choices[0].message.role}: {completion.choices[0].message.content}")

# `context` is in the model_extra for Azure
print(f"\nContext: {completion.choices[0].message.model_extra['context']['messages'][0]['content']}")
```

如果想用串流接收回應，傳 `stream=True` 參數就可以：

```python
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "What are the differences between Azure Machine Learning and Azure AI services?"}],
    model=deployment,
    extra_body={
        "dataSources": [
            {
                "type": "AzureCognitiveSearch",
                "parameters": {
                    "endpoint": os.environ["SEARCH_ENDPOINT"],
                    "key": os.environ["SEARCH_KEY"],
                    "indexName": os.environ["SEARCH_INDEX_NAME"],
                }
            }
        ]
    },
    stream=True,
)

for chunk in response:
    delta = chunk.choices[0].delta

    if delta.role:
        print("\n"+ delta.role + ": ", end="", flush=True)
    if delta.content:
        print(delta.content, end="", flush=True)
    if delta.model_extra.get("context"):
        print(f"Context: {delta.model_extra['context']}", end="", flush=True)
```

## 重點整理

- Azure OpenAI on your data 讓 chat 模型直接根據你的文件回答，不用訓練或 fine-tuning。
- 流程是先用 Azure AI Search 依問題和對話歷史撈資料，再補進 prompt 給模型，這就是 grounding。
- 驗證可以用 API key，也可以用 Azure Active Directory。後者建議搭配 `get_bearer_token_provider`，token 會自動快取和更新。
- 資料來源在 `dataSources` 設定，回應的 `context` 會告訴你模型引用了什麼。
- 這個功能在原文寫作時還是 preview，需要先備齊 Azure OpenAI、AI Search、Blob Storage 三個資源。

## 練習

1. 把問題換成別的跟你 index 文件相關的問題，比較 `context` 裡引用的內容有什麼不同。
2. 在最後那個 chat completion 請求裡，多問一輪追問（例如「請再用一句話總結」），觀察 messages 裡的對話歷史怎麼影響撈回的資料。
3. 把驗證方式從 API key 改成 Azure Active Directory，確認 `.env` 不放 `AZURE_OPENAI_API_KEY` 還能跑。
