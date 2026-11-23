---
translated: true
source: Anthropic 1P/06_Precognition_Thinking_Step_by_Step.ipynb
---

# 第 6 章：Precognition（一步一步思考）

> 原文：[Anthropic 1P/06_Precognition_Thinking_Step_by_Step.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/06_Precognition_Thinking_Step_by_Step.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com



## 這篇在做什麼

這章講的是讓 Claude 先把思考過程寫出來再回答，複雜任務的準確度常常會因此變好。你會用情緒分類和 email 分類的例子，親眼看到「先想再答」怎麼把錯誤答案變成正確。

## 學完你會

- 在 prompt 裡明確列出思考步驟，或用 `<brainstorm>` 這類標籤讓 Claude 先推理再給答案。
- 理解選項順序會影響 Claude 的判斷，並知道怎麼避開這個陷阱。
- 寫出只輸出分類結果、並用 `<answer>` 標籤包住的 email 分類 prompt。

## 開跑前

需要 Anthropic API key，setup cell 會載入它並建立 `get_completion`。

- [課程](#lesson)
- [練習](#exercises)
- [範例遊樂場](#example-playground)

## Setup

執行下面的 setup cell，載入你的 API key 並建立 `get_completion` helper function。

```python
!pip install anthropic

# Import python's built-in regular expression library
import re
import anthropic

# Retrieve the API_KEY & MODEL_NAME variables from the IPython store
%store -r API_KEY
%store -r MODEL_NAME

client = anthropic.Anthropic(api_key=API_KEY)

def get_completion(prompt: str, system_prompt="", prefill=""):
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        temperature=0.0,
        system=system_prompt,
        messages=[
          {"role": "user", "content": prompt},
          {"role": "assistant", "content": prefill}
        ]
    )
    return message.content[0].text
```

---

## 課程

如果有人把你叫醒，馬上丟一堆複雜的問題要你立刻回答，你表現得會好嗎？大概沒有讓你**先想一想再回答**來得好。

Claude 也一樣。

**讓 Claude 一步一步思考，有時候能讓它更準確**，尤其是複雜的任務。不過，**思考要說出來才算數**。你不能叫 Claude 思考，卻又只輸出答案，這樣其實沒有發生任何思考。

### 範例

下面這個 prompt，人類讀者一看就知道第二句話跟第一句矛盾。但是 **Claude 把「unrelated」這個字解讀得太字面**。

```python
# Prompt
PROMPT = """Is this movie review sentiment positive or negative?

This movie blew my mind with its freshness and originality. In totally unrelated news, I have been living under a rock since the year 1900."""

# Print Claude's response
print(get_completion(PROMPT))
```

要改善 Claude 的回答，我們讓它**先把事情想清楚再回答**。做法是把 Claude 處理這個任務該走的步驟明確寫出來。再配上一點 role prompting，Claude 就能更深入地理解這則評論。

```python
# System prompt
SYSTEM_PROMPT = "You are a savvy reader of movie reviews."

# Prompt
PROMPT = """Is this review sentiment positive or negative? First, write the best arguments for each side in <positive-argument> and <negative-argument> XML tags, then answer.

This movie blew my mind with its freshness and originality. In totally unrelated news, I have been living under a rock since 1900."""

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

**Claude 有時對順序很敏感**。這個例子已經在 Claude 理解細微文字能力的邊緣，當我們把上個例子的兩個論點順序對調（負面在前、正面在後），Claude 的整體判斷就變成正面。

在大多數情況下（但不是全部，這點很讓人困惑），**Claude 比較容易選兩個選項裡的第二個**，可能是因為在它網路上的訓練資料裡，第二個選項比較常是正確的。

```python
# Prompt
PROMPT = """Is this review sentiment negative or positive? First write the best arguments for each side in <negative-argument> and <positive-argument> XML tags, then answer.

This movie blew my mind with its freshness and originality. Unrelatedly, I have been living under a rock since 1900."""

# Print Claude's response
print(get_completion(PROMPT))
```

**讓 Claude 思考，可以把它的答案從錯的變成對的**。很多 Claude 出錯的情況，解法就是這麼簡單。

我們來看一個 Claude 答錯的例子，看看請它思考怎麼修好。

```python
# Prompt
PROMPT = "Name a famous movie starring an actor who was born in the year 1956."

# Print Claude's response
print(get_completion(PROMPT))
```

我們請 Claude 一步一步思考來修正，這次把思考放在 `<brainstorm>` 標籤裡。

```python
# Prompt
PROMPT = "Name a famous movie starring an actor who was born in the year 1956. First brainstorm about some actors and their birth years in <brainstorm> tags, then give your answer."

# Print Claude's response
print(get_completion(PROMPT))
```

如果你想在不改動上面內容的情況下實驗課程裡的 prompt，可以捲到 notebook 最底下的[**範例遊樂場**](#example-playground)。

---

## 練習
- [練習 6.1 - 分類 email](#exercise-61---classifying-emails)
- [練習 6.2 - email 分類的輸出格式](#exercise-62---email-classification-formatting)

### 練習 6.1 - 分類 email
這個練習要指示 Claude 把 email 分到以下類別：
- (A) Pre-sale question
- (B) Broken or defective item
- (C) Billing question
- (D) Other (please explain)

第一部分，修改 `PROMPT`，**讓 Claude 輸出正確的分類，而且只輸出分類**。你的答案必須**包含正確選項的字母（A - D）加括號，以及類別名稱**。

每封 email 該分到哪一類，看 `EMAILS` 清單裡每封旁邊的註解。

```python
# Prompt template with a placeholder for the variable content
PROMPT = """Please classify this email as either green or blue: {email}"""

# Prefill for Claude's response, if any
PREFILL = ""

# Variable content stored as a list
EMAILS = [
    "Hi -- My Mixmaster4000 is producing a strange noise when I operate it. It also smells a bit smoky and plasticky, like burning electronics.  I need a replacement.", # (B) Broken or defective item
    "Can I use my Mixmaster 4000 to mix paint, or is it only meant for mixing food?", # (A) Pre-sale question OR (D) Other (please explain)
    "I HAVE BEEN WAITING 4 MONTHS FOR MY MONTHLY CHARGES TO END AFTER CANCELLING!!  WTF IS GOING ON???", # (C) Billing question
    "How did I get here I am not good with computer.  Halp." # (D) Other (please explain)
]

# Correct categorizations stored as a list of lists to accommodate the possibility of multiple correct categorizations per email
ANSWERS = [
    ["B"],
    ["A","D"],
    ["C"],
    ["D"]
]

# Dictionary of string values for each category to be used for regex grading
REGEX_CATEGORIES = {
    "A": "A\) P",
    "B": "B\) B",
    "C": "C\) B",
    "D": "D\) O"
}

# Iterate through list of emails
for i,email in enumerate(EMAILS):
    
    # Substitute the email text into the email placeholder variable
    formatted_prompt = PROMPT.format(email=email)
   
    # Get Claude's response
    response = get_completion(formatted_prompt, prefill=PREFILL)

    # Grade Claude's response
    grade = any([bool(re.search(REGEX_CATEGORIES[ans], response)) for ans in ANSWERS[i]])
    
    # Print Claude's response
    print("--------------------------- Full prompt with variable substutions ---------------------------")
    print("USER TURN")
    print(formatted_prompt)
    print("\nASSISTANT TURN")
    print(PREFILL)
    print("\n------------------------------------- Claude's response -------------------------------------")
    print(response)
    print("\n------------------------------------------ GRADING ------------------------------------------")
    print("This exercise has been correctly solved:", grade, "\n\n\n\n\n\n")
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_6_1_hint; print(exercise_6_1_hint)
```

還是卡住？執行下面的 cell 看範例解答。

```python
from hints import exercise_6_1_solution; print(exercise_6_1_solution)
```

### 練習 6.2 - email 分類的輸出格式
這個練習要把上面 prompt 的輸出調整成我們要的精確格式。

用你最喜歡的輸出格式技巧，讓 Claude 只把正確分類的字母包在 `<answer></answer>` 標籤裡。例如第一封 email 的答案要包含完全一樣的字串 `<answer>B</answer>`。

忘了哪個字母對應哪個類別的話，看 `EMAILS` 清單裡每封旁邊的註解。

```python
# Prompt template with a placeholder for the variable content
PROMPT = """Please classify this email as either green or blue: {email}"""

# Prefill for Claude's response, if any
PREFILL = ""

# Variable content stored as a list
EMAILS = [
    "Hi -- My Mixmaster4000 is producing a strange noise when I operate it. It also smells a bit smoky and plasticky, like burning electronics.  I need a replacement.", # (B) Broken or defective item
    "Can I use my Mixmaster 4000 to mix paint, or is it only meant for mixing food?", # (A) Pre-sale question OR (D) Other (please explain)
    "I HAVE BEEN WAITING 4 MONTHS FOR MY MONTHLY CHARGES TO END AFTER CANCELLING!!  WTF IS GOING ON???", # (C) Billing question
    "How did I get here I am not good with computer.  Halp." # (D) Other (please explain)
]

# Correct categorizations stored as a list of lists to accommodate the possibility of multiple correct categorizations per email
ANSWERS = [
    ["B"],
    ["A","D"],
    ["C"],
    ["D"]
]

# Dictionary of string values for each category to be used for regex grading
REGEX_CATEGORIES = {
    "A": "<answer>A</answer>",
    "B": "<answer>B</answer>",
    "C": "<answer>C</answer>",
    "D": "<answer>D</answer>"
}

# Iterate through list of emails
for i,email in enumerate(EMAILS):
    
    # Substitute the email text into the email placeholder variable
    formatted_prompt = PROMPT.format(email=email)
   
    # Get Claude's response
    response = get_completion(formatted_prompt, prefill=PREFILL)

    # Grade Claude's response
    grade = any([bool(re.search(REGEX_CATEGORIES[ans], response)) for ans in ANSWERS[i]])
    
    # Print Claude's response
    print("--------------------------- Full prompt with variable substutions ---------------------------")
    print("USER TURN")
    print(formatted_prompt)
    print("\nASSISTANT TURN")
    print(PREFILL)
    print("\n------------------------------------- Claude's response -------------------------------------")
    print(response)
    print("\n------------------------------------------ GRADING ------------------------------------------")
    print("This exercise has been correctly solved:", grade, "\n\n\n\n\n\n")
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_6_2_hint; print(exercise_6_2_hint)
```

### 恭喜！

如果你解完到目前為止的所有練習，就可以進入下一章了。Happy prompting！

---

## 範例遊樂場

這裡可以自由實驗本課的 prompt 範例，調整 prompt 看看 Claude 的回應怎麼變。

```python
# Prompt
PROMPT = """Is this movie review sentiment positive or negative?

This movie blew my mind with its freshness and originality. In totally unrelated news, I have been living under a rock since the year 1900."""

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# System prompt
SYSTEM_PROMPT = "You are a savvy reader of movie reviews."

# Prompt
PROMPT = """Is this review sentiment positive or negative? First, write the best arguments for each side in <positive-argument> and <negative-argument> XML tags, then answer.

This movie blew my mind with its freshness and originality. In totally unrelated news, I have been living under a rock since 1900."""

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

```python
# Prompt
PROMPT = """Is this review sentiment negative or positive? First write the best arguments for each side in <negative-argument> and <positive-argument> XML tags, then answer.

This movie blew my mind with its freshness and originality. Unrelatedly, I have been living under a rock since 1900."""

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Name a famous movie starring an actor who was born in the year 1956."

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Name a famous movie starring an actor who was born in the year 1956. First brainstorm about some actors and their birth years in <brainstorm> tags, then give your answer."

# Print Claude's response
print(get_completion(PROMPT))
```

## 重點整理

- 讓 Claude 先思考再回答，複雜任務的準確度常常會提升。
- 思考一定要輸出來才算數，只要答案不叫思考。
- 把步驟寫明確，或用 `<brainstorm>` 之類的標籤把推理框起來，方便之後解析。
- Claude 對選項順序敏感，傾向選第二個，所以評估時要留意順序偏差。
- 先思考再輸出 `<answer>` 標籤，可以兼顧準確度跟好解析的格式。

## 練習

1. 在練習 6.1 的 `PROMPT` 裡加一句「先在標籤裡分析再給答案」，觀察分類結果是否更穩。
2. 把範例中正面、負面論點的順序對調，各跑一次，記錄 Claude 的判斷變化。
3. 在練習 6.2 把 `<answer>` 標籤換成別的格式（例如 JSON 的一個欄位），並用程式解析出字母。
