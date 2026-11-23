---
translated: true
source: examples/azure/functions.ipynb
---

# Azure Functions 範例

> 原文：[examples/azure/functions.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/azure/functions.ipynb)

## 這篇在做什麼
示範怎麼在 Azure OpenAI service 上用 function calling。你會定義函式、讓模型決定要不要呼叫、執行函式，再把結果餵回去讓模型組出最後答案。

## 學完你會
- 用 API key 或 Azure Active Directory 設定 `AzureOpenAI` client
- 用 JSON schema 定義函式，並傳給 chat completions API
- 完整跑一輪 function calling：拿到 tool call、執行函式、把結果回傳給模型

## 開跑前
需要一個 Azure OpenAI 資源，並在 Azure OpenAI Studio 建好 chat 模型的 deployment。設定 `AZURE_OPENAI_API_KEY`、`AZURE_OPENAI_ENDPOINT` 這類環境變數，或改用 Azure AD 驗證。

這個 notebook 示範怎麼在 Azure OpenAI service 上使用 function calling。chat completions 的呼叫端可以定義一些函式，讓模型用來把能力延伸到外部工具和資料來源。

更多說明可以看 OpenAI 的部落格：https://openai.com/blog/function-calling-and-other-api-updates

**注意**：chat functions 需要 gpt-4 以上的模型版本，以及 `-0613` 標籤開頭的 gpt-35-turbo。更舊的模型版本不支援。

## 設定

先安裝需要的套件並 import。

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

Azure OpenAI service 支援多種驗證方式，包含 API key 和 Azure Active Directory 的 token credential。

```python
use_azure_active_directory = False  # Set this flag to True if you are using Azure Active Directory
```

#### 用 API key 驗證

要讓 OpenAI SDK 使用 *Azure API Key*，要把 `api_key` 設成你 endpoint 的 key（在 [Azure Portal](https://portal.azure.com) 的 *Resource Management* 底下 *Keys and Endpoints* 找得到）。resource 的 endpoint 也在同一個地方。

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
再來看怎麼用 Azure Active Directory 驗證。先安裝 `azure-identity`，它提供驗證需要的 token credential，並透過 `get_bearer_token_provider` 這個 helper 建出 token credential provider。比起給 `AzureOpenAI` 一個固定的 token，更建議用 `get_bearer_token_provider`，因為它會自動快取並更新 token。

Azure Active Directory 搭配 Azure OpenAI 的設定方式，可以看這份[文件](https://learn.microsoft.com/azure/ai-services/openai/how-to/managed-identity)。

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

這一節要建立一個 GPT 模型的 deployment，之後拿來呼叫函式。

### Deployment：在 Azure OpenAI Studio 建立
先部署一個 chat completions 用的模型。到 https://portal.azure.com 找到你的 Azure OpenAI resource，進入 Azure OpenAI Studio，點 "Deployments" 分頁，替想用的模型建一個 deployment。你給 deployment 取的名字會在下面的程式碼用到。

```python
deployment = "" # Fill in the deployment name from the portal here
```

## 函式

設定和驗證完成後，就能在 Azure OpenAI service 上用函式了。流程分幾步：

1. 定義函式
2. 把函式定義傳給 chat completions API
3. 用回應裡的參數呼叫函式
4. 把函式的結果回傳給 chat completions API

#### 1. 定義函式

可以定義一串函式，每個包含函式名稱、選填的描述，以及函式接受的參數（用 JSON schema 描述）。

```python
functions = [
    {
        "name": "get_current_weather",
        "description": "Get the current weather",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                },
                "format": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                    "description": "The temperature unit to use. Infer this from the users location.",
                },
            },
            "required": ["location"],
        },
    }
]
```

#### 2. 把函式定義傳給 chat completions API

現在可以把函式傳給 chat completions API。如果模型判斷該呼叫函式，choice 的 `finish_reason` 會是 "tool_calls"，要呼叫哪個函式和參數會在 `message` 裡。你也可以設 `tool_choice` 參數強制模型呼叫特定函式（例如 `{"type": "function", "function": {"name": get_current_weather}}`）。預設是 `auto`，讓模型自己決定要不要呼叫。

```python
messages = [
    {"role": "system", "content": "Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous."},
    {"role": "user", "content": "What's the weather like today in Seattle?"}
]

chat_completion = client.chat.completions.create(
    model=deployment,
    messages=messages,
    tools=functions,
)
print(chat_completion)
```

#### 3. 用回應裡的參數呼叫函式

函式呼叫的名稱會是你一開始提供的名稱，參數則是符合函式定義 schema 的 JSON。

```python
import json

def get_current_weather(request):
    """
    This function is for illustrative purposes.
    The location and unit should be used to determine weather
    instead of returning a hardcoded response.
    """
    location = request.get("location")
    unit = request.get("unit")
    return {"temperature": "22", "unit": "celsius", "description": "Sunny"}

function_call = chat_completion.choices[0].message.tool_calls[0].function
print(function_call.name)
print(function_call.arguments)

if function_call.name == "get_current_weather":
    response = get_current_weather(json.loads(function_call.arguments))
```

#### 4. 把函式回應餵回 chat completions API

函式的回應要序列化成一則新 message，role 設為 "function"。這樣模型就會用回應資料來組出答案。

```python
messages.append(
    {
        "role": "function",
        "name": "get_current_weather",
        "content": json.dumps(response)
    }
)

function_completion = client.chat.completions.create(
    model=deployment,
    messages=messages,
    tools=functions,
)

print(function_completion.choices[0].message.content.strip())
```

## 重點整理
- Azure OpenAI 的 function calling 用法和 OpenAI 一致，差別主要在 client 設定與 deployment 名稱。
- 驗證可以用 API key，也可以用 Azure AD，後者建議用 `get_bearer_token_provider` 自動快取更新 token。
- 函式用 JSON schema 描述，模型只負責決定呼叫誰和給什麼參數，真正執行在你自己的程式。
- `finish_reason` 為 "tool_calls" 表示模型想呼叫函式，`tool_choice` 可以強制指定。
- 函式結果要再放回對話，模型才能產生最終回答。

## 練習
1. 在函式清單多加一個參數（例如溫度單位 enum），看模型傳來的參數有什麼變化。
2. 把 `tool_choice` 改成強制呼叫特定函式，再改回 `auto`，比較問不相關問題時的行為。
3. 再定義第二個函式，讓模型在一個問題裡同時呼叫兩個函式，並把兩個結果都回傳。
