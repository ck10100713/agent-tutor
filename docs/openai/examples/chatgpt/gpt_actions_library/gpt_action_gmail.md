---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_gmail.ipynb
---

# GPT Actions 函式庫：Gmail

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_gmail.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_gmail.ipynb)

## 這篇在做什麼

教你替 Custom GPT 建一個連到 Gmail 的 GPT Action。這個 Action 接 Gmail API，可以在授權的帳號裡讀取、寄送、列出信件和建立草稿。內容包含 GPT 的 instructions、OpenAPI schema 和 Google OAuth 設定。

## 學完你會

- 在 Google Cloud 啟用 Gmail API 並建立 OAuth 憑證
- 把 instructions 與 OpenAPI schema 貼進 Custom GPT 的 Actions
- 在 ChatGPT 設定 OAuth，並把 callback URL 填回 Google Cloud

## 開跑前

- 需要 Google Cloud 帳號，並已啟用 Gmail API
- 應用程式的 Publishing Status 若是 Testing，要把使用者加進測試名單
- 需要 ChatGPT 能建立 Custom GPT 的方案


## 簡介

這一頁是給開發者的指南，說明怎麼替特定應用程式建立 GPT Action。開始前請先看過下面這些資料：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零開始建立 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 Google Gmail。它連接 Google Gmail API，可以在授權的帳號裡讀取、寄送、列出和起草電子郵件。

### 價值與商業使用範例

**價值**：Gmail GPT 能精簡溝通流程、提升客戶互動，並讓資源配置更有效率。

**使用範例**：
- 管理內部溝通：摘要冗長的信件，並依先前的信件往來起草回覆。
- 客服人員可以依公司的溝通準則、語氣和風格，即時回覆客戶。
- 搭配其他 GPT（例如資料分析 GPT），再請它把彙整後的分析用 email 起草或寄出。

## 應用程式資訊

### 應用程式重要連結

開始前先看看這些連結：
- 應用程式網站：https://mail.google.com/mail/u/0/#inbox
- 應用程式 API 文件：https://developers.google.com/gmail/api/guides

### 應用程式前置條件

開始前，請確認你有 Google Cloud 帳號，並已啟用 Gmail API：
- 建立 Google Cloud 專案
- 在 Google API Library 啟用 Gmail API
- 如果應用程式的「Publishing Status」是「Testing」，要確認使用者已加入你的應用程式

## ChatGPT 步驟

### Custom GPT Instructions

建立好 Custom GPT 後，把下面的文字複製到 Instructions 欄位。有疑問可以看[入門範例](https://platform.openai.com/docs/actions/getting-started)，裡面更詳細說明這一步。

```python
**Context**
Act as an email assistant designed to enhance user interaction with emails in various ways. This GPT can assist with productivity by summarizing emails/threads, identifying next steps/follow-ups, drafting or sending pre-written responses, and programmatically interacting with third-party tools (e.g., Notion to-dos, Slack channel summaries, data extraction for responses). This GPT has full scope access to the GMAIL OAuth 2.0 API, capable of reading, composing, sending, and permanently deleting emails from Gmail.

**Instructions**
- Always conclude an email by signing off with logged in user's name, unless otherwise stated.
- Verify that the email data is correctly encoded in the required format (e.g., base64 for the message body).
- Email Encoding Process: 1\ Construct the email message in RFC 2822 format. 2\ Base64 encode the email message. 3\Send the encoded message using the API.
- If not specified, sign all emails with the user name.
- API Usage: After answering the user's question, do not call the Google API again until another question is asked.
- All emails created, draft or sent, should be in plain text.
- Ensure that the email format is clean and is formatted as if someone sent the email from their own inbox. Once a draft is created or email sent, display a message to the user confirming that the draft is ready or the email is sent.
- Check that the "to" email address is valid and in the correct format. It should be in the format "recipient@example.com". 
- Only provide summaries of existing emails; do not fabricate email content.
- Professionalism: Behave professionally, providing clear and concise responses.
- Clarification: Ask for clarification when needed to ensure accuracy and completeness in fulfilling user requests.
- Privacy and Security: Respect user privacy and handle all data securely.
```

### OpenAPI Schema

建立好 Custom GPT 後，把下面的文字複製到 Actions 欄位。有疑問可以看[入門範例](https://platform.openai.com/docs/actions/getting-started)，裡面更詳細說明這一步。

```python
openapi: 3.1.0

info:
  title: Gmail Email API
  version: 1.0.0
  description: API to read, write, and send emails in a Gmail account.

servers:
  - url: https://gmail.googleapis.com

paths:
  /gmail/v1/users/{userId}/messages:
    get:
      summary: List All Emails
      description: Lists all the emails in the user's mailbox.
      operationId: listAllEmails
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
        - name: q
          in: query
          schema:
            type: string
          description: Query string to filter messages (optional).
        - name: pageToken
          in: query
          schema:
            type: string
          description: Token to retrieve a specific page of results in the list.
        - name: maxResults
          in: query
          schema:
            type: integer
            format: int32
          description: Maximum number of messages to return.
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MessageList'
        '400':
          description: Bad Request
        '401':
          description: Unauthorized
        '403':
          description: Forbidden
        '404':
          description: Not Found
        '500':
          description: Internal Server Error

  /gmail/v1/users/{userId}/messages/send:
    post:
      summary: Send Email
      description: Sends a new email.
      operationId: sendEmail
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Message'
      responses:
        '200':
          description: Email sent successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Message'
        '400':
          description: Bad Request
        '401':
          description: Unauthorized
        '403':
          description: Forbidden
        '500':
          description: Internal Server Error

  /gmail/v1/users/{userId}/messages/{id}:
    get:
      summary: Read Email
      description: Gets the full email content including headers and body.
      operationId: readEmail
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
        - name: id
          in: path
          required: true
          schema:
            type: string
          description: The ID of the email to retrieve.
      responses:
        '200':
          description: Successful response
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FullMessage'
        '400':
          description: Bad Request
        '401':
          description: Unauthorized
        '403':
          description: Forbidden
        '404':
          description: Not Found
        '500':
          description: Internal Server Error

  /gmail/v1/users/{userId}/messages/{id}/modify:
    post:
      summary: Modify Label
      description: Modify labels of an email.
      operationId: modifyLabels
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
        - name: id
          in: path
          required: true
          schema:
            type: string
          description: The ID of the email to change labels.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/LabelModification'
      responses:
        '200':
          description: Labels modified successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Message'
        '400':
          description: Bad Request
        '401':
          description: Unauthorized
        '403':
          description: Forbidden
        '500':
          description: Internal Server Error

  /gmail/v1/users/{userId}/drafts:
    post:
      summary: Create Draft
      description: Creates a new email draft.
      operationId: createDraft
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Draft'
      responses:
        '200':
          description: Draft created successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Draft'
        '400':
          description: Bad Request
        '401':
          description: Unauthorized
        '403':
          description: Forbidden
        '500':
          description: Internal Server Error

  /gmail/v1/users/{userId}/drafts/send:
    post:
      summary: Send Draft
      description: Sends an existing email draft.
      operationId: sendDraft
      parameters:
        - name: userId
          in: path
          required: true
          schema:
            type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SendDraftRequest'
      responses:
        '200':
          description: Draft sent successfully
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Message'
        '400':
          description: Bad Request
        '401':
          description: Unauthorized
        '403':
          description: Forbidden
        '500':
          description: Internal Server Error

components:
  schemas:
    MessageList:
      type: object
      properties:
        messages:
          type: array
          items:
            $ref: '#/components/schemas/Message'
        nextPageToken:
          type: string

    Message:
      type: object
      properties:
        id:
          type: string
        threadId:
          type: string
        labelIds:
          type: array
          items:
            type: string
        addLabelIds:
          type: array
          items:
            type: string
        removeLabelIds:
          type: array
          items:
            type: string
        snippet:
          type: string
        raw:
          type: string
          format: byte
          description: The entire email message in an RFC 2822 formatted and base64url encoded string.

    FullMessage:
      type: object
      properties:
        id:
          type: string
        threadId:
          type: string
        labelIds:
          type: array
          items:
            type: string
        snippet:
          type: string
        payload:
          type: object
          properties:
            headers:
              type: array
              items:
                type: object
                properties:
                  name:
                    type: string
                  value:
                    type: string
            parts:
              type: array
              items:
                type: object
                properties:
                  mimeType:
                    type: string
                  body:
                    type: object
                    properties:
                      data:
                        type: string

    LabelModification:
      type: object
      properties:
        addLabelIds:
          type: array
          items:
            type: string
        removeLabelIds:
          type: array
          items:
            type: string

    Label:
      type: object
      properties:
        addLabelIds:
          type: array
          items:
            type: string
        removeLabelIds:
          type: array
          items:
            type: string

    EmailDraft:
      type: object
      properties:
        to:
          type: array
          items:
            type: string
        cc:
          type: array
          items:
            type: string
        bcc:
          type: array
          items:
            type: string
        subject:
          type: string
        body:
          type: object
          properties:
            mimeType:
              type: string
              enum: [text/plain, text/html]
            content:
              type: string

    Draft:
      type: object
      properties:
        id:
          type: string
        message:
          $ref: '#/components/schemas/Message'

    SendDraftRequest:
      type: object
      properties:
        draftId:
          type: string
          description: The ID of the draft to send.
        userId:
          type: string
          description: The user's email address. Use "me" to indicate the authenticated user.
```

## 認證設定

下面說明怎麼設定這個第三方應用程式的認證。有疑問可以看[入門範例](https://platform.openai.com/docs/actions/getting-started)，裡面更詳細說明這一步。

### Action 之前的步驟

在 ChatGPT 設定認證之前，先在應用程式裡完成下列步驟。


- 前往 Google Cloud Console
- 進入 API & Services > Credentials

![gptactions_BigQuery_auth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_Gmail_enableAPIs.png)

![gptactions_BigQuery_auth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_Gmail_gmailApiTile.png)

- 建立新的 OAuth 憑證（或使用既有的）

![gptactions_BigQuery_auth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_Gmail_apikey.png)

- 找到你的 OAuth Client ID 與 Client Secret，並安全保存這兩個值（見下方截圖）

![gptactions_BigQuery_auth.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_Gmail_clientidsecret.png)

### 在 ChatGPT 裡設定

在 ChatGPT 點「Authentication」並選擇 **"OAuth"**，填入下面的資訊。

- **Client ID**：用上面步驟取得的 Client ID
- **Client Secret**：用上面步驟取得的 Client Secret
- **Authorization URL**：https://accounts.google.com/o/oauth2/auth
- **Token URL**：https://oauth2.googleapis.com/token
- **Scope**：https://mail.google.com/
- **Token**：Default (POST)

### Action 之後的步驟

在 ChatGPT 設好認證後，回到應用程式完成下面的步驟，Action 才算設定完成。

- 從 GPT Action 複製 callback URL
- 把你的 callback URL 加到「Authorized redirect URIs」（見上方截圖）


### FAQ 與疑難排解

- *Callback URL 錯誤：*如果 ChatGPT 出現 callback URL 錯誤，請仔細對照上面的截圖。你必須把 callback URL 直接加到 GCP，Action 才能正確認證
- *Schema 呼叫到錯的專案或資料集：*如果 ChatGPT 呼叫了錯的專案或資料集，可以更新 instructions，更明確地（a）指定要呼叫哪個專案或資料集，或（b）要求使用者在執行查詢前先提供這些細節

*有想要我們優先處理的整合嗎？我們的整合有錯誤嗎？歡迎到 GitHub 提 PR 或 issue，我們會處理。*


## 重點整理

- 一個 GPT Action 由三塊組成：Custom GPT instructions、OpenAPI schema、認證設定。
- Gmail Action 走 OAuth，Client ID 和 Secret 來自 Google Cloud 的憑證頁。
- callback URL 要從 ChatGPT 複製後貼回 GCP 的 Authorized redirect URIs，否則認證會失敗。
- 應用程式若是 Testing 狀態，使用者要先加進測試名單。
- instructions 寫得越明確，模型越不容易呼叫錯目標。

## 練習

1. 檢查 Scope 欄位，想想如果只需要讀信，能不能改成範圍更小的 Gmail scope，並試著替換。
2. 在 Custom GPT instructions 加一條規則，要求寄信前一律先建立草稿並請使用者確認。
3. 在 OpenAPI schema 裡找出列出信件的 operation，替它加上依寄件人過濾的查詢參數，並更新 instructions 讓 GPT 會用它。
