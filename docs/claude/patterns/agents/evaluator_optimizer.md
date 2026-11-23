---
translated: true
source: patterns/agents/evaluator_optimizer.ipynb
---

# Evaluator optimizer

> 原文：[patterns/agents/evaluator_optimizer.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/patterns/agents/evaluator_optimizer.ipynb)

一個 LLM 負責生成、另一個 LLM 負責評估並回饋的迴圈式 workflow pattern。

## 這篇在做什麼

示範 evaluator-optimizer workflow：一個 LLM 呼叫產生回應，另一個在迴圈中評估並提供回饋。範例是一個迭代式寫程式的迴圈。

## 學完你會

- 判斷什麼任務適合 evaluator-optimizer
- 寫出生成、評估、依回饋改進的迴圈
- 設計明確的評估標準

## Evaluator-Optimizer Workflow
這個 workflow 裡，一個 LLM 呼叫產生回應，另一個在迴圈中提供評估和回饋。

### 什麼時候用這個 workflow
當我們符合下面條件時，這個 workflow 特別有效：

- 有明確的評估標準
- 迭代改進有價值

適合的兩個徵兆是：

- 給了回饋之後，LLM 的回應確實可以變好
- LLM 自己能提供有意義的回饋

```python
from util import extract_xml, llm_call


def generate(prompt: str, task: str, context: str = "") -> tuple[str, str]:
    """Generate and improve a solution based on feedback."""
    full_prompt = f"{prompt}\n{context}\nTask: {task}" if context else f"{prompt}\nTask: {task}"
    response = llm_call(full_prompt)
    thoughts = extract_xml(response, "thoughts")
    result = extract_xml(response, "response")

    print("\n=== GENERATION START ===")
    print(f"Thoughts:\n{thoughts}\n")
    print(f"Generated:\n{result}")
    print("=== GENERATION END ===\n")

    return thoughts, result


def evaluate(prompt: str, content: str, task: str) -> tuple[str, str]:
    """Evaluate if a solution meets requirements."""
    full_prompt = f"{prompt}\nOriginal task: {task}\nContent to evaluate: {content}"
    response = llm_call(full_prompt)
    evaluation = extract_xml(response, "evaluation")
    feedback = extract_xml(response, "feedback")

    print("=== EVALUATION START ===")
    print(f"Status: {evaluation}")
    print(f"Feedback: {feedback}")
    print("=== EVALUATION END ===\n")

    return evaluation, feedback


def loop(task: str, evaluator_prompt: str, generator_prompt: str) -> tuple[str, list[dict]]:
    """Keep generating and evaluating until requirements are met."""
    memory = []
    chain_of_thought = []

    thoughts, result = generate(generator_prompt, task)
    memory.append(result)
    chain_of_thought.append({"thoughts": thoughts, "result": result})

    while True:
        evaluation, feedback = evaluate(evaluator_prompt, result, task)
        if evaluation == "PASS":
            return result, chain_of_thought

        context = "\n".join(
            ["Previous attempts:", *[f"- {m}" for m in memory], f"\nFeedback: {feedback}"]
        )

        thoughts, result = generate(generator_prompt, task, context)
        memory.append(result)
        chain_of_thought.append({"thoughts": thoughts, "result": result})
```

### 範例使用情境：迭代式寫程式迴圈



```python
evaluator_prompt = """
Evaluate this following code implementation for:
1. code correctness
2. time complexity
3. style and best practices

You should be evaluating only and not attemping to solve the task.
Only output "PASS" if all criteria are met and you have no further suggestions for improvements.
Output your evaluation concisely in the following format.

<evaluation>PASS, NEEDS_IMPROVEMENT, or FAIL</evaluation>
<feedback>
What needs improvement and why.
</feedback>
"""

generator_prompt = """
Your goal is to complete the task based on <user input>. If there are feedback
from your previous generations, you should reflect on them to improve your solution

Output your answer concisely in the following format:

<thoughts>
[Your understanding of the task and feedback and how you plan to improve]
</thoughts>

<response>
[Your code implementation here]
</response>
"""

task = """
<user input>
Implement a Stack with:
1. push(x)
2. pop()
3. getMin()
All operations should be O(1).
</user input>
"""

loop(task, evaluator_prompt, generator_prompt)
```

??? note "輸出"

    ````text

    === GENERATION START ===
    Thoughts:

    The task requires implementing a Stack with constant time operations including finding minimum. 
    To achieve O(1) for getMin(), we need to maintain a second stack that keeps track of minimums.
    Each time we push, if the value is smaller than current min, we add it to minStack.
    When we pop, if the popped value equals current min, we also pop from minStack.


    Generated:

    ```python
    class MinStack:
        def __init__(self):
            self.stack = []
            self.minStack = []
            
        def push(self, x: int) -> None:
            self.stack.append(x)
            if not self.minStack or x <= self.minStack[-1]:
                self.minStack.append(x)
                
        def pop(self) -> None:
            if not self.stack:
                return
            if self.stack[-1] == self.minStack[-1]:
                self.minStack.pop()
            self.stack.pop()
            
        def getMin(self) -> int:
            if not self.minStack:
                return None
            return self.minStack[-1]
    ```

    === GENERATION END ===

    === EVALUATION START ===
    Status: NEEDS_IMPROVEMENT
    ... (省略 94 行)
    ````

## 重點整理

- 兩個角色分工：generator 產出，evaluator 評分並給具體回饋。
- 只有在評估標準明確、而且回饋真的能改善結果時才值得用。
- 迴圈要有結束條件，例如評估通過或達到次數上限。
- 每輪都是額外的 LLM 呼叫，成本和延遲會增加。

## 練習

1. 把迴圈的最大輪數改成 1 和 5，比較結果與成本。
2. 修改 evaluator 的評估標準，加一條新的要求（例如要有 docstring）。
3. 換成非程式碼的任務（例如寫摘要），調整 evaluator 的 prompt。
