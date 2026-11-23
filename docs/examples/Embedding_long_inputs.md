---
translated: true
source: examples/Embedding_long_inputs.ipynb
---
# 對超過模型 context 長度上限的文字做 embedding

> 原文：[examples/Embedding_long_inputs.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Embedding_long_inputs.ipynb)



## 這篇在做什麼

OpenAI 的 embedding 模型有輸入長度上限，超過就會報錯。這篇示範兩種處理過長文字的做法：直接截斷，或切成 chunk 分別做 embedding 再平均。

## 學完你會

- 用 tiktoken 把文字轉成 token，並截斷到模型允許的長度
- 把 token 切成 chunk，對每個 chunk 做 embedding
- 寫出一個不管輸入多長都能安全呼叫的 embedding 函式，並選擇回傳加權平均或 chunk 列表

## 開跑前

- 需要 `OPENAI_API_KEY` 環境變數
- 需要安裝 `openai`、`tiktoken`、`numpy`


OpenAI 的 embedding 模型無法對超過最大長度的文字做 embedding。最大長度因模型而異，而且是用 _token_ 計算，不是字串長度。如果你不熟 tokenization，請看 [How to count tokens with tiktoken](How_to_count_tokens_with_tiktoken.md)。

這份 notebook 示範怎麼處理比模型最大 context 長度還長的文字。我們用 `text-embedding-3-small` 的 embedding 來示範，但同樣的想法也適用於其他模型和任務。想進一步了解 embedding，請看 [OpenAI Embeddings Guide](https://beta.openai.com/docs/guides/embeddings)。


## 1. 模型的 context 長度

首先，選好模型，並定義一個從 API 取得 embedding 的函式。

```python
from openai import OpenAI
import os
import openai
from tenacity import retry, wait_random_exponential, stop_after_attempt, retry_if_not_exception_type

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "<your OpenAI API key if not set as env var>"))

EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_CTX_LENGTH = 8191
EMBEDDING_ENCODING = 'cl100k_base'

# let's make sure to not retry on an invalid request, because that is what we want to demonstrate
@retry(wait=wait_random_exponential(min=1, max=20), stop=stop_after_attempt(6), retry=retry_if_not_exception_type(openai.BadRequestError))
def get_embedding(text_or_tokens, model=EMBEDDING_MODEL):
    return client.embeddings.create(input=text_or_tokens, model=model).data[0].embedding
```

`text-embedding-3-small` 模型在 `cl100k_base` 編碼下的 context 長度是 8191 tokens，超過這個上限就會出錯，如下所示。

```python
long_text = 'AGI ' * 5000
try:
    get_embedding(long_text)
except openai.BadRequestError as e:
    print(e)
```

??? note "輸出"

    ```text
    Error code: 400 - {'error': {'message': "This model's maximum context length is 8192 tokens, however you requested 10001 tokens (10001 in your prompt; 0 for the completion). Please reduce your prompt; or completion length.", 'type': 'invalid_request_error', 'param': None, 'code': None}}
    ```

我們當然想避免這些錯誤，尤其是用程式大量處理 embedding 的時候。但我們還是可能遇到比最大 context 長度更長的文字。下面介紹處理這些長文字的兩種主要做法並提供範例：(1) 直接把文字截斷到允許的最大長度，(2) 把文字切成 chunk，分別對每個 chunk 做 embedding。

## 1. 截斷輸入文字

最簡單的解法是把輸入文字截斷到允許的最大長度。因為 context 長度是用 token 計算，所以截斷前要先 tokenize。API 同時接受文字和 token 形式的輸入，所以只要小心使用正確的編碼，就不用把 token 轉回字串。下面是這種截斷函式的範例。

```python
import tiktoken

def truncate_text_tokens(text, encoding_name=EMBEDDING_ENCODING, max_tokens=EMBEDDING_CTX_LENGTH):
    """Truncate a string to have `max_tokens` according to the given encoding."""
    encoding = tiktoken.get_encoding(encoding_name)
    return encoding.encode(text)[:max_tokens]
```

我們前面的例子現在可以正常執行了。

```python
truncated = truncate_text_tokens(long_text)
len(get_embedding(truncated))
```

??? note "輸出"

    ```text
    1536
    ```

## 2. 把輸入文字切成 chunk

截斷雖然可行，但缺點很明顯：可能丟掉相關的文字。另一種做法是把輸入文字分成 chunk，再分別對每個 chunk 做 embedding。接著可以把 chunk embedding 分開使用，或用某種方式合併，例如平均（依每個 chunk 的大小加權）。

我們從 [Python 自己的 cookbook](https://docs.python.org/3/library/itertools.html#itertools-recipes) 拿一個把序列切成 chunk 的函式。

```python
from itertools import islice

def batched(iterable, n):
    """Batch data into tuples of length n. The last batch may be shorter."""
    # batched('ABCDEFG', 3) --> ABC DEF G
    if n < 1:
        raise ValueError('n must be at least one')
    it = iter(iterable)
    while (batch := tuple(islice(it, n))):
        yield batch
```

接著定義一個函式，把字串編碼成 token，再切成 chunk。

```python
def chunked_tokens(text, encoding_name, chunk_length):
    encoding = tiktoken.get_encoding(encoding_name)
    tokens = encoding.encode(text)
    chunks_iterator = batched(tokens, chunk_length)
    yield from chunks_iterator
```

最後，可以寫一個函式安全地處理 embedding request，即使輸入文字比最大 context 長度還長也沒問題，做法是把輸入 token 切成 chunk，分別對每個 chunk 做 embedding。`average` 旗標設成 `True` 會回傳 chunk embedding 的加權平均，設成 `False` 則直接回傳未修改的 chunk embedding 列表。

```python
import numpy as np


def len_safe_get_embedding(text, model=EMBEDDING_MODEL, max_tokens=EMBEDDING_CTX_LENGTH, encoding_name=EMBEDDING_ENCODING, average=True):
    chunk_embeddings = []
    chunk_lens = []
    for chunk in chunked_tokens(text, encoding_name=encoding_name, chunk_length=max_tokens):
        chunk_embeddings.append(get_embedding(chunk, model=model))
        chunk_lens.append(len(chunk))

    if average:
        chunk_embeddings = np.average(chunk_embeddings, axis=0, weights=chunk_lens)
        chunk_embeddings = chunk_embeddings / np.linalg.norm(chunk_embeddings)  # normalizes length to 1
        chunk_embeddings = chunk_embeddings.tolist()
    return chunk_embeddings
```

同樣地，現在可以處理很長的輸入文字了。

```python
average_embedding_vector = len_safe_get_embedding(long_text, average=True)
chunks_embedding_vectors = len_safe_get_embedding(long_text, average=False)

print(f"Setting average=True gives us a single {len(average_embedding_vector)}-dimensional embedding vector for our long text.")
print(f"Setting average=False gives us {len(chunks_embedding_vectors)} embedding vectors, one for each of the chunks.")
```

??? note "輸出"

    ```text
    Setting average=True gives us a single 1536-dimensional embedding vector for our long text.
    Setting average=False gives us 2 embedding vectors, one for each of the chunks.
    ```

有些情況下，在段落或句子邊界切 chunk 比較合理，有助於保留文字的意思。

## 重點整理

- Embedding 模型的輸入上限是用 token 算的，不是字元數，所以要先 tokenize 再處理。
- 截斷最簡單，但會丟掉後面的內容。
- 切 chunk 不丟資訊，可以分別使用，也可以加權平均成一個 vector。
- 加權平均是依每個 chunk 的 token 數加權，長的 chunk 影響比較大。
- 在段落或句子邊界切，能更好地保留語意。

## 練習

1. 把截斷函式的長度上限改小（例如 100 tokens），比較截斷前後的 embedding 結果。
2. 呼叫 chunk 版的 embedding 函式時，把 `average` 分別設成 `True` 和 `False`，看回傳的形狀有什麼不同。
3. 修改切 chunk 的函式，改成在句子邊界切分，而不是固定 token 數。
