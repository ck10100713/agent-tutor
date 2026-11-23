---
translated: true
source: autonomous-coding/README.md
---

# Autonomous Coding Agent Demo

> 原文：[autonomous-coding/README.md](https://github.com/anthropics/claude-quickstarts/blob/main/autonomous-coding/README.md)



## 這篇在做什麼

這是一個極簡的 harness，示範用 Claude Agent SDK 跑長時間的自主寫程式。它用兩個 agent（initializer 加 coding agent）的模式，跨多個 session 把一整個應用程式做出來。

## 學完你會

- 理解 initializer agent 和 coding agent 怎麼分工，並靠 `feature_list.json` 與 git commit 在 session 之間傳遞進度。
- 看懂這個 demo 的多層安全設計：sandbox、檔案系統限制、bash allowlist。
- 自己調整要做的應用、功能數量與允許的指令，跑出更快的 demo。

## 開跑前

需要安裝最新版的 Claude Code 與 Claude Agent SDK，並設定 `ANTHROPIC_API_KEY`。完整跑完要好幾個小時，會消耗不少 API 額度。

## 前置需求

**必要：** 安裝最新版的 Claude Code 和 Claude Agent SDK：

```bash
# Install Claude Code CLI (latest version required)
npm install -g @anthropic-ai/claude-code

# Install Python dependencies
pip install -r requirements.txt
```

確認安裝成功：
```bash
claude --version  # Should be latest version
pip show claude-code-sdk  # Check SDK is installed
```

**API Key：** 設定你的 Anthropic API key：
```bash
export ANTHROPIC_API_KEY='your-api-key-here'
```

## 快速開始

```bash
python autonomous_agent_demo.py --project-dir ./my_project
```

想用有限的迭代次數來測試：
```bash
python autonomous_agent_demo.py --project-dir ./my_project --max-iterations 3
```

## 時間預期

> **警告：這個 demo 要跑很久！**

- **第一個 session（初始化）：** agent 會產生一份有 200 個測試案例的 `feature_list.json`。這要花好幾分鐘，看起來可能像當掉，這是正常的，agent 正在把所有功能寫出來。

- **後續 session：** 每次 coding 迭代依複雜度可能要 **5 到 15 分鐘**。

- **整個應用：** 把 200 個功能全部做完，通常需要跨多個 session 的**好幾個小時**總執行時間。

**提示：** prompt 裡的 200 個功能是為了完整涵蓋而設計的。想要更快的 demo，可以修改 `prompts/initializer_prompt.md` 減少功能數量（例如 20 到 50 個）。

## 運作方式

### 雙 Agent 模式

1. **Initializer Agent（第 1 個 session）：** 讀取 `app_spec.txt`，建立有 200 個測試案例的 `feature_list.json`，設定專案結構，並初始化 git。

2. **Coding Agent（第 2 個之後的 session）：** 從上一個 session 停下的地方接手，一個一個實作功能，並在 `feature_list.json` 裡把它們標記為通過。

### Session 管理

- 每個 session 都用全新的 context window
- 進度透過 `feature_list.json` 和 git commit 保存
- agent 會在 session 之間自動繼續（延遲 3 秒）
- 按 `Ctrl+C` 暫停，再執行同一個指令就能繼續

## 安全模型

這個 demo 採用縱深防禦的安全做法（見 `security.py` 和 `client.py`）：

1. **OS 層級 Sandbox：** Bash 指令在隔離環境中執行
2. **檔案系統限制：** 檔案操作只限於專案目錄內
3. **Bash Allowlist：** 只允許特定指令：
   - 檔案檢視：`ls`、`cat`、`head`、`tail`、`wc`、`grep`
   - Node.js：`npm`、`node`
   - 版本控制：`git`
   - 程序管理：`ps`、`lsof`、`sleep`、`pkill`（僅限開發程序）

不在 allowlist 裡的指令會被 security hook 擋掉。

## 專案結構

```
autonomous-coding/
├── autonomous_agent_demo.py  # Main entry point
├── agent.py                  # Agent session logic
├── client.py                 # Claude SDK client configuration
├── security.py               # Bash command allowlist and validation
├── progress.py               # Progress tracking utilities
├── prompts.py                # Prompt loading utilities
├── prompts/
│   ├── app_spec.txt          # Application specification
│   ├── initializer_prompt.md # First session prompt
│   └── coding_prompt.md      # Continuation session prompt
└── requirements.txt          # Python dependencies
```

## 產生出來的專案結構

執行後，你的專案目錄會包含：

```
my_project/
├── feature_list.json         # Test cases (source of truth)
├── app_spec.txt              # Copied specification
├── init.sh                   # Environment setup script
├── claude-progress.txt       # Session progress notes
├── .claude_settings.json     # Security settings
└── [application files]       # Generated application code
```

## 執行產生出來的應用

agent 完成（或暫停）後，可以執行產生的應用：

```bash
cd generations/my_project

# Run the setup script created by the agent
./init.sh

# Or manually (typical for Node.js apps):
npm install
npm run dev
```

應用通常會在 `http://localhost:3000` 或類似的網址（確切的 URL 看 agent 的輸出或 `init.sh`）。

## 命令列選項

| Option | Description | Default |
|--------|-------------|---------|
| `--project-dir` | 專案目錄 | `./autonomous_demo_project` |
| `--max-iterations` | agent 最大迭代次數 | 不限 |
| `--model` | 使用的 Claude model | `claude-sonnet-4-5-20250929` |

## 客製化

### 更換要做的應用

編輯 `prompts/app_spec.txt`，指定不同的應用。

### 調整功能數量

編輯 `prompts/initializer_prompt.md`，把「200 features」的要求改成較小的數字，demo 會比較快。

### 修改允許的指令

編輯 `security.py`，在 `ALLOWED_COMMANDS` 裡新增或移除指令。

## 疑難排解

**「第一次執行好像當掉了」**
這是正常的。initializer agent 正在產生 200 個詳細的測試案例，要花不少時間。看到 `[Tool: ...]` 輸出就代表 agent 有在工作。

**「Command blocked by security hook」**
agent 試著執行不在 allowlist 裡的指令。這是安全系統照設計在運作。需要的話，把指令加進 `security.py` 的 `ALLOWED_COMMANDS`。

**「API key not set」**
確認你的 shell 環境有 export `ANTHROPIC_API_KEY`。

## 授權

Anthropic 內部使用。

## 重點整理

- 長時間的自主 coding 靠兩種 agent 分工：initializer 負責規劃與骨架，coding agent 負責逐項實作。
- 每個 session 的 context 都是全新的，進度要存在檔案（`feature_list.json`）和 git 裡才接得起來。
- 安全要多層疊加：OS sandbox、檔案系統限制、bash allowlist，單一防線不夠。
- 功能清單的大小直接決定執行時間，demo 時可以先縮小。
- agent 被 allowlist 擋下是設計行為，要放行就明確改設定。

## 練習

1. 把 `prompts/initializer_prompt.md` 的功能數量從 200 改成 20，跑一次看總時間差多少。
2. 改 `prompts/app_spec.txt`，換成一個你想做的小應用，並用 `--max-iterations 3` 限制迭代次數。
3. 在 `security.py` 的 `ALLOWED_COMMANDS` 加一個指令（例如 `find`），讓 agent 能用，並觀察它在哪些情況會用到。
