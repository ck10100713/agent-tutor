---
translated: true
source: examples/Unit_test_writing_using_a_multi-step_prompt_with_older_completions_API.ipynb
---
# 用多步驟 prompt 搭配舊版 Completions 寫單元測試

> 原文：[examples/Unit_test_writing_using_a_multi-step_prompt_with_older_completions_API.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Unit_test_writing_using_a_multi-step_prompt_with_older_completions_API.ipynb)

## 這篇在做什麼

用三步驟串起來的 prompt，讓 GPT-3 為一個 Python 函式寫 pytest 單元測試：先解釋函式、再規劃測試、最後寫測試程式碼。每一步的輸出會接到下一步的 prompt 裡，還加了條件分支、換模型、輸出檢查和串流。

## 學完你會

- 把一個複雜任務拆成多個串接的 prompt，把前一步產生的文字餵給下一步
- 用條件分支（計畫太短就追加一輪發想）、不同步驟用不同模型（`gpt-3.5-turbo-instruct` 規劃、`gpt-4` 寫程式）
- 用 Python 的 `ast` 模組檢查產出的程式碼能不能解析，不行就重跑，並用串流邊產生邊顯示

## 開跑前

- 需要 OpenAI API key
- 這份範例用的是舊版 Completions API（`openai.Completion.create`），要搭配舊版 `openai` 套件

複雜的任務（像是寫單元測試）很適合用多步驟 prompt。跟單一 prompt 不同，多步驟 prompt 會先讓 GPT-3 產生文字，再把這段文字餵回後面的 prompt。如果你想讓 GPT-3 先解釋推理再回答，或是先腦力激盪出計畫再執行，這招很有用。

在這份 notebook 裡，我們用三步驟的 prompt 來寫 Python 單元測試：

1. 給一個 Python 函式，先請 GPT-3 解釋這個函式在做什麼。
2. 接著請 GPT-3 規劃一組單元測試。
    - 如果計畫太短，就請 GPT-3 再多提一些單元測試的想法。
3. 最後請 GPT-3 寫出單元測試。

這個範例也示範了幾個可選的進階做法：

- 條件分支（例如第一份計畫太短才要求補充）
- 不同步驟用不同模型（例如文字規劃步驟用 `gpt-3.5-turbo-instruct`，寫程式步驟用 `gpt-4`）
- 輸出不滿意就重跑的檢查（例如輸出的程式碼不能被 Python 的 `ast` 模組解析）
- 串流輸出，讓你在內容完整產生前就能開始讀（很長的多步驟輸出特別有用）

完整的三步驟 prompt 長得像下面這樣（以 `pytest` 當單元測試框架、`is_palindrome` 當函式為例）：

    # How to write great unit tests with pytest

    In this advanced tutorial for experts, we'll use Python 3.9 and `pytest` to write a suite of unit tests to verify the behavior of the following function.
    ```python
    def is_palindrome(s):
        return s == s[::-1]
    ```

    Before writing any unit tests, let's review what each element of the function is doing exactly and what the author's intentions may have been.
    - First,{GENERATED IN STEP 1}
        
    A good unit test suite should aim to:
    - Test the function's behavior for a wide range of possible inputs
    - Test edge cases that the author may not have foreseen
    - Take advantage of the features of `pytest` to make the tests easy to write and maintain
    - Be easy to read and understand, with clean code and descriptive names
    - Be deterministic, so that the tests always pass or fail in the same way

    `pytest` has many convenient features that make it easy to write and maintain unit tests. We'll use them to write unit tests for the function above.

    For this particular function, we'll want our unit tests to handle the following diverse scenarios (and under each scenario, we include a few examples as sub-bullets):
    -{GENERATED IN STEP 2}

    [OPTIONALLY APPENDED]In addition to the scenarios above, we'll also want to make sure we don't forget to test rare or unexpected edge cases (and under each edge case, we include a few examples as sub-bullets):
    -{GENERATED IN STEP 2B}

    Before going into the individual tests, let's first look at the complete suite of unit tests as a cohesive whole. We've added helpful comments to explain what each line does.
    ```python
    import pytest  # used for our unit tests

    def is_palindrome(s):
        return s == s[::-1]

    #Below, each test case is represented by a tuple passed to the @pytest.mark.parametrize decorator
    {GENERATED IN STEP 3}

````python
import ast  # used for detecting whether generated Python code is valid
import openai

# example of a function that uses a multi-step prompt to write unit tests
def unit_test_from_function(
    function_to_test: str,  # Python function to test, as a string
    unit_test_package: str = "pytest",  # unit testing package; use the name as it appears in the import statement
    approx_min_cases_to_cover: int = 7,  # minimum number of test case categories to cover (approximate)
    print_text: bool = False,  # optionally prints text; helpful for understanding the function & debugging
    text_model: str = "gpt-3.5-turbo-instruct",  # model used to generate text plans in steps 1, 2, and 2b
    code_model: str = "gpt-3.5-turbo-instruct",  # if you don't have access to code models, you can use text models here instead
    max_tokens: int = 1000,  # can set this high, as generations should be stopped earlier by stop sequences
    temperature: float = 0.4,  # temperature = 0 can sometimes get stuck in repetitive loops, so we use 0.4
    reruns_if_fail: int = 1,  # if the output code cannot be parsed, this will re-run the function up to N times
) -> str:
    """Outputs a unit test for a given Python function, using a 3-step GPT-3 prompt."""

    # Step 1: Generate an explanation of the function

    # create a markdown-formatted prompt that asks GPT-3 to complete an explanation of the function, formatted as a bullet list
    prompt_to_explain_the_function = f"""# How to write great unit tests with {unit_test_package}

In this advanced tutorial for experts, we'll use Python 3.9 and `{unit_test_package}` to write a suite of unit tests to verify the behavior of the following function.
```python
{function_to_test}
```

Before writing any unit tests, let's review what each element of the function is doing exactly and what the author's intentions may have been.
- First,"""
    if print_text:
        text_color_prefix = "\033[30m"  # black; if you read against a dark background \033[97m is white
        print(text_color_prefix + prompt_to_explain_the_function, end="")  # end='' prevents a newline from being printed

    # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
    explanation_response = openai.Completion.create(
        model=text_model,
        prompt=prompt_to_explain_the_function,
        stop=["\n\n", "\n\t\n", "\n    \n"],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    explanation_completion = ""
    if print_text:
        completion_color_prefix = "\033[92m"  # green
        print(completion_color_prefix, end="")
    for event in explanation_response:
        event_text = event["choices"][0]["text"]
        explanation_completion += event_text
        if print_text:
            print(event_text, end="")

    # Step 2: Generate a plan to write a unit test

    # create a markdown-formatted prompt that asks GPT-3 to complete a plan for writing unit tests, formatted as a bullet list
    prompt_to_explain_a_plan = f"""
    
A good unit test suite should aim to:
- Test the function's behavior for a wide range of possible inputs
- Test edge cases that the author may not have foreseen
- Take advantage of the features of `{unit_test_package}` to make the tests easy to write and maintain
- Be easy to read and understand, with clean code and descriptive names
- Be deterministic, so that the tests always pass or fail in the same way

`{unit_test_package}` has many convenient features that make it easy to write and maintain unit tests. We'll use them to write unit tests for the function above.

For this particular function, we'll want our unit tests to handle the following diverse scenarios (and under each scenario, we include a few examples as sub-bullets):
-"""
    if print_text:
        print(text_color_prefix + prompt_to_explain_a_plan, end="")

    # append this planning prompt to the results from step 1
    prior_text = prompt_to_explain_the_function + explanation_completion
    full_plan_prompt = prior_text + prompt_to_explain_a_plan

    # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
    plan_response = openai.Completion.create(
        model=text_model,
        prompt=full_plan_prompt,
        stop=["\n\n", "\n\t\n", "\n    \n"],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True,
    )
    plan_completion = ""
    if print_text:
        print(completion_color_prefix, end="")
    for event in plan_response:
        event_text = event["choices"][0]["text"]
        plan_completion += event_text
        if print_text:
            print(event_text, end="")

    # Step 2b: If the plan is short, ask GPT-3 to elaborate further
    # this counts top-level bullets (e.g., categories), but not sub-bullets (e.g., test cases)
    elaboration_needed = plan_completion.count("\n-") +1 < approx_min_cases_to_cover  # adds 1 because the first bullet is not counted
    if elaboration_needed:
        prompt_to_elaborate_on_the_plan = f"""

In addition to the scenarios above, we'll also want to make sure we don't forget to test rare or unexpected edge cases (and under each edge case, we include a few examples as sub-bullets):
-"""
        if print_text:
            print(text_color_prefix + prompt_to_elaborate_on_the_plan, end="")

        # append this elaboration prompt to the results from step 2
        prior_text = full_plan_prompt + plan_completion
        full_elaboration_prompt = prior_text + prompt_to_elaborate_on_the_plan

        # send the prompt to the API, using \n\n as a stop sequence to stop at the end of the bullet list
        elaboration_response = openai.Completion.create(
            model=text_model,
            prompt=full_elaboration_prompt,
            stop=["\n\n", "\n\t\n", "\n    \n"],
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        elaboration_completion = ""
        if print_text:
            print(completion_color_prefix, end="")
        for event in elaboration_response:
            event_text = event["choices"][0]["text"]
            elaboration_completion += event_text
            if print_text:
                print(event_text, end="")

    # Step 3: Generate the unit test

    # create a markdown-formatted prompt that asks GPT-3 to complete a unit test
    starter_comment = ""
    if unit_test_package == "pytest":
        starter_comment = "Below, each test case is represented by a tuple passed to the @pytest.mark.parametrize decorator"
    prompt_to_generate_the_unit_test = f"""

Before going into the individual tests, let's first look at the complete suite of unit tests as a cohesive whole. We've added helpful comments to explain what each line does.
```python
import {unit_test_package}  # used for our unit tests

{function_to_test}

#{starter_comment}"""
    if print_text:
        print(text_color_prefix + prompt_to_generate_the_unit_test, end="")

    # append this unit test prompt to the results from step 3
    if elaboration_needed:
        prior_text = full_elaboration_prompt + elaboration_completion
    else:
        prior_text = full_plan_prompt + plan_completion
    full_unit_test_prompt = prior_text + prompt_to_generate_the_unit_test

    # send the prompt to the API, using ``` as a stop sequence to stop at the end of the code block
    unit_test_response = openai.Completion.create(
        model=code_model,
        prompt=full_unit_test_prompt,
        stop="```",
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True
    )
    unit_test_completion = ""
    if print_text:
        print(completion_color_prefix, end="")
    for event in unit_test_response:
        event_text = event["choices"][0]["text"]
        unit_test_completion += event_text
        if print_text:
            print(event_text, end="")

    # check the output for errors
    code_start_index = prompt_to_generate_the_unit_test.find("```python\n") + len("```python\n")
    code_output = prompt_to_generate_the_unit_test[code_start_index:] + unit_test_completion
    try:
        ast.parse(code_output)
    except SyntaxError as e:
        print(f"Syntax error in generated code: {e}")
        if reruns_if_fail > 0:
            print("Rerunning...")
            return unit_test_from_function(
                function_to_test=function_to_test,
                unit_test_package=unit_test_package,
                approx_min_cases_to_cover=approx_min_cases_to_cover,
                print_text=print_text,
                text_model=text_model,
                code_model=code_model,
                max_tokens=max_tokens,
                temperature=temperature,
                reruns_if_fail=reruns_if_fail-1,  # decrement rerun counter when calling again
            )

    # return the unit test as a string
    return unit_test_completion
````

```python
example_function = """def is_palindrome(s):
    return s == s[::-1]"""

unit_test_from_function(example_function, print_text=True)
```

??? note "輸出"

    ````text
    # How to write great unit tests with pytest

    In this advanced tutorial for experts, we'll use Python 3.9 and `pytest` to write a suite of unit tests to verify the behavior of the following function.
    ```python
    def is_palindrome(s):
        return s == s[::-1]
    ```

    Before writing any unit tests, let's review what each element of the function is doing exactly and what the author's intentions may have been.
    - First, we have a function definition. This is where we give the function a name, `is_palindrome`, and specify the arguments that the function accepts. In this case, the function accepts a single string argument, `s`.
    - Next, we have a return statement. This is where we specify the value that the function returns. In this case, the function returns `s == s[::-1]`.
    - Finally, we have a function call. This is where we actually call the function with a specific set of arguments. In this case, we're calling the function with the string `"racecar"`.
        
    A good unit test suite should aim to:
    - Test the function's behavior for a wide range of possible inputs
    - Test edge cases that the author may not have foreseen
    - Take advantage of the features of `pytest` to make the tests easy to write and maintain
    - Be easy to read and understand, with clean code and descriptive names
    - Be deterministic, so that the tests always pass or fail in the same way

    `pytest` has many convenient features that make it easy to write and maintain unit tests. We'll use them to write unit tests for the function above.

    For this particular function, we'll want our unit tests to handle the following diverse scenarios (and under each scenario, we include a few examples as sub-bullets):
    - The input is a palindrome
        - `"racecar"`
        - `"madam"`
        - `"anna"`
    - The input is not a palindrome
        - `"python"`
        - `"test"`
        - `"1234"`
    - The input is an empty string
        - `""`
    - The input is `None`
    - The input is not a string
        - `1`
        - `1.0`
        - `True`
        - `False`
        - `[]`
    ... (省略 83 行)
    ````

    ```text
    '.\n#The first element of the tuple is a name for the test case, and the second element is a list of arguments for the test case.\n#The @pytest.mark.parametrize decorator will generate a separate test function for each test case.\n#The generated test function will be named test_is_palindrome_<name> where <name> is the name of the test case.\n#The generated test function will be given the arguments specified in the list of arguments for the test case.\n#The generated test function will be given the fixture specified in the decorator, in this case the function itself.\n#The generated test function will call the function with the arguments and assert that the result is equal to the expected value.\n@pytest.mark.parametrize(\n    "name,args,expected",\n    [\n        # Test the function\'s behavior for a wide range of possible inputs\n        ("palindrome", ["racecar"], True),\n        ("palindrome", ["madam"], True),\n        ("palindrome", ["anna"], True),\n        ("non-palindrome", ["python"], False),\n        ("non-palindrome", ["test"], False),\n        ("non-palindrome", ["1234"], False),\n        ("empty string", [""], True),\n        ("None", [None], False),\n        ("non-string", [1], False),\n        ("non-string", [1.0], False),\n        ("non-string", [True], False),\n        ("non-string", [False], False),\n        ("non-string", [[]], False),\n        ("non-string", [{}], False),\n        # Test edge cases that the author may not have foreseen\n        ("palindrome with spaces", ["race car"], True),\n        ("palindrome with spaces", [" madam "], True),\n        ("palindrome with spaces", [" anna "], True),\n        ("non-palindrome with spaces", [" python "], False),\n        ("non-palindrome with spaces", [" test "], False),\n        ("non-palindrome with spaces", [" 1234 "], False),\n        ("palindrome with punctuation", ["racecar!"], True),\n        ("palindrome with punctuation", ["Madam, I\'m Adam."], True),\n        ("palindrome with punctuation", ["Anna\'s"], True),\n        ("non-palindrome with punctuation", ["python!"], False),\n        ("non-palindrome with punctuation", ["test."], False),\n        ("non-palindrome with punctuation", ["1234!"], False),\n        ("palindrome with mixed case", ["Racecar"], True),\n        ("palindrome with mixed case", ["Madam"], True),\n        ("palindrome with mixed case", ["Anna"], True),\n        ("non-palindrome with mixed case", ["Python"], False),\n        ("non-palindrome with mixed case", ["Test"], False),\n        ("non-palindrome with mixed case", ["1234"], False),\n    ],\n)\ndef test_is_palindrome(is_palindrome, args, expected):\n    assert is_palindrome(*args) == expected\n'
    ```

## 重點整理

- 複雜任務拆成多個串接的 prompt，前一步的輸出變成下一步的上下文，比單一 prompt 更好控制。
- 讓模型先解釋、先規劃再動手寫，通常能改善最後的結果。
- 可以用普通的 Python 邏輯插在步驟之間，像是依長度判斷要不要補充，或不同步驟用不同模型。
- 用 `ast` 這類程式化檢查驗證輸出，不合格就重跑，比直接相信模型輸出可靠。

## 練習

1. 把 `unit_test_package` 從 `pytest` 改成 `unittest`，看第三步產生的測試風格有什麼變化。
2. 調整 `approx_min_cases_to_cover` 的值，觀察第 2b 步（補充邊界情況）在什麼條件下會觸發。
3. 在第三步後面加一道檢查：除了用 `ast` 解析，再多驗證產出的程式碼裡至少有一個 `def test_`，不符合就重跑。
