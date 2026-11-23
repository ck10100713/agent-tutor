---
translated: true
source: misc/batch_processing.ipynb
---

# 用 Message Batches API 做批次處理

> 原文：[misc/batch_processing.ipynb](https://github.com/anthropics/claude-cookbooks/blob/main/misc/batch_processing.ipynb)

用 batch 非同步處理大量 Claude request，成本降低 50%。

## 這篇在做什麼

示範用 Message Batches API 非同步處理大量 request：建立並送出 batch、追蹤處理進度、取回結果，最後處理包含不同訊息類型的進階例子。

## 學完你會

- 建立並送出一個 message batch，並輪詢它的狀態
- 取回結果並處理成功與失敗的 request
- 在同一個 batch 混用簡單訊息、system prompt、多輪對話和圖片

## 開跑前

需要 Anthropic API key。

Message Batches 讓你能以非同步又省錢的方式處理大量 Messages request。這份 cookbook 示範怎麼用 Message Batches API 處理批次作業，同時把成本降低 50%。

這份 cookbook 會示範：

1. 建立並送出 message batch
2. 監控 batch 的處理狀態
3. 取回並處理 batch 結果
4. 實作有效 batching 的最佳實踐

## 設定

先設定環境，匯入需要的套件：

```python
%pip install anthropic
```

```python
import time

import anthropic

client = anthropic.Anthropic()
MODEL_NAME = "claude-sonnet-5-5"
```

## 範例 1：基本 batch 處理

先從簡單的例子開始，示範建立並監控一批 message request。

```python
# Prepare a list of questions for batch processing
questions = [
    "How do solar panels convert sunlight into electricity?",
    "What's the difference between mutual funds and ETFs?",
    "What is a pick and roll in basketball?",
    "Why do leaves change color in autumn?",
]

# Create batch requests
batch_requests = [
    {
        "custom_id": f"question-{i}",
        "params": {
            "model": MODEL_NAME,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": question}],
        },
    }
    for i, question in enumerate(questions)
]

# Submit the batch
response = client.beta.messages.batches.create(requests=batch_requests)

print(f"Batch ID: {response.id}")
print(f"Status: {response.processing_status}")
print(f"Created at: {response.created_at}")
```

??? note "輸出"

    ```text
    Batch ID: msgbatch_01GgqTz9XzriGNHzTSGZsJJ8
    Status: in_progress
    Created at: 2024-10-08 00:46:30.694748+00:00
    ```

# 監控 batch 進度

現在來監控 batch 的處理狀態：

```python
def monitor_batch(batch_id, polling_interval=5):
    while True:
        batch_update = client.beta.messages.batches.retrieve(batch_id)
        batch_update_status = batch_update.processing_status
        print(batch_update)
        print(f"Status: {batch_update_status}")
        if batch_update_status == "ended":
            return batch_update

        time.sleep(polling_interval)


# Monitor our batch
batch_result = monitor_batch(response.id)
print("\nBatch processing complete!")
print("\nRequest counts:")
print(f"  Succeeded: {batch_result.request_counts.succeeded}")
print(f"  Errored: {batch_result.request_counts.errored}")
print(f"  Processing: {batch_result.request_counts.processing}")
print(f"  Canceled: {batch_result.request_counts.canceled}")
print(f"  Expired: {batch_result.request_counts.expired}")
```

??? note "輸出"

    ```text
    BetaMessageBatch(id='msgbatch_01GgqTz9XzriGNHzTSGZsJJ8', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_01GgqTz9XzriGNHzTSGZsJJ8', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_01GgqTz9XzriGNHzTSGZsJJ8', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_01GgqTz9XzriGNHzTSGZsJJ8', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), ended_at=datetime.datetime(2024, 10, 8, 0, 46, 47, 283392, tzinfo=TzInfo(UTC)), expires_at=datetime.datetime(2024, 10, 9, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), processing_status='ended', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=0, succeeded=4), results_url='https://api.anthropic.com/v1/messages/batches/msgbatch_01GgqTz9XzriGNHzTSGZsJJ8/results', type='message_batch')
    Status: ended

    Batch processing complete!

    Request counts:
      Succeeded: 4
      Errored: 0
      Processing: 0
      Canceled: 0
      Expired: 0
    ```

# 取回結果

batch 完成後，就能取回並處理結果：

```python
def process_results(batch_id):
    # First get the batch status
    batch = client.beta.messages.batches.retrieve(batch_id)

    print(f"\nBatch {batch.id} Summary:")
    print(f"Status: {batch.processing_status}")
    print(f"Created: {batch.created_at}")
    print(f"Ended: {batch.ended_at}")
    print(f"Expires: {batch.expires_at}")

    if batch.processing_status == "ended":
        print("\nIndividual Results:")
        for result in client.beta.messages.batches.results(batch_id):
            print(f"\nResult for {result.custom_id}:")
            print(f"Status: {result.result.type}")

            if result.result.type == "succeeded":
                # The message can start with a thinking block, so read the text block.
                text = next(b.text for b in result.result.message.content if b.type == "text")
                print(f"Content: {text[:200]}...")
            elif result.result.type == "errored":
                print("Request errored")
            elif result.result.type == "canceled":
                print("Request was canceled")
            elif result.result.type == "expired":
                print("Request expired")


# Example usage:
batch_status = monitor_batch(response.id)
if batch_status.processing_status == "ended":
    process_results(batch_status.id)
```

??? note "輸出"

    ```text
    BetaMessageBatch(id='msgbatch_01GgqTz9XzriGNHzTSGZsJJ8', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), ended_at=datetime.datetime(2024, 10, 8, 0, 46, 47, 283392, tzinfo=TzInfo(UTC)), expires_at=datetime.datetime(2024, 10, 9, 0, 46, 30, 694748, tzinfo=datetime.timezone.utc), processing_status='ended', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=0, succeeded=4), results_url='https://api.anthropic.com/v1/messages/batches/msgbatch_01GgqTz9XzriGNHzTSGZsJJ8/results', type='message_batch')
    Status: ended

    Batch msgbatch_01GgqTz9XzriGNHzTSGZsJJ8 Summary:
    Status: ended
    Created: 2024-10-08 00:46:30.694748+00:00
    Ended: 2024-10-08 00:46:47.283392+00:00
    Expires: 2024-10-09 00:46:30.694748+00:00

    Individual Results:

    Result for question-0:
    Status: succeeded
    Content: Solar panels convert sunlight into electricity through a process called the photovoltaic effect. Here's a step-by-step explanation of how this works:

    1. Solar panel composition:
    Solar panels are made...

    Result for question-1:
    Status: succeeded
    Content: Mutual funds and ETFs (Exchange-Traded Funds) are both popular investment vehicles that allow investors to diversify their portfolios, but they have several key differences:

    1. Trading:
    - Mutual fund...

    Result for question-2:
    Status: succeeded
    Content: A pick and roll, also known as a screen and roll, is a fundamental offensive play in basketball involving two players. Here's how it works:

    1. The ball handler (usually a guard) has possession of the...

    Result for question-3:
    Status: succeeded
    Content: Leaves change color in autumn due to a combination of factors, primarily related to changes in temperature, daylight, and the tree's biological processes. Here's a breakdown of why this happens:

    1. C...
    ```

## 範例 2：處理不同訊息類型的進階 batch

這個例子示範更進階的用法，包含錯誤處理，以及在同一個 batch 裡處理不同類型的 request：簡單訊息、帶 system prompt 的訊息、多輪訊息，和帶圖片的訊息。

```python
import base64


def create_complex_batch():
    # Get base64 encoded image
    def get_base64_encoded_image(image_path):
        with open(image_path, "rb") as image_file:
            binary_data = image_file.read()
            base_64_encoded_data = base64.b64encode(binary_data)
            base64_string = base_64_encoded_data.decode("utf-8")
            return base64_string

    # Mix of different request types
    batch_requests = [
        {
            "custom_id": "simple-question",
            "params": {
                "model": MODEL_NAME,
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": "What is quantum computing?"}],
            },
        },
        {
            "custom_id": "image-analysis",
            "params": {
                "model": MODEL_NAME,
                "max_tokens": 1024,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": get_base64_encoded_image(
                                        "../images/sunset-dawn-nature-mountain-preview.jpg"
                                    ),
                                },
                            },
                            {
                                "type": "text",
                                "text": "Describe this mountain landscape. What time of day does it appear to be, and what weather conditions do you observe?",
                            },
                        ],
                    }
                ],
            },
        },
        {
            "custom_id": "system-prompt",
            "params": {
                "model": MODEL_NAME,
                "max_tokens": 1024,
                "system": "You are a helpful science teacher.",
                "messages": [{"role": "user", "content": "Explain gravity to a 5-year-old."}],
            },
        },
        {
            "custom_id": "multi-turn",
            "params": {
                "model": MODEL_NAME,
                "max_tokens": 1024,
                "messages": [
                    {"role": "user", "content": "What is DNA?"},
                    {
                        "role": "assistant",
                        "content": "DNA is like a blueprint for living things...",
                    },
                    {"role": "user", "content": "How is DNA copied?"},
                ],
            },
        },
    ]

    try:
        response = client.beta.messages.batches.create(requests=batch_requests)
        return response.id
    except Exception as e:
        print(f"Error creating batch: {e}")
        return None


complex_batch_id = create_complex_batch()
print(f"Complex batch ID: {complex_batch_id}")
```

??? note "輸出"

    ```text
    Complex batch ID: msgbatch_011FAkvqkL8pEskdyS3xdmNW
    ```

好，現在來看這個 batch 的結果：

```python
# Example usage:
batch_status = monitor_batch(complex_batch_id)
if batch_status.processing_status == "ended":
    process_results(batch_status.id)
```

??? note "輸出"

    ```text
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=None, expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='in_progress', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=4, succeeded=0), results_url=None, type='message_batch')
    Status: in_progress
    BetaMessageBatch(id='msgbatch_011FAkvqkL8pEskdyS3xdmNW', cancel_initiated_at=None, created_at=datetime.datetime(2024, 10, 8, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), ended_at=datetime.datetime(2024, 10, 8, 0, 24, 27, 768229, tzinfo=TzInfo(UTC)), expires_at=datetime.datetime(2024, 10, 9, 0, 23, 58, 507550, tzinfo=datetime.timezone.utc), processing_status='ended', request_counts=RequestCounts(canceled=0, errored=0, expired=0, processing=0, succeeded=4), results_url='https://api.anthropic.com/v1/messages/batches/msgbatch_011FAkvqkL8pEskdyS3xdmNW/results', type='message_batch')
    Status: ended

    Batch msgbatch_011FAkvqkL8pEskdyS3xdmNW Summary:
    Status: ended
    Created: 2024-10-08 00:23:58.507550+00:00
    Ended: 2024-10-08 00:24:27.768229+00:00
    Expires: 2024-10-09 00:23:58.507550+00:00

    Individual Results:

    Result for simple-question:
    Status: succeeded
    Content: Quantum computing is an advanced form of computing that uses the principles of quantum mechanics to process information. Unlike classical computers that use bits (0s and 1s) to store and process data,...

    Result for image-analysis:
    Status: succeeded
    Content: This image captures a breathtaking mountain landscape at sunset. The sun is visible as a bright orb just dipping behind the distant mountain ranges, casting a warm golden glow across the entire scene....

    Result for system-prompt:
    Status: succeeded
    Content: Sure! Here's how I might explain gravity to a 5-year-old:

    Gravity is like a big invisible hug that the Earth gives to everything on it. It's what keeps us stuck to the ground instead of floating away...

    Result for multi-turn:
    Status: succeeded
    Content: DNA replication is the process by which DNA makes a copy of itself during cell division. Here's a basic overview of how it works:
    ... (省略 2 行)
    ```

## 重點整理

- Batch API 是非同步的，換來 50% 的成本折扣，適合不需要即時回應的大量任務。
- 流程是建立、輪詢狀態、取回結果，三步分開。
- 每個 request 有自己的 `custom_id`，結果要靠它對回原本的 request。
- 同一個 batch 裡的 request 可以長得不一樣，也要為個別失敗做錯誤處理。

## 練習

1. 把範例 1 的 request 數量增加到 10 個，觀察完成時間。
2. 在範例 2 的 batch 裡加一個故意錯誤的 request（例如不存在的模型名），看結果怎麼回報。
3. 寫一個函式，把結果依 `custom_id` 整理成 dict。
