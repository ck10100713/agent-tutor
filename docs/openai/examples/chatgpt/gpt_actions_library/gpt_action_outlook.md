---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_outlook.ipynb
---
# GPT Actions 範例庫：Outlook

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_outlook.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_outlook.ipynb)



## 這篇在做什麼
示範怎麼做一個連到 Outlook 的 GPT Action，讓使用者用自然語言收發郵件、讀寫行事曆。內容包含 Custom GPT 的 Instructions、OpenAPI schema，以及 Azure 的 App Registration 和 OAuth 設定。

## 學完你會
- 在 Azure Portal 註冊 App、建立 client secret，並加上 Microsoft Graph 的 delegated 權限。
- 把 Instructions 和 OpenAPI schema 貼到 Custom GPT，在 ChatGPT 填好 OAuth 欄位（含 Tenant ID）。
- 把 GPT Action 的 callback URL 回填到 Azure 的 Redirect URI。

## 開跑前
- 需要 Azure 帳號，並有權限建立 [App Registration](https://portal.azure.com/?feature.tokencaching=true&feature.internalgraphapiversion=true#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)。
- 需要能建立 Custom GPT 的 ChatGPT 帳號。



## 簡介

這一頁是給要為特定應用開發 GPT Action 的開發者看的說明和指南。開始前，請先看過下面這些資料：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions 範例庫簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零打造 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 Outlook，也就是 Microsoft 的電子郵件與行事曆網路服務。這個 action 以使用者自己的身分運作，可以從 Outlook 寄信、取信，以及讀取、建立行事曆事件。

### 價值與商業使用情境

**價值**：使用者可以用 ChatGPT 的自然語言能力，直接連到 Outlook

**使用情境範例**： 
- 使用者查詢當天所有的會議，請 ChatGPT 總結這一天
- 使用者直接把 ChatGPT 的輸出寄信給某人

## 應用程式資訊

### 應用程式重要連結

開始前先看看這些連結：
- 應用程式網站：https://portal.azure.com/
- 應用程式 API 文件：https://learn.microsoft.com/en-us/graph/api/overview?view=graph-rest-1.0

### 應用程式前置需求

開始前，先在應用程式環境完成下面的步驟：
- 確認你有權限[在 Azure 設定 App Registration](https://portal.azure.com/?feature.tokencaching=true&feature.internalgraphapiversion=true#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有疑問的話，看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started) 會有更詳細的說明。

```python
**Context**: you are specialized GPT designed to manage emails and calendar events through API connections to Microsoft Outlook. This GPT can create, read, send, and alter emails and calendar events based on user instructions. It ensures efficient handling of communication and scheduling needs by leveraging Microsoft Graph API for seamless integration with Outlook services.

**Instructions**:
- When asked to perform a task, use the available actions via the microsoft.graph.com API.
- You should behave professionally and provide clear, concise responses.
- Offer assistance with tasks such as drafting emails, scheduling meetings, organising calendar events, and retrieving email or event details.
- Ask for clarification when needed to ensure accuracy and completeness in fulfilling user requests.
- Always conclude an email by signing off with logged in user's name which can be retrieved via the User.Read endpoint
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有疑問的話，看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started) 會有更詳細的說明。

```python
openapi: 3.1.0
info:
  title: Microsoft Graph API Integration
  version: 1.0.0
servers:
  - url: https://graph.microsoft.com/v1.0
components:
  securitySchemes:
    OAuth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token
          scopes:
            https://graph.microsoft.com/User.Read: Access current user profile
            https://graph.microsoft.com/Mail.Read: Read user mail
            https://graph.microsoft.com/Mail.Send: Send mail
            https://graph.microsoft.com/Calendars.ReadWrite: Read and write user calendars
  schemas:
    UserProfile:
      type: object
      properties:
        id:
          type: string
        displayName:
          type: string
        mail:
          type: string
    UserMessage:
      type: object
      properties:
        id:
          type: string
        subject:
          type: string
        bodyPreview:
          type: string
    CalendarEvent:
      type: object
      properties:
        id:
          type: string
        subject:
          type: string
        start:
          type: object
          properties:
            dateTime:
              type: string
            timeZone:
              type: string
        end:
          type: object
          properties:
            dateTime:
              type: string
            timeZone:
              type: string
    NewEvent:
      type: object
      properties:
        subject:
          type: string
        start:
          type: object
          properties:
            dateTime:
              type: string
            timeZone:
              type: string
        end:
          type: object
          properties:
            dateTime:
              type: string
            timeZone:
              type: string
        attendees:
          type: array
          items:
            type: object
            properties:
              emailAddress:
                type: object
                properties:
                  address:
                    type: string
                  name:
                    type: string
    SendMailRequest:
      type: object
      properties:
        message:
          type: object
          properties:
            subject:
              type: string
            body:
              type: object
              properties:
                contentType:
                  type: string
                content:
                  type: string
            toRecipients:
              type: array
              items:
                type: object
                properties:
                  emailAddress:
                    type: object
                    properties:
                      address:
                        type: string
security:
  - OAuth2: []
paths:
  /me:
    get:
      operationId: getUserProfile
      summary: Get the authenticated user's profile
      security:
        - OAuth2: []
      responses:
        '200':
          description: A user profile
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/UserProfile'
  /me/messages:
    get:
      operationId: getUserMessages
      summary: Get the authenticated user's messages
      security:
        - OAuth2: []
      parameters:
        - name: $top
          in: query
          required: false
          schema:
            type: integer
            default: 10
            description: Number of messages to return
        - name: $filter
          in: query
          required: false
          schema:
            type: string
            description: OData filter query to narrow results
        - name: $orderby
          in: query
          required: false
          schema:
            type: string
            description: OData order by query to sort results
      responses:
        '200':
          description: A list of user messages
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/UserMessage'
  /me/sendMail:
    post:
      operationId: sendUserMail
      summary: Send an email as the authenticated user
      security:
        - OAuth2: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SendMailRequest'
      responses:
        '202':
          description: Accepted
  /me/events:
    get:
      operationId: getUserCalendarEvents
      summary: Get the authenticated user's calendar events
      security:
        - OAuth2: []
      responses:
        '200':
          description: A list of calendar events
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/CalendarEvent'
    post:
      operationId: createUserCalendarEvent
      summary: Create a new calendar event for the authenticated user
      security:
        - OAuth2: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/NewEvent'
      responses:
        '201':
          description: Created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/CalendarEvent'
```

## 驗證設定說明

下面說明怎麼設定 Outlook 的驗證。有疑問的話，看 [Getting Started 範例](https://platform.openai.com/docs/actions/getting-started) 會有更詳細的說明。


### Azure 步驟

1. <b>App Registration</b>：第一步是在 [Azure Portal](https://portal.azure.com) 註冊一個新的 App registration，用來在我們的應用和 Azure Active Directory/Entra ID 之間整合 OAuth。給應用取一個合適的名稱，Redirect URI 先留空，之後會回來設定，然後儲存。

![gptactions_outlook_registerapplication.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_registerapplication.png)

2. <b>Certificate & Secrets</b>：接著要產生一個 client secret，讓 GPT 和 Azure 之間能安全通訊。在 App registration 裡，從側邊欄進到 <b>Certificate & secrets</b>

![gptactions_outlook_secrets.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_secrets.png)

點 New client secret，用想要的名稱和到期日建立一個新的 client secret。按儲存後會得到一個 Secret，供建立 GPT 時使用。務必把 **Value** 欄位存下來，因為它只有在建立時看得到，之後會用到！

![gptactions_outlook_secretvalue.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_secretvalue.png)

3. <b>API Permissions</b>：下一步是給整合所需的 scope，讓它能執行我們需要的動作。 
在 App registration 裡，從側邊欄進到 <b>Manage > API permissions</b>。 

![gptactions_outlook_permissions.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_permissions.png)

點 <b>Add a permission</b>，在打開的側邊選單選 <b>Microsoft graph > Delegated Permissions</b>。用搜尋列加入下面這些權限：
- Calendars.ReadWrite
- Mail.Read
- Mail.Send
- User.Read


![gptactions_outlook_permissionadd.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_permissionadd.png)

### 在 ChatGPT 裡

在 ChatGPT 點 "Authentication"，選 **"OAuth"**，填入下面的資訊。 

- **Client ID**：Azure 註冊的 App 的 Overview 頁面上，**Application (client) ID** 列出的值
- **Client Secret**：**Azure 步驟** 第 2 步存下來的 secret **Value**

下面兩個欄位，把 <Tenant_ID> 換成已註冊 App 的 Overview 頁面上 **Directory (tenant) ID** 列出的值

- **Authorization URL**：https://login.microsoftonline.com/<Tenant_ID>/oauth2/v2.0/authorize
- **Token URL**：https://login.microsoftonline.com/<Tenant_ID>/oauth2/v2.0/token
- **Scope**：https://graph.microsoft.com/User.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Calendars.ReadWrite 
- **Token Exchange Method**：Default (POST Request)

### Action 設定後的步驟

在 ChatGPT 設好驗證之後，照下面的步驟回到應用程式完成 Action 的設定。

- 從 GPT Action 複製 callback URL

![gptactions_outlook_callback.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_callback.png)

- 在 Azure 的 app 裡，進到 **Manage > Authentication** 分頁，點 **Add a platform**，選 **Web**，把你的 callback URL 加到 **Redirect URI**


![gptactions_outlook_redirectconfig.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_redirectconfig.png)
![gptactions_outlook_redirectinput.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_outlook_redirectinput.png)

### FAQ 與疑難排解

- **Callback URL 錯誤**：如果在 ChatGPT 看到 callback URL 錯誤，請再確認 Callback URL 的值，因為驗證設定有改動時，它偶爾會變


*有想要我們優先處理的整合嗎？我們的整合有錯誤嗎？歡迎在 github 提 PR 或 issue，我們會去看。*


## 重點整理
- GPT Action 由三塊組成：Custom GPT 的 Instructions、OpenAPI schema、驗證設定。
- Outlook 透過 Microsoft Graph 的 delegated 權限，以使用者身分存取信件和行事曆。
- OAuth 的 URL 要帶自己的 Tenant ID，client secret 的 Value 只在建立時看得到，要先存好。
- 設定有個來回：Redirect URI 先留空，等 ChatGPT 產生 callback URL 後再回填 Azure。

## 練習
1. 把你的 Tenant ID 填進頁面上 Authorization URL 和 Token URL 的 `<Tenant_ID>`。
2. 把 Scope 裡的 `Mail.Send` 拿掉（Azure 權限也對應移除），確認 GPT 就不能寄信了。
3. 在 OpenAPI schema 加一個 Microsoft Graph 的端點（例如列出行事曆事件的篩選條件），並更新 Instructions 讓 GPT 知道怎麼用。
