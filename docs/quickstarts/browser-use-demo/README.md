---
translated: true
source: browser-use-demo/README.md
---
# Claude 瀏覽器自動化 Demo

> 原文：[browser-use-demo/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/README.md)



## 這篇在做什麼

這是用 Playwright 讓 Claude 操作瀏覽器的完整參考實作，包在 Docker 裡，介面是 Streamlit。Claude 可以瀏覽網站、操作 DOM 元素、擷取內容、填表單，你也可以把它當成自己專案的範本。

## 學完你會

- 用 Docker Compose 把瀏覽器自動化 demo 跑起來，並從網頁或 NoVNC 看 Claude 操作瀏覽器
- 理解用 `ref` 做元素定位，為什麼比像素座標可靠，以及座標怎麼從 1456x819 縮放到 1920x1080
- 知道 `browser.py`、`loop.py`、`streamlit.py` 各自負責什麼，能改成自己的瀏覽器 tool

## 開跑前

- 安裝 Docker 和 Docker Compose
- Anthropic API key

一個用 Playwright 讓 Claude 做瀏覽器自動化的完整參考實作。這個 demo 提供一個容器化的 Streamlit 介面，展示如何讓 Claude 能夠瀏覽網站、與 DOM 元素互動、擷取內容和填寫表單。

> [!TIP]
> **想看 production 就緒的做法嗎？** 這個 demo 刻意做成最精簡的容器化參考，專注在 Docker 裡只用瀏覽器（DOM）的自動化。如果你想看讓 computer-use 和 browser-use agent 更可靠、更省成本的常見做法，包括明確的 tool 定義、圖片尺寸與修剪、prompt caching、server-side compaction、批次 tool call、sandbox shell 和軌跡錄製，請看 [Computer Use Best Practices](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-best-practices) quickstart，它在 macOS 上原生執行完整的 GUI agent（截圖加點擊，再加一個 Playwright 瀏覽器 tool），並搭配 Anthropic 的 [computer-use 最佳實務指南](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude)。

## 概覽

這個 demo 實作一個自訂的瀏覽器 tool，讓 Claude 能跟網頁瀏覽器互動。它提供：

- **DOM 存取**：讀取頁面結構與元素參照
- **導覽控制**：瀏覽 URL 並管理瀏覽歷史
- **表單操作**：直接設定表單輸入值
- **文字擷取**：取得頁面所有文字內容
- **元素定位**：透過 ref 或座標參數與元素互動
- **智慧捲動**：捲動到特定元素或往特定方向
- **頁面搜尋**：在頁面上尋找並標示文字
- **視覺擷取**：截圖與擷取放大的區域

### 相較座標式自動化的優勢

- **可靠性**：透過 `ref` 參數做元素定位，在不同螢幕尺寸與版面都能運作，不像像素座標在視窗縮放時就壞掉
- **直接操作 DOM**：提供對頁面元素及其屬性的結構化可見度，能精準操作動態內容、隱藏元素和複雜的網頁應用
- **網頁專用動作**：內建支援導覽、文字擷取和表單填寫

## 快速開始

### 前置需求

- 系統上已安裝 Docker 和 Docker Compose
- Anthropic API key

### 設定

1. **Clone repository**：
   ```bash
   git clone https://github.com/anthropics/claude-quickstarts.git
   cd claude-quickstarts/browser-use-demo
   ```

2. **設定環境**：
   ```bash
   cp .env.example .env
   # Edit .env file and add your ANTHROPIC_API_KEY
   ```

   顯示解析度設為 1920x1080（16:9），以獲得最佳的座標準確度。
   - 更多選項與座標縮放細節請看 `.env.example`

### 用 Docker Compose 執行

```bash
# For production use:
docker-compose up --build

# For development with file watching (auto-sync changes):
docker-compose up --build --watch
```

### 存取介面：
   - **主要 UI**：http://localhost:8080（Streamlit 介面）
   - **NoVNC 瀏覽器畫面**：http://localhost:6080（看瀏覽器）
   - **VNC**：用任何 VNC client 連到 localhost:5900

https://github.com/user-attachments/assets/4fb72078-6902-4b63-bcd1-5f2c4cd60582

## 使用範例

Demo 跑起來之後，在 Streamlit 介面試試這些 prompt：

- "Navigate to news.ycombinator.com and tell me the top 3 stories"
- "Go to google.com and search for 'Anthropic Claude'"
- "Visit wikipedia.org and find information about artificial intelligence"
- "Navigate to github.com and search for 'playwright'"

注意：目前的 Playwright 實作在 Google.com 搜尋時會碰到 CAPTCHA。要避免的話，建議在 prompt 裡指定網站（例如 navigate to Anthropic.com and search for x）。

## 安全考量

瀏覽器自動化帶有獨特的風險，不同於一般的 API 功能或聊天介面，在用它跟網際網路互動時風險更高。為了降低風險，可以考慮以下預防措施：

1. 在隔離的虛擬機或容器環境中、以最小權限執行瀏覽器，避免直接的系統攻擊或意外。
2. 避免讓模型接觸敏感資料，例如帳號登入資訊，以防資訊被竊取。
3. 考慮設定網域白名單，減少接觸惡意內容的機會。
4. 對可能造成實際影響的決定，以及任何需要明確同意的任務（例如接受 cookie、執行金融交易、同意服務條款），要求人類確認。

在某些情況下，Claude 會遵循內容中找到的指令，即使它跟使用者的指示衝突。例如網頁上或圖片中的指令，可能會覆蓋使用者的指示，或讓 Claude 犯錯。我們建議採取預防措施，讓 Claude 與敏感資料和敏感操作隔離，避開 prompt injection 的風險。

最後，在你自己的產品中啟用瀏覽器自動化之前，請告知終端使用者相關風險並取得他們的同意。

這個 demo 在容器化環境中執行瀏覽器。雖然有隔離，請注意：

- **不要輸入個人憑證或敏感資訊**：這是示範用的工具
- **小心你造訪的網站**：有些網站有反自動化的機制
- **不適用於 production**：這個 demo 僅供學習和開發用途

## 實作參考

這個 demo 展示如何用 Playwright 搭配 Claude 做瀏覽器自動化。所有瀏覽器動作（navigate、click、type、scroll、form_input 等）都以方法的形式，用 Playwright 的 async API 實作在 [browser.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/tools/browser.py)。

### 主要檔案

- **[browser.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/tools/browser.py)**：含所有瀏覽器動作的主要 tool
- **[loop.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/loop.py)**：處理 API 呼叫與回應的 sampling loop
- **[streamlit.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/streamlit.py)**：聊天 UI
- **[browser_tool_utils/](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/browser_tool_utils)**：用於 DOM 擷取、元素尋找和表單操作的 JavaScript 工具

### 核心模式

**元素參照：** JavaScript 工具產生 `ref` 識別碼，讓元素定位在不同螢幕尺寸下都可靠（取代脆弱的像素座標）。

**Tool 設定：**

```python
browser_tool = BrowserTool()

def to_params(self):
    return {
        "name": "browser",
        "description": BROWSER_TOOL_DESCRIPTION,
        "input_schema": BROWSER_TOOL_INPUT_SCHEMA,
    }
```

### 座標縮放

瀏覽器 tool 的實作包含自動座標縮放，確保互動準確：

**運作方式：**
- 瀏覽器 viewport 固定在 1920x1080（16:9 長寬比）
- Claude 以 1456x819 像素處理 16:9 長寬比的截圖（見[文件](https://docs.claude.com/en/docs/build-with-claude/vision#evaluate-image-size)）
- 瀏覽器 tool 會自動把座標從 Claude 處理的解析度（1456x819）縮放到實際的 viewport（1920x1080）
- 這確保點擊和互動發生在正確的位置

實作請看 `browser_use_demo/tools/coordinate_scaling.py`。

這個 demo 使用帶有明確 input schema 的自訂 tool 定義，讓你完全掌控 tool 介面。[browser.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/tools/browser.py) 裡的 `BROWSER_TOOL_DESCRIPTION` 和 `BROWSER_TOOL_INPUT_SCHEMA` 常數，提供一個完整範例，你可以當作自己瀏覽器自動化 tool 的起點。


### 修改與當範本使用

**要修改這個 demo：**
1. 編輯 `browser_use_demo/tools/browser.py` 加功能或改行為
2. 重建 Docker image（volume mount 讓 Python 程式碼可以即時更新）

**要當作自己專案的範本：**
1. 複製 [browser.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/tools/browser.py) 和 [browser_tool_utils/](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/browser_tool_utils)
2. 把 [loop.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/loop.py) 改成適合你的 API 整合
3. 建你自己的 UI，或以 [streamlit.py](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/browser_use_demo/streamlit.py) 當起點

## 架構

```
┌──────────────────────────────────┐
│     Docker Container              │
│                                   │
│  ┌─────────────────────────────┐ │
│  │   Streamlit Interface       │ │  ← User interacts here
│  └──────────┬──────────────────┘ │
│             │                     │
│  ┌──────────▼──────────────────┐ │
│  │  Claude API + Browser Tool  │ │  ← Claude controls browser
│  └──────────┬──────────────────┘ │
│             │                     │
│  ┌──────────▼──────────────────┐ │
│  │   Playwright + Chromium     │ │  ← Browser automation
│  └──────────┬──────────────────┘ │
│             │                     │
│  ┌──────────▼──────────────────┐ │
│  │   XVFB Virtual Display      │ │  ← Virtual display
│  └──────────┬──────────────────┘ │
│             │                     │
│  ┌──────────▼──────────────────┐ │
│  │   VNC/NoVNC Server          │ │  ← Visual access
│  └─────────────────────────────┘ │
└──────────────────────────────────┘
```

## 瀏覽器自動化與 Computer Use 的差異

這個瀏覽器自動化 demo 專門針對網頁自動化做最佳化，有 DOM 感知的功能，像是元素定位、頁面讀取和表單操作。它跟 [computer use demo](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-demo) 有許多共通能力，但瀏覽器自動化多了網頁專用動作，以及用參照而不只是座標來定位元素的能力。Computer use 提供對任何應用程式的通用桌面控制，瀏覽器自動化則專注在瀏覽器內的任務。

### 瀏覽器自動化獨有的動作

這些網頁專用動作在 computer use 裡沒有：

- **navigate**：導覽到 URL，或用 "back"/"forward" 走歷史（需要 text）
- **read_page**：取得帶元素 ref 的 DOM tree；用 text="interactive" 過濾
- **get_page_text**：擷取頁面所有文字內容
- **find**：搜尋文字並標示符合處（需要 text）
- **form_input**：直接設定表單元素的值（需要 ref 和 value）
- **scroll_to**：把元素捲動到可見範圍（需要 ref）
- **execute_js**：在頁面 context 執行 JavaScript 程式碼（需要放 JS 程式碼的 text）

### 與 Computer Use 共通的動作

這些動作的運作跟 computer use 的對應動作類似。關鍵差異是，瀏覽器自動化允許用元素參照（`ref`）來定位，作為座標之外的另一種選擇：

**滑鼠動作**（接受 `ref` 或 `coordinate`）：
- **left_click**、**right_click**、**middle_click**、**double_click**、**triple_click**
- **hover**：移動游標但不點擊（用於 tooltip、下拉選單）
- **left_click_drag**：從 start_coordinate 拖曳到 coordinate
- **left_mouse_down**、**left_mouse_up**：細緻的滑鼠控制

**鍵盤動作**：
- **type**：在游標處輸入文字（需要 text）
- **key**：按下按鍵或組合鍵（需要 text）
- **hold_key**：按住按鍵一段時間（需要 text 和 duration）

**其他**：
- **screenshot**：擷取目前的 viewport
- **scroll**：往某方向捲動（需要 scroll_direction、scroll_amount、coordinate）
- **zoom**：區域放大截圖（需要 region：x1, y1, x2, y2）
- **wait**：等待指定秒數（需要 duration，0-100）

### 此 demo 未包含的 Computer Use 動作

這些桌面層級的 computer use 動作不在這個瀏覽器 demo 裡：

- **cursor_position**：取得游標目前的 (x, y) 像素座標

這對瀏覽器自動化比較不相關，因為 `ref` 參數提供可靠的元素定位，不需要追蹤游標。注意 `hover` 提供跟 `mouse_move` 類似的功能，可用來觸發 hover 狀態。

## 疑難排解

**看不到瀏覽器？**
- 確認 port 6080 可以存取
- 試著重新整理 NoVNC 頁面
- 確認 Docker 分配到足夠的資源

**API 錯誤？**
- 確認你的 Anthropic API key 設定正確
- 確認你用的是相容的模型（Claude 4.5 模型：claude-sonnet-4-5-20250929、claude-opus-4-5-20251101 或 claude-haiku-4-5-20251001）

**瀏覽器動作失敗？**
- 有些網站有反自動化的機制
- 先試比較簡單的網站，測試功能是否正常
- 看瀏覽器畫面，確認發生了什麼事

## 授權標示

這個軟體包含來自 Microsoft Playwright 的元件。詳情請見 [NOTICE](https://github.com/anthropics/claude-quickstarts/blob/main/browser-use-demo/NOTICE) 檔案。

## 致謝

使用以下項目建置：
- [Anthropic Claude API](https://www.anthropic.com)
- [Playwright](https://playwright.dev)
- [Streamlit](https://streamlit.io)
- [NoVNC](https://novnc.com)

## 重點整理

- 瀏覽器自動化用 DOM 的 `ref` 定位元素，比像素座標穩，換螢幕尺寸也不會壞。
- 瀏覽器專用動作（navigate、read_page、form_input、execute_js 等）是 computer use 沒有的，其餘滑鼠鍵盤動作兩邊共通。
- Claude 看到的截圖是 1456x819，tool 會自動把座標縮放到 1920x1080 的實際 viewport。
- 網頁內容裡的指令可能蓋過使用者指示（prompt injection），所以要隔離環境、限制網域、重要操作讓人確認。
- 整個 demo 分成 tool（browser.py）、sampling loop（loop.py）、UI（streamlit.py）三塊，可以各自替換。

## 練習

1. 照 README 把 demo 跑起來，在 Streamlit 輸入一個指定網站的 prompt，同時開 NoVNC 看 Claude 實際怎麼操作。
2. 在 `.env` 改顯示解析度，再看 `coordinate_scaling.py`，說明縮放比例怎麼跟著變。
3. 在 `browser.py` 新增一個簡單動作（例如回傳目前頁面 title），同步更新 `BROWSER_TOOL_INPUT_SCHEMA` 和描述，讓 Claude 能用它。
