---
translated: true
source: examples/third_party/How_to_automate_S3_storage_with_functions.ipynb
---

# 用 function calling 自動化 AWS 工作

> 原文：[examples/third_party/How_to_automate_S3_storage_with_functions.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/third_party/How_to_automate_S3_storage_with_functions.ipynb)



## 這篇在做什麼

用 ChatGPT 的 function calling 操作 Amazon S3：列出 bucket、在所有 bucket 裡搜尋特定檔案、上傳和下載檔案。OpenAI Chat API 負責理解使用者指令、產生自然語言回應，並從輸入中抽出該呼叫的函式。

## 學完你會

- 寫 S3 的 helper 函式，並把函式描述和參數格式提供給模型
- 做一個對話主函式：送出使用者輸入、執行模型要求的函式呼叫、回傳最終回應
- 測試列出、搜尋、上傳、下載，以及模型怎麼處理參數不明確和無關任務

## 開跑前

- 一組有 S3 bucket 寫入權限的 AWS access key
- OpenAI API key
- 兩者都放在本機的 `.env` 檔裡

這份程式示範如何用 ChatGPT functions 完成跟 Amazon S3 bucket 相關的任務。notebook 涵蓋 S3 bucket 的主要功能：執行簡單的列出指令、在所有 bucket 裡搜尋特定檔案、上傳檔案到 bucket、從 bucket 下載檔案。OpenAI Chat API 會理解使用者指令、產生自然語言回應，並根據使用者輸入抽出適當的函式呼叫。

**需求**：
要執行這份 notebook，請產生具有 S3 bucket 寫入權限的 AWS access key，並和 OpenAI key 一起存在本機的環境檔裡。"`.env`" 檔的格式：
```
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-key>
OPENAI_API_KEY=<your-key>
```

```python
! pip install openai
! pip install boto3
! pip install tenacity
! pip install python-dotenv
```

```python
from openai import OpenAI
import json
import boto3
import os
import datetime
from urllib.request import urlretrieve

# load environment variables
from dotenv import load_dotenv
load_dotenv()
```

??? note "輸出"

    ```text
    True
    ```

## 初始化

```python
OpenAI.api_key = os.environ.get("OPENAI_API_KEY")
GPT_MODEL = "gpt-3.5-turbo"
```

```python
# Optional - if you had issues loading the environment file, you can set the AWS values using the below code
# os.environ['AWS_ACCESS_KEY_ID'] = ''
# os.environ['AWS_SECRET_ACCESS_KEY'] = ''

# Create S3 client
s3_client = boto3.client('s3')

# Create openai client
client = OpenAI()
```

## 工具函式

為了把使用者的問題或指令連到正確的函式，我們得提供 ChatGPT 必要的函式細節和預期的參數。

```python
# Functions dict to pass S3 operations details for the GPT model
functions = [
    {   
        "type": "function",
        "function":{
            "name": "list_buckets",
            "description": "List all available S3 buckets",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function":{
            "name": "list_objects",
            "description": "List the objects or files inside a given S3 bucket",
            "parameters": {
                "type": "object",
                "properties": {
                    "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                    "prefix": {"type": "string", "description": "The folder path in the S3 bucket"},
                },
                "required": ["bucket"],
            },
        }
    },
    {   
        "type": "function",
        "function":{
            "name": "download_file",
            "description": "Download a specific file from an S3 bucket to a local distribution folder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                    "key": {"type": "string", "description": "The path to the file inside the bucket"},
                    "directory": {"type": "string", "description": "The local destination directory to download the file, should be specificed by the user."},
                },
                "required": ["bucket", "key", "directory"],
            }
        }
    },
    {
        "type": "function",
        "function":{
            "name": "upload_file",
            "description": "Upload a file to an S3 bucket",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "The local source path or remote URL"},
                    "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                    "key": {"type": "string", "description": "The path to the file inside the bucket"},
                    "is_remote_url": {"type": "boolean", "description": "Is the provided source a URL (True) or local path (False)"},
                },
                "required": ["source", "bucket", "key", "is_remote_url"],
            }
        }
    },
    {
        "type": "function",
        "function":{
            "name": "search_s3_objects",
            "description": "Search for a specific file name inside an S3 bucket",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_name": {"type": "string", "description": "The name of the file you want to search for"},
                    "bucket": {"type": "string", "description": "The name of the S3 bucket"},
                    "prefix": {"type": "string", "description": "The folder path in the S3 bucket"},
                    "exact_match": {"type": "boolean", "description": "Set exact_match to True if the search should match the exact file name. Set exact_match to False to compare part of the file name string (the file contains)"}
                },
                "required": ["search_name"],
            },
        }
    }
]
```

建立跟 S3 服務互動的 helper 函式，例如列出 bucket、列出物件、下載和上傳檔案，以及搜尋特定檔案。

```python
def datetime_converter(obj):
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
```

```python
def list_buckets():
    response = s3_client.list_buckets()
    return json.dumps(response['Buckets'], default=datetime_converter)

def list_objects(bucket, prefix=''):
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    return json.dumps(response.get('Contents', []), default=datetime_converter)

def download_file(bucket, key, directory):
    
    filename = os.path.basename(key)
    
    # Resolve destination to the correct file path
    destination = os.path.join(directory, filename)
    
    s3_client.download_file(bucket, key, destination)
    return json.dumps({"status": "success", "bucket": bucket, "key": key, "destination": destination})

def upload_file(source, bucket, key, is_remote_url=False):
    if is_remote_url:
        file_name = os.path.basename(source)
        urlretrieve(source, file_name)
        source = file_name
       
    s3_client.upload_file(source, bucket, key)
    return json.dumps({"status": "success", "source": source, "bucket": bucket, "key": key})

def search_s3_objects(search_name, bucket=None, prefix='', exact_match=True):
    search_name = search_name.lower()
    
    if bucket is None:
        buckets_response = json.loads(list_buckets())
        buckets = [bucket_info["Name"] for bucket_info in buckets_response]
    else:
        buckets = [bucket]

    results = []

    for bucket_name in buckets:
        objects_response = json.loads(list_objects(bucket_name, prefix))
        if exact_match:
            bucket_results = [obj for obj in objects_response if search_name == obj['Key'].lower()]
        else:
            bucket_results = [obj for obj in objects_response if search_name in obj['Key'].lower()]

        if bucket_results:
            results.extend([{"Bucket": bucket_name, "Object": obj} for obj in bucket_results])

    return json.dumps(results)
```

下面這個字典把名稱對應到函式，讓我們能根據 ChatGPT 的回應執行對應的函式。

```python
available_functions = {
    "list_buckets": list_buckets,
    "list_objects": list_objects,
    "download_file": download_file,
    "upload_file": upload_file,
    "search_s3_objects": search_s3_objects
}
```

## ChatGPT

```python
def chat_completion_request(messages, functions=None, function_call='auto', 
                            model_name=GPT_MODEL):
    
    if functions is not None:
        return client.chat.completions.create(
            model=model_name,
            messages=messages,
            tools=functions,
            tool_choice=function_call)
    else:
        return client.chat.completions.create(
            model=model_name,
            messages=messages)
```

### 對話流程

建立 chatbot 的主函式：接收使用者輸入、送到 OpenAI Chat API、取得回應、執行 API 產生的任何函式呼叫，最後回傳最終回應給使用者。

```python
def run_conversation(user_input, topic="S3 bucket functions.", is_log=False):

    system_message=f"Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous. If the user ask question not related to {topic} response your scope is {topic} only."
    
    messages = [{"role": "system", "content": system_message},
                {"role": "user", "content": user_input}]
    
    # Call the model to get a response
    response = chat_completion_request(messages, functions=functions)
    response_message = response.choices[0].message
    
    if is_log:
        print(response.choices)
    
    # check if GPT wanted to call a function
    if response_message.tool_calls:
        function_name = response_message.tool_calls[0].function.name
        function_args = json.loads(response_message.tool_calls[0].function.arguments)
        
        # Call the function
        function_response = available_functions[function_name](**function_args)
        
        # Add the response to the conversation
        messages.append(response_message)
        messages.append({
            "role": "tool",
            "content": function_response,
            "tool_call_id": response_message.tool_calls[0].id,
        })
        
        # Call the model again to summarize the results
        second_response = chat_completion_request(messages)
        final_message = second_response.choices[0].message.content
    else:
        final_message = response_message.content

    return final_message
```

### S3 bucket bot 測試
在下面的範例中，執行前請先把 `<file_name>`、`<bucket_name>` 和 `<directory_path>` 這類佔位符換成你自己的值。

#### 列出與搜尋

先列出所有可用的 bucket。

```python
print(run_conversation('list my S3 buckets'))
```

你可以請 assistant 在所有 bucket 或某個特定 bucket 裡搜尋特定檔名。

```python
search_file = '<file_name>'
print(run_conversation(f'search for a file {search_file} in all buckets'))
```

```python
search_word = '<file_name_part>'
bucket_name = '<bucket_name>'
print(run_conversation(f'search for a file contains {search_word} in {bucket_name}'))
```

如果參數值有歧義，依 system message 的描述，模型應該會向使用者釐清需求。

```python
print(run_conversation('search for a file'))
```

??? note "輸出"

    ```text
    Sure, to help me find what you're looking for, could you please provide the name of the file you want to search for and the name of the S3 bucket? Also, should the search match the file name exactly, or should it also consider partial matches?
    ```

#### 驗證邊界情況

我們也指示模型拒絕無關的任務。來測試看看實際效果。

```python
# the model should not answer details not related to the scope
print(run_conversation('what is the weather today'))
```

??? note "輸出"

    ```text
    Apologies for the misunderstanding, but I am only able to assist with S3 bucket functions. Can you please ask a question related to S3 bucket functions?
    ```

提供的函式不只能取得資訊，也能協助使用者上傳或下載檔案。

#### 下載檔案

```python
search_file = '<file_name>'
bucket_name = '<bucket_name>'
local_directory = '<directory_path>'
print(run_conversation(f'download {search_file} from {bucket_name} bucket to {local_directory} directory'))
```

#### 上傳檔案

```python
local_file = '<file_name>'
bucket_name = '<bucket_name>'
print(run_conversation(f'upload {local_file} to {bucket_name} bucket'))
```

## 重點整理

- function calling 的做法是：把函式的描述和參數 schema 給模型，模型決定要不要呼叫、帶什麼參數，實際執行由你的程式負責。
- 名稱對函式的字典，是把模型回傳的函式名稱接到真正程式碼的橋。
- system message 可以約束行為，像是參數不明時先問、無關任務要拒絕。
- 這套模式不限於 S3，換成別的服務的 helper 函式就能重用。

## 練習

1. 新增一個 helper 函式（例如刪除物件，或取得檔案大小），補上它的描述並加進名稱對函式的字典。
2. 修改 system message，加一條規則（例如上傳前一定要先跟使用者確認），重跑上傳測試。
3. 故意問一個參數不全的問題，觀察模型怎麼追問，再想想如何讓它在缺參數時更有效率。
