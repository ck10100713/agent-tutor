---
translated: true
source: extended_thinking/extended_thinking.ipynb
---

# Extended thinking

> 原文：[extended_thinking/extended_thinking.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/extended_thinking/extended_thinking.ipynb)

用 Claude 的 extended thinking 取得透明的逐步推理，並管理思考的力度。

## 這篇在做什麼

在 Claude Sonnet 5.5 上示範 extended thinking：基本用法、streaming、token 計算與 `effort` 的影響、redacted thinking，以及常見的錯誤情況。

## 學完你會

- 用 adaptive thinking 搭配 `effort` 和 `display` 設定，取得思考摘要。
- 在 streaming 中處理 thinking 內容。
- 知道 thinking token 怎麼計費、什麼設定會被拒絕（budget_tokens、非預設 temperature 等）。

## 開跑前

需要 Anthropic API key。

## 目錄
- [設定](#setup)
- [基本範例](#basic-example)
- [搭配 streaming 的 extended thinking](#streaming-with-extended-thinking)
- [Token 計算與 context window 管理](#token-counting-and-context-window-management)
- [了解 redacted thinking](#understanding-redacted-thinking-blocks)
- [處理錯誤情況](#handling-error-cases)

這份 notebook 示範如何在 Claude Sonnet 5.5 上使用 Claude 的 extended thinking 功能，包含各種範例和邊界情況。

Extended thinking 讓 Claude 在複雜任務上有更強的推理能力，同時在給出最終答案之前，讓你看到它逐步的思考過程。開啟 extended thinking 後，Claude 會建立 `thinking` content block，在裡面輸出內部推理。Claude 會把這些推理的洞見納入，再寫出最終回應。

在 Claude Sonnet 5.5 上，thinking 是 **adaptive** 的：你傳 `thinking={"type": "adaptive"}`（省略 `thinking` 時也是預設值），模型會依每個請求決定要想多少。你用 `output_config={"effort": ...}`（`"low"`、`"medium"`、`"high"`、`"xhigh"` 或 `"max"`，預設 `"high"`）來控制思考力度，而不是用 token budget。舊的 `{"type": "enabled", "budget_tokens": N}` 形式在這個模型上不被接受。更多 extended thinking 的資訊，見我們的[文件](https://platform.claude.com/docs/en/build-with-claude/thinking)。

## 設定

先安裝需要的套件並設定環境。

```python
%pip install anthropic
```

```python
import anthropic

# Set your API key as an environment variable or directly
# os.environ["ANTHROPIC_API_KEY"] = "your-api-key-here"

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


def count_tokens(messages):
    """Count tokens for a given message list."""
    result = client.messages.count_tokens(model="claude-sonnet-5-5", messages=messages)
    return result.input_tokens
```

## 基本範例

先從基本範例開始，看 extended thinking 的實際效果。

開始前有一個細節要注意：在 Claude Sonnet 5.5 上，thinking 的 `display` 設定預設是 `"omitted"`，會回傳文字為空的 `thinking` block（仍然會有 signature，thinking token 也照樣計費）。因為這份 notebook 要印出推理內容，每個請求都設了 `"display": "summarized"`，讓 API 回傳 Claude 思考的摘要。

Adaptive 也代表 Claude 可以判斷某個 prompt 完全不需要思考，這時回應就不會有 `thinking` block。簡單的 prompt 和較低的 `effort` 最容易發生。下面的範例用一個小型的限制滿足問題搭配 `"effort": "xhigh"`，讓你穩定看到思考；後面的 token 計算段落會示範把 `effort` 從 `"low"` 調到 `"xhigh"` 時，思考量怎麼變化。

```python
def basic_thinking_example():
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=16000,  # thinking tokens count toward max_tokens, so leave headroom
        thinking={
            "type": "adaptive",
            "display": "summarized",  # default is "omitted" (empty thinking text)
        },
        output_config={"effort": "xhigh"},  # low | medium | high (default) | xhigh | max
        messages=[
            {
                "role": "user",
                "content": "Five talks (A, B, C, D, E) must be scheduled in five consecutive slots. Constraints: A comes before C; B is not adjacent to D; E is neither first nor last; C is immediately before or after E; D comes before A. List every valid ordering and explain how you know there are no others.",
            }
        ],
    )

    print_thinking_response(response)


basic_thinking_example()
```

??? note "輸出"

    ```text

    ==== FULL RESPONSE ====

    🧠 THINKING BLOCK:
    I'm working through the constraints: D must come before A, which comes before C, E must sit adjacent to C and be in positions 2-4, and B can't be next to D. I'm now systematically trying placements of D to narrow down valid orderings.

    Checking the other two candidates confirms all constraints hold: D before A, A before C, C adjacent E, and no B next to D. So the three valid orderings are DABEC, DAECB, and DACEB.



    [Signature available: True]
    [Signature (first 50 chars): CAQS8RIKEAgSGAI4AUIIdGhpbmtpbmcSDC9PApxA+kqk+axotR...]

    ✓ FINAL ANSWER:
    **Valid orderings (slots 1→5):**

    1. D A B E C
    2. D A E C B
    3. D A C E B

    **Why there are no others**

    1. Combining "D before A" and "A before C" gives the chain D < A < C.
    2. E must be next to C, so E is either immediately before C (block "EC") or immediately after C (block "CE"). A cannot be E, so in either case A comes before the whole block. That leaves D, A, [block] in that fixed order, with B free to go in any of 4 places: before D, between D and A, between A and the block, or after the block.

    **Case 1: block EC.** The four placements of B give:
    - B D A E C: B is next to D, so this is invalid.
    - D B A E C: B is next to D, so this is invalid.
    - D A B E C: valid. E is in slot 4, and B (slot 3) is not next to D (slot 1).
    - D A E C B: valid. E is in slot 3, and B (slot 5) is not next to D (slot 1).

    **Case 2: block CE.** The four placements of B give:
    - B D A C E: E is last, so this is invalid.
    - D B A C E: E is last, so this is invalid.
    - D A B C E: E is last, so this is invalid.
    - D A C E B: valid. E is in slot 4, and B (slot 5) is not next to D (slot 1).

    Every arrangement satisfying the ordering and adjacency constraints appears among these 8 candidates, and only 3 survive the "B not adjacent to D" and "E not first or last" constraints. So the three orderings above are the only valid ones.

    ==== END RESPONSE ====
    ```

## 搭配 streaming 的 extended thinking

這個範例示範如何處理 thinking 的 streaming：

```python
def streaming_with_thinking():
    with client.messages.stream(
        model="claude-sonnet-5-5",
        max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "xhigh"},
        messages=[
            {
                "role": "user",
                "content": "Five talks (A, B, C, D, E) must be scheduled in five consecutive slots. Constraints: A comes before C; B is not adjacent to D; E is neither first nor last; C is immediately before or after E; D comes before A. List every valid ordering and explain how you know there are no others.",
            }
        ],
    ) as stream:
        # Track what we're currently building
        current_block_type = None
        current_content = ""

        for event in stream:
            if event.type == "content_block_start":
                current_block_type = event.content_block.type
                print(f"\n--- Starting {current_block_type} block ---")
                current_content = ""

            elif event.type == "content_block_delta":
                if event.delta.type == "thinking_delta":
                    print(
                        event.delta.thinking, end="", flush=True
                    )  # Just print dots for thinking to avoid clutter
                    current_content += event.delta.thinking
                elif event.delta.type == "text_delta":
                    print(event.delta.text, end="", flush=True)
                    current_content += event.delta.text

            elif event.type == "content_block_stop":
                if current_block_type == "thinking":
                    # Just show a summary for thinking
                    print(f"\n[Completed thinking block, {len(current_content)} characters]")
                elif current_block_type == "redacted_thinking":
                    print("\n[Redacted thinking block]")
                print(f"--- Finished {current_block_type} block ---\n")
                current_block_type = None

            elif event.type == "message_stop":
                print("\n--- Message complete ---")


streaming_with_thinking()
```

??? note "輸出"

    ```text

    --- Starting thinking block ---
    I need to work through the constraints: D before A before C, E adjacent to C, and B not adjacent to D. I'm trying to build the ordering by placing D, A, C first then inserting E next to C and checking where B can go without violating the adjacency rule with D.

    Testing "D A C E B" works since D and B aren't adjacent and E sits at position 4, not the ends. Now I'm checking the other case where E comes immediately before C, inserting B in each of the four gaps and verifying the adjacency and positional rules each time.

    After going through DBAEC, DABEC, and DAECB, I find that DABEC and DAECB both satisfy every condition while DBAEC fails because B ends up next to D. Combined with the earlier valid case, that gives three total valid orderings: DACEB, DABEC, and DAECB.


    [Completed thinking block, 777 characters]
    --- Finished thinking block ---


    --- Starting text block ---
    **Valid orderings (3):**

    1. D A C E B
    2. D A B E C
    3. D A E C B

    **Why there are no others**

    1. **Chain.** "D before A" and "A before C" force the relative order D < A < C.

    2. **Treat C and E as a block.** E must be immediately before or after C, so C and E form a two-letter block, either "CE" or "EC". The remaining pieces are D, A, the block, and B. D, A and the block must appear in that order, since the block contains C. B can go in any of 4 places: before D, between D and A, between A and the block, or after the block. That gives 4 candidates for each block orientation, 8 in total.

    3. **Block "CE"** (the order is D, A, CE, with B inserted):
       - B D A C E: E is last, so it is invalid.
       - D B A C E: E is last, so it is invalid.
       - D A B C E: E is last, so it is invalid.
       - **D A C E B:** E is 4th, and B (5th) is not next to D (1st). Valid.

    4. **Block "EC"** (the order is D, A, EC, with B inserted):
       - B D A E C: B and D are adjacent, so it is invalid.
       - D B A E C: B and D are adjacent, so it is invalid.
       - **D A B E C:** B is 3rd and D is 1st, so they are not adjacent. E is 4th. Valid.
       - **D A E C B:** E is 3rd, and B (5th) is not next to D (1st). Valid.

    5. **Completeness.** Every ordering satisfying the "D < A < C" and "C adjacent to E" constraints appears among those 8 candidates. The "E not first or last" and "B not adjacent to D" constraints eliminate exactly 5 of them, leaving the three above.--- Finished text block ---

    ... (省略 2 行)
    ```

## Token 計算與 context window 管理

這個範例示範如何追蹤 extended thinking 的 token 用量，以及 `effort` 設定如何改變 Claude 的思考量：

```python
def token_counting_example():
    # Define a function to create a sample prompt
    def create_sample_messages():
        messages = [
            {
                "role": "user",
                "content": "Five talks (A, B, C, D, E) must be scheduled in five consecutive slots. Constraints: A comes before C; B is not adjacent to D; E is neither first nor last; C is immediately before or after E; D comes before A. List every valid ordering and explain how you know there are no others.",
            }
        ]
        return messages

    # Count tokens without thinking
    base_messages = create_sample_messages()
    base_token_count = count_tokens(base_messages)
    print(f"Base token count (input only): {base_token_count}")

    # Make a request with thinking and check actual usage
    max_tokens = 16000
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=max_tokens,
        thinking={"type": "adaptive", "display": "summarized"},
        output_config={"effort": "xhigh"},
        messages=base_messages,
    )

    # usage.output_tokens counts the *full* thinking plus the final answer,
    # even though the thinking text we get back is only a summary.
    summary_chars = sum(
        len(block.thinking) for block in response.content if block.type == "thinking"
    )

    final_answer_tokens = sum(
        len(block.text.split()) * 1.3  # Rough estimate
        for block in response.content
        if block.type == "text"
    )

    print(f"\nInput tokens (from usage): {response.usage.input_tokens}")
    print(f"Output tokens (from usage, thinking + answer): {response.usage.output_tokens}")
    print(f"Estimated final answer tokens: ~{int(final_answer_tokens)}")
    print(
        f"So roughly ~{response.usage.output_tokens - int(final_answer_tokens)} output tokens went to thinking"
    )
    print(f"Thinking summary returned: {summary_chars} characters")
    print(
        f"Input tokens + max_tokens = {base_token_count + max_tokens} (this total must fit in the model's context window)"
    )

    # Demo with escalating effort levels: same prompt, different effort.
    # There is no token budget on current models; effort is the knob that
    # trades thinking depth for latency and cost ("max" exists too). At the
    # lower levels Claude may decide this problem needs no thinking at all,
    # in which case the response has no thinking block.
    for effort in ["low", "medium", "high", "xhigh"]:
        response = client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=max_tokens,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort},
            messages=base_messages,
        )
        summary_chars = sum(len(b.thinking) for b in response.content if b.type == "thinking")
        answer = " ".join(b.text for b in response.content if b.type == "text")
        print(f"\nWith effort={effort!r}:")
        print(f"Output tokens (thinking + answer): {response.usage.output_tokens}")
        print(f"Thinking summary length: {summary_chars} characters")
        print(f"Final answer preview: {answer[:120]}...")


# Uncomment to run the example
token_counting_example()
```

??? note "輸出"

    ```text
    Base token count (input only): 102

    Input tokens (from usage): 102
    Output tokens (from usage, thinking + answer): 1595
    Estimated final answer tokens: ~518
    So roughly ~1077 output tokens went to thinking
    Thinking summary returned: 457 characters
    Input tokens + max_tokens = 16102 (this total must fit in the model's context window)

    With effort='low':
    Output tokens (thinking + answer): 1043
    Thinking summary length: 0 characters
    Final answer preview: Constraints:
    1. A before C
    2. B not adjacent to D
    3. E in slot 2, 3, or 4
    4. C adjacent to E
    5. D before A

    From 1 and 5...

    With effort='medium':
    Output tokens (thinking + answer): 794
    Thinking summary length: 0 characters
    Final answer preview: Constraints:
    1. A before C
    2. B not adjacent to D
    3. E in slot 2, 3, or 4
    4. C adjacent to E
    5. D before A

    From 1 and 5...

    With effort='high':
    Output tokens (thinking + answer): 1150
    Thinking summary length: 423 characters
    Final answer preview: **Valid orderings (slots 1–5):**

    1. D A C E B
    2. D A E C B
    ... (省略 17 行)
    ```

## 了解 redacted thinking block

偶爾 Claude 的內部推理會被安全系統標記。這時我們會把 `thinking` block 的一部分或全部加密，以 `redacted_thinking` block 的形式回傳給你。這些 redacted thinking block 傳回 API 時會被解密，讓 Claude 能在不遺失 context 的情況下繼續回應。

這個範例用一個會觸發它的特殊測試字串，示範如何處理 redacted thinking block：

```python
def redacted_thinking_example():
    # Using the special test string that triggers redacted thinking
    response = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=16000,
        thinking={"type": "adaptive", "display": "summarized"},
        messages=[
            {
                "role": "user",
                "content": "ANTHROPIC_MAGIC_STRING_TRIGGER_REDACTED_THINKING_46C9A13E193C177646C7398A98432ECCCE4C1253D5E2D82641AC0E52CC2876CB",
            }
        ],
    )

    # Identify redacted thinking blocks
    redacted_blocks = [block for block in response.content if block.type == "redacted_thinking"]
    thinking_blocks = [block for block in response.content if block.type == "thinking"]
    text_blocks = [block for block in response.content if block.type == "text"]
    print(response.content)
    print(f"Response includes {len(response.content)} total blocks:")
    print(f"- {len(redacted_blocks)} redacted thinking blocks")
    print(f"- {len(thinking_blocks)} regular thinking blocks")
    print(f"- {len(text_blocks)} text blocks")

    # Show data properties of redacted blocks
    if redacted_blocks:
        print("\nRedacted thinking blocks contain encrypted data:")
        for i, block in enumerate(redacted_blocks[:3]):  # Show first 3 at most
            print(f"Block {i + 1} data preview: {block.data[:50]}...")

    # Print the final text output
    if text_blocks:
        print("\nFinal text response:")
        print(text_blocks[0].text)


# Uncomment to run the example
redacted_thinking_example()
```

??? note "輸出"

    ```text
    [RedactedThinkingBlock(data='CAQSlgcKEAgSGAI4AUIIdGhpbmtpbmcSDAvmF1hXsbzdc6DDlRoMIy9+bFB/la3LWaH1IjC+I73fnh6GNH2OQ+TidhopDIDmbIW4mmtPmzkCaQ8UTME/PoGMzIXaO/eVST+TaIoqswZLLsrmRNXVM/3MhNxyw8jVP+FUnkD7uGtVa42A2hGhP9K3EULP3DSzs1CO/iPrA/4LJChjLBrcwxnQEfHQW5zPbhujyTxBQtmM6jGXhZCD1O941b2NVBz35R2EPIcLMIO23k6F1p3g8UtucM8AvfbJ8qyO+JMK1/lAKsRjEuE+w0HUzYV1J526sVbUuqCYlHDsVnNHdVTPm802tuEZJo6NdR3On14JGpl4jmq0auTenXRSFCqgyiAefctT6uTFKzvzUYgYiaHGTxfxtHrN6/JPWwGhCBDPdqF8tr1dk4pzYhTY5a4cmmHGi4f++OMknWHM0Vp7OKWZZRbVvrbnm2Quwcv1gjDP2/+cUWyVg5urBpy39bU6mPNasiQkrPg0yjB/VpBLOjQ5EE+zAZILCEo4zLY7K2WD1+UHfmTi59+mfnDcqaFLjhVRK3mqY5Ut0C9IO5JFKYXyZGITljOhADq3amYPthG4ES+wgh3I4HAVNj9wo0kh2KiS7h1HDh20vF1o+Q4RpF9XPKL3OYcLPQDHxX7ZHzHLGzERnTsNGDQnxYAy95AAzn1lcnOk/rPDK+q+uqptheVgraDCxqXPtZrYyI/P7qlirMGbCoDmyi4IzAC4n1ej09Li0G0pGe8B9C49nSwn5Czn1L23/BSX7XLzddaf+/aEHOhAD7h7w+ru/NI0WBBmbyiXh8XrzRwtFmRfhhSrWAGOnFc2VtCHUijFz4XTGf6CNG0QLTw7XlT6fS+02kai2aNcIjqhhcD32cEmo8Hj9ZRDhWvfPJuHAAv9PVF14W9F+tFGSc6iW/PyQqMRRVDc4yBSUJv/va3UpBXm8Sopl3ayXgdK/OtU/dvp0FB2L+zgaFheVFARV7Y8xx4nWlSzIygix0nhPyh7+tLREn8aAfFQl3as4loRV8kcVbAI0r3KiRZzzUWshhZNfpAmnv+LGqi0dZ+dTpJPCoxPV4gt4U5fInVs/coz3Q5Yepa9SLfAvbusvwN3NoC/swXfY6pro5+6N6PKGPRSZcnj8HCVN7+SHM4LILMRuRicwBA+eJtzYmbDraTAiPg7tvpI202sh3yTgu/9PHFdQN/eQ4oYAQ==', type='redacted_thinking'), TextBlock(citations=None, text="That message looks like a test string or placeholder, not a question or request. It doesn't trigger any special behavior on my end.\n\nWhat would you like to talk about or work on? I can help with writing, coding, analysis, brainstorming, or answering questions.", type='text')]
    Response includes 2 total blocks:
    - 1 redacted thinking blocks
    - 0 regular thinking blocks
    - 1 text blocks

    Redacted thinking blocks contain encrypted data:
    Block 1 data preview: CAQSlgcKEAgSGAI4AUIIdGhpbmtpbmcSDAvmF1hXsbzdc6DDlR...

    Final text response:
    That message looks like a test string or placeholder, not a question or request. It doesn't trigger any special behavior on my end.

    What would you like to talk about or work on? I can help with writing, coding, analysis, brainstorming, or answering questions.
    ```

## 處理錯誤情況

使用 extended thinking 時請記得：

1. **用 effort，不用 budget：** 目前的模型沒有 `budget_tokens`。用 `output_config={"effort": ...}` 控制 Claude 的思考力度：從預設（`"high"`）開始，延遲和成本比深度重要時降到 `"medium"` 或 `"low"`，最難的問題再用 `"xhigh"` 或 `"max"`。對 Claude Sonnet 5.5 送舊的 `thinking={"type": "enabled", "budget_tokens": N}` 形式會得到 400 錯誤。

2. **不相容的功能：** 在 Claude Sonnet 5.5 上，非預設的 `temperature`、`top_p` 或 `top_k` 值會被拒絕（不論有沒有 thinking），也不能預填 assistant 回應。

3. **定價與限制：** Thinking token 會計入 `max_tokens` 和 context window，並以 output token 計費（計費的是完整的思考，不是你拿到的摘要）。它們也會計入 rate limit。`max_tokens` 要設得寬鬆，值很大時要用 streaming。

搭配 tool use 的 extended thinking 詳情，見「Extended Thinking with Tool Use」notebook。

```python
def demonstrate_common_errors():
    # 1. Error from sending the legacy manual-budget form.
    #    Current models only accept {"type": "adaptive"}; non-default
    #    temperature / top_p / top_k values are rejected the same way.
    try:
        client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=4000,
            thinking={
                "type": "enabled",  # Legacy form, not accepted on this model
                "budget_tokens": 1024,
            },
            messages=[{"role": "user", "content": "Explain quantum computing."}],
        )
    except Exception as e:
        print(f"\nError with legacy budget_tokens thinking config: {e}")

    # 2. Error from exceeding context window
    try:
        # Create a very large prompt (large enough to overflow the context window)
        long_content = "Please analyze this text. " + "This is sample text. " * 300000

        client.messages.create(
            model="claude-sonnet-5-5",
            max_tokens=20000,  # This plus the long prompt will exceed context window
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": long_content}],
        )
    except Exception as e:
        print(f"\nError from exceeding context window: {e}")


# Run the common error examples
demonstrate_common_errors()
```

??? note "輸出"

    ```text

    Error with legacy budget_tokens thinking config: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': '"thinking.type.enabled" is not supported for this model. Use "thinking.type.adaptive" and "output_config.effort" to control thinking behavior.'}, 'request_id': 'req_011Cfdh4WYGPktVi5kjF5NAt'}

    Error from exceeding context window: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'prompt is too long: 1800065 tokens > 1000000 maximum'}, 'request_id': 'req_011Cfdh4XWok6x352LDwYdg6'}
    ```

## 重點整理
- Sonnet 5.5 的 thinking 是 adaptive，模型自己決定想多少，簡單題可能完全不想。
- 用 `effort` 控制力度，不再有 `budget_tokens`，舊寫法會得到 400。
- `display` 預設 `"omitted"`，要讀思考內容得設 `"summarized"`，但計費仍是完整的 thinking。
- Thinking token 算進 `max_tokens`、context window 和 rate limit，並以 output token 計費。
- 部分推理可能被加密成 `redacted_thinking`，傳回 API 時會解密，要原樣保留。

## 練習
1. 把基本範例的 `effort` 從 `"xhigh"` 改成 `"low"`，比較 thinking 內容的長度。
2. 把 `display` 改成預設的 `"omitted"`，看回傳的 thinking block 長什麼樣。
3. 故意加上 `temperature=0.5`，觀察 API 的錯誤訊息。
