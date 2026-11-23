---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/How_to_handle_rate_limits.ipynb
---
# 如何處理 rate limit

> 原文：[examples/How_to_handle_rate_limits.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_handle_rate_limits.ipynb)



## 這篇在做什麼

重複呼叫 OpenAI API 時，常會遇到 `429: 'Too Many Requests'` 或 `RateLimitError`，這是超過 API 的 rate limit 了。這篇整理怎麼避免和處理這類錯誤：exponential backoff 重試、退到備用模型、調整 `max_tokens`、主動加延遲，以及把多個任務 batch 進同一個 request。

## 學完你會

- 用 Tenacity、backoff 或自己寫的方式，幫 API 呼叫加上 random exponential backoff
- 調整 `max_tokens`、加固定延遲，讓批次處理的吞吐量貼近 rate limit 上限
- 用 Structured Outputs 把多個 prompt 合併成一個 request，減少 RPM 消耗

## 開跑前

需要 OpenAI API key，範例會真的呼叫 API。

---

重複呼叫 OpenAI API 時，可能會看到 `429: 'Too Many Requests'` 或 `RateLimitError` 的錯誤訊息，這些都是超過 API rate limit 造成的。

這份指南分享避免和處理 rate limit 錯誤的訣竅。

想看節流平行請求來避免 rate limit 錯誤的範例腳本，請看 [api_request_parallel_processor.py](https://github.com/openai/openai-cookbook/blob/main/examples/api_request_parallel_processor.py)。

## 為什麼要有 rate limit

Rate limit 是 API 的常見做法，原因有幾個。

- 第一，防止 API 被濫用。例如惡意的人可能用大量請求灌爆 API，想讓服務過載或中斷。設了 rate limit，OpenAI 就能擋掉這類行為。
- 第二，確保大家都能公平使用 API。如果某個人或組織送出過多請求，會拖慢所有其他人。限制單一使用者的請求量，讓每個人都能順暢使用。
- 最後，rate limit 能幫 OpenAI 管理整體基礎設施的負載。如果 API 請求暴增，可能拖垮伺服器、造成效能問題。設定 rate limit 能讓所有使用者維持順暢一致的體驗。

雖然碰到 rate limit 很煩，但它是為了保護 API 能穩定運作。

## 預設的 rate limit

你的 rate limit 和花費上限（quota）會依多種因素自動調整。當你的 API 用量變多、也順利付清帳單，系統會自動提升你的用量等級（usage tier）。想知道 rate limit 的具體資訊，可以看下面的資源。

### 其他 rate limit 資源

想多了解 OpenAI 的 rate limit，可以看這些資源：

- [Guide: Rate limits](https://platform.openai.com/docs/guides/rate-limits?context=tier-free)
- [Help Center: Is API usage subject to any rate limits?](https://help.openai.com/en/articles/5955598-is-api-usage-subject-to-any-rate-limits)
- [Help Center: How can I solve 429: 'Too Many Requests' errors?](https://help.openai.com/en/articles/5955604-how-can-i-solve-429-too-many-requests-errors)

### 申請提高 rate limit

想了解怎麼提升組織的用量等級和 rate limit，到你的 [Limits 設定頁](https://platform.openai.com/account/limits)。

```python
import openai
import os

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))
```

## Rate limit 錯誤範例

API 請求送太快就會出現 rate limit 錯誤。如果用 OpenAI Python library，看起來會像這樣：

```
RateLimitError: Rate limit reached for default-codex in organization org-{id} on requests per min. Limit: 20.000000 / min. Current: 24.000000 / min. Contact support@openai.com if you continue to have issues or if you’d like to request an increase.
```

下面是觸發 rate limit 錯誤的範例程式。

```python
# request a bunch of completions in a loop
for _ in range(100):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
        max_tokens=10,
    )
```

??? note "輸出"

    ```text
    RateLimitError: Error code: 429 - {'error': {'message': 'You exceeded your current quota, please check your plan and billing details. For more information on this error, read the docs: https://platform.openai.com/docs/guides/error-codes/api-errors.', 'type': 'insufficient_quota', 'param': None, 'code': 'insufficient_quota'}}
    ```

## 怎麼減少 rate limit 錯誤

### 用 exponential backoff 重試

減少 rate limit 錯誤的一個簡單做法，是用 random exponential backoff 自動重試。意思是碰到 rate limit 錯誤時先短暫 sleep，再重試失敗的請求。如果還是失敗，就拉長 sleep 時間再重複，直到成功或達到最大重試次數。

這個做法有很多好處：

- 自動重試讓你從 rate limit 錯誤恢復，不會 crash 也不會漏資料
- Exponential backoff 讓最前面的重試可以很快，如果前幾次都失敗，後面再享受更長的延遲
- 在延遲加上隨機 jitter，可以避免所有重試同時撞在一起

注意失敗的請求也會算進你每分鐘的上限，所以一直重送是沒用的。

下面是幾種範例做法。

#### 範例 1：用 Tenacity library

[Tenacity](https://tenacity.readthedocs.io/en/latest/) 是 Apache 2.0 授權、用 Python 寫的通用重試函式庫，讓你幫幾乎任何東西加上重試行為。

要幫請求加 exponential backoff，可以用 `tenacity.retry` 這個 [decorator](https://peps.python.org/pep-0318/)。下面的例子用 `tenacity.wait_random_exponential` 函式幫請求加上 random exponential backoff。

注意 Tenacity 是第三方工具，OpenAI 不保證它的可靠性或安全性。

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)  # for exponential backoff

@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def completion_with_backoff(**kwargs):
    return client.chat.completions.create(**kwargs)


completion_with_backoff(model="gpt-4o-mini", messages=[{"role": "user", "content": "Once upon a time,"}])
```

??? note "輸出"

    ```text
    ChatCompletion(id='chatcmpl-8PAu6anX2JxQdYmJRzps38R8u0ZBC', choices=[Choice(finish_reason='stop', index=0, message=ChatCompletionMessage(content='in a small village nestled among green fields and rolling hills, there lived a kind-hearted and curious young girl named Lily. Lily was known for her bright smile and infectious laughter, bringing joy to everyone around her.\n\nOne sunny morning, as Lily played in the meadows, she stumbled upon a mysterious book tucked away beneath a tall oak tree. Intrigued, she picked it up and dusted off its weathered cover to reveal intricate golden patterns. Without hesitation, she opened it, discovering that its pages were filled with magical tales and enchanting adventures.\n\nAmong the stories she found, one particularly caught her attention—a tale of a long-lost treasure hidden deep within a mysterious forest. Legend had it that whoever found this hidden treasure would be granted one wish, no matter how big or small. Excited by the prospect of finding such treasure and fulfilling her wildest dreams, Lily decided to embark on a thrilling journey to the forest.\n\nGathering her courage, Lily told her parents about the magical book and her quest to find the hidden treasure. Though concerned for their daughter\'s safety, they couldn\'t help but admire her spirit and determination. They hugged her tightly and blessed her with love and luck, promising to await her return.\n\nEquipped with a map she found within the book, Lily ventured into the depths of the thick forest. The trees whispered tales of forgotten secrets, and the enchanted creatures hidden within watched her every step. But Lily remained undeterred, driven by her desire to discover what lay ahead.\n\nDays turned into weeks as Lily traversed through dense foliage, crossed swift rivers, and climbed treacherous mountains. She encountered mystical beings who offered guidance and protection along her perilous journey. With their help, she overcame countless obstacles and grew braver with each passing day.\n\nFinally, after what felt like an eternity, Lily reached the heart of the forest. There, beneath a jeweled waterfall, she found the long-lost treasure—a magnificent chest adorned with sparkling gemstones. Overwhelmed with excitement, she gently opened the chest to reveal a brilliant light that illuminated the forest.\n\nWithin the glow, a wise voice echoed, "You have proven your courage and pure heart, young Lily. Make your wish, and it shall be granted."\n\nLily thought deeply about her wish, realizing that her true treasure was the love and happiness she felt in her heart. Instead of making a wish for herself, she asked for the wellbeing and prosperity of her village, spreading joy and harmony to everyone living there.\n\nAs the light faded, Lily knew her quest was complete. She retraced her steps through the forest, returning home to find her village flourishing. Fields bloomed with vibrant flowers, and laughter filled the air.\n\nThe villagers greeted Lily with open arms, recognizing her selflessness and the magic she had brought into their lives. From that day forward, they told the tale of Lily\'s journey, celebrating her as a heroine who embodied the power of love, kindness, and the belief that true treasure lies within oneself.\n\nAnd so, the story of Lily became an everlasting legend, inspiring generations to follow their dreams, be selfless, and find the true treasures that lie within their hearts.', role='assistant', function_call=None, tool_calls=None))], created=1701010806, model='gpt-3.5-turbo-0613', object='chat.completion', system_fingerprint=None, usage=CompletionUsage(completion_tokens=641, prompt_tokens=12, total_tokens=653))
    ```

#### 範例 2：用 backoff library

另一個提供 backoff 和重試 decorator 的函式庫是 [backoff](https://pypi.org/project/backoff/)。

跟 Tenacity 一樣，backoff 也是第三方工具，OpenAI 不保證它的可靠性或安全性。

```python
import backoff  # for exponential backoff

@backoff.on_exception(backoff.expo, openai.RateLimitError, max_time=60, max_tries=6)
def completions_with_backoff(**kwargs):
    return client.chat.completions.create(**kwargs)


completions_with_backoff(model="gpt-4o-mini", messages=[{"role": "user", "content": "Once upon a time,"}])
```

??? note "輸出"

    ```text
    ChatCompletion(id='chatcmpl-AqRiD3gF3q8VVs6w8jgba6FHGr0L5', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content="in a small village nestled between lush green hills and a shimmering lake, there lived a young girl named Elara. Elara had a curious spirit and a heart full of dreams. Every day, she would explore the woods surrounding her home, searching for hidden treasures and magical creatures.\n\nOne sunny afternoon, while wandering deeper into the forest than she ever had before, Elara stumbled upon a sparkling, crystal-clear pond. As she knelt down to take a closer look, she noticed a glimmering object at the bottom. It was a beautifully crafted key, shining with an otherworldly light. Without thinking twice, Elara reached into the cool water and retrieved the key, feeling a strange warmth envelop her.\n\nLittle did she know, this key was no ordinary key. It was said to unlock a secret door hidden in the heart of the forest, a door that led to a realm of wonder and adventure. Legends whispered of enchanted beings, ancient wisdom, and challenges that could only be overcome through bravery and kindness.\n\nExcited by the possibility of what awaited her, Elara set off on a quest to find the hidden door. Guided by a faint glow that seemed to beckon her, she journeyed through twisting pathways, lush groves, and enchanted glades.\n\nAlong the way, she encountered talking animals, wise old trees, and mischievous fairies, each offering clues and riddles that tested her resolve and imagination. With each challenge she faced, Elara grew stronger and more confident, realizing that the true magic lay not just in the world around her, but within herself.\n\nAfter what felt like days of exploring, she finally found the door—a majestic archway covered in vines and blossoms, with a keyhole that sparkled like the night sky. Heart pounding with excitement, Elara inserted the key. With a gentle turn, the door slowly creaked open, revealing a land more breathtaking than she could have ever imagined.\n\nAs she stepped through the doorway, she found herself in a vibrant world filled with colors beyond description, where the sky shimmered in hues of gold and lavender, and the air was filled with the sweet scent of flowers that sang as they swayed in the breeze. Here, she encountered beings of light who welcomed her with open arms.\n\nBut soon, she discovered that this realm was in peril. A dark shadow loomed over the land, threatening to steal its magic and joy. Elara knew she couldn’t stand by and do nothing. With the friends she had made along her journey and the courage she had found within herself, she set out to confront the darkness.\n\nThrough trials that tested her strength, intellect, and compassion, Elara and her friends gathered the forgotten magic of the realm. They united their powers, confronting the shadow in an epic battle of light and dark. In the end, it was Elara's unwavering belief in hope and friendship that banished the darkness, restoring peace and harmony to the land.\n\nGrateful for her bravery, the beings of light gifted Elara a shimmering pendant that would allow her to return to their world whenever she wished, reminding her that true magic lies in the connections we forge with others and the courage to follow our dreams.\n\nWith her heart full of joy, Elara returned to her village, forever changed by her adventure. She would often revisit the magical realm, sharing stories with her friends and inspiring them to embrace their own dreams. And so, the girl who once wandered the woods became a beacon of hope, a reminder that within every heart lies the power to change the world.\n\nAnd from that day on, the little village thrived, full of laughter, love, and dreams waiting to be explored—each adventure beginning just like hers, with a curious heart and a willingness to believe in the impossible. \n\nThe end.", refusal=None, role='assistant', audio=None, function_call=None, tool_calls=None), internal_metrics=[{'cached_prompt_tokens': 0, 'total_accepted_tokens': 0, 'total_batched_tokens': 794, 'total_predicted_tokens': 0, 'total_rejected_tokens': 0, 'total_tokens_in_completion': 795, 'cached_embeddings_bytes': 0, 'cached_embeddings_n': 0, 'uncached_embeddings_bytes': 0, 'uncached_embeddings_n': 0, 'fetched_embeddings_bytes': 0, 'fetched_embeddings_n': 0, 'n_evictions': 0, 'sampling_steps': 767, 'sampling_steps_with_predictions': 0, 'batcher_ttft': 0.20319080352783203, 'batcher_initial_queue_time': 0.12981152534484863}])], created=1737062945, model='gpt-4o-mini-2024-07-18', object='chat.completion', service_tier='default', system_fingerprint='fp_72ed7ab54c', usage=CompletionUsage(completion_tokens=767, prompt_tokens=12, total_tokens=779, completion_tokens_details=CompletionTokensDetails(accepted_prediction_tokens=0, audio_tokens=0, reasoning_tokens=0, rejected_prediction_tokens=0), prompt_tokens_details=PromptTokensDetails(audio_tokens=0, cached_tokens=0, cached_tokens_internal=0)))
    ```

#### 範例 3：自己實作 backoff

如果不想用第三方函式庫，可以自己寫 backoff 邏輯。

```python
# imports
import random
import time

# define a retry decorator
def retry_with_exponential_backoff(
    func,
    initial_delay: float = 1,
    exponential_base: float = 2,
    jitter: bool = True,
    max_retries: int = 10,
    errors: tuple = (openai.RateLimitError,),
):
    """Retry a function with exponential backoff."""

    def wrapper(*args, **kwargs):
        # Initialize variables
        num_retries = 0
        delay = initial_delay

        # Loop until a successful response or max_retries is hit or an exception is raised
        while True:
            try:
                return func(*args, **kwargs)

            # Retry on specified errors
            except errors as e:
                # Increment retries
                num_retries += 1

                # Check if max retries has been reached
                if num_retries > max_retries:
                    raise Exception(
                        f"Maximum number of retries ({max_retries}) exceeded."
                    )

                # Increment the delay
                delay *= exponential_base * (1 + jitter * random.random())

                # Sleep for the delay
                time.sleep(delay)

            # Raise exceptions for any errors not specified
            except Exception as e:
                raise e

    return wrapper


@retry_with_exponential_backoff
def completions_with_backoff(**kwargs):
    return client.chat.completions.create(**kwargs)


completions_with_backoff(model="gpt-4o-mini", messages=[{"role": "user", "content": "Once upon a time,"}])
```

??? note "輸出"

    ```text
    ChatCompletion(id='chatcmpl-8PAxGvV3GbLpnOoKSvJ00XCUdOglM', choices=[Choice(finish_reason='stop', index=0, message=ChatCompletionMessage(content="in a faraway kingdom, there lived a young princess named Aurora. She was known for her beauty, grace, and kind heart. Aurora's kingdom was filled with lush green meadows, towering mountains, and sparkling rivers. The princess loved spending time exploring the enchanting forests surrounding her castle.\n\nOne day, while Aurora was wandering through the woods, she stumbled upon a hidden clearing. At the center stood a majestic oak tree, its branches reaching towards the sky. Aurora approached the tree with curiosity, and as she got closer, she noticed a small door at its base.\n\nIntrigued, she gently pushed open the door and was amazed to find herself in a magical realm. The forest transformed into a breathtaking wonderland, with colorful flowers blooming in every direction and woodland creatures frolicking joyously. Aurora's eyes widened with wonder as she explored this extraordinary world.\n\nAs she explored further, Aurora came across a small cottage in the distance. Curiosity overcame her, and she cautiously approached the cottage. To her surprise, an elderly woman with twinkling eyes and a warm smile stood in the doorway, welcoming her inside.\n\nThe woman revealed herself to be a fairy named Luna. Luna informed Aurora that she had been chosen to undertake a quest that would bring harmony to both her kingdom and the mystical realm. Aurora, eager to help, listened intently as Luna explained that a powerful enchantress had cast a spell on the kingdom, causing darkness and despair to loom over the land.\n\nTo break the curse, Aurora had to embark on a journey to retrieve a magical crystal hidden deep within the heart of an ancient cave. Without hesitation, the princess agreed and bid farewell to Luna, promising to return victorious.\n\nWith newfound determination, Aurora set off on her quest. Along the way, she encountered numerous challenges and obstacles but never lost hope. She often drew strength from the enchanting woodland creatures who accompanied her on this journey, reminding her that she was not alone.\n\nAfter a long and arduous journey, Aurora reached the entrance of the ancient cave. Inside, she faced a series of tests that pushed her physical and emotional limits. With sheer determination and unwavering courage, she overcame each trial, paving her way to the crystal's resting place.\n\nAs Aurora held the crystal in her hands, its warmth spread through her body. The artifact contained unimaginable power that could shatter the enchantress's curse and restore light to her kingdom. Brimming with joy and newfound strength, she made her way back to Luna's cottage.\n\nUpon her return, Aurora and Luna performed a powerful ritual, using the crystal's magic to break the curse. Waves of light and color spread across the kingdom, banishing darkness and despair. The once-gray skies turned blue, and laughter filled the air once again. The kingdom rejoiced, thanking Princess Aurora for her bravery and selflessness.\n\nFrom that day forward, Aurora was hailed as a hero, not only in her kingdom but also in the mystical realm. She continued to be a beacon of hope and kindness, reminding everyone that true courage lies within, waiting to be awakened.\n\nAnd so, Princess Aurora's tale lived on as a timeless reminder that even in the darkest of times, there is always light and hope to be found.", role='assistant', function_call=None, tool_calls=None))], created=1701011002, model='gpt-3.5-turbo-0613', object='chat.completion', system_fingerprint=None, usage=CompletionUsage(completion_tokens=657, prompt_tokens=12, total_tokens=669))
    ```

### 退到另一個模型

如果主要模型碰到 rate limit 錯誤，一個選擇是改用次要模型。這樣在主要模型被限流或無法使用時，應用還是能保持回應。

不過備用模型在準確度、延遲和成本上可能差很多，所以這個策略不見得適合所有情境，特別是需要高度一致結果的。另外，有些模型共用 rate limit，單純換模型的效果可能有限。你可以在[組織的 limit 頁面](https://platform.openai.com/settings/organization/limits)看到哪些模型共用額度。

上線前，要徹底測試這個做法對輸出品質、使用者體驗和營運預算的影響。用相關的 eval 驗證你的備援方案，確保在真實情況下仍符合需求、效能可接受。

```python
def completions_with_fallback(fallback_model, **kwargs):
    try:
        return client.chat.completions.create(**kwargs)
    except openai.RateLimitError:
        kwargs['model'] = fallback_model
        return client.chat.completions.create(**kwargs)
    
    
completions_with_fallback(fallback_model="gpt-4o", model="gpt-4o-mini", messages=[{"role": "user", "content": "Once upon a time,"}])
```

??? note "輸出"

    ```text
    ChatCompletion(id='chatcmpl-AsX9Zts2toXoKA80ZujeWMXKMolBy', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content='in a quaint little village nestled between lush green hills and sparkling blue rivers, there lived a young girl named Elara. Elara was known for her adventurous spirit and her unwavering curiosity about the world beyond her village. She often spent her days wandering the meadows, exploring the enchanted forest, and collecting wildflowers.\n\nOne sunny afternoon, while she was picking daisies near the edge of the forest, Elara stumbled upon an old, ornate key half-buried in the ground. Intrigued, she dusted it off and inspected it closely. The key was beautifully crafted, with intricate patterns carved into its metal. Elara felt a strange pull towards it, as if it were meant for her.\n\nDetermined to uncover its secrets, Elara ran back to the village, her heart racing with excitement. She gathered her closest friends—Jasper, a clever boy with a knack for puzzles, and Lila, a brave girl who loved to climb trees—and shared her discovery with them.\n\n"Do you think it belongs to a hidden treasure?" Jasper wondered, his eyes sparkling with mischief.\n\n"Or perhaps a secret door!" Lila added, her imagination running wild.\n\nTogether, they decided to seek out the source of the key. They combed through old tales told by the village elders, searching for any clues about a hidden door or treasure nearby. After days of excitement and exploration, they stumbled upon an ancient map tucked away in an old library. The map illustrated a long-lost castle deep within the enchanted forest, rumored to have been abandoned for centuries.\n\nWith the map in hand and their imaginations ignited, Elara, Jasper, and Lila set off towards the castle. The journey through the enchanted forest was filled with wonders—glowing fireflies, singing birds, and trees that seemed to whisper secrets as the wind rustled through their leaves. Eventually, they reached the castle, its crumbling walls draped in vines and mysterious shadows.\n\nStanding before the grand entrance, Elara held the key tightly in her hand. "This is it," she whispered, her heart pounding in anticipation. The friends exchanged nervous glances but shared the thrill of adventure. Together, they pushed open the heavy door, which creaked eerily as it swung wide.\n\nInside, they found a majestic hall adorned with fading tapestries and dust-laden chandeliers. In the center of the room stood a locked chest, adorned with the same intricate patterns as the key. Elara knelt beside it, her friends gathering around as she inserted the key into the lock. With a satisfying click, the chest opened to reveal a trove of shimmering jewels, ancient scrolls, and forgotten treasures.\n\nBut among the riches, they discovered something even more valuable—an old book filled with stories of bravery, friendship, and magic. As they turned the pages, each story seemed to echo their own journey and the spirit of adventure that had led them to this moment.\n\nElara, Jasper, and Lila realized that the true treasure was not the jewels or gold, but the experiences they had shared and the bond they had formed through their journey. They decided to take the book back to their village and share its tales with everyone, inspiring others to seek their own adventures and explore the wonders of the world around them.\n\nFrom that day forward, the trio became known as the Keepers of the Forest, guardians of the stories that connected their village to the magic of the enchanted world. And as they continued their adventures, they learned that the real magic lay within their hearts and the friendships they cherished. \n\nAnd so, they lived happily ever after, their spirits forever intertwined in a tapestry of tales waiting to be told.', refusal=None, role='assistant', audio=None, function_call=None, tool_calls=None), internal_metrics=[{'cached_prompt_tokens': 0, 'total_accepted_tokens': 0, 'total_batched_tokens': 774, 'total_predicted_tokens': 0, 'total_rejected_tokens': 0, 'total_tokens_in_completion': 775, 'cached_embeddings_bytes': 0, 'cached_embeddings_n': 0, 'uncached_embeddings_bytes': 0, 'uncached_embeddings_n': 0, 'fetched_embeddings_bytes': 0, 'fetched_embeddings_n': 0, 'n_evictions': 0, 'sampling_steps': 747, 'sampling_steps_with_predictions': 0, 'batcher_ttft': 0.08919167518615723, 'batcher_initial_queue_time': 0.008681058883666992}])], created=1737560517, model='gpt-4o-mini-2024-07-18', object='chat.completion', service_tier='default', system_fingerprint='fp_72ed7ab54c', usage=CompletionUsage(completion_tokens=747, prompt_tokens=12, total_tokens=759, completion_tokens_details=CompletionTokensDetails(accepted_prediction_tokens=0, audio_tokens=0, reasoning_tokens=0, rejected_prediction_tokens=0), prompt_tokens_details=PromptTokensDetails(audio_tokens=0, cached_tokens=0, cached_tokens_internal=0)))
    ```

### 把 `max_tokens` 降到接近預期的回應長度

Rate limit 用量是取下面兩者中較大的來算：
1. `max_tokens`：回應最多允許的 token 數。
2. 輸入的估計 token 數：由 prompt 的字元數推算。

如果 `max_tokens` 設太高，即使實際回應短很多，用量也會被高估。為了避免太早撞到 rate limit，把 `max_tokens` 設成接近預期的回應大小，這樣用量計算比較準，也能避免不必要的限流。

```python
def completions_with_max_tokens(**kwargs):
    return client.chat.completions.create(**kwargs)


completions_with_max_tokens(model="gpt-4o-mini", messages=[{"role": "user", "content": "Once upon a time,"}], max_tokens=100)
```

??? note "輸出"

    ```text
    ChatCompletion(id='chatcmpl-Aq0JmjugPw2i232ZEZuK5inHnx6Vc', choices=[Choice(finish_reason='length', index=0, logprobs=None, message=ChatCompletionMessage(content='in a small village nestled between lush green hills and a sparkling river, there lived a young girl named Lila. Lila was known for her boundless curiosity and adventurous spirit. She had a wild imagination, often spinning tales about the mysteries that lay beyond the village borders.\n\nOne day, while exploring the forest, Lila stumbled upon a hidden path she had never seen before. The path was winding and overgrown, beckoning her with whispers of adventure. Against her better judgment, she decided to', refusal=None, role='assistant', audio=None, function_call=None, tool_calls=None), internal_metrics=[{'cached_prompt_tokens': 0, 'total_accepted_tokens': 0, 'total_batched_tokens': 127, 'total_predicted_tokens': 0, 'total_rejected_tokens': 0, 'total_tokens_in_completion': 128, 'cached_embeddings_bytes': 0, 'cached_embeddings_n': 0, 'uncached_embeddings_bytes': 0, 'uncached_embeddings_n': 0, 'fetched_embeddings_bytes': 0, 'fetched_embeddings_n': 0, 'n_evictions': 0, 'sampling_steps': 100, 'sampling_steps_with_predictions': 0, 'batcher_ttft': 0.030033111572265625, 'batcher_initial_queue_time': 0.0006170272827148438}])], created=1736957642, model='gpt-4o-mini-2024-07-18', object='chat.completion', service_tier='default', system_fingerprint='fp_bd83329f63', usage=CompletionUsage(completion_tokens=100, prompt_tokens=12, total_tokens=112, completion_tokens_details=CompletionTokensDetails(accepted_prediction_tokens=0, audio_tokens=0, reasoning_tokens=0, rejected_prediction_tokens=0), prompt_tokens_details=PromptTokensDetails(audio_tokens=0, cached_tokens=0, cached_tokens_internal=0)))
    ```

## 有 rate limit 時，怎麼讓批次處理的吞吐量最大

如果你在處理使用者的即時請求，backoff 加重試是降低延遲、又避免 rate limit 錯誤的好策略。

但如果你在處理大量批次資料，吞吐量比延遲重要，除了 backoff 和重試，還有幾件事可以做。

### 主動在請求之間加延遲

如果你一直撞到 rate limit，然後 backoff，又撞到，再 backoff，那你的請求額度有一大部分可能浪費在需要重試的請求上。在固定的 rate limit 下，這會限制處理吞吐量。

這裡一個可行的做法，是算出你的 rate limit，加上等於它倒數的延遲（例如 rate limit 是每分鐘 20 個請求，每個請求加 3 到 6 秒的延遲）。這樣可以貼著 rate limit 上限運作又不會撞到，也避免浪費請求。

#### 幫請求加延遲的範例

```python
import time

# Define a function that adds a delay to a Completion API call
def delayed_completion(delay_in_seconds: float = 1, **kwargs):
    """Delay a completion by a specified amount of time."""

    # Sleep for the delay
    time.sleep(delay_in_seconds)

    # Call the Completion API and return the result
    return client.chat.completions.create(**kwargs)


# Calculate the delay based on your rate limit
rate_limit_per_minute = 20
delay = 60.0 / rate_limit_per_minute

delayed_completion(
    delay_in_seconds=delay,
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Once upon a time,"}]
)
```

??? note "輸出"

    ```text
    ChatCompletion(id='chatcmpl-8PAyCR1axKsomV0e349XiCN1Z81pH', choices=[Choice(finish_reason='stop', index=0, message=ChatCompletionMessage(content="in a small village, there lived a young girl named Maya. Maya was known for her kindness and love for nature. She spent hours exploring the forests surrounding the village, admiring the vibrant flowers and talking to the animals.\n\nOne sunny day, as Maya was picking wildflowers, she stumbled upon a wounded blackbird with a broken wing. Feeling sorry for the bird, Maya gently picked it up and cradled it in her hands. She knew she had to help the bird, so she hurried back to her cottage.\n\nMaya set up a cozy nest for the blackbird and carefully splinted its wing. She fed it worms and berries, doing everything she could to nurse it back to health. Each day, she would sing lullabies and tell stories to keep the blackbird company. Slowly, the bird's wing healed, and before long, it was ready to fly again.\n\nOn a beautiful morning, Maya opened the window of her cottage and released the blackbird into the sky. As the bird soared into the air, Maya's heart filled with joy and gratitude. Little did she know, this act of kindness would change her life forever.\n\nThe following night, a mysterious glowing light illuminated Maya's room. Startled, she sat up and saw a magical creature standing before her. It was a fairy, tiny yet radiating warmth and light.\n\nThe fairy introduced herself as Luna, the Guardian of the Forest. She had witnessed Maya's kindness towards the blackbird and had been watching her ever since. Luna explained that she had come to reward Maya for her selflessness.\n\nWith a wave of her wand, Luna granted Maya the ability to communicate with animals. Maya's eyes widened with amazement as she realized she could now understand the language of nature. Birds chirped melodies, rabbits whispered secrets, and trees shared their ancient wisdom.\n\nOver time, Maya's ability made her beloved by both humans and animals. Farmers sought her advice on how to care for their crops, and children flocked to her for stories of her enchanting encounters with the forest creatures. Maya used her gift to teach others about the importance of living in harmony with nature.\n\nAs years passed, Maya became known as the Village Guardian. She dedicated herself to protecting the surrounding forests from harm and educating others on sustainable living. The village flourished under Maya's guidance, and animals and humans lived side by side peacefully.\n\nAnd so, Maya's story became a legend passed down through generations. Her kindness, love for nature, and her ability to communicate with animals inspired people to treat the world around them with compassion and care.", role='assistant', function_call=None, tool_calls=None))], created=1701011060, model='gpt-3.5-turbo-0613', object='chat.completion', system_fingerprint=None, usage=CompletionUsage(completion_tokens=524, prompt_tokens=12, total_tokens=536))
    ```

### Batch 請求

OpenAI API 對每分鐘/每天請求數（RPM/RPD）和每分鐘 token 數（TPM）有各自的限制。如果你撞到的是 RPM，但 TPM 還有空間，可以考慮把多個任務 batch 進同一個請求。

把幾個 prompt 綁在一起，每分鐘送出的請求總數就變少，有助於避開 RPM 上限。如果你小心管理 TPM 用量，整體吞吐量也可能更高。不過要注意幾點：
- 每個模型單次請求能處理的 token 數有上限。batch 後的 prompt 超過上限，請求會失敗或被截斷。
- 如果任務要等到湊成一個請求才送，batch 可能增加額外等待時間，對時效性高的應用會影響使用者體驗。
- 送多個 prompt 時，回應物件的順序或格式可能跟送出的 prompt 不一致。你要試著在後處理輸出時，把每個回應對回對應的 prompt。

#### 沒有 batch 的範例

```python
num_stories = 10
content = "Once upon a time,"

# serial example, with one story completion per request
for _ in range(num_stories):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": content}],
        max_tokens=20,
    )

    print(content + response.choices[0].message.content)
```

??? note "輸出"

    ```text
    Once upon a time,in a quaint little village nestled between rolling hills and a sparkling river, there lived a young girl named
    Once upon a time,Once upon a time, in a tranquil village nestled between rolling hills and lush forests, there lived a
    Once upon a time,in a lush, green valley surrounded by towering mountains, there lay a small village called Eldergrove
    Once upon a time,in a quaint little village nestled between rolling hills and a sparkling river, there lived a young girl named
    Once upon a time,in a small village nestled between whispering woods and a sparkling river, there lived a curious young girl
    Once upon a time,in a small village nestled between a vast forest and a shimmering lake, there lived a kind-hearted girl
    Once upon a time,in a quaint little village nestled between rolling hills and a shimmering lake, there lived a curious girl named
    Once upon a time,in a quaint little village nestled between emerald hills and a sparkling brook, there was a curious child named
    Once upon a time,in a quaint little village nestled between rolling hills and lush forests, there lived an old clockmaker named
    Once upon a time,in a quaint little village nestled between rolling hills and a shimmering lake, there lived a curious young girl
    ```

#### 用 Structured Outputs 把多個 prompt 合進單一請求的範例

OpenAI 的 [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs) 功能讓你能把多個 prompt batch 進一個請求。

不用解析原始文字，也不用靠非正式的格式，直接指定嚴格的 schema。Structured Outputs 會強制符合這個結構，減少解析和結構驗證的工作。應用程式碼還是得驗證商業規則和每個值的意義。

```python
from pydantic import BaseModel

# Define the Pydantic model for the structured output
class StoryResponse(BaseModel):
    stories: list[str]
    story_count: int

num_stories = 10
content = "Once upon a time,"

prompt_lines = [f"Story #{i+1}: {content}" for i in range(num_stories)]
prompt_text = "\n".join(prompt_lines)

messages = [
    {
        "role": "developer",
        "content": "You are a helpful assistant. Please respond to each prompt as a separate short story."
    },
    {
        "role": "user",
        "content": prompt_text
    }
]

# batched example, with all story completions in one request and using structured outputs
response = client.beta.chat.completions.parse(
    model="gpt-4o-mini",
    messages=messages,
    response_format=StoryResponse,
)

print(response.choices[0].message.content)
```

??? note "輸出"

    ```text
    {"stories":["Once upon a time, in a lush green valley, there lived a curious little fox named Felix. Every day, he would explore the woods, finding hidden glades and sparkling streams. One day, while chasing a butterfly, he stumbled upon a magical oak tree that granted wishes. Felix wished for courage and became the bravest fox in the land, helping his friends as they faced challenges together.","Once upon a time, a village known for its beautiful gardens fell into despair when a drought struck. The villagers prayed for rain but to no avail. One evening, a wise old woman arrived and told them of a hidden spring deep in the forest. With hope, the villagers embarked on a quest to find it, learning the value of teamwork and perseverance. Eventually, they found the spring, and the rain returned, reviving their gardens and spirits.","Once upon a time, in a kingdom high atop the clouds, lived Princess Lumina who had the ability to control the stars. But she felt lonely and longed for a companion. One night, she captured a shooting star and transformed it into a dashing young man named Orion. Together, they painted the night skies with adventures until Lumina learned to find joy in her own light.","Once upon a time, in a bustling bazaar in the heart of the city, there lived a clever merchant named Amina. She had a special talent for selling spices that made people fall in love. One day, a mysterious stranger entered her shop and bought a rare spice, causing an unexpected romance between two feuding families. Amina realized her spices held the power of unity, and she continued to spread love through her trade.","Once upon a time, a little turtle named Tilly dreamed of flying. Every day she watched the birds soar above her, wishing she could join them. One night, she met an old owl who shared stories of how to fly in one's heart, rather than with wings. Inspired, Tilly began to paint her dreams on shells, and soon, her colorful art attracted the birds. They carried her art into the sky, proving that dreams can take flight in unexpected ways.","Once upon a time, there was a forgotten castle hidden deep in the mountains. In this castle lived an ancient dragon named Ignis, who guarded a treasure of wisdom unlike any other. One day, a brave yet naive knight named Roland attempted to seize the treasure. But Ignis offered him a riddle instead. After solving it, Roland realized that the true treasure was knowledge and understanding. He left the castle as a wiser man, sharing Ignis's teachings with his kingdom.","Once upon a time, in a world where colors had feelings, there lived a dull gray town where nobody smiled. One day, a little girl named Bloom arrived, carrying a bright yellow paintbrush. She began to paint laughter and joy on the walls. Slowly, the townspeople found happiness in her colors and learned to express their emotions. Eventually, the town transformed into a vibrant place where every day was a celebration of life.","Once upon a time, an old clockmaker named Mr. Tick was known for creating the finest clocks in the town. But his favorite creation was an enchanted clock that could tell stories of the past. One day, a little girl named Clara stumbled into his shop and begged him to tell her a story. Mr. Tick set the clock and took her on a journey through time, where Clara learned the importance of history and family. Inspired, she decided to become a storyteller.","Once upon a time, in a small fishing village, a mysterious blue whale appeared off the coast every summer. Legend had it that the whale could grant one wish to the person who dared to swim alongside it. A daring young boy named Leo decided to brave the waters. As he swam next to the majestic creature, he wished for prosperity for his village. From that day onward, the village thrived, and they celebrated the bond of friendship with the whale every summer.","Once upon a time, in a land of giants, there lived a tiny girl named Fiona. Despite her size, she had a heart full of ambition. She dreamt of building a bridge between her village and the giants’ realm to facilitate friendship. With determination and ingenuity, she crafted a plan. When the giants saw her efforts, they helped her, and together they constructed a magnificent bridge. Fiona's courage became a legend, and the two realms flourished in harmony."],"story_count":10}
    ```

## 平行處理腳本範例

我們寫了一個平行處理大量 API 請求的範例腳本：[api_request_parallel_processor.py](https://github.com/openai/openai-cookbook/blob/main/examples/api_request_parallel_processor.py)。

這個腳本結合了幾個好用的功能：
- 從檔案串流讀取請求，處理超大任務也不會記憶體不足
- 並行送請求，讓吞吐量最大
- 同時節流請求數和 token 用量，維持在 rate limit 以下
- 重試失敗的請求，避免漏資料
- 記錄錯誤，方便診斷請求的問題

可以直接用，也可以依需求修改。

## 重點整理

- 429 是因為請求太快，失敗的請求也會算進每分鐘額度，所以不能無腦重送。
- 即時請求用 exponential backoff 加 jitter 重試，jitter 避免大家同時重試。
- `max_tokens` 會算進 rate limit 用量，設得比預期回應大很多只是白白浪費額度。
- 批次處理要看吞吐量：主動加延遲讓請求貼近上限，RPM 吃緊就把多個 prompt batch 成一個請求。
- 備用模型要用 eval 驗證品質，而且有些模型共用額度，換了不一定有用。

## 練習

1. 把範例的 retry 次數上限和 `wait_random_exponential` 的 `max` 改一改，故意觸發 rate limit，觀察重試間隔怎麼變。
2. 把 `max_tokens` 從很大的值改成接近實際回應長度，比較用量差異。
3. 把「沒有 batch」的範例改成用 Structured Outputs 一次送多個 prompt，並寫程式把每個回答對回原本的 prompt。
