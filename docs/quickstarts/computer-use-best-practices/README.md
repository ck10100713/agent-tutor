---
translated: true
source: computer-use-best-practices/README.md
---
# 用 Claude 操作電腦與瀏覽器

> 原文：[computer-use-best-practices/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-best-practices/README.md)



## 這篇在做什麼

這是 Anthropic 的 macOS computer-use 參考實作，在本機跑（不用 Docker），讓 Claude 看螢幕截圖、控制滑鼠鍵盤和 headless 瀏覽器。重點是讓你讀懂每個 tool 的定義、截圖縮放和 prompt caching 怎麼做，再改成自己的版本，不是拿來當 library 直接 import。

## 學完你會

- 看懂 computer-use 與 browser-use tool 的 name、description、JSON schema 長什麼樣，並能自己改。
- 知道截圖為什麼要先縮放、座標怎麼換算回原圖，以及 prompt caching 與 image pruning 怎麼控制成本。
- 用 `Config` 的 TOML 與環境變數調整行為，並用 trajectory viewer 與 tool panel 除錯。

## 開跑前

- 只支援 macOS，需要 Python 3.11 以上（macOS 內建的 3.9 不行）。
- 需要 Anthropic API key。
- 終端機要授權 Screen Recording 和 Accessibility。
- 強烈建議在可丟棄的 macOS VM 裡跑，agent 會控制你真實的滑鼠、鍵盤和螢幕。


> [!CAUTION]
> **這只是教學用的參考實作。**
>
> 強烈不建議在虛擬機器之外執行這個 agent。
> agent 完全控制你的滑鼠、鍵盤和螢幕。
> **沒有任何防護**能阻止它截下含敏感資訊的畫面並上傳到 API、
> 刪除或覆寫重要資料，或開啟並操作你機器上的任何應用程式。
>
> 請在可丟棄的 macOS VM 裡執行。[UTM](https://mac.getutm.app/) 和
> [Parallels](https://www.parallels.com/) 都支援 macOS guest；我們內部用這些工具做這件事，
> 但與兩者都沒有任何關係，也不認為它們比其他替代品好。
>
> 如果你想要有內建防護、讓使用者掌控流程的 computer-use 功能，
> 而不是教學用的骨架，請用
> [**Cowork**](https://claude.ai/downloads)。

這個 repository 是**參考實作**：用意是讓你閱讀、理解並改成適合自己的用途，不是當 library import，也不是可直接上線的 SDK。它搭配
[computer-use best-practices guide](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude)，
兩份最好並排閱讀。

它**只支援 macOS**。按鍵處理、`pyautogui` backend 和
`sandbox-exec` 都是 Mac 專屬的；容器化或 Linux 版本不在這裡的範圍內。如果你想要最小的容器化起點，
可以看這個 repository 裡的 [Computer Use Demo](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-demo)（Docker + X11
桌面）或 [Browser Use Demo](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo)（Docker +
Playwright，只有瀏覽器）。

這是一個專注、偏教學的 Claude computer-use 示範，跑在 **macOS** 上，
**本機**執行（不用 Docker），包含：

- 明確定義的 tool：模型看到的每個 computer-use 和 browser-use tool 都完整寫在
  `computer_use/tools/`，所以你可以讀到放進 API 呼叫的確切 name、description 和 JSON schema。
- 正確的截圖尺寸：`computer_use/image.py` 移植了 API 的參考縮放邏輯，
  讓模型看到的像素就是你送出的像素，點擊座標才會準。
- Batch tool：`computer_batch` / `browser_batch` 讓模型把可預測的動作串在同一個 turn。
  當模型能有把握地先規劃好幾步時，batching 可以明顯降低延遲和成本；
  demo 會在單一動作的呼叫後附上 `BATCH_REMINDER` 來引導這種用法。
- 透過 `sandbox-exec` 沙盒化的 `bash` / `python`（profile 在 `sandbox/`）。
- Trajectory 記錄（`runs/…`）和 Streamlit viewer。
- 可以手動測試 tool 的 FastAPI debug 面板。

> [!TIP]
> **快速開始**
>
> 用 [Claude Code](https://claude.ai/code)？在它裡面打開這個資料夾並執行
> **`/first-run`**，會有引導式的流程。
>
> 不然需要的就是這三個指令：
>
> ```bash
> python -m pip install -r requirements.txt && python -m playwright install chromium
> echo "ANTHROPIC_API_KEY=<YOUR API KEY HERE>" > .env
> python -m computer_use "open TextEdit and type hello world"
> ```
>
> 這個任務會移動你真實的滑鼠和鍵盤，執行前請先讀這份文件最上面的
> [警告區塊](#computer-and-browser-use-with-claude)。完整設定（包含 Python 3.11+ 的需求）
> 請看 [Installation](#installation)。

## 安裝

需要 **Python 3.11+**。macOS 內建的 `python3` 是 3.9，
不能用；請先安裝較新的直譯器（例如
`brew install python@3.13`，或用
[python.org](https://www.python.org/downloads/) 的安裝程式），再用它建立下面的 virtual environment。

```bash
# Replace `python3.13` with whatever 3.11+ interpreter you installed.
python3.13 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Download a headless Chromium for the `browser` tool (one-time, ~150 MB):
python -m playwright install chromium
```

<details>
<summary>或用 <code>uv</code>（比較快）</summary>

```bash
uv sync
uv run playwright install chromium
```

這份 README 其餘部分用的是一般的 `python ...` 指令；裝了 uv 的話，
任何指令前面都可以改加 `uv run`，不用啟動 venv。
</details>

在 System Settings → Privacy &
Security 把 **Screen Recording**（截圖用）和
**Accessibility**（控制滑鼠鍵盤用）授權給你的終端機，然後完全結束並重開終端機，macOS 才會套用變更。
agent 的 preflight 在第一次執行時會替你打開這些設定面板；
想自己直接跳過去的話：

```bash
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
```

<p>
  <img src="https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/computer-use-best-practices/docs/images/screen-recording-permissions.jpg" alt="Screen &amp; System Audio Recording pane in System Settings" width="49%">
  <img src="https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/computer-use-best-practices/docs/images/accessibility-permissions.jpg" alt="Accessibility pane in System Settings" width="49%">
</p>

在 macOS 15 (Sequoia) 以後，agent 第一次截圖時，你還會看到另一個
**"bypass the system private window picker"** 對話框，之後大約每個月一次。
這是 macOS 對舊版螢幕擷取 API 的重新授權，跟上面的開關無關；按 **Allow** 即可。

設定 API key，可以 export，也可以放在 repo 根目錄的 `.env` 檔
（複製 `.env.example`）：

```bash
cp .env.example .env  # then edit .env
# or: export ANTHROPIC_API_KEY=...
```

## 執行 agent

```bash
python -m computer_use "open TextEdit and type hello world"
```

只用瀏覽器的範例（不想讓 agent 碰你的桌面時很方便；這會完全停用 `computer` tool）：

```bash
CU_ENABLE_COMPUTER_USE_TOOLS=false python -m computer_use \
  "Navigate to https://en.wikipedia.org/wiki/Special:Random three times, \
   take a screenshot each time, then summarize what you saw."
```

這會開啟互動式 session。印出安全橫幅並檢查 macOS 權限後，agent 進入一個 loop：

1. 模型的回應會**即時串流到你的終端機**：thinking 用暗灰色，assistant 文字用一般粗細，
   每個 tool 呼叫是一行青色的 `→ computer({"action": "screenshot"})`。
2. loop 在你真實的機器上執行被要求的 tool（截圖、移動滑鼠、打字、開啟 app 等），
   並把結果印成一行黃色的 `← computer: [image 105KB]`。
3. 一行暗色的 `[usage] in=… cache_read=… out=… | cache_eff=…% | 12.3s` 會顯示這個 turn 的
   token 數量和 prompt cache 效率。
4. 步驟 1-3 重複，直到模型不再呼叫 tool，這時會出現 `you >` 提示讓你輸入後續訊息。
   任何時候按 Ctrl-C 可以中斷目前的 turn 並回到那個提示；輸入空行則離開。

<p align="center">
  <img src="https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/computer-use-best-practices/docs/images/hello-world-example.jpg" alt="Terminal output of the agent running the TextEdit hello-world task" width="800">
</p>

agent 送出和收到的所有內容，也會寫進
`runs/<timestamp>/`，格式是 JSONL transcript 加上 JPEG 截圖，
之後可以在 viewer 裡重播。

常用 flag：`--model {claude-haiku-4-5,claude-sonnet-4-6,claude-opus-4-6,claude-opus-4-7}`、
`--thinking {off,low,medium,high,max}`、`--max-iters N`、`--skip-preflight`。

## 檢視 trajectory

```bash
python -m streamlit run dev_ui/trajectory_viewer/app.py
```

會開一個瀏覽器分頁，側邊欄列出所有 run（最新的在前）。
主區域把選到的 run 渲染成聊天紀錄：使用者訊息、
assistant thinking（可收合）、assistant 文字、每個 tool 呼叫（以 code block 呈現），
以及每個 tool 結果（展開的面板，內含文字輸出和內嵌的截圖）。
這是事後檢查模型實際看到什麼、做了什麼決定最簡單的方式。

<p align="center">
  <img src="https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/computer-use-best-practices/docs/images/trajectory-viewer.jpg" alt="Trajectory viewer rendering the hello-world run" width="700">
</p>

## Localization demo

```bash
python -m uvicorn dev_ui.localization_demo.server:app --reload --port 8001
# open http://127.0.0.1:8001
```

這是點擊式 localization 的最小起點，用來讓縮放與還原座標的流程具體可見。
上傳任一張圖片，輸入描述（「藍色的 Submit 按鈕」），伺服器會：(1) 用
`target_image_size()` 縮放圖片，讓 API 不會再縮一次，(2) 搭配單一
`point_at` tool 並用 `tool_choice` 強制送出，(3) 取得模型回傳的
`(x, y)`（這是在*縮放後*圖片的座標空間），(4) 用 `x * orig_w / sent_w`
換算回原圖。頁面會並排顯示兩張圖，各自標上標記，讓你看到兩個座標空間。
整個流程在 `dev_ui/localization_demo/server.py` 裡大約 100 行。

<p align="center">
  <img src="https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/computer-use-best-practices/docs/images/localization-demo.jpg" alt="Localization demo locating the Chrome icon in an uploaded screenshot" width="700">
</p>

## Tool 面板

```bash
python -m uvicorn dev_ui.tool_panel.server:app --reload
# open http://127.0.0.1:8000
```

一個不經過模型、手動測試 tool 的單頁介面。
每個 tool 都有一個從它的 `input_schema` 自動產生的表單；填好欄位、
設一個倒數延遲（讓你有時間切換到目標視窗，動作才會觸發），然後按 Run。
結果區會顯示回傳的 JSON 和內嵌的截圖。點截圖時會把你點的圖片像素位置填進
最近的 `coordinate` 欄位，並顯示對應的螢幕像素位置，這是檢查座標縮放是否正確最快的方法。
缺少 Screen Recording 或 Accessibility 權限時會出現紅色橫幅。

<p align="center">
  <img src="https://raw.githubusercontent.com/anthropics/claude-quickstarts/main/computer-use-best-practices/docs/images/tool-panel.jpg" alt="Tool panel with per-tool forms on the left and a screenshot result on the right" width="700">
</p>

## 設定

所有可調整的參數都在 `constants.py` 的 `Config` dataclass 上。目前生效的
實例是 `constants.cfg`；程式碼其餘部分都讀 `cfg.<field>`，所以只有一個資料來源。
你可以不改檔案就覆寫任何欄位（後面的優先）：

1. **TOML 檔**：複製 `config.example.toml`，設定你要的欄位，
   再用 `CU_CONFIG` 指向它。
2. **每個欄位的環境變數**：`CU_<FIELD_NAME>=value`。這些疊在 TOML 檔之上。

兩種都可以放在 `.env` 或你的 shell。範例：

```bash
# one-off: turn off browser tools and bump JPEG quality
CU_ENABLE_BROWSER_USE_TOOLS=false CU_JPEG_QUALITY=85 \
  python -m computer_use "open Notes and type hello"

# pin a viewport via env var (string is coerced to a tuple)
CU_BROWSER_VIEWPORT=1280x720 python -m computer_use "..."

# or keep a config.toml and point at it from .env
#   .env:      CU_CONFIG=config.toml
#   config.toml:
#     enable_advisor_tool = true
#     image_prune_strategy = "none"
#     extra_models = ["some-beta-model"]
```

字串值會被轉成宣告的欄位型別（`"true"`→`True`、
`"80"`→`80`、`"1280x720"`→`(1280, 720)`、`"none"`→可選 int 的 `None`）。

### 功能開關一覽

| Field | Default | What it does |
|---|---|---|
| `enable_computer_use_tools` | `true` | `computer`, `computer_batch`, `open_application` (pyautogui screen control). At least one of this or browser must be on. |
| `enable_browser_use_tools` | `true` | `browser`, `browser_batch` (headless Playwright). |
| `enable_editor_tool` | `true` | `editor` (view/create/str_replace/insert) confined to the per-run scratch dir; bash/python share the same workspace. Also adds the TODO.md guidance to the system prompt. |
| `enable_advisor_tool` | `false` | Server-side advisor: the executor model can consult `advisor_model` (Opus by default) mid-generation. See [Advisor tool](#advisor-tool-experimental). |
| `enable_autocompaction` | `true` | Server-side `compact_20260112`: when input tokens cross `autocompaction_trigger_tokens`, the server summarizes older context. Only applied on supported models (Sonnet/Opus). |
| `image_prune_strategy` | `"interval"` | `"none"` keeps every screenshot; `"simple"` keeps the last N (cache-hostile); `"interval"` keeps the prefix stable for `image_prune_interval` turns. See the next section. |
| `print_usage` | `true` | Per-turn `[usage]` line with token counts and cache efficiency. |
| `extra_models` | `()` | Additional model IDs accepted by `--model` (older or beta models not in the built-in enum). |

`Config` 上其他都是數值型的調整參數（重試次數、JPEG 品質、
viewport 大小、advisor 上限等）；細節看 `constants.py` 裡每個欄位的註解。

## 明確定義的 tool vs. hosted 的 `computer` tool
這個 demo 預設把每個 tool 都明確定義：`computer` tool 的
name、description 和 JSON schema 全都在
`computer_use/tools/computer.py`，所以你可以讀到也能編輯模型實際看到的內容，
中間沒有任何 server 端預設值擋著。這就是參考實作的重點。

代價是 safety classifier 的涵蓋範圍。API 的 computer-use 專用 safety classifier
（包含對截圖內容的 prompt-injection 偵測）**只有**在 request 宣告
Anthropic 定義的 computer tool 時才會執行。用明確的 schema 時，你的 request 走的是通用 safety 路徑，
你得靠自己的 prompt-injection 防護（system prompt 的指示、
這份 README 最上面建議的 VM 隔離，以及你自己的監控）。

如果你想要那些 classifier，又不想放棄 demo 的其他部分，就設
`cfg.use_hosted_computer_tool = True`（或 `CU_USE_HOSTED_COMPUTER_TOOL=true`）。
只有 `computer` tool 的*宣告*會改變；`computer_batch`、`browser`、
`bash` 和其餘 tool 仍然是明確定義，而且每個 tool 仍然在本機執行。

在第一方 API 上，hosted 宣告是 computer **toolset**，
`{"type": "computer_toolset_20260801"}`，這是單一個沒有名字的項目，
會為每個 action 宣告一個成員 tool，不需要 beta header，也不需要顯示尺寸
（座標一律是截圖像素，你送出的截圖就建立了那個座標框架）。
自己寫 loop 時值得知道 toolset 的三件事，這個 repo 的 `loop.py` 都有示範：

- **成員呼叫是一般的 `tool_use` block，以 action 命名**
  （`left_click`、`zoom` 等），帶有 `toolset_name: "computer"`，input 裡沒有 `action`
  欄位。`ToolCollection.run` 依 `(toolset_name, name)` 路由，並把 name 折回
  `action`，所以明確定義的 `ComputerTool` 兩種宣告都能服務。每個成員（包含 toolset 預設啟用的 `zoom`）都在那裡實作。
- **一個 turn 可以帶好幾個成員呼叫。** 它們依 block 順序依序執行；第一個失敗後，其餘的會以
  `is_error: true` 和契約規定的 `"Not executed: …"` 文字回覆，而不是執行，
  因為後面的每個動作都假設前面的成功了。（這就是 `computer_batch` 為明確定義的 tool 提供的 batching，由 toolset 原生做到。）
- **每個成員的 `tool_result` 必須帶有跟它的 `tool_use` 相同的 `toolset_name`**；
  一般 tool 的結果則不能帶。`_tool_result_block` 會蓋上這個欄位，
  包括 Ctrl-C 補上的 `[interrupted by user]` 結果。

Vertex 和 Bedrock 還不提供 toolset，所以用這兩個 provider 時 hosted
模式會退回有日期的 `computer_20250124` tool 加上它的 beta header
（由 `Config.hosted_computer` 決定）；這時模型以 `name: "computer"`
搭配 `input.action` 呼叫，也就是明確定義 tool 本身的形狀。

## Provider

`cfg.provider` 選擇 API 介面：`"anthropic"`（預設，第一方）、
`"vertex"`（Google Cloud，透過 `AnthropicVertex`），或 `"bedrock"`（AWS，透過
`AnthropicBedrock`）。每種需要的憑證見 `.env.example`。
Vertex 和 Bedrock 還需要 SDK 的選用依賴，`requirements.txt` 不含這些：
`pip install "anthropic[vertex]"` 或
`pip install "anthropic[bedrock]"`。

Vertex 和 Bedrock 對 request body 大小有上限，第一方 API 沒有。demo 在 image pruner 裡強制一個保守的門檻
（Vertex 18 MB、Bedrock 11 MB）：如果序列化後的訊息 list 超過上限，
就強制 prune 到 `cfg.image_prune_min` 張圖，並重置 interval 週期，讓後續 turn 從小的開始。

advisor tool 和 server 端 autocompaction 是只限第一方的 beta
功能。在 `provider != "anthropic"` 時啟用任一個，會在啟動時丟出 `ValueError`，
並指出衝突的設定；把它設成 `False`（或換 provider）才能繼續。

## 有效的 caching 與 context pruning

computer-use 的 trajectory 幾乎每個 turn 都會累積一張截圖，
每張截圖大約 1,500 個 input token。30 個 turn 後，光圖片歷史就有約 45k token，
每次 API 呼叫都要重送（也重付一次）。這個 repo 用兩個機制壓住它：

**Prompt caching。** `loop.py` 在 system prompt 放一個 `cache_control: {"type": "ephemeral"}`
斷點，在最近一個 user turn 的最後一個 tool-result block 再放一個。
下次呼叫時，API 可以把斷點之前的內容全部從 cache 讀取（約 input-token 價格的 10%，延遲也明顯更低）。
每個 turn 印出的 `[usage]` 行會顯示 `cache_read` 對 `in`，讓你看命中率。

**Image pruning。** Prompt caching 只有在 request 的*前綴*在兩次呼叫之間
逐位元組完全相同時才有用。限制截圖歷史的天真做法
（「只留最後 N 張，更舊的換成 placeholder」），一旦超過 N，每個 turn 被替換的圖片都不一樣，
所以前綴每個 turn 都變，cache 每個 turn 都 miss。

`cfg.image_prune_strategy = "interval"`（預設，見
`computer_use/formatters.py`）的做法是讓保留的圖片數量從 `cfg.image_prune_min`
*逐步*增加到
`cfg.image_prune_min + cfg.image_prune_interval - 1`，然後落回。在連續
`cfg.image_prune_interval` 個 turn 裡，*同樣*的舊圖片對應到
*同樣*的 placeholder 文字，前綴保持相同，cache 持續命中。
你每 `cfg.image_prune_interval` 個 turn 才付一次 cache 寫入，而不是每個 turn 都付。
把 strategy 設成
`"none"` 可以完全停用 pruning，設成 `"simple"` 則可以看到對 cache 不友善的行為來比較。

### Pruning vs. server 端 context 摘要

`cfg.enable_autocompaction` 會開啟 API 的 server 端 context-management
edit：一旦總 input token 超過 `cfg.autocompaction_trigger_tokens`，
server 就會執行一次獨立的 sub-call，把到目前為止的對話濃縮成
一個簡短的摘要 block，client 在下個 turn 把那個 block 之前的內容全部丟掉。
Pruning 和摘要都能限制 context 大小，但取捨不同：

- **摘要是比較貴的事件。** 它是額外一整個 API turn
  （整段對話進去，多段落的摘要出來），而且下個 turn 從冷的 cache 開始，因為前綴是全新的。
  相比之下，interval-prune 的 rollover 只重新處理有變動的後段，也不產生 output token。
  Pruning 短期內快得多也便宜得多，但長期（跨越許多後續 turn）可能反而更貴，
  因為 image pruning 永遠不會刪掉 user/assistant 訊息，這些訊息會隨時間累積。
- **摘要保留更多資訊。** 摘要保有發生過什麼的文字紀錄；pruning 則是直接把舊截圖刪掉。
  這就是為什麼 `cfg.image_prune_min` 很重要：要設得夠高，
  模型在 rollover 之後才仍有需要的視覺 context。
- **Pruning 只有在真的避免了摘要時才值得。** 因為
  cache 讀取比未快取的 input 便宜大約一個數量級，
  多帶一個已經快取的截圖再一個 turn 幾乎不花錢，
  而把它丟掉會迫使排在它後面的所有內容重新快取。
  丟掉一張圖省下的錢，要在那張圖原本還會被讀大約十次之後，才回收得了失效的成本。
  所以在短的、截圖少、永遠碰不到摘要觸發點的任務上，
  最便宜的設定就是「完全不 prune」：你付多幾張圖的少量 cache 讀取成本，
  同時避開兩種干擾。
- **長的、截圖很多的任務，pruning 比較划算。** 光圖片就會
  超過觸發點時，每 `cfg.image_prune_interval` 張圖做一次便宜的 rollover，
  比讓對話觸發摘要便宜得多。延遲差距也在這裡最大：
  摘要 sub-call 的 output token 生成很慢，所以 rollover 比摘要快非常多，
  即使兩者的金額很接近。

預設值（`image_prune_min=3`、`image_prune_interval=40`、
`autocompaction_trigger_tokens=150_000`）是這樣調的：截圖很多的
執行會在到達摘要觸發點之前就先 prune，而截圖少的
執行兩者都不會發生。如果你的工作負載一直都很短，就把
`image_prune_strategy="none"`，讓摘要當作少見的安全網；
如果一直都很長又很視覺化，就調低 `image_prune_interval`，並把摘要留給 pruning 刪不掉的文字。

## Advisor tool（實驗性）

這不是一般性的建議；請在你自己的
工作負載上試試，看品質提升值不值得多出來的成本和延遲。
設 `enable_advisor_tool = true`（透過 `CU_ENABLE_ADVISOR_TOOL=true` 或你的
`config.toml`），讓 executor model 在生成途中向更強的 advisor model
（預設是 Opus）請教策略性的建議。這是這個 repo 裡唯一
**沒有**定義在 `computer_use/tools/` 的 tool：它完全在 Anthropic 那端執行，
沒有 client 端的 `execute()`。
loop 把它宣告在 `tools` 陣列裡，在 system prompt 附加 advisor 用法的段落
（時機指引，以及如何衡量建議），建議到達時用暗色文字顯示，
並在後續 turn 來回傳遞結果 block。每隔 `cfg.advisor_reminder_interval` 個沒有呼叫
advisor 的 turn，就會在 tool 結果後附上一段簡短提醒。

相關的設定欄位：`advisor_model`、`advisor_max_uses`（每個 request 的上限）、
`advisor_max_conversation_uses`（超過後 loop 會丟掉 advisor，並把它的結果 block 從歷史中移除，
因為 API 會拒絕孤立的結果）、
`advisor_caching`（advisor 端的 prompt caching；每段對話大約呼叫三次 advisor 時打平，
所以預設的 `"5m"` 適合 agent loop），以及 `advisor_reminder_interval`。
每個 turn 的 `[usage]` 行在每次 advisor 呼叫時會多一列，顯示 advisor model 的 token，
這部分跟 executor 分開計費。

## 測試

```bash
python -m pytest
```

## 目錄結構

```
constants.py            Config dataclass + cfg instance, prompts, derived sets
config.example.toml     template for CU_CONFIG overrides
computer_use/
  __main__.py           CLI entrypoint, build_tools(), build_system_prompt()
  loop.py               streaming sampling loop, retry, advisor/compaction wiring
  image.py              target_image_size + JPEG encode + size sanity check
  formatters.py         cache-aware screenshot pruning (interval/simple)
  render.py             terminal output (turn headers, deltas, usage, banners)
  preflight.py          macOS Screen Recording / Accessibility permission check
  trajectory.py         on-disk transcript + images + per-run scratch dir
  tools/
    base.py             Tool ABC + ToolCollection
    result.py           ToolResult + image/document content-block helpers
    computer.py         pyautogui screen control (incl. zoom, key aliasing)
    browser.py          playwright headless chromium
    batch.py            computer_batch / browser_batch
    editor.py           view/create/str_replace/insert in scratch dir
    shell.py            sandboxed bash + python with output cap
    open_app.py         `open -a ...`
sandbox/default.sb      sandbox-exec profile
dev_ui/
  assets/anthropic.css  shared design tokens for all dev UIs below
  trajectory_viewer/    streamlit transcript viewer
  tool_panel/           FastAPI tool-tester (per-tool forms, click-to-coord)
  localization_demo/    label-localization demo (resize/rescale round-trip)
```

## 重點整理

- 參考實作的價值在於每個 tool 都明確寫在程式碼裡，你可以讀到並修改模型實際看到的 name、description 和 schema。
- 截圖要先縮成 API 不會再縮的尺寸，模型回傳的座標是縮放後的座標空間，要換算回原圖才準。
- 用 hosted 的 computer tool 才會啟用 API 的 computer-use safety classifier（含 prompt-injection 偵測），明確 schema 走的是通用路徑，要自己做防護。
- 截圖歷史會讓每次呼叫越來越貴，interval pruning 讓前綴保持穩定以維持 cache 命中，長任務再靠 server 端摘要當後盾。
- 在 macOS 上這個 agent 控制真實的滑鼠鍵盤，一律建議在可丟棄的 VM 裡跑。

## 練習

1. 用 `CU_PRINT_USAGE` 這類 per-field 環境變數（或 TOML）改一個設定，例如把 `enable_browser_use_tools` 關掉，再跑一次 `python -m computer_use`，確認 tool 清單變了。
2. 把 `image_prune_strategy` 分別設成 `"none"`、`"simple"`、`"interval"`，跑同一個 20 個 turn 以上的任務，比較 `[usage]` 行裡的 `cache_read` 和 `cache_eff`。
3. 在 `use_hosted_computer_tool = True` 和預設之間切換，用 trajectory viewer 比較 tool call 的形狀（`left_click` 加 `toolset_name`，對比 `computer` 加 `input.action`），再試著為 `computer_use/tools/computer.py` 的 schema 新增一個你自己的 action。
