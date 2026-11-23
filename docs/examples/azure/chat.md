---
translated: true
source: examples/azure/chat.ipynb
---

# Azure Chat Completions 範例（preview）

> 原文：[examples/azure/chat.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/azure/chat.ipynb)



## 這篇在做什麼
示範用 Azure OpenAI 服務做 chat completions，包含兩種驗證方式、一般與 streaming 呼叫，以及怎麼處理 content filtering。

## 學完你會
- 用 API key 或 Azure Active Directory 設定 `AzureOpenAI` client
- 用 deployment 名稱建立一般和 streaming 的 chat completion
- 處理被 content filter 擋下的 prompt，並讀取回應中的 content filter 結果

## 開跑前
- 一個 Azure OpenAI 資源，以及在 Azure OpenAI Studio 建立好的模型 deployment
- 該資源的 API key 和 endpoint（或使用 Azure Active Directory 驗證）

這個範例會介紹如何用 Azure OpenAI 服務做 chat completions，也包含內容過濾 (content filtering) 的資訊。

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

### 驗證

Azure OpenAI 服務支援多種驗證機制，包括 API key 和 Azure Active Directory token 憑證。

```python
use_azure_active_directory = False  # Set this flag to True if you are using Azure Active Directory
```

#### 用 API key 驗證

要讓 OpenAI SDK 使用 *Azure API Key*，需要把 `api_key` 設成你的 endpoint 對應的 key（可以在 [Azure Portal](https://portal.azure.com) 的 *"Resource Management"* 底下的 *"Keys and Endpoints"* 找到）。你也會在那裡找到資源的 endpoint。

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

#### 用 Azure Active Directory 驗證
現在來看怎麼透過 Azure Active Directory 驗證。先安裝 `azure-identity` 函式庫。這個函式庫提供驗證所需的 token 憑證，並透過 `get_bearer_token_provider` 這個 helper 函式，幫我們建立 token 憑證 provider。建議使用 `get_bearer_token_provider`，而不是給 `AzureOpenAI` 一個靜態 token，因為這個 API 會自動幫你快取並更新 token。 

更多關於如何用 Azure OpenAI 設定 Azure Active Directory 驗證的資訊，請看[文件](https://learn.microsoft.com/azure/ai-services/openai/how-to/managed-identity)。

```python
! pip install "azure-identity>=1.15.0"
```

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

if use_azure_active_directory:
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"]

    client = openai.AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"),
        api_version="2023-09-01-preview"
    )
```

> 注意：如果沒有提供這些參數，AzureOpenAI 會從對應的環境變數推斷：

- `api_key` 來自 `AZURE_OPENAI_API_KEY`
- `azure_ad_token` 來自 `AZURE_OPENAI_AD_TOKEN`
- `api_version` 來自 `OPENAI_API_VERSION`
- `azure_endpoint` 來自 `AZURE_OPENAI_ENDPOINT`


## Deployment

這一段要建立一個 GPT 模型的 deployment，用來建立 chat completions。

### Deployment：在 Azure OpenAI Studio 建立
來部署一個要用在 chat completions 的模型。到 https://portal.azure.com，找到你的 Azure OpenAI 資源，然後進入 Azure OpenAI Studio。點選 "Deployments" 分頁，然後為你要用在 chat completions 的模型建立一個 deployment。你給模型取的 deployment 名稱，會用在下面的程式裡。

```python
deployment = "" # Fill in the deployment name from the portal here
```

## 建立 chat completion

現在用我們建好的 client 來建立 chat completion。

```python
# For all possible arguments see https://platform.openai.com/docs/api-reference/chat-completions/create
response = client.chat.completions.create(
    model=deployment,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Knock knock."},
        {"role": "assistant", "content": "Who's there?"},
        {"role": "user", "content": "Orange."},
    ],
    temperature=0,
)

print(f"{response.choices[0].message.role}: {response.choices[0].message.content}")
```

### 建立 streaming chat completion

我們也可以用 stream 的方式取得回應。

```python
response = client.chat.completions.create(
    model=deployment,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Knock knock."},
        {"role": "assistant", "content": "Who's there?"},
        {"role": "user", "content": "Orange."},
    ],
    temperature=0,
    stream=True
)

for chunk in response:
    if len(chunk.choices) > 0:
        delta = chunk.choices[0].delta

        if delta.role:
            print(delta.role + ": ", end="", flush=True)
        if delta.content:
            print(delta.content, end="", flush=True)
```

### 內容過濾 (Content filtering)

Azure OpenAI 服務包含對 prompt 和 completion 回應的內容過濾。你可以在[這裡](https://learn.microsoft.com/azure/ai-services/openai/concepts/content-filter)進一步了解內容過濾以及怎麼設定。

如果 prompt 被內容過濾器標記，函式庫會丟出帶有 `content_filter` 錯誤碼的 `BadRequestError` 例外。否則，你可以從回應中存取 `prompt_filter_results` 和 `content_filter_results`，查看內容過濾的結果以及哪些類別被標記。

#### Prompt 被內容過濾器標記

```python
import json

messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "<text violating the content policy>"}
]

try:
    completion = client.chat.completions.create(
        messages=messages,
        model=deployment,
    )
except openai.BadRequestError as e:
    err = json.loads(e.response.text)
    if err["error"]["code"] == "content_filter":
        print("Content filter triggered!")
        content_filter_result = err["error"]["innererror"]["content_filter_result"]
        for category, details in content_filter_result.items():
            print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")
```

### 檢查內容過濾的結果

```python
messages = [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "What's the biggest city in Washington?"}
]

completion = client.chat.completions.create(
    messages=messages,
    model=deployment,
)
print(f"Answer: {completion.choices[0].message.content}")

# prompt content filter result in "model_extra" for azure
prompt_filter_result = completion.model_extra["prompt_filter_results"][0]["content_filter_results"]
print("\nPrompt content filter results:")
for category, details in prompt_filter_result.items():
    print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")

# completion content filter result
print("\nCompletion content filter results:")
completion_filter_result = completion.choices[0].model_extra["content_filter_results"]
for category, details in completion_filter_result.items():
    print(f"{category}:\n filtered={details['filtered']}\n severity={details['severity']}")
```

## 重點整理
- Azure OpenAI 用 `AzureOpenAI` client，驗證可用 API key 或 Azure AD token。
- Azure AD 建議用 `get_bearer_token_provider`，會自動快取並更新 token。
- 呼叫時填的是 deployment 名稱，不是模型名稱。
- 被 content filter 擋下的 prompt 會丟 `BadRequestError`，沒被擋的回應則附帶各類別的過濾結果。

## 練習
1. 把 client 設定改成只靠環境變數（不傳參數），確認仍能呼叫成功。
2. 把 streaming 範例改成逐 chunk 即時印出內容。
3. 寫一段 try/except，抓到 `BadRequestError` 時判斷是不是 `content_filter` 錯誤碼，並印出友善訊息；沒被擋時印出每個類別的 `content_filter_results`。
