---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_notion.ipynb
---

# GPT Actions library：Notion

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_notion.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_notion.ipynb)



## 這篇在做什麼
教你做一個連到 Notion 的 GPT Action。它接收使用者的問題，用 Notion 的搜尋功能掃描相關頁面，再回傳符合頁面的資訊。

## 學完你會
- 在 Notion 建立 Internal Integration，取得 Internal Integration Secret
- 設定 Custom GPT 的 Instructions、OpenAPI schema 和 Bearer 認證
- 知道要把頁面或 wiki 分享給 integration，GPT 才查得到

## 開跑前
- 一個有內容頁面的 Notion workspace
- 在 Notion 建立的 integration 和它的 secret


## 簡介

這一頁是給開發者的說明，教你替特定應用程式建 GPT Action。開始之前，請先熟悉以下內容： 
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 **Notion**。這個 Action 接收使用者的問題，用 Notion 的搜尋功能掃描相關的 Notion 頁面，然後回傳符合頁面的資訊。

### 價值與商業使用情境

**價值**：使用者現在可以用 ChatGPT 的自然語言能力，直接連到 Notion 裡的知識，並查詢和整合。管理員可以明確地把頁面分享給 integration 來管理存取權限。

**使用情境範例**： 
- 新進員工想快速找到設定新系統的 how-to 資訊
- 客服人員需要從 Notion 快速取得資訊，不用讀完整份文件
- 使用者想整合資訊，做成摘要或轉換格式，用在工作的其他地方

## 應用程式資訊

### 應用程式重要連結

開始之前，先看看這些應用程式的連結：
- 應用程式網站：https://www.notion.so/
- 應用程式 API 文件：https://developers.notion.com/reference/intro
- Notion 授權方式：https://developers.notion.com/docs/authorization
    - 注意：Notion 只允許「Public Integrations」使用 OAuth。請參考連結的文件，判斷哪種最適合你的需求

### 應用程式前置需求

開始之前，請先在你的應用程式環境完成以下步驟：
- 建立一個有內容頁面的 notion workspace
- 在 notion 分享頁面，搭配特定的 Wiki 效果最好。可以考慮把知識庫整理成一個或一組 wiki

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有問題可以看 [Getting Started Example](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_getting_started)，裡面有這一步的詳細說明。

```python
**Context**: You are a helpful chatbot focussed on retrieving information from a company's Notion. An administrator has given you access to a number of useful Notion pages.  You are to act similar to a librarian and be helpful answering and finding answers for users' questions.

**Instructions**:
1. Use the search functionality to find the most relevant page or pages.
- Display the top 3 pages.  Include a formatted list containing: Title, Last Edit Date, Author.
- The Title should be a link to that page.
1.a. If there are no relevant pages, reword the search and try again (up to 3x)
1.b. If there are no relevant pages after retries, return "I'm sorry, I cannot find the right info to help you with that question"
2. Open the most relevant article, retrieve and read all of the contents (including any relevant linked pages or databases), and provide a 3 sentence summary.  Always provide a quick summary before moving to the next step.
3. Ask the user if they'd like to see more detail.  If yes, provide it and offer to explore more relevant pages.

**Additional Notes**: 
- If the user says "Let's get started", introduce yourself as a librarian for the Notion workspace, explain that the user can provide a topic or question, and that you will help to look for relevant pages.
- If there is a database on the page.  Always read the database when looking at page contents.
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

```python
openapi: 3.1.0
info:
  title: Notion API
  description: API for interacting with Notion's pages, databases, and users.
  version: 1.0.0
servers:
  - url: https://api.notion.com/v1
    description: Main Notion API server
paths:
  /users:
    get:
      operationId: listAllUsers
      summary: List all users
      parameters:
        - name: Notion-Version
          in: header
          required: true
          schema:
            type: string
          example: 2022-06-28
          constant: 2022-06-28
      responses:
        '200':
          description: Successful response
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
                        name:
                          type: string
                        avatar_url:
                          type: string
                        type:
                          type: string
  /blocks/{block_id}/children:
    get:
      operationId: retrieveBlockChildren
      summary: Retrieve block children
      parameters:
        - name: block_id
          in: path
          required: true
          schema:
            type: string
        - name: Notion-Version
          in: header
          required: true
          schema:
            type: string
          example: 2022-06-28
          constant: 2022-06-28
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  object:
                    type: string
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                        type:
                          type: string
                        has_children:
                          type: boolean
  /comments:
    get:
      operationId: retrieveComments
      summary: Retrieve comments
      parameters:
        - name: Notion-Version
          in: header
          required: true
          schema:
            type: string
          example: 2022-06-28
          constant: 2022-06-28
      responses:
        '200':
          description: Successful response
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
                        text:
                          type: string
                        created_time:
                          type: string
                          format: date-time
                        created_by:
                          type: object
                          properties:
                            id:
                              type: string
                            name:
                              type: string
  /pages/{page_id}/properties/{property_id}:
    get:
      operationId: retrievePagePropertyItem
      summary: Retrieve a page property item
      parameters:
        - name: page_id
          in: path
          required: true
          schema:
            type: string
        - name: property_id
          in: path
          required: true
          schema:
            type: string
        - name: Notion-Version
          in: header
          required: true
          schema:
            type: string
          example: 2022-06-28
          constant: 2022-06-28
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  type:
                    type: string
                  title:
                    type: array
                    items:
                      type: object
                      properties:
                        type:
                          type: string
                        text:
                          type: object
                          properties:
                            content:
                              type: string
  /databases/{database_id}/query:
    post:
      operationId: queryDatabase
      summary: Query a database
      parameters:
        - name: database_id
          in: path
          required: true
          schema:
            type: string
        - name: Notion-Version
          in: header
          required: true
          schema:
            type: string
          example: 2022-06-28
          constant: 2022-06-28
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                filter:
                  type: object
                sorts:
                  type: array
                  items:
                    type: object
                start_cursor:
                  type: string
                page_size:
                  type: integer
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  object:
                    type: string
                  results:
                    type: array
                    items:
                      type: object
                  next_cursor:
                    type: string
                  has_more:
                    type: boolean
  /search:
    post:
      operationId: search
      summary: Search
      parameters:
        - name: Notion-Version
          in: header
          required: true
          schema:
            type: string
          example: 2022-06-28
          constant: 2022-06-28
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                query:
                  type: string
                filter:
                  type: object
                  properties:
                    value:
                      type: string
                    property:
                      type: string
                sort:
                  type: object
                  properties:
                    direction:
                      type: string
                    timestamp:
                      type: string
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                type: object
                properties:
                  object:
                    type: string
                  results:
                    type: array
                    items:
                      type: object
                      properties:
                        id:
                          type: string
                        title:
                          type: array
                          items:
                            type: object
                            properties:
                              type:
                                type: string
                              text:
                                type: object
                                properties:
                                  content:
                                    type: string
```

## 認證設定說明

以下是設定這個第三方應用程式認證的步驟。

### Action 前的步驟

在 ChatGPT 設定認證之前，請先在 Notion 完成以下步驟。

1. 前往 workspace 的 Notion Settings 頁面
2. 到 My Connections > Develop or Manage Integrations
3. 建立新的 Integration，標記為 Internal
4. 找到你的 integration，找到標示為 Internal Integration Secret 的 API Key。這就是這個 integration 的 bearer token。

**注意！** 你必須把特定的頁面、資料庫或 wiki 分享給 integration，才能在 ChatGPT 裡存取。做法是點頁面右上角的 ... 按鈕，選擇對應的 connection。

**注意！** 如果 integration 標記為「Public」，Notion 允許它使用 OAuth。請看 [Notion's Auth Documentation](https://developers.notion.com/docs/authorization)，判斷哪種 integration 路線最適合你的需求。

![notion_connections.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/creating_notion_integration.png)

![sharing_notion_pages.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/sharing_notion_with_GPT.png)

### 在 ChatGPT 裡

在 ChatGPT 點「Authentication」，選 **"API Key"**，填入下列資訊。 

- **API Key**：用上面步驟取得的 Internal Integration Secret
- **Auth Type**：Bearer

### FAQ 與疑難排解

- *搜尋沒有回傳任何東西*：如果搜尋沒有回傳任何頁面，請再確認你已經在 Notion 把相關頁面分享給這個應用程式

*有想要我們優先支援的整合嗎？我們的整合有錯誤嗎？歡迎在 GitHub 提 PR 或 issue，我們會處理。*


## 重點整理
- Notion 的 Internal Integration 用 Bearer token 認證，Public Integration 才能走 OAuth。
- integration 只能存取被明確分享給它的頁面、資料庫或 wiki，這同時也是權限管理的方式。
- 搜尋沒結果時，先檢查頁面有沒有分享給 integration。
- 把知識庫整理成 wiki 再分享，管理起來比較省事。
- Instructions 和 OpenAPI schema 決定 GPT 怎麼用 Notion 的搜尋 API。

## 練習
1. 建一個 Internal Integration，只分享一個測試頁面，確認 GPT 只搜得到那一頁。
2. 在 Instructions 加一條規則，要求回答時附上來源頁面的標題。
3. 改 OpenAPI schema 裡搜尋請求的參數（例如篩選條件），觀察回傳結果的變化。
