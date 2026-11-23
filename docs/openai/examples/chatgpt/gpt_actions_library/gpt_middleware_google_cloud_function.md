---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function.md
---
# GPT Actions library（Middleware）：Google Cloud Function

> 原文：[examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_middleware_google_cloud_function.md)

## 這篇在做什麼

教你寫一個 middleware，讓 GPT Action 透過它接到別的應用。這裡用 Google Cloud Function 當 middleware，加上 OAuth 保護，再接到 Custom GPT。這樣 ChatGPT 可以先經過你的函式處理資料，再拿到結果。

## 學完你會

- 用 `gcloud` 在本機建一個 Node.js 的 Google Cloud Function 並部署
- 寫出對應的 OpenAPI schema 和 Custom GPT instructions
- 在 Google Cloud 建 OAuth client，並在 ChatGPT 和 GCP 兩邊設好授權與 callback URL

## 開跑前

- 一個有權限建立 Cloud Functions 和 Google Cloud API 的 Google Cloud Console 帳號
- ChatGPT 帳號可以建立 Custom GPT

## 簡介

這頁是給開發者的說明，教你怎麼寫 middleware，把 GPT Action 接到特定應用。開始之前，先看過下面這些資料：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 會說明怎麼建立 **Google Cloud Function**（Google 的雲端函式服務）。文件會帶你設定一個受 OAuth 保護的 Google Cloud Function，把它連到 GPT Action 和一個範例應用。

### 價值與商業使用情境

**價值**：使用者可以靠 ChatGPT 的自然語言能力直接連到 Google Cloud Function，好處有幾個：

- GPT Actions 有 10 萬字元的限制：可以用 middleware 先處理 API 回傳的文字。例如在 middleware 裡用 OpenAI 的 API 先做摘要，再回傳給 ChatGPT。
- 一般 action 都是靠 SaaS API 回傳文字。你可以把廠商 API 的回應轉成容易讀的文字，結構化和非結構化資料都能處理。
- 它可以回傳檔案，不只是文字。例如回傳 CSV 檔給 Data Analysis 用，或回傳 PDF，ChatGPT 會把它當成使用者上傳的檔案。


**範例使用情境**：
- 使用者要查 Google Cloud SQL，但 ChatGPT 和 Google Cloud SQL 之間需要一個 middleware 應用
- 使用者在 Google Cloud function 裡串好了好幾個步驟，需要能用 ChatGPT 啟動這整個流程

## 應用資訊

### 應用相關連結

開始之前先看看這些連結：
- 應用網站：https://cloud.google.com/functions/docs
- 應用 API 文件：https://cloud.google.com/functions/docs/writing/write-http-functions

### 應用前置條件

開始之前，先在你的應用環境準備好：
- 有權限建立 Google Cloud Functions 和 Google Cloud API 的 Google Cloud Console（設定 OAuth Client 會用到）

## 應用設定

### 安裝應用

建立並部署 Google Cloud Functions 有 3 種方式

*   IDE：用你慣用的 IDE 建立，例如 VS Code
*   Google Cloud Console：用瀏覽器建立
*   Google Cloud CLI (gcloud)：用命令列建立

支援的 runtime 可以看[這裡](https://cloud.google.com/functions/docs/concepts/execution-environment)

#### 方式 1：用 IDE（VSCode）

怎麼用 VSCode 部署，看 Google 的[文件](https://cloud.google.com/functions/docs/create-deploy-ide)。如果你熟這種做法，就直接用。


#### 方式 2：直接在 Google Cloud Console

怎麼用 Google Cloud Console 部署，看[這份文件](https://cloud.google.com/functions/docs/console-quickstart)。

#### 方式 3：用 Google Cloud CLI（`gcloud`）

怎麼用命令列部署，看[這份文件](https://cloud.google.com/functions/docs/create-deploy-gcloud)。這裡我們一步一步走一遍範例。


##### 第 1 部分：安裝並初始化 Google Cloud CLI（`gcloud`）
照[這裡](https://cloud.google.com/sdk/docs/install)中符合你作業系統的步驟安裝。最後一步是執行 `gcloud init` 並登入你的 Google 帳號

##### 第 2 部分：設定本機開發環境
這個範例用 Node.js 環境。

```
mkdir <directory_name>
cd <directory_name>
```

初始化 Node.js 專案

```
npm init
```
`npm init` 的問題都用預設值就好

##### 第 3 部分：建立 Function
建立 `index.js` 檔

```
const functions = require('@google-cloud/functions-framework');
const axios = require('axios');

const TOKENINFO_URL = 'https://oauth2.googleapis.com/tokeninfo';

// Register an HTTP function with the Functions Framework that will be executed
// when you make an HTTP request to the deployed function's endpoint.
functions.http('executeGCPFunction', async (req, res) => {
  const authHeader = req.headers.authorization;

  if (!authHeader) {
    return res.status(401).send('Unauthorized: No token provided');
  }

  const token = authHeader.split(' ')[1];
  if (!token) {
    return res.status(401).send('Unauthorized: No token provided');
  }

  try {
    const tokenInfo = await validateAccessToken(token);            
    res.json("You have connected as an authenticated user to Google Functions");
  } catch (error) {
    res.status(401).send('Unauthorized: Invalid token');
  }  
});

async function validateAccessToken(token) {
  try {
    const response = await axios.get(TOKENINFO_URL, {
      params: {
        access_token: token,
      },
    });
    return response.data;
  } catch (error) {
    throw new Error('Invalid token');
  }
}
```
##### 第 4 部分：部署 Function

下面這步會安裝需要的依賴，並加進 `package.json`

```
npm install @google-cloud/functions-framework
npm install axios
```

```
npx @google-cloud/functions-framework --target=executeGCPFunction
```

```
gcloud functions deploy gcp-function-for-chatgpt \
  --gen2 \
  --runtime=nodejs20 \
  --region=us-central1 \
  --source=. \
  --entry-point=executeGCPFunction \
  --trigger-http \
  --allow-unauthenticated
```

## ChatGPT 的步驟

### Custom GPT Instructions

建好 Custom GPT 之後，把下面的文字複製到 Instructions 面板。有疑問可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

```
When the user asks you to test the integration, you will make a call to the custom action and display the results
```

### OpenAPI Schema

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有疑問可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。

下面是連到這個 Middleware 的範例，你需要在這段填入自己的應用和函式資訊。

```javascript
openapi: 3.1.0
info:
  title: {insert title}
  description: {insert description}
  version: 1.0.0
servers:
  - url: {url of your Google Cloud Function}
    description: {insert description}
paths:
  /{your_function_name}:
    get:
      operationId: {create an operationID}
      summary: {insert summary}
      responses:
        '200':
          description: {insert description}
          content:
            text/plain:
              schema:
                type: string
                example: {example of response}
```

## 驗證設定

下面說明怎麼設定這個第三方應用的驗證。有疑問可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有更詳細的說明。


### 在 Google Cloud Console

在 Google Cloud Console 要建立 OAuth client ID 憑證。到對應頁面的方式是在 Google Cloud Console 搜尋 "Credentials"，或在瀏覽器輸入 `https://console.cloud.google.com/apis/credentials?project=<your_project_id>`。更多說明看[這裡](https://developers.google.com/workspace/guides/create-credentials)。

點 "CREATE CREDENTIALS" 並選 "Oauth client ID"。"Application type" 選 "Web Application"，並填入應用名稱（見下圖）。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gcp-function-middleware-oauthclient.png)

在跳出的 "OAuth client created" 對話框裡，記下

* Client ID
* Client secret


### 在 ChatGPT（對照 Getting Started Example 的 Step 2）

在 ChatGPT 點 "Authentication"，選 **"OAuth"**，填入下面的資訊。

- **Client ID**：見上一步
- **Client Secret**：見上一步
- **Authorization URL**：`https://accounts.google.com/o/oauth2/auth`
- **Token URL**：`https://oauth2.googleapis.com/token`
- **Scope**：`https://www.googleapis.com/auth/userinfo.email`

### 回到 Google Cloud Console（對照 Getting Started Example 的 Step 4）

編輯你稍早在 Google Cloud 建立的 OAuth 2.0 Client ID，加上建立 custom action 後拿到的 callback URL。

![](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gcp-function-middleware-oauthcallback.png)

### 測試 GPT

現在可以測試這個 GPT 了。輸入簡單的 prompt，例如 "Test Integration"，應該會看到：

1. 要求登入 Google
2. 允許對你的 Google Function 的請求
3. ChatGPT 顯示函式回傳的回應，例如 "You have connected as an authenticated user to Google Functions"

*有想優先支援的整合嗎？我們的整合有錯誤嗎？到我們的 github 開 PR 或 issue，我們會處理。*

## 重點整理

- Middleware 的用途是夾在 ChatGPT 和 SaaS API 之間：先前處理文字（例如摘要來避開 10 萬字元限制）、轉換資料格式，或回傳檔案。
- Google Cloud Function 可以用 IDE、Console 或 `gcloud` 三種方式部署，做法不同但結果一樣。
- GPT Action 要接受保護的函式，靠的是 OpenAPI schema 加 OAuth 設定。
- OAuth 要兩邊互相填：GCP 產生 Client ID 和 secret 給 ChatGPT，ChatGPT 產生 callback URL 再填回 GCP。

## 練習

1. 照 `gcloud` 的步驟部署一個回傳固定文字的函式，用 "Test Integration" 測試整條流程。
2. 修改 `index.js`，讓函式回傳目前時間或你自己的 JSON，並同步更新 OpenAPI schema 中的回應描述。
3. 在函式裡呼叫 OpenAI API，把一段很長的文字摘要後再回傳給 ChatGPT。
