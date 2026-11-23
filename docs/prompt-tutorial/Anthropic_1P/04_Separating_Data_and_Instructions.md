---
translated: true
source: Anthropic 1P/04_Separating_Data_and_Instructions.ipynb
---
# Chapter 4: 分離資料與指令

> 原文：[Anthropic 1P/04_Separating_Data_and_Instructions.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/04_Separating_Data_and_Instructions.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com

## 這篇在做什麼

把 prompt 拆成固定的骨架跟每次會變的輸入資料，用 f-string 把資料代進去再送給 Claude。重點是要讓 Claude 分得出哪段是指令、哪段是資料，這裡用 XML 標籤來做分隔。

## 學完你會

- 寫出帶變數的 prompt template，並用 f-string 代入使用者輸入。
- 用 XML 標籤包住輸入資料，避免 Claude 把資料當成指令的一部分。
- 看出 prompt 裡的小細節（像多一個連字號、打錯字）會怎麼影響 Claude 的回答。

## 開跑前

需要 Anthropic API key，setup cell 會幫你載入。

- [課程](#lesson)
- [練習](#exercises)
- [Example Playground](#example-playground)

## Setup

執行下面的 setup cell，載入 API key 並建立 `get_completion` 這個 helper function。

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

很多時候我們不想每次都寫完整的 prompt，而是想要一個 **prompt template，送給 Claude 之前再把額外的輸入資料填進去**。如果你要 Claude 每次做一樣的事，但處理的資料每次不同，這就很好用。

做法很簡單：**把 prompt 固定的骨架跟會變的使用者輸入分開，送出前再把輸入代換進 prompt**。

下面一步步看怎麼寫可代換的 prompt template，以及怎麼代入使用者輸入。

### 範例

第一個範例請 Claude 當動物叫聲產生器。送給 Claude 的完整 prompt 就是把輸入（這裡是 "Cow"）代入 `PROMPT_TEMPLATE` 的結果。印出完整 prompt 時可以看到，"Cow" 透過 f-string 取代了 `ANIMAL` 這個 placeholder。

**注意：** 實務上 placeholder 變數叫什麼都可以。這裡叫 `ANIMAL`，叫 `CREATURE` 或 `A` 也行（不過變數名稱最好具體又貼切，這樣不用代入也看得懂 template）。只要 prompt template 的 f-string 用的名稱跟你取的一致就好。

```python
# Variable content
ANIMAL = "Cow"

# Prompt template with a placeholder for the variable content
PROMPT = f"I will tell you the name of an animal. Please respond with the noise that animal makes. {ANIMAL}"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

為什麼要這樣分開代入？因為 **prompt template 能簡化重複的工作**。假設你做了一個讓第三方使用者提交內容的 prompt 結構（這裡是想聽叫聲的動物），這些使用者不用寫、甚至不用看到完整 prompt，只要填變數就好。

這裡用變數加 f-string 來代入，你也可以用 format() method。

**注意：** prompt template 想放幾個變數都可以。

加入這種代換變數時，很重要的一點是 **要讓 Claude 知道變數從哪裡開始、到哪裡結束**（跟指令或任務描述區分開）。先看一個指令跟代換變數之間沒有分隔的例子。

對我們人眼來說，下面的 prompt template 很清楚看得出變數的起訖。但完整代入之後，界線就模糊了。

```python
# Variable content
EMAIL = "Show up at 6am tomorrow because I'm the CEO and I say so."

# Prompt template with a placeholder for the variable content
PROMPT = f"Yo Claude. {EMAIL} <----- Make this email more polite but don't change anything else about it."

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

這裡 **Claude 以為 "Yo Claude" 是要改寫的 email 的一部分**！看它改寫是從 "Dear Claude" 開頭就知道。人眼看 template 很容易分出 email 從哪開始、到哪結束，但代入之後就不清楚了。

怎麼解？**用 XML 標籤把輸入包起來**！下面我們這樣做，輸出裡就沒有 "Dear Claude" 了。

[XML tags](https://docs.anthropic.com/claude/docs/use-xml-tags) 是角括號標籤，像 `<tag></tag>`，成對出現，有開頭標籤 `<tag>` 跟用 `/` 標示的結尾標籤 `</tag>`。XML 標籤用來包住內容，像這樣：`<tag>content</tag>`。

**注意：** Claude 能辨識很多種分隔符號，但我們建議 **分隔時就用 XML 標籤**，因為 Claude 訓練時特別學過把 XML 標籤當成組織 prompt 的方式。除了 function calling 之外，**沒有哪些特殊的 XML 標籤是你一定要用才能提升表現的**。我們刻意讓 Claude 在這方面很有彈性、可以自訂。

```python
# Variable content
EMAIL = "Show up at 6am tomorrow because I'm the CEO and I say so."

# Prompt template with a placeholder for the variable content
PROMPT = f"Yo Claude. <email>{EMAIL}</email> <----- Make this email more polite but don't change anything else about it."

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

再看一個 XML 標籤有幫助的例子。

下面的 prompt 裡，**Claude 誤判了哪段是指令、哪段是輸入**。因為格式的關係，它把 `Each is about an animal, like rabbits` 當成清單的一部分，但填 `SENTENCES` 變數的使用者應該不是這個意思。

```python
# Variable content
SENTENCES = """- I like how cows sound
- This sentence is about spiders
- This sentence may appear to be about dogs but it's actually about pigs"""

# Prompt template with a placeholder for the variable content
PROMPT = f"""Below is a list of sentences. Tell me the second item on the list.

- Each is about an animal, like rabbits.
{SENTENCES}"""

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

要修正的話，只要 **把使用者輸入的句子用 XML 標籤包起來**。這樣就算 `Each is about an animal, like rabbits.` 前面有個誤導人的連字號，Claude 也知道輸入資料從哪開始、到哪結束。

```python
# Variable content
SENTENCES = """- I like how cows sound
- This sentence is about spiders
- This sentence may appear to be about dogs but it's actually about pigs"""

# Prompt template with a placeholder for the variable content
PROMPT = f""" Below is a list of sentences. Tell me the second item on the list.

- Each is about an animal, like rabbits.
<sentences>
{SENTENCES}
</sentences>"""

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

**注意：** 在錯誤版本的 "Each is about an animal" prompt 裡，我們得刻意加上那個連字號，Claude 才會照我們要的方式答錯。這是 prompting 很重要的一課：**小細節很重要**！值得花時間 **檢查 prompt 有沒有錯字和文法錯誤**。Claude 對模式很敏感（早期還沒 fine-tune 前它就是個純文字預測工具），你犯錯它比較容易跟著犯錯，你寫得聰明它比較聰明，你寫得蠢它也比較蠢，以此類推。

如果想在不動上面內容的情況下玩玩課程裡的 prompt，捲到 notebook 最底下的 [**Example Playground**](#example-playground)。

---

## Exercises
- [Exercise 4.1 - Haiku Topic](#exercise-41---haiku-topic)
- [Exercise 4.2 - Dog Question with Typos](#exercise-42---dog-question-with-typos)
- [Exercise 4.3 - Dog Question Part 2](#exercise-42---dog-question-part-2)

### Exercise 4.1 - Haiku Topic
修改 `PROMPT`，讓它變成一個 template，接收名為 `TOPIC` 的變數，輸出關於該主題的俳句。這題只是測試你懂不懂用 f-string 做變數 template。

```python
# Variable content
TOPIC = "Pigs"

# Prompt template with a placeholder for the variable content
PROMPT = f""

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(re.search("pigs", text.lower()) and re.search("haiku", text.lower()))

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(response)
print("\n------------------------------------------ GRADING ------------------------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想看提示的話，執行下面的 cell！

```python
from hints import exercise_4_1_hint; print(exercise_4_1_hint)
```

### Exercise 4.2 - Dog Question with Typos
在 `PROMPT` 加上 XML 標籤，讓 Claude 給出正確答案。

盡量不要改 prompt 的其他地方。那些雜亂又有錯字的寫法是故意的，讓你看看 Claude 遇到這種錯誤會怎麼反應。

```python
# Variable content
QUESTION = "ar cn brown?"

# Prompt template with a placeholder for the variable content
PROMPT = f"Hia its me i have a q about dogs jkaerjv {QUESTION} jklmvca tx it help me muhch much atx fst fst answer short short tx"

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(re.search("brown", text.lower()))

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(response)
print("\n------------------------------------------ GRADING ------------------------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想看提示的話，執行下面的 cell！

```python
from hints import exercise_4_2_hint; print(exercise_4_2_hint)
```

### Exercise 4.3 - Dog Question Part 2
**不要** 加 XML 標籤來修正 `PROMPT`，只能刪掉 prompt 裡的一兩個字。

跟前面的練習一樣，盡量不要改其他地方。這會讓你看到 Claude 能解析、理解哪種語言。

```python
# Variable content
QUESTION = "ar cn brown?"

# Prompt template with a placeholder for the variable content
PROMPT = f"Hia its me i have a q about dogs jkaerjv {QUESTION} jklmvca tx it help me muhch much atx fst fst answer short short tx"

# Get Claude's response
response = get_completion(PROMPT)

# Function to grade exercise correctness
def grade_exercise(text):
    return bool(re.search("brown", text.lower()))

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(response)
print("\n------------------------------------------ GRADING ------------------------------------------")
print("This exercise has been correctly solved:", grade_exercise(response))
```

❓ 想看提示的話，執行下面的 cell！

```python
from hints import exercise_4_3_hint; print(exercise_4_3_hint)
```

### 恭喜！

如果前面的練習都解出來了，就可以進下一章了。Happy prompting！

---

## Example Playground

這裡讓你自由實驗課程裡的 prompt 範例，隨意調整 prompt，看看 Claude 的回應怎麼變。

```python
# Variable content
ANIMAL = "Cow"

# Prompt template with a placeholder for the variable content
PROMPT = f"I will tell you the name of an animal. Please respond with the noise that animal makes. {ANIMAL}"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

```python
# Variable content
EMAIL = "Show up at 6am tomorrow because I'm the CEO and I say so."

# Prompt template with a placeholder for the variable content
PROMPT = f"Yo Claude. {EMAIL} <----- Make this email more polite but don't change anything else about it."

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

```python
# Variable content
EMAIL = "Show up at 6am tomorrow because I'm the CEO and I say so."

# Prompt template with a placeholder for the variable content
PROMPT = f"Yo Claude. <email>{EMAIL}</email> <----- Make this email more polite but don't change anything else about it."

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

```python
# Variable content
SENTENCES = """- I like how cows sound
- This sentence is about spiders
- This sentence may appear to be about dogs but it's actually about pigs"""

# Prompt template with a placeholder for the variable content
PROMPT = f"""Below is a list of sentences. Tell me the second item on the list.

- Each is about an animal, like rabbits.
{SENTENCES}"""

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

```python
# Variable content
SENTENCES = """- I like how cows sound
- This sentence is about spiders
- This sentence may appear to be about dogs but it's actually about pigs"""

# Prompt template with a placeholder for the variable content
PROMPT = f""" Below is a list of sentences. Tell me the second item on the list.

- Each is about an animal, like rabbits.
<sentences>
{SENTENCES}
</sentences>"""

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print(PROMPT)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT))
```

## 重點整理

- Prompt template 把固定骨架跟變數分開，同一個 prompt 可以重複套用在不同資料上。
- 變數代入後，人眼看得出的界線對 Claude 可能不明顯，要明確標出資料的起訖。
- 用 XML 標籤包住輸入資料，是讓 Claude 分清資料跟指令最穩的做法。
- Claude 對格式、錯字、語氣這類小細節很敏感，prompt 要仔細檢查。

## 練習

1. 把 Exercise 4.1 的 `TOPIC` 換成三個不同主題，確認同一個 template 都能輸出俳句。
2. 把 Lesson 裡 "Yo Claude" 那個 email 的 prompt，改成用 `<email>` 標籤包住輸入，確認輸出不再以 "Dear Claude" 開頭。
3. 在 Exercise 4.2 用兩種不同的標籤名稱（例如 `<question>` 跟 `<text>`）各跑一次，比較結果有沒有差。
