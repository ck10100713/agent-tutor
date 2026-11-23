---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Named_Entity_Recognition_to_enrich_text.ipynb
---

# 用 Named Entity Recognition 豐富文字內容

> 原文：[examples/Named_Entity_Recognition_to_enrich_text.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Named_Entity_Recognition_to_enrich_text.ipynb)



## 這篇在做什麼

用 chat completion 加 function calling 做 NER（命名實體辨識），把一段文字裡的人名、地名、事件等抓出來，再幫它們補上 Wikipedia 連結。最後還會教你怎麼從 response 算出這次呼叫花了多少錢。

## 學完你會

- 用 function calling 讓模型直接回傳符合 JSON schema 的結構化結果。
- 用 system、assistant、user 三種 message 組出 one-shot 的 NER prompt。
- 從 response 的 `usage` 欄位估算 token 用量和 API 成本。

## 開跑前

需要 `OPENAI_API_KEY`，呼叫 OpenAI API 會產生費用。

## Named Entity Recognition (NER) 豐富文字

`Named Entity Recognition` (NER) 是 `Natural Language Processing` 的一種任務，把文字裡的命名實體（NE）找出來，分到預先定義好的語意類別，例如人物、組織、地點、事件、時間表達和數量。把原始文字轉成結構化資訊之後，資料更好用，資訊抽取、資料彙整、分析、社群媒體監控這類工作都會比較容易。

這個 notebook 示範怎麼用 [chat completion](https://platform.openai.com/docs/api-reference/chat) 和 [functions-calling](https://platform.openai.com/docs/guides/gpt/function-calling) 做 NER，把文字加上指向 Wikipedia 這類知識庫的連結：

**原文：**

*In Germany, in 1440, goldsmith Johannes Gutenberg invented the movable-type printing press. His work led to an information revolution and the unprecedented mass-spread of literature throughout Europe. Modelled on the design of the existing screw presses, a single Renaissance movable-type printing press could produce up to 3,600 pages per workday.*

**加上 Wikipedia 連結後：**

*In [Germany](https://en.wikipedia.org/wiki/Germany), in 1440, goldsmith [Johannes Gutenberg]() invented the [movable-type printing press](https://en.wikipedia.org/wiki/Movable_Type). His work led to an [information revolution](https://en.wikipedia.org/wiki/Information_revolution) and the unprecedented mass-spread of literature throughout [Europe](https://en.wikipedia.org/wiki/Europe). Modelled on the design of the existing screw presses, a single [Renaissance](https://en.wikipedia.org/wiki/Renaissance) [movable-type printing press](https://en.wikipedia.org/wiki/Movable_Type) could produce up to 3,600 pages per workday.*

**推論成本：** 這個 notebook 也會示範怎麼估算 OpenAI API 的費用。

### 1. 環境設定

#### 1.1 安裝/升級 Python 套件

```python
%pip install --upgrade openai --quiet
%pip install --upgrade nlpia2-wikipedia --quiet
%pip install --upgrade tenacity --quiet
```

??? note "輸出"

    ```text
    Note: you may need to restart the kernel to use updated packages.
    Note: you may need to restart the kernel to use updated packages.
    Note: you may need to restart the kernel to use updated packages.
    ```

#### 1.2 載入套件和 OPENAI_API_KEY

API key 可以在 OpenAI 網頁介面產生，細節看 https://platform.openai.com/account/api-keys 。

這個 notebook 使用最新的 OpenAI 模型 `gpt-3.5-turbo-0613` 和 `gpt-4-0613`。

```python
import json
import logging
import os

import openai
import wikipedia

from typing import Optional
from IPython.display import display, Markdown
from tenacity import retry, wait_random_exponential, stop_after_attempt

logging.basicConfig(level=logging.INFO, format=' %(asctime)s - %(levelname)s - %(message)s')

OPENAI_MODEL = 'gpt-3.5-turbo-0613'

client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

### 2. 定義要辨識的 NER 標籤

我們先定義一組標準的 NER 標籤，展示各種使用情境。不過這次的任務是替文字補知識庫連結，實際上只會用到其中一部分。

```python
labels = [
    "person",      # people, including fictional characters
    "fac",         # buildings, airports, highways, bridges
    "org",         # organizations, companies, agencies, institutions
    "gpe",         # geopolitical entities like countries, cities, states
    "loc",         # non-gpe locations
    "product",     # vehicles, foods, appareal, appliances, software, toys 
    "event",       # named sports, scientific milestones, historical events
    "work_of_art", # titles of books, songs, movies
    "law",         # named laws, acts, or legislations
    "language",    # any named language
    "date",        # absolute or relative dates or periods
    "time",        # time units smaller than a day
    "percent",     # percentage (e.g., "twenty percent", "18%")
    "money",       # monetary values, including unit
    "quantity",    # measurements, e.g., weight or distance
]
```

### 3. 準備 messages

[chat completions API](https://platform.openai.com/docs/guides/gpt/chat-completions-api) 的輸入是一串 message，輸出是模型產生的 message。chat 格式主要是為多輪對話設計的，但拿來做沒有前文的單輪任務也一樣好用。這裡我們會分別準備 system、assistant、user 三種角色的 message。

#### 3.1 System Message

`system message`（prompt）定義 assistant 的角色和任務，決定它的行為。我們也在這裡列出想辨識的實體標籤。

雖然也可以直接用 prompt 要求模型指定輸出格式，但 `gpt-3.5-turbo-0613` 和 `gpt-4-0613` 都經過 fine-tuning，會判斷什麼時候該呼叫 function，並且回傳符合 function signature 的 `JSON`。這讓 prompt 可以寫得更短，也能直接拿到結構化資料。

```python
def system_message(labels):
    return f"""
You are an expert in Natural Language Processing. Your task is to identify common Named Entities (NER) in a given text.
The possible common Named Entities (NER) types are exclusively: ({", ".join(labels)})."""
```

#### 3.2 Assistant Message

`Assistant messages` 通常放之前 assistant 的回覆。不過像這個情境，也可以拿來寫範例，示範想要的行為。OpenAI 的模型可以做 `zero-shot` 的 NER，但我們發現 `one-shot` 的結果比較準。

```python
def assisstant_message():
    return f"""
EXAMPLE:
    Text: 'In Germany, in 1440, goldsmith Johannes Gutenberg invented the movable-type printing press. His work led to an information revolution and the unprecedented mass-spread / 
    of literature throughout Europe. Modelled on the design of the existing screw presses, a single Renaissance movable-type printing press could produce up to 3,600 pages per workday.'
    {{
        "gpe": ["Germany", "Europe"],
        "date": ["1440"],
        "person": ["Johannes Gutenberg"],
        "product": ["movable-type printing press"],
        "event": ["Renaissance"],
        "quantity": ["3,600 pages"],
        "time": ["workday"]
    }}
--"""
```

#### 3.3 User Message

`user message` 放這次任務要處理的文字：

```python
def user_message(text):
    return f"""
TASK:
    Text: {text}
"""
```

### 4. OpenAI Functions（和工具函式）

呼叫 OpenAI API 時，可以把 `functions` 描述給 `gpt-3.5-turbo-0613` 和 `gpt-4-0613`，模型會自己判斷要不要輸出一個 `JSON` 物件，裡面是呼叫那些 `functions` 的參數。要注意 [chat completions API](https://platform.openai.com/docs/guides/gpt/chat-completions-api) 不會真的執行 `function`，它只回傳 `JSON`，再由你的程式拿去呼叫 `function`。更多細節看 [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)。

我們的 function `enrich_entities(text, label_entities)` 接收一段文字，以及一個放了標籤和實體的 dictionary，然後把辨識出的實體對應到 Wikipedia 文章連結。

```python
@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
def find_link(entity: str) -> Optional[str]:
    """
    Finds a Wikipedia link for a given entity.
    """
    try:
        titles = wikipedia.search(entity)
        if titles:
            # naively consider the first result as the best
            page = wikipedia.page(titles[0])
            return page.url
    except (wikipedia.exceptions.WikipediaException) as ex:
        logging.error(f'Error occurred while searching for Wikipedia link for entity {entity}: {str(ex)}')

    return None
```

```python
def find_all_links(label_entities:dict) -> dict:
    """ 
    Finds all Wikipedia links for the dictionary entities in the whitelist label list.
    """
    whitelist = ['event', 'gpe', 'org', 'person', 'product', 'work_of_art']
    
    return {e: find_link(e) for label, entities in label_entities.items() 
                            for e in entities
                            if label in whitelist}
```

```python
def enrich_entities(text: str, label_entities: dict) -> str:
    """
    Enriches text with knowledge base links.
    """
    entity_link_dict = find_all_links(label_entities)
    logging.info(f"entity_link_dict: {entity_link_dict}")
    
    for entity, link in entity_link_dict.items():
        text = text.replace(entity, f"[{entity}]({link})")

    return text
```

### 4. ChatCompletion

前面提過，`gpt-3.5-turbo-0613` 和 `gpt-4-0613` 經過 fine-tuning，會偵測什麼時候該呼叫 `function`，也能產生符合 `function` signature 的 `JSON`。流程如下：

1. 定義 `function` 和對應的 `JSON` Schema。
2. 用 `messages`、`tools` 和 `tool_choice` 參數呼叫模型。
3. 把輸出轉成 `JSON` 物件，再用模型給的 `arguments` 呼叫 `function`。

實際應用中，你可能會把 `function` 的結果當成新的 message 加回去，再呼叫一次模型，讓它對使用者總結結果。這裡不需要這一步。

*注意：真實情境下，強烈建議在執行動作之前加上使用者確認流程。*

#### 4.1 定義 Function 和 JSON schema

我們要的是模型輸出一個「標籤對應辨識實體」的 dictionary：

```python
{   
    "gpe": ["Germany", "Europe"],   
    "date": ["1440"],   
    "person": ["Johannes Gutenberg"],   
    "product": ["movable-type printing press"],   
    "event": ["Renaissance"],   
    "quantity": ["3,600 pages"],   
    "time": ["workday"]   
}   
```
所以要定義對應的 `JSON` schema，傳給 `tools` 參數：

```python
def generate_functions(labels: dict) -> list:
    return [
        {   
            "type": "function",
            "function": {
                "name": "enrich_entities",
                "description": "Enrich Text with Knowledge Base Links",
                "parameters": {
                    "type": "object",
                        "properties": {
                            "r'^(?:' + '|'.join({labels}) + ')$'": 
                            {
                                "type": "array",
                                "items": {
                                    "type": "string"
                                }
                            }
                        },
                        "additionalProperties": False
                },
            }
        }
    ]
```

#### 4.2 Chat Completion

接著呼叫模型。這裡把 `tool_choice` 參數設成 `{"type": "function", "function" : {"name": "enrich_entities"}}`，強制 API 使用指定的 function。

```python
@retry(wait=wait_random_exponential(min=1, max=10), stop=stop_after_attempt(5))
def run_openai_task(labels, text):
    messages = [
          {"role": "system", "content": system_message(labels=labels)},
          {"role": "assistant", "content": assisstant_message()},
          {"role": "user", "content": user_message(text=text)}
      ]

    # TODO: functions and function_call are deprecated, need to be updated
    # See: https://platform.openai.com/docs/api-reference/chat/create#chat-create-tools
    response = openai.chat.completions.create(
        model="gpt-3.5-turbo-0613",
        messages=messages,
        tools=generate_functions(labels),
        tool_choice={"type": "function", "function" : {"name": "enrich_entities"}}, 
        temperature=0,
        frequency_penalty=0,
        presence_penalty=0,
    )

    response_message = response.choices[0].message
    
    available_functions = {"enrich_entities": enrich_entities}  
    function_name = response_message.tool_calls[0].function.name
    
    function_to_call = available_functions[function_name]
    logging.info(f"function_to_call: {function_to_call}")

    function_args = json.loads(response_message.tool_calls[0].function.arguments)
    logging.info(f"function_args: {function_args}")

    function_response = function_to_call(text, function_args)

    return {"model_response": response, 
            "function_response": function_response}
```

### 5. 實際替文字加上 Wikipedia 連結

#### 5.1 執行 OpenAI 任務

```python
text = """The Beatles were an English rock band formed in Liverpool in 1960, comprising John Lennon, Paul McCartney, George Harrison, and Ringo Starr."""
result = run_openai_task(labels, text)
```

??? note "輸出"

    ```text
     2023-10-20 18:05:51,729 - INFO - function_to_call: <function enrich_entities at 0x0000021D30C462A0>
     2023-10-20 18:05:51,730 - INFO - function_args: {'person': ['John Lennon', 'Paul McCartney', 'George Harrison', 'Ringo Starr'], 'org': ['The Beatles'], 'gpe': ['Liverpool'], 'date': ['1960']}
     2023-10-20 18:06:09,858 - INFO - entity_link_dict: {'John Lennon': 'https://en.wikipedia.org/wiki/John_Lennon', 'Paul McCartney': 'https://en.wikipedia.org/wiki/Paul_McCartney', 'George Harrison': 'https://en.wikipedia.org/wiki/George_Harrison', 'Ringo Starr': 'https://en.wikipedia.org/wiki/Ringo_Starr', 'The Beatles': 'https://en.wikipedia.org/wiki/The_Beatles', 'Liverpool': 'https://en.wikipedia.org/wiki/Liverpool'}
    ```

#### 5.2 Function 回傳結果

```python
display(Markdown(f"""**Text:** {text}   
                     **Enriched_Text:** {result['function_response']}"""))
```

??? note "輸出"

    ```text
    <IPython.core.display.Markdown object>
    ```

#### 5.3 Token 用量

要估算推論成本，可以解析 response 裡的 "usage" 欄位。各模型的 token 價格看 [OpenAI Pricing Guide](https://openai.com/pricing)：

```python
# estimate inference cost assuming gpt-3.5-turbo (4K context)
i_tokens  = result["model_response"].usage.prompt_tokens 
o_tokens = result["model_response"].usage.completion_tokens 

i_cost = (i_tokens / 1000) * 0.0015
o_cost = (o_tokens / 1000) * 0.002

print(f"""Token Usage
    Prompt: {i_tokens} tokens
    Completion: {o_tokens} tokens
    Cost estimation: ${round(i_cost + o_cost, 5)}""")
```

??? note "輸出"

    ```text
    Token Usage
        Prompt: 331 tokens
        Completion: 47 tokens
        Cost estimation: $0.00059
    ```

## 重點整理

- NER 把非結構化文字變成結構化資料，標籤集合可以只留任務用得到的部分。
- 想拿穩定的 JSON，用 function calling 加 `tool_choice` 強制指定 function，比單靠 prompt 要求格式可靠。
- chat API 不會執行 function，只回傳參數，執行是你的程式的事，真實場景要先做使用者確認。
- assistant message 可以拿來放範例，one-shot 比 zero-shot 準。
- response 的 `usage` 欄位直接告訴你 token 數，乘上單價就是成本。

## 練習

1. 把 `usage` 裡的 prompt token 和 completion token 分開，用目前模型價格算出這次呼叫的費用。
2. 修改 NER 標籤清單，只留 `PERSON` 和 `GPE` 之類兩三個標籤，觀察輸出的連結有什麼變化。
3. 把 assistant 的 one-shot 範例拿掉改成 zero-shot，換一段自己的文字，比較兩種做法抓到的實體差在哪。
