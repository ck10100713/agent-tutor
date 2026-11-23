---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function.ipynb
---
# GPT Actions library (Middleware) - Azure Functions

> 原文：[examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function.ipynb)



## 這篇在做什麼

教你在 Azure Portal 建一個有 OAuth 保護的 Azure Function，當作 GPT Action 跟其他應用程式之間的 middleware。內容包含建立 Function App、設定 Entra 驗證、用 Postman 測試，最後接上 Custom GPT。

## 學完你會

- 在 Azure Portal 建出 HTTP trigger 的 Azure Function，並用 Easy Auth 加上 Microsoft 登入
- 取得並整理 `CLIENT_ID`、`TENANT_ID`、`SCOPE`、secret，用 Postman 的 Authorization Code 流程測通
- 把 Function 的 OpenAPI spec 貼進 GPT Actions，設定 OAuth 並補上 callback URI

## 開跑前

- 需要 Azure Portal 帳號，且有權限建立 Azure Function App 和 Entra App Registration
- 部分步驟需要 Azure 管理員做 Grant Admin Consent
- 測試用 Postman



## 簡介

這一頁是給開發者看的，教你做 middleware，把 GPT Action 接到特定應用程式。開始之前，先看過下面這些：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 概述怎麼建 **Azure Function**，也就是 Microsoft 雲端的 function 建置服務。這份文件帶你設定一個有 OAuth 保護的 Azure Function，連到 GPT Action，也連到一個範例應用程式。

### 價值與業務情境

**價值**：使用者可以用 ChatGPT 的自然語言能力直接連到 Azure Function，有幾種好處：

- GPT Actions 有 10 萬字元限制：可以用 middleware 先處理 API 回傳的文字。例如在 middleware 裡呼叫 OpenAI API 先做摘要，再回傳給 ChatGPT。
- 一般 action 都靠 SaaS API 回傳文字。你可以把廠商 API 的回應轉成容易消化的文字，結構化和非結構化資料都能處理。
- 可以回傳檔案，不只是文字。例如把 CSV 檔拿出來做資料分析，或帶回 PDF 檔，ChatGPT 會把它當成上傳的檔案處理。


**範例情境**：
- 使用者要查 Sharepoint 的檔案，但 ChatGPT 跟 Sharepoint 之間需要一個 middleware app
- 使用者在 Azure function 裡串了好幾個步驟，想用 ChatGPT 觸發整個流程

## 應用程式資訊

### 重要連結

開始前先看這些連結：
- Application Website: https://learn.microsoft.com/en-us/azure/azure-functions/
- Application API Documentation: https://learn.microsoft.com/en-us/azure/azure-functions/functions-reference/

### 前置條件

開始前，先在你的環境準備好：
- 有 Azure Portal，並有權限建立 Azure Function App 和 Azure Entra App Registration

## 應用程式設定

### 安裝 app

左邊的文件目錄有 Azure Functions 支援的語言和部署方式，可以看[這裡](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview?pivots=programming-language-csharp)。 

#### 選項 1：用 VSCode

用 VSCode 部署的方式見 Microsoft 的[文件](https://learn.microsoft.com/en-us/azure/azure-functions/functions-develop-vs-code?tabs=node-v4,python-v2,isolated-process\&pivots=programming-language-javascript)。熟悉這種方式的話可以直接用。 


#### 選項 2：直接用 Azure Portal

用 Azure portal 部署的方式見[這份文件](https://learn.microsoft.com/en-us/azure/azure-functions/functions-create-function-app-portal?pivots=programming-language-javascript)。這裡一步一步帶你做一遍。


##### 第 1 部分：建立 Function

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/create_function_app.png)

1. 建立 [Azure Function app](https://learn.microsoft.com/en-us/azure/azure-functions/functions-overview?pivots=programming-language-csharp)。我用下面的設定，你可以用自己習慣的。注意不是每個語言 / 作業系統都能直接在 console 編輯 function，我選的組合可以。我其他都用預設值，只做了下面的選擇。這組設定可以直接用在 SharePoint Node.js 方案，見[這裡](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc)和[這裡](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_text)。 

   1. Basics

      1. _Do you want to deploy code or container image?:_  **Code**

      2. _Runtime stack:_ **Node.js**

      3. _Operating system:_ **Windows**

   2. Networking

      1. _Enable public access_: **on (need this on to connect to the GPT)**

2. 做完後會到 “Deployments” 頁面。部署完成（幾分鐘而已）後，點 **“Go to Resource”** 回到 Function App

  > 第一次可能會出錯，再按一次 create 通常就會成功。 

##### 第 2 部分：設定驗證

3. 在 Azure Function App 左邊選單，點 **Settings** 底下的 **Authentication**。 

   1. Add identity provider

   2. identity provider 選 **Microsoft**。 

   3. tenant type 選 **Workforce**

   4. **Create a new application。**用現有的 application 步驟也差不多，但新建比較簡單，因為它會透過 “Easy Auth” 自動設好 callback URL 並開放 API。詳情見[這裡](https://learn.microsoft.com/en-us/azure/app-service/overview-authentication-authorization)。

   5. 這頁其他設定維持預設，也可以依你們內部規範調整。

   6. 在 **permissions** 分頁，點 **Add Permission**，加入 **Files.Read.All** 和 **Sites.ReadAll**，再按 **Add。**這讓 application 能讀檔案，使用 Microsoft Graph Search API 時需要。如果你不是做 SharePoint 方案（見[這裡](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc)和[這裡](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_text)），可以跳過。

4. 建好後，**點進剛建立的 enterprise application**（也就是離開 Function App 頁面，進到剛建的 Enterprise Application）**。**接著要再給它一個權限，讓它能模擬登入應用程式的使用者來執行 Azure Function。詳情見[這裡](https://learn.microsoft.com/en-us/azure/app-service/configure-authentication-provider-aad?tabs=workforce-tenant)。

   1. 在主頁點 “**View API Permissions”**

   2. 在 **APIs my organization uses** 搜尋 **Microsoft Azure App Service**，找到 **user\_impersonation** 

   3. 加入後，需要 Azure Portal 的 Admin 來 **Grant Admin Consent。**

5) **在那個 enterprise application 裡**，點左邊 **Manage** 底下的 **“Expose an API”**，用 **Copy to Clipboard** 按鈕複製建好的 **scope**。scope 長得像 “api://\<insert-uuid>/user\_impersonation”。**存起來之後當作** `SCOPE`**。**

6) 點左邊 **Manage** 底下的 **“Authentication”**

   1. 在 **Web** 區塊會看到已自動加入一個 callback URI。再加上測試用的 Postman redirect URI (<https://oauth.pstmn.io/v1/callback>)。

7) 左邊選 **Overview**。複製 **application (client) ID** 和 **directory (tenant) ID**，**存起來當作** `CLIENT_ID` **和** `TENANT_ID`**。**

##### 第 3 部分：建立測試 Function

8. 回首頁，再回到你的 **Function App。**

9. 點 **Create Function。**這個範例我直接在 portal 開發，你也可以用 VSCode 或其他 IDE。

   1. 選 **HTTP trigger**

   2. **Authorization Level** 可以選任何 key 類型。

      1. 注意第一次可能會報錯，但 Function 多半已經建好了，重新整理頁面確認。

10. 點進剛建好的 function（可能要按 refresh 才看得到）。點 **Get Function URL** 並存起來，用 Postman 測試。之後貼進 GPT 時，建立 OpenAPI spec 也會用到。 

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/get_function_url.png)

11. 回到 function app，點 **Configuration。**顯示 `MICROSOFT_PROVIDER_AUTHENTICATION_SECRET` 這個變數的值，複製起來（點 advanced edit 才能複製），**存起來備用。**  

到這裡，你應該有一個測試 function，並存好 **client id、tenant id、secret、scope 和 function URL**。可以用 Postman 測試驗證了

##### 第 4 部分：用 Postman 測試驗證

12. 用下面的 OAuth 設定，在 Postman 打剛建的 endpoint：

    1. **Grant Type:** Authorization Code

    2. **Auth URL**: https://login.microsoftonline.com/`TENANT_ID`/oauth2/v2.0/authorize

    3. **Auth Token URL**: https://login.microsoftonline.com/`TENANT_ID`/oauth2/v2.0/token

    4. **Client ID:** 上面步驟 7 的 `CLIENT_ID`

    5. **Client secret:** 上面步驟 11 的 `MICROSOFT_PROVIDER_AUTHENTICATION_SECRET `

    6. **Scope**: 上面步驟 5 的 `SCOPE`

    7. **Client credentials**: Send client credentials in body

13. 要先點 **Get New Access Token**，再打步驟 10 存的 endpoint。成功的話，會得到這個回應：`”This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.”`

##### 第 5 部分：在 Azure Function 設定你的應用程式

這要另外做，內容依你的 app 而定。範例見 [SharePoint Cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc)。 

##### 第 6 部分：設定 ChatGPT

14. 幫你的 endpoint 產生 OpenAPI spec。 

15. 貼進 GPT 的 Actions 區塊，authentication type 選 OAuth。OAuth 設定跟上面 Postman 一樣。 

16. 儲存 action 後，會在 GPT 設定的最下面看到 callback URI。複製那個 URL，然後**回到 Azure Portal 的 Function App**。

17. 點 **Settings** 底下的 **Authentication**，再點你的 Entra application。

18. 進去後，點 **Manage** 區塊的 **Authentication**。

19. 在那頁的 **Web** 區塊新增一個 Redirect URI，貼上步驟 16 拿到的 Callback URI，然後 Save。 

20. 測試 GPT，應該會正常運作。

## ChatGPT 步驟

### Custom GPT Instructions 

*這部分依應用程式而定。範例見 [SharePoint Cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc)*

### OpenAPI Schema 

建好 Custom GPT 後，把下面的文字複製到 Actions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

下面是連到這個 Middleware 的範例。你要在這裡填入自己應用程式和 function 的資訊。 

```python
openapi: 3.1.0
info:
  title: {insert title}
  description: {insert description}
  version: 1.0.0
servers:
  - url: https://{your_function_app_name}.azurewebsites.net/api
    description: {insert description}
paths:
  /{your_function_name}?code={enter your specific endpoint id here}:
    post:
      operationId: {insert operationID}
      summary: {insert summary}
      requestBody: 
{the rest of this is specific to your application}
```

## 驗證說明

下面是這個第三方應用程式的驗證設定。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

### Action 前置步驟

在 ChatGPT 設定驗證之前，先在應用程式做下面的步驟。

*照上面的步驟 2 和 4 設定驗證*
### 在 ChatGPT 設定

在 ChatGPT 點 "Authentication"，選 **"OAuth"**，填入下面的資訊。 

- **Client ID**: *見上面步驟 12*
- **Client Secret**: *同上*
- **Authorization URL**: *同上*
- **Token URL**: *同上*
- **Scope**: *同上*
- **Token**: *同上*

### Action 後續步驟

ChatGPT 的驗證設好後，照下面在應用程式做完最後設定。 

*測試方式見上面*

*有想優先支援的整合嗎？我們的整合有錯嗎？歡迎到 github 開 PR 或 issue，我們會看。*


## 重點整理

- Azure Function 當 middleware，可以繞過 GPT Actions 10 萬字元的限制，先摘要再回傳，也能回傳檔案。
- Easy Auth 會自動設好 callback URL 並開放 API，所以新建 application 比用現有的省事。
- Function 要能被 GPT 呼叫，需要 `user_impersonation` 權限加上 Admin Consent，並且開啟 public access。
- 有兩個地方要設 redirect URI：Postman 測試用的，和 ChatGPT 儲存 action 後給的 callback URI。

## 練習

1. 照步驟 12 到 13 在 Postman 設好 OAuth，確認拿到預設的成功訊息。
2. 把 function 的回傳內容改成你自己的文字，重新用 Postman 打一次確認。
3. 為你的 function 寫 OpenAPI spec 貼進 GPT Actions，並把 ChatGPT 給的 callback URI 加到 Entra 的 Web Redirect URI，實際讓 GPT 呼叫一次。
