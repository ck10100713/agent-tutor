---
translated: true
source: claude_agent_sdk/01_The_chief_of_staff_agent.ipynb
---
# Chief of staff agent

> 原文：[claude_agent_sdk/01_The_chief_of_staff_agent.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/01_The_chief_of_staff_agent.ipynb)

用 subagent、hook、output style 和 plan mode 打造 multi-agent 系統。

## 這篇在做什麼

接續 notebook 00 的簡單研究 agent，這篇一個功能一個功能地加，最後做出一個替新創公司 CEO 服務的 AI Chief of Staff。過程中會用到 CLAUDE.md 記憶、Bash 跑 Python 腳本、output style、plan mode、slash command、hook 和 subagent。每個功能都照「是什麼、為什麼用、怎麼做」的順序講。

## 學完你會

- 用 `cwd` 加 CLAUDE.md 給 agent 持久的背景 context，並知道 prompt 怎麼引導它用高層摘要還是細部資料。
- 用 `setting_sources` 載入 `.claude/` 底下的 output style、slash command、hook 和 subagent 定義。
- 用 `permission_mode="plan"` 讓 agent 只出計畫不動手，再用 hook 留下稽核紀錄、用 Agent tool 把工作委派給 subagent。

## 開跑前

- 需要 Anthropic API key
- 需要 Claude Agent SDK（claude-agent-sdk）和對應的執行環境
- 範例資料和腳本在 `chief_of_staff_agent/` 目錄底下，要先備好

```python
from dotenv import load_dotenv
from utils.agent_visualizer import (
    display_agent_response,
    print_activity,
    reset_activity_context,
    visualize_conversation,
)

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

load_dotenv()

# Define the model to use throughout this notebook
# Using Opus 5.5 for its superior planning and reasoning capabilities
MODEL = "claude-opus-5-5"
print(f"📋 Notebook configured to use: {MODEL}")
```

??? note "輸出"

    ```text
    📋 Notebook configured to use: claude-opus-5-5
    ```


#### 簡介

在 notebook 00 裡，我們做了一個簡單的研究 agent。這個 notebook 會一步步介紹 Claude Code SDK 的關鍵功能，用來打造完整的 agent。每個功能都會說明：
- **What**：這個功能是什麼
- **Why**：它能做什麼、為什麼要用
- **How**：一個最小的使用範例

如果你熟悉 Claude Code，會發現 SDK 讓你用程式、headless 的方式，使用 Claude Code 的所有能力。

#### 情境

整個 notebook 我們要為一間 50 人、剛拿到 $10M A 輪募資的新創公司打造一個 **AI Chief of Staff**。CEO 需要靠數據的洞察，在積極成長和財務永續之間取得平衡。

最後的 Chief of Staff agent 會：
- **協調各領域的專門 subagent**
- **整合多個來源的洞察**
- **提供附帶可執行建議的主管摘要**

## 基本功能

### 功能 0：用 [CLAUDE.md](https://www.anthropic.com/engineering/claude-code-best-practices) 當記憶

**What**：`CLAUDE.md` 檔是 agent 的持久記憶和指示。專案目錄裡有這個檔案時，Claude Code 在你初始化 agent 時會自動讀進來。

**Why**：你不用每次互動都重複提供專案背景、團隊偏好或標準，寫一次放在 `CLAUDE.md` 就好。這樣行為比較一致，也不用重複說明，省 token。

**How**：
- 在工作目錄放一個 `CLAUDE.md`，我們的例子是 `chief_of_staff_agent/CLAUDE.md`
- 把 ClaudeSDKClient 的 `cwd` 參數設成 CLAUDE.md 所在的目錄
- 想讓 agent 優先用高層 context、而不是細部資料檔時，用明確的 prompt 引導

**重要行為說明**：CLAUDE.md 和詳細資料檔（像 CSV）同時存在時，agent 可能會去讀比較細的資料來源，回答得更精確。這是預期中的行為，agent 本來就會去找最權威的資料。要讓 agent 用 CLAUDE.md 裡的高層 context，就要在 prompt 裡明確指示（見下面的範例）。這帶出一個重點：CLAUDE.md 提供的是 *context 和指引*，不是對資料來源的硬性限制。

```python
messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        cwd="chief_of_staff_agent",  # Points to subdirectory with our CLAUDE.md
        setting_sources=["project"],
    )
) as agent:
    await agent.query("What's our current runway?")
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)

# Display the response with HTML rendering
display_agent_response(messages)
# With this prompt, the agent should use CLAUDE.md values: ~$500K burn, 20 months runway
```

??? note "輸出"

    ```text
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

#### 了解 agent 對資料來源的偏好

**剛剛發生了什麼：**
我們在 prompt 裡加上了   ，引導 agent 去依賴 CLAUDE.md 的 context，而不是去 CSV 檔找更細的資料。

**重點觀察：**
1. **CLAUDE.md 是 context，不是限制**：設了 `cwd` 後，CLAUDE.md 會被載入當背景 context。但 agent 自然會去找最權威的資料來源，如果有詳細的 CSV，它可能為了精確度而偏好 CSV。

2. **prompt 寫法很重要**：「high-level financial numbers from context」這個說法，是在告訴 agent 你要的是 CLAUDE.md 裡簡化過的主管摘要（$500K burn、20 個月 runway），而不是 financial_data/burn_rate.csv 裡逐月的精確數字（$525K 毛額、$235K 淨 burn）。

3. **架構上的設計選擇**：這種行為在正式系統裡其實是好事，你會希望 agent 找到最好的資料來源。CLAUDE.md 應該放：
   - 高層的 context 和策略
   - 公司資訊和標準
   - 細部資料放在哪的指引
   - 什麼時候該用高層數字、什麼時候該用細部數字的準則

4. **實務上的模式**：把 CLAUDE.md 想成讓 agent 熟悉環境的「新人手冊」，詳細檔案則是需要精確度時可以查詢的「來源系統」。

### 功能 1：用 Bash tool 執行 Python 腳本

**What**：Bash tool 讓 agent 可以（除了其他事之外）直接執行 Python 腳本，取得程序性知識、做複雜運算、資料分析，以及其他超出 agent 原生能力的整合。

**Why**：Chief of Staff 可能需要處理資料檔、跑財務模型，或根據資料產生視覺化。這些都很適合用 Bash tool。

**How**：把 Python 腳本放在 agent 拿得到的地方，並補上說明它們是什麼、怎麼呼叫。如果腳本是給 chief of staff agent 用的，就把說明寫進它的 CLAUDE.md；如果是給某個 subagent 用的，就寫進該 subagent 的 MD 檔（後面會細講）。這份教學在 `chief_of_staff_agent/scripts` 加了五個示範腳本：
1. `hiring_impact.py`：計算新進工程師對 burn rate、runway 和現金部位的影響。`financial-analyst` subagent 用它來針對每月 $500K burn 和 20 個月 runway 模擬招聘情境。
2. `talent_scorer.py`：用加權的標準替候選人評分，包含技術能力、經驗、文化契合度和期望薪資。是 `recruiter` subagent 的核心工具，用來拿工程師候選人對照 TechStart 資深工程師 $180-220K 的基準做排名。
3. `simple_calculation.py`：快速做 runway、burn rate 和季度指標等財務計算。chief of staff 不用複雜建模就能即時拿到指標的工具腳本。
4. `financial_forecast.py`：以目前 $2.4M ARR、每月成長 15% 為基礎，模擬 ARR 成長情境（base/optimistic/pessimistic）。`financial-analyst` 用它推估 Series B 的準備程度，並驗證 $30M 的募資目標。
5. `decision_matrix.py`：替策略性決策（像收購 SmartDev 或擴大辦公室）建立加權決策矩陣。幫助 chief of staff 在多個利害關係人和標準下，有系統地評估複雜決策。

```python
messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        allowed_tools=["Bash", "Read"],
        cwd="chief_of_staff_agent",  # Points to subdirectory where our agent is defined
        setting_sources=["project"],
    )
) as agent:
    await agent.query(
        "Use your simple calculation script with a total runway of 2904829 and a monthly burn of 121938."
    )
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)

# Display the response with HTML rendering
display_agent_response(messages)
```

??? note "輸出"

    ```text
    🤖 Using: Glob()
    🤖 Using: Glob()
    🤖 Using: Glob()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Read()
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Bash()
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

### 功能 2：Output Styles

**What**：output style 讓你針對不同的對象使用不同的輸出風格。每種風格用一個 markdown 檔定義。

**Why**：你的 agent 可能被不同專業程度的人使用，或是他們的優先事項不同。用 output style 就能區分這些族群，不用另外做一個 agent。

**How**：
- 在 `chief_of_staff_agent/.claude/output-styles/` 裡替每種風格設一個 markdown 檔。例如看 `.claude/output-styles/executive.md` 的 Executive output style。output style 用簡單的 frontmatter 定義，有兩個欄位：name 和 description。注意：frontmatter 裡的 name 要跟檔名完全一致（區分大小寫）

> **重要**：output style 會修改 Claude Code 底層的 system prompt，拿掉偏軟體工程的部分，讓你在軟體工程以外的情境有更多控制權。

> **SDK 設定注意**：跟 slash command（功能 4 會講）一樣，output style 存放在檔案系統的 `.claude/output-styles/`。SDK 要載入這些檔案，你 **必須** 在 `ClaudeAgentOptions` 裡加上 `setting_sources=["project"]`。`settings` 參數告訴 SDK *用哪一個* style，但 `setting_sources` 才是真正 *載入* style 定義的設定。這是在後面章節 debug 時發現的，適用於所有基於檔案系統的設定。

```python
messages_executive = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        cwd="chief_of_staff_agent",
        settings='{"outputStyle": "executive"}',
        # IMPORTANT: setting_sources must include "project" to load output styles from .claude/output-styles/
        # Without this, the SDK does NOT load filesystem settings (output styles, slash commands, etc.)
        setting_sources=["project"],
    )
) as agent:
    await agent.query("Tell me in two sentences about your writing output style.")
    async for msg in agent.receive_response():
        print_activity(msg)
        messages_executive.append(msg)

messages_technical = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        cwd="chief_of_staff_agent",
        settings='{"outputStyle": "technical"}',
        setting_sources=["project"],
    )
) as agent:
    await agent.query("Tell me in two sentences about your writing output style.")
    async for msg in agent.receive_response():
        print_activity(msg)
        messages_technical.append(msg)
```

??? note "輸出"

    ```text
    🤖 Thinking...
    🤖 Thinking...
    ```

```python
# Display executive style response
display_agent_response(messages_executive)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# Technical output style - detailed, implementation-focused
display_agent_response(messages_technical, title="Technical Style")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

### 功能 3：Plan Mode，只規劃不執行

**What**：plan mode 要求 agent 產出詳細的執行計畫，但不執行任何動作。agent 會分析需求、提出解法、列出步驟，但不會改檔案、不會執行指令、也不會做任何變更。

**Why**：複雜任務先規劃，可以減少錯誤、方便審查、改善協調。規劃階段之後，agent 在整個執行過程中就有一條主線可以依循。

**How**：只要設 `permission_mode="plan"`

**保存計畫**：計畫是審查和決策的重要產物，所以我們會示範怎麼擷取並存成 markdown 檔。這樣利害關係人可以在核准執行前先看過計畫。

> 注意：這個功能在 Claude Code 裡表現很好，但在 SDK 的 headless 應用裡還沒有完全適配。具體來說，agent 會嘗試呼叫它的 `ExitPlanMode()` tool，而這個 tool 只在互動模式下有意義。這種情況下，你可以再送一個 `continue_conversation=True` 的後續 query，讓 agent 在同一個 context 裡執行它的計畫。

```python
# =============================================================================
# Plan Mode Helper Functions
# =============================================================================
# These utilities handle the various ways an agent might output its plan.
# Since agents can output plans via direct text, Write tool, or Claude's
# internal plan directory, we need robust extraction from multiple sources.

import glob as glob_module
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def extract_plan_from_xml(text: str | None, min_length: int = 200) -> str | None:
    """
    Extract content between <plan> tags from text.

    Args:
        text: The text to search for plan content
        min_length: Minimum character count for valid plan (prevents empty matches)

    Returns:
        Extracted plan content, or None if not found/too short
    """
    if not text:
        return None
    match = re.search(r"<plan>(.*?)</plan>", text, re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        if len(extracted) > min_length:
            return extracted
    return None


def extract_plan_from_messages(
    plan_content: list[str], min_fallback_length: int = 500
) -> tuple[str | None, str | None]:
    """
    Try to extract plan from captured message stream content.

    Args:
        plan_content: List of text blocks captured during streaming
        min_fallback_length: Minimum length for fallback (no XML tags)

    Returns:
        Tuple of (plan_text, source_description)
    """
    combined_text = "\n\n".join(plan_content)

    # First try: XML tags
    plan = extract_plan_from_xml(combined_text)
    if plan:
        return plan, "message stream"

    # Fallback: Use raw content if substantial
    if len(combined_text.strip()) > min_fallback_length:
        return combined_text.strip(), "full message content (fallback)"

    return None, None


def extract_plan_from_write_tool(
    write_contents: list[str], min_fallback_length: int = 500
) -> tuple[str | None, str | None]:
    """
    Try to extract plan from captured Write tool calls.

    Args:
        write_contents: List of content strings from Write tool calls
        min_fallback_length: Minimum length for fallback (no XML tags)

    Returns:
        Tuple of (plan_text, source_description)
    """
    for content in write_contents:
        # Try XML extraction first
        plan = extract_plan_from_xml(content)
        if plan:
            return plan, "Write tool capture"

        # Fallback: substantial content without tags
        if content and len(content.strip()) > min_fallback_length:
            return content.strip(), "Write tool capture (no XML tags)"

    return None, None


def extract_plan_from_claude_dir(
    max_age_seconds: int = 300, min_fallback_length: int = 500
) -> tuple[str | None, str | None]:
    """
    Check Claude's internal plan directory for recently created plans.

    Args:
        max_age_seconds: Maximum age of plan file to consider (default: 5 minutes)
        min_fallback_length: Minimum length for fallback (no XML tags)

    Returns:
        Tuple of (plan_text, source_description)
    """
    claude_plans_dir = os.path.expanduser("~/.claude/plans")

    if not os.path.exists(claude_plans_dir):
        return None, None

    # Find most recent plan file
    plan_files = sorted(
        glob_module.glob(os.path.join(claude_plans_dir, "*.md")),
        key=os.path.getmtime,
        reverse=True,
    )

    if not plan_files:
        return None, None

    most_recent = plan_files[0]
    file_age = datetime.now().timestamp() - os.path.getmtime(most_recent)

    if file_age > max_age_seconds:
        return None, None

    with open(most_recent) as f:
        content = f.read()

    filename = os.path.basename(most_recent)

    # Try XML extraction first
    plan = extract_plan_from_xml(content)
    if plan:
        return plan, f"Claude plan file ({filename})"

    # Fallback: substantial content without tags
    if len(content.strip()) > min_fallback_length:
        return content.strip(), f"Claude plan file ({filename}, no XML tags)"

    return None, None


def save_plan_to_file(
    plan_content: str,
    plan_source: str,
    model_name: str,
    prompt_summary: str,
    output_dir: str = "chief_of_staff_agent/plans",
    title: str = "Agent Plan: Engineering Restructure for AI Focus",
) -> Path:
    """
    Save extracted plan to a timestamped markdown file.

    Args:
        plan_content: The plan text to save
        plan_source: Description of where plan was extracted from
        model_name: The model used to generate the plan
        prompt_summary: Brief description of the original prompt
        output_dir: Directory to save plan files
        title: Title for the plan document

    Returns:
        Path to the saved plan file
    """
    plans_dir = Path(output_dir)
    plans_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    plan_file = plans_dir / f"plan_{timestamp}.md"

    with open(plan_file, "w") as f:
        f.write(f"# {title}\n\n")
        f.write(f"**Created:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"**Prompt:** {prompt_summary}\n")
        f.write(f"**Model:** {model_name}\n")
        f.write(f"**Plan Source:** {plan_source}\n\n")
        f.write("---\n\n")
        f.write(plan_content)
        f.write("\n\n---\n\n")
        f.write("*This plan was generated in plan mode and has not been executed.*\n")

    return plan_file


def capture_message_content(
    msg: Any,
    plan_content: list[str],
    write_tool_content: list[str],
    write_tool_paths: list[str],
) -> None:
    """
    Process a streaming message and capture relevant plan content.

    This function extracts content from three potential sources:
    1. Text blocks in message content
    2. Write tool call parameters
    3. Final result attribute

    Args:
        msg: The message object from the agent stream
        plan_content: List to append text content to
        write_tool_content: List to append Write tool content to
        write_tool_paths: List to append Write tool file paths to
    """
    # Source 1: Text blocks from message content
    if hasattr(msg, "content"):
        for block in msg.content:
            if hasattr(block, "text"):
                plan_content.append(block.text)

            # Source 2: Write tool calls
            if hasattr(block, "type") and block.type == "tool_use":
                if hasattr(block, "name") and block.name == "Write":
                    if hasattr(block, "input") and isinstance(block.input, dict):
                        if "content" in block.input:
                            write_tool_content.append(block.input["content"])
                        if "file_path" in block.input:
                            write_tool_paths.append(block.input["file_path"])

    # Source 3: Final result
    if hasattr(msg, "result") and msg.result:
        plan_content.append(msg.result)


print("✅ Plan Mode helper functions loaded")
```

??? note "輸出"

    ```text
    ✅ Plan Mode helper functions loaded
    ```

```python
# =============================================================================
# Plan Mode Configuration
# =============================================================================

# Note: MODEL is defined in cell-0 as "claude-opus-5-5"
# Opus excels at complex planning tasks

# The prompt is carefully crafted to:
# 1. Provide explicit context (since Opus prefers explicit information)
# 2. Request XML-tagged output for reliable extraction
# 3. Prevent file-writing so we can capture the plan programmatically

PLAN_PROMPT = """Restructure our engineering team for AI focus.

**CONTEXT (from CLAUDE.md):**
You are the Chief of Staff for TechStart Inc, a 50-person B2B SaaS startup that raised $10M Series A.
- Current engineering team: 25 people (Backend: 12, Frontend: 8, DevOps: 5)
- Monthly burn rate: ~$500K, Runway: 20 months
- Senior Engineer compensation: $180K-$220K + equity

**CRITICAL OUTPUT INSTRUCTIONS:**

1. **DO NOT use the Write tool** - Output your plan directly in your response text
2. **DO NOT save to any files** - I will handle saving the plan myself
3. **Wrap your ENTIRE plan inside `<plan> </plan>` XML tags** in your response

**Required Format:**
<plan>
[Your complete restructuring plan here - include all sections, timelines, budgets, and recommendations]
</plan>

**IMPORTANT:**
- The plan content MUST appear directly in your response between the XML tags
- Do NOT use Write, Edit, or any file-saving tools
- You may research and analyze before outputting, but the final plan must be in your response text
- Include: team structure, hiring recommendations, timeline, budget impact, and success metrics
- Use the company context provided above - do NOT ask clarifying questions"""

print(f"📋 Plan Mode configured with model: {MODEL}")
print(f"📝 Prompt length: {len(PLAN_PROMPT):,} characters")
```

??? note "輸出"

    ```text
    📋 Plan Mode configured with model: claude-opus-4-6
    📝 Prompt length: 1,180 characters
    ```

```python
# =============================================================================
# Execute Plan Mode Agent
# =============================================================================
# Run the agent with plan mode enabled. The agent will create a detailed plan
# but won't execute any actions. We capture content from multiple sources
# to handle different agent behaviors.

# Initialize capture lists
messages = []
plan_content = []  # Text from message stream
write_tool_content = []  # Content from Write tool calls
write_tool_paths = []  # Paths from Write tool calls

# Run the agent in plan mode
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        permission_mode="plan",
        cwd="chief_of_staff_agent",
        setting_sources=["project"],
    )
) as agent:
    await agent.query(PLAN_PROMPT)
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)

        # Capture content from this message
        capture_message_content(msg, plan_content, write_tool_content, write_tool_paths)

print(f"\n✅ Agent completed. Captured {len(plan_content)} content blocks.")
```

??? note "輸出"

    ```text
    🤖 Thinking...
    🤖 Using: ExitPlanMode()
    ✓ Tool completed
    🤖 Thinking...

    ✅ Agent completed. Captured 3 content blocks.
    ```

```python
# =============================================================================
# Extract and Save the Plan
# =============================================================================
# Try multiple sources in priority order to find the plan content.
# This handles different agent behaviors robustly.

final_plan = None
plan_source = None

# Priority 1: Message stream (preferred - direct from agent response)
final_plan, plan_source = extract_plan_from_messages(plan_content)

# Priority 2: Write tool captures (if agent saved despite instructions)
if not final_plan and write_tool_content:
    final_plan, plan_source = extract_plan_from_write_tool(write_tool_content)

# Priority 3: Claude's internal plan directory (safety net)
if not final_plan:
    final_plan, plan_source = extract_plan_from_claude_dir()

# Report results
if final_plan:
    print(f"✅ Plan extracted from: {plan_source}")
    print(f"   Plan length: {len(final_plan):,} characters")

    # Save to file
    plan_file = save_plan_to_file(
        plan_content=final_plan,
        plan_source=plan_source,
        model_name=MODEL,
        prompt_summary="Restructure our engineering team for AI focus.",
    )
    print(f"\n📁 Plan saved to: {plan_file}")
else:
    error_msg = "Could not extract plan content from any source!\n"
    error_msg += "   Sources checked: message stream, Write tool, ~/.claude/plans/"
    if write_tool_paths:
        error_msg += f"\n   Write tool attempted to save to: {write_tool_paths}"
    print(f"❌ ERROR: {error_msg}")
    raise RuntimeError(f"Plan extraction failed: {error_msg}")
```

??? note "輸出"

    ```text
    ✅ Plan extracted from: message stream
       Plan length: 6,783 characters

    📁 Plan saved to: chief_of_staff_agent/plans/plan_20251204_152737.md
    ```

```python
# Display the plan result with styled HTML
display_agent_response(messages, title="Engineering Restructure Plan")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

#### 執行已保存的計畫

如前所述，agent 產出計畫後就會停下來。保存下來的計畫檔，是給利害關係人審查用的。

**審查後要執行計畫：**
1. 查看保存在 `chief_of_staff_agent/plans/plan_*.md` 的計畫
2. 如果核准，送一個新的 query，帶 `continue_conversation=True` 並移除 `permission_mode="plan"` 來執行

這樣就形成「規劃 → 審查 → 核准 → 執行」的循環，很適合組織重整或重大基礎建設變更這類高風險決策。

#### 計畫保存怎麼運作

上面的程式碼裡，我們實作了一個 **多來源的計畫擷取機制**，處理 plan mode 的 agent 可能輸出計畫的各種方式：

**挑戰：**
用 `permission_mode="plan"` 時，agent 輸出計畫的方式可能不同：
1. **直接文字輸出** 在 message stream 裡（理想情況）
2. **Write tool** 存到 `~/.claude/plans/`（Claude 內部的計畫系統）
3. **Write tool** 存到自訂路徑

我們的擷取機制用 **依優先順序的 fallback 系統** 處理這三種情況：

**來源優先順序（依序）：**

1. **Message Stream**（首選）
   - 串流時從 `msg.content` 擷取文字 block
   - 取出 `<plan></plan>` XML tag 之間的內容
   - 這是最乾淨的做法，因為內容直接來自回應

2. **擷取 Write tool**
   - 監看 message stream 裡的 Write tool 呼叫
   - 取出被寫入的 `content` 參數
   - agent 不顧 prompt 指示還是決定存檔時很有用

3. **Claude 內部的計畫目錄**
   - 檢查 `~/.claude/plans/` 裡最近建立的計畫檔（5 分鐘內）
   - 讀取並取出最新檔案的內容
   - 其他方法都失敗時當作安全網

4. **完整內容 fallback**
   - 如果找不到 XML tag，但有相當多的內容（>500 字元），就直接使用
   - 避免產出空的計畫檔，同時保留部分資訊

**主要實作細節：**

```python
def extract_plan_from_text(text):
    """Extract content between <plan> tags, return None if not found or empty."""
    match = re.search(r'<plan>(.*?)</plan>', text, re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        # Validate minimum content length (a real plan should be substantial)
        if len(extracted) > 200:
            return extracted
    return None
```

**為什麼要驗證內容：**
- 舊版本如果擷取「成功」但沒有內容，會產出空的計畫檔
- 現在要求有 XML tag 的內容至少 200 字元
- 避免 regex 比對到空的或無意義內容而誤判

**針對直接輸出的 prompt 設計：**
prompt 明確要求 agent：
- **不要用 Write tool**：避免繞去檔案系統
- **直接在回應裡輸出**：確保內容經過 message stream
- **使用 XML tag**：即使回應很囉唆，也能乾淨地擷取

這個做法帶來：
- **可靠性**：不管 agent 怎麼做，計畫都能被擷取
- **透明度**：保存的檔案會標示用了哪個來源
- **稽核軌跡**：所有計畫的歷史，附時間戳記和來源 metadata
- **除錯**：擷取失敗時有清楚的錯誤訊息

來看保存下來的計畫：

```python
# Display the saved plan with markdown rendering
from IPython.display import Markdown, display

# Show the plan with proper markdown formatting
display(Markdown(f"## 📋 Saved Plan Preview\n\n{final_plan}"))

print(f"\n📁 Full plan with metadata saved to: {plan_file}")
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

    ```text

    📁 Full plan with metadata saved to: chief_of_staff_agent/plans/plan_20251204_152737.md
    ```

## 進階功能

### 功能 4：自訂 Slash Commands
> 注意：slash command 是給使用者的語法糖，不是 agent 的新能力

**What**：自訂 slash command 是預先定義好的 prompt 範本，使用者可以用簡寫語法觸發（例如 `/budget-impact`）。這些是 **給使用者的捷徑**，不是 agent 的能力。可以想成鍵盤快捷鍵，會展開成完整、精心寫好的 prompt。

**Why**：你的 Chief of Staff 會反覆處理主管常問的問題。使用者不用一再輸入複雜的 prompt，可以直接用已經審核過的 prompt。這樣比較一致、也比較標準化。

**How**：
- 在 `.claude/commands/` 裡定義一個 markdown 檔。例如我們在 `.claude/commands/slash-command-test.md` 定義了一個。看一下這個 command 怎麼定義：frontmatter 有兩個欄位（name、description），加上展開後的 prompt，還可以選擇帶入 query 傳來的參數。
- 你可以用 `$ARGUMENTS`（完整參數字串）或 `$1`、`$2` 等（位置參數）在 prompt 裡加參數
- 使用者在 prompt 裡使用 slash command

> **SDK 設定的關鍵**：用 SDK 時，要在 `ClaudeAgentOptions` 裡明確設定 `setting_sources`，這樣你才能控制載入哪些檔案系統設定（slash command、CLAUDE.md、subagent、hook 等）。`setting_sources=["project"]` 只載入這個專案的 `.claude/` 目錄。從 claude-agent-sdk 0.2 開始，不設的話會載入所有來源，包含你個人的 `~/.claude` 設定，跟互動式 Claude Code 一樣；傳 `setting_sources=[]` 可以隔離執行。

```python
# User types: "/slash-command-test this is a test"
# -> behind the scenes EXPANDS to the prompt in .claude/commands/slash-command-test.md
# In this case the expanded prompt says to simply reverse the sentence word wise

messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        cwd="chief_of_staff_agent",
        # IMPORTANT: setting_sources must include "project" to load slash commands from .claude/commands/
        # Without this, the SDK does NOT load filesystem settings (slash commands, CLAUDE.md, etc.)
        setting_sources=["project"],
    )
) as agent:
    await agent.query("/slash-command-test this is a test")
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)
```

??? note "輸出"

    ```text
    🤖 Thinking...
    ```

```python
display_agent_response(messages, title="Slash Command Result")
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

### 功能 5：Hooks，自動且確定性的動作

**What**：hook 是 Python 腳本，可以設定在特定事件自動執行，例如特定 tool 呼叫之前（pre）或之後（post）。hook 是 **確定性** 地執行，很適合用在驗證和稽核軌跡。

**Why**：想像你要確保 agent 有一些護欄（例如阻止危險操作），或是需要稽核軌跡的情境。hook 搭配 agent 很理想：給 agent 足夠的自由完成任務，同時確保它的行為是安全的。

**How**：
- 在 `.claude/hooks/` 定義 hook 腳本，決定 hook 觸發時 _要做什麼_
- 在 `.claude/settings.local.json` 定義 hook 設定，決定 _什麼時候_ 觸發
- 這個例子裡，hook 設定成監看特定的 tool 呼叫（Bash、Write、Edit）
- 這些 tool 被呼叫時，hook 腳本會在 tool 完成之後執行（PostToolUse）

> **SDK 設定注意**：設在 `.claude/settings.local.json` 的 hook 需要 `setting_sources=["project", "local"]`。SDK 區分三種設定來源：
> - `"project"` → `.claude/settings.json`（納入版本控制、團隊共用）
> - `"local"` → `.claude/settings.local.json`（被 gitignore、本機設定，像 hook）
> - `"user"` → `~/.claude/settings.json`（使用者全域設定）
>
> 因為我們的 hook 在 `settings.local.json`，所以 `setting_sources` 一定要包含 `"local"`。

**範例：為了合規追蹤報告**

一個 hook，為了稽核和合規，記錄對財務報告的 Write/Edit 操作。
hook 定義在 `chief_of_staff_agent/.claude/hooks/report-tracker.py`，而負責讓它生效的邏輯在 `chief_of_staff_agent/.claude/settings.local.json`：


```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Write",
      "hooks": [
        {
          "type": "command",
          "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/report-tracker.py"
        }
      ]
    },
    {
      "matcher": "Edit",
      "hooks": [
        {
          "type": "command",
          "command": "$CLAUDE_PROJECT_DIR/.claude/hooks/report-tracker.py"
        }
      ]
    }
  ]
}
```

```python
messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        cwd="chief_of_staff_agent",
        allowed_tools=["Bash", "Write", "Edit", "MultiEdit"],
        # IMPORTANT: setting_sources must include BOTH "project" AND "local" to load hooks
        # - "project" loads .claude/settings.json (shared settings, CLAUDE.md, slash commands)
        # - "local" loads .claude/settings.local.json (where hooks are configured)
        setting_sources=["project", "local"],
    )
) as agent:
    await agent.query(
        "Create a quick Q2 financial forecast report with our current burn rate and runway projections. Save it to our /output_reports folder."
    )
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)

# The hook will track this in audit/report_history.json
display_agent_response(messages, title="Q2 Financial Forecast")
```

??? note "輸出"

    ```text
    🤖 Using: Bash()
    🤖 Using: Bash()
    🤖 Using: Bash()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Using: Read()
    🤖 Using: Read()
    🤖 Using: Read()
    🤖 Using: Bash()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Write()
    ✓ Tool completed
    🤖 Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

現在到 `./chief_of_staff_agent/audit/report_history.json` 看，會發現它已經記錄了 agent 建立和（或）修改你的報告。產生的報告本身在 `./chief_of_staff_agent/output_reports/`。

### 功能 6：透過 Agent tool 使用 Subagents

**What**：Agent tool（claude-agent-sdk 0.2 之前叫 `Task`，舊名稱仍然接受）讓你的 agent 把專門的工作委派給其他 subagent。每個 subagent 有自己的指示、tool 和專長。

**Why**：加入 subagent 有很多好處：
1. 專業化：每個 subagent 是各自領域的專家
2. 獨立的 context：subagent 有自己的對話歷史和 tool
3. 平行化：多個 subagent 可以同時處理不同面向

**How**：
- 把 `"Agent"` 加到 allowed_tools
- 用 system prompt 指示你的 agent 怎麼委派任務（也可以更通用地定義在它的 CLAUDE.md）
- 在 `.claude/agents/` 替每個 agent 建一個 markdown 檔。例如看 `.claude/agents/financial-analyst.md`，注意 (sub)agent 可以用這麼簡單直覺的 markdown 檔定義：frontmatter 有三個欄位（name、description 和 tools），加上它的 system prompt。description 能讓主要的 chief of staff agent 知道什麼時候該呼叫哪個 subagent。

**視覺化強化**：我們的 `print_activity()` 和 `visualize_conversation()` 工具已經強化，能清楚顯示 subagent 的操作：
- 🚀 表示正在委派給某個 subagent（附 subagent 名稱）
- 📎 表示 subagent 正在使用的 tool（縮排以呈現階層）
- 視覺分隔線清楚標出 subagent 委派和完成的邊界
- 對話時間軸裡會顯示任務描述和 prompt

```python
# Reset the subagent tracking context before starting a new query
# This ensures clean state for activity display
reset_activity_context()

messages = []
async with ClaudeSDKClient(
    options=ClaudeAgentOptions(
        model=MODEL,
        allowed_tools=["Agent"],  # this enables our Chief agent to invoke subagents
        system_prompt="Delegate financial questions to the financial-analyst subagent. Do not try to answer these questions yourself.",
        cwd="chief_of_staff_agent",
        setting_sources=["project", "local"],
    )
) as agent:
    await agent.query("Should we hire 5 engineers? Analyze the financial impact.")
    async for msg in agent.receive_response():
        print_activity(msg)
        messages.append(msg)

display_agent_response(messages, title="Hiring Impact Analysis")
```

??? note "輸出"

    ```text
    🤖 Thinking...
    🚀 Delegating to subagent: financial-analyst
       └─ Task: Analyze 5 engineer hiring impact
       ✓ Tool completed
       📎 [financial-analyst] Using: Bash()
       📎 [financial-analyst] Using: Read()
       📎 [financial-analyst] Using: Read()
       ✓ Tool completed
       ✓ Tool completed
       ✓ Tool completed
       📎 [financial-analyst] Using: Read()
       📎 [financial-analyst] Using: Bash()
       ✓ Tool completed
       ✓ Tool completed
       📎 [financial-analyst] Using: Bash()
       ✓ Tool completed
       📎 [financial-analyst] Using: Bash()
       ✓ Tool completed
       📎 [financial-analyst] Using: Bash()
       ✓ Tool completed
       📎 [financial-analyst] Using: Bash()
       ✓ Tool completed
       ✓ Tool completed
       📎 [financial-analyst] Thinking...
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

```python
visualize_conversation(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

這裡，主 agent 決定使用 subagent 時，會：
  1. 呼叫 Agent tool，帶這樣的參數：
  ```json
    {
      "description": "Analyze hiring impact",
      "prompt": "Analyze the financial impact of hiring 5 engineers...",
      "subagent_type": "financial-analyst"
    }
  ```
  2. Agent tool 在獨立的 context 裡執行 subagent
  3. 把結果回傳給主 Chief of Staff agent 繼續處理

## 全部組合起來

把前面看過的全部組合起來。我們請 agent 判斷聘請 3 位資深工程師的財務影響，並把洞察寫到 `output_reports/hiring_decision.md`。這會展示上面所有功能：
- **Bash Tool**：用來執行 `hiring_impact.py` 腳本，判斷聘請新工程師的影響
- **Memory**：讀取目錄裡的 `CLAUDE.md` 當 context，了解目前的預算、runway、營收和其他相關資訊
- **Output style**：不同的 output style，定義在 `chief_of_staff_agent/.claude/output-styles`
- **自訂 Slash Commands**：使用捷徑 `/budget-impact`，展開成定義在 `chief_of_staff_agent/.claude/commands` 的完整 prompt
- **Subagents**：我們的 `/budget_impact` command 引導 chief of staff agent 去呼叫定義在 `chief_of_staff_agent/.claude/agents` 的 financial-analyst subagent
- **Hooks**：hook 定義在 `chief_of_staff_agent/.claude/hooks`，設定在 `chief_of_staff_agent/.claude/settings.local.json`
    - 如果我們的某個 agent 在更新財務報告，hook 會把這個編輯/寫入動作記錄到 `chief_of_staff_agent/audit/report_history.json`
    - 如果 financial analyst subagent 呼叫 `hiring_impact.py` 腳本，會記錄在 `chief_of_staff_agent/audit/tool_usage_log.json`

- **Plan Mode**：如果你想讓 chief of staff 在採取任何行動前，先提出一個計畫讓你核准，把下面被註解掉的那一行取消註解

為了方便直接跑，我們跟前一個 notebook 一樣，把 agent loop 包進一個 python 檔。看 `chief_of_staff_agent` 子目錄裡的 agent.py 檔。

總之，我們的 `send_query()` 函式接受 4 個參數（prompt、continue_conversation、permission_mode 和 output_style），其他都在 agent 檔裡設好了，包括：system prompt、max turns、allowed tools 和工作目錄。

想更清楚看這一切怎麼組合，可以看看 [Claude 幫我們畫的流程和架構圖 :)](https://github.com/anthropics/claude-cookbooks/blob/main/claude_agent_sdk/chief_of_staff_agent/flow_diagram.md)


```python
from chief_of_staff_agent.agent import send_query

reset_activity_context()

result, messages = await send_query(
    "/budget-impact hiring 3 senior engineers. Save your insights by updating the 'hiring_decision.md' file in /output_reports or creating a new file there",
    # permission_mode="plan", # Enable this to use planning mode
    output_style="executive",
)
```

??? note "輸出"

    ```text
    🤖 Thinking...
    🤖 Using: Glob()
    🤖 Using: Glob()
    ✓ Tool completed
    ✓ Tool completed
    🤖 Using: Read()
    🤖 Using: Read()
    🤖 Using: Read()
    🤖 Using: Read()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Task()
    ✓ Tool completed
    🤖 Using: Bash()
    🤖 Using: Read()
    🤖 Using: Read()
    🤖 Using: Read()
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    ✓ Tool completed
    🤖 Thinking...
    🤖 Using: Write()
    ✓ Tool completed
    🤖 Thinking...
    ```

```python
visualize_conversation(messages)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 結論

我們示範了 Claude Code SDK 怎麼讓你打造具備企業級功能的複雜 multi-agent 系統。從用 Bash tool 執行基本腳本開始，逐步加入進階能力：用 CLAUDE.md 做持久記憶、針對不同對象的自訂 output style、策略性的規劃模式、方便使用者的 slash command、當護欄的合規 hook，以及處理專門任務的 subagent 協調。

結合這些功能，我們做出一個能處理複雜主管決策流程的 AI Chief of Staff。系統把財務分析委派給專門的 subagent，用 hook 維持稽核軌跡，針對不同的利害關係人調整溝通風格，並提供以數據分析為根據、可執行的洞察。

這份進階 agentic 模式和 multi-agent 編排的基礎，會幫你準備好打造可上線的企業系統。下一個 notebook 會講怎麼透過 Model Context Protocol (MCP) server 把 agent 連到外部服務，大幅擴充內建 tool 以外的能力。

下一篇：[02_The_observability_agent.ipynb](02_The_observability_agent.md)，學怎麼透過 MCP 用自訂整合和外部資料來源擴充你的 agent。

## 重點整理

- CLAUDE.md 是 agent 的背景 context 和新人手冊，不是對資料來源的硬性限制，agent 仍會為了精確度去找更細的資料，要用 prompt 引導。
- `setting_sources` 決定 SDK 載入哪些檔案系統設定，output style、slash command、subagent 放 project，hook 放 local 就要加 `"local"`。
- plan mode 讓 agent 只規劃不執行，搭配保存計畫和 `continue_conversation=True`，可以做成「規劃、審查、核准、執行」的流程。
- hook 是確定性執行的，適合做護欄和稽核；slash command 只是給使用者的 prompt 捷徑，不是 agent 的新能力。
- subagent 有各自的 context、tool 和專長，主 agent 靠 description 決定何時委派。

## 練習

1. 改 `chief_of_staff_agent/CLAUDE.md` 裡的 burn rate 或 runway 數字，再跑功能 0 的 prompt，確認 agent 回答的是你改過的值。
2. 在 `.claude/output-styles/` 新增一個給工程主管看的 style 檔，frontmatter 的 name 要跟檔名一致，然後用它跑同一個財務問題，比較輸出差異。
3. 照 `.claude/hooks/report-tracker.py` 的做法，另外寫一個 hook 腳本，在 Bash tool 呼叫 `hiring_impact.py` 時寫一筆紀錄，並在 `settings.local.json` 設定觸發條件。
