---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_github.md
---

# GPT Actions 範例庫：GitHub

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_github.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_github.md)



## 這篇在做什麼
教你把 GPT Action 接到 GitHub，做一個 Pull Request 審查助理。它會抓 PR 的 diff，針對品質和安全給建議，你確認後再自動以留言貼回 PR。

## 學完你會
- 建立 fine-grained GitHub Personal Access Token，並設好需要的權限。
- 用 OpenAPI schema 定義「GET PR diff」和「POST 留言到 PR」兩個 action。
- 在 GPT 設定 Bearer 驗證，並用 owner、repo、PR 編號做測試。

## 開跑前
- 需要一個有 open pull request 的 GitHub repo。
- 需要 GitHub Personal Access Token；如果 repo 屬於 SSO 組織，token 可能還需要組織核准。
- 需要能建立 Custom GPT 的 ChatGPT 帳號。

## 簡介

這一頁是給開發者的指南，說明怎麼把 GPT Action 接到 GitHub。開始之前，先看過這些資料：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 幫開發者評估 GitHub Pull Request diff 的品質和安全性。它針對每個面向提供回饋和建議，讓開發者可以修改或接受回饋，再自動以留言的方式送到 Pull Request 上。

## 價值與商業使用情境

### **價值**：
使用者可以利用 ChatGPT 的自然語言能力輔助 GitHub Pull Request 審查。

- **對開發者**：分析程式碼變更，即時得到對修改的回饋，做出高品質的 review。
- **對組織**：確保 diff 符合最佳實務和程式碼規範，或自動提出重構的替代方案（要定義最佳實務可能需要額外的 API 請求）。
- **整體**：這個 AI 驅動的 Code Review 助理能提升生產力，並確保程式碼品質更高、更安全。

### **使用情境範例**：
- Reviewer 想知道一個程式碼變更的品質和安全性。
- 組織希望在 code review 時自動落實最佳實務和標準。

## 示範影片：
[![Watch the video](https://img.youtube.com/vi/bcjybCh-x-Q/0.jpg)](https://www.youtube.com/watch?v=bcjybCh-x-Q)

## 應用程式資訊

### **重要連結**
開始之前，先看看這些資源：
- [GitHub](https://github.com)
- [GitHub API Documentation](https://docs.github.com/en/rest/pulls?apiVersion=2022-11-28)

### **前置需求**
確定你有一個有 open pull request 的 repository。

## 應用程式設定

### **選一個 Pull Request**
1. 進到某個 repository，例如[範例 PR](https://github.com/microsoft/vscode/pull/229241)。
   - 記下 owner（例如 "microsoft"）、repository 名稱（例如 "vscode"）和 PR 編號（例如 "229241"）。
   - 如果 repository 的 owner 是 SSO 組織，你的 token 可能需要[核准](https://docs.github.com/en/organizations/managing-programmatic-access-to-your-organization/managing-requests-for-personal-access-tokens-in-your-organization#managing-fine-grained-personal-access-token-requests)。
2. 看一下[怎麼做高品質的 code review](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/getting-started/best-practices-for-pull-requests)。

### **產生 "Fine Grained" GitHub Personal Access Token**
1. 登入 GitHub，進到 **Settings**。
2. 前往 **Developer settings** > **Fine Grained Personal access tokens**。
3. 點 **Generate new token**，取名字、設到期日，並選必要的 scope（例如 `read:content`、`read&write:pull_requests`）。
4. 複製 token 並安全保存。

## ChatGPT 的步驟

### **Custom GPT Instructions**

建好 Custom GPT 之後，把下面內容複製到 Instructions 欄位：

```
# **Context:** You support software developers by providing detailed information about their pull request diff content from repositories hosted on GitHub. You help them understand the quality, security and completeness implications of the pull request by providing concise feedback about the code changes based on known best practices. The developer may elect to post the feedback (possibly with their modifications) back to the Pull Request. Assume the developer is familiar with software development.

# **Instructions:**

## Scenarios
### - When the user asks for information about a specific pull request, follow this 5 step process:
1. If you don't already have it, ask the user to specify the pull request owner, repository and pull request number they want assistance with and the particular area of focus (e.g., code performance, security vulnerabilities, and best practices).
2. Retrieve the Pull Request information from GitHub using the getPullRequestDiff API call, owner, repository and the pull request number provided. 
3. Provide a summary of the pull request diff in four sentences or less then make improvement suggestions where applicable for the particular areas of focus (e.g., code performance, security vulnerabilities, and best practices).
4. Ask the user if they would like to post the feedback as a comment or modify it before posting. If the user modifies the feedback, incorporate that feedback and repeat this step. 
5. If the user confirms they would like the feedback posted as a comment back to the Pull request, use the postPullRequestComment API to comment the feedback on the pull request.
```

### OpenAPI Schema

建好 Custom GPT 之後，把下面的文字複製到 Actions 欄位。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

下面是連到 GitHub 做 GET Pull Request Diff 和 POST Pull Request 回饋的範例。

```javascript
openapi: 3.1.0
info:
  title: GitHub Pull Request API
  description: Retrieve the diff of a pull request and post comments back to it.
  version: 1.0.0
servers:
  - url: https://api.github.com
    description: GitHub API
paths:
  /repos/{owner}/{repo}/pulls/{pull_number}:
    get:
      operationId: getPullRequestDiff
      summary: Get the diff of a pull request.
      parameters:
        - name: owner
          in: path
          required: true
          schema:
            type: string
          description: Owner of the repository.
        - name: repo
          in: path
          required: true
          schema:
            type: string
          description: Name of the repository.
        - name: pull_number
          in: path
          required: true
          schema:
            type: integer
          description: The number of the pull request.
        - name: Accept
          in: header
          required: true
          schema:
            type: string
            enum:
              - application/vnd.github.v3.diff
          description: Media type for the diff format.
      responses:
        "200":
          description: Successfully retrieved the pull request diff.
          content:
            text/plain:
              schema:
                type: string
        "404":
          description: Pull request not found.
  /repos/{owner}/{repo}/issues/{issue_number}/comments:
    post:
      operationId: postPullRequestComment
      summary: Post a comment to the pull request.
      parameters:
        - name: owner
          in: path
          required: true
          schema:
            type: string
          description: Owner of the repository.
        - name: repo
          in: path
          required: true
          schema:
            type: string
          description: Name of the repository.
        - name: issue_number
          in: path
          required: true
          schema:
            type: integer
          description: The issue or pull request number.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                body:
                  type: string
                  description: The content of the comment.
      responses:
        "201":
          description: Successfully created a comment.
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: integer
                  body:
                    type: string
                  user:
                    type: object
                    properties:
                      login:
                        type: string
                      id:
                        type: integer
        "404":
          description: Pull request not found.
```

## 驗證設定

下面說明怎麼對這個第三方應用程式設定驗證。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

### 在 ChatGPT 裡（參考 Getting Started Example 的 Step 2）

在 ChatGPT 點 "Authentication"，選 **"Bearer"**，填入下面資訊。確定你的 token 有上面應用程式設定中說明的權限。

- Authentication Type: API Key
- Auth Type: Bearer
- API Key 
  <personal_access_token>

### 測試 GPT

現在可以測試這個 GPT 了。你可以輸入簡單的 prompt，例如 "Can you review my pull request? owner: <org_name>, repo: <repo_name>, pull request number: <PR_Number>"，預期會看到：

![landing_page.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/../images/landing_page.png)

1. 所引用 pull request（PR）的變更摘要。

![First Interaction](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/first_interaction.png)

2. 品質和安全的回饋，以及下一版 PR 可以採納的建議。

![First Feedback](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/first_feedback.png)

3. 可以選擇繼續調整回饋，或接受它，讓 GPT 直接以你的名義把它當留言貼到 PR 上。 

![First Interaction](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/final_result.png)

*有想要我們優先處理的整合嗎？我們的整合有錯誤嗎？到我們的 github 開 PR 或 issue，我們會去看。*

## 重點整理
- GPT Action 的核心是三件事：Instructions 定義行為、OpenAPI schema 定義能呼叫的 API、Authentication 提供憑證。
- 這個範例只需要兩個 API：取得 PR diff、對 PR 貼留言。
- Fine-grained token 只給必要權限，比較安全。
- 流程設計成讓人先確認回饋再送出，避免 GPT 直接對外發言。

## 練習
1. 在 Instructions 裡加一條規則，要求回饋一定要分成「品質」和「安全」兩個段落。
2. 修改 token 權限，拿掉 `read&write:pull_requests` 的寫入權限，測試 GPT 貼留言時會出什麼錯。
3. 在 OpenAPI schema 加一個 GET 操作，取得 PR 的檔案清單，並在 Instructions 說明何時使用。
