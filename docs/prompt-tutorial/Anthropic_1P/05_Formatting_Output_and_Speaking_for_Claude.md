---
translated: true
source: Anthropic 1P/05_Formatting_Output_and_Speaking_for_Claude.ipynb
---

# 第 5 章：格式化輸出與替 Claude 開頭

> 原文：[Anthropic 1P/05_Formatting_Output_and_Speaking_for_Claude.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/05_Formatting_Output_and_Speaking_for_Claude.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com



## 這篇在做什麼

這章教你控制 Claude 輸出的格式：用 XML 標籤把真正要的內容框起來，或在 `assistant` 回合先填一段開頭（prefill），讓 Claude 接著寫。這樣下游程式才能穩定地把結果抽出來。

## 學完你會

- 要求 Claude 用 XML 標籤包住輸出，並用程式抽出標籤內的內容。
- 用 prefill 讓 Claude 從指定開頭接著寫，例如 `<haiku>` 或 JSON 的 `{`。
- 用 `stop_sequences` 在 Claude 輸出結束標籤時就停止，省錢也省時間。

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

# New argument added for prefill text, with a default value of an empty string
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

**Claude 可以用很多種方式格式化輸出**，你只要開口要求就行。

其中一種是用 XML 標籤，把回應跟其他多餘的文字分開。你已經學過可以用 XML 標籤讓 prompt 更清楚、更好被 Claude 解析。其實你也可以請 Claude **用 XML 標籤讓輸出更清楚，也更容易讓人理解**。

### 範例

還記得第 2 章我們靠叫 Claude 完全跳過開場白，解決了「詩的開場白問題」嗎？其實**叫 Claude 把詩放進 XML 標籤**，也能達到類似的效果。

```python
# Variable content
ANIMAL = "Rabbit"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Put it in <haiku> tags."

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

為什麼要這樣做？因為輸出放在 **XML 標籤裡，終端使用者就能寫一小段程式，抽出標籤之間的內容，穩定地只拿到詩本身**。

這個技巧可以再延伸：**把第一個 XML 標籤放進 `assistant` 回合。當你在 `assistant` 回合放文字，基本上是告訴 Claude 它已經說過這些話，要從那裡接著往下說。這個技巧叫做「替 Claude 開頭」（speaking for Claude）或「prefill Claude 的回應」。

下面我們用第一個 `<haiku>` XML 標籤做了這件事。注意 Claude 是怎麼直接從我們停下的地方接著寫的。

```python
# Variable content
ANIMAL = "Cat"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Put it in <haiku> tags."

# Prefill for Claude's response
PREFILL = "<haiku>"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN:")
print(PROMPT)
print("\nASSISTANT TURN:")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

Claude 也很擅長其他輸出格式，尤其是 `JSON`。如果你想強制輸出 JSON（不是百分之百，但很接近），也可以用開頭的括號 `{` 來 prefill Claude 的回應。

```python
# Variable content
ANIMAL = "Cat"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Use JSON format with the keys as \"first_line\", \"second_line\", and \"third_line\"."

# Prefill for Claude's response
PREFILL = "{"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\nASSISTANT TURN")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

下面這個例子，**在同一個 prompt 裡有多個輸入變數，同時還指定了輸出格式，全部都用 XML 標籤完成**。

```python
# First input variable
EMAIL = "Hi Zack, just pinging you for a quick update on that prompt you were supposed to write."

# Second input variable
ADJECTIVE = "olde english"

# Prompt template with a placeholder for the variable content
PROMPT = f"Hey Claude. Here is an email: <email>{EMAIL}</email>. Make this email more {ADJECTIVE}. Write the new version in <{ADJECTIVE}_email> XML tags."

# Prefill for Claude's response (now as an f-string with a variable)
PREFILL = f"<{ADJECTIVE}_email>"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\nASSISTANT TURN")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

#### 額外一課

如果你是透過 API 呼叫 Claude，可以把結束的 XML 標籤傳給 `stop_sequences` 參數，讓 Claude 一吐出你要的標籤就停止 sampling。這樣在它已經給出你在意的答案之後，可以省掉結尾的客套話，節省費用，也縮短拿到最後一個 token 的時間。

如果你想在不改動上面內容的情況下實驗課程裡的 prompt，可以捲到 notebook 最底下的[**範例遊樂場**](#example-playground)。

---

## 練習
- [練習 5.1 - Steph Curry GOAT](#exercise-51---steph-curry-goat)
- [練習 5.2 - 兩首俳句](#exercise-52---two-haikus)
- [練習 5.3 - 兩首俳句、兩種動物](#exercise-53---two-haikus-two-animals)

### 練習 5.1 - Steph Curry GOAT
被迫做選擇時，Claude 會指定 Michael Jordan 是史上最強的籃球員。我們能讓 Claude 選別人嗎？

修改 `PREFILL` 變數，**逼 Claude 詳細論證史上最強的籃球員是 Stephen Curry**。除了 `PREFILL` 之外盡量不要改別的，因為這個練習的重點就是它。

```python
# Prompt template with a placeholder for the variable content
PROMPT = f"Who is the best basketball player of all time? Please choose one specific player."

# Prefill for Claude's response
PREFILL = ""

# Get Claude's response
response = get_completion(PROMPT, prefill=PREFILL)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(re.search("Warrior", text))

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\nASSISTANT TURN")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(response)
print("\n------------------------------------------ GRADING ------------------------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_5_1_hint; print(exercise_5_1_hint)
```

### 練習 5.2 - 兩首俳句
用 XML 標籤修改下面的 `PROMPT`，讓 Claude 針對這個動物寫兩首俳句，而不只一首。兩首詩在哪裡結束、哪裡開始要很清楚。

```python
# Variable content
ANIMAL = "cats"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Put it in <haiku> tags."

# Prefill for Claude's response
PREFILL = "<haiku>"

# Get Claude's response
response = get_completion(PROMPT, prefill=PREFILL)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(
        (re.search("cat", text.lower()) and re.search("<haiku>", text))
        and (text.count("\n") + 1) > 5
    )

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\nASSISTANT TURN")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(response)
print("\n------------------------------------------ GRADING ------------------------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_5_2_hint; print(exercise_5_2_hint)
```

### 練習 5.3 - 兩首俳句、兩種動物
修改下面的 `PROMPT`，讓 **Claude 針對兩種不同的動物各寫一首俳句**。用 `{ANIMAL1}` 代表第一個替換，`{ANIMAL2}` 代表第二個替換。

```python
# First input variable
ANIMAL1 = "Cat"

# Second input variable
ANIMAL2 = "Dog"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL1}. Put it in <haiku> tags."

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(re.search("tail", text.lower()) and re.search("cat", text.lower()) and re.search("<haiku>", text))

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(response)
print("\n------------------------------------------ GRADING ------------------------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_5_3_hint; print(exercise_5_3_hint)
```

### 恭喜！

如果你解完到目前為止的所有練習，就可以進入下一章了。Happy prompting！

---

## 範例遊樂場

這裡可以自由實驗本課的 prompt 範例，調整 prompt 看看 Claude 的回應怎麼變。

```python
# Variable content
ANIMAL = "Rabbit"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Put it in <haiku> tags."

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

```python
# Variable content
ANIMAL = "Cat"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Put it in <haiku> tags."

# Prefill for Claude's response
PREFILL = "<haiku>"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN:")
print(PROMPT)
print("\nASSISTANT TURN:")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

```python
# Variable content
ANIMAL = "Cat"

# Prompt template with a placeholder for the variable content
PROMPT = f"Please write a haiku about {ANIMAL}. Use JSON format with the keys as \"first_line\", \"second_line\", and \"third_line\"."

# Prefill for Claude's response
PREFILL = "{"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\nASSISTANT TURN")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

```python
# First input variable
EMAIL = "Hi Zack, just pinging you for a quick update on that prompt you were supposed to write."

# Second input variable
ADJECTIVE = "olde english"

# Prompt template with a placeholder for the variable content
PROMPT = f"Hey Claude. Here is an email: <email>{EMAIL}</email>. Make this email more {ADJECTIVE}. Write the new version in <{ADJECTIVE}_email> XML tags."

# Prefill for Claude's response (now as an f-string with a variable)
PREFILL = f"<{ADJECTIVE}_email>"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN")
print(PROMPT)
print("\nASSISTANT TURN")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

## 重點整理

- 叫 Claude 把要的內容包在 XML 標籤裡，程式就能穩定抽出，不用處理開場白。
- Prefill 是在 `assistant` 回合先寫一段開頭，Claude 會從那裡接著寫。
- 用 `{` 做 prefill 可以大幅提高輸出 JSON 的機率。
- 多個輸入變數和輸出格式都可以用 XML 標籤在同一個 prompt 裡講清楚。
- `stop_sequences` 設成結束標籤，可以省掉結尾廢話的費用和時間。

## 練習

1. 在練習 5.1 只改 `PREFILL`，試試不同的開頭，看哪種最能讓 Claude 照你要的立場寫。
2. 在練習 5.2 寫一小段程式，用正規表示式把兩首俳句從輸出中分別抽出來。
3. 在練習 5.3 的 API 呼叫加上 `stop_sequences`，設成第二首的結束標籤，確認輸出在那裡停止。
