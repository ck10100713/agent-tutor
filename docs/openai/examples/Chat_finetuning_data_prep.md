---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/Chat_finetuning_data_prep.ipynb
---

# 聊天模型 fine-tuning 的資料準備與分析

> 原文：[examples/Chat_finetuning_data_prep.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/Chat_finetuning_data_prep.ipynb)



## 這篇在做什麼
拿一份 chat 格式的 JSONL 資料集，在送去 fine-tuning 前先檢查格式、算統計數字，並估算要花多少 token（也就是多少錢）。

## 學完你會
- 寫程式驗證每筆對話符合 fine-tuning API 要求的格式，並依錯誤類型統計
- 用 tiktoken 算出每筆對話和 assistant 訊息的 token 數，找出超過上限的樣本
- 估算整份資料 fine-tuning 的總 token 數與訓練 epoch 數

## 開跑前
需要安裝 tiktoken 等套件。這個 notebook 本身只讀本機的 JSONL 檔，不需要 API key。

這個 notebook 是用來前處理並分析 chat 資料集，為 fine-tuning 聊天模型做準備。
它會檢查格式錯誤、提供基本統計，並估算 fine-tuning 的 token 數與成本。
這裡的做法對應 gpt-3.5-turbo 的[目前 fine-tuning 方法](https://platform.openai.com/docs/guides/fine-tuning)。
babbage-002、davinci-002 這類模型請看 [legacy fine-tuning](https://platform.openai.com/docs/guides/legacy-fine-tuning)。

```python
import json
import tiktoken # for token counting
import numpy as np
from collections import defaultdict
```

## 載入資料

先從一個[範例 JSONL 檔](https://github.com/openai/openai-cookbook/blob/main/examples/data/toy_chat_fine_tuning.jsonl)載入 chat 資料集。

```python
data_path = "data/toy_chat_fine_tuning.jsonl"

# Load the dataset
with open(data_path, 'r', encoding='utf-8') as f:
    dataset = [json.loads(line) for line in f]

# Initial dataset stats
print("Num examples:", len(dataset))
print("First example:")
for message in dataset[0]["messages"]:
    print(message)
```

??? note "輸出"

    ```text
    Num examples: 5
    First example:
    {'role': 'system', 'content': 'You are a happy assistant that puts a positive spin on everything.'}
    {'role': 'user', 'content': 'I fell off my bike today.'}
    {'role': 'assistant', 'content': "It's great that you're getting exercise outdoors!"}
    ```

## 格式驗證

我們可以做幾種錯誤檢查，確認資料集裡每段對話都符合 fine-tuning API 預期的格式。錯誤會依性質分類，方便除錯。

1. **資料型別檢查**：檢查每筆資料是否為 dictionary (`dict`)。錯誤類型：`data_type`。
2. **有沒有 messages 清單**：檢查每筆資料是否有 `messages` 清單。錯誤類型：`missing_messages_list`。
3. **message 的 key 檢查**：確認 `messages` 裡每則訊息都有 `role` 和 `content`。錯誤類型：`message_missing_key`。
4. **訊息中的未知 key**：如果訊息出現 `role`、`content`、`weight`、`function_call`、`name` 以外的 key 就記錄。錯誤類型：`message_unrecognized_key`。
5. **role 驗證**：確認 `role` 是 "system"、"user" 或 "assistant" 其中之一。錯誤類型：`unrecognized_role`。
6. **content 驗證**：確認 `content` 有文字內容而且是字串。錯誤類型：`missing_content`。
7. **是否有 assistant 訊息**：檢查每段對話至少有一則 assistant 訊息。錯誤類型：`example_missing_assistant_message`。

下面的程式會做這些檢查，並印出每種錯誤的數量。這在除錯、確認資料集可以進入下一步時很有用。


```python
# Format error checks
format_errors = defaultdict(int)

for ex in dataset:
    if not isinstance(ex, dict):
        format_errors["data_type"] += 1
        continue
        
    messages = ex.get("messages", None)
    if not messages:
        format_errors["missing_messages_list"] += 1
        continue
        
    for message in messages:
        if "role" not in message or "content" not in message:
            format_errors["message_missing_key"] += 1
        
        if any(k not in ("role", "content", "name", "function_call", "weight") for k in message):
            format_errors["message_unrecognized_key"] += 1
        
        if message.get("role", None) not in ("system", "user", "assistant", "function"):
            format_errors["unrecognized_role"] += 1
            
        content = message.get("content", None)
        function_call = message.get("function_call", None)
        
        if (not content and not function_call) or not isinstance(content, str):
            format_errors["missing_content"] += 1
    
    if not any(message.get("role", None) == "assistant" for message in messages):
        format_errors["example_missing_assistant_message"] += 1

if format_errors:
    print("Found errors:")
    for k, v in format_errors.items():
        print(f"{k}: {v}")
else:
    print("No errors found")
```

??? note "輸出"

    ```text
    No errors found
    ```

## Token 計數工具

先定義幾個後面會用到的小工具。

```python
encoding = tiktoken.get_encoding("cl100k_base")

# not exact!
# simplified from https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def num_tokens_from_messages(messages, tokens_per_message=3, tokens_per_name=1):
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3
    return num_tokens

def num_assistant_tokens_from_messages(messages):
    num_tokens = 0
    for message in messages:
        if message["role"] == "assistant":
            num_tokens += len(encoding.encode(message["content"]))
    return num_tokens

def print_distribution(values, name):
    print(f"\n#### Distribution of {name}:")
    print(f"min / max: {min(values)}, {max(values)}")
    print(f"mean / median: {np.mean(values)}, {np.median(values)}")
    print(f"p5 / p95: {np.quantile(values, 0.1)}, {np.quantile(values, 0.9)}")
```

## 資料警告與 token 數 

做一些輕量分析，就能找出資料集的潛在問題（例如缺少訊息），並得到訊息數與 token 數的統計。

1. **缺少 system/user 訊息**：統計缺少 "system" 或 "user" 訊息的對話數量。這些訊息對定義 assistant 的行為和開啟對話很關鍵。
2. **每筆範例的訊息數**：彙整每段對話的訊息數分布，可以看出對話的複雜度。
3. **每筆範例的總 token 數**：計算並彙整每段對話總 token 數的分布，對了解 fine-tuning 成本很重要。
4. **assistant 訊息的 token 數**：計算每段對話中 assistant 訊息的 token 數並彙整分布，可以看出 assistant 講話多不多話。
5. **token 上限警告**：檢查有沒有範例超過 token 上限（16,385 tokens），超過的範例在 fine-tuning 時會被截斷，可能造成資料遺失。


```python
# Warnings and tokens counts
n_missing_system = 0
n_missing_user = 0
n_messages = []
convo_lens = []
assistant_message_lens = []

for ex in dataset:
    messages = ex["messages"]
    if not any(message["role"] == "system" for message in messages):
        n_missing_system += 1
    if not any(message["role"] == "user" for message in messages):
        n_missing_user += 1
    n_messages.append(len(messages))
    convo_lens.append(num_tokens_from_messages(messages))
    assistant_message_lens.append(num_assistant_tokens_from_messages(messages))
    
print("Num examples missing system message:", n_missing_system)
print("Num examples missing user message:", n_missing_user)
print_distribution(n_messages, "num_messages_per_example")
print_distribution(convo_lens, "num_total_tokens_per_example")
print_distribution(assistant_message_lens, "num_assistant_tokens_per_example")
n_too_long = sum(l > 16385 for l in convo_lens)
print(f"\n{n_too_long} examples may be over the 16,385 token limit, they will be truncated during fine-tuning")
```

??? note "輸出"

    ```text
    Num examples missing system message: 1
    Num examples missing user message: 1

    #### Distribution of num_messages_per_example:
    min / max: 2, 9
    mean / median: 3.8, 3.0
    p5 / p95: 2.0, 6.6000000000000005

    #### Distribution of num_total_tokens_per_example:
    min / max: 26, 8032
    mean / median: 1648.4, 45.0
    p5 / p95: 26.8, 4863.6

    #### Distribution of num_assistant_tokens_per_example:
    min / max: 4, 8000
    mean / median: 1610.2, 10.0
    p5 / p95: 6.0, 4811.200000000001

    0 examples may be over the 16,385 token limit, they will be truncated during fine-tuning
    ```

## 成本估算

最後這一段，我們估算 fine-tuning 會用掉的總 token 數，藉此推算成本。要注意 fine-tuning job 的時間也會隨 token 數增加。 

```python
# Pricing and default n_epochs estimate
MAX_TOKENS_PER_EXAMPLE = 16385

TARGET_EPOCHS = 3
MIN_TARGET_EXAMPLES = 100
MAX_TARGET_EXAMPLES = 25000
MIN_DEFAULT_EPOCHS = 1
MAX_DEFAULT_EPOCHS = 25

n_epochs = TARGET_EPOCHS
n_train_examples = len(dataset)
if n_train_examples * TARGET_EPOCHS < MIN_TARGET_EXAMPLES:
    n_epochs = min(MAX_DEFAULT_EPOCHS, MIN_TARGET_EXAMPLES // n_train_examples)
elif n_train_examples * TARGET_EPOCHS > MAX_TARGET_EXAMPLES:
    n_epochs = max(MIN_DEFAULT_EPOCHS, MAX_TARGET_EXAMPLES // n_train_examples)

n_billing_tokens_in_dataset = sum(min(MAX_TOKENS_PER_EXAMPLE, length) for length in convo_lens)
print(f"Dataset has ~{n_billing_tokens_in_dataset} tokens that will be charged for during training")
print(f"By default, you'll train for {n_epochs} epochs on this dataset")
print(f"By default, you'll be charged for ~{n_epochs * n_billing_tokens_in_dataset} tokens")
```

??? note "輸出"

    ```text
    Dataset has ~4306 tokens that will be charged for during training
    By default, you'll train for 20 epochs on this dataset
    By default, you'll be charged for ~86120 tokens
    ```

實際總成本請參考 https://openai.com/pricing 來估算。

## 重點整理
- fine-tuning 前先驗證資料格式，能避免 job 送出後才因為格式錯誤失敗。
- 每則訊息都要有合法的 `role` 和字串 `content`，而且每段對話至少要有一則 assistant 訊息。
- 超過 token 上限的範例會被截斷，要在送出前先找出來。
- 成本跟總 token 數和 epoch 數成正比，先估算再決定要不要訓練。

## 練習
1. 在範例 JSONL 裡故意刪掉某一筆的 `role`，重跑驗證，看哪個錯誤類型的計數會增加。
2. 把 token 上限警告的門檻改小（例如 500），看有幾筆範例被標記。
3. 修改成本估算的 epoch 數，比較總 token 數怎麼變，並想想資料量變大時成本如何成長。
