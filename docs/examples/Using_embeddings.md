---
translated: true
source: examples/Using_embeddings.ipynb
---
# 使用 embeddings

> 原文：[examples/Using_embeddings.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Using_embeddings.ipynb)



## 這篇在做什麼
一組用 `text-embedding-3-small` 模型透過 OpenAI API 把文字轉成 embedding 的小範例，從單一文字到加上 retry 的做法。程式碼很短，適合拿來當自己專案的起手式。

## 學完你會
- 呼叫 OpenAI API 取得一段文字的 embedding。
- 用 `tenacity` 加上指數退避（exponential backoff），避免打到 rate limit。
- 把取 embedding 的流程包成可重用的函式。

## 開跑前
- 需要 `OPENAI_API_KEY`，呼叫 API 會產生費用。

## 使用 embeddings

這份 notebook 收集了一些實用的程式片段，用 `text-embedding-3-small` 模型透過 OpenAI API 對文字做 embedding。

```python
from openai import OpenAI
client = OpenAI()

embedding = client.embeddings.create(
    input="Your text goes here", model="text-embedding-3-small"
).data[0].embedding
len(embedding)
```

??? note "輸出"

    ```text
    1536
    ```

建議使用 `tenacity` 套件或其他指數退避的實作，來更好地處理 API 的 rate limit，因為太快打太多次 API 會觸發 rate limit。用下面的函式可以讓你盡快拿到 embedding。

```python
# Negative example (slow and rate-limited)
from openai import OpenAI
client = OpenAI()

num_embeddings = 10000 # Some large number
for i in range(num_embeddings):
    embedding = client.embeddings.create(
        input="Your text goes here", model="text-embedding-3-small"
    ).data[0].embedding
    print(len(embedding))
```

```python
# Best practice
from tenacity import retry, wait_random_exponential, stop_after_attempt
from openai import OpenAI
client = OpenAI()

# Retry up to 6 times with exponential backoff, starting at 1 second and maxing out at 20 seconds delay
@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6))
def get_embedding(text: str, model="text-embedding-3-small") -> list[float]:
    return client.embeddings.create(input=[text], model=model).data[0].embedding

embedding = get_embedding("Your text goes here", model="text-embedding-3-small")
print(len(embedding))
```

??? note "輸出"

    ```text
    1536
    ```

## 重點整理
- embedding 把文字轉成向量，`text-embedding-3-small` 是這篇用的模型。
- 呼叫太頻繁會觸發 rate limit，要用指數退避重試。
- 把取 embedding 的邏輯包成函式，之後換模型或加 retry 只要改一處。

## 練習
1. 把模型換成 `text-embedding-3-large`，比較回傳向量的長度。
2. 對兩句意思相近的話各取 embedding，算它們的 cosine similarity。
3. 修改 retry 的設定（等待時間或最大次數），故意用壞的 API key，看重試行為怎麼變化。
