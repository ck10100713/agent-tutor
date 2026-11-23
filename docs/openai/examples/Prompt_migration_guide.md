---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Prompt_migration_guide.ipynb
---

# Prompt 遷移指南

> 原文：[examples/Prompt_migration_guide.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Prompt_migration_guide.ipynb)



## 這篇在做什麼
把原本為舊模型寫的 prompt，改寫成適合 GPT-4.1 的版本。流程是先抽出所有 instruction，再讓 GPT-4.1 自己批評 prompt 哪裡模糊、矛盾，最後自動產生修訂版，並用 MT-Bench 子集測量改寫前後跟人類判斷的一致度。

## 學完你會
- 用模型列出 prompt 裡所有 instruction，檢查哪些不該是 instruction、哪些不清楚
- 讓 GPT-4.1 找出 prompt 的歧義、缺定義、衝突和缺漏 context，並據此自動產生新的 system prompt
- 用有人類標註的資料算出 LLM judge 和人類的一致度，比較改寫前後的差別

## 開跑前
需要安裝 `openai` Python 套件，並設定好 `OPENAI_API_KEY`。

GPT-4.1 這類較新的模型，在效能和遵循指令上是同級最佳。模型越聰明，原本為早期模型限制量身打造的 prompt 就越需要調整，才能讓它們在新一代模型上依然有效又清楚。

GPT‑4.1 這類模型很會照指示做事，但這種精準也表示，遇到不清楚或寫得不好的指示，它可能會**照字面**解讀，得到出乎意料或錯誤的結果。要發揮 GPT‑4.1 的完整潛力，必須修改 prompt，讓每一條指示都明確、沒有歧義，並且符合你想要的結果。

---

不清楚的指示範例：

- 有歧義：

> "Do not include irrelevant information."

問題：如果沒有明確定義什麼是「不相關」，GPT-4.1 可能不知道怎麼判斷。這可能讓它因為過度保守而漏掉重要細節，或是不小心放了太多細節。

- 改善後：

> "Only include facts directly related to the main topic (X). Exclude personal anecdotes, unrelated historical context, or side discussions."

---

**目標**：這個互動式 notebook 幫你把現有的 prompt（為其他模型寫的），依最佳實務改成清楚、沒有歧義、針對 GPT‑4.1 最佳化的版本。

**流程總覽**  
這個 notebook 的做法如下：

- [Step 1. 輸入你原本的 prompt](#step-1-input-your-original-prompt)  
- [Step 2. 找出 prompt 裡所有的指示](#step-2-identify-all-instructions-in-your-prompt)  
- [Step 3. 請 GPT-4.1 *批評* 這個 prompt](#step-3-ask-gpt-4-1-to-critique-the-prompt)  
- [Step 4. 自動產生修訂後的 system prompt](#step-4-auto-generate-a-revised-system-prompt)  
- [Step 5. 評估並迭代](#step-5-evaluate-and-iterate)  
- [Step 6.（選用）自動套用 GPT-4.1 最佳實務](#step-6-optional-automatically-apply-gpt-4-1-best-practices)

**前置條件**
- `openai` Python 套件和 `OPENAI_API_KEY`

```python
# !pip install openai pydantic tiktoken
```

```python
# Imports & API connection
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Any, Dict, Iterable, List, Optional
import tiktoken
import html
from html import escape  
import difflib
import sys

from IPython.display import display, HTML

try:
    from IPython.display import HTML, display
    _IN_IPYTHON = True
except ImportError:
    _IN_IPYTHON = False


client = OpenAI()

MODEL = "gpt-4.1"
```

下面是幾個 helper function，讓我們可以輕鬆檢視對 prompt 的分析和修改。

```python
_COLORS = {
    '+': ("#d2f5d6", "#22863a"),   # additions  (green)
    '-': ("#f8d7da", "#b31d28"),   # deletions  (red)
    '@': (None,      "#6f42c1"),   # hunk header (purple)
}

def _css(**rules: str) -> str:
    """Convert kwargs to a CSS string (snake_case → kebab-case)."""
    return ";".join(f"{k.replace('_', '-')}: {v}" for k, v in rules.items())

def _render(html_str: str) -> None:
    """Render inside Jupyter if available, else print to stdout."""
    try:
        display  # type: ignore[name-defined]
        from IPython.display import HTML  # noqa: WPS433
        display(HTML(html_str))
    except NameError:
        print(html_str, flush=True)

# ---------- diff helpers ------------------------------------------------------

def _style(line: str) -> str:
    """Wrap a diff line in a <span> with optional colors."""
    bg, fg = _COLORS.get(line[:1], (None, None))
    css = ";".join(s for s in (f"background:{bg}" if bg else "",
                               f"color:{fg}" if fg else "") if s)
    return f'<span style="{css}">{html.escape(line)}</span>'

def _wrap(lines: Iterable[str]) -> str:
    body = "<br>".join(lines)
    return (
        "<details>"
        "<summary>🕵️‍♂️ Critique & Diff (click to expand)</summary>"
        f'<div style="font-family:monospace;white-space:pre;">{body}</div>'
        "</details>"
    )

def show_critique_and_diff(old: str, new: str) -> str:
    """Display & return a GitHub-style HTML diff between *old* and *new*."""
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(),
                                fromfile="old", tofile="new", lineterm="")
    html_block = _wrap(map(_style, diff))
    _render(html_block)
    return html_block

# ---------- “card” helpers ----------------------------------------------------

CARD    = _css(background="#f8f9fa", border_radius="8px", padding="18px 22px",
               margin_bottom="18px", border="1px solid #e0e0e0",
               box_shadow="0 1px 4px #0001")
TITLE   = _css(font_weight="600", font_size="1.1em", color="#2d3748",
               margin_bottom="6px")
LABEL   = _css(color="#718096", font_size="0.95em", font_weight="500",
               margin_right="6px")
EXTRACT = _css(font_family="monospace", background="#f1f5f9", padding="7px 10px",
               border_radius="5px", display="block", margin_top="3px",
               white_space="pre-wrap", color="#1a202c")

def display_cards(
    items: Iterable[Any],
    *,
    title_attr: str,
    field_labels: Optional[Dict[str, str]] = None,
    card_title_prefix: str = "Item",
) -> None:
    """Render objects as HTML “cards” (or plaintext when not in IPython)."""
    items = list(items)
    if not items:
        _render("<em>No data to display.</em>")
        return

    # auto-derive field labels if none supplied
    if field_labels is None:
        sample = items[0]
        field_labels = {
            a: a.replace("_", " ").title()
            for a in dir(sample)
            if not a.startswith("_")
            and not callable(getattr(sample, a))
            and a != title_attr
        }

    cards = []
    for idx, obj in enumerate(items, 1):
        title_html = html.escape(str(getattr(obj, title_attr, "<missing title>")))
        rows = [f'<div style="{TITLE}">{card_title_prefix} {idx}: {title_html}</div>']

        for attr, label in field_labels.items():
            value = getattr(obj, attr, None)
            if value is None:
                continue
            rows.append(
                f'<div><span style="{LABEL}">{html.escape(label)}:</span>'
                f'<span style="{EXTRACT}">{html.escape(str(value))}</span></div>'
            )

        cards.append(f'<div style="{CARD}">{"".join(rows)}</div>')

    _render("\n".join(cards))
```

## Step 1. 輸入你原本的 prompt
先把你現有的 prompt 清楚地放在三個引號（`"""`）之間。這個 prompt 會是改善的基準。

這個範例用的是 LLM-as-a-Judge 的 system prompt，出自這篇 [論文](https://arxiv.org/pdf/2306.05685)。

```python
original_prompt = """
[System]
Please act as an impartial judge and evaluate the quality of the responses provided by two
AI assistants to the user question displayed below. You should choose the assistant that
follows the user’s instructions and answers the user’s question better. Your evaluation
should consider factors such as the helpfulness, relevance, accuracy, depth, creativity,
and level of detail of their responses. Begin your evaluation by comparing the two
responses and provide a short explanation. Avoid any position biases and ensure that the
order in which the responses were presented does not influence your decision. Do not allow
the length of the responses to influence your evaluation. Do not favor certain names of
the assistants. Be as objective as possible. After providing your explanation, output your
final verdict by strictly following this format: "[[A]]" if assistant A is better, "[[B]]"
if assistant B is better, and "[[C]]" for a tie.

[User Question]
{question}

[The Start of Assistant A’s Answer]
{answer_a}
[The End of Assistant A’s Answer]

[The Start of Assistant B’s Answer]
{answer_b}
[The End of Assistant B’s Answer]
"""

encoding = tiktoken.encoding_for_model("gpt-4")
num_tokens = len(encoding.encode(original_prompt))
print("Original prompt length:", num_tokens, "tokens")
```

??? note "輸出"

    ```text
    Original prompt length: 243 tokens
    ```

## Step 2. 找出 prompt 裡所有的指示
這一段我們會抽出 LLM 在 system prompt 裡辨識出的每一條 INSTRUCTION。這樣你可以檢查清單，找出不該算指示的句子，並釐清含糊的地方。

仔細確認每條列出的指示都正確，而且值得保留。

```python
class Instruction(BaseModel):
    instruction_title: str = Field(description="A 2-8 word title of the instruction that the LLM has to follow.")
    extracted_instruction: str = Field(description="The exact text that was extracted from the system prompt that the instruction is derived from.")

class InstructionList(BaseModel):
    instructions: list[Instruction] = Field(description="A list of instructions and their corresponding extracted text that the LLM has to follow.")


EXTRACT_INSTRUCTIONS_SYSTEM_PROMPT = """
## Role & Objective
You are an **Instruction-Extraction Assistant**.  
Your job is to read a System Prompt provided by the user and distill the **mandatory instructions** the target LLM must obey.

## Instructions
1. **Identify Mandatory Instructions**  
   • Locate every instruction in the System Prompt that the LLM is explicitly required to follow.  
   • Ignore suggestions, best-practice tips, or optional guidance.

2. **Generate Rules**  
   • Re-express each mandatory instruction as a clear, concise rule.
   • Provide the extracted text that the instruction is derived from.
   • Each rule must be standalone and imperative.

## Output Format
Return a json object with a list of instructions which contains an instruction_title and their corresponding extracted text that the LLM has to follow. Do not include any other text or comments.

## Constraints
- Include **only** rules that the System Prompt explicitly enforces.  
- Omit any guidance that is merely encouraged, implied, or optional.  
"""

response = client.responses.parse(
    model=MODEL,
    input="SYSTEM_PROMPT TO ANALYZE: " + original_prompt,
    instructions=EXTRACT_INSTRUCTIONS_SYSTEM_PROMPT,
    temperature=0.0,
    text_format=InstructionList,
)

instructions_list = response.output_parsed
```

```python
display_cards(
    instructions_list.instructions,
    title_attr="instruction_title",
    field_labels={"extracted_instruction": "Extracted Text"},
    card_title_prefix="Instruction"
)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

看看模型把你 prompt 的哪些部分當成指示，很有幫助。指示就是我們用自然語言「寫程式」控制模型的方式，所以務必確保它們清楚、精確、正確。

## Step 3. 請 GPT-4.1 *批評* 這個 prompt
接下來，由 GPT‑4.1 自己批評原本的 prompt，特別找出可能造成混淆或錯誤的地方：

- 歧義：可以有多種解讀的措辭。

- 缺少定義：沒有清楚定義的標籤或用語，可能讓模型自己推測或猜它的意思。

- 指示衝突：互相矛盾或重疊的規則或條件。

- 缺少 context 或假設：必要的資訊或 context 沒有明說。

批評的輸出會整理得很清楚，標出具體問題和可執行的改善建議。

模型非常擅長**找出 prompt 裡它覺得含糊或混淆的地方**。解決這些問題之後，我們就能調整指示，讓模型更容易看懂、更有效。

````python
class CritiqueIssue(BaseModel):
    issue: str
    snippet: str
    explanation: str
    suggestion: str

class CritiqueIssues(BaseModel):
    issues: List[CritiqueIssue] = Field(..., min_length=1, max_length=6)
    
CRITIQUE_SYSTEM_PROMPT = """
## Role & Objective  
You are a **Prompt-Critique Assistant**.
Examine a user-supplied LLM prompt (targeting GPT-4.1 or compatible) and surface any weaknesses.

## Instructions
Check for the following issues:
- Ambiguity: Could any wording be interpreted in more than one way?
- Lacking Definitions: Are there any class labels, terms, or concepts that are not defined that might be misinterpreted by an LLM?
- Conflicting, missing, or vague instructions: Are directions incomplete or contradictory?
- Unstated assumptions: Does the prompt assume the model has to be able to do something that is not explicitly stated?

## Do **NOT** list issues of the following types:
- Invent new instructions, tool calls, or external information. You do not know what tools need to be added that are missing.
- Issues that you are not sure about.

## Output Format  
Return a JSON **array** (not an object) with 1-6 items, each following this schema:

```json
{
  "issue":      "<1-6 word label>",
  "snippet":    "<≤50-word excerpt>",
  "explanation":"<Why it matters>",
  "suggestion": "<Actionable fix>"
}
Return a JSON array of these objects. If the prompt is already clear, complete, and effective, return an empty list: `[]`.
"""

CRITIQUE_USER_PROMPT = f"""
Evaluate the following prompt for clarity, completeness, and effectiveness:
###
{original_prompt}
###
Return your critique using the specified JSON format only.
"""
````

```python
response = client.responses.parse(
    model=MODEL,
    input=[
        {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
        {"role": "user", "content": CRITIQUE_USER_PROMPT},
    ],
    temperature=0.0,
    text_format=CritiqueIssues,
)

critique = response.output_parsed
```

```python
display_cards(
    critique.issues,
    title_attr="issue",
    field_labels={
        "snippet": "Snippet",
        "explanation": "Explanation",
        "suggestion": "Suggestion"
    },
    card_title_prefix="Issue"
)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

```python
# Create a string of the issues
issues_str = "\n".join(
    f"Issue: {issue.issue}\nSnippet: {issue.snippet}\nExplanation: {issue.explanation}\nSuggestion: {issue.suggestion}\n"
    for issue in critique.issues
)

print(issues_str)
```

??? note "輸出"

    ```text
    Issue: Ambiguous evaluation criteria
    Snippet: consider factors such as the helpfulness, relevance, accuracy, depth, creativity, and level of detail
    Explanation: The prompt lists several evaluation factors but does not define them or explain how to weigh them. This could lead to inconsistent or subjective judgments.
    Suggestion: Provide clear definitions for each criterion and specify if any should be prioritized over others.

    Issue: Unclear handling of ties
    Snippet: "[[C]]" for a tie
    Explanation: The prompt allows for a tie verdict but does not specify under what circumstances a tie is appropriate, which may lead to inconsistent use.
    Suggestion: Clarify when a tie should be chosen, e.g., if both responses are equally strong across all criteria.

    Issue: Potential ambiguity in 'objectivity'
    Snippet: Be as objective as possible.
    Explanation: The prompt asks for objectivity but does not specify what constitutes objectivity in this context, especially given the subjective nature of some criteria.
    Suggestion: Define what is meant by objectivity in this evaluation context, possibly by referencing adherence to the listed criteria.
    ```

檢視問題清單：
- 如果你滿意，就繼續下一步 #4。 
- 如果你覺得有些問題不相關，把上面的文字複製到下一個 cell，並刪掉那些問題。這個例子裡三個問題都合理，所以跳過這一步。

```python
# issues_str = """
# PLACEHOLDER FOR ISSUES YOU WANT TO CORRECT, DO NOT RUN THIS CELL UNLESS YOU HAVE COPY-PASTED THE ISSUES FROM ABOVE
# """
```

## Step 4. 自動產生修訂後的 *system* prompt
現在把批評結果餵回 GPT‑4.1，請它產生原 prompt 的改善版本，可以直接放進 `system` role 的訊息。

```python
REVISE_SYSTEM_PROMPT = """
## Role & Objective  
Revise the user’s original prompt to resolve most of the listed issues, while preserving the original wording and structure as much as possible.

## Instructions
1. Carefully review the original prompt and the list of issues.
2. Apply targeted edits directly addressing the listed issues. The edits should be as minimal as possible while still addressing the issue.
3. Do not introduce new content or make assumptions beyond the provided information.
4. Maintain the original structure and format of the prompt.

## Output Format
Return only the fully revised prompt. Do not include commentary, summaries, or code fences.
"""

REVISE_USER_PROMPT = f"""
Here is the original prompt:
---
{original_prompt}
---

Here are the issues to fix:
{issues_str}

Please return **only** the fully revised prompt. Do not include commentary, summaries, or explanations.
"""
```

```python
revised_response = client.responses.create(
    model=MODEL,
    input=REVISE_USER_PROMPT,
    instructions=REVISE_SYSTEM_PROMPT,
    temperature=0.0
)

revised_prompt = revised_response.output_text
print("\n🔄 Revised prompt:\n------------------")
print(revised_response.output_text)
```

??? note "輸出"

    ```text

    🔄 Revised prompt:
    ------------------
    [System]
    Please act as an impartial judge and evaluate the quality of the responses provided by two AI assistants to the user question displayed below. You should choose the assistant that follows the user’s instructions and answers the user’s question better. Your evaluation should be based on the following criteria:

    - Helpfulness: The extent to which the response addresses the user’s needs and provides useful information.
    - Relevance: How closely the response pertains to the user’s question and instructions.
    - Accuracy: The correctness and factual reliability of the information provided.
    - Depth: The level of insight, explanation, or reasoning demonstrated in the response.
    - Creativity: The originality or resourcefulness shown in addressing the question, where appropriate.
    - Level of Detail: The thoroughness and completeness of the response.

    All criteria should be considered equally unless the user’s instructions indicate otherwise. 

    Begin your evaluation by comparing the two responses according to these criteria and provide a short explanation. Remain impartial by avoiding any position biases and ensuring that the order in which the responses were presented does not influence your decision. Do not allow the length of the responses or the names of the assistants to influence your evaluation.

    Be as objective as possible by strictly adhering to the defined criteria above and basing your judgment solely on how well each response meets them.

    After providing your explanation, output your final verdict by strictly following this format: "[[A]]" if assistant A is better, "[[B]]" if assistant B is better, and "[[C]]" for a tie. Choose "[[C]]" only if both responses are equally strong across all criteria.

    [User Question]
    {question}

    [The Start of Assistant A’s Answer]
    {answer_a}
    [The End of Assistant A’s Answer]

    [The Start of Assistant B’s Answer]
    {answer_b}
    [The End of Assistant B’s Answer]
    ```

我們用並排比較的方式看修改，標出改善版和精修版的差異：

```python
show_critique_and_diff(original_prompt, revised_prompt)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## Step 5. 評估並迭代
最後，用下面的方式評估你精修後的 prompt：

- 用有代表性的評估範例或資料來測試。

- 分析回應，確認有達到想要的結果。

- 如果還需要改善，就回頭重複前面的步驟。

持續測試和精修，才能確保 prompt 每次都達到預期的結果。

### 目前的範例

我們來評估這次的 prompt 遷移，在這個 judge 的任務上到底有沒有進步。原本的 prompt 出自這篇[論文](https://arxiv.org/pdf/2306.05685)，用來擔任兩個助理答案之間的評審。方便的是，論文提供了一組人類標註的 ground truth，所以我們可以衡量 LLM judge 跟人類判斷一致的頻率。

因此，我們的成功指標是：遷移後的 prompt 產生的判斷，跟人類評估的吻合程度，相較於 baseline prompt 產生的判斷如何。補充一下，我們用的 benchmark 是 MT-Bench 的子集，裡面是多輪對話。這個範例評估 200 筆對話資料，每筆比較不同模型組合的表現。



在我們的評估子集上，一個有用的參考基準是人與人之間的一致度，因為每段對話都由多位標註者評分。人類對於哪個助理的答案比較好，也不一定意見一致，所以我們也不會期待 judge 能達到完美一致。第 1 輪（不含平手）人類彼此一致的比例是 81%，第 2 輪是 76%。

![Graph 3 for Model Agreement](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/prompt_migrator_fig.png)

對照遷移前的模型：GPT-4（論文用的）跟人類判斷的一致度，第 1 輪是 74%，第 2 輪是 71%，不算差，但還是低於人類之間的上限。換成 GPT-4.1（用同一個 prompt）後，一致度提高：第 1 輪 77%，第 2 輪 72%。最後，針對 GPT-4.1 遷移並調整 prompt 之後，一致度再往上，第 1 輪到 80%，第 2 輪 72%，非常接近人類標註者之間的一致程度。

整體來看，prompt 遷移加上升級到更強的模型，都能提高這個範例任務的一致度。現在換你用自己的 prompt 試試！

## Step 6.（選用）自動套用 GPT‑4.1 最佳實務

這一步會自動套用 GPT-4.1 最佳實務來改善你原本的 prompt。我們強烈建議你手動檢查這些修改，再決定要不要保留。

可以參考 [4.1 Prompting Guide](https://cookbook.openai.com/examples/gpt4-1_prompting_guide)。

```python
BEST_PRACTICES_SYSTEM_PROMPT = """
## Task
Your task is to take a **Baseline Prompt** (provided by the user) and output a **Revised Prompt** that keeps the original wording and order as intact as possible **while surgically inserting improvements that follow the “GPT‑4.1 Best Practices” reference**.

## How to Edit
1. **Keep original text** — Only remove something if it directly goes against a best practice. Otherwise, keep the wording, order, and examples as they are.
2. **Add best practices only when clearly helpful.** If a guideline doesn’t fit the prompt or its use case (e.g., diff‑format guidance on a non‑coding prompt), just leave that part of the prompt unchanged.
3. **Where to add improvements** (use Markdown `#` headings):
   - At the very top, add *Agentic Reminders* (like Persistence, Tool-calling, or Planning) — only if relevant. Don’t add these if the prompt doesn’t require agentic behavior (agentic means prompts that involve planning or running tools for a while).
   - When adding sections, follow this order if possible. If some sections do not make sense, don't add them:
     1. `# Role & Objective`  
        - State who the model is supposed to be (the role) and what its main goal is.
     2. `# Instructions`  
        - List the steps, rules, or actions the model should follow to complete the task.
     3. *(Any sub-sections)*  
        - Include any extra sections such as sub-instructions, notes or guidelines already in the prompt that don’t fit into the main categories.
     4. `# Reasoning Steps`  
        - Explain the step-by-step thinking or logic the model should use when working through the task.
     5. `# Output Format`  
        - Describe exactly how the answer should be structured or formatted (e.g., what sections to include, how to label things, or what style to use).
     6. `# Examples`  
        - Provide sample questions and answers or sample outputs to show the model what a good response looks like.
     7. `# Context`  
        - Supply any background information, retrieved context, or extra details that help the model understand the task better.
   - Don’t introduce new sections that don’t exist in the Baseline Prompt. For example, if there’s no `# Examples` or no `# Context` section, don’t add one.
4. If the prompt is for long context analysis or long tool use, repeat key Agentic Reminders, Important Reminders and Output Format points at the end.
5. If there are class labels, evaluation criterias or key concepts, add a definition to each to define them concretely.
5. Add a chain-of-thought trigger at the end of main instructions (like “Think step by step...”), unless one is already there or it would be repetitive.
6. For prompts involving tools or sample phrases, add Failure-mode bullets:
   - “If you don’t have enough info to use a tool, ask the user first.”
   - “Vary sample phrases to avoid repetition.”
7. Match the original tone (formal or casual) in anything you add.
8. **Only output the full Revised Prompt** — no explanations, comments, or diffs. Do not output "keep the original...", you need to fully output the prompt, no shortcuts.
9. Do not delete any sections or parts that are useful and add value to the prompt and doesn't go against the best practices.
10. **Self-check before sending:** Make sure there are no typos, duplicated lines, missing headings, or missed steps.


## GPT‑4.1 Best Practices Reference  
1. **Persistence reminder**: Explicitly instructs the model to continue working until the user's request is fully resolved, ensuring the model does not stop early.
2. **Tool‑calling reminder**: Clearly tells the model to use available tools or functions instead of making assumptions or guesses, which reduces hallucinations.
3. **Planning reminder**: Directs the model to create a step‑by‑step plan and reflect before and after tool calls, leading to more accurate and thoughtful output.
4. **Scaffold structure**: Requires a consistent and predictable heading order (e.g., Role, Instructions, Output Format) to make prompts easier to maintain.
5. **Instruction placement (long context)**: Ensures that key instructions are duplicated or placed strategically so they remain visible and effective in very long prompts.
6. **Chain‑of‑thought trigger**: Adds a phrase that encourages the model to reason step by step, which improves logical and thorough responses.
7. **Instruction‑conflict hygiene**: Checks for and removes any contradictory instructions, ensuring that the most recent or relevant rule takes precedence.
8. **Failure‑mode mitigations**: Adds safeguards against common errors, such as making empty tool calls or repeating phrases, to improve reliability.
9. **Diff / code‑edit format**: Specifies a robust, line‑number‑free diff or code‑edit style for output, making changes clear and easy to apply.
10. **Label Definitions**: Defines all the key labels or terms that are used in the prompt so that the model knows what they mean.
"""
```

```python
best_practices_response = client.responses.create(
    model="o3",
    input="BASELINE_PROMPT: " + revised_prompt,
    instructions=BEST_PRACTICES_SYSTEM_PROMPT,
    reasoning={"effort": "high"}
)

improved_prompt = best_practices_response.output_text
print("\nImproved prompt:\n")
print(improved_prompt)
```

??? note "輸出"

    ```text

    Improved prompt:

    # Role & Objective
    You are an impartial judge. Your goal is to determine which of two AI assistant answers better fulfills the user’s request.

    # Instructions  
    Follow the steps below exactly and remain strictly neutral:

    1. Read the User Question and both assistant answers in full.  
    2. Evaluate each answer against **all** six criteria, treating them with equal weight unless the user explicitly states otherwise:
       • Helpfulness – Does the response address the user’s needs and provide useful information?  
       • Relevance – How closely does the response pertain to the user’s question and instructions?  
       • Accuracy – Is the information correct and factually reliable?  
       • Depth – Does the answer show insight, explanation, or reasoning?  
       • Creativity – Is the approach original or resourceful when appropriate?  
       • Level of Detail – Is the response thorough and complete?  
    3. Stay impartial:  
       • Ignore the order in which the answers appear.  
       • Ignore the length of each answer.  
       • Ignore the assistants’ names.  
    4. Make your decision solely on how well each response meets the criteria above.  
    5. After your analysis, produce a final verdict using the exact format in the Output Format section.

    # Reasoning Steps
    Think step by step:
    1. For each criterion, briefly note strengths and weaknesses for Assistant A.  
    2. Repeat for Assistant B.  
    3. Compare the two sets of notes criterion by criterion.  
    4. Decide which answer is overall superior, or declare a tie if both are equally strong across all criteria.

    # Output Format
    First provide a short, objective explanation (1–3 concise paragraphs).  
    Then on a new line output only one of the following tokens (without quotes or extra text):
    • [[A]]  – if Assistant A is better  
    • [[B]]  – if Assistant B is better  
    • [[C]]  – if it is a tie  

    # Context (inserted at runtime)
    [User Question]  
    ... (省略 9 行)
    ```

```python
show_critique_and_diff(revised_prompt, improved_prompt)
```

??? note "輸出"

    ```text
    <IPython.core.display.HTML object>
    ```

## 重點整理
- 新模型會更精準地照字面執行指示，舊 prompt 裡含糊的句子可能造成意外結果
- 先抽出 instruction 清單檢查，因為指示就是你用自然語言寫的「程式」
- 模型很會指出 prompt 裡自己覺得模糊、缺定義或互相衝突的地方，可以拿來當批評者
- 改寫後一定要用有 ground truth 的資料評估，不能只憑感覺
- 自動套用最佳實務的結果，要自己手動檢查再決定保不保留

## 練習
1. 把 Step 1 的 prompt 換成你自己專案裡的一段 system prompt，跑一遍 Step 2，看模型抽出的 instruction 有沒有你沒預期的。
2. 在 Step 3 的批評結果裡，刪掉一個你覺得不相關的問題再進 Step 4，比較產生的 prompt 有什麼差別。
3. 自己挑 10 筆有人類標註的資料，分別用原本和遷移後的 prompt 跑一遍，算出各自跟人類的一致度。
