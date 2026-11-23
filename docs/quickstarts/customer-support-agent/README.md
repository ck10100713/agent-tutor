---
translated: true
source: customer-support-agent/README.md
---
# Claude Customer Support Agent

> 原文：[customer-support-agent/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/customer-support-agent/README.md)

## 這篇在做什麼

這是一個用 Claude 驅動的客服聊天介面，知識檢索靠 Amazon Bedrock Knowledge Bases（RAG）。前端用 Next.js 和 shadcn/ui，可以顯示 agent 的思考、除錯資訊和引用的知識來源，也會偵測使用者情緒並轉接給適當的 agent。

## 學完你會

- 把專案跑起來，設好 Claude API key 和 AWS 憑證
- 建立自己的 Bedrock knowledge base，並接到 `ChatArea.tsx`
- 切換 Claude 模型、客製 UI 主題，並用 AWS Amplify 部署

## 開跑前

- Node.js 20 以上
- Claude API key
- AWS 帳號（有 Bedrock 權限）、IAM 使用者的 access key 和 secret
- 一個 Bedrock knowledge base（下面有建立步驟）

![preview](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/preview.png)

## 主要功能

-  用 Anthropic 的 Claude 模型做 AI 聊天
-  整合 Amazon Bedrock 做有 context 的知識檢索
-  即時顯示思考與除錯資訊
-  知識庫來源視覺化
-  偵測使用者情緒，並轉接適當的 agent
-  用 shadcn/ui 元件，UI 高度可客製

##  開始使用

1. Clone 這個 repo
2. 安裝相依套件：`npm install`（需要 Node.js 20 以上；app 使用 Anthropic TypeScript SDK，`@anthropic-ai/sdk` v1.x）
3. 設定環境變數（見設定一節）
4. 啟動開發伺服器：`npm run dev`
5. 用瀏覽器開 [http://localhost:3000](http://localhost:3000)

## ⚙️ 設定

在根目錄建立 `.env.local`，放這些變數：

```
ANTHROPIC_API_KEY=your_anthropic_api_key
BAWS_ACCESS_KEY_ID=your_aws_access_key
BAWS_SECRET_ACCESS_KEY=your_aws_secret_key
```

注意：AWS 的環境變數前面多加了一個「B」，原因在後面的部署一節會說明。

##  怎麼拿到你的 key

### Claude API Key

1. 到 [console.anthropic.com](https://console.anthropic.com/dashboard)
2. 註冊或登入帳號
3. 點「Get API keys」
4. 複製 key，貼到 `.env.local`

### AWS Access Key 和 Secret Key

照這些步驟取得 AWS 憑證：

1. 登入 AWS Management Console
2. 進入 IAM（Identity and Access Management）儀表板

3. 在左側選單點「Users」

4. 點「Create user」，照提示建立新使用者
   ![Add User](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/create-user.png)
5. 在 Set Permission 頁選「Attach policies directly」
   ![Attach Policy](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/attach.png)
5. 在權限頁使用「AmazonBedrockFullAccess」policy
   ![Attach Policy](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/bedrock.png)
6. 檢查並建立使用者
7. 在 Summary 頁點 Create access key。
8. 接著選「Application running on an AWS compute service」。想的話加個描述，然後點「Create」。
9. 這時會顯示 Access Key ID 和 Secret Access Key。注意這些 key 只會在建立時顯示一次，務必安全地保存。
   ![Access Keys](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/access-keys.png)
8. 把這兩個 key 複製到 `.env.local`

注意：務必保管好你的 key，不要公開分享。

##  Amazon Bedrock RAG 整合

這個專案用 Amazon Bedrock 做 Retrieval-Augmented Generation（RAG）。設定方式：

1. 確認你的 AWS 帳號有 Bedrock 存取權。
2. 在你想用的 AWS region 建立 Bedrock knowledge base。
3. 把你的文件／來源索引到 knowledge base。做法見「如何建立自己的 Knowledge Base」一節。
4. 在 `ChatArea.tsx` 裡，更新 `knowledgeBases` 陣列，填入你的 knowledge base ID 和名稱：

```typescript
const knowledgeBases: KnowledgeBase[] = [
  { id: "your-knowledge-base-id", name: "Your KB Name" },
  // Add more knowledge bases as needed
];
```

app 會在對話中用這些 knowledge base 做 context 檢索。

### 如何建立自己的 Knowledge Base

建立自己的 knowledge base：

1. 到 AWS Console，選 Amazon Bedrock。
2. 在左側選單的「More」下點「Knowledge base」。

3. 點「Create knowledge base」。
   ![Create Knowledge Base](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/create-knowledge-base.png)
4. 幫 knowledge base 取名。可以保留「Create a new service role」。
5. 選 knowledge base 的來源。這個範例用 Amazon S3 儲存服務。
   ![Choose Source](https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/customer-support-agent/tutorial/choose-source.png)

   注意：用 S3 的話，要先建一個 bucket 來上傳檔案。也可以等 knowledge base 建好之後再上傳檔案。

6. 點「Next」。
7. 選 knowledge base 的位置，可以是 S3 bucket、資料夾，甚至單一文件。
8. 點「Next」。
9. 選你想用的 embedding model。這裡用 Titan Text Embeddings 2。
10. 選「Quick create a new vector store」。
11. 確認並建立 knowledge base。
12. 建好之後，從 knowledge base 總覽取得 knowledge base ID。

##  切換模型

這個專案支援多個 Claude 模型。切換方式：

1. 在 `ChatArea.tsx` 裡，`models` 陣列定義了可用的模型：

```typescript
const models: Model[] = [
  { id: "claude-haiku-4-5-20251001", name: "Claude Haiku 4.5" },
  { id: "claude-sonnet-4-6", name: "Claude Sonnet 4.6" },
  // Add more models as needed
];
```

2. `selectedModel` 這個 state 變數控制目前選的模型：

```typescript
const [selectedModel, setSelectedModel] = useState("claude-haiku-4-5-20251001");
```

3. UI 上用一個下拉元件來更新 `selectedModel`，實現模型切換。

##  客製化

這個專案用 shadcn/ui 元件，客製空間很大：

* 修改 `components/ui` 目錄下的 UI 元件
* 在 `app/globals.css` 調整主題
* 在各個元件檔案裡客製版面和功能
* 編輯 `styles/themes.js` 修改主題顏色和樣式：

```javascript
// styles/themes.js
export const themes = {
  neutral: {
    light: {
      // Light mode colors for neutral theme
    },
    dark: {
      // Dark mode colors for neutral theme
    }
  },
  // Add more themes here
};
```
你可以新增主題，或調整這個檔案裡的顏色值來修改現有主題。

##  用 AWS Amplify 部署

用 AWS Amplify 部署這個應用程式的步驟：

1. 到 AWS Console，選 Amplify。
2. 點「Create new app」（圖片連結之後補上）。
3. 選 GitHub（或你偏好的 provider）當來源。
4. 選這個 repo。
5. 編輯 YAML 檔，內容改成：

   ```yaml
   version: 1
   frontend:
     phases:
       preBuild:
         commands:
           - npm ci --cache .npm --prefer-offline
       build:
         commands:
           - npm run build # Next.js build runs first
           - echo "ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY" >> .env
           - echo "KNOWLEDGE_BASE_ID=$KNOWLEDGE_BASE_ID" >> .env
           - echo "BAWS_ACCESS_KEY_ID=$BAWS_ACCESS_KEY_ID" >> .env
           - echo "BAWS_SECRET_ACCESS_KEY=$BAWS_SECRET_ACCESS_KEY" >> .env
     artifacts:
       baseDirectory: .next
       files:
         - "**/*"
     cache:
       paths:
         - .next/cache/**/*
         - .npm/**/*
   ```

6. 選擇建立新的 service role 或用既有的。參考「Service Role」一節。
7. 點「Advanced settings」，加上你的環境變數：

   ```
   ANTHROPIC_API_KEY=your_anthropic_api_key
   BAWS_ACCESS_KEY_ID=your_aws_access_key
   BAWS_SECRET_ACCESS_KEY=your_aws_secret_key
   ```
   這裡的 key 前面加「B」的原因是 AWS 不允許 Amplify 的 key 以「AWS」開頭。

8. 點「Save and deploy」開始部署。

你的應用程式就會用 AWS Amplify 部署好了。


### Service Role

應用程式部署好之後，如果你選的是建立新的 service role：

1. 到你的 deployments 頁面
2. 選剛建立的 deployment
3. 點「App settings」
4. 複製 Service role ARN
5. 到 IAM console 找到這個 role
6. 把「AmazonBedrockFullAccess」policy 附加到這個 role

這樣 Amplify app 才有權限跟 Amazon Bedrock 互動。

##  自訂部署與開發

這個專案現在支援彈性的部署與開發設定，可以依需求包含或排除特定元件（左側欄、右側欄）。
設定
側欄要不要包含，由 config.ts 檔控制，它用環境變數來設定：
```typescript
typescriptCopytype Config = {
  includeLeftSidebar: boolean;
  includeRightSidebar: boolean;
};

const config: Config = {
  includeLeftSidebar: process.env.NEXT_PUBLIC_INCLUDE_LEFT_SIDEBAR === "true",
  includeRightSidebar: process.env.NEXT_PUBLIC_INCLUDE_RIGHT_SIDEBAR === "true",
};

export default config;
```

這個設定用到兩個環境變數：

NEXT_PUBLIC_INCLUDE_LEFT_SIDEBAR：設成 "true" 就包含左側欄
NEXT_PUBLIC_INCLUDE_RIGHT_SIDEBAR：設成 "true" 就包含右側欄

## NPM Scripts
package.json 新增了幾個給不同設定用的 script：

```bash
npm run dev: Runs the full app with both sidebars (default)
npm run build: Builds the full app with both sidebars (default)
npm run dev:full: Same as npm run dev
npm run dev:left: Runs the app with only the left sidebar
npm run dev:right: Runs the app with only the right sidebar
npm run dev:chat: Runs the app with just the chat area (no sidebars)
npm run build:full: Same as npm run build
npm run build:left: Builds the app with only the left sidebar
npm run build:right: Builds the app with only the right sidebar
npm run build:chat: Builds the app with just the chat area (no sidebars)
```

用法
使用特定設定：

開發：執行想要的 script（例如 npm run dev:left）
正式環境：用想要的 script 來 build（例如 npm run build:right）

這些 script 會在執行或 build 之前設好對應的環境變數，讓你輕鬆切換不同設定。
這個彈性讓你能依需求調整 app 的版面，不論是測試、開發或正式部署。

## 附錄

這個專案是原型，以「現狀」提供，不適合用在正式環境，可能有 bug、錯誤或不一致。使用這個原型即表示你知道並同意：
- 軟體以預先發行、beta 或試用的形式提供。
- 它可能不適合正式或關鍵任務的環境。
- 開發者不對使用它造成的任何問題、資料遺失或損害負責。
- 不提供任何明示或默示的保證。
- 這個原型的支援可能有限或沒有。
- 使用風險自負。歡迎回報問題或提供回饋，幫助改善未來的版本。

## 重點整理

- 這個 app 是 Claude 加 Bedrock Knowledge Base 的 RAG 客服範例：模型負責對話，knowledge base 提供有根據的內容。
- 知識來源（S3 文件經 embedding 進 vector store）決定回答品質，換成你自己的資料就是你的客服。
- 模型和知識庫都是 `ChatArea.tsx` 裡的陣列設定，換起來只要改幾行。
- 部署到 Amplify 時 AWS 變數要加 `B` 前綴，且 service role 要另外附加 Bedrock 權限。
- 這是原型，不能直接當正式環境。

## 練習

1. 在 `ChatArea.tsx` 的 `models` 陣列加一個你想試的 Claude 模型，用下拉選單切過去比較回答。
2. 把 `styles/themes.js` 裡某個主題的顏色改掉，或新增一個主題，確認 UI 變色。
3. 設定 `NEXT_PUBLIC_INCLUDE_LEFT_SIDEBAR` 和 `NEXT_PUBLIC_INCLUDE_RIGHT_SIDEBAR`（例如用 `npm run dev:left`），比較有無側欄的版面，並看 `config.ts` 怎麼讀這兩個變數。
