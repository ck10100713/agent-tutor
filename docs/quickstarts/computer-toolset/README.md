---
translated: true
source: computer-toolset/README.md
---
# Computer Toolset Quickstart

> 原文：[computer-toolset/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/computer-toolset/README.md)

## 這篇在做什麼

這是 Claude computer toolset（`computer_toolset_20260801`）最精簡的 VNC 範例，有 Python 跟 TypeScript 版。你只要在 `tools` 宣告一個 toolset 項目，model 就會把每個桌面動作（`screenshot`、`left_click`、`type` 等）當成獨立 tool 呼叫，由 driver 在桌面上執行。

## 學完你會

- 用 VNC server 跑起 computer toolset 的範例，讓 Claude 操作一個拋棄式桌面。
- 不用 model 就能用 `exercise` 測試 driver 對各種 tool call 的回應。
- 知道範例 driver 實作了哪些 tool、省略了哪些，以及做 production driver 還缺什麼。

## 開跑前

- Anthropic API key，放在 `ANTHROPIC_API_KEY`。
- 一個沒設密碼的 VNC server，螢幕不超過 1920×1200，且一定要在 sandbox 裡的拋棄式桌面上跑。
- Python 3.10+ 或 Node.js 20+。

The minimal VNC example of Claude's computer toolset (`computer_toolset_20260801`)，有 Python 和 TypeScript 版本。你在 `tools` 宣告一個 toolset 項目，model 把每個桌面動作（`screenshot`、`left_click`、`type` 等）當成各自獨立的 tool 呼叫，再由 driver 在桌面上執行這些呼叫。

Driver 只有幾百行。它透過 VNC（RFB protocol）操作一個桌面，實作了 toolset 十個 tool。它展示的是介面，不是 production 等級的程式碼。

| File | What it is |
| --- | --- |
| `run.py` / `run.ts` | 這個 quickstart：建立範例 driver、交給 tool runner，並印出 model 的訊息。從這裡開始。 |
| `exercise.py` / `exercise.ts` | 不用 model 驅動同一個 toolset：把 model 會送的呼叫送到你的 VNC server，並印出 model 會看到的內容。 |
| `vnc_computer.py` / `vnc-computer.ts` | 範例 driver：SDK 抽象 computer toolset 的子類別，用原始 RFB 操作一個桌面。 |

> [!WARNING]
> 螢幕上的內容會影響 model 下一步做什麼，而且被聚焦的 terminal 會執行它收到的任何輸入。請對 sandbox 裡的拋棄式桌面執行，不要對你自己的桌面。
>
> Server 沒有設密碼，所以要把它限制在 localhost（下面兩個指令都用 `-localhost`）；從 container 執行時，只把它的 port 發佈到 host 的 loopback（`-p 127.0.0.1:5900:5900`）。
>
> 在把它指向其他東西之前，先讀 SDK tool helper 文件裡的 "Running a computer toolset safely"：[Python](https://github.com/anthropics/anthropic-sdk-python/blob/main/computer-toolset.md#running-a-computer-toolset-safely)、[TypeScript](https://github.com/anthropics/anthropic-sdk-typescript/blob/main/computer-toolset.md#running-a-computer-toolset-safely)。

## 安裝

你需要：

- 在 `ANTHROPIC_API_KEY` 設好 Anthropic API key；
- 有 computer toolset helper 的 Anthropic SDK：Python 用 `anthropic` 2.0 或更新版本（`anthropic.tools.computer`），TypeScript 用 `@anthropic-ai/sdk` 1.0 或更新版本（`@anthropic-ai/sdk/helpers/beta/toolsets`）。`requirements.txt` 和 `package.json` 已經釘好版本；
- Python 3.10+ 或 Node.js 20+；
- 一個沒設密碼的 VNC server，螢幕不超過 1920×1200。TigerVNC 的 `Xvnc` 是單一程序、不需要其他東西（`apt install tigervnc-standalone-server`）；`-SecurityTypes None` 會關掉它預設要求的密碼：

```bash
Xvnc :1 -geometry 1280x800 -depth 24 -SecurityTypes None -localhost -rfbport 5900 &
DISPLAY=:1 xterm -geometry 160x50 &
```

在既有的 X display 前面用 `x11vnc` 也可以（`x11vnc -display :0 -nopw -localhost -forever`）。它是用輪詢取得螢幕畫面，所以輸入後馬上截圖可能會看到輸入前的畫面，model 就會重複動作或再截一次圖。

```bash
cd computer-toolset/python
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

```bash
cd computer-toolset/typescript
npm install
```

## 執行

```bash
python run.py "Open a terminal, run date, and tell me today's date and time zone"     # Python
npm run start -- "Open a terminal, run date, and tell me today's date and time zone"  # TypeScript
```

整個命令列就是任務內容。`run.ts` 不讀任何選項，所以連 `--help` 也會被當成任務送給 model。`run.py` 則會自己回應 `--help`。

它會在 model 的每則訊息抵達時印出來：先是 tool call，最後是最終答案。`run` 只用 SDK 的抽象 toolset，所以換別的 driver 也是一樣：建立它、在 `tools` 傳進去、對 tool runner 跑 loop，loop 結束時關閉它。

除了截圖以外的每個動作之前，`run` 都會把呼叫顯示給你，只有你回答 `y` 才會執行。這是透過 toolset 的 `confirm` 選項做到的。`exercise` 傳入的 `confirm` 則會核准所有呼叫。

| Variable | Effect |
| --- | --- |
| `VNC_HOST` | VNC server 的 host。預設：`127.0.0.1`。 |
| `VNC_PORT` | VNC server 的 port。預設：`5900`。 |
| `MODEL` | 要跑的 model。預設：`claude-sonnet-5-5`。 |

## 不用 model 測試 toolset

`exercise` 不需要 API key。它把 driver 連到 VNC server，並透過 tool runner 使用的進入點，送出 model 會送的呼叫：

```bash
python exercise.py        # Python
npm run exercise          # TypeScript
```

它會印出 model 會看到的每個 `tool_result`，截圖的 bytes 會省略。會回應六個呼叫：`screenshot`、在螢幕中心的 `left_click`、`type`、`key`、`wait`，以及第二次 `screenshot`（如果 server 延遲，會重試幾秒）。兩個會被以 `is_error` 拒絕：超出螢幕一個像素的 `left_click`，以及 driver 沒實作的 `zoom`。

只要有任何呼叫的結果不同，就會以非零狀態結束。

## 範例 driver 實作了什麼、省略了什麼

已實作：`screenshot`（整個螢幕，原樣）、`left_click`、`right_click`、`double_click`、`triple_click`、`mouse_move`、`scroll`、`type`、`key`（像 `Return` 或 `Page_Up` 的名稱、單一字元，或像 `ctrl+s` 的組合鍵）和 `wait`。其餘由 SDK 提供：tool schema、對 driver 沒實作的 tool 的拒絕處理，以及 tool runner。

沒有座標的 click 會在指標上次所在的位置動作，click 的 `text` 裡的修飾鍵組合會在點擊期間按住。

省略的部分：

- 所有其他 tool：`zoom`、`left_click_drag`、`left_mouse_down`、`left_mouse_up`、`middle_click`、`hold_key` 和 `cursor_position`；
- 縮放：螢幕原樣送出，driver 連線時會拒絕寬度超過 1920 或高度超過 1200 的螢幕。更大的螢幕可能需要縮放以符合 model 的圖片限制，之後座標再縮放回去；
- VNC 密碼，以及比 RFB 3.7 更舊的 server：driver 對提供 `None` security type 的 server 使用 RFB 3.7 或更新版本；
- Raw 以外的 encoding：每張截圖都未壓縮地傳整個螢幕，1280×800 約 4 MB，localhost 沒問題，其他地方會慢；
- driver 連線期間螢幕大小改變；
- 按住 shift 的字母：`shift+a` 會輸入 `a`；
- `wait` 的上限：driver 會睡 model 要求的任何時間；
- server 停止回應時的恢復：截圖會等 10 秒然後失敗，之後每一次也都是。要重新連線得建立新的 driver。

Production driver 需要這份清單中的大部分。上面連結的 SDK 指南涵蓋每個部分。

## 重點整理

- Computer toolset 只要在 `tools` 宣告一個項目，每個桌面動作就成為獨立 tool，由 driver 執行。
- 螢幕內容會影響 model 的下一步，所以一定要在 sandbox 裡的拋棄式桌面、只開在 localhost 的 VNC 上跑。
- `confirm` 選項讓每個非截圖動作先經過人確認，是最基本的安全閘門。
- `exercise` 不需要 model，可以單獨驗證 driver 的行為。
- 範例 driver 只是示範介面，缺少縮放、密碼、壓縮 encoding 和錯誤恢復，不能直接拿來 production。

## 練習

1. 用 `VNC_PORT` 環境變數把 VNC server 開在別的 port，再跑 `exercise` 確認連得上。
2. 跑 `run`，給一個簡單任務（例如打開 terminal 輸入一行字），每次 `confirm` 提示時看清楚呼叫內容再決定是否回 `y`。
3. 閱讀 `vnc_computer` 的程式，試著補上一個被省略的 tool（例如 `middle_click`），再用 `exercise` 驗證。
