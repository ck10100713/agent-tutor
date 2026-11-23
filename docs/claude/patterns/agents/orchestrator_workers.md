---
translated: true
source: patterns/agents/orchestrator_workers.ipynb
---
# Orchestrator-workers

> 原文：[patterns/agents/orchestrator_workers.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/orchestrator_workers.ipynb)

由一個中央 LLM 動態把任務分派給 worker LLM，再整合它們的結果。

## 這篇在做什麼

這篇實作 orchestrator-workers 模式：一個 orchestrator LLM 先分析任務，在執行時決定要拆成哪些子任務，再交給各個 worker LLM 去做。範例是替一個產品產生多種風格的行銷文案。

## 學完你會

- 寫出會輸出 XML 子任務清單的 orchestrator prompt，並用 `parse_tasks()` 解析
- 實作 `FlexibleOrchestrator`，讓 worker 同時拿到原始任務和自己的子任務說明
- 判斷什麼情況該用這個模式，什麼情況改用單純的平行化

## 開跑前

需要 Anthropic API key，設成環境變數：`export ANTHROPIC_API_KEY='your-key'`。在 Colab 上用 Secrets 設定，或在 cell 裡 `os.environ["ANTHROPIC_API_KEY"] = ...`。

## 簡介

你有沒有遇過同一個任務需要多個觀點，卻無法事先預測哪些觀點最有價值？orchestrator-workers 模式的解法是：讓一個中央 LLM 分析每個獨一無二的任務，動態決定最適合交給專門 worker LLM 的子任務。

傳統做法不是要手動 prompt 很多次，就是用寫死的平行化，不管情境都產生同樣的變化。

這個做法裡，orchestrator LLM 分析任務，判斷這個特定案例最有價值的變化是哪些，再交給 worker LLM 去產生每個變化。

### 你會建出什麼

一個系統，輸入產品描述的需求，然後：

1. 分析哪些類型的行銷文案有價值
2. 動態產生給 worker 的專門任務描述
3. 產生針對不同受眾最佳化的多個內容版本
4. 回傳所有 worker 協調後的結果

### 前置條件

- Python 3.9 以上
- 把 Anthropic API key 設成環境變數：`export ANTHROPIC_API_KEY='your-key'`
- 對 prompt engineering 有基本了解
- 熟悉 Python class 和 type hint


### 什麼時候用這個 workflow

這個 workflow 適合你無法事先預測需要哪些子任務的複雜任務。跟單純平行化最大的差別是彈性：子任務不是預先定義的，而是由 orchestrator 根據特定輸入決定。

**適合用在：**

- 任務需要多種不同的做法或觀點
- 最佳子任務取決於特定輸入
- 需要比較不同策略或風格

**不適合用在：**

- 簡單、單一輸出的任務（徒增複雜度）
- 延遲很關鍵（多次 LLM 呼叫會增加負擔）
- 子任務可預測、能預先定義（用比較簡單的平行化）

## 運作方式

orchestrator-workers 模式分兩個階段：

1. **分析與規劃階段**：orchestrator LLM 收到任務和 context，分析哪些做法有價值，並以 XML 格式產生結構化的子任務描述。

2. **執行階段**：每個 worker LLM 會收到：
   - 原始任務，作為 context
   - 它自己的子任務類型和描述
   - 任何額外提供的 context

orchestrator *在執行時*才決定要建立哪些子任務，所以比預先定義的平行 workflow 更能適應。

## 設定

### 安裝
```bash
pip install anthropic
```

### Helper 函式
這個範例用 `util.py` 的 helper 函式做 LLM 呼叫和解析 XML 回應：

- `llm_call(prompt, system_prompt="", model="claude-sonnet-5-5")`：把 prompt 送給 Claude，回傳文字回應
- `extract_xml(text, tag)`：用 regex 取出 XML tag 裡的內容

這些工具處理 API 認證（從環境變數讀 `ANTHROPIC_API_KEY`），並為 orchestrator-workers 模式提供簡單的介面。完整實作可看 [util.py](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/util.py)。

## 實作

`FlexibleOrchestrator` class 協調這個兩階段 workflow：

**關鍵設計決策：**
- prompt 是模板，接受執行時變數（`task`、`context`）以保持彈性
- 用 XML 做結構化輸出的解析（可靠，對 language model 友善）
- worker 同時收到原始任務和自己的特定指示，context 更完整
- 錯誤處理會驗證 worker 回傳的不是空回應

實作包含：
- `parse_tasks()`：把 orchestrator 的 XML 輸出解析成結構化的 task dictionary
- `FlexibleOrchestrator.process()`：主要協調邏輯，先呼叫 orchestrator，再呼叫 worker
- 回應驗證，抓出並處理 worker 的空輸出

```python
from util import extract_xml, llm_call

# Model configuration
MODEL = "claude-sonnet-5-5"  # Fast, capable model for both orchestrator and workers


def parse_tasks(tasks_xml: str) -> list[dict]:
    """Parse XML tasks into a list of task dictionaries."""
    tasks = []
    current_task = {}

    for line in tasks_xml.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("<task>"):
            current_task = {}
        elif line.startswith("<type>"):
            current_task["type"] = line[6:-7].strip()
        elif line.startswith("<description>"):
            current_task["description"] = line[12:-13].strip()
        elif line.startswith("</task>"):
            if "description" in current_task:
                if "type" not in current_task:
                    current_task["type"] = "default"
                tasks.append(current_task)

    return tasks


class FlexibleOrchestrator:
    """Break down tasks and run them in parallel using worker LLMs."""

    def __init__(
        self,
        orchestrator_prompt: str,
        worker_prompt: str,
        model: str = MODEL,
    ):
        """Initialize with prompt templates and model selection."""
        self.orchestrator_prompt = orchestrator_prompt
        self.worker_prompt = worker_prompt
        self.model = model

    def _format_prompt(self, template: str, **kwargs) -> str:
        """Format a prompt template with variables."""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing required prompt variable: {e}") from e

    def process(self, task: str, context: dict | None = None) -> dict:
        """Process task by breaking it down and running subtasks in parallel."""
        context = context or {}

        # Step 1: Get orchestrator response
        orchestrator_input = self._format_prompt(self.orchestrator_prompt, task=task, **context)
        orchestrator_response = llm_call(orchestrator_input, model=self.model)

        # Parse orchestrator response
        analysis = extract_xml(orchestrator_response, "analysis")
        tasks_xml = extract_xml(orchestrator_response, "tasks")
        tasks = parse_tasks(tasks_xml)

        print("\n" + "=" * 80)
        print("ORCHESTRATOR ANALYSIS")
        print("=" * 80)
        print(f"\n{analysis}\n")

        print("\n" + "=" * 80)
        print(f"IDENTIFIED {len(tasks)} APPROACHES")
        print("=" * 80)
        for i, task_info in enumerate(tasks, 1):
            print(f"\n{i}. {task_info['type'].upper()}")
            print(f"   {task_info['description']}")

        print("\n" + "=" * 80)
        print("GENERATING CONTENT")
        print("=" * 80 + "\n")

        # Step 2: Process each task
        worker_results = []
        for i, task_info in enumerate(tasks, 1):
            print(f"[{i}/{len(tasks)}] Processing: {task_info['type']}...")

            worker_input = self._format_prompt(
                self.worker_prompt,
                original_task=task,
                task_type=task_info["type"],
                task_description=task_info["description"],
                **context,
            )

            worker_response = llm_call(worker_input, model=self.model)
            worker_content = extract_xml(worker_response, "response")

            # Validate worker response - handle empty outputs
            if not worker_content or not worker_content.strip():
                print(f"⚠️  Warning: Worker '{task_info['type']}' returned no content")
                worker_content = f"[Error: Worker '{task_info['type']}' failed to generate content]"

            worker_results.append(
                {
                    "type": task_info["type"],
                    "description": task_info["description"],
                    "result": worker_content,
                }
            )

        # Display results
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        for i, result in enumerate(worker_results, 1):
            print(f"\n{'-' * 80}")
            print(f"Approach {i}: {result['type'].upper()}")
            print(f"{'-' * 80}")
            print(f"\n{result['result']}\n")

        return {
            "analysis": analysis,
            "worker_results": worker_results,
        }
```

## 範例情境：產生行銷文案變化

來看 orchestrator-workers 模式的實際範例：為一個產品產生多種風格的行銷文案。

**為什麼這個例子很適合說明這個模式：**
- 不同產品適合不同的行銷角度
- 「最好」的變化取決於特定的產品特色和目標受眾
- orchestrator 能根據輸入調整策略，而不是用固定模板

**Prompt 設計重點：**
- orchestrator prompt 要求 2-3 種做法，並提供 XML 結構的指引
- worker prompt 給 worker 完整的 context（原始任務、它的風格和準則）
- 兩個 prompt 都用清楚的 XML 格式確保解析可靠

```python
ORCHESTRATOR_PROMPT = """
Analyze this task and break it down into 2-3 distinct approaches:

Task: {task}

Return your response in this format:

<analysis>
Explain your understanding of the task and which variations would be valuable.
Focus on how each approach serves different aspects of the task.
</analysis>

<tasks>
    <task>
    <type>formal</type>
    <description>Write a precise, technical version that emphasizes specifications</description>
    </task>
    <task>
    <type>conversational</type>
    <description>Write an engaging, friendly version that connects with readers</description>
    </task>
</tasks>
"""

WORKER_PROMPT = """
Generate content based on:
Task: {original_task}
Style: {task_type}
Guidelines: {task_description}

Return your response in this format:

<response>
Your content here, maintaining the specified style and fully addressing requirements.
</response>
"""


orchestrator = FlexibleOrchestrator(
    orchestrator_prompt=ORCHESTRATOR_PROMPT,
    worker_prompt=WORKER_PROMPT,
)

results = orchestrator.process(
    task="Write a product description for a new eco-friendly water bottle",
    context={
        "target_audience": "environmentally conscious millennials",
        "key_features": ["plastic-free", "insulated", "lifetime warranty"],
    },
)
```

??? note "輸出"

    ```text

    ================================================================================
    ORCHESTRATOR ANALYSIS
    ================================================================================


    This task requires creating marketing copy for an eco-friendly water bottle. The core challenge is balancing product information with persuasive messaging while highlighting the environmental benefits. Different approaches would serve distinct marketing channels and audience segments:

    1. A **feature-focused technical approach** would appeal to detail-oriented consumers who make purchasing decisions based on specifications, materials, and measurable environmental impact. This serves e-commerce listings and comparison shopping.

    2. A **lifestyle-oriented emotional approach** would connect with values-driven consumers through storytelling and aspirational messaging, emphasizing how the product fits into an eco-conscious lifestyle. This serves social media and brand-building content.

    3. A **benefit-driven practical approach** would focus on solving everyday problems while weaving in sustainability advantages, appealing to mainstream consumers who want both functionality and environmental responsibility. This serves broad retail contexts.

    Each approach addresses the "eco-friendly" aspect differently—through data, values, or practical advantages—making them valuable for different marketing contexts.



    ================================================================================
    IDENTIFIED 3 APPROACHES
    ================================================================================

    1. TECHNICAL-SPECIFICATIONS
       >Write a detailed, feature-focused description emphasizing materials, construction, environmental certifications, and measurable sustainability metrics (recyclability percentages, carbon footprint reduction, etc.)<

    2. LIFESTYLE-EMOTIONAL
       >Write an inspirational, story-driven description that connects the product to environmental values, personal identity, and the broader movement toward sustainable living<

    3. BENEFIT-PRACTICAL
       >Write a problem-solution focused description highlighting everyday usability benefits (temperature retention, durability, convenience) while naturally integrating eco-friendly advantages<

    ================================================================================
    GENERATING CONTENT
    ================================================================================

    [1/3] Processing: technical-specifications...
    [2/3] Processing: lifestyle-emotional...
    [3/3] Processing: benefit-practical...

    ================================================================================
    ... (省略 152 行)
    ```

## 總結

你已經實作了一個 orchestrator-workers 模式，它會依特定輸入動態調整任務拆解。這個模式產生了多個行銷文案變化，各自針對不同的受眾和情境，而你不用事先定義這些變化應該是什麼。

### 重點

**模式的好處：**
- **適應性**：orchestrator 為每個獨特輸入決定最佳做法
- **彈性**：改 prompt 就能套用到不同領域
- **結構化協調**：用 XML 溝通，解析可靠
- **容錯**：驗證能抓出並處理 worker 失敗

**這個模式特別適合：**
- 需要多種觀點的內容產生（行銷、文件、創意寫作）
- 能受益於不同分析角度的分析任務
- 拆解策略取決於問題本身的問題解決

### 限制與考量

**成本與延遲：**
- 需要 N+1 次 LLM 呼叫（1 個 orchestrator + N 個 worker）
- 這個實作是循序處理（worker 一次跑一個）
- 想要更好的效能，可以用 `asyncio` 或 thread pool 平行化 worker 呼叫

**什麼時候不要用這個模式：**
- 輸出單一又明確的簡單任務（多出來的複雜度不划算）
- 延遲敏感的應用（多次 API 呼叫增加負擔）
- 子任務永遠一樣的任務（改用預先定義的平行化）

**要考慮的失敗模式：**
- orchestrator 可能沒有最佳地拆解任務（prompt engineering 很關鍵）
- worker 可能回傳空的或格式錯誤的回應（我們用驗證處理）
- 如果 model 沒有完全遵守格式，XML 解析可能失敗（可以考慮改用 JSON）

### 下一步

**強化這個實作：**
1. 用 `asyncio` 加上平行的 worker 執行，提升效能
2. 為失敗的 worker 實作重試邏輯
3. 加一個整合階段，讓 LLM 把 worker 的輸出合併
4. 試不同的 orchestrator 策略（例如要求更多或更少子任務）

**調整成你的使用情境：**
- 修改 orchestrator prompt，引導你領域的任務拆解
- 調整 worker prompt，提供領域專屬的指示
- 加入跟你應用相關的 context 參數
- 可以考慮 orchestrator 用 Claude Opus、worker 用 Claude Haiku，在成本和品質間取得平衡

## 重點整理

- orchestrator-workers 的關鍵是子任務在執行時才由 orchestrator 決定，不是預先寫死
- 用 XML 當 orchestrator 與程式之間的結構化介面，再解析成 task 清單
- worker 要同時拿到原始任務和自己的子任務說明，產出才不會偏題
- 成本是 N+1 次 LLM 呼叫，這個實作循序執行，要快可以平行化
- 子任務固定或只有單一輸出時，別用這個模式

## 練習

1. 改 orchestrator prompt，把要求的做法從 2-3 種改成固定 4 種，看輸出的變化。
2. 把 `process()` 裡循序呼叫 worker 的迴圈改成 thread pool 平行執行，比較總耗時。
3. 在 worker 結果後加一個整合步驟，再呼叫一次 LLM 把所有文案合併成一份推薦清單。
