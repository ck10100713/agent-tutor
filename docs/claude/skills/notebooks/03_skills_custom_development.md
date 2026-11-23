---
translated: true
source: skills/notebooks/03_skills_custom_development.ipynb
---

# 為 Claude 打造自訂 Skills

> 原文：[skills/notebooks/03_skills_custom_development.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/skills/notebooks/03_skills_custom_development.ipynb)

建立、部署、管理自訂 skill，把組織專屬的工作流程教給 Claude。

## 這篇在做什麼

帶你從零做出三個自訂 skill（財務比率計算、品牌規範、財務建模），透過 API 上傳、測試，再示範怎麼做版本管理。最後整理 production 的最佳實務。

## 學完你會

- 寫出符合規格的 `SKILL.md`，並搭配 Python script 和多個 .md 檔組成 skill
- 用 API 上傳 skill、在對話中呼叫它，並跟 Anthropic 內建 skill 搭配使用
- 為 skill 建立新版本、列出和清理 workspace 裡的 skills

## 開跑前

- 有 Skills 權限的 Anthropic API key
- Anthropic SDK 2.0.0 以上
- 建議先看過 [Notebook 1: Skills 入門](01_skills_introduction.md)

學會怎麼建立、部署、管理自訂 skill，用你組織專屬的知識和工作流程擴充 Claude 的能力。

## 目錄

1. [簡介與設定](#introduction)
2. [了解自訂 Skills 架構](#architecture)
3. [範例 1：財務比率計算器](#financial-ratio)
4. [範例 2：公司品牌規範](#brand-guidelines)
5. [範例 3：財務建模套件](#financial-modeling)
6. [Skill 管理與版本控制](#management)
7. [最佳實務與 production 技巧](#best-practices)
8. [疑難排解](#troubleshooting)

## 1. 簡介與設定 {#introduction}

### 什麼是自訂 Skills？

**自訂 skill** 是你自己做的專業知識包，用來教 Claude 你組織獨有的工作流程、領域知識和最佳實務。跟 Anthropic 預先做好的 skill（Excel、PowerPoint、PDF）不同，自訂 skill 讓你能：

- **把組織知識寫下來**：記錄團隊專屬的方法
- **確保一致性**：所有互動都套用同樣的標準
- **自動化複雜流程**：把多步驟流程串起來
- **保護智慧財產**：專有方法不外流

### 主要好處

| 好處 | 說明 |
|---------|-------------|
| **規模化的專業知識** | 讓每次 Claude 互動都帶著專業知識 |
| **版本控制** | 追蹤變更，需要時可以回滾 |
| **可組合** | 多個 skill 組合起來處理複雜任務 |
| **隱私** | 你的 skill 只屬於你的組織 |

### 前置條件

開始之前，請確認：
- 已完成 [Notebook 1: Skills 入門](01_skills_introduction.md)
- 有 Skills 權限的 Anthropic API key
- 裝了 Anthropic SDK 2.0.0 以上的 Python 環境

### 環境設定

先設定環境並匯入需要的函式庫：

```python
import os
import sys
from pathlib import Path
from typing import Any

# Add parent directory for imports
sys.path.insert(0, str(Path.cwd().parent))

from anthropic import Anthropic
from anthropic.lib import files_from_dir
from dotenv import load_dotenv

# Import our utilities
from file_utils import (
    download_all_files,
    extract_file_ids,
    print_download_summary,
)

# We'll create skill_utils later in this notebook
# from skill_utils import (
#     create_skill,
#     list_skills,
#     delete_skill,
#     test_skill
# )

# Load environment variables
load_dotenv(Path.cwd().parent / ".env")

API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")

if not API_KEY:
    raise ValueError(
        "ANTHROPIC_API_KEY not found. Copy ../.env.example to ../.env and add your API key."
    )

# Initialize client (the Skills API is GA in SDK 2.x: client.skills needs no beta header)
client = Anthropic(api_key=API_KEY)

# Setup directories
SKILLS_DIR = Path.cwd().parent / "custom_skills"
OUTPUT_DIR = Path.cwd().parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

print("✓ API key loaded")
print(f"✓ Using model: {MODEL}")
print(f"✓ Custom skills directory: {SKILLS_DIR}")
print(f"✓ Output directory: {OUTPUT_DIR}")
print("\n📝 Skills API ready for skill management")
```

## 2. 了解自訂 Skills 架構 {#architecture}

### Skill 結構

每個自訂 skill 都遵循這個目錄結構：

```
skill_name/
├── SKILL.md           # REQUIRED: Instructions with YAML frontmatter
├── *.md               # Optional: Any additional .md files (documentation, guides)
├── scripts/           # Optional: Executable code
│   ├── process.py
│   └── utils.js
└── resources/         # Optional: Templates, data files
    └── template.xlsx
```

**重要：**
- **SKILL.md 是唯一必要的檔案**，其他都是選用
- **可以有多個 .md 檔**：最上層資料夾可以放任意數量的 markdown 檔
- **所有 .md 檔都會載入**：不只 SKILL.md 和 REFERENCE.md，你放進去的任何 .md 都會
- **依需要組織**：複雜文件可以拆成多個 .md 檔

📖 看看我們的工程部落格文章 [Equipping agents for the real world with Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

### Skills 不只是 Markdown

![Skills Can Include Scripts and Files](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/skills/assets/not-just-markdown.png)

Skill 可以打包各種檔案類型：
- **Markdown 檔**：說明和文件（SKILL.md、REFERENCE.md 等）
- **Scripts**：Python、JavaScript 或其他可執行程式碼，處理複雜操作
- **Templates**：可以客製的現成檔案（Excel 範本、文件範本）
- **Resources**：輔助的資料檔、設定檔或資產

### SKILL.md 的要求

`SKILL.md` 檔必須包含：

1. **YAML Frontmatter**（name：64 字元，description：1024 字元）
   - `name`：小寫英數字加連字號（必填）
   - `description`：簡短說明這個 skill 做什麼（必填）

2. **說明內容**（markdown 格式）
   - 給 Claude 的清楚指引
   - 使用範例
   - 任何限制或規則
   - 建議：控制在 5,000 tokens 以內

### 額外的文件檔

你可以放多個 markdown 檔來讓內容更好整理：

```
skill_name/
├── SKILL.md           # Main instructions (required)
├── REFERENCE.md       # API reference (optional)
├── EXAMPLES.md        # Usage examples (optional)
├── TROUBLESHOOTING.md # Common issues (optional)
└── CHANGELOG.md       # Version history (optional)
```

根目錄下所有 `.md` 檔，在 skill 載入時都能被 Claude 用到。

### 打包檔案的範例

![Bundled Files in Skills](https://raw.githubusercontent.com/anthropics/claude-cookbooks/main/skills/assets/skills-bundled-files.png)

這個例子顯示 Skill 能打包多個檔案：
- **SKILL.md**：主要說明，包含顏色、字型和各個段落
- **slide-decks.md**：針對特定用途的額外文件
- **Scripts 和 resources**：skill 執行時可以參照和使用

### Progressive Disclosure（漸進式載入）

Skill 分三個階段載入，節省 token：

| 階段 | 內容 | Token 成本 | 何時載入 |
|-------|---------|------------|-------------|
| **1. Metadata** | 名稱與描述 | name：64 字元，description：1024 字元 | 一直可見 |
| **2. Instructions** | 所有 .md 檔 | 建議 <5,000 tokens | 相關時 |
| **3. Resources** | Scripts 與檔案 | 視需要 | 執行期間 |

### API 流程

```python
# 1. Create skill
skill = client.skills.create(
    display_name="My Skill",
    files=files_from_dir("path/to/skill")
)

# 2. Use in messages
response = client.beta.messages.create(
    container={
        "skills": [{
            "type": "custom",
            "skill_id": skill.id,
            "version": "latest"
        }]
    },
    # ... rest of message parameters
)
```

### 最佳實務

建立 skill 的詳細指引和最佳實務請看：
- [Claude Skills Best Practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices)
- [Skills Documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)

### 建立 Skill 工具函式

先寫幾個管理 skill 的 helper 函式：

```python
def create_skill(client: Anthropic, skill_path: str, display_name: str) -> dict[str, Any]:
    """
    Create a new custom skill from a directory.

    Args:
        client: Anthropic client instance
        skill_path: Path to skill directory
        display_name: Human-readable skill name

    Returns:
        Dictionary with skill_id, version, and metadata
    """
    try:
        # Create skill using files_from_dir
        skill = client.skills.create(display_name=display_name, files=files_from_dir(skill_path))

        return {
            "success": True,
            "skill_id": skill.id,
            "display_name": skill.display_name,
            "latest_version_id": skill.latest_version_id,
            "created_at": skill.created_at,
            "source": skill.source,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_custom_skills(client: Anthropic) -> list[dict[str, Any]]:
    """
    List all custom skills in the workspace.

    Returns:
        List of skill dictionaries
    """
    try:
        skills_response = client.skills.list(source="custom")

        skills = []
        for skill in skills_response.data:
            skills.append(
                {
                    "skill_id": skill.id,
                    "display_name": skill.display_name,
                    "latest_version_id": skill.latest_version_id,
                    "created_at": skill.created_at,
                    "updated_at": skill.updated_at,
                }
            )

        return skills
    except Exception as e:
        print(f"Error listing skills: {e}")
        return []


def delete_skill(client: Anthropic, skill_id: str) -> bool:
    """
    Delete a custom skill and all its versions.

    Args:
        client: Anthropic client
        skill_id: ID of skill to delete

    Returns:
        True if successful, False otherwise
    """
    try:
        # Deleting a skill also deletes all of its versions
        client.skills.delete(skill_id)
        return True

    except Exception as e:
        print(f"Error deleting skill: {e}")
        return False


def test_skill(
    client: Anthropic,
    skill_id: str,
    test_prompt: str,
    model: str = "claude-sonnet-5-5",
) -> Any:
    """
    Test a custom skill with a prompt.

    Args:
        client: Anthropic client
        skill_id: ID of skill to test
        test_prompt: Prompt to test the skill
        model: Model to use for testing

    Returns:
        Response from Claude
    """
    response = client.beta.messages.create(
        model=model,
        max_tokens=4096,
        container={"skills": [{"type": "custom", "skill_id": skill_id, "version": "latest"}]},
        tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
        messages=[{"role": "user", "content": test_prompt}],
        betas=[
            "code-execution-2025-08-25",
            "files-api-2025-04-14",
            "skills-2025-10-02",
        ],
    )

    return response


print("✓ Skill utility functions defined")
print("  - create_skill()")
print("  - list_custom_skills()")
print("  - delete_skill()")
print("  - test_skill()")
```

### 檢查現有的自訂 Skills

看看你的 workspace 裡是否已經有自訂 skill：

### ⚠️ 重要：開始前先清掉現有的 Skills

如果你是重跑這份 notebook，可能留有上次 session 建的 skill。Skill 的顯示標題不能重複，所以有三個選擇：

1. **刪掉現有的 skills**（測試時建議）：從乾淨狀態開始
2. **用不同的顯示標題**：在名稱加時間戳或版本號
3. **用新版本更新現有 skill**：見 [Skill 管理與版本控制](#management) 一節

檢查並視情況清理現有的 skill：

```python
# Check for existing skills that might conflict
existing_skills = list_custom_skills(client)
skill_titles_to_create = [
    "Financial Ratio Analyzer",
    "Corporate Brand Guidelines",
    "Financial Modeling Suite",
]
conflicting_skills = []

if existing_skills:
    print(f"Found {len(existing_skills)} existing custom skill(s):")
    for skill in existing_skills:
        print(f"  - {skill['display_name']} (ID: {skill['skill_id']})")
        if skill["display_name"] in skill_titles_to_create:
            conflicting_skills.append(skill)

    if conflicting_skills:
        print(
            f"\n⚠️ Found {len(conflicting_skills)} skill(s) that will conflict with this notebook:"
        )
        for skill in conflicting_skills:
            print(f"  - {skill['display_name']} (ID: {skill['skill_id']})")

        print("\n" + "=" * 70)
        print("To clean up these skills and start fresh, uncomment and run:")
        print("=" * 70)
        print("\n# UNCOMMENT THE LINES BELOW TO DELETE CONFLICTING SKILLS:")
        print("# for skill in conflicting_skills:")
        print("#     if delete_skill(client, skill['skill_id']):")
        print("#         print(f\"✅ Deleted: {skill['display_name']}\")")
        print("#     else:")
        print("#         print(f\"❌ Failed to delete: {skill['display_name']}\")")

        # for skill in conflicting_skills:
        #     if delete_skill(client, skill['skill_id']):
        #         print(f"✅ Deleted: {skill['display_name']}")
        #     else:
        #         print(f"❌ Failed to delete: {skill['display_name']}")
    else:
        print("\n✅ No conflicting skills found. Ready to proceed!")
else:
    print("✅ No existing custom skills found. Ready to create new ones!")
```

## 3. 範例 1：財務比率計算器 {#financial-ratio}

做第一個自訂 skill：能分析公司財務健康度的財務比率計算器。

### Skill 概覽

**財務比率計算器** skill 會：
- 計算主要財務比率（ROE、P/E、流動比率等）
- 結合產業背景解讀比率
- 產生格式化報告
- 處理多種資料格式（CSV、JSON、文字）

### 上傳財務分析 Skill

現在把財務分析 skill 上傳給 Claude：

```python
# Upload the Financial Analyzer skill
financial_skill_path = SKILLS_DIR / "analyzing-financial-statements"

if financial_skill_path.exists():
    print("Uploading Financial Analyzer skill...")
    result = create_skill(client, str(financial_skill_path), "Financial Ratio Analyzer")

    if result["success"]:
        financial_skill_id = result["skill_id"]
        print("✅ Skill uploaded successfully!")
        print(f"   Skill ID: {financial_skill_id}")
        print(f"   Version: {result['latest_version_id']}")
        print(f"   Created: {result['created_at']}")
    else:
        print(f"❌ Upload failed: {result['error']}")
        if "already exists" in str(result["error"]) or "cannot reuse" in str(result["error"]):
            print("\n💡 Solution: A skill with this name already exists.")
            print("   Run the 'Clean Up Existing Skills' cell above to delete it first,")
            print("   or change the display_name to something unique.")
else:
    print(f"⚠️ Skill directory not found: {financial_skill_path}")
    print(
        "Please ensure the custom_skills directory contains the analyzing-financial-statements folder."
    )
```

### 測試財務分析 Skill

用範例財務資料測試這個 skill：

```python
# Test the Financial Analyzer skill
if "financial_skill_id" in locals():
    test_prompt = """
    Calculate financial ratios for this company:

    Income Statement:
    - Revenue: $1,000M
    - EBITDA: $200M
    - Net Income: $120M

    Balance Sheet:
    - Total Assets: $2,000M
    - Current Assets: $500M
    - Current Liabilities: $300M
    - Total Debt: $400M
    - Shareholders Equity: $1,200M

    Market Data:
    - Share Price: $50
    - Shares Outstanding: 100M

    Please calculate key ratios and provide analysis.
    """

    print("Testing Financial Analyzer skill...")
    response = test_skill(client, financial_skill_id, test_prompt)

    # Print response
    for content in response.content:
        if content.type == "text":
            print(content.text)
else:
    print("⚠️ Please upload the Financial Analyzer skill first (run the previous cell)")
```

## 4. 範例 2：公司品牌規範 {#brand-guidelines}

接著做一個 skill，確保所有文件都遵守公司品牌標準。

### Skill 概覽

**品牌規範** skill 會：
- 套用一致的顏色、字型和版面
- 確保 logo 的擺放和使用
- 維持專業的語氣和訊息
- 適用所有文件類型（Excel、PowerPoint、PDF）

```python
# Upload the Brand Guidelines skill
brand_skill_path = SKILLS_DIR / "applying-brand-guidelines"

if brand_skill_path.exists():
    print("Uploading Brand Guidelines skill...")
    result = create_skill(client, str(brand_skill_path), "Corporate Brand Guidelines")

    if result["success"]:
        brand_skill_id = result["skill_id"]
        print("✅ Skill uploaded successfully!")
        print(f"   Skill ID: {brand_skill_id}")
        print(f"   Version: {result['latest_version_id']}")
    else:
        print(f"❌ Upload failed: {result['error']}")
        if "already exists" in str(result["error"]) or "cannot reuse" in str(result["error"]):
            print("\n💡 Solution: A skill with this name already exists.")
            print("   Run the 'Clean Up Existing Skills' cell above to delete it first,")
            print("   or change the display_name to something unique.")
else:
    print(f"⚠️ Skill directory not found: {brand_skill_path}")
```

### 用建立文件測試品牌規範

用品牌 skill 做一份有品牌風格的 PowerPoint 簡報來測試：

```python
# Test Brand Guidelines skill with PowerPoint creation
if "brand_skill_id" in locals():
    # Combine brand skill with Anthropic's pptx skill
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4096,
        container={
            "skills": [
                {"type": "custom", "skill_id": brand_skill_id, "version": "latest"},
                {"type": "anthropic", "skill_id": "pptx", "version": "latest"},
            ]
        },
        tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
        messages=[
            {
                "role": "user",
                "content": """Create a 3-slide PowerPoint presentation following Acme Corporation brand guidelines:

            Slide 1: Title slide for "Q4 2025 Results"
            Slide 2: Revenue Overview with a chart showing Q1-Q4 growth
            Slide 3: Key Achievements (3 bullet points)

            Apply all brand colors, fonts, and formatting standards.
            """,
            }
        ],
        betas=[
            "code-execution-2025-08-25",
            "files-api-2025-04-14",
            "skills-2025-10-02",
        ],
    )

    print("Response from Claude:")
    for content in response.content:
        if content.type == "text":
            print(content.text[:500] + "..." if len(content.text) > 500 else content.text)

    # Download generated file
    file_ids = extract_file_ids(response)
    if file_ids:
        results = download_all_files(
            client, response, output_dir=str(OUTPUT_DIR), prefix="branded_"
        )
        print_download_summary(results)
else:
    print("⚠️ Please upload the Brand Guidelines skill first")
```

## 5. 範例 3：財務建模套件 {#financial-modeling}

做最進階的 skill：用於估值和風險分析的完整財務建模套件。

### Skill 概覽

**財務建模套件** skill 提供：
- **DCF 估值**：完整的現金流量折現模型
- **敏感度分析**：測試各變數對估值的影響
- **Monte Carlo 模擬**：用機率分布做風險建模
- **情境規劃**：最佳、基準、最差情境分析

這示範了一個多檔案的 skill，包含複雜計算和專業等級的財務建模。

### 上傳財務建模套件

先上傳財務建模 skill：

```python
# Upload the Financial Modeling Suite skill
modeling_skill_path = SKILLS_DIR / "creating-financial-models"

if modeling_skill_path.exists():
    print("Uploading Financial Modeling Suite skill...")
    result = create_skill(client, str(modeling_skill_path), "Financial Modeling Suite")

    if result["success"]:
        modeling_skill_id = result["skill_id"]
        print("✅ Skill uploaded successfully!")
        print(f"   Skill ID: {modeling_skill_id}")
        print(f"   Version: {result['latest_version_id']}")
        print("\nThis skill includes:")
        print("   - DCF valuation model (dcf_model.py)")
        print("   - Sensitivity analysis framework (sensitivity_analysis.py)")
        print("   - Monte Carlo simulation capabilities")
        print("   - Scenario planning tools")
    else:
        print(f"❌ Upload failed: {result['error']}")
else:
    print(f"⚠️ Skill directory not found: {modeling_skill_path}")
    print(
        "Please ensure the custom_skills directory contains the creating-financial-models folder."
    )
```

### 測試財務建模套件

用一個 DCF 估值請求來測試進階建模能力：

```python
# Test the Financial Modeling Suite with a DCF valuation
if "modeling_skill_id" in locals():
    dcf_test_prompt = """
    Perform a DCF valuation for TechCorp with the following data:

    Historical Financials (Last 3 Years):
    - Revenue: $500M, $600M, $750M
    - EBITDA Margin: 25%, 27%, 30%
    - CapEx: $50M, $55M, $60M
    - Working Capital: 15% of revenue

    Projections:
    - Revenue growth: 20% for years 1-3, then declining to 5% by year 5
    - EBITDA margin expanding to 35% by year 5
    - Terminal growth rate: 3%

    Market Assumptions:
    - WACC: 10%
    - Tax rate: 25%
    - Current net debt: $200M
    - Shares outstanding: 100M

    Please create a complete DCF model with sensitivity analysis on WACC and terminal growth.
    Generate an Excel file with the full model including:
    1. Revenue projections
    2. Free cash flow calculations
    3. Terminal value
    4. Enterprise value to equity value bridge
    5. Sensitivity table
    """

    print("Testing Financial Modeling Suite with DCF valuation...")
    print("=" * 70)
    print("\n⏱️ Note: Complex financial model generation may take 1-2 minutes.\n")

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4096,
        container={
            "skills": [
                {"type": "custom", "skill_id": modeling_skill_id, "version": "latest"},
                {"type": "anthropic", "skill_id": "xlsx", "version": "latest"},
            ]
        },
        tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
        messages=[{"role": "user", "content": dcf_test_prompt}],
        betas=[
            "code-execution-2025-08-25",
            "files-api-2025-04-14",
            "skills-2025-10-02",
        ],
    )

    # Print Claude's response
    for content in response.content:
        if content.type == "text":
            # Print first 800 characters to keep output manageable
            text = content.text
            if len(text) > 800:
                print(text[:800] + "\n\n[... Output truncated for brevity ...]")
            else:
                print(text)

    # Download the DCF model if generated
    file_ids = extract_file_ids(response)
    if file_ids:
        print("\n" + "=" * 70)
        print("Downloading generated DCF model...")
        results = download_all_files(
            client, response, output_dir=str(OUTPUT_DIR), prefix="dcf_model_"
        )
        print_download_summary(results)
        print("\n💡 Open the Excel file to explore the complete DCF valuation model!")
else:
    print("⚠️ Please upload the Financial Modeling Suite skill first (run the previous cell)")
```

## 6. Skill 管理與版本控制 {#management}

長期管理 skill 需要了解版本控制、更新和生命週期管理。

### 列出你的 Skills

總覽 workspace 裡所有自訂 skill：

```python
# List all your custom skills
my_skills = list_custom_skills(client)

if my_skills:
    print(f"You have {len(my_skills)} custom skill(s):\n")
    print("=" * 70)
    for i, skill in enumerate(my_skills, 1):
        print(f"\n{i}. {skill['display_name']}")
        print(f"   Skill ID: {skill['skill_id']}")
        print(f"   Current Version: {skill['latest_version_id']}")
        print(f"   Created: {skill['created_at']}")
        if skill.get("updated_at"):
            print(f"   Last Updated: {skill['updated_at']}")
    print("\n" + "=" * 70)
else:
    print("No custom skills found in your workspace.")
```

### 建立新版本

Skill 支援版本控制，可保留歷史並能回滾。我們來強化財務分析 skill，並建立新版本。

#### 步驟 1：強化財務分析 skill

加入**醫療產業**的基準，讓 skill 更通用。這是依使用者需求擴充 skill 能力的真實情境。

```python
# Add healthcare industry benchmarks to the Financial Analyzer
# This demonstrates a realistic skill enhancement scenario

if "financial_skill_id" in locals():
    # Read the current interpret_ratios.py file
    interpret_file_path = SKILLS_DIR / "analyzing-financial-statements" / "interpret_ratios.py"

    with open(interpret_file_path) as f:
        content = f.read()

    # Add healthcare benchmarks after the 'manufacturing' section
    healthcare_benchmarks = """        },
        'healthcare': {
            'current_ratio': {'excellent': 2.3, 'good': 1.8, 'acceptable': 1.4, 'poor': 1.0},
            'debt_to_equity': {'excellent': 0.3, 'good': 0.6, 'acceptable': 1.0, 'poor': 1.8},
            'roe': {'excellent': 0.22, 'good': 0.16, 'acceptable': 0.11, 'poor': 0.07},
            'gross_margin': {'excellent': 0.65, 'good': 0.45, 'acceptable': 0.30, 'poor': 0.20},
            'pe_ratio': {'undervalued': 18, 'fair': 28, 'growth': 40, 'expensive': 55}
        """

    # Find the position after manufacturing section and before the closing brace
    insert_pos = content.find("        }\n    }")  # Find the end of the BENCHMARKS dict

    if insert_pos != -1:
        # Insert the healthcare benchmarks
        new_content = content[:insert_pos] + healthcare_benchmarks + content[insert_pos:]

        # Save the enhanced file
        with open(interpret_file_path, "w") as f:
            f.write(new_content)

        print("✅ Enhanced Financial Analyzer with healthcare industry benchmarks")
        print("\nChanges made:")
        print("  - Added healthcare industry to BENCHMARKS")
        print("  - Includes specific thresholds for:")
        print("    • Current ratio (liquidity)")
        print("    • Debt-to-equity (leverage)")
        print("    • ROE (profitability)")
        print("    • Gross margin")
        print("    • P/E ratio (valuation)")
        print("\n📝 Now we can create a new version of the skill with this enhancement!")
    else:
        print("⚠️ Could not find the correct position to insert healthcare benchmarks")
        print("The file structure may have changed.")
else:
    print("⚠️ Please upload the Financial Analyzer skill first (run cells in Section 3)")
```

#### 步驟 2：建立新版本

強化完成後，建立新版本來記錄這次變更：

```python
# Create a new version of the enhanced Financial Analyzer skill
def create_skill_version(client: Anthropic, skill_id: str, skill_path: str):
    """Create a new version of an existing skill."""
    try:
        version = client.skills.versions.create(skill_id=skill_id, files=files_from_dir(skill_path))
        return {
            "success": True,
            "version_id": version.id,
            "created_at": version.created_at,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# Create the new version with our healthcare enhancement
if "financial_skill_id" in locals():
    print("Creating new version of Financial Analyzer with healthcare benchmarks...")

    result = create_skill_version(
        client, financial_skill_id, str(SKILLS_DIR / "analyzing-financial-statements")
    )

    if result["success"]:
        print("✅ New version created successfully!")
        print(f"   Version ID: {result['version_id']}")
        print(f"   Created: {result['created_at']}")
        print("\n📊 Version History:")
        print("   Initial version: Original skill with tech, retail, financial, manufacturing")
        print(f"   {result['version_id']}: Enhanced with healthcare industry benchmarks")
    else:
        print(f"❌ Version creation failed: {result['error']}")
else:
    print("⚠️ Please run the previous cells to upload the skill and make enhancements first")
```

#### 步驟 3：測試新版本

分析一家醫療公司，驗證強化有效：

```python
# Test the enhanced skill with healthcare industry data
if "financial_skill_id" in locals():
    healthcare_test_prompt = """
    Analyze this healthcare company using the healthcare industry benchmarks:

    Company: MedTech Solutions (Healthcare Industry)

    Income Statement:
    - Revenue: $800M
    - EBITDA: $320M
    - Net Income: $160M

    Balance Sheet:
    - Total Assets: $1,200M
    - Current Assets: $400M
    - Current Liabilities: $200M
    - Total Debt: $300M
    - Shareholders Equity: $700M

    Market Data:
    - Share Price: $75
    - Shares Outstanding: 50M

    Please calculate key ratios and provide healthcare-specific analysis.
    """

    print("Testing enhanced Financial Analyzer with healthcare company...")
    print("=" * 70)

    response = test_skill(client, financial_skill_id, healthcare_test_prompt, MODEL)

    # Print Claude's analysis
    for content in response.content:
        if content.type == "text":
            # Print first 1000 characters to keep output manageable
            text = content.text
            if len(text) > 1000:
                print(text[:1000] + "\n\n[... Output truncated for brevity ...]")
            else:
                print(text)

    print(
        "\n✅ The skill now recognizes 'healthcare' as an industry and applies specific benchmarks!"
    )
else:
    print("⚠️ Please run the previous cells to create the enhanced version first")
```

### 清理：管理你的 Skills

測試完或需要整理 workspace 時，可以選擇性移除 skill。先回顧我們建了什麼，並提供清理選項：

```python
# Comprehensive skill cleanup with detailed reporting
def review_and_cleanup_skills(client, dry_run=True):
    """
    Review all skills and optionally clean up the ones created in this notebook.

    Args:
        client: Anthropic client
        dry_run: If True, only show what would be deleted without actually deleting
    """
    # Get all current skills
    all_skills = list_custom_skills(client)

    # Skills we created in this notebook
    notebook_skill_names = [
        "Financial Ratio Analyzer",
        "Corporate Brand Guidelines",
        "Financial Modeling Suite",
    ]

    # Track skills created by this notebook
    notebook_skills = []
    other_skills = []

    for skill in all_skills:
        if skill["display_name"] in notebook_skill_names:
            notebook_skills.append(skill)
        else:
            other_skills.append(skill)

    print("=" * 70)
    print("SKILL INVENTORY REPORT")
    print("=" * 70)

    print(f"\nTotal custom skills in workspace: {len(all_skills)}")

    if notebook_skills:
        print(f"\n📚 Skills created by this notebook ({len(notebook_skills)}):")
        for skill in notebook_skills:
            print(f"   • {skill['display_name']}")
            print(f"     ID: {skill['skill_id']}")
            print(f"     Version: {skill['latest_version_id']}")
            print(f"     Created: {skill['created_at']}")
    else:
        print("\n✅ No skills from this notebook found")

    if other_skills:
        print(f"\n🔧 Other skills in workspace ({len(other_skills)}):")
        for skill in other_skills:
            print(f"   • {skill['display_name']} ({skill['latest_version_id']})")

    # Cleanup options
    if notebook_skills:
        print("\n" + "=" * 70)
        print("CLEANUP OPTIONS")
        print("=" * 70)

        if dry_run:
            print("\n🔍 DRY RUN MODE - No skills will be deleted")
            print("\nTo delete the notebook skills, uncomment and run:")
            print("-" * 40)
            print("# review_and_cleanup_skills(client, dry_run=False)")
            print("-" * 40)

            print("\nThis would delete:")
            for skill in notebook_skills:
                print(f"   • {skill['display_name']}")
        else:
            print("\n⚠️ DELETION MODE - Skills will be permanently removed")
            print("\nDeleting notebook skills...")

            success_count = 0
            for skill in notebook_skills:
                if delete_skill(client, skill["skill_id"]):
                    print(f"   ✅ Deleted: {skill['display_name']}")
                    success_count += 1
                else:
                    print(f"   ❌ Failed to delete: {skill['display_name']}")

            print(f"\n📊 Cleanup complete: {success_count}/{len(notebook_skills)} skills deleted")

    return {
        "total_skills": len(all_skills),
        "notebook_skills": len(notebook_skills),
        "other_skills": len(other_skills),
        "notebook_skill_ids": [s["skill_id"] for s in notebook_skills],
    }


# Run the review (in dry-run mode by default)
print("Reviewing your custom skills workspace...")
cleanup_summary = review_and_cleanup_skills(client, dry_run=True)

# Store skill IDs for potential cleanup
if cleanup_summary["notebook_skill_ids"]:
    skills_to_cleanup = cleanup_summary["notebook_skill_ids"]
    print(f"\n💡 Tip: {len(skills_to_cleanup)} skill(s) can be cleaned up when you're done testing")

# UNCOMMENT THE LINE BELOW TO ACTUALLY DELETE THE NOTEBOOK SKILLS:
# review_and_cleanup_skills(client, dry_run=False)
```

## 7. 最佳實務與 production 技巧 {#best-practices}

### Skill 設計原則

1. **單一職責**：每個 skill 專注在一個專業領域
2. **文件清楚**：SKILL.md 要完整但精簡
3. **錯誤處理**：script 要能妥善處理邊界情況
4. **版本控制**：用 Git 追蹤 skill 的變更
5. **測試**：上 production 前一定要測試 skill

### 目錄結構最佳實務

```
custom_skills/
├── financial_analyzer/       # Single purpose, clear naming
│   ├── SKILL.md             # Under 5,000 tokens
│   ├── scripts/             # Modular Python/JS files
│   └── tests/               # Unit tests for scripts
├── brand_guidelines/         # Organizational standards
│   ├── SKILL.md
│   ├── REFERENCE.md         # Additional documentation
│   └── assets/              # Logos, templates
```

### 效能最佳化

| 策略 | 影響 | 做法 |
|----------|--------|----------------|
| **精簡 Frontmatter** | skill 探索更快 | name：64 字元，description：1024 字元 |
| **Lazy Loading** | 減少 token 用量 | 只在需要時才參照檔案 |
| **Skill 組合** | 避免重複 | 組合多個 skill，而不是做一個巨型 skill |
| **Caching** | 回應更快 | 重用 skill container |

### 安全考量

- **API Keys**：絕對不要把憑證寫死在 skill 裡
- **資料隱私**：skill 檔案裡不要放敏感資料
- **存取控制**：skill 屬於特定 workspace
- **驗證**：script 裡要清理輸入
- **稽核軌跡**：記錄 skill 的使用情況以利合規

## 下一步

🎉 **恭喜！** 你學會了怎麼為 Claude 建立、部署和管理自訂 skill。

### 你學到了

- ✅ 自訂 skill 的架構和要求
- ✅ 用 SKILL.md 和 Python script 建立 skill
- ✅ 透過 API 上傳 skill
- ✅ 組合自訂和 Anthropic 的 skill
- ✅ production 部署的最佳實務
- ✅ 常見問題的排解

### 繼續往下走

1. **實驗**：改寫範例 skill 套到你的情境
2. **建置**：為你組織的工作流程做 skill
3. **最佳化**：監控 token 用量和效能
4. **分享**：把你的 skill 文件化，方便團隊協作

### 資源

- [Claude API Documentation](https://docs.anthropic.com/en/api/messages)
- [Skills Documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
- [Best Practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices)
- [Files API Documentation](https://docs.claude.com/en/api/files-content)
- Example Skills Repository (coming soon)

### 可以試試的 Skill 點子

- 📊 **資料管線**：帶驗證的 ETL 流程
- 📝 **文件範本**：合約、提案、報告
- 🔍 **Code Review**：風格指南和最佳實務
- 📈 **分析儀表板**：KPI 追蹤和視覺化
- 🤖 **自動化套件**：重複性任務的工作流程

祝你 skill 做得開心！🚀

## 重點整理

- Skill 只有 `SKILL.md` 是必要的，frontmatter 的 name 和 description 一直可見，其餘內容按需載入
- Progressive disclosure 分三階段（metadata、instructions、resources），目的是省 token
- Skill 不只有 markdown，也能打包 script、template 和資料檔
- 改 skill 用新版本而不是覆蓋，這樣可追蹤歷史也能回滾
- 設計原則是單一職責，多個小 skill 組合比一個巨型 skill 好

## 練習

1. 把財務分析 skill 的 `description` 改短一點，再看 Claude 是否仍會在對的情境觸發它。
2. 仿照醫療產業那步，替財務分析 skill 加上另一個產業的基準，建立新版本並測試。
3. 自己寫一個只有 `SKILL.md` 加一支 Python script 的小 skill（例如單位換算），上傳並用 API 呼叫它。
