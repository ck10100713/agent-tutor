---
translated: true
source: examples/Optimize_Prompts.ipynb
---
# Optimize Prompts

> 原文：[examples/Optimize_Prompts.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Optimize_Prompts.ipynb)



## 這篇在做什麼

用 Agents SDK 搭配 Evals，做出一個早期版本的 prompt 優化系統。多個專職 agent 平行檢查 prompt 的矛盾、格式不明、和 few-shot 範例不一致的問題，再由 rewriter agent 改寫。最後用三個範例看實際效果。

## 學完你會

- 用 Pydantic 定義 agent 之間傳遞的結構化輸入輸出（Issues、MessagesOutput 等）
- 用 `Agent` class 寫出範圍明確的 checker 與 rewriter agent，並理解寫 instructions 的幾項最佳實務
- 用 `optimize_prompt_parallel` 平行跑 checker、再有條件地跑 rewriter，並用 golden examples 搭配 Evals 選模型、調 instructions

## 開跑前

- 安裝 `openai` 和 `openai-agents` 兩個 Python 套件
- 設好環境變數 `OPENAI_API_KEY`


寫出有效的 prompt 是用 AI 模型的關鍵技能。就算是有經驗的使用者，也可能不小心寫出矛盾、模糊或不一致的內容，導致結果不理想。這裡示範的系統能找出並修正常見問題，讓 prompt 更可靠、更有效。

這個優化流程採用 multi-agent 的做法，由各有專長的 AI agent 合作分析和改寫 prompt。系統會自動找出並處理幾類常見問題：

- prompt 指示之間的**矛盾**
- 缺少或不清楚的**格式規範**
- prompt 和 few-shot 範例之間的**不一致**

---

**目標**：這篇示範用 Agents SDK 搭配 Evals 的最佳實務，做出 OpenAI prompt 優化系統的早期版本。你可以用這份程式碼優化 prompt，也可以直接用 [playground 裡的優化器](https://platform.openai.com/playground/prompts)！








Ask ChatGPT


**內容結構**  
這份 notebook 的結構如下：

- [Step 1. System Overview](#1-system-overview) - 了解 prompt 優化系統怎麼運作  
- [Step 2. Data Models](#2-data-models) - 了解系統用的資料結構
- [Step 3. Defining the Agents](#3-defining-the-agents) - 看分析並改進 prompt 的 agent
- [Step 4. Evaluations](#4-using-evaluations-to-arrive-at-these-agents) - 用 Evals 驗證我們選的 agent 模型和 instructions
- [Step 5. Run Optimization Workflow](#4-run-optimization-workflow) - 看 workflow 怎麼傳遞 prompt
- [Step 6. Examples](#5-examples) - 看 prompt 優化的實際範例

**前置條件**
- `openai` Python 套件 
- `openai-agents` 套件
- 在環境變數設好 OpenAI API key `OPENAI_API_KEY`

## 1. 系統概覽

Prompt 優化系統採用協作式的 multi-agent 做法來分析並改進 prompt。每個 agent 專門負責偵測或改寫一種問題：

1. **Dev-Contradiction-Checker**：掃描 prompt 裡的邏輯矛盾或不可能達成的指示，例如同一個 prompt 裡同時說「只能用正數」和「要包含負數範例」。

2. **Format-Checker**：找出 prompt 期待結構化輸出（像 JSON、CSV 或 Markdown），卻沒清楚說明確切格式的情況。這個 agent 確保所有必要欄位、資料型別和格式規則都有明確定義。

3. **Few-Shot-Consistency-Checker**：檢查範例對話，確認 assistant 的回應確實遵守 prompt 裡訂的規則。這能抓出 prompt 的要求跟範例實際示範不符的地方。

4. **Dev-Rewriter**：問題找出來之後，這個 agent 改寫 prompt，解決矛盾、釐清格式規範，同時保留原本的意圖。

5. **Few-Shot-Rewriter**：把不一致的範例回應更新成符合 prompt 的規則，確保所有範例都符合新的 developer prompt。

這些 agent 合作，就能有系統地找出並修正 prompt 的問題。

```python
# Import required modules
from openai import AsyncOpenAI
import asyncio
import json
import os
from enum import Enum
from typing import Any, List, Dict
from pydantic import BaseModel, Field
from agents import Agent, Runner, set_default_openai_client, trace

openai_client: AsyncOpenAI | None = None

def _get_openai_client() -> AsyncOpenAI:
    global openai_client
    if openai_client is None:
        openai_client = AsyncOpenAI(
            api_key=os.environ.get("OPENAI_API_KEY", "your-api-key"),
        )
    return openai_client

set_default_openai_client(_get_openai_client())
```

## 2. Data Models

為了讓 agent 之間能做結構化的溝通，系統用 Pydantic model 定義輸入與輸出的預期格式。這些 Pydantic model 幫忙驗證資料，確保整個 workflow 一致。

資料模型包含：

1. **Role** - 訊息角色的 enum（user/assistant）
2. **ChatMessage** - 代表對話中的一則訊息
3. **Issues** - 回報偵測到問題的基底 model
4. **FewShotIssues** - 擴充的 model，加上對範例訊息的改寫建議
5. **MessagesOutput** - 包含優化後的對話訊息
6. **DevRewriteOutput** - 包含改進後的 developer prompt

用 Pydantic，系統就能在流程的每一步驗證資料符合預期格式。

```python
class Role(str, Enum):
    """Role enum for chat messages."""
    user = "user"
    assistant = "assistant"

class ChatMessage(BaseModel):
    """Single chat message used in few-shot examples."""
    role: Role
    content: str

class Issues(BaseModel):
    """Structured output returned by checkers."""
    has_issues: bool
    issues: List[str]
    
    @classmethod
    def no_issues(cls) -> "Issues":
        return cls(has_issues=False, issues=[])

class FewShotIssues(Issues):
    """Output for few-shot contradiction detector including optional rewrite suggestions."""
    rewrite_suggestions: List[str] = Field(default_factory=list)
    
    @classmethod
    def no_issues(cls) -> "FewShotIssues":
        return cls(has_issues=False, issues=[], rewrite_suggestions=[])

class MessagesOutput(BaseModel):
    """Structured output returned by `rewrite_messages_agent`."""

    messages: list[ChatMessage]


class DevRewriteOutput(BaseModel):
    """Rewriter returns the cleaned-up developer prompt."""

    new_developer_message: str
```

## 3. 定義 Agents

這一節用 `openai-agents` 套件的 `Agent` class 建立專職的 AI agent。看這些 agent 的定義，可以學到幾項寫出有效 AI instructions 的最佳實務：

### Agent Instructions 的最佳實務

1. **明確的範圍定義**：每個 agent 的目的都很窄，邊界明確。例如 contradiction checker 只專注在「真正的自我矛盾」，並明說「重疊或冗餘不算矛盾」。

2. **逐步的流程**：instructions 提供清楚的方法，例如 format checker 會先替任務分類，再分析格式要求。

3. **明確的定義**：關鍵術語都精確定義，避免歧義。few-shot consistency checker 有一份詳細的 “Compliance Rubric”，明確說明什麼才算符合。

4. **設定界線**：instructions 說明 agent 不該做什麼。few-shot checker 明確列出 “Out-of-scope” 的項目，避免過度標記問題。

5. **結構化的輸出要求**：每個 agent 都有嚴格定義的輸出格式並附範例，確保優化 pipeline 的一致性。

這些原則造就可靠、專注、能在優化系統裡有效合作的 agent。下面是完整的 agent 定義和詳細的 instructions。

````python
dev_contradiction_checker = Agent(
    name="contradiction_detector",
    model="gpt-4.1",
    output_type=Issues,
    instructions="""
    You are **Dev-Contradiction-Checker**.

    Goal
    Detect *genuine* self-contradictions or impossibilities **inside** the developer prompt supplied in the variable `DEVELOPER_MESSAGE`.

    Definitions
    • A contradiction = two clauses that cannot both be followed.
    • Overlaps or redundancies in the DEVELOPER_MESSAGE are *not* contradictions.

    What you MUST do
    1. Compare every imperative / prohibition against all others.
    2. List at most FIVE contradictions (each as ONE bullet).
    3. If no contradiction exists, say so.

    Output format (**strict JSON**)
    Return **only** an object that matches the `Issues` schema:

    ```json
    {"has_issues": <bool>,
    "issues": [
        "<bullet 1>",
        "<bullet 2>"
    ]
    }
    - has_issues = true IFF the issues array is non-empty.
    - Do not add extra keys, comments or markdown.
""",
)
format_checker = Agent(
    name="format_checker",
    model="gpt-4.1",
    output_type=Issues,
    instructions="""
    You are Format-Checker.

    Task
    Decide whether the developer prompt requires a structured output (JSON/CSV/XML/Markdown table, etc.).
    If so, flag any missing or unclear aspects of that format.

    Steps
    Categorise the task as:
    a. "conversation_only", or
    b. "structured_output_required".

    For case (b):
    - Point out absent fields, ambiguous data types, unspecified ordering, or missing error-handling.

    Do NOT invent issues if unsure. be a little bit more conservative in flagging format issues

    Output format
    Return strictly-valid JSON following the Issues schema:

    {
    "has_issues": <bool>,
    "issues": ["<desc 1>", "..."]
    }
    Maximum five issues. No extra keys or text.
""",
)
fewshot_consistency_checker = Agent(
    name="fewshot_consistency_checker",
    model="gpt-4.1",
    output_type=FewShotIssues,
    instructions="""
    You are FewShot-Consistency-Checker.

    Goal
    Find conflicts between the DEVELOPER_MESSAGE rules and the accompanying **assistant** examples.

    USER_EXAMPLES:      <all user lines>          # context only
    ASSISTANT_EXAMPLES: <all assistant lines>     # to be evaluated

    Method
    Extract key constraints from DEVELOPER_MESSAGE:
    - Tone / style
    - Forbidden or mandated content
    - Output format requirements

    Compliance Rubric - read carefully
    Evaluate only what the developer message makes explicit.

    Objective constraints you must check when present:
    - Required output type syntax (e.g., "JSON object", "single sentence", "subject line").
    - Hard limits (length ≤ N chars, language required to be English, forbidden words, etc.).
    - Mandatory tokens or fields the developer explicitly names.

    Out-of-scope (DO NOT FLAG):
    - Whether the reply "sounds generic", "repeats the prompt", or "fully reflects the user's request" - unless the developer text explicitly demands those qualities.
    - Creative style, marketing quality, or depth of content unless stated.
    - Minor stylistic choices (capitalisation, punctuation) that do not violate an explicit rule.

    Pass/Fail rule
    - If an assistant reply satisfies all objective constraints, it is compliant, even if you personally find it bland or loosely related.
    - Only record an issue when a concrete, quoted rule is broken.

    Empty assistant list ⇒ immediately return has_issues=false.

    For each assistant example:
    - USER_EXAMPLES are for context only; never use them to judge compliance.
    - Judge each assistant reply solely against the explicit constraints you extracted from the developer message.
    - If a reply breaks a specific, quoted rule, add a line explaining which rule it breaks.
    - Optionally, suggest a rewrite in one short sentence (add to rewrite_suggestions).
    - If you are uncertain, do not flag an issue.
    - Be conservative—uncertain or ambiguous cases are not issues.

    be a little bit more conservative in flagging few shot contradiction issues
    Output format
    Return JSON matching FewShotIssues:

    {
    "has_issues": <bool>,
    "issues": ["<explanation 1>", "..."],
    "rewrite_suggestions": ["<suggestion 1>", "..."] // may be []
    }
    List max five items for both arrays.
    Provide empty arrays when none.
    No markdown, no extra keys.
    """,
)
dev_rewriter = Agent(
    name="dev_rewriter",
    model="gpt-4.1",
    output_type=DevRewriteOutput,
    instructions="""
    You are Dev-Rewriter.

    You receive:
    - ORIGINAL_DEVELOPER_MESSAGE
    - CONTRADICTION_ISSUES (may be empty)
    - FORMAT_ISSUES (may be empty)

    Rewrite rules
    Preserve the original intent and capabilities.

    Resolve each contradiction:
    - Keep the clause that preserves the message intent; remove/merge the conflicting one.

    If FORMAT_ISSUES is non-empty:
    - Append a new section titled ## Output Format that clearly defines the schema or gives an explicit example.

    Do NOT change few-shot examples.

    Do NOT add new policies or scope.

    Output format (strict JSON)
    {
    "new_developer_message": "<full rewritten text>"
    }
    No other keys, no markdown.
""",
)
fewshot_rewriter = Agent(
    name="fewshot_rewriter",
    model="gpt-4.1",
    output_type=MessagesOutput,
    instructions="""
    You are FewShot-Rewriter.

    Input payload
    - NEW_DEVELOPER_MESSAGE (already optimized)
    - ORIGINAL_MESSAGES (list of user/assistant dicts)
    - FEW_SHOT_ISSUES (non-empty)

    Task
    Regenerate only the assistant parts that were flagged.
    User messages must remain identical.
    Every regenerated assistant reply MUST comply with NEW_DEVELOPER_MESSAGE.

    After regenerating each assistant reply, verify:
    - It matches NEW_DEVELOPER_MESSAGE. ENSURE THAT THIS IS TRUE.

    Output format
    Return strict JSON that matches the MessagesOutput schema:

    {
    "messages": [
        {"role": "user", "content": "..."},
        {"role": "assistant", "content": "..."}
        ]
    }
    Guidelines
    - Preserve original ordering and total count.
    - If a message was unproblematic, copy it unchanged.
    """,
)
````

## 4. 用 Evaluations 得出這些 Agent

來看我們怎麼用 OpenAI Evals 調整 agent 的 instructions 並挑選正確的模型。為此我們建立了一組 golden examples：每一組都包含原始訊息（developer message 加 user/assistant 訊息），以及我們的優化 workflow 應該做的修改。下面是我們用的兩組 golden pair 範例：

```
[
  {
    "focus": "contradiction_issues",
    "input_payload": {
      "developer_message": "Always answer in **English**.\nNunca respondas en inglés.",
      "messages": [
        {
          "role": "user",
          "content": "¿Qué hora es?"
        }
      ]
    },
    "golden_output": {
      "changes": true,
      "new_developer_message": "Always answer **in English**.",
      "new_messages": [
        {
          "role": "user",
          "content": "¿Qué hora es?"
        }
      ],
      "contradiction_issues": "Developer message simultaneously insists on English and forbids it.",
      "few_shot_contradiction_issues": "",
      "format_issues": "",
      "general_improvements": ""
    }
  },
  {
    "focus": "few_shot_contradiction_issues",
    "input_payload": {
      "developer_message": "Respond with **only 'yes' or 'no'** – no explanations.",
      "messages": [
        {
          "role": "user",
          "content": "Is the sky blue?"
        },
        {
          "role": "assistant",
          "content": "Yes, because wavelengths …"
        },
        {
          "role": "user",
          "content": "Is water wet?"
        },
        {
          "role": "assistant",
          "content": "Yes."
        }
      ]
    },
    "golden_output": {
      "changes": true,
      "new_developer_message": "Respond with **only** the single word \"yes\" or \"no\".",
      "new_messages": [
        {
          "role": "user",
          "content": "Is the sky blue?"
        },
        {
          "role": "assistant",
          "content": "yes"
        },
        {
          "role": "user",
          "content": "Is water wet?"
        },
        {
          "role": "assistant",
          "content": "yes"
        }
      ],
      "contradiction_issues": "",
      "few_shot_contradiction_issues": "Assistant examples include explanations despite instruction not to.",
      "format_issues": "",
      "general_improvements": ""
    }
  }
]
```

這 20 組人工標註的 golden output 涵蓋各種情況：矛盾問題、few shot 問題、格式問題、沒有問題，或多種問題並存。我們據此建了一個 python string check grader，驗證兩件事：每組 golden pair 有沒有偵測到問題，以及偵測到的問題是否符合預期。靠這個訊號，我們調整 agent 的 instructions 和使用的模型，讓這個評測的準確率最大化。最後我們選了 4.1 模型，在準確率、成本和速度之間取得平衡。我們用的 prompt 也遵循 4.1 prompting guide。如你所見，20 組 golden output 的標籤全部正確：找對問題，也沒有誤判。 

![Accuracy for the golden set](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/optimizepromptfig1.png)

![Evaluation for the golden set](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/optimizepromptfig2.png)

## 5. 執行優化 Workflow

來看優化系統從頭到尾實際怎麼運作。核心 workflow 會多次平行執行 agent，有效率地處理並優化 prompt。

```python
def _normalize_messages(messages: List[Any]) -> List[Dict[str, str]]:
    """Convert list of pydantic message models to JSON-serializable dicts."""
    result = []
    for m in messages:
        if hasattr(m, "model_dump"):
            result.append(m.model_dump())
        elif isinstance(m, dict) and "role" in m and "content" in m:
            result.append({"role": str(m["role"]), "content": str(m["content"])})
    return result

async def optimize_prompt_parallel(
    developer_message: str,
    messages: List["ChatMessage"],
) -> Dict[str, Any]:
    """
    Runs contradiction, format, and few-shot checkers in parallel,
    then rewrites the prompt/examples if needed.
    Returns a unified dict suitable for an API or endpoint.
    """

    with trace("optimize_prompt_workflow"):
        # 1. Run all checkers in parallel (contradiction, format, fewshot if there are examples)
        tasks = [
            Runner.run(dev_contradiction_checker, developer_message),
            Runner.run(format_checker, developer_message),
        ]
        if messages:
            fs_input = {
                "DEVELOPER_MESSAGE": developer_message,
                "USER_EXAMPLES": [m.content for m in messages if m.role == "user"],
                "ASSISTANT_EXAMPLES": [m.content for m in messages if m.role == "assistant"],
            }
            tasks.append(Runner.run(fewshot_consistency_checker, json.dumps(fs_input)))

        results = await asyncio.gather(*tasks)

        # Unpack results
        cd_issues: Issues = results[0].final_output
        fi_issues: Issues = results[1].final_output
        fs_issues: FewShotIssues = results[2].final_output if messages else FewShotIssues.no_issues()

        # 3. Rewrites as needed
        final_prompt = developer_message
        if cd_issues.has_issues or fi_issues.has_issues:
            pr_input = {
                "ORIGINAL_DEVELOPER_MESSAGE": developer_message,
                "CONTRADICTION_ISSUES": cd_issues.model_dump(),
                "FORMAT_ISSUES": fi_issues.model_dump(),
            }
            pr_res = await Runner.run(dev_rewriter, json.dumps(pr_input))
            final_prompt = pr_res.final_output.new_developer_message

        final_messages: list[ChatMessage] | list[dict[str, str]] = messages
        if fs_issues.has_issues:
            mr_input = {
                "NEW_DEVELOPER_MESSAGE": final_prompt,
                "ORIGINAL_MESSAGES": _normalize_messages(messages),
                "FEW_SHOT_ISSUES": fs_issues.model_dump(),
            }
            mr_res = await Runner.run(fewshot_rewriter, json.dumps(mr_input))
            final_messages = mr_res.final_output.messages

        return {
            "changes": True,
            "new_developer_message": final_prompt,
            "new_messages": _normalize_messages(final_messages),
            "contradiction_issues": "\n".join(cd_issues.issues),
            "few_shot_contradiction_issues": "\n".join(fs_issues.issues),
            "format_issues": "\n".join(fi_issues.issues),
        }
```

![Trace for the workflow](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/optimizepromptfig3.png)

### 了解優化 Workflow

`optimize_prompt_parallel` function 實作的 workflow 靠平行化來提高效率：

1. **平行偵測問題**：第一階段同時執行所有 checker agent：
   - `dev_contradiction_checker` 找 prompt 裡的邏輯矛盾
   - `format_checker` 找不清楚的格式規範
   - `fewshot_consistency_checker`（有範例時）檢查 prompt 和範例是否不一致

平行檢查之後，workflow 會小心處理相依關係：

2. **改寫 Prompt（有條件）**：只有偵測到矛盾或格式問題時，才會執行 `dev_rewriter` agent。這個 agent 依賴下面的輸出：
   - `dev_contradiction_checker`（`cd_issues` 變數）
   - `format_checker`（`fi_issues` 變數）

3. **改寫範例（有條件）**：只有偵測到範例不一致時，才會執行 `fewshot_rewriter` agent。這個 agent 依賴：
   - 改寫後的 prompt（必須在改寫 prompt 之後做）
   - 原始訊息
   - few-shot 問題（`fs_issues` 變數）


## 6. 範例

用幾個實際範例看優化系統運作。

### 範例 1：修正矛盾

````python
async def example_contradiction():
    # A prompt with contradictory instructions
    prompt = """Quick-Start Card — Product Parser

Goal  
Digest raw HTML of an e-commerce product detail page and emit **concise, minified JSON** describing the item.

**Required fields:**  
name | brand | sku | price.value | price.currency | images[] | sizes[] | materials[] | care_instructions | features[]

**Extraction priority:**  
1. schema.org/JSON-LD blocks  
2. <meta> & microdata tags  
3. Visible DOM fallback (class hints: "product-name", "price")

** Rules:**  
- If *any* required field is missing, short-circuit with: `{"error": "FIELD_MISSING:<field>"}`.
- Prices: Numeric with dot decimal; strip non-digits (e.g., "1.299,00 EUR" → 1299.00 + "EUR").
- Deduplicate images differing only by query string. Keep ≤10 best-res.
- Sizes: Ensure unit tag ("EU", "US") and ascending sort.
- Materials: Title-case and collapse synonyms (e.g., "polyester 100%" → "Polyester").

**Sample skeleton (minified):**
```json
{"name":"","brand":"","sku":"","price":{"value":0,"currency":"USD"},"images":[""],"sizes":[],"materials":[],"care_instructions":"","features":[]}
Note: It is acceptable to output null for any missing field instead of an error ###"""
    
    result = await optimize_prompt_parallel(prompt, [])
    
    # Display the results
    if result["contradiction_issues"]:
        print("Contradiction issues:")
        print(result["contradiction_issues"])
        print()
        
    print("Optimized prompt:")
    print(result["new_developer_message"])
    
# Run the example
await example_contradiction()
````

??? note "輸出"

    ```text
    Contradiction issues:
    There is a contradiction between the rule that says to short-circuit and output an error if *any* required field is missing ('{"error": "FIELD_MISSING:<field>"}') and the final note which states that it is acceptable to output null for any missing field instead of an error. Both behaviors cannot be followed simultaneously when a required field is missing.

    Optimized prompt:
    Quick-Start Card — Product Parser

    Goal  
    Digest raw HTML of an e-commerce product detail page and emit **concise, minified JSON** describing the item.

    **Required fields:**  
    name | brand | sku | price.value | price.currency | images[] | sizes[] | materials[] | care_instructions | features[]

    **Extraction priority:**  
    1. schema.org/JSON-LD blocks  
    2. <meta> & microdata tags  
    3. Visible DOM fallback (class hints: "product-name", "price")

    **Rules:**  
    - If *any* required field is missing, short-circuit and output: `{"error": "FIELD_MISSING:<field>"}`
    - Prices: Numeric with dot decimal; strip non-digits (e.g., "1.299,00 EUR" → 1299.00 + "EUR").
    - Deduplicate images differing only by query string. Keep ≤10 best-res.
    - Sizes: Ensure unit tag ("EU", "US") and ascending sort.
    - Materials: Title-case and collapse synonyms (e.g., "polyester 100%" → "Polyester").

    ## Output Format

    - Successful Output: Emit a minified JSON object with the following fields and types (order not enforced):
      - name: string
      - brand: string
      - sku: string
      - price: object with:
        - value: number
        - currency: string
      - images: array of string URLs
      - sizes: array of strings (each including a unit tag, e.g., "37 EU")
      - materials: array of strings
      - care_instructions: string
      - features: array of strings

    Example:
    ... (省略 5 行)
    ```

這示範系統怎麼偵測並解決關鍵矛盾，這些矛盾可能讓輸出不一致，或讓模型困惑。 

### 範例 2：修正 Prompt 與 Few-Shot 範例之間的不一致


```python
async def example_fewshot_fix():
    prompt = "Respond **only** with JSON using keys `city` (string) and `population` (integer)."
    
    messages = [
        {"role": "user", "content": "Largest US city?"},
        {"role": "assistant", "content": "New York City"},
        {"role": "user", "content": "Largest UK city?"},
        {"role": "assistant", "content": "{\"city\":\"London\",\"population\":9541000}"}
    ]
    
    
    print("Few-shot examples before optimization:")
    print(f"User: {messages[0]['content']}")
    print(f"Assistant: {messages[1]['content']}")
    print(f"User: {messages[2]['content']}")
    print(f"Assistant: {messages[3]['content']}")
    print()
    
    # Call the optimization API
    result = await optimize_prompt_parallel(prompt, [ChatMessage(**m) for m in messages])
    
    # Display the results
    if result["few_shot_contradiction_issues"]:
        print("Inconsistency found:", result["few_shot_contradiction_issues"])
        print()
    
    # Show the optimized few-shot examples
    optimized_messages = result["new_messages"]
    print("Few-shot examples after optimization:")
    print(f"User: {optimized_messages[0]['content']}")
    print(f"Assistant: {optimized_messages[1]['content']}")
    print(f"User: {optimized_messages[2]['content']}")
    print(f"Assistant: {optimized_messages[3]['content']}")
    
# Run the example
await example_fewshot_fix()
```

??? note "輸出"

    ```text
    Few-shot examples before optimization:
    User: Largest US city?
    Assistant: New York City
    User: Largest UK city?
    Assistant: {"city":"London","population":9541000}

    Inconsistency found: The response 'New York City' does not use JSON format and is missing the required keys `city` and `population` as stated in the rule 'Respond **only** with JSON using keys `city` (string) and `population` (integer).'

    Few-shot examples after optimization:
    User: Largest US city?
    Assistant: {"city":"New York City","population":8468000}
    User: Largest UK city?
    Assistant: {"city":"London","population":9541000}
    ```

這點特別重要，因為 few-shot 範例對模型的回應影響很大。如果範例不遵守所述規則，模型可能學會忽略規則、改去模仿範例。確保 prompt 指示和範例一致，優化系統就能做出更可靠的 prompt。

### 範例 3：釐清較長 Prompt 裡的格式

```python
async def example_format_issue():
    # A prompt with unclear or inconsistent formatting instructions
    prompt = """Task → Translate dense patent claims into 200-word lay summaries with a glossary.

Operating Steps:
1. Split the claim at semicolons, "wherein", or numbered sub-clauses.
2. For each chunk:
   a) Identify its purpose.
   b) Replace technical nouns with everyday analogies.
   c) Keep quantitative limits intact (e.g., "≥150 C").
3. Flag uncommon science terms with asterisks, and later define them.
4. Re-assemble into a flowing paragraph; do **not** broaden or narrow the claim’s scope.
5. Omit boilerplate if its removal does not alter legal meaning.

Output should follow a Markdown template:
- A summary section.
- A glossary section with the marked terms and their definitions.

Corner Cases:
- If the claim is over 5 kB, respond with CLAIM_TOO_LARGE.
- If claim text is already plain English, skip glossary and state no complex terms detected.

Remember: You are *not* providing legal advice—this is for internal comprehension only."""

    # Call the optimization API to check for format issues
    result = await optimize_prompt_parallel(prompt, [])

    # Display the results
    if result.get("format_issues"):
        print("Format issues found:", result["format_issues"])
        print()

    print("Optimized prompt:")
    print(result["new_developer_message"])

# Run the example
await example_format_issue()
```

??? note "輸出"

    ````text
    Format issues found: Output must follow a precise Markdown template, but the expected structure (headers, formatting) for the summary and glossary sections is not fully specified.
    Ambiguity if output should be a Markdown string or a structured object containing Markdown—data type of output is implicit.
    No explicit ordering instruction for the summary and glossary sections—potentially ambiguous.
    Word count limit (200 words) is mentioned for the summary but not for the glossary section—scope unclear.
    No specific format for CLAIM_TOO_LARGE error or for indicating 'no complex terms'—should these be Markdown or plaintext?

    Optimized prompt:
    Task → Translate dense patent claims into 200-word lay summaries with a glossary.

    Operating Steps:
    1. Split the claim at semicolons, "wherein", or numbered sub-clauses.
    2. For each chunk:
       a) Identify its purpose.
       b) Replace technical nouns with everyday analogies.
       c) Keep quantitative limits intact (e.g., ">=150 C").
    3. Flag uncommon science terms with asterisks, and later define them.
    4. Re-assemble into a flowing paragraph; do **not** broaden or narrow the claim’s scope.
    5. Omit boilerplate if its removal does not alter legal meaning.

    ## Output Format
    - All outputs must be provided as a Markdown string.
    - If the claim exceeds 5 kB, respond only with the text: `CLAIM_TOO_LARGE` (no Markdown formatting).
    - If the claim is already in plain English, output the following Markdown:
      
      ```markdown
      ## Summary
      <summary text>
      
      ## Glossary
      No complex terms detected.
      ```
    - Otherwise, follow this Markdown template:
      
      ```markdown
      ## Summary
      <Lay summary of the claim (max 200 words)>
      
      ## Glossary
      - *Term1*: Definition of Term1
      - *Term2*: Definition of Term2
    ... (省略 6 行)
    ````

這個範例突顯 format checker 怎麼找出並解決含糊的格式規範。原本的 prompt 要求輸出 Markdown，優化流程大幅改進了這些格式規範。

## 重點整理

- Prompt 常見的三類問題是指示矛盾、格式規範不明、和 few-shot 範例不一致，各用一個專職 agent 檢查。
- 檢查可以平行跑，改寫有相依關係，所以只在偵測到問題時才依序執行 rewriter。
- 好的 agent instructions 範圍窄、有步驟、術語有定義、寫明不該做什麼、輸出格式嚴格。
- Few-shot 範例影響力很大，和規則不一致時，模型會去模仿範例而不是遵守規則。
- 用 golden examples 搭配 Evals，可以量化地選模型和調 instructions。

## 練習

1. 在範例 1 的 prompt 裡再加一條跟原本衝突的指示，執行後看 contradiction checker 有沒有抓到。
2. 在範例 2 的 few-shot 範例裡故意改一個回應讓它違反規則，確認 few-shot checker 找得出來，且 rewriter 能修正。
3. 把 `optimize_prompt_parallel` 裡其中一個 checker 的模型換成別的，用你自己準備的幾組 golden pair 比較偵測結果有沒有變。
