---
translated: true
source: extended_thinking/extended_thinking_with_tool_use.ipynb
---

# Extended thinking 搭配 tool use

> 原文：[extended_thinking/extended_thinking_with_tool_use.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/extended_thinking/extended_thinking_with_tool_use.ipynb)

把 extended thinking 和 tool 結合，在多步驟流程中讓推理過程透明可見。

## 這篇在做什麼

示範在 Claude Sonnet 5.5 上同時使用 extended thinking 和 tool：先做單一 tool 呼叫，再做多個 tool 呼叫，最後講在多輪中如何正確保留 thinking block。

## 學完你會

- 設定 adaptive thinking 並搭配 tool 呼叫，讀出 Claude 決定用哪個 tool 的思考。
- 處理多個 tool 呼叫，包含 tool 之間的 interleaved thinking。
- 把 `thinking` 和 `redacted_thinking` block 連同 signature 原樣傳回去。

## 開跑前

需要 Anthropic API key。

## 目錄
- [設定](#setup)
- [基本範例](#basic-example)
- [多個 tool 呼叫](#multiple-tool-calls-with-thinking)
- [保留 thinking block](#preserving-thinking-blocks)

這份 notebook 示範如何在 Claude Sonnet 5.5 上搭配 tool 使用 Claude 的 extended thinking 功能。Extended thinking 讓你在 Claude 給出最終答案之前，看到它一步步的思考，了解它怎麼決定要用哪個 tool、怎麼解讀 tool 的結果。

在 Claude Sonnet 5.5 上，thinking 是 adaptive 的（`thinking={"type": "adaptive"}`，用 `output_config={"effort": ...}` 控制思考的力度），模型可能在第一次 tool 請求之前先思考，讀完 tool 結果後在 tool 呼叫之間再思考一次（interleaved thinking）。這個功能不需要 beta header。Thinking block 帶有 signature，並綁定到目前為止的對話，所以先前的 assistant 內容（包括 `thinking` 和 `redacted_thinking` block）在每次後續請求都必須原封不動傳回去。更多 extended thinking 的資訊，見我們的[文件](https://platform.claude.com/docs/en/build-with-claude/thinking)。

## 設定

先安裝需要的套件並設定環境。

```python
%pip install anthropic
```

```python
import json

import anthropic

# Global variables for model, output limit, and thinking effort
MODEL_NAME = "claude-sonnet-5-5"
MAX_TOKENS = 16000  # thinking tokens count toward max_tokens, so leave headroom
EFFORT = "xhigh"  # how hard Claude thinks: low | medium | high (default) | xhigh | max.
# Adaptive thinking may skip thinking entirely on easy requests at lower effort; "xhigh"
# makes these small examples reliably produce thinking blocks you can inspect.

# Every request below passes thinking={"type": "adaptive", "display": "summarized"}.
# "display" defaults to "omitted" on this model, which returns thinking blocks with
# empty text; "summarized" returns a summary of the reasoning so we can print it.

# Set your API key as an environment variable or directly
# os.environ["ANTHROPIC_API_KEY"] = "your_api_key_here"

# Initialize the client
client = anthropic.Anthropic()


# Helper functions
def print_thinking_response(response):
    """Pretty print a message response with thinking blocks."""
    print("\n==== FULL RESPONSE ====")
    for block in response.content:
        if block.type == "thinking":
            print("\n🧠 THINKING BLOCK:")
            # Show truncated thinking for readability
            print(block.thinking[:500] + "..." if len(block.thinking) > 500 else block.thinking)
            print(f"\n[Signature available: {bool(getattr(block, 'signature', None))}]")
            if hasattr(block, "signature") and block.signature:
                print(f"[Signature (first 50 chars): {block.signature[:50]}...]")
        elif block.type == "redacted_thinking":
            print("\n🔒 REDACTED THINKING BLOCK:")
            print(f"[Data length: {len(block.data) if hasattr(block, 'data') else 'N/A'}]")
        elif block.type == "text":
            print("\n✓ FINAL ANSWER:")
            print(block.text)

    print("\n==== END RESPONSE ====")


def count_tokens(messages, tools=None):
    """Count tokens for a given message list with optional tools."""
    if tools:
        response = client.messages.count_tokens(model=MODEL_NAME, messages=messages, tools=tools)
    else:
        response = client.messages.count_tokens(model=MODEL_NAME, messages=messages)
    return response.input_tokens
```

## 單一 tool 呼叫搭配 thinking

這個範例示範如何結合 thinking 並做一次 tool 呼叫，用的是一個模擬的天氣 tool。

```python
def tool_use_with_thinking():
    # Define a weather tool
    tools = [
        {
            "name": "weather",
            "description": "Get current weather information for a location.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The location to get weather for.",
                    }
                },
                "required": ["location"],
            },
        }
    ]

    def weather(location):
        # Mock weather data, keyed by bare city name (the model may pass "Paris, FR")
        location = location.split(",")[0].strip()
        weather_data = {
            "New York": {"temperature": 72, "condition": "Sunny"},
            "London": {"temperature": 62, "condition": "Cloudy"},
            "Tokyo": {"temperature": 80, "condition": "Partly cloudy"},
            "Paris": {"temperature": 65, "condition": "Rainy"},
            "Sydney": {"temperature": 85, "condition": "Clear"},
            "Berlin": {"temperature": 60, "condition": "Foggy"},
        }

        return weather_data.get(location, {"error": f"No weather data available for {location}"})

    # A bare "what's the weather in Paris?" usually goes straight to the tool call with no
    # thinking. Giving Claude a small decision that depends on the result makes it reason first.
    user_message = {
        "role": "user",
        "content": "I'm hosting an outdoor dinner in Paris this evening and deciding whether to move it indoors. Work out what you need to check, use the tool, then give me a recommendation with your reasoning.",
    }

    # Initial request with tool use and thinking
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": EFFORT},
        tools=tools,
        messages=[user_message],
    )

    # Detailed diagnostic output of initial response
    print("\n=== INITIAL RESPONSE ===")
    print(f"Response ID: {response.id}")
    print(f"Stop reason: {response.stop_reason}")
    print(f"Model: {response.model}")
    print(f"Content blocks: {len(response.content)} blocks")

    for i, block in enumerate(response.content):
        print(f"\nBlock {i + 1}: Type = {block.type}")
        if block.type == "thinking":
            print(f"Thinking content: {block.thinking[:150]}...")
            print(f"Signature available: {bool(getattr(block, 'signature', None))}")
        elif block.type == "text":
            print(f"Text content: {block.text}")
        elif block.type == "tool_use":
            print(f"Tool: {block.name}")
            print(f"Tool input: {block.input}")
            print(f"Tool ID: {block.id}")
    print("=== END INITIAL RESPONSE ===\n")

    # Handle tool use until Claude gives its final answer
    full_conversation = [user_message]

    while response.stop_reason == "tool_use":
        # Keep the whole assistant turn (thinking, redacted_thinking, text and tool_use blocks,
        # in order) for the conversation history. Thinking blocks are signed and bound to the
        # conversation prefix, so pass the turn back exactly as received.
        full_conversation.append({"role": "assistant", "content": response.content})

        # Execute every tool_use block in this turn and answer each one
        tool_results = []
        for tool_use_block in (b for b in response.content if b.type == "tool_use"):
            print("\n=== EXECUTING TOOL ===")
            print(f"Tool name: {tool_use_block.name}")
            print(f"Location to check: {tool_use_block.input['location']}")
            tool_result = weather(tool_use_block.input["location"])
            print(f"Result: {tool_result}")
            print("=== TOOL EXECUTION COMPLETE ===\n")
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": json.dumps(tool_result),
                }
            )

        # Add the tool results to the conversation in a single user turn
        full_conversation.append({"role": "user", "content": tool_results})

        # Continue the conversation with the same thinking configuration
        print("\n=== SENDING FOLLOW-UP REQUEST WITH TOOL RESULT ===")
        response = client.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": EFFORT},
            tools=tools,
            messages=full_conversation,
        )
        print(f"Follow-up response received. Stop reason: {response.stop_reason}")

    print_thinking_response(response)


# Run the example
tool_use_with_thinking()
```

??? note "輸出"

    ```text

    === INITIAL RESPONSE ===
    Response ID: msg_011Cfdj5KspNpopEXyAhbhct
    Stop reason: tool_use
    Model: claude-sonnet-5-5
    Content blocks: 3 blocks

    Block 1: Type = thinking
    Thinking content: I need to check the weather in Paris, so I'll call the weather tool for that.

    ...
    Signature available: True

    Block 2: Type = text
    Text content: I need to check Paris's current conditions and anything that affects this evening, such as rain, temperature, wind, and how the weather is trending. I'll pull the weather now.

    Block 3: Type = tool_use
    Tool: weather
    Tool input: {'location': 'Paris, France'}
    Tool ID: toolu_014FismJG9gGgQfUSw9WVjGs
    === END INITIAL RESPONSE ===


    === EXECUTING TOOL ===
    Tool name: weather
    Location to check: Paris, France
    Result: {'temperature': 65, 'condition': 'Rainy'}
    === TOOL EXECUTION COMPLETE ===


    === SENDING FOLLOW-UP REQUEST WITH TOOL RESULT ===
    Follow-up response received. Stop reason: end_turn

    ==== FULL RESPONSE ====

    🧠 THINKING BLOCK:
    The data I got back is pretty sparse—just 65°F and rainy, no forecast details or timing. I'll be upfront about those limits while still giving a practical recommendation, like suggesting a covered or indoor option as a safe bet given the current rain.



    ... (省略 26 行)
    ```

## 多個 tool 呼叫搭配 thinking

這個範例示範如何處理多個 tool 呼叫（例如模擬的新聞和天氣服務），同時觀察思考過程。

```python
def multiple_tool_calls_with_thinking():
    # Define tools
    tools = [
        {
            "name": "weather",
            "description": "Get current weather information for a location.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The location to get weather for.",
                    }
                },
                "required": ["location"],
            },
        },
        {
            "name": "news",
            "description": "Get latest news headlines for a topic.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to get news about."}
                },
                "required": ["topic"],
            },
        },
    ]

    def weather(location):
        # Mock weather data, keyed by bare city name (the model may pass "Paris, FR")
        location = location.split(",")[0].strip()
        weather_data = {
            "New York": {"temperature": 72, "condition": "Sunny"},
            "London": {"temperature": 62, "condition": "Cloudy"},
            "Tokyo": {"temperature": 80, "condition": "Partly cloudy"},
            "Paris": {"temperature": 65, "condition": "Rainy"},
            "Sydney": {"temperature": 85, "condition": "Clear"},
            "Berlin": {"temperature": 60, "condition": "Foggy"},
        }

        return weather_data.get(location, {"error": f"No weather data available for {location}"})

    def news(topic):
        # Mock news data
        news_data = {
            "technology": [
                "New AI breakthrough announced by research lab",
                "Tech company releases latest smartphone model",
                "Quantum computing reaches milestone achievement",
            ],
            "sports": [
                "Local team wins championship game",
                "Star player signs record-breaking contract",
                "Olympic committee announces host city for 2036",
            ],
            "weather": [
                "Storm system developing in the Atlantic",
                "Record temperatures recorded across Europe",
                "Climate scientists release new research findings",
            ],
        }

        # Loose matching so "London tech" or "technology news" resolve to a category
        topic = topic.lower()
        for key, headlines in news_data.items():
            if key in topic or (key == "technology" and "tech" in topic):
                return {"headlines": headlines}
        return {"headlines": ["No news available for this topic"]}

    # Initial request
    response = client.messages.create(
        model=MODEL_NAME,
        max_tokens=MAX_TOKENS,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": EFFORT},
        tools=tools,
        messages=[
            {
                "role": "user",
                "content": "I run an outdoor tech meetup in London tomorrow evening and I'm deciding whether to move it indoors and what to open the talk with. Work out which of your tools you need and in what order, use them, then give me a recommendation with your reasoning.",
            }
        ],
    )

    # Print detailed information about initial response
    print("\n=== INITIAL RESPONSE ===")
    print(f"Response ID: {response.id}")
    print(f"Stop reason: {response.stop_reason}")
    print(f"Model: {response.model}")
    print(f"Content blocks: {len(response.content)} blocks")

    # Print each content block
    for i, block in enumerate(response.content):
        print(f"\nBlock {i + 1}: Type = {block.type}")
        if block.type == "thinking":
            print(f"Thinking content: {block.thinking[:150]}...")
            print(f"Signature available: {bool(getattr(block, 'signature', None))}")
        elif block.type == "text":
            print(f"Text content: {block.text}")
        elif block.type == "tool_use":
            print(f"Tool: {block.name}")
            print(f"Tool input: {block.input}")
            print(f"Tool ID: {block.id}")
    print("=== END INITIAL RESPONSE ===\n")

    # Handle potentially multiple tool calls
    full_conversation = [
        {
            "role": "user",
            "content": "I run an outdoor tech meetup in London tomorrow evening and I'm deciding whether to move it indoors and what to open the talk with. Work out which of your tools you need and in what order, use them, then give me a recommendation with your reasoning.",
        }
    ]

    # Track iteration count for multi-turn tool use
    iteration = 0

    while response.stop_reason == "tool_use":
        iteration += 1
        print(f"\n=== TOOL USE ITERATION {iteration} ===")

        # Keep the whole assistant turn (thinking, text and tool_use blocks, in order)
        # for the conversation history; pass it back exactly as received
        assistant_blocks = response.content

        # Add assistant response with thinking blocks and tool use
        full_conversation.append({"role": "assistant", "content": assistant_blocks})

        # Run every tool_use block in this turn (Claude may call several tools in parallel)
        tool_use_blocks = [block for block in response.content if block.type == "tool_use"]
        if tool_use_blocks:
            tool_results = []
            for tool_use_block in tool_use_blocks:
                print("\n=== EXECUTING TOOL ===")
                print(f"Tool name: {tool_use_block.name}")

                # Execute the appropriate tool
                if tool_use_block.name == "weather":
                    print(f"Location to check: {tool_use_block.input['location']}")
                    tool_result = weather(tool_use_block.input["location"])
                elif tool_use_block.name == "news":
                    print(f"Topic to check: {tool_use_block.input['topic']}")
                    tool_result = news(tool_use_block.input["topic"])
                else:
                    tool_result = {"error": "Unknown tool"}

                print(f"Result: {tool_result}")
                print("=== TOOL EXECUTION COMPLETE ===\n")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_block.id,
                        "content": json.dumps(tool_result),
                    }
                )

            # Add all tool results to the conversation in a single user turn
            full_conversation.append({"role": "user", "content": tool_results})

            # Continue the conversation
            print("\n=== SENDING FOLLOW-UP REQUEST WITH TOOL RESULT ===")
            response = client.messages.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive", "display": "summarized"},
                output_config={"effort": EFFORT},
                tools=tools,
                messages=full_conversation,
            )

            # Print follow-up response details
            print(f"\n=== FOLLOW-UP RESPONSE (ITERATION {iteration}) ===")
            print(f"Response ID: {response.id}")
            print(f"Stop reason: {response.stop_reason}")
            print(f"Content blocks: {len(response.content)} blocks")

            for i, block in enumerate(response.content):
                print(f"\nBlock {i + 1}: Type = {block.type}")
                if block.type == "thinking":
                    print(f"Thinking content preview: {block.thinking[:100]}...")
                elif block.type == "text":
                    print(f"Text content preview: {block.text[:100]}...")
                elif block.type == "tool_use":
                    print(f"Tool: {block.name}")
                    print(f"Tool input preview: {str(block.input)[:100]}")
            print(f"=== END FOLLOW-UP RESPONSE (ITERATION {iteration}) ===\n")

            if response.stop_reason != "tool_use":
                print("\n=== FINAL RESPONSE ===")
                print_thinking_response(response)
                print("=== END FINAL RESPONSE ===")
        else:
            print("No tool_use block found in response.")
            break


# Run the example
multiple_tool_calls_with_thinking()
```

??? note "輸出"

    ```text

    === INITIAL RESPONSE ===
    Response ID: msg_011Cfdj62iENiRCj8mRZbo5x
    Stop reason: tool_use
    Model: claude-sonnet-5-5
    Content blocks: 4 blocks

    Block 1: Type = thinking
    Thinking content: London weather and outdoor tech news are unrelated requests, so I can fetch both at once.

    ...
    Signature available: True

    Block 2: Type = text
    Text content: I'll check two things: the London weather, which decides indoors or outdoors, and current outdoor tech news, which could give you an opening for the talk. Neither depends on the other, so I'll run both now.

    Block 3: Type = tool_use
    Tool: weather
    Tool input: {'location': 'London'}
    Tool ID: toolu_016w2JwNyoLzMzEVbLpH62xJ

    Block 4: Type = tool_use
    Tool: news
    Tool input: {'topic': 'outdoor tech'}
    Tool ID: toolu_01VbrLTn6hoqbSCzFdsJSTYm
    === END INITIAL RESPONSE ===


    === TOOL USE ITERATION 1 ===

    === EXECUTING TOOL ===
    Tool name: weather
    Location to check: London
    Result: {'temperature': 62, 'condition': 'Cloudy'}
    === TOOL EXECUTION COMPLETE ===


    === EXECUTING TOOL ===
    Tool name: news
    Topic to check: outdoor tech
    ... (省略 60 行)
    ```

## 保留 thinking block

搭配 tool 使用 extended thinking 時，請確保：

1. **原封不動傳回 thinking block，連同 signature。** 每個 `thinking` block 帶有一個針對完整（未摘要）推理內容的加密 `signature`。送出 tool 結果時，要把前一個 assistant 回合完全照收到的樣子放進去：`thinking` / `redacted_thinking` / `text` / `tool_use` block，順序也要一致。signature 驗證不過的 block 會被 400 拒絕。

2. **不要編輯先前的回合。** 在 Claude Sonnet 5.5 上，thinking block 還會綁定到產生它的對話前綴（system prompt、`tools` 陣列，以及先前每則訊息）。如果你改了其中任何一項再重播 thinking block，這個 block 就跟對話對不上了。2026 年 8 月 31 日（含）之後建立的帳號預設會收到 400；舊帳號可以加上 `thinking-binding-controls-2026-08-01` beta header，並把 `thinking.block_binding.prefix_mismatch_behavior` 設成 `"error"`（拒絕請求）或 `"drop_block"`（丟掉過期的 block 並在 `input_transformations` 回報）。下面的範例用了這個 beta header，讓任何帳號行為一致。

3. **也不要默默丟掉它們。** 重播的回合裡省略 thinking block，API 會接受，但 Claude 會在沒有 tool 呼叫前那段推理的情況下繼續任務。請保留它們。

4. **同時處理 `thinking` 和 `redacted_thinking` block。** 兩者都必須保留在對話歷史裡，即使 redacted block 的內容人讀不懂。

沒有 tool 的 extended thinking 詳情，見主要的「Extended Thinking」notebook。

```python
def thinking_block_preservation_example():
    # Define a simple weather tool
    tools = [
        {
            "name": "weather",
            "description": "Get current weather information for a location.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The location to get weather for.",
                    }
                },
                "required": ["location"],
            },
        }
    ]

    def weather(location):
        # Mock weather data, keyed by bare city name (the model may pass "Paris, FR")
        location = location.split(",")[0].strip()
        weather_data = {
            "New York": {"temperature": 72, "condition": "Sunny"},
            "London": {"temperature": 62, "condition": "Cloudy"},
            "Tokyo": {"temperature": 80, "condition": "Partly cloudy"},
            "Paris": {"temperature": 65, "condition": "Rainy"},
            "Sydney": {"temperature": 85, "condition": "Clear"},
            "Berlin": {"temperature": 60, "condition": "Foggy"},
        }

        return weather_data.get(location, {"error": f"No weather data available for {location}"})

    question = "I'm about to cycle across Berlin to a meeting I can't be late for. Work out what you need to check, use the tool, then tell me whether to leave extra time and why."

    # Opt in to strict prefix binding so this demo behaves the same on every account
    # (accounts created on or after 2026-08-31 get this behavior by default).
    betas = ["thinking-binding-controls-2026-08-01"]
    strict_thinking = {
        "type": "adaptive",
        "display": "summarized",
        "block_binding": {"prefix_mismatch_behavior": "error"},
    }

    # Initial request with tool use and thinking. Adaptive thinking occasionally skips
    # thinking even here, so retry a couple of times until we have a thinking block to work with.
    for _ in range(3):
        response = client.beta.messages.create(
            model=MODEL_NAME,
            max_tokens=MAX_TOKENS,
            thinking=strict_thinking,
            output_config={"effort": EFFORT},
            tools=tools,
            betas=betas,
            messages=[{"role": "user", "content": question}],
        )
        thinking_blocks = [b for b in response.content if b.type == "thinking"]
        tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
        if thinking_blocks and tool_use_blocks:
            break

    print("\n=== INITIAL RESPONSE ===")
    print("Response contains:")
    print(f"- {len(thinking_blocks)} thinking blocks")
    print(f"- {len(tool_use_blocks)} tool use blocks")

    if not (thinking_blocks and tool_use_blocks):
        print("\nClaude answered without a thinking block or without calling the tool this time;")
        print("re-run the cell to see the preservation checks below.")
        return

    tool_block = tool_use_blocks[0]
    print(f"\nTool called: {tool_block.name}")
    print(f"Location to check: {tool_block.input['location']}")

    # Execute the tool
    tool_result = weather(tool_block.input["location"])
    print(f"Tool result: {tool_result}")
    tool_result_turn = {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_block.id,
                "content": json.dumps(tool_result),
            }
        ],
    }

    def follow_up(label, messages, thinking=strict_thinking):
        try:
            result = client.beta.messages.create(
                model=MODEL_NAME,
                max_tokens=MAX_TOKENS,
                thinking=thinking,
                output_config={"effort": EFFORT},
                tools=tools,
                betas=betas,
                messages=messages,
            )
            print(f"SUCCESS ({label}): stop_reason={result.stop_reason}")
            return result
        except anthropic.BadRequestError as e:
            print(f"ERROR ({label}): {e}")
            return None

    # TEST 1: tamper with the thinking block's signature -> rejected
    print("\n=== TEST 1: modified signature ===")
    tampered_turn = []
    for block in response.content:
        block_dict = block.model_dump()
        if block_dict["type"] == "thinking":
            block_dict["signature"] = block_dict["signature"][:-4] + "AAAA"
        tampered_turn.append(block_dict)
    follow_up(
        "tampered signature",
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": tampered_turn},
            tool_result_turn,
        ],
    )
    print("Thinking blocks must be passed back byte-for-byte, signature included.")

    # TEST 2: replay the thinking block unchanged but edit the earlier user message.
    # The block is bound to the original prefix, so with prefix_mismatch_behavior="error"
    # the request is rejected...
    print("\n=== TEST 2: edited earlier turn, prefix_mismatch_behavior='error' ===")
    edited_history = [
        {"role": "user", "content": question + " Thanks!"},  # <- not what Claude saw
        {"role": "assistant", "content": response.content},
        tool_result_turn,
    ]
    follow_up("edited prefix", edited_history)

    # ...and with "drop_block" the API drops the stale thinking block, tells you it did so
    # in input_transformations, and Claude continues without that reasoning.
    print("\n=== TEST 3: edited earlier turn, prefix_mismatch_behavior='drop_block' ===")
    lenient = {**strict_thinking, "block_binding": {"prefix_mismatch_behavior": "drop_block"}}
    dropped = follow_up("edited prefix, drop_block", edited_history, thinking=lenient)
    if dropped is not None:
        print(f"input_transformations: {dropped.to_dict().get('input_transformations')}")

    # TEST 4: the correct approach - every block from the first response, in order, unchanged,
    # on top of an unchanged prefix.
    print("\n=== TEST 4: WITH thinking block, unchanged history (correct approach) ===")
    complete_response = follow_up(
        "full replay",
        [
            {"role": "user", "content": question},
            {"role": "assistant", "content": response.content},
            tool_result_turn,
        ],
    )
    if complete_response is not None:
        second_thinking = [b for b in complete_response.content if b.type == "thinking"]
        second_text = [b for b in complete_response.content if b.type == "text"]
        print("\nSecond response contains:")
        print(f"- {len(second_thinking)} thinking blocks")
        print(f"- {len(second_text)} text blocks")
        if second_text:
            print(f"\nFinal answer: {second_text[0].text}")
        print(
            "\nNote: with adaptive thinking Claude may or may not think again after a tool result,"
        )
        print(
            "so the second response can contain thinking blocks. Either way, pass every earlier block back unchanged."
        )


# Run the example
thinking_block_preservation_example()
```

??? note "輸出"

    ```text

    === INITIAL RESPONSE ===
    Response contains:
    - 1 thinking blocks
    - 1 tool use blocks

    Tool called: weather
    Location to check: Berlin
    Tool result: {'temperature': 60, 'condition': 'Foggy'}

    === TEST 1: modified signature ===
    ERROR (tampered signature): Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'messages.1.content.0: Invalid `signature` in `thinking` block'}, 'request_id': 'req_011Cfdj789gkiDGRiGuVqr8n'}
    Thinking blocks must be passed back byte-for-byte, signature included.

    === TEST 2: edited earlier turn, prefix_mismatch_behavior='error' ===
    ERROR (edited prefix): Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'messages.1.content.0: Invalid `signature` in `thinking` block. The block is bound to a different conversation. Remove the block, or set `thinking.block_binding.prefix_mismatch_behavior` to "drop_block". Content before this block differs from when it was created, first at `messages.0.content.0`.'}, 'request_id': 'req_011Cfdj78tLJjd4YRHAKCFck'}

    === TEST 3: edited earlier turn, prefix_mismatch_behavior='drop_block' ===
    SUCCESS (edited prefix, drop_block): stop_reason=end_turn
    input_transformations: [{'type': 'thinking_dropped', 'path': 'messages.1.content.0', 'reason': 'prefix_binding_mismatch'}]

    === TEST 4: WITH thinking block, unchanged history (correct approach) ===
    SUCCESS (full replay): stop_reason=end_turn

    Second response contains:
    - 1 thinking blocks
    - 1 text blocks

    Final answer: **Yes, leave extra time. I'd add about 10–15 minutes, or more if your route is long or goes through busy areas.**

    The tool reports Berlin as **foggy at 60 degrees**. It gave no unit, but 60 is only a plausible temperature in °F, which is about 16°C. That's mild, so cold isn't the problem.

    **Why the fog matters**
    - **Visibility:** You'll see junctions, tram tracks, turning vehicles and pedestrians later, and drivers will see you later too. You'll probably ride more slowly and cautiously, especially on shared roads and at crossings.
    - **Damp surfaces:** Fog often leaves roads, cobbles, tram rails and painted road markings slick. Berlin has plenty of all of these, so braking and cornering need more care.
    - **Delays at junctions:** Slower traffic and more cautious road users tend to add stops and waiting time across a whole cross-city ride.

    **What I couldn't check**
    - The report had no wind, rain or forecast data, so I can't say whether conditions will improve or get worse during your ride.
    - I only have a city-wide reading. Fog can be thicker near the Spree, parks or open areas like Tempelhofer Feld.
    ... (省略 11 行)
    ```

## 結論

這份 notebook 示範如何結合 Claude 的 extended thinking 和 tool use。主要好處包括：

1. 使用 tool 時能看到 Claude 的思考過程
2. 看到 Claude 如何決定用 tool 還是用內部知識
3. 更了解涉及多個 tool 呼叫的多步驟任務
4. 了解 Claude 如何解讀 tool 結果並整合進回應

搭配 tool 使用 extended thinking 時，請記得：
- 選符合任務的 `effort` 等級（預設 `"high"`；`"low"` 和 `"medium"` 用深度換速度和成本，`"xhigh"` 和 `"max"` 留給最難的問題）。目前的模型沒有 token budget
- 想讀思考內容就設 `"display": "summarized"`；預設值（`"omitted"`）會回傳空的 thinking 文字
- 傳回 tool 結果時一定要保留 thinking block 和它們的 signature
- 對話歷史裡要同時包含一般和 redacted 的 thinking block
- 確保每次呼叫之間 system prompt、tool 和 thinking 設定一致
- Claude 可能在 tool 呼叫之間再度思考（interleaved thinking），所以任何 assistant 回合裡的 `thinking` block 都要處理，並全部原樣傳回
- 同時用 tool 和 thinking 可能增加 token 用量和回應時間

## 重點整理
- Extended thinking 搭配 tool 能讓你看到 Claude 為什麼選某個 tool、怎麼解讀結果。
- Sonnet 5.5 用 adaptive thinking，`effort` 控制思考力度，可以在 tool 呼叫之間再思考。
- Thinking block 帶 signature 且綁定對話前綴，tool 結果回傳時必須原樣傳回整個 assistant 回合。
- 中途改 system prompt、tools 或先前訊息，會讓重播的 thinking block 失效。
- 預設不回傳思考文字，要讀的話設 `"display": "summarized"`。

## 練習
1. 把 `effort` 從預設改成 `"low"`，比較思考內容和回應速度。
2. 設 `"display": "summarized"` 並印出 thinking block，觀察模型在 tool 呼叫前後各想了什麼。
3. 故意在回傳 tool 結果時丟掉 thinking block，比較最終答案有什麼差別。
