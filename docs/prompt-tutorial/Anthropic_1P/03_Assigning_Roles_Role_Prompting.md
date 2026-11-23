---
translated: true
source: Anthropic 1P/03_Assigning_Roles_Role_Prompting.ipynb
---

# 第 3 章：指派角色（Role Prompting）

> 原文：[Anthropic 1P/03_Assigning_Roles_Role_Prompting.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/03_Assigning_Roles_Role_Prompting.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com



## 這篇在做什麼

這章講 role prompting：叫 Claude 扮演一個特定角色，連同需要的背景一起給它。角色不只會改變語氣和風格，也會影響它在邏輯、數學題上的表現。

## 學完你會

- 在 system prompt 或 user 訊息裡指派角色，改變 Claude 的語氣、風格和內容。
- 再補上目標讀者的資訊，讓回應更貼合情境。
- 用「邏輯機器人」這類角色，修正 Claude 在邏輯與數學判斷上的錯誤。

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

def get_completion(prompt: str, system_prompt=""):
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
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

延續「Claude 除了你說的話之外沒有任何背景」這個主題，有時很重要的是**用 prompt 讓 Claude 進入特定角色（包含所有必要的背景）**。這也叫 role prompting。角色背景越詳細越好。

**先給 Claude 一個角色，可以提升它在各種領域的表現**，從寫作、寫程式到摘要都是。就像人被告知「像個 ______ 一樣思考」，有時會比較好上手。Role prompting 也能改變 Claude 回應的風格、語氣和方式。

**注意：** Role prompting 可以放在 system prompt，也可以放在 user 訊息回合裡。

### 範例

下面的例子裡，沒有 role prompting 時，請 Claude 用一句話講對滑板的看法，它給的是**直接、沒有風格的回答**。

但是當我們讓 Claude 扮演一隻貓，它的觀點就變了，**回應的語氣、風格、內容都會配合新角色調整**。

**注意：** 另一個額外的技巧是**告訴 Claude 它的目標讀者是誰**。下面的 prompt 可以再改成告訴 Claude 它要對誰說話。「You are a cat」跟「you are a cat talking to a crowd of skateboarders」會產生很不一樣的回應。

這是 system prompt 沒有 role prompting 的版本：

```python
# Prompt
PROMPT = "In one sentence, what do you think about skateboarding?"

# Print Claude's response
print(get_completion(PROMPT))
```

這是同樣的使用者問題，但加了 role prompting。

```python
# System prompt
SYSTEM_PROMPT = "You are a cat."

# Prompt
PROMPT = "In one sentence, what do you think about skateboarding?"

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

你可以用 role prompting 讓 Claude 模仿某種寫作風格、用某種聲音說話，或控制回答的複雜度。**Role prompting 也能讓 Claude 在數學或邏輯任務上表現更好。**

例如下面這個例子有明確的正確答案，也就是 yes。但 Claude 答錯了，還以為資訊不足，其實資訊是夠的：

```python
# Prompt
PROMPT = "Jack is looking at Anne. Anne is looking at George. Jack is married, George is not, and we don’t know if Anne is married. Is a married person looking at an unmarried person?"

# Print Claude's response
print(get_completion(PROMPT))
```

那如果我們**讓 Claude 扮演邏輯機器人**，會怎麼改變它的答案？

結果是有了這個新角色，Claude 答對了。（不過要注意，不見得每個理由都對。）

```python
# System prompt
SYSTEM_PROMPT = "You are a logic bot designed to answer complex logic problems."

# Prompt
PROMPT = "Jack is looking at Anne. Anne is looking at George. Jack is married, George is not, and we don’t know if Anne is married. Is a married person looking at an unmarried person?"

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

**注意：** 你在這門課會學到，**有很多 prompt engineering 技巧可以得到類似的結果**。用哪種技巧是你自己的偏好！我們鼓勵你**多實驗，找出屬於你自己的 prompt engineering 風格**。

如果你想在不改動上面內容的情況下實驗課程裡的 prompt，可以捲到 notebook 最底下的[**範例遊樂場**](#example-playground)。

---

## 練習
- [練習 3.1 - 數學批改](#exercise-31---math-correction)

### 練習 3.1 - 數學批改
有些情況下，**Claude 在數學上可能會吃力**，即使是簡單的數學。下面 Claude 錯誤地判斷這道數學題解對了，但第二步明明有明顯的算術錯誤。注意 Claude 一步一步檢查時其實有抓到錯誤，卻沒有下結論說整個解答是錯的。

修改 `PROMPT` 和（或）`SYSTEM_PROMPT`，讓 Claude 把這個解答評為 `incorrectly` 解出，而不是正確解出。


```python
# System prompt - if you don't want to use a system prompt, you can leave this variable set to an empty string
SYSTEM_PROMPT = ""

# Prompt
PROMPT = """Is this equation solved correctly below?

2x - 3 = 9
2x = 6
x = 3"""

# Get Claude's response
response = get_completion(PROMPT, SYSTEM_PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    if "incorrect" in text or "not correct" in text.lower():
        return True
    else:
        return False

# Print Claude's response and the corresponding grade
print(response)
print("\n--------------------------- GRADING ---------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_3_1_hint; print(exercise_3_1_hint)
```

### 恭喜！

如果你解完到目前為止的所有練習，就可以進入下一章了。Happy prompting！

---

## 範例遊樂場

這裡可以自由實驗本課的 prompt 範例，調整 prompt 看看 Claude 的回應怎麼變。

```python
# Prompt
PROMPT = "In one sentence, what do you think about skateboarding?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# System prompt
SYSTEM_PROMPT = "You are a cat."

# Prompt
PROMPT = "In one sentence, what do you think about skateboarding?"

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

```python
# Prompt
PROMPT = "Jack is looking at Anne. Anne is looking at George. Jack is married, George is not, and we don’t know if Anne is married. Is a married person looking at an unmarried person?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# System prompt
SYSTEM_PROMPT = "You are a logic bot designed to answer complex logic problems."

# Prompt
PROMPT = "Jack is looking at Anne. Anne is looking at George. Jack is married, George is not, and we don’t know if Anne is married. Is a married person looking at an unmarried person?"

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

## 重點整理

- Claude 只知道你給的 context，所以角色和背景要講清楚，越詳細越好。
- 角色可以放在 system prompt，也可以放在 user 回合。
- 角色會改變語氣、風格和內容，也可能提升邏輯與數學任務的準確度。
- 補上目標讀者的資訊，是個簡單又有效的加分技巧。
- 達成同一個效果有很多 prompt 技巧，多實驗找出適合自己的做法。

## 練習

1. 把貓的角色換成別的（例如一位資深廚師），同樣問滑板的問題，比較語氣差異。
2. 在貓的角色後面加上「正在對一群滑板玩家說話」，看回應怎麼變。
3. 在練習 3.1 試試只改 `SYSTEM_PROMPT` 指派角色，再試試只改 `PROMPT`，比較哪個比較有效。
