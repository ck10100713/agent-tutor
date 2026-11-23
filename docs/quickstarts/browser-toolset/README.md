---
translated: true
source: browser-toolset/README.md
---

# Browser Toolset Quickstart

> 原文：[browser-toolset/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/browser-toolset/README.md)

## 這篇在做什麼

這是 Claude browser toolset（`browser_toolset_20260801`）的最小 CDP 範例，有 Python 和 TypeScript 兩版。你在 `tools` 裡宣告一個 toolset，模型就會把每個瀏覽器動作當成獨立 tool 來呼叫，由 driver 在瀏覽器裡執行。

## 學完你會

- 知道怎麼在 `tools` 宣告 browser toolset，並用 tool runner 跑起來。
- 看懂 example driver 如何用 CDP 實作 `navigate`、`read_page`、`left_click` 等 tool。
- 用 URL policy 限制模型能訪問的網域，並在不接模型的情況下用 `exercise` 測 driver。

## 開跑前

需要 `ANTHROPIC_API_KEY`、支援 browser toolset 的 SDK、Python 3.10+ 或 Node.js 20+，以及一個 Chromium 執行檔。

Claude browser toolset 的最小 CDP 範例，Python 和 TypeScript 都有。你在 `tools` 宣告一個 toolset 項目。模型會把每個瀏覽器動作（`navigate`、`read_page`、`left_click` 等）當作獨立的 tool 呼叫，driver 再把這些呼叫拿到瀏覽器裡執行。

Driver 只有幾百行。它透過 Chrome DevTools Protocol（CDP）操作一個 Chromium 分頁，實作 toolset 裡的五個 tool。它是用來展示介面的，不是 production 程式碼。

| 檔案 | 說明 |
| --- | --- |
| `run.py` / `run.ts` | Quickstart 本體：建立範例 driver、交給 tool runner，並印出模型的訊息。從這裡開始。 |
| `exercise.py` / `exercise.ts` | 不用模型就能驅動同一個 toolset：對本機頁面送出模型會送的呼叫，印出模型會看到的結果。 |
| `cdp_browser.py` / `cdp-browser.ts` | 範例 driver：SDK 抽象 browser toolset 的子類別，透過原始 CDP 操作一個 Chromium 分頁。 |

> [!WARNING]
> 模型造訪的頁面會影響它接下來的行為。請在有 egress 管控的 sandbox 裡，用用完即丟的瀏覽器 profile 來跑，不要用你日常的瀏覽器。
>
> 要拿去接別的東西之前，先讀 SDK tool helper 文件裡的「Running a browser toolset safely」：[Python](https://github.com/anthropics/anthropic-sdk-python/blob/main/browser-toolset.md#running-a-browser-toolset-safely)、[TypeScript](https://github.com/anthropics/anthropic-sdk-typescript/blob/main/browser-toolset.md#running-a-browser-toolset-safely)。

## 安裝

你需要：

- `ANTHROPIC_API_KEY` 裡放 Anthropic API key；
- 有 browser toolset helper 的 Anthropic SDK：Python 要 `anthropic` 2.0 以上（`anthropic.tools.browser`），TypeScript 要 `@anthropic-ai/sdk` 1.0 以上（`@anthropic-ai/sdk/helpers/beta/toolsets`）。`requirements.txt` 和 `package.json` 已經鎖好版本；
- Python 3.10+ 或 Node.js 20+；
- Chromium 執行檔，從 `CHROME_PATH` 或 `PATH` 上的 `google-chrome` / `chromium` 找。Ubuntu 用 snap 裝的 Chromium 無法在 `/tmp` 底下開 profile，請裝 Google Chrome 的 `.deb`，或把 `CHROME_PATH` 指到非 snap 的版本。

```bash
cd browser-toolset/python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

```bash
cd browser-toolset/typescript
npm install
```

## 執行

```bash
python run.py "Open example.com and tell me the heading"          # Python
npm run start -- "Open example.com and tell me the heading"       # TypeScript
```

整條命令列就是任務內容。`run.ts` 不讀任何選項，連 `--help` 也會送給模型。`run.py` 會自己回應 `--help`。

它會在每則模型訊息到達時印出來：先是 tool 呼叫，最後是答案。`run` 只用 SDK 的抽象 toolset，所以換別的 driver 也一樣：建好它、放進 `tools`、對 tool runner 跑迴圈，迴圈結束時關掉它。

`run` 會給 toolset 一個範例 URL policy（`run.py` 的 `example_policy`、`run.ts` 的 `examplePolicy`），只允許 `ALLOWED_DOMAINS` 裡主機的 http(s) 頁面（含子網域）和空白分頁。它示範 policy 該放哪裡，不是 production 用的 policy。你的 policy 需要什麼，看上面連結的 SDK 指南。

`confirm` hook 可以在 tool 執行前問使用者，也放在同一個地方：toolset 的 `confirm` 選項。範例 driver 沒有啟用需要 confirm 的 tool。

| 變數 | 作用 |
| --- | --- |
| `ALLOWED_DOMAINS` | 模型可以造訪的主機，用逗號分隔，含子網域。預設 `example.com,iana.org`。設成空字串代表不允許任何主機。 |
| `HEADLESS` | 設成 `0` 可以看到瀏覽器。Chromium 會開兩個分頁：它自己的空白啟動分頁，和 driver 操作的那一個。 |
| `CHROME_PATH` | 指定 Chromium 執行檔。 |
| `MODEL` | 要跑的模型。 |

## 不接模型直接測 toolset

`exercise` 不需要 API key。它在 localhost 開一個小頁面，用只允許該頁面的 policy 啟動 driver，再透過 tool runner 用的同一個入口送出模型會送的呼叫：

```bash
python exercise.py        # Python
npm run exercise          # TypeScript
```

它會印出模型會看到的每個 `tool_result`。有四個呼叫會成功：`navigate`、`read_page`、對讀到的 `ref_N` 做 `left_click`，以及 `get_page_text`（可看出點擊造成了什麼）。有兩個會以 `is_error` 被拒絕：用 `127.0.0.1` 去 `navigate` 同一個頁面，以及超過 30 秒的 `wait`。只要有任何呼叫的結果不符預期，就會以非零狀態碼結束。

## 範例 driver 實作了什麼、省略了什麼

已實作：`navigate`（到某個 URL；文件解析完就返回）、`read_page`（標題、連結、按鈕和表單控制項，各有 `ref_N`）、`left_click`（用 ref 或座標）、`get_page_text` 和 `wait`，再加上回報它那一個分頁狀態的 `browser_state`。其餘由 SDK 提供：tool schema、包住你 policy 的 URL 檢查、拒絕 driver 沒實作的 tool，以及 tool runner。

省略的部分：

- 其他所有 tool：截圖、捲動、打字、表單輸入、find、分頁、上傳下載、讀 console 和 network、執行 JavaScript；
- click 的修飾鍵，以及多分頁；
- 頁面不再回應的情況，包括跳出對話框（alert、confirm、prompt）：之後每個呼叫（包含 navigate）都會在 60 秒後失敗；
- request 攔截。URL policy 只判斷模型要求的網址，不管瀏覽器自己發的 request。轉址，或允許頁面上的圖片、script，仍可能連到 policy 會拒絕的主機，這要靠 egress 規則擋；
- 在文件解析完成前就用 script 把自己換掉的頁面：`navigate` 會等一個永遠不來的文件，30 秒後放棄；
- 觸發導覽的 click 或頁面 script：下一次讀取可能失敗一次，或讀到舊頁面，模型會再讀一次或等一下；
- Ctrl-C 之後的清理：TypeScript 版會留下暫存的 profile 目錄。

Production 用的 driver 大部分都需要處理上面這些。SDK 指南裡有逐項說明。

## 重點整理
- Browser toolset 只需要在 `tools` 宣告一項，模型的每個瀏覽器動作會變成獨立的 tool 呼叫。
- Driver 負責真正執行動作，SDK 負責 schema、URL 檢查和 tool runner。
- URL policy 只看模型要求的網址，擋不住轉址和頁面內資源，需要搭配 egress 規則。
- 模型造訪的頁面會影響它的行為，所以要放在 sandbox 加用完即丟的 profile 裡跑。
- 範例 driver 只示範介面，production 要補上它省略的功能。

## 練習
1. 設定 `ALLOWED_DOMAINS` 與 `HEADLESS=0`，換一個網域跑一次 `run`，看模型的 tool 呼叫流程。
2. 把 `ALLOWED_DOMAINS` 設成空字串，觀察 `navigate` 被拒絕時模型怎麼回應。
3. 在 `exercise` 加一個會被拒絕的呼叫（例如非 http(s) 的網址），確認它回 `is_error`。
