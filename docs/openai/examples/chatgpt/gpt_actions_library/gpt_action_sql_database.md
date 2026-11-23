---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_sql_database.ipynb
---

# GPT Actions library：SQL Database

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_sql_database.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_sql_database.ipynb)



## 這篇在做什麼

說明怎麼用 GPT Action 讓 ChatGPT 查詢 SQL 資料庫。因為多數託管資料庫沒有 REST API，中間要架一層 middleware，負責收 SQL、送進資料庫，再把結果轉成 base64 的 CSV 回傳給 GPT。範例用 PostgreSQL，其他 SQL 資料庫做法類似。

## 學完你會

- 設計 middleware 的 OpenAPI schema，讓 GPT 能用一個 `q` 參數送出 SQL。
- 把資料庫回傳的 JSON 記錄轉成 CSV、做 base64 編碼，並用 `openaiFileResponse` 回給 GPT。
- 知道要怎麼設定唯讀權限和使用者層級的權限，避免 AI 產生的 SQL 傷到資料。

## 開跑前

- 需要 ChatGPT 的 GPT builder 和 Actions 功能（付費方案）。
- 需要自己部署一個 middleware（例如 serverless function）和一個可連線的 SQL 資料庫。
- 想讓 GPT 進一步分析回傳的檔案，要在 GPT 開啟 Code Interpreter & Data Analysis。



## 簡介

這份指南給想讓 ChatGPT 透過 GPT Action 查詢 SQL 資料庫的開發者。閱讀前請先熟悉下列內容：



* [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
* [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
* [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這份指南說明如何透過 middleware 應用把 ChatGPT 連到 SQL 資料庫。範例用 PostgreSQL，但其他 SQL 資料庫（MySQL、MS SQL Server、Amazon Aurora、Google Cloud 上的 SQL Server 等）流程都很類似。文件會講解建立 GPT Action 所需的步驟，這個 Action 能：



* 對 SQL 資料庫執行讀取查詢
* 用文字回應回傳記錄
* 用 CSV 檔案回傳記錄


### 價值與商業使用情境範例

**價值**：使用者現在可以靠 ChatGPT 的自然語言能力，回答關於 SQL 資料庫內資料的問題：



* 業務人員不用寫 SQL，也不用向分析師提需求，就能取得資料庫裡的資訊
* 資料分析師可以把資料抽出來交給 ChatGPT 分析，做到單靠 SQL 查詢做不到的複雜分析

**使用情境範例**：



* 業務人員想回答銷售漏斗的相關問題
* 資料分析師要對大型資料集做迴歸分析


## 應用設計考量

因為大多數託管的 SQL 資料庫不提供送出查詢的 REST API，你需要一個 middleware 應用來完成這些功能：



1. 透過 REST API request 接收資料庫查詢
2. 把查詢轉送給整合的 SQL 資料庫
3. 把資料庫回應轉成 CSV 檔案
4. 把 CSV 檔案回傳給請求方

第一個功能有兩種主要的設計方式：



1. middleware 只提供一個方法，接收 GPT 產生的任意 SQL 查詢並轉送給資料庫。這種做法的好處有：
    1. 開發容易
    2. 彈性高（不必預先想好使用者會下什麼查詢）
    3. 維護成本低（資料庫改了也不用更新 API schema）
2. middleware 提供多個方法，對應特定允許的查詢。這種做法的好處有：
    4. 控制更多
    5. 模型產生 SQL 時出錯的機會比較少

這份指南會專注在第一種。如果你對第二種有興趣，可以考慮用 [PostgREST](https://github.com/PostgREST/postgrest) 或 [Hasura](https://hasura.io/) 這類服務簡化流程。

![An application architecture diagram depicting the interaction between the user, GPT, middleware, and database](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_sql_database_middleware.png)
_應用架構圖_

## Middleware 的考量

開發者可以自己做 middleware（通常部署成 serverless function，放在 AWS、GCP、MS Azure 等雲端），也可以用第三方方案（像 [Mulesoft Anypoint](https://www.mulesoft.com/platform/enterprise-integration) 或 [Retool Workflows](https://retool.com/products/workflows)）。第三方 middleware 能加快開發，但彈性比自己做低。

自己做 middleware 能更掌握應用的行為。自訂 middleware 的範例可以看我們的 [Azure Functions cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function)。

這份指南不談 middleware 設定的細節，而是專注在 middleware 和 GPT、SQL 資料庫之間的介面。


## 流程步驟


### 1) GPT 產生 SQL 查詢

GPT 很擅長依使用者的自然語言 prompt 寫 SQL 查詢。你可以用下列其中一種方式讓它取得資料庫 schema，提升查詢產生的能力：



1. 指示 GPT 一開始先查詢資料庫取得 schema（這個做法在我們的 [BigQuery cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_bigquery#custom-gpt-instructions) 有更詳細的示範）。
2. 直接把 schema 寫在 GPT instructions 裡（最適合小型、不常變動的 schema）

下面是一份 GPT instructions 範例，包含簡單資料庫 schema 的資訊：


```python
# Context
You are a data analyst. Your job is to assist users with their business questions by analyzing the data contained in a PostgreSQL database.

## Database Schema

### Accounts Table
**Description:** Stores information about business accounts.

| Column Name  | Data Type      | Constraints                        | Description                             |
|--------------|----------------|------------------------------------|-----------------------------------------|
| account_id   | INT            | PRIMARY KEY, AUTO_INCREMENT, NOT NULL | Unique identifier for each account      |
| account_name | VARCHAR(255)   | NOT NULL                           | Name of the business account            |
| industry     | VARCHAR(255)   |                                    | Industry to which the business belongs  |
| created_at   | TIMESTAMP      | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Timestamp when the account was created  |

### Users Table
**Description:** Stores information about users associated with the accounts.

| Column Name  | Data Type      | Constraints                        | Description                             |
|--------------|----------------|------------------------------------|-----------------------------------------|
| user_id      | INT            | PRIMARY KEY, AUTO_INCREMENT, NOT NULL | Unique identifier for each user         |
| account_id   | INT            | NOT NULL, FOREIGN KEY (References Accounts(account_id)) | Foreign key referencing Accounts(account_id) |
| username     | VARCHAR(50)    | NOT NULL, UNIQUE                   | Username chosen by the user             |
| email        | VARCHAR(100)   | NOT NULL, UNIQUE                   | User's email address                    |
| role         | VARCHAR(50)    |                                    | Role of the user within the account     |
| created_at   | TIMESTAMP      | NOT NULL, DEFAULT CURRENT_TIMESTAMP | Timestamp when the user was created     |

### Revenue Table
**Description:** Stores revenue data related to the accounts.

| Column Name  | Data Type      | Constraints                        | Description                             |
|--------------|----------------|------------------------------------|-----------------------------------------|
| revenue_id   | INT            | PRIMARY KEY, AUTO_INCREMENT, NOT NULL | Unique identifier for each revenue record |
| account_id   | INT            | NOT NULL, FOREIGN KEY (References Accounts(account_id)) | Foreign key referencing Accounts(account_id) |
| amount       | DECIMAL(10, 2) | NOT NULL                           | Revenue amount                          |
| revenue_date | DATE           | NOT NULL                           | Date when the revenue was recorded      |

# Instructions:
1. When the user asks a question, consider what data you would need to answer the question and confirm that the data should be available by consulting the database schema.
2. Write a PostgreSQL-compatible query and submit it using the `databaseQuery` API method.
3. Use the response data to answer the user's question.
4. If necessary, use code interpreter to perform additional analysis on the data until you are able to answer the user's question.
```

### 2) GPT 把 SQL 查詢送給 middleware

為了讓 GPT 跟 middleware 溝通，我們要設定 GPT Action。middleware 需要提供一個 REST API endpoint 來接收 SQL 查詢字串，介面可以有好幾種設計方式。下面是一個簡單 endpoint 的 OpenAPI schema 範例，在 POST operation 裡接收 "q" 參數：

```python
openapi: 3.1.0
info:
  title: PostgreSQL API
  description: API for querying a PostgreSQL database
  version: 1.0.0
servers:
  - url: https://my.middleware.com/v1
    description: middleware service
paths:
  /api/query:
    post:
      operationId: databaseQuery
      summary: Query a PostgreSQL database
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                q:
                  type: string
                  example: select * from users
      responses:
        "200":
          description: database records
          content:
            application/json:
              schema:
                type: object
                properties:
                  openaiFileResponse:
                    type: array
                    items:
                      type: object
                      properties:
                        name:
                          type: string
                          description: The name of the file.
                        mime_type:
                          type: string
                          description: The MIME type of the file.
                        content:
                          type: string
                          format: byte
                          description: The content of the file in base64 encoding.
        "400":
          description: Bad Request. Invalid input.
        "401":
          description: Unauthorized. Invalid or missing API key.
      security:
        - ApiKey: []
components:
  securitySchemes:
    ApiKey:
      type: apiKey
      in: header
      name: X-Api-Key
  schemas: {}
```

**關於認證的說明：** 上面範例的 API 介面只接受一個系統層級的 API key，它跟 GPT 的設定存在一起，用來驗證所有 GPT 使用者的 request。GPT Actions 也支援 OAuth 認證，可以做到使用者層級的認證與授權。[了解更多 GPT Action 認證選項](https://platform.openai.com/docs/actions/authentication)。

因為使用者是對 middleware 認證，而不是直接對底層資料庫認證，要落實使用者層級的存取控制（資料表或 row 層級的權限）需要多花功夫。不過，如果 GPT 的使用者對底層資料庫有不同的存取等級，這可能是必要的。

 要落實使用者層級的權限，middleware 應該：



1. 接收 IdP 在 OAuth 流程中提供的使用者 metadata，並取出識別資訊
2. 查詢資料庫，取得該使用者的資料庫權限
3. 對資料庫下指令，在該 session 剩下的時間套用相關權限

為了維持好的使用體驗，建議針對每個使用者動態取得可用的資料庫 schema，而不是把 schema 資料直接寫在 GPT instructions 裡。這樣能確保 GPT 只能存取目前使用者有權代為查詢的資料表。


### 3) Middleware 把 SQL 查詢轉送給資料庫

你的 middleware 會實作資料庫 driver 或 client library，才能直接查詢 PostgreSQL 資料庫。如果用第三方 middleware，廠商應該會提供 SQL 資料庫的原生 connector。如果自己做 middleware，可能需要使用資料庫廠商或第三方提供的 client library。例如這是 PostgreSQL 社群維護的 client library 清單：[https://wiki.postgresql.org/wiki/List_of_drivers](https://wiki.postgresql.org/wiki/List_of_drivers)

在這個步驟，middleware 應用需要從 GPT 送來的 request 取出 SQL 字串，並用 client library 提供的方法轉送給資料庫。

**關於唯讀權限的說明：** 這個設計模式會讓資料庫處理任意由 AI 產生的 SQL 查詢，所以要確保 middleware 在資料庫上只有唯讀權限。這樣 AI 產生的查詢就不能新增資料或修改既有資料。如果你的使用情境需要寫入權限，建議改成部署針對特定操作的 endpoint，而不是接受任意 SQL。


### 4) 資料庫把記錄回傳給 middleware

依你採用的 client library 不同，middleware 可能收到各種格式的記錄。常見的模式是收到 JSON 物件的陣列，每個物件代表一筆符合查詢的資料庫記錄：


```python
[
  {
    "account_id": 1,
    "number_of_users": 10,
    "total_revenue": 43803.96,
    "revenue_per_user": 4380.40
  },
  {
    "account_id": 2,
    "number_of_users": 12,
    "total_revenue": 77814.84,
    "revenue_per_user": 6484.57
  },
  ...
]
```

### 5) Middleware 把記錄轉成 base64 編碼的 CSV 檔案

ChatGPT 要分析大量記錄，需要 CSV 格式的資料。GPT Actions 介面允許 GPT [接收 base64 編碼的檔案](https://platform.openai.com/docs/actions/sending-files/returning-files)，大小上限 10mb。

你的 middleware 需要做兩件事：


#### 把記錄轉成 CSV 格式

很多程式語言都有處理 CSV 檔案的原生函式庫（例如 Python 的 [csv](https://docs.python.org/3/library/csv.html)）。

下面示範 middleware 怎麼把 JSON 物件的陣列轉成 CSV 檔案：

```python
import json
import csv

# Sample JSON array of objects
json_data = '''
[
    {"account_id": 1, "number_of_users": 10, "total_revenue": 43803.96, "revenue_per_user": 4380.40}, 
    {"account_id": 2, "number_of_users": 12, "total_revenue": 77814.84, "revenue_per_user": 6484.57}
]
'''

# Load JSON data
data = json.loads(json_data)

# Define the CSV file name
csv_file = 'output.csv'

# Write JSON data to CSV
with open(csv_file, 'w', newline='') as csvfile:
    # Create a CSV writer object
    csvwriter = csv.writer(csvfile)
    
    # Write the header (keys of the first dictionary)
    header = data[0].keys()
    csvwriter.writerow(header)
    
    # Write the data rows
    for row in data:
        csvwriter.writerow(row.values())

print(f"JSON data has been written to {csv_file}")
```

#### 把 CSV 檔案做 base64 編碼

很多程式語言也有處理 base64 編碼的原生函式庫（例如 Python 的 [base64](https://docs.python.org/3/library/base64.html)）。

下面示範 middleware 怎麼把上一步產生的 CSV 檔案做 base64 編碼：

```python
import base64 

# Base64 encode the CSV file
encoded_string = base64.b64encode(open('output.csv', 'rb').read()).decode('utf-8')

print("Base64 Encoded CSV:")
print(encoded_string)
```

### 6) Middleware 把 base64 編碼的 CSV 檔案回傳給 GPT

為了讓 GPT Actions 介面能處理 base64 編碼的 CSV 檔案，middleware 回傳的 response 必須包含 `openaiFileResponse` 參數。它的值必須是檔案物件或檔案連結的陣列（詳見 [Actions 文件](https://platform.openai.com/docs/actions/sending-files/returning-files)）。這個範例用檔案物件的陣列。

下面是合法 response body 的範例：

```python
{
  "openaiFileResponse": [
    {
      "name": "output.csv",
      "mime_type": "text/csv",
      "content": "ImFjY291bn...NC41NyI="
    }
  ]
}
```

### 7) GPT 處理回傳的檔案

GPT 收到 base64 編碼的 CSV 檔案後，會自動解碼並處理，用來回答使用者的問題。這可能包括用 [code interpreter 對 CSV 檔案做進一步分析](https://help.openai.com/en/articles/9213685-extracting-insights-with-chatgpt-data-analysis)，運作方式跟使用者在 prompt 裡直接上傳 CSV 檔案一樣。

**注意：** 如果想對回傳的檔案做進一步分析，必須在 GPT 啟用 _Code Interpreter & Data Analysis_ 功能。


## 結論

GPT Actions 提供彈性的框架，能從 SQL 資料庫這類外部來源取得資料。讓 ChatGPT 能查詢資料庫，可以大幅擴充它作為知識助理和分析師的能力。

_有哪些整合是你希望我們優先處理的？我們的整合有錯誤嗎？歡迎到 GitHub 發 PR 或 issue，我們會看。_

## 重點整理

- 託管 SQL 資料庫通常沒有 REST API，所以要靠 middleware 接 GPT 的請求、查資料庫、回傳結果。
- 讓 GPT 直接送任意 SQL 最省事也最彈性，代價是模型可能寫錯 SQL，所以 middleware 一定要用唯讀權限。
- schema 小又固定就寫進 GPT instructions；使用者權限不同時，要動態取得每個人可用的 schema。
- 大量記錄用 CSV 傳，要 base64 編碼並放在 `openaiFileResponse`，上限 10mb。
- 想讓 GPT 進一步分析回傳的檔案，要開 Code Interpreter & Data Analysis。

## 練習

1. 在 GPT instructions 範例裡換成你自己資料表的 schema，請 GPT 回答一個需要 JOIN 的問題，檢查它產生的 SQL。
2. 改 OpenAPI schema，把 `q` 參數的描述加上限制（例如只允許 SELECT、結果最多 1000 筆），看 GPT 的行為有什麼變化。
3. 修改 CSV 轉換的程式，讓空值輸出成特定字串，並在 middleware 回傳前檢查 base64 編碼後的大小有沒有超過 10mb，超過就回錯誤訊息。
