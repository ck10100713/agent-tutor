---
translated: true
source: Anthropic 1P/01_Basic_Prompt_Structure.ipynb
---
# 第 1 章：基本 Prompt 結構

> 原文：[Anthropic 1P/01_Basic_Prompt_Structure.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/01_Basic_Prompt_Structure.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com

## 這篇在做什麼

這章從 Messages API 的最小格式講起：一次呼叫要有哪些參數、`user` 和 `assistant` 怎麼輪流、system prompt 放在哪。你會看到格式正確和錯誤的呼叫各自的結果，再自己動手改 prompt 來通過兩道練習。

## 學完你會

- 寫出符合 Messages API 規定的呼叫（`model`、`max_tokens`、`messages`）
- 知道 `user` / `assistant` 必須交替、第一則一定是 `user`
- 用 `system` 參數改變 Claude 的回應風格

## 開跑前

- Anthropic API key（setup cell 會載入）。在 Colab 執行時，把 key 存進 Colab 的 Secrets 或直接在 cell 裡設定即可。

- [課程](#lesson)
- [練習](#exercises)
- [範例遊樂場](#example-playground)

## Setup

執行下面的 setup cell，載入 API key 並建立 `get_completion` helper 函式。

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

## Lesson

Anthropic 提供兩種 API：舊的 [Text Completions API](https://docs.anthropic.com/claude/reference/complete_post) 和現行的 [Messages API](https://docs.anthropic.com/claude/reference/messages_post)。這個教學只使用 Messages API。

用 Messages API 呼叫 Claude，至少需要這些參數：
- `model`：你要呼叫的模型的 [API 模型名稱](https://docs.anthropic.com/claude/docs/models-overview#model-recommendations)

- `max_tokens`：停止前最多產生的 token 數。注意 Claude 可能在達到上限前就停了，這個參數只是指定產生 token 的絕對上限。而且這是*硬*停止，可能讓 Claude 在字或句子中間就停下來。

- `messages`：輸入訊息的陣列。我們的模型是訓練成在交替的 `user` 和 `assistant` 對話輪次上運作。建立新的 `Message` 時，你用 messages 參數指定先前的對話輪次，模型再產生對話中的下一則 `Message`。
  - 每則輸入訊息必須是有 `role` 和 `content` 的物件。你可以只放單一 `user` 角色的訊息，也可以放多則 `user` 和 `assistant` 訊息（這時必須交替）。第一則訊息一定要用 user `role`。

也有一些選用參數，例如：
- `system`：system prompt，下面會再講。
  
- `temperature`：Claude 回應的變化程度。這些課程和練習中，我們把 `temperature` 設成 0。

完整的 API 參數清單請看我們的 [API 文件](https://docs.anthropic.com/claude/reference/messages_post)。

### 範例

來看 Claude 怎麼回應格式正確的 prompt。對下面每個 cell，執行它（`shift+enter`），Claude 的回應會出現在區塊下方。

```python
# Prompt
PROMPT = "Hi Claude, how are you?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Can you tell me the color of the ocean?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "What year was Celine Dion born in?"

# Print Claude's response
print(get_completion(PROMPT))
```

接著看一些沒有照正確 Messages API 格式寫的 prompt。這些格式錯誤的 prompt，Messages API 會回傳錯誤。

首先是一個 Messages API 呼叫，`messages` 陣列裡缺少 `role` 和 `content` 欄位。

```python
# Get Claude's response
response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        temperature=0.0,
        messages=[
          {"Hi Claude, how are you?"}
        ]
    )

# Print Claude's response
print(response[0].text)
```

這個 prompt 沒有在 `user` 和 `assistant` 角色之間交替。

```python
# Get Claude's response
response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        temperature=0.0,
        messages=[
          {"role": "user", "content": "What year was Celine Dion born in?"},
          {"role": "user", "content": "Also, can you tell me some other facts about her?"}
        ]
    )

# Print Claude's response
print(response[0].text)
```

`user` 和 `assistant` 訊息**必須交替**，而且訊息**必須從 `user` 輪次開始**。一個 prompt 裡可以有多組 `user` 和 `assistant`（就像模擬多輪對話）。你也可以在最後的 `assistant` 訊息裡先放一些字，讓 Claude 從你停下的地方接著寫（後面的章節會再講）。

#### System Prompts

你也可以用 **system prompt**。system prompt 是在 "User" 輪次提出問題或任務之前，先**給 Claude 背景、指示和準則**的方式。

結構上，system prompt 獨立於 `user` 和 `assistant` 訊息列表之外，所以放在另一個 `system` 參數（請看 notebook [Setup](#setup) 一節裡 `get_completion` helper 函式的結構）。

在這個教學中，只要可能用到 system prompt 的地方，我們都在你的 completion 函式裡提供了 `system` 欄位。如果你不想用 system prompt，把 `SYSTEM_PROMPT` 變數設成空字串就好。

#### System Prompt 範例

```python
# System prompt
SYSTEM_PROMPT = "Your answer should always be a series of critical thinking questions that further the conversation (do not provide answers to your questions). Do not actually answer the user question."

# Prompt
PROMPT = "Why is the sky blue?"

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

為什麼要用 system prompt？**寫得好的 system prompt 能以多種方式提升 Claude 的表現**，例如提高 Claude 遵守規則和指示的能力。更多資訊請看我們的文件 [how to use system prompts](https://docs.anthropic.com/claude/docs/how-to-use-system-prompts)。

現在進入練習。如果想在不改動上面內容的情況下試驗課程裡的 prompt，捲到課程 notebook 的最底部，到 [**範例遊樂場**](#example-playground)。

---

## Exercises
- [練習 1.1：數到三](#exercise-11---counting-to-three)
- [練習 1.2：System Prompt](#exercise-12---system-prompt)

### 練習 1.1：數到三
用正確的 `user` / `assistant` 格式，編輯下面的 `PROMPT`，讓 Claude **數到三**。輸出也會告訴你答案是否正確。

```python
# Prompt - this is the only field you should change
PROMPT = "[Replace this text]"

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    pattern = re.compile(r'^(?=.*1)(?=.*2)(?=.*3).*$', re.DOTALL)
    return bool(pattern.match(text))

# Print Claude's response and the corresponding grade
print(response)
print("\n--------------------------- GRADING ---------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_1_1_hint; print(exercise_1_1_hint)
```

### 練習 1.2：System Prompt

修改 `SYSTEM_PROMPT`，讓 Claude 像三歲小孩一樣回答。

```python
# System prompt - this is the only field you should change
SYSTEM_PROMPT = "[Replace this text]"

# Prompt
PROMPT = "How big is the sky?"

# Get Claude's response
response = get_completion(PROMPT, SYSTEM_PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(re.search(r"giggles", text) or re.search(r"soo", text))

# Print Claude's response and the corresponding grade
print(response)
print("\n--------------------------- GRADING ---------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想要提示的話，執行下面的 cell！

```python
from hints import exercise_1_2_hint; print(exercise_1_2_hint)
```

### 恭喜！

如果你解完了到這裡為止的所有練習，就可以進入下一章了。Happy prompting！

---

## Example Playground

這是讓你自由試驗本課範例 prompt、並調整 prompt 看看會怎麼影響 Claude 回應的區域。

```python
# Prompt
PROMPT = "Hi Claude, how are you?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "Can you tell me the color of the ocean?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = "What year was Celine Dion born in?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Get Claude's response
response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        temperature=0.0,
        messages=[
          {"Hi Claude, how are you?"}
        ]
    )

# Print Claude's response
print(response[0].text)
```

```python
# Get Claude's response
response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=2000,
        temperature=0.0,
        messages=[
          {"role": "user", "content": "What year was Celine Dion born in?"},
          {"role": "user", "content": "Also, can you tell me some other facts about her?"}
        ]
    )

# Print Claude's response
print(response[0].text)
```

```python
# System prompt
SYSTEM_PROMPT = "Your answer should always be a series of critical thinking questions that further the conversation (do not provide answers to your questions). Do not actually answer the user question."

# Prompt
PROMPT = "Why is the sky blue?"

# Print Claude's response
print(get_completion(PROMPT, SYSTEM_PROMPT))
```

## 重點整理

- Messages API 最少要有 `model`、`max_tokens`、`messages`；`max_tokens` 是硬上限，可能在句子中間截斷。
- `messages` 裡每則都要有 `role` 和 `content`，`user` 與 `assistant` 必須交替，且第一則必為 `user`。
- 最後一則放 `assistant` 內容，可以讓 Claude 從那裡接著寫。
- system prompt 放在獨立的 `system` 參數，用來給背景、指示和規則，能讓 Claude 更守規矩。

## 練習

1. 在範例遊樂場把 `messages` 的 `role` 拿掉一個，看錯誤訊息，再把兩則 `user` 連續放，比較兩種錯誤。
2. 在 `messages` 加入三組 `user` / `assistant` 輪次，模擬多輪對話，讓 Claude 接續回答最後一個問題。
3. 把 `max_tokens` 設成很小的值（例如 5），觀察回應在字或句中被截斷，再調回去，並搭配 `SYSTEM_PROMPT` 要求只用一句話回答。
