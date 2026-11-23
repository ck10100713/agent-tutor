---
translated: true
source: misc/session_memory_compaction.ipynb
---

# Session memory compaction

> 原文：[misc/session_memory_compaction.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/session_memory_compaction.ipynb)

用背景 thread 和 prompt caching，實現即時的 session memory compaction，管理長時間執行的 Claude 對話。

## 這篇在做什麼

長對話會超過 context 上限，重要資訊就掉了。傳統做法是 context 滿了才請 Claude 做摘要，使用者得乾等。這篇示範在背景先把 session memory 建好，等到需要 compaction 時直接換上，使用者零等待，並用 prompt caching 把背景更新的成本壓低。

## 學完你會

- 寫出能在 compaction 之後保留關鍵 context 的 session memory prompt
- 用 `threading.Thread` 和 `threading.Lock` 實作 `InstantCompactingChatSession`，讓摘要在背景更新
- 用 `cache_control` 讓背景摘要共用對話前綴的 cache，把更新成本降低約 80%

## 開跑前

- 需要 Anthropic API key 和 Anthropic SDK
- Python 3.11 以上

跟 Claude 的長對話可能超過 context 上限，導致重要資訊遺失。不管你在做 coding assistant、創作寫作工具還是客服 agent，管理 session memory 對維持連續性和品質都很關鍵。

這份 cookbook 教你**主動管理 session memory**，避免突然撞到 context 上限而中斷。有別於等 context 滿了才處理的被動做法，你會學到在背景建立 session memory，讓需要 compaction 的時候可以瞬間完成。

**相關：** agentic 工作流程裡用 SDK 自動做 compaction，請看 [Automatic Context Compaction](../tool_use/automatic-context-compaction.md)。這份 cookbook 聚焦在對話式應用的手動控制模式。

## 學習目標

讀完這份 cookbook，你將能夠：

- 寫出有效的 session memory prompt，在 compaction 事件之後保留關鍵 context
- 用背景 threading 實作**即時 compaction**，消除使用者等待時間
- 套用 prompt caching，把背景 memory 更新的成本降低約 80%
- 依你的使用情境，在傳統和即時 compaction 之間選擇合適的策略

## 先備條件與設定

在照著這份指南做之前，請確認：

**需要的知識**
- 對 Claude API 用法和 message 格式有基本了解
- 熟悉 Python threading 的概念（有的話更好，但不是必須）

**需要的工具**
- Python 3.11 以上
- Anthropic API key
- Anthropic SDK

### 安裝

首先安裝需要的相依套件。在 Colab 上直接在 cell 前面加 `!` 用 `pip install` 即可：

```python
%%capture
%pip install -U anthropic python-dotenv
```

```python
import anthropic
from anthropic.types import MessageParam, TextBlockParam
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"
```

```python
# Helper functions
def response_text(response) -> str:
    """Return the text of a response. Responses can start with a thinking block, so this reads
    the text blocks rather than content[0].

    Raises instead of returning "" so an empty assistant turn is never stored in the history
    (the API rejects empty text blocks on the next request)."""
    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise ValueError(
            f"Response has no text content (stop_reason={response.stop_reason!r}). "
            "If stop_reason is 'max_tokens', thinking used the whole budget: raise max_tokens."
        )
    return text


def kept_output_tokens(usage) -> int:
    """Output tokens that end up in the conversation: usage.output_tokens minus thinking tokens,
    which are billed as output but never stored in the message history."""
    details = getattr(usage, "output_tokens_details", None)
    thinking_tokens = getattr(details, "thinking_tokens", 0) or 0
    return usage.output_tokens - thinking_tokens


def truncate_response(text: str, max_lines: int = 15) -> str:
    """Truncate long responses for cleaner output display."""
    lines = text.strip().split("\n")
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def remove_thinking_blocks(text: str) -> tuple[str, str]:
    """Remove <think>...</think> blocks from the text."""
    import re

    matches = re.findall(r"<think>.*?</think>", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()
    return cleaned, "".join(matches)


def add_cache_control(messages: list[dict]) -> list[MessageParam]:
    """Add cache_control to the last user message for prompt caching.

    For prompt caching to work, the message prefix structure must be identical between requests.
    All messages are converted to list format for consistency, and cache_control is placed on
    the last user message to match the standard API call pattern.
    """
    cached_messages: list[MessageParam] = []
    last_user_idx = None

    # Find last user message index
    for i, msg in enumerate(messages):
        if msg["role"] == "user":
            last_user_idx = i

    for i, msg in enumerate(messages):
        content = msg["content"]
        text = content if isinstance(content, str) else content[0]["text"]

        content_block: TextBlockParam = {"type": "text", "text": text}
        if i == last_user_idx:
            content_block["cache_control"] = {"type": "ephemeral"}

        cached_messages.append({"role": msg["role"], "content": [content_block]})

    return cached_messages


def estimate_tokens(text: str) -> int:
    """Rudimentary token estimation: 1 token per 4 characters."""
    return len(text) // 4
```

```python
SESSION_MEMORY_PROMPT = """
Compress the conversation into a structured summary
that preserves all information needed to continue work seamlessly. Optimize for the assistant's
ability to continue working, not human readability.

<analysis-instructions>
Before generating your summary, analyze the transcript in <think>...</think> tags:
1. What did the user originally request? (Exact phrasing)
2. What actions succeeded? What failed and why?
3. Did the user correct or redirect the assistant at any point?
4. What was actively being worked on at the end?
5. What tasks remain incomplete or pending?
6. What specific details (IDs, paths, values, names) must survive compression?
</analysis-instructions>

<summary-format>
## User Intent
The user's original request and any refinements. Use direct quotes for key requirements.
If the user's goal evolved during the conversation, capture that progression.

## Completed Work
Actions successfully performed. Be specific:
- What was created, modified, or deleted
- Exact identifiers (file paths, record IDs, URLs, names)
- Specific values, configurations, or settings applied

## Errors & Corrections
- Problems encountered and how they were resolved
- Approaches that failed (so they aren't retried)
- User corrections: "don't do X", "actually I meant Y", "that's wrong because..."
Capture corrections verbatim—these represent learned preferences.

## Active Work
What was in progress when the session ended. Include:
- The specific task being performed
- Direct quotes showing exactly where work left off
- Any partial results or intermediate state

## Pending Tasks
Remaining items the user requested that haven't been started.
Distinguish between "explicitly requested" and "implied/assumed."

## Key References
Important details needed to continue:
- Identifiers: IDs, paths, URLs, names, keys
- Values: numbers, dates, configurations, credentials (redacted)
- Context: relevant background information, constraints, preferences
- Citations: sources referenced during the conversation
</summary-format>

<preserve-rules>
Always preserve when present:
- Exact identifiers (IDs, paths, URLs, keys, names)
- Error messages verbatim
- User corrections and negative feedback
- Specific values, formulas, or configurations
- Technical constraints or requirements discovered
- The precise state of any in-progress work
</preserve-rules>

<compression-rules>
- Weight recent messages more heavily—the end of the transcript is the active context
- Omit pleasantries, acknowledgments, and filler ("Sure!", "Great question")
- Omit system context that will be re-injected separately
- Keep each section under 500 words; condense older content to make room for recent
- If you must cut details, preserve: user corrections > errors > active work > completed work
</compression-rules>
"""
```

### 傳統 compaction 的程式範例
傳統 compaction 是等 token 達到門檻時，才產生一份摘要。
傳統 compaction 很慢：撞到 context 上限時，你得等摘要產生。


```
TRADITIONAL COMPACTION (slow)
─────────────────────────────
Turn 1 → Turn 2 → Turn 3 → ... → Turn N → CONTEXT FULL!
                                              │
                                              ▼
                                    ┌─────────────────┐
                                    │ Generate summary│
                                    │ ( USER WAITS !) │
                                    └─────────────────┘
                                              │
                                              ▼
                                         Continue

```

```python
import time


class TraditionalCompactingChatSession:
    """Traditional chat session with compaction after the fact."""

    def __init__(self, system_message="You are a helpful assistant", context_limit: int = 10000):
        self.system_message = system_message
        self.context_limit = context_limit  # the point at which the conversation is compacted so it does not exceed model limits.
        self.messages = []
        self.current_context_window_tokens = 0
        self.summary = None

    def chat(self, user_message: str) -> tuple[str, anthropic.types.Usage]:
        # In traditional compaction, we check if we need to compact when the user sends a message. NOT IDEAL!
        if self.current_context_window_tokens >= self.context_limit:
            print(
                f"\n🧹 Context window at {self.current_context_window_tokens} tokens. Limit exceeded, compacting session memory..."
            )
            self.compact()  # compacts everything before the new user message

        self.messages.append({"role": "user", "content": user_message})
        print(f"\nUser: {user_message}")

        # A thinking model can spend 10K+ tokens reasoning before a long draft, so give it a large
        # budget and stream the reply (the SDK requires streaming for budgets this size).
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=self.system_message,
            messages=add_cache_control(self.messages),
        ) as stream:
            response = stream.get_final_message()
        assistant_message = response_text(response)
        self.messages.append({"role": "assistant", "content": assistant_message})

        print(f"\nAssistant: \n{truncate_response(assistant_message, max_lines=15)}")

        # approximate current token count in the conversation before the next user message
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        total_input = response.usage.input_tokens + cache_read + cache_write
        # thinking tokens are not stored in self.messages, so kept_output_tokens() leaves them out
        self.current_context_window_tokens = total_input + kept_output_tokens(response.usage)

        print(
            f"Input={total_input:,}, Prompt cached used= {cache_read > 0} | "
            f"Output={response.usage.output_tokens:,} | "
            f"Messages={len(self.messages)}"
        )
        return assistant_message, response.usage

    def compact(self) -> None:
        start_time = time.perf_counter()

        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=self.system_message,  # Same as main chat for cache sharing
            messages=add_cache_control(self.messages)
            + [{"role": "user", "content": SESSION_MEMORY_PROMPT}],
        ) as stream:
            response = stream.get_final_message()
        elapsed = time.perf_counter() - start_time

        # Generate new summary message
        self.summary, removed_text = remove_thinking_blocks(
            response_text(response)
        )  # clean up any <think> blocks because they are not needed in the session memory
        approximate_summary_tokens = kept_output_tokens(response.usage) - round(
            len(removed_text) / 4
        )  # rough estimate: text output minus the <think> block we stripped

        # Replace prior messages with new summary message
        self.messages = [
            {
                "role": "user",
                "content": f"""This session is being continued from a previous conversation. Here is the session memory: {self.summary}.Continue from where we left off.""",
            }
        ]

        # Show token reduction if we just compacted
        reduction = self.current_context_window_tokens - approximate_summary_tokens
        pct = (reduction / self.current_context_window_tokens) * 100

        print(f"\n{'-' * 60}")
        print("📝 New session memory created.")
        print(
            f"✅ Tokens reduced: {self.current_context_window_tokens:,} → {approximate_summary_tokens:.0f} ({reduction:,} tokens saved, {pct:.0f}% reduction)"
        )
        print(f"⏱️ Compaction time: {elapsed:.2f}s (user waiting...)")
        print(f" Cache used: {getattr(response.usage, 'cache_read_input_tokens', 0) > 0}")
        print(f"{'-' * 60}")

        # Update token count to reflect compacted state
        self.current_context_window_tokens = approximate_summary_tokens
```

下面模擬一位作者和一個協助寫故事的 LLM 之間的對話。

```python
SYSTEM_PROMPT = """
You are a short story writer who helps authors develop their ideas into compelling narratives.

## What You Do

**Plot Development**
- Help authors work through story structure, pacing, and narrative arc
- Identify plot holes, inconsistencies, or missed opportunities
- Suggest ways to raise stakes, add tension, or deepen conflict
- Brainstorm twists, resolutions, and scene transitions

**Character Development**
- Develop backstories, motivations, and internal conflicts
- Ensure characters have distinct voices and consistent behavior
- Explore character relationships and how they drive the plot
- Help authors understand what their characters want vs. what they need

**Drafting**
- Write short stories or scenes based on the author's ideas and direction
- Match tone, genre conventions, and stylistic preferences
- Show rather than tell when bringing scenes to life
- Craft dialogue that reveals character and advances plot

## How You Work
- You are the lead writer. When you disagree with a creative choice, say so respectfully, but ultimately defer to what the author wants.
- DO NOT ask the user to provide more context or clarify their request. Assume you have enough information to proceed.
"""
```

```python
session = TraditionalCompactingChatSession(system_message=SYSTEM_PROMPT)

# Simulated conversation
messages = [
    "I want to create a story about a young detective solving a mysterious case in a small town. Generate 3 well thought out plot ideas for me to consider.",
    "I don't like those ideas, can you think of one plot something more unique and unexpected?",
    "Ok I like it. Can you help me develop the main character's backstory and motivations?",
    "Can you draft a detailed outline for the story, breaking it down into chapters and key events?",
    "Can you draft me a first chapter based on the plot and character ideas we've discussed so far? Make it around 2,000 words.",
    "Can you draft a second chapter that builds on the first one, introducing a new twist in the mystery?",
]

print("Starting conversation...\n")

turn_count = 0

for _i, message in enumerate(messages, 1):
    turn_count += 1
    print(f"==============================================\nTurn {turn_count}:\n")
    response, usage = session.chat(message)
```

??? note "輸出"

    ```text
    Starting conversation...

    ==============================================
    Turn 1:


    User: I want to create a story about a young detective solving a mysterious case in a small town. Generate 3 well thought out plot ideas for me to consider.

    Assistant: 
    # Three Plot Concepts: Young Detective, Small Town

    ## 1. The Lighthouse Keeper's Ledger

    **Setting:** Harrow's End, a fading fishing town on a foggy northern coast.

    **Detective:** Nell Okafor, 24, a newly appointed deputy who returned home after failing out of a big-city police academy. She's underestimated by everyone, including herself.

    **The Case:** The town's retired lighthouse keeper, Abel Rusk, is found dead at the base of the tower, an apparent fall. But his meticulously kept weather ledger has a page torn out, and the final entry is dated three days *after* his death.

    **How It Unfolds:**
    - Nell discovers Abel wasn't just logging weather. He was recording the nighttime comings and goings of boats that never appeared in the harbor records.
    - Each lead points to a different respected townsperson: the harbormaster, the cannery owner, the beloved pastor.
    - The mystery deepens when she realizes the post-death entry was written by someone who knew Abel's shorthand, which only his estranged daughter and Nell's own late father ever learned.

    ... (49 more lines)
    Input=444, Prompt cached used= False | Output=1,791 | Messages=2
    ==============================================
    Turn 2:


    User: I don't like those ideas, can you think of one plot something more unique and unexpected?

    Assistant: 
    # The Drought Year

    ## The Hook

    Calder Bend sits on the edge of a reservoir that has been dropping for months. Beneath the water lies Old Calder, the original town, flooded in 1978 so the new one could have a water supply. Then the doorsteps start filling up.

    Every morning, a different family in town finds a waterlogged object on their porch, arranged with care: a child's shoe, a church hymnal swollen shut, a brass house number, a barber's chair bolt. Nothing is stolen, no one is threatened, and there are no footprints. The only trace is a trail of silt and the smell of lake bed.
    ... (省略 115 行)
    ```

這是一段有好幾輪的長對話，你會注意到幾件事：

Prompt caching：你會看到輸入 token 很快成長到足以使用 prompt caching 的程度（第 3 輪）。對話越長，這能幫忙降低成本、加快速度！

Compaction：到了第 6 輪，對話已經超過我們設定的 10K context window 上限，所以 session 在回答之前先停下來做 compaction，使用者全程在等。

只要有一輪開始時超過 10K 上限，使用者就得先等 compaction 才能拿到答案；上面這次執行是在第 6 輪發生。下一輪就從壓縮後的 session memory 接著走：

```python
response, usage = session.chat("Propose a title for the book")
```

??? note "輸出"

    ```text

    User: Propose a title for the book

    Assistant: 
    # Title Proposals

    **My top pick: *A Thing Written Down Properly***
    This is Walter's line, and the story's central irony. Dilly believes a written record stays true, but the record that matters most is a forgery, and she ends up forging one herself before correcting it. The title sounds calm and bureaucratic, which suits the mystery's understated tone, and the meaning turns darker as the story goes on. It's also a quiet fit for the ending, when Dilly's notebook finally holds words instead of measurements.

    **Other options**

    - ***Dead Pool***: A real reservoir term for water that has dropped below the outlet and can no longer flow downstream. It works as both a technical term and a hint at the body in the pumphouse cellar. It's the most genre-forward choice, but a bit blunt for the prose style we've established.
    - ***Full Pool***: The opposite term, for a reservoir at capacity. It suggests the town's whole history rests on a lake kept full at any cost. It's subtler, but less intriguing on a cover.
    - ***Below the 1,140 Line***: Taken from the last line of Chapter 1. It's specific and atmospheric, and it makes readers wonder what lies below the line. It's a little clinical as a book title.
    - ***Proceed***: One word, from Harold Pruitt's pencil note. It's sharp and ominous, and it implies the town's complicity. It might be too cryptic before the reader has context.
    - ***The Water Girl***: Dilly's nickname. It puts the protagonist first, but it sounds like a different, lighter book, and it undersells the story's moral weight.

    **My recommendation:** *A Thing Written Down Properly*, with *The Drought Year* kept as the working title in the outline. If you'd rather have something shorter and more commercial, *Dead Pool* is the strongest alternative.
    Input=7,728, Prompt cached used= True | Output=1,086 | Messages=5
    ```

你會看到上面 agent 壓縮對話花了**超過 25 秒**。因為用的是傳統 compaction，使用者得等 Claude 壓縮對話，使用體驗不理想。

下面是壓縮的結果。它用大約 3K token 抓住了對話的關鍵元素。

```python
print(session.summary)
```

??? note "輸出"

    ```text
    ## User Intent
    The user is developing a short story or novelette about a young detective in a small town. Original request: "Generate 3 well thought out plot ideas." After rejecting those ("I don't like those ideas, can you think of one plot something more unique and unexpected?"), they approved "The Drought Year" ("Ok I like it"). They then requested, in order: protagonist backstory and motivations, a detailed chapter-by-chapter outline, and a Chapter 1 draft of "around 2,000 words." The system role is lead writer: respectfully voice disagreements, defer to the author, and never ask for clarification (assume enough information to proceed).

    ## Completed Work
    - **3 initial plots** (rejected, do not reuse).
    - **Premise, "The Drought Year":** Calder Bend sits beside a reservoir that is dropping in a drought. Old Calder, flooded in 1978, is resurfacing. Each morning a waterlogged Old Calder object appears on the porch of a descendant of the family tied to it. The deliveries follow Old Calder's Front Street toward the Wend property, which will surface in about a week.
    - **Twist:** The culprit is Dilly's grandmother Hester, who has early dementia. In 1978 her husband Walter, the council clerk, forged Tobias Wend's "relocation" papers after Wend was sealed in the pumphouse cellar so the floodgates could close on schedule. Hester sleepwalks to the lake bed and delivers objects, a confession she cannot say aloud.
    - **Dilly's character document:**
      - Odile "Dilly" Marsh, 19, technician at the county surveyor's office, locally called "the water girl." She calls Hester "Hess."
      - Mother Renata left at 17, returned when Dilly was 3, left again after 4 years, and sends cards and checks. Father unknown.
      - Walter taught her to read plat maps and told her "A thing written down properly stays true." He died when she was 11. She carries his brass ruler.
      - She deferred a hydrology scholarship because of Hester's lapses.
      - Lie she believes: "If I keep the record clean and the people I love close, nothing can be taken from me." Need: accept that love sometimes means letting someone tell a devastating truth, and that she comes from complicity.
      - Flaws: over-reliance on data, protective secrecy, retreat into estimating when emotional, stubborn pride.
      - Habits: paces off distances, mutters figures, sketches objects in a waterproof field notebook instead of photographing them, dry speech.
      - Key arc beat: she falsifies an official waterline reading, repeating Walter's act, then corrects it.
    - **10-chapter outline over 9 days:**
      - Ch1 Low Water (Day 1)
      - Ch2 The Hymnal (Day 2): meets Gus Ferreira, the old surveyor; the hymnal is stolen from the evidence locker.
      - Ch3 The Procession (Day 3): route extrapolated, six days until the Wend property surfaces; Wend's records show no new address, tax record, or death certificate.
      - Ch4 The Daughter Returns (Day 4): Renata arrives and researches memory-care facilities; Gus says Walter's records "never quite added up"; Hester hums the hymn.
      - Ch5 The Seal (Day 5, midpoint): the W.M. embossing seal appears on the Marsh porch; Dilly follows sleepwalking Hester at 2 a.m.
      - Ch6 The Paper (Day 6): the relocation form is dated Oct 12, but the gates closed Oct 9.
      - Ch7 The Falsified Reading (Days 6-7, low point): Dilly changes "three days" to "three weeks"; she fights with Renata.
      - Ch8 Hess (Day 8): Hester is lucid, then asks "Who are you?" and answers to "Hess"; Renata reconciles; the sheriff arrives with a warrant.
      - Ch9 The Water Drops (Days 8-9): the pumphouse surfaces early; Dilly corrects the record; Gus co-signs.
      - Ch10 The Key (Day 9): Hester, Dilly, and Renata walk through the town; Hester places a small iron key on the Wend doorstep; Dilly writes non-measurement words in her notebook.
      - Optional coda: Hester forgets it all.

    **Delivery table:**

    | Day | Object | Recipient | Meaning |
    |---|---|---|---|
    | 1 | Child's shoe | Pruitt family | The council chairman's daughter lost it the night the gates closed |
    | 2 | Swollen hymnal | Ames family | The reverend blessed the closing |
    | 3 | Brass house number | Kessler (sheriff) | The constable locked Wend's door |
    | 4 | Barber's chair bolt | Dutton family | The council voted in his shop |
    | 5 | Embossing seal "W.M." | Marsh house | Walter forged the papers |
    | 7 | Pump valve wheel | Ibsen family | The pumphouse operator sealed the cellar |
    | 9 | Wend's front-door key | Wend doorstep | Hester kept it for over 40 years |
    ... (省略 54 行)
    ```

## 即時 Compaction

**即時 compaction** 是在達到軟性 token 門檻時，就**主動**產生 session memory。

等使用者觸發 compaction 或到達硬性上限時，摘要已經準備好了，使用者不用等。

結果：即時 compaction，不用等。


SESSION MEMORY COMPACTION (instant)
```
────────────────────────────────────
Turn 1 → Turn 2 → ... → Turn K → Turn K+1 → ... → Turn N → ..  → CONTEXT FULL!
                            │                         │            │
                (soft token threshold met:        (update          │
               initialize session memory)          trigger)        │
                            │                                      │
                            │                         │            │
                            ▼                         ▼            │
                       ┌────────┐                ┌────────┐        │
                       │ Create │                │ Update │        │
                       │ memory │ (background)   │ memory │        │
                       └────────┘                └────────┘        │
                            │                         │            │
                            ▼                         ▼            ▼
                     📝 session-memory.md ──────────────────► INSTANT SWAP!
                       (continuously updated)
```

**更新觸發時機：** 第一份摘要在達到初始軟性 token 上限後產生。之後可以每一輪都更新，或在自然的段落處定期更新（例如每約 10k token 或 3 次以上 tool call）。

這個 `InstantCompactingChatSession` 類別用 **threading** 在背景執行：
1. **`threading.Thread`**：在背景執行 memory 更新，不阻塞主流程
2. **Thread-safe 狀態**：用 `threading.Lock` 安全地更新共享的 memory
3. **Daemon thread**：背景工作不會讓程式無法結束
4. **即時 compaction**：context 滿的時候，直接換上預先建好的 memory

```python
import threading
import time


class InstantCompactingChatSession:
    """
    Maintains session memory via incremental background updates.

    Key insight: By updating memory in the background after each turn,
    the summary is already ready when compaction is needed - instant swap!
    """

    def __init__(
        self,
        system_message="You are a helpful assistant",
        context_limit: int = 12000,
        min_tokens_to_init: int = 7500,
        min_tokens_between_updates: int = 2000,
    ):
        # Thresholds
        self.context_limit = context_limit  # the point at which the conversation is compacted so it does not exceed model limits
        self.min_tokens_to_init = min_tokens_to_init  # tokens needed to trigger initial memory creation; note this happens PROACTIVELY in background unlike traditional compaction
        self.min_tokens_between_updates = min_tokens_between_updates  # tokens needed to trigger memory update. only comes into play after initial memory is created and additional compaction (memory update) is needed after that

        # Conversation state
        self.system_message = system_message
        self.messages = []
        self.current_context_window_tokens = 0

        # Session memory state
        self.session_memory = None  # this is the compacted conversation in session memory; for the demo we are storing this in memory, but in production you would write to session_memory.md file
        self.last_summarized_index = (
            0  # The index of the last message included in the session memory
        )
        self.tokens_at_last_update = 0  # To track tokens at last memory update and see if enough new tokens have been added to trigger another update

        # Background update tracking
        self._update_thread: threading.Thread | None = None
        self._compactions = 0  # bumped by compact(); lets an in-flight update notice it went stale
        self.last_update_time = None
        self._lock = threading.Lock()

    def chat(self, user_message: str) -> tuple[str, anthropic.types.Usage, str | None]:
        """Process a chat turn with background session memory updates."""

        if self.current_context_window_tokens + estimate_tokens(user_message) >= self.context_limit:
            self.compact()  # note that when this is triggered, the compaction has already been created and is just swapped in instantly

        self.messages.append({"role": "user", "content": user_message})

        # Large budget + streaming, as in the traditional session: thinking can run 10K+ tokens
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=self.system_message,
            messages=add_cache_control(self.messages),
        ) as stream:
            response = stream.get_final_message()

        assistant_message = response_text(response)
        self.messages.append({"role": "assistant", "content": assistant_message})

        # Calculate token usage including cache
        cache_read = getattr(response.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(response.usage, "cache_creation_input_tokens", 0) or 0
        total_input = response.usage.input_tokens + cache_read + cache_write

        # Update context window tokens (includes cached tokens since they still count toward context;
        # thinking tokens are not stored in self.messages, so kept_output_tokens() leaves them out)
        self.current_context_window_tokens = total_input + kept_output_tokens(response.usage)

        # KEY DIFFERENCE: Trigger background memory update if needed proactively, before compaction is needed
        background_status = None
        if self._should_init_memory() or self._should_update_memory():
            if self._trigger_background_update():
                background_status = "initializing" if self.session_memory is None else "updating"

        # Return usage info with cache stats
        return assistant_message, response.usage, background_status

    # Helper methods to determine when to init session memory
    def _should_init_memory(self) -> bool:
        return (
            self.session_memory is None
            and self.current_context_window_tokens >= self.min_tokens_to_init
        )

    # Helper method to determine if memory should be updated
    def _should_update_memory(self) -> bool:
        if self.session_memory is None:
            return False
        tokens_since = self.current_context_window_tokens - self.tokens_at_last_update
        return tokens_since >= self.min_tokens_between_updates

    # Methods to create initial session memory
    def _create_session_memory(self, messages: list[dict]) -> str:
        """Generate initial session memory from messages."""
        # Put compaction instructions in user message to share cache with main chat
        compaction_messages = [{"role": "user", "content": SESSION_MEMORY_PROMPT}]
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=self.system_message,  # Same as main chat for cache sharing
            messages=add_cache_control(messages) + compaction_messages,
        ) as stream:
            response = stream.get_final_message()
        summary, _ = remove_thinking_blocks(
            response_text(response)
        )  # clean up any <think> blocks because they are not needed in the session memory
        print(
            f"   [Background] Initial session memory created. Cache hit={getattr(response.usage, 'cache_read_input_tokens', 0) > 0}"
        )
        return summary

    def _update_session_memory(self, new_messages: list[dict]) -> str:
        """Update existing session memory with new messages. In practice, you may want to do this via file edit rather than full re-generation. But for demo purposes we do full regeneration here."""
        # Put compaction instructions in user message to share cache with main chat
        compaction_update_messages = [
            {
                "role": "user",
                "content": SESSION_MEMORY_PROMPT
                + f"""There is an existing session memory: {self.session_memory}. Return the entire session memory with updates to reflect new messages.""",
            }
        ]
        with client.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=self.system_message,
            messages=new_messages
            + compaction_update_messages,  # you may want to use prompt caching instead, in which case you'd use add_cache_control(self.messages) here
        ) as stream:
            response = stream.get_final_message()
        updated_summary, _ = remove_thinking_blocks(
            response_text(response)
        )  # clean up any <think> blocks because they are not needed in the session memory
        print("   [Background] Session memory updated.")
        return updated_summary

    # Background memory update methods
    def _background_memory_update(
        self,
        messages_snapshot: list[dict],
        snapshot_index: int,
        current_tokens: int,
        generation: int,
    ) -> None:
        """Run session memory update in a background thread."""
        try:
            with self._lock:
                current_session_memory = self.session_memory
                last_index = self.last_summarized_index

            if current_session_memory is None:
                new_memory = self._create_session_memory(messages_snapshot)
            else:
                # Get new messages since last summary
                new_messages = messages_snapshot[last_index:]
                if not new_messages:
                    return
                new_memory = self._update_session_memory(new_messages)

            # Update state (thread-safe)
            with self._lock:
                if generation != self._compactions:
                    if generation + 1 != self._compactions:
                        return  # compacted more than once since the snapshot: drop this result
                    # compact() ran once while this update was in flight. It kept the turns this
                    # update covers verbatim right after the summary message, so re-base the index
                    # onto the compacted list and keep the token baseline compact() set.
                    snapshot_index = 1 + (snapshot_index - last_index)
                    current_tokens = self.tokens_at_last_update
                self.session_memory = new_memory
                self.last_summarized_index = snapshot_index
                self.tokens_at_last_update = current_tokens
                self.last_update_time = time.time()

        except Exception as e:
            print(f"   [Background] Error updating memory: {e}")

    # This makes sure only one background update runs at a time. If one is already running, we skip starting another. If not, we start a new thread to do the update.
    def _trigger_background_update(self) -> bool:
        """Trigger a background session memory update. Returns False if one is already running."""
        if self._update_thread is not None and self._update_thread.is_alive():
            return False

        messages_snapshot = self.messages.copy()
        snapshot_index = len(messages_snapshot)
        current_tokens = self.current_context_window_tokens

        self._update_thread = threading.Thread(
            target=self._background_memory_update,
            args=(messages_snapshot, snapshot_index, current_tokens, self._compactions),
            daemon=True,
        )
        self._update_thread.start()
        return True

    def wait_for_background_update(self, timeout: float = 120.0) -> None:
        """Block until any in-flight background memory update finishes."""
        if self._update_thread is not None and self._update_thread.is_alive():
            self._update_thread.join(timeout=timeout)

    # Function to compact
    def compact(self) -> None:
        """INSTANT compaction using pre-built session memory."""
        prev_msg_count = len(self.messages)

        # Ensure session memory is ready. Shouldn't be an issue normally, but here for safety.
        if self.session_memory is None:
            if self._update_thread is not None and self._update_thread.is_alive():
                print("   ⏳ Waiting for background memory update...")
                self.wait_for_background_update()

            if self.session_memory is None:
                print("   ⚠️  No pre-built memory, creating synchronously...")
                start = time.perf_counter()
                self.session_memory = self._create_session_memory(self.messages)
                elapsed = time.perf_counter() - start
                print(f"   ⏱️  Took {elapsed:.2f}s (but should be instant normally!)")
                self.last_summarized_index = len(self.messages)
                self._compactions += 1  # an update still in flight predates this memory: drop it

        with self._lock:
            unsummarized = self.messages[self.last_summarized_index :]
            summary_message = [
                {
                    "role": "user",
                    "content": f"""This session is being continued from a previous conversation. Here is the session memory: {self.session_memory}.Continue from where we left off.""",
                }
            ]
            self.messages = summary_message + unsummarized
            self.last_summarized_index = 1
            self._compactions += 1

            # Re-base the token bookkeeping on the compacted context (the next response replaces
            # this estimate with real usage) so a background update can fire again before the
            # limit is reached.
            self.current_context_window_tokens = estimate_tokens(self.system_message) + sum(
                estimate_tokens(m["content"]) for m in self.messages
            )
            self.tokens_at_last_update = self.current_context_window_tokens

            print(f"\n{'=' * 60}")
            print(f"⚡ INSTANT COMPACTION! Messages: {prev_msg_count} → {len(self.messages)}")
            print("   Session memory was pre-built (no wait time!)")
            print(f"{'=' * 60}")
```

### 即時 Compaction 的使用範例

```python
# Low thresholds for demo - in production you'd use higher values
session = InstantCompactingChatSession(
    system_message=SYSTEM_PROMPT,
)

messages = [
    "I want to create a story about a young detective solving a mysterious case in a small town. Generate 3 well thought out plot ideas for me to consider.",
    "I don't like those ideas, can you think of one plot something more unique and unexpected?",
    "Ok I like it. Can you help me develop the main character's backstory and motivations?",
    "Can you draft a detailed outline for the story, breaking it down into chapters and key events?",
    "Can you draft me a first chapter based on the plot and character ideas we've discussed so far? Make it around 2,000 words.",
    "Can you draft a second chapter that builds on the first one?",
]
print("Starting conversation with instant compacting chat session...\n")

turn_count = 0
for message in messages:
    response, usage, background_status = session.chat(message)
    turn_count += 1

    # Calculate cache stats
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_created = getattr(usage, "cache_creation_input_tokens", 0) or 0
    total_input = usage.input_tokens + cache_read + cache_created

    print(f"{'=' * 60}")
    print(f"Turn {turn_count}:")
    print(f"\nUser: {message}")
    print(f"\nAssistant: \n{truncate_response(response, max_lines=3)}")
    print("\nToken Usage:")
    print(
        f"  Input: {total_input:,} (new: {usage.input_tokens:,}, cached: {cache_read:,}, "
        f"cache write: {cache_created:,})"
    )
    print(f"  Output: {usage.output_tokens:,}")
    print(
        f"  Messages: {len(session.messages)} | Memory: {'ready' if session.session_memory else 'not yet'}"
    )

    if cache_read > 0:
        cache_pct = (cache_read / total_input) * 100
        print(f"  ✓ Cache hit! {cache_pct:.0f}% of input from cache")

    if background_status:
        print(f"\n  [Background] Proactively {background_status} session memory...")
        print(f"  Context window: {session.current_context_window_tokens:,} tokens")

    print()
```

??? note "輸出"

    ```text
    Starting conversation with instant compacting chat session...

    ============================================================
    Turn 1:

    User: I want to create a story about a young detective solving a mysterious case in a small town. Generate 3 well thought out plot ideas for me to consider.

    Assistant: 
    # Three Plot Concepts: Young Detective in a Small Town

    ## 1. **The Lighthouse Keeper's Ledger**
    ... (54 more lines)

    Token Usage:
      Input: 444 (new: 444, cached: 0, cache write: 0)
      Output: 1,768
      Messages: 2 | Memory: not yet

    ============================================================
    Turn 2:

    User: I don't like those ideas, can you think of one plot something more unique and unexpected?

    Assistant: 
    # **The Missing Tuesday**

    **Setting:** Little Marrow, a town of 412 people, tucked in a valley with one road in and one road out
    ... (29 more lines)

    Token Usage:
      Input: 2,143 (new: 4, cached: 0, cache write: 2,139)
      Output: 2,955
      Messages: 4 | Memory: not yet

    ============================================================
    Turn 3:

    User: Ok I like it. Can you help me develop the main character's backstory and motivations?

    Assistant: 
    ... (省略 76 行)
    ```

```python
message = "What did we just talk about? Give me one sentence"
response, usage, background_status = session.chat(message)

# Calculate cache stats
cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
cache_created = getattr(usage, "cache_creation_input_tokens", 0) or 0
total_input = usage.input_tokens + cache_read + cache_created

print(f"\nUser: {message}")
print(f"\nAssistant: \n{truncate_response(response, max_lines=3)}")
print("\nToken Usage:")
print(
    f"  Input: {total_input:,} (new: {usage.input_tokens:,}, cached: {cache_read:,}, "
    f"cache write: {cache_created:,})"
)
print(f"  Output: {usage.output_tokens:,}")
print(
    f"  Messages: {len(session.messages)} | Memory: {'ready' if session.session_memory else 'not yet'}"
)

if cache_read > 0:
    cache_pct = (cache_read / total_input) * 100
    print(f"  ✓ Cache hit! {cache_pct:.0f}% of input from cache")

# The last turn may have kicked off another background memory update. Wait for it so the
# notebook doesn't finish with the daemon thread still mid-request.
session.wait_for_background_update()
```

??? note "輸出"

    ```text

    User: What did we just talk about? Give me one sentence

    Assistant: 
    We drafted Chapters 1 and 2 of *The Missing Tuesday*: Wren Okafor wakes to a "Tuesday" that is really Wednesday, with an unexplained wrist mark and an unread notebook page, then finds a bound stranger's body in the church, as Deputy Hal Brewer deflects and the silent townspeople watch, with notes on the clues planted along the way and an offer to move on to Chapter 3.

    Token Usage:
      Input: 10,978 (new: 4, cached: 7,234, cache write: 3,740)
      Output: 408
      Messages: 7 | Memory: ready
      ✓ Cache hit! 66% of input from cache
       [Background] Session memory updated.
    ```

你會看到對話一碰到 context 上限（上面的第 6 輪），預先建好的 session memory 就被瞬間換上，使用者回應時零等待！之後背景更新讓 memory 在後續輪次持續保持最新。

## 進階：了解 Prompt Caching


用 prompt caching 可以讓背景更新**便宜約 10 倍**。訣竅是：
1. 把**完整對話**傳給背景摘要器
2. 加上 `cache_control` 標記，讓之後的請求命中 cache
3. 只有新的「請摘要」指令按全價計費

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    PROMPT CACHING FOR LONG CONVERSATIONS                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  WITHOUT CACHING: Pay full price for entire context every turn                 │
│  ════════════════════════════════════════════════════════════                   │
│                                                                                 │
│  Turn 1:  [System][User1][Asst1]                         →  500 tokens  @ $3/M │
│  Turn 2:  [System][User1][Asst1][User2][Asst2]           → 1500 tokens  @ $3/M │
│  Turn 3:  [System][User1][Asst1][User2][Asst2][User3]... → 3000 tokens  @ $3/M │
│  Turn 4:  [System][User1][Asst1][User2][Asst2][User3]... → 5000 tokens  @ $3/M │
│           ─────────────────────────────────────────────                         │
│                                              Total: 10,000 tokens = $0.030      │
│                                                                                 │
│                                                                                 │
│  WITH CACHING: Pay full price once, then 90% discount on prefix                │
│  ═══════════════════════════════════════════════════════════════                │
│                                                                                 │
│  Turn 1:  [System][User1][Asst1]◆                        →  500 tokens  @ $3/M │
│                                ▲                            (cache created)    │
│                          cache breakpoint                                       │
│                                                                                 │
│  Turn 2:  [System][User1][Asst1][User2][Asst2]◆                                │
│           ╰─────── cached ──────╯                                              │
│                500 @ $0.30/M + 1000 new @ $3/M  =  $0.0032                     │
│                                                                                 │
│  Turn 3:  [System][User1][Asst1][User2][Asst2][User3][Asst3]◆                  │
│           ╰──────────── cached ─────────────╯                                  │
│               1500 @ $0.30/M + 1500 new @ $3/M  =  $0.0050                     │
│                                                                                 │
│  Turn 4:  [System][User1][Asst1][User2][Asst2][User3][Asst3][User4][Asst4]◆    │
│           ╰───────────────────── cached ─────────────────────╯                 │
│                     3000 @ $0.30/M + 2000 new @ $3/M  =  $0.0069               │
│           ─────────────────────────────────────────────                         │
│                                              Total: $0.0166  (45% savings)     │
│                                                                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  COMPACTION + CACHING: Double benefit                                           │
│  ════════════════════════════════════                                           │
│                                                                                 │
│    Main Chat                      Background Summarizer                         │
│    ─────────                      ─────────────────────                         │
│                                                                                 │
│  [Conversation grows...]          [Same conversation prefix]◆ + [Summarize!]   │
│         │                                    │                                  │
│         │                         Cache hit! Only pays for                      │
│         │                         the summarization prompt                      │
│         │                                    │                                  │
│         ▼                                    ▼                                  │
│  Context limit reached  ──────►  Session memory ready instantly                │
│                                  (built cheaply in background)                  │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │  Key insight: The background summarizer reuses the same conversation     │  │
│  │  prefix that was just sent to the main chat - automatic cache hit!       │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘

◆ = cache_control breakpoint (cache everything before this point)
```

### 為什麼這對 compaction 很重要

| Scenario | Cost per background update | Notes |
|----------|---------------------------|-------|
| No caching | Full input cost | 5,000 tokens × $3/M = $0.015 |
| With caching | ~10% of input cost | 500 new + 4,500 cached = $0.003 |
| **Savings** | **~80%** | Compounds over many updates |

對話越長，省越多，而這正是你最需要 compaction 的時候！

### Caching 怎麼運作

關鍵在 `_add_cache_control()` 和 `_create_session_memory_cached()`：

```python
# 1. Mark the last conversation message with cache_control
{
    "role": "user",
    "content": [{
        "type": "text",
        "text": msg["content"],
        "cache_control": {"type": "ephemeral"}  # <-- This creates a cache breakpoint
    }]
}

# 2. Also mark the system prompt
system=[{
    "type": "text",
    "text": "You are a session memory agent...",
    "cache_control": {"type": "ephemeral"}
}]
```

**為什麼有效：**
- 第一次背景更新會替 `[System + Messages]` 建立 cache entry
- 之後 message 前綴相同的更新會**命中 cache**
- 只有新的摘要指令按全價計費
- Cache entry 的 TTL 是 5 分鐘，所以更新越密集越划算

**成本計算：**
- 沒有 caching：5,000 token × $3.00/1M = 每次更新 $0.015
- 有 caching：500 個新 token × $3.00/1M + 4,500 個 cached × $0.30/1M = $0.00285
- **節省：** 背景摘要成本省約 80%

## 結論

這份 cookbook 教你怎麼用 session memory compaction 管理長時間的 Claude 對話。

### 我們涵蓋了什麼

✅ **有效的 compaction prompt**：組織 session memory 的結構，保留使用者意圖、已完成的工作、錯誤、進行中的工作和關鍵參照，丟掉廢話

✅ **即時 compaction**：用背景 threading 主動建立 session memory，到達 context 上限時消除使用者等待

✅ **用 prompt caching 省成本**：重用對話前綴的 cache，背景更新成本降低約 80%

✅ **傳統與即時模式**：了解依應用需求何時用哪一種

### 重點

1. **重視最近的內容**：對話的結尾是正在進行的工作 context
2. **使用者的更正要逐字保留**：避免模型退回舊的行為
3. **主動建立 memory**：不要等到 context 上限才動手，早點開始背景更新
4. **善用 prompt caching**：背景摘要可以跟主對話共用 cache

### 下一步

- **agentic 工作流程**：看 [Automatic Context Compaction](../tool_use/automatic-context-compaction.md)，了解搭配 tool use 的 SDK 自動 compaction
- **Production**：考慮把 session memory 存到硬碟，而不是只放在記憶體裡
- **最佳化**：實驗更新頻率的門檻，在成本和新鮮度之間取得平衡

## 重點整理

- 傳統 compaction 在撞到上限時才摘要，使用者要等；即時 compaction 在背景先建好摘要，需要時直接換上。
- 背景工作靠 thread 加 lock：thread 負責更新，lock 保護共享的 memory，daemon thread 不阻擋程式結束。
- 摘要的品質取決於 prompt：重視最近內容、保留使用者更正原文、結構化記錄意圖、進度、錯誤和參照。
- 背景摘要把完整對話當前綴並加 `cache_control`，就能吃到 cache，每次更新成本降約 80%。
- Cache 只有 5 分鐘 TTL，更新頻率和成本新鮮度要一起調。

## 練習

1. 把示範裡的 context 上限從 10K 改成 6K，重跑傳統和即時兩種 session，比較 compaction 發生的輪次和使用者等待時間。
2. 修改 session memory prompt，要求額外保留「待辦事項」一節，看壓縮後的結果有沒有包含它。
3. 把背景更新從「每輪都更新」改成「每累積約 10k token 才更新」，記錄成本和 memory 新鮮度的差異。

