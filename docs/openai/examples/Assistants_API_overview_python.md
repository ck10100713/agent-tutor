---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Assistants_API_overview_python.ipynb
---

# Assistants API 總覽（Python SDK）

> 原文：[examples/Assistants_API_overview_python.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Assistants_API_overview_python.ipynb)



## 這篇在做什麼

用 Python SDK 從頭走一遍 Assistants API：建立 Assistant、開 Thread、加 Message、跑 Run、讀回應，再接上 Code Interpreter、File Search 和自訂 Function 三種 tool。範例是一個 Math Tutor。

## 學完你會

- 分清楚 Assistant、Thread、Run 各自負責什麼，並用 `client.beta` 的 API 建出來
- 用輪詢（polling）等 Run 完成，然後按時間倒序讀 Thread 裡的 Message
- 幫 Assistant 加上 tool，處理 `requires_action` 狀態，把 function 的輸出用 `submit_tool_outputs` 送回去

## 開跑前

需要 OpenAI API key（呼叫模型會計費），並且把 `openai` Python SDK 更新到支援 Assistants API 的版本。



新的 [Assistants API](https://platform.openai.com/docs/assistants/overview) 是 [Chat Completions API](https://platform.openai.com/docs/guides/text-generation/chat-completions-api) 的有狀態（stateful）進化版，目的是簡化類似助理的體驗的建置，也讓開發者能用 Code Interpreter 和 File Search 這些強大的 tool。

![Assistants API Diagram](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/assistants_overview_diagram.png)

## Chat Completions API 與 Assistants API 的差別

**Chat Completions API** 的基本單位是 `Messages`，你用某個 `Model`（`gpt-4o`、`gpt-4o-mini` 等）對它們做 `Completion`。它輕巧又強大，但本質上是無狀態的，也就是對話狀態、tool 定義、檢索文件和程式碼執行都要自己手動管理。

**Assistants API** 的基本單位是：

- `Assistants`：封裝基礎模型、instructions、tools 和（context）文件，
- `Threads`：代表對話的狀態，
- `Runs`：負責讓 `Assistant` 在某個 `Thread` 上執行，包含文字回應和多步驟的 tool 使用。

接下來看這些東西怎麼組合出強大的有狀態體驗。


## 環境設定

### Python SDK

> **Note**
> 我們更新了 [Python SDK](https://github.com/openai/openai-python)，加入對 Assistants API 的支援，所以你需要更新到最新版（寫這篇時是 `1.59.4`）。


```python
!pip install --upgrade openai
```

??? note "輸出"

    ```text
    Requirement already satisfied: openai in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (1.59.4)
    Requirement already satisfied: anyio<5,>=3.5.0 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (3.7.1)
    Requirement already satisfied: distro<2,>=1.7.0 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (1.9.0)
    Requirement already satisfied: httpx<1,>=0.23.0 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (0.27.0)
    Requirement already satisfied: jiter<1,>=0.4.0 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (0.7.0)
    Requirement already satisfied: pydantic<3,>=1.9.0 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (2.8.2)
    Requirement already satisfied: sniffio in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (1.3.1)
    Requirement already satisfied: tqdm>4 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (4.66.4)
    Requirement already satisfied: typing-extensions<5,>=4.11 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from openai) (4.12.2)
    Requirement already satisfied: idna>=2.8 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from anyio<5,>=3.5.0->openai) (3.7)
    Requirement already satisfied: certifi in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from httpx<1,>=0.23.0->openai) (2024.7.4)
    Requirement already satisfied: httpcore==1.* in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from httpx<1,>=0.23.0->openai) (1.0.5)
    Requirement already satisfied: h11<0.15,>=0.13 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from httpcore==1.*->httpx<1,>=0.23.0->openai) (0.14.0)
    Requirement already satisfied: annotated-types>=0.4.0 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from pydantic<3,>=1.9.0->openai) (0.7.0)
    Requirement already satisfied: pydantic-core==2.20.1 in /Users/lee.spacagna/myenv/lib/python3.12/site-packages (from pydantic<3,>=1.9.0->openai) (2.20.1)
    ```

並執行下面的指令確認是最新版：


```python
!pip show openai | grep Version
```

??? note "輸出"

    ```text
    Version: 1.59.4
    ```

### 漂亮輸出的輔助函式


```python
import json

def show_json(obj):
    display(json.loads(obj.model_dump_json()))
```

## Assistants API 完整範例


### Assistants


開始使用 Assistants API 最簡單的方式是 [Assistants Playground](https://platform.openai.com/playground)。


![Assistants Playground](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/assistants_overview_assistants_playground.png)


先來建立一個 assistant！我們照 [文件](https://platform.openai.com/docs/assistants/overview) 的做法建一個 Math Tutor。


![Creating New Assistant](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/assistants_overview_new_assistant.png)


你也可以直接透過 Assistants API 建立 Assistant，像這樣：


```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))


assistant = client.beta.assistants.create(
    name="Math Tutor",
    instructions="You are a personal math tutor. Answer questions briefly, in a sentence or less.",
    model="gpt-4o",
)
show_json(assistant)
```

??? note "輸出"

    ```text
    {'id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'created_at': 1736340398,
     'description': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'metadata': {},
     'model': 'gpt-4o',
     'name': 'Math Tutor',
     'object': 'assistant',
     'tools': [],
     'response_format': 'auto',
     'temperature': 1.0,
     'tool_resources': {'code_interpreter': None, 'file_search': None},
     'top_p': 1.0} 'tools': [],
     'response_format': 'auto',
     'temperature': 1.0,
     'tool_resources': {'code_interpreter': None, 'file_search': None},
     'top_p': 1.0}
    ```

不管你是用 Dashboard 還是 API 建立 Assistant，都要記下 Assistant ID。之後在 Threads 和 Runs 裡就是用它來指定這個 Assistant。


接著建立新的 Thread 並加入一則 Message。它會保存我們的對話狀態，所以不用每次都重送整段訊息歷史。


### Threads


建立新的 thread：


```python
thread = client.beta.threads.create()
show_json(thread)
```

??? note "輸出"

    ```text
    {'id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6',
     'created_at': 1736340398,
     'metadata': {},
     'object': 'thread',
     'tool_resources': {'code_interpreter': None, 'file_search': None}} 'object': 'thread',
     'tool_resources': {'code_interpreter': None, 'file_search': None}}
    ```

然後把 Message 加進 thread：


```python
message = client.beta.threads.messages.create(
    thread_id=thread.id,
    role="user",
    content="I need to solve the equation `3x + 11 = 14`. Can you help me?",
)
show_json(message)
```

??? note "輸出"

    ```text
    {'id': 'msg_1q4Y7ZZ9gIcPoAKSx9UtrrKJ',
     'assistant_id': None,
     'attachments': [],
     'completed_at': None,
     'attachments': [],
     'completed_at': None,
     'content': [{'text': {'annotations': [],
        'value': 'I need to solve the equation `3x + 11 = 14`. Can you help me?'},
       'type': 'text'}],
     'created_at': 1736340400,
     'incomplete_at': None,
     'incomplete_details': None,
     'metadata': {},
     'object': 'thread.message',
     'role': 'user',
     'run_id': None,
     'status': None,
     'thread_id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6'}
    ```

> **Note**
> 雖然你不再每次都送出整段歷史，但每次 Run 還是會按整段對話歷史的 token 計費。


### Runs

注意我們建立的 Thread **沒有**跟先前建立的 Assistant 綁在一起！Threads 是獨立於 Assistants 存在的，如果你用過 ChatGPT（thread 會綁定某個 model/GPT），這點可能跟你預期的不一樣。

要讓 Assistant 針對某個 Thread 產生回應，必須建立一個 Run。建立 Run 會通知 Assistant 去看 Thread 裡的 messages 並採取行動：要嘛加入單一回應，要嘛使用 tools。

> **Note**
> Run 是 Assistants API 和 Chat Completions API 的關鍵差異。Chat Completions 裡模型只會回一則 message，但在 Assistants API 裡，一次 Run 可能讓 Assistant 用到一個或多個 tool，並且可能在 Thread 加入多則 messages。

要讓 Assistant 回應使用者，來建立 Run。如前所述，你必須同時指定 Assistant 和 Thread。


```python
run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant.id,
)
show_json(run)
```

??? note "輸出"

    ```text
    {'id': 'run_qVYsWok6OCjHxkajpIrdHuVP',
     'assistant_id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'cancelled_at': None,
     'completed_at': None,
     'created_at': 1736340403,
     'expires_at': 1736341003,
     'failed_at': None,
     'incomplete_details': None,
     'incomplete_details': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'last_error': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'metadata': {},
     'model': 'gpt-4o',
     'object': 'thread.run',
     'parallel_tool_calls': True,
     'parallel_tool_calls': True,
     'required_action': None,
     'response_format': 'auto',
     'response_format': 'auto',
     'started_at': None,
     'status': 'queued',
     'thread_id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6',
     'tool_choice': 'auto',
     'tools': [],
     'truncation_strategy': {'type': 'auto', 'last_messages': None},
     'usage': None,
     'temperature': 1.0,
     'top_p': 1.0,
     'tool_resources': {}}
    ```

跟 Chat Completions API 建立 completion 不同，**建立 Run 是非同步的操作**。它會立刻回傳 Run 的 metadata，其中的 `status` 一開始會是 `queued`。Assistant 執行操作（像是用 tool 和加入 message）時，`status` 會跟著更新。

要知道 Assistant 什麼時候處理完，可以用迴圈輪詢 Run。（streaming 支援即將推出！）這裡只檢查 `queued` 或 `in_progress` 狀態，但實際上 Run 可能經歷[多種狀態變化](https://platform.openai.com/docs/api-reference/runs/object#runs/object-status)，你可以選擇把它們顯示給使用者看。（這些叫做 Steps，後面會講。）


```python
import time

def wait_on_run(run, thread):
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        time.sleep(0.5)
    return run
```

```python
run = wait_on_run(run, thread)
show_json(run)
```

??? note "輸出"

    ```text
    {'id': 'run_qVYsWok6OCjHxkajpIrdHuVP',
     'assistant_id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'cancelled_at': None,
     'completed_at': 1736340406,
     'created_at': 1736340403,
     'expires_at': None,
     'failed_at': None,
     'incomplete_details': None,
     'incomplete_details': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'last_error': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'metadata': {},
     'model': 'gpt-4o',
     'object': 'thread.run',
     'parallel_tool_calls': True,
     'parallel_tool_calls': True,
     'required_action': None,
     'response_format': 'auto',
     'started_at': 1736340405,
     'status': 'completed',
     'thread_id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6',
     'tool_choice': 'auto',
     'tools': [],
     'truncation_strategy': {'type': 'auto', 'last_messages': None},
     'usage': {'completion_tokens': 35,
      'prompt_tokens': 66,
      'total_tokens': 101,
      'prompt_token_details': {'cached_tokens': 0},
      'completion_tokens_details': {'reasoning_tokens': 0}},
     'temperature': 1.0,
     'top_p': 1.0,
     'tool_resources': {}}
    ```

### Messages


現在 Run 完成了，可以列出 Thread 裡的 Messages，看 Assistant 加了什麼。


```python
messages = client.beta.threads.messages.list(thread_id=thread.id)
show_json(messages)
```

??? note "輸出"

    ```text
    {'data': [{'id': 'msg_A5eAN6ZAJDmFBOYutEm5DFCy',
       'assistant_id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
       'attachments': [],
       'completed_at': None,
       'content': [{'text': {'annotations': [],
          'value': 'Sure! Subtract 11 from both sides to get \\(3x = 3\\), then divide by 3 to find \\(x = 1\\).'},
         'type': 'text'}],
       'created_at': 1736340405,
       'incomplete_at': None,
       'incomplete_details': None,
       'metadata': {},
       'object': 'thread.message',
       'role': 'assistant',
       'run_id': 'run_qVYsWok6OCjHxkajpIrdHuVP',
       'status': None,
       'thread_id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6'},
      {'id': 'msg_1q4Y7ZZ9gIcPoAKSx9UtrrKJ',
       'assistant_id': None,
       'attachments': [],
       'completed_at': None,
       'attachments': [],
       'completed_at': None,
       'content': [{'text': {'annotations': [],
          'value': 'I need to solve the equation `3x + 11 = 14`. Can you help me?'},
         'type': 'text'}],
       'created_at': 1736340400,
       'incomplete_at': None,
       'incomplete_details': None,
       'metadata': {},
       'object': 'thread.message',
       'role': 'user',
       'run_id': None,
       'status': None,
       'thread_id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6'}],
     'object': 'list',
     'first_id': 'msg_A5eAN6ZAJDmFBOYutEm5DFCy',
     'last_id': 'msg_1q4Y7ZZ9gIcPoAKSx9UtrrKJ',
     'has_more': False}
    ```

可以看到 Messages 是按時間倒序排列的，這樣最新的結果永遠在第一個 `page`（因為結果可能分頁）。要留意這點，因為它跟 Chat Completions API 裡 messages 的順序相反。


來請 Assistant 把結果再解釋得詳細一點！


```python
# Create a message to append to our thread
message = client.beta.threads.messages.create(
    thread_id=thread.id, role="user", content="Could you explain this to me?"
)

# Execute our run
run = client.beta.threads.runs.create(
    thread_id=thread.id,
    assistant_id=assistant.id,
)

# Wait for completion
wait_on_run(run, thread)

# Retrieve all the messages added after our last user message
messages = client.beta.threads.messages.list(
    thread_id=thread.id, order="asc", after=message.id
)
show_json(messages)
```

??? note "輸出"

    ```text
    {'data': [{'id': 'msg_wSHHvaMnaWktZWsKs6gyoPUB',
       'assistant_id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
       'attachments': [],
       'completed_at': None,
       'content': [{'text': {'annotations': [],
          'value': 'Certainly! To isolate \\(x\\), first subtract 11 from both sides of the equation \\(3x + 11 = 14\\), resulting in \\(3x = 3\\). Then, divide both sides by 3 to solve for \\(x\\), giving you \\(x = 1\\).'},
         'type': 'text'}],
       'created_at': 1736340414,
       'incomplete_at': None,
       'incomplete_details': None,
       'metadata': {},
       'object': 'thread.message',
       'role': 'assistant',
       'run_id': 'run_lJsumsDtPTmdG3Enx2CfYrrq',
       'status': None,
       'thread_id': 'thread_j4dc1TiHPfkviKUHNi4aAsA6'}],
     'object': 'list',
     'first_id': 'msg_wSHHvaMnaWktZWsKs6gyoPUB',
     'last_id': 'msg_wSHHvaMnaWktZWsKs6gyoPUB',
     'has_more': False}
    ```

為了拿到一個回應要走這麼多步驟，特別是這麼簡單的例子，可能會覺得有點繁瑣。不過你很快就會看到，幾乎不用改多少程式碼，就能幫 Assistant 加上很強大的功能！


### 範例


來看看怎麼把這些全部組合起來。下面就是使用你建好的 Assistant 所需的全部程式碼。

因為我們已經建好 Math Assistant，我把它的 ID 存在 `MATH_ASSISTANT_ID`。然後定義了兩個函式：

- `submit_message`：在 Thread 上建立 Message，然後啟動（並回傳）一個新的 Run
- `get_response`：回傳 Thread 裡的 Message 清單


```python
from openai import OpenAI

MATH_ASSISTANT_ID = assistant.id  # or a hard-coded ID like "asst-..."

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

def submit_message(assistant_id, thread, user_message):
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=user_message
    )
    return client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=assistant_id,
    )


def get_response(thread):
    return client.beta.threads.messages.list(thread_id=thread.id, order="asc")
```

我也定義了一個可重複使用的 `create_thread_and_run` 函式（其實跟 API 裡的 [`client.beta.threads.create_and_run`](https://platform.openai.com/docs/api-reference/runs/createThreadAndRun) 複合函式幾乎一樣 ;) ）。最後，我們把每個模擬的使用者請求各自送到新的 Thread。

注意這些 API 呼叫全都是非同步操作，也就是說，不用任何 async 函式庫（例如 `asyncio`），我們的程式碼就有了非同步的行為！


```python
def create_thread_and_run(user_input):
    thread = client.beta.threads.create()
    run = submit_message(MATH_ASSISTANT_ID, thread, user_input)
    return thread, run


# Emulating concurrent user requests
thread1, run1 = create_thread_and_run(
    "I need to solve the equation `3x + 11 = 14`. Can you help me?"
)
thread2, run2 = create_thread_and_run("Could you explain linear algebra to me?")
thread3, run3 = create_thread_and_run("I don't like math. What can I do?")

# Now all Runs are executing...
```

所有 Run 都啟動後，就可以逐一等待並取得回應。


```python
import time

# Pretty printing helper
def pretty_print(messages):
    print("# Messages")
    for m in messages:
        print(f"{m.role}: {m.content[0].text.value}")
    print()


# Waiting in a loop
def wait_on_run(run, thread):
    while run.status == "queued" or run.status == "in_progress":
        run = client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id,
        )
        time.sleep(0.5)
    return run


# Wait for Run 1
run1 = wait_on_run(run1, thread1)
pretty_print(get_response(thread1))

# Wait for Run 2
run2 = wait_on_run(run2, thread2)
pretty_print(get_response(thread2))

# Wait for Run 3
run3 = wait_on_run(run3, thread3)
pretty_print(get_response(thread3))

# Thank our assistant on Thread 3 :)
run4 = submit_message(MATH_ASSISTANT_ID, thread3, "Thank you!")
run4 = wait_on_run(run4, thread3)
pretty_print(get_response(thread3))
```

??? note "輸出"

    ```text
    # Messages
    user: I need to solve the equation `3x + 11 = 14`. Can you help me?
    assistant: Sure! Subtract 11 from both sides to get \(3x = 3\), then divide by 3 to find \(x = 1\).

    # Messages
    user: Could you explain linear algebra to me?
    assistant: Linear algebra is the branch of mathematics concerning vector spaces, linear transformations, and systems of linear equations, often represented with matrices.

    # Messages
    user: I don't like math. What can I do?
    assistant: Try relating math to real-life interests or hobbies, practice with fun games or apps, and gradually build confidence with easier problems.

    # Messages
    user: I don't like math. What can I do?
    assistant: Try relating math to real-life interests or hobbies, practice with fun games or apps, and gradually build confidence with easier problems.
    user: Thank you!
    assistant: You're welcome! If you have any more questions, feel free to ask!
    ```

大功告成！

你可能發現這段程式碼其實跟我們的 math Assistant 完全無關⋯⋯只要改 Assistant ID，這段程式碼就能用在你建立的任何新 Assistant。這就是 Assistants API 的威力。


## Tools

Assistants API 的一個關鍵功能是能替 Assistant 配備 Tools，像是 Code Interpreter、File Search 和自訂 Functions。我們逐一來看。

### Code Interpreter

幫我們的 Math Tutor 加上 [Code Interpreter](https://platform.openai.com/docs/assistants/tools/code-interpreter) tool，可以從 Dashboard 操作⋯⋯


![Enabling code interpreter](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/assistants_overview_enable_code_interpreter.png)


⋯⋯或是用 API，透過 Assistant ID 更新。


```python
assistant = client.beta.assistants.update(
    MATH_ASSISTANT_ID,
    tools=[{"type": "code_interpreter"}],
)
show_json(assistant)
```

??? note "輸出"

    ```text
    {'id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'created_at': 1736340398,
     'description': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'metadata': {},
     'model': 'gpt-4o',
     'name': 'Math Tutor',
     'object': 'assistant',
     'tools': [{'type': 'code_interpreter'}],
     'response_format': 'auto',
     'temperature': 1.0,
     'tool_resources': {'code_interpreter': {'file_ids': []}, 'file_search': None},
     'top_p': 1.0} 'tools': [{'type': 'code_interpreter'}],
     'response_format': 'auto',
     'temperature': 1.0,
     'tool_resources': {'code_interpreter': {'file_ids': []}, 'file_search': None},
     'top_p': 1.0}
    ```

現在，請 Assistant 用它的新 tool。


```python
thread, run = create_thread_and_run(
    "Generate the first 20 fibbonaci numbers with code."
)
run = wait_on_run(run, thread)
pretty_print(get_response(thread))
```

??? note "輸出"

    ```text
    # Messages
    user: Generate the first 20 fibbonaci numbers with code.
    assistant: The first 20 Fibonacci numbers are: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987, 1597, 2584, 4181.
    ```

這樣就好了！Assistant 在背景用了 Code Interpreter，然後給我們最後的回應。

有些情境這樣就夠了。不過，如果想知道 Assistant 到底做了什麼，可以看 Run 的 Steps。

### Steps


一個 Run 由一個或多個 Steps 組成。跟 Run 一樣，每個 Step 都有可以查詢的 `status`。這很適合用來把 Step 的進度顯示給使用者（例如 Assistant 寫程式或做檢索時顯示 spinner）。


```python
run_steps = client.beta.threads.runs.steps.list(
    thread_id=thread.id, run_id=run.id, order="asc"
)
```

來看每個 Step 的 `step_details`。


```python
for step in run_steps.data:
    step_details = step.step_details
    print(json.dumps(show_json(step_details), indent=4))
```

??? note "輸出"

    ```text
    {'tool_calls': [{'id': 'call_E1EE1loDmcWoc7FpkOMKYj6n',
       'code_interpreter': {'input': 'def generate_fibonacci(n):\n    fib_sequence = [0, 1]\n    while len(fib_sequence) < n:\n        next_value = fib_sequence[-1] + fib_sequence[-2]\n        fib_sequence.append(next_value)\n    return fib_sequence\n\n# Generate the first 20 Fibonacci numbers\nfirst_20_fibonacci = generate_fibonacci(20)\nfirst_20_fibonacci',
        'outputs': []},
       'type': 'code_interpreter'}],
     'type': 'tool_calls'}
    ```

    ```text
    null
    ```

    ```text
    {'message_creation': {'message_id': 'msg_RzTnbBMmzDYHk79a0x9qM5uU'},
     'type': 'message_creation'}
    ```

    ```text
    null
    ```

我們看到兩個 Step 的 `step_details`：

1. `tool_calls`（用複數，因為單一 Step 裡可能有不只一個）
2. `message_creation`

第一個 Step 是 `tool_calls`，具體是用 `code_interpreter`，裡面包含：

- `input`：呼叫 tool 之前產生的 Python 程式碼，
- `output`：Code Interpreter 執行後的結果。

第二個 Step 是 `message_creation`，裡面是加到 Thread 用來向使用者傳達結果的 `message`。


### File search

Assistants API 另一個強大的 tool 是 [File search](https://platform.openai.com/docs/assistants/tools/file-search)。它讓你把檔案上傳給 Assistant，當成回答問題時的知識庫。


![Enabling retrieval](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/assistants_overview_enable_retrieval.png)


```python
# Upload the file
file = client.files.create(
    file=open(
        "data/language_models_are_unsupervised_multitask_learners.pdf",
        "rb",
    ),
    purpose="assistants",
)

# Create a vector store
vector_store = client.beta.vector_stores.create(
    name="language_models_are_unsupervised_multitask_learners",
)

# Add the file to the vector store
vector_store_file = client.beta.vector_stores.files.create_and_poll(
    vector_store_id=vector_store.id,
    file_id=file.id,
)

# Confirm the file was added
while vector_store_file.status == "in_progress":
    time.sleep(1)
if vector_store_file.status == "completed":
    print("File added to vector store")
elif vector_store_file.status == "failed":
    raise Exception("Failed to add file to vector store")

# Update Assistant
assistant = client.beta.assistants.update(
    MATH_ASSISTANT_ID,
    tools=[{"type": "code_interpreter"}, {"type": "file_search"}],
    tool_resources={
        "file_search":{
            "vector_store_ids": [vector_store.id]
        },
        "code_interpreter": {
            "file_ids": [file.id]
        }
    },
)
show_json(assistant)
```

??? note "輸出"

    ```text
    File added to vector store
    ```

    ```text
    {'id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'created_at': 1736340398,
     'description': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'metadata': {},
     'model': 'gpt-4o',
     'name': 'Math Tutor',
     'object': 'assistant',
     'tools': [{'type': 'code_interpreter'},
      {'type': 'file_search',
       'file_search': {'max_num_results': None,
        'ranking_options': {'score_threshold': 0.0,
         'ranker': 'default_2024_08_21'}}}],
     'response_format': 'auto',
     'temperature': 1.0,
     'tool_resources': {'code_interpreter': {'file_ids': ['file-GQFm2i7N8LrAQatefWKEsE']},
      'file_search': {'vector_store_ids': ['vs_dEArILZSJh7J799QACi3QhuU']}},
     'top_p': 1.0}
    ```

```python
thread, run = create_thread_and_run(
    "What are some cool math concepts behind this ML paper pdf? Explain in two sentences."
)
run = wait_on_run(run, thread)
pretty_print(get_response(thread))
```

??? note "輸出"

    ```text
    # Messages
    user: What are some cool math concepts behind this ML paper pdf? Explain in two sentences.
    assistant: The paper explores the concept of multitask learning where a single model is used to perform various tasks, modeling the conditional distribution \( p(\text{output} | \text{input, task}) \), inspired by probabilistic approaches【6:10†source】. It also discusses the use of Transformer-based architectures and parallel corpus substitution in language models, enhancing their ability to generalize across domain tasks without explicit task-specific supervision【6:2†source】【6:5†source】.
    ```

> **Note**
> File Search 還有更多細節，像是 [Annotations](https://platform.openai.com/docs/assistants/how-it-works/managing-threads-and-messages)，可能會在另一份 cookbook 講。


```python
# Delete the vector store
client.beta.vector_stores.delete(vector_store.id)
```

??? note "輸出"

    ```text
    VectorStoreDeleted(id='vs_dEArILZSJh7J799QACi3QhuU', deleted=True, object='vector_store.deleted')
    ```

### Functions

Assistant 最後一個強大的 tool，是你可以指定自訂的 [Functions](https://platform.openai.com/docs/assistants/tools/function-calling)（很像 Chat Completions API 的 [Function Calling](https://platform.openai.com/docs/guides/function-calling)）。在 Run 期間，Assistant 可以表示它想呼叫你指定的一個或多個 function。接著由你負責呼叫 Function，並把輸出送回給 Assistant。

來看一個例子，幫 Math Tutor 定義一個 `display_quiz()` Function。

這個 function 接收一個 `title` 和一個 `question` 陣列，顯示測驗，並取得使用者對每題的輸入：

- `title`
- `questions`
  - `question_text`
  - `question_type`：[`MULTIPLE_CHOICE`, `FREE_RESPONSE`]
  - `choices`：["choice 1", "choice 2", ...]

我用 `get_mock_response...` 來模擬回應，實際上這裡就是取得使用者真正輸入的地方。


```python
def get_mock_response_from_user_multiple_choice():
    return "a"


def get_mock_response_from_user_free_response():
    return "I don't know."


def display_quiz(title, questions):
    print("Quiz:", title)
    print()
    responses = []

    for q in questions:
        print(q["question_text"])
        response = ""

        # If multiple choice, print options
        if q["question_type"] == "MULTIPLE_CHOICE":
            for i, choice in enumerate(q["choices"]):
                print(f"{i}. {choice}")
            response = get_mock_response_from_user_multiple_choice()

        # Otherwise, just get response
        elif q["question_type"] == "FREE_RESPONSE":
            response = get_mock_response_from_user_free_response()

        responses.append(response)
        print()

    return responses
```

測驗的範例長這樣：


```python
responses = display_quiz(
    "Sample Quiz",
    [
        {"question_text": "What is your name?", "question_type": "FREE_RESPONSE"},
        {
            "question_text": "What is your favorite color?",
            "question_type": "MULTIPLE_CHOICE",
            "choices": ["Red", "Blue", "Green", "Yellow"],
        },
    ],
)
print("Responses:", responses)
```

??? note "輸出"

    ```text
    Quiz: Sample Quiz

    What is your name?

    What is your favorite color?
    0. Red
    1. Blue
    2. Green
    3. Yellow

    Responses: ["I don't know.", 'a']
    ```

接著用 JSON 格式定義這個 function 的介面，讓 Assistant 能呼叫它：


```python
function_json = {
    "name": "display_quiz",
    "description": "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
    "parameters": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "questions": {
                "type": "array",
                "description": "An array of questions, each with a title and potentially options (if multiple choice).",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_text": {"type": "string"},
                        "question_type": {
                            "type": "string",
                            "enum": ["MULTIPLE_CHOICE", "FREE_RESPONSE"]
                        },
                        "choices": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["question_text"]
                }
            }
        },
        "required": ["title", "questions"]
    }
}
```

同樣地，透過 Dashboard 或 API 更新我們的 Assistant。


![Enabling custom function](https://raw.githubusercontent.com/openai/openai-cookbook/main/images/assistants_overview_enable_function.png)

> **Note**
> 把 function JSON 貼到 Dashboard 時，縮排之類的細節有點麻煩。我就請 ChatGPT 把我的 function 格式化成跟 Dashboard 上某個範例一樣 :)。


```python
assistant = client.beta.assistants.update(
    MATH_ASSISTANT_ID,
    tools=[
        {"type": "code_interpreter"},
        {"type": "file_search"},
        {"type": "function", "function": function_json},
    ],
)
show_json(assistant)
```

??? note "輸出"

    ```text
    {'id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'created_at': 1736340398,
     'description': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'metadata': {},
     'model': 'gpt-4o',
     'name': 'Math Tutor',
     'object': 'assistant',
     'tools': [{'type': 'code_interpreter'},
      {'type': 'file_search',
       'file_search': {'max_num_results': None,
        'ranking_options': {'score_threshold': 0.0,
         'ranker': 'default_2024_08_21'}}},
      {'function': {'name': 'display_quiz',
        'description': "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
        'description': "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
        'parameters': {'type': 'object',
         'properties': {'title': {'type': 'string'},
          'questions': {'type': 'array',
           'description': 'An array of questions, each with a title and potentially options (if multiple choice).',
           'items': {'type': 'object',
            'properties': {'question_text': {'type': 'string'},
             'question_type': {'type': 'string',
              'enum': ['MULTIPLE_CHOICE', 'FREE_RESPONSE']},
             'choices': {'type': 'array', 'items': {'type': 'string'}}},
            'required': ['question_text']}}},
         'required': ['title', 'questions']},
        'strict': False},
       'type': 'function'}],
     'response_format': 'auto',
     'temperature': 1.0,
     'tool_resources': {'code_interpreter': {'file_ids': ['file-GQFm2i7N8LrAQatefWKEsE']},
      'file_search': {'vector_store_ids': []}},
     'top_p': 1.0}
    ```

現在，來要求產生一份測驗。


```python
thread, run = create_thread_and_run(
    "Make a quiz with 2 questions: One open ended, one multiple choice. Then, give me feedback for the responses."
)
run = wait_on_run(run, thread)
run.status
```

??? note "輸出"

    ```text
    'requires_action'
    ```

這次檢查 Run 的 `status` 時，我們看到的是 `requires_action`！來仔細看看。


```python
show_json(run)
```

??? note "輸出"

    ```text
    {'id': 'run_ekMRSI2h35asEzKirRf4BTwZ',
     'assistant_id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'cancelled_at': None,
     'completed_at': None,
     'created_at': 1736341020,
     'expires_at': 1736341620,
     'failed_at': None,
     'incomplete_details': None,
     'incomplete_details': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'last_error': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'metadata': {},
     'model': 'gpt-4o',
     'object': 'thread.run',
     'parallel_tool_calls': True,
     'required_action': {'submit_tool_outputs': {'tool_calls': [{'id': 'call_uvJEn0fxM4sgmzek8wahBGLi',
         'function': {'arguments': '{"title":"Math Quiz","questions":[{"question_text":"What is the derivative of the function f(x) = 3x^2 + 2x - 5?","question_type":"FREE_RESPONSE"},{"question_text":"What is the value of \\\\( \\\\int_{0}^{1} 2x \\\\, dx \\\\)?","question_type":"MULTIPLE_CHOICE","choices":["0","1","2","3"]}]}',
          'name': 'display_quiz'},
         'type': 'function'}]},
      'type': 'submit_tool_outputs'},
     'response_format': 'auto',
     'started_at': 1736341022,
     'status': 'requires_action',
     'thread_id': 'thread_8bK2PXfoeijEHBVEzYuJXt17',
     'tool_choice': 'auto',
     'tools': [{'type': 'code_interpreter'},
      {'type': 'file_search',
       'file_search': {'max_num_results': None,
        'ranking_options': {'score_threshold': 0.0,
         'ranker': 'default_2024_08_21'}}},
      {'function': {'name': 'display_quiz',
        'description': "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
        'description': "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
        'parameters': {'type': 'object',
         'properties': {'title': {'type': 'string'},
          'questions': {'type': 'array',
    ... (省略 21 行)
    ```

`required_action` 欄位表示有一個 Tool 在等我們執行並把輸出送回給 Assistant，具體來說就是 `display_quiz` function！先解析 `name` 和 `arguments`。

> **Note**
> 這個例子裡我們知道只有一個 Tool call，但實際上 Assistant 可能選擇呼叫多個 tools。


```python
# Extract single tool call
tool_call = run.required_action.submit_tool_outputs.tool_calls[0]
name = tool_call.function.name
arguments = json.loads(tool_call.function.arguments)

print("Function Name:", name)
print("Function Arguments:")
arguments
```

??? note "輸出"

    ```text
    Function Name: display_quiz
    Function Arguments:
    ```

    ```text
    {'title': 'Math Quiz',
     'questions': [{'question_text': 'What is the derivative of the function f(x) = 3x^2 + 2x - 5?',
       'question_type': 'FREE_RESPONSE'},
      {'question_text': 'What is the value of \\( \\int_{0}^{1} 2x \\, dx \\)?',
       'question_type': 'MULTIPLE_CHOICE',
       'choices': ['0', '1', '2', '3']}]}
    ```

現在用 Assistant 提供的參數真的呼叫 `display_quiz` function：


```python
responses = display_quiz(arguments["title"], arguments["questions"])
print("Responses:", responses)
```

??? note "輸出"

    ```text
    Quiz: Math Quiz
    Quiz: Math Quiz

    What is the derivative of the function f(x) = 3x^2 + 2x - 5?

    What is the value of \( \int_{0}^{1} 2x \, dx \)?
    0. 0
    1. 1
    2. 2
    3. 3

    Responses: ["I don't know.", 'a']
    ```

很好！（記得這些回應是我們先前模擬出來的。實際上，我們會從這次 function 呼叫取得使用者的輸入。）

有了回應之後，把它們送回給 Assistant。我們需要先前解析出來的 `tool_call` 裡的 `tool_call` ID，還要把回應的 `list` 編碼成 `str`。


```python
run = client.beta.threads.runs.submit_tool_outputs(
    thread_id=thread.id,
    run_id=run.id,
    tool_outputs=tool_outputs
)
show_json(run)
```

??? note "輸出"

    ```text
    {'id': 'run_ekMRSI2h35asEzKirRf4BTwZ',
     'assistant_id': 'asst_qvXmYlZV8zhABI2RtPzDfV6z',
     'cancelled_at': None,
     'completed_at': None,
     'created_at': 1736341020,
     'expires_at': 1736341620,
     'failed_at': None,
     'incomplete_details': None,
     'incomplete_details': None,
     'instructions': 'You are a personal math tutor. Answer questions briefly, in a sentence or less.',
     'last_error': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'max_completion_tokens': None,
     'max_prompt_tokens': None,
     'metadata': {},
     'model': 'gpt-4o',
     'object': 'thread.run',
     'parallel_tool_calls': True,
     'parallel_tool_calls': True,
     'required_action': None,
     'response_format': 'auto',
     'started_at': 1736341022,
     'status': 'queued',
     'thread_id': 'thread_8bK2PXfoeijEHBVEzYuJXt17',
     'tool_choice': 'auto',
     'tools': [{'type': 'code_interpreter'},
      {'type': 'file_search',
       'file_search': {'max_num_results': None,
        'ranking_options': {'score_threshold': 0.0,
         'ranker': 'default_2024_08_21'}}},
      {'function': {'name': 'display_quiz',
        'description': "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
        'description': "Displays a quiz to the student, and returns the student's response. A single quiz can have multiple questions.",
        'parameters': {'type': 'object',
         'properties': {'title': {'type': 'string'},
          'questions': {'type': 'array',
           'description': 'An array of questions, each with a title and potentially options (if multiple choice).',
           'items': {'type': 'object',
            'properties': {'question_text': {'type': 'string'},
    ... (省略 18 行)
    ```

現在可以再次等 Run 完成，然後檢查 Thread！


```python
run = wait_on_run(run, thread)
pretty_print(get_response(thread))
```

??? note "輸出"

    ```text
    # Messages
    user: Make a quiz with 2 questions: One open ended, one multiple choice. Then, give me feedback for the responses.
    assistant: Since no specific information was found in the uploaded file, I'll create a general math quiz for you:

    1. **Open-ended Question**: What is the derivative of the function \( f(x) = 3x^2 + 2x - 5 \)?

    2. **Multiple Choice Question**: What is the value of \( \int_{0}^{1} 2x \, dx \)?
        - A) 0
        - B) 1
        - C) 2
        - D) 3

    I will now present the quiz to you for response.
    assistant: Here is the feedback for your responses:

    1. **Derivative Question**: 
       - Your Response: "I don't know."
       - Feedback: The derivative of \( f(x) = 3x^2 + 2x - 5 \) is \( f'(x) = 6x + 2 \).

    2. **Integration Question**: 
       - Your Response: A) 0
       - Feedback: The correct answer is B) 1. The integration \(\int_{0}^{1} 2x \, dx \) evaluates to 1.
    ```

太棒了 🎉


## 結論

這篇涵蓋了很多內容，給自己擊個掌吧！希望你現在有了穩固的基礎，能用 Code Interpreter、Retrieval 和 Functions 這些 tool 打造強大的有狀態體驗！

為了精簡，有幾個部分沒有涵蓋，這裡列出一些可以繼續探索的資源：

- [Annotations](https://platform.openai.com/docs/assistants/how-it-works/managing-threads-and-messages)：解析檔案引用
- [Files](https://platform.openai.com/docs/api-reference/assistants/file-object)：Thread 範圍 vs Assistant 範圍
- [Parallel Function Calls](https://platform.openai.com/docs/guides/function-calling/parallel-function-calling)：單一 Step 裡呼叫多個 tools
- Multi-Assistant Thread Runs：單一 Thread 裡有來自多個 Assistants 的 Messages
- Streaming：即將推出！

現在去做點很棒的東西吧！[zing](https://www.youtube.com/watch?v=xvFZjo5PgG0&pp=ygUQcmljayByb2xsIG5vIGFkcw%3D%3D)


## 重點整理

- Assistants API 是有狀態的：Assistant 放設定，Thread 放對話，Run 負責執行，三者獨立存在。
- Run 是非同步的，要輪詢 `status`，而且一次 Run 可能用多個 tool、產生多則 message。
- Thread 的 messages 預設最新的在前面，跟 Chat Completions 相反。
- Steps 讓你看到 Run 內部做了什麼，像 tool 呼叫和 message 建立，適合做進度顯示。
- 自訂 Function 時，Run 會進入 `requires_action`，由你執行 function 再把輸出送回去。

## 練習

1. 把 Math Tutor 的 `instructions` 改成別的角色（例如英文寫作教練），只換 Assistant 設定，重跑 `submit_message` 和 `get_response`，確認其他程式碼不用動。
2. 在輪詢迴圈裡把每次的 `run.status` 印出來，並加上 `time.sleep` 的間隔調整，觀察 Run 會經過哪些狀態。
3. 仿照 `display_quiz`，另外定義一個自己的 function（例如 `get_weather(city)`），寫 JSON 介面、更新 Assistant，並處理 `requires_action` 把結果送回去。
