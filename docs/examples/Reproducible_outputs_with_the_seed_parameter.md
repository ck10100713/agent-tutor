---
translated: true
source: examples/Reproducible_outputs_with_the_seed_parameter.ipynb
---

# 用新的 seed 參數讓 completion 輸出保持一致

> 原文：[examples/Reproducible_outputs_with_the_seed_parameter.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Reproducible_outputs_with_the_seed_parameter.ipynb)



## 這篇在做什麼
Chat Completions 預設每次輸出都可能不同。這篇示範怎麼加上 `seed` 並固定其他參數，讓輸出（大致上）一樣，還有怎麼用 `system_fingerprint` 判斷後端有沒有變動。

## 學完你會
- 在 Chat Completion 請求裡設定 `seed`，得到大致一致的輸出
- 看懂 `system_fingerprint` 的意義，知道什麼時候輸出可能因為後端更新而不同
- 比較有 seed 和沒 seed 的結果，並知道要一起固定哪些參數

## 開跑前
- OpenAI API key


**TLDR**：開發者現在可以在 Chat Completion 請求裡指定 `seed` 參數，拿到（大致）一致的輸出。為了讓你追蹤變動，我們提供 `system_fingerprint` 欄位。這個值不同的話，輸出可能因為我們系統的變更而不一樣。注意這個功能還在 beta，目前只支援 `gpt-4-1106-preview` 和 `gpt-3.5-turbo-1106`。

### 背景

可重現性一直是使用者社群對 API 的大宗需求。例如能拿到可重現的數值結果，就能做很多對數值變化敏感的應用。

#### 讓輸出一致的模型層級功能

Chat Completions 和 Completions API 預設是非確定性的（也就是每次請求的輸出可能不同），但現在提供幾個模型層級的控制，讓輸出更接近確定性。

這能讓 completion 保持一致，讓你完全掌控建在 API 之上的模型行為，對重現結果和測試很有用，你可以確切知道會得到什麼。

#### 如何讓輸出一致

要讓多次 API 呼叫得到*大致*確定的輸出：

- 把 `seed` 設成你選的任意整數，每次請求都用同一個值，例如 `12345`。
- 其他參數（prompt、temperature、top_p 等）每次請求都設成一樣。
- 檢查回應中的 `system_fingerprint` 欄位。它是 OpenAI 伺服器產生 completion 時所用的模型權重、基礎設施和其他設定組合的識別碼。你改請求參數，或 OpenAI 更新模型服務的數值設定（一年可能有幾次），它就會改變。

只要 `seed`、請求參數和 `system_fingerprint` 都一致，模型輸出大多會一樣。即使這些都相同，因為模型本身固有的非確定性，仍有小機率回應不同。


### 讓輸出一致的模型層級控制：`seed` 和 `system_fingerprint`

##### `seed`

指定之後，系統會盡力以確定性的方式取樣，相同的 seed 和參數重複請求，應該回傳相同結果。不保證一定確定，請參考回應裡的 `system_fingerprint` 來監控後端變化。

##### `system_fingerprint`

這個 fingerprint 代表模型執行時的後端設定。它可以搭配 seed 請求參數，用來了解什麼時候後端有變動、可能影響確定性。使用者是否能期待「幾乎每次都一樣的結果」，就看這個指標。


## 範例：用固定 seed 產生短文

這個範例示範怎麼用固定 seed 產生一小段文字。在需要一致結果的情境（測試、除錯，或需要輸出一致的應用）特別有用。

### Python SDK

> **Note**
> 請切到最新版 SDK（撰文時是 `1.3.3`）。

```python
!pip install --upgrade openai # Switch to the latest version of OpenAI (1.3.3 at time of writing)
```

```python
import openai
import asyncio
from IPython.display import display, HTML

from utils.embeddings_utils import (
    get_embedding,
    distances_from_embeddings
)

GPT_MODEL = "gpt-3.5-turbo-1106"
```

```python
async def get_chat_response(
    system_message: str, user_request: str, seed: int = None, temperature: float = 0.7
):
    try:
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_request},
        ]

        response = openai.chat.completions.create(
            model=GPT_MODEL,
            messages=messages,
            seed=seed,
            max_tokens=200,
            temperature=temperature,
        )

        response_content = response.choices[0].message.content
        system_fingerprint = response.system_fingerprint
        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.total_tokens - response.usage.prompt_tokens

        table = f"""
        <table>
        <tr><th>Response</th><td>{response_content}</td></tr>
        <tr><th>System Fingerprint</th><td>{system_fingerprint}</td></tr>
        <tr><th>Number of prompt tokens</th><td>{prompt_tokens}</td></tr>
        <tr><th>Number of completion tokens</th><td>{completion_tokens}</td></tr>
        </table>
        """
        display(HTML(table))

        return response_content
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

def calculate_average_distance(responses):
    """
    This function calculates the average distance between the embeddings of the responses.
    The distance between embeddings is a measure of how similar the responses are.
    """
    # Calculate embeddings for each response
    response_embeddings = [get_embedding(response) for response in responses]

    # Compute distances between the first response and the rest
    distances = distances_from_embeddings(response_embeddings[0], response_embeddings[1:])

    # Calculate the average distance
    average_distance = sum(distances) / len(distances)

    # Return the average distance
    return average_distance
```

先試著不加 `seed` 參數，產生幾個關於「火星之旅」的短文版本。這是預設行為：

```python
topic = "a journey to Mars"
system_message = "You are a helpful assistant."
user_request = f"Generate a short excerpt of news about {topic}."

responses = []


async def get_response(i):
    print(f'Output {i + 1}\n{"-" * 10}')
    response = await get_chat_response(
        system_message=system_message, user_request=user_request
    )
    return response


responses = await asyncio.gather(*[get_response(i) for i in range(5)])
average_distance = calculate_average_distance(responses)
print(f"The average similarity between responses is: {average_distance}")
```

??? note "輸出"

    ```text
    Output 1
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 2
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 3
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 4
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 5
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    The average similarity between responses is: 0.1136714512418833
    ```

現在用固定的 `seed` 123 和 `temperature` 0 跑同樣的程式，比較回應和 `system_fingerprint`。

```python
SEED = 123
responses = []


async def get_response(i):
    print(f'Output {i + 1}\n{"-" * 10}')
    response = await get_chat_response(
        system_message=system_message,
        seed=SEED,
        temperature=0,
        user_request=user_request,
    )
    return response


responses = await asyncio.gather(*[get_response(i) for i in range(5)])

average_distance = calculate_average_distance(responses)
print(f"The average distance between responses is: {average_distance}")
```

??? note "輸出"

    ```text
    Output 1
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 2
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 3
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 4
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    Output 5
    ----------
    ```

    ```text
    <IPython.core.display.HTML object>
    ```

    ```text
    The average distance between responses is: 0.0449054397632461
    ```

可以看到，`seed` 參數讓我們得到一致得多的結果。

## 結論

我們示範了怎麼用固定的整數 `seed` 讓模型產生一致的輸出，在需要可重現性的情境特別有用。不過要注意，`seed` 只保證一致，不保證輸出品質。要用可重現輸出，每次 Chat Completions 呼叫都要用同一個整數 `seed`，也要讓 `temperature`、`max_tokens` 等其他參數一致。進一步的用法是：在 benchmark、評估不同 prompt 或模型時使用固定 `seed`，確保每個版本在相同條件下被評估，比較才公平、結果才可靠。

## 重點整理
- Chat Completions 預設非確定性，`seed` 讓輸出大致可重現，但不保證 100% 一樣。
- 想重現結果，`seed` 和 prompt、temperature、top_p、max_tokens 等參數都要一致。
- `system_fingerprint` 代表後端設定，值變了表示輸出可能因為系統更新而不同。
- `seed` 只管一致性，不管輸出好壞。
- 固定 seed 很適合用在測試、除錯和公平比較不同 prompt 或模型。

## 練習
1. 把 `seed` 從 123 改成另一個數字，確認輸出變了，但同樣 seed 跑兩次仍然一致。
2. 把 `temperature` 改成 1 但保持 `seed` 不變，觀察一致性有沒有下降。
3. 寫一個迴圈連續呼叫 10 次，用 `system_fingerprint` 和輸出內容算出有幾次結果完全相同。
