---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_salesforce.ipynb
---

# GPT Actions library：Salesforce

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_salesforce.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_salesforce.ipynb)



## 這篇在做什麼

教你替 Salesforce Service Cloud 建一個 GPT Action，讓使用者直接在 ChatGPT 裡查詢和更新 case。內容包含 Custom GPT 的 Instructions、OpenAPI schema，以及在 Salesforce 建 Connected App 並設定 OAuth 的完整步驟。

## 學完你會

- 把 Instructions 和 OpenAPI schema 貼進 Custom GPT，讓它能呼叫 Salesforce API。
- 在 Salesforce 建立 Connected App，設定好 OAuth 相關選項。
- 在 ChatGPT 填入 OAuth 資訊，並把 callback URL 回填到 Salesforce 完成驗證。

## 開跑前

- 需要有 Salesforce 帳號，且有權限建立 App。
- 需要能建立 Custom GPT 的 ChatGPT 帳號。

## 簡介

這一頁是給開發者的指引，說明怎麼替特定的應用程式建一個 GPT Action。開始之前，請先熟悉以下內容：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions/introduction)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 Salesforce，具體來說是 Salesforce Service Cloud。這個 Action 的 schema 讓使用者直接在 ChatGPT 裡抓取 case 資料並更新 case。為其他 Salesforce Cloud 產品建立 Action 時，Connected App 和驗證的設定方式一樣，只是需要不同的 API schema。

### 價值與商業使用情境範例

**價值**：使用者現在能用 ChatGPT 的自然語言能力直接連到 Salesforce

**使用情境範例**：
- 縮短對客戶的平均回應時間
- 縮短排查 case 或問題的時間
- 搭配 GPT 裡的知識和 instructions，讓回覆客戶的品牌語氣更一致

## 應用程式資訊

### 應用程式的重要連結

開始之前，先看看這些來自該應用程式的連結：
- [Create Lightning Apps in Salesforce](https://help.salesforce.com/s/articleView?id=sf.apps_lightning_create.htm&type=5)
- [OAuth Tokens and Scopes](https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_tokens_scopes.htm&type=5)
- [Salesforce API Docs](https://developer.salesforce.com/docs/apis)

### 應用程式的前置條件

開始之前，請先在你的應用程式環境完成以下步驟：
- 確認你有在 Salesforce 建立 App 的權限

## ChatGPT 的步驟

### Custom GPT Instructions

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有問題的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

```python
**Context**: Your purpose is to pull information from Service Cloud, and push updates to cases. A user is going to ask you a question and ask you to make updates.

**Instructions**:
1. When a user asks you to help them solve a case in Service Cloud, ask for the case number and pull the details for the case into the conversation using the getCaseDetailsFromNumber action.
2. If the user asks you to update the case details, use the action updateCaseStatus.

**Example**: 
User: Help me solve case 00001104 in Service Cloud.
```

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有問題的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

```python
openapi: 3.1.0
info:
  title: Salesforce Service Cloud Case Update API
  description: API for updating the status of Service Cloud tickets (cases) in Salesforce.
  version: 1.0.3
servers:
  - url: https://your_instance.my.salesforce.com
    description: Base URL for your Salesforce instance (replace 'your_instance' with your actual Salesforce domain)
paths:
  /services/data/v60.0/sobjects/Case/{CaseId}:
    patch:
      operationId: updateCaseStatus
      summary: Updates the status of a Service Cloud case
      description: Updates the status of a Service Cloud ticket based on the case ID number.
      parameters:
        - name: CaseId
          in: path
          required: true
          description: The ID of the case to update.
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                Status:
                  type: string
                  description: The new status of the case.
      responses:
        '204':
          description: Successfully updated the case status
        '400':
          description: Bad request - invalid input or case ID not found
        '401':
          description: Unauthorized - authentication required
        '404':
          description: Not Found - case ID does not exist
    delete:
      operationId: deleteCase
      summary: Deletes a Service Cloud case
      description: Deletes a Service Cloud ticket based on the case ID number.
      parameters:
        - name: CaseId
          in: path
          required: true
          description: The ID of the case to delete.
          schema:
            type: string
      responses:
        '204':
          description: Successfully deleted the case
        '400':
          description: Bad request - invalid case ID
        '401':
          description: Unauthorized - authentication required
        '404':
          description: Not Found - case ID does not exist
  /services/data/v60.0/query:
    get:
      operationId: getCaseDetailsFromNumber
      summary: Retrieves case details using a case number
      description: Retrieves the details of a Service Cloud case associated with a given case number.
      parameters:
        - name: q
          in: query
          required: true
          description: SOQL query string to find the Case details based on Case Number.
          schema:
            type: string
            example: "SELECT Id, CaseNumber, Status, Subject, Description FROM Case WHERE CaseNumber = '123456'"
      responses:
        '200':
          description: Successfully retrieved the case details
          content:
            application/json:
              schema:
                type: object
                properties:
                  totalSize:
                    type: integer
                  done:
                    type: boolean
                  records:
                    type: array
                    items:
                      type: object
                      properties:
                        Id:
                          type: string
                        CaseNumber:
                          type: string
                        Status:
                          type: string
                        Subject:
                          type: string
                        Description:
                          type: string
        '400':
          description: Bad request - invalid query
        '401':
          description: Unauthorized - authentication required
        '404':
          description: Not Found - case number does not exist
```

## 驗證設定說明

以下是設定這個第三方應用程式驗證的步驟。有問題的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

### Action 之前的步驟

在 ChatGPT 設定驗證之前，請先在應用程式裡做以下步驟。

1. 進入 Salesforce Setup

![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_setup.png)

2. 搜尋 “App Manager”


![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_manager.png)

3. 點 “New Connected App”
4. 輸入 Connected App 名稱
5. 輸入聯絡 email（你自己的 email）
6. 勾選啟用 OAuth settings
7. 填入 callback URL（先用佔位的，例如 https://chat.openai.com/aip//oauth/callback，之後在 ChatGPT 建好 Action 再更新） 


![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_oauth2.png)

8. 選 “Selected OAuth Scopes” 並給予適當權限。範圍請依你們內部的資安政策決定。 


![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_scope.png)

9. 確認以下選項都已勾選：
- Enable Client Credentials Flow
- Enable Authorization Code and Credentials FLow
- Enable Token Exchange Flow
10. 確認以下選項沒有勾選： 
- Require Proof Key for Code Exchange (PKCE) Extension for Supported Authorization Flows


![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_settings_condensed.png) 

11. 儲存你的 New Connected App
12. 在 “Consumer Key and Secret” 下點 “Manage Consumer Details”。用寄到你帳號 email 的驗證碼驗證身分，然後複製 key 和 secret。 
- Salesforce Consumer Key = ChatGPT Client ID
- Salesforce Consumer Secret = ChatGPT Client Secret


![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_credentials.png)

13. 回到 App 頁面
14. 點 “Manage” 
15. 點 “Edit Policies”
16. 在 OAuth Policies 底下，勾選 “Enable Token Exchange Flow”


![gptactions_salesforce.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gpt_actions_salesforce_token.png)

17. 按儲存

### 在 ChatGPT 裡

在 ChatGPT 點 "Authentication" 並選 **"OAuth"**，填入下列資訊。 

- **Client ID**：用前面步驟取得的 Client ID 
- **Client Secret**：用前面步驟取得的 Client Secret
- **Authorization URL**：https://[inserturlhere].my.salesforce.com/services/oauth2/authorize
- **Token URL**：https://[inserturlhere].my.salesforce.com/services/oauth2/token 
- **Scope**：full
- **Token**：Default (POST)

### Action 之後的步驟


在 ChatGPT 設定好驗證之後，照下面的步驟在應用程式裡完成 Action 的設定。

- 從 GPT Action 複製 callback URL
- 回到 Salesforce 的 Connected App，把你的 callback URL 加進去。


### FAQ 與疑難排解

- *Callback URL 錯誤：* 如果在 ChatGPT 看到 callback URL 錯誤，請仔細看上面的截圖。你需要把 callback URL 直接加到 Salesforce，Action 才能正確驗證
- *Internal Server Error：* 確認 Connected App 的 OAuth 設定裡，該勾的和不該勾的選項都正確 

*有哪些整合希望我們優先做？我們的整合有錯誤嗎？歡迎到 GitHub 提 PR 或 issue，我們會處理。*


## 重點整理

- GPT Action 由三塊組成：Custom GPT 的 Instructions、OpenAPI schema、驗證設定。
- 換成其他 Salesforce Cloud 產品時，Connected App 和驗證不用變，只要換 API schema。
- Salesforce 的 Consumer Key 和 Secret 就是 ChatGPT 的 Client ID 和 Client Secret。
- OAuth 選項要勾對，而且 PKCE 要關掉，否則會出 Internal Server Error。
- callback URL 要等 ChatGPT 產生後，再回填到 Salesforce。

## 練習

1. 把 Instructions 裡的回覆語氣規則改成你們公司的風格，測試 GPT 回覆 case 的口吻有沒有變。
2. 在 OpenAPI schema 裡限制只保留查詢 case 的 endpoint，移除更新的，確認 GPT 就不能改 case 了。
3. 故意不要把 callback URL 填回 Salesforce，重現 callback URL 錯誤，再修好它。
