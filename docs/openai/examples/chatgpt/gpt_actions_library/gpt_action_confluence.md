---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_confluence.ipynb
---

# GPT Actions 範例庫：Confluence

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_confluence.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_confluence.ipynb)



## 這篇在做什麼
示範怎麼做一個連到 Confluence 的 GPT Action。使用者問問題，GPT 會去搜尋相關的 Confluence space 和頁面，整理出答案。這篇只做讀取和搜尋，不改 Confluence 內容。

## 學完你會
- 在 Atlassian Developer Portal 建立 OAuth 2.0 app，並設定 scope 和 callback URL。
- 把 Custom GPT 的 Instructions 和 OpenAPI schema 貼到 GPT 裡，讓它能查 Confluence。
- 在 ChatGPT 填入 OAuth 設定（Client ID、Authorization URL、Token URL、Scope），並排解 callback URL 錯誤、action 迴圈等常見問題。

## 開跑前
- 需要 ChatGPT 能建立 Custom GPT 的帳號。
- 需要 Atlassian 帳號，且有權限在 Atlassian Developer Portal 建立 App。

## 簡介

這一頁是給開發者的說明，教你替特定應用程式做 GPT Action。開始之前，建議先看過下面這些資料：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零打造 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 **Confluence**，也就是 Atlassian 的協作與文件平台。它會接收使用者的問題，掃描相關的 Confluence space 和頁面蒐集資訊，再組出答案。這份教學不處理從 ChatGPT 直接更新 Confluence 內容，不過加上額外的 Action 和 scope 技術上是做得到的。

### 價值與商業情境範例

**價值**

使用者可以用 ChatGPT 的自然語言能力直接連到 Confluence，順暢地查詢組織的知識庫。

**情境範例**
- **知識工作者**：輕鬆從 Confluence 頁面和 space 取得資訊，回答問題或蒐集報告、簡報的資料。
- **專案經理**：不用手動翻頁面，就能快速取得存在 Confluence 的專案文件和進度。
- **客服團隊**：從 Confluence 知識庫撈出相關資訊，正確又即時地回覆客戶問題。
- **所有使用者**：更清楚公司內的文件、政策和流程，促進協作與知識分享。

## 應用程式資訊

### 應用程式重要連結

開始前先看看這些連結：
- 應用程式網站：https://developer.atlassian.com/console/myapps/ 
- 應用程式 API 文件：https://developer.atlassian.com/cloud/confluence/rest/v2/intro/#about

### 應用程式前置條件

開始前，請先在應用程式環境完成下面的事：
- 確認你有權限在 Atlassian Developer Portal 建立 App
- 決定你要讓 GPT 做哪些操作（搜尋、讀取、編輯等）

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有疑問可以看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
You are a "Confluence Savant", equipped with the ability to search our company's Product Wiki in Confluence to answer product-related questions.

You must ALWAYS perform the "getAccessibleResources" Action first to get the "cloudid" value you will need in subsequent Actions.

Your job is to provide accurate and detailed responses by retrieving information from the Product Wiki. Your responses should be clear, concise, and directly address the question asked. You have the capability to execute an action named "performConfluenceSearch" that allows you to search for content within our Confluence Product Wiki using specific terms or phrases related to the user's question.

    - When you receive a query about product information, use the "performConfluenceSearch" action to retrieve relevant content from the Product Wiki. Formulate your search query based on the user's question, using specific keywords or phrases to find the most pertinent information.
    - Once you receive the search results, review the content to ensure it matches the user's query. If necessary, refine your search query to retrieve more accurate results.
    - Provide a response that synthesizes the information from the Product Wiki, clearly answering the user's question. Your response should be easy to understand and directly related to the query.
    - If the query is complex or requires clarification, ask follow-up questions to the user to refine your understanding and improve the accuracy of your search.
    - If the information needed to answer the question is not available in the Product Wiki, inform the user and guide them to where they might find the answer, such as contacting a specific department or person in the company.

    Here is an example of how you might respond to a query:

    User: "What are the latest features of our XYZ product?"
    You: "The latest features of the XYZ product, as detailed in our Product Wiki, include [feature 1], [feature 2], and [feature 3]. These features were added in the recent update to enhance [specific functionalities]. For more detailed information, you can refer to the Product Wiki page [link to the specific Confluence page]."

Remember, your goal is to provide helpful, accurate, and relevant information to the user's query by effectively leveraging the Confluence Product Wiki.
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有疑問可以看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
openapi: 3.1.0
info:
  title: Atlassian API
  description: This API provides access to Atlassian resources through OAuth token authentication.
  version: 1.0.0
servers:
  - url: https://api.atlassian.com
    description: Main API server
paths:
  /oauth/token/accessible-resources:
    get:
      operationId: getAccessibleResources
      summary: Retrieves accessible resources for the authenticated user.
      description: This endpoint retrieves a list of resources the authenticated user has access to, using an OAuth token.
      security:
        - bearerAuth: []
      responses:
        '200':
          description: A JSON array of accessible resources.
          content:
            application/json:
              schema: 
                $ref: '#/components/schemas/ResourceArray'
  /ex/confluence/{cloudid}/wiki/rest/api/search:
    get:
      operationId: performConfluenceSearch
      summary: Performs a search in Confluence based on a query.
      description: This endpoint allows searching within Confluence using the CQL (Confluence Query Language).
      parameters:
        - in: query
          name: cql
          required: true
          description: The Confluence Query Language expression to evaluate.
          schema:
            type: string
        - in: path
          name: cloudid
          required: true
          schema:
            type: string
          description: The cloudid retrieved from the getAccessibleResources Action
        - in: query
          name: cqlcontext
          description: The context to limit the search, specified as JSON.
          schema:
            type: string
        - in: query
          name: expand
          description: A comma-separated list of properties to expand on the search result.
          schema:
            type: string
      responses:
        '200':
          description: A list of search results matching the query.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SearchResults'
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    ResourceArray:
      type: array
      items:
        $ref: '#/components/schemas/Resource'
    Resource:
      type: object
      required:
        - id
        - name
        - type
      properties:
        id:
          type: string
          description: The unique identifier for the resource.
        name:
          type: string
          description: The name of the resource.
        type:
          type: string
          description: The type of the resource.
    SearchResults:
      type: object
      properties:
        results:
          type: array
          items:
            $ref: '#/components/schemas/SearchResult'
    SearchResult:
      type: object
      properties:
        id:
          type: string
          description: The unique identifier of the content.
        title:
          type: string
          description: The title of the content.
        type:
          type: string
          description: The type of the content (e.g., page, blog post).
        space:
          type: object
          properties:
            id:
              type: string
              description: The space ID where the content is located.
            name:
              type: string
              description: The name of the space.
```

## 驗證設定說明

下面是跟這個第三方應用程式設定驗證的步驟。有疑問可以看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started)。

### Action 設定前的步驟

在 ChatGPT 設定驗證之前，先到 Atlassian Developer portal 完成下面的步驟，建立你的 Confluence app：

1. 選擇 Create 下拉選單
2. 選 OAuth 2.0 integration
3. 取個名字、同意條款，按 Create
4. 在左側選單選 "Distribution"，按 “Edit”
5. 把選項改成 "Sharing"
6. 填完必填欄位，儲存
7. 在左側選單選 "Permissions"
8. 加入你要的 scope（例如 User identity API 和 Confluence API，這樣 app 才知道使用者能存取什麼、能從 Confluence 取什麼）
9. 在左側選單選 "Authorization"
10. 在 OAuth 2.0 那一列的 Action 下按 "Add"
11. 輸入 GPT 的 callback URL（注意：你可能得先填一個佔位值，等 GPT 裡的 Action 和 OAuth 建好、拿到最終的 callback URL 後再回來改）
12. 在左側選單選 "Settings"
13. 複製 Client ID 和 Secret，之後在 GPT 設定 OAuth 時使用


![confluence_gpt.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/confluence_gpt.png)

### 在 ChatGPT 裡設定

在 ChatGPT 點 "Authentication"，選 **"OAuth"**，填入下面的資訊。 

- **Client ID**：用上面步驟取得的 Client ID 
- **Client Secret**：用上面步驟取得的 Client Secret
- **Authorization URL**：https://auth.atlassian.com/authorize
- **Token URL**：https://auth.atlassian.com/oauth/token 
- **Scope**：read:confluence-content.all search:confluence
- **Token**：Default (POST)

### Action 設定後的步驟

在 ChatGPT 設定好驗證後，回到應用程式完成最後設定。

- 從 GPT Action 複製 callback URL
- 把 callback URL 加到 “Authorized redirect URIs”（參考上面的截圖） 


### FAQ 與疑難排解

- *Callback URL 錯誤：* 如果在 ChatGPT 看到 callback URL 錯誤，請仔細對照上面的截圖。你必須把 callback URL 直接加到 Confluence app 裡，action 才能正確驗證
- *Schema 呼叫了錯的 project 或 dataset：* 如果 ChatGPT 呼叫了錯的 project 或 dataset，可以更新 instructions，更明確地指定 (a) 要呼叫哪個 project / dataset，或 (b) 要求使用者在執行 query 前先提供這些細節
- *Action 一直迴圈：* 可能是沒有給 app 完成目標所需的 scope 或權限

*有想要我們優先支援的整合嗎？整合有錯誤嗎？歡迎到 GitHub 開 PR 或 issue，我們會看。*


## 重點整理
- GPT Action 由三塊組成：Instructions（告訴 GPT 怎麼用）、OpenAPI schema（定義能呼叫的 API）、Authentication（這裡用 OAuth 2.0）。
- OAuth 要兩邊對接：先在 Atlassian 建 app 拿到 Client ID 和 Secret，再把 GPT 產生的 callback URL 回填進 app。
- Scope 決定 GPT 能做什麼，這篇只給讀取和搜尋的 scope，所以不能改內容。
- Action 迴圈通常是 scope 不夠；呼叫錯對象則靠改 instructions 解決。

## 練習
1. 在 Custom GPT 的 Instructions 裡加一句，要求回答時一律附上 Confluence 頁面連結。
2. 把 Scope 欄位拿掉 `search:confluence`，測一次看 GPT 的行為會怎麼變，確認 scope 的作用。
3. 在 OpenAPI schema 裡加上一個只列出 space 的 endpoint，並在 Instructions 裡要求 GPT 先列 space 讓使用者選，再去搜尋。
