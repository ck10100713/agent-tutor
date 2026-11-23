---
translated: true
source: examples/How_to_use_guardrails.ipynb
---
# 如何實作 LLM guardrails

> 原文：[examples/How_to_use_guardrails.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_use_guardrails.ipynb)



## 這篇在做什麼

示範怎麼替 LLM 應用加上 guardrails：在輸入端用一個 `gpt-4o-mini` 判斷問題是不是離題，在輸出端用 G-Eval 風格的評分擋掉不適當的回答。同時也講設計 guardrail 時要怎麼在準確度、延遲和成本之間取捨。

## 學完你會

- 寫一個 topical guardrail，並用 async 讓它跟主 LLM 呼叫平行執行，被擋下時直接回罐頭訊息。
- 寫一個 moderation guardrail，用 domain、criteria、steps 讓 LLM 打 1 到 5 分，超過門檻就擋掉回答。
- 判斷 guardrail 的限制（prompt injection、長對話、over-refusal），並知道怎麼調整門檻和緩解。

## 開跑前

- 需要 OpenAI API key，guardrail 和主 LLM 都會呼叫模型，會產生費用。

在這份 notebook 裡，我們分享幾個替 LLM 應用實作 guardrails 的範例。guardrail 是一個通用詞，指的是用來引導應用行為的**偵測型控制（detective controls）**。LLM 本質上有隨機性，所以需要更高的可控性很常見，因此做出有效的 guardrails，成了把 LLM 從原型推向正式環境時最常見的效能最佳化方向之一。

Guardrails 的種類非常[多樣](https://github.com/NVIDIA/NeMo-Guardrails/blob/main/examples/README.md)，幾乎可以部署在任何你想得到 LLM 會出問題的情境。這份 notebook 想提供簡單的範例，讓你延伸去符合自己的使用情境，同時也說明在決定要不要實作 guardrail、以及怎麼實作時該考慮的取捨。

這份 notebook 會聚焦在：
1. **輸入 guardrails**：在不適當的內容進到 LLM 之前就先標記起來
2. **輸出 guardrails**：在 LLM 的產出送到客戶面前之前先驗證

**注意：** 這份 notebook 把 guardrails 當成圍繞 LLM 的偵測型控制的通稱。如果你要找提供現成 guardrails 框架的正式函式庫，可以看：
- [NeMo Guardrails](https://github.com/NVIDIA/NeMo-Guardrails/tree/main)
- [Guardrails AI](https://github.com/ShreyaR/guardrails)


```python
import openai

GPT_MODEL = 'gpt-4o-mini'
```

## 1. 輸入 guardrails

輸入 guardrails 的目標是從源頭阻止不適當的內容進到 LLM，常見的用途有：
- **主題 guardrails（topical）：** 辨識使用者問了離題的問題，並告訴他 LLM 能協助哪些主題。
- **Jailbreaking：** 偵測使用者想劫持 LLM、覆蓋它原本的 prompt。
- **Prompt injection：** 抓出使用者想藏惡意程式碼的情況，這些程式碼會在 LLM 執行的下游函式裡被執行。

這些情況下，guardrail 都是預防型控制，在 LLM 之前或與 LLM 平行執行，一旦符合其中一項條件，就觸發應用改變行為。

### 設計一個 guardrail

設計 guardrails 時，要考慮**準確度**、**延遲**和**成本**之間的取捨，目標是在對獲利和使用者體驗影響最小的前提下，達到最高的準確度。

我們先從一個簡單的 **topical guardrail** 開始，它負責偵測離題的問題，一旦觸發就阻止 LLM 回答。這個 guardrail 只有一個簡單的 prompt，用的是 `gpt-4o-mini`，在準確度夠好的前提下把延遲和成本壓到最低。如果想進一步最佳化，可以考慮：
- **準確度：** 可以考慮 fine-tune `gpt-4o-mini` 或加 few-shot 範例來提高準確度。如果你有一份能幫助判斷內容是否允許的資料，RAG 也會有效。
- **延遲/成本：** 可以試著 fine-tune 更小的模型，例如 `babbage-002`，或是 Llama 這類開源模型，給足夠的訓練範例時表現可以很好。用開源模型時，也可以調整推論用的機器，把成本或延遲壓到最低。

這個簡單的 guardrail 要確保 LLM 只回答預先定義的主題，對超出範圍的問題就回一則罐頭訊息。

### 擁抱 async

降低延遲的常見設計，是把 guardrails 和主要的 LLM 呼叫一起非同步送出。如果 guardrail 被觸發，就回傳它的回應，否則就回傳 LLM 的回應。

我們會用這個做法，建立一個 `execute_chat_with_guardrails` 函式，讓它平行執行 LLM 的 `get_chat_response` 和 `topical_guardrail` guardrail，只有在 guardrail 回傳 `allowed` 時才回傳 LLM 的回應。

### 限制

開發設計時，一定要考慮 guardrails 的限制。幾個要注意的重點：
- 用 LLM 當 guardrail 時，要知道它們和你的基礎 LLM 呼叫有一樣的弱點。例如 **prompt injection** 的嘗試可能同時繞過你的 guardrail 和實際的 LLM 呼叫。
- 對話越長，LLM 越容易被 **jailbreak**，因為你的指示會被多出來的文字稀釋。
- 如果為了彌補上述問題把 guardrails 設得太嚴格，就會傷害使用者體驗。具體表現是 **over-refusal**：guardrails 因為某些無害的請求跟 prompt injection 或 jailbreak 嘗試有相似之處，就把它拒絕了。

### 緩解方式

如果能把 guardrails 結合規則式或比較傳統的機器學習模型來做偵測，可以降低一部分風險。我們也看過有客戶讓 guardrails 只看最新一則訊息，以降低模型被長對話搞混的風險。

我們也建議逐步上線，並主動監控對話，這樣才能抓到 prompt injection 或 jailbreak 的案例，然後再加更多 guardrails 來涵蓋這些新的行為類型，或是把它們當成訓練範例加進現有的 guardrails。

```python
system_prompt = "You are a helpful assistant."

bad_request = "I want to talk about horses"
good_request = "What are the best breeds of dog for people that like cats?"
```

```python
import asyncio


async def get_chat_response(user_request):
    print("Getting LLM response")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
    response = openai.chat.completions.create(
        model=GPT_MODEL, messages=messages, temperature=0.5
    )
    print("Got LLM response")

    return response.choices[0].message.content


async def topical_guardrail(user_request):
    print("Checking topical guardrail")
    messages = [
        {
            "role": "system",
            "content": "Your role is to assess whether the user question is allowed or not. The allowed topics are cats and dogs. If the topic is allowed, say 'allowed' otherwise say 'not_allowed'",
        },
        {"role": "user", "content": user_request},
    ]
    response = openai.chat.completions.create(
        model=GPT_MODEL, messages=messages, temperature=0
    )

    print("Got guardrail response")
    return response.choices[0].message.content


async def execute_chat_with_guardrail(user_request):
    topical_guardrail_task = asyncio.create_task(topical_guardrail(user_request))
    chat_task = asyncio.create_task(get_chat_response(user_request))

    while True:
        done, _ = await asyncio.wait(
            [topical_guardrail_task, chat_task], return_when=asyncio.FIRST_COMPLETED
        )
        if topical_guardrail_task in done:
            guardrail_response = topical_guardrail_task.result()
            if guardrail_response == "not_allowed":
                chat_task.cancel()
                print("Topical guardrail triggered")
                return "I can only talk about cats and dogs, the best animals that ever lived."
            elif chat_task in done:
                chat_response = chat_task.result()
                return chat_response
        else:
            await asyncio.sleep(0.1)  # sleep for a bit before checking the tasks again
```

```python
# Call the main function with the good request - this should go through
response = await execute_chat_with_guardrail(good_request)
print(response)
```

??? note "輸出"

    ```text
    Checking topical guardrail
    Got guardrail response
    Getting LLM response
    Got LLM response
    If you like cats and are considering getting a dog, there are several breeds known for their compatibility with feline friends. Here are some of the best dog breeds that tend to get along well with cats:

    1. **Golden Retriever**: Friendly and tolerant, Golden Retrievers often get along well with other animals, including cats.

    2. **Labrador Retriever**: Similar to Golden Retrievers, Labs are social and friendly, making them good companions for cats.

    3. **Cavalier King Charles Spaniel**: This breed is gentle and affectionate, often forming strong bonds with other pets.

    4. **Basset Hound**: Basset Hounds are laid-back and generally have a calm demeanor, which can help them coexist peacefully with cats.

    5. **Beagle**: Beagles are friendly and sociable, and they often enjoy the company of other animals, including cats.

    6. **Pug**: Pugs are known for their playful and friendly nature, which can make them good companions for cats.

    7. **Shih Tzu**: Shih Tzus are typically friendly and adaptable, often getting along well with other pets.

    8. **Collie**: Collies are known for their gentle and protective nature, which can extend to their relationships with cats.

    9. **Newfoundland**: These gentle giants are known for their calm demeanor and often get along well with other animals.

    10. **Cocker Spaniel**: Cocker Spaniels are friendly and affectionate dogs that can get along well with cats if introduced properly.

    When introducing a dog to a cat, it's important to do so gradually and supervise their interactions to ensure a positive relationship. Each dog's personality can vary, so individual temperament is key in determining compatibility.
    ```

```python
# Call the main function with the bad request - this should get blocked
response = await execute_chat_with_guardrail(bad_request)
print(response)
```

??? note "輸出"

    ```text
    Checking topical guardrail
    Got guardrail response
    Getting LLM response
    Got LLM response
    Topical guardrail triggered
    I can only talk about cats and dogs, the best animals that ever lived.
    ```

看起來 guardrail 有效：第一個問題被放行，第二個因為離題被擋下。接下來把這個概念延伸，也去審查 LLM 回傳的回應。

## 2. 輸出 guardrails

輸出 guardrails 管的是 LLM 回傳的內容。形式很多，最常見的有：
- **幻覺/事實查核 guardrails：** 用一份基準事實資料，或是一份幻覺回答的訓練集，來擋掉幻覺的回答。
- **內容審查 guardrails：** 套用品牌和公司準則來審查 LLM 的結果，一旦違反就擋掉或改寫回答。
- **語法檢查：** LLM 的結構化輸出可能壞掉、無法解析。這類 guardrails 會偵測這些情況，然後重試或優雅地失敗，避免下游應用出錯。
    - 這是 function calling 常用的控制，確保 LLM 回傳 `function_call` 時，`arguments` 裡是預期的 schema。
    
### Moderation guardrail

這裡我們實作一個 **moderation guardrail**，用 [G-Eval](https://arxiv.org/abs/2303.16634) 評估方法的一個版本，替 LLM 回應裡出現不想要內容的程度打分數。這個方法在我們另一份 [notebook](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/How_to_eval_abstractive_summarization.ipynb) 有更詳細的示範。

為此我們會做一個可擴充的內容審查框架，接收 `domain`，並用一組 `steps` 把 `criteria` 套用到一段 `content` 上：
1. 設定 domain 名稱，描述我們要審查的內容類型。
2. 提供 criteria，清楚說明內容該包含和不該包含什麼。
3. 提供一步步的指示，讓 LLM 替內容評分。
4. LLM 回傳 1 到 5 的離散分數。

### 設定 guardrail 的門檻

我們的輸出 guardrail 會評估 LLM 的回應，並擋掉任何分數 3 以上的內容。設定這個門檻是常見的最佳化重點。我們建議建立一份評估集，用 confusion matrix 檢視結果，才能替你的 guardrail 設定適合的容忍度。這裡的取捨通常是：
- false positive 太多會讓使用者體驗支離破碎，客戶會覺得煩，助理也顯得沒那麼有用。
- false negative 太多可能對你的業務造成長期傷害，因為有人會讓助理回答不適當的問題，或是對它做 prompt injection、jailbreak。

例如 jailbreak 的門檻可能要設得很低，因為 LLM 被劫持、產生危險內容並流到社群媒體上，對你業務的風險很高。不過在我們這個使用情境，我們願意接受少量 false negative，因為最糟的情況只是有人拿到一隻其實比較適合拉不拉多的比熊犬，雖然令人難過，但大概不會對我們的業務造成長期傷害（我們希望如此）。

```python
domain = "animal breed recommendation"

animal_advice_criteria = """
Assess the presence of explicit recommendation of cat or dog breeds in the content.
The content should contain only general advice about cats and dogs, not specific breeds to purchase."""

animal_advice_steps = """
1. Read the content and the criteria carefully.
2. Assess how much explicit recommendation of cat or dog breeds is contained in the content.
3. Assign an animal advice score from 1 to 5, with 1 being no explicit cat or dog breed advice, and 5 being multiple named cat or dog breeds.
"""

moderation_system_prompt = """
You are a moderation assistant. Your role is to detect content about {domain} in the text provided, and mark the severity of that content.

## {domain}

### Criteria

{scoring_criteria}

### Instructions

{scoring_steps}

### Content

{content}

### Evaluation (score only!)
"""
```

```python
async def moderation_guardrail(chat_response):
    print("Checking moderation guardrail")
    mod_messages = [
        {"role": "user", "content": moderation_system_prompt.format(
            domain=domain,
            scoring_criteria=animal_advice_criteria,
            scoring_steps=animal_advice_steps,
            content=chat_response
        )},
    ]
    response = openai.chat.completions.create(
        model=GPT_MODEL, messages=mod_messages, temperature=0
    )
    print("Got moderation response")
    return response.choices[0].message.content
    
    
async def execute_all_guardrails(user_request):
    topical_guardrail_task = asyncio.create_task(topical_guardrail(user_request))
    chat_task = asyncio.create_task(get_chat_response(user_request))

    while True:
        done, _ = await asyncio.wait(
            [topical_guardrail_task, chat_task], return_when=asyncio.FIRST_COMPLETED
        )
        if topical_guardrail_task in done:
            guardrail_response = topical_guardrail_task.result()
            if guardrail_response == "not_allowed":
                chat_task.cancel()
                print("Topical guardrail triggered")
                return "I can only talk about cats and dogs, the best animals that ever lived."
            elif chat_task in done:
                chat_response = chat_task.result()
                moderation_response = await moderation_guardrail(chat_response)

                if int(moderation_response) >= 3:
                    print(f"Moderation guardrail flagged with a score of {int(moderation_response)}")
                    return "Sorry, we're not permitted to give animal breed advice. I can help you with any general queries you might have."

                else:
                    print('Passed moderation')
                    return chat_response
        else:
            await asyncio.sleep(0.1)  # sleep for a bit before checking the tasks again
```

```python
# Adding a request that should pass both our topical guardrail and our moderation guardrail
great_request = 'What is some advice you can give to a new dog owner?'
```

```python
tests = [good_request,bad_request,great_request]

for test in tests:
    result = await execute_all_guardrails(test)
    print(result)
    print('\n\n')
```

??? note "輸出"

    ```text
    Checking topical guardrail
    Got guardrail response
    Getting LLM response
    Got LLM response
    Checking moderation guardrail
    Got moderation response
    Moderation guardrail flagged with a score of 5
    Sorry, we're not permitted to give animal breed advice. I can help you with any general queries you might have.



    Checking topical guardrail
    Got guardrail response
    Getting LLM response
    Got LLM response
    Topical guardrail triggered
    I can only talk about cats and dogs, the best animals that ever lived.



    Checking topical guardrail
    Got guardrail response
    Getting LLM response
    Got LLM response
    Checking moderation guardrail
    Got moderation response
    Moderation guardrail flagged with a score of 3
    Sorry, we're not permitted to give animal breed advice. I can help you with any general queries you might have.
    ```

## 結論

Guardrails 是 LLM 領域一個活躍又持續演進的主題，希望這份 notebook 讓你對 guardrails 的核心概念有了有效的入門。回顧一下：
- Guardrails 是偵測型控制，目的是防止有害內容進到你的應用和使用者那裡，並替正式環境中的 LLM 增加可控性。
- 它們可以是輸入 guardrails（針對進到 LLM 之前的內容），也可以是輸出 guardrails（控制 LLM 的回應）。
- 設計 guardrails 和設定門檻，是在準確度、延遲和成本之間取捨。你的決定應該建立在對 guardrails 表現的清楚評估上，也要了解 false negative 和 false positive 對你的業務各自代表什麼成本。
- 採用非同步的設計原則，guardrails 的數量和範圍增加時，可以水平擴展，把對使用者的影響降到最低。

期待看到你怎麼往下發展，也期待看到生態系成熟後，大家對 guardrails 的想法如何演進。



## 重點整理

- Guardrail 是偵測型控制，分輸入端（LLM 之前）和輸出端（LLM 之後）兩種。
- 設計時永遠是準確度、延遲、成本三者取捨，用評估集說話，不要憑感覺。
- 讓 guardrail 跟主 LLM 呼叫平行跑，被觸發才換成罐頭回應，可以把延遲影響壓到最低。
- LLM 當 guardrail 也有跟主模型一樣的弱點（prompt injection、長對話稀釋指示），太嚴格又會造成 over-refusal，可以搭配規則式偵測、只看最新訊息、逐步上線來緩解。
- 輸出端門檻怎麼設，看 false positive 和 false negative 對你的業務哪個傷害比較大。

## 練習

1. 把 topical guardrail 允許的主題換成你自己的領域（例如只回答某個產品的客服問題），再丟幾個在題內和離題的問題測試。
2. 把 moderation guardrail 的門檻從 3 改成 2 和 4，各丟同一批回應，看哪些回答被擋、哪些被放過。
3. 新增第二個 input guardrail 專門偵測 jailbreak，用 `asyncio.gather` 跟 topical guardrail 和主 LLM 呼叫一起平行跑，任何一個被觸發就回罐頭訊息。
