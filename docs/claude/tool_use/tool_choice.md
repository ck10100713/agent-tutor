---
translated: true
source: tool_use/tool_choice.ipynb
---
# Tool choice

> 原文：[tool_use/tool_choice.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/tool_use/tool_choice.ipynb)

用 tool_choice 參數控制 Claude 怎麼選 tool：自動選擇或強制指定。

## 這篇在做什麼

這篇介紹 tool use 的 `tool_choice` 參數：`auto`、`tool`、`any` 三種模式各自怎麼運作，各自適合什麼時候用。每種模式都用一個小範例，比較有沒有設定時 Claude 行為的差別。

## 學完你會

- 用 `auto` 讓 Claude 自己決定要不要呼叫 tool，並用 system prompt 避免它過度呼叫
- 用 `tool` 強制呼叫特定 tool，把它當成結構化 JSON 輸出的手段
- 用 `any` 做一個一定只透過 tool 回應的 chatbot

## 開跑前

需要 Anthropic API key。注意範例用 `claude-haiku-5-5`，原因見下面的 Model note。

Tool use 支援一個叫 `tool_choice` 的參數，讓你指定要 Claude 怎麼呼叫 tool。這個 notebook 會看它怎麼運作、什麼時候用。開始之前，請先確認你熟悉 Claude tool use 的基本概念。

`tool_choice` 參數有三個選項：

* `auto` 讓 Claude 自己決定要不要呼叫提供的 tool
* `tool` 讓我們強制 Claude 一定要用某個特定 tool
* `any` 告訴 Claude 一定要用提供的其中一個 tool，但不指定是哪個

來逐一看每個選項。先 import Anthropic SDK：

```python
from anthropic import Anthropic

client = Anthropic()
MODEL_NAME = "claude-haiku-5-5"
```

> **Model note：** 這個 notebook 用 `claude-haiku-5-5`，因為強制的 `tool_choice`（`{"type": "tool"}` / `{"type": "any"}`）在 Claude Haiku 5.5 上可用，但在 Claude Opus 5.5、Claude Sonnet 5.5 和 Claude Fable 5.1 上會被 400 拒絕。在那些 model 上，請用 `tool_choice: {"type": "auto"}` 加一句明確點名 tool 的指示，或在 tool 定義加 `"strict": true`，或用 structured outputs（`output_config.format`）。Haiku 5.5 可能在 `tool_use` block 前回傳 `thinking` block，所以請依 `type` 讀取 block，不要依位置。

## Auto

把 `tool_choice` 設成 `auto`，model 會自動決定要不要用 tool。這是用 tool 時的預設行為。

為了示範，我們給 Claude 一個假的網路搜尋 tool。我們會問 Claude 一些問題，有些需要呼叫搜尋 tool，有些 Claude 自己就答得出來。

先定義一個叫 `web_search` 的 tool。注意，為了讓 demo 簡單，我們其實沒有真的去搜尋網路：

```python
def web_search(topic):
    print(f"pretending to search the web for {topic}")


web_search_tool = {
    "name": "web_search",
    "description": "A tool to retrieve up to date information on a given topic by searching the web",
    "input_schema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "The topic to search the web for"},
        },
        "required": ["topic"],
    },
}
```

接著寫一個函式，接受 user_query 並連同 `web_search_tool` 一起傳給 Claude。

我們也把 `tool_choice` 設成 `auto`：

```py
tool_choice={"type": "auto"}
```

完整的函式如下：

```python
from datetime import date


def chat_with_web_search(user_query):
    messages = [{"role": "user", "content": user_query}]

    system_prompt = f"""
    Answer as many questions as you can using your existing knowledge.
    Only search the web for queries that you can not confidently answer.
    Today's date is {date.today().strftime("%B %d %Y")}
    If you think a user's question involves something in the future that hasn't happened yet, use the search tool.
    """

    response = client.messages.create(
        system=system_prompt,
        model=MODEL_NAME,
        messages=messages,
        max_tokens=2048,
        tool_choice={"type": "auto"},
        tools=[web_search_tool],
    )
    last_content_block = response.content[-1]
    if last_content_block.type == "text":
        print("Claude did NOT call a tool")
        print(f"Assistant: {last_content_block.text}")
    elif last_content_block.type == "tool_use":
        print("Claude wants to use a tool")
        print(last_content_block)
```

先問一個 Claude 不需要用 tool 就能回答的問題：

```python
chat_with_web_search("What color is the sky?")
```

??? note "輸出"

    ```text
    Claude did NOT call a tool
    Assistant: The sky is usually blue during the day. This happens because of Rayleigh scattering: sunlight passes through the atmosphere, and shorter blue wavelengths scatter off air molecules more than longer red wavelengths do, so blue light reaches our eyes from all directions.

    The sky can look different under other conditions. At sunrise and sunset it often looks orange, pink, or red, because light travels through more atmosphere and the blue is scattered out. On cloudy days it can look gray or white, and at night it is dark.
    ```

問「天空是什麼顏色？」時，Claude 沒有用 tool。再試一個 Claude 應該用網路搜尋 tool 才能回答的問題：

```python
chat_with_web_search("Who won the most recent Miami Grand Prix?")
```

??? note "輸出"

    ```text
    Claude wants to use a tool
    ToolUseBlock(id='toolu_01SpdeYBZfEhEMHUgC45MLau', caller=DirectCaller(type='direct'), input={'topic': 'Miami Grand Prix 2026 race winner'}, name='web_search', type='tool_use')
    ```

問最近一場邁阿密大獎賽時，Claude 無法確定自己的知識是不是最新，所以用了網路搜尋 tool！

再試幾個例子：

```python
# Claude should NOT need to use the tool for this:
chat_with_web_search("Who won the superbowl in 2022?")
```

??? note "輸出"

    ```text
    Claude did NOT call a tool
    Assistant: The **Los Angeles Rams** won Super Bowl LVI in February 2022, beating the Cincinnati Bengals 23–20 at SoFi Stadium in Inglewood, California.
    ```

```python
# Claude SHOULD use the tool for this:
chat_with_web_search("Who won the most recent Super Bowl?")
```

??? note "輸出"

    ```text
    Claude wants to use a tool
    ToolUseBlock(id='toolu_01538T8powgXWLgxc53avSnj', caller=DirectCaller(type='direct'), input={'topic': 'Super Bowl LX winner February 2026'}, name='web_search', type='tool_use')
    ```

### Prompt 很重要！

`tool_choice` 用 `auto` 時，花時間寫詳細的 prompt 很重要。Claude 常常太急著呼叫 tool。詳細的 prompt 能幫 Claude 判斷什麼時候該呼叫、什麼時候不該。上面的例子，我們在 system prompt 裡放了具體的指示：


```py
 system_prompt=f"""
    Answer as many questions as you can using your existing knowledge.  
    Only search the web for queries that you can not confidently answer.
    Today's date is {date.today().strftime("%B %d %Y")}
    If you think a user's question involves something in the future that hasn't happened yet, use the search tool.
"""
```



## 強制指定 tool

可以用 `tool_choice` 強制 Claude 使用特定 tool。下面的例子定義了兩個簡單的 tool：
* `print_sentiment_scores`：一個「騙」Claude 產生含情緒分析資料、結構良好的 JSON 輸出的 tool。這個做法的更多資訊，見 [Extracting Structured JSON using Claude and Tool Use](https://github.com/anthropics/anthropic-cookbook/blob/main/tool_use/extracting_structured_json.ipynb)
* `calculator`：很簡單的計算機 tool，接受兩個數字並相加


```python
tools = [
    {
        "name": "print_sentiment_scores",
        "description": "Prints the sentiment scores of a given tweet or piece of text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "positive_score": {
                    "type": "number",
                    "description": "The positive sentiment score, ranging from 0.0 to 1.0.",
                },
                "negative_score": {
                    "type": "number",
                    "description": "The negative sentiment score, ranging from 0.0 to 1.0.",
                },
                "neutral_score": {
                    "type": "number",
                    "description": "The neutral sentiment score, ranging from 0.0 to 1.0.",
                },
            },
            "required": ["positive_score", "negative_score", "neutral_score"],
        },
    },
    {
        "name": "calculator",
        "description": "Adds two number",
        "input_schema": {
            "type": "object",
            "properties": {
                "num1": {"type": "number", "description": "first number to add"},
                "num2": {"type": "number", "description": "second number to add"},
            },
            "required": ["num1", "num2"],
        },
    },
]
```

我們的目標是寫一個叫 `analyze_tweet_sentiment` 的函式，接受一則推文並印出它的基本情緒分析。最後我們會「強制」Claude 使用情緒分析 tool，但先看**沒有**強制時會發生什麼。

在 `analyze_tweet_sentiment` 函式這第一個「不好」的版本裡，我們給 Claude 兩個 tool。為了比較，先把 tool_choice 設成 "auto"：

```py
tool_choice={"type": "auto"}
```

注意，我們刻意沒有給 Claude 寫得好的 prompt，這樣比較容易看出強制使用特定 tool 的影響。

```python
def analyze_tweet_sentiment(query):
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        tools=tools,
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": query}],
    )
    print(response)
```

來看用推文「Holy cow, I just made the most incredible meal!」呼叫這個函式會怎樣：

```python
analyze_tweet_sentiment("Holy cow, I just made the most incredible meal!")
```

??? note "輸出"

    ```text
    Message(id='msg_011Cg4UE1eK9vKN67pFtQGAE', container=None, content=[ThinkingBlock(signature='CAQS3wQKVAgSGAIiQMDKvq1uCMHUFMYMLRqz9mc8ezXulDzkMGkuTQHJIrvlB06LzRbMsiGV9wrypeySQOKKwY0o/2Ue/a3Y58uWy0coATgBQgh0aGlua2luZxIMce+sUvV2rOuYXjsCGgz/XltMeJn60CZXp5wiMIA8qT8ZyWA5Kus+50RkRuihJ1IK0DW/cuTU6uqTVQWd02B9p+ck0VGPe2A1ElNw0yq4Axt7+RN5Ah7vznLvh/csm6LWn73juCvwYET8rIl1EArIVDdU24vIb3Ot5CVsRh16xSMsrvuF1MPvQ52nLZy7y7B47ZgNxHE8SxwQ9xMbtwyb5Y3fWqetr+YfzJ1R1Siz2u6+21D4+QRQQYhyUyjBO7M2XwpQsM1Hxw8J5u3CUFQTyde3aj2pR+p6fmR8Xct/+/YjBlTvkr9vr3dnOqmUZ8O7AuRA8WhG3EB6Ja1pLPXqD/cvp8gc5AT4/hVohJymzSvCG4lS+bwXAz5q7d1EiVnW1xYeCwepie3FEEBr4h7z2ZBbG/6NBcA+ATyUiprE+sfaPM0/1dO//tSzgmqElfgXaFskT2j4veYlOdTqN1sYYkFLr2q9CWC+m66oxEKlILZuv75J70mGscNdzSNmpj9U6ZP9XF1fDBShCayoD4ldplrmBYVoIytxhtXK5uK0DWE+ZMhTznOPgaN/pTcXtxxH+JDxTKAia9R8Ybt3lHzmo1Xe+rpMb+c7y3VZ4LPZLLOeN/bBvGCT3UrHzPThmup2iC4Cv/TPfYdCDuMzsblC9pYmsCza1Lm6zgeeBkVIflyviJvP9ynaGAI=', thinking="The user says a sentence. They didn't ask for sentiment analysis explicitly. The tool prints sentiment scores of a given text, but the tool takes scores as input, not text. Odd tool: it takes positive/negative/neutral scores as parameters. I could compute the sentiment myself and call the tool. But is that appropriate? The user just made an exclamation. Perhaps they want a reply. I should respond warmly and ask what meal. Maybe don't call tools. Keep short.", type='thinking'), TextBlock(citations=None, text="That sounds like a great cooking win! What did you make? I'd love to hear about it, whether it was a new recipe or something you improvised.", type='text')], model='claude-haiku-5-5', role='assistant', stop_details=None, stop_reason='end_turn', stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=641, output_tokens=204, output_tokens_details=OutputTokensDetails(thinking_tokens=159), server_tool_use=None, service_tier='standard', iterations=[{'input_tokens': 641, 'output_tokens': 204, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0}, 'type': 'message'}]), diagnostics=None)
    ```

Claude 沒有呼叫我們的情緒分析 tool：
> "That's awesome! It sounds like you're really excited about what you cooked up! ... What did you make?"

接著想像有人發這則推文：「I love my cats! I had four and just adopted 2 more! Guess how many I have now?」

```python
analyze_tweet_sentiment(
    "I love my cats! I had four and just adopted 2 more! Guess how many I have now?"
)
```

??? note "輸出"

    ```text
    Message(id='msg_011Cg4UE7w5FcmGvkmnTu5VZ', container=None, content=[ThinkingBlock(signature='CAQS3wQKVAgSGAIiQJ7UaMKDMvsTIn1kJ0Te9nRzODOnCAoYHJi+CGhKk5UDoE4DeWUxufJOoIxpqttyVQh7wM92v7yThy+IoTtd03MoATgBQgh0aGlua2luZxIMNFG7YQbnyz2X1D/TGgxXg2nr0W4L8ZstJwkiMF5b0+gbQPn/feXqPS2jpUzsr6t1S4yFIHieCLh57xTWkooGV20IQe+UNKWUZaUVHCq4A3Cui6nrsekoJzDtQwDbsS88joumwS8jQIkBE4IaLYXQ5egQn55YJg1vdo7jWHU2+YgpfwNoZ+D/dKDbYxtvxkKZLyyo8ZL8caV9COfVJlcIbyWiL7QImqjJ58elKjt9ylwb1W6ML6mgLVt3UX/RKwA/eXXDUgHlAzn7MGM869AdSRbI6vuA9+8PgXgwWJQCa9Uo7WwwtJ4NYILHYUdyYWA43fDb5raTKAEFZ638DnupUnsL9SpRU0k24iInBxEoOoshgQsWpwayrFjgBzvsUtv6BCU5VnJYF09P+QPq05xYj/ssE0J/XL9Yu8M3HXJtuzFirD5YTI8R9D5H/GrvzkM5dXhmXobacc4zC5YC6MZ3CveLLPMJ2D2WRf/SBo1t3+0N25Gp+yZ2Tc4Gu37jWykiNDLZaSPrOvgAVBmPT+h0IIfFxsNjK3xaq7xeOiUMbbWdUzW0FlxkdjTUW4ZUJep9JksYQglCuGLmyuidnyIdb+XwadKO/GWglT1hNX15S+3Mi3BmQGojGfUNmvawbfuwmdvsFXZpCZyiaZLcNsqxu1axCgCvpWmVgiEwEQKRLvvLaFdS3BeQGAI=', thinking="The user asks a simple math question: 4 + 2 = 6. I can use calculator tool. Should I? It's simple; could just answer. The tool exists; using it is fine. I'll call calculator with 4 and 2.", type='thinking'), ToolUseBlock(id='toolu_01DoLR6PzfydqVfjbS9iRgQ6', caller=DirectCaller(type='direct'), input={'num1': 4, 'num2': 2}, name='calculator', type='tool_use')], model='claude-haiku-5-5', role='assistant', stop_details=None, stop_reason='tool_use', stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=652, output_tokens=144, output_tokens_details=OutputTokensDetails(thinking_tokens=73), server_tool_use=None, service_tier='standard', iterations=[{'input_tokens': 652, 'output_tokens': 144, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0}, 'type': 'message'}]), diagnostics=None)
    ```

Claude 想呼叫計算機 tool：

> ToolUseBlock(id='toolu_01...', input={'num1': 4, 'num2': 2}, name='calculator', type='tool_use')

很明顯，目前這個實作沒有做到我們要的（主要是因為我們故意設成會失敗）。

接下來，更新 `tool_choice`，強制 Claude **永遠**使用 `print_sentiment_scores` tool：

```py
tool_choice={"type": "tool", "name": "print_sentiment_scores"}
```

除了把 `type` 設成 `tool`，還必須提供特定的 tool 名稱。

```python
def analyze_tweet_sentiment(query):
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        tools=tools,
        tool_choice={"type": "tool", "name": "print_sentiment_scores"},
        messages=[{"role": "user", "content": query}],
    )
    print(response)
```

現在用前面同樣的 prompt 問 Claude，它一定會呼叫 `print_sentiment_scores` tool：

```python
analyze_tweet_sentiment("Holy cow, I just made the most incredible meal!")
```

??? note "輸出"

    ```text
    Message(id='msg_011Cg4UECUfkHso53Kieoabs', container=None, content=[ToolUseBlock(id='toolu_01WJoB9kA8sjR17wJ8vK4VCq', caller=DirectCaller(type='direct'), input={'positive_score': 0.95, 'negative_score': 0.02, 'neutral_score': 0.03}, name='print_sentiment_scores', type='tool_use')], model='claude-haiku-5-5', role='assistant', stop_details=None, stop_reason='tool_use', stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=772, output_tokens=90, output_tokens_details=OutputTokensDetails(thinking_tokens=0), server_tool_use=None, service_tier='standard', iterations=[{'input_tokens': 772, 'output_tokens': 90, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0}, 'type': 'message'}]), diagnostics=None)
    ```

Claude 呼叫了我們的 `print_sentiment_scores` tool：

> ToolUseBlock(id='toolu_01...', input={'positive_score': 0.95, 'negative_score': 0.02, 'neutral_score': 0.03}, name='print_sentiment_scores', type='tool')

即使我們拿「數學味」的推文去絆它，它還是一定會呼叫 `print_sentiment_scores` tool：

```python
analyze_tweet_sentiment(
    "I love my cats! I had four and just adopted 2 more! Guess how many I have now?"
)
```

??? note "輸出"

    ```text
    Message(id='msg_011Cg4UEHS5DckQXLEsK4bp5', container=None, content=[ToolUseBlock(id='toolu_01B4Pdo9ceA6PAqtGNufwPyy', caller=DirectCaller(type='direct'), input={'positive_score': 0.95, 'negative_score': 0.01, 'neutral_score': 0.04}, name='print_sentiment_scores', type='tool_use'), ToolUseBlock(id='toolu_01Rciej4xSiLg62Ff4fumQTk', caller=DirectCaller(type='direct'), input={'num1': 4, 'num2': 2}, name='calculator', type='tool_use')], model='claude-haiku-5-5', role='assistant', stop_details=None, stop_reason='tool_use', stop_sequence=None, type='message', usage=Usage(cache_creation=CacheCreation(ephemeral_1h_input_tokens=0, ephemeral_5m_input_tokens=0), cache_creation_input_tokens=0, cache_read_input_tokens=0, inference_geo='global', input_tokens=783, output_tokens=157, output_tokens_details=OutputTokensDetails(thinking_tokens=0), server_tool_use=None, service_tier='standard', iterations=[{'input_tokens': 783, 'output_tokens': 157, 'cache_read_input_tokens': 0, 'cache_creation_input_tokens': 0, 'cache_creation': {'ephemeral_5m_input_tokens': 0, 'ephemeral_1h_input_tokens': 0}, 'type': 'message'}]), diagnostics=None)
    ```

強制 tool 保證指定的 tool 會被呼叫，但不會阻止 Claude 在同一輪呼叫*其他* tool：上面的執行裡它也同時呼叫了 `calculator`。如果你需要剛好一次 tool 呼叫，也要在 `tool_choice` 裡傳 `disable_parallel_tool_use=True`。

即使我們強制 Claude 呼叫 `print_sentiment_scores` tool，仍然應該用一些基本的 prompt engineering：

```python
def analyze_tweet_sentiment(query):
    prompt = f"""
    Analyze the sentiment in the following tweet:
    <tweet>{query}</tweet>
    """

    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=4096,
        tools=tools,
        tool_choice={"type": "auto"},
        messages=[{"role": "user", "content": prompt}],
    )
    print(response)
```

## Any

`tool_choice` 的最後一個選項是 `any`，讓我們告訴 Claude「你一定要呼叫 tool，但你可以挑要哪個」。想像我們要用 Claude 做一個 SMS chatbot。這個 chatbot 唯一能真正跟使用者「溝通」的方式就是 SMS 簡訊。

下面的例子做了一個很簡單的簡訊助理，有兩個 tool 可用：
* `send_text_to_user` 傳簡訊給使用者
* `get_customer_info` 根據 username 查客戶資料

想法是做出一個永遠呼叫其中一個 tool、絕不用非 tool 方式回應的 chatbot。任何情況下，Claude 要嘛嘗試傳簡訊回覆，要嘛呼叫 `get_customer_info` 取得更多客戶資訊。

最重要的是，我們把 `tool_choice` 設成 "any"：

```py
tool_choice={"type": "any"}
```

```python
def send_text_to_user(text):
    # Sends a text to the user
    # We'll just print out the text to keep things simple:
    print(f"TEXT MESSAGE SENT: {text}")


def get_customer_info(username):
    return {
        "username": username,
        "email": f"{username}@email.com",
        "purchases": [
            {"id": 1, "product": "computer mouse"},
            {"id": 2, "product": "screen protector"},
            {"id": 3, "product": "usb charging cable"},
        ],
    }


tools = [
    {
        "name": "send_text_to_user",
        "description": "Sends a text message to a user",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The piece of text to be sent to the user via text message",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "get_customer_info",
        "description": "gets information on a customer based on the customer's username.  Response includes email, username, and previous purchases. Only call this tool once a user has provided you with their username",
        "input_schema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "The username of the user in question. ",
                },
            },
            "required": ["username"],
        },
    },
]

system_prompt = """
All your communication with a user is done via text message.
Only call tools when you have enough information to accurately call them.
Do not call the get_customer_info tool until a user has provided you with their username. This is important.
If you do not know a user's username, simply ask a user for their username.
"""


def sms_chatbot(user_message):
    messages = [{"role": "user", "content": user_message}]

    response = client.messages.create(
        system=system_prompt,
        model=MODEL_NAME,
        max_tokens=4096,
        tools=tools,
        tool_choice={"type": "any"},
        messages=messages,
    )
    if response.stop_reason == "tool_use":
        last_content_block = response.content[-1]
        if last_content_block.type == "tool_use":
            tool_name = last_content_block.name
            tool_inputs = last_content_block.input
            print(f"=======Claude Wants To Call The {tool_name} Tool=======")
            if tool_name == "send_text_to_user":
                send_text_to_user(tool_inputs["text"])
            elif tool_name == "get_customer_info":
                print(get_customer_info(tool_inputs["username"]))
            else:
                print("Oh dear, that tool doesn't exist!")

    else:
        print("No tool was called. This shouldn't happen!")
```

先從簡單的開始：

```python
sms_chatbot("Hey there! How are you?")
```

??? note "輸出"

    ```text
    =======Claude Wants To Call The send_text_to_user Tool=======
    TEXT MESSAGE SENT: Hey there! I'm doing well, thanks for asking. How can I help you today? If you need help with your account or a previous purchase, please send me your username.
    ```

Claude 呼叫 `send_text_to_user` tool 來回覆。

接著問 Claude 比較棘手的問題：

```python
sms_chatbot("I need help looking up an order")
```

??? note "輸出"

    ```text
    =======Claude Wants To Call The send_text_to_user Tool=======
    TEXT MESSAGE SENT: I'd be happy to help you look up your order. Could you please provide your username?
    ```

Claude 想傳簡訊，請使用者提供 username。

現在看看提供我們的 username 給 Claude 會怎樣：

```python
sms_chatbot("I need help looking up an order.  My username is jenny76")
```

??? note "輸出"

    ```text
    =======Claude Wants To Call The get_customer_info Tool=======
    {'username': 'jenny76', 'email': 'jenny76@email.com', 'purchases': [{'id': 1, 'product': 'computer mouse'}, {'id': 2, 'product': 'screen protector'}, {'id': 3, 'product': 'usb charging cable'}]}
    ```

Claude 呼叫了 `get_customer_info` tool，正如我們希望的！

即使傳一則亂碼訊息給 Claude，它還是會呼叫我們的其中一個 tool：

```python
sms_chatbot("askdj aksjdh asjkdbhas kjdhas 1+1 ajsdh")
```

??? note "輸出"

    ```text
    =======Claude Wants To Call The send_text_to_user Tool=======
    TEXT MESSAGE SENT: Hi! I'm not sure I understood your message. It looks like it may have been sent by mistake. Could you tell me what you need help with? If you have an account question, please share your username so I can look up your information.
    ```

## 重點整理

- `auto` 是預設，由 Claude 決定要不要用 tool；它可能過度呼叫，所以要靠 system prompt 寫清楚何時該用
- `tool` 強制呼叫指定 tool，常用來取得穩定的結構化 JSON 輸出
- 強制一個 tool 不代表只會呼叫那一個，要只有一次呼叫得加 `disable_parallel_tool_use=True`
- `any` 保證一定會呼叫 tool 但由 Claude 挑，適合只能透過 tool 回應的 chatbot
- 強制式 `tool_choice` 並非所有 model 都支援，換 model 前先確認

## 練習

1. 把 `auto` 範例的 system prompt 拿掉，看 Claude 對「天空是什麼顏色」這類問題會不會開始亂呼叫 `web_search`。
2. 在強制 `print_sentiment_scores` 的 `tool_choice` 裡加上 `disable_parallel_tool_use=True`，重跑數學味的推文，確認只剩一次 tool 呼叫。
3. 在 `any` 的簡訊助理再加第三個 tool（例如 `check_order_status`），設計幾則訊息，觀察 Claude 怎麼挑。
