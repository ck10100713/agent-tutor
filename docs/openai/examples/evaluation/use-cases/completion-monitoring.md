---
translated: true
status: deprecated
tags:
- 原文已封存
source: examples/evaluation/use-cases/completion-monitoring.ipynb
---

# Evals API 使用案例：監控已儲存的 completions

> 原文：[examples/evaluation/use-cases/completion-monitoring.ipynb](https://github.com/openai/openai-cookbook/blob/main/examples/evaluation/use-cases/completion-monitoring.ipynb)



## 這篇在做什麼
用 Evals API 檢查 prompt 改動有沒有造成 regression。資料來源是 production 已儲存的 chat completions，用兩個版本的 prompt 比較表現。

## 學完你會
- 用 `store=True` 和 metadata 記錄 chat completions，並以 stored completions 當 eval 的資料來源
- 建立 Eval（data source config 加上 model grader）和多個 Run
- 用 metadata filter 比較不同 prompt 版本，也能換模型重新產生 completions 比較

## 開跑前
需要 OpenAI API key。建立的 completions 要在 https://platform.openai.com/logs 看得到，後面步驟才能用。

Evals 是**以任務為導向**且可迭代的，是檢查你的 LLM 整合表現、並加以改進的最好方式。

下面這個 eval 要處理的任務是**偵測 prompt 改動造成的 regression**。

我們的使用情境是：
1. 我們一直在 production 的 chat completions 請求裡設定 `store=True` 來記錄請求。注意你也可以在管理面板開啟「預設記錄」（https://platform.openai.com/settings/organization/data-controls/data-retention）。
2. 我們想知道 prompt 改動有沒有造成 regression。

## Evals 的結構

Evals 有兩個部分，「Eval」和「Run」。「Eval」保存你的測試準則設定，以及「Run」的資料結構。一個 Eval 可以有很多個 Run，每個 Run 都會用你的測試準則來評估。

```python
from openai import AsyncOpenAI
import os
import asyncio

os.environ["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "your-api-key")
client = AsyncOpenAI()
```

## 使用案例

我們要測試的整合是推播通知摘要：它接收多則推播通知，並濃縮成一則，這是一個 chat completions 呼叫。

# 產生測試資料

我會用兩個不同版本的 prompt 產生模擬的 production chat completions 請求，測試各自的表現。第一個是「好」的 prompt，第二個是「壞」的 prompt。它們會帶不同的 metadata，後面會用到。

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

```python
PROMPTS = [
    (
        """
        You are a helpful assistant that summarizes push notifications.
        You are given a list of push notifications and you need to collapse them into a single one.
        Output only the final summary, nothing else.
        """,
        "v1"
    ),
    (
        """
        You are a helpful assistant that summarizes push notifications.
        You are given a list of push notifications and you need to collapse them into a single one.
        The summary should be longer than it needs to be and include more information than is necessary.
        Output only the final summary, nothing else.
        """,
        "v2"
    )
]

tasks = []
for notifications in push_notification_data:
    for (prompt, version) in PROMPTS:
        tasks.append(client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "developer", "content": prompt},
                {"role": "user", "content": notifications},
            ],
            store=True,
            metadata={"prompt_version": version, "usecase": "push_notifications_summarizer"},
        ))
await asyncio.gather(*tasks)
```

你可以到 https://platform.openai.com/logs 查看剛建立的 completions。

**請確認這些 chat completions 有出現，因為下一步需要它們。**

```python
completions = await client.chat.completions.list()
assert completions.data, "No completions found. You may need to enable logs in your admin panel."
completions.data[0]
```

# 設定你的 eval

Eval 保存多個 *Run* 共用的設定，有兩個組成：
1. 資料來源設定 `data_source_config`：你之後的 *Run* 要遵循的 schema（欄位）。
    - `data_source_config` 用 JSON Schema 定義 Eval 裡有哪些變數可用。
2. 測試準則 `testing_criteria`：你要怎麼判斷資料來源的每一*列*，整合是否運作正常。

這個使用案例用的是 stored-completions，所以我們設定對應的 data_source_config

**重要**
你很可能有許多不同的 stored completions 使用情境，metadata 是追蹤它們的最佳方式，能讓 eval 保持聚焦、以任務為導向。

```python
# We want our input data to be available in our variables, so we set the item_schema to
# PushNotifications.model_json_schema()
data_source_config = {
    "type": "stored_completions",
    "metadata": {
        "usecase": "push_notifications_summarizer"
    }
}
```

這個 data_source_config 定義了整個 eval 裡可用的變數。

stored completions 的設定提供兩個變數，讓你在 eval 裡使用：
1. {{item.input}}：送進 completions 呼叫的 messages
2. {{sample.output_text}}：assistant 回應的文字

**接下來用這些變數來設定測試準則。**

```python
GRADER_DEVELOPER_PROMPT = """
Label the following push notification summary as either correct or incorrect.
The push notification and the summary will be provided below.
A good push notificiation summary is concise and snappy.
If it is good, then label it as correct, if not, then incorrect.
"""
GRADER_TEMPLATE_PROMPT = """
Push notifications: {{item.input}}
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

`push_notification_grader` 是一個 model grader（llm-as-a-judge），它會看輸入 `{{item.input}}` 和產生的摘要 `{{sample.output_text}}`，並把它標成 "correct" 或 "incorrect"。

注意：底層用的是 structured outputs，所以標籤一定是合法值。

**現在建立 eval，並開始加入資料**

```python
eval_create_result = await client.evals.create(
    name="Push Notification Completion Monitoring",
    metadata={"description": "This eval monitors completions"},
    data_source_config=data_source_config,
    testing_criteria=[push_notification_grader],
)

eval_id = eval_create_result.id
```

# 建立 Run

eval 和測試準則設定好之後，就可以開始加入 Run。
我想比較我的兩個 **prompt 版本**之間的表現

做法是把資料來源定義成 "stored_completions"，並為每個 prompt 版本加上 metadata filter。

```python
# Grade prompt_version=v1
eval_run_result = await client.evals.runs.create(
    eval_id=eval_id,
    name="v1-run",
    data_source={
        "type": "completions",
        "source": {
            "type": "stored_completions",
            "metadata": {
                "prompt_version": "v1",
            }
        }
    }
)
print(eval_run_result.report_url)
```

```python
# Grade prompt_version=v2
eval_run_result_v2 = await client.evals.runs.create(
    eval_id=eval_id,
    name="v2-run",
    data_source={
        "type": "completions",
        "source": {
            "type": "stored_completions",
            "metadata": {
                "prompt_version": "v2",
            }
        }
    }
)
print(eval_run_result_v2.report_url)
```

為了更完整，我們看看這個 prompt 用 4o 而不是 4o-mini 表現如何，兩個 prompt 版本都當起點。

只需要引用輸入 messages（{{item.input}}），並把模型設成 4o。因為我們還沒有任何 4o 的 stored completions，這個 eval run 會產生新的 completions。

```python
tasks = []
for prompt_version in ["v1", "v2"]:
    tasks.append(client.evals.runs.create(
        eval_id=eval_id,
        name=f"post-fix-new-model-run-{prompt_version}",
        data_source={
            "type": "completions",
            "input_messages": {
                "type": "item_reference",
                "item_reference": "item.input",
            },
            "model": "gpt-4o",
            "source": {
                "type": "stored_completions",
                "metadata": {
                    "prompt_version": prompt_version,
                }
            }
        },
    ))
result = await asyncio.gather(*tasks)
for run in result:
    print(run.report_url)
```

打開那份報告就會看到，prompt_version=v2 出現了 regression！

## 恭喜，你剛發現了一個 bug，可以把它 revert，或再改一次 prompt 等等！

## 重點整理
- Eval 保存測試準則和資料結構，Run 是用這些準則評估的一次執行，一個 Eval 可以有很多 Run。
- 用 `store=True` 加 metadata 記錄 production 請求，就能直接拿真實流量當 eval 資料。
- model grader 用 `{{item.input}}` 和 `{{sample.output_text}}` 兩個變數評斷輸出好壞。
- 用 metadata filter 區分 prompt 版本，就能偵測 prompt 改動造成的 regression。

## 練習
1. 改 grader 的評分指示，讓它對摘要多加一條標準（例如不能超過一句話）。
2. 新增第三個 prompt 版本的 completions，建立對應的 Run 一起比較。
3. 把重新產生 completions 的 Run 換成別的模型，看 regression 是否仍然存在。
