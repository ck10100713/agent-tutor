---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_text.ipynb
---
# GPT Actions library - Sharepoint（回傳文字）

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_text.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_sharepoint_text.ipynb)



## 這篇在做什麼

這篇教你做一個 GPT Action，讓 ChatGPT 能根據使用者在 SharePoint / Office365 有權限看的檔案來回答問題。中間用 Azure Function 呼叫 Microsoft Graph API 搜尋檔案、把檔案轉成純文字，再用 gpt-4o-mini 抽出跟問題相關的段落，最後把文字丟回給 ChatGPT。

## 學完你會

- 了解為什麼 Graph Search API 要搭配 middleware，以及 Azure Function 在中間做哪幾件事
- 用 On-Behalf-Of (OBO) token 讓搜尋只回傳登入使用者有權限的檔案
- 寫出 Custom GPT 的 instructions 和 OpenAPI schema，把這個 Function 接進 ChatGPT

## 開跑前

- 一個可用的 SharePoint 環境
- Postman（要懂 API 和 OAuth）
- 從 platform.openai.com 申請的 OpenAI API Key
- 一個已設定好驗證的 Azure Function（見文中連結的 Azure Function cookbook）

## 簡介

這頁是給開發者的指南，教你為特定應用程式做一個 GPT Action。開始之前，先看過下面這些資料：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零打造 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個方案讓 GPT action 能根據使用者在 SharePoint 或 Office365 可存取的檔案來回答問題，用的是 Microsoft Graph API 的[搜尋功能](https://learn.microsoft.com/en-us/graph/api/resources/search-api-overview?view=graph-rest-1.0)和[取得檔案](https://learn.microsoft.com/en-us/graph/api/driveitem-get?view=graph-rest-1.0\&tabs=http)的能力。Azure Functions 負責處理 Graph API 的回應，轉成人看得懂的格式，或整理成 ChatGPT 能理解的結構。這份程式碼只是示範方向，請依你的需求修改。

這個方案在 Azure Function 內就先把檔案處理好，Function 回傳的是文字，不是 base64 編碼的檔案。因為有先處理、轉成文字，所以最適合大型的非結構化文件，也適合你想分析的檔案數量超過第一個方案所支援的上限的情況（見[這份文件](https://platform.openai.com/docs/actions/sending-files)）。

### 價值與範例使用情境

**價值**：使用者可以用 ChatGPT 的自然語言能力，直接連到 SharePoint 裡的檔案。

**範例使用情境**：
- 使用者想找出跟某個主題有關的檔案
- 使用者需要一個藏在文件深處的關鍵答案

## 架構 / 範例

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/solution_2.gif)

這個方案用一個 Node.js Azure Function，依登入的使用者做下面的事：

1. 根據使用者最初的問題，搜尋他有權限存取的相關檔案。

2. 對找到的每個檔案，轉成一致的可讀格式並取出所有文字。

3. 用 GPT 4o mini (gpt-4o-mini) 根據使用者最初的問題，從檔案中抽出相關文字。GPT 4o mini 的價格看[這裡](https://openai.com/pricing#language-models)，因為處理的是小段 token，這一步的成本很低。

4. 把資料回傳給 ChatGPT，GPT 再用這些資訊回答使用者最初的問題。

從下面的架構圖可以看到，前三步跟方案 1 一樣。主要差別是這個方案把檔案轉成文字，而不是 base64 字串，然後再用 GPT 4o mini 摘要那段文字。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/solution_2_architecture.png)

## 應用程式資訊

### 應用程式重要連結

開始前先看看這些連結：
- Application Website: https://www.microsoft.com/en-us/microsoft-365/sharepoint/collaboration
- Application API Documentation: https://learn.microsoft.com/en-us/previous-versions/office/developer/sharepoint-rest-reference/

### 應用程式前置需求

開始前，先在你的應用程式環境完成下面幾項：
- 有 SharePoint 環境的存取權
- Postman（以及 API 和 OAuth 的知識）
- 從 platform.openai.com 取得的 OpenAI API Key

## Middleware 資訊

照著[搜尋概念檔案指南](https://learn.microsoft.com/en-us/graph/search-concept-files)做，[Microsoft Graph Search API](https://learn.microsoft.com/en-us/graph/search-concept-files) 回傳的是符合條件的檔案參考，不是檔案內容本身。所以需要 middleware，不能直接打 MSFT 的 endpoint。

步驟：

1. 迴圈跑過回傳的檔案，用 [Download File endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0\&tabs=http) 或 [Convert File endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0\&tabs=http) 下載檔案

2. 用 [pdf-parse](https://www.npmjs.com/package/pdf-parse) 把二進位串流轉成人看得懂的文字

3. 接著可以在 function 裡用 gpt-4o-mini 做摘要，進一步最佳化，幫忙應付目前 Actions 加諸的 100,000 字元上限

### 額外步驟

#### 設定 Azure Function

1. 照 [Azure Function cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function) 的步驟設定好 Azure Function

#### 加入 Function 程式碼

現在你有一個已驗證的 Azure Function 了，接下來更新它，讓它能搜尋 SharePoint / O365

2. 到你的測試 function，貼上[這個檔案](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_two_preprocessing.js)的程式碼，然後儲存。

> **這份程式碼只是示範方向**：雖然應該可以直接跑，但設計上是讓你依需求客製化（見文件後段的範例）。

3. 到左邊 **Settings** 底下的 **Configuration** 分頁設定下列環境變數。依你的 Azure UI 版本，這些可能直接列在 **Environment Variables** 裡。

    1. `TENANT_ID`：從前面的章節複製

    2. `CLIENT_ID`：從前面的章節複製

    3. `OPENAI_API_KEY:` 到 platform.openai.com 建一個 OpenAI API key。

4. 到 **Development Tools** 底下的 **Console** 分頁

    1. 在 console 安裝下面這些套件

       1. `npm install @microsoft/microsoft-graph-client`

       2. `npm install axios`

       3. `npm install pdf-parse`

       4. `npm install openai`

5. 完成後，再用 Postman 呼叫一次這個 function（POST），body 放下面的內容（用你覺得會有結果的 query 和搜尋詞）。

    ```json
    {
        "query": "<choose a question>",
        "searchTerm": "<choose a search term>"
    }
    ```

6. 如果有拿到回應，就可以接到 Custom GPT 了！


## 詳細說明

下面是這個方案獨有的設定與說明：在 Azure Function 裡預先處理檔案並抽出摘要。完整程式碼在[這裡](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/sharepoint_azure_function/solution_two_preprocessing.js)。

### 程式碼說明

#### 實作驗證

下面是幾個 function 會用到的 helper function。

#### 初始化 Microsoft Graph Client
建立一個用 access token 初始化 Graph client 的 function，後面用它來搜尋 Office 365 和 SharePoint。

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

#### 取得 On-Behalf-Of (OBO) Token
這個 function 用現有的 bearer token 向 Microsoft 的 identity platform 換一個 OBO token。這樣就能把使用者的身分帶下去，確保搜尋只回傳登入使用者有權限看的檔案。

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

這個 function 抓取 drive item 的內容，處理不同檔案類型，必要時先把檔案轉成 PDF 才能抽文字。PDF 用 [download endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0\&tabs=http)，其他支援的檔案類型用 [convert endpoint](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0\&tabs=http)。
```javascript
const getDriveItemContent = async (client, driveId, itemId, name) => {
    try {
        const fileType = path.extname(name).toLowerCase();
        // the below files types are the ones that are able to be converted to PDF to extract the text. See https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0&tabs=http
        const allowedFileTypes = ['.pdf', '.doc', '.docx', '.odp', '.ods', '.odt', '.pot', '.potm', '.potx', '.pps', '.ppsx', '.ppsxm', '.ppt', '.pptm', '.pptx', '.rtf'];
        // filePath changes based on file type, adding ?format=pdf to convert non-pdf types to pdf for text extraction, so all files in allowedFileTypes above are converted to pdf
        const filePath = `/drives/${driveId}/items/${itemId}/content` + ((fileType === '.pdf' || fileType === '.txt' || fileType === '.csv') ? '' : '?format=pdf');
        if (allowedFileTypes.includes(fileType)) {
            response = await client.api(filePath).getStream();
            // The below takes the chunks in response and combines
            let chunks = [];
            for await (let chunk of response) {
                chunks.push(chunk);
            }
            let buffer = Buffer.concat(chunks);
            // the below extracts the text from the PDF.
            const pdfContents = await pdfParse(buffer);
            return pdfContents.text;
        } else if (fileType === '.txt') {
            // If the type is txt, it does not need to create a stream and instead just grabs the content
            response = await client.api(filePath).get();
            return response;
        }  else if (fileType === '.csv') {
            response = await client.api(filePath).getStream();
            let chunks = [];
            for await (let chunk of response) {
                chunks.push(chunk);
            }
            let buffer = Buffer.concat(chunks);
            let dataString = buffer.toString('utf-8');
            return dataString
            
    } else {
        return 'Unsupported File Type';
    }
     
    } catch (error) {
        console.error('Error fetching drive content:', error);
        throw new Error(`Failed to fetch content for ${name}: ${error.message}`);
    }
};
```

#### 整合 GPT 4o mini 做文字分析

這個 function 用 OpenAI SDK 分析從文件抽出的文字，根據使用者的 query 找出相關資訊。這樣能確保回給 GPT 的只有跟使用者問題有關的文字。

```javascript
const getRelevantParts = async (text, query) => {
    try {
        // We use your OpenAI key to initialize the OpenAI client
        const openAIKey = process.env["OPENAI_API_KEY"];
        const openai = new OpenAI({
            apiKey: openAIKey,
        });
        const response = await openai.chat.completions.create({
            // Using gpt-4o-mini due to speed to prevent timeouts. You can tweak this prompt as needed
            model: "gpt-4o-mini",
            messages: [
                {"role": "system", "content": "You are a helpful assistant that finds relevant content in text based on a query. You only return the relevant sentences, and you return a maximum of 10 sentences"},
                {"role": "user", "content": `Based on this question: **"${query}"**, get the relevant parts from the following text:*****\n\n${text}*****. If you cannot answer the question based on the text, respond with 'No information provided'`}
            ],
            // using temperature of 0 since we want to just extract the relevant content
            temperature: 0,
            // using max_tokens of 1000, but you can customize this based on the number of documents you are searching. 
            max_tokens: 1000
        });
        return response.choices[0].message.content;
    } catch (error) {
        console.error('Error with OpenAI:', error);
        return 'Error processing text with OpenAI' + error;
    }
};
```

#### 建立處理請求的 Azure Function

有了這些 helper function，Azure Function 就負責串起整個流程：驗證使用者、執行搜尋、逐一處理搜尋結果抽出文字，再把相關片段回給 GPT。

**處理 HTTP 請求：** Function 一開始從 HTTP 請求取出 query 和 searchTerm，檢查有沒有 Authorization header，並取出 bearer token。

**驗證：** 用 bearer token 呼叫上面定義的 getOboToken，向 Microsoft 的 identity platform 取得 OBO token。

**初始化 Graph Client：** 拿 OBO token，用上面定義的 initGraphClient 初始化 Microsoft Graph client。

**文件搜尋：** 組出搜尋 query，送給 Microsoft Graph API，根據 searchTerm 找文件。

**文件處理**：對搜尋回傳的每份文件：

- 用 getDriveItemContent 取得文件內容。

- 如果檔案類型有支援，就用 getRelevantParts 分析內容，它會把文字送給 OpenAI 的模型，根據 query 抽出相關資訊。

- 收集分析結果，並附上文件名稱和 URL 等 metadata。

**回應**：Function 依相關度排序結果，放進 HTTP 回應送回去。

```javascript
module.exports = async function (context, req) {
    const query = req.query.query || (req.body && req.body.query);
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
        // Function to tokenize content (e.g., based on words). 
        const tokenizeContent = (content) => {
            return content.split(/\s+/);
        };

        // Function to break tokens into 10k token windows for gpt-4o-mini
        const breakIntoTokenWindows = (tokens) => {
            const tokenWindows = []
            const maxWindowTokens = 10000; // 10k tokens
            let startIndex = 0;

            while (startIndex < tokens.length) {
                const window = tokens.slice(startIndex, startIndex + maxWindowTokens);
                tokenWindows.push(window);
                startIndex += maxWindowTokens;
            }

            return tokenWindows;
        };
        // This is where we are doing the search
        const list = await client.api('/search/query').post(requestBody);

        const processList = async () => {
            // This will go through and for each search response, grab the contents of the file and summarize with gpt-4o-mini
            const results = [];

            await Promise.all(list.value[0].hitsContainers.map(async (container) => {
                for (const hit of container.hits) {
                    if (hit.resource["@odata.type"] === "#microsoft.graph.driveItem") {
                        const { name, id } = hit.resource;
                        // We use the below to grab the URL of the file to include in the response
                        const webUrl = hit.resource.webUrl.replace(/\s/g, "%20");
                        // The Microsoft Graph API ranks the responses, so we use this to order it
                        const rank = hit.rank;
                        // The below is where the file lives
                        const driveId = hit.resource.parentReference.driveId;
                        const contents = await getDriveItemContent(client, driveId, id, name);
                        if (contents !== 'Unsupported File Type') {
                            // Tokenize content using function defined previously
                            const tokens = tokenizeContent(contents);

                            // Break tokens into 10k token windows
                            const tokenWindows = breakIntoTokenWindows(tokens);

                            // Process each token window and combine results
                            const relevantPartsPromises = tokenWindows.map(window => getRelevantParts(window.join(' '), query));
                            const relevantParts = await Promise.all(relevantPartsPromises);
                            const combinedResults = relevantParts.join('\n'); // Combine results

                            results.push({ name, webUrl, rank, contents: combinedResults });
                        } 
                        else {
                            results.push({ name, webUrl, rank, contents: 'Unsupported File Type' });
                        }
                    }
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
            results.sort((a, b) => a.rank - b.rank);
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

下面是幾個可以客製的地方。

- 可以調整 GPT 的 prompt，讓它在找不到東西時再搜尋幾次。

- 可以修改搜尋 query，只搜尋特定的 SharePoint 網站或 O365 Drive，這樣搜尋更聚焦、檢索更準。目前的設定會搜尋登入使用者能存取的所有檔案。

- 可以用 gpt-4o 取代 gpt-4o-mini。成本和延遲會稍微增加，但摘要品質可能更好。

- 可以調整呼叫 Microsoft Graph 時要搜尋的檔案數量。


### 注意事項

Actions 的限制在這裡全部適用，包括回傳 100K 字元以內，以及 [45 秒 timeout](https://platform.openai.com/docs/actions/production/timeouts)。


- 這個方案只適用於文字，不適用於圖片。在 Azure Function 多寫一些程式，可以改用 GPT-4o 來摘要圖片內容。

- 不適用結構化資料。如果結構化資料是你使用情境的重點，建議用方案 1。

## ChatGPT 步驟

### Custom GPT Instructions

建好 Custom GPT 後，把下面的文字複製到 Instructions 面板。有問題的話，看[入門範例](https://platform.openai.com/docs/actions/getting-started)了解這一步的細節。

```python
You are a Q&A helper that helps answer users questions. You have access to a documents repository through your API action. When a user asks a question, you pass in that question exactly as stated to the "query" parameter, and for the "searchTerm" you use a single keyword or term you think you should use for the search.

****

Scenario 1: There are answers

If your action returns results, then you take the results from the action and summarize concisely with the webUrl returned from the action. You answer the users question to the best of your knowledge from the action

****

Scenario 2: No results found

If the response you get from the action is "No results found", stop there and let the user know there were no results and that you are going to try a different search term, and explain why. You must always let the user know before conducting another search.

Example:

****

I found no results for "DEI". I am now going to try [insert term] because [insert explanation]

****

Then, try a different searchTerm that is similar to the one you tried before, with a single word. 

Try this three times. After the third time, then let the user know you did not find any relevant documents to answer the question, and to check SharePoint. Be sure to be explicit about what you are searching for at each step.

****

In either scenario, try to answer the user's question. If you cannot answer the user's question based on the knowledge you find, let the user know and ask them to go check the HR Docs in SharePoint. If the file is a CSV, XLSX, or XLS, you can tell the user to download the file using the link and re-upload to use Advanced Data Analysis.
```

### OpenAPI Schema

建好 Custom GPT 後，把下面的文字複製到 Actions 面板。有問題的話，看[入門範例](https://platform.openai.com/docs/actions/getting-started)了解這一步的細節。

下面的 spec 會傳入 `query` 參數來引導預先處理，並傳入 `searchTerm` 在 Microsoft Graph 找對應的檔案。
>記得依照上面截圖中複製的連結，換成你自己的 function app 名稱、function 名稱和 code

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
                query:
                  type: string
                  description: The full query to search for in SharePoint documents.
                searchTerm:
                  type: string
                  description: A specific term to search for within the documents.
      responses:
        '200':
          description: Search results
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    documentName:
                      type: string
                      description: The name of the document.
                    snippet:
                      type: string
                      description: A snippet from the document containing the search term.
                    url:
                      type: string
                      description: The URL to access the document.
```

## 驗證說明

下面是設定這個第三方應用程式驗證的說明。有問題的話，看[入門範例](https://platform.openai.com/docs/actions/getting-started)了解這一步的細節。

*驗證的詳細說明請看上面，以及 [Azure Function cookbook](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function)。*

## FAQ 與疑難排解

- 為什麼程式碼用 Microsoft Graph API，不用 [SharePoint API](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/get-to-know-the-sharepoint-rest-service?tabs=csom)？

  - SharePoint API 是舊的。依 Microsoft 的[文件](https://learn.microsoft.com/en-us/sharepoint/dev/apis/sharepoint-rest-graph)，“For SharePoint Online, innovation using a REST API against SharePoint is driven via the Microsoft Graph REST API's.” Graph API 比較有彈性，而 SharePoint API 一樣會碰到[為什麼不直接跟 Microsoft Graph API 互動？](#why-is-this-necessary-instead-of-interacting-with-the-microsoft-api-directly)那段列出的檔案問題。

- 支援哪些檔案類型？
    1. 支援 Convert File endpoint 文件[_這裡_](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format?view=graph-rest-1.0\&tabs=http)列出的所有檔案。具體來說，支援 _pdf, doc, docx, odp, ods, odt, pot, potm, potx, pps, ppsx, ppsxm, ppt, pptm, pptx, rtf_。

    2. 搜尋結果如果是 XLS、XLSX 或 CSV，會提示使用者下載檔案，再重新上傳，用 Advanced Data Analysis 來提問。如上所述，如果你的使用情境包含結構化資料，建議用方案 1。

- 為什麼要申請 OBO token？

  - 如果用登入 Azure Function 的同一個 token 去驗證 Graph API，會得到 “invalid audience” token 錯誤。因為這個 token 的 audience 只能是 user\_impersonation。

  - 為了解決這個問題，function 會在 app 內申請一個 scope 為 Files.Read.All 的新 token，用的是 [On Behalf Of flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow)。它會繼承登入使用者的權限，所以這個 function 只會搜尋登入使用者有權限存取的檔案。

  - 我們刻意每次請求都重新申請一個 On Behalf Of token，因為 Azure Function App 本來就設計成無狀態。你也可以整合 Azure Key Vault 來儲存 secret，再用程式取出。

*有想優先支援的整合嗎？我們的整合有錯誤嗎？歡迎到 GitHub 開 PR 或 issue，我們會去看。*


## 重點整理

- Graph Search API 只回傳檔案的參考，不含內容，所以需要 Azure Function 這類 middleware 去下載並轉成文字。
- OBO token 讓 function 繼承登入使用者的權限，搜尋結果自然只包含他看得到的檔案。
- 先在 function 內用 gpt-4o-mini 抽出相關片段，才能把回傳量壓在 Actions 100K 字元和 45 秒 timeout 的限制內。
- 這個方案只處理文字類檔案；Excel、CSV 這類結構化資料建議改用方案 1。

## 練習

1. 把 Postman 請求 body 的 `query` 和 `searchTerm` 換成你自己 SharePoint 裡真的有的主題，看回傳的文字片段是否跟問題相關。
2. 把 `getRelevantParts` 裡用的模型從 gpt-4o-mini 改成 gpt-4o，比較摘要品質、延遲和成本的差異。
3. 修改 Graph 搜尋的 query，讓它只搜尋某一個 SharePoint 網站，或調整一次搜尋的檔案數量，觀察結果和 45 秒 timeout 的關係。
