---
translated: true
source: misc/building_moderation_filter.ipynb
---

# 用 Claude 建立內容審核過濾器

> 原文：[misc/building_moderation_filter.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/building_moderation_filter.ipynb)

在 prompt 裡定義規則與類別，建立可客製化的內容審核過濾器。

## 這篇在做什麼

這份指南示範怎麼用 Claude 為使用者產生的文字建立內容審核過濾器。核心想法是把審核規則和類別直接寫在 prompt 裡，方便客製化和實驗。

## 學完你會

- 寫出定義 ALLOW 和 BLOCK 類別的審核 prompt，並用 Python 批次審核留言。
- 改寫類別描述，把過濾器改成適合別的社群（例如雲霄飛車討論區的離題檢查）。
- 用 chain-of-thought 和 few-shot 範例，提升模糊案例的判斷品質。

## 開跑前

需要 Anthropic API key。

這份指南會示範如何用 Claude 為使用者產生的文字建立內容審核過濾器。核心想法是把審核規則和類別直接定義在 prompt 裡，讓客製化和實驗都很容易。

## 基本做法
基本做法是給 Claude 一個 prompt，描述你想過濾的類別（例如「ALLOW」和「BLOCK」），並附上每個類別應該涵蓋哪些內容的詳細描述或範例。接著把要分類的使用者文字插入 prompt，請 Claude 根據提供的準則分類。

這是一個 prompt 結構的範例：

```text
You are a content moderation expert tasked with categorizing user-generated text based on the following guidelines:

BLOCK CATEGORY:
- [Description or examples of content that should be blocked]

ALLOW CATEGORY:
- [Description or examples of content that is allowed]

Here is the user-generated text to categorize:
<user_text>{{USER_TEXT}}</user_text>

Based on the guidelines above, classify this text as either ALLOW or BLOCK. Return nothing else.
```

使用時，把 `{{USER_TEXT}}` 換成實際要分類的使用者文字，再透過 Claude API 把 prompt 送給 Claude。Claude 的回應應該是「ALLOW」或「BLOCK」，表示依你提供的準則，這段文字該怎麼處理。

## 使用範例
這是示範這個做法的 Python 程式碼範例：

```python
%pip install anthropic
```

```python
from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-haiku-5-5"


def moderate_text(user_text, guidelines):
    prompt_template = """
    You are a content moderation expert tasked with categorizing user-generated text based on the following guidelines:

    {guidelines}

    Here is the user-generated text to categorize:
    <user_text>{user_text}</user_text>

    Based on the guidelines above, classify this text as either ALLOW or BLOCK. Return nothing else.
    """

    # Format the prompt with the user text
    prompt = prompt_template.format(user_text=user_text, guidelines=guidelines)

    # Send the prompt to Claude and get the response
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Read the text block by type: the response may start with a thinking block
    return "".join(block.text for block in response.content if block.type == "text").strip()
```

下面是怎麼用這個 function 審核一個使用者留言陣列：

```python
example_guidelines = """BLOCK CATEGORY:
    - Promoting violence, illegal activities, or hate speech
    - Explicit sexual content
    - Harmful misinformation or conspiracy theories

    ALLOW CATEGORY:
    - Most other content is allowed, as long as it is not explicitly disallowed
"""

user_comments = [
    "This movie was great, I really enjoyed it. The main actor really killed it!",
    "Delete this post now or you better hide. I am coming after you and your family.",
    "Stay away from the 5G cellphones!! They are using 5G to control you.",
    "Thanks for the helpful information!",
]

for comment in user_comments:
    classification = moderate_text(comment, example_guidelines)
    print(f"Comment: {comment}\nClassification: {classification}\n")
```

??? note "輸出"

    ```text
    Comment: This movie was great, I really enjoyed it. The main actor really killed it!
    Classification: ALLOW

    Comment: Delete this post now or you better hide. I am coming after you and your family.
    Classification: BLOCK

    Comment: Stay away from the 5G cellphones!! They are using 5G to control you.
    Classification: BLOCK

    Comment: Thanks for the helpful information!
    Classification: ALLOW
    ```

## 客製化

這個做法的主要好處之一，是你可以輕鬆修改 prompt 裡「BLOCK」和「ALLOW」類別的描述或範例，來客製化審核規則。這讓你能依特定需求或偏好微調過濾。

例如，如果你想讓 Claude 審核雲霄飛車愛好者論壇，確保貼文不離題，就可以相應地更新「ALLOW」和「BLOCK」的類別描述：

```python
rollercoaster_guidelines = """BLOCK CATEGORY:
- Content that is not related to rollercoasters, theme parks, or the amusement industry
- Explicit violence, hate speech, or illegal activities
- Spam, advertisements, or self-promotion

ALLOW CATEGORY:
- Discussions about rollercoaster designs, ride experiences, and park reviews
- Sharing news, rumors, or updates about new rollercoaster projects
- Respectful debates about the best rollercoasters, parks, or ride manufacturers
- Some mild profanity or crude language, as long as it is not directed at individuals
"""

post_titles = [
    "Top 10 Wildest Inversions on Steel Coasters",
    "My Review of the New RMC Raptor Coaster at Cedar Point",
    "Best Places to Buy Cheap Hiking Gear",
    "Rumor: Is Six Flags Planning a Giga Coaster for 2025?",
    "My Thoughts on the Latest Marvel Movie",
]

for title in post_titles:
    classification = moderate_text(title, rollercoaster_guidelines)
    print(f"Title: {title}\nClassification: {classification}\n")
```

??? note "輸出"

    ```text
    Title: Top 10 Wildest Inversions on Steel Coasters
    Classification: ALLOW

    Title: My Review of the New RMC Raptor Coaster at Cedar Point
    Classification: ALLOW

    Title: Best Places to Buy Cheap Hiking Gear
    Classification: BLOCK

    Title: Rumor: Is Six Flags Planning a Giga Coaster for 2025?
    Classification: ALLOW

    Title: My Thoughts on the Latest Marvel Movie
    Classification: BLOCK
    ```

## 用 Chain of Thought (CoT) 提升表現

可以強化 Claude 內容審核能力的一個技巧是「chain-of-thought」（CoT）prompting。這種做法鼓勵 Claude 把推理過程拆成一步一步的思考鏈，而不是只給最終輸出。

要在審核中運用 chain of thought，可以修改 prompt，明確指示 Claude 在 `<thinking>` 標籤內把過程拆成清楚的步驟。範例如下：

```python
cot_prompt = """You are a content moderation expert tasked with categorizing user-generated text based on the following guidelines:

BLOCK CATEGORY:
- Content that is not related to rollercoasters, theme parks, or the amusement industry
- Explicit violence, hate speech, or illegal activities
- Spam, advertisements, or self-promotion

ALLOW CATEGORY:
- Discussions about rollercoaster designs, ride experiences, and park reviews
- Sharing news, rumors, or updates about new rollercoaster projects
- Respectful debates about the best rollercoasters, parks, or ride manufacturers
- Some mild profanity or crude language, as long as it is not directed at individuals

First, inside of <thinking> tags, identify any potentially concerning aspects of the post based on the guidelines below and consider whether those aspects are serious enough to block the post or not. Finally, classify this text as either ALLOW or BLOCK inside <output> tags. Return nothing else.

Given those instructions, here is the post to categorize:

<user_post>{user_post}</user_post>"""

user_post = "Introducing my new band - Coaster Shredders. Check us out on YouTube!!"

response = client.messages.create(
    model=MODEL_NAME,
    max_tokens=2048,
    messages=[{"role": "user", "content": cot_prompt.format(user_post=user_post)}],
)
response = "".join(block.text for block in response.content if block.type == "text")

print(response)
```

??? note "輸出"

    ```text
    <thinking>
    The post promotes a band called "Coaster Shredders" and asks readers to check out its YouTube channel. That is self-promotion, which the BLOCK guidelines name explicitly. The band name contains a rollercoaster reference, but the post does not discuss coasters, parks, rides, or the amusement industry. It contains no violence, hate speech, or illegal content. The promotional nature is the deciding factor.
    </thinking>

    <output>BLOCK</output>
    ```

## 用範例提升表現
另一個提升表現的技巧是在 prompt 加入幾個範例，也就是給 Claude 一些初始的訓練資料或「few-shot learning」，讓它更理解想要的分類方式。對於細微或模糊的案例特別有幫助，因為光看文字描述，類別界線可能不夠清楚。下面是修改 prompt template 加入範例的做法：

```python
examples_prompt = """You are a content moderation expert tasked with categorizing user-generated text based on the following guidelines:

BLOCK CATEGORY:
- Content that is not related to rollercoasters, theme parks, or the amusement industry
- Explicit violence, hate speech, or illegal activities
- Spam, advertisements, or self-promotion

ALLOW CATEGORY:
- Discussions about rollercoaster designs, ride experiences, and park reviews
- Sharing news, rumors, or updates about new rollercoaster projects
- Respectful debates about the best rollercoasters, parks, or ride manufacturers
- Some mild profanity or crude language, as long as it is not directed at individuals

Here are some examples:
<examples>
Text: I'm selling weight loss products, check my link to buy!
Category: BLOCK

Text: I hate my local park, the operations and customer service are terrible. I wish that place would just burn down.
Category: BLOCK

Text: Did anyone ride the new RMC raptor Trek Plummet 2 yet? I've heard it's insane!
Category: ALLOW

Text: Hercs > B&Ms. That's just facts, no cap! Arrow > Intamin for classic woodies too.
Category: ALLOW
</examples>

Given those examples, here is the user-generated text to categorize:
<user_text>{user_text}</user_text>

Based on the guidelines above, classify this text as either ALLOW or BLOCK. Return nothing else."""

user_post = "Why Boomerang Coasters Ain't It (Don't @ Me)"

response = client.messages.create(
    model=MODEL_NAME,
    max_tokens=2048,
    messages=[{"role": "user", "content": examples_prompt.format(user_text=user_post)}],
)
response = "".join(block.text for block in response.content if block.type == "text")

print(response)
```

??? note "輸出"

    ```text
    ALLOW
    ```

## 重點整理

- 審核規則寫在 prompt 裡，不用訓練 model，改規則就是改文字。
- 輸出限制成 ALLOW 或 BLOCK 這種固定標籤，程式才好處理。
- 換社群只要重寫類別描述，同一套程式碼可以重複使用。
- 加上 CoT 讓 Claude 先推理，能改善複雜案例的判斷。
- 模糊案例用 few-shot 範例劃清界線，比文字描述更有效。

## 練習

1. 把審核函式的類別描述改成你熟悉的社群規則，用 5 則自己編的留言測試。
2. 把 CoT 版本的輸出改成只保留 `<thinking>` 之後的最終標籤，並用程式解析出來。
3. 找一則你的過濾器會誤判的留言，把它加進 few-shot 範例，再看判斷是否改變。
