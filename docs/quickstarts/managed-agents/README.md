---
translated: true
source: managed-agents/README.md
---
# Managed Agents quickstarts

> 原文：[managed-agents/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/README.md)

## 這篇在做什麼

這是一份用 [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) 做的 quickstart 專案總覽。Managed Agents 是由 Anthropic 幫你跑的 agent，有 server-side session、sandbox 化的 tool，以及給你的 app 消費的 event stream。每個 quickstart 都是完整可執行的 app，把 Managed Agents 接在真實的產品介面上。

## 學完你會

- 知道各個 quickstart 接的是哪種介面（瀏覽器聊天、Slack、Linear、Sentry、MCP 等）
- 看出 session、vault、webhook、memory store 這些元件在不同場景怎麼組合
- 依自己的需求選一個起點來讀

## 開跑前

各個 quickstart 需要的憑證不同（例如 Slack、Linear、Sentry、GitHub 的 token），請看各自的目錄。

## Quickstarts

- **[assistant-ui/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/assistant-ui)** 把一位試算表分析師放進完全用 assistant-ui primitive 做的瀏覽器聊天。session 就是對話串清單，也是唯一的狀態：側邊欄就是 `sessions.list`，舊對話就是把 event log 經過一個純 reducer 重播，每個內建 tool 都有自己的卡片（`bash` 是 terminal、`web_search` 是來源卡片、`edit` 是 diff、client 端執行的 `show_chart` 是圖表）。Bash 是 `always_ask`，所以每個指令都會讓 session 暫停，並渲染一個內嵌的 Allow/Deny 關卡，重新整理後仍然保留。輸入框的附件會上傳到 Files API，並在訊息送出前掛進 sandbox。不需要第三方憑證。
- **[chat-sdk/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/chat-sdk)** 用 Vercel 的 Chat SDK 把一位研究分析師放進瀏覽器聊天。每個對話是一個持久的 session（對話 ID 就是 session ID）；分析師用 web search 做研究，並在同一個持續的 response 上逐 token 串流最終簡報（session `event_deltas` 預覽），同時有即時 feed 顯示 tool 呼叫。不需要第三方憑證，換個 adapter 同一個 handler 就能搬到 Slack、Teams、Discord、Telegram 或 WhatsApp。

- **[copilot-kit-ag-ui/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/copilot-kit-ag-ui)** 把個人理財助理放進透過 AG-UI protocol 的 CopilotKit 聊天。上游的 [`@ag-ui/claude-managed-agents`](https://www.npmjs.com/package/@ag-ui/claude-managed-agents) adapter 把每個聊天 thread 對應到一個 managed session，並逐 token 串流回覆。agent 想呈現數字時會呼叫 custom tool，在對話中以可互動的圖表渲染（還款時間軸、成長預測、預算），滑桿在 client 端重新計算。

- **[daily-brief/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/daily-brief)** 每個平日早上根據你的 Slack 頻道和 GitHub pull request 在 Slack 貼一則簡短的 brief，不需要 host process。六個資源（agent、environment、兩個 memory store、vault、cron deployment）都是用 `ant apply` 套用的檔案，所以設定就是一個 script 加兩個 vault 憑證。執行步驟寫成無人看管時也能好好失敗：每個來源用書籤而不是「過去 24 小時」、用帳本避免重複、讀不到的來源回報為無法讀取而不是平靜的一天、一個 agent 每次執行都會重讀的唯讀偏好 store，以及 sandbox 看不到的、放在 vault 憑證裡的 Slack token。

- **[knowledge-wiki/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/knowledge-wiki)** 用一次 dynamic workflow（extractor、resolver、analyzer、organizer）把文件語料一次蒸餾成 knowledge wiki（一個有版本的 memory store），之後分析師反覆提問時從 wiki 回答而不是重讀文件，每個事實都有 `[source | as-of]` 出處，每題成本也更低。實際範例是真實的併購 data room：2024 年 Squarespace / Permira 私有化交易，資料取自公開的 SEC EDGAR 申報文件。

- **[linear/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/linear)** 在 Linear issue 中回應 `@mentions` 和指派，並以留言回覆，靠的是 Linear Agent Platform 上的無狀態 Bun webhook bridge。`AgentSessionEvent` 建立 session，並把 Linear 的 session 和 organization ID 存進 session `metadata`；handler 在 Linear 的 10 秒視窗內貼出一則「thought」，`session.status_idled` webhook 再把 metadata 讀回來貼出回覆。它用 `actor=app` 透過 Linear OAuth 安裝，第一個安裝的 workspace 擁有這個 bridge，在 Linear 按 Stop 會中斷執行中的 session。

- **[mcp-server-typescript/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/mcp-server-typescript)** 把 Sessions API 包成九個 MCP tool，讓 Claude Desktop、Claude Code 或 claude.ai 可以列出你 workspace 裡的 agent、啟動 session 並轉送訊息。八個 tool 一對一對應 endpoint，`wait_for_idle` 把 event stream 變成一次 request/response 呼叫。它自己不建立任何 agent。HTTP entrypoint 預設綁 loopback，`ALLOWED_AGENT_IDS` 限制 bearer token 持有者能存取哪些 agent。

- **[roadtrip-planner/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/roadtrip-planner)** 在直接建在 session 上的 Next.js 聊天中規劃國家公園公路旅行，沒有聊天框架也沒有資料庫。它在一個畫面上展示四個 API 功能：透過一層薄的 SSE proxy 做 `event_deltas` token 串流、用 `injection_location` 把 vault 憑證注入 header 或 JSON body、用 `agent_with_overrides` 做每個 session 的模型覆寫，以及一個 `multiagent` coordinator 在同一條 event stream 上把草稿交給 reviewer agent。

- **[self-hosted-sandboxes/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/self-hosted-sandboxes)** 在你控制的硬體上執行 session。self-hosted environment 就是一個 work queue：host process 用 environment key 輪詢它，並為每個被認領的 session 啟動一個短命的 Docker 容器。`docker/` 是全 CLI 的基準版；`docker-memory/` 在容器裡跑 Python SDK worker，讓每個 session 把 memory store 掛在 `/mnt/memory` 並同步回去，並用每個 session 的 token 讓 environment key 不進容器。`archil/` 把容器換成 Archil 的持久 sandbox，全都掛載同一個 SEC EDGAR 磁碟，讓平行的分析師 session 直接處理 70 GB 的申報文件。`openshell/` 把容器換成 NVIDIA OpenShell sandbox，每個都由 `policy.yaml` 限制在檔案系統允許清單和 `api.anthropic.com` 上的六條路由。它跟 `docker/` 一樣全是 CLI，並把每個 session 的 token 透過 stdin 餵給 `ant beta:worker run`，讓 environment key 留在 host。
  另外五個變體從 `session.status_run_started` webhook 而不是 poller 啟動 sandbox，分別在 Cloudflare Containers、沒有容器的 Cloudflare Worker、Daytona、Modal、Vercel Sandbox 上。它們共用一個 agent 和 environment，從 `webhook-demo/` 用 `ant apply .` 建立。

- **[sentry/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/sentry)** 依排程跑一個 Sentry triage agent，不需要 host process。deployment 依 cron 表達式啟動 session，agent 透過 Sentry 代管的 MCP server 拉過去 24 小時的 issue，在可用時請 Seer 做根本原因分析，並寫出依使用者影響排序的報告。設定在 Claude Code 裡用 Sentry 的 Agent Plugin 選 org 和 project，瀏覽器 OAuth 授權會以可更新的 `mcp_oauth` 憑證存進 vault，由 Anthropic 注入 MCP 連線並負責更新；sandbox 從不持有 token。

- **[sentry-autofix/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/sentry-autofix)** 把新的 Sentry issue 變成 pull request。簽章過的 Sentry webhook 為每個 issue 啟動一個 session。agent 透過 Sentry MCP server（`mcp_oauth` vault 憑證）讀 stack trace 和 Seer 的根本原因分析，在掛載的 repo 裡用一個會失敗的測試重現 bug，然後 push 一個 branch。host 透過 custom tool 開 pull request，所以 repo、base branch 和 `Fixes SHOP-1A` 連結都不由 agent 決定，pull request 一開完就收回 session 的 push 權限。設定在 Claude Code 裡用 Sentry 的 Agent Plugin 選 org 和 project。

- **[slack/](https://github.com/anthropics/claude-quickstarts/blob/main/managed-agents/slack)** 在 Slack 回應 `@mentions`，以 thread 回覆，靠的是無狀態的 Bun webhook bridge。Slack event 建立 session，並把頻道和 thread 存進 session `metadata`，handler 在 Slack 的 3 秒視窗內回 ack，`session.status_idled` webhook 再把 metadata 讀回來貼出回覆。沒有資料庫，也沒有持續占用的連線。

## 重點整理

- Managed Agents 的共通骨架是：事件進來（webhook、cron、使用者訊息）建立 session，結果透過 event stream 或 `session.status_idled` 之類的 webhook 回送。
- 狀態放在 session（含 `metadata`）和 memory store，bridge 本身可以無狀態、不用資料庫。
- 憑證放 vault，由平台注入，sandbox 不接觸 token；這是這幾個範例反覆出現的安全做法。
- 想把人放進流程，可以用 `always_ask` 或 custom tool 讓 session 暫停等核准。
- sandbox 可以在 Anthropic 端，也可以 self-host 在自己的硬體或第三方 sandbox 上。

## 練習

1. 讀 `slack/` 和 `linear/` 兩個目錄，比較它們各自把什麼存進 session `metadata`，以及為什麼回覆時需要它。
2. 挑一個你有帳號的整合（例如 Slack），照該目錄的 README 跑起來，並觀察 `session.status_idled` webhook 何時觸發。
3. 讀 `mcp-server-typescript/`，試著把 `ALLOWED_AGENT_IDS` 設成只允許一個 agent，確認其他 agent 被擋下。
