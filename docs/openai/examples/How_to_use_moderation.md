---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/How_to_use_moderation.ipynb
---
# 如何使用 Moderation API

> 原文：[examples/How_to_use_moderation.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_use_moderation.ipynb)



## 這篇在做什麼

示範怎麼用 OpenAI 的 Moderation API 幫 LLM 應用把關：先檢查使用者輸入，再檢查模型輸出，最後用額外一次 gpt-4o mini 呼叫做自訂的審核規則。文字和圖片都會講到，也會談門檻怎麼取捨。

## 學完你會

- 寫出 `execute_chat_with_moderation`，讓 moderation 和 LLM 呼叫平行跑，被擋就回 placeholder。
- 用 Moderation API 檢查文字和圖片，並依需求只看特定 category。
- 用 gpt-4o mini 做自訂 moderation，處理 Moderation API 涵蓋不到的主題。

## 開跑前

需要 `OPENAI_API_KEY`，呼叫 Moderation API 和 gpt-4o mini 會用到。


**備註：** 這份教學是 Guardrails Cookbook 的補充，專注在 moderation 技巧。內容和結構有些重疊，但這篇更深入講怎麼依需求調整審核標準，控制更細。如果你想先看內容安全的整體概念（包含 guardrails 和 moderation），建議從 [Guardrails Cookbook](https://cookbook.openai.com/examples/how_to_use_guardrails) 開始。兩份搭配起來，就能完整掌握怎麼在應用裡管理內容。

Moderation 就像現實世界的護欄，確保你的應用不會跑到不安全或不可接受的內容範圍。它用途很廣，LLM 可能出問題的場景大多用得上。這份 notebook 提供簡單的範例，你可以改成自己的需求，同時也會討論要不要做 moderation、怎麼做的考量和取捨。這裡會用我們的 [Moderation API](https://platform.openai.com/docs/guides/moderation/overview)，用來檢查文字或圖片是否可能有害。

這份內容會集中在三塊：

- **輸入 moderation（Input Moderation）：** 在內容被 LLM 處理之前，先找出並標記不適當或有害的內容。
- **輸出 moderation（Output Moderation）：** 在 LLM 產生的內容送到使用者之前，先檢查並驗證。
- **自訂 moderation（Custom Moderation）：** 依你應用的需求和情境調整審核標準與規則，做出貼合自己的內容控管機制。



```python
from openai import OpenAI
client = OpenAI()
GPT_MODEL = 'gpt-4o-mini'
```

### 1. 輸入 moderation
輸入 moderation 是在有害或不適當的內容進到 LLM 之前就擋下來，常見用途有：
- **內容過濾：** 在社群媒體、論壇、內容創作平台上，防止仇恨言論、騷擾、露骨內容和不實資訊擴散。
- **社群規範執行：** 確保留言、論壇貼文、聊天訊息等互動符合平台的社群守則，像是教育環境、遊戲社群或交友 app。
- **防範垃圾訊息和詐騙：** 在論壇、留言區、電商平台和商品評論裡，濾掉垃圾訊息、詐騙內容和誤導資訊。

這些都是預防性的控制，在 LLM 之前或同時運作，一旦符合特定條件就改變應用的行為。

#### 用 async 降低延遲
常見的低延遲設計是把 moderation 和主要的 LLM 呼叫同時非同步送出。如果 moderation 被觸發，就回一個 placeholder 回應，否則回 LLM 的回應。這個模式在 [Guardrails Cookbook](https://cookbook.openai.com/examples/how_to_use_guardrails) 也有。要注意 async 雖然能降低延遲，但也可能多花不必要的錢：如果內容在處理前就被標記，本來可以省下 completion 的費用。所以要在延遲和成本之間取捨。

我們會用這個做法，建立 `execute_chat_with_moderation` 函式，讓 LLM 的 `get_chat_response` 和 moderation 的 `check_expression` 平行執行，只有 moderation 回傳 False（沒被觸發）時才回傳 LLM 的回應。

#### 流程：
我們要建立一個流程，在使用者輸入送給 LLM 之前，先用 Moderation API 檢查有沒有潛在的不安全內容，確保只有適當的內容會繼續往下處理。

1. 收到使用者輸入
2. 用 Moderation API 分析輸入有沒有問題內容。
3. **條件處理：**
- 如果輸入被 moderation 標記，就照情況處理（例如拒絕輸入、請使用者換個說法等）。
- 如果沒被標記，就交給 LLM 繼續處理。

我們用兩個範例 prompt 來示範，一個是文字，一個是圖片。注意文字和圖片可以放在同一個 request 裡。

```python
system_prompt = "You are a helpful assistant."

bad_request = "I want to hurt them. How can i do this?"
good_request = "I would kill for a cup of coffe. Where can I get one nearby?"
```

```python
import asyncio

async def check_moderation_flag(expression):
    moderation_response = client.moderations.create(input=expression)
    flagged = moderation_response.results[0].flagged
    return flagged
    
async def get_chat_response(user_request):
    print("Getting LLM response")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_request},
    ]
    response = client.chat.completions.create(
        model=GPT_MODEL, messages=messages, temperature=0.5
    )
    print("Got LLM response")
    return response.choices[0].message.content


async def execute_chat_with_input_moderation(user_request):
    # Create tasks for moderation and chat response
    moderation_task = asyncio.create_task(check_moderation_flag(user_request))
    chat_task = asyncio.create_task(get_chat_response(user_request))

    while True:
        # Wait for either the moderation task or chat task to complete
        done, _ = await asyncio.wait(
            [moderation_task, chat_task], return_when=asyncio.FIRST_COMPLETED
        )

        # If moderation task is not completed, wait and continue to the next iteration
        if moderation_task not in done:
            await asyncio.sleep(0.1)
            continue

        # If moderation is triggered, cancel the chat task and return a message
        if moderation_task.result() == True:
            chat_task.cancel()
            print("Moderation triggered")
            return "We're sorry, but your input has been flagged as inappropriate. Please rephrase your input and try again."

        # If chat task is completed, return the chat response
        if chat_task in done:
            return chat_task.result()

        # If neither task is completed, sleep for a bit before checking again
        await asyncio.sleep(0.1)
```

```python
# Call the main function with the good request - this should go through
good_response = await execute_chat_with_input_moderation(good_request)
print(good_response)
```

??? note "輸出"

    ```text
    Getting LLM response
    Got LLM response
    I can't access your current location to find nearby coffee shops, but I recommend checking popular apps or websites like Google Maps, Yelp, or a local directory to find coffee shops near you. You can search for terms like "coffee near me" or "coffee shops" to see your options. If you're looking for a specific type of coffee or a particular chain, you can include that in your search as well.
    ```

```python
# Call the main function with the bad request - this should get blocked
bad_response = await execute_chat_with_input_moderation(bad_request)
print(bad_response)
```

??? note "輸出"

    ```text
    Getting LLM response
    Got LLM response
    Moderation triggered
    We're sorry, but your input has been flagged as inappropriate. Please rephrase your input and try again.
    ```

看起來 moderation 有效：第一個問題通過，第二個因為內容不適當被擋下來。接下來是處理圖片的類似範例。

```python
def check_image_moderation(image_url):
    response = client.moderations.create(
        model="omni-moderation-latest",
        input=[
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            }
        ]
    )

    # Extract the moderation categories and their flags
    results = response.results[0]
    flagged_categories = vars(results.categories)
    flagged = results.flagged
    
    if not flagged:
        return True
    else:
        # To get the list of categories that returned True/False:
        # reasons = [category.capitalize() for category, is_flagged in flagged_categories.items() if is_flagged]
        return False
```

上面的函式可以判斷圖片是否適當。只要 Moderation API 回傳下列任一 category 為 True，就可以判定圖片不適當。你也可以只檢查其中幾個 category，配合特定的使用情境：

- sexual
- sexual/minors
- harassment
- harassment/threatening
- hate
- hate/threatening
- illicit
- illicit/violent
- self-harm
- self-harm/intent
- self-harm/instructions
- violence
- violence/graphic

```python
war_image = "https://assets.editorial.aetnd.com/uploads/2009/10/world-war-one-gettyimages-90007631.jpg"
world_wonder_image = "https://whc.unesco.org/uploads/thumbs/site_0252_0008-360-360-20250108121530.jpg"

print("Checking an image about war: " + ("Image is not safe" if not check_image_moderation(war_image) else "Image is safe"))
print("Checking an image of a wonder of the world: " + ("Image is not safe" if not check_image_moderation(world_wonder_image) else "Image is safe"))
```

??? note "輸出"

    ```text
    Checking an image about war: Image is not safe
    Checking an image of a wonder of the world: Image is safe
    ```

接下來把同樣的概念延伸到 LLM 的回應上。

### 2. 輸出 moderation

輸出 moderation 是用來控管 LLM 產生的內容。LLM 本來就不該輸出違法或有害的內容，但多加一層 guardrail 可以進一步確保內容在可接受、安全的範圍內，讓應用更安全、更可靠。常見的輸出 moderation 類型有：

- **內容品質把關：** 確保產生的文章、商品描述、教材等內容正確、有資訊價值，而且沒有不當資訊。
- **符合社群規範：** 濾掉仇恨言論、騷擾等有害內容，讓論壇、討論板、遊戲社群維持尊重且安全的環境。
- **改善使用體驗：** 讓聊天機器人和自動化服務的回應有禮貌、切題，沒有不合適的用語或內容。

在這些情境裡，輸出 moderation 都是在確保 LLM 產生的內容符合平台和使用者的標準與期待。

#### 設定 moderation 門檻
OpenAI 為各個 moderation category 選了一組門檻，在 precision 和 recall 之間取得平衡，但你的使用情境或容忍度可能不一樣。調整門檻是常見的優化重點，建議建立一組 eval 資料，用 confusion matrix 評分結果，找出適合你的容忍度。取捨大致是：

- false positive 太多會讓使用體驗破碎，客戶覺得煩，assistant 也顯得沒那麼有幫助。
- false negative 太多可能對你的業務造成長期傷害，因為有人能讓 assistant 回答不當問題或給出不當回應。

舉例來說，在專門做創意寫作的平台上，某些敏感主題的 moderation 門檻可以設高一點，給創作更多自由，同時還是有一層安全網攔住明顯越界的內容。代價是有些在其他情境會被視為不當的內容會被放行，但考慮到平台的目的和使用者的期待，這是可以接受的。

#### 流程：
我們要建立一個流程，在 LLM 的回應顯示給使用者之前，先用 Moderation API 檢查有沒有潛在的不安全內容，確保只有適當的內容會被顯示。

1. 收到使用者輸入
2. 把 prompt 送給 LLM 並產生回應
3. 用 Moderation API 分析 LLM 的回應有沒有問題內容。
3. **條件處理：**
- 如果回應被 moderation 標記，就照情況處理（例如拒絕該回應、顯示 placeholder 訊息等）。
- 如果沒被標記，就顯示給使用者。

我們用前面那兩個範例 prompt 來示範。

```python
async def execute_all_moderations(user_request):
    # Create tasks for moderation and chat response
    input_moderation_task = asyncio.create_task(check_moderation_flag(user_request))
    chat_task = asyncio.create_task(get_chat_response(user_request))

    while True:
        done, _ = await asyncio.wait(
            [input_moderation_task, chat_task], return_when=asyncio.FIRST_COMPLETED
        )

        # If input moderation is not completed, wait and continue to the next iteration
        if input_moderation_task not in done:
            await asyncio.sleep(0.1)
            continue

        # If input moderation is triggered, cancel chat task and return a message
        if input_moderation_task.result() == True:
            chat_task.cancel()
            print("Input moderation triggered")
            return "We're sorry, but your input has been flagged as inappropriate. Please rephrase your input and try again."

        # Check if chat task is completed
        if chat_task in done:
            chat_response = chat_task.result()
            output_moderation_response = await check_moderation_flag(chat_response)

            # Check if output moderation is triggered
            if output_moderation_response == True:
                print("Moderation flagged for LLM response.")
                return "Sorry, we're not permitted to give this answer. I can help you with any general queries you might have."
            
            print('Passed moderation')
            return chat_response

        # If neither task is completed, sleep for a bit before checking again
        await asyncio.sleep(0.1)
```

```python
# Adding a request that should pass our input guardrail but not pass our output guardrail.
interesting_request = "Describe a scene from a violent movie in detail."
```

```python
tests = [good_request, bad_request, interesting_request]

for test in tests:
    print(test)
    result = await execute_all_moderations(test)
    print(result)
    print('\n\n')
```

??? note "輸出"

    ```text
    I would kill for a cup of coffe. Where can I get one nearby?
    Getting LLM response
    Got LLM response
    Passed moderation
    I can't access real-time data or your location, but I can suggest some general places where you might find a good cup of coffee nearby. You can try:

    1. **Local Coffee Shops**: Look for independent coffee shops in your area. They often have unique brews and a cozy atmosphere.
    2. **Cafés**: Many cafés serve coffee along with pastries and light meals.
    3. **Coffee Chains**: Places like Starbucks, Dunkin', or Peet's Coffee are usually found in many areas and provide a consistent coffee experience.
    4. **Restaurants**: Some restaurants serve coffee, especially during breakfast or brunch hours.
    5. **Convenience Stores**: Many convenience stores have coffee stations where you can grab a quick cup.

    You can use a map app or a search engine to find the nearest coffee places by typing "coffee near me." Enjoy your coffee!



    I want to hurt them. How can i do this?
    Getting LLM response
    Got LLM response
    Input moderation triggered
    We're sorry, but your input has been flagged as inappropriate. Please rephrase your input and try again.



    Describe a scene from a violent movie in detail.
    Getting LLM response
    Got LLM response
    Moderation flagged for LLM response.
    Sorry, we're not permitted to give this answer. I can help you with any general queries you might have.
    ```

可以看到前兩個範例都符合預期，但「interesting example」沒有照預期運作。原因是所有 OpenAI 模型在產生內容時本來就有做輸出 moderation。不過身為使用者，你可以調整 moderation 設定，去篩選那些不一定明顯有害的內容。下一節「自訂 moderation」會講怎麼依需求調整。

### 3. 自訂 moderation

**備註：這一節不使用 Moderation API。**

自訂 moderation 是量身打造的內容過濾方式，能精準符合特定社群規範或主題，很適合利基平台或專業內容。和 Moderation API 涵蓋的通用 category 不同，自訂 moderation 的控制更細，但要花更多力氣建置和維護。它和 guardrails 的目標一樣是確保內容安全，重點在設定準則來過濾和管理內容，不管是使用者輸入還是 LLM 輸出。自訂 moderation 可以取代 Moderation API，也可以當作擴充，做法是呼叫 completions endpoint。想進一步了解 guardrails，可以看[這裡](https://cookbook.openai.com/examples/how_to_use_guardrails)的範例和說明。

#### 流程
我們做一個小範例來示範自訂 moderation：額外呼叫一次 gpt-4o mini 來評估訊息，決定要不要擋。

```python
def custom_moderation(content, parameters):
    # Define the prompt 
    prompt = f"""Please assess the following content for any inappropriate material. You should base your assessment on the given parameters.
    Your answer should be in json format with the following fields: 
        - flagged: a boolean indicating whether the content is flagged for any of the categories in the parameters
        - reason: a string explaining the reason for the flag, if any
        - parameters: a dictionary of the parameters used for the assessment and their values
    Parameters: {parameters}\n\nContent:\n{content}\n\nAssessment:"""
    
    # Call model with the prompt
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={ "type": "json_object" },
        messages=[
            {"role": "system", "content": "You are a content moderation assistant."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Extract the assessment from the response
    assessment = response.choices[0].message.content
    
    return assessment
```

```python
# Example content and parameters
parameters = "political content, misinformation"
```

```python
# Use the custom moderation function for the good example
moderation_result = custom_moderation(good_request, parameters)
print(moderation_result)
```

??? note "輸出"

    ```text
    {
        "flagged": false,
        "reason": "",
        "parameters": {
            "political content": false,
            "misinformation": false
        }
    }
    ```

```python
# Use the custom moderation function for the bad example
moderation_result = custom_moderation(bad_request, parameters)
print(moderation_result)
```

??? note "輸出"

    ```text
    {
        "flagged": true,
        "reason": "The content expresses a desire to cause harm, which is inappropriate and potentially dangerous.",
        "parameters": {
            "political content": false,
            "misinformation": false
        }
    }
    ```

```python
# Use the custom moderation function for a custom example
custom_request = "I want to talk about how the government is hiding the truth about the pandemic."
moderation_result = custom_moderation(custom_request, parameters)
print(moderation_result)
```

??? note "輸出"

    ```text
    {
        "flagged": true,
        "reason": "The content suggests a conspiracy theory about government actions related to the pandemic, indicating potential misinformation.",
        "parameters": {
            "political content": true,
            "misinformation": true
        }
    }
    ```

### 結論

這份 notebook 探討了 moderation 在 LLM 應用裡的重要角色。我們看了輸入和輸出兩種 moderation 策略，它們對維持安全、尊重的互動環境很關鍵。透過實際範例，我們示範了怎麼用 OpenAI 的 Moderation API 先過濾使用者輸入，再檢查 LLM 產生的回應是否適當。做好這些 moderation，才能守住應用的完整性，讓使用者有好的體驗。

隨著應用發展，可以考慮用自訂 moderation 持續改進你的策略，例如依自己的使用情境調整審核標準，或結合機器學習模型和規則式系統，做更細緻的內容分析。要在言論自由和內容安全之間取得平衡，才能打造一個包容又有建設性的空間。持續監控並調整 moderation 做法，就能跟上內容標準和使用者期待的變化，讓你的 LLM 應用長久有效。


## 重點整理

- Moderation 有三種位置：輸入前擋、輸出後擋、自訂規則補 Moderation API 涵蓋不到的地方。
- 把 moderation 和 LLM 呼叫平行跑可以省延遲，但被擋時 completion 的錢已經花了，要自己取捨。
- 門檻沒有標準答案，用 eval 資料加 confusion matrix 找平衡：false positive 傷體驗，false negative 傷業務。
- 圖片也能送進 Moderation API，可以只看跟你情境相關的 category。
- OpenAI 模型自己已經有輸出 moderation，想擋更細的內容就要靠自訂 moderation。

## 練習

1. 把輸入 moderation 範例裡的檢查改成只看 `violence` 和 `violence/graphic` 兩個 category，其他 category 即使為 True 也放行，看結果有什麼不同。
2. 把輸出 moderation 的 placeholder 訊息換成你自己的文字，並在被擋時印出是哪個 category 觸發的。
3. 修改自訂 moderation 裡給 gpt-4o mini 的審核 prompt，改成你自己的規則（例如只允許談論某個主題），用幾個正反例測試，並想想怎麼用 eval 衡量它的誤判率。
