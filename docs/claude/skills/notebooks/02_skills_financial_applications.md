---
translated: true
source: skills/notebooks/02_skills_financial_applications.ipynb
---
# Claude Skills 在財務上的應用

> 原文：[skills/notebooks/02_skills_financial_applications.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/skills/notebooks/02_skills_financial_applications.ipynb)

用 Claude 的 Excel、PowerPoint、PDF Skills 建立財務儀表板和投資組合分析。

## 這篇在做什麼

這篇用 Claude 的 Excel、PowerPoint、PDF Skills，從財務資料產出三種東西：財務儀表板、投資組合分析、自動化的多格式報表流程。每個 Skill 都是請 Claude 在 code execution 容器裡直接產檔，再把檔案下載下來。

## 學完你會

- 讓 Claude 產出帶公式和圖表的 Excel 財務模型
- 用同一份財務資料生成給主管看的 PowerPoint 簡報
- 把 Excel、PPT、PDF 串成一條 pipeline，一次產出整套報表

## 開跑前

- 需要 Anthropic API key，而且要先看過 Notebook 1（Skills 介紹）
- 需要 Anthropic SDK 2.0.0 以上。在 Colab 上直接在 cell 裡 `pip install` 並用 Colab Secrets 放 API key 即可，不用建 virtual environment

> **💡 實際影響：** 這些 Skills 就是 **[Claude Creates Files](https://www.anthropic.com/news/create-files)** 背後在用的，Claude 能直接在介面裡做出專業的財務文件。

**你會學到：**
- 在 Excel 裡建立有公式和圖表的完整財務模型
- 從財務資料產生給主管看的簡報
- 建立帶風險指標的投資組合分析工具
- 自動化多格式報表流程

## 目錄

1. [設定與載入資料](#setup)
2. [情境 1：建立財務儀表板](#financial-dashboard)
   - [Excel 財務模型](#excel-model)
   - [主管簡報 PowerPoint](#executive-ppt)
   - [PDF 財務報告](#pdf-report)
3. [情境 2：投資組合分析流程](#portfolio-analysis)
   - [投資組合分析 Excel](#portfolio-excel)
   - [投資委員會簡報](#investment-deck)
4. [情境 3：自動化報表 pipeline](#reporting-pipeline)

## 前置條件

這個 notebook 假設你已經做完 **Notebook 1：Skills 介紹**。

還沒做的話：
1. 先完成 Notebook 1 的設定
2. 跑測試 cell 確認環境沒問題
3. 確認你能建立並下載檔案

**必要條件：**
- 已設定 Anthropic API key
- Anthropic SDK 2.0.0 以上（`pip install -r requirements.txt`）
- 已啟用 virtual environment

## 1. 設定與載入資料 {#setup}

先 import 需要的套件，載入整個 notebook 會用到的財務資料。

```python
# Standard imports
import json
import os
import sys
from pathlib import Path

import pandas as pd

# Add parent directory for imports
sys.path.insert(0, str(Path.cwd().parent))

# Anthropic SDK
from anthropic import Anthropic
from dotenv import load_dotenv

# Our utilities
from file_utils import (
    download_all_files,
    print_download_summary,
)

# Load environment
load_dotenv(Path.cwd().parent / ".env")

# Configuration
API_KEY = os.getenv("ANTHROPIC_API_KEY")
MODEL = "claude-sonnet-5-5"

if not API_KEY:
    raise ValueError("ANTHROPIC_API_KEY not found. Please configure your .env file.")

# Initialize client
client = Anthropic(api_key=API_KEY)

# Setup directories
OUTPUT_DIR = Path.cwd().parent / "outputs" / "financial"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR = Path.cwd().parent / "sample_data"

print("✓ Environment configured")
print(f"✓ Output directory: {OUTPUT_DIR}")
print(f"✓ Data directory: {DATA_DIR}")
```

### 載入財務資料

我們有四份資料集，各代表公司財務狀況的一個面向：

```python
# Load financial statements
financial_statements = pd.read_csv(DATA_DIR / "financial_statements.csv")
print("📊 Financial Statements Overview:")
print(f"   Shape: {financial_statements.shape}")
print(f"   Categories: {len(financial_statements['Category'].unique())} financial metrics")
print(f"   Quarters: {list(financial_statements.columns[1:5])}")
print()

# Show sample data
print("Sample data (first 5 rows):")
financial_statements.head()
```

```python
# Load portfolio holdings
with open(DATA_DIR / "portfolio_holdings.json") as f:
    portfolio_data = json.load(f)

print("💼 Portfolio Overview:")
print(f"   Portfolio: {portfolio_data['portfolio_name']}")
print(f"   Total Value: ${portfolio_data['total_value']:,.2f}")
print(f"   Holdings: {len(portfolio_data['holdings'])} stocks")
print(f"   Cash Position: ${portfolio_data['cash_position']['amount']:,.2f}")
print(f"   Total Return: {portfolio_data['performance_metrics']['total_return_percent']:.1f}%")
print()

# Convert holdings to DataFrame for easier manipulation
portfolio_df = pd.DataFrame(portfolio_data["holdings"])
print("Top 5 holdings by value:")
portfolio_df.nlargest(5, "market_value")[["ticker", "name", "market_value", "unrealized_gain"]]
```

```python
# Load quarterly metrics
with open(DATA_DIR / "quarterly_metrics.json") as f:
    quarterly_metrics = json.load(f)

print("📈 Quarterly Metrics Overview:")
print(f"   Quarters available: {len(quarterly_metrics['quarters'])}")
print(f"   Metrics per quarter: {len(quarterly_metrics['quarters'][0])} KPIs")
print()

# Show latest quarter metrics
latest_quarter = quarterly_metrics["quarters"][-1]
print(f"Latest Quarter ({latest_quarter['quarter']}):")
for key, value in latest_quarter.items():
    if key != "quarter" and isinstance(value, int | float):
        if "revenue" in key.lower() or "cost" in key.lower():
            print(f"   {key.replace('_', ' ').title()}: ${value:,.0f}")
        elif "percent" in key.lower() or "margin" in key.lower() or "rate" in key.lower():
            print(f"   {key.replace('_', ' ').title()}: {value:.1f}%")
        else:
            print(f"   {key.replace('_', ' ').title()}: {value:,.0f}")
```

### Helper 函式

先定義幾個這個 notebook 會用到的 helper：

```python
def create_skills_message(client, prompt, skills, prefix="", show_token_usage=True):
    """
    Helper function to create messages with Skills.

    Args:
        client: Anthropic client
        prompt: User prompt
        skills: List of skill dicts [{"type": "anthropic", "skill_id": "xlsx", "version": "latest"}]
        prefix: Prefix for downloaded files
        show_token_usage: Whether to print token usage

    Returns:
        Tuple of (response, download_results)
    """
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=4096,
        container={"skills": skills},
        tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
        messages=[{"role": "user", "content": prompt}],
        betas=[
            "code-execution-2025-08-25",
            "files-api-2025-04-14",
            "skills-2025-10-02",
        ],
    )

    if show_token_usage:
        print(
            f"\n📊 Token Usage: {response.usage.input_tokens} in, {response.usage.output_tokens} out"
        )

    # Download files
    results = download_all_files(client, response, output_dir=str(OUTPUT_DIR), prefix=prefix)

    return response, results


def format_financial_value(value, is_currency=True, decimals=0):
    """Format financial values for display."""
    if is_currency:
        return f"${value:,.{decimals}f}"
    else:
        return f"{value:,.{decimals}f}"


print("✓ Helper functions defined")
```

## 2. 情境 1：建立財務儀表板 {#financial-dashboard}

資料和 helper 都準備好了，進入第一個實際情境：建立完整的財務儀表板。先從多 sheet 的 Excel 活頁簿開始，Claude 會自動放進公式、格式和圖表。

### 2.1 Excel 財務模型 {#excel-model}

我們要做的財務儀表板包含：
- 有年增率比較的損益表（P&L）
- 資產負債表分析
- 現金流追蹤
- 帶視覺化的 KPI 儀表板

這展示了 Claude Skills 能處理複雜的 Excel 產生任務，這種事人工做通常要花好幾個小時。

```python
# Create Financial Dashboard Excel
print("Creating financial dashboard Excel file...")
print("This creates a 2-sheet dashboard optimized for the Skills API.")
print("\n⏱️ Generation time: 1-2 minutes\n")

# Prepare the financial data
fs_data = financial_statements.to_dict("records")
quarters_2024 = ["Q1_2024", "Q2_2024", "Q3_2024", "Q4_2024"]

# Extract key financial metrics
revenue_by_quarter = {
    "Q1 2024": financial_statements[financial_statements["Category"] == "Revenue"][
        "Q1_2024"
    ].values[0],
    "Q2 2024": financial_statements[financial_statements["Category"] == "Revenue"][
        "Q2_2024"
    ].values[0],
    "Q3 2024": financial_statements[financial_statements["Category"] == "Revenue"][
        "Q3_2024"
    ].values[0],
    "Q4 2024": financial_statements[financial_statements["Category"] == "Revenue"][
        "Q4_2024"
    ].values[0],
}

financial_dashboard_prompt = f"""
Create a financial dashboard Excel workbook with 2 sheets:

Sheet 1 - "P&L Summary":
Create a Profit & Loss summary table for 2024 quarters with these rows:
- Revenue: {", ".join([f"Q{i + 1}: ${v / 1000000:.1f}M" for i, v in enumerate(revenue_by_quarter.values())])}
- Gross Profit: Use values from the data
- Operating Income: Use values from the data
- Net Income: Use values from the data
- Add a Total column with SUM formulas
- Add a row showing profit margins (Net Income / Revenue)
- Apply currency formatting and bold headers
- Add a simple bar chart showing quarterly revenue

Sheet 2 - "Key Metrics":
Create a metrics dashboard with:
- Total Revenue 2024: SUM of all quarters
- Average Quarterly Revenue: AVERAGE formula
- Q4 vs Q1 Growth: Percentage increase
- Best Quarter: MAX formula to identify
- Operating Margin Q4: Calculate from data
- Year-over-year growth vs 2023

Apply professional formatting with borders, bold headers, and currency formats.
"""

# Create the Excel financial dashboard
excel_response, excel_results = create_skills_message(
    client,
    financial_dashboard_prompt,
    [{"type": "anthropic", "skill_id": "xlsx", "version": "latest"}],
    prefix="financial_dashboard_",
)

print("\n" + "=" * 60)
print_download_summary(excel_results)

if len(excel_results) > 0 and excel_results[0]["success"]:
    print("\n✅ Financial dashboard Excel created successfully!")
```

### 💡 產生 Excel 的最佳實務

根據我們的測試，用 Skills 產生 Excel 檔最好這樣做：

**建議做法：**
- **每個活頁簿 2-3 個 sheet** 最穩，產生速度也快
- **每個 sheet 專注一個用途**（例如 P&L、指標、圖表）
- **逐步加複雜度**，先從簡單的開始再強化

**複雜的儀表板：**
1. **拆成多個專注的檔案**，不要塞進一個複雜檔案
   - 例如：`financial_pnl.xlsx`、`balance_sheet.xlsx`、`kpi_dashboard.xlsx`
2. **用 pipeline 模式**，依序建立並強化檔案
3. **需要的話用 pandas 或 openpyxl 在程式裡合併檔案**

**效能提示：**
- 簡單的 2 sheet 儀表板：約 1-2 分鐘
- PowerPoint 和 PDF 產生：內容再複雜都很穩
- Token 用量：結構化資料（JSON/CSV）比文字描述省

### 2.2 主管簡報 PowerPoint {#executive-ppt}

財務資料已經整理進 Excel，接著做一份給主管看的簡報來總結重點。這示範 Skills 如何產生專業的 PowerPoint，有圖表、排版好的文字和多張投影片，很適合董事會或投資人更新。

簡報內容包含：
- 2024 Q4 表現重點
- 帶年增率比較的財務指標
- 獲利趨勢視覺化
- 重點結論與展望

```python
print("Creating executive presentation from financial metrics...")
print("\n⏱️ Generation time: 1-2 minutes\n")

# Calculate some key metrics for the presentation
q4_2024_revenue = 14500000
q4_2023_revenue = 12300000
yoy_growth = (q4_2024_revenue - q4_2023_revenue) / q4_2023_revenue * 100

q4_2024_net_income = 1878750
q4_2023_net_income = 1209000
net_income_growth = (q4_2024_net_income - q4_2023_net_income) / q4_2023_net_income * 100

executive_ppt_prompt = f"""
Create a 4-slide executive presentation for Q4 2024 financial results:

Slide 1 - Title:
- Title: "Q4 2024 Financial Results"
- Subtitle: "Executive Summary - Acme Corporation"
- Date: January 2025

Slide 2 - Financial Highlights:
- Title: "Q4 2024 Performance Highlights"
- Create a two-column layout:
  Left side - Key Metrics:
  • Revenue: $14.5M (+{yoy_growth:.1f}% YoY)
  • Net Income: $1.88M (+{net_income_growth:.1f}% YoY)
  • Operating Margin: 17.9% (up 2.9pp)
  • Operating Cash Flow: $2.85M

  Right side - Column chart showing quarterly revenue:
  Q1 2024: $12.5M
  Q2 2024: $13.2M
  Q3 2024: $13.8M
  Q4 2024: $14.5M

Slide 3 - Profitability Trends:
- Title: "Margin Expansion & Profitability"
- Add a line chart showing net margin % by quarter:
  Q1 2024: 11.4%
  Q2 2024: 11.8%
  Q3 2024: 12.4%
  Q4 2024: 13.0%
- Add bullet points below:
  • Consistent margin expansion throughout 2024
  • Operating leverage driving profitability
  • Cost optimization initiatives delivering results

Slide 4 - Key Takeaways:
- Title: "Key Takeaways & Outlook"
- Bullet points:
  ✓ Record Q4 revenue of $14.5M
  ✓ 17.9% YoY revenue growth
  ✓ 55% increase in net income YoY
  ✓ Strong cash generation: $2.85M operating cash flow
  ✓ Well-positioned for continued growth in 2025

Use professional corporate design:
- Dark blue (#003366) for headers
- Clean, modern layout
- Data-driven visualizations
"""

# Create the executive presentation
ppt_response, ppt_results = create_skills_message(
    client,
    executive_ppt_prompt,
    [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}],
    prefix="executive_summary_",
)

print("\n" + "=" * 60)
print_download_summary(ppt_results)

if len(ppt_results) > 0 and ppt_results[0]["success"]:
    print("\n✅ Executive presentation created successfully!")
```

## 3. 情境 2：投資組合分析流程 {#portfolio-analysis}

接下來從公司財報轉到投資組合分析。這一節用前面載入的投資組合資料，做出完整的組合分析和投資委員會簡報。

這個流程會展示：
- 在 Excel 裡做詳細的投資組合績效分析
- 風險指標和產業配置視覺化
- 專業的投資委員會簡報
- 以資料為依據的再平衡建議

先建一份有投資組合分析的 Excel 活頁簿，再產生總結結果的投資委員會簡報。

### 先建立完整的投資組合分析 Excel 活頁簿

做投資委員會簡報之前，要先詳細分析投資組合資料。這份 Excel 就是投資建議的基礎。

```python
print("Creating portfolio analysis Excel workbook...")
print("This creates a focused 2-sheet portfolio analysis optimized for the Skills API.")
print("\n⏱️ Generation time: 1-2 minutes\n")

# Prepare portfolio data for the prompt
top_holdings = portfolio_df.nlargest(5, "market_value")
sector_allocation = portfolio_data["sector_allocation"]

portfolio_excel_prompt = f"""
Create a portfolio analysis Excel workbook with 2 sheets:

Sheet 1 - "Portfolio Overview":
Create a comprehensive holdings and performance table:

Section 1 - Holdings (top of sheet):
{portfolio_df[["ticker", "name", "shares", "current_price", "market_value", "unrealized_gain", "allocation_percent"]].head(10).to_string()}

Section 2 - Portfolio Summary:
- Total portfolio value: ${portfolio_data["total_value"]:,.2f}
- Total unrealized gain: ${portfolio_df["unrealized_gain"].sum():,.2f}
- Total Return: {portfolio_data["performance_metrics"]["total_return_percent"]:.1f}%
- YTD Return: {portfolio_data["performance_metrics"]["year_to_date_return"]:.1f}%
- Sharpe Ratio: {portfolio_data["performance_metrics"]["sharpe_ratio"]:.2f}
- Portfolio Beta: {portfolio_data["performance_metrics"]["beta"]:.2f}

Apply conditional formatting: green for gains, red for losses.
Add a bar chart showing top 5 holdings by value.

Sheet 2 - "Sector Analysis & Risk":
Create sector allocation and risk metrics:

Section 1 - Sector Allocation:
{json.dumps(sector_allocation, indent=2)}
Include a pie chart of sector allocation.

Section 2 - Key Risk Metrics:
- Portfolio Beta: {portfolio_data["performance_metrics"]["beta"]:.2f}
- Standard Deviation: {portfolio_data["performance_metrics"]["standard_deviation"]:.1f}%
- Value at Risk (95%): $62,500
- Maximum Drawdown: -12.3%
- Sharpe Ratio: {portfolio_data["performance_metrics"]["sharpe_ratio"]:.2f}

Section 3 - Rebalancing Recommendations:
- Reduce Technology from 20% to 18%
- Increase Healthcare from 8.7% to 10%
- Maintain current diversification

Apply professional formatting with clear sections and headers.
"""

# Create portfolio analysis Excel
portfolio_response, portfolio_results = create_skills_message(
    client,
    portfolio_excel_prompt,
    [{"type": "anthropic", "skill_id": "xlsx", "version": "latest"}],
    prefix="portfolio_analysis_",
)

print("\n" + "=" * 60)
print_download_summary(portfolio_results)

if len(portfolio_results) > 0 and portfolio_results[0]["success"]:
    print("\n✅ Portfolio analysis Excel created successfully!")
```

### 3.2 投資委員會簡報 {#investment-deck}

詳細分析做完了，現在為投資委員會做一份專業簡報。它會把 Excel 分析的重點濃縮成精簡、視覺化的形式，方便決策者看。

簡報涵蓋：
- 含關鍵指標的投資組合績效摘要
- 資產配置和分散程度分析
- 風險指標與風險調整後報酬
- 再平衡的策略建議

```python
print("Creating investment committee presentation...")
print("\n⏱️ Generation time: 1-2 minutes\n")

investment_deck_prompt = f"""
Create a 5-slide investment committee presentation:

Slide 1 - Title:
- Title: "Portfolio Review - Q4 2024"
- Subtitle: "{portfolio_data["portfolio_name"]}"
- Date: January 2025
- Portfolio Value: ${portfolio_data["total_value"]:,.0f}

Slide 2 - Portfolio Overview:
- Title: "Portfolio Performance Summary"
- Two-column layout:

  Left - Key Metrics:
  • Total Value: ${portfolio_data["total_value"]:,.0f}
  • YTD Return: +{portfolio_data["performance_metrics"]["year_to_date_return"]:.1f}%
  • Total Return: ${portfolio_data["performance_metrics"]["total_return"]:,.0f}
  • Sharpe Ratio: {portfolio_data["performance_metrics"]["sharpe_ratio"]:.2f}

  Right - Bar chart of top 5 holdings by value:
  {", ".join([f"{h['ticker']}: ${h['market_value']:,.0f}" for h in top_holdings.to_dict("records")])}

Slide 3 - Sector Allocation:
- Title: "Asset Allocation & Diversification"
- Pie chart showing:
  Technology: {sector_allocation["Technology"]:.1f}%
  Financials: {sector_allocation["Financials"]:.1f}%
  Healthcare: {sector_allocation["Healthcare"]:.1f}%
  Consumer: {sector_allocation["Consumer Discretionary"] + sector_allocation["Consumer Staples"]:.1f}%
  Fixed Income: {sector_allocation["Bonds"]:.1f}%
  Cash: {sector_allocation["Cash"]:.1f}%

Slide 4 - Risk Analysis:
- Title: "Risk Metrics & Analysis"
- Content:
  Risk Indicators:
  • Portfolio Beta: {portfolio_data["performance_metrics"]["beta"]:.2f} (lower market risk)
  • Standard Deviation: {portfolio_data["performance_metrics"]["standard_deviation"]:.1f}%
  • Maximum Drawdown: -12.3%
  • Value at Risk (95%): $62,500

  Risk-Adjusted Performance:
  • Sharpe Ratio: {portfolio_data["performance_metrics"]["sharpe_ratio"]:.2f} (excellent)
  • Alpha Generation: +2.3% vs benchmark

Slide 5 - Recommendations:
- Title: "Strategic Recommendations"
- Bullet points:
  ✓ Maintain current allocation - well diversified
  ✓ Consider profit-taking in Technology (20% → 18%)
  ✓ Increase Healthcare allocation (8.7% → 10%)
  ✓ Monitor bond duration given rate environment
  ✓ Rebalance quarterly to maintain targets

Use professional investment presentation design.
"""

# Create investment committee deck
investment_response, investment_results = create_skills_message(
    client,
    investment_deck_prompt,
    [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}],
    prefix="investment_committee_",
)

print("\n" + "=" * 60)
print_download_summary(investment_results)
print("\n✅ Investment committee presentation created successfully!")
```

## 4. 情境 3：自動化報表 pipeline {#reporting-pipeline}

到目前為止，我們都是為特定用途各自產生文件。現在來看把多個 Skills 串起來的自動化流程。在 production 系統裡，需要從同一份資料來源產出多份相關文件，這種 pipeline 模式很重要。

這個範例會做出一整套報表：
1. **在 Excel 裡分析資料**，有計算和圖表
2. **在 PowerPoint 簡報裡總結洞察**
3. **在正式的 PDF 報告裡記錄過程**

這說明 Skills 可以一起運作，做出完整的報表方案，傳統上這需要多個工具加人工協調。

**Pipeline 做法的好處：**
- 所有文件的資料一致
- 總產生時間縮短
- Token 用量最佳化
- 能擴充到多種報表

**⏱️ 預期總時間：** 整條 pipeline 約 2-3 分鐘

```python
print("🔄 Starting Automated Reporting Pipeline")
print("=" * 60)
print("This will create a complete reporting suite:")
print("1. Excel analysis → 2. PowerPoint summary → 3. PDF documentation")
print("\n⏱️ Total pipeline time: 2-3 minutes\n")

# Track token usage across the pipeline
pipeline_tokens = {"input": 0, "output": 0}

# Step 1: Create Excel Analysis
print("Step 1/3: Creating Excel analysis with quarterly metrics...")

excel_pipeline_prompt = f"""
Create a quarterly business metrics Excel file:

Sheet 1 - "Quarterly KPIs":
Create a table with these quarterly metrics for 2024:
{
    json.dumps(
        [
            {
                k: v
                for k, v in q.items()
                if k in ["quarter", "revenue", "gross_margin", "customer_count", "churn_rate"]
            }
            for q in quarterly_metrics["quarters"]
        ],
        indent=2,
    )
}

Add:
- Quarter-over-quarter growth calculations
- Average and total rows
- Conditional formatting for trends
- Line chart showing revenue trend
- Column chart showing customer count

Sheet 2 - "YoY Comparison":
Compare Q4 2024 vs Q4 2023 for all metrics.
Calculate percentage changes and highlight improvements.

Professional formatting with headers and borders.
"""

excel_response, excel_results = create_skills_message(
    client,
    excel_pipeline_prompt,
    [{"type": "anthropic", "skill_id": "xlsx", "version": "latest"}],
    prefix="pipeline_1_metrics_",
    show_token_usage=False,
)

pipeline_tokens["input"] += excel_response.usage.input_tokens
pipeline_tokens["output"] += excel_response.usage.output_tokens
print(
    f"✓ Excel created - Tokens: {excel_response.usage.input_tokens} in, {excel_response.usage.output_tokens} out"
)

# Step 2: Create PowerPoint Summary
print("\nStep 2/3: Creating PowerPoint summary from metrics...")

ppt_pipeline_prompt = """
Create a 3-slide quarterly metrics summary presentation:

Slide 1:
- Title: "Q4 2024 Metrics Summary"
- Subtitle: "Automated Reporting Pipeline Demo"

Slide 2:
- Title: "Key Performance Indicators"
- Show Q4 2024 metrics:
  • Revenue: $3.2M (+15% QoQ)
  • Customers: 850 (+8.9% QoQ)
  • Gross Margin: 72%
  • Churn Rate: 2.8% (improved from 3.5%)
- Add a simple bar chart comparing Q3 vs Q4 revenue

Slide 3:
- Title: "Quarterly Trend Analysis"
- Line chart showing revenue growth Q1-Q4
- Key insight bullets:
  • Consistent QoQ growth
  • Customer acquisition accelerating
  • Churn reduction successful

Clean, data-focused design.
"""

ppt_response, ppt_results = create_skills_message(
    client,
    ppt_pipeline_prompt,
    [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}],
    prefix="pipeline_2_summary_",
    show_token_usage=False,
)

pipeline_tokens["input"] += ppt_response.usage.input_tokens
pipeline_tokens["output"] += ppt_response.usage.output_tokens
print(
    f"✓ PowerPoint created - Tokens: {ppt_response.usage.input_tokens} in, {ppt_response.usage.output_tokens} out"
)

# Step 3: Create PDF Documentation
print("\nStep 3/3: Creating PDF documentation...")

pdf_pipeline_prompt = """
Create a PDF document summarizing the quarterly reporting pipeline:

AUTOMATED REPORTING PIPELINE
Q4 2024 Results Documentation

EXECUTIVE SUMMARY
This document summarizes the Q4 2024 business metrics generated through
our automated reporting pipeline.

KEY METRICS
- Revenue: $3.2M (15% QoQ growth)
- Customer Base: 850 active customers
- Gross Margin: 72%
- Churn Rate: 2.8% (improved from 3.5%)

PIPELINE COMPONENTS
1. Data Processing: Quarterly metrics analyzed in Excel
2. Visualization: Key insights presented in PowerPoint
3. Documentation: Formal report generated in PDF

AUTOMATION BENEFITS
• Reduced reporting time by 90%
• Consistent format and quality
• Eliminated manual errors
• Scalable to multiple reports

NEXT STEPS
- Expand pipeline to include predictive analytics
- Add automated email distribution
- Implement real-time data feeds

Generated: January 2025
Pipeline Version: 1.0

Format as a professional technical document.
"""

pdf_response, pdf_results = create_skills_message(
    client,
    pdf_pipeline_prompt,
    [{"type": "anthropic", "skill_id": "pdf", "version": "latest"}],
    prefix="pipeline_3_documentation_",
    show_token_usage=False,
)

pipeline_tokens["input"] += pdf_response.usage.input_tokens
pipeline_tokens["output"] += pdf_response.usage.output_tokens
print(
    f"✓ PDF created - Tokens: {pdf_response.usage.input_tokens} in, {pdf_response.usage.output_tokens} out"
)

# Pipeline Summary
print("\n" + "=" * 60)
print("🎯 PIPELINE COMPLETE!")
print("=" * 60)

print("\n📊 Pipeline Token Usage Summary:")
print(f"   Total Input Tokens: {pipeline_tokens['input']:,}")
print(f"   Total Output Tokens: {pipeline_tokens['output']:,}")
print(f"   Total Tokens: {pipeline_tokens['input'] + pipeline_tokens['output']:,}")
print(f"   Average per document: {(pipeline_tokens['input'] + pipeline_tokens['output']) // 3:,}")

print("\n📁 Generated Files:")
all_results = excel_results + ppt_results + pdf_results
for i, result in enumerate(all_results, 1):
    if result["success"]:
        print(f"   {i}. {os.path.basename(result['output_path'])} ({result['size'] / 1024:.1f} KB)")

print("\n✅ Automated reporting pipeline executed successfully!")
print("   All three documents created and linked in workflow.")
```

## 總結與下一步

### 我們完成了什麼

這個 notebook 裡你學到：

✅ **建立財務儀表板**
- 建出多 sheet、有公式和圖表的 Excel 模型
- 產生主管簡報 PowerPoint
- 製作專業 PDF 報告

✅ **投資組合分析**
- 開發投資組合分析活頁簿
- 製作投資委員會簡報
- 實作風險指標和再平衡工具

✅ **自動化 pipeline**
- 串接多種文件格式
- 最佳化 token 用量
- 建立可上線的模式

### 重點

1. **Skills 大幅簡化財務文件製作**：人工要幾小時的事，幾分鐘就好
2. **Token 效率很高**：Skills 用的 token 比手動寫指令少約 90%
3. **品質是專業等級**：文件在商業場合可以直接用
4. **自動化很直接**：pipeline 模式讓複雜流程做得起來

### 繼續學習

📚 **下一篇：[Notebook 3 - 自訂 Skills 開發](03_skills_custom_development.md)**
- 做你自己的專屬財務 Skills
- 建立公司專用的模板
- 實作進階自動化

### 試試這些實驗

1. **修改財務儀表板**，加入你自己的指標
2. **建立自訂的投資組合**，用不同的資產類別
3. **為你自己的報表需求建一條 pipeline**
4. **試不同的複雜度**，感受產生時間的差異
5. **追蹤不同文件類型的 token 用量**

### 資源

- [Claude API Documentation](https://docs.anthropic.com/en/api/messages)
- [Skills Documentation](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
- [Best Practices](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/best-practices)
- [Files API Reference](https://docs.claude.com/en/api/files-content)

## 重點整理

- Skills 讓 Claude 直接產出 Excel、PowerPoint、PDF，你只要描述需求，不用自己寫產檔程式
- Excel 每個活頁簿控制在 2-3 個 sheet 最穩，複雜需求拆成多個檔案
- 輸入資料用 JSON/CSV 這類結構化格式，比文字描述省 token
- 把多個 Skill 串成 pipeline，同一份資料就能產出一致的 Excel、簡報和報告

## 練習

1. 把載入的財務資料換成你自己的幾筆數字，重跑 2.1 的 Excel 產生 cell，確認公式有跟著變。
2. 改 2.2 簡報的 prompt，把投影片數量限制在 3 張，並指定每張的主題。
3. 在 pipeline 那個 cell 加上計時和 token 用量輸出，比較 Excel、PPT、PDF 三步各花多少。
