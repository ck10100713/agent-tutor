---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_retool_workflow.md
---

# GPT Actions library：Retool Workflow

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_retool_workflow.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_retool_workflow.md)



## 這篇在做什麼
教你做一個連到 Retool Workflow 的 GPT Action。ChatGPT 把使用者輸入透過 webhook 觸發 Retool 的 workflow，workflow 跑完後以 JSON 回傳給 ChatGPT。

## 學完你會
- 在 Retool 建立並部署一個用 webhook 觸發的簡單 workflow
- 在 OpenAPI schema 填入你的 workflow ID，讓 GPT 能呼叫它
- 用自訂 header 的 API Key 方式在 ChatGPT 設定認證

## 開跑前
- Retool 帳號
- 一個已經 deploy 的 workflow，以及 webhook 面板上的 API Key


## 簡介

這一頁是給開發者的說明，教你替特定應用程式建 GPT Action。開始之前，請先熟悉以下內容： 
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 說明怎麼連到 **Retool Workflow**。這個 Action 接收使用者輸入，用 webhook trigger 送到 Retool 的 workflow。Retool 執行設定好的 workflow，再以 JSON 物件回傳給 ChatGPT。

### 價值與商業使用情境

**價值**：使用者現在可以用 ChatGPT 的自然語言能力，直接連到 Retool 裡的任何 workflow。

**使用情境範例**： 
- 你有自訂程式碼跑在 Retool workflow 裡，想把它整合進 GPT。 
- 資料科學家維護外部的 VectorDB（用 Retool Vector 或其他向量資料庫），想把向量搜尋結果送回 ChatGPT。 
- Retool 被當作 middleware 連接內部服務，你想用 Retool 的 webhook 讓 ChatGPT 能存取這些服務。

## 應用程式資訊

### 應用程式重要連結

開始之前，先看看這些應用程式的連結：
- 應用程式網站：https://retool.com/products/workflows
- 應用程式 API 文件：https://docs.retool.com/workflows

### 應用程式前置需求

開始之前，請先在你的 Retool 環境完成以下步驟：
- 建立 Retool 帳號
- 建立一個簡單的 workflow

### 應用程式 Workflow 步驟

下面是一個基本 Retool Workflow 的範例。這個 workflow 接收 2 個值，把它們相加，再回應 webhook trigger 傳回結果。

***注意：*** workflow 必須先 deploy，你的 GPT 才能存取。

<!--ARCADE EMBED START--><div style="position: relative; padding-bottom: calc(57.26681127982647% + 41px); height: 0; width: 100%;"><iframe src="https://demo.arcade.software/MG7PcF8fh3RH722eonUb?embed&embed_mobile=tab&embed_desktop=inline&show_copy_link=true" title="Retool Workflow Cookbook" frameborder="0" loading="lazy" webkitallowfullscreen mozallowfullscreen allowfullscreen allow="clipboard-write" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; color-scheme: light;" ></iframe></div><!--ARCADE EMBED END-->

## ChatGPT 步驟

### Custom GPT Instructions 

建好 Custom GPT 之後，要在 Instructions 裡說明這個 GPT 的角色，以及它能執行哪些 action。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

### OpenAPI Schema 

建好 Custom GPT 之後，把下面的文字複製到 Actions 面板。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

***注意：*** 你需要把下面 OpenAPI spec 裡的 __<WORKFLOW_ID>__ 換成你自己 workflow 的 ID。


```yaml
openapi: 3.1.0
info:
  title: Retool Workflow API
  description: API for interacting with Retool workflows.
  version: 1.0.0
servers:
  - url: https://api.retool.com/v1
    description: Main (production) server
paths:
  /workflows/<WORKFLOW_ID>/startTrigger:
    post:
      operationId: add_numbers
      summary: Takes 2 numbers and adds them.
      description: Initiates a workflow in Retool by triggering a specific workflow ID.
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                first:
                  type: integer
                  description: First parameter for the workflow.
                second:
                  type: integer
                  description: Second parameter for the workflow.
      responses:
        "200":
          description: Workflow triggered successfully.
        "400":
          description: Bad Request - Invalid parameters or missing data.
        "401":
          description: Unauthorized - Invalid or missing API key.
      security:
        - apiKeyAuth: []
```

## 認證設定說明

以下是設定這個第三方應用程式認證的步驟。有問題可以看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started)，裡面有這一步的詳細說明。

### Action 前的步驟

在 ChatGPT 設定認證之前，請先在應用程式裡完成以下步驟。
- 從 Webhook 設定面板取得你的 API Key

![retool_api_key.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/retool_api_key.png)

### 在 ChatGPT 裡

在 ChatGPT 點「Authentication」，選 **"API Key"**，填入下列資訊。 

- **API Key**：（貼上 Retool Workflow Webhook Trigger 提供的 API Key）
- **Auth Type**：Custom
- **Custom Header Name**：X-Workflow-Api-Key

### FAQ 與疑難排解

- *認證錯誤：* 確認 custom header name 有設對。
- *Invalid Workflow 錯誤：* 確認你已在 Retool 裡 deploy 了 workflow。

*有想要我們優先支援的整合嗎？我們的整合有錯誤嗎？歡迎在 GitHub 提 PR 或 issue，我們會處理。*

## 重點整理
- 這個 Action 的做法是把 Retool workflow 當成 webhook API，讓 ChatGPT 用 HTTP 呼叫它。
- Retool 很適合當 middleware，連內部服務、跑自訂程式碼或查向量資料庫。
- workflow 一定要 deploy 才能被呼叫，OpenAPI spec 裡的 workflow ID 也要換成自己的。
- 認證用 API Key 搭配自訂 header 名稱，名稱錯了就會出認證錯誤。
- Instructions 要講清楚 GPT 的角色和可執行的 action。

## 練習
1. 在 Retool 建一個接收兩個數字相加的 workflow，deploy 後把 workflow ID 填進 OpenAPI spec 測試。
2. 把 workflow 改成相乘，確認 GPT 的回答跟著變。
3. 故意把 Custom Header Name 寫錯，看出現什麼錯誤，再改回來。
