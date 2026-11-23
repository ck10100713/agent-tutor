---
translated: true
source: skills/notebooks/01_skills_introduction.ipynb
---

# Claude Skills 入門

> 原文：[skills/notebooks/01_skills_introduction.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/skills/notebooks/01_skills_introduction.ipynb)

用 Claude 的 Excel、PowerPoint、PDF Skills 建立文件、分析資料、自動化工作流程。

## 這篇在做什麼

Skills 是一包包指令、可執行程式和資源，讓 Claude 在特定任務上有專家級的能力。這篇帶你用 API 呼叫 Anthropic 內建的 xlsx、pptx、pdf Skills，產生預算表、簡報和收據，再用 Files API 把檔案下載下來。

## 學完你會

- 說清楚 Skills 的 progressive disclosure 三層載入怎麼省 token
- 用 `client.beta.messages.create()` 加 `container` 和 code execution tool 呼叫 Skills，並列出可用的內建 Skills
- 從回應取出 `file_id`，用 Files API 下載產生的 Excel、PowerPoint、PDF 檔

## 開跑前

- 需要 Anthropic API key，放在 skills 目錄的 `.env`
- Python 3.8 以上，anthropic SDK 要 2.0.0 以上
- 產生一份文件要 40 秒到 2 分鐘，cell 跑的時候不要中斷

學習怎麼用 Claude 的 Skills 功能建立專業文件、分析資料，並用 Excel、PowerPoint 和 PDF 產生來自動化商業工作流程。

> **看看實際效果：** 你要學的 Skills 就是 Claude 檔案建立能力的基礎！到 **[Claude Creates Files](https://www.anthropic.com/news/create-files)** 看這些 Skills 怎麼讓 Claude 直接在 Claude.ai 裡建立和編輯文件。

## 目錄

1. [Setup & Installation](#setup)
2. [Understanding Skills](#understanding)
3. [Discovering Available Skills](#discovering)
4. [Quick Start: Excel](#excel-quickstart)
5. [Quick Start: PowerPoint](#powerpoint-quickstart)
6. [Quick Start: PDF](#pdf-quickstart)
7. [Troubleshooting](#troubleshooting)

## 1. 設定與安裝 {#setup}

### 先備條件

開始前請確認你有：
- Python 3.8 以上
- 來自 [console.anthropic.com](https://console.anthropic.com/) 的 Anthropic API key

### 環境設定（只需做一次）

**如果還沒設定環境**，照以下步驟做。如果在 Colab 上執行，不需要建 venv，直接在 cell 裡用 `pip install` 安裝套件，API key 則用 Colab 的 Secrets 設定。

#### 步驟 1：建立虛擬環境

```bash
# Navigate to the skills directory
cd /path/to/claude-cookbooks/skills

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate     # On Windows
```

#### 步驟 2：安裝相依套件

```bash
# With venv activated, install requirements
pip install -r requirements.txt
```

#### 步驟 3：在 VSCode/Jupyter 選擇 Kernel

**在 VSCode：**
1. 開啟這個 notebook
2. 點右上角的 kernel 選擇器（例如 "Python 3.11.x"）
3. 選 "Python Environments..."
4. 選 `./venv/bin/python` 這個 interpreter

**在 Jupyter：**
1. 從 Kernel 選單 → Change Kernel
2. 選跟你的 venv 對應的 kernel

#### 步驟 4：設定 API Key

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your API key:
# ANTHROPIC_API_KEY=sk-ant-api03-...
```

### 快速檢查安裝

執行下面的 cell 確認環境設定正確：

**如果上面看到任何 ❌ 或 ⚠️ 警告**，請先完成設定再繼續。

**如果 anthropic SDK 版本太舊（需要 2.0.0 以上）：**
```bash
pip install "anthropic>=2.0.0"
```
然後**重新啟動 Jupyter kernel**，讓新版本生效。

---

### API 設定

現在載入 API key 並設定 client：

### API 設定

**⚠️ 重要**：在 skills 目錄建立 `.env` 檔：

```bash
# Copy the example file
cp ../.env.example ../.env
```

然後編輯 `../.env`，填入你的 Anthropic API key。

```python
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path.cwd().parent))


from anthropic import Anthropic
from dotenv import load_dotenv

# Import our file utilities
from file_utils import (
    download_all_files,
    extract_file_ids,
    get_file_info,
    print_download_summary,
)

# Load environment variables from parent directory
load_dotenv(Path.cwd().parent / ".env")

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

if not API_KEY:
    raise ValueError(
        "ANTHROPIC_API_KEY not found. Copy ../.env.example to ../.env and add your API key."
    )

# Initialize client
# Note: We'll add beta headers per-request when using Skills
client = Anthropic(api_key=API_KEY)

# Create outputs directory if it doesn't exist
OUTPUT_DIR = Path.cwd().parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

print("✓ API key loaded")
print(f"✓ Using model: {MODEL}")
print(f"✓ Output directory: {OUTPUT_DIR}")
print("\n📝 Note: Beta headers will be added per-request when using Skills")
```

### 測試連線

確認 API 連線正常：

```python
# Simple test to verify API connection
test_response = client.messages.create(
    model=MODEL,
    max_tokens=1024,
    messages=[
        {
            "role": "user",
            "content": "Say 'Connection successful!' if you can read this.",
        }
    ],
)

print("API Test Response:")
print("".join(block.text for block in test_response.content if block.type == "text"))
print(
    f"\n✓ Token usage: {test_response.usage.input_tokens} in, {test_response.usage.output_tokens} out"
)
```

## 2. 了解 Skills {#understanding}

### 什麼是 Skills？

**Skills** 是一包包有組織的指令、可執行程式碼和資源，讓 Claude 在特定任務上擁有專業能力。可以把它們想成「專家包」，Claude 能動態發現並載入。

📖 讀我們的工程部落格文章：[Equipping agents for the real world with Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

### 為什麼 Skills 重要

學過 MCP (Model Context Protocol) 和 tool 之後，你可能會想 Skills 為什麼重要：

- **Skills 層級比單一 tool 高**：它結合了指令、程式碼和資源
- **Skills 可以組合**：多個 skill 能無縫一起運作
- **Skills 很有效率**：progressive disclosure 讓你只為用到的部分付費
- **Skills 包含驗證過的程式碼**：helper script 運作可靠，省時間又減少錯誤

### 主要好處

- **專家級表現**：不用學習成本就能交出專業成果
- **驗證過的 helper script**：Skills 內含測試過、能用的程式碼，Claude 可以直接使用
- **組織知識**：把公司的工作流程和最佳實務打包起來
- **成本效益**：progressive disclosure 把 token 用量降到最低
- **可靠**：預先測試過的 script 代表錯誤更少、結果更一致
- **省時間**：Claude 用現成的解法，而不是從頭生成程式碼
- **可組合**：多個 skill 一起處理複雜的工作流程

### Progressive Disclosure 架構

Skills 用三層載入模型：

![Progressive Disclosure - How Skills Load](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/skills/assets/prog-disc-1.png)

1. **Metadata**（name：64 字元，description：1024 字元）：Claude 只看到 skill 的名稱和描述
2. **完整指令**（<5k token）：skill 跟任務相關時才載入
3. **連結的檔案**：額外資源只在需要時才載入

![Progressive Disclosure Stages](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/skills/assets/prog-disc-2.png)

這樣可以在提供深度專業能力的同時保持高效率。一開始 Claude 只看到 SKILL.md 的 YAML frontmatter 裡的 metadata。只有 skill 跟任務相關時，才會載入完整內容，包含 helper script 和資源。

### Skill 類型

| Type | Description | Example |
|------|-------------|----------|
| **Anthropic-Managed** | Pre-built skills maintained by Anthropic | `xlsx`, `pptx`, `pdf`, `docx` |
| **Custom** | User-defined skills for specific workflows | Brand guidelines, financial models |

### Skills 概念總覽

![Skills Conceptual Diagram](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/skills/assets/skills-conceptual-diagram.png)

這張圖說明：
- **Skill 目錄結構**：Skills 怎麼用 SKILL.md 和輔助檔案組織
- **YAML Frontmatter**：Claude 一開始看到的 metadata
- **漸進載入**：Skills 怎麼被發現並依需求載入
- **可組合性**：多個 Skills 在同一個請求裡一起運作

### Skills 如何搭配 Code Execution

Skills 需要啟用 **code execution** tool。典型流程如下：

```python
# Use client.beta.messages.create() for Skills support
response = client.beta.messages.create(
    model="claude-sonnet-5-5",
    max_tokens=4096,
    container={
        "skills": [
            {"type": "anthropic", "skill_id": "xlsx", "version": "latest"}
        ]
    },
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[{"role": "user", "content": "Create an Excel file..."}],
    # Use betas parameter instead of extra_headers
    betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"]
)
```

**發生了什麼：**
1. Claude 收到你的請求，並載入了 xlsx skill
2. Claude 用 code execution 建立檔案
3. 回應裡包含已建立檔案的 `file_id`
4. 你用 **Files API** 下載檔案

**重要：Beta API**
- 使用 `client.beta.messages.create()`（不是 `client.messages.create()`）
- `container` 參數只在 beta API 可用
- 用 `betas` 參數啟用 beta 功能：
  - `code-execution-2025-08-25`：啟用 code execution
  - `files-api-2025-04-14`：下載檔案時必須
  - `skills-2025-10-02`：啟用 Skills 功能

⚠️ **注意**：使用 Skills 時，請求裡一定要包含 code_execution tool。

### Token 用量最佳化

跟把指令寫在 prompt 裡相比，Skills 大幅降低 token 用量：

| Approach | Token Cost | Performance |
|----------|------------|-------------|
| Manual instructions | 5,000-10,000 tokens/request | Variable quality |
| Skills (metadata only) | Minimal (just name/description) | Expert-level |
| Skills (full load) | ~5,000 tokens when skill is used | Expert-level |

**最大的好處：** 你可以在 prompt 裡放多個 skill 而不讓它變肥。每個 skill 在真正用到之前，只花 metadata（名稱加描述）的成本。

**範例**：建立有格式的 Excel 檔
- 沒有 Skills：一開始要花約 8,000 token 說明所有 Excel 功能
- 有 Skills：一開始只有極少的 metadata 開銷，呼叫 Excel skill 時才花約 5,000 token
- **關鍵洞察**：98% 的節省是針對一開始的 context。一旦用了某個 skill，完整指令就會被載入。

**額外好處：**
- Skills 內含確定能用的 helper script，可靠度更高
- Claude 用驗證過的程式碼模式，不用從頭生成，省時間
- 結果更一致、更專業

### ⏱️ 預期的產生時間

**⚠️ 重要**：用 Skills 產生文件需要 code execution 和建立檔案，會花一些時間。請耐心等 cell 跑完。

**觀察到的產生時間：**
- **Excel 檔**：約 2 分鐘（含圖表和格式）
- **PowerPoint 簡報**：約 1 到 2 分鐘（簡單的 2 張投影片加圖表）
- **PDF 文件**：約 40 到 60 秒（簡單文件）

**會看到什麼：**
- Cell 執行中會顯示 `[*]`
- 你可能會看到 "Executing..." 狀態持續 1 到 2 分鐘
- **不要中斷 cell**，讓它完整跑完

**💡 建議：**
1. **從簡單開始**：先用最小的範例確認設定沒問題
2. **逐步增加複雜度**：一次加一個功能
3. **有耐心**：操作通常要 40 秒到 2 分鐘
4. **注意**：很複雜的文件可能更久，範例請保持精簡

## 3. 發現可用的 Skills {#discovering}

### 列出所有內建 Skills

來看 Anthropic 管理的 skill 有哪些：

```python
# List all available Anthropic skills
# Note: the Skills API is GA in SDK 2.x (client.skills), no beta header needed
skills_response = client.skills.list(source="anthropic")

print("Available Anthropic-Managed Skills:")
print("=" * 80)

for skill in skills_response.data:
    print(f"\n📦 Skill ID: {skill.id}")
    print(f"   Name: {skill.display_name}")
    print(f"   Latest Version: {skill.latest_version_id}")
    print(f"   Created: {skill.created_at}")

    # Get version details
    try:
        version_info = client.skills.versions.retrieve(
            skill_id=skill.id, version=skill.latest_version_id
        )
        print(f"   Name: {version_info.name}")
        print(f"   Description: {version_info.description}")
    except Exception as e:
        print(f"   (Unable to fetch version details: {e})")

print(f"\n\n✓ Found {len(skills_response.data)} Anthropic-managed skills")
```

### 了解 Skill Metadata

每個 skill 有：
- **skill_id**：唯一識別碼（例如 "xlsx"、"pptx"）
- **version**：版本號或 "latest"
- **name**：人類可讀的名稱
- **description**：這個 skill 做什麼
- **directory**：skill 的資料夾結構

### 版本策略

- Anthropic 的 skill 用 `"latest"`（建議）
- Anthropic 會自動更新 skill
- Production 想要穩定就固定特定版本
- Custom skill 用 epoch timestamp 當版本

### 範例：每月預算試算表

先看兩個例子：一個簡單的一句話，和一個詳細的需求。

#### 簡單範例（1 到 2 行）
先看 Skills 怎麼用最簡短的 prompt 運作：

```python
# Simple prompt - Skills handle the complexity
prompt = "Create a quarterly sales report Excel file with revenue data and a chart"
```

#### 詳細範例
想要更多控制，可以提供具體需求：
- 收入和支出分類
- 加總用的公式
- 基本格式

### 範例：每月預算試算表

我們來建立一個簡單的預算試算表，包含：
- 收入和支出分類
- 加總用的公式
- 基本格式

**⏱️ 注意**：Excel 產生通常要 **1 到 2 分鐘**（含圖表和格式）。Cell 執行時會顯示 `[*]`，請耐心等待！

```python
# Create an Excel budget spreadsheet
excel_response = client.beta.messages.create(  # Note: Using beta.messages for Skills support
    model=MODEL,
    max_tokens=4096,
    container={"skills": [{"type": "anthropic", "skill_id": "xlsx", "version": "latest"}]},
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[
        {
            "role": "user",
            "content": """Create a monthly budget Excel spreadsheet with the following:

Income:
- Salary: $5,000
- Freelance: $1,200
- Investments: $300

Expenses:
- Rent: $1,500
- Utilities: $200
- Groceries: $600
- Transportation: $300
- Entertainment: $400
- Savings: $1,000

Include:
1. Formulas to calculate total income and total expenses
2. A formula for net savings (income - expenses)
3. Format currency values properly
4. Add a simple column chart showing income vs expenses
5. Use professional formatting with headers
""",
        }
    ],
    # Use betas parameter for beta features
    betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"],
)

print("Excel Response:")
print("=" * 80)
for content in excel_response.content:
    if content.type == "text":
        print(content.text)
    elif content.type == "tool_use":
        print(f"\n🔧 Tool: {content.name}")
        if hasattr(content, "input"):
            print(f"   Input preview: {str(content.input)[:200]}...")

print("\n\n📊 Token Usage:")
print(f"   Input: {excel_response.usage.input_tokens}")
print(f"   Output: {excel_response.usage.output_tokens}")
```

### 下載 Excel 檔

現在取出 file_id 並下載產生的 Excel 檔：

```python
# Extract file IDs from the response
file_ids = extract_file_ids(excel_response)

if file_ids:
    print(f"✓ Found {len(file_ids)} file(s)\n")

    # Download all files
    results = download_all_files(
        client, excel_response, output_dir=str(OUTPUT_DIR), prefix="budget_"
    )

    # Print summary
    print_download_summary(results)

    # Show file details
    for file_id in file_ids:
        info = get_file_info(client, file_id)
        if info:
            print("\n📄 File Details:")
            print(f"   Filename: {info['filename']}")
            print(f"   Size: {info['size'] / 1024:.1f} KB")
            print(f"   Created: {info['created_at']}")
else:
    print("❌ No files found in response")
    print("\nDebug: Response content types:")
    for i, content in enumerate(excel_response.content):
        print(f"  {i}. {content.type}")
```

**✨ 剛剛發生了什麼？**

1. Claude 用 `xlsx` skill 建立了專業的 Excel 檔
2. Skill 處理了所有 Excel 專屬的格式和公式
3. 檔案是在 Claude 的 code execution 環境裡建立的
4. 我們從回應取出 `file_id`
5. 用 Files API 下載了檔案
6. 檔案現在存在 `outputs/budget_*.xlsx`

用 Excel 打開檔案看結果！

## 5. 快速上手：PowerPoint {#powerpoint-quickstart}

現在用 `pptx` skill 建立 PowerPoint 簡報。

### 範例：營收簡報

#### 簡單範例（1 行）
```python
# Minimal prompt - let Skills handle the details
prompt = "Create an executive summary presentation with 3 slides about Q3 results"
```

#### 詳細範例
**注意**：刻意保持簡單（2 張投影片、1 張圖表），以縮短產生時間並展示核心功能。

### 範例：簡單的營收簡報

**注意**：刻意保持簡單（2 張投影片、1 張圖表），以縮短產生時間並展示核心功能。

```python
# Create a PowerPoint presentation
pptx_response = client.beta.messages.create(
    model=MODEL,
    max_tokens=4096,
    container={"skills": [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}]},
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[
        {
            "role": "user",
            "content": """Create a simple 2-slide PowerPoint presentation:

Slide 1: Title slide
- Title: "Q3 2025 Results"
- Subtitle: "Acme Corporation"

Slide 2: Revenue Overview
- Title: "Quarterly Revenue"
- Add a simple column chart showing:
  - Q1: $12M
  - Q2: $13M
  - Q3: $14M

Use clean, professional formatting.
""",
        }
    ],
    betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"],
)

print("PowerPoint Response:")
print("=" * 80)
for content in pptx_response.content:
    if content.type == "text":
        print(content.text)

print("\n\n📊 Token Usage:")
print(f"   Input: {pptx_response.usage.input_tokens}")
print(f"   Output: {pptx_response.usage.output_tokens}")
```

### 下載 PowerPoint 檔

```python
# Download the PowerPoint file
file_ids = extract_file_ids(pptx_response)

if file_ids:
    results = download_all_files(
        client, pptx_response, output_dir=str(OUTPUT_DIR), prefix="q3_review_"
    )

    print_download_summary(results)

    print("\n✅ Open the presentation in PowerPoint or Google Slides to view!")
else:
    print("❌ No files found in response")
```

**⏱️ 注意**：簡單文件的 PDF 產生通常要 **1 到 2 分鐘**。Cell 執行時會顯示 `[*]`，請耐心等待！

### 範例：PDF 文件

#### 簡單範例（1 行）
```python
# Quick PDF generation
prompt = "Create a professional invoice PDF for $500 consulting services"
```

#### 詳細範例：收據
**注意**：刻意保持簡單，確保格式乾淨。

### 範例：簡單的收據

**注意**：刻意保持簡單，確保格式乾淨。

```python
# Create a PDF receipt
pdf_response = client.beta.messages.create(
    model=MODEL,
    max_tokens=4096,
    container={"skills": [{"type": "anthropic", "skill_id": "pdf", "version": "latest"}]},
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[
        {
            "role": "user",
            "content": """Create a simple receipt PDF:

RECEIPT

Acme Corporation
Date: January 15, 2025
Receipt #: RCT-2025-001

Customer: Jane Smith

Items:
- Product A: $50.00
- Product B: $75.00
- Product C: $25.00

Subtotal: $150.00
Tax (8%): $12.00
Total: $162.00

Thank you for your business!

Use simple, clean formatting with clear sections.
""",
        }
    ],
    betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"],
)

print("PDF Response:")
print("=" * 80)
for content in pdf_response.content:
    if content.type == "text":
        print(content.text)

print("\n\n📊 Token Usage:")
print(f"   Input: {pdf_response.usage.input_tokens}")
print(f"   Output: {pdf_response.usage.output_tokens}")
```

### 下載並驗證 PDF

```python
# Download the PDF file
file_ids = extract_file_ids(pdf_response)

if file_ids:
    results = download_all_files(
        client, pdf_response, output_dir=str(OUTPUT_DIR), prefix="receipt_"
    )

    print_download_summary(results)

    # Verify PDF integrity
    for result in results:
        if result["success"]:
            file_path = result["output_path"]
            file_size = result["size"]

            # Basic PDF validation
            with open(file_path, "rb") as f:
                header = f.read(5)
                if header == b"%PDF-":
                    print(f"\n✅ PDF file is valid: {file_path}")
                    print(f"   File size: {file_size / 1024:.1f} KB")
                else:
                    print(f"\n⚠️ File may not be a valid PDF: {file_path}")
else:
    print("❌ No files found in response")
```

## 7. 疑難排解 {#troubleshooting}

### 常見問題與解法

### 問題 1：找不到 API Key

**錯誤：**
```
ValueError: ANTHROPIC_API_KEY not found
```

**解法：**
1. 確認 `.env` 檔存在於上層目錄
2. 檢查有設定 `ANTHROPIC_API_KEY=sk-ant-api03-...`
3. 建立或編輯 `.env` 後重新啟動 Jupyter kernel

### 問題 2：不認得 Container 參數

**錯誤：**
```
TypeError: Messages.create() got an unexpected keyword argument 'container'
```

**解法：**
用 `client.beta.messages.create()` 取代 `client.messages.create()`：
```python
# ✅ Correct - use beta.messages
response = client.beta.messages.create(
    model=MODEL,
    container={"skills": [...]},
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[...],
    betas=["code-execution-2025-08-25", "files-api-2025-04-14", "skills-2025-10-02"]
)

# ❌ Incorrect - regular messages doesn't support container
response = client.messages.create(
    model=MODEL,
    container={"skills": [...]},  # Error!
    messages=[...]
)
```

### 問題 3：Skills Beta 需要 Code Execution Tool

**錯誤：**
```
BadRequestError: Skills beta requires the code_execution tool to be included in the request.
```

**解法：**
使用 Skills 時，一定要包含 code_execution tool：
```python
# ✅ Correct
response = client.beta.messages.create(
    model=MODEL,
    tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
    messages=[...],
    betas=["...", "skills-2025-10-02"]
)

# ❌ Incorrect - missing code_execution tool
response = client.beta.messages.create(
    model=MODEL,
    messages=[...],
    betas=["...", "skills-2025-10-02"]
)
```

### 問題 4：回應裡找不到檔案

**錯誤：**
```
❌ No files found in response
```

**解法：**
1. 確認請求裡有包含 code execution tool
2. 確認 skill 有被載入（檢查回應內容）
3. 確認任務確實需要建立檔案
4. 看回應文字裡有沒有錯誤訊息

### 問題 5：檔案下載失敗

**錯誤：**
```
Error retrieving file: File not found
```

**解法：**
1. 檔案在 Anthropic 伺服器上的保存時間可能有限
2. 建立後馬上下載
3. 確認 file_id 有正確從回應取出
4. 確認 betas 清單裡有 Files API beta

### Token 最佳化技巧

1. Anthropic 的 skill 用 **"latest" 版本**，會自動最佳化
2. **批次操作**：盡可能在一次對話裡建立多個檔案
3. **重用 container**：用先前回應的 `container.id`，避免重新載入 skill
4. **要具體**：指示清楚，反覆修改的次數就少

### API Rate Limiting

遇到 rate limit 時：
- 重試時實作 exponential backoff
- 多個檔案用批次處理
- 考慮升級 API 方案取得更高的上限

## 下一步

🎉 **恭喜！** 你已經學會 Claude Skills 的基礎。

### 看 Skills 的實際應用

看官方公告，了解這些 Skills 怎麼支撐 Claude 的檔案建立能力：
- **[Claude Creates Files](https://www.anthropic.com/news/create-files)**：看 Skills 怎麼讓 Claude 直接建立和編輯 Excel、PowerPoint 和 PDF 檔

### 繼續學習：

- **[Notebook 2: Financial Applications](02_skills_financial_applications.md)**：用財務資料做真實的商業案例
- **[Notebook 3: Custom Skills Development](03_skills_custom_development.md)**：打造你自己的專門 skill

### 支援文章：

- 📚 **[Teach Claude your way of working using Skills](https://support.claude.com/en/articles/12580051-teach-claude-your-way-of-working-using-skills)**：Skills 的使用者指南
- 🛠️ **[How to create a skill with Claude through conversation](https://support.claude.com/en/articles/12599426-how-to-create-a-skill-with-claude-through-conversation)**：互動式建立 skill 的指南

### 資源：

- [Claude API Documentation](https://docs.anthropic.com/en/api/messages)
- [Skills Documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
- [Skills Best Practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices)
- [Files API Documentation](https://docs.claude.com/en/api/files-content)
- [Claude Support](https://support.claude.com)

### 試試這些實驗：

1. 從簡單的一行 prompt 開始，看 Skills 的實際效果
2. 修改預算範例，加入更多分類
3. 用你自己的資料建立簡報
4. 產生結合文字和表格的 PDF 報告
5. 在同一個請求裡一起使用多個 skill

## 重點整理

- Skills 是指令、程式碼和資源的組合包，層級比單一 tool 高，可以疊加使用。
- Progressive disclosure 分三層：先只載入 metadata，相關時才載完整指令，需要時才載連結檔案，所以裝很多 skill 也不會讓 prompt 變肥。
- 用 Skills 一定要走 beta API，並同時帶 `container` 和 code execution tool，少一個都會報錯。
- Skill 在 code execution 環境裡產生檔案，回應只給 `file_id`，要再用 Files API 下載，而且要趁檔案還在時下載。
- Anthropic 內建的 skill 建議用 `"latest"`，production 想要穩定再固定版本。

## 練習

1. 把預算試算表的 prompt 改成加入「儲蓄目標」分類和一個計算達成率的公式，重新產生並用 Excel 打開檢查。
2. 把 PowerPoint 範例從 2 張投影片改成 4 張，加一張圓餅圖，記下產生時間的變化。
3. 在同一個請求的 `container` 裡同時掛 `xlsx` 和 `pdf` 兩個 skill，要求 Claude 先產生資料表再輸出成 PDF 報告，並重用上一次回應的 `container.id`。

