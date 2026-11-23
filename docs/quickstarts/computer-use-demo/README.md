---
translated: true
source: computer-use-demo/README.md
---
# Anthropic Computer Use Demo

> 原文：[computer-use-demo/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-demo/README.md)

## 這篇在做什麼

這是 Anthropic 的 computer use 參考實作：用 Docker 起一個 Linux 桌面（X11 + VNC），讓 Claude 透過 agent loop 看螢幕、點滑鼠、打字。你可以在 streamlit 介面跟 agent 對話，同時在旁邊看它操作桌面。

## 學完你會

- 用 Docker 啟動 demo，並選 Claude API、Bedrock 或 Vertex 當後端
- 知道 demo 介面的幾個存取入口（整合介面、streamlit、noVNC、VNC）
- 用 `WIDTH` / `HEIGHT` 設定螢幕尺寸，並理解為什麼建議 XGA 解析度

## 開跑前

- Docker
- 對應後端的憑證：Claude API key，或 AWS（Bedrock）、Google Cloud（Vertex）憑證

> [!NOTE]
> 這個 demo 現在預設用 Claude Opus 4.8（claude-opus-4-8），搭配 adaptive thinking：模型自己決定要想多久，你用可選的 effort 等級來引導。Claude Opus 4.7、Opus 4.6、Sonnet 4.6 也支援 adaptive thinking；較舊的模型（Claude Opus 4.5、Sonnet 4.5、Sonnet 4、Opus 4、Haiku 4.5）仍可用，走的是 extended thinking 和 str_replace_based_edit_tool。

> [!CAUTION]
> Computer use 是 beta 功能。它的風險跟一般 API 功能或聊天介面不一樣，拿來操作網路時風險更高。建議採取這些預防措施：
>
> 1. 用權限最小的專用虛擬機或容器，避免直接的系統攻擊或意外。
> 2. 不要讓模型接觸敏感資料，例如帳號登入資訊，避免資料被竊取。
> 3. 把網路連線限制在允許清單內的網域，減少接觸惡意內容。
> 4. 會造成實際後果的決定，以及需要明確同意的事（例如接受 cookie、執行金融交易、同意服務條款），都要請人類確認。
>
> 在某些情況下，Claude 會照內容裡找到的指令做，即使那跟使用者的指示衝突。例如網頁上或圖片裡的指令可能蓋過使用者的指示，讓 Claude 犯錯。建議把 Claude 跟敏感資料和敏感操作隔離，避免 prompt injection 的風險。
>
> 最後，在自己的產品啟用 computer use 之前，請先告知終端使用者相關風險並取得同意。

這個 repo 幫你開始使用 Claude 的 computer use，提供這些參考實作：

- 建立 Docker 容器（含所有必要相依套件）的 build 檔
- 用 Claude API、Bedrock 或 Vertex 存取 Claude Opus 4.5、Claude Sonnet 4.5、Claude Sonnet 4、Claude Opus 4、Claude Haiku 4.5、Claude 3.7 Sonnet、Claude 3.5 Sonnet 的 computer use agent loop
- Anthropic 定義的 computer use tools
- 用來跟 agent loop 互動的 streamlit app

> [!TIP]
> **想看 production 等級的做法？** 這個 demo 刻意做得很精簡：只示範在 Docker 裡的 Linux 桌面（X11 + VNC）上跑最基本的 agent loop。想看讓 computer-use agent 更可靠、更省錢的常見做法，包括明確的 tool 定義、圖片縮放與修剪、prompt caching、server-side compaction、批次 tool call、沙箱 shell、軌跡記錄，請看 [Computer Use Best Practices](https://github.com/anthropics/claude-quickstarts/blob/main/computer-use-best-practices) quickstart，它直接跑在 macOS（不用容器），並搭配 Anthropic 的 [computer-use best-practices guide](https://claude.com/blog/best-practices-for-computer-and-browser-use-with-claude)。

模型回應品質、API 本身或文件品質的回饋，請用[這份表單](https://forms.gle/BT1hpBrqDPDUrCqo7)，我們很期待聽到你的意見。

> [!IMPORTANT]
> 這個參考實作用的 Beta API 可能會變動。最新資訊請看 [API release notes](https://docs.claude.com/en/release-notes/api)。

> [!IMPORTANT]
> 各元件的分離很弱：agent loop 跑在被 Claude 控制的那個容器裡，同一時間只能給一個 session 用，必要時要在 session 之間重啟或重置。

## Tool 版本

這個 demo 支援每個有日期版本的 Anthropic 定義 computer use tool，可以在 app 側邊欄選。側邊欄預設選跟所選模型相符的版本。

最新的形式 `computer_toolset_20260801` 把 computer tool 宣告成一個 *toolset*：`tools[]` 裡一個沒有名字的項目，替每個 computer 動作宣告一個成員 tool。模型會把每個動作當成獨立的 tool 來呼叫：`tool_use.name` 是成員名稱（`left_click`、`screenshot` 等），區塊帶有 `toolset_name: "computer"`，input 就是該動作的參數，沒有 `action` 這個區分欄位。每個回應成員呼叫的 `tool_result` 都帶同一個 `toolset_name`，同一輪的成員呼叫依序執行，遇到第一個失敗就停，而且這個 toolset 不需要 `anthropic-beta` header。較早的有日期版本（API type 從 `computer_20241022` 到 `computer_20251124`，對應側邊欄的 `computer_use_*` 項目）仍是單一 `computer` tool 加 `action` 參數，並需要各自的 beta header。一個模型只支援 toolset 或它訓練時對應的較早版本，請查 [computer use 文件](https://docs.claude.com/en/docs/agents-and-tools/computer-use)確認各模型支援的版本。

## Quickstart：執行 Docker 容器

### Claude API

> [!TIP]
> API key 可以在 [Claude Console](https://console.anthropic.com/) 找到。

```bash
export ANTHROPIC_API_KEY=%your_api_key%
docker run \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -v $HOME/.anthropic:/home/computeruse/.anthropic \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -it ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

容器跑起來之後，連線方式見下面的[存取 demo app](#accessing-the-demo-app)。

### Bedrock

> [!TIP]
> 要在 Bedrock 用新的 Claude 3.7 Sonnet，要先[申請模型存取權](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access-modify.html)。

你需要傳入有適當權限的 AWS 憑證，才能在 Bedrock 用 Claude。
Bedrock 的認證有幾種做法，更多細節和選項見 [boto3 文件](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html#environment-variables)。

#### 選項 1：（建議）用主機的 AWS 憑證檔和 AWS profile

```bash
export AWS_PROFILE=<your_aws_profile>
docker run \
    -e API_PROVIDER=bedrock \
    -e AWS_PROFILE=$AWS_PROFILE \
    -e AWS_REGION=us-west-2 \
    -v $HOME/.aws:/home/computeruse/.aws \
    -v $HOME/.anthropic:/home/computeruse/.anthropic \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -it ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

容器跑起來之後，連線方式見下面的[存取 demo app](#accessing-the-demo-app)。

#### 選項 2：用 access key 和 secret

```bash
export AWS_ACCESS_KEY_ID=%your_aws_access_key%
export AWS_SECRET_ACCESS_KEY=%your_aws_secret_access_key%
export AWS_SESSION_TOKEN=%your_aws_session_token%
docker run \
    -e API_PROVIDER=bedrock \
    -e AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
    -e AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
    -e AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN \
    -e AWS_REGION=us-west-2 \
    -v $HOME/.anthropic:/home/computeruse/.anthropic \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -it ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

容器跑起來之後，連線方式見下面的[存取 demo app](#accessing-the-demo-app)。

### Vertex

你需要傳入有適當權限的 Google Cloud 憑證，才能在 Vertex 用 Claude。

```bash
docker build . -t computer-use-demo
gcloud auth application-default login
export VERTEX_REGION=%your_vertex_region%
export VERTEX_PROJECT_ID=%your_vertex_project_id%
docker run \
    -e API_PROVIDER=vertex \
    -e CLOUD_ML_REGION=$VERTEX_REGION \
    -e ANTHROPIC_VERTEX_PROJECT_ID=$VERTEX_PROJECT_ID \
    -v $HOME/.config/gcloud/application_default_credentials.json:/home/computeruse/.config/gcloud/application_default_credentials.json \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -it computer-use-demo
```

容器跑起來之後，連線方式見下面的[存取 demo app](#accessing-the-demo-app)。

這個範例示範用 Google Cloud Application Default Credentials 對 Vertex 認證。
你也可以設 `GOOGLE_APPLICATION_CREDENTIALS` 來用任意憑證檔，細節見 [Google Cloud Authentication 文件](https://cloud.google.com/docs/authentication/application-default-credentials#GAC)。

### 存取 demo app

容器跑起來之後，用瀏覽器開 [http://localhost:8080](http://localhost:8080)，就是同時有 agent 聊天和桌面畫面的整合介面。

容器會把 API key 和自訂 system prompt 這類設定存在 `~/.anthropic/`。掛載這個目錄，設定就能在容器重啟後保留。

其他入口：

- 只看 Streamlit 介面：[http://localhost:8501](http://localhost:8501)
- 只看桌面：[http://localhost:6080/vnc.html](http://localhost:6080/vnc.html)
- 直接 VNC 連線：`vnc://localhost:5900`（給 VNC client 用）

## 螢幕尺寸

可以用環境變數 `WIDTH` 和 `HEIGHT` 設螢幕尺寸，例如：

```bash
docker run \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -v $HOME/.anthropic:/home/computeruse/.anthropic \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -e WIDTH=1920 \
    -e HEIGHT=1080 \
    -it ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

我們不建議送超過 [XGA/WXGA](https://en.wikipedia.org/wiki/Display_resolution_standards#XGA) 解析度的截圖，避免[圖片縮放](https://docs.claude.com/en/docs/build-with-claude/vision#evaluate-image-size)帶來的問題。
依賴 API 自己縮圖，會比在 tool 裡自己做縮放得到更低的準確度和更慢的速度。這個專案的 `computer` tool 實作示範了怎麼把圖片和座標從較高解析度縮放到建議的解析度。

自己實作 computer use 時，建議用 XGA 解析度（1024x768）：

- 解析度更高時：把圖縮到 XGA 給模型操作，再把座標按比例對回原解析度。
- 解析度更低或裝置更小（例如手機）：在顯示區域周圍補黑邊，補到 1024x768。

## 開發

```bash
./setup.sh  # configure venv, install development dependencies, and install pre-commit hooks
docker build . -t computer-use-demo:local  # manually build the docker image (optional)
export ANTHROPIC_API_KEY=%your_api_key%
docker run \
    -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
    -v $(pwd)/computer_use_demo:/home/computeruse/computer_use_demo/ `# mount local python module for development` \
    -v $HOME/.anthropic:/home/computeruse/.anthropic \
    -p 5900:5900 \
    -p 8501:8501 \
    -p 6080:6080 \
    -p 8080:8080 \
    -it computer-use-demo:local  # can also use ghcr.io/anthropics/anthropic-quickstarts:computer-use-demo-latest
```

上面的 docker run 指令把 repo 掛進 docker image，所以你可以從主機編輯檔案。Streamlit 已設定好自動重新載入。

## 重點整理

- Computer use 的核心是 agent loop：截圖、模型決定動作、tool 執行、再截圖，demo 把這些放在 Docker 的 Linux 桌面裡。
- 風險很實際：用最小權限的容器、不放敏感資料、限制網域，並防範網頁內容造成的 prompt injection。
- Tool 有不同日期版本，新的 toolset 形式把每個動作拆成獨立 tool；模型只支援它訓練時對應的版本。
- 截圖建議 XGA（1024x768），自己縮放比讓 API 縮圖準確又快。

## 練習

1. 啟動容器時加上 `WIDTH` 和 `HEIGHT`，設成 1024x768，確認桌面畫面尺寸改變。
2. 把 `~/.anthropic/` 掛載進容器，在介面改 system prompt，重啟容器看設定有沒有保留。
3. 在側邊欄切換不同的 tool 版本，觀察 agent 送出的 tool_use 區塊長相有什麼差別（toolset 版有 `toolset_name`、沒有 `action`）。
