---
translated: true
source: misc/how_to_enable_json_mode.ipynb
---

# 用 prompt 讓 Claude 輸出 "JSON mode"

> 原文：[misc/how_to_enable_json_mode.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/how_to_enable_json_mode.ipynb)

不靠 constrained sampling，只用有效的 prompting 技巧讓 Claude 穩定輸出 JSON。

## 這篇在做什麼

示範幾種只靠 prompt 就能讓 Claude 輸出可解析 JSON 的技巧：擷取 code fence、prefill、stop sequence 和 XML tag。

## 學完你會

- 用字串解析從回應中抽出 JSON
- 用 prefill `{` 跳過前言，再用 stop sequence 去掉 JSON 後面的文字
- 讓 Claude 把多個 JSON 放進 XML tag，並用 regex 一次抽出

## 開跑前

需要 Anthropic API key。

> **模型說明：**這份 notebook 用的是 `claude-haiku-4-5`，是舊版模型，因為下面示範的 assistant-message prefill 只有 Claude Haiku 4.5 接受。所有現行模型（Claude Opus 5.5、Claude Sonnet 5.5、Claude Fable 5.1、Claude Haiku 5.5）遇到以 assistant message 結尾的 request 都會回 400。現行模型要保證 JSON，請改用 [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)（`output_config.format` 加 JSON schema）；後面的 tag 加 stop sequence 技巧在所有模型都能用。

這份教學示範不靠 constrained sampling、只用 prompting 技巧讓 Claude 穩定輸出 JSON。如果你需要保證符合 JSON schema 的輸出，現行的 Claude 模型也支援 [structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)（`output_config.format`）；這裡的技巧在你想讓模型在 JSON 前後自由推理，或只能靠 prompt 時還是很有用。

先看看 Claude 的預設行為。

```python
%pip install anthropic
```

```python
import json
import re
from pprint import pprint

from anthropic import Anthropic
```

```python
client = Anthropic()
# See the model note at the top: prefill (used below) is only accepted on the legacy
# Claude Haiku 4.5; current models, including Claude Haiku 5.5, return a 400 for it.
MODEL_NAME = "claude-haiku-4-5"
```

```python
message = (
    client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": "Give me a JSON dict with names of famous athletes & their sports.",
            },
        ],
    )
    .content[0]
    .text
)
print(message)
```

??? note "輸出"

    ```text
    Here is a JSON dictionary with names of famous athletes and their respective sports:

    {
      "athletes": [
        {
          "name": "Usain Bolt",
          "sport": "Track and Field"
        },
        {
          "name": "Michael Phelps",
          "sport": "Swimming"
        },
        {
          "name": "Serena Williams",
          "sport": "Tennis"
        },
        {
          "name": "LeBron James",
          "sport": "Basketball"
        },
        {
          "name": "Lionel Messi",
          "sport": "Soccer"
        },
        {
          "name": "Simone Biles",
          "sport": "Gymnastics"
        },
        {
          "name": "Tom Brady",
          "sport": "American Football"
        },
        {
          "name": "Muhammad Ali",
          "sport": "Boxing"
        },
        {
          "name": "Nadia Comaneci",
          "sport": "Gymnastics"
        },
    ... (省略 14 行)
    ```

Claude 照指示輸出了一個漂亮的 dictionary，我們可以用程式碼抽出來：

```python
def extract_json(response):
    json_start = response.index("{")
    json_end = response.rfind("}")
    return json.loads(response[json_start : json_end + 1])


extract_json(message)
```

??? note "輸出"

    ```text
    {'athletes': [{'name': 'Usain Bolt', 'sport': 'Track and Field'},
      {'name': 'Michael Phelps', 'sport': 'Swimming'},
      {'name': 'Serena Williams', 'sport': 'Tennis'},
      {'name': 'LeBron James', 'sport': 'Basketball'},
      {'name': 'Lionel Messi', 'sport': 'Soccer'},
      {'name': 'Simone Biles', 'sport': 'Gymnastics'},
      {'name': 'Tom Brady', 'sport': 'American Football'},
      {'name': 'Muhammad Ali', 'sport': 'Boxing'},
      {'name': 'Nadia Comaneci', 'sport': 'Gymnastics'},
      {'name': 'Michael Jordan', 'sport': 'Basketball'},
      {'name': 'Pelé', 'sport': 'Soccer'},
      {'name': 'Roger Federer', 'sport': 'Tennis'}]}
    ```

但如果想讓 Claude 跳過前言、直接輸出 JSON 呢？一個簡單的方法是 prefill Claude 的回應，放一個 "{" 字元。

```python
message = (
    client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": "Give me a JSON dict with names of famous athletes & their sports.",
            },
            {"role": "assistant", "content": "Here is the JSON requested:\n{"},
        ],
    )
    .content[0]
    .text
)
print(message)
```

??? note "輸出"

    ```text

       "athletes":[
          {
             "name":"Michael Jordan",
             "sport":"Basketball"
          },
          {
             "name":"Babe Ruth",
             "sport":"Baseball"
          },
          {
             "name":"Muhammad Ali",
             "sport":"Boxing"
          },
          {
             "name":"Serena Williams",
             "sport":"Tennis"
          },
          {
             "name":"Wayne Gretzky",
             "sport":"Hockey"
          },
          {
             "name":"Michael Phelps",
             "sport":"Swimming"
          },
          {
             "name":"Usain Bolt",
             "sport":"Track and Field"
          },
          {
             "name":"Mia Hamm",
             "sport":"Soccer"
          },
          {
             "name":"Michael Schumacher",
             "sport":"Formula 1 Racing"
          },
          {
             "name":"Simone Biles",
    ... (省略 4 行)
    ```

現在只要把 prefill 的 "{" 補回去，就能抽出 JSON。

```python
output_json = json.loads("{" + message[: message.rfind("}") + 1])
output_json
```

??? note "輸出"

    ```text
    {'athletes': [{'name': 'Michael Jordan', 'sport': 'Basketball'},
      {'name': 'Babe Ruth', 'sport': 'Baseball'},
      {'name': 'Muhammad Ali', 'sport': 'Boxing'},
      {'name': 'Serena Williams', 'sport': 'Tennis'},
      {'name': 'Wayne Gretzky', 'sport': 'Hockey'},
      {'name': 'Michael Phelps', 'sport': 'Swimming'},
      {'name': 'Usain Bolt', 'sport': 'Track and Field'},
      {'name': 'Mia Hamm', 'sport': 'Soccer'},
      {'name': 'Michael Schumacher', 'sport': 'Formula 1 Racing'},
      {'name': 'Simone Biles', 'sport': 'Gymnastics'}]}
    ```

如果 prompt 很長很複雜、裡面有多個 JSON 輸出，用字串搜尋 "{" 和 "}" 行不通，你也可以讓 Claude 把每個 JSON 項目放在指定的 tag 裡，方便之後抽取。

```python
message = (
    client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": """Give me a JSON dict with the names of 5 famous athletes & their sports.
Put this dictionary in <athlete_sports> tags.

Then, for each athlete, output an additional JSON dictionary. In each of these additional dictionaries:
- Include two keys: the athlete's first name and last name.
- For the values, list three words that start with the same letter as that name.
Put each of these additional dictionaries in separate <athlete_name> tags.""",
            },
            {"role": "assistant", "content": "Here is the JSON requested:"},
        ],
    )
    .content[0]
    .text
)
print(message)
```

??? note "輸出"

    ```text
     

    <athlete_sports>
    {
      "Michael Jordan": "Basketball",
      "Serena Williams": "Tennis",
      "Lionel Messi": "Soccer", 
      "Usain Bolt": "Track and Field",
      "Michael Phelps": "Swimming"
    }
    </athlete_sports>

    <athlete_name>
    {
      "first": ["Magnificent", "Motivating", "Memorable"],
      "last": ["Joyful", "Jumping", "Jocular"]
    }
    </athlete_name>

    <athlete_name>
    {
      "first": ["Skillful", "Strong", "Superstar"],
      "last": ["Winning", "Willful", "Wise"]
    }
    </athlete_name>

    <athlete_name>
    {
      "first": ["Legendary", "Lively", "Leaping"],
      "last": ["Magical", "Marvelous", "Masterful"]  
    }
    </athlete_name>

    <athlete_name>
    {
      "first": ["Unbeatable", "Unbelievable", "Unstoppable"],
      "last": ["Brave", "Bold", "Brilliant"]
    }
    </athlete_name>

    ... (省略 6 行)
    ```

接著用 regex 取出所有 dictionary。

```python
import re


def extract_between_tags(tag: str, string: str, strip: bool = False) -> list[str]:
    ext_list = re.findall(f"<{tag}>(.+?)</{tag}>", string, re.DOTALL)
    if strip:
        ext_list = [e.strip() for e in ext_list]
    return ext_list


athlete_sports_dict = json.loads(extract_between_tags("athlete_sports", message)[0])
athlete_name_dicts = [json.loads(d) for d in extract_between_tags("athlete_name", message)]
```

```python
pprint(athlete_sports_dict)
```

??? note "輸出"

    ```text
    {'Lionel Messi': 'Soccer',
     'Michael Jordan': 'Basketball',
     'Michael Phelps': 'Swimming',
     'Serena Williams': 'Tennis',
     'Usain Bolt': 'Track and Field'}
    ```

```python
pprint(athlete_name_dicts, width=1)
```

??? note "輸出"

    ```text
    [{'first': ['Magnificent',
                'Motivating',
                'Memorable'],
      'last': ['Joyful',
               'Jumping',
               'Jocular']},
     {'first': ['Skillful',
                'Strong',
                'Superstar'],
      'last': ['Winning',
               'Willful',
               'Wise']},
     {'first': ['Legendary',
                'Lively',
                'Leaping'],
      'last': ['Magical',
               'Marvelous',
               'Masterful']},
     {'first': ['Unbeatable',
                'Unbelievable',
                'Unstoppable'],
      'last': ['Brave',
               'Bold',
               'Brilliant']},
     {'first': ['Marvelous',
                'Methodical',
                'Medalist'],
      'last': ['Powerful',
               'Persevering',
               'Precise']}]
    ```

回顧一下：

- 可以用字串解析，抽出 "```json" and "```" 之間的文字來取得 JSON。
- 可以用部分的 Assistant message 去掉 JSON *前面*的前言（不過這樣 Claude 就沒辦法在輸出 JSON 前先做 "Chain of Thought" 來變聰明）。
- 可以用 stop sequence 去掉 JSON *後面*的文字。
- 可以指示 Claude 把 JSON 放在 XML tag 裡，複雜的 prompt 之後比較好收集。

## 重點整理

- 沒有 constrained sampling 時，JSON 輸出靠 prompt 加解析程式碼，兩邊都要處理。
- prefill 能去掉前言，但會犧牲先推理再輸出的空間，而且現行模型不再接受。
- stop sequence 負責截掉 JSON 之後多餘的文字。
- 多個 JSON 的情況，用 XML tag 包起來最好抽取。
- 需要保證 schema 時，現行模型用 structured outputs。

## 練習

1. 把範例的 prompt 換成要求輸出一個含三個欄位的 JSON，用 prefill 加 `json.loads` 解析。
2. 加上 `stop_sequences`，確認 JSON 後面沒有多餘文字。
3. 要求輸出 3 個各放在 `<item>` tag 的 JSON，寫一個 regex 把它們全部抽成 list。
