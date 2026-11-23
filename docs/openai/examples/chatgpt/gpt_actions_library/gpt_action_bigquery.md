---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_bigquery.ipynb
---

# GPT Actions library：BigQuery

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_bigquery.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_bigquery.ipynb)



## 這篇在做什麼
教你做一個連到 Google BigQuery 的 GPT Action。使用者問問題後，GPT 會先掃相關資料表取得 schema，再寫出能回答問題的 SQL。

## 學完你會
- 設定 Custom GPT 的 Instructions 和 OpenAPI schema，讓 GPT 能呼叫 BigQuery API
- 在 Google Cloud Console 建 OAuth 憑證，並在 ChatGPT 填入 OAuth 設定
- 處理 callback URL 錯誤、GPT 查錯 project 或 dataset 這類常見問題

## 開跑前
- 一個 GCP project，裡面有 BigQuery dataset
- 用 ChatGPT 登入 BigQuery 的使用者要有該 dataset 的存取權
- Google OAuth Client ID 和 Client Secret


## 簡介

這一頁是給開發者的說明，教你替特定應用程式建 GPT Action。開始之前，請先熟悉以下內容： 
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 **Google BigQuery**，也就是 Google Cloud 的分析型資料倉儲。這個 Action 接收使用者的問題，掃描相關資料表來取得資料 schema，再寫 SQL 查詢來回答問題。 

注意：這份說明回傳的是可執行的 SQL 語句，不是查詢結果本身。目前要回傳 CSV 檔需要 middleware，我們之後會發佈相關範例說明。

### 價值與商業使用情境

**價值**：使用者現在可以用 ChatGPT 的自然語言能力，直接連到 BigQuery 的資料倉儲。 

**使用情境範例**： 
- 資料科學家可以連到資料表，用 ChatGPT 的 Data Analysis 做資料分析
- 一般資料使用者可以對交易資料問基本問題
- 使用者能更清楚看到自己的資料和潛在異常

## 應用程式資訊

### 應用程式重要連結

開始之前，先看看這些應用程式的連結：
- 應用程式網站：https://cloud.google.com/bigquery 
- 應用程式 API 文件：https://cloud.google.com/bigquery/docs/reference/rest 

### 應用程式前置需求

開始之前，請先在你的應用程式環境完成以下步驟：
- 建立 GCP project 
- 在該 GCP project 建一個 BQ dataset
- 確保透過 ChatGPT 登入 BigQuery 的使用者有該 BQ dataset 的存取權 

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

```python
**Context**: You are an expert at writing BigQuery SQL queries. A user is going to ask you a question. 

**Instructions**:
1. No matter the user's question, start by running `runQuery` operation using this query: "SELECT column_name, table_name, data_type, description FROM `{project}.{dataset}.INFORMATION_SCHEMA.COLUMN_FIELD_PATHS`" 
-- Assume project = "<insert your default project here>", dataset = "<insert your default dataset here>", unless the user provides different values 
-- Remember to include useLegacySql:false in the json output
2. Convert the user's question into a SQL statement that leverages the step above and run the `runQuery` operation on that SQL statement to confirm the query works. Add a limit of 100 rows
3. Now remove the limit of 100 rows and return back the query for the user to see

**Additional Notes**: If the user says "Let's get started", explain that the user can provide a project or dataset, along with a question they want answered. If the user has no ideas, suggest that we have a sample flights dataset they can query - ask if they want you to query that
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

```python
openapi: 3.1.0
info:
  title: BigQuery API
  description: API for querying a BigQuery table.
  version: 1.0.0
servers:
  - url: https://bigquery.googleapis.com/bigquery/v2
    description: Google BigQuery API server
paths:
  /projects/{projectId}/queries:
    post:
      operationId: runQuery
      summary: Executes a query on a specified BigQuery table.
      description: Submits a query to BigQuery and returns the results.
      x-openai-isConsequential: false
      parameters:
        - name: projectId
          in: path
          required: true
          description: The ID of the Google Cloud project.
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                  description: The SQL query string.
                useLegacySql:
                  type: boolean
                  description: Whether to use legacy SQL.
                  default: false
      responses:
        '200':
          description: Successful query execution.
          content:
            application/json:
              schema:
                type: object
                properties:
                  kind:
                    type: string
                    example: "bigquery#queryResponse"
                  schema:
                    type: object
                    description: The schema of the results.
                  jobReference:
                    type: object
                    properties:
                      projectId:
                        type: string
                      jobId:
                        type: string
                  rows:
                    type: array
                    items:
                      type: object
                      properties:
                        f:
                          type: array
                          items:
                            type: object
                            properties:
                              v:
                                type: string
                  totalRows:
                    type: string
                    description: Total number of rows in the query result.
                  pageToken:
                    type: string
                    description: Token for pagination of query results.
        '400':
          description: Bad request. The request was invalid.
        '401':
          description: Unauthorized. Authentication is required.
        '403':
          description: Forbidden. The request is not allowed.
        '404':
          description: Not found. The specified resource was not found.
        '500':
          description: Internal server error. An error occurred while processing the request.
```

## 認證設定說明

以下是設定這個第三方應用程式認證的步驟。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

### Action 前的步驟

在 ChatGPT 設定認證之前，請先在應用程式裡完成以下步驟。

- 前往 Google Cloud Console
- 到 API & Services > Credentials
- 建立新的 OAuth 憑證（或使用現有的）
- 找到 OAuth Client ID 和 Client Secret，並安全地保存這兩個值（見下方截圖）

![gptactions_BigQuery_auth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_BigQuery_auth.png)

### 在 ChatGPT 裡

在 ChatGPT 點「Authentication」，選 **"OAuth"**，填入下列資訊。 

- **Client ID**：用上面步驟取得的 Client ID 
- **Client Secret**：用上面步驟取得的 Client Secret
- **Authorization URL**：https://accounts.google.com/o/oauth2/auth
- **Token URL**：https://oauth2.googleapis.com/token 
- **Scope**：https://www.googleapis.com/auth/bigquery 
- **Token**：Default (POST)

### Action 後的步驟

在 ChatGPT 設定好認證後，回到應用程式完成以下步驟來收尾。 

- 從 GPT Action 複製 callback URL
- 把你的 callback URL 加到「Authorized redirect URIs」（見上方截圖）


### FAQ 與疑難排解

- *Callback URL 錯誤：* 如果 ChatGPT 出現 callback URL 錯誤，仔細看上面的截圖。你必須把 callback URL 直接加到 GCP，Action 才能正確認證
- *Schema 呼叫了錯的 project 或 dataset：* 如果 ChatGPT 呼叫了錯的 project 或 dataset，可以修改 instructions，寫得更明確：(a) 該呼叫哪個 project / dataset，或 (b) 要求使用者在執行查詢前提供確切的資訊

*有想要我們優先支援的整合嗎？我們的整合有錯誤嗎？歡迎在 GitHub 提 PR 或 issue，我們會處理。*


## 重點整理
- GPT Action 由三塊組成：Instructions（角色與行為）、OpenAPI schema（可呼叫的 API）、Authentication。
- 這個 Action 只回傳可執行的 SQL，要拿到結果檔需要另外的 middleware。
- BigQuery 用 OAuth 認證，callback URL 要手動加回 GCP 的 Authorized redirect URIs。
- 使用者的 Google 帳號權限決定能查到什麼，所以要確保帳號有 dataset 存取權。
- GPT 查錯 project 或 dataset 時，改 instructions 把目標寫明確最有效。

## 練習
1. 在 Instructions 裡寫死你的 project 和 dataset 名稱，測試 GPT 是不是不再查錯地方。
2. 在 Instructions 加一條規則，要求 GPT 在寫 SQL 前先列出它掃到的資料表和欄位。
3. 改 OpenAPI schema 裡的 operation 描述，觀察 GPT 選擇呼叫哪個 API 的行為有什麼變化。
