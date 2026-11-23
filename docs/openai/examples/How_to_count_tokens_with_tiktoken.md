---
translated: true
source: examples/How_to_count_tokens_with_tiktoken.ipynb
---

# 用 Tiktoken 計算 Token 數量

> 原文：[examples/How_to_count_tokens_with_tiktoken.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb)



## 這篇在做什麼
介紹 OpenAI 的開源 tokenizer `tiktoken`，示範怎麼把文字切成 token、還原回文字，以及比較不同 encoding。最後教你替 chat completions 的 messages（包含 tool calls）估算 token 數。

## 學完你會
- 用 `tiktoken.get_encoding()` 和 `encoding_for_model()` 載入 encoding，並用 `encode()` 算出字串的 token 數。
- 用 `decode()` 和 `decode_single_token_bytes()` 把 token 轉回文字，並避開單一 token 解碼的陷阱。
- 寫函式估算 chat messages 和帶 tool 的請求會用掉多少 token。

## 開跑前
- 需要安裝 `tiktoken`（`pip install tiktoken`）。第一次載入 encoding 時要連網下載。

[`tiktoken`](https://github.com/openai/tiktoken/blob/main/README.md) 是 OpenAI 做的快速開源 tokenizer。

給定一個文字字串（例如 `"tiktoken is great!"`）和一個 encoding（例如 `"cl100k_base"`），tokenizer 可以把字串切成 token 的列表（例如 `["t", "ik", "token", " is", " great", "!"]`）。

把字串切成 token 很有用，因為 GPT 模型是以 token 的形式看文字。知道字串有多少 token，可以告訴你 (a) 字串對文字模型來說會不會太長，以及 (b) 一次 OpenAI API 呼叫要花多少錢（因為用量是按 token 計價）。


## Encoding

Encoding 決定文字怎麼轉成 token。不同模型用不同的 encoding。

`tiktoken` 支援 OpenAI 模型用的幾種 encoding：

| Encoding name           | OpenAI models                                       |
|-------------------------|-----------------------------------------------------|
| `o200k_base`            | `gpt-4o`, `gpt-4o-mini`                             |
| `cl100k_base`           | `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo`, `text-embedding-ada-002`, `text-embedding-3-small`, `text-embedding-3-large`  |
| `p50k_base`             | Codex models, `text-davinci-002`, `text-davinci-003`|
| `r50k_base` (or `gpt2`) | GPT-3 models like `davinci`                         |

你可以用 `tiktoken.encoding_for_model()` 取得某個模型的 encoding，如下：
```python
encoding = tiktoken.encoding_for_model('gpt-4o-mini')
```

注意 `p50k_base` 和 `r50k_base` 有大量重疊，非程式碼的應用通常會切出一樣的 token。

## 各語言的 Tokenizer 函式庫

`o200k_base`、`cl100k_base` 和 `p50k_base` encoding：
- Python: [tiktoken](https://github.com/openai/tiktoken/blob/main/README.md)
- .NET / C#: [SharpToken](https://github.com/dmitry-brazhenko/SharpToken), [TiktokenSharp](https://github.com/aiqinxuancai/TiktokenSharp)
- Java: [jtokkit](https://github.com/knuddelsgmbh/jtokkit)
- Golang: [tiktoken-go](https://github.com/pkoukk/tiktoken-go)
- Rust: [tiktoken-rs](https://github.com/zurawiki/tiktoken-rs)

`r50k_base`（`gpt2`）encoding 則有很多語言的 tokenizer 可用。
- Python: [tiktoken](https://github.com/openai/tiktoken/blob/main/README.md) (or alternatively [GPT2TokenizerFast](https://huggingface.co/docs/transformers/model_doc/gpt2#transformers.GPT2TokenizerFast))
- JavaScript: [gpt-3-encoder](https://www.npmjs.com/package/gpt-3-encoder)
- .NET / C#: [GPT Tokenizer](https://github.com/dluc/openai-tools)
- Java: [gpt2-tokenizer-java](https://github.com/hyunwoongko/gpt2-tokenizer-java)
- PHP: [GPT-3-Encoder-PHP](https://github.com/CodeRevolutionPlugins/GPT-3-Encoder-PHP)
- Golang: [tiktoken-go](https://github.com/pkoukk/tiktoken-go)
- Rust: [tiktoken-rs](https://github.com/zurawiki/tiktoken-rs)

（OpenAI 不對第三方函式庫背書或做任何保證。）


## 字串通常怎麼被切成 token

在英文裡，token 的長度通常從一個字元到一個單字不等（例如 `"t"` 或 `" great"`），不過在某些語言裡，token 可能比一個字元還短，或比一個單字還長。空白通常會跟單字的開頭放在一起（例如 `" is"`，而不是 `"is "` 或 `" "`+`"is"`）。你可以在 [OpenAI Tokenizer](https://beta.openai.com/tokenizer) 或第三方的 [Tiktokenizer](https://tiktokenizer.vercel.app/) 網頁應用快速查看字串怎麼被切。

## 0. 安裝 `tiktoken`

需要的話，用 `pip` 安裝 `tiktoken`：

```python
%pip install --upgrade tiktoken -q
%pip install --upgrade openai -q
```

??? note "輸出"

    ```text

    [notice] A new release of pip is available: 24.0 -> 24.2
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.

    [notice] A new release of pip is available: 24.0 -> 24.2
    [notice] To update, run: pip install --upgrade pip
    Note: you may need to restart the kernel to use updated packages.
    ```

## 1. 匯入 `tiktoken`

```python
import tiktoken
```

## 2. 載入 encoding

用 `tiktoken.get_encoding()` 依名稱載入 encoding。

第一次執行時需要連網下載，之後就不用了。

```python
encoding = tiktoken.get_encoding("cl100k_base")
```

用 `tiktoken.encoding_for_model()`，可以依模型名稱自動載入正確的 encoding。

```python
encoding = tiktoken.encoding_for_model("gpt-4o-mini")
```

## 3. 用 `encoding.encode()` 把文字轉成 token



`.encode()` 方法會把文字字串轉成 token 整數的列表。

```python
encoding.encode("tiktoken is great!")
```

??? note "輸出"

    ```text
    [83, 8251, 2488, 382, 2212, 0]
    ```

算 `.encode()` 回傳列表的長度，就是 token 數。

```python
def num_tokens_from_string(string: str, encoding_name: str) -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens
```

```python
num_tokens_from_string("tiktoken is great!", "o200k_base")
```

??? note "輸出"

    ```text
    6
    ```

## 4. 用 `encoding.decode()` 把 token 轉回文字

`.decode()` 會把 token 整數列表轉成字串。

```python
encoding.decode([83, 8251, 2488, 382, 2212, 0])
```

??? note "輸出"

    ```text
    'tiktoken is great!'
    ```

警告：`.decode()` 雖然可以用在單一 token，但如果 token 不在 utf-8 邊界上，結果可能會失真。

對單一 token，用 `.decode_single_token_bytes()` 可以安全地把單一整數 token 轉成它代表的 bytes。

```python
[encoding.decode_single_token_bytes(token) for token in [83, 8251, 2488, 382, 2212, 0]]
```

??? note "輸出"

    ```text
    [b't', b'ikt', b'oken', b' is', b' great', b'!']
    ```

（字串前面的 `b` 表示它們是 byte string。）

## 5. 比較不同的 encoding

不同的 encoding 在切字、合併空白、處理非英文字元上各有差異。用上面的方法，可以在幾個範例字串上比較不同的 encoding。

```python
def compare_encodings(example_string: str) -> None:
    """Prints a comparison of three string encodings."""
    # print the example string
    print(f'\nExample string: "{example_string}"')
    # for each encoding, print the # of tokens, the token integers, and the token bytes
    for encoding_name in ["r50k_base", "p50k_base", "cl100k_base", "o200k_base"]:
        encoding = tiktoken.get_encoding(encoding_name)
        token_integers = encoding.encode(example_string)
        num_tokens = len(token_integers)
        token_bytes = [encoding.decode_single_token_bytes(token) for token in token_integers]
        print()
        print(f"{encoding_name}: {num_tokens} tokens")
        print(f"token integers: {token_integers}")
        print(f"token bytes: {token_bytes}")
```

```python
compare_encodings("antidisestablishmentarianism")
```

??? note "輸出"

    ```text

    Example string: "antidisestablishmentarianism"

    r50k_base: 5 tokens
    token integers: [415, 29207, 44390, 3699, 1042]
    token bytes: [b'ant', b'idis', b'establishment', b'arian', b'ism']

    p50k_base: 5 tokens
    token integers: [415, 29207, 44390, 3699, 1042]
    token bytes: [b'ant', b'idis', b'establishment', b'arian', b'ism']

    cl100k_base: 6 tokens
    token integers: [519, 85342, 34500, 479, 8997, 2191]
    token bytes: [b'ant', b'idis', b'establish', b'ment', b'arian', b'ism']

    o200k_base: 6 tokens
    token integers: [493, 129901, 376, 160388, 21203, 2367]
    token bytes: [b'ant', b'idis', b'est', b'ablishment', b'arian', b'ism']
    ```

```python
compare_encodings("2 + 2 = 4")
```

??? note "輸出"

    ```text

    Example string: "2 + 2 = 4"

    r50k_base: 5 tokens
    token integers: [17, 1343, 362, 796, 604]
    token bytes: [b'2', b' +', b' 2', b' =', b' 4']

    p50k_base: 5 tokens
    token integers: [17, 1343, 362, 796, 604]
    token bytes: [b'2', b' +', b' 2', b' =', b' 4']

    cl100k_base: 7 tokens
    token integers: [17, 489, 220, 17, 284, 220, 19]
    token bytes: [b'2', b' +', b' ', b'2', b' =', b' ', b'4']

    o200k_base: 7 tokens
    token integers: [17, 659, 220, 17, 314, 220, 19]
    token bytes: [b'2', b' +', b' ', b'2', b' =', b' ', b'4']
    ```

```python
compare_encodings("お誕生日おめでとう")
```

??? note "輸出"

    ```text

    Example string: "お誕生日おめでとう"

    r50k_base: 14 tokens
    token integers: [2515, 232, 45739, 243, 37955, 33768, 98, 2515, 232, 1792, 223, 30640, 30201, 29557]
    token bytes: [b'\xe3\x81', b'\x8a', b'\xe8\xaa', b'\x95', b'\xe7\x94\x9f', b'\xe6\x97', b'\xa5', b'\xe3\x81', b'\x8a', b'\xe3\x82', b'\x81', b'\xe3\x81\xa7', b'\xe3\x81\xa8', b'\xe3\x81\x86']

    p50k_base: 14 tokens
    token integers: [2515, 232, 45739, 243, 37955, 33768, 98, 2515, 232, 1792, 223, 30640, 30201, 29557]
    token bytes: [b'\xe3\x81', b'\x8a', b'\xe8\xaa', b'\x95', b'\xe7\x94\x9f', b'\xe6\x97', b'\xa5', b'\xe3\x81', b'\x8a', b'\xe3\x82', b'\x81', b'\xe3\x81\xa7', b'\xe3\x81\xa8', b'\xe3\x81\x86']

    cl100k_base: 9 tokens
    token integers: [33334, 45918, 243, 21990, 9080, 33334, 62004, 16556, 78699]
    token bytes: [b'\xe3\x81\x8a', b'\xe8\xaa', b'\x95', b'\xe7\x94\x9f', b'\xe6\x97\xa5', b'\xe3\x81\x8a', b'\xe3\x82\x81', b'\xe3\x81\xa7', b'\xe3\x81\xa8\xe3\x81\x86']

    o200k_base: 8 tokens
    token integers: [8930, 9697, 243, 128225, 8930, 17693, 4344, 48669]
    token bytes: [b'\xe3\x81\x8a', b'\xe8\xaa', b'\x95', b'\xe7\x94\x9f\xe6\x97\xa5', b'\xe3\x81\x8a', b'\xe3\x82\x81', b'\xe3\x81\xa7', b'\xe3\x81\xa8\xe3\x81\x86']
    ```

## 6. 計算 chat completions API 呼叫的 token

`gpt-4o-mini` 和 `gpt-4` 這類 ChatGPT 模型使用 token 的方式跟舊的 completions 模型一樣，但因為它們是以 message 為單位的格式，要算一段對話會用掉多少 token 比較難。

下面是一個範例函式，用來計算傳給 `gpt-3.5-turbo`、`gpt-4`、`gpt-4o` 和 `gpt-4o-mini` 的 messages 的 token 數。

注意，從 message 計算 token 的確切方式可能因模型而異。請把下面函式算出的數字當成估計值，不要當成永遠不變的保證。

特別是，使用選用的 functions 輸入的請求，會在下面估算的結果之外再多消耗 token。

```python
def num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("o200k_base")
    if model in {
        "gpt-3.5-turbo-0125",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
        "gpt-4o-mini-2024-07-18",
        "gpt-4o-2024-08-06"
        }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif "gpt-3.5-turbo" in model:
        print("Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0125.")
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0125")
    elif "gpt-4o-mini" in model:
        print("Warning: gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-mini-2024-07-18.")
        return num_tokens_from_messages(messages, model="gpt-4o-mini-2024-07-18")
    elif "gpt-4o" in model:
        print("Warning: gpt-4o and gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-2024-08-06.")
        return num_tokens_from_messages(messages, model="gpt-4o-2024-08-06")
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

from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

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
    "gpt-3.5-turbo",
    "gpt-4-0613",
    "gpt-4",
    "gpt-4o",
    "gpt-4o-mini"
    ]:
    print(model)
    # example token count from the function defined above
    print(f"{num_tokens_from_messages(example_messages, model)} prompt tokens counted by num_tokens_from_messages().")
    # example token count from the OpenAI API
    response = client.chat.completions.create(model=model,
    messages=example_messages,
    temperature=0,
    max_tokens=1)
    print(f'{response.usage.prompt_tokens} prompt tokens counted by the OpenAI API.')
    print()
```

??? note "輸出"

    ```text
    gpt-3.5-turbo
    Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0125.
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.

    gpt-4-0613
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.

    gpt-4
    Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.
    129 prompt tokens counted by num_tokens_from_messages().
    129 prompt tokens counted by the OpenAI API.

    gpt-4o
    Warning: gpt-4o and gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-2024-08-06.
    124 prompt tokens counted by num_tokens_from_messages().
    124 prompt tokens counted by the OpenAI API.

    gpt-4o-mini
    Warning: gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-mini-2024-07-18.
    124 prompt tokens counted by num_tokens_from_messages().
    124 prompt tokens counted by the OpenAI API.
    ```

## 7. 計算含 tool call 的 chat completions 的 token

接下來看怎麼把這個計算套用到可能含有 function call 的 messages。因為 tools 本身的格式，這件事並不是一眼就能解決。 

下面是一個範例函式，用來計算含 tools、傳給 `gpt-3.5-turbo`、`gpt-4`、`gpt-4o` 和 `gpt-4o-mini` 的 messages 的 token 數。

```python
def num_tokens_for_tools(functions, messages, model):
    
    # Initialize function settings to 0
    func_init = 0
    prop_init = 0
    prop_key = 0
    enum_init = 0
    enum_item = 0
    func_end = 0
    
    if model in [
        "gpt-4o",
        "gpt-4o-mini"
    ]:
        
        # Set function settings for the above models
        func_init = 7
        prop_init = 3
        prop_key = 3
        enum_init = -3
        enum_item = 3
        func_end = 12
    elif model in [
        "gpt-3.5-turbo",
        "gpt-4"
    ]:
        # Set function settings for the above models
        func_init = 10
        prop_init = 3
        prop_key = 3
        enum_init = -3
        enum_item = 3
        func_end = 12
    else:
        raise NotImplementedError(
            f"""num_tokens_for_tools() is not implemented for model {model}."""
        )
    
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using o200k_base encoding.")
        encoding = tiktoken.get_encoding("o200k_base")
    
    func_token_count = 0
    if len(functions) > 0:
        for f in functions:
            func_token_count += func_init  # Add tokens for start of each function
            function = f["function"]
            f_name = function["name"]
            f_desc = function["description"]
            if f_desc.endswith("."):
                f_desc = f_desc[:-1]
            line = f_name + ":" + f_desc
            func_token_count += len(encoding.encode(line))  # Add tokens for set name and description
            if len(function["parameters"]["properties"]) > 0:
                func_token_count += prop_init  # Add tokens for start of each property
                for key in list(function["parameters"]["properties"].keys()):
                    func_token_count += prop_key  # Add tokens for each set property
                    p_name = key
                    p_type = function["parameters"]["properties"][key]["type"]
                    p_desc = function["parameters"]["properties"][key]["description"]
                    if "enum" in function["parameters"]["properties"][key].keys():
                        func_token_count += enum_init  # Add tokens if property has enum list
                        for item in function["parameters"]["properties"][key]["enum"]:
                            func_token_count += enum_item
                            func_token_count += len(encoding.encode(item))
                    if p_desc.endswith("."):
                        p_desc = p_desc[:-1]
                    line = f"{p_name}:{p_type}:{p_desc}"
                    func_token_count += len(encoding.encode(line))
        func_token_count += func_end
        
    messages_token_count = num_tokens_from_messages(messages, model)
    total_tokens = messages_token_count + func_token_count
    
    return total_tokens
```

```python
tools = [
  {
    "type": "function",
    "function": {
      "name": "get_current_weather",
      "description": "Get the current weather in a given location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "The city and state, e.g. San Francisco, CA",
          },
          "unit": {"type": "string", 
                   "description": "The unit of temperature to return",
                   "enum": ["celsius", "fahrenheit"]},
        },
        "required": ["location"],
      },
    }
  }
]

example_messages = [
    {
        "role": "system",
        "content": "You are a helpful assistant that can answer to questions about the weather.",
    },
    {
        "role": "user",
        "content": "What's the weather like in San Francisco?",
    },
]

for model in [
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-4o",
    "gpt-4o-mini"
    ]:
    print(model)
    # example token count from the function defined above
    print(f"{num_tokens_for_tools(tools, example_messages, model)} prompt tokens counted by num_tokens_for_tools().")
    # example token count from the OpenAI API
    response = client.chat.completions.create(model=model,
          messages=example_messages,
          tools=tools,
          temperature=0)
    print(f'{response.usage.prompt_tokens} prompt tokens counted by the OpenAI API.')
    print()
```

??? note "輸出"

    ```text
    gpt-3.5-turbo
    Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0125.
    105 prompt tokens counted by num_tokens_for_tools().
    105 prompt tokens counted by the OpenAI API.

    gpt-4
    Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613.
    105 prompt tokens counted by num_tokens_for_tools().
    105 prompt tokens counted by the OpenAI API.

    gpt-4o
    Warning: gpt-4o and gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-2024-08-06.
    101 prompt tokens counted by num_tokens_for_tools().
    101 prompt tokens counted by the OpenAI API.

    gpt-4o-mini
    Warning: gpt-4o-mini may update over time. Returning num tokens assuming gpt-4o-mini-2024-07-18.
    101 prompt tokens counted by num_tokens_for_tools().
    101 prompt tokens counted by the OpenAI API.
    ```

## 重點整理
- GPT 模型看到的是 token，不是字元；token 數決定能不能塞進 context 和 API 要花多少錢。
- 不同模型用不同 encoding，所以要用 `encoding_for_model()` 依模型取對的那個。
- 單一 token 的 `decode()` 可能因為不在 utf-8 邊界而失真，要看原始 bytes 用 `decode_single_token_bytes()`。
- Chat messages 和 tool 定義會帶來額外的格式 token，函式算出的數字只是估計。

## 練習
1. 載入 `o200k_base` 和 `cl100k_base`，對一句中文和一句英文各算 token 數，比較差異。
2. 把 `encode()` 回傳的 token 列表逐個用 `decode_single_token_bytes()` 印出來，找出哪些字被拆成非完整字元的 bytes。
3. 修改 chat messages 的計數函式，加上一個你自己的 tool 定義，比較加入前後算出的 token 數差多少。
