---
translated: true
source: examples/How_to_stream_completions.ipynb
---

# 如何 stream completion

> 原文：[examples/How_to_stream_completions.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_stream_completions.ipynb)



## 這篇在做什麼
示範怎麼用 `stream=True` 讓 Chat Completions 邊生成邊回傳，不用等整段結果算完。比較一般回應和 streaming 回應的格式與速度，也教你怎麼拿到 stream 的 token 用量。

## 學完你會
- 用 `stream=True` 呼叫 chat completions，並用 for 迴圈從 `delta` 欄位取出內容
- 量測 streaming 的首個 token 延遲，和一般請求比較
- 用 `stream_options={"include_usage": True}` 拿到 streaming 回應的 token 用量

## 開跑前
需要 OpenAI API key（環境變數 `OPENAI_API_KEY`）。

預設情況下，向 OpenAI 請求 completion 時，整段 completion 會先全部生成完，再一次回傳。

如果生成的內容很長，等待回應可能要好幾秒。

想更早拿到回應，可以在生成過程中「stream」completion。這樣你可以在完整內容生成完之前，就開始印出或處理開頭的部分。

要 stream completion，呼叫 chat completions 或 completions endpoint 時設定 `stream=True`。這會回傳一個物件，以 [data-only server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format) 的形式串流回傳結果。要從 `delta` 欄位取出 chunk，而不是 `message` 欄位。

## 缺點

注意，在正式環境使用 `stream=True` 會讓內容審核比較困難，因為不完整的 completion 比較難評估。這可能影響[核准的使用方式](https://beta.openai.com/docs/usage-guidelines)。

## 範例程式

下面這個 notebook 會示範：
1. 一般 chat completion 回應長什麼樣
2. streaming chat completion 回應長什麼樣
3. streaming chat completion 省了多少時間
4. 如何取得 streaming chat completion 回應的 token 用量

```python
# !pip install openai
```

```python
# imports
import time  # for measuring time duration of API calls
from openai import OpenAI
import os
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

### 1. 一般 chat completion 回應長什麼樣

一般的 ChatCompletions API 呼叫，是先把回應算完，再一次回傳。

```python
# Example of an OpenAI ChatCompletion request
# https://platform.openai.com/docs/guides/text-generation/chat-completions-api

# record the time before the request is sent
start_time = time.time()

# send a ChatCompletion request to count to 100
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
        {'role': 'user', 'content': 'Count to 100, with a comma between each number and no newlines. E.g., 1, 2, 3, ...'}
    ],
    temperature=0,
)
# calculate the time it took to receive the response
response_time = time.time() - start_time

# print the time delay and text received
print(f"Full response received {response_time:.2f} seconds after request")
print(f"Full response received:\n{response}")
```

??? note "輸出"

    ```text
    Full response received 1.88 seconds after request
    Full response received:
    ChatCompletion(id='chatcmpl-9lMgdoiMfxVHPDNVCtvXuTWcQ2GGb', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content='1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100', role='assistant', function_call=None, tool_calls=None))], created=1721075651, model='gpt-july-test', object='chat.completion', system_fingerprint='fp_e9b8ed65d2', usage=CompletionUsage(completion_tokens=298, prompt_tokens=36, total_tokens=334))
    ```

回覆可以用 `response.choices[0].message` 取出。

回覆的文字內容可以用 `response.choices[0].message.content` 取出。

```python
reply = response.choices[0].message
print(f"Extracted reply: \n{reply}")

reply_content = response.choices[0].message.content
print(f"Extracted content: \n{reply_content}")
```

??? note "輸出"

    ```text
    Extracted reply: 
    ChatCompletionMessage(content='1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100', role='assistant', function_call=None, tool_calls=None)
    Extracted content: 
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100
    ```

### 2. 如何 stream chat completion

用 streaming API 呼叫時，回應會透過 [event stream](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events#event_stream_format) 分成一個個 chunk 逐步回傳。在 Python 裡，可以用 `for` 迴圈迭代這些 event。

來看看長什麼樣：

```python
# Example of an OpenAI ChatCompletion request with stream=True
# https://platform.openai.com/docs/api-reference/streaming#chat/create-stream

# a ChatCompletion request
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
        {'role': 'user', 'content': "What's 1+1? Answer in one word."}
    ],
    temperature=0,
    stream=True  # this time, we set stream=True
)

for chunk in response:
    print(chunk)
    print(chunk.choices[0].delta.content)
    print("****************")
```

??? note "輸出"

    ```text
    ChatCompletionChunk(id='chatcmpl-9lMgfRSWPHcw51s6wxKT1YEO2CKpd', choices=[Choice(delta=ChoiceDelta(content='', function_call=None, role='assistant', tool_calls=None), finish_reason=None, index=0, logprobs=None)], created=1721075653, model='gpt-july-test', object='chat.completion.chunk', system_fingerprint='fp_e9b8ed65d2', usage=None)

    ****************
    ChatCompletionChunk(id='chatcmpl-9lMgfRSWPHcw51s6wxKT1YEO2CKpd', choices=[Choice(delta=ChoiceDelta(content='Two', function_call=None, role=None, tool_calls=None), finish_reason=None, index=0, logprobs=None)], created=1721075653, model='gpt-july-test', object='chat.completion.chunk', system_fingerprint='fp_e9b8ed65d2', usage=None)
    Two
    ****************
    ChatCompletionChunk(id='chatcmpl-9lMgfRSWPHcw51s6wxKT1YEO2CKpd', choices=[Choice(delta=ChoiceDelta(content='.', function_call=None, role=None, tool_calls=None), finish_reason=None, index=0, logprobs=None)], created=1721075653, model='gpt-july-test', object='chat.completion.chunk', system_fingerprint='fp_e9b8ed65d2', usage=None)
    .
    ****************
    ChatCompletionChunk(id='chatcmpl-9lMgfRSWPHcw51s6wxKT1YEO2CKpd', choices=[Choice(delta=ChoiceDelta(content=None, function_call=None, role=None, tool_calls=None), finish_reason='stop', index=0, logprobs=None)], created=1721075653, model='gpt-july-test', object='chat.completion.chunk', system_fingerprint='fp_e9b8ed65d2', usage=None)
    None
    ****************
    ```

如上所示，streaming 回應有的是 `delta` 欄位，不是 `message` 欄位。`delta` 可能包含：
- role token（例如 `{"role": "assistant"}`）
- content token（例如 `{"content": "\n\n"}`）
- 空的內容（例如 `{}`），代表 stream 結束

### 3. streaming 省了多少時間

現在再請 `gpt-4o-mini` 數到 100，看要花多久。

```python
# Example of an OpenAI ChatCompletion request with stream=True
# https://platform.openai.com/docs/api-reference/streaming#chat/create-stream

# record the time before the request is sent
start_time = time.time()

# send a ChatCompletion request to count to 100
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
        {'role': 'user', 'content': 'Count to 100, with a comma between each number and no newlines. E.g., 1, 2, 3, ...'}
    ],
    temperature=0,
    stream=True  # again, we set stream=True
)
# create variables to collect the stream of chunks
collected_chunks = []
collected_messages = []
# iterate through the stream of events
for chunk in response:
    chunk_time = time.time() - start_time  # calculate the time delay of the chunk
    collected_chunks.append(chunk)  # save the event response
    chunk_message = chunk.choices[0].delta.content  # extract the message
    collected_messages.append(chunk_message)  # save the message
    print(f"Message received {chunk_time:.2f} seconds after request: {chunk_message}")  # print the delay and text

# print the time delay and text received
print(f"Full response received {chunk_time:.2f} seconds after request")
# clean None in collected_messages
collected_messages = [m for m in collected_messages if m is not None]
full_reply_content = ''.join(collected_messages)
print(f"Full conversation received: {full_reply_content}")
```

??? note "輸出"

    ```text
    Message received 1.14 seconds after request: 
    Message received 1.14 seconds after request: 1
    Message received 1.14 seconds after request: ,
    Message received 1.14 seconds after request:  
    Message received 1.14 seconds after request: 2
    Message received 1.16 seconds after request: ,
    Message received 1.16 seconds after request:  
    Message received 1.16 seconds after request: 3
    Message received 1.35 seconds after request: ,
    Message received 1.35 seconds after request:  
    Message received 1.35 seconds after request: 4
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 5
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 6
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 7
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 8
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 9
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 10
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 11
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.36 seconds after request: 12
    Message received 1.36 seconds after request: ,
    Message received 1.36 seconds after request:  
    Message received 1.45 seconds after request: 13
    Message received 1.45 seconds after request: ,
    Message received 1.45 seconds after request:  
    ... (省略 262 行)
    ```

#### 時間比較

上面的例子裡，兩個請求都花了大約 4 到 5 秒才完整結束。請求時間會因負載和其他隨機因素而不同。

不過在 streaming 請求中，第一個 token 在 0.1 秒後就收到了，之後每個 token 大約每 0.01 到 0.02 秒到一個。

### 4. 如何取得 streaming chat completion 回應的 token 用量

設定 `stream_options={"include_usage": True}`，就能拿到 streaming 回應的 token 用量統計。這樣做之後，會多一個額外的 chunk 當作最後一個 chunk 串流出來，你可以從這個 chunk 的 `usage` 欄位讀到整個請求的用量資料。設定 `stream_options={"include_usage": True}` 時有幾個重點：
* 除了最後一個 chunk 之外，所有 chunk 的 `usage` 欄位值都是 null。
* 最後一個 chunk 的 `usage` 欄位包含整個請求的 token 用量統計。
* 最後一個 chunk 的 `choices` 欄位一定是空陣列 `[]`。

用第 2 節的例子來看看怎麼運作。

```python
# Example of an OpenAI ChatCompletion request with stream=True and stream_options={"include_usage": True}

# a ChatCompletion request
response = client.chat.completions.create(
    model='gpt-4o-mini',
    messages=[
        {'role': 'user', 'content': "What's 1+1? Answer in one word."}
    ],
    temperature=0,
    stream=True,
    stream_options={"include_usage": True}, # retrieving token usage for stream response
)

for chunk in response:
    print(f"choices: {chunk.choices}\nusage: {chunk.usage}")
    print("****************")
```

??? note "輸出"

    ```text
    choices: [Choice(delta=ChoiceDelta(content='', function_call=None, role='assistant', tool_calls=None), finish_reason=None, index=0, logprobs=None)]
    usage: None
    ****************
    choices: [Choice(delta=ChoiceDelta(content='Two', function_call=None, role=None, tool_calls=None), finish_reason=None, index=0, logprobs=None)]
    usage: None
    ****************
    choices: [Choice(delta=ChoiceDelta(content='.', function_call=None, role=None, tool_calls=None), finish_reason=None, index=0, logprobs=None)]
    usage: None
    ****************
    choices: [Choice(delta=ChoiceDelta(content=None, function_call=None, role=None, tool_calls=None), finish_reason='stop', index=0, logprobs=None)]
    usage: None
    ****************
    choices: []
    usage: CompletionUsage(completion_tokens=2, prompt_tokens=18, total_tokens=20)
    ****************
    ```

## 重點整理
- `stream=True` 的總耗時差不多，但首個 token 到得快很多，使用者體驗更好。
- streaming 的內容在 `delta` 裡，不是 `message`，而且 role、content 和結束訊號可能分別出現在不同 chunk。
- 內容是不完整的片段，審核會比較難做。
- 要拿用量要設定 `include_usage`，資料在最後一個 chunk，而且那個 chunk 的 `choices` 是空的。

## 練習
1. 修改 prompt，要求模型數到 20 就好，觀察 chunk 數量怎麼變。
2. 在 for 迴圈裡把每個 chunk 的 `delta.content` 即時 `print`（`end=""`），做出打字機效果。
3. 開啟 `include_usage`，在迴圈中判斷最後一個 chunk，印出總 token 用量，並自己加上首個 token 的延遲計時。
