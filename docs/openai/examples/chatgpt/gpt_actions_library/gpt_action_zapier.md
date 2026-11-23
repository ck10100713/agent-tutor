---
translated: true
source: examples/chatgpt/gpt_actions_library/gpt_action_zapier.ipynb
---

# GPT Actions 函式庫：Zapier

> 原文：[examples/chatgpt/gpt_actions_library/gpt_action_zapier.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/gpt_actions_library/gpt_action_zapier.ipynb)



## 這篇在做什麼

說明怎麼把自訂 GPT 接到 Zapier，讓 GPT 一次取得 Zapier 上數千個 app 和兩萬多個 action。大部分設定都在 Zapier 那邊做，ChatGPT 這邊只要用 URL 匯入 OpenAPI 設定。

## 學完你會

- 在 Zapier 的 AI Action Manager 設定要開放給 GPT 的 action
- 在 ChatGPT 的 GPT 建立畫面，用 "Import from URL" 匯入 Zapier 的 OpenAPI 設定
- 想出 Zapier 加 GPT 適合的使用情境，例如行事曆助理或 CRM 助理

## 開跑前

- Zapier 帳號，並先在 [AI Action Manager](https://actions.zapier.com/gpt/actions/) 設好要用的 AI Actions
- 能建立自訂 GPT 的 ChatGPT 帳號

## 簡介

這一頁是給開發者的指南，說明如何為特定應用程式建立 GPT Action。開始之前，請先熟悉下面這些資訊：
- [GPT Actions 簡介](https://platform.openai.com/docs/actions)
- [GPT Actions Library 簡介](https://platform.openai.com/docs/actions/actions-library)
- [從零建立 GPT Action 的範例](https://platform.openai.com/docs/actions/getting-started)

這個 GPT Action 概述如何把 GPT 連到 **Zapier**。因為大部分設定都在 Zapier 上進行，建議先看 ***[Zapier 提供的這份連接 GPT 與自訂 Zapier Actions 的指南](https://actions.zapier.com/docs/platform/gpt)***。

### 價值與範例商業情境

**價值**：使用者現在可以把 ChatGPT 裡的自訂 GPT 連到 Zapier，立即整合整個技術堆疊裡 6,000 多個 app 和 20,000 多個 action。

**範例情境**：
- 組織已經設好 Zapier 整合，想在把技術生態系連到 ChatGPT 時，避免額外的整合工作
- 做一個行事曆助理 GPT，查詢行事曆事件，並根據與會者的 LinkedIn 資料補充背景
- 做一個 CRM GPT，把 Hubspot 連到 ChatGPT，讓業務團隊隨時更新或查看聯絡人與備註


## 應用程式資訊

### 應用程式重要連結

開始之前，先看看應用程式提供的這些連結：
- 應用程式網站：https://zapier.com
- AI Actions URL：https://actions.zapier.com/gpt/actions/
- 自動 OpenAPI 設定：https://actions.zapier.com/gpt/api/v1/dynamic/openapi.json?tools=meta

### 應用程式前置需求

開始之前，先在 Zapier 完成下面這一步：
- 透過 [AI Action Manager](https://actions.zapier.com/gpt/actions/) 設定想要的 AI Actions

![zapier_ai_actions.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/zapier_ai_actions.png)

![zapier_action_config.png](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/zapier_action_config.png)

### 在 ChatGPT 裡

在 ChatGPT 的自訂 GPT 建立畫面點 "Actions"，選 **"Import from URL"**。輸入 Zapier 提供給 GPT 的 URL：https://actions.zapier.com/gpt/api/v1/dynamic/openapi.json?tools=meta

*有想優先支援的整合嗎？整合有錯誤嗎？歡迎到我們的 github 提 PR 或 issue，我們會處理。*


## 重點整理

- 用 Zapier 當中介，GPT 不用逐一接各家 API，就能碰到大量 app。
- 設定主要在 Zapier：先決定開放哪些 action，GPT 才看得到。
- ChatGPT 端靠 OpenAPI 的 URL 匯入，Zapier 會依你設定的 action 動態產生內容。
- 適合已經有 Zapier 整合的組織，省掉重做整合的工作。

## 練習

1. 在 AI Action Manager 新增一個簡單的 action（例如查行事曆），再重新匯入，確認 GPT 看得到。
2. 修改匯入 URL 的 `tools` 參數以外的設定前，先打開 URL 看 OpenAPI 內容，找出你設定的 action 對應哪個 operation。
3. 寫下一段 GPT 的 instructions，讓它在使用者問行程時主動呼叫行事曆 action。
