---
translated: true
source: examples/chatgpt/daily_usage_limits/README.md
---
# 按小時、每天或每週釋出 ChatGPT 使用額度

> 原文：[examples/chatgpt/daily_usage_limits/README.md](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/README.md)

把每月的 ChatGPT 預算（以 credits 或美元計）拆成按小時、每天或每週的額度逐步釋出。可以先在瀏覽器試算方案，再用 Codex 輔助做小規模試行，最後部署到受管理的基礎設施上。

## 這篇在做什麼
ChatGPT Enterprise 和 Edu 的使用上限是以月為單位，重度使用者第一週就可能用光。這個範例用 ChatGPT Admin API 寫了一支 Node.js 程式，把月預算切成小份定期釋出，讓額度分散在整個月。

## 學完你會
- 在本機用假資料跑一次 credits 或美元的釋出模擬，看每個人的月上限怎麼逐週增加。
- 看懂 `startCap`、`increment`、`ceiling` 這些設定怎麼算出 500、1,000、1,500、2,000 的階梯，以及對應的 Admin API 請求長什麼樣。
- 知道正式環境要怎麼選方案、先小範圍試行，再放到組織管理的基礎設施上，並能停止與還原。

## 開跑前
- 本機範例需要 Node.js 24 或更新版本，不需要 Admin API key。
- 要真的套用到 workspace，需要 ChatGPT Enterprise 或 Edu 的 Admin API 權限。
- 部署到 AWS 需要自己的 AWS 帳號。


這個可以直接執行的範例，用 [ChatGPT Admin API](https://chatgpt.com/public/admin/api-reference) 自動更新 ChatGPT Enterprise 和 Edu 的使用上限。裡面有一支 Node.js 程式，可以先在本機試跑，再設定成適用你的 workspace。

**ChatGPT Enterprise 和 Edu 的使用上限是按月計算**。如果有人第一週就把額度用完，整個月大部分的時間都會卡在上限。

你可以用 **credits 或美元（USD）**，按小時、每天、每週或自訂排程釋出一部分預算，讓後面的工作還有額度可用。金額和排程可以針對個人、部門或整個 workspace 設定。

對最活躍的使用者，可以根據最近的用量增加可用額度，上限是你設定的每月最大值。同時定期告知大家使用狀況，讓他們知道還剩多少、什麼時候會有更多額度，以及選擇的模型怎麼影響消耗。

## 讓額度在整個月都用得到

圖中的例子是**每人每月 2,000 credits**。這份指南裡所有金額都只是範例，請依你要服務的人和團隊決定預算。

![A person uses a 2,000-credit monthly budget in the first week and has no credits left for the remaining weeks.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/daily_usage_limits/assets/monthly-budget-problem.svg)

每週釋出 500 credits，就能把一部分額度留給後面幾週。每次釋出都會提高這個人的月上限，到第四次釋出時達到完整的 2,000 credits。

<details>
<summary>每月重置日</summary>

使用上限預設在每個月 1 號（UTC）重置。workspace 也可以讓每月使用期間對齊帳單週期。[查看你的 workspace 使用期間](https://help.openai.com/en/articles/20001001-manage-usage-limits-and-overages-in-chatgpt-enterprise-and-edu)。

</details>

## 在瀏覽器試算釋出方案

打開[互動範例](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/assets/release-explorer.html)。選 **Credits**、**US dollars (USD)** 或 **Both**，比較兩份獨立的範例方案。可以改預算和釋出排程，看用量怎麼影響可用額度。

| 釋出日期 | 新增可用 credits | 釋出後的月上限 |
| --- | ---: | ---: |
| 第 1 天 | 500 | 500 |
| 第 8 天 | 500 | 1,000 |
| 第 15 天 | 500 | 1,500 |
| 第 22 天 | 500 | 2,000 |

![Four releases of 500 credits increase the monthly limit to 2,000.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/daily_usage_limits/assets/release-timeline.svg)

已釋出但沒用完的 credits 在當月內仍然可用。每月總預算和每一份什麼時候釋出，都由你決定。

## 選擇美元或 credits

使用 workspace 使用設定裡、依你客戶合約顯示的計費單位。credit-based 的 workspace 選 **Credits**，以美元計價和限額的 workspace 選 **US dollars (USD)**。controller 在套用方案前，會先檢查 API 回報的單位。

| 範例方案 | 每人每月預算 | 每週釋出 | 設定 |
| --- | ---: | ---: | --- |
| Credits | 2,000 credits | 500 credits | `"unit": "credit"` |
| US dollars | $200.00 | $50.00 | `"unit": "usd"` |

這是兩份各自獨立的示範預算。請用你組織的計費單位決定金額。credit 上限用整數 credits，美元上限用到分。三種釋出方式都支援兩種單位。[設定單位與金額](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#choose-the-billing-unit)。

## 開始動手

在 **Windows、macOS 或 Linux** 執行本機範例需要 **Node.js 24 或更新版本**。範例用三個虛構的人，所有變更都只存在記憶體裡，不需要 Admin API key。

1. [下載 starter ZIP](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/daily_usage_limits/assets/chatgpt-usage-budget-starter.zip) 並解壓縮。
2. 打開 `chatgpt-usage-budget-starter` 資料夾，裡面有 `README.md`、`docs`、`src` 和 `assets`。
3. 在這個資料夾打開 terminal。Windows 在檔案總管資料夾空白處按右鍵，選 **Open in Terminal**。macOS 或 Linux 打開 Terminal，輸入 `cd `，把解壓縮的資料夾拖進視窗，按 Enter。

執行 credits 範例：

```bash
node src/demo.mjs --unit credit
```

或執行美元範例：

```bash
node src/demo.mjs --unit usd
```

程式會預覽第一次釋出、在本機模擬器套用，然後前進到下一次每週釋出。每個虛構人物的上限會依所選方案變化：

| 範例 | 起始月上限 | 第一次釋出 | 下一次每週釋出 |
| --- | ---: | ---: | ---: |
| Credits | 2,000 credits | 500 credits | 1,000 credits |
| US dollars | $200.00 | $50.00 | $100.00 |

示範也會模擬更新被中斷和 admin 手動編輯衝突的情況，然後還原起始設定。成功執行會以 `Demo complete. All simulated state stayed in memory.` 結尾。

依你手上有的工具選擇設定方式：

| 你的情況 | 指南 |
| --- | --- |
| 你用 Codex，想要有人幫忙設定。 | [用 Codex 打開資料夾](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/get-started.md#let-codex-help)，請它執行範例。 |
| 你的團隊提供受管理的電腦、虛擬機或雲端環境。 | [在該環境執行](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/get-started.md#use-a-managed-environment)。你的電腦不能裝所需軟體時，也可以走這條路。 |

示範跑完後，再決定試行要涵蓋的人、金額和排程。

## 每週方案怎麼用到 API

下面這段設定節錄表達的是每週 500 credits 的方案。請把這些欄位放進[設定與登錄指南](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment)產生的完整設定裡，並把範例的 `anchor` 換成你的方案在已確認的月使用期間內的起點。

```json
{
  "unit": "credit",
  "policy": {
    "pattern": "fixed_release",
    "anchor": "2030-01-01T00:00:00Z",
    "intervalHours": 168,
    "startCap": "500",
    "increment": "500",
    "ceiling": "2000"
  }
}
```

`startCap` 設定第一個月上限。controller 每隔 168 小時，把 `increment` 加到排程目標上，最多加到 `ceiling`。結果月上限依序是 **500、1,000、1,500、2,000 credits**。同一週重複執行，目標不變；漏跑的話，會補到當週的目標。

第二次釋出時，[API adapter](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/src/admin-api.mjs) 會在登錄和擬議變更都審核過後，送出下面這種形狀的請求。下面的 `WORKSPACE_ID` 和 `USER_ID` 代表所選的 workspace 和已登錄的人：

```http
PATCH /v1/manage/workspaces/WORKSPACE_ID/usage_limits/users/USER_ID
Host: api.chatgpt.com
Content-Type: application/json

{
  "override_monthly_usage_limit": {
    "type": "limited",
    "limit_amount": { "unit": "credit", "amount": "1000" },
    "temporary": true
  }
}
```

這個請求把該人的月上限總額設成 1,000 credits。workspace 餘額和月使用期間都不變。`temporary: true` 讓這個覆寫在該期間結束時失效。套用到你的 workspace 之前，請先照著[審核登錄與預覽步驟](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment)做；[API contract](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/api-contract.md) 涵蓋驗證、單位和還原。

## 選擇釋出預算的方式

| 方式 | 用途 |
| --- | --- |
| 排程釋出 | 把月配額分散成按小時、每天、每週或自訂的釋出。 |
| 依用量增加 | 隨著使用量成長，給活躍使用者更多額度，上限是每月最大值。 |

不同族群可以設不同的預算和排程。例如專案團隊用每週釋出，一小群重度使用者用依用量增加。每個人只能屬於一份啟用中的設定。

設定細節請看[政策設定與範例](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#choose-a-policy)。每月配額、目前用量和下次釋出日期，可以透過你們現有的溝通管道告知大家，讓大家選擇符合工作需求和可用預算的模型。

## 先用小群組測試

用本機執行或 Codex 自動化，先對一小群人試行。檢視擬議的上限，觀察釋出排程跟他們的工作合不合，再調整方案。

要長期管理 workspace 預算，請把程式跑在**組織管理的基礎設施**上，例如受管理的虛擬機或雲端服務。指派一個團隊監控，並讓它不依賴任何個人的電腦持續運作。

![Test locally or with Codex, then run ongoing releases on organization-managed infrastructure.](https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/chatgpt/daily_usage_limits/assets/control-flow.svg)

| 下一步 | 指南 |
| --- | --- |
| 測試排程式 Codex 試行 | [設定 Codex 試行](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/codex.md) |
| 在受管理的 macOS 或 Linux 電腦或伺服器上執行 | [設定受管理主機](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/local.md) |
| 用你的 AWS 帳號部署 | [部署到 AWS](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/aws.md) |

AWS 指南包含部署範本、大量登錄用的佇列處理，以及進度追蹤。先從小群組開始，確認完成狀況和 API 吞吐量後再擴大登錄人數。你的技術團隊也可以把程式改寫成適用組織其他基礎設施。

給 Windows admin：AWS 指南提供透過 AWS CloudShell 的瀏覽器設定路徑。本機的即時排程則使用內附的 macOS 或 Linux service 設定。

## 準備審核過的登錄名單

先選一個 workspace，再用 user ID、email、workspace group ID 或所有現有成員來挑人。檢查解析出來的名單、目前設定、月使用期間和擬議變更。[設定與登錄指南](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#prepare-a-reviewed-enrollment)會帶你走每個步驟。預覽會在套用前顯示擬議的上限。

## 停止、還原與續期

程式會保存原始設定並記錄自己做的變更。結束試行或更改政策時，請照著[停止與還原流程](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/operations.md#stop-restore-and-renew)做。AWS 上要進入下一個月使用期間時，請[確認日期並檢查開頭的上限](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/aws.md#7-renew-the-next-period)。續期 helper 會在同一個部署上沿用你的政策和人員，包含既有的紀錄和憑證。
實作細節請看[驗證指南](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/verification.md)和 [API contract](https://github.com/openai/openai-cookbook/blob/main/examples/chatgpt/daily_usage_limits/docs/api-contract.md)。

## 重點整理
- ChatGPT Enterprise 和 Edu 的上限是按月，所以要把月預算切成小份定期釋出，避免有人第一週就用光。
- 排程由 `startCap`（起始上限）、`increment`（每次增加）、`ceiling`（月最大值）和釋出間隔決定，重複執行結果不變，漏跑會補到當週目標。
- 套用上限是呼叫 Admin API 設定個人的月總額，`temporary: true` 讓覆寫在月底失效。
- 要先小群組試行，長期運作放在組織管理的基礎設施上，並保留停止與還原的流程。
- 單位要跟 workspace 的計費單位一致，controller 套用前會檢查 API 回報的單位。

## 練習
1. 把 credits 範例的概念改成每月 3,000 credits、每週釋出 750，算出四次釋出後的月上限序列，確認最後等於 ceiling。
2. 把設定裡的釋出間隔從 168 小時改成每天（24 小時），推算一個月內會有幾次釋出，以及每次的 `increment` 要設多少才能剛好在月底達到 ceiling。
3. 同時跑 credits 和美元兩個本機範例，比較兩者輸出的第一次與下一次釋出數字，說明 `"unit"` 欄位影響了哪些地方。
