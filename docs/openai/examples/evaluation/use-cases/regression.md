---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/use-cases/regression.ipynb
---

# Evals API 使用案例：偵測 prompt 退步

> 原文：[examples/evaluation/use-cases/regression.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/regression.ipynb)



## 這篇在做什麼
用 Evals API 建立一個 eval，偵測改了 prompt 之後是不是讓結果變差。情境是一個把多則推播通知濃縮成一句話的 LLM 功能。

## 學完你會
- 用 JSON Schema 定義 eval 的 `data_source_config`，並設定 model grader 當 `testing_criteria`
- 對同一個 eval 建立多個 run，比較 baseline 和修改後 prompt 的分數
- 在 prompt 被改壞時，透過 eval 報告的低分及早發現

## 開跑前
需要 OpenAI API key。建立 run 會呼叫模型，產生 API 費用。

Eval 是**以任務為導向**且可迭代的，是檢查 LLM 整合表現並加以改善的最好方式。

在下面這個 eval 裡，我們聚焦在**偵測我改了 prompt 是不是造成退步**這個任務。

我們的使用情境是：
1. 我有一個 llm 整合，接收一串推播通知，並把它們摘要成一句濃縮的陳述。
2. 我想偵測 prompt 的改動是否讓行為退步

## Eval 的結構

Eval 有兩個部分，「Eval」和「Run」。「Eval」裡放你的測試標準設定，以及「Run」的資料結構。一個 Eval 可以有很多個 run，由你的測試標準來評估。

```python
import openai
from openai.types.chat import ChatCompletion
import pydantic
import os

os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "your-api-key")
```

## 使用案例

我們要測試下面這個整合，也就是推播通知摘要，它接收多則推播通知，並把它們合併成一則，這是一個 chat completions 呼叫。

```python
class PushNotifications(pydantic.BaseModel):
    notifications: str

print(PushNotifications.model_json_schema())
```

```python
DEVELOPER_PROMPT = """
You are a helpful assistant that summarizes push notifications.
You are given a list of push notifications and you need to collapse them into a single one.
Output only the final summary, nothing else.
"""

def summarize_push_notification(push_notifications: str) -> ChatCompletion:
    result = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": push_notifications},
        ],
    )
    return result

example_push_notifications_list = PushNotifications(notifications="""
- Alert: Unauthorized login attempt detected.
- New comment on your blog post: "Great insights!"
- Tonight's dinner recipe: Pasta Primavera.
""")
result = summarize_push_notification(example_push_notifications_list.notifications)
print(result.choices[0].message.content)
```

# 設定你的 eval

Eval 裡放的是多個 *Run* 共用的設定，它有兩個組成：
1. 資料來源設定 `data_source_config`：未來的 *Run* 要遵循的 schema（欄位）。
    - `data_source_config` 用 JSON Schema 定義 Eval 中可用的變數。
2. 測試標準 `testing_criteria`：你要怎麼判斷資料來源中每一*列*資料的整合有沒有正常運作。

在這個使用案例裡，我們想測試推播通知摘要的結果好不好，所以會照這個目標來設定 eval。

```python
# We want our input data to be available in our variables, so we set the item_schema to
# PushNotifications.model_json_schema()
data_source_config = {
    "type": "custom",
    "item_schema": PushNotifications.model_json_schema(),
    # We're going to be uploading completions from the API, so we tell the Eval to expect this
    "include_sample_schema": True,
}
```

這個 data_source_config 定義了整個 eval 中有哪些變數可用。

這個 item schema：
```json
{
  "properties": {
    "notifications": {
      "title": "Notifications",
      "type": "string"
    }
  },
  "required": ["notifications"],
  "title": "PushNotifications",
  "type": "object"
}
```
代表我們的 eval 裡會有 `{{item.notifications}}` 這個變數可用。

`"include_sample_schema": True`
代表我們的 eval 裡會有 `{{sample.output_text}}` 這個變數可用。

**現在，我們用這些變數來設定測試標準。**

```python
GRADER_DEVELOPER_PROMPT = """
Label the following push notification summary as either correct or incorrect.
The push notification and the summary will be provided below.
A good push notificiation summary is concise and snappy.
If it is good, then label it as correct, if not, then incorrect.
"""
GRADER_TEMPLATE_PROMPT = """
Push notifications: {{item.notifications}}
Summary: {{sample.output_text}}
"""
push_notification_grader = {
    "name": "Push Notification Summary Grader",
    "type": "label_model",
    "model": "o3-mini",
    "input": [
        {
            "role": "developer",
            "content": GRADER_DEVELOPER_PROMPT,
        },
        {
            "role": "user",
            "content": GRADER_TEMPLATE_PROMPT,
        },
    ],
    "passing_labels": ["correct"],
    "labels": ["correct", "incorrect"],
}
```

`push_notification_grader` 是一個 model grader（llm-as-a-judge），它會看輸入 `{{item.notifications}}` 和產生的摘要 `{{sample.output_text}}`，並標記為 "correct" 或 "incorrect"。
接著我們透過 "passing_labels" 指定什麼樣的答案算通過。

注意：它底層用的是 structured outputs，所以標籤一定是合法的。

**現在來建立 eval！並開始加資料進去**

```python
eval_create_result = openai.evals.create(
    name="Push Notification Summary Workflow",
    metadata={
        "description": "This eval checks if the push notification summary is correct.",
    },
    data_source_config=data_source_config,
    testing_criteria=[push_notification_grader],
)

eval_id = eval_create_result.id
```

# 建立 run

現在 eval 已經用 test_criteria 設定好了，可以開始新增一堆 run！
我們先從一些推播通知資料開始。

```python
push_notification_data = [
        """
- New message from Sarah: "Can you call me later?"
- Your package has been delivered!
- Flash sale: 20% off electronics for the next 2 hours!
""",
        """
- Weather alert: Thunderstorm expected in your area.
- Reminder: Doctor's appointment at 3 PM.
- John liked your photo on Instagram.
""",
        """
- Breaking News: Local elections results are in.
- Your daily workout summary is ready.
- Check out your weekly screen time report.
""",
        """
- Your ride is arriving in 2 minutes.
- Grocery order has been shipped.
- Don't miss the season finale of your favorite show tonight!
""",
        """
- Event reminder: Concert starts at 7 PM.
- Your favorite team just scored!
- Flashback: Memories from 3 years ago.
""",
        """
- Low battery alert: Charge your device.
- Your friend Mike is nearby.
- New episode of "The Tech Hour" podcast is live!
""",
        """
- System update available.
- Monthly billing statement is ready.
- Your next meeting starts in 15 minutes.
""",
        """
- Alert: Unauthorized login attempt detected.
- New comment on your blog post: "Great insights!"
- Tonight's dinner recipe: Pasta Primavera.
""",
        """
- Special offer: Free coffee with any breakfast order.
- Your flight has been delayed by 30 minutes.
- New movie release: "Adventures Beyond" now streaming.
""",
        """
- Traffic alert: Accident reported on Main Street.
- Package out for delivery: Expected by 5 PM.
- New friend suggestion: Connect with Emma.
"""]
```

第一個 run 會用上面 completions 函式 `summarize_push_notification` 的預設結果。
我們會跑過資料集，呼叫 completions，然後把結果當成一個 run 送出去打分。

```python
run_data = []
for push_notifications in push_notification_data:
    result = summarize_push_notification(push_notifications)
    run_data.append({
        "item": PushNotifications(notifications=push_notifications).model_dump(),
        "sample": result.model_dump()
    })

eval_run_result = openai.evals.runs.create(
    eval_id=eval_id,
    name="baseline-run",
    data_source={
        "type": "jsonl",
        "source": {
            "type": "file_content",
            "content": run_data,
        }
    },
)
print(eval_run_result)
# Check out the results in the UI
print(eval_run_result.report_url)
```

現在來模擬一次退步，這是我們原本的 prompt，我們模擬開發者把 prompt 改壞的情況。

```python
DEVELOPER_PROMPT = """
You are a helpful assistant that summarizes push notifications.
You are given a list of push notifications and you need to collapse them into a single one.
Output only the final summary, nothing else.
"""
```

```python
DEVELOPER_PROMPT = """
You are a helpful assistant that summarizes push notifications.
You are given a list of push notifications and you need to collapse them into a single one.
You should make the summary longer than it needs to be and include more information than is necessary.
"""

def summarize_push_notification_bad(push_notifications: str) -> ChatCompletion:
    result = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "developer", "content": DEVELOPER_PROMPT},
            {"role": "user", "content": push_notifications},
        ],
    )
    return result
```

```python
run_data = []
for push_notifications in push_notification_data:
    result = summarize_push_notification_bad(push_notifications)
    run_data.append({
        "item": PushNotifications(notifications=push_notifications).model_dump(),
        "sample": result.model_dump()
    })

eval_run_result = openai.evals.runs.create(
    eval_id=eval_id,
    name="regression-run",
    data_source={
        "type": "jsonl",
        "source": {
            "type": "file_content",
            "content": run_data,
        }
    },
)
print(eval_run_result.report_url)
```

如果你看那份報告，會發現它的分數比 baseline-run 低很多。

## 恭喜，你剛剛阻止了一個 bug 上線到使用者手上

小提醒：
Evals 目前還沒有原生支援 `responses` API，不過你可以用下面的程式把它轉成 `completions` 格式。

```python
def summarize_push_notification_responses(push_notifications: str):
    result = openai.responses.create(
                model="gpt-4o",
                input=[
                    {"role": "developer", "content": DEVELOPER_PROMPT},
                    {"role": "user", "content": push_notifications},
                ],
            )
    return result
def transform_response_to_completion(response):
    completion = {
        "model": response.model,
        "choices": [{
        "index": 0,
        "message": {
            "role": "assistant",
            "content": response.output_text
        },
        "finish_reason": "stop",
    }]
    }
    return completion

run_data = []
for push_notifications in push_notification_data:
    response = summarize_push_notification_responses(push_notifications)
    completion = transform_response_to_completion(response)
    run_data.append({
        "item": PushNotifications(notifications=push_notifications).model_dump(),
        "sample": completion
    })

report_response = openai.evals.runs.create(
    eval_id=eval_id,
    name="responses-run",
    data_source={
        "type": "jsonl",
        "source": {
            "type": "file_content",
            "content": run_data,
        }
    },
)
print(report_response.report_url)
```

## 重點整理
- Eval 分成兩層：Eval 放共用設定（資料 schema 和測試標準），Run 是每次實際的測試。
- `data_source_config` 決定 eval 中有哪些變數可用，`testing_criteria` 決定怎麼打分。
- model grader（llm-as-a-judge）用 structured outputs，標籤格式保證合法。
- 改 prompt 前後各跑一個 run 並比較分數，就能在上線前抓出退步。

## 練習
1. 修改 `push_notification_grader` 的 `passing_labels`，讓判準更嚴格，看 baseline 的分數怎麼變。
2. 在資料集中加幾筆推播通知，重跑 baseline run。
3. 自己寫一個更糟（或更好）的 prompt 版本當新的 run，在報告中比較三個 run 的分數。
