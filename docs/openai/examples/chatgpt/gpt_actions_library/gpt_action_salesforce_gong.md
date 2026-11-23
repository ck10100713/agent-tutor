---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/chatgpt/gpt_actions_library/gpt_action_salesforce_gong.md
---

# GPT Actions 函式庫：Salesforce 與 Gong

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_salesforce_gong.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_salesforce_gong.md)

## 這篇在做什麼

教你建一個同時串接 Salesforce 和 Gong 的 GPT。Salesforce 直接用既有 cookbook 的做法，Gong 則透過一個 serverless middleware 取得通話逐字稿。最後在同一個 GPT 裡建兩個 Action。

## 學完你會

- 寫一個接收 `callIds` 陣列、從 Gong 取逐字稿並整理回應的 serverless function
- 為 Salesforce 和 middleware 各寫一份 OpenAPI schema，建立兩個獨立的 Action
- 用 Custom GPT instructions 讓 GPT 先查 Salesforce 拿 Call ID，再取 Gong 逐字稿並用 MEDPICC 或 SPICED 整理

## 開跑前

- 需要 Salesforce 帳號與 Connected App（OAuth 設定見 Salesforce cookbook）
- 需要 Gong API key
- 需要部署 middleware 的雲端環境（AWS、Azure Functions 或 Google Cloud Function）


## 簡介

這一頁是給開發者的指南，說明怎麼建立 middleware，把 GPT Action 連到特定應用程式。開始前請先看過下面這些資料：

- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零開始建立 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼建立一個能從 Salesforce 和 Gong 取得資訊的 GPT。過程會建立多個自訂 Action，它們已記錄在既有的 cookbook 裡，下一節會列出這些 cookbook。

### 價值與商業使用範例

**價值**：使用者現在可以用 ChatGPT 的能力來：

- 連接 Salesforce
- 搜尋客戶帳號
- 取得先前通話的 Gong 逐字稿

**使用範例**：

業務代表正在準備即將到來的客戶會議。透過這個整合，他可以快速從 Salesforce 取得相關的帳號資料，取得最近的 Gong 通話逐字稿，並得到 AI 產生、依 MEDPICC 或 SPICED 這類成熟銷售方法論整理的摘要與洞察。這讓業務代表清楚掌握客戶目前的狀況和下一步，全程只要幾分鐘

## 應用程式資訊
這個例子會連接 Salesforce 和 Gong（透過 middleware）。Salesforce 的基本設定與認證，以及 middleware 的建立，我們參考既有的 cookbook。

### Salesforce GPT Action

請參考我們設定 Salesforce GPT Action 的 cookbook。其中要注意的兩個設定是：

- [Application Information](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_salesforce#application-information)：涵蓋 Salesforce 中需要熟悉的概念
- [Authentication Instructions](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_salesforce#authentication-instructions)：涵蓋在 Salesforce 建立 Connected App，並設定 OAuth（Salesforce 和 ChatGPT 兩邊都要）

### Middleware GPT Action
請參考我們任一份建立 middleware 的 cookbook：

- [GPT Actions library (Middleware) - AWS](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_aws_function)
- [GPT Actions library (Middleware) - Azure Functions](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_azure_function)
- [GPT Actions library (Middleware) - Google Cloud Function](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function)

### 應用程式前置條件

除了上面 cookbook 的前置條件外，還要確認你有 Gong API key

## 應用程式設定

### 部署 serverless function

這個 serverless function 會接收一個 `callIds` 陣列，從 Gong 取得逐字稿，並整理好回應再送給 ChatGPT。下面是它在 Azure Functions (Javascript) 上的範例

```javascript
const { app } = require('@azure/functions');
const axios = require('axios');

// Replace with your Gong API token
const GONG_API_BASE_URL = "https://api.gong.io/v2";
const GONG_API_KEY = process.env.GONG_API_KEY;

app.http('callTranscripts', {
    methods: ['POST'],
    authLevel: 'function',
    handler: async (request, context) => {        
        try {            
            const body = await request.json();
            const callIds = body.callIds;

            if (!Array.isArray(callIds) || callIds.length === 0) {
                return {
                    status: 400,
                    body: "Please provide call IDs in the 'callIds' array."
                };
            }

            // Fetch call transcripts
            const transcriptPayload = { filter: { callIds } };
            const transcriptResponse = await axios.post(`${GONG_API_BASE_URL}/calls/transcript`, transcriptPayload, {
                headers: {
                    'Authorization': `Basic ${GONG_API_KEY}`,
                    'Content-Type': 'application/json'
                }
            });

            const transcriptData = transcriptResponse.data;

            // Fetch extensive call details
            const extensivePayload = {
                filter: { callIds },
                contentSelector: {
                    exposedFields: { parties: true }
                }
            };

            const extensiveResponse = await axios.post(`${GONG_API_BASE_URL}/calls/extensive`, extensivePayload, {
                headers: {
                    'Authorization': `Basic ${GONG_API_KEY}`,
                    'Content-Type': 'application/json'
                }
            });

            const extensiveData = extensiveResponse.data;

            // Create a map of call IDs to metadata and speaker details
            const callMetaMap = {};
            extensiveData.calls.forEach(call => {
                callMetaMap[call.metaData.id] = {
                    title: call.metaData.title,
                    started: call.metaData.started,
                    duration: call.metaData.duration,
                    url: call.metaData.url,
                    speakers: {}
                };

                call.parties.forEach(party => {
                    callMetaMap[call.metaData.id].speakers[party.speakerId] = party.name;
                });
            });

            // Transform transcript data into content and include metadata
            transcriptData.callTranscripts.forEach(call => {
                const meta = callMetaMap[call.callId];
                if (!meta) {
                    throw new Error(`Metadata for callId ${call.callId} not found.`);
                }

                let content = '';
                call.transcript.forEach(segment => {
                    const speakerName = meta.speakers[segment.speakerId] || "Unknown Speaker";

                    // Combine all sentences for the speaker into a paragraph
                    const sentences = segment.sentences.map(sentence => sentence.text).join(' ');
                    content += `${speakerName}: ${sentences}\n\n`; // Add a newline between speaker turns
                });

                // Add metadata and content to the call object
                call.title = meta.title;
                call.started = meta.started;
                call.duration = meta.duration;
                call.url = meta.url;
                call.content = content;
                
                delete call.transcript;
            });

            // Return the modified transcript data
            return {
                status: 200,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(transcriptData)
            };
        } catch (error) {
            context.log('[ERROR]', "Error processing request:", error);

            return {
                status: error.response?.status || 500,
                body: {
                    message: "An error occurred while fetching or processing call data.",
                    details: error.response?.data || error.message
                }
            };
        }
    }
});

```

這是你要放進 `package.json` 的相依套件

```javascript
"dependencies": {
    "@azure/functions": "^4.0.0",
    "axios": "^1.7.7"
  }
```

## ChatGPT 步驟

### Custom GPT Instructions

建立好 Custom GPT 後，把下面的文字複製到 Instructions 欄位。有疑問可以看[入門範例](https://platform.openai.com/docs/actions/getting-started)，裡面更詳細說明這一步。

```
# Trigger
User enters the name of an account that they want to prepare for

# Steps
1. Retrieve Account Names - Make a call to the `executeSOSLSearch` custom action searching for a Salesforce Account with that name (SOSL). Retrieve up to 5 accounts. This is what the query should look like - `FIND {Acme} IN ALL FIELDS RETURNING Account(Id, Name) LIMIT 5`

2. Show the accounts in this format - `Account Name - salesforceID`. Ask the user to confirm which account they are interested in. 

3. Get Gong Call IDs for the account - For the confirmed account, make a call to `executeSOQLQuery` to get all the Gong Call IDs. It should look like this - `SELECT XXX, YYY, ZZZ
FROM Gong__Gong_Call__c 
WHERE Gong__Primary_Account__c = '<AccountId>' 
ORDER BY Gong__Call_Start__c DESC 
LIMIT 2
`

4. Pass in the callIds to `getTranscriptsByCallIds `

# Trigger
User says "Summarize call"

# Steps

Use both the transcripts and provide the following output

## Account Name
Print out the account name

## Details of calls
>Please list the calls for which you retrieved the transcripts along with their dates and attendees in this table format:  
>>Headers: <Title of Call>, <Date>, <Attendees>, <Gong URL>

## Recommended Meeting Focus Areas: 
>Analyze the transcripts to identify themes, challenges, and opportunities. Based on this, generate a list of recommended focus areas for the next meeting. These should be actionable and specific to the client’s needs. Explain **why** each item should be a meeting focus.

For each of the following insights, specify **which call and date** you sourced the insight from:

### Metrics
Quantifiable outcomes the customer is trying to achieve. These could be cost reduction, increased revenue, user growth, efficiency gains, etc. Look for KPIs or success measures mentioned.

### Economic Buyer
Identify if the true economic decision-maker was mentioned or involved. This includes titles, names, or hints at budget ownership or final authority.

### Decision Criteria
What are the key factors the customer will use to evaluate solutions? These could include price, performance, support, integrations, ease of use, etc.

### Decision Process
Describe how the customer plans to make the buying decision: stages, stakeholders involved, approval processes, timelines.

### Paper Process
Any mention of legal, procurement, compliance, or contract-related steps and timelines should be captured here.

### Identify Pain
Highlight the core business challenges the customer is facing, ideally in their own words. Understand what’s driving urgency.

### Champion
Is there someone internally who is championing our solution? Mention names, roles, or behaviors that indicate advocacy (e.g., “I’m pushing this internally”).

### (Optional) Competition
Mention any competing vendors, internal builds, or alternative solutions discussed.
```
上面的例子裡，請把 (3) 的查詢換成從你自訂的 Salesforce 物件取出 Gong Call ID 的查詢。

接著你要建立 2 個獨立的 Action，一個連 Salesforce，另一個連呼叫 Gong API 的 middleware

### Salesforce 自訂 Action 的 OpenAPI Schema

建立好 Custom GPT 後，把下面的文字複製到 Actions 欄位。有疑問可以看[入門範例](https://platform.openai.com/docs/actions/getting-started)，裡面更詳細說明這一步。

下面是連接 Salesforce 的範例，你需要在這一段填入你的 URL。

```javascript
openapi: 3.1.0
info:
  title: Salesforce API
  version: 1.0.0
  description: API for accessing Salesforce sObjects and executing queries.
servers:
  - url: https://<subdomain>.my.salesforce.com/services/data/v59.0
    description: Salesforce API server
paths:
  /query:
    get:
      summary: Execute a SOQL Query
      description: Executes a given SOQL query and returns the results.
      operationId: executeSOQLQuery
      parameters:
        - name: q
          in: query
          description: The SOQL query string to be executed.
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Query executed successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/QueryResult'

  /search:
    get:
      summary: Execute a SOSL Search
      description: Executes a SOSL search based on the given query and returns matching records.
      operationId: executeSOSLSearch
      parameters:
        - name: q
          in: query
          description: The SOSL search string (e.g., 'FIND {Acme}').
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Search executed successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SearchResult'

components:
  schemas:
    QueryResult:
      type: object
      description: Result of a SOQL query.
      properties:
        totalSize:
          type: integer
          description: The total number of records matching the query.
        done:
          type: boolean
          description: Indicates if the query result includes all records.
        records:
          type: array
          description: The list of records returned by the query.
          items:
            $ref: '#/components/schemas/SObject'

    SearchResult:
      type: object
      description: Result of a SOSL search.
      properties:
        searchRecords:
          type: array
          description: The list of records matching the search query.
          items:
            $ref: '#/components/schemas/SObject'

    SObject:
      type: object
      description: A Salesforce sObject, which represents a database table record.
      properties:
        attributes:
          type: object
          description: Metadata about the sObject, such as type and URL.
          properties:
            type:
              type: string
              description: The sObject type.
            url:
              type: string
              description: The URL of the record.
        Id:
          type: string
          description: The unique identifier for the sObject.
      additionalProperties: true
```

### Salesforce 自訂 Action 的認證設定
請照 [GPT Actions library - Salesforce](https://cookbook.openai.com/examples/chatgpt/gpt_actions_library/gpt_action_salesforce#in-chatgpt) 裡的步驟做

### 連接 Gong 的 middleware 的 OpenAPI Schema
這個例子是針對呼叫 Gong API 的 Azure Function 來設定。請把 `url` 換成你自己的 middleware URL

```
openapi: 3.1.0
info:
  title: Call Transcripts API
  description: API to retrieve call transcripts and associated metadata by specific call IDs.
  version: 1.0.1
servers:
  - url: https://<subdomain>.azurewebsites.net/api
    description: Production server
paths:
  /callTranscripts:
    post:
      operationId: getTranscriptsByCallIds
      x-openai-isConsequential: false
      summary: Retrieve call transcripts by call IDs
      description: Fetches specific call transcripts based on the provided call IDs in the request body.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                callIds:
                  type: array
                  description: List of call IDs for which transcripts need to be fetched.
                  items:
                    type: string
              required:
                - callIds
      responses:
        '200':
          description: A successful response containing the requested call transcripts and metadata.
          content:
            application/json:
              schema:
                type: object
                properties:
                  requestId:
                    type: string
                    description: Unique request identifier.
                  records:
                    type: object
                    description: Metadata about the pagination.
                    properties:
                      totalRecords:
                        type: integer
                        description: Total number of records available.
                      currentPageSize:
                        type: integer
                        description: Number of records in the current page.
                      currentPageNumber:
                        type: integer
                        description: The current page number.
                  callTranscripts:
                    type: array
                    description: List of call transcripts.
                    items:
                      type: object
                      properties:
                        callId:
                          type: string
                          description: Unique identifier for the call.
                        title:
                          type: string
                          description: Title of the call or meeting.
                        started:
                          type: string
                          format: date-time
                          description: Timestamp when the call started.
                        duration:
                          type: integer
                          description: Duration of the call in seconds.
                        url:
                          type: string
                          format: uri
                          description: URL to access the call recording or details.
                        content:
                          type: string
                          description: Transcript content of the call.
        '400':
          description: Invalid request. Possibly due to missing or invalid `callIds` parameter.
        '401':
          description: Unauthorized access due to invalid or missing API key.
        '500':
          description: Internal server error.
```


*有想要我們優先處理的整合嗎？我們的整合有錯誤嗎？歡迎到 GitHub 提 PR 或 issue，我們會處理。*

## 重點整理

- 多個系統的整合可以拆成多個 Action，每個 Action 各有自己的 OpenAPI schema 和認證。
- Gong 這類不方便直接給 GPT 呼叫的 API，可以用 serverless middleware 包起來，順便清理回應。
- middleware 在回傳前整理資料，能減少給 ChatGPT 的雜訊和 token。
- Custom GPT instructions 負責定義步驟順序，像是先查 Salesforce 拿 Call ID，再取 Gong 逐字稿。
- 用 MEDPICC、SPICED 這類框架引導摘要，輸出會比較結構化。

## 練習

1. 在 middleware 程式裡，把回傳的逐字稿欄位只留下發言者和文字，看回應大小變化。
2. 修改 instructions 的 (3)，改成查你自己物件的 Call ID 欄位名稱。
3. 在 instructions 裡把摘要框架從 MEDPICC 換成 SPICED，比較 GPT 輸出的結構。
