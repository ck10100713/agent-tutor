---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc.ipynb
---
# GPT Actions library - Sharepoint (Return Docs)

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_doc.ipynb)



## 這篇在做什麼

做一個 GPT Action，讓 ChatGPT 能搜尋使用者在 SharePoint / Office365 有權限看的檔案，並把檔案內容當成使用者直接上傳的附件來回答問題。中間靠一個 Node.js Azure Function 呼叫 Microsoft Graph API，再把檔案轉成 base64 回傳給 ChatGPT。

## 學完你會

- 用 Azure Function 當 middleware，串接 Microsoft Graph 搜尋 SharePoint 檔案
- 用 On-Behalf-Of (OBO) token 讓搜尋只回傳登入使用者有權限的檔案
- 把檔案轉成 `openaiFileResponse` 格式，並寫出對應的 Custom GPT instructions 和 OpenAPI schema

## 開跑前

- 有 SharePoint 環境的存取權
- 安裝 Postman，並懂基本 API 與 OAuth
- 已依 Azure Function cookbook 建好有驗證的 Azure Function，並取得 `TENANT_ID`、`CLIENT_ID`



## 簡介

這一頁是給開發者看的，教你為特定應用程式做 GPT Action。開始之前，先看過下面這些：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個方案讓 GPT action 能根據使用者在 SharePoint 或 Office365 有權限的檔案來回答問題，用的是 Microsoft Graph API 的[搜尋功能](https://learn.microsoft.com/en-us/graph/api/resources/search-api-overview?view=graph-rest-1.0)和[取得檔案](https://learn.microsoft.com/en-us/graph/api/driveitem-get?view=graph-rest-1.0\&tabs=http)的能力。Azure Functions 負責處理 Graph API 的回應，轉成人看得懂或 ChatGPT 看得懂的結構。這份程式碼只是參考方向，請依你的需求修改。

這個方案用到了 Actions 的[檔案回傳功能](https://platform.openai.com/docs/actions/sending-files)，檔案可以當成直接上傳到對話的檔案來用。Azure Function 回傳 base64 字串，ChatGPT 再轉成檔案。結構化和非結構化資料都能處理，但有大小限制（見[這份文件](https://platform.openai.com/docs/actions/sending-files)）。

### 價值與業務情境

**價值**：使用者可以用 ChatGPT 的自然語言能力，直接連到 SharePoint 裡的檔案。

**範例情境**：
- 使用者想查哪些檔案跟某個主題有關
- 使用者有個重要問題，答案藏在文件深處

## 架構與範例

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/solution_1.gif)


這個方案用 Node.js Azure Function，依登入的使用者做這幾件事：

1. 根據使用者最初的問題，搜尋他有權限存取的相關檔案。

2. 每個找到的檔案都轉成 base64 字串。

3. 整理成 ChatGPT 預期的[資料結構](https://platform.openai.com/docs/actions/sending-files/inline-option)。

4. 回傳給 ChatGPT。GPT 就能像使用者上傳到對話的檔案一樣使用它們。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/solution_1_architecture.png)

## 應用程式資訊

### 重要連結

開始前先看這些連結：
- Application Website: https://www.microsoft.com/en-us/microsoft-365/sharepoint/collaboration
- Application API Documentation: https://learn.microsoft.com/en-us/previous-versions/office/developer/sharepoint-rest-reference/

### 前置條件

開始前，先在你的環境準備好：
- 有 SharePoint 環境的存取權
- Postman（以及 API 和 OAuth 的基本知識）


## Middleware 資訊

照著 [search concept files guide](https://learn.microsoft.com/en-us/graph/search-concept-files) 做，[Microsoft Graph Search API](https://learn.microsoft.com/en-us/graph/search-concept-files) 只會回傳符合條件的檔案參照，不會回傳檔案內容。所以需要 middleware，不能直接打 MSFT 的 endpoint。

我們得把那個 API 的回應重組成 `openaiFileResponse` 的結構，格式見[這裡](https://platform.openai.com/docs/actions/getting-started/inline-option)。

### 額外步驟

#### 設定 Azure Function

1. 照 [Azure Function cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function) 的步驟設定 Azure Function

#### 加入 Function 程式碼

現在已經有一個通過驗證的 Azure Function，接著更新它來搜尋 SharePoint / O365。

2. 到你的測試 function，貼上[這個檔案](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_one_file_retrieval.js)的程式碼，然後儲存。

> **這份程式碼只是參考方向**。它應該能直接跑，但設計上是讓你依需求客製（客製範例在文末）。

3. 到左邊 **Settings** 底下的 **Configuration** 分頁設定下列環境變數。依 Azure UI 不同，也可能直接列在 **Environment Variables**。

    1. `TENANT_ID`：從前面的段落複製

    2. `CLIENT_ID`：從前面的段落複製

4. 到 **Development Tools** 底下的 **Console** 分頁

    1. 在 console 安裝下列套件

       1. `npm install @microsoft/microsoft-graph-client`

       2. `npm install axios`

5. 完成後，再用 Postman 對 function 發 POST，body 放下面這段（query 和搜尋詞挑你覺得會有結果的）。

     ```json
    {
        "searchTerm": "<choose a search term>"
    }
    ```

6. 有拿到回應就可以接上 Custom GPT 了！設定方式見 Azure Function 那頁的 ChatGPT 段落


## 更詳細的逐段說明


下面是這個方案獨有的設定與說明。完整程式碼在[這裡](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_one_file_retrieval.js)。

### 程式碼說明

下面一段一段看 function 的各個部分。開始前，確認已安裝需要的套件、設好環境變數（見上面的安裝步驟）。


#### 實作驗證

先有幾個 function 會用到的 helper。


##### 初始化 Microsoft Graph Client

建立一個用 access token 初始化 Graph client 的 function，後面用來搜尋 Office 365 和 SharePoint。

```javascript
const { Client } = require('@microsoft/microsoft-graph-client');

function initGraphClient(accessToken) {
    return Client.init({
        authProvider: (done) => {
            done(null, accessToken);
        }
    });
}
```

##### 取得 On-Behalf-Of (OBO) Token

這個 function 用現有的 bearer token 向 Microsoft 的 identity platform 要一個 OBO token。這樣就能把憑證往下傳，確保搜尋只回傳登入使用者有權限的檔案。

```javascript
const axios = require('axios');
const qs = require('querystring');

async function getOboToken(userAccessToken) {
    const { TENANT_ID, CLIENT_ID, MICROSOFT_PROVIDER_AUTHENTICATION_SECRET } = process.env;
    const params = {
        client_id: CLIENT_ID,
        client_secret: MICROSOFT_PROVIDER_AUTHENTICATION_SECRET,
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion: userAccessToken,
        requested_token_use: 'on_behalf_of',
        scope: 'https://graph.microsoft.com/.default'
    };

    const url = `https\://login.microsoftonline.com/${TENANT_ID}/oauth2/v2.0/token`;
    try {
        const response = await axios.post(url, qs.stringify(params), {
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
        });
        return response.data.access\_token;
    } catch (error) {
        console.error('Error obtaining OBO token:', error.response?.data || error.message);
        throw error;
    }
}
```

#### 取得 O365 / SharePoint 項目的內容

這個 function 抓取 drive item 的內容，轉成 base64 字串，再重組成 `openaiFileResponse` 的格式。
```javascript
const getDriveItemContent = async (client, driveId, itemId, name) => {
   try
       const filePath = `/drives/${driveId}/items/${itemId}`;
       const downloadPath = filePath + `/content`
       // this is where we get the contents and convert to base64
       const fileStream = await client.api(downloadPath).getStream();
       let chunks = [];
           for await (let chunk of fileStream) {
               chunks.push(chunk);
           }
       const base64String = Buffer.concat(chunks).toString('base64');
       // this is where we get the other metadata to include in response
       const file = await client.api(filePath).get();
       const mime_type = file.file.mimeType;
       const name = file.name;
       return {"name":name, "mime_type":mime_type, "content":base64String}
   } catch (error) {
       console.error('Error fetching drive content:', error);
       throw new Error(`Failed to fetch content for ${name}: ${error.message}`);
   }
```

#### 建立處理請求的 Azure Function

有了這些 helper，Azure Function 負責串起整個流程：驗證使用者、執行搜尋、逐一處理搜尋結果取出文字，再把相關內容回傳給 GPT。

**處理 HTTP 請求：**function 一開始從 HTTP request 取出 query 和 searchTerm，檢查有沒有 Authorization header，並取出 bearer token。

**驗證：**用 bearer token 呼叫上面定義的 getOboToken，向 Microsoft identity platform 取得 OBO token。

**初始化 Graph Client：**拿到 OBO token 後，用上面定義的 initGraphClient 初始化 Microsoft Graph client。

**文件搜尋：**組出搜尋 query，送到 Microsoft Graph API，依 searchTerm 找文件。

**文件處理**：對搜尋回傳的每份文件：

- 用 getDriveItemContent 取得文件內容。

- 轉成 base64 字串，並重組成 `openaiFileResponse` 的結構。

**回應**：function 把結果放在 HTTP response 傳回去。
```javascript
module.exports = async function (context, req) {
   // const query = req.query.query || (req.body && req.body.query);
   const searchTerm = req.query.searchTerm || (req.body && req.body.searchTerm);
   if (!req.headers.authorization) {
       context.res = {
           status: 400,
           body: 'Authorization header is missing'
       };
       return;
   }
   /// The below takes the token passed to the function, to use to get an OBO token.
   const bearerToken = req.headers.authorization.split(' ')[1];
   let accessToken;
   try {
       accessToken = await getOboToken(bearerToken);
   } catch (error) {
       context.res = {
           status: 500,
           body: `Failed to obtain OBO token: ${error.message}`
       };
       return;
   }
   // Initialize the Graph Client using the initGraphClient function defined above
   let client = initGraphClient(accessToken);
   // this is the search body to be used in the Microsoft Graph Search API: https://learn.microsoft.com/en-us/graph/search-concept-files
   const requestBody = {
       requests: [
           {
               entityTypes: ['driveItem'],
               query: {
                   queryString: searchTerm
               },
               from: 0,
               // the below is set to summarize the top 10 search results from the Graph API, but can configure based on your documents.
               size: 10
           }
       ]
   };


   try {
       // This is where we are doing the search
       const list = await client.api('/search/query').post(requestBody);
       const processList = async () => {
           // This will go through and for each search response, grab the contents of the file and summarize with gpt-3.5-turbo
           const results = [];
           await Promise.all(list.value[0].hitsContainers.map(async (container) => {
               for (const hit of container.hits) {
                   if (hit.resource["@odata.type"] === "#microsoft.graph.driveItem") {
                       const { name, id } = hit.resource;
                       // The below is where the file lives
                       const driveId = hit.resource.parentReference.driveId;
                       // we use the helper function we defined above to get the contents, convert to base64, and restructure it
                       const contents = await getDriveItemContent(client, driveId, id, name);
                       results.push(contents)
               }
           }));
           return results;
       };
       let results;
       if (list.value[0].hitsContainers[0].total == 0) {
           // Return no results found to the API if the Microsoft Graph API returns no results
           results = 'No results found';
       } else {
           // If the Microsoft Graph API does return results, then run processList to iterate through.
           results = await processList();
           // this is where we structure the response so ChatGPT knows they are files
           results = {'openaiFileResponse': results}
       }
       context.res = {
           status: 200,
           body: results
       };
   } catch (error) {
       context.res = {
           status: 500,
           body: `Error performing search or processing results: ${error.message}`,
       };
   }
};
```
### 客製化

幾個可以客製的方向。

- 可以改 GPT 的 prompt，讓它在找不到東西時再多搜尋幾次。

- 可以改搜尋 query，只搜尋特定的 SharePoint 網站或 O365 Drive，讓搜尋更聚焦、檢索更準。目前的設定會搜尋登入使用者能存取的所有檔案。

- 可以改程式碼，只回傳特定類型的檔案，例如只回傳結構化資料 / CSV。 

- 可以調整呼叫 Microsoft Graph 時搜尋的檔案數量。注意依[這份文件](https://platform.openai.com/docs/actions/getting-started)，最多只能放 10 個檔案。 

### 注意事項

Actions 的限制在這裡全都適用，例如回傳要在 10 萬字元以內，以及 [45 秒 timeout](https://platform.openai.com/docs/actions/production/timeouts)。

- 請務必讀過[回傳檔案](https://platform.openai.com/docs/actions/sending-files)和[檔案上傳](https://help.openai.com/en/articles/8555545-file-uploads-faq)的文件，那些限制在這裡也適用。

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 後，把下面的文字複製到 Instructions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```python
You are a Q&A helper that helps answer users questions. You have access to a documents repository through your API action. When a user asks a question, you pass in the "searchTerm" a single keyword or term you think you should use for the search.

****

Scenario 1: There are answers

If your action returns results, then you take the results from the action and try to answer the users question. 

****

Scenario 2: No results found

If the response you get from the action is "No results found", stop there and let the user know there were no results and that you are going to try a different search term, and explain why. You must always let the user know before conducting another search.

Example:

****

I found no results for "DEI". I am now going to try [insert term] because [insert explanation]

****

Then, try a different searchTerm that is similar to the one you tried before, with a single word. 

Try this three times. After the third time, then let the user know you did not find any relevant documents to answer the question, and to check SharePoint. 
Be sure to be explicit about what you are searching for at each step.

****

In either scenario, try to answer the user's question. If you cannot answer the user's question based on the knowledge you find, let the user know and ask them to go check the HR Docs in SharePoint.
```

### OpenAPI Schema 

建好 Custom GPT 後，把下面的文字複製到 Actions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

這個 schema 預期回應符合我們文件裡的[檔案回傳結構](https://platform.openai.com/docs/actions/sending-files)，並傳入 `searchTerm` 參數來決定搜尋內容。
>記得依截圖中複製的連結，改掉 function app 名稱、function 名稱和 code

```python
openapi: 3.1.0
info:
  title: SharePoint Search API
  description: API for searching SharePoint documents.
  version: 1.0.0
servers:
  - url: https://{your_function_app_name}.azurewebsites.net/api
    description: SharePoint Search API server
paths:
  /{your_function_name}?code={enter your specific endpoint id here}:
    post:
      operationId: searchSharePoint
      summary: Searches SharePoint for documents matching a query and term.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                searchTerm:
                  type: string
                  description: A specific term to search for within the documents.
      responses:
        '200':
          description: A CSV file of query results encoded in base64.
          content:
            application/json:
              schema:
                type: object
                properties:
                  openaiFileResponseData:
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
                          description: The base64 encoded contents of the file.
        '400':
          description: Bad request when the SQL query parameter is missing.
        '413':
          description: Payload too large if the response exceeds the size limit.
        '500':
          description: Server error when there are issues executing the query or encoding the results.
```

## 驗證說明

下面是這個第三方應用程式的驗證設定。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

*驗證的詳細說明請看上面，以及 [Azure Function cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function)。*

## FAQ 與疑難排解

- 為什麼程式碼用 Microsoft Graph API，而不是 [SharePoint API](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/get-to-know-the-sharepoint-rest-service?tabs=csom)？

  - SharePoint API 是舊的。依 Microsoft 的[文件](https://learn.microsoft.com/en-us/sharepoint/dev/apis/sharepoint-rest-graph)，「For SharePoint Online, innovation using a REST API against SharePoint is driven via the Microsoft Graph REST API's.」Graph API 比較有彈性，而且 SharePoint API 還是會碰到同樣的檔案問題，見 [Why is this necessary instead of interacting with the Microsoft Graph API directly?](#why-is-this-necessary-instead-of-interacting-with-the-microsoft-api-directly) 那一段。

- 支援哪些檔案類型？

  跟[檔案上傳文件](https://help.openai.com/en/articles/8555545-file-uploads-faq)的規範一樣。 

- 為什麼要要求 OBO token？
  - 如果拿登入 Azure Function 的同一個 token 去驗證 Graph API，會得到 “invalid audience” token 錯誤，因為這個 token 的 audience 只能是 user\_impersonation。

  - 所以 function 會用 [On Behalf Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)，在 app 內要一個 scope 為 Files.Read.All 的新 token。它會繼承登入使用者的權限，所以 function 只會搜尋登入使用者有權限的檔案。 

  - 我們刻意每次請求都要一個新的 On Behalf Of token，因為 Azure Function App 本來就是 stateless。你也可以搭配 Azure Key Vault 存 secret，再用程式取出。 

*有想優先支援的整合嗎？我們的整合有錯嗎？歡迎到 github 開 PR 或 issue，我們會看。*


## 重點整理

- GPT Action 要回傳檔案內容時，Graph Search 只給參照，所以要有 middleware 把檔案抓下來轉成 base64，再包成 `openaiFileResponse`。
- OBO token 讓 function 繼承登入使用者的權限，搜尋結果不會超出他能看的範圍。
- 每次請求都重新要 OBO token，是因為 Azure Function 是 stateless；要快取的話可以搭配 Key Vault。
- Actions 的限制（回傳 10 萬字元以內、45 秒 timeout、最多 10 個檔案）在這裡都適用。

## 練習

1. 把 Postman 的 body 裡的 `searchTerm` 換成別的關鍵字，看回傳哪些檔案。
2. 改 Graph 搜尋 query，只回傳 CSV 檔，再確認 GPT 還能回答問題。
3. 把搜尋範圍限制在某一個 SharePoint site，並把回傳檔案數量上限設成 3，觀察回答品質有什麼變化。
