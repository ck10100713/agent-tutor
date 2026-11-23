---
translated: true
source: Anthropic 1P/02_Being_Clear_and_Direct.ipynb
---

# 第 2 章：清楚又直接

> 原文：[Anthropic 1P/02_Being_Clear_and_Direct.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/02_Being_Clear_and_Direct.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com



## 這篇在做什麼

這章講 prompt 最基本的原則：Claude 對清楚、直接的指示反應最好。你會用寫俳句、選最強籃球員這些例子，體會「想要什麼就直接講」的差別。

## 學完你會

- 用 Clear Prompting 的黃金法則檢查自己的 prompt。
- 用一句明確的指示，讓 Claude 省掉開場白，直接給你要的內容。
- 用 system prompt 指定回答語言，並逼 Claude 給出明確的單一答案或夠長的輸出。

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

# Note that we changed max_tokens to 4K just for this lesson to allow for longer completions in the exercises
def get_completion(prompt: str, system_prompt=""):
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4000,
        temperature=0.0,
        system=system_prompt,
        messages=[
          {"role": "user", "content": prompt}
        ]
    )
    return message.content[0].text
```

---

## 課程

**Claude 對清楚又直接的指示反應最好。**

把 Claude 想成一個剛到職的新人。**除了你字面上告訴它的，Claude 對要做什麼沒有任何背景**。就像你第一次交代一個人做事，你越是直白地把想要的東西說清楚，Claude 的回應就越好、越準確。

有疑問時，遵守**清楚 prompt 的黃金法則**：
- 把你的 prompt 拿給同事或朋友看，請他們照指示自己做做看，能不能做出你要的結果。如果他們困惑，Claude 也會困惑。

### 範例

拿寫詩這個任務來看。（忽略音節數不對的問題，LLM 還不太會數音節。）

```python
# Prompt
PROMPT = "Write a haiku about robots."

# Print Claude's response
print(get_completion(PROMPT))
```

這首俳句還不錯，但使用者可能希望 Claude 直接進入詩的內容，不要有「Here is a haiku」這種開場白。

怎麼做到？我們**直接要求**！

```python
# Prompt
PROMPT = "Write a haiku about robots. Skip the preamble; go straight into the poem."

# Print Claude's response
print(get_completion(PROMPT))
```

再看另一個例子。我們問 Claude 誰是史上最強的籃球員。可以看到下面 Claude 雖然列了幾個名字，**卻沒有給出明確的「最強」**。

```python
# Prompt
PROMPT = "Who is the best basketball player of all time?"

# Print Claude's response
print(get_completion(PROMPT))
```

能不能讓 Claude 下定決心，選出最強的球員？可以！直接開口要求就好！

```python
# Prompt
PROMPT = "Who is the best basketball player of all time? Yes, there are differing opinions, but if you absolutely had to pick one player, who would it be?"

# Print Claude's response
print(get_completion(PROMPT))
```

如果你想在不改動上面內容的情況下實驗課程裡的 prompt，可以捲到 notebook 最底下的[**範例遊樂場**](#example-playground)。

---

## 練習
- [練習 2.1 - 西班牙文](#exercise-21---spanish)
- [練習 2.2 - 只回一位球員](#exercise-22---one-player-only)
- [練習 2.3 - 寫一個故事](#exercise-23---write-a-story)

### 練習 2.1 - 西班牙文
修改 `SYSTEM_PROMPT`，讓 Claude 用西班牙文輸出答案。

```python
# System prompt - this is the only field you should chnage
SYSTEM_PROMPT = "[Replace this text]"

# Prompt
PROMPT = "Hello Claude, how are you?"

# Get Claude's response
response = get_completion(PROMPT, SYSTEM_PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return "hola" in text.lower()

# Print Claude's response and the corresponding grade
print(response)
print("\n--------------------------- GRADING ---------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_2_1_hint; print(exercise_2_1_hint)
```

### 練習 2.2 - 只回一位球員

修改 `PROMPT`，讓 Claude 完全不要模稜兩可，**只**回答一位特定球員的名字，**不要有其他文字或標點**。

```python
# Prompt - this is the only field you should change
PROMPT = "[Replace this text]"

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return text == "Michael Jordan"

# Print Claude's response and the corresponding grade
print(response)
print("\n--------------------------- GRADING ---------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_2_2_hint; print(exercise_2_2_hint)
```

### 練習 2.3 - 寫一個故事

修改 `PROMPT`，讓 Claude 盡可能給出最長的回應。如果你的答案**超過 800 字**，Claude 的回應就會被評為正確。

```python
# Prompt - this is the only field you should change
PROMPT = "[Replace this text]"

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    trimmed = text.strip()
    words = len(trimmed.split())
    return words >= 800

# Print Claude's response and the corresponding grade
print(response)
print("\n--------------------------- GRADING ---------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_2_3_hint; print(exercise_2_3_hint)
```

### 恭喜！

如果你解完到目前為止的所有練習，就可以進入下一章了。Happy prompting！

---

## 範例遊樂場

這裡可以自由實驗本課的 prompt 範例，調整 prompt 看看 Claude 的回應怎麼變。

```python
# Prompt
PROMPT = "Write a haiku about robots."

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Write a haiku about robots. Skip the preamble; go straight into the poem."

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Who is the best basketball player of all time?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Who is the best basketball player of all time? Yes, there are differing opinions, but if you absolutely had to pick one player, who would it be?"

# Print Claude's response
print(get_completion(PROMPT))
```

## 重點整理

- Claude 除了你寫的內容沒有任何背景，想要什麼就直接、明確地說。
- 黃金法則：讓同事照你的 prompt 做做看，他們困惑，Claude 就會困惑。
- 不想要開場白、想要單一答案、想要長輸出，都直接在 prompt 裡要求。
- 語言這類全域設定，可以放在 system prompt。

## 練習

1. 在練習 2.1 把語言換成日文，並要求用簡短的一句話回答。
2. 在練習 2.2 試試不同的措辭，看哪種最能讓 Claude 只輸出名字、沒有標點。
3. 在練習 2.3 寫程式數輸出的字數，並調整 prompt 要求，看能把輸出推到多長。
