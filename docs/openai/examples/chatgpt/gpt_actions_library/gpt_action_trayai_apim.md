---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_trayai_apim.md
---

# GPT Actions 程式庫：Tray.ai APIM

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_trayai_apim.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_trayai_apim.md)



## 這篇在做什麼
說明怎麼把 ChatGPT 的 GPT Action 接到 Tray.ai 的 API Management 操作。Tray.ai 專案裡匯出的 API spec 貼進 Custom GPT，再用 Bearer token 設定驗證。

## 學完你會
- 把 Tray.ai 專案的 OpenAPI spec 貼進 Custom GPT 的 action schema
- 在 Tray.ai 建 role、policy、client 取得 API token
- 在 ChatGPT 用 API Key（Bearer）設定驗證並排除常見錯誤

## 開跑前
需要 Tray.ai 帳號，以及一個含簡單 API Management operations 的專案。

## 簡介

這一頁是給開發者的說明與指南，幫你跨多個應用程式建立一組 GPT Actions。開始之前，請先熟悉下面這些資訊：
- [Introduction to GPT Actions](https://platform.openai.com/docs/actions)
- [Introduction to GPT Actions Library](https://platform.openai.com/docs/actions/actions-library)
- [Example of Building a GPT Action from Scratch](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 概述怎麼連接 **Tray.ai API Management Operations**。

### 價值與商業使用情境範例

**價值**：使用者現在可以用 ChatGPT 的自然語言能力，直接連到透過 Tray.ai API Management 建立的 API。

**使用情境範例**：
- Tray.ai 是中介軟體，可以組合 workflow、處理 workflow action 的擴展，並串接數百個第三方 API
- 你有自訂的 operation 跑在 Tray.ai workflow 裡，想把它整合進 GPT
- 你想用單一 API 介面管理組織或團隊對 action 的存取權限

## 應用程式資訊

### 應用程式重要連結

開始之前可以先看應用程式提供的這些連結：
- 應用程式網站：https://tray.ai/universal-automation-cloud/api-management
- 應用程式 API 文件：https://tray.ai/documentation/tray-uac/api-management/api-management-overview/

### 應用程式前置條件

開始之前，請先在你的 Tray.ai 環境完成這些步驟：
- 建立 Tray.ai 帳號
- 建立一個專案，裡面有一組簡單的 API Management operations

### 應用程式 workflow 步驟

下面是建立並擴充一組基本 API Management operations 的範例：\
![Tray.ai APIM Create Operation Gif](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_trayai_createoperation.gif)

## ChatGPT 的步驟

### Custom GPT Instructions

建好 Custom GPT 之後，你應該在 Instructions 裡提供 GPT 的角色，以及它能執行哪些 action 的背景說明。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

### OpenAPI Schema

建好 Custom GPT 之後，從你的 Tray.ai 專案下載 API specification，複製內容，貼到 Custom GPT 的 action schema。貼上之後，把 schema 的 `openapi` 屬性更新成 `3.1.0` 版。

下面是設定這個第三方應用程式驗證的說明。有疑問的話，看 [Getting Started Example](https://platform.openai.com/docs/actions/getting-started) 了解這一步的細節。

### Action 前置步驟

在 ChatGPT 設定驗證之前，請先在應用程式裡做這些步驟：
- 建立一個名為 `full` 的新 role
- 建立一個新 policy，指定名稱、允許的 operations，以及 policy 規則 `"Authentication" == True` 且 role 為 `full`
- 建立一個新 client，role 設為 `full`
- 儲存你的 API Token，後面的步驟會用到

![Tray.ai APIM Create Operation Gif](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/gptactions_trayai_createclientcredential.gif)


### 在 ChatGPT 裡

在 ChatGPT 點「Authentication」並選 **"API Key"**，填入下面的資訊。

- **API Key**：（貼上 Tray.ai API Management Client 提供的 API Key）
- **Auth Type**：Bearer

### FAQ 與疑難排解

- *Auth/Forbidden 錯誤：* 確認 API key 有正確填入，而且 `Auth Type` 設成 `Bearer`。
- *Tray.ai Internal Error：* 你可以設定錯誤處理並回傳錯誤訊息，把回應送回你的 CustomGPT。

## 重點整理
- GPT Action 就是把一份 OpenAPI schema 貼進 Custom GPT，讓 ChatGPT 能呼叫外部 API。
- Tray.ai APIM 讓你用單一 API 介面管理多個 workflow operation 的存取。
- 驗證靠 Tray.ai 端的 role、policy、client 產生 token，在 ChatGPT 端用 Bearer 的 API Key 帶入。
- 貼進來的 schema 要把 `openapi` 版本改成 `3.1.0`。

## 練習
1. 在 Tray.ai 專案多加一個 operation，重新下載 spec 貼進 Custom GPT，測試新 action。
2. 在 Custom GPT 的 Instructions 寫清楚每個 action 該在什麼情況下呼叫。
3. 故意把 `Auth Type` 改成錯的值，觀察錯誤訊息，再照 FAQ 修好。
