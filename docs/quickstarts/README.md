---
translated: true
source: README.md
---

# Claude Quickstarts

> 原文：[README.md](https://github.com/anthropics/claude-quickstarts/blob/main/README.md)

## 這篇在做什麼

這是 Claude Quickstarts 的總目錄，列出官方提供的各種範例專案，從客服 agent、computer use 到 Managed Agents 系列。每個專案都是可以直接改的起點。

## 學完你會

- 知道有哪些官方 quickstart，並挑出跟你需求最接近的那個
- 照通用步驟 clone、安裝並跑起任何一個 quickstart
- 分辨 Agent SDK、computer use、Managed Agents 這幾類範例各自示範什麼

## 開跑前

- 需要 Claude API key，可到 [console.anthropic.com](https://console.anthropic.com) 免費註冊

Claude Quickstarts 是一組專案集合，幫開發者快速上手用 Claude API 做應用。每個 quickstart 都提供一個基礎，你可以在上面直接延伸、客製成自己要的東西。

## 開始使用

要用這些 quickstart，你需要 Claude API key。還沒有的話，可以到 [console.anthropic.com](https://console.anthropic.com) 免費註冊。

## 可用的 Quickstart

### Customer Support Agent

用 Claude 做的客服 agent。這個專案示範怎麼運用 Claude 的自然語言理解和生成能力，做出能存取知識庫的 AI 輔助客服系統。

[Go to Customer Support Agent Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/customer-support-agent)

### Financial Data Analyst

用 Claude 做的財務資料分析師。這個專案示範怎麼結合互動式資料視覺化，讓使用者用聊天的方式分析財務資料。

[Go to Financial Data Analyst Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/financial-data-analyst)

### Computer Use Demo

讓 Claude 控制桌面電腦的環境和 tool。這個專案示範怎麼運用 Claude 的 computer use 能力，包括支援最新的 `computer_toolset_20260801` toolset 形式，每個電腦操作都是模型用名稱呼叫的成員 tool。

[Go to Computer Use Demo Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-demo)

### Computer Use Best Practices

教學用的原生 macOS computer-use agent 參考實作。跟容器化的 Computer Use Demo 不同，這個專案直接跑在 macOS 桌面上（請在 VM 裡跑！），示範讓 computer-use agent 更可靠、更省成本的常見做法：明確的 tool 定義、正確的圖片尺寸與裁剪、prompt caching、server-side compaction、批次 tool call、sandboxed shell 和 trajectory 錄製。搭配 Anthropic 的 [computer-use best-practices guide](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude) 一起看。

[Go to Computer Use Best Practices Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-best-practices)

### Browser Use Demo

用 Claude 做瀏覽器自動化的完整參考實作。這個專案示範怎麼用自訂的 Playwright 瀏覽器 tool，讓 Claude 能瀏覽網站、檢視並操作 DOM 元素、擷取內容和填表單。

[Go to Browser Use Demo Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo)

### Browser Toolset Quickstart

Claude 瀏覽器 toolset（`browser_toolset_20260801`）的最小 CDP 範例，有 Python 和 TypeScript 版。包含一個透過 Chrome DevTools Protocol 驅動單一 Chromium 分頁的小 driver、一支用 tool runner 跑這個 driver 的 script，以及一支不用模型就能測試的 script。它只示範介面，不是 production 程式碼。

[Go to Browser Toolset Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/browser-toolset)

### Computer Toolset Quickstart

Claude computer toolset（`computer_toolset_20260801`）的最小 VNC 範例，有 Python 和 TypeScript 版。包含一個透過 VNC（RFB protocol，不用 VNC 函式庫）驅動單一桌面的小 driver、一支用 tool runner 跑這個 driver 的 script，以及一支不用模型就能測試的 script。它只示範介面，不是 production 程式碼。

[Go to Computer Toolset Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/computer-toolset)

### Autonomous Coding Agent

用 Claude Agent SDK 做的自主 coding agent。這個專案示範雙 agent 模式（initializer + coding agent），能跨多個 session 建出完整應用，進度靠 git 保存，並有一份 agent 逐步完成的功能清單。

[Go to Autonomous Coding Agent Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/autonomous-coding)

### Managed Agents: Chat SDK

用 Claude Managed Agents 和 Vercel 的 Chat SDK 做的瀏覽器聊天 app。這個專案示範每段對話配一個持久的 Managed Agents session，並接上聊天介面：research analyst 用 web search 查資料，把報告一個 token 一個 token 串流出來，同時有即時 feed 顯示 tool call。換掉 Chat SDK adapter，同一個 handler 就能跑在 Slack、Teams、Discord、Telegram 或 WhatsApp。

[Go to Managed Agents Chat SDK Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/chat-sdk)

### Managed Agents with CopilotKit and AG-UI

建在 Claude Managed Agent 上、用 CopilotKit 渲染的個人理財助理聊天 app。這個專案示範怎麼把 managed-agent session 橋接到 AG-UI protocol，用 event delta 逐 token 串流回覆，並把 agent 的 tool call 渲染成聊天裡可互動的 generative UI 元件。

[Go to Managed Agents with CopilotKit Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/copilot-kit-ag-ui)

### Managed Agents: Daily Brief

排程執行的 agent，每個工作日讀你的 Slack 頻道和 GitHub pull request，然後在 Slack 發一則簡短的 brief，建在 Claude Managed Agents 上。這個專案示範整個 deployment 完全用檔案定義、再用 `ant apply` 套用（agent、environment、兩個 memory store、vault、cron deployment），一個唯讀的偏好 store 搭配一個可讀寫的狀態 store，以及為無人值守設計、失敗時也能處理得好的執行步驟：每個來源的書籤、防止重複的紀錄表，還有讀不到的來源會回報「讀不到」，而不是當成平靜的一天。

[Go to Managed Agents Daily Brief Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/daily-brief)

### Managed Agents: Knowledge Wiki

用 Claude Managed Agents 做的 deal-room 知識 wiki。這個專案示範怎麼用一次動態 workflow 執行（擷取、解析、整併），把文件集一次蒸餾成有版本的 memory-store 知識 wiki，之後分析師反覆提問都從 wiki 回答，每個事實都有出處，每題成本也比直接搜原始文件低。範例用的是從公開 SEC EDGAR 文件抓下來的真實併購資料室。

[Go to Managed Agents Knowledge Wiki Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/knowledge-wiki)

### Managed Agents: Linear

在 Linear 裡可以 @mention 或指派的 agent，背後是 Claude Managed Agent。這個專案示範建在 Linear Agent Platform 上的無狀態 webhook bridge：`AgentSessionEvent` 會建立一個 Managed Agents session，把 Linear 的 session 和 organization ID 存在 session metadata 裡，`session.status_idled` webhook 再讀回 metadata，把回覆貼成留言。透過 Linear OAuth 以 `actor=app` 安裝。

[Go to Managed Agents Linear Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/linear)

### Managed Agents: MCP Server (TypeScript)

把 Claude Managed Agents Sessions API 包成九個 tool 的 MCP server。這個專案示範怎麼讓 Claude Desktop、Claude Code 或 claude.ai 操作你 workspace 裡現有的 agent：列出它們、開始 session、送訊息、等待回覆，可走 stdio 或 Streamable HTTP。其中 `wait_for_idle` 這個 tool 把 session 的 event stream 變成單一的 request/response 呼叫，agent allowlist 則限制 bearer-token 持有者能碰到哪些 agent。

[Go to Managed Agents MCP Server (TypeScript) Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/mcp-server-typescript)

### Managed Agents: Road Trip Planner

直接建在 Claude Managed Agents session 上的國家公園公路旅行規劃器，用 Next.js，沒有聊天框架也沒有資料庫。這個專案在同一個畫面示範四個 API 功能：session event stream 上用 `event_deltas` 逐 token 串流、把 vault 憑證注入到特定的 request 位置（`injection_location`）、用 `agent_with_overrides` 對單一 session 覆寫 model，以及 `multiagent` coordinator 在 session thread 裡把草稿交給 reviewer agent。

[Go to Managed Agents Road Trip Planner Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/roadtrip-planner)

### Managed Agents: Sentry

建在 Claude Managed Agents 上、排程執行的 Sentry triage agent。這個專案示範一種 deployment：依 cron 排程開 session、不需要 host process，用 Sentry 的 Agent Plugin 做引導式設定，並把可更新的 MCP OAuth 憑證存在 vault，用於 issue triage 和 Seer 的 root-cause 分析。

[Go to Managed Agents Sentry Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/sentry)

### Managed Agents: Sentry Autofix

用 Claude Managed Agents 和 Sentry MCP server，把 production 錯誤變成 pull request 修好。這個專案示範每個 Sentry issue 一個由 webhook 觸發的 session：agent 讀 stack trace 和 Seer 的 root cause 分析，在掛載的 GitHub repo 裡用一個失敗的 test 重現 bug，然後 push 一個 branch，再由 host 透過自訂 tool 開 pull request，讓每個修正都有人審。設定在 Claude Code 裡用 Sentry 的 Agent Plugin 完成。憑證放在 sandbox 外的 vault，sandbox 沒有通往公開網路的路，每個 session 都有硬性的花費上限。

[Go to Managed Agents Sentry Autofix Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/sentry-autofix)

### Managed Agents: Slack

由 Claude Managed Agent 驅動的 Slack bot。這個專案示範無狀態的 webhook bridge：`@mention` 會建立一個 Managed Agents session，把頻道和 thread 存在 session metadata，`session.status_idled` webhook 再讀回 metadata，把回覆貼進對應的 thread。沒有資料庫，也沒有長連線。

[Go to Managed Agents Slack Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/slack)

## 一般用法

每個 quickstart 專案都有自己的 README 和設定說明。大致上照這些步驟：

1. Clone 這個 repository
2. 進到你要的 quickstart 目錄
3. 安裝需要的依賴
4. 把你的 Claude API key 設成環境變數
5. 執行 quickstart 應用

## 延伸閱讀

想更深入了解怎麼用 Claude 和 Claude API，可以看這些資源：

- [Claude API Documentation](https://docs.claude.com)
- [Claude Cookbooks](https://github.com/anthropics/claude-cookbooks)：常見任務的程式碼片段和指南
- [Claude API Fundamentals Course](https://github.com/anthropics/courses/tree/master/anthropic_api_fundamentals)

## 貢獻

歡迎對 Claude Quickstarts repository 貢獻！如果你有新 quickstart 專案的點子或改進建議，請開 issue 或送 pull request。

## 社群與支援

- 加入 [Anthropic Discord community](https://www.anthropic.com/discord) 討論和取得支援
- 到 [Anthropic support documentation](https://support.anthropic.com) 找更多協助

## 授權

這個專案採用 MIT License，詳見 [LICENSE](https://github.com/anthropics/claude-quickstarts/blob/main/LICENSE) 檔案。

## 重點整理

- Quickstarts 是官方的範例專案集，每個都是可以直接改造的起點
- 範例分幾類：客服與資料分析、computer / browser use、Agent SDK、Managed Agents
- Managed Agents 系列大多靠 webhook 加 session metadata 做成無狀態的橋接，不需要資料庫
- 每個專案都有自己的 README 和 setup，通用流程是 clone、安裝、設 API key、執行

## 練習

1. 從清單挑一個你最有興趣的 quickstart，clone 下來並照它的 README 跑起來。
2. 比較 Computer Use Demo 和 Computer Use Best Practices 的 README，列出兩者在執行環境上的差異。
3. 挑一個 Managed Agents 範例，找出它的 webhook handler，看 session metadata 存了哪些欄位。
