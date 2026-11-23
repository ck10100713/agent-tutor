---
translated: true
source: tool_evaluation/tool_evaluation.ipynb
---

# Tool evaluation

> 原文：[tool_evaluation/tool_evaluation.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_evaluation/tool_evaluation.ipynb)

從 evaluation 任務檔，獨立地平行跑 agent 評估來測試 tool。

## 這篇在做什麼

讓多個 agent 各自獨立執行 evaluation 檔裡的同一個評估任務，用來測 tool 好不好用。範例以計算機 tool 為評估對象。

## 學完你會

- 寫出評估用的 prompt 和 agent 迴圈
- 寫出平行執行多個 agent 評估的主函式
- 對一個 tool（計算機）跑完整的 evaluation 並看結果

## 開跑前

需要 Anthropic API key，以及 evaluation 任務檔。

多個 agent 獨立執行 evaluation 檔裡的同一個評估任務。

```python
import json
import re
import time
import traceback
import xml.etree.ElementTree as ET  # noqa: S314
from pathlib import Path
from typing import Any

from anthropic import Anthropic
```

## Prompt

```python
# Embedded evaluator prompt
EVALUATION_PROMPT = """You are an AI assistant with access to tools.

When given a task, you MUST:
1. Use the available tools to complete the task
2. Provide summary of each step in your approach, wrapped in <summary> tags
3. Provide feedback on the tools provided, wrapped in <feedback> tags
4. Provide your final response, wrapped in <response> tags

Summary Requirements:
- In your <summary> tags, you must explain:
  - The steps you took to complete the task
  - Which tools you used, in what order, and why
  - The inputs you provided to each tool
  - The outputs you received from each tool
  - A summary for how you arrived at the response

Feedback Requirements:
- In your <feedback> tags, provide constructive feedback on the tools:
  - Comment on tool names: Are they clear and descriptive?
  - Comment on input parameters: Are they well-documented? Are required vs optional parameters clear?
  - Comment on descriptions: Do they accurately describe what the tool does?
  - Comment on any errors encountered during tool usage: Did the tool fail to execute? Did the tool return too many tokens?
  - Identify specific areas for improvement and explain WHY they would help
  - Be specific and actionable in your suggestions

Response Requirements:
- Your response should be concise and directly address what was asked
- Always wrap your final response in <response> tags
- If you cannot solve the task return <response>NOT_FOUND</response>
- For numeric responses, provide just the number
- For IDs, provide just the ID
- For names or text, provide the exact text requested
- Your response should go last"""
```

## Agent 迴圈

```python
client = Anthropic()
model = "claude-sonnet-5-5"


def agent_loop(prompt: str, tools: list[dict[str, Any]] = None) -> tuple[str, dict[str, Any]]:
    """Simplified agent class for tool evaluation"""
    messages = [{"role": "user", "content": prompt}]

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=EVALUATION_PROMPT,
        messages=messages,
        tools=tools,
    )

    messages.append({"role": "assistant", "content": response.content})

    # Track tool calls with timing
    tool_metrics = {}  # {tool_name: {"count": N, "durations": [X1, X2, ...]}}

    def _prepare_tool_result(tool_use_id, tool_result):
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": tool_result,
        }

    while response.stop_reason == "tool_use":
        # The model may call several tools in one turn; every tool_use needs a tool_result
        tool_results = []
        for tool_use in (block for block in response.content if block.type == "tool_use"):
            tool_name = tool_use.name

            tool_start_ts = time.time()
            try:
                # Note: eval is used here for demonstration purposes to dynamically call tool functions.
                # In production, use a safer dispatch mechanism like a dictionary of functions.
                tool_response = eval(  # noqa: S307
                    f"{tool_name}(**tool_use.input)"
                )  # Call the tool function with its input
            except Exception as e:
                tool_response = f"Error executing tool {tool_name}: {str(e)}\n"
                tool_response += traceback.format_exc()
            tool_duration = time.time() - tool_start_ts

            # Update tool metrics
            if tool_name not in tool_metrics:
                tool_metrics[tool_name] = {"count": 0, "durations": []}
            tool_metrics[tool_name]["count"] += 1
            tool_metrics[tool_name]["durations"].append(tool_duration)

            tool_results.append(_prepare_tool_result(tool_use.id, tool_response))

        # Append all tool results in a single user message
        messages.append({"role": "user", "content": tool_results})
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=EVALUATION_PROMPT,
            messages=messages,
            tools=tools,
        )
        messages.append({"role": "assistant", "content": response.content})

    response = next(
        (block.text for block in response.content if hasattr(block, "text")),
        None,
    )
    return response, tool_metrics
```

## 輔助函式

```python
def parse_evaluation_file(file_path: Path) -> list[dict[str, Any]]:
    """Parse XML evaluation file and return list of evaluation tasks."""
    try:
        # Parse trusted local XML evaluation file
        tree = ET.parse(file_path)  # noqa: S314
        root = tree.getroot()
        evaluations = []

        # Check for task elements
        tasks = root.findall(".//task")
        for task in tasks:
            prompt_elem = task.find("prompt")
            response_elem = task.find("response")

            if prompt_elem is not None and response_elem is not None:
                eval_dict = {
                    "prompt": (prompt_elem.text or "").strip(),
                    "response": (response_elem.text or "").strip(),
                }
                evaluations.append(eval_dict)

        return evaluations
    except Exception as e:
        print(f"Error parsing evaluation file {file_path}: {e}")
        return []
```

```python
def evaluate_single_task(
    task: dict[str, Any], tools: list[dict[str, Any]], task_index: int
) -> dict[str, Any]:
    """Evaluate a single task with the given tools."""
    start_time = time.time()

    # Run the task
    print(f"Task {task_index + 1}: Running task with prompt: {task['prompt']}")
    response, tool_metrics = agent_loop(task["prompt"], tools)

    # Extract all tagged content
    def _extract_xml_content(text, tag):
        pattern = rf"<{tag}>(.*?)</{tag}>"
        matches = re.findall(pattern, text, re.DOTALL)
        return matches[-1].strip() if matches else None

    response, summary, feedback = (
        _extract_xml_content(response, tag) for tag in ["response", "summary", "feedback"]
    )
    duration_seconds = time.time() - start_time

    return {
        "prompt": task["prompt"],
        "expected": task["response"],
        "actual": response,
        "score": int(response == task["response"]),
        "total_duration": duration_seconds,
        "tool_calls": tool_metrics,
        "num_tool_calls": sum(len(metrics["durations"]) for metrics in tool_metrics.values()),
        "summary": summary,
        "feedback": feedback,
    }
```

## 主要評估函式

```python
# Report Templates
REPORT_HEADER = """
# Evaluation Report

## Summary

- **Accuracy**: {correct}/{total} ({accuracy:.1f}%)
- **Average Task Duration**: {average_duration_s:.2f}s
- **Average Tool Calls per Task**: {average_tool_calls:.2f}
- **Total Tool Calls**: {total_tool_calls}

---
"""

TASK_TEMPLATE = """
### Task

**Prompt**: {prompt}
**Ground Truth Response**: `{expected_response}`
**Actual Response**: `{actual_response}`
**Correct**: {correct_indicator}
**Duration**: {total_duration:.2f}s
**Tool Calls**: {tool_calls}

**Summary**
{summary}

**Feedback**
{feedback}

---
"""


def run_evaluation(eval_path: str, tools: list[dict[str, Any]]) -> str:
    """
    Run evaluation with provided tools using a simple loop.

    Args:
        eval_path: Path to XML evaluation file
        tools: List of tool definitions to use for evaluation

    """
    print("🚀 Starting Evaluation")

    eval_file = Path(eval_path)

    # Parse evaluation tasks
    tasks = parse_evaluation_file(eval_file)

    print(f"📋 Loaded {len(tasks)} evaluation tasks")

    # Simple loop to run all tasks
    results = []
    for i, task in enumerate(tasks):
        print(f"Processing task {i + 1}/{len(tasks)}")
        results.append(evaluate_single_task(task, tools, i))

    # Calculate summary statistics
    correct = sum(r["score"] for r in results)
    accuracy = (correct / len(results)) * 100
    average_duration_s = sum(r["total_duration"] for r in results) / len(results)
    average_tool_calls = sum(r["num_tool_calls"] for r in results) / len(results)
    total_tool_calls = sum(r["num_tool_calls"] for r in results)

    report = REPORT_HEADER.format(
        correct=correct,
        total=len(results),
        accuracy=accuracy,
        average_duration_s=average_duration_s,
        average_tool_calls=average_tool_calls,
        total_tool_calls=total_tool_calls,
    )

    report += "".join(
        [
            TASK_TEMPLATE.format(
                prompt=task["prompt"],
                expected_response=task["response"],
                actual_response=result["actual"],
                correct_indicator="✅" if result["score"] else "❌",
                total_duration=result["total_duration"],
                tool_calls=json.dumps(result["tool_calls"], indent=2),
                summary=result["summary"] or "N/A",
                feedback=result["feedback"] or "N/A",
            )
            for task, result in zip(tasks, results, strict=False)
        ]
    )
    # Join all sections into final report
    return report
```

## 計算機 Tool

```python
def calculator(expression: str) -> str:
    """A basic calculator that performs arithmetic operations."""
    try:
        # Note: eval with restricted builtins is used here for demonstration.
        # In production, use a safer alternative like a math expression parser.
        result = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return str(result)
    except Exception as e:
        return f"Error: {str(e)}"


# Define the tool schema for the calculator
calculator_tool = {
    "name": "calculator",
    "description": "",  # An unhelpful tool description.
    "input_schema": {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "",  # An unhelpful schema description.
            }
        },
        "required": ["expression"],
    },
}

# Set the tools list
tools = [calculator_tool]
```

## 執行評估

```python
# Run evaluation
print("✅ Using calculator tool")

report = run_evaluation(eval_path="evaluation.xml", tools=tools)

print(report)
```

??? note "輸出"

    ```text
    ✅ Using calculator tool
    🚀 Starting Evaluation
    📋 Loaded 8 evaluation tasks
    Processing task 1/8
    Task 1: Running task with prompt: Calculate the compound interest on $10,000 invested at 5% annual interest rate, compounded monthly for 3 years. What is the final amount in dollars (rounded to 2 decimal places)?
    ```

    ```text
    Processing task 2/8
    Task 2: Running task with prompt: A projectile is launched at a 45-degree angle with an initial velocity of 50 m/s. Calculate the total distance (in meters) it has traveled from the launch point after 2 seconds, assuming g=9.8 m/s². Round to 2 decimal places.
    ```

    ```text
    Processing task 3/8
    Task 3: Running task with prompt: A sphere has a volume of 500 cubic meters. Calculate its surface area in square meters. Round to 2 decimal places.
    ```

    ```text
    Processing task 4/8
    Task 4: Running task with prompt: Calculate the population standard deviation of this dataset: [12, 15, 18, 22, 25, 30, 35]. Round to 2 decimal places.
    ```

    ```text
    Processing task 5/8
    Task 5: Running task with prompt: Calculate the pH of a solution with a hydrogen ion concentration of 3.5 × 10^-5 M. Round to 2 decimal places.
    ```

    ```text
    Processing task 6/8
    Task 6: Running task with prompt: Calculate the monthly payment for a $200,000 mortgage at 4.5% annual interest rate for 30 years (360 months). Use the standard mortgage payment formula. Round to 2 decimal places.
    ```

    ```text
    Processing task 7/8
    Task 7: Running task with prompt: Calculate the energy in joules of a photon with wavelength 550 nanometers. Use h = 6.626 × 10^-34 J·s and c = 3 × 10^8 m/s. Express the answer in scientific notation with 2 significant figures after the decimal (e.g., 3.61e-19).
    ```

    ```text
    Processing task 8/8
    Task 8: Running task with prompt: Find the larger real root of the quadratic equation 3x² - 7x + 2 = 0. Give the exact value.
    ```

    ```text

    # Evaluation Report

    ## Summary

    - **Accuracy**: 8/8 (100.0%)
    - **Average Task Duration**: 6.43s
    - **Average Tool Calls per Task**: 2.75
    - **Total Tool Calls**: 22

    ---

    ### Task

    **Prompt**: Calculate the compound interest on $10,000 invested at 5% annual interest rate, compounded monthly for 3 years. What is the final amount in dollars (rounded to 2 decimal places)?
    **Ground Truth Response**: `11614.72`
    **Actual Response**: `11614.72`
    **Correct**: ✅
    **Duration**: 6.71s
    **Tool Calls**: {
      "calculator": {
        "count": 3,
        "durations": [
          9.393692016601562e-05,
          0.00010085105895996094,
          8.034706115722656e-05
        ]
      }
    }

    **Summary**
    1. I called the calculator with `10000 * (1 + 0.05/12)^(36)`. It returned an error because the `^` operator isn't supported for floats.
    2. I called it again with `round(10000 * (1 + 0.05/12)**36, 2)`. It returned an error because `round` isn't defined.
    3. I called it a third time with `10000 * (1 + 0.05/12)**36`. It returned 11614.722313334678.
    4. I rounded that result to 2 decimal places by hand, which gives 11614.72.

    **Feedback**
    The calculator tool has a clear name, but its description is missing. It doesn't say which operators or functions it supports.
    - The `^` operator fails with a confusing Python type error. `**` works. Documenting this, or treating `^` as exponentiation, would help.
    - `round` is not available. Either support it or state that rounding must be done by hand.
    ... (省略 213 行)
    ```

## 重點整理

- tool 好不好用要用 agent 實際跑任務來測，不能只靠看 schema。
- 同一任務讓多個 agent 各跑一次，能看出結果是否穩定。
- 評估要有明確的任務和預期答案，才能算對錯。
- 評估結果能回頭指出 tool 描述或設計的問題。

## 練習

1. 增加 agent 的並行數量，觀察結果的一致性。
2. 在 evaluation 檔加一個新任務，用計算機 tool 測試。
3. 故意把 tool 描述改模糊，比較評估結果變差多少。
