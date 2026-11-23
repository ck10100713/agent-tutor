---
translated: true
source: examples/gpt-5/gpt-5_new_params_and_tools.ipynb
---
# GPT-5 新參數與新工具

> 原文：[examples/gpt-5/gpt-5_new_params_and_tools.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/gpt-5/gpt-5_new_params_and_tools.ipynb)



## 這篇在做什麼
GPT-5 系列多了幾個開發者可以調的控制項：輸出長度、自由格式的 tool call、用文法限制輸出，還有最低推理量。這篇一個一個跑範例，看每個參數實際對輸出有什麼影響。

## 學完你會
- 用 `verbosity` 參數在不改 prompt 的情況下控制回答長短和程式碼的詳細程度。
- 用 `"type": "custom"` 的 tool 讓模型直接送出純文字（Python、SQL 等），再用 Lark 或 Regex 文法限制格式。
- 用 `reasoning effort: "minimal"` 換取更快的第一個 token。

## 開跑前
需要設好環境變數 `OPENAI_API_KEY`，並把 OpenAI SDK 升級到支援這些新參數的版本。


GPT-5 系列新增了幾個開發者控制項，讓你更能掌握模型的回應：從調整輸出長度與風格，到強制嚴格的格式。以下是最新功能的快速總覽：


| #  | Feature | Overview | Values / Usage |
|----|---------|----------|----------------|
| 1. | **Verbosity Parameter** | Lets you hint the model to be more or less expansive in its replies. Keep prompts stable and use the parameter instead of re-writing. | • **low** → terse UX, minimal prose.<br>• **medium** *(default)* → balanced detail.<br>• **high** → verbose, great for audits, teaching, or hand-offs. |
| 2. | **Freeform Function Calling** | Generate raw text payloads—anything from Python scripts to SQL queries—directly to your custom tool without JSON wrapping. Offers greater flexibility for external runtimes like:<br>• Code sandboxes (Python, C++, Java, …)<br>• SQL databases<br>• Shell environments<br>• Config generators | Use when structured JSON isn’t needed and raw text is more natural for the target tool. |
| 3. | **Context-Free Grammar (CFG)** | A set of production rules defining valid strings in a language. Each rule rewrites a non-terminal into terminals and/or other non-terminals, independent of surrounding context. Useful for constraining output to match the syntax of programming languages or custom formats in OpenAI tools. | Use as a contract to ensure the model emits only valid strings accepted by the grammar. |
| 4. | **Minimal Reasoning** | Runs GPT-5 with few or no reasoning tokens to minimize latency and speed time-to-first-token. Ideal for deterministic, lightweight tasks (extraction, formatting, short rewrites, simple classification) where explanations aren’t needed. If not specified, effort defaults to medium. | Set reasoning effort: "minimal". Avoid for multi-step planning or tool-heavy workflows. |


**支援的模型：**  
- gpt-5  
- gpt-5-mini  
- gpt-5-nano  

**支援的 API endpoint** 
- Responses API 
- Chat Completions API 

注意：建議搭配 GPT-5 系列使用 Responses API，才能發揮模型最好的表現。 


## 事前準備 

先把 OpenAI SDK 更新到支援 GPT-5 新參數和新工具的版本。另外確認已經把 OPENAI_API_KEY 設成環境變數。 

```python
!pip install --quiet --upgrade openai pandas && \
echo -n "openai " && pip show openai | grep '^Version:' | cut -d' ' -f2 && \
echo -n "pandas " && pip show pandas | grep '^Version:' | cut -d' ' -f2
```

??? note "輸出"

    ```text
    openai 1.99.2
    pandas 2.3.1
    ```

## 1. Verbosity 參數 

### 1.1 概述 
verbosity 參數可以提示模型回答要詳細還是簡短。   

**可用值：** "low"、"medium"、"high"

- low：精簡的 UX，文字越少越好。
- medium（預設）：詳細程度適中。
- high：講得很完整，適合稽核、教學或交接。

prompt 維持不變，用這個參數調整就好，不用重寫 prompt。


```python
from openai import OpenAI
import pandas as pd
from IPython.display import display

client = OpenAI()

question = "Write a poem about a boy and his first pet dog."

data = []

for verbosity in ["low", "medium", "high"]:
    response = client.responses.create(
        model="gpt-5-mini",
        input=question,
        text={"verbosity": verbosity}
    )

    # Extract text
    output_text = ""
    for item in response.output:
        if hasattr(item, "content"):
            for content in item.content:
                if hasattr(content, "text"):
                    output_text += content.text

    usage = response.usage
    data.append({
        "Verbosity": verbosity,
        "Sample Output": output_text,
        "Output Tokens": usage.output_tokens
    })

# Create DataFrame
df = pd.DataFrame(data)

# Display nicely with centered headers
pd.set_option('display.max_colwidth', None)
styled_df = df.style.set_table_styles(
    [
        {'selector': 'th', 'props': [('text-align', 'center')]},  # Center column headers
        {'selector': 'td', 'props': [('text-align', 'left')]}     # Left-align table cells
    ]
)

display(styled_df)
```

??? note "輸出"

    ```text
    <pandas.io.formats.style.Styler at 0x10b50fa10>
    ```

輸出的 token 數大致隨 verbosity 線性增加：low（560）→ medium（849）→ high（1288）。

### 2.3 在寫程式的情境使用 Verbosity 

verbosity 參數也會影響產出程式碼的長度與複雜度，以及附帶說明的深度。下面這個例子用不同的 verbosity 等級，請模型寫一個 Python 程式，對 1000000 個隨機數字做排序。 

```python
from openai import OpenAI

client = OpenAI()

prompt = "Output a Python program that sorts an array of 1000000 random numbers"

def ask_with_verbosity(verbosity: str, question: str):
    response = client.responses.create(
        model="gpt-5-mini",
        input=question,
        text={
            "verbosity": verbosity
        }
    )

    # Extract assistant's text output
    output_text = ""
    for item in response.output:
        if hasattr(item, "content"):
            for content in item.content:
                if hasattr(content, "text"):
                    output_text += content.text

    # Token usage details
    usage = response.usage

    print("--------------------------------")
    print(f"Verbosity: {verbosity}")
    print("Output:")
    print(output_text)
    print("Tokens => input: {} | output: {}".format(
        usage.input_tokens, usage.output_tokens
    ))


# Example usage:
ask_with_verbosity("low", prompt)
```

??? note "輸出"

    ````text
    --------------------------------
    Verbosity: low
    Output:
    ```python
    #!/usr/bin/env python3
    import random
    import time

    def main():
        N = 1_000_000
        arr = [random.random() for _ in range(N)]

        t0 = time.perf_counter()
        arr.sort()
        t1 = time.perf_counter()

        print(f"Sorted {N} numbers in {t1 - t0:.4f} seconds")
        print("First 10:", arr[:10])
        print("Last 10:", arr[-10:])

    if __name__ == "__main__":
        main()
    ```
    Tokens => input: 21 | output: 575
    ````

注意這裡輸出的程式碼只是一支單純的 script。接著改用 'medium' 跑跑看。 

```python
ask_with_verbosity("medium", prompt)
```

??? note "輸出"

    ````text
    --------------------------------
    Verbosity: medium
    Output:
    Here's a simple Python script that generates 1,000,000 random numbers, sorts them using the built-in Timsort, and reports timings and a small sample of the sorted output:

    ```python
    #!/usr/bin/env python3
    import random
    import time

    def main():
        N = 1_000_000
        random.seed(42)  # remove or change for different runs

        t0 = time.perf_counter()
        data = [random.random() for _ in range(N)]
        t1 = time.perf_counter()

        data.sort()
        t2 = time.perf_counter()

        # Basic verification and sample output
        is_sorted = all(data[i] <= data[i+1] for i in range(len(data)-1))
        print(f"Generated {N} random numbers in {t1 - t0:.3f} seconds")
        print(f"Sorted in {t2 - t1:.3f} seconds")
        print("Sorted check:", is_sorted)
        print("First 10 values:", data[:10])
        print("Last 10 values:", data[-10:])

    if __name__ == "__main__":
        main()
    ```

    Notes:
    - This uses Python's built-in list sort (Timsort), which is efficient for general-purpose sorting.
    - If you need more memory- and performance-efficient numeric operations on large arrays, consider using NumPy (numpy.random.random and numpy.sort).
    Tokens => input: 21 | output: 943
    ````

medium 的程式碼比較豐富，還附上額外說明。接著試試 high。 

```python
ask_with_verbosity("high", prompt)
```

??? note "輸出"

    ```text
    --------------------------------
    Verbosity: high
    Output:
    Here's a single, self-contained Python program that generates 1,000,000 random numbers and sorts them. It supports two backends: the built-in Python list sort (Timsort) and NumPy (if you have NumPy installed). It measures and prints the time taken for generation, sorting, and verification.

    Copy the code into a file (for example sort_random.py) and run it. By default it uses the pure Python backend; pass --backend numpy to use NumPy.

    Note: Sorting a million Python floats uses a moderate amount of memory (Python floats and list overhead). NumPy will typically be faster and use less overhead but requires the numpy package.

    Program:

    import time
    import random
    import argparse
    import sys

    def is_sorted_list(a):
        # Linear check for sortedness
        return all(a[i] <= a[i+1] for i in range(len(a)-1))

    def main():
        parser = argparse.ArgumentParser(description="Generate and sort random numbers.")
        parser.add_argument("--n", type=int, default=1_000_000, help="Number of random numbers (default: 1,000,000)")
        parser.add_argument("--backend", choices=["python", "numpy"], default="python",
                            help="Sorting backend to use: 'python' (default) or 'numpy'")
        parser.add_argument("--seed", type=int, default=0, help="Random seed (default: 0)")
        parser.add_argument("--sample", type=int, default=10, help="How many sample elements to print (default: 10)")
        args = parser.parse_args()

        n = args.n
        backend = args.backend
        seed = args.seed
        sample = args.sample

        print(f"Generating {n:,} random numbers using backend: {backend!r}, seed={seed}")

        random.seed(seed)

        if backend == "python":
            # Generate list of floats in Python
    ... (省略 82 行)
    ```

high 給了更多細節和說明。 

### 1.3 重點 

新的 verbosity 參數可以穩定地調整輸出的長度與深度，同時維持正確性和推理品質，**完全不用改 prompt**。
以這個例子來說：

- **Low verbosity** 只給最精簡、能跑的 script，沒有多餘的註解或結構。
- **Medium verbosity** 加上說明用的註解、函式結構，以及可重現的設定。
- **High verbosity** 給出完整、接近 production 的 script，有參數解析、多種排序方法、計時與驗證、使用說明和最佳實務提示。

## 2. 自由格式 Function Calling

### 2.1 概述 
GPT‑5 現在可以用新的 tool 類型 `"type": "custom"`，把純文字 payload（從 Python script 到 SQL 查詢都行）直接送給你的自訂 tool，不用包成 JSON。這跟傳統的結構化 function call 不一樣，跟下面這些外部 runtime 互動時彈性更大：

- code_exec 搭配 sandbox（Python、C++、Java 等）
- SQL 資料庫
- Shell 環境
- 設定檔產生器

**注意：custom tool 類型不支援 parallel tool calling。**

### 2.2 快速範例：計算圓的面積

下面的程式碼會產生一段計算圓面積的 Python 程式，並指示模型用自由格式的 tool call 輸出結果。 

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5-mini",
    input="Please use the code_exec tool to calculate the area of a circle with radius equal to the number of 'r's in strawberry",
    text={"format": {"type": "text"}},
    tools=[
        {
            "type": "custom",
            "name": "code_exec",
            "description": "Executes arbitrary python code",
        }
    ]
)
print(response.output)
```

??? note "輸出"

    ```text
    [ResponseReasoningItem(id='rs_6894e31b1f8081999d18325e5aeffcfe0861a2e1728d1664', summary=[], type='reasoning', content=[], encrypted_content=None, status=None), ResponseCustomToolCall(call_id='call_Gnqod2MwPvayp2JdNyA0z0Ah', input='# Counting \'r\'s in the word "strawberry" and computing circle area with that radius\nimport math\nr = "strawberry".count(\'r\')\narea = math.pi * r**2\n{"radius": r, "area": area, "area_exact": f"{r}*pi"}', name='code_exec', type='custom_tool_call', id='ctc_6894e31c66f08199abd622bb5ac3c4260861a2e1728d1664', status='completed')]
    ```

模型會送出一個 `tool call`，內容是純 Python。你在 server 端執行這段程式、取得印出的結果，再用另一次 responses.create 呼叫把結果送回去。

### 2.3 小型 Benchmark：用三種語言排序陣列
為了示範自由格式 tool call，我們請 GPT‑5：
- 產生 Python、C++、Java 程式碼，對一個固定陣列排序 10 次。
- 程式碼裡只印出每次迭代花的時間（ms）。
- 三個函式都呼叫一次，然後停止 

```python
from openai import OpenAI
from typing import List, Optional

MODEL_NAME = "gpt-5"

# Tools that will be passed to every model invocation. They are defined once so
# that the configuration lives in a single place.
TOOLS = [
    {
        "type": "custom",
        "name": "code_exec_python",
        "description": "Executes python code",
    },
    {
        "type": "custom",
        "name": "code_exec_cpp",
        "description": "Executes c++ code",
    },
    {
        "type": "custom",
        "name": "code_exec_java",
        "description": "Executes java code",
    },
]

client = OpenAI()

def create_response(
    input_messages: List[dict],
    previous_response_id: Optional[str] = None,
):
    """Wrapper around ``client.responses.create``.

    Parameters
    ----------
    input_messages: List[dict]
        The running conversation history to feed to the model.
    previous_response_id: str | None
        Pass the ``response.id`` from the *previous* call so the model can keep
        the thread of the conversation.  Omit on the very first request.
    """
    kwargs = {
        "model": MODEL_NAME,
        "input": input_messages,
        "text": {"format": {"type": "text"}},
        "tools": TOOLS,
    }
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id

    return client.responses.create(**kwargs)

# Recursive 
def run_conversation(
    input_messages: List[dict],
    previous_response_id: Optional[str] = None,
):
  
    response = create_response(input_messages, previous_response_id)

    # ``response.output`` is expected to be a list where element 0 is the model
    # message.  Element 1 (if present) denotes a tool call.  When the model is
    # done with tool calls, that element is omitted.
    tool_call = response.output[1] if len(response.output) > 1 else None

    if tool_call and tool_call.type == "custom_tool_call":
        print("--- tool name ---")
        print(tool_call.name)
        print("--- tool call argument (generated code) ---")
        print(tool_call.input)
        
        # Add a synthetic *tool result* so the model can continue the thread.
        
        input_messages.append(
            {
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": "done", # <-- replace with the result of the tool call
            }
        )

        # Recurse with updated conversation and track the response id so the
        # model is aware of the prior turn.
        return run_conversation(input_messages, previous_response_id=response.id)
    else:
        # Base-case: no further tool call - return. 
        return 


prompt = """
Write code to sort the array of numbers in three languages: C++, Python and Java (10 times each)using code_exec functions.

ALWAYS CALL THESE THREE FUNCTIONS EXACTLY ONCE: code_exec_python, code_exec_cpp and code_exec_java tools to sort the array in each language. Stop once you've called these three functions in each language once.

Print only the time it takes to sort the array in milliseconds. 

[448, 986, 255, 884, 632, 623, 246, 439, 936, 925, 644, 159, 777, 986, 706, 723, 534, 862, 195, 686, 846, 880, 970, 276, 613, 736, 329, 622, 870, 284, 945, 708, 267, 327, 678, 807, 687, 890, 907, 645, 364, 333, 385, 262, 730, 603, 945, 358, 923, 930, 761, 504, 870, 561, 517, 928, 994, 949, 233, 137, 670, 555, 149, 870, 997, 809, 180, 498, 914, 508, 411, 378, 394, 368, 766, 486, 757, 319, 338, 159, 585, 934, 654, 194, 542, 188, 934, 163, 889, 736, 792, 737, 667, 772, 198, 971, 459, 402, 989, 949]
"""

# Initial developer message.
messages = [
    {
        "role": "developer",
        "content": prompt,
    }
]

run_conversation(messages)
```

??? note "輸出"

    ```text
    --- tool name ---
    code_exec_python
    --- tool call argument (generated code) ---
    import time

    arr = [448, 986, 255, 884, 632, 623, 246, 439, 936, 925, 644, 159, 777, 986, 706, 723, 534, 862, 195, 686, 846, 880, 970, 276, 613, 736, 329, 622, 870, 284, 945, 708, 267, 327, 678, 807, 687, 890, 907, 645, 364, 333, 385, 262, 730, 603, 945, 358, 923, 930, 761, 504, 870, 561, 517, 928, 994, 949, 233, 137, 670, 555, 149, 870, 997, 809, 180, 498, 914, 508, 411, 378, 394, 368, 766, 486, 757, 319, 338, 159, 585, 934, 654, 194, 542, 188, 934, 163, 889, 736, 792, 737, 667, 772, 198, 971, 459, 402, 989, 949]

    start = time.perf_counter()
    for _ in range(10):
        b = arr[:]  # copy
        b.sort()
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    print(elapsed_ms, end="")
    --- tool name ---
    code_exec_cpp
    --- tool call argument (generated code) ---
    #include <iostream>
    #include <vector>
    #include <algorithm>
    #include <chrono>
    using namespace std;

    int main() {
        vector<int> a = {448, 986, 255, 884, 632, 623, 246, 439, 936, 925, 644, 159, 777, 986, 706, 723, 534, 862, 195, 686, 846, 880, 970, 276, 613, 736, 329, 622, 870, 284, 945, 708, 267, 327, 678, 807, 687, 890, 907, 645, 364, 333, 385, 262, 730, 603, 945, 358, 923, 930, 761, 504, 870, 561, 517, 928, 994, 949, 233, 137, 670, 555, 149, 870, 997, 809, 180, 498, 914, 508, 411, 378, 394, 368, 766, 486, 757, 319, 338, 159, 585, 934, 654, 194, 542, 188, 934, 163, 889, 736, 792, 737, 667, 772, 198, 971, 459, 402, 989, 949};
        auto start = chrono::high_resolution_clock::now();
        for (int i = 0; i < 10; ++i) {
            auto b = a;
            sort(b.begin(), b.end());
        }
        auto end = chrono::high_resolution_clock::now();
        auto ms = chrono::duration_cast<chrono::milliseconds>(end - start).count();
        cout << ms;
        return 0;
    }
    --- tool name ---
    code_exec_java
    --- tool call argument (generated code) ---
    import java.util.*;
    public class Main {
        public static void main(String[] args) {
    ... (省略 10 行)
    ```

模型針對同一個演算法輸出了 Python、C++、Java 三段程式碼。function call 的輸出會接回去當作模型的輸入，讓模型繼續往下做，直到三個函式各被呼叫一次。 

### 2.4 重點 

GPT-5 的自由格式 tool calling 讓你把純文字 payload（例如 Python script、SQL 查詢、設定檔）直接送給自訂 tool，不用包 JSON。模型可以照你的 tool 要的格式產生程式碼或文字，跟外部 runtime 互動比較有彈性。不需要結構化 JSON 的時候，用純文字輸出會更順手。

## 3. Context‑Free Grammar (CFG)

### 3.1 概述 
context‑free grammar（無上下文文法）是一組產生規則，用來定義哪些字串屬於某個語言。每條規則把一個 non‑terminal 符號改寫成一串 terminal（字面 token）和 / 或其他 non‑terminal，不受前後文影響，所以叫 context‑free。CFG 可以描述大部分程式語言的語法；在 OpenAI 的 custom tool 裡，它就像一份合約，強迫模型只能輸出符合文法的字串。

### 3.2 文法基礎

**支援的文法語法** 
- Lark - https://lark-parser.readthedocs.io/en/stable/
- Regex - https://docs.rs/regex/latest/regex/#syntax

底層用 LLGuidance 來限制模型的 sampling：https://github.com/guidance-ai/llguidance。

**不支援的 Lark 功能** 
- regex 裡的 lookaround（`(?=...)`、`(?!...)` 等）
- regex 裡的 lazy modifier（`*?`、`+?`、`??`）。
- Terminal priorities、templates、%declares、%import（%import common 除外）。


**Terminals vs Rules 與 Greedy Lexing** 

| Concept          | Take-away                                                                    |
|------------------|------------------------------------------------------------------------------|
| Terminals (UPPER)| Matched first by the lexer – longest match wins.                             |
| Rules (lower)    | Combine terminals; cannot influence how text is tokenised.                   |
| Greedy lexer     | Never try to “shape” free text across multiple terminals – you’ll lose control. |

**正確與錯誤的 pattern 設計** 

✅ **用一個有界的 terminal 處理兩個錨點之間的自由文字**  
```
start: SENTENCE
SENTENCE: /[A-Za-z, ]*(the hero|a dragon)[A-Za-z, ]*(fought|saved)[A-Za-z, ]*(a treasure|the kingdom)[A-Za-z, ]*\./
```
❌ **不要把自由文字拆到多個 terminal / rule**  
```
start: sentence
sentence: /[A-Za-z, ]+/ subject /[A-Za-z, ]+/ verb /[A-Za-z, ]+/ object /[A-Za-z, ]+/
```

### 3.3 範例：SQL 方言，MS SQL vs PostgreSQL

下面的程式碼是用 CFG 建構多方言 SQL tool 的標準參考寫法。它示範了：

- 兩份獨立的文法定義（`mssql_grammar_definition`、`postgres_grammar_definition`），分別對應 TOP 與 LIMIT 的語意。
- 怎麼在同一支 script 裡寫 prompt、呼叫、檢查 tool call。
- 並排比較 assistant 的回應。

先定義不同 SQL 方言的 LARK 文法

```python
import textwrap

# ----------------- grammars for MS SQL dialect -----------------
mssql_grammar = textwrap.dedent(r"""
            // ---------- Punctuation & operators ----------
            SP: " "
            COMMA: ","
            GT: ">"
            EQ: "="
            SEMI: ";"

            // ---------- Start ----------
            start: "SELECT" SP "TOP" SP NUMBER SP select_list SP "FROM" SP table SP "WHERE" SP amount_filter SP "AND" SP date_filter SP "ORDER" SP "BY" SP sort_cols SEMI

            // ---------- Projections ----------
            select_list: column (COMMA SP column)*
            column: IDENTIFIER

            // ---------- Tables ----------
            table: IDENTIFIER

            // ---------- Filters ----------
            amount_filter: "total_amount" SP GT SP NUMBER
            date_filter: "order_date" SP GT SP DATE

            // ---------- Sorting ----------
            sort_cols: "order_date" SP "DESC"

            // ---------- Terminals ----------
            IDENTIFIER: /[A-Za-z_][A-Za-z0-9_]*/
            NUMBER: /[0-9]+/
            DATE: /'[0-9]{4}-[0-9]{2}-[0-9]{2}'/
    """)

# ----------------- grammars for PostgreSQL dialect -----------------
postgres_grammar = textwrap.dedent(r"""
            // ---------- Punctuation & operators ----------
            SP: " "
            COMMA: ","
            GT: ">"
            EQ: "="
            SEMI: ";"

            // ---------- Start ----------
            start: "SELECT" SP select_list SP "FROM" SP table SP "WHERE" SP amount_filter SP "AND" SP date_filter SP "ORDER" SP "BY" SP sort_cols SP "LIMIT" SP NUMBER SEMI

            // ---------- Projections ----------
            select_list: column (COMMA SP column)*
            column: IDENTIFIER

            // ---------- Tables ----------
            table: IDENTIFIER

            // ---------- Filters ----------
            amount_filter: "total_amount" SP GT SP NUMBER
            date_filter: "order_date" SP GT SP DATE

            // ---------- Sorting ----------
            sort_cols: "order_date" SP "DESC"

            // ---------- Terminals ----------
            IDENTIFIER: /[A-Za-z_][A-Za-z0-9_]*/
            NUMBER: /[0-9]+/
            DATE: /'[0-9]{4}-[0-9]{2}-[0-9]{2}'/
    """)
```

### 3.4 產生特定的 SQL 方言 
先定義 prompt，再呼叫函式產生 MS SQL 方言 

```python
from openai import OpenAI
client = OpenAI()

sql_prompt_mssql = (
    "Call the mssql_grammar to generate a query for Microsoft SQL Server that retrieve the "
    "five most recent orders per customer, showing customer_id, order_id, order_date, and total_amount, "
    "where total_amount > 500 and order_date is after '2025-01-01'. "
)

response_mssql = client.responses.create(
    model="gpt-5",
    input=sql_prompt_mssql,
    text={"format": {"type": "text"}},
    tools=[
        {
            "type": "custom",
            "name": "mssql_grammar",
            "description": "Executes read-only Microsoft SQL Server queries limited to SELECT statements with TOP and basic WHERE/ORDER BY. YOU MUST REASON HEAVILY ABOUT THE QUERY AND MAKE SURE IT OBEYS THE GRAMMAR.",
            "format": {
                "type": "grammar",
                "syntax": "lark",
                "definition": mssql_grammar
            }
        },
    ],
    parallel_tool_calls=False
)

print("--- MS SQL Query ---")
print(response_mssql.output[1].input)
```

??? note "輸出"

    ```text
    --- MS SQL Query ---
    SELECT TOP 5 customer_id, order_id, order_date, total_amount FROM orders WHERE total_amount > 500 AND order_date > '2025-01-01' ORDER BY order_date DESC;
    ```

輸出的 SQL 正確使用了 "SELECT TOP" 語法。 

```python
sql_prompt_pg = (
    "Call the postgres_grammar to generate a query for PostgreSQL that retrieve the "
    "five most recent orders per customer, showing customer_id, order_id, order_date, and total_amount, "
    "where total_amount > 500 and order_date is after '2025-01-01'. "
)

response_pg = client.responses.create(
    model="gpt-5",
    input=sql_prompt_pg,
    text={"format": {"type": "text"}},
    tools=[
        {
            "type": "custom",
            "name": "postgres_grammar",
            "description": "Executes read-only PostgreSQL queries limited to SELECT statements with LIMIT and basic WHERE/ORDER BY. YOU MUST REASON HEAVILY ABOUT THE QUERY AND MAKE SURE IT OBEYS THE GRAMMAR.",
            "format": {
                "type": "grammar",
                "syntax": "lark",
                "definition": postgres_grammar
            }
        },
    ],
    parallel_tool_calls=False,
)

print("--- PG SQL Query ---")
print(response_pg.output[1].input)
```

??? note "輸出"

    ```text
    --- PG SQL Query ---
    SELECT customer_id, order_id, order_date, total_amount FROM orders WHERE total_amount > 500 AND order_date > '2025-01-01' ORDER BY order_date DESC LIMIT 5;
    ```

輸出是同一個邏輯查詢，只是實際語法不同。給不同的文法，模型就只能產生符合該方言的合法語句。

| Dialect       | Generated Query                                              | Key Difference                          |
|---------------|--------------------------------------------------------------|------------------------------------------|
| MS SQL Server | SELECT TOP 5 customer_id, … ORDER BY order_date DESC;         | Uses `TOP N` clause before column list.  |
| PostgreSQL    | SELECT customer_id, … ORDER BY order_date DESC LIMIT 5;       | Uses `LIMIT N` after `ORDER BY`.         |



### 3.5 範例：Regex CFG 語法

下面的程式碼示範用 Regex CFG 語法，把自由格式 tool call 限制成特定的時間戳記格式。

```python
from openai import OpenAI
client = OpenAI()

timestamp_grammar_definition = r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]) (?:[01]\d|2[0-3]):[0-5]\d$"

timestamp_prompt = (
        "Call the timestamp_grammar to save a timestamp for August 7th 2025 at 10AM."
)

response_mssql = client.responses.create(
    model="gpt-5",
    input=timestamp_prompt,
    text={"format": {"type": "text"}},
    tools=[
        {
            "type": "custom",
            "name": "timestamp_grammar",
            "description": "Saves a timestamp in date + time in 24-hr format.",
            "format": {
                "type": "grammar",
                "syntax": "regex",
                "definition": timestamp_grammar_definition
            }
        },
    ],
    parallel_tool_calls=False
)

print("--- Timestamp ---")
print(response_mssql.output[1].input)
```

??? note "輸出"

    ```text
    --- Timestamp ---
    2025-08-07 10:00
    ```

### 3.5 最佳實務

Lark 文法很難一次寫到完美。簡單的文法通常最穩，複雜的文法往往得反覆調整文法定義、prompt 和 tool 描述，才能避免模型輸出偏離正常分佈。

- terminal 要有界：用 `/[^.\n]{0,10}*\./`，不要用 `/.*\./`。同時用內容（排除字元集）和長度（`{M,N}` 量詞）限制比對範圍。 
- 明確寫字元集，少用 `.` 萬用字元。
- 空白要明確寫進去，例如用 `SP = " "`，不要用全域的 `%ignore`。
- 描述好你的 tool：告訴模型這份 CFG 接受什麼，並要求它多花心思推理確保符合文法。

**疑難排解**
- API 因為文法太複雜而拒絕 ➜ 簡化 rule 和 terminal，拿掉 `%ignore.*`。
- 出現非預期的 token ➜ 確認 terminal 沒有互相重疊，檢查 greedy lexer。
- 模型偏離正常分佈時（表現為輸出過長或一直重複，語法合法但語意是錯的）：
    - 把文法收緊。
    - 調整 prompt（加 few-shot 範例）和 tool 描述（解釋文法，並要求模型推理以符合文法）。
    - 試試更高的 reasoning effort（例如從 medium 調到 high）。

**參考資源：**  
- Lark Docs – https://lark-parser.readthedocs.io/en/stable/
- Lark IDE – https://www.lark-parser.org/ide/
- LLGuidance Syntax – https://github.com/guidance-ai/llguidance/blob/main/docs/syntax.md
- Regex (Rust crate) – https://docs.rs/regex/latest/regex/#syntax

### 3.6 重點 

GPT-5 的 Context-Free Grammar (CFG) 支援讓你嚴格限制模型輸出符合預先定義的語法，只產生合法字串。這對強制遵守程式語言規則或自訂格式特別有用，可以減少後處理和錯誤。只要給精確的文法和清楚的 tool 描述，模型就能穩定地待在你要的輸出結構裡。

## 4. Minimal Reasoning 

### 4.1 概述 

GPT-5 現在支援新的 minimal reasoning effort。使用 minimal 時，模型只會輸出很少甚至沒有 reasoning token，適合想要很快拿到第一個使用者看得到的 token 的情境。注意：如果沒有指定 reasoning effort，預設是 medium。 

```python
from openai import OpenAI

client = OpenAI()

prompt = "Classify sentiment of the review as positive|neutral|negative. Return one word only." 


response = client.responses.create(
    model="gpt-5",
    input= [{ 'role': 'developer', 'content': prompt }, 
            { 'role': 'user', 'content': 'The food that the restaurant was great! I recommend it to everyone.' }],
    reasoning = {
        "effort": "minimal"
    },
)

# Extract model's text output
output_text = ""
for item in response.output:
    if hasattr(item, "content"):
        for content in item.content:
            if hasattr(content, "text"):
                output_text += content.text

# Token usage details
usage = response.usage

print("--------------------------------")
print("Output:")
print(output_text)
```

??? note "輸出"

    ```text
    --------------------------------
    Output:
    positive
    ```

### 4.2 重點 
Minimal reasoning 讓 GPT-5 只用很少或不用 reasoning token，藉此降低延遲、加快第一個 token 出現的速度。適合用在確定性高、輕量的任務（擷取、格式轉換、短篇改寫、簡單分類），這類任務不需要解釋。沒指定 effort 的話預設是 medium，想要速度勝過深思就要明確設成 minimal。

## 重點整理
- `verbosity` 可以不改 prompt 就調整輸出長度和深度，low、medium、high 三檔。
- `"type": "custom"` 的 tool 讓模型直接送純文字給外部 runtime，不用包 JSON，但不支援 parallel tool calling。
- CFG（Lark 或 Regex）像合約，讓模型只能輸出合法語法，不同 SQL 方言只要換文法就好。
- 文法要簡單、terminal 要有界、tool 描述要寫清楚，模型才不容易跑偏。
- minimal reasoning 犧牲推理換速度，適合輕量任務，不適合多步驟規劃或重度用 tool 的流程。

## 練習
1. 把 verbosity 範例裡的 `"low"` 改成 `"high"`，比較兩次輸出的 token 數，看看跟頁面上的 560 到 1288 差多少。
2. 在 MS SQL 範例裡，把 prompt 的查詢改成「取最新 10 筆訂單」，確認產出的是 `TOP 10`，再換成 PostgreSQL 文法看是否變成 `LIMIT 10`。
3. 修改 Regex CFG 範例的時間戳記 pattern（例如改成只接受日期、不含時間），看模型的輸出怎麼跟著變。
