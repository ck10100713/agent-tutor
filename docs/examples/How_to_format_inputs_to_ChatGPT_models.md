---
translated: true
source: examples/How_to_format_inputs_to_ChatGPT_models.ipynb
---
# 怎麼格式化 ChatGPT 模型的輸入

> 原文：[examples/How_to_format_inputs_to_ChatGPT_models.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_format_inputs_to_ChatGPT_models.ipynb)

## 這篇在做什麼

用幾個實際的 API 呼叫，說明 chat 模型的輸入格式：`messages` 陣列、`role`、`content`，以及怎麼讀回應。後半講 system message、few-shot 的寫法，最後給一個估算 messages 會用掉多少 token 的函式。

## 學完你會

- 組出正確的 `messages` 並從 response 取出模型的回覆
- 用 system message 和假的 example messages（few-shot）引導模型的行為
- 用函式估算一組 messages 會用掉多少 token

## 開跑前

- 環境變數 `OPENAI_API_KEY`，呼叫 API 會產生費用

ChatGPT 是由 `gpt-3.5-turbo` 和 `gpt-4` 驅動的，這是 OpenAI 最先進的模型。

你可以用 OpenAI API，拿 `gpt-3.5-turbo` 或 `gpt-4` 做自己的應用。

Chat 模型的輸入是一串 messages，輸出是 AI 寫的一則 message。

這份指南用幾個範例 API 呼叫來說明 chat 格式。

## 1. 匯入 openai 套件

```python
# if needed, install and/or upgrade to the latest version of the OpenAI Python library
%pip install --upgrade openai
```

```python
# import the OpenAI Python library for calling the OpenAI API
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

## 2. 一個 chat completion API 呼叫範例

Chat completion API 呼叫的參數，
**必填**
- `model`：要用的模型名稱（例如 `gpt-3.5-turbo`、`gpt-4`、`gpt-3.5-turbo-16k-1106`）
- `messages`：message 物件的清單，每個物件有兩個必填欄位：
    - `role`：發話者的角色（`system`、`user`、`assistant` 或 `tool`）
    - `content`：訊息內容（例如 `Write me a beautiful poem`）

Message 也可以有選填的 `name` 欄位，用來給發話者取名，例如 `example-user`、`Alice`、`BlackbeardBot`。名稱不能含空格。

**選填**
- `frequency_penalty`: Penalizes tokens based on their frequency, reducing repetition.
- `logit_bias`: Modifies likelihood of specified tokens with bias values.
- `logprobs`: Returns log probabilities of output tokens if true.
- `top_logprobs`: Specifies the number of most likely tokens to return at each position.
- `max_tokens`: Sets the maximum number of generated tokens in chat completion.
- `n`: Generates a specified number of chat completion choices for each input.
- `presence_penalty`: Penalizes new tokens based on their presence in the text.
- `response_format`: Specifies the output format, e.g., JSON mode.
- `seed`: Ensures deterministic sampling with a specified seed.
- `stop`: Specifies up to 4 sequences where the API should stop generating tokens.
- `stream`: Sends partial message deltas as tokens become available.
- `temperature`: Sets the sampling temperature between 0 and 2.
- `top_p`: Uses nucleus sampling; considers tokens with top_p probability mass.
- `tools`: Lists functions the model may call.
- `tool_choice`: Controls the model's function calls (none/auto/function).
- `user`: Unique identifier for end-user monitoring and abuse detection.


2024 年 1 月起，你也可以選擇性地傳入 `functions` 清單，告訴 GPT 能不能產生 JSON 餵給函式。細節看[文件](https://platform.openai.com/docs/guides/function-calling)、[API reference](https://platform.openai.com/docs/api-reference/chat)，或 Cookbook 的指南 [How to call functions with chat models](How_to_call_functions_with_chat_models.md)。

一般來說，對話會從一則 system message 開始，告訴 assistant 該怎麼表現，後面接著交替的 user 和 assistant 訊息，但你不一定要照這個格式。

來看一個 chat API 呼叫的例子，看 chat 格式實際上怎麼運作。

```python
# Example OpenAI Python library request
MODEL = "gpt-3.5-turbo"
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Knock knock."},
        {"role": "assistant", "content": "Who's there?"},
        {"role": "user", "content": "Orange."},
    ],
    temperature=0,
)
```

```python
print(json.dumps(json.loads(response.model_dump_json()), indent=4))
```

??? note "輸出"

    ```text
    {
        "id": "chatcmpl-8dee9DuEFcg2QILtT2a6EBXZnpirM",
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "logprobs": null,
                "message": {
                    "content": "Orange who?",
                    "role": "assistant",
                    "function_call": null,
                    "tool_calls": null
                }
            }
        ],
        "created": 1704461729,
        "model": "gpt-3.5-turbo-0613",
        "object": "chat.completion",
        "system_fingerprint": null,
        "usage": {
            "completion_tokens": 3,
            "prompt_tokens": 35,
            "total_tokens": 38
        }
    }
    ```

如你所見，response 物件有幾個欄位：
- `id`：請求的 ID
- `choices`：completion 物件的清單（除非你把 `n` 設成大於 1，否則只有一個）
    - `finish_reason`：模型停止產生文字的原因（`stop`，或達到 `max_tokens` 上限時的 `length`）
    - `index`：這個 choice 在清單中的索引
    - `logprobs`：這個 choice 的 log probability 資訊
    - `message`：模型產生的 message 物件
        - `content`：訊息內容
        - `role`：這則訊息作者的角色
        - `tool_calls`：模型產生的 tool call，例如 function call（有給 tools 的話）
- `created`：請求的 timestamp
- `model`：產生這個回應的模型完整名稱
- `object`：回傳物件的類型（例如 `chat.completion`）
- `system_fingerprint`：代表模型運行時的後端設定
- `usage`：產生回覆所用的 token 數，包含 prompt、completion 和總數

只取出回覆的方法：

```python
response.choices[0].message.content
```

??? note "輸出"

    ```text
    'Orange who?'
    ```

即使不是對話類的任務，也能放進 chat 格式，做法是把指令放在第一則 user message。

例如，要請模型用海盜黑鬍子的口吻解釋非同步程式設計，可以這樣組對話：

```python
# example with a system message
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain asynchronous programming in the style of the pirate Blackbeard."},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    Arr, me matey! Let me tell ye a tale of asynchronous programming, in the style of the fearsome pirate Blackbeard!

    Picture this, me hearties. In the vast ocean of programming, there be times when ye need to perform multiple tasks at once. But fear not, for asynchronous programming be here to save the day!

    Ye see, in traditional programming, ye be waitin' for one task to be done before movin' on to the next. But with asynchronous programming, ye can be takin' care of multiple tasks at the same time, just like a pirate multitaskin' on the high seas!

    Instead of waitin' for a task to be completed, ye can be sendin' it off on its own journey, while ye move on to the next task. It be like havin' a crew of trusty sailors, each takin' care of their own duties, without waitin' for the others.

    Now, ye may be wonderin', how does this sorcery work? Well, me matey, it be all about callbacks and promises. When ye be sendin' off a task, ye be attachin' a callback function to it. This be like leavin' a message in a bottle, tellin' the task what to do when it be finished.

    While the task be sailin' on its own, ye can be movin' on to the next task, without wastin' any precious time. And when the first task be done, it be sendin' a signal back to ye, lettin' ye know it be finished. Then ye can be takin' care of the callback function, like openin' the bottle and readin' the message inside.

    But wait, there be more! With promises, ye can be makin' even fancier arrangements. Instead of callbacks, ye be makin' a promise that the task will be completed. It be like a contract between ye and the task, swearin' that it will be done.

    Ye can be attachin' multiple promises to a task, promisin' different outcomes. And when the task be finished, it be fulfillin' the promises, lettin' ye know it be done. Then ye can be handlin' the fulfillments, like collectin' the rewards of yer pirate adventures!

    So, me hearties, that be the tale of asynchronous programming, told in the style of the fearsome pirate Blackbeard! With callbacks and promises, ye can be takin' care of multiple tasks at once, just like a pirate conquerin' the seven seas!
    ```

```python
# example without a system message
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "user", "content": "Explain asynchronous programming in the style of the pirate Blackbeard."},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    Arr, me hearties! Gather 'round and listen up, for I be tellin' ye about the mysterious art of asynchronous programming, in the style of the fearsome pirate Blackbeard!

    Now, ye see, in the world of programming, there be times when we need to perform tasks that take a mighty long time to complete. These tasks might involve fetchin' data from the depths of the internet, or performin' complex calculations that would make even Davy Jones scratch his head.

    In the olden days, we pirates used to wait patiently for each task to finish afore movin' on to the next one. But that be a waste of precious time, me hearties! We be pirates, always lookin' for ways to be more efficient and plunder more booty!

    That be where asynchronous programming comes in, me mateys. It be a way to tackle multiple tasks at once, without waitin' for each one to finish afore movin' on. It be like havin' a crew of scallywags workin' on different tasks simultaneously, while ye be overseein' the whole operation.

    Ye see, in asynchronous programming, we be breakin' down our tasks into smaller chunks called "coroutines." Each coroutine be like a separate pirate, workin' on its own task. When a coroutine be startin' its work, it don't wait for the task to finish afore movin' on to the next one. Instead, it be movin' on to the next task, lettin' the first one continue in the background.

    Now, ye might be wonderin', "But Blackbeard, how be we know when a task be finished if we don't wait for it?" Ah, me hearties, that be where the magic of callbacks and promises come in!

    When a coroutine be startin' its work, it be attachin' a callback or a promise to it. This be like leavin' a message in a bottle, tellin' the coroutine what to do when it be finished. So, while the coroutine be workin' away, the rest of the crew be movin' on to other tasks, plunderin' more booty along the way.

    When a coroutine be finished with its task, it be sendin' a signal to the callback or fulfillin' the promise, lettin' the rest of the crew know that it be done. Then, the crew can gather 'round and handle the results of the completed task, celebratin' their victory and countin' their plunder.

    So, me hearties, asynchronous programming be like havin' a crew of pirates workin' on different tasks at once, without waitin' for each one to finish afore movin' on. It be a way to be more efficient, plunder more booty, and conquer the vast seas of programming!

    Now, set sail, me mateys, and embrace the power of asynchronous programming like true pirates of the digital realm! Arr!
    ```

## 3. 指示 gpt-3.5-turbo-0301 的小技巧

指示模型的最佳做法可能隨模型版本而變。下面的建議適用於 `gpt-3.5-turbo-0301`，不一定適用於未來的模型。

### System messages

System message 可以用來讓 assistant 帶有不同的個性或行為。

注意 `gpt-3.5-turbo-0301` 通常不像 `gpt-4-0314` 或 `gpt-3.5-turbo-0613` 那麼重視 system message。所以對 `gpt-3.5-turbo-0301`，我們建議把重要的指示放在 user message。有些開發者發現，不斷把 system message 往對話尾端移，可以避免對話變長時模型的注意力飄走。

```python
# An example of a system message that primes the assistant to explain concepts in great depth
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a friendly and helpful teaching assistant. You explain concepts in great depth using simple terms, and you give examples to help people learn. At the end of each explanation, you ask a question to check for understanding"},
        {"role": "user", "content": "Can you explain how fractions work?"},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    Of course! Fractions are a way to represent parts of a whole. They are made up of two numbers: a numerator and a denominator. The numerator tells you how many parts you have, and the denominator tells you how many equal parts make up the whole.

    Let's take an example to understand this better. Imagine you have a pizza that is divided into 8 equal slices. If you eat 3 slices, you can represent that as the fraction 3/8. Here, the numerator is 3 because you ate 3 slices, and the denominator is 8 because the whole pizza is divided into 8 slices.

    Fractions can also be used to represent numbers less than 1. For example, if you eat half of a pizza, you can write it as 1/2. Here, the numerator is 1 because you ate one slice, and the denominator is 2 because the whole pizza is divided into 2 equal parts.

    Now, let's talk about equivalent fractions. Equivalent fractions are different fractions that represent the same amount. For example, 1/2 and 2/4 are equivalent fractions because they both represent half of something. To find equivalent fractions, you can multiply or divide both the numerator and denominator by the same number.

    Here's a question to check your understanding: If you have a cake divided into 12 equal slices and you eat 4 slices, what fraction of the cake did you eat?
    ```

```python
# An example of a system message that primes the assistant to give brief, to-the-point answers
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a laconic assistant. You reply with brief, to-the-point answers with no elaboration."},
        {"role": "user", "content": "Can you explain how fractions work?"},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    Fractions represent parts of a whole. They have a numerator (top number) and a denominator (bottom number).
    ```

### Few-shot prompting

有些情況下，示範給模型看比用說的更容易。

示範的一種方式是用假造的範例 messages。

例如：

```python
# An example of a faked few-shot conversation to prime the model into translating business jargon to simpler speech
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a helpful, pattern-following assistant."},
        {"role": "user", "content": "Help me translate the following corporate jargon into plain English."},
        {"role": "assistant", "content": "Sure, I'd be happy to!"},
        {"role": "user", "content": "New synergies will help drive top-line growth."},
        {"role": "assistant", "content": "Things working well together will increase revenue."},
        {"role": "user", "content": "Let's circle back when we have more bandwidth to touch base on opportunities for increased leverage."},
        {"role": "assistant", "content": "Let's talk later when we're less busy about how to do better."},
        {"role": "user", "content": "This late pivot means we don't have time to boil the ocean for the client deliverable."},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    This sudden change in direction means we don't have enough time to complete the entire project for the client.
    ```

為了讓模型清楚這些範例訊息不是真正對話的一部分、不該被回頭引用，可以試著把 `system` message 的 `name` 欄位設成 `example_user` 和 `example_assistant`。

把上面的 few-shot 範例改寫之後，可以這樣寫：

```python
# The business jargon translation example, but with example names for the example messages
response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": "You are a helpful, pattern-following assistant that translates corporate jargon into plain English."},
        {"role": "system", "name":"example_user", "content": "New synergies will help drive top-line growth."},
        {"role": "system", "name": "example_assistant", "content": "Things working well together will increase revenue."},
        {"role": "system", "name":"example_user", "content": "Let's circle back when we have more bandwidth to touch base on opportunities for increased leverage."},
        {"role": "system", "name": "example_assistant", "content": "Let's talk later when we're less busy about how to do better."},
        {"role": "user", "content": "This late pivot means we don't have time to boil the ocean for the client deliverable."},
    ],
    temperature=0,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    This sudden change in direction means we don't have enough time to complete the entire project for the client.
    ```

設計對話不是每次一試就成功。

如果第一次嘗試失敗，別怕多試幾種引導或調整模型的方式。

舉個例子，有個開發者發現，插入一則 user message 說 "Great job so far, these have been perfect"，可以讓模型的回答品質變高，準確率也跟著上升。

想知道更多提升模型可靠性的做法，可以讀我們的指南[提升可靠性的技巧](../articles/techniques_to_improve_reliability.md)。那份是針對非 chat 模型寫的，但很多原則仍然適用。

## 4. 計算 token

送出請求時，API 會把 messages 轉成一串 token。

用掉的 token 數會影響：
- 請求的成本
- 產生回應所需的時間
- 回覆是否會因為達到 token 上限而被截斷（`gpt-3.5-turbo` 是 4,096，`gpt-4` 是 8,192）

你可以用下面的函式算出一組 messages 會用掉多少 token。

注意，messages 的 token 實際算法可能因模型而異。把下面函式算出的數字當成估計值，不是永遠成立的保證。 

特別是有用到選填的 functions 輸入的請求，會比下面算出的估計多消耗 token。

更多關於計算 token 的內容，看 [How to count tokens with tiktoken](How_to_count_tokens_with_tiktoken.md)。

```python
import tiktoken


def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = 4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif "gpt-3.5-turbo" in model:
        print("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")
    elif "gpt-4" in model:
        print("Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.")
        return num_tokens_from_messages(messages, model="gpt-4-0613")
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens
```

```python
# let's verify the function above matches the OpenAI API response
example_messages = [
    {
        "role": "system",
        "content": "You are a helpful, pattern-following assistant that translates corporate jargon into plain English.",
    },
    {
        "role": "system",
        "name": "example_user",
        "content": "New synergies will help drive top-line growth.",
    },
    {
        "role": "system",
        "name": "example_assistant",
        "content": "Things working well together will increase revenue.",
    },
    {
        "role": "system",
        "name": "example_user",
        "content": "Let's circle back when we have more bandwidth to touch base on opportunities for increased leverage.",
    },
    {
        "role": "system",
        "name": "example_assistant",
        "content": "Let's talk later when we're less busy about how to do better.",
    },
    {
        "role": "user",
        "content": "This late pivot means we don't have time to boil the ocean for the client deliverable.",
    },
]

for model in [
    # "gpt-3.5-turbo-0301",
    # "gpt-4-0314",
    # "gpt-4-0613",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4-1106-preview",
    ]:
    print(model)
    # example token count from the function defined above
    print(f"{num_tokens_from_messages(example_messages, model)} prompt tokens counted by num_tokens_from_messages().")
    # example token count from the OpenAI API
    response = client.chat.completions.create(model=model,
    messages=example_messages,
    temperature=0,
    max_tokens=1)
    token = response.usage.prompt_tokens
    print(f'{token} prompt tokens counted by the OpenAI API.')
    print()
```

??? note "輸出"

    ```text
    gpt-3.5-turbo-1106
    Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613.
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.

    gpt-3.5-turbo
    Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613.
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.

    gpt-4
    Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.

    gpt-4-1106-preview
    Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.
    ```

## 重點整理

- Chat 模型的輸入是 `messages` 陣列，每則有 `role` 和 `content`；回覆在 `choices[0].message.content`。
- 一般對話以 system message 開頭，再交替 user 和 assistant，但不是硬性規定。
- 非對話任務也能放進 chat 格式，把指令寫在第一則 user message 就行。
- Few-shot 可以用假造的 example messages，用 `name` 設成 `example_user` / `example_assistant` 標明它們不是真實對話。
- Token 數影響成本、延遲和截斷，函式算出來的只是估計值。

## 練習

1. 把黑鬍子範例的 `max_tokens` 改成很小的值，看 `finish_reason` 變成什麼。
2. 把 `n` 設成 3，印出每個 `choices[i].message.content`，並用 `usage` 看 token 數怎麼變。
3. 自己寫一組 few-shot（例如把句子改成正式語氣），分別用一般 message 和 `name="example_user"` 的寫法，再用計算 token 的函式比較兩種的 token 數。
