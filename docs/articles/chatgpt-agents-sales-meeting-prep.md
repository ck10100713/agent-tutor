---
translated: true
source: articles/chatgpt-agents-sales-meeting-prep.md
---
# 在 ChatGPT 建立 workspace agent，完成可重複的端到端工作

> 原文：[articles/chatgpt-agents-sales-meeting-prep.md](https://github.com/openai/openai-cookbook/blob/main/articles/chatgpt-agents-sales-meeting-prep.md)

建立、測試、排程並分享一個 ChatGPT workspace agent，用行事曆、SharePoint 和網路搜尋的資料幫業務準備會議簡報。

## 這篇在做什麼

用 ChatGPT 的對話式 builder 建一個 workspace agent，它會讀你的行事曆、搜尋團隊在 SharePoint 的客戶文件、查公司新聞，幫業務準備隔天的客戶會議 brief。做完後測試、排成每個工作日自動跑，再分享給同事。

## 學完你會

- 用對話式 builder 建出 workspace agent，並設定 Google Calendar、SharePoint、Gmail 的帳號類型與權限
- 加上 skill 和 Memory，讓 agent 每次都用一致的格式產出 brief
- 在 Preview 測試、設定每個工作日的排程，並用 Can chat / Can edit 分享給團隊

## 開跑前

- ChatGPT Business、Enterprise 或 Edu workspace，且能使用 workspace agents
- Google Calendar、Microsoft SharePoint、Gmail 帳號，以及對應的權限
- 跟 workspace admin 確認 agent 可用、可分享，且需要的 app actions 已開放


這篇示範怎麼建一個 ChatGPT workspace agent，用你的行事曆和團隊的客戶文件來準備業務會議 brief。

我們會用對話式 builder 建 workspace agent，讓它存取團隊的行事曆和知識庫，再加一個撰寫 brief 的 skill 來規範輸出。接著測試 agent，排成定期執行，最後分享給同事。

## 簡介

ChatGPT workspace agent 是共享的 agent，可以在 ChatGPT 裡執行可重複的工作流程，也能獨立完成端到端的任務。它們能用連接的 app、遵循 skill、照排程執行，還能分享給 workspace 裡的同事。

這篇會建一個支援業務團隊的 workspace agent。業務常常得手動整理客戶筆記、最近的客戶回饋、產品使用數據和公司新聞，才能準備即將到來的客戶會議。

我們要建的 agent 會檢查下一個工作日的客戶會議，從 SharePoint 收集近期的客戶資料，並搜尋網路上的公司新聞。先在 ChatGPT 測試，再設定每個工作日的排程來準備 brief。在有對應的 app actions 和核准的前提下，它可以把 brief 存到 SharePoint，並寄出摘要 email。

## 前置條件與設定

這篇需要 ChatGPT Business、Enterprise 或 Edu workspace，且能使用 workspace agents。我們的 agent 會從 Google Calendar 讀即將到來的會議，把會議 brief 存到 Microsoft SharePoint，再透過 Gmail 寄摘要。

開始建之前，先跟 workspace admin 確認這三個設定。

1. **你能使用 workspace agents。**確認你能開啟 **Agents**，並在 workspace 裡建立 agent。
2. **你能把 agent 連同它的 connection 一起分享。**這個範例用 agent 擁有的 SharePoint connection。確認 workspace 允許你把 agent 連同那個 connection 分享，如果想列在 team directory，也要能發佈到那裡。
3. **需要的 app 和 action 都可用。**確認 workspace 允許讀取行事曆、搜尋 SharePoint 與建立檔案、用 Gmail 寄信。用對應的 Google 和 Microsoft 權限連接帳號。如果 workspace 限制寫入，agent 可以直接在 ChatGPT 裡回傳 brief。

如果想在 Slack 跑這個 agent 的版本，照 [Workspace Agents in Slack 設定說明](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)做。Slack 部署需要每個 app connection 都用共用驗證。這個範例在 ChatGPT 跑，所以每位同事可以用自己的行事曆和 email 帳號。

## 建立你的 agent

在 ChatGPT 開啟 **Agents**，選 **Create** → **Create agent**。對話式 builder 可以草擬 agent 的 profile、選 app、產生 skill、寫 instructions。我們會先檢查它的選擇，再到 **Preview** 測試 agent。

想從現有範例開始的話，改從 **Create** 選單選 **Browse templates**。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img0.png" alt="Build a new agent" width="80%" />
</p>

### 1. 描述你的工作流程

在 agent builder 輸入下面這段：

```text
Create an agent to help with sales meeting prep. Check my Google Calendar for customer meetings on the next weekday. On Friday, prepare briefs for Monday. Exclude internal-only meetings and skip events with no external attendees.

For each customer meeting, pull recent notes and feedback from SharePoint, then search the web for any relevant company news from the last 30 days. Then write a 2-3 page meeting brief. Save it as a file in the team's SharePoint folder.

Then, send me an email with a daily summary of my upcoming meetings, with a link to the full brief.
```

看過計畫後，選 **Build this agent**。確認草稿包含 Google Calendar、SharePoint 和 Gmail。

如果還沒設定好需要的 app，agent builder 會帶你一步步完成。如果 Gmail 不可用，可以請 agent 在 ChatGPT 裡回傳 SharePoint brief 的連結。

### 2. 檢查並設定你的 app

接下來檢查各 app 的設定。因為 agent 能存取外部工具，一定要清楚它在這些工具上有哪些操作權限，以及把 agent 分享給其他同事用時，這些權限會怎麼變。

哪些 app action 可用由 workspace admin 控制。這個範例中，SharePoint app 需要權限去搜尋客戶文件和建立會議 brief。如果 workspace 把 SharePoint 限制成唯讀，就讓 agent 在 ChatGPT 裡回傳 brief。

可以點進每個 app 查看並修改它的權限。

**Google Calendar** 用每個人自己的 connection。**Use for everyone** 保持關閉，如果 builder 顯示帳號選項，就選 **End-user account**。每位在 ChatGPT 執行這個 agent 的人，要連接自己的 Google Calendar 帳號，agent 才能讀他們的會議。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img2.png" alt="End-user auth for Google Calendar" width="60%" />
</p>

Google Calendar 只需要查看即將到來的會議和與會者，所以只開啟讀取 action。也可以更細緻地控管權限，逐一選擇要啟用或停用哪些 action。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img3.png" alt="Read access for Google Calendar" width="60%" />
</p>

**Gmail** 同樣用每個人自己的 connection。在 ChatGPT 執行時，agent 用的是執行者的 Gmail connection。要寄出摘要，它需要有寄信給該使用者的權限。

**Microsoft SharePoint** 要開啟 **Use for everyone**，如果 builder 顯示帳號選項，就選 **Agent-owned account**。連接一個業務團隊的 service account，這個帳號要能存取 agent 需要的客戶文件，以及存放 brief 的資料夾。每次執行都用同一個帳號。

啟用找文件、讀來源文件、在目標資料夾建立 brief 所需的 SharePoint action。確認預期的收件人能打開那個資料夾裡的檔案。分享、刪除和其他不相關的寫入 action 都保持停用。

在每個 app 的設定裡，要把核准（approval）和「啟用哪些 action」分開檢查。Workspace agent 預設在寫入 action 前會先詢問。測試時，先看 agent 嘗試建立檔案和寄信時會怎樣，再決定能不能依賴排程自動寄送。

除了這些 app，agent 也用 **Web search** 找最近 30 天的公開公司新聞。

### 3. 啟用 skill 和 memory，讓輸出一致又客製

用 workspace agent 的好處之一，是很容易確保輸出**品質高又一致**。skill 很適合讓 agent 每次產出會議準備文件時都走同一套流程。

Skill 把 instructions、資源和腳本打包起來，幫 agent 穩定地完成任務。要幫 agent 加 skill，在 agent 畫面選 "Add skill"。可以上傳已經做好的 skill（skill 建立在[開源的 agent skills 標準](https://agentskills.io/home)上，所以能跨 AI 產品使用），也可以直接用 ChatGPT workspace agents 內建的 skill builder。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img5.png" alt="Creating a skill for our agent" width="336" />
</p>

如果團隊已經有會議 brief 的範本，上傳到 builder，請助理在建立 skill 時沿用它的段落。要調整 skill，可以在 agent builder 裡編輯，或上傳它能用的檔案。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img6.png" alt="Editing a skill for our agent" width="60%" />
</p>

我們也會幫 agent 開啟 **Memory**。Memory 讓 agent 能跨 session 保留 context，方式是給它一個持久的資料夾，可以存筆記、草稿和輸出。這裡我們讓 agent 記住它先前的執行紀錄，這樣它就知道每個使用者的 context。

在 ChatGPT 裡，agent 對每個使用者各有一份獨立的 memory。同事可以在 agent 頁面查看自己的 memory。例如，可以叫 agent 記住你想跳過哪些定期會議。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img7.png" alt="Giving our agent access to memory" width="60%" />
</p>

## 測試你的 agent

在 builder 選 **Preview**，分享之前先用你自己的帳號測試 agent。準備好後，選 **Create** 發佈 agent。之後如果改了草稿，選 **Update** 發佈新版本。

注意 agent builder 已自動建立一些範例 starter prompt，會顯示在 ChatGPT 裡 agent 旁邊。要查看和編輯這些 prompt，到 agent 畫面的 "Channels" 底下選 ChatGPT。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img9.png" alt="Updating starter prompts" width="336" />
</p>

我們請 agent 準備下一個工作日會議的 brief。執行過程中，可以檢查它做了哪些 app action，例如讀取行事曆事件、把 brief 存到 SharePoint。

確認預期的檔案存在、email 已送達、連結對收件人也能打開。下面的截圖是另一次針對當天會議的執行所產生的 email 和 brief。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img11.png" alt="Output email" width="80%" />
</p>

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img12.png" alt="Output meeting brief" width="80%" />
</p>

可以用不同的輸入資料多跑幾次測試。例如請 agent 為你上週已經開過的會議準備 brief，跟人工寫的準備文件比較。你也可以把那份準備文件加進 skill 的檔案當範例。要精進輸出，可以更新 agent 的 instructions、調整 app 與權限設定，或修改它的 skill。

## 部署你的 agent

在 ChatGPT 開啟已發佈的 agent，選 **Automations**。選 ChatGPT channel，排程設成每個工作日美東時間下午 4 點。輸入針對下一個工作日會議的 instructions，選 **Add automation**。排程會以建立排程的人的身分執行已發佈的版本。依賴 email 之前，先檢查第一次執行有沒有待核准或失敗的 action。

下面的圖是較早版本的排程編輯器裡同樣的工作日設定。如果想要每週一份 brief，就選週日晚上，並請 agent 涵蓋接下來這一週。

<p align="center">
  <img src="https://cdn.openai.com/cookbook/chatgpt-agents-sales-meeting-prep/img10.png" alt="Weekdays at 4 p.m. Eastern in an earlier version of the schedule editor" width="336" />
</p>

要分享 agent，在 builder 開啟它並選 **Share**。能不能分享 agent 由 workspace admin 控制。

用 **Can chat** 邀請業務同事，他們就能執行 agent。想讓同事跟你一起維護，給他 **Can edit**。Editor 可以更新共用的草稿並發佈新版本。符合條件的受管 workspace 也能把權限給 workspace group。有建立 agent 權限的同事可以複製 agent，做出獨立的版本。見 [workspace agent 分享指南](https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business)。
想收到定期的個人 brief，每位同事要連接自己的 Google Calendar 和 Gmail 帳號，並建立自己的 ChatGPT 排程。**任何能執行這個 agent 的人，也能透過業務團隊的 service account 使用它已啟用的 SharePoint action。**分享之前，先檢查 service account 能存取哪些內容、agent 能做哪些 SharePoint action。

如果 workspace 允許發佈到 directory，你也可以把 agent 列給有 agent 存取權的 workspace 成員。他們可以在 **Agents** 的 **Team directory** 找到它。

## 重點整理

- Workspace agent 是可共享、可排程的 agent，用連接的 app 加 skill 完成端到端的重複性工作。
- 帳號類型要照用途選：行事曆和 Gmail 用每個人自己的帳號，SharePoint 用 agent 擁有的 service account。
- 權限最小化：只開需要的 action，寫入 action 預設要核准，先測試再靠排程自動執行。
- Skill 讓輸出格式一致，Memory 讓 agent 記住每個使用者各自的 context。
- 分享給別人等於讓他們也能用 service account 的 SharePoint action，分享前要確認它能碰到什麼。

## 練習

1. 在 builder 的描述裡多加一個需求，例如 brief 要附上客戶最近一次的 email 往來，重新 build 看草稿有什麼變化。
2. 把你團隊現有的會議 brief 範本上傳，請助理用它的段落建立 skill，再用 Preview 跑一次比較輸出。
3. 把排程改成週日晚上、涵蓋整週的 brief，再請同事用 Can chat 權限各自建立排程，檢查他們是否都用到自己的行事曆。
