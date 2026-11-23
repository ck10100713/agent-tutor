---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_jira.ipynb
---
# GPT Actions 範例庫：Jira

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_jira.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_jira.ipynb)



## 這篇在做什麼
示範怎麼做一個連到 Jira Cloud 的 GPT Action，讓使用者用自然語言讀寫某個專案裡的 issue。內容包含 Custom GPT 的 Instructions、OpenAPI schema，以及 Atlassian 的 OAuth 2.0 設定。

## 學完你會
- 在 Atlassian Developer Console 建一個 OAuth 2.0 (3LO) 應用，設定 Jira 的讀寫 scope。
- 把 Instructions 和 OpenAPI schema 貼到 Custom GPT，並正確填入 `<CLOUD_ID>`。
- 在 ChatGPT 填好 OAuth 欄位，再把 callback URL 回填到 Atlassian。

## 開跑前
- 需要一個 Atlassian Cloud（Jira）帳號，並有權限在 [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/) 建立應用。
- 需要能建立 Custom GPT 的 ChatGPT 帳號。



## 簡介

這一頁是給要為特定應用開發 GPT Action 的開發者看的說明和指南。開始前，請先看過下面這些資料：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions 範例庫簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零打造 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 Jira，也就是 Atlassian 的專案與工單管理工具。這個 action 以使用者自己的身分運作，可以讀寫指定專案裡的 issue。

### 價值與商業使用情境

**價值**：使用者可以用 ChatGPT 的自然語言能力，直接連到 Jira Cloud

**使用情境範例**： 
- 使用者載入某個專案最近的 issue，請 ChatGPT 提供解決方案
- 使用者下指令讓 ChatGPT 建立、修改 issue 和 sub-task，並指派給特定人員

## 應用程式資訊

### 應用程式重要連結

開始前先看看這些連結：
- 應用程式網站：https://<YOUR_SUBDOMAIN>.atlassian.net/jira
- 應用程式 API 文件：https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/
- 應用程式 OAuth 2.0 文件：https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/

### 應用程式前置需求

開始前，先在應用程式環境完成下面的步驟：
- 確認你有權限在 [Atlassian Cloud Developer Console](https://developer.atlassian.com/console/myapps/) 建立應用

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有疑問的話，看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started) 會有更詳細的說明。

```python
**Context**: you are specialized GPT designed to create and edit issues through API connections to Jira Cloud. This GPT can create, read, and edit project issues based on user instructions.

**Instructions**:
- When asked to perform a task, use the available actions via the api.atlassian.com API.
- When asked to create an issue, use the user's input to synthesize a summary and description and file the issue in JIRA.
- When asked to create a subtask, assume the project key and parent issue key of the currently discussed issue. Clarify with if this context is not available.
- When asked to assign an issue or task to the user, first use jql to query the current user's profile and use this account as the assignee. 
- Ask for clarification when needed to ensure accuracy and completeness in fulfilling user requests.
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有疑問的話，看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started) 會有更詳細的說明。

*注意：把 url 裡的佔位符 <CLOUD_ID> 換成你雲端環境專屬的 ID。可以到 https://<YOUR_SUBDOMAIN>.atlassian.net/_edge/tenant_info 查到這個值*


```python
openapi: 3.1.0
info:
  title: Jira API
  description: API for interacting with Jira issues and sub-tasks.
  version: 1.0.0
servers:
  - url: https://api.atlassian.com/ex/jira/<CLOUD_ID>/rest/api/3
    description: Jira Cloud API
components:
  securitySchemes:
    OAuth2:
      type: oauth2
      flows:
        authorizationCode:
          authorizationUrl: https://auth.atlassian.com/authorize
          tokenUrl: https://auth.atlassian.com/oauth/token
          scopes:
            read:jira-user: Read Jira user information
            read:jira-work: Read Jira work data
            write:jira-work: Write Jira work data
  schemas:
    Issue:
      type: object
      properties:
        id:
          type: string
        key:
          type: string
        fields:
          type: object
          properties:
            summary:
              type: string
            description:
              type: string
            issuetype:
              type: object
              properties:
                name:
                  type: string
paths:
  /search:
    get:
      operationId: getIssues
      summary: Retrieve a list of issues
      parameters:
        - name: jql
          in: query
          required: false
          schema:
            type: string
        - name: startAt
          in: query
          required: false
          schema:
            type: integer
        - name: maxResults
          in: query
          required: false
          schema:
            type: integer
      responses:
        '200':
          description: A list of issues
          content:
            application/json:
              schema:
                type: object
                properties:
                  issues:
                    type: array
                    items:
                      $ref: '#/components/schemas/Issue'
  /issue:
    post:
      operationId: createIssue
      summary: Create a new issue
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                fields:
                  type: object
                  properties:
                    project:
                      type: object
                      properties:
                        key:
                          type: string
                    summary:
                      type: string
                    description:
                      type: string
                    issuetype:
                      type: object
                      properties:
                        name:
                          type: string
      responses:
        '201':
          description: Issue created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Issue'
  /issue/{issueIdOrKey}:
    get:
      operationId: getIssue
      summary: Retrieve a specific issue
      parameters:
        - name: issueIdOrKey
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Issue details
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Issue'
    put:
      operationId: updateIssue
      summary: Update an existing issue
      parameters:
        - name: issueIdOrKey
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                fields:
                  type: object
                  properties:
                    summary:
                      type: string
                    description:
                      type: string
                    issuetype:
                      type: object
                      properties:
                        name:
                          type: string
      responses:
        '204':
          description: Issue updated successfully
  /issue:
    post:
      operationId: createSubTask
      summary: Create a sub-task for an issue
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                fields:
                  type: object
                  properties:
                    project:
                      type: object
                      properties:
                        key:
                          type: string
                    parent:
                      type: object
                      properties:
                        key:
                          type: string
                    summary:
                      type: string
                    description:
                      type: string
                    issuetype:
                      type: object
                      properties:
                        name:
                          type: string
      responses:
        '201':
          description: Sub-task created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Issue'
security:
  - OAuth2:
      - read:jira-user
      - read:jira-work
      - write:jira-work
```

## 驗證設定說明

下面說明怎麼設定 Jira 的驗證。有疑問的話，看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started) 會有更詳細的說明。


### Jira 步驟

1. <b>建立應用</b>：第一步是在 Jira 建一個新應用，用來跟 ChatGPT 整合。到 [Atlassian Developer Console](https://developer.atlassian.com/console/myapps/)，點 **Create**，選 **OAuth 2.0 Integration**。 

![gptactions_jira_devconsole.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_devconsole.png)

接著輸入整合的名稱，點 **Create**。

![gptactions_jira_newapplication.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_newapplication.png)

2. <b>設定權限</b>：接下來要給應用所需的權限。在新應用裡，從側邊欄打開 **Permissions** 選單，找到 **Jira API**，點 **Add**，再點 **Configure**。

![gptactions_jira_permissions.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_permissions.png)

需要哪些權限取決於這個 GPT 要做什麼。這裡我們要讀寫 Jira issue，所以點 **Edit Scopes**，在 **Jira platform REST API** 底下選這幾個 scope：

- read:jira-work
- write:jira-work
- read:jira-user

選好後點 **Save**

![gptactions_jira_scopes.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_scopes.png)

3. <b>設定佔位用的 Callback URL</b>：要取得 **Client ID** 和 **Secret**（用來讓 ChatGPT 和 Jira 之間安全驗證），得先加一個佔位用的 callback URL。做法是點側邊欄的 **Authorization**，再點 **OAuth 2.0 (3LO)** 旁邊的 **Configure**。在這裡隨便輸入一個佔位 URL，點 **Save Changes**。


![gptactions_jira_placeholder.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_placeholder.png)

4. <b>應用的 Client ID/Secret</b>：接著找出 **Client ID** 和 **Secret**。點側邊欄的 **Settings**，往下捲到 **Authentication Details** 就能看到。 

      這個頁面先不要關，下一階段的設定會用到這些值！

![gptactions_jira_clientsecret.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_clientsecret.png)

### 在 ChatGPT 裡

在 ChatGPT 點 "Authentication"，選 **"OAuth"**，填入下面的資訊。 

- **Client ID**：Jira 設定 **步驟 3** 取得的 **Client ID**
- **Client Secret**：Jira 設定 **步驟 3** 取得的 **Secret**
- **Authorization URL**：https://auth.atlassian.com/authorize
- **Token URL**：https://auth.atlassian.com/oauth/token
- **Scope**：read:jira-work write:jira-work read:jira-user 
- **Token Exchange Method**：Default (POST Request)

### Action 設定後的步驟

在 ChatGPT 設好驗證之後，照下面的步驟回到應用程式完成 Action 的設定。

- 從 GPT Action 複製 callback URL

![gptactions_jira_redirect.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_redirect.png)

- 在 Atlassian Developer Console 的應用裡，進到 **Authorization** 側邊欄分頁，點 **OAuth 2.0 (3L0)** 旁邊的 **Configure**，把你的 callback URL 加到 **Callback URL**


![gptactions_jira_callback.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_jira_callback.png)

### FAQ 與疑難排解

- **Callback URL 錯誤**：如果在 ChatGPT 看到 callback URL 錯誤，請再確認 Callback URL 的值，因為驗證設定有改動時，它偶爾會變


*有想要我們優先處理的整合嗎？我們的整合有錯誤嗎？歡迎在 github 提 PR 或 issue，我們會去看。*


## 重點整理
- GPT Action 由三塊組成：Custom GPT 的 Instructions、OpenAPI schema、驗證設定。
- Jira 用 OAuth 2.0 (3LO)，scope 決定 GPT 能讀寫什麼，這裡只開 issue 與使用者的讀寫。
- OpenAPI schema 的 URL 要帶自己的 `<CLOUD_ID>`，從 tenant_info 查得到。
- 設定順序有個來回：先用佔位 callback URL 拿到 Client ID/Secret，ChatGPT 設完再把真正的 callback URL 回填 Atlassian。

## 練習
1. 查出你自己的 `<CLOUD_ID>`，換進頁面的 OpenAPI schema 的 url。
2. 把 Custom GPT Instructions 改成只允許查詢、不允許建立 issue，並對應移除 `write:jira-work` scope。
3. 在 OpenAPI schema 裡多加一個你需要的 Jira REST 端點（例如查詢單一 issue 的 comments），讓 GPT 能呼叫它。
