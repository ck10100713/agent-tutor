---
translated: true
source: Anthropic 1P/07_Using_Examples_Few-Shot_Prompting.ipynb
---

# 第 7 章：用範例（Few-Shot Prompting）

> 原文：[Anthropic 1P/07_Using_Examples_Few-Shot_Prompting.ipynb](https://github.com/anthropics/prompt-eng-interactive-tutorial/blob/master/Anthropic%201P/07_Using_Examples_Few-Shot_Prompting.ipynb)

!!! note "個人閱讀用"
    本頁是個人閱讀用的翻譯。原文未附授權條款，版權屬於 Anthropic。如有任何問題或是錯誤使用，請寄信到 b04201003@gmail.com



## 這篇在做什麼

這章講 few-shot prompting：直接給 Claude 幾個理想行為的範例，比寫一長串說明更有效。你會用「家長機器人」和人名職業擷取的例子，看範例怎麼同時改善語氣和格式。

## 學完你會

- 用幾個範例讓 Claude 學會你要的語氣，而不是花力氣描述。
- 用格式正確的範例，讓 Claude 自己推論出輸出結構。
- 用 few-shot 範例重做 email 分類，讓輸出的最後一個字母就是分類結果。

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

**給 Claude 你希望它怎麼做（或不希望它怎麼做）的範例，非常有效**，可以用來：
- 拿到正確的答案
- 拿到格式正確的答案

這種 prompt 方式也叫「**few shot prompting**」。你也可能看到「zero-shot」、「n-shot」或「one-shot」。「shot」的數量指的是 prompt 裡用了幾個範例。

### 範例

假裝你是開發者，想做一個回答小孩問題的「家長機器人」。**Claude 預設的回應相當正式又機械**，這會讓小孩心碎。

```python
# Prompt
PROMPT = "Will Santa bring me presents on Christmas?"

# Print Claude's response
print(get_completion(PROMPT))
```

你可以花時間描述想要的語氣，但更簡單的做法是直接**給 Claude 幾個理想回應的範例**。

```python
# Prompt
PROMPT = """Please complete the conversation by writing the next line, speaking as "A".
Q: Is the tooth fairy real?
A: Of course, sweetie. Wrap up your tooth and put it under your pillow tonight. There might be something waiting for you in the morning.
Q: Will Santa bring me presents on Christmas?"""

# Print Claude's response
print(get_completion(PROMPT))
```

在下面的格式範例裡，我們可以一步一步地教 Claude 一組格式指示，說明怎麼擷取人名和職業，再照我們要的格式輸出。也可以直接**給 Claude 幾個格式正確的範例，Claude 會自己推演**。注意 `assistant` 回合裡的 `<individuals>`，用來讓 Claude 有個好的開頭。

```python
# Prompt template with a placeholder for the variable content
PROMPT = """Silvermist Hollow, a charming village, was home to an extraordinary group of individuals.
Among them was Dr. Liam Patel, a neurosurgeon who revolutionized surgical techniques at the regional medical center.
Olivia Chen was an innovative architect who transformed the village's landscape with her sustainable and breathtaking designs.
The local theater was graced by the enchanting symphonies of Ethan Kovacs, a professionally-trained musician and composer.
Isabella Torres, a self-taught chef with a passion for locally sourced ingredients, created a culinary sensation with her farm-to-table restaurant, which became a must-visit destination for food lovers.
These remarkable individuals, each with their distinct talents, contributed to the vibrant tapestry of life in Silvermist Hollow.
<individuals>
1. Dr. Liam Patel [NEUROSURGEON]
2. Olivia Chen [ARCHITECT]
3. Ethan Kovacs [MISICIAN AND COMPOSER]
4. Isabella Torres [CHEF]
</individuals>

At the heart of the town, Chef Oliver Hamilton has transformed the culinary scene with his farm-to-table restaurant, Green Plate. Oliver's dedication to sourcing local, organic ingredients has earned the establishment rave reviews from food critics and locals alike.
Just down the street, you'll find the Riverside Grove Library, where head librarian Elizabeth Chen has worked diligently to create a welcoming and inclusive space for all. Her efforts to expand the library's offerings and establish reading programs for children have had a significant impact on the town's literacy rates.
As you stroll through the charming town square, you'll be captivated by the beautiful murals adorning the walls. These masterpieces are the work of renowned artist, Isabella Torres, whose talent for capturing the essence of Riverside Grove has brought the town to life.
Riverside Grove's athletic achievements are also worth noting, thanks to former Olympic swimmer-turned-coach, Marcus Jenkins. Marcus has used his experience and passion to train the town's youth, leading the Riverside Grove Swim Team to several regional championships.
<individuals>
1. Oliver Hamilton [CHEF]
2. Elizabeth Chen [LIBRARIAN]
3. Isabella Torres [ARTIST]
4. Marcus Jenkins [COACH]
</individuals>

Oak Valley, a charming small town, is home to a remarkable trio of individuals whose skills and dedication have left a lasting impact on the community.
At the town's bustling farmer's market, you'll find Laura Simmons, a passionate organic farmer known for her delicious and sustainably grown produce. Her dedication to promoting healthy eating has inspired the town to embrace a more eco-conscious lifestyle.
In Oak Valley's community center, Kevin Alvarez, a skilled dance instructor, has brought the joy of movement to people of all ages. His inclusive dance classes have fostered a sense of unity and self-expression among residents, enriching the local arts scene.
Lastly, Rachel O'Connor, a tireless volunteer, dedicates her time to various charitable initiatives. Her commitment to improving the lives of others has been instrumental in creating a strong sense of community within Oak Valley.
Through their unique talents and unwavering dedication, Laura, Kevin, and Rachel have woven themselves into the fabric of Oak Valley, helping to create a vibrant and thriving small town."""

# Prefill for Claude's response
PREFILL = "<individuals>"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN:")
print(PROMPT)
print("\nASSISTANT TURN:")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

如果你想在不改動上面內容的情況下實驗課程裡的 prompt，可以捲到 notebook 最底下的[**範例遊樂場**](#example-playground)。

---

## 練習
- [練習 7.1 - 用範例做 email 格式化](#exercise-71---email-formatting-via-examples)

### 練習 7.1 - 用範例做 email 格式化
我們要重做練習 6.2，但這次要編輯 `PROMPT`，用 email 加上正確分類（和格式）的「few-shot」範例，讓 Claude 輸出正確答案。我們希望 Claude 輸出的*最後一個*字母就是類別的字母。

忘了哪個字母對應哪個類別的話，看 `EMAILS` 清單裡每封旁邊的註解。

別忘了這些是 email 的類別：
- (A) Pre-sale question
- (B) Broken or defective item
- (C) Billing question
- (D) Other (please explain)

```python
# Prompt template with a placeholder for the variable content
PROMPT = """Please classify this email as either green or blue: {email}"""

# Prefill for Claude's response
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

# Iterate through list of emails
for i,email in enumerate(EMAILS):
    
    # Substitute the email text into the email placeholder variable
    formatted_prompt = PROMPT.format(email=email)
   
    # Get Claude's response
    response = get_completion(formatted_prompt, prefill=PREFILL)

    # Grade Claude's response
    grade = any([bool(re.search(ans, response[-1])) for ans in ANSWERS[i]])
    
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
from hints import exercise_7_1_hint; print(exercise_7_1_hint)
```

還是卡住？執行下面的 cell 看範例解答。

```python
from hints import exercise_7_1_solution; print(exercise_7_1_solution)
```

### 恭喜！

如果你解完到目前為止的所有練習，就可以進入下一章了。Happy prompting！

---

## 範例遊樂場

這裡可以自由實驗本課的 prompt 範例，調整 prompt 看看 Claude 的回應怎麼變。

```python
# Prompt
PROMPT = "Will Santa bring me presents on Christmas?"

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt
PROMPT = """Please complete the conversation by writing the next line, speaking as "A".
Q: Is the tooth fairy real?
A: Of course, sweetie. Wrap up your tooth and put it under your pillow tonight. There might be something waiting for you in the morning.
Q: Will Santa bring me presents on Christmas?"""

# Print Claude's response
print(get_completion(PROMPT))
```

```python
# Prompt template with a placeholder for the variable content
PROMPT = """Silvermist Hollow, a charming village, was home to an extraordinary group of individuals.
Among them was Dr. Liam Patel, a neurosurgeon who revolutionized surgical techniques at the regional medical center.
Olivia Chen was an innovative architect who transformed the village's landscape with her sustainable and breathtaking designs.
The local theater was graced by the enchanting symphonies of Ethan Kovacs, a professionally-trained musician and composer.
Isabella Torres, a self-taught chef with a passion for locally sourced ingredients, created a culinary sensation with her farm-to-table restaurant, which became a must-visit destination for food lovers.
These remarkable individuals, each with their distinct talents, contributed to the vibrant tapestry of life in Silvermist Hollow.
<individuals>
1. Dr. Liam Patel [NEUROSURGEON]
2. Olivia Chen [ARCHITECT]
3. Ethan Kovacs [MISICIAN AND COMPOSER]
4. Isabella Torres [CHEF]
</individuals>

At the heart of the town, Chef Oliver Hamilton has transformed the culinary scene with his farm-to-table restaurant, Green Plate. Oliver's dedication to sourcing local, organic ingredients has earned the establishment rave reviews from food critics and locals alike.
Just down the street, you'll find the Riverside Grove Library, where head librarian Elizabeth Chen has worked diligently to create a welcoming and inclusive space for all. Her efforts to expand the library's offerings and establish reading programs for children have had a significant impact on the town's literacy rates.
As you stroll through the charming town square, you'll be captivated by the beautiful murals adorning the walls. These masterpieces are the work of renowned artist, Isabella Torres, whose talent for capturing the essence of Riverside Grove has brought the town to life.
Riverside Grove's athletic achievements are also worth noting, thanks to former Olympic swimmer-turned-coach, Marcus Jenkins. Marcus has used his experience and passion to train the town's youth, leading the Riverside Grove Swim Team to several regional championships.
<individuals>
1. Oliver Hamilton [CHEF]
2. Elizabeth Chen [LIBRARIAN]
3. Isabella Torres [ARTIST]
4. Marcus Jenkins [COACH]
</individuals>

Oak Valley, a charming small town, is home to a remarkable trio of individuals whose skills and dedication have left a lasting impact on the community.
At the town's bustling farmer's market, you'll find Laura Simmons, a passionate organic farmer known for her delicious and sustainably grown produce. Her dedication to promoting healthy eating has inspired the town to embrace a more eco-conscious lifestyle.
In Oak Valley's community center, Kevin Alvarez, a skilled dance instructor, has brought the joy of movement to people of all ages. His inclusive dance classes have fostered a sense of unity and self-expression among residents, enriching the local arts scene.
Lastly, Rachel O'Connor, a tireless volunteer, dedicates her time to various charitable initiatives. Her commitment to improving the lives of others has been instrumental in creating a strong sense of community within Oak Valley.
Through their unique talents and unwavering dedication, Laura, Kevin, and Rachel have woven themselves into the fabric of Oak Valley, helping to create a vibrant and thriving small town."""

# Prefill for Claude's response
PREFILL = "<individuals>"

# Print Claude's response
print("--------------------------- Full prompt with variable substutions ---------------------------")
print("USER TURN:")
print(PROMPT)
print("\nASSISTANT TURN:")
print(PREFILL)
print("\n------------------------------------- Claude's response -------------------------------------")
print(get_completion(PROMPT, prefill=PREFILL))
```

## 重點整理

- 給範例是同時控制答案正確性與輸出格式最有效的手段之一。
- Shot 的數量就是 prompt 裡的範例數量，zero-shot 是 0 個，one-shot 是 1 個。
- 要調語氣時，給理想回應的範例比用文字描述語氣更省力。
- 格式要求也可以靠範例傳達，Claude 會自己歸納規則。
- 在 `assistant` 回合放開頭標籤（如 `<individuals>`），能讓輸出更穩定。

## 練習

1. 在練習 7.1 先放 1 個範例，再增加到 3 個，比較分類準確度。
2. 把範例的 email 換成跟測試資料差異很大的類型，觀察 Claude 是否還能正確分類。
3. 在練習 7.1 的範例裡加一封故意歸到 (D) 的 email 並附上簡短說明，看 Claude 對 (D) 類的輸出是否也遵循同樣格式。
